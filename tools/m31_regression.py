#!/usr/bin/env python3
"""M31 (D-068): regression of the installer and launcher refinements. Starts no game and shows nothing on the
person's desktop.

  * controls: the runtime's 25 keybind settings with Escape on B (M10); since M32 the keymap
    (config/controls/keymap.json, tools/m32_regression.py) replaces the read-only controls file
  * settings: install default (fullscreen for a new installation only), hidden advanced options kept, the window
    size that requires the window mode, diagnostics; the registry rules refuse malformed entries
  * play.ps1: the window plan (physical size, DPI, fit to the work area) with made-up displays, the session
    retention (timestamp folders only, never save_history), the diagnostics arguments; -DryRun end to end when the
    built executable and the extracted data exist (skipped, never passed, without them)
  * runtime: tools/m31_runtime_patch.py applied (guest video mode apart from the window size, sampled known lines),
    the built binaries carry it and the project icon
  * icon: tools/make_r3hd_icon.py draws it deterministically (a build output); the launcher and r3hd.exe carry it
  * installer wiring: progress page, cancellation, desktop shortcut task, icon, payload
  * the launcher (private/work/launcher) on a private desktop (--ui-test): the window size follows the display mode,
    the Controls page (the M32 keyboard map) lays out at 96 and 144 DPI
usage: m31_regression.py [--keep DIR]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import make_r3hd_icon as icon  # noqa: E402
import r3hd_installer as engine  # noqa: E402
import r3hd_settings as rs  # noqa: E402

SDK = ROOT / "external" / "rexglue-sdk"
MNK = SDK / "src" / "input" / "mnk" / "mnk_input_driver.cpp"
LAUNCHER = ROOT / "private" / "work" / "launcher" / "r3hd_launcher.exe"
BUILD = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
GAME = Path(os.environ.get("R3HD_GAME_DIR") or ROOT / "private" / "extracted" / "5841123F")
checks, skipped = [], []


def check(name, cond, detail=""):
    checks.append((name, bool(cond)))
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  ({detail})" if detail and not cond else ""))


def skip(name, why):
    skipped.append(name)
    print(f"skip {name}  ({why})")


def refused(fn, code):
    try:
        fn()
    except (rs.Refused, engine.Refusal) as e:
        return e.code == code
    return False


def powershell(script: str):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


# --- controls ------------------------------------------------------------------------------------------------------

def controls_checks():
    """M32 (D-069): the read-only Controls file of M31 is replaced by config/controls/keymap.json, whose ties to the
    SDK sources, layouts and launcher rows tools/m32_regression.py checks. What M31 needed of the runtime stays."""
    if not MNK.is_file():
        check("controls: the SDK input source exists (external/rexglue-sdk; run the build first)", False, str(MNK))
        return
    src = MNK.read_text(encoding="utf-8", errors="replace")
    binds = dict(re.findall(r'REXCVAR_DEFINE_STRING\(keybind_(\w+),\s*"([^"]*)"', src))
    check("controls: the runtime defines the 26 keybind settings (M49: walk)", len(binds) == 26 and "walk" in binds, sorted(binds))
    check("controls: the patched source maps Escape to pad B (M10)", "Escape" in binds.get("b", "").split(","))
    check("controls: the M31 read-only file is gone; the keymap replaces it (M32)",
          not (ROOT / "config" / "controls" / "controls.json").exists()
          and (ROOT / "config" / "controls" / "keymap.json").is_file())
    defn = json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))
    check("controls: the keymap is in the installer payload", defn["app_files"].get("app/config/controls/keymap.json")
          == "config/controls/keymap.json" and "app/config/controls/controls.json" not in defn["app_files"])
    return binds


# --- settings ------------------------------------------------------------------------------------------------------

def settings_checks():
    reg = rs.load_registry()
    S = reg["settings"]
    check("registry: the install defaults are fullscreen and (D-108) both DualSense options on; display stays windowed",
          rs.install_defaults(reg) == {"display": "fullscreen", "dualsense_light": "on", "dualsense_trigger": "on"} and S["display"]["vanilla"] == "windowed")
    check("registry: cursor and save clock are hidden preferences with their defaults (auto, local)",
          S["cursor"].get("ui") == S["save_clock"].get("ui") == "hidden" and S["cursor"]["vanilla"] == "auto"
          and S["save_clock"]["vanilla"] == "local")
    check("registry: the window size is a preference that requires the window mode, default auto",
          rs.scope(S["window_size"]) == "preference" and S["window_size"]["requires"] == {"display": "windowed"}
          and S["window_size"]["vanilla"] == "auto"
          and S["window_size"]["values"] == ["auto", "1280x720", "1600x900", "1920x1080", "2560x1440"])
    check("registry: diagnostics standard | detailed, default standard",
          S["diagnostics"]["values"] == ["standard", "detailed"] and S["diagnostics"]["vanilla"] == "standard")
    check("registry: no 1080p rendering resolution (fractional scale not supported, D-068)",
          S["render_scale"]["values"] == ["auto", "1", "2", "3"])
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        base = json.loads((ROOT / "config" / "settings" / "registry.json").read_text(encoding="utf-8"))
        for i, (key, field, value) in enumerate([("layer_coords", "install_default", "separate"),
                                                 ("display", "install_default", "borderless"),
                                                 ("cursor", "ui", "invisible"),
                                                 ("window_size", "requires", {"display": "maximised"}),
                                                 ("window_size", "requires", {"nothing": "x"})]):
            bad = json.loads(json.dumps(base))
            bad["settings"][key][field] = value
            (t / f"r{i}.json").write_text(json.dumps(bad), encoding="utf-8")
            check(f"registry refusal {i}: {key}.{field}={value!r}", refused(lambda: rs.load_registry(t / f"r{i}.json"),
                                                                            "REGISTRY_INVALID"))
    keys = [o["key"] for o in engine.describe_options()]
    check("the launcher and configure show neither cursor nor save clock", "cursor" not in keys and "save_clock" not in keys)
    v = rs.resolve(reg, settings={"schema": 2, "preset": "hdplus", "preferences": {"cursor": "visible", "save_clock": "utc"}})
    check("a stored cursor / save clock choice still resolves (legacy settings)", v["values"]["cursor"] == "visible"
          and v["values"]["save_clock"] == "utc")
    d = rs.make_settings(reg, "vanilla", pairs=["display=fullscreen", "window_size=1920x1080"],
                         keep_preferences={"cursor": "visible", "save_clock": "utc"})
    check("saving shown settings keeps the hidden choices", d["preferences"] == {"cursor": "visible", "display": "fullscreen",
                                                                                  "save_clock": "utc", "window_size": "1920x1080"})


# --- play.ps1 ------------------------------------------------------------------------------------------------------

def play_function(name: str) -> str:
    play = (TOOLS / "play.ps1").read_text(encoding="utf-8")
    m = re.search(r"^function " + name + r"\b.*?(?=^function |\Z)", play, re.M | re.S)
    return m.group(0)


def window_plan(size, area):
    a = "$null" if area is None else ("[ordered]@{ width = %d; height = %d; dpi = %d; frame_width = %d; frame_height = %d }" % area)
    code, out = powershell(play_function("Get-WindowPlan") + f"\n$p = Get-WindowPlan '{size}' ({a})\n"
                           "\"$($p.width) $($p.height) $($p.logical_width) $($p.logical_height) $($p.fitted)\"")
    return out.strip().splitlines()[-1] if code == 0 and out.strip() else f"error {out[-300:]}"


def play_checks():
    play = (TOOLS / "play.ps1").read_text(encoding="utf-8")
    # (work area w, h, dpi, frame w, frame h): 2560x1440 at 100 % with a taskbar; 2560x1440 at 150 %; 1920x1080 at
    # 125 %; a 1366x768 laptop.
    cases = [
        ("1920x1080", (2560, 1392, 96, 16, 39), "1920 1080 1920 1080 False"),
        ("2560x1440", (2560, 1392, 96, 16, 39), "1920 1080 1920 1080 True"),
        ("1920x1080", (2560, 1392, 144, 22, 54), "1920 1080 1280 720 False"),
        ("2560x1440", (2560, 1392, 144, 22, 54), "1920 1080 1280 720 True"),
        ("1920x1080", (1920, 1032, 120, 20, 46), "1600 900 1280 720 True"),
        ("1280x720", (1366, 728, 96, 16, 39), "1222 688 1222 688 True"),
        ("auto", (2560, 1392, 144, 22, 54), "1920 1080 0 0 False"),
        ("auto", None, "1280 720 0 0 False"),
        ("1600x900", None, "1600 900 1600 900 False"),
    ]
    for size, area, want in cases:
        got = window_plan(size, area)
        check(f"window plan {size} on {area}: {want}", got == want, got)
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for i in range(12):
            (t / f"20261014-1200{i:02d}").mkdir()
        for name in ("save_history", "notes", "2026-10-14"):
            (t / name).mkdir()
        code, out = powershell(play_function("Get-SessionsToPrune") + f"\n(Get-SessionsToPrune '{t}' 9) | ForEach-Object Name")
        check("retention: the oldest timestamp folders beyond the newest 9 (+ this session = 10), nothing else",
              code == 0 and out.split() == [f"20261014-1200{i:02d}" for i in range(3)], out[-300:])
        code, out = powershell(play_function("Get-SessionsToPrune") + f"\n@(Get-SessionsToPrune '{t}' 20).Count")
        check("retention: nothing when there are fewer", code == 0 and out.strip() == "0", out)
    check("diagnostics: standard limits rotated logs; detailed sets R3HD_DIAGNOSTICS (cleared before every launch)",
          "if ($Diagnostics -eq 'standard') { $arguments += '--log_max_files=2' }" in play
          and "if ($Diagnostics -eq 'detailed') { $env:R3HD_DIAGNOSTICS = 'detailed' }" in play
          and "'R3HD_DIAGNOSTICS'" in play.split("$testOnly = ")[1].split("\n$saved")[0])
    check("retention: only an installed home, before the new session is made, never in a dry run",
          "$prune = if ($installed) {" in play and play.index("foreach ($old in $prune)") > play.index("if ($DryRun) {")
          and "save_history" not in play_function("Get-SessionsToPrune"))
    check("window: -Width / -Height win; fullscreen passes no window size",
          "if ($Width -gt 0 -and $Height -gt 0) {" in play and "} elseif ($Display -ne 'fullscreen') {" in play)
    if not ((BUILD / "r3hd.exe").is_file() and (GAME / "Default.xex").is_file()):
        skip("play.ps1 -DryRun in a synthetic installed home", "needs the built executable and the extracted data")
        return
    with tempfile.TemporaryDirectory(prefix="r3hd_m31_play_") as tmp:
        home = Path(tmp) / "home"
        (home / "sessions").mkdir(parents=True)
        (home / "installer.json").write_text("{}", encoding="utf-8")
        for i in range(11):
            (home / "sessions" / f"20261014-1300{i:02d}").mkdir()
        (home / "save_history" / "20261014-130000").mkdir(parents=True)

        def dry(prefs):
            (home / "settings.json").write_text(json.dumps({"schema": 2, "preset": "vanilla", "preferences": prefs}),
                                                encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if not k.startswith("R3HD_")}
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TOOLS / "play.ps1"),
                                "-UserHome", str(home), "-BinDir", str(BUILD), "-GameDir", str(GAME), "-DryRun"],
                               capture_output=True, text=True, env=env, timeout=300)
            return r.returncode, r.stdout + r.stderr

        code, out = dry({"window_size": "1600x900"})
        check("dry run: a saved window size is used in Window mode (physical size, fitted or as asked)",
              code == 0 and re.search(r"window     : \d+x\d+ \(", out) and "--window_width=" in out
              and "--log_max_files=2" in out, out[-400:])
        check("dry run: an installed home would keep 10 sessions (11 + 1 -> remove 2); nothing removed in a dry run",
              "would remove 2" in out and len(list((home / "sessions").iterdir())) == 11
              and (home / "save_history" / "20261014-130000").is_dir(), out[-300:])
        code, out = dry({"display": "fullscreen", "window_size": "1600x900", "diagnostics": "detailed"})
        check("dry run: fullscreen ignores the window size; detailed diagnostics keep the runtime's rotation",
              code == 0 and "--window_width=" not in out and "window     : not used (fullscreen)" in out
              and "--log_max_files" not in out and "diagnostics: detailed" in out, out[-400:])


# --- runtime, icon, installer ----------------------------------------------------------------------------------------

def runtime_checks():
    bat = (TOOLS / "build_milestone8.bat").read_text(encoding="utf-8")
    check("build: the M31 patch replays after M26, the M31 prepare after M26's, this regression in the build",
          bat.index("m26_runtime_patch.py") < bat.index("m31_runtime_patch.py") < bat.index("cmake -S external")
          and bat.index("m26_prepare.py") < bat.index("m31_prepare.py") < bat.index("rexglue.exe")
          and "python tools\\m31_regression.py || exit /b 1" in bat)
    video = (SDK / "src" / "kernel" / "xboxkrnl" / "xboxkrnl_video.cpp")
    cache = (SDK / "src" / "graphics" / "pipeline" / "texture" / "cache.cpp")
    if not video.is_file():
        check("runtime: the SDK checkout exists", False)
        return
    v, c = video.read_text(errors="replace"), cache.read_text(errors="replace")
    check("runtime: the window size no longer sets the guest video mode",
          'HasNonDefaultValue("window_width")' not in v and 'HasNonDefaultValue("window_height")' not in v
          and '"M31 video_mode={}x{}' in v)
    check("runtime: both invalid-fetch lines are sampled in a standard playtest session",
          c.count("m31diag::Sample(") == 2 and '"M31 sampled invalid_fetch count=' in c
          and '"M31 sampled invalid_type_warning count=' in c and "#include <rex/m31_diagnostics.h>" in c)
    header = SDK / "include" / "rex" / "m31_diagnostics.h"
    check("runtime: the installed header is tools/m31_diagnostics.h",
          header.is_file() and header.read_bytes() == (TOOLS / "m31_diagnostics.h").read_bytes())
    h = (TOOLS / "m31_diagnostics.h").read_text(encoding="utf-8")
    check("runtime: sampling needs R3HD_PLAY and is off with R3HD_DIAGNOSTICS=detailed (hidden runs keep every line)",
          'std::getenv("R3HD_PLAY")' in h and 'std::strcmp(level, "detailed") == 0' in h)
    dll = BUILD / "rexruntime.dll"
    gpu = BUILD / "rexgpu-xenos.dll"
    if dll.is_file() and gpu.is_file():
        both = dll.read_bytes() + gpu.read_bytes()
        check("binaries: the built runtime carries the M31 lines", b"M31 video_mode=" in both
              and b"M31 sampled invalid_fetch count=" in both)
    else:
        skip("binaries: the built runtime carries the M31 lines", "no build")


def icon_checks():
    data = icon.build()
    check("icon: make_r3hd_icon.py draws the same bytes twice (deterministic; a build output, not committed)",
          data == icon.build() and not list((TOOLS / "launcher").glob("*.ico")))
    # Pinned MIT text SVGs replace the former project-drawn glove; no runtime dependency or game art.
    provenance = (TOOLS / "icons/fluent/README.md").read_text(encoding="utf-8")
    sources = list((TOOLS / "icons/fluent").glob("*.svg"))
    check("icon: pinned licensed Fluent sources match their recorded LF hashes",
          len(sources) == 7 and all(hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                                   in provenance for p in sources))
    check("icon: Settings gear is distinct from application fallback at every size",
          all(icon.render(size, "settings") != icon.render(size, "game") for size in icon.SIZES))
    launcher_source = (TOOLS / "launcher/r3hd_launcher.cpp").read_text(encoding="utf-8")
    check("icon: Settings window uses its shortcut's resource 2",
          "MAKEINTRESOURCEW(2), IMAGE_ICON" in launcher_source)
    n = int.from_bytes(data[4:6], "little")
    images = []
    for i in range(n):
        size = int.from_bytes(data[6 + 16 * i + 8:6 + 16 * i + 12], "little")
        off = int.from_bytes(data[6 + 16 * i + 12:6 + 16 * i + 16], "little")
        images.append(data[off:off + size])
    for name, exe in (("launcher", LAUNCHER), ("r3hd.exe", BUILD / "r3hd.exe")):
        if exe.is_file():
            blob = exe.read_bytes()
            check(f"icon: {name} carries every image of the icon", all(img in blob for img in images))
        else:
            skip(f"icon: {name} carries every image of the icon", "not built")
    rc = (TOOLS / "launcher" / "r3hd_launcher.rc").read_text(encoding="utf-8")
    bat = (TOOLS / "launcher" / "build_launcher.bat").read_text(encoding="utf-8")
    check("icon: the launcher's first icon resource is the project icon, drawn by its build",
          '1 ICON "r3hd.ico"' in rc and 'python tools\\make_r3hd_icon.py --out "%OUT%\\r3hd.ico"' in bat)
    prep = (TOOLS / "m31_prepare.py").read_text(encoding="utf-8")
    check("icon: r3hd.exe gets it through m31_prepare.py", "make_r3hd_icon.py" in prep and "r3hd_icon.rc" in prep)
    cmake = ROOT / "private" / "work" / "rex" / "CMakeLists.txt"
    if cmake.is_file():
        check("icon: the r3hd target lists the resource", '/r3hd_icon.rc")' in cmake.read_text(encoding="utf-8"))

def installer_checks():
    iss = (TOOLS / "installer" / "r3hd_setup.iss").read_text(encoding="utf-8")
    check("setup: the project icon (the launcher build's output)", "SetupIconFile={#IconFile}" in iss
          and '#define IconFile "..\\..\\private\\work\\launcher\\r3hd.ico"' in iss)
    check("setup: an optional desktop shortcut task, checked by default",
          re.search(r'^Name: "desktopicon"; Description: "[^"]+"; GroupDescription: "[^"]+"$', iss, re.M)
          and 'Check: DesktopShortcut' in iss and "UsePreviousTasks=no" in iss)
    check("setup: a silent repair or update follows the recorded choice; a deleted shortcut counts as declined",
          "Result := RecordedDesktop = '1'" in iss and "not FileExists(DesktopLink) then RecordedDesktop := '0'" in iss
          and "WizardSelectTasks('!desktopicon')" in iss and "--desktop-shortcut 1" in iss)
    check("setup: the install runs with progress lines and a cancel file; ExecAndLogOutput delivers them",
          "--progress --cancel-file" in iss and "ExecAndLogOutput(PayloadPath('app\\python\\python.exe')" in iss
          and "@EngineOutput" in iss)
    check("setup: the bar follows the engine's permille only (never a made-up value) and never goes back",
          "ProgressPage.SetProgress(LastPermille, 1000)" in iss and "if Permille > LastPermille then LastPermille := Permille;" in iss
          # M48-P: the third is the playtest steps' full bar, after the engine has ended
          and iss.count("SetProgress(") == 3 and "ProgressPage.SetProgress(1000, 1000);" in iss)
    check("setup: Cancel is offered until the commit; the wizard's Cancel asks the engine to stop",
          "if Phase = 'commit' then begin" in iss and "procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);" in iss
          and "if CancelRequested or Committing or not EngineRunning then Exit;" in iss)
    check("setup: the cancel test hook works only in test mode", "if IsTestMode then CancelAt := StrToIntDef(ExpandConstant('{param:CANCELAT|-1}'), -1);" in iss)
    check("setup: version 0.31.0 or later (1.0.0)", re.search(r'#define AppVersion "(0\.(3[1-9]|[4-9][0-9])\.0(-private)?|[1-9][0-9]*\.[0-9]+\.[0-9]+)"', iss))
    check("engine: CANCELLED has advice and the cancellation point is before any write into HOME",
          "CANCELLED" in engine.ADVICE and engine.Cancelled("x").code == "CANCELLED")
    src = (TOOLS / "r3hd_installer.py").read_text(encoding="utf-8")
    body = src.split("def _install(")[1].split("\ndef ")[0]
    check("engine: progress.commit() comes after the data staging and before the settings / state writes",
          body.index("stage_data(") < body.index("progress.commit()") < body.index('write_json(staging / "settings.json"')
          < body.index("cleaned = commit(home, staging, items, log)"))


# --- the launcher ----------------------------------------------------------------------------------------------------

def launcher_checks(keep, controls):
    if not LAUNCHER.is_file():
        check("launcher built (tools\\launcher\\build_launcher.bat)", False)
        return
    import m30_launcher_regression as m30  # its synthetic-home and private-desktop helpers (no checks run on import)
    saved = {k: os.environ.get(k) for k in engine.HOOKS}
    with tempfile.TemporaryDirectory(prefix="r3hd_m31_ui_") as tmp:
        t = Path(tmp)
        sys32 = t / "sys32"
        sys32.mkdir()
        for n in engine.VC_RUNTIME:
            (sys32 / n).write_bytes(b"x")
        os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0", R3HD_INSTALL_FAKE_LAUNCHER="0")
        try:
            home = m30.make_home(t, "home")
            script = "\n".join(["dump initial", "set display windowed", "dump windowed", "set window_size 1920x1080",
                                "set display fullscreen", "dump fullscreen", "click save", "dump saved", "shot settings_96",
                                "page controls", "dump controls", "shot controls_96", "dpi 144", "dump controls144",
                                "shot controls_144", "page settings", "dump back", "click close", ""])
            code, d, log, out = m30.ui(home, t, "m31", script)
            check("UI run completed", code == 0 and all(k in d for k in ("initial", "windowed", "fullscreen", "saved",
                                                                          "controls", "controls144", "back")), log[-400:])
            if code == 0 and "back" in d:
                check("UI: a new installation shows fullscreen; the window size is off then",
                      d["initial"]["setting.display"] == "fullscreen enabled=1"
                      and d["initial"]["setting.window_size"] == "auto enabled=0")
                check("UI: Window mode turns the window size on", d["windowed"]["setting.window_size"] == "auto enabled=1")
                check("UI: back to fullscreen, the chosen size is kept but off",
                      d["fullscreen"]["setting.window_size"] == "1920x1080 enabled=0")
                check("UI: saved through the engine; both preferences stored",
                      m30.settings(home)["preferences"] == {"display": "fullscreen", "window_size": "1920x1080",
                                                            "ui_language": "en", "dualsense_light": "on", "dualsense_trigger": "on"})  # D-092 retains explicit English
                check("UI: no cursor or save clock setting is shown", not any(k.startswith(("setting.cursor", "setting.save_clock"))
                                                                              for k in d["initial"]))
                check("UI: the Controls page is the keyboard map (its rows: tools/m32_regression.py)",
                      d["controls"]["page"] == "controls" and int(d["controls"].get("key_rows", "0")) > 0)
                check("UI: Controls page and settings page lay out without overlap at 96 and 144 DPI",
                      all(m30.layout_ok(d[k]) for k in ("saved", "controls", "controls144", "back")),
                      " / ".join(d[k].get("controls", "") for k in ("saved", "controls", "controls144", "back")))
                check("UI: back on the settings page", d["back"]["page"] == "settings" and "page: controls" in log)
            if keep:
                shutil.copytree(out, Path(keep) / "ui_m31", dirs_exist_ok=True)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keep")
    ap.add_argument("--skip-runtime-dry-run", action="store_true", help="skip real-build dry runs while a person plays")
    a = ap.parse_args()
    controls = controls_checks()
    settings_checks()
    if a.skip_runtime_dry_run:
        skip("play.ps1 dry runs", "explicit --skip-runtime-dry-run; game may be running")
    else:
        play_checks()
    runtime_checks()
    icon_checks()
    installer_checks()
    if controls:
        launcher_checks(a.keep, controls)
    failed = sum(not ok for _, ok in checks)
    print(f"M31_REGRESSION {'PASS' if not failed else 'FAIL'} checks={len(checks)} failures={failed} skipped={len(skipped)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
