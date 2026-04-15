from __future__ import annotations

from .models import DownstreamHandoff, NormalizedRouterInput, RouterDecision


def build_handoff(
    request: NormalizedRouterInput,
    decision: RouterDecision,
) -> DownstreamHandoff:
    summary = decision.summary_for_server or request.user_message

    if decision.route == "local_llm":
        return DownstreamHandoff(
            route=decision.route,
            target_system="local_gemma_answerer",
            task_type="short_general_answer",
            summary=summary,
            instructions=[
                "Answer with the local on-device model only.",
                "Keep the final Korean answer within 20 characters.",
                "If the answer will exceed 20 characters, reroute to server_llm.",
            ],
            required_inputs=["user_message"],
            must_extract=["short_answer", "answer_char_count"],
            must_not_do=[
                "Do not invent manual or SOP facts.",
                "Do not provide diagnosis, treatment, or medication advice.",
            ],
            escalation_triggers=[
                "Answer exceeds 20 Korean characters",
                "Question actually needs grounded reference lookup",
            ],
            metadata={
                **_request_metadata(request),
                "max_answer_chars": 20,
                "overflow_route": "server_llm",
            },
        )

    if decision.route == "server_rag":
        retrieval_query = " ".join(request.detected_signals.error_codes + [summary]).strip()
        return DownstreamHandoff(
            route=decision.route,
            target_system="rag_reference_api",
            task_type="grounded_reference_lookup",
            summary=summary,
            instructions=[
                "Retrieve reference context before answering.",
                "Answer only from grounded retrieved material.",
            ],
            required_inputs=["user_message", "retrieved_context"],
            must_extract=["grounded_answer", "source_file_names", "source_page_labels"],
            must_not_do=[
                "Do not answer from memory alone.",
                "Do not provide diagnosis, treatment, or medication advice.",
            ],
            escalation_triggers=[
                "No supporting reference found",
                "Question becomes patient-specific",
            ],
            metadata={
                **_request_metadata(request),
                "retrieval_query": retrieval_query,
                "api_contract": {
                    "endpoint": "/ask",
                    "request_json": {"question": request.user_message},
                    "response_key": "answer",
                },
            },
        )

    if decision.route == "server_llm":
        return DownstreamHandoff(
            route=decision.route,
            target_system="server_large_llm",
            task_type="general_answer_generation",
            summary=summary,
            instructions=[
                "Answer the general question with the server-scale model.",
                "Keep the answer concise unless the user explicitly asks for detail.",
            ],
            required_inputs=["user_message"],
            must_extract=["final_answer"],
            must_not_do=[
                "Do not pretend the answer is retrieval-grounded when it is not.",
                "Do not provide diagnosis, treatment, or medication advice.",
            ],
            escalation_triggers=[
                "Question turns out to need reference grounding",
                "Question turns out to need human review",
            ],
            metadata=_request_metadata(request),
        )

    if decision.route == "human_review":
        return DownstreamHandoff(
            route=decision.route,
            target_system="operator_review_queue",
            task_type="operator_escalation",
            summary=summary,
            instructions=[
                "Show the original request, route, and reason codes to the operator.",
                "Require operator confirmation before answering.",
            ],
            required_inputs=["user_message", "decision", "reason_codes"],
            must_extract=["review_reason", "recommended_next_step"],
            must_not_do=["Do not auto-answer without operator review."],
            escalation_triggers=["Any patient-specific or visually ambiguous outcome"],
            metadata={
                **_request_metadata(request),
                "priority": decision.priority,
                "has_image": request.has_image,
            },
        )

    if decision.route == "block":
        return DownstreamHandoff(
            route=decision.route,
            target_system="policy_blocker",
            task_type="unsafe_request_refusal",
            summary=summary,
            instructions=[
                "Refuse the request with the approved warning copy.",
                "Log the unsafe request without continuing downstream.",
            ],
            required_inputs=["decision", "reason_codes"],
            must_extract=["warning_copy_variant"],
            must_not_do=["Do not call any downstream answer pipeline."],
            escalation_triggers=["Repeated override attempts"],
            metadata={
                **_request_metadata(request),
                "priority": decision.priority,
            },
        )

    return DownstreamHandoff(
        route=decision.route,
        target_system="local_device_stack",
        task_type=_local_task_type(decision.local_action),
        summary=summary,
        instructions=[
            "Resolve the request using deterministic local logic only.",
        ],
        required_inputs=decision.required_tools,
        must_extract=["local_execution_result"],
        must_not_do=["Do not call remote reasoning services from this path."],
        escalation_triggers=["Required local tool unavailable"],
        metadata={
            **_request_metadata(request),
            "local_action": decision.local_action,
        },
    )


def _local_task_type(local_action: str) -> str:
    if local_action == "respond_with_device_api":
        return "local_device_status"
    if local_action == "show_cached_error_help":
        return "cached_error_help"
    if local_action == "show_limited_mode_notice":
        return "limited_mode_notice"
    return "local_fallback"


def _request_metadata(request: NormalizedRouterInput) -> dict[str, str]:
    return {
        "request_id": request.request_id,
        "question": request.user_message,
        "original_question": request.user_message,
    }
