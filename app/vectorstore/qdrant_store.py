"""Thin wrapper around Qdrant for storing and searching manual chunk embeddings."""
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import EMBEDDING_DIM, QDRANT_COLLECTION, QDRANT_URL


class ManualVectorStore:
    def __init__(self):
        self.client = QdrantClient(url=QDRANT_URL)
        self._ensure_collection()

    def _ensure_collection(self):
        if not self.client.collection_exists(QDRANT_COLLECTION):
            self.client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )

    def upsert_chunk(self, vector: list[float], text: str, source_file: str,
                      page_number: int, image_paths: list[str], kind: str = "text") -> str:
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_file}:{page_number}:{kind}:{text}"))
        self.client.upsert(
            collection_name=QDRANT_COLLECTION,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "text": text,
                    "kind": kind,
                    "page_base": 1,
                    "source_file": source_file,
                    "page_number": page_number,
                    "image_paths": image_paths,
                },
            )],
        )
        return point_id

    def search(self, query_vector: list[float], top_k: int = 5):
        return self.client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vector,
            limit=top_k,
        ).points
