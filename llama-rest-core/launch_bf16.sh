#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="/tmp/gemma4-bf16"
PID_FILE="${RUN_DIR}/gemma4-bf16.pid"
LOG_FILE="${RUN_DIR}/gemma4-bf16.log"
PORT="${GEMMA4_BF16_PORT:-18088}"
MODEL_DIR="${GEMMA4_BF16_MODEL_DIR:-/home/rbiotech-server/llama_Rest/models/gemma4-31b-bf16}"
ACTION="${1:-start}"
VISION_BUDGET="${GEMMA4_BF16_VISION_BUDGET:-280}"

mkdir -p "${RUN_DIR}"

stop_server() {
  if [[ -f "${PID_FILE}" ]]; then
    local pid
    pid="$(cat "${PID_FILE}")"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      echo "Stopping gemma4-bf16 (${pid})"
      kill "${pid}" >/dev/null 2>&1 || true
      sleep 2
      kill -9 "${pid}" >/dev/null 2>&1 || true
    fi
    rm -f "${PID_FILE}"
  fi
  fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
}

wait_ready() {
  python3 - <<PY
import sys
import time
import urllib.request

url = "http://127.0.0.1:${PORT}/healthz"
started = time.time()
while True:
    if time.time() - started > 900:
        print("ready=0 timeout=1")
        sys.exit(1)
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            print(f"ready=1 status={resp.getcode()}")
            sys.exit(0)
    except Exception:
        time.sleep(2)
PY
}

case "${ACTION}" in
  start)
    stop_server
    echo "Starting gemma4-bf16 on port ${PORT}"
    setsid env \
      GEMMA4_BF16_PORT="${PORT}" \
      GEMMA4_BF16_MODEL_DIR="${MODEL_DIR}" \
      GEMMA4_BF16_VISION_BUDGET="${VISION_BUDGET}" \
      python3 "${SCRIPT_DIR}/gemma4_bf16_server.py" >"${LOG_FILE}" 2>&1 < /dev/null &
    echo "$!" > "${PID_FILE}"
    wait_ready
    echo "log: ${LOG_FILE}"
    ;;
  restart)
    stop_server
    "$0" start
    ;;
  stop)
    stop_server
    ;;
  status)
    if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" >/dev/null 2>&1; then
      echo "gemma4-bf16: running (pid=$(cat "${PID_FILE}"), port=${PORT})"
    else
      echo "gemma4-bf16: not running"
    fi
    ;;
  logs)
    tail -n 120 "${LOG_FILE}"
    ;;
  *)
    echo "Usage: $0 [start|restart|stop|status|logs]" >&2
    exit 1
    ;;
esac
