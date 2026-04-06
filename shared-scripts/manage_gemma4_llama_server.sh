#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-status}"
MODEL_VARIANT="${MODEL_VARIANT:-${2:-e4b-q4}}"
CTX_SIZE="${CTX_SIZE:-${3:-4096}}"
PORT="${PORT:-${4:-8080}}"
ALIAS="${ALIAS:-${5:-gemma4-shared}}"
CONTAINER_NAME="${CONTAINER_NAME:-${6:-gemma4-${MODEL_VARIANT}-${PORT}}}"

IMAGE="ghcr.io/nvidia-ai-iot/llama_cpp:gemma4-jetson-orin"
RUN_SCRIPT="${RUN_SCRIPT:-/home/rb/AI/shared-scripts/run_gemma4_llama_server.sh}"
DEFAULT_SAMPLE_REQUEST="${DEFAULT_SAMPLE_REQUEST:-/home/rb/AI/gemma-routing/examples/medical_router_request.json}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/gemma4}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-180}"

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

mkdir -p "${OUTPUT_DIR}"

find_matching_containers() {
  "${DOCKER_CMD[@]}" ps -a --filter "ancestor=${IMAGE}" --format '{{.ID}} {{.Names}}'
}

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

  "${DOCKER_CMD[@]}" ps -a --filter "ancestor=${IMAGE}" --format '{{.Names}}' | head -n 1
}

stop_matching_containers() {
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

stop_all_gemma_containers() {
  local matches
  matches="$(find_matching_containers || true)"
  if [[ -z "${matches}" ]]; then
    echo "No existing Gemma llama.cpp containers found."
    return 0
  fi

  while read -r cid cname; do
    [[ -z "${cid:-}" ]] && continue
    echo "Stopping existing Gemma container ${cname} (${cid})"
    "${DOCKER_CMD[@]}" rm -f "${cid}" >/dev/null 2>&1 || true
  done <<<"${matches}"
}

follow_container_logs() {
  local first_name

  first_name="$(resolve_container_name)"
  if [[ -n "${first_name}" ]]; then
    exec "${DOCKER_CMD[@]}" logs -f "${first_name}"
  fi

  echo "No Gemma container found for logs." >&2
  exit 1
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

def print_recent_logs():
    try:
        cmd = f"{docker_cmd} logs --tail 40 {container_name}"
        result = subprocess.run(
            cmd,
            shell=True,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.stdout.strip():
            print("recent_logs_start")
            print(result.stdout.rstrip())
            print("recent_logs_end")
        if result.stderr.strip():
            print("recent_logs_stderr_start")
            print(result.stderr.rstrip())
            print("recent_logs_stderr_end")
    except Exception as exc:
        print(f"log_fetch_failed={exc}")

print("waiting_for_server=1")
sys.stdout.flush()

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
        print_recent_logs()
        sys.exit(1)

    print(f"waiting_s={elapsed:.1f}")
    sys.stdout.flush()
    time.sleep(2)
PY
}

run_http_request() {
  local payload_path="$1"
  local response_path="$2"

  python3 - <<PY
import json
import sys
import time
import threading
import urllib.request
from pathlib import Path

payload_path = Path(${payload_path@Q})
response_path = Path(${response_path@Q})
url = "http://127.0.0.1:${PORT}/v1/chat/completions"

if not payload_path.exists():
    print(f"request_failed=payload_not_found:{payload_path}")
    sys.exit(1)

started_ts = time.time()
started_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_ts))
payload_raw = payload_path.read_text(encoding="utf-8")

try:
    payload = json.loads(payload_raw)
except json.JSONDecodeError as exc:
    print(f"request_failed=invalid_json:{exc}")
    sys.exit(1)

print("started_at=", started_at)
print("request_file=", str(payload_path))
print("payload_bytes=", len(payload_raw.encode("utf-8")))
print("model=", payload.get("model"))
print("message_count=", len(payload.get("messages", [])))
sys.stdout.flush()

stop_event = threading.Event()

def heartbeat():
    while not stop_event.wait(5):
        print(f"waiting_s={time.time() - started_ts:.1f}")
        sys.stdout.flush()

heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
heartbeat_thread.start()

req = urllib.request.Request(
    url,
    data=payload_raw.encode("utf-8"),
    headers={"Content-Type": "application/json"},
)

try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = resp.read()
        status = resp.getcode()
except Exception as exc:
    stop_event.set()
    print(f"request_failed={exc}")
    sys.exit(1)
finally:
    stop_event.set()
    heartbeat_thread.join(timeout=1)

elapsed = time.time() - started_ts
response_path.write_bytes(body)

try:
    data = json.loads(body.decode("utf-8"))
except Exception as exc:
    print(f"http_status={status}")
    print(f"elapsed_s={elapsed:.2f}")
    print(f"response_parse_failed={exc}")
    print("response_file=", str(response_path))
    sys.exit(1)

choice = (data.get("choices") or [{}])[0]
message = choice.get("message") or {}
content = message.get("content")
timings = data.get("timings")
usage = data.get("usage")

if isinstance(content, list):
    preview = json.dumps(content, ensure_ascii=False)
else:
    preview = str(content)

preview = preview.replace("\\n", " ")
if len(preview) > 240:
    preview = preview[:240] + "..."

print(f"http_status={status}")
print(f"elapsed_s={elapsed:.2f}")
print("finish_reason=", choice.get("finish_reason"))
print("content_preview=", preview)
print("usage=", usage)
print("timings=", timings)
print("response_file=", str(response_path))
PY
}

