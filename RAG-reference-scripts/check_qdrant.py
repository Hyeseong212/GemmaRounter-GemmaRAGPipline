# check_qdrant.py
from qdrant_client import QdrantClient
client = QdrantClient(host="localhost", port=6333)
collection_info = client.get_collection("medical_knowledge")
print(f"📊 현재 저장된 지식 조각 수: {collection_info.points_count}")
