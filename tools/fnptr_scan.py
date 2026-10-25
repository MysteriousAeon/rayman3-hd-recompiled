#!/usr/bin/env python3
"""Scan non-code sections for big-endian pointers into code and compare with
ReXGlue's function table. Classifies untranslated code words. Usage:
  fnptr_scan.py <image> <pe_analysis.json> <rex init.cpp> <rex_coverage.json> <generated_dir> <out.json>"""
import sys, json, struct, re, glob, bisect, collections
imgp, pep, initp, covp, G, outp = sys.argv[1:7]
img = open(imgp, "rb").read(); R = json.load(open(pep)); base = int(R["image_base"], 16)
starts = sorted(int(m, 16) for m in re.findall(r"\{ 0x([0-9A-F]{8}), ", open(initp).read())); S = set(starts)
code = [(int(s["va"], 16), int(s["va"], 16) + int(s["vsize"], 16)) for s in R["sections"] if s["code"]]
incode = lambda a: any(lo <= a < hi for lo, hi in code)
# rebuild claimed set exactly as rex_coverage.py does
claimed = set(); named = {m.group(2): int(m.group(1), 16) for m in re.finditer(r"\{ 0x([0-9A-F]{8}), (\w+) \}", open(initp).read())}
rn = re.compile(r"^DEFINE_REX_FUNC\((\w+)\)"); rl = re.compile(r"^\s*loc_([0-9A-F]{8}):"); ri = re.compile(r"^\s+// [a-z.]")
for f in glob.glob(G + "/r3hd_recomp.*.cpp"):
    pc = None
    for l in open(f, encoding="utf-8", errors="replace"):
        m = rn.match(l)
        if m: pc = named.get(m.group(1)); continue
        m = rl.match(l)
        if m: pc = int(m.group(1), 16); continue
        if pc is not None and ri.match(l): claimed.add(pc); pc += 4
for e in R["imports"]:
    if e["thunk"]: claimed.update(range(int(e["thunk"], 16), int(e["thunk"], 16) + 16, 4))
ptrs = collections.Counter()
for s in R["sections"]:
    if s["code"] or s["name"] in (".pdata", ".reloc", ".XBLD"): continue
    va, n = int(s["va"], 16), min(int(s["vsize"], 16), int(s["rawsize"], 16)) // 4
    if va % 4: continue
    for i, w in enumerate(struct.unpack_from(f">{n}I", img, va - base)):
        if w & 3 == 0 and incode(w) and struct.unpack_from(">I", img, w - base)[0] != 0:
            ptrs[w] += 1
P = set(ptrs)
not_start = sorted(P - S)
not_start_unclaimed = [p for p in not_start if p not in claimed]
not_start_claimed = [p for p in not_start if p in claimed]
# classify unclaimed nonzero words
un = []
for lo, hi in code:
    for i, w in enumerate(struct.unpack_from(f">{(hi - lo) // 4}I", img, lo - base)):
        if w and lo + i * 4 not in claimed: un.append((lo + i * 4, w))
k = collections.Counter()
for a, w in un:
    if incode(w) and w & 3 == 0: k["word is a code pointer (in-text jump table data)"] += 1
    else: k["instruction-like"] += 1
out = {"data_pointers_into_code_distinct": len(P), "of_which_rexglue_function_starts": len(P & S),
       "not_function_start_but_translated_midfunction": len(not_start_claimed),
       "not_function_start_and_untranslated": len(not_start_unclaimed),
       "untranslated_word_classes": dict(k), "untranslated_targets": [hex(p) for p in not_start_unclaimed],
       "midfunction_targets_sample": [hex(p) for p in not_start_claimed[:50]]}
json.dump(out, open(outp, "w"), indent=1)
print(json.dumps({x: y for x, y in out.items() if not isinstance(y, list)}, indent=1)); print(out["untranslated_targets"][:12])
