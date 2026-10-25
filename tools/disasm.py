#!/usr/bin/env python3
"""Disassemble a range of the decrypted image: disasm.py <image> <va_hex> [count]. Debug aid only."""
import sys, struct
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
img = open(sys.argv[1], "rb").read(); base = 0x82000000
va = int(sys.argv[2], 16); n = int(sys.argv[3]) if len(sys.argv) > 3 else 16
md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
for i in range(n):
    a = va + i * 4; w = img[a - base:a - base + 4]
    ins = next(md.disasm(w, a), None)
    print(f"{a:08x}  {w.hex()}  " + (f"{ins.mnemonic} {ins.op_str}" if ins else "<undecoded>"))
