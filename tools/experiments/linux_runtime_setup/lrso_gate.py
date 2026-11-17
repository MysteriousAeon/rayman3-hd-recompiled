"""Linux Runtime Setup Ownership (LRSO): source contract, native gate, evidence, audit.

Subcommands:
  source-contract  (any) check the pinned SDK blobs (never the working tree) for the facts the experiment relies on:
                   where seh_initialize()/the latch are used, the Runtime::Setup/Shutdown ordering, the signal
                   installation inventory and the thread creation inventory.
  source           (any) write the source-only CachyOS ZIP from committed Git bytes (no generated code).
  run              (Linux x86-64 only) build Clang/GCC O0/O2, run the LRSO matrix and the LRB regression.
  evidence         (Linux) package results, own ELF/object bytes, records and dumps.  The ZIP is PRIVATE.
  audit            (any, read-only) re-derive every validator and binary check from a returned evidence ZIP.

Never builds, patches or installs the SDK; never launches the game; removes only /dev/shm objects proven to belong
to its own child.  No generated code is involved: the children run the real pinned rex::Runtime::Setup in tool mode
plus one synthetic LWR leaf.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import struct
import subprocess
import sys
import traceback
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REL = "tools/experiments/linux_runtime_setup/"
sys.path.insert(0, str(HERE.parent / "linux_write_watch_restart"))
import lwr_gate as W  # noqa: E402  (audited LWR gate: tracer, object checks, packaging helpers; unchanged)

G = W.G
L = W.L
GateError, require, sha, lf, read_json = L.GateError, L.require, L.sha, L.lf, L.read_json
OWN_FILES = ["CMakeLists.txt", "README.md", "lrso_tests.cpp", "lrso_gate.py", "test_lrso_gate.py"]
DEFAULT_SDK = ROOT / "external/rexglue-sdk"
CONFIG_KEYS = [f"{a}_O{o}" for a, _, o in L.CONFIGS]

POSITIVE = ["default", "default-originals", "latch", "latch-cycles"]
TRACED_POSITIVE = "latch-traced-positive"
FATAL_LRSO = ["latch-unregistered", "latch-unauthorized", "latch-consumed", "latch-foreign-session"]
# mode -> (variant, cycles, claims, invalidations)
MODES = {"default": ("default", 1, 0, 0), "default-originals": ("default", 1, 0, 0),
         "latch": ("latch", 1, 1, 1), "latch-cycles": ("latch", 3, 3, 3), TRACED_POSITIVE: ("latch", 1, 1, 1),
         **{m: ("latch", 1, 0, 0) for m in FATAL_LRSO}}
STAGES = {
    "default": ["after-setup", "after-shutdown"],
    "default-originals": ["after-setup", "after-thunk-removal", "after-owner-refused", "after-shutdown"],
    "latch": ["after-setup", "after-thunk-removal", "after-owner", "after-restart", "after-owner-removal",
              "after-shutdown"],
    "fatal": ["after-setup", "after-thunk-removal", "after-owner"],
}
THREAD_STAGES = {
    "default": ["after-setup", "after-owner", "after-shutdown"],
    "default-originals": ["after-setup", "after-owner", "after-shutdown"],
    "latch": ["after-setup", "after-owner", "after-restart", "after-shutdown"],
    "fatal": ["after-setup", "after-owner"],
}
SEGV, ILL, BUS, FPE = 11, 4, 7, 8
SIGNALS = [s for s in range(1, 65) if s not in (9, 19)]
SA_SIGINFO, SA_NODEFER, SA_ONSTACK = 0x4, 0x40000000, 0x08000000
OWNER_MASK = (1 << 10) | (1 << 6)  # LRB owner blocks SIGSEGV (11) and SIGBUS (7) while running.
EXPECTED_ADDRESS = 0x100000000 + 0xA4000000 + 0x4100  # runtime membase + vA alias + P4 target offset
LATCH_SYMBOL = "_ZN3rex8platform17g_seh_initializedE"
SDK_PIN = L.SDK_PIN

LRSO_SDK_FILES = ["include/rex/runtime.h", "include/rex/platform/seh.h", "include/rex/platform/exceptions.h",
                  "include/rex/system/kernel_state.h", "src/system/runtime.cpp", "src/system/kernel_state.cpp",
                  "src/core/seh_posix.cpp", "src/core/threading_posix.cpp", "src/core/timer_queue.cpp",
                  "src/system/xam/user_profile.cpp", "src/system/xam/content_manager.cpp"]

NATIVE_NAMES = ["lrso_tests.elf", "lrb_owner.o", "lwr_restart.o", "lwr_test_leaf.o", "lrb_access.o", "lrso_tests.o",
                "final.objdump.txt", "owner.objdump.txt", "restart.objdump.txt", "final.readelf.txt",
                "runtime.dynsym.txt", "runtime.dynamic.txt", "runtime.relocs.txt", "runtime.symbols.txt"]
TEXT_NAMES = [n for n in NATIVE_NAMES if n.endswith(".txt")]
REGRESSION_RUNS = 1


def register_fatal():
    """Register the LRSO fatal modes with the audited LRB ownership validator (unlink-after-map policy)."""
    L.FATAL = tuple(dict.fromkeys(L.FATAL + tuple(FATAL_LRSO)))


def source_files():
    return sorted({REL + f for f in OWN_FILES} | set(W.source_files()))


# ------------------------------------------------------------------ pinned SDK source contract

def git_out(sdk, *args, ok=(0,)):
    try:
        p = subprocess.run(["git", "-C", str(sdk), *args], capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GateError(f"git {args[0]} failed: {error}") from None
    require(p.returncode in ok, f"git {' '.join(args[:3])} failed (rc={p.returncode}): {p.stderr.decode(errors='replace')[:200]}")
    return p.stdout


def pinned_bytes(sdk, path, pin=SDK_PIN):
    return git_out(sdk, "show", f"{pin}:{path}").replace(b"\r\n", b"\n")


def pinned_text(sdk, path, pin=SDK_PIN):
    return pinned_bytes(sdk, path, pin).decode("utf-8")


def pinned_grep_files(sdk, tokens, paths, pin=SDK_PIN):
    args = ["grep", "-l", "-F"]
    for token in tokens:
        args += ["-e", token]
    out = git_out(sdk, *args, pin, "--", *paths, ok=(0, 1)).decode("utf-8", errors="replace")
    return sorted(line[len(pin) + 1:] for line in out.splitlines() if line.startswith(pin + ":"))


def pinned_grep_lines(sdk, token, paths, pin=SDK_PIN):
    """{path: [(line number, text)]} for a fixed string."""
    out = git_out(sdk, "grep", "-n", "-F", "-e", token, pin, "--", *paths, ok=(0, 1)).decode("utf-8", errors="replace")
    found = {}
    for line in out.splitlines():
        if not line.startswith(pin + ":"):
            continue
        path, number, text = line[len(pin) + 1:].split(":", 2)
        found.setdefault(path, []).append((int(number), text.rstrip("\r")))
    return found


def function_body(text, header):
    require(text.count(header) == 1, f"{header!r} must occur exactly once")
    start = text.index(header)
    end = text.find("\n}\n", start)
    require(end != -1, f"{header!r} has no closing brace")
    return text[start:end]


def ordered(body, needles, what):
    position = 0
    for needle in needles:
        found = body.find(needle, position)
        require(found != -1, f"{what}: {needle!r} missing or out of order")
        position = found + len(needle)


def fact_latch_declaration(seh_h):
    lines = seh_h.split("\n")
    require(lines.count("inline std::atomic<bool> g_seh_initialized{false};") == 1,
            "seh.h: the latch is not declared exactly as the public inline atomic")
    namespaces = [i for i, line in enumerate(lines) if line == "namespace rex::platform {"]
    require(len(namespaces) == 1 and namespaces[0] < lines.index("inline std::atomic<bool> g_seh_initialized{false};"),
            "seh.h: latch not declared inside namespace rex::platform")
    return {"declaration": "inline std::atomic<bool> g_seh_initialized{false};"}


def fact_seh_posix(text):
    ordered(text, ["void seh_initialize() {\n  if (g_seh_initialized.exchange(true)) {\n    return;"], "seh_initialize latch")
    ordered(text, ["sa.sa_flags = SA_SIGINFO | SA_NODEFER;", "sigaction(SIGSEGV, &sa, nullptr);",
                   "sigaction(SIGBUS, &sa, nullptr);", "sigaction(SIGFPE, &sa, nullptr);",
                   "sigaction(SIGILL, &sa, nullptr);"], "seh_initialize installs")
    handler = function_body(text, "static void signal_handler(int sig, siginfo_t* info, void* /*ucontext*/) {")
    require("throw SehException(code, address);" in handler, "signal_handler no longer throws SehException")
    require("signal(sig, SIG_DFL);\n    raise(sig);" in handler, "signal_handler inactive path is not SIG_DFL + raise")
    init = function_body(text, "void seh_initialize() {")
    require(init.count("sigaction(") == 4, "seh_initialize installs other than four signals")
    return {"signals": ["SIGSEGV", "SIGBUS", "SIGFPE", "SIGILL"], "flags": "SA_SIGINFO|SA_NODEFER"}


def fact_latch_files(paths):
    want = ["include/rex/platform/seh.h", "src/core/seh_posix.cpp", "src/core/seh_win.cpp"]
    require(sorted(paths) == want, f"g_seh_initialized occurs in {sorted(paths)}, expected {want}")
    return want


def fact_initialize_seh_sites(occurrences, exceptions_h, seh_h):
    require(sorted(occurrences) == ["include/rex/platform/exceptions.h", "src/system/runtime.cpp"],
            f"initialize_seh() occurrences in {sorted(occurrences)}")
    runtime = occurrences["src/system/runtime.cpp"]
    require(len(runtime) == 1 and runtime[0][1].strip() == "rex::initialize_seh();",
            "src/system/runtime.cpp must contain exactly the one call rex::initialize_seh();")
    header = [text.strip() for _, text in occurrences["include/rex/platform/exceptions.h"]]
    require(len(header) == 2 and header[1] == "inline void initialize_seh() {" and header[0].startswith("*")
            and "rex::initialize_seh()" in header[0], "exceptions.h: unexpected initialize_seh() occurrences")
    require("inline void initialize_seh() {\n  platform::seh_initialize();\n}" in exceptions_h,
            "exceptions.h: initialize_seh() is not exactly platform::seh_initialize()")
    require("void seh_initialize();" in seh_h, "seh.h: seh_initialize declaration")
    return {"call_sites": 1, "definition": "include/rex/platform/exceptions.h"}


def fact_setup_order(runtime_cpp):
    body = function_body(runtime_cpp, "X_STATUS Runtime::Setup(RuntimeConfig config) {")
    ordered(body, ["rex::initialize_seh();", "memory_ = std::make_unique<memory::Memory>();", "memory_->Initialize()",
                   "std::make_unique<runtime::ExportResolver>()", "std::make_unique<runtime::FunctionDispatcher>",
                   "std::make_unique<rex::filesystem::VirtualFileSystem>()", "std::make_unique<system::KernelState>(this)",
                   "if (config.input_factory)", "if (config.kernel_init)", "if (config.audio_factory)",
                   "if (!SetupVfs())", "if (tool_mode_) {", "if (config.graphics)"], "Runtime::Setup")
    return {"order": "seh, memory, resolver, dispatcher, vfs, kernel_state, input, kernel_init, audio, vfs, tool_mode, graphics"}


def fact_shutdown_order(runtime_cpp):
    body = function_body(runtime_cpp, "void Runtime::Shutdown() {")
    ordered(body, ["graphics_system_.reset()", "audio_system_.reset()", "input_system_.reset()", "kernel_state_.reset();",
                   "function_dispatcher_.reset();", "export_resolver_.reset();", "file_system_.reset();",
                   "memory_.reset();", "rex::perf::Profiler::Shutdown();"], "Runtime::Shutdown")
    for forbidden in ("seh", "sigaction", "signal("):
        require(forbidden not in body, f"Runtime::Shutdown touches {forbidden!r}")
    return {"touches_signals": False}


def fact_setup_vfs(runtime_cpp):
    body = function_body(runtime_cpp, "bool Runtime::SetupVfs() {")
    inner = body[len("bool Runtime::SetupVfs() {"):].lstrip()
    require(inner.startswith("if (game_data_root_.empty()) {"), "SetupVfs does not start with the empty-root check")
    ordered(body, ["if (game_data_root_.empty()) {", "return true;", "std::filesystem::absolute"], "SetupVfs empty root")
    return {"empty_root": "returns true before any filesystem access"}


def fact_exception_handler(text):
    install = function_body(text, "void ExceptionHandler::Install(Handler fn, void* data) {")
    ordered(install, ["signal_handler.sa_flags = SA_SIGINFO;",
                      "sigaction(SIGILL, &signal_handler, &original_sigill_handler_)",
                      "sigaction(SIGSEGV, &signal_handler, &original_sigsegv_handler_)",
                      "#if REX_PLATFORM_MAC\n", "sigaction(SIGBUS, &signal_handler, &original_sigbus_handler_)",
                      "#endif"], "ExceptionHandler::Install")
    require(install.count("sigaction(") == 3 and install.count("sigaction(SIGBUS") == 1, "Install installs other than ILL/SEGV/(mac BUS)")
    uninstall = function_body(text, "void ExceptionHandler::Uninstall(Handler fn, void* data) {")
    ordered(uninstall, ["if (!has_any) {", "sigaction(SIGILL, &original_sigill_handler_, NULL)",
                        "sigaction(SIGSEGV, &original_sigsegv_handler_, NULL)", "#if REX_PLATFORM_MAC\n",
                        "sigaction(SIGBUS, &original_sigbus_handler_, NULL)", "#endif"], "ExceptionHandler::Uninstall")
    require(uninstall.count("sigaction(") == 3, "Uninstall restores other than ILL/SEGV/(mac BUS)")
    require(uninstall.find("sigaction(") > uninstall.find("if (!has_any) {"), "Uninstall restores before checking has_any")
    return {"linux_installs": ["SIGILL", "SIGSEGV"], "sigbus": "REX_PLATFORM_MAC only"}


def count_tokens(texts, tokens):
    """{token: {path: count}} over non-Windows files."""
    out = {t: {} for t in tokens}
    for path, text in sorted(texts.items()):
        if path.endswith("_win.cpp"):
            continue
        for token in tokens:
            n = text.count(token)
            if n:
                out[token][path] = n
    return out


SIGNAL_TOKENS = ["sigaction(", "signal("]
PINNED_SIGNAL_INVENTORY = {
    "sigaction(": {"src/core/exception_handler_posix.cpp": 6, "src/core/seh_posix.cpp": 4,
                   "src/core/threading_posix.cpp": 1},
    "signal(": {"src/core/dbg_posix.cpp": 2, "src/core/seh_posix.cpp": 2},
}
THREAD_TOKENS = ["pthread_create(", "Thread::Create(", "std::thread(", "std::jthread(", "new XHostThread("]
PINNED_THREAD_INVENTORY = {
    "pthread_create(": {"src/core/threading_posix.cpp": 1},
    "Thread::Create(": {"src/core/threading_posix.cpp": 1, "src/graphics/d3d12/pipeline_cache.cpp": 4,
                        "src/graphics/vulkan/pipeline_cache.cpp": 3, "src/system/xthread.cpp": 3},
    "std::thread(": {"src/rexglue/ui/progress.cpp": 1, "src/ui/presenter.cpp": 1, "src/ui/rex_app.cpp": 1},
    "std::jthread(": {"src/core/timer_queue.cpp": 1},
    "new XHostThread(": {"src/system/kernel_state.cpp": 1},
}


def fact_signal_inventory(texts):
    inventory = count_tokens(texts, SIGNAL_TOKENS)
    require(inventory == PINNED_SIGNAL_INVENTORY, f"signal installation inventory changed: {inventory}")
    body = function_body(texts["src/core/threading_posix.cpp"], "void install_signal_handler(SignalType type) {")
    require(body.count("sigaction(") == 1, "threading_posix sigaction is not inside install_signal_handler")
    return inventory


def fact_thread_inventory(texts):
    inventory = count_tokens(texts, THREAD_TOKENS)
    require(inventory == PINNED_THREAD_INVENTORY, f"thread creation inventory changed: {inventory}")
    return inventory


def fact_kernel_state_threads(kernel_state_cpp):
    ctor = function_body(kernel_state_cpp, "KernelState::KernelState(Runtime* emulator)")
    for token in THREAD_TOKENS:
        require(token not in ctor, f"KernelState constructor creates threads ({token})")
    execute = function_body(kernel_state_cpp, "void KernelState::SetExecutableModule(object_ref<UserModule> module) {")
    require(kernel_state_cpp.count("new XHostThread(") == 1 and "new XHostThread(" in execute,
            "the XHostThread is not created only inside SetExecutableModule")
    return {"xhostthread": "SetExecutableModule only"}


def fact_thread_signal_sites(threading_cpp):
    spans = []
    for header in ("std::unique_ptr<Thread> Thread::Create(CreationParameters params,", "Thread* Thread::GetCurrentThread() {"):
        start = threading_cpp.index(header) if threading_cpp.count(header) == 1 else -1
        require(start != -1, f"{header!r} must occur exactly once")
        end = threading_cpp.find("\n}\n", start)
        require(end != -1, f"{header!r} has no closing brace")
        spans.append((start, end))
    token = "install_signal_handler(SignalType::"
    sites, start = [], 0
    while True:
        index = threading_cpp.find(token, start)
        if index == -1:
            break
        sites.append(index)
        start = index + 1
    require(sites and all(any(a <= i < b for a, b in spans) for i in sites),
            "install_signal_handler(SignalType:: called outside Thread::Create / Thread::GetCurrentThread")
    require(all(any(a <= i < b for i in sites) for a, b in spans), "a thread entry point no longer installs signal handlers")
    return {"call_sites": len(sites)}


def fact_timer_queue(timer_queue_cpp):
    require("std::jthread([this](std::stop_token stop_token)" in timer_queue_cpp, "timer queue dispatcher jthread missing")
    return {"dispatcher": "std::jthread"}


def source_contract(sdk, pin=SDK_PIN):
    """Every fact from the pinned blobs only (the working tree carries Windows patches)."""
    sdk = Path(sdk)
    require((sdk / ".git").exists() or (sdk / "HEAD").exists(), f"not a git checkout: {sdk}")
    require(git_out(sdk, "cat-file", "-t", pin).strip() == b"commit", "pinned SDK commit not present")
    text = {p: pinned_text(sdk, p, pin) for p in (
        "include/rex/platform/seh.h", "include/rex/platform/exceptions.h", "src/core/seh_posix.cpp",
        "src/system/runtime.cpp", "src/core/exception_handler_posix.cpp", "src/system/kernel_state.cpp",
        "src/core/threading_posix.cpp", "src/core/timer_queue.cpp")}
    latch_files = pinned_grep_files(sdk, ["g_seh_initialized"], ["src", "include", "cmake", "tools"], pin)
    initialize = pinned_grep_lines(sdk, "initialize_seh()", ["."], pin)
    signal_texts = {p: pinned_text(sdk, p, pin) for p in pinned_grep_files(sdk, SIGNAL_TOKENS, ["src"], pin)
                    if not p.endswith("_win.cpp")}
    thread_texts = {p: pinned_text(sdk, p, pin) for p in pinned_grep_files(sdk, THREAD_TOKENS, ["src"], pin)
                    if not p.endswith("_win.cpp")}
    facts = {
        "a_latch_declaration": fact_latch_declaration(text["include/rex/platform/seh.h"]),
        "b_seh_posix": fact_seh_posix(text["src/core/seh_posix.cpp"]),
        "c_latch_files": fact_latch_files(latch_files),
        "d_initialize_seh_sites": fact_initialize_seh_sites(initialize, text["include/rex/platform/exceptions.h"],
                                                            text["include/rex/platform/seh.h"]),
        "e_setup_order": fact_setup_order(text["src/system/runtime.cpp"]),
        "e_shutdown_order": fact_shutdown_order(text["src/system/runtime.cpp"]),
        "e_setup_vfs": fact_setup_vfs(text["src/system/runtime.cpp"]),
        "f_exception_handler": fact_exception_handler(text["src/core/exception_handler_posix.cpp"]),
        "g_signal_inventory": fact_signal_inventory(signal_texts),
        "h_thread_inventory": fact_thread_inventory(thread_texts),
        "h_kernel_state_threads": fact_kernel_state_threads(text["src/system/kernel_state.cpp"]),
        "h_thread_signal_sites": fact_thread_signal_sites(text["src/core/threading_posix.cpp"]),
        "h_timer_queue": fact_timer_queue(text["src/core/timer_queue.cpp"]),
    }
    return {"sdk": pin, "facts": facts}


def lrso_sdk_identity(sdk, prefix):
    files = {}
    for name in LRSO_SDK_FILES:
        expected = pinned_bytes(sdk, name)
        require(lf(sdk / name) == expected, "SDK source differs from the pin: " + name)
        if name.startswith("include/"):
            require(lf(prefix / name) == expected, "installed header differs from the pin: " + name)
        files[name] = sha(expected)
    return files


# ------------------------------------------------------------------ record parsing

SIG_RE = re.compile(r"LRSO_SIG_V1\|mode=([a-z-]+)\|cycle=(\d+)\|stage=([a-z-]+)\|sig=(\d+)\|state=(dfl|ign|fn|invalid)"
                    r"\|siginfo=([01])\|flags=(0x[0-9a-f]+)\|mask=(0x[0-9a-f]{16})\|object=([^|]+)\|offset=(0x[0-9a-f]+)")
THREADS_RE = re.compile(r"LRSO_THREADS_V1\|mode=([a-z-]+)\|cycle=(\d+)\|stage=([a-z-]+)\|count=(\d+)\|baseline=(\d+)\|equal=([01])")
LATCH_RE = re.compile(r"LRSO_LATCH_V1\|mode=([a-z-]+)\|stage=([a-z-]+)\|value=([01])\|object=([^|]+)")
RUNTIME_RE = re.compile(r"LRSO_RUNTIME_V1\|mode=([a-z-]+)\|cycle=(\d+)\|setup_status=(0x[0-9a-f]+)\|instance=1\|kernel_shared=1"
                        r"\|mmio=1\|membase=(0x[0-9a-f]+)\|tool_mode=1\|shm=(/xenia_memory_[0-9]+)\|inode=(\d+)\|device=(\d+)")
SIMPLE_RE = {"LRSO_TEARDOWN_V1": re.compile(r"LRSO_TEARDOWN_V1\|mode=([a-z-]+)\|cycle=(\d+)\|"),
             "LRSO_RESTART_V1": re.compile(r"LRSO_RESTART_V1\|mode=([a-z-]+)\|cycle=(\d+)\|"),
             "LRSO_HANDOFF_V1": re.compile(r"LRSO_HANDOFF_V1\|mode=([a-z-]+)\|cycle=(\d+)\|")}
KINDS = {"LRSO_SIG_V1": "sig", "LRSO_THREADS_V1": "threads", "LRSO_LATCH_V1": "latch", "LRSO_RUNTIME_V1": "runtime",
         "LRSO_TEARDOWN_V1": "teardown", "LRSO_RESTART_V1": "restart", "LRSO_HANDOFF_V1": "handoff"}
ROW_KEYS = ("state", "siginfo", "flags", "mask", "object", "offset")


def parse_records(text, mode):
    require(isinstance(text, str) and text.endswith("\n") and "\r" not in text, "record file framing")
    out = {kind: [] for kind in KINDS.values()}
    for line in text[:-1].split("\n"):
        prefix = line.split("|", 1)[0]
        require(prefix in KINDS, "unknown record line: " + line[:80])
        kind = KINDS[prefix]
        if kind == "sig":
            m = SIG_RE.fullmatch(line)
            require(m is not None, "malformed signal record: " + line[:120])
            g = m.groups()
            item = {"mode": g[0], "cycle": int(g[1]), "stage": g[2], "sig": int(g[3]), "state": g[4], "siginfo": int(g[5]),
                    "flags": int(g[6], 16), "mask": int(g[7], 16), "object": g[8], "offset": int(g[9], 16)}
        elif kind == "threads":
            m = THREADS_RE.fullmatch(line)
            require(m is not None, "malformed thread record: " + line[:120])
            g = m.groups()
            item = {"mode": g[0], "cycle": int(g[1]), "stage": g[2], "count": int(g[3]), "baseline": int(g[4]),
                    "equal": int(g[5])}
        elif kind == "latch":
            m = LATCH_RE.fullmatch(line)
            require(m is not None, "malformed latch record: " + line[:120])
            g = m.groups()
            item = {"mode": g[0], "stage": g[1], "value": int(g[2]), "object": g[3]}
        elif kind == "runtime":
            m = RUNTIME_RE.fullmatch(line)
            require(m is not None, "malformed runtime record: " + line[:160])
            g = m.groups()
            item = {"mode": g[0], "cycle": int(g[1]), "setup_status": g[2], "membase": g[3], "shm": g[4],
                    "inode": int(g[5]), "device": int(g[6])}
        else:
            m = SIMPLE_RE[prefix].match(line)
            require(m is not None, "malformed record: " + line[:120])
            item = {"mode": m.group(1), "cycle": int(m.group(2)), "raw": line}
        require(item["mode"] == mode, f"record mode {item['mode']} != {mode}")
        out[kind].append(item)
    return out


def group_stages(sig_rows):
    require(sig_rows and len(sig_rows) % len(SIGNALS) == 0, "signal records are not whole stages")
    stages = []
    for i in range(0, len(sig_rows), len(SIGNALS)):
        chunk = sig_rows[i:i + len(SIGNALS)]
        key = (chunk[0]["cycle"], chunk[0]["stage"])
        require(all((r["cycle"], r["stage"]) == key for r in chunk), f"stage {key} block mixes stages")
        require([r["sig"] for r in chunk] == SIGNALS, f"stage {key} does not list signals 1..64 without 9/19 once each")
        stages.append((key, {r["sig"]: r for r in chunk}))
    return stages


def row_of(r):
    return tuple(r[k] for k in ROW_KEYS)


def changed(a, b):
    return [s for s in SIGNALS if row_of(a[s]) != row_of(b[s])]


def stage_kind(mode):
    return "fatal" if mode in FATAL_LRSO else ("latch" if MODES[mode][0] == "latch" else mode)


def require_sdk_fn(r, flags, what):
    require(r["state"] == "fn" and r["siginfo"] == 1 and r["flags"] == flags and r["mask"] == 0
            and r["object"].startswith("librexruntime.so"),
            f"{what}: expected an SDK handler (siginfo=1 flags=0x{flags:x} mask=0 in librexruntime), got {row_of(r)}")


def validate_records(mode, text):
    """Re-derive the signal ownership contract of one LRSO run from its record file."""
    require(mode in MODES, "unknown LRSO mode " + str(mode))
    variant, cycles = MODES[mode][0], MODES[mode][1]
    fatal = mode in FATAL_LRSO
    recs = parse_records(text, mode)
    stages = group_stages(recs["sig"])
    kind = stage_kind(mode)
    want = [(0, "entry"), (0, "after-logging")] + [(c, s) for c in range(1, cycles + 1) for s in STAGES[kind]]
    require([k for k, _ in stages] == want, f"stage sequence {[k for k, _ in stages]} != {want}")
    by_key = dict(stages)
    entry, logged = by_key[(0, "entry")], by_key[(0, "after-logging")]
    for sig in (SEGV, ILL, BUS, FPE):
        require(entry[sig]["state"] == "dfl", f"entry: signal {sig} is not SIG_DFL")
    require(changed(entry, logged) == [], "logging initialization changed a signal disposition")

    thunk = seh = None
    for c in range(1, cycles + 1):
        setup = by_key[(c, "after-setup")]
        if variant == "default":
            require(changed(entry, setup) == sorted([ILL, BUS, FPE, SEGV]), f"cycle {c}: Setup changed {changed(entry, setup)}")
            require(row_of(setup[SEGV]) == row_of(setup[ILL]), "SIGSEGV and SIGILL thunks differ")
            require_sdk_fn(setup[SEGV], SA_SIGINFO, "MMIO thunk")
            require(row_of(setup[BUS]) == row_of(setup[FPE]), "SIGBUS and SIGFPE SEH actions differ")
            require_sdk_fn(setup[FPE], SA_SIGINFO | SA_NODEFER, "SEH handler")
            require(setup[SEGV]["offset"] != setup[FPE]["offset"], "SEH handler and MMIO thunk share an offset")
            cycle_thunk, cycle_seh = setup[SEGV]["offset"], setup[FPE]["offset"]
            seh_row = row_of(setup[FPE])

            def seh_only(stage_rows, what):
                for sig in SIGNALS:
                    expect = seh_row if sig in (ILL, BUS, FPE, SEGV) else row_of(entry[sig])
                    require(row_of(stage_rows[sig]) == expect, f"cycle {c} {what}: signal {sig} differs from the expected SEH state")
            if mode == "default-originals":
                removed = by_key[(c, "after-thunk-removal")]
                seh_only(removed, "after-thunk-removal")
                require(changed(removed, by_key[(c, "after-owner-refused")]) == [], "refused owner install changed a signal")
            seh_only(by_key[(c, "after-shutdown")], "after-shutdown")
        else:
            require(changed(entry, setup) == [ILL, SEGV], f"cycle {c}: latch Setup changed {changed(entry, setup)}")
            require(row_of(setup[SEGV]) == row_of(setup[ILL]), "SIGSEGV and SIGILL thunks differ")
            require_sdk_fn(setup[SEGV], SA_SIGINFO, "MMIO thunk")
            require(setup[BUS]["state"] == "dfl" and setup[FPE]["state"] == "dfl", "latch: SIGBUS/SIGFPE not SIG_DFL after Setup")
            cycle_thunk, cycle_seh = setup[SEGV]["offset"], None
            require(changed(entry, by_key[(c, "after-thunk-removal")]) == [], "thunk removal did not restore the entry state")
            owner = by_key[(c, "after-owner")]
            require(changed(entry, owner) == [SEGV], f"cycle {c}: owner changed {changed(entry, owner)}")
            o = owner[SEGV]
            require(o["state"] == "fn" and o["siginfo"] == 1 and o["flags"] == SA_ONSTACK | SA_SIGINFO and o["mask"] == OWNER_MASK
                    and o["object"] in ("lrso_tests", "main"),
                    f"LRB owner action is not the executable's SA_ONSTACK|SA_SIGINFO handler with mask 0x{OWNER_MASK:x}: {row_of(o)}")
            if not fatal:
                require(changed(owner, by_key[(c, "after-restart")]) == [], "the restart changed a signal disposition")
                require(changed(entry, by_key[(c, "after-owner-removal")]) == [], "owner removal did not restore the entry state")
                require(changed(entry, by_key[(c, "after-shutdown")]) == [], "Shutdown did not restore the entry state")
        thunk = cycle_thunk if thunk is None else thunk
        seh = cycle_seh if seh is None else seh
        require(cycle_thunk == thunk and cycle_seh == seh, "handler offsets differ between cycles")

    # Threads.
    tkind = stage_kind(mode)
    twant = [(0, "entry"), (0, "after-logging")] + [(c, s) for c in range(1, cycles + 1) for s in THREAD_STAGES[tkind]]
    require([(t["cycle"], t["stage"]) for t in recs["threads"]] == twant, "thread record sequence")
    for t in recs["threads"]:
        require(t["equal"] == 1 and t["count"] == t["baseline"] == 2, f"thread set changed: {t}")

    # Latch.
    lwant = {"default": [("entry", 0), ("after-setup", 1), ("after-shutdown", 1)],
             "latch": [("entry", 0), ("after-store", 1), ("after-setup", 1), ("after-shutdown", 1)]}[variant]
    if fatal:
        lwant = lwant[:-1]
    require([(r["stage"], r["value"]) for r in recs["latch"]] == lwant, "latch record sequence")
    require(all(r["object"].startswith("librexruntime.so") for r in recs["latch"]), "the latch is not the SDK library's own")

    # Runtime / teardown / handoff / restart.
    require([r["cycle"] for r in recs["runtime"]] == list(range(1, cycles + 1)), "runtime record per cycle")
    for r in recs["runtime"]:
        require(r["setup_status"] == "0x0" and r["membase"] == "0x100000000", f"runtime record: {r}")
    # Names are tick-based and must differ; tmpfs may legitimately reuse an inode number after unlink.
    require(len({r["shm"] for r in recs["runtime"]}) == cycles, "runtime cycles reuse a shm name")
    teardown = [] if fatal else [f"LRSO_TEARDOWN_V1|mode={mode}|cycle={c}|instance=0|kernel_shared=0|mmio=0|views_unmapped=1"
                                 f"|shm_removed=1|altstack_disabled=1" for c in range(1, cycles + 1)]
    require([r["raw"] for r in recs["teardown"]] == teardown, "teardown records")
    result, beneath = {"default": ("not-attempted", "unobserved"), "latch": ("installed", "sig_dfl")}[variant]
    if mode == "default-originals":
        result, beneath = "refused-ebusy", "sdk-seh"
    handoff = [f"LRSO_HANDOFF_V1|mode={mode}|cycle={c}|result={result}|segv_beneath={beneath}" for c in range(1, cycles + 1)]
    require([r["raw"] for r in recs["handoff"]] == handoff, "handoff records")
    restart = [] if (variant == "default" or fatal) else [
        f"LRSO_RESTART_V1|mode={mode}|cycle={c}|page=4|target_offset=0x4100|width=4|length=3|error=7|claims=1"
        f"|invalidations=1|region_equal=1|watch_cleared=1" for c in range(1, cycles + 1)]
    require([r["raw"] for r in recs["restart"]] == restart, "restart records")
    return {"thunk": thunk, "seh": seh, "shm": [r["shm"] for r in recs["runtime"]]}


# ------------------------------------------------------------------ run validators

WITNESS = re.compile(r"LRSO_GATE_V1 token=([0-9a-f]{32}) mode=([a-z-]+) phase=([a-z]+) claims=(\d+) "
                     r"invalidations=(\d+) address=0x([0-9a-f]+)\n")


def parse_witness(text, token=None, mode=None):
    rows, offset = [], 0
    while offset < len(text):
        match = WITNESS.match(text, offset)
        require(match is not None, "unexpected/partial trace bytes")
        tok, name, phase, claims, invalidations, address = match.groups()
        require(token is None or tok == token, "witness token")
        require(mode is None or name == mode, "witness mode")
        rows.append({"phase": phase, "claims": int(claims), "invalidations": int(invalidations), "address": int(address, 16)})
        offset = match.end()
    return rows


def stop_rows(stop, run):
    require(run["stderr"].startswith(stop["trace"]) and (stop["trace"] == "" or stop["trace"].endswith("\n")),
            "stop-time stderr is not a complete-line prefix of the final stderr")
    return parse_witness(stop["trace"], run.get("token"), run["mode"])


def pass_line(mode):
    variant, cycles, claims, invalidations = MODES[mode]
    return re.compile(rf"LRSO PASS mode={mode} variant={variant} cycles={cycles} claims={claims} "
                      rf"invalidations={invalidations} checks=(\d+) tasks=2 native=1\n")


def validate_untraced(run, record_text):
    mode = run["mode"]
    require(mode in POSITIVE, "untraced run of a non-positive mode")
    require(not run.get("timeout") and run["returncode"] == 0 and run["stderr"] == "", "untraced run exit/stderr")
    match = pass_line(mode).fullmatch(run["stdout"])
    require(match is not None, "untraced stdout contract")
    require(run.get("cwd_entries") == [], f"the runtime created files in its working directory: {run.get('cwd_entries')}")
    summary = validate_records(mode, record_text)
    validate_owned_shm(run, record_text)
    return {**summary, "checks": int(match.group(1))}


def validate_traced_positive(run, record_text):
    require(run["status"] == "PASS" and run["mode"] == TRACED_POSITIVE, "failed traced record")
    require(run["returncode"] == 0 and not run.get("timeout"), "traced positive exit status")
    require(re.fullmatch(r"[0-9a-f]{32}", run.get("token") or "") is not None, "gate token")
    match = pass_line(TRACED_POSITIVE).fullmatch(run["stdout"])
    require(match is not None, "traced positive stdout contract")
    rows = parse_witness(run["stderr"], run["token"], TRACED_POSITIVE)
    require(len(rows) == 1 and rows[0]["phase"] == "claim" and rows[0]["claims"] == 1 and rows[0]["invalidations"] == 0
            and rows[0]["address"] == EXPECTED_ADDRESS, "traced positive witness row")
    stops = run["signals"]
    require(len(stops) == 1, "traced positive stop count")
    W.check_stop_kind(stops[0], "ACCERR", run["pid"], rows[0]["address"])
    require(len(stop_rows(stops[0], run)) == 0, "witness written before the fault stop")
    summary = validate_records(TRACED_POSITIVE, record_text)
    validate_owned_shm(run, record_text)
    return {**summary, "checks": int(match.group(1))}


def validate_owned_shm(run, record_text):
    """LRB ownership/residue rules, and the record names the shm object of the last runtime cycle."""
    L.validate_ownership(run, expect_residue=False)
    names = [m.group(5) for m in RUNTIME_RE.finditer(record_text)]
    require(names and run["ownership"]["shm_name"] == names[-1],
            "ownership record does not name the last runtime cycle's shm object")


def fatal_contract(mode, rows):
    require(rows, "fatal witness rows")
    address = rows[0]["address"]
    require(address == EXPECTED_ADDRESS, "fatal witness address")
    if mode == "latch-consumed":
        return ([("begin", 0, 0, address), ("claimed", 1, 0, address), ("rewatched", 1, 1, address)],
                [("ACCERR", 1), ("ACCERR", 3), ("TKILL", 3)])
    return [("begin", 0, 0, address)], [("ACCERR", 1), ("TKILL", 1)]


def validate_traced_fatal(run, record_text):
    mode = run["mode"]
    require(run["status"] == "PASS" and mode in FATAL_LRSO, "failed traced record")
    require(re.fullmatch(r"[0-9a-f]{32}", run.get("token") or "") is not None, "gate token")
    require(run["returncode"] == -11 and run["stdout"] == "" and not run.get("timeout"),
            "not real SIGSEGV death or extra stdout")
    rows = parse_witness(run["stderr"], run["token"], mode)
    want_rows, want_stops = fatal_contract(mode, rows)
    require([(r["phase"], r["claims"], r["invalidations"], r["address"]) for r in rows] == want_rows,
            "witness phase/counter/address sequence")
    stops = run["signals"]
    require(len(stops) == len(want_stops), "signal sequence length")
    for stop, (kind, at_stop) in zip(stops, want_stops):
        W.check_stop_kind(stop, kind, run["pid"], rows[0]["address"])
        require(len(stop_rows(stop, run)) == at_stop, f"witness lines already written at the {kind} stop")
    require(stops[-1]["trace"] == run["stderr"], "trace changed after terminal delivery stop")
    summary = validate_records(mode, record_text)
    validate_owned_shm(run, record_text)
    return summary


# ------------------------------------------------------------------ binary checks and cross-run checks

SYMBOL_ROW = re.compile(r"^\s*\d+:\s+[0-9a-f]+\s+\d+\s+(\w+)\s+(\w+)\s+(\w+)\s+(\S+)(?:\s+(\S+))?\s*$")


def latch_rows(text):
    rows = []
    for line in text.splitlines():
        m = SYMBOL_ROW.match(line)
        if m and m.group(5) and (m.group(5) == LATCH_SYMBOL or m.group(5).startswith(LATCH_SYMBOL + "@")):
            rows.append({"type": m.group(1), "bind": m.group(2), "vis": m.group(3), "ndx": m.group(4)})
    return rows


def check_latch_binary(final_readelf, dynsym, dynamic, relocs):
    """The experiment relies on the SDK library owning the one latch definition."""
    exe = latch_rows(final_readelf)
    require(all(r["ndx"] == "UND" for r in exe), "the test executable defines its own copy of the SDK latch")
    defined = [r for r in latch_rows(dynsym) if r["ndx"] != "UND"]
    require(len(defined) == 1, f"librexruntime must define the latch exactly once in .dynsym, found {len(defined)}")
    require(defined[0]["bind"] in ("UNIQUE", "WEAK", "GLOBAL") and defined[0]["vis"] == "DEFAULT",
            f"the SDK latch is not interposable/exported: bind={defined[0]['bind']} vis={defined[0]['vis']}")
    for line in dynamic.splitlines():
        require("(SYMBOLIC)" not in line and not ("(FLAGS)" in line and "SYMBOLIC" in line),
                "librexruntime is linked -Bsymbolic (DT_SYMBOLIC)")
    return {"exe_defines_latch": False, "sdk_bind": defined[0]["bind"], "sdk_visibility": defined[0]["vis"],
            "symbolic": False, "sdk_relocation_against_latch": any(LATCH_SYMBOL in l for l in relocs.splitlines()),
            "exe_references_latch": bool(exe)}


def binary_checks(text):
    return {"bind_now": W.check_bind_now(text["final.readelf.txt"]),
            "owner_calls_admit": W.check_owner_calls_admit(text["owner.objdump.txt"]),
            "restart_admit": W.check_restart_object(text["restart.objdump.txt"]),
            "signal_closure": W.check_signal_closure(text["owner.objdump.txt"], text["restart.objdump.txt"]),
            "latch": check_latch_binary(text["final.readelf.txt"], text["runtime.dynsym.txt"],
                                        text["runtime.dynamic.txt"], text["runtime.relocs.txt"])}


NM_ROW = re.compile(r"^([0-9a-f]+)\s+[A-Za-z]\s+(\S+)$")


def check_provenance(nm_text, thunk, seh):
    thunks, handlers = set(), set()
    for line in nm_text.splitlines():
        m = NM_ROW.match(line.strip())
        if not m:
            continue
        address, name = int(m.group(1), 16), m.group(2)
        if "ExceptionHandlerCallback" in name:
            thunks.add(address)
        if "rex8platform" in name and "signal_handler" in name:
            handlers.add(address)
    if not thunks and not handlers:
        return "unsymbolized"
    require(thunks and handlers, "partially symbolized librexruntime.so")
    require(thunk in thunks, f"recorded MMIO thunk 0x{thunk:x} is not the ExceptionHandlerCallback symbol")
    require(seh in handlers, f"recorded SEH handler 0x{seh:x} is not rex::platform's signal_handler symbol")
    return "symbolized"


def check_cross_run(summaries, symbols_text):
    thunks = {s["thunk"] for s in summaries}
    sehs = {s["seh"] for s in summaries if s["seh"] is not None}
    require(len(thunks) == 1, f"the MMIO thunk offset differs between runs: {sorted(hex(t) for t in thunks)}")
    require(len(sehs) == 1, f"the SEH handler offset differs between runs: {sorted(hex(t) for t in sehs)}")
    thunk, seh = thunks.pop(), sehs.pop()
    require(thunk != seh, "the SEH handler and the MMIO thunk are the same function")
    return {"thunk": hex(thunk), "seh": hex(seh), "provenance": check_provenance(symbols_text, thunk, seh)}


# ------------------------------------------------------------------ result validation

def run_text(run, reader):
    data = reader(run["record_file"])
    require(sha(data) == run["record_sha256"], "record file digest: " + run["record_file"])
    return data.decode("ascii")


def validate_regression(regression, reader=None):
    require([r["key"] for r in regression["lrb"]] == CONFIG_KEYS, "regression configurations")
    for row in regression["lrb"]:
        W.check_closure("lrb", row["key"], "lrb_tests.elf", row["executable_sha256"], row["cxx_version"])
        W.check_closure("lrb", row["key"], "lrb_owner.o", row["owner_sha256"], row["cxx_version"])
        require(len(row["normal"]) == REGRESSION_RUNS, "LRB regression repetitions")
        for run in row["normal"]:
            L.checked(run, L.validate_normal)


def validate_results(result, reader):
    register_fatal()
    require(result.get("status") == "PASS", "result status")
    require([c["key"] for c in result["configurations"]] == CONFIG_KEYS, "configurations")
    n, cr, t = result["repeats"], result["cycles_repeats"], result["traced_repeats"]
    require(min(n, cr, t) >= 1, "repetition counts")
    checks = {}
    for row in result["configurations"]:
        key = row["key"]
        require(row["status"] == "PASS", "configuration status")
        for name in NATIVE_NAMES:
            require(sha(reader(f"native/{key}/{name}")) == row["artifacts"][name], f"artifact digest: native/{key}/{name}")
        require(row["executable_sha256"] == row["artifacts"]["lrso_tests.elf"], "ELF identity")
        text = {name: reader(f"native/{key}/{name}").decode("utf-8") for name in TEXT_NAMES}
        require(binary_checks(text) == row["object_checks"], "object checks re-derived: " + key)
        summaries = []
        modes = sorted(r["mode"] for r in row["runs"])
        require(modes == sorted(["default"] * n + ["default-originals"] * n + ["latch"] * n + ["latch-cycles"] * cr),
                "untraced run inventory")
        for run in row["runs"]:
            s = L.checked(run, lambda r: validate_untraced(r, run_text(r, reader)))
            summaries.append(s)
            checks.setdefault(run["mode"], set()).add(s["checks"])
        require(len(row["traced_positive"]) == t, "traced positive repetitions")
        for run in row["traced_positive"]:
            s = L.checked(run, lambda r: validate_traced_positive(r, run_text(r, reader)))
            summaries.append(s)
            checks.setdefault(TRACED_POSITIVE, set()).add(s["checks"])
        require(sorted(r["mode"] for r in row["traced_fatal"]) == sorted(FATAL_LRSO * t), "traced fatal inventory")
        for run in row["traced_fatal"]:
            summaries.append(L.checked(run, lambda r: validate_traced_fatal(r, run_text(r, reader))))
        require(check_cross_run(summaries, text["runtime.symbols.txt"]) == row["cross_run"], "cross-run checks re-derived: " + key)
    require(all(len(v) == 1 for v in checks.values()), f"check counts differ between runs/configurations: {checks}")
    require(result["shm_snapshot"]["foreign_new"] == [], "unattributed new xenia_memory objects")
    require(result["shm_snapshot"]["own_left"] == [], "own shm residue left")
    validate_regression(result["regression"])
    return {m: sorted(v)[0] for m, v in checks.items()}


# ------------------------------------------------------------------ source transfer

def package_source(path):
    head = G.git("rev-parse", "HEAD").decode().strip()
    entries = W.package_entries(head, source_files(), lambda n: G.git("show", f"HEAD:{n}"), lambda n: lf(ROOT / n))
    digest = L.write_zip(path, entries)
    W.write_sidecar(path, digest)
    print(f"LRSO_SOURCE PASS files={len(entries)} commit={head} size={path.stat().st_size} sha256={digest} path={path}")


def source_identity():
    manifest = read_json((ROOT / "SOURCE_MANIFEST.json").read_bytes())
    identity = read_json((ROOT / "IMPLEMENTATION_ID.json").read_bytes())
    require(all(sha(lf(ROOT / p)) == h for p, h in manifest.items()), "source transfer hash mismatch")
    require(sorted(manifest) == source_files(), "LRSO source inventory")
    require(re.fullmatch(r"[0-9a-f]{40}", identity["commit"]) is not None, "commit identity")
    return manifest, identity


# ------------------------------------------------------------------ native gate

def run_untraced(exe, mode, out, tag):
    """One untraced child in a fresh empty working directory; never raises on child failure."""
    record = out / "records" / f"{tag}.txt"
    record.parent.mkdir(parents=True, exist_ok=True)
    if record.exists():
        record.unlink()
    own = L.ownership_path(out, tag)
    cwd = out / "cwd" / tag
    if cwd.exists():
        shutil.rmtree(cwd)
    cwd.mkdir(parents=True)
    env = os.environ.copy()
    env.pop("LRB_GATE_TOKEN", None)
    env.pop("LRB_SDK_LOG_CONSOLE", None)
    env.update({"LRSO_RECORD_FILE": str(record), "LRB_OWNERSHIP_FILE": str(own)})
    argv = [str(exe), mode]
    run = {"mode": mode, "argv": argv, "cwd": str(cwd), "record_file": f"records/{tag}.txt", "shm_before": L.shm_names()}
    try:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=cwd)
        run["pid"] = p.pid
        try:
            stdout, stderr = p.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            p.kill()
            stdout, stderr = p.communicate()
            run["timeout"] = True
        run.update(returncode=p.returncode, stdout=stdout.decode(errors="replace"), stderr=stderr.decode(errors="replace"))
    except OSError as error:
        run.update(pid=0, returncode=-1000, stdout="", stderr=f"spawn failed: {error}")
    run["cwd_entries"] = sorted(os.listdir(cwd))
    run["record_sha256"] = sha(record.read_bytes() if record.exists() else b"")
    L.inspect_residue(own, run, remove=True)
    return run


def run_traced(exe, mode, out, tag, token, sink):
    record = {"mode": mode, "token": token, "status": "INCOMPLETE"}
    sink.append(record)  # Partial facts stay in results.json if the tracer raises.
    rec = out / "records" / f"{tag}.txt"
    rec.parent.mkdir(parents=True, exist_ok=True)
    if rec.exists():
        rec.unlink()
    record["record_file"] = f"records/{tag}.txt"
    own = L.ownership_path(out, tag)
    try:
        W.traced([exe, mode], W.traced_env(token, own, {"LRSO_RECORD_FILE": str(rec)}), timeout=120, ownership=own,
                 result=record)
    finally:
        record["record_sha256"] = sha(rec.read_bytes() if rec.exists() else b"")
    return record


def locate_runtime_library(prefix):
    found = sorted(p for d in ("lib", "lib64") if (prefix / d).is_dir() for p in (prefix / d).rglob("librexruntime.so*")
                   if p.is_file() and not p.is_symlink())
    require(len(found) == 1, f"expected exactly one installed librexruntime.so under {prefix}, found {len(found)}")
    return found[0]


def native_config(out, key, cxx, cc, opt, prefix, args, row):
    log = row["commands"]
    build = out / "build" / key
    if build.exists():
        shutil.rmtree(build)
    row["cxx_version"] = L.command([cxx, "--version"], log)
    row["cc_version"] = L.command([cc, "--version"], log)
    W.configure_and_build(HERE, build, cxx, cc, prefix, ["-DLRSO_OPT=" + opt], log)
    exe = build / "lrso_tests"
    exe_sha = sha(exe.read_bytes())
    row["executable_sha256"] = exe_sha
    objects = build / "CMakeFiles/lrso_tests.dir"
    native = out / "native" / key
    native.mkdir(parents=True, exist_ok=True)
    sources = {"lrso_tests.elf": exe, "lrb_owner.o": W.find_one(objects, "lrb_owner.c.o"),
               "lwr_restart.o": W.find_one(objects, "lwr_restart.c.o"),
               "lwr_test_leaf.o": W.find_one(objects, "lwr_test_leaf.S.o"),
               "lrb_access.o": W.find_one(objects, "lrb_access.S.o"),
               "lrso_tests.o": W.find_one(objects, "lrso_tests.cpp.o")}
    for name, src in sources.items():
        shutil.copyfile(src, native / name)
    runtime = locate_runtime_library(prefix)
    row["runtime_library"] = {"path": runtime.relative_to(prefix).as_posix(), "sha256": sha(runtime.read_bytes())}
    dumps = {"final.objdump.txt": ("objdump", ["-drwC"], native / "lrso_tests.elf"),
             "owner.objdump.txt": ("objdump", ["-drwC"], native / "lrb_owner.o"),
             "restart.objdump.txt": ("objdump", ["-drwC"], native / "lwr_restart.o"),
             "final.readelf.txt": ("readelf", ["-a", "-W"], native / "lrso_tests.elf"),
             "runtime.dynsym.txt": ("readelf", ["--dyn-syms", "-W"], runtime),
             "runtime.dynamic.txt": ("readelf", ["-d", "-W"], runtime)}
    for name, (tool, flags, target) in dumps.items():
        (native / name).write_text(L.command([tool, *flags, target], log), encoding="utf-8", newline="\n")
    relocs = L.command(["readelf", "-r", "-W", runtime], log)
    (native / "runtime.relocs.txt").write_text("".join(l + "\n" for l in relocs.splitlines() if "g_seh_initialized" in l),
                                               encoding="utf-8", newline="\n")
    try:
        symbols = L.command(["nm", "--defined-only", runtime], log)
    except GateError:
        symbols = ""  # A stripped library: recorded as unsymbolized, not a failure.
    keep = ("ExceptionHandlerCallback", "signal_handler", "g_seh_initialized")
    (native / "runtime.symbols.txt").write_text("".join(l + "\n" for l in symbols.splitlines() if any(k in l for k in keep)),
                                                encoding="utf-8", newline="\n")
    row["artifacts"] = {n: sha((native / n).read_bytes()) for n in NATIVE_NAMES}
    require(row["artifacts"]["lrso_tests.elf"] == exe_sha, "executable changed during inspection")
    text = {n: (native / n).read_text(encoding="utf-8") for n in TEXT_NAMES}
    row["object_checks"] = binary_checks(text)
    row["runs"], row["traced_positive"], row["traced_fatal"] = [], [], []
    plan = [("default", args.repeats), ("default-originals", args.repeats), ("latch", args.repeats),
            ("latch-cycles", args.cycles_repeats)]
    summaries = []
    for mode, count in plan:
        for i in range(count):
            run = run_untraced(exe, mode, out, f"{key}_{mode}_{i}")
            row["runs"].append(run)
            summaries.append(L.checked(run, lambda r: validate_untraced(r, run_text(r, lambda p: (out / p).read_bytes()))))
    for i in range(args.traced_repeats):
        run = run_traced(exe, TRACED_POSITIVE, out, f"{key}_{TRACED_POSITIVE}_{i}", secrets.token_hex(16),
                         row["traced_positive"])
        summaries.append(L.checked(run, lambda r: validate_traced_positive(r, run_text(r, lambda p: (out / p).read_bytes()))))
    for i in range(args.traced_repeats):
        for mode in FATAL_LRSO:
            run = run_traced(exe, mode, out, f"{key}_{mode}_{i}", secrets.token_hex(16), row["traced_fatal"])
            summaries.append(L.checked(run, lambda r: validate_traced_fatal(r, run_text(r, lambda p: (out / p).read_bytes()))))
    row["cross_run"] = check_cross_run(summaries, text["runtime.symbols.txt"])
    require(sha(exe.read_bytes()) == exe_sha, "binary changed during runs")
    row["status"] = "PASS"


def lrb_regression(out, key, cxx, cc, opt, prefix, row):
    """The audited LRB test rebuilt exactly as the LRB/LWR gates build it; closure digests must reproduce."""
    row["cxx_version"] = L.command([cxx, "--version"], row["commands"])
    base = out / "regression"
    build = base / "lrb" / key
    if build.exists():
        shutil.rmtree(build)
    W.configure_and_build(HERE.parent / "linux_runtime_bootstrap", build, cxx, cc, prefix,
                          ["-DLRB_OPT=" + opt, "-DLRB_ORDINARY_ONLY=OFF"], row["commands"])
    exe = build / "lrb_tests"
    row["executable_sha256"] = sha(exe.read_bytes())
    row["owner_sha256"] = sha((build / "CMakeFiles/lrb_tests.dir/lrb_owner.c.o").read_bytes())
    W.check_closure("lrb", key, "lrb_tests.elf", row["executable_sha256"], row["cxx_version"])
    W.check_closure("lrb", key, "lrb_owner.o", row["owner_sha256"], row["cxx_version"])
    for i in range(REGRESSION_RUNS):
        run = L.run_plain([exe], "normal", base / "lrb", f"{key}_normal_{i}")
        row["normal"].append(run)
        L.checked(run, L.validate_normal)


def run_native(args):
    require(platform.system() == "Linux" and platform.machine() == "x86_64" and struct.calcsize("P") == 8,
            "native Linux x86-64 required; no Windows/WSL fallback")
    register_fatal()
    # The inspected installed librexruntime.so must be the one the children load.
    loader = {k: os.environ.pop(k) for k in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT") if k in os.environ}
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sdk, prefix = args.sdk.resolve(), args.prefix.resolve()
    result = {"status": "INCOMPLETE", "platform": platform.platform(), "machine": platform.machine(),
              "kernel": platform.release(), "python": sys.version, "repeats": args.repeats,
              "cycles_repeats": args.cycles_repeats, "traced_repeats": args.traced_repeats, "configurations": [],
              "regression": {"lrb": []}, "loader_environment_removed": sorted(loader)}
    before_names = L.shm_names()
    result["shm_snapshot"] = {"before": before_names}
    try:
        manifest, identity = source_identity()
        result.update(identity=identity, source_manifest=manifest)
        sdk_info = L.sdk_identity(sdk, prefix)
        lrso_info = lrso_sdk_identity(sdk, prefix)
        result["sdk_identity"], result["lrso_sdk_files"] = sdk_info, lrso_info
        result["source_contract"] = source_contract(sdk)
        compilers = {}
        for cxx_name, cc_name, opt in L.CONFIGS:
            cxx, cc = shutil.which(cxx_name), shutil.which(cc_name)
            require(cxx and cc, "missing compiler pair " + cxx_name)
            key = f"{cxx_name}_O{opt}"
            compilers[key] = (cxx, cc, opt)
            row = {"key": key, "status": "INCOMPLETE", "commands": []}
            result["configurations"].append(row)
            native_config(out, key, cxx, cc, opt, prefix, args, row)
        for key, (cxx, cc, opt) in compilers.items():
            row = {"key": key, "status": "INCOMPLETE", "commands": [], "normal": []}
            result["regression"]["lrb"].append(row)
            lrb_regression(out, key, cxx, cc, opt, prefix, row)
            row["status"] = "PASS"
        names = L.shm_names()
        ours = set()
        for row in result["configurations"]:
            for r in row["runs"] + row["traced_positive"] + row["traced_fatal"]:
                if isinstance(r.get("ownership"), dict) and isinstance(r["ownership"].get("shm_name"), str):
                    ours.add(r["ownership"]["shm_name"])
        for row in result["regression"]["lrb"]:
            for r in row["normal"]:
                if isinstance(r.get("ownership"), dict) and isinstance(r["ownership"].get("shm_name"), str):
                    ours.add(r["ownership"]["shm_name"])
        result["shm_snapshot"].update(after=names, foreign_new=sorted(set(names) - set(before_names) - ours),
                                      own_left=sorted(set(names) & ours))
        require(not result["shm_snapshot"]["own_left"], "own shm residue left")
        require(L.sdk_identity(sdk, prefix) == sdk_info and lrso_sdk_identity(sdk, prefix) == lrso_info,
                "SDK changed during run")
        require(source_identity() == (manifest, identity), "sources changed during run")
        result["positive_checks"] = validate_results({**result, "status": "PASS"}, lambda p: (out / p).read_bytes())
        result["status"] = "PASS"
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        (out / "regression").mkdir(exist_ok=True)
        (out / "regression/regression.json").write_text(json.dumps(result["regression"], indent=2) + "\n",
                                                        encoding="utf-8", newline="\n")
    n, c, t = args.repeats, args.cycles_repeats, args.traced_repeats
    print(f"LRSO_GATE PASS configurations=4 untraced={4 * (3 * n + c)} traced_positive={4 * t} "
          f"traced_fatal={4 * len(FATAL_LRSO) * t} facts={len(result['source_contract']['facts'])} regression=PASS; "
          "independent audit still required")


# ------------------------------------------------------------------ evidence and audit

def package_evidence(out, path, failure):
    out = out.resolve()
    entries = {}
    results = out / "results.json"
    if results.exists():
        entries["results.json"] = results.read_bytes()
        if not failure:
            require(read_json(entries["results.json"]).get("status") == "PASS", "results status is not PASS")
    elif not failure:
        raise GateError("results.json missing")
    for src in sorted((out / "native").rglob("*")) if (out / "native").is_dir() else []:
        if src.is_file():
            entries[src.relative_to(out).as_posix()] = src.read_bytes()
    for src in sorted((out / "records").glob("*.txt")) if (out / "records").is_dir() else []:
        entries["records/" + src.name] = src.read_bytes()
    if (out / "regression/regression.json").exists():
        entries["regression/regression.json"] = (out / "regression/regression.json").read_bytes()
    for name in ("SOURCE_MANIFEST.json", "IMPLEMENTATION_ID.json"):
        if (ROOT / name).exists():
            entries[name] = (ROOT / name).read_bytes()
    for name in ("console.log", "validator.log"):
        if (out / name).exists():
            entries[name] = (out / name).read_bytes()
    entries["PRIVATE.txt"] = (b"PRIVATE: SDK-linked ELF/object bytes and dumps. Keep under private/work/linux_runtime_setup/; "
                              b"never commit, publish or upload.\n")
    if failure:
        own = out / "ownership"
        for p in sorted(own.glob("*.json")) if own.is_dir() else []:
            entries["ownership/" + p.name] = p.read_bytes()
        entries["FAILURE.txt"] = b"INCOMPLETE/FAILED native LRSO evidence; not a PASS claim.\n"
    require(entries, "nothing to package")
    for name, data in entries.items():
        require(b"\nDEFINE_REX_FUNC(" not in data, "generated code in the evidence: " + name)
    entries["EVIDENCE_MANIFEST.json"] = (json.dumps({n: sha(b) for n, b in sorted(entries.items())}, indent=2) + "\n").encode()
    digest = L.write_zip(path, entries)
    print(f"LRSO_EVIDENCE {'FAILURE' if failure else 'PASS'} entries={len(entries)} sha256={digest} path={path} "
          "(PRIVATE: SDK-linked bytes; keep under private/work/linux_runtime_setup/)")


def audit(archive, implementation, sdk):
    register_fatal()
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) and z.testzip() is None, "archive integrity")
        data = {n: z.read(n) for n in names}
    require("FAILURE.txt" not in data, "failure bundle is not PASS evidence")
    require(not any(n.endswith((".cpp", ".h")) for n in data), "no source or generated code in evidence")
    require(not any(b"\nDEFINE_REX_FUNC(" in b for b in data.values()), "no generated function definitions in evidence")
    manifest = read_json(data["EVIDENCE_MANIFEST.json"])
    require(set(manifest) == set(data) - {"EVIDENCE_MANIFEST.json"}, "evidence inventory")
    require(all(sha(data[n]) == h for n, h in manifest.items()), "evidence digest mismatch")
    identity = read_json(data["IMPLEMENTATION_ID.json"])
    require(identity["commit"] == implementation, "implementation commit mismatch")
    source = read_json(data["SOURCE_MANIFEST.json"])
    require(sorted(source) == source_files(), "transferred source inventory")
    for name, digest in source.items():
        blob = G.git("show", f"{implementation}:{name}").replace(b"\r\n", b"\n")
        require(sha(blob) == digest, "transferred source differs from Git: " + name)
    result = read_json(data["results.json"])
    require(result["identity"] == identity and result["source_manifest"] == source, "result source identity")
    require(result["sdk_identity"]["sdk"] == SDK_PIN and result["sdk_identity"]["simde"] == L.SIMDE_PIN, "SDK pins")
    for name, digest in result["sdk_identity"]["sources_sha256_lf"].items():
        require(sha(pinned_bytes(sdk, name)) == digest, "SDK source identity differs from pin: " + name)
    require(sorted(result["lrso_sdk_files"]) == sorted(LRSO_SDK_FILES), "LRSO SDK file inventory")
    for name, digest in result["lrso_sdk_files"].items():
        require(sha(pinned_bytes(sdk, name)) == digest, "LRSO SDK file differs from pin: " + name)
    require(result["source_contract"] == source_contract(sdk), "source contract differs from the pinned blobs")
    def reader(name):
        require(name in data, "missing archive entry " + name)
        return data[name]

    checks = validate_results(result, reader)
    require("regression/regression.json" in data and read_json(data["regression/regression.json"]) == result["regression"],
            "regression results archived")
    print(f"LRSO_AUDIT PASS configurations=4 modes={len(checks)} entries={len(data)} "
          f"facts={len(result['source_contract']['facts'])}; root disassembly review still required")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("source-contract"); c.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    s = sub.add_parser("source"); s.add_argument("--zip", type=Path, required=True)
    r = sub.add_parser("run")
    r.add_argument("--sdk", type=Path, required=True); r.add_argument("--prefix", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--repeats", type=int, default=5); r.add_argument("--cycles-repeats", type=int, default=3)
    r.add_argument("--traced-repeats", type=int, default=2)
    e = sub.add_parser("evidence"); e.add_argument("--out", type=Path, required=True)
    e.add_argument("--zip", type=Path, required=True); e.add_argument("--failure", action="store_true")
    a = sub.add_parser("audit"); a.add_argument("--archive", type=Path, required=True)
    a.add_argument("--implementation", required=True); a.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    args = ap.parse_args()
    if args.cmd == "source-contract":
        facts = source_contract(args.sdk.resolve())
        print(f"LRSO_SOURCE_CONTRACT PASS facts={len(facts['facts'])} sdk={facts['sdk']}")
    elif args.cmd == "source":
        package_source(args.zip.resolve())
    elif args.cmd == "run":
        require(min(args.repeats, args.cycles_repeats, args.traced_repeats) >= 1, "positive repetition counts")
        run_native(args)
    elif args.cmd == "evidence":
        package_evidence(args.out, args.zip.resolve(), args.failure)
    else:
        audit(args.archive, args.implementation, args.sdk.resolve())


if __name__ == "__main__":
    try:
        main()
    except GateError as error:
        print(f"LRSO_GATE FAIL: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:  # Unexpected runner fault: keep the traceback, still a FAIL.
        traceback.print_exc()
        print(f"LRSO_GATE FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
