#!/usr/bin/env python3
"""M43 (D-080) regression: the Settings window's placement, the simplified Controls page, the Diagnostics default,
the Mods page's description box and the provisional HD+ Robo-Pirate correction. No game run.

    python tools/m43_regression.py [--launcher EXE] [--real-mod MOD_JSON] [--keep DIR]
        -> M43_REGRESSION PASS checks=N failures=0 skipped=S
    python tools/m43_regression.py --placement-only --launcher EXE      only the window placement (e.g. the M42 build)

  * placement: the launcher runs `--ui-test` on its own desktop (never the person's); an observer in this process
    reads the window's rectangle from outside (EnumDesktopWindows + GetWindowRect: no input, no focus, no message to
    the window) while the script switches pages at 96, 120 and 144 DPI, after a simulated move by a person, and on a
    simulated 1366 x 728 work area at 144 DPI. Pages that fit share one centre; switching back returns the window to the
    same rectangle; the window stays inside its work area; a status line or a key capture never moves it.
  * Controls: the uncharacterised inputs are never shown and there is no option to show them; their keys stay in the
    map (saved, restored by a layout); capture, swap, Restore defaults and Save still work.
  * Diagnostics: a new installation resolves Standard without storing it; an explicit Detailed is kept by a preset
    change, a repair and an update, and by the Settings window's Save; choosing Standard there touches nothing else.
  * Mods: the selected mod's details sit in a fixed, scrolling box: the whole description is in it and reachable for
    the real preview mod's metadata (--real-mod: name, version and description only are read) and a synthetic long one,
    enabled and disabled, at 96 and 144 DPI; the page does not change height; nothing overlaps.
  * HD+: texture_orient = corrected in HD+ (provisional, with a note), original in Vanilla, either in Custom; the
    play.ps1 parameter turns it off.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import r3hd_installer as engine  # noqa: E402
import r3hd_mods as mods  # noqa: E402
import r3hd_settings as rs  # noqa: E402
import m30_launcher_regression as m30  # noqa: E402

LAUNCHER = ROOT / "private" / "work" / "launcher" / "r3hd_launcher.exe"
PLAY = TOOLS / "play.ps1"
checks = failures = skipped = 0


def check(name, cond, detail=""):
    global checks, failures
    checks += 1
    if not cond:
        failures += 1
        print(f"FAIL {name}" + (f": {str(detail)[:600]}" if detail else ""))


def skip(name, why):
    global skipped
    skipped += 1
    print(f"SKIP {name}: {why}")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


# --- an observer of the launcher's window on its private desktop -------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user32.OpenDesktopW.restype = wt.HANDLE
user32.OpenDesktopW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.BOOL, wt.DWORD]
user32.EnumDesktopWindows.argtypes = [wt.HANDLE, EnumProc, wt.LPARAM]
user32.CloseDesktop.argtypes = [wt.HANDLE]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
DESKTOP_READOBJECTS, DESKTOP_ENUMERATE = 0x0001, 0x0040


def window_rect(pid: int):
    """The Settings window's rectangle on the test desktop of launcher process pid, or None (read-only)."""
    desk = user32.OpenDesktopW(f"r3hd_ui_test_{pid}", 0, False, DESKTOP_READOBJECTS | DESKTOP_ENUMERATE)
    if not desk:
        return None
    found = []

    def cb(h, _):
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, buf, 64)
        if buf.value == "R3HDRecompSettings":
            r = wt.RECT()
            if user32.GetWindowRect(h, ctypes.byref(r)):
                found.append((r.left, r.top, r.right, r.bottom))
        return True
    user32.EnumDesktopWindows(desk, EnumProc(cb), 0)
    user32.CloseDesktop(desk)
    return found[0] if found else None


