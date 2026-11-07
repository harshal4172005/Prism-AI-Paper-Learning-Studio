#!/usr/bin/python3
"""Root-owned, fixed-scope Prism release receiver. Never executes release scripts as root."""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HELPERS=Path("/usr/local/lib/prism-cicd")
sys.path.insert(0,str(HELPERS if HELPERS.exists() else Path(__file__).resolve().parent))
from archive import MAX_COMPRESSED,validate

ROOT=Path("/opt/prism-learning")
DATA=Path("/var/lib/prism-learning")
SERVICE="prism-learning.service"


def command(args,**kwargs):
    subprocess.run(args,check=True,timeout=300,**kwargs)


def point(link,target):
    temporary=link.with_name(link.name+".next")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target,target_is_directory=True)
    temporary.replace(link)


def health(commit=None,seconds=35):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8176/api/health",timeout=2) as response:
                result=json.load(response)
            if result.get("status")=="ok" and (commit in (None,"bootstrap") or result.get("release")==commit):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


class Installer:
    def __init__(self,root=ROOT,data=DATA):
        self.root=Path(root);self.data=Path(data)

    def environment(self,files):
        lock=files["deploy/requirements-server.lock"]
        digest=hashlib.sha256(lock).hexdigest()
        baseline=self.root/"requirements-server.lock"
        if baseline.exists() and baseline.read_bytes().replace(b"\r\n",b"\n")==lock.replace(b"\r\n",b"\n"):
            return self.root/"venv"
        parent=self.root/"venvs";parent.mkdir(exist_ok=True)
        target=parent/digest
        marker=target/".prism-complete"
        if marker.exists():
            return target
        if target.exists():
            shutil.rmtree(target)
        target.mkdir()
        import pwd
        build_user=pwd.getpwnam("prism-build")
        os.chown(target,build_user.pw_uid,build_user.pw_gid)
        lockfile=target/"requirements.lock"
        lockfile.write_bytes(lock)
        environment={"PATH":"/usr/bin:/bin","HOME":"/var/lib/prism-build","PIP_CONFIG_FILE":"/dev/null","PYTHONDONTWRITEBYTECODE":"1"}
        try:
            command(["/usr/sbin/runuser","-u","prism-build","--","/usr/bin/python3","-m","venv",str(target)],env=environment)
            command(["/usr/sbin/runuser","-u","prism-build","--",str(target/"bin/python"),"-m","pip","install","--no-cache-dir","--disable-pip-version-check","--only-binary=:all:","-r",str(lockfile)],env=environment,stdout=subprocess.DEVNULL)
            size=sum(path.stat().st_size for path in target.rglob("*") if path.is_file() and not path.is_symlink())
            if size>256*1024*1024:
                raise ValueError("Dependency environment exceeds the 256 MB budget")
            for directory,dirs,filenames in os.walk(target,followlinks=False):
                os.chown(directory,0,0,follow_symlinks=False)
                for name in dirs+filenames:
                    os.chown(Path(directory)/name,0,0,follow_symlinks=False)
            marker.write_text(digest)
            return target
        except Exception:
            shutil.rmtree(target)
            raise

    def backup(self):
        source=self.data/"library/library.sqlite"
        if not source.exists():
            return
        folder=self.data/"deploy-backups";folder.mkdir(mode=0o700,exist_ok=True)
        temporary=folder/"predeploy.next.sqlite"
        temporary.unlink(missing_ok=True)
        with sqlite3.connect("file:"+str(source)+"?mode=ro",uri=True,timeout=15) as src:
            with sqlite3.connect(temporary) as dest:
                src.backup(dest,pages=256,sleep=0.05)
        os.chmod(temporary,0o600)
        temporary.replace(folder/"predeploy.sqlite")

    def restart(self):
        command(["/usr/bin/systemctl","restart",SERVICE])

    def check(self,commit=None):
        return health(commit)

    def deploy(self,files,commit,digest):
        if not (self.root/".prism-owned").is_file():
            raise ValueError("Prism ownership marker missing")
        releases=self.root/"releases";releases.mkdir(exist_ok=True)
        current=self.root/"current";current_venv=self.root/"current-venv"
        if not current.is_symlink() or not current_venv.is_symlink():
            raise ValueError("Prism release links have not been provisioned")
        previous=current.resolve();previous_venv=current_venv.resolve()
        if previous.parent!=releases.resolve():
            raise ValueError("Current release is outside the Prism release directory")
        target=releases/commit
        if target.exists():
            manifest=json.loads((target/"deployment.json").read_text())
            if manifest.get("digest")!=digest:
                raise ValueError("A different artifact already exists for this commit")
            if previous==target and self.check(commit):
                print("This exact Prism release is already healthy.")
                return
        else:
            stage=Path(tempfile.mkdtemp(prefix=".staging-",dir=releases))
            os.chmod(stage,0o755)
            try:
                for name,content in files.items():
                    path=stage/name;path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(content);os.chmod(path,0o644)
                (stage/"release.env").write_text("PRISM_RELEASE_SHA="+commit+"\n")
                (stage/"deployment.json").write_text(json.dumps({"commit":commit,"digest":digest}))
                stage.replace(target)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        try:
            new_venv=self.environment(files)
            self.backup()
        except Exception:
            if target!=previous:
                shutil.rmtree(target)
            raise
        try:
            point(current_venv,new_venv)
            point(current,target)
            self.restart()
            if not self.check(commit):
                raise RuntimeError("New Prism release failed its commit-specific health check")
        except Exception:
            point(current_venv,previous_venv)
            point(current,previous)
            self.restart()
            restored=self.check()
            if target!=previous:
                shutil.rmtree(target)
            raise RuntimeError("Prism code rollback completed." if restored else "Prism rollback needs operator attention.") from None
        keep={target,previous}
        for directory in releases.iterdir():
            if directory.is_dir() and not directory.is_symlink() and directory not in keep and not directory.name.startswith("."):
                shutil.rmtree(directory)
        # Keep only environments referenced by the two retained releases.
        environments={new_venv.resolve(),previous_venv.resolve()}
        parent=self.root/"venvs"
        if parent.exists():
            for directory in parent.iterdir():
                if directory.is_dir() and not directory.is_symlink() and directory.resolve() not in environments:
                    shutil.rmtree(directory)
        print("Healthy Prism release: "+commit)
        print("Previous code retained for rollback; user data and provider credentials preserved.")


def main():
    if os.geteuid()!=0 or len(sys.argv)!=3:
        sys.exit("This receiver must run through the restricted deployment entry point.")
    import fcntl
    with open("/run/lock/prism-learning-deploy.lock","a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        data=sys.stdin.buffer.read(MAX_COMPRESSED+1)
        commit,digest=sys.argv[1:]
        files=validate(data,commit,digest)
        Installer().deploy(files,commit,digest)


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        sys.exit("Prism deployment failed: "+str(exc))
