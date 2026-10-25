#!/usr/bin/env python3
"""M39 regression (no game run): capacity reports and draft alternatives.

  * selftests of r3hd_capacity.py (synthetic tables: fit, fragmentation, total capacity, pinned slots, encoding,
    shared-language pointers, projections), r3hd_trwork.py, r3hd_locflow.py and r3hd_loc.py
  * the review prompt explains the alternative columns; build order: this regression after M38
  * real data (skipped without it), in a temporary workspace with the M34 sample's own Turkish (tracked, no game
    text):
      - a capacity report: both packers measured, the English table's allocation, deterministic (the same JSON
        twice), ids and numbers only (no English phrase, no Turkish text of the strings in the report);
      - alternatives: stored beside the text (text, status and revision counter unchanged), the same file twice adds
        nothing, a broken alternative is refused, the report with --use-alt measures them, the review round and the
        decision sheet show them; a later draft keeps the replaced one as an alternative;
      - a projection (MODEL): runs, gives a break-even factor, writes nothing into the workspace;
      - game files unchanged
Writes only into a temporary folder.

usage: m39_regression.py
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
import r3hd_capacity as cap  # noqa: E402
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


def finish() -> int:
    n = results.count(False)
    print(f"M39_REGRESSION {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}")
    return 1 if n else 0


def main() -> int:
    sys.stdout.reconfigure(errors="backslashreplace")
    for tool, marker in (("r3hd_capacity.py", "R3HD_CAPACITY_SELFTEST PASS"),
                         ("r3hd_trwork.py", "R3HD_TRWORK_SELFTEST PASS"),
                         ("r3hd_locflow.py", "R3HD_LOCFLOW_SELFTEST PASS"), ("r3hd_loc.py", "R3HD_LOC_SELFTEST PASS")):
        r = run(str(TOOLS / tool), "selftest")
        check(r.returncode == 0 and marker in r.stdout,
              f"{tool} selftest ({r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]})")
    body = (ROOT / "config" / "localization" / "prompts" / "review.md").read_text(encoding="utf-8")
    check("alternative" in body and "alt_reason" in body, "review prompt: explains the alternative columns")
    bat = (TOOLS / "build_milestone8.bat").read_text(encoding="utf-8", errors="replace")
    pos = [bat.find(s) for s in ("python tools\\m38_regression.py", "python tools\\m39_regression.py", "M8_BUILD_OK")]
    check(all(x > 0 for x in pos) and pos == sorted(pos), f"build: M39 regression after M38 {pos}")
    game = ROOT / "private" / "extracted" / rm.TITLE_ID
    if not (game / "GAMEDATAbin" / "VS.sub").is_file():
        print("SKIP real-data checks: no game data", flush=True)
        return finish()
    watched = [game / "GAMEDATAbin" / n for n in ("fix.lvl", "fix.ptr", "VS.sub")]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    paths = loc.game_paths(argparse.Namespace(cache=None, game_dir=None))
    sample_file = ROOT / "config" / "localization" / "tr" / "tr.json"
    if not sample_file.is_file():
        # The game-derived sample is left out of the public source export (config/release/public_export.json).
        print("SKIP sample checks: config/localization/tr/tr.json is absent", flush=True)
        return finish()
    sample = json.loads(sample_file.read_text(encoding="utf-8"))["strings"]
    with tempfile.TemporaryDirectory() as td:
        w = Path(td) / "private" / "rayman3hd-turkish"
        tw.cmd_new(w, "tr.regress", "Türkçe (regression)")
        ws = tw.WS(w)
        tw.cmd_inventory(ws)
        tw.cmd_batch(ws, None, None, ",".join(sample), "", 40, ".jsonl")
        man = json.loads((w / "private" / "batches" / "r001" / "manifest.json").read_text(encoding="utf-8"))
        rows = [r for _, r in lf.read_table(w / "private" / "batches" / "r001" / man["batches"]["batch_001"]["file"])]
        f = Path(td) / "ans.jsonl"
        f.write_text("".join(json.dumps(dict(r, turkish=sample[r["id"]]["text"]), ensure_ascii=False) + "\n"
                             for r in rows), encoding="utf-8")
        tw.cmd_ingest(ws, f, "r001/batch_001", "regress-model", False)
        src = lf.load_project(w / "tr.json")
        r1 = cap.measure(paths, src, w, None)
        r2 = cap.measure(paths, lf.load_project(w / "tr.json"), w, None)
        t = r1["main_table"]
        check(cap.dump(r1) == cap.dump(r2), "capacity: the same report twice (deterministic)")
        check(set(t["packers"]) == {"m34", "compact"} and t["auto"].get("ok") and t["strings"] == sum(
              1 for s in src["strings"] if not loc.is_sub(s)) and r1["baseline"]["strings"] == 1169
              and r1["baseline"]["handles"] == 1188 and "rebuilt_bytes" in r1["subtitles"],
              f"capacity: both packers, the English table's allocation, the subtitles ({t['verdict']})")
        cat = lf.catalog_index(loc.catalog_rows(paths, "en"))
        phrases = {c["text"] for c in cat.values() if len(c["text"]) >= 16 and " " in c["text"]}
        txt = cap.dump(r1) + cap.markdown(r1)
        leaks = [p[:20] for p in phrases if p in txt] + [e["text"][:20] for e in src["strings"].values()
                                                           if len(e["text"]) >= 8 and e["text"] in txt]
        check(not leaks, f"capacity: the report holds ids and numbers only, no English or Turkish text {leaks[:3]}")
        # alternatives
        a_id, b_id = sorted((s for s in src["strings"] if not loc.is_sub(s)), key=loc.sid_key)[:2]
        ea = dict(src["strings"][a_id])
        alts = [{"id": a_id, "check": lf.check_of(cat[a_id]["source_sha256"]), "alternative": ea["text"] + " a",
                 "alt_reason": "regression"},
                {"id": b_id, "check": lf.check_of(cat[b_id]["source_sha256"]), "alternative": "x一"}]
        lf.write_table(Path(td) / "alt.csv", ["id", "check", "alternative", "alt_reason"], alts)
        s1 = tw.cmd_suggest(ws, Path(td) / "alt.csv", "regress", "proposal", False)
        s2 = tw.cmd_suggest(ws, Path(td) / "alt.csv", "regress", "proposal", False)
        e2 = lf.load_project(w / "tr.json")["strings"][a_id]
        check(s1["changed"] == [a_id] and s1["rejected"] and s1["rejected"][0]["id"] == b_id and not s2["changed"]
              and e2["text"] == ea["text"] and e2["status"] == ea["status"] and e2.get("rev") == ea.get("rev")
              and e2["alt"][0]["text"] == ea["text"] + " a",
              "alternatives: stored beside the text (text, status, rev unchanged), once, a broken one refused")
        src2, used = cap.with_alternatives(lf.load_project(w / "tr.json"))
        r3 = cap.measure(paths, src2, w, None, layout=False)
        check(used == [a_id] and r3["main_table"]["replacement_bytes"] == t["replacement_bytes"] + 2,
              "alternatives: --use-alt measures the alternative (2 bytes more)")
        rv = tw.cmd_review(ws, "draft", None, 60, ".jsonl", a_id)
        rr = [x for _, x in lf.read_table(Path(rv["files"][0]))]
        sh = tw.cmd_sheet(ws, "all", None, ".csv")
        sr = {x["id"]: x for _, x in lf.read_table(Path(sh["file"]))}
        check(len(rr) == 1 and rr[0]["alternative"] == ea["text"] + " a" and sr[a_id]["alternative"] == ea["text"] + " a",
              "alternatives: shown in a review round (taken by --ids) and in the decision sheet")
        f2 = Path(td) / "ans2.jsonl"
        r0 = next(r for r in rows if r["id"] == a_id)
        f2.write_text(json.dumps(dict(r0, turkish=ea["text"] + "!"), ensure_ascii=False) + "\n", encoding="utf-8")
        tw.cmd_ingest(ws, f2, "r001/batch_001", "regress-model2", False)
        e3 = lf.load_project(w / "tr.json")["strings"][a_id]
        check(e3["text"] == ea["text"] + "!" and [x["text"] for x in e3["alt"]] == [ea["text"] + " a", ea["text"]]
              and e3["alt"][1]["kind"] == "previous_draft",
              "drafts: a later draft keeps the alternatives and the replaced draft")
        h = hashlib.sha256((w / "tr.json").read_bytes()).hexdigest()
        ws2 = tw.WS(w)
        pr = cap.project(paths, ws2.src, w, ws2.cat, ws2.context(), cap.parse_cases("x:1.0:1.0"), {"menu"}, True)
        check(pr["model"] and pr["cases"][0]["synthetic_strings"] > 100 and isinstance(pr.get("break_even"), (float, str))
              and hashlib.sha256((w / "tr.json").read_bytes()).hexdigest() == h,
              f"projection: a MODEL with a break-even factor ({pr.get('break_even')}); the workspace unchanged")
    check(all(hashlib.sha256(p.read_bytes()).hexdigest() == v for p, v in before.items()),
          "game files unchanged (fix.lvl, fix.ptr, VS.sub)")
    return finish()


if __name__ == "__main__":
    sys.exit(main())
