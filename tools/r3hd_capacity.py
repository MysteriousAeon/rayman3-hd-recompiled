#!/usr/bin/env python3
"""M39: how much room a translation has in the game's text resources: measured, reproducible, without game text.

The main text table (fix.lvl) and the movie subtitles (VS.sub) are measured separately, and the drawn layout apart
from both: a translation that packs is not yet a readable one.

  r3hd_capacity.py report SOURCE [--include all|approved] [--use-alt] [--json OUT.json] [--md OUT.md]
      one translation source (tr.json of a workspace, or any r3hd-translation source) against the person's game data:
        main table - the English table's allocation (slots, used, free padding), the overridden slots, English and
                     replacement bytes, net growth, the capacity left under each packer, fragmentation before and
                     after, the M34 and the M38 compacting packer (success or the refusal, its string, its cause),
                     relocated strings, rewritten pointers, pointers of the other language tables involved;
        subtitles  - VS.sub size, rebuilt size, growth against its limit, cue warnings (bytes, lines, reading speed);
        layout     - lines drawn wider than the English and changed line counts (warnings only);
        glyphs     - the characters the translation needs beyond the game's font.
      --use-alt: each entry's latest alternative (M39 'alt') instead of its text (what a reviewer may choose).
  r3hd_capacity.py project SOURCE [--cases NAME:S:R,...] [--groups G,..] [--break-even] [--json F] [--md F]
      a MODEL of a fuller translation (SOURCE in a workspace): per case, every existing text scaled to S x its bytes
      (1 = as it is) and every untranslated string of the chosen groups (default: everything a translation would
      change) a synthetic text of R x its English bytes. Default cases low 1.0:0.95, central 1.0:1.05, high 1.1:1.2.
      Only the packers run (in memory; nothing is built or written into a workspace). --break-even: the largest factor
      applied to both for which the compacting packer still packs. A model, never a build.
  r3hd_capacity.py compare A.json B.json     two reports side by side (ids and numbers)
  r3hd_capacity.py selftest

The reports hold ids, offsets and byte counts only: no English and no Turkish text. Keep them beside the workspace's
private files all the same (offsets and ids describe the person's game data). Common: --game-dir DIR.
Exit 0 ok (the translation packs), 1 it does not (refusal recorded in the report), 2 refused (bad input).
"""
import argparse
import bisect
import json
import re
import struct
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_loc as loc  # noqa: E402
import r3hd_mods as rm  # noqa: E402

KIND = "r3hd-capacity-report"
FORMAT = 1
PACKERS = ("m34", "compact")
READ_CPS = 17.0          # subtitle reading speed above which a cue is flagged (characters per second, common guidance)
# The groups a full translation would change (r3hd_trwork categories); credits, development labels, PS2 messages and
# glyph-only strings stay as they are unless asked for (--groups).
TRANSLATE_GROUPS = ("menu", "system", "tutorial", "bonus_help", "album", "dialogue", "subtitle")
POINTER_RE = re.compile(r"^pointer@(\d+)->(\d+)$")


class Problem(Exception):
    pass


# ---------------------------------------------------------------------------------------------------------------
# The game's tables

def owners(fix: bytes) -> dict:
    """{pointer location: 'lang.handle'} of every entry of the five language tables."""
    out = {}
    for lang, (base, n) in loc.tables(fix).items():
        for h in range(n):
            out[base + 4 * h] = f"{lang}.{h}"
    return out


def baseline(paths, lang="en") -> dict:
    """The language table as shipped: its strings' slots (string, NUL, 4-alignment padding), used and free bytes."""
    fix = (paths["game"] / "GAMEDATAbin" / "fix.lvl").read_bytes()
    t = loc.tables(fix)
    refs = rm.text_refs(paths["game"])
    own = owners(fix)
    base, n = t[lang]
    offs = {}
    empty = 0
    for h in range(n):
        try:
            off, slot = loc.string_at(fix, t, f"{lang}.{h}")
        except loc.Problem:
            empty += 1
            continue
        offs.setdefault(off, slot)
    slots = sum(len(s) for s in offs.values())
    used = sum(s.index(b"\0") + 1 for s in offs.values())
    shared = sum(1 for off in offs if any(own.get(x, "").split(".")[0] != lang for x in refs.get(off, [])))
    lo = min(offs) if offs else 0
    hi = max(off + len(s) for off, s in offs.items()) if offs else 0
    every = set()
    for lg, (b, k) in t.items():
        for h in range(k):
            v = struct.unpack_from(">I", fix, b + 4 * h)[0]
            if v:
                every.add(v + rm.REF_BIAS)
    return {"language": lang, "handles": n, "handles_without_string": empty, "strings": len(offs),
            "slot_bytes": slots, "used_bytes": used, "free_padding_bytes": slots - used,
            "slack_percent": round(100 * (slots - used) / slots, 2) if slots else 0.0,
            "shared_with_other_languages": shared, "extent": {"from": lo, "to": hi, "bytes": hi - lo},
            "strings_all_languages": len(every), "pointers_in_fix_ptr": sum(len(v) for v in refs.values())}


# ---------------------------------------------------------------------------------------------------------------
# Main table

