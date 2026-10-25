#!/usr/bin/env python3
"""M49 (D-088): regression of the keyboard Walk key. Starts no game and shows nothing on the person's desktop.

  * keymap / resolver: Walk is a visible, rebindable keyboard-only movement input; Modern holds it on Ctrl and Original
    PC on Shift (each layout's lock-on key stays); no layout conflicts; the launch passes --keybind_walk and
    --mnk_walk_magnitude; a map saved before Walk existed that uses the Walk default elsewhere stays valid (Walk yields
    its key) and an explicit conflict is still refused
  * driver (m32_keymap_test.exe, the real keyboard driver): Walk alone does nothing; Walk + a direction gives the
    magnitude; diagonals keep the same length; releasing Walk restores full deflection at once; jump, attack, lock-on
    and the camera stick are unchanged while Walk is held; opposite keys still cancel; no Walk key = the old behaviour
  * runtime: tools/m49_runtime_patch.py applied to the SDK sources once, and its line in the built runtime
  * play.ps1 -DryRun: the Walk arguments of the default layout and of a saved map
  * the launcher on a private desktop (--ui-test): the Walk row is shown, a captured key moves from lock-on with a
    swap, Save stores it
usage: m49_regression.py [--keep DIR]
"""
import argparse
import math
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
import m32_regression as m32  # noqa: E402
import r3hd_settings as rs  # noqa: E402

SDK = ROOT / "external" / "rexglue-sdk"
checks = []


def check(name, cond, detail=""):
    checks.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + ("" if cond or detail == "" else f"  [{str(detail)[:600]}]"))


def walk_value(magnitude, dx, dy):
    """The stick the driver must give for key directions dx, dy (each -1 / 0 / 1) with Walk held (tools/m49_walk.h)."""
    lx, ly = dx * 32767, dy * 32767
    if not lx and not ly:
        return 0, 0
    scale = magnitude * 32767 / math.hypot(lx, ly)
    rnd = lambda v: int(math.floor(abs(v) + 0.5)) * (1 if v >= 0 else -1)  # std::lround
    return rnd(lx * scale), rnd(ly * scale)


def resolver_checks(km):
    walk = next((i for i in km["inputs"] if i["id"] == "walk"), {})
    check("keymap: Walk is a visible keyboard-only movement input, not required, yielding",
          walk.get("group") == "movement" and not walk.get("hidden") and walk.get("keyboard_only")
          and walk.get("yields") and "walk" not in km["required"], walk)
    m, o = rs.layout_keys(km, "modern"), rs.layout_keys(km, "original_pc")
    check("keymap: Walk = Ctrl in Modern (Shift stays lock-on), Shift in Original PC (Ctrl stays lock-on)",
          m["walk"][0] == "Control" and m["right_trigger"][0] == "Shift" and o["walk"][0] == "Shift"
          and o["right_trigger"][0] == "Control", (m["walk"], o["walk"]))
    mag = km.get("walk_magnitude")
    check("keymap: the walk magnitude is a fraction from 0.1 to 1.0", isinstance(mag, float) and 0.1 <= mag <= 1.0, mag)
    for lay in km["layouts"]:
        kb = rs.resolve_keyboard(km, {"layout": lay})
        check(f"resolve: {lay} passes --keybind_walk and --mnk_walk_magnitude",
              f"--keybind_walk={','.join(kb['effective']['walk'])}" in kb["args"]
              and f"--mnk_walk_magnitude={mag}" in kb["args"], kb["args"][-4:])
    old = {"layout": "modern", "keys": {"x": ["Control"]}}  # a map saved before M49 with Ctrl on attack
    kb = rs.resolve_keyboard(km, old)
    check("migration: a saved map that uses Ctrl elsewhere stays valid; Walk gives its default key away",
          kb["state"] == "saved" and kb["effective"]["x"] == ["Control"] and kb["effective"]["walk"] == []
          and not kb["warnings"] and "--keybind_walk=None" in kb["args"], kb)
    check("migration: storing that map again keeps only the person's change",
          rs.keyboard_section(km, "modern", old["keys"]) == old)
    kb = rs.resolve_keyboard(km, {"layout": "original_pc", "keys": {"y": ["Shift"]}})
    check("migration: the same for Original PC and Shift", kb["state"] == "saved" and kb["effective"]["walk"] == [], kb)
    kb = rs.resolve_keyboard(km, {"layout": "modern", "keys": {"x": ["V"]}})
    check("migration: a saved map that does not touch the Walk key gets the Walk default",
          kb["state"] == "saved" and kb["effective"]["walk"] == ["Control"])
    try:
        rs.keyboard_section(km, "modern", {"walk": ["E"]})
        refused = None
    except rs.Refused as e:
        refused = e.code
    check("rebinding: Walk on a key another input uses is refused (KEY_CONFLICT)", refused == "KEY_CONFLICT", refused)
    check("rebinding: Walk on a free key, two keys, or none is stored",
          rs.keyboard_section(km, "modern", {"walk": ["Z", "V"]})["keys"] == {"walk": ["Z", "V"]}
          and rs.keyboard_section(km, "modern", {"walk": []})["keys"] == {"walk": []})


