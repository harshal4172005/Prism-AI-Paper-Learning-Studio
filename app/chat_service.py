"""Durable conversations and bounded background generation."""
import json
import os
import threading
import time
import uuid
from app import library, usage
from app.accounts import owned_document
from app.rag.evidence import prepare_sources
from app.rag.teacher import explain

GENERATION_SLOTS = threading.BoundedSemaphore(2)


def public_source(source):
    document_id=source["document_id"]
    return {key:source[key] for key in ("id","document_id","document","page","text","score","kind")} | {
        "image_urls": [f"/api/documents/{document_id}/pages/{source['page']}.jpg"] if source.get("image_paths") else []}


def chat_payload(chat):
    result=dict(chat)
    result["document_ids"]=json.loads(result["document_ids"])
    result.pop("user_id",None)
    return result


def message_payload(message):
    result=dict(message)
    result["payload"]=json.loads(result["payload"]) if result["payload"] else None
    result.pop("request_id",None)
    return result


def complete_message(message_id,user_id,document_ids,level,action):
    with library.connect() as db:
        message=db.execute("SELECT * FROM messages WHERE id=?",(message_id,)).fetchone()
        if not message:
            return
        chat_id=message["chat_id"]
        previous=db.execute("SELECT question,payload FROM messages WHERE chat_id=? AND state='ready' ORDER BY rowid DESC LIMIT 8",(chat_id,)).fetchall()
    acquired=GENERATION_SLOTS.acquire(timeout=60)
    try:
        if not acquired:
            raise RuntimeError("The AI is busy. Please retry shortly.")
        history=[]
        for row in reversed(previous):
            answer=json.loads(row["payload"])["answer"]
            history.append({"question":row["question"],"answer":json.dumps(answer,ensure_ascii=False)[:2200]})
        query=message["question"]
        if history:
            query += " " + history[-1]["question"] + " " + history[-1]["answer"][:450]
        chunks=[]
        selected=[]
        per_document=max(2,10//len(document_ids))
        for document_id in document_ids:
            document=owned_document(user_id,document_id)
            selected.append({"id":document_id,"title":document["title"]})
            matches=library.retrieve(document_id,query,limit=per_document)
            if len(document_ids)>1:
                opening=library.retrieve(document_id,"main idea overview",limit=1)
                combined=opening+matches
                seen=set()
                matches=[]
                for chunk in combined:
                    if chunk["text"] not in seen:
                        seen.add(chunk["text"])
                        matches.append(chunk)
                matches=matches[:per_document]
            for chunk in matches:
                chunk["source_file"]=document["title"]
            chunks.extend(matches)
        sources=prepare_sources(chunks[:12])
        started=time.monotonic()
        usage_context=usage.generation_owner.set((user_id,chat_id))
        try:
            answer,trace=explain(message["question"],sources,level,history,action=action,documents=selected)
        finally:
            usage.generation_owner.reset(usage_context)
        result={"answer":answer,"sources":[public_source(source) for source in sources],"documents":selected,
            "document_ids":document_ids,"trace":trace,"elapsed_seconds":round(time.monotonic()-started,2),"action":action}
        with library.connect() as db:
            db.execute("UPDATE messages SET payload=?,state='ready' WHERE id=?",(json.dumps(result,ensure_ascii=False),message_id))
            title=db.execute("SELECT title FROM chats WHERE id=?",(chat_id,)).fetchone()
            if title and title["title"]=="New conversation":
                db.execute("UPDATE chats SET title=? WHERE id=?",(message["question"][:65],chat_id))
    except Exception as exc:
        # User-facing messages never include provider response bodies or credentials.
        error=str(exc) if isinstance(exc,ValueError) else "The AI could not complete this reply. Please retry; your conversation is saved."
        with library.connect() as db:
            db.execute("UPDATE messages SET state='failed',error=? WHERE id=?",(error,message_id))
    finally:
        if acquired:
            GENERATION_SLOTS.release()
        with library.connect() as db:
            db.execute("UPDATE chats SET busy_until=0,updated_at=CURRENT_TIMESTAMP WHERE id=?",(chat_id,))
