"""Linux Runtime Generated Dispatch (LRGD): source contract, private check, Windows reference, native gate, audit.

Subcommands:
  source-contract  (any) check the pinned SDK blobs (never the working tree) for the dispatcher/Setup/table facts the
                   experiment relies on (plus the unchanged LRSO facts).
  private-check    (any) verify the unchanged LGE private extract and that its production layout equals the constants in
                   lrgd_tests.cpp (and, on the Windows host, the production r3hd_init.cpp rows and codegen flags).
  windows          (Windows, inside tools\\devenv.bat) build/run default-dispatch with clang O0/O2 against the existing
                   SDK install and write the PRIVATE LRGD reference.
  check-run        (any, read-only) validate one existing run directory against the references.
  private-zip      (any) package the PRIVATE LRGD reference for the CachyOS handoff.
  source           (any) write the source-only CachyOS ZIP from committed Git bytes (no generated code).
  run              (Linux x86-64 only) build Clang/GCC O0/O2 and run the LRGD matrix.
  evidence         (Linux) package results, own ELF/object bytes, records and dumps.  The ZIP is PRIVATE.
  audit            (any, read-only) re-derive every validator and binary check from a returned evidence ZIP.

Never builds, patches or installs the SDK; never launches the game; removes only /dev/shm objects proven to belong to its
own child.  The children run the real pinned rex::Runtime::Setup(PPCImageInfo) in tool mode and dispatch the audited
LGE/LWR cases through the real FunctionDispatcher::Execute.
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
REL = "tools/experiments/linux_runtime_dispatch/"
sys.path.insert(0, str(HERE.parent / "linux_runtime_setup"))
import lrso_gate as S  # noqa: E402  (audited LRSO gate; unchanged)

W = S.W  # audited LWR gate (tracer, object checks, packaging helpers)
G = S.G  # audited LGE gate (case parsing, generated-object checks)
L = S.L  # audited LRB gate (runner primitives)
GateError, require, sha, lf, read_json = L.GateError, L.require, L.sha, L.lf, L.read_json
OWN_FILES = ["CMakeLists.txt", "README.md", "lrgd_tests.cpp", "lrgd_gate.py", "test_lrgd_gate.py"]
DEFAULT_SDK = ROOT / "external/rexglue-sdk"
PRIVATE = ROOT / "private/work/linux_runtime_dispatch"
WINDOWS_WORK = PRIVATE / "windows"
REFERENCE_NAME = "lrgd_windows_reference.json"
LGE_PRIVATE = W.LGE_PRIVATE
LGE_REFERENCE = LGE_PRIVATE / "windows_reference.json"
LWR_REFERENCE = W.PRIVATE / W.REFERENCE_NAME
DEFAULT_INIT = ROOT / "private/work/rex/generated/default/r3hd_init.cpp"
DEFAULT_PREFIX = G.DEFAULT_WIN_PREFIX
SDK_PIN = L.SDK_PIN
CR, LF = chr(13), chr(10)
CONFIG_KEYS = S.CONFIG_KEYS
CPP = HERE / "lrgd_tests.cpp"

# ------------------------------------------------------------------ modes and constants

POSITIVE = ["default-dispatch", "latch", "latch-cycles"]
TRACED_POSITIVE = "latch-traced-positive"
FATAL_LRGD = ["lrgd-write-guard", "lrgd-unregistered-page", "lrgd-unauthorized", "lrgd-wrong-function"]
# mode -> (variant, cycles)
MODES = {"default-dispatch": ("default", 1), "latch": ("latch", 1), "latch-cycles": ("latch", 2),
         TRACED_POSITIVE: ("latch", 1), **{m: ("latch", 1) for m in FATAL_LRGD}}
LGE_COUNT, LWR_COUNT = 124, 8
# FunctionDispatcher::Execute calls per cycle: 1 negative + 2 passes x (124 LGE + 8 LWR [x2 when also watched]).
DISPATCHES = {"default": 265, "latch": 281}
CLAIMS_PER_CYCLE = 2 * W.TOTAL_CLAIMS  # both passes run the LWR cases watched in the latch variants
MAPPINGS = [(0x820E6D08, "sub_820E6D08"), (0x820E7328, "sub_820E7328"), (0x820E73CC, "__savegprlr_29"),
            (0x820E741C, "__restgprlr_29"), (0x820E7440, "sub_820E7440"), (0x820E78A0, "sub_820E78A0"),
            (0x820EB350, "sub_820EB350"), (0x820EB7D8, "sub_820EB7D8"), (0x820F0A28, "sub_820F0A28"),
            (0x820F7978, "sub_820F7978")]
CODE_BASE, CODE_SIZE, IMAGE_BASE, IMAGE_SIZE = 0x820E0000, 0x007425E4, 0x82000000, 0x00CE0000
THUNK_RESERVE = 0x10000
TABLE_BASE = IMAGE_BASE + IMAGE_SIZE
TABLE_SIZE = (CODE_SIZE + THUNK_RESERVE) * 2
UNREGISTERED = CODE_BASE
WINDOW_POPULATED, WINDOW_EMPTY = 10, 18422  # table slots for guest 0x820E6000..0x820F8000 step 4: 18432 = 10 + 18422
THREAD_ID = 0x4C524744
MEMBASE = 0x100000000
GUARD_ADDRESS = MEMBASE + 0x20011000   # runtime membase + LGE high guard page (0x20000000 + 0x11000)
P4_ADDRESS = MEMBASE + 0xA4004000      # runtime membase + vA alias page 4
VA_REGION = (MEMBASE + 0xA4000000, MEMBASE + 0xA4000000 + 0x10000)
SENTINEL_LR = "00000000bcbcbcbc"
RETURN_LR = "0000000082fff000"
PAD = 64 + 112
NARGS = {"820e7440": 3, "820eb7d8": 3, "820e78a0": 3, "820eb350": 3, "820e7328": 3, "820f7978": 3,
         "820e6d08": 2, "820f0a28": 4}
LR_SLOT_GUEST = "820f7978"
LR_SLOT_OFFSET = 0xFEF8
FILE_NAMES = ["record", "lge", "lwr", "watched", "dispatch", "restart", "claims"]
FILE_ENV = {"record": "LRGD_RECORD_FILE", "lge": "LRGD_LGE_FILE", "lwr": "LRGD_LWR_FILE",
            "watched": "LRGD_LWR_WATCHED_FILE", "dispatch": "LRGD_DISPATCH_FILE", "restart": "LRGD_RESTART_FILE",
            "claims": "LRGD_CLAIMS_FILE"}
OWNER_OBJECTS = ("lrgd_tests", "main")
PCH_NAMES = ["REX_IMAGE_BASE", "REX_IMAGE_SIZE", "REX_CODE_BASE", "REX_CODE_SIZE", "REXCRT_HEAP"]
CODEGEN_FLAGS = ["skip_lr", "ctr_as_local", "xer_as_local", "reserved_as_local", "skip_msr", "cr_as_local",
                 "non_argument_as_local", "non_volatile_as_local"]
REGRESSION_NOTE = "no LRB/LGE regression rebuild: LRGD reuses the audited objects through closure checks"

NATIVE_NAMES = ["lrgd_tests.elf", "lrb_owner.o", "lrb_access.o", "lwr_restart.o", "lrgd_tests.o", "lge_generated.o",
                "final.objdump.txt", "owner.objdump.txt", "restart.objdump.txt", "generated.objdump.txt",
                "generated.nm.txt", "final.readelf.txt", "runtime.dynsym.txt", "runtime.dynamic.txt",
                "runtime.relocs.txt", "runtime.symbols.txt"]
TEXT_NAMES = [n for n in NATIVE_NAMES if n.endswith(".txt")]

LRGD_SDK_FILES = ["include/rex/system/function_dispatcher.h", "include/rex/system/thread_state.h",
                  "resources/templates/codegen/_indirect_call.inja", "src/system/function_dispatcher.cpp",
                  "src/system/runtime.cpp", "src/system/thread_state.cpp", "src/system/xmemory.cpp"]
LOOKUP_TEMPLATE = "resources/templates/codegen/_indirect_call.inja"
LOOKUP_TEXT = "REX_IMAGE_BASE + REX_IMAGE_SIZE + (u64(u32(y) - REX_CODE_BASE) * 2)"
DISPATCH_TOKENS = ["sigaction(", "signal(", "pthread_create(", "std::thread(", "std::jthread(", "Thread::Create(", "throw "]


def register_fatal():
    """Register the LRGD fatal modes with the audited LRB ownership validator (unlink-after-map policy)."""
    L.FATAL = tuple(dict.fromkeys(L.FATAL + tuple(FATAL_LRGD)))


def source_files():
    return sorted({REL + f for f in OWN_FILES} | set(S.source_files()))


# ------------------------------------------------------------------ pinned SDK source contract

def fact_execute_private(text):
    body = S.function_body(text, "bool FunctionDispatcher::Execute(ThreadState* thread_state, uint32_t address) {")
    S.ordered(body, ["PPCFunc* fn = GetFunction(address);", "return false;",
                     "auto* previous_thread_state = ThreadState::Get();", "ThreadState::Bind(thread_state);",
                     "ctx->r1.u64 -= 64 + 112;", "uint64_t previous_lr = ctx->lr;", "ctx->lr = 0xBCBCBCBC;",
                     "fn(*ctx, memory_->virtual_membase());", "ctx->lr = previous_lr;", "ctx->r1.u64 += 64 + 112;",
                     "ThreadState::Bind(previous_thread_state);"], "FunctionDispatcher::Execute(private)")
    return {"pad": "64 + 112", "lr_sentinel": "0xBCBCBCBC", "restores": "r1, lr, ThreadState binding"}


def fact_execute_args(text):
    body = S.function_body(text, "uint64_t FunctionDispatcher::Execute(ThreadState* thread_state, uint32_t address, "
                                 "uint64_t args[],")
    needles = [f"ctx->r{3 + i}.u64 = args[{i}];" for i in range(8)]
    S.ordered(body, needles + ["if (arg_count > 8)", "if (!Execute(thread_state, address))", "return 0xDEADBABE;",
                              "return ctx->r3.u64;"], "FunctionDispatcher::Execute(args)")
    return {"register_args": "r3..r10", "not_found": "0xDEADBABE", "returns": "r3"}


def fact_setup_image(text):
    body = S.function_body(text, "X_STATUS Runtime::Setup(const rex::PPCImageInfo& image_info, RuntimeConfig config) {")
    S.ordered(body, ["X_STATUS status = Setup(std::move(config));", "codegen_flags_ = image_info.codegen_flags;",
                     "InitializeFunctionTable(image_info.code_base, image_info.code_size,", "/*is_entrypoint=*/true",
                     "image_info.func_mappings[i].guest != 0", "function_dispatcher_->SetFunction(guest, host)",
                     "if (rejected > 0)"], "Runtime::Setup(PPCImageInfo)")
    return {"order": "Setup(config), codegen_flags, InitializeFunctionTable(entrypoint), SetFunction rows, reject check"}


def fact_memory_table(text):
    init = S.function_body(text, "bool Memory::InitializeFunctionTable(uint32_t code_base, uint32_t code_size, "
                                 "uint32_t image_base,")
    S.ordered(init, ["uint32_t table_base = image_base + image_size;",
                     "uint32_t table_size = (code_size + kThunkReserveSize) * 2;", "heaps_.v80000000.AllocFixed(",
                     "Zero(table_base, table_size);"], "Memory::InitializeFunctionTable")
    setter = S.function_body(text, "bool Memory::SetFunction(uint32_t guest_address, PPCFunc* host_function) {")
    S.ordered(setter, ["uint64_t offset = (uint64_t(guest_address) - entry.code_base) * 2;", "*slot = host_function;"],
              "Memory::SetFunction")
    return {"table": "image_base + image_size, (code_size + thunk_reserve) * 2, zeroed",
            "slot": "table_base + (guest - code_base) * 2"}


def fact_thread_state(cpp, header, dispatcher_header):
    ctor = S.function_body(cpp, "ThreadState::ThreadState(uint32_t thread_id, uint32_t stack_base, uint32_t pcr_address,")
    S.ordered(ctor, ["context_->r1.u64 = stack_base;", "context_->r13.u64 = pcr_address;"], "ThreadState constructor")
    require("thread_local ThreadState* thread_state_ = nullptr;" in cpp, "thread_state.cpp: binding is not thread_local")
    bind = S.function_body(cpp, "void ThreadState::Bind(ThreadState* thread_state) {")
    require("thread_state_ = thread_state;" in bind, "ThreadState::Bind does not store the binding")
    require("alignas(64)::PPCContext context_storage_{};" in header, "thread_state.h: context storage is not 64-aligned")
    require("static constexpr uint32_t kThunkReserveSize = 0x10000;" in dispatcher_header,
            "function_dispatcher.h: thunk reserve is not 0x10000")
    return {"binding": "thread_local", "context": "alignas(64) storage", "thunk_reserve": "0x10000"}


def fact_resolve_indirect(text):
    require(text.count("PPCFunc* ResolveIndirectFunction(uint32_t guest_address) {") == 1,
            "ResolveIndirectFunction definition")
    getter = S.function_body(text, "FunctionDispatcher* GetBoundFunctionDispatcher() {")
    require("Runtime* runtime = Runtime::instance();" in getter, "GetBoundFunctionDispatcher does not use Runtime::instance()")
    resolve = S.function_body(text, "PPCFunc* ResolveIndirectFunction(uint32_t guest_address) {")
    S.ordered(resolve, ["GetBoundFunctionDispatcher();", "dispatcher->GetFunction(guest_address)", "InvalidFunctionTrap"],
              "ResolveIndirectFunction")
    return {"binding": "Runtime::instance()->function_dispatcher()->GetFunction"}


def fact_prelude_lookup(template_files, template_text):
    require(template_files == [LOOKUP_TEMPLATE], f"codegen lookup text occurs in {template_files}, expected [{LOOKUP_TEMPLATE}]")
    S.ordered(template_text, ["#define REX_LOOKUP_FUNC(x, y)", "(*(PPCFunc**)(x + " + LOOKUP_TEXT + ")"], "codegen lookup macro")
    return {"template": LOOKUP_TEMPLATE, "lookup": LOOKUP_TEXT}


def fact_dispatch_inventory(texts):
    counts = {t: {p: texts[p].count(t) for p in sorted(texts)} for t in DISPATCH_TOKENS}
    for token, per_file in counts.items():
        require(all(n == 0 for n in per_file.values()), f"dispatch path contains {token!r}: {per_file}")
    return counts


def source_contract(sdk, pin=SDK_PIN):
    """Every fact from the pinned blobs only (the working tree carries Windows patches)."""
    sdk = Path(sdk)
    lrso = S.source_contract(sdk, pin)
    text = {p: S.pinned_text(sdk, p, pin) for p in LRGD_SDK_FILES}
    template_files = S.pinned_grep_files(sdk, [LOOKUP_TEXT], ["resources"], pin)
    facts = {
        "a_execute_private": fact_execute_private(text["src/system/function_dispatcher.cpp"]),
        "b_execute_args": fact_execute_args(text["src/system/function_dispatcher.cpp"]),
        "c_setup_image": fact_setup_image(text["src/system/runtime.cpp"]),
        "d_memory_table": fact_memory_table(text["src/system/xmemory.cpp"]),
        "e_thread_state": fact_thread_state(text["src/system/thread_state.cpp"], text["include/rex/system/thread_state.h"],
                                            text["include/rex/system/function_dispatcher.h"]),
        "f_resolve_indirect": fact_resolve_indirect(text["src/system/function_dispatcher.cpp"]),
        "g_prelude_lookup": fact_prelude_lookup(template_files, text[LOOKUP_TEMPLATE]),
        "h_dispatch_inventory": fact_dispatch_inventory({p: text[p] for p in ("src/system/function_dispatcher.cpp",
                                                                              "src/system/thread_state.cpp")}),
    }
    return {"sdk": pin, "facts": facts, "lrso": lrso}


def fact_count(contract):
    return len(contract["facts"]) + len(contract["lrso"]["facts"])


def lrgd_sdk_identity(sdk, prefix):
    files = {}
    for name in LRGD_SDK_FILES:
        expected = S.pinned_bytes(sdk, name)
        require(lf(sdk / name) == expected, "SDK source differs from the pin: " + name)
        if name.startswith("include/"):
            require(lf(prefix / name) == expected, "installed header differs from the pin: " + name)
        files[name] = sha(expected)
    return files


# ------------------------------------------------------------------ private identity and production layout

def parse_pch(text):
    """The five production layout defines of the private r3hd_pch.h, each defined exactly once."""
    out = {}
    text = text.replace("\r\n", "\n")
    for name in PCH_NAMES:
        found = re.findall(rf"^#define {name} (\S+)[ \t]*$", text, re.M)
        require(len(found) == 1, f"r3hd_pch.h must define {name} exactly once")
        m = re.fullmatch(r"(0x[0-9a-fA-F]+|[0-9]+)(?:ull|ULL|ul|UL|u|U)?", found[0])
        require(m is not None, f"r3hd_pch.h {name} is not an integer literal: {found[0]}")
        out[name] = int(m.group(1), 0)
    return out


def parse_cpp_constants(text):
    """The layout constants committed in lrgd_tests.cpp (production values)."""
    out = {}
    for cpp_name, pch_name in (("kImageBase", "REX_IMAGE_BASE"), ("kImageSize", "REX_IMAGE_SIZE"),
                               ("kCodeBase", "REX_CODE_BASE"), ("kCodeSize", "REX_CODE_SIZE")):
        found = re.findall(rf"^constexpr uint32_t {cpp_name} = (0x[0-9A-Fa-f]+)u;", text, re.M)
        require(len(found) == 1, f"lrgd_tests.cpp must define {cpp_name} exactly once")
        out[pch_name] = int(found[0], 16)
    require(len(re.findall(r"^\s*info\.rexcrt_heap = false;", text, re.M)) == 1, "lrgd_tests.cpp rexcrt_heap is not false")
    out["REXCRT_HEAP"] = 0
    return out


def parse_cpp_mappings(text):
    rows = re.findall(r"\{(0x[0-9A-F]{8})u, (\w+), \"(\w+)\"\}", text)
    require(all(sym == name for _, sym, name in rows), "lrgd_tests.cpp mapping symbol/name differ")
    got = [(int(g, 16), sym) for g, sym, _ in rows]
    require(got == MAPPINGS, f"lrgd_tests.cpp kMappings differ from the gate's production rows: {got}")
    return got


def check_init(text):
    """The production r3hd_init.cpp (Windows host only): the ten rows and the eight false codegen flags."""
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    for guest, symbol in MAPPINGS:
        row = f"\t{{ 0x{guest:08X}, {symbol} }},"
        require(lines.count(row) == 1, f"production init lacks exactly one row {row.strip()}")
    for flag in CODEGEN_FLAGS:
        require(len(re.findall(rf"^\s*\.{flag} = false,\s*$", text, re.M)) == 1, f"production codegen flag {flag} is not false")
    require(len(re.findall(r"^\s*\.rexcrt_heap = REXCRT_HEAP,\s*$", text, re.M)) == 1, "production init rexcrt_heap")
    return {"rows": len(MAPPINGS), "flags": len(CODEGEN_FLAGS)}


def private_check(private_dir, production_init=None):
    """Unchanged LGE private extract + production layout identity; never writes."""
    private_dir = Path(private_dir)
    manifest, _ = G.private_identity(private_dir)
    result = {"generated_manifest_sha256": sha((private_dir / "GENERATED_MANIFEST.json").read_bytes()),
              "files": manifest["files"]}
    zip_path = private_dir.parent / "lge-private-generated.zip"
    sidecar = private_dir.parent / "lge-private-generated.zip.sha256"
    if zip_path.is_file() and sidecar.is_file():
        want = sidecar.read_text(encoding="ascii").split()
        require(len(want) == 2 and want[1] == zip_path.name and want[0] == sha(zip_path.read_bytes()),
                "LGE private ZIP differs from its .sha256 sidecar")
        result["private_zip_sha256"] = want[0]
    else:
        result["private_zip_sha256"] = None
    pch = parse_pch((private_dir / "r3hd_pch.h").read_bytes().decode("utf-8"))
    cpp_text = lf(CPP).decode("utf-8")
    constants = parse_cpp_constants(cpp_text)
    require(pch == constants, f"private r3hd_pch.h layout {pch} differs from lrgd_tests.cpp {constants}")
    require((pch["REX_IMAGE_BASE"], pch["REX_IMAGE_SIZE"], pch["REX_CODE_BASE"], pch["REX_CODE_SIZE"])
            == (IMAGE_BASE, IMAGE_SIZE, CODE_BASE, CODE_SIZE), "gate layout constants differ from the private pch")
    parse_cpp_mappings(cpp_text)
    result["pch"] = pch
    result["init_sha256"] = None
    if production_init is not None and Path(production_init).is_file():
        data = Path(production_init).read_bytes()
        result["init"] = check_init(data.decode("utf-8"))
        result["init_sha256"] = sha(data)
    return result


# ------------------------------------------------------------------ canonical-line parsing and re-derivation

MASK64 = (1 << 64) - 1
STATE_KEYS = [f"r{i}" for i in range(32)] + ["lr", "ctr", "xer", "cr"]
STATE_WIDTH = {**{f"r{i}": 16 for i in range(32)}, "lr": 16, "ctr": 16, "xer": 6, "cr": 64}
RAW_FIELDS = ("suite", "watched", "pass", "id", "guest", "nargs", "ret", "pre", "entry", "post", "bound", "ctx",
              "entry_ctx", "lr_slot", "raw_changed", "raw_delta", "trace", "canonical")
FIXED_TOKENS = {"bound": "thread_state", "ctx": "thread_state", "entry_ctx": "input+lr_sentinel"}


def parse_state(text, what):
    tokens = text.split(" ")
    require(len(tokens) == len(STATE_KEYS), f"{what}: integer state token count")
    state = {}
    for key, token in zip(STATE_KEYS, tokens):
        require(token.startswith(key + "="), f"{what}: integer state key order at {key}")
        value = token[len(key) + 1:]
        require(re.fullmatch(r"[0-9a-f]{%d}" % STATE_WIDTH[key], value) is not None, f"{what}: {key} is malformed")
        state[key] = value
    return state


def fmt_state(state):
    return " ".join(f"{key}={state[key]}" for key in STATE_KEYS)


def h16(value):
    return f"{value & MASK64:016x}"


def parse_delta(text, what):
    """`offset:hexbytes,...` -> {offset: byte}; a repeated byte offset is malformed."""
    out = {}
    if text == "":
        return out
    for part in text.split(","):
        m = re.fullmatch(r"([0-9a-f]+):((?:[0-9a-f]{2})+)", part)
        require(m is not None, f"{what}: malformed delta part {part[:40]!r}")
        offset = int(m.group(1), 16)
        for k, byte in enumerate(bytes.fromhex(m.group(2))):
            require(offset + k not in out, f"{what}: overlapping delta bytes")
            out[offset + k] = byte
    return out


def parse_dispatch_line(line):
    prefix = "LRGD_CASE_V1|"
    require(line.startswith(prefix), "dispatch record prefix")
    parts = line[len(prefix):].split("|")
    require(len(parts) == len(RAW_FIELDS), "dispatch record field count")
    fields = {}
    for part, name in zip(parts, RAW_FIELDS):
        require(part.startswith(name + "="), "dispatch record field order: " + name)
        fields[name] = part[len(name) + 1:]
    return fields


def check_row(row, ref):
    """Re-derive one dispatch row from its reference case (the reference is the audited Windows result)."""
    cid = ref["id"]
    require(row["id"] == cid and row["guest"] == ref["guest"], f"{cid}: row identity differs from the reference")
    require(ref["fn"] == "sub_" + ref["guest"].upper(), f"{cid}: reference function/guest mismatch")
    require(row["pass"] == "1", f"{cid}: only pass 1 is recorded")
    for name, value in FIXED_TOKENS.items():
        require(row[name] == value, f"{cid}: fixed token {name}")
    nargs = NARGS.get(row["guest"])
    require(nargs is not None and row["nargs"] == str(nargs), f"{cid}: argument count for guest {row['guest']}")
    before, after = parse_state(ref["before"], cid + " reference before"), parse_state(ref["after"], cid + " reference after")
    pre, entry, post = (parse_state(row[k], f"{cid} {k}") for k in ("pre", "entry", "post"))
    # entry: the callee sees the LGE input with only lr replaced by the dispatcher sentinel.
    require(entry["lr"] == SENTINEL_LR, f"{cid}: entry lr is not the dispatcher sentinel")
    require({**entry, "lr": RETURN_LR} == before, f"{cid}: entry differs from the reference input beyond lr")
    # pre: reference input, r1 + padding, argument registers poisoned with their complement.
    want_pre = dict(before)
    want_pre["r1"] = h16(int(before["r1"], 16) + PAD)
    for i in range(nargs):
        key = f"r{3 + i}"
        want_pre[key] = h16(~int(before[key], 16))
    require(pre == want_pre, f"{cid}: pre differs from the derived pre-Execute context")
    # post: Execute restored r1 and the caller lr; the reference 'after' is post with r1 - padding (+ the r12 LR note).
    require(post["r1"] == pre["r1"] and post["lr"] == pre["lr"], f"{cid}: Execute did not restore r1/lr")
    want_after = dict(post)
    want_after["r1"] = h16(int(post["r1"], 16) - PAD)
    slot = row["lr_slot"]
    require(slot == (f"{LR_SLOT_OFFSET:x}" if row["guest"] == LR_SLOT_GUEST else "-"), f"{cid}: lr_slot")
    if slot != "-":
        require(post["r12"] == SENTINEL_LR, f"{cid}: r12 does not hold the observed dispatcher sentinel")
        want_after["r12"] = RETURN_LR
    require(want_after == after, f"{cid}: reference 'after' differs from the derived post state")
    require(re.fullmatch(r"[0-9a-f]{16}", row["ret"]) is not None and row["ret"] == post["r3"],
            f"{cid}: ret is not post r3")
    # memory delta: identical outside the declared LR slot; inside it only the sentinel / return-LR bytes.
    raw, norm = parse_delta(row["raw_delta"], cid + " raw"), parse_delta(ref["delta"], cid + " reference")
    require(re.fullmatch(r"[0-9]+", row["raw_changed"]) is not None and int(row["raw_changed"]) == len(raw),
            f"{cid}: raw_changed is not the raw delta byte count")
    require(re.fullmatch(r"[0-9]+", ref["changed"]) is not None and int(ref["changed"]) == len(norm),
            f"{cid}: reference changed is not its delta byte count")
    inside = range(LR_SLOT_OFFSET, LR_SLOT_OFFSET + 4)
    require({k: v for k, v in raw.items() if k not in inside} == {k: v for k, v in norm.items() if k not in inside},
            f"{cid}: raw and reference deltas differ outside the LR slot")
    if slot == "-":
        require(raw == norm, f"{cid}: raw and reference deltas differ")
    else:
        sentinel, restored = bytes.fromhex("bcbcbcbc"), bytes.fromhex("82fff000")
        for k in inside:
            require(k not in raw or raw[k] == sentinel[k - LR_SLOT_OFFSET], f"{cid}: raw LR slot byte is not the sentinel")
            require(k not in norm or norm[k] == restored[k - LR_SLOT_OFFSET], f"{cid}: normalized LR slot byte is not the LR")
    require(row["trace"] == ref["trace"], f"{cid}: entered-function trace differs from the reference")
    require(row["canonical"] == ref["digest"], f"{cid}: canonical digest differs from the reference digest")


def rederive(dispatch_lines, lge_ref_lines, lwr_ref_lines, native_watched):
    """Field-by-field re-derivation of every raw dispatch record from the audited reference cases.

    File order: the 124 LGE rows (watched=0), then per LWR case its watched=0 row, followed (watched run only)
    by its watched=1 row."""
    require(len(lge_ref_lines) == LGE_COUNT and len(lwr_ref_lines) == LWR_COUNT, "reference case counts")
    plan = [("lge", G.parse_case(line), "0") for line in lge_ref_lines]
    for line in lwr_ref_lines:
        case = W.parse_case(line)
        plan.append(("lwr", case, "0"))
        if native_watched:
            plan.append(("lwr", case, "1"))
    require(len(dispatch_lines) == len(plan), f"dispatch row count {len(dispatch_lines)} != {len(plan)}")
    previous = None
    for line, (suite, ref, watched) in zip(dispatch_lines, plan):
        row = parse_dispatch_line(line)
        require(row["suite"] == suite and row["watched"] == watched, f"{ref['id']}: suite/watched sequence")
        check_row(row, ref)
        if watched == "1":
            require({k: v for k, v in row.items() if k != "watched"} == {k: v for k, v in previous.items() if k != "watched"},
                    f"{ref['id']}: watched row differs from its ordinary row")
        previous = row
    return {"lge": LGE_COUNT, "lwr": LWR_COUNT, "rows": len(plan), "watched_rows": LWR_COUNT if native_watched else 0,
            "lr_slot_rows": sum(1 for _, c, _ in plan if c["guest"] == LR_SLOT_GUEST)}


# ------------------------------------------------------------------ references

def make_refs(lge_text, lwr_text):
    require(isinstance(lge_text, str) and isinstance(lwr_text, str), "reference case texts")
    lge, lwr = G.parse_cases(lge_text.encode("ascii")), W.parse_cases(lwr_text.encode("ascii"))
    require(len(lge) == LGE_COUNT and len(lwr) == LWR_COUNT, "reference case counts")
    return {"lge_text": lge_text, "lwr_text": lwr_text, "lge_lines": lge_text[:-1].split("\n"),
            "lwr_lines": lwr_text[:-1].split("\n"), "lge_aggregate": G.aggregate(lge), "lwr_aggregate": W.aggregate(lwr)}


def load_raw_references(lge_path, lwr_path):
    lge = read_json(Path(lge_path).read_bytes())
    require(lge.get("format") == "LGE_REFERENCE_V1", "LGE reference format")
    data = lge["cases_text"].encode("ascii")
    require(sha(data) == lge["cases_sha256"] and G.aggregate(G.parse_cases(data)) == lge["aggregate"], "LGE reference identity")
    lwr = read_json(Path(lwr_path).read_bytes())
    W.check_reference(lwr)
    refs = make_refs(lge["cases_text"], lwr["cases_text"])
    require(refs["lge_aggregate"] == lge["aggregate"] and refs["lwr_aggregate"] == lwr["aggregate"], "reference aggregates")
    return refs


def check_lrgd_reference(reference):
    """Self-consistency of an LRGD_REFERENCE_V1 document; returns the case references."""
    require(reference.get("format") == "LRGD_REFERENCE_V1", "LRGD reference format")
    refs = make_refs(reference["lge_cases_text"], reference["lwr_cases_text"])
    require(sha(reference["lge_cases_text"].encode()) == reference["lge_cases_sha256"]
            and sha(reference["lwr_cases_text"].encode()) == reference["lwr_cases_sha256"], "LRGD reference case digests")
    require(refs["lge_aggregate"] == reference["lge_aggregate"] and refs["lwr_aggregate"] == reference["lwr_aggregate"],
            "LRGD reference aggregates")
    require(sha(reference["dispatch_text"].encode()) == reference["dispatch_sha256"], "LRGD reference dispatch digest")
    rederive(reference["dispatch_text"][:-1].split("\n"), refs["lge_lines"], refs["lwr_lines"], False)
    validate_records("default-dispatch", reference["records_text"], False)
    return refs


def load_references(path=None, lge_path=None, lwr_path=None):
    """The LRGD reference when given/present, else the two audited raw references."""
    if path is not None:
        reference = read_json(Path(path).read_bytes())
        if reference.get("format") == "LRGD_REFERENCE_V1":
            return check_lrgd_reference(reference), reference
        raise GateError("not an LRGD_REFERENCE_V1 document: " + str(path))
    return load_raw_references(lge_path or LGE_REFERENCE, lwr_path or LWR_REFERENCE), None


# ------------------------------------------------------------------ record validation

SIG_RE = re.compile(S.SIG_RE.pattern.replace("LRSO_", "LRGD_"))
THREADS_RE = re.compile(S.THREADS_RE.pattern.replace("LRSO_", "LRGD_"))
LATCH_RE = re.compile(S.LATCH_RE.pattern.replace("LRSO_", "LRGD_"))
RUNTIME_NATIVE = re.compile(r"LRGD_RUNTIME_V1\|mode=([a-z-]+)\|cycle=(\d+)\|setup_status=(0x[0-9a-f]+)\|instance=1"
                            r"\|kernel_shared=1\|mmio=1\|dispatcher=1\|membase=(0x[0-9a-f]+)\|tool_mode=1"
                            r"\|shm=(/xenia_memory_[0-9]+)\|inode=(\d+)\|device=(\d+)\|allocated=(\d+)")
RUNTIME_PLAIN = re.compile(r"LRGD_RUNTIME_V1\|mode=([a-z-]+)\|cycle=(\d+)\|setup_status=(0x[0-9a-f]+)\|instance=1"
                           r"\|kernel_shared=1\|mmio=1\|dispatcher=1\|tool_mode=1")
EXACT_KINDS = {"LRGD_REG_V1": "REG", "LRGD_IMAGE_V1": "IMAGE", "LRGD_THREAD_STATE_V1": "THREAD_STATE",
               "LRGD_NEGATIVE_V1": "NEGATIVE", "LRGD_PASS_V1": "PASS", "LRGD_DISPATCH_V1": "DISPATCH",
               "LRGD_TEARDOWN_V1": "TEARDOWN", "LRGD_HANDOFF_V1": "HANDOFF"}
CYCLE_RE = re.compile(r"LRGD_[A-Z_]+_V1\|mode=([a-z-]+)\|cycle=(\d+)\|")
ALLOCATED_BOUND = (64 << 20) + TABLE_SIZE  # LRSO bound plus the zeroed function table (C++ verify_views)


def program(mode, native):
    """The exact record sequence one run writes: [(key, acceptable exact texts or None)] (SIG keys are stage blocks)."""
    variant, cycles = MODES[mode]
    latch, fatal = variant == "latch", mode in FATAL_LRGD
    p = []
    if native:
        p += [(("SIG", 0, "entry"), None), (("THREADS", 0, "entry"), None), (("LATCH", "entry"), None),
              (("SIG", 0, "after-logging"), None), (("THREADS", 0, "after-logging"), None)]
        if latch:
            p.append((("LATCH", "after-store"), None))
    for c in range(1, cycles + 1):
        if native:
            p.append((("THREADS", c, "after-setup"), None))
        p.append((("RUNTIME", c), None))
        for guest, symbol in MAPPINGS:
            p.append((("REG", c), [f"LRGD_REG_V1|mode={mode}|cycle={c}|guest={guest:08x}|symbol={symbol}|dispatcher=1"
                                   "|table_slot=1|indirect=1"]))
        p.append((("IMAGE", c), [f"LRGD_IMAGE_V1|mode={mode}|cycle={c}|code_base={CODE_BASE:08x}|code_size={CODE_SIZE:08x}"
                                 f"|image_base={IMAGE_BASE:08x}|image_size={IMAGE_SIZE:08x}|table_base={TABLE_BASE:08x}"
                                 f"|table_size={TABLE_SIZE:08x}|thunk_reserve={THUNK_RESERVE:08x}|mappings={len(MAPPINGS)}"
                                 f"|window_populated={WINDOW_POPULATED}|window_empty={WINDOW_EMPTY}|codegen_flags=00000000"
                                 "|rexcrt_heap=0|register_modules=0"]))
        if native:
            if c == 1:
                p.append((("LATCH", "after-setup"), None))
            p.append((("SIG", c, "after-setup"), None))
            if latch:
                p += [(("SIG", c, "after-thunk-removal"), None), (("SIG", c, "after-owner"), None),
                      (("THREADS", c, "after-owner"), None)]
            result, beneath = ("installed", "sig_dfl") if latch else ("not-attempted", "sdk-seh")
            p.append((("HANDOFF", c), [f"LRGD_HANDOFF_V1|mode={mode}|cycle={c}|result={result}|segv_beneath={beneath}"]))
        p.append((("THREAD_STATE", c), [f"LRGD_THREAD_STATE_V1|mode={mode}|cycle={c}|thread_id=0x{THREAD_ID:x}|xthread=0"
                                        "|host_thread=main|bound_before=0"]))
        if fatal:
            break
        p.append((("NEGATIVE", c), [f"LRGD_NEGATIVE_V1|mode={mode}|cycle={c}|unregistered={UNREGISTERED:08x}"
                                    "|ret=0xdeadbabe|entered=0|bound=unchanged|context=args-only|memory=unchanged"
                                    "|out_of_range_set=refused"]))
        for number in (1, 2):
            p.append((("PASS", c), [f"LRGD_PASS_V1|mode={mode}|cycle={c}|pass={number}|lge={LGE_COUNT}|lwr={LWR_COUNT}"
                                    f"|watched={8 if latch else 0}|reproduced={'-' if (c, number) == (1, 1) else '1'}"]))
        if native:
            p += [(("SIG", c, "after-dispatch"), None), (("THREADS", c, "after-dispatch"), None)]
        claims = CLAIMS_PER_CYCLE if latch else 0
        p.append((("DISPATCH", c), [f"LRGD_DISPATCH_V1|mode={mode}|cycle={c}|dispatches={DISPATCHES[variant]}|claims={claims}"]))
        if native:
            if latch:
                p.append((("SIG", c, "after-owner-removal"), None))
            p += [(("SIG", c, "after-shutdown"), None), (("THREADS", c, "after-shutdown"), None)]
        base = f"LRGD_TEARDOWN_V1|mode={mode}|cycle={c}|instance=0|kernel_shared=0|mmio=0|dispatcher=0|"
        # Non-native: lrgd_tests.cpp now prints '-' (LRB_NATIVE=0); the first Windows reference runs predate that edit.
        tails = ["views_unmapped=1|shm_removed=1"] if native else ["views_unmapped=-|shm_removed=-"]
        p.append((("TEARDOWN", c), [base + tail for tail in tails]))
        if native and c == cycles:
            p.append((("LATCH", "after-shutdown"), None))
    return p


def parse_records(text, mode, native):
    """Ordered tokens: SIG stage blocks, parsed THREADS/LATCH/RUNTIME rows and exact-text kinds."""
    require(isinstance(text, str) and text.endswith("\n") and "\r" not in text, "record file framing")
    tokens, sig_run = [], []

    def flush():
        if sig_run:
            for (cycle, stage), rows in S.group_stages(sig_run):
                tokens.append({"key": ("SIG", cycle, stage), "rows": rows})
            sig_run.clear()

    runtime_re = RUNTIME_NATIVE if native else RUNTIME_PLAIN
    for line in text[:-1].split("\n"):
        prefix = line.split("|", 1)[0]
        if prefix == "LRGD_SIG_V1":
            m = SIG_RE.fullmatch(line)
            require(m is not None, "malformed signal record: " + line[:120])
            g = m.groups()
            require(g[0] == mode, f"record mode {g[0]} != {mode}")
            sig_run.append({"mode": g[0], "cycle": int(g[1]), "stage": g[2], "sig": int(g[3]), "state": g[4],
                            "siginfo": int(g[5]), "flags": int(g[6], 16), "mask": int(g[7], 16), "object": g[8],
                            "offset": int(g[9], 16)})
            continue
        flush()
        if prefix == "LRGD_THREADS_V1":
            m = THREADS_RE.fullmatch(line)
            require(m is not None and m.group(1) == mode, "malformed thread record: " + line[:120])
            g = m.groups()
            tokens.append({"key": ("THREADS", int(g[1]), g[2]), "count": int(g[3]), "baseline": int(g[4]), "equal": int(g[5])})
        elif prefix == "LRGD_LATCH_V1":
            m = LATCH_RE.fullmatch(line)
            require(m is not None and m.group(1) == mode, "malformed latch record: " + line[:120])
            tokens.append({"key": ("LATCH", m.group(2)), "value": int(m.group(3)), "object": m.group(4)})
        elif prefix == "LRGD_RUNTIME_V1":
            m = runtime_re.fullmatch(line)
            require(m is not None and m.group(1) == mode, "malformed runtime record: " + line[:200])
            g = m.groups()
            item = {"key": ("RUNTIME", int(g[1])), "setup_status": g[2]}
            if native:
                item.update(membase=g[3], shm=g[4], inode=int(g[5]), device=int(g[6]), allocated=int(g[7]))
            tokens.append(item)
        elif prefix in EXACT_KINDS:
            m = CYCLE_RE.match(line)
            require(m is not None and m.group(1) == mode, "malformed record: " + line[:120])
            tokens.append({"key": (EXACT_KINDS[prefix], int(m.group(2))), "line": line})
        else:
            raise GateError("unknown record line: " + line[:80])
    flush()
    return tokens


def check_sequence(tokens, prog):
    for i, (token, (key, exact)) in enumerate(zip(tokens, prog)):
        require(token["key"] == key, f"record {i}: expected {key}, found {token['key']}")
        if exact is not None:
            require(token["line"] in exact, f"record {i} {key}: unexpected content {token['line'][:160]!r}")
    require(len(tokens) == len(prog), f"record count {len(tokens)} != {len(prog)}")


def validate_records(mode, text, native):
    """Re-derive the whole record contract of one LRGD run (signal ownership, threads, latch, image, dispatcher)."""
    require(mode in MODES, "unknown LRGD mode " + str(mode))
    require(native or mode == "default-dispatch", "non-native records exist only for default-dispatch")
    variant, cycles = MODES[mode]
    latch, fatal = variant == "latch", mode in FATAL_LRGD
    tokens = parse_records(text, mode, native)
    check_sequence(tokens, program(mode, native))
    runtime = [t for t in tokens if t["key"][0] == "RUNTIME"]
    require([t["key"][1] for t in runtime] == list(range(1, cycles + 1)), "runtime record per cycle")
    for t in runtime:
        require(t["setup_status"] == "0x0", f"runtime record: {t}")
    if not native:
        return {"thunk": None, "seh": None, "shm": []}
    for t in runtime:
        require(t["membase"] == "0x100000000" and t["allocated"] < ALLOCATED_BOUND, f"runtime record: {t}")
    require(len({t["shm"] for t in runtime}) == cycles, "runtime cycles reuse a shm name")
    stages = {t["key"][1:]: t["rows"] for t in tokens if t["key"][0] == "SIG"}
    entry, logged = stages[(0, "entry")], stages[(0, "after-logging")]
    for sig in (S.SEGV, S.ILL, S.BUS, S.FPE):
        require(entry[sig]["state"] == "dfl", f"entry: signal {sig} is not SIG_DFL")
    require(S.changed(entry, logged) == [], "logging initialization changed a signal disposition")
    thunk = seh = None
    for c in range(1, cycles + 1):
        setup = stages[(c, "after-setup")]
        if not latch:
            require(S.changed(entry, setup) == sorted([S.ILL, S.BUS, S.FPE, S.SEGV]),
                    f"cycle {c}: Setup changed {S.changed(entry, setup)}")
            require(S.row_of(setup[S.SEGV]) == S.row_of(setup[S.ILL]), "SIGSEGV and SIGILL thunks differ")
            S.require_sdk_fn(setup[S.SEGV], S.SA_SIGINFO, "MMIO thunk")
            require(S.row_of(setup[S.BUS]) == S.row_of(setup[S.FPE]), "SIGBUS and SIGFPE SEH actions differ")
            S.require_sdk_fn(setup[S.FPE], S.SA_SIGINFO | S.SA_NODEFER, "SEH handler")
            require(setup[S.SEGV]["offset"] != setup[S.FPE]["offset"], "SEH handler and MMIO thunk share an offset")
            cycle_thunk, cycle_seh = setup[S.SEGV]["offset"], setup[S.FPE]["offset"]
            seh_row = S.row_of(setup[S.FPE])
            require(S.changed(setup, stages[(c, "after-dispatch")]) == [], "dispatch changed a signal disposition")
            shut = stages[(c, "after-shutdown")]
            for sig in S.SIGNALS:
                want = seh_row if sig in (S.ILL, S.BUS, S.FPE, S.SEGV) else S.row_of(entry[sig])
                require(S.row_of(shut[sig]) == want, f"cycle {c} after-shutdown: signal {sig} differs from the expected SEH state")
        else:
            require(S.changed(entry, setup) == [S.ILL, S.SEGV], f"cycle {c}: latch Setup changed {S.changed(entry, setup)}")
            require(S.row_of(setup[S.SEGV]) == S.row_of(setup[S.ILL]), "SIGSEGV and SIGILL thunks differ")
            S.require_sdk_fn(setup[S.SEGV], S.SA_SIGINFO, "MMIO thunk")
            require(setup[S.BUS]["state"] == "dfl" and setup[S.FPE]["state"] == "dfl",
                    "latch: SIGBUS/SIGFPE not SIG_DFL after Setup")
            cycle_thunk, cycle_seh = setup[S.SEGV]["offset"], None
            require(S.changed(entry, stages[(c, "after-thunk-removal")]) == [], "thunk removal did not restore the entry state")
            owner = stages[(c, "after-owner")]
            require(S.changed(entry, owner) == [S.SEGV], f"cycle {c}: owner changed {S.changed(entry, owner)}")
            o = owner[S.SEGV]
            require(o["state"] == "fn" and o["siginfo"] == 1 and o["flags"] == S.SA_ONSTACK | S.SA_SIGINFO
                    and o["mask"] == S.OWNER_MASK and o["object"] in OWNER_OBJECTS,
                    f"LRB owner action is not the executable's SA_ONSTACK|SA_SIGINFO handler with mask 0x{S.OWNER_MASK:x}: "
                    f"{S.row_of(o)}")
            if not fatal:
                require(S.changed(owner, stages[(c, "after-dispatch")]) == [], "dispatch changed a signal disposition")
                require(S.changed(entry, stages[(c, "after-owner-removal")]) == [], "owner removal did not restore the entry state")
                require(S.changed(entry, stages[(c, "after-shutdown")]) == [], "Shutdown did not restore the entry state")
        thunk = cycle_thunk if thunk is None else thunk
        seh = cycle_seh if seh is None else seh
        require(cycle_thunk == thunk and cycle_seh == seh, "handler offsets differ between cycles")
    for t in tokens:
        if t["key"][0] == "THREADS":
            require(t["equal"] == 1 and t["count"] == t["baseline"] == 2, f"thread set changed: {t}")
    latches = [t for t in tokens if t["key"][0] == "LATCH"]
    want = [("entry", 0)] + ([("after-store", 1)] if latch else []) + [("after-setup", 1)] + ([] if fatal else [("after-shutdown", 1)])
    require([(t["key"][1], t["value"]) for t in latches] == want, "latch record sequence")
    require(all(t["object"].startswith("librexruntime.so") for t in latches), "the latch is not the SDK library's own")
    return {"thunk": thunk, "seh": seh, "shm": [t["shm"] for t in runtime],
            "last_runtime": {"inode": runtime[-1]["inode"], "device": runtime[-1]["device"],
                             "allocated": runtime[-1]["allocated"]}}


# ------------------------------------------------------------------ output (file) validation

def expected_restart_text():
    return "".join(line.replace("LWR_RESTART_V1|", "LRGD_RESTART_V1|", 1) + "\n" for line in W.EXPECTED_RESTART)


def validate_claims(text):
    require(text.endswith("\n") and "\r" not in text, "claims file framing")
    converted = []
    for line in text[:-1].split("\n"):
        require(line.startswith("LRGD_CLAIM_V1|"), "claim record prefix")
        converted.append("LWR_CLAIM_V1|" + line[len("LRGD_CLAIM_V1|"):])
    return W.validate_claims("\n".join(converted) + "\n")


def pass_pattern(mode, native, refs):
    variant, cycles = MODES[mode]
    latch = variant == "latch"
    return re.compile(rf"LRGD PASS mode={re.escape(mode)} variant={variant} cycles={cycles} lge={LGE_COUNT} lwr={LWR_COUNT} "
                      rf"watched={8 if latch else 0} claims={CLAIMS_PER_CYCLE * cycles if latch else 0} "
                      rf"lge_aggregate={refs['lge_aggregate']} lwr_aggregate={refs['lwr_aggregate']} "
                      rf"checks=(\d+) native={1 if native else 0}\n")


def validate_outputs(mode, stdout, texts, refs, native):
    """Pass line (when given), result files against the audited references, re-derived dispatch rows, records."""
    require(mode in POSITIVE or mode == TRACED_POSITIVE, "output validation of a non-positive mode")
    latch = MODES[mode][0] == "latch"
    checks = None
    if stdout is not None:
        match = pass_pattern(mode, native, refs).fullmatch(stdout)
        require(match is not None, "stdout pass-line contract")
        checks = int(match.group(1))
    require(texts["lge"] == refs["lge_text"], "LGE case file differs from the Windows reference")
    require(texts["lwr"] == refs["lwr_text"], "LWR case file differs from the Windows reference")
    dispatch = texts["dispatch"]
    require(dispatch.endswith("\n") and "\r" not in dispatch, "dispatch file framing")
    summary = rederive(dispatch[:-1].split("\n"), refs["lge_lines"], refs["lwr_lines"], latch)
    if latch:
        require(texts.get("watched") == texts["lwr"], "watched LWR file differs from the ordinary LWR file")
        require(texts.get("restart") == expected_restart_text(), "restart file differs from the expected restart records")
        validate_claims(texts["claims"])
    else:
        for name in ("watched", "restart", "claims"):
            require(texts.get(name, "") == "", f"default-dispatch wrote a non-empty {name} file")
    records = validate_records(mode, texts["record"], native)
    return {"checks": checks, "dispatch": summary, "records": records}


# ------------------------------------------------------------------ run validators

WITNESS = re.compile(r"LRGD_GATE_V1 token=([0-9a-f]{32}) mode=([a-z-]+) phase=([a-z]+) claims=(\d+) "
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


def positive_expectations():
    """(claims of the case, witness rows already written) for each of the 18 faults (two watched passes)."""
    out, before = [], 0
    for _ in range(2):
        for k in W.CASE_CLAIMS:
            out.extend([(k, before)] * k)
            before += k
    return out


def run_texts(run, reader, names=FILE_NAMES):
    require(sorted(run["files"]) == sorted(names), f"run files {sorted(run['files'])} != {sorted(names)}")
    out = {}
    for name in names:
        data = reader(run["files"][name])
        require(sha(data) == run["file_sha256"][name], "result file digest: " + run["files"][name])
        out[name] = data.decode("ascii")
    return out


def validate_owned_shm(run, record_text, summary):
    """LRB ownership/residue rules; the ownership record names the last cycle's shm object."""
    L.validate_ownership(run, expect_residue=False)
    last = [m.group(5) for m in RUNTIME_NATIVE.finditer(record_text)]
    require(last and run["ownership"]["shm_name"] == last[-1], "ownership record does not name the last runtime cycle's shm object")
    info = summary["last_runtime"]
    own = run["ownership"]
    require(own["inode"] == info["inode"] and own["device"] == info["device"] and own["allocated_bytes"] == info["allocated"],
            "ownership record differs from the last runtime record")


