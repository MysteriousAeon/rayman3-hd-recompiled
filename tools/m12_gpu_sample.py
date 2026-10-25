#!/usr/bin/env python3
"""Whole-adapter GPU state beside a hidden run: utilisation together with clock, power state and power draw (M12).

    python tools/m12_gpu_sample.py RUN [--baseline 15] [--after 10]

Start it BEFORE the hidden run. It records `nvidia-smi` once per second: first for --baseline seconds with no
game (the desktop's own load), then while private/work/m6_runs/RUN's process lives, then --after seconds more.
Writes private/work/m6_runs/RUN/gpu_adapter.json when the run directory exists at the end.

Why: the Windows per-process "GPU Engine" counter (tools/m11_perf_sample.py) is the share of time the engine was
busy at whatever clock and power state the adapter had chosen. 30 % busy at half clock in a low power state is
not 30 % of the card. This sampler records those states so the two can be read together. It is adapter-wide
(every process on the desktop contributes), hence the baseline. NVIDIA adapters only; read-only.
"""
import argparse
import ctypes
import json
import re
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["utilization.gpu", "utilization.memory", "clocks.current.graphics", "clocks.max.graphics", "power.draw",
          "power.limit", "pstate", "memory.used", "temperature.gpu"]
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]


def query():
    done = subprocess.run(["nvidia-smi", f"--query-gpu={','.join(FIELDS)}", "--format=csv,noheader,nounits", "-i", "0"],
                          capture_output=True, text=True, timeout=10, creationflags=0x08000000)
    cells = [cell.strip() for cell in done.stdout.strip().split(",")]
    if done.returncode != 0 or len(cells) != len(FIELDS):
        return None
    out = {}
    for name, cell in zip(FIELDS, cells):
        if name == "pstate":
            out[name] = cell
        else:
            try:
                out[name] = float(cell)
            except ValueError:
                out[name] = None
    return out


def alive(handle) -> bool:
    code = wintypes.DWORD()
    k32.GetExitCodeProcess(handle, ctypes.byref(code))
    return code.value == 259


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--baseline", type=float, default=15.0)
    ap.add_argument("--after", type=float, default=10.0)
    ap.add_argument("--wait", type=float, default=180.0, help="seconds to wait for the run to start after the baseline")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.run):
        ap.error("invalid run name")
    run_dir = ROOT / "private" / "work" / "m6_runs" / a.run
    info_path = run_dir / "process.json"
    if info_path.exists():
        print("start the sampler before the run", file=sys.stderr)
        return 2
    if query() is None:
        print("nvidia-smi query failed", file=sys.stderr)
        return 2
    samples, phase, handle, pid = [], "baseline", None, None
    started = time.monotonic()
    phase_end = started + a.baseline
    while True:
        now = time.monotonic()
        if phase == "baseline" and now >= phase_end:
            phase, phase_end = "waiting", now + a.wait
        if phase in ("baseline", "waiting") and info_path.exists():
            if phase == "baseline":
                print("warning: the run started during the baseline", file=sys.stderr)
            time.sleep(0.2)
            pid = int(json.loads(info_path.read_text(encoding="utf-8-sig"))["pid"])
            handle = wintypes.HANDLE(k32.OpenProcess(0x1000 | 0x100000, False, pid))
            phase = "run"
        if phase == "waiting" and now >= phase_end:
            print("run did not start", file=sys.stderr)
            return 2
        if phase == "run" and not alive(handle):
            phase, phase_end = "after", now + a.after
        if phase == "after" and now >= phase_end:
            break
        if phase != "waiting":
            values = query()
            if values:
                samples.append({"t": round(now - started, 2), "local": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "phase": phase, **values})
        time.sleep(max(0.0, 1.0 - (time.monotonic() - now)))
    if handle:
        k32.CloseHandle(handle)
    (run_dir / "gpu_adapter.json").write_text(json.dumps({
        "run": a.run, "pid": pid, "source": "nvidia-smi --query-gpu (adapter-wide, 1 s)", "fields": FIELDS,
        "samples": samples}) + "\n", encoding="utf-8")
    for name in ("baseline", "run", "after"):
        rows = [s for s in samples if s["phase"] == name]
        if rows:
            def mean(key):
                values = [r[key] for r in rows if r.get(key) is not None]
                return sum(values) / len(values) if values else float("nan")
            states = sorted({r["pstate"] for r in rows})
            print(f"{name:8} n={len(rows):4} util={mean('utilization.gpu'):5.1f}% clock={mean('clocks.current.graphics'):6.0f} MHz "
                  f"power={mean('power.draw'):5.1f} W pstates={','.join(states)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
