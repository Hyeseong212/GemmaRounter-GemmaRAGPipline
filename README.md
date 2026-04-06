# GemmaRouter-GemmaRAGPipline

이 저장소는 Jetson Orin 환경에서 Gemma 기반 로컬 LLM, 라우팅, RAG를 프로젝트별로 분리해 운영하기 위한 워크스페이스입니다.

## 플로우

현재 기본 흐름은 아래와 같습니다.

1. 사용자의 질문이 `gemma-routing`으로 들어옵니다.
2. 라우터가 먼저 질문에서 신호를 추출합니다.
   - 예: 에러코드, 상태조회, 문서참조 필요 여부, 짧은 답변 가능성
3. 명확한 케이스는 하드룰로 바로 분기합니다.
   - 상태조회 -> 로컬 규칙 처리
   - 에러코드/매뉴얼/절차 -> `server_rag`
   - 짧은 일반 질문 -> `local_llm`
   - 위험 질문 -> `human_review` 또는 `block`
4. 애매한 일반 질문만 로컬 Gemma가 한 번 더 추론해서 `local_llm / server_llm / server_rag` 중 하나로 분기합니다.
5. 최종 결과는 `handoff` 형태로 내려가며, 어떤 시스템이 다음 작업을 해야 하는지 같이 전달합니다.
6. `/handle` 경로를 쓰면 `local_llm`으로 분기된 경우 실제 로컬 Gemma가 답변까지 생성합니다.
7. 로컬 답변이 20자를 넘기면 로컬 답변을 버리고 `server_llm`으로 다시 넘깁니다.

즉 지금 구조는 `완전 규칙 기반`도 아니고 `완전 LLM 자율 판단`도 아닙니다.  
`안전한 규칙 기반 분기 + 작은 로컬 LLM 보조 추론` 구조입니다.

## How To Use

가장 쉬운 실행 방법은 각 프로젝트 루트의 `launch.sh`를 쓰는 것입니다.

### 프로젝트 구성

- [`gemma-routing`](/home/rb/AI/gemma-routing)
  - 질문 분기, 안전 게이트, 로컬 답변 실행
- [`gemma-rag`](/home/rb/AI/gemma-rag)
  - 문서 기반 RAG 응답 생성
- [`gemma-tranferRobotLLM`](/home/rb/AI/gemma-tranferRobotLLM)
  - 이승로봇용 로컬 LLM, STT 교정 및 TTS용 답변 생성

### 가장 자주 쓰는 명령

Routing 시작
```bash
/home/rb/AI/gemma-routing/launch.sh
```

Routing 상태 확인
```bash
/home/rb/AI/gemma-routing/launch.sh status
```

Routing 중지
```bash
/home/rb/AI/gemma-routing/launch.sh stop
```

Transfer Robot 시작
```bash
/home/rb/AI/gemma-tranferRobotLLM/launch.sh
```

RAG 시작
```bash
/home/rb/AI/gemma-rag/launch.sh
```

`launch.sh`를 실행하면 기존에 떠 있던 Gemma 컨테이너를 먼저 정리한 뒤 새로 시작합니다.

### Routing API 사용

Routing 프로젝트를 띄우면 아래 두 가지가 같이 올라옵니다.

- 모델 서버: `8080`
- 라우터 API: `8090`

라우팅만 보고 싶을 때:

```bash
curl http://127.0.0.1:8090/route \
  -H 'Content-Type: application/json' \
  -d @/home/rb/AI/gemma-routing/examples/local_general_router_request.json
```

라우팅 디버그 전체를 보고 싶을 때:

```bash
curl http://127.0.0.1:8090/route/debug \
  -H 'Content-Type: application/json' \
  -d @/home/rb/AI/gemma-routing/examples/local_general_router_request.json
```

로컬 답변 생성까지 같이 보고 싶을 때:

```bash
curl http://127.0.0.1:8090/handle \
  -H 'Content-Type: application/json' \
  -d @/home/rb/AI/gemma-routing/examples/local_general_router_request.json
```

### 예제 데이터

기본 예제:

- [`local_general_router_request.json`](/home/rb/AI/gemma-routing/examples/local_general_router_request.json)
- [`server_general_router_request.json`](/home/rb/AI/gemma-routing/examples/server_general_router_request.json)
- [`router_api_request.json`](/home/rb/AI/gemma-routing/examples/router_api_request.json)

대량 테스트용 예제:

- [`bulk_local_router_requests.json`](/home/rb/AI/gemma-routing/examples/bulk_local_router_requests.json)
- [`bulk_server_router_requests.json`](/home/rb/AI/gemma-routing/examples/bulk_server_router_requests.json)
- [`bulk_rag_router_requests.json`](/home/rb/AI/gemma-routing/examples/bulk_rag_router_requests.json)

### 추가 문서

- 전체 사용 가이드: [`GemmaHowToUse`](/home/rb/AI/GemmaHowToUse)
- Routing 설명: [`gemma-routing/README.md`](/home/rb/AI/gemma-routing/README.md)
- Routing 스키마: [`gemma-routing/docs/router-schema.md`](/home/rb/AI/gemma-routing/docs/router-schema.md)
