# Gemma RAG Flow Explained For Jetson Orin

이 문서는 `gemma-rag`가 실제로 어떤 흐름으로 동작하는지, 그리고 어려운 용어를 최대한 쉬운 말로 풀어서 설명한 문서다.

대상 독자:

- 지금 이 프로젝트를 처음 보는 팀원
- RAG, 임베딩, 청크 같은 용어가 아직 익숙하지 않은 사람
- Jetson Orin에서 어떤 모델 구성이 실제로 돌아가는지 빠르게 알고 싶은 사람

## 한 줄 요약

`gemma-rag`는 문서를 직접 찾는 프로그램이 아니라, 위쪽 검색기에서 찾아준 문서 조각을 받아서 최종 답변을 만드는 "답변 생성기"다.

즉, 이 프로젝트의 핵심 흐름은 아래와 같다.

1. 문서를 준비한다.
2. 문서를 잘게 나눈다.
3. 각 조각을 숫자 벡터로 바꾼다.
4. 질문이 들어오면 가장 비슷한 조각을 찾는다.
5. 찾은 조각만 Gemma에게 넘긴다.
6. Gemma는 그 조각 안에서만 답하게 한다.

## 이 프로젝트에서 실제로 쓰는 것

- 테스트 문서: [`test-corpus/mfds-korean-medical-device/starter`](/home/rb/AI/gemma-rag/test-corpus/mfds-korean-medical-device/starter)
- 임베딩 모델: `mykor/KURE-v1`
- 생성 모델 alias: `gemma4-rag`
- 기본 생성 프로젝트: [`gemma-rag`](/home/rb/AI/gemma-rag)
- 임베딩/청크 생성 스크립트: [`scripts/build_embedding_index.py`](/home/rb/AI/gemma-rag/scripts/build_embedding_index.py)
- 평가 스크립트: [`scripts/evaluate_rag_answers.py`](/home/rb/AI/gemma-rag/scripts/evaluate_rag_answers.py)
- 평가 런처: [`launch-eval.sh`](/home/rb/AI/gemma-rag/launch-eval.sh)

## 전체 흐름

### 1. 문서를 준비한다

우리는 먼저 공개 문서로 작은 테스트 세트를 만들었다.

시작용 문서는 아래 두 개다.

- `mfds_2017_urine_analyzer_safety.pdf`
- `mfds_2023_implant_knee_safety.pdf`

이 문서들은 한국어 의료기기 문서이고, 텍스트 추출이 가능해서 RAG 첫 테스트용으로 적합하다.

### 2. 문서를 청크로 나눈다

문서 전체를 한 번에 모델에 넣지 않고, 작은 덩어리로 나눈다.

현재 테스트에서는 아래 기준을 썼다.

- chunk size: `700`
- chunk overlap: `120`

실제 생성된 결과:

- 문서 2개
- 총 청크 9개
- 결과 위치: [`indexes/mfds-korean-medical-device-starter-kure-v1`](/home/rb/AI/gemma-rag/indexes)

### 3. 각 청크를 임베딩으로 바꾼다

문자열 자체를 저장하는 것만으로는 "의미가 비슷한 문장"을 잘 찾기 어렵다.

그래서 각 청크를 숫자 배열로 바꾸는데, 이 숫자 배열을 임베딩이라고 부른다.

이번 테스트에서는:

- 임베딩 모델: `mykor/KURE-v1`
- 임베딩 차원: `1024`

결과 파일:

- [`embeddings.npy`](/home/rb/AI/gemma-rag/indexes/mfds-korean-medical-device-starter-kure-v1/embeddings.npy)
- [`chunks.jsonl`](/home/rb/AI/gemma-rag/indexes/mfds-korean-medical-device-starter-kure-v1/chunks.jsonl)
- [`manifest.json`](/home/rb/AI/gemma-rag/indexes/mfds-korean-medical-device-starter-kure-v1/manifest.json)

### 4. 질문이 들어오면 비슷한 청크를 찾는다

질문도 같은 임베딩 모델로 숫자로 바꾼다.

그 다음:

- 질문 벡터
- 문서 청크 벡터

사이의 유사도를 계산해서 가장 관련 있는 청크를 고른다.

쉽게 말하면:

- 질문과 가장 뜻이 비슷한 문서 조각을 찾는 단계다.

