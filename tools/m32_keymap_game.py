#!/usr/bin/env python3
"""M32 (D-069): does a keyboard map reach the game? Hidden, muted, non-activating runs only.

    python tools/m32_keymap_game.py TAG [--layout L] [--key INPUT=KEY[,KEY] ...] [--scenario menu|play|both]

The keybind_* arguments are taken from tools/play.ps1 -DryRun for a settings file holding the map (the arguments a
person's launch passes), then given to a hidden run (R3HD_HIDDEN_EXTRA) with R3HD_KEYMAP_TEST=1: the scheduled keys
(SDL scancodes of the map's own keys) go through the runtime's SDL translation and a window-less instance of the real
keyboard driver, whose pad state the title reads through XamInputGetState (tools/m32_key_test.h). Nothing reaches the
desktop, no physical controller is opened, the run is muted (D-023, D-051, D-053).

  menu  title -> Start -> down, down -> A (Help & Options) -> B (the main menu; its cursor is back on New) -> down
        (Load) -> up (New) -> A -> A (name) -> the intro movie opens -> Start skips it -> intro_10 loads. Only reached
        when Start, both stick directions, A and B all work (B must leave the submenu, else New is never chosen).
        Fresh isolated profile; two private frames.
  play  isolated test-only level wood_10 (D-040; not progression): idle, move forward (displacement), jump (rise),
        turn the camera (camera angle around Rayman), hold attack (behaviour), hold lock-on while moving, pause with
        Start (holding forward moves nothing), resume with A, move again; with --old-key KEY also a key that is no
        longer bound (no change expected).
Rows: private/work/m32/game_TAG.json. Judges: the M21 / M22 / M23 haptics regressions are run on each run afterwards.
"""
import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import r3hd_settings as rs  # noqa: E402
from m13_control_check import status  # noqa: E402

RUNS = ROOT / "private" / "work" / "m6_runs"
WORK = ROOT / "private" / "work" / "m32"
BUILD = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
GAME = ROOT / "private" / "extracted" / "5841123F"
SDL = ROOT / "external" / "rexglue-sdk" / "thirdparty" / "sdl3"


def sdl_scancodes(km) -> dict:
    """Key name -> the SDL scancode the window gives for its first scan code."""
    num = {m[0]: int(m[1]) for m in re.findall(r"\b(SDL_SCANCODE_\w+)\s*=\s*(\d+)", (SDL / "include/SDL3/SDL_scancode.h").read_text())}
    table = re.findall(r"/\*0x[0-9a-fA-F]+\*/\s*(SDL_SCANCODE_\w+)", (SDL / "src/events/scancodes_windows.h").read_text())
    out = {}
    for k in km["keys"]:
        s = k["scan"][0]
        out[k["name"]] = num[table[int(s[-2:], 16) | (0x80 if len(s) == 4 else 0)]]
    return out


def launch_args(km, layout, changes) -> tuple:
    """play.ps1 -DryRun with a settings file holding the map: the keybind arguments and the keyboard line."""
    with tempfile.TemporaryDirectory(prefix="r3hd_m32_game_") as tmp:
        f = Path(tmp) / "settings.json"
        data = rs.make_settings(rs.load_registry(), "vanilla", keyboard=rs.keyboard_section(km, layout, changes))
        f.write_text(json.dumps(data), encoding="utf-8")
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                            str(TOOLS / "play.ps1"), "-DryRun", "-BinDir", str(BUILD), "-GameDir", str(GAME),
                            "-SettingsFile", str(f)], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise SystemExit(f"play.ps1 -DryRun failed: {r.stdout[-400:]} {r.stderr[-400:]}")
    argv = [line.split(":", 1)[1].strip() for line in r.stdout.splitlines() if line.startswith("argument   :")]
    keyboard = next(line.split(":", 1)[1].strip() for line in r.stdout.splitlines() if line.startswith("keyboard   :"))
    return [a for a in argv if a.startswith(("--keybind_", "--mnk_modifier_keys", "--mnk_walk_magnitude"))], keyboard


def judges(run: str) -> dict:
    out = {}
    for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True, text=True,
                           timeout=600)
        out[tool] = (r.stdout.strip().splitlines() or [""])[-1]
    return out


