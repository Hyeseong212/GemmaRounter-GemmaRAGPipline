# Runtime Lane And KV Design

이 문서는 `llama-rest-core`의 현재 실행 구조와, 이후 최적화 방향을 정리한다.

## 현재 상태

현재 서버는 `GGUF Gemma 4 31B` 한 개를 로드한 뒤, 하나의 워커에서 `/infer` 요청을 처리한다.

- 모델 가중치: 단일 프로세스
- KV cache: 단일 프로세스
- HTTP 진입점: `18088`
- 텍스트/멀티모달 요청: 같은 프로세스에서 처리

즉 현재는 `text 전용 서버`와 `multimodal 전용 서버`가 따로 도는 구조가 아니다.

다만 큐는 이제 논리적으로 두 개로 분리되어 있다.

- `text lane`
  - server router / RAG / final-score가 내부적으로 사용하는 텍스트 생성 요청
- `multimodal lane`
  - 사용자가 직접 `/infer`에 넣는 이미지/영상 요청

현재 스케줄러는 `text lane`을 우선하되, `multimodal lane`이 완전히 굶지 않도록 간단한 burst 제한을 둔다.

## 현재 KV cache 수치

현재 로그 기준 수치는 아래와 같다.

- `n_ctx = 8192`
- `n_seq_max = 1`
- non-SWA KV: 약 `640 MiB`
- SWA KV: 약 `6400 MiB`
- 총 KV: 약 `7040 MiB`

GPU 분배:

- GPU0: 약 `2944 MiB`
- GPU1: 약 `4096 MiB`

즉 현재 요청 시점에 VRAM이 크게 증가하지 않는 이유는, KV가 서버 시작 시점에 미리 잡혀 있기 때문이다.

## 왜 text / multimodal을 프로세스로 분리하지 않았는가

같은 `31B` 모델을 프로세스 두 개로 띄우면 모델 가중치가 두 번 올라간다.

이 경우:

- KV만 분리되는 것이 아니라
- 모델 본체 VRAM도 거의 중복된다

현재 5090 x 2 구성에서는 이 방식이 `queue 분리`보다 비용이 크다.

그래서 현재 방향은:

- `모델/KV는 공유`
- `큐만 logical lane으로 분리`
- `활성 생성 슬롯은 제한`

으로 간다.

## 현재 최적화 방향

현재 워크로드 특성은 아래에 가깝다.

- 요청은 많이 들어옴
- 실제 생성은 1~2개만 동시에 처리하면 충분
- 나머지는 대기열에서 순서대로 처리

이 경우 1차 최적화는 `RAM queue + 제한된 active GPU slot`이다.

정리:

1. 요청은 RAM 큐에 저장
2. GPU에서는 활성 슬롯만 유지
3. 텍스트 파이프라인 요청은 text lane 우선
4. 이미지/영상 요청은 multimodal lane으로 분리

이 방식은 `모든 요청의 KV를 RAM으로 swap`하는 구조보다 단순하고, 현재 짧은 request-response 워크로드에 더 잘 맞는다.

## KV swap / restore는 언제 필요한가

`KV를 RAM에 저장했다가 다시 복구`하는 구조는 아래 경우에 효과가 있다.

- 긴 대화 세션
- 긴 멀티모달 세션
- 요청 중단 후 재개
- 동일한 prefix를 반복적으로 재사용

반대로 현재 파이프라인처럼:

- Jetson 1차 결과 수신
- 서버 2차 라우팅
- RAG 또는 server answer
- final-score

처럼 짧게 끝나는 요청은 `queue 관리`가 먼저다.

즉 KV swap / restore는 2차 최적화로 보는 것이 맞다.

## 현재 병렬 이슈

`LLAMA_REST_PARALLEL > 1`은 아직 안정화되지 않았다.

현재 확인된 문제:

- `seq_id` 범위 문제는 수정했음
- 하지만 `logits / sampler` 경로가 멀티슬롯에서 아직 안정적이지 않음

즉 현재 병렬 병목은 `VRAM 부족`보다 `런타임 구현`이다.

## 다음 권장 단계

1. 현재 logical lane 구조 유지
2. text lane 요청 우선순위 정책 다듬기
3. 멀티슬롯 생성 경로를 안정화
4. 그 다음 `active slot 2`부터 검증
5. 이후 필요하면 `KV snapshot / restore` 추가

## 실무 기준 결론

현재 기준으로는 아래 판단이 맞다.

- `KV cache를 RAM에 저장하고 필요할 때만 VRAM으로 올리는 구조`
  - 지금 당장 1순위는 아님
- `RAM queue + 제한된 active slot + text/multimodal logical lane 분리`
  - 지금 1순위 최적화 방향

