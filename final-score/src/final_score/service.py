from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from .models import (
    Action,
    FinalScoreDecision,
    FinalScoreDisplay,
    FinalScoreInput,
    FinalScoreResult,
    HarnessTraceEntry,
    NormalizedFinalScoreInput,
    ScoreBreakdown,
)


REFERENCE_KEYWORDS = {
    "manual",
    "sop",
    "procedure",
    "guide",
    "document",
    "reference",
    "spec",
    "specs",
    "policy",
    "policies",
    "매뉴얼",
    "절차",
    "문서",
    "가이드",
    "설명서",
    "사용설명서",
    "레퍼런스",
    "규격",
    "사양",
    "정책",
    "기준",
}
RISKY_CONTENT_KEYWORDS = {
    "진단",
    "치료",
    "처방",
    "투약",
    "복용",
    "용량",
    "수술",
    "약을",
    "약물",
}
UNSAFE_OVERRIDE_KEYWORDS = {
    "무시",
    "우회",
    "강제로",
    "비활성",
    "해제",
    "override",
    "bypass",
}
ERROR_CODE_PATTERN = re.compile(r"\b[Ee]\d{2,4}\b")
CONFIDENCE_POINTS = {"high": 20, "medium": 14, "low": 8}


@dataclass
class FinalScoreService:
    def evaluate(self, request: FinalScoreInput) -> FinalScoreResult:
        normalized_input = normalize_final_score_input(request)
        trace = [
            HarnessTraceEntry(
                stage="normalize",
                status="passed",
                detail="Input was normalized for deterministic final scoring.",
                data={
                    "request_id": normalized_input.request_id,
                    "route_used": normalized_input.route_used,
                },
            )
        ]

        if normalized_input.route_used == "server_rag":
            decision = _score_rag_path(normalized_input)
        else:
            decision = _score_server_llm_path(normalized_input)

        trace.append(
            HarnessTraceEntry(
                stage="evaluate",
                status="applied",
                detail="Applied deterministic final-score policy.",
                data={
                    "action": decision.action,
                    "final_score": decision.final_score,
                },
            )
        )
        trace.append(
            HarnessTraceEntry(
                stage="decision",
                status="applied",
                detail="Built the final score gate result.",
                data={"reasons": decision.reasons},
            )
        )

        return FinalScoreResult(
            display=_build_display(decision),
            decision=decision,
            normalized_input=normalized_input,
            trace=trace,
        )


def build_final_score_service() -> FinalScoreService:
    return FinalScoreService()


def normalize_final_score_input(request: FinalScoreInput) -> NormalizedFinalScoreInput:
    resolved_request_id = (
        request.request_id
        or str(request.metadata.get("request_id", "")).strip()
        or uuid4().hex[:12]
    )
    return NormalizedFinalScoreInput(
        request_id=resolved_request_id,
        original_question=request.original_question,
        route_used=request.route_used,
        metadata=request.metadata,
        second_router=request.second_router,
        rag_result=request.rag_result,
        server_llm_result=request.server_llm_result,
    )


def _score_rag_path(request: NormalizedFinalScoreInput) -> FinalScoreDecision:
    reasons: list[str] = []
    routing_confidence = _routing_points(request)
    evidence_quality = 0
    safety = 25
    answer_quality = 0
    format_quality = 0
    action: Action = "retry_generation"
    final_answer: str | None = None

    if request.rag_result is None:
        reasons.append("missing_rag_result")
        return _build_decision(
            request,
            action="retry_generation",
            reasons=reasons,
            routing_confidence=routing_confidence,
            evidence_quality=evidence_quality,
            safety=safety,
            answer_quality=answer_quality,
            format_quality=format_quality,
            final_answer=None,
        )

    rag_result = request.rag_result
    answer = rag_result.answer

    if answer:
        answer_quality = 18 if len(answer) >= 20 else 10
        format_quality += 4
    else:
        reasons.append("empty_answer")

    if rag_result.answerable:
        evidence_quality = 18
        if rag_result.used_chunk_ids:
            evidence_quality += 7
            format_quality += 6
        else:
            reasons.append("missing_chunk_ids")
        if rag_result.retrieved_scores:
            average_score = sum(rag_result.retrieved_scores) / len(rag_result.retrieved_scores)
            if average_score >= 0.85:
                evidence_quality = min(25, evidence_quality + 2)
            elif average_score < 0.45:
                evidence_quality = max(0, evidence_quality - 4)
                reasons.append("low_retrieval_scores")
    else:
        evidence_quality = 4
        reasons.append("unsupported_by_context")

    if rag_result.needs_human_review:
        safety = 0
        reasons.append("rag_requested_human_review")
    elif rag_result.warning:
        safety = 18
        reasons.append("warning_present")

    if rag_result.needs_human_review or not rag_result.answerable:
        action = "human_review"
    elif not answer:
        action = "retry_generation"
    elif not rag_result.used_chunk_ids:
        action = "retry_generation"
    else:
        tentative_score = routing_confidence + evidence_quality + safety + answer_quality + format_quality
        if tentative_score >= 75:
            action = "release"
            final_answer = answer
        elif tentative_score >= 55:
            action = "retry_generation"
        else:
            action = "human_review"

    return _build_decision(
        request,
        action=action,
        reasons=reasons,
        routing_confidence=routing_confidence,
        evidence_quality=evidence_quality,
        safety=safety,
        answer_quality=answer_quality,
        format_quality=format_quality,
        final_answer=final_answer,
    )


