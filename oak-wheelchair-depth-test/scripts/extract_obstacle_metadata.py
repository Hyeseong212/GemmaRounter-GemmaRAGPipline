#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-dir",
        default=(
            "/home/rbiotech-server/LLM_Harnes_Support/"
            "GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/"
            "test-assets/korean-hospital-obstacles"
        ),
    )
    parser.add_argument(
        "--server",
        default="http://127.0.0.1:18088/infer",
    )
    parser.add_argument("--timeout", type=int, default=300)
    return parser.parse_args()


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def extract_json_blob(text: str) -> dict[str, Any]:
    stripped = text.strip()
    stripped = stripped.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    stripped = re.sub(r"//.*", "", stripped)
    first_brace = stripped.find("{")
    if first_brace >= 0:
        stripped = stripped[first_brace:]
    try:
        decoder = json.JSONDecoder()
        payload, _ = decoder.raw_decode(stripped)
        return payload
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            raise
        decoder = json.JSONDecoder()
        payload, _ = decoder.raw_decode(match.group(0))
        return payload


def normalized_yx_to_pixels(location_yx_1000: list[int], width: int, height: int) -> dict[str, list[int]]:
    raw_y = int(location_yx_1000[0])
    raw_x = int(location_yx_1000[1])
    pixel_x = round((raw_x / 1000.0) * width)
    pixel_y_image = round((raw_y / 1000.0) * height)
    pixel_x = max(0, min(pixel_x, width))
    pixel_y_image = max(0, min(pixel_y_image, height))
    pixel_y_bottom_left = height - pixel_y_image
    return {
        "top_left": [pixel_x, pixel_y_image],
        "bottom_left": [pixel_x, pixel_y_bottom_left],
    }


def main() -> int:
    args = parse_args()
    dataset_dir = Path(args.dataset_dir)
    images_dir = dataset_dir / "images"
    results_dir = dataset_dir / "results"
    raw_dir = results_dir / "raw"
    manifest_path = dataset_dir / "sources.tsv"

    results_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    manifest = read_manifest(manifest_path)
    session = requests.Session()
    session.headers.update({"User-Agent": "oak-wheelchair-depth-test/1.0"})

    aggregate: list[dict[str, Any]] = []

    for item in manifest:
        image_path = images_dir / item["image_filename"]
        width, height = Image.open(image_path).size

        response = session.post(
            args.server,
            json={
                "prompt": PROMPT,
                "image_path": str(image_path),
            },
            timeout=args.timeout,
        )
        response.raise_for_status()

        raw_text = response.content.decode("utf-8", errors="replace")
        (raw_dir / f"{image_path.stem}.txt").write_text(raw_text, encoding="utf-8")

        payload = extract_json_blob(raw_text)
        obstacles = payload.get("obstacles", [])

        normalized_obstacles: list[dict[str, Any]] = []
        for obstacle in obstacles:
            location = obstacle.get("location_yx_1000")
            if not isinstance(location, list) or len(location) != 2:
                continue
            pixels = normalized_yx_to_pixels(location, width, height)
            normalized_obstacles.append(
                {
                    "class_name": obstacle.get("class_name", "unknown"),
                    "reason": obstacle.get("reason", ""),
                    "location_yx_1000": location,
                    "pixel_top_left": pixels["top_left"],
                    "pixel_bottom_left": pixels["bottom_left"],
                }
            )

        aggregate.append(
            {
                "image_filename": item["image_filename"],
                "title": item["title"],
                "source_name": item["source_name"],
                "source_page": item["source_page"],
                "image_url": item["image_url"],
                "note": item["note"],
                "image_width": width,
                "image_height": height,
                "obstacles": normalized_obstacles,
                "raw_response_path": f"results/raw/{image_path.stem}.txt",
            }
        )

    (results_dir / "obstacle_metadata.json").write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Korean Hospital Obstacle Metadata",
        "",
        f"- server: `{args.server}`",
        f"- prompt: `{PROMPT}`",
        "",
    ]
    for entry in aggregate:
        lines.append(f"## {entry['image_filename']}")
        lines.append(f"- title: {entry['title']}")
        lines.append(f"- source_name: {entry['source_name']}")
        lines.append(f"- source_page: {entry['source_page']}")
        lines.append(f"- image_size: {entry['image_width']}x{entry['image_height']}")
        if not entry["obstacles"]:
            lines.append("- obstacles: none parsed")
        for obstacle in entry["obstacles"]:
            lines.append(
                "- "
                f"{obstacle['class_name']} | yx_1000={obstacle['location_yx_1000']} | "
                f"bottom_left={obstacle['pixel_bottom_left']} | "
                f"top_left={obstacle['pixel_top_left']} | "
                f"reason={obstacle['reason']}"
            )
        lines.append("")
    (results_dir / "obstacle_summary.md").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
