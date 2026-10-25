#!/usr/bin/env python3
"""M32 (D-069): the compiled setup's lifecycle for the keyboard map and the Settings shortcut. Silent, test mode only
(/VERYSILENT /SUPPRESSMSGBOXES /R3HDTEST=1: no uninstall entry, no launch, shortcuts only into the named test folders),
into synthetic folders under OUT; the package is only read.

    python tools/m32_setup_lifecycle.py SETUP.exe PACKAGE OUT [--previous OLD_SETUP.exe]

  1  fresh install with the Settings shortcut: both desktop shortcuts, the Settings one with the launcher's icon 2;
     the engine records both choices; no keyboard section (the default layout)
  2  keys saved as the launcher saves them (set-preset --keyboard ... --key ...); a visual preset change keeps them
  3  direct Play (r3hd_launcher.exe --play --dry-run --no-ui on the installed home): the saved keys reach play.ps1's
     arguments without the Settings window
  4  silent repair: keys, preferences and both shortcuts kept; a deleted Settings shortcut is not recreated by the
     next repair; settings.json deleted -> restored with the keys from the installation record
  5  cancel at 30 % of a repair (/CANCELAT): the installation unchanged, keys kept, healthy
  6  with --previous: an installation by the previous setup, keys written into its settings by this engine's resolver
     is not possible there, so: previous install, then this setup updates it silently: its settings file kept as it
     was (schema 2), the default keys apply; then keys saved, and a second update keeps them
  7  uninstall: only this installer's shortcuts go (a foreign .lnk stays); the user's settings.json is kept
Rows: OUT/lifecycle.json; prints M32_LIFECYCLE PASS n/n.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks = []


def check(name, cond, detail=""):
    checks.append({"name": name, "ok": bool(cond), "detail": "" if cond else str(detail)[:400]})
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  ({str(detail)[:300]})" if detail and not cond else ""), flush=True)


def setup(exe, out, tag, *args):
    log = out / f"{tag}.log"
    t = time.monotonic()
    r = subprocess.run([str(exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/R3HDTEST=1", f"/LOG={log}", *args],
                       timeout=900)
    return r.returncode, round(time.monotonic() - t, 1), log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""


def engine(home, *args):
    py = home / "app" / "python" / "python.exe"
    r = subprocess.run([str(py), "-B", str(home / "app" / "tools" / "r3hd_installer.py"), *args, "--home", str(home)],
                       capture_output=True, text=True, timeout=600)
    return r.returncode, r.stdout + r.stderr


def settings(home):
    return json.loads((home / "settings.json").read_text(encoding="utf-8"))


def lnk_icon(path: Path) -> str:
    ps = f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{path}'); $s.IconLocation + '|' + $s.Arguments + '|' + $s.TargetPath"
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


def tree_hash(root: Path, skip=("cache", "sessions")) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and rel.split("/")[0] not in skip and not rel.endswith(".log"):
            h.update(rel.encode() + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("setup", type=Path)
    ap.add_argument("package", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--previous", type=Path)
    a = ap.parse_args()
    out = a.out
    if out.exists():
        raise SystemExit(f"{out} exists; give a new folder")
    out.mkdir(parents=True)
    menu, desk = out / "menu", out / "desktop"
    menu.mkdir()
    desk.mkdir()
    home = out / "home"
    sc = [f"/STARTMENUDIR={menu}", f"/DESKTOPDIR={desk}"]
    play_lnk, set_lnk = desk / "Rayman 3 HD Recompiled.lnk", desk / "Rayman 3 HD Recompiled - Settings.lnk"

    # 1 fresh install with the Settings shortcut
    code, secs, log = setup(a.setup, out, "fresh", f"/DIR={home}", f"/PACKAGE={a.package}", "/PRESET=vanilla",
                            "/MERGETASKS=settingsicon", *sc)
    check("1 fresh install: setup exit 0", code == 0, log[-500:])
    if code != 0:
        print("M32_LIFECYCLE FAIL (no installation to continue with)")
        return 1
    check("1 fresh install: Play and Settings desktop shortcuts, Settings with the launcher's second icon",
          play_lnk.is_file() and set_lnk.is_file() and lnk_icon(set_lnk).split("|")[0].endswith("r3hd_launcher.exe,1")
          and "--play" in lnk_icon(play_lnk) and (menu / "Rayman 3 HD Recompiled - Settings.lnk").is_file(),
          [lnk_icon(play_lnk), lnk_icon(set_lnk)] if set_lnk.is_file() else list(desk.iterdir()))
    rc, txt = engine(home, "status", "--json")
    st = json.loads(txt[txt.index("{"):txt.rindex("}") + 1]) if "{" in txt else {}
    check("1 the engine recorded both shortcut choices", st.get("desktop_shortcut") == "1" and st.get("settings_shortcut") == "1", st)
    check("1 a new installation has no keyboard section (the default layout applies)", "keyboard" not in settings(home))
    # 2 keys saved as the launcher saves them
    rc, txt = engine(home, "set-preset", "--preset", "vanilla", "--keyboard", "original_pc", "--key", "x=V", "a=C,Return")
    rc2, _ = engine(home, "set-preset", "--preset", "hdplus")
    kb = settings(home).get("keyboard")
    check("2 keys saved through the engine; a visual preset change keeps them",
          rc == 0 and rc2 == 0 and kb == {"layout": "original_pc", "keys": {"x": ["V"]}} and settings(home)["preset"] == "hdplus", (txt[-300:], kb))
    rc, txt = engine(home, "set-preset", "--preset", "hdplus", "--keyboard", "original_pc", "--key", "x=C")  # C is Jump
    check("2 a conflicting map is refused and nothing changes", rc == 2 and "KEY_CONFLICT" in txt
          and settings(home).get("keyboard") == kb, txt[-300:])
    # 3 direct Play
    env = {k: v for k, v in os.environ.items() if k not in ("R3HD_GAME_DIR", "R3HD_BIN_DIR", "R3HD_PLAY_ROOT", "R3HD_HOME")}
    r = subprocess.run([str(home / "app" / "r3hd_launcher.exe"), "--play", "--dry-run", "--no-ui"], capture_output=True,
                       text=True, timeout=300, env=env)
    o = r.stdout + r.stderr
    check("3 direct Play (no Settings window) passes the saved keys", r.returncode == 0 and "--keybind_x=V" in o
          and "--keybind_a=C,Return" in o and "--keybind_right_trigger=Control" in o and "Original PC" in o, o[-800:])
    # 4 repair keeps keys and shortcuts; a deleted Settings shortcut stays deleted; a lost settings.json comes back
    before = settings(home)
    code, secs, log = setup(a.setup, out, "repair1", f"/DIR={home}", *sc)
    check("4 repair: exit 0; keys, preferences and both shortcuts kept", code == 0 and settings(home) == before
          and play_lnk.is_file() and set_lnk.is_file(), log[-400:])
    set_lnk.unlink()
    code, secs, log = setup(a.setup, out, "repair2", f"/DIR={home}", *sc)
    rc, txt = engine(home, "status", "--json")
    st = json.loads(txt[txt.index("{"):txt.rindex("}") + 1]) if "{" in txt else {}
    check("4 a deleted Settings shortcut is not recreated by a repair, and is now recorded as declined",
          code == 0 and not set_lnk.is_file() and play_lnk.is_file() and st.get("settings_shortcut") == "0", st)
    (home / "settings.json").unlink()
    code, secs, log = setup(a.setup, out, "repair3", f"/DIR={home}", *sc)
    check("4 a lost settings.json is restored with the keys from the installation record",
          code == 0 and settings(home).get("keyboard") == kb, settings(home) if (home / "settings.json").is_file() else "missing")
    # 5 cancel during a repair with a data check
    h0 = tree_hash(home)
    code, secs, log = setup(a.setup, out, "cancel", f"/DIR={home}", f"/PACKAGE={a.package}", "/VERIFYDATA=1", "/CANCELAT=50", *sc)
    rc, txt = engine(home, "verify")
    check("5 cancel early in a repair (the copy jumps from 12 % to 99 % in one line): setup reports it, the installation is unchanged, keys kept, healthy",
          code != 0 and "cancel requested" in log and tree_hash(home) == h0 and settings(home).get("keyboard") == kb
          and rc == 0, (code, txt[-200:]))
    # 6 update from the previous version
    if a.previous:
        home2 = out / "home_prev"
        sc2 = [f"/STARTMENUDIR={out / 'menu_prev'}", f"/DESKTOPDIR={out / 'desktop_prev'}"]  # its own shortcut folders
        (out / "menu_prev").mkdir()
        (out / "desktop_prev").mkdir()
        code, secs, log = setup(a.previous, out, "prev_install", f"/DIR={home2}", f"/PACKAGE={a.package}",
                                "/PRESET=vanilla", *sc2)
        old_settings = (home2 / "settings.json").read_bytes() if code == 0 else b""
        code2, secs, log2 = setup(a.setup, out, "update", f"/DIR={home2}", *sc2)
        check("6 the previous version installs, and this setup updates it keeping its settings file byte for byte",
              code == 0 and code2 == 0 and (home2 / "settings.json").read_bytes() == old_settings, (code, code2, log2[-300:]))
        r = subprocess.run([str(home2 / "app" / "r3hd_launcher.exe"), "--play", "--dry-run", "--no-ui"], capture_output=True,
                           text=True, timeout=300, env=env)
        check("6 after the update the default keys apply (Modern)", r.returncode == 0 and "--keybind_a=Space" in r.stdout
              and "Modern" in r.stdout, r.stdout[-500:])
        engine(home2, "set-preset", "--preset", "vanilla", "--keyboard", "modern", "--key", "x=F", "lstick_press=E")
        kb2 = settings(home2).get("keyboard")
        code3, secs, log3 = setup(a.setup, out, "update2", f"/DIR={home2}", *sc2)
        check("6 keys saved after the update survive the next update (reinstall)", code3 == 0 and kb2
              and settings(home2).get("keyboard") == kb2, (kb2, settings(home2).get("keyboard")))
        code4, _, _ = setup(home2 / "unins000.exe", out, "uninstall_prev")
        check("6 the updated installation uninstalls", code4 == 0)
    # 7 uninstall: own shortcuts only, user data kept
    foreign = desk / "Someone else.lnk"
    shutil.copy(play_lnk, foreign)
    code, secs, log = setup(home / "unins000.exe", out, "uninstall")
    time.sleep(2)
    check("7 uninstall removes this installer's shortcuts only and keeps the person's settings",
          code == 0 and not play_lnk.exists() and not set_lnk.exists() and foreign.is_file()
          and not (menu / "Rayman 3 HD Recompiled - Settings.lnk").exists() and (home / "settings.json").is_file()
          and settings(home).get("keyboard") == kb, list(desk.iterdir()))
    failed = sum(not c["ok"] for c in checks)
    (out / "lifecycle.json").write_text(json.dumps(checks, indent=1) + "\n", encoding="utf-8")
    print(f"M32_LIFECYCLE {'PASS' if not failed else 'FAIL'} {len(checks) - failed}/{len(checks)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
