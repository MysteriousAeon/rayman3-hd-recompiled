#!/usr/bin/env python3
"""Bounded LX2F -> 53607db source update. No installed home, SDK, game build or game process.

Build reads the fixed Git commits, not working-tree payload files. Apply verifies the whole staged update and all
destination preconditions before writing; modified source files are refused, existing files backed up privately.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

BASE = "fe6e11ffa607a43627e803107519eb2344347db3"
COMMIT = "53607db18a7c9121acd31f36aa6b6bb936d71bb1"
SELF = "tools/linux/r3hd_mods_update.py"
META = "private/lx2mods"
MANIFEST = META + "/LX2MODS_MANIFEST.json"
SUMS = META + "/LX2MODS_SHA256SUMS"
README = META + "/README.txt"
# Entire implementation checkpoint, plus the local dependency closure used by its GUI, CLI and focused tests.
# None of these are game bytes, binaries, translation assets, keys or private evidence.
CHANGED = (
    "CURRENT_TASK.md", "DECISIONS.md", "EXPERIMENTS.md", "KNOWLEDGE_INDEX.md", "PROJECT_STATE.md",
    "reports/COMPATIBILITY.md", "reports/COVERAGE.md", "reports/LINUX_MODS_PARITY_2026-11.md",
    "reports/LINUX_PARITY_RELEASE_2026-11.md", "tools/linux/README-LINUX.txt",
    "tools/linux/mod_plan_probe.cpp", "tools/linux/r3hd_settings_gui.py", "tools/linux/test_r3hd_mods.py",
    "tools/m33_mod_overlay_test.cpp",
)
SHARED = (
    "tools/r3hd_mods.py", "tools/r3hd_installer.py", "tools/r3hd_intake.py", "tools/r3hd_settings.py",
    "tools/r3hd_ui_locale.py", "tools/r3hd_portable.py", "tools/stfs_extract.py", "tools/linux/r3hd_play.py",
    "tools/linux/test_r3hd_play.py", "tools/linux/test_r3hd_settings_gui.py", "tools/play.ps1",
    "tools/installer/r3hd_en.isl", "tools/installer/r3hd_setup.iss", "tools/m33_mod_overlay.h", "config/settings/registry.json",
    "config/settings/ui_strings.json", "config/controls/keymap.json", "config/controls/padmap.json",
    "config/intake/known_releases.json", "config/release/payload.json",
    "reports/milestone1/data/content_manifest.tsv",
)
# The other checkpoint changes are durable Windows-side records, not Linux runtime/test dependencies. Avoid
# overwriting the Linux checkout's older evidence books (the prior LX2F delta did not transfer those books).
PAYLOAD_CHANGED = tuple(p for p in CHANGED if p.startswith("tools/") or p == "reports/LINUX_MODS_PARITY_2026-11.md")
FILES = sorted((*PAYLOAD_CHANGED, *SHARED, SELF))
README_TEXT = """LX2 Mods source handoff (53607db; base LX2F / fe6e11f)

PRIVATE maintainer transfer. Repository-relative paths, as LX2F; never extract over an installed home.
Verify the outer ZIP SHA-256 first, extract to a new staging folder, then from that folder:
  sha256sum -c private/lx2mods/LX2MODS_SHA256SUMS
  python3 -B tools/linux/r3hd_mods_update.py apply --source "$PWD" --checkout "$HOME/Projects/RaymanLM1"
The apply command rechecks checksums, refuses unexpected destination edits and backs up replaced files under
RaymanLM1/private/lx2mods/backup-*. It accepts already-applied files. No SDK/game rebuild or relink is needed.

From RaymanLM1 (stop on any failure):
  python3 -B tools/linux/test_r3hd_mods.py -v
  python3 -B tools/linux/test_r3hd_settings_gui.py
  python3 -B tools/linux/test_r3hd_play.py
