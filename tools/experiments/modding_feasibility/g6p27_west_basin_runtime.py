#!/usr/bin/env python3
"""E-516 (D-283) G6-P27: runtime acceptance of the G6-P25 `west-basin` level patch (start-floor-v2: vertex 6 -0.20,
2 / 4 -0.15; FairyLight on graph A) at the G6-P26 west-floor witness. Development-only; private; hidden.

    g6p27_west_basin_runtime.py preflight   Phase A: CLI compile -> mod.json -> import / plan; identities, hashes,
                                            members, range count, graph A, growth, independent combined checker,
                                            actual-position surface model sanity at W
    g6p27_west_basin_runtime.py negtest     G6-P20's negtest (real overlay code, dev + production) on this plan
    g6p27_west_basin_runtime.py run TAG     the single hidden run M (development build) with the G6-P26 walk
    g6p27_west_basin_runtime.py judge TAG   P1-P6
Outputs: private/work/e516/ (numbers only).

Reuse: the G6-P20 runner / judge through the G6-P23 re-pointing (work folder, mod id, terrain edits, run ranges) plus
two default-preserving hooks added for this run: run_case(tick=...) and the P1 range count N_RANGES. The walk is
G6-P26 run w2's (amendment 1 start gate 0.25), re-implemented as a tick on the same samples. P2 uses G6-P23's exact
read-back rule (own-file pointer slots of the plan's rebuilt table compared as file value + area base). P3 is new: the
actual-position surface criterion below.

INPUT
  declaration level_patch_examples/g6p25_west_basin_fairy.json (mod id g6p25.west-basin-fairy); terrain west-basin
  (start-floor-v2: 6 -0.20, 2 / 4 -0.15; 0 unchanged); fairylight follow_graph_of 0 (graph A 0x3226A8).
  Sources: intro_20.lvl 6,135,684 a21aa769..., intro_20.ptr 273,540 be90b58a..., transit.lvl 26,140 51c0fbf1....
  Expected transaction: level-tx 2 intro_20 g6p25.west-basin-fairy 9083786df631a5a3; 55 ranges (13 fairy + 42
  terrain); growth +2,892 / +408 / 0; results lvl 086042dfecb2b203..., ptr 40934d08... and transit 2be9a434... (= G6-P20's).
  Preflight 12 / 12 PASS; negtest of this plan development 9 / 9, production 2 / 2 PASS (before the build).

RUNTIME PROTOCOL (committed before the run; thresholds are not changed after results)
Build: no development runtime is retained (G6-P23 restored production in place), so the verified cycle is used:
g5p1_dev_gate.py apply (existing rows; no native source change) + tools\\build_incremental.bat (INCREMENTAL_BUILD_OK);
the development hashes are recorded before the run. Before the run: preflight PASS, negtest of this plan (development
+ production) PASS. Afterwards: g5p1_dev_gate.py revert, the same incremental build, `status` production, no
R3HD_DEV_STRUCTURAL_TX string in r3hd.exe / rexruntime.dll, new production hashes recorded, M33 / M36 / M38.
One run M `e516_<tag>_M` (no repeat except an INVALID run or a demonstrated harness defect, after a committed
amendment): G6-P20's run_case (m9_license_run.py hidden, non-activating, muted, no physical pad, private user root,
--test-level intro_20, 150 s; plan = this mod, marker armed; the game gets R3HD_DEV_STRUCTURAL_TX=intro_20; G6-P3's
Exit Game sequence 85 s after intro_20.lvl opens; reads at area + 6 s and + 80 s; positions every 0.1 s).
WALK (tick, guest-scoped XAM 300 / 301 appended to RUN/schedule.txt; StdCam from the run's own discovery):
  1. wait until Rayman is YAM_C_Attente within 0.25 of probe l1, at most 30 s after the first read, else no input;
  2. every 0.1 s the m7_path_pilot steer rule (stick forward = camera -> Rayman) toward W = (-75.4334, -62.8105);
     deflection 1.0 while d > 2.0, then max(0.35, d / 2); release at d <= 0.5 or after 30 s;
  3. safety abort (release, no further input): z outside [floor - 0.5, floor + 1.0] of the MODIFIED surface under
     Rayman, or a behaviour not starting YAM_C_;
  4. no further walk input; the Exit Game sequence follows at 85 s.
Reference value (recorded, not the primary criterion): modified plane at W = -25.3889 (G6-P26).
  P1 atomic activation: G6-P20's P1 with this plan (one active state; level-tx id; version 2; members lvl / ptr /
     transit; snapshots 6,138,576 / 273,948 / 26,140; growth; served exactly the 3 files and all 55 planned ranges;
     no host_changed).
  P2 guest readback: P2a the 42 west-basin terrain ranges hold the plan image at both reads; P2b the 10 fairy-edited
     words hold the plan image at both reads (own-file pointer slots as file value + area base). Unread = not observed.
  P3 west-floor physics (actual position): walk result `reached` (d <= 0.5) with no abort; settled window = the 10 s
     starting 10 s after the release (all before the exit input): >= 40 samples, all YAM_C_Attente, spread <= 0.01;
     at the last window position (x, y): exactly one upward collision triangle under it in the plan's final lvl image,
     one of the vertex-6 triangles 1/2, 1/3, 1/4, edge margin >= 0.3 (G6-P26 criterion), vertex-6 barycentric weight
     >= 0.2; the product helper and the independent G6-P16 surface model agree within 1e-4; predicted modified -
     original plane at (x, y) <= -0.05 (material effect); |z - modified plane| <= 0.02; no walk / settle sample below
     the modified surface - 0.10. Outside the triangle coverage -> P3 INCONCLUSIVE (never PASS).
  P4 FairyLight: G6-P20's P4 unchanged (registration, both variable-2 words = X(0x3226A8), 5-node walk, >= 3 arrivals
     per graph-A waypoint, cycle with <= 1 irregular step, 0 graph-B arrivals, source and movers >= 3 arrivals).
  P5 exit and cleanup: G6-P20's P5 unchanged (menumap route, +2,892 loaded, fix-only between levels, menumap = A,
     lists consistent, marker armed then cleared).
  P6 safety: G6-P20's P6 (M21 / M22 / M23 0, haptics, runner exit 0, no process left, fault codes within {406D1388},
     only fix / transit / intro_20 / menumap) + this plan's negtest; production restored afterwards.
  Classes: P1-P6 PASS -> G6-P27 VERIFIED — AUTHORED WEST-FLOOR PHYSICS; P1 + P2 PASS and P3 INCONCLUSIVE or the walk
     not reached -> PARTIAL — MODIFIED TERRAIN LOADED, PHYSICS UNVERIFIED; P3 FAIL on a covered vertex-6 interior ->
     FAILED — WEST-FLOOR PHYSICS MISMATCH; P1 FAIL -> BLOCKED — TRANSACTION; P2 / P4 / P5 / P6 FAIL -> FAILED — named.
"""
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import r3hd_mods as rm  # noqa: E402
import g6p20_fairy_terrain as g20  # noqa: E402
import g6p21_level_patch as g21  # noqa: E402
import g6p22_intro20_terrain as g22  # noqa: E402
import g6p16_multi_surface as p16  # noqa: E402

