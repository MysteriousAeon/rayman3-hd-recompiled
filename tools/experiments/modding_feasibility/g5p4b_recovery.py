#!/usr/bin/env python3
"""E-481 (D-248) G5-P4b: structural-session recovery after a real abnormal termination of a test-owned game process.

usage:
  g5p4b_recovery.py preflight    deterministic: orderly-exit decision, marker lifecycle through the launcher functions
                                 (tools\\play.ps1, loaded by g5p4b_lifecycle.ps1), synthetic abnormal child, concurrency,
                                 profile-scoped clear, production refusal, play.ps1 -DryRun; plus G5-P2b recovery R1-R8
  g5p4b_recovery.py TAG          phases A (armed launch, consumption, forced termination), C (recovery launch),
                                 D (explicit clear, re-authorization); development build
  g5p4b_recovery.py judge TAG    R1-R10
Outputs stay under private/work/e481/ (disposable mods roots, plans, markers; game profiles under m9_profiles/<run>).

LAUNCHER ROUTE. tools\\play.ps1 starts a visible window and refuses agent shells, so it is not run. Its own three
functions -- Invoke-R3hdModsPlan (the mod tool's `plan` with the session id: compiles the plan and arms the marker
before any game start), Test-R3hdOrderlyExit and Complete-R3hdStructuralSession (the post-exit decision and
`structural-end`) -- are loaded from play.ps1 by the PowerShell parser and called unchanged (g5p4b_lifecycle.ps1). Only
the window launch differs: the game is started by the established hidden runner (m9_license_run.py ->
run_milestone6.ps1: hidden, non-activating, guest-scoped input, no captures), which records the game's exit code in
run.json. So the marker, plan and exit-handling code of the launcher are verified; play.ps1's visible Start-Process
line is not.

FIX BEFORE TESTING (D-248): play.ps1 cleared the marker on exit code 0 without a crash record. Now an orderly exit also
needs the runtime's orderly-shutdown line in the session log ('Title terminated; hard-exiting process.' from the
window-close path, 'Execution complete' from a guest-initiated exit); a process terminated from outside writes neither.

PROSPECTIVE PROTOCOL (committed before any forced termination)
Build: g5p1_dev_gate.py apply + tools\\build_incremental.bat (development; production restored afterwards).
Mods root RA (disposable): g5p1.neutral (intro_10 node-13 insertion, structural) + e478.lums-6 (designer default,
  not structural; makes intro_10 exit to intro_15 about 62 s after it opens). Mods root RB (disposable): g5p1.neutral
  only, never planned for a launch (isolation witness). R3HD_DEV_STRUCTURAL_TX=intro_10 in every phase.
A: Invoke-R3hdModsPlan(RA, stamp e481_TAG_A); hidden run e481_TAG_A (`--test-level intro_10`, no input, up to 140 s)
   with that plan. Read-only observation as E-478 (block-8 snapshots, graph walk, generator variable 8 at 0.1 s).
   After the first 13 -> N -> 14 pass (+3 s), and no later than 45 s after intro_10's area appears: the game pid from
   process.json is checked (r3hd.exe, the runner's exe path, command line containing this run's
   `--log_file=...\\e481_TAG_A\\runtime.log`, created after the harness started the runner, parent's parent = the
   runner process the harness started) and only that pid is terminated (Stop-Process, re-verified creation time). If
   ownership does not match, nothing is terminated (BLOCKED). After the runner ends: Complete-R3hdStructuralSession
   (RA, stamp A, the plan's marker, the run directory, run.json's exit code).
C: Invoke-R3hdModsPlan(RA, stamp e481_TAG_C); hidden run e481_TAG_C (110 s, same options) with that plan; nothing
   ends or clears the marker (C arms none).
D: `r3hd_mods.py structural-recovery clear` on RA; Invoke-R3hdModsPlan(RA, dry run) and (RA, stamp e481_TAG_D); then
   `structural-recovery clear` again (cleanup of the disposable root).
Criteria:
  R1 session ownership: A's marker names session e481_TAG_A and the SHA-256 of RA's plan file; the plan is the one in
     the run's R3HD_MODS_PLAN; the terminated pid passed every ownership check.
  R2 activation ordering: the marker file's mtime < the game process's creation time < the first `M36 grow size`
     line naming intro_10 (log time); `G5P1 level-tx active` and `G5P3 tx snapshot` x2 present in A.
  R3 functional activation (A, before termination): live walk 144 distinct nodes, no problems, N at index 14, node
     13's arc -> N; >= 1 pass 13 -> N -> 14 in generator variable 8 before the termination time.
  R4 abnormal termination: kill result true for exactly that pid; run.json exit_code != 0; runner observed the end
     (run.json finished before the planned 140 s); no process with that pid and creation time afterwards and no
     r3hd.exe whose command line names an e481 run; Test-R3hdOrderlyExit(A) controlled = false with orderly_line
     null; and with exit code 0 substituted, still controlled = false.
  R5 marker persistence: Complete-R3hdStructuralSession returned cleared = false; the marker file is byte-identical
     before the launch, after the termination and after Complete.
  R6 next-launch rejection: C's plan output: g5p1.neutral not applied with code STRUCTURAL_RECOVERY,
     structural_recovery = armed, no structural_marker; the plan file has no `level-tx` / `tx-file` record; C's log:
     `M33 mods state=active`, no `G5P1 level-tx`, no `G5P3`, no `M36 grow` line; live intro_10 walk 143 nodes, area
     length 7,661,832; the marker byte-identical after C.
  R7 nonstructural compatibility: e478.lums-6 active in A's and C's plans; C's log serves it in intro_10.lvl (`M33
     mods served mod=e478.lums-6 file=intro_10.lvl`); C leaves intro_10 for intro_15 (an area change to intro_15's
     base 0x40F5F320) within the run.
  R8 profile isolation: RB has no marker before A, after A, after C and after D; RB's dry-run plan lists g5p1.neutral
     active after C; preflight's profile-scoped clear case passes.
  R9 explicit recovery: after `clear`, RA has no marker; the dry run lists g5p1.neutral active; the stamp-D plan
     activates it (level-tx in the plan) and arms a marker naming e481_TAG_D; the final clear removes it.
  R10 production and desktop safety: preflight passed (production header refuses the intro_10 transaction:
     unknown_record); intro_10.lvl / .ptr SHA-256 unchanged before / after; the registered save entries' and the
     default play profile's file hashes unchanged; A and C: initial foreground unchanged and no foreground events
     (run.json), M21 / M22 / M23 0, no game process left; C runner exit 0.
  Invalid (fresh tag, protocol unchanged): no 13 -> N -> 14 pass within 45 s (nothing terminated), intro_10 never
  loaded, runner failure before the game starts.
  Class: R1-R10 PASS = G5-P4b VERIFIED — ABNORMAL-TERMINATION RECOVERY.
REVISION 1 (after run k1; k1 stays as judged under the original R10: R1-R9 PASS, R10 FAIL, NOT PASSED):
  Cause: R10's "initial foreground unchanged and no foreground events" counts every window change on the desktop. In
  k1's phase C all 15 events were other applications of the person at the desktop (Discord, steamwebhelper, ShareX,
  explorer); the game's own foreground events and samples were 0 in A and C (it never took focus), M21 / M22 / M23 0.
  Revised R10 desktop part, for fresh runs only: in A and C run.json game_foreground_events = 0 and
  game_foreground_samples = 0 (the game never foreground), monitor hook ready and stopped cleanly, no foreground
  event naming r3hd; everything else in R10 and R1-R9 unchanged. Fresh run: k2 (a new forced termination of a new
  test-owned process; the k1 evidence is kept).
"""
ORIGINAL_R10_TAGS = {"k1"}
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
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
import g5p2b_lifecycle as p2b  # noqa: E402

