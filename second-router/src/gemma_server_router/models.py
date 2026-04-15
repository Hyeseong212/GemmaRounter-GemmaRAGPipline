from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


Route = Literal["server_rag", "server_llm"]
Confidence = Literal["high", "medium", "low"]
DecisionSource = Literal["model", "fallback"]
TraceStage = Literal["normalize", "model", "fallback", "handoff"]
TraceStatus = Literal["passed", "generated", "applied", "failed"]
ExecutionStatus = Literal["completed", "failed"]
ExecutionTarget = Literal["rag_reference_api", "server_large_llm"]
FirstRouterRoute = Literal[
    "local_rule_only",
    "local_llm",
    "server_rag",
    "server_llm",
    "human_review",
    "block",
]
FirstRouterDecisionSource = Literal["hard_rule", "model", "fallback", "local_execution"]
ReasonCode = Literal[
    "error_code_reference",
    "manual_or_sop_reference",
    "spec_or_policy_reference",
    "organization_specific_reference",
    "general_reasoning_ok",
    "fallback_reference_bias",
    "fallback_general_reasoning",
]


class ServerRouterInput(BaseModel):
    request_id: str | None = None
    user_message: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_message")
    @classmethod
    def normalize_user_message(cls, value: str) -> str:
        collapsed = " ".join(value.split())
        if not collapsed:
            raise ValueError("user_message must not be blank")
        return collapsed


class FirstRouterDisplay(BaseModel):
    route: FirstRouterRoute
    decision_source: FirstRouterDecisionSource
    brief: str
    target_system: str
    reason_codes: list[str] = Field(default_factory=list)


class FirstRouterHandoff(BaseModel):
    route: FirstRouterRoute
    target_system: str
    task_type: str
    summary: str
    required_inputs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FirstRouterCompactResult(BaseModel):
    display: FirstRouterDisplay
    handoff: FirstRouterHandoff


class ServerRouterFromFirstRouterInput(BaseModel):
    request_id: str | None = None
    original_question: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    first_router: FirstRouterCompactResult

    @field_validator("original_question")
    @classmethod
    def normalize_original_question(cls, value: str | None) -> str | None:
        if value is None:
            return None
        collapsed = " ".join(value.split())
        return collapsed or None


class DetectedSignals(BaseModel):
    error_codes: list[str] = Field(default_factory=list)
    asks_manual_or_sop: bool = False
    asks_error_meaning: bool = False
    asks_steps_or_procedure: bool = False
    asks_specs_or_policy: bool = False
    organization_specific: bool = False
    reference_grounding_likely: bool = False
    open_ended_reasoning: bool = False

    @field_validator("error_codes")
    @classmethod
    def deduplicate_error_codes(cls, value: list[str]) -> list[str]:
        deduped: list[str] = []
        for code in value:
            upper_code = code.upper()
            if upper_code not in deduped:
                deduped.append(upper_code)
        return deduped


class NormalizedServerRouterInput(BaseModel):
    request_id: str
    user_message: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    detected_signals: DetectedSignals


class ServerRouterDecision(BaseModel):
    route: Route
    needs_rag: bool
    confidence: Confidence
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    summary_for_handoff: str
    retrieval_query: str = ""

    @field_validator("summary_for_handoff")
    @classmethod
    def trim_summary(cls, value: str) -> str:
        return " ".join(value.split())[:240]

    @field_validator("retrieval_query")
    @classmethod
    def trim_retrieval_query(cls, value: str) -> str:
        return " ".join(value.split())[:240]


class HarnessTraceEntry(BaseModel):
    stage: TraceStage
    status: TraceStatus
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)


class ServerRouterDisplay(BaseModel):
    route: Route
    needs_rag: bool
    confidence: Confidence
    brief: str
    reason_codes: list[ReasonCode] = Field(default_factory=list)


class DownstreamHandoff(BaseModel):
    route: Route
    target_system: str
    task_type: str
    summary: str
    required_inputs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServerRouterCompactResult(BaseModel):
    display: ServerRouterDisplay
    handoff: DownstreamHandoff


class ServerRouterResult(BaseModel):
    display: ServerRouterDisplay
    decision_source: DecisionSource
    decision: ServerRouterDecision
    handoff: DownstreamHandoff
    normalized_input: NormalizedServerRouterInput
    trace: list[HarnessTraceEntry] = Field(default_factory=list)


class ProcessExecutionResult(BaseModel):
    target_system: ExecutionTarget
    status: ExecutionStatus
    answer: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class FinalScoreSnapshot(BaseModel):
    final_score: int
    action: str
    brief: str
    reasons: list[str] = Field(default_factory=list)
    final_answer: str | None = None


class ServerProcessCompactResult(BaseModel):
    request_id: str
    original_question: str
    second_route: ServerRouterDisplay
    execution: ProcessExecutionResult
    final_score: FinalScoreSnapshot
    final_answer: str | None = None


class ServerProcessResult(BaseModel):
    request_id: str
    original_question: str
    routing: ServerRouterResult
    execution: ProcessExecutionResult
    final_score: FinalScoreSnapshot
    score_payload: dict[str, Any] = Field(default_factory=dict)
    final_answer: str | None = None


class ModelRouteChoice(BaseModel):
    route: Route
    confidence: Confidence = "medium"
    summary_for_handoff: str = ""
    retrieval_query: str = ""

    @field_validator("summary_for_handoff")
    @classmethod
    def trim_summary(cls, value: str) -> str:
        return " ".join(value.split())[:240]

    @field_validator("retrieval_query")
    @classmethod
    def trim_retrieval_query(cls, value: str) -> str:
        return " ".join(value.split())[:240]
