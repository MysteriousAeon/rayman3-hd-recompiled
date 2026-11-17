#!/usr/bin/env python3
"""E-465a (D-232): read-only census of engine memory block 8 (level areas) in hidden runs.

Layout (static, D-232; checked by the walk below before any number is trusted):
- module byte 82837E3C; block table pointer 82C692E0[module]; block 8 descriptor = table + 8 * 16 =
  {start, end (inclusive), free-list head, highest used address}. Block 8 is created at start-up (82100550 ->
  821894D8 -> 82235920, flags 12: free-list mode, alignment 4; one CRT malloc of 0x1800000 bytes).
- free chunk = {u32 size in words, u32 next (0 ends)}; allocated chunk = {u32 size in words} + data; an allocation
  of L bytes takes ceil(L / 4) + 1 words (82235EB0, first fit; the allocated part is the start of the chosen chunk,
  the rest stays free right after it).
- level areas: base 82C5FE80[area], end 82C60280[area] (base + length - 4 of the file), cross-file save table
  82C5F6A0[area] = {pointer, count}; areas 0 fix, 1 level, 2 / 3 transit.
Validity of a snapshot: the free list stays inside the block, 4-aligned, strictly ascending and non-overlapping; a
walk of chunk sizes from start tiles the block exactly to end + 1; every free-list chunk is a tile; every loaded
area's header (base - 4) is an allocated tile of ceil(length / 4) + 1 words. Snapshots that fail are torn reads or
a wrong model and are not used (three attempts each).

PRE-REGISTERED CAPACITY GATE (fixed before the first E-465a run; N = 4096 bytes, the E-465b extension):
  G1 model: in every run, at least one valid snapshot after intro_10's area appears, and every used snapshot valid.
  G2 identity: intro_10's area length = 7,661,832 (file length - 4); its chunk = 1,915,459 words.
  G3 margin: in each baseline run, the free bytes in the run of free tiles that starts right after intro_10's chunk
     >= 4 x (N + intro_10.ptr length 209,068 + cross-file table 495 x 8) = 868,496 bytes.
  G4 reproducible: both baseline runs give intro_10 the same area base and pass G3.
  G5 temporary buffer (SUPPORTED level): the transition run reaches intro_15, whose 8,474,200-byte pre-read buffer
     (CRT heap) exceeds intro_10 + N (7,665,932).
  Recorded but not gating: free bytes, largest free chunk, chunk counts at each captured state; whether intro_10's
  chunk is free after the transition to intro_15.
REVISION after run a1 (recorded in E-465; applies to fresh runs only, a1 stays FAIL under G1 / G3 as written):
  a1 passed G2, G4, G5 and safety and failed G1 and G3. Causes: (a) G1: each run's first snapshot (t about 1.4 s)
  was taken before block 8 existed (descriptor not yet readable, recorded as invalid "read"); every snapshot after
  the block existed was valid (walk exact, 4 allocated / 1 free chunk at intro_10). (b) G3: wrong layout
  prediction: the level's cross-file save table (495 x 8 bytes, allocated by the same loader right after the area)
  is the chunk right after intro_10's area, so the free run directly after the area is 0; the block's only free
  chunk (13,088,528 bytes) follows the save table. Revised criteria:
  G1r: snapshots before the block-8 descriptor is readable are excluded (recorded as pre-creation); every other
     snapshot valid; at least one valid snapshot with intro_10's area.
  G3r: in each baseline run the chunk after intro_10's area is its save table (header = save - 4, 991 words for
     495 entries) and the free run right after the save table >= 868,496 bytes (same bound as G3).
  G2, G4, G5, safety unchanged.
Cases (m9_license_run.py: hidden, muted, no physical pad, private test profile, --test-level intro_10, no input, no
captures): base1, base2 (no mod, 60 s), trans (E-460 mod: generator variable 5 = 6, which exits the loop to intro_15
about 62 s after intro_10 opens; 140 s).

usage: block8_probe.py TAG [--cases base1,base2,trans]
       block8_probe.py judge TAG
Outputs stay under private/work/e465/.
"""
import argparse
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

GAME = ROOT / "private" / "extracted" / "5841123F"
RUNS = ROOT / "private" / "work" / "m6_runs"
PREFIX = "e465"
MODULE_BYTE, BLOCK_TABLE, BLOCK = 0x82837E3C, 0x82C692E0, 8
AREA_BASE, AREA_END, AREA_SAVE = 0x82C5FE80, 0x82C60280, 0x82C5F6A0
CAPACITY = 0x1800000
N = 4096
INTRO10_AREA, INTRO10_PTR, INTRO10_M = 7661832, 209068, 495
INTRO15_FILE = 8474200
CASES = {"base1": 60, "base2": 60, "trans": 140}


def words_for(length):
    return (length + 3) // 4 + 1


def descriptor(p):
    module = p.read(MODULE_BYTE, 1)
    if not module:
        return None
    table = p.words(BLOCK_TABLE + 4 * module[0], 1)
    if not table or not table[0]:
        return None
    d = p.words(table[0] + BLOCK * 16, 4)
    return {"module": module[0], "table": table[0], "start": d[0], "end": d[1], "free": d[2], "top": d[3]} if d else None


