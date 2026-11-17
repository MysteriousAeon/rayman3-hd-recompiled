#!/usr/bin/env python3
"""Regression for tools/linux/lgpl_so_check.py (E-376) on stand-in libraries (POSIX, a C compiler, binutils nm).

A stand-in libffmpeg.so exports the recorded imports plus extra av* names (a platform's configuration may export
more than Windows: not a failure), libmspack.so the recorded lzxd_* set, and librexruntime.so imports exactly the
recorded functions. PASS is expected; then an exported ff_* name, a missing import and a runtime that defines av_*
itself must each FAIL. The Windows-list difference is reported as information.

  python3 tools/linux/test_lgpl_so_check.py [--cc gcc]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cc", default="cc")
    a = ap.parse_args()
    if os.name == "nt":
        print("R3HD_LGPL_SO_TEST SKIP (POSIX only)")
        return 0
    rec = json.loads((ROOT / "config/release/lgpl_components.json").read_text(encoding="utf-8"))["components"]
    av, lz = rec["ffmpeg"]["imported_by_rexruntime"], rec["libmspack"]["exports"]
    fails = []

    def build(d, ff_extra=(), drop=None, rt_defines=()):
        d.mkdir()
        names = [n for n in av if n != drop] + list(ff_extra)
        (d / "ff.c").write_text("".join(f"void {n}(void) {{}}\n" for n in names))
        (d / "ms.c").write_text("".join(f"void {n}(void) {{}}\n" for n in lz))
        (d / "rt.c").write_text("".join(f"void {n}(void);\n" for n in av + lz) + "".join(
            f"void {n}(void) {{}}\n" for n in rt_defines) + "void rt(void) {" + "".join(f" {n}();" for n in av + lz) + " }\n")
        cc = [a.cc, "-shared", "-fPIC"]
        subprocess.check_call(cc + [str(d / "ff.c"), "-o", str(d / "libffmpeg.so")])
        subprocess.check_call(cc + [str(d / "ms.c"), "-o", str(d / "libmspack.so")])
        subprocess.check_call(cc + [str(d / "rt.c"), "-o", str(d / "librexruntime.so")])  # undefined refs allowed
        return subprocess.run([sys.executable, str(HERE / "lgpl_so_check.py"), "--lib", str(d), "--windows-list",
                               str(d / "win.txt")] if (d / "win.txt").exists() else
                              [sys.executable, str(HERE / "lgpl_so_check.py"), "--lib", str(d)],
                              capture_output=True, text=True)

    def expect(label, r, verdict):
        ok = f"R3HD_LGPL_SO {verdict}" in r.stdout
        print(("ok   " if ok else "FAIL ") + label + ("" if ok else f" ({r.stdout[-400:]}{r.stderr[-300:]})"))
        if not ok:
            fails.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        good = t / "good"
        r = build(good, ff_extra=("av_linux_only_a", "av_linux_only_b"))
        expect("recorded imports + two extra av* exports: PASS (a count is not the criterion)", r, "PASS")
        (good / "win.txt").write_text("EXTERN(\n" + "".join(f"  {n}\n" for n in av) + ")\n")
        r = subprocess.run([sys.executable, str(HERE / "lgpl_so_check.py"), "--lib", str(good), "--windows-list",
                            str(good / "win.txt")], capture_output=True, text=True)
        expect("Windows-list difference reported", r, "PASS")
        if "Linux-only ['av_linux_only_a', 'av_linux_only_b']" not in r.stdout:
            fails.append("Linux-only names reported")
            print("FAIL Linux-only names reported")
        expect("an exported ff_* name: FAIL", build(t / "ffname", ff_extra=("ff_private",)), "FAIL")
        expect("a missing import: FAIL", build(t / "missing", drop=av[0]), "FAIL")
        expect("FFmpeg still inside the runtime: FAIL", build(t / "static", rt_defines=("av_static_left",)), "FAIL")
        # B3b (E-378): libraries rebuilt from the source archive are judged against the shipped runtime.
        rebuilt_bad = t / "rebuilt_bad"
        build(rebuilt_bad, drop=av[1])
        expect("--replacement: a rebuilt libffmpeg.so missing an import: FAIL",
               subprocess.run([sys.executable, str(HERE / "lgpl_so_check.py"), "--lib", str(good), "--replacement",
                               str(rebuilt_bad)], capture_output=True, text=True), "FAIL")
        rebuilt = t / "rebuilt"
        build(rebuilt, ff_extra=("av_other_config",))
        expect("--replacement: a compatible rebuild: PASS",
               subprocess.run([sys.executable, str(HERE / "lgpl_so_check.py"), "--lib", str(good), "--replacement",
                               str(rebuilt)], capture_output=True, text=True), "PASS")
    print(f"R3HD_LGPL_SO_TEST {'PASS' if not fails else 'FAIL'} checks=7")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
