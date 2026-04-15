#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = ROOT_DIR / "rag-answerer/test-corpus/mfds-korean-medical-device/text"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "rag-answerer/indexes/mfds-korean-medical-device-text-bge-m3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a dense embedding index from plain-text corpus files.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-name", type=str, default="BAAI/bge-m3")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument("--chunk-max-chars", type=int, default=700)
    return parser.parse_args()


def split_pages(raw_text: str) -> list[str]:
    pages: list[str] = []
    for page in raw_text.replace("\r\n", "\n").split("\f"):
        normalized = page.strip()
        if normalized:
            pages.append(normalized)
    if not pages and raw_text.strip():
        pages.append(raw_text.strip())
    return pages


def split_paragraphs(page_text: str) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in page_text.splitlines():
        normalized = re.sub(r"\s+", " ", line).strip()
        if not normalized:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(normalized)
    if current:
        paragraphs.append(" ".join(current))
    if not paragraphs and page_text.strip():
        paragraphs.append(re.sub(r"\s+", " ", page_text).strip())
    return paragraphs


def build_chunks(file_path: Path, max_chars: int) -> list[dict[str, object]]:
    raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
    pages = split_pages(raw_text)
    chunks: list[dict[str, object]] = []
    chunk_number = 0

    for page_index, page_text in enumerate(pages, start=1):
        paragraphs = split_paragraphs(page_text)
        current = ""
        for paragraph in paragraphs:
            if not current:
                current = paragraph
                continue
            if len(current) + len(paragraph) + 1 > max_chars:
                chunk_number += 1
                chunks.append(
                    {
                        "chunk_id": f"{file_path.stem}-p{page_index}-c{chunk_number}",
                        "source_file": file_path.name,
                        "page_label": str(page_index),
                        "text": current,
                        "search_text": current.lower(),
                    }
                )
                current = paragraph
            else:
                current += "\n"
                current += paragraph
        if current:
            chunk_number += 1
            chunks.append(
                {
                    "chunk_id": f"{file_path.stem}-p{page_index}-c{chunk_number}",
                    "source_file": file_path.name,
                    "page_label": str(page_index),
                    "text": current,
                    "search_text": current.lower(),
                }
            )
    return chunks


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    text_files = sorted(args.input_dir.glob("*.txt"))
    if not text_files:
        raise SystemExit(f"No .txt files found in {args.input_dir}")

    rows: list[dict[str, object]] = []
    document_stats: list[dict[str, object]] = []
    for text_file in text_files:
        chunks = build_chunks(text_file, max_chars=args.chunk_max_chars)
        rows.extend(chunks)
        document_stats.append(
            {
                "source": text_file.name,
                "chunk_count": len(chunks),
            }
        )

    if not rows:
        raise SystemExit("No text chunks were generated")

    model = SentenceTransformer(args.model_name, device=args.device)
    embeddings = model.encode(
        [str(row["text"]) for row in rows],
        batch_size=args.batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    embeddings = np.asarray(embeddings, dtype=np.float32)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(args.input_dir),
        "output_dir": str(args.output_dir),
        "model_name": args.model_name,
        "chunk_max_chars": args.chunk_max_chars,
        "batch_size": args.batch_size,
        "document_count": len(text_files),
        "chunk_count": len(rows),
        "embedding_dim": int(embeddings.shape[1]),
        "documents": document_stats,
    }

    np.save(args.output_dir / "embeddings.npy", embeddings)
    write_jsonl(args.output_dir / "chunks.jsonl", rows)
    write_json(args.output_dir / "manifest.json", manifest)

    print(f"[done] chunks={len(rows)}")
    print(f"[done] embeddings={args.output_dir / 'embeddings.npy'}")
    print(f"[done] metadata={args.output_dir / 'chunks.jsonl'}")
    print(f"[done] manifest={args.output_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
