#!/usr/bin/env python3
"""Frame-exact trace of the `menu_10` sniper fight in both vblank timings (M17, read-only).

    python tools/m17_combat_trace.py run RUN --mode poll|deadline [--seconds 75] [--extra-env NAME=VALUE ...]
                                         [--layout-from EARLIER_RUN]
    python tools/m17_combat_trace.py analyze RUN... [--json OUT]

`run` starts one hidden isolated `menu_10` run without input (tools/m14_scenario.py) with the per-frame guest
trace on (tools/m17_frame_trace.h, R3HD_FRAME_TRACE) and, once the actors are known, lists for it the engine
timer, the player, the three hoodlums and the first always-actor slots (the hoodlums' projectiles live there).
`analyze` turns a trace into a shot / hit timeline in engine frames and prints statistics only. Nothing is
written to the guest; the trace and the timeline are game-derived and stay under private/work/m17.

Layouts used (RE_NOTES "M17"): engine timer at 82C06220 +0x64; always-actor slots: SuperObject array at
4113969C and Perso array at 4113AA9C (0x80 apiece, 40 slots), per-slot block of 0x7F0 bytes at 4113C594
(matrix +0, StdGame +0x19C, Mind +0x20C, Intelligence +0x220, designer variables +0x384). These are `menu_10`
addresses; the tool checks the reciprocal links per frame and reports a slot whose layout does not match.
"""
import argparse
import json
import math
import os
import re
import struct
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m17_frame_trace as ft  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "private" / "work" / "m6_runs"
WORK = ROOT / "private" / "work" / "m17"
SCAN = ROOT / "private" / "work" / "m14" / "scan"
LEVEL = "menu_10"
PLAYER, HOODLUM, PROJECTILE = "YLT_RaymanModel", "YAM_M_CagouSnipeBase", "YAM_CagProjectile"
SLOT_SO, SLOT_PERSO, SLOT_BLOCK, SLOT_STEP, SLOTS = 0x4113969C, 0x4113AA9C, 0x4113C594, 0x7F0, 12
SLOT_STD, SLOT_INTELLIGENCE, SLOT_DSG, SLOT_BYTES = 0x19C, 0x220, 0x384, 0x3B0


def behaviour_names(level: str) -> dict:
    """Behaviour address -> short name, from the M14 script scan of the level (private)."""
    names = {}
    for path in (SCAN / level / "scripts").glob("*.txt"):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"## (?:normal|reflex) ([0-9A-Fa-f]{8}) .*:([A-Za-z0-9_]+)$", line)
            if m:
                names[int(m.group(1), 16)] = m.group(2)
    return names


def actor_ranges(process, actor) -> dict:
    """Guest ranges that describe one ordinary actor (addresses are fixed for the actor's life)."""
    ranges = {"so": (actor.so, 0x24), "matrix": (actor.matrix, 0x40), "std": (actor.std, 0x50)}
    if actor.mind:
        if actor.mind[1]:
            ranges["normal"] = (actor.mind[1], 0x10)
        if actor.mind[2]:
            ranges["reflex"] = (actor.mind[2], 0x10)
        mem = process.words(actor.mind[3], 3) if actor.mind[3] else None
        var = process.words(process.words(mem[0], 1)[0], 4) if mem and mem[0] else None
        if var and mem[2] and 0 < var[2] <= ft_max():
            ranges["dsg"] = (mem[2], var[2])
    return ranges


def ft_max() -> int:
    return 0x1000


