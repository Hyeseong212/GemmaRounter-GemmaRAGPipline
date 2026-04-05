# Gemma RAG Project

This project is for the Gemma-facing part of a separate RAG pipeline.

## Purpose

- receive retrieved context from your retriever
- answer only from grounded context
- refuse unsupported claims
- return structured output if needed

## Shared Model Policy

This project also uses the same shared Gemma runtime:

- [`../scripts/run_gemma4_llama_server.sh`](/home/rb/AI/scripts/run_gemma4_llama_server.sh)

Expected model alias:

- `gemma4-shared`

## Files

- prompt: [`prompts/rag_answer_system_prompt.txt`](/home/rb/AI/gemma-rag/prompts/rag_answer_system_prompt.txt)
- request example: [`examples/rag_answer_request.json`](/home/rb/AI/gemma-rag/examples/rag_answer_request.json)
