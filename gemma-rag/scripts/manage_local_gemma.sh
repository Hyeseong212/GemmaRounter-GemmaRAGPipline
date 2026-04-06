#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/rb/AI"
ACTION="${1:-status}"
DEFAULT_SAMPLE_REQUEST="${ROOT_DIR}/gemma-rag/examples/rag_answer_request.json"

case "${ACTION}" in
  sample|trace|stream)
    SAMPLE_REQUEST="${2:-${DEFAULT_SAMPLE_REQUEST}}"
    MODEL_VARIANT="${MODEL_VARIANT:-e4b-q4}" \
    CTX_SIZE="${CTX_SIZE:-4096}" \
    PORT="${PORT:-8082}" \
    ALIAS="${ALIAS:-gemma4-rag}" \
    CONTAINER_NAME="${CONTAINER_NAME:-gemma-rag-e4b-q4-8082}" \
    RUN_SCRIPT="${ROOT_DIR}/gemma-rag/scripts/run_local_gemma.sh" \
    DEFAULT_SAMPLE_REQUEST="${DEFAULT_SAMPLE_REQUEST}" \
    OUTPUT_DIR="${OUTPUT_DIR:-/tmp/gemma-rag}" \
    exec "${ROOT_DIR}/shared-scripts/manage_gemma4_llama_server.sh" \
      "${ACTION}" \
      "${SAMPLE_REQUEST}"
    ;;
  *)
    MODEL_VARIANT="${2:-e4b-q4}"
    CTX_SIZE="${3:-4096}"
    PORT="${4:-8082}"
    ALIAS="${5:-gemma4-rag}"
    CONTAINER_NAME="${6:-gemma-rag-${MODEL_VARIANT}-${PORT}}"

    RUN_SCRIPT="${ROOT_DIR}/gemma-rag/scripts/run_local_gemma.sh" \
    DEFAULT_SAMPLE_REQUEST="${DEFAULT_SAMPLE_REQUEST}" \
    OUTPUT_DIR="${OUTPUT_DIR:-/tmp/gemma-rag}" \
    exec "${ROOT_DIR}/shared-scripts/manage_gemma4_llama_server.sh" \
      "${ACTION}" \
      "${MODEL_VARIANT}" \
      "${CTX_SIZE}" \
      "${PORT}" \
      "${ALIAS}" \
      "${CONTAINER_NAME}"
    ;;
esac
