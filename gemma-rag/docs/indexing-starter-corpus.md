# Starter Corpus Indexing

This note shows how to chunk and embed the public Korean medical-device starter corpus inside [`gemma-rag`](/home/rb/AI/gemma-rag/README.md).

## Prerequisites

- `pdftotext` available on the machine
- a Python environment with:
  - `sentence-transformers`
  - `transformers`
  - `torch`
  - `pypdf`

## Default Command

```bash
/home/rb/AI/.venv-gemma-rag-index/bin/python \
  /home/rb/AI/gemma-rag/scripts/build_embedding_index.py
```

Default behavior:

- input dir: [`test-corpus/mfds-korean-medical-device/starter`](/home/rb/AI/gemma-rag/test-corpus/mfds-korean-medical-device/starter)
- profile: [`config/korean_medical_device_rag.env`](/home/rb/AI/gemma-rag/config/korean_medical_device_rag.env)
- model: `mykor/KURE-v1`
- output dir: `/home/rb/AI/gemma-rag/indexes/mfds-korean-medical-device-starter-kure-v1`

## Outputs

- `chunks.jsonl`
  - one chunk record per line
- `embeddings.npy`
  - dense vectors aligned with `chunks.jsonl`
- `manifest.json`
  - run summary and document statistics

## Notes

- The script reads page text with `pdftotext` when available.
- If `pdftotext` is missing, it falls back to `pypdf`.
- Chunk size and overlap default to the retrieval profile values.
