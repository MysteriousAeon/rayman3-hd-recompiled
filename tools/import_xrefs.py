#!/usr/bin/env python3
"""Count direct call references (bl/b) to each import thunk and, transitively, to
single-thunk wrapper functions. Usage: import_xrefs.py <image> <pe_analysis.json> [--detail NAME ...]"""
import sys, json, struct, bisect, collections
img = open(sys.argv[1], "rb").read(); R = json.load(open(sys.argv[2])); base = int(R["image_base"], 16)
detail = sys.argv[sys.argv.index("--detail") + 1:] if "--detail" in sys.argv else []
secs = [(int(s["va"], 16), int(s["vsize"], 16)) for s in R["sections"] if s["code"]]
thunks = {int(e["thunk"], 16): e for e in R["imports"] if e["thunk"]}
refs = collections.defaultdict(list)
for va, sz in secs:
    ws = struct.unpack_from(f">{sz // 4}I", img, va - base)
    for i, w in enumerate(ws):
        if w >> 26 == 18 and not w & 2:
            off = w & 0x03FFFFFC
            if off & 0x02000000: off -= 0x04000000
            t = va + i * 4 + off
            if t in thunks: refs[t].append(va + i * 4)
rows = []
for t, e in sorted(thunks.items(), key=lambda kv: (kv[1]["lib"], kv[1]["name"] or "")):
    rows.append((e["lib"], e["name"] or f"ord_{e['ordinal']}", e["ordinal"], len(refs[t])))
out = {"imports": [{"lib": l, "name": n, "ordinal": o, "direct_refs": c} for l, n, o, c in rows]}
unref = [n for l, n, o, c in rows if c == 0]
print(f"function imports: {len(rows)}; with zero direct bl/b references: {len(unref)}")
print("UNREFERENCED:", " ".join(unref))
print("REFERENCED:", " ".join(f"{n}:{c}" for l, n, o, c in rows if c))
for name in detail:
    for t, e in thunks.items():
        if e["name"] == name:
            print(f"\n{name} thunk={t:#x} callers:", " ".join(hex(x) for x in refs[t][:40]))
json.dump(out, open(sys.argv[2].replace("pe_analysis", "import_xrefs"), "w"), indent=1)