### 5. 찾은 청크만 Gemma에게 넘긴다

Gemma는 문서 전체를 보는 것이 아니라, 검색으로 뽑힌 일부 청크만 본다.

그래서 RAG 품질은 두 단계가 같이 맞아야 한다.

- 검색이 맞아야 한다
- 생성이 맞아야 한다

검색이 틀리면 Gemma가 똑똑해도 잘못된 문서를 보고 답하게 된다.

### 6. Gemma가 최종 답변을 만든다

`gemma-rag`의 시스템 프롬프트는 아래 파일에 있다.

- [`prompts/rag_answer_system_prompt.txt`](/home/rb/AI/gemma-rag/prompts/rag_answer_system_prompt.txt)

이 프롬프트의 핵심 목적은 아래와 같다.

- 문맥에 있는 내용만 답하기
- 근거 없으면 모른다고 말하기
- 경고 문구를 함부로 바꾸지 않기
- 가능하면 사용한 chunk id를 같이 돌려주기

## 어려운 단어를 쉬운 말로 다시 설명

### 청크

문서를 너무 길지 않게 잘라놓은 작은 조각이다.

쉽게 말하면:

- 긴 PDF를 여러 개의 짧은 문단 묶음으로 나눠둔 것

### 임베딩

문장을 "숫자 좌표"로 바꾼 값이다.

쉽게 말하면:

- 뜻이 비슷한 문장은 숫자상으로도 가까워지게 바꾸는 방식

### 벡터 검색

질문과 가장 가까운 임베딩을 찾는 검색이다.

쉽게 말하면:

- 글자 그대로 일치하지 않아도 뜻이 비슷하면 찾으려는 검색

### top-k

질문과 가장 비슷한 결과를 몇 개까지 가져올지 정하는 숫자다.

예:

- `top-k=3`이면 가장 관련 높은 3개 청크를 가져온다.

### 리랭커

처음 검색한 후보를 다시 한 번 정렬하는 모델이다.

쉽게 말하면:

- 1차 검색 결과를 다시 검토해서 순서를 더 정확하게 다듬는 도구

### 양자화

모델을 조금 더 가볍게 저장하는 방식이다.

쉽게 말하면:

- 메모리를 덜 쓰도록 모델을 압축하는 방법

예:

- `Q8_0`은 비교적 무겁다
- `Q4_K_M`은 더 가볍다

### GPU layers

모델 계산 중 일부 레이어를 GPU에 올릴지 정하는 값이다.

쉽게 말하면:

- 모델의 일부를 GPU가 맡아서 빨리 계산하게 하는 옵션

### 쓰로틀링

장비가 너무 뜨겁거나 전력 제한에 걸려서 성능을 스스로 낮추는 현상이다.

쉽게 말하면:

- 계속 무겁게 돌리다 보면 처음보다 느려지는 현상

### fallback

원래 방식이 실패했을 때 대체 방식으로 내려가는 것이다.

예:

- GPU로 안 뜨면 CPU로 내려가는 것

### citation

답변에 사용한 근거 청크를 표시하는 것이다.

쉽게 말하면:

- "이 답은 문서 어디에서 가져왔는지"를 보여주는 표시

### human review

사람이 한 번 더 확인해야 하는 경우를 뜻한다.

쉽게 말하면:

- 모델 혼자 결정하지 말고 사람이 검토해야 한다는 신호

## Jetson Orin에서 실제로 확인한 것

이번 작업에서 실제로 확인한 내용은 아래와 같다.

### 1. `e2b Q8_0`는 현재 Jetson GPU에서 정상 기동되지 않았다

우리는 `e2b`를 GPU 모드로 여러 번 시도했다.

시도한 예:

- `GPU_LAYERS=4`
- `GPU_LAYERS=1`

하지만 둘 다 CUDA 메모리 부족으로 실패했다.

즉 현재 환경에서는:

- `e2b` 자체가 문제라기보다
- 현재 연결된 `Q8_0` 자산이 Jetson GPU 메모리에 맞지 않는 상태다

### 2. `e4b-q4`는 GPU에서 기동되는 것을 확인했다

`e4b-q4`는 GPU에서 실제로 올라왔다.

다만 운영 중에는 쓰로틀링이 걸리는 문제가 관찰됐다.

