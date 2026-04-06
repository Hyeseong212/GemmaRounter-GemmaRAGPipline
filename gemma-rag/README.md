# Gemma RAG Project

This project is for the Gemma-facing part of a separate RAG pipeline.

## Purpose

- receive retrieved context from your retriever
- answer only from grounded context
- refuse unsupported claims
- return structured output if needed

## Shared Model Policy

This project uses its own project wrapper scripts:

- run: [`scripts/run_local_gemma.sh`](/home/rb/AI/gemma-rag/scripts/run_local_gemma.sh)
- manage: [`scripts/manage_local_gemma.sh`](/home/rb/AI/gemma-rag/scripts/manage_local_gemma.sh)

Expected model alias:

- `gemma4-rag`

Default runtime profile:

- `e2b`
- `ctx 4096`
- `batch 128`
- `ubatch 32`
- GPU enabled
- GPU layers `8`
- KV offload disabled
- op offload disabled

## Files

- prompt: [`prompts/rag_answer_system_prompt.txt`](/home/rb/AI/gemma-rag/prompts/rag_answer_system_prompt.txt)
- request example: [`examples/rag_answer_request.json`](/home/rb/AI/gemma-rag/examples/rag_answer_request.json)
