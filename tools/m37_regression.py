#!/usr/bin/env python3
"""M37 regression (no game run): the translation production workflow.

  * selftests of r3hd_trwork.py (workspace), r3hd_locflow.py (workflow) and r3hd_loc.py (engine)
  * the context map: valid, covers every English table handle that has a string, no game text in it
  * the project template and prompts: present, the ignore file keeps private/ and build/ out, no game text
  * real data (skipped without it): the inventory numbers; every translatable id classified; an end-to-end run in a
    temporary workspace with the M34 sample's own Turkish (tracked, no game text): batch -> ingest (a broken row
    rejected) -> review -> decision sheet -> approve -> a release build of approved strings only; a NOT FINAL preview
    built twice to the same bytes and checked against the game data and port version; game files unchanged
  * build order: this regression after M36
Writes only into a temporary folder.

usage: m37_regression.py
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import r3hd_loc as loc  # noqa: E402
import r3hd_locflow as lf  # noqa: E402
import r3hd_mods as rm  # noqa: E402
import r3hd_trwork as tw  # noqa: E402

results = []


def check(ok, label):
    results.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'} {label}", flush=True)


def run(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def main() -> int:
    sys.stdout.reconfigure(errors="backslashreplace")
    for tool, marker in (("r3hd_trwork.py", "R3HD_TRWORK_SELFTEST PASS"), ("r3hd_locflow.py", "R3HD_LOCFLOW_SELFTEST PASS"),
                         ("r3hd_loc.py", "R3HD_LOC_SELFTEST PASS")):
        r = run(str(TOOLS / tool), "selftest")
        check(r.returncode == 0 and marker in r.stdout,
              f"{tool} selftest ({r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]})")
    groups = tw.load_groups()
    check(all(g["category"] in tw.CATEGORIES for g in groups) and groups[0]["from"] == 1 and groups[-1]["to"] == 1187,
          "context map: valid categories, handles 1 .. 1187")
    tmpl = tw.TEMPLATE
    files = ["README.md", "STYLE.md", "glossary.json", "gitignore.txt"]
    check(all((tmpl / f).is_file() for f in files), "template: README, STYLE, glossary, ignore file")
    ign = (tmpl / "gitignore.txt").read_text(encoding="utf-8")
    check("/private/" in ign and "/build/" in ign, "template: the ignore file keeps private/ and build/ out")
    g = lf.load_glossary(tmpl / "glossary.json")
    check(g and all(t.get("status") in ("proposed", "approved") for t in g) and all(t["tr"] == [t["en"]] for t in g),
          "template glossary: loads; names only, every term with a status")
    bat = (TOOLS / "build_milestone8.bat").read_text(encoding="utf-8", errors="replace")
    pos = [bat.find(s) for s in ("python tools\\m36_regression.py", "python tools\\m37_regression.py", "M8_BUILD_OK")]
    check(all(x > 0 for x in pos) and pos == sorted(pos), f"build: M37 regression after M36 {pos}")
    for p in ("draft.md", "review.md"):
        body = (ROOT / "config" / "localization" / "prompts" / p).read_text(encoding="utf-8")
        check("placeholders" in body.lower() or "%d" in body, f"prompt {p}: mentions placeholders")
    game = ROOT / "private" / "extracted" / rm.TITLE_ID
    if not (game / "GAMEDATAbin" / "VS.sub").is_file():
        print("SKIP real-data checks: no game data", flush=True)
        return finish()
    watched = [game / "GAMEDATAbin" / n for n in ("fix.lvl", "fix.ptr", "VS.sub")]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    paths = loc.game_paths(argparse.Namespace(cache=None, game_dir=None))
    rows = loc.catalog_rows(paths, "en")
    cat = lf.catalog_index(rows)
    trans = {s: c for s, c in cat.items() if c["text"].strip()}
    check(sum(1 for r in rows if r["kind"] == "text") == 1188 and sum(1 for r in rows if "source_sha256" not in r) == 19
          and len(trans) == 1237 and sum(1 for c in trans.values() if c["kind"] == "subtitle") == 69
          and sum(1 for c in trans.values() if c.get("category") == "voiced line") == 520,
          "inventory: 1,188 handles (19 without a string), 1,237 translatable, 69 subtitles, 520 voiced")
    ctx = {s: tw.classify(c, groups, tw.duplicates(cat)) for s, c in trans.items()}
    check(not [s for s, x in ctx.items() if x["group"] == "unknown"], "context map: every translatable id has a category")
    texts = {c["text"] for c in trans.values() if len(c["text"]) >= 16 and " " in c["text"].strip()}
    body = "".join((tmpl / f).read_text(encoding="utf-8") for f in files) + tw.GROUPS.read_text(encoding="utf-8") + \
        "".join((ROOT / "config" / "localization" / "prompts" / p).read_text(encoding="utf-8")
                for p in ("draft.md", "review.md"))
    leaks = [s[:20] for s in texts if s in body]
    check(not leaks, f"template, context map and prompts: no English game phrase of 16+ characters {leaks[:3]}")
    sample_file = ROOT / "config" / "localization" / "tr" / "tr.json"
    if not sample_file.is_file():
        # The game-derived sample is left out of the public source export (config/release/public_export.json).
        print("SKIP sample checks: config/localization/tr/tr.json is absent", flush=True)
        return finish()
    sample = json.loads(sample_file.read_text(encoding="utf-8"))["strings"]
    with tempfile.TemporaryDirectory() as td:
        w = Path(td) / "private" / "rayman3hd-turkish"   # a temporary folder outside any repository
        tw.cmd_new(w, "tr.regress", "Türkçe (regression)")
        ws = tw.WS(w)
        inv = tw.cmd_inventory(ws)
        check(inv["translatable"] == 1237 and (w / "private" / "inventory" / "inventory.csv").is_file(),
              "end to end: inventory in the workspace's private/")
        b = tw.cmd_batch(ws, None, None, ",".join(sample), "", 5, ".jsonl")
        man = json.loads((w / "private" / "batches" / "r001" / "manifest.json").read_text(encoding="utf-8"))
        check(b["rows"] == len(sample) and len(man["batches"]) == 3, f"end to end: a draft round of the sample ids {b}")
        ans = []
        for name, info in man["batches"].items():
            for _, r in lf.read_table(w / "private" / "batches" / "r001" / info["file"]):
                r["turkish"] = sample[r["id"]]["text"]
                ans.append((name, r))
        broken = next(r for _, r in ans if r["id"] == "en.276")
        broken["turkish"] = broken["turkish"].replace("\\jc", "")
        lost = {"rejected": []}
        for name in man["batches"]:
            f = Path(td) / f"{name}.jsonl"
            f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for n, r in ans if n == name), encoding="utf-8")
            rep = tw.cmd_ingest(ws, f, f"r001/{name}", "regress-model", False)
            if "en.276" in rep["retry"]:
                lost = rep
        check(lost["rejected"] and lost["rejected"][0]["id"] == "en.276" and "codes" in lost["rejected"][0]["reason"]
              and len(ws.src["strings"]) == len(sample) - 1, "end to end: a draft that lost its \\jc is rejected, the rest taken")
        pre = tw.cmd_build(ws, True, False, "", None, True)
        first = Path(pre["zip"]).read_bytes()
        pre2 = tw.cmd_build(ws, True, False, "", None, True)
        m = json.loads(Path(pre["mod"], "mod.json").read_text(encoding="utf-8"))
        check(pre2["zip_sha256"] == hashlib.sha256(first).hexdigest() and m["id"] == "tr.regress.dev"
              and m["description"].startswith("NOT FINAL") and "DEV" in m["name"] and pre["compatible"]
              and pre["validated"]["ranges"] >= len(sample) - 1,
              "end to end: preview NOT FINAL, reproducible, valid against the game data and port version")
        pre3 = tw.cmd_build(ws, True, False, "en.,en.192", None, False)
        check(pre3["strings"] == len(ws.src["strings"]) and pre3["mod"].endswith("-sample"),
              "end to end: a sample preview takes ids and prefixes ending in '.' and has its own name")
        try:
            tw.cmd_build(ws, False, True, "", None, False)
            check(False, "end to end: a release with nothing approved is refused")
        except loc.Problem:
            check(True, "end to end: a release with nothing approved is refused")
        rv = tw.cmd_review(ws, "", None, 60, ".jsonl")
        rrows = [x for _, x in lf.read_table(Path(rv["files"][0]))]
        for x in rrows:
            x["verdict"] = "ok"
        rrows[0].update(verdict="change", suggestion=rrows[0]["turkish"] + "!", review_note="regression")
        f = Path(td) / "review.jsonl"
        f.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rrows), encoding="utf-8")
        tw.cmd_review_in(ws, f, "regress-reviewer", False)
        check(all(lf.loc.status_of(e) == "reviewed" for e in ws.src["strings"].values()),
              "end to end: a review never approves")
        sh = tw.cmd_sheet(ws, "", None, ".csv")
        srows = [x for _, x in lf.read_table(Path(sh["file"]))]
        for x in srows:
            x["decision"] = "approve" if x["id"] != rrows[0]["id"] else "reject"
        srows[1]["decision"] = ""
        lf.write_table(Path(td) / "decide.csv", tw.HUMAN_COLS, srows)
        d = tw.cmd_decide(ws, Path(td) / "decide.csv", False)
        st = {s: lf.loc.status_of(e) for s, e in ws.src["strings"].items()}
        check(not d["rejected"] and list(st.values()).count("approved") == len(srows) - 2,
              f"end to end: decisions applied ({list(st.values()).count('approved')} approved)")
        rel = tw.cmd_build(ws, False, True, "", None, True)
        mr = json.loads(Path(rel["mod"], "mod.json").read_text(encoding="utf-8"))
        texts_in = {o.get("offset") for o in mr["overrides"] if o["type"] == "text"}
        check(rel["strings"] == len(srows) - 2 and rel["not_approved_left_out"] == 2 and mr["id"] == "tr.regress"
              and "NOT FINAL" not in mr.get("description", "") and len(texts_in) == len(srows) - 2,
              "end to end: the release build has the approved strings only")
        dash = tw.cmd_dashboard(ws, None, with_build=False)
        check(not dash["complete"] and dash["total"]["approved"] == len(srows) - 2 and "NOT complete" in dash["verdict"],
              "end to end: the dashboard counts approvals and says the localization is not complete")
        led = (w / "ledger.jsonl").read_text(encoding="utf-8")
        check(all(c["text"] not in led for c in trans.values() if len(c["text"]) >= 12),
              "end to end: the ledger holds no English")
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    check(after == before, "game data unchanged (fix.lvl, fix.ptr, VS.sub)")
    return finish()


def finish() -> int:
    n = results.count(False)
    print(f"M37_REGRESSION {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
