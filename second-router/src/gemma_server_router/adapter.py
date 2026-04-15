from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .config import ServerRouterSettings
from .downstream import FinalScoreClient, RagClient, ServerAnswerClient
from .models import (
    FinalScoreSnapshot,
    ProcessExecutionResult,
    ServerProcessResult,
    ServerRouterDisplay,
    ServerRouterFromFirstRouterInput,
    ServerRouterInput,
    ServerRouterResult,
)
from .prompts import load_system_prompt
from .service import ServerRouterService


WARNING_MARKERS = ("금지", "중지", "주의", "경고", "stop", "warning")
HUMAN_REVIEW_MARKERS = (
    "사람 검토",
    "의사와 상의",
    "전문가와 상의",
    "담당자에게 문의",
    "추가 확인 필요",
    "환자별 판단",
)
INSUFFICIENT_MARKERS = (
    "근거가 부족",
    "정보가 부족",
    "직접 확인할 수 없",
    "문서에서 확인할 수 없",
    "충분한 근거가 없",
)
REFERENCE_MARKERS = ("문서", "매뉴얼", "SOP", "절차", "기준", "출처")
SOURCE_LINE_PATTERN = re.compile(r"^출처:\s*(.+)$")


@dataclass
class ServerProcessAdapter:
    settings: ServerRouterSettings
    router_service: ServerRouterService
    rag_client: RagClient
    server_answer_client: ServerAnswerClient
    final_score_client: FinalScoreClient
    answer_system_prompt: str

    async def process(self, request: ServerRouterInput) -> ServerProcessResult:
        routing = await self.router_service.route(request)
        return await self._process_routing_result(routing)

    async def process_from_first_router(
        self,
        request: ServerRouterFromFirstRouterInput,
    ) -> ServerProcessResult:
        routing = await self.router_service.route_from_first_router(request)
        return await self._process_routing_result(routing)

    async def _process_routing_result(self, routing: ServerRouterResult) -> ServerProcessResult:
        original_question = routing.normalized_input.user_message

        if routing.decision.route == "server_rag":
            execution, score_payload = await self._execute_rag_path(original_question, routing.display)
        else:
            execution, score_payload = await self._execute_server_llm_path(
                original_question,
                routing.display,
            )

        score_result = await self._score_with_fallback(score_payload)
        final_score = _build_final_score_snapshot(score_result)

        return ServerProcessResult(
            request_id=routing.normalized_input.request_id,
            original_question=original_question,
            routing=routing,
            execution=execution,
            final_score=final_score,
            score_payload=score_payload,
            final_answer=final_score.final_answer,
        )

    async def _execute_rag_path(
        self,
        original_question: str,
        second_route: ServerRouterDisplay,
    ) -> tuple[ProcessExecutionResult, dict[str, Any]]:
        try:
            rag_raw = await self.rag_client.ask(original_question)
            rag_score_payload = _build_legacy_rag_score_payload(
                original_question,
                second_route,
                rag_raw,
            )
            execution = ProcessExecutionResult(
                target_system="rag_reference_api",
                status="completed",
                answer=rag_score_payload["rag_result"]["answer"],
                details={
                    "raw_response": rag_raw,
                    "rag_api_endpoint": self.settings.rag_api_endpoint,
                },
            )
            return execution, rag_score_payload
        except Exception as exc:
            execution = ProcessExecutionResult(
                target_system="rag_reference_api",
                status="failed",
                answer=None,
                details={"error": str(exc), "rag_api_endpoint": self.settings.rag_api_endpoint},
            )
            return execution, _build_failed_score_payload(original_question, second_route, "server_rag")

    async def _execute_server_llm_path(
        self,
        original_question: str,
        second_route: ServerRouterDisplay,
    ) -> tuple[ProcessExecutionResult, dict[str, Any]]:
        try:
            answer = await self.server_answer_client.answer(
                original_question,
                self.answer_system_prompt,
            )
            score_payload = _build_server_llm_score_payload(
                original_question,
                second_route,
                answer,
            )
            execution = ProcessExecutionResult(
                target_system="server_large_llm",
                status="completed",
                answer=answer,
                details={
                    "answer_model_endpoint": self.settings.answer_model_endpoint,
                    "answer_model_name": self.settings.answer_model_name,
                },
            )
            return execution, score_payload
        except Exception as exc:
            execution = ProcessExecutionResult(
                target_system="server_large_llm",
                status="failed",
                answer=None,
                details={
                    "error": str(exc),
                    "answer_model_endpoint": self.settings.answer_model_endpoint,
                },
            )
            return execution, _build_failed_score_payload(original_question, second_route, "server_llm")

    async def _score_with_fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self.final_score_client.score(payload)
        except Exception as exc:
            route_used = str(payload.get("route_used", "server_llm"))
            return {
                "display": {
                    "final_score": 0,
                    "action": "retry_generation",
                    "brief": "final-score 서비스 호출 실패",
                    "reasons": ["final_score_unavailable", str(exc)],
                },
                "decision": {
                    "route_used": route_used,
                    "final_score": 0,
                    "action": "retry_generation",
                    "reasons": ["final_score_unavailable", str(exc)],
                    "breakdown": {
                        "routing_confidence": 0,
                        "evidence_quality": 0,
                        "safety": 0,
                        "answer_quality": 0,
                        "format_quality": 0,
                    },
                    "final_answer": None,
                },
            }


