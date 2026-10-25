#!/usr/bin/env python3
"""Name module offsets from a fault log with linker maps (M11).

    python tools/m11_symbolize.py FAULT_LOG --map r3hd.exe=PATH.map --map rexruntime.dll=PATH.map [--code C0000374]

Reads `M2 exception` / `M2 stack N module=... offset=HEX` records (m2_faults.log) and prints, for each frame whose
module has a map, the nearest preceding public symbol and the distance to it. Output is names and offsets only.
The maps are MSVC-format maps as written by lld-link /MAP (r3hd.map is produced by the normal build; a map for
rexruntime.dll comes from relinking the existing objects, see reports/milestone11/REPORT.md).
"""
import argparse
import bisect
import os
import re
import subprocess

PUBLIC = re.compile(r"^\s*[0-9a-fA-F]{4}:[0-9a-fA-F]{8}\s+(\S+)\s+([0-9a-fA-F]{16})\s")
BASE = re.compile(r"Preferred load address is ([0-9a-fA-F]+)")
FRAME = re.compile(r"M2 stack (\d+) module=(.*) offset=([0-9A-Fa-f]+)")
EXC = re.compile(r"M2 exception code=([0-9A-Fa-f]+)")


def load_map(path):
    base = None
    table = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if base is None:
                m = BASE.search(line)
                if m:
                    base = int(m.group(1), 16)
                continue
            m = PUBLIC.match(line)
            if m:
                table.append((int(m.group(2), 16) - base, m.group(1)))
    table.sort()
    return [t[0] for t in table], [t[1] for t in table]


def demangle(names):
    exe = r"C:\Program Files\LLVM\bin\llvm-undname.exe"
    if not names or not os.path.exists(exe):
        return {}
    out = {}
    r = subprocess.run([exe, "--no-access-specifier", "--no-calling-convention", "--no-return-type",
                        "--no-member-type"] + names, capture_output=True, text=True)
    cur = None
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line in names and cur is None:
            cur = line
        elif cur is not None:
            out[cur] = line
            cur = None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--map", action="append", default=[], help="MODULE_FILE_NAME=MAP_PATH")
    ap.add_argument("--code", help="only exceptions with this code (hex)")
    a = ap.parse_args()
    maps = {}
    for spec in a.map:
        name, path = spec.split("=", 1)
        maps[name.lower()] = load_map(path)

    rows = []
    show = True
    for line in open(a.log, encoding="utf-8", errors="replace"):
        m = EXC.search(line)
        if m:
            show = a.code is None or m.group(1).lower() == a.code.lower()
            if show:
                rows.append(("exception", m.group(1), None, None))
            continue
        m = FRAME.search(line)
        if m and show:
            module = os.path.basename(m.group(2).strip().replace("\\", "/"))
            off = int(m.group(3), 16)
            sym = None
            if module.lower() in maps:
                addrs, names = maps[module.lower()]
                i = bisect.bisect_right(addrs, off) - 1
                if i >= 0:
                    sym = (names[i], off - addrs[i])
            rows.append((int(m.group(1)), module, off, sym))

    pretty = demangle(sorted({r[3][0] for r in rows if r[0] != "exception" and r[3]}))
    for r in rows:
        if r[0] == "exception":
            print(f"exception {r[1]}")
            continue
        n, module, off, sym = r
        text = ""
        if sym:
            text = f"  {pretty.get(sym[0], sym[0])} +0x{sym[1]:X}"
        print(f"  {n:2d} {module}+{off:X}{text}")


if __name__ == "__main__":
    main()
