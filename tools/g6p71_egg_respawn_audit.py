#!/usr/bin/env python3
"""G6-P71: read-only audit of the title's egg respawn wiring (GitHub issue #8, knaar_10 soft-lock report).

    python -B tools/g6p71_egg_respawn_audit.py check      -> G6P71_EGG_AUDIT PASS n/n   (private M14 dumps)
    python -B tools/g6p71_egg_respawn_audit.py report     -> JSON summary on stdout     (private M14 dumps)
    python -B tools/g6p71_egg_respawn_audit.py selftest   -> G6P71_SELFTEST PASS n/n    (synthetic, no game data)

Input: the existing read-only M14 format-2 script dumps in private/work/m14/scan_v2/<level>/ (actors.json and
scripts/*.txt; their int / real constants equal the level files, RE_NOTES "Script constants", E-455). No game
process, no guest memory, no write outside private/work/g6p71/. Output stays private (game-derived names).

For every `NIK_SpoRamassable` instance (the carried "egg": one actor that is both the pickup and its own
dispenser) it records:
  - the behaviour transition graph of its own model (ChangeComport targets per behaviour, procA#4A);
  - every actor bound to it through a designer variable of type 18 (actor) holding the egg's super-object
    (the floor switches of knaar_10 each name one egg);
  - every external forced change of its behaviour (procA#48 with the egg as a constant actor), with the
    comparison and designer variable that guard it (the level actor's kill plane in knaar_10).
Node names after Raymap's R3 tables are SUPPORTED only (RE_NOTES "M5 completion" naming caveat); the audit relies
on structure: addresses, node types, designer-variable numbers and behaviour names.
"""
import argparse
import json
import re
import shutil
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = ROOT / "private" / "work" / "m14" / "scan_v2"
WORK = ROOT / "private" / "work" / "g6p71"
EGG_MODEL = "NIK_SpoRamassable"
PREFIX = "NIK_SpoRamassable.rul^CreateIntelligence^CreateComport:"

BEHAVIOUR = re.compile(r"^## (normal|reflex|macro) ([0-9A-F]{8})(?: (\S+))?")
TARGET = re.compile(r"k1D:[0-9A-F]{8} behaviour:\S+:(\w+)")
DSGVAR_LINE = re.compile(r"^dsgvar (\d+) t(\d+) ([0-9a-fA-F]*)")

# Expected facts of the real dumps (the check's oracle). Positions are rounded file-domain values.
EXPECTED = {
    "eggs": {"fact_40": 2, "fact_50": 1, "knaar_10": 2, "knaar_45": 1},
    "graph": {
        "NIK_C_Sporamassable_Init": ["NIK_C_SpoRamassable_GenerateurWaitSafe", "NIK_C_SpoRamassable_Lancer"],
        "NIK_C_Sporamassable_Loop": ["NIK_C_SpoRamassable_Pris"],
        "NIK_C_SpoRamassable_Pris": ["NIK_C_SpoRamassable_Lancer", "NIK_C_Sporamassable_Loop"],
        "NIK_C_SpoRamassable_Lancer": ["NIK_C_SpoRamassable_Explose", "NIK_C_Sporamassable_Loop"],
        "NIK_C_SpoRamassable_Explose": ["NIK_C_SpoRamassable_ResetParametersOLD"],
        "NIK_C_SpoRamassable_Wait": [],
        "NIK_C_Sporamassable_GenerateurGo": ["NIK_C_SpoRamassable_Lancer"],
        "NIK_C_SpoRamassable_GenerateurWaitSafe": ["NIK_C_Sporamassable_GenerateurGo"],
        "NIK_C_SpoRamassable_ResetParametersOLD": ["NIK_C_SpoRamassable_GenerateurWaitSafe",
                                                   "NIK_C_SpoRamassable_Lancer"],
    },
    # knaar_10: switch perso -> egg perso; egg perso -> external nets (actor model, operator, dsgvar, z).
    "knaar_10_switches": {"41310A48": "41311EF8", "4131A720": "412F6950"},
    "knaar_10_nets": {"412F6950": [("Levelknaar_10", "boolcall#8", 8, -244.36)], "41311EF8": []},
}


