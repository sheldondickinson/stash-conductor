#!/usr/bin/env python3
"""Consistent SQLite + immutable originals backup. No production restore implicit."""

import argparse
import hashlib
import json
import os
import sqlite3
import tarfile
import tempfile
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("output", type=Path)
p.add_argument("--data", type=Path, default=Path(os.environ.get("STASH_DATA", "data")))
a = p.parse_args()
if a.output.exists():
    raise SystemExit("Refusing to overwrite a backup")
a.output.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as t:
    root = Path(t)
    with (
        sqlite3.connect(a.data / "stash.sqlite3") as source,
        sqlite3.connect(root / "stash.sqlite3") as target,
    ):
        source.backup(target)
    db = sqlite3.connect(root / "stash.sqlite3")
    assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
    # Media is immutable and never deleted by application actions. Copy all originals,
    # including historical/replaced photos, so every history link remains recoverable.
    import shutil

    shutil.copytree(a.data / "photos", root / "photos")
    names = [
        r[0]
        for r in db.execute(
            "select photo from inventory_item where photo != '' union select photo from inventory_container where photo != ''"
        )
    ]
    for name in names:
        assert (root / "photos" / name).is_file(), "Referenced photo missing"
    manifest = {
        str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in root.rglob("*")
        if f.is_file()
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    with tarfile.open(a.output, "w:gz") as tar:
        for f in root.iterdir():
            tar.add(f, arcname=f.name)
    a.output.chmod(0o600)
print("Backup complete:", a.output, hashlib.sha256(a.output.read_bytes()).hexdigest())
