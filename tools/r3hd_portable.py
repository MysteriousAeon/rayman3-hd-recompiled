#!/usr/bin/env python3
"""Portable first-run preparation; uses the installed application's existing home layout.

Packaged at app/tools/r3hd_portable.py. No registry, shortcut, network or migration.
The top-level command files call this before the unchanged native launcher.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import struct
import sys

# The pinned embedded Python deliberately omits the script directory from sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_installer as engine

# D-126: fixed paths, never a manifest-controlled exemption or a DLL search path.
# LX-4 (E-375): the Linux package is the same portable layout; its replaceable LGPL libraries are shared objects.
LINUX = os.name != "nt"
REPLACEABLE_LGPL = (frozenset(("bin/libffmpeg.so", "bin/libmspack.so")) if LINUX
                    else frozenset(("bin/ffmpeg.dll", "bin/mspack.dll")))


def check_lgpl_so(path, rel):
    if not path.is_file():
        raise engine.Refusal("PORTABLE_LGPL_MISSING", f"{rel}: restore the original or supply a compatible Linux x86-64 shared library")
    # Structural check only (ELF64, little-endian, ET_DYN, x86-64); symbols and ABI are judged by the loader/runtime.
    with path.open("rb") as f:
        head = f.read(20)
    if (len(head) != 20 or head[:4] != b"\x7fELF" or head[4] != 2 or head[5] != 1
            or struct.unpack_from("<H", head, 16)[0] != 3 or struct.unpack_from("<H", head, 18)[0] != 62):
        raise engine.Refusal("PORTABLE_LGPL_FORMAT", f"{rel}: expected a Linux x86-64 ELF shared library; restore the original or rebuild it")


def check_platform_linux(requires=None):
    machine = os.uname().machine.lower()
    if not sys.platform.startswith("linux") or machine not in ("x86_64", "amd64") or sys.maxsize <= 2 ** 32:
        raise engine.Refusal("UNSUPPORTED_OS", f"{sys.platform} {machine}: the Linux package needs Linux x86-64")
    if sys.version_info < (3, 10):
        raise engine.Refusal("UNSUPPORTED_OS", "Python 3.10 or newer is required")
    check_linux_baseline(requires or {}, linux_runtime_versions)


def _version(text):
    return tuple(int(x) for x in re.findall(r"\d+", text or "")) or (0,)


def linux_runtime_versions():
    """B7 (E-378): this system's glibc version and the newest GLIBCXX_ version its libstdc++.so.6 provides."""
    glibc = (os.confstr("CS_GNU_LIBC_VERSION") or "").split()[-1:] or [None]
    glibcxx = None
    try:
        import ctypes
        ctypes.CDLL("libstdc++.so.6")
        with open("/proc/self/maps", encoding="utf-8", errors="replace") as maps:
            path = next((line.split(None, 5)[5].strip() for line in maps
                         if len(line.split(None, 5)) == 6 and "libstdc++.so.6" in line), None)
        if path:
            with open(path, "rb") as f:
                found = set(re.findall(rb"GLIBCXX_(\d+\.\d+(?:\.\d+)?)\x00", f.read()))
            glibcxx = max((v.decode() for v in found), key=_version, default=None)
    except OSError:
        pass
    return {"glibc": glibc[0], "glibcxx": glibcxx}


def check_linux_baseline(requires, versions):
    """Refuse early, with the versions, when the system is older than the package's recorded floor (payload.json
    requires.glibc / requires.glibcxx) instead of letting the loader fail with "version GLIBC_x not found"."""
    need = {k: requires.get(k) for k in ("glibc", "glibcxx") if requires.get(k)}
    if not need:
        return
    have = versions()
    old = [f"{'glibc' if k == 'glibc' else 'libstdc++ (GLIBCXX)'} {v} or newer (this system: {have.get(k) or 'not found'})"
           for k, v in need.items() if not have.get(k) or _version(have[k]) < _version(v)]
    if old:
        raise engine.Refusal("UNSUPPORTED_OS", "This Linux Experimental build needs " + " and ".join(old) +
                             ". Use a current distribution (see app/README-LINUX.txt, REQUIREMENTS).")


def desktop_message(text, run=subprocess.run):
    """E-379: a message a person started from the application menu can see (no terminal): kdialog, zenity or
    notify-send when present; always printed too."""
    print(text, file=sys.stderr)
    for argv in (["kdialog", "--error", text], ["zenity", "--error", "--text", text],
                 ["notify-send", "Rayman 3 HD Recompiled", text]):
        if shutil.which(argv[0]):
            try:
                run(argv, timeout=600, check=False)
                return argv[0]
            except (OSError, subprocess.SubprocessError):
                pass
    return None


