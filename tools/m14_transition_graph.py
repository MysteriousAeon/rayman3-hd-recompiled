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

Input (--scan, default the recorded format-1 scans in private/work/m14/scan/) is one scan set of a single format:
- format 1: node-type and procedure names were printed from Raymap's tables by the probe of that time (RE_NOTES "M5"
  naming caveat) and the format-1 matching below relies on them; kept so the recorded table stays reproducible.
- format 2 with "spec": "D-113-2" (private/work/m14/scan_v2/): node types from the title's interpreter (E-270): a
  change-map call is a procedure call (type 04) whose table-A handler passes its first argument, converted by
  822621C8 (string or text handle), to the level request 82102CA8 (RE_NOTES "M13"): ids 0x21A / 0x21B (handlers
  8223F5A8 / 8223F4F0) and 0x64 / 0x65 / 0x66 (shared handler 82244570, which special-cases "sk8_00" and
  "menumap": those two may not request the named level, so their rows carry "special"). Only direct calls to
  82102CA8 were checked. A literal is type 14, a text constant type 1C, a designer variable type 0B / 0A, an actor
  reference type 17. Format-2 files without the D-113-2 labels are refused.
This tool reads no Raymap file.
"""
import argparse
import ast
import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "private" / "work" / "m14" / "scan"
GAMEDATA = ROOT / "private" / "extracted" / "5841123F" / "GAMEDATAbin"
NODE = re.compile(r"^( *)([A-Za-z0-9_]+):(.*)$")
CHANGE = re.compile(r"ChangeMap|ChangeLevel", re.IGNORECASE)   # format 1 only (Raymap-era names in the scan text)
NODE_V2 = re.compile(r"^( *)k([0-9A-F]{2}):([0-9A-F]{8})(?: (.*))?$")
CHANGE_V2 = {0x21A, 0x21B, 0x64, 0x65, 0x66}   # table-A procedure ids (E-270)
SPECIAL_V2 = ({0x64, 0x65, 0x66}, {"sk8_00", "menumap"})   # names 82244570 handles before or instead of the request


def scan_format(lines: list, path: Path) -> int:
    head = json.loads(lines[0]) if lines and lines[0].startswith("{") else {}
    if "format" not in head:
        return 1
    if head.get("format") != 2 or head.get("spec") != "D-113-2":
        raise SystemExit(f"{path}: format-2 scan without the D-113-2 node labels; rescan with the current probe")
    return 2


def node(line: str, fmt: int):
    """(indent, role, value) of a script line: role text / changemap / string / dsgvar / other, or None."""
    if fmt == 1:
        m = NODE.match(line)
        if not m:
            return None
        kind, value = m.group(2), m.group(3)
        role = {"TextRef": "text", "String": "string", "DsgVarRef": "dsgvar"}.get(kind, "other")
        if kind == "Procedure" and CHANGE.search(value):
            role = "changemap"
        return len(m.group(1)), role, value.strip("'\"").lower() if role == "string" else value
    m = NODE_V2.match(line)
    if not m:
        return None
    kind, param, label = int(m.group(2), 16), int(m.group(3), 16), m.group(4) or ""
    if kind == 0x1C:
        return len(m.group(1)), "text", m.group(3)
    if kind == 0x04 and param in CHANGE_V2:
        return len(m.group(1)), "changemap", f"procA#{param:X}"
    if kind == 0x14 and label[:5] in ("str:'", 'str:"'):
        return len(m.group(1)), "string", ast.literal_eval(label[4:]).lower()
    if kind in (0x0A, 0x0B):
        return len(m.group(1)), "dsgvar", str(param & 0xFF)
    return len(m.group(1)), "other", m.group(3)


def level_names() -> list:
    return sorted(p.name.lower() for p in GAMEDATA.iterdir() if p.is_dir() and (p / f"{p.name}.lvl").is_file())


def short(header: str) -> str:
    return header.rsplit(":", 1)[-1].strip()


def model_of(path: Path) -> str:
    return path.stem.rsplit("_", 1)[0]


def analyse(scan: Path, level: str, known: set, misc: dict, formats: set) -> dict:
    base = scan / level
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
        fmt = scan_format(lines, path)
        formats.add(fmt)
        for index, line in enumerate(lines):
            if line.startswith("## "):
                behaviour = short(line) if "CreateComport" in line else line[3:].split(" ", 1)[0]
                continue
            n = node(line, fmt)
            if not n:
                continue
            indent, role, value = n
            if role == "text":
                text = misc.get(value.upper().zfill(8), "").lower()
                if text in known:
                    rows.append({"kind": "textref", "model": model, "behaviour": behaviour, "destination": text})
            if role != "changemap":
                continue
            args = []
            for follow in lines[index + 1:index + 12]:
                f = node(follow, fmt)
                if not f or f[0] <= indent:
                    break
                args.append(f[1:])
            destination, how = None, "variable"
            for arole, avalue in args:
                if arole == "string":
                    destination, how = avalue, "script"
                    break
                if arole == "text":
                    destination, how = misc.get(avalue.upper().zfill(8), f"text {avalue}").lower(), "script"
                    break
            if destination is None:
                refs = [v for k, v in args if k == "dsgvar"]
                own = by_perso.get(perso, {}).get("texts", {})
                held = (own.get(refs[0], {}).get("text") or "").lower() if refs else ""
                destination = held if held else ("variable " + refs[0] if refs else "expression")
            rows.append({"kind": how, "model": model, "behaviour": behaviour, "procedure": value,
                         "destination": destination})
            if fmt == 2 and int(value[6:], 16) in SPECIAL_V2[0] and destination in SPECIAL_V2[1]:
                rows[-1]["special"] = "82244570 special-cases this name; the named level may not be requested"
    # who refers to a change-map actor instance (for example to set the custom bit that fires it)
    targets = {r["perso"]: r for r in rows if r["kind"] == "actor"}
    for path in sorted((base / "scripts").glob("*.txt")):
        text = path.read_text(errors="replace")
        for perso, row in targets.items():
            if path.stem.endswith(perso):
                continue
            if f"PersoRef:{perso}" in text or f"k17:{perso}" in text or perso.lower() in text.split("## ", 1)[0]:
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
    ap.add_argument("--scan", type=Path, default=SCAN, help="scan set (format-1 scan/ or format-2 scan_v2/)")
    a = ap.parse_args()
    known = set(level_names())
    if not a.scan.is_dir():
        raise SystemExit(f"{a.scan}: no scan set")
    scanned = sorted(p.name for p in a.scan.iterdir() if (p / "actors.json").is_file())
    if not scanned:
        raise SystemExit(f"{a.scan}: no scanned level (actors.json)")
    misc = {}
    for level in scanned:
        path = a.scan / level / "misc_texts.json"
        if path.is_file():
            misc = json.loads(path.read_text(encoding="utf-8"))
            break
    formats = set()
    levels = [analyse(a.scan, level, known, misc, formats) for level in scanned]
    if len(formats) > 1:
        raise SystemExit(f"{a.scan}: format-1 and format-2 scans mixed; the shared-row test needs one format")

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
            if dest in known and dest != entry["level"] and "special" not in row:
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
