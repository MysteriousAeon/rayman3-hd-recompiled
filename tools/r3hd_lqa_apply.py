#!/usr/bin/env python3
"""Final LQA integration (D-106): the person's 'Proposed Turkish' cells, applied verbatim through the workspace's own
decision path (r3hd_trwork.py decide), with every proposal classified first.

    r3hd_lqa_apply.py plan EXPORT.jsonl OUT_DIR --workspace WS [--game-dir DIR]
    r3hd_lqa_apply.py verify EXPORT.jsonl OUT_DIR --workspace WS --before TR_JSON [--game-dir DIR]
    r3hd_lqa_apply.py package PLAN_DIR NEW_DIR --workspace WS --before TR_JSON [--version 1.0.1]
                      [--achievements FILE.json]

EXPORT.jsonl is `r3hd_lqa.py export BOOK --all` of the person's workbook. `plan` writes, under private/ only:
  classes.json    per id: HARD_BLOCKER (a proven loader / font / packer refusal), LAYOUT_RISK (wider or more lines
                  than the Turkish the person already saw in play, and over the M34 width margin against the English),
                  or NO_ISSUE; drawn widths (px, FontRay records) of the English, the current and the proposed text
  decisions.csv   a decide sheet: approve with 'final' = the proposal byte for byte, for every id that is not a
                  HARD_BLOCKER (layout risks keep the person's wording)
  manifest.json   deterministic: book / catalog / mod hashes, per id the English slot hash, SHA-256 of the current
                  and of the proposed text, the class (no text)
`verify` (after decide) proves: each planned id's text equals the proposal byte for byte and is approved by a
person; each held id and every other entry is exactly as in TR_JSON (the copy taken before decide).

A proposal is never edited, shortened or reordered here; a blocked one stays the current text until the person
decides. Lengths against the English are never a blocker: only the build (room), the encoder (font) and the subtitle
limits are. This file holds ids, hashes and counts only.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_loc as loc          # noqa: E402
import r3hd_locflow as lf       # noqa: E402
import r3hd_mods as rm          # noqa: E402
import r3hd_trwork as tw        # noqa: E402

KIND = "r3hd-lqa-application"


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def read_export(path: Path):
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    head, rows = lines[0], lines[1:]
    if head.get("kind") != "r3hd-lqa-submission":
        raise SystemExit(f"{path}: not an r3hd_lqa export")
    return head, [r for r in rows if r.get("proposed")]


def font_tables(ws):
    fix = (ws.paths["game"] / "GAMEDATAbin" / "fix.lvl").read_bytes()
    font = rm.read_font(fix)
    recs = list(font["ray"])
    for o in loc.glyph_overrides(ws.src, ws.proj.parent):
        recs[rm.GLYPH_CODES[o["char"]]] = (0, 0, o["height"], o["width"], 1, o["descent"], 0, 1)
    return font, recs


def widths(text: str, glyphs, font, recs):
    """Drawn width of each line, or None when the encoder refuses the text."""
    try:
        enc = rm.encode_text(text, glyphs, font["defined"])
    except rm.Refusal:
        return None
    return loc.text_width(enc, recs)


def english_widths(text: str, font):
    return loc.text_width(text.encode("cp1252", "replace"), font["ray"])


def whole_check(ws, texts: dict):
    """The preview build's own check of the whole project with `texts` in place (room, moves, subtitles)."""
    src = dict(ws.src, strings={s: (dict(e, text=texts[s]) if s in texts else e) for s, e in ws.src["strings"].items()})
    return loc.cmd_check(ws.paths, ws.proj, None, loc.dev_variant(src))