def free_chunks(blocks: list, minimum=4) -> dict:
    """Free space in [(offset, bytes)] blocks (adjacent blocks join): a chunk is a run of zero bytes after a string's
    terminator, from the next 4-aligned offset (where a packer could start a string) to the run's end."""
    blocks = sorted(blocks)
    merged = []
    for off, data in blocks:
        if merged and merged[-1][0] + len(merged[-1][1]) == off:
            merged[-1][1] += data
        else:
            merged.append([off, bytearray(data)])
    sizes = []
    for off, data in merged:
        i, n = 0, len(data)
        while i < n:
            if data[i]:
                j = data.find(b"\0", i)
                i = n if j < 0 else j + 1   # past the terminator
                continue
            j = i
            while j < n and not data[j]:
                j += 1
            start = rm._align(off + i, 4) - off
            if j - start >= minimum:
                sizes.append(j - start)
            i = j
    return {"chunks": len(sizes), "bytes": sum(sizes), "largest": max(sizes, default=0)}


def pin_test(refs: dict):
    """(offset, slot end) -> (pinned, pointed into) as the compacting packer decides it (r3hd_mods.pack_compact): a
    slot pointed into or holding a pointer location, or a string no table pointer reaches, cannot move."""
    pointed_inside = rm._pointed_inside(refs)
    locs = sorted(x for v in refs.values() for x in v)

    def test(off, end):
        i = bisect.bisect_left(locs, off - 3)
        inside = pointed_inside(off, end) or (i < len(locs) and locs[i] < end)
        return inside or not refs.get(off), inside
    return test


def compact_runs(items: list, refs: dict) -> dict:
    """The compacting packer's view (r3hd_mods.pack_compact, M38): pinned strings and runs of movable slots, their
    capacity and the aligned bytes the movable strings need. Mirrors pack_compact's first pass; the selftest checks it
    against the packer's own refusal numbers."""
    test = pin_test(refs)
    runs, cur, pinned, pinned_too_long = [], None, [], []
    for off, slot, enc in sorted(items, key=lambda it: it[0]):
        end, fits = off + len(slot), len(enc) + 1 <= len(slot)
        pin, inside = test(off, end)
        if pin:
            pinned.append(off)
            if not fits:
                pinned_too_long.append(off)
            tail = rm._align(off + len(enc) + 1, 4)
            cur = [tail, end, []] if not inside and tail < end else None
            if cur:
                runs.append(cur)
            continue
        if cur is not None and cur[1] == off:
            cur[1] = end
            cur[2].append((off, enc))
        else:
            cur = [off, end, [(off, enc)]]
            runs.append(cur)
    cap = sum(hi - lo for lo, hi, _ in runs)
    need = sum(rm._align(len(e) + 1, 4) for _, _, s in runs for _, e in s)
    return {"runs": len(runs), "largest_run": max((hi - lo for lo, hi, _ in runs), default=0), "capacity": cap,
            "need": need, "headroom": cap - need, "pinned": len(pinned), "pinned_too_long": pinned_too_long,
            "movable": sum(len(s) for _, _, s in runs)}


def m34_free(items: list, refs: dict) -> dict:
    """The M34 packer's free list for this mod (tails after texts that stay, whole slots of texts that move)."""
    pointed_inside = rm._pointed_inside(refs)
    free = []
    for off, slot, enc in items:
        if pointed_inside(off, off + len(slot)):
            continue
        if len(enc) + 1 > len(slot):
            free.append((off, off + len(slot)))
        else:
            start = rm._align(off + len(enc) + 1, 4)
            if start < off + len(slot):
                free.append((start, off + len(slot)))
    merged = []
    for lo, hi in sorted(free):
        if merged and merged[-1][1] == lo:
            merged[-1][1] = hi
        else:
            merged.append([lo, hi])
    sizes = [hi - lo for lo, hi in merged]
    longer = [len(enc) + 1 for off, slot, enc in items if len(enc) + 1 > len(slot)]
    return {"chunks": len(sizes), "bytes": sum(sizes), "largest": max(sizes, default=0),
            "longer_strings": len(longer), "longer_need": sum(rm._align(n, 4) for n in longer),
            "largest_longer": max(longer, default=0)}


def classify(detail: str, need: int, cap: int) -> str:
    if "pointed into" in detail:
        return "pinned_slot (a pointer points inside the slot: the string cannot move)"
    if "no table pointer" in detail:
        return "pinned_slot (no table pointer reaches the string: it cannot move)"
    if need > cap:
        return "total_capacity (the mod's movable slots are too small in total)"
    return "fragmentation"


