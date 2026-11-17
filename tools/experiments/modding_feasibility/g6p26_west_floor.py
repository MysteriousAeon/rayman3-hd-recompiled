#!/usr/bin/env python3
"""E-515 (D-282) G6-P26: intro_20 west-floor witness feasibility (read-only, offline; no game run).

    g6p26_west_floor.py study    route geometry from Rayman's verified standing point (E-508 probe l1, triangle 1/11)
                                 to the start-floor-v2 west floor (triangles 1/2-1/4 around vertex 6) on collision mesh
                                 0x4B3F0: floor-triangle adjacency path, height profile along the straight segment,
                                 wall / steep crossings within the mesh, one candidate witness point with original and
                                 west-basin surface heights (product helper and independent G6-P16 surface model)
    g6p26_west_floor.py probe TAG  ONE read-only hidden baseline walk (protocol PROTOCOL below; production build, no plan)
    g6p26_west_floor.py judge TAG  P1-P5 of that run
    g6p26_west_floor.py check      offline: preview west-floor witness = independent model; spawn / runtime classes unchanged
Outputs: private/work/e515/ (numbers only). Uses the G6-P19 decoders and rm.collision_triangles; no new decoder.
"""
import json
import math
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import r3hd_mods as rm  # noqa: E402
import g6p22_intro20_terrain as g22  # noqa: E402
import g6p16_multi_surface as p16  # noqa: E402

g19, ROOT, LEVEL = g22.g19, g22.ROOT, g22.LEVEL
WORK = ROOT / "private" / "work" / "e515"
BASIN = HERE / "terrain_patches" / "intro20-west-basin.json"
TARGET, START = (1, 4), (1, 11)
W6 = 0.5   # candidate barycentric weight of vertex 6 (others 0.25 each): well inside, substantial vertex-6 influence


def seg_dist(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    if dx * dx + dy * dy < 1e-12:   # a vertical wall edge projects to a point
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def seg_cross(p, q, a, b):
    def o(u, v, w):
        return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])
    return o(p, q, a) * o(p, q, b) < 0 and o(a, b, p) * o(a, b, q) < 0


