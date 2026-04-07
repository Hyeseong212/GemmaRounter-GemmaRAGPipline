from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


Route = Literal["server_rag", "server_llm"]
Confidence = Literal["high", "medium", "low"]
DecisionSource = Literal["model", "fallback"]
TraceStage = Literal["normalize", "model", "fallback", "handoff"]
TraceStatus = Literal["passed", "generated", "applied", "failed"]
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
