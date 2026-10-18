from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.rag.generator import generate_answer
from app.rag.retriever import retrieve_chunks

app = FastAPI(title="Multimodal RAG AI/ML Research Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

IMAGE_DIR = Path("data/extracted_images")
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/manual-images", StaticFiles(directory=IMAGE_DIR), name="manual-images")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    sources: list[dict]


@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest):
    chunks = retrieve_chunks(request.question)
    answer = generate_answer(request.question, chunks)
    sources = [
        {
            "page_number": c["page_number"],
            "source_file": c["source_file"],
            "score": c["score"],
            "image_urls": [f"/manual-images/{Path(p).name}" for p in c["image_paths"]],
        }
        for c in chunks
    ]
    return AskResponse(answer=answer, sources=sources)


app.mount("/", StaticFiles(directory="app/frontend", html=True), name="frontend")
