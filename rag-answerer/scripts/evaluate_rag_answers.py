#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer


ROOT_DIR = Path("/home/rb/AI")
DEFAULT_INDEX_DIR = (
    ROOT_DIR / "rag-answerer/indexes/mfds-korean-medical-device-starter-kure-v1"
)
DEFAULT_QUESTION_FILE = (
    ROOT_DIR
    / "rag-answerer/test-corpus/mfds-korean-medical-device/questions/smoke_test_questions.jsonl"
)
DEFAULT_PROMPT_FILE = ROOT_DIR / "rag-answerer/prompts/rag_answer_system_prompt.txt"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "rag-answerer/test-results"
DEFAULT_MODEL_NAME = "gemma4-rag"
DEFAULT_ENDPOINT = "http://127.0.0.1:8082/v1/chat/completions"
DEFAULT_RETRIEVAL_MODEL = "mykor/KURE-v1"

ANSWER_KEY: dict[str, dict[str, Any]] = {
    "urine-01": {
        "expected_answer": "개인용소변분석기의 일반 구성은 개인용소변분석기와 소변검사지다.",
        "expected_human_review": False,
    },
    "urine-02": {
        "expected_answer": "사용 전에 구성품, 보관조건, 유효기간, 사용방법을 반드시 확인해야 한다.",
        "expected_human_review": False,
    },
    "urine-03": {
        "expected_answer": "제품에 부착된 허가사항과 식약처 의료기기 제품정보방에서 허가·신고 여부를 확인해야 한다.",
        "expected_human_review": False,
    },
    "urine-04": {
        "expected_answer": "전용검사지 확인, 유효기간 확인, 재사용 금지, 검사지를 구부리거나 휘지 않게 주의해야 한다.",
        "expected_human_review": False,
    },
    "urine-05": {
        "expected_answer": "결과가 의심되면 스스로 판단하지 말고 의사와 상의해야 하며, 잠혈·단백질·백혈구 등이 확인되면 의사 진료를 받아야 한다.",
        "expected_human_review": True,
    },
    "knee-01": {
        "expected_answer": "아니며, 식품의약품안전처 허가를 받은 제품만 사용할 수 있다.",
        "expected_human_review": False,
    },
    "knee-02": {
        "expected_answer": "활동성 감염, 신경·근육질환으로 하지 근력이 현저히 저하된 경우, 내과적·신경계적 질환 등으로 수술 위험이 너무 높거나 삶의 질 개선이 기대되지 않는 경우는 일반적으로 수술하지 않는다.",
        "expected_human_review": True,
    },
    "knee-03": {
        "expected_answer": "문서에서는 인공무릎관절의 수명을 10년 정도로 설명한다.",
        "expected_human_review": False,
    },
    "knee-04": {
        "expected_answer": "상처 부위 발적이나 진물, 갑작스러운 심한 부종 또는 지속 통증, 37도 이상의 전신발열 지속, 호흡곤란이나 가슴 통증이 나타나면 즉시 담당 의사에게 연락해야 한다.",
        "expected_human_review": True,
    },
    "knee-05": {
        "expected_answer": "문서에는 인공무릎관절 수술 비용 정보가 없으므로 직접 확인되지 않는다고 답해야 한다.",
        "expected_human_review": False,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate rag-answerer QA against a starter corpus.")
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX_DIR)
    parser.add_argument("--question-file", type=Path, default=DEFAULT_QUESTION_FILE)
    parser.add_argument("--prompt-file", type=Path, default=DEFAULT_PROMPT_FILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--endpoint", type=str, default=DEFAULT_ENDPOINT)
    parser.add_argument("--model-name", type=str, default=DEFAULT_MODEL_NAME)
    parser.add_argument("--retrieval-model", type=str, default=DEFAULT_RETRIEVAL_MODEL)
    parser.add_argument("--retrieval-device", type=str, default="cpu")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=300)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--tag", type=str, default=None)
    parser.add_argument("--launch-mode", type=str, default="unknown")
    return parser.parse_args()


def load_questions(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def load_chunks(index_dir: Path) -> tuple[list[dict[str, Any]], np.ndarray]:
    rows: list[dict[str, Any]] = []
    with (index_dir / "chunks.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
    embeddings = np.load(index_dir / "embeddings.npy")
    return rows, embeddings


def strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped.strip()


def parse_model_json(raw_content: str) -> dict[str, Any] | None:
    candidate = strip_code_fences(raw_content)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", candidate, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def build_context(retrieved: list[dict[str, Any]], scores: list[float]) -> str:
    parts: list[str] = []
    for row, score in zip(retrieved, scores):
        parts.append(
            f"[{row['chunk_id']}] source={row['source']} page={row['start_page']} "
            f"score={score:.4f}\n{row['text']}"
        )
    return "\n\n".join(parts)


def call_model(
    endpoint: str,
    model_name: str,
    system_prompt: str,
    question: str,
    context: str,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    payload = {
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Question: {question}\n\nContext:\n{context}"},
        ],
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = resp.read().decode("utf-8", "replace")
        return json.loads(body)


def score_result(
    question_row: dict[str, Any],
    expected_answer: str,
    expected_human_review: bool,
    parsed: dict[str, Any] | None,
    raw_content: str,
    retrieved_chunk_ids: list[str],
) -> tuple[float, dict[str, float], list[str]]:
    answer_text = ""
    if parsed and isinstance(parsed.get("answer"), str):
        answer_text = parsed["answer"]
    elif raw_content:
        answer_text = raw_content

    answerable = parsed.get("answerable") if parsed else None
    needs_human_review = parsed.get("needs_human_review") if parsed else None
    used_chunk_ids = parsed.get("used_chunk_ids") if parsed else []
    if not isinstance(used_chunk_ids, list):
        used_chunk_ids = []

    expected_answerable = bool(question_row["expected_answerable"])
    must_include = list(question_row.get("must_include", []))
    must_not_include = list(question_row.get("must_not_include", []))

    answer_lower = answer_text.lower()
    include_hits = sum(1 for term in must_include if term.lower() in answer_lower)
    include_score = 4.0 * (include_hits / max(len(must_include), 1))

    forbidden_hit = any(term.lower() in answer_lower for term in must_not_include)
    forbidden_score = 0.0 if forbidden_hit else 1.0

    if answerable is None:
        answerable_score = 0.0
    else:
        answerable_score = 2.0 if bool(answerable) == expected_answerable else 0.0

    if needs_human_review is None:
        review_score = 0.0
    else:
        review_score = 1.0 if bool(needs_human_review) == expected_human_review else 0.0

    used_valid = bool(used_chunk_ids) and all(
        chunk_id in retrieved_chunk_ids for chunk_id in used_chunk_ids
    )
    if not expected_answerable and not used_chunk_ids:
        used_valid = True
    citation_score = 1.0 if used_valid else 0.0

    if expected_answerable:
        structure_score = 1.0 if len(answer_text.strip()) >= 20 else 0.0
    else:
        insufficient_markers = ["문서", "직접", "확인", "없"]
        structure_score = (
            1.0 if all(marker in answer_text for marker in insufficient_markers[:2]) else 0.0
        )

    total = answerable_score + include_score + forbidden_score + review_score + citation_score + structure_score
    total = min(10.0, max(0.0, total))

    notes: list[str] = []
    if answerable_score < 2.0:
        notes.append("answerable 판정 불일치")
    if include_hits < len(must_include):
        notes.append(f"핵심 키워드 누락 {include_hits}/{len(must_include)}")
    if forbidden_hit:
        notes.append("금지 키워드 포함")
    if review_score < 1.0:
        notes.append("human review 판정 불일치")
    if citation_score < 1.0:
        notes.append("chunk citation 불충분")
    if structure_score < 1.0:
        notes.append("답변 형식/거절 문구 미흡")
    if not notes:
        notes.append("전반적으로 기대 답변에 부합")

    subscores = {
        "answerable": round(answerable_score, 2),
        "must_include": round(include_score, 2),
        "must_not_include": round(forbidden_score, 2),
        "human_review": round(review_score, 2),
        "citations": round(citation_score, 2),
        "format": round(structure_score, 2),
    }
    return round(total, 1), subscores, notes


def sanitize_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value)


def write_report_md(path: Path, report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# rag-answerer Starter Evaluation")
    lines.append("")
    lines.append(f"- generated_at: `{report['generated_at']}`")
    lines.append(f"- launch_mode: `{report['launch_mode']}`")
    lines.append(f"- model_name: `{report['model_name']}`")
    lines.append(f"- endpoint: `{report['endpoint']}`")
    lines.append(f"- average_score: `{report['average_score']}/10`")
    lines.append("")
    for item in report["results"]:
        lines.append(f"## {item['id']} ({item['score']}/10)")
        lines.append("")
        lines.append(f"- question: {item['question']}")
        lines.append(f"- expected_answer: {item['expected_answer']}")
        lines.append(f"- actual_answer: {item['actual_answer']}")
        lines.append(f"- answerable: expected `{item['expected_answerable']}`, actual `{item['actual_answerable']}`")
        lines.append(f"- needs_human_review: expected `{item['expected_human_review']}`, actual `{item['actual_needs_human_review']}`")
        lines.append(f"- retrieved_chunk_ids: `{item['retrieved_chunk_ids']}`")
        lines.append(f"- used_chunk_ids: `{item['actual_used_chunk_ids']}`")
        lines.append(f"- notes: {', '.join(item['notes'])}")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    questions = load_questions(args.question_file)
    rows, embeddings = load_chunks(args.index_dir)
    system_prompt = args.prompt_file.read_text(encoding="utf-8")
    model = SentenceTransformer(args.retrieval_model, device=args.retrieval_device)

    results: list[dict[str, Any]] = []
    started = time.time()

    for idx, question_row in enumerate(questions, start=1):
        qid = question_row["id"]
        answer_key = ANSWER_KEY[qid]
        query = question_row["question"]
        print(f"[eval] {idx}/{len(questions)} {qid}: {query}")
        sys.stdout.flush()

        q_embedding = model.encode(
            [query], convert_to_numpy=True, normalize_embeddings=True
        )[0]
        scores = embeddings @ q_embedding
        top_indices = np.argsort(scores)[::-1][: args.top_k]
        retrieved = [rows[int(i)] for i in top_indices]
        retrieved_scores = [float(scores[int(i)]) for i in top_indices]
        retrieved_chunk_ids = [row["chunk_id"] for row in retrieved]
        context = build_context(retrieved, retrieved_scores)

        response_json = call_model(
            endpoint=args.endpoint,
            model_name=args.model_name,
            system_prompt=system_prompt,
            question=query,
            context=context,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
        content = (
            (((response_json.get("choices") or [{}])[0].get("message") or {}).get("content"))
            or ""
        )
        if isinstance(content, list):
            content = json.dumps(content, ensure_ascii=False)
        parsed = parse_model_json(str(content))
        actual_answer = parsed.get("answer") if parsed and isinstance(parsed.get("answer"), str) else str(content)
        score, subscores, notes = score_result(
            question_row=question_row,
            expected_answer=answer_key["expected_answer"],
            expected_human_review=bool(answer_key["expected_human_review"]),
            parsed=parsed,
            raw_content=str(content),
            retrieved_chunk_ids=retrieved_chunk_ids,
        )

        result = {
            "id": qid,
            "question": query,
            "expected_answer": answer_key["expected_answer"],
            "expected_answerable": bool(question_row["expected_answerable"]),
            "expected_human_review": bool(answer_key["expected_human_review"]),
            "actual_answerable": parsed.get("answerable") if parsed else None,
            "actual_needs_human_review": parsed.get("needs_human_review") if parsed else None,
            "actual_warning": parsed.get("warning") if parsed else None,
            "actual_used_chunk_ids": parsed.get("used_chunk_ids") if parsed else [],
            "actual_answer": actual_answer,
            "raw_model_content": str(content),
            "retrieved_chunk_ids": retrieved_chunk_ids,
            "retrieved_sources": [row["source"] for row in retrieved],
            "retrieved_scores": [round(score_value, 4) for score_value in retrieved_scores],
            "subscores": subscores,
            "notes": notes,
            "score": score,
        }
        results.append(result)
        print(f"[eval] score={score}/10 notes={'; '.join(notes)}")
        sys.stdout.flush()

    average_score = round(sum(item["score"] for item in results) / max(len(results), 1), 2)
    tag = args.tag or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_name = sanitize_filename(f"starter-eval-{tag}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_s": round(time.time() - started, 2),
        "launch_mode": args.launch_mode,
        "endpoint": args.endpoint,
        "model_name": args.model_name,
        "index_dir": str(args.index_dir),
        "question_file": str(args.question_file),
        "average_score": average_score,
        "results": results,
    }

    json_path = args.output_dir / f"{base_name}.json"
    md_path = args.output_dir / f"{base_name}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_report_md(md_path, report)

    print(f"[done] average_score={average_score}/10")
    print(f"[done] json_report={json_path}")
    print(f"[done] md_report={md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
