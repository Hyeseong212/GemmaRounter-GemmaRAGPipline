#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import requests
from PIL import Image


PROMPT = (
    "다음 이미지를 보고 환자이송 로봇 주행을 방해할 수 있는 병원 실내 장애물을 가능한 한 빠짐없이 분류해라. "
    "최대 20개까지 허용하며, 중복 없이 실제 동선에 놓인 장애물만 골라라. "
    "병실, 병동, 복도, 로비에서 실제 동선에 놓인 물체만 고르고 장식물이나 벽면 사진은 제외해라. "
    "허용 클래스는 wheelchair, hospital_bed, bedside_table, chair, sofa, bench, medical_cart, iv_pole, "
    "monitor, sink, cabinet, person, stretcher, equipment, walker, reception_desk 이다. "
    'JSON만 출력해라. 형식은 {"obstacles":[{"class_name":"...","location_yx_1000":[0-1000,0-1000],'
    '"reason":"한 줄"}]} 이다. '
    "location_yx_1000는 이미지 내부 대략 위치를 [세로, 가로] 0~1000 정수로 적어라. "
    "설명문, 코드펜스, 마크다운 없이 JSON만 출력해라."
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--server", default="http://127.0.0.1:18088/infer")
    parser.add_argument("--output", default="")
    parser.add_argument("--timeout", type=int, default=300)
    return parser.parse_args()


def extract_json_blob(text: str) -> dict[str, Any]:
    stripped = text.strip()
    stripped = stripped.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    stripped = re.sub(r"//.*", "", stripped)
    first_brace = stripped.find("{")
    if first_brace >= 0:
        stripped = stripped[first_brace:]
    decoder = json.JSONDecoder()
    try:
        payload, _ = decoder.raw_decode(stripped)
        return payload
    except json.JSONDecodeError:
        match = re.search(r"\{.*", stripped, re.DOTALL)
        if not match:
            raise
        payload, _ = decoder.raw_decode(match.group(0))
        return payload


def normalized_yx_to_bottom_left(location_yx_1000: list[int], width: int, height: int) -> list[int]:
    raw_y = int(location_yx_1000[0])
    raw_x = int(location_yx_1000[1])
    pixel_x = round((raw_x / 1000.0) * width)
    pixel_y_image = round((raw_y / 1000.0) * height)
    pixel_x = max(0, min(pixel_x, width))
    pixel_y_image = max(0, min(pixel_y_image, height))
    pixel_y_bottom_left = height - pixel_y_image
    return [pixel_x, pixel_y_bottom_left]


def main() -> int:
    args = parse_args()
    image_dir = Path(args.image_dir)
    output_path = Path(args.output) if args.output else image_dir / "장애물_서술형_결과.txt"

    images = sorted(
        p for p in image_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )

    session = requests.Session()
    session.headers.update({"User-Agent": "oak-wheelchair-depth-test/1.0"})

    lines: list[str] = []
    lines.append("병원 이미지 장애물 서술형 결과")
    lines.append(f"server: {args.server}")
    lines.append(f"image_dir: {image_dir}")
    lines.append("")

    for image_path in images:
        width, height = Image.open(image_path).size
        response = session.post(
            args.server,
            json={"prompt": PROMPT, "image_path": str(image_path)},
            timeout=args.timeout,
        )
        response.raise_for_status()
        raw_text = response.content.decode("utf-8", errors="replace")

        lines.append(f"이미지명: {image_path.name}")
        lines.append(f"이미지 픽셀 크기: {width}x{height}")

        try:
            payload = extract_json_blob(raw_text)
            obstacles = payload.get("obstacles", [])
        except Exception as exc:
            lines.append(f"장애물 추출 실패: {exc}")
            lines.append("")
            continue

        if not obstacles:
            lines.append("장애물: 없음")
            lines.append("")
            continue

        lines.append(f"장애물 개수: {len(obstacles)}")
        for index, obstacle in enumerate(obstacles, start=1):
            location = obstacle.get("location_yx_1000")
            if not isinstance(location, list) or len(location) != 2:
                continue
            bottom_left = normalized_yx_to_bottom_left(location, width, height)
            class_name = obstacle.get("class_name", "unknown")
            reason = obstacle.get("reason", "")
            lines.append(
                f"{index}. 클래스: {class_name} | 위치 좌표(수학좌표): {bottom_left} | 설명: {reason}"
            )
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
