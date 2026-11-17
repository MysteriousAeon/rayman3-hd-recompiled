"""E-459 (D-226): offline audit of script macros with the decoder of tools/r3hd_mods.py (read_script_index ->
models, macro_refs). Counts only; nothing game-derived is printed.

usage: python -I macro_audit.py GAMEDATAbin_PARENT [LIVE_SCAN_DIR]

Reports: models and macros per file set; why macros are not editable; references to macro entries (list header,
0x29 nodes of the own model, of another model, other data, the transit file); node types in editable macros and
whether any is ever a relocated word; node arrays shared with other macros or behaviour scripts; live equality of
macro int / real constants and node shapes against the m14 scan_v2 dumps (which print each macro's first script);
a round trip of every editable constant of one level through compile_macro_constants.
"""
import collections
import glob
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # tools/
import r3hd_mods as rm  # noqa: E402

game = Path(sys.argv[1])
live = Path(sys.argv[2]) if len(sys.argv) > 2 else None
g = game / "GAMEDATAbin"
levels = ["fix"] + sorted(d.name for d in g.iterdir() if (d / f"{d.name}.lvl").is_file())
c, refs, kinds, reloc = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
index = {}
for L in levels:
    ix = rm.read_script_index(game, L)
    index[L] = ix
    refs.update(ix["macro_refs"])
    behaviour_arrays = {na for s in ix["behaviours"].values() for na, _ in s or () if na is not None}
    arrays = collections.Counter()
    for key, macros in ix["models"].items():
        if macros is None:
            c["models_not_unique"] += 1
            continue
        c["models"] += 1
        for mac in macros:
            c["macros"] += 1
            c["editable" if not mac["safe"] else "refused: " + mac["safe"]] += 1
            if mac["safe"]:
                continue
            arrays[mac["nodes_at"]] += 1
            c["array_is_a_behaviour_script"] += mac["nodes_at"] in behaviour_arrays
            for k, (p, ind, kind) in enumerate(mac["nodes"]):
                kinds[kind] += 1
                reloc[kind] += (mac["nodes_at"] + 8 * k) in ix["slots"]
    c["arrays_shared_between_macros"] += sum(1 for v in arrays.values() if v > 1)
print("macros:", dict(c))
print("references to macro entries:", dict(refs))
print("node types:", len(kinds), "always relocated:", sorted(f"{k:02X}" for k in kinds if reloc[k] == kinds[k]),
      "mixed:", sorted(f"{k:02X}" for k in kinds if 0 < reloc[k] < kinds[k]))
print("int (0C):", kinds[0x0C], "relocated", reloc[0x0C], "| real (0D):", kinds[0x0D], "relocated", reloc[0x0D],
      "| 1F (load-rewritten):", kinds[0x1F])

if live:
    cmp = collections.Counter()
    for dump in sorted(glob.glob(str(live / "*" / "scripts" / "*.txt"))):
        L = Path(dump).parent.parent.name
        if L not in index:
            continue
        first, macros, cur = None, [], None
        for line in open(dump, encoding="utf-8", errors="replace"):
            if line.startswith("## normal ") and first is None:
                first = line.split(" ", 3)[3].rstrip("\n")
            if line.startswith("## "):
                cur = [] if line.startswith("## macro") else None
                if cur is not None:
                    macros.append(cur)
            else:
                m = re.match(r"^( *)k([0-9A-F]{2}):([0-9A-F]{8})", line)
                if m and cur is not None:
                    cur.append((int(m.group(3), 16), len(m.group(1)) // 2, int(m.group(2), 16)))
        fm = index[L]["models"].get(first) if first else None
        fm = fm if fm is not None else (index["fix"]["models"].get(first) if first else None)
        if not fm:
            cmp["actor_model_not_found"] += 1
            continue
        if len(fm) != len(macros):
            cmp["macro_count_differs"] += 1
            continue
        cmp["actors"] += 1
        for f, lv in zip(fm, macros):
            if f["safe"]:
                cmp["refused_macro_live_nodes" if lv else "refused_macro_live_empty"] += 1
                continue
            if len(f["nodes"]) != len(lv) or any((a[1], a[2]) != (b[1], b[2]) for a, b in zip(f["nodes"], lv)):
                cmp["shape_differs"] += 1
                continue
            cmp["macros_compared"] += 1
            for (fp, _, fk), (lp, _, _) in zip(f["nodes"], lv):
                if fk in rm.SCRIPT_KINDS.values():
                    cmp["const_equal" if fp == lp else "const_differs"] += 1
    print("live:", dict(cmp))

L = "intro_10"
ix = index[L]
ovs = []
for key, macros in ix["models"].items():
    for i, mac in enumerate(macros or ()):
        if mac["safe"]:
            continue
        h = rm.script_hash(ix, mac["nodes_at"], mac["nodes"])
        for row in rm.script_constant_rows(ix, mac["nodes"]):
            ovs.append({"type": "macro-constant", "level": L, "model": key, "macro": i, "node": row["node"],
                        "script_sha256": h, "kind": row["kind"], "value": row["value"]})
for o in ovs:
    rm.parse_macro_constant(o, "audit")
ranges = rm.compile_macro_constants(ovs, {"game": game}, {L: ix})
print(f"round trip {L}: {len(ranges)} macro constants, {sum(ix['data'][o:o + 4] == d for _, o, d, _ in ranges)} equal "
      "to the file's own bytes")
