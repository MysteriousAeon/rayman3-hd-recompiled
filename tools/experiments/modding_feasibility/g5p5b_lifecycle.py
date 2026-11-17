#!/usr/bin/env python3
"""E-483 (D-250) G5-P5b: the G5-P5 dual-node structural mod (one mod `g5p5.dual`, one `level-tx`, new_A after original
node 13, new_B after original node 22; intro_10 143 -> 145 nodes, .lvl +208, .ptr +144 / 18 entries) through G5-P3's
same-process Pause -> Load reload and G5-P4b's ownership-checked abnormal termination and recovery.

usage:
  g5p5b_lifecycle.py check          offline O1-O7 (no game): G5-P5's check and negtest, G5-P4b's preflight with the
                                    dual mod, compiler identity with E-482
  g5p5b_lifecycle.py reload TAG     phase 1: one hidden run of G5-P3's route with the dual mod (case ra)
  g5p5b_lifecycle.py recover TAG    phase 2: G5-P4b's phases A (armed launch, both nodes consumed, forced termination),
                                    C (recovery launch), D (explicit clear)
  g5p5b_lifecycle.py judge-reload TAG / judge-recover TAG
Outputs stay under private/work/e483/.

REUSED MECHANISMS (unchanged except for module constants with single-site defaults, committed with this file):
  g5p3_reentry.run_case (route, steps, observation; PLAN_MOD and AREA10 set here); g5p4b_recovery (preflight, plan /
  orderly / complete through tools\\play.ps1's own functions loaded by g5p4b_lifecycle.ps1, launch, ownership-checked
  kill, run, judge; STRUCT_ID, STRUCT_OV, GROWN_AREA, sites(), GROWN_NODES, new_nodes() set here; the kill now waits
  for a pass through EVERY site, default one site). The generalized G5-P4b judge re-judged E-481 k2 with identical
  R1-R10 and details. Runner bindings: g5p5_pilot.bind (the dual site's 7 edited words, node 13's arc).

OFFLINE (check), before any build:
  O1 compiler stability: the dual plan's .lvl / .ptr SHA-256 and level-tx id equal E-482's (neutral: lvl 9b9aee5f...,
     id 70f2d1351ced88d3; offset: id 521620bc0eb54c7f), sizes 7,662,044 / 209,212.
  O2 structural integrity, O3 relocation, O5 atomic rejection: g5p5_pilot.py check (43 checks) re-run into e483.
  O4 immutable source: g5p5_pilot.py negtest re-run (G5-P3 integrity tests at 208 / 144: snapshot, repeated opens, host
     changes, reversed order; dual-plan header cases).
  O6 recovery compatibility: G5-P4b's preflight with the dual mod (14 checks: orderly-exit decision, arm at plan,
     synthetic abnormal child keeps the marker, wrong owner not terminated, concurrent launch refused, other session /
     wrong plan cannot clear, malformed marker, orderly exit clears, exit 0 alone keeps, profile-scoped clear,
     production refusal, play.ps1 -DryRun, G5-P2b R1-R8).
  O7 production refusal: production header unknown_record (preflight, negtest), production compiler refuses the dual mod.

PROSPECTIVE PROTOCOL (committed before the development build and any modified run)
Build: g5p1_dev_gate.py apply + tools\\build_incremental.bat; production restored afterwards (revert + rebuild).

PHASE 1 (reload), run e483_TAG_ra: G5-P3's route exactly (copy of save entry intro_10_fresh as the disposable profile;
  Title -> Load -> intro_10; 20 s later Pause -> Load -> Yes -> intro_10 again in the same process; 30 s later Pause ->
  Exit Game -> title; 220 s; guest-scoped input, hidden, non-activating, muted, no captures). Plan: the dual neutral
  mod, resolve_all with session = run (marker armed), R3HD_DEV_STRUCTURAL_TX=intro_10; the harness ends the session
  after a controlled exit. Control: NOT re-run: E-479 r2 rb (same route and runner, no plan, no variable; a no-plan run
  never reaches the transaction code, so the later gate additions cannot change it). Traversal window (from that
  control, per site, measured before this protocol): load 1 passes each site once (13 -> 14 at +6.2 s, 22 -> 23 at
  +9.3 s after the area appears; the pause then freezes the flight), load 2 twice (+6.2 / +22.4 s and +9.2 / +25.5 s).
  Route valid: load bursts menumap, intro_10, intro_10 in order and two intro_10 entries observed; otherwise
  INVALID-ROUTE (no verdict; the harness assumption is documented and corrected before a fresh tag).
  L1 initial activation: one `M33 mods state=active`; exactly one `G5P1 level-tx active` = the plan's (level, mod, id);
     `G5P3 tx snapshot` intro_10.lvl image_bytes 7662044 and intro_10.ptr 209212, disk_reads=2, both before the first
     `G5P3 tx read`; entry 1 live walk: 145 distinct nodes, no problems, header count 145, new_A at index 14 and new_B
     at index 24, the 7 edited words = [new_A] x 3 + [new_B] x 3 + [145], node 13's arc -> new_A.
  L2 both nodes consumed (entry 1): >= 1 pass 13 -> new_A -> 14 and >= 1 pass 22 -> new_B -> 23 in generator variable
     8; every departure from node 13's waypoint goes to new_A and from new_A to node 14's; the same for 22 / new_B /
     23; new_A and new_B each in >= 1 sample.
  L3 reload: route valid; entry 1 left (left_t) before entry 2 appeared, with a fix-only block-8 state between them
     (the level area released); `G5P3 tx pass` >= 2 for each member (the second load read the members again); one
     game process for the whole run (one pid, runner exit 0).
  L4 reapplication (entry 2): L1's walk criteria; >= 2 passes through each site (the control's load-2 window has 2),
     departures as in L2.
  L5 memory accounting: valid block-8 walks after the first valid snapshot; versus the control, D(menumap before) = {},
     D(entry 1) = D(entry 2) = {area1_length +208, free -208, largest -208}, D(fix between) = {}, D(menumap after) = {};
     within the run (area slot numbers ignored): entry 1 = entry 2, menumap before = menumap after, fix between = the
     control's fix-only state (20,795,836 free, one chunk). Host side: snapshot images 7,662,044 + 209,212 =
     7,871,256 bytes (<= the 16 MiB snapshot budget), not block 8.
  L6 immutable transaction consistency: one level-tx line, exactly two snapshot lines (no re-snapshot on reload), no
     `G5P3 tx host_changed`, no `M36 grow read` naming intro_10.lvl / .ptr, every `G5P3 tx pass` line's image_bytes
     equal to its member's snapshot; entries 1 and 2 have the same area base and length and the same edited-word values
     relative to the base.
  L7 gameplay: in each entry, with new_A / new_B removed from the waypoint sequence, every transition is one the
     control made or the next node in graph order; the arrival at node 14's and node 23's waypoint after each pass is
     within 1.5 s (relative to the entry's area appearance) of the control's corresponding arrival (E-479 r2: ra vs
     rb 0.1 s; the neutral nodes lie within 0.6 / 0.7 units of the path, E-482).
  L8 safety: M21 / M22 / M23 0, haptics policy line, runner exit 0, no game process left; run.json
     game_foreground_events = game_foreground_samples = 0; the marker armed before the start (session = run, plan
     SHA-256) and cleared by the controlled end; nothing else written to real profiles (G5-P4b's protected() equal
     before / after).
PHASE 2 (recovery), tag TAG: G5-P4b's phases with mods root RA = g5p5.dual + e478.lums-6, RB = g5p5.dual only
  (isolation witness); A 140 s, kill 3 s after BOTH sites have been passed (13 -> new_A -> 14 and 22 -> new_B -> 23),
  no later than 45 s after the area appears (else INVALID, nothing killed); C 110 s; D clear / dry run / re-arm / clear.
  R1 marker ordering: marker mtime < game process creation < first `M36 grow size` naming intro_10; one level-tx and
     two snapshot lines in A.  (G5-P4b R2)
  R2 dual activation: A's live walk 145 distinct nodes, no problems, new_A index 14, new_B index 24, node 13's arc ->
     new_A; >= 1 pass through EACH site before the termination.  (G5-P4b R3, generalized)
  R3 process ownership: the marker names session e483_TAG_A and RA's plan SHA-256; the terminated pid passed every
     check (r3hd.exe, the runner's exe path, this run's --log_file, created after the runner start, grandparent = the
     runner).  (G5-P4b R1)
  R4 abnormal termination, R5 marker persistence: G5-P4b R4 / R5 unchanged (exit code != 0, runner ended early, no
     e483 game process, Test-R3hdOrderlyExit false also with exit 0 substituted; Complete leaves the marker; marker
     bytes identical before the launch, after the kill and after Complete).
  R6 recovery refusal: C's plan refuses g5p5.dual with STRUCTURAL_RECOVERY (both structural changes, the mod whole),
     no level-tx / tx-file in the plan; C's log has no `G5P1 level-tx`, `G5P3` or `M36 grow`; marker unchanged after C.
  R7 original resources: C's live walk 143 nodes without problems; intro_10's area length 7,661,832 (original).
  R8 ordinary mod: G5-P4b R7 (e478.lums-6 active in A and C, served in intro_10.lvl, C leaves for intro_15).
  R9 isolation and explicit clear: G5-P4b R8 and R9 (RB never marked and still lists g5p5.dual; clear, dry run lists
     it, the stamp-D plan carries its level-tx and arms e483_TAG_D, final clear).
  R10 production and desktop safety: G5-P4b R10 as revised (production refusal in preflight, protected files equal,
     game foreground events / samples 0, monitor clean, M21-M23 0, no process left, C exit 0).
REVISION 1 (after reload run l1; l1 stays as judged: L1, L2, L4-L7 PASS, L3 and L8 FAIL, NOT PASSED; its judgement is kept):
  Cause: a harness assumption, not the transaction. L3 / L8's "no game process left" used g3a.alive(pid), a tasklist
  query by pid only, taken the moment the runner returned. In l1 the game logged its orderly shutdown ('Title
  terminated; hard-exiting process.' at 15:24:08.749 UTC), the runner recorded exit code 0 at 15:24:08.789, and no
  r3hd.exe existed afterwards; a pid-only query 40 ms after the reported exit cannot tell a surviving game from an
  image still tearing down or another program given the same pid. Every other L3 / L8 condition passed.
  Correction, for fresh runs only (both phases; the recovery phase has not run): "no game process left" = 5 s after
  the runner ends, no r3hd.exe whose command line names the run (g3a.game_left, positive / negative tested on a
  test-owned process); the immediate pid-only result and the pid's holder are recorded beside it. Nothing else
  changes. Fresh reload run: l2. Recovery tag: k1 (its R4 / R10 use the corrected check).
Class: L1-L8 and R1-R10 PASS = G5-P5b VERIFIED — DUAL-TRANSACTION LIFECYCLE & RECOVERY. Critical failures (a node
missing after reload, partial data, stale pointer, wrong relocation count, retained memory, marker cleared, structural
active in recovery, other profile affected, desktop violation) stop the affected phase; the result is kept.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))
import r3hd_mods as rm  # noqa: E402
import g3a_ab as g3a  # noqa: E402
import g3b_ab as g3b  # noqa: E402
import block8_probe as bp  # noqa: E402,F401
import g5p1_pilot as p1  # noqa: E402
import g5p5_pilot as p5  # noqa: E402
import g5p3_reentry as r3  # noqa: E402
import g5p4b_recovery as p4b  # noqa: E402

PREFIX = "e483"
WORK = ROOT / "private" / "work" / PREFIX
RUNS = g3a.RUNS
TAIL, PGROW = p5.TAIL, p5.PGROW
SIZE, PSIZE, AREA = g3a.SIZE, g3a.PSIZE, g3a.AREA
E482 = ROOT / "private" / "work" / "e482"
CONTROL = ROOT / "private" / "work" / "e479" / "r2" / "rb", "e479_r2_rb"
TX_E482 = {"neutral": "70f2d1351ced88d3", "offset": "521620bc0eb54c7f"}
FIX_ONLY_FREE = 20795836
TOL_T = 1.5


def setup(bind=True):
    """Bind the reused harnesses to the dual mod and to e483 (bind: also G3b's runner constants, for live runs only;
    the offline checks need G3b's own single-site constants)."""
    WORK.mkdir(parents=True, exist_ok=True)
    if bind:
        p5.bind()
    p1.WORK = WORK
    s13, s22 = p5.S(13), p5.S(22)
    r3.PREFIX, r3.WORK = PREFIX, WORK
    r3.PLAN_MOD = (p5.MOD, lambda: p5.dual("neutral"))
    r3.AREA10 = (AREA, AREA + TAIL)
    p4b.PREFIX, p4b.WORK = PREFIX, WORK
    p4b.STRUCT_ID = p5.MOD
    p4b.STRUCT_OV = lambda: p5.dual("neutral")
    p4b.GROWN_AREA = AREA + TAIL
    p4b.GROWN_NODES = 145
    p4b.sites = lambda: [(s13["WA"], p5.PLACE[13]["waypoint"], s13["WB"]),
                         (s22["WA"], p5.PLACE[22]["waypoint"], s22["WB"])]
    p4b.new_nodes = lambda: [(14, p5.PLACE[13]["node"]), (24, p5.PLACE[22]["node"])]
    return s13, s22


# --- offline -----------------------------------------------------------------------------------------------------

def check():
    setup(bind=False)
    res, det = {}, {}
    old = json.loads((E482 / "offline.json").read_text())["details"]
    for v in ("neutral", "offset"):
        _, tx = p5.compiled(v)
        L, P = tx["images"]["lvl"], tx["images"]["ptr"]
        r, text, _ = p1.compile_plan(f"o1_{v}", [(p5.MOD, p5.dual(v))])
        txs = p1.parse_plan(text or "")["txs"]
        res[f"O1_{v}_bytes_and_id_as_E482"] = (rm.sha256_bytes(L) == old[v]["lvl_sha256"]
                                               and rm.sha256_bytes(P) == old[v]["ptr_sha256"]
                                               and len(L) == SIZE + TAIL and len(P) == PSIZE + PGROW
                                               and txs == [f"level-tx 1 intro_10 {p5.MOD} {TX_E482[v]}"]
                                               and tx["info"]["slots"] == 18 and tx["info"]["nodes"] == 145)
        det[f"O1_{v}"] = {"lvl": rm.sha256_bytes(L), "ptr": rm.sha256_bytes(P), "tx": txs}
    # G5-P5's offline check and negtest, re-run into e483 (they write under p5.WORK)
    p5.WORK = WORK / "g5p5"
    p5.WORK.mkdir(parents=True, exist_ok=True)
    p1.WORK = p5.WORK
    rc_check = p5.check()
    p5.WORK.mkdir(parents=True, exist_ok=True)
    p1.WORK = p5.WORK
    rc_neg = p5.negtest()
    off = json.loads((p5.WORK / "offline.json").read_text())
    neg = json.loads((p5.WORK / "negtest" / "summary.json").read_text())
    c = off["checks"]
    det["g5p5_check"] = {"rc": rc_check, "passed": sum(c.values()), "total": len(c)}
    det["g5p5_negtest"] = {"rc": rc_neg, "dev": neg["dev"]["summary"], "prod": neg["prod"]["summary"], "g5p3": neg["g5p3"]}
    pick = lambda pre: all(v for k, v in c.items() if k.startswith(pre))  # noqa: E731
    res["O2_structural_integrity"] = rc_check == 0 and pick("O2_")
    res["O3_relocation_integrity"] = rc_check == 0 and pick("O3_")
    res["O4_immutable_source"] = rc_neg == 0 and neg["g5p3"]["dev_all_pass"] and neg["g5p3"]["old_reproduces_exactly"]
    res["O5_atomic_rejection"] = rc_check == 0 and c["O5_atomic_rejection"] and neg["dev"]["exit"] == 0
    # G5-P4b's preflight with the dual mod (writes e483/preflight.json, which phase 2 requires)
    setup(bind=False)
    rc_pre = p4b.preflight()
    pre = json.loads((WORK / "preflight.json").read_text())
    det["preflight"] = pre["res"]
    res["O6_recovery_compatibility"] = rc_pre in (0, None) and pre["pass"] and len(pre["res"]) == 14
    res["O7_production_refusal"] = (pre["res"]["production_refuses"] and neg["prod"]["exit"] == 0
                                    and c["O6_conflict_policy"])
    out = {"res": res, "details": det, "pass": all(res.values())}
    (WORK / "check.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"res": res, "g5p5": det["g5p5_check"], "neg": det["g5p5_negtest"]}, indent=1, default=str))
    return 0 if out["pass"] else 1


# --- phase 1: reload --------------------------------------------------------------------------------------------

def reload(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    if not json.loads((WORK / "check.json").read_text())["pass"]:
        raise SystemExit("check did not pass")
    setup()
    before = p4b.protected()
    row = r3.run_case(tag, "ra")
    (WORK / tag / "protected.json").write_text(json.dumps({"before": before, "after": p4b.protected()}) + "\n")
    print(json.dumps(row, default=str)[:3000])
    return 0


def _load_reload(work, run):
    r = json.loads((work / "row.json").read_text())
    r["states"] = json.loads((work / "states.json").read_text())
    r["entries"] = json.loads((work / "entries.json").read_text())
    r["log"] = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / run).glob("runtime*.log")))
    r["phases"] = r3.phases(r["states"])
    rj = RUNS / run / "run.json"
    r["run_json"] = json.loads(rj.read_text(encoding="utf-8-sig")) if rj.is_file() else {}
    return r


