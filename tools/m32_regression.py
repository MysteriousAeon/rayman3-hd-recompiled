#!/usr/bin/env python3
"""M32 (D-069): regression of keyboard remapping. Starts no game and shows nothing on the person's desktop.

  * keymap ties: config/controls/keymap.json names exactly the runtime's 25 keybind_* inputs; every key name is one of
    the runtime's (ui/keybinds.cpp); every scan code reaches that key through SDL's Windows scan code table and the
    runtime's SDL translation (ui/sdl_virtual_key.cpp), and every scan code that reaches a listed key is listed; the
    runtime's overlay keys (rex_app.cpp RegisterBind) are reserved; the Original PC layout is the 2003 manual's keys
  * driver: for every layout, the arguments a launch passes (tools/r3hd_settings.py) given to the real keyboard
    driver (m32_keymap_test.exe): each key alone gives exactly its pad input, taps are latched, a held Shift / Ctrl
    binding does not silence movement, the fallback keys, and the SDK's exact modifier matching without the switch
  * play.ps1 -DryRun (the built executable and the extracted data, read only): the default layout, a saved map, an
    explicit -KeyLayout, keybind_* in -ExtraArgs winning, -NoKeyboard, a damaged saved map (warned, defaults used)
  * runtime: tools/m32_runtime_patch.py applied to the SDK sources and present in the built runtime
  * setup wiring: the Settings desktop shortcut (optional, recorded, its own icon), the responsive install wait
  * the launcher (private/work/launcher) on a private desktop (--ui-test): key capture by scan code, a conflict
    resolved by a swap, a reserved key and Esc, a required input kept, layouts, Restore defaults, Save and reload,
    a preset change keeping the keys, the uncharacterised inputs never shown (M43), the Advanced page, layout at 96 and 144 DPI
usage: m32_regression.py [--keep DIR]
"""
import argparse
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
SDL = SDK / "thirdparty" / "sdl3"
LAUNCHER = ROOT / "private" / "work" / "launcher" / "r3hd_launcher.exe"
BUILD = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
GAME = Path(os.environ.get("R3HD_GAME_DIR") or ROOT / "private" / "extracted" / "5841123F")
checks, skipped = [], []

PAD = {  # pad input -> (buttons, lt, rt, lx, ly, rx, ry) of X_INPUT_GAMEPAD
    "a": (0x1000,), "b": (0x2000,), "x": (0x4000,), "y": (0x8000,), "left_shoulder": (0x0100,),
    "right_shoulder": (0x0200,), "back": (0x0020,), "start": (0x0010,), "guide": (0x0400,), "dpad_up": (0x0001,),
    "dpad_down": (0x0002,), "dpad_left": (0x0004,), "dpad_right": (0x0008,), "lstick_press": (0x0040,),
    "rstick_press": (0x0080,), "left_trigger": (0, 255), "right_trigger": (0, 0, 255),
    "lstick_left": (0, 0, 0, -32767), "lstick_right": (0, 0, 0, 32767), "lstick_up": (0, 0, 0, 0, 32767),
    "lstick_down": (0, 0, 0, 0, -32767), "rstick_left": (0, 0, 0, 0, 0, -32767), "rstick_right": (0, 0, 0, 0, 0, 32767),
    "rstick_up": (0, 0, 0, 0, 0, 0, 32767), "rstick_down": (0, 0, 0, 0, 0, 0, -32767),
    "walk": (0,),  # M49: keyboard only, no pad state of its own (tools/m49_regression.py)
}


def pad(*inputs):
    out = [0] * 7
    for i in inputs:
        v = PAD[i] + (0,) * (7 - len(PAD[i]))
        out[0] |= v[0]
        for k in range(1, 7):
            out[k] += v[k]
    return out


def check(name, cond, detail=""):
    checks.append((name, bool(cond)))
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  ({detail})" if detail and not cond else ""))


def skip(name, why):
    skipped.append(name)
    print(f"skip {name}  ({why})")


# --- keymap ties to the SDK sources ------------------------------------------------------------------------------------

