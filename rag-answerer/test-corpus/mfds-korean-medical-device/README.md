# MFDS Korean Medical-Device Test Corpus

This is a small public Korean test corpus for early `rag-answerer` experiments.

It is intended for:

- Korean-only retrieval smoke tests
- chunking and citation checks
- answerable vs non-answerable checks
- warning and human-review behavior checks

It is **not** a substitute for your real device manuals, IFUs, service guides, or SOPs.

## Layout

- [`starter`](/home/rb/AI/rag-answerer/test-corpus/mfds-korean-medical-device/starter)
  - first-pass set with PDFs that already contain extractable text
- [`raw`](/home/rb/AI/rag-answerer/test-corpus/mfds-korean-medical-device/raw)
  - all downloaded source files
- [`extracted`](/home/rb/AI/rag-answerer/test-corpus/mfds-korean-medical-device/extracted)
  - files unpacked from the oxygen-device ZIP
- [`text`](/home/rb/AI/rag-answerer/test-corpus/mfds-korean-medical-device/text)
  - quick `pdftotext` outputs for inspection
- [`questions/smoke_test_questions.jsonl`](/home/rb/AI/rag-answerer/test-corpus/mfds-korean-medical-device/questions/smoke_test_questions.jsonl)
  - starter evaluation questions
- [`sources.tsv`](/home/rb/AI/rag-answerer/test-corpus/mfds-korean-medical-device/sources.tsv)
  - source metadata and download links

## What To Start With

Start by indexing the PDFs in [`starter`](/home/rb/AI/rag-answerer/test-corpus/mfds-korean-medical-device/starter).

These two files are the most useful right now:

- `mfds_2023_implant_knee_safety.pdf`
- `mfds_2017_urine_analyzer_safety.pdf`

Why these first:

- both are Korean medical-device documents
- both have extractable embedded text
- both contain concrete operational statements, warnings, and eligibility details

## OCR Note

Some downloaded files are image-heavy or scan-like:

- `mfds_2017_blood_pressure_monitor_ko.pdf`
- `mfds_2017_manual_suction_ko.pdf`
- `oxygen_device_leaflet_part1.pdf`
- `oxygen_device_leaflet_part2.pdf`

They are still useful later, but your current pipeline will need OCR if you want reliable retrieval from them.

## Recommended First Evaluation

1. Index only the PDFs in [`starter`](/home/rb/AI/rag-answerer/test-corpus/mfds-korean-medical-device/starter).
2. Ask the questions in [`questions/smoke_test_questions.jsonl`](/home/rb/AI/rag-answerer/test-corpus/mfds-korean-medical-device/questions/smoke_test_questions.jsonl).
3. Check:
   - did retrieval find the right document?
   - did the answer cite the right chunk ids?
   - did the model refuse unsupported questions?
   - did safety-related questions raise `needs_human_review` when evidence was incomplete or risk-sensitive?

## Good Expected Behaviors

- exact device terms are preserved
- warning text is not paraphrased away
- unsupported questions are rejected cleanly
- answers stay grounded in the supplied context