def observed_run(launcher: Path, home: Path, t: Path, name: str, steps):
    """Runs steps (lists of script lines); each step ends with a dump `obsN` and a wait, and the observer's sample
    taken a moment after that dump file appeared is the step's rectangle (the M42 build has no window rectangle in its
    dumps, so the rectangle comes from outside). Returns (exit code, [rect per step], dumps, journal, out)."""
    out = t / f"ui_{name}"
    out.mkdir()
    pause = 700
    lines = []
    for i, s in enumerate(steps):
        lines += s + [f"dump obs{i}", f"wait {pause}"]
    (out / "script.txt").write_text("\n".join(lines + ["click close", ""]), encoding="utf-8")
    cmd = [str(launcher), "--ui-test", str(out / "script.txt"), "--out", str(out), "--home", str(home),
           "--python", sys.executable, "--tools", str(TOOLS), "--releases", str(t / "releases.json")]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=m30.launcher_env())
    samples, stop = [], threading.Event()

    def watch():
        while not stop.is_set():
            samples.append((time.time(), window_rect(p.pid)))
            time.sleep(0.03)
    th = threading.Thread(target=watch, daemon=True)
    th.start()
    try:
        p.communicate(timeout=300)
    finally:
        stop.set()
        th.join()
    log = read(out / "ui_test.log") if (out / "ui_test.log").is_file() else ""
    rects = []
    for i in range(len(steps)):
        f = out / f"obs{i}.txt"
        if not f.is_file():
            rects.append(None)
            continue
        at = f.stat().st_mtime + pause / 2000
        later = [r for ts, r in samples if ts >= at and r is not None]
        rects.append(later[0] if later else None)
    dumps = {}
    for f in out.glob("*.txt"):
        if f.name != "script.txt":
            dumps[f.stem] = dict(x.split("=", 1) for x in read(f).splitlines() if "=" in x)
    return p.returncode, rects, dumps, log, out


