#!/usr/bin/env python3
"""E-478 (D-245) G5-P2b: lifecycle of the development-only structural transaction (intro_10 node-13 insertion,
G5-P1) across a genuine level exit, and the launcher-side structural-session recovery marker (tools/r3hd_mods.py
G5-P2b section, tools/play.ps1).

usage:
  g5p2b_lifecycle.py recovery    deterministic R1-R8 (private mods roots, real game data; no game started)
  g5p2b_lifecycle.py negtest     transaction reload cases (repeated opens, stale / tampered plans) through
                                 g5p1_tx_test.cpp, plus G5-P1 / G5-P2a negtests (no game started)
  g5p2b_lifecycle.py TAG         hidden lifecycle runs (development build): lc, lu
  g5p2b_lifecycle.py judge TAG   L1-L8
Outputs stay under private/work/e478/.

LIFECYCLE ROUTE (genuine game logic, no transition hack): the E-460 designer-default override "generator variable 5
= 6" (dsgvar_ab.role(), the same mod as E-465a's trans case) makes intro_10's flight generator take its own exit
branch (macro 3) to intro_15 about 62 s after intro_10 opens. Normal progression never returns to intro_10, so
same-process re-entry is not reachable without an artificial redirect: L5 is UNKNOWN by design. Repeated loading is
covered by separate processes (E-476 p1, E-477 q1 / q2: the same transaction applied identically in each).

PROSPECTIVE PROTOCOL (committed before any run)
Build: g5p1_dev_gate.py apply + tools\\build_incremental.bat; production restored afterwards.
Runs (m9_license_run.py: hidden, non-activating, muted, no physical pad, private user root, `--test-level
  intro_10`, no input, no captures, 140 s; block-8 snapshot at every change of the area table (E-465a model);
  generator sampled every 0.1 s while intro_10 is loaded; graph walked once after actor discovery):
  lc: plan = node-13 neutral insertion (g5p1 mod) + the lums-6 designer-default, compiled by resolve_all with
      session = the run name (the harness is the launcher: the marker must exist before the game starts and is
      ended by `structural-end` after the run, controlled = runner exit 0 and no r3hd_crash.txt); dev variable set.
  lu: plan = the lums-6 designer-default only (unmodified structure); same everything else.
Criteria:
  L1 initial load (lc): `G5P1 level-tx active` with the plan's id; `M36 grow size` intro_10.lvl 7661836 -> 7661948,
     intro_10.ptr 209068 -> 209140; the intro_10 area 7,661,944 bytes; live count 144, walk of 144 distinct nodes,
     the new node at index 14, node 13's arc -> new node.
  L2 consumption (lc): generator variable 8 = the new waypoint's address in >= 2 samples, entered only from node
     13's waypoint and left only for node 14's, >= 2 visits; never in lu.
  L3 level exit (lc and lu): a valid snapshot after intro_10's area disappears and before intro_15's appears with
     only fix loaded: 1 allocated / 1 free chunk, free 20,795,836 bytes, equal between lc and lu and to the snapshot
     with only fix loaded before intro_10 (no retained allocation: grown area, save table, `.ptr` temporaries and
     transit all released).
  L4 next-level integrity: after the transition lc's and lu's intro_15 snapshots are identical: 4 allocated / 1 free
     chunk, intro_15 area base and length (E-465a: 0x40F5F320, 8,474,196), transit length, save-table words, free
     bytes (E-465a: 12,234,744); every snapshot of both runs valid (walk exact); no `M36 grow` / `M33 mods served` line
     naming any intro_15 or transit file.
  L5 re-entry: UNKNOWN (not reachable by genuine progression; see above). Not judged as PASS.
  L6 repeated-load consistency: lc: exactly one `M33 mods state=active` and one `G5P1 level-tx active` line (the
     plan is verified once per process); grow reads only of intro_10.lvl / .ptr, all kind=tail; served files only
     those two; `negtest` (repeated opens in both orders, refused plans repeated, stale and tampered plans) passes.
  L7 recovery: `recovery` R1-R8 pass; and live: lc's marker existed (armed, the run's session, the plan's SHA-256)
     when the game started and is cleared after the controlled end; lu writes no marker.
  L8 safety: M21 / M22 / M23 0, haptics policy line, runner exit 0, no game process left, in both runs.
  Invalid (new tag): file hashes differ, intro_10 or intro_15 never loaded, generator not found, no fix-only snapshot.
  Classes: L1-L4 + L6-L8 PASS with L5 UNKNOWN = G5-P2b PARTIAL — RE-ENTRY UNVERIFIED (the brief's rule).
REVISION 1 (after run k1; k1 stays as judged: L2 FAIL, L1 / L3 / L4 / L6 / L7 / L8 PASS, L5 UNKNOWN):
  Cause: L2's ">= 2 visits" came from the looping route (G3b / E-476 / E-477, no exit mod). With variable 5 = 6 the
  generator flies one pass toward its exit: in k1 the control lu passes node 13 -> node 14 once in 59.7 s of samples
  and lc passes 13 -> N -> 14 once (the only node-13 departure). Revised L2, for fresh runs only: lc's passes
  13 -> N -> 14 >= 1 and equal to lu's 13 -> 14 passes; every lc departure from node 13's waypoint goes to N and every
  departure from N goes to node 14; variable 8 = N in >= 1 sample; never N in lu. Everything else unchanged. Fresh
  run: k2 (lc, lu).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))
import r3hd_mods as rm  # noqa: E402
import g3a_ab as g3a  # noqa: E402
import g3b_ab as g3b  # noqa: E402
import block8_probe as bp  # noqa: E402
import g5p1_pilot as p1  # noqa: E402

PREFIX = "e478"
WORK = ROOT / "private" / "work" / PREFIX
p1.WORK = WORK
LEVEL, ENV = p1.LEVEL, rm.STRUCT_ENV
RUNS = g3a.RUNS
SECONDS = 140
FIX_ONLY_FREE = 20795836


def lums6():
    import dsgvar_ab as d
    return dict(d.role()[0], value=6)


def fresh(name):
    return p1.fresh(name)


def cli(paths, *args):
    """The mod tool exactly as play.ps1 invokes it (JSON on stdout)."""
    r = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), *args, "--json", "--mods-root", str(paths["mods"]),
                        "--cache", str(paths["cache"]), "--game-dir", str(paths["game"])], capture_output=True,
                       text=True, env=dict(os.environ))
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"result": "error", "stderr": r.stderr[-400:]}


# --- deterministic recovery tests ----------------------------------------------------------------------------

def recovery():
    res, det = {}, {}
    marker = lambda paths: rm.structural_marker_path(paths)   # noqa: E731

    def setup(name, structural=True, fixed=True):
        paths = fresh(name)
        with p1.dev_env():
            if structural:
                p1.install(paths, "s.13", [p1.igm("neutral")])
            if fixed:
                p1.install(paths, "w.13", [p1.waypoint13()])
        return paths

    def plan(paths, session):
        with p1.dev_env():
            return cli(paths, "plan", "--session", session)
    # R1 normal exit
    pa = setup("r1")
    r = plan(pa, "sess-r1")
    st, d = rm.read_structural_marker(pa)
    plan_sha = hashlib.sha256(Path(r["plan"]).read_bytes()).hexdigest() if r.get("plan") else None
    res["R1_marker_armed_with_plan"] = (r.get("result") == "ok" and r["active"] == ["s.13", "w.13"] and st == "armed"
                                        and d["session"] == "sess-r1" and d["plan_sha256"] == plan_sha
                                        and r["structural_marker"]["plan_sha256"] == plan_sha
                                        and "level-tx" in Path(r["plan"]).read_text(encoding="utf-8"))
    e = cli(pa, "structural-end", "--session", "sess-r1", "--plan-sha", plan_sha, "--controlled", "yes")
    res["R1_controlled_end_clears"] = e.get("cleared") is True and not marker(pa).exists()
    # R2 abnormal termination (simulated: the launcher reports a non-controlled end, or never calls structural-end)
    pb = setup("r2")
    r = plan(pb, "sess-r2")
    sha = r["structural_marker"]["plan_sha256"]
    before = marker(pb).read_bytes()
    e = cli(pb, "structural-end", "--session", "sess-r2", "--plan-sha", sha, "--controlled", "no")
    res["R2_abnormal_end_keeps_marker"] = e.get("cleared") is False and marker(pb).read_bytes() == before
    # R3 next launch refuses structural, keeps others, keeps the marker
    r3 = plan(pb, "sess-r2-next")
    codes = {m["id"]: m.get("code") for m in r3.get("mods", [])}
    res["R3_next_launch_refuses_structural"] = (codes.get("s.13") == "STRUCTURAL_RECOVERY" and r3["active"] == ["w.13"]
                                                and "level-tx" not in Path(r3["plan"]).read_text(encoding="utf-8")
                                                and r3.get("structural_recovery") == "armed"
                                                and marker(pb).read_bytes() == before)
    # the explicit re-authorization re-enables it (and arms a new marker)
    c = cli(pb, "structural-recovery", "clear")
    r3b = plan(pb, "sess-r2-reauth")
    res["R3_explicit_reauthorization"] = (c.get("cleared") is True and r3b["active"] == ["s.13", "w.13"]
                                          and rm.read_structural_marker(pb)[1]["session"] == "sess-r2-reauth")
    # R4 scope: another home is unaffected; foreign session / plan cannot clear
    pc = setup("r4_other")
    rc = plan(pc, "sess-r4")
    res["R4_other_home_unaffected"] = rc["active"] == ["s.13", "w.13"] and rm.read_structural_marker(pb)[0] == "armed"
    sha_c = rc["structural_marker"]["plan_sha256"]
    e1 = cli(pc, "structural-end", "--session", "sess-r2-reauth", "--plan-sha", sha_c, "--controlled", "yes")
    e2 = cli(pc, "structural-end", "--session", "sess-r4", "--plan-sha", "0" * 64, "--controlled", "yes")
    res["R4_foreign_session_or_plan_cannot_clear"] = (e1.get("cleared") is False and e2.get("cleared") is False
                                                      and rm.read_structural_marker(pc)[0] == "armed"
                                                      and rm.read_structural_marker(pb)[0] == "armed")
    e3 = cli(pc, "structural-end", "--session", "sess-r4", "--plan-sha", sha_c, "--controlled", "yes")
    res["R4_own_session_clears_only_own_home"] = (e3.get("cleared") is True and rm.read_structural_marker(pc)[0] == "none"
                                                  and rm.read_structural_marker(pb)[0] == "armed")
    # R5 stale or malformed markers fail closed, are not deleted, saves untouched
    r5 = {}
    for label, writer in (("garbage", lambda p: p.write_bytes(b"\x00not json")),
                          ("empty", lambda p: p.write_bytes(b"")),
                          ("wrong_schema", lambda p: p.write_text(json.dumps({"schema": 9, "session": "x",
                                                                              "plan_sha256": "0" * 64, "mods": [],
                                                                              "levels": []}))),
                          ("bad_session", lambda p: p.write_text(json.dumps({"schema": 1, "session": "../x",
                                                                             "plan_sha256": "0" * 64, "mods": [],
                                                                             "levels": []}))),
                          ("directory", lambda p: p.mkdir())):
        pm = setup(f"r5_{label}")
        save = pm["_dir"] / "user" / "profile" / "save.bin"
        save.parent.mkdir(parents=True)
        save.write_bytes(b"SAVE" * 16)
        pm["mods"].mkdir(parents=True, exist_ok=True)
        writer(marker(pm))
        snap = marker(pm).read_bytes() if marker(pm).is_file() else "dir"
        r = plan(pm, f"sess-r5-{label}")
        codes = {m["id"]: m.get("code") for m in r.get("mods", [])}
        e = cli(pm, "structural-end", "--session", f"sess-r5-{label}", "--plan-sha", "0" * 64, "--controlled", "yes")
        ok = (codes.get("s.13") == "STRUCTURAL_RECOVERY" and r["active"] == ["w.13"]
              and r.get("structural_recovery") == "malformed" and e.get("cleared") is False
              and (marker(pm).read_bytes() if marker(pm).is_file() else "dir") == snap
              and save.read_bytes() == b"SAVE" * 16)
        r5[label] = ok
        res[f"R5_malformed_{label}"] = ok
    # R6 marker write failure: the plan is rewritten without the structural mod before any launch
    pf = setup("r6")
    real_fsync = os.fsync

    def failing_fsync(fd):
        raise OSError("simulated fsync failure")
    os.fsync = failing_fsync
    try:
        with p1.dev_env():
            r6 = rm.resolve_all(pf, write_plan=pf["cache"], session="sess-r6")
    finally:
        os.fsync = real_fsync
    codes = {m["id"]: m.get("code") for m in r6["mods"]}
    res["R6_write_failure_refuses_structural"] = (codes.get("s.13") == "STRUCTURAL_MARKER" and r6["active"] == ["w.13"]
                                                  and "level-tx" not in Path(r6["plan"]).read_text(encoding="utf-8")
                                                  and rm.read_structural_marker(pf)[0] == "none"
                                                  and not list(pf["mods"].glob(f"{rm.STRUCT_MARKER}.tmp-*")))
    # R7 no structural mod: no marker, the same plan as without a session, recovery state none
    pn = setup("r7", structural=False)
    r7a = plan(pn, "sess-r7")
    t_a = Path(r7a["plan"]).read_text(encoding="utf-8")
    r7b = cli(pn, "plan")
    t_b = Path(r7b["plan"]).read_text(encoding="utf-8")
    strip = lambda t: [ln for ln in t.splitlines() if not ln.startswith("#")]   # noqa: E731
    e = cli(pn, "structural-end", "--session", "sess-r7", "--plan-sha", "0" * 64, "--controlled", "yes")
    res["R7_nonstructural_unchanged"] = (r7a["active"] == ["w.13"] and "structural_marker" not in r7a
                                         and r7a.get("structural_recovery") == "none" and strip(t_a) == strip(t_b)
                                         and not marker(pn).exists() and e.get("cleared") is False)
    # R8 production isolation: without the development opt-in no structural mod applies and nothing is armed
    pp = setup("r8")
    with p1.dev_env(None):
        r8 = cli(pp, "plan", "--session", "sess-r8")
    codes = {m["id"]: m.get("code") for m in r8.get("mods", [])}
    ps = (TOOLS / "play.ps1").read_text(encoding="utf-8")
    # G5-P4b (D-248): the plan call and the structural end moved into play.ps1's own functions Invoke-R3hdModsPlan /
    # Complete-R3hdStructuralSession (defined near the top); the order is checked at their call sites, and the
    # definitions must still pass the session and call structural-end (with the crash-record check)
    i_plan, i_start, i_wait, i_end = (ps.find("$modsOut = Invoke-R3hdModsPlan"), ps.find("$process = Start-Process"),
                                      ps.find("$exitCode = $process.ExitCode"),
                                      ps.find("Complete-R3hdStructuralSession $python"))
    i_t, i_c = ps.find("function Test-R3hdOrderlyExit"), ps.find("function Complete-R3hdStructuralSession")
    defs_ok = ("'--session', $Stamp" in ps[:i_t] and "r3hd_crash.txt" in ps[i_t:i_c]
               and "structural-end --json" in ps[i_c:i_c + 1200])
    res["R8_production_compiler_arms_nothing"] = (codes.get("s.13") == "UNSUPPORTED" and r8["active"] == ["w.13"]
                                                  and not marker(pp).exists())
    res["R8_play_ps1_order"] = (0 < i_t < i_c < i_plan < i_start < i_wait < i_end and "if (-not $DryRun)" in ps
                                and defs_ok and ENV not in ps)
    out = {"checks": res, "pass": all(res.values()), "details": det}
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "recovery.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"failed": [k for k, x in res.items() if not x], "passed": sum(res.values()),
                      "total": len(res), "pass": out["pass"]}, indent=1))
    return 0 if out["pass"] else 1


# --- transaction reload tests (deterministic) -------------------------------------------------------------------

def negtest():
    import g5p2a_pilot as p2a
    p2a.WORK = WORK
    p2a.p1.WORK = WORK
    rc = p2a.negtest()      # G5-P1 30 + 5 and G5-P2a 12 + 2 (rebuilds the test binaries with the repeat-capable test)
    nd = WORK / "negtest"
    data, ptr = g3a.files()
    _, text, _ = p1.compile_plan("reload_valid", [("g5p1.neutral", [p1.igm("neutral")])])
    base = p1.parse_plan(text)
    V = (nd / "valid_lvl.bin", nd / "valid_ptr.bin")
    O = ("-", "-")
    stale = nd / "stale"
    stale.mkdir(exist_ok=True)
    variants = {}
    for label, mut in (("lvl_byte", "lvl"), ("ptr_byte", "ptr"), ("lvl_size", "lvl+")):
        d = stale / label
        d.mkdir(exist_ok=True)
        lv, pv = bytearray(data), bytearray(ptr)
        if mut == "lvl":
            lv[0x200] ^= 1
        elif mut == "ptr":
            pv[8] ^= 1
        else:
            lv += b"\0\0\0\0"
        (d / "intro_10.lvl").write_bytes(bytes(lv))
        (d / "intro_10.ptr").write_bytes(bytes(pv))
        m = json.loads(json.dumps(base))
        for f in m["files"]:
            f["path"] = str(d / Path(f["path"]).name)
        p = nd / f"plan_stale_{label}.txt"
        p.write_text(p1.emit(m), encoding="utf-8")
        variants[label] = (p, d)
    lvl_p, ptr_p = str(g3a.LVL), str(g3a.PTR)
    valid = nd / "plan_valid.txt"
    cases = [("repeated opens lvl,ptr,lvl,ptr,ptr", valid, LEVEL, "active", "lvl,ptr,lvl,ptr,ptr", lvl_p, ptr_p, V),
             ("repeated opens ptr,ptr,lvl,lvl", valid, LEVEL, "active", "ptr,ptr,lvl,lvl", lvl_p, ptr_p, V),
             ("refused plan opened repeatedly", valid, "-", "level_tx_not_enabled", "ptr,lvl,ptr,lvl", lvl_p, ptr_p, O)]
    for label, (p, d) in variants.items():
        want = "file_size" if label == "lvl_size" else "tx_identity"
        cases.append((f"stale plan ({label} changed after compile)", p, LEVEL, want, "ptr,lvl,lvl",
                      str(d / "intro_10.lvl"), str(d / "intro_10.ptr"), O))
    out = {}
    for kind in ("dev", "prod"):
        exe = nd / f"g5p1_tx_test_{kind}.exe"
        cs = cases if kind == "dev" else [("production: repeated opens of a transaction plan", valid, LEVEL,
                                           "unknown_record", "lvl,ptr,lvl", lvl_p, ptr_p, O)]
        cf = nd / f"cases_reload_{kind}.tsv"
        cf.write_text("".join("\t".join([n, str(p), env, want, order, lv, pv, str(e[0]), str(e[1])]) + "\n"
                              for n, p, env, want, order, lv, pv, e in cs), encoding="utf-8")
        r = subprocess.run([str(exe), str(cf)], capture_output=True, text=True, timeout=600)
        (nd / f"result_reload_{kind}.txt").write_text(r.stdout + r.stderr)
        print(r.stdout)
        out[kind] = {"exit": r.returncode, "summary": r.stdout.strip().splitlines()[-1] if r.stdout else ""}
    ok = rc == 0 and all(v["exit"] == 0 for v in out.values())
    out["p1_p2a_rc"] = rc
    (nd / "summary_p2b.json").write_text(json.dumps(out, indent=1) + "\n")
    shutil.rmtree(stale)   # private copies of the game files: not kept
    print(json.dumps(out), "NEGTEST_P2B", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# --- hidden lifecycle runs ---------------------------------------------------------------------------------------

def run_case(tag, case):
    from m5_live import Actor, Process
    data, ptr = g3a.files()
    work = WORK / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_E465_TEST_GROW", "R3HD_G3A_TEST_GROW", ENV):
        env.pop(k, None)
    row = {"case": case, "run": run}
    mods = [("g5p1.neutral", [p1.igm("neutral")])] if case == "lc" else []
    mods.append(("e478.lums-6", [lums6()]))
    paths = fresh(f"run_{tag}_{case}")
    with p1.dev_env():
        for mid, ov in mods:
            p1.install(paths, mid, ov)
        res = rm.resolve_all(paths, write_plan=paths["cache"], session=run)
    want_active = [m for m, _ in mods]
    if res["active"] != want_active:
        raise SystemExit(f"plan: {res['mods']}")
    plan = paths["cache"] / rm.PLAN_NAME
    shutil.copyfile(plan, work / "plan_copy.txt")
    row["plan_sha256"] = hashlib.sha256(plan.read_bytes()).hexdigest()
    row["marker_before_start"] = rm.read_structural_marker(paths)
    env["R3HD_MODS_PLAN"] = str(plan)
    if case == "lc":
        env[ENV] = LEVEL
    (work / "steps.txt").write_text(f"wait {SECONDS - 8}\n", encoding="ascii")
    states, samples, live = [], [], {}
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(SECONDS), "--play", "--test-level",
                                 "intro_10", "--user-root", run], cwd=ROOT, env=env, stdout=log,
                                stderr=subprocess.STDOUT)
        t0 = time.monotonic()
        base = pid = None
        while time.monotonic() < t0 + 60 and game.poll() is None and (base is None or pid is None):
            lp, pj = RUNS / run / "runtime.log", RUNS / run / "process.json"
            if base is None and lp.is_file():
                mm = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", lp.read_text(errors="replace"))
                base = mm.group(1) if mm else None
            if pid is None and pj.is_file():
                try:
                    pid = json.loads(pj.read_text(encoding="utf-8-sig"))["pid"]
                except Exception:
                    pid = None
            time.sleep(0.02)
        if base is None or pid is None:
            row["error"] = "process not found"
        else:
            p = Process(pid, int(base, 16))
            last, t_end, gen, ab, next_sample, discovered = "none", t0 + SECONDS - 5, None, None, 0.0, False

            def rd(a):
                w = p.words(a, 1)
                if not w:
                    raise ValueError(f"read {a:#x}")
                return w[0]
            while time.monotonic() < t_end and p.running():
                ar = bp.areas(p)
                key = json.dumps({k: (v["base"], v["end"]) for k, v in (ar or {}).items()})
                if ar is not None and key != last:
                    last = key
                    s = bp.snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="areas_changed", area_keys=sorted(ar))
                    states.append(s)
                    a1 = s.get("areas", {}).get(1)
                    if a1 and a1["length"] in (g3a.AREA, g3a.AREA + g3b.N) and ab is None:
                        ab = int(a1["base"], 16)
                    elif ab is not None and (not a1 or int(a1["base"], 16) != ab) and gen is not None:
                        gen = None   # intro_10 left: the generator is gone
                        row["left_intro_10_t"] = s["t"]
                if ab is not None and not discovered:
                    discovered = True
                    disc = work / "discovery.json"
                    q = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc),
                                        "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
                    try:
                        nodes, prob, hdr = g3b.walk_null(rd, ab + g3b.GRAPH - 4)
                        al = rd(ab + g3b.NODE13 - 4 + 0x18)
                        live = {"t": round(time.monotonic() - t0, 3), "nodes": nodes, "problems": prob, "header": hdr,
                                "arc13": {"count": rd(al + 8), "target": rd(rd(al) + 0xC)},
                                "changed": [rd(ab + s_ - 4) for s_ in list(g3b.CHANGED) + [g3b.COUNT_AT]]}
                    except Exception as x:
                        live = {"error": repr(x)}
                    for a in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if q.returncode == 0 else []):
                        try:
                            act = Actor(p, int(a["so"], 16))
                        except Exception:
                            continue
                        if act.model == g3a.GEN and act.mind:
                            gen = act
                            break
                    if gen is None:
                        row["generator"] = "not found"
                now = time.monotonic()
                if gen is not None and now >= next_sample:
                    try:
                        v = gen.dsg()
                        samples.append({"t": round(now - t0, 3), "v8": g3a.u32(*v[8]),
                                        "v10": struct.unpack_from(">3f", *v[10])})
                    except Exception as x:
                        row["sampling_stopped"] = type(x).__name__
                        gen = None
                    next_sample = now + 0.1
                time.sleep(0.005)
            if p.running():
                s = bp.snapshot(p)
                s.update(t=round(time.monotonic() - t0, 3), state="final", area_keys=sorted(bp.areas(p) or {}))
                states.append(s)
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and g3a.alive(pid))
    # the harness is the launcher: end the structural session (controlled = runner exit 0 and no crash report)
    controlled = row["runner_exit"] == 0 and not (RUNS / run / "r3hd_crash.txt").exists()
    row["controlled"] = controlled
    if row["marker_before_start"][0] == "armed":
        row["session_end"] = rm.end_structural_session(paths, run, row["plan_sha256"], controlled)
    row["marker_after"] = rm.read_structural_marker(paths)[0]
    for name, obj in (("states", states), ("samples", samples), ("live", live), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1, default=str) + "\n")
    return row


def run(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    g3b.N = 112
    for case in ("lc", "lu"):
        print(json.dumps(run_case(tag, case), default=str), flush=True)
    return 0


def judge(tag):
    out, det = {}, {}
    for case in ("lc", "lu"):
        w = WORK / tag / case
        r = json.loads((w / "row.json").read_text())
        for k in ("states", "samples", "live"):
            r[k] = json.loads((w / f"{k}.json").read_text())
        run_ = r["run"]
        log = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / run_).glob("runtime*.log")))
        r["log"] = log
        r["judges"] = {t: subprocess.run([sys.executable, str(TOOLS / t), "--run", run_], cwd=ROOT,
                                         capture_output=True, text=True).returncode
                       for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py")}
        out[case] = r
    lc, lu = out["lc"], out["lu"]

    def phases(r):
        st = r["states"]
        valid = [x for x in st if "invalid" not in x]
        i0 = next((i for i, x in enumerate(st) if "invalid" not in x), None)
        walk_ok = i0 is not None and not any("invalid" in x for x in st[i0:])
        fix_before = next((x for x in valid if set(x["areas"]) == {"0"}), None)
        i10 = next((i for i, x in enumerate(valid) if "1" in x["areas"]
                    and x["areas"]["1"]["base"] == "0x40f5509c"), None)
        fix_after = next((x for x in valid[i10 + 1:] if set(x["areas"]) == {"0"}), None) if i10 is not None else None
        i15 = next((x for x in valid if "1" in x["areas"] and x["areas"]["1"]["base"] != "0x40f5509c"), None)
        return {"walk_ok": walk_ok, "fix_before": fix_before, "intro10": valid[i10] if i10 is not None else None,
                "fix_after": fix_after, "intro15": i15}
    ph = {c: phases(out[c]) for c in out}
    invalid = [c for c in out if out[c].get("error") or not ph[c]["intro10"] or not ph[c]["intro15"]
               or not ph[c]["fix_after"]] + (["lc:generator"] if lc.get("generator") else [])
    L = {}
    tx = re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", lc["log"])
    ptx = p1.parse_plan((WORK / tag / "lc" / "plan_copy.txt").read_text(encoding="utf-8"))["txs"]
    want_tx = [tuple(ptx[0].split(" ")[2:5])] if ptx else None
    grow = sorted(set(re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", lc["log"])))
    lv = lc["live"]
    ab = 0x40F5509C
    i10 = ph["lc"]["intro10"]
    L["L1_initial_load"] = bool(
        [tuple(x) for x in tx] == want_tx and grow == [("intro_10.lvl", "7661836", "7661948"),
                                                       ("intro_10.ptr", "209068", "209140")]
        and i10 and i10["areas"]["1"]["length"] == g3a.AREA + 112 and lv.get("problems") == []
        and len(lv.get("nodes", [])) == 144 == len(set(lv["nodes"])) and lv["header"]["count"] == 144
        and lv["nodes"][14] == ab + g3b.FN - 4 and lv["arc13"] == {"count": 1, "target": ab + g3b.FN - 4})
    wn, w13, w14 = ab + g3b.FW - 4, ab + g3b.WP13 - 4, ab + g3b.WP14 - 4

    def visits(r):
        sm = r["samples"]
        at = [x for x in sm if x["v8"] == wn]
        ins = [(sm[i - 1]["v8"], sm[i]["v8"]) for i in range(1, len(sm)) if sm[i]["v8"] != sm[i - 1]["v8"]]
        into = [a for a, b in ins if b == wn]
        outof = [b for a, b in ins if a == wn]
        return {"samples": len(at), "into": len(into), "into_from_13": sum(a == w13 for a in into),
                "out": len(outof), "out_to_14": sum(b == w14 for b in outof), "sampled": len(sm),
                "span": round(sm[-1]["t"] - sm[0]["t"], 1) if sm else 0}
    vc, vu = visits(lc), visits(lu)
    det["visits"] = {"lc": vc, "lu": vu}
    def passes(r, a_, b_):
        seq = []
        for x in r["samples"]:
            if not seq or seq[-1] != x["v8"]:
                seq.append(x["v8"])
        return seq
    sc, su = passes(lc, 0, 0), passes(lu, 0, 0)
    lc_dep13 = [b for a, b in zip(sc, sc[1:]) if a == w13]
    lc_depN = [b for a, b in zip(sc, sc[1:]) if a == wn]
    lu_13_14 = sum(1 for a, b in zip(su, su[1:]) if a == w13 and b == w14)
    lc_13_N_14 = sum(1 for i in range(len(sc) - 2) if sc[i] == w13 and sc[i + 1] == wn and sc[i + 2] == w14)
    det["passes"] = {"lc_13_N_14": lc_13_N_14, "lu_13_14": lu_13_14, "lc_departures_13": len(lc_dep13),
                     "lc_departures_N": len(lc_depN)}
    L["L2_consumption"] = (lc_13_N_14 >= 1 and lc_13_N_14 == lu_13_14 and all(b == wn for b in lc_dep13)
                           and all(b == w14 for b in lc_depN) and vc["samples"] >= 1 and vu["samples"] == 0)   # rev. 1

    def brief(x):
        return None if not x else {"free": x["free_bytes"], "alloc": x["allocated_chunks"], "free_chunks": x["free_chunks"],
                                   "largest": x["largest_free"],
                                   "areas": {k: (v["base"], v["length"], v.get("save_words")) for k, v in x["areas"].items()}}
    det["phases"] = {c: {k: (brief(v) if isinstance(v, dict) else v) for k, v in ph[c].items()} for c in ph}
    det["phase_t"] = {c: {k: v.get("t") for k, v in ph[c].items() if isinstance(v, dict)} for c in ph}
    fa = {c: brief(ph[c]["fix_after"]) for c in ph}
    fb = {c: brief(ph[c]["fix_before"]) for c in ph}
    L["L3_level_exit"] = (not invalid and fa["lc"] == fa["lu"] == fb["lc"] == fb["lu"]
                          and fa["lc"]["free"] == FIX_ONLY_FREE and fa["lc"]["alloc"] == 1
                          and fa["lc"]["free_chunks"] == 1)
    i15 = {c: brief(ph[c]["intro15"]) for c in ph}
    other = re.findall(r"M36 grow (?:size|read) file=(\S+)", lc["log"]) + re.findall(r"M33 mods served mod=\S+ file=(\S+)",
                                                                                    lc["log"])
    L["L4_next_level"] = (not invalid and i15["lc"] == i15["lu"] and i15["lc"]["alloc"] == 4
                          and i15["lc"]["free_chunks"] == 1 and all(ph[c]["walk_ok"] for c in ph)
                          and set(other) <= {"intro_10.lvl", "intro_10.ptr"})
    L["L5_re_entry"] = "UNKNOWN"
    reads = re.findall(r"M36 grow read file=(\S+) offset=\d+ length=\d+ host=\d+ served=\d+ kind=(\S+)", lc["log"])
    neg = json.loads((WORK / "negtest" / "summary_p2b.json").read_text())
    L["L6_repeated_load"] = (lc["log"].count("M33 mods state=active") == 1 and len(tx) == 1
                             and {f for f, _ in reads} == {"intro_10.lvl", "intro_10.ptr"}
                             and all(k == "tail" for _, k in reads)
                             and sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", lc["log"])))
                             == ["intro_10.lvl", "intro_10.ptr"]
                             and neg["dev"]["exit"] == 0 and neg["prod"]["exit"] == 0 and neg["p1_p2a_rc"] == 0)
    det["grow_reads"] = reads
    rec = json.loads((WORK / "recovery.json").read_text())
    mb = lc["marker_before_start"]
    L["L7_recovery"] = (rec["pass"] and mb[0] == "armed" and mb[1]["session"] == lc["run"]
                        and mb[1]["plan_sha256"] == lc["plan_sha256"] and lc["controlled"] is True
                        and lc["session_end"]["cleared"] is True and lc["marker_after"] == "none"
                        and lu["marker_before_start"][0] == "none" and lu["marker_after"] == "none")
    L["L8_safety"] = all("M23 haptics policy=suppressed physical_pad_drivers=none" in r["log"]
                         and not any(r["judges"].values()) and r["runner_exit"] == 0 and not r["process_left"]
                         for r in out.values())
    passed = [k for k, v in L.items() if v is True]
    verdict = ("G5-P2b PARTIAL — RE-ENTRY UNVERIFIED" if not invalid and len(passed) == 7 else "NOT PASSED")
    res = {"invalid": invalid, "L": L, "verdict": verdict, "details": det, "left_intro_10_t": lc.get("left_intro_10_t"),
           "judges": {c: r["judges"] for c, r in out.items()}}
    (WORK / f"judgement_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("invalid", "L", "verdict")}, indent=1))
    print(json.dumps(det["phases"], indent=0)[:3000])
    return 0 if verdict.startswith("G5-P2b") else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "recovery":
        return recovery()
    if len(sys.argv) > 1 and sys.argv[1] == "negtest":
        return negtest()
    if len(sys.argv) > 2 and sys.argv[1] == "judge":
        return judge(sys.argv[2])
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]{1,24}", a.tag):
        ap.error("bad tag")
    return run(a.tag)


if __name__ == "__main__":
    sys.exit(main())
