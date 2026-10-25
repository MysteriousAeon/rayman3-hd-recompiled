"""Bounded hidden run using the M5 read-only probes and normal XAM input.

No desktop input or guest writes are performed. If a probe fails, this wrapper
asks run_milestone6.ps1 to stop through a private cancellation marker and waits
for its run.json cleanup record before returning the original error.

Usage: python tools/m6_pilot_run.py RUN [--seconds 420]
       [--plan config/m5/ground_plan.txt] [--audio-after 0]
"""
import argparse
import json
import math
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def read_tail(path: Path, limit: int = 2_000_000) -> str:
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - limit))
            return stream.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    parser.add_argument("--seconds", type=int, default=420)
    parser.add_argument("--plan", default="config/m5/ground_plan.txt", help="ground-control plan passed to m5_ground_probe.py")
    parser.add_argument("--ground-seconds", type=int, default=150)
    parser.add_argument("--pilot-seconds", type=int, default=200, help="maximum intro_10 flight-pilot observation time")
    parser.add_argument("--route", type=Path, help="optional intro_15 route target JSON file")
    parser.add_argument("--route-seconds", type=int, default=300, help="maximum route-pilot run time (1..500)")
    parser.add_argument("--route-jump-every", type=float, default=0, help="optional normal A pulse period; 0 disables")
    parser.add_argument("--route-jump-hold", type=float, default=0.2)
    parser.add_argument("--audio-after", type=int, default=0, help="forwarded to run_milestone6.ps1")
    parser.add_argument("--play", action="store_true",
                        help="M8: run the hidden game with the human-playtest diagnostic profile (run_milestone6.ps1 -Play)")
    parser.add_argument("--license-mask", type=int, choices=(0, 1), default=1,
                        help="M9 (D-032): 1 full version (build default), 0 trial control as in M5..M8 (run_milestone6.ps1 -LicenseMask)")
    parser.add_argument("--user-root", default="", help="M9: persistent isolated profile name (run_milestone6.ps1 -UserRoot)")
    parser.add_argument("--path-goal", nargs=3, type=float, metavar=("X", "Y", "Z"), help="after the ground stage, run m7_path_pilot.py to this position")
    parser.add_argument("--path-snapshot", default="private/work/m7_snap", help="collision snapshot directory for --path-goal")
    parser.add_argument("--path-seconds", type=int, default=500)
    parser.add_argument("--path-stop-comport", default="")
    parser.add_argument("--path-follow", default="", help="follow this actor model with m7_path_pilot.py instead of --path-goal")
    parser.add_argument("--path-attack-comport", default="")
    parser.add_argument("--path-stop-dsg", default="")
    parser.add_argument("--intro15-complete", action="store_true", help="after the ground stage, run m7_intro15_complete.py (barrel, fist switch, intro_17 map change)")
    parser.add_argument("--fixed-startup", action="store_true", help="use the former fixed-time menu schedule instead of observed-state startup")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run):
        parser.error("RUN may contain only letters, digits, underscore, and hyphen")
    if (
        not 1 <= args.seconds <= 1500
        or not 1 <= args.ground_seconds <= 900
        or not 1 <= args.pilot_seconds <= 300
        or not 1 <= args.route_seconds <= 500
        or args.audio_after < 0
    ):
        parser.error("seconds must be 1..1500, ground-seconds 1..900, pilot-seconds 1..300, route-seconds 1..500, audio-after nonnegative")
    if (not math.isfinite(args.route_jump_every) or
        (args.route_jump_every != 0 and args.route_jump_every < 1) or
        not math.isfinite(args.route_jump_hold) or args.route_jump_hold <= 0 or
        (args.route_jump_every > 0 and args.route_jump_hold >= args.route_jump_every)):
        parser.error("route jump period must be 0 or >=1; hold must be finite, positive, and below enabled period")

    root = Path(__file__).resolve().parents[1]
    run_dir = root / "private" / "work" / "m6_runs" / args.run
    launch_log = root / "private" / "work" / f"m6_{args.run}.launch.log"
    pilot_report = run_dir / "pilot.json"
    cancel_request = run_dir / "cancel.request"
    plan = Path(args.plan)
    if not plan.is_absolute():
        plan = (Path.cwd() / plan) if (Path.cwd() / plan).is_file() else (root / plan)
    plan = plan.resolve()
    if not plan.is_file():
        parser.error(f"ground plan does not exist: {plan}")
    route_path = None
    if args.route is not None:
        route_path = args.route if args.route.is_absolute() else (Path.cwd() / args.route if (Path.cwd() / args.route).is_file() else root / args.route)
        route_path = route_path.resolve()
        if not route_path.is_file():
            parser.error(f"route target file does not exist: {route_path}")

    # The guest timer starts after launcher initialization. Allow bounded startup
    # and orderly shutdown instead of racing a 900s guest against a 900s wrapper.
    # All stages still share one deadline (requested guest seconds + 60).
    deadline = time.monotonic() + args.seconds + 60
    launch = None
    launch_return_code = None
    guest_pid = None
    executed = []
    startup_events = []
    failure = None
    started_utc = datetime.now(timezone.utc).isoformat()

    def remaining() -> float:
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError("Milestone 6 orchestration deadline expired")
        return value

    def runtime_logs() -> str:
        return "\n".join(read_tail(path) for path in sorted(run_dir.glob("runtime*.log")))

    def check_launch(description: str) -> None:
        if launch is not None and launch.poll() is not None:
            raise RuntimeError(
                f"run_milestone6.ps1 exited with code {launch.returncode} before {description}; "
                f"runtime log tail:\n{runtime_logs()[-12000:]}"
            )

    def wait_for_log(needle: str) -> None:
        while needle not in runtime_logs():
            check_launch(needle)
            remaining()
            time.sleep(min(1.0, remaining()))

    def wait_for_process_json() -> dict:
        path = run_dir / "process.json"
        while True:
            check_launch("process.json")
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8-sig"))
                    pid = int(data["pid"])
                    if pid > 0:
                        return data
                except (OSError, ValueError, KeyError, json.JSONDecodeError):
                    pass
            remaining()
            time.sleep(min(0.2, remaining()))

    def log_time(needle: str):
        """Timestamp of the first retained log line containing needle, or None."""
        for path in sorted(run_dir.glob("runtime*.log"), key=lambda item: item.stat().st_mtime):
            try:
                with path.open(errors="replace") as stream:
                    for line in stream:
                        if needle in line:
                            return datetime.strptime(line[1:24], "%Y-%m-%d %H:%M:%S.%f")
            except (OSError, ValueError):
                continue
        return None

    def press(scan: int, label: str, hold: float = 0.2) -> None:
        # Same scoped XAM schedule as every other M6 input; never desktop input.
        schedule = run_dir / "schedule.txt"
        with schedule.open("a", encoding="ascii", newline="") as stream:
            stream.write(f"0 {scan} 1\n")
        time.sleep(hold)
        with schedule.open("a", encoding="ascii", newline="") as stream:
            stream.write(f"0 {scan} 0\n")
        startup_events.append({"utc": datetime.now(timezone.utc).isoformat(), "label": label, "scancode": scan})

    def wait_seconds(seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            check_launch("startup delay")
            time.sleep(min(0.5, remaining()))

    def wait_for_log_until(needle: str, seconds: float) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if needle in runtime_logs():
                return True
            check_launch(needle)
            time.sleep(min(1.0, remaining()))
        return needle in runtime_logs()

    def state_driven_startup() -> None:
        """Title -> New Game -> name -> intro movie -> intro_10 from observed file opens.

        The former fixed schedule assumed the attract movies end 45 s after the
        first controller poll. m7_repeat played them at about half speed, so
        Start skipped the trailer instead of leaving the title screen and every
        later press was one screen behind. Presses are now issued only after the
        menu map is observed, with delays scaled by the measured movie slowdown.
        """
        menumap = "menumap\\menumap.lvl result=00000000"
        # The full version skips the trailer attract movie (E-58); the time scale then stays 1.
        wait_for_log(menumap if args.license_mask else "VIDEOS\\trailer.bik result=00000000")
        first, second = log_time("VIDEOS\\ubi.bik result=00000000"), log_time("VIDEOS\\trailer.bik result=00000000")
        scale = 1.0
        if first and second:
            scale = min(3.0, max(1.0, (second - first).total_seconds() / 6.1))
        startup_events.append({"label": "movie_time_scale", "value": round(scale, 3)})
        wait_for_log(menumap)
        wait_seconds(10 * scale)
        press(40, "start_title")
        wait_seconds(15 * scale)
        press(44, "a_new_game")
        wait_seconds(15 * scale)
        press(44, "a_confirm_name")
        retries = 0
        while not wait_for_log_until("VIDEOS\\intro.bik result=00000000", 20 * scale):
            if retries == 2:
                raise RuntimeError("intro.bik did not open after New Game and two bounded A retries")
            retries += 1
            press(44, f"a_retry_{retries}")
        wait_seconds(15 * scale)
        press(40, "start_skip_intro_movie")
        if not wait_for_log_until("intro_10.lvl result=00000000", 30 * scale):
            press(40, "start_skip_intro_movie_retry")
            wait_for_log("intro_10.lvl result=00000000")

    def call(script: str, *argv: object) -> None:
        command = [sys.executable, str(root / "tools" / script), *map(str, argv)]
        executed.append(command)
        subprocess.run(command, cwd=root, check=True, timeout=remaining())

    try:
        if run_dir.exists():
            raise FileExistsError(f"run directory already exists: {run_dir}")
        launch_log.parent.mkdir(parents=True, exist_ok=True)
        with launch_log.open("w", encoding="utf-8") as output:
            launch = subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(root / "tools" / "run_milestone6.ps1"),
                    "-Run",
                    args.run,
                    "-Seconds",
                    str(args.seconds),
                    "-AudioAfter",
                    str(args.audio_after),
                    "-Schedule",
                    "config/m5/idle.txt" if args.fixed_startup else "config/m7/startup_empty.txt",
                ] + (["-Play"] if args.play else [])
                + ["-LicenseMask", str(args.license_mask)]
                + (["-UserRoot", args.user_root] if args.user_root else []),
                cwd=root,
                stdout=output,
                stderr=subprocess.STDOUT,
            )

            if args.fixed_startup:
                wait_for_log("intro_10.lvl result=00000000")
            else:
                state_driven_startup()
            time.sleep(min(22.0, remaining()))
            process_info = wait_for_process_json()
            guest_pid = int(process_info["pid"])
            # Startup mapping may be outside a rolling segment's last 2 MB.
            # Scan the retained logs once rather than rereading them on every poll.
            base_match = None
            for path in sorted(run_dir.glob("runtime*.log")):
                with path.open(errors="replace") as stream:
                    for line in stream:
                        base_match = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", line)
                        if base_match:
                            break
                if base_match:
                    break
            if base_match is None:
                raise RuntimeError("runtime log did not report the guest virtual base")
            base = base_match.group(1)

            call("m5_memory_probe.py", guest_pid, base, run_dir / "actors.json", "--regions")
            call("m5_script_probe.py", guest_pid, base, run_dir / "actors.json", run_dir / "scripts")
            call(
                "m5_flight_pilot.py",
                guest_pid,
                base,
                run_dir / "actors.json",
                run_dir / "schedule.txt",
                run_dir / "pilot.log",
                "--seconds",
                args.pilot_seconds,
            )
            flight_log = run_dir / "pilot.log"
            maximum_lums = 0
            if flight_log.is_file():
                for line in flight_log.read_text(encoding="utf-8", errors="replace").splitlines():
                    try:
                        record = json.loads(line)
                        value = record.get("lums")
                        if isinstance(value, int):
                            maximum_lums = max(maximum_lums, value)
                    except json.JSONDecodeError:
                        continue
            if maximum_lums < 6:
                raise RuntimeError(f"intro_10 flight did not verify six collected lums (observed maximum {maximum_lums}); ground stage skipped")
            call(
                "m5_ground_probe.py",
                guest_pid,
                base,
                run_dir,
                "--plan",
                plan,
                "--ready-comport",
                "YAM_C_Attente",
                "--seconds",
                args.ground_seconds,
            )
            if route_path is not None:
                call(
                    "m6_route_probe.py",
                    guest_pid,
                    base,
                    run_dir,
                    "--targets",
                    route_path,
                    "--seconds",
                    args.route_seconds,
                    "--jump-every",
                    args.route_jump_every,
                    "--jump-hold",
                    args.route_jump_hold,
                )
            if args.path_goal is not None or args.path_follow:
                path_args = [run_dir, root / args.path_snapshot, "--seconds", args.path_seconds]
                path_args += ["--goal", *args.path_goal] if args.path_goal is not None else ["--follow", args.path_follow]
                if args.path_attack_comport:
                    path_args += ["--attack-comport", args.path_attack_comport]
                if args.path_stop_dsg:
                    path_args += ["--stop-dsg", args.path_stop_dsg]
                if args.path_stop_comport:
                    path_args += ["--stop-comport", args.path_stop_comport]
                call("m7_path_pilot.py", *path_args)
            if args.intro15_complete:
                call("m7_intro15_complete.py", run_dir, root / args.path_snapshot, "--seconds", args.path_seconds)
            launch_return_code = launch.wait(timeout=remaining())
            if launch_return_code != 0:
                raise RuntimeError(f"run_milestone6.ps1 exited with code {launch_return_code}; see {launch_log}")
    except BaseException as exc:
        failure = exc
    finally:
        # Cancellation is private to this run. The PowerShell runner owns game
        # shutdown and writes run.json from its finally block.
        if launch is not None and launch.poll() is None:
            try:
                if run_dir.exists():
                    cancel_request.write_text("pilot abort\n", encoding="ascii")
                launch.wait(timeout=min(12.0, max(1.0, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                # Last-resort cleanup is restricted to this runner's process tree.
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(launch.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                        timeout=10,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    launch.terminate()
                try:
                    launch_return_code = launch.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    launch.kill()
                    launch_return_code = launch.wait(timeout=5)
            except OSError as cleanup_error:
                if failure is None:
                    failure = cleanup_error
        if launch is not None and launch_return_code is None:
            launch_return_code = launch.poll()

        report = {
            "started_utc": started_utc,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "run": args.run,
            "seconds": args.seconds,
            "ground_seconds": args.ground_seconds,
            "pilot_seconds": args.pilot_seconds,
            "route_targets": str(route_path) if route_path is not None else None,
            "route_seconds": args.route_seconds if route_path is not None else None,
            "route_jump_every": args.route_jump_every,
            "route_jump_hold": args.route_jump_hold,
            "audio_after": args.audio_after,
            "license_mask": args.license_mask,
            "user_root": args.user_root or None,
            "ground_plan": str(plan),
            "guest_pid_from_process_json": guest_pid,
            "launch_pid": launch.pid if launch is not None else None,
            "launch_return_code": launch_return_code,
            "startup": "fixed" if args.fixed_startup else "state_driven",
            "startup_events": startup_events,
            "commands": executed,
            "error": None if failure is None else {"type": type(failure).__name__, "message": str(failure)},
        }
        try:
            if run_dir.exists():
                pilot_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        except OSError as report_error:
            if failure is None:
                failure = report_error

    if failure is not None:
        print(f"Milestone 6 pilot failed: {type(failure).__name__}: {failure}", file=sys.stderr)
        if launch_log.exists():
            print(f"Launch log: {launch_log}", file=sys.stderr)
        raise failure
    print(f"M6 pilot complete: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
