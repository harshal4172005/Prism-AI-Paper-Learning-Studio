"""Fail CI if tracked source contains obvious credentials or private runtime files."""
import re
import subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[1]
files=subprocess.check_output(["git","ls-files","-z"],cwd=root).decode().split("\0")
patterns=[re.compile(r"-----BEGIN (?:OPENSSH|RSA|EC|DSA)? ?PRIVATE KEY-----"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"github_pat_[A-Za-z0-9_]{50,}")]
problems=[]
for name in filter(None,files):
    path=root/name
    if path.is_symlink():
        problems.append(name+": symlink is not allowed in this source bundle");continue
    if name!=".env.example" and (path.name.startswith(".env") or path.suffix in {".key",".pem",".sqlite",".pdf"} or name.startswith(("data/","venv/","work/"))):
        problems.append(name+": private/runtime file is tracked");continue
    if path.is_file():
        content=path.read_text(encoding="utf-8",errors="ignore")
        if any(pattern.search(content) for pattern in patterns):
            problems.append(name+": potential credential detected (value withheld)")
if problems:
    raise SystemExit("\n".join(problems))
print("Tracked-source credential and runtime-file checks passed.")
