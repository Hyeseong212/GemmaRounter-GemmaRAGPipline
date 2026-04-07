import asyncio

from gemma_server_router.config import ServerRouterSettings
from gemma_server_router.models import ServerRouterInput
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
