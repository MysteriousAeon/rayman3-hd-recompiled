#!/usr/bin/env python3
"""G6-P6 (D-259): read-only pointer ownership census assistant for one existing actor of a level.

PROPOSES ownership classes for the relocated pointer words of one actor's file block, with the evidence for each, for
human or coding-agent review. It never authorizes anything: its output is not an ownership map the structural compiler
accepts (the compiler's maps are written per operation, from a verified census and an oracle; D-256 / D-258).

  python tools/actor_pointer_census.py --level intro_10 --model NIK_mGenSound --instance 2
  python tools/actor_pointer_census.py --level intro_10 --model NIK_mGenSound --instance 2 --json private/work/x.json
  python tools/actor_pointer_census.py ... --json -          (JSON to stdout)

Reads (never writes) the level's .lvl / .ptr, transit.lvl and fix.lvl through the mod tool's parsers
(tools/r3hd_mods.py: script index, pointer table, graph decode); the three level files must be an allow-listed
version (STRUCT_ALLOW + the verified transit hashes). JSON goes only to stdout or a new file under private/.

Scope: every relocated word (own-file or other-file .ptr entry) in [SuperObject, next actor SuperObject in file
order); "next actor" = the next SuperObject named by the level's SO-record list. Classes (G6-P5's): owned, shared,
other-file, sibling link, reference; plus UNKNOWN (no rule applies) and CONFLICTING (rules disagree). Rules are listed
in RULES; every rule that fires is reported, none is preferred over another.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import r3hd_mods as rm  # noqa: E402

SCHEMA = 1
CLASSES = ("owned", "shared", "other-file", "sibling link", "reference")
RECORDS_REF = 0x1CFC          # level word naming the SO-record list header (RE_NOTES G4b; intro_10 and intro_20)
FILE_NAMES = {0: "fix.lvl", 2: "transit.lvl"}   # other-file indices (RE_NOTES G4b: 0 fix, 1 the level, 2 transit)
DESIGNER_REF_TYPES = {18: "actor", 19: "waypoint", 20: "graph"}
GRAPH_NODE_LIMIT = 1024      # revision 1 (after the holdout's first pass): the flight graph has > 64 nodes
RULES = {
    "R-other": "other-file: the .ptr entry names another file (the word keeps its other-file target)",
    "R-link": "sibling link: SuperObject +0x14 / +0x18 naming an actor SuperObject that links back reciprocally",
    "R-chain-own": "owned: a decoded per-instance chain field (SO+4 Perso, SO+0x20 matrix, Perso +0/+4/+8/+0xC, "
                   "Brain+0 Mind, Mind+4 Intelligence, Mind+0xC DsgMem, DsgMem+4/+8 designer buffers) whose target "
                   "lies in the block",
    "R-chain-model": "shared: a decoded model-descriptor field (Mind+0 AI model, DsgMem+0 model DsgVar)",
    "R-peer-own": "owned: every other instance of the model has a relocated word at the same block offset whose "
                  "target is at the same offset inside ITS OWN block (independent per-instance copies)",
    "R-peer-share": "shared: every other instance of the model has a relocated word at the same block offset with the "
                    "same target outside all of their blocks (model data; designer buffers and SuperObject headers "
                    "excluded)",
    "R-designer-ref": "reference: a relocated designer-variable word of type actor / waypoint / graph whose target "
                      "outside the block decodes as that type",
    # G6-P7 (D-260), rules revision 2
    "R-model-object": "shared: the target is the START of a decoded object of the actor's OWN AI model (the record "
                      "Mind+0 names, recognized by the script index's behaviour-name decode: the AI model record, a "
                      "behaviour list header, a behaviour record, a script array, a script node array, the DsgVar "
                      "record); words lying inside those objects are model data themselves and get no class",
    "R-peer-layout": "owned: at least two OTHER instances of the model have the identical block layout (same block "
                     "size, same relocated offsets and file indices) and each points to the same relative offset "
                     "inside its own block (instances of another layout, e.g. one that embeds the model, are not "
                     "comparable and are left out of this rule)",
}
REV2_RULES = ("R-model-object", "R-peer-layout")
RULES_REVISION = 2   # 1 = G6-P6's rule set (kept selectable for the before / after calibration)


class CensusError(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def load_level(game: Path, level: str) -> dict:
    """The level's files, read-only, checked against the allow-list (sizes and SHA-256)."""
    allow = rm.STRUCT_ALLOW.get(level)
    transit = {s["transit"] for spec in (rm.LUM_ALLOW, rm.FROG_ALLOW, rm.FAIRY_ALLOW, rm.GMGR_ALLOW)
               for lv, s in spec.items() if lv == level}
    if allow is None or len(transit) != 1:
        raise CensusError("UNSUPPORTED", f"level {level!r} has no verified file hashes")
    lvl_p, ptr_p, me = rm.script_level_files(game, level)
    paths = {"lvl": lvl_p, "ptr": ptr_p, "transit": lvl_p.with_name("transit.lvl"),
             "fix": game / "GAMEDATAbin" / "fix.lvl"}
    for k, p in paths.items():
        if not p.is_file():
            raise CensusError("TARGET_MISSING", f"{p.name} not found")
    data = {k: p.read_bytes() for k, p in paths.items()}
    want = {"lvl": allow["lvl"], "ptr": allow["ptr"], "transit": next(iter(transit))}
    for k, (size, h) in want.items():
        if (len(data[k]), sha256(data[k])) != (size, h):
            raise CensusError("TARGET_CHANGED", f"{paths[k].name} is not the allow-listed version")
    return {"level": level, "paths": paths, "data": data, "me": me,
            "hashes": {k: sha256(v) for k, v in data.items()}}


