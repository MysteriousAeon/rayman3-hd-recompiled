#!/usr/bin/env python3
"""Static, read-only census of memory access forms in generated PPC->C++ code.

Reads the private generated sources and the pinned SDK macro definitions and
writes aggregate counts only (census.json, census.md) under a private output
directory. It never modifies its inputs. Output carries counts, macro names and
at most 3 short, register/number-normalised example lines per category; it
never reproduces function bodies, function names or guest addresses.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEFAULT_GENERATED = REPO / "private" / "work" / "rex" / "generated" / "Default"
DEFAULT_SDK = REPO / "external" / "rexglue-sdk"
DEFAULT_OUT = REPO / "private" / "work" / "linux_runtime_bootstrap" / "census"
SDK_MACRO_FILES = (
    "resources/templates/codegen/pch_h.inja",
    "resources/templates/codegen/_indirect_call.inja",
)
MAX_EXAMPLES = 3
EXAMPLE_WIDTH = 100

FUNC_DEF = re.compile(r"^(?:DEFINE_REX_FUNC|PPC_FUNC_IMPL|PPC_FUNC|PPC_WEAK_FUNC)\s*\(\s*(\w+)")
COMMENT_MNEMONIC = re.compile(r"^\s*//\s+([a-z][a-z0-9_.]*)(?:\s|$)")

# ---- guest mnemonic groups (from the translator's per-instruction comments) ----
def _expand(bases, suffixes):
    return {b + s for b in bases for s in suffixes}

MNEMONIC_GROUPS = {
    "int_load": _expand(["lbz", "lhz", "lha", "lwz", "lwa"], ["", "u", "x", "ux"]) | {"ld", "ldu", "ldx", "ldux"},
    "int_store": _expand(["stb", "sth", "stw"], ["", "u", "x", "ux"]) | {"std", "stdu", "stdx", "stdux"},
    "byte_reversed": {"lhbrx", "lwbrx", "ldbrx", "sthbrx", "stwbrx", "stdbrx"},
    "fp_load": _expand(["lfs", "lfd"], ["", "u", "x", "ux"]),
    "fp_store": _expand(["stfs", "stfd"], ["", "u", "x", "ux"]) | {"stfiwx"},
    "vec_load_aligned": {"lvx", "lvx128", "lvxl", "lvxl128"},
    "vec_store_aligned": {"stvx", "stvx128", "stvxl", "stvxl128"},
    "vec_element": {"lvewx", "lvewx128", "stvewx", "stvewx128", "lvehx", "stvehx"},
    "vec_left_right_partial": {
        "lvlx", "lvlx128", "lvlxl", "lvlxl128", "lvrx", "lvrx128", "lvrxl", "lvrxl128",
        "stvlx", "stvlx128", "stvlxl", "stvlxl128", "stvrx", "stvrx128", "stvrxl", "stvrxl128",
    },
    "multiword_string": {"lmw", "stmw", "lswi", "lswx", "stswi", "stswx"},
    "reservation": {"lwarx", "ldarx", "stwcx.", "stdcx."},
    "cache_block": {"dcbz", "dcbz128", "dcbzl", "dcbt", "dcbtst", "dcbf", "dcbst", "dcbi", "icbi", "dcbtds", "dcbtstds"},
    "sync_barrier": {"sync", "lwsync", "eieio", "isync", "ptesync"},
}
MNEMONIC_TO_GROUP = {m: g for g, ms in MNEMONIC_GROUPS.items() for m in ms}
NON_MEMORY_L_ST = {"li", "lis", "lvsl", "lvsr", "lvsl128", "lvsr128", "lvlinsert"}
MEMORYISH_MNEMONIC = re.compile(r"^(?:l[a-z0-9]*|st[a-z0-9.]*|dcb\w*|icb\w*)$")

# ---- token patterns: (key, literal-prefilter, regex) ----
TOKENS = []
for _w in (8, 16, 32, 64):
    TOKENS.append((f"scalar_load_u{_w}", "REX_LOAD_U", re.compile(rf"\bREX_LOAD_U{_w}\b")))
    TOKENS.append((f"scalar_store_u{_w}", "REX_STORE_U", re.compile(rf"\bREX_STORE_U{_w}\b")))
    TOKENS.append((f"mmio_load_u{_w}", "REX_MM_LOAD_U", re.compile(rf"\bREX_MM_LOAD_U{_w}\b")))
    TOKENS.append((f"mmio_store_u{_w}", "REX_MM_STORE_U", re.compile(rf"\bREX_MM_STORE_U{_w}\b")))
TOKENS += [
    ("load_string", "REX_LOAD_STRING", re.compile(r"\bREX_LOAD_STRING\b")),
    ("raw_addr", "REX_RAW_ADDR", re.compile(r"\bREX_RAW_ADDR\b")),
    ("global_lock_enter", "REX_ENTER_GLOBAL_LOCK", re.compile(r"\bREX_ENTER_GLOBAL_LOCK\b")),
    ("global_lock_leave", "REX_LEAVE_GLOBAL_LOCK", re.compile(r"\bREX_LEAVE_GLOBAL_LOCK\b")),
    ("global_lock_check", "REX_CHECK_GLOBAL_LOCK", re.compile(r"\bREX_CHECK_GLOBAL_LOCK\b")),
    ("call_indirect_func", "REX_CALL_INDIRECT_FUNC", re.compile(r"\bREX_CALL_INDIRECT_FUNC\b")),
    ("lookup_func", "REX_LOOKUP_FUNC", re.compile(r"\bREX_LOOKUP_FUNC\b")),
    ("bulk_memset", "memset", re.compile(r"\bmemset\b")),
    ("bulk_memcpy", "memcpy", re.compile(r"\bmemcpy\b")),
    ("bulk_memmove", "memmove", re.compile(r"\bmemmove\b")),
    ("atomic_thread_fence", "atomic_thread_fence", re.compile(r"\bstd::atomic_thread_fence\b")),
    ("host_atomic_other", "atomic", re.compile(r"__atomic\w*|std::atomic(?!_thread_fence)|_Interlocked\w*")),
    ("host_sync_builtin_other", "__sync_", re.compile(r"__sync_(?!bool_compare_and_swap)\w+")),
    ("unaligned_intrinsic", "simde_mm_", re.compile(
        r"\bsimde_mm_(?:loadu|storeu|lddqu|loadl|loadh|storel|storeh|stream|maskload|maskstore)\w*")),
    ("direct_base_arith", "base", re.compile(r"\bbase\s*\+")),
]
RAW_ADDR_RE = re.compile(r"\bREX_RAW_ADDR\b")

# ---- RAW_ADDR line classes ----
RAWCLASS = [
    ("raw_vec_load_si128", re.compile(r"simde_mm_load_si128\(\(simde__m128i\*\)REX_RAW_ADDR")),
    ("raw_vec_store_si128", re.compile(r"simde_mm_store_si128\(\(simde__m128i\*\)REX_RAW_ADDR")),
    ("raw_reservation_cas", re.compile(r"__sync_bool_compare_and_swap\(reinterpret_cast<uint(?:32|64)_t\*>\(REX_RAW_ADDR")),
    ("raw_reservation_load", re.compile(r"reserved\.\w+\s*=\s*\*\(uint(?:32|64)_t\*\)REX_RAW_ADDR")),
    ("raw_bulk_memset", re.compile(r"\bmemset\s*\(\s*\(void\*\)REX_RAW_ADDR")),
    ("raw_bulk_memcpy_memmove", re.compile(r"\bmem(?:cpy|move)\s*\(.*REX_RAW_ADDR")),
    ("raw_plain_deref", re.compile(r"\*\(uint(?:8|16|32|64)_t\*\)REX_RAW_ADDR")),
]
RESERVATION_WIDTH = re.compile(r"(?:reserved\.\w+\s*=\s*\*\(uint(32|64)_t\*\)REX_RAW_ADDR|compare_and_swap\(reinterpret_cast<uint(32|64)_t\*>\(REX_RAW_ADDR)")
MEMSET_SIZE = re.compile(r"memset\s*\(\s*\(void\*\)REX_RAW_ADDR\([^)]*\)\s*,\s*[^,]+,\s*(\w+)\s*\)")
SCALAR_ARG = re.compile(r"\bREX_(?:LOAD|STORE)_U(?:8|16|32|64)\(([^,)]*)")
EA_MASK = re.compile(r"\bea\s*=\s*.*&\s*~\s*(0x[0-9A-Fa-f]+|\d+)")
TEMP_MASK = re.compile(r"REX_RAW_ADDR\(temp\.\w+\s*&\s*~\s*(0x[0-9A-Fa-f]+|\d+)\)")
VEC_TABLES = re.compile(r"\b(VectorMaskL|VectorMaskR|VectorShiftTableL|VectorShiftTableR)\b")

# ---- aggregation categories ----
def sumkeys(c, keys):
    return sum(c.get(k, 0) for k in keys)


KEY_GROUPS = {}
for _d in ("load", "store"):
    for _w in (8, 16, 32, 64):
        KEY_GROUPS.setdefault(f"scalar_{_d}_u{_w}", []).append("grp:scalar_all")
        KEY_GROUPS.setdefault(f"mmio_{_d}_u{_w}", []).append("grp:mmio_all")
        if _w != 8:
            KEY_GROUPS[f"scalar_{_d}_u{_w}"].append("grp:scalar_multibyte")
KEY_GROUPS["raw_vec_load_si128"] = ["grp:vector_all"]
KEY_GROUPS["raw_vec_store_si128"] = ["grp:vector_all"]
KEY_GROUPS["host_atomic_other"] = ["grp:other_atomics"]
KEY_GROUPS["host_sync_builtin_other"] = ["grp:other_atomics"]
KEY_GROUPS["mmio_store_u32"].append("grp:mmio_load_store_any")


def classify_scalar_arg(arg):
    a = arg.strip()
    if re.fullmatch(r"ea", a):
        return "ea_variable"
    if re.fullmatch(r"ctx\.\w+\.\w+\s*[+-]\s*(?:0x[0-9A-Fa-f]+|\d+)", a):
        return "reg_plus_imm"
    if re.fullmatch(r"ctx\.\w+\.\w+\s*\+\s*ctx\.\w+\.\w+", a):
        return "reg_plus_reg"
    if re.fullmatch(r"ctx\.\w+\.\w+", a):
        return "reg_only"
    if re.fullmatch(r"(?:0x[0-9A-Fa-f]+|\d+)", a):
        return "constant"
    return "other"


def normalise_example(line):
    s = line.strip()
    s = re.sub(r"sub_[0-9A-Fa-f]+", "sub_N", s)
    s = re.sub(r"ctx\.[A-Za-z_]+\d*\.", "R.", s)
    s = re.sub(r"0x[0-9A-Fa-f]+|\b\d+\b", "N", s)
    return s[:EXAMPLE_WIDTH]


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def aggregate_digest(items):
    h = hashlib.sha256()
    for name, digest in sorted(items):
        h.update(name.encode() + b"\0" + digest.encode() + b"\n")
    return h.hexdigest()


def git_show(sdk, rev, path):
    try:
        r = subprocess.run(["git", "-C", str(sdk), "show", f"{rev}:{path}"],
                           capture_output=True, check=True)
        return r.stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def sdk_identity(sdk):
    """Pin identity: HEAD of the SDK checkout; macro text from the pinned blob."""
    sdk = Path(sdk)
    pin = None
    try:
        pin = subprocess.run(["git", "-C", str(sdk), "rev-parse", "HEAD"],
                             capture_output=True, check=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    files = {}
    texts = []
    for rel in SDK_MACRO_FILES:
        wp = sdk / rel
        working = wp.read_bytes() if wp.is_file() else None
        pinned = git_show(sdk, pin, rel) if pin else None
        files[rel] = {
            "working_sha256": sha256_bytes(working) if working is not None else None,
            "pinned_sha256": sha256_bytes(pinned) if pinned is not None else None,
            "working_equals_pin": (working == pinned) if working is not None and pinned is not None else None,
        }
        src = pinned if pinned is not None else working
        if src is not None:
            texts.append(src.decode("utf-8", "replace"))
    return pin, files, "\n".join(texts)


MACRO_NAMES = [
    "REX_RAW_ADDR", "REX_PHYS_HOST_OFFSET", "REX_IS_MMIO_ADDR", "REX_FUNC_PROLOGUE",
    "REX_LOAD_U8", "REX_LOAD_U16", "REX_LOAD_U32", "REX_LOAD_U64",
    "REX_STORE_U8", "REX_STORE_U16", "REX_STORE_U32", "REX_STORE_U64",
    "REX_MM_LOAD_U8", "REX_MM_LOAD_U16", "REX_MM_LOAD_U32", "REX_MM_LOAD_U64",
    "REX_MM_STORE_U8", "REX_MM_STORE_U16", "REX_MM_STORE_U32", "REX_MM_STORE_U64",
    "REX_LOOKUP_FUNC", "REX_CALL_INDIRECT_FUNC",
    "REX_ENTER_GLOBAL_LOCK", "REX_LEAVE_GLOBAL_LOCK", "REX_CHECK_GLOBAL_LOCK",
]


def macro_forms(text):
    """First #define line of each macro of interest (SDK text, not game code)."""
    out = {}
    for name in MACRO_NAMES:
        m = re.search(rf"^[ \t]*#\s*define\s+{name}\b[^\n]*", text, re.M)
        out[name] = re.sub(r"\s+", " ", m.group(0).rstrip(" \\")).strip() if m else None
    return out


