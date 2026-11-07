"""Private, resource-bounded paper learning service."""
import json
import hashlib
import os
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, Response, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal
from app import accounts, library, sample_paper, usage
from app.chat_service import chat_payload, message_payload, complete_message

ROOT=library.ROOT


@asynccontextmanager
async def lifespan(app):
    with library.connect() as db:
        db.execute("UPDATE documents SET status='failed',error='Preparation interrupted. Please upload this PDF again.' WHERE status='processing'")
        db.execute("UPDATE messages SET state='failed',error='The server restarted before this reply finished. Please retry.' WHERE state='pending'")
        db.execute("UPDATE chats SET busy_until=0")
    yield


app=FastAPI(title="Prism Paper Learning Studio",version="1.0.0",lifespan=lifespan)
user_dependency=Depends(accounts.current_user)


@app.middleware("http")
async def security_headers(request,call_next):
    if request.method in ("POST","PATCH","PUT","DELETE"):
        origin=request.headers.get("origin")
        allowed=os.getenv("PRISM_PUBLIC_ORIGIN","")
        if origin and not ((allowed and origin.rstrip("/")==allowed.rstrip("/")) or
            (not allowed and urlsplit(origin).netloc==request.headers.get("host"))):
            return PlainTextResponse("Request origin is not allowed.",status_code=403)
    response=await call_next(request)
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="same-origin"
    response.headers["X-Frame-Options"]="SAMEORIGIN"
    response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' blob: data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"]="no-store"
    return response


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1,max_length=128)
    name: str = Field(default="Reader",max_length=80)


class Recovery(BaseModel):
    email: str = Field(max_length=254)
    recovery_key: str = Field(max_length=150)
    password: str = Field(min_length=10,max_length=128)


def auth_limit(request,email):
    ip=request.client.host if request.client else "unknown"
    accounts.rate_limit("auth-ip:"+ip,40,900)
    accounts.rate_limit("auth-email:"+accounts.digest(email.strip().lower()),12,900)


@app.post("/api/auth/signup",status_code=201)
def signup(body: Credentials,request: Request,response: Response):
    auth_limit(request,body.email)
    user,recovery=accounts.create_user(body.email,body.name,body.password)
    accounts.issue_session(user["id"],response)
    return {"user":user,"recovery_key":recovery}


@app.post("/api/auth/login")
def login(body: Credentials,request: Request,response: Response):
    auth_limit(request,body.email)
    with library.connect() as db:
        row=db.execute("SELECT * FROM users WHERE email=?",(body.email.strip().lower(),)).fetchone()
    if row is None:
        # Match the expensive password work without allocating an account.
        accounts.verify_password(body.password, "pbkdf2_sha256$600000$"+"00"*16+"$"+"00"*32)
        raise HTTPException(401,"Email or password is incorrect.")
    if not accounts.verify_password(body.password,row["password"]):
        raise HTTPException(401,"Email or password is incorrect.")
    accounts.issue_session(row["id"],response)
    return {"user":accounts.public_user(row)}


@app.post("/api/auth/recover")
def recover(body: Recovery,request: Request):
    auth_limit(request,body.email)
    return {"recovery_key":accounts.reset_password(body.email,body.recovery_key,body.password)}


@app.post("/api/auth/logout")
def logout(request: Request,response: Response):
    with library.connect() as db:
        db.execute("DELETE FROM sessions WHERE token_hash=?",(accounts.digest(request.cookies.get(accounts.COOKIE,"")),))
    response.delete_cookie(accounts.COOKIE,path="/")
    return {"ok":True}