g3, p1, g19 = g20.g3, g20.p1, g20.g19
ROOT, TOOLS, GAME, LEVEL = g20.ROOT, g20.TOOLS, g20.GAME, g20.LEVEL
PREFIX = "e516"
WORK = ROOT / "private" / "work" / PREFIX
DECL = HERE / "level_patch_examples" / "g6p25_west_basin_fairy.json"
LD = json.loads(DECL.read_text(encoding="utf-8"))
MID = LD["id"]
WANT_TX, N_RANGES, W_POINT, W_PRED = "9083786df631a5a3", 55, (-75.4334, -62.8105), -25.3889
START_R, V6_TRIS = 0.25, ((1, 2), (1, 3), (1, 4))
OVERRIDE = {"type": "level-patch", "patch": LD}


def terrain_canon():
    with p1.dev_env(LEVEL):
        c = rm.parse_level_patch(LD, "decl")
    return next(x for x in c["components"] if x["type"] == "terrain")["patch"]


def terrain_edits():
    lvl, ptr = g19.files()
    return rm.collision_edit(lvl, ptr, LEVEL, rm.terrain_spec(terrain_canon()), "west-basin")


def run_ranges():
    with p1.dev_env(LEVEL):
        _, rs, _ = rm.compile_level_patch(LD, {"game": GAME})
    return rs, terrain_canon()["name"]


