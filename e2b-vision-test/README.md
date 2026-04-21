# E2B Vision Test

`e2b-vision-test`는 Jetson 쪽 `Gemma 4 E2B`를 멀티모달 모드로 띄워서 이미지 추론을 빠르게 확인하는 전용 폴더입니다.

목적은 3가지입니다.

- 기존 `first-router` 텍스트 전용 서버와 분리해서 테스트하기
- `mmproj`가 켜진 `E2B`를 별도 포트에서 올리기
- 로컬 이미지 파일 하나로 바로 추론해 보기

## 기본 설정

- model variant: `e2b`
- alias: `gemma4-vision-e2b`
- model port: `8083`
- multimodal: `enabled`
- container name: `e2b-vision-test-e2b-8083`
- batch: `256`
- ubatch: `256`

현재 스크립트는 기존 `first-router` 컨테이너를 내리지 않습니다.
즉 `8080/8090`의 1차 라우팅과 병행해서 올릴 수 있습니다.

## 빠른 시작

```bash
cd /home/rb/AI/e2b-vision-test
./launch.sh start
```

현재 Jetson에서 `first-router` 같은 다른 Gemma 컨테이너가 이미 GPU 메모리를 쓰고 있으면 `start`가 OOM으로 실패할 수 있습니다.
그럴 때는 이미지 테스트용으로 GPU를 비우는 전용 액션을 사용합니다.

```bash
cd /home/rb/AI/e2b-vision-test
./launch.sh start-exclusive
```

`start-exclusive`는 같은 `gemma4-jetson-orin` 계열 컨테이너를 먼저 내린 뒤 이 서버만 단독으로 올립니다.

준비 확인:

```bash
cd /home/rb/AI/e2b-vision-test
./launch.sh ready
```

상태:

```bash
cd /home/rb/AI/e2b-vision-test
./launch.sh status
```

로그:

```bash
cd /home/rb/AI/e2b-vision-test
./launch.sh logs
```

중지:

```bash
cd /home/rb/AI/e2b-vision-test
./launch.sh stop
```

## 헬스체크

```bash
curl http://127.0.0.1:8083/health
```

```bash
curl http://127.0.0.1:8083/v1/models
```

`v1/models` 응답에서 `id`가 `gemma4-vision-e2b`로 보이면 정상입니다.

## 이미지 추론

기본 샘플:

```bash
cd /home/rb/AI/e2b-vision-test
./launch.sh sample
```

좌표 추론 샘플:

```bash
cd /home/rb/AI/e2b-vision-test
./launch.sh sample-coordinate
```

직접 이미지 지정:

```bash
cd /home/rb/AI/e2b-vision-test
python3 scripts/infer_image.py \
  --image /home/rb/AI/llama-rest-core/test-assets/public-research/중앙.jpg \
  --prompt-file examples/sample_scene_prompt.txt
```

직접 프롬프트 지정:

```bash
cd /home/rb/AI/e2b-vision-test
python3 scripts/infer_image.py \
  --image /home/rb/AI/llama-rest-core/test-assets/public-research/중앙.jpg \
  --prompt "이미지에서 보이는 주요 물체와 대략적인 위치를 한국어로 짧게 설명해줘."
```

## OpenAI 호환 API 형식

이 폴더는 `llama-server`의 `POST /v1/chat/completions`를 그대로 사용합니다.
이미지는 `image_url` content part에 data URI 형태로 넣습니다.

이 형식은 공식 `llama.cpp` 서버 문서의 멀티모달 설명에 맞춥니다.

- source: `ggml-org/llama.cpp` `tools/server/README.md`
- note: `If model supports multimodal, you can input the media file via image_url content part.`

## 샘플 에셋

기본 샘플 이미지는 아래 파일을 사용합니다.

- `/home/rb/AI/llama-rest-core/test-assets/public-research/중앙.jpg`

다른 테스트 이미지는 같은 폴더의 `좌상.jpg`, `우상.jpg`, `좌하.jpg`, `우하.jpg`도 사용할 수 있습니다.

## 주의

- 이 서버는 `first-router`의 텍스트 라우팅용 `8080`과 별개입니다.
- Jetson 메모리 상태에 따라 이미지 추론은 텍스트 추론보다 느릴 수 있습니다.
- `E2B`는 가능한 멀티모달 테스트용으로는 충분하지만, 무거운 영상/다중이미지 reasoning은 `31B` 서버보다 제한적일 수 있습니다.
