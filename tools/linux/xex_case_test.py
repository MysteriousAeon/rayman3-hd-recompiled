#!/usr/bin/env python3
"""LX-6 (E-377): the POSIX entrypoint check, compiled from the exact text tools/r3hd_xex_case_patch.py appends.

A directory with the verified name Default.xex must satisfy the runtime's "default.xex" check; other casings too;
a missing file, a directory named default.xex and a different name must not. The hooked `if` line is compiled as
rex_app.cpp has it. POSIX with a C++ compiler (WSL or Linux).

  python3 tools/linux/xex_case_test.py [--cxx g++]
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import r3hd_xex_case_patch as P  # noqa: E402

MAIN = r'''
#include <cstdio>
#include <filesystem>
#include <string>
int check(const std::filesystem::path& xex_host) {
''' + P.LINE_AFTER + r'''      return 0;  // "Entrypoint XEX not found"
    }
  return 1;
}
int main(int argc, char** argv) {
  for (int i = 1; i < argc; ++i) std::printf("%s=%d\n", argv[i], check(std::filesystem::path(argv[i])));
  return 0;
}
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cxx", default="c++")
    a = ap.parse_args()
    if os.name == "nt":
        print("R3HD_XEX_CASE_TEST SKIP (POSIX only)")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "src.cpp").write_text(P.HELPER + MAIN)
        subprocess.check_call([a.cxx, "-std=c++20", "-Wall", "-Werror", str(t / "src.cpp"), "-o", str(t / "x")])
        (t / "content").mkdir()
        (t / "content" / "Default.xex").write_bytes(b"XEX2")
        (t / "dir").mkdir()
        (t / "dir" / "default.xex").mkdir()
        (t / "other").mkdir()
        (t / "other" / "default.xex.bak").write_bytes(b"x")
        cases = {f"{t}/content/default.xex": 1, f"{t}/content/DEFAULT.XEX": 1, f"{t}/content/Default.xex": 1,
                 f"{t}/missing/default.xex": 0, f"{t}/dir/default.xex": 0, f"{t}/other/default.xex": 0}
        out = subprocess.run([str(t / "x"), *cases], capture_output=True, text=True, check=True).stdout
        got = dict(line.rsplit("=", 1) for line in out.splitlines())
        fails = [p for p, want in cases.items() if int(got[p]) != want]
        for p, want in cases.items():
            print(("ok   " if p not in fails else "FAIL ") + f"{Path(p).parent.name}/{Path(p).name} -> {want}")
        print(f"R3HD_XEX_CASE_TEST {'PASS' if not fails else 'FAIL'} checks={len(cases)}")
        return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
