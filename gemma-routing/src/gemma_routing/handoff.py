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
                "Answer using the local on-device LLM only.",
                "Keep the answer within 20 Korean characters.",
                "If the answer is likely to exceed 20 Korean characters, do not answer locally and reroute to server_llm.",
                "Do not claim document-grounded facts you did not retrieve.",
            ],
            required_inputs=["user_message"],
            must_extract=["short_answer", "answer_char_count"],
            must_not_do=[
                "Do not invent grounded manual or SOP citations.",
                "Do not provide diagnosis, treatment, or medication advice.",
            ],
            escalation_triggers=[
                "Question actually requires grounded reference lookup",
                "Question requires long-form or complex server-scale reasoning",
                "Draft answer exceeds 20 Korean characters",
            ],
            metadata={
                "answer_style": "short",
                "max_answer_chars": 20,
                "overflow_route": "server_llm",
                "question": request.user_message,
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
                "Retrieve manual, SOP, and reference evidence before answering.",
                "Answer only from cited retrieved chunks.",
                "Refuse or escalate if the context is insufficient.",
            ],
            required_inputs=["user_message", "retrieved_context"],
            must_extract=["grounded_answer", "source_file_names", "source_page_labels"],
            must_not_do=[
                "Do not answer from parametric memory alone.",
                "Do not provide diagnosis, treatment, or medication advice.",
            ],
            escalation_triggers=[
                "No supporting reference chunks found",
                "Question requires patient-specific clinical judgment",
            ],
            metadata={
                "retrieval_query": retrieval_query,
                "preferred_corpora": ["ifu", "sop", "service_manual", "reference_docs"],
                "question": request.user_message,
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
                "Use richer reasoning than the local LLM path when needed.",
                "Keep the answer concise unless the user explicitly asks for depth.",
            ],
            required_inputs=["user_message"],
            must_extract=["final_answer"],
            must_not_do=[
                "Do not pretend the answer is grounded in retrieval if no RAG context was provided.",
                "Do not provide diagnosis, treatment, or medication advice.",
            ],
            escalation_triggers=[
                "Question turns out to require document grounding",
                "Question turns out to require patient-specific clinical judgment",
            ],
            metadata={
                "question": request.user_message,
                "answer_style": "concise_default",
                "trigger_reason": "expected_reply_over_20_chars_or_complex_general_reasoning",
            },
        )

    if decision.route == "server_vision":
        return DownstreamHandoff(
            route=decision.route,
            target_system="intervl_78b",
            task_type="ui_screen_triage",
            summary=summary,
            instructions=[
                "Extract only visible facts from the attached image or screenshot.",
                "If text is unreadable or cropped, say so and escalate.",
                "Return structured extraction for the next stage instead of a final answer.",
            ],
            required_inputs=["attached_image", "user_message"],
            must_extract=[
                "visible_error_codes",
                "screen_title_or_mode",
                "visible_alarm_or_warning_indicators",
                "notable_device_state",
            ],
            must_not_do=[
                "Do not give diagnosis or treatment advice.",
                "Do not invent unseen text or UI elements.",
                "Do not decide patient safety from the image alone.",
            ],
            escalation_triggers=[
                "No image attached",
                "Image unreadable or partially cropped",
                "Requested answer requires clinical judgment",
            ],
            metadata={
                "vision_model": "InterVL-78B",
                "question": request.user_message,
                "follow_up_path": "server_rag_after_visual_extraction",
            },
        )

    if decision.route == "human_review":
        return DownstreamHandoff(
            route=decision.route,
            target_system="operator_review_queue",
            task_type="operator_escalation",
            summary=summary,
            instructions=[
                "Surface the original request, reason codes, and risk level to the operator.",
                "Require human confirmation before any answer reaches the user.",
            ],
            required_inputs=["user_message", "decision", "reason_codes"],
            must_extract=["review_reason", "recommended_next_step"],
            must_not_do=["Do not auto-answer without operator review."],
            escalation_triggers=["Any patient-specific or treatment-changing outcome"],
            metadata={"priority": decision.priority},
        )

    if decision.route == "block":
        return DownstreamHandoff(
            route=decision.route,
            target_system="policy_blocker",
            task_type="unsafe_request_refusal",
            summary=summary,
            instructions=[
                "Refuse the request and show the approved warning copy.",
                "Log the unsafe request for audit without continuing downstream.",
            ],
            required_inputs=["decision", "reason_codes"],
            must_extract=["warning_copy_variant"],
            must_not_do=["Do not call any downstream answer pipeline."],
            escalation_triggers=["Repeated override attempts"],
            metadata={"priority": decision.priority},
        )

    return DownstreamHandoff(
        route=decision.route,
        target_system="local_device_stack",
        task_type=_local_task_type(decision.local_action),
        summary=summary,
        instructions=[
            "Resolve the request using deterministic local logic only.",
            "Do not synthesize unsupported clinical or procedural guidance.",
        ],
        required_inputs=decision.required_tools,
        must_extract=["local_execution_result"],
        must_not_do=["Do not call remote reasoning services from this path."],
        escalation_triggers=["Required local tool unavailable"],
        metadata={"local_action": decision.local_action},
    )


def _local_task_type(local_action: str) -> str:
    if local_action == "respond_with_device_api":
        return "local_device_status"
    if local_action == "show_cached_error_help":
        return "cached_error_help"
    if local_action == "show_limited_mode_notice":
        return "limited_mode_notice"
    return "local_fallback"
