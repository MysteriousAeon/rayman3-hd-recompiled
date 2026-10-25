#!/usr/bin/env python3
"""Achievement text for the Turkish mod (D-101): the title's own achievement metadata (XDBF resource of the XEX,
read from the decrypted image), a private translation template, and the check of a mod's optional
`achievements/achievements.json`. Nothing here changes an achievement, its id, unlock rule, score or state. The
runtime shows such text in the host Achievements overlay and toast only (r3hd_mods.py plan -> R3HD_ACH_TEXT ->
tools/r3hd_achtext.h, which checks each source hash against the title's XDBF; the font has U+0100..U+017F since
D-101). This file holds ids, field names and hashes only.

usage:
  r3hd_achievements.py inventory [--image IMG] [--json]     ids, scores, languages, hashes (no text)
  r3hd_achievements.py template OUT.json [--image IMG]      private: English + hashes, empty Turkish
  r3hd_achievements.py check FILE.json|MOD.zip|MOD_DIR [--image IMG] [--font extended|current] [--json]
        (--font current = a 1.0.1 runtime, whose overlay font stops at U+00FF)
  r3hd_achievements.py selftest
Exit 0 ok, 1 problems, 2 refused.

achievements.json (format 1), inside the Turkish mod beside mod.json (format-1 mod tools of 1.0.1 carry an extra
file and ignore it, E-246):
  {"format": 1, "kind": "r3hd-achievement-text", "title_id": "5841123F", "language": "tr",
   "strings": [{"id": 9, "field": "label|description|unachieved", "source_sha256": "<sha256 of the English>",
                "text": "<Turkish; empty = English>", "english": "<optional, ignored>"}]}
"""
import argparse
import hashlib
import io
import json
import struct
import sys
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "private" / "work" / "default_image.bin"
TITLE_ID = "5841123F"
IMAGE_BASE, RESOURCE_VA, RESOURCE_SIZE = 0x82000000, 0x82CB0000, 0x2EDBF   # RE_NOTES section 1 (XEX resource)
KIND = "r3hd-achievement-text"
FIELDS = ("label", "description", "unachieved")
MAX_LEN = {"label": 64, "description": 160, "unachieved": 160}
# XLanguage numbers of the console (the SDK's enum); the title's XDBF has 1, 3, 4, 5, 6 (E-245).
LANGS = {1: "en", 2: "ja", 3: "de", 4: "fr", 5: "es", 6: "it", 7: "ko", 8: "zh-tw", 9: "pt", 10: "zh-cn", 11: "pl",
         12: "ru"}
# The SDK's overlay font (imgui_drawer.cpp at the pin): ProggyTiny for U+0020..U+00FF only (+ CJK from msgothic).
FONT_CURRENT = (0x20, 0xFF)
FONT_EXTENDED = (0x20, 0x17F)   # D-101 runtimes: Latin Extended-A for ğ Ğ ı İ ş Ş


class Refused(Exception):
    pass


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def parse_xdbf(d: bytes) -> dict:
    """{'achievements': [...], 'strings': {lang: {id: text}}, 'default_language': n} from an XDBF blob."""
    if len(d) < 24 or d[:4] != b"XDBF":
        raise Refused("no XDBF at the resource address (is this the decrypted image of 5841123F?)")
    _, _, ecount, eused, fcount, _ = struct.unpack_from(">4sIIIII", d, 0)
    content = 24 + ecount * 18 + fcount * 8
    out = {"achievements": [], "strings": {}, "default_language": 1}
    for i in range(eused):
        sec, eid, off, size = struct.unpack_from(">HQII", d, 24 + i * 18)
        blk = d[content + off:content + off + size]
        if sec == 3 and blk[:4] == b"XSTR":
            cnt = struct.unpack_from(">H", blk, 12)[0]
            p, tbl = 14, {}
            for _ in range(cnt):
                sid, ln = struct.unpack_from(">HH", blk, p)
                tbl[sid] = blk[p + 4:p + 4 + ln].decode("utf-8")
                p += 4 + ln
            out["strings"][eid] = tbl
        elif sec == 1 and eid == 0x58414348 and blk[:4] == b"XACH":
            cnt = struct.unpack_from(">H", blk, 12)[0]
            for k in range(cnt):
                e = struct.unpack_from(">HHHHIHHIIIII", blk, 14 + k * 36)
                out["achievements"].append({"id": e[0], "label_id": e[1], "description_id": e[2],
                                            "unachieved_id": e[3], "image_id": e[4], "gamerscore": e[5],
                                            "flags": e[7]})
        elif sec == 1 and eid == 0x58535443 and blk[:4] == b"XSTC":
            out["default_language"] = struct.unpack_from(">I", blk, 12)[0]
    return out


