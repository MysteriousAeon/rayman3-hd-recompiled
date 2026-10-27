#!/usr/bin/env python3
"""D-116: what do the pad buttons the keymap calls "not yet characterised" do in the game? Hidden, muted,
non-activating runs only (D-023, D-051, D-053); no controller is opened: every press is M32's scheduled key through the
real keyboard driver (tools/m32_key_test.h), which the title reads as the pad input that key is bound to.

    python tools/r3hd_pad_inventory_game.py TAG [--scenario menu play both]

  menu  M32's new-game path (title -> Help & Options -> back -> New -> name -> intro_10) with the D-pad instead of the
        left stick for every up / down move: it reaches intro_10 only if the D-pad moves the menus' cursor.
  play  isolated test-only wood_10 (D-040): for Y, LB, RB, Back, the four D-pad directions, L3 and R3 one tap and one
        1.5 s hold each, recording the player's behaviours beyond idle, displacement, jump rise, the camera's angle and
        height around Rayman, actors moved near him and the menu words (M18 watch); then the pause menu (Start) and,
        inside it, a tap of each of those buttons (Y last; the left stick down / up as the cursor's control) with the
        menu words recorded. --pause-only skips the gameplay taps.
Rows: private/work/padinv/game_TAG.json. Nothing is judged PASS / FAIL: the rows are observations (RE_NOTES D-116).
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
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import m32_keymap_game as m32  # noqa: E402
import r3hd_settings as rs  # noqa: E402
from m13_control_check import status  # noqa: E402

WORK = ROOT / "private" / "work" / "padinv"
PROBED = ["y", "left_shoulder", "right_shoulder", "back", "dpad_up", "dpad_down", "dpad_left", "dpad_right",
          "lstick_press", "rstick_press"]
MENU_WORDS = ("page", "cursor", "pages", "menu_mode", "menu_state")


def menu_dpad(tag, eff, sc, extra) -> dict:
    keys = dict(eff)
    keys["lstick_down"], keys["lstick_up"] = eff["dpad_down"], eff["dpad_up"]
    row = m32.menu(f"{tag}dpad", keys, sc, extra)
    row["scenario"] = "menu_dpad"
    row["dpad_navigates_menus"] = row.pop("pass")
    return row


def play(tag, eff, sc, extra, settle=25, pause_only=False) -> dict:
    run, level = f"padinv_{tag}_play", "wood_10"
    run_dir = m32.RUNS / run
    seconds = settle + (80 if pause_only else 200)
    proc, log = m32.start(run, f"wait {seconds - 8}\n", seconds, extra, test_level=level)
    WORK.mkdir(parents=True, exist_ok=True)
    watch_out = WORK / f"{run}_watch.jsonl"
    watcher = subprocess.Popen([sys.executable, str(TOOLS / "m18_progress_watch.py"), str(run_dir), str(watch_out),
                                "--seconds", str(seconds + 30), "--interval", "0.05"], cwd=ROOT,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    row = {"run": run, "scenario": "play", "level": level, "keys": {b: eff[b][0] for b in PROBED}, "buttons": {},
           "pause": {}}

    def key(name, down):
        with (run_dir / "schedule.txt").open("a", encoding="ascii", newline="") as s:
            s.write(f"0 {sc[name]} {int(down)}\n")

    def tap(name, hold=0.25):
        key(name, True)
        time.sleep(hold)
        key(name, False)

    def view(r):  # camera angle around Rayman (degrees) and height above him
        if not r.get("camera"):
            return None, None
        c, p = r["camera"], r["rayman"]
        return math.degrees(math.atan2(c[1] - p[1], c[0] - p[0])), c[2] - p[2]

    def words_between(t0, t1):
        out = []
        if watch_out.is_file():
            for line in watch_out.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if t0 <= rec.get("wall", 0) < t1 and any(k in rec for k in MENU_WORDS):
                    out.append({k: rec[k] for k in MENU_WORDS if k in rec})
        return out
    try:
        needle = re.compile(rf"[\\/]{level}\.lvl result=00000000", re.IGNORECASE)
        end = time.monotonic() + 90
        while time.monotonic() < end and proc.poll() is None:
            if (run_dir / "runtime.log").is_file() and needle.search((run_dir / "runtime.log").read_text(errors="replace")):
                break
            time.sleep(1)
        else:
            row["error"] = "level did not open"
            return row
        time.sleep(settle)
        base = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", (run_dir / "runtime.log").read_text(errors="replace"))
        pid = json.loads((run_dir / "process.json").read_text(encoding="utf-8-sig"))["pid"]
        probe = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base.group(1) if base else "0",
                                str(run_dir / f"actors_{level}.json"), "--regions"], cwd=ROOT, capture_output=True,
                               text=True, timeout=120)
        if probe.returncode != 0:
            row["error"] = "actor discovery failed: " + probe.stderr.strip()[-200:]
            return row
        idle = status(run_dir, level, 3)
        if not idle:
            row["error"] = "no player actor"
            return row
        idle_set = {r["comport"] for r in idle}
        row["idle_comport"] = sorted(idle_set)
        row["idle_drift"] = round(math.dist(idle[0]["rayman"], idle[-1]["rayman"]), 3)
        for b in [] if pause_only else PROBED:
            rec = {}
            s0 = status(run_dir, level, 1)[-1]
            n0 = {a["so"]: a for a in m32.near(run_dir, level)}
            t0 = time.time()
            tap(eff[b][0])
            after_tap = status(run_dir, level, 4)
            key(eff[b][0], True)
            held = status(run_dir, level, 3)
            key(eff[b][0], False)
            time.sleep(0.6)
            n1 = {a["so"]: a for a in m32.near(run_dir, level)}
            s1 = status(run_dir, level, 1)[-1]
            t1 = time.time()
            a0, h0 = view(s0)
            a1, h1 = view(s1)
            rec["comport_beyond_idle"] = sorted({r["comport"] for r in after_tap + held} - idle_set)
            rec["displacement"] = round(math.dist(s0["rayman"], s1["rayman"]), 3)
            rec["max_rise"] = round(max(r["rayman"][2] for r in after_tap + held) - s0["rayman"][2], 3)
            rec["camera_turn_deg"] = round(((a1 - a0 + 180) % 360) - 180, 1) if a0 is not None and a1 is not None else None
            rec["camera_height_change"] = round(h1 - h0, 2) if h0 is not None and h1 is not None else None
            rec["moved_actors"] = [{"model": n1[k]["model"], "moved": round(math.dist(n0[k]["pos"], n1[k]["pos"]), 1)}
                                   for k in n1 if k in n0 and math.dist(n0[k]["pos"], n1[k]["pos"]) > 2.0]
            rec["menu_words"] = words_between(t0, t1)[:6]
            row["buttons"][b] = rec
            time.sleep(1.5)
        # The pause menu: open it, then one tap of each probed button with the menu words recorded.
        t0 = time.time()
        tap(eff["start"][0])
        time.sleep(2.5)
        row["pause"]["start"] = words_between(t0, time.time())[:6]
        # Y last (E-274: it changes the page) and the left stick as the cursor's known control.
        for b in [x for x in PROBED if x != "y"] + ["lstick_down", "lstick_up", "y"]:
            t0 = time.time()
            tap(eff[b][0])
            time.sleep(1.2)
            row["pause"][b] = words_between(t0, time.time())[:6]
    finally:
        row.update(m32.finish(proc, log, run_dir, seconds))
        try:
            watcher.wait(timeout=60)
        except subprocess.TimeoutExpired:
            watcher.kill()  # the watcher this function started, by its own handle
        row["driver_pad_lines"] = m32.runtime_log(run_dir).count("M32 keymap_test pad ")
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--scenario", nargs="*", choices=["menu", "play"], default=["menu", "play"])
    ap.add_argument("--pause-only", action="store_true")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9]+", a.tag):
        ap.error("TAG: letters and digits")
    km = rs.load_keymap()
    extra, _ = m32.launch_args(km, "modern", {})
    eff = rs.resolve_keyboard(km)["effective"]
    sc = m32.sdl_scancodes(km)
    rows = []
    if "menu" in a.scenario:
        rows.append(menu_dpad(a.tag, eff, sc, extra))
        time.sleep(3)
    if "play" in a.scenario:
        rows.append(play(a.tag, eff, sc, extra, pause_only=a.pause_only))
    for r in rows:
        r["judges"] = m32.judges(r["run"])
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / f"game_{a.tag}.json").write_text(json.dumps(rows, indent=1) + "\n", encoding="utf-8")
    for r in rows:
        print(json.dumps(r, separators=(",", ":"))[:6000], flush=True)
    print("R3HD_PAD_INVENTORY_GAME DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