def areas(p):
    b, e, s = p.words(AREA_BASE, 5), p.words(AREA_END, 5), p.words(AREA_SAVE, 10)
    if not (b and e and s):
        return None
    return {i: {"base": b[i], "end": e[i], "save": s[2 * i], "count": s[2 * i + 1]} for i in range(5) if b[i]}


def walk(d, blob, ar):
    """Validate and summarise one snapshot; returns (ok, why, summary)."""
    start, end = d["start"], d["end"]
    if end - start + 1 != CAPACITY or start % 4:
        return False, "descriptor", None
    word = lambda a: struct.unpack_from(">I", blob, a - start)[0]  # noqa: E731
    free, a, last = {}, d["free"], start - 1
    while a:
        if not (start <= a <= end - 7) or a % 4 or a <= last or len(free) > 200000:
            return False, "free_list", None
        w = word(a)
        if w < 2 or a + 4 * w > end + 1:
            return False, "free_size", None
        free[a] = w
        last = a + 4 * w - 1
        a = word(a + 4)
    tiles, a = [], start
    while a <= end:
        w = word(a)
        if w < 1 or a + 4 * w > end + 1 or len(tiles) > 2000000:
            return False, "tiling", None
        tiles.append((a, w, a in free))
        a += 4 * w
    if a != end + 1 or sum(1 for t in tiles if t[2]) != len(free):
        return False, "tiling_end", None
    index = {t[0]: i for i, t in enumerate(tiles)}
    out = {"tiles": len(tiles), "allocated_chunks": len(tiles) - len(free), "free_chunks": len(free),
           "free_bytes": 4 * sum(free.values()), "largest_free": 4 * max(free.values(), default=0),
           "allocated_bytes": CAPACITY - 4 * sum(free.values()), "areas": {}}
    for k, v in (ar or {}).items():
        h = v["base"] - 4
        i = index.get(h)
        length = v["end"] - v["base"]
        if i is None or tiles[i][2] or tiles[i][1] != words_for(length):
            return False, f"area{k}", None
        run, j = 0, i + 1
        while j < len(tiles) and tiles[j][2]:
            run += 4 * tiles[j][1]
            j += 1
        out["areas"][k] = {"base": hex(v["base"]), "length": length, "words": tiles[i][1],
                           "save": hex(v["save"]), "count": v["count"], "free_after": run,
                           "next_allocated": hex(tiles[j][0]) if j < len(tiles) else None}
        si = index.get(v["save"] - 4) if v["save"] else None
        if si is not None and not tiles[si][2]:
            srun, sj = 0, si + 1
            while sj < len(tiles) and tiles[sj][2]:
                srun += 4 * tiles[sj][1]
                sj += 1
            out["areas"][k].update(save_words=tiles[si][1], save_adjacent=(si == i + 1), free_after_save=srun)
    return True, "", out


def snapshot(p):
    why = "read"
    for _ in range(3):
        d, ar = descriptor(p), areas(p)
        if not d or ar is None:
            continue
        blob = p.read(d["start"], CAPACITY)
        if blob is None or areas(p) != ar or descriptor(p) != d:
            why = "changed"
            continue
        ok, why, s = walk(d, blob, ar)
        if ok:
            s["descriptor"] = {k: (hex(v) if k != "module" else v) for k, v in d.items()}
            return s
    return {"invalid": why}


def alive(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in r.stdout


def run_case(tag, case):
    from m5_live import Process
    work = ROOT / "private" / "work" / PREFIX / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    seconds = CASES[case]
    row = {"case": case, "run": run, "seconds": seconds}
    if case == "trans":
        import dsgvar_ab as d
        tpl = d.role()[0]
        src = work / "mod_src"
        src.mkdir()
        rm = d.rm
        (src / "mod.json").write_text(json.dumps({
            "format": 1, "id": f"{PREFIX}.lums-6", "name": f"{PREFIX} test", "version": "1.0.0",
            "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids({"home": None}),
                       "min_port_version": "0.0.1"}, "overrides": [{**tpl, "value": 6}]}), encoding="utf-8")
        d.mods(work, "import", str(src), "--enable")
        env["R3HD_MODS_PLAN"] = row["plan"] = d.mods(work, "plan")["plan"]
    (work / "steps.txt").write_text(f"wait {seconds - 8}\n", encoding="ascii")
    states = []
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(seconds), "--play", "--test-level",
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
            last, t_end, first_desc = "none", t0 + seconds - 5, None
            while time.monotonic() < t_end and p.running():
                ar = areas(p)
                d = descriptor(p)
                if d and d["start"] and first_desc is None:
                    first_desc = time.monotonic() - t0
                    s = snapshot(p)
                    s.update(t=round(first_desc, 3), state="block_created", area_keys=sorted((ar or {}).keys()))
                    states.append(s)
                key = json.dumps({k: (v["base"], v["end"]) for k, v in (ar or {}).items()})
                if ar is not None and key != last:
                    last = key
                    s = snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="areas_changed",
                             area_keys=sorted(ar.keys()))
                    states.append(s)
                time.sleep(0.005)
            if p.running():
                s = snapshot(p)
                s.update(t=round(time.monotonic() - t0, 3), state="final", area_keys=sorted((areas(p) or {}).keys()))
                states.append(s)
        game.wait(timeout=seconds + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and alive(pid))
    (work / "states.json").write_text(json.dumps(states, indent=1) + "\n")
    (work / "row.json").write_text(json.dumps(row, indent=1) + "\n")
    return row


