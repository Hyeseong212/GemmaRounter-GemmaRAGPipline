from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from .client import GemmaChatClient, ModelClient
from .config import RouterSettings, load_project_env
from .handoff import build_handoff
from .hard_rules import apply_hard_rules
from .models import (
    CompactHandoff,
    DecisionSource,
    DownstreamHandoff,
    HarnessTraceEntry,
    LocalExecutionResult,
    ModelRouteChoice,
    NormalizedRouterInput,
    RouterDisplay,
    RouterDecision,
    RouterHandledResult,
    RouterInput,
    RouterResult,
)
from .policies import apply_post_policies
from .prompts import (
    build_local_answer_user_prompt,
    build_router_user_prompt,
    load_system_prompt,
)
from .signals import normalize_router_input

logger = logging.getLogger("uvicorn.error")


@dataclass
class RouterService:
    settings: RouterSettings
    model_client: ModelClient
    system_prompt: str
    local_answer_system_prompt: str

    async def route(self, request: RouterInput) -> RouterResult:
        normalized_request = normalize_router_input(request)
        trace = [
            HarnessTraceEntry(
                stage="normalize",
                status="passed",
                detail="Input was normalized and routing signals were extracted.",
                data=normalized_request.detected_signals.model_dump(),
            )
        ]

        hard_rule_match = apply_hard_rules(normalized_request)
        if hard_rule_match is not None:
            trace.append(
                HarnessTraceEntry(
                    stage="hard_rule",
                    status="applied",
                    detail=hard_rule_match.detail,
                    data={"rule_name": hard_rule_match.rule_name},
                )
            )
            final_decision, policy_traces = apply_post_policies(
                normalized_request,
                hard_rule_match.decision,
            )
            trace.extend(policy_traces)
            handoff = build_handoff(normalized_request, final_decision)
            trace.append(
                HarnessTraceEntry(
                    stage="handoff",
                    status="generated",
                    detail="Generated downstream execution contract for the selected route.",
                    data={"target_system": handoff.target_system, "task_type": handoff.task_type},
                )
            )
            result = RouterResult(
                display=_build_display("hard_rule", final_decision, handoff),
                decision_source="hard_rule",
                decision=final_decision,
                handoff=handoff,
                normalized_input=normalized_request,
                trace=trace,
            )
            _log_router_decision(
                normalized_request=normalized_request,
                result=result,
                branch=f"hard_rule:{hard_rule_match.rule_name}",
                pre_policy_route=hard_rule_match.decision.route,
                policy_override_count=len(policy_traces),
            )
            return result

        model_decision, decision_source, model_traces = await self._get_model_decision(normalized_request)
        trace.extend(model_traces)

        final_decision, policy_traces = apply_post_policies(normalized_request, model_decision)
        trace.extend(policy_traces)

        handoff = build_handoff(normalized_request, final_decision)
        trace.append(
            HarnessTraceEntry(
                stage="handoff",
                status="generated",
                detail="Generated downstream execution contract for the selected route.",
                data={"target_system": handoff.target_system, "task_type": handoff.task_type},
            )
        )

        result = RouterResult(
            display=_build_display(decision_source, final_decision, handoff),
            decision_source=decision_source,
            decision=final_decision,
            handoff=handoff,
            normalized_input=normalized_request,
            trace=trace,
        )
        _log_router_decision(
            normalized_request=normalized_request,
            result=result,
            branch=f"{decision_source}:{model_decision.route}",
            pre_policy_route=model_decision.route,
            policy_override_count=len(policy_traces),
        )
        return result

    async def handle(self, request: RouterInput) -> RouterHandledResult:
        routed = await self.route(request)
        if routed.handoff is None:
            raise ValueError("Router result is missing a downstream handoff")

        compact_handoff = _to_compact_handoff(routed.handoff)
        if routed.decision.route != "local_llm":
            return RouterHandledResult(display=routed.display, handoff=compact_handoff)

        execution = await self._execute_local_answer(routed.normalized_input, routed.handoff)
        _log_local_execution(routed.normalized_input, execution)

        if execution.status == "completed":
            return RouterHandledResult(
                display=routed.display,
                handoff=compact_handoff,
                execution=execution,
            )

        rerouted_decision = _build_local_execution_reroute_decision(
            routed.normalized_input,
            execution.reason,
        )
        rerouted_handoff = build_handoff(routed.normalized_input, rerouted_decision)
        rerouted_display = _build_local_execution_display(
            rerouted_decision,
            rerouted_handoff,
            execution.reason,
        )

        return RouterHandledResult(
            display=rerouted_display,
            handoff=_to_compact_handoff(rerouted_handoff),
            execution=execution,
        )

    async def _get_model_decision(
        self,
        request: NormalizedRouterInput,
    ) -> tuple[RouterDecision, DecisionSource, list[HarnessTraceEntry]]:
        trace: list[HarnessTraceEntry] = []
        user_prompt = build_router_user_prompt(request)

        try:
            raw_response = await self.model_client.complete(self.system_prompt, user_prompt)
            parsed = _extract_json_object(raw_response)
            choice = ModelRouteChoice.model_validate(parsed)
            decision = _decision_from_model_choice(request, choice)
            trace.append(
                HarnessTraceEntry(
                    stage="model",
                    status="generated",
                    detail="Model produced a compact route choice.",
                    data={"route": choice.route},
                )
            )
            return decision, "model", trace
        except Exception as exc:
            trace.append(
                HarnessTraceEntry(
                    stage="model",
                    status="failed",
                    detail="Model output was invalid and the router fell back to deterministic routing.",
                    data={"error": str(exc)},
                )
            )

        fallback = _fallback_decision(request)
        trace.append(
            HarnessTraceEntry(
                stage="fallback",
                status="applied",
                detail="Fallback applied a deterministic minimal route.",
                data={"route": fallback.route},
            )
        )
        return fallback, "fallback", trace

    async def _execute_local_answer(
        self,
        request: NormalizedRouterInput,
        handoff: DownstreamHandoff,
    ) -> LocalExecutionResult:
        max_answer_chars = int(handoff.metadata.get("max_answer_chars", 20))
        user_prompt = build_local_answer_user_prompt(
            request,
            max_answer_chars=max_answer_chars,
        )

        try:
            raw_response = await self.model_client.complete(
                self.local_answer_system_prompt,
                user_prompt,
                temperature=self.settings.local_answer_temperature,
                max_tokens=self.settings.local_answer_max_tokens,
            )
        except Exception:
            return LocalExecutionResult(
                mode="local_llm",
                status="rerouted",
                answer=None,
                answer_char_count=None,
                reason="local_generation_failed",
                rerouted_to=_local_execution_fallback_route(request),
            )

        answer = _sanitize_local_answer(raw_response)
        if not answer:
            return LocalExecutionResult(
                mode="local_llm",
                status="rerouted",
                answer=None,
                answer_char_count=0,
                reason="local_generation_failed",
                rerouted_to=_local_execution_fallback_route(request),
            )

        answer_char_count = len(answer)
        if answer_char_count > max_answer_chars:
            return LocalExecutionResult(
                mode="local_llm",
                status="rerouted",
                answer=None,
                answer_char_count=answer_char_count,
                reason="local_answer_overflow",
                rerouted_to=_local_execution_fallback_route(request),
            )

        return LocalExecutionResult(
            mode="local_llm",
            status="completed",
            answer=answer,
            answer_char_count=answer_char_count,
            reason="completed",
            rerouted_to=None,
        )


