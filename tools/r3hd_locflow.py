#!/usr/bin/env python3
"""M35: the translation workflow around tools/r3hd_loc.py: English catalog -> AI draft -> second-model review ->
human decisions -> validated, approved-only mod. No AI provider, API or network: the tool writes files you hand to
any model yourself and reads back what it returns, row by row, refusing rows whose id, check or codes were changed.

A project is a translation source of r3hd_loc.py (UTF-8 JSON, no game text: per string the source hash, the Turkish
text, a status and an optional pending review). Exports hold the English game text: keep them private (the tool
refuses to write them into the repository outside private/).

  status   draft         an AI (or other) first draft, not reviewed
           needs_review  sent back for another look (refresh: the game's source text changed; or a human's "redo")
           reviewed      a reviewer looked at it (its suggestion, if any, waits for a human decision)
           approved      a person accepted it; only a person's decision changes it again

usage:
  r3hd_locflow.py init PROJECT --id ID --name NAME            a new project (and its glyphs file) in a new folder
  r3hd_locflow.py export PROJECT OUT --for draft|review|human [--only SEL] [--ids I,..] [--category C] [--batch-size N]
        OUT ends in .csv / .tsv (spreadsheets, UTF-8 with BOM) or .jsonl (AI tools); with --batch-size OUT is a folder
        SEL: missing, draft, needs_review, reviewed, approved, pending (has a review suggestion), all (comma list)
  r3hd_locflow.py import PROJECT FILE --from draft|review|human [--label NAME] [--dry-run] [--overwrite-unapproved]
  r3hd_locflow.py status PROJECT [--report OUT.md]          counts, missing, stale, pending, invalid
  r3hd_locflow.py validate PROJECT [--glossary FILE]        every entry: encoding, codes, length, Turkish checks
  r3hd_locflow.py refresh PROJECT                           entries whose game text changed -> needs_review
  r3hd_locflow.py build PROJECT OUT [--zip] [--allow-unapproved]   approved strings only, unless the private override
  r3hd_locflow.py selftest
Common: --game-dir DIR, --json. Exit 0 ok, 1 problems found, 2 refused.
"""
import argparse
import csv
import io
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_loc as loc  # noqa: E402
import r3hd_mods as rm  # noqa: E402

ROOT = rm.ROOT
MODES = ("draft", "review", "human")
SELECT = ("missing", "draft", "needs_review", "reviewed", "approved", "pending", "all")
DECISIONS = ("approve", "accept", "reject", "redo")
CHECK_LEN = 12
COLUMNS = {
    "draft": ["id", "check", "kind", "category", "levels", "speakers", "max_bytes", "lines", "codes", "english",
              "turkish", "note"],
    "review": ["id", "check", "kind", "category", "levels", "speakers", "max_bytes", "lines", "codes", "english",
               "turkish", "status", "round", "verdict", "suggestion", "review_note"],
    # M37: origin (who drafted the current text), final (your own text for approve; empty = the turkish column),
    # human_note (kept as the string's note with any decision)
    "human": ["id", "check", "kind", "category", "levels", "speakers", "max_bytes", "english", "turkish", "origin",
              "status", "review_by", "verdict", "suggestion", "review_note", "problems", "final", "decision",
              "human_note", "text_check"],
}
REQUIRED = {"draft": {"id", "check", "turkish"}, "review": {"id", "check", "verdict", "turkish"},
            "human": {"id", "check", "decision", "text_check"}}
GLOSSARY_KIND = "r3hd-glossary"


class Problem(Exception):
    pass


# ---------------------------------------------------------------------------------------------------------------
# Text helpers

def tr_lower(s: str) -> str:
    """Turkish lower case (I -> ı, İ -> i), as str.lower() is not."""
    return s.replace("I", "ı").replace("İ", "i").lower()


def tr_upper(s: str) -> str:
    """M37: Turkish upper case (i -> İ, ı -> I), as str.upper() is not (it gives I for i)."""
    return s.replace("i", "İ").replace("ı", "I").upper()


# M37: tokens other than the in-band codes that the game fills in or draws specially: printf fields (%i, %d, %s), the
# code \b (the save icon \b¼ as one token; elsewhere ordinary text follows it, as in \bALL) and $ markers. The Turkish
# must keep the same multiset.
PLACEHOLDER_RE = re.compile(r"%[-+0#]*\d*(?:\.\d+)?[a-zA-Z]|\\b¼|\\b|\$")
# M37: what a spreadsheet writes into a cell when a formula failed (English and Turkish Excel / LibreOffice).
SHEET_ERRORS = re.compile(r"^#(NAME\?|VALUE!|REF!|DIV/0!|N/A|NUM!|NULL!|AD\?|DEĞER!|BAŞV!|SAYI/0!|YOK|SAYI!|BOŞ!)$")


def placeholders(text: str) -> list:
    return sorted(PLACEHOLDER_RE.findall(text))


def check_of(sha: str) -> str:
    return sha[:CHECK_LEN]


def state_check(text: str, suggestion: str, status: str) -> str:
    """M37 (review): the status is part of the check, so a sheet older than a newer decision is refused even when
    the decision kept the text (an approve after a redo, a redo after an approval). Sheets exported before M37 must
    be exported again."""
    return rm.sha256_bytes((text + "\0" + suggestion + "\0" + status).encode("utf-8"))[:CHECK_LEN]


def text_check(e) -> str:
    """The project's current text, suggestion and status as a human sheet saw them; empty for a missing entry."""
    if not e:
        return ""
    rv = e.get("review") or {}
    return state_check(e["text"], rv.get("suggestion", ""), f"{loc.status_of(e)}#{e.get('rev', '0')}")


def applied_hash(text: str) -> str:
    return rm.sha256_bytes(text.encode("utf-8"))[:CHECK_LEN]


def review_key(rv: dict) -> str:
    """M37 (review): a decided review, remembered as round:hash so that its sheet cannot bring it back."""
    h = rm.sha256_bytes(json.dumps([rv.get("by", ""), rv.get("verdict", ""), rv.get("suggestion", "")],
                                   ensure_ascii=False).encode("utf-8"))[:CHECK_LEN]
    return f"{rv.get('round', '0') or '0'}:{h}"


def codes(text: str) -> list:
    return sorted(c for c in loc.CODE_RE.findall(text) if c != "\\l")


def breaks(text: str) -> int:
    return text.count("\\l")


class Glyphs(frozenset):
    """M37: the Turkish letters a project adds, carrying the codes the game's font defines (`defined`, None without
    game data), so that every row check refuses a character the font cannot draw (; < > { } have no glyph), not only
    the build."""
    defined = None


def with_font(glyphs, defined) -> "Glyphs":
    g = Glyphs(glyphs)
    g.defined = frozenset(defined) if defined is not None else None
    return g


def encoded_len(text: str, glyphs) -> int:
    return len(rm.encode_text(text, glyphs, getattr(glyphs, "defined", None)))


# M36: what a machine finding means for a translator. The stage says where it fails: encoding (the game cannot store
# or draw the text), format (in-band codes and breaks), capacity (room in the game's files, checked when the mod is
# compiled), compatibility (the port version), layout (how it will look on screen), source (the entry against the
# game's catalog), review / style (advice). Matched against this tool's and r3hd_loc.py's own messages; the action
# is advice: nothing ever changes approved text.
SUB_LINES_SEEN = 2   # the subtitle banner was seen with one or two lines (RE_NOTES M35); more is untested
EXPLAIN = [
    (r"control character|real line break", "format", "no control characters",
     "replace a real line break with \\l and remove tabs"),
    (r"outside the game's 8-bit text range", "encoding", "8-bit text (Windows-1254)",
     "use letters of the game's code page only; replace typographic quotes, dashes and emoji"),
    (r"font has no glyph", "encoding", "a glyph for every character",
     "use a character the font draws, or add its glyph override (the project's glyphs file)"),
    (r"in-band codes (changed|differ)", "format", "in-band codes kept",
     "copy every code exactly as in the English (\\jc, \\f1:3\\f0:, ...); only \\l may move"),
    (r"placeholders changed", "format", "placeholders kept",
     "keep every %i / %d / %s, \\b<icon> and $ exactly as often as the English has them"),
    (r"spreadsheet error value", "format", "a text, not a formula",
     "retype the cell; begin it with an apostrophe if it starts with = + - @"),
    (r"subtitle has \d+ lines", "layout", "subtitle lines",
     "keep a subtitle to one or two lines (\\l); more is untested in the game"),
    (r"line breaks \(\\l\)|lines against", "layout", "line count",
     "keep the English line count unless you know the box fits more"),
    (r"widest line", "layout", "line width (the game never wraps)", "shorten the longest line or split it with \\l"),
    (r"for a slot of \d+: the build moves it", "capacity", "text slot",
     "nothing to do if this mod frees room elsewhere; the build says if it cannot"),
    (r"cannot move|no table pointer|largest free space", "capacity", "room for moved text",
     "shorten this string (the message gives the room), or shorten other strings of this mod to free room"),
    (r"subtitle of \d+ bytes", "capacity", "one subtitle (400 bytes)", "shorten this subtitle by the overage"),
    (r"subtitles need \d+ bytes more", "capacity", "subtitle table growth",
     "shorten subtitles of this mod by the overage the message gives"),
    (r"needs port version", "compatibility", "port version",
     "install the port version named, or shorten the subtitles so the table keeps its size"),
    (r"no room in the font atlas", "capacity", "glyph atlas", "add fewer new glyphs: reuse letters the font has"),
    (r"English changed", "source", "source hash", "run refresh, then check the Turkish against the new English"),
    (r"not in the game's catalog", "source", "known id", "correct the id (ids come from an export) or remove the entry"),
    (r"glossary", "review", "glossary term", "use the glossary's term, or note why not"),
    (r"identical to the English", "review", "translated", "translate it, or approve it as it is (a name)"),
    (r"pending suggestion", "review", "reviewer suggestion", "decide on the suggestion (human sheet)"),
    (r"ends with|starts in lower case|capital I|leading or trailing|double space", "style", "punctuation and case",
     "check against the English; keep it if intended"),
]


def explain(message: str) -> dict:
    """{stage, constraint, action} of one finding ('other' when no rule matches: then the message is all there is)."""
    for pattern, stage, constraint, action in EXPLAIN:
        if re.search(pattern, message):
            return {"stage": stage, "constraint": constraint, "action": action}
    return {"stage": "other", "constraint": "", "action": ""}


