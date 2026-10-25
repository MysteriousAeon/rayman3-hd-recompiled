"""One-shot read-only status of a live hidden run: Rayman, camera and nearby actors.

Opens the process with QUERY_INFORMATION|VM_READ only (m5_live). Prints JSON to
stdout; nothing is written to the guest or to disk.

Usage: python tools/m7_live_status.py RUN_DIR [--level intro_15] [--near 25]
       [--samples 1] [--interval 0.5] [--dsg 13,137,142,169]
PID comes from RUN_DIR/process.json, the host virtual base from the runtime logs.
"""
import argparse
import json
import math
import re
import time
from pathlib import Path

from m5_live import Actor, Process


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--level", default="intro_15")
    parser.add_argument("--near", type=float, default=25.0)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--dsg", default="")
    args = parser.parse_args()

    pid = int(json.loads((args.run / "process.json").read_text(encoding="utf-8-sig"))["pid"])
    base = None
    for path in sorted(args.run.glob("runtime*.log")):
        with path.open(errors="replace") as stream:
            for line in stream:
                match = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", line)
                if match:
                    base = int(match.group(1), 16)
                    break
        if base is not None:
            break
    if base is None:
        raise SystemExit("guest virtual base not found in runtime logs")

    process = Process(pid, base)
    actors = []
    for record in json.loads((args.run / f"actors_{args.level}.json").read_text(encoding="utf-8"))["actors"]:
        try:
            actor = Actor(process, int(record["so"], 16))
        except (TypeError, ValueError, IndexError, OSError):
            continue
        if actor.alive():
            actors.append(actor)
    rayman = next((actor for actor in actors if actor.model == "YLT_RaymanModel"), None)
    camera = next((actor for actor in actors if actor.model == "StdCam"), None)
    if rayman is None:
        print(json.dumps({"pid": pid, "running": process.running(), "rayman": None, "live_actors": len(actors)}))
        return 1
    wanted = [int(item) for item in args.dsg.split(",") if item]
    for index in range(max(1, args.samples)):
        position = rayman.position()
        row = {
            "t": round(time.time(), 3),
            "rayman": [round(value, 3) for value in position],
            "camera": [round(value, 3) for value in camera.position()] if camera else None,
            "comport": rayman.comport(),
            "reflex": rayman.comport(reflex=True),
            "bits": f"{rayman.custom_bits():08X}",
        }
        if wanted:
            dsg = rayman.dsg()
            row["dsg"] = {}
            for number in wanted:
                buffer, offset = dsg[number]
                # Variable offsets are not guaranteed to be ascending; take the
                # distance to the nearest following offset, at most 12 bytes.
                later = [other for _, other in dsg if other > offset]
                end = min(later) if later else len(buffer)
                row["dsg"][str(number)] = buffer[offset:min(end, offset + 12)].hex()
        if index == 0 and args.near > 0:
            near = []
            for actor in actors:
                if actor is rayman or actor is camera:
                    continue
                other = actor.position()
                if other is None or not all(math.isfinite(value) for value in other):
                    continue
                distance = math.dist(position, other)
                if distance <= args.near:
                    near.append({
                        "model": actor.model, "so": f"{actor.so:08X}", "d": round(distance, 1),
                        "pos": [round(value, 1) for value in other], "comport": actor.comport(),
                        "bits": f"{actor.custom_bits():08X}",
                    })
            row["near"] = sorted(near, key=lambda item: item["d"])
        print(json.dumps(row))
        if index + 1 < args.samples:
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
