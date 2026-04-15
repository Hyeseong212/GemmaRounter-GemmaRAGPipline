# LLama REST Core

현재 기본 실행점은 `GGUF 양자화 Gemma 4 31B` 멀티모달 서버입니다.

- 포트: `18088`
- 실행 스크립트: `./launch.sh`
- 모델: `/home/rbiotech-server/llama_Rest/models/gemma4-31b/gemma-4-31B-it-Q4_K_M.gguf`
- 비전 프로젝터: `/home/rbiotech-server/llama_Rest/models/gemma4-31b/mmproj-gemma-4-31B-it-Q8_0.gguf`
- 현재 기본 이미지 토큰 설정: `LLAMA_REST_IMAGE_MIN_TOKENS=252`, `LLAMA_REST_IMAGE_MAX_TOKENS=1120`

`launch_bf16.sh`와 BF16 서버 코드는 실험용으로 남아 있지만, 현재 운영 기준선은 아닙니다.

## 빠른 시작

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

로그:

```bash
cd /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core
./launch.sh logs
tail -f /tmp/llama-rest-core/llama-rest-core.log
```

중지:

```bash
cd /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core
./launch.sh stop
```

## 헬스체크

```bash
curl http://127.0.0.1:18088/healthz
```

예상 응답:

```json
{
  "status": "ok",
  "service": "llama-rest-core"
}
```

## 추론 예시

텍스트:

```bash
curl http://127.0.0.1:18088/infer \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "안녕하세요라고만 답해줘."
  }'
```

이미지:

```bash
curl http://127.0.0.1:18088/infer \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "이 이미지에서 휠체어가 어딨는지 중심을 좌표로 나타내봐",
    "image_path": "/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core/test-assets/public-research/중앙.jpg"
  }'
```

영상:

```bash
curl http://127.0.0.1:18088/infer \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "이 영상에서 보이는 장면을 설명해줘.",
    "video_path": "/home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core/test-assets/public-research/brain_mri_post_glioblastoma_transverse.mp4"
  }'
```

현재 `/infer`는 아래 입력을 받습니다.

- `prompt`
- `image_path`
- `video_path`
- `image` base64
- `video` base64

영상은 내부적으로 여러 프레임을 뽑아 요약 이미지로 만든 뒤 처리합니다.

## 현재 기본 설정

`launch.sh` 기본값:

- `LLAMA_REST_PORT=18088`
- `LLAMA_REST_MODEL_PATH=/home/rbiotech-server/llama_Rest/models/gemma4-31b/gemma-4-31B-it-Q4_K_M.gguf`
- `LLAMA_REST_MMPROJ_PATH=/home/rbiotech-server/llama_Rest/models/gemma4-31b/mmproj-gemma-4-31B-it-Q8_0.gguf`
- `LLAMA_REST_IMAGE_MIN_TOKENS=252`
- `LLAMA_REST_IMAGE_MAX_TOKENS=1120`

토큰 수를 바꾸고 싶으면 이렇게 실행합니다.

```bash
cd /home/rbiotech-server/LLM_Harnes_Support/GemmaRounter-GemmaRAGPipline/llama-rest-core
LLAMA_REST_IMAGE_MAX_TOKENS=1400 RAG_EMBED_HELPER_ENABLE=0 ./launch.sh restart
```

실제 적용 여부는 로그에서 확인할 수 있습니다.

```bash
rg "image_min_pixels|image_max_pixels" /tmp/llama-rest-core/llama-rest-core.log
```

## 좌표 응답 규칙

현재 서버는 좌표 질문에 대해 후처리를 적용합니다.

- Gemma 원출력은 종종 `0~1000` 범위의 정규화된 `[y, x]` 비슷한 좌표로 나옴
- 서버가 이를 원본 이미지 크기에 맞춰 다시 픽셀 좌표로 바꿈
- 최종 반환 좌표계는 `좌하단 원점` 기준

즉 최종 응답 `[x, y]`는:

- `x`: 왼쪽 -> 오른쪽 증가
- `y`: 아래 -> 위 증가

사분면 테스트 예시:

- `좌상.jpg` -> `[409, 834]`
- `우상.jpg` -> `[1536, 780]`
- `좌하.jpg` -> `[328, 267]`
- `우하.jpg` -> `[1586, 243]`

주의:

- 이건 detector가 아니라 LLM 좌표를 보정한 휴리스틱입니다.
- 정밀 bounding box나 산업용 좌표가 목적이면 `YOLO`나 `Grounding DINO` 같은 detection 모델을 별도로 붙이는 것이 맞습니다.

## 줄바꿈

`/infer` 응답 끝에는 자동 줄바꿈이 붙습니다.  
그래서 `curl`로 호출해도 셸 프롬프트가 답변 뒤에 바로 붙지 않습니다.

## 참고

- 모델에게 직접 "너 모델명 뭐야"라고 물으면 잘못 답할 수 있습니다.
- 실제 로드 모델과 비전 토큰 설정은 `/tmp/llama-rest-core/llama-rest-core.log`로 확인하는 게 가장 안전합니다.
- 이 폴더 안에는 통합 라우팅/RAG/C++ 코드도 남아 있지만, 지금 재시작 기준선은 `18088 GGUF 멀티모달 서버` 하나로 잡는 것이 가장 단순합니다.
