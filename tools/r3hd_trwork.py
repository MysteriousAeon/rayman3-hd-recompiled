#!/usr/bin/env python3
"""M37: a translation workspace for Rayman 3 HD Recompiled: the production layer above tools/r3hd_locflow.py.

A workspace is one folder, laid out so that it can later become a repository of its own (for example
rayman3hd-turkish) without carrying the game's text:

  WS/README.md, STYLE.md            how to work; the style guide (no game text)
  WS/workspace.json                 metadata, build settings, round counters, catalog fingerprint (no game text)
  WS/tr.json, glyphs.json           the translation source (hashes, Turkish, statuses, reviews; no English)
  WS/glossary.json                  terminology (proposed / approved terms)
  WS/ledger.jsonl                   every import: file hash, label, counts (ids only)
  WS/.gitignore                     ignores private/ and build/
  WS/private/                       EVERYTHING WITH THE GAME'S ENGLISH: inventory, batches, returns, review sheets,
                                    decision sheets, queues
  WS/build/                         mod packages (preview builds are marked NOT FINAL)

The English stays in WS/private/: r3hd_locflow.py refuses exports elsewhere in a Git work tree. No network, no API:
batches are files you give to a model yourself. Machine drafts and reviews are never approvals; only a person's
decision sheet approves a string.

usage:
  r3hd_trwork.py new WS [--id tr.full] [--name NAME]          a new workspace (from config/localization/project_template)
  r3hd_trwork.py inventory WS                                  catalog, categories, readiness -> WS/private/inventory
  r3hd_trwork.py batch WS [--category C,..] [--readiness R,..] [--ids I,..] [--only SEL] [--size N] [--ext E]
                                                               a draft round: WS/private/batches/rNNN/batch_NNN.*
  r3hd_trwork.py ingest WS FILE --batch rNNN/batch_NNN --model NAME [--dry-run]   a model's answer for one batch
  r3hd_trwork.py retry WS --batch rNNN/batch_NNN               the rows of a batch still without a draft
  r3hd_trwork.py review WS [--only SEL] [--category C,..] [--ids I,..|--ids-file F] [--size N] [--ext E]
                                                               a review round for a second model
  r3hd_trwork.py review-in WS FILE --reviewer NAME [--dry-run] a reviewer's answer (suggestions only)
  r3hd_trwork.py suggest WS FILE --by NAME [--kind K] [--dry-run]
                                                               alternatives beside existing texts (M39; never applied)
  r3hd_trwork.py sheet WS [--only SEL] [--category C,..] [--ext .csv|.tsv]       a bilingual decision sheet
  r3hd_trwork.py decide WS FILE [--dry-run]                    your decisions (the only way to approve)
  r3hd_trwork.py dashboard WS [--report FILE.md]               coverage and approval by category
  r3hd_trwork.py queue WS [--out FILE.csv] [--with-english]    what to look at first, by issue
  r3hd_trwork.py build WS --preview [--ids I,..|--ids-file F] [--zip]   NOT FINAL build of every status
  r3hd_trwork.py build WS --release [--zip]                    approved strings only
  r3hd_trwork.py selftest
Common: --game-dir DIR, --json. Exit 0 ok, 1 problems found, 2 refused.
"""
import argparse
import datetime
import hashlib
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
import r3hd_locflow as lf  # noqa: E402
import r3hd_mods as rm  # noqa: E402

ROOT = rm.ROOT
TEMPLATE = ROOT / "config" / "localization" / "project_template"
GROUPS = ROOT / "config" / "localization" / "context_groups.json"
PROMPTS = ROOT / "config" / "localization" / "prompts"
WS_KIND = "r3hd-translation-workspace"
CATEGORIES = ("menu", "system", "tutorial", "bonus_help", "album", "credits", "dialogue", "subtitle", "internal",
              "legacy", "placeholder", "unknown")
READINESS = ("ready", "partial_context", "needs_context", "verify_display")
STATES = ("untranslated", "draft", "needs_review", "reviewed", "approved")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
BATCH_RE = re.compile(r"^r(\d{3})/batch_(\d{3})$")
# Columns added to exported rows (the importers ignore them): where the string belongs and what to watch.
CONTEXT_COLS = ["group", "readiness", "display", "flags"]
# M39: alternatives shown beside the text (reviewer and decision sheets; the importers ignore these columns)
ALT_COLS = ["alternative", "alt_reason"]
ALT_KINDS = ("restored_longer", "proposal", "previous_draft")


class Problem(Exception):
    pass


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------------------------------------------
# Context: categories and readiness from the context map and the catalog's own data. Nothing is guessed: a string
# whose range is not in the map is 'unknown' and needs context.

def load_groups(path: Path = GROUPS) -> list:
    g = json.loads(path.read_text(encoding="utf-8"))
    if g.get("kind") != "r3hd-context-groups" or not isinstance(g.get("groups"), list):
        raise Problem(f"{path}: not an r3hd-context-groups file")
    for x in g["groups"]:
        if x.get("category") not in CATEGORIES or not (0 <= x.get("from", -1) <= x.get("to", -1)):
            raise Problem(f"{path}: bad group {x}")
    return g["groups"]


def group_of(handle: int, groups: list):
    hit = None
    for x in groups:   # a later rule overrides an earlier one
        if x["from"] <= handle <= x["to"]:
            hit = x
    return hit


def visible(text: str) -> str:
    return loc.CODE_RE.sub(lambda m: "\n" if m.group() == "\\l" else "", text)


def classify(c: dict, groups: list, dup_ids: dict) -> dict:
    """{group, readiness, display, flags} of one catalog entry."""
    text = c["text"]
    vis = visible(text)
    flags = []
    if c.get("category") == "voiced line":
        flags.append("voiced")
    if lf.codes(text):
        flags.append("codes")
    if "\\f1:" in text:
        flags.append("buttons")
    if lf.placeholders(text):
        flags.append("placeholders")
    if lf.breaks(text):
        flags.append(f"lines_{lf.breaks(text) + 1}")
    if "\\jc" in text:
        flags.append("centred")
    if re.match(r"^ {2,}", vis) or "\n  " in vis:
        flags.append("leading_spaces")
    if len(re.sub(r"[^A-Za-zÀ-ÿ0-9]", "", vis)) <= 4:
        flags.append("short")
    if c["id"] in dup_ids:
        flags.append("same_english_as:" + "|".join(x for x in dup_ids[c["id"]] if x != c["id"]))
    if c.get("shared_with"):
        flags.append("shared_with_other_languages")
    if re.match(r"^\(([A-Z]+)\)", vis.strip()):
        flags.append("speaker_tag")
    if lf.breaks(text) or "leading_spaces" in flags:
        flags.append("layout_check")
    if c["kind"] == "subtitle":
        group, display = "subtitle", (f"movie {c.get('movie')}" + (f" = {c['movie_file']} (verified)"
                                      if c.get("movie_file") else " (file not verified)"))
    else:
        g = group_of(c.get("handle", -1), groups)
        group, display = (g["category"], g.get("display", "")) if g else ("unknown", "")
    if c.get("levels") or c.get("speakers"):
        display = (display + "; " if display else "") + "levels " + " ".join(c.get("levels", [])) + \
                  ("; speaker code " + " ".join(c.get("speakers", [])) if c.get("speakers") else "")
    if group in ("internal", "legacy", "placeholder", "credits"):
        readiness = "verify_display"
    elif "speaker_tag" in flags or group == "unknown":
        readiness = "needs_context"
    elif group == "dialogue":
        readiness = "partial_context" if "voiced" in flags else "needs_context"
    elif group == "subtitle":
        readiness = "partial_context"
    else:
        readiness = "ready"
    return {"group": group, "readiness": readiness, "display": display, "flags": " ".join(flags)}


def duplicates(cat: dict) -> dict:
    """{id: [ids with the same English]} for English shared by several ids (each id is still its own entry)."""
    by = {}
    for sid, c in cat.items():
        if c["text"].strip():
            by.setdefault(c["text"], []).append(sid)
    return {sid: ids for ids in by.values() if len(ids) > 1 for sid in ids}


def fingerprint(cat: dict) -> str:
    return rm.sha256_bytes("".join(f"{s}:{cat[s]['source_sha256']}\n" for s in sorted(cat, key=loc.sid_key)).encode())


# ---------------------------------------------------------------------------------------------------------------
# Workspace I/O

