#!/usr/bin/env python3
"""M34: a developer workflow for localization mods of Rayman 3 HD Recompiled (format-1 mods of tools/r3hd_mods.py).

A translation is a UTF-8 JSON source kept apart from the game data: metadata, the glyphs it needs (a glyphs file such
as config/localization/tr/glyphs.json) and its strings, keyed by a stable identifier `<language>.<handle>`: the
language table of the source language and the text handle the game resolves (the index in that table; the sound
banks' `subtitle` ids are such handles). Each string carries the SHA-256 of the source string's slot, never the
source text, so a source holds no game text and still notices a different game version.

  {"format": 1, "kind": "r3hd-translation", "id": "tr.example", "name": "...", "version": "0.1.0",
   "authors": [...], "license": "...", "description": "...",
   "language": {"source": "en", "target": "tr", "name": "Türkçe"},
   "target": {"title_id": "5841123F", "releases": ["x360-xbla-5841123F-v1"], "min_port_version": "0.34.0"},
   "glyphs": "glyphs.json",
   "strings": {"en.471": {"source_sha256": "<64 hex>", "text": "...", "note": "optional"}}}

usage:
  r3hd_loc.py catalog [--lang en] [--out FILE]   the language table: handle, id, offset, slot hash, capacity, the
                                                 source text and what shares it (game-derived: keep it private)
  r3hd_loc.py check SOURCE                       validate: keys, duplicates, encoding and glyphs, source drift,
                                                 length (in place / moved / no room), in-band codes, layout warnings
  r3hd_loc.py build SOURCE OUT [--zip]           the mod folder (or OUT.zip), deterministic: same source, same bytes
  r3hd_loc.py preview SOURCE OUT.png [--ids ID,...]  offline picture of the strings drawn with the composed font
                                                 (game-derived: keep it private)
  r3hd_loc.py selftest
Common: --game-dir DIR (else R3HD_GAME_DIR, else the repository layout), --json. Exit 0 ok, 1 errors, 2 refused.
"""
import argparse
import hashlib
import json
import os
import re
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_mods as rm  # noqa: E402

KIND = "r3hd-translation"
# The localization structure of fix.lvl (RE_NOTES "M34"): the pointer at LANG_PTR leads to five language entries
# (u32 pointer to the table, u16 capacity, u16 handles), in this order; table entries are string pointers (offset - REF_BIAS)
# that fix.ptr relocates, 0 for none.
LANG_PTR = 0x58
LANGS = ("fr", "en", "es", "it", "de")
CAPACITY, HANDLES = 0x4ED, 0x4A4   # the two u16 of an entry; the second is the number of handles in use
ID_RE = re.compile(r"^(fr|en|es|it|de)\.(\d{1,4})$")
SUB_RE = rm.SUB_ID_RE   # M35: movie subtitle cues, vs.<language>.<movie>.<n>
TOP = {"format", "kind", "id", "name", "version", "description", "authors", "license", "website", "language",
       "target", "glyphs", "strings", "requires"}
# M35: review state of a string. A source without states (M34) is all approved: it was written by hand.
STATUSES = ("draft", "needs_review", "reviewed", "approved")
ENTRY_KEYS = {"source_sha256", "text", "note", "status", "origin", "review", "context", "review_closed", "rev", "applied",
              "alt"}
# M39: alternatives proposed beside the current text (never applied by a tool; a person picks one into 'final')
ALT_KEYS = {"text", "by", "reason", "kind", "created"}
REVIEW_KEYS = {"by", "verdict", "suggestion", "note", "round"}   # M37: round = the review round number, as text
VERDICTS = ("ok", "change", "question")
# Voice files in the sound banks: Play_VD[r]_<level>_<speaker code>_..
VOICE_RE = re.compile(r"^Play_VDr?_([A-Za-z0-9]+)_([A-Za-z0-9]+)_")
BANK_RE = re.compile(r"\* file (\S+) \* subtitle 0x([0-9a-fA-F]{8})")
# Movie of a subtitle id, only where a hidden run showed it (RE_NOTES M35); others are named by number.
SUB_MOVIES = {42: "menu10.bik"}


