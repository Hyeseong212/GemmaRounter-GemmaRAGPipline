# Harness Engineering

This router now uses a minimal harness designed for `Gemma 4 E2B`.

## Design Goal

Do not ask the local model to produce a big medical routing schema.

Instead:

1. hard rules catch obvious and risky cases
2. the model returns only a tiny route choice
3. local code expands that into the final router decision
4. post-policies enforce the 20-character rule and offline behavior

## What Stayed

- input normalization
- signal extraction
- hard safety gates
- tiny model route choice
- post-policy override
- downstream handoff generation

## What Was Removed

- repair flow
- vision route from the small E2B router
- large model-emitted JSON contract
- extra routing branches that the local model did not need

## Current Flow

### 1. Normalize

Extract only the signals that matter for this router:

- error codes
- reference-grounding need
- short-answer expectation
- patient or medication risk
- image request
- network-limited mode

### 2. Hard Rules

Handle these without the model:

- medication, treatment, patient-risk requests
- override or bypass requests
- realtime status API requests
- obvious manual or error-code questions
- offline cached-help and limited-mode behavior
- image requests

### 3. Minimal Model Routing

For unresolved cases, Gemma returns only:

- `local_llm`
- `server_rag`
- `server_llm`
- `human_review`
- `block`

### 4. Post-Policy Checks

Even if the model picks a route, local policy can still fix it:

- `local_llm` is upgraded to `server_llm` if 20 characters is unrealistic
- `server_llm` or `server_rag` is downgraded in offline mode
- image or patient-risk requests are kept out of normal auto-answer paths

### 5. Handoff

The final output still carries a downstream execution contract for:

- local answer generation
- RAG reference lookup
- server large-model answering
- operator review
- block handling
