#!/usr/bin/env python3
"""E-470 (D-237) G4a: offline, read-only audit of actor registration structures in one level (intro_10 by default).

Prints counts and offsets only (no game bytes). Pointer conventions as in RE_NOTES "Script constants": a .ptr
same-file entry {i32 file, u32 slot} relocates the word at file offset slot + 4; a pointer's target is its value
+ 4 in the target file (0 fix, 1 level, 2 transit). Cross-file (m) entries {off_a, file_a, off_b, file_b}.
Checks:
  - actors = SuperObjects {+0 type 2, +4 -> Perso} whose Perso +4 StdGame +0xC points back;
  - their parent (SO +0x1C), the dynamic world in transit.lvl (from transit's own header), its child list
    {+8 first, +0xC last (both set by level cross-file entries), +0x10 count} and the sibling chain
    (+0x14 next, +0x18 previous) walked like guest 82127798 (+8 then +0x14 until 0);
  - per actor: StdGame {family, model, personal} indexes, incoming references from outside its own block;
  - the level-wide SuperObject record list (0x48-byte records {+0 next, +4 -> SO}) from its head word;
  - the matrix snapshot list (0x18-byte records {+4 next, +8 -> matrix, +0xC -> copy});
  - one lum block (NIN_m_Lums_Int10, SO 0x548750 in intro_10): relocated words by target class.
usage: g4a_actor_audit.py [LEVEL]
"""
import collections
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
G = ROOT / "private" / "extracted" / "5841123F" / "GAMEDATAbin"


def load(level):
    d = G / level
    lvl, ptr = (d / f"{level}.lvl").read_bytes(), (d / f"{level}.ptr").read_bytes()
    tl, tp = (d / "transit.lvl").read_bytes(), (d / "transit.ptr").read_bytes()
    return lvl, ptr, tl, tp


def entries(ptr, m):
    n = struct.unpack_from(">I", ptr, 0)[0]
    same = [struct.unpack_from(">iI", ptr, 4 + 8 * i) for i in range(n)]
    cross = [struct.unpack_from(">IiIi", ptr, 4 + 8 * n + 16 * j) for j in range(m)]
    return same, cross