def validate_untraced(run, reader, refs):
    mode = run["mode"]
    require(mode in POSITIVE, "untraced run of a non-positive mode")
    require(not run.get("timeout") and run["returncode"] == 0 and run["stderr"] == "", "untraced run exit/stderr")
    require(run.get("cwd_entries") == [], f"the runtime created files in its working directory: {run.get('cwd_entries')}")
    texts = run_texts(run, reader)
    out = validate_outputs(mode, run["stdout"], texts, refs, True)
    validate_owned_shm(run, texts["record"], out["records"])
    return {**out["records"], "checks": out["checks"], "dispatch_sha256": sha(texts["dispatch"].encode()),
            "claims_sha256": sha(texts["claims"].encode())}


def validate_traced_positive(run, reader, refs):
    require(run["status"] == "PASS" and run["mode"] == TRACED_POSITIVE, "failed traced record")
    require(run["returncode"] == 0 and not run.get("timeout"), "traced positive exit status")
    require(re.fullmatch(r"[0-9a-f]{32}", run.get("token") or "") is not None, "gate token")
    texts = run_texts(run, reader)
    out = validate_outputs(TRACED_POSITIVE, run["stdout"], texts, refs, True)
    rows = parse_witness(run["stderr"], run["token"], TRACED_POSITIVE)
    expected = positive_expectations()
    require(len(rows) == len(expected) == CLAIMS_PER_CYCLE and all(
        r["phase"] == "claim" and r["invalidations"] == 0 and VA_REGION[0] <= r["address"] < VA_REGION[1] for r in rows),
        "traced positive witness rows")
    stops = run["signals"]
    require(len(stops) == len(expected), "traced positive stop count")
    for i, (stop, (case_claims, before)) in enumerate(zip(stops, expected)):
        W.check_stop_kind(stop, "ACCERR", run["pid"], rows[i]["address"])
        require(rows[i]["claims"] == case_claims, f"witness {i} claims differ from its case claim count")
        require(len(stop_rows(stop, run)) == before, f"stop {i}: witness lines already written at the fault")
    validate_owned_shm(run, texts["record"], out["records"])
    return {**out["records"], "checks": out["checks"], "dispatch_sha256": sha(texts["dispatch"].encode()),
            "claims_sha256": sha(texts["claims"].encode())}


