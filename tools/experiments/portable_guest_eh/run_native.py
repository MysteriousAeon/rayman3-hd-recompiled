"""Build and run only the isolated native PPC/exception probes; no game data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SDK_PIN = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"
SIMDE_PIN = "71fd833d9666141edcd1d3c109a80e228303d8d7"
SDK_HEADERS = [
    "include/rex/ppc/context.h", "include/rex/platform/fpscr.h",
    "include/rex/ppc/func.h", "include/rex/types.h", "include/rex/assert.h",
    "include/rex/platform.h",
]


def command(argv, *, cwd=None, expected=0, env=None, timeout=120):
    result = subprocess.run([str(x) for x in argv], cwd=cwd, text=True,
                            capture_output=True, env=env, timeout=timeout)
    if result.returncode != expected:
        raise RuntimeError(f"command failed ({result.returncode}, expected {expected}): "
                           f"{argv!r}\n{result.stdout}\n{result.stderr}")
    return result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sdk_info(sdk):
    simde = sdk / "thirdparty" / "simde"
    head = command(["git", "-C", sdk, "rev-parse", "HEAD"]).stdout.strip()
    simde_head = command(["git", "-C", simde, "rev-parse", "HEAD"]).stdout.strip()
    if head != SDK_PIN or simde_head != SIMDE_PIN:
        raise RuntimeError(f"SDK or SIMDe pin mismatch: {head} / {simde_head}")
    # Other SDK files may be patched by the normal build chain. Only the complete
    # include closure used by this probe must be identical to the pinned checkout.
    command(["git", "-C", sdk, "diff", "--quiet", "HEAD", "--", *SDK_HEADERS])
    simde_changes = command(["git", "-C", simde, "status", "--porcelain",
                             "--untracked-files=all", "--", "simde"]).stdout
    if simde_changes:
        raise RuntimeError("SIMDe headers differ from the pin:\n" + simde_changes)
    missing = [str(sdk / h) for h in SDK_HEADERS if not (sdk / h).is_file()]
    if missing or not (simde / "simde" / "x86" / "sse.h").is_file():
        raise RuntimeError(f"Missing SDK/SIMDe headers: {missing}")
    return {"commit": head, "simde_commit": simde_head,
            "sdk_header_sha256": {h: digest(sdk / h) for h in SDK_HEADERS}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sdk", type=Path, default=ROOT / "external" / "rexglue-sdk")
    p.add_argument("--out", type=Path, default=ROOT / "private" / "work" / "portable_guest_eh" / "native")
    p.add_argument("--cxx", action="append", help="repeat to test multiple Clang/GCC drivers")
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--sanitize", action="store_true", help="also run Linux ASan+UBSan or Windows ASan")
    p.add_argument("--bench", action="store_true", help="also run optimized synthetic benchmark")
    args = p.parse_args()
    if args.repeats < 1:
        p.error("--repeats must be positive")
    windows = platform.system() == "Windows"
    if platform.system() not in ("Windows", "Linux") or platform.machine().lower() not in ("amd64", "x86_64"):
        p.error("this milestone supports Windows/Linux x86-64 only")
    sdk, out = args.sdk.resolve(), args.out.resolve()
    info = sdk_info(sdk)
    out.mkdir(parents=True, exist_ok=True)
    source_names = ["ppc_adapter.h", "adapter_tests.cpp", "exception_core.h",
                    "emitter_fixture.cpp", "bridge.cpp", "bridge.h"]
    if args.bench:
        source_names.append("benchmark.cpp")
    sources = {name: digest(HERE / name) for name in source_names}
    results = {"platform": platform.platform(), "machine": platform.machine(),
               "sdk": info, "source_sha256": sources, "configurations": []}
    cxxes = args.cxx or ["clang++"]
    for cxx in cxxes:
        executable = shutil.which(cxx)
        if not executable:
            raise RuntimeError(f"compiler not found: {cxx}")
        version = command([executable, "--version"]).stdout.strip()
        run_env = os.environ.copy()
        if args.sanitize and windows:
            resource_dir = command([executable, "-print-resource-dir"]).stdout.strip()
            run_env["PATH"] = str(Path(resource_dir) / "lib" / "windows") + os.pathsep + run_env.get("PATH", "")
        configs = [("O0", "-O0", []), ("O2", "-O2", [])]
        if args.sanitize:
            configs.append(("san", "-O1", ["-fsanitize=address" if windows else "-fsanitize=address,undefined",
                                           "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]))
        for label, opt, extra in configs:
            dirname = re.sub(r"[^a-zA-Z0-9_.-]", "_", Path(cxx).name) + "_" + label
            build = out / dirname
            build.mkdir(parents=True, exist_ok=True)
            includes = ["-isystem", str(sdk / "include"),
                        "-isystem", str(sdk / "thirdparty" / "simde")]
            common = [executable, "-std=c++23", opt, "-Wall", "-Wextra", "-Werror",
                      "-fexceptions", "-fno-fast-math", "-frounding-math", *extra, *includes]
            if not windows:
                common.append("-pthread")
            suffix = ".exe" if windows else ""
            lib = build / ("pgeh_bridge.dll" if windows else "libpgeh_bridge.so")
            import_lib = build / "pgeh_bridge.lib"
            libcmd = [*common, "-DPGEH_BRIDGE_EXPORTS"]
            if not windows:
                libcmd.append("-fPIC")
            libcmd += ["-shared", str(HERE / "bridge.cpp"), "-o", str(lib)]
            if windows:
                libcmd.append("-Wl,/implib:" + str(import_lib))
            adapter = build / ("adapter_tests" + suffix)
            emitter = build / ("emitter_fixture" + suffix)
            adaptercmd = [*common, str(HERE / "adapter_tests.cpp"), "-o", str(adapter)]
            emitcmd = [*common, str(HERE / "emitter_fixture.cpp"), "-o", str(emitter)]
            if windows:
                emitcmd.append(str(import_lib))
            else:
                emitcmd += ["-L" + str(build), "-lpgeh_bridge", "-Wl,-rpath,$ORIGIN"]
            entry = {"compiler": executable, "version": version, "configuration": label,
                     "commands": [], "runs": []}
            for cmd in (libcmd, adaptercmd, emitcmd):
                command(cmd)
                entry["commands"].append(cmd)
            for iteration in range(args.repeats):
                for exe, marker in ((adapter, "PPC_ADAPTER PASS checks="),
                                    (emitter, "EMITTER_FIXTURE PASS checks=")):
                    result = command([exe], env=run_env)
                    if not result.stdout.startswith(marker):
                        raise RuntimeError(f"missing {marker!r}: {result.stdout!r}")
                    if label == "san" and result.stderr:
                        raise RuntimeError(f"sanitizer test wrote stderr: {result.stderr}")
                    entry["runs"].append({"test": exe.name, "iteration": iteration,
                                          "stdout": result.stdout.strip(),
                                          "stderr": result.stderr.strip()})
                barrier = command([emitter, "--noexcept-barrier"], expected=86, env=run_env)
                if label == "san" and barrier.stderr:
                    raise RuntimeError(f"sanitizer barrier wrote stderr: {barrier.stderr}")
                entry["runs"].append({"test": "noexcept_barrier", "iteration": iteration,
                                      "exit": barrier.returncode, "stdout": barrier.stdout.strip(),
                                      "stderr": barrier.stderr.strip()})
                swallowed = command([emitter, "--swallow-barrier"], expected=87, env=run_env)
                if extra and swallowed.stderr:
                    raise RuntimeError(f"sanitizer swallow barrier wrote stderr: {swallowed.stderr}")
                entry["runs"].append({"test": "swallowed_transfer_reproducer", "iteration": iteration,
                                      "exit": swallowed.returncode})
            if args.bench and label == "O2":
                benchmark = build / ("benchmark" + suffix)
                benchcmd = [*common, str(HERE / "benchmark.cpp"), "-o", str(benchmark)]
                if windows:
                    benchcmd.append(str(import_lib))
                else:
                    benchcmd += ["-L" + str(build), "-lpgeh_bridge", "-Wl,-rpath,$ORIGIN"]
                command(benchcmd)
                entry["commands"].append(benchcmd)
                measured = command([benchmark], timeout=300)
                entry["benchmark"] = json.loads(measured.stdout)
            results["configurations"].append(entry)
            print(f"NATIVE_FIXTURE PASS compiler={Path(cxx).name} config={label} repeats={args.repeats}")
    report = out / "results.json"
    report.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"NATIVE_FIXTURE_MATRIX PASS configurations={len(results['configurations'])} results={report}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"NATIVE_FIXTURE FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
