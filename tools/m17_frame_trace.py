#!/usr/bin/env python3
"""Reader for the M17 per-frame guest trace (tools/m17_frame_trace.h) and the engine-timer summary.

    python tools/m17_frame_trace.py prepare TRACE                 write TRACE.watch with the engine-timer ranges
    python tools/m17_frame_trace.py timer TRACE [--from-frame N] [--json OUT]
    python tools/m17_frame_trace.py check TRACE [--expect deadline|poll] [--from-frame N]

`check` judges the guest-visible timing of a steady 60 Hz stretch (TIMING_CHECK PASS / FAIL): one engine frame
per guest swap, the engine's measured frame time 16 or 17 ms on at least 0.90 of the steps, its simulation step
16 ms on at least 0.94 (an exact 60 Hz vblank gives this title 16 ms on every frame, RE_NOTES "M17"), simulated
time 0.9585..0.9650 of wall time, guest clock equal to host time.
With --expect poll the limits are not applied: the pinned 1 ms polling is being recorded, and it fails them.

A trace is written by the game when R3HD_FRAME_TRACE names a file; `<file>.watch` lists the guest ranges to
record (hex "ADDRESS LENGTH" per line). `TIMER_WATCH` below is the engine timer of RE_NOTES "M17".
Traces are game-derived and stay under private/; this tool prints statistics only.
"""
import argparse
import json
import struct
import sys
import time
from collections import Counter
from pathlib import Path

ENGINE = 0x82C06220
# engine timer block (+0x64 frame number ... +0xD0 ticks per millisecond), the timer-fed word, the averaging
# state (count, index, remainder, system-time divider) and the five-frame window
TIMER_WATCH = [(ENGINE + 0x64, 0x70), (0x82BCE058, 4), (0x82876178, 0x10), (0x82BF7420, 0x14)]


def write_watch(trace: Path, ranges) -> None:
    """Replace the watch list of a trace (atomically, the game may be reading it)."""
    text = "".join(f"{address:08X} {length:X}\n" for address, length in ranges)
    temporary = Path(str(trace) + ".watch.tmp")
    temporary.write_text(text, encoding="ascii")
    for attempt in range(20):  # the game opens the list for a moment every eighth frame
        try:
            temporary.replace(Path(str(trace) + ".watch"))
            return
        except PermissionError:
            time.sleep(0.02)
    raise SystemExit(f"cannot replace {trace}.watch")


def frames(path: Path):
    """Yield (swap, host_seconds, guest_ticks, {address: bytes}) per recorded guest frame."""
    data = Path(path).read_bytes()
    magic, version, frequency = struct.unpack_from("<IIQ", data, 0)
    if magic != 0x54463352 or version != 1:
        raise SystemExit(f"{path}: not an M17 frame trace")
    offset = 16
    while offset + 28 <= len(data):
        mark, swap, count, host, guest = struct.unpack_from("<IIIqQ", data, offset)
        if mark != 0x4D415246:
            raise SystemExit(f"{path}: bad record at {offset}")
        offset += 28
        ranges, complete = {}, True
        for _ in range(count):
            if offset + 8 > len(data):
                complete = False
                break
            address, length = struct.unpack_from("<II", data, offset)
            offset += 8
            if offset + length > len(data):
                complete = False
                break
            ranges[address] = data[offset:offset + length]
            offset += length
        if not complete:
            break
        yield swap, host / frequency, guest, ranges


def timer_fields(ranges):
    """Engine-timer fields of one frame, or None while the watch list was not active."""
    block = ranges.get(ENGINE + 0x64)
    if not block or len(block) < 0x70:
        return None
    frame, _, total_ms, delta_ms = struct.unpack_from(">IIII", block, 0)
    useful_ms, = struct.unpack_from(">I", block, 0x50)
    frame_length, = struct.unpack_from(">f", block, 0x58)
    count_low, count_high = struct.unpack_from(">II", block, 0x5C)
    ticks_per_ms, = struct.unpack_from(">I", block, 0x6C)
    seed = ranges.get(0x82BCE058)
    return {"frame": frame, "total_ms": total_ms, "delta_ms": delta_ms, "useful_ms": useful_ms,
            "frame_length": frame_length, "count": (count_high << 32) | count_low, "ticks_per_ms": ticks_per_ms,
            "seed": struct.unpack(">I", seed)[0] if seed and len(seed) == 4 else None}


