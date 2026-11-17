#!/usr/bin/env python3
"""E-467 (D-234) G2: one existing relocated pointer redirected to a waypoint copy appended past intro_10.lvl's end.
Private, test-only (E-465 gate, e465_test_grow_patch.py); hidden and read-only at run time.

STRUCTURE (static, `check` re-verifies every item from the files and fails closed)
intro_10.lvl 7,661,836 bytes, SHA-256 a37638bf...19e2ee, FNV-1a 64 7982c1135516c2b6; intro_10.ptr 209,068 bytes
(n 25,143, m 495; SHA-256 6c9dd70c...8200e940). Flight generator NIN_m_GenFlyIntro_10, designer variable 0 (graph 0x542498,
143 nodes, editable), node 13 at file 0x542610 {+0 next, +4 previous, +8 graph, +0xC waypoint, +0x18 arcs; all five
pointer words relocated}. Its waypoint (0x14 bytes: x, y, z, radius 1.0, word 0) at file 0x545468 =
W (19.207331, -32.903214, -40.101063). The only pointer to it is node 13's +0xC at file 0x54261C, stored value
0x545464 (= target - 4), relocated by .ptr entry 17028 {file 1, slot 0x542618}. No .ptr slot inside the waypoint,
no pointer into it, no cross-file (m) entry and no transit / fix pointer touching node 13 or the waypoint; the
waypoint holds no pointer, so the copy needs no relocation and `.ptr` is NOT changed or served.
CONSTRUCTION (bytes the plan serves; the guest asks for the grown length through the E-465 test gate)
  [0, 7,661,836): the original file, except the 4 bytes at 0x54261C: 0x00545464 -> 0x0074E914.
  tail N = 32 bytes at 7,661,836: 12 zero bytes, then the copy at file F = 7,661,848 (0x74E918; F = 0x545468 mod 16,
  so the copy's guest address has the original's 16-byte alignment); F - 4 = 0x74E914; F + 0x14 = 7,661,868 = the
  grown length. Variant `copy`: the 20 bytes identical. Variant `mod`: x only = W.x + 6 = 25.207331 (f32 41C9A89D),
  y, z, radius, word 4 identical (W'' = (25.207331, -32.903214, -40.101063)).
  Changed bytes inside the original: 0x54261D..0x54261F only (the slot's first byte stays 00); the mod copy differs
  from the original waypoint in byte 1 only (0x99 -> 0xC9). Served payload FNV / SHA-256: copy 38cac3df0b74b630 /
  151650ef...d558c55d, mod 34c29abfd10f5720 / 26cc68b9...e4c8d61f (`check` recomputes; offline gate 15/15 PASS).
  Plan: `grow 0 7661868`, one range [0, 7,661,868) whose game-bytes hash is the original file's FNV (fail closed).
  Guest area length 7,661,864 (+32), chunk words words_for(7,661,864) (+8); block-8 free 13,088,528 -> 13,088,496.
EXPECTED live (area base B from the block-8 table; E-465a: 0x40F5509C): node 13 +0xC = B + 0x545464 (base, nogate)
  or B + 0x74E914 (copy, mod); original waypoint at B + 0x545464, copy at B + 0x74E914.
  Generator variable 8 (type 19) is the current waypoint's address (E-460 base runs: B + 0x545464 about four samples
  per loop at 0.1 s), variable 10 its position.
CASES (one hidden run each; m9_license_run.py: hidden window, muted, no physical pad, isolated private profile,
  `--test-level intro_10`, no input, no captures; 150 s, generator sampled every 0.1 s for 75 s, tail every 1 s):
  A base: no plan.   B copy: copy plan + gate env.   C mod: mod plan + gate env.   D nogate: mod plan, gate env unset.
PROTOCOL (committed before any run; thresholds fixed here, from E-464's run-to-run noise 0.15 and tolerance 0.5)
  R1 resource: B / C log one `M36 grow size file=intro_10.lvl host_size=7661836 guest_size=7661868` and no other
     grow line, serve intro_10.lvl only, grow reads kind=tail; A / D none (A `M33 mods=off`; D `grow_not_allowed`);
     SHA-256 of the area's first 7,661,832 bytes read back at its first appearance, with the 4 bytes at area offset
     0x542618 zeroed, equal in A, B, C, D; the 32 tail bytes read back equal to the construction at every read for
     60 s (B, C); the original waypoint's live 20 bytes equal the file's in all cases at the end.
  R2 relocation: live node 13 +0xC = B + 0x74E914 in B and C, = B + 0x545464 in A and D (first read and end).
  R3 consumption: generator variable 8 equals the copy's address in >= 3 samples and never the original's in B and
     C; equals the original's in >= 3 samples and never the copy's in A and D; at the samples with variable 8 = the
     copy, C's variable 10 equals W'' (each coordinate within 1e-4) at least once and never W; B's equals W.
  R4 identical copy: B's sampled path (after the latest first sample of the four runs + 0.5 s) within 0.5 of A's
     path, and B's closest approach to W'' within 0.5 of A's; D the same (gate off = original level).
  R5 effect: C's maximum distance from A's path >= 1.5 (10 x noise) at a sample within 25 units of W, displaced
     toward W'' (positive dot product with W'' - W); C's closest approach to W'' at least 1.0 smaller than A's;
     C's samples more than 25 units from W within 0.5 of A's path.
  R6 safety: valid block-8 walk in every snapshot after the first valid one; area length 7,661,864 and chunk words
     words_for(7,661,864) in B / C, 7,661,832 in A / D; free after the load 13,088,496 (B / C), 13,088,528 (A / D);
     haptics policy line, M21 / M22 / M23 0, runner exit 0, no game process left in every case; the gate reverted
     (status production) and rebuilt after the runs.
  Invalid (new tag, not judged): file / .ptr hashes differ, level not opened, area or generator not found, fewer
  than 60 s of samples, or a run's first sample after A's closest approach to W.
  Classes: R2 alone = pointer resolution; R3 = consumption; R5 = functional effect (not claimed without R3).

usage: g2_appended_ab.py check | TAG [--cases base,copy,mod,nogate] | judge TAG
Outputs stay under private/work/e467/.
"""
import argparse
import hashlib
import json
import math
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