def run_packer(paths, texts, glyphs, defined, mode, refs, own, lang, at_id) -> dict:
    try:
        ranges, moved, used = rm.compile_texts(texts, paths, glyphs, defined, packer=mode)
    except rm.Refusal as x:
        mo = re.search(r"the string at (\d+)", x.detail)
        sid = at_id.get(int(mo.group(1))) if mo else None
        return {"ok": False, "code": x.code, "string": sid, "detail": x.detail}
    ptrs = [(int(m.group(1)), int(m.group(2))) for _, _, _, what in ranges for m in [POINTER_RE.match(what)] if m]
    by_loc = {x: off for off, v in refs.items() for x in v}
    moved_from = sorted({by_loc[x] for x, _ in ptrs if x in by_loc})
    other = sorted({own.get(x, f"@{x}") for x, _ in ptrs if own.get(x, "?").split(".")[0] != lang})
    texts_ranges = [(off, data) for _, off, data, what in ranges if what.startswith("text@")]
    return {"ok": True, "packer": used, "ranges": len(ranges), "text_ranges": len(texts_ranges),
            "relocated_strings": len(moved_from), "rewritten_pointers": len(ptrs),
            "other_language_pointers": len(other), "other_language_handles": other[:40],
            "free_after": free_chunks(texts_ranges),
            "relocated_ids": sorted((at_id.get(o, f"@{o}") for o in moved_from), key=_id_key)}


def _id_key(s):
    try:
        return loc.sid_key(s)
    except Exception:   # noqa: BLE001 - '@offset' names
        return (9, s)


def table_capacity(paths, texts: list, glyphs, defined, lang="en", at_id=None) -> dict:
    """Every number of the main table for one mod's text overrides (r3hd_mods format-1 'text' objects)."""
    p = paths["game"] / "GAMEDATAbin" / "fix.lvl"
    fix = p.read_bytes()
    refs = rm.text_refs(paths["game"])
    try:
        own = owners(fix)
    except loc.Problem:
        own = {}
    at_id = at_id or {}
    items, problems = [], []
    for o in texts:
        slot = rm.text_slot(fix, o["offset"])
        try:
            enc = rm.encode_text(o["text"], glyphs, defined)
        except rm.Refusal as x:
            problems.append({"string": at_id.get(o["offset"], o["offset"]), "code": x.code, "detail": x.detail})
            continue
        items.append((o["offset"], slot, enc))
    eng = sum(s.index(b"\0") + 1 for _, s, _ in items)
    rep = sum(len(e) + 1 for _, _, e in items)
    slots = sum(len(s) for _, s, _ in items)
    res = {"strings": len(texts), "encodable": len(items), "encoding_problems": problems,
           "slot_bytes": slots, "english_bytes": eng, "replacement_bytes": rep, "net_growth": rep - eng,
           "in_place": sum(1 for _, s, e in items if len(e) + 1 <= len(s)),
           "longer_than_slot": sum(1 for _, s, e in items if len(e) + 1 > len(s)),
           "free_before": free_chunks([(off, s) for off, s, _ in items]),
           "m34_free_list": m34_free(items, refs), "compaction": compact_runs(items, refs)}
    res["compaction"]["pinned_too_long"] = [at_id.get(o, o) for o in res["compaction"]["pinned_too_long"]]
    shared = [o for o, _, _ in items if any(own.get(x, "").split(".")[0] != lang for x in refs.get(o, []))]
    res["shared_with_other_languages"] = len(shared)
    if problems:
        res["packers"] = {m: {"ok": False, "code": "ENCODING", "detail": "see encoding_problems"} for m in PACKERS}
        res["auto"] = res["packers"]["m34"]
        res["verdict"] = "unsupported_glyph_or_format"
        return res
    out = {}
    for mode in PACKERS:
        out[mode] = run_packer(paths, texts, glyphs, defined, mode, refs, own, lang, at_id)
    res["packers"] = out
    if out["m34"]["ok"]:
        res["auto"] = dict(out["m34"])
    elif out["compact"]["ok"]:
        res["auto"] = dict(out["compact"])
    else:
        res["auto"] = {"ok": False, "detail": out["compact"]["detail"]}
    c = res["compaction"]
    if out["m34"]["ok"]:
        res["verdict"] = "packs (M34 packer)" if res["longer_than_slot"] else "packs (every text fits its slot)"
    elif out["compact"]["ok"]:
        res["verdict"] = "packs (M38 compaction; the M34 packer refuses: fragmentation)"
    else:
        res["verdict"] = classify(out["compact"]["detail"], c["need"], c["capacity"])
    return res


# ---------------------------------------------------------------------------------------------------------------
# Subtitles

def subtitle_capacity(paths, subs: list, glyphs, defined) -> dict:
    p = paths["game"] / rm.SUB_FILE
    data = p.read_bytes()
    sub = rm.parse_vs_sub(data)
    size = len(data)
    res = {"vs_sub_bytes": size, "string_section_end": sub["end"], "cues": len(subs), "growth_limit": rm.SUB_MAX_GROW}
    if not subs:
        res.update(rebuilt_bytes=size, growth=0, headroom=rm.SUB_MAX_GROW, ok=True, warnings=[])
        return res
    warnings, eng, rep = [], 0, 0
    for o in subs:
        i = sub["ids"][o["id"]]
        lang, movie, start, end, _, _ = sub["cues"][i]
        enc = rm.encode_text(o["text"], glyphs, defined)
        eng += len(sub["strings"][i])
        rep += len(enc)
        lines = enc.count(b"\\l") + 1
        chars = len(loc.CODE_RE.sub(" ", o["text"]))
        secs = max((end - start) / 1000, 0.001)
        cps = chars / secs
        cps_en = len(loc.CODE_RE.sub(" ", sub["strings"][i].decode("cp1252", "replace"))) / secs
        if len(enc) > rm.SUB_MAX_TEXT:
            warnings.append({"id": o["id"], "warning": f"{len(enc)} bytes (at most {rm.SUB_MAX_TEXT})"})
        if lines > 2:
            warnings.append({"id": o["id"], "warning": f"{lines} lines (the banner was seen with one or two)"})
        if cps > READ_CPS:
            warnings.append({"id": o["id"], "warning": f"{cps:.1f} characters per second (above {READ_CPS:g}; the "
                             f"English {cps_en:.1f})"})
    res.update(english_bytes=eng, replacement_bytes=rep, net_growth=rep - eng, warnings=warnings)
    try:
        (_, off, body, _), = rm.compile_subtitles(subs, paths, glyphs, defined)
        new = max(size, off + len(body))
        res.update(ok=True, rebuilt_bytes=new, growth=new - size, headroom=rm.SUB_MAX_GROW - (new - size),
                   needs_port=rm.SUB_GROW_PORT if new > size else "")
    except rm.Refusal as x:
        res.update(ok=False, code=x.code, detail=x.detail)
    return res


