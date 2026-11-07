"""Create a deterministic release; excludes credentials, databases and PDFs."""
import argparse
import gzip
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from archive import allowed,validate


def build(output,commit,root=None):
    root=Path(root or Path(__file__).resolve().parents[1])
    entries={"release.json":json.dumps({"commit":commit},sort_keys=True).encode()}
    for folder in ("app","deploy"):
        for path in sorted((root/folder).rglob("*")):
            name=path.relative_to(root).as_posix()
            if path.is_file() and not path.is_symlink() and allowed(name):
                entries[name]=path.read_bytes()
    entries["requirements-server.txt"]=(root/"requirements-server.txt").read_bytes()
    with open(output,"wb") as destination:
        with gzip.GzipFile(filename="",mode="wb",fileobj=destination,mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode="w") as archive:
                for name,data in sorted(entries.items()):
                    info=tarfile.TarInfo(name);info.size=len(data);info.mtime=0;info.mode=0o644
                    archive.addfile(info,io.BytesIO(data))
    data=Path(output).read_bytes();digest=hashlib.sha256(data).hexdigest()
    validate(data,commit,digest)
    return digest


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("output");parser.add_argument("--commit",required=True)
    args=parser.parse_args()
    print(build(args.output,args.commit))
