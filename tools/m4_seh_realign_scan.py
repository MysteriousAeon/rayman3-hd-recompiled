#!/usr/bin/env python3
"""E-373: find M4 owners whose compiled Windows frame is dynamically realigned (read-only; prints names only).

clang's x64 SEH __except filter funclets recover parent locals at a fixed offset from the establisher frame, while a
function with dynamic stack realignment (`and rsp, -N` in the prologue) addresses its locals from the realigned base
register. In such an owner the M4 filter reads a wrong M4Frame and the owner's __except never accepts. This scan
disassembles the production objects of every owner partition and lists the owner functions with a realigning prologue.

    python tools/m4_seh_realign_scan.py [--obj-dir DIR]
Prints M4_SEH_REALIGN owners=N realigned=[...]. Needs LLVM's llvm-objdump.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "private/work/rex/generated/default"
OBJ = ROOT / "private/work/rex/out/build/win-amd64-release/CMakeFiles/r3hd_recomp.dir/generated/default"
SYMBOL = re.compile(r"^[0-9a-f]+ <(__imp__\w+)>:$", re.M)


def owners():
    found = {}
    for p in GEN.glob("r3hd_recomp.*.cpp"):
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"DEFINE_REX_FUNC\((\w+)\) \{(.*?)^\}", text, re.M | re.S):
            if "M4_FRAME(" in m[2] or "M4Init(" in m[2]:
                found.setdefault(p.name, set()).add("__imp__" + m[1])
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--obj-dir", type=Path, default=OBJ)
    args = ap.parse_args()
    objdump = shutil.which("llvm-objdump") or r"C:\Program Files\LLVM\bin\llvm-objdump.exe"
    by_file = owners()
    total, realigned = sum(len(v) for v in by_file.values()), []
    for name, funcs in sorted(by_file.items()):
        obj = args.obj_dir / (name + ".obj")
        text = subprocess.run([objdump, "-d", "--no-show-raw-insn", str(obj)], capture_output=True, text=True).stdout
        starts = [(m.start(), m[1]) for m in SYMBOL.finditer(text)]
        for i, (pos, sym) in enumerate(starts):
            if sym not in funcs:
                continue
            body = text[pos:starts[i + 1][0] if i + 1 < len(starts) else len(text)]
            prologue = "\n".join(body.splitlines()[:40])
            if re.search(r"\band[q]?\s+\$-0x[0-9a-f]+, ?%rsp", prologue):
                realigned.append(sym)
    print(f"M4_SEH_REALIGN owners={total} realigned={sorted(realigned)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