즉 현재 Jetson 관점에서는:

- `e4b-q4`: GPU 기동 가능, 하지만 장시간 부하에서는 속도 저하 위험
- `e2b Q8_0`: 현재 GPU OOM

### 3. 그래서 평가는 `e2b CPU fallback`으로 완료했다

GPU로 `e2b`를 띄우는 데 실패했기 때문에, 평가 런처는 자동으로 CPU fallback으로 내려가도록 만들었다.

관련 런처:

- [`launch-eval.sh`](/home/rb/AI/gemma-rag/launch-eval.sh)

동작 순서:

1. `e2b` GPU 시작 시도
2. 실패 시 로그 출력
3. CPU 모드로 다시 시작
4. 10문항 평가 실행

## 실제 평가 결과 요약

10문항 평가를 실행했고 평균 점수는 아래와 같았다.

- 평균 점수: `6.0 / 10`

좋았던 점:

- 단순 사실 회수형 질문은 꽤 잘 맞췄다
- 예: 구성품, 수명, 허가 제품 여부

아쉬운 점:

- 답 내용은 맞아도 JSON 구조가 자주 불완전했다
- `used_chunk_ids`가 비는 경우가 있었다
- `needs_human_review`가 자주 빠졌다
- 청크 하나만 주는 `top-k=1` 최적화에서는 체크리스트형 질문이 약해졌다

즉 지금 단계의 해석은 아래가 맞다.

- 검색과 내용 회수는 기본적으로 가능하다
- 하지만 운영용으로 쓰려면 구조화 출력 안정화가 더 필요하다

## 실제로 실행하는 순서

### 1. 임베딩과 청크 만들기

```bash
/home/rb/AI/.venv-gemma-rag-index/bin/python \
  /home/rb/AI/gemma-rag/scripts/build_embedding_index.py \
  --device cpu --batch-size 4
```

### 2. Gemma RAG 모델 상태 확인

```bash
/home/rb/AI/gemma-rag/launch.sh status
```

### 3. 평가 실행

```bash
/home/rb/AI/gemma-rag/launch-eval.sh run
```

이 런처는 현재 아래 흐름으로 동작한다.

1. `e2b GPU` 시도
2. 실패하면 `CPU fallback`
3. 질문 10개 평가
4. 결과 파일 저장

## 지금 시점의 실무 결론

### 바로 쓸 수 있는 것

- 공개 한국어 의료기기 문서로 작은 테스트 코퍼스를 만들 수 있다
- `KURE-v1`로 청크 임베딩을 만들 수 있다
- `gemma-rag`를 이용해 실제 RAG 답변 평가를 돌릴 수 있다

### 아직 보완이 필요한 것

- `e2b`를 Jetson GPU에서 안정적으로 돌릴 수 있는 더 가벼운 배포 자산
- JSON 응답을 더 안정적으로 강제하는 프롬프트 또는 후처리
- 체크리스트형 질문에 맞는 청크 크기 재조정
- `used_chunk_ids`, `needs_human_review` 누락 방지

## 추천 다음 단계

1. `e2b`를 꼭 Jetson GPU에서 써야 하면, 현재 `Q8_0` 대신 더 가벼운 양자화 자산을 연결하는 방향을 우선 검토한다.
2. 검색 품질을 위해 청크 크기를 `300~450` 근처로 다시 실험한다.
3. 생성 품질을 위해 JSON 후처리 복구 로직을 추가한다.
4. 장시간 운영을 생각하면 `e4b-q4`의 쓰로틀링 패턴도 별도로 측정한다.

## 관련 파일

- 프로젝트 개요: [`README.md`](/home/rb/AI/gemma-rag/README.md)
- RAG 프로필: [`config/korean_medical_device_rag.env`](/home/rb/AI/gemma-rag/config/korean_medical_device_rag.env)
- 인덱싱 가이드: [`docs/indexing-starter-corpus.md`](/home/rb/AI/gemma-rag/docs/indexing-starter-corpus.md)
- 평가 런처: [`launch-eval.sh`](/home/rb/AI/gemma-rag/launch-eval.sh)
- 평가 스크립트: [`scripts/evaluate_rag_answers.py`](/home/rb/AI/gemma-rag/scripts/evaluate_rag_answers.py)