PREFIX = "e481"
WORK = ROOT / "private" / "work" / PREFIX
p1.WORK = WORK
RUNS = g3a.RUNS
GAME = g3a.GAME
EXE = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release" / "r3hd.exe"
PS1 = HERE / "g5p4b_lifecycle.ps1"
ENV = rm.STRUCT_ENV
INTRO15_BASE = 0x40F5F320
# G5-P5b (E-483): the structural mod, its grown area length and its insertion sites (file offsets of the predecessor's
# waypoint, the new waypoint and the successor's waypoint). Defaults = G5-P4b's node-13 insertion; g5p5b_lifecycle.py
# sets the dual mod. The kill waits for a pass through every site.
STRUCT_ID = "g5p1.neutral"
STRUCT_OV = lambda: [p1.igm("neutral")]  # noqa: E731
GROWN_AREA = g3a.AREA + 112


def sites():
    return [(g3b.WP13, g3b.FW, g3b.WP14)]


GROWN_NODES = 144


def new_nodes():
    """[(walk index, new node's file offset)] of the inserted nodes (default: node 13's, index 14)."""
    return [(14, g3b.FN)]


# G6-P1b (E-485): optional observation hooks (None = the graph walk, variable-8 sample and site-pass kill trigger
# above, unchanged). OBSERVE(rd, p, ab) -> dict replaces the live graph walk; SAMPLER(p, ab) -> callable(gen, t) ->
# dict replaces the 0.1 s sample (it must still carry "v8"); KILL_READY(samples) -> bool replaces "every site passed"
# as the event the termination waits 3 s after (the 45 s limit and every ownership check are unchanged).
OBSERVE = None
SAMPLER = None
KILL_READY = None
# G6-P10 (E-496): EARLY(p, ab, t0) -> list, called once when intro_10's area appears and before the discovery probe
# (read-only fast reads of fixed in-block addresses; written to early.json). None = unchanged.
EARLY = None


def ps(action, **kw):
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS1), "-Action", action]
    for k, v in kw.items():
        if v is True:
            args.append(f"-{k}")
        elif v is not None and v is not False:
            args += [f"-{k}", str(v)]
    r = subprocess.run(args, capture_output=True, text=True, env=dict(os.environ), timeout=300)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"error": (r.stdout + r.stderr)[-800:]}


def root(name, structural=True, lums=True):
    paths = p1.fresh(name)
    with p1.dev_env():
        if structural:
            p1.install(paths, STRUCT_ID, STRUCT_OV())
        if lums:
            p1.install(paths, "e478.lums-6", [p2b.lums6()])
    return paths