def run(a) -> int:
    from m5_live import Actor, Process
    run_dir = RUNS / a.run
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.run) or run_dir.exists():
        raise SystemExit("invalid or existing RUN")
    WORK.mkdir(parents=True, exist_ok=True)
    trace = WORK / f"{a.run}.trace"
    seed = list(ft.TIMER_WATCH)
    if a.layout_from:
        # Actor addresses repeat from run to run of the same level, so an earlier run's layout can be watched
        # from the first frame (ranges that are not mapped yet are recorded as empty).
        earlier = json.loads((WORK / f"{a.layout_from}.layout.json").read_text(encoding="utf-8"))
        for actor in earlier["actors"]:
            seed += [tuple(v) for v in actor["ranges"].values()]
        seed += [(SLOT_SO, SLOTS * 0x80), (SLOT_PERSO, SLOTS * 0x80)]
        seed += [(SLOT_BLOCK + i * SLOT_STEP, SLOT_BYTES) for i in range(SLOTS)]
    ft.write_watch(trace, seed)
    env = dict(os.environ, R3HD_VBLANK=a.mode, R3HD_FRAME_TRACE=str(trace))
    for item in a.extra_env:
        name, _, value = item.partition("=")
        env[name] = value
    steps = WORK / "idle.txt"
    steps.write_text(f"# M17: no input.\nwait {a.seconds - 8}\n", encoding="ascii")
    with (WORK / f"{a.run}.scenario.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(ROOT / "tools" / "m14_scenario.py"), a.run, LEVEL, str(steps),
                                 "--seconds", str(a.seconds), "--settle", "2", "--watch", HOODLUM],
                                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        layout = {"run": a.run, "mode": a.mode, "extra_env": a.extra_env, "actors": [], "watch_written": False}
        actors_file = run_dir / f"actors_{LEVEL}.json"
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and game.poll() is None and not actors_file.is_file():
            time.sleep(0.2)
        if actors_file.is_file():
            time.sleep(0.3)
            pid = json.loads((run_dir / "process.json").read_text(encoding="utf-8-sig"))["pid"]
            base = int(re.search(r"virtual base 0x0*([0-9A-Fa-f]+),",
                                 (run_dir / "runtime.log").read_text(errors="replace")).group(1), 16)
            process = Process(pid, base)
            ranges = list(ft.TIMER_WATCH)
            for record in json.loads(actors_file.read_text(encoding="utf-8"))["actors"]:
                try:
                    actor = Actor(process, int(record["so"], 16))
                except (TypeError, ValueError, IndexError, OSError):
                    continue
                if actor.model in (PLAYER, HOODLUM) and actor.alive():
                    described = actor_ranges(process, actor)
                    layout["actors"].append({"model": actor.model, "perso": actor.perso,
                                             "ranges": {k: list(v) for k, v in described.items()}})
                    ranges += described.values()
            ranges += [(SLOT_SO, SLOTS * 0x80), (SLOT_PERSO, SLOTS * 0x80)]
            ranges += [(SLOT_BLOCK + i * SLOT_STEP, SLOT_BYTES) for i in range(SLOTS)]
            ft.write_watch(trace, ranges)
            layout["watch_written"] = True
        (WORK / f"{a.run}.layout.json").write_text(json.dumps(layout, indent=1) + "\n", encoding="utf-8")
        code = game.wait()
    print(f"M17_COMBAT_TRACE run={a.run} mode={a.mode} scenario_exit={code} watch={layout['watch_written']} "
          f"trace_bytes={trace.stat().st_size if trace.is_file() else 0}")
    return 0 if layout["watch_written"] else 1


def be(fmt, data, offset=0):
    return struct.unpack_from(">" + fmt, data, offset)


