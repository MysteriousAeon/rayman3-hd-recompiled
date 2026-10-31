"""D-138 in-game proof of the mouse controls through the REAL keyboard / mouse driver (hidden, isolated test-only levels,
not progression). R3HD_KEYMAP_TEST=1: scheduled events reach a window-less instance of the real driver
(tools/m32_key_test.h; mouse codes 400 / 401 = relative counts, 410 .. 414 = buttons, 499 = a log marker), whose state
is the guest's pad. The guest context is the run's own (VdSwap). No window, focus, cursor, capture or OS input.

    python tools/r3hd_mouse_game.py TAG [--scenario camera|buttons|all] [--sensitivity S]

camera   menu_20: mouse down raises the camera (stick down), horizontal counts turn it (mouse right = stick right),
         twice the counts turn it further; Mouse Buttons off: a held left button gives no X; in the pause menu motion
         gives no stick and resuming gives no camera jump.
buttons  knaar_20: left held = X held (charge), a click shorter than a poll still reaches the guest, right held = lock-on
         (YAM_C_StrafeWait), keyboard E / Shift unchanged, a left button held across pause / resume gives no X until a
         fresh press; Mouse Camera off: motion gives no stick.
Prints R3HD_MOUSE_GAME PASS|FAIL n/n; rows in private/work/mouse/game_TAG.json. Judges M21 / M23 run beside it.
"""
import argparse
import json
import math
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import m49_walk_game as wg  # noqa: E402
import m32_keymap_game as kg  # noqa: E402

WORK = ROOT / "private" / "work" / "mouse"
# SDL scancodes of the keys used (SDL_scancode.h); the keymap test translates them as the window would.
RETURN, SPACE, KEY_E, LSHIFT = 40, 44, 8, 225
BINDS = ["--keybind_x=E,LMB", "--keybind_right_trigger=Shift,RMB", "--keybind_a=Space", "--keybind_start=Return",
         "--keybind_b=Escape", "--mnk_modifier_keys=true"]


class Run:
    def __init__(self, name, level, extra, seconds):
        wg.LEVEL = level
        self.name, self.level, self.seconds = name, level, seconds
        self.dir = wg.RUNS / name
        self.proc, self.log = wg.start(name, seconds, extra, keymap_test=True)
        self.marker = 0

    def ev(self, *lines):
        with (self.dir / "schedule.txt").open("a", encoding="ascii", newline="") as s:
            for code, value in lines:
                s.write(f"0 {code} {int(value)}\n")

    def mark(self):
        self.marker += 1
        self.ev((499, self.marker))
        return self.marker

    def key(self, code, down):
        self.ev((code, 1 if down else 0))

    def tap(self, code, hold=0.25):
        self.key(code, True)
        time.sleep(hold)
        self.key(code, False)

    def motion(self, dx=0, dy=0, seconds=0.4, steps=20):
        """dx / dy counts spread over `seconds`, as a moving mouse delivers them."""
        sx, sy = dx / steps, dy / steps
        for _ in range(steps):
            self.ev(*([(400, round(sx))] if dx else []), *([(401, round(sy))] if dy else []))
            time.sleep(seconds / steps)

    def samples(self, n, interval=0.1, dsg=""):
        done = subprocess.run([sys.executable, str(TOOLS / "m7_live_status.py"), str(self.dir), "--level", self.level,
                               "--near", "0", "--samples", str(n), "--interval", str(interval)]
                              + (["--dsg", dsg] if dsg else []), cwd=ROOT,
                              capture_output=True, text=True, timeout=180)
        rows = []
        for line in done.stdout.splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
        return rows

    def finish(self):
        return kg.finish(self.proc, self.log, self.dir, self.seconds)


def azimuth(row):
    c, p = row["camera"], row["rayman"]
    return math.degrees(math.atan2(c[1] - p[1], c[0] - p[0])), c[2] - p[2]


def turned(rows):
    """Signed total azimuth change (unwrapped) over the samples, and the height change."""
    pts = [azimuth(r) for r in rows if r.get("camera") and r.get("rayman")]
    if len(pts) < 2:
        return None, None
    total = 0.0
    for (a, _), (b, _) in zip(pts, pts[1:]):
        total += (b - a + 180.0) % 360.0 - 180.0
    return round(total, 1), round(pts[-1][1] - pts[0][1], 2)


def pad_lines(text):
    """(marker, buttons, rt, rx, ry) for every pad state change, tagged with the last marker before it."""
    marker, out = 0, []
    for ln in text.splitlines():
        m = re.search(r"M32 keymap_test ignored scancode=499 value=(\d+)", ln)
        if m:
            marker = int(m[1])
            continue
        m = re.search(r"M32 keymap_test pad buttons=([0-9A-F]{4}) lt=(\d+) rt=(\d+) lx=(-?\d+) ly=(-?\d+) "
                      r"rx=(-?\d+) ry=(-?\d+)", ln)
        if m:
            out.append((marker, int(m[1], 16), int(m[3]), int(m[6]), int(m[7])))
    return out


