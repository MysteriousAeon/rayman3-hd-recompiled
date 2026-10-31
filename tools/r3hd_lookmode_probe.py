#!/usr/bin/env python3
"""Look Mode signal probe (D-143 step 1): which read-only guest word tells that the title has actually entered Look
Mode (held Y, first-person view), and how the title's Look Mode answers the left stick. Hidden, muted, non-activating
runs; scheduled XAM input only (tools/m6_test_input.h codes: Y 19, A 44, Start 40, LT 20, B 42, RT 8, analog 300 lx /
301 ly); ReadProcessMemory only, no guest write, no physical device.

    python tools/r3hd_lookmode_probe.py run RUN LEVEL [--seconds 110]        isolated test-only level (D-040)
    python tools/r3hd_lookmode_probe.py load RUN [--entry intro_15_start]    genuine save from the title (working copy)
    python tools/r3hd_lookmode_probe.py analyze RUN... [--out NAME]
    python tools/r3hd_lookmode_probe.py agree RUN...                         the E-326 flag against the camera
    python tools/r3hd_lookmode_probe.py word --address ADDR... -- RUN...      one word's values per run and phase
    python tools/r3hd_lookmode_probe.py curve RUN LEVEL [--plan standard|repeat|calibrated|persist]
    python tools/r3hd_lookmode_probe.py curve-analyze RUN... | curve-table RUN...   step 2: Look Mode stick response

Ground truth is the camera, not the button: a sample is "look" when the camera actor (StdCam) is within LOOK_DIST of
Rayman (Look Mode puts it at his head, E-324: 9.5 -> 1.8 units). Both runs sample the image's data range
82830000..82CB0000 (word diffs, ~10 Hz), the camera matrix and Rayman. `run` holds Y in plain play (twice, with
left-stick pulses for the measurement) and in negative cases (a short tap, mid-jump, walking, photo mode, lock-on);
the WATCH words are recorded in every sample; `load`
holds Y during a save's opening scene and again after it. `analyze` lists words whose value in every "look" sample
differs from every other sample (transitions excluded), per run and across all runs, with each candidate's lag
against the camera; and the left-stick measurement. Output under private/work/lookmode (addresses, values, angles).
"""
import argparse
import json
import math
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402
import m19_campaign_check as m19  # noqa: E402
import m5_live as live  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
OUT = ROOT / "private" / "work" / "lookmode"
LO, HI = 0x82830000, 0x82CB0000
BLOCK = 4096
LOOK_DIST = 3.0
Y, A, START, LT, B, RT, LX, LY = 19, 44, 40, 20, 42, 8, 300, 301
# The Look Mode candidates of E-326, recorded in every sample (a word that never changes is otherwise not in a run)
WATCH = [0x82C07D5C, 0x82C5C770, 0x82C7E2F0]
FULL = 32767
# (seconds after sampling starts, phase, code, value); phase None = no new phase
PLAN = [
    (4.0, "y_hold_1", Y, 1), (8.0, "idle", Y, 0),
    (12.0, "y_hold_2", Y, 1),
    (14.0, "m_lx_right", LX, FULL), (14.4, None, LX, 0),
    (16.0, "m_lx_left", LX, -FULL), (16.4, None, LX, 0),
    (18.0, "m_ly_up", LY, FULL), (18.4, None, LY, 0),
    (20.0, "m_ly_down", LY, -FULL), (20.4, None, LY, 0),
    (22.0, "m_lx_half", LX, FULL // 2), (22.4, None, LX, 0),
    (24.0, "m_lx_07", LX, int(FULL * 0.7)), (24.4, None, LX, 0),
    (26.0, "m_lx_pulse", LX, FULL), (26.1, None, LX, 0),
    (28.0, "idle", Y, 0),
    (32.0, "neg_y_tap", Y, 1), (32.1, None, Y, 0),
    (35.0, "neg_jump", A, 1), (35.2, None, A, 0), (35.3, None, Y, 1), (36.8, None, Y, 0),
    (40.0, "neg_walk", LX, FULL), (41.0, None, Y, 1), (42.5, None, Y, 0), (43.0, None, LX, 0),
    (46.0, "neg_photo", LT, 1), (46.2, None, LT, 0), (48.5, None, Y, 1), (50.5, None, Y, 0),
    (52.0, None, B, 1), (52.2, None, B, 0),
    (56.0, "y_hold_3", Y, 1), (59.0, "idle", Y, 0),
    (62.0, "neg_lockon", RT, 1), (63.0, None, Y, 1), (65.0, None, Y, 0), (65.5, None, RT, 0),
    (69.0, "end", None, None),
]
LOAD_STEPS = [  # tools/m12_save_entry.py load_steps (title -> Load -> slot), then idle
    r"log VIDEOS\ubi.bik result=00000000", r"log menumap\menumap.lvl result=00000000",
    "wait 10", "press 40", "wait 12", "axis 301 -32767", "wait 0.3", "axis 301 0",
    "wait 2", "press 44", "wait 8", "press 44", "wait 200",
]
LOAD_PLAN = [  # seconds after the level's .lvl open + sampling start
    (4.0, "scene_quiet", None, None),
    (10.0, "neg_scene_y", Y, 1), (14.0, "scene_quiet", Y, 0),
    (20.0, "neg_scene_y", Y, 1), (24.0, "scene_quiet", Y, 0),
    (90.0, "y_hold_play", Y, 1), (94.0, "idle", Y, 0),
    (98.0, "end", None, None),
]


def actor(p, actors_json, model):
    for x in json.loads(actors_json.read_text(encoding="utf-8"))["actors"]:
        try:
            a = live.Actor(p, int(x["so"], 16))
        except (TypeError, IndexError, ValueError, OSError):
            continue
        if a.alive() and a.model == model:
            return a
    return None


def cam_state(p, cam, ray):
    m = p.read(cam.matrix, 0x40) if cam else None
    rp = ray.position() if ray else None
    if not m or not rp:
        return None
    f = struct.unpack_from(">15f", m, 4)
    if not all(math.isfinite(v) for v in f):
        return None
    return {"cols": [list(f[0:3]), list(f[4:7]), list(f[8:11])], "cam": list(f[12:15]), "ray": list(rp)}


def sampler(p, cam, ray, rec, stop, t0):
    prev = p.read(LO, HI - LO)
    rec["base"] = list(struct.unpack(f">{(HI - LO) // 4}I", prev))  # kept in memory only; not written
    while not stop.is_set():
        t = round(time.monotonic() - t0, 3)
        cur = p.read(LO, HI - LO)
        if cur is None:
            break
        diff = {}
        for off in range(0, len(cur), BLOCK):
            a, b = cur[off:off + BLOCK], prev[off:off + BLOCK]
            if a != b:
                for i, (x, y) in enumerate(zip(struct.iter_unpack(">I", a), struct.iter_unpack(">I", b))):
                    if x != y:
                        diff[(off >> 2) + i] = x[0]
        prev = cur
        st = cam_state(p, cam, ray)
        watch = [struct.unpack_from(">I", cur, w - LO)[0] for w in WATCH]
        rec["samples"].append({"t": t, "diff": diff, "cam": st, "comport": ray.comport() if ray else None,
                               "watch": watch})
        time.sleep(0.05)


def drive(run_dir, rec, plan, p, cam, ray, t0):
    stop = threading.Event()
    th = threading.Thread(target=sampler, args=(p, cam, ray, rec, stop, t0), daemon=True)
    th.start()
    for when, phase, code, value in plan:
        time.sleep(max(0.0, when - (time.monotonic() - t0)))
        if code is not None:
            with (run_dir / "schedule.txt").open("a", encoding="ascii", newline="") as s:
                s.write(f"0 {code} {value}\n")
        rec["events"].append({"t": round(time.monotonic() - t0, 3), "phase": phase, "code": code, "value": value})
    stop.set()
    th.join(timeout=10)


def attach_level(run_dir, level, game, log, rec, settle):
    if not m19.wait_for_log(run_dir, f"{level}\\{level}.lvl result=00000000", game, 120):
        return None, [f"{level} did not open"]
    time.sleep(settle)
    pid, base = m19.attach(run_dir)
    actors = run_dir / f"actors_{level}.json"
    subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(actors), "--regions"],
                   cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    p = live.Process(pid, int(base, 16))
    ray, cam = actor(p, actors, "YLT_RaymanModel"), actor(p, actors, "StdCam")
    if not ray or not cam:
        return None, ["rayman or camera actor not found"]
    rec["player"] = {"so": f"{ray.so:08X}", "camera_so": f"{cam.so:08X}"}
    return (p, cam, ray), []


