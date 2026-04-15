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

- run: [`scripts/run_local_gemma.sh`](/home/rb/AI/rag-answerer/scripts/run_local_gemma.sh)
- manage: [`scripts/manage_local_gemma.sh`](/home/rb/AI/rag-answerer/scripts/manage_local_gemma.sh)

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

- env profile: [`config/korean_medical_device_rag.env`](/home/rb/AI/rag-answerer/config/korean_medical_device_rag.env)
- integration notes: [`docs/korean-medical-device-rag-profile.md`](/home/rb/AI/rag-answerer/docs/korean-medical-device-rag-profile.md)

Quick inspect:

```bash
/home/rb/AI/rag-answerer/launch.sh profile
```

Why this profile:

- Korean-only retrieval performs better with `KURE-v1` than a general multilingual default.
- Medical-device manuals, IFUs, warnings, tables, and error codes benefit from hybrid retrieval instead of dense-only search.
- A reranker helps suppress semantically similar but operationally wrong chunks.

## Files

- prompt: [`prompts/rag_answer_system_prompt.txt`](/home/rb/AI/rag-answerer/prompts/rag_answer_system_prompt.txt)
- request example: [`examples/rag_answer_request.json`](/home/rb/AI/rag-answerer/examples/rag_answer_request.json)
- retrieval profile: [`config/korean_medical_device_rag.env`](/home/rb/AI/rag-answerer/config/korean_medical_device_rag.env)
- retrieval notes: [`docs/korean-medical-device-rag-profile.md`](/home/rb/AI/rag-answerer/docs/korean-medical-device-rag-profile.md)
- public test corpus: [`test-corpus/mfds-korean-medical-device/README.md`](/home/rb/AI/rag-answerer/test-corpus/mfds-korean-medical-device/README.md)
- indexing guide: [`docs/indexing-starter-corpus.md`](/home/rb/AI/rag-answerer/docs/indexing-starter-corpus.md)
- Jetson flow doc: [`docs/jetson-rag-flow-explained.md`](/home/rb/AI/rag-answerer/docs/jetson-rag-flow-explained.md)
- Jetson flow docx: [`docs/jetson-rag-flow-explained.docx`](/home/rb/AI/rag-answerer/docs/jetson-rag-flow-explained.docx)

## Jetson Notes

What we confirmed on this Jetson Orin setup:

- `e2b` currently maps to `Q8_0`, and this profile failed to start on GPU due to CUDA OOM.
- `e4b-q4` did start on GPU, but throttling was observed under sustained load.
- Because of that, the current evaluation flow tries `e2b` on GPU first and then falls back to CPU if startup fails.

Relevant files:

- evaluator launcher: [`launch-eval.sh`](/home/rb/AI/rag-answerer/launch-eval.sh)
- evaluator script: [`scripts/evaluate_rag_answers.py`](/home/rb/AI/rag-answerer/scripts/evaluate_rag_answers.py)
- explained flow document: [`docs/jetson-rag-flow-explained.md`](/home/rb/AI/rag-answerer/docs/jetson-rag-flow-explained.md)

Current compact 10-question evaluation summary:

- average score: `6.0 / 10`
- strongest area: direct fact lookup
- weakest area: complete JSON output and citation stability
