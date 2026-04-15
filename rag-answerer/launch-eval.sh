#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/rb/AI/rag-answerer"
RUN_DIR="/tmp/rag-answerer-eval"
VENV_PY="/home/rb/AI/.venv-rag-answerer-index/bin/python"
EVAL_SCRIPT="${PROJECT_DIR}/scripts/evaluate_rag_answers.py"
RUN_SCRIPT="${PROJECT_DIR}/scripts/run_local_gemma.sh"
READY_SCRIPT="${PROJECT_DIR}/scripts/manage_local_gemma.sh"
DEFAULT_OUTPUT_DIR="${PROJECT_DIR}/test-results"
KNOWN_ACTIONS="run status logs stop"
ACTION="run"

MODEL_VARIANT="${MODEL_VARIANT:-e2b}"
CTX_SIZE="${CTX_SIZE:-4096}"
PORT="${PORT:-8082}"
ALIAS="${ALIAS:-gemma4-rag}"
CONTAINER_NAME="${CONTAINER_NAME:-rag-answerer-${MODEL_VARIANT}-${PORT}}"
GPU_LAYERS="${GPU_LAYERS:-1}"
BATCH_SIZE="${BATCH_SIZE:-64}"
UBATCH_SIZE="${UBATCH_SIZE:-16}"
NO_KV_OFFLOAD="${NO_KV_OFFLOAD:-1}"
NO_OP_OFFLOAD="${NO_OP_OFFLOAD:-1}"
OUTPUT_DIR="${OUTPUT_DIR:-${DEFAULT_OUTPUT_DIR}}"

if [[ $# -gt 0 ]]; then
  case " ${KNOWN_ACTIONS} " in
    *" $1 "*)
      ACTION="$1"
      shift || true
      ;;
  esac
fi

mkdir -p "${RUN_DIR}" "${OUTPUT_DIR}"

docker_cmd() {
  if docker info >/dev/null 2>&1; then
    echo "docker"
    return 0
  fi
  if sudo -n docker info >/dev/null 2>&1; then
    echo "sudo -n docker"
    return 0
  fi
  echo "docker unavailable" >&2
  return 1
}

stop_target_container() {
  local dc
  dc="$(docker_cmd)"
  if [[ -n "${dc}" ]]; then
    sh -lc "${dc} rm -f ${CONTAINER_NAME@Q} >/dev/null 2>&1 || true"
  fi
}

start_gpu_model() {
  echo "mode=gpu"
  echo "model_variant=${MODEL_VARIANT}"
  echo "gpu_layers=${GPU_LAYERS}"
  stop_target_container
  RUN_MODE=detached \
  CONTAINER_NAME="${CONTAINER_NAME}" \
  CPU_ONLY=0 \
  GPU_LAYERS="${GPU_LAYERS}" \
  BATCH_SIZE="${BATCH_SIZE}" \
  UBATCH_SIZE="${UBATCH_SIZE}" \
  NO_KV_OFFLOAD="${NO_KV_OFFLOAD}" \
  NO_OP_OFFLOAD="${NO_OP_OFFLOAD}" \
  "${RUN_SCRIPT}" "${MODEL_VARIANT}" "${CTX_SIZE}" "${PORT}" "${ALIAS}"
}

wait_ready_gpu() {
  PORT="${PORT}" \
  CONTAINER_NAME="${CONTAINER_NAME}" \
  CPU_ONLY=0 \
  GPU_LAYERS="${GPU_LAYERS}" \
  BATCH_SIZE="${BATCH_SIZE}" \
  UBATCH_SIZE="${UBATCH_SIZE}" \
  NO_KV_OFFLOAD="${NO_KV_OFFLOAD}" \
  NO_OP_OFFLOAD="${NO_OP_OFFLOAD}" \
  "${READY_SCRIPT}" ready "${MODEL_VARIANT}" "${CTX_SIZE}" "${PORT}" "${ALIAS}" "${CONTAINER_NAME}"
}

start_cpu_model() {
  echo "mode=cpu-fallback"
  stop_target_container
  RUN_MODE=detached \
  CONTAINER_NAME="${CONTAINER_NAME}" \
  CPU_ONLY=1 \
  GPU_LAYERS=0 \
  BATCH_SIZE="${BATCH_SIZE}" \
  UBATCH_SIZE="${UBATCH_SIZE}" \
  NO_KV_OFFLOAD=1 \
  NO_OP_OFFLOAD=1 \
  "${RUN_SCRIPT}" "${MODEL_VARIANT}" "${CTX_SIZE}" "${PORT}" "${ALIAS}"

  PORT="${PORT}" \
  CONTAINER_NAME="${CONTAINER_NAME}" \
  CPU_ONLY=1 \
  GPU_LAYERS=0 \
  BATCH_SIZE="${BATCH_SIZE}" \
  UBATCH_SIZE="${UBATCH_SIZE}" \
  NO_KV_OFFLOAD=1 \
  NO_OP_OFFLOAD=1 \
  "${READY_SCRIPT}" ready "${MODEL_VARIANT}" "${CTX_SIZE}" "${PORT}" "${ALIAS}" "${CONTAINER_NAME}"
}

run_eval() {
  local launch_mode="$1"
  "${VENV_PY}" "${EVAL_SCRIPT}" \
    --endpoint "http://127.0.0.1:${PORT}/v1/chat/completions" \
    --model-name "${ALIAS}" \
    --launch-mode "${launch_mode}" \
    --output-dir "${OUTPUT_DIR}"
}

show_status() {
  curl -s "http://127.0.0.1:${PORT}/v1/models" || true
}

show_logs() {
  local dc
  dc="$(docker_cmd)"
  sh -lc "${dc} logs --tail 120 ${CONTAINER_NAME@Q}" || true
}

case "${ACTION}" in
  run)
    launch_mode="gpu"
    if start_gpu_model && wait_ready_gpu; then
      launch_mode="gpu"
    else
      echo "gpu_start_failed=1"
      echo "gpu_model_variant=${MODEL_VARIANT}"
      echo "gpu_layers_attempted=${GPU_LAYERS}"
      start_cpu_model
      launch_mode="cpu-fallback"
    fi
    run_eval "${launch_mode}"
    ;;
  status)
    show_status
    ;;
  logs)
    show_logs
    ;;
  stop)
    stop_target_container
    ;;
  *)
    echo "Usage: $0 [run|status|logs|stop]" >&2
    exit 1
    ;;
esac