def ask_preset(log, ask=input):
    """E-377: the installer's preset page for a new Linux home (Windows shows it in setup, and the portable ZIP opens
    the Settings window). Same choices and names (registry preset_ui, "HD+ (Recommended)"); Enter keeps the
    installer's preselection, Vanilla. Custom starts on Vanilla, as the installer does; ./Settings.sh changes it."""
    ui = engine.presets.load_registry().get("preset_ui", {})
    keys = ("vanilla", "hdplus", "custom")
    log("How should the game look? You can change this at any time with ./Settings.sh.")
    for i, k in enumerate(keys, 1):
        log(f"  {i}  {ui.get(k, {}).get('name', k)} - {ui.get(k, {}).get('text', '')}")
    while True:
        answer = ask("Preset (1-3, Enter = 1): ").strip()
        if answer in ("", "1", "2", "3"):
            return keys[int(answer or "1") - 1]


def check_lgpl_dll(path, rel):
    if LINUX:
        return check_lgpl_so(path, rel)
    if not path.is_file():
        raise engine.Refusal("PORTABLE_LGPL_MISSING", f"{rel}: restore the original or supply a compatible Windows x64 DLL")
    # Structural check only; exports, ABI, decoder support and dependencies are judged by the loader/runtime.
    try:
        with path.open("rb") as f:
            head = f.read(64)
            if len(head) != 64 or head[:2] != b"MZ":
                raise ValueError()
            offset = struct.unpack_from("<I", head, 60)[0]
            if offset > path.stat().st_size - 26:
                raise ValueError()
            f.seek(offset)
            pe = f.read(26)
            if (pe[:4] != b"PE\0\0" or struct.unpack_from("<H", pe, 4)[0] != 0x8664
                    or not struct.unpack_from("<H", pe, 22)[0] & 0x2000
                    or struct.unpack_from("<H", pe, 24)[0] != 0x20B):
                raise ValueError()
    except (ValueError, struct.error):
        raise engine.Refusal("PORTABLE_LGPL_FORMAT", f"{rel}: expected a Windows x64 PE32+ DLL; restore the original or rebuild it") from None


def safe_path(rel):
    return isinstance(rel, str) and all(p and p not in (".", "..") and
        not any(c in p for c in ':\\') for p in rel.split("/"))


def check_files(home):
    package = engine.read_json(home / "portable.json")
    if package.get("schema") != 1 or package.get("data_model") != "beside-application":
        raise engine.Refusal("PORTABLE_DAMAGED", "Unsupported portable manifest; extract a fresh ZIP")
    for rel, info in package["files"].items():
        if not safe_path(rel):
            raise engine.Refusal("PORTABLE_DAMAGED", "Unsafe manifest path")
        p = home / rel
        if rel in REPLACEABLE_LGPL:
            check_lgpl_dll(p, rel)
            continue
        if not p.is_file() or p.stat().st_size != info["size"] or engine.sha256(p) != info["sha256"]:
            raise engine.Refusal("PORTABLE_DAMAGED", f"{rel}: extract a fresh ZIP; keep your user files")
    # Unlisted program files can change DLL/tool loading. Mutable user files are outside these directories.
    actual = {p.relative_to(home).as_posix() for folder in ("app", "bin")
              for p in (home / folder).rglob("*") if p.is_file()}
    expected = {p for p in package["files"] if p.startswith(("app/", "bin/"))}
    if actual - expected - {"bin/install.json"}:
        raise engine.Refusal("PORTABLE_DAMAGED", "Unlisted program files; extract into a new folder")
    return engine.load_payload(home, verify=False)


def launcher_progress():
    """--progress (RecompLauncher): the engine's progress as `progress <0-1> <text>` lines on stdout."""
    label = [""]

    def emit(line):
        kind, _, rest = line.partition(" ")
        if kind == "R3HD_STEP":
            label[0] = engine.LABELS.get(rest.split(" ", 1)[0], rest)
        elif kind == "R3HD_PROGRESS":
            print(f"progress {int(rest.split(' ', 1)[0]) / 1000:.3f} {label[0]}", flush=True)
    return engine.Progress(emit=emit)