def driver_cases(km) -> str:
    mag = km["walk_magnitude"]
    lines = []
    for layout in km["layouts"]:
        kb = rs.resolve_keyboard(km, {"layout": layout})
        lines.append(f"# layout {layout}")
        for a in kb["args"]:
            name, value = a[2:].split("=", 1)
            lines.append(f"set {name} {value}")
        e = {i: v[0] for i, v in kb["effective"].items() if v}
        w, up, down, left, right = e["walk"], e["lstick_up"], e["lstick_down"], e["lstick_left"], e["lstick_right"]

        def expect(buttons, lt, rt, lx, ly, rx, ry, label):
            lines.append(f"expect {buttons:04X} {lt} {rt} {lx} {ly} {rx} {ry} {layout} {label}")
        lines.append(f"down {w}")
        expect(0, 0, 0, 0, 0, 0, 0, "walk alone does nothing")
        for key, dx, dy in ((up, 0, 1), (down, 0, -1), (left, -1, 0), (right, 1, 0)):
            lines.append(f"down {key}")
            expect(0, 0, 0, *walk_value(mag, dx, dy), 0, 0, f"walk + {key}")
            lines.append(f"up {key}")
        for a, b, dx, dy in ((up, right, 1, 1), (up, left, -1, 1), (down, right, 1, -1), (down, left, -1, -1)):
            lines += [f"down {a}", f"down {b}"]
            vx, vy = walk_value(mag, dx, dy)
            expect(0, 0, 0, vx, vy, 0, 0, f"walk + {a}+{b} diagonal")
            lines += [f"up {a}", f"up {b}"]
        lines += [f"down {up}", f"down {right}", f"up {w}"]
        expect(0, 0, 0, 32767, 32767, 0, 0, "walk released while moving: the old full deflection at once")
        lines += [f"down {w}"]
        expect(0, 0, 0, *walk_value(mag, 1, 1), 0, 0, "walk pressed again while moving")
        lines += [f"up {right}", f"down {left}"]
        expect(0, 0, 0, *walk_value(mag, -1, 1), 0, 0, "direction change while walking")
        lines += [f"down {right}"]
        expect(0, 0, 0, *walk_value(mag, 0, 1), 0, 0, "opposite keys cancel while walking")
        lines += ["release", f"down {w}", f"down {up}", f"down {e['a']}", f"down {e['x']}", f"down {e['right_trigger']}",
                  f"down {e['rstick_left']}"]
        expect(0x1000 | 0x4000, 0, 255, *walk_value(mag, 0, 1), -32767, 0,
               "jump, attack, lock-on and the camera unchanged while walking")
        lines.append("release")
        lines.append(f"set keybind_walk None")
        lines += [f"down {up}", f"down {right}"]
        expect(0, 0, 0, 32767, 32767, 0, 0, "no walk key: the old behaviour")
        lines.append("release")
    lines += ["# magnitude 1.0: straight full, diagonal of length one", "set keybind_walk Z", "set mnk_walk_magnitude 1.0",
              "set keybind_lstick_up W", "set keybind_lstick_right D", "set keybind_rstick_up None",
              "set keybind_rstick_right None",
              "down Z", "down W", "expect 0000 0 0 0 32767 0 0 magnitude 1 straight", "down D",
              "expect 0000 0 0 %d %d 0 0 magnitude 1 diagonal" % walk_value(1.0, 1, 1), "release"]
    return "\n".join(lines) + "\n"


def driver_checks(km, keep):
    exe = m32.BUILD / "m32_keymap_test.exe"
    if not exe.is_file():
        check("driver: m32_keymap_test.exe is built (tools\\build_milestone8.bat)", False, str(exe))
        return
    with tempfile.TemporaryDirectory(prefix="r3hd_m49_drv_") as tmp:
        cases = Path(tmp) / "cases.txt"
        cases.write_text(driver_cases(km), encoding="utf-8")
        if keep:
            shutil.copy(cases, Path(keep) / "walk_cases.txt")
        r = subprocess.run([str(exe), str(cases)], capture_output=True, text=True, timeout=120, cwd=str(m32.BUILD))
        n = sum(1 for line in cases.read_text().splitlines() if line.startswith("expect"))
        check(f"driver: Walk in the real keyboard driver ({n} states, both layouts)",
              r.returncode == 0 and "PASS" in r.stdout, (r.stdout + r.stderr)[-800:])