def runtime_key_tables():
    """name -> VK number (keybinds.cpp + virtual_key.h) and SDL-table index -> VK number (scancodes_windows.h through
    sdl_virtual_key.cpp), parsed from the pinned sources."""
    vk_of = {m[0]: int(m[1], 16) for m in re.findall(r"\b(k\w+)\s*=\s*(0x[0-9A-Fa-f]+)", (SDK / "include/rex/ui/virtual_key.h").read_text())}
    names = {m[0]: vk_of[m[1]] for m in re.findall(r'\{"(\w+)",\s*VirtualKey::(k\w+)\}', (SDK / "src/ui/keybinds.cpp").read_text())}
    sdl_num = {m[0]: int(m[1]) for m in re.findall(r"\b(SDL_SCANCODE_\w+)\s*=\s*(\d+)", (SDL / "include/SDL3/SDL_scancode.h").read_text())}
    table = re.findall(r"/\*0x[0-9a-fA-F]+\*/\s*(SDL_SCANCODE_\w+)", (SDL / "src/events/scancodes_windows.h").read_text())
    src = (SDK / "src/ui/sdl_virtual_key.cpp").read_text()
    for needle in ("scancode >= SDL_SCANCODE_A && scancode <= SDL_SCANCODE_Z", "scancode >= SDL_SCANCODE_1 && scancode <= SDL_SCANCODE_9",
                   "scancode >= SDL_SCANCODE_F1 && scancode <= SDL_SCANCODE_F12", "scancode >= SDL_SCANCODE_KP_1 && scancode <= SDL_SCANCODE_KP_9"):
        assert needle in src, needle
    cases, pending = {}, []
    for line in src.splitlines():
        m = re.search(r"case (SDL_SCANCODE_\w+):", line)
        if m:
            pending.append(m[1])
        m = re.search(r"return VirtualKey::(k\w+);", line)
        if m and pending:
            for p in pending:
                cases[p] = vk_of[m[1]]
            pending = []

    def translate(sc: str):
        n = sdl_num.get(sc)
        if n is None:
            return None
        for lo, hi, base, off in (("A", "Z", "kA", 0), ("1", "9", "k0", 1), ("F1", "F12", "kF1", 0), ("F13", "F24", "kF13", 0),
                                  ("KP_1", "KP_9", "kNumpad0", 1)):
            if sdl_num[f"SDL_SCANCODE_{lo}"] <= n <= sdl_num[f"SDL_SCANCODE_{hi}"]:
                return vk_of[base] + off + n - sdl_num[f"SDL_SCANCODE_{lo}"]
        return cases.get(sc)
    by_index = {i: translate(sc) for i, sc in enumerate(table)}
    return names, by_index, len(table)