@app.get("/api/me")
def me(user=user_dependency):
    owned=documents(user)["documents"]
    size=sum((library.LIBRARY/(row["id"]+".pdf")).stat().st_size for row in owned if (library.LIBRARY/(row["id"]+".pdf")).exists())
    return {"user":user,"usage":{"documents":len(owned),"pdf_mb":round(size/(1024*1024),2),"pdf_bytes":size,**usage.snapshot(user["id"])},"limits":{"upload_mb":library.MAX_BYTES//(1024*1024),"documents":int(os.getenv("PRISM_MAX_DOCUMENTS","12")),"storage_mb":int(os.getenv("PRISM_USER_STORAGE_MB","75")),"daily_questions":int(os.getenv("PRISM_DAILY_QUESTIONS","40"))}}


@app.get("/api/usage")
def get_usage(chat_id: str | None=None,user=user_dependency):
    if chat_id:
        accounts.owned_chat(user["id"],chat_id)
    return usage.snapshot(user["id"],chat_id)


@app.get("/api/health")
def health():
    return {"status":"ok","version":"1.0.0","release":os.getenv("PRISM_RELEASE_SHA","development")}


@app.get("/api/documents")
def documents(user=user_dependency):
    with library.connect() as db:
        rows=db.execute("SELECT d.*,ud.uploaded_name AS private_name FROM documents d JOIN user_documents ud ON ud.document_id=d.id WHERE ud.user_id=? ORDER BY created_at DESC",(user["id"],)).fetchall()
    return {"documents":[accounts.private_document(row) for row in rows]}


@app.post("/api/documents",status_code=202)
async def upload(request: Request,background: BackgroundTasks,filename: str="document.pdf",user=user_dependency):
    data=bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data)>library.MAX_BYTES:
            raise HTTPException(413,"This PDF exceeds the upload limit.")
    return register_document(bytes(data),filename,user,background)


def register_document(data,filename,user,background):
    with library.LOCK:
        existing=documents(user)["documents"]
        candidate=hashlib.sha256(data).hexdigest()[:24]
        already_owned=any(row["id"]==candidate for row in existing)
        if not already_owned and len(existing)>=int(os.getenv("PRISM_MAX_DOCUMENTS","12")):
            raise HTTPException(413,"Your library is full. Remove a PDF before adding another.")
        owned_size=sum((library.LIBRARY/(row["id"]+".pdf")).stat().st_size for row in existing if (library.LIBRARY/(row["id"]+".pdf")).exists())
        if owned_size+(0 if already_owned else len(data))>int(os.getenv("PRISM_USER_STORAGE_MB","75"))*1024*1024:
            raise HTTPException(413,"Your PDF storage allowance is full. Remove a PDF to make room.")
        global_size=sum(item.stat().st_size for folder in (library.LIBRARY,library.IMAGES) if folder.exists() for item in folder.iterdir() if item.is_file())
        extra_bytes=0 if (library.LIBRARY/(candidate+".pdf")).exists() else len(data)
        if global_size+extra_bytes>int(os.getenv("PRISM_TOTAL_STORAGE_MB","512"))*1024*1024:
            raise HTTPException(507,"This installation has reached its storage budget.")
        try:
            document_id,process=library.register_pdf(bytes(data),filename)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from None
        accounts.attach_document(user["id"],document_id,filename)
    if process:
        background.add_task(library.process_pdf,document_id)
    return {"document":accounts.owned_document(user["id"],document_id)}


@app.post("/api/documents/sample",status_code=202)
def use_sample(background: BackgroundTasks,user=user_dependency):
    try:
        with sample_paper.path().open("rb") as file:
            data=file.read(library.MAX_BYTES+1)
    except OSError:
        raise HTTPException(503,"The sample paper is temporarily unavailable. You can still upload your own PDF.") from None
    return register_document(data,sample_paper.FILENAME,user,background)



@app.get("/api/documents/{document_id}/pdf")
def pdf(document_id: str,user=user_dependency):
    row=accounts.owned_document(user["id"],document_id)
    return FileResponse(library.LIBRARY/(row["id"]+".pdf"),media_type="application/pdf",filename=row["name"],content_disposition_type="inline")


@app.get("/api/documents/{document_id}/pages/{page}.jpg")
def page_image(document_id: str,page: int,user=user_dependency):
    row=accounts.owned_document(user["id"],document_id)
    if page<1 or page>row["pages"]:
        raise HTTPException(404,"Page not found")
    return FileResponse(library.preview(document_id,page),media_type="image/jpeg")


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str,user=user_dependency):
    row=accounts.owned_document(user["id"],document_id)
    if row["status"]=="processing":
        raise HTTPException(409,"Wait for PDF processing to finish before removing it.")
    with library.LOCK,library.connect() as db:
        chats=db.execute("SELECT * FROM chats WHERE user_id=?",(user["id"],)).fetchall()
        if any(document_id in json.loads(chat["document_ids"]) and chat["busy_until"]>time.time() for chat in chats):
            raise HTTPException(409,"Wait for the current reply to finish before removing this PDF.")
        db.execute("DELETE FROM user_documents WHERE user_id=? AND document_id=?",(user["id"],document_id))
        for chat in chats:
            db.execute("UPDATE chats SET document_ids=? WHERE id=?",(json.dumps([value for value in json.loads(chat["document_ids"]) if value!=document_id]),chat["id"]))
    library.delete_unreferenced(document_id)
    return {"ok":True}