def study():
    WORK.mkdir(parents=True, exist_ok=True)
    lvl, ptr = g19.files()
    V, T = rm.collision_triangles(lvl, ptr, LEVEL)
    nz = {t: (rm._face(*(V[q] for q in idx)) or [0, 0, 0])[2] for t, idx in T.items()}
    floor = {t for t in T if nz[t] >= 0.9}
    edges = {}
    for t, idx in T.items():
        for k in range(3):
            edges.setdefault(frozenset((idx[k], idx[(k + 1) % 3])), []).append(t)
    adj = {t: set() for t in floor}
    for ts in edges.values():
        fl = [t for t in ts if t in floor]
        for a in fl:
            adj[a].update(b for b in fl if b != a)
    prev, dq = {START: None}, deque([START])
    while dq:
        t = dq.popleft()
        for n in sorted(adj[t]):
            if n not in prev:
                prev[n] = t
                dq.append(n)
    path, t = [], TARGET if TARGET in prev else None
    while t is not None:
        path.append(t)
        t = prev[t]
    path.reverse()
    cen = lambda t: [sum(V[q][i] for q in T[t]) / 3 for i in range(3)]   # noqa: E731
    # candidate: barycentric (vertex 6: W6, the other two corners (1 - W6) / 2) in triangle 1/4 = (2, 4, 6)
    idx = T[TARGET]
    w = [W6 if q == 6 else (1 - W6) / 2 for q in idx]
    cand = [sum(w[k] * V[idx[k]][i] for k in range(3)) for i in range(3)]
    margin = min(seg_dist(cand, V[idx[k]], V[idx[(k + 1) % 3]]) for k in range(3))
    walls = [t for t in T if nz[t] < 0.5]
    wall_d = min(min(seg_dist(cand, V[T[t][k]], V[T[t][(k + 1) % 3]]) for k in range(3)) for t in walls
                 if min(V[q][2] for q in T[t]) < cand[2] + 1.8 and max(V[q][2] for q in T[t]) > cand[2] + 0.05)
    # straight segment from the verified standing point to the candidate
    S = g19.SETTLED_L1
    prof, crossed, jumps = [], set(), 0.0
    for i in range(101):
        f = i / 100
        x, y = S[0] + f * (cand[0] - S[0]), S[1] + f * (cand[1] - S[1])
        su = rm.collision_surface(V, T, x, y)
        top = max(su, key=lambda s: s[1]) if su else None
        prof.append([round(x, 3), round(y, 3), round(top[1], 4) if top else None, list(top[0]) if top else None,
                     round(top[2], 4) if top else None])
    zs = [p[2] for p in prof if p[2] is not None]
    jumps = max(abs(a - b) for a, b in zip(zs, zs[1:])) if len(zs) > 1 else None
    for t in walls + [t for t in T if 0.5 <= nz[t] < 0.9]:
        lo, hi = min(V[q][2] for q in T[t]), max(V[q][2] for q in T[t])
        if lo < max(zs) + 1.8 and hi > min(zs) + 0.05:
            if any(seg_cross(S, cand, V[T[t][k]], V[T[t][(k + 1) % 3]]) for k in range(3)):
                crossed.add(t)
    # original and west-basin heights at the candidate: product helper and independent G6-P16 surface model
    canon, eds = rm.compile_terrain_patch(json.loads(BASIN.read_text(encoding="utf-8")), {"game": g22.GAME}, "basin") \
        if rm.structural_enabled(LEVEL) else (None, None)
    new = bytearray(lvl)
    for _, off, d, _ in eds or []:
        new[off:off + len(d)] = d
    V1, _ = rm.collision_triangles(bytes(new), ptr, LEVEL)
    h0, h1 = rm.collision_surface(V, T, cand[0], cand[1]), rm.collision_surface(V1, T, cand[0], cand[1])
    _, m0 = g19.mesh(lvl)
    _, m1 = g19.mesh(bytes(new))
    i0, i1 = p16.surface(m0, cand[0], cand[1]), p16.surface(m1, cand[0], cand[1])
    gap = S[2] - [z for t_, z, _ in rm.collision_surface(V, T, S[0], S[1])][0]
    expect = 0.0
    moved = {v: g["delta_z"] for g in canon["groups"] for v in g["vertices"]} if canon else {}
    for k, q in enumerate(idx):
        expect += w[k] * moved.get(q, 0.0)
    out = {
        "path_triangles": [{"tri": f"{a}/{b}", "idx": list(T[(a, b)]), "centroid": [round(c, 3) for c in cen((a, b))],
                            "normal_z": round(nz[(a, b)], 4)} for a, b in path],
        "region_triangles": {f"{a}/{b}": {"idx": list(T[(a, b)]), "centroid": [round(c, 3) for c in cen((a, b))],
                                          "normal_z": round(nz[(a, b)], 4)} for a, b in ((1, 2), (1, 3), (1, 4))},
        "candidate": {"triangle": "1/4", "barycentric": dict(zip(map(str, idx), w)), "xy": [round(c, 4) for c in cand[:2]],
                      "edge_margin": round(margin, 3), "nearest_wall_edge_xy": round(wall_d, 3),
                      "distance_from_l1": round(math.hypot(cand[0] - S[0], cand[1] - S[1]), 3),
                      "surface_original": [(list(t_), round(z, 4)) for t_, z, _ in h0],
                      "surface_west_basin": [(list(t_), round(z, 4)) for t_, z, _ in h1],
                      "independent_original": [(list(t_), round(z, 4)) for t_, z, _ in i0],
                      "independent_west_basin": [(list(t_), round(z, 4)) for t_, z, _ in i1],
                      "l1_gap_above_surface": round(gap, 4),
                      "expected_change_from_barycentric": round(expect, 4)},
        "segment": {"samples": len(prof), "z_min": min(zs), "z_max": max(zs), "max_step_between_samples": round(jumps, 4),
                    "triangles": sorted({tuple(p[3]) for p in prof if p[3]}), "min_normal_z": min(p[4] for p in prof if p[4]),
                    "steep_or_wall_crossed_in_mesh": sorted(crossed), "uncovered_samples": sum(p[2] is None for p in prof)},
    }
    (WORK / "study.json").write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, default=str))
    return 0


