#!/usr/bin/env python3
"""E-480 (D-247) G5-P4a: read-only candidate survey for a second structural-mod level.

usage:
  g5p4a_survey.py offline LEVEL...        graph owners, node counts, safety, file identities (no game)
  g5p4a_survey.py live TAG LEVEL...       one unmodified hidden isolated run per level (no plan, no input, no
                                          frames): block-8 snapshots at area changes; at 6 s and 40 s after the level
                                          area appears the actors are discovered and every graph owner's waypoint
                                          (type 19) designer variables and position are sampled every 0.2 s
  g5p4a_survey.py report TAG LEVEL...     which graphs are traversed: each type-19 value mapped to a node of a graph of
                                          the same actor (live address - area base + 4 = file offset)
Outputs stay under private/work/e480/. Nothing is modified; this is the baseline the brief allows before any growth.
"""
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
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))
import r3hd_mods as rm  # noqa: E402
import g3a_ab as g3a  # noqa: E402
import block8_probe as bp  # noqa: E402
import g5p1_pilot as p1  # noqa: E402

WORK = ROOT / "private" / "work" / "e480"
RUNS = g3a.RUNS
SECONDS = 130


def short(model_key):
    return model_key.split("^")[0].split("\\")[-1].replace(".rul", "")


def offline(level):
    ix = rm.read_script_index(p1.GAME, level)
    lp, pp, me = rm.script_level_files(p1.GAME, level)
    out = {"level": level, "lvl": [lp.stat().st_size, rm.sha256_bytes(lp.read_bytes())],
           "ptr": [pp.stat().st_size, rm.sha256_bytes(pp.read_bytes())], "graphs": []}
    for (model, inst, var), e in ix["graphs"].items():
        out["graphs"].append({"model": short(model), "key": model, "instance": inst, "variable": var,
                              "nodes": len(e["nodes"]), "safe": e["safe"] or "safe",
                              "waypoints": [w for _, w in e["nodes"]]})
    return out


def dsg_typed(act):
    p = act.p
    mem = p.words(act.mind[3], 3)
    var = p.words(p.words(mem[0], 1)[0], 4)
    infos = [p.words(var[1] + i * 16, 2) for i in range(var[3] >> 24)]
    buf = p.read(mem[2], var[2])
    return [(off, t, struct.unpack_from(">I", buf, off)[0] if t == 19 and off + 4 <= len(buf) else None)
            for off, t in infos]


def live(tag, level, owners):
    from m5_live import Actor, Process
    run = f"e480_{tag}_{level}"
    work = WORK / tag / level
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_E465_TEST_GROW", "R3HD_G3A_TEST_GROW", rm.STRUCT_ENV):
        env.pop(k, None)
    (work / "steps.txt").write_text(f"wait {SECONDS - 8}\n", encoding="ascii")
    states, samples, discovered = [], [], []
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(SECONDS), "--play", "--test-level", level,
                                 "--user-root", run], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
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
        row = {"level": level, "run": run}
        if base is None or pid is None:
            row["error"] = "process not found"
        else:
            p = Process(pid, int(base, 16))
            last, t_end, area_t, ab, actors, nxt, rounds = "none", t0 + SECONDS - 5, None, None, [], 0.0, [6, 40]
            while time.monotonic() < t_end and p.running():
                ar = bp.areas(p)
                key = json.dumps({k: (v["base"], v["end"]) for k, v in (ar or {}).items()})
                if ar is not None and key != last:
                    last = key
                    s = bp.snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="areas_changed", area_keys=sorted(ar))
                    states.append(s)
                    if ar.get(1) and area_t is None:
                        area_t, ab = time.monotonic(), ar[1]["base"]
                if area_t is not None and rounds and time.monotonic() >= area_t + rounds[0]:
                    rounds.pop(0)
                    disc = work / f"discovery_{len(discovered)}.json"
                    q = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc),
                                        "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
                    found = []
                    for a in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if q.returncode == 0 else []):
                        try:
                            act = Actor(p, int(a["so"], 16))
                        except Exception:
                            continue
                        if act.mind and act.model in owners:
                            found.append(act)
                    discovered.append({"t": round(time.monotonic() - t0, 3),
                                       "actors": [[a.model, hex(a.so)] for a in found]})
                    actors = found
                now = time.monotonic()
                if actors and now >= nxt:
                    row_s = {"t": round(now - t0, 3), "a": []}
                    for a in actors:
                        try:
                            row_s["a"].append([a.model, hex(a.so), [v for _, t, v in dsg_typed(a) if t == 19],
                                               [round(x, 3) for x in (a.position() or ())]])
                        except Exception as x:
                            row_s["a"].append([a.model, hex(a.so), type(x).__name__])
                    samples.append(row_s)
                    nxt = now + 0.2
                time.sleep(0.005)
            row["area_base"] = ab
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and g3a.alive(pid))
    for name, obj in (("states", states), ("samples", samples), ("discovered", discovered), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1, default=str) + "\n")
    return row


def report(tag, level):
    off = offline(level)
    w = WORK / tag / level
    row = json.loads((w / "row.json").read_text())
    samples = json.loads((w / "samples.json").read_text())
    ab = row["area_base"]
    wp = {}
    for g in off["graphs"]:
        for i, o in enumerate(g["waypoints"]):
            if o is not None:
                wp.setdefault(o, []).append((g["model"], g["instance"], g["variable"], i))
    seen = {}
    for s in samples:
        for a in s["a"]:
            if len(a) < 4:
                continue
            for v in a[2]:
                if v and ab and ab <= v:
                    for hit in wp.get(v - ab + 4, []):
                        if hit[0] == a[0]:
                            seen.setdefault((a[0], a[1], hit[1], hit[2]), []).append((s["t"], hit[3]))
    out = {"level": level, "files": [off["lvl"], off["ptr"]], "run": row, "traversed": []}
    for (model, so, inst, var), hits in sorted(seen.items()):
        seq = []
        for t, i in hits:
            if not seq or seq[-1][1] != i:
                seq.append((t, i))
        out["traversed"].append({"model": model, "so": so, "instance": inst, "variable": var,
                                 "distinct_nodes": sorted({i for _, i in hits}), "changes": len(seq) - 1,
                                 "sequence": seq[:80]})
    print(json.dumps(out, indent=1, default=str)[:6000])
    (w / "report.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    return out


def main():
    a = sys.argv[1:]
    if a and a[0] == "offline":
        for lv in a[1:]:
            print(json.dumps(offline(lv), default=str)[:3000])
        return 0
    if len(a) >= 3 and a[0] == "live":
        for lv in a[2:]:
            owners = {g["model"] for g in offline(lv)["graphs"]}
            print(json.dumps(live(a[1], lv, owners), default=str), flush=True)
        return 0
    if len(a) >= 3 and a[0] == "report":
        for lv in a[2:]:
            report(a[1], lv)
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
