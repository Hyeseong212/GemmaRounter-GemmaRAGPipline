#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/rb/AI"
MODEL_VARIANT="${1:-e2b}"
CTX_SIZE="${2:-2048}"
PORT="${3:-8083}"
ALIAS="${4:-gemma4-vision-e2b}"
CONTAINER_NAME="${CONTAINER_NAME:-e2b-vision-test-${MODEL_VARIANT}-${PORT}}"

CPU_ONLY="${CPU_ONLY:-0}" \
GPU_LAYERS="${GPU_LAYERS:-8}" \
NO_KV_OFFLOAD="${NO_KV_OFFLOAD:-1}" \
NO_OP_OFFLOAD="${NO_OP_OFFLOAD:-1}" \
BATCH_SIZE="${BATCH_SIZE:-256}" \
UBATCH_SIZE="${UBATCH_SIZE:-256}" \
CACHE_TYPE_K="${CACHE_TYPE_K:-q4_0}" \
CACHE_TYPE_V="${CACHE_TYPE_V:-q4_0}" \
ENABLE_MMPROJ="${ENABLE_MMPROJ:-1}" \
ENABLE_WARMUP="${ENABLE_WARMUP:-0}" \
RUN_MODE="${RUN_MODE:-detached}" \
N_PARALLEL="${N_PARALLEL:-1}" \
exec "${ROOT_DIR}/shared-scripts/run_gemma4_llama_server.sh" \
  "${MODEL_VARIANT}" \
  "${CTX_SIZE}" \
  "${PORT}" \
  "${ALIAS}"
