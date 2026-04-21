#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/rb/AI/e2b-vision-test"
MODEL_SCRIPT="${PROJECT_DIR}/scripts/manage_local_gemma.sh"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DEFAULT_IMAGE="${DEFAULT_IMAGE:-/home/rb/AI/llama-rest-core/test-assets/public-research/중앙.jpg}"
DEFAULT_SCENE_PROMPT="${PROJECT_DIR}/examples/sample_scene_prompt.txt"
DEFAULT_COORDINATE_PROMPT="${PROJECT_DIR}/examples/sample_coordinate_prompt.txt"
KNOWN_ACTIONS="start restart start-exclusive restart-exclusive stop status ready logs sample sample-coordinate"
ACTION="start"

if [[ $# -gt 0 ]]; then
  case " ${KNOWN_ACTIONS} " in
    *" $1 "*)
      ACTION="$1"
      shift || true
      ;;
  esac
fi

case "${ACTION}" in
  start|restart|start-exclusive|restart-exclusive|stop|status|ready|logs)
    exec "${MODEL_SCRIPT}" "${ACTION}" "$@"
    ;;
  sample)
    exec "${PYTHON_BIN}" "${PROJECT_DIR}/scripts/infer_image.py" \
      --image "${1:-${DEFAULT_IMAGE}}" \
      --prompt-file "${DEFAULT_SCENE_PROMPT}"
    ;;
  sample-coordinate)
    exec "${PYTHON_BIN}" "${PROJECT_DIR}/scripts/infer_image.py" \
      --image "${1:-${DEFAULT_IMAGE}}" \
      --prompt-file "${DEFAULT_COORDINATE_PROMPT}"
    ;;
  *)
    echo "Usage: $0 [start|restart|stop|status|ready|logs|sample|sample-coordinate] [args...]" >&2
    exit 1
    ;;
esac
