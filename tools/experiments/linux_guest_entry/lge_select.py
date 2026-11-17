#!/usr/bin/env python3
"""LGE static selector over the PRIVATE generated PPC->C++ tree (read-only).

Classifies every generated function by the forms its body uses and computes
call closures. A function is *eligible* when its own body uses only:

  - GPR / CR / XER / LR / CTR context fields (no FPR, VMX, FPSCR, MSR, reserve);
  - plain scalar REX_LOAD_U{8,16,32,64} / REX_STORE_U{8,16,32,64};
  - local gotos/labels, `return`, and direct calls to other generated functions;
  - integer builtins (clz, rotate, bswap) and the CR compare helper;

and none of: MMIO macros, indirect calls/lookup, raw address/string views,
memset/memcpy, global locks, traps, atomics, reservations, imports (__imp__
calls), setjmp/longjmp, M4 SEH scaffolding, timebase, unimplemented opcodes,
floating point or vector code, and no absolute guest-address constants
(lis of an image/heap address) so every touched address derives from the
argument registers or the stack pointer.

A *candidate* is an eligible function whose whole transitive call closure is
eligible and small. Output is PRIVATE (function names, addresses, digests):
private/work/linux_guest_entry/selection/. Nothing here reproduces code.
The tool never modifies its inputs.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEFAULT_GENERATED = REPO / "private" / "work" / "rex" / "generated" / "Default"
DEFAULT_OUT = REPO / "private" / "work" / "linux_guest_entry" / "selection"

FUNC_DEF = re.compile(r"^DEFINE_REX_FUNC\((\w+)\) \{$")
CALL = re.compile(r"\b((?:sub|__savegprlr|__restgprlr|__savefpr|__restfpr|__savevmx|__restvmx)_\w+)\(ctx, base\);")
CTX_FIELD = re.compile(r"\bctx\.([a-z_]+)")
ALLOWED_CTX = {"r", "cr", "xer", "lr", "ctr"}
FORBIDDEN = [
    ("mmio", re.compile(r"\bREX_MM_")),
    ("indirect", re.compile(r"\bREX_CALL_INDIRECT_FUNC\b|\bREX_LOOKUP_FUNC\b|PPCFunc")),
    ("raw_addr", re.compile(r"\bREX_RAW_ADDR\b|\bREX_LOAD_STRING\b")),
    ("bulk", re.compile(r"\bmem(?:set|cpy|move)\b")),
    ("global_lock", re.compile(r"GLOBAL_LOCK")),
    ("trap", re.compile(r"\bppc_trap\b|__builtin_trap|__fastfail|\babort\b")),
    ("atomic", re.compile(r"atomic|__sync_|_Interlocked")),
    ("import", re.compile(r"\b__imp__\w+\(")),
    ("setjmp", re.compile(r"ppc_setjmp|ppc_longjmp")),
    ("m4_seh", re.compile(r"\bM4\w*|__try|__except|__finally")),
    ("timebase", re.compile(r"REX_QUERY_TIMEBASE")),
    ("unimplemented", re.compile(r"REX_UNIMPLEMENTED")),
    ("float", re.compile(r"\b(?:double|float|fma|sqrt|isnan|fabs)\b|FlushMode")),
    ("vector", re.compile(r"simde|\bv128\b|__m128")),
    ("switch", re.compile(r"\bswitch\b")),
]
ABS_CONST = re.compile(r"ctx\.r\d+\.s64 = (-?\d+);")
LIS = re.compile(r"^\s*//\s+lis\s+r\d+,(-?\d+)")
MEM = re.compile(r"\bREX_(LOAD|STORE)_U(8|16|32|64)\(")
LABEL = re.compile(r"^loc_([0-9A-F]{8}):$")
GOTO = re.compile(r"goto loc_([0-9A-F]{8});")
INSN = re.compile(r"^\s*//\s+([a-z][a-z0-9_.]*)")


def parse(generated):
    funcs = {}
    for path in sorted(generated.glob("r3hd_recomp.*.cpp")):
        lines = path.read_bytes().decode("utf-8").split("\n")
        i = 0
        while i < len(lines):
            m = FUNC_DEF.match(lines[i].rstrip("\r"))
            if not m:
                i += 1
                continue
            name = m.group(1)
            start = i
            j = i + 1
            while j < len(lines) and lines[j].rstrip("\r") != "}":
                j += 1
            body = [l.rstrip("\r") for l in lines[start:j + 1]]
            text = "\n".join(body) + "\n"
            funcs[name] = {"file": path.name, "line": start + 1, "body": body,
                           "sha256": hashlib.sha256(text.encode()).hexdigest(),
                           "bytes": len(text.encode())}
            i = j + 1
    return funcs


def classify(info):
    body = info["body"]
    code = [l for l in body[1:-1] if not l.strip().startswith("//")]
    comments = [l for l in body if l.strip().startswith("//")]
    reasons = set()
    for line in code:
        if "REX_FUNC_PROLOGUE" in line:
            continue
        for key, rx in FORBIDDEN:
            if rx.search(line):
                reasons.add(key)
        for field in CTX_FIELD.findall(line):
            base = re.sub(r"\d+$", "", field)
            if base not in ALLOWED_CTX:
                reasons.add("ctx_" + base)
    for line in comments:
        m = LIS.match(line)
        if m:
            v = int(m.group(1)) & 0xFFFF
            # 0x7000..0xFFFF upper halves are image/heap/MMIO/physical addresses.
            if v >= 0x7000 or v in range(0x4000, 0x7000):
                reasons.add("abs_address")
    calls = sorted(set(CALL.findall("\n".join(code))))
    mnemonics = [INSN.match(l).group(1) for l in comments if INSN.match(l)]
    labels = [LABEL.match(l.strip()).group(1) for l in code if LABEL.match(l.strip())]
    gotos = GOTO.findall("\n".join(code))
    loads = stores = 0
    widths = set()
    for kind, width in MEM.findall("\n".join(code)):
        widths.add(int(width))
        if kind == "LOAD":
            loads += 1
        else:
            stores += 1
    name_addr = info.get("name", "")
    backward = 0
    for line_no, line in enumerate(code):
        for target in GOTO.findall(line):
            for k, l2 in enumerate(code[:line_no]):
                if l2.strip() == f"loc_{target}:":
                    backward += 1
                    break
    return {"reasons": sorted(reasons), "calls": calls, "insns": len(mnemonics),
            "mnemonics": sorted(set(mnemonics)), "labels": len(labels), "gotos": len(gotos),
            "backward_branches": backward, "loads": loads, "stores": stores,
            "widths": sorted(widths)}


def closure(name, funcs, limit=12):
    seen, stack = [], [name]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.append(n)
        if len(seen) > limit:
            return None
        if n not in funcs:
            return None
        stack.extend(funcs[n]["class"]["calls"])
    return sorted(seen)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--generated", type=Path, default=DEFAULT_GENERATED)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max-closure", type=int, default=6)
    args = ap.parse_args(argv)
    funcs = parse(args.generated)
    if not funcs:
        print("LGE_SELECT FAIL: no generated functions", file=sys.stderr)
        return 1
    for name, info in funcs.items():
        info["class"] = classify(info)
    reason_counts = {}
    eligible = []
    for name, info in funcs.items():
        r = info["class"]["reasons"]
        for k in r:
            reason_counts[k] = reason_counts.get(k, 0) + 1
        if not r:
            eligible.append(name)
    eligible_set = set(eligible)
    candidates = []
    for name in eligible:
        cl = closure(name, funcs, args.max_closure)
        if cl is None or not all(c in eligible_set for c in cl):
            continue
        c = funcs[name]["class"]
        candidates.append({
            "name": name, "file": funcs[name]["file"], "line": funcs[name]["line"],
            "sha256": funcs[name]["sha256"], "closure": cl,
            "insns": c["insns"], "loads": c["loads"], "stores": c["stores"],
            "widths": c["widths"], "backward_branches": c["backward_branches"],
            "calls": c["calls"], "mnemonics": c["mnemonics"],
        })
    inputs = sorted(args.generated.glob("r3hd_recomp.*.cpp"))
    agg = hashlib.sha256()
    for p in inputs:
        agg.update(p.name.encode() + b"\0" + hashlib.sha256(p.read_bytes()).hexdigest().encode() + b"\n")
    args.out.mkdir(parents=True, exist_ok=True)
    result = {
        "generated_dir": str(args.generated), "inputs": len(inputs), "input_aggregate_sha256": agg.hexdigest(),
        "functions": len(funcs), "eligible": len(eligible), "candidates": len(candidates),
        "exclusion_reason_counts": dict(sorted(reason_counts.items())),
        "candidate_list": candidates,
    }
    (args.out / "selection_census.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(f"LGE_SELECT functions={len(funcs)} eligible={len(eligible)} candidates={len(candidates)} "
          f"inputs={len(inputs)} aggregate={agg.hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