def judge(tag):
    out = {}
    for case in CASES:
        work = ROOT / "private" / "work" / PREFIX / tag / case
        run = f"{PREFIX}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        states = json.loads((work / "states.json").read_text())
        log = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / run).glob("runtime*.log")))
        opens = re.findall(r"vfs_open path=(\S+?\.lvl) result=00000000", log)
        row["lvl_opens"] = [o.rsplit("\\", 1)[-1] for o in opens]
        row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
        judges = {}
        for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
            r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True,
                               text=True)
            judges[tool] = r.returncode
            (work / f"{tool}.log").write_text(r.stdout + r.stderr)
        row["judges"] = judges
        valid = [s for s in states if "invalid" not in s]
        row["snapshots"] = len(states)
        row["invalid_snapshots"] = [s["invalid"] for s in states if "invalid" in s]
        created = next((s["t"] for s in states if s.get("state") == "block_created"), None)
        row["pre_creation"] = [s["invalid"] for s in states if "invalid" in s and created and s["t"] < created]
        row["invalid_after_creation"] = [s["invalid"] for s in states
                                         if "invalid" in s and not (created and s["t"] < created)]
        lvl = [s for s in valid if "1" in s["areas"] and s["areas"]["1"]["length"] == INTRO10_AREA]
        row["intro10_states"] = len(lvl)
        if lvl:
            a = lvl[0]["areas"]["1"]
            row["intro10"] = {"base": a["base"], "words": a["words"], "free_after_first": a["free_after"],
                              "free_after_min": min(s["areas"]["1"]["free_after"] for s in lvl),
                              "save_words": a.get("save_words"), "save_adjacent": a.get("save_adjacent"),
                              "free_after_save": a.get("free_after_save")}
        i15 = [s for s in valid if "1" in s["areas"] and s["areas"]["1"]["length"] == INTRO15_FILE - 4]
        row["intro15_loaded"] = bool(i15)
        if i15 and lvl:
            old = int(lvl[0]["areas"]["1"]["base"], 16) - 4
            row["intro15"] = {"base": i15[0]["areas"]["1"]["base"], "free_bytes": i15[0]["free_bytes"],
                              "largest_free": i15[0]["largest_free"], "free_after": i15[0]["areas"]["1"]["free_after"],
                              "intro10_base_reused_or_free": old}
        row["table"] = [{k: s.get(k) for k in ("t", "state", "area_keys", "free_bytes", "largest_free",
                                                "allocated_chunks", "free_chunks", "invalid")} |
                        {"areas": {k: (v["base"], v["length"], v["free_after"]) for k, v in s.get("areas", {}).items()}}
                        for s in states]
        out[case] = row
    need = 4 * (N + INTRO10_PTR + 8 * INTRO10_M)
    b1, b2, tr = out["base1"], out["base2"], out["trans"]
    checks = {
        "G1_model": all(r["intro10_states"] >= 1 and not r["invalid_snapshots"] for r in out.values()),
        "G2_identity": all(r.get("intro10", {}).get("words") == words_for(INTRO10_AREA) for r in out.values()),
        "G3_margin": all(r.get("intro10", {}).get("free_after_first", 0) >= need for r in (b1, b2)),
        "G4_reproducible": b1.get("intro10", {}).get("base") == b2.get("intro10", {}).get("base") is not None,
        "G5_tempbuffer": tr["intro15_loaded"],
        "G1r_model": all(r["intro10_states"] >= 1 and not r["invalid_after_creation"] for r in out.values()),
        "G3r_margin": all(r.get("intro10", {}).get("save_adjacent") is True and
                          r["intro10"].get("save_words") == words_for(8 * INTRO10_M) and
                          (r["intro10"].get("free_after_save") or 0) >= need for r in (b1, b2)),
        "safety": all(r["haptics_policy"] and not any(r["judges"].values()) and not r["process_left"]
                      and r["runner_exit"] == 0 for r in out.values()),
    }
    original = ("G1_model", "G2_identity", "G3_margin", "G4_reproducible", "G5_tempbuffer", "safety")
    revised = ("G1r_model", "G2_identity", "G3r_margin", "G4_reproducible", "G5_tempbuffer", "safety")
    result = {"need_G3": need, "checks": checks, "cases": out,
              "pass_original": all(checks[k] for k in original),  # a1 is judged by this
              "pass": all(checks[k] for k in (original if tag == "a1" else revised))}
    (ROOT / "private" / "work" / PREFIX / tag / "judgement.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({"checks": checks, "pass_original": result["pass_original"], "pass": result["pass"]}, indent=1))
    return 0 if result["pass"] else 1


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
