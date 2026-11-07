import json
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
import fitz
from fastapi.testclient import TestClient
from app import library
from app.api.main import app
from app.rag.teacher import explain


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.patch = patch.object(library, "LIBRARY", Path(self.folder.name) / "library")
        self.images = patch.object(library, "IMAGES", Path(self.folder.name) / "images")
        self.patch.start(); self.images.start()
        self.client = TestClient(app)
        self.client.post("/api/auth/signup",json={"email":"reader@example.com","password":"strong-pass-123","name":"Reader"})

    def tearDown(self):
        self.patch.stop(); self.images.stop(); self.folder.cleanup()

    def pdf(self, text):
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((50, 50), text)
            return pdf.tobytes()

    def upload(self, text="Scaling Study. Attention scaling divides logits before softmax."):
        return self.client.post("/api/documents?filename=study.pdf", content=self.pdf(text), headers={"Content-Type":"application/pdf"})

    def test_upload_is_searchable_and_repeat_is_idempotent(self):
        data = self.pdf("Scaling Study. Attention scaling divides logits before softmax.")
        first = self.client.post("/api/documents?filename=study.pdf",content=data).json()["document"]["id"]
        second = self.client.post("/api/documents?filename=study.pdf",content=data).json()["document"]["id"]
        self.assertEqual(first, second)
        self.assertEqual(len(library.list_documents()),1)
        self.assertEqual(library.get_document(first)["status"],"ready")
        chunks = library.retrieve(first,"Why use attention scaling?")
        self.assertTrue(chunks)
        self.assertEqual(chunks[0]["page_number"],1)

    def test_retrieval_cannot_mix_documents(self):
        one = self.upload("Apple experiments describe apples and fruit.").json()["document"]["id"]
        two = self.upload("Attention softmax scaling describes neural networks.").json()["document"]["id"]
        self.assertEqual(library.retrieve(one,"softmax"),[])
        self.assertTrue(library.retrieve(two,"softmax"))

    def test_bad_pdf_and_scanned_pdf_fail_helpfully(self):
        self.assertEqual(self.client.post("/api/documents",content=b"not a pdf").status_code,422)
        with patch("app.ocr.read_page",return_value=""):
            result = self.upload("").json()["document"]["id"]
        self.assertIsNone(library.get_document(result))
        self.assertFalse((library.LIBRARY/(result+".pdf")).exists())
        self.assertIn("OCR",self.client.get("/api/documents").json()["notices"][0]["error"])
        self.assertEqual(self.client.get("/api/me").json()["usage"]["pdf_bytes"],0)

    def test_scanned_pdf_is_ocr_searchable_and_sources_are_labelled(self):
        with fitz.open() as original:
            page=original.new_page();page.insert_text((50,100),"Certificate of test completion",fontsize=20)
            image=page.get_pixmap().tobytes("png")
        with fitz.open() as scanned:
            page=scanned.new_page();page.insert_image(page.rect,stream=image)
            data=scanned.tobytes()
            self.assertEqual(page.get_text(),"")
        with patch("app.ocr.read_page",return_value="Certificate of test completion. Attention scaling study.") as ocr:
            result=self.client.post("/api/documents?filename=scan.pdf",content=data)
        self.assertEqual(result.status_code,202)
        document_id=result.json()["document"]["id"]
        self.assertEqual(library.get_document(document_id)["ocr_pages"],1)
        sources=library.retrieve(document_id,"certificate")
        self.assertEqual(sources[0]["kind"],"ocr")
        self.assertEqual(len(sources[0]["image_paths"]),1)
        self.assertEqual(ocr.call_count,1)

    def test_failed_upload_does_not_remove_valid_library_material(self):
        valid=self.upload().json()["document"]["id"]
        before=self.client.get("/api/me").json()["usage"]["pdf_bytes"]
        with patch("app.ocr.read_page",return_value=""):
            self.upload("")
        result=self.client.get("/api/me").json()["usage"]
        self.assertEqual(result["documents"],1)
        self.assertEqual(result["pdf_bytes"],before)
        self.assertEqual(self.client.get(f"/api/documents/{valid}/pdf").status_code,200)

    def test_ocr_process_gets_no_provider_credentials_or_shell(self):
        import time
        from app import ocr
        from types import SimpleNamespace
        with fitz.open(stream=self.pdf(""),filetype="pdf") as pdf:
            with patch("app.ocr.shutil.which",return_value="/usr/bin/tesseract"),patch("app.ocr.subprocess.run",return_value=SimpleNamespace(returncode=0,stdout=b"Readable scan")) as run:
                self.assertEqual(ocr.read_page(pdf[0],time.monotonic()+90),"Readable scan")
        kwargs=run.call_args.kwargs
        self.assertEqual(set(kwargs["env"]),{"PATH","LANG","OMP_THREAD_LIMIT"})
        self.assertNotIn("shell",kwargs)
        self.assertLessEqual(kwargs["timeout"],20)

    @unittest.skipUnless(shutil.which("tesseract"),"Native OCR runtime is not installed")
    def test_real_native_ocr_reads_an_image_only_pdf(self):
        with fitz.open() as source:
            page=source.new_page();page.insert_text((50,100),"CERTIFICATE OF COMPLETION",fontsize=20)
            page.insert_text((50,150),"Name: Alex Example",fontsize=18)
            page.insert_text((50,200),"Course: Machine Learning",fontsize=18)
            image=page.get_pixmap(matrix=fitz.Matrix(2,2)).tobytes("png")
        with fitz.open() as scanned:
            page=scanned.new_page();page.insert_image(page.rect,stream=image)
            data=scanned.tobytes()
        result=self.client.post("/api/documents?filename=photo-certificate.pdf",content=data)
        document_id=result.json()["document"]["id"]
        document=library.get_document(document_id)
        self.assertIsNotNone(document)
        self.assertEqual(document["status"],"ready")
        sources=library.retrieve(document_id,"Machine Learning")
        self.assertTrue(sources)
        self.assertTrue(any("Alex Example" in source["text"] for source in sources))

    def test_scan_page_limit_cleans_up_instead_of_saving_partial_material(self):
        with fitz.open() as scanned:
            for _ in range(21):scanned.new_page()
            data=scanned.tobytes()
        with patch("app.ocr.read_page",return_value="Readable scanned page about attention scaling.") as ocr:
            response=self.client.post("/api/documents?filename=too-many-scans.pdf",content=data)
        self.assertEqual(ocr.call_count,20)
        self.assertIsNone(library.get_document(response.json()["document"]["id"]))
        self.assertIn("20 scanned",self.client.get("/api/documents").json()["notices"][0]["error"])

    def test_original_pdf_and_missing_document(self):
        result = self.upload().json()["document"]["id"]
        self.assertEqual(self.client.get(f"/api/documents/{result}/pdf").headers["content-type"],"application/pdf")
        self.assertEqual(self.client.get("/api/documents/unknown/pdf").status_code,404)
        self.assertEqual(self.client.get("/api/documents/"+"a"*24+"/pdf").status_code,404)