def fatal_contract(mode, rows):
    require(rows, "fatal witness rows")
    address = rows[0]["address"]
    require(address == (GUARD_ADDRESS if mode == "lrgd-write-guard" else P4_ADDRESS), "fatal witness address")
    return [("begin", 0, 0, address)], [("ACCERR", 1), ("TKILL", 1)]


def validate_traced_fatal(run, reader):
    mode = run["mode"]
    require(run["status"] == "PASS" and mode in FATAL_LRGD, "failed traced record")
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
    texts = run_texts(run, reader, ["record"])
    summary = validate_records(mode, texts["record"], True)
    validate_owned_shm(run, texts["record"], summary)
    return summary


# ------------------------------------------------------------------ binary checks

def generated_checks(nm_text, objdump_text, readelf_text):
    """The audited LGE generated-object contract: weak aliases, closed body references, helpers, no strays."""
    names = {f["name"] for f in G.selection()["functions"]}
    require(names == {sym for _, sym in MAPPINGS}, "LGE selection differs from the ten production rows")
    G.check_aliases(nm_text, names)
    defined = set(G.nm_symbols(nm_text))
    refs = G.check_body_references(G.body_references(objdump_text, names), names, defined)
    G.check_helper_aliases(G.readelf_symbols(readelf_text), refs)
    stray = {s for s in defined if G.GENERATED_NAME.match(s) and (s[7:] if s.startswith("__imp__") else s) not in names}
    require(not stray, "no unselected generated function in the object: " + ",".join(sorted(stray)))
    return {"functions": sorted(names), "body_references": refs}


