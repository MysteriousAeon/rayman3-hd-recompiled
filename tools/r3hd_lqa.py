#!/usr/bin/env python3
"""Turkish LQA review workbook: one editable .xlsx with every translatable string of the game, its English (read
from the person's game data), the installed Turkish (the shipped tr.full.dev mod), and blank columns for a person's
corrections; then a read-only check and a per-region export of what the person changed. Nothing here edits the
translation, the mod or the game: corrections are applied later, deliberately, through r3hd_trwork.py.

The workbook and its exports hold the game's English and the private translation: they are refused anywhere in this
repository outside private/ (r3hd_locflow.private_path). This file holds ids, level codes and world names only.
Standard library only (the .xlsx is written and read with zipfile + XML).

usage:
  r3hd_lqa.py build OUT.xlsx [--workspace WS] [--mod ZIP|mod.json] [--game-dir DIR]
        a new workbook (never overwrites) + OUT.manifest.json (hashes only)
  r3hd_lqa.py check BOOK.xlsx [--workspace WS] [--mod ...] [--game-dir DIR]
        ids, reference columns against the snapshot and the live sources, review statuses, every proposed text
        against its English (codes, placeholders, letters the font can draw, subtitle size)
  r3hd_lqa.py export BOOK.xlsx OUT.jsonl (--region TEXT | --batch NAME | --all) [--workspace ..] [--mod ..]
        the reviewed rows (a proposal, a note or a status) of one region or batch, with their hashes and findings
  r3hd_lqa.py compare OLD.xlsx NEW.xlsx
        a newer workbook against an older one: same ids, reference text, Seq and hashes; every value typed in the
        older one present in the newer one; region changes counted
  r3hd_lqa.py selftest
Common: --json; --scans DIR (M14 level scans, default private/work/m14/scan). Exit 0 ok, 1 problems found, 2 refused.
"""
import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_loc as loc  # noqa: E402
import r3hd_locflow as lf  # noqa: E402
import r3hd_mods as rm  # noqa: E402

ROOT = rm.ROOT
WORKSPACE = ROOT / "private" / "tr" / "rayman3hd-turkish"
TOOL_VERSION = "2"
MANIFEST_KIND = "r3hd-lqa-workbook"
EXPORT_KIND = "r3hd-lqa-submission"
STATUSES = ("OK", "Change proposed", "Question", "Submitted")
SHEET_MAIN, SHEET_README, SHEET_REGIONS, SHEET_SNAP = "All Strings", "Read Me", "Regions", "Snapshot"

# (header, width, editable)
COLUMNS = [
    ("String ID", 11, False),
    ("Region", 30, False),
    ("Region Evidence", 12, False),
    ("English", 50, False),
    ("Current Turkish", 50, False),
    ("Proposed Turkish", 50, True),
    ("Review Note", 32, True),
    ("Status", 16, True),
    ("Batch", 12, True),
    ("Level(s)", 16, False),
    ("Category", 12, False),
    ("Installed", 14, False),
    ("Context / Source", 42, False),
    ("Format", 26, False),
    ("Region Basis", 34, False),
    ("Seq", 7, False),
]
HEAD = [c[0] for c in COLUMNS]
COL = {h: i for i, h in enumerate(HEAD)}
EDITABLE = [h for h, _, e in COLUMNS if e]
REFERENCE = ("String ID", "English", "Current Turkish")
OPTIONAL = ("Region Evidence",)   # absent from v1 workbooks, which stay checkable

# ---------------------------------------------------------------------------------------------------------------
# Regions (v2). A world is the stretch from its first level to the request of the next world's first level: the
# title's own world-entry table `82837004` (Intro_10, Wood_11, Swamp_60, Moor_00, Knaar_10, Flash_20, Sea_10,
# Fact_40, Tower_10) ends a revisited world exactly there (RE_NOTES "M18", VERIFIED static). Each level's global
# actor sets the current world `82836F60` (script procedure 0x354, RE_NOTES "M18"); the read-only progress watcher
# recorded that number in hidden runs for the levels marked "run" (E-99 ... E-116 watch files). Transition levels
# (menu_*, sk8_*) belong to the world before them: VERIFIED by run for sk8_10 (2) and menu_20 (4). Every other level
# is placed by the played chain (reports/COVERAGE.md, every edge played by a person): SUPPORTED.
# A voiced line's levels come from the sound banks, a script text's from the M14 level scans (VERIFIED data).
V_STATIC = "VERIFIED: first level of the world in the title's world-entry table"
V_RUN = "VERIFIED: world number read in a hidden run"
V_BOTH = "VERIFIED: world-entry table and world number read in a hidden run"
S_CHAIN = "SUPPORTED: played chain between this world's first level and the next world's"
S_TRANSIT = "SUPPORTED: transition level after the world (as sk8_10, menu_20 by run)"
REGIONS = [
    ("01 Intro + The Fairy Council", [("intro_10", V_BOTH), ("intro_15", V_RUN), ("intro_17", S_CHAIN),
                                      ("intro_20", S_CHAIN), ("menu_00", S_TRANSIT), ("sk8_00", S_TRANSIT)]),
    ("02 Clearleaf Forest", [("wood_11", V_BOTH), ("wood_10", V_RUN), ("wood_19", S_CHAIN), ("wood_50", S_CHAIN),
                             ("menu_10", S_TRANSIT), ("sk8_10", V_RUN)]),
    ("03 The Bog of Murk", [("swamp_60", V_BOTH), ("swamp_82", S_CHAIN), ("swamp_81", S_CHAIN),
                            ("swamp_83", S_CHAIN), ("swamp_50", S_CHAIN), ("swamp_51", S_CHAIN)]),
    ("04 The Land of the Livid Dead", [("moor_00", V_STATIC), ("moor_30", S_CHAIN), ("moor_60", S_CHAIN),
                                       ("moor_19", S_CHAIN), ("menu_20", V_RUN), ("sk8_20", S_TRANSIT)]),
    ("05 The Desert of the Knaaren", [("knaar_10", V_STATIC), ("knaar_20", S_CHAIN), ("knaar_30", S_CHAIN),
                                      ("knaar_45", S_CHAIN), ("knaar_60", V_RUN), ("knaar_69", V_RUN),
                                      ("knaar_70", S_CHAIN), ("menu_30", S_TRANSIT)]),
    ("06 The Longest Shortcut", [("flash_20", V_STATIC), ("flash_30", S_CHAIN), ("flash_10", S_CHAIN)]),
    ("07 The Summit Beyond the Clouds", [("sea_10", V_BOTH), ("mount_50", S_CHAIN), ("mount_4x", S_CHAIN)]),
    ("08 Hoodlum Headquarters", [("fact_40", V_BOTH), ("fact_50", V_RUN), ("fact_55", S_CHAIN),
                                 ("fact_34", S_CHAIN), ("fact_22", S_CHAIN)]),
    ("09 The Tower of the Leptys", [("tower_10", V_STATIC), ("tower_20", S_CHAIN), ("tower_30", S_CHAIN),
                                    ("tower_40", S_CHAIN), ("lept_15", S_CHAIN)]),
    ("10 Ending (staff, endgame)", [("staff", "after lept_15 in the played chain (credits)"),
                                    ("endgame", "end-of-game hub (world 9 by run; not a level of a world)")]),
    ("B Bonus games", [(lv, "bonus map (never entered by play)") for lv in
                       ("toudi_00", "ten_map", "ballmap", "crush", "raz_map", "sentinel", "snipe_00", "commando",
                        "ship_map", "bonustxt")]),
]
WORLDS = [name for name, _ in REGIONS[:9]]
LEVEL_REGION = {lv: name for name, lvs in REGIONS for lv, _ in lvs}
LEVEL_EVIDENCE = {lv: ev for _, lvs in REGIONS for lv, ev in lvs}
REGION_ORDER = {name: i for i, (name, _) in enumerate(REGIONS)}
# Movie subtitles: movie id -> (file, region, evidence). RE_NOTES "M35": 42 VERIFIED in game; the others SUPPORTED by
# content and duration against the Bink headers; a movie belongs to the level that plays it (reports/COVERAGE.md).
MOVIES = {
    42: ("menu10.bik", "02 Clearleaf Forest", "VERIFIED movie (cues seen in game); played after menu_10"),
    40: ("swamp51.bik", "03 The Bog of Murk", "SUPPORTED movie by duration; played after swamp_51"),
    35: ("menu20.bik", "04 The Land of the Livid Dead", "SUPPORTED movie by duration; played after menu_20"),
    28: ("menu30.bik", "05 The Desert of the Knaaren", "SUPPORTED movie by duration; played after menu_30"),
    19: ("outro.bik", "10 Ending (staff, endgame)", "SUPPORTED movie by duration; played after lept_15"),
}
# A script text referenced in the levels of more regions than this is shared code (the ~93 texts of every level).
SCRIPT_MAX_REGIONS = 2
SCANS = ROOT / "private" / "work" / "m14" / "scan"
# Region Evidence column values
EV_VERIFIED, EV_SUPPORTED, EV_SHARED, EV_INFERRED, EV_GLOBAL, EV_UNMAPPED = (
    "VERIFIED", "SUPPORTED", "SHARED", "INFERRED", "GLOBAL", "UNMAPPED")