GAME = ROOT / "private" / "extracted" / "5841123F"
LDIR = GAME / "GAMEDATAbin" / "intro_10"
LVL, PTR = LDIR / "intro_10.lvl", LDIR / "intro_10.ptr"
RUNS = ROOT / "private" / "work" / "m6_runs"
PREFIX = "e467"
SIZE = 7661836
ORIG_SHA = "a37638bf1370357db21f33df5c4d37ae806b3c4b9f81b331503ba62d1b19e2ee"
ORIG_FNV = "7982c1135516c2b6"
PTR_SHA = "6c9dd70c488a1cac95efc0a55a6086255dae2d851bacd93f5abefdcc8200e940"
GRAPH, NODE, SLOT, WPO = 0x542498, 0x542610, 0x54261C, 0x545468
OLD_VAL, PTR_INDEX = 0x545464, 17028
PAD, N = 12, 32
F = SIZE + PAD
NEW_VAL = F - 4
AREA = SIZE - 4
W = (19.20733070373535, -32.90321350097656, -40.1010627746582)
W2 = (25.20733070373535, -32.90321350097656, -40.1010627746582)
W2X = bytes.fromhex("41c9a89d")
FREE0 = 13088528
SECONDS, WATCH = 150, 75
CASES = ("base", "copy", "mod", "nogate")
GEN = "NIN_m_GenFlyIntro_10"