def centre(r):
    return ((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)


def inside(r, work):
    return r[0] >= work[0] and r[1] >= work[1] and r[2] <= work[2] and r[3] <= work[3]


def win_of(d):
    return [int(x) for x in d.get("window", "0,0,0,0").split()[0].split(",")]


def work_of(d):
    m = re.search(r"work=(-?\d+),(-?\d+),(-?\d+),(-?\d+)", d.get("window", ""))
    return tuple(int(x) for x in m.groups()) if m else None


def placement_checks(launcher: Path, t: Path, home: Path, keep, baseline=False):
    pages = ["settings", "controls", "advanced", "mods", "settings", "controls", "settings"]
    for dpi in (96, 120, 144):
        steps = [[f"dpi {dpi}", f"dump start{dpi}"]] + [[f"page {p}"] for p in pages] + [[f"dump end{dpi}"]]
        code, rects, d, log, out = observed_run(launcher, home, t, f"place{dpi}", steps)
        if keep:
            shutil.copytree(out, Path(keep) / out.name, dirs_exist_ok=True)
        ok = code == 0 and None not in rects
        check(f"placement {dpi} DPI: run completed and every step observed", ok, f"code={code} rects={rects} {log[-300:]}")
        if not ok:
            continue
        by_page = list(zip(["settings"] + pages, rects[:len(pages) + 1]))  # the start (after the DPI) shows Settings
        print(f"  {dpi} DPI: " + "  ".join(f"{p}={r}" for p, r in by_page))
        work = work_of(d.get(f"start{dpi}", {})) if not baseline else None
        fits = [(p, r) for p, r in by_page if work is None or r[3] - r[1] <= work[3] - work[1]]
        cs = {centre(r) for _, r in fits}
        spread = max(abs(a[1] - b[1]) + abs(a[0] - b[0]) for a in cs for b in cs) if cs else 0
        check(f"placement {dpi} DPI: every page that fits keeps one centre (spread {spread} px)", spread <= 2,
              [(p, centre(r)) for p, r in fits])
        sets = [r for p, r in by_page if p == "settings"]
        check(f"placement {dpi} DPI: back on Settings the window is where it was", len(set(sets)) == 1, sets)
        if work:
            check(f"placement {dpi} DPI: inside the work area on every page", all(inside(r, work) for _, r in by_page),
                  (work, by_page))
    if baseline:
        return
    # A person moved the window: page changes keep it centred there; back on Settings it is exactly where they put it.
    steps = [["dump s0"], ["move 120 60", "dump moved"], ["page controls", "dump c"], ["page mods"], ["page settings", "dump s1"]]
    code, rects, d, log, out = observed_run(launcher, home, t, "placemoved", steps)
    ok = code == 0 and all(k in d for k in ("s0", "moved", "c", "s1"))
    check("placement: a moved window run completed", ok, log[-300:])
    if ok:
        moved = win_of(d["moved"])
        back = win_of(d["s1"])
        check("placement: a person's move is kept (user_placed=1) and Settings returns to that rectangle",
              "user_placed=1" in d["s1"]["window"] and moved == back and moved[:2] == [120, 60], (moved, back))
        c = d["c"]["window"]
        cx = re.search(r"centre=(-?\d+),(-?\d+) anchor=(-?\d+),(-?\d+)", c)
        work = work_of(d["c"])
        win = win_of(d["c"])
        check("placement: Controls after the move is centred on the moved window's centre, or held inside the work area",
              cx and (abs(int(cx.group(1)) - int(cx.group(3))) <= 1 and abs(int(cx.group(2)) - int(cx.group(4))) <= 1
                      or win[1] == work[1]), c)
    # A small screen (1366 x 768 at 150 %: a 728 px work area): every page inside it; a taller page scrolls.
    steps = [["dpi 144", "workarea 0 0 1366 728", "dump small_s"], ["page controls", "dump small_c"],
             ["page mods", "dump small_m"], ["page advanced", "dump small_a"],
             ["page controls", "endmove", "page settings", "dump small_s2"]]  # a title-bar click on a clamped page
    code, rects, d, log, out = observed_run(launcher, home, t, "placesmall", steps)
    if keep:
        shutil.copytree(out, Path(keep) / out.name, dirs_exist_ok=True)
    ok = code == 0 and all(k in d for k in ("small_s", "small_c", "small_m", "small_a", "small_s2"))
    check("placement: small work area run completed", ok, log[-300:])
    if ok:
        work = (0, 0, 1366, 728)
        wins = {k: win_of(d[k]) for k in ("small_s", "small_c", "small_m",
                                                                                     "small_a", "small_s2")}
        check("placement: on a 1366 x 728 work area at 144 DPI every page is inside it",
              all(inside(w, work) for w in wins.values()), wins)
        tall = [k for k in wins if "scroll=1" in d[k]["window"]]
        check("placement: a page taller than the work area scrolls (whole page reachable) and fills its height",
              all(wins[k][1] == 0 and wins[k][3] == 728 for k in tall) and "small_c" in tall, (tall, wins))
        check("placement: Settings returns to the same rectangle on the small screen, also after a title-bar click on a "
              "clamped page (no move, no new anchor)", wins["small_s"] == wins["small_s2"]
              and "user_placed=0" in d["small_s2"]["window"], (wins["small_s"], wins["small_s2"]))
    # D-082: a 1080p screen at 125 % and 150 % (a 1920 x 1032 work area), the desktop where the M33 test-mode exception
    # left Controls outside the real work area. D-120 expands Keyboard: it scrolls at 150%, while Controller fits.
    # The UI test takes the person's path, so the hook and the monitor
    # agree: every page inside, a taller page scrolls and fills the height, the others share one centre, and the
    # layout of the whole page (scrolled or not) holds.
    for dpi in (120, 144):
        steps = [[f"dpi {dpi}", "workarea 0 0 1920 1032", "dump w_s"], ["page keys", "dump w_c"],
                 ["wheel 100", "dump w_bottom"],
                 ["focus key:lstick_up", "wait 150", "wheel -100", "dump w_focus"], ["page pad", "dump w_pad"],
                 ["page advanced", "dump w_a"], ["page mods", "dump w_m"], ["page settings", "dump w_s2"]]
        code, rects, d, log, out = observed_run(launcher, home, t, f"place1032_{dpi}", steps)
        if keep:
            shutil.copytree(out, Path(keep) / out.name, dirs_exist_ok=True)
        keys = ("w_s", "w_c", "w_bottom", "w_focus", "w_pad", "w_a", "w_m", "w_s2")
        ok = code == 0 and all(k in d for k in keys)
        check(f"placement 1920 x 1032 at {dpi} DPI: run completed", ok, log[-300:])
        if not ok:
            continue
        work = (0, 0, 1920, 1032)
        wins = {k: win_of(d[k]) for k in keys}
        tall = [k for k in keys if "scroll=1" in d[k]["window"]]
        # Tabs use Fit() to keep the top-left; top-level pages use Fit(true) to share the anchor.
        cs = {centre(wins[k]) for k in keys if k not in tall and k != "w_pad"}
        spread = max(abs(a[1] - b[1]) + abs(a[0] - b[0]) for a in cs for b in cs) if cs else 0
        # D-080/D-082 retain clamping/centering; D-120 accepts only the expanded Keyboard tab scrolling here.
        expected_tall = ["w_c", "w_bottom", "w_focus"] if dpi == 144 else []
        check(f"placement 1920 x 1032 at {dpi} DPI: every page inside; only expanded Keyboard scrolls at 150% (D-120); the fitting pages "
              f"keep one centre (spread {spread} px); Settings returns to its rectangle",
              all(inside(w, work) for w in wins.values()) and tall == expected_tall
              and all(wins[k][1] == 0 and wins[k][3] == 1032 for k in tall) and spread <= 2
              and wins["w_s"] == wins["w_s2"], (tall, wins))
        check(f"placement 1920 x 1032 at {dpi} DPI: fixed buttons visible after focus and scroll, no clipped text, scroll reaches both ends",
              all(d[k].get("text_clipped") == "0" and d[k].get("in_view", "").startswith(
                  "save:1 play:1 close:1 restore:1") for k in ("w_c", "w_bottom", "w_focus", "w_pad"))
              and int(d["w_focus"]["in_view"].split("scroll_y=")[1]) == 0
              and (dpi != 144 or int(d["w_bottom"]["in_view"].split("scroll_y=")[1]) > 0),
              {k: (d[k].get("in_view"), d[k].get("text_clipped")) for k in ("w_c", "w_bottom", "w_focus", "w_pad")})
        check(f"placement 1920 x 1032 at {dpi} DPI: the whole page's layout holds on every page, the scrolled one too",
              all(m30.layout_ok(d[k]) for k in keys), {k: d[k].get("controls") for k in keys})
    # Key capture, an Esc and a status line never move the window.
    steps = [["page controls", "dump k0"], ["key x 0", "dump k1"], ["press 01", "dump k2"], ["click restore", "dump k3"]]
    code, rects, d, log, out = observed_run(launcher, home, t, "placekeys", steps)
    ok = code == 0 and all(k in d for k in ("k0", "k1", "k2", "k3"))
    check("placement: key capture run completed", ok, log[-300:])
    if ok:
        tops = {k: win_of(d[k])[:2] for k in ("k0", "k1", "k2", "k3")}
        check("placement: key capture, Esc and Restore defaults keep the window's top-left corner",
              len({tuple(v) for v in tops.values()}) == 1, tops)


def static_checks():
    src = read(TOOLS / "launcher" / "r3hd_launcher.cpp")
    check("launcher: no option to show the uncharacterised inputs", "Show the other controller buttons" not in src
          and "showAll" not in src and "kIdShowAll" not in src and 'L"showall"' not in src)
    # D-082: a UI test is clamped and scrolls on the monitor's work area as a person's window does (no M33 exception,
    # which a 1440p desktop never showed and a 1032 px work area did).
    check("launcher: a UI test clamps and scrolls like a person's window (no test-mode exception)",
          "bool scroll = h > maxH;" in src and "ptMaxTrackSize" not in src)
    check("launcher: page changes, DPI changes and the first show recentre on the anchor; a person's move sets it",
          src.count("Fit(true)") >= 4 and "case WM_EXITSIZEMOVE" in src and "CentreAnchor();" in src)
    check("launcher: the mod details are a read-only multi-line box that scrolls",
          re.search(r'g\.modDetail = Make\(L"EDIT", L"", ES_MULTILINE \| ES_READONLY \| ES_AUTOVSCROLL \| WS_VSCROLL', src)
          is not None)
    km = json.loads(read(ROOT / "config" / "controls" / "keymap.json"))
    hidden = [i["id"] for i in km["inputs"] if i.get("hidden")]
    check("keymap: only uncharacterised inputs remain hidden (D-120 exposes Look and menu up/down)",
          set(hidden) == {"back", "dpad_left", "dpad_right", "lstick_press",
                          "rstick_press", "guide"}, hidden)


def preset_checks(skip_runtime=False):
    reg = rs.load_registry()
    s = reg["settings"]["texture_orient"]
    # M49 (D-088): the player-facing help no longer names the status; the provisional flag and its record stay.
    check("registry: texture_orient Vanilla original, HD+ corrected, provisional (flag and validation record)",
          s["vanilla"] == "original" and s["hdplus"] == "corrected" and s.get("provisional") is True
          and "provisionally" not in s["help"] and "hdplus_candidate" not in s and "provisional" in s["validation"])
    h, v = rs.resolve(reg, "hdplus"), rs.resolve(reg, "vanilla")
    check("resolver: HD+ corrects the statues, with a provisional note; Vanilla does not and has no note",
          h["values"]["texture_orient"] == "corrected" and any("provisional" in w for w in h["warnings"])
          and v["values"]["texture_orient"] == "original" and not v["warnings"])
    c1 = rs.resolve(reg, settings={"schema": 3, "preset": "custom", "base": "hdplus", "overrides": {"texture_orient": "original"}})
    c2 = rs.resolve(reg, settings={"schema": 3, "preset": "custom", "base": "vanilla", "overrides": {"texture_orient": "corrected"}})
    check("resolver: Custom chooses it either way (off on HD+, on over Vanilla)",
          c1["values"]["texture_orient"] == "original" and c1["values"]["layer_coords"] == "separate"
          and c2["values"]["texture_orient"] == "corrected" and c2["values"]["layer_coords"] == "original")
    bad = json.loads(read(rs.REGISTRY))
    bad["settings"]["layer_coords"]["provisional"] = True
    bad["settings"]["layer_coords"]["hdplus"] = "original"
    with tempfile.TemporaryDirectory(prefix="r3hd_m43_reg_") as tmp:
        f = Path(tmp) / "registry.json"
        f.write_text(json.dumps(bad), encoding="utf-8")
        try:
            rs.load_registry(f)
            refused = False
        except rs.Refused as e:
            refused = e.code == "REGISTRY_INVALID"
    check("registry: provisional is refused on a setting whose HD+ value equals Vanilla", refused)

    if skip_runtime:
        skip("play.ps1 dry runs", "explicit --skip-runtime-dry-run; game may be running")
        return

    def dry(*args):
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PLAY), "-DryRun", *args],
                           capture_output=True, text=True, cwd=ROOT, timeout=300)
        return r.returncode, dict(re.findall(r"^(\w[\w ]*?)\s*: (.*)$", r.stdout, re.M))
    code, out = dry("-Preset", "hdplus")
    check("play.ps1: -Preset hdplus selects the correction and prints the provisional note",
          code == 0 and out.get("texture ori") == "corrected" and "provisional" in out.get("preset note", ""), out)
    code, out = dry("-Preset", "hdplus", "-TextureOrient", "original")
    check("play.ps1: -TextureOrient original turns it off in HD+ (rollback)", code == 0 and out.get("texture ori") == "original")
    code, out = dry("-Preset", "vanilla")
    check("play.ps1: Vanilla keeps the stored orientation", code == 0 and out.get("texture ori") == "original")