class TeacherTests(unittest.TestCase):
    def test_single_followup_string_from_backup_is_normalized(self):
        raw={"title":"Explanation","introduction":"An example","sections":[],"takeaway":"The idea",
             "followups":"Can you show an example?","figure_source_ids":"UNKNOWN"}
        answer,_=explain("question",self.source(),generate=lambda *a,**kw:(json.dumps(raw),{}))
        self.assertEqual(answer["followups"],["Can you show an example?"])
        self.assertEqual(answer["figure_source_ids"],[])

    def test_optional_null_fields_do_not_discard_a_valid_quiz(self):
        raw={"title":"Quiz","introduction":"Try these questions","sections":None,"takeaway":"Review your answer",
             "figure_source_ids":None,"followups":None,"check_in":None,
             "quiz":[{"question":"Which?","options":["A","B","C","D"],"correct_index":0,"explanation":"Because A.","source_ids":None}]}
        answer,_=explain("quiz",self.source(),action="quiz",generate=lambda *a,**kw:(json.dumps(raw),{}))
        self.assertEqual(len(answer["quiz"]),1)
        self.assertEqual(answer["check_in"],"")

    def test_extra_model_figures_are_capped_without_losing_answer(self):
        raw={"title":"A valid answer","introduction":"Explanation","sections":[],"takeaway":"Conclusion",
             "figure_source_ids":["S1","S2","S3","S4"],"followups":["One?","Two?","Three?","Four?"]}
        sources=[{"id":"S"+str(i),"text":"Evidence", "image_paths":["placeholder.jpg"]} for i in range(1,5)]
        answer,_=explain("question",sources,generate=lambda *a,**kw:(json.dumps(raw),{}))
        self.assertEqual(answer["title"],"A valid answer")
        self.assertEqual(len(answer["figure_source_ids"]),3)
        self.assertEqual(len(answer["followups"]),3)

    def source(self):
        return [{"id":"S1","text":"Evidence about attention scaling.","image_paths":[]}]

    def test_no_evidence_does_not_generate(self):
        def fail(*args,**kwargs):
            self.fail("Should not call provider")
        answer,_=explain("question",[],generate=fail)
        self.assertTrue(answer["insufficient_evidence"])

    def test_unknown_citations_and_unavailable_images_are_removed(self):
        raw={"title":"Clear explanation","introduction":"Intuition","sections":[{"heading":"Why", "body":"Reason", "source_ids":["S1","S999"]}],"takeaway":"Summary","figure_source_ids":["S1","S999"],"followups":[]}
        answer,_=explain("question",self.source(),generate=lambda *a,**kw:(json.dumps(raw),{}))
        self.assertEqual(answer["sections"][0]["source_ids"],["S1"])
        self.assertEqual(answer["figure_source_ids"],[])

    def test_bad_model_output_is_not_rendered(self):
        with self.assertRaises(ValueError):
            explain("question",self.source(),generate=lambda *a,**kw:("<script>malicious()</script>",{}))


if __name__=="__main__":
    unittest.main()
