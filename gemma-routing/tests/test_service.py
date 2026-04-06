import asyncio

from gemma_routing.config import RouterSettings
from gemma_routing.models import RouterInput
from gemma_routing.service import RouterService


class SequenceClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if not self.responses:
            raise RuntimeError("No stub response configured")
        return self.responses.pop(0)


def test_service_repairs_invalid_model_output() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient(
            [
                "not-json",
                """
                {
                  "intent": "device_error_question",
                  "risk_level": "medium",
                  "route": "server_rag",
                  "needs_human_review": false,
                  "patient_related": false,
                  "priority": "high",
                  "required_tools": ["manual_retrieval"],
                  "reason_codes": ["needs_reference_grounding"],
                  "summary_for_server": "사용자가 E210 의미와 조치 방법을 문의함",
                  "local_action": "none"
                }
                """,
            ]
        ),
        system_prompt="system",
    )

    result = asyncio.run(service.route(RouterInput(user_message="E210 에러가 떴어")))

    assert result.decision_source == "model_repair"
    assert result.decision.route == "server_rag"
    assert result.handoff is not None
    assert result.handoff.target_system == "rag_reference_api"
    assert any(entry.stage == "repair" and entry.status == "repaired" for entry in result.trace)


def test_service_overrides_server_vision_without_image() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient(
            [
                """
                {
                  "intent": "ui_screen_question",
                  "risk_level": "medium",
                  "route": "server_vision",
                  "needs_human_review": false,
                  "patient_related": false,
                  "priority": "high",
                  "required_tools": ["vision_analysis"],
                  "reason_codes": ["needs_visual_inspection"],
                  "summary_for_server": "화면 상태를 확인해 달라는 요청",
                  "local_action": "none"
                }
                """
            ]
        ),
        system_prompt="system",
    )

    result = asyncio.run(service.route(RouterInput(user_message="화면 상태 좀 확인해줘")))

    assert result.decision_source == "model"
    assert result.decision.route == "human_review"
    assert result.handoff is not None
    assert result.handoff.target_system == "operator_review_queue"
    assert any(entry.stage == "post_policy" for entry in result.trace)


def test_service_generates_intervl_handoff_for_image_requests() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient([]),
        system_prompt="system",
    )

    result = asyncio.run(
        service.route(RouterInput(user_message="첨부한 장비 화면 좀 봐줘", has_image=True))
    )

    assert result.decision_source == "hard_rule"
    assert result.decision.route == "server_vision"
    assert result.handoff is not None
    assert result.handoff.target_system == "intervl_78b"
    assert "Do not give diagnosis or treatment advice." in result.handoff.must_not_do


def test_service_generates_local_llm_handoff_for_general_question() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient(
            [
                """
                {
                  "intent": "general_question",
                  "risk_level": "low",
                  "route": "local_llm",
                  "needs_human_review": false,
                  "patient_related": false,
                  "priority": "normal",
                  "required_tools": [],
                  "reason_codes": ["local_general_answer_ok"],
                  "summary_for_server": "",
                  "local_action": "answer_with_local_llm"
                }
                """
            ]
        ),
        system_prompt="system",
    )

    result = asyncio.run(service.route(RouterInput(user_message="20자 이내로 출발 안내 멘트 만들어줘")))

    assert result.decision.route == "local_llm"
    assert result.handoff is not None
    assert result.handoff.target_system == "local_gemma_answerer"
    assert result.handoff.task_type == "short_general_answer"
    assert result.handoff.metadata["max_answer_chars"] == 20


def test_service_downgrades_server_llm_to_local_llm_when_offline() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient(
            [
                """
                {
                  "intent": "general_reasoning_question",
                  "risk_level": "low",
                  "route": "server_llm",
                  "needs_human_review": false,
                  "patient_related": false,
                  "priority": "normal",
                  "required_tools": ["server_large_llm"],
                  "reason_codes": ["needs_large_model_reasoning"],
                  "summary_for_server": "운영 방식 차이를 비교해 달라는 일반 질문",
                  "local_action": "none"
                }
                """
            ]
        ),
        system_prompt="system",
    )

    result = asyncio.run(
        service.route(
            RouterInput(
                user_message="운영 방식 차이를 비교해줘",
                network_status="offline",
            )
        )
    )

    assert result.decision.route == "local_llm"
    assert result.handoff is not None
    assert result.handoff.target_system == "local_gemma_answerer"
    assert "network_limited_mode" in result.decision.reason_codes


def test_service_upgrades_local_llm_to_server_llm_when_20_char_budget_is_unlikely() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient(
            [
                """
                {
                  "intent": "general_question",
                  "risk_level": "low",
                  "route": "local_llm",
                  "needs_human_review": false,
                  "patient_related": false,
                  "priority": "normal",
                  "required_tools": [],
                  "reason_codes": ["local_general_answer_ok"],
                  "summary_for_server": "장비 방식 비교 설명 요청",
                  "local_action": "answer_with_local_llm"
                }
                """
            ]
        ),
        system_prompt="system",
    )

    result = asyncio.run(
        service.route(RouterInput(user_message="이 장비 방식과 기존 방식의 차이와 장단점을 자세히 설명해줘"))
    )

    assert result.decision.route == "server_llm"
    assert result.handoff is not None
    assert result.handoff.target_system == "server_large_llm"
    assert "needs_large_model_reasoning" in result.decision.reason_codes


def test_server_rag_handoff_matches_reference_api_contract() -> None:
    service = RouterService(
        settings=RouterSettings(),
        model_client=SequenceClient(
            [
                """
                {
                  "intent": "manual_procedure_question",
                  "risk_level": "medium",
                  "route": "server_rag",
                  "needs_human_review": false,
                  "patient_related": false,
                  "priority": "high",
                  "required_tools": ["manual_retrieval"],
                  "reason_codes": ["needs_reference_grounding"],
                  "summary_for_server": "사용자가 절차 문서를 참고한 답변을 원함",
                  "local_action": "none"
                }
                """
            ]
        ),
        system_prompt="system",
    )

    result = asyncio.run(service.route(RouterInput(user_message="이 절차 순서를 문서 기준으로 알려줘")))

    assert result.decision.route == "server_rag"
    assert result.handoff is not None
    assert result.handoff.target_system == "rag_reference_api"
    assert result.handoff.metadata["api_contract"]["endpoint"] == "/ask"
    assert result.handoff.metadata["api_contract"]["response_key"] == "answer"