# ---------------------------------------------------------------------------------------------------------------
# A source

def with_alternatives(src: dict) -> tuple:
    """A copy whose entries read their latest alternative (M39 'alt'); the ids that changed."""
    src = dict(src, strings=dict(src["strings"]))
    changed = []
    for sid, e in src["strings"].items():
        alts = e.get("alt") or []
        if alts:
            src["strings"][sid] = dict(e, text=alts[-1]["text"])
            changed.append(sid)
    return src, sorted(changed, key=loc.sid_key)


def measure(paths, src: dict, base: Path, include=None, layout=True) -> dict:
    """The whole report for a source dict (include: statuses built; None = every status, as a preview)."""
    m = loc.manifest_of(src, base, paths, include)
    fix = (paths["game"] / "GAMEDATAbin" / "fix.lvl").read_bytes()
    font = rm.read_font(fix)
    if font is None:
        raise Problem("the game's font is not the supported one")
    glyphs = rm.glyph_chars(m)
    texts = [o for o in m["overrides"] if o["type"] == "text"]
    subs = [o for o in m["overrides"] if o["type"] == "subtitle"]
    ids = [s for s in loc.selected(src, include) if not loc.is_sub(s)]
    at_id = {o["offset"]: sid for sid, o in zip(ids, texts)}
    lang = src["language"]["source"]
    res = {"kind": KIND, "format": FORMAT, "project": src.get("id", ""), "include": "all" if include is None else
           ",".join(include), "strings": len(ids) + len(subs),
           "statuses": {s: sum(1 for x in loc.selected(src, include) if loc.status_of(src["strings"][x]) == s)
                        for s in loc.STATUSES},
           "glyphs": {"added": "".join(sorted(glyphs)),
                      "needed_beyond_font": "".join(sorted({c for o in texts + subs for c in o["text"]
                                                            if c in rm.TURKISH}))},
           "baseline": baseline(paths, lang),
           "main_table": table_capacity(paths, texts, glyphs, font["defined"], lang, at_id),
           "subtitles": subtitle_capacity(paths, subs, glyphs, font["defined"])}
    if layout:
        res["layout"] = layout_warnings(paths, src, base, include)
    return res


def layout_warnings(paths, src, base: Path, include) -> dict:
    """r3hd_loc's drawn-width and line-count checks (warnings: the game never wraps). Independent of packing."""
    fd = tempfile.NamedTemporaryFile("w", suffix=".json", dir=base, delete=False, encoding="utf-8")
    try:
        json.dump(src, fd, ensure_ascii=False)
        fd.close()
        r = loc.cmd_check(paths, Path(fd.name), include, src)
    finally:
        Path(fd.name).unlink(missing_ok=True)
    wide = [w for w in r["warnings"] if "widest line" in w]
    lines = [w for w in r["warnings"] if "lines against" in w]
    return {"wider_than_english": len(wide), "line_count_changed": len(lines),
            "ids_wider": sorted({w.split(":")[0] for w in wide}, key=_id_key),
            "ids_line_count": sorted({w.split(":")[0] for w in lines}, key=_id_key),
            "check_errors": [e.split(":")[0] for e in r["errors"]]}


def synthetic(src: dict, cat: dict, ctx: dict, ratio: float, groups, scale: float = 1.0, caps=None) -> tuple:
    """A MODEL source: untranslated strings of `groups` filled with 'a' x round(ratio x English bytes); with `scale`
    other than 1, every existing text is replaced by 'a' x round(scale x its encoded bytes) too (a later review that
    lengthens or shortens the drafts). `caps` {id: bytes}: pinned strings (they cannot move) stay within their own slot,
    as a translator must keep them. Never written to a workspace or built."""
    out = dict(src, strings=dict(src["strings"]))
    caps = caps or {}

    def size(sid, n):
        return max(1, min(n, caps[sid]) if sid in caps else n)
    if scale != 1.0:
        for sid, e in src["strings"].items():
            n = len(e["text"].encode("cp1254", "replace"))   # Turkish letters are one byte each, as in the game
            keep = sid in caps and n > caps[sid]   # a real text already over its pinned slot stays as it is
            out["strings"][sid] = dict(e, text="a" * (n if keep else size(sid, round(n * scale))))
    added, eng = 0, 0
    for sid, c in cat.items():
        if sid in out["strings"] or not c["text"].strip() or ctx.get(sid, {}).get("group") not in groups:
            continue
        n = len(c["text"].encode("cp1252", "replace"))
        out["strings"][sid] = {"source_sha256": c["source_sha256"], "status": "draft",
                               "text": "a" * size(sid, round(n * ratio))}
        added += 1
        eng += n
    return out, added, eng


