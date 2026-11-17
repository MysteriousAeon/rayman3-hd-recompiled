#!/usr/bin/env python3
"""E-474 (D-241) G4d-1: scripted-actor functional closure. Prospective test of the additional MAN_mGenSound_Frog
(G4c construction, unchanged) against the guest scheduler model of G4d-0. Private, test-only (G3a gate), hidden,
read-only instrumentation.

SCHEDULER MODEL (re-verified in the generated code on this baseline, ecb9c47)
  82132F88(so): 82125FB8 increments 3dData +343 and wraps it to 0 at 3dData +342 (P); 82126000 lets the AI run only
  at +343 == 0; 3dData +344 (u16) += 1 per run; then 82251300 (reflex) / 822512D0 (normal) -> 822651D8.
  821256E8(3dData, n): +342 = n; +343 = 0 only if +343 >= n (else unchanged).
  Frog Init (first run, P = 1 from the file): procedure 373(value call 23(28, 35)) sets P (drawn from shared random
  stream 0, 8223ADB0, table in fix.lvl), v8 = timer, -> LoopOneShot. The counter is 0 at that run, so the actor
  then runs at frames f_init + k * P.
  LoopOneShot, evaluated only on runs: if |timer - v8| >= v5 (bool 49 = 8227DD10, timer 0x82C0628C, ms): v8 = timer
  (value call 66); no accumulation, at most one trigger per run.
  => Each inter-trigger interval is k * P frames with k the smallest integer such that the timer advanced >= v5 over
  k * P frames; every trigger timestamp lies on the actor's run phase.
PREDICTIONS (from the model, the G4d-0 random-table draws (fix.lvl offset 1,829,868, indices 76..79) and frame time
  F = 16.667 ms; v5 does not enter any draw, so B and C draw alike):
  A: source P 30 (k = 1: 30 F = 500.0, at the threshold -> 30 or 60 frames).
  B: source P 28 (28 F = 466.7 < 500 -> 56 frames = 933.3 ms only); copy P 33 (33 F = 550 -> 33 frames only).
  C: source P 28 (56 frames only); copy P 33, v5 2000 (99 F = 1650 < 2000 -> 132 frames = 2200 ms only).
  D: refused (no copy); source as A.
CASES: base (A), same (B), diff (C), nogate (D: C's plan without the gate). Exit / cleanup not re-run: the
  constructions are byte-identical to G4c n2's served files (checked by `check`), whose exit case passed S7.

PRE-REGISTERED CRITERIA (E-474; committed before any run)
C1 resource: G4c S1 (sizes, three files served in B / C, A mods off, D refused and nothing served, masked read-back
   equal in A-D) and `check`: G4c offline gate 21 / 21 and constructions byte-identical to G4c n2's served files.
C2 registration / initialization: G4c S2 (union of active / inactive worlds = A's + the copy; copy active; records
   123, copy last; backup targets; personal 70) and G4c S3 (own DsgMem / buffers / Brain / Mind / Intelligence,
   shared model, resolved sound events) in B and C; the source's live 3dData / Brain / Mind / DsgMem / buffer
   addresses equal in A-D.
C3 script execution: in A-D the source's, and in B / C the copy's, Intelligence +8 equals the live LoopOneShot record
   in every sample, and each actor's v8 takes >= 10 distinct values, each within the timer readings bracketing its
   sample.
C4 scheduler prediction: (a) live P constant over the window and equal to the prediction (A / D source 30; B / C
   source 28, copy 33); (b) AI runs (3dData +344 increments) per elapsed frame within 3 % of 1 / P; (c) every
   interval between consecutive distinct v8 values equals m * P frames within max(3, 0.004 * interval) ms, with m
   the predicted set ({1, 2} for A / D source, {2} for B / C source, {1} for the B copy, {4} for the C copy); (d)
   phase: for every sample, run time = timer - counter * F_meas (F_meas = measured ms per frame) and the current v8
   differ by a multiple of P * F_meas within F_meas + 3 ms.
C5 designer independence: in every sample, source initial / current v5 = 500 (A-D); copy initial / current v5 = 500
   (B) / 2000 (C); source and copy buffers at distinct addresses; source v8 sequence != copy v8 sequence.
C6 functional independence: copy median interval B within 3 ms of 33 F_meas and C within 8 ms of 132 F_meas; the
   source's intervals in C equal those in B (both 56 frames) and differ from A only through P (C4); no level change
   and intro_15 not opened in A-D.
C7 cleanup / memory: block-8 walks valid; area length AREA + N in B / C, AREA in A / D; free after load A / D =
   FREE0, B / C = FREE0 - N; level exit coverage = G4c n2 exit (byte-identical construction), not re-measured.
C8 safety: M21 / M22 / M23 0, haptics policy line, runner exit 0, no process left, no guest fault in the log.
Invalid run: process / area not found, structural read error, or < 60 s of samples.
RUN c1 (protocol 4229b02): C1 / C2 / C3 / C5 / C7 / C8 PASS; C4 / C6 FAIL (kept). Guest behaviour matched the
  model: source P 30 (A / D, 30 or 60 frames), 28 (B / C, 56 frames), copy P 33, intervals 550 / 551 (B) and
  2199-2201 (C), runs per frame 1/P within 3 %. Cause: the protocol's per-actor frame time F_meas = window ms /
  (AI runs * P) is quantized to +-1 run (about 0.7 % at P = 33): 16.567 ms for the copy against 16.719 for the
  source in the same process (impossible for one frame clock), so the copy's predicted k * P intervals were 3-13 ms
  short and its phase test drifted.
REVISION 1 (committed before c2; estimator only, tolerances and predictions unchanged): C4 (c) / (d) and C6 use the
  nominal frame F = 1000 / 60 ms (the timer advances in whole milliseconds per frame; every observed interval is
  m * P * 16.667 within 1 ms); the phase tolerance adds 0.4 % of the time since the trigger (as C4 (c) does for
  intervals). The measured value is still reported.
RUN c2 (revision 1; recorded after the run): C1-C8 PASS -> G4d-1 VERIFIED (Frog case); see the G4d-1 report.
Verdict: all C1-C8 -> G4d-1 VERIFIED — SCRIPTED ACTOR FUNCTIONAL INDEPENDENCE (this Frog case only); C2 / C3 pass
but C4 / C6 fail -> PARTIAL (discrepancy named).
"""
import hashlib
import json
import os
import re
import statistics
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