The optional real Turkish test is skipped unless BOTH --turkish ZIP and --game-dir CONTENT are supplied.
Those lawful local assets are NOT in this ZIP. Transfer your existing authorized Turkish ZIP separately now
if it is not already on CachyOS (check the LX2F home's extras/). Do not download or repackage it.

Then reports/LINUX_MODS_PARITY_2026-11.md, "Short CachyOS acceptance": SRC=RaymanLM1, KNOWN=known-good LX2F home,
TEST=a new independent copy. Run the SOURCE GUI against TEST. Do not patch app/ or program integrity manifests in
any portable home. Its unchanged Play.sh supplies the existing M33/M36 native runtime. No menu-entry changes.

Prerequisites: LX2F-era RaymanLM1 source; Python 3.10+; sha256sum, unzip, Bash; tkinter + desktop for GUI; existing
working LX2F Linux portable home with lawful game data/native ELF and matching libraries; writable space for an
independent home copy; authorized Turkish ZIP for real translation acceptance. No pip modules/network are needed.
Optional C++ component proof needs g++/clang++ with C++17; it builds only a test probe, never SDK/game code:
  g++ -std=c++17 -O2 -pthread -Itools tools/linux/mod_plan_probe.cpp -o private/lx2mods/mod-plan-probe
  python3 -B tools/linux/test_r3hd_mods.py --probe private/lx2mods/mod-plan-probe -v
Native GUI/Turkish appearance remains pending. This handoff does not publish a release.
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout


def blob(root, ref, name):
    return git(root, "show", f"{ref}:{name}")


def build(out):
    root = Path(__file__).resolve().parents[2]
    changed = set(git(root, "diff", "--name-only", BASE, COMMIT).decode().splitlines())
    if changed != set(CHANGED):
        raise ValueError("fixed checkpoint changed-file inventory differs")
    payload, rows = {}, {}
    for name in FILES:
        data = Path(__file__).read_bytes().replace(b"\r\n", b"\n") if name == SELF else blob(root, COMMIT, name)
        exists = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{BASE}:{name}"],
                                capture_output=True).returncode == 0
        old = blob(root, BASE, name) if exists else None
        payload[name] = data
        rows[name] = {"sha256": sha(data), "size": len(data), "before_sha256": sha(old) if old is not None else None,
                      "role": "packaging helper" if name == SELF else "changed" if name in CHANGED else "shared dependency"}
    payload[MANIFEST] = (json.dumps({"schema": 1, "base": BASE, "commit": COMMIT, "files": rows,
                                   "checkpoint_changed_files": list(CHANGED),
                                   "records_not_needed_on_linux": sorted(set(CHANGED) - set(PAYLOAD_CHANGED)),
                                   "sdk_delta": None, "game_rebuild": False}, indent=2) + "\n").encode()
    payload[README] = README_TEXT.encode()
    payload[SUMS] = "".join(f"{sha(data)}  {name}\n" for name, data in sorted(payload.items())).encode()
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, (2026, 11, 8, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data, compresslevel=9)
    digest = sha(out.read_bytes())
    out.with_name(out.name + ".sha256").write_bytes(f"{digest}  {out.name}\n".encode())
    print(f"BUILT {out.resolve()} sha256={digest} bytes={out.stat().st_size} files={len(payload)}")


def plain(root, name):
    p = root
    for part in Path(name).parts:
        p = p / part
        if p.exists() or p.is_symlink():
            if p.is_symlink() or getattr(p.lstat(), "st_file_attributes", 0) & 0x400:
                raise ValueError(f"linked path refused: {p}")
    return p


def verify(source):
    manifest = json.loads(plain(source, MANIFEST).read_bytes())
    if manifest.get("schema") != 1 or manifest.get("commit") != COMMIT or manifest.get("base") != BASE \
            or set(manifest.get("files", {})) != set(FILES):
        raise ValueError("unexpected manifest or file inventory")
    sums = {}
    for line in plain(source, SUMS).read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        if name in sums:
            raise ValueError("duplicate checksum entry")
        sums[name] = digest
    if set(sums) != set(FILES) | {MANIFEST, README}:
        raise ValueError("unexpected checksum inventory")
    actual = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file() or p.is_symlink()}
    if actual != set(sums) | {SUMS}:
        raise ValueError("staged update has extra or missing files")
    for name, digest in sums.items():
        data = plain(source, name).read_bytes()
        if sha(data) != digest:
            raise ValueError(f"checksum mismatch: {name}")
        if name in manifest["files"]:
            row = manifest["files"][name]
            if row["sha256"] != digest or row["size"] != len(data):
                raise ValueError(f"manifest mismatch: {name}")
    print(f"VERIFIED staged update: {len(sums)} checksums")
    return manifest


def apply(source, checkout):
    manifest = verify(source)
    if source == checkout or source in checkout.parents or checkout in source.parents:
        raise ValueError("staging and checkout must be separate trees")
    if (checkout / "portable.json").exists() or (checkout / "installer.json").exists() \
            or not (checkout / "config/build/toolchain.json").is_file():
        raise ValueError("destination must be the RaymanLM1 source checkout, never an installed home")
    # Preflight EVERY destination, accepting LF or CRLF source checkouts, before any directory/file write.
    writes = []
    for name, row in manifest["files"].items():
        dest = plain(checkout, name)
        old = dest.read_bytes() if dest.exists() else None
        current = sha(old.replace(b"\r\n", b"\n")) if old is not None else None
        if current not in (row["before_sha256"], row["sha256"]):
            raise ValueError(f"unexpected local change; nothing applied: {name}")
        if old != plain(source, name).read_bytes():
            writes.append((name, old))
    meta = plain(checkout, META)
    meta.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="backup-", dir=meta)) if writes else None
    for name, old in writes:
        if old is not None:
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(old)
    for name, _ in writes:
        dest = checkout / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=".mods-update-", delete=False) as f:
            tmp = Path(f.name)
            f.write((source / name).read_bytes())
        try:
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
    for name in (MANIFEST, README, SUMS):
        plain(checkout, name).write_bytes((source / name).read_bytes())
    for name, row in manifest["files"].items():
        if sha((checkout / name).read_bytes()) != row["sha256"]:
            raise ValueError(f"post-apply mismatch: {name}; backups: {backup}")
    print(f"APPLIED files={len(writes)} backup={backup}; no SDK/game rebuild; installed homes untouched")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("build", "verify", "apply"))
    ap.add_argument("--out", type=Path, default=Path("private/work/linux_build/lx2mods-update.zip"))
    ap.add_argument("--source", type=Path)
    ap.add_argument("--checkout", type=Path)
    a = ap.parse_args()
    try:
        if a.action == "build":
            build(a.out)
        else:
            if not a.source or a.action == "apply" and not a.checkout:
                ap.error("--source required; apply also requires --checkout")
            source = a.source.resolve()
            apply(source, a.checkout.resolve()) if a.action == "apply" else verify(source)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print(f"MODS_UPDATE REFUSED: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
