from __future__ import annotations

import json
from pathlib import Path

from .models import NormalizedRouterInput


REPAIR_SYSTEM_PROMPT = """You repair invalid medical-device router outputs.

Rules:
- Output JSON only.
- Keep the exact router schema.
- Use only the allowed enum values.
- Be conservative and prefer human_review or block over guessing.
- Do not answer the user's question.
"""


def load_system_prompt(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8").strip()


def build_router_user_prompt(request: NormalizedRouterInput) -> str:
    payload = {
        "request_id": request.request_id,
        "user_message": request.user_message,
        "has_image": request.has_image,
        "network_status": request.network_status,
        "local_tools_available": request.local_tools_available,
        "metadata": request.metadata,
        "detected_signals": request.detected_signals.model_dump(),
        "task_boundary": {
            "role": "routing_only",
            "do_not_answer_user": True,
            "return_json_only": True,
        },
        "local_llm_policy": {
            "max_answer_chars": 20,
            "rule": "Use local_llm only when the expected final answer can stay within 20 Korean characters.",
            "overflow_route": "server_llm",
        },
        "instructions": (
            "First decide whether the request is deterministic local, general question, "
            "reference-grounded question, server-scale general reasoning, visual question, "
            "unsafe human-review question, or block-worthy. Treat local_llm as a short-answer path only. "
            "If the reply is likely to exceed 20 Korean characters, prefer server_llm. "
            "Then return only the allowed router JSON shape."
        ),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_repair_user_prompt(
    request: NormalizedRouterInput,
    raw_response: str,
    error_message: str,
) -> str:
    payload = {
        "request_id": request.request_id,
        "user_message": request.user_message,
        "detected_signals": request.detected_signals.model_dump(),
        "invalid_model_output": raw_response,
        "validation_error": error_message,
        "instructions": "Repair the invalid output into the exact allowed router JSON shape.",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
