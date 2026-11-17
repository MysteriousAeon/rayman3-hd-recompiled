#!/usr/bin/env python3
"""E-523 (D-290) G6-P34: runtime behaviour of G6-P33 remix edits on the PRODUCTION build (hidden, read-only probes).

    g6p34_remix_runtime.py prepare           compile the three remix mods with the G6-P33 editor core (no game)
    g6p34_remix_runtime.py run CASE TAG      CASE = L (intro_10) | C (intro_20 combined) | M (intro_15); one run
    g6p34_remix_runtime.py judge CASE TAG

PROSPECTIVE PROTOCOL (committed before any run; thresholds are not changed after results)
Build: the installed production binaries r3hd.exe 6635d2327179d5a0..., rexruntime.dll 784f7b72b7051bc3...;
`g5p1_dev_gate.py status` = production; R3HD_DEV_STRUCTURAL_TX absent in the parent and the game environment.
Mods: compiled by r3hd_level_editor_core.validate_remix (the G6-P33 editor export: actor-position / waypoint-position
overrides, production policy) into private/work/e523/mods/<case>; imported into a private mods root per run with the
mod manager (cmd_import --enable) and planned by resolve_all. Runs: m9_license_run.py (hidden window, muted, no
physical pad, private --user-root, --test-level LEVEL, no captures). Live observation: block8_probe.areas for the level
area base AB (guest address of file offset o = AB + o - 4), m5_live.Actor on the edited actors' SuperObjects
(AB + so - 4), positions every 0.1 s; guest readback of every remix range at the first and the last read. At most one
run per case; a rerun only after a committed amendment for an INVALID run or a demonstrated harness defect.
Authored values are float32 of the numbers below; "at P" means within 0.01 units.

CASE L, intro_10 (no input, 200 s sampled). Collectible family NIN_m_Lums_Int10 (instance 0 VERIFIED by E-461):
  lum #1  F1 (20.0740, -2.3451, -31.2462) -> P1 (16.823, -3.345, -31.034)   (on the E-461 q2 base flight path)
  lum #3  F3 (7.9033, -73.5464, -45.7994) -> P3 (11.139, -73.227, -45.188)  (on the base path)
  lum #4  F4 (9.0286, -57.4297, -45.2718) -> Q4 (-10.090, -52.878, -48.979) (control: 23.3 units from the base path)
  Toad #0 (NIN_m_ToadIntro, scripted, 128 units from the path) T0 (91.4663, -237.7503, -56.0577) -> +3 x
  Hypothesis: a lum keeps an authored position and the flight generator collects it there (distance query), as E-461.
  L1 served: exactly the 8 compiled 12-byte ranges of intro_10.lvl, from one active mod; gameplay line present.
  L2 readback: the 8 ranges hold the compiled bytes at the first and the last read.
  L3 placement: at the first live sample lums #1 / #3 / #4 at P1 / P3 / Q4 and Toad #0 at its authored point; every
     other lum at its file translation.
  L4 collection: generator variable 5 reaches exactly 2 within the window and never exceeds 2; each increment happens
     within 3 s after the generator's closest approach (< 1.0 unit) to P1 or P3; each of lums #1 and #3 has at least one
     such approach.
  L5 control: lum #4 stays at Q4 and readable (alive) at the last sample; no increment within 3 s of any approach to Q4
     (the generator is never predicted within 20 units of Q4).
  L6 safety: haptics line; M21 / M22 / M23 judges 0; runner exit 0; no game process left.
  Toad: classification only (appeared / remained / moved), never a pass criterion.
  Invalid: level does not open; generator / targets not found; sampling ends before 150 s.

CASE C, intro_20 combined (production level patch + remix, G6-P27's walk). Mods: g6p25.west-basin-fairy (the G6-P29
editor export used by G6-P30, tx 9083786df631a5a3, 55 ranges) and the remix mod g6p34.intro20-remix:
  graph C (FairyLight instance 2 variable 2) nodes 0 / 3 / 5 moved by the G6-P28 offsets (-4,-3,-2) / (0,-5,3) / (-3,0,-4)
  NIK_mChameleon #0 +3 x;  YAM_mPowerz #1 +3 x;  Mic_mBoing2 #11 +3 x   (all >= 40 units from the walk)
  Run and inherited judgement: G6-P30's production run (G6-P20 run_case, G6-P27 walker, game environment without the
  development variable) with the two mods in one plan; inherited Q0 and P1-P6 unchanged except the inherited P1 range
  count N_RANGES = 55 + the remix mod's 9 ranges = 64 (P1 requires served == planned, which includes both mods).
  C1 coexistence in the plan: both mods active, one level transaction (the patch's id), the remix not structural.
  C2 production activation and inherited behaviour: G6-P30 Q0 + G6-P27 P1-P6 (terrain readback, west-floor physics,
     inserted FairyLight on graph A, exit, safety) with N_RANGES 64.
  C3 remix readback: the 9 remix ranges hold the compiled bytes at the first and the last read (the in-place edits are
     served over the transaction image, not discarded).
  C4 route: FairyLight instance 2 (tracked f2) comes within 0.30 of each moved node's new position and stays >= 2.0
     from each moved node's original position; unmoved nodes 1 / 2 / 4 within 0.30 (E-480: 0.16-0.27).
  Actors: classification only (first tracked sample at authored / original / elsewhere; last sample).
  Verdict C: COMBINED VERIFIED iff C1-C4 pass.

CASE M, intro_15 (no input, 200 s). Murfy's graph (NIN_m_MurfyIntro15 instance 0 variable 0; Murfy itself LOCKED):
  node 0 (-48.26, 17.65, -3.55) +(0, 5, 0); node 1 (-35.27, 10.05, -1.39) +(0, -5, 0)
  NIK_mChameleon #0 +3 x; ODA_mVerduleBase #0 +3 x
  M1 served / M2 readback as L1 / L2 (6 ranges); M3 placement of the two actors at the first sample (classification);
  M4 route: if Murfy comes within 3 units of any original node 0-8 (the graph is in use), PASS iff its closest
     approach to each moved node's new position is <= 1.0 and at least 2.0 closer than to its original position;
     if it never does, UNKNOWN (graph not used in the window), not FAIL.
  M5 safety as L6.
Classes: VERIFIED MOVABLE (placed, kept and the expected interaction observed); VERIFIED PLACEMENT, BEHAVIOUR UNKNOWN
(placed and kept, no interaction observed); SCRIPT-OVERRIDDEN (live position replaced); VERIFIED ROUTE (consumer
follows the moved waypoints); RESOURCE EDIT ONLY (bytes served, consumer not observed).
Outputs: private/work/e523 (numbers only).

AMENDMENT 1 (after run L r1, before runs C and M; L r1 keeps its original judgement, L2 FAIL): L r1's readback
showed every actor matrix range byte-exact at the first read, and every snapshot range holding the compiled bytes
word-swapped back (the loader converts the word-swapped snapshot copy to native order at load: the authored value, in
memory order). The L2 / M2 / C3 assumption "raw compiled bytes in guest memory" was wrong for snapshot words, and a
live actor matrix may be moved later by the actor itself (the Toad moved 0.16 in y). Revised readback for C3 and M2:
  matrix ranges equal the compiled bytes at the first read; snapshot ranges equal the compiled bytes word-swapped
  (authored value, native order) at the first and the last read; waypoint ranges equal the compiled bytes at the
  first and the last read. Later matrix values are reported by the actor classification, not judged here.
"""
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TOOLS))
import r3hd_mods as rm  # noqa: E402
import r3hd_level_editor_core as core  # noqa: E402

