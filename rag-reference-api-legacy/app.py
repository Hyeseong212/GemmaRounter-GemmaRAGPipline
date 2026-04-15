import torch
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import PromptTemplate
from qdrant_client import QdrantClient
import requests

# 추가된 부분: CustomLLM 관련 임포트
from llama_index.core.llms import CustomLLM, CompletionResponse, CompletionResponseGen, LLMMetadata
from llama_index.core.llms.callbacks import llm_completion_callback

app = FastAPI()

# 1. C++ 서버와 통신하는 LLM 클래스 정의 (누락되었던 부분)
class MyCppServerLLM(CustomLLM):
    url: str = "http://localhost:8080/infer"

    @property
    def metadata(self) -> LLMMetadata:
        # InternVL3-78B 모델 스펙에 맞춤
        return LLMMetadata(context_window=8192, num_output=2048, model_name="InternVL3-78B")

    @llm_completion_callback()
    def complete(self, prompt: str, **kwargs) -> CompletionResponse:
        payload = {"prompt": prompt, "image": ""}
        try:
            # 타임아웃을 넉넉히 설정 (78B 모델 추론 시간 고려)
            res = requests.post(self.url, json=payload, timeout=600)
            res.raise_for_status()
            return CompletionResponse(text=res.text.strip())
        except Exception as e:
            return CompletionResponse(text=f"Error connecting to C++ server: {str(e)}")

    @llm_completion_callback()
    def stream_complete(self, prompt: str, **kwargs) -> CompletionResponseGen:
        response = self.complete(prompt, **kwargs)
        yield CompletionResponse(text=response.text, delta=response.text)

# 2. 전역 설정 (Embedding & LLM)
print("🔄 모델 및 설정 로드 중...")
Settings.embed_model = HuggingFaceEmbedding(
    model_name="BAAI/bge-m3", 
    device="cuda:1",  # C++ 서버와 다른 GPU 사용 권장
    model_kwargs={"torch_dtype": torch.float16}
)
Settings.llm = MyCppServerLLM()

# 3. Qdrant 인덱스 연결
client = QdrantClient(host="localhost", port=6333)
vector_store = QdrantVectorStore(client=client, collection_name="medical_knowledge")
index = VectorStoreIndex.from_vector_store(vector_store=vector_store)

# 4. 쿼리 엔진 및 프롬프트 설정
query_engine = index.as_query_engine(similarity_top_k=2)

# app.py의 qa_prompt_tmpl_str 부분 수정
# app.py 내의 프롬프트 설정 부분 수정
qa_prompt_tmpl_str = (
    "당신은 재활의학 전문 AI 어시스턴트입니다. 아래 제공된 [컨텍스트] 문서 내용을 바탕으로 질문에 답하세요.\n\n"
    "[컨텍스트 정보]\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n\n"
    "수행 지침:\n"
    "1. [컨텍스트 정보]에 표(Table)가 포함되어 있다면, 표 안의 모든 개별 항목을 누락 없이 상세히 나열하세요.\n"
    "2. 답변 시 문서에 사용된 전문 용어를 임의로 수정하지 말고 원문 그대로(한국어/영어 병기) 사용하세요.\n"
    "3. 정보의 양이 많을 경우 단순히 요약하지 말고, 불렛 포인트(●)나 번호를 사용하여 구조적으로 가독성 있게 작성하세요.\n"
    "4. 답변은 질문에 대한 직접적인 정보 외에도 문서 내 관련 수치나 통계가 있다면 함께 언급하세요.\n"
    "5. 답변은 최소 5문장 이상의 상세한 형태로 작성하세요.\n\n"
    "질문: {query_str}\n\n"
    "한국어 상세 답변:"
)
qa_prompt_tmpl = PromptTemplate(qa_prompt_tmpl_str)
query_engine.update_prompts(
    {"response_synthesizer:text_qa_template": qa_prompt_tmpl}
)

class QueryRequest(BaseModel):
    question: str

import json
from fastapi import Response

@app.post("/ask")
async def ask(request: QueryRequest):
    # 1. 쿼리 실행 (C++ 서버로부터 응답을 받음)
    response = query_engine.query(request.question)
    
    # [핵심 수정] C++ 서버에서 온 텍스트가 깨져 있다면 강제로 latin-1 -> utf-8 변환 시도
    # (많은 C++ 서버 라이브러리들이 한글을 바이트로 보낼 때 발생하는 현상 해결)
    raw_text = str(response)
    try:
        # 깨진 글자(ì ë ë)를 바이트로 되돌린 후 utf-8로 다시 읽기
        clean_text = raw_text.encode('latin-1').decode('utf-8')
    except Exception:
        # 변환에 실패하면 원래 텍스트 사용
        clean_text = raw_text

    # 2. 출처 정보 추출
    sources = []
    for node in response.source_nodes:
        file_name = node.metadata.get("file_name", "알 수 없는 파일")
        page_num = node.metadata.get("page_label", "N/A")
        sources.append(f"출처: {file_name} (p.{page_num})")
    
    # 3. 깨끗한 텍스트와 출처 결합
    final_answer = f"{clean_text}\n\n---\n" + "\n".join(sources)
    
    # 4. 최종 반환 (ensure_ascii=False 적용)
    import json
    from fastapi import Response
    result_json = json.dumps({"answer": final_answer}, ensure_ascii=False)
    
    return Response(content=result_json, media_type="application/json")

if __name__ == "__main__":
    import uvicorn
    print("🚀 FastAPI 서버가 8000번 포트에서 시작됩니다.")
    uvicorn.run(app, host="0.0.0.0", port=8000)
