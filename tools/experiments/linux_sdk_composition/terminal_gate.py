"""Narrow source transfer, 12 traced native terminal probes, and evidence audit.

Never runs Linux via Windows or executes commands read from evidence. The parent
traces only its own synthetic child and forwards each expected SIGSEGV unchanged.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import selectors
import shutil
import signal
import struct
import subprocess
import time
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SDK_PIN = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"
SIMDE_PIN = "71fd833d9666141edcd1d3c109a80e228303d8d7"
MODES = ("callback-failure", "repair-failure", "unhandled")
SOURCES = ["tools/experiments/linux_sdk_composition/" + n for n in (
    "sdk_composition.cpp", "terminal_modes.inl", "terminal_trace.h", "transport.c", "transport.h",
    "access.S", "CMakeLists.txt", "terminal_gate.py", "TERMINAL_GATE.md")]
SOURCES += ["tools/experiments/linux_guest_integration/record_bridge.h",
            "tools/experiments/linux_guest_fault/record_contract.h",
            "tools/experiments/portable_guest_eh/exception_core.h",
            "tools/experiments/portable_guest_eh/ppc_adapter.h"]
HEADERS = ["include/rex/" + n for n in ("system/xmemory.h", "system/mmio_handler.h",
    "exception_handler.h", "memory/utils.h", "thread/mutex.h", "ppc/context.h",
    "platform/fpscr.h", "ppc/func.h", "types.h", "platform.h", "assert.h")]
SDK_SOURCES = ["src/" + n for n in ("core/exception_handler_posix.cpp", "core/seh_posix.cpp",
    "system/mmio_handler.cpp", "system/xmemory.cpp", "core/memory_posix.cpp")]


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def lf(path):
    return path.read_bytes().replace(b"\r\n", b"\n")


def read_json(data):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, "duplicate JSON key")
            result[k] = v
        return result
    return json.loads(data, object_pairs_hook=unique)


def phase_lines(mode, token, stderr):
    """Exact wire contract, independent of the C++ witness state machine."""
    phases = {"callback-failure": ("injected", "caught", "terminal"),
              "repair-failure": ("claimed", "retry_fault", "terminal"),
              "unhandled": ("filter_search", "caught", "terminal")}
    require(mode in phases and re.fullmatch(r"[0-9a-f]{32}", token), "mode/token")
    rows = []
    pattern = (r"LSC_GATE_V1 token=([0-9a-f]{32}) mode=([a-z-]+) phase=([a-z_]+) "
               r"attempts=(\d+) faults=(\d+) callbacks=(\d+) invalidations=(\d+) "
               r"filters=(\d+) caught=(\d+) address=0x([0-9a-f]+)\n")
    offset = 0
    while offset < len(stderr):
        match = re.compile(pattern).match(stderr, offset)
        require(match is not None, "unexpected/partial trace bytes")
        tok, name, phase, *values = match.groups()
        i = len(rows)
        require(i < 3 and tok == token and name == mode and phase == phases[mode][i], "trace phase/identity")
        attempts, faults, callbacks, invalidations, filters, caught = map(int, values[:6])
        address = int(values[6], 16)
        expected = ((1, 1, 1, 1, 0, 0 if i == 0 else 1) if mode == "callback-failure" else
                    (1 if i == 0 else 2, 1 if i == 0 else 2, 1, 0, 0, 0) if mode == "repair-failure" else
                    (1, 1, 1, 0, 1, 0 if i == 0 else 1))
        require((attempts, faults, callbacks, invalidations, filters, caught) == expected, "trace counters")
        require(address != 0 and address % 4 == 0 and (not rows or address == rows[0]["address"]), "trace fault address")
        rows.append({"phase": phase, "address": address})
        offset = match.end()
    return rows


def check_stop(mode, token, events, stderr, child_pid):
    """Validate every kernel stop and its phase position, not just final death."""
    rows = phase_lines(mode, token, stderr)
    accerrs = 2 if mode == "repair-failure" else 1
    require(0 < len(events) <= accerrs + 1, "extra/missing SIGSEGV stop")
    current = events[-1]
    require(current["signal"] == 11, "unexpected signal")
    if len(events) <= accerrs:
        require(current["code"] == 2 and current["address"] > 0, "not a checked SEGV_ACCERR")
        require(len(rows) == (1 if len(events) == 2 else 0), "phase order at checked fault")
        require(all(e["code"] == 2 and e["address"] == events[0]["address"] for e in events), "checked address changed")
        if rows:
            require(rows[0]["address"] == current["address"], "kernel/ordinary address mismatch")
    else:
        require(current["code"] == -6 and current["sender_pid"] == child_pid, "terminal signal was not same-process SI_TKILL")
        require(len(rows) == 3 and all(e["code"] == 2 for e in events[:-1]), "terminal branch not witnessed")
        require(all(e["address"] == rows[0]["address"] for e in events[:-1]), "kernel/witness addresses differ")
    return len(rows)


def validate_run(run):
    require(run["status"] == "PASS", "failed probe record")
    require(run["returncode"] == -11 and run["stdout"] == "", "not real SIGSEGV termination/extra stdout")
    events = run["signals"]
    expected_count = 3 if run["mode"] == "repair-failure" else 2
    require(len(events) == expected_count, "signal sequence length")
    for i, event in enumerate(events):
        require(check_stop(run["mode"], run["token"], events[:i + 1], event["trace"], run["pid"]) == event["phases"], "phase snapshot")
    require(events[-1]["trace"] == run["stderr"] and len(phase_lines(run["mode"], run["token"], run["stderr"])) == 3,
            "trace changed after terminal delivery stop")


def traced_run(executable, mode, timeout=20, record=None):
    # Linux x86-64 siginfo_t ABI only. No reads/writes of tracee memory or registers.
    libc = ctypes.CDLL(None, use_errno=True)
    libc.ptrace.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    libc.ptrace.restype = ctypes.c_long
    def ptrace(request, pid=0, addr=None, data=None):
        result = libc.ptrace(request, pid, addr, data)
        if result == -1:
            code = ctypes.get_errno()
            raise OSError(code, "ptrace denied/failed; no security changes or untraced fallback permitted")
        return result
    def trace_me():
        try:
            ptrace(0)  # TRACEME, no pre-exec SIGSTOP (would deadlock Popen).
        except OSError as error:
            os.write(2, f"LSC_PTRACE_BLOCKED errno={error.errno}\n".encode("ascii"))
            os._exit(125)
    token = secrets.token_hex(16)
    env = os.environ.copy(); env["LSC_GATE_TOKEN"] = token
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    process, selector = None, None
    result = record if record is not None else {}
    result.update(mode=mode, token=token, signals=[], status="INCOMPLETE")
    deadline, exited = time.monotonic() + timeout, False
    def drain():
        for key in list(selector.get_map().values()):
            while True:
                try: data = os.read(key.fileobj.fileno(), 4096)
                except BlockingIOError: break
                if not data:
                    selector.unregister(key.fileobj); break
                buffers[key.data].extend(data)
                require(len(buffers[key.data]) <= 16384, "unexpected trace/output volume")
    def wait():
        while time.monotonic() < deadline:
            drain()
            pid, status = os.waitpid(process.pid, os.WNOHANG | os.WUNTRACED)
            if pid: return status
            selector.select(min(0.01, max(0, deadline - time.monotonic())))
        raise TimeoutError("synthetic terminal probe timed out")
    try:
        process = subprocess.Popen([str(executable), mode], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   preexec_fn=trace_me, env=env)
        result["pid"] = process.pid
        selector = selectors.DefaultSelector()
        for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
            os.set_blocking(pipe.fileno(), False); selector.register(pipe, selectors.EVENT_READ, name)
        status = wait(); drain()
        if os.WIFEXITED(status) or os.WIFSIGNALED(status):
            exited = True; process.returncode = os.waitstatus_to_exitcode(status)
            result["returncode"] = process.returncode
        require(os.WIFSTOPPED(status) and os.WSTOPSIG(status) == 5 and status >> 16 == 0,
                "missing initial exec SIGTRAP (tracing may be unsupported)")
        ptrace(0x4200, process.pid, data=ctypes.c_void_p(0x100000))  # SETOPTIONS EXITKILL.
        ptrace(7, process.pid)  # CONT.
        while True:
            status = wait(); drain()
            if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                exited = True; process.returncode = os.waitstatus_to_exitcode(status)
                drain(); result.update(returncode=process.returncode,
                    stdout=buffers["stdout"].decode(), stderr=buffers["stderr"].decode(), status="PASS")
                validate_run(result); return result
            require(os.WIFSTOPPED(status) and status >> 16 == 0 and os.WSTOPSIG(status) == 11, "unexpected ptrace stop/event")
            info = ctypes.create_string_buffer(128)
            ptrace(0x4202, process.pid, data=ctypes.cast(info, ctypes.c_void_p))  # GETSIGINFO.
            sig, error, code = struct.unpack_from("<iii", info.raw)
            event = {"signal": sig, "code": code, "errno": error,
                     "address": struct.unpack_from("<Q", info.raw, 16)[0] if code == 2 else 0,
                     "sender_pid": struct.unpack_from("<i", info.raw, 16)[0] if code == -6 else 0,
                     "trace": buffers["stderr"].decode()}
            result["signals"].append(event)
            event["phases"] = check_stop(mode, token, result["signals"], event["trace"], process.pid)
            require(not buffers["stdout"], "unexpected child stdout")
            ptrace(7, process.pid, data=ctypes.c_void_p(11))  # Forward exact SIGSEGV.
    except BaseException as error:
        result.update(status="FAIL", error=str(error), stdout=buffers["stdout"].decode(errors="replace"),
                      stderr=buffers["stderr"].decode(errors="replace"))
        raise
    finally:
        if process is not None and not exited:
            try: os.kill(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            cleanup_deadline = time.monotonic() + 5
            while time.monotonic() < cleanup_deadline:
                try: pid, status = os.waitpid(process.pid, os.WNOHANG | os.WUNTRACED)
                except ChildProcessError: break
                if pid and (os.WIFEXITED(status) or os.WIFSIGNALED(status)):
                    process.returncode = os.waitstatus_to_exitcode(status)
                    result["cleanup_returncode"] = process.returncode
                    break
                if pid and os.WIFSTOPPED(status):
                    try: ptrace(7, process.pid, data=ctypes.c_void_p(9))
                    except OSError: pass
                time.sleep(0.01)
            else:
                result["cleanup_error"] = "child did not reap after SIGKILL"
                raise RuntimeError(result["cleanup_error"])
        if selector is not None: selector.close()
        if process is not None:
            process.stdout.close(); process.stderr.close()


def command(argv, log):
    p = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=180)
    log.append({"argv": [str(a) for a in argv], "returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr})
    require(p.returncode == 0 and not p.stderr, "setup/build/inspection failed: " + str(argv))
    return p.stdout


def git(repo, *args, data=None):
    return subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(repo), *args], input=data,
                          capture_output=True, timeout=30, check=True).stdout


def pin_blobs(repo, revision, names):
    names = sorted(set(names))
    raw = git(repo, "cat-file", "--batch", data="".join(f"{revision}:{n}\n" for n in names).encode())
    offset, result = 0, {}
    for name in names:
        end = raw.index(b"\n", offset); header = raw[offset:end].split()
        require(len(header) == 3 and header[1] == b"blob", "missing pinned source: " + name)
        size = int(header[2]); offset = end + 1
        result[name] = raw[offset:offset + size].replace(b"\r\n", b"\n"); offset += size
        require(raw[offset:offset + 1] == b"\n", "Git blob framing"); offset += 1
    require(offset == len(raw), "Git batch inventory")
    return result


def source_identity():
    manifest = read_json((ROOT / "SOURCE_MANIFEST.json").read_bytes())
    require(set(manifest) == set(SOURCES) | {"IMPLEMENTATION_ID.json"}, "source transfer inventory")
    require(all(sha(lf(ROOT / p)) == h for p, h in manifest.items()), "source transfer hash mismatch")
    identity = read_json((ROOT / "IMPLEMENTATION_ID.json").read_bytes())
    require(re.fullmatch(r"[0-9a-f]{40}", identity["commit"]), "source commit identity")
    return manifest, identity


def sdk_identity(sdk, prefix):
    require(git(sdk, "rev-parse", "HEAD").decode().strip() == SDK_PIN, "SDK pin mismatch")
    simde = sdk / "thirdparty/simde"
    require(git(simde, "rev-parse", "HEAD").decode().strip() == SIMDE_PIN, "SIMDe pin mismatch")
    files = {}
    for n in HEADERS + SDK_SOURCES:
        expected = git(sdk, "show", SDK_PIN + ":" + n).replace(b"\r\n", b"\n")
        require(lf(sdk / n) == expected, "SDK source changed: " + n)
        if n in HEADERS: require(lf(prefix / n) == expected, "installed header differs: " + n)
        files[n] = sha(expected)
    simde_headers = {}
    names = [n for n in git(simde, "ls-tree", "-r", "--name-only", SIMDE_PIN, "--", "simde").decode().splitlines() if n.endswith(".h")]
    require(set(names) == {p.relative_to(simde).as_posix() for p in (simde / "simde").rglob("*.h")}, "SIMDe worktree inventory")
    for rel, expected in pin_blobs(simde, SIMDE_PIN, names).items():
        require(lf(simde / rel) == expected and lf(prefix / "include" / rel) == expected, "SIMDe header differs from pin")
        simde_headers[rel] = sha(expected)
    require(len(simde_headers) == 469, "SIMDe header inventory")
    libraries = {p.relative_to(prefix).as_posix(): sha(p.read_bytes())
        for d in (prefix / "lib", prefix / "bin") for p in sorted(d.rglob("*"))
        if p.is_file() and (p.suffix in (".so", ".a") or ".so." in p.name)}
    require(any("librexruntime.so" in n for n in libraries), "missing installed SDK runtime")
    return {"sdk": SDK_PIN, "simde": SIMDE_PIN, "sources_sha256_lf": files,
            "simde_sha256_lf": simde_headers, "libraries_sha256": libraries}


def artifact_paths(build, key):
    return {f"native/{key}/" + name: path for name, path in {
        "sdk_composition.elf": build / "sdk_composition",
        "transport.o": build / "CMakeFiles/sdk_composition.dir/transport.c.o",
        "access.o": build / "CMakeFiles/sdk_composition.dir/access.S.o",
        **{n: build / n for n in ("final.objdump.txt", "final.readelf.txt", "transport.objdump.txt", "access.objdump.txt")}}.items()}


def run_native(args):
    require(platform.system() == "Linux" and platform.machine() == "x86_64" and struct.calcsize("P") == 8,
            "native Linux x86-64 required; no Windows/WSL execution fallback")
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    sdk, prefix = args.sdk.resolve(), args.prefix.resolve()
    result = {"status": "INCOMPLETE", "platform": platform.platform(), "machine": platform.machine(),
              "scope": "12 ptrace-supervised fixture-only terminal probes; no performance/sanitizer claim",
              "configurations": []}
    try:
        manifest, identity = source_identity()
        result.update(identity=identity, source_manifest=manifest)
        sdk_info = sdk_identity(sdk, prefix); result["sdk_identity"] = sdk_info
        for cxx_name, cc_name in (("clang++", "clang"), ("g++", "gcc")):
            cxx, cc = shutil.which(cxx_name), shutil.which(cc_name)
            require(cxx and cc, "missing Clang/GCC compiler pair")
            for opt in ("0", "2"):
                key = cxx_name + "_O" + opt; build = out / key
                row = {"key": key, "status": "INCOMPLETE", "commands": [], "runs": []}
                result["configurations"].append(row); log = row["commands"]
                row["cxx_version"] = command([cxx, "--version"], log)
                row["cc_version"] = command([cc, "--version"], log)
                command(["cmake", "-S", HERE, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                    "-DCMAKE_PREFIX_PATH=" + str(prefix), "-DCMAKE_CXX_COMPILER=" + cxx, "-DCMAKE_C_COMPILER=" + cc,
                    "-DCMAKE_ASM_COMPILER=" + cc, "-DPROBE_OPT=" + opt, "-DORDINARY_ONLY=OFF", "-DTERMINAL_DIAGNOSTICS=ON"], log)
                command(["cmake", "--build", build, "--verbose"], log)
                executable = build / "sdk_composition"; before = sha(executable.read_bytes())
                row["executable_sha256"] = before
                for mode in MODES:
                    record = {"mode": mode, "status": "INCOMPLETE"}; row["runs"].append(record)
                    traced_run(executable, mode, record=record)
                require(sha(executable.read_bytes()) == before, "executable changed during probes")
                for tool, flags, path, target in (
                    ("objdump", ["-drwC"], build / "final.objdump.txt", executable),
                    ("readelf", ["-Wh", "-Wr", "-Ws", "-Wl", "-Wd"], build / "final.readelf.txt", executable),
                    ("objdump", ["-drwC"], build / "transport.objdump.txt", build / "CMakeFiles/sdk_composition.dir/transport.c.o"),
                    ("objdump", ["-drwC"], build / "access.objdump.txt", build / "CMakeFiles/sdk_composition.dir/access.S.o")):
                    path.write_text(command([tool, *flags, target], log), encoding="utf-8")
                row["artifacts"] = {n: sha(p.read_bytes()) for n, p in artifact_paths(build, key).items()}
                require(row["artifacts"][f"native/{key}/sdk_composition.elf"] == before, "executable changed during inspection")
                row["status"] = "PASS"
        require(sdk_identity(sdk, prefix) == sdk_info, "SDK installation changed during probes")
        require(source_identity() == (manifest, identity), "source changed during probes")
        result["status"] = "PASS"
    except BaseException as error:
        result["error"] = str(error)
        raise
    finally:
        (out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("TERMINAL_GATE PASS configurations=4 subprocesses=12; independent audit still required")


def write_zip(path, entries):
    require("EVIDENCE_SHA256.json" not in entries, "reserved archive entry")
    manifest = {n: sha(v) for n, v in sorted(entries.items())}
    entries = dict(entries); entries["EVIDENCE_SHA256.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in sorted(entries.items()): z.writestr(n, data)
    with zipfile.ZipFile(path) as z:
        require(z.testzip() is None and set(z.namelist()) == set(entries) and len(z.namelist()) == len(entries), "ZIP inventory/CRC")
        require(all(z.read(n) == v for n, v in entries.items()), "ZIP content changed")
    print(json.dumps({"zip": str(path.resolve()), "files": len(entries), "sha256": sha(path.read_bytes()), "archive_integrity": "PASS"}, indent=2))


def package_source(path):
    revision = git(ROOT, "rev-parse", "HEAD").decode().strip()
    entries = {n: lf(ROOT / n) for n in SOURCES}
    require(all(git(ROOT, "show", revision + ":" + n).replace(b"\r\n", b"\n") == data
                for n, data in entries.items()), "commit the intended source files before packaging")
    entries["IMPLEMENTATION_ID.json"] = (json.dumps({"commit": revision, "baseline": "6f81aa7",
        "scope": "fixture-only terminal diagnostics; native validation pending"}, indent=2) + "\n").encode()
    entries["SOURCE_MANIFEST.json"] = (json.dumps({n: sha(v) for n, v in sorted(entries.items())}, indent=2) + "\n").encode()
    write_zip(path, entries)


def package_evidence(out, path, failure=False):
    result = read_json((out / "results.json").read_bytes())
    if failure:
        require(result["status"] != "PASS", "use normal evidence packaging for successful runs")
        entries = {"FAILED_RESULTS.json": (out / "results.json").read_bytes(),
                   "FAILURE_NOTICE.txt": b"INCOMPLETE diagnostic run; no terminal gate PASS. Do not change system security.\n"}
        if (out / "console.log").is_file(): entries["console.log"] = (out / "console.log").read_bytes()
        write_zip(path, entries); return
    validate_results(result)
    manifest, identity = source_identity()
    require(result["source_manifest"] == manifest and result["identity"] == identity, "source identity changed since probes")
    entries = {"results.json": (out / "results.json").read_bytes(),
               "SOURCE_MANIFEST.json": (ROOT / "SOURCE_MANIFEST.json").read_bytes(),
               "IMPLEMENTATION_ID.json": (ROOT / "IMPLEMENTATION_ID.json").read_bytes()}
    for row in result["configurations"]:
        for name, file in artifact_paths(out / row["key"], row["key"]).items():
            data = file.read_bytes(); require(sha(data) == row["artifacts"][name], "artifact changed")
            entries[name] = data
    write_zip(path, entries)


def validate_results(result):
    require(result["status"] == "PASS" and len(result["configurations"]) == 4, "incomplete terminal evidence")
    require(result["platform"].startswith("Linux") and result["machine"] == "x86_64", "not native Linux evidence")
    seen, seen_tokens = set(), set()
    for row in result["configurations"]:
        require(row["key"] in {c + "_" + o for c in ("clang++", "g++") for o in ("O0", "O2")} and row["key"] not in seen,
                "configuration inventory")
        seen.add(row["key"]); require(row["status"] == "PASS", "configuration failure")
        require([r["mode"] for r in row["runs"]] == list(MODES), "exact three-mode scope")
        for run in row["runs"]:
            validate_run(run); require(run["token"] not in seen_tokens, "run token reused"); seen_tokens.add(run["token"])
        require(all(c["returncode"] == 0 and not c["stderr"] for c in row["commands"]), "build/inspection failed")
        require("clang" in row["cxx_version"].lower() if row["key"].startswith("clang") else
                "gcc" in row["cxx_version"].lower(), "compiler family")
        require("clang" in row["cc_version"].lower() if row["key"].startswith("clang") else
                "gcc" in row["cc_version"].lower(), "C compiler family")
        versions = [c for c in row["commands"] if c["argv"][1:] == ["--version"]]
        require(len(versions) == 2 and versions[0]["stdout"] == row["cxx_version"] and
                versions[1]["stdout"] == row["cc_version"], "compiler version records")
        builds = [c for c in row["commands"] if c["argv"][:2] == ["cmake", "--build"]]
        require(len(builds) == 1, "build command inventory")
        lines = [line for line in builds[0]["stdout"].splitlines() if " -c " in line]
        require(len(lines) == 3 and {line.split(" -c ")[-1].split("/")[-1] for line in lines} ==
                {"sdk_composition.cpp", "transport.c", "access.S"}, "diagnostic compile inputs")
        for line in lines:
            tokens = line.split()
            source = line.split(" -c ")[-1].split("/")[-1]
            expected_driver = versions[0 if source == "sdk_composition.cpp" else 1]["argv"][0]
            require(tokens[1] == expected_driver, "build driver differs from recorded compiler")
            require(all(t in tokens for t in ("-DLSC_TERMINAL_DIAGNOSTICS", "-Wall", "-Wextra", "-Werror")) and
                    not any(t == "-w" or t.startswith(("-Wno-", "-flto")) for t in tokens), "strict diagnostic build flags")
            opts = [t for t in tokens if re.fullmatch(r"-O[0123gs]", t)]
            require(opts and opts[-1] == "-" + row["key"].split("_")[-1], "effective optimization")


def audit_evidence(archive, implementation, sdk):
    require(re.fullmatch(r"[0-9a-f]{40}", implementation), "expected full implementation commit required")
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) and z.testzip() is None, "ZIP CRC/duplicates")
        data = {n: z.read(n) for n in names}
    manifest = read_json(data["EVIDENCE_SHA256.json"])
    require(set(manifest) == set(data) - {"EVIDENCE_SHA256.json"} and
            all(sha(data[n]) == h for n, h in manifest.items()), "evidence hash/inventory")
    if "FAILED_RESULTS.json" in data:
        return {"status": "INCOMPLETE", "failure": read_json(data["FAILED_RESULTS.json"])}
    result = read_json(data["results.json"]); validate_results(result)
    source_manifest = read_json(data["SOURCE_MANIFEST.json"])
    identity = read_json(data["IMPLEMENTATION_ID.json"])
    require(identity == result["identity"] and identity["commit"] == implementation and
            identity["baseline"] == "6f81aa7", "implementation identity")
    require(source_manifest == result["source_manifest"] and set(source_manifest) == set(SOURCES) | {"IMPLEMENTATION_ID.json"}, "source manifest inventory")
    require(sha(data["IMPLEMENTATION_ID.json"]) == source_manifest["IMPLEMENTATION_ID.json"], "implementation metadata hash")
    require({n: sha(v) for n, v in pin_blobs(ROOT, implementation, SOURCES).items()} ==
            {n: h for n, h in source_manifest.items() if n in SOURCES}, "source differs from expected Git commit")
    info = result["sdk_identity"]
    require(info["sdk"] == SDK_PIN and info["simde"] == SIMDE_PIN and
            set(info["sources_sha256_lf"]) == set(HEADERS + SDK_SOURCES), "SDK identity")
    require({n: sha(v) for n, v in pin_blobs(sdk, SDK_PIN, HEADERS + SDK_SOURCES).items()} == info["sources_sha256_lf"], "SDK source hashes")
    simde_names = {n for n in git(sdk / "thirdparty/simde", "ls-tree", "-r", "--name-only", SIMDE_PIN, "--", "simde").decode().splitlines() if n.endswith(".h")}
    require(set(info["simde_sha256_lf"]) == simde_names and len(simde_names) == 469 and
            {n: sha(v) for n, v in pin_blobs(sdk / "thirdparty/simde", SIMDE_PIN, simde_names).items()} == info["simde_sha256_lf"], "SIMDe source hashes")
    require(any("librexruntime.so" in n for n in info["libraries_sha256"]) and
            all(re.fullmatch(r"[0-9a-f]{64}", h) for h in info["libraries_sha256"].values()), "recorded SDK runtime/library digests")
    expected = {"results.json", "SOURCE_MANIFEST.json", "IMPLEMENTATION_ID.json", "EVIDENCE_SHA256.json"}
    for row in result["configurations"]:
        paths = set(artifact_paths(Path("unused"), row["key"]))
        require(set(row["artifacts"]) == paths, "compiled artifact inventory")
        for name in paths:
            require(name in data and sha(data[name]) == row["artifacts"][name], "artifact content hash")
            expected.add(name)
            if name.endswith((".elf", ".o")):
                require(len(data[name]) >= 20 and data[name][:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<H", data[name], 18)[0] == 62,
                        "non-x86-64 ELF artifact")
                require(struct.unpack_from("<H", data[name], 16)[0] in ((2, 3) if name.endswith(".elf") else (1,)),
                        "ELF executable/object type mismatch")
        executable = f"native/{row['key']}/sdk_composition.elf"
        require(sha(data[executable]) == row["executable_sha256"], "executable digest association")
        for filename, tool, suffix in (("final.objdump.txt", "objdump", "/sdk_composition"),
                                      ("final.readelf.txt", "readelf", "/sdk_composition"),
                                      ("transport.objdump.txt", "objdump", "/transport.c.o"),
                                      ("access.objdump.txt", "objdump", "/access.S.o")):
            records = [c for c in row["commands"] if c["argv"][0] == tool and c["argv"][-1].endswith(suffix)]
            require(len(records) == 1 and records[0]["stdout"].encode() == data[f"native/{row['key']}/{filename}"],
                    "inspection text differs from recorded command")
    require(set(data) == expected, "unexpected evidence artifact (SDK libraries/game data forbidden)")
    return {"status": "PASS", "scope": "record/source/ELF-byte integrity; manual machine-code and branch review still required",
            "implementation": implementation, "configurations": 4, "subprocesses": 12,
            "zip_sha256": sha(archive.read_bytes()), "note": "SDK library bytes absent; recorded digests only; ptrace evidence is not a performance or sanitizer result"}


def main():
    ap = argparse.ArgumentParser(description=__doc__); sub = ap.add_subparsers(dest="action", required=True)
    src = sub.add_parser("source"); src.add_argument("--zip", type=Path, default=ROOT / "private/work/linux_sdk_composition/terminal-gate-source.zip")
    run = sub.add_parser("run"); run.add_argument("--sdk", required=True, type=Path); run.add_argument("--prefix", required=True, type=Path)
    run.add_argument("--out", type=Path, default=ROOT / "private/work/linux_sdk_composition/terminal_gate")
    evidence = sub.add_parser("evidence"); evidence.add_argument("--out", required=True, type=Path); evidence.add_argument("--zip", required=True, type=Path)
    evidence.add_argument("--failure", action="store_true", help="package INCOMPLETE results, never a gate PASS")
    audit = sub.add_parser("audit"); audit.add_argument("--archive", required=True, type=Path)
    audit.add_argument("--implementation", required=True); audit.add_argument("--sdk", type=Path, default=ROOT / "external/rexglue-sdk")
    args = ap.parse_args()
    if args.action == "source": package_source(args.zip)
    elif args.action == "run": run_native(args)
    elif args.action == "evidence": package_evidence(args.out.resolve(), args.zip, args.failure)
    else:
        result = audit_evidence(args.archive.resolve(), args.implementation, args.sdk.resolve())
        print(json.dumps(result, indent=2))
        if result["status"] != "PASS": raise SystemExit(1)


if __name__ == "__main__":
    main()
