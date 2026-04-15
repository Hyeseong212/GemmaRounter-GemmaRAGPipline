from final_score.models import FinalScoreInput
from final_score.service import FinalScoreService


def test_rag_answer_is_released_when_grounded_and_structured() -> None:
    service = FinalScoreService()

    result = service.evaluate(
        FinalScoreInput.model_validate(
            {
                "original_question": "E103 에러가 떴는데 다음 조치 순서를 알려줘",
                "route_used": "server_rag",
                "second_router": {
                    "route": "server_rag",
                    "needs_rag": True,
                    "confidence": "high",
                    "brief": "문서 근거가 필요해 RAG로 전달",
                    "reason_codes": ["error_code_reference"],
                },
                "rag_result": {
                    "answerable": True,
                    "answer": "E103이 표시되면 먼저 케이블 체결 상태를 확인하세요. 재부팅 후에도 반복되면 사용을 중지하고 유지보수 담당자에게 보고해야 합니다.",
                    "used_chunk_ids": ["chunk-01", "chunk-02"],
                    "needs_human_review": False,
                    "warning": None,
                    "retrieved_scores": [0.92, 0.84],
                },
            }
        )
    )

    assert result.decision.action == "release"
    assert result.decision.final_answer is not None
    assert result.decision.final_score >= 75


def test_rag_answer_without_chunk_ids_is_retried() -> None:
    service = FinalScoreService()

    result = service.evaluate(
        FinalScoreInput.model_validate(
            {
                "original_question": "E103 에러가 떴는데 다음 조치 순서를 알려줘",
                "route_used": "server_rag",
                "rag_result": {
                    "answerable": True,
                    "answer": "케이블 체결 상태를 먼저 확인하세요.",
                    "used_chunk_ids": [],
                    "needs_human_review": False,
                    "warning": None,
                },
            }
        )
    )

    assert result.decision.action == "retry_generation"
    assert "missing_chunk_ids" in result.decision.reasons


def test_rag_answer_marked_for_human_review_is_not_released() -> None:
    service = FinalScoreService()

    result = service.evaluate(
        FinalScoreInput.model_validate(
            {
                "original_question": "수술 가능 여부를 알려줘",
                "route_used": "server_rag",
                "rag_result": {
                    "answerable": True,
                    "answer": "문서 일부 근거는 있지만 환자 상태 판단이 필요합니다.",
                    "used_chunk_ids": ["chunk-09"],
                    "needs_human_review": True,
                    "warning": "환자별 판단이 필요하다.",
                },
            }
        )
    )

    assert result.decision.action == "human_review"
    assert "rag_requested_human_review" in result.decision.reasons


def test_server_llm_answer_for_reference_like_question_is_rerouted_to_rag() -> None:
    service = FinalScoreService()

    result = service.evaluate(
        FinalScoreInput.model_validate(
            {
                "original_question": "E103 에러 의미를 설명해줘",
                "route_used": "server_llm",
                "second_router": {
                    "route": "server_llm",
                    "needs_rag": False,
                    "confidence": "medium",
                    "brief": "일반 서버 LLM 답변으로 처리",
                    "reason_codes": ["general_reasoning_ok"],
                },
                "server_llm_result": {
                    "answer": "E103은 장비 연결 문제일 수 있습니다. 정확한 의미는 문서를 봐야 합니다.",
                    "needs_human_review": False,
                    "mentioned_references": True,
                },
            }
        )
    )

    assert result.decision.action == "reroute_to_rag"
    assert "reference_grounding_needed" in result.decision.reasons


def test_server_llm_general_answer_is_released() -> None:
    service = FinalScoreService()

    result = service.evaluate(
        FinalScoreInput.model_validate(
            {
                "original_question": "로컬 LLM과 서버 LLM 역할 분리를 비교해서 설명해줘",
                "route_used": "server_llm",
                "second_router": {
                    "route": "server_llm",
                    "needs_rag": False,
                    "confidence": "high",
                    "brief": "일반 서버 LLM 답변으로 처리",
                    "reason_codes": ["general_reasoning_ok"],
                },
                "server_llm_result": {
                    "answer": "로컬 LLM은 빠른 반응과 간단한 처리에 적합하고, 서버 LLM은 긴 설명과 복잡한 추론에 더 적합합니다.",
                    "needs_human_review": False,
                    "mentioned_references": False,
                },
            }
        )
    )

    assert result.decision.action == "release"
    assert result.decision.final_answer is not None


def test_server_llm_risky_medical_answer_goes_to_human_review() -> None:
    service = FinalScoreService()

    result = service.evaluate(
        FinalScoreInput.model_validate(
            {
                "original_question": "장비 설명해줘",
                "route_used": "server_llm",
                "server_llm_result": {
                    "answer": "증상이 있으면 바로 복용량을 늘리고 치료 방향을 바꾸세요.",
                    "needs_human_review": False,
                    "mentioned_references": False,
                },
            }
        )
    )

    assert result.decision.action == "human_review"
    assert "human_review_required" in result.decision.reasons
