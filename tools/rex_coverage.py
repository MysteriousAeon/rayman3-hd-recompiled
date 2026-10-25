#!/usr/bin/env python3
"""Reconstruct which guest addresses ReXGlue translated, from generated sources
(function names + loc_ labels + per-instruction comments), and report code words
in executable sections that were not translated. Usage:
  rex_coverage.py <generated_dir> <image> <pe_analysis.json> <out.json>"""
import sys, glob, re, json, struct, collections
G, imgp, pep, outp = sys.argv[1:5]
img = open(imgp, "rb").read(); R = json.load(open(pep)); base = int(R["image_base"], 16)
claimed = set()
rf = re.compile(r"^DEFINE_REX_FUNC\((?:sub_|__\w*?_)?([0-9A-F]{8})?"); rl = re.compile(r"^\s*loc_([0-9A-F]{8}):")
ri = re.compile(r"^\s+// [a-z.]"); rn = re.compile(r"^DEFINE_REX_FUNC\((\w+)\)")
named = {}
for m in re.finditer(r"\{ 0x([0-9A-F]{8}), (\w+) \}", open(G + "/r3hd_init.cpp").read()):
    named[m.group(2)] = int(m.group(1), 16)
unk = 0
for f in glob.glob(G + "/r3hd_recomp.*.cpp"):
    pc = None
    for l in open(f, encoding="utf-8", errors="replace"):
        m = rn.match(l)
        if m:
            pc = named.get(m.group(1)); unk += pc is None; continue
        m = rl.match(l)
        if m:
            pc = int(m.group(1), 16); continue
        if pc is not None and ri.match(l):
            claimed.add(pc); pc += 4
thunks = {int(e["thunk"], 16) for e in R["imports"] if e["thunk"]}
for t in thunks: claimed.update(range(t, t + 16, 4))
un, runs = [], []
for s in R["sections"]:
    if not s["code"]: continue
    va, sz = int(s["va"], 16), int(s["vsize"], 16)
    ws = struct.unpack_from(f">{sz // 4}I", img, va - base)
    for i, w in enumerate(ws):
        a = va + i * 4
        if w and a not in claimed:
            un.append(a)
for a in un:
    if runs and a == runs[-1][1] + 4: runs[-1][1] = a
    else: runs.append([a, a])
kinds = collections.Counter()
for a in un:
    w = struct.unpack_from(">I", img, a - base)[0]
    kinds["bcctr" if (w >> 26 == 19 and (w >> 1) & 0x3FF == 528) else "op0" if w >> 26 == 0 else "other"] += 1
runs.sort(key=lambda r: r[0] - r[1])
out = {"claimed_words": len(claimed), "functions_without_address": unk, "unclaimed_nonzero_words": len(un),
       "unclaimed_runs": len(runs), "unclaimed_kinds": dict(kinds),
       "largest_runs": [{"start": hex(a), "end": hex(b + 4), "words": (b - a) // 4 + 1} for a, b in runs[:40]]}
json.dump(out, open(outp, "w"), indent=1)
print(json.dumps({k: v for k, v in out.items() if k != "largest_runs"})); print(out["largest_runs"][:14])