def resolve_model(ix: dict, model: str) -> str:
    keys = [k for k, v in ix["placements"].items() if v]
    if model in keys:
        return model
    hits = [k for k in keys if model in k]
    if len(hits) != 1:
        raise CensusError("UNSUPPORTED", f"model {model!r} matches {len(hits)} placed models (give a unique name)")
    return hits[0]


def model_objects(lvl: bytes, slots: dict, me: int, target, ix: dict, aim: int) -> dict:
    """G6-P7: {offset: (kind, size)} of the decoded objects of the AI model record `aim`, read through the script
    index (behaviour-list headers recognized by behaviour names; scripts and node arrays as the index walks them);
    empty unless `aim` is a model record the index recognizes."""
    headers = ix.get("headers") or {}
    recs = {m for ms in rm.model_records(lvl, slots, target, headers).values() for m in ms}
    if aim not in recs:
        return {}
    objs = {aim: ("AI model", 0x10)}
    for lst in (target(aim), target(aim + 4)):
        if lst not in headers or target(lst) is None:
            continue
        objs[lst] = ("behaviour list header", 8)
        base = target(lst)
        for i, nm in enumerate(headers[lst]):
            r = base + i * rm.BEHAVIOR_SIZE
            objs[r] = ("behaviour", rm.BEHAVIOR_SIZE)
            arr, n = target(r + 0x100), lvl[r + 0x108]
            if arr is None or not n:
                continue
            objs[arr] = ("script array", 4 * n)
            for na, nodes in (ix["behaviours"].get(nm) or ()):
                if na is not None and nodes:
                    objs[na] = ("script nodes", 8 * (len(nodes) + 1))
    dv = target(aim + 8)
    if dv is not None:
        objs[dv] = ("DsgVar record", 0x10)
    return objs


