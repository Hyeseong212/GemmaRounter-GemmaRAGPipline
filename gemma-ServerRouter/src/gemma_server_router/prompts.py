from __future__ import annotations

import json
from pathlib import Path

from .models import NormalizedServerRouterInput


def load_system_prompt(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8").strip()


def build_router_user_prompt(request: NormalizedServerRouterInput) -> str:
    payload = {
        "request_id": request.request_id,
        "user_message": request.user_message,
        "detected_signals": {
            "error_codes": request.detected_signals.error_codes,
            "asks_manual_or_sop": request.detected_signals.asks_manual_or_sop,
            "asks_error_meaning": request.detected_signals.asks_error_meaning,
            "asks_steps_or_procedure": request.detected_signals.asks_steps_or_procedure,
            "asks_specs_or_policy": request.detected_signals.asks_specs_or_policy,
            "organization_specific": request.detected_signals.organization_specific,
            "reference_grounding_likely": request.detected_signals.reference_grounding_likely,
            "open_ended_reasoning": request.detected_signals.open_ended_reasoning,
        },
        "route_rules": {
            "server_rag": "Use when the answer should be grounded in manuals, SOPs, error-code tables, specs, policies, or internal project references.",
            "server_llm": "Use when a strong general model can answer directly without document retrieval grounding.",
        },
        "task": "Return only the routing JSON for whether this request needs RAG grounding.",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
