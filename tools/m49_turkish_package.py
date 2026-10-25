#!/usr/bin/env python3
"""M49 (D-088): the release package of the bundled Turkish translation, made from the M47 / M48-P candidate.

    python tools/m49_turkish_package.py OUT.zip [--source ZIP]

Only three manifest fields change: the name and the description (the candidate's said "DEV: unreviewed text",
"NOT FINAL ... do not share", which Settings > Mods shows to a player) and the version (0.2.0-dev -> 1.0.0, so an
installation that has the candidate is updated in place, its on / off choice and priority kept). The ID stays
tr.full.dev (the key of that update; a new ID would make a second copy). Every other byte of mod.json is the
candidate's: the text replacement is checked by reading both manifests back and comparing every other field, the
overrides included. The translation text itself is not touched (the person's decision for this release). The
provenance of the strings (reviewed drafts, none human-approved) stays in the project records (RE_NOTES / D-085).

Refuses (exit 2) unless the source is the candidate (SHA-256 below). The output is deterministic (fixed time stamp).
It holds the translation, so it stays under private/ like the candidate.
"""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "private" / "tr" / "rayman3hd-turkish" / "build" / "preview" / "tr_full_dev-0_2_0.zip"
SOURCE_SHA256 = "39b220e75e7c38ea04500ec17acaee57511fbba49fe0ec9b3475f2a6b015ae2f"
CHANGES = {
    "name": "Türkçe",
    "version": "1.0.0",
    "description": "Turkish translation of the game's text, menus and subtitles (Türkçe çeviri).",
}


def build(source: Path, out: Path) -> dict:
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise SystemExit(f"M49_TURKISH_PACKAGE REFUSED {source}: not the M47 / M48-P candidate {SOURCE_SHA256}")
    with zipfile.ZipFile(source) as z:
        names = z.namelist()
        if names != ["mod.json"]:
            raise SystemExit(f"M49_TURKISH_PACKAGE REFUSED unexpected entries {names}")
        text = z.read("mod.json").decode("utf-8")
    old = json.loads(text)
    for key, value in CHANGES.items():
        line = f'\n  "{key}": {json.dumps(old[key], ensure_ascii=False)},\n'
        if text.count(line) != 1:
            raise SystemExit(f"M49_TURKISH_PACKAGE REFUSED the {key} line is not found exactly once")
        text = text.replace(line, f'\n  "{key}": {json.dumps(value, ensure_ascii=False)},\n')
    new = json.loads(text)
    same = all(new[k] == old[k] for k in old if k not in CHANGES) and set(new) == set(old)
    if not same or any(new[k] != v for k, v in CHANGES.items()):
        raise SystemExit("M49_TURKISH_PACKAGE REFUSED a field other than name / version / description changed")
    out.parent.mkdir(parents=True, exist_ok=True)
    info = zipfile.ZipInfo("mod.json", date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(info, text.encode("utf-8"))
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    overrides = hashlib.sha256(json.dumps(new["overrides"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {"out": str(out), "sha256": digest, "bytes": out.stat().st_size, "id": new["id"], "version": new["version"],
            "source_sha256": SOURCE_SHA256, "overrides": len(new["overrides"]), "overrides_sha256": overrides,
            "unchanged_fields": sorted(k for k in old if k not in CHANGES)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--source", type=Path, default=SOURCE)
    a = ap.parse_args()
    r = build(a.source, a.out)
    print(json.dumps(r, indent=1, ensure_ascii=False))
    print(f"M49_TURKISH_PACKAGE OK {r['sha256']} {r['id']} {r['version']} overrides={r['overrides']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
