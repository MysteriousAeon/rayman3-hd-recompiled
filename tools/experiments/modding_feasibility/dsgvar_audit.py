"""E-460 (D-227): offline audit of designer-variable initial values with the decoder of tools/r3hd_mods.py
(read_script_index -> defaults). Counts only; nothing game-derived is printed.

usage: python -I dsgvar_audit.py GAMEDATAbin_PARENT

Reports, over fix.lvl and every level file: AI models with designer variables, DsgMem instances and why some cannot
be changed; variable types and how many are relocated words in the instance buffers; whether the initial and
current buffers hold the same bytes; how instance buffers compare with the model's default buffer; editable
variables by kind; and a round trip of every editable variable of one level through compile_designer_defaults.
"""
import collections
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # tools/
import r3hd_mods as rm  # noqa: E402

game = Path(sys.argv[1])
g = game / "GAMEDATAbin"
levels = ["fix"] + sorted(d.name for d in g.iterdir() if (d / f"{d.name}.lvl").is_file())
c, types, reloc, kinds, why = (collections.Counter() for _ in range(5))
for L in levels:
    ix = rm.read_script_index(game, L)
    d, slots = ix["data"], ix["slots"]
    for key, e in ix["defaults"].items():
        if e is None:
            c["models_not_unique"] += 1
            continue
        if not e["vars"]:
            c["models_without_designer_variables"] += 1
            continue
        c["models_with_designer_variables"] += 1
        c[f"instances_per_model={min(len(e['instances']), 3)}{'+' if len(e['instances']) >= 3 else ''}"] += 1
        for inst in e["instances"]:
            c["instances"] += 1
            why[inst["safe"] or "editable"] += 1
            if inst["initial"] is None or inst["current"] is None or inst["safe"].startswith("the instance's initial or"):
                continue
            n = e["length"]
            a, b = inst["initial"], inst["current"]
            words = [k for k in range(0, n, 4) if a + k in slots]
            c["initial_equals_current_except_relocated"] += all(
                d[a + k] == d[b + k] for k in range(n) if (a + (k & ~3)) not in slots)
            c["relocated_word_positions_equal"] += words == [k for k in range(0, n, 4) if b + k in slots]
            for var, (off, t) in enumerate(e["vars"]):
                types[t] += 1
                size = rm.DSG_KINDS.get(t, ("", 4))[1]
                reloc[t] += any(w in slots for w in range(a + off - 3, a + off + size))
                if not inst["safe"]:
                    try:
                        kind, size, o = rm.designer_field(ix, e, inst, var)
                        kinds[kind] += 1
                    except ValueError as x:
                        kinds["refused: " + str(x).split(" ", 2)[-1][:60]] += 1
print("instances / models:", dict(c))
print("instance states:", dict(why))
print("types (instance variables):", {t: (types[t], reloc[t]) for t in sorted(types)}, "(count, relocated)")
print("editable variables by kind / refusals:", dict(kinds))

# round trip: every editable variable of intro_10 compiled with its own value equals the file's bytes
ix = rm.read_script_index(game, "intro_10")
paths = {"game": game}
n = ok = 0
for key, e in ix["defaults"].items():
    for i, row in enumerate(rm.designer_rows(ix, e) if e else ()):
        for v in row.get("variables", ()):
            o = {"type": "designer-default", "level": "intro_10", "model": key, "instance": i,
                 "variable": v["variable"], "initial_sha256": row["initial_sha256"], "kind": v["kind"],
                 "value": v["value"]}
            for p, off, data, _ in rm.compile_designer_defaults([o], paths):
                n += 1
                ok += ix["data"][off:off + len(data)] == data
print(f"intro_10 round trip: {ok}/{n} ranges equal the file's bytes")
