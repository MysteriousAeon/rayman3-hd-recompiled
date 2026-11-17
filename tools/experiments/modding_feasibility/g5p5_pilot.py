#!/usr/bin/env python3
"""E-482 (D-249) G5-P5: two `insert-graph-node` operations of ONE development-only mod, compiled into ONE level
transaction of intro_10 (flight graph of NIN_m_GenFlyIntro_10 instance 0, designer variable 0): a new node after
original node 13 (new_A) and one after original node 22 (new_B); 143 -> 145 nodes.

usage:
  g5p5_pilot.py check        offline O1-O7 (real game files read-only; no game started)
  g5p5_pilot.py negtest      O8: runtime transaction cases (g5p1_tx_test.cpp, development and production headers)
                             with the dual plan, G5-P2a's negtest re-run, G5-P3's integrity tests at the dual sizes
  g5p5_pilot.py TAG          hidden runs B, C, D (development build)
  g5p5_pilot.py judge TAG    P1-P8 (A = the retained E-476 run p1 base, as G5-P2a)
Outputs stay under private/work/e482/.

COMBINATION SEMANTICS (compiler, tools/r3hd_mods.py compile_insert_graph_nodes / build_insert_nodes)
  Sites are named by ORIGINAL node index (after_original_node_13, after_original_node_22) and validated against the
  ORIGINAL files; the compiler sorts operations by that index, so manifest order cannot change any byte. Same graph
  and same file hashes required; duplicate sites, more than STRUCT_MAX_OPS (intro_10: 2), adjacent sites (|a - b| < 2)
  and any invalid operation refuse the whole mod before anything is built. One allocator: objects past the file's
  end, site by site in graph order, each in its source object's 16-byte phase; one count edit (143 -> 145); one
  pointer table with the 9 + 9 new own-file entries appended in site order; the cross-file table moved once.
EXPECTED LAYOUT (derived by hand from the single-site layouts and the allocator rule; `check` verifies it against an
  independent construction: G3b's hand-built site 13 plus a hand-built site 22, not the compiler):
  site 13: node 7,661,840 (+4), waypoint +44, list +64, arc +76 (as G3b / G5-P1); the allocator then stands at +108,
  phase 8; node 22's source phase is 12, so site 22: node +112 = 7,661,948, waypoint +140, list +160, arc +172, end
  +204 -> tail 208 bytes (= 112 + 96 here because 112 is a multiple of 16 and every phase lines up; derived, not
  assumed). .ptr 25,143 -> 25,161 own-file entries, 209,068 -> 209,212 bytes. Edited words (7): node 13 +0, node 14
  +4, node 13's arc +0xC, node 22 +0, node 23 +4, node 22's arc +0xC, graph +8 (143 -> 145).
  Logical order: original 0..13, new_A, original 14..22, new_B, original 23..142 (new_A index 14, new_B index 24).
  Memory (compiler budget): area growth 208, free after load 13,088,528 - 208 = 13,088,320, temporary bound 4 x (208
  + 209,212 + 8 x 495) = 853,520, headroom 11,186,224 >= 0 beyond the 1 MiB margin; pre-read 7,662,044 <= 8,474,200.
POSITIONS: neutral = (M, M2) = the midpoints of waypoints 13/14 and 22/23 (G3b, G5-P2a); offset = (M', M2') = each
  midpoint + 6 units horizontally perpendicular to its segment (G3b's and G5-P2a's rule).

OFFLINE (check): O1 single-site output byte-identical to the G5-P4b compiler (git 2315d6b) for sites 13 / 22
  (neutral, offset) and intro_20 site 3, and G5-P1's, G5-P2a's and G5-P4a's checks re-run; O2 topology (independent
  relocation model g3a.relocate + the game's walk g3b.walk_null: 145 distinct, order as above, arcs, waypoints, the
  independent construction byte-identical); O3 relocation (18 entries unique, in bounds, file 1, each target as
  planned; originals and cross-file table intact; only the 7 words changed); O4 determinism (manifest order reversed
  -> identical plan, images and id); O5 atomic rejection (invalid second operation in many forms refuses the whole
  mod; no tx, no intro_10 growth); O6 conflicts (two structural mods both refused; disjoint fixed-size composes;
  overlap with a site-22 word and with the count word in both priority orders refuses the lower side whole; the
  active images are the canonical ones; gameplay marked; production / other-level refusal); O7 memory (values above;
  one byte short, pre-read, growth caps and unmeasured level refused; exact budget accepted).
  O8 (negtest): dual plan through the development header (valid in both open orders, gate off, missing members,
  tampered / partial / wrong hash / id / size) and the production header (unknown_record); G5-P2a's negtest (G5-P1's
  30 + 5 and site 22's cases); G5-P3's integrity tests with 208 / 144-byte growth (snapshot, repeated opens, host
  changes, reversed order; pre-registered G5-P3 expectations unchanged).

PROSPECTIVE PROTOCOL (committed before any modified run)
Build: g5p1_dev_gate.py apply + tools\\build_incremental.bat; production restored after (revert + rebuild).
Runs: G3b's runner (g3b_ab.run_case, unchanged) bound to the dual site: hidden, non-activating, muted, no physical pad,
  private user root, `--test-level intro_10`, no input, no captures, 150 s, generator sampled every 0.1 s for 75 s,
  tail (208 bytes) read every 1 s; the 7 edited words masked in the read-back hash.
  A: NOT re-run: the retained E-476 run p1 base (no plan, same game files, same runner; reused by G5-P2a). A no-plan
     run does not reach the transaction code, so the later gate edits (G5-P3 snapshot) cannot change it; D (same
     build, plan refused) is the fresh same-build control.
  B: dual neutral (compiler plan, R3HD_DEV_STRUCTURAL_TX=intro_10).  C: dual offset.  D: C's plan, variable unset.
Criteria (constants from `check`, not from a run):
  P1 transaction integrity (B, C): one `M33 mods state=active`; exactly one `G5P1 level-tx active` = the plan's
     (level, mod, id); `G5P3 tx snapshot` intro_10.lvl image_bytes 7662044 and intro_10.ptr 209212, disk_reads=2;
     `M36 grow size` exactly 7661836 -> 7662044 and 209068 -> 209212; `M33 mods served` only those two files; no
     `G5P3 tx host_changed`; masked read-back of the original area equal to D's (same mask and build, nothing served);
     tail fixed bytes (all but both new nodes' +0x10..+0x17) = the compiler's tail relocated by the live base at >= 55
     reads over >= 55 s and at both live reads; the four original site waypoints unchanged at the end.
  P2 graph registration (B, C; both live reads): walk of 145 distinct nodes without problems, header count 145;
     new_A at index 14 and new_B at index 24; the rest = A's 143 in order; first / last as A; the 6 redirected words
     = [new_A] x 3 + [new_B] x 3 relocated; node 13's arc list {count 1, target new_A}. D: A's 143, original words.
  P3 first insertion consumed (B, C): generator variable 8 = new_A's waypoint address in >= 3 samples, >= 2 visits,
     every entry from node 13's waypoint, every exit to node 14's; variable 10 there = the planned position (1e-4).
  P4 second insertion consumed (B, C): the same for new_B between node 22's and node 23's waypoints.  D: neither.
  P5 neutral (B): max distance from A's path <= 1.0 within 25 units of M, <= 1.7 within 25 units of M2, <= 0.5
     outside both regions; D <= 0.5 everywhere. Inputs: G3b k1 / E-476 p1 neutral 0.586 / 0.587 (threshold 1.0, G3b
     N6); E-477 q2 site-22 neutral 0.701 (threshold 1.7 pre-registered there); outside 0.193-0.198; gate off 0.06 /
     0.099 (isolation 0.5, E-464). The two regions are 81.8 units apart, so each site keeps its own bound.
  P6 offset (C): in each region (25 units of M, of M2) C's max distance from A >= 1.5 at a sample displaced toward
     M' (resp. M2'), and >= 1.5 from B's path; closest approach to M' (M2') <= 1.0 less than A's and than B's; <= 0.5
     from A outside both regions. Inputs: E-476 p1 offset 3.959 (closest to M' 3.695 vs A 6.81), E-477 q2 site-22
     offset 3.183 (2.339 vs 5.009), outside 0.226 / 0.251; G3b's thresholds 1.5 / 1.0 kept.
  P7 memory and lifecycle (every run): valid block-8 walks in every snapshot after the first valid one; level area
     length 7,661,832 + 208 (B, C) / 7,661,832 (D), chunk words words_for(length), every later snapshot the same;
     free after load = 13,088,528 - 208 = 13,088,320 (B, C) / 13,088,528 (D) (no other allocation difference); free
     after load - the compiler's temporary bound 853,520 >= the 1 MiB margin; G5P3 snapshot image bytes 7,662,044 +
     209,212 (the validated sizes; no other image kept).
  P8 rejection and desktop safety: D `state=refused reason=level_tx_not_enabled`, no `M36 grow`, no `M33 mods served`,
     no `G5P1` / `G5P3` line; `check` and `negtest` passed; every run: M21 / M22 / M23 0, haptics policy line, runner
     exit 0, game_foreground_events = game_foreground_samples = 0 in run.json (G5-P4b rule), no game process left.
  Invalid (new tag, not judged): file hashes differ, level not opened, area / generator not found, < 60 s of samples,
  a run's first sample after A's closest approach to node 13's waypoint.
  All eight = G5-P5 VERIFIED — MULTI-OPERATION STRUCTURAL TRANSACTION; P3 xor P4 failing = PARTIAL.
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
import g5p2a_pilot as p2  # noqa: E402
import g5p4a_pilot as p4  # noqa: E402

PREFIX = "e482"
WORK = ROOT / "private" / "work" / PREFIX
p1.WORK = WORK
LEVEL = p1.LEVEL
ENV = rm.STRUCT_ENV
u32, fnv = g3a.u32, g3a.fnv
SIZE, PSIZE, AREA, FREE0 = g3a.SIZE, g3a.PSIZE, g3a.AREA, g3a.FREE0
A_WORK, A_RUN = ROOT / "private" / "work" / "e476" / "p1" / "base", "e476_p1_base"
BASELINE = "2315d6b"
MOD = "g5p5.dual"
TAIL, PGROW = 208, 144
PLACE = {13: {"node": SIZE + 4, "waypoint": SIZE + 44, "list": SIZE + 64, "arc": SIZE + 76},
         22: {"node": SIZE + 112, "waypoint": SIZE + 140, "list": SIZE + 160, "arc": SIZE + 172}}
TEMP_BOUND = 4 * (TAIL + PSIZE + PGROW + 8 * 495)
TOL = {13: 1.0, 22: 1.7}


def S(after):
    return p2.site(after)


def dual(variant, order=(13, 22), ch=None):
    """The dual mod's overrides, in the given manifest order; ch[after] = changes of that operation."""
    return [p2.igm(a, variant) | (ch or {}).get(a, {}) for a in order]


