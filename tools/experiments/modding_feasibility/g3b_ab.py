#!/usr/bin/env python3
"""E-469 (D-236) G3b: one NEW logical node N inserted between nodes 13 and 14 of the intro_10 flight graph (143 -> 144
nodes), in appended `.lvl` storage with nine new `.ptr` entries. Private, test-only (g3a_test_grow_patch.py, reused
unchanged); hidden and read-only at run time.

STATIC AUDIT (guest code; handler tables: value calls (node type 03) 0x8283B460, procedures (04) 0x828398E8, 8-byte
entries {handler, flags}; evaluator table 0x82839838)
- Graph 0xC {+0 first node, +4 last node, +8 count} (node 0 follows it directly); node 0x1C {+0 next, +4 previous,
  +8 graph, +0xC waypoint, +0x10 capabilities (written at run time), +0x14 initial capabilities, +0x18 arc list};
  arc list 0xC {first arc, last arc, count}; arc 0x20 {+0 next, +4 previous (0, not relocated, in all one-arc
  lists), +8 -> its list, +0xC -> target node, +0x10 capabilities, +0x14, +0x18 weight, +0x1C}. The first node's
  previous and the last node's next are 0.
- The count is read only by 82251818 (`lwz r3,8(r3)`). Its users: value calls 173-180 (8225BE78), 172
  (8225BCC8), 188-194 (8225B5D8) and, through 82252058 / 8224D398 / 8224D5E0, value call 171 and procedures
  468-477, 495-525. All use it as the bound of `for i < count: node i = 82251820(graph, i)` (i steps of +0 from the
  first node; no array, no allocation, no validation). The flight generator (only owner of this graph; nothing else
  in the files points to it) calls only 175 among them (FlyInit, IsInCine, macros 3 / 9). Every other graph call it
  makes (186 / 213, 822550E8 / 822554A0; procedure 444, 8223F108) walks +0 until 0 and finds a node by its waypoint
  pointer; 186 then walks that node's arcs (+0 until 0) and returns the target node's waypoint. No node index is
  stored; indices are the walk order. Nothing builds state from the count at load (the loader only relocates).
  So the count must equal the chain length: 144 with N.
CONSTRUCTION (`check` re-verifies from the files and fails closed)
  Changed original words (file offsets): node 13 +0 0x542610: 0x542628 -> N; node 14 +4 0x542630: 0x54260C -> N;
  node 13's arc +0xC 0x545494: 0x542628 -> N; graph +8 0x5424A0: 143 -> 144. Everything else unchanged.
  Tail at 7,661,836, 112 bytes (node 13's block layout and alignments): 4 zero; N at FN = 7,661,840 {next -> node
  14, previous -> node 13, graph, waypoint -> WN, 0, 0, arcs -> LN}; 12 zero; waypoint WN at FW = 7,661,880 {x, y, z,
  1.0, 0}; arc list LN at FL = 7,661,900 {first -> AN, last -> AN, 1}; arc AN at FA = 7,661,912 {0, 0, list -> LN,
  target -> node 14, 0, 0, 0, 0} (as node 13's arc); 4 zero. Stored pointer values = file offset - 4.
  .ptr: n 25,143 -> 25,152, nine entries {1, slot} appended to the same-file list for N +0 / +4 / +8 / +0xC / +0x18,
  LN +0 / +4, AN +8 / +0xC; cross-file table byte-identical, moved by 72; 209,068 -> 209,140 bytes.
  B neutral: WN = M, the midpoint of node 13's and node 14's waypoints = (17.918686, -38.356636, -41.300476).
  C offset: WN = M' = M + 6 units horizontally, perpendicular to 13 -> 14 (to +x, the E-464 / E-467 side) =
  (23.757877, -39.736439, -41.300476) (f32 values in the constants).
  Served payloads: .lvl neutral FNV fbb2dd5392b51146 (SHA-256 f4d1c95a...246b8720), offset c4e007369445f569
  (eb86a6c4...9b89713e); .ptr (both) 611fc0c224cd5100 (5f7ba599...491aa005). Offline gate 16/16 PASS, including a
  simulated relocation walked as the game walks (+0 until 0, back by +4): 144 distinct nodes, N at index 14, the
  original 143 in order, first / last unchanged, arcs consistent, nothing else in the area changed.
EXPECTED live (area base B; 0x40F5509C in every run so far): N = B + FN - 4, WN = B + FW - 4, LN = B + FL - 4,
  AN = B + FA - 4; original waypoints of node 13 / 14 at B + 0x545464 / B + 0x545424.
CASES (one hidden run each; m9_license_run.py: hidden window, muted, no physical pad, isolated private profile,
  `--test-level intro_10`, no input, no captures; 150 s, generator sampled every 0.1 s for 75 s, tail every 1 s):
  A base: no plan.  B neutral: plan B + R3HD_G3A_TEST_GROW=intro_10.  C offset: plan C + gate env.
  D nogate: plan C, gate env unset (refused as a whole).
TOLERANCES (prospective): run-to-run noise 0.15 (E-464); isolation 0.5 (E-464 W4r / E-467 / E-468). Gain of the path
  toward a moved waypoint 0.49 (E-467 / E-468: 2.897 for a 5.87-unit perpendicular move). A's path passes 0.843
  from M (E-468 h1 base), so B is predicted to bend toward M by about 0.41: neutral insertion tolerance 1.0
  (prediction + noise, doubled) near M, 0.5 elsewhere.
PROTOCOL (committed before any run)
  N1 resource: B / C `M36 grow size` lines name exactly intro_10.lvl 7661836 -> 7661948 and intro_10.ptr 209068 ->
     209140; grow reads only of those two, kind=tail; only those two served; A `M33 mods=off`; D `grow_not_allowed`
     and no grow line; SHA-256 of the area's first 7,661,832 bytes at its first appearance with the four changed
     words zeroed equal in A, B, C, D; the tail's fixed bytes (everything but N +0x10 / +0x14) equal to the
     expectation at every read for 60 s (B, C); node 13's and node 14's original waypoints unchanged at the end.
  N2 relocation: at the first live read and at the end, the nine new pointer words equal their predicted
     addresses (B, C); node 13 +0, node 14 +4 and node 13's arc target = N (B, C), the original values (A, D).
  N3 registration: at both reads, the live count word = 144 (B, C) / 143 (A, D); the walk from the first node by +0
     until 0 gives exactly that many distinct nodes, each +8 = the graph and +4 = the node before, ending at the
     graph's last node; the walk back by +4 from the last node until 0 is its reverse; first and last unchanged
     from A; walk index 14 = N (B, C), and A's nodes 0..142 = B's / C's minus N, in order.
  N4 arcs: (B, C) node 13's arc list count 1, its arc's target N; N's list LN {AN, AN, 1}, AN +8 = LN, AN +0xC =
     node 14, AN +0 / +4 = 0; (A, D) node 13's arc target node 13's original successor (node 14).
  N5 consumption: generator variable 8 equals WN's address in >= 3 samples (B, C) and never (A, D); in B and C
     every change of variable 8 to WN comes from node 13's waypoint and every change from WN goes to node 14's
     waypoint, at least 2 visits; at those samples variable 10 = M (B) / M' (C), each coordinate within 1e-4.
  N6 neutral: B's sampled path (after the latest first sample of the four runs + 0.5 s) within 1.0 of A's path
     everywhere and within 0.5 at samples more than 25 units from M; D within 0.5 of A everywhere.
  N7 effect: C's maximum distance from A's path >= 1.5 at a sample within 25 units of M, displaced toward M'
     (positive dot product with M' - M); C's closest approach to M' at least 1.0 smaller than A's and than B's;
     C's maximum distance from B's path >= 1.5; C's samples more than 25 from M within 0.5 of A's path.
  N8 safety: valid block-8 walk in every snapshot after the first valid one; area 7,661,944 bytes, chunk words
     words_for(7,661,944) (B, C), 7,661,832 (A, D); free after load 13,088,416 (B, C), 13,088,528 (A, D); haptics
     policy line, M21 / M22 / M23 0, runner exit 0, no game process left; gate reverted and rebuilt after.
  Invalid (new tag, not judged): file hashes differ, level not opened, area or generator not found, fewer than 60 s
  of samples, or a run's first sample after A's closest approach to node 13's waypoint.
  Classes: N2-N4 = structural insertion; N5 = consumption (the game visits N); N7 = functional effect.

usage: g3b_ab.py check | TAG [--cases base,neutral,offset,nogate] | judge TAG
Outputs stay under private/work/e469/.
"""
import argparse
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import block8_probe as bp  # noqa: E402
import g3a_ab as g3a  # noqa: E402  (file identities, relocation model, path geometry)

