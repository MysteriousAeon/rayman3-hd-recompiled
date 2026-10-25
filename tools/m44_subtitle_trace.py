#!/usr/bin/env python3
"""M44: gameplay voice-subtitle state from an M17 frame trace (read-only; statistics and line names only).

    python tools/m44_subtitle_trace.py watch TRACE        write TRACE.watch (the subtitle globals below)
    python tools/m44_subtitle_trace.py report TRACE [--json OUT] [--expect-gate]

The title's voice-subtitle state (RE_NOTES "M44"): 828865D0 banner visible, 828865D8 line active, 828865DC line on the
always-show list (8212E260), 828865E0 end time (0 while the voice plays), 82876194 cinematic state (1 on, -1 closing,
0 off; 8210D9B8), 82876150 the Subtitles option, 82837348 the gameplay restriction word (data, 1), 82885FD0 the
current voice name. `report` prints one row per change of these words and, per line, whether it was ever visible and
in which cinematic states. `--expect-gate` checks the rule of 8212F150 on every frame of a playing line:
visible == (restriction == 0 or cinematic != 0 or always-show) (`M44_GATE PASS` / `FAIL`).
No subtitle text is read: the formatted string at 828860D0 is not in the watch list.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m17_frame_trace import frames, write_watch  # noqa: E402

SUB, CINE, OPTION, BANNER, NAME = 0x828865D0, 0x82876194, 0x82876150, 0x82837340, 0x82885FD0
WATCH = [(SUB, 0x1C), (CINE, 4), (OPTION, 4), (BANNER, 0x10), (NAME, 0x20)]


def word(block: bytes, offset: int) -> int:
    return struct.unpack_from(">i", block, offset)[0]


def state(ranges: dict):
    sub, banner = ranges.get(SUB), ranges.get(BANNER)
    if sub is None or banner is None or CINE not in ranges or OPTION not in ranges or NAME not in ranges:
        return None
    name = ranges[NAME].split(b"\0", 1)[0].decode("ascii", "replace")
    return {"visible": word(sub, 0), "active": word(sub, 8), "always": word(sub, 0xC), "end": word(sub, 0x10),
            "cine": word(ranges[CINE], 0), "option": word(ranges[OPTION], 0), "restrict": word(banner, 8),
            "special": word(banner, 0xC), "name": name}


def report(trace: Path, out, expect_gate: bool) -> int:
    rows, lines, previous, first_host = [], {}, None, None
    gate_frames = gate_bad = 0
    for swap, host, _guest, ranges in frames(trace):
        s = state(ranges)
        if s is None:
            continue
        if first_host is None:
            first_host = host
        t = round(host - first_host, 3)
        if s["active"] and s["end"] == 0:  # a playing line: 8212F150 recomputes the flag on this frame
            gate_frames += 1
            want = 1 if (s["restrict"] == 0 or s["cine"] != 0 or s["always"]) else 0
            # the flag is written after the frame's other work: allow the frame on which the inputs changed
            if (s["visible"] != 0) != bool(want) and previous is not None and (
                    previous["cine"] == s["cine"] and previous["name"] == s["name"]):
                gate_bad += 1
        key = (s["visible"], s["active"], s["always"], s["end"] != 0, s["cine"], s["option"], s["name"])
        if previous is None or key != previous["key"]:
            rows.append(dict(s, t=t, swap=swap, end_set=s["end"] != 0))
        if s["active"] and s["name"]:
            info = lines.setdefault(s["name"], {"first_t": t, "visible_frames": 0, "hidden_frames": 0,
                                                "cine_states": set(), "always": s["always"]})
            info["visible_frames" if s["visible"] else "hidden_frames"] += 1
            info["cine_states"].add(s["cine"])
        s["key"] = key
        previous = s
    if first_host is None:
        print("M44_TRACE EMPTY: no complete record")
        return 1
    for r in rows:
        print(f"t={r['t']:9.3f} swap={r['swap']:6d} vis={r['visible']} act={r['active']} always={r['always']} "
              f"ended={int(r['end_set'])} cine={r['cine']:2d} opt={r['option']} restrict={r['restrict']} "
              f"special={r['special']} name={r['name']}")
    print("lines:")
    for name, info in lines.items():
        print(f"  {name:28s} first_t={info['first_t']:9.3f} visible={info['visible_frames']:5d} "
              f"hidden={info['hidden_frames']:5d} cine={sorted(info['cine_states'])} always={info['always']}")
    if out:
        Path(out).write_text(json.dumps({"rows": [{k: v for k, v in r.items() if k != "key"} for r in rows],
                                         "lines": {k: dict(v, cine_states=sorted(v["cine_states"]))
                                                   for k, v in lines.items()},
                                         "gate_frames": gate_frames, "gate_bad": gate_bad}, indent=1))
    print(f"gate frames {gate_frames}, contradicting {gate_bad}")
    if expect_gate:
        ok = gate_frames > 0 and gate_bad == 0
        print(f"M44_GATE {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watch")
    w.add_argument("trace", type=Path)
    r = sub.add_parser("report")
    r.add_argument("trace", type=Path)
    r.add_argument("--json")
    r.add_argument("--expect-gate", action="store_true")
    a = p.parse_args()
    if a.cmd == "watch":
        write_watch(a.trace, WATCH)
        return 0
    return report(a.trace, a.json, a.expect_gate)


if __name__ == "__main__":
    sys.exit(main())
