# Korean Hospital Obstacle Test Set

현재 테스트셋은 `transport_room_shared_01.jpg` 한 장만 유지한다.

목적:

- 환자이송 로봇 기준으로 병실/병동 장애물을 가능한 한 많이 분류
- 각 장애물에 대해 정규화 좌표와 픽셀 좌표를 함께 저장

구성:

- [images/transport_room_shared_01.jpg](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/test-assets/korean-hospital-obstacles/images/transport_room_shared_01.jpg)
- [sources.tsv](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/test-assets/korean-hospital-obstacles/sources.tsv)
- [selected_contact_sheet.jpg](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/test-assets/korean-hospital-obstacles/selected_contact_sheet.jpg)
- [results](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test/test-assets/korean-hospital-obstacles/results)

실행:

```bash
cd /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/oak-wheelchair-depth-test
python scripts/extract_obstacle_metadata.py
```

출력:

- `results/obstacle_metadata.json`
- `results/obstacle_summary.md`
- `results/raw/transport_room_shared_01.txt`
