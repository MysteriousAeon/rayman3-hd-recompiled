"""Build only the SDK composition fixture against an existing installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SDK_PIN = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"
SIMDE_PIN = "71fd833d9666141edcd1d3c109a80e228303d8d7"
HEADERS = ["include/rex/system/xmemory.h", "include/rex/system/mmio_handler.h",
           "include/rex/exception_handler.h", "include/rex/memory/utils.h",
           "include/rex/thread/mutex.h", "include/rex/ppc/context.h",
           "include/rex/platform/fpscr.h", "include/rex/ppc/func.h",
           "include/rex/types.h", "include/rex/platform.h", "include/rex/assert.h"]
SOURCES = ["src/core/exception_handler_posix.cpp", "src/core/seh_posix.cpp",
           "src/system/mmio_handler.cpp", "src/system/xmemory.cpp", "src/core/memory_posix.cpp",
           "src/core/exception_handler_win.cpp", "src/core/memory_win.cpp"]


def sha(path, canonical=True):
    data = path.read_bytes()
    return hashlib.sha256(data.replace(b"\r\n", b"\n") if canonical else data).hexdigest()


def invoke(argv, log, expected=0, marker=None, env=None):
    start = time.monotonic()
    p = subprocess.run([str(x) for x in argv], capture_output=True, text=True,
                       timeout=180, env=env)
    log.append({"command": [str(x) for x in argv], "returncode": p.returncode,
                "expected": expected, "stdout": p.stdout, "stderr": p.stderr,
                "seconds": time.monotonic() - start})
    if p.returncode != expected or p.stderr or (marker and marker not in p.stdout):
        raise RuntimeError(f"unexpected result: {argv}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sdk", type=Path, default=ROOT / "external/rexglue-sdk")
    ap.add_argument("--prefix", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "private/work/linux_sdk_composition/sdk")
    ap.add_argument("--cxx", action="append")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--ordinary-only", action="store_true")
    ap.add_argument("--bench", action="store_true", help="O2 ordinary SDK batch costs")
    args = ap.parse_args()
    linux = platform.system() == "Linux" and platform.machine().lower() == "x86_64"
    if args.repeats < 1 or (not linux and not args.ordinary_only):
        ap.error("positive repetitions; native mode requires Linux x86-64")
    sdk, prefix, out = args.sdk.resolve(), args.prefix.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = {"status": "INCOMPLETE", "platform": platform.platform(), "machine": platform.machine(),
              "scope": "ordinary components" if args.ordinary_only else "native deferred components",
              "sanitizers": "none; SDK Install signal ownership conflicts with ASan",
              "commands": [], "configurations": []}
    log = result["commands"]
    try:
        for path, expected in ((sdk, SDK_PIN), (sdk / "thirdparty/simde", SIMDE_PIN)):
            if invoke(["git", "-C", path, "rev-parse", "HEAD"], log).strip() != expected:
                raise RuntimeError(f"pin mismatch: {path}")
        invoke(["git", "-C", sdk, "diff", "--exit-code", "HEAD", "--", *HEADERS, *SOURCES], log)
        # Compare actual bytes too: index assume-unchanged/skip-worktree flags
        # must not hide a modified source from the fixture's provenance gate.
        for name in HEADERS + SOURCES:
            blob = subprocess.run(["git", "-C", str(sdk), "show", "HEAD:" + name],
                                  capture_output=True, timeout=30, check=True).stdout
            if blob.replace(b"\r\n", b"\n") != (sdk / name).read_bytes().replace(b"\r\n", b"\n"):
                raise RuntimeError(f"working SDK content differs from pin: {name}")
        if invoke(["git", "-C", sdk / "thirdparty/simde", "status", "--porcelain",
                   "--untracked-files=all", "--", "simde"], log):
            raise RuntimeError("SIMDe headers differ from pin")
        result["sdk_commit"], result["simde_commit"] = SDK_PIN, SIMDE_PIN
        result["sdk_sources_sha256_lf"] = {p: sha(sdk / p) for p in HEADERS + SOURCES}
        for name in HEADERS:
            if sha(prefix / name) != sha(sdk / name):
                raise RuntimeError(f"installed header differs: {name}")
        simde_headers = sorted((sdk / "thirdparty/simde/simde").rglob("*.h"))
        if not simde_headers:
            raise RuntimeError("missing SIMDe headers")
        for path in simde_headers:
            rel = path.relative_to(sdk / "thirdparty/simde")
            if sha(prefix / "include" / rel) != sha(path):
                raise RuntimeError(f"installed SIMDe differs: {rel}")
        result["simde_headers_sha256_lf"] = {
            p.relative_to(sdk / "thirdparty/simde").as_posix(): sha(p) for p in simde_headers}
        # Hash all libraries in the supplied prefix, including static transitive components.
        libs = sorted(p for d in (prefix / "lib", prefix / "bin") for p in d.rglob("*")
                      if p.is_file() and (p.suffix in (".a", ".so", ".dll", ".lib") or ".so." in p.name))
        if not libs:
            raise RuntimeError("no installed SDK libraries; no SDK build is attempted")
        result["installed_libraries_sha256"] = {p.relative_to(prefix).as_posix(): sha(p, False) for p in libs}
        result["sources_sha256_lf"] = {
            p.relative_to(ROOT).as_posix(): sha(p)
            for dirname in ("portable_guest_eh", "linux_guest_fault", "linux_guest_integration", "linux_sdk_composition")
            for p in sorted((HERE.parent / dirname).iterdir())
            if p.is_file() and (p.suffix in (".h", ".cpp", ".c", ".S", ".py", ".md") or p.name == "CMakeLists.txt")}
        for name in args.cxx or (["clang++", "g++"] if linux else ["clang++"]):
            compiler = shutil.which(name)
            if not compiler:
                raise RuntimeError(f"compiler missing: {name}")
            version = invoke([compiler, "--version"], log)
            for opt in ("0", "2"):
                build = out / (Path(compiler).stem + "_O" + opt)
                row = {"compiler": compiler, "version": version, "optimization": "O" + opt,
                       "status": "INCOMPLETE", "commands": []}
                result["configurations"].append(row)
                calls = row["commands"]
                configure = ["cmake", "-S", HERE, "-B", build, "-G", "Ninja",
                             "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_PREFIX_PATH=" + str(prefix),
                             "-DCMAKE_CXX_COMPILER=" + compiler, "-DPROBE_OPT=" + opt,
                             "-DORDINARY_ONLY=" + ("ON" if args.ordinary_only else "OFF")]
                # Require paired compiler families for the C signal transport.
                cc = shutil.which("clang" if "clang" in version.lower() else "gcc")
                if not cc:
                    raise RuntimeError("paired C compiler missing")
                configure += ["-DCMAKE_C_COMPILER=" + cc, "-DCMAKE_ASM_COMPILER=" + cc]
                invoke(configure, calls)
                invoke(["cmake", "--build", build, "--verbose"], calls)
                exe = build / ("sdk_composition.exe" if platform.system() == "Windows" else "sdk_composition")
                row["executable_sha256"] = sha(exe, False)
                env = os.environ.copy()
                if platform.system() == "Windows":
                    env["PATH"] = str(prefix / "bin") + os.pathsep + env.get("PATH", "")
                for _ in range(args.repeats):
                    invoke([exe, "normal"], calls, marker="SDK_COMPOSITION PASS", env=env)
                    if not args.ordinary_only:
                        for mode in ("callback-failure", "unhandled", "repair-failure"):
                            invoke([exe, mode], calls, expected=-signal.SIGSEGV, env=env)
                if linux and not args.ordinary_only:
                    for tool, flags, suffix in (("objdump", ["-drwC"], "disassembly.txt"),
                                                 ("readelf", ["-Wr", "-Ws", "-Wl"], "elf.txt")):
                        output = invoke([tool, *flags, exe], calls)
                        (build / suffix).write_text(output, encoding="utf-8")
                    row["inspection"] = "PENDING manual final ELF/TLS/handler review; raw dumps supplied"
                if args.bench and opt == "2":
                    row["benchmarks"] = [invoke([exe, "benchmark"], calls,
                        marker="SDK_COMPOSITION PASS", env=env) for _ in range(args.repeats)]
                row["status"] = "PASS"
        result["status"] = "PASS"
    finally:
        (out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"SDK_COMPOSITION_MATRIX PASS configurations={len(result['configurations'])} scope={result['scope']}")


if __name__ == "__main__":
    main()