# ------------------------------------------------------------------------------------------------- baseline probe
PROTOCOL = """PROSPECTIVE PROTOCOL (committed before the run; criteria are not changed after results)

Run W (one only; no retry): production build (r3hd.exe e1c6df2b..., rexruntime.dll b47316a8...), NO mod plan, NO
R3HD_DEV_STRUCTURAL_TX, unmodified intro_20 files. m9_license_run.py --test-level intro_20, 230 s, hidden, disposable
profile (--user-root = run name), license mask 1, steps: wait only (as E-508 l1). After the level opens: one actor
discovery (m5_memory_probe.py); Rayman (YLT_RaymanModel) and StdCam read-only every 0.1 s.
Input (guest-scoped XAM schedule only, scancodes 300 / 301, appended to RUN/schedule.txt as m7_path_pilot.py does):
  1. wait until Rayman is in YAM_C_Attente within START_R of probe l1 (at most 30 s after discovery), else no input;
  2. walk: every 0.1 s the m7_path_pilot steer rule (stick forward = camera -> Rayman, horizontal) toward the
     candidate C = (-75.1189, -62.6726) in triangle 1/4 (original plane z -25.2104); deflection 1.0 while the horizontal distance d > 2.0, then
     max(0.35, d / 2); stop (stick released) when d <= 0.5 or after 30 s;
  3. safety abort (release, no further input): z outside [floor - 0.5, floor + 1.0] of the original surface under
     Rayman, or a behaviour that is not YAM_C_* ground / move;
  4. then no input to the end; samples continue every 0.2 s.
Criteria (judge W):
  P1 entry / safety: intro_20 opened, `M33 mods=off`, haptics policy line, M21 / M22 / M23 = 0, Rayman and StdCam
     discovered, only fix / transit / intro_20 opened.
  P2 movement: settled horizontal position within 1.0 of C, over collision triangle 1/4 (or 1/3 / 1/2: a vertex-6
     triangle) of mesh 0x4B3F0 by the original-file model, edge margin >= 0.3.
  P3 grounding: settled = the last 10 s (>= 40 samples) with behaviour YAM_C_Attente and position spread <= 0.01.
  P4 surface: |settled z - (original plane z under the settled x / y + 0.0007)| <= 0.02 (0.0007 = probe l1's
     height above its plane; 0.02 = the G6-P19 / G6-P22 / G6-P23 tolerance).
  P5 exit: runner exit 0, no process left, no input after step 4, fault lines as E-508 (reported).
Outcome: VERIFIED baseline west-floor witness only if P1-P5 PASS; a run that does not reach C is a failed /
inconclusive route witness, not repeated. It verifies the ORIGINAL surface only; no modified-terrain claim.
AMENDMENT 1 (after run w1, before run w2; harness defect, not a route result): w1 sent no input because Rayman
idled 0.073 from l1 from the first sample (E-512 recorded 0.058), outside the 0.05 start gate. START_R = 0.25 for
w2 (w1 used 0.05); all other steps and P1-P5 unchanged; w2 is the only rerun.
"""
RUN_SECONDS, PREFIX, START_R = 230, "e515", 0.25   # START_R: amendment 1 (w1: 0.05)
CX, CY = -75.1189, -62.6726


