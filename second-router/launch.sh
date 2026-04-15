#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}"
ENV_FILE="${PROJECT_DIR}/.env"
VENV_DIR="${PROJECT_DIR}/.venv"
VENV_PY="${VENV_DIR}/bin/python"
API_PORT="${SERVER_ROUTER_API_PORT:-8190}"
API_URL="http://127.0.0.1:${API_PORT}/healthz"
RUN_DIR="/tmp/gemma-server-router"
API_PID_FILE="${RUN_DIR}/server-router-api.pid"
API_LOG_FILE="${RUN_DIR}/server-router-api.log"
BOOTSTRAP_DIR="${RUN_DIR}/bootstrap"
GET_PIP_PY="${BOOTSTRAP_DIR}/get-pip.py"
KNOWN_ACTIONS="start restart stop status ready logs"
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

ensure_runtime() {
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

start_api() {
  stop_pidfile_process "${API_PID_FILE}" "gemma-server-router api"
  stop_port_listener "${API_PORT}"
  ensure_runtime

  nohup env \
    PYTHONPATH="${PROJECT_DIR}/src" \
    SERVER_ROUTER_API_PORT="${API_PORT}" \
    "${VENV_PY}" -m uvicorn gemma_server_router.api:app --host 0.0.0.0 --port "${API_PORT}" >"${API_LOG_FILE}" 2>&1 &

  local api_pid=$!
  echo "${api_pid}" > "${API_PID_FILE}"
  echo "Starting gemma-server-router api on port ${API_PORT} (${api_pid})"
  echo "Model endpoint: ${SERVER_ROUTER_MODEL_ENDPOINT:-http://127.0.0.1:8180/v1/chat/completions}"
  wait_http_ready "${API_URL}" 90 "${api_pid}"
  echo "Server Router API log: ${API_LOG_FILE}"
}

show_status() {
  if [[ -f "${API_PID_FILE}" ]]; then
    local pid
    pid="$(cat "${API_PID_FILE}")"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      echo "Server Router API: running (pid=${pid}, port=${API_PORT})"
      echo "Model endpoint: ${SERVER_ROUTER_MODEL_ENDPOINT:-http://127.0.0.1:8180/v1/chat/completions}"
      return 0
    fi
  fi

  if ss -ltn "sport = :${API_PORT}" 2>/dev/null | grep -q ":${API_PORT}"; then
    echo "Server Router API: listening on port ${API_PORT}"
  else
    echo "Server Router API: not running"
  fi
}

case "${ACTION}" in
  start)
    start_api
    ;;
  restart)
    stop_pidfile_process "${API_PID_FILE}" "gemma-server-router api"
    stop_port_listener "${API_PORT}"
    start_api
    ;;
  stop)
    stop_pidfile_process "${API_PID_FILE}" "gemma-server-router api"
    stop_port_listener "${API_PORT}"
    ;;
  status)
    show_status
    ;;
  ready)
    wait_http_ready "${API_URL}" 10
    ;;
  logs)
    if [[ -f "${API_LOG_FILE}" ]]; then
      tail -n 120 "${API_LOG_FILE}"
    else
      echo "No server router API log file yet: ${API_LOG_FILE}"
    fi
    ;;
  *)
    echo "Usage: $0 [start|restart|stop|status|ready|logs]" >&2
    exit 1
    ;;
esac
