"""M23: traced frames from a genuine save entry (hidden, muted, working copy of the entry's profile).

Loads a registered entry (m12_save_entry.py, D-039) through the title's own menu exactly as the M12 smoke does,
then runs a step tail from config/m23 that may contain `frame` steps. With the M22 draw trace on, the guest frame
after each explicit frame is written to the run directory; with --shaders the pinned SDK's own shader dump
(microcode disassembly of every shader the run translates) goes to RUN/shaders. Everything written is
game-derived and stays under private/. At most eight frames per process (the M6 readback cap).

usage: m23_trace_entry.py NAME RUN TAIL.txt [--seconds N] [--shaders] [--dry-run]
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import m12_save_entry as m12  # noqa: E402

ROOT = m12.ROOT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("run")
    ap.add_argument("tail", type=Path)
    ap.add_argument("--seconds", type=int, default=0)
    ap.add_argument("--shaders", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    entry = m12.load_entry(a.name)
    tail = [line.split("#", 1)[0].strip() for line in a.tail.read_text().splitlines()]
    tail = [line for line in tail if line]
    frames = sum(1 for line in tail if line.split()[0] == "frame")
    waits = sum(float(line.split()[1]) for line in tail if line.split()[0] == "wait")
    if not m12.NAME_RE.fullmatch(a.run) or not 1 <= frames <= 8:
        raise SystemExit("invalid RUN, or the tail has no frame step or more than eight")
    seconds = a.seconds or int(waits) + 95
    steps = m12.STEPS / f"{a.run}.txt"
    work = m12.PROFILES / a.run
    if (m12.RUNS / a.run).exists() or work.exists() or steps.exists():
        raise SystemExit(f"run, profile or step file already exists for {a.run}")
    if not m12.stored_profile_matches(entry):
        raise SystemExit(f"stored profile of {a.name} no longer matches entry.json")
    command = m12.driver_command(a.run, steps, seconds, a.run)
    env = dict(os.environ, R3HD_M22_DRAW_TRACE="1")
    if a.shaders:
        extra = [env["R3HD_HIDDEN_EXTRA"]] if env.get("R3HD_HIDDEN_EXTRA") else []
        env["R3HD_HIDDEN_EXTRA"] = ",".join(extra + ["--dump_shaders=shaders"])
    if a.dry_run:
        print(" ".join(command), f"frames={frames} seconds={seconds}")
        return 0
    shutil.copytree(m12.SAVES / a.name / "profile", work)
    m12.STEPS.mkdir(parents=True, exist_ok=True)
    steps.write_text("\n".join(m12.load_steps(0)[:-1] + tail) + "\n", encoding="ascii")
    log = ROOT / "private" / "work" / f"m23_{a.run}.driver.log"
    # The driver bounds the game itself (R3HD_TEST_SECONDS); this timeout only catches a driver that hangs. The
    # run is then judged from what it left, like any other failed run (working profile and step file stay).
    code = None
    with log.open("w", encoding="utf-8") as output:
        try:
            code = subprocess.run(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT,
                                  timeout=seconds + 300).returncode
        except subprocess.TimeoutExpired:
            pass
    facts = m12.evaluate_entry(entry, a.run)
    run_dir = m12.RUNS / a.run
    got_frames = len(list(run_dir.glob("m3_frame_*.bmp")))
    traces = len(list(run_dir.glob("m22_draws_*.bin")))
    # The smoke's rule "no frame captures" does not apply to a run whose purpose is its explicit frames.
    reasons = [r for r in facts["reasons"] if "frame captures" not in r]
    if code is None:
        reasons.append("driver timeout")
    elif code:
        reasons.append(f"driver exit code {code}")
    if got_frames != frames or traces != frames:
        reasons.append(f"frames {got_frames} / traces {traces} of {frames}")
    print(f"M23_TRACE_ENTRY {'FAIL' if reasons else 'PASS'} name={a.name} run={a.run} frames={got_frames} traces={traces}"
          + (f" reasons={';'.join(reasons)}" if reasons else ""))
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