def main(level="intro_10"):
    lvl, ptr, tl, tp = load(level)
    u = lambda b, o: struct.unpack_from(">I", b, o)[0]   # noqa: E731
    same, cross = entries(ptr, u(lvl, 0))
    slots = {loc + 4: f for f, loc in same}
    tsame, _ = entries(tp, u(tl, 0))
    tslots = {loc + 4: f for f, loc in tsame}

    def tgt(o):
        return (slots[o], u(lvl, o) + 4) if o in slots else None
    inv = collections.defaultdict(list)
    for o, f in slots.items():
        if f == 1:
            inv[u(lvl, o) + 4].append(o)
    out = {"level": level}
    actors = []
    for o in sorted(slots):
        so = o - 4
        if so >= 4 and u(lvl, so) == 2 and slots.get(so + 4) == 1:
            pe = u(lvl, so + 4) + 4
            if slots.get(pe + 4) == 1:
                sg = u(lvl, pe + 4) + 4
                if slots.get(sg + 0xC) == 1 and u(lvl, sg + 0xC) + 4 == so:
                    actors.append(so)
    out["actors"] = len(actors)
    parents = collections.Counter(tgt(so + 0x1C) for so in actors)
    out["actor_parents"] = [[p[0], p[1], c] if p else [None, None, c] for p, c in parents.items()]
    # transit header: dynamic world = the parent all level actors share; check its role in transit's own table
    (pf, dw), = [p for p in parents if p] if len(parents) == 1 else [(None, None)]
    th = [u(tl, 4 + 4 * i) + 4 if 4 + 4 * i in tslots else None for i in range(16)]
    out["transit_header_has_dynamic_world_at"] = [4 + 4 * i for i, v in enumerate(th) if v == dw]
    dwo = {"first_set_by_cross": [], "last_set_by_cross": []}
    for oa, fa, ob, fb in cross:
        if fa == 2 and oa + 4 == dw + 8:
            dwo["first_set_by_cross"].append(ob + 4)
        if fa == 2 and oa + 4 == dw + 0xC:
            dwo["last_set_by_cross"].append(ob + 4)
    dwo["count_word"] = u(tl, dw + 0x10)
    # walk siblings from first (as 82127798)
    walk, so = [], (dwo["first_set_by_cross"] or [None])[0]
    while so and len(walk) < 10000:
        walk.append(so)
        t = tgt(so + 0x14)
        so = t[1] if t and t[0] == 1 else None
    dwo["walked"] = len(walk)
    dwo["walk_is_all_actors"] = sorted(walk) == sorted(actors)
    dwo["walk_ends_at_last"] = bool(walk) and walk[-1] == (dwo["last_set_by_cross"] or [None])[0]
    dwo["previous_links_consistent"] = all(tgt(b + 0x18) == (1, a) for a, b in zip(walk, walk[1:]))
    out["dynamic_world"] = dwo
    # per-actor identity and outside references
    per = []
    for so in actors:
        pe = u(lvl, so + 4) + 4
        sg = u(lvl, pe + 4) + 4
        sib = {x for x in (tgt(so + 0x14), tgt(so + 0x18)) if x}
        ext = [x for x in inv.get(so, []) if (1, x - 0x14) not in sib and (1, x - 0x18) not in sib]
        per.append({"so": so, "std": [u(lvl, sg), u(lvl, sg + 4), u(lvl, sg + 8)], "refs_besides_siblings": len(ext),
                    "brain4": u(lvl, u(lvl, pe + 0xC) + 4 + 4) if slots.get(pe + 0xC) == 1 else None})
    out["personal_index_unique"] = len({p["std"][2] for p in per}) == len(per)
    out["brain4_values"] = dict(collections.Counter(f"{p['brain4']:08x}" for p in per if p["brain4"] is not None))
    # level-wide SO record list
    heads = [o for o in slots if tgt(o) and tgt(o)[0] == 1 and not inv.get(o)]
    recs = {}
    for so in actors:
        for x in inv.get(so, []):
            nx = tgt(x - 4)
            if nx and nx[0] == 1 and nx[1] - (x - 4) == 0x48 and u(lvl, x + 4) == 0x01000000:
                recs[x - 4] = so
    def back(r):
        seen = set()
        while r not in seen:
            seen.add(r)
            prev = [q for q in inv.get(r, []) if tgt(q) == (1, r)]
            if not prev:
                return r
            r = prev[0]
        return r

    def fwd(c):
        chain = []
        while c and len(chain) < 20000:
            chain.append(c)
            t = tgt(c)
            c = t[1] if t and t[0] == 1 else None
        return chain
    chain = max((fwd(h) for h in {back(r) for r in recs}), key=len, default=[])
    recs = {r: s for r, s in recs.items() if r in chain}
    kinds = collections.Counter()
    for c in chain[1:]:
        t = tgt(c + 4)
        kinds["fix" if t and t[0] == 0 else (u(lvl, t[1]) if t and t[0] == 1 else "none")] += 1
    out["so_record_list"] = {"head_word": chain[0] if chain else None, "records": len(chain) - 1,
                             "actor_records": len(recs), "target_so_types": {str(k): v for k, v in kinds.items()},
                             "parentless_type2": sum(1 for c in chain[1:] if tgt(c + 4) and tgt(c + 4)[0] == 1
                                                     and u(lvl, tgt(c + 4)[1]) == 2 and tgt(c + 4)[1] not in actors)}
    # matrix snapshot records for actors
    snaps = sum(1 for so in actors for x in inv.get(u(lvl, so + 0x20) + 4, []) if x != so + 0x20)
    out["actor_matrices_with_snapshot_record"] = snaps
    # lum block
    LUM, SIZE = 0x548750, 0x4B8
    if level == "intro_10" and LUM in actors:
        cls = collections.Counter()
        for o in range(LUM, LUM + SIZE, 4):
            if o in slots:
                f, a = tgt(o)
                cls["in_block" if f == 1 and LUM <= a < LUM + SIZE else ("level_external" if f == 1 else f"file{f}")] += 1
        incoming = {f"+0x{o - LUM:x}": len([x for x in inv.get(o, []) if not LUM <= x < LUM + SIZE])
                    for o in range(LUM, LUM + SIZE, 4) if [x for x in inv.get(o, []) if not LUM <= x < LUM + SIZE]}
        pe = u(lvl, LUM + 4) + 4
        out["lum_block"] = {"so": LUM, "size": SIZE, "relocated": dict(cls), "incoming_from_outside": incoming,
                            "perso_components_present": [i for i in range(11) if u(lvl, pe + 4 * i)],
                            "mind_dsgmem": u(lvl, u(lvl, u(lvl, pe + 0xC) + 4) + 4 + 0xC)}
    out["per_actor_refs_besides_siblings"] = dict(collections.Counter(p["refs_besides_siblings"] for p in per))
    print(json.dumps(out, indent=1))
    ok = dwo["walk_is_all_actors"] and dwo["walk_ends_at_last"] and dwo["count_word"] == len(actors)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