def save(rec, reasons):
    OUT.mkdir(parents=True, exist_ok=True)
    base = rec.pop("base", None) or []
    changed = {int(i) for s in rec["samples"] for i in s["diff"]}
    rec["initial"] = {str(i): base[i] for i in sorted(changed) if i < len(base)}  # changed words only
    rec["samples"] = [dict(s, diff={str(k): v for k, v in s["diff"].items()}) for s in rec["samples"]]
    (OUT / f"{rec['run']}.json").write_text(json.dumps(rec), encoding="utf-8")
    print("R3HD_LOOKMODE_PROBE", json.dumps({"run": rec["run"], "samples": len(rec["samples"]), "reasons": reasons}))
    return 1 if reasons else 0


def cmd_run(a) -> int:
    rec = {"run": a.run, "level": a.level, "kind": "isolated", "events": [], "samples": []}

    def beside(run_dir, game, log):
        got, reasons = attach_level(run_dir, a.level, game, log, rec, 10)
        if reasons:
            return reasons
        drive(run_dir, rec, PLAN, *got, time.monotonic())
        return []
    reasons = m19.hidden_run(a.run, ROOT / "config" / "m14" / "idle110.txt", a.seconds, test_level=a.level, beside=beside)
    return save(rec, reasons)


def cmd_load(a) -> int:
    entry = m12.load_entry(a.entry)
    level = entry["level_key"].lower()
    rec = {"run": a.run, "level": level, "kind": f"genuine save {a.entry} (working copy)", "events": [], "samples": []}
    work = m12.PROFILES / a.run
    if work.exists():
        raise SystemExit(f"profile {work} already exists")
    if not m12.stored_profile_matches(entry):
        raise SystemExit(f"stored profile of {a.entry} no longer matches entry.json")
    shutil.copytree(m12.SAVES / a.entry / "profile", work)
    OUT.mkdir(parents=True, exist_ok=True)
    steps = OUT / f"steps_{a.run}.txt"
    steps.write_text("\n".join(LOAD_STEPS) + "\n", encoding="ascii")

    def beside(run_dir, game, log):
        got, reasons = attach_level(run_dir, level, game, log, rec, 2)
        if reasons:
            return reasons
        drive(run_dir, rec, LOAD_PLAN, *got, time.monotonic())
        return []
    reasons = m19.hidden_run(a.run, steps, a.seconds, user_root=a.run, beside=beside)
    return save(rec, reasons)