def compiled(variant, order=(13, 22), ch=None):
    with p1.dev_env():
        return rm.compile_insert_graph_nodes(dual(variant, order, ch), {"game": g3a.GAME})


def refused(fn, code, env=LEVEL):
    with p1.dev_env(env):
        return p1.refused(fn, code)


def new_slots(after):
    p = PLACE[after]
    return [p["node"] + k for k in (0, 4, 8, 0xC, 0x18)] + [p["list"], p["list"] + 4, p["arc"] + 8, p["arc"] + 0xC]


def construct(data, ptr, variant):
    """Independent construction (not the compiler): G3b's hand-built site 13, plus site 22 built here from the graph's
    own bytes at the hand-derived offsets; count 145; pointer table 9 + 9."""
    nl, np_, _, _ = g3b.construct(data, ptr, variant)
    s = S(22)
    L = bytearray(nl[:SIZE]) + bytearray(TAIL)
    L[SIZE:SIZE + 112] = nl[SIZE:SIZE + 112]
    p = PLACE[22]
    FN, FW, FL, FA = p["node"], p["waypoint"], p["list"], p["arc"]
    for w in s["changed"]:
        struct.pack_into(">I", L, w, FN - 4)
    struct.pack_into(">I", L, g3b.COUNT_AT, 145)
    struct.pack_into(">7I", L, FN, s["B"] - 4, s["A"] - 4, g3b.GRAPH - 4, FW - 4, 0, 0, FL - 4)
    L[FW:FW + 12] = struct.pack(">3f", *s["WPOS"][variant])
    L[FW + 12:FW + 20] = data[s["WA"] + 12:s["WA"] + 20]
    struct.pack_into(">3I", L, FL, FA - 4, FA - 4, 1)
    struct.pack_into(">8I", L, FA, 0, 0, FL - 4, s["B"] - 4, 0, 0, 0, 0)
    n0 = u32(ptr, 0)
    P = (struct.pack(">I", n0 + 18) + ptr[4:4 + 8 * n0]
         + b"".join(struct.pack(">iI", 1, x - 4) for x in new_slots(13) + new_slots(22)) + ptr[4 + 8 * n0:])
    return bytes(L), P


