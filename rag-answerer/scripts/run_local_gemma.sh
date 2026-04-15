#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/rb/AI"
MODEL_VARIANT="${1:-e2b}"
CTX_SIZE="${2:-4096}"
PORT="${3:-8082}"
ALIAS="${4:-gemma4-rag}"
CONTAINER_NAME="${CONTAINER_NAME:-rag-answerer-${MODEL_VARIANT}-${PORT}}"

CPU_ONLY="${CPU_ONLY:-0}" \
GPU_LAYERS="${GPU_LAYERS:-8}" \
NO_KV_OFFLOAD="${NO_KV_OFFLOAD:-1}" \
NO_OP_OFFLOAD="${NO_OP_OFFLOAD:-1}" \
BATCH_SIZE="${BATCH_SIZE:-128}" \
UBATCH_SIZE="${UBATCH_SIZE:-32}" \
CACHE_TYPE_K="${CACHE_TYPE_K:-q4_0}" \
CACHE_TYPE_V="${CACHE_TYPE_V:-q4_0}" \
exec "${ROOT_DIR}/shared-scripts/run_gemma4_llama_server.sh" \
  "${MODEL_VARIANT}" \
  "${CTX_SIZE}" \
  "${PORT}" \
  "${ALIAS}"
