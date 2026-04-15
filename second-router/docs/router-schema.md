# Server Router Schema

`second-router` is the server-side RAG gate.

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
- `POST /route/from-first-router`
  - use when the server receives the first router compact result from Jetson
- `POST /route/from-first-router/debug`
  - same as above, with the full debug envelope
- `POST /process/from-first-router`
  - thin adapter entrypoint: second routing plus downstream execution plus final-score
- `POST /process/from-first-router/debug`
  - same as above, with the full routing and score payload included

## First Router Input

Use this shape when forwarding the Jetson-side router result to the server:

```json
{
  "request_id": "server-router-bridge-001",
  "original_question": "장비 화면에 E103 에러가 떴어. 무슨 뜻이고 다음에 뭘 확인해야 해?",
  "metadata": {
    "locale": "ko-KR",
    "device_id": "demo-orin-01"
  },
  "first_router": {
    "display": {
      "route": "server_rag",
      "decision_source": "hard_rule",
      "brief": "문서 근거가 필요해 RAG로 전달",
      "target_system": "rag_reference_api",
      "reason_codes": ["needs_reference_grounding"]
    },
    "handoff": {
      "route": "server_rag",
      "target_system": "rag_reference_api",
      "task_type": "grounded_reference_lookup",
      "summary": "E103 에러 의미와 조치 질문",
      "required_inputs": ["user_message", "retrieved_context"],
      "metadata": {
        "request_id": "demo-router-001",
        "original_question": "장비 화면에 E103 에러가 떴어. 무슨 뜻이고 다음에 뭘 확인해야 해?"
      }
    }
  }
}
```

The server uses `original_question` first.
If it is missing, it falls back to `first_router.handoff.metadata.original_question` or `question`.

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

## Process Response

`POST /process/from-first-router` returns a compact server-side result:

```json
{
  "request_id": "server-router-bridge-001",
  "original_question": "장비 화면에 E103 에러가 떴어. 무슨 뜻이고 다음에 뭘 확인해야 해?",
  "second_route": {
    "route": "server_rag",
    "needs_rag": true,
    "confidence": "high",
    "brief": "문서 근거가 필요해 RAG로 전달",
    "reason_codes": ["error_code_reference"]
  },
  "execution": {
    "target_system": "rag_reference_api",
    "status": "completed",
    "answer": "먼저 케이블 체결 상태를 확인하세요.",
    "details": {}
  },
  "final_score": {
    "final_score": 82,
    "action": "release",
    "brief": "최종 점수 기준을 만족해 답변 출고",
    "reasons": [],
    "final_answer": "먼저 케이블 체결 상태를 확인하세요."
  },
  "final_answer": "먼저 케이블 체결 상태를 확인하세요."
}
```