def old_compiler():
    """The G5-P4b compiler (git BASELINE), loaded under another module name from a private copy."""
    d = WORK / "old_compiler"
    d.mkdir(parents=True, exist_ok=True)
    src = subprocess.run(["git", "show", f"{BASELINE}:tools/r3hd_mods.py"], cwd=ROOT, capture_output=True,
                         check=True).stdout
    (d / "r3hd_mods_g5p4b.py").write_bytes(src)
    import importlib.util
    spec = importlib.util.spec_from_file_location("r3hd_mods_g5p4b", d / "r3hd_mods_g5p4b.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def redirect(sub):
    """G5-P1's / G5-P2a's / G5-P4a's helpers write under e482/<sub> (their own folders are historical evidence)."""
    w = WORK / sub
    w.mkdir(parents=True, exist_ok=True)
    p1.WORK = p2.WORK = p4.WORK = w
    return w


# --- offline -----------------------------------------------------------------------------------------------------

def check():
    data, ptr = g3a.files()
    res, det = {}, {}
    # O1 existing behaviour preserved
    old = old_compiler()
    same = {}
    for after in (13, 22):
        for v in ("neutral", "offset"):
            with p1.dev_env():
                a = rm.compile_insert_graph_node(p2.igm(after, v), {"game": g3a.GAME})
                b = old.compile_insert_graph_node(p2.igm(after, v), {"game": g3a.GAME})
            same[f"intro_10_{after}_{v}"] = (a[0] == b[0] and a[1]["images"] == b[1]["images"]
                                             and a[1]["info"] == b[1]["info"])
    for v in ("neutral", "offset"):
        with p1.dev_env("intro_20"):
            a = rm.compile_insert_graph_node(p4.igm(v), {"game": g3a.GAME})
            b = old.compile_insert_graph_node(p4.igm(v), {"game": g3a.GAME})
        same[f"intro_20_3_{v}"] = (a[0] == b[0] and a[1]["images"] == b[1]["images"]
                                   and a[1]["info"] == b[1]["info"])
    det["O1_identity"] = same
    res["O1_single_site_byte_identical_6"] = len(same) == 6 and all(same.values())
    rc = {}
    redirect("o1_g5p1")
    rc["g5p1"] = p1.check()
    redirect("o1_g5p2a")
    rc["g5p2a"] = p2.check()
    w = redirect("o1_g5p4a")
    rc["g5p4a"] = p4.check()
    redirect(".")
    p1.WORK = WORK
    det["O1_rerun"] = {k: v for k, v in rc.items()}
    det["O1_counts"] = {
        "g5p1": len(json.loads((WORK / "o1_g5p1" / "offline.json").read_text())["checks"]),
        "g5p2a": len(json.loads((WORK / "o1_g5p2a" / "offline_p2a.json").read_text())["checks"]),
        "g5p4a": len(json.loads((w / "check.json").read_text())["res"])}
    res["O1_g5p1_g5p2a_g5p4a_checks"] = all(v == 0 for v in rc.values())
    # the dual mod through the whole compiler path (installed mod -> resolve_all -> plan)
    B1 = 0x40F5509C
    base_area, _, _ = g3a.relocate(data, ptr, B1)
    rd0 = lambda a: u32(base_area, a - B1)   # noqa: E731
    nodes0, prob0, hdr0 = g3b.walk_null(rd0, B1 + g3b.GRAPH - 4)
    res["O2_original_walk_143"] = not prob0 and len(nodes0) == 143
    s13, s22 = S(13), S(22)
    plans = {}
    for v in ("neutral", "offset"):
        r, text, paths = p1.compile_plan(f"dual_{v}", [(MOD, dual(v))])
        m = p1.parse_plan(text or "")
        plans[v] = (r, text, m)
        im = p1.images(m) if text else {}
        L, P = im.get("intro_10.lvl", b""), im.get("intro_10.ptr", b"")
        IL, IP = construct(data, ptr, v)
        n0, m0, n1 = u32(ptr, 0), u32(data, 0), (u32(P, 0) if P else 0)
        area, seen, dup = g3a.relocate(L, P, B1)
        rd = lambda a, area=area: u32(area, a - B1)   # noqa: E731
        nodes, prob, hdr = g3b.walk_null(rd, B1 + g3b.GRAPH - 4)
        NA, NB = B1 + PLACE[13]["node"] - 4, B1 + PLACE[22]["node"] - 4
        want = nodes0[:14] + [NA] + nodes0[14:23] + [NB] + nodes0[23:]

        def site_ok(s, after, N):
            p = PLACE[after]
            A_, B_ = B1 + s["A"] - 4, B1 + s["B"] - 4
            lst, arc = rd(N + 0x18), rd(rd(N + 0x18))
            al = rd(A_ + 0x18)
            wp = rd(N + 0xC)
            return (rd(N) == B_ and rd(N + 4) == A_ and rd(N + 8) == B1 + g3b.GRAPH - 4
                    and wp == B1 + p["waypoint"] - 4 and lst == B1 + p["list"] - 4 and arc == B1 + p["arc"] - 4
                    and rd(lst + 4) == arc and rd(lst + 8) == 1 and rd(arc) == rd(arc + 4) == 0
                    and rd(arc + 8) == lst and rd(arc + 0xC) == B_ and rd(al + 8) == 1 and rd(rd(al) + 0xC) == N
                    and rd(A_) == N and rd(B_ + 4) == N
                    and struct.unpack_from(">3f", area, wp - B1) == s["WPOS"][v]
                    and area[wp - B1 + 12:wp - B1 + 20] == data[s["WA"] + 12:s["WA"] + 20])
        o2 = {"nodes_145_distinct": len(nodes) == 145 == len(set(nodes)) and hdr["count"] == 145,
              "walks_forward_backward": not prob,
              "logical_order": nodes == want and nodes.index(NA) == 14 and nodes.index(NB) == 24,
              "first_last_unchanged": hdr["first"] == hdr0["first"] and hdr["last"] == hdr0["last"],
              "site13_links_arc_waypoint": site_ok(s13, 13, NA),
              "site22_links_arc_waypoint": site_ok(s22, 22, NB),
              "independent_construction_identical": (L, P) == (IL, IP)}
        added = [struct.unpack_from(">iI", P, 4 + 8 * i) for i in range(n0, n1)]
        slots_new = [loc + 4 for _, loc in added]
        exp_t = {}
        for after, s in ((13, s13), (22, s22)):
            p = PLACE[after]
            exp_t.update({p["node"]: s["B"], p["node"] + 4: s["A"], p["node"] + 8: g3b.GRAPH,
                          p["node"] + 0xC: p["waypoint"], p["node"] + 0x18: p["list"], p["list"]: p["arc"],
                          p["list"] + 4: p["arc"], p["arc"] + 8: p["list"], p["arc"] + 0xC: s["B"]})
        diff = sorted({i & ~3 for i in range(SIZE) if L[i] != data[i]})
        o3 = {"entries_18_unique_file1_in_bounds": (len(added) == 18 and all(f == 1 for f, _ in added)
                                                    and len(set(slots_new)) == 18 and not dup
                                                    and all(SIZE <= x and x + 4 <= len(L) for x in slots_new)),
              "entry_order_site13_then_site22": slots_new == new_slots(13) + new_slots(22),
              "every_target_as_planned": all(u32(L, x) + 4 == exp_t[x] for x in slots_new) and len(exp_t) == 18,
              "originals_and_cross_table": (P[4:4 + 8 * n0] == ptr[4:4 + 8 * n0] and P[4 + 8 * n1:] == ptr[4 + 8 * n0:]
                                            and len(P) == 4 + 8 * n1 + 16 * m0 == PSIZE + PGROW),
              "only_seven_words_changed": diff == sorted(list(s13["changed"]) + list(s22["changed"]) + [g3b.COUNT_AT])
                                          and u32(L, g3b.COUNT_AT) == 145,
              "sizes": len(L) == SIZE + TAIL and n1 == n0 + 18}
        recs = {"level-tx": len(m["txs"]), "tx-file": sum(len(f["tx"]) for f in m["files"]),
                "grow": sum(len(f["grow"]) for f in m["files"]), "ranges": sorted(len(f["range"]) for f in m["files"])}
        o3["one_transaction_records"] = (recs == {"level-tx": 1, "tx-file": 2, "grow": 2, "ranges": [1, 8]}
                                         and r["structural_active"] == {MOD: LEVEL} and r["gameplay_active"] == [MOD]
                                         and f"gameplay {MOD}" in (text or ""))
        for grp, d in (("O2", o2), ("O3", o3)):
            for k, x in d.items():
                res[f"{grp}_{v}_{k}"] = bool(x)
        det[v] = {"lvl_len": len(L), "ptr_len": len(P), "lvl_sha256": hashlib.sha256(L).hexdigest(),
                  "ptr_sha256": hashlib.sha256(P).hexdigest(), "tx": m["txs"], "records": recs,
                  "positions": {13: s13["WPOS"][v], 22: s22["WPOS"][v]}}
    # simulator as an oracle for the combined case: cross-site and overlap faults refuse
    ix = rm.read_script_index(g3a.GAME, LEVEL)
    entry = ix["graphs"][(rm.FLY10, 0, 0)]
    gnodes = [nd for nd, _ in entry["nodes"]]
    _, tx = compiled("neutral")
    L, P = tx["images"]["lvl"], tx["images"]["ptr"]
    sites = [(13, PLACE[13]), (22, PLACE[22])]
    edits = [(o, "") for o in sorted(list(s13["changed"]) + list(s22["changed"]) + [g3b.COUNT_AT])]
    slots18 = new_slots(13) + new_slots(22)

    def sim(LL, PP, st=sites):
        return lambda: rm.verify_inserts(data, ptr, bytes(LL), bytes(PP), 1, g3b.GRAPH, gnodes, st, slots18, edits, "o")
    cross = bytearray(L)
    struct.pack_into(">I", cross, PLACE[13]["node"] + 0xC, PLACE[22]["waypoint"] - 4)   # new_A -> new_B's waypoint
    swap = bytearray(L)
    struct.pack_into(">I", swap, PLACE[22]["arc"] + 0xC, s13["B"] - 4)                  # new_B's arc -> node 14
    dupp = bytearray(P)
    struct.pack_into(">iI", dupp, 4 + 8 * (u32(P, 0) - 1), 1, slots18[0] - 4)
    cnt = bytearray(L)
    struct.pack_into(">I", cnt, g3b.COUNT_AT, 144)
    overlap = [(13, PLACE[13]), (22, dict(PLACE[22], node=PLACE[13]["arc"]))]
    o2s = {"valid": sim(L, P)() is None,
           "cross_site_waypoint": p1.refused(sim(cross, P), "STRUCTURE_CHECK"),
           "new_B_arc_to_wrong_successor": p1.refused(sim(swap, P), "STRUCTURE_CHECK"),
           "duplicate_slot": p1.refused(sim(L, dupp), "STRUCTURE_CHECK"),
           "count_144": p1.refused(sim(cnt, P), "STRUCTURE_CHECK"),
           "overlapping_objects": p1.refused(sim(L, P, overlap), "STRUCTURE_CHECK")}
    det["O2_simulator"] = o2s
    res["O2_simulator_refuses_combined_faults"] = all(x is True for x in o2s.values())
    # O4 determinism: manifest order reversed
    r_rev, t_rev, _ = p1.compile_plan("dual_neutral_reversed", [(MOD, dual("neutral", order=(22, 13)))])
    strip = lambda t: [re.sub(r"roots\\[^\\]+\\", "", ln) for ln in t.splitlines() if not ln.startswith("#")]  # noqa
    m_rev = p1.parse_plan(t_rev or "")
    res["O4_reversed_manifest_identical_plan"] = bool(t_rev) and strip(plans["neutral"][1]) == strip(t_rev)
    res["O4_reversed_identical_images_and_id"] = (p1.images(m_rev) == p1.images(plans["neutral"][2])
                                                  and m_rev["txs"] == plans["neutral"][2]["txs"])
    _, tx_rev = compiled("neutral", order=(22, 13))
    res["O4_reversed_identical_compiler_output"] = tx_rev["images"] == tx["images"] and tx_rev["info"] == tx["info"]
    r_again, t_again, _ = p1.compile_plan("dual_neutral_again", [(MOD, dual("neutral"))])
    res["O4_repeat_identical"] = strip(t_again or "") == strip(plans["neutral"][1])
    # O5 atomic rejection: an invalid second operation refuses the whole mod (also its valid first operation)
    far = list(s22["WPOS"]["neutral"])
    far[1] += 17
    bad22 = {
        "site_23_not_allowed": ({22: {"after_node": 23}}, "UNSUPPORTED"),
        "site_21_not_allowed": ({22: {"after_node": 21}}, "UNSUPPORTED"),
        "position_far": ({22: {"position": far}}, "UNSUPPORTED"),
        "position_not_finite": ({22: {"position": [float("nan"), 0.0, 0.0]}}, "BAD_MANIFEST"),
        "other_lvl_hash": ({22: {"lvl_sha256": "0" * 64}}, "BAD_MANIFEST"),
        "other_variable": ({22: {"variable": 1}}, "BAD_MANIFEST"),
        "duplicate_site": ({22: {"after_node": 13}}, "BAD_MANIFEST"),
    }
    o5 = {}
    for label, (kw, code) in bad22.items():
        o5[f"compiler_{label}"] = refused(lambda kw=kw: compiled("neutral", ch=kw), code)
        # import refuses the mod (nothing installed); a valid dual mod whose installed copy is then changed the same
        # way is refused whole at resolve time (no transaction, no intro_10 growth; the ordinary mod still applies).
        # Correction before any game run (check run 4): the installed copy is integrity-checked before it is compiled,
        # so the resolve-time code is DAMAGED, not the operation's own code (stricter; the operation's code is the
        # import-time one). The compile-time refusal at resolve is O7's resolve_budget case.
        paths = p1.fresh(f"o5_{label}")
        with p1.dev_env():
            p1.install(paths, "w.13", [p1.waypoint13()])
            imp = p1.refused(lambda kw=kw, paths=paths: p1.install(paths, MOD, dual("neutral", ch=kw)), code)
            p1.install(paths, MOD + "x", dual("neutral"))
            mf = paths["mods"] / "installed" / (MOD + "x") / "mod.json"
            doc = json.loads(mf.read_text(encoding="utf-8"))
            doc["overrides"] = dual("neutral", ch=kw)
            mf.write_text(json.dumps(doc), encoding="utf-8")
            r = rm.resolve_all(paths, write_plan=paths["cache"])
        pl = paths["cache"] / rm.PLAN_NAME
        mm = p1.parse_plan(pl.read_text(encoding="utf-8") if pl.is_file() else "")
        lv = next((f for f in mm["files"] if f["path"].endswith("intro_10.lvl")), None)
        st5 = {x["id"]: (x["state"], x.get("code")) for x in r["mods"]}
        o5[f"plan_{label}"] = (imp is True and st5 == {MOD + "x": ("invalid", "DAMAGED"), "w.13": ("active", None)}
                               and r["structural_active"] == {} and not mm["txs"] and lv is not None and not lv["grow"]
                               and not any(f["path"].endswith("intro_10.ptr") for f in mm["files"]))
        if not o5[f"plan_{label}"]:
            det.setdefault("O5_plans", {})[label] = {"import": imp, "states": st5, "txs": mm["txs"]}
    three = dual("neutral") + [p2.igm(13, "offset") | {"after_node": 5}]
    o5["three_operations"] = refused(lambda: rm.parse_manifest({"mod.json": json.dumps(
        p1.manifest("x.three", three)).encode()}), "BAD_MANIFEST")
    o5["extra_key_in_second"] = refused(lambda: rm.parse_manifest({"mod.json": json.dumps(p1.manifest(
        "x.extra", [p2.igm(13, "neutral"), p2.igm(22, "neutral") | {"offset": 4}])).encode()}), "BAD_MANIFEST")
    o5["adjacent_sites_builder"] = p1.refused(lambda: rm.build_insert_nodes(
        data, ptr, 1, entry, [(13, s13["WPOS"]["neutral"]), (14, s13["WPOS"]["neutral"])], "o"), "UNSUPPORTED")
    o5["unordered_sites_builder"] = p1.refused(lambda: rm.build_insert_nodes(
        data, ptr, 1, entry, [(22, s22["WPOS"]["neutral"]), (13, s13["WPOS"]["neutral"])], "o"), "STRUCTURE_CHECK")

    def put(buf, o, val):
        x = bytearray(buf)
        struct.pack_into(">I", x, o, val)
        return bytes(x)
    pos2 = [(13, s13["WPOS"]["neutral"]), (22, s22["WPOS"]["neutral"])]
    o5["malformed_site22_link_refuses_both"] = p1.refused(lambda: rm.build_insert_nodes(
        put(data, s22["A"], s22["A"] - 4), ptr, 1, entry, pos2, "o"), "STRUCTURE_CHECK")
    o5["site22_arc_capabilities_refuses_both"] = p1.refused(lambda: rm.build_insert_nodes(
        put(data, s22["ARC"] + 0x10, 1), ptr, 1, entry, pos2, "o"), "STRUCTURE_CHECK")
    det["O5"] = o5
    res["O5_atomic_rejection"] = all(x is True for x in o5.values())
    # O6 conflict policy
    codes = lambda r: {x["id"]: x.get("code") for x in r["mods"] if x["state"] != "active"}  # noqa: E731
    o6 = {}
    r, t, _ = p1.compile_plan("o6_two_structural", [(MOD, dual("neutral")), ("s.22", [p2.igm(22, "offset")])])
    o6["dual_and_single_structural_both_refused"] = (r["active"] == [] and t is None and codes(r) == {
        MOD: "STRUCTURAL_CONFLICT", "s.22": "STRUCTURAL_CONFLICT"})
    r, t, _ = p1.compile_plan("o6_disjoint", [(MOD, dual("neutral")), ("w.13", [p1.waypoint13()])])
    mm = p1.parse_plan(t or "")
    im = p1.images(mm) if t else {}
    o6["disjoint_waypoint13_composes"] = (r["active"] == [MOD, "w.13"] and len(mm["txs"]) == 1
                                          and im.get("intro_10.lvl", b"")[g3b.WP13:g3b.WP13 + 12]
                                          == struct.pack(">3f", 19.0, -33.0, -40.0)
                                          and im["intro_10.lvl"][SIZE:] == tx["images"]["lvl"][SIZE:]
                                          and im["intro_10.ptr"] == tx["images"]["ptr"])
    real_compile = rm.compile_mod
    lvl_p = g3a.LVL
    overlap_at = {"site22_word": s22["A"], "count_word": g3b.COUNT_AT}

    def fake_compile(m, files, paths, manifests=None):
        if m["id"].startswith("f."):
            return [(lvl_p, overlap_at[m["id"][2:]], struct.pack(">I", 7), "synthetic.word")]
        return real_compile(m, files, paths, manifests)
    rm.compile_mod = fake_compile
    try:
        for which in overlap_at:
            for label, order_, want_active, want in (
                    ("structural_first", [(MOD, dual("neutral")), (f"f.{which}", [p1.waypoint13()])], [MOD],
                     {f"f.{which}": "STRUCTURAL_CONFLICT"}),
                    ("fixed_first", [(f"f.{which}", [p1.waypoint13()]), (MOD, dual("neutral"))], [f"f.{which}"],
                     {MOD: "STRUCTURAL_CONFLICT"})):
                r4, t4, _ = p1.compile_plan(f"o6_{which}_{label}", order_)
                m4 = p1.parse_plan(t4 or "")
                ok = r4["active"] == want_active and codes(r4) == want
                if want_active == [MOD]:
                    i4 = p1.images(m4)
                    ok = ok and len(m4["txs"]) == 1 and i4["intro_10.lvl"] == tx["images"]["lvl"] \
                        and i4["intro_10.ptr"] == tx["images"]["ptr"]
                else:
                    ok = ok and not m4["txs"] and r4["structural_active"] == {}
                o6[f"overlap_{which}_{label}"] = ok
    finally:
        rm.compile_mod = real_compile
    o6["production_refuses_dual"] = refused(lambda: rm.parse_manifest({"mod.json": json.dumps(
        p1.manifest("x.dual", dual("neutral"))).encode()}), "UNSUPPORTED", env=None)
    o6["other_level_enabled_refuses_dual"] = refused(lambda: compiled_env("intro_20"), "UNSUPPORTED", env="intro_20")
    o6["gameplay_marked"] = plans["neutral"][0]["gameplay_active"] == [MOD]
    det["O6"] = o6
    res["O6_conflict_policy"] = all(x is True for x in o6.values())
    # O7 memory budget of the combined layout
    mem = tx["info"]["memory"]
    det["O7_memory"] = mem
    res["O7_budget_values"] = (mem["area_growth"] == TAIL and mem["free_after_load"] == FREE0 - TAIL
                               and mem["temporary_bound"] == TEMP_BOUND == 853520
                               and mem["headroom"] == FREE0 - TAIL - TEMP_BOUND - rm.STRUCT_MEMORY_MARGIN > 0
                               and mem["preread"] == SIZE + TAIL <= mem["preread_verified"]
                               and tx["info"]["tail"] == TAIL and tx["info"]["slots"] == 18
                               and tx["info"]["nodes"] == 145)
    _, t13 = compiled_single(13)
    _, t22 = compiled_single(22)
    res["O7_combined_not_assumed_sum"] = (t13["info"]["tail"] + t22["info"]["tail"] == TAIL
                                          and mem["temporary_bound"] != t13["info"]["memory"]["temporary_bound"]
                                          + t22["info"]["memory"]["temporary_bound"])
    saved = json.loads(json.dumps(rm.STRUCT_MEMORY))
    sg = dict(rm.STRUCT_MAX_GROW)
    o7 = {}
    try:
        rm.STRUCT_MEMORY["intro_10"]["free_after_load"] = TEMP_BOUND + rm.STRUCT_MEMORY_MARGIN + TAIL - 1
        o7["one_byte_short"] = refused(lambda: compiled("neutral"), "BUDGET")
        p7 = p1.fresh("o7_short")
        with p1.dev_env():
            o7["one_byte_short_import_refused"] = p1.refused(lambda: p1.install(p7, MOD, dual("neutral")), "BUDGET")
            o7["one_byte_short_nothing_installed"] = not (p7["mods"] / "installed" / MOD).exists()
        rm.STRUCT_MEMORY.clear()
        rm.STRUCT_MEMORY.update(json.loads(json.dumps(saved)))
        pr = p1.fresh("o7_resolve_budget")
        with p1.dev_env():
            p1.install(pr, "w.13", [p1.waypoint13()])
            p1.install(pr, MOD, dual("neutral"))
            rm.STRUCT_MEMORY["intro_10"]["free_after_load"] = TEMP_BOUND + rm.STRUCT_MEMORY_MARGIN + TAIL - 1
            rr = rm.resolve_all(pr, write_plan=pr["cache"])
        pt = pr["cache"] / rm.PLAN_NAME
        mr = p1.parse_plan(pt.read_text(encoding="utf-8") if pt.is_file() else "")
        o7["resolve_budget_refuses_whole_mod"] = ({x["id"]: (x["state"], x.get("code")) for x in rr["mods"]}
                                                  == {"w.13": ("active", None), MOD: ("invalid", "BUDGET")}
                                                  and not mr["txs"] and rr["structural_active"] == {}
                                                  and not any(f["grow"] for f in mr["files"]))
        rm.STRUCT_MEMORY["intro_10"]["free_after_load"] = TEMP_BOUND + rm.STRUCT_MEMORY_MARGIN + TAIL
        o7["exact_budget_accepted"] = refused(lambda: compiled("neutral"), "BUDGET") is False
        rm.STRUCT_MEMORY["intro_10"] = dict(saved["intro_10"], preread_verified=SIZE + TAIL - 4)
        o7["preread_refused"] = refused(lambda: compiled("neutral"), "BUDGET")
        rm.STRUCT_MEMORY["intro_10"] = dict(saved["intro_10"], preread_verified=SIZE + TAIL)
        o7["preread_exact_accepted"] = refused(lambda: compiled("neutral"), "BUDGET") is False
        del rm.STRUCT_MEMORY["intro_10"]
        o7["unmeasured_level_refused"] = refused(lambda: compiled("neutral"), "BUDGET")
    finally:
        rm.STRUCT_MEMORY.clear()
        rm.STRUCT_MEMORY.update(saved)
    try:
        rm.STRUCT_MAX_GROW["lvl"] = TAIL - 1
        o7["lvl_growth_cap"] = refused(lambda: compiled("neutral"), "BUDGET")
        rm.STRUCT_MAX_GROW.update(sg)
        rm.STRUCT_MAX_GROW["ptr"] = PGROW - 1
        o7["ptr_growth_cap"] = refused(lambda: compiled("neutral"), "BUDGET")
    finally:
        rm.STRUCT_MAX_GROW.clear()
        rm.STRUCT_MAX_GROW.update(sg)
    o7["restored"] = rm.STRUCT_MEMORY == saved and rm.STRUCT_MAX_GROW == sg
    det["O7"] = o7
    res["O7_budget_refusals"] = all(x is True for x in o7.values())
    st = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "selftest"], cwd=ROOT, capture_output=True,
                        text=True)
    det["selftest"] = st.stdout.strip().splitlines()[-1] if st.stdout.strip() else st.stderr[-300:]
    res["O1_selftest"] = st.returncode == 0
    res["game_files_unchanged"] = g3a.files() == (data, ptr)
    out = {"checks": res, "pass": all(res.values()), "details": det}
    (WORK / "offline.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"failed": [k for k, x in res.items() if not x], "passed": sum(res.values()),
                      "total": len(res), "pass": out["pass"],
                      "fail_detail": {k: v for g in ("O2_simulator", "O5", "O6", "O7")
                                      for k, v in det.get(g, {}).items() if v is not True}}, indent=1, default=str))
    return 0 if out["pass"] else 1


