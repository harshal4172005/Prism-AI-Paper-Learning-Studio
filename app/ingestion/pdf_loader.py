"""Extracts per-page text and images from a manual/paper PDF.

Covers two kinds of figures: embedded raster images (photos, screenshots) and
vector-drawn diagrams (architecture diagrams, flowcharts, plots) — common in
academic papers and invisible to PyMuPDF's raster image extraction. For a page
with vector drawings but no raster images, the whole page is rasterized instead.
"""
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # pymupdf

# ponytail: whole-page screenshot instead of a tight crop around just the diagram;
# upgrade path: cluster get_drawings() bounding boxes to isolate individual figures.
MIN_DRAWINGS_FOR_PAGE_RENDER = 5


@dataclass
class PageContent:
    page_number: int
    text: str
    image_paths: list[str] = field(default_factory=list)


def load_pdf(pdf_path: str, image_output_dir: str) -> list[PageContent]:
    doc = fitz.open(pdf_path)
    out_dir = Path(image_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    for page_index, page in enumerate(doc):
        text = page.get_text().strip()
        image_paths = []
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_path = out_dir / f"page{page_index}_img{img_index}.{base_image['ext']}"
            image_path.write_bytes(base_image["image"])
            image_paths.append(str(image_path))

        if not image_paths and len(page.get_drawings()) >= MIN_DRAWINGS_FOR_PAGE_RENDER:
            image_path = out_dir / f"page{page_index}_vector.png"
            page.get_pixmap(dpi=150).save(str(image_path))
            image_paths.append(str(image_path))

        pages.append(PageContent(page_number=page_index, text=text, image_paths=image_paths))

    doc.close()
    return pages
