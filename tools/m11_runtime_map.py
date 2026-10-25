#!/usr/bin/env python3
"""Write a linker map for the current rexruntime.dll without touching the SDK build tree (M11).

    cmd /c "tools\\devenv.bat python tools\\m11_runtime_map.py"

The SDK build ships rexruntime.dll without a map or a pdb, so host stack frames inside it (m2_faults.log) could
not be named. This relinks the existing objects with the build's own link line plus /MAP into
private/work/m11_map/ and checks that the result is the shipped DLL apart from the link timestamp, so the map's
addresses are valid for the DLL the game is running. Use the map with tools/m11_symbolize.py.
Needs the toolchain environment (tools\\devenv.bat) for the library paths.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "external/rexglue-sdk/out/build/win-amd64"
SHIPPED = ROOT / "private/work/rex/out/build/win-amd64-release/rexruntime.dll"
OUT = ROOT / "private/work/m11_map"


def main() -> int:
    text = (BUILD / "CMakeFiles/impl-Release.ninja").read_text(encoding="utf-8")
    start = text.index("CXX_SHARED_LIBRARY_LINKER__rexruntime_Release")
    start = text.rindex("\nbuild ", 0, start) + 1
    block = text[start:text.index("\n\n", start)].splitlines()
    var = dict(m.groups() for m in (re.match(r"^  ([A-Z_]+) = (.*)$", line) for line in block[1:]) if m)
    body = block[0].split(": ", 1)[1].split(" || ")[0].split(" | ")[0]
    inputs = [t.replace("$:", ":").replace("$ ", " ") for t in re.split(r"(?<!\$) ", body)[1:] if t]

    OUT.mkdir(parents=True, exist_ok=True)
    rsp = OUT / "link.rsp"
    rsp.write_text(" ".join(inputs) + " " + var.get("LINK_PATH", "") + " " + var["LINK_LIBRARIES"].replace("$:", ":"),
                   encoding="utf-8")
    dll = OUT / "rexruntime.dll"
    cmd = [r"C:\Program Files\LLVM\bin\clang++.exe", "-nostartfiles", "-nostdlib"]
    cmd += var["LANGUAGE_COMPILE_FLAGS"].split() + var["LINK_FLAGS"].split()
    cmd += ["-o", str(dll), "-Xlinker", "/MANIFEST:EMBED", "-Xlinker", f"/implib:{OUT / 'rexruntime.lib'}",
            "-Xlinker", f"/pdb:{OUT / 'rexruntime.pdb'}", "-Xlinker", "/version:0.0",
            "-Xlinker", f"/MAP:{OUT / 'rexruntime.map'}", f"@{rsp}"]
    done = subprocess.run(cmd, cwd=BUILD, capture_output=True, text=True)
    if done.returncode:
        print((done.stdout + done.stderr)[-2000:])
        return done.returncode
    a, b = dll.read_bytes(), SHIPPED.read_bytes()
    differing = sum(x != y for x, y in zip(a, b)) if len(a) == len(b) else -1
    for name in ("rexruntime.dll", "rexruntime.lib", "link.rsp"):
        (OUT / name).unlink(missing_ok=True)
    print(f"map: {OUT / 'rexruntime.map'}; relinked image differs from the shipped DLL in {differing} bytes "
          f"({'size mismatch' if differing < 0 else 'timestamp only expected: <= 8'})")
    return 0 if 0 <= differing <= 8 else 1


if __name__ == "__main__":
    sys.exit(main())