def timer_summary(path: Path, first_frame: int = 0, last_frame: int = 1 << 62) -> dict:
    rows = []
    for swap, host, guest, ranges in frames(path):
        fields = timer_fields(ranges)
        if fields and first_frame <= swap < last_frame:
            rows.append((swap, host, guest, fields))
    if len(rows) < 3:
        return {"frames": len(rows)}
    # one engine frame per swap: keep the steps where the engine frame number advanced by one
    steps = [(a, b) for a, b in zip(rows, rows[1:]) if b[3]["frame"] == a[3]["frame"] + 1 and b[0] == a[0] + 1]
    host_ms = [(b[1] - a[1]) * 1000.0 for a, b in steps]
    regular = [(a, b) for (a, b), h in zip(steps, host_ms) if 12.0 <= h <= 21.0]
    if not regular:
        return {"frames": len(rows), "engine_frame_steps": len(steps), "regular_steps": 0}
    delta = Counter(b[3]["delta_ms"] for a, b in regular)
    useful = Counter(b[3]["useful_ms"] for a, b in regular)
    wall = sum((b[1] - a[1]) for a, b in regular) * 1000.0
    guest_ms = sum((b[2] - a[2]) for a, b in regular) / (rows[0][3]["ticks_per_ms"] or 50000)
    sim = sum(b[3]["useful_ms"] for a, b in regular)
    measured = sum(b[3]["delta_ms"] for a, b in regular)
    h = sorted((b[1] - a[1]) * 1000.0 for a, b in regular)
    mean = sum(h) / len(h)
    return {
        "frames": len(rows), "engine_frame_steps": len(steps), "regular_steps": len(regular),
        "swaps_without_engine_frame": sum(1 for a, b in zip(rows, rows[1:]) if b[3]["frame"] == a[3]["frame"]),
        "engine_frames_skipping_swap": sum(1 for a, b in zip(rows, rows[1:]) if b[3]["frame"] > a[3]["frame"] + 1),
        "frame_length_s": rows[-1][3]["frame_length"], "ticks_per_ms": rows[-1][3]["ticks_per_ms"],
        "host_interval_ms": {"mean": round(mean, 4), "sd": round((sum((x - mean) ** 2 for x in h) / len(h)) ** 0.5, 4),
                             "p5": round(h[len(h) * 5 // 100], 3), "p95": round(h[len(h) * 95 // 100], 3)},
        "delta_ms": dict(sorted(delta.items())), "useful_ms": dict(sorted(useful.items())),
        "wall_ms": round(wall, 1), "guest_clock_ms": round(guest_ms, 1), "measured_ms": measured, "simulated_ms": sim,
        "simulated_per_wall": round(sim / wall, 5), "measured_per_wall": round(measured / wall, 5),
        "useful_changes": sum(1 for a, b in regular if a[3]["useful_ms"] != b[3]["useful_ms"]),
    }


# Calibrated on hidden runs (E-93, E-97): deadline delivery gives measured 16..17 ms on 0.94..0.98 of steps, step
# 16 ms on 0.968..0.997, simulated / wall 0.9604..0.9619 (`menu_10`, `wood_11`); the pinned polling 0.76..0.82,
# 0.80..0.87 and 0.970..0.972. The limits lie between the two populations.
LIMITS = {"min_regular_steps": 1200, "min_delta_16_17_share": 0.90, "min_useful_16_share": 0.94,
          "simulated_per_wall": (0.9585, 0.9650), "guest_per_host_tolerance": 2e-4, "max_swaps_without_frame_share": 0.01}


def timing_check(summary: dict) -> list:
    """Reasons why a steady stretch does not have the timing of an exact 60 Hz vblank (empty = pass)."""
    reasons = []
    n = summary.get("regular_steps", 0)
    if n < LIMITS["min_regular_steps"]:
        return [f"only {n} regular 60 Hz steps"]
    delta_ok = sum(c for v, c in summary["delta_ms"].items() if int(v) in (16, 17)) / n
    useful_ok = sum(c for v, c in summary["useful_ms"].items() if int(v) == 16) / n
    if delta_ok < LIMITS["min_delta_16_17_share"]:
        reasons.append(f"measured frame time 16..17 ms in {delta_ok:.4f} of steps")
    if useful_ok < LIMITS["min_useful_16_share"]:
        reasons.append(f"simulation step 16 ms in {useful_ok:.4f} of steps")
    low, high = LIMITS["simulated_per_wall"]
    if not low <= summary["simulated_per_wall"] <= high:
        reasons.append(f"simulated / wall {summary['simulated_per_wall']}")
    if abs(summary["guest_clock_ms"] / summary["wall_ms"] - 1.0) > LIMITS["guest_per_host_tolerance"]:
        reasons.append(f"guest clock / host time {summary['guest_clock_ms'] / summary['wall_ms']:.6f}")
    if summary["swaps_without_engine_frame"] > LIMITS["max_swaps_without_frame_share"] * summary["frames"]:
        reasons.append(f"{summary['swaps_without_engine_frame']} swaps without an engine frame")
    if summary["engine_frames_skipping_swap"]:
        reasons.append(f"{summary['engine_frames_skipping_swap']} engine frames without a swap")
    return reasons


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    pr = sub.add_parser("prepare")
    pr.add_argument("trace", type=Path)
    c = sub.add_parser("check")
    c.add_argument("trace", type=Path)
    c.add_argument("--expect", choices=("deadline", "poll"), default="deadline")
    c.add_argument("--from-frame", type=int, default=0)
    c.add_argument("--to-frame", type=int, default=1 << 62)
    t = sub.add_parser("timer")
    t.add_argument("trace", type=Path)
    t.add_argument("--from-frame", type=int, default=0)
    t.add_argument("--to-frame", type=int, default=1 << 62)
    t.add_argument("--json", type=Path)
    a = ap.parse_args()
    if a.command == "prepare":
        a.trace.parent.mkdir(parents=True, exist_ok=True)
        write_watch(a.trace, TIMER_WATCH)
        print(f"watch written: {a.trace}.watch")
        return 0
    summary = timer_summary(a.trace, a.from_frame, a.to_frame)
    if a.command == "check":
        reasons = timing_check(summary) if summary.get("regular_steps") else ["no engine-timer data in the trace"]
        applied = a.expect == "deadline"
        verdict = "PASS" if (not reasons or not applied) else "FAIL"
        print(json.dumps({"expect": a.expect, "limits_applied": applied, "reasons": reasons, **summary}))
        print(f"TIMING_CHECK {verdict} expect={a.expect} regular_steps={summary.get('regular_steps', 0)} "
              f"useful_ms={summary.get('useful_ms')} simulated_per_wall={summary.get('simulated_per_wall')} "
              f"reasons={reasons}")
        return 0 if verdict == "PASS" else 1
    text = json.dumps(summary, indent=1)
    if a.json:
        a.json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