def binary_checks(text):
    checks = S.binary_checks(text)
    checks["final_admit_instructions"] = W.check_final_admit(text["final.objdump.txt"])
    checks["generated"] = generated_checks(text["generated.nm.txt"], text["generated.objdump.txt"], text["final.readelf.txt"])
    return json.loads(json.dumps(checks))


# Claim fields that are machine-code facts of one compiler configuration: the
# instruction offset inside the generated body and the x86 instruction length.
# check_claim_sites verifies both against that configuration's own disassembly
# (a scalar mov store of the claimed width and exact length). Every other field
# is guest/restart semantics and must agree across all configurations.
MACHINE_CODE_CLAIM_FIELDS = ("offset=", "length=")


def claim_semantics(claims_text):
    """The claims file without the per-configuration machine-code fields (validated first)."""
    validate_claims(claims_text)
    return "".join("|".join(f for f in line.split("|") if not f.startswith(MACHINE_CODE_CLAIM_FIELDS)) + "\n"
                   for line in claims_text[:-1].split("\n"))


def check_claim_consistency(claims_by_config):
    """Claims files of the latch-family runs, keyed by configuration.

    Within a configuration every run must produce the identical file (the audited LWR rule).
    Across configurations only the disassembly-verified machine-code fields may differ:
    the semantic projection must be identical everywhere (LRGD native attempt 1: the four
    compilers placed the same stores at different offsets with different encodings).
    """
    require(claims_by_config and all(claims_by_config.values()), "claims files for every configuration")
    semantics = set()
    for key, texts in claims_by_config.items():
        require(len(set(texts)) == 1, "claims file differs across runs of a configuration: " + key)
        semantics.add(claim_semantics(texts[0]))
    require(len(semantics) == 1,
            "claim semantics (all fields except the disassembly-verified offset/length) differ between configurations")
    return sha(next(iter(semantics)).encode())