def is_sub(sid: str) -> bool:
    return bool(SUB_RE.match(sid))


def sid_key(sid: str):
    """Deterministic order: table strings by handle, then subtitle cues by movie and number."""
    m = ID_RE.match(sid)
    if m:
        return (0, m.group(1), int(m.group(2)), 0)
    m = SUB_RE.match(sid)
    return (1, m.group(1), int(m.group(2)), int(m.group(3)))


def status_of(e: dict) -> str:
    return e.get("status", "approved")
CODE_RE = re.compile(r"\\(?:f\d+:|c\d+:\d+:\d+:|z\d+:|hm?\d+:|j[clr]|l)")
LAYOUT_WARN = 1.15   # a line drawn wider than this times the source's widest line


class Problem(Exception):
    pass


def tables(fix: bytes) -> dict:
    """{language: (table offset, entries)}; refuses a layout other than the shipped one."""
    if len(fix) < LANG_PTR + 4:
        raise Problem("fix.lvl is too short")
    arr = struct.unpack_from(">I", fix, LANG_PTR)[0] + rm.REF_BIAS
    out = {}
    for i, lang in enumerate(LANGS):
        if arr + 8 * i + 8 > len(fix):
            raise Problem("the language list is outside fix.lvl")
        ptr, cap, n = struct.unpack_from(">IHH", fix, arr + 8 * i)
        if (cap, n) != (CAPACITY, HANDLES) or ptr + rm.REF_BIAS + 4 * n > len(fix):
            raise Problem(f"language {lang}: {n} entries at {ptr + rm.REF_BIAS:#x}; not the supported text tables")
        out[lang] = (ptr + rm.REF_BIAS, n)
    return out


def string_at(fix: bytes, lang_tables: dict, sid: str):
    """(offset, slot) of a string id, or a Problem."""
    m = ID_RE.match(sid)
    if not m:
        raise Problem(f"{sid}: an id is <language>.<handle>, e.g. en.471")
    base, n = lang_tables[m.group(1)]
    h = int(m.group(2))
    if h >= n:
        raise Problem(f"{sid}: handle out of range (0..{n - 1})")
    v = struct.unpack_from(">I", fix, base + 4 * h)[0]
    if not v:
        raise Problem(f"{sid}: no string at this handle")
    off = v + rm.REF_BIAS
    try:
        return off, rm.text_slot(fix, off)
    except rm.Refusal as x:
        raise Problem(f"{sid}: {x.detail}")


def game_paths(a):
    ns = argparse.Namespace(home=None, mods_root=None, cache=a.cache, game_dir=a.game_dir)
    p = rm.resolve_paths(ns)
    if a.cache is None:
        p["cache"] = rm.ROOT / "private" / "work" / "loc_cache"
    return p


def voice_context(game: Path) -> dict:
    """{handle: [(level, voice file)]} from the sound banks: an event that plays a voice file names the text handle of
    its subtitle (RE_NOTES M34 / M35). Evidence only; speaker codes are the voice file's own tokens, not names."""
    out = {}
    d = game / "GAMEDATAbin" / "WORLD" / "SOUND"
    for p in sorted(d.glob("*.bnh")) if d.is_dir() else []:
        for f, h in BANK_RE.findall(p.read_text(encoding="latin1")):
            v = int(h, 16)
            if v != 0xFFFFFFFF:
                out.setdefault(v, set()).add((p.stem.lower(), f))
    return {k: sorted(v) for k, v in out.items()}


