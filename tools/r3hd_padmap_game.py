#!/usr/bin/env python3
"""D-115: does a controller button map reach the game? Hidden, muted, non-activating runs only; no controller is
opened (D-053), so the map is proven through the test-only switch R3HD_PADMAP_TEST: the hidden run's scheduled pad
state (M32's keys through the real keyboard driver, tools/m32_key_test.h) is mapped by the runtime's own map
(tools/r3hd_padmap.h, from R3HD_PAD_MAP) exactly as a physical pad's state is in InputSystem::GetState.

    python tools/r3hd_padmap_game.py TAG [--case default swap control ...]

  default  no map, the original keys: M32's menu path (title -> Help & Options -> back -> New -> name -> intro movie ->
           intro_10) passes; the log says state=default.
  swap     map a=b,b=a (Jump / Confirm and Back swapped: A / Cross <-> B / Circle) with R3HD_DS_LIGHT / R3HD_DS_TRIGGER on;
           every press of A is sent as the key of B and every B as the key of A, so the path passes only if the map
           turns them back. The log says state=custom map=a=b,b=a and records mapped presses; the DualSense line is
           present (suppressed: no pad in a hidden run).
  control  the swap case's keys without a map: the path must not reach intro_10 (the test can fail).
  analog   D-116: M32's play scenario (isolated wood_10) with the triggers and the sticks exchanged
           (left_trigger=right_trigger,... left_stick=right_stick,...): every stick and trigger press is sent as the
           other one's key, so moving, the camera turn and lock-on / strafe pass only if the map exchanges them back.
  analogcontrol  the analog case's keys without a map: Rayman must not move (the camera key is the other stick's).
The map value is the resolver's for a settings file holding it, checked against play.ps1 -DryRun's controller line.
Rows: private/work/padmap/game_TAG.json. The M21 / M22 / M23 haptics judges run on every run afterwards.
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import m32_keymap_game as m32  # noqa: E402
import r3hd_settings as rs  # noqa: E402

WORK = ROOT / "private" / "work" / "padmap"


def map_value(pm, changes) -> str:
    """R3HD_PAD_MAP as a person's launch passes it: the resolver's value, and play.ps1 -DryRun's controller line."""
    reg = rs.load_registry()
    data = rs.make_settings(reg, "vanilla", controller=rs.controller_section(pm, changes))
    env = rs.resolve(reg, settings=data)["controller"]["env"]
    with tempfile.TemporaryDirectory(prefix="r3hd_padmap_game_") as tmp:
        f = Path(tmp) / "settings.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        import subprocess
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                            str(TOOLS / "play.ps1"), "-DryRun", "-BinDir", str(m32.BUILD), "-GameDir", str(m32.GAME),
                            "-SettingsFile", str(f)], capture_output=True, text=True, timeout=300)
    line = next((ln.split(":", 1)[1].strip() for ln in r.stdout.splitlines() if ln.startswith("controller :")), "")
    want = f"saved: {env}" if env else "default"
    if r.returncode != 0 or line != want:
        raise SystemExit(f"play.ps1 -DryRun controller line {line!r}, expected {want!r}")
    return env


ANALOG = {"left_trigger": "right_trigger", "right_trigger": "left_trigger", "left_stick": "right_stick",
          "right_stick": "left_stick"}


def run_analog(tag, case, eff, sc, extra, pm) -> dict:
    """D-116: the play scenario with every stick direction and trigger sent as its partner's key."""
    keys = dict(eff)
    for d in ("up", "down", "left", "right"):
        keys[f"lstick_{d}"], keys[f"rstick_{d}"] = eff[f"rstick_{d}"], eff[f"lstick_{d}"]
    keys["left_trigger"], keys["right_trigger"] = eff["right_trigger"], eff["left_trigger"]
    for k in ("R3HD_PAD_MAP", "R3HD_PADMAP_TEST"):
        os.environ.pop(k, None)
    os.environ["R3HD_PADMAP_TEST"] = "1"
    value = map_value(pm, ANALOG) if case == "analog" else ""
    if value:
        os.environ["R3HD_PAD_MAP"] = value
    try:
        row = m32.play(f"{tag}{case}", keys, sc, extra)
    finally:
        for k in ("R3HD_PAD_MAP", "R3HD_PADMAP_TEST"):
            os.environ.pop(k, None)
    text = m32.runtime_log(m32.RUNS / row["run"])
    state = re.search(r"R3HD padmap state=(\w+) map=(\S+) error=(.*)", text)
    row.update(case=case, pad_map=value or None, padmap_line=state.group(0).strip() if state else None,
               play_pass=row.pop("pass"))
    if case == "analog":
        row["pass"] = bool(row["play_pass"] and state and state.group(1) == "custom" and state.group(2) == value)
    else:
        row["pass"] = bool(state and state.group(1) == "default" and not row.get("moves"))
    return row


