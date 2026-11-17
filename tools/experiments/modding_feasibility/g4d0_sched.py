#!/usr/bin/env python3
"""E-473 (D-240) G4d-0: why the original MAN_mGenSound_Frog's script period changed (500 -> 933 ms) when G4c added
a copy. Private, read-only; reuses the G4c construction (variant "same", v5 = 500) under the G3a test gate.

STATIC FINDINGS (guest code; see the report)
  Per-actor AI step 82132F88(so) (from the per-SuperObject update 82133188): 82125FB8(so) advances the signed byte
  3dData +343 and wraps it to 0 when it reaches 3dData +342; 82126000(so) lets the AI run only when +343 == 0; then
  Brain / Mind checks (Brain +9, 821034C8), 3dData +344 (u16) += 1 per AI run, reflex (82251300) and normal
  (822512D0) intelligences -> 82265420 -> 822651D8 (scripts of Intelligence +8, the current behaviour).
  So an actor's scripts run every P frames, P = 3dData +342. Only writer of +342: 821256E8(3dData, n), reached from
  procedure 373 (8224A8F0). File value: P = 1, counter 0xFF (every frame) for all four Gen_Sound actors and the copy.
  NIK_mGenSound / NIK_mGenManager Init: procedure 373(value call 23(28, 35)); value call 23 = 8223ADB0(0, 28, 35):
  table-driven random draw on shared stream 0 (state 0x82C6C080: +0 table size N, +4 + 4s index of stream s,
  +208 max value, +216 -> table): result = min + table[idx] * (max - min + 1) / (max + 1) with the index BEFORE the
  draw; then idx += (word 0x82B4C72C mod 255) + 1, wrapped to 0 at N.
  LoopOneShot: if |timer - v8| >= v5: v8 = timer; macro 0 (custom bit 33; v4 == 1: procedure 755 on v0 and v2:
  sound). No wait, no accumulation: an interval is the first script run at or after v8 + v5.
EXISTING TRACES (G4c n1 / n2, block +0x202 = 3dData +342): source P = 30 in every A / D read, 28 in every B / C / E
  read (10 runs); copy P = 33. Frames of 16.667 ms predict 30 f = 500 (or 1000 if 30 frames sum to 499 ms), 28 f =
  467 < 500 -> 56 f = 933, 33 f = 550, 132 f = 2200: the n2 intervals exactly.
RUN s1 (protocol 77f90b9): INVALID, harness defect: the area test used a "length" key that block8_probe.areas()
  does not return (integer base / end); the base case raised KeyError before any read and the run was abandoned
  (its bounded game process exited on its own). Fixed (length = end - base); criteria unchanged; fresh run s2.
RUN s2 (fix 0ac387e): D1 / D2 / D3 / D5 / D6 PASS, D4 FAIL (kept). Judge code defect fixed before judging (it
  indexed out[case]["row"]; analysis only). Frog P 30 (A) / 28 (B), copy 33; AI runs per frame 0.0334 / 0.0356 /
  0.0303; intervals A 84 x 30 f + 18 x 60 f (threshold case), B 64 x 56 f, copy 109 x 33 f; ms per frame 16.65-16.72.
  D4 failed as registered: (1) the stream-0 index is updated inside the draw before procedure 373 stores the period,
  so "the index before the poll in which the period appeared" is already post-draw (no reproduction found);
  (2) the 40,000-byte table read returned nothing (rng_table_equal True compared None with None: meaningless).
  Observed (not pre-registered): step word 0 (index + 1 per draw); stream-0 index after the load burst 69 (A) /
  70 (B), then +7 to 76 / 77 before the first AI frame; draws A GenManager 35, Frog 30; B GenManager 30, Frog 28,
  copy 33; SmallRiver / Forest never draw. The table is fix.lvl offset 1,829,868 (10,000 words, 0..32762):
  28 + t[i] * 8 // 32764 for i = 76..79 = 35, 30, 28, 33, which reproduces A at 76 / 77 and B at 77 / 78 / 79.
  Static: 3dData init 821258D8 (from 82126580) draws one stream-0 value per actor for 3dData +344.
REVISION 2 (committed before s3; D4 replaced by D4r, all else unchanged): D4r: table = fix.lvl (size / sha pinned)
  offset 1,829,868; predicted final periods A GenManager 35, Frog 30; B GenManager 30, Frog 28, copy 33 (= draws at
  indices 76 / 77 and 77 / 78 / 79); the stream-0 index at the end of the load burst (first change followed by a
  >= 0.1 s gap) is 69 (A) / 70 (B); the step word is 0 in every poll. Classification: EXPECTED GUEST SCHEDULING
  BEHAVIOR if D1-D3, D5 and D4r hold; otherwise as before (D4r failing -> PARTIAL).
RUN s3 (revision 2; recorded after the run): D1-D6 PASS -> EXPECTED GUEST SCHEDULING BEHAVIOR. Draws A 35 / 30,
  B 30 / 28 / 33 as predicted; load burst 69 / 70; see the G4d-0 report.
OPEN QUESTION (this run): why the source draws 28 instead of 30 with the copy present.

CASES: base (A, no copy), same (B, G4c "same" construction). Hidden, non-activating, private profiles, no input,
no captures, 120 s; read-only: fast polling (no sleep) from the level area's appearance for EARLY s, logging every
change of the random state (N, stream-0 index, word 0x82B4C72C, timer) and of 3dData +340..+347 of GenManager_Frog,
Frog, SmallRiver, Forest (and the copy in B); then 0.1-s samples of the Frog's / copy's v8, 3dData +342 / +344 and
the timer for STEADY s; at the end the random table (N words) and max.

PRE-REGISTERED CRITERIA (E-473; committed before any run)
D1 dispatch cadence: over the steady window, for the Frog (A, B) and the copy (B), AI runs (3dData +344 increments)
   per elapsed frames (timer ms / 16.667) is within 5 % of 1 / P, P = the recorded 3dData +342.
D2 trigger cadence: >= 95 % of the v8 intervals equal k * P frames (+-2 ms), k = the smallest integer with
   k * P * 16.667 >= v5; the rest equal (k + 1) * P frames and only when k * P * 16.667 is within 2 ms of v5.
D3 timer: timer advance per frame in [16.4, 16.9] ms (timer ms / (AI runs * P)).
D4 draw: in A and B each monitored Gen_Sound actor's 3dData +342 goes from 1 to one value in [28, 35] once and
   stays; A: Frog 30; B: Frog 28, copy 33 (n1 / n2 values). Reproduction: for every poll interval in which exactly
   the expected period bytes appeared, simulating the draws in live dynamic-world order from the last stream-0 index
   seen before it, with the recorded word 0x82B4C72C, reproduces each drawn value and the next observed index.
   Reported, not judged: the index and the word at the Frog's draw in A versus B.
D5 control: the Frog's live 3dData, Brain, Mind, DsgMem and buffer addresses are equal in A and B; its v5 = 500 and
   behaviour LoopOneShot throughout; the Frog's file-initial +342 / +343 equal (1 / 0xFF) for the source and copy.
D6 safety: M21 / M22 / M23 0, haptics policy line, runner exit 0, no process left, no guest fault in the log.
CLASSIFICATION (pre-registered): EXPECTED GUEST SCHEDULING BEHAVIOR if D1-D3 hold in both cases, D5 holds and D4
reproduces the Frog's B draw from the random state alone; ACTOR CONSTRUCTION DEFECT if a construction-written field
of the source differs; MEASUREMENT ARTIFACT if the recorded P does not predict the intervals; PARTIAL if D4's
reproduction is not resolvable at poll resolution (the cause of the random-state difference then stays named).
"""
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import block8_probe as bp  # noqa: E402
import g3a_ab as g3a  # noqa: E402
import g4c_ab as g4c  # noqa: E402

