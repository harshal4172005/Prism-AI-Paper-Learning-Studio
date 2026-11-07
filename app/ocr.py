"""Bounded, local OCR; document contents never leave the server for extraction."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import pymupdf as fitz

MAX_SCAN_PAGES=20
DOCUMENT_SECONDS=90


def read_page(page,deadline):
    binary=shutil.which("tesseract")
    if not binary:
        raise ValueError("OCR is not available on this installation yet. Try again later or upload a searchable PDF.")
    remaining=deadline-time.monotonic()
    if remaining<1:
        raise ValueError("OCR took too long. Split the photo PDF into a smaller file and try again.")
    scale=min(3,2000/max(page.rect.width,page.rect.height))
    with tempfile.TemporaryDirectory(prefix="prism-ocr-") as temporary:
        image=Path(temporary)/"page.png"
        page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csGRAY,alpha=False).save(image)
        try:
            result=subprocess.run([binary,str(image),"stdout","-l","eng","--psm","3","--dpi","200"],
                stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=min(20,remaining),
                env={"PATH":os.defpath,"LANG":"C.UTF-8","OMP_THREAD_LIMIT":"1"},check=False)
        except subprocess.TimeoutExpired:
            raise ValueError("OCR took too long on this page. Try a clearer photo or a smaller PDF.") from None
        if result.returncode:
            raise ValueError("OCR could not read this page. Try a clearer, upright photo.")
        text=result.stdout.decode("utf-8",errors="replace").strip()
        if len(text)>100_000:
            raise ValueError("This scanned page contains too much text. Split it into smaller pages.")
        return text
