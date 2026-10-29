#!/usr/bin/env python3
"""Portable first-run preparation; uses the installed application's existing home layout.

Packaged at app/tools/r3hd_portable.py. No registry, shortcut, network or migration.
The top-level command files call this before the unchanged native launcher.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import struct
import sys

# The pinned embedded Python deliberately omits the script directory from sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_installer as engine

# D-126: fixed paths, never a manifest-controlled exemption or a DLL search path.
REPLACEABLE_LGPL = frozenset(("bin/ffmpeg.dll", "bin/mspack.dll"))


def check_lgpl_dll(path, rel):
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


def prepare(home, source=None, *, releases=None, ask=False, log=print):
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
    engine.check_platform(vc_dir=home / "bin")  # Validate the pinned application-local CRT.
    if sys.getwindowsversion().build < 18362:
        raise engine.Refusal("UNSUPPORTED_OS", "Portable UTF-8 paths require Windows 10 version 1903 or newer")
    engine.check_not_running()
    # Never fall back to an installed home or system user-data folder on access failure.
    with engine.Lock(home):
        engine.recover(home, log)
        previous = engine.read_state(home)
        if previous and (previous.get("distribution") != "portable" or
                         previous["payload_id"] != payload["payload_id"]):
            raise engine.Refusal("PORTABLE_UPDATE_REQUIRED", "Extract a fresh ZIP into a new folder; copy user files explicitly")
        releases = releases if releases is not None else engine.load_releases()
        release = engine.required_release(payload, releases)
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
        settings = engine.presets.load_settings_file(home / "settings.json") if s["state"] == "ok" else \
            engine.settings_from_args("vanilla", None, (), False, home, fresh=True)
        if previous and data["state"] == "ok" and s["state"] == "ok":
            return {"home": str(home), "data": "verified", "version": payload["version"]}
        staging = home / f".staging-{os.getpid()}"
        staging.mkdir()
        try:
            items = []
            if data["state"] != "ok":
                src = engine.check_source(Path(source), releases)
                if src["release"] != release["id"]:
                    raise engine.Refusal("RELEASE_MISMATCH", "Package does not match this application")
                record = engine.stage_data(src, staging / "data", release, releases, log)
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
        return {"home": str(home), "data": "verified", "version": payload["version"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("play", "settings", "prepare"))
    ap.add_argument("--source", type=Path)
    ap.add_argument("--no-input", action="store_true")
    a = ap.parse_args()
    home = Path(__file__).resolve().parents[2]
    try:
        # Explicit home is insufficient: play.ps1 gives individual environment paths higher precedence.
        for key in list(os.environ):
            if key.upper().startswith("R3HD_"):
                del os.environ[key]
        result = prepare(home, a.source, ask=not a.no_input)
        print("R3HD_PORTABLE READY " + json.dumps(result, ensure_ascii=True))
        print("LGPL replacement policy: bin/ffmpeg.dll and bin/mspack.dll may differ from the shipped hashes. "
              "Preparation checks file format only; loading and runtime use determine compatibility. "
              "If loading fails, check exports/dependencies or restore your saved originals.", flush=True)
        if a.action != "prepare":
            args = [str(home / "app" / "r3hd_launcher.exe")]
            if a.action == "play":
                args.append("--play")
            return subprocess.call(args, cwd=home)
        return 0
    except (engine.Refusal, OSError, ValueError, EOFError) as e:
        print(f"Portable startup stopped: {e}\nUse a writable extracted folder. No installed-copy data was changed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
