"""v1.1.0 compatibility hardening (D-142): the D-138 mouse in the title's special camera modes and across input-ownership
transitions, through the REAL keyboard / mouse driver (R3HD_KEYMAP_TEST=1, tools/m32_key_test.h: scheduled SDL scancodes,
mouse codes 400 / 401 counts, 410 .. 414 buttons, 499 markers). Hidden, muted, non-activating runs; no window, focus,
cursor, capture, OS input or physical controller. Guest state is only read (tools/m5_live.py).

    python tools/r3hd_mouse_modes_game.py TAG [--scenario modes|f4|slide|load|all]

Every comparison is mouse against the Modern map's own camera keys (arrows = the right stick), never against a free-look
model: the mouse is right-stick time (D-138), so in each mode it must do what that stick does there, and nothing after it
stops (bounded backlog, no jump).

modes  isolated menu_20: normal camera, held Y (R) = first-person Look Mode, LT (Q) = photo mode and its exit (Escape).
f4     isolated menu_20 with R3HD_PCSET_TEST toggles: held left button, right button, motion, arrow and Shift across the
       in-game PC Settings panel: neutral while open, everything held withheld after it until released, motion made
       while open never turns the camera afterwards, the mouse camera and buttons work again after a fresh press.
slide  isolated sk8_10 (a ride level: Rayman is carried forward under a chase camera): mouse against the arrow keys,
       relative to quiet windows.
load   genuine save entry intro_15_start from the title (keyboard menu keys): a left button held from the front end through
       the load gives no X until a fresh press, the level's opening cinematic (stick from mouse and arrow alike), and
       the camera after it.
Prints R3HD_MOUSE_MODES PASS|FAIL n/n; rows in private/work/mouse_modes/modes_TAG.json. Judges M21 / M23 run beside it.
"""
import argparse
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import m12_save_entry as m12  # noqa: E402
import m32_keymap_game as kg  # noqa: E402
import r3hd_settings as rs  # noqa: E402
from m5_live import Actor, Process  # noqa: E402

RUNS = ROOT / "private" / "work" / "m6_runs"
WORK = ROOT / "private" / "work" / "mouse_modes"
X_BIT = 0x4000
MOUSE = ["--mnk_mouse=true", "--mnk_mouse_buttons=true", "--mnk_sensitivity=1"]


def modern():
    km = rs.load_keymap()
    kb = rs.resolve_keyboard(km, {"layout": "modern"})
    args = [a for a in kb["args"] if a.startswith(("--keybind_", "--mnk_"))]
    sc = kg.sdl_scancodes(km)
    keys = {name: sc[keys[0]] for name, keys in kb["effective"].items() if keys and keys[0] in sc}
    return args, keys


class Run:
    def __init__(self, name, extra, seconds, test_level=None, user_root=None, env=None):
        self.name, self.seconds, self.dir = name, seconds, RUNS / name
        if self.dir.exists():
            raise SystemExit(f"run {name} already exists")
        WORK.mkdir(parents=True, exist_ok=True)
        steps = WORK / f"steps_{name}.txt"
        steps.write_text(f"wait {seconds - 8}\n", encoding="ascii")
        e = dict(os.environ, R3HD_HIDDEN_EXTRA=",".join(extra), R3HD_KEYMAP_TEST="1", **(env or {}))
        cmd = [sys.executable, str(TOOLS / "m9_license_run.py"), name, str(steps), "--license-mask", "1", "--seconds",
               str(seconds), "--play"]
        cmd += ["--test-level", test_level] if test_level else ["--user-root", user_root]
        self.log = (WORK / f"{name}.driver.log").open("w")
        self.proc = subprocess.Popen(cmd, cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT, env=e)
        self.marker, self.cam, self.marks = 0, None, {}

    def text(self):
        return kg.runtime_log(self.dir) if self.dir.is_dir() else ""

    def wait_for(self, pattern, timeout, after=0):
        """Waits until `pattern` appears in the runtime log (count > after); returns the count, 0 on timeout."""
        rx, end = re.compile(pattern, re.IGNORECASE), time.monotonic() + timeout
        while time.monotonic() < end and self.proc.poll() is None:
            n = len(rx.findall(self.text()))
            if n > after:
                return n
            time.sleep(0.5)
        return 0

    def discover(self, level):
        text = self.text()
        base = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
        pid = json.loads((self.dir / "process.json").read_text(encoding="utf-8-sig"))["pid"]
        out = self.dir / f"actors_{level}.json"
        probe = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base.group(1) if base else "0",
                                str(out), "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        if probe.returncode != 0:
            return "actor discovery failed: " + probe.stderr.strip()[-200:]
        self.cam = Cam(pid, int(base.group(1), 16), out)
        return "" if self.cam.ok() else "rayman or camera not found"

    def ev(self, *lines):
        with (self.dir / "schedule.txt").open("a", encoding="ascii", newline="") as s:
            for code, value in lines:
                s.write(f"0 {code} {int(value)}\n")

    def mark(self, name):
        self.marker += 1
        self.marks[name] = self.marker
        self.ev((499, self.marker))

    def key(self, code, down):
        self.ev((code, 1 if down else 0))

    def tap(self, code, hold=0.25):
        self.key(code, True)
        time.sleep(hold)
        self.key(code, False)

    def motion(self, dx=0, dy=0, seconds=0.4, steps=20):
        sx, sy = dx / steps, dy / steps
        for _ in range(steps):
            self.ev(*([(400, round(sx))] if dx else []), *([(401, round(sy))] if dy else []))
            time.sleep(seconds / steps)

    def window(self, name, action, seconds=1.8, interval=0.05):
        """Marks `name`, runs action() while sampling the camera; returns the sample rows (t relative to the start)."""
        rows, stop = [], threading.Event()

        def sampler():
            t0 = time.monotonic()
            while not stop.is_set():
                r = self.cam.row()
                if r:
                    r["t"] = round(time.monotonic() - t0, 3)
                    rows.append(r)
                time.sleep(interval)
        self.mark(name)
        th = threading.Thread(target=sampler)
        th.start()
        t_start = time.monotonic()
        action()
        rest = seconds - (time.monotonic() - t_start)
        if rest > 0:
            time.sleep(rest)
        stop.set()
        th.join()
        return rows

    def finish(self):
        return kg.finish(self.proc, self.log, self.dir, self.seconds)


