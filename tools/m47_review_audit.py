#!/usr/bin/env python3
"""M47: returned review rounds -> one reconciled, rerunnable integration (D-085).

A reviewer (a second model) returns every exported review batch (`private/review/rNNN/batch_NNN.jsonl`) as a table.
Before anything enters the project, this tool checks each returned table against the batch it was made from (the
export is authoritative for ids, order, English, Turkish and metadata; only `verdict`, `suggestion`, `review_note` are
the reviewer's), writes a derived copy whose metadata is restored from the export (the returned file is never
changed), and proves the derived copies with the project's own importer on an isolated copy of the workspace.

`merge` then reduces the overlapping rounds to one row per string id: a consolidated review (`review-in`, once) and
the suggestions chosen for integration (`r3hd_trwork.py integrate`), from the editorial dispositions and the
resolution file of the person running it. Nothing here approves a string: integrated text stays `reviewed`.

  audit WS [--returned DIR] [--out DIR] [--expect r001=7:375,...]
  merge WS [--out DIR] --resolution FILE          (writes OUT/merge; put a proposals.tsv beside it to add
                                                   alternatives: id, check, alternative, alt_reason)
  apply WS [--out DIR] [--isolated]               (review-in, suggest --kind proposal, integrate; ledger-guarded)
  verify WS [--out DIR]
  selftest

Every output holds the game's English: it is written under a private/ folder only (as r3hd_locflow exports). Reports
printed to the console hold ids and counts, never text.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_loc as loc  # noqa: E402
import r3hd_locflow as lf  # noqa: E402
import r3hd_trwork as tw  # noqa: E402

FILE_RE = re.compile(r"^r(\d{3})_batch_(\d{3})\.tsv$")
REVIEW_FIELDS = ("verdict", "suggestion", "review_note")
IDENTITY = ("id", "check", "english", "turkish")   # a difference here means another text was reviewed: never repaired


class Problem(Exception):
    pass


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def cell(v) -> str:
    return "" if v is None else v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def read_source(path: Path) -> list:
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if line.strip():
            try:
                rows.append({k: cell(v) for k, v in json.loads(line).items()})
            except ValueError as x:
                raise Problem(f"{path.name} line {n}: not JSON ({x})")
    return rows


def compare(src_rows: list, raw: bytes, rnd: int) -> dict:
    """One returned TSV against its export. Pure: no project, no game data. Returns
    {fatal: [..], repaired: {field: n}, warnings: [..], verdicts: Counter, rows: n, derived: [row dicts] | None}."""
    res = {"fatal": [], "repaired": Counter(), "warnings": [], "verdicts": Counter(), "rows": 0, "derived": None,
           "bom": raw.startswith(b"\xef\xbb\xbf"), "crlf": b"\r\n" in raw}
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as x:
        res["fatal"].append(f"not UTF-8 ({x.reason} at byte {x.start})")
        return res
    if "�" in text:
        res["fatal"].append("U+FFFD replacement characters (text lost in a re-encoding)")
    if not src_rows:
        res["fatal"].append("the export has no rows")
        return res
    cols = list(src_rows[0])
    table = list(csv.reader(io.StringIO(text, newline=""), delimiter="\t"))
    if not table:
        res["fatal"].append("empty file")
        return res
    head = [h.strip() for h in table[0]]
    if head != cols:
        res["fatal"].append(f"header differs from the export (missing {sorted(set(cols) - set(head))}, extra "
                            f"{sorted(set(head) - set(cols))}, order {'same' if sorted(head) == sorted(cols) else 'n/a'})")
        return res
    body = [r for r in table[1:] if any(c.strip() for c in r)]
    res["rows"] = len(body)
    for n, r in enumerate(body, 2):
        if len(r) != len(cols):
            res["fatal"].append(f"line {n}: {len(r)} cells for {len(cols)} columns (a tab inside a cell?)")
    if res["fatal"]:
        return res
    # cells as the importer reads them (r3hd_locflow.read_table): '#hex' checks and formula-guard apostrophes undone
    got = [{c: lf.sheet_value(c, v) for c, v in zip(cols, r)} for r in body]
    ids, sids = [g["id"] for g in got], [s["id"] for s in src_rows]
    dup = sorted(k for k, v in Counter(ids).items() if v > 1)
    if dup:
        res["fatal"].append(f"duplicated ids {dup[:10]}")
    if set(ids) - set(sids):
        res["fatal"].append(f"ids not in the export {sorted(set(ids) - set(sids))[:10]}")
    if set(sids) - set(ids):
        res["fatal"].append(f"ids of the export missing {sorted(set(sids) - set(ids))[:10]}")
    if not res["fatal"] and ids != sids:
        res["fatal"].append("row order differs from the export")
    if res["fatal"]:
        return res
    derived = []
    for s, g in zip(src_rows, got):
        for k in cols:
            if k in REVIEW_FIELDS or g[k] == s[k]:
                continue
            if k in IDENTITY:
                res["fatal"].append(f"{s['id']}: '{k}' differs from the export (another text was reviewed)")
            else:
                res["repaired"][k] += 1
        if s.get("round", "") != str(rnd):
            res["fatal"].append(f"{s['id']}: the export's own round is {s.get('round')!r}, not {rnd}")
        v = g["verdict"].strip().lower()
        res["verdicts"][v or "(empty)"] += 1
        if v not in loc.VERDICTS:
            res["fatal"].append(f"{s['id']}: verdict {g['verdict']!r} (one of {', '.join(loc.VERDICTS)})")
        sug = g["suggestion"]
        if v == "change" and not sug.strip():
            res["fatal"].append(f"{s['id']}: change without a suggestion")
        if v == "change" and sug == s["turkish"]:
            res["warnings"].append(f"{s['id']}: change whose suggestion equals the current text (a no-op)")
        if v in ("ok", "question") and sug.strip() and sug != s["turkish"]:
            res["warnings"].append(f"{s['id']}: {v} with a suggestion")
        if sug != sug.strip():
            res["warnings"].append(f"{s['id']}: suggestion with leading or trailing spaces")
        d = dict(s)
        d.update({k: g[k] for k in REVIEW_FIELDS})
        d["verdict"] = v
        derived.append(d)
    if not res["fatal"]:
        res["derived"] = derived
    return res


def export_view(src: dict) -> dict:
    """The project as the review rounds saw it: an entry this tool's apply step integrated gets back the text it
    replaced (its last `previous_draft` alternative written by integrate), and a pending review is dropped (a
    non-approved entry is a draft again). Approved entries stay as they are. Lets audit and merge run again after
    apply (a rerun) without calling the integrated rows stale."""
    out = dict(src, strings={})
    for sid, e in src["strings"].items():
        e = dict(e)
        if loc.status_of(e) != "approved":
            if str(e.get("origin", "")).startswith("integrated:"):
                prev = [a for a in e.get("alt") or [] if a.get("kind") == "previous_draft"
                        and "(integrated by " in a.get("reason", "")]
                if prev:
                    e["text"], e["origin"] = prev[-1]["text"], prev[-1].get("by", "")
            if e.pop("review", None) is not None and e.get("status") == "reviewed":
                e["status"] = "draft"
        out["strings"][sid] = e
    return out


def private_out(p: Path) -> Path:
    lf.private_path(p)
    rel = p.resolve().parts
    if "private" not in rel:
        raise Problem(f"{p}: outputs hold the game's text; write them under a private/ folder")
    return p


def cmd_audit(ws_path: Path, returned: Path, out: Path, expect: str, game_dir=None) -> dict:
    out = private_out(out)
    ws = tw.WS(ws_path, game_dir)
    applied = sum(1 for e in ws.src["strings"].values() if e.get("review"))
    ws.src = export_view(ws.src)   # after an apply: the state the rounds were exported from
    review = ws.priv / "review"
    files = sorted(p for p in returned.iterdir() if FILE_RE.match(p.name))
    sources = sorted(review.glob("r[0-9][0-9][0-9]/batch_[0-9][0-9][0-9].jsonl"))
    want = {f"{p.parent.name}_{p.stem}.tsv" for p in sources}
    have = {p.name for p in files}
    rep = {"workspace": str(ws_path), "returned_dir": str(returned), "files": [], "missing_returns": sorted(want - have),
           "unexpected_returns": sorted(have - want), "fatal": 0, "rounds": {}, "importer": {}, "project": {},
           "cross_round": {}}
    out.mkdir(parents=True, exist_ok=True)
    (out / "derived").mkdir(exist_ok=True)
    per_id = defaultdict(list)
    derived_files = []
    for p in files:
        m = FILE_RE.match(p.name)
        rnd, bn = int(m.group(1)), int(m.group(2))
        srcp = review / f"r{rnd:03d}" / f"batch_{bn:03d}.jsonl"
        raw = p.read_bytes()
        if not srcp.is_file():
            rep["files"].append({"file": p.name, "fatal": ["no export for this file"]})
            rep["fatal"] += 1
            continue
        src_rows = read_source(srcp)
        r = compare(src_rows, raw, rnd)
        # against the project: the import needs the same English (catalog) and the project's current Turkish
        stale, glyph_err, over = [], [], []
        for d in r["derived"] or []:
            c, e = ws.cat.get(d["id"]), ws.src["strings"].get(d["id"])
            if c is None or lf.check_of(c["source_sha256"]) != d["check"].lstrip("#") or c["text"] != d["english"]:
                r["fatal"].append(f"{d['id']}: the export no longer matches the game's catalog")
                continue
            if e is None or e["text"] != d["turkish"]:
                stale.append(d["id"])
            if d["suggestion"].strip() and d["suggestion"] != d["turkish"]:
                er, wa = lf.text_problems(d["id"], c["text"], d["suggestion"], ws.glyphs, c)
                if er:
                    glyph_err.append({"id": d["id"], "errors": er})
                if any("for a slot of" in w for w in wa):
                    over.append(d["id"])
            per_id[d["id"]].append({"round": rnd, "batch": bn, "verdict": d["verdict"]})
        if stale:
            r["fatal"].append(f"{len(stale)} rows review a Turkish text the project no longer holds: {stale[:10]}")
        if r["fatal"]:
            r["derived"] = None
        entry = {"file": p.name, "export": f"{srcp.parent.name}/{srcp.name}", "sha256": sha(raw), "bytes": len(raw),
                 "bom": r["bom"], "line_ends": "CRLF" if r["crlf"] else "LF", "rows": r["rows"],
                 "export_rows": len(src_rows), "verdicts": dict(sorted(r["verdicts"].items())),
                 "repaired": dict(r["repaired"]), "fatal": r["fatal"], "warnings": r["warnings"],
                 "suggestion_errors": glyph_err, "suggestions_over_slot": over}
        if r["derived"] is not None:
            dp = out / "derived" / p.name
            lf.write_table(dp, list(src_rows[0]), r["derived"])
            entry["derived"] = f"derived/{p.name}"
            entry["derived_sha256"] = sha(dp.read_bytes())
            derived_files.append((rnd, bn, dp))
        rep["fatal"] += len(r["fatal"]) + len(glyph_err)
        rep["files"].append(entry)
        rr = rep["rounds"].setdefault(f"r{rnd:03d}", {"batches": 0, "rows": 0, "verdicts": Counter()})
        rr["batches"] += 1
        rr["rows"] += r["rows"]
        rr["verdicts"].update(r["verdicts"])
    for k in rep["rounds"]:
        rep["rounds"][k]["verdicts"] = dict(sorted(rep["rounds"][k]["verdicts"].items()))
    rep["fatal"] += len(rep["missing_returns"]) + len(rep["unexpected_returns"])
    if expect:
        for item in expect.split(","):
            k, v = item.split("=")
            b, n = (int(x) for x in v.split(":"))
            got = rep["rounds"].get(k, {"batches": 0, "rows": 0})
            ok = got["batches"] == b and got["rows"] == n
            rep.setdefault("expect", {})[k] = {"batches": b, "rows": n, "ok": ok}
            rep["fatal"] += 0 if ok else 1
    multi = {k: v for k, v in per_id.items() if len(v) > 1}
    rep["cross_round"] = {"unique_ids": len(per_id), "occurrences": sum(map(len, per_id.values())),
                          "ids_in_several_rounds": len(multi),
                          "round_sets": dict(Counter("+".join(f"r{x['round']:03d}" for x in v)
                                                     for v in multi.values())),
                          "disagreeing_ids": sorted((k for k, v in multi.items()
                                                     if len({x["verdict"] for x in v}) > 1), key=loc.sid_key)}
    rep["project"] = {"entries": len(ws.src["strings"]), "entries_with_a_review_before_the_view": applied,
                      "statuses": dict(Counter(loc.status_of(e) for e in ws.src["strings"].values())),
                      "unreviewed_entries": sorted(set(ws.src["strings"]) - set(per_id), key=loc.sid_key)[:20],
                      "unreviewed_count": len(set(ws.src["strings"]) - set(per_id))}
    # The importer itself, on an isolated copy: every derived file alone against the untouched project (dry run), and
    # the raw files that needed a repair, to show what they would have stored.
    base = copy.deepcopy(ws.src)
    with tempfile.TemporaryDirectory(prefix="m47_iso_", dir=out) as td:
        iso = Path(td) / "ws"
        shutil.copytree(ws_path, iso, ignore=shutil.ignore_patterns("build", "private"))
        wsi = tw.WS(iso, game_dir)
        before = sha((iso / "tr.json").read_bytes())
        for rnd, bn, dp in derived_files:
            wsi.src = copy.deepcopy(base)
            r = tw.cmd_review_in(wsi, dp, "gemini", True)
            rounds = Counter((e.get("review") or {}).get("round", "") for s, e in wsi.src["strings"].items()
                             if s in r["changed"])
            rep["importer"][dp.name] = {"changed": r["changed_count"], "unchanged": r["unchanged"],
                                        "rejected": len(r["rejected"]), "skipped": len(r["skipped"]),
                                        "stored_rounds": dict(rounds), "written": r["written"]}
            if r["rejected"] or r["changed_count"] + r["unchanged"] != sum(1 for _ in lf.read_table(dp)) \
                    or set(rounds) != {str(rnd)}:
                rep["fatal"] += 1
        for f in rep["files"]:
            if f.get("repaired"):
                wsi.src = copy.deepcopy(base)
                r = tw.cmd_review_in(wsi, returned / f["file"], "gemini", True)
                rounds = Counter((e.get("review") or {}).get("round", "") for s, e in wsi.src["strings"].items()
                                 if s in r["changed"])
                rep["importer"]["raw:" + f["file"]] = {"changed": r["changed_count"], "rejected": len(r["rejected"]),
                                                       "stored_rounds": dict(rounds),
                                                       "note": "the raw file, for comparison only: never imported"}
        rep["isolated_copy_untouched"] = sha((iso / "tr.json").read_bytes()) == before
    rep["result"] = "PASS" if rep["fatal"] == 0 and rep["isolated_copy_untouched"] else "FAIL"
    lf.atomic_write(out / "audit.json", (json.dumps(rep, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode())
    return rep


# ---------------------------------------------------------------------------------------------------------------

def selftest() -> int:
    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ' :: ' + str(detail)}")

    cols = ["id", "check", "kind", "english", "turkish", "status", "round", "verdict", "suggestion", "review_note"]
    src = [dict(zip(cols, [f"en.{i}", f"c{i:011d}", "text", f"E{i}", f"T{i}", "draft", "1", "", "", ""]))
           for i in range(1, 5)]

    def tsv(rows, head=cols, bom=False, sep="\t"):
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=sep, lineterminator="\r\n")
        w.writerow(head)
        for r in rows:
            w.writerow([r.get(c, "") for c in head])
        return (b"\xef\xbb\xbf" if bom else b"") + buf.getvalue().encode("utf-8")

    def ret(**over):
        rows = [dict(r, verdict="ok") for r in src]
        for i, kv in over.items():
            rows[int(i)].update(kv)
        return rows

    r = compare(src, tsv(ret()), 1)
    check("a clean return passes; the derived rows equal the export plus the verdicts",
          not r["fatal"] and r["derived"] == [dict(s, verdict="ok") for s in src] and r["verdicts"]["ok"] == 4, r)
    r = compare(src, tsv(ret(**{"0": {"round": "3"}, "1": {"round": "3"}})), 1)
    check("a drifted round is repaired from the export, counted, never kept",
          not r["fatal"] and r["repaired"] == {"round": 2} and all(d["round"] == "1" for d in r["derived"]), r)
    r = compare(src, tsv(ret(**{"2": {"turkish": "X"}})), 1)
    check("a changed Turkish is fatal (another text was reviewed)", r["fatal"] and r["derived"] is None, r)
    r = compare(src, tsv(ret(**{"2": {"english": "X"}})), 1)
    check("a changed English is fatal", r["fatal"] and r["derived"] is None, r)
    rows = ret()
    rows[0], rows[1] = rows[1], rows[0]
    check("swapped rows are fatal", compare(src, tsv(rows), 1)["fatal"])
    check("a missing row is fatal", compare(src, tsv(ret()[:3]), 1)["fatal"])
    check("a duplicated row is fatal", compare(src, tsv(ret() + [ret()[0]]), 1)["fatal"])
    check("an invented id is fatal", compare(src, tsv(ret(**{"3": {"id": "en.99"}})), 1)["fatal"])
    check("a bad verdict is fatal", compare(src, tsv(ret(**{"1": {"verdict": "fine"}})), 1)["fatal"])
    check("change without a suggestion is fatal", compare(src, tsv(ret(**{"1": {"verdict": "change"}})), 1)["fatal"])
    r = compare(src, tsv(ret(**{"1": {"verdict": "change", "suggestion": "T2"}})), 1)
    check("a no-op change is a warning, not fatal", not r["fatal"] and r["warnings"], r)
    check("another header is fatal", compare(src, tsv(ret(), head=cols[::-1]), 1)["fatal"])
    check("a comma file is fatal (not tab separated)", compare(src, tsv(ret(), sep=","), 1)["fatal"])
    check("non-UTF-8 is fatal", compare(src, tsv(ret()).replace(b"T1", b"T\xfe1"), 1)["fatal"])
    check("U+FFFD is fatal", compare(src, tsv(ret(**{"1": {"review_note": "�"}})), 1)["fatal"])
    check("a BOM is accepted and recorded", compare(src, tsv(ret(), bom=True), 1)["bom"])
    r = compare(src, tsv(ret()), 2)
    check("an export of another round than its folder is fatal", r["fatal"], r)
    selftest_merge(check)
    src = {"strings": {
        "en.1": {"text": "B", "status": "reviewed", "origin": "integrated:gemini.r2",
                 "review": {"by": "gemini", "verdict": "change"},
                 "alt": [{"text": "A", "by": "draft:m", "kind": "previous_draft", "reason": "x (integrated by c; not approved)"}]},
        "en.2": {"text": "C", "status": "approved", "origin": "human", "review": {"by": "g", "verdict": "ok"}},
        "en.3": {"text": "D", "status": "reviewed", "origin": "draft:m", "review": {"by": "g", "verdict": "ok"}}}}
    v = export_view(src)["strings"]
    check("export view: an integrated entry gets back the text it replaced; reviews dropped; approved untouched",
          v["en.1"]["text"] == "A" and v["en.1"]["status"] == "draft" and "review" not in v["en.1"]
          and v["en.2"] == src["strings"]["en.2"] and v["en.3"]["status"] == "draft" and src["strings"]["en.1"]["text"] == "B", v)
    n = len(results)
    print(f"M47_REVIEW_AUDIT selftest {'PASS' if all(results) else 'FAIL'} {sum(results)}/{n}")
    return 0 if all(results) else 1


def selftest_merge(check):
    occ = [{"round": 1, "verdict": "change", "suggestion": "A", "review_note": "x"},
           {"round": 3, "verdict": "ok", "suggestion": "", "review_note": ""}]
    d = decisive(occ)
    check("merge: the decisive review is the latest non-ok one (a later ok never hides an earlier change)",
          d["round"] == 1 and d["verdict"] == "change", d)
    check("merge: without a non-ok review, the latest round decides",
          decisive([dict(occ[1], round=2), occ[1]])["round"] == 3)
    check("merge: the order of the occurrences does not matter", decisive(occ[::-1]) == d)
    note = consolidated_note(occ, [{"round": "1", "editor_disposition": "accept_candidate"}],
                             {"action": "integrate", "reason": "r"})
    check("merge: the note names every round, the editorial disposition and the resolution",
          "r001 change" in note and "r003 ok" in note and "accept_candidate" in note and "integrate" in note, note)
    return None


def decisive(occ: list) -> dict:
    """The review that speaks for an id across overlapping rounds: the latest round with a non-ok verdict, else the
    latest round. Deterministic and independent of the order the rounds are read in."""
    s = sorted(occ, key=lambda o: int(o["round"]))
    bad = [o for o in s if o["verdict"] != "ok"]
    return (bad or s)[-1]


def consolidated_note(occ: list, editorial: list, res) -> str:
    seen = "; ".join("r%03d %s" % (int(o["round"]), o["verdict"]) for o in sorted(occ, key=lambda o: int(o["round"])))
    parts = [f"[M47 consolidated: {seen}]"]
    for e in sorted(editorial, key=lambda e: str(e.get("round", ""))):
        parts.append(f"[editorial r{int(e['round']):03d}: {e['editor_disposition']}]")
    if res:
        parts.append(f"[M47 {res['action']}{': ' + res['reason'] if res.get('reason') else ''}]")
    d = decisive(occ)
    if d.get("review_note"):
        parts.append(d["review_note"])
    return " ".join(parts)[:1000]


ACTIONS = ("integrate", "keep", "hold")


def cmd_merge(ws_path: Path, out: Path, resolution: Path, returned: Path, game_dir=None) -> dict:
    """One row per id from the derived (repaired) audit files, the editorial dispositions and the resolution file
    (id, action = integrate | keep | hold, group, reason). Fails closed: every id with a non-ok verdict or an
    editorial row needs a resolution, and only a decisive `change` suggestion can be integrated."""
    out = private_out(out)
    audit = out.parent / "audit"
    aj = json.loads((audit / "audit.json").read_text(encoding="utf-8"))
    if aj.get("result") != "PASS":
        raise Problem("the audit did not pass: merge refuses")
    ws = tw.WS(ws_path, game_dir)
    ws.src = export_view(ws.src)
    occ = defaultdict(list)
    for f in aj["files"]:
        p = audit / f["derived"]
        if sha(p.read_bytes()) != f["derived_sha256"]:
            raise Problem(f"{p.name} changed since the audit")
        for n, r in lf.read_table(p):
            occ[r["id"]].append(dict(r, round=int(r["round"]), batch=p.stem))
    ed, ed_problems = defaultdict(list), []
    for p in sorted(returned.glob("r[0-9][0-9][0-9]_editorial_decisions.tsv")):
        for n, r in lf.read_table(p):
            sid, rnd = r["id"], int(r["round"])
            hit = [o for o in occ.get(sid, []) if o["round"] == rnd and o["batch"] == Path(r["batch"]).stem]
            if not hit:
                ed_problems.append(f"{p.name} line {n}: {sid} has no review in {r['batch']}")
            else:
                o = hit[0]
                if o["verdict"] != r["gemini_verdict"].strip().lower():
                    ed_problems.append(f"{p.name} line {n}: {sid} verdict {r['gemini_verdict']} vs {o['verdict']}")
                if r.get("current_turkish") and r["current_turkish"] != o["turkish"]:
                    ed_problems.append(f"{p.name} line {n}: {sid} current_turkish differs from the export")
                if r.get("gemini_suggestion") and r["gemini_suggestion"] != o["suggestion"]:
                    ed_problems.append(f"{p.name} line {n}: {sid} gemini_suggestion differs from the review")
                if r.get("english") and r["english"] != o["english"]:
                    ed_problems.append(f"{p.name} line {n}: {sid} english differs from the export")
            ed[sid].append(r)
    res = {}
    for n, r in lf.read_table(resolution):
        sid = r["id"].strip()
        if sid in res:
            raise Problem(f"{resolution.name} line {n}: {sid} twice")
        if r["action"] not in ACTIONS:
            raise Problem(f"{resolution.name} line {n}: action {r['action']!r} (one of {', '.join(ACTIONS)})")
        res[sid] = {"action": r["action"], "group": r.get("group", "").strip(), "reason": r.get("reason", "").strip()}
    need = {s for s, v in occ.items() if any(o["verdict"] != "ok" for o in v)} | set(ed)
    fatal = [f"{s}: no resolution" for s in sorted(need - set(res), key=loc.sid_key)]
    fatal += [f"{s}: a resolution for an id without a non-ok review or an editorial row"
              for s in sorted(set(res) - need, key=loc.sid_key)]
    review_rows, integ, table = [], [], []
    for sid in sorted(occ, key=loc.sid_key):
        v = occ[sid]
        d = decisive(v)
        e, c = ws.src["strings"][sid], ws.cat[sid]
        if any(o["turkish"] != e["text"] for o in v):
            fatal.append(f"{sid}: a review of another Turkish text than the project's")
        r = res.get(sid)
        sugs = sorted({o["suggestion"] for o in v if o["verdict"] == "change" and o["suggestion"] != o["turkish"]})
        if r and r["action"] == "integrate":
            if d["verdict"] != "change" or not d["suggestion"].strip() or d["suggestion"] == e["text"]:
                fatal.append(f"{sid}: integrate without a decisive change suggestion")
            else:
                integ.append({"id": sid, "check": lf.check_of(c["source_sha256"]), "from_text": e["text"],
                              "text": d["suggestion"], "reason": r["reason"][:200]})
        review_rows.append({"id": sid, "check": lf.check_of(c["source_sha256"]), "turkish": e["text"],
                            "round": str(d["round"]), "verdict": d["verdict"], "suggestion": d["suggestion"],
                            "review_note": consolidated_note(v, ed.get(sid, []), r)})
        table.append({"id": sid, "rounds": [f"r{o['round']:03d}:{o['verdict']}" for o in sorted(v, key=lambda o: o["round"])],
                      "decisive_round": d["round"], "decisive_verdict": d["verdict"],
                      "distinct_suggestions": len(sugs),
                      "editorial": [f"r{int(x['round']):03d}:{x['editor_disposition']}" for x in ed.get(sid, [])],
                      "action": r["action"] if r else "keep", "group": r["group"] if r else "",
                      "resolved": bool(r), "reason": r["reason"] if r else "all reviews ok"})
    out.mkdir(parents=True, exist_ok=True)
    review_cols = ["id", "check", "turkish", "round", "verdict", "suggestion", "review_note"]
    lf.write_table(out / "consolidated_review.tsv", review_cols, review_rows)
    lf.write_table(out / "integrate.tsv", ["id", "check", "from_text", "text", "reason"], integ)
    rep = {"unique_ids": len(occ), "occurrences": sum(map(len, occ.values())),
           "decisive_verdicts": dict(Counter(x["decisive_verdict"] for x in table)),
           "actions": dict(Counter(x["action"] for x in table)),
           "resolved": len(res), "integrate": len(integ),
           "multi_suggestion_ids": [x["id"] for x in table if x["distinct_suggestions"] > 1],
           "editorial_rows": sum(map(len, ed.values())), "editorial_problems": ed_problems,
           "groups": dict(Counter(x["group"] for x in table if x["group"])), "fatal": fatal,
           "files": {n: sha((out / n).read_bytes()) for n in ("consolidated_review.tsv", "integrate.tsv")},
           "result": "PASS" if not fatal and not ed_problems else "FAIL"}   # editorial mismatches fail closed too
    lf.atomic_write(out / "reconciliation.json", (json.dumps({"summary": rep, "ids": table}, indent=1,
                                                             ensure_ascii=False) + "\n").encode("utf-8"))
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["audit", "merge", "apply", "verify", "selftest"])
    ap.add_argument("--isolated", action="store_true", help="apply: on a temporary copy, twice (rerun check)")
    ap.add_argument("--reviewer", default="gemini")
    ap.add_argument("--proposer", default="editorial")
    ap.add_argument("--integrator", default="claude-opus-5.5.m47")
    ap.add_argument("workspace", nargs="?")
    ap.add_argument("--returned", help="folder of returned review tables (default WS/private/review/_gemini-output)")
    ap.add_argument("--out", help="output folder under private/ (default WS/private/m47)")
    ap.add_argument("--expect", default="", help="rNNN=batches:rows,... the counts the returns must have")
    ap.add_argument("--resolution")
    ap.add_argument("--game-dir")
    a = ap.parse_args()
    if a.command == "selftest":
        return selftest()
    if not a.workspace:
        ap.error("WS is required")
    ws = Path(a.workspace)
    out = Path(a.out) if a.out else ws / "private" / "m47"
    try:
        if a.command == "audit":
            returned = Path(a.returned) if a.returned else ws / "private" / "review" / "_gemini-output"
            rep = cmd_audit(ws, returned, out / "audit", a.expect, a.game_dir)
            for f in rep["files"]:
                print(f"{f['file']}: rows {f.get('rows')}/{f.get('export_rows')} verdicts {f.get('verdicts')} "
                      f"repaired {f.get('repaired') or '-'} fatal {len(f['fatal'])} warnings {len(f.get('warnings', []))}"
                      f" suggestion-errors {len(f.get('suggestion_errors', []))}")
            print(json.dumps({k: rep[k] for k in ("rounds", "cross_round", "missing_returns", "unexpected_returns",
                                                  "expect", "isolated_copy_untouched") if k in rep}, default=str))
            print(f"M47_REVIEW_AUDIT {rep['result']} fatal={rep['fatal']} files={len(rep['files'])}")
            return 0 if rep["result"] == "PASS" else 1
        return merge_main(a, ws, out)
    except (Problem, tw.Problem, lf.Problem, loc.Problem, KeyError, ValueError) as x:
        print(f"error: {x}", file=sys.stderr)
        return 2


STEPS = (("review", "consolidated_review.tsv"), ("suggest", "proposals.tsv"), ("integrate", "integrate.tsv"))


def snapshot(src: dict) -> dict:
    return {k: json.dumps(v, sort_keys=True, ensure_ascii=False) for k, v in src["strings"].items()}


def apply_steps(ws_path: Path, merge: Path, reviewer: str, proposer: str, integrator: str, game_dir=None) -> dict:
    """The merge outputs through the project's own commands, in a fixed order; a file whose hash the ledger already
    holds for the same action is not applied again (a rerun changes nothing)."""
    ws = tw.WS(ws_path, game_dir)
    led = [json.loads(x) for x in (ws_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    # a step counts as applied only when its ledger line rejected nothing (a partly rejected file runs again)
    done = {(x.get("action"), x.get("sha256")) for x in led if not x.get("rejected")}
    rec = merge / "reconciliation.json"
    summary = json.loads(rec.read_text(encoding="utf-8"))["summary"] if rec.is_file() else {}
    if summary.get("result") != "PASS" or any(sha((merge / n).read_bytes()) != h
                                              for n, h in summary.get("files", {}).items()):
        raise Problem("apply needs a passing merge whose files are unchanged since (run merge again)")
    before = snapshot(ws.src)
    out = {"steps": []}
    for action, name in STEPS:
        p = merge / name
        if not p.is_file():
            out["steps"].append({"step": action, "file": name, "result": "absent"})
            continue
        h = sha(p.read_bytes())
        if (action, h) in done:
            out["steps"].append({"step": action, "file": name, "result": "already applied"})
            continue
        if action == "review":
            r = tw.cmd_review_in(ws, p, reviewer, False)
        elif action == "suggest":
            r = tw.cmd_suggest(ws, p, proposer, "proposal", False)
        else:
            r = tw.cmd_integrate(ws, p, integrator, False)
        out["steps"].append({"step": action, "file": name, "changed": r["changed_count"], "unchanged": r["unchanged"],
                             "rejected": r["rejected"], "skipped": len(r.get("skipped", []))})
        if r["rejected"]:
            out["result"] = "FAIL"
            return out
    after = snapshot(ws.src)
    out["changed_entries"] = sum(1 for k in after if after[k] != before.get(k))
    out["result"] = "PASS"
    return out


def verify(ws_path: Path, merge: Path, game_dir=None) -> dict:
    """Invariants after apply: approved entries untouched (none forged), every reviewed entry carries the reviewer's
    review, integrated texts are the stored suggestions with the replaced text kept, every other text unchanged."""
    ws = tw.WS(ws_path, game_dir)
    integ = {r["id"]: r for _, r in lf.read_table(merge / "integrate.tsv")}
    cons = {r["id"]: r for _, r in lf.read_table(merge / "consolidated_review.tsv")}
    fails = []
    for sid, e in ws.src["strings"].items():
        st = loc.status_of(e)
        if st == "approved" and (not e.get("applied") or str(e.get("origin", "")).startswith("integrated:")):
            fails.append(f"{sid}: approved without a person's decision record, or an integrated text approved")
        if sid in integ:
            g = integ[sid]
            if e["text"] != g["text"] or not str(e.get("origin", "")).startswith("integrated:") \
                    or not any(a["text"] == g["from_text"] for a in e.get("alt") or []) or st != "reviewed":
                fails.append(f"{sid}: integration not as planned")
        elif sid in cons and e["text"] != cons[sid]["turkish"]:
            fails.append(f"{sid}: a text changed that was not to be integrated")
        if sid in cons and (e.get("review") or {}).get("verdict") != cons[sid]["verdict"]:
            fails.append(f"{sid}: stored verdict differs from the consolidated one")
    c = Counter(loc.status_of(e) for e in ws.src["strings"].values())
    return {"statuses": dict(c), "integrated": sum(1 for e in ws.src["strings"].values()
                                                    if str(e.get("origin", "")).startswith("integrated:")),
            "fails": fails, "result": "PASS" if not fails else "FAIL"}


def merge_main(a, ws, out) -> int:
    if a.command in ("apply", "verify"):
        merge = out / "merge"
        if a.command == "verify":
            v = verify(ws, merge, a.game_dir)
            print(json.dumps(v, ensure_ascii=False))
            print(f"M47_INTEGRATION_VERIFY {v['result']}")
            return 0 if v["result"] == "PASS" else 1
        if a.isolated:
            with tempfile.TemporaryDirectory(prefix="m47_apply_", dir=private_out(out)) as td:
                iso = Path(td) / "ws"
                shutil.copytree(ws, iso, ignore=shutil.ignore_patterns("build", "private"))
                r1 = apply_steps(iso, merge, a.reviewer, a.proposer, a.integrator, a.game_dir)
                v1 = verify(iso, merge, a.game_dir)
                h1 = sha((iso / "tr.json").read_bytes())
                r2 = apply_steps(iso, merge, a.reviewer, a.proposer, a.integrator, a.game_dir)
                h2 = sha((iso / "tr.json").read_bytes())
                rep = {"first": r1, "verify": v1, "rerun": r2, "rerun_identical": h1 == h2, "tr_json_sha256": h1}
            ok = r1["result"] == v1["result"] == r2["result"] == "PASS" and h1 == h2 \
                and all(s["result"] == "already applied" for s in r2["steps"] if s["result"] != "absent")
        else:
            r1 = apply_steps(ws, merge, a.reviewer, a.proposer, a.integrator, a.game_dir)
            v1 = verify(ws, merge, a.game_dir)
            rep = {"applied": r1, "verify": v1, "tr_json_sha256": sha((ws / "tr.json").read_bytes())}
            ok = r1["result"] == v1["result"] == "PASS"
        print(json.dumps(rep, ensure_ascii=False, default=str))
        print(f"M47_INTEGRATION_APPLY {'PASS' if ok else 'FAIL'}{' (isolated copy)' if a.isolated else ''}")
        return 0 if ok else 1
    if not a.resolution:
        raise Problem("merge needs --resolution FILE (id, action, group, reason)")
    returned = Path(a.returned) if a.returned else ws / "private" / "review" / "_gemini-output"
    rep = cmd_merge(ws, out / "merge", Path(a.resolution), returned, a.game_dir)
    print(json.dumps({k: v for k, v in rep.items() if k != "files"}, ensure_ascii=False))
    print(f"M47_REVIEW_MERGE {rep['result']} ids={rep['unique_ids']} integrate={rep['integrate']} "
          f"fatal={len(rep['fatal'])} editorial_problems={len(rep['editorial_problems'])}")
    return 0 if rep["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