ROOT = TOOLS.parent
GAME = ROOT / "private" / "extracted" / "5841123F"
RUNS = ROOT / "private" / "work" / "m6_runs"
WORK = ROOT / "private" / "work" / "e523"
PREFIX = "e523"
f32 = core.f32
GEN10 = "NIN_m_GenFlyIntro_10"
LUM10 = core.LUM10
FAIRY20 = rm.FAIRY20

# ------------------------------------------------------------------------------------------------ targets


def key_of(model, name):
    return next(k for (k, _), a in model.actors.items() if a["name"] == name)


def gkey_of(model, name, inst, var):
    return next(k for k in model.graphs if model.graphs[k]["name"] == name and k[1:] == (inst, var))


def plus(p, d):
    return [f32(a + b) for a, b in zip(p, d)]


def spec(case):
    """{level, actors: [(label, key, inst, authored)], waypoints: [(label, gkey, node, authored)]}."""
    if case == "L":
        m = core.RemixModel(GAME, "intro_10")
        tk = key_of(m, "NIN_m_ToadIntro")
        return m, {"level": "intro_10", "actors": [
            ("lum1", LUM10, 1, [f32(v) for v in (16.823, -3.345, -31.034)]),
            ("lum3", LUM10, 3, [f32(v) for v in (11.139, -73.227, -45.188)]),
            ("lum4", LUM10, 4, [f32(v) for v in (-10.090, -52.878, -48.979)]),
            ("toad0", tk, 0, plus(m.actors[(tk, 0)]["position"], (3, 0, 0)))], "waypoints": []}
    if case == "C":
        m = core.RemixModel(GAME, "intro_20")
        g = (FAIRY20, 2, 2)
        offs = {0: (-4.0, -3.0, -2.0), 3: (0.0, -5.0, 3.0), 5: (-3.0, 0.0, -4.0)}
        acts = []
        for label, name, i in (("cham0", "NIK_mChameleon", 0), ("powerz1", "YAM_mPowerz", 1),
                               ("boing11", "Mic_mBoing2", 11)):
            k = key_of(m, name)
            acts.append((label, k, i, plus(m.actors[(k, i)]["position"], (3, 0, 0))))
        return m, {"level": "intro_20", "actors": acts, "waypoints": [
            (f"c{n}", g, n, plus(m.graphs[g]["nodes"][n]["position"], o)) for n, o in sorted(offs.items())]}
    if case == "M":
        m = core.RemixModel(GAME, "intro_15")
        mk = next(k for k in m.graphs if m.graphs[k]["name"] == "NIN_m_MurfyIntro15" and k[1:] == (0, 0))
        acts = []
        for label, name in (("cham0", "NIK_mChameleon"), ("verdule0", "ODA_mVerduleBase")):
            k = key_of(m, name)
            acts.append((label, k, 0, plus(m.actors[(k, 0)]["position"], (3, 0, 0))))
        return m, {"level": "intro_15", "actors": acts, "waypoints": [
            ("m0", mk, 0, plus(m.graphs[mk]["nodes"][0]["position"], (0, 5, 0))),
            ("m1", mk, 1, plus(m.graphs[mk]["nodes"][1]["position"], (0, -5, 0)))]}
    raise SystemExit(f"unknown case {case}")


