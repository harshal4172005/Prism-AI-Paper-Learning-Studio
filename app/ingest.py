"""CLI: ingest a manual PDF into Qdrant. Usage: python -m app.ingest <pdf_path>"""
import sys

from app.embeddings.gemini_embedder import embed_text
from app.ingestion.chunker import chunk_text
from app.ingestion.image_captioner import caption_image
from app.ingestion.pdf_loader import load_pdf
from app.vectorstore.qdrant_store import ManualVectorStore


def ingest_manual(pdf_path: str):
    store = ManualVectorStore()
    pages = load_pdf(pdf_path, image_output_dir="data/extracted_images")

    chunk_count = 0
    image_count = 0
    for page in pages:
        for chunk in chunk_text(page.text):
            vector = embed_text(chunk)
            store.upsert_chunk(
                vector=vector,
                text=chunk,
                source_file=pdf_path,
                page_number=page.page_number,
                image_paths=page.image_paths,
            )
            chunk_count += 1

        for image_path in page.image_paths:
            try:
                caption = caption_image(image_path, page.text)
                vector = embed_text(caption)
            except Exception as exc:
                print(f"  [skip] captioning failed for {image_path}: {exc}")
                continue
            store.upsert_chunk(
                vector=vector,
                text=caption,
                source_file=pdf_path,
                page_number=page.page_number,
                image_paths=[image_path],
            )
            image_count += 1

    print(f"Ingested {len(pages)} pages, {chunk_count} text chunks, {image_count} image captions from {pdf_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.ingest <pdf_path>")
        sys.exit(1)
    ingest_manual(sys.argv[1])