trace_request_with_logs() {
  local payload_path="$1"
  local container_name
  local stamp
  local log_path
  local response_path
  local log_pid
  local request_rc

  container_name="$(resolve_container_name)"
  if [[ -z "${container_name}" ]]; then
    echo "No Gemma container found for tracing." >&2
    exit 1
  fi

  stamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  log_path="${OUTPUT_DIR}/trace_$(date +%Y%m%d_%H%M%S).server.log"
  response_path="${OUTPUT_DIR}/trace_$(date +%Y%m%d_%H%M%S).response.json"

  echo "container_name=${container_name}"
  echo "server_log_file=${log_path}"
  echo "response_file=${response_path}"
  echo "following_server_logs=1"

  (
    "${DOCKER_CMD[@]}" logs -f --since "${stamp}" "${container_name}" 2>&1 \
      | awk '{print "[server] " $0; fflush()}' \
      | tee "${log_path}"
  ) &
  log_pid=$!

  sleep 1

  set +e
  run_http_request "${payload_path}" "${response_path}"
  request_rc=$?
  set -e

  kill "${log_pid}" >/dev/null 2>&1 || true
  wait "${log_pid}" 2>/dev/null || true

  return "${request_rc}"
}

stream_http_request() {
  local payload_path="$1"
  local stream_log_path="$2"

  python3 - <<PY
import json
import sys
import time
import threading
import urllib.request
from pathlib import Path

payload_path = Path(${payload_path@Q})
stream_log_path = Path(${stream_log_path@Q})
url = "http://127.0.0.1:${PORT}/v1/chat/completions"

if not payload_path.exists():
    print(f"request_failed=payload_not_found:{payload_path}")
    sys.exit(1)

started_ts = time.time()
started_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_ts))
payload = json.loads(payload_path.read_text(encoding="utf-8"))
payload["stream"] = True
payload_raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")

print("started_at=", started_at)
print("request_file=", str(payload_path))
print("stream_mode=1")
print("stream_log_file=", str(stream_log_path))
print("content_start")
sys.stdout.flush()

stop_event = threading.Event()

def heartbeat():
    while not stop_event.wait(5):
        print(f"waiting_s={time.time() - started_ts:.1f}")
        sys.stdout.flush()

heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
heartbeat_thread.start()

req = urllib.request.Request(
    url,
    data=payload_raw,
    headers={"Content-Type": "application/json"},
)