def claim_sites(claims_text, text):
    claims = validate_claims(claims_text)
    return json.loads(json.dumps(W.check_claim_sites(claims, G.readelf_symbols(text["final.readelf.txt"]),
                                                     W.instruction_index(text["final.objdump.txt"]))))


# ------------------------------------------------------------------ result validation

def validate_results(result, reader, refs):
    register_fatal()
    require(result.get("status") == "PASS", "result status")
    require([c["key"] for c in result["configurations"]] == CONFIG_KEYS, "configurations")
    n, cr, t = result["repeats"], result["cycles_repeats"], result["traced_repeats"]
    require(min(n, cr, t) >= 1, "repetition counts")
    checks, dispatch_hashes, claims_by_config = {}, set(), {}
    for row in result["configurations"]:
        key = row["key"]
        claims_by_config[key] = []
        require(row["status"] == "PASS", "configuration status")
        for name in NATIVE_NAMES:
            require(sha(reader(f"native/{key}/{name}")) == row["artifacts"][name], f"artifact digest: native/{key}/{name}")
        require(row["executable_sha256"] == row["artifacts"]["lrgd_tests.elf"], "ELF identity")
        W.check_closure("lge", key, "lge_generated.o", row["artifacts"]["lge_generated.o"], row.get("cxx_version"))
        text = {name: reader(f"native/{key}/{name}").decode("utf-8") for name in TEXT_NAMES}
        require(binary_checks(text) == row["object_checks"], "object checks re-derived: " + key)
        summaries = []
        require(sorted(r["mode"] for r in row["runs"]) == sorted(["default-dispatch"] * n + ["latch"] * n + ["latch-cycles"] * cr),
                "untraced run inventory")
        for run in row["runs"]:
            s = L.checked(run, lambda r: validate_untraced(r, reader, refs))
            summaries.append(s)
            checks.setdefault(run["mode"], set()).add(s["checks"])
            dispatch_hashes.add((MODES[run["mode"]][0], s["dispatch_sha256"]))
            if MODES[run["mode"]][0] == "latch":
                claims_by_config[key].append(run_texts(run, reader)["claims"])
        require(len(row["traced_positive"]) == t, "traced positive repetitions")
        for run in row["traced_positive"]:
            s = L.checked(run, lambda r: validate_traced_positive(r, reader, refs))
            summaries.append(s)
            checks.setdefault(TRACED_POSITIVE, set()).add(s["checks"])
            dispatch_hashes.add(("latch", s["dispatch_sha256"]))
            claims_by_config[key].append(run_texts(run, reader)["claims"])
        require(sorted(r["mode"] for r in row["traced_fatal"]) == sorted(FATAL_LRGD * t), "traced fatal inventory")
        for run in row["traced_fatal"]:
            summaries.append(L.checked(run, lambda r: validate_traced_fatal(r, reader)))
        first_latch = next(r for r in row["runs"] if r["mode"] == "latch")
        require(claim_sites(run_texts(first_latch, reader)["claims"], text) == row["claim_sites"], "claim sites re-derived: " + key)
        require(len(row["claim_sites"]) == W.TOTAL_CLAIMS, "claim site count")
        require(S.check_cross_run(summaries, text["runtime.symbols.txt"]) == row["cross_run"], "cross-run checks re-derived: " + key)
    require(all(len(v) == 1 for v in checks.values()), f"check counts differ between runs/configurations: {checks}")
    require(len({v for variant, v in dispatch_hashes if variant == "default"}) == 1
            and len({v for variant, v in dispatch_hashes if variant == "latch"}) == 1,
            "dispatch file differs between runs/configurations of a variant")
    check_claim_consistency(claims_by_config)
    require(result["shm_snapshot"]["foreign_new"] == [], "unattributed new xenia_memory objects")
    require(result["shm_snapshot"]["own_left"] == [], "own shm residue left")
    return {m: sorted(v)[0] for m, v in checks.items()}