def between(pads, first, last):
    return [p for p in pads if first <= p[0] < last]


def camera(tag, sens, checks):
    extra = BINDS + ["--mnk_mouse=true", "--mnk_mouse_buttons=false", f"--mnk_sensitivity={sens}"]
    r = Run(f"mouse_{tag}_camera", "menu_20", extra, 30 + 95)
    row = {"run": r.name, "level": r.level, "sensitivity": sens}
    try:
        err = wg.wait_level(r.proc, r.dir, 25)
        if err:
            row["error"] = err
            return row
        turns = {}
        for counts in (400, -400, 200, -200, 400):
            r.motion(dy=600, seconds=0.3)  # mouse down: the camera rises (where the orbit is free in menu_20)
            time.sleep(1.2)
            got = []
            m = r.mark()
            t = threading.Thread(target=lambda: got.extend(r.samples(22)))
            t.start()
            r.motion(dx=counts, seconds=0.4)
            t.join()
            turns.setdefault(counts, []).append(turned(got))
            row.setdefault("markers", {})[f"turn{counts}_{m}"] = m
            time.sleep(0.8)
        row["turns"] = {str(k): v for k, v in turns.items()}
        m_hold = r.mark()
        r.ev((410, 1))
        time.sleep(1.0)
        r.ev((410, 0))
        m_pause = r.mark()
        r.tap(RETURN)
        time.sleep(2.0)
        m_in = r.mark()
        r.motion(dx=400, seconds=0.4)
        time.sleep(0.6)
        m_resume = r.mark()
        r.tap(SPACE)
        time.sleep(1.5)
        m_end = r.mark()
        time.sleep(1.0)
        row["markers"].update(hold=m_hold, pause=m_pause, in_pause=m_in, resume=m_resume, end=m_end)
    finally:
        row.update(r.finish())
    text = kg.runtime_log(r.dir)
    pads = pad_lines(text)
    a4 = [t for t in turns.get(400, []) if t and t[0] is not None]
    a2 = [t for t in turns.get(200, []) if t and t[0] is not None]
    n4 = [t for t in turns.get(-400, []) if t and t[0] is not None]
    row["config_line"] = next((ln.split("R3HD mouse ", 1)[1] for ln in text.splitlines() if "R3HD mouse camera=" in ln), None)
    row["context_lines"] = [ln.split("R3HD mouse ", 1)[1] for ln in text.splitlines() if "R3HD mouse context" in ln]
    checks.append(("camera: configuration line (camera on, buttons off)", bool(row["config_line"]) and
                   "camera=true buttons=false" in row["config_line"]))
    checks.append(("camera: mouse right turns the camera like the stick (azimuth falls) every time",
                   len(a4) == 2 and all(t[0] < -5 for t in a4)))
    checks.append(("camera: mouse left turns it the other way", len(n4) == 1 and n4[0][0] > 5))
    checks.append(("camera: twice the counts turn further", len(a4) == 2 and len(a2) == 1 and
                   min(abs(t[0]) for t in a4) > abs(a2[0][0]) > 2))
    m = row.get("markers", {})
    if m:
        hold = between(pads, m["hold"], m["pause"])
        checks.append(("camera run (Mouse Buttons off): a held left button gives no X",
                       not any(p[1] & 0x4000 for p in hold)))
        in_pause = between(pads, m["in_pause"], m["resume"])
        checks.append(("pause: mouse motion gives no stick", not any(p[3] for p in in_pause)))
        after = between(pads, m["resume"], m["end"])
        checks.append(("resume: no camera jump (no stick from motion made in the pause)", not any(p[3] for p in after)))
        checks.append(("pause / resume reached the driver as guest context changes",
                       any("gameplay=0" in c for c in row["context_lines"]) and
                       any("gameplay=1" in c for c in row["context_lines"])))
    return row


