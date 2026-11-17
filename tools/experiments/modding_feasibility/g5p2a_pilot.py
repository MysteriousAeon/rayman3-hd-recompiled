#!/usr/bin/env python3
"""E-477 (D-244) G5-P2a: the development-only `insert-graph-node` at two allow-listed sites of the intro_10 flight
graph (after node 13: G3b / G5-P1; after node 22: selected here) and the compiler's block-8 memory budget
(tools/r3hd_mods.py structural_budget). The runtime part is G5-P1's development gate (g5p1_dev_gate.py, unchanged).

usage:
  g5p2a_pilot.py check       offline O1-O7 (G5-P1's check re-run, plus site 22, budget and conflict checks)
  g5p2a_pilot.py negtest     deterministic runtime tests: G5-P1's 30 + 5 cases plus site-22 cases (no game)
  g5p2a_pilot.py TAG         hidden runs: B (node 13, neutral), C / D / E (node 22 neutral / offset / gate off)
  g5p2a_pilot.py judge TAG   P1-P8 (A = the retained E-476 run p1 base, see below)
Outputs stay under private/work/e477/.

SITE 22 (selected from the real graph, E-477; rejected alternatives in the report): node 22 -> node 23, one arc
  (+0 / +4 zero, attributes zero), both nodes' capabilities 0, waypoints owned by their node only, nodes referenced
  only by their neighbours and node 22's arc, visited 22 -> 23 on every loop of the base route (5 per run), 81.8 units
  from G3b's M (regions apart), segment 7.56 units, turns 8.5 / 0.3 degrees, the base path passes 1.021 from the
  segment midpoint (node 13: 0.843). Compiled layout: tail 96 bytes at 7,661,836 (node at +0, waypoint +28, list
  +48, arc +60; the source objects' 16-byte phases), nine new `.ptr` entries, four edited words.
  Neutral: M2 = midpoint of node 22's and node 23's waypoints. Offset: M2' = M2 + 6 units horizontally along
  (-dy, dx) / |d| of d = W23 - W22 (G3b's rule for M').

PROSPECTIVE PROTOCOL (committed before any run)
Build: g5p1_dev_gate.py apply + tools\\build_incremental.bat; production restored after (revert + rebuild).
Runs (G3b's runner, g3b_ab.run_case, unchanged; hidden, non-activating, muted, no physical pad, private user root,
  `--test-level intro_10`, no input, no captures, 150 s, generator sampled every 0.1 s for 75 s, tail every 1 s):
  A base: NOT re-run: the retained E-476 run p1 base (private/work/e476/p1/base, e476_p1_base; no plan, same game files,
     same runner; G3b k1 and E-476 p1 base agree: closest to M 0.843 / 0.845, read-back 26abb599...). Judged again.
  B: node 13 neutral (the compiler's plan, R3HD_DEV_STRUCTURAL_TX=intro_10).  C: node 22 neutral.  D: node 22
  offset.  E: D's plan, the variable unset (refused whole: `level_tx_not_enabled`).
Criteria (site constants: node 13 from G3b; node 22 from the compiler's output above, cross-checked offline by `check`):
  P1 resource integrity: B / C / D: `M33 mods state=active`, one `G5P1 level-tx active` with the plan's id; `M36 grow
     size` exactly intro_10.lvl 7661836 -> 7661836 + tail (112 / 96) and intro_10.ptr 209068 -> 209140; grow reads
     only of those two, kind=tail; only those two served; masked read-back of the original area equal to A's; tail
     fixed bytes (all but the new node's +0x10 / +0x14) equal to the compiler's tail relocated by the live base at
     >= 55 reads over >= 55 s and at both live reads; the site's original waypoints unchanged at the end.
  P2 relocation: B / C / D at both live reads: the three redirected words = the new node's live address, the count
     144 (A / E: original values, 143); the nine new pointers are part of P1's tail check.
  P3 registration: B / C / D: forward walk of 144 distinct nodes without problems, the new node at index after + 1
     (14 / 23), the rest = A's 143 in order, first / last as A; the site node's arc list {count 1, target new node};
     E as A.
  P4 consumption (C, D): generator variable 8 = the new waypoint's address in >= 3 samples, entered only from node
     22's waypoint and left only for node 23's, >= 2 visits; variable 10 there = M2 / M2' within 1e-4; never in E.
  P5 original-site regression (B): P1-P3 as above, variable 8 = the node-13 waypoint >= 3 samples, entered from node
     13 / left to node 14 only, >= 2 visits, variable 10 = M; B within 1.0 of A's path within 25 units of M and 0.5
     elsewhere (G3b N6; G3b k1 0.586 / 0.196, E-476 p1 0.587 / 0.198).
  P6 second-site effect: C within 1.7 of A's path within 25 units of M2 and 0.5 elsewhere; E within 0.5 everywhere;
     D's maximum distance from A >= 1.5 at a sample within 25 units of M2, displaced toward M2'; D's closest approach
     to M2' >= 1.0 smaller than A's and than C's; D >= 1.5 from C's path; D within 0.5 of A beyond 25 units.
     Derivation: noise 0.15 and isolation 0.5 (E-464); the neutral pull in G3b k1 / E-476 p1 was 0.586 / 0.587 for a
     path passing 0.843 from M (ratio 0.70); A passes 1.021 from M2, so C is predicted at about 0.71; (0.71 + 0.15)
     x 2 = 1.72 -> 1.7 (G3b's rule: prediction plus noise, doubled). Offset: gain 0.49 per unit (E-467 / E-468)
     predicts about 2.9 for 6 units (G3b observed 3.96-3.99); threshold 1.5 as G3b.
  P7 memory: every run: valid block-8 walks in every snapshot after the first valid one; level area length 7,661,832
     + tail (A / E: 7,661,832), chunk words words_for(length); free after load = 13,088,528 - tail (13,088,416 B,
     13,088,432 C / D; A / E 13,088,528); and free after load - the compiler's temporary bound (852,848 / 852,784)
     >= the 1 MiB margin (the compiler's budget holds in the observed state).
  P8 transaction and desktop safety: E: `state=refused reason=level_tx_not_enabled`, no `M36 grow`, no `M33 mods
     served`, no `G5P1` line; `check` and `negtest` pass on the run's baseline; every run: M21 / M22 / M23 0, haptics
     policy line, runner exit 0, no game process left.
  Invalid (new tag, not judged): file hashes differ, level not opened, area / generator not found, < 60 s of samples,
  a run's first sample after A's closest approach to the site's first waypoint (node 13 for B, node 22 for C-E).
  All eight = G5-P2a VERIFIED.
REVISION 1 (after run q1; q1 stays FAIL as written: P1 FAIL, P2-P8 PASS, judgement_q1.json kept):
  Cause: P1's masked read-back compares each run with A's. The runner zeroes the bound site's four edited words before
  hashing; the retained A (E-476 p1) was hashed with node 13's words zeroed, so it has no value for the site-22 mask
  (B = A = 26abb599...; C = D = E = e3cb0e7c... with E serving nothing: refused, no grow / served line). The value
  cannot be rebuilt offline (the live area is partly relocated at first appearance). Revised P1, for fresh runs only:
  B's masked read-back equals A's (node-13 mask); C's and D's equal E's (site-22 mask, same build, nothing served),
  and E's is present. Everything else unchanged. Fresh run: q2 (all four cases).
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))
import r3hd_mods as rm  # noqa: E402
import g3a_ab as g3a  # noqa: E402
import g3b_ab as g3b  # noqa: E402
import block8_probe as bp  # noqa: E402
import g5p1_pilot as p1  # noqa: E402

PREFIX = "e477"
WORK = ROOT / "private" / "work" / PREFIX
p1.WORK = WORK          # G5-P1's helpers write under this experiment's folder
LEVEL = p1.LEVEL
ENV = rm.STRUCT_ENV
u32, fnv = g3a.u32, g3a.fnv
SIZE, PSIZE, AREA, FREE0 = g3a.SIZE, g3a.PSIZE, g3a.AREA, g3a.FREE0
A_WORK, A_RUN = ROOT / "private" / "work" / "e476" / "p1" / "base", "e476_p1_base"
TOL_NEAR = {13: 1.0, 22: 1.7}


def f32(v):
    return struct.unpack(">f", struct.pack(">f", v))[0]


def site(after):
    """Constants of one allow-listed site from the original files and the graph resolver (not from a run)."""
    data, ptr = g3a.files()
    ix = rm.read_script_index(g3a.GAME, LEVEL)
    nodes = ix["graphs"][(rm.FLY10, 0, 0)]["nodes"]
    slots = ix["slots"]
    tg = lambda o: u32(data, o) + 4   # noqa: E731
    A, WA = nodes[after]
    B, WB = nodes[after + 1]
    LA = tg(A + 0x18)
    ARC = tg(LA)
    wa, wb = struct.unpack_from(">3f", data, WA), struct.unpack_from(">3f", data, WB)
    if after == 13:
        mid, off = g3b.M, g3b.MP
    else:
        mid = tuple(f32((x + y) / 2) for x, y in zip(wa, wb))
        d = (wb[0] - wa[0], wb[1] - wa[1])
        n = math.hypot(*d)
        perp = (-d[1] / n, d[0] / n)
        off = (f32(mid[0] + 6 * perp[0]), f32(mid[1] + 6 * perp[1]), mid[2])
    assert all(slots.get(o) == 1 for o in (A, B + 4, ARC + 0xC))
    return {"after": after, "A": A, "B": B, "WA": WA, "WB": WB, "LA": LA, "ARC": ARC, "wa": wa, "wb": wb,
            "M": mid, "MP": off, "WPOS": {"neutral": mid, "offset": off}, "graph": g3b.GRAPH,
            "changed": {A: B - 4, B + 4: A - 4, ARC + 0xC: B - 4}, "count_at": g3b.COUNT_AT}


def igm(after, variant):
    s = site(after)
    return p1.igm(after_node=after, position=list(s["WPOS"][variant]))


def compiled(after, variant):
    with p1.dev_env():
        rs, tx = rm.compile_insert_graph_node(igm(after, variant), {"game": g3a.GAME})
    return rs, tx


# --- offline -----------------------------------------------------------------------------------------------------

def refused(fn, code, env=LEVEL):
    with p1.dev_env(env):
        return p1.refused(fn, code)


def check():
    data, ptr = g3a.files()
    res, det = {}, {}
    # O1 + G5-P1's checks (node 13 byte identity with G3b, refusals, composition, production compiler) re-run
    rc = p1.check()
    off1 = json.loads((WORK / "offline.json").read_text())
    res["O1_g5p1_check_72"] = rc == 0 and off1["pass"] and len(off1["checks"]) == 72
    res["O1_node13_byte_identical"] = all(off1["checks"][f"P1_{v}_{k}"] for v in ("neutral", "offset")
                                          for k in ("lvl_bytes_identical", "ptr_bytes_identical"))
    (WORK / "offline_g5p1.json").write_text(json.dumps(off1, indent=1, default=str) + "\n")
    # site 22 through the whole compiler path (installed mod -> resolve_all -> plan), checked by G3's own model
    s = site(22)
    B1 = 0x40F5509C
    base_area, _, _ = g3a.relocate(data, ptr, B1)
    rd0 = lambda a: u32(base_area, a - B1)   # noqa: E731
    nodes0, prob0, hdr0 = g3b.walk_null(rd0, B1 + g3b.GRAPH - 4)
    res["site22_original_walk"] = not prob0 and len(nodes0) == 143 and nodes0[22] == B1 + s["A"] - 4
    for v in ("neutral", "offset"):
        r, text, paths = p1.compile_plan(f"s22_{v}", [(f"g5p2a.s22.{v}", [igm(22, v)])])
        m = p1.parse_plan(text or "")
        im = p1.images(m) if text else {}
        L, P = im.get("intro_10.lvl", b""), im.get("intro_10.ptr", b"")
        n0, m0 = u32(ptr, 0), u32(data, 0)
        n1 = u32(P, 0) if P else 0
        tail = len(L) - SIZE
        area, seen, dup = g3a.relocate(L, P, B1)
        rd = lambda a, area=area: u32(area, a - B1)   # noqa: E731
        nodes, prob, hdr = g3b.walk_null(rd, B1 + g3b.GRAPH - 4)
        new_entries = [struct.unpack_from(">iI", P, 4 + 8 * i) for i in range(n0, n1)]
        new_slots = [loc + 4 for _, loc in new_entries]
        FN = new_slots[0] if new_slots else 0
        NA = B1 + FN - 4
        objs = (FN, FN + 0x1C)
        # the new node's own words, read through the simulated relocation (independent of the compiler)
        wpt, lst = rd(NA + 0xC), rd(NA + 0x18)
        arc = rd(lst) if lst else 0
        diff = sorted({i & ~3 for i in range(SIZE) if L[i] != data[i]})
        all_slots = {struct.unpack_from(">iI", P, 4 + 8 * i)[1] + 4 for i in range(n1)}
        owners_w = sorted(so for so in all_slots if so + 4 <= len(L)
                          and u32(L, so) + 4 == wpt - B1 + 4) if wpt else []
        o2 = {
            "nodes_144_distinct": len(nodes) == 144 == len(set(nodes)) and hdr["count"] == 144,
            "walks_forward_backward": not prob,
            "inserted_at_23": len(nodes) > 23 and nodes[23] == NA and nodes[:23] + nodes[24:] == nodes0,
            "first_last_unchanged": hdr["first"] == hdr0["first"] and hdr["last"] == hdr0["last"],
            "arc_topology": (rd(rd(B1 + s["A"] - 4 + 0x18)) and rd(rd(rd(B1 + s["A"] - 4 + 0x18)) + 0xC) == NA
                             and rd(lst) == rd(lst + 4) == arc and rd(lst + 8) == 1 and rd(arc + 8) == lst
                             and rd(arc + 0xC) == B1 + s["B"] - 4 and rd(arc) == rd(arc + 4) == 0),
            "waypoint_owned_by_new_node": owners_w == [FN + 0xC]
                                          and struct.unpack_from(">3f", area, wpt - B1) == s["WPOS"][v],
        }
        o3 = {
            "new_entries_9_unique_in_bounds": (len(new_entries) == 9 and all(f == 1 for f, _ in new_entries)
                                               and len(set(new_slots)) == 9 and not dup
                                               and all(SIZE <= x and x + 4 <= len(L) for x in new_slots)
                                               and all(u32(L, x) + 4 < len(L) for x in new_slots)),
            "original_entries_and_cross_table": (P[4:4 + 8 * n0] == ptr[4:4 + 8 * n0]
                                                 and P[4 + 8 * n1:] == ptr[4 + 8 * n0:]
                                                 and len(P) == 4 + 8 * n1 + 16 * m0),
            "only_four_words_changed": diff == sorted(list(s["changed"]) + [s["count_at"]]),
            "tail_size": tail == 96 and objs[0] == SIZE,
        }
        recs = {"level-tx": len(m["txs"]), "tx-file": sum(len(f["tx"]) for f in m["files"]),
                "grow": sum(len(f["grow"]) for f in m["files"]), "ranges": [len(f["range"]) for f in m["files"]]}
        o4 = {"records": recs == {"level-tx": 1, "tx-file": 2, "grow": 2, "ranges": [5, 1]}
              and r["structural_active"] == {f"g5p2a.s22.{v}": LEVEL} and r["gameplay_active"] == [f"g5p2a.s22.{v}"]}
        for grp, d in (("O2", o2), ("O3", o3), ("O4", o4)):
            for k, x in d.items():
                res[f"{grp}_{v}_{k}"] = bool(x)
        det[v] = {"lvl_len": len(L), "ptr_len": len(P), "lvl_sha256": hashlib.sha256(L).hexdigest(),
                  "ptr_sha256": hashlib.sha256(P).hexdigest(), "new_slots": [hex(x) for x in new_slots],
                  "tx": m["txs"], "position": s["WPOS"][v]}
    r2, text2, _ = p1.compile_plan("s22_neutral_again", [("g5p2a.s22.neutral", [igm(22, "neutral")])])
    t1 = (WORK / "roots" / "s22_neutral" / "cache" / rm.PLAN_NAME).read_text(encoding="utf-8")
    strip = lambda t: [re.sub(r"roots\\[^\\]+\\", "", ln) for ln in t.splitlines() if not ln.startswith("#")]  # noqa
    res["O2_deterministic"] = strip(t1) == strip(text2)
    # O5 memory budget
    _, tx13 = compiled(13, "neutral")
    _, tx22 = compiled(22, "neutral")
    m13, m22 = tx13["info"]["memory"], tx22["info"]["memory"]
    res["O5_budget_values"] = (m13["area_growth"] == 112 and m22["area_growth"] == 96
                               and m13["free_after_load"] == FREE0 - 112 and m22["free_after_load"] == FREE0 - 96
                               and m13["temporary_bound"] == 4 * (112 + 209140 + 8 * 495)
                               and m22["temporary_bound"] == 4 * (96 + 209140 + 8 * 495)
                               and min(m13["headroom"], m22["headroom"]) > 0 and m13["preread"] <= 8474200)
    det["memory"] = {"13": m13, "22": m22}
    saved = json.loads(json.dumps(rm.STRUCT_MEMORY))
    try:
        rm.STRUCT_MEMORY["intro_10"]["free_after_load"] = 852848 + rm.STRUCT_MEMORY_MARGIN + 111   # 1 byte short
        res["O5_insufficient_free_refused"] = refused(lambda: rm.compile_insert_graph_node(
            igm(13, "neutral"), {"game": g3a.GAME}), "BUDGET") is True
        rm.STRUCT_MEMORY["intro_10"]["free_after_load"] = 852848 + rm.STRUCT_MEMORY_MARGIN + 112   # exactly enough
        res["O5_exact_budget_accepted"] = refused(lambda: rm.compile_insert_graph_node(
            igm(13, "neutral"), {"game": g3a.GAME}), "BUDGET") is False
        rm.STRUCT_MEMORY["intro_10"] = dict(saved["intro_10"], preread_verified=7661900)
        res["O5_preread_refused"] = refused(lambda: rm.compile_insert_graph_node(
            igm(22, "neutral"), {"game": g3a.GAME}), "BUDGET") is True
        del rm.STRUCT_MEMORY["intro_10"]
        res["O5_unmeasured_level_refused"] = refused(lambda: rm.compile_insert_graph_node(
            igm(22, "neutral"), {"game": g3a.GAME}), "BUDGET") is True
    finally:
        rm.STRUCT_MEMORY.clear()
        rm.STRUCT_MEMORY.update(saved)
    res["O5_budget_restored"] = rm.STRUCT_MEMORY == saved
    res["O5_overflow_and_alignment"] = all(refused(lambda a=a: rm.structural_budget(LEVEL, *a, "t"), "BUDGET") is True
                                           for a in ((SIZE, SIZE + 2, 209140, 495), (SIZE, 1 << 31, 209140, 495),
                                                     (SIZE, SIZE - 4, 209140, 495), (SIZE, SIZE + 96, -1, 495)))
    # O6 negative rejection (site 22 specific; G5-P1's list re-ran above)
    ix = rm.read_script_index(g3a.GAME, LEVEL)
    entry = ix["graphs"][(rm.FLY10, 0, 0)]
    pos = s["WPOS"]["neutral"]

    def put(buf, o, val):
        x = bytearray(buf)
        struct.pack_into(">I", x, o, val)
        return bytes(x)

    def b22(lvl=data, p=ptr):
        return lambda: rm.build_insert_node(lvl, p, 1, entry, 22, pos, "t")
    n0 = u32(ptr, 0)
    other = next(o for o in range(0x100, SIZE, 4) if o not in ix["slots"] and u32(data, o) == 0)
    extra_ref = put(data, other, s["B"] - 4)
    extra_ptr = struct.pack(">I", n0 + 1) + ptr[4:4 + 8 * n0] + struct.pack(">iI", 1, other - 4) + ptr[4 + 8 * n0:]
    six = [
        ("O6_wrong_site_after_21", lambda: rm.compile_insert_graph_node(igm(22, "neutral") | {"after_node": 21},
                                                                        {"game": g3a.GAME}), "UNSUPPORTED"),
        ("O6_wrong_site_after_23", lambda: rm.compile_insert_graph_node(igm(22, "neutral") | {"after_node": 23},
                                                                        {"game": g3a.GAME}), "UNSUPPORTED"),
        ("O6_wrong_lvl_hash_site22", lambda: rm.compile_insert_graph_node(igm(22, "neutral") | {"lvl_sha256": "0" * 64},
                                                                          {"game": g3a.GAME}), "TARGET_CHANGED"),
        ("O6_wrong_ptr_hash_site22", lambda: rm.compile_insert_graph_node(igm(22, "neutral") | {"ptr_sha256": "0" * 64},
                                                                          {"game": g3a.GAME}), "TARGET_CHANGED"),
        ("O6_position_far_site22", lambda: rm.compile_insert_graph_node(
            igm(22, "neutral") | {"position": [pos[0], pos[1] + 17, pos[2]]}, {"game": g3a.GAME}), "UNSUPPORTED"),
        ("O6_malformed_count", b22(lvl=put(data, g3b.COUNT_AT, 144)), "STRUCTURE_CHECK"),
        ("O6_malformed_next_link", b22(lvl=put(data, s["A"], s["A"] - 4)), "STRUCTURE_CHECK"),
        ("O6_malformed_arc_target", b22(lvl=put(data, s["ARC"] + 0xC, s["A"] - 4)), "STRUCTURE_CHECK"),
        ("O6_arc_with_capabilities", b22(lvl=put(data, s["ARC"] + 0x10, 1)), "STRUCTURE_CHECK"),
        ("O6_extra_reference_to_successor", b22(lvl=extra_ref, p=extra_ptr), "STRUCTURE_CHECK"),
        ("O6_duplicate_slot", b22(p=put(ptr, 4 + 8 * (n0 - 1) + 4, struct.unpack_from(">iI", ptr, 4)[1])),
         "STRUCTURE_CHECK"),
    ]
    for label, fn, code in six:
        got = refused(fn, code)
        res[label] = got is True
        if got is not True:
            det.setdefault("o6", {})[label] = got
    r, text, _ = p1.compile_plan("two_sites", [("s.13", [igm(13, "neutral")]), ("s.22", [igm(22, "neutral")])])
    res["O6_two_sites_both_refused"] = ({x["id"]: x.get("code") for x in r["mods"]}
                                        == {"s.13": "STRUCTURAL_CONFLICT", "s.22": "STRUCTURAL_CONFLICT"}
                                        and text is None)
    res["O6_production_compiler_refuses_site22"] = refused(lambda: rm.parse_insert_graph_node(igm(22, "neutral"), "o"),
                                                           "UNSUPPORTED", env=None) is True
    # O7 compatibility: fixed-size + site 22 compose; the production header and VS.sub are tested by negtest / M36
    r, text, _ = p1.compile_plan("s22_with_waypoint13", [("s.22", [igm(22, "neutral")]), ("w.13", [p1.waypoint13()])])
    res["O7_site22_with_fixed_size_composes"] = r["active"] == ["s.22", "w.13"] and text is not None
    res["O7_game_files_unchanged"] = g3a.files() == (data, ptr)
    out = {"checks": res, "pass": all(res.values()), "details": det}
    (WORK / "offline_p2a.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"failed": [k for k, x in res.items() if not x], "passed": sum(res.values()),
                      "total": len(res), "pass": out["pass"]}, indent=1))
    return 0 if out["pass"] else 1


# --- deterministic runtime test --------------------------------------------------------------------------------

def negtest():
    rc1 = p1.negtest()          # G5-P1's 30 + 5 cases (node 13), into private/work/e477/negtest
    nd = WORK / "negtest"
    _, text, _ = p1.compile_plan("neg_s22", [("g5p2a.s22.neutral", [igm(22, "neutral")])])
    base = p1.parse_plan(text)
    im = p1.images(base)
    _, tx = compiled(22, "neutral")
    assert im["intro_10.lvl"] == tx["images"]["lvl"] and im["intro_10.ptr"] == tx["images"]["ptr"]
    (nd / "s22_lvl.bin").write_bytes(im["intro_10.lvl"])
    (nd / "s22_ptr.bin").write_bytes(im["intro_10.ptr"])
    li = next(i for i, f in enumerate(base["files"]) if f["path"].endswith("intro_10.lvl"))
    pi = 1 - li

    def variant(name, fn=None):
        m = json.loads(json.dumps(base))
        if fn:
            fn(m)
        p = nd / f"plan_s22_{name}.txt"
        p.write_text(p1.emit(m), encoding="utf-8")
        return p

    def tamper(m, i, ri):
        off, length, gb, nb, mid, blob = m["files"][i]["range"][ri].split(" ", 5)
        b = bytearray(Path(blob).read_bytes())
        b[len(b) // 2] ^= 0x33
        q = nd / f"s22_tampered_{i}_{ri}.bin"
        q.write_bytes(bytes(b))
        m["files"][i]["range"][ri] = " ".join([off, length, gb, f"{fnv(bytes(b)):016x}", mid, str(q)])

    def retx(m, i, k, v):
        t = m["files"][i]["tx"][0].split(" ")
        t[k] = v
        m["files"][i]["tx"][0] = " ".join(t)
    plans = {
        "valid": variant("valid"),
        "missing_lvl": variant("missing_lvl", lambda m: m["files"].pop(li)),
        "missing_ptr": variant("missing_ptr", lambda m: m["files"].pop(pi)),
        "tampered_ptr": variant("tampered_ptr", lambda m: tamper(m, pi, 0)),
        "tampered_tail": variant("tampered_tail", lambda m: tamper(m, li, 4)),
        "wrong_lvl_sha": variant("wrong_lvl_sha", lambda m: retx(m, li, 1, "0" * 64)),
        "partial": variant("partial", lambda m: m["files"][li].update(
            range=[r for r in m["files"][li]["range"] if int(r.split(" ")[0]) >= SIZE])),
        "corrupt_id": variant("corrupt_id", lambda m: m.update(
            txs=[m["txs"][0][:-1] + ("0" if m["txs"][0][-1] != "0" else "1")])),
        "node13_size_for_site22": variant("node13_size", lambda m: (retx(m, li, 2, str(SIZE + 112)),
                                                                    m["files"][li].update(grow=[str(SIZE + 112)]))),
    }
    O = ("-", "-")
    V = (nd / "s22_lvl.bin", nd / "s22_ptr.bin")
    lvl_p, ptr_p = str(g3a.LVL), str(g3a.PTR)
    dev = [("site 22 valid, .lvl first", "valid", LEVEL, "active", "lvl,ptr", V),
           ("site 22 valid, .ptr first", "valid", LEVEL, "active", "ptr,lvl", V),
           ("site 22 not enabled (.lvl first)", "valid", "-", "level_tx_not_enabled", "lvl,ptr", O),
           ("site 22 not enabled (.ptr first)", "valid", "-", "level_tx_not_enabled", "ptr,lvl", O),
           ("site 22 missing .lvl", "missing_lvl", LEVEL, "tx_incomplete", "ptr,lvl", O),
           ("site 22 missing .ptr", "missing_ptr", LEVEL, "tx_incomplete", "lvl,ptr", O),
           ("site 22 tampered .ptr, rehashed", "tampered_ptr", LEVEL, "tx_result_hash", "ptr,lvl", O),
           ("site 22 tampered tail, rehashed", "tampered_tail", LEVEL, "tx_result_hash", "lvl,ptr", O),
           ("site 22 wrong original .lvl hash", "wrong_lvl_sha", LEVEL, "tx_identity", "lvl,ptr", O),
           ("site 22 partial (edited words dropped)", "partial", LEVEL, "tx_result_hash", "lvl,ptr", O),
           ("site 22 corrupted id", "corrupt_id", LEVEL, "tx_id", "lvl,ptr", O),
           ("site 22 declared size of the other site", "node13_size_for_site22", LEVEL, "grow_uncovered",
            "lvl,ptr", O)]
    prod = [("production: site 22 transaction (.lvl first)", "valid", LEVEL, "unknown_record", "lvl,ptr", O),
            ("production: site 22 transaction (.ptr first)", "valid", LEVEL, "unknown_record", "ptr,lvl", O)]
    out = {}
    for kind, cases in (("dev", dev), ("prod", prod)):
        exe = WORK / "negtest" / f"g5p1_tx_test_{kind}.exe"
        cf = nd / f"cases_s22_{kind}.tsv"
        cf.write_text("".join("\t".join([n, str(plans[p]), env, want, order, lvl_p, ptr_p, str(e[0]), str(e[1])])
                              + "\n" for n, p, env, want, order, e in cases), encoding="utf-8")
        r = subprocess.run([str(exe), str(cf)], capture_output=True, text=True, timeout=600)
        (nd / f"result_s22_{kind}.txt").write_text(r.stdout + r.stderr)
        print(r.stdout)
        out[kind] = {"exit": r.returncode, "summary": r.stdout.strip().splitlines()[-1] if r.stdout else ""}
    g = json.loads((nd / "summary.json").read_text())
    out["g5p1"] = g
    ok = rc1 == 0 and all(v["exit"] == 0 for k, v in out.items() if k != "g5p1")
    (nd / "summary_p2a.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out), "NEGTEST_P2A", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# --- hidden runs ---------------------------------------------------------------------------------------------------

_SITE = {"after": None}


def bind(after):
    """Point G3b's runner at one site (constants used by g3b_ab.run_case: N, CHANGED, NODE13, WP13, WP14)."""
    s = site(after)
    _, tx = compiled(after, "neutral")
    g3b.PREFIX = PREFIX
    g3b.GATE_ENV = (ENV, LEVEL)
    g3b.N = len(tx["images"]["lvl"]) - SIZE
    g3b.CHANGED = s["changed"]
    g3b.NODE13, g3b.NODE14, g3b.WP13, g3b.WP14 = s["A"], s["B"], s["WA"], s["WB"]
    g3b.write_plan = plan_for_run
    _SITE["after"] = after
    os.environ.pop("R3HD_G3A_TEST_GROW", None)
    os.environ.pop(ENV, None)


