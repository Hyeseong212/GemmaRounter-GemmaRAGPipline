# Gemma Server Router

`gemma-ServerRouter`는 서버 측 Gemma 라우터입니다.

역할은 하나입니다.

- 이 질문이 `RAG가 필요한 질문인지`
- 아니면 `서버 대형 LLM이 바로 답해도 되는 질문인지`

를 분기하는 것입니다.

## 플로우

1. 이미 서버로 올라온 질문이 `gemma-ServerRouter`에 들어옵니다.
2. 서버 라우터는 질문을 보고 `RAG 필요 여부`를 판단합니다.
3. `server_rag`로 판단되면 문서 검색 파이프라인으로 handoff를 만듭니다.
4. `server_llm`으로 판단되면 일반 서버 대형 모델 답변 경로로 handoff를 만듭니다.
5. 모델 출력이 이상하면 최소 휴리스틱 fallback으로 다시 결정합니다.

즉 이 프로젝트는 `local/device routing`이 아니라 `server-side RAG gate`입니다.

## 라우팅 기준

`server_rag`

- 에러코드 의미
- 매뉴얼, SOP, 절차, 문서 기준 질문
- 규격, 사양, 정책, 내부 문서 사실 확인
- 프로젝트/장비 고유 정보가 필요해 보이는 질문

`server_llm`

- 일반 설명
- 비교, 장단점, trade-off
- 구조 설명, 설계 이유, 브레인스토밍
- 문서 근거가 없어도 답할 수 있는 일반 추론

## 실행 방법

이 프로젝트는 기본적으로 `서버 Gemma endpoint`가 이미 떠 있다고 가정합니다.

기본 endpoint:

- `SERVER_ROUTER_MODEL_ENDPOINT=http://127.0.0.1:8180/v1/chat/completions`
- `SERVER_ROUTER_MODEL_NAME=gemma4-server-router`

실행:

```bash
/home/rb/AI/gemma-ServerRouter/launch.sh
```

상태 확인:

```bash
/home/rb/AI/gemma-ServerRouter/launch.sh status
```

중지:

```bash
/home/rb/AI/gemma-ServerRouter/launch.sh stop
```

## API

라우팅만 보기:

```bash
curl http://127.0.0.1:8190/route \
  -H 'Content-Type: application/json' \
  -d @/home/rb/AI/gemma-ServerRouter/examples/server_router_request.json
```

디버그 전체 보기:

```bash
curl http://127.0.0.1:8190/route/debug \
  -H 'Content-Type: application/json' \
  -d @/home/rb/AI/gemma-ServerRouter/examples/server_router_request.json
```

예제:

- [`server_router_rag_request.json`](/home/rb/AI/gemma-ServerRouter/examples/server_router_rag_request.json)
- [`server_router_llm_request.json`](/home/rb/AI/gemma-ServerRouter/examples/server_router_llm_request.json)

## 참고

현재 워크스페이스에서 직접 5090 서버를 테스트한 것은 아닙니다.

그래서 이 프로젝트는:

- 서버 라우터 API
- 프롬프트
- fallback 로직
- handoff 구조
- launch 방식

까지 만들어 둔 상태이고, 실제 서버 endpoint만 연결하면 바로 붙일 수 있게 구성했습니다.
