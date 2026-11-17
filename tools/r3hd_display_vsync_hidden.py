#!/usr/bin/env python3
"""D-220: hidden Off/On A/B of the host display V-Sync, only through tools/run_milestone6.ps1 (hidden window,
scoped XAM/SDL test input, muted audio, haptics suppressed, no captures).

    python tools/r3hd_display_vsync_hidden.py [--scenario gameplay|settings ...] [--mode off|on ...] [--tag T]

Scenarios (isolated test-only level entry, D-040; never played progression):
  gameplay  wood_11: level load, scheduled movement / jump, pause (Start) and resume, with the M17 frame trace.
  settings  menu_20: the in-game Settings panel toggled open/closed twice by R3HD_PCSET_TEST (continuous UI repaint
            while open), no scheduled input.
Each mode sets R3HD_DISPLAY_VSYNC exactly as play.ps1 does. Runs are serial; the next starts after the game exits.

Per run: tools/r3hd_display_vsync_check.py --expect MODE, tools/m16_pacing_check.py (deadline) and, for gameplay,
tools/m17_frame_trace.py check. The process's CPU time is sampled read-only (GetProcessTimes; no memory read) and
reported as a share of one core over the steady part of the run. Summary: private/work/display_vsync/<tag>.json.
Afterwards judge the run set with m21_regression.py / m22_regression.py / m23_haptics_regression.py --run.
A hidden run measures what the application asked DXGI for and how the calls behaved; not what a display showed.
"""
import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "private" / "work" / "m6_runs"
WORK = ROOT / "private" / "work" / "display_vsync"
PY = sys.executable

# "ms scancode down" (SDL scancodes, default bindings): 7 D = move right, 44 Space = A (jump), 40 Return = Start.
GAMEPLAY = """# D-220 gameplay: move, jump, pause, resume, move.
30000 7 1
34000 7 0
35000 44 1
35200 44 0
40000 40 1
40200 40 0
52000 40 1
52200 40 0
58000 7 1
62000 7 0
63000 44 1
63200 44 0
"""
SCENARIOS = {
    "gameplay": {"level": "wood_11", "seconds": 95, "schedule": "gameplay.txt", "trace": True, "env": {}},
    "settings": {"level": "menu_20", "seconds": 105, "schedule": "quiet.txt", "trace": False,
                 "env": {"R3HD_PCSET_TEST": "30,45,60,75"}},
}


class FILETIME(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]


def cpu_seconds(pid):
    """Kernel + user time of a process (PROCESS_QUERY_LIMITED_INFORMATION; no memory access)."""
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    try:
        c, e, kt, ut = FILETIME(), FILETIME(), FILETIME(), FILETIME()
        if not k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut)):
            return None
        return ((kt.hi << 32 | kt.lo) + (ut.hi << 32 | ut.lo)) / 1e7
    finally:
        k32.CloseHandle(h)


def run_one(scenario, mode, tag):
    sc = SCENARIOS[scenario]
    name = f"vsync_{tag}_{scenario}_{mode}"
    run_dir = RUNS / name
    schedule = WORK / sc["schedule"]
    env = dict(os.environ)
    env["R3HD_DISPLAY_VSYNC"] = mode
    env.update(sc["env"])
    trace = None
    if sc["trace"]:
        trace = WORK / f"{name}.trace"
        for stale in (trace, Path(str(trace) + ".watch")):
            if stale.exists():
                stale.unlink()
        subprocess.run([PY, str(ROOT / "tools/m17_frame_trace.py"), "prepare", str(trace)], check=True, cwd=ROOT)
        env["R3HD_FRAME_TRACE"] = str(trace)
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools/run_milestone6.ps1"),
           "-Run", name, "-Seconds", str(sc["seconds"]), "-Schedule", str(schedule.relative_to(ROOT)),
           "-TestLevel", sc["level"]]
    with (WORK / f"{name}.launch.log").open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
        pid, samples, started = None, [], time.monotonic()
        while proc.poll() is None:
            if pid is None and (run_dir / "process.json").exists():
                try:
                    pid = json.loads((run_dir / "process.json").read_text(encoding="utf-8-sig"))["pid"]
                    started = time.monotonic()
                except (ValueError, KeyError, OSError):
                    pid = None
            if pid is not None:
                c = cpu_seconds(pid)
                if c is not None:
                    samples.append((time.monotonic() - started, c))
            time.sleep(2.0)
    steady = [s for s in samples if 25.0 <= s[0] <= sc["seconds"] - 5.0]
    cpu = None
    if len(steady) >= 2 and steady[-1][0] > steady[0][0]:
        cpu = round(100.0 * (steady[-1][1] - steady[0][1]) / (steady[-1][0] - steady[0][0]), 1)
    result = {"run": name, "scenario": scenario, "mode": mode, "runner_exit": proc.returncode,
              "cpu_percent_of_one_core": cpu, "cpu_window_s": [round(steady[0][0], 1), round(steady[-1][0], 1)] if len(steady) >= 2 else None}
    try:
        meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8-sig"))
        result.update(exit_code=meta.get("exit_code"), forced_termination=meta.get("forced_termination"),
                      game_foreground_events=meta.get("game_foreground_events"),
                      game_foreground_samples=meta.get("game_foreground_samples"), error=meta.get("error"))
    except (OSError, ValueError):
        result["error"] = "run.json missing"

    def judge(args, marker):
        p = subprocess.run([PY] + args, cwd=ROOT, capture_output=True, text=True)
        line = next((ln for ln in p.stdout.splitlines()[::-1] if ln.startswith(marker)), p.stdout.strip()[-400:])
        return {"exit": p.returncode, "line": line}

    result["vsync_check"] = judge(["tools/r3hd_display_vsync_check.py", str(run_dir), "--expect", mode,
                                   "--json", str(WORK / f"{name}.vsync.json")], "DISPLAY_VSYNC_CHECK")
    result["pacing_check"] = judge(["tools/m16_pacing_check.py", str(run_dir)], "PACING_CHECK")
    if trace is not None:
        result["timing_check"] = judge(["tools/m17_frame_trace.py", "check", str(trace), "--from-frame", "600"],
                                       "TIMING_CHECK")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", nargs="+", choices=sorted(SCENARIOS), default=["gameplay", "settings"])
    ap.add_argument("--mode", nargs="+", choices=("off", "on"), default=["off", "on"])
    ap.add_argument("--tag", default="ab")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9]{1,16}", a.tag):
        raise SystemExit("tag must be short alphanumeric")
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "gameplay.txt").write_text(GAMEPLAY, encoding="ascii")
    (WORK / "quiet.txt").write_text("# D-220 settings: no scheduled key; the panel toggles itself (R3HD_PCSET_TEST).\n",
                                    encoding="ascii")
    results = []
    for scenario in a.scenario:
        for mode in a.mode:
            r = run_one(scenario, mode, a.tag)
            results.append(r)
            print(json.dumps(r), flush=True)
    (WORK / f"{a.tag}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    bad = [r["run"] for r in results if r.get("exit_code") != 0 or r["vsync_check"]["exit"] != 0
           or r.get("game_foreground_events") or r.get("game_foreground_samples")]
    print(f"DISPLAY_VSYNC_HIDDEN {'PASS' if not bad else 'FAIL'} runs={len(results)} bad={bad}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