LVL, PTR, GAME, LDIR = g3a.LVL, g3a.PTR, g3a.GAME, g3a.LDIR
RUNS = g3a.RUNS
PREFIX = "e469"
SIZE, PSIZE, AREA = g3a.SIZE, g3a.PSIZE, g3a.AREA
ORIG_FNV, PTR_FNV = g3a.ORIG_FNV, g3a.PTR_FNV
GRAPH, NODE13, NODE14, NODE12 = 0x542498, 0x542610, 0x54262C, 0x5425F4
WP13, WP14, ARC13 = 0x545468, 0x545428, 0x545488
CHANGED = {NODE13: 0x542628, NODE14 + 4: 0x54260C, ARC13 + 0xC: 0x542628}   # slot -> original stored value
COUNT_AT = GRAPH + 8
N = 112
FN, FW, FL, FA = SIZE + 4, SIZE + 44, SIZE + 64, SIZE + 76
K = 9
f32 = lambda v: struct.unpack(">f", struct.pack(">f", v))[0]   # noqa: E731
W13 = (19.20733070373535, -32.90321350097656, -40.1010627746582)
W14 = (16.630041122436523, -43.81005859375, -42.49989318847656)
M = tuple(f32((a + b) / 2) for a, b in zip(W13, W14))
_d = (W14[0] - W13[0], W14[1] - W13[1])
_n = math.hypot(*_d)
_perp = (-_d[1] / _n, _d[0] / _n)          # (0.973, -0.230): toward +x
MP = (f32(M[0] + 6 * _perp[0]), f32(M[1] + 6 * _perp[1]), M[2])
WPOS = {"neutral": M, "offset": MP}
FREE0 = g3a.FREE0
SECONDS, WATCH = 150, 75
CASES = ("base", "neutral", "offset", "nogate")
GROWN = ("neutral", "offset")
GEN = g3a.GEN
GATE_ENV = g3a.GATE_ENV
u32, fnv = g3a.u32, g3a.fnv


