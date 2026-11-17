#!/usr/bin/env python3
"""LM-A A2: compare Windows objects of generated partitions built from two generated trees (prints a verdict only).

COFF objects carry a timestamp, and -gline-tables-only debug sections record the checksums of included files (the pch
text changes with the guarded portable block), so whole-file bytes differ even for unchanged sources. What must be
identical is everything that executes or drives exception handling: the disassembly with raw bytes, the .pdata,
.xdata and .rdata contents, and the relocations of every non-debug section.

    python tools/m4_object_compare.py BEFORE_DIR AFTER_DIR      (directories holding the same *.obj names)
Prints M4_OBJECT_COMPARE PASS|FAIL objects=N.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

OBJDUMP = shutil.which("llvm-objdump") or r"C:\Program Files\LLVM\bin\llvm-objdump.exe"


def run(*args):
    return subprocess.run([OBJDUMP, *args], capture_output=True, text=True).stdout


def facets(path):
    body = lambda text: "\n".join(text.splitlines()[2:])  # drop the file-name header
    relocs = {}
    for m in re.finditer(r"RELOCATION RECORDS FOR \[([^\]]+)\]:\n(.*?)(?=\n\nRELOCATION RECORDS FOR|\Z)",
                         run("-r", str(path)), re.S):
        if "debug" not in m[1]:
            relocs.setdefault(m[1], []).append(m[2])
    return {"code": body(run("-d", str(path))),
            "seh_and_rdata": body(run("-s", "-j", ".xdata", "-j", ".pdata", "-j", ".rdata", str(path))),
            "relocations": relocs}


def main():
    before, after = Path(sys.argv[1]), Path(sys.argv[2])
    names = sorted(p.name for p in before.glob("*.obj"))
    failures = 0
    for name in names:
        a, b = facets(before / name), facets(after / name)
        differ = [k for k in a if a[k] != b[k]]
        failures += bool(differ)
        print(f"{name}: {'identical' if not differ else 'DIFFER ' + ','.join(differ)}")
    print(f"M4_OBJECT_COMPARE {'PASS' if names and not failures else 'FAIL'} objects={len(names)}")
    return 0 if names and not failures else 1


if __name__ == "__main__":
    sys.exit(main())
