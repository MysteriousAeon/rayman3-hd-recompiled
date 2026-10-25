#!/usr/bin/env python3
"""Static cross-reference aid over the private decrypted image (debug aid; output is game-derived).

    m8_xref.py callers <va_hex>          direct bl/b sites targeting an address, with their .pdata owner
    m8_xref.py func <va_hex>             disassemble the .pdata function containing an address
    m8_xref.py refs <va_hex>             lis/addi|ori|lwz|stw... sites that materialise an address
    m8_xref.py imports <substring>       import thunks and their local wrapper callers

Function bounds are .pdata begin addresses (end = next begin), so non-.pdata leaves are attributed
to the preceding entry. Keep listings under private/; reports carry addresses and conclusions only.
"""
import bisect, json, struct, sys
from pathlib import Path
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN

ROOT = Path(__file__).resolve().parents[1]
IMG = (ROOT / 'private/work/default_image.bin').read_bytes()
PE = json.loads((ROOT / 'private/work/pe_analysis.json').read_text())
BASE = 0x82000000
CODE = [(int(s['va'], 16), int(s['va'], 16) + int(s['vsize'], 16)) for s in PE['sections'] if s['code']]
PDATA = next(s for s in PE['sections'] if s['name'] == '.pdata')
IMPORTS = {int(i['thunk'], 16): i['name'] for i in PE['imports'] if i.get('thunk')}
md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)


def word(a):
    return struct.unpack_from('>I', IMG, a - BASE)[0]


def starts():
    va, size = int(PDATA['va'], 16), int(PDATA['vsize'], 16)
    out = [word(va + i) for i in range(0, size, 8)]
    return sorted(a for a in out if a)


STARTS = starts()


def owner(a):
    i = bisect.bisect_right(STARTS, a) - 1
    return (STARTS[i], STARTS[i + 1] if i + 1 < len(STARTS) else a + 4) if i >= 0 else (a, a + 4)


def branches():
    for lo, hi in CODE:
        for a in range(lo, hi, 4):
            w = word(a)
            if w >> 26 == 18 and not w & 2:
                d = w & 0x03FFFFFC
                if d & 0x02000000: d -= 0x04000000
                yield a, (a + d) & 0xFFFFFFFF, bool(w & 1)


def callers(target):
    return [(a, link) for a, t, link in branches() if t == target]


def cstring(a):
    if not (BASE <= a < BASE + len(IMG)): return None
    raw = IMG[a - BASE:a - BASE + 64].split(b'\0')[0]
    return raw.decode('ascii') if len(raw) >= 4 and all(32 <= c < 127 for c in raw) else None


def listing(lo, hi):
    high = {}
    for a in range(lo, hi, 4):
        w = IMG[a - BASE:a - BASE + 4]
        ins = next(md.disasm(w, a), None)
        text = f'{ins.mnemonic} {ins.op_str}' if ins else '<undecoded>'
        note = ''
        v = word(a)
        if v >> 26 == 18 and not v & 2:
            d = v & 0x03FFFFFC
            if d & 0x02000000: d -= 0x04000000
            t = (a + d) & 0xFFFFFFFF
            note = f'  ; -> {t:08X} {IMPORTS.get(t, "")}'
        elif v >> 26 == 15 and (v >> 16) & 31 == 0:           # lis rD, imm
            high[(v >> 21) & 31] = (v & 0xFFFF) << 16
        elif v >> 26 in (14, 24, 32, 36, 34, 38, 40, 44, 48, 50) and ((v >> 16) & 31) in high:
            imm = v & 0xFFFF
            full = (high[(v >> 16) & 31] + (imm - 0x10000 if imm & 0x8000 and v >> 26 != 24 else imm)) & 0xFFFFFFFF
            s = cstring(full)
            note = f'  ; {full:08X}' + (f' "{s}"' if s else '')
        print(f'{a:08X}  {text}{note}')


def refs(target):
    """lis + (addi/ori/load/store) pairs within 8 instructions that form the target address."""
    hits = []
    for lo, hi in CODE:
        for a in range(lo, hi, 4):
            v = word(a)
            if v >> 26 != 15 or (v >> 16) & 31: continue
            reg, base_value = (v >> 21) & 31, (v & 0xFFFF) << 16
            if abs(base_value - target) > 0x10000: continue
            for b in range(a + 4, min(a + 36, hi), 4):
                u = word(b)
                if u >> 26 in (14, 24, 32, 36, 34, 38, 40, 44, 48, 50, 52, 54) and (u >> 16) & 31 == reg:
                    imm = u & 0xFFFF
                    full = (base_value + (imm - 0x10000 if imm & 0x8000 and u >> 26 != 24 else imm)) & 0xFFFFFFFF
                    if full == target: hits.append((b, u >> 26))
    return hits


if __name__ == '__main__':
    mode, arg = sys.argv[1], sys.argv[2]
    if mode == 'callers':
        for a, link in callers(int(arg, 16)):
            print(f'{a:08X} {"bl" if link else "b "} in {owner(a)[0]:08X}')
    elif mode == 'func':
        lo, hi = owner(int(arg, 16))
        print(f'; function {lo:08X}..{hi:08X}')
        listing(lo, hi)
    elif mode == 'refs':
        for a, op in refs(int(arg, 16)):
            print(f'{a:08X} op{op} in {owner(a)[0]:08X}')
    elif mode == 'imports':
        for thunk, name in sorted(IMPORTS.items()):
            if arg.lower() not in name.lower(): continue
            sites = callers(thunk)
            print(f'{name} thunk={thunk:08X} ' + ' '.join(f'{a:08X}@{owner(a)[0]:08X}' for a, _ in sites))
