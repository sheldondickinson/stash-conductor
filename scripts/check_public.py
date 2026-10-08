"""Fail closed on accidental deployment data in tracked files or outgoing history."""

import re
import subprocess
from pathlib import Path

files = subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
for name in filter(None, files):
    assert not any(
        x in Path(name).parts for x in ("data", ".venv", ".playwright-cli", "output")
    ), name
    assert Path(name).name not in (".env", "CODEX_START_HERE.md", "backup-password"), (
        name
    )
    raw = Path(name).read_bytes()
    if b"\0" in raw:
        continue
    for pattern in [
        rb"313east\.cc",
        rb"/" + rb"Users/",
        rb"192\.168\.",
        rb"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY",
        rb"gh[pousr]_[A-Za-z0-9]{30,}",
    ]:
        assert not re.search(pattern, raw), f"Private-data pattern in {name}"
print("Tracked public-source checks passed")