def build_router_service(settings: RouterSettings | None = None) -> RouterService:
    load_project_env()
    resolved_settings = settings or RouterSettings()
    system_prompt = load_system_prompt(resolved_settings.prompt_path)
    local_answer_system_prompt = load_system_prompt(resolved_settings.local_answer_prompt_path)
    model_client = GemmaChatClient(resolved_settings)
    return RouterService(
        settings=resolved_settings,
        model_client=model_client,
        system_prompt=system_prompt,
        local_answer_system_prompt=local_answer_system_prompt,
    )


def _extract_json_object(raw_text: str) -> dict[str, object]:
    stripped = raw_text.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```").strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")

    return json.loads(stripped[start : end + 1])


def _fallback_decision(request: NormalizedRouterInput) -> RouterDecision:
    signals = request.detected_signals

    if signals.reference_grounding_required:
        if signals.network_limited:
            if signals.error_codes and "cached_error_help" in request.local_tools_available:
                return RouterDecision(
                    intent="device_error_question",
                    risk_level="medium",
                    route="local_rule_only",
                    needs_human_review=False,
                    patient_related=False,
                    priority="high",
                    required_tools=["cached_error_help"],
                    reason_codes=["needs_reference_grounding", "network_limited_mode"],
                    summary_for_server="",
                    local_action="show_cached_error_help",
                )
            return RouterDecision(
                intent="manual_procedure_question",
                risk_level="medium",
                route="local_rule_only",
                needs_human_review=False,
                patient_related=False,
                priority="high",
                required_tools=[],
                reason_codes=["needs_reference_grounding", "network_limited_mode"],
                summary_for_server="",
                local_action="show_limited_mode_notice",
            )
        return RouterDecision(
            intent="manual_procedure_question",
            risk_level="medium",
            route="server_rag",
            needs_human_review=False,
            patient_related=False,
            priority="high",
            required_tools=["manual_retrieval"],
            reason_codes=["needs_reference_grounding"],
            summary_for_server=" ".join(request.user_message.split())[:240],
            local_action="none",
        )

    if signals.general_question_candidate and signals.short_answer_expected:
        return RouterDecision(
            intent="general_question",
            risk_level="low",
            route="local_llm",
            needs_human_review=False,
            patient_related=False,
            priority="normal",
            required_tools=[],
            reason_codes=["local_general_answer_ok"],
            summary_for_server="",
            local_action="answer_with_local_llm",
        )

    if request.network_status == "online":
        return RouterDecision(
            intent="general_question",
            risk_level="low",
            route="server_llm",
            needs_human_review=False,
            patient_related=False,
            priority="normal",
            required_tools=["server_large_llm"],
            reason_codes=["needs_large_model_reasoning"],
            summary_for_server=" ".join(request.user_message.split())[:240],
            local_action="none",
        )

    return RouterDecision(
        intent="unknown",
        risk_level="medium",
        route="local_rule_only",
        needs_human_review=False,
        patient_related=False,
        priority="high",
        required_tools=[],
        reason_codes=["network_limited_mode", "unknown_request_type"],
        summary_for_server="",
        local_action="show_limited_mode_notice",
    )


def _decision_from_model_choice(
    request: NormalizedRouterInput,
    choice: ModelRouteChoice,
) -> RouterDecision:
    summary = choice.summary_for_server or " ".join(request.user_message.split())[:240]
    signals = request.detected_signals

    if choice.route == "local_llm":
        return RouterDecision(
            intent="general_question",
            risk_level="low",
            route="local_llm",
            needs_human_review=False,
            patient_related=False,
            priority="normal",
            required_tools=[],
            reason_codes=["local_general_answer_ok"],
            summary_for_server="",
            local_action="answer_with_local_llm",
        )

    if choice.route == "server_rag":
        return RouterDecision(
            intent="device_error_question" if signals.error_codes else "manual_procedure_question",
            risk_level="medium",
            route="server_rag",
            needs_human_review=False,
            patient_related=False,
            priority="high",
            required_tools=["manual_retrieval"],
            reason_codes=["needs_reference_grounding"],
            summary_for_server=summary,
            local_action="none",
        )

    if choice.route == "server_llm":
        return RouterDecision(
            intent="general_question",
            risk_level="low",
            route="server_llm",
            needs_human_review=False,
            patient_related=False,
            priority="normal",
            required_tools=["server_large_llm"],
            reason_codes=["needs_large_model_reasoning"],
            summary_for_server=summary,
            local_action="none",
        )

    if choice.route == "block":
        return RouterDecision(
            intent="contraindication_override_request",
            risk_level="forbidden",
            route="block",
            needs_human_review=True,
            patient_related=signals.patient_related,
            priority="critical",
            required_tools=[],
            reason_codes=["contraindication_override", "unsafe_override_request"],
            summary_for_server=summary,
            local_action="block_and_warn",
        )

    return RouterDecision(
        intent="clinical_risk_question" if signals.patient_related else "unknown",
        risk_level="high" if signals.patient_related else "medium",
        route="human_review",
        needs_human_review=True,
        patient_related=signals.patient_related,
        priority="critical" if signals.patient_related else "high",
        required_tools=[],
        reason_codes=["requires_operator_confirmation"],
        summary_for_server=summary,
        local_action="handoff_to_operator",
    )


def _build_local_execution_reroute_decision(
    request: NormalizedRouterInput,
    reason: str,
) -> RouterDecision:
    if request.network_status == "online":
        reason_codes = ["needs_large_model_reasoning"]
        if reason == "local_answer_overflow":
            reason_codes = ["local_answer_overflow", "needs_large_model_reasoning"]
        elif reason == "local_generation_failed":
            reason_codes = ["local_generation_failed", "needs_large_model_reasoning"]

        return RouterDecision(
            intent="general_question",
            risk_level="low",
            route="server_llm",
            needs_human_review=False,
            patient_related=False,
            priority="normal",
            required_tools=["server_large_llm"],
            reason_codes=reason_codes,
            summary_for_server=" ".join(request.user_message.split())[:240],
            local_action="none",
        )

    reason_codes = ["network_limited_mode"]
    if reason == "local_answer_overflow":
        reason_codes = ["local_answer_overflow", "network_limited_mode"]
    elif reason == "local_generation_failed":
        reason_codes = ["local_generation_failed", "network_limited_mode"]

    return RouterDecision(
        intent="unknown",
        risk_level="medium",
        route="local_rule_only",
        needs_human_review=False,
        patient_related=False,
        priority="high",
        required_tools=[],
        reason_codes=reason_codes,
        summary_for_server="",
        local_action="show_limited_mode_notice",
    )


def _build_display(
    decision_source: DecisionSource,
    decision: RouterDecision,
    handoff,
) -> RouterDisplay:
    brief_map = {
        "local_llm": "20자 이내 로컬 답변으로 처리",
        "server_rag": "문서 근거가 필요해 RAG로 전달",
        "server_llm": "설명형 일반 질문이라 서버 LLM으로 전달",
        "human_review": "자동 처리 대신 사람 검토가 필요함",
        "block": "안전 정책상 요청을 차단함",
        "local_rule_only": _local_rule_brief(decision.local_action),
    }
    return RouterDisplay(
        route=decision.route,
        decision_source=decision_source,
        brief=brief_map.get(decision.route, "라우팅 결과가 결정됨"),
        target_system=handoff.target_system,
        reason_codes=decision.reason_codes,
    )


def _build_local_execution_display(
    decision: RouterDecision,
    handoff: DownstreamHandoff,
    reason: str,
) -> RouterDisplay:
    if decision.route == "server_llm":
        if reason == "local_answer_overflow":
            brief = "로컬 답변이 20자를 넘어 서버 LLM으로 전달"
        else:
            brief = "로컬 답변 생성 실패로 서버 LLM으로 전달"
    else:
        brief = "로컬 답변이 어려워 제한 모드 안내로 처리"

    return RouterDisplay(
        route=decision.route,
        decision_source="local_execution",
        brief=brief,
        target_system=handoff.target_system,
        reason_codes=decision.reason_codes,
    )


def _to_compact_handoff(handoff: DownstreamHandoff) -> CompactHandoff:
    return CompactHandoff(
        route=handoff.route,
        target_system=handoff.target_system,
        task_type=handoff.task_type,
        summary=handoff.summary,
        required_inputs=handoff.required_inputs,
        metadata=handoff.metadata,
    )


def _local_rule_brief(local_action: str) -> str:
    if local_action == "respond_with_device_api":
        return "로컬 장비 API로 바로 처리"
    if local_action == "show_cached_error_help":
        return "오프라인 캐시 안내로 처리"
    if local_action == "show_limited_mode_notice":
        return "제한 모드 안내로 처리"
    if local_action == "handoff_to_operator":
        return "사람 검토로 넘김"
    if local_action == "block_and_warn":
        return "정책 경고 후 차단"
    return "로컬 규칙으로 처리"


def _log_router_decision(
    normalized_request: NormalizedRouterInput,
    result: RouterResult,
    branch: str,
    pre_policy_route: str,
    policy_override_count: int,
) -> None:
    reason_codes = ", ".join(result.decision.reason_codes) or "none"
    logger.info(
        "\n[라우팅 결과]\n"
        "  요청 ID     : %s\n"
        "  분기 소스   : %s\n"
        "  세부 분기   : %s\n"
        "  분기 전 경로: %s\n"
        "  최종 경로   : %s\n"
        "  대상 시스템 : %s\n"
        "  정책 보정   : %s회\n"
        "  사유 코드   : %s\n"
        "  한줄 설명   : %s\n"
        "  사용자 질문 : %s",
        normalized_request.request_id,
        _format_decision_source_label(result.decision_source),
        _format_branch_label(branch),
        pre_policy_route,
        result.decision.route,
        result.handoff.target_system if result.handoff is not None else "none",
        policy_override_count,
        reason_codes,
        result.display.brief,
        normalized_request.user_message[:120],
    )


def _log_local_execution(
    normalized_request: NormalizedRouterInput,
    execution: LocalExecutionResult,
) -> None:
    logger.info(
        "\n[로컬 답변 실행]\n"
        "  요청 ID     : %s\n"
        "  실행 상태   : %s\n"
        "  답변 글자수 : %s\n"
        "  생성 답변   : %s\n"
        "  재분기 경로 : %s\n"
        "  실행 사유   : %s",
        normalized_request.request_id,
        "완료" if execution.status == "completed" else "재분기",
        execution.answer_char_count if execution.answer_char_count is not None else "unknown",
        execution.answer or "-",
        execution.rerouted_to or "-",
        execution.reason,
    )


def _format_decision_source_label(decision_source: DecisionSource) -> str:
    labels = {
        "hard_rule": "하드 룰",
        "model": "모델 판단",
        "fallback": "폴백",
        "local_execution": "로컬 실행",
    }
    return labels.get(decision_source, decision_source)


def _format_branch_label(branch: str) -> str:
    if ":" not in branch:
        return branch

    source, detail = branch.split(":", 1)
    source_labels = {
        "hard_rule": "하드 룰",
        "model": "모델",
        "fallback": "폴백",
    }
    return f"{source_labels.get(source, source)} -> {detail}"


def _local_execution_fallback_route(request: NormalizedRouterInput) -> str:
    if request.network_status == "online":
        return "server_llm"
    return "local_rule_only"


def _sanitize_local_answer(raw_text: str) -> str:
    stripped = raw_text.strip()
    if not stripped:
        return ""

    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```").strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()

    parsed_answer = _extract_short_answer_from_json(stripped)
    if parsed_answer:
        return parsed_answer

    for line in stripped.splitlines():
        collapsed = " ".join(line.split()).strip()
        if not collapsed:
            continue

        cleaned = _strip_answer_prefix(collapsed).strip(" \"'`")
        if cleaned:
            return cleaned

    return ""


def _extract_short_answer_from_json(raw_text: str) -> str:
    try:
        parsed = _extract_json_object(raw_text)
    except Exception:
        return ""

    for key in ("short_answer", "answer", "reply", "reply_for_tts"):
        value = parsed.get(key)
        if isinstance(value, str):
            cleaned = " ".join(value.split()).strip(" \"'`")
            if cleaned:
                return cleaned

    return ""


def _strip_answer_prefix(text: str) -> str:
    return re.sub(r"^(short_answer|answer|답변)\s*:\s*", "", text, flags=re.IGNORECASE)