# Strings seen in game in a level although no voice file names them: id -> (level, evidence).
OBSERVED = {"en.471": ("intro_10", "seen in game: Murfy's first intro_10 box (RE_NOTES M7, M34)")}
# Strings without a level: region by what the string is (r3hd_trwork context groups).
CATEGORY_REGION = {
    "menu": "UI: menus (global)", "system": "UI: system messages (global)",
    "tutorial": "Tutorial & hints (level not recorded)", "bonus_help": "UI: bonus games help",
    "album": "UI: album", "credits": "Credits", "internal": "Internal / legacy (probably never shown)",
    "legacy": "Internal / legacy (probably never shown)", "placeholder": "Internal / legacy (probably never shown)",
}
UNMAPPED_DIALOGUE = "Unmapped dialogue (level not recorded)"
SUBTITLE_REGION = "Movie subtitles"


class Problem(Exception):
    pass


class Refused(Exception):
    pass


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def file_sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sid_key(sid: str):
    try:
        return loc.sid_key(sid)
    except Exception:   # an id the catalog does not know sorts last, deterministically
        return (9, sid, 0, 0)


# ---------------------------------------------------------------------------------------------------------------
# Sources: live English catalog, installed Turkish mod, workspace context

def load_mod(path: Path) -> tuple:
    """(mod dict, sha256 of the file given, sha256 of mod.json)."""
    path = Path(path)
    data = path.read_bytes()
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            inner = z.read("mod.json")
    else:
        inner = data
    return json.loads(inner.decode("utf-8")), hashlib.sha256(data).hexdigest(), hashlib.sha256(inner).hexdigest()


def mod_texts(mod: dict, rows: list) -> tuple:
    """{id: Turkish} of the mod's text and subtitle overrides, matched exactly to catalog rows (a text override by
    file, offset and the English slot's hash; a subtitle by id and the English cue's hash), and the problems."""
    by_off = {}
    for r in rows:
        if r["kind"] == "text" and "offset" in r:
            by_off.setdefault(r["offset"], []).append(r)
    subs = {r["id"]: r for r in rows if r["kind"] == "subtitle"}
    out, problems = {}, []
    for i, o in enumerate(mod.get("overrides", [])):
        t = o.get("type")
        if t == "text":
            hit = [r for r in by_off.get(o.get("offset"), [])
                   if r.get("slot_sha256") == o.get("slot_sha256") and str(o.get("file", "")).endswith("fix.lvl")]
            if len(hit) != 1:
                problems.append(f"override {i}: text at offset {o.get('offset')} matches {len(hit)} catalog rows")
                continue
            sid = hit[0]["id"]
        elif t == "subtitle":
            r = subs.get(o.get("id"))
            if not r or r.get("source_sha256") != o.get("source_sha256"):
                problems.append(f"override {i}: subtitle {o.get('id')} does not match the catalog")
                continue
            sid = r["id"]
        else:
            continue   # glyphs
        if sid in out:
            problems.append(f"{sid}: more than one override")
            continue
        out[sid] = o.get("text", "")
    return out, problems


def load_script_refs(scans: Path) -> dict:
    """{en.N: sorted levels} of every text handle below 0x4E20 (= language-table index, RE_NOTES "M14") that a
    level's decoded scripts (TextRef constants) or its actors' Text designer variables name, from the private M14
    scans (`m14_script_scan.py --all`). Empty when the scans are absent."""
    refs = {}
    if not scans or not Path(scans).is_dir():
        return refs
    tr = re.compile(r"TextRef:([0-9A-Fa-f]{8})")
    for d in sorted(p for p in Path(scans).iterdir() if p.is_dir()):
        found = set()
        for f in sorted((d / "scripts").glob("*.txt")):
            found.update(int(h, 16) for h in tr.findall(f.read_text(encoding="utf-8", errors="replace")))
        a = d / "actors.json"
        if a.is_file():
            for act in json.loads(a.read_text(encoding="utf-8")).get("actors", []):
                for t in (act.get("texts") or {}).values():
                    try:
                        found.add(int(t.get("handle", "FFFFFFFF"), 16))
                    except ValueError:
                        pass
        for h in found:
            if h < 0x4E20:
                refs.setdefault(f"en.{h}", set()).add(d.name)
    return {k: sorted(v) for k, v in refs.items()}


def levels_region(levels: list) -> tuple:
    """(region, evidence, per-level evidence text) of a set of levels."""
    regs = sorted({LEVEL_REGION.get(lv, f"Level {lv}") for lv in levels}, key=lambda n: REGION_ORDER.get(n, 99))
    known = [lv for lv in levels if lv in LEVEL_REGION]
    if len(regs) > 1:
        return "Multiple: " + " | ".join(regs), EV_SHARED, ""
    if not known:
        return regs[0], EV_UNMAPPED, "level not in a region"
    ev = [LEVEL_EVIDENCE[lv] for lv in known]
    worst = EV_VERIFIED if all(e.startswith("VERIFIED") for e in ev) else EV_SUPPORTED
    if regs[0] not in WORLDS:
        worst = EV_VERIFIED   # level data; the region is not a world
    return regs[0], worst, "; ".join(f"{lv}: {LEVEL_EVIDENCE[lv]}" for lv in known)


def region_of(sid: str, c: dict, group: str, script_levels=None) -> tuple:
    """(region, basis, evidence) from data only; None region = decided later by neighbours or left unmapped."""
    if c["kind"] == "subtitle":
        mv = MOVIES.get(c.get("movie"))
        if mv:
            return mv[1], f"movie {c.get('movie')} = {mv[0]} ({mv[2]})", (
                EV_VERIFIED if mv[2].startswith("VERIFIED") else EV_SUPPORTED)
        return (SUBTITLE_REGION, f"movie {c.get('movie')} (scene not identified: one of fact22 / kna60 / mount4x "
                "by duration)", EV_UNMAPPED)
    levels = list(c.get("levels") or [])
    basis = "voice bank (verified level)"
    if not levels and sid in OBSERVED:
        levels, basis = [OBSERVED[sid][0]], OBSERVED[sid][1]
    if levels:
        region, ev, why = levels_region(levels)
        if ev == EV_SHARED:
            return region, basis + "; line used in several regions", ev
        return region, basis + (f"; {why}" if why else ""), ev
    sl = [lv for lv in (script_levels or []) if lv in LEVEL_REGION]
    if sl:
        regs = {LEVEL_REGION[lv] for lv in sl}
        if len(regs) <= SCRIPT_MAX_REGIONS:
            region, ev, why = levels_region(sl)
            return region, f"script text of level {' '.join(sl)} (M14 level scan)" + (f"; {why}" if why else ""), ev
    if group == "dialogue":
        return None, "", ""
    extra = f"; referenced by the scripts of {len(script_levels)} levels (shared)" if script_levels else ""
    return CATEGORY_REGION.get(group, "Unmapped"), f"category {group} (no level){extra}", EV_GLOBAL


