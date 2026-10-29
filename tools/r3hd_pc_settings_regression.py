#!/usr/bin/env python3
"""Reproduce PC Settings input-ownership blockers; no game/UI/device/global input.

PASS is a feasibility baseline, never feature acceptance. Logs and exact native
binary identities stay private. Uses the existing SDK headers and runtime.
"""
import hashlib
from pathlib import Path
import re
import subprocess

import m32_regression as keyboard

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "private/work/pc_settings_probe"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cmd", "/d", "/c", str(ROOT / "tools/devenv.bat"),
         str(ROOT / "tools/build_pc_settings_probe.bat")],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    (OUT / "baseline.log").write_bytes((result.stdout + result.stderr).encode("utf-8"))
    print(result.stdout + result.stderr, end="")
    if result.returncode or not re.search(
            r"PC_SETTINGS_INPUT_BASELINE PASS checks=\d+ failures=0; UI acceptance DEFERRED", result.stdout):
        raise RuntimeError(f"native evidence failed or absent: exit {result.returncode}")
    # Preserve the established real-driver keyboard compatibility checks without
    # starting a game or native UI. No mouse bindings/features are exercised.
    keyboard.checks.clear()
    keymap = keyboard.rs.load_keymap()
    keyboard.keymap_checks(keymap)
    keyboard.driver_checks(keymap, str(OUT))
    if any(not ok for _, ok in keyboard.checks):
        raise RuntimeError("existing keyboard compatibility checks failed")
    paths = (
        "tools/r3hd_pc_settings_probe.cpp",
        "private/work/pc_settings_probe/probe.exe",
        "private/work/rex/out/build/win-amd64-release/rexruntime.dll",
        "external/rexglue-sdk/out/install/win-amd64/bin/rexruntime.dll",
        "private/work/rex/out/build/win-amd64-release/m32_keymap_test.exe",
    )
    identities = []
    for relative in paths:
        data = (ROOT / relative).read_bytes()
        if relative.endswith(".cpp"):
            data = data.replace(b"\r\n", b"\n")
        identities.append(f"{hashlib.sha256(data).hexdigest()}  {relative}")
    (OUT / "identities.txt").write_bytes(("\n".join(identities) + "\n").encode("utf-8"))
    print(f"PC_SETTINGS_FEASIBILITY_BASELINE PASS keyboard_checks={len(keyboard.checks)}; "
          "product implementation DEFERRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