def catalog_rows(paths, lang: str = "en") -> list:
    """Every translatable string of a language: the table's handles, then the movie subtitle cues. Game-derived."""
    fix = (paths["game"] / "GAMEDATAbin" / "fix.lvl").read_bytes()
    t = tables(fix)
    refs = rm.text_refs(paths["game"])
    voices = voice_context(paths["game"])
    by_loc = {}
    for lg, (base, n) in t.items():
        for h in range(n):
            by_loc[base + 4 * h] = f"{lg}.{h}"
    rows = []
    base, n = t[lang]
    for h in range(n):
        sid = f"{lang}.{h}"
        try:
            off, slot = string_at(fix, t, sid)
        except Problem as x:
            rows.append({"id": sid, "kind": "text", "handle": h, "problem": str(x)})
            continue
        end = slot.index(b"\0")
        shared = sorted(by_loc.get(loc, f"@{loc:#x}") for loc in refs.get(off, []) if by_loc.get(loc) != sid)
        v = voices.get(h, [])
        rows.append({"id": sid, "kind": "text", "handle": h, "offset": off, "capacity": len(slot) - 1,
                     "slot_sha256": rm.sha256_bytes(slot), "source_sha256": rm.sha256_bytes(slot),
                     "text": slot[:end].decode("cp1252", "replace"), "shared_with": shared,
                     "category": "voiced line" if v else "",
                     "levels": sorted({lv for lv, _ in v}),
                     "speakers": sorted({m.group(2) for _, f in v for m in [VOICE_RE.match(f)] if m}),
                     "voice_files": [f for _, f in v][:8]})
    p = paths["game"] / rm.SUB_FILE
    if p.is_file():
        sub = rm.parse_vs_sub(p.read_bytes())
        for sid, i in sub["ids"].items():
            lg, movie, start, end_ms, _index, _raw = sub["cues"][i]
            if lg != lang:
                continue
            rows.append({"id": sid, "kind": "subtitle", "movie": movie, "movie_file": SUB_MOVIES.get(movie, ""),
                         "start_ms": start, "end_ms": end_ms, "source_sha256": rm.sub_hash(sub, i),
                         "bytes": len(sub["strings"][i]), "text": sub["strings"][i].decode("cp1252", "replace"),
                         "category": "movie subtitle", "levels": [], "speakers": [], "voice_files": []})
    return rows


def cmd_catalog(paths, lang: str, out):
    rows = catalog_rows(paths, lang)
    doc = {"note": "game-derived: keep it private", "language": lang, "entries": rows}
    if out:
        Path(out).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"language": lang, "entries": len(rows), "out": str(out)}
    return doc


