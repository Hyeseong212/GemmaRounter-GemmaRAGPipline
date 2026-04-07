# Server Router Schema

`gemma-ServerRouter` is the server-side RAG gate.

Its purpose is simple:

- decide whether a request needs retrieval grounding
- route to `server_rag` or `server_llm`

## Output Shape

The model returns a small JSON object:

```json
{
  "route": "server_rag | server_llm",
  "confidence": "high | medium | low",
  "summary_for_handoff": "short summary string",
  "retrieval_query": "string"
}
```

## Route Meaning

- `server_rag`
  - manuals, SOPs, error-code tables, specs, internal docs, project reference facts
- `server_llm`
  - general reasoning, explanation, comparison, brainstorming, rewriting, synthesis

## API

- `POST /route`
  - compact response for routing use
- `POST /route/debug`
  - full debug envelope with normalized input and trace

## Compact Response

```json
{
  "display": {
    "route": "server_rag",
    "needs_rag": true,
    "confidence": "high",
    "brief": "문서 근거가 필요해 RAG로 전달",
    "reason_codes": ["error_code_reference"]
  },
  "handoff": {
    "route": "server_rag",
    "target_system": "rag_reference_api",
    "task_type": "grounded_reference_lookup",
    "summary": "E103 에러 의미와 조치 질문",
    "required_inputs": ["user_message", "retrieved_context"],
    "metadata": {
      "needs_rag": true,
      "retrieval_query": "E103 에러 의미 조치"
    }
  }
}
```
