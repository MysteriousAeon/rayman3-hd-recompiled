"""Build and run the isolated Linux signal-lifecycle fixture only."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCES = ("transport.h", "transport.c", "access.S", "lifecycle.c", "run_lifecycle.py")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(argv, log, expected=0, marker=None, output_file=None):
    start = time.monotonic()
    p = subprocess.run([str(x) for x in argv], capture_output=True, text=True, timeout=60)
    item = {"command": [str(x) for x in argv], "returncode": p.returncode,
            "expected": expected, "elapsed_seconds": time.monotonic() - start,
            "stderr": p.stderr}
    if output_file is None:
        item["stdout"] = p.stdout
    else:
        output_file.write_text(p.stdout, encoding="utf-8")
        item["output_file"] = str(output_file)
        item["output_sha256"] = digest(output_file)
    log.append(item)
    if p.returncode != expected or p.stderr or (marker and marker not in p.stdout):
        raise RuntimeError(f"unexpected result: {argv!r}\n{p.stdout}\n{p.stderr}")
    return p.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", action="append", help="repeat for Clang and GCC")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--sanitize", action="store_true", help="ordinary lifecycle rejection only")
    parser.add_argument("--bench", action="store_true", help="unsanitized O2 synthetic batch costs")
    parser.add_argument("--out", type=Path, default=ROOT / "private/work/linux_sdk_composition/lifecycle")
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64" or args.repeats < 1:
        parser.error("Linux x86-64 and positive repetitions required")
    if args.bench and args.sanitize:
        parser.error("benchmark only unsanitized builds")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = {"status": "INCOMPLETE", "platform": platform.platform(), "machine": platform.machine(),
              "scope": "ordinary rejection only; no signal ownership or fault recovery" if args.sanitize
                       else "native lifecycle and controlled exact read/write",
              "sanitizers": "address,undefined" if args.sanitize else "none",
              "sources_sha256": {name: digest(HERE / name) for name in SOURCES}, "configurations": []}
    try:
        for compiler in args.cc or ["clang", "gcc"]:
            cc = shutil.which(compiler)
            if not cc:
                raise RuntimeError(f"missing compiler {compiler}")
            for opt in ("0", "2"):
                build = out / (Path(cc).name + "_O" + opt)
                build.mkdir(parents=True, exist_ok=True)
                row = {"compiler": cc, "optimization": "O" + opt, "commands": [], "status": "INCOMPLETE"}
                result["configurations"].append(row)
                log = row["commands"]
                row["version"] = call([cc, "--version"], log)
                flags = ["-std=gnu11", "-O" + opt, "-Wall", "-Wextra", "-Werror", "-pthread", "-DLSC_TEST"]
                if args.sanitize:
                    flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer"]
                transport = build / "transport.o"
                access = build / "access.o"
                exe = build / "lifecycle"
                call([cc, *flags, "-c", HERE / "transport.c", "-o", transport], log)
                call([cc, "-DLSC_TEST", "-c", HERE / "access.S", "-o", access], log)
                call([cc, *flags, HERE / "lifecycle.c", transport, access, "-o", exe], log)
                row["executable_sha256"] = digest(exe)
                row["transport_object_sha256"] = digest(transport)
                modes = ("ordinary",) if args.sanitize else ("ordinary", "normal", "conflicts", "replaced")
                for _ in range(args.repeats):
                    for mode in modes:
                        call([exe, mode], log, marker=f"LSC_LIFECYCLE PASS mode={mode} ")
                    if not args.sanitize:
                        for mode in ("host-null", "host-outside", "unarmed", "wrong-site", "reentrant", "terminal"):
                            call([exe, mode], log, expected=-signal.SIGSEGV)
                if not args.sanitize:
                    if args.bench and opt == "2":
                        row["benchmarks"] = [call([exe, "benchmark"], log,
                            marker="LSC_LIFECYCLE PASS mode=benchmark ") for _ in range(args.repeats)]
                    for tool in ("objdump", "readelf"):
                        if not shutil.which(tool):
                            raise RuntimeError(f"missing {tool} for required machine-code audit")
                    call(["objdump", "-drwC", transport], log, output_file=build / "transport.objdump.txt")
                    call(["objdump", "-drwC", exe], log, output_file=build / "lifecycle.objdump.txt")
                    call(["readelf", "-rWs", transport], log, output_file=build / "transport.readelf.txt")
                    call(["readelf", "-rWsl", exe], log, output_file=build / "lifecycle.readelf.txt")
                row["status"] = "PASS"
        result["status"] = "PASS"
    finally:
        (out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"LSC_LIFECYCLE_MATRIX PASS configurations={len(result['configurations'])} scope={result['scope']}")


if __name__ == "__main__":
    main()
