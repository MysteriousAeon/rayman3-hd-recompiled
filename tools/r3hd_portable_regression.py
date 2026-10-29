#!/usr/bin/env python3
"""Portable isolated state, recovery, corruption and actual ZIP/extracted launcher checks. No game starts.

python tools/r3hd_portable_regression.py [--archive PRIVATE.zip] [--keep DIR]
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
from unittest.mock import patch

import r3hd_installer as e
import r3hd_portable as p
import r3hd_portable_zip as pack

checks = []


def check(name, value):
    checks.append(bool(value))
    print(("ok   " if value else "FAIL ") + name, flush=True)
    if not value:
        raise AssertionError(name)


def refused(fn, code):
    try:
        fn()
    except e.Refusal as exc:
        return exc.code == code
    return False


def tree_hash(root):
    return {f.relative_to(root).as_posix(): e.sha256(f) for f in root.rglob("*") if f.is_file()}


def synthetic(t):
    payload, source, releases = e.make_fixture(t)
    home = t / "Portable Türkçe folder"
    shutil.copytree(payload, home)
    for name in e.VC_RUNTIME:
        (home / "bin" / name).write_bytes(b"synthetic-runtime-presence")
    files = tree_hash(home)
    def seal():
        rows = {n: {"size": (home / n).stat().st_size, "sha256": e.sha256(home / n)} for n in files}
        e.write_json(home / "portable.json", {"schema": 1, "data_model": "beside-application", "files": rows})
    seal()
    prepare = lambda h=home, s=None: p.prepare(h, s, releases=releases, log=lambda *_: None)
    check("missing data refuses without creating installed state", refused(prepare, "PACKAGE_REQUIRED")
          and not (home / e.STATE).exists())
    prepare(s=source)
    check("first preparation uses existing home layout and portable state", (home / "profiles").is_dir()
          and e.read_state(home)["distribution"] == "portable" and e.data_state(home, releases[0], full=True)["state"] == "ok")
    for name in ("profiles/Player/user/ save", "mods/preserve.txt", "save_history/old/user/save", "sessions/old/session.txt"):
        f = home / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"user-owned keep")
    kept = {n: h for n, h in tree_hash(home).items() if n.startswith(("profiles/", "mods/", "save_history/", "sessions/"))
            or n == "settings.json"}
    prepare()
    check("repeat preparation preserves all user bytes", all(e.sha256(home / n) == h for n, h in kept.items()))
    moved = t / "Moved İ renamed"
    home.rename(moved)
    prepare(moved)
    check("relocation preserves data and resolves home from its new position", e.data_state(moved, releases[0], full=True)["state"] == "ok")
    old = tree_hash(moved)
    # Separate installed fixture: no portable operation may touch it.
    installed = t / "installed"
    e.install(installed, payload, source, "vanilla", releases=releases, log=lambda *_: None)
    installed_before = tree_hash(installed)
    new = t / "New update"
    newer_payload, _, _ = e.make_fixture(t, "0.29.1", b"v2")
    shutil.copytree(newer_payload, new)
    for name in e.VC_RUNTIME:
        (new / "bin" / name).write_bytes(b"synthetic-runtime-presence")
    e.write_json(new / "portable.json", {"schema": 1, "data_model": "beside-application", "files": {
        f.relative_to(new).as_posix(): {"size": f.stat().st_size, "sha256": e.sha256(f)}
        for f in new.rglob("*") if f.is_file()}})
    for name in (*e.USER_ITEMS, "data"):
        src, dst = moved / name, new / name
        if src.is_dir():
            shutil.copytree(src, dst)
        elif src.is_file():
            shutil.copyfile(src, dst)
    prepare(new)
    check("newer-payload update preserves copied settings/saves/mods", all(e.sha256(new / n) == h for n, h in kept.items())
          and e.read_state(new)["version"] == "0.29.1")
    check("update leaves old portable and installed home unchanged", tree_hash(moved) == old and tree_hash(installed) == installed_before)
    # Same-size damage must be detected, and refusing it must leave saves/settings intact.
    f = new / "data/content/GAMEDATAbin/a.bhf"
    f.write_bytes(b"BAD")
    check("same-size data corruption refuses", refused(lambda: prepare(new), "PACKAGE_REQUIRED"))
    with patch.dict(os.environ, {"R3HD_INSTALL_FAULT": "commit:installer.json"}):
        try:
            prepare(new, source)
            rolled_back = False
        except OSError:
            rolled_back = True
    check("failed repair rolls back through the existing journal", rolled_back and f.read_bytes() == b"BAD"
          and not (new / e.TXN).exists() and all(e.sha256(new / n) == h for n, h in kept.items()))
    prepare(new, source)
    check("reacquisition repairs data without resetting user files", all(e.sha256(new / n) == h for n, h in kept.items())
          and f.read_bytes() == b"aaa")
    sf = new / "settings.json"
    saved = sf.read_bytes()
    sf.write_bytes(b"invalid")
    check("invalid settings preserved and refused", refused(lambda: prepare(new), "SETTINGS_INCOMPATIBLE") and sf.read_bytes() == b"invalid")
    sf.write_bytes(saved)
    with patch.object(e.os, "open", side_effect=PermissionError(5, "synthetic access denied")):
        try:
            prepare(new)
            denied = False
        except PermissionError:
            denied = True
    check("write denial propagates without fallback or user-data changes", denied and all(e.sha256(new / n) == h for n, h in kept.items()))
    e.write_json(new / e.STATE, {**e.read_state(new), "payload_id": "different"})
    check("overlay update refused rather than silently mixing versions", refused(lambda: prepare(new), "PORTABLE_UPDATE_REQUIRED"))
    (moved / "bin/rexruntime.dll").write_bytes(b"damaged")
    check("damaged program refused before data changes", refused(lambda: prepare(moved), "PORTABLE_DAMAGED"))
    check("installed home still unchanged", tree_hash(installed) == installed_before)


def actual(archive, t):
    result = pack.check(archive)
    check("actual ZIP exact contents and all checksums", result["result"] == "PASS")
    dest = t / "Extracted Türkçe path"
    with zipfile.ZipFile(archive) as z:
        z.extractall(dest)
    home = dest / pack.TOP
    # Call packaged Python and script from an unrelated working directory, with no interactive prompts.
    env = {k: v for k, v in os.environ.items() if not k.startswith("R3HD_")}
    env.update(R3HD_HOME=str(t / "must-not-exist"), R3HD_GAME_DIR=str(t / "must-not-exist"))
    args = [str(home / "app/python/python.exe"), "-B", str(home / "app/tools/r3hd_portable.py"), "prepare", "--no-input"]
    r = subprocess.run(args, cwd=t, env=env, capture_output=True)
    print(f"packaged prepare exit={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}", flush=True)
    check("packaged first run refuses missing data with lawful acquisition guidance", r.returncode == 2 and b"PACKAGE_REQUIRED" in r.stderr)
    check("packaged startup ignores inherited installed home", not (t / "must-not-exist").exists())
    # Negative fixtures contain no runtime or game bytes. Never duplicate a key-bearing archive.
    bad = t / "tampered.zip"
    fixture = {"schema": 1, "files": {"Play.cmd": {"size": 8, "sha256": pack.digest(b"original")}}}
    with zipfile.ZipFile(bad, "w") as dst:
        dst.writestr(pack.TOP + "/portable.json", pack.encoded(fixture))
        dst.writestr(pack.TOP + "/Play.cmd", b"bad")
    try:
        pack.check(bad)
        rejected = False
    except ValueError as exc:
        rejected = str(exc) == "Archive checksum mismatch: Play.cmd"
    check("no-key modified ZIP fixture rejected by checksum", rejected)
    extra = t / "leaking.zip"
    with zipfile.ZipFile(extra, "w") as dst:
        dst.writestr(pack.TOP + "/portable.json", pack.encoded(fixture))
        dst.writestr(pack.TOP + "/Play.cmd", b"original")
        dst.writestr(pack.TOP + "/profiles/default/user/save", b"synthetic personal data")
    try:
        pack.check(extra)
        rejected = False
    except ValueError as exc:
        rejected = str(exc) == "Archive members differ from manifest"
    check("no-key ZIP fixture containing an extra save rejected", rejected)
    return home


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path)
    ap.add_argument("--keep", type=Path)
    a = ap.parse_args()
    env = {"R3HD_INSTALL_FAKE_RUNNING": "0", "R3HD_INSTALL_FAKE_LAUNCHER": "0"}
    with tempfile.TemporaryDirectory(prefix="r3hd_portable_") as tmp, patch.dict(os.environ, env):
        t = Path(tmp)
        native = pack.ROOT / "private/work/portable/utf8_path.exe"
        if not native.is_file():
            raise RuntimeError("Build the host-only UTF-8 probe with tools/build_utf8_path_test.bat first")
        r = subprocess.run([str(native), str(t / "UTF-8 Türkçe 東京")], capture_output=True)
        check("native process manifest reads/writes/renames UTF-8 paths", r.returncode == 0 and b"acp=65001 same=1" in r.stdout)
        r = subprocess.run([str(native.with_name("utf8_path_control.exe")), str(t / "Control Türkçe 東京")], capture_output=True)
        check("unchanged native control isolates the code-page conversion", (r.returncode == 1 and b"same=0" in r.stdout)
              or (r.returncode == 0 and b"acp=65001 same=1" in r.stdout))
        (t / "synthetic").mkdir()
        synthetic(t / "synthetic")
        if a.archive:
            home = actual(a.archive, t)
            if a.keep:
                shutil.copytree(home, a.keep)
    print(f"R3HD_PORTABLE_REGRESSION PASS checks={len(checks)} game_starts=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