def diagnostics_checks(launcher: Path, t: Path, keep):
    # 1. a new installation: Standard, and nothing about diagnostics is stored
    home = m30.make_home(t, "diagfresh")
    stored = m30.settings(home)
    model = engine.launcher_model(home, releases=json.loads(read(t / "releases.json"))["releases"])
    row = next((r for r in model.splitlines() if r.startswith("SETTING\tdiagnostics\t")), "")
    check("diagnostics: a new installation stores no diagnostics choice and resolves Standard",
          "diagnostics" not in json.dumps(stored) and row.endswith("\tstandard"), (stored, row))
    # 2. an explicit Detailed with other choices beside it
    home = m30.make_home(t, "diagkept")
    explicit = {"schema": 3, "preset": "custom", "base": "vanilla", "overrides": {"texture_orient": "corrected"},
                "preferences": {"display": "fullscreen", "window_size": "1920x1080", "diagnostics": "detailed"},
                "keyboard": {"layout": "modern", "keys": {"x": ["F"], "lstick_press": ["E"]}}}
    (home / "settings.json").write_text(json.dumps(explicit, indent=1), encoding="utf-8")
    before = (home / "settings.json").read_bytes()
    pl, _tree, rels = engine.make_fixture(t)
    engine.repair(home, pl, releases=rels, log=lambda *_: None)
    check("diagnostics: a repair keeps the settings file byte for byte", (home / "settings.json").read_bytes() == before)
    pl2, tree2, rels2 = engine.make_fixture(t, version="0.30.0", tag=b"v2")
    try:
        engine.install(home, pl2, tree2, releases=rels2, log=lambda *_: None)
        check("diagnostics: an update keeps the settings file byte for byte", (home / "settings.json").read_bytes() == before)
    except engine.Refusal as e:
        skip("diagnostics: an update keeps the settings file", f"fixture update refused: {e}")
    engine.set_preset(home, "hdplus")
    after = m30.settings(home)
    check("diagnostics: a preset change keeps Detailed, the other preferences and the keys",
          after["preferences"] == explicit["preferences"] and after.get("keyboard") == explicit["keyboard"]
          and after["preset"] == "hdplus", after)
    if not launcher.is_file():
        check("launcher built", False)
        return
    m30.LAUNCHER = launcher
    code, d, log, out = m30.ui(home, t, "diag", "\n".join([
        "page advanced", "dump a0", "page settings", "profile vanilla", "click save", "dump saved_vanilla",
        "page advanced", "set diagnostics standard", "click save", "dump std", "click close", ""]))
    if keep:
        shutil.copytree(out, Path(keep) / out.name, dirs_exist_ok=True)
    ok = code == 0 and all(k in d for k in ("a0", "saved_vanilla", "std"))
    check("diagnostics: UI run completed", ok, log[-400:])
    if ok:
        check("diagnostics: the Settings window shows the saved Detailed (selectable)",
              d["a0"]["setting.diagnostics"] == "detailed enabled=1")
        s1 = None
        try:
            s1 = m30.settings(home)
        except Exception:
            pass
        check("diagnostics: choosing Standard there and saving changes only that choice",
              s1 is not None and s1["preset"] == "vanilla" and s1["preferences"].get("display") == "fullscreen"
              and s1["preferences"].get("window_size") == "1920x1080" and s1["preferences"].get("diagnostics", "standard") == "standard"
              and s1.get("keyboard") == explicit["keyboard"] and d["std"]["setting.diagnostics"] == "standard enabled=1", s1)


