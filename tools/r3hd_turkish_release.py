#!/usr/bin/env python3
"""Stage the frozen Turkish ZIP locally, without touching its sources or installer.

stage OUT: new directory below private/work, containing only ZIP + metadata + checksum.
check ZIP: verify pinned package bytes and contents; no game data or cache writes.
Run r3hd_modkit.py check separately for validation against the player's game files.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

import m49_turkish_package as package

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "config/localization/tr/release.json"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def check(path, record):
    raw = path.read_bytes()
    if len(raw) != record["bytes"] or sha(raw) != record["sha256"]:
        raise ValueError("ZIP differs from the selected release")
    with zipfile.ZipFile(path) as z:
        if z.namelist() != ["mod.json"]:
            raise ValueError("only mod.json is allowed; no reviews, assets or workspace files")
        manifest = z.read("mod.json")
    m = json.loads(manifest)
    if sha(manifest) != record["manifest_sha256"]:
        raise ValueError("manifest checksum differs")
    if any(m[k] != record[k] for k in ("id", "name", "version", "target")):
        raise ValueError("mod identity or target differs")
    if dict(Counter(o["type"] for o in m["overrides"])) != record["overrides"]:
        raise ValueError("override types or counts differ")


def stage(out, record):
    out = out.resolve()
    work = (ROOT / "private/work").resolve()
    if not out.is_relative_to(work) or out == work:
        raise ValueError("output must be a new directory below private/work")
    if out.exists():
        raise ValueError("output already exists; frozen candidates are never replaced")
    # Existing builder reads the pinned preview and changes only release metadata.
    # Build in a temporary directory; publish locally only after all checks pass.
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tr_release_", dir=work) as tmp:
        d = Path(tmp) / "release"
        d.mkdir()
        p = d / record["file"]
        package.build(package.SOURCE, p)
        check(p, record)
        (d / "MANIFEST.json").write_bytes(
            (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        (d / "SHA256SUMS.txt").write_bytes(
            f'{record["sha256"]}  {record["file"]}\n'.encode("ascii"))
        out.parent.mkdir(parents=True, exist_ok=True)
        d.rename(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=("stage", "check"))
    ap.add_argument("path", type=Path)
    a = ap.parse_args()
    try:
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        if a.cmd == "stage":
            stage(a.path, record)
        else:
            check(a.path, record)
    except (ValueError, OSError, zipfile.BadZipFile) as e:
        print(f"TURKISH_RELEASE REFUSED: {e}")
        return 2
    print(f'TURKISH_RELEASE {a.cmd.upper()} PASS {record["id"]} {record["version"]} {record["sha256"]}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