def compiled_single(after):
    with p1.dev_env():
        return rm.compile_insert_graph_node(p2.igm(after, "neutral"), {"game": g3a.GAME})


def compiled_env(level):
    with p1.dev_env(level):
        return rm.compile_insert_graph_nodes(dual("neutral"), {"game": g3a.GAME})


# --- O8: runtime transaction cases -------------------------------------------------------------------------------

def negtest():
    out = {}
    # G5-P2a's negtest (G5-P1's 30 + 5 and site 22's 12 + 2), redirected; it builds both test executables
    redirect("o8_g5p2a")
    out["g5p2a_rc"] = p2.negtest()
    exes = {k: WORK / "o8_g5p2a" / "negtest" / f"g5p1_tx_test_{k}.exe" for k in ("dev", "prod")}
    p1.WORK = WORK
    nd = WORK / "negtest"
    if nd.exists():
        shutil.rmtree(nd)
    nd.mkdir(parents=True)
    _, text, _ = p1.compile_plan("neg_dual", [(MOD, dual("neutral"))])
    base = p1.parse_plan(text)
    im = p1.images(base)
    _, tx = compiled("neutral")
    assert im["intro_10.lvl"] == tx["images"]["lvl"] and im["intro_10.ptr"] == tx["images"]["ptr"]
    (nd / "dual_lvl.bin").write_bytes(im["intro_10.lvl"])
    (nd / "dual_ptr.bin").write_bytes(im["intro_10.ptr"])
    li = next(i for i, f in enumerate(base["files"]) if f["path"].endswith("intro_10.lvl"))
    pi = 1 - li
    tail_ri = next(i for i, r in enumerate(base["files"][li]["range"]) if int(r.split(" ")[0]) == SIZE)
    words22 = set(S(22)["changed"])

    def variant(name, fn=None):
        m = json.loads(json.dumps(base))
        if fn:
            fn(m)
        p = nd / f"plan_dual_{name}.txt"
        p.write_text(p1.emit(m), encoding="utf-8")
        return p

    def tamper(m, i, ri):
        off, length, gb, nb, mid, blob = m["files"][i]["range"][ri].split(" ", 5)
        b = bytearray(Path(blob).read_bytes())
        b[len(b) // 2] ^= 0x33
        q = nd / f"dual_tampered_{i}_{ri}.bin"
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
        "tampered_tail": variant("tampered_tail", lambda m: tamper(m, li, tail_ri)),
        "wrong_lvl_sha": variant("wrong_lvl_sha", lambda m: retx(m, li, 1, "0" * 64)),
        "partial_site22": variant("partial_site22", lambda m: m["files"][li].update(
            range=[r for r in m["files"][li]["range"] if int(r.split(" ")[0]) not in words22])),
        "partial_all_words": variant("partial_all_words", lambda m: m["files"][li].update(
            range=[r for r in m["files"][li]["range"] if int(r.split(" ")[0]) >= SIZE])),
        "corrupt_id": variant("corrupt_id", lambda m: m.update(
            txs=[m["txs"][0][:-1] + ("0" if m["txs"][0][-1] != "0" else "1")])),
        "single_site_size": variant("single_site_size", lambda m: (retx(m, li, 2, str(SIZE + 112)),
                                                                   m["files"][li].update(grow=[str(SIZE + 112)]))),
        "two_tx": variant("two_tx", lambda m: m.update(txs=m["txs"] * 2)),
    }
    O = ("-", "-")
    V = (nd / "dual_lvl.bin", nd / "dual_ptr.bin")
    lvl_p, ptr_p = str(g3a.LVL), str(g3a.PTR)
    dev = [("dual valid, .lvl first", "valid", LEVEL, "active", "lvl,ptr", V),
           ("dual valid, .ptr first", "valid", LEVEL, "active", "ptr,lvl", V),
           ("dual not enabled (.lvl first)", "valid", "-", "level_tx_not_enabled", "lvl,ptr", O),
           ("dual not enabled (.ptr first)", "valid", "-", "level_tx_not_enabled", "ptr,lvl", O),
           # expected codes of the next case and of "declared single-site size" corrected after negtest run 1 (before
           # any game run; both were refused whole as expected, with the gate's earlier, more specific reason: the
           # variable naming another level is `tx_level`; a range past a smaller declared size is `range_bounds`)
           ("dual enabled for another level", "valid", "intro_20", "tx_level", "lvl,ptr", O),
           ("dual missing .lvl", "missing_lvl", LEVEL, "tx_incomplete", "ptr,lvl", O),
           ("dual missing .ptr", "missing_ptr", LEVEL, "tx_incomplete", "lvl,ptr", O),
           ("dual tampered .ptr, rehashed", "tampered_ptr", LEVEL, "tx_result_hash", "ptr,lvl", O),
           ("dual tampered tail, rehashed", "tampered_tail", LEVEL, "tx_result_hash", "lvl,ptr", O),
           ("dual wrong original .lvl hash", "wrong_lvl_sha", LEVEL, "tx_identity", "lvl,ptr", O),
           ("dual partial: site 22's words dropped", "partial_site22", LEVEL, "tx_result_hash", "lvl,ptr", O),
           ("dual partial: every edited word dropped", "partial_all_words", LEVEL, "tx_result_hash", "lvl,ptr", O),
           ("dual corrupted id", "corrupt_id", LEVEL, "tx_id", "lvl,ptr", O),
           ("dual declared single-site size", "single_site_size", LEVEL, "range_bounds", "lvl,ptr", O),
           ("dual two transactions", "two_tx", LEVEL, "tx_count", "lvl,ptr", O)]
    prod = [("production: dual transaction (.lvl first)", "valid", LEVEL, "unknown_record", "lvl,ptr", O),
            ("production: dual transaction (.ptr first)", "valid", LEVEL, "unknown_record", "ptr,lvl", O)]
    for kind, cases in (("dev", dev), ("prod", prod)):
        cf = nd / f"cases_dual_{kind}.tsv"
        cf.write_text("".join("\t".join([n, str(plans[p]), env, want, order, lvl_p, ptr_p, str(e[0]), str(e[1])])
                              + "\n" for n, p, env, want, order, e in cases), encoding="utf-8")
        r = subprocess.run([str(exes[kind]), str(cf)], capture_output=True, text=True, timeout=600)
        (nd / f"result_dual_{kind}.txt").write_text(r.stdout + r.stderr)
        print(r.stdout)
        out[kind] = {"exit": r.returncode, "cases": len(cases),
                     "summary": r.stdout.strip().splitlines()[-1] if r.stdout else ""}
    # G5-P3's integrity tests at the dual growth (its fixtures are random bytes; expectations as pre-registered there)
    import g5p3_integrity as p3
    p3.WORK = WORK / "o8_g5p3"
    p3.LVL_GROW, p3.PTR_GROW = TAIL, PGROW
    out["g5p3_rc"] = p3.negtest()
    out["g5p3"] = json.loads((p3.WORK / "summary.json").read_text()).get("res")
    ok = out["g5p2a_rc"] == 0 and out["g5p3_rc"] == 0 and all(out[k]["exit"] == 0 for k in ("dev", "prod"))
    out["pass"] = ok
    (nd / "summary.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(out, default=str), "NEGTEST_P5", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# --- hidden runs ---------------------------------------------------------------------------------------------------

def bind():
    """Point G3b's runner at the dual site (constants used by g3b_ab.run_case)."""
    s13, s22 = S(13), S(22)
    g3b.PREFIX = PREFIX
    g3b.GATE_ENV = (ENV, LEVEL)
    g3b.N = TAIL
    g3b.CHANGED = dict(s13["changed"]) | dict(s22["changed"])
    g3b.NODE13, g3b.NODE14, g3b.WP13, g3b.WP14 = s13["A"], s13["B"], s13["WA"], s13["WB"]
    g3b.write_plan = plan_for_run
    os.environ.pop("R3HD_G3A_TEST_GROW", None)
    os.environ.pop(ENV, None)


def plan_for_run(work, data, ptr, variant):
    res, text, paths = p1.compile_plan(f"run_{work.parent.name}_{work.name}", [(MOD, dual(variant))])
    if text is None or res["active"] != [MOD]:
        raise SystemExit(f"compiler refused the run's mod: {res['mods']}")
    plan = paths["cache"] / rm.PLAN_NAME
    shutil.copyfile(plan, work / "plan_copy.txt")
    return plan


CASES = (("B", "neutral"), ("C", "offset"), ("D", "nogate"))


def run(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    bind()
    for _, case in CASES:
        print(json.dumps(g3b.run_case(tag, case)), flush=True)
    return 0


def load(work, run):
    row = p2.load(work, run)
    row["snapshots"] = sorted((f, b, d) for f, _, b, d in re.findall(
        r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", row["log"]))
    rj = g3a.RUNS / run / "run.json"
    row["run_json"] = json.loads(rj.read_text(encoding="utf-8-sig")) if rj.is_file() else {}
    return row


def judge(tag):
    data, ptr = g3a.files()
    A = load(A_WORK, A_RUN)
    rows = {"A": A}
    for role, case in CASES:
        rows[role] = load(WORK / tag / case, f"{PREFIX}_{tag}_{case}")
    s13, s22 = S(13), S(22)
    SITES = {13: s13, 22: s22}
    txs = {v: compiled(v)[1] for v in ("neutral", "offset")}
    variant = {"B": "neutral", "C": "offset"}
    det, P = {}, {}

    def ab(r):
        return int(r["area"]["base"], 16) if r.get("area") else None
    invalid = [k for k, r in rows.items() if r.get("error") or not r["samples"]
               or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60]
    t_close = min(A["samples"], key=lambda q: math.dist(q["pos"], s13["wa"]))["t"]
    invalid += [k for k in ("B", "C", "D") if rows[k]["samples"] and rows[k]["samples"][0]["t"] >= t_close
                and k not in invalid]
    shas = {k: r.get("original_readback_sha256") for k, r in rows.items()}
    free_words = {p["node"] - SIZE + k for p in PLACE.values() for k in range(0x10, 0x18)}

    def tail_check(k):
        r, base = rows[k], ab(rows[k])
        exp = bytearray(txs[variant[k]]["images"]["lvl"][SIZE:])
        for sl in new_slots(13) + new_slots(22):
            struct.pack_into(">I", exp, sl - SIZE, (u32(exp, sl - SIZE) + base) & 0xFFFFFFFF)

        def fixed(h):
            b = bytes.fromhex(h) if h else b""
            return len(b) == TAIL and all(b[i] == exp[i] for i in range(TAIL) if i not in free_words)
        ts = r["tails"]
        out = {"reads": len(ts), "all": all(fixed(t["hex"]) for t in ts),
               "span": round(ts[-1]["t"] - ts[0]["t"], 2) if ts else 0,
               "live": all(fixed((r.get(x) or {}).get("tail")) for x in ("live_first", "live_end"))}
        out["ok"] = out["reads"] >= 55 and out["all"] and out["span"] >= 55 and out["live"]
        return out

    def resource(k):
        r = rows[k]
        tc = tail_check(k)
        wps = [s13["WA"], s13["WB"], s22["WA"], s22["WB"]]
        end = (r.get("live_end") or {}).get("orig_wp")
        log = r["log"]
        ok = (log.count("M33 mods state=active") == 1 and r["plan_tx"] and r["tx_lines"] == r["plan_tx"]
              and r["snapshots"] == [("intro_10.lvl", str(SIZE + TAIL), "2"), ("intro_10.ptr", str(PSIZE + PGROW), "2")]
              and r["grow_size"] == sorted([("intro_10.lvl", str(SIZE), str(SIZE + TAIL)),
                                            ("intro_10.ptr", str(PSIZE), str(PSIZE + PGROW))])
              and r["served_files"] == ["intro_10.lvl", "intro_10.ptr"] and "G5P3 tx host_changed" not in log
              and shas[k] and shas[k] == shas["D"] and tc["ok"]
              and end == [data[w:w + 0x14].hex() for w in (s13["WA"], s13["WB"])])
        # the runner reads node 13's and 14's original waypoints; node 22's / 23's come from the tail-independent
        # read-back hash (they lie in the original area, which the masked hash covers)
        det[f"resource_{k}"] = {"snapshots": r["snapshots"], "grow_size": r["grow_size"], "tx": r["tx_lines"],
                                "plan_tx": r["plan_tx"], "served": r["served_files"], "tail": tc,
                                "orig_wp13_14": end == [data[w:w + 0x14].hex() for w in wps[:2]]}
        return bool(ok)

    def regist(k, grown=True):
        r, base = rows[k], ab(rows[k])
        ok = bool(base)
        NA, NB = (base or 0) + PLACE[13]["node"] - 4, (base or 0) + PLACE[22]["node"] - 4
        info = {}
        for x in ("live_first", "live_end"):
            lv = r.get(x) or {}
            gr = lv.get("graph") or {}
            nodes = gr.get("nodes") or []
            a_nodes = ((A.get(x) or {}).get("graph") or {}).get("nodes") or []
            a_hdr = ((A.get(x) or {}).get("graph") or {}).get("header") or {}
            if grown:
                want_words = [NA] * 3 + [NB] * 3 + [145]
                ok = ok and (gr.get("problems") == [] and len(nodes) == 145 == len(set(nodes))
                             and gr["header"]["count"] == 145 and nodes[14] == NA and nodes[24] == NB
                             and nodes[:14] + nodes[15:24] + nodes[25:] == a_nodes
                             and gr["header"]["first"] == a_hdr.get("first") and gr["header"]["last"] == a_hdr.get("last")
                             and gr.get("arc13") == {"count": 1, "target": NA} and lv.get("changed") == want_words)
            else:
                want_words = [base + v for v in list(s13["changed"].values()) + list(s22["changed"].values())] + [143]
                ok = ok and gr.get("problems") == [] and nodes == a_nodes and lv.get("changed") == want_words
            info[x] = {"n": len(nodes), "changed_ok": lv.get("changed") == want_words}
        det[f"registration_{k}"] = info
        return bool(ok)
    near = lambda p, q: all(abs(p[i] - q[i]) <= 1e-4 for i in range(3))   # noqa: E731

    def visits(k, after, grown=True):
        s, r, base = SITES[after], rows[k], ab(rows[k]) or 0
        wn, wa, wb = base + PLACE[after]["waypoint"] - 4, base + s["WA"] - 4, base + s["WB"] - 4
        sm = r["samples"]
        at = [x for x in sm if x["v8"] == wn]
        ins = [(sm[i - 1]["v8"], sm[i]["v8"]) for i in range(1, len(sm)) if sm[i]["v8"] != sm[i - 1]["v8"]]
        into = [a for a, b in ins if b == wn]
        outof = [b for a, b in ins if a == wn]
        v = {"samples": len(at), "into": len(into), "into_from_site": sum(a == wa for a in into), "out": len(outof),
             "out_to_next": sum(b == wb for b in outof)}
        det[f"visits_{k}_{after}"] = v | {"v10": sorted({tuple(round(c, 4) for c in x["v10"]) for x in at})}
        if not grown:
            return v["samples"] == 0
        return (v["samples"] >= 3 and v["into"] >= 2 and v["into"] == v["into_from_site"] and v["out"] >= 2
                and v["out"] == v["out_to_next"] and all(near(x["v10"], s["WPOS"][variant[k]]) for x in at))

    def alloc(k):
        r = rows[k]
        grown = k in ("B", "C")
        L = AREA + (TAIL if grown else 0)
        st = r["states"]
        i = next((j for j, x in enumerate(st) if "invalid" not in x), None)
        walk_ok = i is not None and not any("invalid" in x for x in st[i:])
        used = [q for q in st if "invalid" not in q and "1" in q.get("areas", {})]
        free = used[-1]["free_bytes"] if used else None
        ok = (walk_ok and (r.get("area") or {}).get("length") == L and r["area"]["words"] == bp.words_for(L)
              and bool(used) and all(q["areas"]["1"]["length"] == L for q in used))
        ok = ok and free == FREE0 - (TAIL if grown else 0)
        if grown:
            ok = ok and free - TEMP_BOUND >= rm.STRUCT_MEMORY_MARGIN
            ok = ok and sum(int(b) for _, b, _ in r["snapshots"]) == SIZE + TAIL + PSIZE + PGROW
        det[f"alloc_{k}"] = {"length": (r.get("area") or {}).get("length"), "free_after": free, "walk_ok": walk_ok}
        return bool(ok)

    def path_of(r, start):
        return [q["pos"] for q in r["samples"] if q["t"] >= start]

    def devs(r, path, start):
        return [(g3a.to_path(q, path), q) for q in path_of(r, start)]

    def region_max(o, centre, inside=True, other=None):
        sel = [x for x in o if (math.dist(x[1], centre) <= 25) == inside
               and (other is None or math.dist(x[1], other) > 25)]
        return max(sel, key=lambda x: x[0][0]) if sel else None

    def closest(r, start, target):
        q = path_of(r, start)
        return g3a.to_path(target, q)[0] if len(q) > 1 else None
    geo = {}
    if not invalid:
        start = max(r["samples"][0]["t"] for r in rows.values()) + 0.5
        pa, pb = path_of(A, start - 1.0), path_of(rows["B"], start - 1.0)
        M, Mp, M2, M2p = s13["M"], s13["MP"], s22["M"], s22["MP"]
        oB, oC, oD, oCB = (devs(rows["B"], pa, start), devs(rows["C"], pa, start), devs(rows["D"], pa, start),
                           devs(rows["C"], pb, start))

        def region(o, c, cp=None):
            x = region_max(o, c)
            d = {"max": round(x[0][0], 3) if x else None, "at_dist": round(math.dist(x[1], c), 2) if x else None}
            if cp is not None and x:
                d["toward"] = sum((x[1][i] - x[0][1][i]) * (cp[i] - c[i]) for i in range(3)) > 0
            return d
        outside = lambda o: round(region_max(o, M, inside=False, other=M2)[0][0], 3)  # noqa: E731
        geo = {"B": {"M": region(oB, M), "M2": region(oB, M2), "outside": outside(oB),
                     "closest_Mp": round(closest(rows["B"], start, Mp), 3),
                     "closest_M2p": round(closest(rows["B"], start, M2p), 3)},
               "C": {"M": region(oC, M, Mp), "M2": region(oC, M2, M2p), "outside": outside(oC),
                     "vs_B_M": region(oCB, M)["max"], "vs_B_M2": region(oCB, M2)["max"],
                     "closest_Mp": round(closest(rows["C"], start, Mp), 3),
                     "closest_M2p": round(closest(rows["C"], start, M2p), 3)},
               "D": {"max": round(max(x[0][0] for x in oD), 3)},
               "A": {"closest_Mp": round(closest(A, start, Mp), 3), "closest_M2p": round(closest(A, start, M2p), 3)},
               "start": start}
    g = geo
    P["P1_transaction_integrity"] = resource("B") and resource("C")
    P["P2_graph_registration"] = regist("B") and regist("C") and regist("D", grown=False)
    P["P3_first_insertion_consumed"] = visits("B", 13) and visits("C", 13) and visits("D", 13, grown=False)
    P["P4_second_insertion_consumed"] = visits("B", 22) and visits("C", 22) and visits("D", 22, grown=False)
    P["P5_neutral"] = bool(g) and (g["B"]["M"]["max"] <= TOL[13] and g["B"]["M2"]["max"] <= TOL[22]
                                   and g["B"]["outside"] <= 0.5 and g["D"]["max"] <= 0.5)
    P["P6_offset"] = bool(g) and all(
        g["C"][reg]["max"] >= 1.5 and g["C"][reg]["toward"] is True and g["C"][f"vs_B_{reg}"] >= 1.5
        and g["C"][f"closest_{reg}p"] <= g["A"][f"closest_{reg}p"] - 1.0
        and g["C"][f"closest_{reg}p"] <= g["B"][f"closest_{reg}p"] - 1.0 for reg in ("M", "M2")) \
        and g["C"]["outside"] <= 0.5
    P["P7_memory_lifecycle"] = all(alloc(k) for k in rows)
    D = rows["D"]
    off = json.loads((WORK / "offline.json").read_text())
    neg = json.loads((WORK / "negtest" / "summary.json").read_text())
    fg = {k: (r["run_json"].get("game_foreground_events"), r["run_json"].get("game_foreground_samples"))
          for k, r in rows.items() if k != "A"}
    P["P8_rejection_desktop"] = (
        "state=refused reason=level_tx_not_enabled" in D["log"] and "M36 grow" not in D["log"]
        and "M33 mods served" not in D["log"] and "G5P1" not in D["log"] and "G5P3" not in D["log"]
        and off["pass"] and neg["pass"] and all(v == (0, 0) for v in fg.values())
        and all(r["haptics_policy"] and not any(r["judges"].values()) and r["runner_exit"] == 0
                and not r["process_left"] for k, r in rows.items() if k != "A"))
    out = {"invalid": invalid, "P": P, "pass": not invalid and all(P.values()), "geometry": geo, "details": det,
           "readback": shas, "foreground": fg, "judges": {k: r["judges"] for k, r in rows.items()},
           "runner_exit": {k: r.get("runner_exit") for k, r in rows.items()}}
    (WORK / f"judgement_{tag}.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({k: out[k] for k in ("invalid", "P", "pass", "geometry", "foreground")}, indent=1, default=str))
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
    WORK.mkdir(parents=True, exist_ok=True)
    return run(a.tag)


if __name__ == "__main__":
    sys.exit(main())