def controls_checks(launcher: Path, t: Path, home: Path, keep):
    km = json.loads(read(ROOT / "config" / "controls" / "keymap.json"))
    visible = [i["id"] for i in km["inputs"] if not i.get("hidden")]
    hidden = [i["id"] for i in km["inputs"] if i.get("hidden")]
    m30.LAUNCHER = launcher
    code, d, log, out = m30.ui(home, t, "controls", "\n".join([
        "page controls", "dump c0", "shot controls_96", "showall on", "dump c1", "layout original_pc", "dump orig",
        "click restore", "key x 0", "press 21", "click save", "dump saved", "dpi 144", "dump c144", "shot controls_144",
        "click close", ""]))
    if keep:
        shutil.copytree(out, Path(keep) / out.name, dirs_exist_ok=True)
    ok = code == 2 and all(k in d for k in ("c0", "c1", "orig", "saved", "c144"))  # 2: `showall` is an unknown command
    check("controls: UI run completed (the old `showall` command is refused)", ok and "unknown command" in log, log[-400:])
    if not ok:
        return
    check("controls: only characterised inputs are shown, with and without the old command",
          all(int(d[k]["key_rows_shown"]) == len(visible) for k in ("c0", "c1", "c144"))
          and all("visible=0" in d["c0"][f"key.{i}"] for i in hidden))
    o = rs.layout_keys(rs.load_keymap(), "original_pc")
    check("controls: a layout still sets the hidden inputs' keys (kept in the map)",
          all(d["orig"][f"key.{i}"].split(" caption=")[0] == ",".join(o.get(i, [])) or not o.get(i) for i in hidden))
    s = m30.settings(home)
    check("controls: capture with a swap and Save still work", s.get("keyboard", {}).get("layout") == "original_pc"
          and d["saved"]["key_capture"] == "" and "x" in s.get("keyboard", {}).get("keys", {}), s.get("keyboard"))
    check("controls: lays out without overlap at 96 and 144 DPI", m30.layout_ok(d["c0"]) and m30.layout_ok(d["c144"]),
          [d[k].get("controls") for k in ("c0", "c144")])


