#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/rb/AI"
MODEL_VARIANT="${1:-e4b-q4}"
CTX_SIZE="${2:-4096}"
PORT="${3:-8080}"
ALIAS="${4:-gemma4-routing}"
CONTAINER_NAME="${CONTAINER_NAME:-gemma-routing-${MODEL_VARIANT}-${PORT}}"

exec "${ROOT_DIR}/shared-scripts/run_gemma4_llama_server.sh" \
  "${MODEL_VARIANT}" \
  "${CTX_SIZE}" \
  "${PORT}" \
  "${ALIAS}"
