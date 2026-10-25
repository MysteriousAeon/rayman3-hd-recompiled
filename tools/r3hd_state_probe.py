#!/usr/bin/env python3
"""DualSense guest-state probe (D-102): which guest words tell pause, lock-on and the player actor, from one hidden
isolated run. Read-only: ReadProcessMemory only, no guest write, no physical device, scheduled XAM input only.

    python tools/r3hd_state_probe.py run RUN LEVEL [--seconds 120]
    python tools/r3hd_state_probe.py analyze RUN

run: the level opens (D-040 entry); 8 s later this tool starts sampling the image's data range 82830000..82CB0000
(word diffs, 5 Hz), the player's behaviour and designer variable 2, and drives through the run's own schedule:
R2 held 3 s, Start (pause) 6 s, A (Resume Game), R2 held 2 s, Start 10 s, A, idle. Every press is time-stamped.
It also lists every data-range word that holds the player's SuperObject or Perso address at the start.
analyze: words whose value during both pauses differs from every sample outside them, and words that hold a value
only while R2 is held; the player behaviour names seen per phase. Output under private/work/r3hd_probe (game-derived
evidence: addresses, values and behaviour names only).
"""
import argparse
import json
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
OUT = ROOT / "private" / "work" / "r3hd_probe"
LO, HI = 0x82830000, 0x82CB0000
START, A_BUTTON, RT = 40, 44, 8
PLAN = [  # (seconds after sampling starts, phase name, code, value)
    (5.0, "r2_1", RT, 1), (8.0, "play", RT, 0),
    (12.0, "pause_1", START, 1), (12.15, None, START, 0), (18.0, "resume_1", A_BUTTON, 1), (18.15, None, A_BUTTON, 0),
    (24.0, "r2_2", RT, 1), (26.0, "play", RT, 0),
    (30.0, "pause_2", START, 1), (30.15, None, START, 0), (40.0, "resume_2", A_BUTTON, 1), (40.15, None, A_BUTTON, 0),
    (48.0, "end", None, None),
]


def find_player(p: live.Process, actors_json: Path):
    for x in json.loads(actors_json.read_text(encoding="utf-8"))["actors"]:
        try:
            a = live.Actor(p, int(x["so"], 16))
        except (TypeError, IndexError):
            continue
        if a.model == "YLT_RaymanModel":
            return a
    return None


def cmd_run(a) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rec = {"run": a.run, "level": a.level, "events": [], "samples": [], "holders": {}}

    def beside(run_dir: Path, game, log) -> list:
        if not m19.wait_for_log(run_dir, f"{a.level}\\{a.level}.lvl result=00000000", game, 90):
            return [f"{a.level} did not open"]
        time.sleep(8)
        pid, base = m19.attach(run_dir)
        actors = run_dir / f"actors_{a.level}.json"
        subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(actors), "--regions"],
                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        p = live.Process(pid, int(base, 16))
        player = find_player(p, actors)
        if player is None:
            return ["no YLT_RaymanModel actor"]
        rec["player"] = {"so": f"{player.so:08X}", "perso": f"{player.perso:08X}"}
        data = p.read(LO, HI - LO)
        for i, (w,) in enumerate(struct.iter_unpack(">I", data)):
            if w in (player.so, player.perso):
                rec["holders"][f"{LO + i * 4:08X}"] = "so" if w == player.so else "perso"
        prev = list(struct.unpack(f">{(HI - LO) // 4}I", data))
        rec["base_sha"] = __import__("hashlib").sha256(data).hexdigest()
        t0 = time.monotonic()
        stop = threading.Event()

        def sample():
            nonlocal prev
            while not stop.is_set():
                t = round(time.monotonic() - t0, 2)
                d = p.read(LO, HI - LO)
                if d is None:
                    break
                cur = struct.unpack(f">{(HI - LO) // 4}I", d)
                diff = {i: v for i, (v, o) in enumerate(zip(cur, prev)) if v != o}
                prev = list(cur)
                dsg = None
                try:
                    dsg = struct.unpack_from(">I", player.dsg()[2][0], player.dsg()[2][1])[0]
                except (TypeError, IndexError, struct.error):
                    pass
                rec["samples"].append({"t": t, "diff": diff, "comport": player.comport(), "var2": dsg})
                time.sleep(0.2)

        th = threading.Thread(target=sample, daemon=True)
        th.start()
        schedule = run_dir / "schedule.txt"
        for when, phase, code, value in PLAN:
            time.sleep(max(0.0, when - (time.monotonic() - t0)))
            if code is not None:
                with schedule.open("a", encoding="ascii", newline="") as s:
                    s.write(f"0 {code} {value}\n")
            rec["events"].append({"t": round(time.monotonic() - t0, 2), "phase": phase, "code": code, "value": value})
        stop.set()
        th.join(timeout=10)
        return []

    env = dict(e.split("=", 1) for e in a.env)
    reasons = m19.hidden_run(a.run, ROOT / "config" / "m14" / "idle110.txt", a.seconds, test_level=a.level,
                             beside=beside, env=env)
    out = OUT / f"{a.run}.json"
    out.write_text(json.dumps(rec), encoding="utf-8")
    print("R3HD_STATE_PROBE", json.dumps({"run": a.run, "samples": len(rec["samples"]), "holders": rec["holders"],
                                          "player": rec.get("player"), "reasons": reasons}))
    return 1 if reasons else 0