def prepare(home, source=None, *, releases=None, ask=False, log=print, preset=None, update_in_place=False,
            progress=None):
    """update_in_place (--in-place-update): the program files of this folder were replaced by a newer or older
    release in place (RecompLauncher's update); after the same checks as every start, record that release instead of
    refusing. progress (--progress): an engine.Progress for the extraction."""
    home = home.resolve()
    # User-data junctions could silently share saves with another copy. Refuse rather than follow them.
    pending = [home / name for name in (*engine.USER_ITEMS, "data", "app", "bin")]
    while pending:
        path = pending.pop()
        if not path.exists() and not path.is_symlink():
            continue
        if getattr(path.lstat(), "st_file_attributes", 0) & 0x400 or path.is_symlink():
            raise engine.Refusal("PORTABLE_LINK", "Linked files/directories are unsupported; use an independent copy")
        if path.is_dir():
            pending.extend(path.iterdir())
    payload = check_files(home)
    if LINUX:
        check_platform_linux(payload.get("requires") if isinstance(payload, dict) else None)
    else:
        engine.check_platform(vc_dir=home / "bin")  # Validate the pinned application-local CRT.
        if sys.getwindowsversion().build < 18362:
            raise engine.Refusal("UNSUPPORTED_OS", "Portable UTF-8 paths require Windows 10 version 1903 or newer")
    engine.check_not_running()
    # Never fall back to an installed home or system user-data folder on access failure.
    with engine.Lock(home):
        engine.recover(home, log)
        previous = engine.read_state(home)
        if previous and (previous.get("distribution") != "portable" or
                         previous["payload_id"] != payload["payload_id"] and not update_in_place):
            raise engine.Refusal("PORTABLE_UPDATE_REQUIRED", "Extract a fresh ZIP into a new folder; copy user files explicitly")
        updated = bool(previous) and previous["payload_id"] != payload["payload_id"]
        if updated:
            log(f"program files replaced in place: {previous['version']} -> {payload['version']}")
        releases = releases if releases is not None else engine.load_releases()
        release = engine.required_release(payload, releases)
        if progress is not None:
            print("progress 0.000 Checking your game data", flush=True)
        # Hash all game files, including same-size corruption, before any launch.
        data = engine.data_state(home, release, full=True)
        if data["state"] != "ok" and source is None and ask:
            log("Game data is missing or damaged. Supply your legally obtained Xbox 360 Rayman 3 HD package")
            log("or its verified extracted content folder. Nothing is downloaded. Blank cancels.")
            answer = input("Package / content path: ").strip().strip('"')
            source = Path(answer) if answer else None
        if data["state"] != "ok" and source is None:
            raise engine.Refusal("PACKAGE_REQUIRED", f"Game data {data['state']}; run Play.cmd and supply your package")
        s = engine.settings_state(home)
        if s["state"] == "invalid":
            raise engine.Refusal("SETTINGS_INCOMPATIBLE", s.get("detail", "Keep settings.json and repair it explicitly"))
        if preset not in ("vanilla", "hdplus", "custom"):  # E-379: the Linux setup window passes its choice
            preset = ask_preset(log) if LINUX and ask and s["state"] == "missing" else "vanilla"
        settings = engine.presets.load_settings_file(home / "settings.json") if s["state"] == "ok" else \
            engine.settings_from_args(preset, "vanilla" if preset == "custom" else None, (), False, home, fresh=True)
        if previous and data["state"] == "ok" and s["state"] == "ok" and not updated:
            if LINUX:
                engine.write_play_icon(home)  # E-379: kept when present; made while the package is still there
            return {"home": str(home), "data": "verified", "version": payload["version"]}
        staging = home / f".staging-{os.getpid()}"
        staging.mkdir()
        try:
            items = []
            if data["state"] != "ok":
                src = engine.check_source(Path(source), releases)
                if src["release"] != release["id"]:
                    raise engine.Refusal("RELEASE_MISMATCH", "Package does not match this application")
                if progress is not None:
                    content = release["content"]
                    progress.plan(([("extract", content["bytes"], content["files"])] if src["kind"] == "package" else
                                   [("check", content["bytes"], content["files"]),
                                    ("copy", content["bytes"], content["files"])]) +
                                  [("verify", content["bytes"], content["files"])])
                record = engine.stage_data(src, staging / "data", release, releases, log, progress)
                items.append("data")
            else:
                record = engine.read_json(home / "data" / "intake.json")
            if s["state"] == "missing":
                engine.write_json(staging / "settings.json", settings)
                items.append("settings.json")
            state = engine.new_state(payload, record, settings, previous)
            state["distribution"] = "portable"
            engine.write_json(staging / engine.STATE, state)
            engine.write_json(staging / engine.HOME_MARK, engine.home_mark())
            items += [engine.STATE, engine.HOME_MARK]
            engine.commit(home, staging, items, log)
        except BaseException:
            # Retain an interrupted journal for the engine's recovery, never erase its evidence.
            if not (home / engine.TXN).exists():
                engine.rmtree(staging)
            raise
        for folder in ("profiles", "cache", "sessions", "save_history", "mods"):
            (home / folder).mkdir(exist_ok=True)
        if LINUX:  # E-379: the game's own icon from the person's package, as the Windows installer writes it
            engine.write_play_icon(home)
            # E-380: this start installed (setup's Finish page follows); a ready home returns above without the key
            return {"home": str(home), "data": "verified", "version": payload["version"], "installed": True}
        return {"home": str(home), "data": "verified", "version": payload["version"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("play", "settings", "prepare", "level-editor"))
    ap.add_argument("--source", "--game", dest="source", type=Path)
    ap.add_argument("--no-input", action="store_true")
    ap.add_argument("--console", action="store_true", help="Linux: the console questions, not the Settings window")
    # RecompLauncher (recomplauncher.json); without these options nothing changes.
    ap.add_argument("--progress", action="store_true", help="prepare: print 'progress <0-1> <text>' lines")
    ap.add_argument("--in-place-update", action="store_true",
                    help="prepare: accept program files replaced in this folder by another release (launcher update)")
    ap.add_argument("--wait", action="store_true", help="Windows play: return when the game has ended")
    a = ap.parse_args()
    home = Path(__file__).resolve().parents[2]
    try:
        # Explicit home is insufficient: play.ps1 gives individual environment paths higher precedence.
        for key in list(os.environ):
            if key.upper().startswith("R3HD_"):
                del os.environ[key]
        gui = None
        if LINUX and not a.console and not a.no_input:
            sys.path.insert(0, str(Path(__file__).resolve().parent / "linux"))
            import r3hd_settings_gui
            gui = r3hd_settings_gui if r3hd_settings_gui.gui_available() else None
        # E-379: a start from the application menu has no terminal. E-380: with a display, the first start is the
        # setup window (Windows setup's pages) from a terminal too; the console questions are the fallback.
        terminal = not LINUX or sys.stdin is not None and sys.stdin.isatty()
        action, window = a.action, False
        try:
            result = prepare(home, a.source, ask=not a.no_input and terminal and gui is None,
                             update_in_place=a.in_place_update and a.action == "prepare",
                             progress=launcher_progress() if a.progress and a.action == "prepare" else None)
        except engine.Refusal as e:
            if not (LINUX and e.code == "PACKAGE_REQUIRED" and a.action != "prepare" and not a.no_input):
                raise
            if gui is None:
                desktop_message("Rayman 3 HD Recompiled needs your game data. Run ./Play.sh in a terminal, or "
                                "install Python's tkinter (e.g. the 'tk' package) for the setup window.")
                raise
            done = gui.run_setup(home, prepare)
            if done is None:
                return 2
            (result, action), window = done, True
            result = dict(result or {}, installed=True)
        if LINUX and result.get("installed") and a.action != "prepare":
            # E-380: a start that installed ends on setup's Finish page; nothing starts unless the person chooses.
            if not window:  # the console questions installed (no window): the Finish page in the terminal
                sys.path.insert(0, str(Path(__file__).resolve().parent / "linux"))
                import r3hd_settings_gui as finish
                action = finish.finished_choice() if terminal and not a.no_input else None
            if action is None:
                print("R3HD_PORTABLE READY " + json.dumps(result, ensure_ascii=True))
                return 0
            a.action = action
        print("R3HD_PORTABLE READY " + json.dumps(result, ensure_ascii=True))
        print(f"LGPL replacement policy: {' and '.join(sorted(REPLACEABLE_LGPL))} may differ from the shipped hashes. "
              "Preparation checks file format only; loading and runtime use determine compatibility. "
              "If loading fails, check exports/dependencies or restore your saved originals.", flush=True)
        if LINUX and a.action == "level-editor":
            print("The level editor is part of the Windows edition only.", file=sys.stderr)
            return 2
        if LINUX and a.action != "prepare":
            # LX-4: the Linux launcher reads this home (bin, data/content, settings.json, mods, profiles); Settings is
            # the engine's console configuration until a Linux Settings window exists. Same engine, same files.
            tools = Path(__file__).resolve().parent
            if a.action == "play":
                args = [sys.executable, "-B", str(tools / "linux" / "r3hd_play.py"), "--home", str(home)]
            elif gui is not None:  # E-379: the Settings window; the console stays the fallback (--console)
                return gui.run_settings(home)
            else:
                args = [sys.executable, "-B", str(tools / "r3hd_installer.py"), "configure", "--home", str(home)]
            return subprocess.call(args, cwd=home)
        if a.action != "prepare":
            args = [str(home / "app" / "r3hd_launcher.exe")]
            if a.action == "play":
                args.append("--play")
                if a.wait:
                    args.append("--wait")
            elif a.action == "level-editor":  # G6-P31 (D-287): the same entry as the installed Start menu item
                args.append("--level-editor")
            return subprocess.call(args, cwd=home)
        if a.progress:
            print("progress 1.000 Ready to play", flush=True)
        return 0
    except (engine.Refusal, OSError, ValueError, EOFError) as e:
        print(f"Portable startup stopped: {e}\nUse a writable extracted folder. No installed-copy data was changed.", file=sys.stderr)
        if a.progress and isinstance(e, engine.Refusal) and e.code in engine.ADVICE:
            print(engine.ADVICE[e.code], file=sys.stderr)  # the launcher shows the last lines: the reason last
        return 2


if __name__ == "__main__":
    sys.exit(main())
