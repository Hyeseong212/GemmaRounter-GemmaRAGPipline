# GemmaRouter-GemmaRAGPipline

현재 저장소의 기준 실행점은 `GGUF 양자화 Gemma 4 31B` 서버입니다.

- 현재 주 실행점: [`llama-rest-core`](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core)
- 현재 운영 포트: `18088`
- 현재 운영 모델: `Gemma 4 31B Q4_K_M GGUF`
- 현재 실행 스크립트: `./launch.sh`
- 현재 서버 파이프라인 기본 모델 호출 경로: `http://127.0.0.1:18088/infer`

즉 지금은 `18088 단일 GGUF 멀티모달 서버` 기준으로 먼저 안정화한 상태입니다.

## 폴더 구성

- [`first-router`](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/first-router)
  - Jetson Orin 쪽 1차 라우팅 모듈
- [`second-router`](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/second-router)
  - 서버 측 2차 라우팅 모듈
- [`rag-answerer`](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/rag-answerer)
  - 문서 기반 RAG 응답 모듈
- [`final-score`](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/final-score)
  - 서버 최종 점수 게이트
- [`transfer-robot-llm`](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/transfer-robot-llm)
  - STT 교정 / TTS 응답 보조 모듈
- [`llama-rest-core`](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core)
  - 현재 실행 기준점

## 지금 바로 쓰는 방법

시작:

```bash
cd /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core
RAG_EMBED_HELPER_ENABLE=0 ./launch.sh start
```

재시작:

```bash
cd /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core
RAG_EMBED_HELPER_ENABLE=0 ./launch.sh restart
```

상태:

```bash
cd /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core
./launch.sh status
```

헬스체크:

```bash
curl http://127.0.0.1:18088/healthz
```

텍스트 추론:

```bash
curl http://127.0.0.1:18088/infer \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "안녕하세요라고만 답해줘."
  }'
```

이미지 추론:

```bash
curl http://127.0.0.1:18088/infer \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "이 이미지에서 휠체어가 어딨는지 중심을 좌표로 나타내봐",
    "image_path": "/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core/test-assets/public-research/중앙.jpg"
  }'
```

## 현재 확인된 사항

- 현재 기본 실행은 BF16이 아니라 `GGUF 양자화`입니다.
- 기본 이미지 토큰 설정은 `LLAMA_REST_IMAGE_MAX_TOKENS=1120`입니다.
- 좌표 응답은 모델 원출력을 그대로 쓰지 않고 서버가 후처리합니다.
- 현재 최종 좌표계는 `좌하단 원점 [x, y]` 기준입니다.

즉 `좌상`, `우상`, `좌하`, `우하` 테스트처럼 사분면 방향은 지금 기준으로 맞춰져 있습니다.

## 다음 단계

기준선을 이렇게 정리한 뒤 다음 순서로 가면 됩니다.

1. `18088 GGUF` 단일 서버 유지
2. Jetson `2B first-router`와 HTTP 계약 재점검
3. 서버 `POST /process/from-first-router`로 `second-router -> RAG -> final-score` 연결
4. 정밀 좌표/박스가 필요하면 `YOLO`나 `Grounding DINO` 같은 detection 모델 추가

세부 실행법은 [`llama-rest-core/README.md`](/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core/README.md) 에 정리돼 있습니다.
