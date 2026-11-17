#!/usr/bin/env python3
"""LM-A A3: real generated owners against both M4 backends (private; nothing generated is tracked).

Uses the five functions tools/m4_validate_emission.py extracts from the current generated tree into
private/work/rex/m4_generated_test.cpp (real owners, filters and finally funclets of the macro emission) with the
backend-neutral harness tools/m4_generated_fixture_lma.h. Builds:
  Windows (cmd /c tools\\devenv.bat python tools/m4_real_owner_test.py):
    windows-seh-original  the unchanged Windows M4 fixture (tools/m4_generated_fixture.h), as the build's test
    windows-seh           the neutral harness, Windows SEH backend
    windows-portable      the neutral harness, portable backend (R3HD_M4_PORTABLE)
  Linux / WSL (python3 tools/m4_real_owner_test.py):
    linux-portable        the neutral harness, portable backend (GCC), -O0 and -O2
Each must report PASS with the same observations (raises returned, label body entries, cleanup count and the
cleanup funclet's r12/r31). Results: private/work/m4_real/results-<platform>.json; --compare FILE... checks others.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external/rexglue-sdk"
OUT = ROOT / "private/work/m4_real"
WORK = ROOT / "private/work/rex"  # --tree: an extracted LM-A private tree with the same layout (rex_lma/)
GEN = WORK / "generated/default"
WINDOWS = platform.system() == "Windows"
OBS = re.compile(r"M4_REAL_OWNER_TEST (PASS|FAIL) checks=\d+ failures=(\d+) (returned_raise=\S+ body=\S+ "
                 r"cleanup=\S+ cleanup_r12=\S+ cleanup_r31=\S+)")
OBS_ORIGINAL = re.compile(r"actual emitter execution: (\d+) checks, (\d+) failures: (PASS|FAIL)")


def staged(build):
    inc = build / "inc" / "rex"
    inc.mkdir(parents=True, exist_ok=True)
    for name in ("m4_seh.h", "m4_seh_portable.h"):
        shutil.copyfile(ROOT / "tools" / name, inc / name)
    return build / "inc"


SETJMP_FUNCTIONS = ("sub_82559C48", "sub_82559DA8", "sub_82559D90", "sub_82559EF0")  # owners + their real filters


def extract(names):
    found = {}
    for p in sorted(GEN.glob("r3hd_recomp.*.cpp")):
        for m in re.finditer(r"DEFINE_REX_FUNC\((\w+)\) \{.*?^\}", p.read_text(encoding="utf-8"), re.M | re.S):
            if m[1] in names:
                found[m[1]] = m[0]
    assert sorted(found) == sorted(names), sorted(found)
    return "\n".join(found[n] for n in names)


def source(build, kind):
    """kind: original (Windows M4 fixture), neutral (A3 harness), setjmp (A4 harness + the two setjmp owners)."""
    if kind == "setjmp":
        path = build / "real_setjmp.cpp"
        path.write_text(f'#include "{(ROOT / "tools/m4_setjmp_fixture_lma.h").as_posix()}"\n'
                        + extract(SETJMP_FUNCTIONS) + "\nint main() { return SetjmpTests(); }\n", encoding="utf-8")
        return path
    text = (WORK / "m4_generated_test.cpp").read_text(encoding="utf-8")
    first, rest = text.split("\n", 1)
    assert first.startswith('#include "../../../tools/m4_generated_fixture.h"'), first
    fixture = "m4_generated_fixture.h" if kind == "original" else "m4_generated_fixture_lma.h"
    path = build / f"real_{kind}.cpp"
    path.write_text(f'#include "{(ROOT / "tools" / fixture).as_posix()}"\n' + rest, encoding="utf-8")
    return path


def run(cmd, exe, env=None):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        return {"compile_exit": p.returncode, "compile_errors": (p.stdout + p.stderr)[-5000:]}
    r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120, env=env)
    row = {"compile_exit": 0, "exit": r.returncode, "stdout": r.stdout.strip()[-1500:], "stderr": r.stderr.strip()[-800:]}
    if "setjmp" in exe.name:  # A4: the raise set (see tools/m4_setjmp_fixture_lma.h)
        e = dict(env or os.environ, M4_SETJMP_SET="raise")
        x = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120, env=e)
        row["raise"] = {"exit": x.returncode, "exit_hex": f"{x.returncode & 0xFFFFFFFF:08X}",
                        "stdout": x.stdout.strip()[-1500:],
                        "traces": dict(re.findall(r"^TRACE (\w+): (.*)$", x.stdout, re.M)),
                        "pass": x.returncode == 0 and "M4_SETJMP_OWNER_TEST PASS" in x.stdout}
    return row


def windows_build(variant, build, kind):
    inst = SDK / "out/install/win-amd64"
    exe = build / f"{variant}-{kind}.exe"
    cmd = ["clang++", "-DNOMINMAX", "-DREX_HAS_D3D12=1", "-DSPDLOG_COMPILED_LIB", "-DSPDLOG_FMT_EXTERNAL",
           "-DWIN32_LEAN_AND_MEAN", "-D_DLL", "-D_MT", "-DNDEBUG", "-std=gnu++23", "-O2", "-msse4.1",
           "-fasync-exceptions", "-fexceptions", "-Xclang", "--dependent-lib=msvcrt",
           "-I", str(staged(build)), "-I", str(GEN), "-I", str(WORK),
           "-I", str(WORK / "src"), "-isystem", str(inst / "include"),
           "-isystem", str(inst / "include/dxc"), "-Wno-unused-command-line-argument", "-w"]
    if variant == "windows-portable":
        cmd.append("-DR3HD_M4_PORTABLE")
    cmd += [str(source(build, kind)), "-o", str(exe),
            str(inst / "lib/rexruntime.lib"), str(inst / "lib/spdlog.lib"), str(inst / "lib/fmt.lib"),
            str(inst / "lib/TracyClient.lib")]
    env = dict(__import__("os").environ)
    env["PATH"] = str(inst / "bin") + ";" + env.get("PATH", "")
    return run(cmd, exe, env)


def linux_build(opt, build, kind, cxx="g++"):
    # Headers only; linked objects are ours alone (fmt's formatting and inert logging entry points, no SDK runtime).
    # On a host with the Linux SDK install (CachyOS) its headers are used, otherwise the Windows install's.
    inst = next(p for p in (SDK / "out/install/linux-amd64", SDK / "out/install/win-amd64") if (p / "include").is_dir())
    exe = build / f"linux-portable-{Path(cxx).name}-{opt.strip('-')}-{kind}"
    cmd = [cxx, "-std=c++23", opt, "-msse4.1", "-fexceptions", "-pthread", "-w", "-DREX_PLATFORM_LINUX=1",
           "-DSPDLOG_FMT_EXTERNAL", "-DNDEBUG",
           "-include", str(ROOT / "tools/linux/compat_gcc/rex_gcc_builtin_assume.h"),
           "-include", str(ROOT / "tools/experiments/linux_guest_entry/lge_define_rex_func.h"),
           "-I", str(staged(build)), "-I", str(build / "logstub"), "-I", str(GEN), "-I", str(WORK),
           "-I", str(WORK / "src"), "-I", str(ROOT / "tools/linux/compat"),
           "-isystem", str(inst / "include"), "-isystem", str(SDK / "thirdparty/fmt/include"),
           "-isystem", str(SDK / "thirdparty/spdlog/include"),
           str(source(build, kind)),
           # Link only: fmt's formatting functions and inert SDK logging entry points (no Linux SDK build here).
           str(SDK / "thirdparty/fmt/src/format.cc"), str(ROOT / "tools/linux/m4_log_link_stub.cpp"),
           "-o", str(exe)]
    return run(cmd, exe)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compare", nargs="*", type=Path, default=[])
    ap.add_argument("--cxx", action="append", help="Linux compiler(s) (default g++; repeat for clang++)")
    ap.add_argument("--tree", type=Path, help="tree root holding generated/default, src and m4_generated_test.cpp")
    args = ap.parse_args()
    if args.tree:
        global WORK, GEN
        WORK = args.tree.resolve()
        GEN = WORK / "generated/default"
    build = OUT / f"build-{platform.system().lower()}"
    build.mkdir(parents=True, exist_ok=True)
    rows = {}
    if WINDOWS:
        rows["windows-seh-original"] = windows_build("windows-seh-original", build, "original")
        for variant in ("windows-seh", "windows-portable"):
            for kind in ("neutral", "setjmp"):
                rows[f"{variant}-{kind}"] = windows_build(variant, build, kind)
    else:
        for cxx in args.cxx or ["g++"]:
            for opt in ("-O0", "-O2"):
                for kind in ("neutral", "setjmp"):
                    rows[f"linux-portable-{Path(cxx).name}{opt}-{kind}"] = linux_build(opt, build, kind, cxx)
    for name, row in rows.items():
        out = row.get("stdout", "")
        m = OBS.search(out)
        o = OBS_ORIGINAL.search(out) if name == "windows-seh-original" else None
        s = re.search(r"M4_SETJMP_OWNER_TEST (PASS|FAIL)", out)
        row["pass"] = row.get("exit") == 0 and bool((m and m.group(1) == "PASS") or (o and o.group(3) == "PASS")
                                                    or (s and s.group(1) == "PASS"))
        row["observations"] = m.group(3) if m else None
        row["setjmp_traces"] = dict(re.findall(r"^TRACE (\w+): (.*)$", out, re.M)) if s else None
        if "raise" in row:
            if name.startswith("windows-seh"):
                # E-372: characterized Windows SEH divergence for these two owners (unhandled guest raise, 0xE0473458).
                row["raise"]["windows_known_divergence"] = row["raise"]["exit_hex"] == "E0473458"
                row["pass"] = row["pass"] and row["raise"]["windows_known_divergence"]
            else:
                row["pass"] = row["pass"] and row["raise"]["pass"]
    neutral = {n: r["observations"] for n, r in rows.items() if r.get("observations")}
    setjmp = {n: json.dumps(r["setjmp_traces"], sort_keys=True) for n, r in rows.items() if r.get("setjmp_traces")}
    for f in args.compare:
        for n, r in json.loads(f.read_text())["rows"].items():
            if r.get("observations"):
                neutral[f"{f.name}:{n}"] = r["observations"]
            if r.get("setjmp_traces"):
                setjmp[f"{f.name}:{n}"] = json.dumps(r["setjmp_traces"], sort_keys=True)
    same = len(set(neutral.values())) == 1 and len(set(setjmp.values())) == 1
    result = {"platform": platform.platform(), "rows": rows, "observations": neutral, "setjmp": setjmp,
              "identical": same, "pass": all(r["pass"] for r in rows.values()) and same}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"results-{platform.system().lower()}.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for n, r in rows.items():
        print(f"{n}: compile={r['compile_exit']} exit={r.get('exit')} pass={r['pass']} {r.get('observations') or ''}")
        if r.get("compile_errors"):
            print(r["compile_errors"][-3000:])
        elif not r["pass"]:
            print(r.get("stdout", ""), r.get("stderr", ""))
    print(f"M4_REAL_OWNER_RUN {'PASS' if result['pass'] else 'FAIL'} builds={len(rows)} identical={same} "
          f"compared={len(args.compare)} results={path}")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
