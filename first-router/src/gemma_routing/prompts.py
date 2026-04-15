from __future__ import annotations

import json
from pathlib import Path

from .models import NormalizedRouterInput


def load_system_prompt(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8").strip()


def build_router_user_prompt(request: NormalizedRouterInput) -> str:
    payload = {
        "request_id": request.request_id,
        "user_message": request.user_message,
        "network_status": request.network_status,
        "detected_signals": {
            "error_codes": request.detected_signals.error_codes,
            "reference_grounding_required": request.detected_signals.reference_grounding_required,
            "short_answer_expected": request.detected_signals.short_answer_expected,
            "complex_reasoning_requested": request.detected_signals.complex_reasoning_requested,
            "general_question_candidate": request.detected_signals.general_question_candidate,
        },
        "route_rules": {
            "local_llm": "Use only when the final Korean answer is likely to stay within 20 characters.",
            "server_rag": "Use when manuals, SOPs, reference documents, or error-code grounding are needed.",
            "server_llm": "Use for general answers likely to exceed 20 characters or requiring explanation.",
            "human_review": "Use when the request is unsafe, ambiguous, or should not be auto-routed.",
            "block": "Use only for unsafe override or bypass intent.",
        },
        "task": "Return the smallest valid routing JSON for this unresolved request.",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_local_answer_user_prompt(
    request: NormalizedRouterInput,
    *,
    max_answer_chars: int,
) -> str:
    payload = {
        "request_id": request.request_id,
        "user_message": request.user_message,
        "answer_rules": {
            "language": "ko-KR",
            "max_answer_chars": max_answer_chars,
            "style": "short robot guidance or acknowledgement",
            "output": "Return only the final Korean answer text.",
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