def configure():
    WORK.mkdir(parents=True, exist_ok=True)
    g20.WORK, g20.PREFIX, g20.MID, g20.SEL, g20.N_RANGES = WORK, PREFIX, MID, "a", N_RANGES
    g20.terrain_edits, g20.run_ranges = terrain_edits, run_ranges
    g20.op = lambda **kw: dict(OVERRIDE)
    g3.WORK = WORK
    p1.WORK = WORK


def jdump(name, obj):
    (WORK / name).write_text(json.dumps(obj, indent=1, default=str) + "\n", encoding="utf-8")


def surfaces(img_lvl, x, y):
    """(product [(tri, z, nz)], independent [(tri, z, nz)]) of the first SIZE bytes of a level image at (x, y)."""
    lvl, ptr = g19.files()
    base = img_lvl[:len(lvl)]
    V, T = rm.collision_triangles(base, ptr, LEVEL)
    _, m = g19.mesh(base)
    return rm.collision_surface(V, T, x, y), p16.surface(m, x, y), (V, T)


# ------------------------------------------------------------------------------------------------- preflight
def preflight():
    configure()
    out, det = {}, {}
    raw = DECL.read_bytes()
    tc = terrain_canon()
    with p1.dev_env(LEVEL):
        canon = rm.parse_level_patch(LD, "decl")
        op = rm.level_patch_operation(canon)
    det["declaration"] = {"file_sha256": rm.sha256_bytes(raw), "identity": rm.level_patch_identity(canon),
                          "terrain_identity": rm.terrain_identity(tc), "id": MID}
    out["declaration: west-basin (start-floor-v2: 6 -0.20, 2 / 4 -0.15, 0 unchanged) + fairylight graph A"] = (
        tc["region"] == "start-floor-v2" and tc["name"] == "west-basin"
        and {v: g["delta_z"] for g in tc["groups"] for v in g["vertices"]} == {6: -0.20, 2: -0.15, 4: -0.15}
        and op["follow_graph_of"] == 0 and "terrain_preset" not in op)
    out["source hashes = the verified intro_20 originals"] = (
        LD["lvl_sha256"] == rm.STRUCT_ALLOW[LEVEL]["lvl"][1] and LD["ptr_sha256"] == rm.STRUCT_ALLOW[LEVEL]["ptr"][1]
        and LD["transit_sha256"] == rm.FAIRY_ALLOW[LEVEL]["transit"][1])
    cdir = WORK / "preflight"
    if cdir.exists():
        shutil.rmtree(cdir)
    cdir.mkdir(parents=True)
    rc, cli = g21.cli(["level-patch", str(DECL)], LEVEL, cdir / "mod")
    det["cli"] = {k: cli.get(k) for k in ("transaction", "growth", "range_count", "terrain_ranges", "fairylight_ranges")}
    det["cli_preview_west_floor"] = (cli.get("preview", {}).get("witnesses") or [{}])[0].get("predicted_settled_z")
    out["CLI level-patch: exit 0, mod.json, tx 9083786df631a5a3, 55 ranges (13 + 42), growth +2892 / +408 / 0"] = (
        rc == 0 and (cdir / "mod" / "mod.json").is_file() and cli.get("transaction", {}).get("id") == WANT_TX
        and cli.get("range_count") == 55 and cli.get("terrain_ranges") == 42 and cli.get("fairylight_ranges") == 13
        and cli.get("growth") == {"lvl": 2892, "ptr": 408, "transit": 0})
    mj = json.loads((cdir / "mod" / "mod.json").read_text(encoding="utf-8")) if rc == 0 else None
    res, text, _ = g3.compile_plan("preflight_cli_mod", [(mj["id"], mj["overrides"])]) if mj else ({}, None, None)
    m = p1.parse_plan(text) if text else None
    out["import + plan: active, one level-tx 2 intro_20 g6p25.west-basin-fairy 9083786df631a5a3"] = (
        m is not None and res.get("active") == [MID] and m["txs"] == [f"level-tx 2 {LEVEL} {MID} {WANT_TX}"])
    if m:
        tx = {f["tx"][0].split(" ")[0]: f["tx"][0].split(" ") for f in m["files"]}
        det["results"] = {k: v[3] for k, v in tx.items()}
        out["members exactly lvl / ptr / transit; originals = the allow-list; ptr / transit results = G6-P20's"] = (
            sorted(tx) == ["lvl", "ptr", "transit"] and tx["lvl"][1] == rm.STRUCT_ALLOW[LEVEL]["lvl"][1]
            and tx["ptr"][1] == rm.STRUCT_ALLOW[LEVEL]["ptr"][1]
            and tx["transit"][1] == rm.FAIRY_ALLOW[LEVEL]["transit"][1]
            and tx["ptr"][3] == g21.REF_RESULTS["ptr"] and tx["transit"][3] == g21.REF_RESULTS["transit"])
        _, text_d, _ = g3.compile_plan("preflight_direct", [(MID, [OVERRIDE])])
        out["CLI mod plan = direct declaration plan"] = g21.body(text) == g21.body(text_d)
        fc = g22.combined_check(text, "a", MID, {k: v for k, v in tc.items() if k != "description"})
        det["combined_check"] = {k: v for k, v in fc.items() if not isinstance(v, dict)}
        out["independent combined checker (final_check + declaration-derived geometry) ok"] = bool(fc.get("ok"))
        img = p1.images(m)[f"{LEVEL}.lvl"]
        lvl, _ = g19.files()
        a, b, _ = surfaces(img, *W_POINT)
        o_, _, _ = surfaces(lvl, *W_POINT)
        det["W"] = {"modified_product": a, "modified_independent": b, "original": o_}
        out["actual-position model at W: one vertex-6 triangle (1/4), product = independent, modified -25.3889"] = (
            len(a) == len(b) == 1 and a[0][0] == b[0][0] == (1, 4) and abs(a[0][1] - b[0][1]) <= 1e-4
            and round(a[0][1], 4) == W_PRED and a[0][1] - o_[0][1] <= -0.05)
    rs, tname = run_ranges()
    fw = [o for p_, o, d, w in rs if p_.name.lower() == f"{LEVEL}.lvl" and len(d) == 4 and o < g20.SIZE
          and f".terrain.{tname} " not in w]
    out["run reads: 42 terrain ranges + 10 fairy words"] = len(terrain_edits()) == 42 and len(fw) == 10
    with p1.dev_env(LEVEL):
        x1, x2 = rm.compile_level_patch(LD, {"game": GAME}), rm.compile_level_patch(LD, {"game": GAME})
    out["deterministic (two compiles equal)"] = x1[1] == x2[1] and x1[2]["images"] == x2[2]["images"]
    out["growth within the development gate's intro_20 v2 rows (lvl <= 4096, ptr <= 1024)"] = 2892 <= 4096 and 408 <= 1024
    w2 = json.loads((ROOT / "private/work/e515/w2/judge.json").read_text())
    out["G6-P26 w2 route witness PASS (original W = -25.2122)"] = w2["pass"] and round(w2["details"]["settled"][2], 4) == -25.2122
    gate = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    det["gate_status"] = gate.stdout.strip()
    r_ = {"pass": all(out.values()), "checks": out, "details": det}
    jdump("preflight.json", r_)
    print(json.dumps({"pass": r_["pass"], "checks": out, "results": det.get("results")}, indent=1))
    return 0 if r_["pass"] else 1