def pinned_caps(paths, cat: dict) -> dict:
    """{id: slot bytes} of the table strings the compacting packer would pin (they must fit their own slot)."""
    test = pin_test(rm.text_refs(paths["game"]))
    return {sid: c["capacity"] for sid, c in cat.items()
            if c.get("kind") == "text" and "offset" in c and test(c["offset"], c["offset"] + c["capacity"] + 1)[0]}


def parse_cases(spec: str) -> list:
    """'name:existing_scale:untranslated_ratio,...' -> [(name, scale, ratio)]."""
    out = []
    for item in (x.strip() for x in spec.split(",") if x.strip()):
        p = item.split(":")
        if len(p) != 3:
            raise Problem(f"--cases {item}: name:existing_scale:untranslated_ratio (e.g. central:1.0:1.05)")
        out.append((p[0], float(p[1]), float(p[2])))
    return out


def project(paths, src, base, cat, ctx, cases, groups, break_even=False) -> dict:
    res = {"kind": KIND + "-projection", "format": FORMAT, "model": True,
           "note": "MODEL: untranslated strings replaced by synthetic text of ratio x English bytes and, where the scale "
                   "is not 1, existing texts by synthetic text of scale x their bytes; packers run in memory only; "
                   "not a build and not a translation", "groups": sorted(groups), "cases": []}
    fix = (paths["game"] / "GAMEDATAbin" / "fix.lvl").read_bytes()
    font = rm.read_font(fix)
    caps = pinned_caps(paths, cat)
    over = sorted((sid for sid, e in src["strings"].items() if sid in caps
                   and len(e["text"].encode("cp1254", "replace")) > caps[sid]), key=_id_key)
    res["pinned"] = {"strings": len(caps), "ids": sorted(caps, key=_id_key),
                     "real_texts_over_their_slot": over,
                     "note": "pinned strings cannot move: each must fit its own slot; the model keeps scaled texts "
                             "within it (a real text over its slot is a refusal of its own, listed here)"}
    for name, scale, r in cases:
        s, added, eng = synthetic(src, cat, ctx, r, groups, scale, caps)
        m = measure(paths, s, base, None, layout=False)
        res["cases"].append({"name": name, "existing_scale": scale, "ratio": r, "synthetic_strings": added,
                             "synthetic_english_bytes": eng, "real_strings": len(src["strings"]),
                             "main_table": m["main_table"], "subtitles": m["subtitles"]})
    if break_even:
        lo, hi = 0.5, 3.0

        def packs(x):
            s, _, _ = synthetic(src, cat, ctx, x, groups, x, caps)
            mm = loc.manifest_of(s, base, paths, None)
            texts = [o for o in mm["overrides"] if o["type"] == "text"]
            try:
                rm.compile_texts(texts, paths, rm.glyph_chars(mm), font["defined"], packer="compact")
                return True
            except rm.Refusal:
                return False
        if not packs(lo):
            res["break_even"] = None
        elif packs(hi):
            res["break_even"] = f">={hi}"
        else:
            for _ in range(14):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if packs(mid) else (lo, mid)
            res["break_even"] = round(lo, 3)
        res["break_even_note"] = ("the largest factor f for which the compacting packer still packs when every existing "
                                  "text is f x its bytes and every untranslated string of the groups f x its English")
    return res


# ---------------------------------------------------------------------------------------------------------------
# Output

