#!/usr/bin/env bash
set -euo pipefail

SERVER="${SERVER:-http://127.0.0.1:8080/v1/chat/completions}"
MODEL="${MODEL:-gemma4-routing}"
PROMPT="${PROMPT:-휠체어 위치만 답해. 좌상, 우상, 좌하, 우하, 중앙 중 하나만 출력해.}"
TEMPERATURE="${TEMPERATURE:-0}"
MAX_TOKENS="${MAX_TOKENS:-8}"
DEFAULT_IMAGE="/home/rb/AI/llama-rest-core/test-assets/public-research/중앙.jpg"

if [[ $# -eq 0 ]]; then
  set -- "${DEFAULT_IMAGE}"
fi

for image_path in "$@"; do
  if [[ ! -f "${image_path}" ]]; then
    echo "image_not_found=${image_path}" >&2
    exit 1
  fi

  payload="$(
    IMAGE_PATH="${image_path}" \
    MODEL="${MODEL}" \
    PROMPT="${PROMPT}" \
    TEMPERATURE="${TEMPERATURE}" \
    MAX_TOKENS="${MAX_TOKENS}" \
    python3 - <<'PY'
import base64
import json
import mimetypes
import os
from pathlib import Path

image_path = Path(os.environ["IMAGE_PATH"])
mime_type, _ = mimetypes.guess_type(image_path.name)
if mime_type is None:
    mime_type = "image/jpeg"

data_url = "data:{};base64,{}".format(
    mime_type,
    base64.b64encode(image_path.read_bytes()).decode("ascii"),
)

payload = {
    "model": os.environ["MODEL"],
    "temperature": float(os.environ["TEMPERATURE"]),
    "max_tokens": int(os.environ["MAX_TOKENS"]),
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": os.environ["PROMPT"]},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ],
}

print(json.dumps(payload, ensure_ascii=False))
PY
  )"

  echo "=== $(basename "${image_path}") ==="
  printf '%s' "${payload}" | curl -sS "${SERVER}" \
    -H 'Content-Type: application/json' \
    --data-binary @-
  echo
done
