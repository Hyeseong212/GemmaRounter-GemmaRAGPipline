from gemma_routing.hard_rules import apply_hard_rules
from gemma_routing.models import RouterInput
from gemma_routing.signals import normalize_router_input


def test_local_status_question_routes_to_local_rule() -> None:
    request = normalize_router_input(RouterInput(user_message="배터리 상태 보여줘"))

    match = apply_hard_rules(request)

    assert match is not None
    assert match.decision.route == "local_rule_only"
    assert match.decision.intent == "device_status_question"
    assert match.rule_name == "use_local_device_status"


def test_medication_question_routes_to_human_review() -> None:
    request = normalize_router_input(RouterInput(user_message="이 환자한테 약 용량을 늘려도 돼?"))

    match = apply_hard_rules(request)

    assert match is not None
    assert match.decision.route == "human_review"
    assert match.decision.intent == "medication_advice_request"


def test_attached_image_routes_to_server_vision() -> None:
    request = normalize_router_input(
        RouterInput(user_message="첨부한 스크린샷 좀 봐줘", has_image=True)
    )

    match = apply_hard_rules(request)

    assert match is not None
    assert match.decision.route == "server_vision"
    assert match.decision.reason_codes == ["needs_visual_inspection"]


def test_offline_general_question_routes_to_local_llm() -> None:
    request = normalize_router_input(
        RouterInput(
            user_message="20자 이내로 출발 안내 멘트 만들어줘",
            network_status="offline",
        )
    )

    match = apply_hard_rules(request)

    assert match is not None
    assert match.decision.route == "local_llm"
    assert match.decision.local_action == "answer_with_local_llm"
    assert "network_limited_mode" in match.decision.reason_codes


def test_offline_long_general_question_routes_to_limited_notice() -> None:
    request = normalize_router_input(
        RouterInput(
            user_message="이 장비 방식과 기존 방식의 차이와 장단점을 자세히 설명해줘",
            network_status="offline",
        )
    )

    match = apply_hard_rules(request)

    assert match is not None
    assert match.decision.route == "local_rule_only"
    assert match.decision.local_action == "show_limited_mode_notice"


def test_offline_error_code_prefers_cached_help() -> None:
    request = normalize_router_input(
        RouterInput(
            user_message="E210 에러가 떴어. 의미가 뭐야?",
            network_status="offline",
            local_tools_available=["device_status_api", "cached_error_help"],
        )
    )

    match = apply_hard_rules(request)

    assert match is not None
    assert match.decision.route == "local_rule_only"
    assert match.decision.local_action == "show_cached_error_help"
    assert "needs_reference_grounding" in match.decision.reason_codes