def markdown(rep: dict) -> str:
    if rep.get("model"):
        lines = ["# Capacity projection (MODEL, not a build)", "", rep["note"], "", f"Groups: {', '.join(rep['groups'])}",
                 "", "| case | existing x | untranslated x | synthetic strings | M34 | compact | need / capacity (movable) | "
                 "headroom | relocated | pointers | VS.sub growth |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for c in rep["cases"]:
            t, s = c["main_table"], c["subtitles"]
            k = t["compaction"]
            lines.append(f"| {c['name']} | {c['existing_scale']} | {c['ratio']} | {c['synthetic_strings']} | "
                         f"{_ok(t['packers']['m34'])} | "
                         f"{_ok(t['packers']['compact'])} | {k['need']} / {k['capacity']} | {k['headroom']} | "
                         f"{t['packers']['compact'].get('relocated_strings', '-')} | "
                         f"{t['packers']['compact'].get('rewritten_pointers', '-')} | {s.get('growth', '-')} |")
        if "pinned" in rep:
            pn = rep["pinned"]
            lines += ["", f"Pinned strings (cannot move, each limited to its own slot): {pn['strings']} "
                      f"({', '.join(pn['ids'])}); real texts already over their slot: "
                      f"{', '.join(pn['real_texts_over_their_slot']) or 'none'}"]
        if "break_even" in rep:
            lines += ["", f"Break-even factor: {rep['break_even']} ({rep['break_even_note']})"]
        return "\n".join(lines) + "\n"
    b, t, s = rep["baseline"], rep["main_table"], rep["subtitles"]
    k, f34 = t["compaction"], t["m34_free_list"]
    lines = [f"# Capacity report: {rep['project']} ({rep['include']}; {rep['strings']} strings)", "",
             "Ids and byte counts only. A packing result says nothing about how the text looks on screen.", "",
             "## Main table (fix.lvl)", "",
             f"- English table: {b['strings']} strings in {b['slot_bytes']} slot bytes; used {b['used_bytes']}, free "
             f"padding {b['free_padding_bytes']} ({b['slack_percent']}%); {b['shared_with_other_languages']} shared "
             "with another language's table.",
             f"- This translation: {t['strings']} strings, {t['slot_bytes']} slot bytes; English {t['english_bytes']} "
             f"-> replacement {t['replacement_bytes']} bytes (net {t['net_growth']:+d}); {t['in_place']} fit their "
             f"slot, {t['longer_than_slot']} longer; {t['shared_with_other_languages']} shared strings.",
             f"- Free space in the overridden slots before (English): {t['free_before']['chunks']} chunks, "
             f"{t['free_before']['bytes']} bytes, largest {t['free_before']['largest']}.",
             f"- M34 packer's free list: {f34['chunks']} chunks, {f34['bytes']} bytes, largest {f34['largest']}; "
             f"{f34['longer_strings']} strings to move need {f34['longer_need']} bytes (largest {f34['largest_longer']}).",
             f"- Compaction: {k['runs']} runs (largest {k['largest_run']}), {k['pinned']} pinned, {k['movable']} "
             f"movable; capacity {k['capacity']}, need {k['need']}, **headroom {k['headroom']} bytes**.", "",
             "| packer | result | relocated strings | rewritten pointers | other-language pointers | free after |",
             "|---|---|---|---|---|---|"]
    for mode in PACKERS:
        r = t["packers"][mode]
        fa = r.get("free_after", {})
        lines.append(f"| {mode} | {_ok(r)} | {r.get('relocated_strings', '-')} | {r.get('rewritten_pointers', '-')} | "
                     f"{r.get('other_language_pointers', '-')} | "
                     + (f"{fa['chunks']} chunks, {fa['bytes']} B, largest {fa['largest']}" if fa else "-") + " |")
    lines += ["", f"**Verdict:** {t['verdict']}", "", "## Subtitles (VS.sub)", "",
              f"- VS.sub {s['vs_sub_bytes']} bytes; {s['cues']} cues replaced; rebuilt {s.get('rebuilt_bytes', '-')} "
              f"bytes; growth {s.get('growth', '-')} of at most {s['growth_limit']} (headroom {s.get('headroom', '-')})"
              + ("" if s.get("ok", True) else f"; REFUSED: {s.get('detail')}"),
              f"- Warnings: {len(s.get('warnings', []))}" + "".join(f"\n  - {w['id']}: {w['warning']}"
                                                                    for w in s.get("warnings", [])[:30])]
    if "layout" in rep:
        ly = rep["layout"]
        lines += ["", "## Layout (warnings; independent of packing)", "",
                  f"- Drawn wider than the English (+15% and over 40 px): {ly['wider_than_english']}",
                  f"- Line count changed: {ly['line_count_changed']}"]
    lines += ["", "## Glyphs", "", f"- Added: {rep['glyphs']['added'] or 'none'}; used Turkish letters: "
              f"{rep['glyphs']['needed_beyond_font'] or 'none'}"]
    return "\n".join(lines) + "\n"


def _ok(r):
    if r.get("ok"):
        return f"packs ({r.get('packer')})"
    return f"REFUSED at {r.get('string') or '?'}"


def compare(a: dict, b: dict) -> dict:
    def pick(r):
        t, s = r["main_table"], r["subtitles"]
        return {"strings": r["strings"], "replacement_bytes": t["replacement_bytes"], "net_growth": t["net_growth"],
                "longer_than_slot": t["longer_than_slot"], "headroom": t["compaction"]["headroom"],
                "m34": t["packers"]["m34"].get("ok"), "compact": t["packers"]["compact"].get("ok"),
                "auto_packer": t["auto"].get("packer"), "relocated": t["auto"].get("relocated_strings"),
                "pointers": t["auto"].get("rewritten_pointers"),
                "other_language_pointers": t["auto"].get("other_language_pointers"),
                "subtitle_growth": s.get("growth"), "subtitle_warnings": len(s.get("warnings", [])),
                "layout_wider": (r.get("layout") or {}).get("wider_than_english")}
    pa, pb = pick(a), pick(b)
    return {k: {"a": pa[k], "b": pb[k]} for k in pa}


def dump(obj) -> str:
    return json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------------------------------------------

def _refused(fn) -> bool:
    try:
        fn()
        return False
    except Problem:
        return True


def selftest() -> int:
    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ' :: ' + str(detail)}")

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        game = td / "game"
        (game / "GAMEDATAbin").mkdir(parents=True)
        paths = {"game": game}
        # A synthetic fix.lvl: the five language tables (loc.tables layout) at 0x100; English handles 0-5 point to six
        # adjacent 8-byte slots at 0x9000; French handle 0 shares English string 4.
        size = 0xA000
        fix = bytearray(size)
        struct.pack_into(">I", fix, loc.LANG_PTR, 0x100 - rm.REF_BIAS)
        tab = {}
        for i, lang in enumerate(loc.LANGS):
            tab[lang] = 0x200 + i * 4 * loc.HANDLES
            struct.pack_into(">IHH", fix, 0x100 + 8 * i, tab[lang] - rm.REF_BIAS, loc.CAPACITY, loc.HANDLES)
        offs = [0x9000 + 8 * i for i in range(6)]
        refs = {}
        for i, off in enumerate(offs):
            fix[off:off + 7] = f"String{i}".encode()
            refs[tab["en"] + 4 * i] = off
        refs[tab["fr"]] = offs[4]
        for x, off in refs.items():
            struct.pack_into(">I", fix, x, off - rm.REF_BIAS)
        fix = bytes(fix)
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(fix)
        (game / "GAMEDATAbin" / "fix.ptr").write_bytes(
            struct.pack(">I", len(refs)) + b"".join(struct.pack(">II", 0, x) for x in refs))

        def ovs(texts):
            return [{"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": offs[i],
                     "slot_sha256": rm.sha256_bytes(rm.text_slot(fix, offs[i])), "text": t} for i, t in texts.items()]
        at_id = {off: f"en.{i}" for i, off in enumerate(offs)}
        b = baseline(paths)
        check("baseline: six strings, 48 slot bytes, all used (7 letters + NUL), one shared with French",
              (b["strings"], b["slot_bytes"], b["used_bytes"], b["shared_with_other_languages"]) == (6, 48, 48, 1), b)
        fit = table_capacity(paths, ovs({0: "x", 1: "kisa"}), frozenset(), None, "en", at_id)
        check("fit: every text in its slot, no packer moves anything, net growth negative",
              fit["verdict"].startswith("packs (every") and fit["net_growth"] < 0
              and fit["packers"]["m34"]["relocated_strings"] == 0, fit["verdict"])
        frag = {0: "x", 1: "Metin 1", 2: "y", 3: "Metin 3", 4: "Uzun metin"}
        r = table_capacity(paths, ovs(frag), frozenset(), None, "en", at_id)
        check("fragmentation: M34 refuses (naming the string), compaction packs; verdict says so",
              not r["packers"]["m34"]["ok"] and r["packers"]["m34"]["string"] == "en.4"
              and r["packers"]["compact"]["ok"] and "fragmentation" in r["verdict"], r["packers"])
        check("fragmentation: relocated strings and rewritten pointers counted; the French pointer of the shared "
              "string is an other-language pointer",
              r["packers"]["compact"]["relocated_strings"] == 2 and r["packers"]["compact"]["rewritten_pointers"] == 3
              and r["packers"]["compact"]["other_language_handles"] == ["fr.0"], r["packers"]["compact"])
        check("fragmentation: the M34 free list is three chunks (4, 4, 8) against 11 bytes to place",
              (r["m34_free_list"]["chunks"], r["m34_free_list"]["largest"], r["m34_free_list"]["largest_longer"])
              == (3, 8, 11), r["m34_free_list"])
        check("report is deterministic", dump(table_capacity(paths, ovs(frag), frozenset(), None, "en", at_id))
              == dump(r))
        big = {i: f"Daha uzun {i}" for i in range(5)}
        r2 = table_capacity(paths, ovs(big), frozenset(), None, "en", at_id)
        mo = re.search(r"\((\d+) runs, (\d+) bytes for (\d+) bytes", r2["packers"]["compact"]["detail"])
        k = r2["compaction"]
        check("total capacity: both refuse; the verdict names total capacity; the runs model equals the packer's own "
              "refusal numbers", not r2["packers"]["compact"]["ok"] and r2["verdict"].startswith("total_capacity")
              and mo and (int(mo.group(1)), int(mo.group(2)), int(mo.group(3))) == (k["runs"], k["capacity"], k["need"]),
              (r2["verdict"], r2["packers"]["compact"].get("detail"), k))
        # without font data (None) every 8-bit character is accepted: a character outside cp1252 is refused
        bad = table_capacity(paths, ovs({0: "x一"}), frozenset(), None, "en", at_id)
        check("unsupported character: refused before packing, named", bad["verdict"] == "unsupported_glyph_or_format"
              and bad["encoding_problems"] and bad["encoding_problems"][0]["string"] == "en.0", bad)
        ch = free_chunks([(0, b"ab\0\0\0\0\0\0"), (8, b"abcdef\0\0")])
        check("free chunks: adjacent blocks join; a chunk starts 4-aligned after a terminator",
              ch == {"chunks": 1, "bytes": 4, "largest": 4}, ch)
        # projections and alternatives on a source dict
        src = {"strings": {"en.0": {"text": "x", "alt": [{"text": "longer"}]}, "en.1": {"text": "y"}}}
        s2, changed = with_alternatives(src)
        check("alternatives: the latest alternative is measured; the source itself is unchanged",
              s2["strings"]["en.0"]["text"] == "longer" and src["strings"]["en.0"]["text"] == "x" and changed == ["en.0"])
        cat = {f"en.{i}": {"id": f"en.{i}", "text": f"String{i}", "source_sha256": "0" * 64} for i in range(6)}
        ctx = {f"en.{i}": {"group": "dialogue" if i < 5 else "credits"} for i in range(6)}
        s3, added, eng = synthetic({"strings": {"en.0": {"text": "real"}}}, cat, ctx, 1.5, {"dialogue"})
        check("projection: real text kept, untranslated strings of the chosen groups synthetic (ratio x bytes), "
              "other groups left out", s3["strings"]["en.0"]["text"] == "real" and added == 4 and eng == 28
              and s3["strings"]["en.1"]["text"] == "a" * 10 and "en.5" not in s3["strings"], s3)
        s4, _, _ = synthetic({"strings": {"en.0": {"text": "ğüşi"}}}, cat, ctx, 1.0, set(), 1.5)
        check("projection: a scale other than 1 models existing texts by their game bytes (Turkish letters one byte)",
              s4["strings"]["en.0"]["text"] == "a" * 6, s4)
        s5, _, _ = synthetic({"strings": {"en.0": {"text": "abcdefgh"}}}, cat, ctx, 2.0, {"dialogue"}, 2.0,
                             {"en.0": 7, "en.1": 9})
        check("projection: pinned strings stay within their slot (scaled or synthetic); others scale",
              len(s5["strings"]["en.0"]["text"]) == 8 and len(s5["strings"]["en.1"]["text"]) == 9
              and len(s5["strings"]["en.2"]["text"]) == 14, {k: len(v["text"]) for k, v in s5["strings"].items()})
        check("projection: cases parse; a malformed case is refused",
              parse_cases("low:1.0:0.95, high:1.1:1.2") == [("low", 1.0, 0.95), ("high", 1.1, 1.2)]
              and _refused(lambda: parse_cases("bad:1")))
        txt = markdown({"baseline": b, "main_table": r, "subtitles": {"vs_sub_bytes": 1, "cues": 0, "growth_limit": 1},
                        "project": "t", "include": "all", "strings": 5, "glyphs": {"added": "", "needed_beyond_font": ""}})
        check("markdown: ids and numbers, no text of the strings", "Metin" not in txt and "String" not in txt
              and "Verdict" in txt)
    n = results.count(False)
    print(f"R3HD_CAPACITY_SELFTEST {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}")
    return 1 if n else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("report", "project", "compare", "selftest"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--include", default="all", help="all (every status, as a preview) or approved")
    ap.add_argument("--use-alt", action="store_true")
    ap.add_argument("--cases", default="low:1.0:0.95,central:1.0:1.05,high:1.1:1.2",
                    help="project: name:existing_scale:untranslated_ratio,...")
    ap.add_argument("--groups", default=",".join(TRANSLATE_GROUPS))
    ap.add_argument("--break-even", action="store_true")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--md")
    ap.add_argument("--game-dir")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    try:
        if a.cmd == "compare":
            if len(a.args) != 2:
                raise Problem("compare A.json B.json")
            r = compare(*(json.loads(Path(x).read_text(encoding="utf-8")) for x in a.args))
            print(dump(r), end="")
            return 0
        if len(a.args) != 1:
            raise Problem(f"{a.cmd} SOURCE")
        source = Path(a.args[0])
        src = loc.load_source(source)
        paths = loc.game_paths(argparse.Namespace(cache=None, game_dir=a.game_dir))
        include = None if a.include == "all" else ("approved",) if a.include == "approved" else None
        if a.include not in ("all", "approved"):
            raise Problem("--include all|approved")
        alt_ids = []
        if a.use_alt:
            src, alt_ids = with_alternatives(src)
        if a.cmd == "report":
            r = measure(paths, src, source.parent, include)
            if a.use_alt:
                r["alternatives_used"] = alt_ids
            ok = r["main_table"]["auto"].get("ok") and r["subtitles"].get("ok", True)
        else:
            import r3hd_trwork as tw   # the workspace's catalog and categories
            ws = tw.WS(source.parent, a.game_dir)
            groups = {g.strip() for g in a.groups.split(",") if g.strip()}
            r = project(paths, src, source.parent, ws.cat, ws.context(), parse_cases(a.cases), groups, a.break_even)
            ok = True
        if a.json_out:
            Path(a.json_out).write_text(dump(r), encoding="utf-8")
        if a.md:
            Path(a.md).write_text(markdown(r), encoding="utf-8")
        if not a.json_out and not a.md:
            print(markdown(r), end="")
        else:
            print(markdown(r).split("\n## ")[0] if a.cmd == "report" else markdown(r), end="")
            if a.cmd == "report":
                print(f"verdict: {r['main_table']['verdict']}; subtitles "
                      f"{'ok' if r['subtitles'].get('ok', True) else 'REFUSED'}")
        return 0 if ok else 1
    except (Problem, loc.Problem, rm.Refusal) as x:
        print(f"refused: {getattr(x, 'detail', x)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
