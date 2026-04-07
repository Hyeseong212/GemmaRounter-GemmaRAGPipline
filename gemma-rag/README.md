# Gemma RAG Project

This project is for the Gemma-facing answer-generator part of a separate RAG pipeline.

## Purpose

- receive retrieved context from your retriever
- answer only from grounded context
- refuse unsupported claims
- return structured output if needed

This project does not own the retriever runtime itself.
It now includes a retrieval profile for the upstream Korean medical-device RAG stack that should feed this generator.

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

## Korean Medical-Device Retrieval Profile

Recommended upstream retrieval stack:

- dense retriever: `mykor/KURE-v1`
- sparse retriever: `BM25`
- fusion: `RRF`
- reranker: `BAAI/bge-reranker-v2-m3`

Profile files:

- env profile: [`config/korean_medical_device_rag.env`](/home/rb/AI/gemma-rag/config/korean_medical_device_rag.env)
- integration notes: [`docs/korean-medical-device-rag-profile.md`](/home/rb/AI/gemma-rag/docs/korean-medical-device-rag-profile.md)

Quick inspect:

```bash
/home/rb/AI/gemma-rag/launch.sh profile
```

Why this profile:

- Korean-only retrieval performs better with `KURE-v1` than a general multilingual default.
- Medical-device manuals, IFUs, warnings, tables, and error codes benefit from hybrid retrieval instead of dense-only search.
- A reranker helps suppress semantically similar but operationally wrong chunks.

## Files

- prompt: [`prompts/rag_answer_system_prompt.txt`](/home/rb/AI/gemma-rag/prompts/rag_answer_system_prompt.txt)
- request example: [`examples/rag_answer_request.json`](/home/rb/AI/gemma-rag/examples/rag_answer_request.json)
- retrieval profile: [`config/korean_medical_device_rag.env`](/home/rb/AI/gemma-rag/config/korean_medical_device_rag.env)
- retrieval notes: [`docs/korean-medical-device-rag-profile.md`](/home/rb/AI/gemma-rag/docs/korean-medical-device-rag-profile.md)
- public test corpus: [`test-corpus/mfds-korean-medical-device/README.md`](/home/rb/AI/gemma-rag/test-corpus/mfds-korean-medical-device/README.md)