def phases(rec):
    """[(t0, t1, name)] from the recorded events."""
    ev = [e for e in rec["events"] if e["phase"]]
    return [(e["t"], ev[i + 1]["t"] if i + 1 < len(ev) else 1e9, e["phase"]) for i, e in enumerate(ev)]


def cmd_analyze(a) -> int:
    rec = json.loads((OUT / f"{a.run}.json").read_text(encoding="utf-8"))
    ph = phases(rec)

    def phase_at(t):
        for t0, t1, n in ph:
            if t0 <= t < t1:
                return n
        return "before"
    # reconstruct per-word value series only for words that change at all
    values, series = {}, {}
    for s in rec["samples"]:
        for i, v in s["diff"].items():
            series.setdefault(int(i), []).append((s["t"], v))
    first_t = rec["samples"][0]["t"] if rec["samples"] else 0
    margin = 0.6   # the title reacts within a few frames; samples this close to an edge are ignored

    def value_at(seq, t):
        cur = None
        for tt, v in seq:
            if tt <= t:
                cur = v
            else:
                break
        return cur
    times = [s["t"] for s in rec["samples"]]
    cand_pause, cand_r2 = [], []
    for i, seq in series.items():
        inside_p, outside_p, inside_r, outside_r = set(), set(), set(), set()
        for t in times:
            near = any(abs(t - e["t"]) < margin for e in rec["events"] if e["phase"])
            if near:
                continue
            v = value_at(seq, t)
            if v is None:
                continue
            n = phase_at(t)
            (inside_p if n.startswith("pause") else outside_p).add(v)
            (inside_r if n.startswith("r2") else outside_r).add(v)
        if inside_p and outside_p and not (inside_p & outside_p) and len(inside_p) == 1:
            cand_pause.append((f"{LO + i * 4:08X}", sorted(inside_p), sorted(outside_p)[:4], len(outside_p)))
        if inside_r and outside_r and not (inside_r & outside_r) and len(inside_r) == 1:
            cand_r2.append((f"{LO + i * 4:08X}", sorted(inside_r), sorted(outside_r)[:4], len(outside_r)))
    comports = {}
    for s in rec["samples"]:
        comports.setdefault(phase_at(s["t"]), set()).add(s["comport"])
    res = {"run": a.run, "player": rec.get("player"), "holders": rec["holders"], "phases": ph,
           "pause_words": cand_pause[:40], "pause_word_count": len(cand_pause),
           "r2_words": cand_r2[:40], "r2_word_count": len(cand_r2),
           "comport_by_phase": {k: sorted(x for x in v if x) for k, v in comports.items()},
           "var2": sorted({s["var2"] for s in rec["samples"] if s["var2"] is not None})}
    (OUT / f"{a.run}.analysis.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1)[:6000])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("run")
    p.add_argument("level")
    p.add_argument("--seconds", type=int, default=110)
    p.add_argument("--env", action="append", default=[], help="NAME=VALUE for the game (e.g. R3HD_DS_LIGHT=on)")
    p = sub.add_parser("analyze")
    p.add_argument("run")
    a = ap.parse_args()
    return cmd_run(a) if a.cmd == "run" else cmd_analyze(a)


if __name__ == "__main__":
    sys.exit(main())
