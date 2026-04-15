#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"
BUILD_DIR="${PROJECT_DIR}/build"
BINARY_PATH="${BUILD_DIR}/llama_Rest"
ENV_FILE="${PROJECT_DIR}/.env"
RUN_DIR="/tmp/llama-rest-core"
PID_FILE="${RUN_DIR}/llama-rest-core.pid"
LOG_FILE="${RUN_DIR}/llama-rest-core.log"
EMBED_PID_FILE="${RUN_DIR}/rag-embed-helper.pid"
EMBED_LOG_FILE="${RUN_DIR}/rag-embed-helper.log"
API_PORT="${LLAMA_REST_PORT:-18088}"
API_URL="http://127.0.0.1:${API_PORT}/healthz"
RAG_EMBED_HELPER_HOST="${RAG_EMBED_HELPER_HOST:-127.0.0.1}"
RAG_EMBED_HELPER_PORT="${RAG_EMBED_HELPER_PORT:-18089}"
RAG_EMBED_HELPER_URL="http://${RAG_EMBED_HELPER_HOST}:${RAG_EMBED_HELPER_PORT}/healthz"
RAG_EMBED_HELPER_ENABLE="${RAG_EMBED_HELPER_ENABLE:-1}"
RAG_EMBED_HELPER_MODEL_NAME="${RAG_EMBED_HELPER_MODEL_NAME:-BAAI/bge-m3}"
RAG_EMBED_HELPER_DEVICE="${RAG_EMBED_HELPER_DEVICE:-}"
RAG_INDEX_DIR="${RAG_INDEX_DIR:-${PROJECT_DIR}/../rag-answerer/indexes/mfds-korean-medical-device-text-bge-m3}"
LLAMA_REST_MODEL_PATH="${LLAMA_REST_MODEL_PATH:-/home/rbiotech-server/llama_Rest/models/gemma4-31b/gemma-4-31B-it-Q4_K_M.gguf}"
LLAMA_REST_MMPROJ_PATH="${LLAMA_REST_MMPROJ_PATH:-/home/rbiotech-server/llama_Rest/models/gemma4-31b/mmproj-gemma-4-31B-it-Q8_0.gguf}"
LLAMA_REST_IMAGE_MIN_TOKENS="${LLAMA_REST_IMAGE_MIN_TOKENS:-252}"
LLAMA_REST_IMAGE_MAX_TOKENS="${LLAMA_REST_IMAGE_MAX_TOKENS:-1120}"
LLAMA_REST_ENABLE_DEV_FIRST_ROUTER="${LLAMA_REST_ENABLE_DEV_FIRST_ROUTER:-0}"
LLAMA_REST_ENABLE_DEV_PIPELINE_FROM_USER="${LLAMA_REST_ENABLE_DEV_PIPELINE_FROM_USER:-0}"
KNOWN_ACTIONS="start restart stop status ready logs build build-index"
ACTION="start"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