class Cam:
    """Read-only: the camera actor's matrix (type at +0, 4x4 column by column from +4, translation +0x34) and Rayman."""

    def __init__(self, pid, base, actors_json):
        self.p = Process(pid, base)
        self.ray = self.cam = None
        for rec in json.loads(actors_json.read_text(encoding="utf-8"))["actors"]:
            try:
                a = Actor(self.p, int(rec["so"], 16))
            except (TypeError, ValueError, IndexError, OSError):
                continue
            if a.alive() and a.model == "YLT_RaymanModel" and not self.ray:
                self.ray = a
            if a.alive() and a.model == "StdCam" and not self.cam:
                self.cam = a

    def ok(self):
        return bool(self.ray and self.cam)

    def row(self):
        m = self.p.read(self.cam.matrix, 0x40) if self.cam else None
        rp = self.ray.position() if self.ray else None
        if not m or not rp:
            return None
        f = struct.unpack_from(">15f", m, 4)
        cols = [f[0:3], f[4:7], f[8:11]]
        pos = f[12:15]
        if not all(math.isfinite(v) for v in f):
            return None
        return {"cols": cols, "cam": pos, "ray": list(rp), "comport": self.ray.comport()}


def yaw_change(rows):
    """Unwrapped yaw change of the camera's most horizontal axis, and the largest change of any axis' vertical part."""
    rows = [r for r in rows if r]
    if len(rows) < 2:
        return None, None
    k = max(range(3), key=lambda i: math.hypot(rows[0]["cols"][i][0], rows[0]["cols"][i][1]))
    yaws = [math.degrees(math.atan2(r["cols"][k][1], r["cols"][k][0])) for r in rows]
    total = sum((b - a + 180.0) % 360.0 - 180.0 for a, b in zip(yaws, yaws[1:]))
    pitch = max(abs(rows[-1]["cols"][i][2] - rows[0]["cols"][i][2]) for i in range(3))
    return round(total, 1), round(pitch, 3)


def orbit_change(rows):
    """Azimuth change of the camera position around Rayman (the third-person orbit, as r3hd_mouse_game.py)."""
    pts = [math.degrees(math.atan2(r["cam"][1] - r["ray"][1], r["cam"][0] - r["ray"][0])) for r in rows if r]
    if len(pts) < 2:
        return None
    return round(sum((b - a + 180.0) % 360.0 - 180.0 for a, b in zip(pts, pts[1:])), 1)


def split(rows, t):
    return [r for r in rows if r["t"] < t], [r for r in rows if r["t"] >= t]


