from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from uuid import uuid4

from .client import GemmaChatClient, ModelClient
from .config import ServerRouterSettings, load_project_env
from .models import (
    DecisionSource,
    DetectedSignals,
    DownstreamHandoff,
    FirstRouterRoute,
    HarnessTraceEntry,
    ModelRouteChoice,
    NormalizedServerRouterInput,
    ServerRouterDecision,
    ServerRouterDisplay,
    ServerRouterFromFirstRouterInput,
    ServerRouterInput,
    ServerRouterResult,
)
from .prompts import build_router_user_prompt, load_system_prompt


logger = logging.getLogger("uvicorn.error")

ERROR_CODE_PATTERN = re.compile(r"\b[Ee]\d{2,4}\b")
MANUAL_KEYWORDS = {
    "manual",
    "sop",
    "procedure",
    "guide",
    "document",
    "reference",
    "매뉴얼",
    "절차",
    "문서",
    "가이드",
    "설명서",
    "사용설명서",
    "레퍼런스",
}
ERROR_MEANING_KEYWORDS = {
    "error",
    "meaning",
    "뜻",
    "의미",
    "에러",
    "알람",
    "경고",
}
STEP_KEYWORDS = {
    "step",
    "steps",
    "procedure",
    "sequence",
    "how should",
    "조치",
    "순서",
    "절차",
    "단계",
    "어떻게",
}
SPEC_KEYWORDS = {
    "spec",
    "specs",
    "policy",
    "policies",
    "rule",
    "규격",
    "사양",
    "정책",
    "기준",
    "요건",
}
ORG_SPECIFIC_KEYWORDS = {
    "우리 프로젝트",
    "우리 장비",
    "이 장비",
    "이 제품",
    "내부 문서",
    "사내",
    "프로젝트 문서",
}
OPEN_REASONING_KEYWORDS = {
    "compare",
    "comparison",
    "difference",
    "tradeoff",
    "pros and cons",
    "why",
    "brainstorm",
    "analyze",
    "비교",
    "차이",
    "장단점",
    "왜",
    "분석",
    "정리",
    "설명",
}


@dataclass
class ServerRouterService:
    settings: ServerRouterSettings
    model_client: ModelClient
    system_prompt: str

    async def route_from_first_router(
        self,
        request: ServerRouterFromFirstRouterInput,
    ) -> ServerRouterResult:
        adapted_request = adapt_first_router_input(request)
        return await self.route(adapted_request)

    async def route(self, request: ServerRouterInput) -> ServerRouterResult:
        normalized_request = normalize_server_router_input(request)
        trace = [
            HarnessTraceEntry(
                stage="normalize",
                status="passed",
                detail="Input was normalized and server-side routing signals were extracted.",
                data=normalized_request.detected_signals.model_dump(),
            )
        ]

        decision, decision_source, model_traces = await self._get_decision(normalized_request)
        trace.extend(model_traces)

        handoff = build_handoff(normalized_request, decision)
        trace.append(
            HarnessTraceEntry(
                stage="handoff",
                status="generated",
                detail="Generated downstream handoff for the selected server route.",
                data={"target_system": handoff.target_system, "task_type": handoff.task_type},
            )
        )

        result = ServerRouterResult(
            display=_build_display(decision),
            decision_source=decision_source,
            decision=decision,
            handoff=handoff,
            normalized_input=normalized_request,
            trace=trace,
        )
        _log_server_router_decision(normalized_request, result)
        return result

    async def _get_decision(
        self,
        request: NormalizedServerRouterInput,
    ) -> tuple[ServerRouterDecision, DecisionSource, list[HarnessTraceEntry]]:
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
                    detail="Model produced a server routing decision.",
                    data={
                        "route": choice.route,
                        "confidence": choice.confidence,
                    },
                )
            )
            return decision, "model", trace
        except Exception as exc:
            trace.append(
                HarnessTraceEntry(
                    stage="model",
                    status="failed",
                    detail="Model output was invalid and the server router fell back to deterministic routing.",
                    data={"error": str(exc)},
                )
            )

        fallback = _fallback_decision(request)
        trace.append(
            HarnessTraceEntry(
                stage="fallback",
                status="applied",
                detail="Fallback applied a deterministic RAG-vs-LLM route.",
                data={"route": fallback.route},
            )
        )
        return fallback, "fallback", trace


