"""Private, provider-reported AI usage. One Vibe Point equals one token."""
import os
import time
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from app import library

generation_owner = ContextVar("generation_owner", default=None)


def record(provider, model, metadata):
    owner = generation_owner.get()
    if not owner or not metadata:
        return
    if provider == "gemini":
        incoming = int(metadata.get("promptTokenCount", 0))
        outgoing = int(metadata.get("candidatesTokenCount", 0)) + int(metadata.get("thoughtsTokenCount", 0))
        total = int(metadata.get("totalTokenCount", incoming + outgoing))
        cached = int(metadata.get("cachedContentTokenCount", 0))
    else:
        incoming = int(metadata.get("prompt_tokens", 0))
        outgoing = int(metadata.get("completion_tokens", 0))
        total = int(metadata.get("total_tokens", incoming + outgoing))
        cached = 0
    # Standard paid-tier equivalent, not the operator's invoice or a user charge.
    # Gemini Developer API pricing, checked 2026-11-07; unknown models stay unpriced.
    cost = None
    if (provider == "gemini" and model == "gemini-2.5-flash"
            and datetime.now(timezone.utc) < datetime(2026,12,1,tzinfo=timezone.utc)):
        cost = (max(0, incoming-cached)*0.30 + cached*0.03 + outgoing*2.50)/1_000_000
    with library.connect() as db:
        db.execute("INSERT INTO ai_usage(user_id,chat_id,input_points,output_points,total_points,estimated_usd,provider,model) VALUES(?,?,?,?,?,?,?,?)",
                   (*owner, incoming, outgoing, total, cost, provider, model))


def totals(db, user_id, chat_id=None, provider=None):
    clause = "user_id=?" + (" AND chat_id=?" if chat_id else "")
    args = (user_id, chat_id) if chat_id else (user_id,)
    if provider:
        clause += " AND provider=?"
        args += (provider,)
    row = db.execute("SELECT count(*) AS calls,coalesce(sum(input_points),0) AS input_points,coalesce(sum(output_points),0) AS output_points,coalesce(sum(total_points),0) AS vibe_points,coalesce(sum(estimated_usd),0) AS estimated_usd,sum(CASE WHEN estimated_usd IS NULL THEN 1 ELSE 0 END) AS unpriced_calls FROM ai_usage WHERE "+clause,args).fetchone()
    return dict(row)


def snapshot(user_id, chat_id=None):
    now = datetime.now(timezone.utc)
    reset = (now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
    limit = int(os.getenv("PRISM_DAILY_QUESTIONS","40"))
    with library.connect() as db:
        row = db.execute("SELECT count FROM rate_limits WHERE bucket=? AND expires>?",
                         ("questions-user:"+user_id+":"+now.strftime("%Y-%m-%d"),time.time())).fetchone()
        used = min(limit,row[0] if row else 0)
        result = {"questions":{"used":used,"limit":limit,"remaining":max(0,limit-used),"reset_at":reset.isoformat()},
                  "ai":totals(db,user_id)}
        from app import config
        settings=[("gemini","Gemini","Primary",", ".join(config.GENERATION_MODELS),config.GEMINI_API_KEY),
                  ("groq","Groq","Backup 1",config.GROQ_MODEL,config.GROQ_API_KEY),
                  ("nvidia","NVIDIA","Backup 2",config.NVIDIA_MODEL,config.NVIDIA_API_KEY)]
        result["provider_usage"]=[]
        for name,label,role,model,key in settings:
            item={"provider":name,"label":label,"role":role,"model":model,"configured":bool(key),"ai":totals(db,user_id,provider=name)}
            if chat_id:
                item["chat_ai"]=totals(db,user_id,chat_id,provider=name)
            result["provider_usage"].append(item)
        if chat_id:
            result["chat_ai"] = totals(db,user_id,chat_id)
    return result
