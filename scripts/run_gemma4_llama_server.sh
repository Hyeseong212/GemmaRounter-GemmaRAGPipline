#!/usr/bin/env bash
set -euo pipefail

MODEL_VARIANT="${1:-e2b}"
CTX_SIZE="${2:-4096}"
PORT="${3:-8080}"
ALIAS="${4:-gemma4-shared}"

IMAGE="ghcr.io/nvidia-ai-iot/llama_cpp:gemma4-jetson-orin"
HF_CACHE="${HOME}/.cache/huggingface"

case "${MODEL_VARIANT}" in
  e2b)
    HF_MODEL="ggml-org/gemma-4-E2B-it-GGUF:Q8_0"
    ;;
  e4b)
    HF_MODEL="ggml-org/gemma-4-E4B-it-GGUF:Q4_K_M"
    ;;
  *)
    echo "Usage: $0 [e2b|e4b] [ctx_size] [port] [alias]" >&2
    exit 1
    ;;
esac

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

mkdir -p "${HF_CACHE}"

echo "Starting ${ALIAS} on port ${PORT} with ctx-size ${CTX_SIZE}"
echo "Model: ${HF_MODEL}"

exec "${SUDO[@]}" docker run -it --rm \
  --pull always \
  --runtime=nvidia \
  --network host \
  -v "${HF_CACHE}:/root/.cache/huggingface" \
  "${IMAGE}" \
  llama-server \
  -hf "${HF_MODEL}" \
  --alias "${ALIAS}" \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --ctx-size "${CTX_SIZE}"
