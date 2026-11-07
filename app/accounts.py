"""Server-side accounts, private ownership and revocable cookie sessions."""
import hashlib
import hmac
import os
import re
import secrets
import time
import uuid
from fastapi import HTTPException, Request
from app import library

COOKIE = "prism_session"
SESSION_SECONDS = 7 * 86400
PASSWORD_ROUNDS = 600_000


def schema(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE,name TEXT,password TEXT,recovery TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT,expires REAL);
    CREATE TABLE IF NOT EXISTS user_documents(user_id TEXT,document_id TEXT,PRIMARY KEY(user_id,document_id));
    CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY,user_id TEXT,title TEXT,document_ids TEXT DEFAULT '[]',busy_until REAL DEFAULT 0,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,chat_id TEXT,question TEXT,payload TEXT,state TEXT,error TEXT,request_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(chat_id,request_id));
    CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY,user_id TEXT,title TEXT,content TEXT,chat_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS rate_limits(bucket TEXT PRIMARY KEY,count INTEGER,expires REAL);
    CREATE INDEX IF NOT EXISTS chat_owner ON chats(user_id,updated_at);
    CREATE INDEX IF NOT EXISTS message_chat ON messages(chat_id,created_at);
    CREATE INDEX IF NOT EXISTS session_owner ON sessions(user_id);
    """)
    columns={row[1] for row in db.execute("PRAGMA table_info(user_documents)")}
    if "uploaded_name" not in columns:
        db.execute("ALTER TABLE user_documents ADD COLUMN uploaded_name TEXT")


def password_hash(password):
    salt = secrets.token_hex(16)
    result = hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),PASSWORD_ROUNDS).hex()
    return f"pbkdf2_sha256${PASSWORD_ROUNDS}${salt}${result}"


def verify_password(password, encoded):
    try:
        _, rounds, salt, expected = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def rate_limit(bucket, maximum, seconds):
    now = time.time()
    with library.connect() as db:
        db.execute("DELETE FROM rate_limits WHERE expires<?", (now,))
        db.execute("INSERT INTO rate_limits(bucket,count,expires) VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1", (bucket,now+seconds))
        count = db.execute("SELECT count FROM rate_limits WHERE bucket=?",(bucket,)).fetchone()[0]
    if count > maximum:
        raise HTTPException(429, "Too many attempts. Please try again later.")


def public_user(row):
    return {key:row[key] for key in ("id","email","name")}


def create_user(email, name, password):
    email = email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email) or len(email)>254:
        raise HTTPException(422,"Enter a valid email address.")
    if not 10 <= len(password) <= 128:
        raise HTTPException(422,"Use a password with 10 to 128 characters.")
    recovery = secrets.token_urlsafe(24)
    user_id = uuid.uuid4().hex
    hashed = password_hash(password)
    with library.connect() as db:
        if db.execute("SELECT count(*) FROM users").fetchone()[0] >= int(os.getenv("PRISM_MAX_ACCOUNTS","100")):
            raise HTTPException(503,"This installation has reached its account limit.")
        if db.execute("SELECT 1 FROM users WHERE email=?",(email,)).fetchone():
            raise HTTPException(409,"An account with this email already exists. Sign in or use your recovery key.")
        db.execute("INSERT INTO users(id,email,name,password,recovery) VALUES(?,?,?,?,?)",(user_id,email,name.strip()[:80] or "Reader",hashed,digest(recovery)))
    return {"id":user_id,"email":email,"name":name.strip()[:80] or "Reader"}, recovery


def issue_session(user_id, response):
    token = secrets.token_urlsafe(32)
    with library.connect() as db:
        db.execute("DELETE FROM sessions WHERE expires<?",(time.time(),))
        db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash NOT IN (SELECT token_hash FROM sessions WHERE user_id=? ORDER BY expires DESC LIMIT 9)",(user_id,user_id))
        db.execute("INSERT INTO sessions VALUES(?,?,?)",(digest(token),user_id,time.time()+SESSION_SECONDS))
    response.set_cookie(COOKIE,token,max_age=SESSION_SECONDS,httponly=True,
        secure=os.getenv("PRISM_COOKIE_SECURE","0")=="1",samesite="lax",path="/")


def current_user(request: Request):
    token = request.cookies.get(COOKIE,"")
    with library.connect() as db:
        row = db.execute("SELECT u.* FROM users u JOIN sessions s ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?",(digest(token),time.time())).fetchone()
    if not row:
        raise HTTPException(401,"Please sign in to continue.")
    return public_user(row)


def owned_document(user_id, document_id):
    with library.connect() as db:
        row=db.execute("SELECT d.*,ud.uploaded_name AS private_name FROM documents d JOIN user_documents ud ON ud.document_id=d.id WHERE ud.user_id=? AND d.id=?",(user_id,document_id)).fetchone()
    if not row:
        raise HTTPException(404,"Document not found in your library.")
    return private_document(row)


def private_document(row):
    from pathlib import Path
    result=dict(row)
    name=result.pop("private_name",None)
    if name:
        if result["title"]==Path(result["name"]).stem.replace("_"," "):
            result["title"]=Path(name).stem.replace("_"," ")
        result["name"]=name
    return result


def attach_document(user_id, document_id, name="document.pdf"):
    with library.connect() as db:
        name=name.replace("\\", "/").split("/")[-1][:180] or "document.pdf"
        db.execute("INSERT INTO user_documents(user_id,document_id,uploaded_name) VALUES(?,?,?) ON CONFLICT(user_id,document_id) DO UPDATE SET uploaded_name=excluded.uploaded_name",(user_id,document_id,name))


def owned_chat(user_id, chat_id):
    with library.connect() as db:
        row = db.execute("SELECT * FROM chats WHERE id=? AND user_id=?",(chat_id,user_id)).fetchone()
    if not row:
        raise HTTPException(404,"Conversation not found.")
    return dict(row)


def reset_password(email, recovery, new_password):
    if not 10<=len(new_password)<=128:
        raise HTTPException(422,"Use a password with 10 to 128 characters.")
    with library.connect() as db:
        row=db.execute("SELECT * FROM users WHERE email=?",(email.strip().lower(),)).fetchone()
    if not row or not hmac.compare_digest(digest(recovery),row["recovery"]):
        raise HTTPException(400,"The email or recovery key is incorrect.")
    replacement=secrets.token_urlsafe(24)
    encoded=password_hash(new_password)
    with library.connect() as db:
        changed=db.execute("UPDATE users SET password=?,recovery=? WHERE id=? AND recovery=?",(encoded,digest(replacement),row["id"],digest(recovery)))
        if changed.rowcount!=1:
            raise HTTPException(400,"This recovery key has already been used. Use the replacement key.")
        db.execute("DELETE FROM sessions WHERE user_id=?",(row["id"],))
    return replacement
