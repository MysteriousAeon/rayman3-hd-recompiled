#!/usr/bin/env python3
"""E-479 (D-246) G5-P3: same-process re-entry of the grown intro_10 through the title's own Pause -> Load, with the
G5-P3 snapshot runtime (g5p1_dev_gate.py apply, development build).

usage:
  g5p3_reentry.py TAG          hidden runs ra (node-13 structural mod) and rb (no mods), development build
  g5p3_reentry.py judge TAG    I1-I8 and the re-entry verdict
Outputs stay under private/work/e479/.

ROUTE (genuine title behaviour, no transition hack, no state patch): a copy of the registered save entry
`intro_10_fresh` (written by the title at name confirmation, names Intro_10; m12_save_entry.py) is the run's
disposable user root. Title -> Start -> Load -> slot (the M12 smoke sequence) loads intro_10 (entry 1). 20 s after
its file opens: Start -> the pause menu (opened 20 s into intro_10 in M18's run) -> Load -> slot -> "quit the current
game and load a new game?" -> left + A: the title tears intro_10 down and loads the saved level, intro_10, again in
the same process (entry 2; the mechanism VERIFIED for intro_15 in E-71). 30 s later: Start -> Exit Game -> left + A
-> the title screen (menumap). Guest-scoped input only (m9_license_run.py steps), no frames, no captures, hidden and
non-activating, muted, no physical pad, 220 s. No mutation of any game or save file; the save entry is never run on.
Observation (read-only): block-8 snapshot at every change of the area table; at each new intro_10 entry the graph is
walked once and the flight generator found; its variable 8 sampled every 0.1 s while intro_10 is loaded.

PROSPECTIVE PROTOCOL (committed before any run)
Build: g5p1_dev_gate.py apply (with the G5-P3 snapshot) + tools\\build_incremental.bat; production restored after.
  ra: plan = the node-13 neutral insertion (G5-P1 mod) only, compiled by resolve_all with session = run name (the
      harness ends the structural session after the run); R3HD_DEV_STRUCTURAL_TX=intro_10.
  rb: no plan, no development variable (control); same everything else.
Route validity: in both runs the load bursts contain menumap, intro_10, intro_10 in this order (m12 load_bursts) and
  both intro_10 entries are observed (area 1 of intro_10's length appears twice with a different area table between).
  Not valid -> the run pair is INVALID-ROUTE (no transaction verdict; at most one revision of step timing, then L5 /
  re-entry stays UNKNOWN).
Criteria:
  I1 transaction validation (ra): one `M33 mods state=active`, one `G5P1 level-tx active` with the plan's id; two
     `G5P3 tx snapshot` lines (intro_10.lvl image_bytes 7661948, intro_10.ptr 209140), both disk_reads=2; both
     before the first `G5P3 tx read` line.
  I2 immutable source (ra live + deterministic): no `M36 grow read` line naming intro_10.lvl / .ptr (every member
     read served from the image), no `G5P3 tx host_changed`; `G5P3 tx pass` >= 2 for each member (both entries read
     from the image); and private/work/e479/summary.json (g5p3_integrity.py negtest) pass.
  I3 repeated-open consistency (ra): entry 1 and entry 2 each walk 144 distinct nodes without problems, the new node
     at index 14, node 13's arc -> new node, identical changed words, identical intro_10 area (base, length).
  I4 no partial activation (deterministic): summary.json dev_all_pass (refusals before activation in both orders,
     no variable), prod_refused, budget_refused.
  I5 bounded overhead: summary.json i5_overhead; ra's two image_bytes sum 7,871,088 (<= 16 MiB).
  I6 gameplay (both entries): ra: >= 1 pass 13 -> N -> 14, every departure from node 13's waypoint goes to N and
     from N to node 14, variable 8 = N in >= 1 sample; rb: >= 1 pass 13 -> 14 and never N.
  I7 lifecycle integrity: every snapshot after the first valid one valid in both runs; with D(phase) = ra's
     snapshot minus rb's (free bytes, largest free, allocated / free chunks, every area's base, length, save
     words): D(menumap before entry 1) = 0; D(entry 1) = D(entry 2) = {intro_10 area length +112, free -112,
     largest -112, nothing else}; D(fix only between the entries) = 0; D(menumap after Exit Game) = 0. (Within-run
     equalities entry 1 = entry 2 and menumap before = after are recorded, not judged.)
  I8 safety: M21 / M22 / M23 0, haptics policy line, runner exit 0, no game process left, in both runs; ra's marker
     armed before the start and cleared after the controlled end; rb writes none.
  Re-entry verdict: VERIFIED (same process, this route) when the route is valid and I1-I3, I6-I8 PASS (I4 / I5
     deterministic PASS); otherwise as judged.
REVISION 1 (after run r1; r1 stays as judged: INVALID-ROUTE, both runs 0 harness entries):
  Cause: a harness defect, not the route. The live entry detection computed intro_10's area length as end - base + 4,
  but block8_probe's convention (and every recorded snapshot) is length = end - base, so no intro_10 entry was
  recognised: no graph walk, no generator, no samples. The title itself took the route in both runs (load bursts
  ubi, menumap, intro_10, intro_10, menumap; recorded block-8 snapshots show intro_10's area at 42.4 s and again at
  81.0 s, 7,661,944 bytes in ra), the controlled ends cleared ra's marker, exits 0, no process left. Fix: length =
  end - base. Nothing else changes (steps, criteria, thresholds). Fresh runs: r2 (ra, rb).
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
import m12_save_entry as m12  # noqa: E402

PREFIX = "e479"
WORK = ROOT / "private" / "work" / PREFIX
p1.WORK = WORK
LEVEL, ENV = p1.LEVEL, rm.STRUCT_ENV
RUNS = g3a.RUNS
SECONDS = 220
ENTRY = "intro_10_fresh"
AREA10 = (g3a.AREA, g3a.AREA + 112)
# G5-P5b (E-483): the structural mod of case ra (default: G5-P1's node-13 insertion, as E-479); g5p5b_lifecycle.py
# sets the dual mod and AREA10 for its own runs. Nothing else here changes.
PLAN_MOD = ("g5p1.neutral", lambda: [p1.igm("neutral")])
# G6-P1b (E-485): optional observation hooks (None = the graph walk and the variable-8 sample above, unchanged).
# OBSERVE(rd, p, ab) -> dict replaces the entry's graph walk (called at the same point, after the discovery probe);
# SAMPLER(p, ab) -> callable(gen, t) -> dict, made once per entry, replaces the 0.1 s variable-8 sample.
OBSERVE = None
SAMPLER = None
# G6-P1c (E-486): optional run hooks (defaults: G5-P3 behaviour, unchanged). EXTRA_MODS = [(id, overrides_fn)]
# installed after PLAN_MOD in case ra's mods root and required active with it; PLAN_MOD = None installs only those.
# TICK(p, profile, t) is called on every loop pass and once (p = None) after the runner exited; it only reads.
EXTRA_MODS = []
TICK = None
# G6-P10 (E-496): EARLY(p, ab, t0) -> list, called once at each new intro_10 entry before the discovery probe
# (read-only fast reads of fixed in-block addresses; stored as the entry's "early"). None = unchanged.
EARLY = None
DOWN = ["axis 301 -32767", "wait 0.3", "axis 301 0"]
LEFT = ["axis 300 -32767", "wait 0.3", "axis 300 0"]
STEPS = ["log VIDEOS\\ubi.bik result=00000000", "log menumap\\menumap.lvl result=00000000", "wait 10", "press 40",
         "wait 12", *DOWN, "wait 2", "press 44", "wait 8", "press 44",
         "log intro_10\\intro_10.lvl result=00000000 60",
         "wait 20", "press 40", "wait 3", *DOWN, "wait 1.2", *DOWN, "wait 1.5", "press 44", "wait 6", "press 44",
         "wait 3", *LEFT, "wait 1.5", "press 44",
         "wait 30", "press 40", "wait 3"] + sum([[*DOWN, "wait 1.2"] for _ in range(5)], []) + [
         "press 44", "wait 4", *LEFT, "wait 1.5", "press 44", "wait 18"]


def run_case(tag, case):
    from m5_live import Actor, Process
    work = WORK / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    profile = m12.PROFILES / run
    if work.exists() or (RUNS / run).exists() or profile.exists():
        raise SystemExit(f"exists: {work}, {RUNS / run} or {profile}")
    entry = m12.load_entry(ENTRY)
    if not m12.stored_profile_matches(entry):
        raise SystemExit("stored profile of the save entry no longer matches entry.json")
    work.mkdir(parents=True)
    shutil.copytree(m12.SAVES / ENTRY / "profile", profile)   # disposable copy; the entry itself is never run on
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_E465_TEST_GROW", "R3HD_G3A_TEST_GROW", ENV):
        env.pop(k, None)
    row = {"case": case, "run": run, "marker_before_start": ["none", None]}
    paths = None
    if case == "ra":
        paths = p1.fresh(f"run_{tag}_{case}")
        mods = ([PLAN_MOD] if PLAN_MOD else []) + list(EXTRA_MODS)
        with p1.dev_env():
            for mid, ov in mods:
                p1.install(paths, mid, ov())
            res = rm.resolve_all(paths, write_plan=paths["cache"], session=run)
        if sorted(res["active"]) != sorted(m[0] for m in mods):
            raise SystemExit(f"plan: {res['mods']}")
        plan = paths["cache"] / rm.PLAN_NAME
        shutil.copyfile(plan, work / "plan_copy.txt")
        row["plan_sha256"] = hashlib.sha256(plan.read_bytes()).hexdigest()
        row["marker_before_start"] = rm.read_structural_marker(paths)
        env["R3HD_MODS_PLAN"] = str(plan)
        env[ENV] = LEVEL
    (work / "steps.txt").write_text("\n".join(STEPS) + "\n", encoding="ascii")
    states, entries = [], []
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(SECONDS), "--play", "--user-root", run],
                                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
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
            last, t_end, gen, cur, next_sample = "none", t0 + SECONDS - 5, None, None, 0.0
            smp = None

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
                    a1 = (ar or {}).get(1)
                    ln = a1["end"] - a1["base"] if a1 else None   # block8_probe: length = end - base (revision 1)
                    if ln in AREA10 and cur is None:
                        cur = {"index": len(entries) + 1, "t": s["t"], "ab": a1["base"], "length": ln, "samples": []}
                        entries.append(cur)
                        gen = None
                        ab = a1["base"]
                        if EARLY is not None:   # G6-P10 hook
                            cur["early"] = EARLY(p, ab, t0)
                        disc = work / f"discovery_{cur['index']}.json"
                        q = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base,
                                            str(disc), "--regions"], cwd=ROOT, capture_output=True, text=True,
                                           timeout=180)
                        try:
                            if OBSERVE is not None:   # G6-P1b hook
                                cur["live"] = dict(t=round(time.monotonic() - t0, 3), **OBSERVE(rd, p, ab))
                                raise StopIteration
                            nodes, prob, hdr = g3b.walk_null(rd, ab + g3b.GRAPH - 4)
                            al = rd(ab + g3b.NODE13 - 4 + 0x18)
                            cur["live"] = {"t": round(time.monotonic() - t0, 3), "nodes": nodes, "problems": prob,
                                           "header": hdr, "arc13": {"count": rd(al + 8), "target": rd(rd(al) + 0xC)},
                                           "changed": [rd(ab + s_ - 4) for s_ in list(g3b.CHANGED) + [g3b.COUNT_AT]]}
                        except StopIteration:
                            pass
                        except Exception as x:
                            cur["live"] = {"error": repr(x)}
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
                            cur["generator"] = "not found"
                    elif ln not in AREA10 and cur is not None:
                        cur["left_t"] = s["t"]
                        cur, gen = None, None
                now = time.monotonic()
                if gen is not None and cur is not None and now >= next_sample:
                    try:
                        if smp is not None:   # G6-P1b hook
                            cur["samples"].append({"t": round(now - t0, 3), **smp(gen, round(now - t0, 3))})
                        else:
                            v = gen.dsg()
                            cur["samples"].append({"t": round(now - t0, 3), "v8": g3a.u32(*v[8])})
                    except Exception as x:
                        cur["sampling_stopped"] = type(x).__name__
                        gen = None
                    next_sample = now + 0.1
                if TICK is not None:   # G6-P1c hook
                    TICK(p, profile, round(now - t0, 3))
                time.sleep(0.005)
            if p.running():
                s = bp.snapshot(p)
                s.update(t=round(time.monotonic() - t0, 3), state="final", area_keys=sorted(bp.areas(p) or {}))
                states.append(s)
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"], row["process_detail"] = g3a.game_left(pid, run)   # E-483 revision 1
        if TICK is not None:   # G6-P1c hook: one read after the runner exited
            TICK(None, profile, round(time.monotonic() - t0, 3))
    controlled = row["runner_exit"] == 0 and not (RUNS / run / "r3hd_crash.txt").exists()
    row["controlled"] = controlled
    if paths is not None:
        if row["marker_before_start"][0] == "armed":
            row["session_end"] = rm.end_structural_session(paths, run, row["plan_sha256"], controlled)
        row["marker_after"] = rm.read_structural_marker(paths)[0]
    row["bursts"] = m12.load_bursts(m12.run_lines(RUNS / run)) if (RUNS / run).is_dir() else []
    for name, obj in (("states", states), ("entries", entries), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1, default=str) + "\n")
    return row


def run(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    g3b.N = 112
    for case in ("ra", "rb"):
        print(json.dumps(run_case(tag, case), default=str), flush=True)
    return 0


def brief(x):
    return None if not x else {"free": x["free_bytes"], "largest": x["largest_free"], "alloc": x["allocated_chunks"],
                               "free_chunks": x["free_chunks"],
                               "areas": {str(k): (v["base"], v["length"], v.get("save_words"))
                                         for k, v in x["areas"].items()}}


def diff(a, b):
    """ra minus rb over the judged fields (None when either is missing)."""
    if not a or not b:
        return None
    d = {k: a[k] - b[k] for k in ("free", "largest", "alloc", "free_chunks") if a[k] != b[k]}
    for k in sorted(set(a["areas"]) | set(b["areas"])):
        x, y = a["areas"].get(k), b["areas"].get(k)
        if x == y:
            continue
        if x and y and x[0] == y[0] and x[2] == y[2]:
            d[f"area{k}_length"] = x[1] - y[1]
        else:
            d[f"area{k}"] = [x, y]
    return d


def phases(states):
    valid = [x for x in states if "invalid" not in x]
    i0 = next((i for i, x in enumerate(states) if "invalid" not in x), None)
    walk_ok = i0 is not None and not any("invalid" in x for x in states[i0:])

    def kind(x):
        a1 = x["areas"].get("1")
        if a1 is None:
            return "fix" if set(x["areas"]) == {"0"} else "partial"
        return "intro_10" if a1["length"] in AREA10 else "menu"
    ks = [kind(x) for x in valid]
    e = [i for i, k in enumerate(ks) if k == "intro_10" and (i == 0 or ks[i - 1] != "intro_10")]
    out = {"walk_ok": walk_ok, "kinds": ks, "menu_before": None, "e1": None, "e2": None, "fix_between": None,
           "menu_after": None}
    if e:
        out["menu_before"] = next((valid[i] for i in range(e[0] - 1, -1, -1) if ks[i] == "menu"), None)
        out["e1"] = valid[e[0]]
    if len(e) >= 2:
        out["e2"] = valid[e[1]]
        out["fix_between"] = next((valid[i] for i in range(e[0] + 1, e[1]) if ks[i] == "fix"), None)
        out["menu_after"] = next((valid[i] for i in range(e[1] + 1, len(valid)) if ks[i] == "menu"), None)
    return out


def judge(tag):
    out = {}
    for case in ("ra", "rb"):
        w = WORK / tag / case
        r = json.loads((w / "row.json").read_text())
        r["states"] = json.loads((w / "states.json").read_text())
        r["entries"] = json.loads((w / "entries.json").read_text())
        log = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / r["run"]).glob("runtime*.log")))
        r["log"] = log
        r["judges"] = {t: subprocess.run([sys.executable, str(TOOLS / t), "--run", r["run"]], cwd=ROOT,
                                         capture_output=True, text=True).returncode
                       for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py")}
        r["phases"] = phases(r["states"])
        out[case] = r
    ra, rb = out["ra"], out["rb"]
    det = {}

    def route_ok(r):
        b = iter(r["bursts"])
        return (all(any(n == s for s in b) for n in ("menumap", "intro_10", "intro_10"))
                and len(r["entries"]) >= 2 and r["phases"]["e2"] is not None)
    route = {c: route_ok(out[c]) for c in out}
    det["route"] = route
    det["bursts"] = {c: out[c]["bursts"] for c in out}
    I = {}
    if not all(route.values()):
        res = {"verdict": "INVALID-ROUTE", "route": route, "bursts": det["bursts"],
               "entries": {c: len(out[c]["entries"]) for c in out}}
        (WORK / f"judgement_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
        print(json.dumps(res, indent=1, default=str))
        return 1
    log = ra["log"]
    lines = log.splitlines()
    tx = re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log)
    ptx = p1.parse_plan((WORK / tag / "ra" / "plan_copy.txt").read_text(encoding="utf-8"))["txs"]
    want_tx = [tuple(ptx[0].split(" ")[2:5])] if ptx else None
    snaps = re.findall(r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", log)
    first = {k: next((i for i, ln in enumerate(lines) if k in ln), None)
             for k in ("M33 mods state=active", "G5P3 tx snapshot", "G5P3 tx read")}
    I["I1_validation"] = (log.count("M33 mods state=active") == 1 and [tuple(x) for x in tx] == want_tx
                          and sorted((f, b, d) for f, _, b, d in snaps) == [("intro_10.lvl", "7661948", "2"),
                                                                          ("intro_10.ptr", "209140", "2")]
                          and None not in first.values() and first["M33 mods state=active"] < first["G5P3 tx read"]
                          and first["G5P3 tx snapshot"] < first["G5P3 tx read"])
    passes = re.findall(r"G5P3 tx pass file=(\S+) pass=(\d+)", log)
    neg = json.loads((WORK / "summary.json").read_text())
    member_grow_reads = re.findall(r"M36 grow read file=(intro_10\.(?:lvl|ptr))", log)
    det["tx_passes"] = {f: sum(1 for x, _ in passes if x == f) for f in ("intro_10.lvl", "intro_10.ptr")}
    I["I2_immutable_source"] = (not member_grow_reads and "G5P3 tx host_changed" not in log
                                and all(v >= 2 for v in det["tx_passes"].values()) and neg["pass"])
    ab = {i: e["ab"] for i, e in enumerate(ra["entries"][:2])}

    def walk_ok(e):
        lv, a = e.get("live", {}), e["ab"]
        return (lv.get("problems") == [] and len(lv.get("nodes", [])) == 144 == len(set(lv["nodes"]))
                and lv["header"]["count"] == 144 and lv["nodes"][14] == a + g3b.FN - 4
                and lv["arc13"] == {"count": 1, "target": a + g3b.FN - 4})
    e1, e2 = ra["entries"][0], ra["entries"][1]
    I["I3_repeated_open"] = (walk_ok(e1) and walk_ok(e2) and e1["live"]["changed"] == e2["live"]["changed"]
                             and (e1["ab"], e1["length"]) == (e2["ab"], e2["length"]) == (e1["ab"], g3a.AREA + 112))
    det["ab"] = ab
    I["I4_no_partial_activation"] = neg["res"]["dev_all_pass"] and neg["res"]["prod_refused"] and neg["res"][
        "budget_refused"]
    I["I5_bounded_overhead"] = neg["res"]["i5_overhead"] and sum(int(b) for _, _, b, _ in snaps) == 7871088

    def seq(e):
        s = []
        for x in e["samples"]:
            if not s or s[-1] != x["v8"]:
                s.append(x["v8"])
        return s

    def consume(e, structural):
        a = e["ab"]
        wn, w13, w14 = a + g3b.FW - 4, a + g3b.WP13 - 4, a + g3b.WP14 - 4
        s = seq(e)
        at_n = sum(1 for x in e["samples"] if x["v8"] == wn)
        if structural:
            dep13 = [b for x, b in zip(s, s[1:]) if x == w13]
            depn = [b for x, b in zip(s, s[1:]) if x == wn]
            n = sum(1 for i in range(len(s) - 2) if s[i] == w13 and s[i + 1] == wn and s[i + 2] == w14)
            return {"passes": n, "at_n": at_n, "dep13": len(dep13), "ok": n >= 1 and at_n >= 1
                    and all(b == wn for b in dep13) and all(b == w14 for b in depn)}
        n = sum(1 for x, b in zip(s, s[1:]) if x == w13 and b == w14)
        return {"passes": n, "at_n": at_n, "ok": n >= 1 and at_n == 0}
    cons = {"ra": [consume(e, True) for e in ra["entries"][:2]], "rb": [consume(e, False) for e in rb["entries"][:2]]}
    det["consumption"] = cons
    I["I6_gameplay"] = all(c["ok"] for v in cons.values() for c in v) and not any(
        e.get("generator") for r in out.values() for e in r["entries"][:2])
    pa, pb = ra["phases"], rb["phases"]
    D = {k: diff(brief(pa[k]), brief(pb[k])) for k in ("menu_before", "e1", "e2", "fix_between", "menu_after")}
    det["D"] = D
    det["phases"] = {c: {k: brief(v) if isinstance(v, dict) else v for k, v in out[c]["phases"].items()
                         if k != "kinds"} for c in out}
    det["within"] = {c: {"e1_eq_e2": brief(out[c]["phases"]["e1"]) == brief(out[c]["phases"]["e2"]),
                         "menu_before_eq_after": brief(out[c]["phases"]["menu_before"])
                         == brief(out[c]["phases"]["menu_after"])} for c in out}
    want = {"area1_length": 112, "free": -112, "largest": -112}
    I["I7_lifecycle"] = (pa["walk_ok"] and pb["walk_ok"] and D["menu_before"] == {} and D["e1"] == want
                         and D["e2"] == want and D["fix_between"] == {} and D["menu_after"] == {})
    mb = ra["marker_before_start"]
    I["I8_safety"] = (all("M23 haptics policy=suppressed physical_pad_drivers=none" in r["log"]
                          and not any(r["judges"].values()) and r["runner_exit"] == 0 and not r["process_left"]
                          for r in out.values())
                      and mb[0] == "armed" and mb[1]["session"] == ra["run"] and mb[1]["plan_sha256"] == ra["plan_sha256"]
                      and ra["controlled"] is True and ra["session_end"]["cleared"] is True
                      and ra["marker_after"] == "none" and rb["marker_before_start"][0] == "none")
    ok = all(v is True for v in I.values())
    verdict = "RE-ENTRY VERIFIED (same process, Pause -> Load route)" if ok else "NOT PASSED"
    res = {"route": route, "I": I, "verdict": verdict, "details": det,
           "judges": {c: r["judges"] for c, r in out.items()}}
    (WORK / f"judgement_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("route", "I", "verdict")}, indent=1))
    print(json.dumps({k: det[k] for k in ("D", "within", "consumption", "tx_passes", "bursts")}, indent=1,
                     default=str)[:4000])
    return 0 if ok else 1


def main():
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
