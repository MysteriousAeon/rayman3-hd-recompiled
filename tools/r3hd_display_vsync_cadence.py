#!/usr/bin/env python3
"""D-220: deterministic cadence model of the Windows display V-Sync pipeline at several display refresh rates.

    python tools/r3hd_display_vsync_cadence.py [--seconds 600] [--phases 16] [--jitter-us 100] [--json OUT]
    python tools/r3hd_display_vsync_cadence.py selftest

A model, not a measurement: it says what the implemented scheduling rules imply for a fixed-refresh display; it
does not observe any display, driver or compositor. Inputs are the measured hidden-run quantities (E-449): guest
frames at exactly 60.000 Hz (M16 deadline vblank) with an independent Gaussian jitter (guest swap core sd about
0.1 ms) and a UI paint/Present cost of about 0.2 ms.

V-Sync On (Present(1, 0), implicit V-Sync, frame-latency object with maximum latency L): every guest frame asks the
UI thread to paint; the UI thread paints the newest finished guest frame as soon as fewer than L presented frames
are waiting for a vertical blank (the latest-frame mailbox drops older ones); a frame submitted by `margin` before a
vertical blank is flipped at it. Reported per refresh rate: displayed and dropped guest frames, repeated refreshes
beyond the even pattern, the hold pattern (refreshes per displayed frame) and guest-ready-to-flip latency.
V-Sync Off (Present(0) with tearing on a fixed-refresh display that is not VRR): a frame appears at once; the share
of flips outside the vertical-blank interval is the share that can show a tear line.
VRR (G-Sync/FreeSync) within range is not modelled: there the display refreshes when a frame arrives.
Rates are typical real modes (119.98, 143.98, 164.98, 239.96, 59.94 Hz): their small offset from a multiple of 60
sweeps the frame/vblank phase slowly, as on real hardware. 60.000 Hz exactly is the phase-locked case: "worst"
there is the worst fixed phase (frames ready within the jitter of a vertical blank), not a time average.
"""
import argparse
import json
import math
import random
import sys

GUEST_HZ = 60.0
PAINT_S = 0.0002


def simulate_on(refresh_hz, seconds, jitter_s, latency, phase, seed, margin_s=0.0003):
    rng = random.Random(seed)
    tg, td = 1.0 / GUEST_HZ, 1.0 / refresh_hz
    n = int(seconds * GUEST_HZ)
    ready = [k * tg + max(-3 * jitter_s, min(3 * jitter_s, rng.gauss(0.0, jitter_s))) for k in range(n)]
    queue = []           # (frame index, submit time) waiting for a vertical blank, oldest first
    shown = []           # (frame index, flip time)
    next_frame = 0       # first guest frame not yet considered by the UI thread
    ui_free = 0.0        # the UI thread is busy until then
    v = phase * td       # next vertical blank
    end = n * tg
    while v < end + 4 * td:
        # The UI thread paints while it may (queue below the latency limit) and a newer frame is ready before v.
        while next_frame < n and len(queue) < latency:
            start = max(ui_free, ready[next_frame])
            if start >= v:
                break
            # newest finished frame at paint start (mailbox: latest wins)
            k = next_frame
            while k + 1 < n and ready[k + 1] <= start:
                k += 1
            submit = start + PAINT_S
            queue.append((k, submit))
            ui_free = submit
            next_frame = k + 1
        # vertical blank: flip the oldest frame submitted early enough
        if queue and queue[0][1] <= v - margin_s:
            if len(queue) >= latency:
                ui_free = max(ui_free, v)  # the UI thread was waiting on the latency object until this flip
            k, _ = queue.pop(0)
            shown.append((k, v))
        v += td
    flips = [t for _, t in shown]
    holds = [round((b - a) / td) for a, b in zip(flips, flips[1:])]
    lat = sorted((t - ready[k]) * 1000.0 for k, t in shown)
    nominal = refresh_hz / GUEST_HZ
    even = {math.floor(nominal), math.ceil(nominal)}
    extra = sum(h - max(even) for h in holds if h > max(even))
    hist = {}
    for h in holds:
        hist[h] = hist.get(h, 0) + 1
    minutes = seconds / 60.0
    return {
        "displayed_per_s": round(len(shown) / seconds, 3),
        "dropped_per_min": round((n - len({k for k, _ in shown})) / minutes, 2),
        "extra_repeat_refreshes_per_min": round(extra / minutes, 2),
        "hold_pattern": {str(k): round(v / max(1, len(holds)), 4) for k, v in sorted(hist.items())},
        "latency_ms_mean": round(sum(lat) / len(lat), 2),
        "latency_ms_p95": round(lat[int(0.95 * (len(lat) - 1))], 2),
        "latency_ms_max": round(lat[-1], 2),
    }