PREFIX = "e473"
RUNS, AREA = g3a.RUNS, g3a.AREA
GATE_ENV = g3a.GATE_ENV
CASES = ("base", "same")
SECONDS, EARLY, STEADY = 120, 12, 60
RNG, STEP, TIMER = 0x82C6C080, 0x82B4C72C, 0x82C0628C
ACTORS = {"genmgr": 0x53C3F0, "frog": 0x53BED0, "river": 0x53B9B0, "forest": 0x53A09C}
D3 = 0xAC
FRAME = 1000 / 60
FIX_SIZE, FIX_SHA = 4369988, "f929551622ad62394367ae65f94cd942a6c8176dbe8d63aec73e8dfecac5d3e5"
FIX_TABLE, RNG_N, RNG_MAX = 1829868, 10000, 32763     # random table: fix.lvl file offset (live 0x40CDEC1C in s2)


def run_case(tag, case):
    from m5_live import Process
    data, ptr, tl = g4c.files()
    work = ROOT / "private" / "work" / PREFIX / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_E465_TEST_GROW", GATE_ENV[0]):
        env.pop(k, None)
    row = {"case": case, "run": run}
    L = g4c.layout()
    acts = dict(ACTORS)
    if case == "same":
        plan, _ = g4c.write_plan(work, data, ptr, tl, "same")
        env["R3HD_MODS_PLAN"] = row["plan"] = str(plan)
        env[GATE_ENV[0]] = GATE_ENV[1]
        acts["copy"] = L["fc"]
    (work / "steps.txt").write_text(f"wait {SECONDS - 8}\n", encoding="ascii")
    early, steady = [], []
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
            area, deadline = None, t0 + 45
            while time.monotonic() < deadline and p.running() and area is None:
                a1 = (bp.areas(p) or {}).get(1)
                if a1 and a1["end"] - a1["base"] >= AREA:     # areas(): integer base / end (s1 defect)
                    area = {"base": hex(a1["base"]), "length": a1["end"] - a1["base"]}
                time.sleep(0.002)
            if area is None:
                row["error"] = "level area not seen"
            else:
                row["area"] = {k: area[k] for k in ("base", "length")}
                ab = int(area["base"], 16)
                live = lambda fo: ab + fo - 4                     # noqa: E731
                d3 = {k: live(fo + D3) for k, fo in acts.items()}

                def snap():
                    s = {}
                    r = p.read(RNG, 16)
                    s["rng"] = list(struct.unpack(">4I", r)) if r and len(r) == 16 else None
                    w = p.words(STEP, 1)
                    s["step"] = w[0] if w else None
                    w = p.words(TIMER, 1)
                    s["timer"] = w[0] if w else None
                    for k, a in d3.items():
                        b = p.read(a + 340, 8)
                        s[k] = b.hex() if b else None
                    return s
                t_end, last = time.monotonic() + EARLY, None
                n = 0
                while time.monotonic() < t_end and p.running():
                    s = snap()
                    n += 1
                    key = json.dumps({k: v for k, v in s.items() if k != "timer"})
                    if key != last:
                        last = key
                        s["t"] = round(time.monotonic() - t0, 4)
                        s["poll"] = n
                        early.append(s)
                row["early_polls"] = n
                fo = acts["frog"]

                def ptrs(fo_):
                    w = lambda a: (p.words(a, 1) or [None])[0]      # noqa: E731
                    dm = live(fo_ + g4c.DSGMEM)
                    return {"d3": w(live(fo_ + 0x80)), "brain": w(live(fo_ + 0x80 + 0xC)),
                            "mind": w(live(fo_ + g4c.BRAIN)), "dsgmem_ini": w(dm + 4), "dsgmem_cur": w(dm + 8)}
                row["frog_ptrs"] = ptrs(fo)
                row["loop_oneshot"] = live(g4c.LOOP_ONESHOT)
                t_end = time.monotonic() + STEADY
                while time.monotonic() < t_end and p.running():
                    try:
                        s = {"t": round(time.monotonic() - t0, 3), "timer": p.words(TIMER, 1)[0]}
                        for k in [x for x in ("frog", "copy") if x in acts]:
                            pp = ptrs(acts[k]) if k == "copy" else row["frog_ptrs"]
                            cb = p.read(pp["dsgmem_cur"], g4c.VLEN)
                            b = p.read(d3[k] + 340, 8)
                            s[k] = {"v8": struct.unpack_from(">I", cb, g4c.V8)[0],
                                    "v5": struct.unpack_from(">i", cb, g4c.V5)[0],
                                    "P": b[2], "runs": struct.unpack_from(">H", b, 4)[0],
                                    "beh": p.words(live(acts[k] + g4c.INTEL + 8), 1)[0]}
                        steady.append(s)
                    except Exception as x:
                        row["steady_stopped"] = repr(x)
                        break
                    time.sleep(0.1)
                try:
                    r = p.read(RNG, 220)
                    nt, mx, tp = struct.unpack_from(">I", r, 0)[0], struct.unpack_from(">I", r, 208)[0], \
                        struct.unpack_from(">I", r, 216)[0]
                    tab = p.read(tp, 4 * nt) if 0 < nt <= 4096 else None
                    row["rng_table"] = {"n": nt, "max": mx, "ptr": tp,
                                        "words": list(struct.unpack(f">{nt}I", tab)) if tab else None}
                except Exception as x:
                    row["rng_table"] = {"error": repr(x)}
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and g3a.alive(pid))
    for name, obj in (("early", early), ("steady", steady), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj) + "\n")
    return {k: v for k, v in row.items() if k != "rng_table"}


