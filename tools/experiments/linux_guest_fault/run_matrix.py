"""Isolated source-only fault research runner. Never builds or runs the game."""
import argparse
import hashlib
import importlib.util
import json
import platform
from pathlib import Path
import shutil
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def invoke(argv, records, expected=0):
    start = time.monotonic()
    p = subprocess.run([str(x) for x in argv], capture_output=True, text=True, timeout=120)
    records.append({"command": [str(x) for x in argv], "returncode": p.returncode,
                    "stdout": p.stdout, "stderr": p.stderr,
                    "elapsed_seconds": time.monotonic() - start, "expected": expected})
    if p.returncode != expected:
        raise RuntimeError(f"Expected {expected}, got {p.returncode}: {argv}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cxx", action="append")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--out", type=Path, default=ROOT / "private/work/linux_guest_fault/matrix")
    ap.add_argument("--sdk", type=Path, default=ROOT / "external/rexglue-sdk")
    ap.add_argument("--portable-only", action="store_true", help="record model only; Windows compatible")
    ap.add_argument("--sanitize", action="store_true", help="record model ASan/UBSan only on Linux; no hardware claim")
    args = ap.parse_args()
    if args.repeats < 1:
        ap.error("positive repetitions required")
    linux = platform.system() == "Linux" and platform.machine().lower() == "x86_64"
    if not args.portable_only and not linux:
        ap.error("native Linux x86-64 required; use --portable-only for the record model")
    if args.sanitize and not linux:
        ap.error("this sanitizer matrix requires Linux")
    args.out.mkdir(parents=True, exist_ok=True)
    result = {"status": "INCOMPLETE", "platform": platform.platform(),
              "machine": platform.machine(), "portable_only": args.portable_only,
              "sanitizer_scope": "record model only" if args.sanitize else "none",
              "sources": {p.name: hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                          for p in sorted(HERE.iterdir()) if p.is_file()},
              "configurations": []}
    try:
        if not args.portable_only:
            spec = importlib.util.spec_from_file_location("pgeh_native", HERE.parent / "portable_guest_eh/run_native.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            result["sdk"] = mod.sdk_info(args.sdk.resolve())
            result["emitter_sources"] = {p.name: mod.digest(p) for p in sorted((HERE.parent / "portable_guest_eh").iterdir())
                                         if p.suffix in (".cpp", ".h", ".py")}
        for cxx in args.cxx or ["clang++", "g++"]:
            driver = shutil.which(cxx)
            if not driver:
                raise RuntimeError(f"missing compiler: {cxx}")
            for opt in ("O0", "O2"):
                rec = {"compiler": driver, "optimization": opt, "commands": []}
                result["configurations"].append(rec)
                log = rec["commands"]
                rec["version"] = invoke([driver, "--version"], log)
                out = args.out / (Path(driver).stem + "_" + opt)
                out.mkdir(parents=True, exist_ok=True)
                exe = out / ("record.exe" if platform.system() == "Windows" else "record")
                flags = ["-Wall", "-Wextra", "-Werror", "-" + opt, "-fno-fast-math"]
                if args.sanitize:
                    flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
                invoke([driver, "-std=c++23", *flags, HERE / "record_tests.cpp", "-o", exe], log)
                for _ in range(args.repeats):
                    if "RECORD_CONTRACT PASS" not in invoke([exe], log):
                        raise RuntimeError("missing record success marker")
                if not args.portable_only and not args.sanitize:
                    run_native(driver, flags, out, log, args)
                rec["status"] = "PASS"
        result["status"] = "PASS"
    finally:
        (args.out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("LINUX_FAULT_MATRIX PASS scope=" + ("record-only" if args.portable_only or args.sanitize else "native-fixtures"))


def run_native(driver, flags, out, log, args):
    includes = ["-isystem", args.sdk.resolve() / "include", "-isystem",
                args.sdk.resolve() / "thirdparty/simde"]
    for name in ("transport",):
        invoke([driver, "-x", "c", "-std=gnu11", *flags, "-DLGF_TEST",
                "-c", HERE / (name + ".c"), "-o", out / (name + ".o")], log)
    invoke([driver, "-DLGF_TEST", "-c", HERE / "access.S", "-o", out / "access.o"], log)
    exe = out / "fault_fixture"
    invoke([driver, "-std=c++23", *flags, "-fexceptions", "-pthread", "-DLGF_TEST",
            *includes, HERE / "fault_fixture.cpp", out / "transport.o", out / "access.o",
            "-o", exe], log)
    # All deliberate crashes are separate exec'd subprocesses. Exact signals
    # distinguish default rejection from exit(128+signal) and unexpected aborts.
    for _ in range(args.repeats):
        if "LGF_FIXTURE PASS mode=normal" not in invoke([exe, "normal"], log):
            raise RuntimeError("missing fault fixture success marker")
        if "LGF_FIXTURE PASS mode=prior-handler" not in invoke([exe, "prior-handler"], log):
            raise RuntimeError("missing handler ownership refusal marker")
        for mode in ("host-null", "host-outside", "wrong-site", "unarmed", "reentrant"):
            invoke([exe, mode], log, -signal.SIGSEGV)
        invoke([exe, "unsupported-bus"], log, -signal.SIGBUS)
    invoke([driver, "-x", "c", "-std=gnu11", *flags,
            "-c", HERE / "context_fixture.c", "-o", out / "context_fixture.o"], log)
    invoke([driver, "-c", HERE / "context_state.S", "-o", out / "context_state.o"], log)
    context_exe = out / "context_fixture"
    invoke([driver, out / "context_fixture.o", out / "context_state.o", "-o", context_exe], log)
    for _ in range(args.repeats):
        if "LGF_CONTEXT PASS" not in invoke([context_exe], log):
            raise RuntimeError("missing native context success marker")


if __name__ == "__main__":
    main()
