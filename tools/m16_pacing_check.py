#!/usr/bin/env python3
"""M16 (D-043): mechanical frame-pacing check of one run from its log.

usage: m16_pacing_check.py RUN_DIR|runtime.log [--expect deadline|poll] [--max-swap-sd-us 250]
                           [--max-present-sd-us 350] [--max-late-p95-us 200] [--json OUT]

Reads the `M16 vblank` lines (lateness of the guest vblank against its schedule, one per 600 vblanks) and the
`M11 pacing` lines (interval statistics of guest swaps and host presents, one per 600; M16 added core_sd_us and
lag1_milli). The quantity checked is the regularity of 60 Hz frames, not the frame rate: windows whose median
interval is not a 60 Hz frame (movies at 30 Hz, loading, an overlay repainting at the display rate) and windows
with fewer than 570 regular intervals (a level change inside the window) are left out and counted.

PASS (mode deadline) needs: the vblank mode is the expected one; the median over vblank windows of late_p95_us is
at most --max-late-p95-us; the median over steady guest_swap windows of core_sd_us is at most --max-swap-sd-us;
the same for host_present with --max-present-sd-us; at least two steady windows per series.
With --expect poll the limits are not applied (the pinned behaviour is being measured); the figures are printed.
Final line: PACING_CHECK PASS|FAIL ...; exit code 0 / 1 (2 = no usable data).

A hidden run measures frame production and the present call. What a display shows is outside its reach.
"""
import argparse
import json
import re
import statistics
import sys
from pathlib import Path

VBLANK = re.compile(r"M16 vblank mode=(\w+) window=(\d+) n=(\d+) late_mean_us=(\d+) late_p50_us=(\d+) "
                    r"late_p95_us=(\d+) late_p99_us=(\d+) late_max_us=(\d+) spin_us=(\d+)")
PACING = re.compile(r"M11 pacing series=(\w+) window=(\d+) n=(\d+) mean_us=(\d+) min_us=(\d+) p50_us=(\d+) "
                    r"p95_us=(\d+) p99_us=(\d+) max_us=(\d+) over_20ms=(\d+) over_33ms=(\d+) over_50ms=(\d+) "
                    r"over_100ms=(\d+) core_n=(\d+) core_sd_us=(\d+) lag1_milli=(-?\d+)")
CP_WAIT = re.compile(r"M16 cp_wait mode=(\w+) sleeps=(\d+) wait_ms=(\d+) memory=(\w+) address=([0-9A-F]{8})")


def analyse(text: str) -> dict:
    vblank = [m.groups() for m in VBLANK.finditer(text)]
    modes = sorted({v[0] for v in vblank})
    series = {}
    for m in PACING.finditer(text):
        name = m.group(1)
        row = {"window": int(m.group(2)), "p50_us": int(m.group(6)), "p95_us": int(m.group(7)),
               "core_n": int(m.group(14)), "core_sd_us": int(m.group(15)), "lag1_milli": int(m.group(16))}
        row["steady"] = 16000 <= row["p50_us"] <= 17400 and row["core_n"] >= 570
        series.setdefault(name, []).append(row)
    out = {"vblank_modes": modes, "vblank_windows": len(vblank), "series": {}}
    if vblank:
        out["late_p95_us_median"] = statistics.median(int(v[5]) for v in vblank)
        out["late_p99_us_median"] = statistics.median(int(v[6]) for v in vblank)
        out["late_max_us"] = max(int(v[7]) for v in vblank)
        out["late_mean_us_median"] = statistics.median(int(v[3]) for v in vblank)
    for name, rows in series.items():
        steady = [r for r in rows if r["steady"]]
        entry = {"windows": len(rows), "steady_windows": len(steady)}
        if steady:
            entry["core_sd_us_median"] = statistics.median(r["core_sd_us"] for r in steady)
            entry["core_sd_us_max"] = max(r["core_sd_us"] for r in steady)
            entry["p95_minus_p50_us_median"] = statistics.median(r["p95_us"] - r["p50_us"] for r in steady)
            entry["lag1_milli_median"] = statistics.median(r["lag1_milli"] for r in steady)
        out["series"][name] = entry
    waits = [m.groups() for m in CP_WAIT.finditer(text)]
    if waits:
        out["cp_wait"] = {"mode": waits[-1][0], "count_logged": int(waits[-1][1]), "wait_ms": int(waits[-1][2]),
                          "memory": waits[-1][3], "address": waits[-1][4]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--expect", choices=("deadline", "poll"), default="deadline")
    ap.add_argument("--max-swap-sd-us", type=int, default=250)
    ap.add_argument("--max-present-sd-us", type=int, default=350)
    ap.add_argument("--max-late-p95-us", type=int, default=200)
    ap.add_argument("--json")
    a = ap.parse_args()
    path = Path(a.run)
    if path.is_dir():
        path = path / "runtime.log"
    if not path.is_file():
        print(f"PACING_CHECK FAIL no log: {path}")
        return 2
    facts = analyse(path.read_text(encoding="utf-8", errors="replace"))
    reasons = []
    swap = facts["series"].get("guest_swap", {})
    present = facts["series"].get("host_present", {})
    if not facts["vblank_windows"]:
        reasons.append("no M16 vblank line")
    elif facts["vblank_modes"] != [a.expect]:
        reasons.append(f"vblank mode {facts['vblank_modes']} != {a.expect}")
    for name, entry in (("guest_swap", swap), ("host_present", present)):
        if entry.get("steady_windows", 0) < 2:
            reasons.append(f"{name}: fewer than two steady 60 Hz windows")
    if a.expect == "deadline" and not reasons:
        if facts["late_p95_us_median"] > a.max_late_p95_us:
            reasons.append(f"vblank late_p95 median {facts['late_p95_us_median']} us > {a.max_late_p95_us}")
        if swap["core_sd_us_median"] > a.max_swap_sd_us:
            reasons.append(f"guest_swap core sd median {swap['core_sd_us_median']} us > {a.max_swap_sd_us}")
        if present["core_sd_us_median"] > a.max_present_sd_us:
            reasons.append(f"host_present core sd median {present['core_sd_us_median']} us > {a.max_present_sd_us}")
    facts["expect"] = a.expect
    facts["reasons"] = reasons
    if a.json:
        Path(a.json).write_text(json.dumps(facts, indent=1) + "\n", encoding="utf-8")
    no_data = any(r.startswith("no M16") or "fewer than two" in r for r in reasons)
    summary = (f"mode={','.join(facts['vblank_modes']) or '-'} late_p95_us={facts.get('late_p95_us_median', '-')} "
               f"late_max_us={facts.get('late_max_us', '-')} "
               f"swap_sd_us={swap.get('core_sd_us_median', '-')} swap_p95-p50_us={swap.get('p95_minus_p50_us_median', '-')} "
               f"present_sd_us={present.get('core_sd_us_median', '-')} "
               f"steady={swap.get('steady_windows', 0)}/{swap.get('windows', 0)}")
    if reasons:
        print(f"PACING_CHECK FAIL {summary} :: {'; '.join(reasons)}")
        return 2 if no_data else 1
    print(f"PACING_CHECK PASS {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