def start(run, steps_text, seconds, extra, test_level=None, user_root=None):
    WORK.mkdir(parents=True, exist_ok=True)
    steps = WORK / f"steps_{run}.txt"
    steps.write_text(steps_text, encoding="ascii")
    env = dict(__import__("os").environ, R3HD_KEYMAP_TEST="1", R3HD_HIDDEN_EXTRA=",".join(extra))
    cmd = [sys.executable, str(TOOLS / "m9_license_run.py"), run, str(steps), "--license-mask", "1", "--seconds",
           str(seconds), "--play"]
    if test_level:
        cmd += ["--test-level", test_level]
    if user_root:
        cmd += ["--user-root", user_root]
    log = (WORK / f"{run}.driver.log").open("w")
    return subprocess.Popen(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=env), log


def finish(proc, log, run_dir, seconds):
    try:
        proc.wait(timeout=seconds + 180)
    except subprocess.TimeoutExpired:
        (run_dir / "cancel.request").write_text("m32 abort\n", encoding="ascii")
        proc.wait(timeout=60)
    log.close()
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8-sig")) if (run_dir / "run.json").is_file() else {}
    return {"exit_code": meta.get("exit_code"), "forced_termination": meta.get("forced_termination"),
            "game_foreground_events": meta.get("game_foreground_events")}


def runtime_log(run_dir: Path) -> str:
    return "\n".join(p.read_text(errors="replace") for p in sorted(run_dir.glob("runtime*.log")))


def menu(tag, eff, sc, extra) -> dict:
    """The new-game path through the menus, every step with the map's own first keys."""
    run = f"m32_{tag}_menu"

    def press(i, hold=0.3):
        return f"press {sc[eff[i][0]]} {hold}\n"
    text = ("log VIDEOS\\ubi.bik result=00000000\nlog menumap\\menumap.lvl result=00000000\nwait 10\n" + press("start")
            + "wait 12\n" + press("lstick_down") + "wait 1.5\n" + press("lstick_down") + "wait 2\n" + press("a")
            + "wait 6\nframe submenu\n" + press("b") + "wait 6\n" + press("lstick_down") + "wait 1.5\n"
            + press("lstick_up") + "wait 2\nframe on_new\n" + press("a") + "wait 8\n" + press("a")
            + "log VIDEOS\\intro.bik result=00000000 40\nwait 3\n" + press("start")
            + "log intro_10\\intro_10.lvl result=00000000 60\nwait 5\n")
    run_dir = RUNS / run
    proc, log = start(run, text, 180, extra, user_root=f"m32_{tag}_menu")
    row = {"run": run, "scenario": "menu", "keys": {i: eff[i][0] for i in ("start", "lstick_down", "lstick_up", "a", "b")}}
    row.update(finish(proc, log, run_dir, 180))
    text_log = runtime_log(run_dir)
    row["intro_movie_opened"] = "intro.bik result=00000000" in text_log
    row["intro_10_loaded"] = "intro_10.lvl result=00000000" in text_log
    row["driver_pad_lines"] = text_log.count("M32 keymap_test pad ")
    row["keyboard_line"] = next((line.split("M32 keyboard ", 1)[1] for line in text_log.splitlines()
                                 if "M32 keyboard test_instance=true" in line), None)
    row["pass"] = bool(row["intro_movie_opened"] and row["intro_10_loaded"] and row["exit_code"] == 0)
    return row


def near(run_dir: Path, level: str, radius: float = 60.0) -> list:
    """Actors near Rayman (m7_live_status.py --near; read only)."""
    done = subprocess.run([sys.executable, str(TOOLS / "m7_live_status.py"), str(run_dir), "--level", level, "--near",
                           str(radius)], cwd=ROOT, capture_output=True, text=True, timeout=60)
    for line in done.stdout.splitlines():
        try:
            return json.loads(line).get("near", [])
        except ValueError:
            pass
    return []


