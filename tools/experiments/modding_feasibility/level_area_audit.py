#!/usr/bin/env python3
"""E-465 (D-232): offline check of the level-area layout the guest loader 827CDA58 implies. Read-only, private data.

usage: python -I level_area_audit.py <GAMEDATAbin directory>

Loader facts (static, generated code): a `.lvl` = u32 m, then the area (file length - 4 bytes, allocated from engine
memory block 8, 24 MiB, created once at start-up). Its `.ptr` = u32 n, n x {u32 file id, u32 slot offset in this
area}, then m x {u32 slot offset, u32 slot file, u32 target offset, u32 target file}; ids 0 fix, 1 level, 2 transit.
Checks: .ptr length == 4 + 8 n + 16 m for every pair; every slot and target lies inside its file's area; reports
the block-8 budget of each level (fix + transit + level areas + its .ptr, which is a temporary block-8 buffer).
"""
import struct
import sys
from pathlib import Path

BLOCK8 = 384 << 16  # 82100550: lis r3,384 ; bl 821894D8 (create block 8)


def area(p):
    return p.stat().st_size - 4 if p.exists() else None


def main(root):
    fix_area = area(root / "fix.lvl")
    pairs = ok = 0
    no_ptr = []
    rows = []
    for lvl in sorted(p for p in root.rglob("*") if p.suffix.lower() == ".lvl"):
        ptr = lvl.with_suffix(".ptr")
        if not ptr.exists():
            no_ptr.append(str(lvl.relative_to(root)))
            continue
        L, P = lvl.read_bytes(), ptr.read_bytes()
        m = struct.unpack_from(">I", L, 0)[0]
        n = struct.unpack_from(">I", P, 0)[0]
        own = len(L) - 4
        is_fix = lvl.name.lower() == "fix.lvl"
        is_transit = lvl.name.lower() == "transit.lvl"
        transit = None if is_fix else area(lvl.parent / "transit.lvl")
        level = None if (is_fix or is_transit) else own
        if is_transit:
            level = area(lvl.parent / (lvl.parent.name + ".lvl"))
        limits = {0: fix_area, 1: level, 2: transit}
        good = len(P) == 4 + 8 * n + 16 * m
        for i in range(n):
            f, off = struct.unpack_from(">iI", P, 4 + 8 * i)
            good &= off + 4 <= own and f in limits
        for j in range(m):
            oa, fa, ob, fb = struct.unpack_from(">IIII", P, 4 + 8 * n + 16 * j)
            la, lb = limits.get(fa), limits.get(fb)
            good &= la is not None and lb is not None and oa + 4 <= la and ob + 4 <= lb
        pairs += 1
        ok += good
        if not good:
            print("MISMATCH", lvl.relative_to(root))
        if not (is_fix or is_transit):
            budget = fix_area + (transit or 0) + own + len(P)
            rows.append((budget, lvl.parent.name, own, transit or 0, len(P)))
    rows.sort()
    print(f"pairs {pairs} consistent {ok}; .lvl without .ptr: {len(no_ptr)} ({', '.join(no_ptr)})")
    print(f"block 8 = {BLOCK8} bytes; fix area {fix_area}")
    for budget, name, own, tr, pl in sorted(set(rows[-3:] + [r for r in rows if r[1].lower() == "intro_10"])):
        print(f"  {name}: level area {own}, transit area {tr}, .ptr {pl}; fix+transit+level+ptr {budget}; "
              f"upper bound left in block 8 {BLOCK8 - budget}")
    return 0 if ok == pairs else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