def runtime_checks():
    src = (SDK / "src/input/mnk/mnk_input_driver.cpp").read_text(encoding="utf-8", errors="replace")
    check("runtime: the M49 patch is in the driver once (Walk setting, magnitude, apply, line)",
          src.count("REXCVAR_DEFINE_STRING(keybind_walk,") == 1 and src.count("m49walk::Apply(") == 1
          and src.count("M49 keyboard walk=") == 1 and src.count("#include <rex/m49_walk.h>") == 1)
    hdr = SDK / "include/rex/m49_walk.h"
    check("runtime: tools/m49_walk.h is installed unchanged", hdr.is_file()
          and hdr.read_bytes() == (TOOLS / "m49_walk.h").read_bytes())
    apply_at = src.find("m49walk::Apply(")
    check("runtime: Walk changes only the left stick (applied before the right stick and the mouse are read)",
          0 < apply_at < src.find("keybind_rstick_left)))", apply_at + 1) if apply_at > 0 else False)
    dll = m32.BUILD / "rexruntime.dll"
    if dll.is_file():
        check("runtime: the built runtime carries the M49 line", b"M49 keyboard walk=" in dll.read_bytes())
    else:
        check("runtime: rexruntime.dll is built", False, str(dll))


def play_checks(km):
    if not (m32.BUILD / "r3hd.exe").is_file() or not (m32.GAME / "Default.xex").is_file():
        print("SKIP  play.ps1 dry runs (the built executable or the extracted data is missing)")
        return
    code, out, argv, kb = m32.dry_run()
    check("play: the default launch passes Walk on Ctrl and the magnitude", code == 0
          and "--keybind_walk=Control" in argv and f"--mnk_walk_magnitude={km['walk_magnitude']}" in argv, out[-400:])
    with tempfile.TemporaryDirectory(prefix="r3hd_m49_play_") as tmp:
        import json
        f = Path(tmp) / "settings.json"
        data = rs.make_settings(rs.load_registry(), "vanilla", keyboard={"layout": "modern", "keys": {"x": ["Control"]}})
        f.write_text(json.dumps(data), encoding="utf-8")
        code, out, argv, kb = m32.dry_run("-SettingsFile", str(f))
        check("play: an older saved map with Ctrl on attack launches without a warning; Walk has no key",
              code == 0 and "--keybind_x=Control" in argv and "--keybind_walk=None" in argv
              and "not used" not in out, out[-400:])


def launcher_checks(km, keep):
    if not m32.LAUNCHER.is_file():
        check("launcher built (tools\\launcher\\build_launcher.bat)", False)
        return
    import m30_launcher_regression as m30
    engine = m32.engine
    saved = {k: os.environ.get(k) for k in engine.HOOKS}
    with tempfile.TemporaryDirectory(prefix="r3hd_m49_ui_") as tmp:
        t = Path(tmp)
        sys32 = t / "sys32"
        sys32.mkdir()
        for n in engine.VC_RUNTIME:
            (sys32 / n).write_bytes(b"x")
        os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0", R3HD_INSTALL_FAKE_LAUNCHER="0")
        try:
            home = m30.make_home(t, "home")
            script = "\n".join(["page controls", "dump c0", "shot controls_walk", "key walk 0", "press 2A", "dump swap",
                                "click save", "dump saved", "click close", ""])
            code, d, log, out = m30.ui(home, t, "m49", script)
            if keep:
                shutil.copytree(out, Path(keep) / "ui_m49", dirs_exist_ok=True)
            ok = code == 0 and all(k in d for k in ("c0", "swap", "saved"))
            check("UI run m49 completed", ok, log[-600:])
            if not ok:
                return
            key = lambda dump, i: dump.get(f"key.{i}", "").split(" caption=")[0]
            check("UI: the Walk row is shown with its default key (Ctrl)",
                  "visible=1" in d["c0"].get("key.walk", "") and key(d["c0"], "walk") == "Control,", d["c0"].get("key.walk"))
            check("UI: Left Shift captured for Walk moves from lock-on, which gets Ctrl (a swap)",
                  key(d["swap"], "walk") == "Shift," and key(d["swap"], "right_trigger") == "Control,"
                  and "Keys swapped:" in d["swap"]["status"], (d["swap"].get("key.walk"), d["swap"].get("status")))
            s = m30.settings(home)
            check("UI: Save stores the swap", s.get("keyboard") == {"layout": "modern", "keys": {
                "walk": ["Shift"], "right_trigger": ["Control"]}}, s.get("keyboard"))
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep")
    ap.add_argument("--no-ui", action="store_true", help="skip the launcher (never beside a setup lifecycle test)")
    ap.add_argument("--skip-runtime-dry-run", action="store_true", help="skip real-build dry runs while a person plays")
    a = ap.parse_args()
    km = rs.load_keymap()
    resolver_checks(km)
    runtime_checks()
    driver_checks(km, a.keep)
    if a.skip_runtime_dry_run:
        print("SKIP play.ps1 dry runs (explicit --skip-runtime-dry-run; game may be running)")
    else:
        play_checks(km)
    if not a.no_ui:
        launcher_checks(km, a.keep)
    failed = [n for n, ok in checks if not ok]
    print(f"M49_REGRESSION {'PASS' if not failed else 'FAIL'} {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