def keymap_checks(km):
    mnk = (SDK / "src/input/mnk/mnk_input_driver.cpp").read_text(encoding="utf-8", errors="replace")
    binds = re.findall(r"REXCVAR_DEFINE_STRING\(keybind_(\w+),", mnk)
    check("keymap: its inputs are exactly the runtime's 26 keybind settings (25 pad inputs + M49 walk)",
          sorted(km["_ids"]) == sorted(binds) and len(binds) == 26, sorted(set(km["_ids"]) ^ set(binds)))
    names, by_index, size = runtime_key_tables()
    check("keymap: SDL's Windows scan code table has its 256 entries", size == 256, size)
    unknown = [k for k in km["_names"] if k not in names]
    check("keymap: every key name is one of the runtime's", not unknown, unknown)
    wrong, listed = [], set()
    for k in km["keys"]:
        for s in k["scan"]:
            index = int(s[-2:], 16) | (0x80 if len(s) == 4 else 0)
            listed.add(index)
            if by_index.get(index) != names.get(k["name"]):
                wrong.append((k["name"], s, by_index.get(index), names.get(k["name"])))
    check("keymap: every scan code reaches its key through SDL and the runtime's translation", not wrong, wrong)
    vks = {names[k] for k in km["_names"] if k in names}
    missing = [f"{'E0' if i >= 0x80 else ''}{i & 0x7F:02X}" for i, vk in by_index.items() if vk in vks and i not in listed]
    check("keymap: every scan code that reaches a listed key is listed (no key is missed by the capture)", not missing, missing)
    overlay = set(re.findall(r'RegisterBind\("\w+",\s*"(\w+)"', (SDK / "src/ui/rex_app.cpp").read_text()))
    check("keymap: the runtime's overlay keys are reserved", overlay and overlay <= set(km["reserved"]), sorted(overlay))
    o = rs.layout_keys(km, "original_pc")
    manual = {"lstick_up": "Up", "lstick_down": "Down", "lstick_left": "Left", "lstick_right": "Right", "a": "C",
              "x": "Space", "right_trigger": "Control", "start": "Escape", "b": "W", "y": "X", "left_shoulder": "V", "right_shoulder": "V", "left_trigger": "F1"}
    check("keymap: the Original PC layout has the 2003 manual's keys as first keys (arrows, C, Space, Ctrl, Esc, "
          "W, X, shared V, F1) and Enter on confirm / Backspace on cancel", all(o[i][0] == k for i, k in manual.items())
          and "Return" in o["a"] and "Backspace" in o["b"],
          {i: o[i] for i in manual})
    m = rs.layout_keys(km, "modern")
    check("keymap: the Modern layout is W A S D, arrows for the camera, Space to jump",
          [m[i][0] for i in ("lstick_up", "lstick_left", "lstick_down", "lstick_right", "rstick_up", "a")]
          == ["W", "A", "S", "D", "Up", "Space"])
    check("keymap: the default layout is Modern; no layout uses a reserved key or a prefix",
          km["default_layout"] == "modern" and all("+" not in k and k not in km["reserved"]
                                                   for lay in km["layouts"] for v in rs.layout_keys(km, lay).values() for k in v))
    hidden = {i["id"] for i in km["inputs"] if i.get("hidden")}
    check("keymap: hidden inputs are exactly the uncharacterised ones and they say so",
          all(("Not yet characterised" in i["action"] or i["id"] == "guide") == (i["id"] in hidden) for i in km["inputs"]))
    bad = [{"layout": ["x"]}, {"layout": {"a": 1}}, ["x"], "modern", 5, {"layout": "modern", "keys": {"a": [1]}},
           {"layout": "modern", "keys": {"a": {"x": 1}}}, {"layout": "modern", "keys": "a"}, {"other": 1}]
    states = []
    for sec in bad:
        try:
            states.append(rs.resolve_keyboard(km, sec)["state"])
        except Exception as e:  # noqa: BLE001  (the point: nothing may escape)
            states.append(f"{type(e).__name__}")
    check("keymap: any malformed saved section is reported invalid, never an exception (M32 review)",
          states == ["invalid"] * len(bad), states)
    # Visual presets never change keys.
    reg = rs.load_registry()
    check("keymap: the registry has no keyboard setting (keys are not part of Vanilla / HD+ / Custom)",
          not any("key" in k for k in reg["settings"]))


# --- the real driver ---------------------------------------------------------------------------------------------------

def driver_cases(km) -> str:
    lines = []
    for layout in km["layouts"]:
        kb = rs.resolve_keyboard(km, {"layout": layout})
        lines.append(f"# layout {layout}")
        for a in kb["args"]:
            name, value = a[2:].split("=", 1)
            lines.append(f"set {name} {value}")
        for input_id, keys in kb["effective"].items():
            for k in keys:
                lines += [f"down {k}", "expect %04X %d %d %d %d %d %d" % tuple(pad(*(i for i, v in kb["effective"].items() if k in v))) + f" {layout} {k} -> {input_id}",
                          f"up {k}", "expect 0000 0 0 0 0 0 0" + f" {layout} {k} released"]
        a_key = kb["effective"]["a"][0]
        lines += [f"tap {a_key}", "expect %04X 0 0 0 0 0 0" % pad("a")[0] + f" {layout} tap latched",
                  "expect 0000 0 0 0 0 0 0 tap seen once"]
        lock, fwd = kb["effective"]["right_trigger"][0], kb["effective"]["lstick_up"][0]
        lines += [f"down {lock}", f"down {fwd}", "expect %04X %d %d %d %d %d %d" % tuple(pad("right_trigger", "lstick_up"))
                  + f" {layout} lock-on held while moving", "release"]
    # Independent numeric expectations for the shared pair, tap latch and a saved detached override.
    lines += ["tap V", "expect 0300 0 0 0 0 0 0 shared V tap latched",
              "expect 0000 0 0 0 0 0 0 shared V tap consumed",
              "set keybind_left_shoulder H", "down V", "expect 0200 0 0 0 0 0 0 detached V is RB only",
              "release", "down H", "expect 0100 0 0 0 0 0 0 detached H is LB only", "release"]
    lines += ["# the SDK's exact modifier matching without the switch (legacy Shift+arrow combinations)",
              "set mnk_modifier_keys false", "set keybind_dpad_up Shift+Up", "set keybind_rstick_up Up",
              "set keybind_right_trigger E", "set keybind_lstick_up W", "down Shift", "down Up", "expect 0001 0 0 0 0 0 0 exact: Shift+Up is the D-pad only",
              "release", "down Up", "expect 0000 0 0 0 0 0 32767 exact: Up alone", "release"]
    return "\n".join(lines) + "\n"


