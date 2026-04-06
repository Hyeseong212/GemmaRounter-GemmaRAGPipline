# Harness Engineering

This document describes the full router harness that wraps Gemma instead of letting the model directly control the whole pipeline.

## Design Goal

Gemma should make a narrow structured routing decision.

The harness around Gemma is responsible for:

- input normalization
- signal extraction
- hard policy gates
- output validation
- repair on malformed output
- post-policy safety overrides
- downstream handoff contract generation

## Stages

### 1. Normalize

The router converts the raw request into a normalized request envelope and extracts signals such as:

- error codes
- reference-grounding need
- general-question candidacy
- complex reasoning request
- short-answer expectation under 20 characters
- patient-related language
- medication or treatment language
- override attempts
- image or screenshot presence
- local-only status queries
- network-limited mode

### 2. Hard Rules

Before Gemma runs, deterministic and high-risk categories are intercepted:

- medication advice
- treatment-change questions
- patient-specific risk interpretation
- local status API requests
- offline cached error help
- attached-image vision triage

### 3. Model Routing

Gemma is only asked to output the strict router JSON contract. It does not answer the user.

The core routing split is now:

- deterministic local rule
- local LLM general answer
- server RAG grounded answer
- server large-model general answer
- server vision
- human review
- block

### 4. Repair

If Gemma returns malformed JSON or invalid enum values, the harness sends the invalid output into a constrained repair prompt once. If repair still fails, the harness falls back to `human_review`.

### 5. Post-Policy Override

Even valid model output can be overridden if it violates execution policy, for example:

- patient-specific content routed to a normal answer path
- `server_llm` chosen while the network is degraded or offline
- `server_rag` chosen while the network is degraded or offline
- `server_vision` chosen without an actual image attachment
- `local_rule_only` chosen while the required local tool is unavailable

### 6. Downstream Handoff

The final result includes a structured handoff contract.

For `server_rag`, the contract is designed around the current reference RAG API:

- `POST /ask`
- request key `question`
- response key `answer`

For `local_llm`, the contract is intentionally short-answer and low-latency.
The local path should only be used when the expected reply fits within 20 Korean characters.

For `server_vision`, the contract is designed for `InterVL 78B` and explicitly includes:

- target system
- task type
- required inputs
- required extraction fields
- banned behaviors
- escalation triggers

This keeps `InterVL 78B` acting as a visual extractor and triage specialist instead of a free-form final answer model.
