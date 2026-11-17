"""Prepare a fresh human-only test home, with an optional separate private profile copy.

The launcher references the owner's existing data read-only and uses private copied
development binaries. Existing destinations are refused. No package/release is made.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

import r3hd_settings as settings
import r3hd_button_prompts as prompts

ROOT = Path(__file__).resolve().parents[1]


def prepare(home, shoulder_source, profile_source=None):
    home = home.resolve()
    home.relative_to((ROOT / "private/manual_playtests").resolve())
    if home.exists():
        raise ValueError("test home already exists; preserve it and choose a new name")
    shoulder_source = shoulder_source.resolve()
    prompts.read_glyphs(shoulder_source)  # validate before creating anything
    profile_hashes = {}
    if profile_source:
        profile_source = profile_source.resolve()
        profile_source.relative_to((ROOT / "private/manual_playtests").resolve())
        total = 0
        for base, directories, files in os.walk(profile_source, followlinks=False):
            for name in (".", *directories, *files):
                path = Path(base) / name
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ValueError("profile contains a link/reparse point; no copy made")
            for name in files:
                path = Path(base) / name
                total += path.stat().st_size
                if total > 128 * 1024 * 1024:
                    raise ValueError("oversized private profile copy")
                profile_hashes[str(path.relative_to(profile_source))] = hashlib.sha256(path.read_bytes()).hexdigest()
        if not profile_hashes or total > 128 * 1024 * 1024:
            raise ValueError("missing or oversized private profile copy")
    payload = json.loads((ROOT / "config/release/payload.json").read_text())
    source = ROOT / payload["binaries"]["build_dir"]
    sources = {name: source / name for name in payload["binaries"]["files"]}
    # Private local testing only: portable preflight requires these dependencies
    # beside the copied game. Read installed system files; never install/change them.
    runtime_root = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32"
    sources.update({name: runtime_root / name for name in ("MSVCP140.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll")})
    for name, path in sources.items():
        if not path.is_file():
            raise ValueError(f"missing development binary: {name}")
    home.mkdir(parents=True)
    (home / "bin").mkdir()
    source_copy = home / "private_assets/ps3_glyphs"
    source_copy.mkdir(parents=True)
    for name in ("glyphs.json", *(n + ".png" for n in prompts.NATIVE_GLYPHS)):
        shutil.copyfile(shoulder_source if name == "glyphs.json" else shoulder_source.parent / name,
                        source_copy / name)
    if profile_source:
        shutil.copytree(profile_source, home / "profiles/button-prompts")
        if profile_hashes != {str(path.relative_to(profile_source)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in profile_source.rglob("*") if path.is_file()}:
            raise ValueError("source profile changed during copy")
        (home / "profile-copy-hashes.json").write_text(json.dumps(profile_hashes, indent=2) + "\n")
    identities = {}
    for name, path in sources.items():
        shutil.copyfile(path, home / "bin" / name)
        identities[name] = hashlib.sha256((home / "bin" / name).read_bytes()).hexdigest()
    data = settings.make_settings(settings.load_registry(), "vanilla")
    data["preferences"] = dict(data.get("preferences", {}), controller_prompts="auto", display="windowed",
                               render_scale="1", dualsense_light="off", dualsense_trigger="off",
                               dualsense_speaker="off")
    (home / "settings.json").write_text(json.dumps(data, indent=2) + "\n")
    (home / "installer.json").write_text(json.dumps({"schema": 1, "distribution": "portable",
        "version": payload["version"], "private_test": True, "files": {}, "data": {"release": "synthetic-home"}}) + "\n")
    game = ROOT / "private/extracted/5841123F"
    common = (f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{ROOT / "tools/play.ps1"}" '
              f'-UserHome "{home}" -BinDir "{home / "bin"}" -GameDir "{game}" '
              f'-SettingsFile "{home / "settings.json"}" -Profile button-prompts -Width 1280 -Height 720')
    for name, extra in (("Play", ""), ("Xbox", " -ButtonPrompts xbox"),
                        ("PlayStation", " -ButtonPrompts playstation")):
        (home / f"{name}.cmd").write_text("@echo off\n" +
            f'set "R3HD_PS3_PROMPT_SOURCE={source_copy / "glyphs.json"}"\n' + common + extra + "\npause\n")
    (home / "binary-identities.json").write_text(json.dumps(identities, indent=2) + "\n")
    (home / "README.txt").write_text(
        "HUMAN ONLY. No game has been started by preparation.\n"
        "Use PlayStation.cmd for the complete private native PS3 artwork.\n"
        "Connect one desired controller before starting. Restart after changing controllers.\n"
        "Original profiles/settings/test homes remain untouched. A requested profile is a separate copy.\n"
        "1. Load RAYDS (intro_15): inspect native tutorial face-button shapes, color, scale and baseline.\n"
        "2. Use the private source comparison PNG for all four faces; check a natural tutorial when shown.\n"
        "3. Pause: confirm accepted menu/shoulder presentation; check the Start return-to-game hint.\n"
        "4. Optional RAY1 (Knaar_69): confirm accepted gameplay shoulders and Xbox.cmd control.\n"
        "Report PASS/FAIL for those three contexts and your display resolution. No full playthrough.\n"
        "Play.cmd uses saved preferences; Xbox.cmd is an optional original-art control.\n"
        "This home contains proprietary PS3 glyph crops for PRIVATE testing only. Do not distribute it.\n")
    return {"home": str(home), "binaries": identities, "game_started": False}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--home", type=Path, required=True)
    ap.add_argument("--glyph-source", "--shoulder-source", dest="shoulder_source", type=Path, required=True)
    ap.add_argument("--copy-profile-from", type=Path)
    a = ap.parse_args()
    print(json.dumps(prepare(a.home, a.shoulder_source, a.copy_profile_from)))