def load_image(path) -> dict:
    p = Path(path)
    if not p.is_file():
        raise Refused(f"{p}: no decrypted image (a developer build's private/work/default_image.bin); a user-mode "
                      "clone has none, the runtime reads the same table from memory")
    data = p.read_bytes()
    off = RESOURCE_VA - IMAGE_BASE
    return parse_xdbf(data[off:off + RESOURCE_SIZE])


def english(db: dict) -> list:
    """[(id, field, English)] in table order."""
    en = db["strings"].get(1, {})
    rows = []
    for a in db["achievements"]:
        for f in FIELDS:
            rows.append((a["id"], f, en.get(a[f + "_id"], "")))
    return rows


def inventory(db: dict) -> dict:
    ach = db["achievements"]
    rows = english(db)
    by = {(i, f): t for i, f, t in rows}
    return {"achievements": len(ach), "ids": [a["id"] for a in ach],
            "gamerscore_total": sum(a["gamerscore"] for a in ach),
            "languages": [LANGS.get(k, str(k)) for k in sorted(db["strings"])],
            "default_language": LANGS.get(db["default_language"], db["default_language"]),
            "turkish_in_title": False,   # the console's language list has no Turkish; the table has none
            "unachieved_equals_description": sum(by[(a["id"], "unachieved")] == by[(a["id"], "description")]
                                                 for a in ach),
            "max_chars": {f: max((len(t) for i, ff, t in rows if ff == f), default=0) for f in FIELDS},
            "rows_sha256": {f"{i}.{f}": sha(t) for i, f, t in rows}}


def read_text_file(src: Path) -> dict:
    src = Path(src)
    if src.is_dir():
        p = src / "achievements" / "achievements.json"
        if not p.is_file():
            raise Refused(f"{src}: no achievements/achievements.json (optional: the overlay stays English)")
        raw = p.read_bytes()
    elif src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as z:
            try:
                raw = z.read("achievements/achievements.json")
            except KeyError:
                raise Refused(f"{src}: no achievements/achievements.json (optional: the overlay stays English)")
    else:
        raw = src.read_bytes()
    if len(raw) > 256 * 1024:
        raise Refused("achievements.json is too large")
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as e:
        raise Refused(f"achievements.json is not JSON: {e}")


def check_text(doc: dict, db: dict, font=FONT_CURRENT) -> dict:
    """Pure: schema, ids, fields, source hashes and characters of a translation file against the title's table."""
    errors, warnings = [], []
    if not isinstance(doc, dict):
        return {"ok": False, "errors": ["not an object"], "warnings": [], "translated": 0}
    extra = set(doc) - {"format", "kind", "title_id", "language", "strings", "note"}
    if extra:
        errors.append(f"unknown keys {sorted(extra)}")
    if doc.get("format") != 1 or doc.get("kind") != KIND:
        errors.append(f"format must be 1 and kind '{KIND}'")
    if doc.get("title_id") != TITLE_ID:
        errors.append(f"title_id must be {TITLE_ID}")
    if not isinstance(doc.get("language"), str) or not doc["language"].isalpha() or len(doc["language"]) > 8:
        errors.append("language must be a short code such as 'tr'")
    src = {(i, f): t for i, f, t in english(db)}
    seen, translated = set(), 0
    strings = doc.get("strings")
    if not isinstance(strings, list):
        errors.append("strings must be a list")
        strings = []
    for n, s in enumerate(strings):
        where = f"strings[{n}]"
        if not isinstance(s, dict):
            errors.append(f"{where}: not an object")
            continue
        if set(s) - {"id", "field", "source_sha256", "text", "english"}:
            errors.append(f"{where}: unknown keys {sorted(set(s) - {'id', 'field', 'source_sha256', 'text', 'english'})}")
        key = (s.get("id"), s.get("field"))
        if not isinstance(key[0], int) or isinstance(key[0], bool) or key[1] not in FIELDS:
            errors.append(f"{where}: id must be an achievement number and field one of {', '.join(FIELDS)}")
            continue
        where = f"{key[0]}.{key[1]}"
        if key not in src:
            errors.append(f"{where}: the title has no such achievement")
            continue
        if key in seen:
            errors.append(f"{where}: listed twice")
            continue
        seen.add(key)
        if s.get("source_sha256") != sha(src[key]):
            errors.append(f"{where}: STALE: the English it was translated from is not the title's")
        t = s.get("text", "")
        if not isinstance(t, str):
            errors.append(f"{where}: text must be a string")
            continue
        if not t:
            continue   # English shown
        translated += 1
        if t != t.strip():
            warnings.append(f"{where}: leading or trailing spaces")
        if len(t) > MAX_LEN[key[1]]:
            errors.append(f"{where}: {len(t)} characters, more than {MAX_LEN[key[1]]}")
        bad = sorted({c for c in t if ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0})
        if bad:
            errors.append(f"{where}: control characters {[hex(ord(c)) for c in bad]}")
        undrawable = sorted({c for c in t if not (font[0] <= ord(c) <= font[1]) and ord(c) >= 0x20})
        if undrawable:
            warnings.append(f"{where}: the overlay font of this runtime cannot draw "
                            + " ".join(f"U+{ord(c):04X}" for c in undrawable) + " (needs the D-101 font range)")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "translated": translated,
            "entries": len(seen), "possible": len(src)}


