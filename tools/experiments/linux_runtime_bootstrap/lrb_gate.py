"""Linux Runtime Bootstrap (LRB) source transfer, native gate, evidence and audit.

Subcommands:
  source    (Windows/any) write the source-only CachyOS ZIP from committed Git bytes.
  run       (Linux x86-64 only) build Clang/GCC O0/O2 and run the full LRB matrix.
  evidence  (Linux) package results, own ELF/object bytes and dumps into one ZIP.
  audit     (Windows/any, read-only) validate a returned evidence ZIP.

Never builds, patches or installs the SDK; never launches the game; never reads
or writes child memory/registers; removes only /dev/shm objects proven (by name,
inode, device and uid) to have been created by its own reaped child.
"""
import argparse
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import secrets
import selectors
import shutil
import signal
import stat
import struct
import subprocess
import sys
import time
import traceback
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REL = "tools/experiments/linux_runtime_bootstrap/"
SDK_PIN = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"
SIMDE_PIN = "71fd833d9666141edcd1d3c109a80e228303d8d7"
SOURCE_ZIP = ROOT / "private/work/linux_runtime_bootstrap/lrb-cachyos-source.zip"
OWN_FILES = ["CMakeLists.txt", "README.md", "lrb_access.S", "lrb_bootstrap.cpp", "lrb_bootstrap.h",
             "lrb_gate.py", "lrb_owner.c", "lrb_owner.h", "lrb_tests.cpp", "test_lrb_gate.py"]
PRIOR_DIRS = ["portable_guest_eh", "linux_guest_fault", "linux_guest_integration", "linux_sdk_composition"]
PRIOR_SUFFIXES = {".h", ".cpp", ".c", ".S", ".py", ".md", ".inl", ".txt"}
HEADERS = ["include/rex/" + n for n in (
    "system/xmemory.h", "system/mmio_handler.h", "exception_handler.h", "memory/utils.h",
    "logging/api.h", "logging/types.h", "logging/macros.h", "thread/mutex.h", "platform.h",
    "types.h", "assert.h")]
SDK_SOURCES = ["src/" + n for n in (
    "system/xmemory.cpp", "system/mmio_handler.cpp", "core/memory_posix.cpp",
    "core/exception_handler_posix.cpp", "core/logging.cpp", "core/clock_posix.cpp",
    "core/seh_posix.cpp")]
CONFIGS = [("clang++", "clang", "0"), ("clang++", "clang", "2"), ("g++", "gcc", "0"), ("g++", "gcc", "2")]
FATAL = ("callback-failure", "repair-failure", "declined-unhandled", "unadmitted", "wrong-site")
# Exact ordinary-code witness contract: (phase, (faults, consumed, invalidations, records)).
PHASES = {
    "callback-failure": [("injected", (1, 0, 1, 0)), ("caught", (1, 0, 1, 0)), ("terminal", (1, 0, 1, 0))],
    "repair-failure": [("claimed", (1, 1, 1, 0)), ("retry_fault", (2, 1, 1, 0)), ("terminal", (2, 1, 1, 0))],
    "declined-unhandled": [("declined", (1, 0, 0, 0)), ("recorded", (1, 0, 0, 1)), ("terminal", (1, 0, 0, 1))],
    "unadmitted": [("begin", (0, 0, 0, 0))],
    "wrong-site": [("begin", (0, 0, 0, 0))],
}
# Witness rows already emitted at each kernel SEGV_ACCERR stop, in order.
ACCERR_ROWS = {"callback-failure": [0], "repair-failure": [0, 1], "declined-unhandled": [0], "unadmitted": [1],
                "wrong-site": [1]}
LINE = re.compile(r"LRB_GATE_V1 token=([0-9a-f]{32}) mode=([a-z-]+) phase=([a-z_]+) faults=(\d+) "
                  r"consumed=(\d+) invalidations=(\d+) records=(\d+) address=0x([0-9a-f]+)\n")
SHM_NAME = re.compile(r"/xenia_memory_[0-9]+")


class GateError(RuntimeError):
    pass


def require(ok, why):
    if not ok:
        raise GateError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def lf(path):
    return Path(path).read_bytes().replace(b"\r\n", b"\n")


def read_json(data):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, "duplicate JSON key " + k)
            result[k] = v
        return result
    return json.loads(data, object_pairs_hook=unique)


# ------------------------------------------------------------------ contracts

def phase_rows(mode, token, stderr):
    """Parse the exact stderr witness bytes; any deviation fails."""
    require(mode in PHASES and re.fullmatch(r"[0-9a-f]{32}", token or ""), "mode/token")
    rows, offset = [], 0
    while offset < len(stderr):
        match = LINE.match(stderr, offset)
        require(match is not None, "unexpected/partial trace bytes")
        tok, name, phase, *values = match.groups()
        i = len(rows)
        require(i < len(PHASES[mode]) and tok == token and name == mode, "trace identity")
        expected_phase, counters = PHASES[mode][i]
        require(phase == expected_phase, "trace phase order")
        require(tuple(map(int, values[:4])) == counters, "trace counters")
        address = int(values[4], 16)
        require(address and address % 4 == 0 and (not rows or rows[0]["address"] == address), "trace address")
        rows.append({"phase": phase, "address": address})
        offset = match.end()
    return rows