def _score_server_llm_path(request: NormalizedFinalScoreInput) -> FinalScoreDecision:
    reasons: list[str] = []
    routing_confidence = _routing_points(request)
    evidence_quality = 12
    safety = 25
    answer_quality = 0
    format_quality = 0
    action: Action = "retry_generation"
    final_answer: str | None = None

    if request.server_llm_result is None:
        reasons.append("missing_server_llm_result")
        return _build_decision(
            request,
            action="retry_generation",
            reasons=reasons,
            routing_confidence=routing_confidence,
            evidence_quality=0,
            safety=safety,
            answer_quality=0,
            format_quality=0,
            final_answer=None,
        )

    answer = request.server_llm_result.answer
    reference_like_question = _is_reference_like(request.original_question)
    risky_content = _contains_any(answer.casefold(), RISKY_CONTENT_KEYWORDS)
    unsafe_override = _contains_any(answer.casefold(), UNSAFE_OVERRIDE_KEYWORDS)

    if request.second_router is not None and request.second_router.route == "server_rag":
        reference_like_question = True
        reasons.append("second_router_prefers_rag")

    if reference_like_question:
        reasons.append("reference_grounding_needed")
        evidence_quality = 0
        action = "reroute_to_rag"
    elif unsafe_override:
        reasons.append("unsafe_override_detected")
        safety = 0
        evidence_quality = 0
        action = "block"
    elif request.server_llm_result.needs_human_review or risky_content:
        reasons.append("human_review_required")
        safety = 0
        action = "human_review"

    if answer:
        answer_quality = 18 if len(answer) >= 20 else 10
        format_quality = 10
    else:
        reasons.append("empty_answer")

    if action in {"release", "retry_generation"}:
        tentative_score = routing_confidence + evidence_quality + safety + answer_quality + format_quality
        if tentative_score >= 70:
            action = "release"
            final_answer = answer
        else:
            action = "retry_generation"

    return _build_decision(
        request,
        action=action,
        reasons=reasons,
        routing_confidence=routing_confidence,
        evidence_quality=evidence_quality,
        safety=safety,
        answer_quality=answer_quality,
        format_quality=format_quality,
        final_answer=final_answer,
    )


def _routing_points(request: NormalizedFinalScoreInput) -> int:
    if request.second_router is None:
        return CONFIDENCE_POINTS["medium"]
    return CONFIDENCE_POINTS[request.second_router.confidence]


def _build_decision(
    request: NormalizedFinalScoreInput,
    *,
    action: Action,
    reasons: list[str],
    routing_confidence: int,
    evidence_quality: int,
    safety: int,
    answer_quality: int,
    format_quality: int,
    final_answer: str | None,
) -> FinalScoreDecision:
    breakdown = ScoreBreakdown(
        routing_confidence=routing_confidence,
        evidence_quality=evidence_quality,
        safety=safety,
        answer_quality=answer_quality,
        format_quality=format_quality,
    )
    total = (
        breakdown.routing_confidence
        + breakdown.evidence_quality
        + breakdown.safety
        + breakdown.answer_quality
        + breakdown.format_quality
    )
    unique_reasons: list[str] = []
    for reason in reasons:
        if reason not in unique_reasons:
            unique_reasons.append(reason)
    return FinalScoreDecision(
        route_used=request.route_used,
        final_score=max(0, min(100, total)),
        action=action,
        reasons=unique_reasons,
        breakdown=breakdown,
        final_answer=final_answer,
    )


def _build_display(decision: FinalScoreDecision) -> FinalScoreDisplay:
    brief_map = {
        "release": "최종 점수 기준을 만족해 답변 출고",
        "reroute_to_rag": "문서 근거가 필요해 RAG로 재분기",
        "retry_generation": "출력 품질이 부족해 재생성 필요",
        "human_review": "안전 또는 근거 이슈로 사람 검토 필요",
        "block": "위험한 우회/무시 성격이 보여 차단",
    }
    return FinalScoreDisplay(
        final_score=decision.final_score,
        action=decision.action,
        brief=brief_map[decision.action],
        reasons=decision.reasons,
    )


def _is_reference_like(question: str) -> bool:
    lowered = question.casefold()
    return bool(ERROR_CODE_PATTERN.search(question)) or _contains_any(lowered, REFERENCE_KEYWORDS)


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)