def classify(ws, rows):
    font, recs = font_tables(ws)
    glyphs = rm.glyph_chars({"overrides": loc.glyph_overrides(ws.src, ws.proj.parent)})
    seen, out = {}, {}
    for r in rows:
        seen[r["id"]] = seen.get(r["id"], 0) + 1
    for r in rows:
        sid, prop = r["id"], r["proposed"]
        c, e = ws.cat.get(sid), ws.src["strings"].get(sid)
        hard, risk, notes = [], [], []
        if seen[sid] > 1:
            hard.append("id appears more than once in the workbook")
        if c is None or e is None:
            hard.append("unknown id or no current entry")
            out[sid] = {"class": "HARD_BLOCKER", "hard": hard, "risk": [], "notes": []}
            continue
        if r.get("stale") or r["english"] != c["text"] or r["current"] != e["text"] \
                or e["source_sha256"] != c["source_sha256"]:
            hard.append("reference columns differ from the catalog / workspace (stale row)")
        er, wa = lf.text_problems(sid, c["text"], prop, ws.glyphs, c)
        hard += er
        notes += wa
        wn, wc, we = widths(prop, glyphs, font, recs), widths(e["text"], glyphs, font, recs), english_widths(c["text"], font)
        if wn is not None and wc is not None:
            if max(wn) > max(wc) and max(wn) > loc.LAYOUT_WARN * max(we) and max(wn) > 40:
                risk.append(f"widest line {max(wn)} px: current Turkish {max(wc)} px, English {max(we)} px")
            if len(wn) != len(wc):
                risk.append(f"{len(wn)} lines against {len(wc)} in the current Turkish")
        if c.get("kind") == "subtitle" and lf.breaks(prop) + 1 > lf.SUB_LINES_SEEN:
            risk.append(f"subtitle of {lf.breaks(prop) + 1} lines (seen: one or two)")
        out[sid] = {"class": "HARD_BLOCKER" if hard else "LAYOUT_RISK" if risk else "NO_ISSUE", "hard": hard,
                    "risk": risk, "notes": notes, "px": {"english": we, "current": wc, "proposed": wn}}
    # Room in the game's files: the whole project with every non-blocked proposal in place, as the build sees it.
    ok = {s: r["proposed"] for s, r in ((r["id"], r) for r in rows) if out[s]["class"] != "HARD_BLOCKER"}
    base, full = whole_check(ws, {}), whole_check(ws, ok)
    for err in full["errors"]:
        sid = err.split(":")[0]
        if sid in out:
            out[sid]["hard"].append(f"build: {err}")
            out[sid]["class"] = "HARD_BLOCKER"
    summary = {"baseline_errors": base["errors"], "errors": full["errors"], "moved": full.get("moved"),
               "baseline_moved": base.get("moved"), "subtitle_growth": full.get("subtitle_growth"),
               "baseline_subtitle_growth": base.get("subtitle_growth"),
               "unattributed_errors": [x for x in full["errors"] if x.split(":")[0] not in out]}
    return out, summary