def check_stop(mode, token, events, stderr, child_pid):
    """Validate the kernel stop just recorded against the witness position."""
    rows = phase_rows(mode, token, stderr)
    accerrs = ACCERR_ROWS[mode]
    require(0 < len(events) <= len(accerrs) + 1, "extra/missing SIGSEGV stop")
    current = events[-1]
    require(current["signal"] == 11, "unexpected signal")
    if len(events) <= len(accerrs):
        require(current["code"] == 2 and current["address"] > 0, "not a SEGV_ACCERR fault")
        require(len(rows) == accerrs[len(events) - 1], "witness position at checked fault")
        require(all(e["address"] == events[0]["address"] for e in events), "fault address changed")
        if rows:
            require(rows[0]["address"] == current["address"], "kernel/witness address mismatch")
    else:
        require(current["code"] == -6 and current["sender_pid"] == child_pid,
                "terminal signal was not same-process SI_TKILL")
        require(len(rows) == len(PHASES[mode]), "terminal branch not fully witnessed")
        require(all(e["code"] == 2 and e["address"] == rows[0]["address"] for e in events[:-1]),
                "kernel/witness addresses differ")
    return len(rows)


def describe(run):
    """Child facts appended to every failure so the real cause is never masked."""
    rc = run.get("returncode")
    parts = [f"mode={run.get('mode')}", f"pid={run.get('pid')}", f"returncode={rc}"]
    if isinstance(rc, int) and rc < 0:
        parts.append(f"signal={-rc}")
    if run.get("timeout"):
        parts.append("timeout=true")
    if run.get("ownership_error"):
        parts.append("ownership_error=" + run["ownership_error"])
    if run.get("unattributed_new_shm"):
        parts.append("unattributed_new_shm=" + ",".join(run["unattributed_new_shm"]))
    parts.append("stderr_tail=" + repr((run.get("stderr") or "")[-600:]))
    parts.append("stdout_tail=" + repr((run.get("stdout") or "")[-300:]))
    return " ".join(parts)


def checked(run, validator):
    try:
        return validator(run)
    except GateError as error:
        raise GateError(f"{error} [{describe(run)}]") from None


def validate_traced(run):
    require(run["status"] == "PASS", "failed traced record")
    require(run["returncode"] == -11 and run["stdout"] == "", "not real SIGSEGV death or extra stdout")
    events = run["signals"]
    require(len(events) == len(ACCERR_ROWS[run["mode"]]) + 1, "signal sequence length")
    for i, event in enumerate(events):
        require(check_stop(run["mode"], run["token"], events[:i + 1], event["trace"], run["pid"]) == event["phases"],
                "phase snapshot")
    require(events[-1]["trace"] == run["stderr"], "trace changed after terminal delivery stop")
    require(len(phase_rows(run["mode"], run["token"], run["stderr"])) == len(PHASES[run["mode"]]), "phase count")
    validate_ownership(run, expect_residue=False)


def validate_ownership(run, expect_residue):
    own = run.get("ownership")
    require(not run.get("ownership_error") and isinstance(own, dict) and own.get("format") == "LRB_OWNERSHIP_V1",
            "ownership record")
    require(own.get("stage") == "started", "ownership record stage is started")
    require(own["pid"] == run["pid"] and SHM_NAME.fullmatch(own["shm_name"]), "ownership identity")
    require(own["virtual_membase"] == 1 << 32, "views at 2^32")
    require(own["apparent_size"] == 0x120001000 and own["allocated_bytes"] < 64 << 20, "sparse shm size")
    fatal = run["mode"] in FATAL
    require(own["unlinked_early"] == fatal and own["policy"] == ("unlink-after-map" if fatal else "sdk-contract"),
            "shm policy for mode")
    residue = run.get("residue")
    require(isinstance(residue, dict), "residue record")
    if expect_residue:
        require(residue["present"] and residue["inode_match"] and residue["removed"] and not residue["after"],
                "crash residue detected and exactly-owned object removed")
    else:
        require(residue == {"present": False, "after": False}, "owned /dev/shm residue left")


NORMAL_STDOUT = re.compile(r"LRB_MEMORY vm_size_kib_before=(\d+) vm_size_kib_after=(\d+) vm_rss_kib_before=(\d+) "
                           r"vm_rss_kib_after=(\d+) shm_apparent=(\d+) shm_allocated=(\d+)\n"
                           r"LRB PASS checks=(\d+) mode=normal native=1\n")


