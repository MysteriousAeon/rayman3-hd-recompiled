"""D-223 / E-455: offline audit of the script-constant decoder in tools/r3hd_mods.py (read_script_index) on the
person's extracted data, optionally against earlier read-only live script dumps (m14 scan_v2, format 2). Counts
only; nothing game-derived is printed or written.

usage: python -I script_const_audit.py GAMEDATAbin_PARENT [LIVE_SCAN_DIR]
  GAMEDATAbin_PARENT  the folder holding GAMEDATAbin (e.g. private/extracted/5841123F)
  LIVE_SCAN_DIR       e.g. private/work/m14/scan_v2 (<level>/scripts/*.txt)

Checks: (1) per node type, whether its parameter word is ever / always a .ptr slot; (2) behaviour names unique
per file, node arrays not shared; (3) every int / real node of the file equals the live dump, and every
difference is confined to types the decoder never edits; (4) a compile of every int / real node of one level
(the original value written back) yields ranges equal to the file's own bytes.
"""
import collections
import glob
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # tools/
import r3hd_mods as rm  # noqa: E402

game = Path(sys.argv[1])
live = Path(sys.argv[2]) if len(sys.argv) > 2 else None
g = game / "GAMEDATAbin"
levels = ["fix"] + sorted(d.name for d in g.iterdir() if (d / f"{d.name}.lvl").is_file())
kinds = collections.Counter()
in_ptr = collections.Counter()
c = collections.Counter()
index = {}
for L in levels:
    ix = rm.read_script_index(game, L)
    index[L] = ix
    owners = collections.Counter()
    for nm, scripts in ix["behaviours"].items():
        if scripts is None:
            c["names_not_unique"] += 1
            continue
        c["behaviours"] += 1
        for na, nodes in scripts:
            if nodes is None:
                c["unreadable_scripts"] += 1
                continue
            owners[na] += 1
            c["scripts"] += 1
            for k, (p, ind, kind) in enumerate(nodes):
                kinds[kind] += 1
                in_ptr[kind] += (na + 8 * k) in ix["slots"]
    c["shared_node_arrays"] += sum(1 for v in owners.values() if v > 1)
c["files"] = len(levels)
print("decoder:", dict(c))
mixed = sorted(f"{k:02X}" for k in kinds if 0 < in_ptr[k] < kinds[k])
print("node types:", len(kinds), "always relocated:", sorted(f"{k:02X}" for k in kinds if in_ptr[k] == kinds[k]),
      "mixed:", mixed)
print("int (0C):", kinds[0x0C], "relocated", in_ptr[0x0C], "| real (0D):", kinds[0x0D], "relocated", in_ptr[0x0D])

if live:
    cmp = collections.Counter()
    diff_kinds = collections.Counter()
    for dump in sorted(glob.glob(str(live / "*" / "scripts" / "*.txt"))):
        L = Path(dump).parent.parent.name
        if L not in index:
            continue
        beh, cur, dumped = None, None, collections.defaultdict(list)
        for line in open(dump, encoding="utf-8", errors="replace"):
            if line.startswith(("## normal ", "## reflex ")):
                beh, cur = line.split(" ", 3)[3].rstrip("\n"), None
            elif line.startswith("## macro"):
                beh = None
            elif line.startswith("# script") and beh:
                cur = []
                dumped[beh].append(cur)
            else:
                m = re.match(r"^( *)k([0-9A-F]{2}):([0-9A-F]{8})", line)
                if m and cur is not None and beh:
                    cur.append((int(m.group(3), 16), len(m.group(1)) // 2, int(m.group(2), 16)))
        for nm, lscripts in dumped.items():
            fscripts = index[L]["behaviours"].get(nm) or index["fix"]["behaviours"].get(nm)
            if not fscripts:
                cmp["live_behaviour_not_in_files"] += 1
                continue
            if len(fscripts) != len(lscripts) or any(f[1] is None or len(f[1]) != len(s)
                                                     for f, s in zip(fscripts, lscripts)):
                cmp["shape_differs"] += 1
                continue
            cmp["behaviours_compared"] += 1
            for (na, fn), ln in zip(fscripts, lscripts):
                for (fp, fi, fk), (lp, li, lk) in zip(fn, ln):
                    if (fi, fk) != (li, lk):
                        cmp["node_shape_differs"] += 1
                    elif fk in rm.SCRIPT_KINDS.values():
                        cmp["const_equal" if fp == lp else "const_differs"] += 1
                    elif fp != lp:
                        diff_kinds[f"{fk:02X}"] += 1
    print("live:", dict(cmp))
    print("non-constant parameters that differ live, by type:", dict(diff_kinds))

# (4) round trip on the first level with constants: every int / real node rewritten with its own value
L = next(x for x in levels if x != "fix")
ix = index[L]
ovs = []
for nm, scripts in ix["behaviours"].items():
    for j, (na, nodes) in enumerate(scripts or ()):
        if nodes is None:
            continue
        h = rm.script_hash(ix, na, nodes)
        for row in rm.script_constant_rows(ix, nodes):
            ovs.append({"type": "script-constant", "level": L, "behavior": nm, "script": j, "node": row["node"],
                        "script_sha256": h, "kind": row["kind"], "value": row["value"]})
for o in ovs:
    rm.parse_script_constant(o, "audit")
ranges = rm.compile_script_constants(ovs, {"game": game}, {L: ix})
same = sum(1 for p, off, data, _ in ranges if ix["data"][off:off + 4] == data)
print(f"round trip {L}: {len(ranges)} constants compiled, {same} equal to the file's own bytes")
