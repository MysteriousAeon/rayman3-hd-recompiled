"""D-139 regression (in the build, after the runtime is installed): the in-game PC Settings panel.

1. tools/r3hd_pcset_patch.py is in the SDK tree as it writes it (input gate in the keyboard / mouse, SDL and XInput
   drivers, the app's SetHostUiInputBlocked hook in the SDK's is_active() callback, Window::SetHostUiCursor through
   the M21 rule); the panel source stays host-only (no guest memory, no rendering-resolution or developer setting,
   no window of its own, the engine only as a hidden process and never in a hidden run).
2. The native test (tools/build_hostui_test.bat): the pure gates, the panel model and the REAL keyboard / mouse
   driver with the panel opening and closing (R3HD_HOSTUI_TEST PASS n/n).
3. The engine on synthetic homes: launcher-model REVISION, set-preferences (shown preferences only, revision check
   under the lock, every other section kept as data, schema 1 kept), set-preset --expect-revision, BUSY under a
   held lock, Game Language independent of the Settings language and of the preset.
4. play.ps1 hands the panel its home only for a launch from that home's settings.json and clears the variables.
Starts no game. Prints R3HD_PCSET_REGRESSION PASS n/n.
"""
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
SDK = ROOT / "external/rexglue-sdk"
checks = failures = 0


def check(ok, label):
    global checks, failures
    checks += 1
    if not ok:
        failures += 1
        print(f"FAIL: {label}")


def read(p):
    return Path(p).read_text(encoding="utf-8", errors="replace")


def code_only(text):
    return "\n".join(line.split("//")[0] for line in text.splitlines())


# --- 1. the patch and the panel source ---------------------------------------------------------------------------
check((SDK / "include/rex/r3hd_hostui_gate.h").read_bytes() == (TOOLS / "r3hd_hostui_gate.h").read_bytes(),
      "installed gate header is tools/r3hd_hostui_gate.h")
check((SDK / "include/rex/m21_cursor.h").read_bytes() == (TOOLS / "m21_cursor.h").read_bytes(),
      "installed cursor rule is tools/m21_cursor.h")
app_h = read(SDK / "include/rex/rex_app.h")
app = read(SDK / "src/ui/rex_app.cpp")
check("void SetHostUiInputBlocked(bool blocked)" in app_h and "std::atomic<bool> host_ui_input_blocked_{false};" in app_h,
      "rex_app.h: the ownership hook, off by default")
callback = app.split("input_sys->SetActiveCallback([this]() {")[1].split("});")[0]
check(callback.lstrip().startswith("if (host_ui_input_blocked_.load(std::memory_order_acquire)) return false;"),
      "the SDK's is_active() callback answers false first while the app's panel holds the input")
mnk = read(SDK / "src/input/mnk/mnk_input_driver.cpp")
state = mnk.split("X_RESULT MnkInputDriver::GetDeviceState(")[1].split("X_RESULT MnkInputDriver::SetDeviceVibration(")[0]
keydown = mnk.split("void MnkInputDriver::OnKeyDown(")[1].split("void MnkInputDriver::OnKeyUp(")[0]
keyup = mnk.split("void MnkInputDriver::OnKeyUp(")[1].split("void MnkInputDriver::OnMouseDown(")[0]
check("IsBindPressed(key_down_" not in state and state.count("IsBindPressed(gate_keys,") >= 25,
      "keyboard: every binding of a poll sees the gated keys")
check(state.count("host_gate_.Sync(host_active, key_down_)") == 2 and "if (!host_active) pending_buttons_ = 0;" in state,
      "keyboard: taps latched while the panel is open are dropped, at the close too")
check(keydown.index("host_gate_.Sync(host_active, key_down_)") < keydown.index("SetKeyState(vk, true);") <
      keydown.index("if (!host_active) return;") and "IsBindPressed(key_down_" not in keydown,
      "keyboard: a key-down syncs the gate before it is recorded and latches nothing while the panel is open")