def plan(paths, stamp, dry=False):
    with p1.dev_env():
        return ps("plan", Python=sys.executable, ModsRoot=paths["mods"], Cache=paths["cache"], Game=GAME, Stamp=stamp,
                  DryRun=dry)


def marker_bytes(paths):
    p = rm.structural_marker_path(paths)
    return p.read_bytes() if p.is_file() else None


def sha(b):
    return hashlib.sha256(b).hexdigest() if b is not None else None


def tree_hashes(d):
    """{relative path: sha256} of regular files, never following links or junctions."""
    out = {}
    d = Path(d)
    if not d.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(d, followlinks=False):
        dirnames[:] = [x for x in dirnames if not os.path.islink(os.path.join(dirpath, x))
                       and not (os.stat(os.path.join(dirpath, x), follow_symlinks=False).st_file_attributes & 0x400)]
        for f in filenames:
            q = Path(dirpath) / f
            if q.is_file() and not q.is_symlink():
                out[str(q.relative_to(d))] = sha(q.read_bytes())
    return out


def protected():
    lvl, ptr = g3a.LVL, g3a.PTR
    return {"intro_10.lvl": sha(lvl.read_bytes()), "intro_10.ptr": sha(ptr.read_bytes()),
            "save_entries": tree_hashes(ROOT / "private" / "saves"),
            "play_profiles": tree_hashes(ROOT / "private" / "play" / "profiles")}


def end(paths, stamp, marker_json, session, code):
    mf = WORK / f"marker_{stamp}.json"
    mf.write_text(json.dumps(marker_json), encoding="utf-8")
    return ps("complete", Python=sys.executable, ModsRoot=paths["mods"], Stamp=stamp, MarkerFile=mf, Session=session,
              ExitCode="" if code is None else code)


# --- deterministic preflight --------------------------------------------------------------------------------------

