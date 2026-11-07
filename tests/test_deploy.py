import gzip
import hashlib
import importlib.util
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

DEPLOY=Path(__file__).resolve().parents[1]/"deploy"
sys.path.insert(0,str(DEPLOY))
from archive import allowed,validate
from package import build
from receiver import Installer

COMMIT="a"*40


def bundle(extra=None,commit=COMMIT):
    entries={"app/api/main.py":b"app=None\n","deploy/requirements-server.lock":b"fastapi==0.162.0\n",
        "release.json":json.dumps({"commit":commit}).encode()}
    entries.update(extra or {})
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode="w:gz") as archive:
        for name,data in entries.items():
            member=tarfile.TarInfo(name);member.size=len(data);archive.addfile(member,io.BytesIO(data))
    data=output.getvalue()
    return data,hashlib.sha256(data).hexdigest()


class ReleaseValidationTests(unittest.TestCase):
    def test_valid_source_bundle(self):
        data,digest=bundle()
        self.assertIn("app/api/main.py",validate(data,COMMIT,digest))

    def test_rejects_traversal_credentials_and_data(self):
        for path in ["../app.py","/etc/passwd","app/../../escape.py","app/.env","deploy/key.pem","app/data/user.txt","app/link\\escape.py"]:
            data,digest=bundle({path:b"invalid"})
            with self.subTest(path=path),self.assertRaises(ValueError):
                validate(data,COMMIT,digest)

    def test_rejects_symbolic_links(self):
        output=io.BytesIO()
        with tarfile.open(fileobj=output,mode="w:gz") as archive:
            info=tarfile.TarInfo("app/link.py");info.type=tarfile.SYMTYPE;info.linkname="/etc/passwd";archive.addfile(info)
        data=output.getvalue()
        with self.assertRaises(ValueError):validate(data,COMMIT,hashlib.sha256(data).hexdigest())

    def test_rejects_changed_digest_or_commit(self):
        data,digest=bundle()
        for commit,checksum in [(COMMIT,"0"*64),("b"*40,digest)]:
            with self.assertRaises(ValueError):validate(data,commit,checksum)

    def test_rejects_dependency_urls_and_install_options(self):
        for value in [b"--index-url https://example.test\n",b"package @ https://example.test/code.whl\n"]:
            data,digest=bundle({"deploy/requirements-server.lock":value})
            with self.assertRaises(ValueError):validate(data,COMMIT,digest)

    def test_rejects_expansion_over_budget(self):
        data,digest=bundle({"app/big.py":b"x"*1024})
        with patch("archive.MAX_EXPANDED",100),self.assertRaises(ValueError):validate(data,COMMIT,digest)

    def test_package_is_deterministic_and_excludes_private_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"app/api").mkdir(parents=True);(root/"deploy").mkdir()
            (root/"app/api/main.py").write_text("app=None")
            (root/"deploy/requirements-server.lock").write_text("fastapi==0.162.0\n")
            (root/"requirements-server.txt").write_text("fastapi==0.162.0\n")
            (root/"app/.env").write_text("private")
            (root/"app/private.key").write_text("private")
            first=build(root/"one.tgz",COMMIT,root)
            second=build(root/"two.tgz",COMMIT,root)
            self.assertEqual(first,second)
            files=validate((root/"one.tgz").read_bytes(),COMMIT,first)
            self.assertNotIn("app/.env",files)
            self.assertNotIn("app/private.key",files)


@unittest.skipUnless(os.name=="posix","Deployment symlinks are exercised by Linux CI")
class ReleaseSwitchTests(unittest.TestCase):
    def prepare(self,root):
        (root/".prism-owned").touch()
        baseline=root/"releases/bootstrap";baseline.mkdir(parents=True)
        venv=root/"venv";venv.mkdir()
        (root/"current").symlink_to(baseline,target_is_directory=True)
        (root/"current-venv").symlink_to(venv,target_is_directory=True)
        return baseline,venv

    def test_failed_health_restores_code_and_dependency_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);baseline,venv=self.prepare(root)
            data,digest=bundle();files=validate(data,COMMIT,digest)
            installer=Installer(root,root/"data")
            with patch.object(installer,"environment",return_value=venv),patch.object(installer,"backup"),patch.object(installer,"restart") as restart,patch.object(installer,"check",side_effect=[False,True]):
                with self.assertRaisesRegex(RuntimeError,"rollback completed"):
                    installer.deploy(files,COMMIT,digest)
            self.assertEqual((root/"current").resolve(),baseline)
            self.assertEqual((root/"current-venv").resolve(),venv)
            self.assertEqual(restart.call_count,2)
            self.assertFalse((root/"releases"/COMMIT).exists())

    def test_success_keeps_previous_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);baseline,venv=self.prepare(root)
            data,digest=bundle();files=validate(data,COMMIT,digest)
            installer=Installer(root,root/"data")
            with patch.object(installer,"environment",return_value=venv),patch.object(installer,"backup"),patch.object(installer,"restart"),patch.object(installer,"check",return_value=True):
                installer.deploy(files,COMMIT,digest)
            self.assertTrue(baseline.exists())
            self.assertEqual((root/"current").resolve(),root/"releases"/COMMIT)


if __name__=="__main__":unittest.main()