def scan_file(path, st):
    in_func = None
    cur_cats = set()
    cpp = True

    def close():
        for c in cur_cats:
            st["func_count"][c] += 1
        cur_cats.clear()

    def hit(cat, n, line):
        st["occ"][cat] += n
        if in_func is not None:
            cur_cats.add(cat)
            cur_cats.update(KEY_GROUPS.get(cat, ()))
        ex = st["examples"][cat]
        if len(ex) < MAX_EXAMPLES:
            ex.append(normalise_example(line))

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = FUNC_DEF.match(line) if cpp else None
            if m:
                close()
                in_func = m.group(1)
                st["functions"] += 1
                continue
            if cpp and in_func is not None and line.startswith("}"):
                close()
                in_func = None
                continue
            st["lines"] += 1
            s = line.lstrip()
            if s.startswith("//"):
                mm = COMMENT_MNEMONIC.match(line)
                if mm:
                    mn = mm.group(1)
                    g = MNEMONIC_TO_GROUP.get(mn)
                    if g:
                        st["mn"][mn] += 1
                        hit("mn:" + g, 1, line)
                        if in_func is not None:
                            cur_cats.add("mnm:" + mn)
                    elif mn not in NON_MEMORY_L_ST and MEMORYISH_MNEMONIC.match(mn):
                        st["unclassified_mn"][mn] += 1
                continue
            if "REX_" in line or "memset" in line or "memcpy" in line or "memmove" in line \
                    or "simde_mm_" in line or "atomic" in line or "__sync_" in line \
                    or "Interlocked" in line or "base" in line:
                for key, lit, rx in TOKENS:
                    if lit in line:
                        n = len(rx.findall(line))
                        if n:
                            hit(key, n, line)
                if "REX_RAW_ADDR" in line:
                    n_raw = len(RAW_ADDR_RE.findall(line))
                    matched = False
                    for key, rx in RAWCLASS:
                        if rx.search(line):
                            hit(key, n_raw, line)
                            matched = True
                            break
                    if not matched:
                        hit("raw_other_unclassified", n_raw, line)
                    wm = RESERVATION_WIDTH.search(line)
                    if wm:
                        st["reservation_width"][wm.group(1) or wm.group(2)] += 1
                    mt = MEMSET_SIZE.search(line)
                    if mt:
                        st["memset_size"][mt.group(1)] += 1
                    tm = TEMP_MASK.search(line)
                    if tm:
                        st["partial_vec_mask"][tm.group(1)] += 1
                    for t in VEC_TABLES.findall(line):
                        st["vec_tables"][t] += 1
                if "REX_LOAD_U" in line or "REX_STORE_U" in line:
                    for a in SCALAR_ARG.findall(line):
                        st["scalar_arg_form"][classify_scalar_arg(a)] += 1
                for t in re.findall(r"\bREX_[A-Z0-9_]+\b", line):
                    st["rex_tokens_all"][t] += 1
            elif "VectorShiftTable" in line or "VectorMask" in line:
                for t in VEC_TABLES.findall(line):
                    st["vec_tables"][t] += 1
            if "ea =" in line:
                em = EA_MASK.search(line)
                if em:
                    st["ea_mask"][em.group(1).lower()] += 1
                else:
                    st["ea_unmasked"] += 1
    close()