def driver_checks(km, keep):
    exe = BUILD / "m32_keymap_test.exe"
    if not exe.is_file():
        check("driver: m32_keymap_test.exe is built (tools\\build_milestone8.bat)", False, str(exe))
        return
    with tempfile.TemporaryDirectory(prefix="r3hd_m32_drv_") as tmp:
        cases = Path(tmp) / "cases.txt"
        cases.write_text(driver_cases(km), encoding="utf-8")
        if keep:
            shutil.copy(cases, Path(keep) / "driver_cases.txt")
        r = subprocess.run([str(exe), str(cases)], capture_output=True, text=True, timeout=120, cwd=str(BUILD))
        n = sum(1 for line in cases.read_text().splitlines() if line.startswith("expect"))
        check(f"driver: every layout's keys reach exactly their pad input in the real driver ({n} states)",
              r.returncode == 0 and "PASS" in r.stdout, (r.stdout + r.stderr)[-800:])


# --- play.ps1 ----------------------------------------------------------------------------------------------------------

def dry_run(*args):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(TOOLS / "play.ps1"), "-DryRun", "-BinDir", str(BUILD), "-GameDir", str(GAME), *args],
                       capture_output=True, text=True, timeout=300)
    out = r.stdout + r.stderr
    argv = [line.split(":", 1)[1].strip() for line in out.splitlines() if line.startswith("argument   :")]
    keyboard = next((line.split(":", 1)[1].strip() for line in out.splitlines() if line.startswith("keyboard   :")), "")
    return r.returncode, out, argv, keyboard


def play_checks(km):
    if not (BUILD / "r3hd.exe").is_file() or not (GAME / "Default.xex").is_file():
        skip("play.ps1 dry runs", "the built executable or the extracted data is missing")
        return
    want = rs.resolve_keyboard(km)["args"]
    code, out, argv, kb = dry_run()
    check("play: without settings the Modern keys are passed, every input named once", code == 0
          and [a for a in argv if a.startswith(("--keybind_", "--mnk_modifier_keys", "--mnk_walk_magnitude"))] == want and "Modern" in kb, out[-500:])
    with tempfile.TemporaryDirectory(prefix="r3hd_m32_play_") as tmp:
        f = Path(tmp) / "settings.json"
        data = rs.make_settings(rs.load_registry(), "hdplus", keyboard=rs.keyboard_section(km, "original_pc", {"x": "H"}))
        f.write_text(json.dumps(data), encoding="utf-8")
        code, out, argv, kb = dry_run("-SettingsFile", str(f))
        check("play: a saved map is passed (Original PC with Attack on H); the visual preset is HD+",
              code == 0 and "--keybind_x=H" in argv and "--keybind_a=C,Return" in argv and "--keybind_start=Escape" in argv
              and "Original PC" in kb and "saved" in kb and "--layer_coords" not in " ".join(argv), out[-500:])
        code, out, argv, kb = dry_run("-SettingsFile", str(f), "-KeyLayout", "modern")
        check("play: -KeyLayout wins over the saved map", code == 0 and "--keybind_x=E" in argv and "explicit" in kb, kb)
        code, out, argv, kb = dry_run("-SettingsFile", str(f), "-ExtraArgs", "--keybind_x=K")
        check("play: keybind_* in -ExtraArgs wins (the map's own argument for that input is left out)",
              code == 0 and argv.count("--keybind_x=K") == 1 and not any(a.startswith("--keybind_x=H") for a in argv), argv)
        code, out, argv, kb = dry_run("-ExtraArgs", "--keybind_dpad_up=Shift+Up")
        check("play: a modifier combination in -ExtraArgs keeps the SDK's exact matching",
              code == 0 and "--mnk_modifier_keys=true" not in argv and "--keybind_dpad_up=Shift+Up" in argv, argv)
        code, out, argv, kb = dry_run("-NoKeyboard")
        check("play: -NoKeyboard passes no keys", code == 0 and "--mnk_mode=false" in argv
              and not any(a.startswith("--keybind_") for a in argv), argv)
        data["keyboard"] = {"layout": "original_pc", "keys": {"a": ["F4"]}}
        f.write_text(json.dumps(data), encoding="utf-8")
        code, out, argv, kb = dry_run("-SettingsFile", str(f))
        check("play: a damaged saved map warns and uses its layout's keys; the visual settings still apply",
              code == 0 and "--keybind_a=C,Return" in argv and "invalid" in kb and "KEY_RESERVED" in out
              and "hdplus" in out, out[-600:])
        data["keyboard"] = {"layout": ["modern"]}
        f.write_text(json.dumps(data), encoding="utf-8")
        code, out, argv, kb = dry_run("-SettingsFile", str(f))
        check("play: a saved layout that is not a name still launches with the default keys (M32 review)",
              code == 0 and "--keybind_a=Space" in argv and "invalid" in kb, out[-400:])
        code, out, argv, kb = dry_run("-KeyLayout", "nope")
        check("play: an unknown -KeyLayout is refused", code != 0 and "KEY_LAYOUT_UNKNOWN" in out, out[-300:])


