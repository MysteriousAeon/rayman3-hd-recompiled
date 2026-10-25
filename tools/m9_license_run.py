"""Bounded hidden run with a stated licence mode and a small step script (M9, D-032).

Starts run_milestone6.ps1 (hidden window, scoped XAM input, foreground monitor, zero default captures) with
-LicenseMask 0 (trial control) or 1 (full version) and executes steps from a text file. Guest state is only read (m8_license_probe); input goes
through the same appended XAM schedule as every other hidden run; frames are explicit requests (cap 8 per process).

Step file, one step per line, '#' comments:
  log NEEDLE [TIMEOUT_S]     wait until the runtime log contains NEEDLE (rest of the line up to the last number)
  wait SECONDS
  press SCANCODE [HOLD_S]    40 Start, 44 A, 52 B, 15 X, 19 Y, 43 Back
  axis ID VALUE              300 lx, 301 ly, 302 rx, 303 ry; signed 16-bit, 0 releases
  probe LABEL                read-only licence / save-gate snapshot
  frame LABEL                one explicit frame request
  scale                      measure the attract-movie time scale (D-026); later waits are multiplied by it
  exit TIMEOUT_S             (M11) wait for the game to end by itself (a guest-initiated exit); the run then
                             passes only if the game's exit code is 0

Usage: python tools/m9_license_run.py RUN STEPS --license-mask {0,1} [--seconds 240] [--user-root NAME] [--play]
                                        [--extra=--cvar=value]   (M12: one runtime setting for a bounded A/B,
                                                                  checked by run_milestone6.ps1 -ExtraArgs)

"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("steps", type=Path)
    parser.add_argument("--license-mask", type=int, choices=(0, 1), required=True)
    parser.add_argument("--seconds", type=int, default=240)
    parser.add_argument("--user-root", default="")
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--extra", default="")
    parser.add_argument("--test-level", default="",
                        help="M13 (D-040): isolated test-only entry into this level directory (guest option -level:)")
    parser.add_argument("--audio-after", type=int, default=0,
                        help="M12: start the bounded 10 s float capture this many seconds after start-up")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run) or not 1 <= args.seconds <= 1500:
        parser.error("invalid bounded run")
    run_dir = ROOT / "private" / "work" / "m6_runs" / args.run
    if run_dir.exists():
        parser.error(f"run directory already exists: {run_dir}")
    steps = [line.split("#", 1)[0].split() for line in args.steps.read_text().splitlines()]
    steps = [step for step in steps if step]
    deadline = time.monotonic() + args.seconds + 60
    events, failure, frame_id, scale = [], None, 0, 1.0
    launch_log = ROOT / "private" / "work" / f"m6_{args.run}.launch.log"

    def logs() -> str:
        return "\n".join(path.read_text(errors="replace") for path in sorted(run_dir.glob("runtime*.log")))

    def alive(what: str) -> None:
        if launch.poll() is not None:
            raise RuntimeError(f"runner exited with code {launch.returncode} before {what}")
        if time.monotonic() > deadline:
            raise TimeoutError(f"deadline expired before {what}")

    def note(kind: str, **data) -> None:
        events.append({"utc": datetime.now(timezone.utc).isoformat(), "step": kind, **data})

    def log_time(needle: str):
        for line in logs().splitlines():
            if needle in line:
                return datetime.strptime(line[1:24], "%Y-%m-%d %H:%M:%S.%f")
        return None

    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / "run_milestone6.ps1"),
               "-Run", args.run, "-Seconds", str(args.seconds), "-Schedule", "config/m7/startup_empty.txt",
               "-LicenseMask", str(args.license_mask)]
    if args.user_root:
        command += ["-UserRoot", args.user_root]
    if args.play:
        command.append("-Play")
    if args.extra:
        command += ["-ExtraArgs", args.extra]
    if args.test_level:
        command += ["-TestLevel", args.test_level]
    if args.audio_after:
        command += ["-AudioAfter", str(args.audio_after)]
    with launch_log.open("w", encoding="utf-8") as output:
        launch = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        try:
            for step in steps:
                kind = step[0]
                if kind == "log":
                    timeout = float(step[-1]) if len(step) > 2 and re.fullmatch(r"[0-9.]+", step[-1]) else None
                    needle = " ".join(step[1:-1] if timeout is not None else step[1:])
                    end = time.monotonic() + (timeout * scale if timeout else 1e9)
                    found = False
                    while time.monotonic() < end:
                        if needle in logs():
                            found = True
                            break
                        alive(needle)
                        time.sleep(1.0)
                    note("log", needle=needle, found=found)
                    if not found:
                        raise RuntimeError(f"log needle not observed: {needle}")
                elif kind == "scale":
                    first, second = log_time("VIDEOS\\ubi.bik result=00000000"), log_time("VIDEOS\\trailer.bik result=00000000")
                    if first and second:
                        scale = min(3.0, max(1.0, (second - first).total_seconds() / 6.1))
                    note("scale", value=round(scale, 3))
                elif kind == "wait":
                    end = time.monotonic() + float(step[1]) * scale
                    while time.monotonic() < end:
                        alive("wait")
                        time.sleep(0.25)
                elif kind in ("press", "axis"):
                    with (run_dir / "schedule.txt").open("a", encoding="ascii", newline="") as stream:
                        stream.write(f"0 {int(step[1])} {1 if kind == 'press' else int(step[2])}\n")
                    if kind == "press":
                        time.sleep(float(step[2]) if len(step) > 2 else 0.2)
                        with (run_dir / "schedule.txt").open("a", encoding="ascii", newline="") as stream:
                            stream.write(f"0 {int(step[1])} 0\n")
                    note(kind, args=step[1:])
                elif kind == "probe":
                    alive("probe")
                    done = subprocess.run([sys.executable, str(ROOT / "tools" / "m8_license_probe.py"), str(run_dir)],
                                          cwd=ROOT, capture_output=True, text=True, timeout=30)
                    note("probe", label=step[1], state=json.loads(done.stdout) if done.returncode == 0 else None,
                         error=done.stderr[-400:] if done.returncode else None)
                elif kind == "frame":
                    frame_id += 1
                    (run_dir / "frame.request").write_text(f"{frame_id}\n", encoding="ascii")
                    time.sleep(1.5)
                    note("frame", label=step[1], request_id=frame_id)
                elif kind == "exit":
                    try:
                        launch.wait(timeout=float(step[1]) * scale)
                    except subprocess.TimeoutExpired:
                        raise RuntimeError("the game did not exit by itself") from None
                    note("exit", runner_return_code=launch.returncode)
                else:
                    raise ValueError(f"unknown step: {step}")
            launch.wait(timeout=max(1.0, deadline - time.monotonic()))
            if launch.returncode != 0:
                raise RuntimeError(f"runner exited with code {launch.returncode}")
        except BaseException as exc:  # noqa: BLE001 - recorded, then re-raised
            failure = exc
        finally:
            if launch.poll() is None:
                (run_dir / "cancel.request").write_text("driver abort\n", encoding="ascii")
                try:
                    launch.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    subprocess.run(["taskkill", "/PID", str(launch.pid), "/T", "/F"], capture_output=True, check=False)
            if run_dir.exists():
                (run_dir / "license_run.json").write_text(json.dumps({
                    "run": args.run, "license_mask": args.license_mask, "user_root": args.user_root or None,
                    "steps": str(args.steps), "movie_time_scale": round(scale, 3), "events": events,
                    "launch_return_code": launch.returncode,
                    "error": None if failure is None else {"type": type(failure).__name__, "message": str(failure)},
                }, indent=2) + "\n", encoding="utf-8")
    if failure is not None:
        raise failure
    print(f"licence run complete: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