class ChatInput(BaseModel):
    title: str = Field(default="New conversation",min_length=1,max_length=120)
    document_ids: list[str] = Field(default_factory=list,max_length=5)


def validate_documents(user_id,ids):
    for document_id in ids:
        document=accounts.owned_document(user_id,document_id)
        if document["status"]!="ready":
            raise HTTPException(409,"Wait until every selected PDF is ready.")
    return list(dict.fromkeys(ids))


@app.get("/api/chats")
def chats(q: str="",user=user_dependency):
    q=q[:150]
    with library.connect() as db:
        rows=db.execute("SELECT DISTINCT c.* FROM chats c LEFT JOIN messages m ON c.id=m.chat_id WHERE c.user_id=? AND (c.title LIKE ? OR m.question LIKE ?) ORDER BY c.updated_at DESC LIMIT 200",(user["id"],"%"+q+"%","%"+q+"%")).fetchall()
    return {"chats":[chat_payload(row) for row in rows]}


@app.post("/api/chats",status_code=201)
def create_chat(body: ChatInput,user=user_dependency):
    ids=validate_documents(user["id"],body.document_ids)
    chat_id=uuid.uuid4().hex
    with library.connect() as db:
        if db.execute("SELECT count(*) FROM chats WHERE user_id=?",(user["id"],)).fetchone()[0]>=100:
            raise HTTPException(413,"You have 100 conversations. Delete an older chat to make room.")
        db.execute("INSERT INTO chats(id,user_id,title,document_ids) VALUES(?,?,?,?)",(chat_id,user["id"],body.title.strip() or "New conversation",json.dumps(ids)))
    return {"chat":chat_payload(accounts.owned_chat(user["id"],chat_id))}


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str,user=user_dependency):
    chat=accounts.owned_chat(user["id"],chat_id)
    with library.connect() as db:
        rows=db.execute("SELECT * FROM messages WHERE chat_id=? ORDER BY rowid",(chat_id,)).fetchall()
    return {"chat":chat_payload(chat),"messages":[message_payload(row) for row in rows]}


@app.patch("/api/chats/{chat_id}")
def change_chat(chat_id: str,body: ChatInput,user=user_dependency):
    chat=accounts.owned_chat(user["id"],chat_id)
    if chat["busy_until"]>time.time():
        raise HTTPException(409,"Wait for this reply to finish before changing the chat.")
    ids=validate_documents(user["id"],body.document_ids)
    with library.connect() as db:
        db.execute("UPDATE chats SET title=?,document_ids=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(body.title.strip() or "New conversation",json.dumps(ids),chat_id))
    return {"chat":chat_payload(accounts.owned_chat(user["id"],chat_id))}


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str,user=user_dependency):
    chat=accounts.owned_chat(user["id"],chat_id)
    if chat["busy_until"]>time.time():
        raise HTTPException(409,"Wait for this reply to finish before deleting the chat.")
    with library.connect() as db:
        db.execute("DELETE FROM messages WHERE chat_id=?",(chat_id,))
        db.execute("DELETE FROM chats WHERE id=?",(chat_id,))
    return {"ok":True}