def mods_checks(launcher: Path, t: Path, keep, real_mod):
    home = m30.make_home(t, "modshome")
    game = home / "data" / "content" / "GAMEDATAbin"
    game.mkdir(parents=True, exist_ok=True)
    fix = bytearray(0x100)
    fix[0x40:0x48] = b"Options\0"
    (game / "fix.lvl").write_bytes(bytes(fix))
    slot = mods.text_slot(bytes(fix), 0x40)
    rels = json.loads(read(home / "data" / "intake.json")).get("release")

    def make(name, mid, title, version, description):
        z = t / f"{name}.zip"
        m = {"format": 1, "id": mid, "name": title, "version": version, "description": description,
             "target": {"title_id": "5841123F", "releases": [rels], "min_port_version": "0.1"},
             "overrides": [{"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": 0x40,
                            "slot_sha256": mods.sha256_bytes(slot), "text": "Ayarlar"}]}
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(f"{name}/mod.json", json.dumps(m))
        return z, m
    cases = []
    if real_mod and Path(real_mod).is_file():
        r = json.loads(Path(real_mod).read_text(encoding="utf-8"))  # metadata only: name, version, description
        cases.append(make("real", "ui.real", r["name"], r["version"], r["description"]))
    else:
        skip("mods: the real preview mod's metadata", "no --real-mod file")
    para = ("This synthetic description is long on purpose: it tests that the Settings window shows every word of a "
            "mod's description, however long, without cutting it off or covering the buttons below. ")
    long_desc = "\n".join([para * 3, para * 2, "Line three.", para * 4]) + " END-OF-DESCRIPTION"
    long_name = ("A mod with a very long name that keeps going well past the list box width " * 2)[:80]  # format maximum
    cases.append(make("long", "ui.long", long_name, "123.456.789.1011-preview.build.20261017.long", long_desc))
    cases.append(make("short", "ui.short", "Short", "1.0", "Short."))
    m30.LAUNCHER = launcher
    lines = ["page mods"] + [f"mod import {z}" for z, _ in cases]
    for _, m in cases:
        mid = m["id"]
        lines += [f"mod select {mid}", f"dump off_{mid}", f"shot off_{mid.split('.')[1]}", "mod toggle",
                  f"dump on_{mid}", f"shot on_{mid.split('.')[1]}"]
    lines += ["mod select ui.long", "dpi 144", "dump long144", "shot long_144", "dpi 96", "click close", ""]
    code, d, log, out = m30.ui(home, t, "mods", "\n".join(lines), env=m30.launcher_env())
    if keep:
        shutil.copytree(out, Path(keep) / out.name, dirs_exist_ok=True)
    ok = code == 0 and all(f"{s}_{m['id']}" in d for _, m in cases for s in ("off", "on")) and "long144" in d
    check("mods: UI run completed", ok, log[-600:])
    if not ok:
        return

    def flat(text):
        return " ".join(text.replace("\r", "").split())

    def box(dd):
        return {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", dd.get("mod_detail_box", ""))}
    windows = set()
    for _, m in cases:
        for state, word in (("off", "State: Off"), ("on", "State: Active")):
            dd = d[f"{state}_{m['id']}"]
            shown = flat(dd["mod_detail"])
            b = box(dd)
            check(f"mods: {m['id']} {state}: name, version, state and the whole description are in the box",
                  flat(m["name"]) in shown and m["version"] in shown and word in shown and shown.endswith(flat(m["description"])),
                  shown[:200])
            check(f"mods: {m['id']} {state}: every line is reachable (fits, or scrolls to its last line)",
                  b.get("lines", 0) <= b.get("fit", 0) or b.get("scroll_max", -1) + 1 >= b.get("lines", 0), b)
            check(f"mods: {m['id']} {state}: nothing overlaps or leaves the window", m30.layout_ok(dd), dd.get("controls"))
            windows.add(dd.get("client"))
    check("mods: the page keeps one size whatever the selection and its state", len(windows) == 1, windows)
    b = box(d["long144"])
    check("mods: the long description at 144 DPI scrolls to its end and the layout holds",
          b.get("lines", 0) > b.get("fit", 0) and b.get("scroll_max", -1) + 1 >= b.get("lines", 0)
          and m30.layout_ok(d["long144"]), (b, d["long144"].get("controls")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--launcher", default=str(LAUNCHER))
    ap.add_argument("--real-mod", help="a mod.json whose name / version / description are used (read only)")
    ap.add_argument("--keep", help="copy the UI runs' dumps and screenshots here (private)")
    ap.add_argument("--placement-only", action="store_true", help="only the placement runs (also for an older build)")
    ap.add_argument("--skip-runtime-dry-run", action="store_true", help="skip real-build dry runs while a person plays")
    a = ap.parse_args()
    launcher = Path(a.launcher)
    saved = {k: os.environ.get(k) for k in engine.HOOKS}
    with tempfile.TemporaryDirectory(prefix="r3hd_m43_") as tmp:
        t = Path(tmp)
        sys32 = t / "sys32"
        sys32.mkdir()
        for n in engine.VC_RUNTIME:
            (sys32 / n).write_bytes(b"x")
        os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0", R3HD_INSTALL_FAKE_LAUNCHER="0")
        try:
            home = m30.make_home(t, "home")
            if a.placement_only:
                placement_checks(launcher, t, home, a.keep, baseline=True)
            else:
                static_checks()
                preset_checks(a.skip_runtime_dry_run)
                if not launcher.is_file():
                    check(f"launcher built ({launcher})", False)
                else:
                    placement_checks(launcher, t, home, a.keep)
                    controls_checks(launcher, t, m30.make_home(t, "ctlhome"), a.keep)
                    diagnostics_checks(launcher, t, a.keep)
                    mods_checks(launcher, t, a.keep, a.real_mod)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    print(f"M43_REGRESSION {'PASS' if failures == 0 else 'FAIL'} checks={checks} failures={failures} skipped={skipped}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