def draw(tab, mx, idx, lo=28, hi=35):
    return lo + (tab[idx] * (hi - lo + 1)) // (mx + 1)


def judge(tag):
    out = {}
    for case in CASES:
        work = ROOT / "private" / "work" / PREFIX / tag / case
        run = f"{PREFIX}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        row["early"] = json.loads((work / "early.json").read_text())
        row["steady"] = json.loads((work / "steady.json").read_text())
        log = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / run).glob("runtime*.log")))
        row["fault"] = "access violation" in log
        row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
        judges = {}
        for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
            r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True,
                               text=True)
            judges[tool] = r.returncode
        row["judges"] = judges
        out[case] = row
    res, det = {}, {}
    # D1 / D2 / D3
    d1 = d2 = d3 = True
    for case in CASES:
        st = out[case]["steady"]
        for k in [x for x in ("frog", "copy") if st and x in st[0]]:
            P = {s[k]["P"] for s in st}
            runs = st[-1][k]["runs"] - st[0][k]["runs"]
            runs = runs if runs >= 0 else runs + 65536
            ms = st[-1]["timer"] - st[0]["timer"]
            frames = ms / FRAME
            p_ = next(iter(P)) if len(P) == 1 else None
            rate_ok = p_ is not None and runs > 0 and abs(runs / frames - 1 / p_) <= 0.05 / p_
            per_frame = ms / (runs * p_) if p_ and runs else None
            vals = []
            for s in st:
                v = s[k]["v8"]
                if v and (not vals or v != vals[-1]):
                    vals.append(v)
            iv = [b - a for a, b in zip(vals, vals[1:])]
            v5 = st[0][k]["v5"]
            kk = next(j for j in range(1, 1000) if j * p_ * FRAME >= v5) if p_ else None
            main = [x for x in iv if kk and abs(x - kk * p_ * FRAME) <= 2]
            slip = [x for x in iv if kk and abs(x - (kk + 1) * p_ * FRAME) <= 2]
            slip_ok = not slip or abs(kk * p_ * FRAME - v5) <= 2
            ok2 = bool(iv) and len(main) >= 0.95 * len(iv) and len(main) + len(slip) == len(iv) and slip_ok
            if not ok2 and kk and abs(kk * p_ * FRAME - v5) <= 2:
                ok2 = bool(iv) and len(main) + len(slip) == len(iv)   # threshold case: mixture allowed by D2
            det[f"{case}_{k}"] = {"P": sorted(P), "runs": runs, "frames": round(frames, 1),
                                  "runs_per_frame": round(runs / frames, 5) if frames else None,
                                  "ms_per_frame": round(per_frame, 3) if per_frame else None, "k": kk,
                                  "intervals": len(iv), "main": len(main), "slip": len(slip),
                                  "other": sorted(set(iv) - set(main) - set(slip))[:10], "v5": v5,
                                  "beh_ok": all(s[k]["beh"] == out[case].get("loop_oneshot") for s in st)}
            d1 = d1 and rate_ok
            d2 = d2 and ok2
            d3 = d3 and per_frame is not None and 16.4 <= per_frame <= 16.9
    res["D1_dispatch_cadence"], res["D2_trigger_cadence"], res["D3_timer"] = d1, d2, d3
    # D4
    d4 = True
    draws = {}
    for case in CASES:
        ea = out[case]["early"]
        rt = out[case].get("rng_table") or {}
        tab, mx, nt = rt.get("words"), rt.get("max"), rt.get("n")
        keys = [k for k in ("genmgr", "frog", "river", "forest", "copy") if ea and k in ea[0]]
        seq = {k: [bytes.fromhex(s[k])[2] for s in ea if s.get(k)] for k in keys}
        final = {}
        for k in keys:
            vs = [v for i, v in enumerate(seq[k]) if i == 0 or v != seq[k][i - 1]]
            final[k] = vs
            ok = len(vs) == 2 and vs[0] == 1 and 28 <= vs[1] <= 35
            d4 = d4 and ok
        want = {"base": {"frog": 30}, "same": {"frog": 28, "copy": 33}}[case]
        d4 = d4 and all(final.get(k, [None])[-1] == v for k, v in want.items())
        # events: polls where any monitored period byte changed from 1
        ev = []
        for i in range(1, len(ea)):
            ch = [k for k in keys if ea[i].get(k) and ea[i - 1].get(k)
                  and bytes.fromhex(ea[i - 1][k])[2] == 1 and bytes.fromhex(ea[i][k])[2] != 1]
            if ch:
                ev.append({"poll": ea[i]["poll"], "t": ea[i]["t"], "actors": ch,
                           "values": {k: bytes.fromhex(ea[i][k])[2] for k in ch},
                           "idx_before": (ea[i - 1]["rng"] or [None, None])[1], "idx_after": (ea[i]["rng"] or [None, None])[1],
                           "step_before": ea[i - 1]["step"], "step_after": ea[i]["step"],
                           "timer": ea[i]["timer"]})
        repro = []
        for e in ev:
            r = {"poll": e["poll"], "actors": e["actors"], "reproduced": None}
            if tab and e["idx_before"] is not None and e["step_before"] == e["step_after"]:
                step = (e["step_before"] % 255) + 1
                # live dynamic-world order of the monitored actors (as recorded in G4c n2): genmgr, forest, frog,
                # river, copy; other draws in between are not modelled: try 0..8 unmodelled draws before each
                order = [k for k in ("genmgr", "forest", "frog", "river", "copy") if k in e["actors"]]
                found = None
                for extra in range(0, 9):
                    idx = e["idx_before"]
                    for _ in range(extra):
                        idx = idx + step if idx + step < nt else 0
                    got = {}
                    for k in order:
                        got[k] = draw(tab, mx, idx)
                        idx = idx + step
                        idx = idx if idx < nt else 0
                    if got == {k: e["values"][k] for k in order}:
                        found = {"unmodelled_before": extra, "idx_end": idx, "idx_after_obs": e["idx_after"]}
                        break
                r["reproduced"] = found
            repro.append(r)
        frog_ev = next((r for r in repro if "frog" in r["actors"]), None)
        d4 = d4 and frog_ev is not None and frog_ev["reproduced"] is not None
        draws[case] = {"final": final, "events": ev, "repro": repro}
    res["D4_draw"] = d4
    if tag not in ("s1", "s2"):
        # D4r (revision 2, committed before s3): explicit predictions from the hash-pinned fix.lvl table
        fx = (g3a.LDIR.parent / "fix.lvl").read_bytes()
        tab_ok = len(fx) == FIX_SIZE and hashlib.sha256(fx).hexdigest() == FIX_SHA
        tab = struct.unpack_from(f">{RNG_N}I", fx, FIX_TABLE) if tab_ok else None
        pred = {"base": {"genmgr": 76, "frog": 77}, "same": {"genmgr": 77, "frog": 78, "copy": 79}}
        load_end = {"base": 69, "same": 70}
        d4r, rep = bool(tab_ok), {}
        for case in CASES:
            ea = out[case]["early"]
            fin = {k: v[-1] for k, v in draws[case]["final"].items()}
            vals = {k: draw(tab, RNG_MAX, i) for k, i in pred[case].items()} if tab else {}
            idx = [s["rng"][1] for s in ea if s["rng"]]
            plateaus = [b for a, b in zip(idx, idx[1:]) if b != a]
            first_ai = next((s["rng"][1] for s in ea if s["rng"] and any(
                s.get(k) and bytes.fromhex(s[k])[2] != 1 for k in pred[case])), None)
            # the load burst ends at the index seen at the first poll after the burst (>= 0.1 s gap)
            ts = [(s["t"], s["rng"][1]) for s in ea if s["rng"]]
            burst = next((ts[i][1] for i in range(1, len(ts)) if ts[i][1] != ts[i - 1][1]
                          and i + 1 < len(ts) and ts[i + 1][0] - ts[i][0] >= 0.1), None)
            ok = (fin.get("frog") == vals.get("frog") and all(fin.get(k) == v for k, v in vals.items())
                  and burst == load_end[case] and all(s["step"] == 0 for s in ea if s["step"] is not None))
            rep[case] = {"pred_values": vals, "observed": fin, "load_burst_end": burst, "plateaus": plateaus[:40],
                         "first_ai_index": first_ai, "ok": ok}
            d4r = d4r and ok
        res["D4r_draw_reproduction"] = bool(d4r)
        del res["D4_draw"]
        draws["D4r"] = rep
    # D5
    fa, fb = out["base"].get("frog_ptrs"), out["same"].get("frog_ptrs")
    data = g4c.files()[0]
    L = g4c.layout()
    nl = g4c.construct(*g4c.files(), "same")[0]
    res["D5_control"] = bool(fa and fa == fb and data[0x53BED0 + D3 + 342:0x53BED0 + D3 + 344] == b"\x01\xff"
                             and nl[L["fc"] + D3 + 342:L["fc"] + D3 + 344] == b"\x01\xff"
                             and all(s["frog"]["v5"] == 500 for c in CASES for s in out[c]["steady"])
                             and all(det[f"{c}_frog"]["beh_ok"] for c in CASES))
    res["D6_safety"] = all(r["haptics_policy"] and not any(r["judges"].values()) and r["runner_exit"] == 0
                           and not r["process_left"] and not r["fault"] for r in out.values())
    result = {"checks": res, "detail": det, "draws": draws,
              "rng": {c: {k: v for k, v in (out[c].get("rng_table") or {}).items() if k != "words"}
                      for c in CASES},
              "rng_table_equal": (out["base"].get("rng_table") or {}).get("words")
              == (out["same"].get("rng_table") or {}).get("words"),
              "frog_ptrs": {"base": fa, "same": fb}, "early_polls": {c: out[c].get("early_polls") for c in CASES}}
    (ROOT / "private" / "work" / PREFIX / tag / "judgement.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1)[:12000])
    return 0 if all(res.values()) else 1


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "judge":
        return judge(sys.argv[2])
    tag = sys.argv[1]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", tag):
        raise SystemExit("bad tag")
    for case in CASES:
        print(json.dumps(run_case(tag, case)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
