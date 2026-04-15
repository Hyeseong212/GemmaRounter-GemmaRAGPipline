# Router Schema

This is the simplified router shape for the E2B local model.

## Main Idea

Let hard rules do most of the work.

Use the local model only for unresolved general questions, and keep its output tiny.

## Hard-Rule First

These cases are handled before the model runs:

- medication or treatment questions
- patient-specific risk questions
- unsafe override requests
- realtime device status questions
- image or screenshot requests
- obvious reference-grounded questions
- offline fallback paths

## Model Output Shape

The model no longer emits the full router decision.

It emits only:

```json
{
  "route": "local_llm | server_rag | server_llm | human_review | block",
  "summary_for_server": "short summary string"
}
```

## Final Router Decision

The service converts that tiny model output into the full validated router decision:

```json
{
  "intent": "string",
  "risk_level": "low | medium | high | forbidden",
  "route": "local_rule_only | local_llm | server_rag | server_llm | human_review | block",
  "needs_human_review": false,
  "patient_related": false,
  "priority": "normal | high | critical",
  "required_tools": ["string"],
  "reason_codes": ["string"],
  "summary_for_server": "string",
  "local_action": "string"
}
```

## Route Meaning

- `local_rule_only`: deterministic local tool or limited-mode notice
- `local_llm`: short general answer on device, capped at 20 Korean characters
- `server_rag`: grounded answer from manuals, SOPs, or error-code reference docs
- `server_llm`: general answer from the server large model
- `human_review`: operator review required
- `block`: unsafe request refusal

## Examples

Short local answer:

```json
{
  "route": "local_llm",
  "summary_for_server": ""
}
```

Reference question:

```json
{
  "route": "server_rag",
  "summary_for_server": "사용자가 E103 의미와 점검 항목을 물음"
}
```

Long general question:

```json
{
  "route": "server_llm",
  "summary_for_server": "사용자가 장비 방식 비교 설명을 요청함"
}
```

## RAG Contract

The current reference pipeline under [`../rag-reference-api-legacy`](/home/rb/AI/rag-reference-api-legacy) expects:

- endpoint: `POST /ask`
- request JSON: `{"question": "..."}`
- response JSON: `{"answer": "..."}`

## Local Answer Budget

`local_llm` is only for short reply generation.

- target budget: 20 Korean characters or less
- if the reply is likely to exceed 20 characters, reroute to `server_llm`

## API Split

- `POST /route`: compact routing result only
- `POST /route/debug`: full routing debug envelope
- `POST /handle`: routing plus local short-answer execution when the route is `local_llm`