def infer_neighbours(model: list):
    """Unvoiced dialogue between two voiced lines of one and the same region (nearest table neighbours) gets that
    region, marked as inferred; anything else stays unmapped."""
    text = [m for m in model if m["kind"] == "text"]
    single = [(m["region"] if m["basis"].startswith("voice bank") and not m["region"].startswith("Multiple")
               else None) for m in text]
    for i, m in enumerate(text):
        if m["region"] is not None:
            continue
        prev = next(((j, single[j]) for j in range(i - 1, -1, -1) if text[j]["category"] == "dialogue"
                     and text[j]["region"] is not None and text[j]["basis"].startswith("voice bank")), None)
        nxt = next(((j, single[j]) for j in range(i + 1, len(text)) if text[j]["category"] == "dialogue"
                    and text[j]["basis"].startswith("voice bank")), None)
        if prev and nxt and prev[1] and prev[1] == nxt[1]:
            m["region"] = prev[1]
            m["basis"] = (f"INFERRED, not verified: between voiced lines {text[prev[0]]['id']} and "
                          f"{text[nxt[0]]['id']} of this region")
            m["evidence"] = EV_INFERRED
        else:
            m["region"], m["basis"] = UNMAPPED_DIALOGUE, "unvoiced dialogue; neighbours disagree or are missing"
            m["evidence"] = EV_UNMAPPED


def fmt_notes(english: str, c: dict) -> str:
    parts = []
    cs = sorted(set(lf.codes(english)))
    if cs:
        parts.append("codes " + " ".join(cs))
    ph = lf.placeholders(english)
    if ph:
        parts.append("placeholders " + " ".join(ph))
    n = lf.breaks(english)
    if n:
        parts.append(f"{n + 1} lines (\\l)")
    if english != english.strip():
        parts.append("leading/trailing spaces")
    if c["kind"] == "subtitle":
        parts.append(f"subtitle max {rm.SUB_MAX_TEXT} bytes")
    return "; ".join(parts)


def build_model(ws_path: Path, mod_path: Path, game_dir=None, scans=SCANS) -> dict:
    import r3hd_trwork as tw
    ws = tw.WS(ws_path, game_dir)
    ctx = ws.context()
    mod, mod_file_sha, mod_json_sha = load_mod(mod_path)
    tr, problems = mod_texts(mod, ws.rows)
    refs = load_script_refs(scans)
    model, seq = [], 0
    for r in sorted(ws.rows, key=lambda r: sid_key(r["id"])):
        sid = r["id"]
        if "source_sha256" not in r or not r.get("text", "").strip():
            continue
        c, x = ws.cat[sid], ctx[sid]
        seq += 1
        region, basis, evidence = region_of(sid, c, x["group"], refs.get(sid))
        levels = list(c.get("levels") or [])
        if not levels and basis.startswith("script text"):
            levels = [lv for lv in refs.get(sid, []) if lv in LEVEL_REGION]
        ctxt = []
        if c.get("speakers"):
            ctxt.append("speaker code " + " ".join(c["speakers"]))
        if c.get("voice_files"):
            v = c["voice_files"]
            ctxt.append("voice " + ", ".join(v[:3]) + (f" (+{len(v) - 3})" if len(v) > 3 else ""))
        if x.get("display") and c["kind"] != "subtitle":
            ctxt.append(x["display"].split("; levels")[0])
        if c["kind"] == "subtitle":
            ctxt.append(f"movie {c.get('movie')}, {c.get('start_ms')}..{c.get('end_ms')} ms")
        dup = [f for f in x["flags"].split() if f.startswith("same_english_as:")]
        if dup:
            ctxt.append("same English as " + dup[0].split(":", 1)[1].replace("|", ", "))
        if "shared_with_other_languages" in x["flags"]:
            ctxt.append("slot shared with the other languages")
        model.append({
            "id": sid, "kind": c["kind"], "seq": seq, "english": c["text"], "turkish": tr.get(sid),
            "category": x["group"], "levels": " ".join(levels), "region": region, "basis": basis,
            "evidence": evidence, "context": "; ".join(ctxt), "format": fmt_notes(c["text"], c),
            "installed": "translated" if sid in tr else "not translated (English shown)",
        })
    infer_neighbours(model)
    ids = {m["id"] for m in model}
    for sid in tr:
        if sid not in ids:
            problems.append(f"{sid}: the mod translates a string without English text")
    project_diff = sorted((s for s, e in ws.src["strings"].items() if tr.get(s) != e.get("text")), key=sid_key)
    refs_sha = sha(json.dumps(refs, sort_keys=True)) if refs else ""
    return {"ws": ws, "model": model, "mod": mod, "mod_path": Path(mod_path), "mod_file_sha256": mod_file_sha,
            "script_refs_levels": len({lv for v in refs.values() for lv in v}), "script_refs_sha256": refs_sha,
            "mod_json_sha256": mod_json_sha, "map_problems": problems, "project_diff": project_diff,
            "fingerprint": tw.fingerprint(ws.cat), "handles_without_string": [r["id"] for r in ws.rows
                                                                              if "source_sha256" not in r],
            "blank": sorted((s for s, c in ws.cat.items() if not c["text"].strip()), key=sid_key)}


