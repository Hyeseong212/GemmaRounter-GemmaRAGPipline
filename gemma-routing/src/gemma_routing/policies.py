from __future__ import annotations

from .models import HarnessTraceEntry, NormalizedRouterInput, RouterDecision


def apply_post_policies(
    request: NormalizedRouterInput,
    decision: RouterDecision,
) -> tuple[RouterDecision, list[HarnessTraceEntry]]:
    traces: list[HarnessTraceEntry] = []
    current = _stabilize_decision(request, decision)

    if current != decision:
        traces.append(
            HarnessTraceEntry(
                stage="post_policy",
                status="overridden",
                detail="Filled minimal downstream fields from the chosen route.",
            )
        )

    signals = request.detected_signals

    if signals.override_related and (signals.medication_related or signals.treatment_related):
        if current.route != "block":
            current = RouterDecision(
                intent="contraindication_override_request",
                risk_level="forbidden",
                route="block",
                needs_human_review=True,
                patient_related=signals.patient_related,
                priority="critical",
                required_tools=[],
                reason_codes=["contraindication_override", "unsafe_override_request"],
                summary_for_server=_summary(request, current.summary_for_server),
                local_action="block_and_warn",
            )
            traces.append(
                HarnessTraceEntry(
                    stage="post_policy",
                    status="overridden",
                    detail="Unsafe override language forced the request to block.",
                )
            )

    if (signals.patient_related or signals.medication_related or signals.treatment_related) and current.route not in {
        "human_review",
        "block",
    }:
        current = RouterDecision(
            intent="medication_advice_request" if signals.medication_related else "clinical_risk_question",
            risk_level="high",
            route="human_review",
            needs_human_review=True,
            patient_related=True,
            priority="critical",
            required_tools=[],
            reason_codes=_unique_reason_codes(
                current.reason_codes + ["patient_specific_clinical_judgment", "requires_operator_confirmation"]
            ),
            summary_for_server=_summary(request, current.summary_for_server),
            local_action="handoff_to_operator",
        )
        traces.append(
            HarnessTraceEntry(
                stage="post_policy",
                status="overridden",
                detail="Patient-specific content was escalated to human review.",
            )
        )

    if (request.has_image or signals.visual_related) and current.route not in {"human_review", "block"}:
        current = RouterDecision(
            intent="unknown",
            risk_level="medium",
            route="human_review",
            needs_human_review=True,
            patient_related=False,
            priority="high",
            required_tools=[],
            reason_codes=_unique_reason_codes(current.reason_codes + ["requires_operator_confirmation"]),
            summary_for_server=_summary(request, current.summary_for_server),
            local_action="handoff_to_operator",
        )
        traces.append(
            HarnessTraceEntry(
                stage="post_policy",
                status="overridden",
                detail="Visual requests were kept out of the simplified E2B routing path.",
            )
        )

    if current.route == "server_rag" and signals.network_limited:
        if signals.error_codes and "cached_error_help" in request.local_tools_available:
            current = RouterDecision(
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
            traces.append(
                HarnessTraceEntry(
                    stage="post_policy",
                    status="overridden",
                    detail="Offline RAG request was downgraded to cached local help.",
                )
            )
        else:
            current = RouterDecision(
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
            traces.append(
                HarnessTraceEntry(
                    stage="post_policy",
                    status="overridden",
                    detail="Offline RAG request was replaced with a limited-mode notice.",
                )
            )

    if current.route == "server_llm" and signals.network_limited:
        if signals.short_answer_expected:
            current = RouterDecision(
                intent="general_question",
                risk_level="low",
                route="local_llm",
                needs_human_review=False,
                patient_related=False,
                priority="normal",
                required_tools=[],
                reason_codes=["local_general_answer_ok", "network_limited_mode"],
                summary_for_server="",
                local_action="answer_with_local_llm",
            )
            traces.append(
                HarnessTraceEntry(
                    stage="post_policy",
                    status="overridden",
                    detail="Offline short general question was downgraded from server LLM to local LLM.",
                )
            )
        else:
            current = RouterDecision(
                intent="unknown",
                risk_level="medium",
                route="local_rule_only",
                needs_human_review=False,
                patient_related=False,
                priority="high",
                required_tools=[],
                reason_codes=_unique_reason_codes(current.reason_codes + ["network_limited_mode"]),
                summary_for_server="",
                local_action="show_limited_mode_notice",
            )
            traces.append(
                HarnessTraceEntry(
                    stage="post_policy",
                    status="overridden",
                    detail="Offline long general request was replaced with a limited-mode notice.",
                )
            )

    if current.route == "local_llm" and not signals.short_answer_expected:
        if request.network_status == "online":
            current = RouterDecision(
                intent="general_question",
                risk_level="low",
                route="server_llm",
                needs_human_review=False,
                patient_related=False,
                priority="normal",
                required_tools=["server_large_llm"],
                reason_codes=["needs_large_model_reasoning"],
                summary_for_server=_summary(request, current.summary_for_server),
                local_action="none",
            )
            traces.append(
                HarnessTraceEntry(
                    stage="post_policy",
                    status="overridden",
                    detail="Local LLM was upgraded to server LLM because the 20-character budget is unlikely.",
                )
            )
        else:
            current = RouterDecision(
                intent="unknown",
                risk_level="medium",
                route="local_rule_only",
                needs_human_review=False,
                patient_related=False,
                priority="high",
                required_tools=[],
                reason_codes=["needs_large_model_reasoning", "network_limited_mode"],
                summary_for_server="",
                local_action="show_limited_mode_notice",
            )
            traces.append(
                HarnessTraceEntry(
                    stage="post_policy",
                    status="overridden",
                    detail="Offline local LLM overflow was replaced with a limited-mode notice.",
                )
            )

    if current.route == "local_rule_only":
        missing_tools = [tool for tool in current.required_tools if tool not in request.local_tools_available]
        if missing_tools:
            current = RouterDecision(
                intent="unknown",
                risk_level="medium",
                route="human_review" if request.network_status == "online" else "local_rule_only",
                needs_human_review=request.network_status == "online",
                patient_related=False,
                priority="high",
                required_tools=[],
                reason_codes=["requires_operator_confirmation"]
                if request.network_status == "online"
                else ["network_limited_mode"],
                summary_for_server=_summary(request, current.summary_for_server)
                if request.network_status == "online"
                else "",
                local_action="handoff_to_operator"
                if request.network_status == "online"
                else "show_limited_mode_notice",
            )
            traces.append(
                HarnessTraceEntry(
                    stage="post_policy",
                    status="overridden",
                    detail="Missing local tool caused rerouting away from local-only execution.",
                    data={"missing_tools": missing_tools},
                )
            )

    return current, traces


def _stabilize_decision(request: NormalizedRouterInput, decision: RouterDecision) -> RouterDecision:
    summary = _summary(request, decision.summary_for_server)
    required_tools = list(decision.required_tools)
    local_action = decision.local_action

    if decision.route == "server_rag" and not required_tools:
        required_tools = ["manual_retrieval"]
    elif decision.route == "server_llm" and not required_tools:
        required_tools = ["server_large_llm"]

    if decision.route == "local_rule_only" and local_action == "none":
        if request.detected_signals.status_related:
            local_action = "respond_with_device_api"
        elif request.detected_signals.error_codes:
            local_action = "show_cached_error_help"
        else:
            local_action = "show_limited_mode_notice"
    elif decision.route == "local_llm" and local_action == "none":
        local_action = "answer_with_local_llm"
    elif decision.route == "human_review" and local_action == "none":
        local_action = "handoff_to_operator"
    elif decision.route == "block" and local_action == "none":
        local_action = "block_and_warn"

    return RouterDecision(
        intent=decision.intent,
        risk_level=decision.risk_level,
        route=decision.route,
        needs_human_review=decision.needs_human_review or decision.route in {"human_review", "block"},
        patient_related=decision.patient_related or request.detected_signals.patient_related,
        priority=decision.priority,
        required_tools=required_tools,
        reason_codes=decision.reason_codes,
        summary_for_server=summary if decision.route in {"server_rag", "server_llm", "human_review", "block"} else "",
        local_action=local_action,
    )


def _summary(request: NormalizedRouterInput, current_summary: str) -> str:
    summary = current_summary or request.user_message
    return " ".join(summary.split())[:240]


def _unique_reason_codes(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
