#!/usr/bin/env python3
"""Restore only into a new directory, validate hashes and database + media references."""

import argparse
import hashlib
import json
import sqlite3
import tarfile
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("archive", type=Path)
p.add_argument("destination", type=Path)
a = p.parse_args()
if a.destination.exists():
    raise SystemExit("Destination must not exist; never overwrite production")
a.destination.mkdir(mode=0o700, parents=True)
with tarfile.open(a.archive) as t:
    for m in t.getmembers():
        if (
            not (m.isfile() or m.isdir())
            or Path(m.name).is_absolute()
            or ".." in Path(m.name).parts
        ):
            raise SystemExit("Unsafe archive")
    t.extractall(a.destination, filter="data")
manifest = json.loads((a.destination / "manifest.json").read_text())
for name, digest in manifest.items():
    p = Path(name)
    if p.is_absolute() or ".." in p.parts:
        raise SystemExit("Unsafe manifest")
    assert hashlib.sha256((a.destination / p).read_bytes()).hexdigest() == digest, (
        "Hash mismatch"
    )
c = sqlite3.connect(a.destination / "stash.sqlite3")
assert c.execute("pragma integrity_check").fetchone()[0] == "ok"
for (name,) in c.execute(
    "select photo from inventory_item where photo != '' union select photo from inventory_container where photo != ''"
):
    assert (a.destination / "photos" / name).is_file()
print(
    "Restored and verified",
    c.execute("select count(*) from inventory_item").fetchone()[0],
    "inventory records and all referenced originals",
)
