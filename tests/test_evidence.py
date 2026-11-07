import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import fitz
from fastapi.testclient import TestClient
from app.api.main import app
from app.rag.demo import DEMO_CHUNKS
from app.rag.evidence import audit_claims, prepare_sources, build_report, compare_reports
from app.ingestion.pdf_loader import load_pdf
from app.vectorstore.qdrant_store import ManualVectorStore


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.sources = prepare_sources(DEMO_CHUNKS)

    def claim(self, quote, sid="S1"):
        return [{"text": "A claim", "evidence": [{"source_id": sid, "quote": quote}]}]

    def test_quote_found_with_whitespace_normalization(self):
        quote = "The attention score matrix\n grows quadratically with sequence length."
        result = audit_claims(self.claim(quote), self.sources)
        self.assertEqual(result[0]["status"], "quote_anchored")

    def test_fabricated_quote_is_not_anchored(self):
        result = audit_claims(self.claim("The model is faster by 99 percent on all hardware."), self.sources)
        self.assertEqual(result[0]["status"], "needs_review")
        self.assertFalse(result[0]["evidence"][0]["quote_found"])

    def test_unknown_source_and_tiny_quote_are_rejected(self):
        for quote, sid in [(DEMO_CHUNKS[0]["text"], "S999"), ("the", "S1")]:
            self.assertEqual(audit_claims(self.claim(quote, sid), self.sources)[0]["status"], "needs_review")

    def test_caption_is_not_primary_evidence(self):
        self.sources[0]["kind"] = "figure_caption"
        result = audit_claims(self.claim(self.sources[0]["text"]), self.sources)[0]
        self.assertEqual(result["status"], "needs_review")
        self.assertTrue(result["evidence"][0]["quote_found"])

    def test_bad_evidence_types_fail_closed(self):
        result = audit_claims([{"text": "x", "evidence": [{"source_id": [], "quote": None}]}], self.sources)
        self.assertEqual(result[0]["status"], "needs_review")

    def test_duplicate_sources_are_collapsed(self):
        self.assertEqual(len(prepare_sources(DEMO_CHUNKS + DEMO_CHUNKS)), 3)

    def test_legacy_page_conversion(self):
        chunk = dict(DEMO_CHUNKS[0], page_number=0, page_base=0)
        self.assertEqual(prepare_sources([chunk])[0]["page"], 1)

    def test_invalid_model_output_is_not_accepted(self):
        for output in ["not json", "[]", '{"claims": "not a list"}']:
            report = build_report("question", self.sources, generate=lambda *a, **kw: (output, {}))
            self.assertEqual(report["status"], "invalid_model_output")
            self.assertEqual(report["claims"], [])

    def test_no_sources_does_not_call_model(self):
        generate = MagicMock()
        self.assertEqual(build_report("q", [], generate=generate)["status"], "insufficient_evidence")
        generate.assert_not_called()






class IngestionTests(unittest.TestCase):
    def test_pdf_images_do_not_collide_and_pages_are_one_based(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ["one", "two"]:
                doc = fitz.open()
                page = doc.new_page()
                page.insert_text((50,50), name)
                for i in range(6):
                    page.draw_rect(fitz.Rect(50+i*20,100,60+i*20,160))
                doc.save(root / (name + ".pdf")); doc.close()
            first = load_pdf(str(root / "one.pdf"),str(root / "images"))
            second = load_pdf(str(root / "two.pdf"),str(root / "images"))
            self.assertEqual(first[0].page_number,1)
            self.assertNotEqual(first[0].image_paths[0],second[0].image_paths[0])
            self.assertTrue(Path(first[0].image_paths[0]).exists())

    def test_reingestion_uses_stable_ids(self):
        store = object.__new__(ManualVectorStore)
        store.client = MagicMock()
        kwargs = dict(vector=[0.1]*768,text="same excerpt",source_file="paper.pdf",page_number=1,image_paths=[])
        self.assertEqual(store.upsert_chunk(**kwargs),store.upsert_chunk(**kwargs))
        self.assertNotEqual(store.upsert_chunk(**kwargs),store.upsert_chunk(**(kwargs | {"kind":"figure_caption"})))


if __name__ == "__main__":
    unittest.main()
