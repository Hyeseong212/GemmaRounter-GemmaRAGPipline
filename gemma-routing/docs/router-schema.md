# Router Schema

This is the recommended v1 schema for the Jetson-side Gemma router.

The base design follows your intended behavior:

- Jetson does not generate the full answer
- Jetson decides where the request should go
- unsafe requests are blocked or escalated before the main server path

## Why This Schema Is Good

Your current route design is already the right backbone:

- `local_rule_only`
- `server_rag`
- `server_vision`
- `human_review`
- `block`

That is enough to start.

## What I Recommend Adding

Add only these two fields beyond the core routing fields:

1. `reason_codes`
   - machine-readable explanation for why the route was chosen
   - better than relying only on free-text `reason`
   - useful for logs, analytics, dashboards, and deterministic downstream handling

2. `priority`
   - useful for alarm-driven device workflows
   - helps the server or operator queue requests

I do **not** recommend adding model `confidence` in v1.
For medical-device routing, confidence is often noisy and easy to over-trust.

## Final Recommended v1 Shape

```json
{
  "intent": "string",
  "risk_level": "low | medium | high | forbidden",
  "route": "local_rule_only | server_rag | server_vision | human_review | block",
  "needs_human_review": false,
  "patient_related": false,
  "priority": "normal | high | critical",
  "required_tools": ["string"],
  "reason_codes": ["string"],
  "summary_for_server": "string",
  "local_action": "string"
}
```

## Field Notes

### `intent`

Keep this to a small fixed set at first:

- `device_status_question`
- `device_error_question`
- `device_usage_question`
- `manual_procedure_question`
- `ui_screen_question`
- `clinical_risk_question`
- `treatment_change_request`
- `medication_advice_request`
- `contraindication_override_request`
- `unknown`

### `risk_level`

- `low`: informational or deterministic device questions
- `medium`: non-clinical but requires grounding or careful handling
- `high`: clinically risky or operator-sensitive
- `forbidden`: should not be answered by the system

### `route`

- `local_rule_only`: answer with local device API, cached SOP, or deterministic rule
- `server_rag`: send to the 5090 RAG path
- `server_vision`: send to the vision specialist path
- `human_review`: stop automated answering and ask for clinician/operator review
- `block`: refuse and do not continue

### `priority`

- `normal`: standard request
- `high`: important but not immediately critical
- `critical`: alarm-like, urgent, or operator-immediate handling needed

### `reason_codes`

Recommended starting codes:

- `local_status_available`
- `needs_manual_grounding`
- `needs_visual_inspection`
- `patient_specific_clinical_judgment`
- `medication_or_treatment_change`
- `contraindication_override`
- `unsafe_override_request`
- `requires_operator_confirmation`
- `network_limited_mode`
- `unknown_request_type`

### `local_action`

Keep this deterministic and implementation-friendly:

- `none`
- `respond_with_device_api`
- `show_cached_error_help`
- `show_limited_mode_notice`
- `handoff_to_operator`
- `block_and_warn`

## Example A

Input:

`에러코드 E210이 떴어. 어떻게 해야 해?`

```json
{
  "intent": "device_error_question",
  "risk_level": "medium",
  "route": "server_rag",
  "needs_human_review": false,
  "patient_related": false,
  "priority": "high",
  "required_tools": ["error_code_lookup", "manual_retrieval"],
  "reason_codes": ["needs_manual_grounding"],
  "summary_for_server": "사용자가 에러코드 E210의 의미와 조치 방법을 문의함",
  "local_action": "none"
}
```

## Example B

Input:

`환자 맥박이 이 정도면 계속 써도 돼?`

```json
{
  "intent": "clinical_risk_question",
  "risk_level": "high",
  "route": "human_review",
  "needs_human_review": true,
  "patient_related": true,
  "priority": "critical",
  "required_tools": [],
  "reason_codes": ["patient_specific_clinical_judgment", "requires_operator_confirmation"],
  "summary_for_server": "환자 상태 기반 사용 지속 가능 여부를 묻는 임상 판단 질문",
  "local_action": "handoff_to_operator"
}
```

## Example C

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

## Implementation Notes

Recommended execution order:

1. Hard rules first
2. Gemma router second
3. Route dispatcher third

Hard rules should handle things like:

- network offline or degraded mode
- hard-blocked phrases or policy categories
- deterministic device APIs
- obvious PHI or sensitive-input handling

## Recommendation

This schema is good enough to move forward now.

If you want to stay disciplined for v1:

- keep exactly 5 routes
- keep the intent list small
- add only `reason_codes` and `priority`
- avoid confidence scores
- avoid letting the router generate long natural-language answers