# ------------------------------------------------------------------ source transfer

def package_source(path):
    head = G.git("rev-parse", "HEAD").decode().strip()
    entries = W.package_entries(head, source_files(), lambda n: G.git("show", f"HEAD:{n}"), lambda n: lf(ROOT / n))
    digest = L.write_zip(path, entries)
    W.write_sidecar(path, digest)
    print(f"LRGD_SOURCE PASS files={len(entries)} commit={head} size={path.stat().st_size} sha256={digest} path={path}")


def source_identity():
    manifest = read_json((ROOT / "SOURCE_MANIFEST.json").read_bytes())
    identity = read_json((ROOT / "IMPLEMENTATION_ID.json").read_bytes())
    require(all(sha(lf(ROOT / p)) == h for p, h in manifest.items()), "source transfer hash mismatch")
    require(sorted(manifest) == source_files(), "LRGD source inventory")
    require(re.fullmatch(r"[0-9a-f]{40}", identity["commit"]) is not None, "commit identity")
    return manifest, identity


def private_zip(path):
    reference_bytes = (PRIVATE / REFERENCE_NAME).read_bytes()
    check_lrgd_reference(read_json(reference_bytes))
    require(b"\nDEFINE_REX_FUNC(" not in reference_bytes, "generated code in the LRGD private ZIP")
    entries = {REFERENCE_NAME: reference_bytes}
    entries["PRIVATE_MANIFEST.json"] = (json.dumps({n: sha(b) for n, b in sorted(entries.items())}, indent=1) + "\n").encode()
    digest = L.write_zip(path, entries)
    W.write_sidecar(path, digest)
    print(f"LRGD_PRIVATE_ZIP PASS entries={len(entries)} size={path.stat().st_size} sha256={digest} path={path}")


# ------------------------------------------------------------------ Windows reference and check-run

def read_dir_files(directory):
    """Result files of one run directory as texts: records.txt lge.txt lwr.txt dispatch.txt (+ optional others)."""
    directory = Path(directory)
    names = {"record": "records.txt", "lge": "lge.txt", "lwr": "lwr.txt", "dispatch": "dispatch.txt",
             "watched": "watched.txt", "restart": "restart.txt", "claims": "claims.txt"}
    texts = {}
    for name, filename in names.items():
        path = directory / filename
        if path.is_file():
            text = path.read_bytes().decode("ascii")
            # Only the record file is opened in text mode by the C++ (CRLF on Windows); every other file is binary LF.
            texts[name] = text.replace(CR + LF, LF) if name == "record" else text
        else:
            require(name in ("watched", "restart", "claims"), f"{directory}: missing {filename}")
    return texts


def check_run(directory, refs, mode="default-dispatch", native=False):
    texts = read_dir_files(directory)
    out = validate_outputs(mode, None, texts, refs, native)
    return {"dir": str(directory), "dispatch": out["dispatch"], "dispatch_sha256": sha(texts["dispatch"].encode()),
            "records_sha256": sha(texts["record"].encode())}


def run_child(argv, env_extra, cwd, timeout=300):
    env = os.environ.copy()
    env.pop("LRB_GATE_TOKEN", None)
    env.pop("LRB_SDK_LOG_CONSOLE", None)
    env.update(env_extra)
    p = subprocess.run([str(a) for a in argv], capture_output=True, timeout=timeout, env=env, cwd=cwd)
    return {"argv": [str(a) for a in argv], "returncode": p.returncode, "stdout": p.stdout.decode(errors="replace"),
            "stderr": p.stderr.decode(errors="replace")}