PREFIX = "e474"
RUNS, AREA, FREE0, SIZE, PSIZE = g3a.RUNS, g3a.AREA, g3a.FREE0, g3a.SIZE, g3a.PSIZE
GATE_ENV = g3a.GATE_ENV
CASES = ("base", "same", "diff", "nogate")
GROWN = ("same", "diff")
SECONDS, WATCH = 150, 75
D3 = 0xAC
F = 1000 / 60
PRED_P = {"base": {"src": 30}, "nogate": {"src": 30}, "same": {"src": 28, "copy": 33}, "diff": {"src": 28, "copy": 33}}
PRED_M = {"base": {"src": {1, 2}}, "nogate": {"src": {1, 2}}, "same": {"src": {2}, "copy": {1}},
          "diff": {"src": {2}, "copy": {4}}}
V5 = {"src": 500, "same": 500, "diff": 2000}


def check():
    rc = g4c.check()
    data, ptr, tl = g4c.files()
    same = {}
    for v in ("same", "diff", "exit"):
        nl, np_, nt, _ = g4c.construct(data, ptr, tl, v)
        w = ROOT / "private" / "work" / "e472" / "n2" / v
        same[v] = all((w / f"{k}_range.bin").read_bytes() == x for k, x in (("lvl", nl), ("ptr", np_), ("transit", nt)))
    print(json.dumps({"g4c_gate_rc": rc, "identical_to_g4c_n2": same}))
    return 0 if rc == 0 and all(same.values()) else 1


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
    variant = {"same": "same", "diff": "diff", "nogate": "diff"}.get(case)
    if variant:
        plan, _ = g4c.write_plan(work, data, ptr, tl, variant)
        env["R3HD_MODS_PLAN"] = row["plan"] = str(plan)
    if case in GROWN:
        env[GATE_ENV[0]] = GATE_ENV[1]
    L = g4c.layout()
    MASK = g4c.mask_words(data, ptr, tl)
    (work / "steps.txt").write_text(f"wait {SECONDS - 8}\n", encoding="ascii")
    states, samples = [], []
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
            area, last, deadline = None, None, t0 + 45
            while time.monotonic() < deadline and p.running() and area is None:
                ar = bp.areas(p)
                key = json.dumps({k: (v["base"], v["end"]) for k, v in (ar or {}).items()})
                if ar is not None and key != last:
                    last = key
                    s = bp.snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="areas_changed", area_keys=sorted(ar))
                    states.append(s)
                    a1 = s.get("areas", {}).get(1)
                    if a1 and a1["length"] >= AREA:
                        area = a1
                        blob = p.read(int(a1["base"], 16), AREA)
                        if blob:
                            blob = bytearray(blob)
                            for o in MASK:
                                blob[o - 4:o] = bytes(4)
                        row["original_readback_sha256"] = hashlib.sha256(blob).hexdigest() if blob else None
                time.sleep(0.005)
            if area is None:
                row["error"] = "level area not seen"
            else:
                row["area"] = area
                ab = int(area["base"], 16)
                grown = area["length"] > AREA
                live = lambda fo: ab + fo - 4                     # noqa: E731

                def w(a):
                    x = p.words(a, 1)
                    if not x:
                        raise ValueError(f"read {a:#x}")
                    return x[0]

                def lists():
                    r = {}
                    try:
                        for key, g_ in (("dw", g4c.G_DW), ("inactive", g4c.G_INACT)):
                            h = w(g_)
                            walk, so = [], w(h + 8)
                            while so and len(walk) < 400:
                                walk.append(so)
                                so = w(so + 0x14)
                            r[key] = {"count": w(h + 0x10), "walk": walk,
                                      "prev_ok": all(w(b + 0x18) == a for a, b in zip(walk, walk[1:]))}
                        h = w(g4c.G_REC)
                        recs, c = [], w(h)
                        while c and len(recs) < 1000:
                            recs.append(w(c + 4))
                            nx = w(c)
                            if nx == c:
                                break
                            c = nx
                        r["rec"] = {"count": w(h + 8), "n": len(recs), "last_so": recs[-1] if recs else None}
                        links, l_ = [], w(g4c.G_BAK)
                        while l_ and len(links) < 2000:
                            links.append(w(l_ + 4))
                            l_ = w(l_)
                        r["bak_targets"] = links
                        pc = w(g4c.G_OBJ + 0x20)
                        e, i = w(g4c.G_OBJ + 0x18), 0
                        while e and i < pc - 1:
                            e, i = w(e), i + 1
                        nm = p.read(w(e + 0xC), 24) if e else None
                        r["personal"] = {"count": pc, "last_name": nm.split(bytes(1))[0].decode("ascii", "replace")
                                         if nm else None}
                    except Exception as x:
                        r["error"] = repr(x)
                    return r

                def actor(fo):
                    dm = live(fo + g4c.DSGMEM)
                    ini, cur = w(dm + 4), w(dm + 8)
                    ev = list(p.words(ini, 4) or []) + list(p.words(cur, 4) or [])
                    return {"dsgmem": dm, "dsgvar": w(dm), "ini": ini, "cur": cur, "mind0": w(live(fo + g4c.MIND)),
                            "d3": w(live(fo + 0x80)), "brain": w(live(fo + 0x80 + 0xC)),
                            "mind": w(live(fo + g4c.BRAIN)), "intel": w(live(fo + g4c.MIND + 4)),
                            "mind_dsgmem": w(live(fo + g4c.MIND + 0xC)), "brain4": w(live(fo + g4c.BRAIN + 4)),
                            "buf3d": w(live(fo + 0x14C)), "events": ev}
                time.sleep(1.0)
                row["live_first"] = {"lists": lists()}
                acts = {}
                try:
                    acts = {"src": actor(g4c.SRC)}
                    if grown:
                        acts["copy"] = actor(L["fc"])
                    row["actors"] = acts
                except Exception as x:
                    row["error"] = f"actor read {x!r}"
                row["loop_oneshot"] = live(g4c.LOOP_ONESHOT)
                t_end = time.monotonic() + WATCH
                while time.monotonic() < t_end and p.running() and acts:
                    now = time.monotonic()
                    a1 = (bp.areas(p) or {}).get(1)
                    if a1 and a1["base"] != ab:
                        row["level_change_t"] = round(now - t0, 3)
                        break
                    try:
                        smp = {"t": round(now - t0, 3), "timer": w(g4c.TIMER)}
                        for k, a in acts.items():
                            sb = p.read(a["d3"] + 340, 8)
                            ib, cb = p.read(a["ini"], g4c.VLEN), p.read(a["cur"], g4c.VLEN)
                            smp[k] = {"P": sb[2], "ctr": sb[3], "runs": struct.unpack_from(">H", sb, 4)[0],
                                      "beh": w(a["intel"] + 8), "ini_v5": struct.unpack_from(">i", ib, g4c.V5)[0],
                                      "cur_v5": struct.unpack_from(">i", cb, g4c.V5)[0],
                                      "v8": struct.unpack_from(">I", cb, g4c.V8)[0]}
                        smp["timer2"] = w(g4c.TIMER)
                        samples.append(smp)
                    except Exception as x:
                        row["sampling_stopped"] = repr(x)
                        break
                    time.sleep(0.1)
                if p.running():
                    row["live_end"] = {"lists": lists()}
                    s = bp.snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="final", area_keys=sorted(bp.areas(p) or {}))
                    states.append(s)
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and g3a.alive(pid))
    for name, obj in (("states", states), ("samples", samples), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj) + "\n")
    return {k: v for k, v in row.items() if k not in ("live_first", "live_end", "actors")}


