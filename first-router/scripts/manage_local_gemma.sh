#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/rb/AI"
ACTION="${1:-status}"
DEFAULT_SAMPLE_REQUEST="${ROOT_DIR}/first-router/examples/medical_router_request.json"

case "${ACTION}" in
  sample|trace|stream)
    SAMPLE_REQUEST="${2:-${DEFAULT_SAMPLE_REQUEST}}"
    MODEL_VARIANT="${MODEL_VARIANT:-e2b}" \
    CTX_SIZE="${CTX_SIZE:-2048}" \
    PORT="${PORT:-8080}" \
    ALIAS="${ALIAS:-gemma4-routing}" \
    CONTAINER_NAME="${CONTAINER_NAME:-first-router-e2b-8080}" \
    CPU_ONLY="${CPU_ONLY:-0}" \
    GPU_LAYERS="${GPU_LAYERS:-8}" \
    NO_KV_OFFLOAD="${NO_KV_OFFLOAD:-1}" \
    NO_OP_OFFLOAD="${NO_OP_OFFLOAD:-1}" \
    BATCH_SIZE="${BATCH_SIZE:-128}" \
    UBATCH_SIZE="${UBATCH_SIZE:-32}" \
    CACHE_TYPE_K="${CACHE_TYPE_K:-q4_0}" \
    CACHE_TYPE_V="${CACHE_TYPE_V:-q4_0}" \
    RUN_SCRIPT="${ROOT_DIR}/first-router/scripts/run_local_gemma.sh" \
    DEFAULT_SAMPLE_REQUEST="${DEFAULT_SAMPLE_REQUEST}" \
    OUTPUT_DIR="${OUTPUT_DIR:-/tmp/first-router}" \
    exec "${ROOT_DIR}/shared-scripts/manage_gemma4_llama_server.sh" \
      "${ACTION}" \
      "${SAMPLE_REQUEST}"
    ;;
  *)
    MODEL_VARIANT="${2:-e2b}"
    CTX_SIZE="${3:-2048}"
    PORT="${4:-8080}"
    ALIAS="${5:-gemma4-routing}"
    CONTAINER_NAME="${6:-first-router-${MODEL_VARIANT}-${PORT}}"

    CPU_ONLY="${CPU_ONLY:-0}" \
    GPU_LAYERS="${GPU_LAYERS:-8}" \
    NO_KV_OFFLOAD="${NO_KV_OFFLOAD:-1}" \
    NO_OP_OFFLOAD="${NO_OP_OFFLOAD:-1}" \
    BATCH_SIZE="${BATCH_SIZE:-128}" \
    UBATCH_SIZE="${UBATCH_SIZE:-32}" \
    CACHE_TYPE_K="${CACHE_TYPE_K:-q4_0}" \
    CACHE_TYPE_V="${CACHE_TYPE_V:-q4_0}" \
    RUN_SCRIPT="${ROOT_DIR}/first-router/scripts/run_local_gemma.sh" \
    DEFAULT_SAMPLE_REQUEST="${DEFAULT_SAMPLE_REQUEST}" \
    OUTPUT_DIR="${OUTPUT_DIR:-/tmp/first-router}" \
    exec "${ROOT_DIR}/shared-scripts/manage_gemma4_llama_server.sh" \
      "${ACTION}" \
      "${MODEL_VARIANT}" \
      "${CTX_SIZE}" \
      "${PORT}" \
      "${ALIAS}" \
      "${CONTAINER_NAME}"
    ;;
esac
