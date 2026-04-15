import asyncio

from gemma_server_router.adapter import ServerProcessAdapter
from gemma_server_router.config import ServerRouterSettings
from gemma_server_router.models import ServerRouterFromFirstRouterInput
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


class FakeRagClient:
    def __init__(self, response: dict[str, str]) -> None:
        self.response = response
        self.questions: list[str] = []

    async def ask(self, question: str) -> dict[str, str]:
        self.questions.append(question)
        return self.response


class FakeServerAnswerClient:
    def __init__(self, answer: str) -> None:
        self.answer_text = answer
        self.questions: list[str] = []

    async def answer(self, question: str, system_prompt: str) -> str:
        self.questions.append(question)
        return self.answer_text


class FakeFinalScoreClient:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.payloads: list[dict] = []

    async def score(self, payload: dict) -> dict:
        self.payloads.append(payload)
        return self.response


class FailingFinalScoreClient:
    async def score(self, payload: dict) -> dict:
        raise RuntimeError("final score service down")


def test_process_from_first_router_executes_rag_path() -> None:
    router_service = ServerRouterService(
        settings=ServerRouterSettings(),
        model_client=SequenceClient(["not-json"]),
        system_prompt="system",
    )
    rag_client = FakeRagClient(
        {
            "answer": "먼저 케이블 체결 상태를 확인하세요.\n\n---\n출처: IFU_v3.pdf (p.41)",
        }
    )
    final_score_client = FakeFinalScoreClient(
        {
            "display": {
                "final_score": 82,
                "action": "release",
                "brief": "최종 점수 기준을 만족해 답변 출고",
                "reasons": [],
            },
            "decision": {
                "final_score": 82,
                "action": "release",
                "reasons": [],
                "final_answer": "먼저 케이블 체결 상태를 확인하세요.",
            },
        }
    )
    adapter = ServerProcessAdapter(
        settings=ServerRouterSettings(),
        router_service=router_service,
        rag_client=rag_client,
        server_answer_client=FakeServerAnswerClient("unused"),
        final_score_client=final_score_client,
        answer_system_prompt="answer-system",
    )
    request = ServerRouterFromFirstRouterInput.model_validate(
        {
            "original_question": "E103 에러가 떴는데 다음 조치 순서를 알려줘",
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
                    "metadata": {"original_question": "E103 에러가 떴는데 다음 조치 순서를 알려줘"},
                },
            },
        }
    )

    result = asyncio.run(adapter.process_from_first_router(request))

    assert result.routing.decision.route == "server_rag"
    assert result.execution.target_system == "rag_reference_api"
    assert result.execution.status == "completed"
    assert rag_client.questions == ["E103 에러가 떴는데 다음 조치 순서를 알려줘"]
    assert final_score_client.payloads[0]["route_used"] == "server_rag"
    assert final_score_client.payloads[0]["rag_result"]["used_chunk_ids"] == ["IFU_v3.pdf (p.41)"]
    assert result.final_score.action == "release"


def test_process_from_first_router_executes_server_llm_path() -> None:
    router_service = ServerRouterService(
        settings=ServerRouterSettings(),
        model_client=SequenceClient(["bad-output"]),
        system_prompt="system",
    )
    final_score_client = FakeFinalScoreClient(
        {
            "display": {
                "final_score": 74,
                "action": "release",
                "brief": "최종 점수 기준을 만족해 답변 출고",
                "reasons": [],
            },
            "decision": {
                "final_score": 74,
                "action": "release",
                "reasons": [],
                "final_answer": "로컬은 빠르고 서버는 복잡한 설명에 적합합니다.",
            },
        }
    )
    server_answer_client = FakeServerAnswerClient(
        "로컬은 빠르고 서버는 복잡한 설명에 적합합니다."
    )
    adapter = ServerProcessAdapter(
        settings=ServerRouterSettings(),
        router_service=router_service,
        rag_client=FakeRagClient({"answer": "unused"}),
        server_answer_client=server_answer_client,
        final_score_client=final_score_client,
        answer_system_prompt="answer-system",
    )
    request = ServerRouterFromFirstRouterInput.model_validate(
        {
            "original_question": "로컬 LLM과 서버 LLM 역할 분리를 비교해서 설명해줘",
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
                    "summary": "로컬과 서버 역할 분리 설명 요청",
                    "required_inputs": ["user_message"],
                    "metadata": {"original_question": "로컬 LLM과 서버 LLM 역할 분리를 비교해서 설명해줘"},
                },
            },
        }
    )

    result = asyncio.run(adapter.process_from_first_router(request))

    assert result.routing.decision.route == "server_llm"
    assert result.execution.target_system == "server_large_llm"
    assert server_answer_client.questions == ["로컬 LLM과 서버 LLM 역할 분리를 비교해서 설명해줘"]
    assert final_score_client.payloads[0]["route_used"] == "server_llm"
    assert final_score_client.payloads[0]["server_llm_result"]["answer"] == "로컬은 빠르고 서버는 복잡한 설명에 적합합니다."
    assert result.final_answer == "로컬은 빠르고 서버는 복잡한 설명에 적합합니다."


def test_process_from_first_router_falls_back_when_final_score_is_unavailable() -> None:
    router_service = ServerRouterService(
        settings=ServerRouterSettings(),
        model_client=SequenceClient(["bad-output"]),
        system_prompt="system",
    )
    adapter = ServerProcessAdapter(
        settings=ServerRouterSettings(),
        router_service=router_service,
        rag_client=FakeRagClient({"answer": "unused"}),
        server_answer_client=FakeServerAnswerClient("일반 설명 답변입니다."),
        final_score_client=FailingFinalScoreClient(),
        answer_system_prompt="answer-system",
    )
    request = ServerRouterFromFirstRouterInput.model_validate(
        {
            "original_question": "로컬 LLM과 서버 LLM 역할 분리를 비교해서 설명해줘",
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
                    "summary": "로컬과 서버 역할 분리 설명 요청",
                    "required_inputs": ["user_message"],
                    "metadata": {"original_question": "로컬 LLM과 서버 LLM 역할 분리를 비교해서 설명해줘"},
                },
            },
        }
    )

    result = asyncio.run(adapter.process_from_first_router(request))

    assert result.final_score.action == "retry_generation"
    assert "final_score_unavailable" in result.final_score.reasons