def census(game: Path, level: str, model: str, instance: int, revision: int = RULES_REVISION) -> dict:
    L = load_level(game, level)
    lvl, ptr, tl, me = L["data"]["lvl"], L["data"]["ptr"], L["data"]["transit"], L["me"]

    def fail(why):
        raise CensusError("STRUCTURE", why)
    slots, cross, target, tail = rm.actor_tables(lvl, ptr, tl, me, fail)
    ix = rm.read_script_index(game, level)
    if ix["data"] != lvl:
        raise CensusError("TARGET_CHANGED", "the level file changed while it was read")
    key = resolve_model(ix, model)
    insts = ix["placements"][key]
    if not isinstance(instance, int) or not 0 <= instance < len(insts):
        raise CensusError("UNSUPPORTED", f"instance {instance!r} (the model has {len(insts)})")
    # the actor set: owners of the SO-record list
    rh = target(RECORDS_REF)
    owners = sorted({target(r + 4) for r in rm.actor_walk(target(rh), target) if target(r + 4) is not None}) \
        if rh is not None else []
    if not owners:
        fail("the SO-record list")

    def block(so):
        nxt = [o for o in owners if o > so]
        return (so, nxt[0]) if nxt else None
    SO = insts[instance]["so"]
    if SO not in owners or block(SO) is None:
        raise CensusError("UNSUPPORTED", "the actor is not followed by another actor SuperObject (scope undefined)")
    _, END = block(SO)
    peers = [i["so"] for n, i in enumerate(insts) if n != instance and i["so"] in owners and block(i["so"])]
    inblk = lambda o, b=SO, e=END: b <= o < e   # noqa: E731
    # designer layout (from the script index) and the source's buffers
    dsg = ix["defaults"].get(key) or {"vars": [], "instances": [], "length": 0}
    dinst = dsg["instances"][instance] if instance < len(dsg.get("instances") or []) else None
    vtypes = {off: t for off, t in (dsg.get("vars") or [])}
    bufs = []
    if dinst and isinstance(dinst.get("initial"), int) and isinstance(dinst.get("current"), int):
        bufs = [(dinst["initial"], dsg["length"]), (dinst["current"], dsg["length"])]
    in_buf = lambda o: next(((b, o - b) for b, n in bufs if b <= o < b + n), None)   # noqa: E731
    # decoded per-instance chain (each link only when it is an own-file slot of the block)
    chain_own, chain_model = {}, {}

    def link(field, name, own=True):
        if field is not None and inblk(field) and slots.get(field) == me and target(field) is not None:
            (chain_own if own else chain_model)[field] = name
            return target(field)
        return None
    perso = link(SO + 4, "SO+4 -> Perso")
    link(SO + 0x20, "SO+0x20 -> matrix")
    brain = mind = dm = None
    if perso is not None and inblk(perso):
        for k, nm in ((0, "3dData"), (4, "StdGame"), (8, "Dynam")):
            link(perso + k, f"Perso+{k:#x} -> {nm}")
        brain = link(perso + 0xC, "Perso+0xC -> Brain")
    if brain is not None and inblk(brain):
        mind = link(brain, "Brain+0 -> Mind")
    if mind is not None and inblk(mind):
        link(mind, "Mind+0 -> AI model", own=False)
        link(mind + 4, "Mind+4 -> Intelligence")
        dm = link(mind + 0xC, "Mind+0xC -> DsgMem")
    if dm is not None and inblk(dm):
        link(dm, "DsgMem+0 -> model DsgVar", own=False)
        link(dm + 4, "DsgMem+4 -> initial buffer")
        link(dm + 8, "DsgMem+8 -> current buffer")
    # embedded graphs: graphs a designer graph word names whose objects all lie inside the block
    embedded, emb_objs = [], set()
    for b, n in bufs:
        for off, t in vtypes.items():
            w = b + off
            if t == 20 and slots.get(w) == me and target(w) is not None and inblk(target(w)):
                objs = rm._graph_objects(lvl, target, target(w), GRAPH_NODE_LIMIT)
                if objs and all(inblk(o) and inblk(o + z - 1) for o, (_, z) in objs.items()):
                    embedded.append((min(objs), max(o + z for o, (_, z) in objs.items()), target(w)))
                    emb_objs |= {(o, o + z) for o, (_, z) in objs.items()}
    embedded = sorted(set(embedded))
    emb_objs = sorted(emb_objs)
    # membership is by the decoded objects themselves (revision 1), not the span between them: other per-instance
    # records may lie between a graph's objects
    in_emb = lambda o: any(a <= o < z for a, z in emb_objs)   # noqa: E731
    # G6-P7: the actor's own AI model (Mind+0), decoded through the script index; layout-identical peers
    aim = target(mind) if revision >= 2 and mind is not None and inblk(mind) and slots.get(mind) == me else None
    mobjs = model_objects(lvl, slots, me, target, ix, aim) if aim is not None else {}
    mspans = sorted((o, o + z) for o, (_, z) in mobjs.items())
    in_model = lambda o: any(a <= o < z for a, z in mspans)   # noqa: E731

    def layout(p):
        pe = block(p)[1]
        return pe - p, frozenset((o - p, slots[o]) for o in range(p, pe, 4) if o in slots)
    same = [p for p in peers if layout(p) == layout(SO)] if revision >= 2 else []
    sizes = {0: len(L["data"]["fix"]), me: len(lvl), 2: len(tl)}
    rows = []
    for o in range(SO, END, 4):
        if o not in slots:
            continue
        f = slots[o]
        raw = struct.unpack_from(">I", lvl, o)[0]
        t = raw + 4
        row = {"offset": o, "field": o - SO, "file": f, "target_resource": None, "target": None, "region": None,
               "candidates": {}, "against": [], "notes": []}
        cand = row["candidates"]

        def add(cls, rule, why):
            cand.setdefault(cls, []).append({"rule": rule, "evidence": why})
        if f != me:
            row["target_resource"] = FILE_NAMES.get(f, f"file {f}")
            row["target"] = t
            if f not in sizes or not 0 <= t < sizes[f]:
                row["notes"].append("other-file target outside that file's range (unmapped)")
            else:
                add("other-file", "R-other", f".ptr names file {f} ({row['target_resource']}), target {t:#x}")
        else:
            row["target_resource"] = f"{level}.lvl"
            if t >= len(lvl):
                row["notes"].append("own-file target outside the level (unmapped)")
            else:
                row["target"] = t
                row["region"] = ("embedded graph" if in_emb(t) else "embedded model" if in_model(t) else "block") \
                    if inblk(t) else "outside block"
                if in_model(o):
                    row["notes"].append("the word lies inside the decoded objects of the actor's own AI model (model "
                                        "data; no copy class)")
                elif t in mobjs:
                    add("shared", "R-model-object", f"target is the {mobjs[t][0]} at {t:#x} of the actor's AI model "
                        f"{aim:#x}")
                # sibling links
                if o in (SO + 0x14, SO + 0x18) and t in owners:
                    back = SO + 0x18 if o == SO + 0x14 else SO + 0x14
                    if target(t + (0x18 if o == SO + 0x14 else 0x14)) == SO:
                        add("sibling link", "R-link", f"{'next' if o == SO + 0x14 else 'previous'} actor {t:#x} "
                            f"links back")
                    else:
                        row["notes"].append(f"+{o - SO:#x} names an actor that does not link back (paired {back:#x})")
                if o in chain_own and inblk(t) and not in_emb(t):
                    add("owned", "R-chain-own", chain_own[o])
                if o in chain_model:
                    add("shared", "R-chain-model", chain_model[o])
                bw = in_buf(o)
                if bw is not None:
                    vt = vtypes.get(bw[1])
                    row["designer"] = {"buffer": bw[0], "offset": bw[1], "type": vt}
                    kind = DESIGNER_REF_TYPES.get(vt)
                    if kind and not inblk(t):
                        ok = (kind == "actor" and t in owners) or \
                             (kind == "graph" and rm._graph_objects(lvl, target, t, GRAPH_NODE_LIMIT) is not None)
                        if ok:
                            add("reference", "R-designer-ref", f"designer variable at +{bw[1]} (type {vt}, {kind}) "
                                f"names an existing {kind} {t:#x}")
                        else:
                            row["notes"].append(f"designer type {vt} ({kind}) but the target does not decode as one")
                    elif kind:
                        row["notes"].append(f"designer {kind} reference whose target lies inside the source's own "
                                            "block (embedded): keep (shared) or retarget (reference) is an operation "
                                            "decision, not evidence")
                    elif vt is None:
                        row["notes"].append("relocated word in a designer buffer at an offset with no declared variable")
                # peer evidence (not for SuperObject headers or designer buffers)
                if len(same) >= 2 and bw is None and o - SO >= 0x20 and not in_emb(o) and not in_model(o) \
                        and inblk(t) and not in_model(t):
                    k = o - SO
                    if all(slots.get(p + k) == me and target(p + k) == p + (t - SO) for p in same):
                        add("owned", "R-peer-layout", f"{len(same)} layout-identical instances "
                            f"({', '.join(hex(p) for p in same)}) each point +{t - SO:#x} into their own blocks")
                if peers and bw is None and o - SO >= 0x20 and not in_emb(o) and not in_model(o):
                    k = o - SO
                    rel, ab = [], []
                    for p in peers:
                        pe = block(p)[1]
                        po = p + k
                        if po >= pe or slots.get(po) != me or target(po) is None:
                            rel.append(False)
                            ab.append(False)
                            continue
                        pt = target(po)
                        rel.append(inblk(t) and p <= pt < pe and pt - p == t - SO)
                        ab.append(pt == t and not inblk(t) and not any(q <= t < block(q)[1] for q in peers))
                    if all(rel):
                        add("owned", "R-peer-own", f"all {len(peers)} other instances point +{t - SO:#x} into their "
                            "own blocks")
                    elif all(ab):
                        add("shared", "R-peer-share", f"all {len(peers)} other instances name the same target")
                    elif any(rel) or any(ab):
                        row["notes"].append(f"peers disagree ({sum(rel)} relative / {sum(ab)} absolute matches of "
                                            f"{len(peers)})")
                if in_emb(o):
                    row["notes"].append("the word lies inside an embedded graph's objects")
                if not cand and inblk(t) and not in_emb(t) and not in_model(o):
                    row["notes"].append("in-block target without per-instance evidence (location alone is not "
                                        "ownership)")
        cls = sorted(cand)
        row["proposal"] = cls[0] if len(cls) == 1 else ("CONFLICTING" if cls else "UNKNOWN")
        if len(cls) == 1:
            row["against"] = [c for c in CLASSES if c != cls[0]]
        rows.append(row)
    counts = {c: sum(r["proposal"] == c for r in rows) for c in CLASSES + ("UNKNOWN", "CONFLICTING")}
    classified = sum(counts[c] for c in CLASSES)
    return {"schema": SCHEMA, "tool": "actor_pointer_census", "authorizes_compilation": False,
            "level": level, "model": key, "instance": instance, "superobject": SO, "scope": [SO, END],
            "scope_rule": "relocated words in [SuperObject, next actor SuperObject named by the SO-record list)",
            "resources": {k: {"name": L["paths"][k].name, "size": len(L["data"][k]), "sha256": L["hashes"][k]}
                          for k in ("lvl", "ptr", "transit", "fix")},
            "peers": peers, "embedded_graphs": [[a, z, g] for a, z, g in embedded], "rules_revision": revision,
            "layout_peers": same, "ai_model": aim, "ai_model_in_block": bool(aim is not None and inblk(aim)),
            "ai_model_objects": len(mobjs),
            "designer": {"length": dsg.get("length"), "vars": [list(v) for v in dsg.get("vars") or []],
                         "buffers": [b for b, _ in bufs]},
            "rules": {k: v for k, v in RULES.items() if revision >= 2 or k not in REV2_RULES}, "rows": rows, "counts": counts, "total": len(rows),
            "coverage": round(classified / len(rows), 4) if rows else None}


