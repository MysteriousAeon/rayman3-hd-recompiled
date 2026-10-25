#!/usr/bin/env python3
"""M49 (D-088): Rayman's ground speed against the left stick's length, and the keyboard Walk key in the game.
Hidden, muted, non-activating runs in the isolated test-only level wood_10 only (D-040: not progression; D-053: no
physical controller). Guest state is only read (m7_live_status.py through m13_control_check.status).

    python tools/m49_walk_game.py TAG [--scenario curve keys] [--magnitudes 0.15,0.3,...]

  curve  the scoped XAM schedule holds the left stick forward at each length (a fraction of full deflection) for
         HOLD seconds, then back to the start: speed = distance / time over the steady part of the forward hold, and
         the behaviours seen (YAM_C_Course ...). This is the title's own response to an analog stick, the evidence
         for the Walk key's length. Run m49_walk_game_curve.
  keys   the real keyboard driver with the Modern map's arguments (R3HD_KEYMAP_TEST=1, scheduled SDL scancodes, as
         tools/m32_keymap_game.py): W alone, Ctrl+W, Ctrl+W+D (diagonal), W with Ctrl pressed and released while
         moving, and a jump while walking. Run m49_walk_game_keys.
Rows: private/work/m49/walk_TAG.json. The M21 / M22 / M23 haptics judges are run on each run afterwards.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import r3hd_settings as rs  # noqa: E402
from m13_control_check import status  # noqa: E402
import m32_keymap_game as kg  # noqa: E402

RUNS = ROOT / "private" / "work" / "m6_runs"
WORK = ROOT / "private" / "work" / "m49"
LEVEL = "wood_10"
HOLD = 3.0


def start(run, seconds, extra, keymap_test):
    WORK.mkdir(parents=True, exist_ok=True)
    steps = WORK / f"steps_{run}.txt"
    steps.write_text(f"wait {seconds - 8}\n", encoding="ascii")
    env = dict(os.environ, R3HD_HIDDEN_EXTRA=",".join(extra))
    env.pop("R3HD_KEYMAP_TEST", None)
    if keymap_test:
        env["R3HD_KEYMAP_TEST"] = "1"
    cmd = [sys.executable, str(TOOLS / "m9_license_run.py"), run, str(steps), "--license-mask", "1", "--seconds",
           str(seconds), "--play", "--test-level", LEVEL]
    log = (WORK / f"{run}.driver.log").open("w")
    return subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env), log


def wait_level(proc, run_dir, settle) -> str:
    needle = re.compile(rf"[\\/]{LEVEL}\.lvl result=00000000", re.IGNORECASE)
    end = time.monotonic() + 90
    while time.monotonic() < end and proc.poll() is None:
        if (run_dir / "runtime.log").is_file() and needle.search((run_dir / "runtime.log").read_text(errors="replace")):
            break
        time.sleep(1)
    else:
        return "level did not open"
    time.sleep(settle)
    base = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", (run_dir / "runtime.log").read_text(errors="replace"))
    pid = json.loads((run_dir / "process.json").read_text(encoding="utf-8-sig"))["pid"]
    probe = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base.group(1) if base else "0",
                            str(run_dir / f"actors_{LEVEL}.json"), "--regions"], cwd=ROOT, capture_output=True,
                           text=True, timeout=120)
    if probe.returncode != 0:
        return "actor discovery failed: " + probe.stderr.strip()[-200:]
    return ""


def sample(run_dir):
    t = time.monotonic()
    rows = status(run_dir, LEVEL, 1)
    return (t + time.monotonic()) / 2, (rows[-1] if rows else None)


def segment(run_dir, begin, end_, hold=HOLD):
    """begin() starts the input; speed over the steady part (from 1 s after the start to the end of the hold)."""
    begin()
    t_start = time.monotonic()
    seen = set()
    time.sleep(1.0)
    t0, r0 = sample(run_dir)
    while time.monotonic() - t_start < hold - 0.4:
        _, r = sample(run_dir)
        if r:
            seen.add(r["comport"])
    t1, r1 = sample(run_dir)
    end_()
    if not (r0 and r1):
        return {"error": "no player sample"}
    seen |= {r0["comport"], r1["comport"]}
    d = math.dist(r0["rayman"][:2], r1["rayman"][:2])
    return {"speed": round(d / (t1 - t0), 3), "distance": round(d, 3), "seconds": round(t1 - t0, 2),
            "comports": sorted(seen)}


def curve(tag, magnitudes, settle=25) -> dict:
    run = f"m49_walk_{tag}_curve"
    run_dir = RUNS / run
    seconds = settle + 20 + len(magnitudes) * 10
    proc, log = start(run, seconds, [], keymap_test=False)
    row = {"run": run, "scenario": "curve", "level": LEVEL, "entry": "isolated test-only (-level:)", "points": []}

    def axis(v):
        with (run_dir / "schedule.txt").open("a", encoding="ascii", newline="") as s:
            s.write(f"0 301 {int(v)}\n")
    try:
        err = wait_level(proc, run_dir, settle)
        if err:
            row["error"] = err
            return row
        for m in magnitudes:
            v = round(m * 32767)
            fwd = segment(run_dir, lambda: axis(v), lambda: axis(0))
            time.sleep(1.2)
            back = segment(run_dir, lambda: axis(-v), lambda: axis(0))
            time.sleep(1.2)
            row["points"].append({"magnitude": m, "value": v, "forward": fwd, "back": back})
            print(f"  curve {m:.2f}: forward {fwd.get('speed')} {fwd.get('comports')} back {back.get('speed')}", flush=True)
    finally:
        row.update(kg.finish(proc, log, run_dir, seconds))
    full = next((p["forward"].get("speed") for p in row["points"] if p["magnitude"] == 1.0), None)
    for p in row["points"]:
        s = p["forward"].get("speed")
        p["ratio_to_full"] = round(s / full, 3) if full and s is not None else None
    row["pass"] = row.get("exit_code") == 0 and bool(full) and not row.get("error")
    return row


def keys(tag, settle=25) -> dict:
    km = rs.load_keymap()
    kb = rs.resolve_keyboard(km, {"layout": "modern"})
    extra = [a for a in kb["args"] if a.startswith(("--keybind_", "--mnk_"))]
    eff, sc = kb["effective"], kg.sdl_scancodes(km)
    run = f"m49_walk_{tag}_keys"
    run_dir = RUNS / run
    seconds = settle + 80
    proc, log = start(run, seconds, extra, keymap_test=True)
    W, S, D, A_, WALK, JUMP = (eff["lstick_up"][0], eff["lstick_down"][0], eff["lstick_right"][0], eff["lstick_left"][0],
                               eff["walk"][0], eff["a"][0])
    row = {"run": run, "scenario": "keys", "level": LEVEL, "entry": "isolated test-only (-level:)",
           "keys": {"forward": W, "walk": WALK, "jump": JUMP}, "magnitude": km["walk_magnitude"]}

    def key(name, down):
        with (run_dir / "schedule.txt").open("a", encoding="ascii", newline="") as s:
            s.write(f"0 {sc[name]} {int(down)}\n")

    def keys_(names, down):
        return lambda: [key(n, down) for n in names]
    try:
        err = wait_level(proc, run_dir, settle)
        if err:
            row["error"] = err
            return row
        row["run_forward"] = segment(run_dir, keys_([W], True), keys_([W], False))
        time.sleep(1.2)
        segment(run_dir, keys_([S], True), keys_([S], False))  # back to the start
        time.sleep(1.2)
        row["walk_forward"] = segment(run_dir, keys_([WALK, W], True), keys_([W, WALK], False))
        time.sleep(1.2)
        row["walk_back"] = segment(run_dir, keys_([WALK, S], True), keys_([S, WALK], False))
        time.sleep(1.2)
        row["walk_diagonal"] = segment(run_dir, keys_([WALK, W, D], True), keys_([W, D, WALK], False))
        time.sleep(1.2)
        row["walk_diagonal_back"] = segment(run_dir, keys_([WALK, S, A_], True), keys_([S, A_, WALK], False))
        time.sleep(1.2)
        # transitions: running, then Walk pressed while moving, then released while moving
        key(W, True)
        time.sleep(1.5)
        row["transition_walk_pressed"] = segment(run_dir, lambda: key(WALK, True), lambda: None, hold=2.5)
        row["transition_walk_released"] = segment(run_dir, lambda: key(WALK, False), lambda: key(W, False), hold=2.5)
        time.sleep(1.5)
        # a jump while walking
        key(WALK, True)
        key(S, True)
        time.sleep(1.2)
        _, before = sample(run_dir)
        key(JUMP, True)
        time.sleep(0.25)
        key(JUMP, False)
        jump = status(run_dir, LEVEL, 4)
        key(S, False)
        key(WALK, False)
        if before and jump:
            row["jump_while_walking_rise"] = round(max(r["rayman"][2] for r in jump) - before["rayman"][2], 3)
            row["jump_comports"] = sorted({r["comport"] for r in jump})
    finally:
        row.update(kg.finish(proc, log, run_dir, seconds))
    text = kg.runtime_log(run_dir)
    row["walk_line"] = next((ln.split("M49 keyboard ", 1)[1].strip() for ln in text.splitlines() if "M49 keyboard walk=" in ln), None)
    rf, wf = (row.get(k, {}).get("speed") for k in ("run_forward", "walk_forward"))
    # open-loop terrain: one diagonal can meet an obstacle (w1: 0.12 forward, 2.4 back); the driver's exact diagonal
    # length is m49_regression.py's, so the game check takes the better of the two diagonal segments
    wd = max((row.get(k, {}).get("speed") or 0) for k in ("walk_diagonal", "walk_diagonal_back")) or None
    tp, tr = (row.get(k, {}).get("speed") for k in ("transition_walk_pressed", "transition_walk_released"))
    row["walk_to_run"] = round(wf / rf, 3) if rf and wf else None
    row["diagonal_to_straight"] = round(wd / wf, 3) if wf and wd else None
    row["pass"] = bool(row.get("exit_code") == 0 and rf and wf and wd and tp and tr and wf < 0.85 * rf
                       and 0.8 <= wd / wf <= 1.2 and tr > tp * 1.2 and (row.get("jump_while_walking_rise") or 0) > 1.0
                       and row["walk_line"])
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--scenario", nargs="*", choices=["curve", "keys"], default=["curve", "keys"])
    ap.add_argument("--magnitudes", default="0.15,0.25,0.35,0.45,0.55,0.65,0.8,1.0")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9]+", a.tag):
        ap.error("TAG: letters and digits")
    rows = []
    if "curve" in a.scenario:
        rows.append(curve(a.tag, [float(x) for x in a.magnitudes.split(",")]))
        time.sleep(3)
    if "keys" in a.scenario:
        rows.append(keys(a.tag))
    for row in rows:
        row["judges"] = kg.judges(row["run"])
        print(f"M49_WALK {row['scenario']} {row['run']} pass={row['pass']} "
              + json.dumps({k: v for k, v in row.items() if k not in ("points", "judges")}), flush=True)
        print("  judges: " + " | ".join(row["judges"].values()), flush=True)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / f"walk_{a.tag}.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    ok = all(r["pass"] for r in rows)
    print(f"M49_WALK_GAME {'PASS' if ok else 'FAIL'} {sum(r['pass'] for r in rows)}/{len(rows)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
