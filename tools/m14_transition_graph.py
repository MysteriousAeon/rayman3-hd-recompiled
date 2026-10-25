#!/usr/bin/env python3
"""Script-derived level-transition table from the private scans of tools/m14_script_scan.py (M14).

    python tools/m14_transition_graph.py [--json reports/milestone14/transitions.json] [--md FILE]

Everything here is a static reading of what was decoded from live isolated runs: which actors hold a level name
in a designer variable of type Text, and which script calls of the change-map procedures name a level. Nothing
in the output was executed as a transition. Evidence classes of the rows:

  actor     an actor instance in the level whose Text variable resolves to a level name (the change-map actor's
            variable 0 is what its script passes to the change-map procedure, RE_NOTES "M13")
  script    a change-map procedure call whose argument is a literal string or a text constant
  variable  a change-map procedure call whose argument is a designer variable or an expression; the destination
            is whatever that variable holds at run time (not known statically unless the actor row gives it)
  textref   a text constant naming a level elsewhere in a script (for example stored into a variable)

Rows that occur with the same model, behaviour and destination in at least half of the scanned levels are
reported once as "shared" (global actor, player model): they are not level-specific edges.

The output holds level, model and behaviour names, positions and counts: metadata only. Script text stays private.
"""
import argparse
import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "private" / "work" / "m14" / "scan"
GAMEDATA = ROOT / "private" / "extracted" / "5841123F" / "GAMEDATAbin"
NODE = re.compile(r"^( *)([A-Za-z0-9_]+):(.*)$")
CHANGE = re.compile(r"ChangeMap|ChangeLevel", re.IGNORECASE)


def level_names() -> list:
    return sorted(p.name.lower() for p in GAMEDATA.iterdir() if p.is_dir() and (p / f"{p.name}.lvl").is_file())


def short(header: str) -> str:
    return header.rsplit(":", 1)[-1].strip()


def model_of(path: Path) -> str:
    return path.stem.rsplit("_", 1)[0]


