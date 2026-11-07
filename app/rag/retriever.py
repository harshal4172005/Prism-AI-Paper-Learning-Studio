"""Finds the manual chunks most relevant to a user's troubleshooting question."""
from app.embeddings.gemini_embedder import embed_query
from app.vectorstore.qdrant_store import ManualVectorStore


def retrieve_chunks(query: str, top_k: int = 5):
    store = ManualVectorStore()
    query_vector = embed_query(query)
    hits = store.search(query_vector, top_k=top_k)
    return [
        {
            "id": str(hit.id),
            "kind": hit.payload.get("kind", "legacy_unknown"),
            "page_base": hit.payload.get("page_base", 0),
            "text": hit.payload["text"],
            "source_file": hit.payload["source_file"],
            "page_number": hit.payload["page_number"],
            "image_paths": hit.payload["image_paths"],
            "score": hit.score,
        }
        for hit in hits
    ]