def cmd_plan(a):
    out_dir = Path(a.out_dir)
    lf.private_path(out_dir / "x")
    ws = tw.WS(Path(a.workspace), a.game_dir)
    head, rows = read_export(Path(a.export))
    classes, summary = classify(ws, rows)
    if summary["unattributed_errors"]:
        raise SystemExit(f"LQA_APPLY REFUSED: build errors not tied to a proposal: {summary['unattributed_errors']}")
    out_dir.mkdir(parents=True, exist_ok=True)
    order = sorted(classes, key=loc.sid_key)
    cols = ["id", "check", "turkish", "final", "decision", "text_check", "human_note"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    prop = {r["id"]: r["proposed"] for r in rows}
    for sid in order:
        if classes[sid]["class"] == "HARD_BLOCKER":
            continue
        e = ws.src["strings"][sid]
        w.writerow({"id": sid, "check": lf.check_of(ws.cat[sid]["source_sha256"]), "turkish": e["text"],
                    "final": prop[sid], "decision": "approve", "text_check": lf.text_check(e),
                    "human_note": f"LQA workbook {head['book_sha256'][:12]}"})
    (out_dir / "decisions.csv").write_bytes(buf.getvalue().encode("utf-8"))
    counts = {k: sum(1 for v in classes.values() if v["class"] == k) for k in ("NO_ISSUE", "LAYOUT_RISK", "HARD_BLOCKER")}
    manifest = {"kind": KIND, "format": 1, "book_sha256": head["book_sha256"],
                "catalog_fingerprint": head["catalog_fingerprint"], "mod_json_sha256": head["mod_json_sha256"],
                "workspace_tr_json_sha256": hashlib.sha256(ws.proj.read_bytes()).hexdigest(),
                "proposals": len(rows), "counts": counts,
                "entries": [{"id": s, "class": classes[s]["class"], "apply": classes[s]["class"] != "HARD_BLOCKER",
                             "source_sha256": ws.cat[s]["source_sha256"] if s in ws.cat else "",
                             "current_sha256": sha(ws.src["strings"][s]["text"]) if s in ws.src["strings"] else "",
                             "proposed_sha256": sha(prop[s])} for s in order],
                "build": {k: summary[k] for k in ("moved", "baseline_moved", "subtitle_growth",
                                                  "baseline_subtitle_growth", "errors", "baseline_errors")}}
    (out_dir / "manifest.json").write_bytes((json.dumps(manifest, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    (out_dir / "classes.json").write_bytes((json.dumps({s: classes[s] for s in order}, indent=1,
                                                       ensure_ascii=False) + "\n").encode("utf-8"))
    print(json.dumps({"proposals": len(rows), **counts, "moved": summary["moved"],
                      "baseline_moved": summary["baseline_moved"], "subtitle_growth": summary["subtitle_growth"],
                      "manifest_sha256": hashlib.sha256((out_dir / "manifest.json").read_bytes()).hexdigest()}))
    return 0


def cmd_verify(a):
    ws = tw.WS(Path(a.workspace), a.game_dir)
    head, rows = read_export(Path(a.export))
    m = json.loads((Path(a.out_dir) / "manifest.json").read_text(encoding="utf-8"))
    before = json.loads(Path(a.before).read_text(encoding="utf-8"))["strings"]
    prop = {r["id"]: r["proposed"] for r in rows}
    bad = []
    if m["book_sha256"] != head["book_sha256"]:
        bad.append("the export is of another workbook than the plan")
    planned = {x["id"] for x in m["entries"] if x["apply"]}
    for x in m["entries"]:
        e = ws.src["strings"][x["id"]]
        if x["apply"]:
            if e["text"] != prop[x["id"]] or sha(e["text"]) != x["proposed_sha256"]:
                bad.append(f"{x['id']}: text is not the proposal byte for byte")
            if e.get("status") != "approved" or e.get("origin") != "human":
                bad.append(f"{x['id']}: not approved by a person ({e.get('status')}, {e.get('origin')})")
        elif e != before[x["id"]]:
            bad.append(f"{x['id']}: held, but changed")
    others = [s for s in set(ws.src["strings"]) | set(before) if s not in planned]
    changed = [s for s in others if ws.src["strings"].get(s) != before.get(s)]
    if changed:
        bad.append(f"entries outside the plan changed: {sorted(changed, key=loc.sid_key)[:10]}")
    print(json.dumps({"ok": not bad, "applied": len(planned), "held": len(m["entries"]) - len(planned),
                      "untouched": len(others), "problems": bad}, ensure_ascii=False))
    return 0 if not bad else 1


def build_manifest(ws, src: dict, folder: Path, omit_glyphs=()) -> dict:
    """The workspace's preview build (every status, id tr.full.dev) of `src` into `folder`; returns mod.json.
    `omit_glyphs`: glyph characters left out of the workspace's glyphs file for this build (a snapshot made before
    they were added)."""
    fd, tmp = tempfile.mkstemp(dir=ws.proj.parent, prefix=".lqa_build_", suffix=".json")
    os.close(fd)
    tmp = Path(tmp)
    gtmp = None
    try:
        if omit_glyphs:
            fd, gtmp = tempfile.mkstemp(dir=ws.proj.parent, prefix=".lqa_glyphs_", suffix=".json")
            os.close(fd)
            gtmp = Path(gtmp)
            doc = json.loads((ws.proj.parent / src["glyphs"]).read_text(encoding="utf-8"))
            doc["glyphs"] = [g for g in doc["glyphs"] if g["char"] not in omit_glyphs]
            gtmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            src = dict(src, glyphs=gtmp.name)
        lf.write_project(tmp, src)
        loc.cmd_build(ws.paths, tmp, folder, False, allow_unapproved=True)
    finally:
        tmp.unlink(missing_ok=True)
        Path(str(tmp) + ".bak").unlink(missing_ok=True)
        if gtmp:
            gtmp.unlink(missing_ok=True)
    return json.loads((folder / "mod.json").read_text(encoding="utf-8"))


def cmd_package(a):
    """A new private Turkish mod: the workspace's preview build (as M47 made 0.2.0-dev), the release-copy fields of
    m49_turkish_package (name, description; version a.version) and the optional achievements file. Before that, the
    TR_JSON snapshot is rebuilt and must reproduce the pinned 0.2.0-dev manifest byte for byte, so the only change
    in the new mod is the applied text and the glyphs named by --new-glyph (added to the workspace's glyphs file
    after the snapshot, e.g. the ellipsis): those are left out of the snapshot's build and must be the only other
    overrides the new mod adds."""
    import m49_turkish_package as m49
    out = Path(a.out_dir)
    lf.private_path(out / "x")
    if out.exists():
        raise SystemExit(f"LQA_APPLY REFUSED: {out} exists (candidates are never replaced)")
    ws = tw.WS(Path(a.workspace), a.game_dir)
    m = json.loads((Path(a.export_or_plan) / "manifest.json").read_text(encoding="utf-8"))
    before = lf.load_project(Path(a.before))
    with zipfile.ZipFile(m49.SOURCE) as z:
        pinned = z.read("mod.json")
    out.mkdir(parents=True)
    work = out / "work"
    added = set(a.new_glyph or ())
    if added - set(rm.GLYPH_CODES):
        raise SystemExit(f"LQA_APPLY REFUSED: --new-glyph takes one of {''.join(rm.GLYPH_CODES)}")
    old = build_manifest(ws, before, work / "before", added)
    same = (work / "before" / "mod.json").read_bytes() == pinned
    if not same:
        raise SystemExit("LQA_APPLY REFUSED: the snapshot does not rebuild the pinned 0.2.0-dev manifest")
    new = build_manifest(ws, dict(ws.src, version=a.version), work / "after")
    applied = {x["id"] for x in m["entries"] if x["apply"]}
    def key(o):
        return str(o.get("id") or o.get("offset") or o.get("char"))
    ov_old = {key(o): o for o in old["overrides"]}
    ov_new = {key(o): o for o in new["overrides"]}
    if set(ov_new) - set(ov_old) != added or any(ov_new[k]["type"] != "glyph" for k in added):
        raise SystemExit(f"LQA_APPLY REFUSED: the new manifest adds {sorted(set(ov_new) - set(ov_old))}, "
                         f"--new-glyph names {sorted(added)}")
    ov_new = {k: v for k, v in ov_new.items() if k not in added}
    diff = sorted(k for k in set(ov_old) | set(ov_new) if ov_old.get(k) != ov_new.get(k))
    if len(diff) != len(applied) or set(ov_old) != set(ov_new) \
            or any(set(ov_old[k]) != set(ov_new[k]) or {f for f in ov_old[k] if ov_old[k][f] != ov_new[k][f]} != {"text"}
                   for k in ov_old if ov_old[k] != ov_new[k]):
        raise SystemExit(f"LQA_APPLY REFUSED: the new manifest differs in more than the applied texts ({len(diff)})")
    text = (work / "after" / "mod.json").read_text(encoding="utf-8")
    for key, value in dict(m49.CHANGES, version=a.version).items():
        line = f'\n  "{key}": {json.dumps(new[key], ensure_ascii=False)},\n'
        if text.count(line) != 1:
            raise SystemExit(f"LQA_APPLY REFUSED: the {key} line is not found exactly once")
        text = text.replace(line, f'\n  "{key}": {json.dumps(value, ensure_ascii=False)},\n')
    final = json.loads(text)
    if any(final[k] != new[k] for k in new if k not in m49.CHANGES) or final["id"] != "tr.full.dev":
        raise SystemExit("LQA_APPLY REFUSED: a field other than name / description / version changed")
    files = [("mod.json", text.encode("utf-8"))]
    if a.achievements:
        files.append(("achievements/achievements.json", Path(a.achievements).read_bytes()))
    pkg = out / f"rayman3hd-turkish-{a.version}.zip"
    with zipfile.ZipFile(pkg, "w") as z:
        for name, data in files:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    v = rm.cmd_validate(ws.paths, pkg)
    rm.check_compat(rm.parse_manifest(rm.read_package(pkg)), ws.paths)
    shutil.rmtree(work)
    counts = {}
    for o in final["overrides"]:
        counts[o["type"]] = counts.get(o["type"], 0) + 1
    rec = {"kind": "r3hd-lqa-mod-candidate", "id": final["id"], "name": final["name"], "version": final["version"],
           "file": pkg.name, "bytes": pkg.stat().st_size, "sha256": hashlib.sha256(pkg.read_bytes()).hexdigest(),
           "manifest_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "overrides": counts,
           "entries": [n for n, _ in files], "applied_texts": len(diff), "added_glyphs": sorted(added),
           "plan_manifest_sha256":
           hashlib.sha256((Path(a.export_or_plan) / "manifest.json").read_bytes()).hexdigest(),
           "achievements_sha256": hashlib.sha256(files[1][1]).hexdigest() if a.achievements else None,
           "snapshot_rebuilds_pinned_0_2_0": same, "validated_ranges": v.get("ranges")}
    (out / "CANDIDATE.json").write_bytes((json.dumps(rec, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    (out / "SHA256SUMS.txt").write_bytes(f"{rec['sha256']}  {pkg.name}\n".encode("ascii"))
    print(json.dumps(rec, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("plan", "verify", "package"))
    ap.add_argument("export_or_plan", metavar="EXPORT|PLAN_DIR")
    ap.add_argument("out_dir")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--before")
    ap.add_argument("--version", default="1.0.1")
    ap.add_argument("--achievements")
    ap.add_argument("--new-glyph", action="append", help="package: a glyph added after the TR_JSON snapshot")
    ap.add_argument("--game-dir")
    a = ap.parse_args()
    a.export = a.export_or_plan
    if a.cmd in ("verify", "package") and not a.before:
        ap.error(f"{a.cmd} needs --before TR_JSON")
    return {"plan": cmd_plan, "verify": cmd_verify, "package": cmd_package}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