def judge_reload(tag):
    s13, s22 = setup()
    run = f"{PREFIX}_{tag}_ra"
    ra = _load_reload(WORK / tag / "ra", run)
    rb = _load_reload(*CONTROL)                      # the control never grows: AREA is in AREA10 either way
    ra["judges"] = {t: subprocess.run([sys.executable, str(TOOLS / t), "--run", run], cwd=ROOT, capture_output=True,
                                      text=True).returncode
                    for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py")}
    det, L = {}, {}
    b = iter(ra["bursts"])
    route = (all(any(n == s for s in b) for n in ("menumap", "intro_10", "intro_10")) and len(ra["entries"]) >= 2
             and ra["phases"]["e2"] is not None)
    det["bursts"] = ra["bursts"]
    if not route:
        res = {"verdict": "INVALID-ROUTE", "bursts": ra["bursts"], "entries": len(ra["entries"])}
        (WORK / f"judgement_reload_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
        print(json.dumps(res, indent=1, default=str))
        return 1
    log = ra["log"]
    lines = log.splitlines()
    ptx = p1.parse_plan((WORK / tag / "ra" / "plan_copy.txt").read_text(encoding="utf-8"))["txs"]
    want_tx = [tuple(ptx[0].split(" ")[2:5])] if ptx else None
    tx = [tuple(x) for x in re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log)]
    snaps = re.findall(r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", log)
    snap_sizes = {f: b_ for f, _, b_, _ in snaps}
    first = {k: next((i for i, ln in enumerate(lines) if k in ln), None)
             for k in ("M33 mods state=active", "G5P3 tx snapshot", "G5P3 tx read")}
    e1, e2 = ra["entries"][0], ra["entries"][1]

    def graph_ok(e):
        lv, a = e.get("live", {}), e["ab"]
        NA, NB = a + p5.PLACE[13]["node"] - 4, a + p5.PLACE[22]["node"] - 4
        return (lv.get("problems") == [] and len(lv.get("nodes", [])) == 145 == len(set(lv["nodes"]))
                and lv["header"]["count"] == 145 and lv["nodes"][14] == NA and lv["nodes"][24] == NB
                and lv["changed"] == [NA] * 3 + [NB] * 3 + [145] and lv["arc13"] == {"count": 1, "target": NA}
                and e["length"] == AREA + TAIL)
    det["graph"] = {i: graph_ok(e) for i, e in ((1, e1), (2, e2))}
    L["L1_initial_activation"] = (log.count("M33 mods state=active") == 1 and tx == want_tx
                                  and sorted((f, b_, d) for f, _, b_, d in snaps)
                                  == [("intro_10.lvl", str(SIZE + TAIL), "2"), ("intro_10.ptr", str(PSIZE + PGROW), "2")]
                                  and None not in first.values() and first["G5P3 tx snapshot"] < first["G5P3 tx read"]
                                  and first["M33 mods state=active"] < first["G5P3 tx read"] and det["graph"][1])

    def seq(e):
        out = []
        for x in e["samples"]:
            if not out or out[-1][0] != x["v8"]:
                out.append((x["v8"], x["t"]))
        return out

    def consume(e, need):
        a, s = e["ab"], seq(e)
        v = [w for w, _ in s]
        out = {}
        for k, st in ((13, s13), (22, s22)):
            wa, wn, wb = a + st["WA"] - 4, a + p5.PLACE[k]["waypoint"] - 4, a + st["WB"] - 4
            n = sum(1 for i in range(len(v) - 2) if v[i] == wa and v[i + 1] == wn and v[i + 2] == wb)
            dep_a = [y for x, y in zip(v, v[1:]) if x == wa]
            dep_n = [y for x, y in zip(v, v[1:]) if x == wn]
            at_n = sum(1 for x in e["samples"] if x["v8"] == wn)
            out[k] = {"passes": n, "at_new": at_n, "ok": n >= need and at_n >= 1 and all(y == wn for y in dep_a)
                      and all(y == wb for y in dep_n)}
        return out
    c1, c2 = consume(e1, 1), consume(e2, 2)
    det["consumption"] = {"entry1": c1, "entry2": c2}
    L["L2_both_nodes_consumed"] = c1[13]["ok"] and c1[22]["ok"]
    passes = re.findall(r"G5P3 tx pass file=(\S+) pass=(\d+) reads_before=\d+ image_bytes=(\d+)", log)
    det["tx_passes"] = {f: sum(1 for x, _, _ in passes if x == f) for f in ("intro_10.lvl", "intro_10.ptr")}
    ph = ra["phases"]
    L["L3_reload"] = (route and e1.get("left_t") is not None and e1["left_t"] <= e2["t"]
                      and ph["fix_between"] is not None and all(n >= 2 for n in det["tx_passes"].values())
                      and ra["runner_exit"] == 0 and not ra["process_left"])
    L["L4_reapplication"] = det["graph"][2] and c2[13]["ok"] and c2[22]["ok"]
    D = {k: r3.diff(r3.brief(ph[k]), r3.brief(rb["phases"][k]))
         for k in ("menu_before", "e1", "e2", "fix_between", "menu_after")}

    def norm(x):
        bb = r3.brief(x)
        return bb and {k: bb[k] for k in ("free", "largest", "alloc", "free_chunks")} | {
            "areas": sorted(bb["areas"].values())}
    within = {"e1_eq_e2": norm(ph["e1"]) == norm(ph["e2"]), "menu_before_eq_after":
              norm(ph["menu_before"]) == norm(ph["menu_after"]),
              "fix_between": norm(ph["fix_between"]) == norm(rb["phases"]["fix_between"])
              and (ph["fix_between"] or {}).get("free_bytes") == FIX_ONLY_FREE}
    want = {"area1_length": TAIL, "free": -TAIL, "largest": -TAIL}
    host = sum(int(b_) for b_ in snap_sizes.values())
    det["memory"] = {"D": D, "within": within, "host_snapshot_bytes": host,
                     "phases": {k: r3.brief(v) for k, v in ph.items() if isinstance(v, dict)}}
    L["L5_memory_accounting"] = (ph["walk_ok"] and D["menu_before"] == {} and D["e1"] == want and D["e2"] == want
                                 and D["fix_between"] == {} and D["menu_after"] == {} and all(within.values())
                                 and host == SIZE + TAIL + PSIZE + PGROW <= 16 << 20)
    rel = lambda e: [w - e["ab"] for w in e["live"]["changed"][:6]]  # noqa: E731
    L["L6_immutable_consistency"] = (
        len(tx) == 1 and len(snaps) == 2 and "G5P3 tx host_changed" not in log
        and not re.search(r"M36 grow read file=intro_10\.(lvl|ptr)", log)
        and all(b_ == snap_sizes.get(f) for f, _, b_ in passes)
        and (e1["ab"], e1["length"]) == (e2["ab"], e2["length"]) and rel(e1) == rel(e2))
    # L7: route and timing against the control
    graph_next = {}
    entry = rm.read_script_index(g3a.GAME, "intro_10")["graphs"][(rm.FLY10, 0, 0)]
    wps = [w for _, w in entry["nodes"]]
    for i in range(len(wps) - 1):
        graph_next[wps[i]] = wps[i + 1]
    news = {p5.PLACE[13]["waypoint"], p5.PLACE[22]["waypoint"]}

    def collapsed(e):
        return [(w - e["ab"] + 4, t) for w, t in seq(e) if w - e["ab"] + 4 not in news]

    def trans(e):
        c = [w for w, _ in collapsed(e)]
        return {(x, y) for x, y in zip(c, c[1:]) if x != y}
    ctrl = trans(rb["entries"][0]) | trans(rb["entries"][1])

    def arrivals(e, w):
        return [round(t - e["t"], 2) for x, t in collapsed(e) if x == w]
    l7 = {}
    for i, (ea, eb) in enumerate(((e1, rb["entries"][0]), (e2, rb["entries"][1])), 1):
        bad = [t for t in trans(ea) if t not in ctrl and graph_next.get(t[0]) != t[1]]
        arr = {k: (arrivals(ea, st["WB"]), arrivals(eb, st["WB"])) for k, st in ((13, s13), (22, s22))}
        ok_t = all(len(x) >= 1 and len(y) >= 1 and all(abs(p - q) <= TOL_T for p, q in zip(x, y))
                   for x, y in arr.values())
        l7[i] = {"unexpected_transitions": len(bad), "arrivals_ra_rb": arr, "ok": not bad and ok_t}
    det["L7"] = l7
    L["L7_gameplay"] = all(v["ok"] for v in l7.values())
    rj = ra["run_json"]
    prot = json.loads((WORK / tag / "protected.json").read_text())
    mb = ra["marker_before_start"]
    L["L8_safety"] = ("M23 haptics policy=suppressed physical_pad_drivers=none" in log and not any(ra["judges"].values())
                      and ra["runner_exit"] == 0 and not ra["process_left"]
                      and rj.get("game_foreground_events") == 0 and rj.get("game_foreground_samples") == 0
                      and mb[0] == "armed" and mb[1]["session"] == run and mb[1]["plan_sha256"] == ra["plan_sha256"]
                      and ra["controlled"] is True and ra["session_end"]["cleared"] is True
                      and ra["marker_after"] == "none" and prot["before"] == prot["after"])
    det["safety"] = {"judges": ra["judges"], "foreground": (rj.get("game_foreground_events"),
                                                            rj.get("game_foreground_samples")),
                     "session_end": ra.get("session_end"),
                     "tx": tx, "snapshots": snaps}
    ok = all(v is True for v in L.values())
    res = {"L": L, "verdict": "RELOAD VERIFIED" if ok else "NOT PASSED", "details": det}
    (WORK / f"judgement_reload_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({"L": L, "verdict": res["verdict"], "consumption": det["consumption"], "L7": l7,
                      "D": D, "within": within, "tx_passes": det["tx_passes"]}, indent=1, default=str))
    return 0 if ok else 1