KNOWN_REX_TOKENS = {
    "REX_FUNC_PROLOGUE", "REX_CALL_FUNC", "REX_QUERY_TIMEBASE", "REX_SET_FLUSH_MODE",
    "REX_UNIMPLEMENTED", "REX_IMAGE_BASE", "REX_IMAGE_SIZE", "REX_CODE_BASE", "REX_CODE_SIZE",
    "REX_THUNK_RESERVE_SIZE", "REX_MEMORY_SIZE",
}


def build_result(generated, sdk):
    files = sorted(p for p in Path(generated).iterdir()
                   if p.is_file() and p.suffix in (".cpp", ".h"))
    # Only .cpp are counted: .h carry declarations and a copy of the macro
    # definitions, which would inflate token counts.
    st = {
        "occ": Counter(), "func_count": Counter(), "examples": {},
        "functions": 0, "lines": 0, "mn": Counter(), "unclassified_mn": Counter(),
        "reservation_width": Counter(), "memset_size": Counter(), "partial_vec_mask": Counter(),
        "vec_tables": Counter(), "scalar_arg_form": Counter(), "rex_tokens_all": Counter(),
        "ea_mask": Counter(), "ea_unmasked": 0,
    }

    class Ex(dict):
        def __missing__(self, k):
            self[k] = []
            return self[k]
    st["examples"] = Ex()

    hashes = []
    for p in files:
        hashes.append((p.name, sha256_file(p)))
        if p.suffix == ".cpp":
            scan_file(p, st)

    pin, sdk_files, sdk_text = sdk_identity(sdk)
    forms = macro_forms(sdk_text)
    if not forms.get("REX_LOAD_U32") or not forms.get("REX_STORE_U32") or not forms.get("REX_RAW_ADDR"):
        raise SystemExit("ACCESS_CENSUS FAIL sdk macro definitions not found")

    occ, fc = st["occ"], st["func_count"]

    def group_row(name, keys, grp=None):
        # distinct-function count: exact for single keys and for groups with a tracked tag.
        fcs = [fc.get(k, 0) for k in keys]
        if grp:
            return {"occurrences": sumkeys(occ, keys), "functions_exact": fc.get(grp, 0),
                    "functions_lower_bound_max_member": max(fcs) if fcs else 0}
        return {
            "occurrences": sumkeys(occ, keys),
            "functions_exact": fcs[0] if len(keys) == 1 else None,
            "functions_lower_bound_max_member": max(fcs) if fcs else 0,
        }

    scalar = {}
    for w in (8, 16, 32, 64):
        scalar[f"load_u{w}"] = group_row("", [f"scalar_load_u{w}"])
        scalar[f"store_u{w}"] = group_row("", [f"scalar_store_u{w}"])
    all_scalar = [f"scalar_{d}_u{w}" for d in ("load", "store") for w in (8, 16, 32, 64)]
    multi_scalar = [f"scalar_{d}_u{w}" for d in ("load", "store") for w in (16, 32, 64)]
    mmio = [f"mmio_{d}_u{w}" for d in ("load", "store") for w in (8, 16, 32, 64)]
    vec = ["raw_vec_load_si128", "raw_vec_store_si128"]
    vec_row = group_row("", vec, "grp:vector_all")

    total_mem_tokens = sumkeys(occ, all_scalar + mmio + vec + ["raw_bulk_memset"])
    size_counts = {
        "1_byte": sumkeys(occ, ["scalar_load_u8", "scalar_store_u8", "mmio_load_u8", "mmio_store_u8"]),
        "2_byte": sumkeys(occ, ["scalar_load_u16", "scalar_store_u16", "mmio_load_u16", "mmio_store_u16"]),
        "4_byte": sumkeys(occ, ["scalar_load_u32", "scalar_store_u32", "mmio_load_u32", "mmio_store_u32"]),
        "8_byte": sumkeys(occ, ["scalar_load_u64", "scalar_store_u64", "mmio_load_u64", "mmio_store_u64"]),
        "16_byte_vector_aligned": sumkeys(occ, vec),
    }
    multibyte = size_counts["2_byte"] + size_counts["4_byte"] + size_counts["8_byte"] + size_counts["16_byte_vector_aligned"]
    mn_groups = {g: {"occurrences": occ.get("mn:" + g, 0), "functions": fc.get("mn:" + g, 0)}
                 for g in sorted(MNEMONIC_GROUPS)}
    mn_each = {m: {"occurrences": c, "functions": fc.get("mnm:" + m, 0)} for m, c in sorted(st["mn"].items())}
    other_rex = {t: c for t, c in sorted(st["rex_tokens_all"].items())
                 if t not in KNOWN_REX_TOKENS and not re.fullmatch(
                     r"REX_(?:LOAD|STORE|MM_LOAD|MM_STORE)_U(?:8|16|32|64)|REX_RAW_ADDR|REX_LOAD_STRING|"
                     r"REX_(?:ENTER|LEAVE|CHECK)_GLOBAL_LOCK|REX_CALL_INDIRECT_FUNC|REX_LOOKUP_FUNC", t)}
    result = {
        "inputs": {
            "generated_file_count": len(files),
            "generated_cpp_count": sum(1 for p in files if p.suffix == ".cpp"),
            "generated_h_count": sum(1 for p in files if p.suffix == ".h"),
            "generated_aggregate_sha256": aggregate_digest(hashes),
            "function_definitions": st["functions"],
            "scanned_lines": st["lines"],
            "sdk_pin_head": pin,
            "sdk_macro_files": sdk_files,
        },
        "sdk_macro_forms": forms,
        "scalar_by_width": scalar,
        "scalar_total": group_row("", all_scalar, "grp:scalar_all"),
        "scalar_multibyte_total": group_row("", multi_scalar, "grp:scalar_multibyte"),
        "scalar_address_argument_form": dict(sorted(st["scalar_arg_form"].items())),
        "access_size_occurrences": size_counts,
        "multibyte_total_cross_page_upper_bound": multibyte,
        "total_guest_memory_access_tokens": total_mem_tokens,
        "mmio": {k: group_row("", [k]) for k in mmio if occ.get(k, 0)} | {"all": group_row("", mmio, "grp:mmio_all")},
        "vector_aligned_raw_addr": {
            "all": vec_row,
            "load_si128": group_row("", ["raw_vec_load_si128"]),
            "store_si128": group_row("", ["raw_vec_store_si128"]),
            "partial_left_right_mask_tables": dict(sorted(st["vec_tables"].items())),
            "partial_address_mask_literals": dict(sorted(st["partial_vec_mask"].items())),
        },
        "effective_address_alignment_masks": dict(sorted(st["ea_mask"].items())) | {"unmasked_ea_assignments": st["ea_unmasked"]},
        "reservations": {
            "load_reserved": group_row("", ["raw_reservation_load"]),
            "store_conditional_cas": group_row("", ["raw_reservation_cas"]),
            "width_bits_by_line": dict(sorted(st["reservation_width"].items())),
            "global_lock_enter": group_row("", ["global_lock_enter"]),
            "global_lock_leave": group_row("", ["global_lock_leave"]),
            "global_lock_check": group_row("", ["global_lock_check"]),
            "other_host_atomics": group_row("", ["host_atomic_other", "host_sync_builtin_other"], "grp:other_atomics"),
            "atomic_thread_fence": group_row("", ["atomic_thread_fence"]),
        },
        "bulk_memory": {
            "memset_raw_addr": group_row("", ["raw_bulk_memset"]),
            "memset_size_argument": dict(sorted(st["memset_size"].items())),
            "memset_tokens_all": group_row("", ["bulk_memset"]),
            "memcpy_tokens": group_row("", ["bulk_memcpy"]),
            "memmove_tokens": group_row("", ["bulk_memmove"]),
            "memcpy_memmove_with_raw_addr": group_row("", ["raw_bulk_memcpy_memmove"]),
        },
        "indirect_calls_and_code_addresses": {
            "call_indirect_func": group_row("", ["call_indirect_func"]),
            "lookup_func": group_row("", ["lookup_func"]),
        },
        "raw_addr": {
            "total": group_row("", ["raw_addr"]),
            "plain_deref_without_swap_class": group_row("", ["raw_plain_deref"]),
        },
        "explicit_unaligned_forms": {
            "unaligned_intrinsics_loadu_storeu_etc": group_row("", ["unaligned_intrinsic"]),
            "guest_mnemonics_partial_left_right": mn_groups["vec_left_right_partial"],
            "guest_mnemonics_multiword_string": mn_groups["multiword_string"],
            "guest_mnemonics_byte_reversed": mn_groups["byte_reversed"],
        },
        "guest_mnemonic_groups": mn_groups,
        "guest_mnemonics": mn_each,
        "unclassified_memory_like_mnemonics": dict(sorted(st["unclassified_mn"].items())),
        "other_unclassified": {
            "raw_addr_lines_not_matching_known_forms": group_row("", ["raw_other_unclassified"]),
            "direct_base_arithmetic_outside_macros": group_row("", ["direct_base_arith"]),
            "load_string": group_row("", ["load_string"]),
            "other_rex_tokens": other_rex,
        },
        "examples_normalised_max3": {k: v for k, v in sorted(st["examples"].items())},
    }
    return result


