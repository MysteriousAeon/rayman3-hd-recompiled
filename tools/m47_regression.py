#!/usr/bin/env python3
"""M47 regression (no game run): returned review rounds -> one reconciled integration (D-085).

  * selftests of m47_review_audit.py (returned table against its export: drifted metadata repaired, changed English /
    Turkish, order, missing / duplicated / invented rows, verdicts, encoding, header and separator refused; overlapping
    rounds reduced deterministically) and r3hd_trwork.py (integrate: only a stored suggestion, never approved,
    idempotent, approved entries untouched, stale rows refused)
  * build order: this regression after M39; the workflow guide names integrate
  * real data (skipped without it), in a temporary workspace with the M34 sample's own Turkish (tracked, no game
    text): a review round exported, two returned tables written (one with a drifted round, one reviewing another
    Turkish), the audit (repair + importer dry run on an isolated copy; the corrupt table fails closed), merge (a
    missing resolution fails closed), apply on an isolated copy and for real, verify, a rerun that changes nothing,
    no entry approved, the returned tables byte-identical afterwards; game files unchanged
Writes only into a temporary folder.

usage: m47_regression.py
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


def last(r) -> str:
    out = r.stdout.strip().splitlines()
    return out[-1] if out else r.stderr[-200:]


def finish() -> int:
    n = results.count(False)
    print(f"M47_REGRESSION {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}")
    return 1 if n else 0


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    sys.stdout.reconfigure(errors="backslashreplace")
    for tool, marker in (("m47_review_audit.py", "M47_REVIEW_AUDIT selftest PASS"),
                         ("r3hd_trwork.py", "R3HD_TRWORK_SELFTEST PASS")):
        r = run(str(TOOLS / tool), "selftest")
        check(r.returncode == 0 and marker in r.stdout, f"{tool} selftest ({last(r)})")
    bat = (TOOLS / "build_milestone8.bat").read_text(encoding="utf-8", errors="replace")
    pos = [bat.find(s) for s in ("python tools\\m39_regression.py", "python tools\\m47_regression.py", "M8_BUILD_OK")]
    check(all(x > 0 for x in pos) and pos == sorted(pos), f"build: M47 regression after M39 {pos}")
    guide = (ROOT / "config" / "localization" / "WORKFLOW.md").read_text(encoding="utf-8")
    check("integrate" in guide and "m47_review_audit" in guide, "workflow guide: names the audit and integrate")
    game = ROOT / "private" / "extracted" / rm.TITLE_ID
    if not (game / "GAMEDATAbin" / "VS.sub").is_file():
        print("SKIP real-data checks: no game data", flush=True)
        return finish()
    watched = [game / "GAMEDATAbin" / n for n in ("fix.lvl", "fix.ptr", "VS.sub")]
    before = {p: sha(p) for p in watched}
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
        ids = sorted((s for s in tw.WS(w).src["strings"] if not loc.is_sub(s)), key=loc.sid_key)
        rv = tw.cmd_review(tw.WS(w), "draft", None, 60, ".jsonl", ",".join(ids[:4]))
        export = Path(rv["files"][0])
        src_rows = [json.loads(x) for x in export.read_text(encoding="utf-8").splitlines() if x.strip()]
        cols = list(src_rows[0])
        ret = w / "private" / "review" / "_returned"
        ret.mkdir(parents=True)

        def returned(rows_out, name="r001_batch_001.tsv"):
            lf.write_table(ret / name, cols, rows_out)
            return ret / name
        changed_id = src_rows[0]["id"]
        out_rows = []
        for i, r in enumerate(src_rows):
            r = {k: ("" if v is None else v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
                 for k, v in r.items()}
            r["verdict"] = "ok"
            if i == 0:
                r.update(verdict="change", suggestion=r["turkish"] + " a", review_note="regression")
            if i == 1:
                r["round"] = "3"   # the r001 / batch_002 kind of drift
            out_rows.append(r)
        p_ret = returned(out_rows)
        h_ret = sha(p_ret)
        out = w / "private" / "m47"
        a = run(str(TOOLS / "m47_review_audit.py"), "audit", str(w), "--returned", str(ret), "--expect", "r001=1:4")
        aj = json.loads((out / "audit" / "audit.json").read_text(encoding="utf-8"))
        f0 = aj["files"][0]
        if a.returncode:
            print("  audit:", json.dumps({k: aj.get(k) for k in ("expect", "missing_returns", "unexpected_returns")}),
                  [x["fatal"] + x.get("suggestion_errors", []) for x in aj["files"]], flush=True)
        check(a.returncode == 0 and "M47_REVIEW_AUDIT PASS" in a.stdout and f0["repaired"] == {"round": 1}
              and aj["importer"]["r001_batch_001.tsv"]["stored_rounds"] == {"1": 4}
              and aj["importer"]["raw:r001_batch_001.tsv"]["stored_rounds"] == {"1": 3, "3": 1}
              and aj["isolated_copy_untouched"],
              f"audit: drifted round repaired from the export; the importer (isolated) stores round 1; the raw file "
              f"would have stored round 3 ({last(a)})")
        bad = [dict(r) for r in out_rows]
        bad[2]["turkish"] = bad[2]["turkish"] + "x"
        returned(bad, "r001_batch_001.tsv")
        b = run(str(TOOLS / "m47_review_audit.py"), "audit", str(w), "--returned", str(ret),
                "--out", str(Path(td) / "private" / "bad"))
        check(b.returncode == 1 and "M47_REVIEW_AUDIT FAIL" in b.stdout,
              f"audit: a returned table that reviewed another Turkish fails closed ({last(b)})")
        returned(out_rows)
        check(sha(p_ret) == h_ret, "audit: the returned table is never rewritten by the audit (same bytes)")
        a = run(str(TOOLS / "m47_review_audit.py"), "audit", str(w), "--returned", str(ret))
        res = Path(td) / "private" / "res.tsv"
        lf.write_table(res, ["id", "action", "group", "reason"], [])
        m = run(str(TOOLS / "m47_review_audit.py"), "merge", str(w), "--returned", str(ret), "--resolution", str(res))
        check(m.returncode == 1 and "M47_REVIEW_MERGE FAIL" in m.stdout,
              f"merge: a non-ok review without a resolution fails closed ({last(m)})")
        hx = sha(w / "tr.json")
        x = run(str(TOOLS / "m47_review_audit.py"), "apply", str(w))
        check(x.returncode == 2 and "passing merge" in (x.stdout + x.stderr) and sha(w / "tr.json") == hx,
              "apply: refused after a failed merge; the project untouched")
        lf.write_table(res, ["id", "action", "group", "reason"],
                       [{"id": changed_id, "action": "integrate", "group": "", "reason": "regression"}])
        m = run(str(TOOLS / "m47_review_audit.py"), "merge", str(w), "--returned", str(ret), "--resolution", str(res))
        check(m.returncode == 0 and "integrate=1" in m.stdout, f"merge: one row per id, one integration ({last(m)})")
        h0 = sha(w / "tr.json")
        i = run(str(TOOLS / "m47_review_audit.py"), "apply", str(w), "--isolated")
        check(i.returncode == 0 and "PASS (isolated copy)" in i.stdout and sha(w / "tr.json") == h0,
              f"apply --isolated: twice on a copy, the rerun identical; the workspace untouched ({last(i)})")
        ap = run(str(TOOLS / "m47_review_audit.py"), "apply", str(w))
        h1 = sha(w / "tr.json")
        ap2 = run(str(TOOLS / "m47_review_audit.py"), "apply", str(w))
        v = run(str(TOOLS / "m47_review_audit.py"), "verify", str(w))
        src = lf.load_project(w / "tr.json")
        e = src["strings"][changed_id]
        check(ap.returncode == ap2.returncode == v.returncode == 0 and sha(w / "tr.json") == h1
              and "already applied" in ap2.stdout and e["status"] == "reviewed"
              and e["text"] == out_rows[0]["turkish"] + " a" and e["origin"] == "integrated:gemini.r1"
              and any(x["text"] == out_rows[0]["turkish"] for x in e["alt"])
              and not any(loc.status_of(x) == "approved" for x in src["strings"].values())
              and all(x["review"]["by"] == "gemini" for k, x in src["strings"].items() if k in ids[:4]),
              f"apply: reviews stored, the suggestion integrated as reviewed text (previous kept), nothing "
              f"approved; a rerun changes nothing; verify passes ({last(v)})")
        mh = {n: sha(out / "merge" / n) for n in ("consolidated_review.tsv", "integrate.tsv")}
        a2 = run(str(TOOLS / "m47_review_audit.py"), "audit", str(w), "--returned", str(ret))
        m2 = run(str(TOOLS / "m47_review_audit.py"), "merge", str(w), "--returned", str(ret), "--resolution", str(res))
        check(a2.returncode == m2.returncode == 0
              and all(sha(out / "merge" / n) == h for n, h in mh.items()) and sha(w / "tr.json") == h1,
              f"rerun after apply: audit and merge see the export-time view; the same merge files; nothing changes "
              f"({last(a2)} / {last(m2)})")
        check(sha(p_ret) == h_ret, "returned table byte-identical after audit, merge and apply")
    check(all(sha(p) == h for p, h in before.items()), "game files unchanged")
    return finish()


if __name__ == "__main__":
    sys.exit(main())