def preflight():
    WORK.mkdir(parents=True, exist_ok=True)
    res, det = {}, {}
    pre = WORK / "pre"
    if pre.exists():
        shutil.rmtree(pre)
    pre.mkdir()
    # orderly-exit decision on synthetic session folders
    line = "[2026-11-14 12:00:00.000] [info] [core] [t1] "
    cases = {"orderly_close": ([line + "Title terminated; hard-exiting process."], 0, False, True),
             "orderly_guest_exit": ([line + "Execution complete"], 0, False, True),
             "zero_without_line": ([line + "M16 vblank mode=deadline"], 0, False, False),
             "line_but_nonzero": ([line + "Title terminated; hard-exiting process."], 1, False, False),
             "line_but_crash_record": ([line + "Execution complete"], 0, True, False),
             "no_log": (None, 0, False, False),
             "no_exit_code": ([line + "Execution complete"], None, False, False),
             "text_not_a_log_line": (["note: Execution complete"], 0, False, False),
             "killed_code": ([line + "M16 vblank"], -1, False, False)}
    o = {}
    for name, (lines, code, crash, want) in cases.items():
        d = pre / name
        d.mkdir()
        if lines is not None:
            (d / "runtime.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if crash:
            (d / "r3hd_crash.txt").write_text("synthetic\n", encoding="ascii")
        r = ps("orderly", Session=d, ExitCode="" if code is None else code)
        o[name] = r.get("controlled") is want
    det["orderly"] = o
    res["orderly_exit_decision"] = all(o.values())
    # lifecycle through the launcher functions, real game files read-only, disposable roots
    A = root("pre_A")
    pa = plan(A, "pf-a")
    mk = marker_bytes(A)
    res["arm_at_plan"] = (pa.get("result") == "ok" and sorted(pa.get("active", [])) == sorted(["e478.lums-6", STRUCT_ID])
                          and (pa.get("structural_marker") or {}).get("session") == "pf-a" and mk is not None
                          and json.loads(mk)["plan_sha256"] == sha(Path(pa["plan"]).read_bytes()))
    # synthetic abnormal child: a test-owned sleeper, ownership-checked and terminated
    token = f"g5p4b-child-{os.getpid()}-{time.time_ns()}"
    child = subprocess.Popen([sys.executable, "-c", "import time, sys; time.sleep(120)", token])
    time.sleep(1.0)
    own = ps("owner", ProcId=child.pid).get("owner") or {}
    k = ps("kill", ProcId=child.pid, Created=own.get("created", ""), Needle=token, ExePath=own.get("path", ""))
    child.wait(timeout=30)
    sess = pre / "child_session"
    sess.mkdir()
    (sess / "runtime.log").write_text(line + "M16 vblank\n", encoding="utf-8")
    ea = end(A, "pf-a", pa["structural_marker"], sess, child.returncode)
    res["abnormal_child_keeps_marker"] = (k.get("killed") is True and child.returncode != 0
                                          and ea.get("exit", {}).get("controlled") is False
                                          and (ea.get("end") or {}).get("cleared") is False
                                          and marker_bytes(A) == mk)
    det["child"] = {"kill": k, "returncode": child.returncode, "end": ea}
    # a wrong owner is never terminated
    child2 = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", token + "x"])
    time.sleep(1.0)
    own2 = ps("owner", ProcId=child2.pid).get("owner") or {}
    k2 = ps("kill", ProcId=child2.pid, Created=own2.get("created", ""), Needle="not-this-session",
            ExePath=own2.get("path", ""))
    alive2 = child2.poll() is None
    child2.kill()
    child2.wait(timeout=30)
    res["wrong_owner_not_terminated"] = k2.get("killed") is False and alive2
    # concurrency: a second launch while A's marker is armed
    pb = plan(A, "pf-b")
    codes = {m["id"]: m.get("code") for m in pb.get("mods", []) if m.get("state") != "active"}
    res["second_launch_refuses_structural"] = (pb.get("active") == ["e478.lums-6"] and codes == {
        STRUCT_ID: "STRUCTURAL_RECOVERY"} and pb.get("structural_recovery") == "armed"
        and not pb.get("structural_marker") and marker_bytes(A) == mk)
    orderly = pre / "orderly_close"
    eb = end(A, "pf-b", pa["structural_marker"], orderly, 0)
    res["other_session_cannot_clear"] = ((eb.get("end") or {}).get("cleared") is False
                                         and (eb.get("end") or {}).get("reason") == "another session's marker"
                                         and marker_bytes(A) == mk)
    bad = dict(pa["structural_marker"], plan_sha256="0" * 64)
    ec = end(A, "pf-a", bad, orderly, 0)
    res["wrong_plan_cannot_clear"] = (ec.get("end") or {}).get("cleared") is False and marker_bytes(A) == mk
    # malformed marker
    Cm = root("pre_C")
    rm.structural_marker_path(Cm).write_bytes(b"{not json")
    pc = plan(Cm, "pf-c")
    res["malformed_marker_refuses"] = (pc.get("active") == ["e478.lums-6"] and pc.get("structural_recovery")
                                       == "malformed" and marker_bytes(Cm) == b"{not json")
    # controlled exit clears
    E = root("pre_E")
    pe = plan(E, "pf-e")
    ee = end(E, "pf-e", pe["structural_marker"], orderly, 0)
    res["orderly_exit_clears"] = (ee.get("exit", {}).get("controlled") is True
                                  and (ee.get("end") or {}).get("cleared") is True and marker_bytes(E) is None)
    # exit code 0 without the orderly line keeps the marker (the D-248 fix)
    E2 = root("pre_E2")
    pe2 = plan(E2, "pf-e2")
    ee2 = end(E2, "pf-e2", pe2["structural_marker"], pre / "zero_without_line", 0)
    res["exit_zero_alone_keeps_marker"] = ((ee2.get("end") or {}).get("cleared") is False
                                           and marker_bytes(E2) is not None)
    # explicit clear is profile-scoped
    F = root("pre_F")
    pf = plan(F, "pf-f")
    mf = marker_bytes(F)
    cl = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "structural-recovery", "clear", "--json",
                         "--mods-root", str(A["mods"]), "--cache", str(A["cache"]), "--game-dir", str(GAME)],
                        capture_output=True, text=True)
    res["clear_is_profile_scoped"] = (cl.returncode == 0 and marker_bytes(A) is None and marker_bytes(F) == mf
                                      and pf.get("structural_marker") is not None)
    det["clear"] = cl.stdout[-400:]
    # production header refuses the transaction (the plan of root F)
    exe = p1.build_test("prod")
    nd = WORK / "negtest"
    cf = nd / "cases_prod.tsv"
    cf.write_text("\t".join(["production: intro_10 transaction", pf["plan"], "intro_10", "unknown_record", "lvl,ptr",
                             str(g3a.LVL), str(g3a.PTR), "-", "-"]) + "\n", encoding="utf-8")
    r = subprocess.run([str(exe), str(cf)], capture_output=True, text=True, timeout=600)
    res["production_refuses"] = r.returncode == 0
    det["production"] = r.stdout[-300:]
    # play.ps1 dry run on a disposable play root (list only: no marker, nothing started)
    G = root("pre_G")
    dr = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TOOLS / "play.ps1"),
                         "-DryRun", "-PlayRoot", str(G["_dir"])], capture_output=True, text=True, timeout=300,
                        env=dict(os.environ, **{ENV: "intro_10"}))
    res["play_dry_run"] = (dr.returncode == 0 and STRUCT_ID in dr.stdout and marker_bytes(G) is None)
    det["play_dry_run"] = [ln for ln in dr.stdout.splitlines() if ln.startswith(("mods", "Mods"))][:6] or dr.stderr[-400:]
    # G5-P2b R1-R8 (marker write failure, malformed, stale, clear, play.ps1 wiring)
    r8 = subprocess.run([sys.executable, str(HERE / "g5p2b_lifecycle.py"), "recovery"], capture_output=True, text=True)
    res["g5p2b_recovery_R1_R8"] = r8.returncode == 0
    for k_ in (F,):
        subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "structural-recovery", "clear", "--json",
                        "--mods-root", str(k_["mods"]), "--cache", str(k_["cache"]), "--game-dir", str(GAME)],
                       capture_output=True, text=True)
    out = {"res": res, "details": det, "pass": all(res.values())}
    (WORK / "preflight.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1))
    print("G5P4B_PREFLIGHT", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


# --- live phases ----------------------------------------------------------------------------------------------------

def launch(tag, phase, plan_path, seconds, kill_after_pass):
    """One hidden run of intro_10 with the plan; observation as E-478; optionally the ownership-checked termination."""
    from m5_live import Actor, Process
    run = f"{PREFIX}_{tag}_{phase}"
    work = WORK / tag / phase
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_E465_TEST_GROW", "R3HD_G3A_TEST_GROW"):
        env.pop(k, None)
    env["R3HD_MODS_PLAN"] = str(plan_path)
    env[ENV] = "intro_10"
    (work / "steps.txt").write_text(f"wait {seconds - 8}\n", encoding="ascii")
    row = {"phase": phase, "run": run, "planned_seconds": seconds}
    states, samples, live, early = [], [], {}, []
    t_start_utc = datetime.now(timezone.utc)
    row["harness_started_runner_utc"] = t_start_utc.isoformat()
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(seconds), "--play", "--test-level", "intro_10",
                                 "--user-root", run], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        row["runner_pid"] = game.pid
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
        row["game_pid"] = pid
        if base is None or pid is None:
            row["error"] = "process not found"
        else:
            p = Process(pid, int(base, 16))
            last, gen, ab, area_t, nxt, discovered = "none", None, None, None, 0.0, False
            pass_t, killed = None, False
            smp = None
            ws = []
            site_t = {}

            def rd(a):
                w = p.words(a, 1)
                if not w:
                    raise ValueError(f"read {a:#x}")
                return w[0]
            while time.monotonic() < t0 + seconds - 5 and p.running():
                ar = bp.areas(p)
                key = json.dumps({k: (v["base"], v["end"]) for k, v in (ar or {}).items()})
                if ar is not None and key != last:
                    last = key
                    s = bp.snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="areas_changed", area_keys=sorted(ar))
                    states.append(s)
                    a1 = (ar or {}).get(1)
                    if a1 and a1["end"] - a1["base"] in (g3a.AREA, GROWN_AREA) and ab is None:
                        ab, area_t = a1["base"], time.monotonic()
                        ws = [(ab + a - 4, ab + n - 4, ab + b - 4) for a, n, b in sites()]
                        if EARLY is not None:   # G6-P10 hook: read-only, before the discovery probe
                            early = EARLY(p, ab, t0)
                    elif ab is not None and (not a1 or a1["base"] != ab):
                        gen = None
                        row.setdefault("left_intro_10_t", s["t"])
                if ab is not None and not discovered:
                    discovered = True
                    disc = work / "discovery.json"
                    q = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc),
                                        "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
                    try:
                        if OBSERVE is not None:   # G6-P1b hook
                            live = dict(t=round(time.monotonic() - t0, 3), ab=ab, **OBSERVE(rd, p, ab))
                        else:
                            nodes, prob, hdr = g3b.walk_null(rd, ab + g3b.GRAPH - 4)
                            al = rd(ab + g3b.NODE13 - 4 + 0x18)
                            live = {"t": round(time.monotonic() - t0, 3), "ab": ab, "nodes": nodes, "problems": prob,
                                    "header": hdr, "arc13": {"count": rd(al + 8), "target": rd(rd(al) + 0xC)}}
                    except Exception as x:
                        live = {"error": repr(x)}
                    smp = SAMPLER(p, ab) if SAMPLER is not None else None
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
                if gen is not None and now >= nxt:
                    try:
                        if smp is not None:   # G6-P1b hook
                            samples.append({"t": round(now - t0, 3), **smp(gen, round(now - t0, 3))})
                        else:
                            v = gen.dsg()
                            samples.append({"t": round(now - t0, 3), "v8": g3a.u32(*v[8])})
                    except Exception as x:
                        row["sampling_stopped"] = type(x).__name__
                        gen = None
                    nxt = now + 0.1
                    seq = []
                    for x in samples:
                        if not seq or seq[-1] != x["v8"]:
                            seq.append(x["v8"])
                    for k, (wa, wn, wb) in enumerate(ws):
                        if k not in site_t and any(seq[i] == wa and seq[i + 1] == wn and seq[i + 2] == wb
                                                   for i in range(len(seq) - 2)):
                            site_t[k] = round(now - t0, 3)
                            row["site_pass_t"] = dict(site_t)
                    if pass_t is None and ws and len(site_t) == len(ws):
                        pass_t = now
                        row["pass_t"] = round(now - t0, 3)
                    if pass_t is None and KILL_READY is not None and KILL_READY(samples):   # G6-P1b hook
                        pass_t = now
                        row["pass_t"] = round(now - t0, 3)
                if kill_after_pass and not killed and area_t is not None and (
                        (pass_t is not None and now >= pass_t + 3) or now >= area_t + 45):
                    killed = True
                    if pass_t is None:
                        row["kill"] = {"killed": False, "reason": "no 13 -> N -> 14 pass within 45 s (invalid)"}
                    else:
                        own = ps("owner", ProcId=pid).get("owner") or {}
                        row["owner"] = own
                        needle = f"--log_file={RUNS / run / 'runtime.log'}"
                        chain = own.get("parents") or []
                        created = own.get("created")
                        try:
                            c_dt = datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None
                        except ValueError:
                            c_dt = None
                        checks = {
                            "name": own.get("name") == "r3hd.exe",
                            "path": (own.get("path") or "").lower() == str(EXE).lower(),
                            "command_line": needle in (own.get("command_line") or ""),
                            "created_after_runner_start": bool(c_dt and c_dt >= t_start_utc),
                            "grandparent_is_runner": len(chain) >= 2 and chain[1]["pid"] == game.pid,
                        }
                        row["ownership"] = checks
                        if all(checks.values()):
                            row["kill"] = ps("kill", ProcId=pid, Created=created, Needle=needle, ExePath=own["path"])
                            row["kill_t"] = round(time.monotonic() - t0, 3)
                        else:
                            row["kill"] = {"killed": False, "reason": "ownership not established (BLOCKED)"}
                time.sleep(0.005)
        game.wait(timeout=seconds + 240)
        row["runner_exit"] = game.returncode
        row["process_left"], row["process_detail"] = g3a.game_left(pid, run)   # E-483 revision 1
    try:
        rj = json.loads((RUNS / run / "run.json").read_text(encoding="utf-8-sig"))
        row["run_json"] = {k: rj.get(k) for k in ("exit_code", "started_utc", "finished_utc",
                                                  "initial_foreground_unchanged")}
        row["run_json"]["foreground_events"] = len(rj.get("foreground_events") or [])
        for k in ("game_foreground_events", "game_foreground_samples", "monitor_hook_ready", "monitor_stop_clean"):
            row["run_json"][k] = rj.get(k)
        row["run_json"]["r3hd_foreground_events"] = sum(
            1 for e in (rj.get("foreground_events") or []) if str(e.get("ProcessName", "")).lower().startswith("r3hd"))
    except Exception as x:
        row["run_json"] = {"error": repr(x)}
    left = subprocess.run(["powershell", "-NoProfile", "-Command",
                           "@(Get-CimInstance Win32_Process -Filter \"Name='r3hd.exe'\" | Where-Object { $_.CommandLine "
                           "-like '*" + PREFIX + "_*' } | ForEach-Object { $_.ProcessId }) -join ','"],
                          capture_output=True, text=True)
    row[f"{PREFIX}_game_processes_left"] = left.stdout.strip()
    outs = [("states", states), ("samples", samples), ("live", live), ("row", row)]
    if EARLY is not None:   # G6-P10 hook
        outs.append(("early", early))
    for name, obj in outs:
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1, default=str) + "\n")
    return row


