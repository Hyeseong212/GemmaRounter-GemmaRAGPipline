# Presentation Assets Guide

발표자료에 바로 넣기 좋은 현재 자산 위치를 정리한다.

주요 결과 파일:

- 실측 휠체어 거리 측정 이미지:
  - [장애물거리측정.png](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/presentation/assets/장애물거리측정.png)
- 병원 이미지 8장 서술형 결과:
  - [장애물_서술형_결과.txt](</home/rbiotech-server/Downloads/병원 이미지/장애물_서술형_결과.txt>)
- 단일 병실 메타데이터:
  - [obstacle_metadata.json](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/test-assets/korean-hospital-obstacles/results/obstacle_metadata.json)
  - [obstacle_summary.md](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/test-assets/korean-hospital-obstacles/results/obstacle_summary.md)
- 병실 대표 이미지:
  - [transport_room_shared_01.jpg](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/test-assets/korean-hospital-obstacles/images/transport_room_shared_01.jpg)
- OAK 테스트 하네스 문서:
  - [oak-wheelchair-depth-test/README.md](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/README.md)

발표에 넣기 좋은 항목:

- 문제 정의:
  - 병원 내 이동 동선 사진
- 시스템 개요:
  - OAK -> Gemma 4 -> 좌표 후처리 -> depth 조회 흐름
- 결과:
  - `transport_room_shared_01.jpg`
  - `장애물거리측정.png`
  - 사용자 샘플 8장 결과 텍스트
- 한계:
  - detector 미사용
  - 프롬프트 기반 누락 가능성
