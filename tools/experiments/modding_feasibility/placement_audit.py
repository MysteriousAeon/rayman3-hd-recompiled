"""E-461 (D-228): offline audit of actor placement with the decoder of tools/r3hd_mods.py (read_script_index ->
placements). Counts only; nothing game-derived is printed.

usage: python -I placement_audit.py GAMEDATAbin_PARENT [LIVE_SCAN_DIR]

Reports, over every level file (fix is refused by the override and only counted): actors found through an AI model,
editable actors and why the others cannot move, matrix types; with LIVE_SCAN_DIR (the m14 scan_v2 dumps), how many
scanned actors stand exactly at a file translation of their model, by matrix type; and a round trip of every
editable actor of intro_10 through compile_actor_positions (own position -> the file's bytes, matrix and snapshot).
"""
import collections
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # tools/
import r3hd_mods as rm  # noqa: E402

game = Path(sys.argv[1])
live = Path(sys.argv[2]) if len(sys.argv) > 2 else None
g = game / "GAMEDATAbin"
levels = sorted(d.name for d in g.iterdir() if (d / f"{d.name}.lvl").is_file())
c, why, types, eq = (collections.Counter() for _ in range(4))
for L in levels:
    ix = rm.read_script_index(game, L)
    d = ix["data"]
    pos = []
    for key, insts in ix["placements"].items():
        if insts is None:
            c["models_not_unique"] += 1
            continue
        for inst in insts:
            c["actors"] += 1
            why[inst["safe"] or ("refused (D-229): the model's scripts set the position"
                                 if rm.model_sets_position(ix, key) else "editable")] += 1
            m = inst["matrix"]
            if m is not None and m + rm.PLACEMENT_SIZE <= len(d):
                t = struct.unpack_from(">I", d, m)[0]
                types[t] += 1
                pos.append((key.split("\\")[1], t, struct.unpack_from(">3f", d, m + 0x34)))
    f = live / L / "actors.json" if live else None
    if f and f.is_file():
        for a in json.loads(f.read_text(encoding="utf-8"))["actors"]:
            cands = [(math.dist(p, a["position"]), t) for nm, t, p in pos if nm == a["model"]]
            if cands:
                dist, t = min(cands)
                eq[(t, "equal" if dist < 0.01 else "differs")] += 1
print("actors:", dict(c))
print("states:", dict(why))
print("matrix types:", dict(sorted(types.items())))
if live:
    print("scanned actors at a file translation of their model (type, equal):", dict(sorted(eq.items())))
ix = rm.read_script_index(game, "intro_10")
paths = {"game": game}
n = ok = 0
for key, insts in ix["placements"].items():
    for row in rm.placement_rows(ix, insts or [], key):
        if "position" not in row:
            continue
        o = {"type": "actor-position", "level": "intro_10", "model": key, "instance": row["instance"],
             "matrix_sha256": row["matrix_sha256"], "position": row["position"]}
        for p, off, data, _ in rm.compile_actor_positions([o], paths):
            n += 1
            ok += ix["data"][off:off + len(data)] == data
print(f"intro_10 round trip: {ok}/{n} ranges equal the file's bytes")