check("host_gate_.Released(vk);" in keyup, "keyboard: a key-up frees a withheld key")
check("host_gate_.ClearHeld();" in mnk.split("void MnkInputDriver::OnLostFocus(")[1], "keyboard: focus loss clears it")
sdl = read(SDK / "src/input/sdl/sdl_input_driver.cpp")
check(sdl.count("controller->host_gate.Apply(is_active,") == 2, "SDL: the gate on the state and on the keystroke path")
check("AnalogToKeyfield(gated)" in sdl and "a withheld button never repeats" in sdl, "SDL: keystrokes from the gated state")
xin = read(SDK / "src/input/xinput/xinput_input_driver.cpp")
check("host_gates_[user_index].Apply(is_active(), out_state->gamepad)" in xin and
      "host_gates_[user_index].Withholding()" in xin and "std::lock_guard lock(host_gates_mutex_);" in xin, "XInput: the gate on the state; no key-down while held")
window = read(SDK / "src/ui/window_sdl.cpp")
host_ui = window.split("void WindowSDL::ApplyHostUiCursor(bool open) {")[1].split("\n}\n")[0]
check('if (std::getenv("R3HD_NONINTRUSIVE")) return;' in host_ui and
      'if (M21CursorAuto()) M21ApplyCursor(M21Tracker().HostUi(open), "host_ui");' in host_ui and
      not re.search(r"SDL_\w+", host_ui), "pointer: the M21 rule only, never in a hidden window")
gate = code_only(read(TOOLS / "r3hd_hostui_gate.h"))
for needle in ("PPCContext", "virtual_membase", "SDL_", "windows.h", "REX_KERNEL_MEMORY"):
    check(needle not in gate, f"gate header is host- and SDK-free ({needle})")
panel = read(TOOLS / "m2_host/r3hd_pc_settings.h")
panel_code = code_only(panel)
host = read(TOOLS / "m2_host/r3hd_app.h")
for needle in ("virtual_membase", "PPCContext", "TranslateVirtual", "REX_KERNEL_MEMORY", "resolution_scale",
               "anisotropic", "vsync", "SetFullscreen(", "WarpMouse", "SetCursorPos", "ClipCursor",
               "CreateWindow", "SetForegroundWindow", "keybd_event", "SendInput", "r3hd.toml", "SaveConfig"):
    check(needle not in panel_code and needle not in code_only(host), f"panel / app: no {needle}")
check("license_mask" not in panel_code, "panel: no licence setting")
check("CREATE_NO_WINDOW" in panel_code and panel_code.count("CreateProcessW(") == 2,
      "engine: a hidden process; the only other process is the Settings app on the person's click")
check('if (std::getenv("R3HD_NONINTRUSIVE")) return e;' in panel_code, "a hidden run never starts the engine")
check('L"set-preferences", L"--expect-revision"' in panel_code,
      "panel saves through set-preferences with the revision it read")
check(sorted(re.findall(r'SetFlagByName\("(\w+)"', panel_code)) ==
      ["fullscreen", "mnk_mouse", "mnk_mouse_buttons", "mnk_sensitivity"], "panel: the four live runtime settings only")
check("kConfirmSeconds = 15.0" in panel_code and "RevertDisplay(\"timeout\")" in panel_code and
      "RevertDisplay(\"close\")" in panel_code, "display: confirm or revert after 15 s, also when the panel closes")
check('RegisterBind("bind_pc_settings", "F4"' in host and host.index("SetHostUiInputBlocked(true);") <
      host.index("new r3hd_pcset::Panel("), "F4; the input is held before the panel exists")
check('if (!plan || !std::getenv("R3HD_NONINTRUSIVE")) return;' in host, "the test toggle exists in hidden runs only")
# D-142: the hidden-run key source's mirror of the block is written beside SetHostUiInputBlocked only, read only there
SET_MIRROR = 'if (std::getenv("R3HD_NONINTRUSIVE")) rex::platform::env::set(r3hd_hostui::kTestSourceBlocked, "1");'
UNSET_MIRROR = 'if (std::getenv("R3HD_NONINTRUSIVE")) rex::platform::env::unset(r3hd_hostui::kTestSourceBlocked);'
check(host.count(SET_MIRROR) == 1 and host.count(UNSET_MIRROR) == 1 and host.count("kTestSourceBlocked") == 2 and
      host.index("SetHostUiInputBlocked(true);") < host.index(SET_MIRROR) and
      host.index("SetHostUiInputBlocked(false);") < host.index(UNSET_MIRROR),
      "app: the test source's mirror follows both SetHostUiInputBlocked calls, in hidden runs only")
