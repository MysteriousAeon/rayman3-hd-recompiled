#!/usr/bin/env python3
"""Reproduce current mouse limitations and check existing input compatibility.

Research only: no game, window, physical devices or injected OS input. PASS
means baseline reproduced, NOT that mouse attacks meet feature acceptance.
Run: python tools/r3hd_mouse_regression.py
Needs the existing installed SDK, built runtime and M32 driver test.
"""
import hashlib
import os
from pathlib import Path
import re
import runpy
import subprocess
import tempfile

import m32_regression as keyboard
import r3hd_padmap_regression as controller
import r3hd_mouse_context_report as context_report
import r3hd_mouse_dispatch_report as dispatch_report
import r3hd_mouse_dispatch_patch as dispatch_patch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "private/work/mouse_probe"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # Keep resolver CLI child processes on the same writable temporary root.
    tmp = OUT / "temp"
    tmp.mkdir(exist_ok=True)
    old_temp = tempfile.tempdir
    old_env = {name: os.environ.get(name) for name in ("TMP", "TEMP")}
    try:
        tempfile.tempdir = str(tmp)
        os.environ.update(TMP=str(tmp), TEMP=str(tmp))
        result = subprocess.run(
            ["cmd", "/d", "/c", str(ROOT / "tools/devenv.bat"), str(ROOT / "tools/build_mouse_probe.bat")],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
        (OUT / "baseline.log").write_bytes((result.stdout + result.stderr).encode("utf-8"))
        print(result.stdout + result.stderr, end="")
        if result.returncode or not re.search(r"R3HD_MOUSE_BASELINE PASS checks=97 failures=0", result.stdout):
            raise RuntimeError(f"mouse baseline failed or missing evidence (exit {result.returncode})")
        context_checks, context_failures = context_report.selftest()
        dispatch_checks, dispatch_failures = dispatch_report.selftest()
        # Verify optional instrumentation replay on a disposable source copy,
        # never by mutating the installed SDK during a regression.
        import m8_runtime_patch as patcher
        import m16_runtime_patch as installer
        with tempfile.TemporaryDirectory(dir=tmp) as scratch:
            sdk = Path(scratch)
            source = sdk / "src/kernel/xam/xam_input.cpp"
            source.parent.mkdir(parents=True)
            (sdk / "include/rex").mkdir(parents=True)
            original = (ROOT / "external/rexglue-sdk/src/kernel/xam/xam_input.cpp").read_bytes()
            source.write_bytes(original)
            previous = patcher.SDK, installer.SDK
            try:
                patcher.SDK = installer.SDK = sdk
                runpy.run_path(str(ROOT / "tools/r3hd_mouse_context_patch.py"), run_name="__main__")
                once = source.read_bytes()
                runpy.run_path(str(ROOT / "tools/r3hd_mouse_context_patch.py"), run_name="__main__")
                text = once.decode("utf-8")
                if (source.read_bytes() != once or text.count("r3hd_mouse_trace::Poll(") != 1
                        or text.index("r3hd_mouse_trace::Poll(") > text.index("auto s = m6input::Sample(")):
                    raise RuntimeError("context patch replay/idempotence/ordering failed")
                print("MOUSE_CONTEXT_PATCH_TEST PASS idempotence, single hook before sampling")
            finally:
                patcher.SDK, installer.SDK = previous
            host = sdk / "host"
            host.mkdir()
            wrapper = host / "m2_trace.cpp"
            wrapper.write_bytes((ROOT / "tools/m2_host/m2_trace.cpp").read_bytes())
            dispatch_patch.apply(host)
            once = wrapper.read_bytes()
            dispatch_patch.apply(host)
            if (wrapper.read_bytes() != once or once.count(b"r3hd_mouse_dispatch::Enter(name, ctx);") != 1
                    or once.index(b"r3hd_mouse_dispatch::Enter(name, ctx);") > once.index(b"if (!m2_probes) return;")):
                raise RuntimeError("dispatcher patch replay/idempotence/ordering failed")
            # Ambiguous/missing host probe must fail closed, not silently instrument elsewhere.
            wrapper.write_bytes(b"// no existing entry probe\n")
            try:
                dispatch_patch.apply(host)
            except ValueError:
                pass
            else:
                raise RuntimeError("dispatcher patch accepted unknown wrapper")
            print("MOUSE_DISPATCH_PATCH_TEST PASS idempotence, pre-research entry hook, unknown wrapper refused")
        keyboard.checks.clear()
        controller.checks.clear()
        km, pm = keyboard.rs.load_keymap(), controller.rs.load_padmap()
        keyboard.keymap_checks(km)
        keyboard.driver_checks(km, OUT)
        controller.tie_checks(km, pm)
        controller.resolver_checks(km, pm)
        controller.runtime_checks()
        checks = keyboard.checks + controller.checks
        failures = sum(not ok for _, ok in checks) + context_failures + dispatch_failures
        identities = []
        for relative in (
            "tools/r3hd_mouse_probe.cpp",
            "private/work/mouse_probe/mouse_probe.exe",
            "private/work/rex/out/build/win-amd64-release/rexruntime.dll",
            "private/work/rex/out/build/win-amd64-release/m32_keymap_test.exe",
            "external/rexglue-sdk/out/install/win-amd64/bin/rexruntime.dll",
        ):
            data = (ROOT / relative).read_bytes()
            if relative.endswith(".cpp"):
                data = data.replace(b"\r\n", b"\n")  # D-065: tracked text under autocrlf.
            digest = hashlib.sha256(data).hexdigest()
            identities.append(f"{digest}  {relative}")
        (OUT / "identities.txt").write_bytes(("\n".join(identities) + "\n").encode("utf-8"))
        print(f"R3HD_MOUSE_INVESTIGATION {'FAIL' if failures else 'PASS'} baseline=97 "
              f"compatibility={len(checks)} context_analysis={context_checks} dispatch_analysis={dispatch_checks} "
              f"failures={failures}; feature acceptance remains BLOCKED")
        return int(bool(failures))
    finally:
        tempfile.tempdir = old_temp
        for name, value in old_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


if __name__ == "__main__":
    raise SystemExit(main())