def play(tag, eff, sc, extra, old_key=None, settle=25) -> dict:
    run, level = f"m32_{tag}_play", "wood_10"
    run_dir = RUNS / run
    seconds = settle + 85
    proc, log = start(run, f"wait {seconds - 8}\n", seconds, extra, test_level=level)
    # The pause menu's words (M18 watch, read only) beside the run.
    watch_out = WORK / f"{run}_menu_watch.jsonl"
    watcher = subprocess.Popen([sys.executable, str(TOOLS / "m18_progress_watch.py"), str(run_dir), str(watch_out),
                                "--seconds", str(seconds + 30), "--interval", "0.05"], cwd=ROOT,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    row = {"run": run, "scenario": "play", "level": level, "entry": "isolated test-only (-level:)",
           "keys": {i: eff[i][0] for i in ("lstick_up", "a", "rstick_left", "x", "right_trigger", "lstick_right", "start")}}

    def key(name, down):
        with (run_dir / "schedule.txt").open("a", encoding="ascii", newline="") as s:
            s.write(f"0 {sc[name]} {int(down)}\n")

    def hold(names, seconds_):
        for n in names:
            key(n, True)
        time.sleep(seconds_)
        mid = status(run_dir, level, 1)
        for n in names:
            key(n, False)
        return mid

    def tap(name):
        key(name, True)
        time.sleep(0.25)
        key(name, False)

    def pos(rows):
        return rows[-1]["rayman"] if rows else None

    def cam_angle(r):
        return math.degrees(math.atan2(r["camera"][1] - r["rayman"][1], r["camera"][0] - r["rayman"][0])) if r.get("camera") else None
    try:
        needle = re.compile(rf"[\\/]{level}\.lvl result=00000000", re.IGNORECASE)
        end = time.monotonic() + 90
        while time.monotonic() < end and proc.poll() is None:
            if (run_dir / "runtime.log").is_file() and needle.search((run_dir / "runtime.log").read_text(errors="replace")):
                break
            time.sleep(1)
        else:
            row["error"], row["pass"] = "level did not open", False
            return row
        time.sleep(settle)
        # Read-only actor discovery first (as m13_control_check.py does); the status reads use its result.
        base = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", (run_dir / "runtime.log").read_text(errors="replace"))
        pid = json.loads((run_dir / "process.json").read_text(encoding="utf-8-sig"))["pid"]
        probe = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base.group(1) if base else "0",
                                str(run_dir / f"actors_{level}.json"), "--regions"], cwd=ROOT, capture_output=True,
                               text=True, timeout=120)
        if probe.returncode != 0:
            row["error"], row["pass"] = "actor discovery failed: " + probe.stderr.strip()[-200:], False
            return row
        idle = status(run_dir, level, 3)
        if not idle:
            row["error"], row["pass"] = "no player actor", False
            return row
        row["idle_comport"] = sorted({r["comport"] for r in idle})
        row["idle_drift"] = round(math.dist(idle[0]["rayman"], idle[-1]["rayman"]), 3)
        hold([eff["lstick_up"][0]], 3.0)
        time.sleep(0.5)
        moved = status(run_dir, level, 1)
        row["move_displacement"] = round(math.dist(pos(idle), pos(moved)), 3)
        tap(eff["a"][0])
        jump = status(run_dir, level, 4)
        row["jump_max_rise"] = round(max(r["rayman"][2] for r in jump) - pos(moved)[2], 3)
        row["jump_comport"] = sorted({r["comport"] for r in jump})
        time.sleep(2.5)
        before = status(run_dir, level, 1)[-1]
        hold([eff["rstick_left"][0]], 2.0)
        time.sleep(0.5)
        after = status(run_dir, level, 1)[-1]
        a0, a1 = cam_angle(before), cam_angle(after)
        row["camera_turn_deg"] = round(((a1 - a0 + 180) % 360) - 180, 1) if a0 is not None and a1 is not None else None
        # Attack: the fist is an actor of its own (RE_NOTES "M14"); a throw moves an actor away from Rayman.
        n0 = {a["so"]: a for a in near(run_dir, level)}
        tap(eff["x"][0])
        time.sleep(0.15)
        n1 = {a["so"]: a for a in near(run_dir, level)}
        flew = [{"model": n1[k]["model"], "moved": round(math.dist(n0[k]["pos"], n1[k]["pos"]), 1)}
                for k in n1 if k in n0 and math.dist(n0[k]["pos"], n1[k]["pos"]) > 2.0]
        row["attack_moved_actors"] = flew
        time.sleep(1.5)
        charge = hold([eff["x"][0]], 1.2)
        time.sleep(0.4)
        row["attack_hold_comport"] = sorted({r["comport"] for r in charge})
        time.sleep(1.5)
        p0 = status(run_dir, level, 1)
        lock = hold([eff["right_trigger"][0], eff["lstick_right"][0]], 1.5)
        time.sleep(0.4)
        p1 = status(run_dir, level, 1)
        row["lock_strafe_comport"] = sorted({r["comport"] for r in lock})
        row["lock_strafe_displacement"] = round(math.dist(pos(p0), pos(p1)), 3)
        time.sleep(1.5)
        if old_key:
            o0 = status(run_dir, level, 1)
            m0 = {x["so"]: x for x in near(run_dir, level)}
            tap(old_key)
            time.sleep(0.15)
            m1 = {x["so"]: x for x in near(run_dir, level)}
            o1 = status(run_dir, level, 2)
            row["old_key"] = old_key
            row["old_key_comport"] = sorted({r["comport"] for r in o1})
            row["old_key_displacement"] = round(math.dist(pos(o0), pos(o1)), 3)
            row["old_key_moved_actors"] = [m1[k]["model"] for k in m1 if k in m0 and math.dist(m0[k]["pos"], m1[k]["pos"]) > 2.0]
            time.sleep(1.0)
        # Pause: the pause menu's words change (M18 watch) and the world is frozen: a held camera key turns nothing
        # (the left stick would move the menu's cursor off Resume Game). A on Resume Game, then the player moves.
        row["pause_wall"] = time.time()
        tap(eff["start"][0])
        time.sleep(2.5)
        q0 = status(run_dir, level, 1)[-1]
        hold([eff["rstick_left"][0]], 2.0)
        time.sleep(0.4)
        q1 = status(run_dir, level, 1)[-1]
        c0, c1 = cam_angle(q0), cam_angle(q1)
        row["paused_camera_turn_deg"] = round(((c1 - c0 + 180) % 360) - 180, 1) if c0 is not None and c1 is not None else None
        row["paused_displacement"] = round(math.dist(q0["rayman"], q1["rayman"]), 3)
        row["resume_wall"] = time.time()
        tap(eff["a"][0])
        time.sleep(3.0)
        r0 = status(run_dir, level, 1)
        hold([eff["lstick_up"][0]], 2.0)
        time.sleep(0.4)
        r1 = status(run_dir, level, 1)
        row["resumed_displacement"] = round(math.dist(pos(r0), pos(r1)), 3)
    finally:
        row.update(finish(proc, log, run_dir, seconds))
        try:
            watcher.wait(timeout=60)
        except subprocess.TimeoutExpired:
            watcher.kill()  # the watcher this function started, by its own handle
        text_log = runtime_log(run_dir)
        row["driver_pad_lines"] = text_log.count("M32 keymap_test pad ")
        row["rt_seen_by_driver"] = bool(re.search(r"M32 keymap_test pad buttons=\w+ lt=\d+ rt=255", text_log))
        row["keyboard_line"] = next((line.split("M32 keyboard ", 1)[1] for line in text_log.splitlines()
                                     if "M32 keyboard test_instance=true" in line), None)
    drift = row.get("idle_drift", 0) or 0
    row["moves"] = (row.get("move_displacement") or 0) - 3 * drift > 1.0
    row["jumps"] = (row.get("jump_max_rise") or 0) > 1.0
    row["camera_turns"] = abs(row.get("camera_turn_deg") or 0) > 10
    row["attack_throws"] = bool(row.get("attack_moved_actors"))
    row["pause_freezes_camera"] = (row.get("paused_camera_turn_deg") is not None and abs(row["paused_camera_turn_deg"]) < 2
                                   and row.get("paused_displacement", 99) < 0.5)
    menu_changes = []
    if watch_out.is_file():
        for line in watch_out.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if row.get("pause_wall", 1e18) <= rec.get("wall", 0) and any(k in rec for k in ("page", "menu_state", "menu_mode")):
                menu_changes.append({k: rec[k] for k in ("wall", "page", "menu_state", "menu_mode") if k in rec})
    row["menu_word_changes"] = menu_changes[:8]
    row["pause_menu_opened"] = any(c["wall"] < row.get("resume_wall", 0) for c in menu_changes)
    row["pause_menu_closed"] = any(c["wall"] >= row.get("resume_wall", 1e18) for c in menu_changes)
    row["resume_moves"] = (row.get("resumed_displacement") or 0) > 1.0
    if old_key:
        row["old_key_inert"] = (row.get("old_key_displacement", 99) < 0.5 and not row.get("old_key_moved_actors")
                                and not set(row.get("old_key_comport", [])) - set(row.get("idle_comport", [])))
    row["lock_strafes"] = any("Strafe" in c for c in row.get("lock_strafe_comport", []))
    # Attack is judged by the combat scenario (a fist's flight is too short for these one-second probes); the
    # attack and menu-close observations here are recorded only.
    need = ["lock_strafes", "moves", "jumps", "camera_turns", "pause_freezes_camera", "pause_menu_opened", "resume_moves"]
    need += ["old_key_inert"] if old_key else []
    row["pass"] = all(row.get(k) for k in need) and row.get("exit_code") == 0
    return row