def project(case):
    m, s = spec(case)
    p = core.new_remix(s["level"])
    p["meta"]["id"] = f"g6p34.{s['level'].replace('_', '')}-remix"
    p["actors"] = [{"model": k, "instance": i, "matrix_sha256": m.actors[(k, i)]["matrix_sha256"], "position": pos}
                   for _, k, i, pos in s["actors"]]
    p["waypoints"] = [{"model": g[0], "instance": g[1], "variable": g[2], "node": n,
                       "waypoint_sha256": m.graphs[g]["nodes"][n]["waypoint_sha256"], "position": pos}
                      for _, g, n, pos in s["waypoints"]]
    return m, s, core.check_remix(p)


def prepare():
    os.environ.pop(rm.STRUCT_ENV, None)
    out = {}
    for case in ("L", "C", "M"):
        m, s, p = project(case)
        d = WORK / "mods" / case
        if d.exists():
            shutil.rmtree(d)
        r = core.validate_remix(p, GAME, d, model=m)
        if not r["ok"]:
            raise SystemExit(f"{case}: {r}")
        (WORK / "mods" / f"{case}_project.json").write_text(json.dumps(p, indent=1) + "\n")
        (WORK / "mods" / f"{case}_ranges.json").write_text(json.dumps(r["range_list"], indent=1) + "\n")
        out[case] = {"id": p["meta"]["id"], "ranges": r["ranges"],
                     "mod_sha256": rm.sha256_bytes((d / "mod.json").read_bytes())}
    (WORK / "mods" / "prepared.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


def targets_so(m, s):
    """[(label, kind, file SO offset or waypoint offset, authored, original)]."""
    ix = m.ix
    out = []
    for label, k, i, pos in s["actors"]:
        out.append((label, "actor", ix["placements"][k][i]["so"], pos, list(m.actors[(k, i)]["position"])))
    for label, g, n, pos in s["waypoints"]:
        out.append((label, "waypoint", ix["graphs"][g]["nodes"][n][1], pos, list(m.graphs[g]["nodes"][n]["position"])))
    return out


# ------------------------------------------------------------------------------------------------ runs L / M
def plain_run(case, tag):
    import block8_probe as bp
    from m5_live import Actor, Process, u8
    if os.environ.get(rm.STRUCT_ENV):
        raise SystemExit(f"{rm.STRUCT_ENV} is set")
    m, s, p = project(case)
    level = s["level"]
    run = f"{PREFIX}_{tag}_{case}"
    work = WORK / "runs" / tag / case
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    paths = {"home": None, "game": GAME, "mods": work / "mods", "cache": work / "cache"}
    rm.cmd_import(paths, WORK / "mods" / case, enable=True)
    res = rm.resolve_all(paths, write_plan=paths["cache"])
    row = {"case": case, "run": run, "plan_active": res["active"], "plan_ranges": res["ranges"],
           "gameplay_active": res["gameplay_active"], "structural_active": res["structural_active"]}
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    env.pop(rm.STRUCT_ENV, None)
    env["R3HD_MODS_PLAN"] = row["plan"] = str(paths["cache"] / rm.PLAN_NAME)
    rngs = [(o, bytes.fromhex(d)) for _, o, d, _ in json.loads((WORK / "mods" / f"{case}_ranges.json").read_text())]
    tg = targets_so(m, s)
    seconds, watch = 260, 200
    (work / "steps.txt").write_text(f"wait {seconds - 8}\n", encoding="ascii")
    samples, reads = [], {}
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(seconds), "--play", "--test-level", level,
                                 "--user-root", run], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        needle = re.compile(rf"[\\/]{level}\.lvl result=00000000", re.IGNORECASE)
        opened = base = pid = None
        end = time.monotonic() + 90
        while time.monotonic() < end and game.poll() is None and opened is None:
            time.sleep(0.5)
            lp = RUNS / run / "runtime.log"
            if lp.is_file():
                text = lp.read_text(errors="replace")
                opened = time.monotonic() if needle.search(text) else None
                mm = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
                base = mm.group(1) if mm else base
        if opened is None or base is None:
            row["error"] = "level did not open"
        else:
            pid = json.loads((RUNS / run / "process.json").read_text(encoding="utf-8-sig"))["pid"]
            pr = Process(pid, int(base, 16))
            ab = None
            while time.monotonic() < opened + 20 and ab is None:
                ar = bp.areas(pr)
                ab = ar[1]["base"] if ar and ar.get(1) else None
                time.sleep(0.1)
            time.sleep(2.0)
            row["ab"] = hex(ab) if ab else None
            acts = {}
            for label, kind, off, _, _ in tg:
                if kind == "actor" and ab:
                    try:
                        acts[label] = Actor(pr, ab + off - 4)
                    except Exception as x:
                        row.setdefault("actor_errors", {})[label] = repr(x)
            row["actor_models"] = {k: a.model for k, a in acts.items()}
            follower = None
            disc = work / "discovery.json"
            q = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc),
                                "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
            others = []
            want = GEN10 if case == "L" else "NIN_m_MurfyIntro15"
            for x in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if q.returncode == 0 else []):
                try:
                    a_ = Actor(pr, int(x["so"], 16))
                except Exception:
                    continue
                if a_.model == want and follower is None and (case != "L" or a_.mind):
                    follower = a_
                elif case == "L" and a_.model == "NIN_m_Lums_Int10":
                    others.append(list(a_.position()))
            row["follower_found"] = follower is not None
            row["lums_all_first"] = others

            def read_back():
                return {o: (pr.read(ab + o - 4, len(d)) or b"").hex() for o, d in rngs} if ab else {}
            reads["first"] = read_back()
            row["first_t"] = round(time.monotonic() - opened, 3)
            t_end = time.monotonic() + watch
            while time.monotonic() < t_end and pr.running():
                smp = {"t": round(time.monotonic() - opened, 3), "a": {}}
                for label, a in list(acts.items()):
                    try:
                        smp["a"][label] = [list(a.position()), a.alive()]
                    except Exception:
                        smp["a"][label] = None
                if follower is not None:
                    try:
                        smp["f"] = list(follower.position())
                        if case == "L":
                            smp["v5"] = u8(follower.dsg()[5])
                    except Exception as x:
                        row["sampling_stopped"] = type(x).__name__
                        break
                samples.append(smp)
                time.sleep(0.1)
            reads["last"] = read_back() if pr.running() else {}
            row["last_t"] = samples[-1]["t"] if samples else None
        game.wait(timeout=seconds + 240)
        row["runner_exit"] = game.returncode
        r_ = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True) if pid else None
        row["process_left"] = bool(pid and str(pid) in r_.stdout)
    for name, obj in (("samples", samples), ("reads", reads), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in row.items() if k != "lums_all_first"}, default=str)[:900])
    return 0


