import asyncio

from gemma_routing.config import RouterSettings
from gemma_routing.models import RouterInput
from gemma_routing.service import RouterService


class SequenceClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        self.calls.append((system_prompt, user_prompt))
        if not self.responses:
            raise RuntimeError("No stub response configured")
        return self.responses.pop(0)


def test_service_falls_back_to_server_llm_on_invalid_model_output() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient(["not-json"]),
        system_prompt="system",
        local_answer_system_prompt="answer-system",
    )

    result = asyncio.run(
        service.route(RouterInput(user_message="이 장비 방식과 기존 방식의 차이를 설명해줘"))
    )

    assert result.decision_source == "fallback"
    assert result.decision.route == "server_llm"
    assert result.handoff is not None
    assert result.handoff.target_system == "server_large_llm"
    assert any(entry.stage == "fallback" for entry in result.trace)


def test_service_routes_short_general_question_to_local_llm_via_hard_rule() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient(
            [
                """
                {
                  "route": "local_llm",
                  "summary_for_server": ""
                }
                """
            ]
        ),
        system_prompt="system",
        local_answer_system_prompt="answer-system",
    )

    result = asyncio.run(service.route(RouterInput(user_message="짧게 출발 멘트 줘")))

    assert result.decision_source == "hard_rule"
    assert result.decision.route == "local_llm"
    assert result.handoff is not None
    assert result.handoff.target_system == "local_gemma_answerer"
    assert result.handoff.metadata["max_answer_chars"] == 20


def test_service_upgrades_local_llm_to_server_llm_when_20_char_budget_is_unlikely() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient(
            [
                """
                {
                  "route": "local_llm",
                  "summary_for_server": "장비 방식 비교 설명 요청"
                }
                """
            ]
        ),
        system_prompt="system",
        local_answer_system_prompt="answer-system",
    )

    result = asyncio.run(
        service.route(RouterInput(user_message="이 장비 방식과 기존 방식의 차이와 장단점을 자세히 설명해줘"))
    )

    assert result.decision.route == "server_llm"
    assert result.handoff is not None
    assert result.handoff.target_system == "server_large_llm"
    assert "needs_large_model_reasoning" in result.decision.reason_codes


def test_service_routes_reference_question_to_rag_contract() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient([]),
        system_prompt="system",
        local_answer_system_prompt="answer-system",
    )

    result = asyncio.run(service.route(RouterInput(user_message="이 절차 순서를 문서 기준으로 알려줘")))

    assert result.decision_source == "hard_rule"
    assert result.decision.route == "server_rag"
    assert result.handoff is not None
    assert result.handoff.target_system == "rag_reference_api"
    assert result.handoff.metadata["original_question"] == "이 절차 순서를 문서 기준으로 알려줘"
    assert result.handoff.metadata["question"] == "이 절차 순서를 문서 기준으로 알려줘"
    assert result.handoff.metadata["request_id"]
    assert result.handoff.metadata["api_contract"]["endpoint"] == "/ask"
    assert result.handoff.metadata["api_contract"]["response_key"] == "answer"


def test_service_routes_image_request_to_human_review() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient([]),
        system_prompt="system",
        local_answer_system_prompt="answer-system",
    )

    result = asyncio.run(
        service.route(RouterInput(user_message="첨부한 장비 화면 좀 봐줘", has_image=True))
    )

    assert result.decision_source == "hard_rule"
    assert result.decision.route == "human_review"
    assert result.handoff is not None
    assert result.handoff.target_system == "operator_review_queue"


def test_handle_executes_local_answer_when_route_is_local_llm() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient(["출발하겠습니다"]),
        system_prompt="router-system",
        local_answer_system_prompt="answer-system",
    )

    result = asyncio.run(service.handle(RouterInput(user_message="20자 이내로 출발 안내 멘트 만들어줘")))

    assert result.display.route == "local_llm"
    assert result.execution is not None
    assert result.execution.status == "completed"
    assert result.execution.answer == "출발하겠습니다"
    assert result.execution.answer_char_count == len("출발하겠습니다")


def test_handle_reroutes_to_server_llm_when_local_answer_is_too_long() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient(["지금 바로 출발하겠습니다 안전하게 이동할게요"]),
        system_prompt="router-system",
        local_answer_system_prompt="answer-system",
    )

    result = asyncio.run(service.handle(RouterInput(user_message="20자 이내로 출발 안내 멘트 만들어줘")))

    assert result.display.route == "server_llm"
    assert result.display.decision_source == "local_execution"
    assert result.execution is not None
    assert result.execution.status == "rerouted"
    assert result.execution.reason == "local_answer_overflow"
    assert result.execution.rerouted_to == "server_llm"
