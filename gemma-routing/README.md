# Gemma Routing Project

This project is for the Jetson-side router.

## Purpose

- classify intent
- classify risk
- decide route
- block unsafe requests
- emit JSON only

## Shared Model Policy

This project does not own a separate model download.

It uses the shared Gemma runtime from:

- [`../scripts/run_gemma4_llama_server.sh`](/home/rb/AI/scripts/run_gemma4_llama_server.sh)

Expected model alias:

- `gemma4-shared`

## Files

- schema: [`docs/router-schema.md`](/home/rb/AI/gemma-routing/docs/router-schema.md)
- prompt: [`prompts/medical_router_system_prompt.txt`](/home/rb/AI/gemma-routing/prompts/medical_router_system_prompt.txt)
- request example: [`examples/medical_router_request.json`](/home/rb/AI/gemma-routing/examples/medical_router_request.json)