def cmd_template(a) -> dict:
    sys.path.insert(0, str(ROOT / "tools"))
    import r3hd_locflow as lf
    out = Path(a.out)
    lf.private_path(out)
    if out.exists():
        raise Refused(f"{out} exists: a template is never overwritten (it may hold a person's translation)")
    db = load_image(a.image)
    doc = {"format": 1, "kind": KIND, "title_id": TITLE_ID, "language": "tr",
           "note": "PRIVATE. Fill 'text' (empty = English shown). Never edit id, field, source_sha256 or english.",
           "strings": [{"id": i, "field": f, "source_sha256": sha(t), "english": t, "text": ""}
                       for i, f, t in english(db)]}
    out.parent.mkdir(parents=True, exist_ok=True)
    lf.atomic_write(out, (json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    res = check_text(doc, db)
    return {"ok": res["ok"], "out": str(out), "entries": res["entries"], "translated": res["translated"]}


# ---------------------------------------------------------------------------------------------------------------

def make_xdbf(ach: list, strings: dict) -> bytes:
    """Synthetic XDBF (selftest): ach = [(id, label, desc, unach, score)], strings = {lang: {sid: text}}."""
    blocks = []
    x = b"".join(struct.pack(">HHHHIHHIIIII", i, l, d, u, 0x29 + n, sc, 0, 9, 0, 0, 0, 0)
                 for n, (i, l, d, u, sc) in enumerate(ach))
    blocks.append((1, 0x58414348, struct.pack(">4sIIH", b"XACH", 1, len(x) + 14, len(ach)) + x))
    blocks.append((1, 0x58535443, struct.pack(">4sIII", b"XSTC", 1, 12, 1)))
    for lang, tbl in strings.items():
        body = b"".join(struct.pack(">HH", sid, len(t.encode())) + t.encode() for sid, t in sorted(tbl.items()))
        blocks.append((3, lang, struct.pack(">4sIIH", b"XSTR", 1, len(body) + 14, len(tbl)) + body))
    head = struct.pack(">4sIIIII", b"XDBF", 0x10000, len(blocks), len(blocks), 1, 1)
    ents, data = b"", b""
    for sec, eid, b in blocks:
        ents += struct.pack(">HQII", sec, eid, len(data), len(b))
        data += b
    return head + ents + struct.pack(">II", 0, 0) + data


def selftest() -> int:
    fails, done = [], []

    def check(name, ok, detail=""):
        print(("ok   " if ok else "FAIL ") + name + (f": {detail}" if detail and not ok else ""))
        done.append(name)
        if not ok:
            fails.append(name)

    en = {1: "First", 2: "Do a thing.", 3: "Do a thing.", 4: "Second", 5: "Other thing.", 6: "Other thing."}
    db = parse_xdbf(make_xdbf([(1, 1, 2, 3, 10), (9, 4, 5, 6, 5)], {1: en, 3: {1: "Erste"}}))
    inv = inventory(db)
    check("parse: two achievements, ids, scores", inv["ids"] == [1, 9] and inv["gamerscore_total"] == 15)
    check("parse: languages", inv["languages"] == ["en", "de"] and inv["default_language"] == "en")
    check("unachieved equals description counted", inv["unachieved_equals_description"] == 2)
    check("inventory holds no text", "First" not in json.dumps(inv))

    def doc(strings, **kw):
        d = {"format": 1, "kind": KIND, "title_id": TITLE_ID, "language": "tr", "strings": strings}
        d.update(kw)
        return d

    def s(i, f, text, src=None):
        return {"id": i, "field": f, "source_sha256": sha(src if src is not None else
                                                          {(1, "label"): "First", (1, "description"): "Do a thing.",
                                                           (9, "label"): "Second"}.get((i, f), "")), "text": text}
    r = check_text(doc([s(1, "label", "Birinci"), s(1, "description", "")]), db)
    check("valid file: one translated, empty = English", r["ok"] and r["translated"] == 1 and r["entries"] == 2)
    r = check_text(doc([s(1, "label", "Birinci", src="Old")]), db)
    check("stale English refused", not r["ok"] and "STALE" in r["errors"][0])
    r = check_text(doc([s(7, "label", "x")]), db)
    check("unknown achievement refused", not r["ok"])
    r = check_text(doc([dict(s(1, "label", "x"), field="score")]), db)
    check("unknown field refused (no score / unlock / id edits)", not r["ok"])
    r = check_text(doc([s(1, "label", "a"), s(1, "label", "b")]), db)
    check("duplicate refused", not r["ok"] and "twice" in r["errors"][0])
    r = check_text(doc([s(1, "label", "a\x01b")]), db)
    check("control character refused", not r["ok"])
    r = check_text(doc([s(1, "label", "x" * 65)]), db)
    check("too long refused", not r["ok"])
    r = check_text(doc([s(9, "label", "Başarı İçin ğ ı")]), db)
    check("Turkish letters: warning with the current font", r["ok"] and any("U+011F" in w for w in r["warnings"]))
    r = check_text(doc([s(9, "label", "Başarı İçin ğ ı")]), db, FONT_EXTENDED)
    check("Turkish letters: clean with the extended range", r["ok"] and not r["warnings"])
    r = check_text(doc([], gamerscore=5), db)
    check("unknown top-level key refused", not r["ok"])
    r = check_text(doc([], title_id="41560817"), db)
    check("other title refused", not r["ok"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mod.json", "{}")
        z.writestr("achievements/achievements.json", json.dumps(doc([s(1, "label", "Birinci")])))
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        zp = Path(td) / "m.zip"
        zp.write_bytes(buf.getvalue())
        check("read from a mod zip", check_text(read_text_file(zp), db)["translated"] == 1)
        empty = Path(td) / "mod"
        empty.mkdir()
        try:
            read_text_file(empty)
            check("mod without the file: English fallback reported", False)
        except Refused as x:
            check("mod without the file: English fallback reported", "stays English" in str(x))
    print(f"R3HD_ACHIEVEMENTS_SELFTEST {'PASS' if not fails else 'FAIL'} {len(done) - len(fails)}/{len(done)}")
    return 0 if not fails else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inventory")
    p.add_argument("--image", default=str(IMAGE))
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("template")
    p.add_argument("out")
    p.add_argument("--image", default=str(IMAGE))
    p = sub.add_parser("check")
    p.add_argument("src")
    p.add_argument("--image", default=str(IMAGE))
    p.add_argument("--font", choices=("current", "extended"), default="extended")
    p.add_argument("--json", action="store_true")
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    try:
        if a.cmd == "inventory":
            res = inventory(load_image(a.image))
            res["ok"] = True
            if not a.json:
                res.pop("rows_sha256")
        elif a.cmd == "template":
            res = cmd_template(a)
        else:
            res = check_text(read_text_file(Path(a.src)), load_image(a.image),
                             FONT_EXTENDED if a.font == "extended" else FONT_CURRENT)
    except Refused as x:
        print(f"REFUSED: {x}", file=sys.stderr)
        return 2
    print(json.dumps(res, indent=1, ensure_ascii=True))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