def summary(rows, active_s):
    """Turn during the input (+0.35 s for the title's ease-out) and after it (residual)."""
    during, after = split(rows, active_s + 0.35)
    y, p = yaw_change(during)
    ya, pa = yaw_change(after)
    return {"yaw": y, "pitch": p, "orbit": orbit_change(during), "after_yaw": ya, "after_pitch": pa,
            "after_orbit": orbit_change(after), "ray_moved": round(math.dist(rows[0]["ray"], rows[-1]["ray"]), 2) if rows else None,
            "comports": sorted({r["comport"] for r in rows if r.get("comport")}),
            "cam_ray_dist": round(math.dist(rows[0]["cam"], rows[0]["ray"]), 2) if rows else None}


def events(text):
    """Ordered (kind, value) from the runtime log: markers, pad states, pcset open / close, mouse context."""
    out = []
    for ln in text.splitlines():
        m = re.search(r"M32 keymap_test ignored scancode=499 value=(\d+)", ln)
        if m:
            out.append(("mark", int(m[1])))
            continue
        m = re.search(r"M32 keymap_test pad buttons=([0-9A-F]{4}) lt=(\d+) rt=(\d+) lx=(-?\d+) ly=(-?\d+) "
                      r"rx=(-?\d+) ry=(-?\d+)", ln)
        if m:
            out.append(("pad", (int(m[1], 16), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6]), int(m[7]))))
            continue
        if "R3HD pcset open" in ln:
            out.append(("pcset", "open"))
        elif "R3HD pcset close" in ln:
            out.append(("pcset", "close"))
        m = re.search(r"R3HD mouse context gameplay=(\d) level=(\S*)", ln)
        if m:
            out.append(("context", (int(m[1]), m[2])))
    return out


def pads_between(evs, first, last):
    """Pad states logged after marker `first` and before marker `last` (the state at `first` included)."""
    state, out, inside = None, [], False
    for kind, v in evs:
        if kind == "pad":
            state = v
            if inside:
                out.append(v)
        elif kind == "mark":
            if v == first:
                inside = True
                if state:
                    out.append(state)
            elif v == last and inside:
                break
    return out


def same_sense(a, b, floor=2.0):
    """Mouse turn `a` follows key turn `b`: both clearly the same direction, or both (near) nothing."""
    if a is None or b is None:
        return False
    if abs(b) < floor:
        return abs(a) < max(floor, abs(b) + 1.5)
    return a * b > 0 and abs(a) >= floor