def fnv(b):
    h = 0xCBF29CE484222325
    for x in b:
        h = ((h ^ x) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def files():
    data, ptr = LVL.read_bytes(), PTR.read_bytes()
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != ORIG_SHA or f"{fnv(data):016x}" != ORIG_FNV:
        raise SystemExit("file check: intro_10.lvl is not the protocol's file")
    if hashlib.sha256(ptr).hexdigest() != PTR_SHA:
        raise SystemExit("file check: intro_10.ptr is not the protocol's file")
    return data, ptr


def construct(data, variant):
    wp = data[WPO:WPO + 0x14]
    copy = wp if variant == "copy" else W2X + wp[4:]
    new = bytearray(data)
    new[SLOT:SLOT + 4] = struct.pack(">I", NEW_VAL)
    tail = b"\0" * PAD + copy
    assert len(tail) == N
    return bytes(new) + tail, tail


def check():
    """Offline safety gate: every structural and construction claim of the protocol, from the files."""
    data, ptr = files()
    n, m = u32(ptr, 0), u32(data, 0)
    res = {}
    ents = [struct.unpack_from(">iI", ptr, 4 + 8 * i) for i in range(n)]
    slots = {loc + 4: f for f, loc in ents}

    def target(o):
        return u32(data, o) + 4 if slots.get(o) == 1 else None
    res["ptr_layout"] = 4 + 8 * n + 16 * m == len(ptr) and len(slots) == n
    res["ptr_entry"] = tuple(ents[PTR_INDEX]) == (1, SLOT - 4) and sum(1 for f, loc in ents if loc + 4 == SLOT) == 1
    res["stored_value"] = u32(data, SLOT) == OLD_VAL and OLD_VAL + 4 == WPO
    res["node_links"] = (target(NODE + 8) == GRAPH and target(NODE + 0xC) == WPO
                         and all(NODE + k in slots for k in (0, 4, 8, 0xC, 0x18)))
    res["single_reference"] = [o for o in slots if target(o) is not None and WPO <= target(o) < WPO + 0x14] == [SLOT]
    res["no_slot_in_waypoint"] = not any(o in slots for o in range(WPO - 3, WPO + 0x14))
    cross = [struct.unpack_from(">IiIi", ptr, 4 + 8 * n + 16 * j) for j in range(m)]
    res["no_cross_entry"] = not any(
        (fa == 1 and (NODE <= oa + 4 < NODE + 0x1C or WPO <= oa + 4 < WPO + 0x14))
        or (fb == 1 and (NODE <= ob + 4 < NODE + 0x1C or WPO <= ob + 4 < WPO + 0x14)) for oa, fa, ob, fb in cross)
    tl, tp = (LDIR / "transit.lvl").read_bytes(), (LDIR / "transit.ptr").read_bytes()
    tr = []
    for i in range(u32(tp, 0)):
        f, loc = struct.unpack_from(">iI", tp, 4 + 8 * i)
        if f == 1 and (NODE <= u32(tl, loc + 4) + 4 < NODE + 0x1C or WPO <= u32(tl, loc + 4) + 4 < WPO + 0x14):
            tr.append(i)
    fp = (GAME / "GAMEDATAbin" / "fix.ptr").read_bytes()
    res["no_transit_or_fix_reference"] = not tr and not any(
        struct.unpack_from(">iI", fp, 4 + 8 * i)[0] == 1 for i in range(u32(fp, 0)))
    wp = data[WPO:WPO + 0x14]
    res["waypoint_value"] = struct.unpack(">3f", wp[:12]) == W and struct.unpack(">f", wp[12:16])[0] == 1.0 \
        and wp[16:] == b"\0" * 4
    res["w2_bits"] = struct.unpack(">f", W2X)[0] == W2[0] and W2[1:] == W[1:]
    desc = {}
    for variant in ("copy", "mod"):
        new, tail = construct(data, variant)
        diff = [i for i in range(SIZE) if new[i] != data[i]]
        cp = new[F:F + 0x14]
        cdiff = [i for i in range(0x14) if cp[i] != wp[i]]
        ok = (len(new) == SIZE + N and diff and min(diff) >= SLOT and max(diff) < SLOT + 4
              and u32(new, SLOT) == NEW_VAL and NEW_VAL + 4 == F and F + 0x14 <= len(new)
              and F % 4 == 0 and F % 16 == WPO % 16 and new[SIZE:F] == b"\0" * PAD
              and (cdiff == [] if variant == "copy" else (cdiff and max(cdiff) < 4 and cp[:4] == W2X)))
        res[f"construct_{variant}"] = bool(ok)
        desc[variant] = {"length": len(new), "changed_in_original": [f"0x{i:X}" for i in diff],
                         "slot": f"0x{SLOT:X}: {OLD_VAL:08X} -> {NEW_VAL:08X}", "tail_at": SIZE, "copy_at": F,
                         "tail_hex": tail.hex(), "copy_changed_bytes": cdiff, "fnv": f"{fnv(new):016x}",
                         "sha256": hashlib.sha256(new).hexdigest()}
    res["guest_target_inside_area"] = NEW_VAL + 0x14 <= (SIZE + N) - 4
    res["capacity"] = bp.words_for(AREA + N) * 4 - bp.words_for(AREA) * 4 == N and N <= FREE0 - 868496
    prod = (TOOLS / "m33_mod_overlay.h").read_text(encoding="utf-8")
    res["production_refuses_lvl_growth"] = 'kGrowNames' in prod and "intro_10" not in prod \
        and "E465" not in prod
    out = {"checks": res, "pass": all(res.values()), "constructions": desc,
           "ptr_sha256": hashlib.sha256(ptr).hexdigest()}
    d = ROOT / "private" / "work" / PREFIX
    d.mkdir(parents=True, exist_ok=True)
    (d / "offline.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0 if out["pass"] else 1


def write_plan(work, data, variant):
    new, _ = construct(data, variant)
    blob = work / "range.bin"
    blob.write_bytes(new)
    plan = work / "plan.txt"
    plan.write_text("R3HD_MOD_PLAN 1\n# E-467 test-only plan (g2_appended_ab.py)\nmod e467.g2 1.0.0\n"
                    f"file {SIZE} {LVL}\ngrow 0 {SIZE + N}\n"
                    f"range 0 0 {SIZE + N} {ORIG_FNV} {fnv(new):016x} e467.g2 {blob}\nend 1 1\n", encoding="utf-8")
    return plan


def alive(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in r.stdout


def run_case(tag, case):
    from m5_live import Actor, Process
    data, _ = files()
    work = ROOT / "private" / "work" / PREFIX / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    env.pop("R3HD_E465_TEST_GROW", None)
    row = {"case": case, "run": run}
    if case != "base":
        env["R3HD_MODS_PLAN"] = row["plan"] = str(write_plan(work, data, "copy" if case == "copy" else "mod"))
    if case in ("copy", "mod"):
        env["R3HD_E465_TEST_GROW"] = "intro_10.lvl"
    (work / "steps.txt").write_text(f"wait {SECONDS - 8}\n", encoding="ascii")
    states, tails, samples = [], [], []
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
                m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", lp.read_text(errors="replace"))
                base = m.group(1) if m else None
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
                    if a1 and a1["length"] in (AREA, AREA + N):
                        area = a1
                        ab = int(a1["base"], 16)
                        blob = p.read(ab, AREA)
                        if blob:
                            blob = blob[:SLOT - 4] + b"\0" * 4 + blob[SLOT:]
                        row["original_readback_sha256"] = hashlib.sha256(blob).hexdigest() if blob else None
                time.sleep(0.005)
            if area is None:
                row["error"] = "level area not seen"
            else:
                row["area"] = area
                ab = int(area["base"], 16)

                def live(label):
                    sl = p.words(ab + SLOT - 4, 1)
                    row[label] = {"slot": sl[0] if sl else None,
                                  "orig_wp": (p.read(ab + OLD_VAL, 0x14) or b"").hex(),
                                  "copy": (p.read(ab + NEW_VAL, 0x14) or b"").hex()
                                  if area["length"] == AREA + N else None}
                live("live_first")
                disc = work / "discovery.json"
                q = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc),
                                    "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
                gen = None
                for a in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if q.returncode == 0 else []):
                    try:
                        act = Actor(p, int(a["so"], 16))
                    except Exception:
                        continue
                    if act.model == GEN and act.mind:
                        gen = act
                        break
                if gen is None:
                    row["error"] = "generator not found"
                t_end, next_tail = time.monotonic() + WATCH, 0.0
                while time.monotonic() < t_end and p.running():
                    now = time.monotonic()
                    if area["length"] == AREA + N and now >= next_tail:
                        b = p.read(ab + AREA, N)
                        tails.append({"t": round(now - t0, 3), "hex": b.hex() if b else None})
                        next_tail = now + 1.0
                    if gen is not None:
                        try:
                            v = gen.dsg()
                            samples.append({"t": round(now - t0, 3), "pos": gen.position(),
                                            "v8": u32(*v[8]), "v9": u32(*v[9]),
                                            "v10": struct.unpack_from(">3f", *v[10]),
                                            "v11": struct.unpack_from(">3f", *v[11])})
                        except Exception as x:
                            row["sampling_stopped"] = type(x).__name__
                            gen = None
                    time.sleep(0.1)
                if p.running():
                    live("live_end")
                    s = bp.snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="final", area_keys=sorted(bp.areas(p) or {}))
                    states.append(s)
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and alive(pid))
    for name, obj in (("states", states), ("tails", tails), ("samples", samples), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1) + "\n")
    return row