# ------------------------------------------------------------------------------------------------ run C
def combined_setup():
    import g6p30_production_run as g30
    g27 = g30.g27
    g30.WORK, g30.PREFIX = WORK / "runs_c", "e523c"
    g27.N_RANGES = 55 + 9                       # pre-registered: patch 55 + remix 9 (the only inherited change)
    g30.configure()
    return g30, g27


def combined_run(tag):
    from m5_live import Actor
    import block8_probe as bp
    if os.environ.get(rm.STRUCT_ENV):
        raise SystemExit(f"{rm.STRUCT_ENV} is set")
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True,
                        text=True).stdout.strip()
    if st != "production":
        raise SystemExit(f"gate {st}")
    g30, g27 = combined_setup()
    g20 = g27.g20
    m, s, p = project("C")
    remix = json.loads((WORK / "mods" / "C" / "mod.json").read_text(encoding="utf-8"))
    patch = json.loads(g30.MOD.read_text(encoding="utf-8"))["overrides"]
    run_ = f"e523c_{tag}_M"
    res, text, paths = g20.plan_of(f"run_{tag}", [(g30.MID, patch), (remix["id"], remix["overrides"])],
                                   session=run_, env=None)
    want = f"level-tx 2 intro_20 {g30.MID} {g30.WANT_TX}"
    if sorted(res["active"]) != sorted([g30.MID, remix["id"]]) or text is None or \
            g27.p1.parse_plan(text)["txs"] != [want]:
        raise SystemExit(f"plan refused or changed: {res.get('mods')}")
    rngs = [(o, bytes.fromhex(d)) for _, o, d, _ in json.loads((WORK / "mods" / "C_ranges.json").read_text())]
    tg = targets_so(m, s)
    walker = g27.make_walker()
    st_ = {"ab": None, "reads": {}, "added": False, "next_read": 0.0}

    def tick(pr, actors, work, run, t0):
        if not st_["added"]:
            ar = bp.areas(pr)
            ab = ar[1]["base"] if ar and ar.get(1) else None
            if ab:
                st_["ab"], st_["added"] = ab, True
                for label, kind, off, _, _ in tg:
                    if kind == "actor":
                        try:
                            actors["rx_" + label] = Actor(pr, ab + off - 4)
                        except Exception as x:
                            st_.setdefault("errors", {})[label] = repr(x)
        now = time.monotonic()
        if st_["ab"] and now >= st_["next_read"]:
            r = {o: (pr.read(st_["ab"] + o - 4, len(d)) or b"").hex() for o, d in rngs}
            st_["reads"].setdefault("first", r)
            st_["reads"]["last"], st_["reads"]["last_t"] = r, round(now - t0, 3)
            st_["next_read"] = now + 5.0
        walker(pr, actors, work, run, t0)

    row = g20.run_case(tag, "M", paths["cache"] / rm.PLAN_NAME, paths, tick=tick)
    w = g30.WORK / tag / "M"
    (w / "env.json").write_text(json.dumps({"parent_has_variable": bool(os.environ.get(rm.STRUCT_ENV)),
                                            "runner_variable": g20.ENV}, indent=1) + "\n")
    (w / "remix_reads.json").write_text(json.dumps({"ab": hex(st_["ab"]) if st_["ab"] else None,
                                                    "reads": st_["reads"], "errors": st_.get("errors")}, indent=1) + "\n")
    (w / "plan_result.json").write_text(json.dumps({k: res[k] for k in ("active", "ranges", "gameplay_active",
                                                                         "structural_active")}, indent=1) + "\n")
    print(json.dumps(row, default=str)[:800])
    return 0