def plan_for_run(work, data, ptr, variant):
    after = _SITE["after"]
    mid = f"g5p2a.s{after}.{variant}"
    res, text, paths = p1.compile_plan(f"run_{work.parent.name}_{work.name}", [(mid, [igm(after, variant)])])
    if text is None or res["active"] != [mid]:
        raise SystemExit(f"compiler refused the run's mod: {res['mods']}")
    plan = paths["cache"] / rm.PLAN_NAME
    shutil.copyfile(plan, work / "plan_copy.txt")
    return plan


RUNS_PLAN = [("b13", 13, "neutral"), ("s22", 22, "neutral"), ("s22", 22, "offset"), ("s22", 22, "nogate")]


def run(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    for sub, after, case in RUNS_PLAN:
        bind(after)
        print(json.dumps(g3b.run_case(f"{tag}_{sub}", case)), flush=True)
    return 0


def load(work, run):
    row = json.loads((work / "row.json").read_text())
    for k in ("states", "tails", "samples"):
        row[k] = json.loads((work / f"{k}.json").read_text())
    log = "\n".join(q.read_text(errors="replace") for q in sorted((g3a.RUNS / run).glob("runtime*.log")))
    row["log"] = log
    row["grow_size"] = sorted(set(re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)))
    row["grow_reads"] = re.findall(r"M36 grow read file=(\S+) offset=(\d+) length=(\d+) host=(\d+) served=(\d+)"
                                   r" kind=(\S+)", log)
    row["served_files"] = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
    row["tx_lines"] = re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log)
    row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
    judges = {}
    for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True, text=True)
        judges[tool] = r.returncode
    row["judges"] = judges
    pc = work / "plan_copy.txt"
    row["plan_tx"] = None
    if pc.is_file():
        t = p1.parse_plan(pc.read_text(encoding="utf-8"))["txs"]
        row["plan_tx"] = [tuple(t[0].split(" ")[2:5])] if t else None
    return row