class MessageInput(BaseModel):
    question: str = Field(min_length=3,max_length=3000)
    request_id: str = Field(min_length=16,max_length=80)
    level: Literal["simple","technical"] = "simple"
    action: Literal["ask","simpler","example","math","diagram","quiz"] = "ask"


@app.post("/api/chats/{chat_id}/messages",status_code=202)
def send_message(chat_id: str,body: MessageInput,background: BackgroundTasks,user=user_dependency):
    chat=accounts.owned_chat(user["id"],chat_id)
    if not body.question.strip():
        raise HTTPException(422,"Please type a question.")
    if library.storage_bytes()+256000>int(os.getenv("PRISM_TOTAL_STORAGE_MB","512"))*1024*1024:
        raise HTTPException(507,"This installation has reached its storage budget. Remove old PDFs or chats before continuing.")
    ids=validate_documents(user["id"],json.loads(chat["document_ids"]))
    if not ids:
        raise HTTPException(422,"Select at least one PDF for this conversation.")
    with library.connect() as db:
        duplicate=db.execute("SELECT * FROM messages WHERE chat_id=? AND request_id=?",(chat_id,body.request_id)).fetchone()
    if duplicate:
        return {"message":message_payload(duplicate)}
    accounts.rate_limit("questions-user:"+user["id"]+":"+time.strftime("%Y-%m-%d",time.gmtime()),int(os.getenv("PRISM_DAILY_QUESTIONS","40")),86400)
    accounts.rate_limit("questions-global:"+time.strftime("%Y-%m-%d",time.gmtime()),int(os.getenv("PRISM_GLOBAL_DAILY_QUESTIONS","300")),86400)
    message_id=uuid.uuid4().hex
    with library.connect() as db:
        if db.execute("SELECT count(*) FROM messages m JOIN chats c ON c.id=m.chat_id WHERE c.user_id=?",(user["id"],)).fetchone()[0]>=500:
            raise HTTPException(413,"Your saved message allowance is full. Delete an older conversation to make room.")
        cursor=db.execute("UPDATE chats SET busy_until=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND busy_until<?",(time.time()+180,chat_id,time.time()))
        if cursor.rowcount!=1:
            raise HTTPException(409,"A reply is already being prepared in this chat.")
        db.execute("INSERT INTO messages(id,chat_id,question,state,request_id) VALUES(?,?,?,'pending',?)",(message_id,chat_id,body.question.strip(),body.request_id))
    background.add_task(complete_message,message_id,user["id"],ids,body.level,body.action)
    return {"message":{"id":message_id,"chat_id":chat_id,"question":body.question,"state":"pending","payload":None,"error":None}}


@app.get("/api/chats/{chat_id}/export")
def export_chat(chat_id: str,user=user_dependency):
    data=get_chat(chat_id,user)
    lines=["# "+data["chat"]["title"],""]
    for message in data["messages"]:
        lines += ["## You",message["question"],""]
        if message["payload"]:
            answer=message["payload"]["answer"]
            lines += ["## Prism",answer["introduction"],""]
            for section in answer["sections"]:
                lines += ["### "+section["heading"],section["body"],""]
            lines += ["**Takeaway:** "+answer["takeaway"],""]
            for source in message["payload"]["sources"]:
                lines += ["- Source: "+source["document"]+", page "+str(source["page"])]
    return PlainTextResponse("\n".join(lines),headers={"Content-Disposition":"attachment; filename=prism-conversation.md"})


class NoteInput(BaseModel):
    title: str = Field(min_length=1,max_length=120)
    content: str = Field(min_length=1,max_length=15000)
    chat_id: str | None = None


