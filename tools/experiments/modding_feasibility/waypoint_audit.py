"""E-464 (D-231): offline audit of actor-owned waypoint graphs with the decoder of tools/r3hd_mods.py
(read_script_index -> graphs). Counts only; nothing game-derived is printed.

usage: python -I waypoint_audit.py GAMEDATAbin_PARENT

Reports, over every level file: graph designer variables (type 20) of actor instances, why some graphs cannot be
edited, waypoints and why some cannot move, waypoint radius / flags values, and a round trip of every editable
waypoint of intro_10 through compile_waypoint_positions (own position -> the file's bytes).
"""
import collections
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # tools/
import r3hd_mods as rm  # noqa: E402

game = Path(sys.argv[1])
g = game / "GAMEDATAbin"
levels = sorted(d.name for d in g.iterdir() if (d / f"{d.name}.lvl").is_file())
c, gwhy, wwhy, flags = (collections.Counter() for _ in range(4))
graphs_seen = collections.Counter()
for L in levels:
    ix = rm.read_script_index(game, L)
    d = ix["data"]
    for (key, n, var), e in ix["graphs"].items():
        c["graph_variables"] += 1
        graphs_seen[(L, e["graph"])] += 1
        gwhy[e["safe"] or "editable"] += 1
        if e["safe"]:
            continue
        for i, (nd, w) in enumerate(e["nodes"]):
            c["waypoints"] += 1
            wwhy[e["wsafe"].get(i, "editable")] += 1
            if i not in e["wsafe"]:
                flags[struct.unpack_from(">I", d, w + 16)[0]] += 1
print("graph variables:", dict(c), "distinct graphs:", len(graphs_seen),
      "graphs named by more than one variable:", sum(1 for v in graphs_seen.values() if v > 1))
print("graph states:", dict(gwhy))
print("waypoint states:", dict(wwhy))
print("flags words of editable waypoints:", dict(flags.most_common(6)))
ix = rm.read_script_index(game, "intro_10")
paths = {"game": game}
n = ok = 0
for (key, inst, var) in ix["graphs"]:
    for row in rm.waypoint_rows(ix, key):
        if row["instance"] != inst or row["variable"] != var:
            continue
        for nd in row.get("nodes", ()):
            if "position" not in nd:
                continue
            o = {"type": "waypoint-position", "level": "intro_10", "model": key, "instance": inst, "variable": var,
                 "node": nd["node"], "waypoint_sha256": nd["waypoint_sha256"], "position": nd["position"]}
            for p, off, data, _ in rm.compile_waypoint_positions([o], paths):
                n += 1
                ok += ix["data"][off:off + len(data)] == data
print(f"intro_10 round trip: {ok}/{n} ranges equal the file's bytes")