def judge(tag):
    data, ptr = g3a.files()
    A = load(A_WORK, A_RUN)
    rows = {"A": A}
    for role, (sub, case) in {"B": ("b13", "neutral"), "C": ("s22", "neutral"), "D": ("s22", "offset"),
                              "E": ("s22", "nogate")}.items():
        rows[role] = load(WORK / f"{tag}_{sub}" / case, f"{PREFIX}_{tag}_{sub}_{case}")
        rows[role]["_case"] = case
    S = {13: site(13), 22: site(22)}
    for after in (13, 22):
        _, tx = compiled(after, "neutral")
        S[after]["tail"] = len(tx["images"]["lvl"]) - SIZE
        S[after]["FN"] = tx["info"]["objects"]["node"]
        S[after]["FW"] = tx["info"]["objects"]["waypoint"]
        S[after]["mem"] = tx["info"]["memory"]
        S[after]["slots"] = [S[after]["FN"] + k for k in (0, 4, 8, 0xC, 0x18)] + \
            [tx["info"]["objects"]["list"], tx["info"]["objects"]["list"] + 4,
             tx["info"]["objects"]["arc"] + 8, tx["info"]["objects"]["arc"] + 0xC]
    role_site = {"B": 13, "C": 22, "D": 22, "E": 22}
    variant = {"B": "neutral", "C": "neutral", "D": "offset"}

    def ab(r):
        return int(r["area"]["base"], 16) if r.get("area") else None
    det, P = {}, {}
    # invalid conditions
    invalid = [k for k, r in rows.items() if r.get("error") or not r["samples"]
               or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60]
    for k in ("B", "C", "D", "E"):
        w = S[role_site[k]]["wa"]
        t_close = min(A["samples"], key=lambda q: math.dist(q["pos"], w))["t"]
        if rows[k]["samples"] and rows[k]["samples"][0]["t"] >= t_close and k not in invalid:
            invalid.append(k)
    shas = {k: r.get("original_readback_sha256") for k, r in rows.items()}

    def tail_check(k):
        s, r, base = S[role_site[k]], rows[k], ab(rows[k])
        _, tx = compiled(role_site[k], variant[k])
        exp = bytearray(tx["images"]["lvl"][SIZE:])
        for sl in s["slots"]:
            o = sl - SIZE
            struct.pack_into(">I", exp, o, (u32(exp, o) + base) & 0xFFFFFFFF)
        free = set(range(s["FN"] - SIZE + 0x10, s["FN"] - SIZE + 0x18))

        def fixed(h):
            b = bytes.fromhex(h) if h else b""
            return len(b) == s["tail"] and all(b[i] == exp[i] for i in range(s["tail"]) if i not in free)
        ts = r["tails"]
        out = {"reads": len(ts), "all": all(fixed(t["hex"]) for t in ts), "span": round(ts[-1]["t"] - ts[0]["t"], 2)
               if ts else 0, "live": all(fixed((r.get(x) or {}).get("tail")) for x in ("live_first", "live_end"))}
        out["ok"] = out["reads"] >= 55 and out["all"] and out["span"] >= 55 and out["live"]
        return out

    def resource(k):
        s, r = S[role_site[k]], rows[k]
        want = sorted([("intro_10.lvl", str(SIZE), str(SIZE + s["tail"])), ("intro_10.ptr", str(PSIZE),
                                                                           str(PSIZE + 72))])
        tc = tail_check(k)
        wp_ok = (r.get("live_end") or {}).get("orig_wp") == [data[w:w + 0x14].hex() for w in (s["WA"], s["WB"])]
        ok = ("M33 mods state=active" in r["log"] and r["tx_lines"] == r["plan_tx"] and r["plan_tx"]
              and r["grow_size"] == want and r["served_files"] == ["intro_10.lvl", "intro_10.ptr"]
              and {x[0] for x in r["grow_reads"]} == {"intro_10.lvl", "intro_10.ptr"}
              and all(x[5] == "tail" for x in r["grow_reads"]) and shas[k] == shas["A" if role_site[k] == 13 else "E"] and shas[k] and tc["ok"] and wp_ok)
        det[f"resource_{k}"] = {"grow_size": r["grow_size"], "tx": r["tx_lines"], "tail": tc, "orig_wp": wp_ok}
        return bool(ok)

    def reloc(k, grown=True):
        s, r, base = S[role_site[k]], rows[k], ab(rows[k])
        want = ([base + s["FN"] - 4] * 3 + [144]) if grown else ([base + v for v in s["changed"].values()] + [143])
        got = [(r.get(x) or {}).get("changed") for x in ("live_first", "live_end")]
        det[f"reloc_{k}"] = {"want": want, "got": got}
        return all(g == want for g in got)

    def regist(k, grown=True):
        s, r, base = S[role_site[k]], rows[k], ab(rows[k])
        ok = bool(base)
        idx = s["after"] + 1
        for x in ("live_first", "live_end"):
            gr = (r.get(x) or {}).get("graph") or {}
            nodes = gr.get("nodes") or []
            a_nodes = ((A.get(x) or {}).get("graph") or {}).get("nodes") or []
            if grown:
                ok = ok and gr.get("problems") == [] and len(nodes) == 144 == len(set(nodes)) \
                    and nodes[idx] == base + s["FN"] - 4 and nodes[:idx] + nodes[idx + 1:] == a_nodes \
                    and gr["header"]["first"] == A[x]["graph"]["header"]["first"] \
                    and gr["header"]["last"] == A[x]["graph"]["header"]["last"] \
                    and gr.get("arc13") == {"count": 1, "target": base + s["FN"] - 4}
            else:
                ok = ok and gr.get("problems") == [] and nodes == a_nodes
        return ok

    near = lambda p, q: all(abs(p[i] - q[i]) <= 1e-4 for i in range(3))   # noqa: E731

    def visits(k, grown=True):
        s, r, base = S[role_site[k]], rows[k], ab(rows[k]) or 0
        wn, wa, wb = base + s["FW"] - 4, base + s["WA"] - 4, base + s["WB"] - 4
        sm = r["samples"]
        at = [x for x in sm if x["v8"] == wn]
        ins = [(sm[i - 1]["v8"], sm[i]["v8"]) for i in range(1, len(sm)) if sm[i]["v8"] != sm[i - 1]["v8"]]
        into = [a for a, b in ins if b == wn]
        outof = [b for a, b in ins if a == wn]
        v = {"samples": len(at), "into": len(into), "into_from_site": sum(a == wa for a in into), "out": len(outof),
             "out_to_next": sum(b == wb for b in outof)}
        det[f"visits_{k}"] = v | {"v10": sorted({tuple(round(c, 4) for c in x["v10"]) for x in at})}
        if not grown:
            return v["samples"] == 0
        return (v["samples"] >= 3 and v["into"] >= 2 and v["into"] == v["into_from_site"] and v["out"] >= 2
                and v["out"] == v["out_to_next"] and any(near(x["v10"], s["WPOS"][variant[k]]) for x in at))

    def alloc(k):
        r = rows[k]
        s = S[role_site.get(k, 13)]
        grown = k in ("B", "C", "D")
        L = AREA + (s["tail"] if grown else 0)
        st = r["states"]
        i = next((j for j, x in enumerate(st) if "invalid" not in x), None)
        walk_ok = i is not None and not any("invalid" in x for x in st[i:])
        used = [q for q in st if "invalid" not in q and "1" in q.get("areas", {})]
        free = used[-1]["free_bytes"] if used else None
        ok = (walk_ok and (r.get("area") or {}).get("length") == L and r["area"]["words"] == bp.words_for(L)
              and bool(used) and all(q["areas"]["1"]["length"] == L for q in used)
              and free == FREE0 - (s["tail"] if grown else 0))
        if grown:
            ok = ok and free - s["mem"]["temporary_bound"] >= rm.STRUCT_MEMORY_MARGIN
        det[f"alloc_{k}"] = {"length": (r.get("area") or {}).get("length"), "free_after": free, "walk_ok": walk_ok}
        return bool(ok)

    def path_of(r, start):
        return [q["pos"] for q in r["samples"] if q["t"] >= start]

    def maxdev(r, path, start, M, region=None, inside=None):
        o = [(g3a.to_path(q, path), q) for q in path_of(r, start)]
        if region is not None:
            o = [x for x in o if (math.dist(x[1], M) > region) != bool(inside)]
        return max(o, key=lambda x: x[0][0]) if o else None

    def closest(r, start, target):
        q = path_of(r, start)
        return g3a.to_path(target, q)[0] if len(q) > 1 else None
    geo = {}
    if not invalid:
        start = max(r["samples"][0]["t"] for r in rows.values()) + 0.5
        pa = path_of(A, start - 1.0)
        pc = path_of(rows["C"], start - 1.0)
        M13, M2, M2p = S[13]["M"], S[22]["M"], S[22]["MP"]
        fB, fBo = maxdev(rows["B"], pa, start, M13), maxdev(rows["B"], pa, start, M13, 25)
        fC, fCo = maxdev(rows["C"], pa, start, M2), maxdev(rows["C"], pa, start, M2, 25)
        fE = maxdev(rows["E"], pa, start, M2)
        fD, fDo, fDC = maxdev(rows["D"], pa, start, M2), maxdev(rows["D"], pa, start, M2, 25), \
            maxdev(rows["D"], pc, start, M2)
        geo = {"B": {"max_off_A": round(fB[0][0], 3), "at_dist_to_M": round(math.dist(fB[1], M13), 2),
                     "outside_25": round(fBo[0][0], 3) if fBo else 0.0,
                     "closest_to_M": round(closest(rows["B"], start, M13), 3)},
               "C": {"max_off_A": round(fC[0][0], 3), "at_dist_to_M2": round(math.dist(fC[1], M2), 2),
                     "outside_25": round(fCo[0][0], 3) if fCo else 0.0,
                     "closest_to_M2": round(closest(rows["C"], start, M2), 3),
                     "closest_to_M2p": round(closest(rows["C"], start, M2p), 3)},
               "E": {"max_off_A": round(fE[0][0], 3)},
               "D": {"max_off_A": round(fD[0][0], 3), "at_dist_to_M2": round(math.dist(fD[1], M2), 2),
                     "toward_M2p": sum((fD[1][i] - fD[0][1][i]) * (M2p[i] - M2[i]) for i in range(3)) > 0,
                     "outside_25": round(fDo[0][0], 3) if fDo else 0.0, "max_off_C": round(fDC[0][0], 3),
                     "closest_to_M2p": round(closest(rows["D"], start, M2p), 3)},
               "A": {"closest_to_M": round(closest(A, start, M13), 3), "closest_to_M2": round(closest(A, start, M2), 3),
                     "closest_to_M2p": round(closest(A, start, M2p), 3)}}
    g = geo
    P["P1_resource"] = all(resource(k) for k in ("B", "C", "D"))
    P["P2_relocation"] = all(reloc(k) for k in ("B", "C", "D")) and reloc("E", grown=False)
    P["P3_registration"] = all(regist(k) for k in ("C", "D")) and regist("E", grown=False)
    P["P4_consumption"] = visits("C") and visits("D") and visits("E", grown=False)
    P["P5_original_site"] = (bool(g) and resource("B") and reloc("B") and regist("B") and visits("B")
                             and g["B"]["max_off_A"] <= TOL_NEAR[13] and g["B"]["outside_25"] <= 0.5)
    P["P6_second_site_effect"] = bool(g) and (
        g["C"]["max_off_A"] <= TOL_NEAR[22] and g["C"]["outside_25"] <= 0.5 and g["E"]["max_off_A"] <= 0.5
        and g["D"]["max_off_A"] >= 1.5 and g["D"]["at_dist_to_M2"] <= 25 and g["D"]["toward_M2p"] is True
        and g["D"]["closest_to_M2p"] <= g["A"]["closest_to_M2p"] - 1.0
        and g["D"]["closest_to_M2p"] <= g["C"]["closest_to_M2p"] - 1.0
        and g["D"]["max_off_C"] >= 1.5 and g["D"]["outside_25"] <= 0.5)
    P["P7_memory"] = all(alloc(k) for k in rows)
    E = rows["E"]
    off = json.loads((WORK / "offline_p2a.json").read_text())
    neg = json.loads((WORK / "negtest" / "summary_p2a.json").read_text())
    neg_ok = all(v["exit"] == 0 for k, v in neg.items() if k != "g5p1") and all(
        v["exit"] == 0 for v in neg["g5p1"].values())
    P["P8_transaction_desktop"] = (
        "state=refused reason=level_tx_not_enabled" in E["log"] and "M36 grow" not in E["log"]
        and "M33 mods served" not in E["log"] and not E["tx_lines"] and off["pass"] and neg_ok
        and all(r["haptics_policy"] and not any(r["judges"].values()) and r["runner_exit"] == 0
                and not r["process_left"] for r in rows.values()))
    out = {"invalid": invalid, "P": P, "pass": not invalid and all(P.values()), "geometry": geo, "details": det,
           "readback": shas, "judges": {k: r["judges"] for k, r in rows.items()},
           "runner_exit": {k: r["runner_exit"] for k, r in rows.items()}}
    (WORK / f"judgement_{tag}.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({k: out[k] for k in ("invalid", "P", "pass", "geometry")}, indent=1))
    return 0 if out["pass"] else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return check()
    if len(sys.argv) > 1 and sys.argv[1] == "negtest":
        return negtest()
    if len(sys.argv) > 2 and sys.argv[1] == "judge":
        return judge(sys.argv[2])
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]{1,24}", a.tag):
        ap.error("bad tag")
    return run(a.tag)


if __name__ == "__main__":
    sys.exit(main())