@app.get("/api/notes")
def notes(user=user_dependency):
    with library.connect() as db:
        rows=db.execute("SELECT * FROM notes WHERE user_id=? ORDER BY created_at DESC",(user["id"],)).fetchall()
    return {"notes":[{key:row[key] for key in ("id","title","content","chat_id","created_at")} for row in rows]}


@app.post("/api/notes",status_code=201)
def add_note(body: NoteInput,user=user_dependency):
    if library.storage_bytes()+32000>int(os.getenv("PRISM_TOTAL_STORAGE_MB","512"))*1024*1024:
        raise HTTPException(507,"This installation has reached its storage budget.")
    if body.chat_id:
        accounts.owned_chat(user["id"],body.chat_id)
    note_id=uuid.uuid4().hex
    with library.connect() as db:
        if db.execute("SELECT count(*) FROM notes WHERE user_id=?",(user["id"],)).fetchone()[0]>=100:
            raise HTTPException(413,"Your notebook has 100 entries. Remove an older note to make room.")
        db.execute("INSERT INTO notes(id,user_id,title,content,chat_id) VALUES(?,?,?,?,?)",(note_id,user["id"],body.title,body.content,body.chat_id))
    return {"id":note_id}


@app.patch("/api/notes/{note_id}")
def edit_note(note_id: str,body: NoteInput,user=user_dependency):
    with library.connect() as db:
        result=db.execute("UPDATE notes SET title=?,content=? WHERE id=? AND user_id=?",(body.title,body.content,note_id,user["id"]))
        if result.rowcount!=1:
            raise HTTPException(404,"Note not found")
    return {"ok":True}


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str,user=user_dependency):
    with library.connect() as db:
        result=db.execute("DELETE FROM notes WHERE id=? AND user_id=?",(note_id,user["id"]))
        if result.rowcount!=1:
            raise HTTPException(404,"Note not found")
    return {"ok":True}


@app.get("/api/notes/export")
def export_notes(user=user_dependency):
    lines=["# My Prism Notebook",""]
    for note in notes(user)["notes"]:
        lines += ["## "+note["title"],note["content"],""]
    return PlainTextResponse("\n".join(lines),headers={"Content-Disposition":"attachment; filename=prism-notebook.md"})


@app.get("/api/account/export")
def export_account(user=user_dependency):
    data={"user":user,"documents":documents(user)["documents"],"notes":notes(user)["notes"],
        "conversations":[get_chat(chat["id"],user) for chat in chats("",user)["chats"]]}
    return Response(json.dumps(data,ensure_ascii=False),media_type="application/json",headers={"Content-Disposition":"attachment; filename=prism-account.json"})


class DeleteAccount(BaseModel):
    password: str = Field(max_length=128)


@app.delete("/api/account")
def delete_account(body: DeleteAccount,response: Response,user=user_dependency):
    with library.connect() as db:
        row=db.execute("SELECT password FROM users WHERE id=?",(user["id"],)).fetchone()
    if not row or not accounts.verify_password(body.password,row["password"]):
        raise HTTPException(403,"Password is incorrect.")
    docs=documents(user)["documents"]
    if any(row["status"]=="processing" for row in docs):
        raise HTTPException(409,"Wait for your PDF uploads to finish first.")
    with library.LOCK,library.connect() as db:
        if db.execute("SELECT 1 FROM chats WHERE user_id=? AND busy_until>?",(user["id"],time.time())).fetchone():
            raise HTTPException(409,"Wait for your current replies to finish first.")
        db.execute("DELETE FROM messages WHERE chat_id IN (SELECT id FROM chats WHERE user_id=?)",(user["id"],))
        for table in ("chats","notes","sessions","user_documents","ai_usage"):
            db.execute("DELETE FROM "+table+" WHERE user_id=?",(user["id"],))
        db.execute("DELETE FROM users WHERE id=?",(user["id"],))
    for row in docs:
        library.delete_unreferenced(row["id"])
    response.delete_cookie(accounts.COOKIE,path="/")
    return {"ok":True}


app.mount("/",StaticFiles(directory=ROOT/"app"/"frontend",html=True),name="frontend")