# ---------------------------------------------------------------- modes: normal / Look Mode / photo mode (menu_20)
def scenario_modes(tag, checks):
    args, k = modern()
    r = Run(f"mm_{tag}_modes", args + MOUSE, 150, test_level="menu_20")
    row = {"run": r.name, "level": "menu_20", "entry": "isolated test-only (-level:), not progression"}
    w, raw = {}, {}
    try:
        if not r.wait_for(r"[\\/]menu_20\.lvl result=00000000", 90):
            row["error"] = "level did not open"
            return row
        time.sleep(25)
        err = r.discover("menu_20")
        if err:
            row["error"] = err
            return row
        right, up, left_stick_right = k["rstick_right"], k["rstick_up"], k["lstick_right"]
        # normal third-person camera, raised first (its orbit is free there, E-315)
        r.tap(k["rstick_down"], 0.35)
        time.sleep(1.2)
        w["normal_key"] = summary(r.window("normal_key", lambda: r.tap(right, 0.4)), 0.4)
        r.tap(k["rstick_down"], 0.35)
        time.sleep(1.2)
        w["normal_mouse"] = summary(r.window("normal_mouse", lambda: r.motion(dx=400)), 0.4)
        time.sleep(0.5)
        # Look Mode: Y held (Modern R)
        raw["idle_before_look"] = r.window("idle_before_look", lambda: None, 0.6)
        w["idle_before_look"] = summary(raw["idle_before_look"], 0.0)
        r.key(k["y"], True)
        time.sleep(1.5)
        w["look_idle"] = summary(r.window("look_idle", lambda: None, 1.0), 0.0)
        w["look_key"] = summary(r.window("look_key", lambda: r.tap(right, 0.4)), 0.4)
        # D-145: the mouse first (each direction's first frame must be a full deflection), then the keys as reference
        raw["look_mouse"] = r.window("look_mouse", lambda: r.motion(dx=400))
        w["look_mouse"] = summary(raw["look_mouse"], 0.4)
        w["look_left_stick"] = summary(r.window("look_left_stick", lambda: r.tap(left_stick_right, 0.4)), 0.4)
        w["look_mouse_half"] = summary(r.window("look_mouse_half", lambda: r.motion(dx=200)), 0.4)
        w["look_mouse_back"] = summary(r.window("look_mouse_back", lambda: r.motion(dx=-400)), 0.4)
        raw["look_key_s"] = r.window("look_key_s", lambda: r.tap(k["lstick_down"], 0.25))
        w["look_key_s"] = summary(raw["look_key_s"], 0.25)
        raw["look_mouse_up"] = r.window("look_mouse_up", lambda: r.motion(dy=-300))
        w["look_mouse_up"] = summary(raw["look_mouse_up"], 0.4)
        w["look_key_up"] = summary(r.window("look_key_up", lambda: r.tap(up, 0.4)), 0.4)
        w["look_click"] = summary(r.window("look_click", lambda: r.ev((410, 1), (410, 0)), 1.0), 0.1)
        r.mark("look_release")
        r.key(k["y"], False)
        time.sleep(2.0)
        w["after_look"] = summary(r.window("after_look", lambda: None, 0.6), 0.0)
        # photo mode: LT (Modern Q), its camera, then Escape (B)
        r.tap(k["left_trigger"], 0.25)
        time.sleep(2.5)
        w["photo_idle"] = summary(r.window("photo_idle", lambda: None, 1.0), 0.0)
        w["photo_key"] = summary(r.window("photo_key", lambda: r.tap(right, 0.4)), 0.4)
        w["photo_mouse"] = summary(r.window("photo_mouse", lambda: r.motion(dx=400)), 0.4)
        w["photo_click"] = summary(r.window("photo_click", lambda: r.ev((410, 1), (410, 0)), 1.0), 0.1)
        r.mark("photo_exit")
        r.tap(k["b"], 0.25)
        time.sleep(2.5)
        w["after_photo_idle"] = summary(r.window("after_photo_idle", lambda: None, 0.6), 0.0)
        r.tap(k["rstick_down"], 0.35)
        time.sleep(1.2)
        w["after_photo_mouse"] = summary(r.window("after_photo_mouse", lambda: r.motion(dx=400)), 0.4)
        r.mark("end")
        time.sleep(1.0)
    finally:
        row.update(r.finish())
    row["windows"], row["markers"] = w, r.marks
    evs = events(r.text())
    row["contexts"] = [v for kind, v in evs if kind == "context"]
    m = r.marks
    if "end" not in m:
        checks.append(("modes: run reached its steps", False))
        return row
    nm, nk = w["normal_mouse"]["orbit"], w["normal_key"]["orbit"]
    checks.append(("normal camera: mouse right turns the orbit like the Right key", same_sense(nm, nk) and abs(nm) > 5))
    look_entered = (w["look_idle"]["cam_ray_dist"] is not None and w["idle_before_look"]["cam_ray_dist"] is not None and
                    w["look_idle"]["cam_ray_dist"] < 0.6 * w["idle_before_look"]["cam_ray_dist"])
    row["look_entered"] = look_entered
    checks.append(("Look Mode (held Y) reached: the camera moves to Rayman", look_entered))
    # E-324: the title looks with the LEFT stick in Look Mode and ignores the right one. This check keeps the
    # comparisons below from passing on a blind probe.
    ls = w["look_left_stick"]["yaw"]
    checks.append(("Look Mode: the probe sees the view turn (left-stick key D turns it, Rayman stays)",
                   ls is not None and abs(ls) > 5 and (w["look_left_stick"]["ray_moved"] or 0) < 0.5))
    checks.append(("Look Mode: the right-stick key still does nothing there (title behaviour)",
                   w["look_key"]["yaw"] is not None and abs(w["look_key"]["yaw"]) < 2.0))
    # D-145: the mouse drives the left stick in Look Mode
    lm, lh, lb = w["look_mouse"]["yaw"], w["look_mouse_half"]["yaw"], w["look_mouse_back"]["yaw"]
    checks.append(("Look Mode (D-145): mouse right turns the view as the left-stick key D does, Rayman stays",
                   same_sense(lm, ls) and abs(lm or 0) > 5 and (w["look_mouse"]["ray_moved"] or 0) < 0.5))
    checks.append(("Look Mode (D-145): 400 counts turn about 0.05 deg per count (12..28 deg)",
                   lm is not None and 12.0 <= abs(lm) <= 28.0))
    checks.append(("Look Mode (D-145): half the counts turn about half as far (0.3..0.75)",
                   lm and lh is not None and 0.3 <= lh / lm <= 0.75))
    checks.append(("Look Mode (D-145): mouse left turns it the other way", lb is not None and lm and lb * lm < 0 and abs(lb) > 5))

    def forward_axis(rows):
        """(axis, sign) of the camera's look direction: the matrix row most aligned with camera -> Rayman in the
        third-person frames (E-331; the most vertical-moving axis has no known sign, which inverted E-327)."""
        votes = {}
        for x in rows:
            if not x or math.dist(x["cam"], x["ray"]) < 1.0:
                continue
            d = [a - b for a, b in zip(x["ray"], x["cam"])]
            dots = [sum(u * v for u, v in zip(c, d)) / (math.hypot(*c) or 1.0) for c in x["cols"]]
            i = max(range(3), key=lambda j: abs(dots[j]))
            votes[(i, 1 if dots[i] > 0 else -1)] = votes.get((i, 1 if dots[i] > 0 else -1), 0) + 1
        return max(votes, key=votes.get) if votes else None

    def tilt(rows, fwd):
        """Change of the forward axis' elevation (deg): positive = the view looks up."""
        a = [x for x in rows if x]
        if not fwd or len(a) < 2:
            return None
        def el(x):
            c = [fwd[1] * v for v in x["cols"][fwd[0]]]
            return math.degrees(math.atan2(c[2], math.hypot(c[0], c[1])))
        return round(el(a[-1]) - el(a[0]), 2)
    fwd = forward_axis(raw["idle_before_look"])
    ks, mu = tilt(raw["look_key_s"], fwd), tilt(raw["look_mouse_up"], fwd)
    row["look_tilt"] = {"forward": fwd, "key_s_deg": ks, "mouse_up_deg": mu}
    checks.append(("Look Mode (D-145): mouse up tilts the view UP (the forward axis rises), as the user sees it",
                   mu is not None and mu > 2.0))
    checks.append(("Look Mode: the left-stick-down key S tilts the view down (title behaviour, E-331)",
                   ks is not None and ks < -2.0))
    lx_mouse = [p[3] for p in pads_between(evs, m["look_mouse"], m["look_left_stick"]) if p[3]]
    lx_half = [p[3] for p in pads_between(evs, m["look_mouse_half"], m["look_mouse_back"]) if p[3]]
    lx_back = [p[3] for p in pads_between(evs, m["look_mouse_back"], m["look_key_s"]) if p[3]]
    row["look_lx"] = {"mouse": lx_mouse[:12], "half": lx_half[:12], "back": lx_back[:12]}
    checks.append(("Look Mode (D-145): each direction's first mouse frame is a full deflection (title calibration)",
                   bool(lx_mouse) and lx_mouse[0] == 32767 and bool(lx_back) and lx_back[0] == -32767))
    checks.append(("Look Mode (D-145): once calibrated, partial deflections, never below 0.45",
                   any(0 < v < 32767 for v in lx_half) and all(abs(v) >= int(0.45 * 32767) for v in lx_half)))
    resid = [w[n]["after_yaw"] for n in ("look_mouse", "look_mouse_half", "look_mouse_back")]
    checks.append(("Look Mode: no turn continues after the mouse stops (residual < 3 deg)",
                   all(x is not None and abs(x) < 3.0 for x in resid)))
    click = pads_between(evs, m["look_click"], m["look_release"])
    checks.append(("Look Mode: a left click reaches the guest as X (as the bound key would)", any(p[0] & X_BIT for p in click)))
    pk, pm = w["photo_key"]["yaw"], w["photo_mouse"]["yaw"]
    pko, pmo = w["photo_key"]["orbit"], w["photo_mouse"]["orbit"]
    checks.append(("photo mode (D-145 off there): the mouse gives no left stick",
                   not any(p[3] or p[4] for p in pads_between(evs, m["photo_mouse"], m["photo_click"]))))
    checks.append(("photo mode: mouse right acts as the right-stick key does (view or orbit)",
                   same_sense(pm, pk) and same_sense(pmo, pko)))
    checks.append(("photo mode: no turn continues after the mouse stops (residual < 3 deg)",
                   w["photo_mouse"]["after_yaw"] is not None and abs(w["photo_mouse"]["after_yaw"]) < 3.0))
    am = w["after_photo_mouse"]["orbit"]
    checks.append(("after photo mode: the mouse camera turns the orbit again", am is not None and am < -5))
    return row