# ---------------------------------------------------------------------------------------------------------------
# Minimal XLSX writer / reader (inline strings; Excel's own saves use shared strings, both are read)

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
ESC_RE = re.compile(r"_(x[0-9A-Fa-f]{4})_")
BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def col_name(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def xml_text(s: str) -> str:
    """OOXML string escaping: a literal _xHHHH_ is protected as _x005F_xHHHH_; characters XML cannot carry are
    written as _xHHHH_ (none occur in the game's text; refused rather than lost)."""
    s = ESC_RE.sub(r"_x005F_\1_", s)
    s = BAD_XML.sub(lambda m: f"_x{ord(m.group()):04X}_", s)
    return escape(s)


def xml_untext(s: str) -> str:
    return ESC_RE.sub(lambda m: chr(int(m.group(1)[1:], 16)), s) if "_x" in s else s


def cell_xml(ref: str, v, style: int) -> str:
    if v is None or v == "":
        return f'<c r="{ref}" s="{style}"/>' if style else ""
    if isinstance(v, int):
        return f'<c r="{ref}" s="{style}"><v>{v}</v></c>'
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{xml_text(str(v))}</t></is></c>'


STYLES = XML_HEAD + f"""<styleSheet xmlns="{NS}">
<fonts count="3"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>
<font><b/><sz val="14"/><name val="Calibri"/><family val="2"/></font></fonts>
<fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFD9D9D9"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFBDD7EE"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF2F8FD"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="8"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="1" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="49" fontId="0" fillId="4" borderId="0" xfId="0" applyNumberFormat="1" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
<dxfs count="2"><dxf><fill><patternFill patternType="solid"><bgColor rgb="FFFFE699"/></patternFill></fill></dxf>
<dxf><font><color rgb="FF9C5700"/></font><fill><patternFill patternType="solid"><bgColor rgb="FFFFEB9C"/></patternFill></fill></dxf></dxfs>
</styleSheet>"""
S_HEAD_REF, S_HEAD_EDIT, S_TEXT, S_EDIT, S_TOP, S_TITLE, S_BOLD = 1, 2, 3, 4, 5, 6, 7


def sheet_xml(rows: list, widths: list, styles=None, freeze=None, autofilter=False, extra="", tab_selected=False):
    """rows: lists of values; styles(r, c) -> style id."""
    out = [XML_HEAD, f'<worksheet xmlns="{NS}" xmlns:r="{NS_R}">']
    ncols = max((len(r) for r in rows), default=1)
    out.append(f'<dimension ref="A1:{col_name(ncols - 1)}{max(len(rows), 1)}"/>')
    sel = ' tabSelected="1"' if tab_selected else ""
    if freeze:
        x, y = freeze
        tl = f"{col_name(x)}{y + 1}"
        if x and y:
            pane = (f'<pane xSplit="{x}" ySplit="{y}" topLeftCell="{tl}" activePane="bottomRight" state="frozen"/>'
                    f'<selection pane="topRight"/><selection pane="bottomLeft"/>'
                    f'<selection pane="bottomRight" activeCell="{tl}" sqref="{tl}"/>')
        else:   # rows only (Excel refuses a zero split with a bottom-right pane)
            pane = (f'<pane ySplit="{y}" topLeftCell="{tl}" activePane="bottomLeft" state="frozen"/>'
                    f'<selection pane="bottomLeft" activeCell="{tl}" sqref="{tl}"/>')
        out.append(f'<sheetViews><sheetView workbookViewId="0"{sel}>{pane}</sheetView></sheetViews>')
    else:
        out.append(f'<sheetViews><sheetView workbookViewId="0"{sel}/></sheetViews>')
    out.append('<sheetFormatPr defaultRowHeight="15"/><cols>')
    for i, w in enumerate(widths):
        out.append(f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>')
    out.append("</cols><sheetData>")
    for ri, r in enumerate(rows):
        cells = "".join(cell_xml(f"{col_name(ci)}{ri + 1}", v, styles(ri, ci) if styles else 0) for ci, v in enumerate(r))
        out.append(f'<row r="{ri + 1}">{cells}</row>')
    out.append("</sheetData>")
    if autofilter:
        out.append(f'<autoFilter ref="A1:{col_name(ncols - 1)}{len(rows)}"/>')
    out.append(extra)
    out.append('<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/></worksheet>')
    return "".join(out)


def write_xlsx(path: Path, sheets: list, defined_names: str = ""):
    """sheets: [(name, xml, hidden)]. Deterministic bytes (fixed timestamps, fixed order)."""
    ct = [XML_HEAD, '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
          '<Default Extension="xml" ContentType="application/xml"/>',
          '<Override PartName="/xl/workbook.xml" '
          'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
          '<Override PartName="/xl/styles.xml" '
          'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    wb = [XML_HEAD, f'<workbook xmlns="{NS}" xmlns:r="{NS_R}"><bookViews><workbookView activeTab="0"/></bookViews><sheets>']
    rels = [XML_HEAD, '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    parts = []
    for i, (name, xml, hidden) in enumerate(sheets, 1):
        ct.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
                  'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        wb.append(f'<sheet name="{escape(name)}" sheetId="{i}"{" state=" + chr(34) + "hidden" + chr(34) if hidden else ""} r:id="rId{i}"/>')
        rels.append(f'<Relationship Id="rId{i}" Type="{NS_R}/worksheet" Target="worksheets/sheet{i}.xml"/>')
        parts.append((f"xl/worksheets/sheet{i}.xml", xml))
    n = len(sheets) + 1
    rels.append(f'<Relationship Id="rId{n}" Type="{NS_R}/styles" Target="styles.xml"/></Relationships>')
    wb.append("</sheets>" + (f"<definedNames>{defined_names}</definedNames>" if defined_names else "") + "</workbook>")
    ct.append("</Types>")
    files = [("[Content_Types].xml", "".join(ct)),
             ("_rels/.rels", XML_HEAD + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
              f'relationships"><Relationship Id="rId1" Type="{NS_R}/officeDocument" Target="xl/workbook.xml"/>'
              "</Relationships>"),
             ("xl/workbook.xml", "".join(wb)), ("xl/_rels/workbook.xml.rels", "".join(rels)),
             ("xl/styles.xml", STYLES)] + parts
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            zi = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data.encode("utf-8"))
    lf.atomic_write(Path(path), buf.getvalue())


def _q(tag):
    return f"{{{NS}}}{tag}"


def _string_of(el) -> str:
    """Text of an <si> / <is>: its own <t> or its runs' <t>, never phonetic runs."""
    t = el.find(_q("t"))
    if t is not None:
        return xml_untext(t.text or "")
    return "".join(xml_untext(r.findtext(_q("t")) or "") for r in el.findall(_q("r")))


def read_xlsx(path: Path) -> dict:
    """{sheet name: [[cell, ...], ...]} where a cell is {"v": str|None, "t": type, "f": has formula}."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        target = {r.get("Id"): r.get("Target") for r in rels}
        shared = []
        if "xl/sharedStrings.xml" in names:
            shared = [_string_of(si) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(_q("si"))]
        out = {}
        for s in wb.find(_q("sheets")):
            t = target[s.get(f"{{{NS_R}}}id")].lstrip("/")
            p = t if t.startswith("xl/") else "xl/" + t
            root = ET.fromstring(z.read(p))
            rows = {}
            for row in root.iter(_q("row")):
                ri = int(row.get("r")) - 1
                cells = {}
                for c in row.findall(_q("c")):
                    ci = col_index(c.get("r"))
                    typ = c.get("t", "n")
                    f = c.find(_q("f")) is not None
                    if typ == "inlineStr":
                        is_ = c.find(_q("is"))
                        v = _string_of(is_) if is_ is not None else ""
                    else:
                        raw = c.findtext(_q("v"))
                        v = shared[int(raw)] if typ == "s" and raw is not None else (xml_untext(raw) if raw is not None
                                                                                      else None)
                    cells[ci] = {"v": v, "t": typ, "f": f}
                rows[ri] = cells
            n = max(rows) + 1 if rows else 0
            out[s.get("name")] = [[rows.get(i, {}).get(j, {"v": None, "t": "n", "f": False})
                                   for j in range(max(rows.get(i, {0: 0}).keys(), default=-1) + 1)]
                                  for i in range(n)]
        return out


# ---------------------------------------------------------------------------------------------------------------
# Workbook content

def readme_rows(meta: dict, counts: dict) -> list:
    R = [["Rayman 3 HD Recompiled — Turkish LQA review workbook"], [""],
         ["PRIVATE: holds the game's English text and the unpublished translation. Do not share or commit it."], [""],
         ["How to review"],
         ["1. Work in the 'All Strings' sheet. Filter the Region column (or use Ctrl+F) to find the line you saw in game."],
         ["2. Type your correction in 'Proposed Turkish'. Leave it empty when the current Turkish is fine."],
         ["3. Optional: 'Review Note' (why / question), 'Status' (dropdown), 'Batch' (your own label, e.g. FC-1)."],
         ["4. Never edit 'String ID', 'English' or 'Current Turkish': they are the reference the check compares."],
         ["5. Keep codes exactly: \\l = line break (do not press Alt+Enter), \\f1: … \\f0: = button/colour, \\jc = centred, "
          "%d / %s = numbers and names. The game font has no ; < > { } and no typographic quotes."],
         ["6. Rows with a proposal turn yellow. You may sort and filter freely: rows are matched by String ID, not by position."],
         ["7. Save as .xlsx (not CSV). Send the workbook (or say which Region/Batch is ready); the check and export read it."],
         [""], ["Submitting one region (e.g. Intro + The Fairy Council)"],
         ["• Filter Region by '01 Intro + The Fairy Council'. Also look at 'Tutorial & hints', 'UI: menus', "
          "'Movie subtitles', 'Unmapped dialogue' and 'Multiple: …' rows for lines you saw there (Ctrl+F on the English)."],
         ["• Set Batch to one label for everything you want sent together (strongest), or rely on the Region."],
         ["• Export (run by the agent): python tools/r3hd_lqa.py export BOOK.xlsx OUT.jsonl --region \"Fairy Council\"  "
          "or --batch FC-1"], [""],
         ["Columns"],
         ["String ID: stable id (en.N = game text table handle N; vs.en.M.K = subtitle cue K of movie M)."],
         ["Region: one of the nine worlds (01 .. 09), the ending, bonus games, or a global group (menus, tutorial, "
          "system …); 'Multiple: …' = the line is used in several regions. See the 'Regions' sheet and 'Region Basis'."],
         ["Region Evidence: VERIFIED / SUPPORTED / SHARED / INFERRED / GLOBAL / UNMAPPED (see Limits); filter it to "
          "review the certain rows first."],
         ["English / Current Turkish: unchanged source text and the installed translation (empty = the game shows English)."],
         ["Proposed Turkish / Review Note / Status / Batch: yours (light blue). Status: " + ", ".join(STATUSES) + "."],
         ["Level(s): level codes from the sound banks (voiced lines) or the level's scripts (tutorial boxes). "
          "Category: menu, tutorial, dialogue, subtitle …"],
         ["Context / Source: speaker code, voice file, movie and timing, other ids with the same English."],
         ["Format: codes, placeholders and line count of the English that the Turkish must keep."],
         ["Seq: game order; sort by it to restore the original order."], [""],
         ["Limits"],
         ["• Region comes from data for voiced lines (" + str(counts.get("voice", 0)) + "), tutorial boxes named by "
          "one level's scripts (" + str(counts.get("script", 0)) + ") and observed ones; unvoiced dialogue is inferred "
          "or unmapped; menus and system texts used everywhere are GLOBAL."],
         ["• Subtitle cues name a movie number: 42 (menu10.bik) is verified, 40 / 35 / 28 / 19 are matched by duration "
          "(SUPPORTED); movies 8 and 32 are not identified."],
         ["• Region Evidence: VERIFIED = the line's level is data and that level's world is verified (world-entry table "
          "or world number read in a run); SUPPORTED = level from data, world from the played order; SHARED = used in "
          "several regions; INFERRED = guessed from neighbouring voiced lines; GLOBAL = menus/system/shared, no level; "
          "UNMAPPED = no evidence."],
         ["• Transition levels (menu_00, sk8_00, menu_10, sk8_10, menu_20, sk8_20, menu_30) count to the world before "
          "them, as the game itself does (world number read in a run for sk8_10 and menu_20)."],
         ["• Lines marked 'not translated (English shown)' have no Turkish in the installed mod (credits, debug, PS2…)."],
         [""], ["Build"]]
    for k, v in meta.items():
        R.append([f"{k}: {v}"])
    return R


def build_book(m: dict, out: Path, created: str) -> dict:
    model = m["model"]
    data = [HEAD]
    for x in model:
        data.append([x["id"], x["region"], x.get("evidence", ""), x["english"], x["turkish"] or "", "", "", "", "",
                     x["levels"], x["category"], x["installed"], x["context"], x["format"], x["basis"], x["seq"]])
    n = len(data)
    edit_cols = {COL[h] for h in EDITABLE}

    def st(r, c):
        if r == 0:
            return S_HEAD_EDIT if c in edit_cols else S_HEAD_REF
        if c in edit_cols:
            return S_EDIT
        return S_TOP if c in (COL["String ID"], COL["Seq"]) else S_TEXT

    last = col_name(len(HEAD) - 1)
    pc, sc = col_name(COL["Proposed Turkish"]), col_name(COL["Status"])
    extra = (f'<conditionalFormatting sqref="A2:{last}{n}"><cfRule type="expression" dxfId="0" priority="1">'
             f'<formula>LEN(${pc}2)&gt;0</formula></cfRule></conditionalFormatting>'
             f'<conditionalFormatting sqref="{sc}2:{sc}{n}"><cfRule type="cellIs" dxfId="1" priority="2" operator="equal">'
             f'<formula>"Question"</formula></cfRule></conditionalFormatting>'
             f'<dataValidations count="1"><dataValidation type="list" allowBlank="1" showErrorMessage="1" '
             f'errorTitle="Status" error="Choose a status from the list (or leave it empty)." sqref="{sc}2:{sc}{n}">'
             f'<formula1>"{",".join(STATUSES)}"</formula1></dataValidation></dataValidations>')
    main = sheet_xml(data, [w for _, w, _ in COLUMNS], st, freeze=(1, 1), autofilter=True, extra=extra,
                     tab_selected=True)
    # Regions summary
    counts = {}
    evs = (EV_VERIFIED, EV_SUPPORTED, EV_INFERRED, EV_SHARED, EV_GLOBAL, EV_UNMAPPED)
    for x in model:
        k = x["region"]
        d = counts.setdefault(k, {"rows": 0, "translated": 0, **{e: 0 for e in evs}})
        d["rows"] += 1
        d["translated"] += x["turkish"] is not None
        if x.get("evidence") in d:
            d[x["evidence"]] += 1
    order = lambda k: (REGION_ORDER.get(k, 50 if k.startswith("Multiple") else 60), k)  # noqa: E731
    ev = dict(REGIONS)
    reg = [["Region", "Rows", "Translated", *[e.title() for e in evs], "Levels (world evidence)"]]
    for k in sorted(counts, key=order):
        lvs = "; ".join(f"{lv}: {e}" for lv, e in ev.get(k, []))
        reg.append([k, counts[k]["rows"], counts[k]["translated"], *[counts[k][e] for e in evs], lvs])
    regs = sheet_xml(reg, [48, 7, 11, 10, 11, 10, 9, 9, 11, 120], lambda r, c: S_HEAD_REF if r == 0 else S_TEXT,
                     freeze=(0, 1), autofilter=True)
    meta = {"created": created, "tool": f"tools/r3hd_lqa.py v{TOOL_VERSION}",
            "catalog_fingerprint": m["fingerprint"], "mod": f"{m['mod'].get('id')} {m['mod'].get('version')}",
            "mod_file_sha256": m["mod_file_sha256"], "mod_json_sha256": m["mod_json_sha256"], "rows": len(model)}
    if m.get("script_refs_sha256"):
        meta["script_refs_sha256"] = m["script_refs_sha256"]
    snap = [["String ID", "English SHA-256", "Current Turkish SHA-256", "Seq"]]
    snap += [[f"#{k}", str(v), "", ""] for k, v in meta.items() if k != "created"]
    snap += [[x["id"], sha(x["english"]), sha(x["turkish"]) if x["turkish"] is not None else "", x["seq"]] for x in model]
    snaps = sheet_xml(snap, [14, 66, 66, 7])
    voice = sum(1 for x in model if x["basis"].startswith("voice bank"))
    script = sum(1 for x in model if x["basis"].startswith("script text"))
    rm_rows = readme_rows(meta, {"voice": voice, "script": script})
    bold = {i for i, r in enumerate(rm_rows) if r and (r[0] in ("How to review", "Columns", "Limits", "Build")
                                                      or r[0].startswith("Submitting one region"))}
    rd = sheet_xml(rm_rows, [160],
                   lambda r, c: S_TITLE if r == 0 else (S_BOLD if r in bold else S_TEXT))
    dn = f"<definedName name=\"_xlnm._FilterDatabase\" localSheetId=\"0\" hidden=\"1\">'{SHEET_MAIN}'!$A$1:${last}${n}</definedName>"
    dn += f"<definedName name=\"_xlnm._FilterDatabase\" localSheetId=\"2\" hidden=\"1\">'{SHEET_REGIONS}'!$A$1:${col_name(len(reg[0]) - 1)}${len(reg)}</definedName>"
    write_xlsx(out, [(SHEET_MAIN, main, False), (SHEET_README, rd, False), (SHEET_REGIONS, regs, False),
                     (SHEET_SNAP, snaps, True)], dn)
    return meta


# ---------------------------------------------------------------------------------------------------------------
# Check / export

def cell_str(c) -> str:
    v = c.get("v") if c else None
    return "" if v is None else str(v)


def read_review(book: Path) -> dict:
    sheets = read_xlsx(book)
    if SHEET_MAIN not in sheets:
        raise Refused(f"{book}: no '{SHEET_MAIN}' sheet")
    rows = sheets[SHEET_MAIN]
    if not rows:
        raise Refused(f"{book}: '{SHEET_MAIN}' is empty")
    head = [cell_str(c) for c in rows[0]]
    where = {}
    for i, h in enumerate(head):
        if h in COL:
            if h in where:
                raise Refused(f"column '{h}' appears twice")
            where[h] = i
    missing = [h for h in HEAD if h not in where and h not in OPTIONAL]
    if missing:
        raise Refused("columns missing or renamed: " + ", ".join(missing))
    out = []
    for ri, r in enumerate(rows[1:], 2):
        get = lambda h: (r[where[h]] if h in where and where[h] < len(r)  # noqa: E731
                         else {"v": None, "t": "n", "f": False})
        rec = {"row": ri, **{h: cell_str(get(h)) for h in HEAD}, "_cells": {h: get(h) for h in EDITABLE}}
        if any(rec[h] for h in HEAD):
            out.append(rec)
    snap = {}
    for r in sheets.get(SHEET_SNAP, [])[1:]:
        vals = [cell_str(c) for c in r] + ["", "", ""]
        if vals[0]:
            snap[vals[0]] = vals[1:3]
    return {"rows": out, "snapshot": snap}


def check_book(book_rows: list, snapshot: dict, model: list, glyphs, cat: dict) -> dict:
    """Pure: findings for every row against the snapshot written with the workbook and the live model."""
    live = {x["id"]: x for x in model}
    errors, warnings, reviewed, seen, fatal = [], [], [], {}, []
    for r in book_rows:
        sid = r["String ID"].strip()
        where = f"row {r['row']}"
        if not sid:
            fatal.append(f"{where}: empty String ID")
            continue
        if sid in seen:
            fatal.append(f"{where}: {sid} duplicated (also row {seen[sid]})")
            continue
        seen[sid] = r["row"]
        x = live.get(sid)
        if x is None:
            fatal.append(f"{where}: {sid} is not a string of the current catalog")
            continue
        rf = {"stale": False, "edited": [], "errors": [], "warnings": []}
        snap = snapshot.get(sid)
        cur = x["turkish"] or ""
        if snap is None:
            rf["errors"].append("not in the workbook's snapshot")
        else:
            if sha(r["English"]) != snap[0]:
                rf["edited"].append("English")
            if (sha(r["Current Turkish"]) if r["Current Turkish"] else "") != snap[1]:
                rf["edited"].append("Current Turkish")
            if snap[0] != sha(x["english"]) or snap[1] != (sha(x["turkish"]) if x["turkish"] is not None else ""):
                rf["stale"] = True
        if not rf["edited"] and (r["English"] != x["english"] or r["Current Turkish"] != cur):
            rf["stale"] = True
        for h in rf["edited"]:
            rf["errors"].append(f"reference column '{h}' was edited in the workbook")
        if rf["stale"]:
            rf["errors"].append("STALE: the English or the installed Turkish changed since the workbook was built")
        for h in EDITABLE:
            c = r["_cells"][h]
            if c.get("f"):
                rf["errors"].append(f"'{h}' holds a formula (a cell starting with = + - @?); type it as text")
            elif c.get("t") in ("n", "b", "e") and c.get("v") not in (None, ""):
                rf["warnings"].append(f"'{h}' was stored as a {'number' if c['t'] == 'n' else 'value'}, read as text")
        st = r["Status"].strip()
        if st and st not in STATUSES:
            rf["errors"].append(f"unknown Status '{st}' (use: {', '.join(STATUSES)})")
        prop = r["Proposed Turkish"]
        if prop:
            e, w = lf.text_problems(sid, x["english"], prop, glyphs, cat.get(sid))
            rf["errors"] += e
            rf["warnings"] += w
            if prop == cur:
                rf["warnings"].append("same as the current Turkish")
        if any(r[h].strip() or cell_str(r["_cells"][h]).strip() for h in EDITABLE):
            reviewed.append(sid)
        for p in rf["errors"]:
            errors.append(f"{where} {sid}: {p}")
        for p in rf["warnings"]:
            warnings.append(f"{where} {sid}: {p}")
        r["_find"] = rf
    absent = sorted((s for s in live if s not in seen), key=sid_key)
    if absent:
        warnings.append(f"{len(absent)} ids of the catalog are not in the workbook (rows deleted?): "
                        + ", ".join(absent[:20]) + (" …" if len(absent) > 20 else ""))
    reviewed.sort(key=sid_key)
    return {"errors": fatal + errors, "fatal": fatal, "warnings": warnings, "reviewed": reviewed, "absent": absent,
            "rows": len(book_rows), "proposed": sum(1 for r in book_rows if r["Proposed Turkish"])}


def load_checked(a) -> tuple:
    book = Path(a.book)
    m = build_model(Path(a.workspace), Path(a.mod), a.game_dir, Path(a.scans))
    rv = read_review(book)
    res = check_book(rv["rows"], rv["snapshot"], m["model"], m["ws"].glyphs, m["ws"].cat)
    snap_meta = {k[1:]: v[0] for k, v in rv["snapshot"].items() if k.startswith("#")}
    stale = []
    if snap_meta.get("catalog_fingerprint") not in (None, m["fingerprint"]):
        stale.append("STALE workbook: the game's English catalog changed since it was built")
    if snap_meta.get("mod_json_sha256") not in (None, m["mod_json_sha256"]):
        stale.append("STALE workbook: built against another Turkish mod "
                     f"({snap_meta.get('mod_json_sha256', '')[:12]} != {m['mod_json_sha256'][:12]})")
    res["fatal"] = stale + res["fatal"]
    res["errors"] = stale + res["errors"]
    res["book_sha256"] = file_sha(book)
    return m, rv, res


def cmd_build(a) -> dict:
    out = Path(a.out)
    if out.suffix.lower() != ".xlsx":
        raise Refused(f"{out}: the workbook must end in .xlsx")
    lf.private_path(out)
    man = out.with_name(out.stem + ".manifest.json")
    for p in (out, man):
        if p.exists():
            raise Refused(f"{p} exists: a workbook is never overwritten (it may hold a person's corrections)")
    m = build_model(Path(a.workspace), Path(a.mod), a.game_dir, Path(a.scans))
    if m["map_problems"]:
        raise Refused("the mod does not map onto the catalog: " + "; ".join(m["map_problems"][:10]))
    import datetime
    created = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = build_book(m, out, created)
    model = m["model"]
    counts = {
        "rows": len(model), "text": sum(x["kind"] == "text" for x in model),
        "subtitle": sum(x["kind"] == "subtitle" for x in model),
        "translated": sum(x["turkish"] is not None for x in model),
        "untranslated": sum(x["turkish"] is None for x in model),
        "region_voice_bank": sum(x["basis"].startswith("voice bank") for x in model),
        "region_observed": sum(x["id"] in OBSERVED for x in model),
        "region_inferred": sum(x["basis"].startswith("INFERRED") for x in model),
        "region_script_text": sum(x["basis"].startswith("script text") for x in model),
        "script_refs_levels": m["script_refs_levels"],
        "region_category": sum(x["basis"].startswith("category") for x in model),
        "region_subtitle_movie": sum(x["kind"] == "subtitle" for x in model),
        "unmapped_dialogue": sum(x["region"] == UNMAPPED_DIALOGUE for x in model),
        "multi_region": sum(x["region"].startswith("Multiple") for x in model),
        "evidence": {e: sum(x.get("evidence") == e for x in model) for e in
                     (EV_VERIFIED, EV_SUPPORTED, EV_SHARED, EV_INFERRED, EV_GLOBAL, EV_UNMAPPED)},
        "worlds": {w: sum(x["region"] == w for x in model) for w in WORLDS},
        "worlds_incl_shared": {w: sum(w in x["region"] for x in model) for w in WORLDS},
        "handles_without_string": len(m["handles_without_string"]), "blank": len(m["blank"]),
        "workspace_vs_mod_differences": len(m["project_diff"]),
    }
    by_region = {}
    for x in model:
        by_region[x["region"]] = by_region.get(x["region"], 0) + 1
    manifest = {"kind": MANIFEST_KIND, "format": 1, **meta, "workbook": out.name, "workbook_sha256": file_sha(out),
                "mod_path": str(Path(a.mod).resolve()), "workspace": str(Path(a.workspace).resolve()),
                "workspace_tr_json_sha256": file_sha(m["ws"].proj), "counts": counts, "by_region": by_region,
                "handles_without_string": m["handles_without_string"], "blank": m["blank"],
                "workspace_vs_mod": m["project_diff"],
                "rows_sha256": {x["id"]: [sha(x["english"]), sha(x["turkish"]) if x["turkish"] is not None else ""]
                                for x in model}}
    lf.atomic_write(man, (json.dumps(manifest, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    # Round trip: the written bytes must give back every id and reference text exactly.
    rv = read_review(out)
    res = check_book(rv["rows"], rv["snapshot"], model, m["ws"].glyphs, m["ws"].cat)
    same = [r["String ID"] for r, x in zip(rv["rows"], model)
            if (r["String ID"], r["English"], r["Current Turkish"]) != (x["id"], x["english"], x["turkish"] or "")]
    ok = not res["errors"] and not res["reviewed"] and not same and len(rv["rows"]) == len(model)
    return {"ok": ok, "workbook": str(out), "manifest": str(man), "workbook_sha256": manifest["workbook_sha256"],
            "counts": counts, "by_region": by_region, "roundtrip_mismatch": same[:20], "check_errors": res["errors"][:20]}


def cmd_check(a) -> dict:
    m, rv, res = load_checked(a)
    return {"ok": not res["errors"], **{k: res[k] for k in ("rows", "proposed", "reviewed", "errors", "warnings")},
            "book_sha256": res["book_sha256"], "catalog_fingerprint": m["fingerprint"],
            "mod_json_sha256": m["mod_json_sha256"]}


def cmd_export(a) -> dict:
    out = Path(a.out)
    lf.private_path(out)
    if out.exists():
        raise Refused(f"{out} exists")
    m, rv, res = load_checked(a)
    if res["fatal"]:
        raise Refused("the workbook cannot be exported: " + "; ".join(res["fatal"][:10]))
    live = {x["id"]: x for x in m["model"]}
    sel = []
    for r in rv["rows"]:
        sid = r["String ID"].strip()
        if sid not in res["reviewed"]:
            continue
        if a.batch is not None and r["Batch"].strip() != a.batch:
            continue
        if a.region is not None and a.region.lower() not in r["Region"].lower():
            continue
        sel.append(r)
    sel.sort(key=lambda r: sid_key(r["String ID"].strip()))
    head = {"kind": EXPORT_KIND, "format": 1, "book": Path(a.book).name, "book_sha256": res["book_sha256"],
            "catalog_fingerprint": m["fingerprint"], "mod_json_sha256": m["mod_json_sha256"],
            "filter": {"region": a.region, "batch": a.batch, "all": a.all}, "rows": len(sel),
            "proposed": sum(1 for r in sel if r["Proposed Turkish"]),
            "with_errors": sum(1 for r in sel if r["_find"]["errors"])}
    lines = [json.dumps(head, ensure_ascii=False)]
    for r in sel:
        sid = r["String ID"].strip()
        x = live[sid]
        f = r["_find"]
        lines.append(json.dumps({
            "id": sid, "region": x["region"], "english_sha256": sha(x["english"]),
            "current_sha256": sha(x["turkish"]) if x["turkish"] is not None else "",
            "english": x["english"], "current": x["turkish"], "proposed": r["Proposed Turkish"] or None,
            "note": r["Review Note"], "status": r["Status"], "batch": r["Batch"], "stale": f["stale"],
            "errors": f["errors"], "warnings": f["warnings"]}, ensure_ascii=False))
    out.parent.mkdir(parents=True, exist_ok=True)
    lf.atomic_write(out, ("\n".join(lines) + "\n").encode("utf-8"))
    return {"ok": head["with_errors"] == 0, "out": str(out), **{k: head[k] for k in ("rows", "proposed", "with_errors")},
            "errors": [e for e in res["errors"] if any(e.split(": ")[0].endswith(" " + r["String ID"].strip())
                                                       for r in sel)]}


def compare_books(old: dict, new: dict) -> dict:
    """Pure: a newer workbook against an older one (read_review of each). Ids, reference text, Seq and snapshot
    hashes must be equal; every value a person typed in the older one must be in the newer one."""
    errors, region_moves = [], {}
    o = {r["String ID"].strip(): r for r in old["rows"]}
    n = {r["String ID"].strip(): r for r in new["rows"]}
    for name, book in (("old", old), ("new", new)):
        if len(book["rows"]) != len({r["String ID"].strip() for r in book["rows"]}):
            errors.append(f"{name} workbook has duplicate String IDs")
    only_o, only_n = sorted(set(o) - set(n), key=sid_key), sorted(set(n) - set(o), key=sid_key)
    if only_o:
        errors.append(f"{len(only_o)} ids only in the old workbook: " + ", ".join(only_o[:10]))
    if only_n:
        errors.append(f"{len(only_n)} ids only in the new workbook: " + ", ".join(only_n[:10]))
    carried = 0
    for sid in sorted(set(o) & set(n), key=sid_key):
        a, b = o[sid], n[sid]
        for h in ("English", "Current Turkish", "Seq"):
            if a[h] != b[h]:
                errors.append(f"{sid}: '{h}' differs")
        if old["snapshot"].get(sid) != new["snapshot"].get(sid):
            errors.append(f"{sid}: snapshot hashes differ")
        for h in EDITABLE:
            if a[h].strip():
                carried += 1
                if a[h] != b[h]:
                    errors.append(f"{sid}: the old workbook's '{h}' is not in the new one")
        if a["Region"] != b["Region"]:
            k = f"{a['Region']} -> {b['Region']}"
            region_moves[k] = region_moves.get(k, 0) + 1
    meta = lambda s: {k[1:]: v[0] for k, v in s.items() if k.startswith("#")}  # noqa: E731
    mo, mn = meta(old["snapshot"]), meta(new["snapshot"])
    for k in ("catalog_fingerprint", "mod_json_sha256", "mod_file_sha256"):
        if mo.get(k) != mn.get(k):
            errors.append(f"build identity '{k}' differs")
    return {"ok": not errors, "old_rows": len(old["rows"]), "new_rows": len(new["rows"]),
            "common_ids": len(set(o) & set(n)), "old_values_typed": carried,
            "region_changed": sum(region_moves.values()), "region_moves": dict(sorted(region_moves.items())),
            "errors": errors}


def cmd_compare(a) -> dict:
    res = compare_books(read_review(Path(a.old)), read_review(Path(a.new)))
    res["old_sha256"], res["new_sha256"] = file_sha(Path(a.old)), file_sha(Path(a.new))
    return res


# ---------------------------------------------------------------------------------------------------------------
# Selftest (synthetic text only)

def selftest() -> int:
    import tempfile
    fails, done = [], []

    def check(name, ok, detail=""):
        print(("ok   " if ok else "FAIL ") + name + (f": {detail}" if detail and not ok else ""))
        done.append(name)
        if not ok:
            fails.append(name)

    tricky = ["  lead and trail  ", "a\\lb \\f1:c\\f0: %d", "çğıİöşü ÇĞÖŞÜ é®…", "_x0041_ literal", "<&>\"'",
              "=1+1", "tab\there", "😀 astral"]
    model = [{"id": f"en.{i + 1}", "kind": "text", "seq": i + 1, "english": t, "turkish": (t[::-1] if i % 2 else None),
              "category": "dialogue", "levels": "intro_10", "region": REGIONS[0][0], "basis": "voice bank (verified level)",
              "context": "", "format": "", "installed": "x"} for i, t in enumerate(tricky)]
    m = {"model": model, "fingerprint": "f" * 64, "mod": {"id": "t", "version": "0"}, "mod_file_sha256": "a" * 64,
         "mod_json_sha256": "b" * 64}
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.xlsx"
        build_book(m, p, "2000-01-01T00:00:00+00:00")
        b1 = p.read_bytes()
        build_book(m, p, "2000-01-01T00:00:00+00:00")
        check("deterministic bytes", b1 == p.read_bytes())
        rv = read_review(p)
        check("row count", len(rv["rows"]) == len(model))
        check("reference text round trip", all((r["String ID"], r["English"], r["Current Turkish"]) ==
                                               (x["id"], x["english"], x["turkish"] or "")
                                               for r, x in zip(rv["rows"], model)),
              str([(r["English"], x["english"]) for r, x in zip(rv["rows"], model) if r["English"] != x["english"]]))
        res = check_book(rv["rows"], rv["snapshot"], model, frozenset(), {})
        check("clean workbook has no findings", not res["errors"] and not res["reviewed"], str(res["errors"][:3]))
        # Edit like a person: a proposal, a reference edit, a duplicate id, a bad status, a formula, a lost code.
        rows = rv["rows"]
        rows[0]["Proposed Turkish"] = "  yeni  "
        rows[1]["English"] = "changed"
        rows[2]["Status"] = "Done?"
        rows[3]["_cells"]["Review Note"] = {"v": "#NAME?", "t": "e", "f": True}
        rows[1]["Proposed Turkish"] = "a b"
        rows.append(dict(rows[4], row=99))
        res = check_book(rows, rv["snapshot"], model, frozenset(), {})
        txt = "\n".join(res["errors"])
        check("reference edit detected", "reference column 'English'" in txt)
        check("lost code detected", "in-band codes changed" in txt or "placeholders changed" in txt, txt)
        check("bad status detected", "unknown Status" in txt)
        check("formula detected", "formula" in txt)
        check("duplicate id detected", "duplicated" in txt)
        check("reviewed rows listed deterministically", res["reviewed"] == ["en.1", "en.2", "en.3", "en.4"],
              str(res["reviewed"]))
        stale = [dict(x) for x in model]
        stale[0]["english"] = "new source"
        rv2 = read_review(p)
        res = check_book(rv2["rows"], rv2["snapshot"], stale, frozenset(), {})
        check("stale source detected", any("STALE" in e and "en.1" in e for e in res["errors"]))
        rows = rv2["rows"][:-1]
        res = check_book(rows, rv2["snapshot"], model, frozenset(), {})
        check("missing id reported", res["absent"] == ["en.8"])
        # Excel-style shared strings are read as well.
        ss = '<sst xmlns="%s"><si><t xml:space="preserve"> x_x005F_x0041_ </t></si><si><r><t>a</t></r><r><t>b</t></r></si></sst>' % NS
        with zipfile.ZipFile(p) as z:
            items = {n: z.read(n) for n in z.namelist()}
        sh = items["xl/worksheets/sheet4.xml"].decode()
        sh = sh.replace('<row r="1">', '<row r="1"><c r="E1" t="s"><v>0</v></c><c r="F1" t="s"><v>1</v></c>', 1)
        items["xl/worksheets/sheet4.xml"] = sh.encode()
        items["xl/sharedStrings.xml"] = ss.encode()
        q = Path(td) / "s.xlsx"
        with zipfile.ZipFile(q, "w") as z:
            for n, d in items.items():
                z.writestr(n, d)
        snap = read_xlsx(q)[SHEET_SNAP][0]
        check("shared strings and _x escapes", cell_str(snap[4]) == " x_x0041_ " and cell_str(snap[5]) == "ab",
              repr((cell_str(snap[4]), cell_str(snap[5]))))
        # A v1 workbook (no Region Evidence column) stays readable.
        v1 = [h for h in HEAD if h not in OPTIONAL]
        rowv = {"String ID": "en.1", "English": "e", "Current Turkish": "t", "Seq": 1}
        p1 = Path(td) / "v1.xlsx"
        write_xlsx(p1, [(SHEET_MAIN, sheet_xml([v1, [rowv.get(h, "") for h in v1]], [10] * len(v1)), False)])
        try:
            r1 = read_review(p1)["rows"]
            check("v1 workbook without Region Evidence is read", len(r1) == 1 and r1[0]["Region Evidence"] == "")
        except Refused as x:
            check("v1 workbook without Region Evidence is read", False, str(x))
        # compare: identical books, a lost typed value, a region change
        a1, a2 = read_review(p), read_review(p)
        check("compare identical books", compare_books(a1, a2)["ok"])
        a1["rows"][0]["Proposed Turkish"] = "yazılan"
        a2["rows"][1]["Region"] = "other"
        c = compare_books(a1, a2)
        check("compare finds a lost typed value", not c["ok"] and any("en.1" in e for e in c["errors"]), str(c["errors"]))
        check("compare counts a region change", c["region_changed"] == 1)
        a2["rows"][2]["English"] = "x"
        check("compare finds changed English", any("en.3: 'English'" in e for e in compare_books(a1, a2)["errors"]))
        # script text references from a synthetic scan
        sd = Path(td) / "scan"
        (sd / "wood_10" / "scripts").mkdir(parents=True)
        (sd / "wood_10" / "scripts" / "a.txt").write_text("  TextRef:000001D7\n  TextRef:00004F51\n", encoding="utf-8")
        (sd / "wood_10" / "actors.json").write_text(json.dumps({"actors": [{"texts": {"1": {"handle": "00000010"},
                                                     "2": {"handle": "FFFFFFFF"}}}]}), encoding="utf-8")
        refs = load_script_refs(sd)
        check("script refs: table handles only", refs == {"en.471": ["wood_10"], "en.16": ["wood_10"]}, str(refs))
    for t in ("intro_10", "wood_11", "fact_40", "lept_15", "flash_20", "sea_10", "ship_map", "menu_30"):
        check(f"level {t} has a region", t in LEVEL_REGION)
    check("nine worlds", len(WORLDS) == 9 and all(w[:2] == f"{i + 1:02d}" for i, w in enumerate(WORLDS)))
    check("worlds 6 and 7 apart", LEVEL_REGION["flash_10"].startswith("06") and LEVEL_REGION["sea_10"].startswith("07")
          and LEVEL_REGION["mount_4x"].startswith("07"))
    check("transition levels to the world before", [LEVEL_REGION[x][:2] for x in
                                                     ("sk8_00", "menu_10", "sk8_10", "menu_20", "sk8_20", "menu_30")]
          == ["01", "02", "02", "04", "04", "05"])
    check("evidence verified / supported", levels_region(["sk8_10"])[1] == EV_VERIFIED
          and levels_region(["wood_19"])[1] == EV_SUPPORTED and levels_region(["wood_19", "sea_10"])[1] == EV_SHARED)
    cat = {"kind": "text", "levels": []}
    check("one level's script text gets its world",
          region_of("en.9", cat, "tutorial", ["wood_10"])[:1] == ("02 Clearleaf Forest",))
    many = ["intro_10", "wood_10", "swamp_60", "moor_00", "knaar_10"]
    check("script text of many worlds stays global", region_of("en.9", cat, "tutorial", many)[2] == EV_GLOBAL
          and region_of("en.9", cat, "tutorial", many)[0] == CATEGORY_REGION["tutorial"])
    check("unvoiced dialogue is left for the neighbours", region_of("en.9", cat, "dialogue", [])[0] is None)
    check("movie 42 verified, movie 8 unmapped",
          region_of("vs", {"kind": "subtitle", "movie": 42}, "subtitle")[::2] == ("02 Clearleaf Forest", EV_VERIFIED)
          and region_of("vs", {"kind": "subtitle", "movie": 8}, "subtitle")[::2] == (SUBTITLE_REGION, EV_UNMAPPED))
    print(f"R3HD_LQA_SELFTEST {'PASS' if not fails else 'FAIL'} {len(done) - len(fails)}/{len(done)}")
    return 0 if not fails else 1


# ---------------------------------------------------------------------------------------------------------------

def main() -> int:
    from m49_build import MOD, MOD_SHA256
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--workspace", default=str(WORKSPACE))
        p.add_argument("--mod", default=str(MOD), help="the installed Turkish mod (.zip or mod.json); default: the "
                       "shipped 1.0.0 release copy")
        p.add_argument("--game-dir", default=None)
        p.add_argument("--scans", default=str(SCANS), help="M14 level scans (script text levels); absent = none")
        p.add_argument("--json", action="store_true")
    p = sub.add_parser("build")
    p.add_argument("out")
    common(p)
    p = sub.add_parser("check")
    p.add_argument("book")
    common(p)
    p = sub.add_parser("export")
    p.add_argument("book")
    p.add_argument("out")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--region")
    g.add_argument("--batch")
    g.add_argument("--all", action="store_true")
    common(p)
    p = sub.add_parser("compare")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("--json", action="store_true")
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    try:
        res = {"build": cmd_build, "check": cmd_check, "export": cmd_export, "compare": cmd_compare}[a.cmd](a)
    except (Refused, Problem, lf.Problem, loc.Problem, rm.Refusal) as x:
        print(f"REFUSED: {getattr(x, 'detail', x)}", file=sys.stderr)
        return 2
    if a.cmd == "build" and Path(a.mod).resolve() == MOD.resolve():
        res["mod_pinned"] = file_sha(MOD) == MOD_SHA256
        res["ok"] = res["ok"] and res["mod_pinned"]
    if a.json:
        print(json.dumps(res, indent=1, ensure_ascii=False))
    else:
        for k, v in res.items():
            if isinstance(v, list):
                print(f"{k}: {len(v)}")
                for x in v[:50]:
                    print(f"  {x}")
            elif isinstance(v, dict):
                print(f"{k}:")
                for kk, vv in v.items():
                    print(f"  {kk}: {vv}")
            else:
                print(f"{k}: {v}")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