def windows_reference(private_dir, prefix, repeats, work, lge_path, lwr_path):
    require(platform.system() == "Windows", "the reference harness runs on the Windows development host")
    pc = private_check(private_dir, DEFAULT_INIT)
    refs = load_raw_references(lge_path, lwr_path)
    cxx, cc = shutil.which("clang++"), shutil.which("clang")
    require(cxx and cc and shutil.which("ninja") and shutil.which("cmake"), "run inside tools\\devenv.bat")
    work.mkdir(parents=True, exist_ok=True)
    configs, dispatch_text, records_text = [], None, None
    for opt in ("0", "2"):
        build = work / f"gate_clang_O{opt}"
        if build.exists():
            shutil.rmtree(build)
        log = []
        row = {"key": f"clang++_O{opt}", "commands": log, "runs": []}
        configs.append(row)
        row["cxx_version"] = L.command([cxx, "--version"], log)
        L.command(["cmake", "-S", HERE, "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                   "-DCMAKE_PREFIX_PATH=" + str(prefix), "-DCMAKE_CXX_COMPILER=clang++", "-DCMAKE_C_COMPILER=clang",
                   "-DLRGD_OPT=" + opt, "-DLRB_ORDINARY_ONLY=ON", "-DLGE_GENERATED_DIR=" + str(private_dir)], log)
        G.build_step(["cmake", "--build", build, "--verbose"], log)
        exe = build / "lrgd_tests.exe"
        row["executable_sha256"] = sha(exe.read_bytes())
        for i in range(repeats):
            cwd = build / "runs" / f"run_{i}"
            if cwd.exists():
                shutil.rmtree(cwd)
            cwd.mkdir(parents=True)
            paths = {name: build / "results" / f"run_{i}" / f"{name}.txt" for name in FILE_NAMES}
            paths["record"].parent.mkdir(parents=True, exist_ok=True)
            env = {FILE_ENV[name]: str(path) for name, path in paths.items()}
            env["PATH"] = str(prefix / "bin") + os.pathsep + os.environ.get("PATH", "")  # rexruntime.dll
            run = run_child([exe, "default-dispatch"], env, cwd)
            row["runs"].append(run)
            require(run["returncode"] == 0 and run["stderr"] == "",
                    f"Windows run failed: {L.describe({**run, 'mode': 'default-dispatch'})}")
            texts = {name: path.read_bytes().decode("ascii") for name, path in paths.items() if path.exists()}
            # The record file is opened in text mode (CRLF on Windows); every other result file is binary LF.
            texts["record"] = texts["record"].replace("\r\n", "\n")
            require(sorted(os.listdir(cwd)) == [], "the runtime created files in its working directory")
            out = validate_outputs("default-dispatch", run["stdout"].replace("\r\n", "\n"), texts, refs, False)
            run.update(checks=out["checks"], dispatch_sha256=sha(texts["dispatch"].encode()),
                       records_sha256=sha(texts["record"].encode()))
            require(dispatch_text in (None, texts["dispatch"]), "Windows dispatch files are not bit-identical across runs/O-levels")
            require(records_text in (None, texts["record"]), "Windows record files are not bit-identical across runs/O-levels")
            dispatch_text, records_text = texts["dispatch"], texts["record"]
    checks = {r["checks"] for row in configs for r in row["runs"]}
    require(len(checks) == 1, "identical check count across Windows runs")
    lge_ref, lwr_ref = Path(lge_path), Path(lwr_path)
    reference = {"format": "LRGD_REFERENCE_V1", "generated_manifest_sha256": pc["generated_manifest_sha256"],
                 "lge_reference_sha256": sha(lge_ref.read_bytes()), "lwr_reference_sha256": sha(lwr_ref.read_bytes()),
                 "private_check": pc, "platform": platform.platform(), "repeats": repeats, "configurations": configs,
                 "checks": checks.pop(), "lge_aggregate": refs["lge_aggregate"], "lwr_aggregate": refs["lwr_aggregate"],
                 "lge_cases_sha256": sha(refs["lge_text"].encode()), "lwr_cases_sha256": sha(refs["lwr_text"].encode()),
                 "lge_cases_text": refs["lge_text"], "lwr_cases_text": refs["lwr_text"],
                 "dispatch_sha256": sha(dispatch_text.encode()), "dispatch_text": dispatch_text, "records_text": records_text}
    check_lrgd_reference(reference)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / REFERENCE_NAME).write_text(json.dumps(reference, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"LRGD_WINDOWS PASS configurations=2 runs={2 * repeats} lge={LGE_COUNT} lwr={LWR_COUNT} checks={reference['checks']} "
          f"lge_aggregate={reference['lge_aggregate']} lwr_aggregate={reference['lwr_aggregate']} "
          f"dispatch_sha256={reference['dispatch_sha256']}")


# ------------------------------------------------------------------ native gate

def lrgd_files(out, tag, names=FILE_NAMES):
    base = out / "files"
    base.mkdir(parents=True, exist_ok=True)
    paths = {name: base / f"{tag}.{name}.txt" for name in names}
    for p in paths.values():
        if p.exists():
            p.unlink()
    return paths, {FILE_ENV[name]: str(p) for name, p in paths.items()}


def record_files(run, paths, out):
    run["files"] = {n: p.relative_to(out).as_posix() for n, p in paths.items() if p.exists()}
    run["file_sha256"] = {n: sha(p.read_bytes()) for n, p in paths.items() if p.exists()}


def run_untraced(exe, mode, out, tag):
    """One untraced child in a fresh empty working directory; never raises on child failure."""
    paths, files_env = lrgd_files(out, tag)
    own = L.ownership_path(out, tag)
    cwd = out / "cwd" / tag
    if cwd.exists():
        shutil.rmtree(cwd)
    cwd.mkdir(parents=True)
    env = os.environ.copy()
    env.pop("LRB_GATE_TOKEN", None)
    env.pop("LRB_SDK_LOG_CONSOLE", None)
    env.update(files_env)
    env["LRB_OWNERSHIP_FILE"] = str(own)
    argv = [str(exe), mode]
    run = {"mode": mode, "argv": argv, "cwd": str(cwd), "shm_before": L.shm_names()}
    try:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=cwd)
        run["pid"] = p.pid
        try:
            stdout, stderr = p.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            p.kill()
            stdout, stderr = p.communicate()
            run["timeout"] = True
        run.update(returncode=p.returncode, stdout=stdout.decode(errors="replace"), stderr=stderr.decode(errors="replace"))
    except OSError as error:
        run.update(pid=0, returncode=-1000, stdout="", stderr=f"spawn failed: {error}")
    run["cwd_entries"] = sorted(os.listdir(cwd))
    record_files(run, paths, out)
    L.inspect_residue(own, run, remove=True)
    return run


def run_traced(exe, mode, out, tag, token, sink):
    record = {"mode": mode, "token": token, "status": "INCOMPLETE"}
    sink.append(record)  # Partial facts stay in results.json if the tracer raises.
    names = FILE_NAMES if mode == TRACED_POSITIVE else ["record"]
    paths, files_env = lrgd_files(out, tag, names)
    own = L.ownership_path(out, tag)
    try:
        W.traced([exe, mode], W.traced_env(token, own, files_env), timeout=300, ownership=own, result=record)
    finally:
        record_files(record, paths, out)
    return record