key_test = read(TOOLS / "m32_key_test.h")
readers = [p.name for p in sorted(TOOLS.rglob("*")) if p.is_file() and p.suffix in (".h", ".cpp", ".py", ".ps1") and
           p.name not in ("r3hd_hostui_gate.h", "r3hd_app.h", "r3hd_pcset_regression.py") and
           ("kTestSourceBlocked" in p.read_text(errors="replace") or
            "R3HD_HOSTUI_TEST_BLOCKED" in p.read_text(errors="replace"))]
check(readers == ["m32_key_test.h"] and "set_is_active_callback(" in key_test,
      "the mirror is read only by the hidden-run key source's own driver instance")
keymap = json.loads(read(ROOT / "config/controls/keymap.json"))
check("F4" in keymap["reserved"], "F4 stays a reserved key: no player binding can collide with the panel")
prepare = read(TOOLS / "m2_prepare.py")
check("'r3hd_pc_settings.h'" in prepare, "the panel source is copied into the build tree")
built = ROOT / "private/work/rex/src/r3hd_pc_settings.h"
check(not built.exists() or built.read_bytes() == (TOOLS / "m2_host/r3hd_pc_settings.h").read_bytes(),
      "the build tree's panel equals tools/m2_host/r3hd_pc_settings.h")

# --- 2. native test --------------------------------------------------------------------------------------------
# B10 (E-319): the layout part draws the engine's own EN and TR models (an HD+ home shows all 16 settings).
def layout_models(out):
    out.mkdir(parents=True, exist_ok=True)
    for lang in ("en", "tr"):
        home = Path(tempfile.mkdtemp(prefix=f"layout_{lang}_", dir=out))
        try:
            (home / "installer.json").write_text(json.dumps({"schema": 1, "version": "test", "files": {}, "data": {}}),
                                                 encoding="utf-8")
            (home / "settings.json").write_text(json.dumps({"schema": 1, "preset": "vanilla"}) + "\n", encoding="utf-8")
            engine = [sys.executable, "-B", str(TOOLS / "r3hd_installer.py")]
            for args in (["set-preset", "--home", str(home), "--preset", "custom", "--base", "hdplus"],
                         ["set-option", "--home", str(home), "--set", f"ui_language={lang}"]):
                subprocess.run(engine + args, capture_output=True, text=True, encoding="utf-8")
            r = subprocess.run(engine + ["launcher-model", "--home", str(home)], capture_output=True, text=True,
                               encoding="utf-8")
            (out / f"layout_model_{lang}.txt").write_text(r.stdout, encoding="utf-8", newline="\n")
        finally:
            shutil.rmtree(home, ignore_errors=True)


if "--skip-native" not in sys.argv:
    layout_dir = ROOT / "private/work/pcset/layout"
    layout_models(layout_dir)
    r = subprocess.run(["cmd", "/c", str(TOOLS / "devenv.bat"), str(TOOLS / "build_hostui_test.bat")], cwd=ROOT,
                       capture_output=True, text=True, errors="replace",
                       env={**os.environ, "R3HD_PCSET_LAYOUT_DIR": str(layout_dir)})
    log = ROOT / "private/work/pcset/hostui_test.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(r.stdout + r.stderr, encoding="utf-8")
    m = re.search(r"R3HD_HOSTUI_TEST (PASS|FAIL) (\d+)/(\d+)", r.stdout)
    check(r.returncode == 0 and m is not None and m[1] == "PASS", f"native gate / driver test ({log})")
    if m:
        print(f"native: {m[0]}")

# --- 3. engine on synthetic homes ------------------------------------------------------------------------------
ENGINE = [sys.executable, "-B", str(TOOLS / "r3hd_installer.py")]


def engine(*args):
    r = subprocess.run(ENGINE + list(args) + ["--json"], capture_output=True, text=True, encoding="utf-8")
    try:
        return r.returncode, json.loads(r.stdout)
    except ValueError:
        return r.returncode, {"raw": r.stdout + r.stderr}