def findings_of(errors: list, warnings: list) -> list:
    """The validate messages as rows: id, severity, stage, constraint, detail, action (ids from the 'id: ' prefix)."""
    out = []
    for severity, msgs in (("error", errors), ("warning", warnings)):
        for msg in msgs:
            m = re.match(r"^((?:en|fr|de|it|es|vs)\.[\w.]+): (.*)$", msg, re.S)
            sid, detail = (m.group(1), m.group(2)) if m else ("", msg)
            out.append({"id": sid, "severity": severity, **explain(detail), "detail": detail})
    return out


def write_findings(path: Path, rows: list):
    """CSV (UTF-8 with BOM, for spreadsheets) or Markdown, by the file name; ids and messages only, no English."""
    cols = ["id", "severity", "stage", "constraint", "detail", "action"]
    if path.suffix.lower() == ".csv":
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\r\n")
        w.writerow(cols)
        w.writerows([sheet_cell(c, r.get(c, "")) for c in cols] for r in rows)
        atomic_write(path, b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"))
    else:
        lines = ["# Validation findings", "", f"{sum(r['severity'] == 'error' for r in rows)} errors, "
                 f"{sum(r['severity'] == 'warning' for r in rows)} warnings.", "",
                 "| id | severity | stage | constraint | detail | action |", "|---|---|---|---|---|---|"]
        lines += ["| " + " | ".join(str(r[c]).replace("|", "\\|") for c in cols) + " |" for r in rows]
        atomic_write(path, ("\n".join(lines) + "\n").encode("utf-8"))


def text_problems(sid: str, english: str, text: str, glyphs, row=None) -> tuple:
    """(errors, warnings) of a Turkish text against its English source: what a script can judge. Never the meaning,
    tone or humour: that is the reviewer's and the person's."""
    errors, warnings = [], []
    if any(ord(c) < 0x20 for c in text):
        errors.append("a control character or real line break (the game's line break is \\l)")
    try:
        n = encoded_len(text, glyphs)
    except rm.Refusal as x:
        errors.append(x.detail)
        n = None
    if codes(english) != codes(text):
        errors.append(f"in-band codes changed ({' '.join(codes(english)) or 'none'} -> {' '.join(codes(text)) or 'none'})")
    if placeholders(english) != placeholders(text):   # M37
        errors.append(f"placeholders changed ({' '.join(placeholders(english)) or 'none'} -> "
                      f"{' '.join(placeholders(text)) or 'none'})")
    if SHEET_ERRORS.match(text.strip()):   # M37: a formula error a spreadsheet saved instead of the text
        errors.append(f"a spreadsheet error value ({text.strip()}) instead of a text (a cell that began with = + - @?)")
    if breaks(english) != breaks(text):
        warnings.append(f"{breaks(text)} line breaks (\\l) against {breaks(english)} in the English")
    if text != text.strip() and english == english.strip():
        warnings.append("leading or trailing spaces")
    if "  " in text and "  " not in english:
        warnings.append("double space")
    if text.strip() == english.strip() and re.search(r"[A-Za-z]{3}", english) and len(english.strip()) > 3:
        warnings.append("identical to the English (not translated?)")
    pe, pt = english.rstrip()[-1:], text.rstrip()[-1:]
    if pe in "?!." and pe and pt != pe and not (pe == "." and pt in "!?…"):
        warnings.append(f"ends with {pt!r}, the English with {pe!r}")
    le = re.search(r"[A-Za-zÀ-ÿ]", english)
    lt = re.search(r"[A-Za-zÀ-ÿğĞşŞıİ]", text)
    if le and lt and le.group().isupper() and lt.group().islower():
        warnings.append("starts in lower case, the English in upper case")
    for w in re.findall(r"[A-Za-zÀ-ÿğĞşŞıİ]{2,}", text):
        if w.isupper() and "I" in w:
            warnings.append(f"capital I in the all-caps word {w!r}: Turkish writes i in capitals as İ (dotless ı as I)")
            break
    if row is not None and n is not None and row.get("kind") == "text" and isinstance(row.get("capacity"), int) \
            and n > row["capacity"]:
        warnings.append(f"{n} bytes for a slot of {row['capacity']}: the build moves it if this mod frees room")
    if row is not None and row.get("kind") == "subtitle":   # M36
        if n is not None and n > rm.SUB_MAX_TEXT:
            errors.append(f"subtitle of {n} bytes: at most {rm.SUB_MAX_TEXT} (shorten by {n - rm.SUB_MAX_TEXT})")
        if breaks(text) + 1 > SUB_LINES_SEEN:
            warnings.append(f"subtitle has {breaks(text) + 1} lines: the banner was seen with one or two")
    return errors, warnings


# ---------------------------------------------------------------------------------------------------------------
# Project I/O

def write_project(path: Path, src: dict):
    """Deterministic: strings in game order, one per line; the previous file kept as .bak; atomic replace."""
    head = {k: v for k, v in src.items() if k != "strings"}
    order = ("source_sha256", "status", "text", "origin", "note", "context", "review", "review_closed", "rev",
             "applied", "alt")
    lines = ["{"]
    for k, v in head.items():
        lines.append(f"  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},")
    lines.append('  "strings": {')
    ids = sorted(src["strings"], key=loc.sid_key)
    for i, sid in enumerate(ids):
        e = src["strings"][sid]
        e = {k: e[k] for k in order if k in e}
        lines.append(f"    {json.dumps(sid)}: {json.dumps(e, ensure_ascii=False)}" + ("," if i < len(ids) - 1 else ""))
    lines += ["  }", "}"]
    data = ("\n".join(lines) + "\n").encode("utf-8")
    json.loads(data)   # always valid JSON
    if path.exists():
        shutil.copyfile(path, path.with_name(path.name + ".bak"))
    atomic_write(path, data)


def project_glyphs(src: dict, base: Path) -> frozenset:
    try:
        return frozenset(o["char"] for o in loc.glyph_overrides(src, base))
    except (OSError, ValueError, KeyError) as x:
        raise Problem(f"the glyphs file named by the project cannot be read: {x}")


def private_path(out: Path):
    """Exports hold game text: never into the repository outside private/."""
    p = out.resolve()
    try:
        rel = p.relative_to(ROOT.resolve())
    except ValueError:
        # M36: nor into another Git work tree (a translation repository such as rayman3hd-turkish) outside a folder
        # named private/ there (keep that folder ignored, as here): an export must never be committed.
        for parent in p.parents:
            if (parent / ".git").exists():
                if "private" not in p.relative_to(parent).parts[:-1]:
                    raise Problem(f"{out}: an export holds the game's text and {parent} is a Git repository; write it "
                                  "under a git-ignored private/ folder there, or outside any repository")
                break
        return
    if not rel.parts or rel.parts[0] != "private":
        raise Problem(f"{out}: an export holds the game's text; write it under private/ or outside the repository")


# ---------------------------------------------------------------------------------------------------------------
# Tables (CSV / TSV / JSONL)

# M37: spreadsheet safety. A cell that begins with = + - @ (or a tab / CR) is a formula to Excel, LibreOffice and
# Google Sheets: such cells are written with a leading apostrophe (and one that already begins with apostrophes before
# such a character gets one more), which import removes again, so every text round-trips. The hexadecimal checks are
# written as #<hex> so that a spreadsheet cannot turn them into numbers (12e45 -> 1.2E+46, leading zeros dropped).
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
HEX_COLUMNS = ("check", "text_check")


def sheet_cell(col: str, v) -> str:
    v = "" if v is None else str(v)
    if col in HEX_COLUMNS and v:
        return "#" + v
    if v[:1] in FORMULA_START or (v[:1] == "'" and v.lstrip("'")[:1] in FORMULA_START and v.lstrip("'")):
        return "'" + v
    return v


def sheet_value(col: str, v: str) -> str:
    if col in HEX_COLUMNS and v.startswith("#"):
        return v[1:]
    if v[:1] == "'" and v.lstrip("'")[:1] in FORMULA_START and v.lstrip("'"):
        return v[1:]
    return v


def atomic_write(path: Path, data: bytes):
    """M37: a whole file or none (temporary file in the same folder, then replace)."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=path.suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_table(path: Path, columns: list, rows: list):
    private_path(path)
    ext = path.suffix.lower()
    if ext == ".jsonl":
        data = "".join(json.dumps({c: r.get(c, "") for c in columns}, ensure_ascii=False) + "\n" for r in rows)
        atomic_write(path, data.encode("utf-8"))
    elif ext in (".csv", ".tsv"):
        buf = io.StringIO()
        w = csv.writer(buf, delimiter="\t" if ext == ".tsv" else ",", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        w.writerow(columns)
        for r in rows:
            w.writerow([sheet_cell(c, r.get(c, "")) for c in columns])
        atomic_write(path, b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"))
    else:
        raise Problem(f"{path.name}: an export is .csv, .tsv or .jsonl")


def read_table(path: Path) -> list:
    """[(line number, {column: text})]; refuses what is not a table of the expected shape."""
    raw = path.read_bytes()
    if len(raw) > (32 << 20):
        raise Problem(f"{path.name} is too large")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Problem(f"{path.name} is not UTF-8 (save it as UTF-8 / CSV UTF-8)")
    ext = path.suffix.lower()
    out = []
    if ext in (".jsonl", ".json"):
        if ext == ".json":
            try:
                items = json.loads(text)
            except ValueError as x:
                raise Problem(f"{path.name}: not JSON: {x}")
            if not isinstance(items, list):
                raise Problem(f"{path.name}: a JSON import is a list of rows")
            pairs = list(enumerate(items, 1))
        else:
            pairs = []
            for n, line in enumerate(text.split("\n"), 1):
                if line.strip():
                    try:
                        pairs.append((n, json.loads(line)))
                    except ValueError as x:
                        raise Problem(f"{path.name} line {n}: not JSON: {x}")
        for n, item in pairs:
            if not isinstance(item, dict):
                raise Problem(f"{path.name} row {n}: not an object")
            out.append((n, {str(k): ("" if v is None else v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
                            for k, v in item.items()}))
    elif ext in (".csv", ".tsv"):
        delim = "\t" if ext == ".tsv" else ","
        first = text.split("\n", 1)[0]
        if ext == ".csv" and ";" in first and "," not in first:
            delim = ";"   # M37: Excel in a Turkish (or other) locale saves "CSV" with semicolons
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
        if not rows:
            raise Problem(f"{path.name} is empty")
        head = [h.strip() for h in rows[0]]
        if len(set(head)) != len(head):
            raise Problem(f"{path.name}: a column name appears twice")
        for n, r in enumerate(rows[1:], 2):
            if not any(c.strip() for c in r):
                continue
            if len(r) > len(head) and any(c.strip() for c in r[len(head):]):
                raise Problem(f"{path.name} line {n}: more cells than columns (a separator inside a cell?)")
            out.append((n, {h: sheet_value(h, r[i] if i < len(r) else "") for i, h in enumerate(head)}))
    else:
        raise Problem(f"{path.name}: an import is .csv, .tsv, .jsonl or .json")
    return out


# ---------------------------------------------------------------------------------------------------------------
# Catalog and rows

def catalog_index(rows: list) -> dict:
    return {r["id"]: r for r in rows if "source_sha256" in r}


def row_of(c: dict, e) -> dict:
    """The export row of one catalog entry and its project entry (or None)."""
    r = {"id": c["id"], "check": check_of(c["source_sha256"]), "kind": c["kind"], "category": c.get("category", ""),
         "levels": " ".join(c.get("levels", [])), "speakers": " ".join(c.get("speakers", [])),
         "max_bytes": c["capacity"] if c["kind"] == "text" else rm.SUB_MAX_TEXT if c["kind"] == "subtitle" else "", "lines": breaks(c["text"]) + 1,
         "codes": " ".join(codes(c["text"])), "english": c["text"]}
    if c["kind"] == "subtitle":
        r["category"] = c.get("category", "") + (f" {c['movie_file']}" if c.get("movie_file") else f" (movie {c['movie']})")
    if e:
        r.update(turkish=e["text"], status=loc.status_of(e), note=e.get("note", ""),
                 origin=e.get("origin", "" if "status" in e else "hand-written (no status)"))
        rv = e.get("review") or {}
        r.update(review_by=rv.get("by", ""), verdict=rv.get("verdict", "") if rv else "",
                 suggestion=rv.get("suggestion", ""), review_note=rv.get("note", ""), review_round=rv.get("round", ""))
    else:
        r.update(turkish="", status="missing")
    return r


def selection(sel: str, mode: str) -> set:
    default = {"draft": "missing", "review": "draft,needs_review", "human": "draft,needs_review,reviewed,pending"}[mode]
    items = {s.strip() for s in (sel or default).split(",") if s.strip()}
    bad = items - set(SELECT)
    if bad:
        raise Problem(f"--only {','.join(sorted(bad))}: one of {', '.join(SELECT)}")
    return items


def wanted(items: set, e) -> bool:
    if "all" in items:
        return True
    if e is None:
        return "missing" in items
    return loc.status_of(e) in items or ("pending" in items and bool((e.get("review") or {}).get("suggestion")))


def id_filter(spec: str):
    """--ids: a comma list of ids, or prefixes ending in '.' (vs.en.42. = every cue of movie 42)."""
    items = [s.strip() for s in spec.split(",") if s.strip()]
    if not items:
        return lambda sid: True
    return lambda sid: any(sid == i or (i.endswith(".") and sid.startswith(i)) for i in items)


def cmd_export(src, base, cat_rows, out: Path, mode: str, only: str, category: str, batch: int, glyphs,
               ids: str = "", annotate=None, columns=None, review_round: int = 0) -> dict:
    """M37: `ids` may also be a set of ids; `annotate(row, catalog entry)` adds columns (and may return False to leave
    the row out); `columns` replaces the mode's columns; `review_round` is written into review rows."""
    items = selection(only, mode)
    cat = catalog_index(cat_rows)
    keep = (lambda sid: sid in ids) if isinstance(ids, (set, frozenset)) else id_filter(ids)
    rows = []
    for sid in sorted(cat, key=loc.sid_key):
        c, e = cat[sid], src["strings"].get(sid)
        if not keep(sid) or not wanted(items, e) or not c["text"].strip():
            continue
        if category and category not in (c.get("category") or "uncategorised"):
            continue
        r = row_of(c, e)
        if mode == "review":
            r["round"] = str(review_round) if review_round else ""
        if annotate is not None and annotate(r, c) is False:
            continue
        if mode == "human":
            probs = []
            for t in [e["text"]] if e else []:
                er, wa = text_problems(sid, c["text"], t, glyphs, c)
                probs += er + wa
            if e and e["source_sha256"] != c["source_sha256"]:
                probs.insert(0, "the game's English changed since this was translated")
            r["problems"] = "; ".join(probs)
            r["text_check"] = text_check(e)
        rows.append(r)
    cols = columns or COLUMNS[mode]
    files = []
    if batch:
        if out.suffix.lower() in (".csv", ".tsv", ".jsonl", ".json"):
            raise Problem("with --batch-size, OUT is a folder (the batches are batch_001.<ext>; give --ext)")
        private_path(out)
        out.mkdir(parents=True, exist_ok=True)
        for k in range(0, max(len(rows), 1), batch):
            p = out / f"batch_{k // batch + 1:03d}{EXT[0]}"
            write_table(p, cols, rows[k:k + batch])
            files.append(str(p))
    else:
        write_table(out, cols, rows)
        files.append(str(out))
    return {"rows": len(rows), "files": files, "mode": mode, "selected": sorted(items),
            "note": "holds the game's English text: keep it private; send it to an AI service only if you choose to"}


EXT = [".jsonl"]


# ---------------------------------------------------------------------------------------------------------------
# Import

def already_applied(d: str, r: dict, e) -> bool:
    """M36: whether a human row whose text_check no longer matches is this very decision, already in the project (the
    same sheet imported twice): then it is a no-op, not a stale sheet. Anything else that changed since the export
    (a newer decision, a new review) still refuses the row."""
    if not e or e.get("review"):
        return False
    shown = str(r.get("suggestion", ""))
    exported = state_check(e["text"], shown, f"{loc.status_of(e)}#{e.get('rev', '0')}")
    if d == "approve":
        t = r.get("final", "") if str(r.get("final", "")).strip() else r.get("turkish", "")
        return e.get("status") == "approved" and e["text"] == t
    if d == "accept":
        return bool(shown) and e.get("status") == "approved" and e["text"] == shown \
            and str(e.get("origin", "")).startswith("review:")
    if d == "reject":
        return bool(shown) and exported == str(r.get("text_check", "")).strip()
    return False


def cmd_import(src, base, cat_rows, table: list, mode: str, label: str, overwrite_unapproved: bool, glyphs) -> dict:
    cat = catalog_index(cat_rows)
    rep = {"mode": mode, "rows": len(table), "changed": [], "unchanged": 0, "skipped": [], "rejected": [], "warnings": []}
    if table:
        cols = set(table[0][1])
        missing = REQUIRED[mode] - cols
        if missing:
            raise Problem(f"the {mode} import needs the columns {', '.join(sorted(missing))} (have {', '.join(sorted(cols))})")
    seen = {}
    for n, r in table:
        seen.setdefault(str(r.get("id", "")).strip(), []).append(n)
    dups = {k for k, v in seen.items() if len(v) > 1}

    def reject(n, sid, why):
        rep["rejected"].append({"row": n, "id": sid, "reason": why})

    for n, r in table:
        sid = str(r.get("id", "")).strip()
        if sid in dups:
            reject(n, sid, f"the id appears {len(seen[sid])} times in the file (rows {', '.join(map(str, seen[sid]))})")
            continue
        c = cat.get(sid)
        if c is None:
            reject(n, sid, "unknown id (changed or invented by the model?)")
            continue
        if str(r.get("check", "")).strip().lower() != check_of(c["source_sha256"]):
            reject(n, sid, "the check does not match the id (row ids shifted or edited?)")
            continue
        if "english" in r and r["english"] != "" and r["english"] != c["text"]:
            reject(n, sid, "the English source text in the row was changed")
            continue
        e = src["strings"].get(sid)
        if e is not None and e["source_sha256"] != c["source_sha256"]:
            reject(n, sid, "the game's English changed since this was translated: run refresh, then review it")
            continue
        status = loc.status_of(e) if e else "missing"

        def validated(text, what):
            er, wa = text_problems(sid, c["text"], text, glyphs, c)
            if er:
                reject(n, sid, f"{what}: {'; '.join(er)}")
                return False
            rep["warnings"] += [{"id": sid, "warning": f"{what}: {w}"} for w in wa]
            return True

        if mode == "draft":
            t = r.get("turkish", "")
            if not t.strip():
                rep["skipped"].append({"id": sid, "reason": "no Turkish text in the row"})
                continue
            if status == "approved":
                rep["skipped"].append({"id": sid, "reason": "approved: kept (a draft never replaces an approved text)"})
                continue
            if status in ("needs_review", "reviewed") and not overwrite_unapproved:
                rep["skipped"].append({"id": sid, "reason": f"{status}: kept (--overwrite-unapproved replaces it)"})
                continue
            if not validated(t, "draft"):
                continue
            if e and e["text"] == t and status == "draft":
                rep["unchanged"] += 1
                continue
            new = {"source_sha256": c["source_sha256"], "status": "draft", "text": t, "origin": f"draft:{label}"}
            if e and e.get("note"):
                new["note"] = e["note"]
            if e:   # M39: a later draft keeps the revision counter and the alternatives, and the replaced draft
                if e.get("rev"):
                    new["rev"] = e["rev"]
                alts = [dict(x) for x in e.get("alt") or []]
                if not any(x["text"] == e["text"] for x in alts):
                    alts.append({"text": e["text"], "by": e.get("origin", ""), "kind": "previous_draft",
                                 "reason": f"replaced by draft:{label}"})
                new["alt"] = alts
            if r.get("note", "").strip() and not new.get("note"):
                new["note"] = r["note"].strip()[:500]
            src["strings"][sid] = new
            rep["changed"].append(sid)
        elif mode == "review":
            v = str(r.get("verdict", "")).strip().lower()
            if not v:
                rep["skipped"].append({"id": sid, "reason": "no verdict"})
                continue
            if v not in loc.VERDICTS:
                reject(n, sid, f"verdict {v!r} (one of {', '.join(loc.VERDICTS)})")
                continue
            if e is None:
                reject(n, sid, "no Turkish text to review in the project")
                continue
            if "turkish" in r and r["turkish"] != e["text"]:
                reject(n, sid, "the reviewed Turkish is not the project's current text (an older export, or the "
                       "reviewer edited it: put changes in 'suggestion')")
                continue
            s = r.get("suggestion", "")
            if v == "change" and not s.strip():
                reject(n, sid, "verdict change without a suggestion")
                continue
            # M37: review rounds. A sheet of an earlier round never replaces a pending review of a later one.
            rnd = str(r.get("round", "")).strip()
            if rnd and not rnd.isdigit():
                reject(n, sid, f"round {rnd!r} is not a number")
                continue
            held = str((e.get("review") or {}).get("round", "") or "0")
            if int(held) > int(rnd or 0):
                reject(n, sid, f"a review of round {held} is pending; this sheet is round {rnd or 'unnumbered'} "
                       "(an older sheet)")
                continue
            # M37 (review): a review a person already decided never comes back, nor one of an earlier round
            closed = str(e.get("review_closed", ""))
            if closed:
                incoming = {"by": label, "verdict": v, "round": str(int(rnd)) if rnd and rnd != "0" else "",
                            "suggestion": s if s.strip() and s != e["text"] else ""}
                if review_key(incoming) == closed:
                    rep["unchanged"] += 1
                    rep["skipped"].append({"id": sid, "reason": "this review was already decided"})
                    continue
                if rnd and int(rnd) <= int(closed.split(":")[0]):
                    reject(n, sid, f"round {closed.split(':')[0]} of this string was already decided; this sheet "
                           f"is round {rnd} (an older sheet)")
                    continue
            if s.strip() and s != e["text"] and not validated(s, "suggestion"):
                continue
            rv = {"by": label, "verdict": v}
            if rnd and rnd != "0":
                rv["round"] = str(int(rnd))
            if s.strip() and s != e["text"]:
                rv["suggestion"] = s
            if r.get("review_note", "").strip():
                rv["note"] = r["review_note"].strip()[:1000]
            e = dict(e)
            e["review"] = rv   # kept (also an "ok") until a person decides, so the human sheet shows who said what
            if status != "approved":
                e["status"] = "reviewed"
            if e == src["strings"][sid]:
                rep["unchanged"] += 1
                continue
            src["strings"][sid] = e
            rep["changed"].append(sid)
            if status == "approved" and rv.get("suggestion"):
                rep["warnings"].append({"id": sid, "warning": "approved text kept; the suggestion waits for a decision"})
        else:
            d = str(r.get("decision", "")).strip().lower()
            if not d:
                rep["unchanged"] += 1
                continue
            if d not in DECISIONS:
                reject(n, sid, f"decision {d!r} (one of {', '.join(DECISIONS)}, or empty)")
                continue
            row_check = str(r.get("text_check", "")).strip()
            if d == "approve":
                wants = str(r.get("final", "")) if str(r.get("final", "")).strip() else r.get("turkish", "")
            elif d == "accept":
                wants = str(r.get("suggestion", ""))
            else:
                wants = e["text"] if e else ""
            if e and row_check and wants == e["text"] and \
                    e.get("applied") == f"{d}:{row_check}:{applied_hash(e['text'])}":   # M37: this row, applied before
                rep["unchanged"] += 1
                rep["skipped"].append({"id": sid, "reason": f"{d}: already applied"})
                continue
            if row_check != text_check(e):
                if already_applied(d, r, e) and not e.get("rev"):   # M36: the same sheet again (pre-M37 entries)
                    rep["unchanged"] += 1
                    rep["skipped"].append({"id": sid, "reason": f"{d}: already applied"})
                    continue
                reject(n, sid, "the project's text changed since this sheet was exported (export a new one)")
                continue
            rv = (e or {}).get("review") or {}
            final = str(r.get("final", ""))
            if final.strip() and d != "approve":
                reject(n, sid, f"{d} with a text in 'final': only approve takes your own text (or clear 'final')")
                continue
            if d == "approve":
                t = final if final.strip() else r.get("turkish", "")
                if not t.strip():
                    reject(n, sid, "approve needs the Turkish text in the row")
                    continue
                if not validated(t, "approved text"):
                    continue
                new = dict(e or {"source_sha256": c["source_sha256"]})
                new.update(status="approved", text=t)
                if not e or t != e["text"]:
                    new["origin"] = "human"
                new.pop("review", None)
            elif d == "accept":
                if not rv.get("suggestion"):
                    reject(n, sid, "accept: there is no pending suggestion")
                    continue
                if "suggestion" in r and r["suggestion"] != rv["suggestion"]:
                    reject(n, sid, "accept: the row's suggestion is not the stored one (edit 'turkish' and approve instead)")
                    continue
                if not validated(rv["suggestion"], "accepted suggestion"):
                    continue
                new = dict(e)
                new.update(status="approved", text=rv["suggestion"], origin=f"review:{rv.get('by', '')}")
                new.pop("review", None)
            elif d == "reject":
                if e is None or not rv:
                    reject(n, sid, "reject: there is no pending review")
                    continue
                new = dict(e)
                new.pop("review", None)
            else:   # redo
                if e is None:
                    reject(n, sid, "redo: nothing to send back")
                    continue
                new = dict(e)
                new["status"] = "needs_review"
            if rv and "review" not in new:   # M37 (review): remember the decided review
                new["review_closed"] = review_key(rv)
            hn = str(r.get("human_note", "")).strip()
            if hn:   # M37: the person's note, kept with the decision (a refresh marker stays)
                old = str((e or {}).get("note", ""))
                mark = old[old.index("[source changed"):] if "[source changed" in old else ""
                new["note"] = (hn[:500 - len(mark) - 1] + (" " + mark if mark else "")).strip()
            if new == e:
                rep["unchanged"] += 1
                continue
            # M37 (review): every applied decision counts, so an older sheet whose text and status happen to match
            # again (redo, then approve) is still refused; the row itself is remembered for a repeated import.
            new["rev"] = str(int((e or {}).get("rev", "0") or "0") + 1)
            new["applied"] = f"{d}:{row_check}:{applied_hash(new['text'])}"
            src["strings"][sid] = new
            rep["changed"].append(sid)
    rep["changed_count"] = len(rep["changed"])
    return rep


# ---------------------------------------------------------------------------------------------------------------
# Status, validation, refresh

def load_glossary(path) -> list:
    if not path:
        return []
    try:
        g = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as x:
        raise Problem(f"glossary: {x}")
    if not isinstance(g, dict) or g.get("kind") != GLOSSARY_KIND or not isinstance(g.get("terms"), list):
        raise Problem(f"glossary: not a {GLOSSARY_KIND} file (see config/localization/tr/glossary.example.json)")
    out = []
    for i, t in enumerate(g["terms"]):
        if not isinstance(t, dict) or not isinstance(t.get("en"), str) or not t["en"].strip() \
                or not isinstance(t.get("tr", []), list) or not isinstance(t.get("avoid", []), list):
            raise Problem(f"glossary term {i}: needs 'en' and lists 'tr' / 'avoid'")
        out.append(t)
    return out


def glossary_warnings(english: str, text: str, terms: list) -> list:
    out = []
    lt = tr_lower(text)
    for t in terms:
        if not re.search(r"(?<![A-Za-z])" + re.escape(t["en"].lower()), english.lower()):
            continue
        want = [tr_lower(x) for x in t.get("tr", []) if x]
        if want and not any(w in lt for w in want):
            out.append(f"glossary: '{t['en']}' is usually {' / '.join(t['tr'])}")
        for a in t.get("avoid", []):
            if a and tr_lower(a) in lt:
                out.append(f"glossary: '{a}' is listed to avoid for '{t['en']}'")
    return out


def subtitle_budget(src, cat, glyphs, statuses=None) -> int:
    """Bytes the project's subtitles add to VS.sub (negative = room left). Above 0 the table grows (M36: port 0.36.0
    or newer, at most rm.SUB_MAX_GROW bytes). `statuses` limits it to those (None = all)."""
    delta = 0
    for sid, e in src["strings"].items():
        c = cat.get(sid)
        if c is None or c["kind"] != "subtitle" or (statuses and loc.status_of(e) not in statuses):
            continue
        try:
            delta += encoded_len(e["text"], glyphs) - c.get("bytes", len(c["text"]))
        except rm.Refusal:
            continue
    return delta


def cmd_status(src, cat_rows, report, glyphs=frozenset()) -> dict:
    cat = catalog_index(cat_rows)
    counts = {s: 0 for s in loc.STATUSES}
    stale, pending, unknown = [], [], []
    for sid, e in src["strings"].items():
        counts[loc.status_of(e)] += 1
        c = cat.get(sid)
        if c is None:
            unknown.append(sid)
        elif e["source_sha256"] != c["source_sha256"]:
            stale.append(sid)
        if (e.get("review") or {}).get("suggestion"):
            pending.append(sid)
    missing = [sid for sid, c in cat.items() if sid not in src["strings"] and c["text"].strip()]
    by_kind = {}
    for sid in missing:
        k = cat[sid]["kind"] + (" (voiced)" if cat[sid].get("category") == "voiced line" else "")
        by_kind[k] = by_kind.get(k, 0) + 1
    res = {"translatable": sum(1 for c in cat.values() if c["text"].strip()), "entries": len(src["strings"]),
           "status": counts, "missing": len(missing), "missing_by_kind": by_kind, "stale": stale,
           "pending_suggestions": len(pending), "unknown_ids": unknown,
           "unreviewed": counts["draft"] + counts["needs_review"],
           "subtitle_bytes_vs_english": {"all": subtitle_budget(src, cat, glyphs),
                                         "approved": subtitle_budget(src, cat, glyphs, ("approved",)),
                                         "limit": rm.SUB_MAX_GROW,
                                         "note": f"above 0 the movie subtitle table grows (needs port "
                                                 f"{rm.SUB_GROW_PORT} or newer); it may grow by at most "
                                                 f"{rm.SUB_MAX_GROW} bytes"}}
    if report:
        lines = ["# Translation status", "", f"Entries {res['entries']} of {res['translatable']} translatable strings.", "",
                 "| status | count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in counts.items()] + \
                [f"| missing | {len(missing)} |", "", f"Pending reviewer suggestions: {len(pending)}", ""]
        for title, ids in (("Stale (the game's text changed)", stale), ("Unknown ids", unknown),
                           ("Pending suggestions", pending), ("Missing", missing)):
            if ids:
                lines += [f"## {title} ({len(ids)})", "", ", ".join(sorted(ids, key=loc.sid_key)), ""]
        Path(report).write_text("\n".join(lines) + "\n", encoding="utf-8")
        res["report"] = str(report)
    return res


def cmd_validate(src, base, cat_rows, glyphs, terms, paths=None, source=None, report=None) -> dict:
    cat = catalog_index(cat_rows)
    errors, warnings = [], []
    for sid in sorted(src["strings"], key=loc.sid_key):
        e, c = src["strings"][sid], cat.get(sid)
        if c is None:
            errors.append(f"{sid}: not in the game's catalog")
            continue
        if e["source_sha256"] != c["source_sha256"]:
            errors.append(f"{sid}: the game's English changed since this was translated (refresh)")
            continue
        er, wa = text_problems(sid, c["text"], e["text"], glyphs, c)
        wa += glossary_warnings(c["text"], e["text"], terms)
        rv = e.get("review") or {}
        if rv.get("suggestion"):
            er2, _ = text_problems(sid, c["text"], rv["suggestion"], glyphs, c)
            wa += [f"pending suggestion: {x}" for x in er2]
        errors += [f"{sid}: {x}" for x in er]
        warnings += [f"{sid}: {x}" for x in wa]
    res = {"entries": len(src["strings"]), "errors": errors, "warnings": warnings,
           "note": "machine checks only: meaning, tone, humour and characterisation need a reviewer and a person"}
    if paths is not None and not errors and src["strings"]:
        whole = loc.cmd_check(paths, source, None, src)   # the whole project as one mod: room, glyphs, layout
        res["build_check"] = {"errors": whole["errors"], "warnings": len(whole["warnings"]), "moved": whole.get("moved", 0)}
        res["errors"] += whole["errors"]
        res["warnings"] += [w for w in whole["warnings"] if w not in res["warnings"]]
        if whole.get("subtitle_growth"):
            res["subtitle_growth"] = whole["subtitle_growth"]
    res["findings"] = findings_of(res["errors"], res["warnings"])
    res["by_stage"] = {}
    for f in res["findings"]:
        k = f"{f['severity']}:{f['stage']}"
        res["by_stage"][k] = res["by_stage"].get(k, 0) + 1
    if report:
        write_findings(Path(report), res["findings"])
        res["report"] = str(report)
    return res


def cmd_refresh(src, cat_rows) -> dict:
    cat = catalog_index(cat_rows)
    changed = []
    for sid, e in src["strings"].items():
        c = cat.get(sid)
        if c is not None and e["source_sha256"] != c["source_sha256"]:
            e["source_sha256"] = c["source_sha256"]
            e["status"] = "needs_review"
            e["note"] = (e.get("note", "") + " [source changed: check against the new English]").strip()[:500]
            changed.append(sid)
    return {"stale_marked": changed}


def cmd_init(path: Path, mid: str, name: str) -> dict:
    if path.exists():
        raise Problem(f"{path} exists")
    if not rm.ID_RE.match(mid):
        raise Problem("--id: 2-64 characters of a-z 0-9 . _ - (lower case), e.g. tr.full")
    path.parent.mkdir(parents=True, exist_ok=True)
    gsrc = ROOT / "config" / "localization" / "tr" / "glyphs.json"
    if not (path.parent / "glyphs.json").exists():
        shutil.copyfile(gsrc, path.parent / "glyphs.json")
    src = {"format": 1, "kind": loc.KIND, "id": mid, "name": name, "version": "0.1.0",
           "description": "A Turkish translation of the game's text (approved strings only in a normal build).",
           "authors": [], "license": "Your choice; it holds no game text.",
           "language": {"source": "en", "target": "tr", "name": "Türkçe"},
           "target": {"title_id": rm.TITLE_ID, "releases": ["x360-xbla-5841123F-v1"], "min_port_version": "0.35.0"},
           "glyphs": "glyphs.json", "strings": {}}
    write_project(path, src)
    return {"project": str(path), "glyphs": str(path.parent / "glyphs.json")}


def load_project(path: Path) -> dict:
    """Like r3hd_loc.load_source, but a new project may have no strings yet."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and raw.get("strings") == {}:
        tmp = dict(raw, strings={"en.0": {"source_sha256": "0" * 64, "text": "x"}})
        fd, t = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(tmp, f)
        try:
            loc.load_source(Path(t))
        finally:
            os.unlink(t)
        return raw
    return loc.load_source(path)


# ---------------------------------------------------------------------------------------------------------------

def selftest() -> int:
    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ' :: ' + str(detail)}")

    def sha(s):
        return rm.sha256_bytes(s.encode())
    # A synthetic catalog (original illustrative strings, not game text).
    cat = [{"id": "en.1", "kind": "text", "text": "Start the race", "capacity": 15, "source_sha256": sha("a"), "category": ""},
           {"id": "en.2", "kind": "text", "text": "\\jcPress \\f1:3\\f0: to jump", "capacity": 31, "source_sha256": sha("b"),
            "category": ""},
           {"id": "en.3", "kind": "text", "text": "The lantern is lit.", "capacity": 19, "source_sha256": sha("c"),
            "category": "voiced line", "levels": ["demo_10"], "speakers": ["Abcd"]},
           {"id": "vs.en.7.0", "kind": "subtitle", "text": "Over the hill!", "source_sha256": sha("d"),
            "category": "movie subtitle", "movie": 7, "movie_file": ""}]
    glyphs = frozenset("ğĞşŞıİ")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        proj = td / "p" / "tr.json"
        cmd_init(proj, "tr.test", "Test")
        src = load_project(proj)
        check("init: an empty project loads", src["strings"] == {} and (td / "p" / "glyphs.json").is_file())
        # draft export: every row is missing; JSONL and CSV round trip with ids and checks
        out = td / "d.jsonl"
        r = cmd_export(src, proj.parent, cat, out, "draft", "", "", 0, glyphs)
        rows = read_table(out)
        check("export draft: four missing rows with checks", r["rows"] == 4 and rows[0][1]["check"] == sha("a")[:12])
        csvp = td / "d.csv"
        cmd_export(src, proj.parent, cat, csvp, "draft", "", "", 0, glyphs)
        check("export: CSV with BOM reads back the same cells",
              csvp.read_bytes()[:3] == b"\xef\xbb\xbf" and [x[1]["english"] for x in read_table(csvp)]
              == [x[1]["english"] for x in rows])
        # an AI draft: one good row, one with a changed id, one with a dropped code, one duplicate pair, one edited English
        ai = [dict(rows[0][1], turkish="Yarışı başlat"),
              dict(rows[1][1], turkish="\\jc\\f1:3\\f0: ile zıpla"),
              dict(rows[1][1], id="en.9", turkish="x"),
              dict(rows[2][1], turkish="Fener yandı."), dict(rows[2][1], turkish="Fener yanıyor."),
              dict(rows[3][1], english="Over the hills!", turkish="Tepenin ardına!")]
        (td / "ai.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ai), encoding="utf-8")
        rep = cmd_import(src, proj.parent, cat, read_table(td / "ai.jsonl"), "draft", "model-a", False, glyphs)
        why = {x["id"]: x["reason"] for x in rep["rejected"]}
        check("import draft: good rows taken as draft", rep["changed"] == ["en.1", "en.2"]
              and src["strings"]["en.1"]["status"] == "draft", rep)
        check("import draft: an unknown id is refused", "unknown" in why.get("en.9", ""), why)
        check("import draft: a duplicated id is refused (both rows)", "times" in why.get("en.3", ""), why)
        check("import draft: an edited English source is refused", "English" in why.get("vs.en.7.0", ""), why)
        bad = [dict(rows[1][1], turkish="Zıplamak için bas")]
        rep = cmd_import(src, proj.parent, cat, list(enumerate(bad, 1)), "draft", "m", False, glyphs)
        check("import draft: a dropped in-band code is refused", rep["rejected"] and "codes" in rep["rejected"][0]["reason"])
        shifted = [dict(rows[0][1], id="en.2", turkish="x y")]
        rep = cmd_import(src, proj.parent, cat, list(enumerate(shifted, 1)), "draft", "m", False, glyphs)
        check("import draft: a shifted id (check of another row) is refused", "check" in rep["rejected"][0]["reason"])
        emoji = [dict(rows[0][1], turkish="Başla ✓")]
        rep = cmd_import(src, proj.parent, cat, list(enumerate(emoji, 1)), "draft", "m", False, glyphs)
        check("import draft: a character the game cannot draw is refused", bool(rep["rejected"]))
        # review: a change suggestion and an ok; text never overwritten
        rv = [{"id": "en.1", "check": sha("a")[:12], "turkish": "Yarışı başlat", "verdict": "change",
               "suggestion": "Yarışa başla", "review_note": "more natural"},
              {"id": "en.2", "check": sha("b")[:12], "turkish": "\\jc\\f1:3\\f0: ile zıpla", "verdict": "ok"},
              {"id": "en.1", "check": sha("a")[:12], "turkish": "x", "verdict": "ok"}]
        rep = cmd_import(src, proj.parent, cat, list(enumerate(rv[:2], 1)), "review", "model-b", False, glyphs)
        e1 = src["strings"]["en.1"]
        check("import review: suggestion stored, text unchanged, status reviewed",
              e1["text"] == "Yarışı başlat" and e1["review"]["suggestion"] == "Yarışa başla" and e1["status"] == "reviewed", e1)
        rep = cmd_import(src, proj.parent, cat, [(1, rv[2])], "review", "model-b", False, glyphs)
        check("import review: a review of another text is refused", rep["rejected"] and "current text" in rep["rejected"][0]["reason"])
        # human: accept the suggestion for en.1, approve en.2 with an edit
        try:
            cmd_import(src, proj.parent, cat, [(1, {"id": "en.1", "check": sha("a")[:12], "verdict": "ok"})],
                       "review", "m", False, glyphs)
            check("import review: a sheet without the reviewed Turkish column is refused", False)
        except Problem:
            check("import review: a sheet without the reviewed Turkish column is refused", True)
        tc = {k: text_check(src["strings"][k]) for k in ("en.1", "en.2")}
        hu = [{"id": "en.1", "check": sha("a")[:12], "decision": "accept", "turkish": "Yarışı başlat",
               "suggestion": "Yarışa başla", "text_check": tc["en.1"]},
              {"id": "en.2", "check": sha("b")[:12], "decision": "approve", "turkish": "\\jc\\f1:3\\f0: ile zıpla!",
               "text_check": tc["en.2"]}]
        rep = cmd_import(src, proj.parent, cat, list(enumerate(hu, 1)), "human", "", False, glyphs)
        check("import human: accept and approve", src["strings"]["en.1"]["text"] == "Yarışa başla"
              and src["strings"]["en.1"]["status"] == "approved" and src["strings"]["en.2"]["origin"] == "human"
              and "review" not in src["strings"]["en.1"], src["strings"])
        old_sheet = [{"id": "en.2", "check": sha("b")[:12], "decision": "approve", "turkish": "eski", "text_check": tc["en.2"]}]
        rep = cmd_import(src, proj.parent, cat, list(enumerate(old_sheet, 1)), "human", "", False, glyphs)
        check("import human: an old sheet never replaces a newer approved text",
              rep["rejected"] and "changed since" in rep["rejected"][0]["reason"]
              and src["strings"]["en.2"]["text"] == "\\jc\\f1:3\\f0: ile zıpla!", rep)
        # approved text is never replaced by a draft or a review
        again = [dict(rows[0][1], turkish="Başka bir taslak")]
        rep = cmd_import(src, proj.parent, cat, list(enumerate(again, 1)), "draft", "m", True, glyphs)
        check("import draft: an approved text is kept (even with --overwrite-unapproved)",
              src["strings"]["en.1"]["text"] == "Yarışa başla" and "approved" in rep["skipped"][0]["reason"])
        rep = cmd_import(src, proj.parent, cat, [(1, {"id": "en.1", "check": sha("a")[:12], "turkish": "Yarışa başla",
                                                      "verdict": "change", "suggestion": "Yarışı başlatın"})],
                         "review", "model-c", False, glyphs)
        check("import review on approved: text and status kept, suggestion pending",
              src["strings"]["en.1"]["status"] == "approved" and src["strings"]["en.1"]["text"] == "Yarışa başla"
              and src["strings"]["en.1"]["review"]["suggestion"] == "Yarışı başlatın")
        rep = cmd_import(src, proj.parent, cat, [(1, {"id": "en.1", "check": sha("a")[:12], "decision": "reject",
                                                      "text_check": text_check(src["strings"]["en.1"])})],
                         "human", "", False, glyphs)
        check("import human: reject drops the suggestion only", "review" not in src["strings"]["en.1"]
              and src["strings"]["en.1"]["text"] == "Yarışa başla")
        rep = cmd_import(src, proj.parent, cat, [(1, {"id": "en.1", "check": sha("a")[:12], "decision": "maybe",
                                                      "turkish": "x", "text_check": ""})], "human", "", False, glyphs)
        check("import human: an unknown decision is refused", bool(rep["rejected"]))
        # status and refresh
        st = cmd_status(src, cat, td / "s.md", glyphs)
        check("status: counts and missing", st["status"]["approved"] == 2 and st["missing"] == 2
              and (td / "s.md").is_file(), st)
        cat2 = [dict(c, source_sha256=sha("a2")) if c["id"] == "en.1" else c for c in cat]
        check("status: a changed game text is stale", cmd_status(src, cat2, None)["stale"] == ["en.1"])
        rf = cmd_refresh(src, cat2)
        check("refresh: stale entry -> needs_review, text kept", rf["stale_marked"] == ["en.1"]
              and src["strings"]["en.1"]["status"] == "needs_review" and src["strings"]["en.1"]["text"] == "Yarışa başla")
        # validation and glossary (an illustrative term)
        terms = [{"en": "lantern", "tr": ["fener"], "avoid": ["lamba"]}]
        w = glossary_warnings("The lantern is lit.", "Lamba yandı.", terms)
        check("glossary: expected term missing and avoided term found", len(w) == 2, w)
        _, wa = text_problems("x", "START", "BASLAT IÇIN", glyphs)
        check("turkish: capital I in an all-caps word is flagged", any("İ" in x for x in wa), wa)
        check("turkish: Turkish lower case of I and dotted I", tr_lower("IŞIK İz") == "ışık iz")
        # deterministic project file, backup kept, ids preserved across a write
        write_project(proj, src)
        a = proj.read_bytes()
        write_project(proj, load_project(proj))
        check("project: deterministic and round-trips", proj.read_bytes() == a and proj.with_name("tr.json.bak").is_file())
        # private exports
        try:
            write_table(ROOT / "config" / "x.csv", ["id"], [])
            check("export: refused inside the repository outside private/", False)
        except Problem:
            check("export: refused inside the repository outside private/", True)
        # batches
        r = cmd_export(src, proj.parent, cat, td / "b", "draft", "all", "", 3, glyphs)
        check("export: batches of a fixed size", len(r["files"]) == 2 and len(read_table(Path(r["files"][1]))) == 1, r)
        q = td / "q.csv"
        write_table(q, ["id", "turkish"], [{"id": "en.1", "turkish": 'Dedi ki: "Evet, hayır"'}])
        jl = td / "q.jsonl"
        write_table(jl, ["id", "turkish"], [{"id": "en.1", "turkish": "a\u2028b"}])
        check("tables: quotes, commas and a U+2028 survive CSV / JSONL",
              read_table(q)[0][1]["turkish"] == 'Dedi ki: "Evet, hayır"' and read_table(jl)[0][1]["turkish"] == "a\u2028b")
        # CSV with a stray separator column is refused
        (td / "x.csv").write_text("id,check,turkish\nen.1,abc,a,b\n", encoding="utf-8")
        try:
            read_table(td / "x.csv")
            check("import: a row with extra cells is refused", False)
        except Problem:
            check("import: a row with extra cells is refused", True)
        # M36: a translation repository of its own: exports only under its private/ folder.
        trrepo = td / "rayman3hd-turkish"
        (trrepo / ".git").mkdir(parents=True)
        (trrepo / "private").mkdir()
        try:
            write_table(trrepo / "batch.csv", ["id"], [])
            check("export (M36): refused in another Git repository outside its private/ folder", False)
        except Problem:
            write_table(trrepo / "private" / "batch.csv", ["id"], [])
            write_table(td / "outside.csv", ["id"], [])
            check("export (M36): refused in another Git repository outside its private/ folder",
                  (trrepo / "private" / "batch.csv").is_file() and not (trrepo / "batch.csv").exists())
        # M36: the same human sheet imported twice is a no-op; a sheet older than a newer decision is still refused.
        p2 = {"strings": {"en.1": {"source_sha256": sha("a"), "status": "reviewed", "text": "Yarışı başlat",
                                   "review": {"by": "m", "verdict": "change", "suggestion": "Yarışa başla"}},
                          "en.3": {"source_sha256": sha("c"), "status": "reviewed", "text": "Fener yandı.",
                                   "review": {"by": "m", "verdict": "change", "suggestion": "Fener yanıyor."}}}}
        sheet = [(1, {"id": "en.1", "check": sha("a")[:12], "decision": "accept", "suggestion": "Yarışa başla",
                      "text_check": text_check(p2["strings"]["en.1"])}),
                 (2, {"id": "en.3", "check": sha("c")[:12], "decision": "reject", "suggestion": "Fener yanıyor.",
                      "text_check": text_check(p2["strings"]["en.3"])})]
        r1 = cmd_import(p2, proj.parent, cat, sheet, "human", "", False, glyphs)
        snap = json.dumps(p2, sort_keys=True)
        r2 = cmd_import(p2, proj.parent, cat, sheet, "human", "", False, glyphs)
        check("import human (M36): the same sheet twice: applied once, then a no-op without rejections",
              len(r1["changed"]) == 2 and not r1["rejected"] and not r2["changed"] and not r2["rejected"]
              and r2["unchanged"] == 2 and json.dumps(p2, sort_keys=True) == snap, (r1, r2))
        p2["strings"]["en.1"]["text"] = "Yarışı şimdi başlat"   # a newer decision after the sheet
        r3 = cmd_import(p2, proj.parent, cat, sheet[:1], "human", "", False, glyphs)
        check("import human (M36): after a newer decision the old sheet is refused",
              r3["rejected"] and p2["strings"]["en.1"]["text"] == "Yarışı şimdi başlat", r3)
        # M36: findings name the id, the stage, the constraint and an action; nothing in the text changes.
        sub_row = next(c for c in cat if c["kind"] == "subtitle")
        er, wa = text_problems("vs.en.7.0", sub_row["text"], "Ş" * 401, glyphs, sub_row)
        er3, wa3 = text_problems("vs.en.7.0", sub_row["text"], "Bir\\liki\\lüç!", glyphs, sub_row)
        check("validate (M36): a subtitle over 400 bytes is an error with the overage; three lines warn",
              any("at most 400 (shorten by 1)" in x for x in er) and any("3 lines" in x for x in wa3) and not er3, (er, wa3))
        msgs = {"control": text_problems("en.1", "Start the race", "Yarış\nbaşlat", glyphs)[0],
                "codes": text_problems("en.2", cat[1]["text"], "Zıpla", glyphs)[0],
                "range": text_problems("en.1", "Start the race", "Yarış “başlat”", glyphs)[0],
                "glyph": text_problems("en.1", "Start the race", "Şu", frozenset())[0],
                "slot": text_problems("en.1", "Start the race", "Yarışı şimdi başlatın", glyphs, cat[0])[1],
                "same": text_problems("en.1", "Start the race", "Start the race", glyphs)[1]}
        ex = {k: [explain(m)["stage"] for m in v] for k, v in msgs.items()}
        check("validate (M36): every finding has a stage", all(v and "other" not in v for v in ex.values())
              and ex["control"][0] == "format" and ex["codes"][0] == "format" and ex["range"][0] == "encoding"
              and ex["glyph"][0] == "encoding" and ex["slot"][0] == "capacity" and ex["same"][0] == "review", ex)
        rows = findings_of(["en.471: x for a slot of 3: the build moves it", "the subtitles need 9 bytes more than "
                            "VS.sub holds; it can grow by at most 4: shorten"], ["vs.en.42.3: widest line 900 px"])
        check("validate (M36): findings carry the id where the message names one",
              [(r["id"], r["severity"], r["stage"]) for r in rows] == [("en.471", "error", "capacity"),
                                                                     ("", "error", "capacity"),
                                                                     ("vs.en.42.3", "warning", "layout")], rows)
        rep_csv, rep_md = td / "f.csv", td / "f.md"
        write_findings(rep_csv, rows)
        write_findings(rep_md, rows)
        back = read_table(rep_csv)
        check("validate (M36): the findings report opens in a spreadsheet (UTF-8 with BOM) and as Markdown",
              rep_csv.read_bytes()[:3] == b"\xef\xbb\xbf" and [r[1]["id"] for r in back] == ["en.471", "", "vs.en.42.3"]
              and "| en.471 | error | capacity |" in rep_md.read_text(encoding="utf-8"))
        v = cmd_validate({"strings": {"en.1": {"source_sha256": sha("a"), "text": "Yarış\nbaşla", "status": "approved"}}},
                         proj.parent, cat, glyphs, [], report=td / "v.csv")
        check("validate (M36): validate writes the findings and counts them by stage",
              v["by_stage"].get("error:format") == 1 and (td / "v.csv").is_file()
              and v["findings"][0]["id"] == "en.1", v.get("by_stage"))
        selftest_m37(check, sha, td, cat, glyphs, proj)
    n = results.count(False)
    print(f"R3HD_LOCFLOW_SELFTEST {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}")
    return 1 if n else 0


def selftest_m37(check, sha, td, cat, glyphs, proj):
    """M37: spreadsheet safety, placeholders, Turkish case, review rounds, the final / human_note columns."""
    # formula injection: every risky cell is neutralised on export and restored on import, also in TSV
    risky = ["=HYPERLINK(\"http://x\")", "+90 dakika", "-61 derece", "@hepsi", "'-zaten", "''=iki", "'", "normal",
             "Çık\\lİptal", "\tsekme"]
    for ext in (".csv", ".tsv"):
        p = td / f"inj{ext}"
        write_table(p, ["id", "turkish"], [{"id": f"en.{i}", "turkish": t} for i, t in enumerate(risky)])
        raw = p.read_bytes().decode("utf-8-sig")
        cells = [line.split("," if ext == ".csv" else "\t", 1)[1] for line in raw.split("\r\n")[1:] if line]
        check(f"tables (M37): no exported {ext} cell starts with = + - @ (formula injection)",
              not any(c.lstrip('"')[:1] in FORMULA_START for c in cells), cells)
        check(f"tables (M37): risky {ext} cells read back unchanged", [r[1]["turkish"] for r in read_table(p)] == risky,
              [r[1]["turkish"] for r in read_table(p)])
    # hexadecimal checks cannot become numbers; old sheets without the # still read
    p = td / "hex.csv"
    write_table(p, ["id", "check", "text_check"], [{"id": "en.1", "check": "12e456789012", "text_check": "000aaa111bbb"}])
    body = p.read_bytes().decode("utf-8-sig")
    back = read_table(p)[0][1]
    check("tables (M37): checks are written as #hex and read back as hex",
          "#12e456789012" in body and back["check"] == "12e456789012" and back["text_check"] == "000aaa111bbb", body)
    (td / "old.csv").write_text("id,check\nen.1,ca978112ca1b\n", encoding="utf-8")
    check("tables (M37): a sheet without the # prefix still reads", read_table(td / "old.csv")[0][1]["check"] == "ca978112ca1b")
    # Excel in a Turkish locale saves CSV with semicolons
    (td / "semi.csv").write_bytes("﻿id;check;turkish\r\nen.1;#ca978112ca1b;Yarış, başla\r\n".encode("utf-8"))
    check("tables (M37): a semicolon CSV (Excel, Turkish locale) reads",
          read_table(td / "semi.csv")[0][1] == {"id": "en.1", "check": "ca978112ca1b", "turkish": "Yarış, başla"})
    # UTF-8 Turkish round trip in every format
    tr = "İğdır'ı, ŞÜPHE ve ılık çay: İ ı Ğ ğ Ş ş Ö ö Ü ü Ç ç"
    ok = True
    for ext in (".csv", ".tsv", ".jsonl"):
        p = td / f"utf{ext}"
        write_table(p, ["id", "turkish"], [{"id": "en.1", "turkish": tr}])
        ok &= read_table(p)[0][1]["turkish"] == tr
    check("tables (M37): Turkish letters round-trip in CSV, TSV and JSONL", ok)
    # atomic writes: an interrupted write leaves the previous file and no temporary file
    p = td / "atom.jsonl"
    write_table(p, ["id"], [{"id": "en.1"}])
    before = p.read_bytes()

    class Boom(Exception):
        pass
    real = os.replace
    try:
        os.replace = lambda a, b: (_ for _ in ()).throw(Boom())
        try:
            write_table(p, ["id"], [{"id": "en.2"}])
        except Boom:
            pass
    finally:
        os.replace = real
    check("tables (M37): an interrupted write keeps the old file and leaves no temporary file",
          p.read_bytes() == before and not list(td.glob(".tmp_*")))
    # Turkish case and placeholders
    check("turkish (M37): upper case i -> İ, ı -> I", tr_upper("istanbul ılık") == "İSTANBUL ILIK"
          and tr_lower(tr_upper("iı")) == "iı")
    er, _ = text_problems("en.1", "Start", "İ".lower() + "lk", glyphs)
    check("turkish (M37): str.lower() of İ (i + U+0307) is refused as unencodable", bool(er), er)
    er, _ = text_problems("en.414", "\\jcLevel score = %i points", "\\jcBölüm puanı = puan", glyphs)
    er2, _ = text_problems("en.414", "\\jcLevel score = %i points", "\\jcBölüm puanı = %i puan", glyphs)
    er3, _ = text_problems("en.379", "\\jcSaving...\\l\\b¼ wait", "\\jcKaydediliyor...\\l bekle", glyphs)
    check("format (M37): a dropped %i or \\b icon is refused; kept is fine",
          any("placeholders" in x for x in er) and not er2 and any("placeholders" in x for x in er3), (er, er2, er3))
    er, _ = text_problems("en.1", "Start the race", "#AD?", glyphs)
    check("format (M37): a spreadsheet error value is refused", any("spreadsheet" in x for x in er), er)
    # the font's own glyph set travels with the project glyphs: a row with a character the font lacks is refused at
    # import (found in M37's real drafts: the font has no ; < > { })
    font = with_font(glyphs, set(range(0x20, 0x7F)) - {ord(";")})
    p4 = {"strings": {}}
    row = [(1, {"id": "en.1", "check": sha("a")[:12], "turkish": "Yarış; başla"})]
    r4 = cmd_import(p4, proj.parent, cat, row, "draft", "m", False, font)
    r5 = cmd_import(p4, proj.parent, cat, row, "draft", "m", False, glyphs)
    check("font (M37): with the font's glyph set a ';' is refused at import; without it (no game data) it passes",
          r4["rejected"] and "no glyph" in r4["rejected"][0]["reason"] and r5["changed"] == ["en.1"]
          and isinstance(font, frozenset) and "ş" in font, (r4, r5))
    # review rounds: an older round never replaces a newer pending review; the same sheet twice is a no-op
    p3 = {"strings": {"en.1": {"source_sha256": sha("a"), "status": "draft", "text": "Yarışı başlat"}}}
    r2 = [(1, {"id": "en.1", "check": sha("a")[:12], "turkish": "Yarışı başlat", "round": "2", "verdict": "change",
               "suggestion": "Yarışa başla"})]
    r1 = [(1, {"id": "en.1", "check": sha("a")[:12], "turkish": "Yarışı başlat", "round": "1", "verdict": "ok"})]
    a = cmd_import(p3, proj.parent, cat, r2, "review", "gemini", False, glyphs)
    b = cmd_import(p3, proj.parent, cat, r2, "review", "gemini", False, glyphs)
    c = cmd_import(p3, proj.parent, cat, r1, "review", "gemini", False, glyphs)
    check("review (M37): round stored; the same round twice is a no-op; an older round is refused",
          a["changed"] == ["en.1"] and p3["strings"]["en.1"]["review"]["round"] == "2" and not b["changed"]
          and not b["rejected"] and c["rejected"] and "round 2" in c["rejected"][0]["reason"]
          and p3["strings"]["en.1"]["review"]["suggestion"] == "Yarışa başla", (a, b, c))
    # human sheet: final column, human_note, accept with a final text is refused; approval only by a decision
    tc = text_check(p3["strings"]["en.1"])
    bad = [(1, {"id": "en.1", "check": sha("a")[:12], "decision": "accept", "final": "Başka", "text_check": tc})]
    rb = cmd_import(p3, proj.parent, cat, bad, "human", "", False, glyphs)
    check("human (M37): accept together with a final text is refused", rb["rejected"]
          and p3["strings"]["en.1"]["status"] == "reviewed")
    none = [(1, {"id": "en.1", "check": sha("a")[:12], "decision": "", "final": "Yarış başlasın", "text_check": tc})]
    rn = cmd_import(p3, proj.parent, cat, none, "human", "", False, glyphs)
    check("human (M37): a final text without a decision changes nothing", not rn["changed"]
          and p3["strings"]["en.1"]["status"] == "reviewed")
    fin = [(1, {"id": "en.1", "check": sha("a")[:12], "decision": "approve", "turkish": "Yarışı başlat",
                "final": "Yarış başlasın", "human_note": "kısa tut", "text_check": tc})]
    rf = cmd_import(p3, proj.parent, cat, fin, "human", "", False, glyphs)
    rf2 = cmd_import(p3, proj.parent, cat, fin, "human", "", False, glyphs)
    e = p3["strings"]["en.1"]
    check("human (M37): approve takes 'final', keeps the note, drops the review; the same sheet again is a no-op",
          e["text"] == "Yarış başlasın" and e["status"] == "approved" and e["note"] == "kısa tut"
          and e["origin"] == "human" and "review" not in e and not rf2["changed"] and not rf2["rejected"], (rf, rf2, e))
    # M37 review findings: a stale sheet whose text did not change but whose status did is refused, both ways
    p6 = {"strings": {"en.1": {"source_sha256": sha("a"), "status": "draft", "text": "Yarışı başlat"}}}
    s1 = [(1, {"id": "en.1", "check": sha("a")[:12], "decision": "approve", "turkish": "Yarışı başlat",
               "text_check": text_check(p6["strings"]["en.1"])})]
    cmd_import(p6, proj.parent, cat, s1, "human", "", False, glyphs)
    s2 = [(1, {"id": "en.1", "check": sha("a")[:12], "decision": "redo",
               "text_check": text_check(p6["strings"]["en.1"])})]
    cmd_import(p6, proj.parent, cat, s2, "human", "", False, glyphs)
    a1 = cmd_import(p6, proj.parent, cat, s1, "human", "", False, glyphs)   # the old approve sheet again
    st_a = p6["strings"]["en.1"]["status"]
    s1b = [(1, dict(s1[0][1], text_check=text_check(p6["strings"]["en.1"])))]
    cmd_import(p6, proj.parent, cat, s1b, "human", "", False, glyphs)     # a fresh approve
    b1 = cmd_import(p6, proj.parent, cat, s2, "human", "", False, glyphs)   # the old redo sheet again
    check("human (M37 review): an old sheet cannot re-approve after a redo, nor demote after a newer approval",
          a1["rejected"] and st_a == "needs_review" and b1["rejected"]
          and p6["strings"]["en.1"]["status"] == "approved", (a1, b1, p6))
    # a decided review cannot come back from its own sheet, nor from an earlier round; a later round can
    p7 = {"strings": {"en.1": {"source_sha256": sha("a"), "status": "draft", "text": "Yarışı başlat"}}}
    rvs = [(1, {"id": "en.1", "check": sha("a")[:12], "turkish": "Yarışı başlat", "round": "2", "verdict": "change",
                "suggestion": "Yarışa başla"})]
    cmd_import(p7, proj.parent, cat, rvs, "review", "gemini", False, glyphs)
    rj = [(1, {"id": "en.1", "check": sha("a")[:12], "decision": "reject",
               "text_check": text_check(p7["strings"]["en.1"])})]
    cmd_import(p7, proj.parent, cat, rj, "human", "", False, glyphs)
    again = cmd_import(p7, proj.parent, cat, rvs, "review", "gemini", False, glyphs)
    older = cmd_import(p7, proj.parent, cat, [(1, dict(rvs[0][1], round="1", suggestion="Başla"))], "review",
                       "gemini", False, glyphs)
    newer = cmd_import(p7, proj.parent, cat, [(1, dict(rvs[0][1], round="3", suggestion="Başla"))], "review",
                       "gemini", False, glyphs)
    check("review (M37 review): a decided review's sheet is a no-op, an earlier round is refused, a later one is taken",
          not again["changed"] and not again["rejected"] and older["rejected"] and newer["changed"] == ["en.1"]
          and p7["strings"]["en.1"]["review"]["suggestion"] == "Başla", (again, older, newer))
    p8 = {"strings": {"en.1": {"source_sha256": sha("a"), "status": "needs_review", "text": "Yarışı başlat",
                               "note": "eski [source changed: check against the new English]"}}}
    cmd_import(p8, proj.parent, cat, [(1, {"id": "en.1", "check": sha("a")[:12], "decision": "redo",
                                           "human_note": "bak", "text_check": text_check(p8["strings"]["en.1"])})],
               "human", "", False, glyphs)
    check("human (M37 review): a human note keeps the refresh marker", p8["strings"]["en.1"]["note"].startswith("bak")
          and "[source changed" in p8["strings"]["en.1"]["note"], p8)
    # export: the human sheet carries origin and final; the review sheet carries the round; annotate filters rows
    src = {"strings": {"en.2": {"source_sha256": sha("b"), "status": "draft", "text": "\\jc\\f1:3\\f0: ile zıpla",
                                "origin": "draft:claude-r1"}}}
    out = td / "h.csv"
    cmd_export(src, proj.parent, cat, out, "human", "draft", "", 0, glyphs)
    h = read_table(out)[0][1]
    check("export (M37): the human sheet has origin, final and human_note", h["origin"] == "draft:claude-r1"
          and "final" in h and "human_note" in h, h)
    out = td / "r.jsonl"
    cmd_export(src, proj.parent, cat, out, "review", "draft", "", 0, glyphs, review_round=3)
    check("export (M37): review rows carry their round", read_table(out)[0][1]["round"] == "3")
    seen = []
    res = cmd_export({"strings": {}}, proj.parent, cat, td / "a.jsonl", "draft", "missing", "", 0, glyphs,
                     ids={"en.1", "en.3"}, annotate=lambda r, c: seen.append(r["id"]) or r["id"] != "en.3")
    check("export (M37): an id set and an annotate filter", res["rows"] == 1 and seen == ["en.1", "en.3"], res)
    dv = loc.dev_variant({"id": "tr.full", "name": "x" * 80, "version": "1.2.3", "description": "d"})
    check("build (M37): a development build is marked NOT FINAL in name, id, version and description",
          dv["id"] == "tr.full.dev" and len(dv["name"]) <= 80 and dv["version"] == "1.2.3-dev"
          and dv["description"].startswith("NOT FINAL"))
    # M39: a later draft over a draft keeps the revision counter, earlier alternatives and the replaced text
    c1 = cat[0]
    s39 = {"strings": {"en.1": {"source_sha256": c1["source_sha256"], "status": "draft", "text": "Yarışı başlat",
                                "origin": "draft:m1", "rev": "4", "alt": [{"text": "Yarışa başla", "by": "m1"}]}}}
    row = {"id": "en.1", "check": check_of(c1["source_sha256"]), "turkish": "Yarışa gir"}
    r39 = cmd_import(s39, proj.parent, cat, [(1, row)], "draft", "m2", False, glyphs)
    e39 = s39["strings"]["en.1"]
    check("import (M39): a later draft keeps rev and alternatives and keeps the replaced draft as an alternative",
          r39["changed"] == ["en.1"] and e39["text"] == "Yarışa gir" and e39["rev"] == "4"
          and [x["text"] for x in e39["alt"]] == ["Yarışa başla", "Yarışı başlat"]
          and e39["alt"][1]["kind"] == "previous_draft" and e39["alt"][1]["by"] == "draft:m1", e39)
    cmd_import(s39, proj.parent, cat, [(1, dict(row, turkish="Yarışı başlat"))], "draft", "m3", False, glyphs)
    check("import (M39): returning to an earlier text adds no duplicate alternative",
          [x["text"] for x in s39["strings"]["en.1"]["alt"]] == ["Yarışa başla", "Yarışı başlat", "Yarışa gir"],
          s39["strings"]["en.1"]["alt"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["init", "export", "import", "status", "validate", "refresh", "build", "selftest"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--for", dest="mode", choices=MODES)
    ap.add_argument("--from", dest="source_mode", choices=MODES)
    ap.add_argument("--only", default="")
    ap.add_argument("--category", default="")
    ap.add_argument("--ids", default="", help="export: ids or prefixes ending in '.', comma separated")
    ap.add_argument("--batch-size", type=int, default=0)
    ap.add_argument("--ext", default=".jsonl", choices=[".jsonl", ".csv", ".tsv"])
    ap.add_argument("--label", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite-unapproved", action="store_true")
    ap.add_argument("--report")
    ap.add_argument("--glossary")
    ap.add_argument("--id")
    ap.add_argument("--name")
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--allow-unapproved", action="store_true")
    ap.add_argument("--game-dir")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    code = 0
    try:
        if a.cmd == "init":
            if len(a.args) != 1 or not a.id or not a.name:
                raise Problem("init PROJECT --id ID --name NAME")
            r = cmd_init(Path(a.args[0]), a.id, a.name)
        else:
            if not a.args:
                raise Problem(f"{a.cmd} PROJECT ...")
            proj = Path(a.args[0])
            src = load_project(proj)
            paths = loc.game_paths(argparse.Namespace(cache=None, game_dir=a.game_dir))
            cat_rows = loc.catalog_rows(paths, src["language"]["source"])
            glyphs = with_font(project_glyphs(src, proj.parent), rm.font_defined(paths))   # M37
            if a.cmd == "export":
                if len(a.args) != 2 or not a.mode:
                    raise Problem("export PROJECT OUT --for draft|review|human")
                EXT[0] = a.ext
                if a.batch_size < 0:
                    raise Problem("--batch-size must be positive")
                r = cmd_export(src, proj.parent, cat_rows, Path(a.args[1]), a.mode, a.only, a.category, a.batch_size,
                               glyphs, a.ids)
            elif a.cmd == "import":
                if len(a.args) != 2 or not a.source_mode:
                    raise Problem("import PROJECT FILE --from draft|review|human")
                label = a.label or Path(a.args[1]).stem
                if not re.match(r"^[A-Za-z0-9._ -]{1,60}$", label):
                    raise Problem("--label: letters, digits, . _ - and spaces")
                r = cmd_import(src, proj.parent, cat_rows, read_table(Path(a.args[1])), a.source_mode, label,
                               a.overwrite_unapproved, glyphs)
                if r["changed"] and not a.dry_run:
                    write_project(proj, src)
                r["written"] = bool(r["changed"]) and not a.dry_run
                code = 1 if r["rejected"] else 0
            elif a.cmd == "status":
                r = cmd_status(src, cat_rows, a.report, glyphs)
            elif a.cmd == "validate":
                r = cmd_validate(src, proj.parent, cat_rows, glyphs, load_glossary(a.glossary), paths, proj, a.report)
                code = 1 if r["errors"] else 0
            elif a.cmd == "refresh":
                r = cmd_refresh(src, cat_rows)
                if r["stale_marked"]:
                    write_project(proj, src)
            elif a.cmd == "build":
                if len(a.args) != 2:
                    raise Problem("build PROJECT OUT [--zip] [--allow-unapproved]")
                r = loc.cmd_build(paths, proj, Path(a.args[1]), a.zip, a.allow_unapproved)
        r = {"result": "ok" if not code else "problems", **r}
    except (Problem, loc.Problem, rm.Refusal) as x:
        r, code = {"result": "refused", "detail": getattr(x, "detail", str(x))}, 2
    except (OSError, ValueError, KeyError, TypeError) as x:
        r, code = {"result": "refused", "detail": f"{type(x).__name__}: {x}"}, 2
    sys.stdout.buffer.write((json.dumps(r, indent=1, ensure_ascii=a.json, default=str) + "\n").encode("utf-8"))
    return code


if __name__ == "__main__":
    sys.exit(main())
