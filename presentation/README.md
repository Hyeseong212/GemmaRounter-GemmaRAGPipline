# Presentation Workflow

이 폴더는 `OAK 카메라 + Gemma 4 기반 이미지 추론 + 장애물 위치 판별 + 클래스 분류` 연구 내용을
발표 자료로 정리하기 위한 워크플로다.

구조:

- [outline](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/presentation/outline)
  - 슬라이드별 메시지와 발표 흐름
- [assets](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/presentation/assets)
  - 실제 결과 파일과 데모 이미지 참조 가이드
- [figures](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/presentation/figures)
  - 파이프라인, 좌표 변환, OAK depth 흐름 다이어그램 원본
- [slides](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/presentation/slides)
  - PPT 초안 생성 스크립트
- [export](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/presentation/export)
  - 최종 `pptx`, `pdf` 출력 위치

권장 제작 흐름:

1. [outline/slides.md](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/presentation/outline/slides.md)에서 슬라이드 구조를 확정
2. [figures](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/presentation/figures) 다이어그램을 수정 또는 렌더링
3. [assets/README.md](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/presentation/assets/README.md)에 정리된 실제 연구 결과 파일을 확인
4. `python-pptx` 설치 후 [slides/make_ppt.py](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/presentation/slides/make_ppt.py)로 초안 PPT 생성
5. `export/` 아래의 `pptx`를 열어 최종 디자인/문구만 보정

빠른 시작:

```bash
cd /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline
python -m pip install python-pptx
python presentation/slides/make_ppt.py
```

생성물:

- [export/gemma4_oak_obstacle_presentation_draft.pptx](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/presentation/export/gemma4_oak_obstacle_presentation_draft.pptx)
  - 생성 후 이 위치에 저장됨

주의:

- 현재 스크립트는 발표 초안 생성기다.
- 최종 발표본은 도식 렌더링 PNG와 실제 스크린샷을 더 넣어야 한다.
- 다이어그램 원본은 `mermaid` 기준으로 제공한다.