def run(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    pre = json.loads((WORK / "preflight.json").read_text())
    if not pre["pass"]:
        raise SystemExit("preflight did not pass")
    g3b.N = 112
    ev = {"tag": tag, "protected_before": protected()}
    RA = root(f"run_{tag}_RA")
    RB = root(f"run_{tag}_RB", lums=False)
    ev["RB_marker"] = {"before": sha(marker_bytes(RB))}
    # A: armed launch, consumption, forced termination, launcher exit handling
    sA = f"{PREFIX}_{tag}_A"
    pa = plan(RA, sA)
    ev["A_plan"] = {k: pa.get(k) for k in ("result", "active", "structural_marker", "structural_recovery", "plan")}
    ev["A_plan"]["codes"] = {m["id"]: m.get("code") for m in pa.get("mods", []) if m.get("state") != "active"}
    mk = marker_bytes(RA)
    mp = rm.structural_marker_path(RA)
    ev["marker_A"] = {"sha256": sha(mk), "mtime_utc": datetime.fromtimestamp(mp.stat().st_mtime, timezone.utc).isoformat()
                      if mk else None, "json": json.loads(mk) if mk else None}
    ev["A_plan_sha256"] = sha(Path(pa["plan"]).read_bytes()) if pa.get("plan") else None
    shutil.copyfile(pa["plan"], WORK / f"plan_{tag}_A.txt")
    rowA = launch(tag, "A", pa["plan"], 140, True)
    ev["marker_after_kill"] = sha(marker_bytes(RA))
    code = (rowA.get("run_json") or {}).get("exit_code")
    ev["A_complete"] = end(RA, sA, pa["structural_marker"], RUNS / rowA["run"], code)
    ev["A_orderly_if_zero"] = ps("orderly", Session=RUNS / rowA["run"], ExitCode=0)
    ev["marker_after_complete"] = sha(marker_bytes(RA))
    ev["RB_marker"]["after_A"] = sha(marker_bytes(RB))
    # C: recovery launch
    sC = f"{PREFIX}_{tag}_C"
    pc = plan(RA, sC)
    ev["C_plan"] = {k: pc.get(k) for k in ("result", "active", "structural_marker", "structural_recovery", "plan")}
    ev["C_plan"]["codes"] = {m["id"]: m.get("code") for m in pc.get("mods", []) if m.get("state") != "active"}
    ctext = Path(pc["plan"]).read_text(encoding="utf-8") if pc.get("plan") else ""
    shutil.copyfile(pc["plan"], WORK / f"plan_{tag}_C.txt")
    ev["C_plan_has_tx"] = bool(re.search(r"^(level-tx|tx-file) ", ctext, re.M))
    ev["marker_after_C_plan"] = sha(marker_bytes(RA))
    if not ev["C_plan_has_tx"]:
        launch(tag, "C", pc["plan"], 110, False)
    else:
        ev["C_launch"] = "NOT LAUNCHED: the recovery plan still carries a transaction (critical, fail-open)"
    ev["marker_after_C"] = sha(marker_bytes(RA))
    rbl = plan(RB, f"{PREFIX}_{tag}_RBdry", dry=True)
    ev["RB_dry_after_C"] = {"active": rbl.get("active"), "result": rbl.get("result")}
    ev["RB_marker"]["after_C"] = sha(marker_bytes(RB))
    # D: explicit clear and re-authorization
    def clear(paths):
        r = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "structural-recovery", "clear", "--json",
                            "--mods-root", str(paths["mods"]), "--cache", str(paths["cache"]), "--game-dir",
                            str(GAME)], capture_output=True, text=True)
        try:
            return json.loads(r.stdout)
        except ValueError:
            return {"error": r.stdout[-300:] + r.stderr[-300:]}
    ev["D_clear"] = clear(RA)
    ev["marker_after_clear"] = sha(marker_bytes(RA))
    dd = plan(RA, f"{PREFIX}_{tag}_Ddry", dry=True)
    ev["D_dry"] = {"active": dd.get("active"), "result": dd.get("result")}
    sD = f"{PREFIX}_{tag}_D"
    pdd = plan(RA, sD)
    ev["D_plan"] = {k: pdd.get(k) for k in ("result", "active", "structural_marker")}
    ev["D_plan_has_tx"] = bool(pdd.get("plan")) and bool(re.search(r"^level-tx ", Path(pdd["plan"]).read_text(
        encoding="utf-8"), re.M))
    ev["D_final_clear"] = clear(RA)
    ev["marker_final"] = sha(marker_bytes(RA))
    ev["RB_marker"]["after_D"] = sha(marker_bytes(RB))
    ev["protected_after"] = protected()
    (WORK / tag / "evidence.json").write_text(json.dumps(ev, indent=1, default=str) + "\n")
    print(json.dumps({k: ev[k] for k in ("marker_after_kill", "marker_after_complete", "marker_after_C",
                                         "marker_after_clear", "marker_final", "RB_marker")}, indent=1, default=str))
    return 0