def build_server_router_service(
    settings: ServerRouterSettings | None = None,
) -> ServerRouterService:
    load_project_env()
    resolved_settings = settings or ServerRouterSettings()
    system_prompt = load_system_prompt(resolved_settings.prompt_path)
    model_client = GemmaChatClient(resolved_settings)
    return ServerRouterService(
        settings=resolved_settings,
        model_client=model_client,
        system_prompt=system_prompt,
    )


def normalize_server_router_input(request: ServerRouterInput) -> NormalizedServerRouterInput:
    resolved_request_id = (
        request.request_id
        or str(request.metadata.get("request_id", "")).strip()
        or uuid4().hex[:12]
    )
    return NormalizedServerRouterInput(
        request_id=resolved_request_id,
        user_message=request.user_message,
        metadata=request.metadata,
        detected_signals=extract_signals(request.user_message),
    )


def adapt_first_router_input(request: ServerRouterFromFirstRouterInput) -> ServerRouterInput:
    _validate_first_router_route(request.first_router.handoff.route)
    if request.first_router.display.route != request.first_router.handoff.route:
        raise ValueError("first_router.display.route must match first_router.handoff.route")

    resolved_question = (
        request.original_question
        or _metadata_text(request.first_router.handoff.metadata, "original_question")
        or _metadata_text(request.first_router.handoff.metadata, "question")
    )
    if not resolved_question:
        raise ValueError(
            "original_question must be provided explicitly or in first_router.handoff.metadata"
        )

    metadata = dict(request.metadata)
    metadata.setdefault("source", "first_router")
    metadata["original_question"] = resolved_question
    metadata["first_router_display"] = request.first_router.display.model_dump()
    metadata["first_router_handoff"] = request.first_router.handoff.model_dump()
    metadata.setdefault("upstream_route", request.first_router.display.route)
    metadata.setdefault("upstream_target_system", request.first_router.handoff.target_system)
    metadata.setdefault("upstream_task_type", request.first_router.handoff.task_type)
    metadata.setdefault("upstream_summary", request.first_router.handoff.summary)

    return ServerRouterInput(
        request_id=request.request_id,
        user_message=resolved_question,
        metadata=metadata,
    )


def extract_signals(message: str) -> DetectedSignals:
    text = message.casefold()
    error_codes = [match.group(0).upper() for match in ERROR_CODE_PATTERN.finditer(message)]

    asks_manual_or_sop = _contains_any(text, MANUAL_KEYWORDS)
    asks_error_meaning = bool(error_codes) or _contains_any(text, ERROR_MEANING_KEYWORDS)
    asks_steps_or_procedure = _contains_any(text, STEP_KEYWORDS)
    asks_specs_or_policy = _contains_any(text, SPEC_KEYWORDS)
    organization_specific = _contains_any(text, ORG_SPECIFIC_KEYWORDS)
    open_ended_reasoning = _contains_any(text, OPEN_REASONING_KEYWORDS) or len(message) >= 120
    reference_grounding_likely = any(
        [
            bool(error_codes),
            asks_manual_or_sop,
            asks_steps_or_procedure,
            asks_specs_or_policy,
            organization_specific and not open_ended_reasoning,
        ]
    )

    return DetectedSignals(
        error_codes=error_codes,
        asks_manual_or_sop=asks_manual_or_sop,
        asks_error_meaning=asks_error_meaning,
        asks_steps_or_procedure=asks_steps_or_procedure,
        asks_specs_or_policy=asks_specs_or_policy,
        organization_specific=organization_specific,
        reference_grounding_likely=reference_grounding_likely,
        open_ended_reasoning=open_ended_reasoning,
    )