# --- runtime -----------------------------------------------------------------------------------------------------------

def runtime_checks():
    drv = (SDK / "src/input/mnk/mnk_input_driver.cpp").read_text(encoding="utf-8", errors="replace")
    xam = (SDK / "src/kernel/xam/xam_input.cpp").read_text(encoding="utf-8", errors="replace")
    hdr = (SDK / "include/rex/input/mnk/mnk_input_driver.h").read_text(encoding="utf-8", errors="replace")
    check("runtime: the M32 patch is in the SDK sources once (modifier switch, bindings line, test instance, hook)",
          drv.count("REXCVAR_DEFINE_BOOL(mnk_modifier_keys") == 1 and drv.count('"M32 keyboard test_instance=') == 1
          and drv.count("|| test_enabled_;") == 1 and hdr.count("void SetTestEnabled(bool on)") == 1
          and xam.count("if (m32keys::Enabled()) s = m32keys::Sample(bool(input_state));") == 1
          and (SDK / "include/rex/m32_key_test.h").read_bytes() == (TOOLS / "m32_key_test.h").read_bytes())
    check("runtime: the hidden key source needs both R3HD_NONINTRUSIVE and R3HD_KEYMAP_TEST; play.ps1 clears the latter",
          'std::getenv("R3HD_NONINTRUSIVE") && std::getenv("R3HD_KEYMAP_TEST")' in (TOOLS / "m32_key_test.h").read_text()
          and "'R3HD_KEYMAP_TEST'" in (TOOLS / "play.ps1").read_text())
    dll = BUILD / "rexruntime.dll"
    if dll.is_file():
        b = dll.read_bytes()
        check("runtime: the built runtime carries the M32 lines", b"M32 keyboard test_instance=" in b and b"M32 keymap_test" in b
              and b"mnk_modifier_keys" in b)
    else:
        check("runtime: rexruntime.dll is built", False, str(dll))


# --- setup wiring ------------------------------------------------------------------------------------------------------

