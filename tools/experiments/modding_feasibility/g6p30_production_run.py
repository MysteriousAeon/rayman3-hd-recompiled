#!/usr/bin/env python3
"""E-519 (D-286) G6-P30: one hidden PRODUCTION-build run of an editor-exported, production-compiled level patch.

    g6p30_production_run.py run TAG     the single hidden run (production build; no development variable anywhere)
    g6p30_production_run.py judge TAG   Q0 production markers, then the inherited G6-P27 P1-P6 judgement

PROSPECTIVE PROTOCOL (committed before the production build is used for any run; thresholds are not changed after
results)
Build: the full replay tools\\build_milestone8.bat (M8_BUILD_OK) with the G6-P30 production header
(tools/m33_mod_overlay.h, commit a92553c); `g5p1_dev_gate.py status` = production (SDK copy == the production
header); the new production hashes are recorded before the run. Before the run: g6p30_production_policy.py negtest
PASS (NEGTEST_G6P30 PASS, private/work/e519/negtest).
Mod: the mod folder the editor exported in G6-P29/E6 without the development variable (private/work/e518/prod_mod,
mod id g6p25.west-basin-fairy: start-floor-v2 vertex 6 -0.20, 2 / 4 -0.15; FairyLight graph A); compiled again here
WITHOUT the variable (production policy); expected transaction level-tx 2 intro_20 g6p25.west-basin-fairy
9083786df631a5a3, 55 ranges: the guest images of G6-P27 run m1.
Run: G6-P20's run_case with G6-P27's walk unchanged (hidden, non-activating, muted, no physical pad, private user
root, --test-level intro_20, 150 s, guest-scoped XAM stick events only, Exit Game at 85 s), with ONE change: the
game process gets NO R3HD_DEV_STRUCTURAL_TX (the runner's development variable is redirected to the inert name
R3HD_G6P30_INERT, which nothing reads; the parent environment must not hold R3HD_DEV_STRUCTURAL_TX).
One run `e519_<tag>_M`; no repeat except an INVALID run or a demonstrated harness defect, after a committed amendment.
Criteria:
  Q0 production activation: the runtime log holds exactly one
       `M33 level-tx active level=intro_20 mod=g6p25.west-basin-fairy id=9083786df631a5a3 (production policy D-286)`
     and exactly one `M33 level-tx version=2 members=lvl,ptr,transit (production policy D-286)`, and none of
     `development build`, `G5P1 level-tx`, `G6P1 level-tx`, `level_tx_not_enabled`; the run's environment record
     shows no R3HD_DEV_STRUCTURAL_TX.
  P1-P6: G6-P27's judgement unchanged (thresholds, walk, west-floor physics at the actual settled x / y, FairyLight
     graph A, exit and cleanup, M21 / M22 / M23 0). Two disclosed adaptations of inherited inputs only: (a) after Q0
     passes, the judge reads the log with the two production lines above mapped to the inherited development patterns
     (`G5P1 level-tx active level=... id=...`, `G6P1 level-tx version=2 members=lvl,ptr,transit`); (b) P6's offline
     refusal input is this milestone's production negtest (all 15 refusal cases and the control pass) instead of the
     development gate-off case, written to the run's own negtest/summary.json in the inherited shape.
Verdict: PRODUCTION RUNTIME VERIFIED iff Q0 and P1-P6 pass; otherwise named by the first failing criterion.

AMENDMENT 1 (after the build, before any run; criteria unchanged): the full replay compiled, linked and installed the
production header (SDK copy == tools/m33_mod_overlay.h; status production; r3hd.exe 6635d2327179d5a0...,
rexruntime.dll 784f7b72b7051bc3...; M33 overlay unit test 60 / 60 inside the replay) but stopped before M8_BUILD_OK at
m28_portable_regression's tracked-tree release audit (113 rejected tracked files: HANDOFF.md notes, the
level_patch_examples JSON since G6-P21, an old EXPERIMENTS.md line, a Linux test path; a pre-existing failure class
that earlier G6 restores never met because they used the incremental build; none is the overlay). The build
precondition is therefore: the replay's build and native-test stages PASS, then the overlay-relevant post-M28
regressions run separately on these binaries (r3hd_mods selftest, M33, M36, M38) and PASS before the run. The audit
failure is recorded as a release blocker, not fixed here.
AMENDMENT 1 RESULT (before the run): selftest 399 / 399, M33 38 / 38, M38 9 / 9; M36 first 19 / 20: its source-shape
check required no memcpy in ExtendRead, which the promoted G5-P3 member-image read now contains by design; the check
was updated (the grow path outside the R3HD_LEVEL_TX block keeps the old rule; the block must be exactly one copy of
min(length, image size - offset) bytes from the verified image), then M36 20 / 20. Criteria unchanged.
After the run: production stays installed (no development build is made); M33 / M36 / M38 regressions on it.
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import r3hd_mods as rm  # noqa: E402
import g6p27_west_basin_runtime as g27  # noqa: E402

g20, g3, p1 = g27.g20, g27.g3, g27.p1
ROOT = g27.ROOT
PREFIX = "e519"
WORK = ROOT / "private" / "work" / "e519" / "run"
NEG = ROOT / "private" / "work" / "e519" / "negtest" / "summary.json"
MOD = ROOT / "private" / "work" / "e518" / "prod_mod" / "mod.json"
MID, WANT_TX = "g6p25.west-basin-fairy", "9083786df631a5a3"
PROD_ACTIVE = (f"M33 level-tx active level=intro_20 mod={MID} id={WANT_TX} (production policy D-286)")
PROD_VERSION = "M33 level-tx version=2 members=lvl,ptr,transit (production policy D-286)"
DEV_MARKERS = ("development build", "G5P1 level-tx", "G6P1 level-tx", "level_tx_not_enabled")


def configure():
    g27.WORK, g27.PREFIX = WORK, PREFIX
    g27.configure()
    g20.ENV = "R3HD_G6P30_INERT"   # the runner's development variable, redirected: the game gets no gate variable


def run(tag):
    if os.environ.get(rm.STRUCT_ENV):
        raise SystemExit(f"{rm.STRUCT_ENV} is set in this environment")
    configure()
    st = os.popen(f'"{sys.executable}" "{HERE / "g5p1_dev_gate.py"}" status').read().strip()
    if st != "production":
        raise SystemExit(f"gate status {st!r}, not production")
    neg = json.loads(NEG.read_text())
    if not (neg["prod"][-1].endswith("PASS 19/19") and neg["old"][-1].endswith("PASS 1/1")):
        raise SystemExit("production negtest did not pass")
    overrides = json.loads(MOD.read_text(encoding="utf-8"))["overrides"]
    run_ = f"{PREFIX}_{tag}_M"
    res, text, paths = g20.plan_of(f"run_{tag}", [(MID, overrides)], session=run_, env=None)
    if res["active"] != [MID] or text is None or p1.parse_plan(text)["txs"] != [f"level-tx 2 intro_20 {MID} {WANT_TX}"]:
        raise SystemExit(f"compiler refused or changed the run's mod: {res.get('mods')}")
    row = g20.run_case(tag, "M", paths["cache"] / rm.PLAN_NAME, paths, tick=g27.make_walker())
    (WORK / tag / "M" / "env.json").write_text(json.dumps({"parent_has_variable": bool(os.environ.get(rm.STRUCT_ENV)),
                                                           "runner_variable": g20.ENV}, indent=1) + "\n")
    print(json.dumps(row, default=str)[:800])
    return 0


def judge(tag):
    configure()
    w = WORK / tag / "M"
    row = json.loads((w / "row.json").read_text())
    raw = g3.load_log(row["run"])
    q0 = {"active line once": raw.count(PROD_ACTIVE) == 1, "version line once": raw.count(PROD_VERSION) == 1,
          "no development markers": not any(m in raw for m in DEV_MARKERS),
          "no development variable in the game environment": (lambda e: not e["parent_has_variable"]
                                                              and e["runner_variable"] != rm.STRUCT_ENV)(
              json.loads((w / "env.json").read_text()))}
    (WORK / f"q0_{tag}.json").write_text(json.dumps(q0, indent=1) + "\n")
    if not all(q0.values()):
        print(json.dumps({"Q0": q0, "verdict": "PRODUCTION RUNTIME FAILED — ACTIVATION (Q0)"}, indent=1))
        return 1
    mapped = raw.replace(PROD_ACTIVE, f"G5P1 level-tx active level=intro_20 mod={MID} id={WANT_TX}").replace(
        PROD_VERSION, "G6P1 level-tx version=2 members=lvl,ptr,transit")
    g3.load_log = lambda run, _m=mapped: _m   # adaptation (a), after Q0
    neg = json.loads(NEG.read_text())
    ok = neg["prod"][-1].endswith("PASS 19/19") and neg["old"][-1].endswith("PASS 1/1")
    nd = WORK / "negtest"
    nd.mkdir(parents=True, exist_ok=True)
    (nd / "summary.json").write_text(json.dumps({   # adaptation (b): the inherited shape, from the production negtest
        "source": str(NEG), "dev": {"results": [{"case": "combined not enabled -> G6-P30 production refusals N1-N15",
                                                  "rc": 0 if ok else 1}]},
        "prod": {"passed": 19 if ok else 0, "cases": 19}}, indent=1) + "\n")
    rc = g27.judge(tag)
    # judge correction after the first call (disclosed; first output kept as verdict_<tag>_first_call.json): the
    # first call read judgement_<tag>.json, G6-P20's intermediate judgement (start-two-step-v1 P2 / P3) that G6-P27's
    # judge builds on; the protocol's P1-P6 are G6-P27's own judgement, written to judgement_g6p27_<tag>.json
    j = json.loads((WORK / f"judgement_g6p27_{tag}.json").read_text())
    verdict = ("PRODUCTION RUNTIME VERIFIED" if rc == 0 and str(j.get("verdict", "")).startswith("G6-P27 VERIFIED")
               else f"PRODUCTION RUNTIME NOT VERIFIED ({j.get('verdict')})")
    (WORK / f"verdict_{tag}.json").write_text(json.dumps({"Q0": q0, "inherited": j.get("verdict"),
                                                          "verdict": verdict}, indent=1) + "\n")
    print(verdict)
    return 0 if verdict == "PRODUCTION RUNTIME VERIFIED" else 1


if __name__ == "__main__":
    cmd = sys.argv[1:]
    if len(cmd) == 2 and cmd[0] in ("run", "judge"):
        sys.exit({"run": run, "judge": judge}[cmd[0]](cmd[1]))
    raise SystemExit(__doc__)
