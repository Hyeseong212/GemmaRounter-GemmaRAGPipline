import asyncio

import pytest

from gemma_server_router.config import ServerRouterSettings
from gemma_server_router.models import ServerRouterFromFirstRouterInput, ServerRouterInput
from gemma_server_router.service import ServerRouterService


class SequenceClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        if not self.responses:
            raise RuntimeError("No stub response configured")
        return self.responses.pop(0)


def test_service_routes_to_rag_from_model_output() -> None:
    service = ServerRouterService(
        settings=ServerRouterSettings(),
        model_client=SequenceClient(
            [
                """
                {
                  "route": "server_rag",
                  "confidence": "high",
                  "summary_for_handoff": "E103 에러 의미와 조치 질문",
                  "retrieval_query": "E103 에러 의미 조치"
                }
                """
            ]
        ),
        system_prompt="system",
    )

    result = asyncio.run(service.route(ServerRouterInput(user_message="E103 에러 의미와 조치 알려줘")))

    assert result.decision_source == "model"
    assert result.decision.route == "server_rag"
    assert result.handoff.target_system == "rag_reference_api"
    assert result.decision.needs_rag is True


def test_service_falls_back_to_rag_for_reference_like_question() -> None:
    service = ServerRouterService(
        settings=ServerRouterSettings(),
        model_client=SequenceClient(["not-json"]),
        system_prompt="system",
    )

    result = asyncio.run(service.route(ServerRouterInput(user_message="슬링 체결 절차를 SOP 기준으로 알려줘")))

    assert result.decision_source == "fallback"
    assert result.decision.route == "server_rag"
    assert result.handoff.target_system == "rag_reference_api"


def test_service_falls_back_to_server_llm_for_general_reasoning() -> None:
    service = ServerRouterService(
        settings=ServerRouterSettings(),
        model_client=SequenceClient(["bad-output"]),
        system_prompt="system",
    )

    result = asyncio.run(
        service.route(ServerRouterInput(user_message="로컬 LLM과 서버 LLM 역할 분리를 비교해서 설명해줘"))
    )

    assert result.decision_source == "fallback"
    assert result.decision.route == "server_llm"
    assert result.handoff.target_system == "server_large_llm"


def test_route_from_first_router_uses_explicit_original_question() -> None:
    service = ServerRouterService(
        settings=ServerRouterSettings(),
        model_client=SequenceClient(["bad-output"]),
        system_prompt="system",
    )

    request = ServerRouterFromFirstRouterInput.model_validate(
        {
            "request_id": "server-bridge-001",
            "original_question": "이 장비 구조를 비교해서 설명해줘",
            "metadata": {"locale": "ko-KR"},
            "first_router": {
                "display": {
                    "route": "server_llm",
                    "decision_source": "fallback",
                    "brief": "설명형 일반 질문이라 서버 LLM으로 전달",
                    "target_system": "server_large_llm",
                    "reason_codes": ["needs_large_model_reasoning"],
                },
                "handoff": {
                    "route": "server_llm",
                    "target_system": "server_large_llm",
                    "task_type": "general_answer_generation",
                    "summary": "장비 구조 비교 설명 요청",
                    "required_inputs": ["user_message"],
                    "metadata": {
                        "question": "짧은 요약 질문",
                        "request_id": "router-001",
                    },
                },
            },
        }
    )

    result = asyncio.run(service.route_from_first_router(request))

    assert result.normalized_input.user_message == "이 장비 구조를 비교해서 설명해줘"
    assert result.normalized_input.metadata["source"] == "first_router"
    assert result.normalized_input.metadata["first_router_display"]["route"] == "server_llm"
    assert result.normalized_input.metadata["upstream_target_system"] == "server_large_llm"
    assert result.decision.route == "server_llm"


def test_route_from_first_router_falls_back_to_handoff_original_question() -> None:
    service = ServerRouterService(
        settings=ServerRouterSettings(),
        model_client=SequenceClient(["not-json"]),
        system_prompt="system",
    )

    request = ServerRouterFromFirstRouterInput.model_validate(
        {
            "request_id": "server-bridge-002",
            "metadata": {"locale": "ko-KR"},
            "first_router": {
                "display": {
                    "route": "server_rag",
                    "decision_source": "hard_rule",
                    "brief": "문서 근거가 필요해 RAG로 전달",
                    "target_system": "rag_reference_api",
                    "reason_codes": ["needs_reference_grounding"],
                },
                "handoff": {
                    "route": "server_rag",
                    "target_system": "rag_reference_api",
                    "task_type": "grounded_reference_lookup",
                    "summary": "E103 에러 의미와 조치 질문",
                    "required_inputs": ["user_message", "retrieved_context"],
                    "metadata": {
                        "original_question": "E103 에러가 떴는데 다음 조치 순서를 알려줘",
                        "request_id": "router-002",
                    },
                },
            },
        }
    )

    result = asyncio.run(service.route_from_first_router(request))

    assert result.normalized_input.user_message == "E103 에러가 떴는데 다음 조치 순서를 알려줘"
    assert result.decision.route == "server_rag"
    assert result.handoff.target_system == "rag_reference_api"


def test_route_from_first_router_rejects_non_server_bound_route() -> None:
    service = ServerRouterService(
        settings=ServerRouterSettings(),
        model_client=SequenceClient(["bad-output"]),
        system_prompt="system",
    )

    request = ServerRouterFromFirstRouterInput.model_validate(
        {
            "original_question": "출발 멘트 줘",
            "first_router": {
                "display": {
                    "route": "local_llm",
                    "decision_source": "hard_rule",
                    "brief": "짧은 일반 질문이라 로컬 처리",
                    "target_system": "local_gemma_answerer",
                    "reason_codes": ["local_general_answer_ok"],
                },
                "handoff": {
                    "route": "local_llm",
                    "target_system": "local_gemma_answerer",
                    "task_type": "short_general_answer",
                    "summary": "출발 멘트 요청",
                    "required_inputs": ["user_message"],
                    "metadata": {"question": "출발 멘트 줘"},
                },
            },
        }
    )

    with pytest.raises(ValueError, match="server-bound"):
        asyncio.run(service.route_from_first_router(request))