def render_md(r):
    L = ["# Access census (private output)", ""]
    i = r["inputs"]
    L += [f"- generated files: {i['generated_file_count']} ({i['generated_cpp_count']} cpp, {i['generated_h_count']} h)",
          f"- function definitions: {i['function_definitions']}",
          f"- generated aggregate sha256: {i['generated_aggregate_sha256']}",
          f"- sdk pin HEAD: {i['sdk_pin_head']}", ""]
    for rel, d in sorted(i["sdk_macro_files"].items()):
        L.append(f"- sdk {rel}: working==pin {d['working_equals_pin']} pin {d['pinned_sha256']}")
    L += ["", "## SDK macro definition forms (SDK text, first #define line)", ""]
    for k, v in sorted(r["sdk_macro_forms"].items()):
        L.append(f"- {k}: `{v}`")

    def table(title, rows):
        L.extend(["", f"## {title}", "", "| item | occurrences | functions |", "|---|---:|---:|"])
        for name, d in rows:
            fnc = d.get("functions_exact", d.get("functions"))
            if fnc is None:
                fnc = f">= {d.get('functions_lower_bound_max_member', 0)}"
            L.append(f"| {name} | {d['occurrences']} | {fnc} |")

    table("Scalar", sorted(r["scalar_by_width"].items()) + [("total", r["scalar_total"])])
    table("MMIO", sorted(r["mmio"].items()))
    rows = [("vector load_si128", r["vector_aligned_raw_addr"]["load_si128"]),
            ("vector store_si128", r["vector_aligned_raw_addr"]["store_si128"])]
    table("Vector (guest memory)", rows)
    table("Reservations and locks", [(k, v) for k, v in sorted(r["reservations"].items()) if isinstance(v, dict) and "occurrences" in v])
    table("Bulk", [(k, v) for k, v in sorted(r["bulk_memory"].items()) if isinstance(v, dict) and "occurrences" in v])
    table("Indirect calls", sorted(r["indirect_calls_and_code_addresses"].items()))
    table("Guest mnemonic groups (from translator comments)", sorted(r["guest_mnemonic_groups"].items()))
    L += ["", "## Other tables", ""]
    for key in ("access_size_occurrences", "scalar_address_argument_form", "effective_address_alignment_masks",
                "vector_aligned_raw_addr", "unclassified_memory_like_mnemonics", "other_unclassified"):
        L += [f"### {key}", "", "```", json.dumps(r[key], indent=1, sort_keys=True), "```", ""]
    L += [f"multibyte total (cross-page upper bound): {r['multibyte_total_cross_page_upper_bound']}", "",
          "## Normalised examples (max 3 per category, registers and numbers masked)", ""]
    for k, v in sorted(r["examples_normalised_max3"].items()):
        L.append(f"- {k}")
        for e in v:
            L.append(f"  - `{e}`")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--generated", default=str(DEFAULT_GENERATED))
    ap.add_argument("--sdk", default=str(DEFAULT_SDK))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args(argv)
    gen = Path(a.generated)
    if not gen.is_dir():
        print(f"ACCESS_CENSUS FAIL generated dir missing: {gen}", file=sys.stderr)
        return 2
    r = build_result(gen, a.sdk)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "census.json").write_text(json.dumps(r, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    (out / "census.md").write_text(render_md(r), encoding="utf-8", newline="\n")
    print(f"ACCESS_CENSUS PASS files={r['inputs']['generated_file_count']} "
          f"functions={r['inputs']['function_definitions']} "
          f"scalar={r['scalar_total']['occurrences']} "
          f"vector={r['vector_aligned_raw_addr']['load_si128']['occurrences'] + r['vector_aligned_raw_addr']['store_si128']['occurrences']} "
          f"digest={r['inputs']['generated_aggregate_sha256'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
