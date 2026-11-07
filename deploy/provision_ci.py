#!/usr/bin/python3
"""One-time operator provisioning. CI never runs this script with elevated privileges."""
import os
import pwd
import re
import shutil
import subprocess
import sys
from pathlib import Path

root=Path("/opt/prism-learning")
helpers=Path("/usr/local/lib/prism-cicd")
if os.geteuid()!=0 or len(sys.argv)!=2 or not (root/".prism-owned").is_file():
    sys.exit("Run as the server operator for the existing isolated Prism installation.")
if helpers.exists() and not (helpers/".prism-owned").is_file():
    sys.exit("Refusing an unrelated helper directory")
if not helpers.exists():
    for name in ("prism-deploy","prism-build"):
        try:
            pwd.getpwnam(name)
        except KeyError:
            continue
        sys.exit("Refusing an existing unrelated deployment account")
helpers.mkdir(parents=True,exist_ok=True);(helpers/".prism-owned").touch()
public=Path(sys.argv[1]).read_text().strip().split()
if len(public)<2 or public[0]!="ssh-ed25519" or not re.fullmatch(r"[A-Za-z0-9+/=]+",public[1]):
    sys.exit("An Ed25519 public key is required")
for name in ("prism-deploy","prism-build"):
    try:
        pwd.getpwnam(name)
    except KeyError:
        subprocess.run(["useradd","--system","--create-home","--home-dir","/var/lib/"+name,"--shell","/bin/sh" if name=="prism-deploy" else "/usr/sbin/nologin",name],check=True)
home=Path("/var/lib/prism-deploy");os.chown(home,0,0);os.chmod(home,0o755)
ssh=home/".ssh";ssh.mkdir(exist_ok=True);os.chown(ssh,0,0);os.chmod(ssh,0o755)
(ssh/"authorized_keys").write_text('restrict,command="/usr/bin/python3 /usr/local/lib/prism-cicd/ssh_entry.py" '+public[0]+" "+public[1]+" prism-github-production\n")
os.chmod(ssh/"authorized_keys",0o644)
source=Path(__file__).resolve().parent
for name in ("archive.py","ssh_entry.py"):
    shutil.copyfile(source/name,helpers/name);os.chmod(helpers/name,0o644)
receiver=Path("/usr/local/sbin/prism-install-release")
shutil.copyfile(source/"receiver.py",receiver);os.chmod(receiver,0o755)
sudoers=Path("/etc/sudoers.d/prism-learning-deploy")
temporary=sudoers.with_suffix(".pending")
temporary.write_text("prism-deploy ALL=(root) NOPASSWD: /usr/local/sbin/prism-install-release\n")
os.chmod(temporary,0o440)
subprocess.run(["visudo","-cf",str(temporary)],check=True)
temporary.replace(sudoers)
releases=root/"releases";releases.mkdir(exist_ok=True)
if not (root/"current").is_symlink():
    baseline=releases/"bootstrap";baseline.mkdir(exist_ok=True)
    for name in ("app","deploy"):
        shutil.copytree(root/name,baseline/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns("__pycache__"))
    (baseline/"release.env").write_text("PRISM_RELEASE_SHA=bootstrap\n")
    (root/"current").symlink_to(baseline,target_is_directory=True)
if not (root/"current-venv").is_symlink():
    (root/"current-venv").symlink_to(root/"venv",target_is_directory=True)
dropin=Path("/etc/systemd/system/prism-learning.service.d")
dropin.mkdir(exist_ok=True)
(dropin/"ci.conf").write_text("""[Service]
WorkingDirectory=/opt/prism-learning/current
EnvironmentFile=-/opt/prism-learning/current/release.env
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=
ExecStart=/opt/prism-learning/current-venv/bin/python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8176 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log --timeout-graceful-shutdown 150
TimeoutStopSec=170
""")
subprocess.run(["systemctl","daemon-reload"],check=True)
print("Provisioned a Prism-only deployment account and release links. No other site or service changed.")