def build_handoff(
    request: NormalizedServerRouterInput,
    decision: ServerRouterDecision,
) -> DownstreamHandoff:
    summary = decision.summary_for_handoff or request.user_message
    if decision.route == "server_rag":
        retrieval_query = decision.retrieval_query or " ".join(
            request.detected_signals.error_codes + [summary]
        ).strip()
        return DownstreamHandoff(
            route="server_rag",
            target_system="rag_reference_api",
            task_type="grounded_reference_lookup",
            summary=summary,
            required_inputs=["user_message", "retrieved_context"],
            metadata={
                "needs_rag": True,
                "retrieval_query": retrieval_query,
                "question": request.user_message,
            },
        )

    return DownstreamHandoff(
        route="server_llm",
        target_system="server_large_llm",
        task_type="general_answer_generation",
        summary=summary,
        required_inputs=["user_message"],
        metadata={
            "needs_rag": False,
            "question": request.user_message,
        },
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


def _decision_from_model_choice(
    request: NormalizedServerRouterInput,
    choice: ModelRouteChoice,
) -> ServerRouterDecision:
    summary = choice.summary_for_handoff or " ".join(request.user_message.split())[:240]
    retrieval_query = choice.retrieval_query

    if choice.route == "server_rag":
        reason_codes = _rag_reason_codes(request.detected_signals)
        return ServerRouterDecision(
            route="server_rag",
            needs_rag=True,
            confidence=choice.confidence,
            reason_codes=reason_codes,
            summary_for_handoff=summary,
            retrieval_query=retrieval_query or summary,
        )

    return ServerRouterDecision(
        route="server_llm",
        needs_rag=False,
        confidence=choice.confidence,
        reason_codes=["general_reasoning_ok"],
        summary_for_handoff=summary,
        retrieval_query="",
    )


def _fallback_decision(request: NormalizedServerRouterInput) -> ServerRouterDecision:
    if request.detected_signals.reference_grounding_likely:
        summary = " ".join(request.user_message.split())[:240]
        retrieval_query = " ".join(request.detected_signals.error_codes + [summary]).strip()
        return ServerRouterDecision(
            route="server_rag",
            needs_rag=True,
            confidence="medium",
            reason_codes=_rag_reason_codes(request.detected_signals) + ["fallback_reference_bias"],
            summary_for_handoff=summary,
            retrieval_query=retrieval_query or summary,
        )

    return ServerRouterDecision(
        route="server_llm",
        needs_rag=False,
        confidence="medium",
        reason_codes=["general_reasoning_ok", "fallback_general_reasoning"],
        summary_for_handoff=" ".join(request.user_message.split())[:240],
        retrieval_query="",
    )


def _rag_reason_codes(signals: DetectedSignals) -> list[str]:
    reasons: list[ReasonCode] = []
    if signals.error_codes or signals.asks_error_meaning:
        reasons.append("error_code_reference")
    if signals.asks_manual_or_sop or signals.asks_steps_or_procedure:
        reasons.append("manual_or_sop_reference")
    if signals.asks_specs_or_policy:
        reasons.append("spec_or_policy_reference")
    if signals.organization_specific:
        reasons.append("organization_specific_reference")
    return reasons or ["manual_or_sop_reference"]


def _build_display(decision: ServerRouterDecision) -> ServerRouterDisplay:
    brief = (
        "문서 근거가 필요해 RAG로 전달"
        if decision.route == "server_rag"
        else "일반 서버 LLM 답변으로 처리"
    )
    return ServerRouterDisplay(
        route=decision.route,
        needs_rag=decision.needs_rag,
        confidence=decision.confidence,
        brief=brief,
        reason_codes=decision.reason_codes,
    )


def _log_server_router_decision(
    normalized_request: NormalizedServerRouterInput,
    result: ServerRouterResult,
) -> None:
    reason_codes = ", ".join(result.decision.reason_codes) or "none"
    logger.info(
        "\n[서버 라우팅 결과]\n"
        "  요청 ID     : %s\n"
        "  분기 소스   : %s\n"
        "  최종 경로   : %s\n"
        "  RAG 필요    : %s\n"
        "  신뢰도      : %s\n"
        "  대상 시스템 : %s\n"
        "  사유 코드   : %s\n"
        "  한줄 설명   : %s\n"
        "  사용자 질문 : %s",
        normalized_request.request_id,
        "모델 판단" if result.decision_source == "model" else "폴백",
        result.decision.route,
        "yes" if result.decision.needs_rag else "no",
        result.decision.confidence,
        result.handoff.target_system,
        reason_codes,
        result.display.brief,
        normalized_request.user_message[:160],
    )


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _metadata_text(metadata: dict[str, object], key: str) -> str:
    value = metadata.get(key)
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _validate_first_router_route(route: FirstRouterRoute) -> None:
    if route not in {"server_rag", "server_llm"}:
        raise ValueError("Only server-bound first-router routes can be forwarded to server routing")