class WS:
    def __init__(self, path: Path, game_dir=None, need_game=True):
        self.path = Path(path)
        meta = self.path / "workspace.json"
        if not meta.is_file():
            raise Problem(f"{self.path}: not a translation workspace (no workspace.json; create one with new)")
        self.meta = json.loads(meta.read_text(encoding="utf-8"))
        if self.meta.get("kind") != WS_KIND:
            raise Problem(f"{meta}: not a {WS_KIND} file")
        self.proj = self.path / self.meta["project"]
        self.src = lf.load_project(self.proj)
        self.glyphs = lf.project_glyphs(self.src, self.proj.parent)
        g = self.path / self.meta.get("glossary", "glossary.json")
        self.terms = lf.load_glossary(g) if g.is_file() else []
        self.priv = self.path / "private"
        self.paths = None
        self.cat = {}
        if need_game:
            self.paths = loc.game_paths(argparse.Namespace(cache=None, game_dir=game_dir))
            self.rows = loc.catalog_rows(self.paths, self.src["language"]["source"])
            self.cat = lf.catalog_index(self.rows)
            self.glyphs = lf.with_font(self.glyphs, rm.font_defined(self.paths))   # rows checked against the font

    def context(self) -> dict:
        groups, dups = load_groups(), duplicates(self.cat)
        return {sid: classify(c, groups, dups) for sid, c in self.cat.items()}

    def save_meta(self):
        lf.atomic_write(self.path / "workspace.json",
                        (json.dumps(self.meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))

    def save_project(self):
        lf.write_project(self.proj, self.src)

    def ledger(self, entry: dict):
        """Append-only record of what changed the project (ids and counts only, never the English)."""
        with open(self.path / "ledger.jsonl", "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"time": now(), **entry}, ensure_ascii=False) + "\n")

    def next_round(self, kind: str, taken=None) -> int:
        """The next free number (M37 review: one whose folder or file an interrupted earlier command left behind is
        skipped, so a crash never blocks the command)."""
        n = int(self.meta.setdefault("rounds", {}).get(kind, 0)) + 1
        while taken is not None and taken(n):
            n += 1
        self.meta["rounds"][kind] = n
        return n


def file_sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def annotator(ctx: dict, categories=None, readiness=None, strings=None):
    """`strings` (the project's entries): also fill the M39 alternative columns."""
    def annotate(r, c):
        x = ctx.get(c["id"])
        if x is None:
            return False
        if categories and x["group"] not in categories:
            return False
        if readiness and x["readiness"] not in readiness:
            return False
        r.update(x)
        if strings is not None:
            r.update(alt_columns(strings.get(c["id"])))
        return True
    return annotate


def alt_columns(e) -> dict:
    """The latest alternative of an entry and why it was proposed (empty when there is none)."""
    alts = [a for a in (e or {}).get("alt") or [] if a["text"] != e["text"]]
    if not alts:
        return {"alternative": "", "alt_reason": ""}
    a = alts[-1]
    more = f" (+{len(alts) - 1} earlier)" if len(alts) > 1 else ""
    return {"alternative": a["text"], "alt_reason": f"{a.get('kind', '')}: {a.get('reason', '')} [{a.get('by', '')}]"
            + more}


def split(s) -> set:
    return {x.strip() for x in (s or "").split(",") if x.strip()}


def checked(values: set, allowed, what) -> set:
    bad = values - set(allowed)
    if bad:
        raise Problem(f"{what} {', '.join(sorted(bad))}: one of {', '.join(allowed)}")
    return values


# ---------------------------------------------------------------------------------------------------------------
# Commands

def cmd_new(path: Path, mid: str, name: str) -> dict:
    path = Path(path)
    if path.exists() and any(path.iterdir()):
        raise Problem(f"{path} exists and is not empty")
    path.mkdir(parents=True, exist_ok=True)
    lf.cmd_init(path / "tr.json", mid, name)
    src = lf.load_project(path / "tr.json")
    src["target"]["min_port_version"] = rm.SUB_GROW_PORT   # Turkish subtitles are expected to grow VS.sub (M36)
    lf.write_project(path / "tr.json", src)
    (path / "tr.json.bak").unlink(missing_ok=True)
    for f in ("README.md", "STYLE.md", "glossary.json"):
        shutil.copyfile(TEMPLATE / f, path / f)
    shutil.copyfile(TEMPLATE / "gitignore.txt", path / ".gitignore")
    for d in ("inventory", "batches", "returns", "review", "sheets", "queue"):
        (path / "private" / d).mkdir(parents=True, exist_ok=True)
    (path / "build").mkdir(exist_ok=True)
    meta = {"kind": WS_KIND, "format": 1, "name": name, "project": "tr.json", "glossary": "glossary.json",
            "language": {"source": "en", "target": "tr"},
            "build": {"release": "approved strings only", "preview": "every status; id <id>.dev, marked NOT FINAL"},
            "rounds": {"draft": 0, "review": 0, "sheet": 0}, "catalog_fingerprint": "", "created": now()}
    lf.atomic_write(path / "workspace.json", (json.dumps(meta, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return {"workspace": str(path), "project": str(path / "tr.json"),
            "note": "English-bearing files go under private/ only; keep this folder out of any public place until "
                    "private/ is ignored there"}


def cmd_inventory(ws: WS) -> dict:
    ctx = ws.context()
    out = ws.priv / "inventory"
    out.mkdir(parents=True, exist_ok=True)
    no_string = [r["id"] for r in ws.rows if "source_sha256" not in r]
    blank = [s for s, c in ws.cat.items() if not c["text"].strip()]
    rows = []
    for sid in sorted(ws.cat, key=loc.sid_key):
        c = ws.cat[sid]
        if not c["text"].strip():
            continue
        x = ctx[sid]
        rows.append({"id": sid, "check": lf.check_of(c["source_sha256"]), "kind": c["kind"], **x,
                     "levels": " ".join(c.get("levels", [])), "speakers": " ".join(c.get("speakers", [])),
                     "max_bytes": c.get("capacity", rm.SUB_MAX_TEXT if c["kind"] == "subtitle" else ""),
                     "lines": lf.breaks(c["text"]) + 1, "codes": " ".join(lf.codes(c["text"])),
                     "placeholders": " ".join(lf.placeholders(c["text"])), "english": c["text"]})
    cols = ["id", "check", "kind", "group", "readiness", "display", "flags", "levels", "speakers", "max_bytes", "lines",
            "codes", "placeholders", "english"]
    lf.write_table(out / "inventory.csv", cols, rows)
    lf.atomic_write(out / "catalog.json", (json.dumps({"note": "game-derived: keep it private", "rows": ws.rows},
                                                      indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    by = {}
    for r in rows:
        by.setdefault(r["group"], {k: 0 for k in READINESS})[r["readiness"]] += 1
    flagc = {}
    for r in rows:
        for f in r["flags"].split():
            k = "multi_line" if f.startswith("lines_") else f.split(":")[0]
            flagc[k] = flagc.get(k, 0) + 1
    dups = duplicates(ws.cat)
    groups = sorted({tuple(sorted(v, key=loc.sid_key)) for v in dups.values()})
    res = {"handles": sum(1 for r in ws.rows if r["kind"] == "text"), "no_string": len(no_string),
           "blank": len(blank), "translatable": len(rows),
           "by_kind": {k: sum(1 for r in rows if r["kind"] == k) for k in ("text", "subtitle")},
           "voiced": flagc.get("voiced", 0), "by_group": by,
           "readiness": {k: sum(1 for r in rows if r["readiness"] == k) for k in READINESS}, "flags": flagc,
           "duplicate_english_groups": len(groups), "ids_in_duplicate_groups": sum(len(g) for g in groups),
           "catalog_fingerprint": fingerprint(ws.cat), "files": [str(out / "inventory.csv"), str(out / "catalog.json")]}
    lines = ["# Translation inventory (private)", "", f"Generated {now()} from the person's game data. Ids and counts "
             "only; the English is in inventory.csv beside this file.", "",
             f"- Text table handles: {res['handles']} ({res['no_string']} without a string, {res['blank']} blank)",
             f"- Translatable: {res['translatable']} ({res['by_kind']['text']} table strings, "
             f"{res['by_kind']['subtitle']} movie subtitles); voiced lines: {res['voiced']}",
             f"- Same English under several ids: {res['duplicate_english_groups']} groups, "
             f"{res['ids_in_duplicate_groups']} ids (each id keeps its own translation)",
             f"- Catalog fingerprint: `{res['catalog_fingerprint'][:16]}`", "",
             "## Categories and readiness", "",
             "| category | " + " | ".join(READINESS) + " | total |", "|---" * (len(READINESS) + 2) + "|"]
    for g in CATEGORIES:
        if g in by:
            lines.append(f"| {g} | " + " | ".join(str(by[g][k]) for k in READINESS) + f" | {sum(by[g].values())} |")
    lines += ["", "- **ready**: the category says where it is shown; translate.",
              "- **partial_context**: level and speaker code (voiced lines) or the movie (subtitles), no scene.",
              "- **needs_context**: dialogue without a voice file, a bracketed speaker tag, or an unknown range: "
              "find where it is said before a final translation.",
              "- **verify_display**: credits, development labels, another platform's messages, glyph-only strings: "
              "check whether (and how) the game shows them before spending effort.", "",
              "## Flags", "", "| flag | count |", "|---|---|"] + \
             [f"| {k} | {v} |" for k, v in sorted(flagc.items())] + \
             ["", "## Same English, several ids", ""] + [", ".join(g) for g in groups] + \
             ["", "## Handles without a string", "", ", ".join(no_string), "",
              "## Shared with the other languages' tables",
              "", "These are one copy in fix.lvl for every language: a Turkish text changes them for French, German, "
              "Italian and Spanish too (a text that fits is written in place; a longer one is moved and every pointer "
              "to it, of every language, is redirected).", "",
              ", ".join(sorted((s for s, c in ws.cat.items() if c.get("shared_with")), key=loc.sid_key)), ""]
    lf.atomic_write(out / "coverage.md", ("\n".join(lines) + "\n").encode("utf-8"))
    res["files"].append(str(out / "coverage.md"))
    ws.meta["catalog_fingerprint"] = res["catalog_fingerprint"]
    ws.meta["inventory"] = {k: res[k] for k in ("handles", "no_string", "blank", "translatable", "by_kind", "voiced")}
    ws.save_meta()
    return res


def batch_dir(ws: WS, spec: str):
    m = BATCH_RE.match(spec or "")
    if not m:
        raise Problem("--batch is rNNN/batch_NNN (the round folder and the batch name, e.g. r001/batch_003)")
    d = ws.priv / "batches" / f"r{m.group(1)}"
    man = d / "manifest.json"
    if not man.is_file():
        raise Problem(f"{man} is missing")
    manifest = json.loads(man.read_text(encoding="utf-8"))
    name = f"batch_{m.group(2)}"
    if name not in manifest["batches"]:
        raise Problem(f"{spec}: no such batch in {man}")
    return d, manifest, name


def cmd_batch(ws: WS, categories, readiness, ids, only, size, ext) -> dict:
    ctx = ws.context()
    if size < 1 or size > 400:
        raise Problem("--size: 1 to 400 rows per batch")
    rnd = ws.next_round("draft", lambda n: (ws.priv / "batches" / f"r{n:03d}").exists())
    d = ws.priv / "batches" / f"r{rnd:03d}"
    cols = lf.COLUMNS["draft"][:-2] + CONTEXT_COLS + ["turkish", "note"]
    lf.EXT[0] = ext
    r = lf.cmd_export(ws.src, ws.proj.parent, ws.rows, d, "draft", only or "missing", "", size, ws.glyphs,
                      ids or "", annotate=annotator(ctx, categories, readiness), columns=cols)   # ids: prefixes allowed
    if not r["rows"]:
        shutil.rmtree(d, ignore_errors=True)
        ws.meta["rounds"]["draft"] = rnd - 1
        raise Problem("no string matches (nothing missing in that selection?)")
    batches = {}
    for f in r["files"]:
        p = Path(f)
        rows = lf.read_table(p)
        batches[p.stem] = {"file": p.name, "sha256": file_sha(p), "ids": [x["id"] for _, x in rows],
                           "checks": {x["id"]: x["check"] for _, x in rows}}
    manifest = {"kind": "r3hd-draft-round", "round": rnd, "created": now(), "selection":
                {"categories": sorted(categories or []), "readiness": sorted(readiness or []), "only": only or "missing",
                 "ids": ids or ""}, "catalog_fingerprint": fingerprint(ws.cat), "batches": batches}
    lf.atomic_write(d / "manifest.json", (json.dumps(manifest, indent=1) + "\n").encode("utf-8"))
    shutil.copyfile(PROMPTS / "draft.md", d / "PROMPT.md")
    (ws.priv / "returns" / f"r{rnd:03d}").mkdir(parents=True, exist_ok=True)
    ws.save_meta()
    return {"round": rnd, "rows": r["rows"], "batches": len(batches), "folder": str(d),
            "return_to": str(ws.priv / "returns" / f"r{rnd:03d}"),
            "next": f"give each batch with PROMPT.md to a model; then ingest WS FILE --batch r{rnd:03d}/batch_001 "
                    "--model NAME"}


def cmd_ingest(ws: WS, file: Path, spec: str, model: str, dry_run: bool) -> dict:
    if not NAME_RE.match(model or ""):
        raise Problem("--model: a short name such as claude-opus-5.5 or gemini (letters, digits, . _ -)")
    d, manifest, name = batch_dir(ws, spec)
    want = manifest["batches"][name]["ids"]
    table = lf.read_table(file)
    got = {str(r.get("id", "")).strip() for _, r in table}
    unexpected = [(n, str(r.get("id", "")).strip()) for n, r in table if str(r.get("id", "")).strip() not in want]
    keep = [(n, r) for n, r in table if str(r.get("id", "")).strip() in want]
    label = f"{model}.r{manifest['round']:03d}.{name}"
    rep = lf.cmd_import(ws.src, ws.proj.parent, ws.rows, keep, "draft", label, False, ws.glyphs)
    rep["rejected"] += [{"row": n, "id": sid, "reason": "not a row of this batch (added or renamed by the model?)"}
                        for n, sid in unexpected]
    empty = {s["id"] for s in rep["skipped"] if s["reason"].startswith("no Turkish")}
    rep["missing"] = [s for s in want if s not in got or s in empty]
    rep["retry"] = [s for s in want if s not in ws.src["strings"]]   # still without any text: retry exports these
    rep["batch"], rep["label"] = spec, label
    rep["written"] = bool(rep["changed"]) and not dry_run
    if rep["written"]:
        ws.save_project()
        ws.ledger({"action": "draft", "batch": spec, "file": file.name, "sha256": file_sha(file), "label": label,
                   "changed": len(rep["changed"]), "rejected": len(rep["rejected"]), "missing": len(rep["missing"])})
    rep["changed_count"] = len(rep["changed"])
    return rep


def cmd_retry(ws: WS, spec: str) -> dict:
    d, manifest, name = batch_dir(ws, spec)
    ids = {s for s in manifest["batches"][name]["ids"] if s not in ws.src["strings"]}
    if not ids:
        return {"rows": 0, "note": "every row of this batch has a draft (or better)"}
    k = 1
    while (d / f"{name}.retry{k}.jsonl").exists():
        k += 1
    out = d / f"{name}.retry{k}.jsonl"
    cols = lf.COLUMNS["draft"][:-2] + CONTEXT_COLS + ["turkish", "note"]
    r = lf.cmd_export(ws.src, ws.proj.parent, ws.rows, out, "draft", "missing", "", 0, ws.glyphs, ids,
                      annotate=annotator(ws.context()), columns=cols)
    return {"rows": r["rows"], "file": str(out), "next": f"ingest WS FILE --batch {spec} --model NAME"}


def cmd_review(ws: WS, only, categories, size, ext, ids="") -> dict:
    size = size or 60
    if size < 1 or size > 400:
        raise Problem("--size: 1 to 400 rows per batch")
    rnd = ws.next_round("review", lambda n: (ws.priv / "review" / f"r{n:03d}").exists())
    d = ws.priv / "review" / f"r{rnd:03d}"
    cols = lf.COLUMNS["review"][:-4] + CONTEXT_COLS + ["origin"] + ALT_COLS + lf.COLUMNS["review"][-4:]
    lf.EXT[0] = ext
    r = lf.cmd_export(ws.src, ws.proj.parent, ws.rows, d, "review", only, "", size, ws.glyphs, ids or "",
                      annotate=annotator(ws.context(), categories, strings=ws.src["strings"]), columns=cols,
                      review_round=rnd)
    if not r["rows"]:
        shutil.rmtree(d, ignore_errors=True)
        ws.meta["rounds"]["review"] = rnd - 1
        raise Problem("nothing to review in that selection")
    shutil.copyfile(PROMPTS / "review.md", d / "PROMPT.md")
    ws.save_meta()
    return {"round": rnd, "rows": r["rows"], "files": r["files"],
            "next": "give each file with PROMPT.md to the reviewer (your choice of service); then review-in WS FILE "
                    "--reviewer NAME"}


def cmd_review_in(ws: WS, file: Path, reviewer: str, dry_run: bool) -> dict:
    if not NAME_RE.match(reviewer or ""):
        raise Problem("--reviewer: a short name such as gemini (letters, digits, . _ -)")
    rep = lf.cmd_import(ws.src, ws.proj.parent, ws.rows, lf.read_table(file), "review", reviewer, False, ws.glyphs)
    rep["written"] = bool(rep["changed"]) and not dry_run
    if rep["written"]:
        ws.save_project()
        ws.ledger({"action": "review", "file": file.name, "sha256": file_sha(file), "label": reviewer,
                   "changed": len(rep["changed"]), "rejected": len(rep["rejected"])})
    rep["changed_count"] = len(rep["changed"])
    return rep


HUMAN_COLS = ["id", "check", "group", "readiness", "display", "flags", "levels", "speakers", "max_bytes", "english",
              "turkish", "origin", "status", "review_by", "review_round", "verdict", "suggestion", "review_note",
              "alternative", "alt_reason", "problems", "final", "decision", "human_note", "text_check"]


def cmd_sheet(ws: WS, only, categories, ext) -> dict:
    n = ws.next_round("sheet", lambda k: any((ws.priv / "sheets").glob(f"sheet_{k:03d}.*")))
    out = ws.priv / "sheets" / f"sheet_{n:03d}{ext}"
    r = lf.cmd_export(ws.src, ws.proj.parent, ws.rows, out, "human", only, "", 0, ws.glyphs, "",
                      annotate=annotator(ws.context(), categories, strings=ws.src["strings"]), columns=HUMAN_COLS)
    if not r["rows"]:
        out.unlink(missing_ok=True)
        raise Problem("nothing to decide in that selection (no sheet written)")
    ws.save_meta()
    return {"rows": r["rows"], "file": str(out),
            "how": "fill 'decision' per row: approve (the 'final' text if you wrote one, else 'turkish'), accept (the "
                   "reviewer's suggestion), reject (drop the suggestion), redo (back to needs_review), or leave it "
                   "empty; to take the 'alternative', copy it into 'final' and approve; save as CSV UTF-8 and run "
                   "decide WS FILE"}


def cmd_suggest(ws: WS, file: Path, by: str, kind: str, dry_run: bool) -> dict:
    """M39: alternatives beside existing texts (columns id, check, alternative, alt_reason). An alternative never
    replaces the text, its status, its review or its revision counter; it waits for a person (or a reviewer) to choose
    it. Validated like a draft (codes, placeholders, font); the same alternative twice is stored once."""
    if not NAME_RE.match(by or ""):
        raise Problem("--by: a short name such as claude-opus-5.5 (letters, digits, . _ -)")
    if kind not in ALT_KINDS:
        raise Problem(f"--kind: one of {', '.join(ALT_KINDS)}")
    rep = {"changed": [], "unchanged": 0, "rejected": [], "warnings": []}
    for n, r in lf.read_table(file):
        sid = str(r.get("id", "")).strip()
        t = str(r.get("alternative", ""))
        c, e = ws.cat.get(sid), ws.src["strings"].get(sid)
        if c is None or e is None:
            rep["rejected"].append({"row": n, "id": sid, "reason": "no such entry (alternatives go beside an existing "
                                                                   "text; a new text is a draft)"})
            continue
        if str(r.get("check", "")).strip().lstrip("#") != lf.check_of(c["source_sha256"]) \
                or e["source_sha256"] != c["source_sha256"]:
            rep["rejected"].append({"row": n, "id": sid, "reason": "check differs (another English or a stale row)"})
            continue
        if not t.strip():
            rep["rejected"].append({"row": n, "id": sid, "reason": "no alternative text"})
            continue
        er, wa = lf.text_problems(sid, c["text"], t, ws.glyphs, c)
        if er:
            rep["rejected"].append({"row": n, "id": sid, "reason": "; ".join(er)})
            continue
        rep["warnings"] += [{"id": sid, "warning": w} for w in wa]
        if t == e["text"] or any(a["text"] == t for a in e.get("alt") or []):
            rep["unchanged"] += 1
            continue
        a = {"text": t, "by": by, "kind": kind, "reason": str(r.get("alt_reason", "")).strip()[:300], "created": now()}
        ws.src["strings"][sid] = dict(e, alt=list(e.get("alt") or []) + [a])
        rep["changed"].append(sid)
    rep["written"] = bool(rep["changed"]) and not dry_run
    if rep["written"]:
        ws.save_project()
        ws.ledger({"action": "suggest", "file": file.name, "sha256": file_sha(file), "label": by, "kind": kind,
                   "changed": len(rep["changed"]), "rejected": len(rep["rejected"])})
    rep["changed_count"] = len(rep["changed"])
    return rep


def cmd_integrate(ws: WS, file: Path, by: str, dry_run: bool) -> dict:
    """M47 (D-085): a reviewer's stored suggestion becomes the working text, for a preview build; it is never an
    approval. Rows: id, check, from_text (the text it replaces, as the project holds it now), text (must equal the
    pending review's suggestion: nothing else can be integrated), reason. The entry stays (or becomes) `reviewed`, the
    review keeps its verdict, round and note (its suggestion is now the text), the replaced text is kept as a
    `previous_draft` alternative, origin `integrated:<reviewer>.r<round>`. Approved entries are never touched; a stale
    row (from_text no longer the text) is refused; the same file twice changes nothing."""
    if not NAME_RE.match(by or ""):
        raise Problem("--by: a short name such as claude-opus-5.5 (letters, digits, . _ -)")
    rep = {"changed": [], "unchanged": 0, "skipped": [], "rejected": [], "warnings": []}
    for n, r in lf.read_table(file):
        sid = str(r.get("id", "")).strip()
        t, frm = str(r.get("text", "")), str(r.get("from_text", ""))
        c, e = ws.cat.get(sid), ws.src["strings"].get(sid)

        def reject(why):
            rep["rejected"].append({"row": n, "id": sid, "reason": why})
        if c is None or e is None:
            reject("no such entry")
            continue
        if str(r.get("check", "")).strip().lstrip("#") != lf.check_of(c["source_sha256"]) \
                or e["source_sha256"] != c["source_sha256"]:
            reject("check differs (another English or a stale row)")
            continue
        if loc.status_of(e) in ("approved", "needs_review"):   # a person's text, or a person's redo: theirs to settle
            rep["skipped"].append({"id": sid, "reason": f"{loc.status_of(e)}: left to the person's decision"})
            continue
        if e["text"] == t and str(e.get("origin", "")).startswith("integrated:"):
            rep["unchanged"] += 1
            continue
        if e["text"] != frm:
            reject("the project's text is not the row's from_text (a newer change, or a stale file)")
            continue
        rv = e.get("review") or {}
        if not t.strip() or rv.get("suggestion") != t:
            reject("only the pending review's own suggestion can be integrated")
            continue
        er, wa = lf.text_problems(sid, c["text"], t, ws.glyphs, c)
        if er:
            reject("; ".join(er))
            continue
        rep["warnings"] += [{"id": sid, "warning": w} for w in wa]
        rnd = rv.get("round", "")
        reason = str(r.get("reason", "")).strip()
        alts = [dict(x) for x in e.get("alt") or []]
        if not any(x["text"] == e["text"] for x in alts):
            alts.append({"text": e["text"], "by": e.get("origin", ""), "kind": "previous_draft",
                         "reason": f"replaced by the {rv.get('by', '')} r{rnd} suggestion (integrated by {by}; not "
                                   "approved)"})
        new_rv = {k: v for k, v in rv.items() if k != "suggestion"}
        new_rv["note"] = (f"[integrated by {by}{': ' + reason if reason else ''}] " + rv.get("note", ""))[:1000].strip()
        new = dict(e, text=t, status="reviewed", origin=f"integrated:{rv.get('by', '')}.r{rnd}", review=new_rv,
                   alt=alts)
        ws.src["strings"][sid] = new
        rep["changed"].append(sid)
    rep["written"] = bool(rep["changed"]) and not dry_run
    if rep["written"]:
        ws.save_project()
        ws.ledger({"action": "integrate", "file": file.name, "sha256": file_sha(file), "label": by,
                   "changed": len(rep["changed"]), "rejected": len(rep["rejected"])})
    rep["changed_count"] = len(rep["changed"])
    return rep


def cmd_decide(ws: WS, file: Path, dry_run: bool) -> dict:
    rep = lf.cmd_import(ws.src, ws.proj.parent, ws.rows, lf.read_table(file), "human", "", False, ws.glyphs)
    rep["written"] = bool(rep["changed"]) and not dry_run
    if rep["written"]:
        ws.save_project()
        ws.ledger({"action": "human", "file": file.name, "sha256": file_sha(file), "changed": len(rep["changed"]),
                   "rejected": len(rep["rejected"])})
    rep["changed_count"] = len(rep["changed"])
    return rep


def issues_of(ws: WS, with_build: bool) -> dict:
    """{id: [(stage, severity, detail)]} from validate (entries) plus the whole-project build check."""
    res = lf.cmd_validate(ws.src, ws.proj.parent, ws.rows, ws.glyphs, ws.terms,
                          ws.paths if with_build else None, ws.proj if with_build else None)
    out = {}
    for f in res["findings"]:
        out.setdefault(f["id"], []).append((f["stage"], f["severity"], f["detail"]))
    return out


def cmd_dashboard(ws: WS, report=None, with_build=True) -> dict:
    ctx = ws.context()
    issues = issues_of(ws, with_build)
    trans = [s for s, c in ws.cat.items() if c["text"].strip()]
    table = {}
    for sid in trans:
        g = ctx[sid]["group"]
        row = table.setdefault(g, {**{k: 0 for k in STATES}, "invalid": 0, "missing_context": 0, "total": 0})
        e = ws.src["strings"].get(sid)
        row["untranslated" if e is None else loc.status_of(e)] += 1
        row["total"] += 1
        if any(sev == "error" for _, sev, _ in issues.get(sid, [])):
            row["invalid"] += 1
        if ctx[sid]["readiness"] in ("needs_context", "verify_display"):
            row["missing_context"] += 1
    tot = {k: sum(r[k] for r in table.values()) for k in list(STATES) + ["invalid", "missing_context", "total"]}
    n = tot["total"] or 1
    drafted = n - tot["untranslated"]
    unknown = [s for s in ws.src["strings"] if s not in ws.cat]
    stale = [s for s, e in ws.src["strings"].items() if s in ws.cat and e["source_sha256"] != ws.cat[s]["source_sha256"]]
    fp = ws.meta.get("catalog_fingerprint", "")
    res = {"by_category": table, "total": tot,
           "coverage": {"any_text": round(100 * drafted / n, 1), "reviewed_or_approved":
                        round(100 * (tot["reviewed"] + tot["approved"]) / n, 1),
                        "approved_by_a_person": round(100 * tot["approved"] / n, 1)},
           "complete": tot["approved"] == tot["total"] and not tot["invalid"] and not stale and not unknown,
           "unreviewed_machine_or_draft_text": tot["draft"] + tot["needs_review"],
           "stale": stale, "unknown_ids": unknown,
           "catalog_changed_since_inventory": bool(fp) and fp != fingerprint(ws.cat),
           "pending_suggestions": sum(1 for e in ws.src["strings"].values() if (e.get("review") or {}).get("suggestion")),
           "with_alternatives": sum(1 for e in ws.src["strings"].values() if alt_columns(e)["alternative"]),
           "build_check": with_build}
    res["verdict"] = ("complete: every string approved by a person" if res["complete"] else
                      f"NOT complete: {tot['approved']} of {tot['total']} strings approved by a person "
                      f"({res['coverage']['approved_by_a_person']}%); {drafted} have some text "
                      f"({res['coverage']['any_text']}%), of which {tot['draft'] + tot['needs_review']} are unreviewed "
                      "drafts. Draft coverage is not localization coverage.")
    if report:
        cols = list(STATES) + ["invalid", "missing_context", "total"]
        lines = ["# Translation dashboard", "", f"{now()}. **{res['verdict']}**", "",
                 "| category | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
        for g in CATEGORIES:
            if g in table:
                lines.append(f"| {g} | " + " | ".join(str(table[g][k]) for k in cols) + " |")
        lines.append("| **all** | " + " | ".join(f"**{tot[k]}**" for k in cols) + " |")
        lines += ["", "- *invalid*: entries with a validation error (they cannot be built); *missing_context*: "
                  "strings whose category, speaker or display is not known well enough (readiness needs_context / "
                  "verify_display), translated or not.",
                  f"- Coverage: some text {res['coverage']['any_text']}%, reviewed or approved "
                  f"{res['coverage']['reviewed_or_approved']}%, **approved by a person "
                  f"{res['coverage']['approved_by_a_person']}%**.",
                  f"- Pending reviewer suggestions: {res['pending_suggestions']}; entries with an alternative: "
                  f"{res['with_alternatives']}; stale: {len(stale)}; unknown ids: "
                  f"{len(unknown)}; catalog changed since the inventory: {res['catalog_changed_since_inventory']}."]
        lf.atomic_write(Path(report), ("\n".join(lines) + "\n").encode("utf-8"))
        res["report"] = str(report)
    return res


QUEUE_ORDER = [  # (priority, test on the issues / state, action)
    (1, "invalid", "fix the text (it cannot be built): see 'issues'"),
    (2, "stale", "the game's English changed: refresh, then check the Turkish"),
    (3, "decision", "decide on the reviewer's suggestion (sheet: accept / reject / approve)"),
    (3, "alternative", "choose between the text and its alternative (copy it into 'final' to take it)"),
    (4, "question", "the reviewer asked a question: answer it in the sheet's human_note and decide"),
    (5, "overflow", "check the length on screen (line width, slot, subtitle lines)"),
    (6, "terminology", "align with the glossary, or record why not"),
    (7, "context", "find where and by whom it is said before approving"),
    (8, "unreviewed", "machine or first draft: review, then decide"),
    (9, "reviewed", "reviewed: decide"),
]


def cmd_queue(ws: WS, out: Path, with_english: bool, with_build=True) -> dict:
    ctx = ws.context()
    issues = issues_of(ws, with_build)
    rows = []
    for sid, e in ws.src["strings"].items():
        c = ws.cat.get(sid)
        x = ctx.get(sid, {"group": "unknown", "readiness": "needs_context", "display": "", "flags": ""})
        found = issues.get(sid, [])
        st = loc.status_of(e)
        rv = e.get("review") or {}
        tags = set()
        if any(sev == "error" for _, sev, _ in found):
            tags.add("invalid")
        if c is None or e["source_sha256"] != c["source_sha256"]:
            tags.add("stale")
        if rv.get("suggestion"):
            tags.add("decision")
        if alt_columns(e)["alternative"]:
            tags.add("alternative")
        if rv.get("verdict") == "question":
            tags.add("question")
        if any(stage in ("layout", "capacity") for stage, _, _ in found):
            tags.add("overflow")
        if any(stage == "review" and "glossary" in d for stage, _, d in found):
            tags.add("terminology")
        if x["readiness"] in ("needs_context", "verify_display") and st != "approved":
            tags.add("context")
        if st in ("draft", "needs_review"):
            tags.add("unreviewed")
        if st == "reviewed":
            tags.add("reviewed")
        if not tags:
            continue
        prio = min(p for p, t, _ in QUEUE_ORDER if t in tags)
        row = {"priority": prio, "id": sid, "group": x["group"], "readiness": x["readiness"], "status": st,
               "origin": e.get("origin", ""), "tags": " ".join(t for _, t, _ in QUEUE_ORDER if t in tags),
               "issues": "; ".join(f"{sev}:{stage}: {d}" for stage, sev, d in found),
               "action": next(a for p, t, a in QUEUE_ORDER if p == prio and t in tags)}
        if with_english:
            row.update(english=c["text"] if c else "", turkish=e["text"])
        rows.append(row)
    rows.sort(key=lambda r: (r["priority"], loc.sid_key(r["id"]) if r["id"] in ws.cat else (9,)))
    cols = ["priority", "id", "group", "readiness", "status", "origin", "tags", "issues", "action"] + \
        (["english", "turkish"] if with_english else [])
    out = Path(out) if out else ws.priv / "queue" / "queue.csv"
    if with_english:
        lf.private_path(out)   # refused before anything is created
    out.parent.mkdir(parents=True, exist_ok=True)
    lf.write_table(out, cols, rows)
    counts = {}
    for r in rows:
        counts[r["priority"]] = counts.get(r["priority"], 0) + 1
    return {"rows": len(rows), "file": str(out),
            "by_priority": {f"{p} " + "/".join(t for q, t, _ in QUEUE_ORDER if q == p): counts.get(p, 0)
                            for p in sorted({p for p, _, _ in QUEUE_ORDER})}}


def cmd_build(ws: WS, preview: bool, release: bool, ids: str, ids_file, as_zip: bool) -> dict:
    if preview == release:
        raise Problem("build: give --preview (NOT FINAL, every status) or --release (approved only)")
    if release and (ids or ids_file):
        raise Problem("a release build takes every approved string; --ids is for previews")
    want = split(ids)
    if ids_file:
        want |= {x.strip() for x in Path(ids_file).read_text(encoding="utf-8").split() if x.strip()}
    src = dict(ws.src)
    if want:   # exact ids, or prefixes ending in '.' (as for batch)
        unknown = sorted(w for w in want if not any(s == w or (w.endswith(".") and s.startswith(w))
                                                    for s in src["strings"]))
        if unknown:
            raise Problem(f"--ids: no entry for {', '.join(unknown[:10])}")
        keep = lf.id_filter(",".join(sorted(want)))
        src["strings"] = {s: e for s, e in src["strings"].items() if keep(s)}
    kind = "preview" if preview else "release"
    out_dir = ws.path / "build" / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    mid = src["id"] + (".dev" if preview else "")
    out = out_dir / (f"{mid}-{src['version']}" + ("-sample" if want else "")).replace(".", "_")   # no dot: OUT.zip
    fd, tmp = tempfile.mkstemp(dir=ws.proj.parent, prefix=".build_", suffix=".json")
    os.close(fd)
    tmp = Path(tmp)
    try:
        lf.write_project(tmp, src)
        Path(str(tmp) + ".bak").unlink(missing_ok=True)
        r = loc.cmd_build(ws.paths, tmp, out, as_zip, allow_unapproved=preview)
    finally:
        tmp.unlink(missing_ok=True)
        Path(str(tmp) + ".bak").unlink(missing_ok=True)
    pkg = Path(r["zip"]) if as_zip else Path(r["mod"])
    v = rm.cmd_validate(ws.paths, pkg)
    m = rm.parse_manifest(rm.read_package(pkg))
    rm.check_compat(m, ws.paths)
    r.update(kind=kind, validated={"ranges": v.get("ranges"), "overrides": v["overrides"]}, compatible=True,
             statuses={s: sum(1 for e in src["strings"].values() if loc.status_of(e) == s
                              and (preview or s == "approved")) for s in loc.STATUSES})
    if preview:
        r["warning"] = ("NOT FINAL: contains unreviewed draft / machine text; for private tests only, never a release")
    ws.ledger({"action": f"build-{kind}", "id": m["id"], "version": m["version"], "sha256": r.get("zip_sha256", r["sha256"]),
               "strings": r["strings"]})
    return r


# ---------------------------------------------------------------------------------------------------------------

def merge_glossary(current: dict, proposed: list, origin: str) -> dict:
    """Adds proposed terms; never changes a term whose status is approved (a person's decision); a proposed term
    replaces only another proposed one of the same English. Returns the counts."""
    terms = current.setdefault("terms", [])
    idx = {t["en"].lower(): i for i, t in enumerate(terms)}
    added = updated = kept = 0
    for p in proposed:
        p = dict(p, status="proposed", origin=origin)
        i = idx.get(p["en"].lower())
        if i is None:
            terms.append(p)
            idx[p["en"].lower()] = len(terms) - 1
            added += 1
        elif terms[i].get("status", "approved") == "approved":
            kept += 1
        else:
            terms[i] = p
            updated += 1
    return {"added": added, "updated": updated, "kept_approved": kept}


def selftest() -> int:
    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ' :: ' + str(detail)}")

    def sha(s):
        return rm.sha256_bytes(s.encode())
    groups = load_groups()
    check("context map: loads; every category known; ranges ordered",
          groups and all(g["category"] in CATEGORIES for g in groups))
    # synthetic catalog (original illustrative strings, not game text)
    cat_rows = [
        {"id": "en.180", "handle": 180, "kind": "text", "text": "Options", "capacity": 7, "source_sha256": sha("m")},
        {"id": "en.181", "handle": 181, "kind": "text", "text": "\\jcSave now?\\lYes", "capacity": 19,
         "source_sha256": sha("q")},
        {"id": "en.430", "handle": 430, "kind": "text", "text": "To climb, press \\f1:c\\f0:.", "capacity": 31,
         "source_sha256": sha("t")},
        {"id": "en.450", "handle": 450, "kind": "text", "text": "(NARRATOR) Read the sign.", "capacity": 27,
         "source_sha256": sha("n")},
        {"id": "en.600", "handle": 600, "kind": "text", "text": "Look at the moon!", "capacity": 19,
         "source_sha256": sha("d"), "category": "voiced line", "levels": ["demo_10"], "speakers": ["Abcd"]},
        {"id": "en.601", "handle": 601, "kind": "text", "text": "Look at the moon!", "capacity": 19,
         "source_sha256": sha("d2")},
        {"id": "en.380", "handle": 380, "kind": "text", "text": "\\jcInsert card %d", "capacity": 19,
         "source_sha256": sha("l"), "shared_with": ["fr.380"]},
        {"id": "en.1999", "handle": 1999, "kind": "text", "text": "Mystery", "capacity": 7, "source_sha256": sha("u")},
        {"id": "vs.en.7.0", "kind": "subtitle", "text": "Over the hill!", "source_sha256": sha("s"), "movie": 7,
         "movie_file": "", "category": "movie subtitle"},
    ]
    cat = lf.catalog_index(cat_rows)
    ctx = {s: classify(c, groups, duplicates(cat)) for s, c in cat.items()}
    check("classify: menu ready; tutorial with buttons ready; bracket tag needs context",
          ctx["en.180"]["group"] == "menu" and ctx["en.180"]["readiness"] == "ready" and "short" not in ctx["en.180"]["flags"]
          and ctx["en.430"]["group"] == "tutorial" and "buttons" in ctx["en.430"]["flags"]
          and ctx["en.450"]["readiness"] == "needs_context" and "speaker_tag" in ctx["en.450"]["flags"], ctx)
    check("classify: voiced dialogue partial context with level and speaker code; unvoiced needs context",
          ctx["en.600"]["readiness"] == "partial_context" and "speaker code Abcd" in ctx["en.600"]["display"]
          and ctx["en.601"]["readiness"] == "needs_context", ctx)
    check("classify: same English under two ids is flagged, each id kept",
          "same_english_as:en.601" in ctx["en.600"]["flags"] and "same_english_as:en.600" in ctx["en.601"]["flags"])
    check("classify: legacy / shared / placeholders / layout flags; unknown range needs context; subtitles",
          ctx["en.380"]["readiness"] == "verify_display" and "shared_with_other_languages" in ctx["en.380"]["flags"]
          and "placeholders" in ctx["en.380"]["flags"] and "layout_check" in ctx["en.181"]["flags"]
          and ctx["en.1999"]["group"] == "unknown" and ctx["en.1999"]["readiness"] == "needs_context"
          and ctx["vs.en.7.0"]["group"] == "subtitle" and "not verified" in ctx["vs.en.7.0"]["display"], ctx)
    check("fingerprint: changes when an English string changes",
          fingerprint(cat) != fingerprint(dict(cat, **{"en.180": dict(cat["en.180"], source_sha256=sha("x"))})))
    glyphs = frozenset("ğĞşŞıİ")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        w = td / "rayman3hd-turkish"
        cmd_new(w, "tr.test", "Türkçe (test)")
        meta = json.loads((w / "workspace.json").read_text(encoding="utf-8"))
        tracked_like = [p for p in w.rglob("*") if p.is_file() and "private" not in p.relative_to(w).parts]
        check("new: layout, metadata, ignore file; nothing English outside private/",
              meta["kind"] == WS_KIND and (w / "private" / "batches").is_dir() and (w / "STYLE.md").is_file()
              and "private/" in (w / ".gitignore").read_text(encoding="utf-8") and len(tracked_like) >= 6
              and lf.load_project(w / "tr.json")["target"]["min_port_version"] == rm.SUB_GROW_PORT)
        try:
            cmd_new(w, "tr.test", "x")
            check("new: refuses a folder that is not empty", False)
        except Problem:
            check("new: refuses a folder that is not empty", True)
        ws = WS(w, need_game=False)
        ws.rows, ws.cat, ws.glyphs = cat_rows, cat, glyphs
        orig_ctx = WS.context
        WS.context = lambda self: ctx
        try:
            # a draft round of the ready menu / tutorial strings, two per batch
            b = cmd_batch(ws, {"menu", "tutorial"}, {"ready"}, "", "", 2, ".jsonl")
            man = json.loads((w / "private" / "batches" / "r001" / "manifest.json").read_text(encoding="utf-8"))
            check("batch: round folder, manifest with ids and checks, prompt; only ready menu / tutorial rows",
                  b["round"] == 1 and b["rows"] == 3 and man["batches"]["batch_001"]["ids"] == ["en.180", "en.181"]
                  and man["batches"]["batch_002"]["ids"] == ["en.430"] and (w / "private/batches/r001/PROMPT.md").is_file(), b)
            rows = [x for _, x in lf.read_table(w / "private/batches/r001/batch_001.jsonl")]
            check("batch: rows carry the context columns", rows[0]["group"] == "menu" and rows[1]["flags"], rows)
            (w / "private" / "batches" / "r002").mkdir()   # left behind by an interrupted command
            b2 = cmd_batch(ws, None, None, "vs.en.,en.1999", "", 5, ".csv")
            check("batch: a folder left by an interrupted round is skipped, not fatal",
                  b2["round"] == 3 and json.loads((w / "workspace.json").read_text(encoding="utf-8"))["rounds"]["draft"] == 3, b2)
            check("batch: --ids takes exact ids and prefixes ending in '.'; a second round; CSV batches",
                  b2["rows"] == 2 and (w / "private/batches/r003/batch_001.csv").is_file(), b2)
            # a model answers batch_001: one good row, one row of another batch, one invented id; the other row missing
            ans = [dict(rows[0], turkish="Ayarlar"), dict(rows[0], id="en.430", check=lf.check_of(sha("t")),
                                                          turkish="Tırmanmak için \\f1:c\\f0:."),
                   dict(rows[0], id="en.9", turkish="x")]
            f = td / "ans.jsonl"
            f.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ans), encoding="utf-8")
            r = cmd_ingest(ws, f, "r001/batch_001", "model-a", False)
            check("ingest: good row as draft with provenance; rows of other batches and invented ids rejected; "
                  "the unanswered row is missing and retried",
                  r["changed"] == ["en.180"] and ws.src["strings"]["en.180"]["origin"] == "draft:model-a.r001.batch_001"
                  and {x["id"] for x in r["rejected"]} == {"en.430", "en.9"} and r["missing"] == ["en.181"]
                  and r["retry"] == ["en.181"] and ws.src["strings"]["en.180"]["status"] == "draft", r)
            led = (w / "ledger.jsonl").read_text(encoding="utf-8")
            check("ingest: the ledger records the file hash and counts, no text", '"action": "draft"' in led
                  and "Ayarlar" not in led and file_sha(f) in led)
            r2 = cmd_ingest(ws, f, "r001/batch_001", "model-a", False)
            check("ingest: the same answer twice changes nothing", not r2["changed"] and not r2["written"], r2)
            rt = cmd_retry(ws, "r001/batch_001")
            check("retry: exports only the batch's rows without a draft",
                  rt["rows"] == 1 and [x["id"] for _, x in lf.read_table(Path(rt["file"]))] == ["en.181"], rt)
            bad = [dict(rows[1], turkish="\\jcŞimdi kaydet?")]   # dropped \l is a warning; a dropped code is not
            (td / "b2.jsonl").write_text(json.dumps(dict(rows[1], turkish="Şimdi kaydet?\\lEvet"), ensure_ascii=False)
                                         + "\n", encoding="utf-8")
            r3 = cmd_ingest(ws, td / "b2.jsonl", "r001/batch_001", "model-a", False)
            check("ingest: a row that lost its \\jc code is rejected; the rest of the project is untouched",
                  r3["rejected"] and "codes" in r3["rejected"][0]["reason"] and "en.181" not in ws.src["strings"]
                  and ws.src["strings"]["en.180"]["text"] == "Ayarlar", r3)
            (td / "b3.jsonl").write_text(json.dumps(bad[0], ensure_ascii=False) + "\n", encoding="utf-8")
            r4 = cmd_ingest(ws, td / "b3.jsonl", "r001/batch_001", "model-b", True)
            check("ingest --dry-run: reports, writes nothing", r4["changed"] == ["en.181"] and not r4["written"]
                  and "en.181" not in lf.load_project(w / "tr.json")["strings"], r4)
            try:
                cmd_ingest(ws, f, "r009/batch_001", "model-a", False)
                check("ingest: an unknown batch is refused", False)
            except Problem:
                check("ingest: an unknown batch is refused", True)
            # a review round; the reviewer suggests; the approved text is never touched by a review
            rv = cmd_review(ws, "draft", None, 0, ".jsonl")
            rrows = [x for _, x in lf.read_table(Path(rv["files"][0]))]
            check("review: round 1 rows carry origin, context and round", rv["round"] == 1 and rrows[0]["round"] == "1"
                  and rrows[0]["origin"].startswith("draft:") and rrows[0]["group"] == "menu", rrows)
            (td / "rv.jsonl").write_text(json.dumps(dict(rrows[0], verdict="change", suggestion="Seçenekler",
                                                         review_note="menü terimi"), ensure_ascii=False) + "\n",
                                         encoding="utf-8")
            r5 = cmd_review_in(ws, td / "rv.jsonl", "gemini", False)
            e = ws.src["strings"]["en.180"]
            check("review-in: suggestion stored beside the text; text unchanged; reviewed, not approved",
                  e["text"] == "Ayarlar" and e["review"]["suggestion"] == "Seçenekler" and e["status"] == "reviewed"
                  and e["review"]["round"] == "1", e)
            # the bilingual decision sheet and a human decision
            sh = cmd_sheet(ws, "", None, ".csv")
            srows = [x for _, x in lf.read_table(Path(sh["file"]))]
            check("sheet: bilingual, with context, provenance, review, final and decision columns",
                  srows and srows[0]["english"] == "Options" and srows[0]["turkish"] == "Ayarlar"
                  and srows[0]["suggestion"] == "Seçenekler" and srows[0]["group"] == "menu"
                  and srows[0]["origin"].startswith("draft:") and set(HUMAN_COLS) <= set(srows[0]), srows)
            raw = Path(sh["file"]).read_bytes()
            check("sheet: UTF-8 with BOM; checks written as #hex", raw[:3] == b"\xef\xbb\xbf"
                  and b",#" + lf.check_of(sha("m")).encode() in raw)
            srows[0]["decision"] = "accept"
            lf.write_table(td / "dec.csv", HUMAN_COLS, srows)
            r6 = cmd_decide(ws, td / "dec.csv", False)
            r7 = cmd_decide(ws, td / "dec.csv", False)
            e = ws.src["strings"]["en.180"]
            check("decide: accept approves the suggestion; the same sheet again is a no-op",
                  e["status"] == "approved" and e["text"] == "Seçenekler" and e["origin"] == "review:gemini"
                  and not r7["changed"] and not r7["rejected"], (r6, r7, e))
            # an AI draft and a later review never change the approved text
            (td / "again.jsonl").write_text(json.dumps(dict(rows[0], turkish="Başka"), ensure_ascii=False) + "\n",
                                            encoding="utf-8")
            r8 = cmd_ingest(ws, td / "again.jsonl", "r001/batch_001", "model-c", False)
            rv2 = cmd_review(ws, "approved", None, 0, ".jsonl")
            rr2 = [x for _, x in lf.read_table(Path(rv2["files"][0]))]
            (td / "rv2.jsonl").write_text(json.dumps(dict(rr2[0], verdict="change", suggestion="Opsiyonlar"),
                                                     ensure_ascii=False) + "\n", encoding="utf-8")
            cmd_review_in(ws, td / "rv2.jsonl", "gemini", False)
            r9 = cmd_review_in(ws, td / "rv.jsonl", "gemini", False)   # a stale round-1 sheet
            e = ws.src["strings"]["en.180"]
            check("approved: a later draft is skipped, a review only adds a suggestion, a stale review is refused",
                  e["text"] == "Seçenekler" and e["status"] == "approved" and "approved" in r8["skipped"][0]["reason"]
                  and e["review"]["suggestion"] == "Opsiyonlar" and r9["rejected"], (r8, r9, e))
            srows[0]["decision"] = "approve"
            srows[0]["final"] = "Eski"
            lf.write_table(td / "old.csv", HUMAN_COLS, srows)
            r10 = cmd_decide(ws, td / "old.csv", False)
            check("decide: an old sheet cannot overwrite the newer decision state",
                  r10["rejected"] and ws.src["strings"]["en.180"]["text"] == "Seçenekler", r10)
            # M39: alternatives beside a draft and beside an approved text; never applied; idempotent
            ws.src["strings"]["en.430"] = {"source_sha256": sha("t"), "status": "draft",
                                           "text": "Tırmanmak için \\f1:c\\f0:.", "origin": "draft:model-a", "rev": "2"}
            before = json.dumps(ws.src["strings"]["en.180"], sort_keys=True)
            alt_rows = [{"id": "en.430", "check": lf.check_of(sha("t")), "alternative":
                         "Tırmanmak için \\f1:c\\f0: tuşuna bas.", "alt_reason": "the longer M37 wording"},
                        {"id": "en.180", "check": lf.check_of(sha("m")), "alternative": "Seçenek",
                         "alt_reason": "shorter"},
                        {"id": "en.181", "check": lf.check_of(sha("q")), "alternative": "x", "alt_reason": ""},
                        {"id": "en.430", "check": lf.check_of(sha("t")), "alternative": "Tırmanmak için bas.",
                         "alt_reason": "lost its code"},
                        {"id": "en.430", "check": "000000000000", "alternative": "Tırman \\f1:c\\f0:."}]
            lf.write_table(td / "alt.csv", ["id", "check", "alternative", "alt_reason"], alt_rows)
            sa = cmd_suggest(ws, td / "alt.csv", "model-a", "restored_longer", False)
            e430 = ws.src["strings"]["en.430"]
            check("suggest: stored beside the text; text, status and rev unchanged; an approved text keeps its text "
                  "and status; missing entries, lost codes and wrong checks rejected",
                  sa["changed"] == ["en.430", "en.180"] and e430["text"] == "Tırmanmak için \\f1:c\\f0:."
                  and e430["status"] == "draft" and e430["rev"] == "2" and e430["alt"][0]["kind"] == "restored_longer"
                  and ws.src["strings"]["en.180"]["text"] == "Seçenekler"
                  and ws.src["strings"]["en.180"]["status"] == "approved"
                  and json.loads(before)["text"] == "Seçenekler"
                  and [x["row"] for x in sa["rejected"]] == [4, 5, 6], sa)
            sa2 = cmd_suggest(ws, td / "alt.csv", "model-a", "restored_longer", False)
            check("suggest: the same file twice adds nothing", not sa2["changed"] and sa2["unchanged"] == 2
                  and len(ws.src["strings"]["en.430"]["alt"]) == 1, sa2)
            check("suggest: the project still loads (alt is a known key) and keeps the alternatives",
                  lf.load_project(w / "tr.json")["strings"]["en.430"]["alt"][0]["text"].endswith("tuşuna bas."))
            sh2 = cmd_sheet(ws, "all", None, ".csv")
            s2rows = {x["id"]: x for _, x in lf.read_table(Path(sh2["file"]))}
            check("sheet: the alternative and its reason beside the text",
                  s2rows["en.430"]["alternative"].endswith("tuşuna bas.")
                  and "restored_longer" in s2rows["en.430"]["alt_reason"] and s2rows["en.180"]["alternative"] == "Seçenek",
                  s2rows.get("en.430"))
            try:
                cmd_suggest(ws, td / "alt.csv", "model-a", "better", False)
                check("suggest: an unknown kind is refused", False)
            except Problem:
                check("suggest: an unknown kind is refused", True)
            # M47: integrate promotes a stored suggestion only; never approves; idempotent; approved untouched
            ws.src["strings"]["en.430"] = {"source_sha256": sha("t"), "status": "reviewed", "text": "Tırman \\f1:c\\f0:.",
                                           "origin": "draft:model-a", "rev": "1",
                                           "review": {"by": "gemini", "verdict": "change", "round": "2",
                                                      "suggestion": "Tırmanmak için \\f1:c\\f0:.", "note": "n"}}
            ig_rows = [{"id": "en.430", "check": lf.check_of(sha("t")), "from_text": "Tırman \\f1:c\\f0:.",
                        "text": "Tırmanmak için \\f1:c\\f0:.", "reason": "editorial candidate"},
                       {"id": "en.180", "check": lf.check_of(sha("m")), "from_text": "Seçenekler",
                        "text": "Opsiyonlar"}]
            lf.write_table(td / "ig.csv", ["id", "check", "from_text", "text", "reason"], ig_rows)
            ig = cmd_integrate(ws, td / "ig.csv", "agent-x", False)
            e430 = ws.src["strings"]["en.430"]
            check("integrate: the suggestion becomes the text; reviewed, not approved; previous text kept; review "
                  "keeps verdict and round; approved entry skipped",
                  ig["changed"] == ["en.430"] and e430["text"] == "Tırmanmak için \\f1:c\\f0:."
                  and e430["status"] == "reviewed" and e430["origin"] == "integrated:gemini.r2"
                  and e430["alt"][-1] == {**e430["alt"][-1], "text": "Tırman \\f1:c\\f0:.", "kind": "previous_draft"}
                  and e430["review"]["verdict"] == "change" and e430["review"]["round"] == "2"
                  and "suggestion" not in e430["review"] and e430["rev"] == "1"
                  and ws.src["strings"]["en.180"]["status"] == "approved" and ig["skipped"], ig)
            ig2 = cmd_integrate(ws, td / "ig.csv", "agent-x", False)
            check("integrate: the same file twice changes nothing; the project still loads",
                  not ig2["changed"] and ig2["unchanged"] == 1 and not ig2["rejected"]
                  and lf.load_project(w / "tr.json")["strings"]["en.430"]["status"] == "reviewed", ig2)
            ws.src["strings"]["en.430"] = dict(e430, text="X \\f1:c\\f0:.", origin="draft:b",
                                               review={"by": "gemini", "verdict": "change", "suggestion": "Y \\f1:c\\f0:."})
            lf.write_table(td / "ig3.csv", ["id", "check", "from_text", "text"],
                           [{"id": "en.430", "check": lf.check_of(sha("t")), "from_text": "Tırman \\f1:c\\f0:.",
                             "text": "Y \\f1:c\\f0:."},
                            {"id": "en.430", "check": lf.check_of(sha("t")), "from_text": "X \\f1:c\\f0:.",
                             "text": "Z \\f1:c\\f0:."},
                            {"id": "en.430", "check": lf.check_of(sha("t")), "from_text": "X \\f1:c\\f0:.",
                             "text": "Y"}])
            ig3 = cmd_integrate(ws, td / "ig3.csv", "agent-x", True)
            ws.src["strings"]["en.430"] = dict(ws.src["strings"]["en.430"],
                                               review={"by": "gemini", "verdict": "change", "suggestion": "Y"})
            lf.write_table(td / "ig4.csv", ["id", "check", "from_text", "text"],
                           [{"id": "en.430", "check": lf.check_of(sha("t")), "from_text": "X \\f1:c\\f0:.", "text": "Y"}])
            ig4 = cmd_integrate(ws, td / "ig4.csv", "agent-x", True)
            ws.src["strings"]["en.430"] = dict(ws.src["strings"]["en.430"], status="needs_review",
                                               review={"by": "gemini", "verdict": "change", "suggestion": "Y \\f1:c\\f0:."})
            lf.write_table(td / "ig5.csv", ["id", "check", "from_text", "text"],
                           [{"id": "en.430", "check": lf.check_of(sha("t")), "from_text": "X \\f1:c\\f0:.",
                             "text": "Y \\f1:c\\f0:."}])
            ig5 = cmd_integrate(ws, td / "ig5.csv", "agent-x", True)
            check("integrate: a stored suggestion that lost its code is refused by the row checks; a person's redo "
                  "(needs_review) is left alone", ig4["rejected"] and "codes" in ig4["rejected"][0]["reason"]
                  and not ig5["changed"] and ig5["skipped"], (ig4, ig5))
            check("integrate: a stale from_text and texts other than the stored suggestion (another wording, the "
                  "suggestion without its code) are refused", [x["row"] for x in ig3["rejected"]] == [2, 3, 4]
                  and not ig3["changed"], ig3)
            # dashboard: draft coverage is not completion
            ws.src["strings"]["en.430"] = {"source_sha256": sha("t"), "status": "draft", "text": "Tırmanmak için bas",
                                           "origin": "draft:model-a"}
            d = cmd_dashboard(ws, td / "dash.md", with_build=False)
            check("dashboard: per category; invalid counted; approved separate from drafted; not complete",
                  d["by_category"]["menu"]["approved"] == 1 and d["by_category"]["tutorial"]["invalid"] == 1
                  and d["by_category"]["tutorial"]["draft"] == 1 and not d["complete"]
                  and "NOT complete" in d["verdict"] and d["coverage"]["approved_by_a_person"] < d["coverage"]["any_text"]
                  and (td / "dash.md").is_file(), d)
            for s, c in cat.items():   # every string drafted by a machine: still not complete
                if s not in ws.src["strings"]:
                    ws.src["strings"][s] = {"source_sha256": c["source_sha256"], "status": "draft", "text": c["text"]
                                            .replace("Look", "Bak"), "origin": "draft:model-a"}
            d2 = cmd_dashboard(ws, None, with_build=False)
            check("dashboard: 100% machine-drafted is reported as NOT complete",
                  d2["coverage"]["any_text"] == 100.0 and not d2["complete"] and "NOT complete" in d2["verdict"], d2)
            q = cmd_queue(ws, td / "q.csv", False, with_build=False)
            qrows = [x for _, x in lf.read_table(td / "q.csv")]
            check("queue: sorted by issue; invalid first; context and pending decisions named; no English by default",
                  qrows[0]["id"] == "en.430" and qrows[0]["tags"].startswith("invalid")
                  and any("context" in x["tags"] for x in qrows) and any("decision" in x["tags"] for x in qrows)
                  and any("alternative" in x["tags"] for x in qrows)
                  and "english" not in qrows[0] and [int(x["priority"]) for x in qrows] == sorted(int(x["priority"]) for x in qrows), qrows[:3])
            cat2 = dict(cat, **{"en.180": dict(cat["en.180"], source_sha256=sha("m2"))})
            ws.cat, ws.rows = cat2, [cat2.get(r["id"], r) for r in cat_rows]
            d3 = cmd_dashboard(ws, None, with_build=False)
            check("dashboard: a changed English source is reported stale", d3["stale"] == ["en.180"], d3["stale"])
            ws.cat, ws.rows = cat, cat_rows
            # glossary merge never overwrites a person's approved term
            gl = {"terms": [{"en": "Hoodlum", "tr": ["Kapüşonlu"], "status": "approved"},
                            {"en": "Lum", "tr": ["Lum"], "status": "proposed"}]}
            m = merge_glossary(gl, [{"en": "hoodlum", "tr": ["Haydut"]}, {"en": "Lum", "tr": ["Lumlar"]},
                                    {"en": "Teensy", "tr": ["Teensy"]}], "claude-m37")
            check("glossary: proposed terms added / updated, an approved term kept",
                  m == {"added": 1, "updated": 1, "kept_approved": 1} and gl["terms"][0]["tr"] == ["Kapüşonlu"]
                  and gl["terms"][1]["tr"] == ["Lumlar"] and gl["terms"][2]["status"] == "proposed", m)
            check("glossary template: loads as a glossary", lf.load_glossary(w / "glossary.json") is not None)
        finally:
            WS.context = orig_ctx
        # private boundary: batches refused outside private/ in a Git tree
        g = td / "repo"
        (g / ".git").mkdir(parents=True)
        try:
            lf.write_table(g / "batch.jsonl", ["id"], [])
            check("boundary: an English-bearing table outside private/ of a Git tree is refused", False)
        except lf.Problem:
            check("boundary: an English-bearing table outside private/ of a Git tree is refused", True)
    # the tracked template carries no game text: only names in the glossary, no English sentences
    tmpl = "".join(p.read_text(encoding="utf-8") for p in TEMPLATE.iterdir() if p.is_file())
    check("template: present (README, STYLE, glossary, ignore file)",
          all((TEMPLATE / f).is_file() for f in ("README.md", "STYLE.md", "glossary.json", "gitignore.txt")))
    check("template: the ignore file keeps private/ and build/ out", "private/" in (TEMPLATE / "gitignore.txt").read_text(
        encoding="utf-8") and "build/" in (TEMPLATE / "gitignore.txt").read_text(encoding="utf-8") and tmpl)
    n = results.count(False)
    print(f"R3HD_TRWORK_SELFTEST {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}")
    return 1 if n else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["new", "inventory", "batch", "ingest", "retry", "review", "review-in", "suggest",
                                    "integrate", "sheet", "decide", "dashboard", "queue", "build", "selftest"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--id", default="tr.full")
    ap.add_argument("--name", default="Türkçe")
    ap.add_argument("--category", default="")
    ap.add_argument("--readiness", default="")
    ap.add_argument("--ids", default="")
    ap.add_argument("--ids-file")
    ap.add_argument("--only", default="")
    ap.add_argument("--size", type=int, default=0, help="rows per batch (batch: 40, review: 60)")
    ap.add_argument("--ext", default=".jsonl", choices=[".jsonl", ".csv", ".tsv"])
    ap.add_argument("--batch")
    ap.add_argument("--model")
    ap.add_argument("--reviewer")
    ap.add_argument("--by", help="suggest: who proposes the alternatives")
    ap.add_argument("--kind", default="proposal", help="suggest: restored_longer, proposal or previous_draft")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report")
    ap.add_argument("--out")
    ap.add_argument("--with-english", action="store_true")
    ap.add_argument("--no-build-check", action="store_true", help="dashboard / queue: entry checks only (faster)")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--release", action="store_true")
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--game-dir")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    code = 0
    try:
        if not a.args:
            raise Problem(f"{a.cmd} WS ...")
        if a.cmd == "new":
            r = cmd_new(Path(a.args[0]), a.id, a.name)
        else:
            ws = WS(Path(a.args[0]), a.game_dir)
            cats = checked(split(a.category), CATEGORIES, "--category")
            ready = checked(split(a.readiness), READINESS, "--readiness")
            file = Path(a.args[1]) if len(a.args) > 1 else None
            if a.cmd in ("ingest", "review-in", "decide", "suggest", "integrate") and file is None:
                raise Problem(f"{a.cmd} WS FILE ...")
            if a.cmd == "inventory":
                r = cmd_inventory(ws)
            elif a.cmd == "batch":
                r = cmd_batch(ws, cats, ready, a.ids, a.only, a.size or 40, a.ext)
            elif a.cmd == "ingest":
                r = cmd_ingest(ws, file, a.batch, a.model, a.dry_run)
                code = 1 if r["rejected"] else 0
            elif a.cmd == "retry":
                r = cmd_retry(ws, a.batch)
            elif a.cmd == "review":
                r = cmd_review(ws, a.only, cats, a.size or 60, a.ext,
                               ",".join([a.ids] + (Path(a.ids_file).read_text(encoding="utf-8").split()
                                                   if a.ids_file else [])))
            elif a.cmd == "review-in":
                r = cmd_review_in(ws, file, a.reviewer, a.dry_run)
                code = 1 if r["rejected"] else 0
            elif a.cmd == "suggest":
                r = cmd_suggest(ws, file, a.by, a.kind, a.dry_run)
                code = 1 if r["rejected"] else 0
            elif a.cmd == "integrate":
                r = cmd_integrate(ws, file, a.by, a.dry_run)
                code = 1 if r["rejected"] else 0
            elif a.cmd == "sheet":
                r = cmd_sheet(ws, a.only, cats, a.ext if a.ext != ".jsonl" else ".csv")
            elif a.cmd == "decide":
                r = cmd_decide(ws, file, a.dry_run)
                code = 1 if r["rejected"] else 0
            elif a.cmd == "dashboard":
                r = cmd_dashboard(ws, a.report, not a.no_build_check)
            elif a.cmd == "queue":
                r = cmd_queue(ws, a.out, a.with_english, not a.no_build_check)
            else:
                r = cmd_build(ws, a.preview, a.release, a.ids, a.ids_file, a.zip)
        r = {"result": "ok" if not code else "problems", **r}
    except (Problem, lf.Problem, loc.Problem, rm.Refusal) as x:
        r, code = {"result": "refused", "detail": getattr(x, "detail", str(x))}, 2
    except (OSError, ValueError, KeyError, TypeError) as x:
        r, code = {"result": "refused", "detail": f"{type(x).__name__}: {x}"}, 2
    sys.stdout.buffer.write((json.dumps(r, indent=1, ensure_ascii=a.json, default=str) + "\n").encode("utf-8"))
    return code


if __name__ == "__main__":
    sys.exit(main())