def make_home(base, settings):
    home = Path(base) / f"home{len(list(Path(base).iterdir()))}"
    home.mkdir()
    (home / "installer.json").write_text(json.dumps({"schema": 1, "version": "test", "files": {}, "data": {}}),
                                         encoding="utf-8")
    (home / "settings.json").write_text(json.dumps(settings, indent=1) + "\n", encoding="utf-8")
    return home


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


temp = Path(tempfile.mkdtemp(prefix="r3hd_pcset_", dir=ROOT / "private/work/pcset"))
try:
    home = make_home(temp, {"schema": 1, "preset": "vanilla"})
    code, out = engine("set-preset", "--home", str(home), "--preset", "custom", "--base", "hdplus", "--set",
                       "combo_close=original", "display=fullscreen", "mouse_buttons=on", "--keyboard", "original_pc",
                       "--key", "walk=Q", "--pad", "a=b", "b=a")
    code2, _ = engine("set-option", "--home", str(home), "--set", "ui_language=tr")
    full = json.loads(read(home / "settings.json"))
    check(code == 0 and code2 == 0 and full.get("keyboard") and full.get("controller") and
          full["preferences"].get("ui_language") == "tr", f"fixture: a Custom home with keyboard and controller maps {out}")
    model = subprocess.run(ENGINE + ["launcher-model", "--home", str(home)], capture_output=True, text=True,
                           encoding="utf-8").stdout
    rev = next((line.split("\t")[1] for line in model.splitlines() if line.startswith("REVISION\t")), None)
    check(rev == sha(home / "settings.json"), "launcher-model: REVISION is the SHA-256 of settings.json")
    before = json.loads(read(home / "settings.json"))
    code, out = engine("set-preferences", "--home", str(home), "--expect-revision", rev, "--set", "mouse_camera=on",
                       "mouse_sensitivity=70", "game_language=fr", "display=windowed")
    after = json.loads(read(home / "settings.json"))
    check(code == 0 and out.get("changed") == 1, "set-preferences with the read revision: saved")
    check(after["preferences"] == {**before["preferences"], "mouse_camera": "on", "mouse_sensitivity": "70",
                                   "game_language": "fr", "display": "windowed"}, "only the named preferences change")
    check(all(after.get(k) == before.get(k) for k in ("preset", "base", "overrides", "keyboard", "controller", "schema")),
          "preset, overrides, keyboard and controller sections kept as data")
    check(after["preferences"]["ui_language"] == "tr", "Game Language is independent of the Settings language")
    check(out.get("revision") == sha(home / "settings.json"), "the result names the new revision")
    saved = (home / "settings.json").read_bytes()
    code, out = engine("set-preferences", "--home", str(home), "--expect-revision", rev, "--set", "display=fullscreen")
    check(code == 2 and out.get("code") == "STALE" and (home / "settings.json").read_bytes() == saved,
          "an older revision: STALE, the newer file untouched")
    for pair, why in (("layer_coords=separate", "a preset correction"), ("combo_close=delayed", "Combo Meter Animation"),
                      ("ui_language=en", "a hidden preference"), ("cursor=visible", "a hidden preference"),
                      ("pacing=pinned", "mandatory behaviour"), ("mouse_sensitivity=0", "out of range"),
                      ("display=exclusive", "an unknown value"), ("nonsense=1", "an unknown key")):
        code, out = engine("set-preferences", "--home", str(home), "--set", pair)
        check(code == 2 and out.get("code") == "USAGE" and (home / "settings.json").read_bytes() == saved,
              f"set-preferences refuses {why} ({pair})")
    code, out = engine("set-preferences", "--home", str(home), "--set", "game_language=fr")
    check(code == 0 and out.get("changed") == 0 and (home / "settings.json").read_bytes() == saved,
          "an unchanged value writes nothing")
    resolved = subprocess.run([sys.executable, str(TOOLS / "r3hd_settings.py"), "resolve", "--settings",
                               str(home / "settings.json")], capture_output=True, text=True, encoding="utf-8")
    values = json.loads(resolved.stdout)["values"]
    check(values["combo_close"] == "original" and values["layer_coords"] == "separate" and
          values["game_language"] == "fr" and values["mouse_camera"] == "on",
          "the resolver: Custom on HD+ keeps its Combo override; preferences apply")
    # set-preset --expect-revision (the Settings app)
    code, out = engine("set-preset", "--home", str(home), "--preset", "hdplus", "--expect-revision", rev)
    check(code == 2 and out.get("code") == "STALE" and (home / "settings.json").read_bytes() == saved,
          "Settings app save with an old revision: STALE, nothing replaced")
    code, out = engine("set-preset", "--home", str(home), "--preset", "hdplus", "--expect-revision",
                       sha(home / "settings.json"))
    now = json.loads(read(home / "settings.json"))
    check(code == 0 and now["preset"] == "hdplus" and now["preferences"]["mouse_camera"] == "on",
          "Settings app save with the current revision: saved, preferences carried over")
    # a held lock
    (home / ".r3hd_install.lock").write_text(json.dumps({"pid": os.getpid(), "at": "now"}), encoding="utf-8")
    saved = (home / "settings.json").read_bytes()
    code, out = engine("set-preferences", "--home", str(home), "--set", "mouse_buttons=off")
    check(code == 2 and out.get("code") == "BUSY" and (home / "settings.json").read_bytes() == saved,
          "a live lock: BUSY, nothing written")
    (home / ".r3hd_install.lock").unlink()
    # a schema 1 (v1.0.x) home: its fields keep their values
    legacy = make_home(temp, {"schema": 1, "preset": "custom", "base": "vanilla", "overrides": {"render_scale": "2"}})
    code, out = engine("set-preferences", "--home", str(legacy), "--set", "mouse_camera=on")
    data = json.loads(read(legacy / "settings.json"))
    check(code == 0 and data["schema"] == 2 and data["overrides"] == {"render_scale": "2"} and
          data["preferences"] == {"mouse_camera": "on"}, "schema 1 home: kept, preference added (schema 2)")
    resolved = subprocess.run([sys.executable, str(TOOLS / "r3hd_settings.py"), "resolve", "--settings",
                               str(legacy / "settings.json")], capture_output=True, text=True, encoding="utf-8")
    check(json.loads(resolved.stdout)["values"]["render_scale"] == "2", "schema 1 home: its rendering resolution stays")
    # damaged settings are never replaced from the panel
    bad = make_home(temp, {})
    (bad / "settings.json").write_text("{not json", encoding="utf-8")
    code, out = engine("set-preferences", "--home", str(bad), "--set", "mouse_camera=on")
    check(code == 2 and read(bad / "settings.json") == "{not json", "damaged settings.json: refused, kept")
    code, out = engine("set-preferences", "--home", str(temp / "missing"), "--set", "mouse_camera=on")
    check(code == 2 and out.get("code") == "NOT_INSTALLED", "no installation: refused")