def build_process_adapter(
    settings: ServerRouterSettings,
    router_service: ServerRouterService,
    rag_client: RagClient,
    server_answer_client: ServerAnswerClient,
    final_score_client: FinalScoreClient,
) -> ServerProcessAdapter:
    answer_system_prompt = load_system_prompt(settings.answer_prompt_path)
    return ServerProcessAdapter(
        settings=settings,
        router_service=router_service,
        rag_client=rag_client,
        server_answer_client=server_answer_client,
        final_score_client=final_score_client,
        answer_system_prompt=answer_system_prompt,
    )


def _build_server_llm_score_payload(
    original_question: str,
    second_route: ServerRouterDisplay,
    answer: str,
) -> dict[str, Any]:
    return {
        "original_question": original_question,
        "route_used": "server_llm",
        "second_router": second_route.model_dump(),
        "server_llm_result": {
            "answer": answer,
            "needs_human_review": _contains_any(answer, HUMAN_REVIEW_MARKERS),
            "mentioned_references": _contains_any(answer, REFERENCE_MARKERS),
        },
    }


def _build_legacy_rag_score_payload(
    original_question: str,
    second_route: ServerRouterDisplay,
    rag_raw: dict[str, Any],
) -> dict[str, Any]:
    raw_answer = str(rag_raw.get("answer", "")).strip()
    answer_text, source_lines = _split_legacy_rag_answer(raw_answer)
    return {
        "original_question": original_question,
        "route_used": "server_rag",
        "second_router": second_route.model_dump(),
        "rag_result": {
            "answerable": not _contains_any(answer_text, INSUFFICIENT_MARKERS),
            "answer": answer_text,
            "used_chunk_ids": source_lines,
            "needs_human_review": _contains_any(answer_text, HUMAN_REVIEW_MARKERS),
            "warning": _extract_warning(answer_text),
            "retrieved_scores": [],
        },
    }


def _build_failed_score_payload(
    original_question: str,
    second_route: ServerRouterDisplay,
    route_used: str,
) -> dict[str, Any]:
    return {
        "original_question": original_question,
        "route_used": route_used,
        "second_router": second_route.model_dump(),
    }


def _split_legacy_rag_answer(raw_answer: str) -> tuple[str, list[str]]:
    if not raw_answer:
        return "", []

    body, _, tail = raw_answer.partition("\n\n---\n")
    source_ids: list[str] = []
    for line in tail.splitlines():
        match = SOURCE_LINE_PATTERN.match(line.strip())
        if not match:
            continue
        source = match.group(1).strip()
        if source and source not in source_ids:
            source_ids.append(source)
    return body.strip(), source_ids


def _extract_warning(answer_text: str) -> str | None:
    for line in re.split(r"[\n\.]", answer_text):
        stripped = line.strip()
        if stripped and _contains_any(stripped, WARNING_MARKERS):
            return stripped
    return None


def _build_final_score_snapshot(raw_result: dict[str, Any]) -> FinalScoreSnapshot:
    display = raw_result.get("display", {})
    decision = raw_result.get("decision", {})
    final_score = int(display.get("final_score", decision.get("final_score", 0)))
    action = str(display.get("action", decision.get("action", "retry_generation")))
    brief = str(display.get("brief", "최종 점수 결과를 반환했습니다."))
    reasons = display.get("reasons", decision.get("reasons", []))
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    final_answer = decision.get("final_answer")
    if final_answer is not None:
        final_answer = str(final_answer)
    return FinalScoreSnapshot(
        final_score=final_score,
        action=action,
        brief=brief,
        reasons=[str(reason) for reason in reasons],
        final_answer=final_answer,
    )


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in markers)
