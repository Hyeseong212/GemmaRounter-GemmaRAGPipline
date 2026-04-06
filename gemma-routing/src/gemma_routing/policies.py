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
                detail="Filled missing decision fields for safer downstream execution.",
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
                    detail="Override-like request touching treatment or medication was forced to block.",
                )
            )

    if (
        signals.patient_related
        or signals.medication_related
        or signals.treatment_related
    ) and current.route not in {"human_review", "block"}:
        current = RouterDecision(
            intent="clinical_risk_question"
            if not signals.medication_related
            else "medication_advice_request",
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
                detail="Patient-specific or clinical-risk content was escalated to human review.",
            )
        )

    if signals.network_limited and current.route in {"server_rag", "server_vision", "server_llm"}:
        if current.route == "server_llm" and signals.short_answer_expected:
            current = RouterDecision(
                intent="general_reasoning_question" if signals.complex_reasoning_requested else "general_question",
                risk_level="low",
                route="local_llm",
                needs_human_review=False,
                patient_related=False,
                priority="normal",
                required_tools=[],
                reason_codes=_unique_reason_codes(current.reason_codes + ["local_general_answer_ok", "network_limited_mode"]),
                summary_for_server="",
                local_action="answer_with_local_llm",
            )
            traces.append(
                HarnessTraceEntry(
                    stage="post_policy",
                    status="overridden",
                    detail="Network-limited short general request was downgraded from server LLM to local LLM.",
                )
            )
        elif signals.error_codes and "cached_error_help" in request.local_tools_available:
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
                    detail="Network-limited request was downgraded to cached error guidance.",
                )
            )
        else:
            current = RouterDecision(
                intent=current.intent,
                risk_level="medium" if current.risk_level == "low" else current.risk_level,
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
                detail="Network-limited request was kept on device and marked limited mode.",
                )
            )

    if current.route == "local_llm" and not signals.short_answer_expected:
        if request.network_status == "online":
            current = RouterDecision(
                intent="general_reasoning_question" if signals.complex_reasoning_requested else "general_question",
                risk_level="low",
                route="server_llm",
                needs_human_review=False,
                patient_related=False,
                priority="normal",
                required_tools=["server_large_llm"],
                reason_codes=_unique_reason_codes(current.reason_codes + ["needs_large_model_reasoning"]),
                summary_for_server=_summary(request, current.summary_for_server),
                local_action="none",
            )
            traces.append(
                HarnessTraceEntry(
                    stage="post_policy",
                    status="overridden",
                    detail="Local LLM route was upgraded to server LLM because the reply is unlikely to fit within 20 characters.",
                )
            )
        else:
            current = RouterDecision(
                intent=current.intent,
                risk_level="medium" if current.risk_level == "low" else current.risk_level,
                route="local_rule_only",
                needs_human_review=False,
                patient_related=False,
                priority="high",
                required_tools=[],
                reason_codes=_unique_reason_codes(current.reason_codes + ["needs_large_model_reasoning", "network_limited_mode"]),
                summary_for_server="",
                local_action="show_limited_mode_notice",
            )
            traces.append(
                HarnessTraceEntry(
                    stage="post_policy",
                    status="overridden",
                    detail="Local LLM route was replaced with limited-mode notice because the expected reply exceeds the 20-character local budget while offline.",
                )
            )

    if current.route == "server_vision" and not request.has_image:
        current = RouterDecision(
            intent=current.intent,
            risk_level="medium" if current.risk_level == "low" else current.risk_level,
            route="human_review",
            needs_human_review=True,
            patient_related=current.patient_related,
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
                detail="Vision route without an attached image was escalated for operator follow-up.",
            )
        )

    if current.route == "local_rule_only":
        missing_tools = [
            tool for tool in current.required_tools if tool not in request.local_tools_available
        ]
        if missing_tools:
            current = _reroute_for_missing_local_tools(request, current, missing_tools)
            traces.append(
                HarnessTraceEntry(
                    stage="post_policy",
                    status="overridden",
                    detail="Missing local tools caused rerouting away from local-only execution.",
                    data={"missing_tools": missing_tools},
                )
            )

    return current, traces


