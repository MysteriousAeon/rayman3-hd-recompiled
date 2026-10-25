#!/usr/bin/env python3
"""Release 1.0.1 (D-110): the final metadata of the Turkish mod, made from the approved LQA candidate.

    python tools/release_turkish_metadata.py OUT.zip [--source ZIP]

Only two manifest fields change: `authors` (empty -> the translator the maintainer named) and `license` (the legacy
placeholder "Your choice; it holds no game text.", which was untrue for translated game text, -> a rights notice
that grants nothing and claims nothing of the game's text). The ID, name, version, description, target and every
override stay the candidate's; `achievements/achievements.json` is copied byte for byte; the entry order, time stamps
and compression are the candidate's. The version stays 1.0.1: the candidate was never published, and its file name is
the one the setup, the documents and the release refer to (an installed copy of the candidate is kept by the bundled
mod policy as "same version, other files"; only these two fields differ).

Refuses (exit 2) unless the source is the approved candidate (SHA-256 below). The output is deterministic and holds the
translation, so it stays under private/.
"""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "private" / "work" / "lqa_ellipsis_20261025" / "mod_candidate" / "rayman3hd-turkish-1.0.1.zip"
SOURCE_SHA256 = "16c754e34e840680b1493e4c03f30ef31229e109adc10d8d1c4652b3e416aa0d"
ENTRIES = ["mod.json", "achievements/achievements.json"]
CHANGES = {
    "authors": ["MysteriousAeon"],
    "license": ("No license is granted. Turkish translation of Rayman 3 game text; the original text belongs to "
                "Ubisoft. Not covered by the project's MIT license. For use with your own copy of the game."),
}


class Refused(Exception):
    pass


def build(source: Path, out: Path) -> dict:
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise Refused(f"{source}: not the approved 1.0.1 candidate {SOURCE_SHA256}")
    if out.exists():
        raise Refused(f"{out} exists: a package is never replaced")
    with zipfile.ZipFile(source) as z:
        infos = z.infolist()
        if [i.filename for i in infos] != ENTRIES:
            raise Refused(f"unexpected entries {[i.filename for i in infos]}")
        data = {i.filename: z.read(i.filename) for i in infos}
    text = data["mod.json"].decode("utf-8")
    old = json.loads(text)
    for key, value in CHANGES.items():
        line = f'\n  "{key}": {json.dumps(old[key], ensure_ascii=False)},\n'
        if text.count(line) != 1:
            raise Refused(f"the {key} line is not found exactly once")
        text = text.replace(line, f'\n  "{key}": {json.dumps(value, ensure_ascii=False)},\n')
    new = json.loads(text)
    if set(new) != set(old) or any(new[k] != old[k] for k in old if k not in CHANGES):
        raise Refused("a field other than authors / license changed")
    if any(new[k] != v for k, v in CHANGES.items()) or len(new["license"]) > 200:
        raise Refused("the new fields did not come out as intended (license: at most 200 characters)")
    data["mod.json"] = text.encode("utf-8")
    sys.path.insert(0, str(ROOT / "tools"))
    import r3hd_mods as mods
    try:
        mods.parse_manifest(dict(data))
    except mods.Refusal as e:
        raise Refused(f"the mod tools refuse the new manifest: {e}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as z:
        for i in infos:
            info = zipfile.ZipInfo(i.filename, date_time=i.date_time)
            info.compress_type = i.compress_type
            info.external_attr = i.external_attr
            info.create_system = i.create_system
            z.writestr(info, data[i.filename])
    with zipfile.ZipFile(out) as z:
        if z.namelist() != ENTRIES or z.read(ENTRIES[1]) != data[ENTRIES[1]] or z.read("mod.json") != data["mod.json"]:
            raise Refused("the written package does not read back as intended")
    body = out.read_bytes()
    return {"out": str(out), "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(), "id": new["id"],
            "name": new["name"], "version": new["version"], "source_sha256": SOURCE_SHA256,
            "manifest_sha256": hashlib.sha256(data["mod.json"]).hexdigest(),
            "achievements_sha256": hashlib.sha256(data[ENTRIES[1]]).hexdigest(),
            "overrides_sha256": hashlib.sha256(json.dumps(new["overrides"], sort_keys=True, ensure_ascii=False)
                                               .encode()).hexdigest(),
            "overrides": len(new["overrides"]), "authors": new["authors"], "license": new["license"],
            "changed_fields": sorted(CHANGES), "unchanged_fields": sorted(k for k in old if k not in CHANGES)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--source", type=Path, default=SOURCE)
    a = ap.parse_args()
    try:
        r = build(a.source, a.out)
    except Refused as e:
        print(f"RELEASE_TURKISH_METADATA REFUSED {e}")
        return 2
    print(json.dumps(r, indent=1, ensure_ascii=False))
    print(f"RELEASE_TURKISH_METADATA OK {r['sha256']} {r['id']} {r['version']} overrides={r['overrides']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