def construct(data, ptr, variant):
    """(new .lvl, new .ptr, tail)."""
    new = bytearray(data)
    for s in CHANGED:
        new[s:s + 4] = struct.pack(">I", FN - 4)
    new[COUNT_AT:COUNT_AT + 4] = struct.pack(">I", 144)
    node = struct.pack(">7I", NODE14 - 4, NODE13 - 4, GRAPH - 4, FW - 4, 0, 0, FL - 4)
    wp = struct.pack(">4f", *WPOS[variant], 1.0) + b"\0" * 4
    lst = struct.pack(">3I", FA - 4, FA - 4, 1)
    arc = struct.pack(">8I", 0, 0, FL - 4, NODE14 - 4, 0, 0, 0, 0)
    tail = b"\0" * 4 + node + b"\0" * 12 + wp + lst + arc + b"\0" * 4
    assert len(tail) == N and len(node) == 0x1C and FN + 0x1C + 12 == FW and FW + 0x14 == FL and FL + 0xC == FA
    n = u32(ptr, 0)
    slots = [FN + k for k in (0, 4, 8, 0xC, 0x18)] + [FL, FL + 4] + [FA + 8, FA + 0xC]
    entries = b"".join(struct.pack(">iI", 1, s - 4) for s in slots)
    nptr = struct.pack(">I", n + K) + ptr[4:4 + 8 * n] + entries + ptr[4 + 8 * n:]
    return bytes(new) + tail, nptr, tail, slots


def walk_null(rd, graph):
    """Walk a graph as the game does (+0 until 0) and back (+4 until 0) -> (nodes, problems)."""
    first, last, count = rd(graph), rd(graph + 4), rd(graph + 8)
    nodes, prev, nd, problems = [], 0, first, []
    while nd:
        if nd in nodes or len(nodes) > 400:
            problems.append("cycle")
            break
        if rd(nd + 8) != graph:
            problems.append(f"node {len(nodes)} graph")
        if rd(nd + 4) != prev:
            problems.append(f"node {len(nodes)} previous")
        nodes.append(nd)
        prev, nd = nd, rd(nd)
    back, nd = [], last
    while nd and len(back) <= 400:
        back.append(nd)
        nd = rd(nd + 4)
    if not nodes or nodes[-1] != last:
        problems.append("last")
    if back[::-1] != nodes:
        problems.append("backward walk differs")
    if count != len(nodes):
        problems.append(f"count {count} != walked {len(nodes)}")
    return nodes, problems, {"first": first, "last": last, "count": count}