def _stabilize_decision(request: NormalizedRouterInput, decision: RouterDecision) -> RouterDecision:
    summary = _summary(request, decision.summary_for_server)
    required_tools = list(decision.required_tools)

    if decision.route == "server_rag" and not required_tools:
        required_tools = ["manual_retrieval"]
    elif decision.route == "server_llm" and not required_tools:
        required_tools = ["server_large_llm"]
    elif decision.route == "server_vision" and not required_tools:
        required_tools = ["vision_analysis"]

    local_action = decision.local_action
    if decision.route == "local_rule_only" and local_action == "none":
        if request.detected_signals.status_related:
            local_action = "respond_with_device_api"
        elif request.detected_signals.error_codes:
            local_action = "show_cached_error_help"
        else:
            local_action = "show_limited_mode_notice"
    elif decision.route == "local_llm" and local_action == "none":
        local_action = "answer_with_local_llm"

    return RouterDecision(
        intent=decision.intent,
        risk_level=decision.risk_level,
        route=decision.route,
        needs_human_review=decision.needs_human_review,
        patient_related=decision.patient_related or request.detected_signals.patient_related,
        priority=decision.priority,
        required_tools=required_tools,
        reason_codes=decision.reason_codes,
        summary_for_server=summary,
        local_action=local_action,
    )


def _reroute_for_missing_local_tools(
    request: NormalizedRouterInput,
    decision: RouterDecision,
    missing_tools: list[str],
) -> RouterDecision:
    signals = request.detected_signals

    if request.network_status == "online":
        if signals.visual_related and request.has_image:
            return RouterDecision(
                intent="ui_screen_question",
                risk_level="medium",
                route="server_vision",
                needs_human_review=False,
                patient_related=False,
                priority="high",
                required_tools=["vision_analysis"],
                reason_codes=["needs_visual_inspection"],
                summary_for_server=_summary(request, decision.summary_for_server),
                local_action="none",
            )
        if signals.reference_grounding_required or signals.error_codes:
            return RouterDecision(
                intent="device_error_question" if signals.error_codes else decision.intent,
                risk_level="medium",
                route="server_rag",
                needs_human_review=False,
                patient_related=False,
                priority="high",
                required_tools=["manual_retrieval"],
                reason_codes=_unique_reason_codes(decision.reason_codes + ["needs_reference_grounding"]),
                summary_for_server=_summary(request, decision.summary_for_server),
                local_action="none",
            )

        if signals.general_question_candidate:
            return RouterDecision(
                intent="general_reasoning_question" if signals.complex_reasoning_requested else "general_question",
                risk_level="low",
                route="local_llm" if signals.short_answer_expected and not signals.complex_reasoning_requested else "server_llm",
                needs_human_review=False,
                patient_related=False,
                priority="normal",
                required_tools=[] if signals.short_answer_expected and not signals.complex_reasoning_requested else ["server_large_llm"],
                reason_codes=["local_general_answer_ok"] if signals.short_answer_expected and not signals.complex_reasoning_requested else ["needs_large_model_reasoning"],
                summary_for_server=_summary(request, decision.summary_for_server),
                local_action="answer_with_local_llm" if signals.short_answer_expected and not signals.complex_reasoning_requested else "none",
            )

    return RouterDecision(
        intent=decision.intent,
        risk_level="medium" if decision.risk_level == "low" else decision.risk_level,
        route="human_review",
        needs_human_review=True,
        patient_related=decision.patient_related,
        priority="high",
        required_tools=[],
        reason_codes=_unique_reason_codes(decision.reason_codes + ["requires_operator_confirmation"]),
        summary_for_server=_summary(request, decision.summary_for_server),
        local_action="handoff_to_operator",
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