def floats(hexstr: str) -> list:
    raw = bytes.fromhex(hexstr)
    return [round(v, 2) for v in struct.unpack(">" + "f" * (len(raw) // 4), raw)]


def parse_dump(path: Path) -> dict:
    """One script dump: header, designer variables, blocks (kind, address, name, lines)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    dsgvars, blocks, current = {}, [], None
    for line in lines[1:]:
        m = DSGVAR_LINE.match(line)
        if m and current is None:
            dsgvars[int(m.group(1))] = (int(m.group(2)), m.group(3).lower())
            continue
        m = BEHAVIOUR.match(line)
        if m:
            current = dict(kind=m.group(1), addr=m.group(2), name=(m.group(3) or "").split(":")[-1] or m.group(2),
                           lines=[])
            blocks.append(current)
        elif current is not None:
            current["lines"].append(line)
    return dict(header=header, dsgvars=dsgvars, blocks=blocks, file=path.name)


def own_graph(dump: dict) -> dict:
    """Behaviour -> sorted ChangeComport (procA#4A) targets in the actor's own normal behaviours."""
    graph = {}
    for block in dump["blocks"]:
        if block["kind"] != "normal":
            continue
        targets = set()
        body = block["lines"]
        for i, line in enumerate(body):
            if "procA#4A " in line and i + 1 < len(body):
                m = TARGET.search(body[i + 1])
                if m:
                    targets.add(m.group(1))
        graph[block["name"]] = sorted(targets)
    return graph


def external_forces(dump: dict, perso: str) -> list:
    """Forced behaviour changes (procA#48) of `perso` from another actor, with their guard."""
    out = []
    for block in dump["blocks"]:
        body = block["lines"]
        for i, line in enumerate(body):
            if "procA#48 " not in line or i + 2 >= len(body):
                continue
            if f"k17:{perso} actor" not in body[i + 1]:
                continue
            m = TARGET.search(body[i + 2])
            guard_op = guard_var = None
            for prev in body[:i]:
                op = re.search(r"(boolcall#[0-9A-F]+)", prev)
                if op and guard_op is None:
                    guard_op = op.group(1)
                var = re.search(r"dsgvar#([0-9A-F]+)", prev)
                if var and guard_var is None:
                    guard_var = int(var.group(1), 16)
            value = dump["dsgvars"].get(guard_var) if guard_var is not None else None
            z = floats(value[1])[2] if value and value[0] == 8 and len(value[1]) == 24 else None
            out.append(dict(by=dump["file"].rsplit("_", 1)[0], block=block["name"], kind=block["kind"],
                            target=m.group(1) if m else None, op=guard_op, dsgvar=guard_var, z=z))
    return out


def analyse(scan: Path) -> dict:
    levels = {}
    for level_dir in sorted(p for p in scan.iterdir() if (p / "actors.json").is_file()):
        actors = json.loads((level_dir / "actors.json").read_text(encoding="utf-8"))["actors"]
        eggs = [a for a in actors if a.get("model") == EGG_MODEL]
        if not eggs:
            continue
        dumps = {p.name: parse_dump(p) for p in sorted((level_dir / "scripts").glob("*.txt"))}
        entries = []
        for egg in eggs:
            perso = egg["perso"].upper()
            own = next((d for d in dumps.values() if d["header"].get("perso", "").upper() == perso), None)
            so = own["header"]["so"].lower() if own else None
            bound = sorted(d["header"]["perso"].upper() for d in dumps.values()
                           if d is not own and so and any(t == 18 and v == so for t, v in d["dsgvars"].values()))
            nets = [f for d in dumps.values() if d is not own for f in external_forces(d, perso)]
            entries.append(dict(perso=perso, so=so, position=[round(v, 1) for v in egg["position"]],
                                graph=own_graph(own) if own else None, bound_by=bound, nets=nets))
        levels[level_dir.name] = entries
    return levels


def judge(levels: dict, expected: dict) -> list:
    """(name, ok, detail) rows."""
    rows = []
    counts = {lvl: len(e) for lvl, e in levels.items()}
    rows.append(("E1 egg census", counts == expected["eggs"], counts))
    graphs = [e["graph"] for lvl in levels.values() for e in lvl]
    rows.append(("E2 one shared transition graph", bool(graphs) and all(g == expected["graph"] for g in graphs),
                 sorted({json.dumps(g, sort_keys=True) for g in graphs})[:1] if graphs else None))
    into_explose = sorted({src for g in graphs for src, dst in g.items() if "NIK_C_SpoRamassable_Explose" in dst})
    rows.append(("E3 Explose reached only from Lancer (own model)", into_explose == ["NIK_C_SpoRamassable_Lancer"],
                 into_explose))
    k10 = {e["perso"]: e for e in levels.get("knaar_10", [])}
    switches = {b: p for p, e in k10.items() for b in e["bound_by"]}
    rows.append(("E4 knaar_10 switch -> egg binding", switches == expected["knaar_10_switches"], switches))
    nets = {p: [(n["by"], n["op"], n["dsgvar"], n["z"]) for n in e["nets"]] for p, e in k10.items()}
    rows.append(("E5 knaar_10 external Explose nets", nets == expected["knaar_10_nets"], nets))
    targets_ok = all(n["target"] == "NIK_C_SpoRamassable_Explose" for lvl in levels.values() for e in lvl
                     for n in e["nets"])
    others = {f"{lvl}:{e['perso']}": len(e["nets"]) for lvl, es in levels.items() for e in es
              if lvl != "knaar_10" and e["nets"]}
    rows.append(("E6 no other forced egg change outside knaar_10", targets_ok and not others, others))
    return rows


def run_check(scan: Path, expected: dict, write: bool) -> int:
    if not scan.is_dir():
        print(f"G6P71_EGG_AUDIT BLOCKED: no private dumps at {scan}")
        return 2
    levels = analyse(scan)
    rows = judge(levels, expected)
    for name, ok, detail in rows:
        print(f"  {'PASS' if ok else 'FAIL'} {name}: {json.dumps(detail)}")
    passed = sum(ok for _, ok, _ in rows)
    if write:
        WORK.mkdir(parents=True, exist_ok=True)
        (WORK / "egg_respawn_audit.json").write_text(json.dumps(levels, indent=1), encoding="utf-8")
    print(f"G6P71_EGG_AUDIT {'PASS' if passed == len(rows) else 'FAIL'} {passed}/{len(rows)}")
    return 0 if passed == len(rows) else 1


# --- synthetic selftest -------------------------------------------------------------------------------------------

def _behaviour(addr: str, name: str, targets: list) -> list:
    out = [f"## normal {addr} Gen_NIK\\{EGG_MODEL}\\{PREFIX}{name}", "# script 00000000"]
    for t in targets:
        out += ["  k04:0000004A procA#4A 822457B8", f"    k1D:00000001 behaviour:Gen_NIK\\x.rul^C:{t}"]
    return out


def _egg_dump(perso: str, so: str) -> str:
    lines = [json.dumps({"so": so, "perso": perso}), "dsgvar 0 t22 00000001", "dsgvar 1 t22 00000002"]
    for i, (name, targets) in enumerate(EXPECTED["graph"].items()):
        lines += _behaviour(f"{0x10000000 + i:08X}", name, targets)
    return "\n".join(lines) + "\n"


def _write_fixture(root: Path, mutation: str | None) -> None:
    level = root / "knaar_10"
    (level / "scripts").mkdir(parents=True)
    eggs = [("412F6950", "412F68D0", [-157.4, 252.3, -240.2]), ("41311EF8", "41311E78", [-171.0, 157.0, -212.2])]
    actors = [dict(model=EGG_MODEL, perso=p, position=pos) for p, _, pos in eggs]
    actors += [dict(model="NIN_m_SwitchDalle", perso=s, position=[0, 0, 0]) for s in ("41310A48", "4131A720")]
    actors.append(dict(model="Levelknaar_10", perso="4130C5DC", position=[0, 0, 0]))
    (level / "actors.json").write_text(json.dumps(dict(level="knaar_10", actors=actors)), encoding="utf-8")
    for p, so, _ in eggs:
        (level / "scripts" / f"{EGG_MODEL}_{p}.txt").write_text(_egg_dump(p, so), encoding="utf-8")
    binding = {"41310A48": "41311e78", "4131A720": "412f68d0"}
    if mutation == "rebind":
        binding["4131A720"] = "41311e78"
    for s, so in binding.items():
        (level / "scripts" / f"NIN_m_SwitchDalle_{s}.txt").write_text(
            json.dumps({"so": "0", "perso": s}) + f"\ndsgvar 0 t22 00000000\ndsgvar 1 t18 {so}\n", encoding="utf-8")
    net_egg = "41311EF8" if mutation == "net_moved" else "412F6950"
    z = "c3745cd6" if mutation != "net_lowered" else "c3800000"
    level_dump = [json.dumps({"so": "0", "perso": "4130C5DC"}), f"dsgvar 8 t8 c32f98434384d276{z}",
                  "## macro 4130F128", "  k00:00000000", "    k01:00000008 boolcall#8",
                  "      k02:00000010", "        k02:0000000D", f"          k17:{net_egg} actor",
                  "      k02:00000010", "        k0B:00000008 dsgvar#8", "  k00:00000010"]
    if mutation != "net_removed":
        level_dump += ["    k04:00000048 procA#48 82245688", f"      k17:{net_egg} actor",
                       "      k1D:412F7518 behaviour:Gen_NIK\\x.rul^C:NIK_C_SpoRamassable_Explose"]
    (level / "scripts" / "Levelknaar_10_4130C5DC.txt").write_text("\n".join(level_dump) + "\n", encoding="utf-8")
    if mutation == "graph":
        path = level / "scripts" / f"{EGG_MODEL}_41311EF8.txt"
        text = path.read_text(encoding="utf-8") + "\n".join(
            _behaviour("1FFFFFFF", "NIK_C_SpoRamassable_Wait", ["NIK_C_SpoRamassable_Explose"])) + "\n"
        path.write_text(text, encoding="utf-8")


def selftest() -> int:
    expected = dict(EXPECTED, eggs={"knaar_10": 2})
    cases = [(None, 0), ("rebind", 1), ("net_removed", 1), ("net_moved", 1), ("net_lowered", 1), ("graph", 1)]
    passed = 0
    for mutation, want in cases:
        tmp = Path(tempfile.mkdtemp(prefix="g6p71_"))
        try:
            _write_fixture(tmp, mutation)
            levels = analyse(tmp)
            ok_all = all(ok for _, ok, _ in judge(levels, expected))
            got = 0 if ok_all else 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        ok = got == want
        passed += ok
        print(f"  {'PASS' if ok else 'FAIL'} fixture {mutation or 'baseline'}: "
              f"{'accepted' if got == 0 else 'rejected'} (want {'accepted' if want == 0 else 'rejected'})")
    vec = floats("c32f98434384d276c3745cd6")
    ok = vec == [-175.59, 265.64, -244.36]
    passed += ok
    print(f"  {'PASS' if ok else 'FAIL'} big-endian vec3 decode {vec}")
    total = len(cases) + 1
    print(f"G6P71_SELFTEST {'PASS' if passed == total else 'FAIL'} {passed}/{total}")
    return 0 if passed == total else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("check", "report", "selftest"))
    parser.add_argument("--scan", type=Path, default=SCAN)
    args = parser.parse_args()
    if args.mode == "selftest":
        return selftest()
    if args.mode == "report":
        print(json.dumps(analyse(args.scan), indent=1))
        return 0
    return run_check(args.scan, EXPECTED, write=True)


if __name__ == "__main__":
    sys.exit(main())
