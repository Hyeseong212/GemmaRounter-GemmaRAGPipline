import os
import logging
import sys
from llama_index.core import (
    VectorStoreIndex, 
    SimpleDirectoryReader, 
    StorageContext, 
    Settings
)
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.node_parser import SentenceSplitter
# 로깅 설정
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

# 1. 설정
print("🔄 BGE-M3 모델 로드 중...")
Settings.embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-m3", device="cuda:0")
Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
def update_knowledge_base(target_dir, collection_name="medical_knowledge"):
    client = QdrantClient(host="localhost", port=6333)
    
    # [권장] 데이터 꼬임 방지를 위해 기존 컬렉션을 삭제하고 새로 구축하는 것을 추천
    # 만약 유지를 원하신다면 이 부분을 주석 처리하세요.
    if client.collection_exists(collection_name):
        client.delete_collection(collection_name)
        print(f"🗑️ 기존 '{collection_name}' 컬렉션을 삭제했습니다. (새로 구축)")

    vector_store = QdrantVectorStore(client=client, collection_name=collection_name)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    # 문서 로드 시 메타데이터(파일명 등)를 강제 주입
    reader = SimpleDirectoryReader(input_dir=target_dir, recursive=True)
    documents = reader.load_data()

    print(f"✅ 총 {len(documents)}개 페이지 로드 완료.")

    # 처음부터 구축 (from_documents)를 쓰면 내부적으로 더 효율적인 배칭(Batching)을 수행합니다.
    print("🧠 지식 베이스 구축 시작 (임베딩 중)...")
    index = VectorStoreIndex.from_documents(
        documents, 
        storage_context=storage_context, 
        show_progress=True
    )
    print("✅ 초기 지식 베이스 구축 완료!")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        new_folder = sys.argv[1]
    else:
        new_folder = "./data/1권_pdf" 
        
    update_knowledge_base(new_folder)
