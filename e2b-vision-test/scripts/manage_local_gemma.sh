#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/rb/AI"
PROJECT_DIR="${ROOT_DIR}/e2b-vision-test"
ACTION="${1:-status}"
MODEL_VARIANT="${2:-e2b}"
CTX_SIZE="${3:-2048}"
PORT="${4:-8083}"
ALIAS="${5:-gemma4-vision-e2b}"
CONTAINER_NAME="${6:-e2b-vision-test-${MODEL_VARIANT}-${PORT}}"
RUN_SCRIPT="${PROJECT_DIR}/scripts/run_local_gemma.sh"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/e2b-vision-test}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-180}"
DEFAULT_IMAGE="${DEFAULT_IMAGE:-/home/rb/AI/llama-rest-core/test-assets/public-research/중앙.jpg}"
IMAGE="ghcr.io/nvidia-ai-iot/llama_cpp:gemma4-jetson-orin"

mkdir -p "${OUTPUT_DIR}"

has_command() {
  command -v "$1" >/dev/null 2>&1
}

stream_contains_exact_line() {
  local pattern="$1"
  if has_command rg; then
    rg -xq "${pattern}"
  else
    grep -Fxq "${pattern}"
  fi
}

filter_port_listeners() {
  local pattern=":${PORT}[[:space:]]"
  if has_command rg; then
    rg "${pattern}" || true
  else
    grep -E "${pattern}" || true
  fi
}

if docker info >/dev/null 2>&1; then
  DOCKER_CMD=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  DOCKER_CMD=(sudo -n docker)
else
  echo "Docker is not accessible for the current user, and passwordless sudo is unavailable." >&2
  exit 1
fi

find_target_container() {
  "${DOCKER_CMD[@]}" ps -a \
    --filter "name=^/${CONTAINER_NAME}$" \
    --format '{{.ID}} {{.Names}}'
}

resolve_container_name() {
  if "${DOCKER_CMD[@]}" ps -a --format '{{.Names}}' | stream_contains_exact_line "${CONTAINER_NAME}"; then
    printf '%s\n' "${CONTAINER_NAME}"
    return 0
  fi
  return 1
}

stop_matching_container() {
  local matches
  matches="$(find_target_container || true)"
  if [[ -z "${matches}" ]]; then
    echo "No Gemma llama.cpp container found for ${CONTAINER_NAME}."
    return 0
  fi

  while read -r cid cname; do
    [[ -z "${cid:-}" ]] && continue
    echo "Stopping ${cname} (${cid})"
    "${DOCKER_CMD[@]}" rm -f "${cid}" >/dev/null 2>&1 || true
  done <<<"${matches}"
}

follow_container_logs() {
  local name
  name="$(resolve_container_name || true)"
  if [[ -z "${name}" ]]; then
    echo "No Gemma container found for logs." >&2
    exit 1
  fi
  exec "${DOCKER_CMD[@]}" logs -f "${name}"
}

stop_other_gemma_containers() {
  local matches
  matches="$("${DOCKER_CMD[@]}" ps -a --filter "ancestor=${IMAGE}" --format '{{.ID}} {{.Names}}' || true)"
  if [[ -z "${matches}" ]]; then
    echo "No other Gemma llama.cpp containers found."
    return 0
  fi

  while read -r cid cname; do
    [[ -z "${cid:-}" ]] && continue
    if [[ "${cname}" == "${CONTAINER_NAME}" ]]; then
      continue
    fi
    echo "Stopping competing Gemma container ${cname} (${cid})"
    "${DOCKER_CMD[@]}" rm -f "${cid}" >/dev/null 2>&1 || true
  done <<<"${matches}"
}

wait_until_ready() {
  local timeout_s="${1:-${WAIT_TIMEOUT}}"

  python3 - <<PY
import json
import subprocess
import sys
import time
import urllib.request
from urllib.error import URLError, HTTPError

url = "http://127.0.0.1:${PORT}/v1/models"
timeout_s = int(${timeout_s})
started_ts = time.time()
last_error = None
container_name = ${CONTAINER_NAME@Q}
docker_cmd = ${DOCKER_CMD[*]@Q}

def get_container_state():
    try:
        cmd = f"{docker_cmd} inspect --format '{{{{.State.Status}}}}' {container_name}"
        result = subprocess.run(
            cmd,
            shell=True,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return "missing"
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"

while True:
    elapsed = time.time() - started_ts
    if elapsed > timeout_s:
        print(f"ready=0 timeout_s={timeout_s}")
        if last_error:
            print(f"last_error={last_error}")
        sys.exit(1)

    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = resp.read().decode("utf-8", "replace")
            data = json.loads(body)
            models = [item.get("id") for item in data.get("data", [])]
            print(f"ready=1 elapsed_s={elapsed:.1f}")
            print(f"models={models}")
            sys.exit(0)
    except (URLError, HTTPError, json.JSONDecodeError, TimeoutError) as exc:
        last_error = exc

    state = get_container_state()
    if state in {"exited", "dead", "missing"}:
        print(f"ready=0 container_state={state}")
        if last_error:
            print(f"last_error={last_error}")
        sys.exit(1)

    print(f"waiting_s={elapsed:.1f}")
    sys.stdout.flush()
    time.sleep(2)
PY
}

case "${ACTION}" in
  status)
    echo "Gemma container for ${CONTAINER_NAME}:"
    find_target_container || true
    echo
    echo "Port listeners:"
    ss -ltnp | filter_port_listeners
    ;;
  stop)
    stop_matching_container
    ;;
  start)
    stop_matching_container
    CONTAINER_NAME="${CONTAINER_NAME}" RUN_MODE=detached "${RUN_SCRIPT}" "${MODEL_VARIANT}" "${CTX_SIZE}" "${PORT}" "${ALIAS}"
    wait_until_ready "${WAIT_TIMEOUT}"
    ;;
  restart)
    stop_matching_container
    CONTAINER_NAME="${CONTAINER_NAME}" RUN_MODE=detached "${RUN_SCRIPT}" "${MODEL_VARIANT}" "${CTX_SIZE}" "${PORT}" "${ALIAS}"
    wait_until_ready "${WAIT_TIMEOUT}"
    ;;
  start-exclusive)
    stop_other_gemma_containers
    stop_matching_container
    CONTAINER_NAME="${CONTAINER_NAME}" RUN_MODE=detached "${RUN_SCRIPT}" "${MODEL_VARIANT}" "${CTX_SIZE}" "${PORT}" "${ALIAS}"
    wait_until_ready "${WAIT_TIMEOUT}"
    ;;
  restart-exclusive)
    stop_other_gemma_containers
    stop_matching_container
    CONTAINER_NAME="${CONTAINER_NAME}" RUN_MODE=detached "${RUN_SCRIPT}" "${MODEL_VARIANT}" "${CTX_SIZE}" "${PORT}" "${ALIAS}"
    wait_until_ready "${WAIT_TIMEOUT}"
    ;;
  ready)
    wait_until_ready "${WAIT_TIMEOUT}"
    ;;
  logs)
    follow_container_logs
    ;;
  *)
    echo "Usage: $0 [start|restart|start-exclusive|restart-exclusive|stop|status|ready|logs] [model_variant] [ctx_size] [port] [alias] [container_name]" >&2
    exit 1
    ;;
esac
