#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/rb/AI/first-router"
MODEL_SCRIPT="${PROJECT_DIR}/scripts/manage_local_gemma.sh"
VENV_DIR="${PROJECT_DIR}/.venv"
VENV_PY="${VENV_DIR}/bin/python"
API_PORT="${ROUTER_API_PORT:-8090}"
API_URL="http://127.0.0.1:${API_PORT}/healthz"
RUN_DIR="/tmp/first-router"
API_PID_FILE="${RUN_DIR}/router-api.pid"
API_LOG_FILE="${RUN_DIR}/router-api.log"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DEFAULT_IMAGE="${DEFAULT_IMAGE:-/home/rb/AI/llama-rest-core/test-assets/public-research/중앙.jpg}"
DEFAULT_SCENE_PROMPT="${PROJECT_DIR}/examples/image_scene_prompt.txt"
DEFAULT_COORDINATE_PROMPT="${PROJECT_DIR}/examples/image_coordinate_prompt.txt"
BOOTSTRAP_DIR="${RUN_DIR}/bootstrap"
GET_PIP_PY="${BOOTSTRAP_DIR}/get-pip.py"
KNOWN_ACTIONS="start restart start-mm restart-mm stop status ready logs model-logs test sample trace stream image-sample image-coordinate"
ACTION="start"

if [[ $# -gt 0 ]]; then
  case " ${KNOWN_ACTIONS} " in
    *" $1 "*)
      ACTION="$1"
      shift || true
      ;;
  esac
fi

mkdir -p "${RUN_DIR}" "${BOOTSTRAP_DIR}"

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
import sys
import time
import urllib.request
import os

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

ensure_router_runtime() {
  if [[ ! -x "${VENV_PY}" ]]; then
    python3 -m venv "${VENV_DIR}"
  fi

  if "${VENV_PY}" - <<'PY' >/dev/null 2>&1
import fastapi
import httpx
import pydantic
import uvicorn
PY
  then
    return 0
  fi

  if ! "${VENV_PY}" -m pip --version >/dev/null 2>&1; then
    if [[ ! -f "${GET_PIP_PY}" ]]; then
      curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "${GET_PIP_PY}"
    fi
    "${VENV_PY}" "${GET_PIP_PY}"
  fi

  "${VENV_PY}" -m pip install --disable-pip-version-check \
    "fastapi>=0.115,<1.0" \
    "httpx>=0.27,<1.0" \
    "pydantic>=2.8,<3.0" \
    "uvicorn>=0.30,<1.0"
}

start_router_api() {
  stop_pidfile_process "${API_PID_FILE}" "first-router api"
  stop_port_listener "${API_PORT}"
  ensure_router_runtime

  if command -v setsid >/dev/null 2>&1; then
    setsid env \
      PYTHONPATH="${PROJECT_DIR}/src" \
      ROUTER_MODEL_ENDPOINT="http://127.0.0.1:8080/v1/chat/completions" \
      ROUTER_MODEL_NAME="gemma4-routing" \
      ROUTER_API_PORT="${API_PORT}" \
      "${VENV_PY}" -m uvicorn gemma_routing.api:app --host 0.0.0.0 --port "${API_PORT}" \
      >"${API_LOG_FILE}" 2>&1 </dev/null &
  else
    nohup env \
      PYTHONPATH="${PROJECT_DIR}/src" \
      ROUTER_MODEL_ENDPOINT="http://127.0.0.1:8080/v1/chat/completions" \
      ROUTER_MODEL_NAME="gemma4-routing" \
      ROUTER_API_PORT="${API_PORT}" \
      "${VENV_PY}" -m uvicorn gemma_routing.api:app --host 0.0.0.0 --port "${API_PORT}" \
      >"${API_LOG_FILE}" 2>&1 </dev/null &
  fi

  local api_pid=$!
  echo "${api_pid}" > "${API_PID_FILE}"
  echo "Starting first-router api on port ${API_PORT} (${api_pid})"
  wait_http_ready "${API_URL}" 90 "${api_pid}"
  echo "Routing API log: ${API_LOG_FILE}"
}

show_status() {
  "${MODEL_SCRIPT}" status || true
  if [[ -f "${API_PID_FILE}" ]]; then
    local pid
    pid="$(cat "${API_PID_FILE}")"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      echo "Routing API: running (pid=${pid}, port=${API_PORT})"
      return 0
    fi
  fi

  if ss -ltn "sport = :${API_PORT}" 2>/dev/null | grep -q ":${API_PORT}"; then
    echo "Routing API: listening on port ${API_PORT}"
  else
    echo "Routing API: not running"
  fi
}

case "${ACTION}" in
  start)
    "${MODEL_SCRIPT}" start "$@"
    start_router_api
    ;;
  restart)
    stop_pidfile_process "${API_PID_FILE}" "first-router api"
    stop_port_listener "${API_PORT}"
    "${MODEL_SCRIPT}" restart "$@"
    start_router_api
    ;;
  start-mm)
    "${MODEL_SCRIPT}" stop >/dev/null 2>&1 || true
    ENABLE_MMPROJ=1 \
    MMPROJ_OFFLOAD="${MMPROJ_OFFLOAD:-1}" \
    GPU_LAYERS="${GPU_LAYERS:-30}" \
    BATCH_SIZE="${BATCH_SIZE:-256}" \
    UBATCH_SIZE="${UBATCH_SIZE:-256}" \
    "${MODEL_SCRIPT}" start "$@"
    start_router_api
    ;;
  restart-mm)
    stop_pidfile_process "${API_PID_FILE}" "first-router api"
    stop_port_listener "${API_PORT}"
    ENABLE_MMPROJ=1 \
    MMPROJ_OFFLOAD="${MMPROJ_OFFLOAD:-1}" \
    GPU_LAYERS="${GPU_LAYERS:-30}" \
    BATCH_SIZE="${BATCH_SIZE:-256}" \
    UBATCH_SIZE="${UBATCH_SIZE:-256}" \
    "${MODEL_SCRIPT}" restart "$@"
    start_router_api
    ;;
  stop)
    stop_pidfile_process "${API_PID_FILE}" "first-router api"
    stop_port_listener "${API_PORT}"
    "${MODEL_SCRIPT}" stop
    ;;
  status)
    show_status
    ;;
  ready)
    "${MODEL_SCRIPT}" ready
    wait_http_ready "${API_URL}" 10
    ;;
  logs)
    if [[ -f "${API_LOG_FILE}" ]]; then
      tail -n 80 "${API_LOG_FILE}"
    else
      echo "No routing API log file yet: ${API_LOG_FILE}"
    fi
    ;;
  model-logs)
    "${MODEL_SCRIPT}" logs
    ;;
  test|sample|trace|stream)
    "${MODEL_SCRIPT}" "${ACTION}" "$@"
    ;;
  image-sample)
    exec "${PYTHON_BIN}" "${PROJECT_DIR}/scripts/infer_image.py" \
      --image "${1:-${DEFAULT_IMAGE}}" \
      --prompt-file "${DEFAULT_SCENE_PROMPT}"
    ;;
  image-coordinate)
    exec "${PYTHON_BIN}" "${PROJECT_DIR}/scripts/infer_image.py" \
      --image "${1:-${DEFAULT_IMAGE}}" \
      --prompt-file "${DEFAULT_COORDINATE_PROMPT}" \
      --temperature 0 \
      --max-tokens 8
    ;;
  *)
    echo "Usage: $0 [start|restart|start-mm|restart-mm|stop|status|ready|logs|model-logs|test|sample|trace|stream|image-sample|image-coordinate] [args...]" >&2
    exit 1
    ;;
esac
