"""Isolated checked-access/record bridge matrix. Never builds or runs the game."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def invoke(argv, log, marker=None):
    start = time.monotonic()
    proc = subprocess.run([str(x) for x in argv], capture_output=True,
                          text=True, timeout=120)
    log.append({"command": [str(x) for x in argv], "returncode": proc.returncode,
                "stdout": proc.stdout, "stderr": proc.stderr,
                "elapsed_seconds": time.monotonic() - start})
    if proc.returncode or proc.stderr or (marker and marker not in proc.stdout):
        raise RuntimeError(f"command failed or unexpected output: {argv}\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=ROOT / "external/rexglue-sdk")
    parser.add_argument("--out", type=Path, default=ROOT / "private/work/linux_guest_integration/matrix")
    parser.add_argument("--cxx", action="append")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--portable-only", action="store_true")
    parser.add_argument("--sanitize", action="store_true", help="Linux ordinary bridge only; excludes signals")
    parser.add_argument("--bench", action="store_true")
    args = parser.parse_args()
    linux = platform.system() == "Linux" and platform.machine().lower() == "x86_64"
    windows = platform.system() == "Windows" and platform.machine().lower() == "amd64"
    if args.repeats < 1 or not (linux or windows):
        parser.error("positive repetitions and Windows/Linux x86-64 required")
    if (not args.portable_only or args.sanitize) and not linux:
        parser.error("native/sanitizer mode requires Linux x86-64; Windows uses --portable-only")
    if args.sanitize and args.bench:
        parser.error("measure unsanitized optimized builds separately")
    spec = importlib.util.spec_from_file_location("pgeh_native", HERE.parent / "portable_guest_eh/run_native.py")
    pgeh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pgeh)
    sdk = args.sdk.resolve()
    sdk_info = pgeh.sdk_info(sdk)
    args.out.mkdir(parents=True, exist_ok=True)
    sources = {}
    for dirname in ("portable_guest_eh", "linux_guest_fault", "linux_guest_integration"):
        for path in sorted((HERE.parent / dirname).iterdir()):
            if path.is_file() and path.suffix in (".h", ".cpp", ".c", ".S", ".py", ".md"):
                sources[str(path.relative_to(ROOT)).replace("\\", "/")] = digest(path)
    results = {"status": "INCOMPLETE", "platform": platform.platform(),
               "machine": platform.machine(), "sdk": sdk_info, "sources": sources,
               "scope": "ordinary bridge" if args.portable_only or args.sanitize else "bridge plus native leaf",
               "sanitizers": "address,undefined" if args.sanitize else "none", "configurations": []}
    try:
        for compiler in args.cxx or (["clang++"] if windows else ["clang++", "g++"]):
            driver = shutil.which(compiler)
            if not driver:
                raise RuntimeError(f"missing compiler: {compiler}")
            for opt in ("O0", "O2"):
                row = {"compiler": driver, "optimization": opt, "commands": [], "status": "INCOMPLETE"}
                results["configurations"].append(row)
                log = row["commands"]
                row["version"] = invoke([driver, "--version"], log)
                build = args.out.resolve() / (Path(driver).stem + "_" + opt)
                build.mkdir(parents=True, exist_ok=True)
                flags = ["-" + opt, "-Wall", "-Wextra", "-Werror", "-fno-fast-math", "-frounding-math"]
                if args.sanitize:
                    flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
                cpp = [driver, "-std=c++23", *flags, "-fexceptions", "-isystem", sdk / "include",
                       "-isystem", sdk / "thirdparty/simde"]
                if linux:
                    cpp.append("-pthread")
                suffix = ".exe" if windows else ""
                exe = build / ("bridge_tests" + suffix)
                invoke([*cpp, HERE / "bridge_tests.cpp", "-o", exe], log)
                for _ in range(args.repeats):
                    invoke([exe], log, "BRIDGE_TESTS PASS checks=")
                row["executable_sha256"] = {exe.name: hashlib.sha256(exe.read_bytes()).hexdigest()}
                if linux and not args.portable_only and not args.sanitize:
                    fault = HERE.parent / "linux_guest_fault"
                    invoke([driver, "-x", "c", "-std=gnu11", *flags, "-c", fault / "transport.c",
                            "-o", build / "transport.o"], log)
                    invoke([driver, "-c", fault / "access.S", "-o", build / "access.o"], log)
                    native = build / "native_bridge"
                    invoke([*cpp, HERE / "native_bridge.cpp", build / "transport.o", build / "access.o",
                            "-o", native], log)
                    for _ in range(args.repeats):
                        invoke([native], log, "NATIVE_BRIDGE PASS checks=")
                    row["executable_sha256"][native.name] = hashlib.sha256(native.read_bytes()).hexdigest()
                if args.bench and opt == "O2":
                    bench = build / ("benchmark" + suffix)
                    invoke([*cpp, HERE / "benchmark.cpp", "-o", bench], log)
                    row["benchmark"] = json.loads(invoke([bench], log))
                row["status"] = "PASS"
        results["status"] = "PASS"
    finally:
        (args.out / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"INTEGRATION_MATRIX PASS configurations={len(results['configurations'])} scope={results['scope']}")


if __name__ == "__main__":
    main()
