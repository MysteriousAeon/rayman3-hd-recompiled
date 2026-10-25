#!/usr/bin/env python3
"""One bounded gameplay scenario in an isolated test-only level run, with a read-only actor watch (M14).

    python tools/m14_scenario.py RUN LEVEL STEPS --seconds N [--settle 10] [--watch MODEL,MODEL] [--radius 0]
                                 [--expect CHECK,CHECK...]

Starts tools/m9_license_run.py RUN STEPS --test-level LEVEL (hidden, scoped input from the step file, D-040),
waits --settle seconds after the level file opened, discovers the actors (tools/m5_memory_probe.py) and runs
tools/m14_combat_watch.py beside the game until it ends. The run is then judged by the mechanical criteria of
the M13 sweep (exit 0, no stub, fatal, trap, invalid target, unexpected exception code, foreground event) and
by the --expect checks over the watch (each must be observed at least once):

  player:NAME        the player actor entered a behaviour or reflex whose name contains NAME
  actor:MODEL:NAME   an actor of MODEL entered a behaviour or reflex whose name contains NAME
  gone:MODEL         an actor of MODEL stopped being a live actor (killed / freed)
  hp:MODEL           the hit-point byte of an actor of MODEL changed (StdGame +0x1D, RE_NOTES "M14")
  reloads:N          the level file was opened at least N times in the process (restart after death)

Nothing is written to the guest. Results: private/work/m14/scenario_<RUN>.json (metadata) and
private/work/m6_runs/<RUN>/watch.jsonl (private). Prints M14_SCENARIO PASS / FAIL.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m13_level_sweep import evaluate, known_imports  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "private" / "work" / "m6_runs"
WORK = ROOT / "private" / "work" / "m14"
PLAYER = "YLT_RaymanModel"


def hp(std_hex):
    """Hit points and their maximum from the recorded StdGame +0x10..+0x50 block (StdGame +0x1D, +0x1E)."""
    if not std_hex or len(std_hex) < 0x10 * 2:
        return None
    block = bytes.fromhex(std_hex)
    return block[0x0D], block[0x0E]


def judge(expect: list, rows: list, loads: list, level: str) -> dict:
    seen = {}
    for check in expect:
        parts = check.split(":")
        kind, ok = parts[0], False
        if kind in ("player", "actor") and len(parts) == (2 if kind == "player" else 3):
            model, name = (PLAYER, parts[1]) if kind == "player" else (parts[1], parts[2])
            ok = any(r.get("model") == model and (name in (r.get("comport") or "") or name in (r.get("reflex") or ""))
                     for r in rows)
        elif kind == "gone" and len(parts) == 2:
            ok = any(r.get("model") == parts[1] and r.get("alive") is False for r in rows)
        elif kind == "hp" and len(parts) == 2:
            values = {}
            for r in rows:
                if r.get("model") == parts[1] and r.get("std"):
                    values.setdefault(r["perso"], set()).add(hp(r["std"]))
            ok = any(len(v) > 1 for v in values.values())
        elif kind == "reloads" and len(parts) == 2:
            ok = sum(1 for name in loads if name == level) >= int(parts[1])
        else:
            raise SystemExit(f"unknown --expect check: {check}")
        seen[check] = ok
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("level")
    ap.add_argument("steps", type=Path)
    ap.add_argument("--seconds", type=int, required=True)
    ap.add_argument("--settle", type=int, default=10)
    ap.add_argument("--watch", default="")
    ap.add_argument("--radius", type=float, default=0.0)
    ap.add_argument("--expect", default="")
    ap.add_argument("--player-dsg", action="store_true", help="record the player's designer variables per sample")
    a = ap.parse_args()
    run_dir = RUNS / a.run
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.run) or run_dir.exists() or not 20 <= a.seconds <= 900:
        ap.error("invalid or existing RUN, or --seconds outside 20..900")
    WORK.mkdir(parents=True, exist_ok=True)
    level = a.level.lower()
    expect = [c for c in a.expect.split(",") if c]
    result = {"run": a.run, "level": level, "entry": "isolated test-only (-level:)", "steps": a.steps.name,
              "expect": {}, "reasons": []}
    watcher = None
    with (WORK / f"{a.run}.driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(ROOT / "tools" / "m9_license_run.py"), a.run, str(a.steps),
                                 "--license-mask", "1", "--seconds", str(a.seconds), "--play", "--test-level", level],
                                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        try:
            needle = re.compile(rf"[\\/]{re.escape(level)}\.lvl result=00000000", re.IGNORECASE)
            opened, base, end = False, None, time.monotonic() + 60
            while time.monotonic() < end and game.poll() is None and not opened:
                time.sleep(1)
                log_path = run_dir / "runtime.log"
                if log_path.is_file():
                    text = log_path.read_text(errors="replace")
                    opened = bool(needle.search(text))
                    m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
                    base = m.group(1) if m else base
            if not opened or base is None:
                result["reasons"].append("level did not open")
            else:
                time.sleep(a.settle)
                pid = json.loads((run_dir / "process.json").read_text(encoding="utf-8-sig"))["pid"]
                actors = run_dir / f"actors_{level}.json"
                probe = subprocess.run([sys.executable, str(ROOT / "tools" / "m5_memory_probe.py"), str(pid), base,
                                        str(actors), "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
                if probe.returncode != 0:
                    result["reasons"].append("actor discovery failed")
                else:
                    extra = ["--player-dsg", str(run_dir / "player_dsg.jsonl")] if a.player_dsg else []
                    watcher = subprocess.Popen([sys.executable, str(ROOT / "tools" / "m14_combat_watch.py"), str(run_dir),
                                                str(actors), str(run_dir / "watch.jsonl"), "--models", a.watch,
                                                "--radius", str(a.radius), "--seconds", str(a.seconds)] + extra,
                                               cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        finally:
            try:
                game.wait(timeout=a.seconds + 180)
            except subprocess.TimeoutExpired:
                (run_dir / "cancel.request").write_text("scenario abort\n", encoding="ascii")
                game.wait(timeout=60)
            if watcher is not None:
                try:
                    watcher.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    watcher.kill()
    row = evaluate(a.run, level, known_imports())
    result["reasons"] += row.get("reasons", [])
    rows = []
    watch = run_dir / "watch.jsonl"
    if watch.is_file():
        for line in watch.read_text(encoding="utf-8").splitlines()[1:]:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    result["expect"] = judge(expect, rows, row.get("loads", []), level)
    result["reasons"] += [f"not observed: {c}" for c, ok in result["expect"].items() if not ok]
    result["watch_rows"] = len(rows)
    result["behaviours"] = {}
    for r in rows:
        if r.get("comport"):
            names = result["behaviours"].setdefault(r["model"], [])
            if r["comport"] not in names:
                names.append(r["comport"])
    result["hit_points"] = {}
    for r in rows:
        value = hp(r.get("std"))
        if value is not None:
            series = result["hit_points"].setdefault(f"{r['model']}:{r['perso']}", [])
            if not series or series[-1][1:] != list(value):
                series.append([r["t"], *value])
    result["sweep_row"] = {k: row.get(k) for k in ("executable_sha256", "exit_code", "forced_termination",
                                                    "game_foreground_events", "loads", "stub_imports", "new_imports",
                                                    "fatal_lines", "trap_lines", "invalid_target_lines", "fault_codes",
                                                    "guest_swap", "audio_output", "xma", "perf")}
    result["pass"] = not result["reasons"]
    (WORK / f"scenario_{a.run}.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(f"M14_SCENARIO {'PASS' if result['pass'] else 'FAIL'} {a.run} level={level} expect={result['expect']} "
          f"reasons={result['reasons']}")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