# ------------------------------------------------------------------------------------------------ analysis
def phases(rec):
    ev = [e for e in rec["events"] if e["phase"]]
    return [(e["t"], ev[i + 1]["t"] if i + 1 < len(ev) else 1e9, e["phase"]) for i, e in enumerate(ev)]


def phase_at(ph, t):
    return next((n for t0, t1, n in ph if t0 <= t < t1), "before")


def dist(s):
    c = s.get("cam")
    return math.dist(c["cam"], c["ray"]) if c else None


def series(rec):
    """word index -> [(t, value)] for every word that changed in the run (the first entry is the value before)."""
    out = {int(i): [(-1.0, v)] for i, v in rec.get("initial", {}).items()}
    for s in rec["samples"]:
        for i, v in s["diff"].items():
            out.setdefault(int(i), []).append((s["t"], v))
    return out


def value_at(seq, t):
    cur = None
    for tt, v in seq:
        if tt <= t:
            cur = v
        else:
            break
    return cur


def truth(rec):
    """[(t, look)] with look = camera within LOOK_DIST of Rayman; samples within 0.35 s of a truth edge are None."""
    raw = [(s["t"], (dist(s) is not None and dist(s) < LOOK_DIST)) for s in rec["samples"] if dist(s) is not None]
    edges = [raw[i][0] for i in range(1, len(raw)) if raw[i][1] != raw[i - 1][1]]
    return [(t, None if any(abs(t - e) < 0.35 for e in edges) else lk) for t, lk in raw], edges


def word_sets(rec, seq, tr):
    look, other = set(), set()
    for t, lk in tr:
        if lk is None:
            continue
        v = value_at(seq, t)
        if v is None:
            continue
        (look if lk else other).add(v)
    return look, other


def yaw_pitch(rows):
    rows = [r for r in rows if r]
    if len(rows) < 2:
        return None, None, None
    k = max(range(3), key=lambda i: math.hypot(rows[0]["cols"][i][0], rows[0]["cols"][i][1]))
    yaws = [math.degrees(math.atan2(r["cols"][k][1], r["cols"][k][0])) for r in rows]
    total = sum((b - a + 180.0) % 360.0 - 180.0 for a, b in zip(yaws, yaws[1:]))
    # pitch of the most vertical-changing axis, as an angle
    def elev(c):
        return math.degrees(math.atan2(c[2], math.hypot(c[0], c[1])))
    pitch = max((elev(rows[-1]["cols"][i]) - elev(rows[0]["cols"][i]) for i in range(3)), key=abs)
    return round(total, 1), round(pitch, 1), round(math.dist(rows[0]["ray"], rows[-1]["ray"]), 2)