def check():
    data, ptr = g3a.files()
    n, m = u32(ptr, 0), u32(data, 0)
    res = {}
    ents = [struct.unpack_from(">iI", ptr, 4 + 8 * i) for i in range(n)]
    slots = {loc + 4: f for f, loc in ents}

    def target(o):
        return u32(data, o) + 4 if slots.get(o) == 1 else None
    res["ptr_layout"] = 4 + 8 * n + 16 * m == len(ptr) and len(slots) == n == 25143
    res["graph_header"] = (u32(data, COUNT_AT) == 143 and COUNT_AT not in slots and target(GRAPH) is not None
                           and target(GRAPH + 4) is not None)
    res["neighbours"] = (target(NODE13) == NODE14 and target(NODE14 + 4) == NODE13 and target(NODE13 + 4) == NODE12
                         and target(NODE13 + 0xC) == WP13 and target(NODE14 + 0xC) == WP14
                         and all(s in slots and u32(data, s) == v for s, v in CHANGED.items()))
    al13 = target(NODE13 + 0x18)
    res["node13_arc"] = (al13 is not None and u32(data, al13 + 8) == 1 and target(al13) == ARC13
                         and target(al13 + 4) == ARC13 and target(ARC13 + 8) == al13 and target(ARC13 + 0xC) == NODE14
                         and u32(data, ARC13) == u32(data, ARC13 + 4) == 0 and ARC13 not in slots
                         and ARC13 + 4 not in slots and data[ARC13 + 0x10:ARC13 + 0x20] == b"\0" * 16)
    # who points to node 14 (the new arc adds one more): node 13 +0, node 15 +4, node 13's arc
    into14 = sorted(o for o in slots if target(o) == NODE14)
    res["node14_refs"] = into14 == sorted([NODE13, ARC13 + 0xC, NODE14 + 0x1C + 4])
    B1 = 0x40F5509C
    rd0 = None
    base_area, _, _ = g3a.relocate(data, ptr, B1)
    rd0 = lambda a: u32(base_area, a - B1)   # noqa: E731
    nodes0, prob0, hdr0 = walk_null(rd0, B1 + GRAPH - 4)
    # pointers to the graph: the 143 nodes' +8 and the owner's two designer-variable buffers (E-464 role check)
    to_graph = {o for o in slots if target(o) == GRAPH}
    node8 = {nd - B1 + 4 + 8 for nd in nodes0}
    import waypoint_ab
    res["graph_owner_only"] = node8 <= to_graph and len(to_graph - node8) == 2 and not waypoint_ab.role()[2]["safe"]
    res["original_walk_143"] = not prob0 and len(nodes0) == 143 and nodes0[13] == B1 + NODE13 - 4 \
        and nodes0[14] == B1 + NODE14 - 4
    desc = {}
    for variant in GROWN:
        nl, np_, tail, nslots = construct(data, ptr, variant)
        diff = sorted({i & ~3 for i in range(SIZE) if nl[i] != data[i]})
        ok = len(nl) == SIZE + N and diff == sorted(list(CHANGED) + [COUNT_AT])
        ok = ok and all(u32(nl, s) == FN - 4 for s in CHANGED) and u32(nl, COUNT_AT) == 144
        ok = ok and FN % 4 == 0 and FW % 16 == WP13 % 16 and FL % 16 == al13 % 16 and FA % 16 == ARC13 % 16
        res[f"lvl_{variant}"] = bool(ok)
        n2 = u32(np_, 0)
        new_ents = [struct.unpack_from(">iI", np_, 4 + 8 * i) for i in range(n, n2)]
        pok = (n2 == n + K and len(np_) == 4 + 8 * n2 + 16 * m == PSIZE + 8 * K
               and np_[4:4 + 8 * n] == ptr[4:4 + 8 * n] and np_[4 + 8 * n2:] == ptr[4 + 8 * n:]
               and [loc + 4 for _, loc in new_ents] == nslots and all(f == 1 for f, _ in new_ents)
               and len(set(nslots)) == K and not any(s in slots for s in nslots)
               and all(SIZE <= s and s + 4 <= len(nl) and u32(nl, s) + 4 < len(nl) for s in nslots))
        # every non-zero word of the new structures that is a pointer has exactly one entry; no other word has one
        ptr_words = {FN + k for k in (0, 4, 8, 0xC, 0x18)} | {FL, FL + 4, FA + 8, FA + 0xC}
        pok = pok and set(nslots) == ptr_words
        res[f"ptr_{variant}"] = bool(pok)
        area, seen, dup = g3a.relocate(nl, np_, B1)
        rd = lambda a, area=area: u32(area, a - B1)   # noqa: E731
        nodes, prob, hdr = walk_null(rd, B1 + GRAPH - 4)
        NA, LA, AA = B1 + FN - 4, B1 + FL - 4, B1 + FA - 4
        sim = (not dup and not prob and len(nodes) == 144 and len(set(nodes)) == 144
               and hdr["first"] == hdr0["first"] and hdr["last"] == hdr0["last"]
               and nodes[14] == NA and nodes[:14] + nodes[15:] == nodes0
               and rd(NA + 0xC) == B1 + FW - 4 and rd(NA + 0x18) == LA and rd(LA) == rd(LA + 4) == AA
               and rd(LA + 8) == 1 and rd(AA + 8) == LA and rd(AA + 0xC) == B1 + NODE14 - 4
               and rd(AA) == rd(AA + 4) == 0
               and rd(rd(rd(B1 + NODE13 - 4 + 0x18)) + 0xC) == NA)
        # node 12's arc still to node 13; every original node keeps its arcs; nothing else in the area changed
        same = [o for o in range(0, AREA, 4) if u32(area, o) != u32(base_area, o)]
        sim = sim and sorted(same) == sorted(s - 4 for s in list(CHANGED) + [COUNT_AT])
        sim = sim and struct.unpack_from(">3f", area, FW - 4) == WPOS[variant]
        res[f"simulated_{variant}"] = bool(sim)
        desc[variant] = {"lvl_length": len(nl), "changed_words": [f"0x{s:X}: {u32(data, s):08X} -> {u32(nl, s):08X}"
                                                                   for s in diff],
                         "tail_hex": tail.hex(), "lvl_fnv": f"{fnv(nl):016x}",
                         "lvl_sha256": hashlib.sha256(nl).hexdigest(), "ptr_length": len(np_), "ptr_n": n2,
                         "ptr_new_slots": [f"0x{s - 4:X}" for s in nslots], "ptr_fnv": f"{fnv(np_):016x}",
                         "ptr_sha256": hashlib.sha256(np_).hexdigest(), "waypoint": WPOS[variant]}
    res["capacity"] = (bp.words_for(AREA + N) - bp.words_for(AREA)) * 4 == N and N + 8 * K <= FREE0 - 868496
    prod = (TOOLS / "m33_mod_overlay.h").read_text(encoding="utf-8")
    res["production_refuses_growth"] = ('kGrowNames[] = {"VS.sub"}' in prod and "intro_10" not in prod
                                        and "G3A" not in prod and "E465" not in prod)
    gate = (Path(__file__).resolve().parent / "g3a_test_grow_patch.py").read_text(encoding="utf-8")
    res["gate_bounds"] = ('intro_10.lvl\\", 7661836, 65536}' in gate and 'intro_10.ptr\\", 209068, 4096}' in gate
                          and N <= 65536 and 8 * K <= 4096)
    out = {"checks": res, "pass": all(res.values()), "constructions": desc, "M": M, "MP": MP}
    d = ROOT / "private" / "work" / PREFIX
    d.mkdir(parents=True, exist_ok=True)
    (d / "offline.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0 if out["pass"] else 1


def write_plan(work, data, ptr, variant):
    nl, np_, _, _ = construct(data, ptr, variant)
    lb, pb = work / "lvl_range.bin", work / "ptr_range.bin"
    lb.write_bytes(nl)
    pb.write_bytes(np_)
    plan = work / "plan.txt"
    plan.write_text("R3HD_MOD_PLAN 1\n# E-469 test-only plan (g3b_ab.py)\nmod e469.g3b 1.0.0\n"
                    f"file {SIZE} {LVL}\nfile {PSIZE} {PTR}\n"
                    f"grow 0 {len(nl)}\nrange 0 0 {len(nl)} {ORIG_FNV} {fnv(nl):016x} e469.g3b {lb}\n"
                    f"grow 1 {len(np_)}\nrange 1 0 {len(np_)} {PTR_FNV} {fnv(np_):016x} e469.g3b {pb}\n"
                    "gameplay e469.g3b\nend 2 2\n", encoding="utf-8")
    return plan


def run_case(tag, case):
    from m5_live import Actor, Process
    data, ptr = g3a.files()
    work = ROOT / "private" / "work" / PREFIX / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_E465_TEST_GROW", GATE_ENV[0]):
        env.pop(k, None)
    row = {"case": case, "run": run}
    if case != "base":
        env["R3HD_MODS_PLAN"] = row["plan"] = str(write_plan(work, data, ptr,
                                                             "neutral" if case == "neutral" else "offset"))
    if case in GROWN:
        env[GATE_ENV[0]] = GATE_ENV[1]
    (work / "steps.txt").write_text(f"wait {SECONDS - 8}\n", encoding="ascii")
    states, tails, samples = [], [], []
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(SECONDS), "--play", "--test-level",
                                 "intro_10", "--user-root", run], cwd=ROOT, env=env, stdout=log,
                                stderr=subprocess.STDOUT)
        t0 = time.monotonic()
        base = pid = None
        while time.monotonic() < t0 + 60 and game.poll() is None and (base is None or pid is None):
            lp, pj = RUNS / run / "runtime.log", RUNS / run / "process.json"
            if base is None and lp.is_file():
                mm = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", lp.read_text(errors="replace"))
                base = mm.group(1) if mm else None
            if pid is None and pj.is_file():
                try:
                    pid = json.loads(pj.read_text(encoding="utf-8-sig"))["pid"]
                except Exception:
                    pid = None
            time.sleep(0.02)
        if base is None or pid is None:
            row["error"] = "process not found"
        else:
            p = Process(pid, int(base, 16))
            area, last, deadline = None, None, t0 + 45
            while time.monotonic() < deadline and p.running() and area is None:
                ar = bp.areas(p)
                key = json.dumps({k: (v["base"], v["end"]) for k, v in (ar or {}).items()})
                if ar is not None and key != last:
                    last = key
                    s = bp.snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="areas_changed", area_keys=sorted(ar))
                    states.append(s)
                    a1 = s.get("areas", {}).get(1)
                    if a1 and a1["length"] in (AREA, AREA + N):
                        area = a1
                        blob = p.read(int(a1["base"], 16), AREA)
                        if blob:
                            blob = bytearray(blob)
                            for sl in list(CHANGED) + [COUNT_AT]:
                                blob[sl - 4:sl] = b"\0" * 4
                        row["original_readback_sha256"] = hashlib.sha256(blob).hexdigest() if blob else None
                time.sleep(0.005)
            if area is None:
                row["error"] = "level area not seen"
            else:
                row["area"] = area
                ab = int(area["base"], 16)

                def rd(a):
                    w = p.words(a, 1)
                    if not w:
                        raise ValueError(f"read {a:#x}")
                    return w[0]

                def live(label):
                    r = {"changed": [p.words(ab + s - 4, 1)[0] for s in list(CHANGED) + [COUNT_AT]],
                         "orig_wp": [(p.read(ab + w - 4, 0x14) or b"").hex() for w in (WP13, WP14)],
                         "tail": (p.read(ab + AREA, N) or b"").hex() if area["length"] == AREA + N else None}
                    try:
                        nodes, prob, hdr = walk_null(rd, ab + GRAPH - 4)
                        al = rd(ab + NODE13 - 4 + 0x18)
                        r["graph"] = {"problems": prob, "nodes": nodes, "header": hdr,
                                      "arc13": {"count": rd(al + 8), "target": rd(rd(al) + 0xC)}}
                    except Exception as x:
                        r["graph"] = {"error": repr(x)}
                    row[label] = r
                disc = work / "discovery.json"
                q = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc),
                                    "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
                live("live_first")
                gen = None
                for a in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if q.returncode == 0 else []):
                    try:
                        act = Actor(p, int(a["so"], 16))
                    except Exception:
                        continue
                    if act.model == GEN and act.mind:
                        gen = act
                        break
                if gen is None:
                    row["error"] = "generator not found"
                t_end, next_tail = time.monotonic() + WATCH, 0.0
                while time.monotonic() < t_end and p.running():
                    now = time.monotonic()
                    if area["length"] == AREA + N and now >= next_tail:
                        b = p.read(ab + AREA, N)
                        tails.append({"t": round(now - t0, 3), "hex": b.hex() if b else None})
                        next_tail = now + 1.0
                    if gen is not None:
                        try:
                            v = gen.dsg()
                            samples.append({"t": round(now - t0, 3), "pos": gen.position(),
                                            "v8": u32(*v[8]), "v9": u32(*v[9]),
                                            "v10": struct.unpack_from(">3f", *v[10])})
                        except Exception as x:
                            row["sampling_stopped"] = type(x).__name__
                            gen = None
                    time.sleep(0.1)
                if p.running():
                    live("live_end")
                    s = bp.snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="final", area_keys=sorted(bp.areas(p) or {}))
                    states.append(s)
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and g3a.alive(pid))
    for name, obj in (("states", states), ("tails", tails), ("samples", samples), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1) + "\n")
    return row