def negtest():
    configure()
    return g20.negtest()


# ------------------------------------------------------------------------------------------------- run
def make_walker():
    from m5_live import Actor
    img = None
    st = {"phase": "init", "events": [], "next": 0.0}
    S = g19.SETTLED_L1

    def tick(p, actors, work, run, t0):
        nonlocal img
        now = time.monotonic()
        if now < st["next"] or st["phase"] == "done" or "rayman" not in actors:
            return
        st["next"] = now + 0.1
        t = round(now - t0, 3)
        if st["phase"] == "init":
            m = p1.parse_plan((work / "plan_copy.txt").read_text(encoding="utf-8"))
            img = p1.images(m)[f"{LEVEL}.lvl"]
            st["V"] = surfaces(img, *W_POINT)[2]
            cam = None
            for x in json.loads((work / "discovery.json").read_text(encoding="utf-8")).get("actors", []):
                try:
                    a_ = Actor(p, int(x["so"], 16))
                except Exception:
                    continue
                if a_.model == "StdCam":
                    cam = a_
                    break
            st.update(cam=cam, sched=g19.RUNS / run / "schedule.txt", sent={300: 0, 301: 0}, wait_t=now,
                      phase="wait_idle" if cam else "done", result=None if cam else "no StdCam: no input")
            save(work, st, t)
            return
        ray = actors["rayman"]
        try:
            pos, beh = ray.position(), ray.comport() or ""
        except Exception as x:
            st.update(phase="done", result=f"rayman unreadable {type(x).__name__}")
            send(st, 0, 0, t)
            save(work, st, t)
            return
        if st["phase"] == "wait_idle":
            if beh == "YAM_C_Attente" and math.hypot(pos[0] - S[0], pos[1] - S[1]) <= START_R:
                st.update(phase="walk", walk_t=now, start_t=t, start_pos=list(pos))
            elif now - st["wait_t"] > 30:
                st.update(phase="done", result="never idle at l1: no input")
            save(work, st, t)
            return
        V, T = st["V"]
        su = rm.collision_surface(V, T, pos[0], pos[1])
        fz = max(z for _, z, _ in su) if su else None
        d = math.hypot(W_POINT[0] - pos[0], W_POINT[1] - pos[1])
        if fz is None or not fz - 0.5 <= pos[2] <= fz + 1.0 or not beh.startswith("YAM_C_"):
            send(st, 0, 0, t)
            st.update(phase="done", result="safety abort", abort_pos=list(pos), abort_beh=beh, stop_t=t)
        elif d <= 0.5 or now - st["walk_t"] > 30:
            send(st, 0, 0, t)
            st.update(phase="done", result="reached" if d <= 0.5 else "timeout", d=round(d, 3), stop_t=t)
        else:
            c = st["cam"].position()
            fx, fy = pos[0] - c[0], pos[1] - c[1]
            ln = math.hypot(fx, fy)
            if ln > 1e-4:
                fx, fy, dx, dy = fx / ln, fy / ln, (W_POINT[0] - pos[0]) / d, (W_POINT[1] - pos[1]) / d
                sc = 1.0 if d > 2.0 else max(0.35, d / 2.0)
                send(st, int(round((dx * fy - dy * fx) * 32767 * sc)), int(round((dx * fx + dy * fy) * 32767 * sc)), t)
        if st["phase"] == "done":
            save(work, st, t)
    return tick


