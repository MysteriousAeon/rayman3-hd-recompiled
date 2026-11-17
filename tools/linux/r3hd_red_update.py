#!/usr/bin/env python3
"""Private LX2F + Mods -> E-383 source/SDK-delta handoff.
Build uses committed source and an isolated-replay SDK delta. Apply preflights all source
hashes and backs up replacements; it never builds or touches an installed home.
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

BASE = "5d986bbcb2ebee4656baa732714607df3f042d83"
COMMIT = "E-383-red-correction-v1"
SELF = "tools/linux/r3hd_red_update.py"
META = "private/lx2red"
MANIFEST = META + "/LX2RED_MANIFEST.json"
SUMS = META + "/LX2RED_SHA256SUMS"
README = META + "/README.txt"
SOURCE_FILES = (
    "tools/r3hd_vulkan_parity_patch.py", "tools/r3hd_vulkan_parity_regression.py",
    "tools/build_milestone8.bat", "tools/m5_vb_residency_regression.py",
    "tools/linux/test_red_correction_upload.py",
    "reports/LINUX_RED_CORRECTION_2026-11.md", SELF,
)
DELTA_FILES = ("delta.json", "files/src/graphics/vulkan/command_processor.cpp")
FILES = sorted((*SOURCE_FILES, *(META + "/sdk/" + n for n in DELTA_FILES)))
README_TEXT = """PRIVATE LX2RED handoff. Extract to a fresh staging folder, never an installed home.
Verify LX2RED_SHA256SUMS, then run this helper's apply command against RaymanLM1.
Follow reports/LINUX_RED_CORRECTION_2026-11.md for SDK rebuild, package and independent-home visual A/B.
No game data, translated code, profiles, saves or translation assets are supplied. SDK delta is private.
Native visual acceptance is pending. Stop on any failure; do not force a baseline mismatch.
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout


def blob(root, ref, name):
    return git(root, "show", f"{ref}:{name}")


def build(out, commit, delta):
    root = Path(__file__).resolve().parents[2]
    payload, rows = {}, {}
    for name in FILES:
        if name.startswith(META + "/sdk/"):
            data = (delta / name.removeprefix(META + "/sdk/")).read_bytes().replace(b"\r\n", b"\n")
            old = None
        else:
            data = blob(root, commit, name)
            exists = subprocess.run(["git", "-C", str(root), "cat-file", "-e", f"{BASE}:{name}"],
                                    capture_output=True).returncode == 0
            old = blob(root, BASE, name) if exists else None
        payload[name] = data
        rows[name] = {"sha256": sha(data), "size": len(data),
                      "before_sha256": sha(old) if old is not None else None}
    payload[MANIFEST] = (json.dumps({"schema": 1, "base": BASE, "commit": COMMIT,
                                   "implementation_commit": commit, "files": rows,
                                   "native_rebuild": "SDK rexgpu-xenos; SDK install; game sync/stamp"}, indent=2) + "\n").encode()
    payload[README] = README_TEXT.encode()
    payload[SUMS] = "".join(f"{sha(data)}  {name}\n" for name, data in sorted(payload.items())).encode()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        raise ValueError("output exists")
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
        with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=".red-update-", delete=False) as f:
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
    print(f"APPLIED files={len(writes)} backup={backup}; source only; SDK rebuild required; installed homes untouched")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("build", "verify", "apply"))
    ap.add_argument("--out", type=Path, default=Path("private/work/linux_build/lx2red-update.zip"))
    ap.add_argument("--source", type=Path)
    ap.add_argument("--checkout", type=Path)
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--delta", type=Path)
    a = ap.parse_args()
    try:
        if a.action == "build":
            if not a.delta:
                ap.error("build requires --delta from isolated replays")
            build(a.out, git(Path(__file__).resolve().parents[2], "rev-parse", a.commit).decode().strip(), a.delta)
        else:
            if not a.source or a.action == "apply" and not a.checkout:
                ap.error("--source required; apply also requires --checkout")
            source = a.source.resolve()
            apply(source, a.checkout.resolve()) if a.action == "apply" else verify(source)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print(f"RED_UPDATE REFUSED: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
