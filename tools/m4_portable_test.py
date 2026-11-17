#!/usr/bin/env python3
"""LM-A A1 runner: build tools/m4_portable_test.cpp against both M4 backends and compare them.

Windows (from a tools\\devenv.bat shell, LLVM clang targeting MSVC):
    cmd /c tools\\devenv.bat python tools/m4_portable_test.py
  builds the Windows SEH backend and the portable backend (R3HD_M4_PORTABLE) at -O0 and -O2.
Linux / WSL:
    python3 tools/m4_portable_test.py [--cxx g++] [--cxx clang++]
  builds the portable backend (the only one on Linux), including the D3 cancellation scenarios.

Every build must pass its own expected traces; on Windows both backends must produce identical traces; every
fail-fast child must terminate abnormally (portable: with a FAIL-FAST record). With --compare FILE... the scenario
traces of earlier result files (e.g. Windows and Linux) must also be identical.
Results: private/work/m4_portable/results-<platform>.json. No game code, data or generated functions.
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
OUT = ROOT / "private/work/m4_portable"
WINDOWS = platform.system() == "Windows"
CHILDREN_COMMON = ["unhandled", "unwind_unknown", "bad_resume"]
CHILDREN_PORTABLE = ["boundary_accept", "funclet_raise"]
LOG_STUB = """#pragma once
// m4_portable_test only: the M4 headers log through these macros; the arguments are consumed, not printed.
template <typename... Args> inline void m4_test_log(Args&&...) {}
#define REXKRNL_INFO(...) m4_test_log(__VA_ARGS__)
#define REXLOG_INFO(...) m4_test_log(__VA_ARGS__)
"""


def stage(build):
    inc = build / "inc" / "rex"
    inc.mkdir(parents=True, exist_ok=True)
    for name in ("m4_seh.h", "m4_seh_portable.h"):
        shutil.copyfile(ROOT / "tools" / name, inc / name)
    (inc / "logging.h").write_text(LOG_STUB, encoding="utf-8")
    return build / "inc"


def build_and_run(cxx, backend, opt, build):
    inc = stage(build)
    exe = build / f"m4_portable_{backend}_{opt.strip('-')}{'.exe' if WINDOWS else ''}"
    cmd = [cxx, "-std=c++23", opt, "-Wall", "-Wextra", "-Werror", "-fexceptions", "-fno-fast-math",
           "-I", str(inc), "-isystem", str(SDK / "include"), "-isystem", str(SDK / "thirdparty/simde"),
           str(ROOT / "tools/m4_portable_test.cpp"), "-o", str(exe)]
    if WINDOWS:
        cmd += ["-fasync-exceptions"] if backend == "windows-seh" else ["-DR3HD_M4_PORTABLE"]
        cmd += ["-Wno-unused-command-line-argument"]
    else:
        cmd += ["-pthread"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    row = {"cxx": cxx, "backend": backend, "opt": opt, "compile_exit": p.returncode}
    if p.returncode:
        row["compile_errors"] = (p.stdout + p.stderr)[-6000:]
        return row
    r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
    row.update(exit=r.returncode, summary=r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "",
               traces=dict(re.findall(r"^TRACE (\w+): (.*)$", r.stdout, re.M)),
               failures=[l for l in r.stdout.splitlines() if l.startswith("FAIL")])
    children = {}
    for name in CHILDREN_COMMON + (CHILDREN_PORTABLE if backend == "portable" else []):
        c = subprocess.run([str(exe), "--child", name], capture_output=True, text=True, timeout=60)
        returned = "returned (no fail-fast)" in c.stdout
        fail_fast = "FAIL-FAST" in c.stderr
        ok = c.returncode != 0 and not returned and (fail_fast or backend == "windows-seh")
        children[name] = {"exit": c.returncode, "fail_fast_record": fail_fast, "ok": ok,
                          "stderr": c.stderr.strip()[-300:]}
    row["children"] = children
    row["pass"] = (r.returncode == 0 and row["summary"].startswith("M4_PORTABLE_TEST PASS")
                   and all(c["ok"] for c in children.values()))
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cxx", action="append")
    ap.add_argument("--compare", nargs="*", type=Path, default=[])
    args = ap.parse_args()
    cxxes = args.cxx or (["clang++"] if WINDOWS else ["g++"])
    backends = ["windows-seh", "portable"] if WINDOWS else ["portable"]
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for cxx in cxxes:
        for backend in backends:
            for opt in ("-O0", "-O2"):
                build = OUT / f"build-{platform.system().lower()}-{Path(cxx).name}"
                rows.append(build_and_run(cxx, backend, opt, build))
    ok = all(r.get("pass") for r in rows)
    reference = rows[0].get("traces", {})
    scenario = lambda t: {k: v for k, v in t.items() if k.startswith("S")}  # cancellation (C*) is Linux-only
    same = all(scenario(r.get("traces", {})) == scenario(reference) for r in rows)
    compared = []
    for f in args.compare:
        other = json.loads(f.read_text())
        for r in other["rows"]:
            compared.append({"file": str(f), "backend": r["backend"], "opt": r["opt"],
                             "same": scenario(r.get("traces", {})) == scenario(reference)})
    same = same and all(c["same"] for c in compared)
    result = {"platform": platform.platform(), "rows": rows, "traces_identical": same, "compared": compared,
              "scenarios": sorted(scenario(reference)), "pass": ok and same}
    path = OUT / f"results-{platform.system().lower()}.json"
    path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for r in rows:
        print(f"{r['cxx']} {r['backend']} {r['opt']}: compile={r['compile_exit']} {r.get('summary', '')} "
              f"children={ {k: v['ok'] for k, v in r.get('children', {}).items()} }")
        for line in r.get("failures", []) + ([r["compile_errors"][-2000:]] if r.get("compile_errors") else []):
            print("   ", line)
    print(f"M4_PORTABLE_RUN {'PASS' if result['pass'] else 'FAIL'} builds={len(rows)} traces_identical={same} "
          f"compared={len(compared)} results={path}")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