def installer_checks():
    iss = (TOOLS / "installer" / "r3hd_setup.iss").read_text(encoding="utf-8")
    check("setup: version 0.32.0 or later (1.0.0)", re.search(r'#define AppVersion "(0\.(3[2-9]|[4-9][0-9])\.0(-private)?|[1-9][0-9]*\.[0-9]+\.[0-9]+)"', iss))
    check("setup: an optional Settings desktop shortcut (checked by default on fresh installs) with the launcher's second icon",
          re.search(r'^Name: "settingsicon"; Description: "[^"]+"; GroupDescription: "[^"]+"$', iss, re.M)
          and 'Check: SettingsShortcut' in iss and 'IconIndex: 1' in iss and "--settings-shortcut 1" in iss)
    check("setup: a declined or deleted Settings shortcut is not recreated; a declined one this installer made is removed",
          "Result := RecordedSettings = '1'" in iss and "not FileExists(SettingsLink) then RecordedSettings := '0'" in iss
          and "WizardSelectTasks('!settingsicon')" in iss and "Check: RemoveDeclinedSettings" in iss)
    check("setup: the wizard stays enabled while the engine runs (Exec's window disabler is undone in the output "
          "callback; the progress page keeps its own Cancel)",
          "external 'EnableWindow@user32.dll stdcall'" in iss and "KeepWizardResponsive" in iss
          and "EnableWindow(WizardForm.Handle, True)" in iss)
    check("setup: Next / Back cannot be used while the engine runs", "WizardForm.NextButton.Enabled := False" in iss
          and "WizardForm.BackButton.Enabled := False" in iss)
    src = (TOOLS / "launcher" / "r3hd_launcher.rc").read_text(encoding="utf-8")
    check("launcher: icon 1 = the game, icon 2 = Settings (a gear; make_r3hd_icon.py --variant settings)",
          '1 ICON "r3hd.ico"' in src and '2 ICON "r3hd_settings.ico"' in src
          and icon.build("settings") != icon.build("game"))
    if LAUNCHER.is_file():
        b = LAUNCHER.read_bytes()
        imgs = [s for s in (16, 32) if bytes(icon.bmp(s, icon.render(s, "settings"))[40:200]) in b]
        check("launcher: the built launcher carries the Settings icon", imgs == [16, 32], imgs)


# --- the launcher ------------------------------------------------------------------------------------------------------