def run_case(tag, case, eff, sc, extra, pm) -> dict:
    keys = dict(eff)
    for k in ("R3HD_PAD_MAP", "R3HD_PADMAP_TEST", "R3HD_DS_LIGHT", "R3HD_DS_TRIGGER"):
        os.environ.pop(k, None)
    os.environ["R3HD_PADMAP_TEST"] = "1"
    value = ""
    if case in ("swap", "control"):
        keys["a"], keys["b"] = eff["b"], eff["a"]  # press the physical button the map gives each guest input
    if case == "swap":
        value = map_value(pm, {"a": "b", "b": "a"})
        os.environ["R3HD_PAD_MAP"] = value
        os.environ.update(R3HD_DS_LIGHT="on", R3HD_DS_TRIGGER="on")
    try:
        row = m32.menu(f"{tag}{case}", keys, sc, extra)
    finally:
        for k in ("R3HD_PAD_MAP", "R3HD_PADMAP_TEST", "R3HD_DS_LIGHT", "R3HD_DS_TRIGGER"):
            os.environ.pop(k, None)
    text = m32.runtime_log(m32.RUNS / row["run"])
    state = re.search(r"R3HD padmap state=(\w+) map=(\S+) error=(.*)", text)
    row.update(case=case, pad_map=value or None, keys_sent={"a": keys["a"][0], "b": keys["b"][0]},
               padmap_line=state.group(0).strip() if state else None,
               mapped_presses=re.findall(r"R3HD padmap_test buttons=([0-9A-F]{4}) mapped=([0-9A-F]{4})", text)[:12],
               dualsense_line=next((ln.split("R3HD dualsense ", 1)[1] for ln in text.splitlines()
                                    if "R3HD dualsense light=" in ln), None))
    reached = row["intro_10_loaded"] and row["exit_code"] == 0
    if case == "default":
        row["pass"] = reached and bool(state) and state.group(1) == "default"
    elif case == "swap":
        swapped = ("2000", "1000") in row["mapped_presses"] and ("1000", "2000") in row["mapped_presses"]
        row["pass"] = (reached and bool(state) and state.group(1) == "custom" and state.group(2) == "a=b,b=a"
                       and swapped and (row["dualsense_line"] or "").startswith("light=on trigger=on policy=suppressed"))
    else:
        row["pass"] = not row["intro_10_loaded"] and bool(state) and state.group(1) == "default"
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--case", nargs="*", choices=["default", "swap", "control", "analog", "analogcontrol"],
                    default=["default", "swap", "control", "analog", "analogcontrol"])
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9]+", a.tag):
        ap.error("TAG: letters and digits")
    km = rs.load_keymap()
    pm = rs.load_padmap(km)
    extra, keyboard = m32.launch_args(km, "modern", {})
    eff = rs.resolve_keyboard(km)["effective"]
    sc = m32.sdl_scancodes(km)
    rows = []
    for case in a.case:
        rows.append((run_analog if case.startswith("analog") else run_case)(a.tag, case, eff, sc, extra, pm))
        time.sleep(3)
    for row in rows:
        row["judges"] = m32.judges(row["run"])
        print(f"PADMAP_GAME {row['case']} {row['run']} pass={row['pass']} " + json.dumps(
            {k: row.get(k) for k in ("pad_map", "keys_sent", "padmap_line", "mapped_presses", "dualsense_line",
                                     "intro_movie_opened", "intro_10_loaded", "moves", "jumps", "camera_turns",
                                     "lock_strafes", "lock_strafe_comport", "play_pass", "exit_code")}), flush=True)
        print("  judges: " + " | ".join(row["judges"].values()), flush=True)
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / f"game_{a.tag}.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    ok = all(r["pass"] for r in rows) and all("PASS" in j for r in rows for j in r["judges"].values())
    print(f"R3HD_PADMAP_GAME {'PASS' if ok else 'FAIL'} {sum(r['pass'] for r in rows)}/{len(rows)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
