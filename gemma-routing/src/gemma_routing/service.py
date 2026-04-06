from __future__ import annotations

import json
from dataclasses import dataclass

from .client import GemmaChatClient, ModelClient
from .config import RouterSettings, load_project_env
from .handoff import build_handoff
from .hard_rules import apply_hard_rules
from .models import (
    DecisionSource,
    HarnessTraceEntry,
    NormalizedRouterInput,
    RouterDecision,
    RouterInput,
    RouterResult,
)
from .policies import apply_post_policies
from .prompts import (
    REPAIR_SYSTEM_PROMPT,
    build_repair_user_prompt,
    build_router_user_prompt,
    load_system_prompt,
)
from .signals import normalize_router_input


@dataclass
class RouterService:
    settings: RouterSettings
    model_client: ModelClient
    system_prompt: str

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
            return RouterResult(
                normalized_input=normalized_request,
                decision_source="hard_rule",
                decision=final_decision,
                handoff=handoff,
                trace=trace,
            )

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

        return RouterResult(
            normalized_input=normalized_request,
            decision_source=decision_source,
            decision=final_decision,
            handoff=handoff,
            trace=trace,
        )

    async def _get_model_decision(
        self,
        request: NormalizedRouterInput,
    ) -> tuple[RouterDecision, DecisionSource, list[HarnessTraceEntry]]:
        normalized_request = request
        trace: list[HarnessTraceEntry] = []
        user_prompt = build_router_user_prompt(normalized_request)
        raw_response = ""
        initial_error = ""

        try:
            raw_response = await self.model_client.complete(self.system_prompt, user_prompt)
            parsed = _extract_json_object(raw_response)
            decision = RouterDecision.model_validate(parsed)
            trace.append(
                HarnessTraceEntry(
                    stage="model",
                    status="generated",
                    detail="Model produced a valid router decision.",
                )
            )
            return decision, "model", trace
        except Exception as exc:
            initial_error = str(exc)
            trace.append(
                HarnessTraceEntry(
                    stage="model",
                    status="failed",
                    detail="Model output was invalid and entered repair flow.",
                    data={"error": initial_error},
                )
            )

        try:
            repair_prompt = build_repair_user_prompt(
                normalized_request,
                raw_response,
                initial_error or "Unknown model failure",
            )
            repaired_response = await self.model_client.complete(REPAIR_SYSTEM_PROMPT, repair_prompt)
            repaired_parsed = _extract_json_object(repaired_response)
            repaired_decision = RouterDecision.model_validate(repaired_parsed)
            trace.append(
                HarnessTraceEntry(
                    stage="repair",
                    status="repaired",
                    detail="Repair flow converted invalid model output into valid router JSON.",
                )
            )
            return repaired_decision, "model_repair", trace
        except Exception as repair_exc:
            trace.append(
                HarnessTraceEntry(
                    stage="repair",
                    status="failed",
                    detail="Repair flow failed and the request fell back to a conservative route.",
                    data={"error": str(repair_exc)},
                )
            )

        fallback = _fallback_decision(normalized_request)
        trace.append(
            HarnessTraceEntry(
                stage="fallback",
                status="applied",
                detail="Fallback forced the request to human review.",
            )
        )
        return fallback, "fallback", trace


def build_router_service(settings: RouterSettings | None = None) -> RouterService:
    load_project_env()
    resolved_settings = settings or RouterSettings()
    system_prompt = load_system_prompt(resolved_settings.prompt_path)
    model_client = GemmaChatClient(resolved_settings)
    return RouterService(
        settings=resolved_settings,
        model_client=model_client,
        system_prompt=system_prompt,
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
    patient_related = request.detected_signals.patient_related
    return RouterDecision(
        intent="unknown",
        risk_level="high" if patient_related else "medium",
        route="human_review",
        needs_human_review=True,
        patient_related=patient_related,
        priority="critical" if patient_related else "high",
        required_tools=[],
        reason_codes=["unknown_request_type"],
        summary_for_server=" ".join(request.user_message.split())[:240],
        local_action="handoff_to_operator",
    )