if [[ $# -gt 0 ]]; then
  case " ${KNOWN_ACTIONS} " in
    *" $1 "*)
      ACTION="$1"
      shift || true
      ;;
  esac
fi

mkdir -p "${RUN_DIR}"

stop_pidfile_process() {
  local pid_file="$1"
  local label="$2"

  if [[ ! -f "${pid_file}" ]]; then
    return 0
  fi

  local pid
  pid="$(cat "${pid_file}")"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    echo "Stopping ${label} (${pid})"
    kill "${pid}" >/dev/null 2>&1 || true
    for _ in $(seq 1 20); do
      if ! kill -0 "${pid}" >/dev/null 2>&1; then
        break
      fi
      sleep 0.2
    done
    kill -9 "${pid}" >/dev/null 2>&1 || true
  fi

  rm -f "${pid_file}"
}

stop_port_listener() {
  local port="$1"
  if ss -ltn "sport = :${port}" 2>/dev/null | grep -q ":${port}"; then
    echo "Stopping process on port ${port}"
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
    sleep 1
  fi
}

wait_http_ready() {
  local url="$1"
  local timeout_s="${2:-60}"
  local pid="${3:-}"

  python3 - <<PY
import os
import sys
import time
import urllib.request

url = ${url@Q}
timeout_s = int(${timeout_s})
pid = ${pid@Q}
started = time.time()

while True:
    elapsed = time.time() - started
    if elapsed > timeout_s:
        print(f"ready=0 timeout_s={timeout_s}")
        sys.exit(1)
    if pid:
        try:
            os.kill(int(pid), 0)
        except OSError:
            print("ready=0 api_process_exited=1")
            sys.exit(1)
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            print(f"ready=1 elapsed_s={elapsed:.1f} status={resp.getcode()}")
            sys.exit(0)
    except Exception:
        time.sleep(1)
PY
}

ensure_build() {
  cmake -S "${PROJECT_DIR}" -B "${BUILD_DIR}"
  cmake --build "${BUILD_DIR}" -j"$(nproc)"
}

build_index() {
  if [[ -f "${RAG_INDEX_DIR}/manifest.json" && -f "${RAG_INDEX_DIR}/chunks.jsonl" && -f "${RAG_INDEX_DIR}/embeddings.npy" ]]; then
    echo "Dense RAG index already present: ${RAG_INDEX_DIR}"
    return 0
  fi
  python3 "${PROJECT_DIR}/build_text_embedding_index.py"
}

start_embed_helper() {
  if [[ "${RAG_EMBED_HELPER_ENABLE}" != "1" ]]; then
    return 0
  fi

  stop_pidfile_process "${EMBED_PID_FILE}" "rag-embed-helper"
  stop_port_listener "${RAG_EMBED_HELPER_PORT}"

  local -a cmd=(
    python3 "${PROJECT_DIR}/rag_embed_helper.py"
    --host "${RAG_EMBED_HELPER_HOST}"
    --port "${RAG_EMBED_HELPER_PORT}"
    --model-name "${RAG_EMBED_HELPER_MODEL_NAME}"
  )
  if [[ -n "${RAG_EMBED_HELPER_DEVICE}" ]]; then
    cmd+=(--device "${RAG_EMBED_HELPER_DEVICE}")
  fi

  setsid "${cmd[@]}" >"${EMBED_LOG_FILE}" 2>&1 < /dev/null &
  local pid=$!
  echo "${pid}" > "${EMBED_PID_FILE}"
  echo "Starting rag-embed-helper on port ${RAG_EMBED_HELPER_PORT} (${pid})"
  wait_http_ready "${RAG_EMBED_HELPER_URL}" 180 "${pid}"
  echo "rag-embed-helper log: ${EMBED_LOG_FILE}"
}

start_service() {
  stop_pidfile_process "${PID_FILE}" "llama-rest-core"
  stop_port_listener "${API_PORT}"
  build_index
  ensure_build
  start_embed_helper

  setsid env \
    LLAMA_REST_ENABLE_INFER="${LLAMA_REST_ENABLE_INFER:-1}" \
    LLAMA_REST_PORT="${API_PORT}" \
    LLAMA_REST_MODEL_PATH="${LLAMA_REST_MODEL_PATH}" \
    LLAMA_REST_MMPROJ_PATH="${LLAMA_REST_MMPROJ_PATH}" \
    LLAMA_REST_IMAGE_MIN_TOKENS="${LLAMA_REST_IMAGE_MIN_TOKENS}" \
    LLAMA_REST_IMAGE_MAX_TOKENS="${LLAMA_REST_IMAGE_MAX_TOKENS}" \
    LLAMA_REST_ENABLE_DEV_FIRST_ROUTER="${LLAMA_REST_ENABLE_DEV_FIRST_ROUTER}" \
    LLAMA_REST_ENABLE_DEV_PIPELINE_FROM_USER="${LLAMA_REST_ENABLE_DEV_PIPELINE_FROM_USER}" \
    RAG_EMBEDDING_ENDPOINT="http://${RAG_EMBED_HELPER_HOST}:${RAG_EMBED_HELPER_PORT}/embed" \
    "${BINARY_PATH}" >"${LOG_FILE}" 2>&1 < /dev/null &

  local pid=$!
  echo "${pid}" > "${PID_FILE}"
  echo "Starting llama-rest-core on port ${API_PORT} (${pid})"
  wait_http_ready "${API_URL}" 90 "${pid}"
  echo "llama-rest-core log: ${LOG_FILE}"
}

show_status() {
  if [[ -f "${EMBED_PID_FILE}" ]]; then
    local embed_pid
    embed_pid="$(cat "${EMBED_PID_FILE}")"
    if [[ -n "${embed_pid}" ]] && kill -0 "${embed_pid}" >/dev/null 2>&1; then
      echo "rag-embed-helper: running (pid=${embed_pid}, port=${RAG_EMBED_HELPER_PORT})"
    fi
  fi

  if [[ -f "${PID_FILE}" ]]; then
    local pid
    pid="$(cat "${PID_FILE}")"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      echo "llama-rest-core: running (pid=${pid}, port=${API_PORT})"
      return 0
    fi
  fi

  if ss -ltn "sport = :${API_PORT}" 2>/dev/null | grep -q ":${API_PORT}"; then
    echo "llama-rest-core: listening on port ${API_PORT}"
  else
    echo "llama-rest-core: not running"
  fi
}

case "${ACTION}" in
  start)
    start_service
    ;;
  restart)
    stop_pidfile_process "${PID_FILE}" "llama-rest-core"
    stop_pidfile_process "${EMBED_PID_FILE}" "rag-embed-helper"
    stop_port_listener "${API_PORT}"
    stop_port_listener "${RAG_EMBED_HELPER_PORT}"
    start_service
    ;;
  stop)
    stop_pidfile_process "${PID_FILE}" "llama-rest-core"
    stop_pidfile_process "${EMBED_PID_FILE}" "rag-embed-helper"
    stop_port_listener "${API_PORT}"
    stop_port_listener "${RAG_EMBED_HELPER_PORT}"
    ;;
  status)
    show_status
    ;;
  ready)
    wait_http_ready "${API_URL}" 10
    ;;
  logs)
    if [[ -f "${EMBED_LOG_FILE}" ]]; then
      echo "== rag-embed-helper =="
      tail -n 80 "${EMBED_LOG_FILE}"
    fi
    if [[ -f "${LOG_FILE}" ]]; then
      echo "== llama-rest-core =="
      tail -n 120 "${LOG_FILE}"
    else
      echo "No llama-rest-core log file yet: ${LOG_FILE}"
    fi
    ;;
  build)
    ensure_build
    ;;
  build-index)
    build_index
    ;;
  *)
    echo "Usage: $0 [start|restart|stop|status|ready|logs|build|build-index]" >&2
    exit 1
    ;;
esac
