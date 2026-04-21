#!/usr/bin/env bash
set -euo pipefail

MODEL_VARIANT="${1:-e2b}"
CTX_SIZE="${2:-4096}"
PORT="${3:-8080}"
ALIAS="${4:-gemma4-shared}"
RUN_MODE="${RUN_MODE:-foreground}"
CONTAINER_NAME="${CONTAINER_NAME:-gemma4-${MODEL_VARIANT}-${PORT}}"
ENABLE_MMPROJ="${ENABLE_MMPROJ:-0}"
MMPROJ_OFFLOAD="${MMPROJ_OFFLOAD:-1}"
ENABLE_WARMUP="${ENABLE_WARMUP:-0}"
N_PARALLEL="${N_PARALLEL:-1}"
BATCH_SIZE="${BATCH_SIZE:-1024}"
UBATCH_SIZE="${UBATCH_SIZE:-256}"
REASONING_MODE="${REASONING_MODE:-off}"
GPU_LAYERS="${GPU_LAYERS:-}"
DEVICE="${DEVICE:-}"
CPU_ONLY="${CPU_ONLY:-0}"
CACHE_TYPE_K="${CACHE_TYPE_K:-}"
CACHE_TYPE_V="${CACHE_TYPE_V:-}"
NO_KV_OFFLOAD="${NO_KV_OFFLOAD:-0}"
NO_OP_OFFLOAD="${NO_OP_OFFLOAD:-0}"

IMAGE="ghcr.io/nvidia-ai-iot/llama_cpp:gemma4-jetson-orin"
HF_CACHE="${HOME}/.cache/huggingface"
MODEL_CACHE="${HOME}/.cache/jetson-models/huggingface"
QUANT_LABEL=""

has_command() {
  command -v "$1" >/dev/null 2>&1
}

stream_contains_exact_line() {
  local pattern="$1"
  if has_command rg; then
    rg -xq "${pattern}"
  else
    grep -Fxq "${pattern}"
  fi
}

case "${MODEL_VARIANT}" in
  e2b)
    HF_MODEL="ggml-org/gemma-4-E2B-it-GGUF:Q8_0"
    QUANT_LABEL="Q8_0"
    ;;
  e4b|e4b-q4|e4b-4bit)
    HF_MODEL="ggml-org/gemma-4-E4B-it-GGUF:Q4_K_M"
    QUANT_LABEL="Q4_K_M (4-bit)"
    ;;
  *)
    echo "Usage: $0 [e2b|e4b|e4b-q4|e4b-4bit] [ctx_size] [port] [alias]" >&2
    exit 1
    ;;
esac

if docker info >/dev/null 2>&1; then
  DOCKER_CMD=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  DOCKER_CMD=(sudo -n docker)
else
  echo "Docker is not accessible for the current user, and passwordless sudo is unavailable." >&2
  echo "Add this user to the docker group or run the script from a root shell." >&2
  exit 1
fi

mkdir -p "${HF_CACHE}"
mkdir -p "${MODEL_CACHE}"

echo "Starting ${ALIAS} on port ${PORT} with ctx-size ${CTX_SIZE}"
echo "Model: ${HF_MODEL}"
echo "Quantization: ${QUANT_LABEL}"
echo "Docker command: ${DOCKER_CMD[*]}"
echo "Run mode: ${RUN_MODE}"
echo "Container name: ${CONTAINER_NAME}"
echo "Enable mmproj: ${ENABLE_MMPROJ}"
echo "Mmproj offload: ${MMPROJ_OFFLOAD}"
echo "Enable warmup: ${ENABLE_WARMUP}"
echo "Parallel slots: ${N_PARALLEL}"
echo "Batch size: ${BATCH_SIZE}"
echo "Ubatch size: ${UBATCH_SIZE}"
echo "Reasoning mode: ${REASONING_MODE}"
echo "CPU only: ${CPU_ONLY}"
echo "GPU layers: ${GPU_LAYERS:-auto}"
echo "Device: ${DEVICE:-auto}"
echo "Cache type K: ${CACHE_TYPE_K:-default}"
echo "Cache type V: ${CACHE_TYPE_V:-default}"
echo "No KV offload: ${NO_KV_OFFLOAD}"
echo "No op offload: ${NO_OP_OFFLOAD}"

COMMON_ARGS=(
  --pull always
  --runtime=nvidia
  --network host
  -v "${HF_CACHE}:/root/.cache/huggingface"
  -v "${MODEL_CACHE}:/data/models/huggingface"
)

SERVER_ARGS=(
  llama-server
  -hf "${HF_MODEL}"
  --alias "${ALIAS}"
  --host 0.0.0.0
  --port "${PORT}"
  --ctx-size "${CTX_SIZE}"
  --parallel "${N_PARALLEL}"
  --batch-size "${BATCH_SIZE}"
  --ubatch-size "${UBATCH_SIZE}"
  --reasoning "${REASONING_MODE}"
)

if [[ "${CPU_ONLY}" == "1" ]]; then
  SERVER_ARGS+=(--device none --no-kv-offload --no-op-offload)
else
  if [[ -n "${DEVICE}" ]]; then
    SERVER_ARGS+=(--device "${DEVICE}")
  fi
  if [[ -n "${GPU_LAYERS}" ]]; then
    SERVER_ARGS+=(--gpu-layers "${GPU_LAYERS}")
  fi
  if [[ "${NO_KV_OFFLOAD}" == "1" ]]; then
    SERVER_ARGS+=(--no-kv-offload)
  fi
  if [[ "${NO_OP_OFFLOAD}" == "1" ]]; then
    SERVER_ARGS+=(--no-op-offload)
  fi
fi

if [[ -n "${CACHE_TYPE_K}" ]]; then
  SERVER_ARGS+=(--cache-type-k "${CACHE_TYPE_K}")
fi

if [[ -n "${CACHE_TYPE_V}" ]]; then
  SERVER_ARGS+=(--cache-type-v "${CACHE_TYPE_V}")
fi

if [[ "${ENABLE_MMPROJ}" == "1" ]]; then
  SERVER_ARGS+=(--mmproj-auto)
  if [[ "${MMPROJ_OFFLOAD}" == "1" ]]; then
    SERVER_ARGS+=(--mmproj-offload)
  else
    SERVER_ARGS+=(--no-mmproj-offload)
  fi
else
  SERVER_ARGS+=(--no-mmproj)
fi

if [[ "${ENABLE_WARMUP}" == "1" ]]; then
  SERVER_ARGS+=(--warmup)
else
  SERVER_ARGS+=(--no-warmup)
fi

if [[ "${RUN_MODE}" == "detached" ]]; then
  if "${DOCKER_CMD[@]}" ps -a --format '{{.Names}}' | stream_contains_exact_line "${CONTAINER_NAME}"; then
    echo "Removing existing container: ${CONTAINER_NAME}"
    "${DOCKER_CMD[@]}" rm -f "${CONTAINER_NAME}" >/dev/null
  fi

  "${DOCKER_CMD[@]}" run -d \
    --name "${CONTAINER_NAME}" \
    "${COMMON_ARGS[@]}" \
    "${IMAGE}" \
    "${SERVER_ARGS[@]}" >/dev/null

  echo "Detached container started: ${CONTAINER_NAME}"
  echo "Logs: ${DOCKER_CMD[*]} logs -f ${CONTAINER_NAME}"
  exit 0
fi

exec "${DOCKER_CMD[@]}" run -it --rm \
  "${COMMON_ARGS[@]}" \
  "${IMAGE}" \
  "${SERVER_ARGS[@]}"