def send(st, x, y, t):
    if "sched" not in st:
        return
    lines = []
    for c, v in ((300, x), (301, y)):
        if abs(st["sent"][c] - v) >= 1500 or (v == 0 and st["sent"][c]):
            lines.append(f"0 {c} {v}\n")
            st["sent"][c] = v
    if lines:
        with st["sched"].open("a", encoding="ascii", newline="") as f_:
            f_.write("".join(lines))
        st["events"].append({"t": t, "x": x, "y": y})


def save(work, st, t):
    keep = {k: v for k, v in st.items() if k in ("phase", "result", "events", "start_t", "start_pos", "stop_t", "d",
                                                  "abort_pos", "abort_beh")}
    (work / "walk.json").write_text(json.dumps({**keep, "saved_t": t}, indent=1) + "\n")


def run(tag):
    configure()
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    for f in ("preflight.json", "negtest/summary.json"):
        if not json.loads((WORK / f).read_text()).get("pass"):
            raise SystemExit(f"{f} did not pass")
    run_ = f"{PREFIX}_{tag}_M"
    res, text, paths = g20.plan_of(f"run_{tag}", [(MID, [dict(OVERRIDE)])], session=run_)
    if res["active"] != [MID] or text is None or p1.parse_plan(text)["txs"] != [f"level-tx 2 {LEVEL} {MID} {WANT_TX}"]:
        raise SystemExit(f"compiler refused or changed the run's mod: {res.get('mods')}")
    row = g20.run_case(tag, "M", paths["cache"] / rm.PLAN_NAME, paths, tick=make_walker())
    print(json.dumps(row, default=str)[:800])
    return 0