finally:
    shutil.rmtree(temp, ignore_errors=True)  # synthetic files only (no junction, no game data)

# --- 4. play.ps1 -----------------------------------------------------------------------------------------------
play = read(TOOLS / "play.ps1")
test_only = play.split("$testOnly =")[1].split("$saved = @{}")[0]
for name in ("R3HD_PCSET_TEST", "R3HD_PCSET_HOME", "R3HD_PCSET_PYTHON", "R3HD_PCSET_TOOLS", "R3HD_PCSET_SESSION",
             "R3HD_PCSET_SETTINGS_APP"):
    check(f"'{name}'" in test_only, f"play.ps1 clears and restores {name}")
check("if ($installed -and $homeSettings -and $SettingsFile -eq $homeSettings) {" in play,
      "play.ps1: persistence only for a launch from the home's own settings.json")
check(play.index("$pcsetHome = ''") < play.index("if ($DryRun) {\n    Write-Host 'DRY RUN") <
      play.index("$env:R3HD_PCSET_HOME = $pcsetHome"),
      "play.ps1: decided before the dry run (which reports it), set only for a real launch")
check('Write-Host "pc settings: $pcsetText"' in play, "dry run reports the panel's persistence")
check("R3HD_PCSET_TEST" not in play.split("$testOnly =")[1].split("$saved = @{}")[1], "play.ps1 never sets the test toggle")

print(f"R3HD_PCSET_REGRESSION {'PASS' if not failures else 'FAIL'} {checks - failures}/{checks}")
sys.exit(1 if failures else 0)
