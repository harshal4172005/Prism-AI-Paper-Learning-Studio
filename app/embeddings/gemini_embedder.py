"""Wraps Gemini's text embedding API for manual chunks and user queries."""
import time

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

from app.config import EMBEDDING_DIM, EMBEDDING_MODEL, GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)

MAX_RETRIES = 4


def _embed_with_retry(text: str, task_type: str, sleep=time.sleep) -> list[float]:
    for attempt in range(MAX_RETRIES):
        try:
            result = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=text,
                task_type=task_type,
                output_dimensionality=EMBEDDING_DIM,
                request_options={"timeout": 30},
            )
            return result["embedding"]
        except ResourceExhausted:
            if attempt == MAX_RETRIES - 1:
                raise
            sleep(2**attempt * 10)  # 10s, 20s, 40s


def embed_text(text: str, task_type: str = "retrieval_document") -> list[float]:
    return _embed_with_retry(text, task_type)


def embed_query(text: str) -> list[float]:
    return embed_text(text, task_type="retrieval_query")


def _demo():
    import app.embeddings.gemini_embedder as mod

    sleeps = []
    attempt_count = {"n": 0}
    original = mod.genai.embed_content

    def fake_embed_content(**kwargs):
        attempt_count["n"] += 1
        if attempt_count["n"] < 3:
            raise ResourceExhausted("quota exceeded")
        return {"embedding": [0.1, 0.2]}

    mod.genai.embed_content = fake_embed_content
    try:
        result = _embed_with_retry("hello", "retrieval_document", sleep=sleeps.append)
        assert result == [0.1, 0.2]
        assert attempt_count["n"] == 3
        assert sleeps == [10, 20]
    finally:
        mod.genai.embed_content = original


if __name__ == "__main__":
    _demo()
    print("ok")