def seq(sm, k):
    vals, inwin, prev = [], [], None
    for s in sm:
        if k not in s:
            continue
        v = s[k]["v8"]
        if v and (not vals or v != vals[-1]):
            vals.append(v)
            if prev is not None:
                inwin.append(prev["timer"] <= v <= s["timer2"])
        prev = s
    return vals, [b - a for a, b in zip(vals, vals[1:])], inwin


def judge(tag):
    data, ptr, tl = g4c.files()
    L = g4c.layout()
    N = L["end"] - SIZE
    K = len(g4c.construct(data, ptr, tl, "diff")[3]["newslots"])
    out = {}
    for case in CASES:
        work = ROOT / "private" / "work" / PREFIX / tag / case
        run = f"{PREFIX}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        row["states"] = json.loads((work / "states.json").read_text())
        row["samples"] = json.loads((work / "samples.json").read_text())
        log = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / run).glob("runtime*.log")))
        row["grow_size"] = sorted(set(re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)))
        row["served_files"] = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
        row["mods_off"] = "M33 mods=off" in log
        row["refused"] = "grow_not_allowed" in log
        row["fault"] = "access violation" in log
        row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
        row["lvl_opens"] = [o.rsplit("\\", 1)[-1].lower() for o in
                            re.findall(r"vfs_open path=(\S+?\.lvl) result=00000000", log)]
        judges = {}
        for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
            r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True,
                               text=True)
            judges[tool] = r.returncode
            (work / f"{tool}.log").write_text(r.stdout + r.stderr)
        row["judges"] = judges
        out[case] = row
    invalid = [c for c, r in out.items() if r.get("error") or not r["samples"]
               or ((r.get("live_first") or {}).get("lists") or {}).get("error")
               or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60]

    def ab(r):
        return int(r["area"]["base"], 16) if r.get("area") else 0
    # C1
    want = sorted([("intro_10.lvl", str(SIZE), str(SIZE + N)), ("intro_10.ptr", str(PSIZE), str(PSIZE + 8 * K))])
    c1 = all(out[c]["grow_size"] == want and out[c]["served_files"] == ["intro_10.lvl", "intro_10.ptr", "transit.lvl"]
             for c in GROWN)
    c1 = c1 and out["base"]["mods_off"] and not out["base"]["grow_size"] and out["nogate"]["refused"] \
        and not out["nogate"]["grow_size"] and not out["nogate"]["served_files"]
    shas = {c: r.get("original_readback_sha256") for c, r in out.items()}
    c1 = c1 and shas["base"] is not None and len(set(shas.values())) == 1 and check() == 0

    # C2
    def union(lst):
        d, i = lst.get("dw", {}), lst.get("inactive", {})
        both = d.get("walk", []) + i.get("walk", [])
        return set(both), len(both) == len(set(both)) and d.get("prev_ok") and i.get("prev_ok"), set(d.get("walk", []))
    a_u = union(((out["base"].get("live_first") or {}).get("lists")) or {})[0]
    c2, reg = len(a_u) == 66, {}
    for c, r in out.items():
        b = ab(r)
        copy_so, src_so = b + L["fc"] - 4, b + g4c.SRC - 4
        ok = bool(b)
        for k in ("live_first", "live_end"):
            lst = ((r.get(k) or {}).get("lists")) or {}
            U, nodup, dws = union(lst)
            rec, per = lst.get("rec", {}), lst.get("personal", {})
            ok = ok and nodup and src_so in dws
            if c in GROWN:
                ok = (ok and U == a_u | {copy_so} and copy_so in dws and rec.get("count") == rec.get("n") == 123
                      and rec.get("last_so") == copy_so
                      and all(copy_so + o in lst.get("bak_targets", []) for o in (0xC4, 0x510, 0x514, 0x518))
                      and per.get("count") == 70 and per.get("last_name") == "MAN_mGenSound_Frog_G4C")
            else:
                ok = ok and U == a_u and rec.get("count") == rec.get("n") == 122 and per.get("count") == 69
        a = r.get("actors") or {}
        sa, ca = a.get("src") or {}, a.get("copy") or {}
        lv = lambda fo: b + fo - 4                            # noqa: E731
        ok = ok and bool(sa) and sa["ini"] == lv(g4c.SRC + g4c.INI) and sa["cur"] == lv(g4c.SRC + g4c.CUR)
        if c in GROWN:
            ok = (ok and bool(ca) and ca["dsgvar"] == sa["dsgvar"] == lv(g4c.MODEL + 8)
                  and ca["ini"] == lv(L["fc"] + g4c.INI) and ca["cur"] == lv(L["fc"] + g4c.CUR)
                  and ca["mind0"] == sa["mind0"] and ca["dsgmem"] == lv(L["fc"] + g4c.DSGMEM)
                  and ca["mind_dsgmem"] == ca["dsgmem"] and ca["brain"] == lv(L["fc"] + g4c.BRAIN)
                  and ca["mind"] == lv(L["fc"] + g4c.MIND) and ca["intel"] == lv(L["fc"] + g4c.INTEL)
                  and ca["d3"] == lv(L["fc"] + D3) and ca["brain4"] == sa["brain4"]
                  and ca["events"] == sa["events"] and len(ca["events"]) == 8 and g4c.RAW_EVENT not in ca["events"])
        reg[c] = {"ok": bool(ok), "src": {k: v for k, v in sa.items() if k != "events"},
                  "copy": {k: v for k, v in ca.items() if k != "events"}}
        c2 = c2 and ok
    src_ids = [{k: v for k, v in reg[c]["src"].items() if k in ("d3", "brain", "mind", "dsgmem", "ini", "cur")}
               for c in CASES]
    c2 = c2 and all(x == src_ids[0] for x in src_ids)
    # C3 / C4 / C5 / C6
    beh, c3, c4, c5 = {}, True, True, True
    for c in CASES:
        sm = out[c]["samples"]
        lo = out[c].get("loop_oneshot")
        ms = sm[-1]["timer"] - sm[0]["timer"] if sm else 0
        for k in PRED_P[c]:
            vals, iv, inwin = seq(sm, k)
            Ps = sorted({s[k]["P"] for s in sm})
            runs = (sm[-1][k]["runs"] - sm[0][k]["runs"]) % 65536 if sm else 0
            frames = ms / F if ms else 0
            P = Ps[0] if len(Ps) == 1 else None
            fm_meas = ms / (runs * P) if P and runs else None     # reported; window-quantized (+-1 run)
            fm = fm_meas if tag == "c1" else F                       # revision 1: nominal 60 Hz frame
            ms_m = {m: [x for x in iv if fm and abs(x - m * P * fm) <= max(3, 0.004 * x)] for m in PRED_M[c][k]}
            matched = sum(len(v) for v in ms_m.values())
            phase_bad = 0
            if fm and P:
                for s in sm:
                    run_t = s["timer"] - s[k]["ctr"] * fm
                    d = (run_t - s[k]["v8"]) / (P * fm)
                    tol = fm + 3 + (0 if tag == "c1" else 0.004 * max(0, run_t - s[k]["v8"]))
                    if s[k]["v8"] and abs(d - round(d)) * P * fm > tol:
                        phase_bad += 1
            e = {"P": Ps, "runs": runs, "frames": round(frames, 1), "ms_per_frame": round(fm, 3) if fm else None,
                 "ms_per_frame_measured": round(fm_meas, 3) if fm_meas else None,
                 "runs_per_frame": round(runs / frames, 5) if frames else None, "n_values": len(vals),
                 "intervals": len(iv), "by_m": {m: len(v) for m, v in ms_m.items()},
                 "unmatched": sorted(set(iv) - {x for v in ms_m.values() for x in v})[:10],
                 "median": statistics.median(iv) if iv else None, "phase_bad": phase_bad,
                 "v8_first": vals[:6], "ini_v5": sorted({s[k]["ini_v5"] for s in sm}),
                 "cur_v5": sorted({s[k]["cur_v5"] for s in sm}),
                 "beh_ok": bool(sm) and all(s[k]["beh"] == lo for s in sm), "inwin_all": bool(inwin) and all(inwin)}
            beh[f"{c}_{k}"] = e
            c3 = c3 and e["beh_ok"] and e["n_values"] >= 10 and e["inwin_all"]
            c4 = (c4 and P == PRED_P[c][k] and frames and abs(runs / frames - 1 / P) <= 0.03 / P
                  and matched == len(iv) > 0 and phase_bad == 0)
            want_v5 = V5["src"] if k == "src" else V5[c]
            c5 = c5 and e["ini_v5"] == e["cur_v5"] == [want_v5]
        if c in GROWN:
            c5 = (c5 and seq(sm, "src")[0] != seq(sm, "copy")[0]
                  and len({reg[c]["src"]["ini"], reg[c]["src"]["cur"], reg[c]["copy"]["ini"], reg[c]["copy"]["cur"]}) == 4)
    fm = {c: beh[f"{c}_copy"]["ms_per_frame"] for c in GROWN}
    c6 = (beh["same_copy"]["median"] is not None and fm["same"] and abs(beh["same_copy"]["median"] - 33 * fm["same"]) <= 3
          and beh["diff_copy"]["median"] is not None and fm["diff"]
          and abs(beh["diff_copy"]["median"] - 132 * fm["diff"]) <= 8
          and beh["same_src"]["by_m"] == {2: beh["same_src"]["intervals"]}
          and beh["diff_src"]["by_m"] == {2: beh["diff_src"]["intervals"]}
          and all(not out[c].get("level_change_t") and "intro_15.lvl" not in out[c]["lvl_opens"] for c in CASES))
    # C7
    alloc = {}
    for c, r in out.items():
        st = r["states"]
        i0 = next((k for k, x in enumerate(st) if "invalid" not in x), None)
        valid = i0 is not None and not any("invalid" in x for x in st[i0:])
        used = [s for s in st if "invalid" not in s and "1" in s.get("areas", {})]
        alloc[c] = {"valid": valid, "length": (r.get("area") or {}).get("length"),
                    "free_after": used[-1]["free_bytes"] if used else None}
    c7 = all(alloc[c]["valid"] and alloc[c]["length"] == AREA + (N if c in GROWN else 0) for c in CASES)
    c7 = c7 and alloc["base"]["free_after"] == FREE0 == alloc["nogate"]["free_after"] \
        and all(alloc[c]["free_after"] == FREE0 - N for c in GROWN)
    c8 = all(r["haptics_policy"] and not any(r["judges"].values()) and r["runner_exit"] == 0 and not r["process_left"]
             and not r["fault"] for r in out.values())
    checks = {"C1_resource": bool(c1), "C2_registration_init": bool(c2), "C3_script_execution": bool(c3),
              "C4_scheduler_prediction": bool(c4), "C5_designer_independence": bool(c5),
              "C6_functional_independence": bool(c6), "C7_cleanup_memory": bool(c7), "C8_safety": bool(c8)}
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()),
              "behaviour": beh, "registration": reg, "alloc": alloc, "readback": shas,
              "grow_size": {c: r["grow_size"] for c, r in out.items()}, "served": {c: r["served_files"] for c, r in out.items()},
              "judges": {c: r["judges"] for c, r in out.items()}, "runner_exit": {c: r["runner_exit"] for c, r in out.items()}}
    (ROOT / "private" / "work" / PREFIX / tag / "judgement.json").write_text(json.dumps(result, indent=1, default=str) + "\n")
    print(json.dumps({k: result[k] for k in ("invalid", "checks", "pass", "behaviour", "alloc")}, indent=1, default=str))
    return 0 if result["pass"] else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return check()
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