# ------------------------------------------------------------------------------------------------ judging
def log_of(run):
    return "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / run).glob("runtime*.log")))


def safety(run, row):
    log = log_of(run)
    judges = {}
    for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True, text=True)
        judges[tool] = r.returncode
    return ("M23 haptics policy=suppressed physical_pad_drivers=none" in log and not any(judges.values())
            and row.get("runner_exit") == 0 and not row.get("process_left")), judges


def classify(first, last, authored, original):
    if first is None:
        return "NOT OBSERVED"
    if math.dist(first, authored) < 0.01:
        if last is not None and math.dist(last, authored) < 0.01:
            return "VERIFIED PLACEMENT (appeared at and kept the authored position)"
        return f"APPEARED AT AUTHORED, THEN MOVED (last {[round(c, 3) for c in last] if last else None})"
    if math.dist(first, original) < 0.01:
        return "SCRIPT-OVERRIDDEN OR NOT SERVED (first sample at the original position)"
    return f"ELSEWHERE AT FIRST SAMPLE ({[round(c, 3) for c in first]})"


def readback_ok(reads, case):
    rl = json.loads((WORK / "mods" / f"{case}_ranges.json").read_text())
    want = {str(o): d for _, o, d, _ in rl}
    return all(reads.get(k) and {str(o): v for o, v in reads[k].items()} == want for k in ("first", "last")), len(want)


