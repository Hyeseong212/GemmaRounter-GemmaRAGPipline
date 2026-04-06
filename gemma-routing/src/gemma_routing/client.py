from __future__ import annotations

from typing import Any, Protocol

import httpx

from .config import RouterSettings


class ModelClient(Protocol):
    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return the raw model response text."""


class GemmaChatClient:
    def __init__(self, settings: RouterSettings) -> None:
        self._settings = settings

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self._settings.model_name,
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_tokens,
            "reasoning": self._settings.reasoning_mode,
            "reasoning_budget": self._settings.reasoning_budget,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        async with httpx.AsyncClient(timeout=self._settings.request_timeout) as client:
            response = await client.post(self._settings.model_endpoint, json=payload)
            response.raise_for_status()

        data: dict[str, Any] = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Unexpected model response shape") from exc
