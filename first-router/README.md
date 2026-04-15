# Gemma Routing Project

This project is the Jetson-side minimal router for your medical-device assistant.

The current E2B-friendly design keeps the model job small:

- hard rules handle safety, status API, image requests, offline mode, and obvious reference questions
- Gemma only picks a small route choice for unresolved general questions
- post-policies enforce the 20-character local-answer rule
- the router emits a downstream handoff for local LLM, RAG, server LLM, or operator review
- the `/handle` endpoint now executes the local short answer when the final route is `local_llm`

## Purpose

- keep unsafe requests out of auto-answer paths
- send manual or error-code questions to RAG
- keep short robot-style replies on the local LLM
- send long general explanations to the server LLM

## Route Set

- `local_rule_only`
- `local_llm`
- `server_rag`
- `server_llm`
- `human_review`
- `block`

## Minimal Routing Rule

The router now answers one simple question for non-safety cases:

- Can this be answered locally in 20 Korean characters or less?

If yes, use `local_llm`.
If the question needs reference grounding, use `server_rag`.
If the answer will likely exceed 20 characters, use `server_llm`.

## What Uses The LLM

- hard rules decide many requests without any model call
- unresolved general questions are sent to the local Gemma router model for a tiny route choice
- if the final route is `local_llm`, the same local Gemma server is called again with a short-answer prompt
- if that generated answer exceeds 20 characters, the flow reroutes to `server_llm`

## Shared Model Policy

This project uses its own wrapper scripts:

- run: [`scripts/run_local_gemma.sh`](/home/rb/AI/first-router/scripts/run_local_gemma.sh)
- manage: [`scripts/manage_local_gemma.sh`](/home/rb/AI/first-router/scripts/manage_local_gemma.sh)

Expected model alias:

- `gemma4-routing`

Recommended local runtime defaults:

- `model_variant=e2b`
- `ctx_size=2048`
- `GPU_LAYERS=8`
- `BATCH_SIZE=128`
- `UBATCH_SIZE=32`
- `NO_KV_OFFLOAD=1`
- `NO_OP_OFFLOAD=1`

## Project Layout

- schema: [`docs/router-schema.md`](/home/rb/AI/first-router/docs/router-schema.md)
- harness notes: [`docs/harness-engineering.md`](/home/rb/AI/first-router/docs/harness-engineering.md)
- RAG reference analysis: [`../docs/rag-reference-analysis.md`](/home/rb/AI/docs/rag-reference-analysis.md)
- prompt: [`prompts/medical_router_system_prompt.txt`](/home/rb/AI/first-router/prompts/medical_router_system_prompt.txt)
- raw Gemma request example: [`examples/medical_router_request.json`](/home/rb/AI/first-router/examples/medical_router_request.json)
- router API request example: [`examples/router_api_request.json`](/home/rb/AI/first-router/examples/router_api_request.json)
- package source: [`src/gemma_routing`](/home/rb/AI/first-router/src/gemma_routing)
- tests: [`tests`](/home/rb/AI/first-router/tests)

## Quick Start

```bash
cd /home/rb/AI/first-router
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

Start the integrated stack:

```bash
/home/rb/AI/first-router/launch.sh
```

Test compact routing only:

```bash
curl http://127.0.0.1:8090/route \
  -H 'Content-Type: application/json' \
  -d @/home/rb/AI/first-router/examples/router_api_request.json
```

Run the full local execution flow:

```bash
curl http://127.0.0.1:8090/handle \
  -H 'Content-Type: application/json' \
  -d @/home/rb/AI/first-router/examples/local_general_router_request.json
```

If you need the full debug envelope with normalized input and trace:

```bash
curl http://127.0.0.1:8090/route/debug \
  -H 'Content-Type: application/json' \
  -d @/home/rb/AI/first-router/examples/router_api_request.json
```

## Harness Summary

1. Hard rules run first.
2. Gemma only returns a tiny route JSON for unresolved cases.
3. Post-policies enforce safety and the 20-character local limit.
4. The router builds the downstream handoff contract.
5. `/handle` executes the local short answer only when the route is `local_llm`.

The full debug response still includes:

- `normalized_input`
- `decision_source`
- `decision`
- `handoff`
- `trace`

The standard `/route` endpoint returns only the short routing view:

- `display`
- `handoff`

The `/handle` endpoint returns the same compact routing view plus:

- `execution`

## Server Forwarding Note

If the final route is `server_rag` or `server_llm`, this router does not automatically post to the server.
The caller should forward:

- the original user question
- the first router compact result

The server-side bridge endpoint is `POST /route/from-first-router`.

The server-bound handoff metadata now carries:

- `request_id`
- `question`
- `original_question`
