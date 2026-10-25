#!/usr/bin/env python3
"""One measured hidden run: resource sampler, adapter GPU sampler, address-space maps at fixed points (M12).

    python tools/m12_measure.py RUN [--steps config/m12/measure_load_intro15.txt] [--profile m9_save2]
                                    [--seconds 140] [--extra=--cvar=value] [--map NEEDLE:DELAY:LABEL ...]

Copies private/work/m9_profiles/<profile> to a fresh private/work/m9_profiles/RUN, starts
tools/m12_gpu_sample.py (10 s desktop baseline first) and tools/m11_perf_sample.py, runs the step file through
tools/m9_license_run.py (hidden, full version, playtest log profile), takes tools/m12_mem_map.py snapshots DELAY
seconds after the log first contains NEEDLE, and finally runs tools/m11_perf_summarize.py. Environment switches
(R3HD_STACK_COMMIT, R3HD_XMA_EAGER, R3HD_GPU_WAIT) are inherited by the game from the caller's environment and
recorded in private/work/m6_runs/RUN/m12_measure.json. Nothing here reads guest memory or sends desktop input.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWITCHES = ("R3HD_STACK_COMMIT", "R3HD_XMA_EAGER", "R3HD_GPU_WAIT")
DEFAULT_MAPS = ["VIDEOS\\ubi.bik result=00000000:3:movie", "menumap\\menumap.lvl result=00000000:22:menu",
                "intro_15\\intro_15.lvl result=00000000:45:level"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--steps", default="config/m12/measure_load_intro15.txt")
    ap.add_argument("--profile", default="m9_save2")
    ap.add_argument("--seconds", type=int, default=140)
    ap.add_argument("--extra", default="")
    ap.add_argument("--map", action="append")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.run):
        ap.error("invalid run name")
    run_dir = ROOT / "private" / "work" / "m6_runs" / a.run
    profiles = ROOT / "private" / "work" / "m9_profiles"
    if run_dir.exists() or (profiles / a.run).exists():
        ap.error("run or profile already exists")
    shutil.copytree(profiles / a.profile, profiles / a.run)
    py, tools = sys.executable, ROOT / "tools"
    out = ROOT / "private" / "work"
    gpu = subprocess.Popen([py, str(tools / "m12_gpu_sample.py"), a.run, "--baseline", "10"], cwd=ROOT,
                           stdout=(out / f"m12_{a.run}.gpu.log").open("w"), stderr=subprocess.STDOUT)
    time.sleep(11)
    perf = subprocess.Popen([py, str(tools / "m11_perf_sample.py"), a.run], cwd=ROOT,
                            stdout=(out / f"m12_{a.run}.sampler.log").open("w"), stderr=subprocess.STDOUT)
    command = [py, str(tools / "m9_license_run.py"), a.run, a.steps, "--license-mask", "1", "--seconds", str(a.seconds),
               "--user-root", a.run, "--play"]
    if a.extra:
        command.append(f"--extra={a.extra}")
    game = subprocess.Popen(command, cwd=ROOT, stdout=(out / f"m12_{a.run}.driver.log").open("w"),
                            stderr=subprocess.STDOUT)
    pending = [spec.rsplit(":", 2) for spec in (a.map or DEFAULT_MAPS)]
    seen, maps = {}, []
    while game.poll() is None:
        text = "".join(p.read_text(errors="replace") for p in sorted(run_dir.glob("runtime*.log"))) if run_dir.exists() else ""
        for needle, delay, label in list(pending):
            if needle in text and label not in seen:
                seen[label] = time.monotonic()
            if label in seen and time.monotonic() - seen[label] >= float(delay):
                done = subprocess.run([py, str(tools / "m12_mem_map.py"), a.run, "--label", label, "--top", "400"],
                                      cwd=ROOT, capture_output=True, text=True)
                maps.append({"label": label, "return_code": done.returncode})
                pending.remove([needle, delay, label])
        time.sleep(1.0)
    perf.wait(timeout=60)
    gpu.wait(timeout=60)
    summary = subprocess.run([py, str(tools / "m11_perf_summarize.py"), a.run, "--out", str(run_dir / "perf_summary.json")],
                             cwd=ROOT, capture_output=True, text=True)
    (run_dir / "m12_measure.json").write_text(json.dumps({
        "run": a.run, "steps": a.steps, "source_profile": a.profile, "extra": a.extra or None,
        "switches": {name: os.environ.get(name) for name in SWITCHES},
        "driver_return_code": game.returncode, "maps": maps, "maps_missed": [p[2] for p in pending],
        "summarize_return_code": summary.returncode}, indent=1) + "\n", encoding="utf-8")
    print((out / f"m12_{a.run}.gpu.log").read_text().strip())
    print(f"M12_MEASURE driver={game.returncode} maps={[m['label'] for m in maps]} missed={[p[2] for p in pending]} "
          f"summarize={summary.returncode}")
    return 0 if game.returncode == 0 and not pending else 1


if __name__ == "__main__":
    raise SystemExit(main())
