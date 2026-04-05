# GemmaRounter-GemmaRAGPipline

This workspace is split into two app projects that share a single Gemma runtime.

## Projects

- [`gemma-routing`](/home/rb/AI/gemma-routing): on-device routing, safety gate, structured JSON decisions
- [`gemma-rag`](/home/rb/AI/gemma-rag): RAG-side answer generation that consumes retrieved context

## Shared Runtime

Use one model service for both projects:

- launcher: [`scripts/run_gemma4_llama_server.sh`](/home/rb/AI/scripts/run_gemma4_llama_server.sh)
- setup guide: [`docs/jetson-orin-gemma4-setup.md`](/home/rb/AI/docs/jetson-orin-gemma4-setup.md)

Both projects should call the same local model alias:

- `gemma4-shared`

That means:

- only one Gemma model is downloaded and served
- routing and RAG clients use the same endpoint
- you can swap `E2B` and `E4B` behind the same alias without changing app code