def analyze_one(name: str) -> dict:
    layout = json.loads((WORK / f"{name}.layout.json").read_text(encoding="utf-8"))
    names = behaviour_names(LEVEL)
    player = next(x for x in layout["actors"] if x["model"] == PLAYER)
    hoodlums = [x for x in layout["actors"] if x["model"] == HOODLUM]
    hoodlum_persos = {x["perso"] for x in hoodlums}

    def behaviour(ranges, actor, which="normal"):
        r = actor["ranges"].get(which)
        data = ranges.get(r[0]) if r else None
        return names.get(be("I", data, 8)[0], f"{be('I', data, 8)[0]:08X}") if data and len(data) >= 12 else None

    def position(ranges, actor):
        data = ranges.get(actor["ranges"]["matrix"][0])
        return be("3f", data, 0x34) if data and len(data) >= 0x40 else None

    events, shots, live, anomalies = [], [], {}, Counter()
    stand_positions, player_stand = {}, None
    previous = {}
    rows = 0
    first = last = None
    timer_rows = []
    for swap, host, guest, ranges in ft.frames(WORK / f"{name}.trace"):
        timer = ft.timer_fields(ranges)
        if timer is None or SLOT_SO not in ranges or not ranges[SLOT_SO]:
            continue
        rows += 1
        first = first if first is not None else (swap, host, timer)
        last = (swap, host, timer)
        timer_rows.append((swap, host, timer["frame"], timer["total_ms"], timer["delta_ms"], timer["useful_ms"]))
        player_position = position(ranges, player)
        for actor in [player] + hoodlums:
            key = actor["perso"]
            state = (behaviour(ranges, actor), behaviour(ranges, actor, "reflex"))
            if actor is not player and state[0] and state[0].endswith("3SnipeTir") and key not in stand_positions                     and player_position and position(ranges, actor):
                stand_positions[key] = [round(v, 3) for v in position(ranges, actor)]
                player_stand = [round(v, 3) for v in player_position]
            if previous.get(key) != state:
                events.append({"swap": swap, "frame": timer["frame"], "ms": timer["total_ms"],
                               "who": "player" if actor is player else f"hoodlum:{key:08X}",
                               "behaviour": state[0], "reflex": state[1]})
                previous[key] = state
        so_array, perso_array = ranges[SLOT_SO], ranges.get(SLOT_PERSO) or b""
        for i in range(SLOTS):
            block = ranges.get(SLOT_BLOCK + i * SLOT_STEP)
            so = SLOT_SO + i * 0x80
            perso = SLOT_PERSO + i * 0x80
            so_type, so_perso = be("II", so_array, i * 0x80)
            alive = False
            if block and len(block) == SLOT_BYTES and len(perso_array) >= (i + 1) * 0x80:
                std, _, brain = be("III", perso_array, i * 0x80 + 4)
                std_so, = be("I", block, SLOT_STD + 0xC)
                alive = so_type == 2 and so_perso == perso and std == SLOT_BLOCK + i * SLOT_STEP + SLOT_STD \
                    and std_so == so
                if so_type == 2 and so_perso == perso and std and not alive:
                    anomalies["slot_layout"] += 1
            current = names.get(be("I", block, SLOT_INTELLIGENCE + 8)[0]) if alive else None
            shot = live.get(i)
            key = None
            if alive and current and "CagProjectile" in current:
                dsg = block[SLOT_DSG:SLOT_DSG + 0x2C]
                direction, wall_point = be("3f", dsg, 0), be("3f", dsg, 12)
                speed, = be("f", dsg, 24)
                start_ms, other, owner, life_ms = be("IIII", dsg, 28)
                here = be("3f", block, 0x34)
                # a slot is reused within one frame: a new start time or owner is a new projectile
                key = (start_ms, owner) if current.endswith("1Avance") else ("init", swap if shot is None else shot["spawn_swap"])
            if shot is not None and (key is None or (shot["key"] != key and shot["key"][0] != "init")):
                shot.update(end_swap=swap, end_frame=timer["frame"], end_ms=timer["total_ms"])
                shots.append(live.pop(i))
                shot = None
            if key is not None:
                if shot is None:
                    shot = live[i] = {"slot": i, "spawn_swap": swap, "spawn_frame": timer["frame"],
                                      "spawn_ms": timer["total_ms"], "spawn_position": here, "owner": None,
                                      "min_distance": None, "frames": 0, "direction": None, "speed": None,
                                      "life_ms": None, "start_ms": None, "path": [], "useful": Counter()}
                shot["key"] = key
                shot["frames"] += 1
                shot["useful"][timer["useful_ms"]] += 1
                if key[0] != "init":
                    shot.update(direction=direction, speed=speed, life_ms=life_ms, start_ms=start_ms,
                                owner=owner, other=other, wall_point=wall_point)
                shot["last_ms"] = timer["total_ms"]
                shot["path"].append(here)
                if player_position:
                    d = math.dist(here, player_position)
                    if shot["min_distance"] is None or d < shot["min_distance"]:
                        shot["min_distance"] = d
                        shot["closest_offset"] = tuple(h - p for h, p in zip(here, player_position))
    hits = [e for e in events if e["who"] == "player" and e["behaviour"] and "Paf" in e["behaviour"]]
    deaths = [e for e in hits if "Mort" in e["behaviour"]]
    hit_swaps = [e["swap"] for e in hits]
    for shot in shots:
        flight_ms = shot["end_ms"] - (shot["start_ms"] or shot["spawn_ms"])
        shot["flight_ms"] = flight_ms
        del shot["key"]
        shot["expired"] = shot["life_ms"] is not None and flight_ms >= shot["life_ms"]
        # the projectile's own collide branch zeroes the Z of its direction variable before it delivers the hit
        shot["hit"] = bool(shot["direction"]) and shot["direction"][2] == 0.0 and shot["frames"] > 2
        shot["near_player_hit"] = any(-2 <= s - shot["end_swap"] <= 3 for s in hit_swaps)
        step = [math.dist(p, q) for p, q in zip(shot["path"], shot["path"][1:])]
        shot["step_mean"] = sum(step) / len(step) if step else None
        shot["travel"] = math.dist(shot["path"][0], shot["path"][-1]) if shot["path"] else None
        del shot["path"]
        shot["useful"] = dict(shot["useful"])
    wall = (last[1] - first[1]) if rows else 0.0
    sim_ms = (last[2]["total_ms"] - first[2]["total_ms"]) if rows else 0
    useful = Counter(r[5] for r in timer_rows)
    fired = [e for e in events if e["who"].startswith("hoodlum") and e["behaviour"] and e["behaviour"].endswith("SnipeTir")]
    first_death_swap = deaths[0]["swap"] if deaths else None
    until = first_death_swap if first_death_swap is not None else (last[0] if rows else 0)
    window_shots = [s for s in shots if s["spawn_swap"] <= until]
    stands = {}
    for e in events:
        if e["who"].startswith("hoodlum") and e["reflex"] and e["reflex"].endswith("3Fight") and e["who"] not in stands:
            stands[e["who"]] = {"fight_swap": e["swap"], "fight_frame": e["frame"], "fight_ms": e["ms"]}
    per_hoodlum = {}
    for actor in hoodlums:
        who = f"hoodlum:{actor['perso']:08X}"
        mine = [s for s in window_shots if s["owner"] == actor["ranges"]["so"][0] and s["life_ms"] is not None]
        lives = sorted(s["life_ms"] for s in mine)
        per_hoodlum[who] = dict(stands.get(who, {}), stand=stand_positions.get(actor["perso"]),
                                shots=len(mine), hits=sum(1 for s in mine if s["hit"]),
                                life_ms_median=lives[len(lives) // 2] if lives else None,
                                miss_distance_median=(sorted(s["min_distance"] for s in mine)[len(mine) // 2]
                                                      if mine else None))
    summary = {
        "run": name, "mode": layout["mode"], "extra_env": layout.get("extra_env", []), "frames": rows,
        "wall_s": round(wall, 2), "engine_ms": sim_ms,
        "useful_ms": dict(sorted(useful.items())),
        "hoodlum_fire_behaviours": len(fired), "shots": len(shots), "shots_before_death": len(window_shots),
        "shots_hit": sum(1 for s in window_shots if s["hit"]),
        "shots_expired": sum(1 for s in window_shots if s["expired"]),
        "shots_other_end": sum(1 for s in window_shots if not s["hit"] and not s["expired"]),
        "player_hits": len(hits), "player_death_swap": first_death_swap,
        "frames_to_death": (first_death_swap - first[0]) if first_death_swap is not None else None,
        "player_stand": player_stand, "hoodlums": per_hoodlum,
        "anomalies": dict(anomalies),
    }
    return {"summary": summary, "events": events, "shots": shots}


def analyze(a) -> int:
    out = []
    for name in a.runs:
        result = analyze_one(name)
        (WORK / f"{name}.timeline.json").write_text(json.dumps(result, indent=0) + "\n", encoding="utf-8")
        out.append(result["summary"])
        print(json.dumps(result["summary"]))
    if a.json:
        a.json.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("run")
    r.add_argument("--mode", choices=("poll", "deadline"), required=True)
    r.add_argument("--seconds", type=int, default=75)
    r.add_argument("--extra-env", action="append", default=[])
    r.add_argument("--layout-from", help="earlier RUN whose actor layout is watched from the first frame")
    r.set_defaults(func=run)
    z = sub.add_parser("analyze")
    z.add_argument("runs", nargs="+")
    z.add_argument("--json", type=Path)
    z.set_defaults(func=analyze)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