# ---------------------------------------------------------------- f4: the PC Settings panel's input gate in the game
def scenario_f4(tag, checks):
    args, k = modern()
    toggles = "40,52,64,76"
    r = Run(f"mm_{tag}_f4", args + MOUSE, 130, test_level="menu_20", env={"R3HD_PCSET_TEST": toggles})
    row = {"run": r.name, "level": "menu_20", "pcset_toggles": toggles}
    w = {}
    try:
        if not r.wait_for(r"[\\/]menu_20\.lvl result=00000000", 60):
            row["error"] = "level did not open"
            return row
        time.sleep(20)
        err = r.discover("menu_20")
        if err:
            row["error"] = err
            return row
        right, shift = k["rstick_right"], k["right_trigger"]
        # first panel: left button and the Right key, motion while open
        r.mark("lmb_down")
        r.ev((410, 1))  # held into the panel
        if not r.wait_for(r"R3HD pcset open", 40):
            row["error"] = "panel did not open"
            return row
        time.sleep(1.0)
        r.mark("open1")
        r.motion(dx=600)  # motion while the panel holds the input
        r.key(right, True)  # pressed while open, held through the close
        n_close = r.wait_for(r"R3HD pcset close", 20)
        time.sleep(0.6)
        w["after_close1_held"] = summary(r.window("closed1_held", lambda: None, 1.4), 0.0)
        r.mark("release1")
        r.ev((410, 0))
        r.key(right, False)
        time.sleep(0.5)
        r.mark("fresh1")
        r.ev((410, 1))
        time.sleep(0.6)
        r.ev((410, 0))
        time.sleep(0.4)
        r.tap(k["rstick_down"], 0.35)
        time.sleep(1.2)
        w["mouse_after_close1"] = summary(r.window("mouse_after1", lambda: r.motion(dx=400)), 0.4)
        # second panel: right button and Shift (both lock-on), held through it
        r.mark("hold2")
        r.ev((411, 1))
        r.key(shift, True)
        if not r.wait_for(r"R3HD pcset open", 30, after=1):
            row["error"] = "second panel did not open"
            return row
        r.mark("open2")
        r.wait_for(r"R3HD pcset close", 30, after=n_close)
        time.sleep(0.8)
        r.mark("closed2_held")
        time.sleep(1.2)
        r.mark("release2")
        r.ev((411, 0))
        r.key(shift, False)
        time.sleep(0.5)
        r.mark("fresh2")
        r.ev((411, 1))
        time.sleep(0.6)
        r.ev((411, 0))
        r.mark("end")
        time.sleep(1.0)
    finally:
        row.update(r.finish())
    row["windows"], row["markers"] = w, r.marks
    text = r.text()
    evs = events(text)
    m = r.marks
    if "end" not in m:
        checks.append(("f4: run reached its steps", False))
        return row
    before = pads_between(evs, m["lmb_down"], m["open1"])
    checks.append(("f4: left button held before the panel reaches the guest as X", any(p[0] & X_BIT for p in before)))
    # the open interval: from the open line to the close line
    seq, inside, opened = [], False, 0
    for kind, v in evs:
        if kind == "pcset" and v == "open":
            inside, opened = True, opened + 1
        elif kind == "pcset" and v == "close":
            inside = False
        elif kind == "pad" and inside:
            seq.append(v)
    checks.append(("f4: while the panel is open the guest sees neutral input (no X, RT, stick)",
                   opened >= 2 and not any(p[0] or p[2] or p[5] or p[6] for p in seq)))
    held1 = pads_between(evs, m["closed1_held"], m["release1"])
    checks.append(("f4: after the close a still-held left button gives no X (fresh press needed)",
                   not any(p[0] & X_BIT for p in held1)))
    checks.append(("f4: after the close the held Right key and the motion made while open give no stick",
                   not any(p[5] for p in held1) and abs(w["after_close1_held"]["orbit"] or 0) < 3))
    fresh1 = pads_between(evs, m["fresh1"], m["hold2"])
    checks.append(("f4: a fresh left press after the close reaches the guest as X", any(p[0] & X_BIT for p in fresh1)))
    am = w["mouse_after_close1"]["orbit"]
    checks.append(("f4: the mouse camera turns the orbit again after the close", am is not None and am < -5))
    held2 = pads_between(evs, m["closed2_held"], m["release2"])
    checks.append(("f4: right button and Shift held through the panel give no RT after it", not any(p[2] for p in held2)))
    fresh2 = pads_between(evs, m["fresh2"], m["end"])
    checks.append(("f4: a fresh right press after the close gives RT 255", any(p[2] == 255 for p in fresh2)))
    checks.append(("f4: the panel never started the engine in the hidden run", "settings_app=started" not in text))
    return row


