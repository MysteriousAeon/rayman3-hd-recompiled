#!/usr/bin/env python3
"""Does the player character respond to input in an isolated test-only level run? (M13, D-040)

    python tools/m13_control_check.py TAG LEVEL [LEVEL ...] [--settle 25]

One hidden run per level (m13_<TAG>_<level>, title option "-level:<level>" through run_milestone6.ps1
-TestLevel). After the level has been open for --settle seconds the existing read-only probes are used
(tools/m5_memory_probe.py actor discovery, tools/m7_live_status.py): Rayman's position and behaviour are sampled
idle, while the left stick is held forward for 3 s through the scoped XAM schedule, and after an A press.
No guest memory is written; input goes only through the run's own schedule file.

Result rows: private/work/m13/control_<TAG>.json. A row says whether a player actor exists, which behaviour it
is in, and whether stick and A changed its position or behaviour. It does not say the level is playable.
"""
import argparse
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "private" / "work" / "m6_runs"
WORK = ROOT / "private" / "work" / "m13"


def status(run_dir: Path, level: str, samples: int = 1) -> list:
    done = subprocess.run([sys.executable, str(ROOT / "tools" / "m7_live_status.py"), str(run_dir), "--level", level,
                           "--near", "0", "--samples", str(samples), "--interval", "0.5"], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)
    rows = []
    for line in done.stdout.splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def schedule(run_dir: Path, code: int, value: int) -> None:
    with (run_dir / "schedule.txt").open("a", encoding="ascii", newline="") as stream:
        stream.write(f"0 {code} {value}\n")


def check(tag: str, level: str, settle: int) -> dict:
    run_name = f"m13_{tag}_{level}"
    run_dir = RUNS / run_name
    if run_dir.exists():
        raise SystemExit(f"run directory exists: {run_name}")
    WORK.mkdir(parents=True, exist_ok=True)
    seconds = settle + 45
    steps = WORK / f"steps_{run_name}.txt"
    steps.write_text(f"wait {seconds - 8}\n", encoding="ascii")
    row: dict = {"run": run_name, "level": level, "entry": "isolated test-only (-level:)"}
    with (WORK / f"{run_name}.driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(ROOT / "tools" / "m9_license_run.py"), run_name, str(steps),
                                 "--license-mask", "1", "--seconds", str(seconds), "--play", "--test-level", level],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            needle = re.compile(rf"[\\/]{re.escape(level)}\.lvl result=00000000", re.IGNORECASE)
            opened, base, end = None, None, time.monotonic() + 60
            while time.monotonic() < end and game.poll() is None and opened is None:
                time.sleep(1)
                log_path = run_dir / "runtime.log"
                if log_path.is_file():
                    text = log_path.read_text(errors="replace")
                    if needle.search(text):
                        opened = time.monotonic()
                    m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
                    base = m.group(1) if m else base
            if opened is None or base is None:
                row["error"] = "level did not open"
                return row
            time.sleep(settle)
            pid = json.loads((run_dir / "process.json").read_text(encoding="utf-8-sig"))["pid"]
            probe = subprocess.run([sys.executable, str(ROOT / "tools" / "m5_memory_probe.py"), str(pid), base,
                                    str(run_dir / f"actors_{level}.json"), "--regions"], cwd=ROOT, capture_output=True,
                                   text=True, timeout=120)
            if probe.returncode != 0:
                row["error"] = "actor discovery failed: " + probe.stderr.strip()[-200:]
                return row
            actors = json.loads((run_dir / f"actors_{level}.json").read_text(encoding="utf-8"))["actors"]
            row["actors"] = len(actors)
            idle = status(run_dir, level, 3)
            if not idle:
                row["player_actor"] = False
                return row
            row["player_actor"] = True
            schedule(run_dir, 301, 32767)
            time.sleep(1.5)
            pushed_mid = status(run_dir, level, 1)
            time.sleep(1.5)
            schedule(run_dir, 301, 0)
            time.sleep(0.5)
            pushed = status(run_dir, level, 1)
            schedule(run_dir, 44, 1)
            time.sleep(0.25)
            schedule(run_dir, 44, 0)
            jump = status(run_dir, level, 4)
            time.sleep(3)
            after = status(run_dir, level, 1)

            def pos(rows):
                return rows[-1]["rayman"] if rows else None
            row.update(
                idle_comport=[r["comport"] for r in idle], idle_reflex=idle[-1].get("reflex"),
                idle_drift=round(math.dist(idle[0]["rayman"], idle[-1]["rayman"]), 3),
                push_comport=[r["comport"] for r in pushed_mid + pushed],
                push_displacement=round(math.dist(pos(idle), pos(pushed)), 3) if pushed else None,
                jump_comport=[r["comport"] for r in jump],
                jump_max_rise=round(max((r["rayman"][2] for r in jump), default=pos(pushed)[2]) - pos(pushed)[2], 3) if pushed else None,
                after_comport=[r["comport"] for r in after])
            moved = (row["push_displacement"] or 0) - 3 * row["idle_drift"] > 1.0
            changed = any(c not in row["idle_comport"] for c in row["push_comport"] + row["jump_comport"])
            row["responds_to_input"] = bool(moved or changed)
        finally:
            try:
                game.wait(timeout=seconds + 120)
            except subprocess.TimeoutExpired:
                (run_dir / "cancel.request").write_text("control check abort\n", encoding="ascii")
                game.wait(timeout=60)
            meta_path = run_dir / "run.json"
            if meta_path.is_file():
                meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
                row.update(exit_code=meta.get("exit_code"), forced_termination=meta.get("forced_termination"),
                           game_foreground_events=meta.get("game_foreground_events"),
                           executable_sha256=meta.get("executable_sha256"))
                log_text = (run_dir / "runtime.log").read_text(errors="replace")
                row["stub_lines"] = log_text.count(" stub=true ")
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("levels", nargs="+")
    ap.add_argument("--settle", type=int, default=25)
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9]+", a.tag) or not 5 <= a.settle <= 300:
        ap.error("invalid TAG or --settle (5..300)")
    result = WORK / f"control_{a.tag}.json"
    rows = json.loads(result.read_text()) if result.is_file() else []
    for level in a.levels:
        row = check(a.tag, level, a.settle)
        rows.append(row)
        WORK.mkdir(parents=True, exist_ok=True)
        result.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
        print(f"M13_CONTROL {level} actors={row.get('actors')} player={row.get('player_actor')} "
              f"idle={row.get('idle_comport', [None])[-1] if row.get('idle_comport') else None} "
              f"push_d={row.get('push_displacement')} push={row.get('push_comport')} jump={row.get('jump_comport')} "
              f"rise={row.get('jump_max_rise')} responds={row.get('responds_to_input')} exit={row.get('exit_code')} "
              f"error={row.get('error')}", flush=True)
        time.sleep(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
