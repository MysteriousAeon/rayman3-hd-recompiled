#!/usr/bin/env python3
"""Bounded read-only instrumentation around synthetic installer directory renames.

python tools/r3hd_fixture_diagnose.py OUT [--engine BASELINE.py] [--rounds 5]
No retries, sleeps or changed assertions; retain fixtures and exact failure metadata.
"""
import argparse
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import sys
import traceback

import r3hd_installer


def metadata(path):
    p = Path(path)
    out = {"path": str(p), "exists": p.exists(), "directory": p.is_dir()}
    if p.exists():
        s = p.stat()
        out.update(mode=s.st_mode, attributes=getattr(s, "st_file_attributes", None))
        # Diagnostic only: can THIS process acquire DELETE access with full sharing?
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p,
                                      ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        kernel.CreateFileW.restype = ctypes.c_void_p
        handle = kernel.CreateFileW(str(p), 0x10000, 7, None, 3, 0x02000000, None)
        out["delete_access_error"] = ctypes.get_last_error() if handle == ctypes.c_void_p(-1).value else 0
        if handle != ctypes.c_void_p(-1).value:
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle(handle)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", type=Path)
    ap.add_argument("--engine", type=Path)
    ap.add_argument("--rounds", type=int, default=5, choices=range(1, 11))
    a = ap.parse_args()
    a.out.mkdir()  # Never overwrite retained evidence.
    e = r3hd_installer
    if a.engine:
        spec = importlib.util.spec_from_file_location("baseline_installer", a.engine)
        e = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(e)
    os.environ.update(R3HD_INSTALL_FAKE_RUNNING="0", R3HD_INSTALL_FAKE_LAUNCHER="0")
    events = []
    replace = os.replace
    def observed(src, dst, *args, **kwargs):
        try:
            result = replace(src, dst, *args, **kwargs)
            events.append({"source": str(src), "destination": str(dst), "result": "ok"})
            return result
        except OSError as exc:
            events.append({"source": metadata(src), "destination": metadata(dst),
                           "parent": metadata(Path(dst).parent), "error": str(exc),
                           "winerror": getattr(exc, "winerror", None), "errno": exc.errno})
            raise
    failure = None
    os.replace = observed
    try:
        for n in range(a.rounds):
            t = a.out / f"round{n}"
            t.mkdir()
            p1, tree, releases = e.make_fixture(t, "1.0.1", b"old")
            p2, _, _ = e.make_fixture(t, "1.0.2", b"new")
            home = t / "home"
            e.install(home, p1, tree, "vanilla", releases=releases, log=lambda *_: None)
            before = (home / "settings.json").read_bytes()
            e.install(home, p2, None, releases=releases, log=lambda *_: None)
            assert (home / "settings.json").read_bytes() == before
            assert e.verify(home, full_data=True, releases=releases)["result"] == "healthy"
    except BaseException:
        failure = traceback.format_exc()
    finally:
        os.replace = replace
    record = {"engine": str(a.engine or Path(e.__file__)), "pid": os.getpid(), "rounds": a.rounds,
              "TEMP": os.environ.get("TEMP"), "TMP": os.environ.get("TMP"),
              "events": events, "failure": failure}
    (a.out / "diagnostic.json").write_bytes((json.dumps(record, indent=1) + "\n").encode())
    print(f"FIXTURE_DIAGNOSE {'FAIL' if failure else 'PASS'} rounds={a.rounds} renames={len(events)}")
    return 1 if failure else 0


if __name__ == "__main__":
    sys.exit(main())
