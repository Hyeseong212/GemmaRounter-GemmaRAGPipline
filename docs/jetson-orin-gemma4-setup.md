# Jetson Orin 16GB Gemma 4 Setup

Last updated: 2026-04-06

This guide assumes a Jetson Orin 16GB class device and focuses on the two Gemma 4 variants that are realistic on-device today:

| Model | Jetson AI Lab memory note | Best first use on Jetson |
| --- | --- | --- |
| `Gemma 4 E2B` | 8GB RAM, `Q8_0`, model size 5.0GB | safest first bring-up, routing, safety gate, short fallback replies |
| `Gemma 4 E4B` | 8GB RAM, `Q4_K_M`, model size 5.3GB | better reasoning, local SOP QA, lightweight multimodal triage |

For a 16GB Jetson, start with `E2B` first, then move to `E4B` after the pipeline is stable.

## What I Recommend

For your medical-device pipeline, treat Gemma 4 on Jetson as a shared local model service that both app projects consume:

- on-device router
- safety gate
- local fallback assistant
- short structured summarizer

Workspace split:

- [`first-router`](/home/rb/AI/first-router)
- [`rag-answerer`](/home/rb/AI/rag-answerer)

Do **not** make Jetson Gemma the final clinical reasoning engine. Keep long-context RAG, heavy retrieval, and final complex answers on the 5090 server.

## Setup Path

There are two practical ways to run Gemma 4 on Jetson:

1. `llama.cpp` container on Jetson AI Lab
   - Best if you want a clean, reproducible OpenAI-compatible local API.
   - This is the path I recommend for your device-side router.
2. `Ollama`
   - Best for fast smoke tests and quick local experiments.

This workspace includes shared base launcher scripts plus project-specific wrappers:

- shared base: [`../shared-scripts/run_gemma4_llama_server.sh`](/home/rb/AI/shared-scripts/run_gemma4_llama_server.sh)
- routing wrapper: [`../first-router/scripts/manage_local_gemma.sh`](/home/rb/AI/first-router/scripts/manage_local_gemma.sh)
- transfer robot wrapper: [`../transfer-robot-llm/scripts/manage_local_gemma.sh`](/home/rb/AI/transfer-robot-llm/scripts/manage_local_gemma.sh)
- RAG wrapper: [`../rag-answerer/scripts/manage_local_gemma.sh`](/home/rb/AI/rag-answerer/scripts/manage_local_gemma.sh)

Each project uses its own local alias and port.

## Step 0: Preflight On Jetson

Check your power mode first:

```bash
sudo /usr/sbin/nvpmodel -q --verbose
```

Then switch to the highest power mode your module supports, if needed:

```bash
sudo /usr/sbin/nvpmodel -m <mode_id>
```

After that, maximize clocks:

```bash
sudo /usr/bin/jetson_clocks
```

Notes:

- Mode IDs differ by module and flash config, so check `nvpmodel -q --verbose` before changing.
- On some Orin modes, changing the GPU partitioning can require a reboot.

## Step 1: Start Gemma 4 With `llama.cpp`

Copy this workspace to the Jetson or recreate the files there, then run:

```bash
chmod +x /home/<user>/AI/shared-scripts/run_gemma4_llama_server.sh
/home/<user>/AI/shared-scripts/run_gemma4_llama_server.sh e2b
```

For `Gemma 4 E4B` 4-bit quantization:

```bash
/home/<user>/AI/shared-scripts/run_gemma4_llama_server.sh e4b-q4 4096 8080 gemma4-routing
```

This launcher maps `e4b`, `e4b-q4`, and `e4b-4bit` to:

- `ggml-org/gemma-4-E4B-it-GGUF:Q4_K_M`

Arguments:

- arg1: `e2b`, `e4b`, `e4b-q4`, or `e4b-4bit`
- arg2: context size, default `4096`
- arg3: port, default `8080`
- arg4: alias, default `gemma4-shared`

Why `4096` first:

- 16GB Jetson can run the model, but long contexts still grow KV cache.
- Your router/safety-gate use case does not need 128K context.
- Start lean and stable, then increase later if you actually need it.

Docker note:

- If your user is already in the `docker` group, the launcher runs `docker` directly.
- If not, it will try passwordless `sudo -n docker`.
- If both fail, run it from a root shell or add the user to the `docker` group.

## Step 2: Smoke Test The Local API

Example project aliases:

- `gemma4-routing`
- `gemma4-transfer-robot`
- `gemma4-rag`