def load_source(path: Path) -> dict:
    def pairs(items):
        keys = [k for k, _ in items]
        dup = {k for k in keys if keys.count(k) > 1}
        if dup:
            raise Problem(f"duplicate keys {sorted(dup)}")
        return dict(items)
    raw = path.read_bytes()
    try:
        src = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs)
    except UnicodeDecodeError:
        raise Problem("the source is not UTF-8")
    except ValueError as x:
        raise Problem(f"the source is not JSON: {x}")
    if not isinstance(src, dict) or src.get("kind") != KIND or src.get("format") != 1:
        raise Problem(f"not a format-1 {KIND} source")
    unknown = set(src) - TOP
    if unknown:
        raise Problem(f"unknown keys {sorted(unknown)}")
    lang = src.get("language")
    if not isinstance(lang, dict) or lang.get("source") not in LANGS or not isinstance(lang.get("target"), str) \
            or not re.match(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$", lang["target"]):
        raise Problem("'language' needs 'source' (fr en es it de) and 'target' (a language tag such as tr)")
    if not isinstance(src.get("strings"), dict) or not src["strings"]:
        raise Problem("'strings' must be a non-empty object")
    for sid, e in src["strings"].items():
        m = ID_RE.match(sid) or SUB_RE.match(sid)
        if not m or m.group(1) != lang["source"]:
            raise Problem(f"{sid}: ids are {lang['source']}.<handle> (the source language's table) or "
                          f"vs.{lang['source']}.<movie>.<cue> (a movie subtitle)")
        if not isinstance(e, dict) or set(e) - ENTRY_KEYS \
                or not isinstance(e.get("text"), str) or not e["text"] \
                or not isinstance(e.get("source_sha256"), str) or not re.match(r"^[0-9a-f]{64}$", e["source_sha256"]):
            raise Problem(f"{sid}: needs 'source_sha256' (64 hex digits) and a non-empty 'text'"
                          f" (other keys: {', '.join(sorted(ENTRY_KEYS - {'source_sha256', 'text'}))})")
        if any(ord(c) < 0x20 for c in e["text"]):
            raise Problem(f"{sid}: a control character or a real line break in the text (the game's line break is \\l)")
        if status_of(e) not in STATUSES:
            raise Problem(f"{sid}: status {e.get('status')!r} (one of {', '.join(STATUSES)})")
        for k in ("note", "origin", "context", "review_closed", "rev", "applied"):
            if k in e and not isinstance(e[k], str):
                raise Problem(f"{sid}: '{k}' must be a text")
        r = e.get("review")
        if r is not None and (not isinstance(r, dict) or set(r) - REVIEW_KEYS or r.get("verdict") not in VERDICTS
                              or not all(isinstance(r.get(k, ""), str) for k in REVIEW_KEYS - {"verdict"})):
            raise Problem(f"{sid}: 'review' needs a verdict ({', '.join(VERDICTS)}) and text fields "
                          f"{', '.join(sorted(REVIEW_KEYS - {'verdict'}))}")
        a = e.get("alt")
        if a is not None and (not isinstance(a, list) or not all(
                isinstance(x, dict) and not set(x) - ALT_KEYS and isinstance(x.get("text"), str) and x["text"]
                and not any(ord(c) < 0x20 for c in x["text"]) and all(isinstance(v, str) for v in x.values())
                for x in a)):
            raise Problem(f"{sid}: 'alt' is a list of alternatives, each with a non-empty 'text' and text fields "
                          f"{', '.join(sorted(ALT_KEYS - {'text'}))}")
    return src


def glyph_overrides(src: dict, base: Path) -> list:
    g = src.get("glyphs")
    if g is None:
        return []
    if not isinstance(g, str) or not re.match(r"^[A-Za-z0-9_.-]+\.json$", g) or ".." in g:
        raise Problem("'glyphs' names a glyphs file beside the source")
    doc = json.loads((base / g).read_text(encoding="utf-8"))
    breve = doc.get("breve")
    out = []
    for o in doc["glyphs"]:
        o = json.loads(json.dumps(o))
        for ly in o["layers"]:
            if ly.pop("breve", None):
                ly["bitmap"] = list(breve)
        out.append(o)
    return out


def selected(src: dict, include) -> list:
    """The ids a build takes: those whose status is in `include` (None = every status), in deterministic order."""
    return sorted((s for s, e in src["strings"].items() if include is None or status_of(e) in include), key=sid_key)


def read_vs_sub(paths) -> dict:
    p = paths["game"] / rm.SUB_FILE
    if not p.is_file():
        raise Problem(f"{rm.SUB_FILE} is missing")
    return rm.parse_vs_sub(p.read_bytes())


def manifest_of(src: dict, base: Path, paths, include=("approved",)) -> dict:
    """The mod manifest a source builds (texts resolved against the person's game data). `include`: the statuses
    taken (default approved only; None = all, for a private development build)."""
    fix = (paths["game"] / "GAMEDATAbin" / "fix.lvl").read_bytes()
    t = tables(fix)
    texts, subs = [], []
    ids = selected(src, include)
    if not ids:
        raise Problem("no string to build: none has a selected status (approve strings, or a private development build "
                      "with --allow-unapproved)")
    sub = read_vs_sub(paths) if any(is_sub(s) for s in ids) else None
    for sid in ids:
        e = src["strings"][sid]
        if is_sub(sid):
            i = sub["ids"].get(sid)
            if i is None or rm.sub_hash(sub, i) != e["source_sha256"]:
                raise Problem(f"{sid}: the source subtitle differs from the one translated (another game version?)")
            subs.append({"type": "subtitle", "id": sid, "source_sha256": e["source_sha256"], "text": e["text"]})
            continue
        off, slot = string_at(fix, t, sid)
        if rm.sha256_bytes(slot) != e["source_sha256"]:
            raise Problem(f"{sid}: the source string differs from the one translated (another game version?)")
        texts.append({"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": off, "slot_sha256": e["source_sha256"],
                      "text": e["text"]})
    m = {"format": 1, "id": src["id"], "name": src["name"], "version": src["version"]}
    for k in ("description", "authors", "license", "website"):
        if k in src:
            m[k] = src[k]
    m["target"] = src["target"]
    if src.get("requires"):
        m["requires"] = src["requires"]
    m["overrides"] = glyph_overrides(src, base) + texts + subs   # texts and subtitles in the order of selected()
    return m


def text_width(enc: bytes, recs) -> list:
    """Drawn width of each line (sum of glyph widths; in-band codes skipped)."""
    s = enc.decode("latin1")
    s = CODE_RE.sub(lambda mo: "\n" if mo.group() == "\\l" else "", s)
    return [sum(recs[ord(c)][3] for c in line if recs[ord(c)][7]) for line in s.split("\n")]


def codes_of(b: bytes) -> list:
    """The in-band codes a string must keep (line breaks may change)."""
    return sorted(c for c in CODE_RE.findall(b.decode("latin1")) if c != "\\l")


def compare_layout(sid: str, orig: bytes, enc: bytes, recs_orig, recs_new) -> tuple:
    """(errors, warnings) of one translated string against its source: in-band codes, widest line, line count."""
    errors, warnings = [], []
    a, b = codes_of(orig), codes_of(enc)
    if a != b:
        errors.append(f"{sid}: in-band codes differ from the source ({' '.join(a) or 'none'} vs {' '.join(b) or 'none'})"
                      " - button glyphs, colours and alignment must be kept")
    wo, wn = text_width(orig, recs_orig), text_width(enc, recs_new)
    if max(wn) > LAYOUT_WARN * max(wo) and max(wn) > 40:
        warnings.append(f"{sid}: widest line {max(wn)} px against {max(wo)} in the source"
                        f" (+{100 * max(wn) // max(max(wo), 1) - 100}%); the game does not wrap: add \\l or shorten")
    if len(wn) != len(wo):
        warnings.append(f"{sid}: {len(wn)} lines against {len(wo)} in the source")
    return errors, warnings


def cmd_check(paths, source: Path, include=("approved",), src=None):
    """Validates what a build with `include` would take (default the approved strings)."""
    src = src if src is not None else load_source(source)
    errors, warnings = [], []
    try:
        m = manifest_of(src, source.parent, paths, include)
        rm.parse_manifest({"mod.json": json.dumps(m).encode()})
    except (Problem, rm.Refusal) as x:
        return {"errors": [getattr(x, "detail", str(x))], "warnings": [], "strings": len(src["strings"])}
    fix = (paths["game"] / "GAMEDATAbin" / "fix.lvl").read_bytes()
    font = rm.read_font(fix)
    if font is None:
        return {"errors": ["the game's font is not the supported one"], "warnings": [], "strings": len(src["strings"])}
    glyphs = rm.glyph_chars(m) | rm.required_glyphs(m, {**paths, "mods": rm.ROOT / "private" / "play" / "mods"})
    recs = list(font["ray"])
    for o in m["overrides"]:
        if o["type"] == "glyph":
            recs[rm.GLYPH_CODES[o["char"]]] = (0, 0, o["height"], o["width"], 1, o["descent"], 0, 1)
    moved = 0
    texts = [o for o in m["overrides"] if o["type"] == "text"]
    subs = [o for o in m["overrides"] if o["type"] == "subtitle"]
    sids = [s for s in selected(src, include) if not is_sub(s)]
    sub = read_vs_sub(paths) if subs else None
    for sid, o in list(zip(sids, texts)) + [(o["id"], o) for o in subs]:
        try:
            enc = rm.encode_text(o["text"], glyphs, font["defined"])
        except rm.Refusal as x:
            errors.append(f"{sid}: {x.detail}")
            continue
        if o["type"] == "text":
            slot = rm.text_slot(fix, o["offset"])
            orig = slot[:slot.index(b"\0")]
            if len(enc) + 1 > len(slot):
                moved += 1
        else:
            orig = sub["strings"][sub["ids"][sid]]
        e, w = compare_layout(sid, orig, enc, font["ray"], recs)
        errors += e
        warnings += w
    growth = 0
    if not errors:
        # M36: a compile refusal names a file offset; the translator needs the id ("en.471: ... the string at N").
        at = {o["offset"]: sid for sid, o in zip(sids, texts)}

        def named(detail):
            mo = re.search(r"the string at (\d+)", detail)
            return f"{at[int(mo.group(1))]}: {detail}" if mo and int(mo.group(1)) in at else detail
        try:
            rm.compile_texts(texts, paths, glyphs, font["defined"])
        except rm.Refusal as x:
            errors.append(named(x.detail))
        try:
            if subs:
                (p, off, data, _), = rm.compile_subtitles(subs, paths, glyphs, font["defined"])
                growth = max(0, off + len(data) - p.stat().st_size)
        except rm.Refusal as x:
            errors.append(x.detail)
    res = {"errors": errors, "warnings": warnings, "strings": len(texts), "subtitles": len(subs), "moved": moved,
           "glyphs": "".join(sorted(rm.glyph_chars(m)))}
    if growth:   # M36: the table grows (needs port 0.36.0 or newer)
        res["subtitle_growth"] = {"bytes": growth, "limit": rm.SUB_MAX_GROW, "needs_port": rm.SUB_GROW_PORT}
    return res


def deterministic_zip(folder: Path, out: Path):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                zi = zipfile.ZipInfo(p.relative_to(folder).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                zi.external_attr = 0o644 << 16
                zi.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(zi, p.read_bytes())


def dev_variant(src: dict) -> dict:
    """M35: a private development build of unapproved text: another mod id, a marked name and version, so it is never
    mistaken for (or replaces) the approved mod."""
    src = dict(src)
    src["id"] = src["id"][:59] + ".dev" if not src["id"].endswith(".dev") else src["id"]
    src["name"] = (src["name"][:56] + " (DEV: unreviewed text)")   # M37: within the manifest's 80 characters
    src["version"] = src["version"].split("+")[0].split("-")[0] + "-dev"
    # M37: the package says it too, for anyone who sees only the Mods page or the manifest.
    src["description"] = ("NOT FINAL - development preview with unreviewed (draft / machine-translated) text; not a "
                          "release, do not share. " + src.get("description", ""))[:2000]
    return src


def cmd_build(paths, source: Path, out: Path, as_zip: bool, allow_unapproved=False):
    src = load_source(source)
    include = None if allow_unapproved else ("approved",)
    if allow_unapproved:
        src = dev_variant(src)
    res = cmd_check(paths, source, include, src)
    if res["errors"]:
        raise Problem("; ".join(res["errors"]))
    m = manifest_of(src, source.parent, paths, include)
    data = (json.dumps(m, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    folder = out.with_suffix("") if as_zip else out
    if folder.exists() and any(folder.iterdir()):
        if not (folder / "mod.json").is_file() or {p.name for p in folder.iterdir()} != {"mod.json"}:
            raise Problem(f"{folder} exists and is not a previous build")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "mod.json").write_bytes(data)
    skipped = len(src["strings"]) - len(selected(src, include))
    result = {"mod": str(folder), "id": m["id"], "overrides": len(m["overrides"]), "sha256": hashlib.sha256(data).hexdigest(),
              "strings": len(selected(src, include)), "not_approved_left_out": skipped, "warnings": res["warnings"]}
    if allow_unapproved:
        result["note"] = "development build with unreviewed text: keep it private, do not share it"
    if as_zip:
        z = out if out.suffix.lower() == ".zip" else out.with_suffix(".zip")
        deterministic_zip(folder, z)
        result["zip"] = str(z)
        result["zip_sha256"] = hashlib.sha256(z.read_bytes()).hexdigest()
    return result


def cmd_preview(paths, source: Path, out: Path, ids):
    src = load_source(source)
    m = manifest_of(src, source.parent, paths, None)
    files = {"mod.json": json.dumps(m).encode()}
    fix = (paths["game"] / "GAMEDATAbin" / "fix.lvl").read_bytes()
    font = rm.read_font(fix)
    recs = list(font["ray"])
    hits = rm.resolve_texture(paths["game"], {"entry": rm.FONT["atlas"], "bundles": [rm.FONT["bundle"]]})
    bhf, e, w, h, fmt = hits[0]
    with open(bhf.with_suffix(".btf"), "rb") as f:
        f.seek(e[2])
        b0 = f.read(e[1])
        f.seek(e[4])
        b1 = f.read(e[3])
    if rm.glyph_chars(m):
        for path, off, data, what in rm.compile_glyphs(m, files, paths):
            if what.endswith("#base"):
                b0 = data
            elif what.startswith("glyph ") and what.endswith(f"@{rm.FONT['fontray'][0]:#x}"):
                recs[rm.GLYPH_CODES[what.split()[1][0]]] = struct.unpack(">6H2B", data)
    atlas = rm.decode_level(w, h, rm.level_rows((b0, b1), rm.layout(w, h, fmt)[2][0], fmt), fmt)
    glyphs = rm.glyph_chars(m)
    order = sorted(src["strings"], key=sid_key)
    lines = []
    for sid in order:
        if ids and sid not in ids:
            continue
        enc = rm.encode_text(src["strings"][sid]["text"], glyphs, None)
        s = CODE_RE.sub(lambda mo: "\n" if mo.group() == "\\l" else "", enc.decode("latin1"))
        lines += s.split("\n")
    if not lines:
        raise Problem("nothing to draw")
    line_h, pad = 56, 8
    widths = [sum(recs[ord(c)][3] + 1 for c in ln if recs[ord(c)][7]) for ln in lines]
    W, H = max(widths) + 2 * pad, line_h * len(lines) + 2 * pad
    img = bytearray(bytes((40, 40, 90, 255)) * (W * H))
    for li, ln in enumerate(lines):
        x, base_y = pad, pad + li * line_h + 40   # baseline
        for c in ln:
            gx, gy, gh, gw, _ps, desc, _bm, df = recs[ord(c)]
            if not df:
                continue
            desc = desc - 0x10000 if desc >= 0x8000 else desc
            top = base_y + desc - gh
            for j in range(gh):
                for i in range(gw):
                    a = atlas[((gy + j) * w + gx + i) * 4 + 3]
                    if a and 0 <= top + j < H:
                        k = ((top + j) * W + x + i) * 4
                        for ch in range(3):
                            img[k + ch] = (img[k + ch] * (255 - a) + 255 * a) // 255
            x += gw + 1
        for i in range(pad, W - pad):   # the baseline, dim
            k = (base_y * W + i) * 4
            img[k:k + 3] = bytes(min(255, v + 40) for v in img[k:k + 3])
    out.write_bytes(rm.write_png(W, H, bytes(img)))
    return {"out": str(out), "lines": len(lines), "size": [W, H], "note": "game-derived: keep it private"}


# ---------------------------------------------------------------------------------------------------------------

def selftest() -> int:
    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ' :: ' + str(detail)}")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        dup = td / "dup.json"
        dup.write_text('{"format": 1, "kind": "r3hd-translation", "strings": {"en.1": {}, "en.1": {}}}', encoding="utf-8")
        try:
            load_source(dup)
            check("source: duplicate keys refused", False)
        except Problem as x:
            check("source: duplicate keys refused", "duplicate" in str(x), x)
        bad = td / "bad.json"
        bad.write_bytes('{"format": 1, "kind": "r3hd-translation"}'.encode("utf-16"))
        try:
            load_source(bad)
            check("source: not UTF-8 refused", False)
        except Problem as x:
            check("source: not UTF-8 refused", "UTF-8" in str(x), x)
        base = {"format": 1, "kind": KIND, "id": "t.x", "name": "x", "version": "1.0.0",
                "language": {"source": "en", "target": "tr"}, "target": {}, "strings": {}}
        for label, strings in (("an id of another language", {"fr.1": {"source_sha256": "0" * 64, "text": "x"}}),
                               ("an id that is not a handle", {"en.x": {"source_sha256": "0" * 64, "text": "x"}}),
                               ("a missing hash", {"en.1": {"text": "x"}}),
                               ("an empty text", {"en.1": {"source_sha256": "0" * 64, "text": ""}})):
            p = td / "s.json"
            p.write_text(json.dumps(dict(base, strings=strings)), encoding="utf-8")
            try:
                load_source(p)
                check(f"source: {label} refused", False)
            except Problem:
                check(f"source: {label} refused", True)
        # tables(): a synthetic localization structure
        fix = bytearray(0x400)
        struct.pack_into(">I", fix, LANG_PTR, 0x100 - rm.REF_BIAS)
        for i in range(5):
            struct.pack_into(">IHH", fix, 0x100 + 8 * i, 0x40, CAPACITY, HANDLES)
        try:
            tables(bytes(fix))
            check("tables: entries outside the file are refused", False)
        except Problem:
            check("tables: entries outside the file are refused", True)
        recs = [(0, 0, 10, 10, 1, 0, 0, 1)] * 256
        check("layout: widths per line, codes skipped", text_width(b"ab\\lc\\jcd", recs) == [20, 20])
        f = td / "fold"
        f.mkdir()
        (f / "mod.json").write_bytes(b"{}\n")
        deterministic_zip(f, td / "a.zip")
        (td / "a.zip").rename(td / "a1.zip")
        os.utime(f / "mod.json", (0, 0))
        deterministic_zip(f, td / "a.zip")
        check("build: the zip does not depend on file times", (td / "a.zip").read_bytes() == (td / "a1.zip").read_bytes())
    n = results.count(False)
    print(f"R3HD_LOC_SELFTEST {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}")
    return 1 if n else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["catalog", "check", "build", "preview", "selftest"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--lang", default="en", choices=LANGS)
    ap.add_argument("--out")
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--allow-unapproved", action="store_true",
                    help="build: a private development build of every status (another id, marked DEV)")
    ap.add_argument("--ids", default="")
    ap.add_argument("--game-dir")
    ap.add_argument("--cache")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    paths = game_paths(a)
    code = 0
    try:
        if a.cmd == "catalog":
            r = cmd_catalog(paths, a.lang, a.out)
        elif a.cmd == "check" and len(a.args) == 1:
            r = cmd_check(paths, Path(a.args[0]))
            code = 1 if r["errors"] else 0
        elif a.cmd == "build" and len(a.args) == 2:
            r = cmd_build(paths, Path(a.args[0]), Path(a.args[1]), a.zip, a.allow_unapproved)
        elif a.cmd == "preview" and len(a.args) == 2:
            r = cmd_preview(paths, Path(a.args[0]), Path(a.args[1]), [i for i in a.ids.split(",") if i])
        else:
            raise Problem(f"usage: see {Path(__file__).name} --help")
        r = {"result": "ok" if not code else "errors", **r}
    except (Problem, rm.Refusal) as x:
        r, code = {"result": "refused", "detail": getattr(x, "detail", str(x))}, 2
    except (OSError, ValueError, KeyError, TypeError, AttributeError, struct.error) as x:  # M34 review: no traceback
        r, code = {"result": "refused", "detail": f"{type(x).__name__}: {x}"}, 2
    sys.stdout.buffer.write((json.dumps(r, indent=1, ensure_ascii=a.json, default=str) + "\n").encode("utf-8"))
    return code


if __name__ == "__main__":
    sys.exit(main())