def summary(c: dict) -> str:
    out = [f"actor_pointer_census: {c['level']} {c['model']!r} instance {c['instance']}",
           f"  SuperObject {c['superobject']:#x}, scope {c['scope'][0]:#x}..{c['scope'][1]:#x} "
           f"({c['scope'][1] - c['scope'][0]:#x} bytes), {c['total']} relocated words, {len(c['peers'])} peer "
           f"instance(s), {len(c['embedded_graphs'])} embedded graph(s)",
           "  " + ", ".join(f"{k} {v}" for k, v in c["counts"].items()) + f"; coverage {c['coverage']}",
           "  PROPOSALS ONLY: nothing here is an approved ownership map (authorizes_compilation = false)"]
    for r in c["rows"]:
        if r["proposal"] in ("UNKNOWN", "CONFLICTING"):
            why = "; ".join(r["notes"]) or ", ".join(sorted(r["candidates"])) or "no rule applies"
            tgt = f"{r['target']:#x}" if r["target"] is not None else "unmapped"
            out.append(f"  {r['proposal']:<11} +{r['field']:#06x} -> {r['target_resource']} {tgt}: {why}")
    return "\n".join(out)


def safe_output(path: str, game: Path) -> Path:
    p = Path(path).resolve()
    priv = (ROOT / "private").resolve()
    if priv not in p.parents:
        raise CensusError("UNSAFE_OUTPUT", "JSON output must be a new file under private/ (or '-' for stdout)")
    g = game.resolve()
    if p == g or g in p.parents or (ROOT / "private" / "extracted").resolve() in p.parents:
        raise CensusError("UNSAFE_OUTPUT", "JSON output must not be inside the game-resource directory")
    if p.exists():
        raise CensusError("UNSAFE_OUTPUT", "JSON output path exists (never overwritten)")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="read-only pointer ownership census of one actor (proposals only)")
    ap.add_argument("--level", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--instance", type=int, required=True)
    ap.add_argument("--json", help="write JSON to a NEW file under private/, or '-' for stdout")
    ap.add_argument("--game", help="game folder (default: the repository's private/extracted copy)")
    ap.add_argument("--rules-revision", type=int, choices=(1, 2), default=RULES_REVISION,
                    help="1 = G6-P6's rule set, 2 = with G6-P7's model-object and layout-peer rules (default)")
    a = ap.parse_args(argv)
    game = Path(a.game) if a.game else rm.resolve_paths(argparse.Namespace(home=None, mods=None, cache=None,
                                                                            game=None))["game"]
    try:
        out = safe_output(a.json, game) if a.json and a.json != "-" else None
        c = census(game, a.level, a.model, a.instance, a.rules_revision)
    except CensusError as x:
        print(f"REFUSED {x.code}: {x.detail}", file=sys.stderr)
        return 2
    text = json.dumps(c, indent=1, sort_keys=True)
    if a.json == "-":
        print(text)
    else:
        print(summary(c))
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "x", encoding="utf-8", newline="\n") as fh:
                fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
