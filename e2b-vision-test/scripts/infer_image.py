#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
import time
import urllib.request
from pathlib import Path


DEFAULT_SERVER = "http://127.0.0.1:8083/v1/chat/completions"
DEFAULT_MODEL = "gemma4-vision-e2b"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a local image to the E2B multimodal llama-server.")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="chat completions endpoint")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="model alias")
    parser.add_argument("--image", required=True, help="local image path")
    parser.add_argument("--prompt", help="prompt string")
    parser.add_argument("--prompt-file", help="UTF-8 text file containing the prompt")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--save", help="optional path to save the raw JSON response")
    return parser.parse_args()


def load_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8").strip()
    if args.prompt:
        return args.prompt.strip()
    return "이미지에서 보이는 주요 내용만 한국어로 간단히 설명해줘."


def image_to_data_url(image_path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(image_path.name)
    if mime_type is None:
        mime_type = "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_payload(args: argparse.Namespace, prompt: str, data_url: str) -> dict:
    return {
        "model": args.model,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
    }


def main() -> int:
    args = parse_args()
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"image_not_found={image_path}", file=sys.stderr)
        return 1

    prompt = load_prompt(args)
    data_url = image_to_data_url(image_path)
    payload = build_payload(args, prompt, data_url)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        args.server,
        data=body,
        headers={"Content-Type": "application/json"},
    )

    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.getcode()
    except Exception as exc:
        print(f"request_failed={exc}", file=sys.stderr)
        return 1

    elapsed = time.time() - started
    if args.save:
        Path(args.save).write_text(raw, encoding="utf-8")

    print(f"http_status={status}")
    print(f"elapsed_s={elapsed:.3f}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(raw)
        return 0

    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        print(json.dumps(content, ensure_ascii=False, indent=2))
    else:
        print(content if content is not None else json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
