#!/usr/bin/env python3
"""Walk the player to one actor in a live hidden run with the left stick (M19; read-only probes, scoped input).

    python tools/m19_walk_to.py RUN_DIR ACTORS_JSON MODEL [--seconds 8] [--stop 1.0] [--log FILE]

Picks the live actor of MODEL nearest to the player and holds the left stick towards it through the run's own
input schedule (the same appended XAM schedule as every hidden run). The stick is camera-relative and the
camera is not read: the first 0.4 s push straight "up" and the measured direction of travel gives the rotation
between stick and world, which is re-estimated at every later sample. It stops when the horizontal distance is
below --stop, when the target is no longer a live actor, or at --seconds, and always releases the stick.
It is one short closed loop to a named actor a few units away, not a route follower (D-041). Nothing is
written to the guest.
"""
import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m5_live import Actor, Process  # noqa: E402

PLAYER = "YLT_RaymanModel"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("actors", type=Path)
    ap.add_argument("model")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--stop", type=float, default=1.0)
    ap.add_argument("--log", type=Path)
    a = ap.parse_args()
    pid = int(json.loads((a.run / "process.json").read_text(encoding="utf-8-sig"))["pid"])
    base = next(int(m.group(1), 16) for p in sorted(a.run.glob("runtime*.log"))
                if (m := re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", p.read_text(errors="replace"))))
    process = Process(pid, base)
    actors = []
    for record in json.loads(a.actors.read_text(encoding="utf-8"))["actors"]:
        try:
            actor = Actor(process, int(record["so"], 16))
        except (TypeError, ValueError, IndexError, OSError):
            continue
        if actor.alive() and actor.model in (PLAYER, a.model):
            actors.append(actor)
    player = next(x for x in actors if x.model == PLAYER)
    start = player.position()
    target = min((x for x in actors if x.model == a.model), key=lambda x: math.dist(x.position(), start))
    schedule, events = a.run / "schedule.txt", []

    def stick(x: float, y: float) -> None:
        with schedule.open("a", encoding="ascii", newline="") as stream:
            stream.write(f"0 300 {int(32767 * x)}\n0 301 {int(32767 * y)}\n")

    def note(**item) -> None:
        events.append({"t": round(time.monotonic() - t0, 2), **item})

    t0, rotation, result = time.monotonic(), None, "timeout"
    angle = math.pi / 2  # stick angle: straight up
    try:
        while time.monotonic() - t0 < a.seconds:
            if not target.alive():
                result = "target_gone"
                break
            here, there = player.position(), target.position()
            dx, dy = there[0] - here[0], there[1] - here[1]
            distance = math.hypot(dx, dy)
            if distance < a.stop:
                result = "reached"
                break
            if rotation is not None:
                angle = math.atan2(dy, dx) - rotation
            stick(math.cos(angle), math.sin(angle))
            time.sleep(0.4 if rotation is None else 0.15)
            after = player.position()
            mx, my = after[0] - here[0], after[1] - here[1]
            if math.hypot(mx, my) > 0.3:  # world heading minus stick angle
                rotation = math.atan2(my, mx) - angle
            note(distance=round(distance, 2), stick_deg=round(math.degrees(angle), 1),
                 rotation_deg=None if rotation is None else round(math.degrees(rotation), 1),
                 player=[round(v, 2) for v in after])
    finally:
        stick(0, 0)
    end = player.position()
    summary = {"model": a.model, "target_perso": f"{target.perso:08X}", "result": result, "seconds": round(time.monotonic() - t0, 2),
               "start": [round(v, 2) for v in start], "end": [round(v, 2) for v in end],
               "target": [round(v, 2) for v in target.position()] if target.alive() else None, "events": events}
    if a.log:
        a.log.write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(f"M19_WALK {result} model={a.model} seconds={summary['seconds']}")
    return 0 if result in ("reached", "target_gone") else 1


if __name__ == "__main__":
    raise SystemExit(main())