stream_log_path.parent.mkdir(parents=True, exist_ok=True)
with stream_log_path.open("w", encoding="utf-8") as log_fp:
    try:
        active_channel = None

        def extract_text(value):
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                parts = []
                for item in value:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(item.get("text", ""))
                return "".join(parts)
            return ""

        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", "replace").strip()
                if not line:
                    continue
                log_fp.write(line + "\\n")
                log_fp.flush()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                reasoning_text = extract_text(delta.get("reasoning_content"))
                content_text = extract_text(delta.get("content"))

                if reasoning_text:
                    if active_channel != "reasoning":
                        if active_channel is not None:
                            print()
                        print("[thinking] ", end="", flush=True)
                        active_channel = "reasoning"
                    print(reasoning_text, end="", flush=True)

                if content_text:
                    if active_channel != "content":
                        if active_channel is not None:
                            print()
                        print("[answer] ", end="", flush=True)
                        active_channel = "content"
                    print(content_text, end="", flush=True)
    except Exception as exc:
        stop_event.set()
        print()
        print(f"request_failed={exc}")
        sys.exit(1)
    finally:
        stop_event.set()
        heartbeat_thread.join(timeout=1)

elapsed = time.time() - started_ts
print()
print("content_end")
print(f"elapsed_s={elapsed:.2f}")
print("stream_log_file=", str(stream_log_path))
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
    stop_matching_containers
    ;;
  start)
    stop_all_gemma_containers
    CONTAINER_NAME="${CONTAINER_NAME}" RUN_MODE=detached "${RUN_SCRIPT}" "${MODEL_VARIANT}" "${CTX_SIZE}" "${PORT}" "${ALIAS}"
    wait_until_ready "${WAIT_TIMEOUT}"
    ;;
  restart)
    stop_all_gemma_containers
    CONTAINER_NAME="${CONTAINER_NAME}" RUN_MODE=detached "${RUN_SCRIPT}" "${MODEL_VARIANT}" "${CTX_SIZE}" "${PORT}" "${ALIAS}"
    wait_until_ready "${WAIT_TIMEOUT}"
    ;;
  startlogs)
    stop_all_gemma_containers
    CONTAINER_NAME="${CONTAINER_NAME}" RUN_MODE=detached "${RUN_SCRIPT}" "${MODEL_VARIANT}" "${CTX_SIZE}" "${PORT}" "${ALIAS}"
    echo "Following container logs. Press Ctrl+C to stop viewing logs only."
    follow_container_logs
    ;;
  restartlogs)
    stop_all_gemma_containers
    CONTAINER_NAME="${CONTAINER_NAME}" RUN_MODE=detached "${RUN_SCRIPT}" "${MODEL_VARIANT}" "${CTX_SIZE}" "${PORT}" "${ALIAS}"
    echo "Following container logs. Press Ctrl+C to stop viewing logs only."
    follow_container_logs
    ;;
  ready)
    wait_until_ready "${WAIT_TIMEOUT}"
    ;;
  logs)
    follow_container_logs
    ;;
  test)
    wait_until_ready "${WAIT_TIMEOUT}"
    test_request="${OUTPUT_DIR}/test_request.json"
    cat > "${test_request}" <<EOF
{"model":"${ALIAS}","messages":[{"role":"user","content":"Reply with just OK"}],"max_tokens":16}
EOF
    run_http_request "${test_request}" "${OUTPUT_DIR}/test_response.json"
    ;;
  sample)
    sample_request="${2:-${DEFAULT_SAMPLE_REQUEST}}"
    wait_until_ready "${WAIT_TIMEOUT}"
    run_http_request "${sample_request}" "${OUTPUT_DIR}/sample_response.json"
    ;;
  trace)
    sample_request="${2:-${DEFAULT_SAMPLE_REQUEST}}"
    wait_until_ready "${WAIT_TIMEOUT}"
    trace_request_with_logs "${sample_request}"
    ;;
  stream)
    sample_request="${2:-${DEFAULT_SAMPLE_REQUEST}}"
    wait_until_ready "${WAIT_TIMEOUT}"
    stream_http_request "${sample_request}" "${OUTPUT_DIR}/stream_$(date +%Y%m%d_%H%M%S).log"
    ;;
  *)
    echo "Usage: $0 [status|start|stop|restart|startlogs|restartlogs|ready|logs|test|sample|trace|stream] [args...]" >&2
    exit 1
    ;;
esac
