# Final Score

`final-score` is the last deterministic gate on the server.

It is designed to sit after:

1. `first-router`
2. `second-router`
3. `rag-answerer` or `server_large_llm`

Its job is to decide whether the candidate answer can be released, should be retried, should be rerouted to RAG, or should be escalated to human review.

## Why This Exists

- keep the last decision deterministic and auditable
- make the JSON contract easy to port to C++ later
- avoid relying on an LLM judge for the first production version

## Actions

- `release`
- `reroute_to_rag`
- `retry_generation`
- `human_review`
- `block`

## API

Score a final candidate:

```bash
curl http://127.0.0.1:8290/score \
  -H 'Content-Type: application/json' \
  -d @/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/final-score/examples/rag_release_request.json
```

Full debug envelope:

```bash
curl http://127.0.0.1:8290/score/debug \
  -H 'Content-Type: application/json' \
  -d @/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/final-score/examples/rag_release_request.json
```

## Input Contract

Required core fields:

- `original_question`
- `route_used`
- one of `rag_result` or `server_llm_result`

Optional context:

- `second_router`
- `metadata`

## Output Contract

The compact response returns:

- `display`
- `decision`

The debug response adds:

- `normalized_input`
- `trace`

## Current V1 Policy

- `server_rag` answers need chunk ids to be auto-released
- `server_rag` answers with `needs_human_review=true` never auto-release
- `server_llm` answers for reference-like questions are rerouted to RAG
- risky medical/treatment style wording is escalated
