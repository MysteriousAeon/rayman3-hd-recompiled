#!/usr/bin/env python3
"""E-465b (D-233): intro_10.lvl presented with a 4,096-byte inert tail, hidden and read-only. Test-only build.

PROTOCOL (committed before the first E-465b run; criteria not changed after results)
Prerequisite: E-465a capacity gate PASS (tag a1; block8_probe.py judge a1).
File: intro_10.lvl, host length 7,661,836, FNV-1a 64 7982c1135516c2b6 (checked here and by the plan), SHA-256 a37638bf...19e2ee
(checked here). Extension N = 4,096 bytes: pattern = for i in 0..255: b"E465TAIL" + i (u32 BE) + 4 bytes 0xA5
(16 bytes each). Plan (written here, not by r3hd_mods.py): one mod, file intro_10.lvl, `grow 0 7665932`, one range
[0, 7,665,932) whose game-bytes hash is the whole original file and whose bytes are the original + the tail; no
gameplay record (inert). Build: the private test build with e465_test_grow_patch.py applied (gate env
R3HD_E465_TEST_GROW=intro_10.lvl); reverted and rebuilt after the runs.
Expected: host-visible length 7,665,932; guest area length 7,665,928 (was 7,661,832; delta 4,096); chunk words
1,916,483 (was 1,915,459); area base 0x40F5509C as in E-465a unless the layout before it differs (then T3 still
needs a valid walk and no overlap); tail at [base + 7,661,832, base + 7,665,928).
Cases (m9_license_run.py hidden, muted, no physical pad, private profile, --test-level intro_10, no input, no
captures, 100 s): base (no plan), grow (plan + gate env), nogate (same plan, gate env unset).
Observation: block-8 snapshots (block8_probe.snapshot) at each area change and at the end; the tail read back from
guest memory every 1 s from its first appearance; generator position every 0.1 s for 60 s after discovery.
Criteria:
  T1 size: grow log has exactly one `M36 grow size file=intro_10.lvl host_size=7661836 guest_size=7665932` line
     and no M36 grow line for any other file; nogate has none (plan refused, `grow_not_allowed` in its log).
  T2 reads: grow serves intro_10.lvl only (`M33 mods served` lines name only intro_10.lvl), its `M36 grow read`
     lines show kind=tail with served = length requested up to 7,665,932, and the guest area's first 7,661,832
     bytes equal the file's bytes 4.. (SHA-256 of a read-back) in the first valid snapshot after the load.
  T3 allocation: valid walk (block8_probe rules) in every grow snapshot after the first valid one (earlier ones
     precede block 8, as in E-465a); area length 7,665,928, chunk 1,916,483
     words, no free tile overlapping it; base / end tables consistent; block free bytes after the load =
     13,084,432 (E-465a's 13,088,528 - 4,096) and base (control) 13,088,528.
  T4 integrity: the tail read back equals the pattern at its first read and at every read for 60 s.
  T5 gameplay: grow and nogate generator samples (after the latest first sample of the three runs + 0.5 s) within
     0.5 units of base's sampled path (the E-464 W4r tolerance; no-mod noise 0.15 recorded for reference); the
     same .lvl opens as base and no intro_15 open.
  T6 safety: haptics policy line, M21 / M22 / M23 judges 0, runner exit 0, no game process left; the test build
     reverted (status production) and rebuilt after the runs.
Invalid (rerun with a new tag, not judged): level not opened, generator not found, fewer than 50 s of samples, no
valid snapshot after the level load, or the file's hashes differ from the protocol.
Negative controls: base (no plan) and nogate (gate off: plan refused as a whole, original level).
REVISION after run b1 (recorded in E-465; applies to fresh runs only, b1 stays FAIL under T2 as written):
  b1 passed T1, T3, T4, T5, T6 and failed T2. Cause: invalid criterion: the guest area is the file after relocation
  (`.ptr` slots hold addresses, not file offsets) and after the level's start-up writes, so it can never equal the
  file's bytes 4.., in any case (base read back 09cb398a..., not the file's). The three b1 read-backs of the first
  7,661,832 bytes, taken at the area's first appearance, were identical across base / grow / nogate. Revised:
  T2r: grow serves intro_10.lvl only, its M36 grow read lines are kind=tail (served up to 7,665,932), and the SHA-256
     of grow's read-back of the area's first 7,661,832 bytes equals base's and nogate's (same base address, so the
     same relocation): the original bytes reach the guest unchanged. T1, T3-T6 unchanged.

usage: e465b_tail.py TAG [--cases base,grow,nogate] | e465b_tail.py judge TAG
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
LVL = GAME / "GAMEDATAbin" / "intro_10" / "intro_10.lvl"
RUNS = ROOT / "private" / "work" / "m6_runs"
PREFIX = "e465b"
SIZE, N = 7661836, 4096
ORIG_FNV = "7982c1135516c2b6"
ORIG_SHA = "a37638bf1370357db21f33df5c4d37ae806b3c4b9f81b331503ba62d1b19e2ee"
EXPECT_BASE = "0x40f5509c"
AREA = SIZE - 4
SECONDS, WATCH = 100, 60
CASES = ("base", "grow", "nogate")
TAIL = b"".join(b"E465TAIL" + struct.pack(">I", i) + b"\xA5" * 4 for i in range(256))
assert len(TAIL) == N


def fnv(b):
    h = 0xCBF29CE484222325
    for x in b:
        h = ((h ^ x) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def file_check():
    data = LVL.read_bytes()
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != ORIG_SHA:
        raise SystemExit("file check: intro_10.lvl is not the protocol's file")
    return data


def write_plan(work, data):
    blob = work / "tail_range.bin"
    new = data + TAIL
    blob.write_bytes(new)
    plan = work / "plan.txt"
    plan.write_text("R3HD_MOD_PLAN 1\n# E-465b test-only plan (e465b_tail.py)\nmod e465.inert-tail 1.0.0\n"
                    f"file {SIZE} {LVL}\ngrow 0 {SIZE + N}\n"
                    f"range 0 0 {SIZE + N} {ORIG_FNV} {fnv(new):016x} e465.inert-tail {blob}\nend 1 1\n",
                    encoding="utf-8")
    return plan


def alive(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in r.stdout


def run_case(tag, case):
    from m5_live import Actor, Process
    data = file_check()
    work = ROOT / "private" / "work" / PREFIX / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    env.pop("R3HD_E465_TEST_GROW", None)
    row = {"case": case, "run": run}
    if case in ("grow", "nogate"):
        env["R3HD_MODS_PLAN"] = row["plan"] = str(write_plan(work, data))
    if case == "grow":
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
            area = None
            last, deadline = None, t0 + 45
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
                        blob = p.read(int(a1["base"], 16), AREA)
                        row["original_readback_sha256"] = hashlib.sha256(blob).hexdigest() if blob else None
                time.sleep(0.005)
            if area is None:
                row["error"] = "level area not seen"
            else:
                row["area"] = area
                tail_at = int(area["base"], 16) + AREA
                disc = work / "discovery.json"
                q = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc),
                                    "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
                gen = None
                for a in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if q.returncode == 0 else []):
                    try:
                        act = Actor(p, int(a["so"], 16))
                    except Exception:
                        continue
                    if act.model == "NIN_m_GenFlyIntro_10" and act.mind:
                        gen = act
                        break
                if gen is None:
                    row["error"] = "generator not found"
                t_end, next_tail = time.monotonic() + WATCH, 0.0
                while time.monotonic() < t_end and p.running():
                    now = time.monotonic()
                    if area["length"] == AREA + N and now >= next_tail:
                        b = p.read(tail_at, N)
                        tails.append({"t": round(now - t0, 3), "equal": b == TAIL,
                                      "sha256": hashlib.sha256(b).hexdigest() if b else None})
                        next_tail = now + 1.0
                    if gen is not None:
                        try:
                            samples.append({"t": round(now - t0, 3), "pos": gen.position()})
                        except Exception as x:
                            row["sampling_stopped"] = type(x).__name__
                            gen = None
                    time.sleep(0.1)
                if p.running():
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
    return math.dist(p, [a[i] + t * ab[i] for i in range(3)])


def judge(tag):
    data = file_check()
    want_orig = hashlib.sha256(data[4:]).hexdigest()
    out = {}
    for case in CASES:
        work = ROOT / "private" / "work" / PREFIX / tag / case
        run = f"{PREFIX}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        row["states_list"] = json.loads((work / "states.json").read_text())
        row["tails"] = json.loads((work / "tails.json").read_text())
        row["samples"] = json.loads((work / "samples.json").read_text())
        log = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / run).glob("runtime*.log")))
        row["grow_size"] = re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)
        row["grow_reads"] = re.findall(r"M36 grow read file=(\S+) offset=(\d+) length=(\d+) host=(\d+) served=(\d+)"
                                       r" kind=(\S+)", log)
        row["served_files"] = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
        row["refused"] = "grow_not_allowed" in log
        row["lvl_opens"] = [o.rsplit("\\", 1)[-1].lower() for o in
                            re.findall(r"vfs_open path=(\S+?\.lvl) result=00000000", log)]
        row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
        judges = {}
        for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
            r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True,
                               text=True)
            judges[tool] = r.returncode
            (work / f"{tool}.log").write_text(r.stdout + r.stderr)
        row["judges"] = judges
        out[case] = row
    b, g, n = out["base"], out["grow"], out["nogate"]
    invalid = [c for c, r in out.items() if r.get("error") or len(r["samples"]) < 500 or
               not any("invalid" not in s and 1 in [int(k) for k in s.get("areas", {})] for s in r["states_list"])]
    start = max(r["samples"][0]["t"] for r in out.values() if r["samples"]) + 0.5 if not invalid else 0
    path = [s["pos"] for s in b["samples"] if s["t"] >= start - 1.0]

    def dev(r):
        pts = [s["pos"] for s in r["samples"] if s["t"] >= start]
        return max((min(seg(q, a, c) for a, c in zip(path, path[1:])) for q in pts), default=None) if path else None

    ga = g.get("area", {})
    used = [s for s in g["states_list"] if "invalid" not in s and "1" in s.get("areas", {})]
    checks = {
        "T1_size": g["grow_size"] == [("intro_10.lvl", str(SIZE), str(SIZE + N))] and not n["grow_size"]
        and n["refused"] and not b["grow_size"],
        "T2_reads": g["served_files"] == ["intro_10.lvl"] and bool(g["grow_reads"]) and
        all(x[0] == "intro_10.lvl" and x[5] == "tail" for x in g["grow_reads"]) and
        (g.get("original_readback_sha256") == want_orig if tag == "b1" else
         g.get("original_readback_sha256") is not None and
         g["original_readback_sha256"] == b.get("original_readback_sha256") == n.get("original_readback_sha256")),
        "T3_allocation": ga.get("length") == AREA + N and ga.get("words") == bp.words_for(AREA + N) and
        bool(used) and all(s["areas"]["1"]["length"] == AREA + N for s in used) and
        not any("invalid" in s for s in g["states_list"][next((i for i, x in enumerate(g["states_list"])
                                                              if "invalid" not in x), 0):]) and
        used[-1]["free_bytes"] == 13088528 - N and
        any("1" in s.get("areas", {}) and s["free_bytes"] == 13088528 for s in b["states_list"]),
        "T4_integrity": len(g["tails"]) >= 55 and all(t["equal"] for t in g["tails"]) and
        g["tails"][-1]["t"] - g["tails"][0]["t"] >= 55,
        "T5_gameplay": not invalid and all(d is not None and d <= 0.5 for d in (dev(g), dev(n))) and
        all(r["lvl_opens"] == b["lvl_opens"] and "intro_15.lvl" not in r["lvl_opens"] for r in (g, n)),
        "T6_safety": all(r["haptics_policy"] and not any(r["judges"].values()) and r["runner_exit"] == 0 and
                         not r["process_left"] for r in out.values()),
    }
    summary = {"invalid": invalid, "start": start, "dev_grow": dev(g) if not invalid else None,
               "dev_nogate": dev(n) if not invalid else None, "checks": checks,
               "pass": not invalid and all(checks.values()),
               "areas": {c: r.get("area") for c, r in out.items()},
               "grow_size": g["grow_size"], "grow_reads": g["grow_reads"][:4], "served": g["served_files"],
               "tails": [len(g["tails"]), g["tails"][:1], g["tails"][-1:]],
               "nogate_refused": n["refused"], "lvl_opens": {c: r["lvl_opens"] for c, r in out.items()},
               "judges": {c: r["judges"] for c, r in out.items()}}
    (ROOT / "private" / "work" / PREFIX / tag / "judgement.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0 if summary["pass"] else 1


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "judge":
        return judge(sys.argv[2])
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--cases", default=",".join(CASES))
    a = ap.parse_args()
    for case in a.cases.split(","):
        print(json.dumps(run_case(a.tag, case)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
