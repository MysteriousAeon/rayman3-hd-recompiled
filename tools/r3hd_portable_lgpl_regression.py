#!/usr/bin/env python3
"""Portable replacement policy and optional real Windows loader checks. Never starts a game.

--original-bin DIR --replacement-bin DIR: use recipient-built modified LGPL DLLs.
No third-party binaries are committed or archived by this test.
"""
import argparse
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from unittest.mock import patch

import r3hd_installer as e
import r3hd_portable as p
import r3hd_portable_zip as pack


def pe_fixture():
    data = bytearray(128)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 68, 0x8664)
    struct.pack_into("<H", data, 86, 0x2000)
    struct.pack_into("<H", data, 88, 0x20B)
    return bytes(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--original-bin", type=Path)
    ap.add_argument("--replacement-bin", type=Path)
    a = ap.parse_args()
    if bool(a.original_bin) != bool(a.replacement_bin):
        ap.error("Supply both DLL directories")
    checks = []

    def check(name, ok):
        checks.append(ok)
        print(("PASS " if ok else "FAIL ") + name, flush=True)
        if not ok:
            raise AssertionError(name)

    def refuses(fn, code):
        try:
            fn()
        except e.Refusal as exc:
            return exc.code == code
        return False

    with tempfile.TemporaryDirectory(prefix="r3hd_lgpl_") as tmp, patch.dict(os.environ, {
            "R3HD_INSTALL_FAKE_RUNNING": "0", "R3HD_INSTALL_FAKE_LAUNCHER": "0"}):
        t = Path(tmp)
        payload, source, releases = e.make_fixture(t)
        home = t / "Portable Türkçe"
        shutil.copytree(payload, home)
        originals = {}
        for rel in p.REPLACEABLE_LGPL:
            originals[rel] = (a.original_bin / Path(rel).name).read_bytes() if a.original_bin else pe_fixture()
            (home / rel).write_bytes(originals[rel])
        for name in e.VC_RUNTIME:
            (home / "bin" / name).write_bytes(b"synthetic CRT")
        files = {f.relative_to(home).as_posix(): {"size": f.stat().st_size, "sha256": e.sha256(f)}
                 for f in home.rglob("*") if f.is_file()}
        e.write_json(home / "portable.json", {"schema": 1, "data_model": "beside-application", "files": files})
        prepare = lambda: p.prepare(home, source, releases=releases, log=lambda *_: None)
        prepare()
        check("untouched extracted manifest", p.check_files(home)["payload_id"] == e.read_state(home)["payload_id"])
        for rel in sorted(p.REPLACEABLE_LGPL):
            f = home / rel
            changed = (a.replacement_bin / f.name).read_bytes() if a.replacement_bin else originals[rel] + b"different size/hash"
            check(rel + " replacement differs", pack.digest(changed) != files[rel]["sha256"])
            f.write_bytes(changed)
            prepare()
            check(rel + " allowed and never restored", f.read_bytes() == changed)
            f.unlink()
            check(rel + " missing diagnostic", refuses(prepare, "PORTABLE_LGPL_MISSING"))
            f.write_bytes(b"not a DLL")
            check(rel + " bad format diagnostic", refuses(prepare, "PORTABLE_LGPL_FORMAT"))
            wrong = bytearray(pe_fixture())
            struct.pack_into("<H", wrong, 68, 0x14C)
            f.write_bytes(wrong)
            check(rel + " x86 refused", refuses(prepare, "PORTABLE_LGPL_FORMAT"))
            f.write_bytes(changed)
        for rel in ("bin/r3hd.exe", "bin/rexruntime.dll", "bin/rexgpu-xenos.dll",
                    "bin/" + e.VC_RUNTIME[0], "app/tools/play.ps1", "app/r3hd_launcher.exe",
                    "app/config/settings/registry.json", "payload.json"):
            f = home / rel
            saved = f.read_bytes()
            f.write_bytes(saved + b"tampered")
            check(rel + " hash remains strict", refuses(prepare, "PORTABLE_DAMAGED"))
            f.unlink()
            check(rel + " missing remains strict", refuses(prepare, "PORTABLE_DAMAGED"))
            f.write_bytes(saved)
        extra = home / "bin/another.dll"
        extra.write_bytes(pe_fixture())
        check("unlisted DLL still refused", refuses(prepare, "PORTABLE_DAMAGED"))
        extra.unlink()
        relocated = t / "Moved İ"
        home.rename(relocated)
        home = relocated
        prepare()
        check("replacements survive relocation", all(e.sha256(home / rel) != files[rel]["sha256"] for rel in p.REPLACEABLE_LGPL))
        # The unchanged archive checker must reject changed LGPL bytes, even though startup permits them.
        archive = t / "no-key-fixture.zip"
        with zipfile.ZipFile(archive, "w") as z:
            rel = "bin/mspack.dll"
            z.writestr(pack.TOP + "/portable.json", pack.encoded({"files": {rel: files[rel]}}))
            z.writestr(pack.TOP + "/" + rel, pe_fixture() + b"changed")
        try:
            pack.check(archive)
            strict = False
        except ValueError as exc:
            strict = "Archive checksum mismatch: bin/mspack.dll" in str(exc)
        check("archive LGPL hash remains strict (no-key fixture)", strict)
        if a.replacement_bin:
            # Fresh child process: no previously loaded module can satisfy the lookup.
            # Restricted LoadLibraryEx search, no new app production loading mechanism.
            child = r'''
import ctypes, sys
from pathlib import Path
home = Path(sys.argv[1])
ff = ctypes.CDLL(str(home / 'bin/ffmpeg.dll'), winmode=0x1100)
ff.av_frame_alloc.restype = ctypes.c_void_p
frame = ctypes.c_void_p(ff.av_frame_alloc())
assert frame.value
ff.av_frame_free.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
ff.av_frame_free(ctypes.byref(frame))
assert frame.value is None
ms = ctypes.CDLL(str(home / 'bin/mspack.dll'), winmode=0x1100)
for name in ('lzxd_init', 'lzxd_decompress', 'lzxd_free'):
    getattr(ms, name)
print('REAL_LGPL_LOADER PASS ffmpeg_alloc_free=1 mspack_exports=3')
'''
            r = subprocess.run([sys.executable, "-c", child, str(home)], capture_output=True, text=True)
            print(r.stdout, end="")
            if r.stderr:
                print(r.stderr, end="")
            check("actual modified DLLs load after portable preparation", r.returncode == 0)
    print(f"PORTABLE_LGPL_REGRESSION PASS checks={len(checks)} real_loader={int(bool(a.replacement_bin))} game_starts=0")


if __name__ == "__main__":
    main()