# ---------------------------------------------------------------- load: genuine save from the title, opening cinematic
def scenario_load(tag, checks, entry_name="intro_15_start"):
    args, k = modern()
    name = f"mm_{tag}_load"
    entry = m12.load_entry(entry_name)
    work = m12.PROFILES / name
    if work.exists():
        raise SystemExit(f"profile {work} already exists")
    if not m12.stored_profile_matches(entry):
        raise SystemExit(f"stored profile of {entry_name} no longer matches entry.json")
    shutil.copytree(m12.SAVES / entry_name / "profile", work)
    r = Run(name, args + MOUSE, 230, user_root=name)
    row = {"run": name, "entry": entry_name, "entry_class": "genuine save (working copy)"}
    w = {}
    try:
        if not (r.wait_for(r"VIDEOS\\ubi\.bik result=00000000", 60) and r.wait_for(r"menumap\\menumap\.lvl result=00000000", 60)):
            row["error"] = "title did not open"
            return row
        time.sleep(10)
        r.tap(k["start"], 0.3)
        time.sleep(12)
        r.mark("lmb_front_end")
        r.ev((410, 1))  # pressed in the front end, held through the menus and the load
        r.tap(k["lstick_down"], 0.3)  # New -> Load: m12's step `axis 301 -32767` is ly down (m6_test_input.h)
        time.sleep(2)
        r.tap(k["a"], 0.3)
        time.sleep(8)
        r.tap(k["a"], 0.3)
        if not r.wait_for(r"[\\/]intro_15\.lvl result=00000000", 60):
            row["error"] = "level did not load"
            return row
        t_load = time.monotonic()
        time.sleep(6)
        err = r.discover("intro_15")
        if err:
            row["error"] = err
            return row
        time.sleep(2)
        r.mark("lmb_release")
        r.ev((410, 0))
        time.sleep(0.6)
        w["cine_quiet"] = summary(r.window("cine_quiet", lambda: None, 1.8), 0.4)
        w["cine_key"] = summary(r.window("cine_key", lambda: r.tap(k["rstick_right"], 0.4)), 0.4)
        w["cine_mouse"] = summary(r.window("cine_mouse", lambda: r.motion(dx=400)), 0.4)
        w["cine_quiet2"] = summary(r.window("cine_quiet2", lambda: None, 1.8), 0.4)
        r.mark("cine_click")
        r.ev((410, 1), (410, 0))
        time.sleep(1.0)
        r.mark("cine_end")
        rest = 90 - (time.monotonic() - t_load)  # the opening scene lasts about 75 s (AGENTS M12)
        if rest > 0:
            time.sleep(rest)
        r.tap(k["rstick_down"], 0.35)
        time.sleep(1.2)
        w["play_key"] = summary(r.window("play_key", lambda: r.tap(k["rstick_right"], 0.4)), 0.4)
        r.tap(k["rstick_down"], 0.35)
        time.sleep(1.2)
        w["play_mouse"] = summary(r.window("play_mouse", lambda: r.motion(dx=400)), 0.4)
        r.mark("play_click")
        r.ev((410, 1), (410, 0))
        time.sleep(1.0)
        r.mark("end")
        time.sleep(1.0)
    finally:
        row.update(r.finish())
    row["windows"], row["markers"] = w, r.marks
    evs = events(r.text())
    row["contexts"] = [v for kind, v in evs if kind == "context"]
    m = r.marks
    if "end" not in m:
        checks.append(("load: run reached its steps", False))
        return row
    held = pads_between(evs, m["lmb_front_end"], m["lmb_release"])
    checks.append(("load: a left button held from the front end through the load gives no X",
                   bool(held) and not any(p[0] & X_BIT for p in held)))
    ctx = row["contexts"]
    # the context starts as "not gameplay" (no line); the first change must be the level, never the front end
    checks.append(("load: front end withholds the mouse, the level gives it back (first context: 1 intro_15)",
                   bool(ctx) and ctx[0][0] == 1 and ctx[0][1].lower() == "intro_15"))
    stick_key = [p for p in pads_between(evs, m["cine_key"], m["cine_mouse"]) if p[5] > 0]
    stick_mouse = [p for p in pads_between(evs, m["cine_mouse"], m["cine_quiet2"]) if p[5] > 0]
    checks.append(("opening cinematic: mouse motion reaches the guest as the same right stick as the key",
                   bool(stick_key) == bool(stick_mouse)))
    click = pads_between(evs, m["cine_click"], m["cine_end"])
    checks.append(("opening cinematic: a fresh left click reaches the guest as X (as the key would)",
                   any(p[0] & X_BIT for p in click)))
    pk, pm = w["play_key"]["orbit"], w["play_mouse"]["orbit"]
    checks.append(("after the cinematic: mouse right turns the orbit like the Right key",
                   same_sense(pm, pk)))
    checks.append(("after the cinematic: no turn continues after the mouse stops (residual < 3 deg)",
                   w["play_mouse"]["after_orbit"] is not None and abs(w["play_mouse"]["after_orbit"]) < 3.0))
    return row


