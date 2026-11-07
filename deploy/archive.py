"""Shared release format: bounded, deterministic, credential-free source bundles."""
import hashlib
import io
import json
import re
import tarfile
from pathlib import PurePosixPath

MAX_COMPRESSED=8*1024*1024
MAX_EXPANDED=20*1024*1024
MAX_FILES=512
SHA=re.compile(r"[0-9a-f]{40}")
EXTENSIONS={".py",".js",".css",".html",".md",".txt",".lock",".sh",".service",".conf",".svg",".png",".jpg",".jpeg",".webp",".ico"}


def allowed(name):
    path=PurePosixPath(name)
    if not re.fullmatch(r"[A-Za-z0-9_./-]+",name):
        return False
    if path.is_absolute() or ".." in path.parts or "\\" in name or str(path)!=name:
        return False
    if name in {"release.json","requirements-server.txt"}:
        return True
    return (len(path.parts)>1 and path.parts[0] in {"app","deploy"}
        and not any(part.startswith(".") or part in {"data","venv","__pycache__","node_modules"} for part in path.parts)
        and path.suffix in EXTENSIONS)


def validate(data,commit,digest):
    if not SHA.fullmatch(commit) or not re.fullmatch(r"[0-9a-f]{64}",digest):
        raise ValueError("Invalid release identifier")
    if len(data)>MAX_COMPRESSED or hashlib.sha256(data).hexdigest()!=digest:
        raise ValueError("Release size or checksum mismatch")
    files={};total=0
    with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as archive:
        for member in archive:
            if not member.isfile() or not allowed(member.name) or member.name in files:
                raise ValueError("Unsafe or duplicate archive entry")
            total+=member.size
            if total>MAX_EXPANDED or member.size<0 or len(files)>=MAX_FILES:
                raise ValueError("Expanded release exceeds budget")
            stream=archive.extractfile(member)
            files[member.name]=stream.read(member.size+1)
            if len(files[member.name])!=member.size:
                raise ValueError("Truncated archive entry")
    for required in ("app/api/main.py","deploy/requirements-server.lock","release.json"):
        if required not in files:
            raise ValueError("Incomplete release")
    if json.loads(files["release.json"]).get("commit")!=commit:
        raise ValueError("Release commit does not match deployment request")
    lock=files["deploy/requirements-server.lock"].decode()
    if not lock.strip() or any(not re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+",line) for line in lock.splitlines()):
        raise ValueError("Dependencies must be exact registry pins without URLs or options")
    return files
