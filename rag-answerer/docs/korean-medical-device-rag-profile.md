# Korean Medical-Device RAG Profile

This document describes the upstream retrieval profile that should feed [`gemma4-rag`](/home/rb/AI/rag-answerer/README.md).

`rag-answerer` is still the grounded answer generator.
The retriever should prepare Korean medical-device context in a way that is safe and easy for the generator to cite.

## Recommended Stack

- dense retriever: `mykor/KURE-v1`
- sparse retriever: `BM25`
- fusion: `RRF`
- reranker: `BAAI/bge-reranker-v2-m3`

## Why This Stack

- `KURE-v1` is tuned for Korean retrieval, so it fits a Korean-only RAG pipeline better than a generic multilingual default.
- Medical-device manuals and IFUs often depend on exact warning text, error codes, model names, and tabular procedures.
- Hybrid retrieval is safer than dense-only retrieval for this kind of content because BM25 helps preserve exact-string matching.
- A reranker reduces the chance that semantically similar but operationally wrong chunks reach the answer generator.

## Recommended Retrieval Flow

1. Normalize the user question without changing device model names, units, or error codes.
2. Run dense retrieval with `KURE-v1`.
3. Run sparse retrieval with `BM25`.
4. Merge candidates with `RRF`.
5. Rerank with `BAAI/bge-reranker-v2-m3`.
6. Send only the final top chunks to `gemma4-rag`.

Recommended cutoffs:

- dense top-k: `12`
- sparse top-k: `20`
- fused top-k: `8`
- final top-k after rerank: `5`

## Chunking Guidance

Recommended chunking for Korean device documentation:

- chunk size: around `700` tokens
- overlap: around `120` tokens
- keep section hierarchy
- keep table rows attached to their headers when possible
- keep warning and contraindication blocks intact

This is meant for:

- IFU
- operator manual
- service manual
- SOP
- maintenance bulletin
- troubleshooting guide

## Context Contract For `gemma4-rag`

The generator works best when each chunk includes both text and minimal metadata:

```text
Question: E103 에러가 발생했을 때 사용자가 가장 먼저 확인해야 하는 항목은 무엇인가?

Context:
[chunk-01] source=IFU_v3.pdf section=7.2 page=41 score=0.92
E103은 센서 미인식 또는 연결 오류와 관련될 수 있다. 장비 화면에 E103이 표시되면 케이블 체결 상태를 먼저 확인한다.

[chunk-02] source=service_note_2026-02.pdf section=troubleshooting page=2 score=0.84
재부팅 이후에도 동일 오류가 반복되면 사용을 중지하고 유지보수 담당자에게 보고한다.
```

Required metadata fields:

- `chunk_id`
- `source`
- `section`
- `page`
- `score`

## Safety Rules For Retrieval

The retriever should prefer recall over aggressive compression for:

- warnings
- contraindications
- stop-use instructions
- operating limits
- maintenance prerequisites
- error-code procedures

The hand-off should trigger `needs_human_review` on the generator side when:

- retrieved chunks conflict
- the top chunks are low-confidence
- the question asks for clinical judgment outside device documentation
- the context is missing a direct answer

## File References

- profile env: [`config/korean_medical_device_rag.env`](/home/rb/AI/rag-answerer/config/korean_medical_device_rag.env)
- generator prompt: [`prompts/rag_answer_system_prompt.txt`](/home/rb/AI/rag-answerer/prompts/rag_answer_system_prompt.txt)
- request example: [`examples/rag_answer_request.json`](/home/rb/AI/rag-answerer/examples/rag_answer_request.json)
