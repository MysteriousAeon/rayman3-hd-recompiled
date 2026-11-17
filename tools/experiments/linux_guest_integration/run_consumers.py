"""Build only the isolated SDK consumer fixture against an existing SDK installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SDK_PIN = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"
SIMDE_PIN = "71fd833d9666141edcd1d3c109a80e228303d8d7"
HEADERS = ["include/rex/system/mmio_handler.h", "include/rex/exception_handler.h",
           "include/rex/memory/utils.h", "include/rex/thread/mutex.h", "include/rex/types.h",
           "include/rex/platform.h", "include/rex/assert.h", "include/rex/ppc/context.h",
           "include/rex/platform/fpscr.h", "include/rex/ppc/func.h"]
SOURCES = ["src/system/mmio_handler.cpp", "src/core/exception_handler_posix.cpp",
           "src/core/exception_handler_win.cpp", "src/core/memory_posix.cpp",
           "src/core/memory_win.cpp"]


def sha(path, canonical=True):
    data = path.read_bytes()
    if canonical:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def invoke(argv, log, marker=None, env=None):
    p = subprocess.run([str(x) for x in argv], capture_output=True, text=True, timeout=180, env=env)
    log.append({"command": [str(x) for x in argv], "returncode": p.returncode,
                "stdout": p.stdout, "stderr": p.stderr})
    if p.returncode or (marker and (marker not in p.stdout or p.stderr)):
        raise RuntimeError(f"command failed: {argv}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=ROOT / "external/rexglue-sdk")
    parser.add_argument("--prefix", required=True, type=Path, help="existing installed SDK prefix")
    parser.add_argument("--out", type=Path, default=ROOT / "private/work/linux_guest_integration/sdk_consumers")
    parser.add_argument("--cxx", action="append")
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("positive repetitions required")
    sdk, prefix, out = args.sdk.resolve(), args.prefix.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = {"status": "INCOMPLETE", "scope": "ordinary SDK callback boundary; no signal integration",
              "platform": platform.platform(), "machine": platform.machine(),
              "sdk": str(sdk), "prefix": str(prefix), "commands": [], "configurations": []}
    log = result["commands"]
    try:
        head = invoke(["git", "-C", sdk, "rev-parse", "HEAD"], log).strip()
        simde = invoke(["git", "-C", sdk / "thirdparty/simde", "rev-parse", "HEAD"], log).strip()
        if head != SDK_PIN or simde != SIMDE_PIN:
            raise RuntimeError(f"SDK/SIMDe pin mismatch: {head} / {simde}")
        if invoke(["git", "-C", sdk / "thirdparty/simde", "status", "--porcelain",
                   "--untracked-files=all", "--", "simde"], log):
            raise RuntimeError("SIMDe source headers differ from the pin")
        simde_headers = sorted((sdk / "thirdparty/simde/simde").rglob("*.h"))
        if not simde_headers:
            raise RuntimeError("missing pinned SIMDe headers")
        installed_simde = {}
        for path in simde_headers:
            relative = path.relative_to(sdk / "thirdparty/simde")
            installed = prefix / "include" / relative
            expected = sha(path)
            if not installed.is_file() or sha(installed) != expected:
                raise RuntimeError(f"installed SIMDe header mismatch: {relative}")
            installed_simde[relative.as_posix()] = expected
        result["installed_simde_header_sha256_lf"] = installed_simde
        invoke(["git", "-C", sdk, "diff", "--quiet", "HEAD", "--", *HEADERS, *SOURCES], log)
        result["sdk_commit"], result["simde_commit"] = head, simde
        result["sdk_source_sha256_lf"] = {s: sha(sdk / s) for s in HEADERS + SOURCES}
        result["installed_header_sha256_lf"] = {s: sha(prefix / s) for s in HEADERS}
        if any(result["sdk_source_sha256_lf"][s] != result["installed_header_sha256_lf"][s]
               for s in HEADERS):
            raise RuntimeError("installed SDK consumer headers differ from pinned source")
        libs = sorted(path for directory in (prefix / "lib", prefix / "bin")
                      for path in directory.glob("*")
                      if path.is_file() and "rexruntime" in path.name.lower())
        if not libs:
            raise RuntimeError("no installed rexruntime library found under prefix/lib")
        result["installed_runtime_sha256"] = {p.relative_to(prefix).as_posix(): sha(p, False) for p in libs}
        closure = [HERE / "sdk_consumers.cpp", HERE / "CMakeLists.txt", Path(__file__),
                   HERE / "record_bridge.h", HERE.parent / "portable_guest_eh/exception_core.h",
                   HERE.parent / "portable_guest_eh/ppc_adapter.h", HERE.parent / "linux_guest_fault/record_contract.h"]
        result["fixture_sha256_lf"] = {p.relative_to(ROOT).as_posix(): sha(p) for p in closure}
        invoke(["cmake", "--version"], log)
        for cxx in args.cxx or (["clang++"] if platform.system() == "Windows" else ["clang++", "g++"]):
            compiler = shutil.which(cxx)
            if not compiler:
                raise RuntimeError(f"missing compiler: {cxx}")
            version = invoke([compiler, "--version"], log).strip()
            for opt in ("0", "2"):
                build = out / (Path(compiler).stem + "_O" + opt)
                entry = {"compiler": compiler, "version": version, "optimization": "O" + opt,
                         "commands": [], "status": "INCOMPLETE"}
                result["configurations"].append(entry)
                commands = entry["commands"]
                invoke(["cmake", "-S", HERE, "-B", build, "-G", "Ninja",
                        "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=" + str(prefix),
                        "-DCMAKE_CXX_COMPILER=" + str(compiler), "-DPROBE_OPT=" + opt], commands)
                invoke(["cmake", "--build", build, "--verbose"], commands)
                exe = build / ("sdk_consumers.exe" if platform.system() == "Windows" else "sdk_consumers")
                entry["executable_sha256"] = sha(exe, False)
                run_env = os.environ.copy()
                if platform.system() == "Windows":
                    run_env["PATH"] = str(prefix / "bin") + os.pathsep + run_env.get("PATH", "")
                    entry["runtime_search_prefix"] = str(prefix / "bin")
                for _ in range(args.repeats):
                    invoke([exe], commands, "SDK_CONSUMERS PASS checks=", run_env)
                entry["status"] = "PASS"
        result["status"] = "PASS"
    finally:
        (out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"SDK_CONSUMER_MATRIX PASS configurations={len(result['configurations'])}")


if __name__ == "__main__":
    main()
