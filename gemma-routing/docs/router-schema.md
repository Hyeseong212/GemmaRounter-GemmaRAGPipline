# Router Schema

This is the recommended v2 schema for the Jetson-side Gemma router.

The main routing question is now:

1. Is this a general question or a reference-grounded question?
2. If it is general, can the local LLM answer it within 20 Korean characters?
3. If not, should it go to the server large model?

Safety gating still stays above all of that.

## Route Set

Use these routes:

- `local_rule_only`
- `local_llm`
- `server_rag`
- `server_llm`
- `server_vision`
- `human_review`
- `block`

## Final Recommended Shape

```json
{
  "intent": "string",
  "risk_level": "low | medium | high | forbidden",
  "route": "local_rule_only | local_llm | server_rag | server_llm | server_vision | human_review | block",
  "needs_human_review": false,
  "patient_related": false,
  "priority": "normal | high | critical",
  "required_tools": ["string"],
  "reason_codes": ["string"],
  "summary_for_server": "string",
  "local_action": "string"
}
```

## Intent Values

- `device_status_question`
- `device_error_question`
- `device_usage_question`
- `manual_procedure_question`
- `ui_screen_question`
- `general_question`
- `general_reasoning_question`
- `clinical_risk_question`
- `treatment_change_request`
- `medication_advice_request`
- `contraindication_override_request`
- `unknown`

## Route Meaning

- `local_rule_only`: deterministic local tool or cached local response
- `local_llm`: short general answer with the on-device LLM, capped at 20 Korean characters
- `server_rag`: grounded answer from the RAG/reference pipeline
- `server_llm`: general answer from the large server model without RAG
- `server_vision`: image or screen understanding path
- `human_review`: operator or clinician review required
- `block`: unsafe request refusal

## Reason Codes

- `local_status_available`
- `needs_reference_grounding`
- `needs_visual_inspection`
- `local_general_answer_ok`
- `needs_large_model_reasoning`
- `patient_specific_clinical_judgment`
- `medication_or_treatment_change`
- `contraindication_override`
- `unsafe_override_request`
- `requires_operator_confirmation`
- `network_limited_mode`
- `unknown_request_type`

## Local Action Values

- `none`
- `respond_with_device_api`
- `answer_with_local_llm`
- `show_cached_error_help`
- `show_limited_mode_notice`
- `handoff_to_operator`
- `block_and_warn`

## Decision Rules

### 1. Deterministic local path

If the request is a device status question and a local API can answer it, use `local_rule_only`.

### 2. Reference-grounded path

If the request needs manuals, SOPs, error-code references, or retrieved document evidence, use `server_rag`.

### 3. General local answer path

If the request is general, non-clinical, non-grounded, and the expected answer can stay within 20 Korean characters, use `local_llm`.

### 4. General server answer path

If the request is general but likely needs stronger reasoning, longer synthesis, or an answer longer than 20 Korean characters, use `server_llm`.

### 5. Safety-first path

If the request touches medication, treatment, contraindication override, or patient-specific risk interpretation, escalate to `human_review` or `block`.

## Example A

Input:

`배터리 상태 보여줘`

```json
{
  "intent": "device_status_question",
  "risk_level": "low",
  "route": "local_rule_only",
  "needs_human_review": false,
  "patient_related": false,
  "priority": "normal",
  "required_tools": ["device_status_api"],
  "reason_codes": ["local_status_available"],
  "summary_for_server": "",
  "local_action": "respond_with_device_api"
}
```

## Example B

Input:

`20자 이내로 출발 안내 멘트 만들어줘`

```json
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
```

## Example C

Input:

`장비 화면에 E103 에러가 떴어. 무슨 뜻이고 다음에 뭘 확인해야 해?`

```json
{
  "intent": "device_error_question",
  "risk_level": "medium",
  "route": "server_rag",
  "needs_human_review": false,
  "patient_related": false,
  "priority": "high",
  "required_tools": ["manual_retrieval"],
  "reason_codes": ["needs_reference_grounding"],
  "summary_for_server": "사용자가 에러코드 E103의 의미와 다음 점검 항목을 문의함",
  "local_action": "none"
}
```

## Example D

Input:

`이 장비 방식이 기존 방식이랑 어떤 차이가 있고 운영상 장단점이 뭐야?`

```json
{
  "intent": "general_reasoning_question",
  "risk_level": "low",
  "route": "server_llm",
  "needs_human_review": false,
  "patient_related": false,
  "priority": "normal",
  "required_tools": ["server_large_llm"],
  "reason_codes": ["needs_large_model_reasoning"],
  "summary_for_server": "사용자가 장비 방식 비교와 운영상 장단점 설명을 요청함",
  "local_action": "none"
}
```

## RAG Contract

The current reference RAG pipeline under [`../RAG-reference-scripts`](/home/rb/AI/RAG-reference-scripts) expects:

- endpoint: `POST /ask`
- request JSON: `{"question": "..."}`
- response JSON: `{"answer": "..."}`

The router should treat that path as grounded reference lookup, not general free-form QA.

## Local Answer Budget

`local_llm` is not the general default answerer.

Treat it as:

- short reply only
- target budget: 20 Korean characters or less
- if the local answer is likely to exceed that budget, reroute to `server_llm`
