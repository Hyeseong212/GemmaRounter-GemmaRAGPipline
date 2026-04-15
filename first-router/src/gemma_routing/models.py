from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


Intent = Literal[
    "device_status_question",
    "device_error_question",
    "manual_procedure_question",
    "general_question",
    "clinical_risk_question",
    "medication_advice_request",
    "contraindication_override_request",
    "unknown",
]

RiskLevel = Literal["low", "medium", "high", "forbidden"]
Route = Literal[
    "local_rule_only",
    "local_llm",
    "server_rag",
    "server_llm",
    "human_review",
    "block",
]
Priority = Literal["normal", "high", "critical"]
NetworkStatus = Literal["online", "degraded", "offline"]
DecisionSource = Literal["hard_rule", "model", "fallback", "local_execution"]
TraceStage = Literal["normalize", "hard_rule", "model", "post_policy", "handoff", "fallback"]
TraceStatus = Literal["passed", "applied", "generated", "overridden", "failed"]
LocalAction = Literal[
    "none",
    "respond_with_device_api",
    "answer_with_local_llm",
    "show_cached_error_help",
    "show_limited_mode_notice",
    "handoff_to_operator",
    "block_and_warn",
]
ReasonCode = Literal[
    "local_status_available",
    "needs_reference_grounding",
    "local_general_answer_ok",
    "needs_large_model_reasoning",
    "local_answer_overflow",
    "local_generation_failed",
    "patient_specific_clinical_judgment",
    "medication_or_treatment_change",
    "contraindication_override",
    "unsafe_override_request",
    "requires_operator_confirmation",
    "network_limited_mode",
    "unknown_request_type",
]


class RouterInput(BaseModel):
    request_id: str | None = None
    user_message: str = Field(min_length=1, description="Raw user message to route.")
    has_image: bool = False
    network_status: NetworkStatus = "online"
    local_tools_available: list[str] = Field(
        default_factory=lambda: ["device_status_api", "cached_error_help"]
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_message")
    @classmethod
    def normalize_user_message(cls, value: str) -> str:
        collapsed = " ".join(value.split())
        if not collapsed:
            raise ValueError("user_message must not be blank")
        return collapsed

    @field_validator("local_tools_available")
    @classmethod
    def deduplicate_local_tools(cls, value: list[str]) -> list[str]:
        deduped: list[str] = []
        for tool in value:
            if tool and tool not in deduped:
                deduped.append(tool)
        return deduped


class DetectedSignals(BaseModel):
    error_codes: list[str] = Field(default_factory=list)
    patient_related: bool = False
    medication_related: bool = False
    treatment_related: bool = False
    override_related: bool = False
    visual_related: bool = False
    status_related: bool = False
    general_question_candidate: bool = False
    complex_reasoning_requested: bool = False
    short_answer_expected: bool = False
    reference_grounding_required: bool = False
    network_limited: bool = False

    @field_validator("error_codes")
    @classmethod
    def deduplicate_error_codes(cls, value: list[str]) -> list[str]:
        deduped: list[str] = []
        for code in value:
            upper_code = code.upper()
            if upper_code not in deduped:
                deduped.append(upper_code)
        return deduped


class NormalizedRouterInput(BaseModel):
    request_id: str
    user_message: str
    has_image: bool = False
    network_status: NetworkStatus = "online"
    local_tools_available: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    detected_signals: DetectedSignals


class RouterDecision(BaseModel):
    intent: Intent
    risk_level: RiskLevel
    route: Route
    needs_human_review: bool
    patient_related: bool
    priority: Priority
    required_tools: list[str] = Field(default_factory=list)
    reason_codes: list[ReasonCode]
    summary_for_server: str
    local_action: LocalAction

    @field_validator("required_tools")
    @classmethod
    def deduplicate_required_tools(cls, value: list[str]) -> list[str]:
        deduped: list[str] = []
        for tool in value:
            if tool and tool not in deduped:
                deduped.append(tool)
        return deduped

    @field_validator("summary_for_server")
    @classmethod
    def trim_summary(cls, value: str) -> str:
        return " ".join(value.split())[:240]


class HarnessTraceEntry(BaseModel):
    stage: TraceStage
    status: TraceStatus
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)


class DownstreamHandoff(BaseModel):
    route: Route
    target_system: str
    task_type: str
    summary: str
    instructions: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    must_extract: list[str] = Field(default_factory=list)
    must_not_do: list[str] = Field(default_factory=list)
    escalation_triggers: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouterDisplay(BaseModel):
    route: Route
    decision_source: DecisionSource
    brief: str
    target_system: str
    reason_codes: list[ReasonCode] = Field(default_factory=list)


class CompactHandoff(BaseModel):
    route: Route
    target_system: str
    task_type: str
    summary: str
    required_inputs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouterCompactResult(BaseModel):
    display: RouterDisplay
    handoff: CompactHandoff


class LocalExecutionResult(BaseModel):
    mode: Literal["local_llm"]
    status: Literal["completed", "rerouted"]
    answer: str | None = None
    answer_char_count: int | None = None
    reason: str
    rerouted_to: Route | None = None


class RouterHandledResult(BaseModel):
    display: RouterDisplay
    handoff: CompactHandoff
    execution: LocalExecutionResult | None = None


class RouterResult(BaseModel):
    display: RouterDisplay
    decision_source: DecisionSource
    decision: RouterDecision
    handoff: DownstreamHandoff | None = None
    normalized_input: NormalizedRouterInput
    trace: list[HarnessTraceEntry] = Field(default_factory=list)


ModelRoute = Literal["local_llm", "server_rag", "server_llm", "human_review", "block"]


class ModelRouteChoice(BaseModel):
    route: ModelRoute
    summary_for_server: str = ""

    @field_validator("summary_for_server")
    @classmethod
    def trim_summary(cls, value: str) -> str:
        return " ".join(value.split())[:240]