def buttons(tag, checks):
    extra = BINDS + ["--mnk_mouse=false", "--mnk_mouse_buttons=true"]
    r = Run(f"mouse_{tag}_buttons", "knaar_20", extra, 30 + 70)
    row = {"run": r.name, "level": r.level}

    def comports(n=12):
        return [x.get("comport") for x in r.samples(n) if x.get("comport")]

    def charge(n=12):
        """Rayman's variable 137 per sample: 1 while X is held with hands (the charge state, RE_NOTES M7)."""
        return [int(any(c != "0" for c in (x.get("dsg") or {}).get("137", "0"))) for x in r.samples(n, dsg="137")]
    try:
        err = wg.wait_level(r.proc, r.dir, 25)
        if err:
            row["error"] = err
            return row
        row["idle"] = sorted(set(comports(5)))
        m = {"e": r.mark()}  # the keyboard first: a thrown fist delays the next charge
        r.key(KEY_E, True)
        row["e_held"] = charge(14)
        r.key(KEY_E, False)
        time.sleep(3.0)
        m["lmb"] = r.mark()
        r.ev((410, 1))
        row["lmb_held"] = charge(14)
        r.ev((410, 0))
        row["lmb_released"] = charge(10)
        time.sleep(1.0)
        m["click"] = r.mark()
        r.ev((410, 1), (410, 0))  # down and up before the next poll
        time.sleep(3.0)
        m["rmb"] = r.mark()
        r.ev((411, 1))
        row["rmb_held"] = comports(12)
        r.ev((411, 0))
        row["rmb_released"] = comports(10)
        m["shift"] = r.mark()
        r.key(LSHIFT, True)
        row["shift_held"] = comports(10)
        r.key(LSHIFT, False)
        time.sleep(1.0)
        m["motion"] = r.mark()
        r.motion(dx=400, dy=400, seconds=0.4)
        time.sleep(0.5)
        m["pause"] = r.mark()
        r.ev((410, 1))  # held into the pause
        time.sleep(0.3)
        r.tap(RETURN)
        time.sleep(2.0)
        m["resume"] = r.mark()
        r.tap(SPACE)
        time.sleep(1.5)
        row["held_after_resume"] = charge(8)
        m["fresh"] = r.mark()
        r.ev((410, 0))
        time.sleep(0.2)
        r.ev((410, 1))
        row["fresh_after_resume"] = charge(10)
        r.ev((410, 0))
        m["end"] = r.mark()
        time.sleep(1.0)
        row["markers"] = m
    finally:
        row.update(r.finish())
    text = kg.runtime_log(r.dir)
    pads = pad_lines(text)
    m = row.get("markers")
    row["config_line"] = next((ln.split("R3HD mouse ", 1)[1] for ln in text.splitlines() if "R3HD mouse camera=" in ln), None)
    if not m:
        checks.append(("buttons: run reached its steps", False))
        return row
    x = lambda a, b: any(p[1] & 0x4000 for p in between(pads, m[a], m[b]))  # noqa: E731
    checks.append(("buttons: configuration line (buttons on, camera off)", bool(row["config_line"]) and
                   "camera=false buttons=true" in row["config_line"]))
    checks.append(("left held: X reaches the guest", x("lmb", "click")))
    checks.append(("left held: the charge state (Rayman variable 137 = 1) while held",
                   sum(row["lmb_held"]) >= 5 and bool(row["lmb_released"]) and row["lmb_released"][-1] == 0))
    checks.append(("short left click: X reaches the guest (one poll at least)", x("click", "rmb")))
    checks.append(("keyboard E unchanged: X and the charge state", x("e", "lmb") and sum(row["e_held"]) >= 5))
    rt = [p for p in between(pads, m["rmb"], m["shift"]) if p[2] == 255]
    checks.append(("right held: right trigger full and lock-on (YAM_C_StrafeWait)",
                   bool(rt) and "YAM_C_StrafeWait" in row["rmb_held"]))
    checks.append(("right released: lock-on ends", bool(row["rmb_released"]) and row["rmb_released"][-1] != "YAM_C_StrafeWait"))
    checks.append(("keyboard Shift unchanged: lock-on", "YAM_C_StrafeWait" in row["shift_held"]))
    checks.append(("Mouse Camera off: motion gives no stick", not any(p[3] or p[4] for p in between(pads, m["motion"], m["pause"]))))
    paused = [p for p in pads if m["pause"] <= p[0] < m["resume"]]
    checks.append(("left held into the pause: X is dropped in the pause menu", bool(paused) and not paused[-1][1] & 0x4000))
    checks.append(("still held after resume: no X and no charge until a fresh press",
                   not x("resume", "fresh") and sum(row["held_after_resume"]) == 0))
    checks.append(("fresh press after resume: X and the charge state again", x("fresh", "end") and
                   sum(row["fresh_after_resume"]) >= 3))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--scenario", choices=["camera", "buttons", "all"], default="all")
    ap.add_argument("--sensitivity", default="1")
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    checks, rows = [], []
    if a.scenario in ("camera", "all"):
        rows.append(camera(a.tag, a.sensitivity, checks))
        while subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower().count("r3hd.exe"):
            time.sleep(2)
    if a.scenario in ("buttons", "all"):
        rows.append(buttons(a.tag, checks))
    for row in rows:
        checks.append((f"{row['run']}: exit 0, never in the foreground",
                       row.get("exit_code") == 0 and not row.get("game_foreground_events") and not row.get("error")))
    out = {"tag": a.tag, "rows": rows, "checks": [[n, ok] for n, ok in checks]}
    (WORK / f"game_{a.tag}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for n, ok in checks:
        print("PASS" if ok else "FAIL", n)
    good = sum(ok for _, ok in checks)
    print(f"R3HD_MOUSE_GAME {'PASS' if good == len(checks) else 'FAIL'} {good}/{len(checks)}")
    return 0 if good == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