HOODLUM = "YAM_M_CagouSnipeBase"


def combat(tag, eff, sc, extra) -> dict:
    """M14's curve_defeat scenario (knaar_69: lock on, strafe, fists until the hoodlum is defeated), its step file
    translated from M14's fixed test codes (15 = X, 8 = right trigger, 300 = left stick x) into this map's keys."""
    run = f"m32_{tag}_combat"
    out = []
    for raw in (ROOT / "config" / "m14" / "k69_curve.txt").read_text().splitlines():
        f = raw.split("#", 1)[0].split()
        if not f:
            continue
        if f[0] == "press" and f[1] == "15":
            out.append(f"press {sc[eff['x'][0]]} {f[2] if len(f) > 2 else '0.2'}")
        elif f[0] == "axis" and f[1] == "8":
            out.append(f"axis {sc[eff['right_trigger'][0]]} {1 if int(f[2]) else 0}")
        elif f[0] == "axis" and f[1] == "300":
            v = int(f[2])
            out.append(f"axis {sc[eff['lstick_right'][0]]} {1 if v > 0 else 0}")
            out.append(f"axis {sc[eff['lstick_left'][0]]} {1 if v < 0 else 0}")
        elif f[0] == "wait":
            out.append(" ".join(f))
        else:
            raise SystemExit(f"untranslated step: {raw}")
    steps = WORK / f"steps_{run}.txt"
    steps.write_text("# M32: config/m14/k69_curve.txt in this map's keys\n" + "\n".join(out) + "\n", encoding="ascii")
    env = dict(__import__("os").environ, R3HD_KEYMAP_TEST="1", R3HD_HIDDEN_EXTRA=",".join(extra))
    expect = f"player:StrafeMode,actor:{HOODLUM}:4Paf,actor:{HOODLUM}:5Mort,hp:{HOODLUM}"
    r = subprocess.run([sys.executable, str(TOOLS / "m14_scenario.py"), run, "knaar_69", str(steps), "--seconds", "62",
                        "--settle", "6", "--watch", HOODLUM, "--expect", expect], cwd=ROOT, capture_output=True,
                       text=True, env=env, timeout=900)
    text_log = runtime_log(RUNS / run)
    row = {"run": run, "scenario": "combat", "level": "knaar_69", "entry": "isolated test-only (-level:)",
           "keys": {i: eff[i][0] for i in ("x", "right_trigger", "lstick_left", "lstick_right")}, "expect": expect,
           "m14_result": (r.stdout.strip().splitlines() or [""])[-1][:400],
           "driver_pad_lines": text_log.count("M32 keymap_test pad ")}
    row["pass"] = r.returncode == 0 and "M14_SCENARIO PASS" in r.stdout
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--layout", default="modern")
    ap.add_argument("--key", nargs="*", default=[])
    ap.add_argument("--scenario", nargs="*", choices=["menu", "play", "combat"], default=["menu", "play", "combat"])
    ap.add_argument("--old-key", help="play: a key that the map no longer binds (nothing may happen)")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9]+", a.tag):
        ap.error("TAG: letters and digits")
    km = rs.load_keymap()
    changes = rs.parse_key_pairs(a.key)
    extra, keyboard = launch_args(km, a.layout, changes)
    eff = rs.resolve_keyboard(km, rs.keyboard_section(km, a.layout, changes))["effective"]
    sc = sdl_scancodes(km)
    rows = []
    if "menu" in a.scenario:
        rows.append(menu(a.tag, eff, sc, extra))
        time.sleep(3)
    if "play" in a.scenario:
        rows.append(play(a.tag, eff, sc, extra, a.old_key))
        time.sleep(3)
    if "combat" in a.scenario:
        rows.append(combat(a.tag, eff, sc, extra))
    for row in rows:
        row["layout"], row["changes"], row["launch_keyboard"], row["launch_args"] = a.layout, changes, keyboard, extra
        row["judges"] = judges(row["run"])
        print(f"M32_GAME {row['scenario']} {row['run']} pass={row['pass']} " + json.dumps(
            {k: v for k, v in row.items() if k not in ("launch_args", "keyboard_line", "judges")}), flush=True)
        print("  judges: " + " | ".join(row["judges"].values()), flush=True)
    out = WORK / f"game_{a.tag}.json"
    out.write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    return 0 if all(r["pass"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