def validate_normal(run):
    require(not run.get("timeout") and run["returncode"] == 0 and run["stderr"] == "", "normal run exit/stderr")
    match = NORMAL_STDOUT.fullmatch(run["stdout"])
    require(match is not None, "normal run stdout contract")
    vm0, vm1, rss0, rss1, apparent, allocated, checks = map(int, match.groups())
    require(vm1 - vm0 >= 0x120000000 // 1024 and apparent == 0x120001000, "4.5 GiB virtual reservation")
    require(allocated < 64 << 20, "sparse shm allocation")
    validate_ownership(run, expect_residue=False)
    return {"checks": checks, "vm_delta_kib": vm1 - vm0, "rss_delta_kib": rss1 - rss0, "shm_allocated": allocated}


def validate_leak(run):
    require(not run.get("timeout") and run["returncode"] == -9 and run["stdout"] == "" and run["stderr"] == "", "leak probe SIGKILL death")
    validate_ownership(run, expect_residue=True)


def validate_results(result):
    require(result.get("status") == "PASS", "result status")
    require([c["key"] for c in result["configurations"]] == [f"{a}_O{o}" for a, _, o in CONFIGS], "configurations")
    checks = set()
    for row in result["configurations"]:
        require(row["status"] == "PASS", "configuration status")
        require(len(row["normal"]) == result["repeats"] and result["repeats"] >= 1, "normal repetitions")
        for run in row["normal"]:
            checks.add(checked(run, validate_normal)["checks"])
        require(sorted(r["mode"] for r in row["traced"]) == sorted(FATAL * result["fatal_repeats"]), "traced inventory")
        for run in row["traced"]:
            checked(run, validate_traced)
        require(len(row["leak"]) == 1, "one leak probe")
        checked(row["leak"][0], validate_leak)
    require(len(checks) == 1, "identical positive check count across configurations")
    require(result["shm_snapshot"]["foreign_new"] == [], "unattributed new xenia_memory objects")
    return checks.pop()


# ---------------------------------------------------------------- native run

def ownership_path(out, tag):
    path = out / "ownership" / f"{tag}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    return path


def inspect_residue(record, out_run, remove):
    """Check the child's own shm object after it has been reaped.

    Never raises for a missing/invalid record: that is recorded as an
    ownership_error (which fails validation) and nothing is removed, because
    without an exact pid/name/inode record no object can be proven to be ours.
    """
    out_run["ownership"] = None
    own = None
    try:
        raw = record.read_bytes()
    except FileNotFoundError:
        raw = None
        out_run["ownership_error"] = ("missing ownership record: the child ended before it identified its "
                                      "SDK shm object")
    if raw is not None:
        try:
            own = read_json(raw)
        except (ValueError, GateError) as error:
            out_run["ownership_error"] = f"unreadable ownership record: {error}"
        if own is not None:
            out_run["ownership"] = own
            if not (isinstance(own, dict) and own.get("pid") == out_run.get("pid")
                    and isinstance(own.get("shm_name"), str) and SHM_NAME.fullmatch(own["shm_name"])
                    and isinstance(own.get("inode"), int) and isinstance(own.get("device"), int)):
                out_run["ownership_error"] = "ownership record does not identify this child's SDK shm object"
    if out_run.get("ownership_error"):
        out_run["residue"] = {"unknown": True}
        # Detection only: names that appeared during this child, never removed.
        out_run["unattributed_new_shm"] = sorted(set(shm_names()) - set(out_run.get("shm_before", [])))
        return
    name = own["shm_name"]
    path = "/dev/shm" + name
    try:
        st = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        out_run["residue"] = {"present": False, "after": False}
        return
    match = (stat.S_ISREG(st.st_mode) and st.st_ino == own["inode"] and st.st_dev == own["device"]
             and st.st_uid == os.getuid())
    residue = {"present": True, "inode_match": match, "removed": False, "allocated_bytes": st.st_blocks * 512}
    if remove and match:
        os.unlink(path)  # Exactly the inode created by our own reaped child.
        residue["removed"] = True
    residue["after"] = os.path.exists(path)
    out_run["residue"] = residue


def run_plain(command, mode, out, tag, extra_env=None, timeout=120):
    """Run one untraced child; ALWAYS return its full result (never raises on child failure)."""
    record = ownership_path(out, tag)
    env = os.environ.copy()
    env.pop("LRB_GATE_TOKEN", None)
    env.pop("LRB_SDK_LOG_CONSOLE", None)
    env.update(extra_env or {})
    env["LRB_OWNERSHIP_FILE"] = str(record)
    argv = [str(c) for c in command] + [mode]
    run = {"mode": mode, "argv": argv, "ownership_file": str(record),
           "env": {k: env[k] for k in sorted(env) if k.startswith("LRB_")}, "shm_before": shm_names()}
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    run["pid"] = p.pid
    try:
        stdout, stderr = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        stdout, stderr = p.communicate()
        run["timeout"] = True
    run.update(returncode=p.returncode, stdout=stdout.decode(errors="replace"), stderr=stderr.decode(errors="replace"))
    inspect_residue(record, run, remove=True)  # Own inode only; a non-leak run still fails.
    return run


def diagnose(command, out, key):
    """One extra normal run with SDK console logging, only after a failure."""
    return run_plain(command, "normal", out, f"{key}_diagnostic", extra_env={"LRB_SDK_LOG_CONSOLE": "1"})


def traced_run(executable, mode, out, tag, timeout=60, result=None):
    """PTRACE_TRACEME supervision: kernel siginfo at every SIGSEGV stop."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.ptrace.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p]
    libc.ptrace.restype = ctypes.c_long

    def ptrace(request, pid=0, addr=None, data=None):
        result = libc.ptrace(request, pid, addr, data)
        if result == -1:
            raise OSError(ctypes.get_errno(), "ptrace denied/failed; no security change or untraced fallback")
        return result

    def trace_me():
        try:
            ptrace(0)
        except OSError as error:
            os.write(2, f"LRB_PTRACE_BLOCKED errno={error.errno}\n".encode())
            os._exit(125)

    token = secrets.token_hex(16)
    record_path = ownership_path(out, tag)
    env = os.environ.copy()
    env["LRB_GATE_TOKEN"] = token
    env["LRB_OWNERSHIP_FILE"] = str(record_path)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    result = result if result is not None else {}
    result.update(mode=mode, token=token, signals=[], status="INCOMPLETE", shm_before=shm_names())
    process, selector, exited = None, None, False
    deadline = time.monotonic() + timeout

    def drain():
        for key in list(selector.get_map().values()):
            while True:
                try:
                    data = os.read(key.fileobj.fileno(), 4096)
                except BlockingIOError:
                    break
                if not data:
                    selector.unregister(key.fileobj)
                    break
                buffers[key.data].extend(data)
                require(len(buffers[key.data]) <= 16384, "unexpected output volume")

    def wait():
        while time.monotonic() < deadline:
            drain()
            pid, status = os.waitpid(process.pid, os.WNOHANG | os.WUNTRACED)
            if pid:
                return status
            selector.select(min(0.01, max(0, deadline - time.monotonic())))
        raise TimeoutError("traced LRB probe timed out")

    try:
        process = subprocess.Popen([str(executable), mode], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   preexec_fn=trace_me, env=env)
        result["pid"] = process.pid
        selector = selectors.DefaultSelector()
        for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, name)
        status = wait(); drain()
        if os.WIFEXITED(status) or os.WIFSIGNALED(status):
            exited = True
            result["returncode"] = os.waitstatus_to_exitcode(status)
        require(os.WIFSTOPPED(status) and os.WSTOPSIG(status) == 5 and status >> 16 == 0,
                "missing initial exec SIGTRAP (tracing unsupported?)")
        ptrace(0x4200, process.pid, data=ctypes.c_void_p(0x100000))  # SETOPTIONS EXITKILL
        ptrace(7, process.pid)  # CONT
        while True:
            status = wait(); drain()
            if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                exited = True
                process.returncode = os.waitstatus_to_exitcode(status)
                drain()
                result.update(returncode=process.returncode, stdout=buffers["stdout"].decode(),
                              stderr=buffers["stderr"].decode(), status="PASS")
                inspect_residue(record_path, result, remove=True)
                checked(result, validate_traced)
                return result
            require(os.WIFSTOPPED(status) and status >> 16 == 0 and os.WSTOPSIG(status) == 11,
                    "unexpected ptrace stop/event")
            info = ctypes.create_string_buffer(128)
            ptrace(0x4202, process.pid, data=ctypes.cast(info, ctypes.c_void_p))  # GETSIGINFO
            sig, error, code = struct.unpack_from("<iii", info.raw)
            event = {"signal": sig, "code": code, "errno": error,
                     "address": struct.unpack_from("<Q", info.raw, 16)[0] if code == 2 else 0,
                     "sender_pid": struct.unpack_from("<i", info.raw, 16)[0] if code == -6 else 0,
                     "trace": buffers["stderr"].decode()}
            result["signals"].append(event)
            event["phases"] = check_stop(mode, token, result["signals"], event["trace"], process.pid)
            require(not buffers["stdout"], "unexpected child stdout")
            ptrace(7, process.pid, data=ctypes.c_void_p(11))  # forward the exact SIGSEGV
    except BaseException as error:
        result.update(status="FAIL", error=str(error), stdout=buffers["stdout"].decode(errors="replace"),
                      stderr=buffers["stderr"].decode(errors="replace"))
        raise
    finally:
        if process is not None and not exited:
            try:
                os.kill(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            cleanup_deadline = time.monotonic() + 5
            while time.monotonic() < cleanup_deadline:
                try:
                    pid, status = os.waitpid(process.pid, os.WNOHANG | os.WUNTRACED)
                except ChildProcessError:
                    break
                if pid and (os.WIFEXITED(status) or os.WIFSIGNALED(status)):
                    result["cleanup_returncode"] = os.waitstatus_to_exitcode(status)
                    break
                if pid and os.WIFSTOPPED(status):
                    try:
                        ptrace(7, process.pid, data=ctypes.c_void_p(9))
                    except OSError:
                        pass
                time.sleep(0.01)
            else:
                result["cleanup_error"] = "child did not reap after SIGKILL"
            if record_path.exists() and "residue" not in result:
                try:
                    inspect_residue(record_path, result, remove=True)
                except Exception as error:  # Recorded, never masks the original failure.
                    result["residue_error"] = str(error)
        if selector is not None:
            selector.close()
        if process is not None:
            process.stdout.close(); process.stderr.close()


def command(argv, log, timeout=600, cwd=None):
    p = subprocess.run([str(a) for a in argv], capture_output=True, text=True, timeout=timeout, cwd=cwd)
    log.append({"argv": [str(a) for a in argv], "returncode": p.returncode,
                "stdout": p.stdout[-20000:], "stderr": p.stderr[-20000:]})
    require(p.returncode == 0, f"command failed: {argv[0]} rc={p.returncode}")
    return p.stdout


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, timeout=120).stdout


def source_identity():
    manifest = read_json((ROOT / "SOURCE_MANIFEST.json").read_bytes())
    require(all(sha(lf(ROOT / p)) == h for p, h in manifest.items()), "source transfer hash mismatch")
    require(all(REL + f in manifest for f in OWN_FILES), "LRB source inventory")
    identity = read_json((ROOT / "IMPLEMENTATION_ID.json").read_bytes())
    require(re.fullmatch(r"[0-9a-f]{40}", identity["commit"]) is not None, "commit identity")
    return manifest, identity


def sdk_identity(sdk, prefix):
    require(git(sdk, "rev-parse", "HEAD").decode().strip() == SDK_PIN, "SDK pin mismatch")
    simde = sdk / "thirdparty/simde"
    require(git(simde, "rev-parse", "HEAD").decode().strip() == SIMDE_PIN, "SIMDe pin mismatch")
    files = {}
    for name in HEADERS + SDK_SOURCES:
        expected = git(sdk, "show", SDK_PIN + ":" + name).replace(b"\r\n", b"\n")
        require(lf(sdk / name) == expected, "SDK source changed: " + name)
        if name in HEADERS:
            require(lf(prefix / name) == expected, "installed header differs: " + name)
        files[name] = sha(expected)
    names = [n for n in git(simde, "ls-tree", "-r", "--name-only", SIMDE_PIN, "--", "simde").decode().splitlines()
             if n.endswith(".h")]
    simde_headers = {}
    for rel in names:
        expected = git(simde, "show", SIMDE_PIN + ":" + rel).replace(b"\r\n", b"\n")
        require(lf(simde / rel) == expected and lf(prefix / "include" / rel) == expected, "SIMDe header differs")
        simde_headers[rel] = sha(expected)
    require(len(simde_headers) == 469, "SIMDe header inventory")
    libraries = {p.relative_to(prefix).as_posix(): sha(p.read_bytes())
                 for d in (prefix / "lib", prefix / "lib64", prefix / "bin") if d.is_dir()
                 for p in sorted(d.rglob("*")) if p.is_file() and (p.suffix in (".so", ".a") or ".so." in p.name)}
    require(any("librexruntime" in n for n in libraries), "missing installed SDK runtime library")
    return {"sdk": SDK_PIN, "simde": SIMDE_PIN, "sources_sha256_lf": files,
            "simde_sha256_lf": simde_headers, "libraries_sha256": libraries}


def shm_names():
    try:
        return sorted("/" + n for n in os.listdir("/dev/shm") if SHM_NAME.fullmatch("/" + n))
    except FileNotFoundError:
        return []


def artifact_paths(build, key):
    objects = build / "CMakeFiles/lrb_tests.dir"
    return {f"native/{key}/{name}": path for name, path in {
        "lrb_tests.elf": build / "lrb_tests",
        "lrb_owner.o": objects / "lrb_owner.c.o",
        "lrb_access.o": objects / "lrb_access.S.o",
        "final.objdump.txt": build / "final.objdump.txt",
        "final.readelf.txt": build / "final.readelf.txt",
        "owner.objdump.txt": build / "owner.objdump.txt",
        "access.objdump.txt": build / "access.objdump.txt",
        "bootstrap.objdump.txt": build / "bootstrap.objdump.txt"}.items()}


# (name, argv, final stdout marker, runner writes a top-level "status")
PRIOR = [
    ("sdk_composition", ["linux_sdk_composition/run.py", "--sdk", "{sdk}", "--prefix", "{prefix}", "--repeats", "20"],
     "SDK_COMPOSITION_MATRIX PASS", True),
    ("sdk_lifecycle", ["linux_sdk_composition/run_lifecycle.py", "--repeats", "20"], "LSC_LIFECYCLE_MATRIX PASS", True),
    ("integration", ["linux_guest_integration/run.py", "--sdk", "{sdk}", "--repeats", "20"],
     "INTEGRATION_MATRIX PASS", True),
    ("integration_sanitizers", ["linux_guest_integration/run.py", "--sdk", "{sdk}", "--portable-only", "--sanitize",
                                "--repeats", "2"], "INTEGRATION_MATRIX PASS", True),
    ("fault", ["linux_guest_fault/run_matrix.py", "--sdk", "{sdk}", "--repeats", "20"], "LINUX_FAULT_MATRIX PASS", True),
    ("record_sanitizers", ["linux_guest_fault/run_matrix.py", "--sdk", "{sdk}", "--portable-only", "--sanitize",
                           "--repeats", "2"], "LINUX_FAULT_MATRIX PASS", True),
    ("emitter", ["portable_guest_eh/run_native.py", "--sdk", "{sdk}", "--cxx", "clang++", "--cxx", "g++",
                 "--sanitize", "--repeats", "20"], "NATIVE_FIXTURE_MATRIX PASS", False),
]


def validate_prior(entry, prior_result):
    spec = {n: (m, s) for n, _, m, s in PRIOR}
    require(entry["name"] in spec and entry["status"] == "PASS" and entry["returncode"] == 0, "prior regression run")
    marker, has_status = spec[entry["name"]]
    require(marker in entry["stdout"], "prior regression marker: " + entry["name"])
    require(not has_status or prior_result.get("status") == "PASS", "prior regression result: " + entry["name"])


def run_native(args):
    require(platform.system() == "Linux" and platform.machine() == "x86_64" and struct.calcsize("P") == 8,
            "native Linux x86-64 required; no Windows/WSL fallback")
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    sdk, prefix = args.sdk.resolve(), args.prefix.resolve()
    result = {"status": "INCOMPLETE", "platform": platform.platform(), "machine": platform.machine(),
              "kernel": platform.release(), "python": sys.version, "repeats": args.repeats,
              "fatal_repeats": args.fatal_repeats, "configurations": [], "prior": []}
    before_names = shm_names()
    result["shm_snapshot"] = {"before": before_names}
    try:
        manifest, identity = source_identity()
        result.update(identity=identity, source_manifest=manifest)
        sdk_info = sdk_identity(sdk, prefix)
        result["sdk_identity"] = sdk_info
        for cxx_name, cc_name, opt in CONFIGS:
            cxx, cc = shutil.which(cxx_name), shutil.which(cc_name)
            require(cxx and cc, "missing compiler pair " + cxx_name)
            key = f"{cxx_name}_O{opt}"
            build = out / key
            row = {"key": key, "status": "INCOMPLETE", "commands": [], "normal": [], "traced": [], "leak": []}
            result["configurations"].append(row)
            log = row["commands"]
            row["cxx_version"] = command([cxx, "--version"], log)
            row["cc_version"] = command([cc, "--version"], log)
            if build.exists():
                shutil.rmtree(build)
            command(["cmake", "-S", HERE, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                     "-DCMAKE_PREFIX_PATH=" + str(prefix), "-DCMAKE_CXX_COMPILER=" + cxx,
                     "-DCMAKE_C_COMPILER=" + cc, "-DCMAKE_ASM_COMPILER=" + cc, "-DLRB_OPT=" + opt,
                     "-DLRB_ORDINARY_ONLY=OFF"], log)
            command(["cmake", "--build", build, "--verbose"], log)
            executable = build / "lrb_tests"
            digest = sha(executable.read_bytes())
            row["executable_sha256"] = digest
            for i in range(args.repeats):
                run = run_plain([executable], "normal", out, f"{key}_normal_{i}")
                row["normal"].append(run)  # Kept in results.json even when it fails.
                try:
                    row.setdefault("normal_summary", []).append(checked(run, validate_normal))
                except GateError:
                    try:  # Never let the diagnostic replace the original failure.
                        row["diagnostic"] = diagnose([executable], out, key)
                    except Exception as error:
                        row["diagnostic_error"] = f"{type(error).__name__}: {error}"
                    raise
            for i in range(args.fatal_repeats):
                for mode in FATAL:
                    record = {"mode": mode, "status": "INCOMPLETE"}
                    row["traced"].append(record)
                    traced_run(executable, mode, out, f"{key}_{mode}_{i}", result=record)
            leak = run_plain([executable], "leak-probe", out, f"{key}_leak")
            row["leak"].append(leak)
            checked(leak, validate_leak)
            require(sha(executable.read_bytes()) == digest, "executable changed during runs")
            objects = build / "CMakeFiles/lrb_tests.dir"
            for tool, flags, path, target in (
                    ("objdump", ["-drwC"], build / "final.objdump.txt", executable),
                    ("readelf", ["-Wh", "-Wr", "-Ws", "-Wl", "-Wd"], build / "final.readelf.txt", executable),
                    ("objdump", ["-drwC"], build / "owner.objdump.txt", objects / "lrb_owner.c.o"),
                    ("objdump", ["-drwC"], build / "access.objdump.txt", objects / "lrb_access.S.o"),
                    ("objdump", ["-drwC"], build / "bootstrap.objdump.txt", objects / "lrb_bootstrap.cpp.o")):
                path.write_text(command([tool, *flags, target], log), encoding="utf-8")
            row["artifacts"] = {n: sha(p.read_bytes()) for n, p in artifact_paths(build, key).items()}
            require(row["artifacts"][f"native/{key}/lrb_tests.elf"] == digest, "executable changed during inspection")
            row["status"] = "PASS"
        lrb_names = shm_names()
        ours = {r["ownership"]["shm_name"] for row in result["configurations"]
                for r in row["normal"] + row["traced"] + row["leak"]
                if isinstance(r.get("ownership"), dict) and isinstance(r["ownership"].get("shm_name"), str)}
        result["shm_snapshot"].update(after_lrb=lrb_names,
                                      foreign_new=sorted(set(lrb_names) - set(before_names) - ours),
                                      own_left=sorted(set(lrb_names) & ours))
        require(not result["shm_snapshot"]["own_left"], "own shm residue left")
        if not args.skip_prior:
            for name, argv, _marker, _has_status in PRIOR:
                target = out / "prior" / name
                entry = {"name": name, "out": str(target), "status": "INCOMPLETE"}
                result["prior"].append(entry)
                full = [sys.executable, str(HERE.parent / argv[0])] + [
                    a.format(sdk=sdk, prefix=prefix) for a in argv[1:]] + ["--out", str(target)]
                entry["argv"] = full
                p = subprocess.run(full, capture_output=True, text=True, timeout=7200, cwd=ROOT)
                entry.update(returncode=p.returncode, stdout=p.stdout[-8000:], stderr=p.stderr[-8000:])
                require(p.returncode == 0, "prior regression failed: " + name)
                entry["status"] = "PASS"
                validate_prior(entry, read_json((target / "results.json").read_bytes()))
        # Informational only: prior fixtures do not use Memory::Initialize.
        result["shm_snapshot"]["after_prior"] = shm_names()
        require(sdk_identity(sdk, prefix) == sdk_info, "SDK changed during run")
        require(source_identity() == (manifest, identity), "sources changed during run")
        result["positive_checks"] = validate_results({**result, "status": "PASS"})
        result["status"] = "PASS"
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"LRB_GATE PASS configurations=4 normal={4 * args.repeats} traced={4 * len(FATAL) * args.fatal_repeats} "
          f"leak=4 prior={0 if args.skip_prior else len(PRIOR)}; independent audit still required")


# ------------------------------------------------------- packaging and audit

def write_zip(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, entries[name])
    with zipfile.ZipFile(temp) as z:
        require(z.testzip() is None and sorted(z.namelist()) == sorted(entries), "zip reopen inventory")
        require(all(z.read(n) == entries[n] for n in entries), "zip reopen content")
    temp.replace(path)
    return sha(path.read_bytes())


def source_files():
    names = [REL + f for f in OWN_FILES]
    for d in PRIOR_DIRS:
        base = ROOT / "tools/experiments" / d
        for p in sorted(base.iterdir()):
            if p.is_file() and (p.suffix in PRIOR_SUFFIXES or p.name == "CMakeLists.txt"):
                names.append(p.relative_to(ROOT).as_posix())
    return sorted(set(names))


def package_source(path):
    head = git(ROOT, "rev-parse", "HEAD").decode().strip()
    entries = {}
    for name in source_files():
        blob = git(ROOT, "show", f"HEAD:{name}").replace(b"\r\n", b"\n")
        require(lf(ROOT / name) == blob, "working file differs from HEAD: " + name)
        entries[name] = blob
    manifest = {n: sha(b) for n, b in entries.items()}
    entries["SOURCE_MANIFEST.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    entries["IMPLEMENTATION_ID.json"] = (json.dumps({"commit": head, "sdk": SDK_PIN, "simde": SIMDE_PIN},
                                                    indent=2) + "\n").encode()
    digest = write_zip(path, entries)
    (path.parent / (path.name + ".sha256")).write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    print(f"LRB_SOURCE PASS files={len(entries)} commit={head} sha256={digest} path={path}")


def package_evidence(out, path, failure):
    out = out.resolve()
    entries = {}
    results = out / "results.json"
    if results.exists():
        entries["results.json"] = results.read_bytes()
        data = read_json(entries["results.json"])
        for row in data.get("configurations", []):
            for name, src in artifact_paths(out / row["key"], row["key"]).items():
                if src.exists():
                    entries[name] = src.read_bytes()
        for entry in data.get("prior", []):
            prior_results = Path(entry["out"]) / "results.json"
            if prior_results.exists():
                entries[f"prior/{entry['name']}/results.json"] = prior_results.read_bytes()
    for name in ("SOURCE_MANIFEST.json", "IMPLEMENTATION_ID.json"):
        if (ROOT / name).exists():
            entries[name] = (ROOT / name).read_bytes()
    console = out / "console.log"
    if console.exists():
        entries["console.log"] = console.read_bytes()
    if failure:
        for p in sorted((out / "ownership").glob("*.json")) if (out / "ownership").is_dir() else []:
            entries["ownership/" + p.name] = p.read_bytes()
        entries["FAILURE.txt"] = b"INCOMPLETE/FAILED native LRB evidence; not a PASS claim.\n"
    require(entries, "nothing to package")
    entries["EVIDENCE_MANIFEST.json"] = (json.dumps({n: sha(b) for n, b in sorted(entries.items())},
                                                    indent=2) + "\n").encode()
    digest = write_zip(path, entries)
    print(f"LRB_EVIDENCE {'FAILURE' if failure else 'PASS'} entries={len(entries)} sha256={digest} path={path}")


def audit(archive, implementation):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) and z.testzip() is None, "archive integrity")
        data = {n: z.read(n) for n in names}
    require("FAILURE.txt" not in data, "failure bundle is not PASS evidence")
    manifest = read_json(data["EVIDENCE_MANIFEST.json"])
    require(set(manifest) == set(data) - {"EVIDENCE_MANIFEST.json"}, "evidence inventory")
    require(all(sha(data[n]) == h for n, h in manifest.items()), "evidence digest mismatch")
    identity = read_json(data["IMPLEMENTATION_ID.json"])
    require(identity["commit"] == implementation, "implementation commit mismatch")
    source = read_json(data["SOURCE_MANIFEST.json"])
    for name, digest in source.items():
        blob = git(ROOT, "show", f"{implementation}:{name}").replace(b"\r\n", b"\n")
        require(sha(blob) == digest, "transferred source differs from Git: " + name)
    result = read_json(data["results.json"])
    require(result["identity"] == identity and result["source_manifest"] == source, "result source identity")
    require(result["sdk_identity"]["sdk"] == SDK_PIN and result["sdk_identity"]["simde"] == SIMDE_PIN, "SDK pins")
    for name, digest in result["sdk_identity"]["sources_sha256_lf"].items():
        blob = git(ROOT / "external/rexglue-sdk", "show", f"{SDK_PIN}:{name}").replace(b"\r\n", b"\n")
        require(sha(blob) == digest, "SDK source identity differs from pin: " + name)
    checks = validate_results(result)
    for row in result["configurations"]:
        for name, digest in row["artifacts"].items():
            require(name in data and sha(data[name]) == digest, "artifact digest: " + name)
        require(row["executable_sha256"] == row["artifacts"][f"native/{row['key']}/lrb_tests.elf"], "ELF identity")
    for entry in result["prior"]:
        require(f"prior/{entry['name']}/results.json" in data, "prior regression results archived")
        validate_prior(entry, read_json(data[f"prior/{entry['name']}/results.json"]))
    require([e["name"] for e in result["prior"]] == [n for n, *_ in PRIOR], "complete prior regression set")
    print(f"LRB_AUDIT PASS positive_checks={checks} configurations=4 entries={len(data)}; "
          "manual final-ELF/TLS/handler review still required")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("source"); s.add_argument("--zip", type=Path, default=SOURCE_ZIP)
    r = sub.add_parser("run")
    r.add_argument("--sdk", type=Path, required=True); r.add_argument("--prefix", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--repeats", type=int, default=20); r.add_argument("--fatal-repeats", type=int, default=5)
    r.add_argument("--skip-prior", action="store_true", help="diagnostic only; full acceptance needs prior regressions")
    e = sub.add_parser("evidence"); e.add_argument("--out", type=Path, required=True)
    e.add_argument("--zip", type=Path, required=True); e.add_argument("--failure", action="store_true")
    a = sub.add_parser("audit"); a.add_argument("--archive", type=Path, required=True)
    a.add_argument("--implementation", required=True)
    args = ap.parse_args()
    if args.cmd == "source":
        package_source(args.zip)
    elif args.cmd == "run":
        require(args.repeats >= 1 and args.fatal_repeats >= 1, "positive repetition counts")
        run_native(args)
    elif args.cmd == "evidence":
        package_evidence(args.out, args.zip, args.failure)
    else:
        audit(args.archive, args.implementation)


if __name__ == "__main__":
    try:
        main()
    except GateError as error:
        print(f"LRB_GATE FAIL: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:  # Unexpected runner fault: keep the traceback, still a FAIL.
        traceback.print_exc()
        print(f"LRB_GATE FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
