#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer


ROOT_DIR = Path("/home/rb/AI")
DEFAULT_PROFILE = ROOT_DIR / "gemma-rag/config/korean_medical_device_rag.env"
DEFAULT_INPUT_DIR = (
    ROOT_DIR / "gemma-rag/test-corpus/mfds-korean-medical-device/starter"
)
DEFAULT_OUTPUT_DIR = (
    ROOT_DIR / "gemma-rag/indexes/mfds-korean-medical-device-starter-kure-v1"
)


@dataclass
class Unit:
    text: str
    page: int
    token_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Chunk PDFs and build dense embeddings for gemma-rag."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Directory that contains PDFs to index.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to write chunks, manifest, and embeddings.",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE,
        help="Env-style retrieval profile file.",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default=None,
        help="Override embedding model name.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="Chunk size in tokens.",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=None,
        help="Chunk overlap in tokens.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Embedding batch size.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="Embedding device, for example cpu or cuda.",
    )
    return parser.parse_args()


def read_profile(path: Path) -> dict[str, str]:
    profile: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        profile[key.strip()] = value.strip()
    return profile


def read_pdf_text(pdf_path: Path) -> str:
    pdftotext = shutil_which("pdftotext")
    if pdftotext is not None:
        result = subprocess.run(
            [pdftotext, "-layout", "-enc", "UTF-8", str(pdf_path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\f".join(pages)


def split_pages(raw_text: str) -> list[str]:
    pages = []
    for page in raw_text.replace("\r\n", "\n").split("\f"):
        normalized = page.strip()
        if normalized:
            pages.append(normalized)
    return pages


def clean_paragraph(paragraph: str) -> str:
    lines = [line.strip() for line in paragraph.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ""
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def paragraph_units(page_text: str, page_num: int, tokenizer) -> list[Unit]:
    paragraphs = [clean_paragraph(part) for part in re.split(r"\n\s*\n+", page_text)]
    units: list[Unit] = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        token_count = len(tokenizer.encode(paragraph, add_special_tokens=False))
        units.extend(split_oversized_unit(paragraph, page_num, token_count, tokenizer))
    return units


def split_oversized_unit(
    text: str, page_num: int, token_count: int, tokenizer
) -> list[Unit]:
    max_tokens = tokenizer.model_max_length
    if token_count <= max_tokens:
        return [Unit(text=text, page=page_num, token_count=token_count)]

    token_ids = tokenizer.encode(text, add_special_tokens=False)
    units: list[Unit] = []
    for start in range(0, len(token_ids), max_tokens):
        window = token_ids[start : start + max_tokens]
        chunk_text = tokenizer.decode(window, skip_special_tokens=True).strip()
        if not chunk_text:
            continue
        units.append(Unit(text=chunk_text, page=page_num, token_count=len(window)))
    return units


def build_chunks(
    units: list[Unit], chunk_size: int, chunk_overlap: int
) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    start = 0
    chunk_number = 1
    while start < len(units):
        token_total = 0
        end = start
        selected: list[Unit] = []
        while end < len(units):
            unit = units[end]
            if selected and token_total + unit.token_count > chunk_size:
                break
            selected.append(unit)
            token_total += unit.token_count
            end += 1

        if not selected:
            selected = [units[start]]
            token_total = units[start].token_count
            end = start + 1

        pages = sorted({unit.page for unit in selected})
        chunks.append(
            {
                "chunk_number": chunk_number,
                "token_count": token_total,
                "pages": pages,
                "start_page": pages[0],
                "end_page": pages[-1],
                "text": "\n\n".join(unit.text for unit in selected),
            }
        )
        chunk_number += 1

        overlap_tokens = 0
        next_start = end
        while next_start > start:
            candidate = units[next_start - 1]
            if overlap_tokens and overlap_tokens + candidate.token_count > chunk_overlap:
                break
            overlap_tokens += candidate.token_count
            next_start -= 1
            if overlap_tokens >= chunk_overlap:
                break
        if next_start == start:
            next_start = end
        start = next_start
    return chunks


def build_document_records(pdf_path: Path, tokenizer, chunk_size: int, chunk_overlap: int):
    raw_text = read_pdf_text(pdf_path)
    pages = split_pages(raw_text)
    units: list[Unit] = []
    for idx, page_text in enumerate(pages, start=1):
        units.extend(paragraph_units(page_text, idx, tokenizer))
    chunks = build_chunks(units, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    stem = pdf_path.stem
    records: list[dict[str, object]] = []
    for chunk in chunks:
        chunk_number = int(chunk["chunk_number"])
        chunk_id = f"{stem}-chunk-{chunk_number:04d}"
        records.append(
            {
                "chunk_id": chunk_id,
                "source": pdf_path.name,
                "source_path": str(pdf_path),
                "token_count": chunk["token_count"],
                "start_page": chunk["start_page"],
                "end_page": chunk["end_page"],
                "pages": chunk["pages"],
                "text": chunk["text"],
                "char_count": len(str(chunk["text"])),
            }
        )
    return {
        "source": pdf_path.name,
        "source_path": str(pdf_path),
        "page_count": len(pages),
        "chunk_count": len(records),
        "records": records,
    }


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def shutil_which(binary: str) -> str | None:
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(path_dir) / binary
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def main() -> int:
    args = parse_args()
    profile = read_profile(args.profile)

    model_name = args.model_name or profile.get("RAG_EMBEDDING_MODEL", "mykor/KURE-v1")
    chunk_size = args.chunk_size or int(profile.get("RAG_CHUNK_SIZE_TOKENS", "700"))
    chunk_overlap = args.chunk_overlap or int(
        profile.get("RAG_CHUNK_OVERLAP_TOKENS", "120")
    )
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model_max_length = getattr(tokenizer, "model_max_length", chunk_size)
    if isinstance(model_max_length, int) and model_max_length > 0:
        chunk_size = min(chunk_size, model_max_length)
        chunk_overlap = min(chunk_overlap, max(chunk_size - 1, 0))

    print(f"[index] model={model_name}")
    print(f"[index] input_dir={args.input_dir}")
    print(f"[index] output_dir={output_dir}")
    print(f"[index] chunk_size={chunk_size} overlap={chunk_overlap}")

    pdf_paths = sorted(args.input_dir.glob("*.pdf"))
    if not pdf_paths:
        raise SystemExit(f"No PDFs found in {args.input_dir}")

    documents = [
        build_document_records(
            pdf_path, tokenizer=tokenizer, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        for pdf_path in pdf_paths
    ]

    rows = [row for document in documents for row in document["records"]]
    texts = [str(row["text"]) for row in rows]
    if not texts:
        raise SystemExit("Chunking produced no text rows.")

    model = SentenceTransformer(model_name, device=args.device)
    embeddings = model.encode(
        texts,
        batch_size=args.batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    embeddings = np.asarray(embeddings, dtype=np.float32)

    manifest = {
        "profile": str(args.profile),
        "model_name": model_name,
        "device": str(getattr(model, "device", args.device or "unknown")),
        "input_dir": str(args.input_dir),
        "output_dir": str(output_dir),
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "batch_size": args.batch_size,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(documents),
        "chunk_count": len(rows),
        "embedding_dim": int(embeddings.shape[1]),
        "documents": [
            {
                "source": document["source"],
                "page_count": document["page_count"],
                "chunk_count": document["chunk_count"],
            }
            for document in documents
        ],
    }

    np.save(output_dir / "embeddings.npy", embeddings)
    write_jsonl(output_dir / "chunks.jsonl", rows)
    write_json(output_dir / "manifest.json", manifest)

    print(f"[done] chunks={len(rows)}")
    print(f"[done] embeddings={output_dir / 'embeddings.npy'}")
    print(f"[done] metadata={output_dir / 'chunks.jsonl'}")
    print(f"[done] manifest={output_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