def cmd_analyze(a) -> int:
    recs = [json.loads((OUT / f"{r}.json").read_text(encoding="utf-8")) for r in a.runs]
    per_run, cands = [], None
    for rec in recs:
        ph, sr = phases(rec), series(rec)
        tr, edges = truth(rec)
        looks = sum(1 for _, lk in tr if lk)
        by_phase = {}
        for s in rec["samples"]:
            d = dist(s)
            if d is not None:
                by_phase.setdefault(phase_at(ph, s["t"]), []).append(d < LOOK_DIST)
        row = {"run": rec["run"], "level": rec["level"], "kind": rec["kind"], "samples": len(rec["samples"]),
               "look_samples": looks, "truth_edges": [round(e, 2) for e in edges],
               "look_fraction_by_phase": {k: round(sum(v) / len(v), 2) for k, v in by_phase.items()},
               "comports_by_phase": {}}
        for s in rec["samples"]:
            row["comports_by_phase"].setdefault(phase_at(ph, s["t"]), set()).add(s["comport"])
        row["comports_by_phase"] = {k: sorted(x for x in v if x) for k, v in row["comports_by_phase"].items()}
        found = {}
        for i, seq in sr.items():
            look, other = word_sets(rec, seq, tr)
            if looks and look and other and not (look & other):
                found[i] = (look, other)
            elif not looks:  # a run without Look Mode: remember every value the word took
                found[i] = (set(), {v for _, v in seq})
        row["separating_words"] = len(found) if looks else None
        per_run.append((rec, row, found, sr, tr))
    positive = [x for x in per_run if x[1]["look_samples"]]
    if positive:
        cands = set.intersection(*(set(x[2]) for x in positive))
    else:
        cands = set()
    result = []
    for i in sorted(cands):
        look_vals = set.union(*(x[2][i][0] for x in positive))
        other_vals = set.union(*(x[2][i][1] for x in positive))
        ok_neg = True
        for rec, row, found, sr, tr in per_run:  # negative runs: the word must never show a look value outside look
            if row["look_samples"]:
                continue
            seq = sr.get(i)
            if seq and ({v for _, v in seq} & look_vals):
                ok_neg = False
        lags = []
        for rec, row, found, sr, tr in positive:
            seq = sr[i]
            for e in row["truth_edges"]:
                ch = [tt for tt, _ in seq if abs(tt - e) < 1.5]
                if ch:
                    lags.append(round(min(ch, key=lambda tt: abs(tt - e)) - e, 2))
        result.append({"address": f"{LO + i * 4:08X}", "look_value_count": len(look_vals),
                       "look_values": sorted(look_vals)[:6],
                       "other_values": sorted(other_vals)[:6], "other_value_count": len(other_vals),
                       "negative_runs_clean": ok_neg, "edge_lags_s": lags})
    result.sort(key=lambda r: (not r["negative_runs_clean"], r["look_value_count"], r["other_value_count"]))
    measure = {}
    for rec, row, *_ in per_run:
        ph = phases(rec)
        for t0, t1, n in ph:
            if n.startswith("m_") or n in ("y_hold_play",):
                rows = [s["cam"] for s in rec["samples"] if t0 <= s["t"] < t0 + 1.2]
                yw, pt, mv = yaw_pitch(rows)
                measure.setdefault(n, []).append({"run": rec["run"], "yaw": yw, "pitch": pt, "ray_moved": mv})
    out = {"runs": [x[1] for x in per_run], "candidates": result[:40], "candidate_count": len(result),
           "left_stick_in_look_mode": measure}
    name = a.out or "_".join(a.runs)[:80]
    (OUT / f"analysis_{name}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1)[:9000])
    return 0


def cmd_word(a) -> int:
    """One word's values per run: in look / other samples, and per phase (the value set seen in that phase)."""
    out = {}
    for r in a.runs:
        rec = json.loads((OUT / f"{r}.json").read_text(encoding="utf-8"))
        ph, tr = phases(rec), truth(rec)[0]
        idx = {f"{LO + i * 4:08X}": i for i in [(int(x, 16) - LO) // 4 for x in a.address]}
        row = {}
        for name, i in idx.items():
            seq = [(-1.0, rec.get("initial", {}).get(str(i)))] if str(i) in rec.get("initial", {}) else []
            seq += [(s["t"], s["diff"][str(i)]) for s in rec["samples"] if str(i) in s["diff"]]
            look, other, by = set(), set(), {}
            for t, lk in tr:
                v = value_at(seq, t) if seq else "unchanged"
                by.setdefault(phase_at(ph, t), set()).add(f"{v:08X}" if isinstance(v, int) else str(v))
                if lk is not None and isinstance(v, int):
                    (look if lk else other).add(f"{v:08X}")
            row[name] = {"look": sorted(look), "other": sorted(other)[:8], "by_phase": {k: sorted(v)[:6] for k, v in by.items()}}
        out[r] = row
    print(json.dumps(out, indent=1))
    return 0


# ------------------------------------------------------------------------------------------------ step 2: curve
# D-143 step 2 (E-327): the title's Look Mode response to the left stick, frame by frame. The M17 frame trace
# (R3HD_FRAME_TRACE, read-only, one record per guest frame) watches the camera matrix, Rayman's matrix and the flag;
# every schedule write is stamped on the same QueryPerformanceCounter clock (time.perf_counter on Windows).
H_MAGS = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
V_MAGS = [0.2, 0.3, 0.4, 0.5, 0.7, 1.0]
PULSES = [0.017, 0.033, 0.05, 0.083, 0.133, 0.2]


def curve_plan(kind="standard"):
    """[(name, [(axis, value)...], hold_s, gap_s)]; values are fractions of full deflection (ly + = up).
    `repeat` measures the same partial deflections at several times and after different histories (E-327)."""
    if kind == "calibrated":  # after a full walk outside Look Mode (cmd_curve does it before Y): the operative curve
        p = []
        mags = [round(0.30 + 0.05 * i, 2) for i in range(15)]
        for m in mags:
            for sg in (1, -1):
                p.append((f"c_h{sg * m:+.2f}", [(LX, sg * m)], 0.6, 0.5))
        for m in mags:
            for sg in (1, -1):
                p.append((f"c_v{sg * m:+.2f}", [(LY, sg * m)], 0.2, 0.6))
        return p
    if kind == "repeat":
        p = []
        for rnd in range(3):
            p.append((f"r{rnd}_const_0.50", [(LX, 0.5)], 0.8, 0.6))
            for m in (0.4, 0.5, 0.6, 1.0, 0.5):
                for sg in (1, -1):
                    p.append((f"r{rnd}_h{sg * m:+.2f}", [(LX, sg * m)], 0.6, 0.6))
            p.append((f"r{rnd}_v+0.50", [(LY, 0.5)], 0.25, 0.6))
            p.append((f"r{rnd}_v-0.50", [(LY, -0.5)], 0.25, 0.6))
            p.append((f"r{rnd}_duty50_full", "duty", 1.0, 0.8))
            p.append((f"r{rnd}_after_duty_0.50", [(LX, 0.5)], 0.8, 0.6))
            p.append((f"r{rnd}_same_sign_0.50", [(LX, 0.5)], 0.8, 0.6))
        return p
    p = []
    for m in H_MAGS:
        for s in (1, -1):
            p.append((f"h{s * m:+.2f}", [(LX, s * m)], 0.8, 0.6))
    for m in V_MAGS:
        for s in (1, -1):
            p.append((f"v{s * m:+.2f}", [(LY, s * m)], 0.25, 0.6))
    p += [("vlim_up", [(LY, 1.0)], 2.0, 0.8), ("vlim_down", [(LY, -1.0)], 3.0, 0.8), ("vlim_back", [(LY, 1.0)], 0.6, 0.8)]
    for d in PULSES:
        for s in (1, -1):
            p.append((f"pulse{s * d * 1000:+.0f}ms", [(LX, float(s))], d, 0.6))
    p += [("duty50_full", "duty", 1.0, 0.8), ("const_0.50", [(LX, 0.5)], 1.0, 0.8), ("const_1.00_half", [(LX, -1.0)], 0.5, 0.8)]
    p += [("diag_0.7", [(LX, 0.7), (LY, 0.7)], 0.25, 0.8), ("diag_1.0", [(LX, -1.0), (LY, -1.0)], 0.25, 0.8)]
    return p


def cmd_curve(a) -> int:
    import m17_frame_trace as m17
    OUT.mkdir(parents=True, exist_ok=True)
    trace = OUT / f"{a.run}.trace"
    if trace.exists():
        raise SystemExit(f"{trace} exists")
    rec = {"run": a.run, "level": a.level, "plan": a.plan, "segments": [], "events": []}

    def beside(run_dir, game, log):
        got, reasons = attach_level(run_dir, a.level, game, log, rec, 10)
        if reasons:
            return reasons
        p, cam, ray = got
        rec["watch"] = {"camera": cam.matrix, "rayman": ray.matrix, "flag": FLAG}
        m17.write_watch(trace, [(cam.matrix, 0x40), (ray.matrix, 0x40), (FLAG, 4)])
        sched = run_dir / "schedule.txt"

        def put(code, value):
            with sched.open("a", encoding="ascii", newline="") as s:
                s.write(f"0 {code} {value}\n")
            rec["events"].append((time.perf_counter(), code, value))
        time.sleep(1.0)
        if a.plan == "persist":  # E-327: per-direction calibration, and does it survive a death and level reload?

            def measure(name):  # +0.5 then -0.5 in Look Mode
                put(Y, 1)
                time.sleep(1.5)
                for sg in (1, -1):
                    t0 = time.perf_counter()
                    put(LX, sg * int(0.5 * FULL))
                    time.sleep(0.4)
                    put(LX, 0)
                    rec["segments"].append({"name": f"{name}_{'+' if sg > 0 else '-'}0.50", "start": t0,
                                            "end": time.perf_counter()})
                    time.sleep(0.6)
                put(Y, 0)
                time.sleep(1.0)

            def step(v, d):
                put(LX, v)
                time.sleep(d)
                put(LX, 0)
                time.sleep(0.8)
            time.sleep(18.0)  # the spawn scene (YAM_C_Init, E-326)
            measure("fresh")
            step(-FULL, 0.3)  # full left only (away from the water)
            measure("neg_only")
            step(FULL, 0.25)  # and full right
            measure("both")
            put(LX, FULL)  # into the toxic water: death and level reload (E-326 swamp_60)
            t0 = time.perf_counter()
            time.sleep(3.0)
            put(LX, 0)
            rec["segments"].append({"name": "death_walk", "start": t0, "end": time.perf_counter()})
            time.sleep(30.0)
            measure("after_reload")
            time.sleep(8.0)
            measure("after_reload_late")
            return []
        if a.plan == "calibrated":  # full deflection on both axes in normal play first (Rayman walks a step each way)
            for ax, v in ((LX, FULL), (LX, -FULL), (LY, FULL), (LY, -FULL)):
                put(ax, v)
                time.sleep(0.3)
                put(ax, 0)
                time.sleep(0.4)
            time.sleep(1.0)
        put(Y, 1)
        time.sleep(1.5)
        for name, axes, hold, gap in curve_plan(a.plan):
            t0 = time.perf_counter()
            if axes == "duty":  # 50 ms full / 50 ms neutral, ten cycles
                for _ in range(10):
                    put(LX, FULL)
                    time.sleep(0.05)
                    put(LX, 0)
                    time.sleep(0.05)
            else:
                for ax, v in axes:
                    put(ax, int(round(v * FULL)))
                time.sleep(hold)
                for ax, _ in axes:
                    put(ax, 0)
            t1 = time.perf_counter()
            rec["segments"].append({"name": name, "start": t0, "end": t1})
            time.sleep(gap)
        # re-entry: release and press Y again; does the view come back level and forward?
        rec["segments"].append({"name": "reentry", "start": time.perf_counter(), "end": None})
        put(Y, 0)
        time.sleep(1.5)
        put(Y, 1)
        time.sleep(1.5)
        rec["segments"][-1]["end"] = time.perf_counter()
        for name, ax, v in (("after_reentry_h+0.50", LX, 0.5), ("after_reentry_v+0.50", LY, 0.5)):
            t0 = time.perf_counter()
            put(ax, int(round(v * FULL)))
            time.sleep(0.4 if ax == LX else 0.2)
            put(ax, 0)
            rec["segments"].append({"name": name, "start": t0, "end": time.perf_counter()})
            time.sleep(0.6)
        put(Y, 0)
        time.sleep(1.0)
        return []
    reasons = m19.hidden_run(a.run, ROOT / "config" / "m14" / "idle110.txt", a.seconds, test_level=a.level,
                             beside=beside, env={"R3HD_FRAME_TRACE": str(trace)})
    (OUT / f"{a.run}.curve.json").write_text(json.dumps(rec), encoding="utf-8")
    print("R3HD_LOOKMODE_CURVE", json.dumps({"run": a.run, "segments": len(rec["segments"]), "reasons": reasons}))
    return 1 if reasons else 0


def _angles(m):
    """(yaw of the most horizontal axis, elevation of the most vertical-moving axis) are chosen per segment."""
    f = struct.unpack_from(">15f", m, 4)
    return [f[0:3], f[4:7], f[8:11]], f[12:15]


def curve_frames(run):
    import m17_frame_trace as m17
    rec = json.loads((OUT / f"{run}.curve.json").read_text(encoding="utf-8"))
    w = rec["watch"]
    rows = []
    for swap, host, _, r in m17.frames(OUT / f"{run}.trace"):
        c, ry, fl = r.get(w["camera"]), r.get(w["rayman"]), r.get(w["flag"])
        if not c or len(c) != 0x40 or not ry or len(ry) != 0x40 or not fl:
            continue
        cols, pos = _angles(c)
        rows.append({"t": host, "cols": cols, "cam": pos, "ray": struct.unpack_from(">3f", ry, 0x34),
                     "flag": bool(struct.unpack(">I", fl)[0] & FLAG_BIT)})
    return rec, rows


def segment_metrics(rows, seg, tail=0.5):
    sel = [r for r in rows if seg["start"] - 0.05 <= r["t"] <= (seg["end"] or seg["start"]) + tail]
    if len(sel) < 3:
        return None
    k = max(range(3), key=lambda i: math.hypot(sel[0]["cols"][i][0], sel[0]["cols"][i][1]))
    yaw = [math.degrees(math.atan2(r["cols"][k][1], r["cols"][k][0])) for r in sel]
    dy = [(b - a + 180.0) % 360.0 - 180.0 for a, b in zip(yaw, yaw[1:])]

    def elev(c):
        return math.degrees(math.atan2(c[2], math.hypot(c[0], c[1])))
    kp = max(range(3), key=lambda i: abs(elev(sel[-1]["cols"][i]) - elev(sel[0]["cols"][i])))
    el = [elev(r["cols"][kp]) for r in sel]
    dp = [b - a for a, b in zip(el, el[1:])]
    dt = [b["t"] - a["t"] for a, b in zip(sel, sel[1:])]
    start, end = seg["start"], seg["end"] or seg["start"]

    def steady(d):  # deg/s over the second half of the hold
        vals = [x / t for x, t, r in zip(d, dt, sel[1:]) if start + (end - start) * 0.5 <= r["t"] <= end and t > 0]
        vals.sort()
        return round(vals[len(vals) // 2], 1) if vals else None

    def first(d):  # frames from the start to the first motion over 0.05 deg
        idx = [i for i, (x, r) in enumerate(zip(d, sel[1:])) if abs(x) > 0.05 and r["t"] >= start]
        return None if not idx else sum(1 for r in sel[1:idx[0] + 1] if r["t"] >= start)

    def stop(d):  # frames after the release that still move over 0.05 deg
        return sum(1 for x, r in zip(d, sel[1:]) if r["t"] > end and abs(x) > 0.05)
    return {"yaw_total": round(sum(dy), 2), "pitch_total": round(sum(dp), 2),
            "yaw_rate": steady(dy), "pitch_rate": steady(dp), "yaw_first_frame": first(dy),
            "pitch_first_frame": first(dp), "yaw_frames_after_release": stop(dy),
            "pitch_frames_after_release": stop(dp), "pitch_range": [round(min(el), 1), round(max(el), 1)],
            "flag_all_on": all(r["flag"] for r in sel if start <= r["t"] <= end),
            "ray_moved": round(math.dist(sel[0]["ray"], sel[-1]["ray"]), 3), "frames": len(sel)}


def cmd_curve_analyze(a) -> int:
    out = {}
    for run in a.runs:
        rec, rows = curve_frames(run)
        segs = {s["name"]: segment_metrics(rows, s, 0.6 if s["name"] != "reentry" else 0.0) for s in rec["segments"]}
        out[run] = {"frames": len(rows), "flag_on_frames": sum(r["flag"] for r in rows), "segments": segs}
    (OUT / f"curve_{a.out or '_'.join(a.runs)[:60]}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for run, d in out.items():
        print("==", run, "frames", d["frames"], "flag_on", d["flag_on_frames"])
        for n, m in d["segments"].items():
            print(f"{n:16s}", m and {k: m[k] for k in ("yaw_total", "yaw_rate", "pitch_total", "pitch_rate",
                                                       "yaw_first_frame", "yaw_frames_after_release",
                                                       "pitch_range", "flag_all_on", "ray_moved")})
    return 0


def cmd_curve_table(a) -> int:
    """Per segment and run: the median per-frame rotation while the input is held (yaw, or pitch for a `v` / `_v`
    segment), whether the flag stayed on, and how far Rayman moved. Prints and writes curve_table_<out>.json."""
    def elev(c):
        return math.degrees(math.atan2(c[2], math.hypot(c[0], c[1])))
    table = {}
    for run in a.runs:
        rec, rows = curve_frames(run)
        for s in rec["segments"]:
            if s["end"] is None:
                continue
            sel = [r for r in rows if s["start"] <= r["t"] <= s["end"] + 0.02]
            if len(sel) < 4:
                continue
            vertical = s["name"].startswith("v") or "_v" in s["name"]
            if vertical:
                kp = max(range(3), key=lambda i: abs(elev(sel[-1]["cols"][i]) - elev(sel[0]["cols"][i])))
                v = [elev(r["cols"][kp]) for r in sel]
                d = [b - x for x, b in zip(v, v[1:])]
            else:
                k = max(range(3), key=lambda i: math.hypot(sel[0]["cols"][i][0], sel[0]["cols"][i][1]))
                v = [math.degrees(math.atan2(r["cols"][k][1], r["cols"][k][0])) for r in sel]
                d = [(b - x + 180) % 360 - 180 for x, b in zip(v, v[1:])]
            mid = sorted(abs(x) for x in (d[1:-1] or d))
            table.setdefault(s["name"], {})[run] = {
                "deg_per_frame": round(mid[len(mid) // 2], 2), "flag_on": all(r["flag"] for r in sel),
                "ray_moved": round(math.dist(sel[0]["ray"], sel[-1]["ray"]), 3)}
    (OUT / f"curve_table_{a.out or '_'.join(a.runs)[:60]}.json").write_text(json.dumps(table, indent=1), encoding="utf-8")
    for n, v in table.items():
        print(f"{n:24s}", "  ".join(f"{r}:{x['deg_per_frame']}{'' if x['flag_on'] else '(no look)'}" for r, x in v.items()))
    return 0


FLAG, FLAG_BIT, CROSS, CROSS_VALUE = 0x82C07D5C, 0x01000000, 0x82C5C770, 0xFF000000  # E-326
ENTRY_S, EXIT_S = 0.8, 0.2  # the camera's travel after the flag rises / falls is not a disagreement


def word_values(rec, address):
    """The word's value at every sample (from the watch list when recorded, else from the diffs)."""
    i = (address - LO) // 4
    k = WATCH.index(address) if address in WATCH else None
    cur, out = rec.get("initial", {}).get(str(i)), []
    for s in rec["samples"]:
        if k is not None and "watch" in s:
            cur = s["watch"][k]
        elif str(i) in s["diff"]:
            cur = s["diff"][str(i)]
        out.append(cur)
    return out


def cmd_agree(a) -> int:
    """The candidate flag against the camera truth: false positives / negatives outside the camera's travel time, the
    cross-check word, Rayman moving while the flag is on, Y-press latency. R3HD_LOOKMODE_AGREE PASS|FAIL."""
    total = {"samples": 0, "flag_on": 0, "entries": 0, "false_on": 0, "false_off": 0, "cross_mismatch": 0,
             "moving_on": 0}
    lat_on, lat_off = [], []
    for r in a.runs:
        rec = json.loads((OUT / f"{r}.json").read_text(encoding="utf-8"))
        flag = [bool((v or 0) & FLAG_BIT) for v in word_values(rec, FLAG)]
        cross = [(v or 0) == CROSS_VALUE for v in word_values(rec, CROSS)]
        ts = [s["t"] for s in rec["samples"]]
        rises = [ts[k] for k in range(1, len(flag)) if flag[k] and not flag[k - 1]]
        falls = [ts[k] for k in range(1, len(flag)) if not flag[k] and flag[k - 1]]
        st = {"run": r, "samples": 0, "flag_on": 0, "entries": len(rises), "false_on": 0, "false_off": 0,
              "cross_mismatch": sum(f != c for f, c in zip(flag, cross)), "moving_on": 0}
        prev = None
        for s, f in zip(rec["samples"], flag):
            c = s["cam"]
            if not c:
                continue
            cam = math.dist(c["cam"], c["ray"]) < LOOK_DIST
            st["samples"] += 1
            st["flag_on"] += f
            st["false_on"] += f and not cam and not any(0 <= s["t"] - x <= ENTRY_S for x in rises)
            st["false_off"] += cam and not f and not any(0 <= s["t"] - x <= EXIT_S for x in falls)
            # speed between two samples that are both flag-on (the first on-sample carries the motion before it)
            if f and prev and prev[2] and s["t"] > prev[0] and math.dist(prev[1], c["ray"]) / (s["t"] - prev[0]) > 0.5:
                st["moving_on"] += 1
            prev = (s["t"], c["ray"], f)
        ys = [(e["t"], e["value"]) for e in rec["events"] if e["code"] == Y]
        for t, v in ys:
            edge = [x for x in (rises if v else falls) if 0 <= x - t < 1.0]
            if edge:
                (lat_on if v else lat_off).append(round(edge[0] - t, 2))
        print(json.dumps(st))
        for k in total:
            total[k] += st[k]
    ok = total["false_on"] == 0 and total["false_off"] == 0 and total["cross_mismatch"] == 0 and total["moving_on"] == 0
    print(json.dumps({"total": total, "y_to_flag_on_s": [min(lat_on, default=None), max(lat_on, default=None)],
                      "y_release_to_flag_off_s": [min(lat_off, default=None), max(lat_off, default=None)]}))
    print(f"R3HD_LOOKMODE_AGREE {'PASS' if ok else 'FAIL'} runs={len(a.runs)} samples={total['samples']} "
          f"entries={total['entries']}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("run")
    p.add_argument("level")
    p.add_argument("--seconds", type=int, default=110)
    p = sub.add_parser("load")
    p.add_argument("run")
    p.add_argument("--entry", default="intro_15_start")
    p.add_argument("--seconds", type=int, default=190)
    p = sub.add_parser("analyze")
    p.add_argument("runs", nargs="+")
    p.add_argument("--out", default="")
    p = sub.add_parser("curve")
    p.add_argument("run")
    p.add_argument("level")
    p.add_argument("--plan", choices=["standard", "repeat", "calibrated", "persist"], default="standard")
    p.add_argument("--seconds", type=int, default=150)
    p = sub.add_parser("curve-analyze")
    p.add_argument("runs", nargs="+")
    p.add_argument("--out", default="")
    p = sub.add_parser("curve-table")
    p.add_argument("runs", nargs="+")
    p.add_argument("--out", default="")
    p = sub.add_parser("agree")
    p.add_argument("runs", nargs="+")
    p = sub.add_parser("word")
    p.add_argument("--address", nargs="+", required=True)
    p.add_argument("runs", nargs="+")
    a = ap.parse_args()
    return {"run": cmd_run, "load": cmd_load, "analyze": cmd_analyze, "word": cmd_word, "agree": cmd_agree, "curve": cmd_curve,
            "curve-analyze": cmd_curve_analyze, "curve-table": cmd_curve_table}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
