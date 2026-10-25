#!/usr/bin/env python3
"""Read-only watcher for combat scenarios in a live hidden run (M14, D-021).

    python tools/m14_combat_watch.py RUN_DIR ACTORS_JSON OUTPUT.jsonl --models A,B [--radius 80]
                                     [--seconds 120] [--interval 0.1]

Follows the player actor and every actor of the named models (optionally only those within --radius of the
player at start) and writes one JSON line whenever an actor's behaviour, reflex, custom bits, standard-game
block or liveness changes, plus the player's position once per second. The standard-game block (StdGame
+0x10..+0x50, where the engine keeps hit points; RE_NOTES "M14") is recorded as hex so a change in hit points
is visible as data, not as an interpretation.

Opens the process with QUERY_INFORMATION | VM_READ only. OUTPUT must be under private/.
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

ROOT = Path(__file__).resolve().parents[1]
PLAYER = "YLT_RaymanModel"


def snapshot(actor: Actor) -> dict:
    std = actor.p.read(actor.std + 0x10, 0x40)
    if std:  # +0x16 / +0x17 are a free-running counter shared by all actors: not state
        std = std[:6] + bytes(2) + std[8:]
    return {"alive": actor.alive(), "comport": actor.comport() if actor.mind else None,
            "reflex": actor.comport(reflex=True) if actor.mind else None,
            "bits": f"{actor.custom_bits():08X}", "std": std.hex() if std else None}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("actors", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--models", default="")
    ap.add_argument("--radius", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--interval", type=float, default=0.1)
    ap.add_argument("--player-dsg", type=Path, help="also record the player's whole designer-variable buffer per sample")
    a = ap.parse_args()
    output = a.output.resolve()
    if (ROOT / "private").resolve() not in output.parents:
        ap.error("OUTPUT must be under private/")
    pid = int(json.loads((a.run / "process.json").read_text(encoding="utf-8-sig"))["pid"])
    base = None
    for path in sorted(a.run.glob("runtime*.log")):
        m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", path.read_text(errors="replace"))
        if m:
            base = int(m.group(1), 16)
            break
    if base is None:
        raise SystemExit("guest virtual base not found in runtime logs")
    process = Process(pid, base)
    wanted = {name for name in a.models.split(",") if name}
    actors = []
    for record in json.loads(a.actors.read_text(encoding="utf-8"))["actors"]:
        try:
            actor = Actor(process, int(record["so"], 16))
        except (TypeError, ValueError, IndexError, OSError):
            continue
        if actor.alive() and (actor.model == PLAYER or actor.model in wanted):
            actors.append(actor)
    player = next((actor for actor in actors if actor.model == PLAYER), None)
    if player is None:
        raise SystemExit("no player actor")
    if a.radius > 0:
        origin = player.position()
        actors = [actor for actor in actors
                  if actor is player or math.dist(actor.position(), origin) <= a.radius]
    previous, start, next_position = {}, time.monotonic(), 0.0
    dsg_stream = a.player_dsg.resolve().open("w", encoding="utf-8") if a.player_dsg else None
    if dsg_stream and (ROOT / "private").resolve() not in a.player_dsg.resolve().parents:
        ap.error("--player-dsg must be under private/")
    with output.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({"watch": [{"perso": f"{x.perso:08X}", "model": x.model} for x in actors],
                                 "pid": pid, "utc": time.time()}) + "\n")
        dsg_offsets_written = False
        while time.monotonic() - start < a.seconds and process.running():
            now = round(time.monotonic() - start, 2)
            for actor in actors:
                try:
                    state = snapshot(actor)
                    position = [round(v, 2) for v in actor.position()]
                except (TypeError, IndexError, OSError, AttributeError):
                    state, position = {"alive": False}, None
                key = f"{actor.perso:08X}"
                if previous.get(key) != state:
                    changed = sorted(k for k in state if previous.get(key, {}).get(k) != state[k])
                    stream.write(json.dumps({"t": now, "perso": key, "model": actor.model, "position": position,
                                             "changed": changed, **state}) + "\n")
                    previous[key] = state
                elif actor is player and now >= next_position:
                    stream.write(json.dumps({"t": now, "perso": key, "model": actor.model, "position": position}) + "\n")
                if actor is player and now >= next_position:
                    next_position = now + 1.0
            if dsg_stream:
                try:
                    dsg = player.dsg()
                    # Offsets go with the first record written (not with t == 0: the first sample can be a
                    # hundredth of a second late, and then no record carried them; seen once in M20).
                    dsg_stream.write(json.dumps({"t": now, "offsets": None if dsg_offsets_written else [off for _, off in dsg],
                                                 "buffer": dsg[0][0].hex()}) + "\n")
                    dsg_offsets_written = True
                except (TypeError, IndexError, OSError, AttributeError):
                    pass
            stream.flush()
            time.sleep(a.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