def simulate_off(refresh_hz, seconds, jitter_s, phase, seed, vblank_fraction=0.04):
    rng = random.Random(seed)
    tg, td = 1.0 / GUEST_HZ, 1.0 / refresh_hz
    n = int(seconds * GUEST_HZ)
    torn = 0
    for k in range(n):
        t = k * tg + rng.gauss(0.0, jitter_s) + PAINT_S
        pos = ((t / td) - phase) % 1.0      # scan position of the flip within the refresh
        if pos < 1.0 - vblank_fraction:      # outside the vertical-blank interval
            torn += 1
    return {"tear_capable_flips_share": round(torn / n, 3), "latency_ms_mean": round(PAINT_S * 1000.0, 2)}


def summarize(runs):
    keys = runs[0].keys()
    out = {}
    for k in keys:
        vals = [r[k] for r in runs]
        if isinstance(vals[0], dict):
            out[k] = vals[len(vals) // 2]
        else:
            s = sorted(vals)
            out[k] = {"median": s[len(s) // 2], "worst": s[-1] if "latency" in k or "dropped" in k or "repeat" in k else s[0]}
    return out


def model(seconds, phases, jitter_us, rates=(59.94, 60.0, 60.05, 119.98, 143.98, 164.98, 239.96), latencies=(1, 2)):
    res = {}
    for hz in rates:
        row = {}
        for lat in latencies:
            runs = [simulate_on(hz, seconds, jitter_us / 1e6, lat, (p + 0.5) / phases, seed=p) for p in range(phases)]
            row[f"on_latency{lat}"] = summarize(runs)
        offs = [simulate_off(hz, seconds, jitter_us / 1e6, (p + 0.5) / phases, seed=p) for p in range(phases)]
        row["off"] = summarize(offs)
        res[f"{hz:g}"] = row
    return res


def selftest():
    fails = []
    r = simulate_on(240.0, 60, 0.0001, 1, 0.37, 1)
    if abs(r["displayed_per_s"] - 60.0) > 0.05 or r["dropped_per_min"] > 0 or r["hold_pattern"] != {"4": 1.0}:
        fails.append(f"240 Hz: {r}")
    r = simulate_on(120.0, 60, 0.0001, 1, 0.37, 1)
    if r["hold_pattern"] != {"2": 1.0} or r["latency_ms_max"] > 8.4:
        fails.append(f"120 Hz: {r}")
    r = simulate_on(144.0, 60, 0.0001, 1, 0.37, 1)
    if set(r["hold_pattern"]) != {"2", "3"} or abs(r["hold_pattern"]["2"] - 0.6) > 0.02:
        fails.append(f"144 Hz 2:3 pattern: {r}")
    r = simulate_on(59.94, 120, 0.0001, 1, 0.37, 1)
    if not (0.5 <= r["dropped_per_min"] <= 5.0):
        fails.append(f"59.94 Hz drift drops: {r}")
    o = simulate_off(60.0, 60, 0.0001, 0.37, 1)
    if o["tear_capable_flips_share"] < 0.5:
        fails.append(f"off tear share: {o}")
    print(f"R3HD_DISPLAY_VSYNC_CADENCE_SELFTEST {'PASS' if not fails else 'FAIL'} {fails}")
    return 0 if not fails else 1


def main():
    if sys.argv[1:2] == ["selftest"]:
        return selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=600)
    ap.add_argument("--phases", type=int, default=16)
    ap.add_argument("--jitter-us", type=float, default=100)
    ap.add_argument("--json")
    a = ap.parse_args()
    res = model(a.seconds, a.phases, a.jitter_us)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)
    for hz, row in res.items():
        for mode, s in row.items():
            print(hz, mode, json.dumps(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