def judge(tag):
    data, ptr = g3a.files()
    to_path = g3a.to_path
    out = {}
    for case in CASES:
        work = ROOT / "private" / "work" / PREFIX / tag / case
        run = f"{PREFIX}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        for k in ("states", "tails", "samples"):
            row[k] = json.loads((work / f"{k}.json").read_text())
        log = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / run).glob("runtime*.log")))
        row["grow_size"] = sorted(set(re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)))
        row["grow_reads"] = re.findall(r"M36 grow read file=(\S+) offset=(\d+) length=(\d+) host=(\d+) served=(\d+)"
                                       r" kind=(\S+)", log)
        row["served_files"] = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
        row["mods_off"] = "M33 mods=off" in log
        row["refused"] = "grow_not_allowed" in log
        row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
        judges = {}
        for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
            r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True,
                               text=True)
            judges[tool] = r.returncode
            (work / f"{tool}.log").write_text(r.stdout + r.stderr)
        row["judges"] = judges
        out[case] = row
    A, B, C, D = (out[c] for c in CASES)

    def abase(r):
        return int(r["area"]["base"], 16) if r.get("area") else None
    invalid = [c for c, r in out.items() if r.get("error") or not r["samples"]
               or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60]
    t_close = min(A["samples"], key=lambda s: math.dist(s["pos"], W13))["t"] if A["samples"] else 0
    invalid += [c for c, r in out.items() if r["samples"] and r["samples"][0]["t"] >= t_close and c not in invalid]
    start = max(r["samples"][0]["t"] for r in out.values() if r["samples"]) + 0.5 if not invalid else 0

    def pts(r):
        return [s["pos"] for s in r["samples"] if s["t"] >= start]
    pathA = [s["pos"] for s in A["samples"] if s["t"] >= start - 1.0]
    pathB = [s["pos"] for s in B["samples"] if s["t"] >= start - 1.0]

    def maxdev(r, path, region=None, inside=None):
        o = [(to_path(q, path), q) for q in pts(r)]
        if region is not None:
            o = [x for x in o if (math.dist(x[1], M) > region) != bool(inside)]
        return max(o, key=lambda x: x[0][0]) if o else None

    def closest(r, target):
        q = pts(r)
        return to_path(target, q)[0] if len(q) > 1 else None

    # N1
    want_sizes = sorted([("intro_10.lvl", str(SIZE), str(SIZE + N)), ("intro_10.ptr", str(PSIZE), str(PSIZE + 8 * K))])
    n1 = all(out[c]["grow_size"] == want_sizes and out[c]["served_files"] == ["intro_10.lvl", "intro_10.ptr"]
             and {x[0] for x in out[c]["grow_reads"]} == {"intro_10.lvl", "intro_10.ptr"}
             and all(x[5] == "tail" for x in out[c]["grow_reads"]) for c in GROWN)
    n1 = n1 and not A["grow_size"] and A["mods_off"] and not D["grow_size"] and D["refused"]
    shas = {c: r.get("original_readback_sha256") for c, r in out.items()}
    n1 = n1 and shas["base"] is not None and len(set(shas.values())) == 1
    tail_ok = {}
    for c in GROWN:
        ab = abase(out[c])
        exp = bytearray(construct(data, ptr, c)[2])
        for s in construct(data, ptr, c)[3]:
            o = s - SIZE
            struct.pack_into(">I", exp, o, (u32(exp, o) + ab) & 0xFFFFFFFF)
        free = set(range(4 + 0x10, 4 + 0x18))     # N +0x10 / +0x14 (run-time capabilities): recorded only

        def fixed(h):
            if not h:
                return False
            b = bytes.fromhex(h)
            return len(b) == N and all(b[i] == exp[i] for i in range(N) if i not in free)
        ts = out[c]["tails"]
        tail_ok[c] = {"reads": len(ts), "all_fixed_equal": all(fixed(t["hex"]) for t in ts),
                      "span": round(ts[-1]["t"] - ts[0]["t"], 2) if ts else 0,
                      "N_caps_seen": sorted({t["hex"][40:56] for t in ts if t["hex"]})}
        for k in ("live_first", "live_end"):
            tail_ok[c][k] = fixed((out[c].get(k) or {}).get("tail"))
    n1 = n1 and all(v["reads"] >= 55 and v["all_fixed_equal"] and v["span"] >= 55 for v in tail_ok.values())
    want_wp = [data[w:w + 0x14].hex() for w in (WP13, WP14)]
    n1 = n1 and all((r.get("live_end") or {}).get("orig_wp") == want_wp for r in out.values())
    # N2
    def n2_case(c):
        r, ab = out[c], abase(out[c])
        if not ab:
            return False
        grown = c in GROWN
        want = [ab + (FN - 4 if grown else CHANGED[s] ) for s in CHANGED] + [144 if grown else 143]
        return all((r.get(k) or {}).get("changed") == want and (not grown or tail_ok[c][k])
                   for k in ("live_first", "live_end"))
    n2 = all(n2_case(c) for c in CASES)
    # N3 / N4
    reg = {}
    for c in CASES:
        r, ab = out[c], abase(out[c])
        grown = c in GROWN
        ok3 = ok4 = bool(ab)
        for k in ("live_first", "live_end"):
            gr = (r.get(k) or {}).get("graph") or {}
            nodes = gr.get("nodes") or []
            ok3 = ok3 and gr.get("problems") == [] and len(nodes) == (144 if grown else 143) \
                and len(set(nodes)) == len(nodes)
            if grown:
                a_nodes = ((A.get(k) or {}).get("graph") or {}).get("nodes") or []
                ok3 = ok3 and len(nodes) > 14 and nodes[14] == ab + FN - 4 and nodes[:14] + nodes[15:] == a_nodes \
                    and gr["header"]["first"] == A[k]["graph"]["header"]["first"] \
                    and gr["header"]["last"] == A[k]["graph"]["header"]["last"]
                ok4 = ok4 and gr.get("arc13") == {"count": 1, "target": ab + FN - 4}
            else:
                ok4 = ok4 and gr.get("arc13") == {"count": 1, "target": ab + NODE14 - 4}
        reg[c] = {"N3": ok3, "N4": ok4}
    n3 = all(v["N3"] for v in reg.values())
    n4 = all(v["N4"] for v in reg.values())   # N's own list / arc words are part of the tail check (N1 / N2)
    # N5
    near = lambda p, q: all(abs(p[i] - q[i]) <= 1e-4 for i in range(3))   # noqa: E731
    visits = {}
    for c, r in out.items():
        ab = abase(r) or 0
        wn, w13, w14 = ab + FW - 4, ab + WP13 - 4, ab + WP14 - 4
        s = r["samples"]
        at = [x for x in s if x["v8"] == wn]
        ins = [(s[i - 1]["v8"], s[i]["v8"]) for i in range(1, len(s)) if s[i]["v8"] != s[i - 1]["v8"]]
        into = [a for a, b in ins if b == wn]
        outof = [b for a, b in ins if a == wn]
        visits[c] = {"samples": len(at), "into_from_13": sum(1 for a in into if a == w13), "into": len(into),
                     "out_to_14": sum(1 for b in outof if b == w14), "out": len(outof),
                     "v10": sorted({tuple(round(v, 4) for v in x["v10"]) for x in at}),
                     "_ok_v10": any(near(x["v10"], WPOS.get(c, (0, 0, 0))) for x in at) if c in GROWN else None}
    n5 = (all(visits[c]["samples"] >= 3 and visits[c]["into"] >= 2 and visits[c]["into"] == visits[c]["into_from_13"]
              and visits[c]["out"] >= 2 and visits[c]["out"] == visits[c]["out_to_14"] and visits[c]["_ok_v10"]
              for c in GROWN)
          and all(visits[c]["samples"] == 0 for c in ("base", "nogate")))
    for v in visits.values():
        v.pop("_ok_v10")
    summary = {}
    if not invalid:
        cAp, cBp = closest(A, MP), closest(B, MP)
        fB, fBo = maxdev(B, pathA), maxdev(B, pathA, 25)
        fD = maxdev(D, pathA)
        fC, fCo, fCB = maxdev(C, pathA), maxdev(C, pathA, 25), maxdev(C, pathB)
        summary = {
            "neutral": {"max_off_A": round(fB[0][0], 3), "at_dist_to_M": round(math.dist(fB[1], M), 2),
                        "max_off_A_outside_25": round(fBo[0][0], 3) if fBo else 0.0,
                        "closest_to_M": round(closest(B, M), 3), "closest_to_Mp": round(cBp, 3)},
            "nogate": {"max_off_A": round(fD[0][0], 3)},
            "offset": {"max_off_A": round(fC[0][0], 3), "at_dist_to_M": round(math.dist(fC[1], M), 2),
                       "toward_Mp": sum((fC[1][i] - fC[0][1][i]) * (MP[i] - M[i]) for i in range(3)) > 0,
                       "max_off_A_outside_25": round(fCo[0][0], 3) if fCo else 0.0,
                       "max_off_B": round(fCB[0][0], 3), "closest_to_Mp": round(closest(C, MP), 3)},
            "base": {"closest_to_M": round(closest(A, M), 3), "closest_to_Mp": round(cAp, 3),
                     "closest_to_W13": round(closest(A, W13), 3)}}
        nb, oc = summary["neutral"], summary["offset"]
        n6 = nb["max_off_A"] <= 1.0 and nb["max_off_A_outside_25"] <= 0.5 and summary["nogate"]["max_off_A"] <= 0.5
        n7 = (oc["max_off_A"] >= 1.5 and oc["at_dist_to_M"] <= 25 and oc["toward_Mp"] is True
              and oc["closest_to_Mp"] <= cAp - 1.0 and oc["closest_to_Mp"] <= cBp - 1.0
              and oc["max_off_B"] >= 1.5 and oc["max_off_A_outside_25"] <= 0.5)
    else:
        n6 = n7 = False

    def walk_ok(r):
        st = r["states"]
        i = next((k for k, x in enumerate(st) if "invalid" not in x), None)
        return i is not None and not any("invalid" in x for x in st[i:])
    alloc = {}
    for c, r in out.items():
        used = [s for s in r["states"] if "invalid" not in s and "1" in s.get("areas", {})]
        L = AREA + (N if c in GROWN else 0)
        alloc[c] = {"length": (r.get("area") or {}).get("length"), "words": (r.get("area") or {}).get("words"),
                    "free_after": used[-1]["free_bytes"] if used else None}
        alloc[c]["ok"] = (walk_ok(r) and alloc[c]["length"] == L and alloc[c]["words"] == bp.words_for(L)
                          and bool(used) and all(s["areas"]["1"]["length"] == L for s in used)
                          and alloc[c]["free_after"] == FREE0 - (N if c in GROWN else 0))
    n8 = all(a["ok"] for a in alloc.values()) and all(
        r["haptics_policy"] and not any(r["judges"].values()) and r["runner_exit"] == 0 and not r["process_left"]
        for r in out.values())
    checks = {"N1_resource": bool(n1), "N2_relocation": bool(n2), "N3_registration": bool(n3), "N4_arcs": bool(n4),
              "N5_consumption": bool(n5), "N6_neutral": bool(n6), "N7_effect": bool(n7), "N8_safety": bool(n8)}
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()), "start": start,
              "summary": summary, "visits": visits, "registration": reg, "alloc": alloc, "readback_sha256": shas,
              "tails": tail_ok,
              "live": {c: {k: {x: y for x, y in (r.get(k) or {}).items() if x != "graph"} |
                           {"graph": {x: y for x, y in ((r.get(k) or {}).get("graph") or {}).items() if x != "nodes"}}
                           for k in ("live_first", "live_end")} for c, r in out.items()},
              "grow_size": {c: r["grow_size"] for c, r in out.items()},
              "grow_reads": {c: r["grow_reads"][:4] for c, r in out.items()},
              "served": {c: r["served_files"] for c, r in out.items()}, "nogate_refused": D["refused"],
              "judges": {c: r["judges"] for c, r in out.items()},
              "runner_exit": {c: r["runner_exit"] for c, r in out.items()}}
    (ROOT / "private" / "work" / PREFIX / tag / "judgement.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("invalid", "checks", "pass", "summary", "visits")}, indent=1))
    return 0 if result["pass"] else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return check()
    if len(sys.argv) > 2 and sys.argv[1] == "judge":
        return judge(sys.argv[2])
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--cases", default=",".join(CASES))
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", a.tag):
        ap.error("bad tag")
    for case in a.cases.split(","):
        print(json.dumps(run_case(a.tag, case)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
