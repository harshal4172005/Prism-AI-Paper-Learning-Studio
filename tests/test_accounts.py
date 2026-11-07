import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import fitz
from fastapi.testclient import TestClient
from app import library
from app.api.main import app

ANSWER={"title":"A clear answer","introduction":"An explanation","sections":[{"heading":"Why","body":"Reason","source_ids":["S1"]}],"takeaway":"Summary","figure_source_ids":[],"followups":["Give an example?"],"quiz":[],"check_in":"Does that make sense?","insufficient_evidence":False}
TRACE={"provider":"test","model":"test","images_seen":0}


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.patches=[patch.object(library,"LIBRARY",Path(self.folder.name)/"library"),patch.object(library,"IMAGES",Path(self.folder.name)/"images")]
        for item in self.patches:item.start()
        self.one=TestClient(app);self.two=TestClient(app)
        self.signup=self.one.post("/api/auth/signup",json={"email":"one@example.com","name":"One","password":"strong-password-1"}).json()
        self.two.post("/api/auth/signup",json={"email":"two@example.com","password":"strong-password-2"})

    def tearDown(self):
        for item in self.patches:item.stop()
        self.folder.cleanup()

    def pdf_bytes(self,text):
        with fitz.open() as pdf:
            page=pdf.new_page();page.insert_text((50,50),text)
            for i in range(5):page.draw_rect(fitz.Rect(20+i*20,100,30+i*20,130))
            return pdf.tobytes()

    def upload(self,client,text="Attention scaling and softmax help explain the scores."):
        response=client.post("/api/documents?filename=paper.pdf",content=self.pdf_bytes(text))
        self.assertEqual(response.status_code,202,response.text)
        return response.json()["document"]["id"]

    def chat(self,client,ids):
        response=client.post("/api/chats",json={"document_ids":ids})
        self.assertEqual(response.status_code,201,response.text)
        return response.json()["chat"]["id"]

    def send(self,client,chat,question="Explain attention scaling",request_id="test-request-0000001"):
        return client.post(f"/api/chats/{chat}/messages",json={"question":question,"request_id":request_id})

    def test_auth_required_and_cookie_is_http_only(self):
        anonymous=TestClient(app)
        for url in ["/api/me","/api/documents","/api/chats","/api/notes"]:
            self.assertEqual(anonymous.get(url).status_code,401)
        response=anonymous.post("/api/auth/login",json={"email":"one@example.com","password":"strong-password-1"})
        self.assertIn("HttpOnly",response.headers["set-cookie"])
        self.assertNotIn("token",response.json())
        anonymous.post("/api/auth/logout")
        self.assertEqual(anonymous.get("/api/me").status_code,401)

    def test_password_recovery_rotates_key_and_revokes_sessions(self):
        response=self.two.post("/api/auth/recover",json={"email":"one@example.com","recovery_key":self.signup["recovery_key"],"password":"replacement-password"})
        self.assertEqual(response.status_code,200)
        self.assertNotEqual(response.json()["recovery_key"],self.signup["recovery_key"])
        self.assertEqual(self.one.get("/api/me").status_code,401)
        self.assertEqual(self.one.post("/api/auth/login",json={"email":"one@example.com","password":"strong-password-1"}).status_code,401)
        self.assertEqual(self.one.post("/api/auth/login",json={"email":"one@example.com","password":"replacement-password"}).status_code,200)

    def test_cross_account_files_images_chats_notes_are_denied(self):
        doc=self.upload(self.one);chat=self.chat(self.one,[doc])
        self.assertEqual(self.two.get("/api/documents").json()["documents"],[])
        for url in [f"/api/documents/{doc}/pdf",f"/api/documents/{doc}/pages/1.jpg",f"/api/chats/{chat}"]:
            self.assertEqual(self.two.get(url).status_code,404)
        self.assertEqual(self.two.post("/api/chats",json={"document_ids":[doc]}).status_code,404)
        note=self.one.post("/api/notes",json={"title":"Private","content":"My note"}).json()["id"]
        self.assertEqual(self.two.delete("/api/notes/"+note).status_code,404)
        self.assertEqual(self.two.get("/api/notes").json()["notes"],[])
        self.assertEqual(TestClient(app).get("/manual-images/example.png").status_code,404)

    def test_history_survives_new_client_and_has_real_context(self):
        doc=self.upload(self.one);chat=self.chat(self.one,[doc])
        with patch("app.chat_service.explain",return_value=(ANSWER,TRACE)) as model:
            self.assertEqual(self.send(self.one,chat).status_code,202)
            self.assertEqual(self.send(self.one,chat,"I did not understand. Can you explain differently?","test-request-0000002").status_code,202)
            self.assertEqual(len(model.call_args.args[3]),1)
        other=TestClient(app);other.post("/api/auth/login",json={"email":"one@example.com","password":"strong-password-1"})
        messages=other.get("/api/chats/"+chat).json()["messages"]
        self.assertEqual(len(messages),2)
        self.assertTrue(all(message["state"]=="ready" for message in messages))
        self.assertEqual(messages[0]["payload"]["document_ids"],[doc])
        self.assertIn("Explain attention",other.get(f"/api/chats/{chat}/export").text)

    def test_multi_paper_switching_and_idempotent_send(self):
        first=self.upload(self.one,"First study. Attention scaling improves numerical stability.")
        second=self.upload(self.one,"Second study. Attention has different memory requirements.")
        chat=self.chat(self.one,[first,second])
        with patch("app.chat_service.explain",return_value=(ANSWER,TRACE)) as model:
            self.send(self.one,chat)
            self.send(self.one,chat)
            self.assertEqual(model.call_count,1)
            self.assertEqual(len(model.call_args.kwargs["documents"]),2)
            self.one.patch("/api/chats/"+chat,json={"title":"Comparison","document_ids":[second]})
            self.send(self.one,chat,"What about its memory?","test-request-0000002")
        rows=self.one.get("/api/chats/"+chat).json()["messages"]
        self.assertEqual(rows[0]["payload"]["document_ids"],[first,second])
        self.assertEqual(rows[1]["payload"]["document_ids"],[second])

    def test_shared_file_deduplication_and_last_owner_cleanup(self):
        data=self.pdf_bytes("Attention scaling test.")
        first=self.one.post("/api/documents?filename=private-name.pdf",content=data).json()["document"]["id"]
        second=self.two.post("/api/documents?filename=own-name.pdf",content=data).json()["document"]["id"]
        self.assertEqual(first,second)
        self.assertEqual(self.two.get("/api/documents").json()["documents"][0]["name"],"own-name.pdf")
        self.one.delete("/api/documents/"+first)
        self.assertTrue((library.LIBRARY/(first+".pdf")).exists())
        self.assertEqual(self.two.get(f"/api/documents/{second}/pdf").status_code,200)
        self.two.delete("/api/documents/"+second)
        self.assertFalse((library.LIBRARY/(first+".pdf")).exists())

    def test_bad_origin_and_account_deletion(self):
        self.assertEqual(self.one.post("/api/chats",json={},headers={"Origin":"https://attacker.example"}).status_code,403)
        doc=self.upload(self.one)
        self.assertEqual(self.one.request("DELETE","/api/account",json={"password":"wrong"}).status_code,403)
        self.assertEqual(self.one.request("DELETE","/api/account",json={"password":"strong-password-1"}).status_code,200)
        self.assertEqual(self.one.get("/api/me").status_code,401)
        self.assertFalse((library.LIBRARY/(doc+".pdf")).exists())

    def test_generation_failure_is_saved_without_secret(self):
        doc=self.upload(self.one);chat=self.chat(self.one,[doc])
        with patch("app.chat_service.explain",side_effect=RuntimeError("API-SECRET")):
            self.send(self.one,chat)
        response=self.one.get("/api/chats/"+chat)
        self.assertEqual(response.json()["messages"][0]["state"],"failed")
        self.assertNotIn("API-SECRET",response.text)

    def test_quota_and_note_export(self):
        self.upload(self.one)
        with patch.dict("os.environ",{"PRISM_MAX_DOCUMENTS":"1"}):
            self.assertEqual(self.one.post("/api/documents",content=self.pdf_bytes("Other text")).status_code,413)
        note=self.one.post("/api/notes",json={"title":"My finding","content":"My content"}).json()["id"]
        self.one.patch("/api/notes/"+note,json={"title":"Updated finding","content":"Edited content"})
        self.assertIn("Edited content",self.one.get("/api/notes/export").text)

if __name__=="__main__":unittest.main()