def probe(tag):
    import os
    import re
    import subprocess
    import time
    from m5_live import Actor, Process
    h, TOOLS, RUNS = g19.h, g19.TOOLS, g19.RUNS
    work = WORK / tag
    run = f"{PREFIX}_{tag}_walk"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k not in ("R3HD_MODS_PLAN", rm.STRUCT_ENV)}
    (work / "steps.txt").write_text(f"wait {RUN_SECONDS - 8}\n", encoding="ascii")
    lvl, ptr = g19.files()
    V, T = rm.collision_triangles(lvl, ptr, LEVEL)
    S = g19.SETTLED_L1
    row, samples, events = {"run": run}, [], []
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(RUN_SECONDS), "--play", "--test-level", LEVEL,
                                 "--user-root", run], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        needle = re.compile(rf"[\\/]{LEVEL}\.lvl result=00000000", re.IGNORECASE)
        opened, vbase, end = None, None, time.monotonic() + 90
        while time.monotonic() < end and game.poll() is None and opened is None:
            time.sleep(0.5)
            lp = RUNS / run / "runtime.log"
            if lp.is_file():
                text = lp.read_text(errors="replace")
                opened = time.monotonic() if needle.search(text) else None
                m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
                vbase = m.group(1) if m else vbase
        pid, sent = None, {300: 0, 301: 0}
        sched = RUNS / run / "schedule.txt"

        def send(x, y):
            lines = [f"0 {c} {v}\n" for c, v in ((300, x), (301, y)) if abs(sent[c] - v) >= 1500 or (v == 0 and sent[c])]
            for c, v in ((300, x), (301, y)):
                if abs(sent[c] - v) >= 1500 or (v == 0 and sent[c]):
                    sent[c] = v
            if lines:
                with sched.open("a", encoding="ascii", newline="") as f_:
                    f_.write("".join(lines))
                events.append({"t": round(time.monotonic() - opened, 2), "x": x, "y": y})

        def floor_z(x, y):
            su = rm.collision_surface(V, T, x, y)
            return (max(su, key=lambda s: s[1])[1], max(su, key=lambda s: s[1])[0]) if su else (None, None)
        if opened is None or vbase is None:
            row["error"] = "level did not open"
        else:
            pid = json.loads((RUNS / run / "process.json").read_text(encoding="utf-8-sig"))["pid"]
            process, ray, cam = Process(pid, int(vbase, 16)), None, None
            while (ray is None or cam is None) and time.monotonic() < opened + 80 and process.running():
                disc = work / "discovery.json"
                p = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), vbase, str(disc),
                                    "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
                for x in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if p.returncode == 0 else []):
                    try:
                        act = Actor(process, int(x["so"], 16))
                    except Exception:
                        continue
                    ray = act if act.model == "YLT_RaymanModel" and ray is None else ray
                    cam = act if act.model == "StdCam" and cam is None else cam
                row["discovery_t"] = round(time.monotonic() - opened, 2)
                if ray is None or cam is None:
                    time.sleep(10)
            t_end = opened + RUN_SECONDS - 45
            if ray is None or cam is None:
                row["error"] = "rayman or camera not found"
            else:
                phase, phase_t = "wait_idle", time.monotonic()
                row["walk"] = {}
                while time.monotonic() < t_end and process.running():
                    try:
                        pos, beh = ray.position(), ray.comport() or ""
                    except Exception as x:
                        row["sampling_stopped"] = type(x).__name__
                        break
                    now = time.monotonic()
                    samples.append({"t": round(now - opened, 2), "pos": pos, "beh": beh, "phase": phase})
                    if phase == "wait_idle":
                        if beh == "YAM_C_Attente" and math.hypot(pos[0] - S[0], pos[1] - S[1]) <= START_R:
                            phase, phase_t = "walk", now
                            row["walk"]["start_t"] = round(now - opened, 2)
                        elif now - phase_t > 30:
                            phase = "done"
                            row["walk"]["result"] = "never idle at l1: no input"
                    elif phase == "walk":
                        fz, _ = floor_z(pos[0], pos[1])
                        d = math.hypot(CX - pos[0], CY - pos[1])
                        if fz is None or not fz - 0.5 <= pos[2] <= fz + 1.0 or not beh.startswith("YAM_C_"):
                            send(0, 0)
                            phase = "done"
                            row["walk"].update(result="safety abort", beh=beh, pos=pos)
                        elif d <= 0.5 or now - phase_t > 30:
                            send(0, 0)
                            phase = "done"
                            row["walk"].update(result="reached" if d <= 0.5 else "timeout", d=round(d, 3),
                                               t=round(now - opened, 2))
                        else:
                            c = cam.position()
                            fx, fy = pos[0] - c[0], pos[1] - c[1]
                            ln = math.hypot(fx, fy)
                            if ln > 1e-4:
                                fx, fy, dx, dy = fx / ln, fy / ln, (CX - pos[0]) / d, (CY - pos[1]) / d
                                sc = 1.0 if d > 2.0 else max(0.35, d / 2.0)
                                send(int(round((dx * fy - dy * fx) * 32767 * sc)), int(round((dx * fx + dy * fy) * 32767 * sc)))
                    time.sleep(0.1 if phase == "walk" else 0.2)
                if phase == "walk":
                    send(0, 0)
                    row["walk"]["result"] = "run ended while walking"
        game.wait(timeout=RUN_SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and h.alive(pid))
    (work / "samples.json").write_text(json.dumps(samples) + "\n")
    (work / "input_events.json").write_text(json.dumps(events) + "\n")
    log = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / run).glob("runtime*.log")))
    row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
    row["mods_off"] = "M33 mods=off" in log
    row["levels_opened"] = re.findall(r"[\\/]([A-Za-z0-9_]+)\.lvl result=00000000", log)
    row["fault_lines"] = len(h.FAULT.findall(log))
    row["judges"] = {}
    for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        r = subprocess.run([sys.executable, str(TOOLS / t), "--run", run], cwd=ROOT, capture_output=True, text=True)
        row["judges"][t] = r.returncode
        (work / f"{t}.log").write_text(r.stdout + r.stderr)
    (work / "row.json").write_text(json.dumps(row, indent=1) + "\n")
    print(json.dumps(row, indent=1))
    return 0


