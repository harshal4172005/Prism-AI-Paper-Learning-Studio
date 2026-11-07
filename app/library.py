"""Persistent PDF library with document-scoped local full-text retrieval."""
import hashlib
import json
import re
import sqlite3
import os
import threading
from contextlib import contextmanager
from pathlib import Path
import pymupdf as fitz
from app.ingestion.chunker import chunk_text

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.getenv("PRISM_DATA_DIR", str(ROOT / "data"))).resolve()
LIBRARY = DATA_ROOT / "library"
IMAGES = DATA_ROOT / "previews"
MAX_BYTES = int(os.getenv("PRISM_MAX_UPLOAD_MB", "25")) * 1024 * 1024
MAX_PAGES = 100
LOCK = threading.RLock()


def _open_db():
    LIBRARY.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(LIBRARY / "library.sqlite", timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA wal_autocheckpoint=256")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY, name TEXT, title TEXT, status TEXT, pages INTEGER DEFAULT 0,
            progress INTEGER DEFAULT 0, error TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY, document_id TEXT, page INTEGER, text TEXT, images TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(text, document_id UNINDEXED, chunk_id UNINDEXED);
    """)
    from app.accounts import schema
    schema(db)
    return db


@contextmanager
def connect():
    db = _open_db()
    try:
        with db:
            yield db
    finally:
        db.close()


def list_documents():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM documents ORDER BY created_at DESC")]


def get_document(document_id):
    with connect() as db:
        row = db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return dict(row) if row else None


def register_pdf(data, name):
    if not data.startswith(b"%PDF-"):
        raise ValueError("Choose a valid PDF file.")
    if len(data) > MAX_BYTES:
        raise ValueError("Please choose a PDF smaller than 25 MB.")
    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise ValueError("Unlock this PDF before uploading it.")
            if not 0 < len(pdf) <= MAX_PAGES:
                raise ValueError("Please choose a PDF with 1 to 100 pages.")
    except ValueError:
        raise
    except Exception:
        raise ValueError("This PDF could not be opened. Try a different copy.") from None
    document_id = hashlib.sha256(data).hexdigest()[:24]
    with connect() as db:
        previous = db.execute("SELECT status FROM documents WHERE id=?", (document_id,)).fetchone()
        if previous and previous["status"] in ("ready", "processing"):
            return document_id, False
        safe_name = name.replace("\\", "/").split("/")[-1][:180] or "document.pdf"
        db.execute("INSERT OR REPLACE INTO documents(id,name,title,status) VALUES(?,?,?,?)",
            (document_id, safe_name, Path(safe_name).stem.replace("_", " "), "processing"))
        (LIBRARY / (document_id + ".pdf")).write_bytes(data)
    return document_id, True


def process_pdf(document_id):
    IMAGES.mkdir(parents=True, exist_ok=True)
    try:
        with fitz.open(LIBRARY / (document_id + ".pdf")) as pdf:
            rows = []
            for index, page in enumerate(pdf):
                text = page.get_text(sort=True).strip()
                if index == 0 and text:
                    heading = text.splitlines()[0].strip()
                    lines = text.splitlines()
                    if heading.split()[-1].lower() in {"for", "of", "and", "with", "in", "the"} and len(lines)>1:
                        heading += " " + lines[1].strip()
                    if 5 < len(heading) < 150:
                        with connect() as db:
                            db.execute("UPDATE documents SET title=? WHERE id=?", (heading, document_id))
                images = []
                # Render the original page, preserving mixed vector/raster diagrams and tables.
                if page.get_images() or len(page.get_drawings()) >= 5:
                    filename = f"{document_id}_p{index+1}.jpg"
                    images.append(str(IMAGES / filename))
                for chunk in chunk_text(text, chunk_size=1800, overlap=250):
                    rows.append((document_id, index + 1, chunk, json.dumps(images)))
                with connect() as db:
                    db.execute("UPDATE documents SET progress=?, pages=? WHERE id=?",
                        (round((index+1)/len(pdf)*90), len(pdf), document_id))
            if not rows:
                raise ValueError("No readable text was found. This PDF needs OCR; please upload a searchable copy.")
            with connect() as db:
                db.execute("DELETE FROM search WHERE document_id=?", (document_id,))
                db.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))
                for row in rows:
                    cursor = db.execute("INSERT INTO chunks(document_id,page,text,images) VALUES(?,?,?,?)", row)
                    db.execute("INSERT INTO search(text,document_id,chunk_id) VALUES(?,?,?)", (row[2], document_id, cursor.lastrowid))
                db.execute("UPDATE documents SET status='ready', progress=100, error=NULL WHERE id=?", (document_id,))
    except Exception as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Could not prepare this PDF. Try another file."
        with connect() as db:
            db.execute("UPDATE documents SET status='failed',error=? WHERE id=?", (message, document_id))


STOPWORDS = set("the a an is are was were why how what does do explain me please this that it in of to and for with from can you we about would if happens".split())


def retrieve(document_id, question, limit=8):
    document = get_document(document_id)
    if not document or document["status"] != "ready":
        raise ValueError("Select a PDF that has finished processing.")
    words = list(dict.fromkeys(w for w in re.findall(r"[a-zA-Z0-9]+", question.lower()) if w not in STOPWORDS and len(w) > 1))[:30]
    if any(word in words for word in ("scaling", "sqrt", "dk", "scaled", "square")):
        words += ["scaled", "gradients", "softmax"]
    if "architecture" in words:
        words += ["encoder", "decoder"]
    if "heads" in words or "head" in words:
        words += ["multi", "head"]
    if not words:
        return []
    expression = " OR ".join('"' + word + '"' for word in dict.fromkeys(words))
    with connect() as db:
        if any(word in words for word in ("summary", "summarize", "overview")) or "main idea" in question.lower():
            rows = db.execute("SELECT *, 0.0 AS rank FROM chunks WHERE document_id=? AND page<=2 ORDER BY id LIMIT ?", (document_id, limit)).fetchall()
        else:
            rows = db.execute("""SELECT c.*, bm25(search) AS rank FROM search
            JOIN chunks c ON c.id=search.chunk_id
            WHERE search MATCH ? AND search.document_id=? ORDER BY rank LIMIT ?""",
            (expression, document_id, limit * 3)).fetchall()
    # Cap per-page repetition so the answer has broader evidence.
    chosen, counts = [], {}
    for row in rows:
        if counts.get(row["page"], 0) >= 2:
            continue
        counts[row["page"]] = counts.get(row["page"], 0) + 1
        image_paths = []
        if json.loads(row["images"]) and sum(bool(c["image_paths"]) for c in chosen) < 3:
            image_paths = [str(preview(document_id, row["page"]))]
        chosen.append({"document_id": document_id, "text": row["text"], "source_file": document["name"], "page_number": row["page"],
            "page_base": 1, "kind": "text", "image_paths": image_paths, "score": -row["rank"]})
        if len(chosen) == limit:
            break
    return chosen


def preview(document_id, page_number):
    if not re.fullmatch(r"[a-f0-9]{24}", document_id) or not 1 <= page_number <= MAX_PAGES:
        raise ValueError("Invalid page")
    path = IMAGES / f"{document_id}_p{page_number}.jpg"
    with LOCK:
        IMAGES.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with fitz.open(LIBRARY / (document_id + ".pdf")) as pdf:
                if page_number > len(pdf):
                    raise ValueError("Page not found")
                page = pdf[page_number-1]
                scale = min(1.2, 1200 / max(page.rect.width, page.rect.height))
                page.get_pixmap(matrix=fitz.Matrix(scale,scale), alpha=False).save(path, jpg_quality=76)
        path.touch()
        files = sorted(IMAGES.glob("*.jpg"), key=lambda item: item.stat().st_mtime)
        total = sum(item.stat().st_size for item in files)
        for item in files:
            if total <= 32 * 1024 * 1024:
                break
            if item != path:
                total -= item.stat().st_size
                item.unlink(missing_ok=True)
    return path


def delete_unreferenced(document_id):
    with LOCK, connect() as db:
        if db.execute("SELECT 1 FROM user_documents WHERE document_id=?",(document_id,)).fetchone():
            return
        db.execute("DELETE FROM search WHERE document_id=?",(document_id,))
        db.execute("DELETE FROM chunks WHERE document_id=?",(document_id,))
        db.execute("DELETE FROM documents WHERE id=?",(document_id,))
        (LIBRARY / (document_id + ".pdf")).unlink(missing_ok=True)
        for item in IMAGES.glob(document_id + "_p*.jpg"):
            item.unlink(missing_ok=True)


def storage_bytes():
    return sum(item.stat().st_size for folder in (LIBRARY, IMAGES) if folder.exists()
        for item in folder.iterdir() if item.is_file())