# ---------------------------------------------------------------- slide: a ride level's chase camera (isolated sk8_10)
def scenario_slide(tag, checks):
    args, k = modern()
    r = Run(f"mm_{tag}_slide", args + MOUSE, 90, test_level="sk8_10")
    row = {"run": r.name, "level": "sk8_10", "entry": "isolated test-only (-level:), not progression"}
    w = {}
    try:
        if not r.wait_for(r"[\\/]sk8_10\.lvl result=00000000", 60):
            row["error"] = "level did not open"
            return row
        time.sleep(10)
        err = r.discover("sk8_10")
        if err:
            row["error"] = err
            return row
        right, left = k["rstick_right"], k["rstick_left"]
        for name, act in (("quiet", lambda: None), ("key", lambda: r.tap(right, 0.4)), ("mouse", lambda: r.motion(dx=400)),
                          ("quiet2", lambda: None), ("key_left", lambda: r.tap(left, 0.4)),
                          ("mouse_left", lambda: r.motion(dx=-400)), ("quiet3", lambda: None)):
            w[name] = summary(r.window(name, act, 1.6), 0.4)
        r.mark("end")
        time.sleep(1.0)
    finally:
        row.update(r.finish())
    row["windows"], row["markers"] = w, r.marks
    evs = events(r.text())
    m = r.marks
    if "end" not in m:
        checks.append(("slide: run reached its steps", False))
        return row
    order = ["quiet", "key", "mouse", "quiet2", "key_left", "mouse_left", "quiet3", "end"]
    stick = {n: [p[5] for p in pads_between(evs, m[n], m[order[i + 1]]) if p[5]] for i, n in enumerate(order[:-1])}
    checks.append(("slide (no Look Mode): the mouse gives no left stick",
                   not any(p[3] or p[4] for n in ("mouse", "mouse_left")
                           for p in pads_between(evs, m[n], m[order[order.index(n) + 1]]))))
    checks.append(("slide: mouse motion reaches the guest as the same right stick as the arrow key, both ways",
                   bool(stick["key"]) == bool(stick["mouse"]) and bool(stick["key_left"]) == bool(stick["mouse_left"]) and
                   all(v > 0 for v in stick["mouse"]) and all(v < 0 for v in stick["mouse_left"])))
    quiet = [w[n]["orbit"] for n in ("quiet", "quiet2", "quiet3") if w[n]["orbit"] is not None]
    base = sum(quiet) / len(quiet) if quiet else None
    noise = max(abs(q - base) for q in quiet) if quiet else None
    rel = {n: (round(w[n]["orbit"] - base, 1) if base is not None and w[n]["orbit"] is not None else None)
           for n in ("key", "mouse", "key_left", "mouse_left")}
    row["relative_orbit"], row["quiet_noise"] = rel, noise
    # the quiet windows swing with the track's curves (E-324: +-25 deg), so compare each mouse window with its key window
    diff = [None if w[a]["orbit"] is None or w[b]["orbit"] is None else abs(w[a]["orbit"] - w[b]["orbit"])
            for a, b in (("mouse", "key"), ("mouse_left", "key_left"))]
    row["mouse_minus_key"] = diff
    checks.append(("slide: the chase camera does with the mouse what it does with the key (within 3 deg)",
                   all(d is not None and d <= 3.0 for d in diff)))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--scenario", choices=["modes", "f4", "load", "slide", "all"], default="all")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_]+", a.tag):
        raise SystemExit("invalid TAG")
    WORK.mkdir(parents=True, exist_ok=True)
    checks, rows = [], []
    for name, fn in (("modes", scenario_modes), ("f4", scenario_f4), ("slide", scenario_slide), ("load", scenario_load)):
        if a.scenario not in (name, "all"):
            continue
        while subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower().count("r3hd.exe"):
            time.sleep(2)
        rows.append(fn(a.tag, checks))
    for row in rows:
        checks.append((f"{row['run']}: exit 0, never in the foreground",
                       row.get("exit_code") == 0 and not row.get("game_foreground_events") and not row.get("error")))
    out = {"tag": a.tag, "rows": rows, "checks": [[n, ok] for n, ok in checks]}
    (WORK / f"modes_{a.tag}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for n, ok in checks:
        print("PASS" if ok else "FAIL", n)
    good = sum(ok for _, ok in checks)
    print(f"R3HD_MOUSE_MODES {'PASS' if good == len(checks) else 'FAIL'} {good}/{len(checks)}")
    return 0 if good == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
