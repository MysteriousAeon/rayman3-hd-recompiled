#!/usr/bin/env python3
"""Issue #2: read-only target inventory; emits hashes/counts, never translation or audio data.

python tools/issue2_french_audit.py --out private/work/issue2/inventory.json
This is evidence extraction, not a playback/completeness or linguistic-quality judge.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct

import r3hd_loc as loc
import r3hd_mods as mods

ROOT = Path(__file__).resolve().parents[1]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def inventory(game):
    fix = (game / "GAMEDATAbin/fix.lvl").read_bytes()
    tables = loc.tables(fix)
    font = mods.read_font(fix)
    if font is None:
        raise ValueError("unrecognised font definitions")
    result = {"title_id": mods.TITLE_ID, "languages": {}, "glyphs": {}, "files": {}}
    for lang, (base, n) in tables.items():
        counts = Counter()
        used = Counter()
        gaps = {}
        for h in range(n):
            ptr = struct.unpack_from(">I", fix, base + h * 4)[0]
            if not ptr:
                counts["null"] += 1
                continue
            try:
                _, slot = loc.string_at(fix, tables, f"{lang}.{h}")
                raw = slot[:slot.index(0)]
                counts["plain_text"] += 1
                used.update(raw)
                for code in set(raw) - font["defined"] - {0x5C}:
                    gaps.setdefault(str(code), []).append(h)
            except loc.Problem:
                counts["non_plain_or_empty"] += 1
        result["languages"][lang] = {"handles": n, **counts,
                                      "undefined_codes": sorted(c for c in used if c not in font["defined"] and c != 0x5C),
                                      "undefined_code_handles": gaps}
    for ch in "éèàçêôœÉÈÀÇÊÔŒîïùûüÿëæÆ":
        code = ch.encode("cp1252")[0]
        result["glyphs"][ch] = {"cp1252": code,
                                 "defined_both_copies": code in font["defined"],
                                 "mod_override_allowed": ch in mods.GLYPH_CODES}
    sub = mods.parse_vs_sub((game / mods.SUB_FILE).read_bytes())
    result["movie_subtitles"] = dict(Counter(c[0] for c in sub["cues"]))
    sound = game / "GAMEDATAbin/WORLD/SOUND"
    banks = {}
    # Serialized language -> wave UUID tables. Match all five keys, not arbitrary 'fr' bytes.
    pattern = re.compile(rb"de  (.{8})en  (.{8})es  (.{8})fr  (.{8})it  (.{8})", re.S)
    for p in sorted(sound.rglob("*.hxx")):
        data = p.read_bytes()
        variants = list(pattern.finditer(data))
        if variants:
            banks[p.relative_to(sound).as_posix()] = {
                "five_language_tables": len(variants),
                "fr_en_distinct": sum(m[2] != m[4] for m in variants),
                "fr_uuid_also_defined_in_bank": sum(
                    b"Obj" + m[4] in data for m in variants)}
    result["sound_banks"] = banks
    result["movies"] = {}
    for p in sorted((game / "Videos").glob("*.bik")):
        with p.open("rb") as f:
            header = f.read(1024)
        if header[:4] not in (b"BIKi", b"BIKf", b"BIKg", b"BIKh"):
            raise ValueError(f"unrecognised Bink header: {p.name}")
        n = struct.unpack_from("<I", header, 40)[0]
        if n > 16:
            raise ValueError("unbounded audio-track count")
        result["movies"][p.name] = {"audio_tracks": n, "track_ids": [
            struct.unpack_from("<I", header, 44 + 8 * n + 4 * i)[0] for i in range(n)]}
    paths = [game / "Default.xex", *(game / "GAMEDATAbin" / n for n in
              ("fix.lvl", "fix.ptr", "fix.bhf", "fix.btf", "VS.sub")),
             *sound.rglob("*"), *(game / "Videos").glob("*.bik")]
    for p in sorted(p for p in paths if p.is_file()):
        result["files"][p.relative_to(game).as_posix()] = {"size": p.stat().st_size, "sha256": digest(p)}
    result["font_definitions"] = {hex(b): hashlib.sha256(fix[b:b + mods.FONTDEF_BYTES]).hexdigest()
                                   for b in mods.FONT["sha256"]}
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-dir", type=Path, default=ROOT / "private/extracted/5841123F")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fixture", type=Path, help="new private folder for a target-derived glyph/text/subtitle specimen")
    a = ap.parse_args()
    result = inventory(a.game_dir)
    if a.fixture:
        make_fixture(a.game_dir, a.fixture)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes((json.dumps(result, ensure_ascii=True, indent=2) + "\n").encode())
    print("ISSUE2_INVENTORY OK languages=" + ",".join(result["languages"]) +
          f" banks_with_five_variants={len(result['sound_banks'])} hashed_files={len(result['files'])}")


def make_fixture(game, out):
    """Test-authored text, plus ligature art from this target's unmapped cells. Never distributable."""
    from PIL import Image
    private = (ROOT / "private").resolve()
    if not out.resolve().is_relative_to(private) or out.exists():
        raise ValueError("fixture must be a NEW directory under private/")
    fixp = game / "GAMEDATAbin/fix.lvl"
    if digest(fixp) != "f929551622ad62394367ae65f94cd942a6c8176dbe8d63aec73e8dfecac5d3e5":
        raise ValueError("fixture requires the verified Xbox 360 HD fix.lvl")
    bhf, entry, w, h, fmt = mods.resolve_texture(game, {"entry": mods.FONT["atlas"],
                                                       "bundles": [mods.FONT["bundle"]]})[0]
    data = bhf.with_suffix(".btf").read_bytes()
    blobs = (data[entry[2]:entry[2] + entry[1]], data[entry[4]:entry[4] + entry[3]])
    atlas = mods.decode_level(w, h, mods.level_rows(blobs, mods.layout(w, h, fmt)[2][0], fmt), fmt)
    out.mkdir(parents=True)
    image = Image.frombytes("RGBA", (w, h), atlas)
    overrides = []
    # Include a transparent margin around the existing ink; baseline at y=287.
    for ch, box, name in (("œ", (277, 262, 313, 288), "lower_oe.png"),
                           ("Œ", (338, 255, 371, 288), "upper_oe.png")):
        image.crop(box).save(out / name)
        overrides.append({"type": "glyph", "char": ch, "width": box[2] - box[0], "height": box[3] - box[1],
                          "descent": 0, "layers": [{"image": name, "x": 0, "y": 0}]})
    fix = fixp.read_bytes()
    tables = loc.tables(fix)
    for sid, text in (("fr.186", "é è à ç ê ô"), ("fr.276", "\\jcÉ È À Ç Ê Ô\\lœ Œ")):
        offset, slot = loc.string_at(fix, tables, sid)
        overrides.append({"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": offset,
                          "slot_sha256": mods.sha256_bytes(slot), "text": text})
    sub = mods.parse_vs_sub((game / mods.SUB_FILE).read_bytes())
    sid = "vs.fr.42.0"
    overrides.append({"type": "subtitle", "id": sid, "source_sha256": mods.sub_hash(sub, sub["ids"][sid]),
                      "text": "é è à ç ê ô œ Œ"})
    manifest = {"format": 1, "id": "dev.issue2.french.specimen", "name": "Private French specimen",
                "version": "0.0.1", "authors": ["local test"], "description": "Target-derived; never distribute",
                "target": {"title_id": "5841123F", "releases": ["x360-xbla-5841123F-v1"],
                           "min_port_version": "1.0.2"}, "overrides": overrides}
    (out / "mod.json").write_bytes((json.dumps(manifest, ensure_ascii=True, indent=2) + "\n").encode())


if __name__ == "__main__":
    main()
