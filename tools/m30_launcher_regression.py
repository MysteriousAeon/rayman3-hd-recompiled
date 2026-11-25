#!/usr/bin/env python3
"""M30 (D-067): regression of the Settings launcher, the preference scope and the simplified installer wiring.

Starts no game and shows nothing on the person's desktop:
  * resolver: preference scope (display mode, rendering resolution, cursor, save clock) is kept across presets and
    stored only when not the default; schema 1 files stay valid; precedence vanilla < preset < custom overrides <
    preferences < explicit launcher parameters; refusals
  * play.ps1 -DryRun: -Display / -Fullscreen and a saved display preference (needs the built executable and the
    extracted data, like m28_portable_regression.py; skipped, never passed, without them)
  * the launcher binary (private/work/launcher, built by tools/launcher/build_launcher.bat): reproducible build,
    GUI subsystem, no build-machine path, no setting of its own in the source; then, against synthetic installations
    made with the engine's own fixtures, its model, its Play path as a dry run and scripted UI runs on a private
    desktop (--ui-test: a desktop of its own that no one sees; never the person's desktop)
  * wiring: the Inno Setup script (no technical options page, launcher shortcuts, AppMutex), payload definition,
    allowlist role
usage: m30_launcher_regression.py [--keep DIR] [--no-rebuild]   (--keep: the UI screenshots and dumps are copied)
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import r3hd_installer as engine  # noqa: E402
import r3hd_release_audit as audit  # noqa: E402
import r3hd_settings as rs  # noqa: E402

LAUNCHER = ROOT / "private" / "work" / "launcher" / "r3hd_launcher.exe"
BUILD = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
GAME = Path(os.environ.get("R3HD_GAME_DIR") or ROOT / "private" / "extracted" / "5841123F")
checks, skipped = [], []


def check(name, cond, detail=""):
    checks.append((name, bool(cond)))
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  ({detail})" if detail and not cond else ""))


def refused(fn, code):
    try:
        fn()
    except rs.Refused as e:
        return e.code == code
    return False


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("R3HD_")}
    env.update(extra)
    return env


# --- resolver: the preference scope -------------------------------------------------------------------------------

def resolver_checks():
    reg = rs.load_registry()
    S = reg["settings"]
    prefs = {k for k, s in S.items() if rs.scope(s) == "preference"}
    check("registry: display, rendering resolution, cursor and save clock are preferences (M31: window size, diagnostics)",
          prefs == {"display", "window_size", "render_scale", "cursor", "save_clock", "diagnostics",
                      "gameplay_subtitles", "game_language", "ui_language", "discord_presence", "dualsense_light",
                      "dualsense_trigger", "dualsense_trigger_strength", "dualsense_speaker", "dualsense_speaker_volume", "mouse_camera", "mouse_sensitivity",
                      "mouse_buttons", "controller_prompts", "display_vsync", "hud_toggle"})  # independent Settings preferences (D-138: mouse; D-220: V-Sync; D-301: HUD toggle)
    check("registry: the corrections stay preset settings; HD+ = layer_coords separate, texture_orient corrected (M43)",
          rs.scope(S["layer_coords"]) == rs.scope(S["texture_orient"]) == "preset"
          and S["layer_coords"]["hdplus"] == "separate" and S["texture_orient"]["hdplus"] == "corrected")
    adjustable = [k for k, s in S.items() if s["category"] != "mandatory"]
    check("registry: every adjustable setting has a group, a short label, help and a label for every value",
          all(S[k].get("group") in reg["groups"] and S[k].get("help") and len(S[k]["label"]) <= 60
              and ("range" in S[k] or sorted(S[k].get("value_labels", {})) == sorted(S[k]["values"]))  # D-108: a slider
              for k in adjustable))
    check("registry: mandatory behaviour has no group (never shown) and is never a preference",
          all(not s.get("group") and rs.scope(s) == "preset" for s in S.values() if s["category"] == "mandatory"))
    check("registry: rendering resolution labels name 720p / 1440p / 2160p for scales 1 / 2 / 3",
          [S["render_scale"]["value_labels"][v].split()[0] for v in ("1", "2", "3")] == ["720p", "1440p", "2160p"])
    check("registry: three presets with a name and a one-line text", sorted(reg["preset_ui"]) == ["custom", "hdplus", "vanilla"]
          and all(p["name"] and p["text"] for p in reg["preset_ui"].values()))
    v = rs.resolve(reg, settings={"schema": 2, "preset": "vanilla", "preferences": {"render_scale": "2", "display": "fullscreen"}})
    check("a fixed preset takes preferences, keeps its label", v["label"] == "vanilla" and v["values"]["render_scale"] == "2"
          and v["values"]["display"] == "fullscreen" and v["sources"]["render_scale"] == "preference"
          and v["values"]["layer_coords"] == "original")
    h = rs.resolve(reg, settings={"schema": 2, "preset": "hdplus", "preferences": {"cursor": "visible"}})
    check("HD+ with a preference keeps the HD+ corrections", h["values"]["layer_coords"] == "separate" and h["label"] == "hdplus")
    e = rs.resolve(reg, settings={"schema": 2, "preset": "hdplus", "preferences": {"display": "fullscreen"}},
                   explicit={"display": "windowed", "render_scale": "1"})
    check("an explicit launcher parameter wins over a preference and does not relabel the preset",
          e["values"]["display"] == "windowed" and e["values"]["render_scale"] == "1" and e["label"] == "hdplus")
    old = rs.resolve(reg, settings={"schema": 1, "preset": "custom", "base": "hdplus",
                                    "overrides": {"render_scale": "3", "texture_orient": "corrected"}})
    check("a schema 1 (M29) custom file resolves as before; its preference is read as one",
          old["values"]["render_scale"] == "3" and old["sources"]["render_scale"] == "preference"
          and old["values"]["texture_orient"] == "corrected" and old["sources"]["texture_orient"] == "custom")
    check("preferences_of reads both forms", rs.preferences_of(reg, {"schema": 1, "overrides": {"render_scale": "3",
                                                                                               "layer_coords": "separate"}})
          == {"render_scale": "3"})
    d = rs.make_settings(reg, "hdplus", pairs=["render_scale=auto", "Display=fullscreen"], keep_preferences={"render_scale": "2",
                                                                                                         "cursor": "visible"})
    check("make_settings: kept preferences, a named one replaced, a default not stored, launcher names accepted",
          d == {"schema": 3, "preset": "hdplus", "preferences": {"cursor": "visible", "display": "fullscreen"}})
    c = rs.make_settings(reg, "custom", "hdplus", ["texture_orient=original", "render_scale=2"])
    check("make_settings: custom overrides and preferences are stored apart",
          c["overrides"] == {"texture_orient": "original"} and c["preferences"] == {"render_scale": "2"} and c["base"] == "hdplus")
    for i, (fn, code) in enumerate([
        (lambda: rs.resolve(reg, settings={"schema": 2, "preset": "vanilla", "preferences": {"layer_coords": "separate"}}),
         "NOT_A_PREFERENCE"),
        (lambda: rs.resolve(reg, settings={"schema": 2, "preset": "vanilla", "preferences": {"revisit": "original"}}),
         "NOT_A_PREFERENCE"),
        (lambda: rs.resolve(reg, settings={"schema": 2, "preset": "vanilla", "preferences": {"render_scale": "4"}}),
         "INVALID_VALUE"),
        (lambda: rs.resolve(reg, settings={"schema": 2, "preset": "vanilla", "preferences": ["x"]}), "SETTINGS_INVALID"),
        (lambda: rs.make_settings(reg, "vanilla", pairs=["layer_coords=separate"]), "OVERRIDES_NEED_CUSTOM"),
    ]):
        check(f"refusal {i}: {code}", refused(fn, code))
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "s1.json").write_text(json.dumps({"schema": 1, "preset": "vanilla", "preferences": {}}), encoding="utf-8")
        check("a schema 1 file cannot carry preferences", refused(lambda: rs.load_settings_file(t / "s1.json"), "SETTINGS_INVALID"))
        bad = json.loads((ROOT / "config" / "settings" / "registry.json").read_text(encoding="utf-8"))
        bad["settings"]["layer_coords"]["scope"] = "preference"
        (t / "r.json").write_text(json.dumps(bad), encoding="utf-8")
        check("registry: a preference that differs between presets is refused",
              refused(lambda: rs.load_registry(t / "r.json"), "REGISTRY_INVALID"))
        bad["settings"]["layer_coords"]["scope"] = "preset"
        bad["settings"]["cursor"]["value_labels"] = {"auto": "x"}
        (t / "r.json").write_text(json.dumps(bad), encoding="utf-8")
        check("registry: value labels must name every value", refused(lambda: rs.load_registry(t / "r.json"), "REGISTRY_INVALID"))


# --- play.ps1 ------------------------------------------------------------------------------------------------------

def play_checks(skip_runtime=False):
    play = (TOOLS / "play.ps1").read_text(encoding="utf-8")
    check("play.ps1: -Display windowed|fullscreen, default windowed (the vanilla column)",
          "[ValidateSet('windowed', 'fullscreen')][string]$Display = 'windowed'," in play)
    check("play.ps1: -Fullscreen is an explicit -Display fullscreen; the runtime flag follows -Display",
          "$PSBoundParameters['Display'] = 'fullscreen'" in play and "--fullscreen=$(($Display -eq 'fullscreen')" in play
          and "$Fullscreen.IsPresent" not in play)
    check("play.ps1: an installed copy is told to repair, a repository to rebuild",
          "run the installer again and choose this folder to repair it" in play and "build with: cmd /c tools\\build_milestone8.bat" in play)
    if skip_runtime:
        skipped.append("runtime dry runs (explicit --skip-runtime-dry-run; game may be running)")
        return
    if not ((BUILD / "r3hd.exe").is_file() and (GAME / "Default.xex").is_file()):
        skipped.append("play.ps1 dry runs (no built executable or extracted data)")
        return
    with tempfile.TemporaryDirectory(prefix="r3hd_m30_") as tmp:
        f = Path(tmp) / "settings.json"
        f.write_text(json.dumps({"schema": 2, "preset": "hdplus", "preferences": {"display": "fullscreen", "render_scale": "2"}}),
                     encoding="utf-8")

        def dry(*args):
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TOOLS / "play.ps1"),
                                "-DryRun", *args], capture_output=True, text=True, env=clean_env(), cwd=ROOT)
            return r.returncode, r.stdout + r.stderr

        code, out = dry("-SettingsFile", str(f))
        check("dry run: a saved display preference reaches the runtime", code == 0 and "--fullscreen=true" in out
              and "display    : fullscreen" in out and "--resolution_scale=2" in out and "layer coord: separate" in out, out[-300:])
        code, out = dry("-SettingsFile", str(f), "-Display", "windowed")
        check("dry run: -Display windowed wins over the saved preference", code == 0 and "--fullscreen=false" in out, out[-300:])
        f.write_text(json.dumps({"schema": 2, "preset": "vanilla", "preferences": {}}), encoding="utf-8")
        code, out = dry("-SettingsFile", str(f), "-Fullscreen")
        check("dry run: -Fullscreen wins over a saved window", code == 0 and "--fullscreen=true" in out
              and "display    : fullscreen" in out, out[-300:])
        code, out = dry("-Fullscreen", "-Display", "windowed")
        check("dry run: -Fullscreen with -Display windowed is refused", code != 0 and "contradict" in out, out[-300:])


# --- the launcher -------------------------------------------------------------------------------------------------

def pe_subsystem(data: bytes) -> int:
    off = struct.unpack_from("<I", data, 0x3C)[0]
    return struct.unpack_from("<H", data, off + 24 + 68)[0]


# D-116 (2026-10-26): the launcher names the family of a connected controller in this one phrase; the D-203
# controller_prompts value label "Xbox" (2026-11-11) is a different, registry-owned string.
DEVICE_DESCRIPTIONS = ('L"Xbox-compatible controller"',)


def leaked_names(src: str, names) -> list:
    """Setting keys and value labels that the launcher source names outside comments and the D-116 device text."""
    code = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    code = re.sub(r"//[^\n]*", " ", code)
    for phrase in DEVICE_DESCRIPTIONS:
        code = code.replace(phrase, " ")
    return sorted(n for n in names if re.search(r"\b" + re.escape(n) + r"\b", code))


def static_checks():
    src = (TOOLS / "launcher" / "r3hd_launcher.cpp").read_text(encoding="utf-8")
    reg = rs.load_registry()
    names = {k for k, s in reg["settings"].items() if k != "ui_language"} | {lbl for key, s in reg["settings"].items() if key != "ui_language" for lbl in s.get("value_labels", {}).values()
                                    if len(lbl) > 3}
    # Game Language reuses English, already named by the independent Settings-language control.
    names -= set(reg["settings"]["ui_language"].get("value_labels", {}).values())
    leaked = leaked_names(src, names)
    check("launcher source names no setting, value label or preset default (the registry is the one source)", not leaked, leaked)
    # G6-P36: the scan ignores comments and the D-116 device description only; a label in code is still found.
    check("source-name scan: a value label in a string literal or code is still found; comments and the D-116 "
          "device description are not settings",
          leaked_names('auto s = L"Xbox"; // Xbox pad\nT(L"Xbox-compatible controller");', {"Xbox"}) == ["Xbox"]
          and leaked_names('// Xbox\nT(L"Xbox-compatible controller"); /* Xbox */', {"Xbox"}) == []
          and leaked_names('T(L"Xbox-compatible controller (Xbox)")', {"Xbox"}) == ["Xbox"])
    check("launcher starts only the bundled Python and Windows PowerShell; never r3hd.exe",
          src.count("CreateProcessW(") == 3 and "CreateProcessW(exe.c_str()" in src and "CreateProcessW(ps.c_str()" in src
          and not re.search(r"(CreateProcessW|ShellExecuteW)\([^;]*r3hd\.exe", src))
    # G6-P31 (D-287): the third start is the level editor: the bundled pythonw.exe beside the bundled python.exe, the
    # editor script of the installation's tools, after the dry-run return.
    ed = src.split("bool StartLevelEditor(", 1)[1].split("\n}\n", 1)[0] if "bool StartLevelEditor(" in src else ""
    check("G6-P31: the level editor is the bundled pythonw.exe running the installation's editor; a dry run starts nothing",
          'Parent(p.python) + L"\\\\pythonw.exe"' in ed
          # G6-P39 (D-295): the same function starts the 3D editor (threeD); the classic editor is the default
          and 'p.tools + (threeD ? L"\\\\r3hd_scene_view.py" : L"\\\\r3hd_level_editor.py")' in ed
          and 'Parent(p.python) + L"\\\\_r3hd_scene_gl.pyd"' in ed and "bool threeD = false" in ed
          and "CreateProcessW(pyw.c_str()" in ed and ed.index("if (dryRun) return true;") < ed.index("CreateProcessW(")
          and src.count("StartLevelEditor(") == 4)
    check("Play is play.ps1 -UserHome HOME, hidden; the dry run is play.ps1's own -DryRun",
          'p.tools + L"\\\\play.ps1", L"-UserHome", p.home' in src and 'args.push_back(L"-DryRun")' in src
          and src.count("CREATE_NO_WINDOW") == 2)
    check("settings are saved only through the engine's set-preset (the launcher never names settings.json)",
          'EngineArgs(p, L"set-preset")' in src and not re.search(r'L"[^"]*settings\.json', src))
    check("UI test: a private desktop is made current before any window, and no modal box is shown there",
          src.index("CreateDesktopW(") < src.index("SetThreadDesktop(desk)") < src.index("if (!CreateUi(inst)) return 1;\n  ShowWindow(g.hwnd, SW_SHOWNOACTIVATE)")
          and src.count("MessageBoxW(g.hwnd") == 1 and "if (g.testMode) { Note(L\"dialog: \"" in src)
    check("UI test: Play is a dry run and Open folder does nothing", "bool dryRun = g.testMode;" in src
          and 'if (g.testMode) Note(L"folder: not opened in test mode");' in src)
    check("foreground permission is granted only for a real launch", "if (!dryRun) AllowSetForegroundWindow(ASFW_ANY);" in src)
    iss = (TOOLS / "installer" / "r3hd_setup.iss").read_text(encoding="utf-8")
    mutex = re.search(r'kAppMutex\[\] = L"([^"]+)"', src).group(1)
    check("setup and launcher agree on the AppMutex", f"AppMutex={mutex}" in iss)
    check("setup: no technical options page (no option list, no combo boxes, no render scale)",
          "describe-options" not in iss and "TNewComboBox" not in iss
          and not re.search(r"render_scale|RenderScale|resolution_scale|texture_orient|layer_coords|cursor", iss))
    check("setup: Play and Settings shortcuts start the launcher; Play directly with --play",
          re.search(r'Name: "\{code:MenuDir\}\\Rayman 3 HD Recompiled"; Filename: "\{app\}\\app\\r3hd_launcher\.exe"; Parameters: "--play"', iss)
          and re.search(r'Name: "\{code:MenuDir\}\\Rayman 3 HD Recompiled - Settings"; Filename: "\{app\}\\app\\r3hd_launcher\.exe";', iss))
    # M49 (D-088, the person's review): two independent boxes, Play checked and Settings unchecked, after Finish only;
    # test-mode twins run the launcher without a window (--play --dry-run --no-ui / --no-ui) into the setup log.
    run = iss.split("\n[Run]\n", 1)[1].split("\n[", 1)[0]
    entries = [ln for ln in run.splitlines() if ln.startswith("Filename:")]
    check("setup: the Finish page offers Play (checked) and Settings (unchecked), independent, never in silent runs",
          len(entries) == 4 and all("postinstall" in e and "skipifsilent" in e for e in entries)
          and "unchecked" not in entries[0] and "unchecked" in entries[1] and "unchecked" not in entries[2]
          and "unchecked" in entries[3] and '"--play --dry-run --no-ui"' in entries[2] and '"--no-ui"' in entries[3]
          and "RunListClickCheck" not in iss and "RunList.Checked" not in iss)
    # M48-P: the captions are custom messages (tools/installer/r3hd_en.isl; r3hd_tr.isl for the playtest build)
    en_isl = (ROOT / "tools" / "installer" / "r3hd_en.isl").read_text(encoding="utf-8-sig")
    check("setup: profile page keeps Vanilla / HD+ / Custom / keep current", all(
        f"PresetPage.Add(CustomMessage('{k}'))" in iss for k in ("PresetVanilla", "PresetHdplus", "PresetCustom", "PresetKeep"))
        and all(x in en_isl for x in ("PresetVanilla=Vanilla", "PresetHdplus=HD+", "PresetCustom=Custom",
                                      "PresetKeep=Keep my current settings")))
    defn = json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))
    pallow = json.loads((ROOT / "config" / "release" / "payload_allowlist.json").read_text(encoding="utf-8"))
    check("payload: the launcher is staged to app/r3hd_launcher.exe with the launcher_native role",
          defn["launcher"]["dest"] == engine.LAUNCHER == "app/r3hd_launcher.exe"
          and pallow["binaries"].get("app/r3hd_launcher.exe") == "launcher_native" and defn["version"].startswith(("0.30.0", "0.31.0", "0.32.0", "0.33.0", "0.34.0", "0.35.0", "0.36.0", "0.49.0", "0.50.0", "1.0.0", "1.0.1", "1.0.2", "1.0.3", "1.1.0", "1.2.0", "1.3.0", "1.3.1", "1.4.0")))
    bat = (TOOLS / "build_milestone8.bat").read_text(encoding="utf-8")
    check("build: launcher built before the regressions, this regression in the build",
          "call tools\\launcher\\build_launcher.bat || exit /b 1" in bat and "python tools\\m30_launcher_regression.py || exit /b 1" in bat
          and bat.index("build_launcher.bat") < bat.index("m30_launcher_regression.py"))


def binary_checks(rebuild: bool):
    if not LAUNCHER.is_file():
        check("launcher built (tools\\launcher\\build_launcher.bat)", False)
        return False
    data = LAUNCHER.read_bytes()
    check("launcher: Windows GUI program (no console window)", data[:2] == b"MZ" and pe_subsystem(data) == 2)
    check("launcher: no build-machine path and no PDB reference", audit.binary_dev_paths(data) == 0 and b".pdb" not in data.lower())
    if rebuild:
        with tempfile.TemporaryDirectory(prefix="r3hd_m30_build_") as tmp:
            digests = []
            for n in ("a", "b"):
                r = subprocess.run(["cmd", "/c", str(TOOLS / "launcher" / "build_launcher.bat"), str(Path(tmp) / n)],
                                   capture_output=True, text=True, cwd=ROOT)
                p = Path(tmp) / n / "r3hd_launcher.exe"
                digests.append(hashlib.sha256(p.read_bytes()).hexdigest() if r.returncode == 0 and p.is_file() else r.stdout[-200:])
            check("launcher: two builds are byte-identical (/Brepro, no PDB)", digests[0] == digests[1] and len(digests[0]) == 64,
                  str(digests))
    return True


def make_home(t: Path, name: str):
    """A synthetic installation made by the engine itself (fixture payload and game tree; nothing from the game)."""
    pl, tree, rels = engine.make_fixture(t)
    home = t / name
    engine.install(home, pl, tree, "vanilla", releases=rels, log=lambda *_: None)
    return home


PATH_VARS = ("R3HD_GAME_DIR", "R3HD_BIN_DIR", "R3HD_PLAY_ROOT", "R3HD_HOME")


def launcher_env(**extra):
    """The synthetic home must decide the paths: play.ps1 prefers these variables (the build sets R3HD_GAME_DIR)."""
    env = {k: v for k, v in os.environ.items() if k not in PATH_VARS}
    env.update(extra)
    return env


def run_launcher(home: Path, t: Path, *args, env=None):
    cmd = [str(LAUNCHER), *args, "--home", str(home), "--python", sys.executable, "--tools", str(TOOLS),
           "--releases", str(t / "releases.json")]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env or launcher_env(), timeout=300)
    return r.returncode, r.stdout + r.stderr


def ui(home: Path, t: Path, name: str, script: str, env=None):
    out = t / f"ui_{name}"
    out.mkdir()
    (out / "script.txt").write_text(script, encoding="utf-8")
    code, text = run_launcher(home, t, "--ui-test", str(out / "script.txt"), "--out", str(out), env=env)
    dumps = {}
    for f in out.glob("*.txt"):
        if f.name != "script.txt":
            dumps[f.stem] = dict(line.split("=", 1) for line in f.read_text(encoding="utf-8").splitlines() if "=" in line)
    log = (out / "ui_test.log").read_text(encoding="utf-8") if (out / "ui_test.log").is_file() else ""
    return code, dumps, log, out


def settings(home: Path) -> dict:
    return json.loads((home / "settings.json").read_text(encoding="utf-8"))


def layout_ok(d: dict) -> bool:
    return d.get("controls", "").endswith("overlaps=0 outside=0") or ("overlaps=0" in d.get("controls", "")
                                                                      and "outside=0" in d.get("controls", ""))


def launcher_checks(keep, skip_runtime=False):
    saved = {k: os.environ.get(k) for k in engine.HOOKS}
    with tempfile.TemporaryDirectory(prefix="r3hd_m30_ui_") as tmp:
        t = Path(tmp)
        sys32 = t / "sys32"
        sys32.mkdir()
        for n in engine.VC_RUNTIME:
            (sys32 / n).write_bytes(b"x")
        os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0", R3HD_INSTALL_FAKE_LAUNCHER="0")
        try:
            home = make_home(t, "home")
            code, out = run_launcher(home, t, "--no-ui")
            check("launcher reads the installation through the engine", code == 0 and "R3HD_LAUNCHER MODEL_OK vanilla" in out, out)
            code, out = run_launcher(home, t, "--play", "--dry-run", "--no-ui")
            check("Play (dry run) on a synthetic installation reports play.ps1's own preflight message",
                  code == 2 and "R3HD_LAUNCHER PLAY FAILED" in out and "Default.xex does not match" in out
                  and "repair it" in out, out[-300:])
            check("Play wrote its log into the installer-owned cache only", (home / "cache" / "launcher_play.log").is_file()
                  and not list(home.glob("launcher*")))
            code, out = subprocess.run([str(LAUNCHER), "--no-ui", "--home", str(home), "--python", str(t / "missing.exe"),
                                        "--tools", str(TOOLS)], capture_output=True, text=True).returncode, ""
            check("a missing Python runtime is reported, not a crash", code == 2)
            # G6-P31 (D-287): the level editor entry (dry run: the files are checked, the command line printed)
            code, out = run_launcher(home, t, "--level-editor", "--dry-run", "--no-ui")
            check("G6-P31: --level-editor --dry-run names pythonw.exe, the editor script and this home; nothing starts",
                  code == 0 and "R3HD_LAUNCHER LEVEL_EDITOR DRY_RUN" in out and "pythonw.exe" in out
                  and "r3hd_level_editor.py" in out and str(home) in out, out[-300:])
            r = subprocess.run([str(LAUNCHER), "--level-editor", "--dry-run", "--no-ui", "--home", str(home),
                                "--python", str(t / "nopython" / "python.exe"), "--tools", str(TOOLS)],
                               capture_output=True, text=True, timeout=120)
            check("G6-P31: a missing editor runtime is reported (exit 2), no window",
                  r.returncode == 2 and "R3HD_LAUNCHER LEVEL_EDITOR FAILED missing" in r.stdout + r.stderr,
                  (r.stdout + r.stderr)[-300:])
            code, _d, log, _o = ui(home, t, "editor", "page mods\nclick leveleditor\nclick close\n")
            check("G6-P31: the Mods page's Level editor button (UI test: dry run, no window)",
                  code == 0 and "level editor: dry run" in log and "pythonw.exe" in log, log[-400:])
            # G6-P39 (D-295): the 3D Level Remix Editor entry. A dry run only checks that files exist, so a folder of
            # empty stand-ins names the bundled runtime layout (pythonw.exe and the OpenGL bridge beside python.exe).
            py3d = t / "py3d"
            py3d.mkdir()
            for n in ("python.exe", "pythonw.exe", "_r3hd_scene_gl.pyd"):
                (py3d / n).write_bytes(b"")
            r = subprocess.run([str(LAUNCHER), "--level-editor-3d", "--dry-run", "--no-ui", "--home", str(home),
                                "--python", str(py3d / "python.exe"), "--tools", str(TOOLS)],
                               capture_output=True, text=True, timeout=120)
            check("G6-P39: --level-editor-3d --dry-run names pythonw.exe, r3hd_scene_view.py and this home; nothing "
                  "starts", r.returncode == 0 and "R3HD_LAUNCHER LEVEL_EDITOR_3D DRY_RUN" in r.stdout
                  and str(py3d / "pythonw.exe") in r.stdout and "r3hd_scene_view.py" in r.stdout
                  and str(home) in r.stdout, (r.stdout + r.stderr)[-300:])
            (py3d / "_r3hd_scene_gl.pyd").unlink()
            r = subprocess.run([str(LAUNCHER), "--level-editor-3d", "--dry-run", "--no-ui", "--home", str(home),
                                "--python", str(py3d / "python.exe"), "--tools", str(TOOLS)],
                               capture_output=True, text=True, timeout=120)
            check("G6-P39: without the OpenGL bridge the 3D editor is reported missing (exit 2), no window",
                  r.returncode == 2 and "R3HD_LAUNCHER LEVEL_EDITOR_3D FAILED missing" in r.stdout
                  and "_r3hd_scene_gl.pyd" in r.stdout, (r.stdout + r.stderr)[-300:])
            code, _d, log, _o = ui(home, t, "editor3d", "page mods\nclick leveleditor3d\nclick close\n")
            check("G6-P39: the Mods page's 3D Level Remix Editor button reaches the 3D entry (UI test: dry run; this "
                  "development Python has no bridge beside it, so the bridge is named as missing)",
                  code == 0 and "3d level editor: failed missing" in log and "_r3hd_scene_gl.pyd" in log, log[-400:])

            mods_layout = ["page mods"]
            for language in ("en", "tr"):
                mods_layout += [f"language {language}", "page mods"]
                for dpi in (96, 120, 144):
                    mods_layout += [f"dpi {dpi}", f"dump {language}{dpi}"]
            mods_layout += ["language en", "click close", ""]
            code, mod_dumps, log, mod_out = ui(home, t, "mods_captions", "\n".join(mods_layout))
            if keep:
                shutil.copytree(mod_out, Path(keep) / mod_out.name, dirs_exist_ok=True)
            check("G6-P42: Mods controls fit their captions at 96, 120 and 144 DPI in English and Turkish",
                  code == 0 and len(mod_dumps) == 6 and all(
                      dump.get("page") == "mods" and layout_ok(dump) and dump.get("text_clipped") == "0"
                      for dump in mod_dumps.values()),
                  [(name, dump.get("controls"), dump.get("text_clipped")) for name, dump in mod_dumps.items()])

            script = "\n".join([
                "dump initial", "shot vanilla_96", "set render_scale 2", "set display fullscreen", "click save", "dump s1",
                "profile hdplus", "set gameplay_subtitles all", "click save", "dump s2", "reload", "dump s2r", "profile custom", "dump c1",
                "page corrections", "dump k1", "dpi 144", "dump k144", "dpi 96", "page settings", "set texture_orient original",
                "click save", "dump s3", "shot custom_96", "profile vanilla", "dump v1", "profile custom", "dump c2",
                "profile vanilla", "click save", "reload", "profile custom", "dump c3", "set layer_coords separate",
                "dpi 144", "dump d144", "shot custom_144", "dpi 120", "dump d120", "click play", "dump played",
                "set diagnostics detailed", "click close", ""])  # M31: save clock hidden
            code, d, log, out = ui(home, t, "main", script)
            check("UI run completed", code == 0 and all(k in d for k in ("initial", "s1", "s2", "c1", "s3", "v1", "c2", "c3",
                                                                         "d144", "played")), log[-400:])
            if code == 0 and "played" in d:
                i = d["initial"]
                check("UI: opens on the saved profile; corrections fixed outside Custom; Save off until a change; Play on",
                      i["profile"] == "vanilla" and i["setting.layer_coords"] == "original enabled=0"
                      and i["setting.render_scale"] == "auto enabled=1" and i["save_enabled"] == "0" and i["play_enabled"] == "1")
                check("UI: display and rendering choices are saved as preferences of the Vanilla profile",
                      d["s1"]["dirty"] == "0" and d["s1"]["status"].startswith("Saved"))
                check("UI: HD+ shows its corrections (fixed) and keeps the preferences",
                      d["s2"]["setting.layer_coords"] == "separate enabled=0" and d["s2"]["setting.render_scale"] == "2 enabled=1")
                check("UI (D-090): gameplay subtitles are a check box under any profile; saved on HD+ it stays HD+",
                      d["s2"]["setting.gameplay_subtitles"] == "all enabled=1" and d["s2r"]["profile"] == "hdplus"
                      and d["s2r"]["setting.gameplay_subtitles"] == "all enabled=1")
                check("UI: Custom starts from the profile shown before (HD+), nothing changed yet",
                      d["c1"]["custom_base"] == "hdplus" and d["c1"]["setting.layer_coords"] == "separate enabled=1"
                      and d["c1"]["setting.texture_orient"] == "corrected enabled=1")
                order = d["c1"].get("settings_tab_order", "").split(",")
                check("UI (D-151, D-161, D-203, D-303): Custom on HD+ shows the red correction on; Tab on Settings walks the "
                      "profile, the button prompts (below it, left column), the score HUD key (under them), Display, then "
                      "gameplay subtitles (moved under Display), then Mouse; no correction is on it",
                      d["c1"].get("setting.red_correction") == "bypass enabled=1"
                      and order[:4] == ["profile", "controller_prompts", "hud_toggle", "display"]
                      and d["c1"].get("setting.hud_toggle") == "off enabled=1" and "render_scale" in order and "gameplay_subtitles" in order
                      and "mouse_camera" in order and not {"combo_close", "red_correction", "sky_clear", "lit_uv_scroll", "power_swirl", "beam_color",
                                    "lockon_far_color", "crown_cutout"} & set(order)
                      and order.index("display") < order.index("render_scale") < order.index("gameplay_subtitles")
                      < order.index("mouse_camera"), d["c1"].get("settings_tab_order"))
                k1 = d.get("k1", {})
                korder = k1.get("corrections_tab_order", "").split(",")
                check("UI (D-161, D-218, D-219, D-221, D-363): the Corrections page: Tab walks the ten corrections in order; focus on the first; "
                      "it names the Custom profile and its base; the charge trail is on (HD+ base); layout holds at 96 and 144 DPI",
                      k1.get("page") == "corrections"
                      and korder == ["combo_close", "layer_coords", "red_correction", "texture_orient", "sky_clear", "lit_uv_scroll",
                                     "power_swirl", "beam_color", "lockon_far_color", "crown_cutout"]
                      and k1.get("setting.lit_uv_scroll") == "applied enabled=1" and k1.get("focus") == "combo_close"
                      and k1.get("corrections_profile", "").startswith("Active profile: Custom, starting from HD+.")
                      and all(layout_ok(d.get(k, {})) and d.get(k, {}).get("text_clipped") == "0" for k in ("k1", "k144")),
                      {f"{k}.{f}": d.get(k, {}).get(f) for k in ("k1", "k144") for f in ("corrections_tab_order", "focus", "controls", "text_clipped")})
                check("UI: Vanilla shows its own corrections again; Custom choices come back within the session",
                      d["v1"]["setting.texture_orient"] == "original enabled=0"
                      and d["c2"]["setting.texture_orient"] == "original enabled=1" and d["c2"]["custom_base"] == "hdplus")
                check("UI: after Vanilla was saved, Custom starts again from Vanilla (old Custom choices dropped)",
                      d["c3"]["custom_base"] == "vanilla" and d["c3"]["setting.texture_orient"] == "original enabled=1"
                      and d["c3"]["setting.display"] == "fullscreen enabled=1")
                check("UI: no control overlaps another or leaves the window at 96, 120 and 144 DPI",
                      all(layout_ok(d[k]) for k in ("initial", "d120", "d144")), str([d[k].get("controls") for k in ("initial", "d120", "d144")]))
                check("UI: the window is compact (at most 680 px tall at 96 DPI, 1020 at 144 DPI; includes Combo animation)",
                      int(i["client"].split("x")[1].split()[0]) <= 680 and int(d["d144"]["client"].split("x")[1].split()[0]) <= 1020,
                      i["client"] + " / " + d["d144"]["client"])
                check("UI: Play in test mode is a dry run that saves first and reports play.ps1's message",
                      "could not be started" in d["played"]["status"] and "Default.xex does not match" in d["played"]["status"]
                      and "status: Saved" in log.split("> click play", 1)[1])
                check("UI: closing with unsaved changes asks (answered No in test mode) and saves nothing",
                      "dialog: Save your changes before closing?" in log)
                s = settings(home)
                check("UI: the final file is the resolver's (Custom base Vanilla with layer_coords from the Play save; "
                      "preferences kept)", s == {"schema": 3, "preset": "custom", "base": "vanilla",
                                                 "overrides": {"layer_coords": "separate"},
                                                 "preferences": {"display": "fullscreen", "gameplay_subtitles": "all",
                                                                 "render_scale": "2", "ui_language": "en", "dualsense_light": "on", "dualsense_trigger": "on"}},
                      json.dumps(s))  # D-108: a new home stores both DualSense options on
            if keep:
                shutil.copytree(out, Path(keep) / "ui_main", dirs_exist_ok=True)

            # States the window must explain.
            (home / "settings.json").write_text("{broken", encoding="utf-8")
            code, d, log, _ = ui(home, t, "invalid", "dump open\nclick save\ndump saved\nclick close\n")
            check("UI: unreadable settings are explained, Save replaces them and keeps a copy",
                  code == 0 and "could not be read" in d["open"]["banner"] and d["open"]["save_enabled"] == "1"
                  and settings(home)["preset"] == "vanilla" and list(home.glob("settings.json.invalid-*")), log[-300:])
            (home / "data" / "content" / "Default.xex").unlink()
            code, d, log, _ = ui(home, t, "nodata", "dump open\n")
            check("UI: missing game data disables Play and says to repair with the installer",
                  code == 0 and d["open"]["play_enabled"] == "0" and "Game data needs repair" in d["open"]["banner"]
                  and "Run setup" in d["open"]["banner"], d.get("open", {}).get("banner", log))
            home2 = make_home(t, "home2")
            (home2 / "bin" / "rexgpu-xenos.dll").unlink()
            code, d, log, _ = ui(home2, t, "nofile", "dump open\n")
            check("UI: a missing program file disables Play and names it",
                  code == 0 and d["open"]["play_enabled"] == "0" and "bin/rexgpu-xenos.dll" in d["open"]["banner"])
            home3 = make_home(t, "home3")
            code, d, log, _ = ui(home3, t, "running", "dump open\nset diagnostics detailed\nclick save\n",  # M31: cursor hidden
                                 env=launcher_env(R3HD_INSTALL_FAKE_RUNNING="1"))
            check("UI: while the game runs, Play is off and saving still works (applies next start)",
                  code == 0 and d["open"]["play_enabled"] == "0" and "is running" in d["open"]["banner"]
                  and settings(home3)["preferences"] == {"diagnostics": "detailed", "display": "fullscreen", "ui_language": "en",
                                                     "dualsense_light": "on", "dualsense_trigger": "on"},  # M31: a new home starts fullscreen; D-108
                  log[-600:] + json.dumps(settings(home3)))
            home4 = make_home(t, "home4")  # D-138: the Mouse group of the Settings page
            code, d, log, _ = ui(home4, t, "mouse", chr(10).join([
                "dump open", "set mouse_sensitivity 75", "dump blocked", "set mouse_camera on", "set mouse_sensitivity 75",
                "set mouse_buttons on", "dump on", "dpi 144", "dump d144", "dpi 120", "dump d120", "dpi 96", "click save", "dump saved",
                "reload", "dump reloaded", "set mouse_camera off", "dump off", "click close", ""]))
            ok = code == 0 and all(k in d for k in ("open", "blocked", "on", "saved", "reloaded", "off"))
            check("UI (D-138): Mouse group: camera and buttons off, sensitivity 50% and disabled until the camera is on",
                  ok and d["open"]["setting.mouse_camera"] == "off enabled=1" and d["open"]["setting.mouse_buttons"] == "off enabled=1"
                  and d["open"]["setting.mouse_sensitivity"].startswith("50 ") and d["open"]["setting.mouse_sensitivity"].endswith("enabled=0")
                  and d["blocked"]["setting.mouse_sensitivity"].startswith("50 "), log[-300:] + json.dumps(d.get("open", {})))
            check("UI (D-138): the camera enables the sensitivity; choices are saved as preferences and come back; the "
                  "sensitivity is disabled (kept) again with the camera off",
                  ok and d["on"]["setting.mouse_sensitivity"].startswith("75 ") and d["on"]["setting.mouse_sensitivity"].endswith("enabled=1")
                  and settings(home4)["preferences"].get("mouse_camera") == "on" and settings(home4)["preferences"].get("mouse_sensitivity") == "75"
                  and settings(home4)["preferences"].get("mouse_buttons") == "on" and d["saved"]["dirty"] == "0"
                  and d["reloaded"]["setting.mouse_camera"] == "on enabled=1" and d["reloaded"]["setting.mouse_sensitivity"].startswith("75 ")
                  and d["reloaded"]["setting.mouse_buttons"] == "on enabled=1"
                  and d["off"]["setting.mouse_sensitivity"].startswith("75 ") and d["off"]["setting.mouse_sensitivity"].endswith("enabled=0"),
                  json.dumps({k: d.get(k, {}).get("setting.mouse_sensitivity") for k in ("on", "reloaded", "off")}))
            check("UI (D-138): the Settings page with the Mouse group lays out without overlap at 96, 120 and 144 DPI",
                  ok and all(layout_ok(d[k]) for k in ("open", "d120", "d144")), str([d.get(k, {}).get("controls") for k in ("open", "d120", "d144")]))
            (home3 / "sessions" / "20261014-101010").mkdir(parents=True)
            (home3 / "sessions" / "20261014-101010" / "session.json").write_text(
                json.dumps({"exit_code": 1, "exit_hex": "00000001", "clean_exit": False, "crash_report": False}),
                encoding="utf-8-sig")
            code, d, log, _ = ui(home3, t, "lastrun", "dump open\n")
            check("UI: a failed last session is reported with its diagnostics folder",
                  code == 0 and "20261014-101010" in d["open"]["banner"] and "ended unexpectedly" in d["open"]["banner"])
            empty = t / "empty"
            empty.mkdir()
            code, d, log, _ = ui(empty, t, "notinstalled", "dump open\n")
            check("UI: a folder without an installation disables Play and Save",
                  code == 0 and d["open"]["play_enabled"] == "0" and d["open"]["save_enabled"] == "0"
                  and "needs repair" in d["open"]["banner"])
            code, d, log, _ = ui(home3, t, "badscript", "frobnicate\n")
            check("UI test: an unknown command fails the run", code == 2)

            # G6-P74 (D-323): the banner after a launcher-only failed start, in English and Turkish.
            home6 = make_home(t, "home_g6p74")
            approved = ("The game couldn't be started. Check the latest support report for details.",
                        "Oyun başlatılamadı. Ayrıntılar için son destek raporunu kontrol edin.")
            fallback = ("The game couldn't be started.", "Oyun başlatılamadı.")
            lang_script = "dump en\nlanguage tr\ndump tr\nlanguage en\n"

            def newest(stamp, body, report=True):
                s = home6 / "sessions" / stamp
                s.mkdir(parents=True)
                (s / "session.json").write_text(json.dumps(body), encoding="utf-8-sig")
                if report:
                    (s / "support_report.txt").write_text("synthetic\n", encoding="utf-8")
            lo = {"record": "launcher_only", "outcome": "start_failed", "game_started": False, "game_pid": None}
            newest("20261120-100000", lo)
            code, d, log, _ = ui(home6, t, "g6p74_start_failed", lang_script)
            check("UI (G6-P74): a launcher-only failed start shows the approved text in English and Turkish",
                  code == 0 and approved[0] in d["en"]["banner"] and approved[1] in d["tr"]["banner"]
                  and "ended unexpectedly" not in d["en"]["banner"] and "beklenmedik" not in d["tr"]["banner"],
                  log[-300:] + json.dumps({k: d.get(k, {}).get("banner") for k in ("en", "tr")}, ensure_ascii=False))
            (home6 / "sessions" / "20261120-100000" / "support_report.txt").unlink()
            code, d, log, _ = ui(home6, t, "g6p74_no_report", lang_script)
            check("UI (G6-P74): without its support report the banner says only that the game couldn't be started",
                  code == 0 and fallback[0] in d["en"]["banner"] and fallback[1] in d["tr"]["banner"]
                  and "report" not in d["en"]["banner"] and "rapor" not in d["tr"]["banner"],
                  json.dumps({k: d.get(k, {}).get("banner") for k in ("en", "tr")}, ensure_ascii=False))
            newest("20261120-100001", {"exit_code": -1073741819, "exit_hex": "C0000005", "clean_exit": False, "crash_report": True})
            code, d, log, _ = ui(home6, t, "g6p74_crash", lang_script)
            check("UI (G6-P74): a later genuine crash keeps D-306's text in both languages",
                  code == 0 and "ended unexpectedly" in d["en"]["banner"] and "20261120-100001" in d["en"]["banner"]
                  and "beklenmedik" in d["tr"]["banner"] and fallback[0] not in d["en"]["banner"]
                  and fallback[1] not in d["tr"]["banner"],
                  json.dumps({k: d.get(k, {}).get("banner") for k in ("en", "tr")}, ensure_ascii=False))
            newest("20261120-100002", {"outcome": "start_failed"})
            code, d, log, _ = ui(home6, t, "g6p74_partial", "dump en\n")
            check("UI (G6-P74): a partial launcher-only record gets the general text, not the start wording",
                  code == 0 and "ended unexpectedly" in d["en"]["banner"] and fallback[0] not in d["en"]["banner"],
                  d.get("en", {}).get("banner", ""))
            newest("20261120-100003", {"exit_code": 0, "exit_hex": "00000000", "clean_exit": True, "crash_report": False})
            code, d, log, _ = ui(home6, t, "g6p74_normal", "dump en\n")
            check("UI (G6-P74): a later normal exit shows no failure line",
                  code == 0 and "ended unexpectedly" not in d["en"]["banner"] and fallback[0] not in d["en"]["banner"]
                  and d["en"]["banner"].startswith("Ready to play"), d.get("en", {}).get("banner", ""))

            # A real running launcher (its private desktop, held open by "wait") blocks uninstall: no test hook.
            home4 = make_home(t, "home4")
            (t / "ui_wait").mkdir()
            (t / "ui_wait" / "script.txt").write_text("wait 12000\n", encoding="utf-8")
            p = subprocess.Popen([str(LAUNCHER), "--ui-test", str(t / "ui_wait" / "script.txt"), "--out", str(t / "ui_wait"),
                                  "--home", str(home4), "--python", sys.executable, "--tools", str(TOOLS),
                                  "--releases", str(t / "releases.json")], env=launcher_env())
            try:
                import time
                time.sleep(3)
                env = {k: v for k, v in os.environ.items() if k != "R3HD_INSTALL_FAKE_LAUNCHER"}
                r = subprocess.run([sys.executable, str(TOOLS / "r3hd_installer.py"), "uninstall", "--check", "--home", str(home4),
                                    "--releases", str(t / "releases.json")], capture_output=True, text=True, env=env)
                check("a running Settings launcher makes uninstall refuse (LAUNCHER_RUNNING), nothing removed",
                      r.returncode == 2 and "LAUNCHER_RUNNING" in r.stderr and (home4 / "installer.json").is_file(), r.stderr[-200:])
            finally:
                p.wait(timeout=120)
            (home4 / "settings.json").write_text('{"schema": 2, "preset": "hdplus", "preferences": {"layer_coords": "separate"}}',
                                                  encoding="utf-8")
            code, out = run_launcher(home4, t, "--play", "--dry-run", "--no-ui")
            check("Play with settings the resolver refuses shows the whole refusal and points to Settings",
                  code == 2 and "Settings refused: NOT_A_PREFERENCE" in out and "Open Rayman 3 HD Settings" in out, out[-300:])

            # End to end through play.ps1 with the developer build and data (play.ps1's own path overrides).
            if not skip_runtime and (BUILD / "r3hd.exe").is_file() and (GAME / "Default.xex").is_file():
                engine.set_preset(home3, "hdplus", pairs=["display=fullscreen", "render_scale=3"])
                code, out = run_launcher(home3, t, "--play", "--dry-run", "--no-ui",
                                         env=dict(clean_env(), R3HD_BIN_DIR=str(BUILD), R3HD_GAME_DIR=str(GAME)))
                check("Play (dry run) end to end: the saved profile and preferences reach the runtime arguments",
                      code == 0 and "R3HD_LAUNCHER PLAY ENDED" in out and "DRY RUN" in out and "preset     : hdplus" in out
                      and "--fullscreen=true" in out and "--resolution_scale=3" in out, out[-400:])
            else:
                skipped.append("launcher end-to-end dry run (explicit skip or missing build/data)")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keep")
    ap.add_argument("--no-rebuild", action="store_true", help="skip the reproducible-build check")
    ap.add_argument("--skip-runtime-dry-run", action="store_true", help="skip dry runs against the real build/data while a person plays")
    a = ap.parse_args()
    resolver_checks()
    play_checks(a.skip_runtime_dry_run)
    static_checks()
    if binary_checks(not a.no_rebuild):
        launcher_checks(a.keep, a.skip_runtime_dry_run)
    failed = sum(not ok for _, ok in checks)
    for s in skipped:
        print(f"skip {s}")
    print(f"M30_LAUNCHER_REGRESSION {'PASS' if not failed else 'FAIL'} checks={len(checks)} failures={failed} skipped={len(skipped)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