def native_config(out, key, cxx, cc, opt, prefix, private_dir, refs, args, row):
    log = row["commands"]
    build = out / "build" / key
    if build.exists():
        shutil.rmtree(build)
    row["cxx_version"] = L.command([cxx, "--version"], log)
    row["cc_version"] = L.command([cc, "--version"], log)
    W.configure_and_build(HERE, build, cxx, cc, prefix, ["-DLRGD_OPT=" + opt, "-DLRB_ORDINARY_ONLY=OFF",
                                                         "-DLGE_GENERATED_DIR=" + str(private_dir)], log)
    exe = build / "lrgd_tests"
    exe_sha = sha(exe.read_bytes())
    row["executable_sha256"] = exe_sha
    objects = build / "CMakeFiles/lrgd_tests.dir"
    native = out / "native" / key
    native.mkdir(parents=True, exist_ok=True)
    sources = {"lrgd_tests.elf": exe, "lrb_owner.o": W.find_one(objects, "lrb_owner.c.o"),
               "lrb_access.o": W.find_one(objects, "lrb_access.S.o"), "lwr_restart.o": W.find_one(objects, "lwr_restart.c.o"),
               "lrgd_tests.o": W.find_one(objects, "lrgd_tests.cpp.o"),
               "lge_generated.o": W.find_one(build / "CMakeFiles/lge_generated.dir", "*.o")}
    for name, src in sources.items():
        shutil.copyfile(src, native / name)
    runtime = S.locate_runtime_library(prefix)
    row["runtime_library"] = {"path": runtime.relative_to(prefix).as_posix(), "sha256": sha(runtime.read_bytes())}
    dumps = {"final.objdump.txt": ("objdump", ["-drwC"], native / "lrgd_tests.elf"),
             "owner.objdump.txt": ("objdump", ["-drwC"], native / "lrb_owner.o"),
             "restart.objdump.txt": ("objdump", ["-drwC"], native / "lwr_restart.o"),
             "generated.objdump.txt": ("objdump", ["-drw"], native / "lge_generated.o"),  # mangled: the audit re-parses
             "generated.nm.txt": ("nm", ["--defined-only"], native / "lge_generated.o"),
             "final.readelf.txt": ("readelf", ["-a", "-W"], native / "lrgd_tests.elf"),
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
    require(row["artifacts"]["lrgd_tests.elf"] == exe_sha, "executable changed during inspection")
    # The generated object must be the audited LGE object for this compiler (same sources and flags).
    W.check_closure("lge", key, "lge_generated.o", row["artifacts"]["lge_generated.o"], row["cxx_version"])
    text = {n: (native / n).read_text(encoding="utf-8") for n in TEXT_NAMES}
    row["object_checks"] = binary_checks(text)
    row["runs"], row["traced_positive"], row["traced_fatal"] = [], [], []
    reader = lambda p: (out / p).read_bytes()  # noqa: E731
    plan = [("default-dispatch", args.repeats), ("latch", args.repeats), ("latch-cycles", args.cycles_repeats)]
    summaries = []
    for mode, count in plan:
        for i in range(count):
            run = run_untraced(exe, mode, out, f"{key}_{mode}_{i}")
            row["runs"].append(run)
            summaries.append(L.checked(run, lambda r: validate_untraced(r, reader, refs)))
    first_latch = next(r for r in row["runs"] if r["mode"] == "latch")
    row["claim_sites"] = claim_sites(run_texts(first_latch, reader)["claims"], text)
    for i in range(args.traced_repeats):
        run = run_traced(exe, TRACED_POSITIVE, out, f"{key}_{TRACED_POSITIVE}_{i}", secrets.token_hex(16), row["traced_positive"])
        summaries.append(L.checked(run, lambda r: validate_traced_positive(r, reader, refs)))
    for i in range(args.traced_repeats):
        for mode in FATAL_LRGD:
            run = run_traced(exe, mode, out, f"{key}_{mode}_{i}", secrets.token_hex(16), row["traced_fatal"])
            summaries.append(L.checked(run, lambda r: validate_traced_fatal(r, reader)))
    row["cross_run"] = S.check_cross_run(summaries, text["runtime.symbols.txt"])
    require(sha(exe.read_bytes()) == exe_sha, "binary changed during runs")
    row["status"] = "PASS"


def run_native(args):
    require(platform.system() == "Linux" and platform.machine() == "x86_64" and struct.calcsize("P") == 8,
            "native Linux x86-64 required; no Windows/WSL fallback")
    register_fatal()
    # The inspected installed librexruntime.so must be the one the children load.
    loader = {k: os.environ.pop(k) for k in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT") if k in os.environ}
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    sdk, prefix, private_dir = args.sdk.resolve(), args.prefix.resolve(), args.private.resolve()
    result = {"status": "INCOMPLETE", "platform": platform.platform(), "machine": platform.machine(),
              "kernel": platform.release(), "python": sys.version, "repeats": args.repeats,
              "cycles_repeats": args.cycles_repeats, "traced_repeats": args.traced_repeats, "configurations": [],
              "loader_environment_removed": sorted(loader), "regression": REGRESSION_NOTE}
    before_names = L.shm_names()
    result["shm_snapshot"] = {"before": before_names}
    try:
        manifest, identity = source_identity()
        result.update(identity=identity, source_manifest=manifest)
        sdk_info = L.sdk_identity(sdk, prefix)
        lrso_info, lrgd_info = S.lrso_sdk_identity(sdk, prefix), lrgd_sdk_identity(sdk, prefix)
        result["sdk_identity"], result["lrso_sdk_files"], result["lrgd_sdk_files"] = sdk_info, lrso_info, lrgd_info
        result["source_contract"] = source_contract(sdk)
        result["private_check"] = private_check(private_dir, None)
        refs, reference = load_references(args.reference)
        result["reference_sha256"] = sha(Path(args.reference).read_bytes())
        require(reference["generated_manifest_sha256"] == result["private_check"]["generated_manifest_sha256"],
                "LRGD reference built from this private extract")
        for cxx_name, cc_name, opt in L.CONFIGS:
            cxx, cc = shutil.which(cxx_name), shutil.which(cc_name)
            require(cxx and cc, "missing compiler pair " + cxx_name)
            key = f"{cxx_name}_O{opt}"
            row = {"key": key, "status": "INCOMPLETE", "commands": []}
            result["configurations"].append(row)
            native_config(out, key, cxx, cc, opt, prefix, private_dir, refs, args, row)
        names = L.shm_names()
        ours = set()
        for row in result["configurations"]:
            for r in row["runs"] + row["traced_positive"] + row["traced_fatal"]:
                if isinstance(r.get("ownership"), dict) and isinstance(r["ownership"].get("shm_name"), str):
                    ours.add(r["ownership"]["shm_name"])
        result["shm_snapshot"].update(after=names, foreign_new=sorted(set(names) - set(before_names) - ours),
                                      own_left=sorted(set(names) & ours))
        require(not result["shm_snapshot"]["own_left"], "own shm residue left")
        require(L.sdk_identity(sdk, prefix) == sdk_info and S.lrso_sdk_identity(sdk, prefix) == lrso_info
                and lrgd_sdk_identity(sdk, prefix) == lrgd_info, "SDK changed during run")
        require(source_identity() == (manifest, identity), "sources changed during run")
        result["positive_checks"] = validate_results({**result, "status": "PASS"}, reader_for(out), refs)
        result["status"] = "PASS"
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (out / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    n, c, t = args.repeats, args.cycles_repeats, args.traced_repeats
    print(f"LRGD_GATE PASS configurations=4 untraced={4 * (2 * n + c)} traced_positive={4 * t} "
          f"traced_fatal={4 * len(FATAL_LRGD) * t} facts={fact_count(result['source_contract'])}; "
          "independent audit still required")


def reader_for(out):
    return lambda p: (out / p).read_bytes()


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
    for src in sorted((out / "files").glob("*.txt")) if (out / "files").is_dir() else []:
        entries["files/" + src.name] = src.read_bytes()
    for name in ("SOURCE_MANIFEST.json", "IMPLEMENTATION_ID.json"):
        if (ROOT / name).exists():
            entries[name] = (ROOT / name).read_bytes()
    for name in ("console.log", "validator.log"):
        if (out / name).exists():
            entries[name] = (out / name).read_bytes()
    entries["PRIVATE.txt"] = (b"PRIVATE: SDK-linked ELF/object bytes, dumps and audited case outputs. Keep under "
                              b"private/work/linux_runtime_dispatch/; never commit, publish or upload.\n")
    if failure:
        own = out / "ownership"
        for p in sorted(own.glob("*.json")) if own.is_dir() else []:
            entries["ownership/" + p.name] = p.read_bytes()
        entries["FAILURE.txt"] = b"INCOMPLETE/FAILED native LRGD evidence; not a PASS claim.\n"
    require(entries, "nothing to package")
    for name, data in entries.items():
        require(b"\nDEFINE_REX_FUNC(" not in data, "generated code in the evidence: " + name)
    entries["EVIDENCE_MANIFEST.json"] = (json.dumps({n: sha(b) for n, b in sorted(entries.items())}, indent=2) + "\n").encode()
    digest = L.write_zip(path, entries)
    print(f"LRGD_EVIDENCE {'FAILURE' if failure else 'PASS'} entries={len(entries)} sha256={digest} path={path} "
          "(PRIVATE: SDK-linked bytes and case outputs; keep under private/work/linux_runtime_dispatch/)")


def audit(archive, implementation, reference_path, sdk):
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
        require(sha(S.pinned_bytes(sdk, name)) == digest, "SDK source identity differs from pin: " + name)
    for key, files in (("lrso_sdk_files", S.LRSO_SDK_FILES), ("lrgd_sdk_files", LRGD_SDK_FILES)):
        require(sorted(result[key]) == sorted(files), key + " inventory")
        for name, digest in result[key].items():
            require(sha(S.pinned_bytes(sdk, name)) == digest, f"{key} differs from pin: {name}")
    require(result["source_contract"] == source_contract(sdk), "source contract differs from the pinned blobs")
    reference_bytes = Path(reference_path).read_bytes()
    require(sha(reference_bytes) == result["reference_sha256"], "reference differs from the one the run used")
    refs = check_lrgd_reference(read_json(reference_bytes))

    def reader(name):
        require(name in data, "missing archive entry " + name)
        return data[name]

    checks = validate_results(result, reader, refs)
    print(f"LRGD_AUDIT PASS configurations=4 modes={len(checks)} entries={len(data)} "
          f"facts={fact_count(result['source_contract'])}; root disassembly review still required")


# ------------------------------------------------------------------ command line

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("source-contract"); c.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    p = sub.add_parser("private-check"); p.add_argument("--private", type=Path, default=LGE_PRIVATE)
    p.add_argument("--production-init", type=Path, default=DEFAULT_INIT)
    w = sub.add_parser("windows"); w.add_argument("--repeats", type=int, default=3)
    w.add_argument("--private", type=Path, default=LGE_PRIVATE); w.add_argument("--prefix", type=Path, default=DEFAULT_PREFIX)
    w.add_argument("--lge-reference", type=Path, default=LGE_REFERENCE)
    w.add_argument("--lwr-reference", type=Path, default=LWR_REFERENCE); w.add_argument("--work", type=Path, default=WINDOWS_WORK)
    k = sub.add_parser("check-run"); k.add_argument("--dir", type=Path, required=True)
    k.add_argument("--reference", type=Path, default=None); k.add_argument("--lge-reference", type=Path, default=LGE_REFERENCE)
    k.add_argument("--lwr-reference", type=Path, default=LWR_REFERENCE)
    z = sub.add_parser("private-zip"); z.add_argument("--zip", type=Path, default=PRIVATE / "lrgd-private-reference.zip")
    s = sub.add_parser("source"); s.add_argument("--zip", type=Path, required=True)
    r = sub.add_parser("run")
    r.add_argument("--sdk", type=Path, required=True); r.add_argument("--prefix", type=Path, required=True)
    r.add_argument("--private", type=Path, required=True); r.add_argument("--reference", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--repeats", type=int, default=3); r.add_argument("--cycles-repeats", type=int, default=2)
    r.add_argument("--traced-repeats", type=int, default=2)
    e = sub.add_parser("evidence"); e.add_argument("--out", type=Path, required=True)
    e.add_argument("--zip", type=Path, required=True); e.add_argument("--failure", action="store_true")
    a = sub.add_parser("audit"); a.add_argument("--archive", type=Path, required=True)
    a.add_argument("--implementation", required=True); a.add_argument("--reference", type=Path, required=True)
    a.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    args = ap.parse_args()
    if args.cmd == "source-contract":
        contract = source_contract(args.sdk.resolve())
        print(f"LRGD_SOURCE_CONTRACT PASS facts={fact_count(contract)} sdk={contract['sdk']}")
    elif args.cmd == "private-check":
        result = private_check(args.private.resolve(), args.production_init)
        print(f"LRGD_PRIVATE PASS manifest={result['generated_manifest_sha256']} files={len(result['files'])} "
              f"zip={result['private_zip_sha256'] or 'absent'} init={result['init_sha256'] or 'absent'} "
              f"layout=0x{result['pch']['REX_IMAGE_BASE']:x}/0x{result['pch']['REX_IMAGE_SIZE']:x}"
              f"/0x{result['pch']['REX_CODE_BASE']:x}/0x{result['pch']['REX_CODE_SIZE']:x}")
    elif args.cmd == "windows":
        require(args.repeats >= 1, "positive repetition count")
        windows_reference(args.private.resolve(), args.prefix.resolve(), args.repeats, args.work.resolve(),
                          args.lge_reference, args.lwr_reference)
    elif args.cmd == "check-run":
        if args.reference is not None:
            refs, _ = load_references(args.reference)
        else:
            refs, _ = load_references(None, args.lge_reference, args.lwr_reference)
        result = check_run(args.dir, refs)
        print(f"LRGD_CHECK_RUN PASS dir={args.dir} rows={result['dispatch']['rows']} dispatch_sha256={result['dispatch_sha256']}")
    elif args.cmd == "private-zip":
        private_zip(args.zip.resolve())
    elif args.cmd == "source":
        package_source(args.zip.resolve())
    elif args.cmd == "run":
        require(min(args.repeats, args.cycles_repeats, args.traced_repeats) >= 1, "positive repetition counts")
        run_native(args)
    elif args.cmd == "evidence":
        package_evidence(args.out, args.zip.resolve(), args.failure)
    else:
        audit(args.archive, args.implementation, args.reference, args.sdk.resolve())


if __name__ == "__main__":
    try:
        main()
    except GateError as error:
        print(f"LRGD_GATE FAIL: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:  # Unexpected runner fault: keep the traceback, still a FAIL.
        traceback.print_exc()
        print(f"LRGD_GATE FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
