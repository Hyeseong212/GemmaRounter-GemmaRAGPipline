# Gemma Routing Project

This project is the Jetson-side router for your medical-device assistant.

It now includes a runnable Python service with:

- hard rules before the model call
- shared Gemma model invocation through an OpenAI-compatible endpoint
- strict router schema validation and repair flow
- conservative post-policy overrides and fallback to `human_review`
- general-question vs reference-question routing
- FastAPI and CLI entrypoints for local testing

## Purpose

- classify intent
- classify risk
- decide route
- keep local-LLM answers within a 20-character short-answer budget
- block unsafe requests
- emit a validated router decision

## Routing Goal

Use the router to answer one question first:

- Is this a short general question the local LLM can handle within 20 Korean characters?

Then decide:

- `local_rule_only` for deterministic local tool requests
- `local_llm` for short general replies that should stay within 20 Korean characters
- `server_rag` for reference-grounded questions
- `server_llm` for general questions likely to exceed the 20-character local budget
- `server_vision` for image-dependent questions
- `human_review` or `block` for unsafe categories

## Shared Model Policy

This project uses its own project wrapper scripts:

- run: [`scripts/run_local_gemma.sh`](/home/rb/AI/gemma-routing/scripts/run_local_gemma.sh)
- manage: [`scripts/manage_local_gemma.sh`](/home/rb/AI/gemma-routing/scripts/manage_local_gemma.sh)

Expected model alias:

- `gemma4-routing`

Recommended low-burst router defaults:

- `max_tokens=96`
- `reasoning=off`
- `reasoning_budget=0`
- text-only runtime with `--no-mmproj`

## Project Layout

- schema: [`docs/router-schema.md`](/home/rb/AI/gemma-routing/docs/router-schema.md)
- harness notes: [`docs/harness-engineering.md`](/home/rb/AI/gemma-routing/docs/harness-engineering.md)
- RAG reference analysis: [`../docs/rag-reference-analysis.md`](/home/rb/AI/docs/rag-reference-analysis.md)
- prompt: [`prompts/medical_router_system_prompt.txt`](/home/rb/AI/gemma-routing/prompts/medical_router_system_prompt.txt)
- raw Gemma request example: [`examples/medical_router_request.json`](/home/rb/AI/gemma-routing/examples/medical_router_request.json)
- router API request example: [`examples/router_api_request.json`](/home/rb/AI/gemma-routing/examples/router_api_request.json)
- local general example: [`examples/local_general_router_request.json`](/home/rb/AI/gemma-routing/examples/local_general_router_request.json)
- server general example: [`examples/server_general_router_request.json`](/home/rb/AI/gemma-routing/examples/server_general_router_request.json)
- package source: [`src/gemma_routing`](/home/rb/AI/gemma-routing/src/gemma_routing)
- tests: [`tests`](/home/rb/AI/gemma-routing/tests)

## Quick Start

1. Create a virtual environment.
2. Install the router package.
3. Start the shared Gemma server.
4. Run the router API or CLI.

Example:

```bash
cd /home/rb/AI/gemma-routing
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

If `python3 -m venv` is unavailable on the device:

```bash
cd /home/rb/AI/gemma-routing
python3 -m pip install --user -e '.[dev]'
cp .env.example .env
```

Start Gemma first:

```bash
/home/rb/AI/gemma-routing/scripts/run_local_gemma.sh e2b
```

Run the API:

```bash
source .venv/bin/activate
gemma-router-api
```

Then call it:

```bash
curl http://127.0.0.1:8090/route \
  -H 'Content-Type: application/json' \
  -d @/home/rb/AI/gemma-routing/examples/router_api_request.json
```

Run the CLI:

```bash
source .venv/bin/activate
gemma-router --message '장비 화면에 E103 에러가 떴어. 무슨 뜻이고 다음에 뭘 확인해야 해?'
```

## Harness Design

The router deliberately limits Gemma to a narrow job:

1. Hard rules run first for deterministic or forbidden categories.
2. Gemma only emits router JSON for the remaining cases.
3. Output is parsed, validated, and if needed repaired once through a constrained repair prompt.
4. Post-policy checks can still override unsafe or unexecutable routes.
5. The router emits a downstream handoff contract for `local_rule_only`, `local_llm`, `server_rag`, `server_llm`, `server_vision`, `human_review`, or `block`.

The API response is now a harness envelope:

- `normalized_input`: request plus extracted signals
- `decision_source`: `hard_rule`, `model`, `model_repair`, or `fallback`
- `decision`: validated router decision
- `handoff`: structured downstream execution contract
- `trace`: stage-by-stage harness audit trail

`server_vision` now emits an explicit InterVL 78B handoff contract instead of sending a loose prompt downstream.
`server_rag` is now framed as a handoff to the reference RAG pipeline, while general non-grounded questions can split into `local_llm` or `server_llm`.
`local_llm` is now treated as a strict short-answer path with a 20-character budget and overflow to `server_llm`.
