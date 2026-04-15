from __future__ import annotations

from typing import Any, Protocol

import httpx

from .config import ServerRouterSettings


class RagClient(Protocol):
    async def ask(self, question: str) -> dict[str, Any]:
        """Execute the downstream RAG path and return the raw payload."""


class ServerAnswerClient(Protocol):
    async def answer(self, question: str, system_prompt: str) -> str:
        """Execute the downstream server LLM path and return answer text."""


class FinalScoreClient(Protocol):
    async def score(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a payload to the final-score service and return the raw payload."""


class LegacyRagHttpClient:
    def __init__(self, settings: ServerRouterSettings) -> None:
        self._settings = settings

    async def ask(self, question: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._settings.request_timeout) as client:
            response = await client.post(
                self._settings.rag_api_endpoint,
                json={"question": question},
            )
            response.raise_for_status()
        return response.json()


class ServerAnswerHttpClient:
    def __init__(self, settings: ServerRouterSettings) -> None:
        self._settings = settings

    async def answer(self, question: str, system_prompt: str) -> str:
        payload = {
            "model": self._settings.answer_model_name,
            "temperature": self._settings.answer_temperature,
            "max_tokens": self._settings.answer_max_tokens,
            "reasoning": self._settings.reasoning_mode,
            "reasoning_budget": self._settings.reasoning_budget,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
        }

        async with httpx.AsyncClient(timeout=self._settings.request_timeout) as client:
            response = await client.post(self._settings.answer_model_endpoint, json=payload)
            response.raise_for_status()

        data: dict[str, Any] = response.json()
        try:
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Unexpected server answer response shape") from exc


class FinalScoreHttpClient:
    def __init__(self, settings: ServerRouterSettings) -> None:
        self._settings = settings

    async def score(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._settings.request_timeout) as client:
            response = await client.post(self._settings.final_score_endpoint, json=payload)
            response.raise_for_status()
        return response.json()