# --- phase 2: abnormal termination and recovery ------------------------------------------------------------------

def recover(tag):
    if not json.loads((WORK / "check.json").read_text())["pass"]:
        raise SystemExit("check did not pass")
    setup()
    return p4b.run(tag)


def judge_recover(tag):
    setup()
    p4b.judge(tag)
    j = json.loads((WORK / f"judgement_{tag}.json").read_text())
    Rp, det = j["R"], j["details"]
    C = json.loads((WORK / tag / "C" / "live.json").read_text()) if (WORK / tag / "C" / "live.json").is_file() else {}
    Cst = json.loads((WORK / tag / "C" / "states.json").read_text()) if (WORK / tag / "C").is_dir() else []
    ev = json.loads((WORK / tag / "evidence.json").read_text())
    R = {"R1_marker_ordering": Rp["R2_activation_ordering"],
         "R2_dual_activation": Rp["R3_functional_activation"],
         "R3_process_ownership": Rp["R1_session_ownership"],
         "R4_abnormal_termination": Rp["R4_abnormal_termination"],
         "R5_marker_persistence": Rp["R5_marker_persistence"],
         "R6_recovery_refusal": Rp["R6_next_launch_rejection"] and ev["C_plan"]["codes"] == {p5.MOD:
                                                                                           "STRUCTURAL_RECOVERY"},
         "R7_original_resources": (len(C.get("nodes", [])) == 143 and C.get("problems") == []
                                   and any(s.get("areas", {}).get("1", {}).get("length") == AREA for s in Cst
                                           if "invalid" not in s)),
         "R8_ordinary_mod": Rp["R7_nonstructural"],
         "R9_isolation_and_clear": Rp["R8_profile_isolation"] and Rp["R9_explicit_recovery"],
         "R10_production_desktop": Rp["R10_production_desktop"]}
    ok = not j["invalid"] and all(R.values())
    res = {"invalid": j["invalid"], "R": R, "verdict": "RECOVERY VERIFIED" if ok else
           ("INVALID" if j["invalid"] else "NOT PASSED"), "g5p4b_judge": Rp, "details": det}
    (WORK / f"judgement_recover_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("invalid", "R", "verdict")}, indent=1, default=str))
    return 0 if ok else 1


def main():
    a = sys.argv[1:]
    ok_tag = len(a) == 2 and re.fullmatch(r"[A-Za-z0-9-]{1,24}", a[1])
    if a == ["check"]:
        return check()
    if ok_tag and a[0] == "reload":
        return reload(a[1])
    if ok_tag and a[0] == "recover":
        return recover(a[1])
    if ok_tag and a[0] == "judge-reload":
        return judge_reload(a[1])
    if ok_tag and a[0] == "judge-recover":
        return judge_recover(a[1])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
