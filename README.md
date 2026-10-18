# multimodal-ai-research-rag

Multimodal RAG assistant for AI/ML research papers. Ingests PDFs (text + figures —
including vector-drawn architecture diagrams that most PDF tools miss), captions
each figure with Gemini Vision so it's independently searchable, embeds everything
into Qdrant, and answers questions grounded in the retrieved paper excerpts and
diagrams, with page citations.

Currently ingested: *Attention Is All You Need*, *Retrieval-Augmented Generation
for Knowledge-Intensive NLP Tasks*, *BERT*, *GPT-3*, *LoRA*, *ResNet*, and
*Denoising Diffusion Probabilistic Models*.

## Status
- [x] Ingestion pipeline: PDF text + image extraction, chunking
- [x] Vector-diagram capture: pages with no raster images but real vector
      drawings (common for academic figures) are rasterized and captioned too
- [x] Gemini embeddings + Qdrant vector storage (`python -m app.ingest <pdf_path>`)
- [x] Image captioning at ingest time (Gemini Vision) so figures are retrievable
      by their own visual content, not just by nearby text
- [x] Retrieval + multimodal RAG answer generation, with page citations
      (`python -m app.ask "<question>"`)
- [x] Generation fallback chain: Gemini 3.6 → 3.8 → 3.5-lite → Groq → NVIDIA,
      so a rate-limited model doesn't block an answer
- [x] Embedding retry/backoff for transient rate limits
- [x] FastAPI backend + chat frontend with markdown rendering and an image
      gallery for retrieved diagrams (`uvicorn app.api.main:app --reload`,
      then open http://localhost:8000)

## Stack
- FastAPI backend
- Google Gemini (embeddings, vision captioning, generation)
- Groq / NVIDIA NIM as text-only generation fallbacks
- Qdrant vector database
- PyMuPDF for PDF parsing and page rasterization

## Setup
1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and add your Gemini API key (Groq/NVIDIA keys optional).
3. `docker compose up -d` to run Qdrant locally.

## Known limitation
Gemini's free tier caps embedding requests at 1000/day — ingesting several
image-heavy papers in one session can exhaust it. The embedder retries on
per-minute rate limits automatically, but a daily cap has no workaround short
of waiting for reset or using a different API key.