def judge(tag):
    work = WORK / tag
    row = json.loads((work / "row.json").read_text())
    smp = json.loads((work / "samples.json").read_text())
    ev = json.loads((work / "input_events.json").read_text())
    lvl, ptr = g19.files()
    V, T = rm.collision_triangles(lvl, ptr, LEVEL)
    out, det = {}, {"walk": row.get("walk"), "events": len(ev)}
    out["P1 entry / safety"] = (row.get("levels_opened") == ["fix", "transit", LEVEL] and row.get("mods_off")
                               and row.get("haptics_policy") and all(v == 0 for v in row.get("judges", {}).values())
                               and "error" not in row)
    last_t = smp[-1]["t"] if smp else 0
    tail = [s for s in smp if s["t"] >= last_t - 10]
    xs = [s["pos"] for s in tail]
    spread = max(max(p[i] for p in xs) - min(p[i] for p in xs) for i in range(3)) if xs else None
    st = xs[-1] if xs else None
    su = rm.collision_surface(V, T, st[0], st[1]) if st else []
    top = max(su, key=lambda s: s[1]) if su else None
    tri = top[0] if top else None
    margin = (min(seg_dist(st, V[T[tri][k]], V[T[tri][(k + 1) % 3]]) for k in range(3)) if tri else None)
    det.update(settled=st, spread=spread, tail_n=len(tail), tail_behaviours=sorted({s["beh"] for s in tail}),
               triangle=list(tri) if tri else None, edge_margin=round(margin, 3) if margin else None,
               plane_z=round(top[1], 4) if top else None,
               d_to_c=round(math.hypot(st[0] - CX, st[1] - CY), 3) if st else None)
    out["P2 movement"] = bool(st and det["d_to_c"] <= 1.0 and tri in ((1, 2), (1, 3), (1, 4)) and margin >= 0.3)
    out["P3 grounding"] = bool(len(tail) >= 40 and det["tail_behaviours"] == ["YAM_C_Attente"] and spread <= 0.01)
    det["p4_diff"] = round(st[2] - (top[1] + 0.0007), 4) if top else None
    out["P4 surface"] = bool(top and abs(det["p4_diff"]) <= 0.02)
    late = [e for e in ev if e["t"] > (row.get("walk", {}).get("t") or 1e9) + 0.5]
    out["P5 exit"] = row.get("runner_exit") == 0 and not row.get("process_left") and not late
    det["fault_lines"] = row.get("fault_lines")
    res = {"pass": all(out.values()), "criteria": out, "details": det}
    (work / "judge.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1, default=str))
    return 0


def check():
    """Offline: the preview's west-floor witness = the independent G6-P16 model at the measured point; spawn
    predictions and runtime classes of the examples unchanged; the witness model refuses a point it does not hold."""
    import g6p24_authoring_ux as g24
    ex = g22.EX
    out, det = {}, {}
    wit = rm.LEVEL_PATCH_WITNESSES[LEVEL][0]
    j = json.loads((WORK / "w2" / "judge.json").read_text())
    out["w2 judge P1-P5 PASS and the witness constant = its settled point"] = (
        j["pass"] and [round(c, 6) for c in wit["xyz"]] == [round(c, 6) for c in j["details"]["settled"]])
    lvl, ptr = g19.files()
    _, m0 = g19.mesh(lvl)
    want = {"g6p25_west_basin_fairy.json": (-25.0779, "OBSERVED"),   # G6-P27 run m1 (UNTESTED until E-516) "g6p22_west_dip_fairy.json": (-25.1408, "OBSERVED"),
            "g6p20_reference.json": (-25.2668, "OBSERVED"), "graph_b.json": (-25.2668, "UNTESTED")}
    for n, (zs, cls) in want.items():
        rc, r, _ = g24.cli(["level-patch", str(ex / n), "--check"], extra=("--json",))
        pv = r["preview"]
        w_ = pv["witnesses"][0]
        with g24.p1.dev_env(LEVEL):
            canon, ranges, tx = rm.compile_level_patch(json.loads((ex / n).read_text(encoding="utf-8")), {"game": g22.GAME})
        _, m1 = g19.mesh(tx["images"]["lvl"][:len(lvl)])
        x, y, z = wit["xyz"]
        s0, s1 = p16.surface(m0, x, y), p16.surface(m1, x, y)
        ind = round(s1[0][1] + (z - s0[0][1]), 4) if len(s0) == len(s1) == 1 else None
        det[n] = {"west_floor": w_.get("predicted_settled_z"), "independent": ind, "spawn": pv["standing"]["predicted_settled_z"]}
        out[f"{n}: west-floor {w_.get('predicted_settled_z')} = independent {ind}; spawn {zs} unchanged; runtime {cls}"] = (
            rc == 0 and w_["available"] and w_["predicted_settled_z"] == ind
            and pv["standing"]["predicted_settled_z"] == zs and pv["evidence"]["runtime"].startswith(cls))
    off = dict(wit, xyz=(wit["xyz"][0] + 1e5, wit["xyz"][1], wit["xyz"][2]))
    r_ = rm.standing_prediction(LEVEL, lvl, ptr, [], off)
    out["witness off the mesh: unavailable with a reason, no number"] = (
        r_["available"] is False and r_.get("reason") and "predicted_settled_z" not in r_)
    res = {"pass": all(out.values()), "checks": out, "details": det}
    (WORK / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=1, default=str))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    cmd = sys.argv[1:]
    if cmd == ["study"]:
        sys.exit(study())
    if cmd == ["check"]:
        sys.exit(check())
    if len(cmd) == 2 and cmd[0] in ("probe", "judge"):
        sys.exit({"probe": probe, "judge": judge}[cmd[0]](cmd[1]))
    raise SystemExit(__doc__ + "\n" + PROTOCOL)
