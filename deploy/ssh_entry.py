#!/usr/bin/python3
"""Forced SSH entry point. No shell, uploads, forwarding or other server commands."""
import os
import re
import shlex
import sys

command=shlex.split(os.environ.get("SSH_ORIGINAL_COMMAND",""))
if (len(command)!=3 or command[0]!="deploy" or not re.fullmatch(r"[0-9a-f]{40}",command[1])
    or not re.fullmatch(r"[0-9a-f]{64}",command[2])):
    sys.exit("Only a Prism release deployment is allowed.")
os.execv("/usr/bin/sudo",["sudo","-n","/usr/local/sbin/prism-install-release",command[1],command[2]])
