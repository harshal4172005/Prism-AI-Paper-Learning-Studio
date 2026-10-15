"""Wraps Gemini's text embedding API for manual chunks and user queries."""
import google.generativeai as genai

from app.config import EMBEDDING_DIM, EMBEDDING_MODEL, GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)


def embed_text(text: str, task_type: str = "retrieval_document") -> list[float]:
    result = genai.embed_content(
        model=EMBEDDING_MODEL,
        content=text,
        task_type=task_type,
        output_dimensionality=EMBEDDING_DIM,
    )
    return result["embedding"]


def embed_query(text: str) -> list[float]:
    return embed_text(text, task_type="retrieval_query")