# --- judge ----------------------------------------------------------------------------------------------------------

def logtime(line):
    m = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\]", line)
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f").astimezone(timezone.utc) if m else None


def judge(tag):
    ev = json.loads((WORK / tag / "evidence.json").read_text())
    out = {}
    for ph in ("A", "C"):
        w = WORK / tag / ph
        if not (w / "row.json").is_file():
            out[ph] = None
            continue
        r = json.loads((w / "row.json").read_text())
        for k in ("states", "samples", "live"):
            r[k] = json.loads((w / f"{k}.json").read_text())
        r["log"] = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / r["run"]).glob("runtime*.log")))
        r["judges"] = {t: subprocess.run([sys.executable, str(TOOLS / t), "--run", r["run"]], cwd=ROOT,
                                         capture_output=True, text=True).returncode
                       for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py")}
        out[ph] = r
    A, C = out["A"], out["C"]
    det, R = {}, {}
    invalid = []
    if not A or A.get("error") or not (A.get("kill") or {}).get("killed"):
        invalid.append("A: " + str((A or {}).get("kill") or (A or {}).get("error")))
    mA = ev["marker_A"]["json"] or {}
    own = A.get("ownership") or {} if A else {}
    R["R1_session_ownership"] = bool(A and mA.get("session") == f"{PREFIX}_{tag}_A"
                                     and mA.get("plan_sha256") == ev["A_plan_sha256"] and own and all(own.values()))
    lines = A["log"].splitlines() if A else []
    grow = next((ln for ln in lines if "M36 grow size file=intro_10" in ln), None)
    created = (A.get("owner") or {}).get("created") if A else None
    t_mark = datetime.fromisoformat(ev["marker_A"]["mtime_utc"]) if ev["marker_A"]["mtime_utc"] else None
    t_proc = datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None
    t_grow = logtime(grow) if grow else None
    det["ordering"] = {"marker_mtime": str(t_mark), "process_created": str(t_proc), "first_grow_size": str(t_grow)}
    R["R2_activation_ordering"] = bool(t_mark and t_proc and t_grow and t_mark < t_proc < t_grow
                                       and "G5P1 level-tx active level=intro_10" in A["log"]
                                       and A["log"].count("G5P3 tx snapshot") == 2)
    lv = A["live"] if A else {}
    ab = lv.get("ab")
    seq = []
    for x in (A["samples"] if A else []):
        if A.get("kill_t") and x["t"] > A["kill_t"]:
            break
        if not seq or seq[-1] != x["v8"]:
            seq.append(x["v8"])
    per_site = [sum(1 for i in range(len(seq) - 2) if seq[i] == ab + a - 4 and seq[i + 1] == ab + n - 4
                    and seq[i + 2] == ab + b - 4) for a, n, b in sites()] if ab else []
    passes = min(per_site) if per_site else 0
    det["A_passes_before_kill"] = passes if len(per_site) == 1 else per_site
    R["R3_functional_activation"] = bool(ab and lv.get("problems") == [] and len(lv.get("nodes", [])) == GROWN_NODES
                                         == len(set(lv["nodes"])) and all(lv["nodes"][i] == ab + fn - 4
                                                                          for i, fn in new_nodes())
                                         and lv["arc13"]["target"] == ab + new_nodes()[0][1] - 4 and passes >= 1)
    rj = (A or {}).get("run_json") or {}
    comp = ev["A_complete"]
    det["A_exit"] = {"run_json": rj, "complete": comp, "orderly_if_zero": ev["A_orderly_if_zero"],
                     "kill": (A or {}).get("kill"), "kill_t": (A or {}).get("kill_t"),
                     "left": (A or {}).get(f"{PREFIX}_game_processes_left")}
    try:
        dur = (datetime.fromisoformat(rj["finished_utc"].replace("Z", "+00:00"))
               - datetime.fromisoformat(rj["started_utc"].replace("Z", "+00:00"))).total_seconds()
    except Exception:
        dur = None
    det["A_runner_seconds"] = dur
    R["R4_abnormal_termination"] = bool(A and (A.get("kill") or {}).get("killed") is True
                                        and rj.get("exit_code") not in (None, 0) and dur is not None and dur < 130
                                        and not A["process_left"] and not A.get(f"{PREFIX}_game_processes_left")
                                        and comp.get("exit", {}).get("controlled") is False
                                        and comp.get("exit", {}).get("orderly_line") is None
                                        and ev["A_orderly_if_zero"].get("controlled") is False)
    R["R5_marker_persistence"] = ((comp.get("end") or {}).get("cleared") is False and ev["marker_A"]["sha256"]
                                  and ev["marker_after_kill"] == ev["marker_A"]["sha256"]
                                  == ev["marker_after_complete"])
    cl = C["log"] if C else ""
    clv = (C or {}).get("live") or {}
    R["R6_next_launch_rejection"] = bool(
        C and ev["C_plan"]["codes"] == {STRUCT_ID: "STRUCTURAL_RECOVERY"}
        and ev["C_plan"]["structural_recovery"] == "armed" and not ev["C_plan"]["structural_marker"]
        and not ev["C_plan_has_tx"] and cl.count("M33 mods state=active") == 1 and "G5P1 level-tx" not in cl
        and "G5P3" not in cl and "M36 grow" not in cl and len(clv.get("nodes", [])) == 143
        and clv.get("problems") == [] and ev["marker_after_C"] == ev["marker_A"]["sha256"]
        and any(s.get("areas", {}).get("1", {}).get("length") == g3a.AREA for s in C["states"] if "invalid" not in s))
    left15 = any(s.get("areas", {}).get("1", {}).get("base") == hex(INTRO15_BASE) for s in (C or {}).get("states", [])
                 if "invalid" not in s)
    det["C_left_for_intro_15"] = left15
    R["R7_nonstructural"] = bool(C and "e478.lums-6" in (ev["A_plan"]["active"] or []) and "e478.lums-6" in
                                 (ev["C_plan"]["active"] or []) and "M33 mods served mod=e478.lums-6 file=intro_10.lvl"
                                 in cl and left15)
    rb = ev["RB_marker"]
    pre = json.loads((WORK / "preflight.json").read_text())
    R["R8_profile_isolation"] = (all(v is None for v in rb.values()) and STRUCT_ID in (ev["RB_dry_after_C"]["active"]
                                                                                           or [])
                                 and pre["res"]["clear_is_profile_scoped"])
    R["R9_explicit_recovery"] = (ev["D_clear"].get("cleared") is True and ev["marker_after_clear"] is None
                                 and STRUCT_ID in (ev["D_dry"]["active"] or []) and ev["D_plan_has_tx"]
                                 and (ev["D_plan"]["structural_marker"] or {}).get("session") == f"{PREFIX}_{tag}_D"
                                 and ev["marker_final"] is None)
    if tag in ORIGINAL_R10_TAGS:
        safe = all(r and not any(r["judges"].values()) and not r["process_left"]
                   and (r.get("run_json") or {}).get("initial_foreground_unchanged") is True
                   and (r.get("run_json") or {}).get("foreground_events") == 0 for r in (A, C))
    else:   # revision 1
        safe = all(r and not any(r["judges"].values()) and not r["process_left"]
                   and (r.get("run_json") or {}).get("game_foreground_events") == 0
                   and (r.get("run_json") or {}).get("game_foreground_samples") == 0
                   and (r.get("run_json") or {}).get("monitor_hook_ready") is True
                   and (r.get("run_json") or {}).get("monitor_stop_clean") is True
                   and (r.get("run_json") or {}).get("r3hd_foreground_events") == 0 for r in (A, C))
    R["R10_production_desktop"] = bool(pre["res"]["production_refuses"] and ev["protected_before"] == ev["protected_after"]
                                       and safe and C and C["runner_exit"] == 0)
    det["judges"] = {p: (r or {}).get("judges") for p, r in (("A", A), ("C", C))}
    passed = [k for k, v in R.items() if v is True]
    verdict = ("G5-P4b VERIFIED — ABNORMAL-TERMINATION RECOVERY" if not invalid and len(passed) == 10
               else ("INVALID" if invalid else "NOT PASSED"))
    res = {"invalid": invalid, "R": R, "verdict": verdict, "details": det}
    (WORK / f"judgement_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1, default=str)[:5000])
    return 0 if verdict.startswith("G5-P4b") else 1


def main():
    a = sys.argv[1:]
    if a and a[0] == "preflight":
        return preflight()
    if len(a) == 2 and a[0] == "judge":
        return judge(a[1])
    if len(a) == 1 and re.fullmatch(r"[A-Za-z0-9-]{1,24}", a[0]):
        return run(a[0])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