Example request:

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d @/home/<user>/AI/first-router/examples/medical_router_request.json
```

The routing example request file in this workspace is:

- [`first-router/examples/medical_router_request.json`](/home/rb/AI/first-router/examples/medical_router_request.json)

The router system prompt is here:

- [`first-router/prompts/medical_router_system_prompt.txt`](/home/rb/AI/first-router/prompts/medical_router_system_prompt.txt)
- [`first-router/docs/router-schema.md`](/home/rb/AI/first-router/docs/router-schema.md)

The RAG-side prompt and request example are here:

- [`rag-answerer/prompts/rag_answer_system_prompt.txt`](/home/rb/AI/rag-answerer/prompts/rag_answer_system_prompt.txt)
- [`rag-answerer/examples/rag_answer_request.json`](/home/rb/AI/rag-answerer/examples/rag_answer_request.json)

## Step 3: Optional Ollama Smoke Test

If you just want the quickest possible first run on Jetson:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama run gemma4:e2b
```

Then later:

```bash
ollama run gemma4:e4b
```

Ollama is great for proving the device works. For your medical-device router, I still prefer `llama-server` because it gives you a cleaner fixed local API boundary.

## Where Gemma 4 Should Sit In Your Pipeline

Recommended Jetson role:

```text
device input
  -> hard rules
  -> Gemma 4 router on Jetson
  -> one of:
       local_rule_only
       local_llm
       server_rag
       server_llm
       server_vision
       human_review
       block
```

### Best Uses On Jetson

1. Local intent and risk classification
   - Example: device usage question, error-code question, patient-risk question, forbidden request

2. Safety gate before the server call
   - Example: block direct diagnosis, medication advice, or treatment-change prompts

3. Structured routing
   - Output JSON only, then let the server decide how to execute retrieval or specialist tools

4. Short local fallback responses
   - Example: network down, show limited-mode response plus warning label

5. Short log summarization
   - Example: compress recent device events into a one-paragraph summary for the server

6. Optional lightweight multimodal triage with `E4B`
   - Example: screen photo or UI screenshot classification before escalating upstream

### Not A Good Primary Use On Jetson

- final clinical judgment
- long-context RAG over large manuals
- full multi-agent planning
- heavy multimodal reasoning over many images
- high-concurrency central serving

## My Model Recommendation

Start like this:

1. `Gemma 4 E2B`
   - first device bring-up
   - router
   - safety gate
   - JSON-only structured outputs

2. `Gemma 4 E4B`
   - `Q4_K_M` 4-bit quantized on Jetson
   - after routing is stable
   - stronger local fallback QA
   - optional document/image triage

If I were choosing just one role for day one, I would use `E2B` as the Jetson-side router and keep the 5090 server as the main reasoning backend.

## Suggested Router Schema

Use a fixed output shape like this:

```json
{
  "intent": "device_error_question",
  "risk_level": "medium",
  "route": "server_rag",
  "needs_human_review": false,
  "patient_related": false,
  "priority": "high",
  "required_tools": ["manual_retrieval"],
  "reason_codes": ["needs_reference_grounding"],
  "summary_for_server": "User asks what error code E103 means and what the next safe action is.",
  "local_action": "none"
}
```

## Sources

- Jetson AI Lab, Ollama on Jetson: https://www.jetson-ai-lab.com/tutorials/ollama/
- Jetson AI Lab, Gemma 4 E2B: https://www.jetson-ai-lab.com/models/gemma4-e2b/
- Jetson AI Lab, Gemma 4 E4B: https://www.jetson-ai-lab.com/models/gemma4-e4b/
- Google Developers Blog, Gemma 4 on-device agentic workflows: https://developers.googleblog.com/bring-state-of-the-art-agentic-skills-to-the-edge-with-gemma-4/
- Ollama model library, Gemma 4: https://ollama.com/library/gemma4
- NVIDIA Jetson Linux Developer Guide, `nvpmodel`: https://docs.nvidia.com/jetson/archives/r36.4.3/DeveloperGuide/SD/PlatformPowerAndPerformance/JetsonOrinNanoSeriesJetsonOrinNxSeriesAndJetsonAgxOrinSeries.html
- NVIDIA Jetson Linux Developer Guide, `jetson_clocks`: https://docs.nvidia.com/jetson/archives/r35.4.1/DeveloperGuide/text/SD/PlatformPowerAndPerformance/JetsonOrinNanoSeriesJetsonOrinNxSeriesAndJetsonAgxOrinSeries.html