def readback_ok_a1(reads, case):
    """Amendment 1: matrix first read exact; snapshot word-swapped at first and last; waypoint exact at both."""
    rl = json.loads((WORK / "mods" / f"{case}_ranges.json").read_text())
    ok = True
    for _, o, d, w in rl:
        b = bytes.fromhex(d)
        sw = b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4)).hex()
        got = {k: (reads.get(k) or {}).get(str(o)) for k in ("first", "last")}
        if w.endswith(" matrix"):
            ok &= got["first"] == d
        elif w.endswith(" snapshot"):
            ok &= got["first"] == sw and got["last"] == sw
        else:
            ok &= got["first"] == d and got["last"] == d
    return bool(ok), len(rl)


def served_ok(run, case, level):
    rl = json.loads((WORK / "mods" / f"{case}_ranges.json").read_text())
    want = sorted((f"{level}.lvl", o, len(d) // 2) for _, o, d, _ in rl)
    got = sorted({(f.lower(), int(o), int(n)) for mid, f, o, n in
                  re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+) length=(\d+)", log_of(run))
                  if mid.startswith("g6p34.")})
    return got == want, len(got)


def judge_plain(case, tag):
    m, s, p = project(case)
    work = WORK / "runs" / tag / case
    row = json.loads((work / "row.json").read_text())
    S = json.loads((work / "samples.json").read_text())
    reads = json.loads((work / "reads.json").read_text())
    run = row["run"]
    level = s["level"]
    tg = {t[0]: t for t in targets_so(m, s)}
    invalid = []
    if row.get("error") or not row.get("follower_found") or not S or (S[-1]["t"] - S[0]["t"]) < 150:
        invalid.append("level / follower / sampling window")
    C, D = {}, {}
    ok1, n1 = served_ok(run, case, level)
    log = log_of(run)
    C[f"{case}1 served exactly the compiled ranges ({n1})"] = ok1 and bool(
        re.search(r"M33 mods gameplay mod=\S+ achievements=not_awarded", log))
    ok2, n2 = readback_ok(reads, case) if case == "L" else readback_ok_a1(reads, case)   # amendment 1 for M
    C[f"{case}2 guest readback of the {n2} ranges" + (" at first and last read" if case == "L" else
                                                      " (amendment 1)")] = ok2
    first = {k: (S[0]["a"].get(k) or [None])[0] for k in tg if tg[k][1] == "actor"} if S else {}
    lastv = {k: next((x["a"][k][0] for x in reversed(S) if x["a"].get(k)), None) for k in first}
    D["classes"] = {k: classify(first[k], lastv[k], tg[k][3], tg[k][4]) for k in first}
    D["first_t"], D["last_t"] = row.get("first_t"), row.get("last_t")
    if case == "L":
        files = [a["position"] for (k, i), a in m.actors.items() if a["name"] == "NIN_m_Lums_Int10"]
        moved = {tuple(m.actors[(LUM10, i)]["position"]) for i in (1, 3, 4)}
        others_ok = all(any(math.dist(x, f) < 0.01 for x in row.get("lums_all_first", []))
                        for f in files if tuple(f) not in moved)
        C["L3 placement: lums #1 / #3 / #4 at P1 / P3 / Q4, Toad at its authored point, other lums at file places"] = (
            all(first.get(k) and math.dist(first[k], tg[k][3]) < 0.01 for k in ("lum1", "lum3", "lum4", "toad0"))
            and others_ok)
        v5 = [(x["t"], x.get("v5")) for x in S if x.get("v5") is not None]
        incs = [v5[i][0] for i in range(1, len(v5)) if v5[i][1] > v5[i - 1][1]]

        def approaches(P):
            out, inside = [], False
            for x in S:
                d = math.dist(x["f"], P) if x.get("f") else 1e9
                if d < 1.0 and not inside:
                    out.append(x["t"])
                inside = d < 1.0
            return out
        a1, a3 = approaches(tg["lum1"][3]), approaches(tg["lum3"][3])
        q4 = min((math.dist(x["f"], tg["lum4"][3]) for x in S if x.get("f")), default=None)
        D.update(v5_seen=sorted({v for _, v in v5}), increments=incs, approach_P1=a1, approach_P3=a3,
                 closest_to_Q4=q4)
        C["L4 collection: v5 reaches exactly 2, never above; each increment within 3 s after an approach to P1 / P3; "
          "both lums approached"] = (
            max((v for _, v in v5), default=0) == 2 and len(incs) == 2 and bool(a1) and bool(a3)
            and all(any(0 <= t - a <= 3 for a in a1 + a3) for t in incs))
        l4 = next((x["a"].get("lum4") for x in reversed(S) if x["a"].get("lum4")), None)
        C["L5 control: lum #4 at Q4 and alive at the last sample; generator never within 1 unit of Q4"] = (
            bool(l4) and math.dist(l4[0], tg["lum4"][3]) < 0.01 and l4[1] and (q4 is None or q4 > 1.0))
        D["lum_alive_last"] = {k: next((x["a"][k][1] for x in reversed(S) if x["a"].get(k)), None)
                               for k in ("lum1", "lum3", "lum4")}
    else:
        gkey = s["waypoints"][0][1]
        nodes = [nd["position"] for nd in m.graphs[gkey]["nodes"][:9] if nd]
        fs = [x["f"] for x in S if x.get("f")]
        used = any(math.dist(f, nd) < 3 for f in fs for nd in nodes)
        D["murfy_first"], D["murfy_last"] = (fs[0] if fs else None), (fs[-1] if fs else None)
        D["murfy_min_to_graph"] = min((math.dist(f, nd) for f in fs for nd in nodes), default=None)
        if used:
            res = {}
            for k in ("m0", "m1"):
                dn = min(math.dist(f, tg[k][3]) for f in fs)
                do = min(math.dist(f, tg[k][4]) for f in fs)
                res[k] = (round(dn, 3), round(do, 3))
            D["murfy_moved_nodes"] = res
            C["M4 route: Murfy reaches each moved node (<= 1.0) and >= 2.0 closer than to its original"] = all(
                dn <= 1.0 and do - dn >= 2.0 for dn, do in res.values())
        else:
            D["M4"] = "UNKNOWN: Murfy never within 3 units of graph nodes 0-8 in the window"
    ok6, judges = safety(run, row)
    C[f"{case}6 safety: haptics, M21 / M22 / M23 0, runner exit 0, no process left"] = ok6
    D["judges"] = judges
    res = {"invalid": invalid, "checks": C, "details": D, "pass": not invalid and all(C.values())}
    (work / "judge.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1, default=str))
    return 0 if res["pass"] else 1


def judge_combined(tag):
    g30, g27 = combined_setup()
    w = g30.WORK / tag / "M"
    m, s, p = project("C")
    pr = json.loads((w / "plan_result.json").read_text())
    C, D = {}, {}
    plan_text = (w / "plan_copy.txt").read_text(encoding="utf-8")
    txs = g27.p1.parse_plan(plan_text)["txs"]
    C["C1 plan: both mods active, one transaction (the patch's), remix not structural"] = (
        sorted(pr["active"]) == sorted([g30.MID, "g6p34.intro20-remix"]) and txs == [
            f"level-tx 2 intro_20 {g30.MID} {g30.WANT_TX}"] and list(pr["structural_active"]) == [g30.MID])
    rc = g30.judge(tag)
    v = json.loads((g30.WORK / f"verdict_{tag}.json").read_text())
    D["inherited"] = v
    C["C2 production activation (Q0) and inherited G6-P27 P1-P6 with N_RANGES 64"] = rc == 0
    rr = json.loads((w / "remix_reads.json").read_text())
    ok3, n3 = readback_ok_a1(rr["reads"], "C")   # amendment 1
    C[f"C3 remix readback of the {n3} in-place ranges over the transaction image (first and last)"] = ok3
    S = json.loads((w / "samples.json").read_text())
    f2 = [x["p"]["f2"] for x in S if "f2" in x["p"]]
    tg = {t[0]: t for t in targets_so(m, s)}
    g = m.graphs[(FAIRY20, 2, 2)]
    res = {}
    for n in range(6):
        k = f"c{n}"
        new = tg[k][3] if k in tg else g["nodes"][n]["position"]
        res[n] = {"new": round(min(math.dist(f, new) for f in f2), 3) if f2 else None}
        if k in tg:
            res[n]["original"] = round(min(math.dist(f, tg[k][4]) for f in f2), 3) if f2 else None
    D["graph_c"] = res
    C["C4 route: f2 within 0.30 of every moved node's new position (>= 2.0 from its original) and of nodes 1 / 2 / 4"] = (
        bool(f2) and all(r["new"] is not None and r["new"] <= 0.30 and r.get("original", 9) >= 2.0
                         for r in res.values()))
    cls = {}
    for label in ("cham0", "powerz1", "boing11"):
        seq = [x["p"].get("rx_" + label) for x in S if x["p"].get("rx_" + label)]
        cls[label] = classify(seq[0] if seq else None, seq[-1] if seq else None, tg[label][3], tg[label][4])
    D["classes"] = cls
    res_ = {"checks": C, "details": D, "pass": all(C.values())}
    (g30.WORK / f"g6p34_judge_{tag}.json").write_text(json.dumps(res_, indent=1, default=str) + "\n")
    print(json.dumps(res_, indent=1, default=str))
    return 0 if res_["pass"] else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["prepare"]:
        sys.exit(prepare())
    if len(a) == 3 and a[0] in ("run", "judge") and a[1] in ("L", "C", "M") and re.fullmatch(r"[a-z0-9]{1,8}", a[2]):
        if a[0] == "run":
            sys.exit(combined_run(a[2]) if a[1] == "C" else plain_run(a[1], a[2]))
        sys.exit(judge_combined(a[2]) if a[1] == "C" else judge_plain(a[1], a[2]))
    raise SystemExit(__doc__)
