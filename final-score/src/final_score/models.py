from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


RouteUsed = Literal["server_rag", "server_llm"]
Confidence = Literal["high", "medium", "low"]
Action = Literal["release", "reroute_to_rag", "retry_generation", "human_review", "block"]
TraceStage = Literal["normalize", "evaluate", "decision"]
TraceStatus = Literal["passed", "applied"]


class SecondRouterSnapshot(BaseModel):
    route: RouteUsed
    needs_rag: bool
    confidence: Confidence = "medium"
    brief: str = ""
    reason_codes: list[str] = Field(default_factory=list)


class RagResult(BaseModel):
    answerable: bool
    answer: str = ""
    used_chunk_ids: list[str] = Field(default_factory=list)
    needs_human_review: bool = False
    warning: str | None = None
    retrieved_scores: list[float] = Field(default_factory=list)

    @field_validator("answer")
    @classmethod
    def normalize_answer(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("used_chunk_ids")
    @classmethod
    def deduplicate_chunk_ids(cls, value: list[str]) -> list[str]:
        deduped: list[str] = []
        for chunk_id in value:
            normalized = chunk_id.strip()
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped


class ServerLlmResult(BaseModel):
    answer: str = ""
    needs_human_review: bool = False
    mentioned_references: bool = False

    @field_validator("answer")
    @classmethod
    def normalize_answer(cls, value: str) -> str:
        return " ".join(value.split())


class FinalScoreInput(BaseModel):
    request_id: str | None = None
    original_question: str = Field(min_length=1)
    route_used: RouteUsed
    metadata: dict[str, Any] = Field(default_factory=dict)
    second_router: SecondRouterSnapshot | None = None
    rag_result: RagResult | None = None
    server_llm_result: ServerLlmResult | None = None

    @field_validator("original_question")
    @classmethod
    def normalize_original_question(cls, value: str) -> str:
        collapsed = " ".join(value.split())
        if not collapsed:
            raise ValueError("original_question must not be blank")
        return collapsed


class NormalizedFinalScoreInput(BaseModel):
    request_id: str
    original_question: str
    route_used: RouteUsed
    metadata: dict[str, Any] = Field(default_factory=dict)
    second_router: SecondRouterSnapshot | None = None
    rag_result: RagResult | None = None
    server_llm_result: ServerLlmResult | None = None


class ScoreBreakdown(BaseModel):
    routing_confidence: int
    evidence_quality: int
    safety: int
    answer_quality: int
    format_quality: int


class FinalScoreDecision(BaseModel):
    route_used: RouteUsed
    final_score: int
    action: Action
    reasons: list[str] = Field(default_factory=list)
    breakdown: ScoreBreakdown
    final_answer: str | None = None


class FinalScoreDisplay(BaseModel):
    final_score: int
    action: Action
    brief: str
    reasons: list[str] = Field(default_factory=list)


class HarnessTraceEntry(BaseModel):
    stage: TraceStage
    status: TraceStatus
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)


class FinalScoreCompactResult(BaseModel):
    display: FinalScoreDisplay
    decision: FinalScoreDecision


class FinalScoreResult(BaseModel):
    display: FinalScoreDisplay
    decision: FinalScoreDecision
    normalized_input: NormalizedFinalScoreInput
    trace: list[HarnessTraceEntry] = Field(default_factory=list)
