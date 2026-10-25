"""Play intro_15 to the intro_17 map change in a live hidden run, through normal input only.

Sequence (each step is the game's own objective, found by decoding its scripts and confirmed
live; nothing is written to the guest):
  1. follow the walking barrel (Mic_GlobBarrelIntro); it flees along its waypoint loop whenever
     Rayman is within 15 units, the route crosses the timed floor switch (NIN_m_SwitchDalle),
     and the barrel stops in Mic_C_gb_kick at the door waypoint while the door's bit 33 is set;
     kick it there (X without hands) -> Rayman designer variable 13 goes 1 -> 0 (hands back);
  2. after the cinematic, go to the fist switch (FRG_mSwitchSwap) and shoot it (X);
  3. after the second cinematic, walk into NIN_m_ChangeMap -> intro_17 loads.
Input is appended to the run's scoped XAM schedule (m7_path_pilot.py and this script).

Usage: python tools/m7_intro15_complete.py RUN_DIR SNAPSHOT_DIR [--seconds 700]
Output: RUN_DIR/intro15_complete.json plus the pilot logs (private).
"""
import argparse
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

from m5_live import Actor, Process

X_BUTTON, AXIS_X, AXIS_Y = 15, 300, 301
SWITCH_STAND = (357.0, 76.0, 1.0)      # observed standing spot 6 units from the switch
EXIT = (394.9, 88.7, 7.3)             # NIN_m_ChangeMap position


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--seconds", type=float, default=700)
    args = parser.parse_args()
    run = args.run.resolve()
    deadline = time.monotonic() + args.seconds
    report = {"steps": [], "result": "error"}
    schedule = run / "schedule.txt"

    def send(text: str) -> None:
        with schedule.open("a", encoding="ascii", newline="") as stream:
            stream.write(text)

    def left() -> float:
        return max(1.0, deadline - time.monotonic())

    def pilot(output: str, *argv: object, seconds: float) -> str:
        command = [sys.executable, str(Path(__file__).with_name("m7_path_pilot.py")), str(run), str(args.snapshot),
                   "--output", output, "--seconds", str(int(min(seconds, left()))), *map(str, argv)]
        done = subprocess.run(command, capture_output=True, text=True)
        try:
            result = json.loads(done.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            result = {"result": "error", "stderr": done.stderr[-400:]}
        report["steps"].append({"step": output, "arguments": [str(item) for item in argv], **result})
        return result.get("result", "error")

    def logs_contain(needle: str) -> bool:
        for path in run.glob("runtime*.log"):
            try:
                if needle in path.read_text(errors="replace"):
                    return True
            except OSError:
                continue
        return False

    try:
        pid = int(json.loads((run / "process.json").read_text(encoding="utf-8-sig"))["pid"])
        base = None
        for path in sorted(run.glob("runtime*.log")):
            with path.open(errors="replace") as stream:
                for line in stream:
                    match = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", line)
                    if match:
                        base = int(match.group(1), 16)
                        break
            if base is not None:
                break
        if base is None:
            raise RuntimeError("guest virtual base not found in runtime logs")
        process = Process(pid, base)
        actors = []
        for record in json.loads((run / "actors_intro_15.json").read_text(encoding="utf-8"))["actors"]:
            try:
                actors.append(Actor(process, int(record["so"], 16)))
            except (TypeError, ValueError, IndexError, OSError):
                continue

        def actor(model: str) -> Actor:
            return next(item for item in actors if item.model == model)

        rayman, camera = actor("YLT_RaymanModel"), actor("StdCam")
        murfy, switch, cagou = actor("NIN_m_MurfyIntro15"), actor("FRG_mSwitchSwap"), actor("NIN_m_CagouIntro")

        def hands_variable() -> int:
            buffer, offset = rayman.dsg()[13]
            return buffer[offset]

        def wait_for(condition, seconds: float) -> bool:
            end = time.monotonic() + min(seconds, left())
            while time.monotonic() < end:
                if condition():
                    return True
                time.sleep(0.2)
            return condition()

        report["hands_variable_before"] = hands_variable()
        if pilot("barrel_pilot.jsonl", "--follow", "Mic_GlobBarrelIntro", "--attack-comport", "gb_kick",
                 "--stop-dsg", "13=0", seconds=450) != "stop_dsg":
            raise RuntimeError("the barrel was not broken (Rayman variable 13 still set)")
        report["hands_variable_after"] = hands_variable()
        report["hands_recovered_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # Murfy leaves the hand cinematic by following his path again.
        report["hand_cinematic_ended"] = wait_for(lambda: "FollowPath" in (murfy.comport() or ""), 60)

        if pilot("switch_pilot.jsonl", "--goal", *SWITCH_STAND, "--goal-radius", "2.5", seconds=240) != "goal_reached":
            raise RuntimeError("the fist switch was not reached")
        shots = 0
        cine = lambda: "IsInCIne" in (cagou.comport() or "") or "TestPaf" not in (switch.comport() or "TestPaf")
        while shots < 8 and not cine() and time.monotonic() < deadline:
            me, cam, target = rayman.position(), camera.position(), switch.position()
            fx, fy = me[0] - cam[0], me[1] - cam[1]
            length = math.hypot(fx, fy) or 1.0
            dx, dy = target[0] - me[0], target[1] - me[1]
            distance = math.hypot(dx, dy) or 1.0
            forward = (dx * fx + dy * fy) / (length * distance)
            right = (dx * fy - dy * fx) / (length * distance)
            # Turn toward the switch with a short light push, then one X tap (fist).
            send(f"0 {AXIS_X} {int(right * 14000)}\n0 {AXIS_Y} {int(forward * 14000)}\n")
            time.sleep(0.25)
            send(f"0 {AXIS_X} 0\n0 {AXIS_Y} 0\n")
            time.sleep(0.3)
            send(f"0 {X_BUTTON} 1\n")
            time.sleep(0.15)
            send(f"0 {X_BUTTON} 0\n")
            shots += 1
            wait_for(cine, 2.5)
        report["fist_shots"] = shots
        report["switch_cinematic_started"] = cine()
        if not report["switch_cinematic_started"]:
            raise RuntimeError("the fist switch did not react")

        loaded = lambda: logs_contain("intro_17\\intro_17.lvl result=00000000")
        for attempt in range(3):
            if loaded():
                break
            pilot(f"exit_pilot{attempt}.jsonl", "--goal", *EXIT, "--goal-radius", "1.0", seconds=150)
            wait_for(loaded, 20)
        report["intro_17_loaded"] = loaded()
        report["result"] = "intro_17_loaded" if report["intro_17_loaded"] else "exit_not_reached"
    except BaseException as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        try:
            send(f"0 {AXIS_X} 0\n0 {AXIS_Y} 0\n0 {X_BUTTON} 0\n0 44 0\n")
        except OSError:
            pass
        (run / "intro15_complete.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in ("result", "fist_shots", "intro_17_loaded", "error")}))
    return 0 if report["result"] == "intro_17_loaded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