# ------------------------------------------------------------------------------------------------- judge
def judge(tag):
    configure()
    g20.judge(tag)
    j = json.loads((WORK / f"judgement_{tag}.json").read_text())
    if j.get("invalid"):
        print(json.dumps({"invalid": j["invalid"], "verdict": "INVALID"}))
        return 1
    w = WORK / tag / "M"
    r = json.loads((w / "row.json").read_text())
    live = json.loads((w / "live.json").read_text())
    samples = json.loads((w / "samples.json").read_text())
    walk = json.loads((w / "walk.json").read_text()) if (w / "walk.json").is_file() else {}
    m = p1.parse_plan((w / "plan_copy.txt").read_text(encoding="utf-8"))
    img = p1.images(m)[f"{LEVEL}.lvl"]
    # P2 (G6-P23's rule)
    ter = {o for o, _, _ in terrain_edits()}
    want = {o: img[o:o + n].hex() for o, n in r["reads_at"]}
    got = {k: dict(tuple(x) for x in live.get(k, {}).get("ranges", [])) for k in ("first", "end")}
    t_offs = [o for o, _ in r["reads_at"] if o in ter]
    f_offs = [o for o, _ in r["reads_at"] if o not in ter]
    raw_want = dict(want)
    pimg = p1.images(m)[f"{LEVEL}.ptr"]
    n_ = struct.unpack_from(">I", pimg, 0)[0]
    own = {struct.unpack_from(">iI", pimg, 4 + 8 * i)[1] + 4 for i in range(n_)
           if struct.unpack_from(">iI", pimg, 4 + 8 * i)[0] == 1}
    ab = live["first"]["ab"]
    for o in f_offs:
        if o in own:
            want[o] = f"{(int(raw_want[o], 16) + ab) & 0xFFFFFFFF:08x}"
    p2a = len(t_offs) == 42 and all(got[k].get(o) == want[o] for k in got for o in t_offs) and not any(o in own for o in t_offs)
    observed_f = len(f_offs) == 10 and all(o in got[k] and got[k][o] for k in got for o in f_offs)
    p2b = observed_f and all(got[k][o] == want[o] for k in got for o in f_offs)
    # P3 actual-position physics
    lvl, _ = g19.files()
    stop = walk.get("stop_t")
    exit_t = live["first"]["t"] + 79
    win = [s for s in samples if "rayman" in s["p"] and stop is not None and stop + 10 <= s["t"] < stop + 20]
    xs = [s["p"]["rayman"] for s in win]
    p3 = {"walk": {k: walk.get(k) for k in ("result", "start_t", "stop_t", "d", "abort_pos", "abort_beh")},
          "events": len(walk.get("events", [])), "window_n": len(win), "W_reference_modified": W_PRED}
    inconclusive, ok3 = False, False
    if walk.get("result") == "reached" and len(win) >= 40 and win[-1]["t"] < exit_t:
        spread = max(max(p[i] for p in xs) - min(p[i] for p in xs) for i in range(3))
        behs = sorted({s.get("beh") for s in win})
        x, y, z = xs[-1]
        a, b, (V, T) = surfaces(img, x, y)
        o_, _, _ = surfaces(lvl, x, y)
        p3.update(settled=[x, y, z], spread=spread, behaviours=behs, product=a, independent=b, original=o_)
        if len(a) == 1 and len(b) == 1 and len(o_) == 1 and a[0][0] in V6_TRIS and a[0][0] == b[0][0] == o_[0][0]:
            tri = a[0][0]
            idx = T[tri]
            pa, pb, pc = (V[q] for q in idx)
            den = (pb[1] - pc[1]) * (pa[0] - pc[0]) + (pc[0] - pb[0]) * (pa[1] - pc[1])
            l1 = ((pb[1] - pc[1]) * (x - pc[0]) + (pc[0] - pb[0]) * (y - pc[1])) / den
            l2 = ((pc[1] - pa[1]) * (x - pc[0]) + (pa[0] - pc[0]) * (y - pc[1])) / den
            bary = dict(zip(idx, (l1, l2, 1 - l1 - l2)))
            import g6p26_west_floor as w26
            margin = min(w26.seg_dist((x, y), V[idx[k]], V[idx[(k + 1) % 3]]) for k in range(3))
            effect = a[0][1] - o_[0][1]
            track = [s for s in samples if "rayman" in s["p"] and (walk.get("start_t") or 1e9) <= s["t"] < exit_t]
            below = []
            for s in track:
                su = rm.collision_surface(V, T, s["p"]["rayman"][0], s["p"]["rayman"][1])
                if su and s["p"]["rayman"][2] < max(q for _, q, _ in su) - 0.10:
                    below.append(s["t"])
            p3.update(triangle=list(tri), barycentric={str(k): round(v, 4) for k, v in bary.items()},
                      v6_weight=round(bary[6], 4), edge_margin=round(margin, 4), plane_modified=round(a[0][1], 4),
                      plane_original=round(o_[0][1], 4), effect=round(effect, 4), residual=round(z - a[0][1], 4),
                      residual_vs_original=round(z - o_[0][1], 4), samples_below=len(below), track_n=len(track),
                      product_vs_independent=abs(a[0][1] - b[0][1]))
            ok3 = (behs == ["YAM_C_Attente"] and spread <= 0.01 and margin >= 0.3 and bary[6] >= 0.2
                   and abs(a[0][1] - b[0][1]) <= 1e-4 and effect <= -0.05 and abs(z - a[0][1]) <= 0.02 and not below)
        else:
            inconclusive = True
    P = dict(j["P"])
    for k in ("P2 terrain loading", "P3 physics"):
        P.pop(k, None)
    P["P2a terrain readback"] = p2a
    P["P2b FairyLight readback"] = p2b
    P["P3 west-floor physics"] = ok3
    det = {"P2a": {k: sum(got[k].get(o) == want[o] for o in t_offs) for k in got} | {"of": len(t_offs)},
           "P2b": {k: sum(got[k].get(o) == want[o] for o in f_offs) for k in got} | {"of": len(f_offs),
                                                                                    "observed": observed_f},
           "P3": p3, "P3_inconclusive": inconclusive}
    if all(P.values()):
        verdict = "G6-P27 VERIFIED — AUTHORED WEST-FLOOR PHYSICS"
    elif not P["P1 atomic activation"]:
        verdict = "G6-P27 BLOCKED — TRANSACTION (P1)"
    elif not (P["P2a terrain readback"] and P["P2b FairyLight readback"]):
        verdict = "G6-P27 FAILED — GUEST READBACK (P2)"
    elif not P["P3 west-floor physics"] and (inconclusive or walk.get("result") != "reached"):
        verdict = "G6-P27 PARTIAL — MODIFIED TERRAIN LOADED, PHYSICS UNVERIFIED"
    elif not P["P3 west-floor physics"]:
        verdict = "G6-P27 FAILED — WEST-FLOOR PHYSICS MISMATCH (P3)"
    elif not P["P4 FairyLight"]:
        verdict = "G6-P27 FAILED — FAIRYLIGHT (P4)"
    else:
        verdict = "G6-P27 FAILED — EXIT / SAFETY (P5 / P6)"
    res = {"P": P, "verdict": verdict, "details": {**j["details"], **det}}
    jdump(f"judgement_g6p27_{tag}.json", res)
    print(json.dumps({"P": P, "verdict": verdict, "P2": det["P2a"] | {"fairy": det["P2b"]}, "P3": p3}, indent=1,
                     default=str))
    return 0 if verdict.startswith("G6-P27 VERIFIED") else 1


if __name__ == "__main__":
    cmd = sys.argv[1:]
    if cmd in (["preflight"], ["negtest"]):
        sys.exit({"preflight": preflight, "negtest": negtest}[cmd[0]]())
    if len(cmd) == 2 and cmd[0] in ("run", "judge"):
        sys.exit({"run": run, "judge": judge}[cmd[0]](cmd[1]))
    raise SystemExit(__doc__)
