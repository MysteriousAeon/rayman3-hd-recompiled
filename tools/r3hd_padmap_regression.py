#!/usr/bin/env python3
"""D-115 / D-116: regression of the controller map. Starts no game, opens no controller and shows nothing on the
person's desktop.

  * ties: config/controls/padmap.json = tools/r3hd_padmap.h's table (names, order, bits, virtual keys; the analog inputs)
    = the SDK's X_INPUT_GAMEPAD_* / VirtualKey kXInputPad* values; every button is a pad input of the keymap; the actions
    Settings lists are the controls with run or human evidence (E-274, E-277)
  * resolver: the original controls by default (no R3HD_PAD_MAP); a saved map; schema 3 kept without a map, 4 with one;
    conflicts and unknown names refused when written; every damaged stored shape recovers to the original controls with
    a warning and never changes the keyboard map; older settings files read; restoring stores nothing
  * engine CLI: set-preset --pad on a synthetic installation, kept by a later set-preset without --pad
  * play.ps1 -DryRun (the built executable and the extracted data, read only): default, saved, damaged; the test-only
    switch and the map variable are cleared before a launch
  * runtime: tools/r3hd_padmap_patch.py applied to the SDK sources (physical devices only, before the merge, state and
    keystrokes; the SDL driver and its DualSense calls untouched) and present in the built runtime
  * the launcher (private/work/launcher) on a private desktop (--ui-test): the Controller tab's thirteen rows, capture with
    simulated controllers (readings and HID reports; never a real device): swaps, kinds, held buttons, Guide / PS,
    Esc, the time limit, focus loss, disconnect; Restore, Save and reload, keyboard coexistence, a damaged map; layout
    of both tabs in English and Turkish at 100 / 125 / 150 % on 1080p and at 720p, a small screen, a short window
usage: r3hd_padmap_regression.py [--keep DIR] [--skip-runtime-dry-run]
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
import r3hd_installer as engine  # noqa: E402
import r3hd_settings as rs  # noqa: E402

SDK = ROOT / "external" / "rexglue-sdk"
BUILD = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
GAME = Path(os.environ.get("R3HD_GAME_DIR") or ROOT / "private" / "extracted" / "5841123F")
checks, skipped = [], []

SDK_BIT = {"a": "A", "b": "B", "x": "X", "y": "Y", "left_shoulder": "LEFT_SHOULDER", "right_shoulder": "RIGHT_SHOULDER",
           "back": "BACK", "start": "START", "lstick_press": "LEFT_THUMB", "rstick_press": "RIGHT_THUMB",
           "dpad_up": "DPAD_UP", "dpad_down": "DPAD_DOWN", "dpad_left": "DPAD_LEFT", "dpad_right": "DPAD_RIGHT"}
SDK_VK = {"a": "A", "b": "B", "x": "X", "y": "Y", "left_shoulder": "LShoulder", "right_shoulder": "RShoulder",
          "back": "Back", "start": "Start", "lstick_press": "LThumbPress", "rstick_press": "RThumbPress",
          "dpad_up": "DpadUp", "dpad_down": "DpadDown", "dpad_left": "DpadLeft", "dpad_right": "DpadRight"}


def check(name, cond, detail=""):
    checks.append((name, bool(cond)))
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  ({detail})" if detail and not cond else ""))


def skip(name, why):
    skipped.append(name)
    print(f"skip {name}  ({why})")


def refused(fn, code):
    try:
        fn()
    except rs.Refused as e:
        return e.code == code
    return False


# --- ties -------------------------------------------------------------------------------------------------------------

def tie_checks(km, pm):
    header = (TOOLS / "r3hd_padmap.h").read_text(encoding="utf-8")
    table = re.findall(r'\{"(\w+)", 0x([0-9A-F]{4}), 0x([0-9A-F]{4})\}', header)
    raw = json.loads((ROOT / "config" / "controls" / "padmap.json").read_text(encoding="utf-8"))
    check("ties: padmap.json and r3hd_padmap.h name the same 14 buttons in the same order with the same bits and keys",
          [(b["id"], b["bit"].upper(), b["vk"].upper()) for b in raw["buttons"]] == table and len(table) == 14, table)
    inp = (SDK / "include/rex/input/input.h").read_text(encoding="utf-8")
    vk = (SDK / "include/rex/ui/virtual_key.h").read_text(encoding="utf-8")
    bits = {m[0]: int(m[1], 16) for m in re.findall(r"X_INPUT_GAMEPAD_(\w+) = 0x([0-9A-Fa-f]+)", inp)}
    vks = {m[0]: int(m[1], 16) for m in re.findall(r"kXInputPad(\w+) = 0x([0-9A-Fa-f]+)", vk)}
    check("ties: every bit is the SDK's X_INPUT_GAMEPAD_* value",
          all(bits.get(SDK_BIT[n]) == int(b, 16) for n, b, _ in table), bits)
    check("ties: every virtual key is the SDK's VirtualKey kXInputPad* value",
          all(vks.get(SDK_VK[n]) == int(v, 16) for n, _, v in table), vks)
    mask = 0
    for _, b, _ in table:
        mask |= int(b, 16)
    check("ties: the header's mask is the 14 bits (Guide 0x0400 and 0x0800 pass)",
          f"kMapped = 0x{mask:04X}" in header and mask & 0x0C00 == 0)
    check("ties: every button is a pad input of the keymap (not keyboard-only)",
          all(i in km["_ids"] and not next(x for x in km["inputs"] if x["id"] == i).get("keyboard_only")
              for i in pm["_ids"] if pm["_kind"][i] == "button"))
    check("ties: Settings lists thirteen confirmed controls, including human-verified health bar and Grimace (E-277)",
          pm["_shown"] == ["left_stick", "right_stick", "a", "x", "y", "b", "right_trigger", "left_trigger",
                           "left_shoulder", "right_shoulder", "start",
                           "dpad_up", "dpad_down"], pm["_shown"])
    actions = {a["input"]: a for a in raw["actions"]}
    inputs = {i["id"]: i for i in km["inputs"]}
    descriptions = {
        "y": "Look Mode (hold)",
        "b": "Roll / Back",
        "left_shoulder": "Show Health Bar",
        "right_shoulder": "Grimace",
    }
    check("inventory: both views use the final concise labels without gameplay conditions or unlock spoilers",
          all(inputs[i]["group"] == actions[i]["group"] == "actions" and not inputs[i].get("hidden")
              and inputs[i]["action"] == actions[i]["name"] == text for i, text in descriptions.items()))
    check("defaults: Modern sends 1 / 3, Original PC shares V; controller defaults stay identity",
          all(rs.resolve_keyboard(km, explicit_layout=l)["effective"][i] == [key]
              and f"--keybind_{i}={key}" in rs.resolve_keyboard(km, explicit_layout=l)["args"]
              for l in ("modern", "original_pc") for i, key in (("left_shoulder", "1" if l == "modern" else "V"), ("right_shoulder", "3" if l == "modern" else "V")))
          and pm["_labels"]["left_shoulder"] == "LB / L1" and pm["_labels"]["right_shoulder"] == "RB / R1"
          and all(i == b for i, b in rs.resolve_controller(pm)["buttons"].items()))
    check("ties: the analog inputs of padmap.json are the header's, in its order (triggers, then sticks)",
          [a["id"] for a in raw["analog"]] == re.findall(r'"(\w+)"', re.search(r"kAnalog\[4\] = \{([^}]*)\}", header)[1])
          and "kInputs = 18" in header)
    payload = json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))
    allow = (ROOT / "config" / "release" / "payload_allowlist.json").read_text(encoding="utf-8")
    check("ties: an installation carries padmap.json beside keymap.json (the installed resolver needs both)",
          payload["app_files"].get("app/config/controls/padmap.json") == "config/controls/padmap.json"
          and '"app/config/controls/padmap.json"' in allow)
    check("ties: one label per button, Xbox / PlayStation where they differ",
          pm["_labels"]["a"] == "A / Cross" and pm["_labels"]["dpad_up"] == "D-pad up"
          and pm["_labels"]["right_trigger"] == "RT / R2" and len(set(pm["_labels"].values())) == 18)


# --- resolver ---------------------------------------------------------------------------------------------------------

def resolver_checks(km, pm):
    reg = rs.load_registry()
    out = rs.resolve(reg)
    check("resolver: without settings the original controls apply and nothing is passed",
          out["controller"]["state"] == "default" and out["controller"]["env"] == ""
          and all(i == b for i, b in out["controller"]["buttons"].items()))
    sec = rs.controller_section(pm, {"a": "b", "b": "a"})
    data = rs.make_settings(reg, "hdplus", controller=sec)
    out = rs.resolve(reg, settings=data)
    check("resolver: a saved swap is stored as the changed inputs only, in a schema 4 file, and passed as pairs",
          data["schema"] == 4 and data["controller"] == {"buttons": {"a": "b", "b": "a"}}
          and out["controller"]["state"] == "saved" and out["controller"]["env"] == "a=b,b=a" and out["preset"] == "hdplus")
    rot = rs.controller_section(pm, {"y": "a", "a": "x", "x": "y"})
    check("resolver: the pairs follow the runtime table's order, whatever order a person chose them in",
          rs.resolve(reg, settings=rs.make_settings(reg, "vanilla", controller=rot))["controller"]["env"] == "a=x,x=y,y=a")
    plain = rs.make_settings(reg, "vanilla")
    restored = rs.make_settings(reg, "vanilla", controller={"buttons": {}})
    check("resolver: no map and a restored map store nothing and stay schema 3 (readable by 1.0.1)",
          plain == restored and plain["schema"] == 3 and "controller" not in plain)
    check("resolver: a button on two inputs is refused (PAD_CONFLICT) and names both",
          refused(lambda: rs.controller_section(pm, {"a": "b"}), "PAD_CONFLICT"))
    try:
        rs.controller_section(pm, {"x": "start"})
    except rs.Refused as e:
        check("resolver: the conflict message names the button and both actions",
              "Start / Options" in e.detail and "Attack" in e.detail and "Pause" in e.detail, e.detail)
    check("resolver: an unknown button, an analog input for a button and an unknown input are refused",
          refused(lambda: rs.controller_section(pm, {"a": "jump"}), "PAD_BUTTON_UNKNOWN")
          and refused(lambda: rs.controller_section(pm, {"a": "left_trigger"}), "PAD_KIND")
          and refused(lambda: rs.controller_section(pm, {"lstick_up": "a"}), "PAD_INPUT_UNKNOWN")
          and refused(lambda: rs.controller_section(pm, {"walk": "a"}), "PAD_INPUT_UNKNOWN"))
    tri = rs.controller_section(pm, {"left_trigger": "right_trigger", "right_trigger": "left_trigger",
                                     "left_stick": "right_stick", "right_stick": "left_stick"})
    out_tri = rs.resolve(reg, settings=rs.make_settings(reg, "vanilla", controller=tri))["controller"]
    check("resolver (D-116): the trigger and stick exchanges are stored under analog (no buttons changed), schema 4, "
          "passed after the buttons", tri == {"buttons": {}, "analog": {"left_trigger": "right_trigger",
                                                                       "right_trigger": "left_trigger",
                                                                       "left_stick": "right_stick",
                                                                       "right_stick": "left_stick"}}
          and out_tri["state"] == "saved"
          and out_tri["env"] == "left_trigger=right_trigger,right_trigger=left_trigger,left_stick=right_stick,right_stick=left_stick"
          and rs.make_settings(reg, "vanilla", controller=tri)["schema"] == 4)
    check("resolver (D-116): a one-way exchange, a trigger for a stick and a stick for a button are refused",
          refused(lambda: rs.controller_section(pm, {"left_trigger": "right_trigger"}), "PAD_CONFLICT")
          and refused(lambda: rs.controller_section(pm, {"left_trigger": "left_stick", "left_stick": "left_trigger"}), "PAD_KIND")
          and refused(lambda: rs.controller_section(pm, {"a": "left_stick", "left_stick": "a"}), "PAD_KIND"))
    check("resolver: make_settings never persists a refused section",
          refused(lambda: rs.make_settings(reg, "vanilla", controller={"buttons": {"a": "b"}}), "PAD_CONFLICT"))
    kb = rs.keyboard_section(km, "original_pc", {"x": "H"})
    base_file = rs.make_settings(reg, "custom", "hdplus", ["texture_orient=corrected"], keyboard=kb)
    base_out = rs.resolve(reg, settings=base_file)
    damaged = [{"buttons": {"a": "b"}}, {"buttons": {"a": "zz"}}, {"buttons": {"zz": "a"}}, {"buttons": ["a"]},
               {"buttons": {"a": 1}}, {"buttons": {"a": None}}, {"other": {}}, ["a=b"], "a=b,b=a", 7, None,
               {"buttons": {"a": "b", "b": "a", "x": "a"}},
               # D-116: analog shapes
               {"analog": {"left_trigger": "right_trigger"}}, {"analog": {"a": "b", "b": "a"}},
               {"buttons": {"left_trigger": "right_trigger", "right_trigger": "left_trigger"}},
               {"analog": {"left_stick": "right_trigger", "right_trigger": "left_stick"}}, {"analog": ["left_stick"]}]
    ok = True
    for section in damaged:
        f = dict(base_file, schema=4, controller=section)
        o = rs.resolve(reg, settings=f)
        state_ok = o["controller"]["state"] == ("default" if section is None else "invalid")
        ok &= (state_ok and o["controller"]["env"] == "" and o["keyboard"] == base_out["keyboard"]
               and o["values"] == base_out["values"] and o["preset"] == base_out["preset"]
               and (section is None or any(w.startswith("controller: saved controller buttons not used") for w in o["warnings"])))
    check(f"resolver: {len(damaged)} damaged stored sections recover to the original controls with a warning; the "
          "keyboard map, preset and values are those of the same file without it", ok)
    check("resolver: older settings files (schema 1, 2, 3) resolve with the original controls",
          all(rs.resolve(reg, settings=s)["controller"]["state"] == "default" for s in
              ({"schema": 1, "preset": "hdplus"}, {"schema": 2, "preset": "vanilla", "preferences": {"render_scale": "2"}},
               {"schema": 3, "preset": "vanilla", "keyboard": {"layout": "modern", "keys": {}}})))
    with tempfile.TemporaryDirectory(prefix="r3hd_padmap_res_") as tmp:
        f = Path(tmp) / "settings.json"
        f.write_text(json.dumps({"schema": 3, "preset": "vanilla", "controller": {"buttons": {}}}), encoding="utf-8")
        check("resolver: a controller section needs schema 4 (a schema 3 file with one is refused as hand-made)",
              refused(lambda: rs.load_settings_file(f), "SETTINGS_INVALID"))
        f.write_text(json.dumps({"schema": 5, "preset": "vanilla"}), encoding="utf-8")
        check("resolver: a newer schema is refused as newer", refused(lambda: rs.load_settings_file(f), "SETTINGS_NEWER"))
        both = rs.make_settings(reg, "vanilla", keyboard=kb, controller=sec)
        o1, o2 = rs.resolve(reg, settings=both), rs.resolve(reg, settings=rs.make_settings(reg, "vanilla", keyboard=kb))
        check("resolver: keyboard and controller maps are independent (the keyboard arguments are identical with and "
              "without a controller map; Jump keeps its keys)", o1["keyboard"]["args"] == o2["keyboard"]["args"]
              and o1["controller"]["env"] == "a=b,b=a" and o2["controller"]["env"] == "")
        # CLI: write --pad, then --keep-preferences without --pad keeps it, --pad alone restores
        cli = [sys.executable, str(TOOLS / "r3hd_settings.py"), "write", str(f)]
        f.unlink()
        r1 = subprocess.run(cli + ["--preset", "vanilla", "--pad", "a=y", "y=a"], capture_output=True, text=True)
        s1 = json.loads(f.read_text(encoding="utf-8"))
        r2 = subprocess.run(cli + ["--preset", "hdplus", "--keep-preferences"], capture_output=True, text=True)
        s2 = json.loads(f.read_text(encoding="utf-8"))
        r3 = subprocess.run(cli + ["--preset", "hdplus", "--pad", "a=b"], capture_output=True, text=True)
        s3 = json.loads(f.read_text(encoding="utf-8"))
        r4 = subprocess.run(cli + ["--preset", "hdplus", "--keep-preferences", "--pad"], capture_output=True, text=True)
        s4 = json.loads(f.read_text(encoding="utf-8"))
        check("resolver CLI: --pad writes, --keep-preferences keeps, a conflict is refused (file unchanged), --pad alone "
              "restores", r1.returncode == 0 and s1["controller"] == {"buttons": {"a": "y", "y": "a"}}
              and r2.returncode == 0 and s2.get("controller") == s1["controller"] and s2["preset"] == "hdplus"
              and r3.returncode == 2 and "PAD_CONFLICT" in r3.stdout and s3 == s2
              and r4.returncode == 0 and "controller" not in s4 and s4["schema"] == 3, (r3.stdout, s4))


# --- engine CLI -------------------------------------------------------------------------------------------------------

def engine_checks():
    saved = {k: os.environ.get(k) for k in engine.HOOKS}
    with tempfile.TemporaryDirectory(prefix="r3hd_padmap_eng_") as tmp:
        t = Path(tmp)
        sys32 = t / "sys32"
        sys32.mkdir()
        for n in engine.VC_RUNTIME:
            (sys32 / n).write_bytes(b"x")
        env = dict(os.environ, R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0", R3HD_INSTALL_FAKE_LAUNCHER="0")
        try:
            os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0", R3HD_INSTALL_FAKE_LAUNCHER="0")
            pl, tree, rels = engine.make_fixture(t)
            home = t / "home"
            engine.install(home, pl, tree, "vanilla", releases=rels, log=lambda *_: None)

            def cli(*args):
                return subprocess.run([sys.executable, str(TOOLS / "r3hd_installer.py"), *args, "--home", str(home),
                                       "--releases", str(t / "releases.json")], capture_output=True, text=True, env=env)
            r1 = cli("set-preset", "--preset", "hdplus", "--pad", "x=y", "y=x")
            s1 = json.loads((home / "settings.json").read_text(encoding="utf-8"))
            r2 = cli("set-preset", "--preset", "vanilla", "--keyboard", "original_pc")
            s2 = json.loads((home / "settings.json").read_text(encoding="utf-8"))
            r3 = cli("set-preset", "--preset", "vanilla", "--pad", "x=y")
            r4 = cli("launcher-model")
            r6 = cli("set-preset", "--preset", "vanilla", "--pad", "left_stick=right_stick", "right_stick=left_stick")
            s6 = json.loads((home / "settings.json").read_text(encoding="utf-8"))
            check("engine CLI (D-116): set-preset --pad exchanges the sticks (stored under analog)",
                  r6.returncode == 0 and s6.get("controller") == {"buttons": {}, "analog": {"left_stick": "right_stick",
                                                                                           "right_stick": "left_stick"}},
                  (r6.stdout[-300:], s6.get("controller")))
            r5 = cli("set-preset", "--preset", "vanilla", "--pad")
            s5 = json.loads((home / "settings.json").read_text(encoding="utf-8"))
            check("engine CLI: set-preset --pad saves the map; a later set-preset without --pad keeps it; a conflict is "
                  "refused; --pad alone restores the original controls",
                  r1.returncode == 0 and s1.get("controller") == {"buttons": {"x": "y", "y": "x"}}
                  and r2.returncode == 0 and s2.get("controller") == s1["controller"] and s2["keyboard"]["layout"] == "original_pc"
                  and r3.returncode != 0 and "PAD_CONFLICT" in (r3.stdout + r3.stderr)
                  and "PADBIND\tx\ty\n" in r4.stdout and r5.returncode == 0 and "controller" not in s5
                  and s5.get("keyboard") == s2["keyboard"], (r1.stdout[-300:], r3.stdout[-300:]))
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


# --- play.ps1 ---------------------------------------------------------------------------------------------------------

def dry_run(*args):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(TOOLS / "play.ps1"), "-DryRun", "-BinDir", str(BUILD), "-GameDir", str(GAME), *args],
                       capture_output=True, text=True, timeout=300)
    out = r.stdout + r.stderr
    line = lambda k: next((ln.split(":", 1)[1].strip() for ln in out.splitlines() if ln.startswith(k)), None)  # noqa: E731
    argv = [ln.split(":", 1)[1].strip() for ln in out.splitlines() if ln.startswith("argument   :")]
    return r.returncode, out, line("controller :"), line("keyboard   :"), argv


def play_checks(km, pm):
    src = (TOOLS / "play.ps1").read_text(encoding="utf-8")
    test_only = re.search(r"\$testOnly = (.*?)\n\$saved", src, re.S)
    check("play: the map variable and the test-only switch are cleared before every launch, then the map is set",
          test_only and "'R3HD_PADMAP_TEST'" in test_only[1] and "'R3HD_PAD_MAP'" in test_only[1]
          and src.index("$env:R3HD_PAD_MAP = $padMap") > src.index("foreach ($name in $testOnly)"))
    if not (BUILD / "r3hd.exe").is_file() or not (GAME / "Default.xex").is_file():
        skip("play.ps1 dry runs", "the built executable or the extracted data is missing")
        return
    reg = rs.load_registry()
    code, out, pad, kb0, argv0 = dry_run()
    check("play: without settings the controller line says default", code == 0 and pad == "default", out[-400:])
    with tempfile.TemporaryDirectory(prefix="r3hd_padmap_play_") as tmp:
        f = Path(tmp) / "settings.json"
        f.write_text(json.dumps(rs.make_settings(reg, "vanilla", controller=rs.controller_section(pm, {"a": "b", "b": "a"}))),
                     encoding="utf-8")
        code, out, pad, kb, argv = dry_run("-SettingsFile", str(f))
        check("play: a saved map is reported and the keyboard arguments are unchanged",
              code == 0 and pad == "saved: a=b,b=a" and kb == kb0 and [a for a in argv if "keybind" in a]
              == [a for a in argv0 if "keybind" in a], out[-400:])
        f.write_text(json.dumps(rs.make_settings(reg, "vanilla", controller=rs.controller_section(
            pm, {"left_trigger": "right_trigger", "right_trigger": "left_trigger"}))), encoding="utf-8")
        code, out, pad, kb, argv = dry_run("-SettingsFile", str(f))
        check("play (D-116): a trigger exchange is passed to the runtime and the keyboard arguments are unchanged",
              code == 0 and pad == "saved: left_trigger=right_trigger,right_trigger=left_trigger" and kb == kb0, out[-400:])
        f.write_text(json.dumps({"schema": 4, "preset": "hdplus", "controller": {"buttons": {"a": "b"}}}), encoding="utf-8")
        code, out, pad, kb, argv = dry_run("-SettingsFile", str(f))
        check("play: a damaged map warns, launches with the original controls and keeps the preset",
              code == 0 and pad == "invalid" and "PAD_CONFLICT" in out and "hdplus" in out, out[-500:])


# --- runtime ----------------------------------------------------------------------------------------------------------

def runtime_checks():
    import r3hd_padmap_patch as patch
    system = (SDK / "src/input/input_system.cpp").read_text(encoding="utf-8")
    get_state = system[system.index("X_RESULT InputSystem::GetState("):system.index("X_RESULT InputSystem::SetState(")]
    get_key = system[system.index("X_RESULT InputSystem::GetKeystroke("):system.index("std::unique_ptr<InputSystem> CreateDefaultInputSystem(")]
    check("runtime: the header is installed unchanged",
          (SDK / "include/rex/r3hd_padmap.h").read_bytes() == (TOOLS / "r3hd_padmap.h").read_bytes())
    check("runtime: GetState maps non-synthetic devices once (buttons, then the analog exchanges), after their state is "
          "read and before the merge", "ApplyAnalog(lt, rt, lx, ly, rx, ry)" in patch.STATE_MAP
          and patch.STATE_MAP_D115 not in system and system.count(patch.STATE_MAP) == 1 and get_state.index("GetDeviceState(id, &state)") < get_state.index(patch.STATE_MAP)
          < get_state.index("active_devices_.Observe") < get_state.index("MergeInto(merged, state)"))
    check("runtime: GetKeystroke maps a physical pad's virtual key once, before the result is returned",
          system.count(patch.KEY_MAP) == 1 and get_key.index("GetDeviceKeystroke(id, flags, out_keystroke)")
          < get_key.index(patch.KEY_MAP) < get_key.index("return result;"))
    check("runtime: every run logs the map's state (at the end of the factory, outside the M23 patch's search text)",
          system.count(patch.FACTORY_LOG + patch.FACTORY_END) == 1 and system.count(patch.M23_LOG + "\n  if (!tool_mode) {") == 1)
    xam = (SDK / "src/kernel/xam/xam_input.cpp").read_text(encoding="utf-8")
    check("runtime: the scheduled-state test hook is gated (NONINTRUSIVE + R3HD_PADMAP_TEST) and sits after the M32 source",
          xam.count(patch.TEST_MAP) == 1 and xam.index(patch.M32_LINE) < xam.index(patch.TEST_MAP)
          and 'std::getenv("R3HD_NONINTRUSIVE") && std::getenv("R3HD_PADMAP_TEST")'
          in (TOOLS / "r3hd_padmap.h").read_text(encoding="utf-8"))
    sdl = (SDK / "src/input/sdl/sdl_input_driver.cpp").read_text(encoding="utf-8")
    ds_sdl = (SDK / "include/rex/r3hd_ds_sdl.h").read_text(encoding="utf-8")
    check("runtime: the SDL driver is not touched (its pad state, rumble and the DualSense step see the physical pad)",
          "padmap" not in sdl and "r3hd_ds::Step(*controller, controllers_" in sdl)
    check("runtime (D-116): the DualSense resistance follows the trigger that locks on: the glue reads only "
          "TriggersSwapped() of the map and builds the block with EffectBlock (R2 at 10, L2 at 21)",
          ds_sdl.count("r3hd_padmap::") == 1 and "EffectBlock(t, r3hd_padmap::Get().TriggersSwapped(), block)" in ds_sdl
          and ds_sdl == (TOOLS / "r3hd_ds_sdl.h").read_text(encoding="utf-8"))
    chain = (TOOLS / "build_milestone8.bat").read_text(encoding="utf-8")
    check("runtime: the patch replays last in the build chain and the regression and host test run in the build",
          chain.index("r3hd_dualsense_patch.py") < chain.index("r3hd_padmap_patch.py")
          < chain.index("r3hd_padmap_regression.py")
          and "r3hd_padmap_test.cpp" in (TOOLS / "build_r3hd_release_tests.bat").read_text(encoding="utf-8"))
    dll = BUILD / "rexruntime.dll"
    if dll.is_file() and dll.stat().st_mtime >= (TOOLS / "r3hd_padmap_patch.py").stat().st_mtime:
        data = dll.read_bytes()
        check("runtime: the built runtime carries the map's log lines", b"R3HD padmap state=" in data
              and b"R3HD padmap_test buttons=" in data)
    else:
        skip("built runtime strings", "no runtime built after the patch")


# --- the launcher -----------------------------------------------------------------------------------------------------

def hid(kind, face=0x08, b1=0, b2=0, lx=0x80, ly=0x80, rx=0x80, ry=0x80, l2=0, r2=0):
    """D-116: one HID input report as Raw Input hands it over (report id first), hex. face = hat (low nibble, 8 = none)
    and Square 0x10 / Cross 0x20 / Circle 0x40 / Triangle 0x80; b1 = L1 01 R1 02 Create 10 Options 20 L3 40 R3 80;
    b2 = PS 01 touchpad 02."""
    if kind == "ds_usb":
        r = [0x01, lx, ly, rx, ry, l2, r2, 0, face, b1, b2] + [0] * 53
    elif kind == "ds_bt":
        r = [0x31, 0, lx, ly, rx, ry, l2, r2, 0, face, b1, b2] + [0] * 66
    elif kind == "ds4_usb":
        r = [0x01, lx, ly, rx, ry, face, b1, b2, l2, r2] + [0] * 54
    elif kind in ("ds_simple10", "ds_simple78"):
        # SDL PS5SimpleStatePacket_t, including the 78-byte Windows-padded form.
        r = [0x01, lx, ly, rx, ry, face, b1, b2, l2, r2]
        if kind == "ds_simple78":
            r += [0] * 68
    elif kind == "ds4_bt":
        r = [0x11, 0xC0, 0, lx, ly, rx, ry, face, b1, b2, l2, r2] + [0] * 66
    else:
        raise ValueError(kind)
    return "".join(f"{b:02X}" for b in r)


def launcher_checks(keep):
    import m30_launcher_regression as m30
    if not m30.LAUNCHER.is_file():
        check("launcher built (tools\\launcher\\build_launcher.bat)", False)
        return
    saved = {k: os.environ.get(k) for k in engine.HOOKS}
    with tempfile.TemporaryDirectory(prefix="r3hd_padmap_ui_") as tmp:
        t = Path(tmp)
        sys32 = t / "sys32"
        sys32.mkdir()
        for n in engine.VC_RUNTIME:
            (sys32 / n).write_bytes(b"x")
        os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0", R3HD_INSTALL_FAKE_LAUNCHER="0")
        try:
            home = m30.make_home(t, "home")

            def pad(dump, i):
                return dump.get(f"pad_map.{i}")

            def cap(dump):
                return dump.get("pad_capture", "").split(" ")[0]

            def run(name, lines, need):
                code, d, log, out = m30.ui(home, t, name, "\n".join(lines + ["click close", ""]))
                if keep:
                    shutil.copytree(out, Path(keep) / f"ui_{name}", dirs_exist_ok=True)
                ok = code == 0 and all(k in d for k in need)
                check(f"UI run {name} completed", ok, log[-600:])
                return d if ok else None
            idle = "padin 1 - 0 0 0 0 0 0"
            # B8: exercise the production parser -> baseline/edge -> kind -> swap path.
            # A single private-desktop run, no physical input or output. Native decoder
            # fixtures independently cover the same formats in r3hd_pad_capture_test.cpp.
            lines, expected = ["page pad", "padsim dualsense"], {}
            buttons = [("a", {"face": 0x28}), ("b", {"face": 0x48}), ("x", {"face": 0x18}),
                       ("y", {"face": 0x88}), ("left_shoulder", {"b1": 1}), ("right_shoulder", {"b1": 2}),
                       ("back", {"b1": 0x10}), ("start", {"b1": 0x20}), ("lstick_press", {"b1": 0x40}),
                       ("rstick_press", {"b1": 0x80}), ("dpad_up", {"face": 0}), ("dpad_down", {"face": 4}),
                       ("dpad_left", {"face": 6}), ("dpad_right", {"face": 2})]
            variants = ("ds_simple10", "ds_simple78", "ds_usb", "ds_bt", "ds4_usb", "ds4_bt")
            for variant in variants:
                model = "ds4" if variant.startswith("ds4") else "dualsense"
                def reading(**kw):
                    return f"hid 99 {model} {hid(variant, **kw)}"
                for physical, kw in buttons + [("left_trigger", {"l2": 180}), ("right_trigger", {"r2": 180})]:
                    want = "right_trigger" if physical == "left_trigger" else "left_trigger" if physical == "right_trigger" else "a"
                    name = variant + "_" + physical
                    lines += ["click restorepad", f"pad {want}", reading(), reading(**kw), f"dump {name}"]
                    expected[name] = (want, physical)
                # Already-held inputs cannot be assigned; repeat does nothing, release/repress works.
                for tag, want, kw in [("held_button", "a", {"face": 0x88}),
                                      ("held_trigger", "left_trigger", {"r2": 180})]:
                    name = variant + "_" + tag
                    lines += ["click restorepad", f"pad {want}", reading(**kw), reading(**kw), f"dump {name}",
                              reading(), reading(**kw), f"dump {name}_edge"]
                    expected[name] = (want, None)
                    expected[name + "_edge"] = (want, "y" if tag == "held_button" else "right_trigger")
                name = variant + "_wrong_kind"
                lines += ["click restorepad", "pad a", reading(), reading(l2=180), f"dump {name}"]
                expected[name] = ("a", None)
                # Gradual normal deflection, both sticks, with several intermediate reports.
                for axis, want, physical in [("rx", "left_stick", "right_stick"), ("lx", "right_stick", "left_stick")]:
                    name = variant + "_" + axis
                    lines += ["click restorepad", f"pad {want}", reading()]
                    lines += [reading(**{axis: value}) for value in (135, 145, 160, 175, 196)]
                    lines += [f"dump {name}"]
                    expected[name] = (want, physical)
                # Resting drift/held stick must first center; a held high baseline is never a choice.
                name = variant + "_drift"
                lines += ["click restorepad", "pad left_stick", reading(rx=230), reading(rx=240), f"dump {name}",
                          reading(rx=128), reading(rx=140), reading(rx=160), reading(rx=196), f"dump {name}_edge"]
                expected[name] = ("left_stick", None)
                expected[name + "_edge"] = ("left_stick", "right_stick")
            # Xbox-compatible samples share the same gradual-stick edge logic.
            lines += ["click restorepad", "padsim xbox", "pad left_stick", idle]
            lines += [f"padin 1 - 0 0 0 0 {v} 0" for v in (3000, 9000, 12000, 15000, 18000)]
            lines += ["dump xbox_ramp", "click restorepad", "click save"]
            expected["xbox_ramp"] = ("left_stick", "right_stick")
            d = run("b8_formats", lines, expected)
            if not d:
                return
            for name, (want, physical) in expected.items():
                check(f"B8 capture {name}",
                      (cap(d[name]) == want and pad(d[name], want) == want) if physical is None else
                      (cap(d[name]) == "" and pad(d[name], want) == physical), d[name].get("status", ""))
            # E-277: these existing inputs were hidden by an incomplete inventory. Exercise the real UI path,
            # including swaps and persistence, with simulated readings only; never a physical controller or save.
            d = run("bumpers", [
                "page keys", "dump modern", "layout original_pc", "dump original", "layout modern",
                "page pad", "padsim xbox", "pad left_shoulder", idle,
                "padin 1 right_shoulder 0 0 0 0 0 0", "dump swap",
                "pad right_shoulder", idle, "padin 1 - 200 0 0 0 0 0", "dump analog",
                "padin 1 y 0 0 0 0 0 0", "dump remap", "click save", "reload", "page pad", "dump reload",
                "page keys", "dump coexist", "page pad", "click restorepad",
                "padsim dualsense", "pad left_shoulder", f"hid 7 dualsense {hid('ds_usb')}",
                f"hid 7 dualsense {hid('ds_usb', b1=0x02)}", "dump sony",
                "pad right_shoulder", f"hid 7 dualsense {hid('ds_usb')}",
                f"hid 7 dualsense {hid('ds_usb', b1=0x01)}", "dump l1",
                "click restorepad", "click save", "dump restored"],
                ("modern", "original", "swap", "analog", "remap", "reload", "coexist", "sony", "l1", "restored"))
            if not d:
                return
            check("UI keyboard: Show Health Bar and Grimace visible with Modern 1 / 3 and Original PC V",
                  all(d[n][f"key.{i}"].startswith(f"{key if n == 'modern' else 'V'}, caption=")
                      and f"visible=1 action={text}" in d[n][f"key.{i}"]
                      for n in ("modern", "original") for i, key, text in (
                          ("left_shoulder", "1", "Show Health Bar"),
                          ("right_shoulder", "3", "Grimace"))))
            check("UI capture: LB / RB actions swap like other buttons; a trigger cannot replace Grimace",
                  pad(d["swap"], "left_shoulder") == "right_shoulder"
                  and pad(d["swap"], "right_shoulder") == "left_shoulder"
                  and cap(d["analog"]) == "right_shoulder"
                  and pad(d["analog"], "right_shoulder") == "left_shoulder"
                  and pad(d["remap"], "right_shoulder") == "y" and pad(d["remap"], "y") == "left_shoulder")
            check("UI persistence: remapped health bar and Grimace survive Save / reload; keys remain 1 / 3",
                  pad(d["reload"], "left_shoulder") == "right_shoulder"
                  and pad(d["reload"], "right_shoulder") == "y"
                  and "caption=RB / R1" in d["reload"]["pad.left_shoulder"]
                  and "caption=Y / Triangle" in d["reload"]["pad.right_shoulder"]
                  and d["coexist"]["key.left_shoulder"].startswith("1, caption=")
                  and d["coexist"]["key.right_shoulder"].startswith("3, caption="))
            check("UI capture: USB L1 / R1 use the same button-capture and swap path",
                  pad(d["sony"], "left_shoulder") == "right_shoulder"
                  and "caption=RB / R1" in d["sony"]["pad.left_shoulder"]
                  and pad(d["l1"], "right_shoulder") == "left_shoulder" and cap(d["l1"]) == "")
            check("UI restore: both bumper defaults return; saving removes the controller map",
                  all(pad(d["restored"], i) == i for i in ("left_shoulder", "right_shoulder"))
                  and "controller" not in m30.settings(home))
            d = run("pada", [
                "workarea 0 0 1920 1032", "page pad", "dump p0", "shot controls_pad_96",
                "pad a", "dump nopad",                                         # no controller: no capture
                "padsim xbox", "pad a", "dump wait",                           # Jump waits for a press
                "padin 1 a 0 0 0 0 0 0", "padin 1 a 0 0 0 0 0 0", "dump held",  # A held when it began: no choice
                "padin 1 - 0 0 0 0 0 0", "padin 1 y 0 0 0 0 0 0", "dump swap1",  # Y: Y's input takes A
                "pad x", idle, "padin 1 b 0 0 0 0 0 0", "dump swap2",        # Attack on B: Back / cancel on X
                "pad start", idle, "padin 1 start 0 0 0 0 0 0", "dump same",  # already there
                "pad right_trigger", idle, "padin 1 x 0 0 0 0 0 0", "dump kind1",  # a button for a trigger: refused
                "padin 1 - 0 0 0 0 32767 0", "dump kind2",                    # a stick for a trigger: refused
                "padin 1 - 100 0 0 0 0 0", "dump light",                      # LT under half way: not yet
                "padin 1 - 200 0 0 0 0 0", "dump trig",                       # LT: the triggers exchange
                "pad a", idle, "padin 1 - 0 0 32767 0 0 0", "dump stickbtn",  # a stick moved for a button: ignored
                "padin 1 - 0 0 0 0 0 0 guide", "dump guide",                  # Guide: not used by the game
                "press 01", "dump esc",                                       # Esc cancels
                "pad b", idle, "padtick 10500", "dump timeout",               # ten seconds without a press
                "pad b", "deactivate", "dump focus",                          # the window loses focus
                "pad b", "padsim none", "padtick 300", "dump disc",           # the controller goes away
                "padsim dualsense", "pad left_stick", f"hid 7 dualsense {hid('ds_usb')}",
                f"hid 7 dualsense {hid('ds_usb', rx=0xFF)}", "dump sticks",   # DualSense USB: right stick for Move
                "pad dpad_up", f"hid 7 dualsense {hid('ds_usb')}", f"hid 7 dualsense {hid('ds_usb', face=0x02)}",
                "dump dpad",                                                  # D-pad right (hat E) for Menu up
                "pad b", f"hid 7 dualsense {hid('ds_usb')}", f"hid 7 dualsense {hid('ds_usb', b2=0x01)}",
                "dump ps", "press 01",                                        # PS: not used
                "padsim ds4", "pad a", f"hid 8 ds4 {hid('ds4_bt')}", f"hid 8 ds4 {hid('ds4_bt', face=0x88)}",
                "dump ds4bt",                                                 # DualShock 4 BT: Triangle = Y
                "pad x", f"hid 8 ds4 {hid('ds4_usb')}", f"hid 8 ds4 {hid('ds4_usb', face=0x48)}",
                "dump ds4usb",                                                # DualShock 4 USB: Circle = B
                "padsim dualsense", "pad start", f"hid 9 dualsense {hid('ds_bt')}",
                f"hid 9 dualsense {hid('ds_bt', b1=0x20)}", "dump dsbt",     # DualSense BT: Options = Start
                "page keys", "key x 0", "press 21", "dump key",               # a keyboard change beside it
                "click save", "dump saved"],
                ("p0", "nopad", "wait", "held", "swap1", "swap2", "same", "kind1", "kind2", "light", "trig", "stickbtn",
                 "guide", "esc", "timeout", "focus", "disc", "sticks", "dpad", "ps", "ds4bt", "ds4usb", "dsbt", "key",
                 "saved"))
            if not d:
                return
            p0 = d["p0"]
            listed = ["left_stick", "right_stick", "a", "x", "y", "b", "right_trigger", "left_trigger",
                      "left_shoulder", "right_shoulder", "start", "dpad_up",
                      "dpad_down"]
            check("UI: the Controller tab lists the thirteen confirmed controls with their default inputs; nothing else",
                  p0["pad_rows_shown"] == "13" and p0["tab"] == "controller" and p0["pad_state"] == "default"
                  and all(f"pad.{i}" in p0 and pad(p0, i) == i for i in listed)
                  and "caption=A / Cross visible=1 action=Jump" in p0["pad.a"]
                  and "caption=RT / R2 visible=1 action=Lock on" in p0["pad.right_trigger"]
                  and "caption=Left stick visible=1 action=Move" in p0["pad.left_stick"]
                  and p0["pad_status"].startswith("No controller found"))
            check("UI capture: without a controller nothing waits and the person is told to connect one",
                  cap(d["nopad"]) == "" and "No controller found. Connect a controller" in d["nopad"]["status"])
            check("UI capture: an action waits for a press of the connected controller (caption and status say so)",
                  cap(d["wait"]) == "a" and "caption=Press a button..." in d["wait"]["pad.a"]
                  and "Press the controller button to use for Jump" in d["wait"]["status"]
                  and d["wait"]["pad_status"] == "Connected: Xbox-compatible controller")
            check("UI capture: a button already held when the capture began is not taken as the choice",
                  cap(d["held"]) == "a" and pad(d["held"], "a") == "a")
            check("UI capture: Jump and the newly listed Look Mode swap and name both actions",
                  pad(d["swap1"], "a") == "y" and pad(d["swap1"], "y") == "a" and cap(d["swap1"]) == ""
                  and "caption=Y / Triangle" in d["swap1"]["pad.a"] and d["swap1"]["dirty"] == "1"
                  and "Y / Triangle assigned to Jump. Look Mode (hold) moved to A / Cross." in d["swap1"]["status"])
            check("UI capture: a swap between two listed actions names both",
                  pad(d["swap2"], "x") == "b" and pad(d["swap2"], "b") == "x" and "caption=X / Square" in d["swap2"]["pad.b"]
                  and "B / Circle assigned to Attack. Roll / Back moved to X / Square." in d["swap2"]["status"])
            check("UI capture: the button an action already has changes nothing",
                  "is already assigned to Pause" in d["same"]["status"] and pad(d["same"], "start") == "start")
            check("UI capture: a trigger action refuses a button and a stick and keeps waiting",
                  cap(d["kind1"]) == "right_trigger" and "Lock on needs a trigger" in d["kind1"]["status"]
                  and cap(d["kind2"]) == "right_trigger" and pad(d["kind2"], "right_trigger") == "right_trigger")
            check("UI capture: a trigger counts from half way (100 / 255 is not a choice)",
                  cap(d["light"]) == "right_trigger" and pad(d["light"], "right_trigger") == "right_trigger")
            check("UI capture: pulling the other trigger exchanges the triggers (Lock on on LT, Photo mode on RT)",
                  pad(d["trig"], "right_trigger") == "left_trigger" and pad(d["trig"], "left_trigger") == "right_trigger"
                  and "LT / L2 assigned to Lock on. Photo mode moved to RT / R2." in d["trig"]["status"]
                  and "caption=RT / R2" in d["trig"]["pad.left_trigger"])
            check("UI capture: a stick moved while a button is wanted is ignored; Guide is refused; Esc cancels",
                  cap(d["stickbtn"]) == "a" and pad(d["stickbtn"], "a") == "y"
                  and cap(d["guide"]) == "a" and "does not use that button" in d["guide"]["status"]
                  and cap(d["esc"]) == "" and d["esc"]["status"] == "Controller not changed." and pad(d["esc"], "a") == "y")
            check("UI capture: ten seconds without a press, focus loss and a disconnect each end the capture unchanged",
                  cap(d["timeout"]) == "" and "No controller button was pressed. Nothing changed." in d["timeout"]["status"]
                  and cap(d["focus"]) == "" and "the window lost focus" in d["focus"]["status"]
                  and cap(d["disc"]) == "" and "The controller was disconnected. Nothing changed." in d["disc"]["status"]
                  and all(pad(d[k], "b") == "x" for k in ("timeout", "focus", "disc")))
            check("UI capture: a DualSense's HID report (USB): the right stick for Move exchanges the sticks; the D-pad's "
                  "hat gives D-pad right; the PS button is refused",
                  pad(d["sticks"], "left_stick") == "right_stick" and pad(d["sticks"], "right_stick") == "left_stick"
                  and d["sticks"]["pad_status"] == "Connected: DualSense"
                  and pad(d["dpad"], "dpad_up") == "dpad_right" and pad(d["dpad"], "dpad_right") == "dpad_up"
                  and "does not use that button" in d["ps"]["status"])
            check("UI capture: DualShock 4 (Bluetooth, USB) and DualSense (Bluetooth) reports name the same positions "
                  "(Triangle = Y, Circle = B, Options = Start)",
                  "Y / Triangle is already assigned to Jump" in d["ds4bt"]["status"]
                  and "B / Circle is already assigned to Attack" in d["ds4usb"]["status"]
                  and "Start / Options is already assigned to Pause" in d["dsbt"]["status"])
            s1 = m30.settings(home)
            check("UI: Save stores the controller map (buttons and analog exchanges, changed inputs only) beside the "
                  "keyboard change, which is the keyboard's own",
                  s1.get("controller") == {"buttons": {"a": "y", "y": "a", "x": "b", "b": "x", "dpad_up": "dpad_right",
                                                       "dpad_right": "dpad_up"},
                                           "analog": {"left_trigger": "right_trigger", "right_trigger": "left_trigger",
                                                      "left_stick": "right_stick", "right_stick": "left_stick"}}
                  and s1["schema"] == 4
                  and s1.get("keyboard") == {"layout": "modern", "keys": {"x": ["F"], "lstick_press": ["E"]}}, s1)
            d = run("padb", ["page pad", "dump reloaded", "click restorepad", "dump restored", "click save",
                             "dump saved", "click restorepad", "dump again", "page settings", "profile hdplus",
                             "click save", "dump hdplus"],
                    ("reloaded", "restored", "saved", "again", "hdplus"))
            if not d:
                return
            check("UI: the saved map survives closing and opening Settings (the Controller tab shows it)",
                  pad(d["reloaded"], "a") == "y" and pad(d["reloaded"], "right_trigger") == "left_trigger"
                  and "caption=Right stick" in d["reloaded"]["pad.left_stick"] and d["reloaded"]["pad_state"] == "saved")
            s2 = m30.settings(home)
            check("UI: Restore gives every default (buttons, triggers, sticks); saved, the controller section is gone "
                  "and the keys stay", all(pad(d["restored"], b) == b for b in ("a", "b", "x", "y", "left_trigger", "left_stick"))
                  and "controller" not in s2 and s2.get("keyboard") == s1["keyboard"]
                  and "already uses its default buttons" in d["again"]["status"], s2)
            d = run("padc", ["page pad", "padsim xbox", "pad start", idle, "padin 1 b 0 0 0 0 0 0", "click save",
                             "page settings", "profile custom", "click save", "dump custom"], ("custom",))
            s3 = m30.settings(home)
            check("UI: a preset change keeps the controller map",
                  d and s3.get("controller") == {"buttons": {"b": "start", "start": "b"}}, s3)
            bad = dict(s3, schema=4, controller={"buttons": {"a": "b"}})
            (home / "settings.json").write_text(json.dumps(bad), encoding="utf-8")
            d = run("padd", ["page pad", "dump damaged", "click save", "dump replaced"], ("damaged", "replaced"))
            s4 = m30.settings(home)
            check("UI: a damaged saved map is reported, shown as the defaults, and Save replaces it after a copy",
                  d and "Saved controller buttons could not be used" in d["damaged"]["banner"] and d["damaged"]["dirty"] == "1"
                  and pad(d["damaged"], "a") == "a" and "controller" not in s4 and s4.get("keyboard") == s1["keyboard"]
                  and list(home.glob("settings.json.invalid-*")), (d or {}).get("damaged", {}).get("banner"))
            # Layout: 1080p at 100 / 125 / 150 % and 720p, both tabs, English and Turkish; a short window; Tab navigation.
            lines = ["page pad", "padsim xbox", "pad a", idle, "padin 1 b 0 0 0 0 0 0"]
            names = []
            for lang in ("en", "tr"):
                lines.append(f"language {lang}")
                for dpi, wa in ((96, "1920 1032"), (120, "1920 1032"), (144, "1920 1032"), (96, "1280 680")):
                    for tab in ("keys", "pad"):
                        n = f"{lang}{dpi}_{wa.split()[0]}_{tab}"
                        lines += [f"dpi {dpi}", f"workarea 0 0 {wa}", f"page {tab}", f"dump {n}"]
                        names.append(n)
                lines += ["dpi 96", "workarea 0 0 1920 1032", "page pad", f"shot controls_pad_{lang}",
                          "page keys", f"shot controls_keys_{lang}"]
            lines += ["language en", "dpi 144", "workarea 0 0 1366 728", "page keys", "dump small", "shot controls_small",
                      "focus key:rstick_down", "dump smallfocus", "dpi 96", "workarea 0 0 1920 1032", "page pad",
                      "resize 380", "dump short", "focus pad:dpad_down", "dump shortfocus", "shot controls_short",
                      "resize 1200", "dump tall"]
            d = run("pade", lines, tuple(names) + ("small", "smallfocus", "short", "shortfocus", "tall"))
            if not d:
                return
            check("UI: Turkish captions; an unsaved swap survives the language change",
                  "caption=B / Daire" in d["tr96_1920_pad"]["pad.a"] and "caption=A / Çarpı" in d["tr96_1920_pad"]["pad.b"]
                  and d["tr96_1920_pad"]["dirty"] == "1" and "action=Zıpla" in d["tr96_1920_pad"]["pad.a"])
            texts = {
                "en": ("Show Health Bar", "Grimace", "Look Mode (hold)", "Roll / Back"),
                "tr": ("Can Barını Göster", "Dil Çıkar", "Bakış Modu (basılı tut)", "Yuvarlan / Geri"),
            }
            check("UI text: both tabs show the final English and Turkish labels at every size",
                  all(f"visible=1 action={texts[n[:2]][j]}" in d[n][f"{'key' if n.endswith('keys') else 'pad'}.{i}"]
                      for n in names for j, i in enumerate(("left_shoulder", "right_shoulder", "y", "b"))))
            fits = [n for n in names if "scroll=0" in d[n]["window"]]
            check("UI layout: both tabs, English and Turkish, 1080p at 100 / 125 / 150 % and 720p: no overlap, no "
                  "text cut, buttons in view; the expanded Keyboard inventory may scroll at smaller sizes",
                  all(n.endswith('keys') or n in fits for n in names)
                  and all(n in fits for n in names if '96_1920' in n)
                  and all(m30.layout_ok(d[n]) and d[n]["text_clipped"] == "0"
                                        and d[n]["in_view"].startswith("save:1 play:1 close:1 restore:1") for n in names),
                  {n: (d[n]["window"][-8:], d[n]["controls"], d[n]["text_clipped"], d[n]["in_view"][:40]) for n in names
                   if n not in fits or d[n]["text_clipped"] != "0" or not m30.layout_ok(d[n])})
            check("UI layout: on 1366 x 768 at 150 % the Keyboard tab scrolls inside the page only: the button row stays "
                  "in view, nothing overlaps, and keyboard focus brings a row that was out of view into it",
                  "scroll=1" in d["small"]["window"] and d["small"]["in_view"].startswith("save:1 play:1 close:1")
                  and m30.layout_ok(d["small"]) and int(d["smallfocus"]["in_view"].split("scroll_y=")[1]) > 0,
                  (d["small"]["in_view"], d["smallfocus"]["in_view"]))
            check("UI layout: a window made short scrolls its page, keeps the button row, follows focus; made tall again "
                  "it shows the whole page", "scroll=1" in d["short"]["window"]
                  and d["short"]["in_view"].startswith("save:1 play:1 close:1") and m30.layout_ok(d["short"])
                  and "scroll=1" in d["shortfocus"]["window"]
                  and int(d["shortfocus"]["in_view"].split("scroll_y=")[1]) > 0 and "scroll=0" in d["tall"]["window"],
                  (d["short"]["in_view"], d["shortfocus"]["in_view"], d["tall"]["window"]))
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
    pm = rs.load_padmap(km)
    tie_checks(km, pm)
    resolver_checks(km, pm)
    engine_checks()
    if a.skip_runtime_dry_run:
        skip("play.ps1 dry runs", "explicit --skip-runtime-dry-run; game may be running")
    else:
        play_checks(km, pm)
    runtime_checks()
    check("Settings Sony decoder: independent native report fixtures",
          subprocess.run([sys.executable, str(TOOLS / "r3hd_pad_capture_regression.py")], cwd=ROOT).returncode == 0)
    launcher_checks(a.keep)
    failed = sum(not ok for _, ok in checks)
    print(f"R3HD_PADMAP_REGRESSION {'PASS' if not failed else 'FAIL'} checks={len(checks)} failures={failed} "
          f"skipped={len(skipped)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
