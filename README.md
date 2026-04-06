# GemmaRouter-GemmaRAGPipline

This workspace is split into three app projects.

## Projects

- [`gemma-routing`](/home/rb/AI/gemma-routing): on-device routing that splits deterministic local, 20-char local LLM, RAG, and server LLM paths
- [`gemma-rag`](/home/rb/AI/gemma-rag): RAG-side answer generation that consumes retrieved context
- [`gemma-tranferRobotLLM`](/home/rb/AI/gemma-tranferRobotLLM): transfer-robot local LLM for STT correction, reply generation, and TTS-ready text

## Runtime

Each project can run its own local Gemma server script:

- [`gemma-routing/scripts/manage_local_gemma.sh`](/home/rb/AI/gemma-routing/scripts/manage_local_gemma.sh)
- [`gemma-rag/scripts/manage_local_gemma.sh`](/home/rb/AI/gemma-rag/scripts/manage_local_gemma.sh)
- [`gemma-tranferRobotLLM/scripts/manage_local_gemma.sh`](/home/rb/AI/gemma-tranferRobotLLM/scripts/manage_local_gemma.sh)

Shared base scripts still exist under [`shared-scripts`](/home/rb/AI/shared-scripts), but day-to-day start and stop should be done from each project wrapper.
