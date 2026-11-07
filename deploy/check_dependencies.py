"""Check the exact runtime lock against PyPI's published security advisories."""
import concurrent.futures
import json
from pathlib import Path
import re
import time
import urllib.request


def check(line):
    name,version=line.split("==")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+",name+version):
        raise ValueError("Invalid locked dependency")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json",timeout=20) as reply:
                data=json.load(reply)
            return name,[item["id"] for item in data.get("vulnerabilities",[])]
        except Exception:
            if attempt==2:
                raise RuntimeError("Could not audit "+name) from None
            time.sleep(1)


if __name__=="__main__":
    lines=Path(__file__).with_name("requirements-server.lock").read_text().splitlines()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(check,filter(None,lines)))
    problems=[name+": "+", ".join(ids) for name,ids in results if ids]
    if problems:
        raise SystemExit("Runtime security advisories found:\n"+"\n".join(problems))
    print(f"No published PyPI advisories found for {len(results)} locked runtime packages.")
