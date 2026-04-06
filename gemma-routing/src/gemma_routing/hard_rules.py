from __future__ import annotations

from dataclasses import dataclass

from .models import NormalizedRouterInput, RouterDecision


@dataclass(frozen=True)
class HardRuleMatch:
    rule_name: str
    detail: str
    decision: RouterDecision


def apply_hard_rules(request: NormalizedRouterInput) -> HardRuleMatch | None:
    signals = request.detected_signals

    if signals.medication_related:
        if signals.override_related:
            return HardRuleMatch(
                rule_name="block_contraindication_override",
                detail="Medication override phrasing was blocked before model execution.",
                decision=RouterDecision(
                intent="contraindication_override_request",
                risk_level="forbidden",
                route="block",
                needs_human_review=True,
                patient_related=signals.patient_related,
                priority="critical",
                required_tools=[],
                reason_codes=["contraindication_override", "unsafe_override_request"],
                summary_for_server=_summarize(request.user_message),
                local_action="block_and_warn",
                ),
            )
        return HardRuleMatch(
            rule_name="escalate_medication_question",
            detail="Medication-related request was escalated before model execution.",
            decision=RouterDecision(
                intent="medication_advice_request",
                risk_level="high",
                route="human_review",
                needs_human_review=True,
                patient_related=True,
                priority="critical",
                required_tools=[],
                reason_codes=["medication_or_treatment_change", "requires_operator_confirmation"],
                summary_for_server=_summarize(request.user_message),
                local_action="handoff_to_operator",
            ),
        )

    if signals.treatment_related or signals.patient_related:
        return HardRuleMatch(
            rule_name="escalate_clinical_risk",
            detail="Patient-specific or treatment-related request was escalated before model execution.",
            decision=RouterDecision(
            intent="clinical_risk_question",
            risk_level="high",
            route="human_review",
            needs_human_review=True,
            patient_related=True,
            priority="critical",
            required_tools=[],
            reason_codes=["patient_specific_clinical_judgment", "requires_operator_confirmation"],
            summary_for_server=_summarize(request.user_message),
            local_action="handoff_to_operator",
            ),
        )

    if signals.status_related and "device_status_api" in request.local_tools_available:
        return HardRuleMatch(
            rule_name="use_local_device_status",
            detail="Deterministic status question was answered through the local device API path.",
            decision=RouterDecision(
            intent="device_status_question",
            risk_level="low",
            route="local_rule_only",
            needs_human_review=False,
            patient_related=False,
            priority="normal",
            required_tools=["device_status_api"],
            reason_codes=["local_status_available"],
            summary_for_server="",
            local_action="respond_with_device_api",
            ),
        )

    if signals.network_limited:
        if signals.reference_grounding_required and signals.error_codes and "cached_error_help" in request.local_tools_available:
            return HardRuleMatch(
                rule_name="offline_cached_error_help",
                detail="Network-limited error-code request was downgraded to cached local guidance.",
                decision=RouterDecision(
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
                ),
            )

        if signals.general_question_candidate and signals.short_answer_expected:
            return HardRuleMatch(
                rule_name="offline_general_question_to_local_llm",
                detail="Network-limited short general question was routed to the local LLM path.",
                decision=RouterDecision(
                    intent="general_reasoning_question" if signals.complex_reasoning_requested else "general_question",
                    risk_level="low",
                    route="local_llm",
                    needs_human_review=False,
                    patient_related=False,
                    priority="normal",
                    required_tools=[],
                    reason_codes=["local_general_answer_ok", "network_limited_mode"],
                    summary_for_server="",
                    local_action="answer_with_local_llm",
                ),
            )

        return HardRuleMatch(
            rule_name="offline_limited_mode_notice",
            detail="Network-limited long, grounded, or unsupported request stayed on device in limited mode.",
            decision=RouterDecision(
            intent="unknown",
            risk_level="medium",
            route="local_rule_only",
            needs_human_review=False,
            patient_related=False,
            priority="high",
            required_tools=[],
            reason_codes=["network_limited_mode"],
            summary_for_server="",
            local_action="show_limited_mode_notice",
            ),
        )

    if request.has_image and signals.visual_related:
        return HardRuleMatch(
            rule_name="route_attached_image_to_vision",
            detail="Attached image was routed to the vision specialist path before model execution.",
            decision=RouterDecision(
            intent="ui_screen_question",
            risk_level="medium",
            route="server_vision",
            needs_human_review=False,
            patient_related=False,
            priority="high",
            required_tools=["vision_analysis"],
            reason_codes=["needs_visual_inspection"],
            summary_for_server=_summarize(request.user_message),
            local_action="none",
            ),
        )

    return None


def _summarize(message: str) -> str:
    return " ".join(message.split())[:240]