def analyse(level: str, known: set, misc: dict) -> dict:
    base = SCAN / level
    actors = json.loads((base / "actors.json").read_text(encoding="utf-8"))["actors"]
    by_perso = {a["perso"]: a for a in actors}
    player = next((a for a in actors if a["model"] == "YLT_RaymanModel"), None)
    rows = []
    for a in actors:
        for number, value in a["texts"].items():
            text = (value.get("text") or "").lower()
            if text in known or text.lstrip("*") in known:
                rows.append({"kind": "actor", "model": a["model"], "variable": int(number), "destination": text,
                             "position": a["position"], "behaviour": a["comport"], "perso": a["perso"]})
    for path in sorted((base / "scripts").glob("*.txt")):
        model, perso = model_of(path), path.stem.rsplit("_", 1)[-1]
        behaviour, lines = "", path.read_text(errors="replace").splitlines()
        for index, line in enumerate(lines):
            if line.startswith("## "):
                behaviour = short(line) if "CreateComport" in line else line[3:].split(" ", 1)[0]
                continue
            m = NODE.match(line)
            if not m:
                continue
            indent, kind, value = len(m.group(1)), m.group(2), m.group(3)
            if kind == "TextRef":
                text = misc.get(value.upper().zfill(8), "").lower()
                if text in known:
                    rows.append({"kind": "textref", "model": model, "behaviour": behaviour, "destination": text})
            if kind != "Procedure" or not CHANGE.search(value):
                continue
            args = []
            for follow in lines[index + 1:index + 12]:
                f = NODE.match(follow)
                if not f or len(f.group(1)) <= indent:
                    break
                args.append((f.group(2), f.group(3)))
            destination, how = None, "variable"
            for akind, avalue in args:
                if akind == "String":
                    destination, how = avalue.strip("'\"").lower(), "script"
                    break
                if akind == "TextRef":
                    destination, how = misc.get(avalue.upper().zfill(8), f"text {avalue}").lower(), "script"
                    break
            if destination is None:
                refs = [v for k, v in args if k == "DsgVarRef"]
                own = by_perso.get(perso, {}).get("texts", {})
                held = (own.get(refs[0], {}).get("text") or "").lower() if refs else ""
                destination = held if held else ("variable " + refs[0] if refs else "expression")
            rows.append({"kind": how, "model": model, "behaviour": behaviour, "procedure": value,
                         "destination": destination})
    # who refers to a change-map actor instance (for example to set the custom bit that fires it)
    targets = {r["perso"]: r for r in rows if r["kind"] == "actor"}
    for path in sorted((base / "scripts").glob("*.txt")):
        text = path.read_text(errors="replace")
        for perso, row in targets.items():
            if path.stem.endswith(perso):
                continue
            if f"PersoRef:{perso}" in text or perso.lower() in text.split("## ", 1)[0]:
                row.setdefault("referenced_by", [])
                if model_of(path) not in row["referenced_by"]:
                    row["referenced_by"].append(model_of(path))
    for row in rows:
        row.pop("perso", None)
        if row["kind"] == "actor" and player:
            row["distance_from_isolated_spawn"] = round(sum((p - q) ** 2 for p, q in
                                                             zip(row["position"], player["position"])) ** 0.5, 1)
    return {"level": level, "actors": len(actors), "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    ap.add_argument("--md", type=Path)
    a = ap.parse_args()
    known = set(level_names())
    scanned = sorted(p.name for p in SCAN.iterdir() if (p / "actors.json").is_file())
    misc = {}
    for level in scanned:
        path = SCAN / level / "misc_texts.json"
        if path.is_file():
            misc = json.loads(path.read_text(encoding="utf-8"))
            break
    levels = [analyse(level, known, misc) for level in scanned]

    def key(row):
        return (row["kind"], row["model"], row.get("behaviour"), row.get("procedure"), row["destination"])
    seen = collections.Counter()
    for entry in levels:
        for k in {key(r) for r in entry["rows"] if r["kind"] != "actor"}:
            seen[k] += 1
    shared = {k for k, n in seen.items() if n >= max(2, len(levels) // 2)}
    edges = collections.OrderedDict()
    for entry in levels:
        specific = []
        for row in entry["rows"]:
            if key(row) in shared:
                continue
            if row not in specific:
                specific.append(row)
        entry["rows"] = specific
        for row in specific:
            dest = row["destination"].lstrip("*")
            if dest in known and dest != entry["level"]:
                edges.setdefault((entry["level"], dest), set()).add(row["kind"])
    result = {
        "evidence": "script-derived (decoded from live isolated runs); no row is an executed transition",
        "scanned_levels": len(levels), "level_directories": len(known), "misc_text_entries": len(misc),
        "shared_rows": [dict(zip(("kind", "model", "behaviour", "procedure", "destination"), k), levels=seen[k])
                        for k in sorted(shared, key=str)],
        "edges": [{"from": f, "to": t, "kinds": sorted(k)} for (f, t), k in edges.items()],
        "levels": levels,
    }
    targets = {t for _, t in edges}
    sources = {f for f, _ in edges}
    result["no_incoming_edge"] = sorted(known - targets)
    result["no_outgoing_edge"] = sorted(set(scanned) - sources)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    lines = ["| From | To | Evidence | Carrier (model, behaviour or position) |", "|---|---|---|---|"]
    for entry in levels:
        for row in entry["rows"]:
            dest = row["destination"]
            if row["kind"] == "actor":
                carrier = (f"`{row['model']}` variable {row['variable']} at "
                           f"({', '.join(f'{v:.0f}' for v in row['position'])})"
                           + (f", {row['distance_from_isolated_spawn']} from the isolated spawn"
                              if "distance_from_isolated_spawn" in row else "")
                           + (f"; referenced by {', '.join('`' + m + '`' for m in row['referenced_by'])}"
                              if row.get("referenced_by") else ""))
            else:
                carrier = f"`{row['model']}` {row.get('behaviour', '')} {row.get('procedure', '')}".strip()
            lines.append(f"| `{entry['level']}` | `{dest}` | {row['kind']} | {carrier} |")
    text = "\n".join(lines) + "\n"
    if a.md:
        a.md.parent.mkdir(parents=True, exist_ok=True)
        a.md.write_text(text, encoding="utf-8")
    print(f"M14_GRAPH levels={len(levels)} edges={len(edges)} shared_rows={len(shared)} "
          f"no_incoming={len(result['no_incoming_edge'])} no_outgoing={len(result['no_outgoing_edge'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