def launcher_checks(km, keep):
    if not LAUNCHER.is_file():
        check("launcher built (tools\\launcher\\build_launcher.bat)", False)
        return
    import m30_launcher_regression as m30
    saved = {k: os.environ.get(k) for k in engine.HOOKS}
    with tempfile.TemporaryDirectory(prefix="r3hd_m32_ui_") as tmp:
        t = Path(tmp)
        sys32 = t / "sys32"
        sys32.mkdir()
        for n in engine.VC_RUNTIME:
            (sys32 / n).write_bytes(b"x")
        os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0", R3HD_INSTALL_FAKE_LAUNCHER="0")
        try:
            home = m30.make_home(t, "home")

            def key(dump, i):
                return dump.get(f"key.{i}", "").split(" caption=")[0]

            def run(name, lines, need):
                code, d, log, out = m30.ui(home, t, name, "\n".join(lines + ["click close", ""]))
                if keep:
                    shutil.copytree(out, Path(keep) / f"ui_{name}", dirs_exist_ok=True)
                ok = code == 0 and all(k in d for k in need)
                check(f"UI run {name} completed", ok, log[-600:])
                return d if ok else None
            # 1: capture, conflicts, reserved keys, Esc, required inputs, removal, Save
            d = run("m32a", ["page controls", "dump c0", "shot controls_96",
                             "key x 0", "dump cap", "press 21", "dump swap",          # F is the left stick press's: swap
                             "key a 0", "press 3E", "dump reserved", "press 01", "dump esc",  # F4 refused; Esc ends it
                             "rclick a 0", "dump required",                            # Jump's only key stays
                             "key a 1", "press E04F", "dump second",                   # End (an extended key)
                             "rclick a 1", "dump removed", "click save", "dump saved"],
                    ("c0", "cap", "swap", "reserved", "esc", "required", "second", "removed", "saved"))
            if not d:
                return
            visible = [i["id"] for i in km["inputs"] if not i.get("hidden")]
            check("UI: Controls shows the Modern keys; only characterised inputs are shown",
                  d["c0"]["key_layout"] == "modern" and key(d["c0"], "a") == "Space," and key(d["c0"], "x") == "E,"
                  and int(d["c0"]["key_rows_shown"]) == len(visible)
                  and all(("visible=1" in d["c0"][f"key.{i['id']}"]) != bool(i.get("hidden")) for i in km["inputs"]))
            check("UI: a key button enters capture mode", d["cap"]["key_capture"] == "x.0"
                  and "caption=Press a key...|" in d["cap"]["key.x"])
            check("UI: a key used elsewhere is swapped, and the status says where it went",
                  key(d["swap"], "x") == "F," and key(d["swap"], "lstick_press") == "E," and d["swap"]["key_capture"] == ""
                  and "Keys swapped:" in d["swap"]["status"])
            check("UI: a reserved key is refused and the capture continues; Esc ends it unchanged",
                  d["reserved"]["key_capture"] == "a.0" and "cannot be used" in d["reserved"]["status"]
                  and key(d["reserved"], "a") == "Space," and d["esc"]["key_capture"] == "" and key(d["esc"], "a") == "Space,")
            check("UI: the only key of a required input cannot be removed", key(d["required"], "a") == "Space,"
                  and "needs at least one key" in d["required"]["status"])
            check("UI: a second key is captured by its scan code (End, an extended key)",
                  key(d["second"], "a") == "Space,End" and "caption=Space|End" in d["second"]["key.a"])
            check("UI: right-click removes a second key", key(d["removed"], "a") == "Space,")
            s1 = m30.settings(home)
            check("UI: Save stores only the changed inputs of the layout",
                  s1.get("keyboard") == {"layout": "modern", "keys": {"x": ["F"], "lstick_press": ["E"]}}, s1.get("keyboard"))
            # 2: a new Settings window shows the saved keys; another layout; a visual preset change keeps the keys
            d = run("m32b", ["page controls", "dump reloaded", "layout original_pc", "dump orig", "key x 0", "press 23",
                             "click save", "page settings", "profile hdplus", "click save", "dump hdplus"],
                    ("reloaded", "orig", "hdplus"))
            if not d:
                return
            check("UI: the saved keys survive closing and opening Settings", key(d["reloaded"], "x") == "F,"
                  and key(d["reloaded"], "lstick_press") == "E,")
            o = rs.layout_keys(km, "original_pc")
            check("UI: choosing a layout shows its keys and its description",
                  d["orig"]["key_layout"] == "original_pc" and key(d["orig"], "a") == ",".join(o["a"])
                  and d["orig"]["layout_text"] == "")
            s2 = m30.settings(home)
            check("UI: the new layout and its change are saved, and changing the visual preset kept them",
                  s2["preset"] == "hdplus" and s2.get("keyboard") == {"layout": "original_pc", "keys": {"x": ["H"]}}, s2)
            # 3: Restore defaults, the hidden inputs, the Advanced page, DPI
            d = run("m32c", ["page controls", "click restore", "dump restored", "click save", "dump all",
                             "dpi 144", "dump c144", "shot controls_144", "page advanced", "dump adv",
                             "shot advanced_144", "dpi 96", "page settings", "dump settings96", "shot settings_96"],
                    ("restored", "all", "c144", "adv", "settings96"))
            if not d:
                return
            check("UI: Restore defaults gives the layout's keys; saved, only the layout remains",
                  key(d["restored"], "x") == ",".join(o["x"])
                  and m30.settings(home).get("keyboard") == {"layout": "original_pc", "keys": {}}, m30.settings(home))
            check("UI (M43): the uncharacterised inputs are never shown and nothing offers to show them",
                  int(d["all"]["key_rows_shown"]) == len(visible) == int(d["c144"]["key_rows_shown"]))
            check("UI: Controls lays out without overlap at 96 and 144 DPI",
                  m30.layout_ok(d["all"]) and m30.layout_ok(d["c144"]), [d[k].get("controls") for k in ("all", "c144")])
            check("UI: Diagnostics and the folder are on the Advanced page, not in the everyday settings",
                  d["adv"]["page"] == "advanced" and d["adv"]["advanced_visible"] == "1"
                  and d["settings96"]["advanced_visible"] == "0" and m30.layout_ok(d["adv"]) and m30.layout_ok(d["settings96"])
                  and "enabled=1" in d["adv"].get("setting.diagnostics", ""))
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
    if a.keep:
        Path(a.keep).mkdir(parents=True, exist_ok=True)
    km = rs.load_keymap()
    keymap_checks(km)
    driver_checks(km, a.keep)
    if a.skip_runtime_dry_run:
        skip("play.ps1 dry runs", "explicit --skip-runtime-dry-run; game may be running")
    else:
        play_checks(km)
    runtime_checks()
    installer_checks()
    launcher_checks(km, a.keep)
    failed = sum(not ok for _, ok in checks)
    print(f"M32_REGRESSION {'PASS' if not failed else 'FAIL'} checks={len(checks)} failures={failed} skipped={len(skipped)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