def seg(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]
    n2 = sum(v * v for v in ab)
    t = 0.0 if not n2 else max(0.0, min(1.0, sum((p[i] - a[i]) * ab[i] for i in range(3)) / n2))
    q = [a[i] + t * ab[i] for i in range(3)]
    return math.dist(p, q), q


def to_path(p, path):
    return min((seg(p, a, b) for a, b in zip(path, path[1:])), key=lambda x: x[0])


def judge(tag):
    data, _ = files()
    out = {}
    for case in CASES:
        work = ROOT / "private" / "work" / PREFIX / tag / case
        run = f"{PREFIX}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        for k in ("states", "tails", "samples"):
            row[k] = json.loads((work / f"{k}.json").read_text())
        log = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / run).glob("runtime*.log")))
        row["grow_size"] = re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)
        row["grow_reads"] = re.findall(r"M36 grow read file=(\S+) offset=(\d+) length=(\d+) host=(\d+) served=(\d+)"
                                       r" kind=(\S+)", log)
        row["served_files"] = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
        row["mods_off"] = "M33 mods=off" in log
        row["refused"] = "grow_not_allowed" in log
        row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
        judges = {}
        for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
            r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True,
                               text=True)
            judges[tool] = r.returncode
            (work / f"{tool}.log").write_text(r.stdout + r.stderr)
        row["judges"] = judges
        out[case] = row
    A, B, C, D = (out[c] for c in CASES)
    grown = ("copy", "mod")
    invalid = [c for c, r in out.items() if r.get("error") or not r["samples"]
               or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60]
    base_pts = [s["pos"] for s in A["samples"]]
    t_close = min(A["samples"], key=lambda s: math.dist(s["pos"], W))["t"] if base_pts else 0
    invalid += [c for c, r in out.items() if r["samples"] and r["samples"][0]["t"] >= t_close and c not in invalid]
    start = max(r["samples"][0]["t"] for r in out.values() if r["samples"]) + 0.5 if not invalid else 0
    path = [s["pos"] for s in A["samples"] if s["t"] >= start - 1.0]

    def pts(r):
        return [s["pos"] for s in r["samples"] if s["t"] >= start]

    def maxdev(r, region=None):
        o = [(to_path(q, path), q) for q in pts(r)]
        if region is not None:
            o = [x for x in o if math.dist(x[1], W) > region]
        return max(o, key=lambda x: x[0][0]) if o else None

    def closest(r, target):
        q = pts(r)
        return to_path(target, q)[0] if len(q) > 1 else None

    def ab(r):
        return int(r["area"]["base"], 16) if r.get("area") else None
    want_tail = {v: construct(data, v)[1].hex() for v in grown}

    # R1
    r1 = all(out[c]["grow_size"] == [("intro_10.lvl", str(SIZE), str(SIZE + N))] and
             out[c]["served_files"] == ["intro_10.lvl"] and bool(out[c]["grow_reads"]) and
             all(x[0] == "intro_10.lvl" and x[5] == "tail" for x in out[c]["grow_reads"]) for c in grown)
    r1 = r1 and not A["grow_size"] and A["mods_off"] and not D["grow_size"] and D["refused"]
    shas = {c: r.get("original_readback_sha256") for c, r in out.items()}
    r1 = r1 and shas["base"] is not None and len(set(shas.values())) == 1
    r1 = r1 and all(len(out[c]["tails"]) >= 55 and all(t["hex"] == want_tail[c] for t in out[c]["tails"])
                    and out[c]["tails"][-1]["t"] - out[c]["tails"][0]["t"] >= 55 for c in grown)
    wp_hex = data[WPO:WPO + 0x14].hex()
    r1 = r1 and all((r.get("live_end") or {}).get("orig_wp") == wp_hex for r in out.values())
    # R2
    def slot_ok(c):
        r = out[c]
        want = ab(r) + (NEW_VAL if c in grown else OLD_VAL) if ab(r) else None
        return want is not None and all((r.get(k) or {}).get("slot") == want for k in ("live_first", "live_end"))
    r2 = all(slot_ok(c) for c in CASES)
    # R3
    v8 = {}
    for c, r in out.items():
        a = ab(r) or 0
        cp = [s for s in r["samples"] if s["v8"] == a + NEW_VAL]
        og = [s for s in r["samples"] if s["v8"] == a + OLD_VAL]
        v8[c] = {"copy_samples": len(cp), "orig_samples": len(og),
                 "v10_at_copy": sorted({tuple(round(x, 4) for x in s["v10"]) for s in cp}),
                 "v10_at_orig": sorted({tuple(round(x, 4) for x in s["v10"]) for s in og})}
        v8[c]["_cp"] = cp
    near = lambda p, q: all(abs(p[i] - q[i]) <= 1e-4 for i in range(3))   # noqa: E731
    r3 = (all(v8[c]["copy_samples"] >= 3 and v8[c]["orig_samples"] == 0 for c in grown)
          and all(v8[c]["orig_samples"] >= 3 and v8[c]["copy_samples"] == 0 for c in ("base", "nogate"))
          and any(near(s["v10"], W2) for s in v8["mod"]["_cp"]) and not any(near(s["v10"], W) for s in v8["mod"]["_cp"])
          and any(near(s["v10"], W) for s in v8["copy"]["_cp"]))
    for c in v8:
        del v8[c]["_cp"]
    summary = {}
    if not invalid:
        cA2 = closest(A, W2)
        for c in ("copy", "mod", "nogate"):
            f = maxdev(out[c])
            fo = maxdev(out[c], 25)
            summary[c] = {"max_off": round(f[0][0], 3) if f else None,
                          "max_off_dist_to_W": round(math.dist(f[1], W), 2) if f else None,
                          "max_off_toward_W2": (sum((f[1][i] - f[0][1][i]) * (W2[i] - W[i]) for i in range(3)) > 0)
                          if f else None,
                          "max_off_outside_25": round(fo[0][0], 3) if fo else 0.0,
                          "closest_to_W2": round(closest(out[c], W2), 3)}
        summary["base"] = {"closest_to_W2": round(cA2, 3), "closest_to_W": round(closest(A, W), 3),
                           "t_closest_W": t_close}
        r4 = all(summary[c]["max_off"] is not None and summary[c]["max_off"] <= 0.5 and
                 abs(summary[c]["closest_to_W2"] - cA2) <= 0.5 for c in ("copy", "nogate"))
        m = summary["mod"]
        r5 = (m["max_off"] >= 1.5 and m["max_off_dist_to_W"] <= 25 and m["max_off_toward_W2"] is True
              and m["closest_to_W2"] <= cA2 - 1.0 and m["max_off_outside_25"] <= 0.5)
    else:
        r4 = r5 = False

    # R6
    def walk_ok(r):
        st = r["states"]
        i = next((k for k, x in enumerate(st) if "invalid" not in x), None)
        return i is not None and not any("invalid" in x for x in st[i:])
    alloc = {}
    for c, r in out.items():
        used = [s for s in r["states"] if "invalid" not in s and "1" in s.get("areas", {})]
        L = AREA + (N if c in grown else 0)
        alloc[c] = {"length": (r.get("area") or {}).get("length"), "words": (r.get("area") or {}).get("words"),
                    "free_after": used[-1]["free_bytes"] if used else None}
        alloc[c]["ok"] = (walk_ok(r) and alloc[c]["length"] == L and alloc[c]["words"] == bp.words_for(L)
                          and bool(used) and all(s["areas"]["1"]["length"] == L for s in used)
                          and alloc[c]["free_after"] == FREE0 - (N if c in grown else 0))
    r6 = all(a["ok"] for a in alloc.values()) and all(
        r["haptics_policy"] and not any(r["judges"].values()) and r["runner_exit"] == 0 and not r["process_left"]
        for r in out.values())
    checks = {"R1_resource": bool(r1), "R2_relocation": bool(r2), "R3_consumption": bool(r3),
              "R4_identical_copy": bool(r4), "R5_effect": bool(r5), "R6_safety": bool(r6)}
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()), "start": start,
              "summary": summary, "var8": v8, "alloc": alloc, "readback_sha256": shas,
              "live": {c: {k: r.get(k) for k in ("live_first", "live_end")} for c, r in out.items()},
              "grow_size": {c: r["grow_size"] for c, r in out.items()},
              "grow_reads": {c: r["grow_reads"][:3] for c, r in out.items()},
              "tails": {c: len(out[c]["tails"]) for c in grown}, "nogate_refused": D["refused"],
              "judges": {c: r["judges"] for c, r in out.items()},
              "runner_exit": {c: r["runner_exit"] for c, r in out.items()}}
    (ROOT / "private" / "work" / PREFIX / tag / "judgement.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))
    return 0 if result["pass"] else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return check()
    if len(sys.argv) > 2 and sys.argv[1] == "judge":
        return judge(sys.argv[2])
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--cases", default=",".join(CASES))
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", a.tag):
        ap.error("bad tag")
    for case in a.cases.split(","):
        print(json.dumps(run_case(a.tag, case)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
