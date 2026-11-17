#!/usr/bin/env python3
"""E-468 (D-235) G3a: graph node 13 of the intro_10 flight moved into appended storage, with five new `.ptr` entries
for its own pointer fields. Private, test-only (g3a_test_grow_patch.py); hidden and read-only at run time.

LOADER (static, LoadArea 827CDA58; `.ptr` part 827CDDFC..827CDF54)
`.ptr` length L from `_filelength`; temporary block-8 buffer 82189610(L, 0) filled from the CRT pre-read (820EB350);
n = buffer word 0; same-file loop over n entries {i32 file, u32 slot} at buffer + 4 (827CDE64): file 2 / 3 remapped
by 82103860, `*(base[area] + slot) += base[file]`; cross-file table at buffer + 4 + 8n, m = the `.lvl`'s first word
(827CDEC8): {off_a, file_a, off_b, file_b}, (slot, old value) saved in the m x 8 save table, `*(base[fa] + oa) =
base[fb] + ob`; buffer freed (82189958). No bounds, order or duplicate checks (a duplicate slot would be added
twice); L only sizes the buffer and the pre-read. So k new entries need n += k and the cross-file table moved by 8k.
STRUCTURE (static; `check` re-verifies from the files and fails closed)
intro_10.lvl 7,661,836 bytes (SHA-256 a37638bf...19e2ee, FNV 7982c1135516c2b6); intro_10.ptr 209,068 bytes
(SHA-256 6c9dd70c...8200e940, FNV 744dddc6c7d81e7b), n 25,143, m 495. Flight graph 0x542498 (143 nodes). Node 13 at file
0x542610, 0x1C bytes: +0 next -> node 14 (0x54262C), +4 previous -> node 12 (0x5425F4), +8 graph, +0xC waypoint
(0x545468, W), +0x10 / +0x14 0x00040000 (not pointers), +0x18 its arc list (0x54547C: one arc, to node 14, whose
+8 points back to the list, not the node). Exactly three pointers lead to node 13, all relocated own-file slots:
node 12 +0 (0x5425F4), node 14 +4 (0x542630), and the target (+0xC) of node 12's only arc (0x5454D4). No cross-file,
transit or fix pointer touches node 13; nothing points into it.
CONSTRUCTION (one logical node moved; node count and order unchanged; nothing added to the graph)
  .lvl 7,661,900 bytes (+64): the original, except the three incoming slots 0x0054260C -> 0x0074E90C; tail at
  7,661,836: 4 zero bytes, node copy at FN = 7,661,840 (0x74E910, same 16-byte alignment as node 13) = node 13's
  words with +0xC -> the waypoint copy (0x0074E934); 12 zero bytes; waypoint copy at FW = 7,661,880 (0x74E938,
  the waypoint's alignment): copy = identical, mod = x + 6 (byte 1 0x99 -> 0xC9, W'' = (25.207331, -32.903214,
  -40.101063)).
  .ptr 209,108 bytes (+40): n 25,143 -> 25,148; entries 0..25,142 unchanged; five new entries {1, slot} for the copy's
  +0, +4, +8, +0xC, +0x18 (slots 0x74E90C, 0x74E910, 0x74E914, 0x74E918, 0x74E924) after them; the 495-entry
  cross-file table byte-identical, moved by 40.
  Plan: per file `grow` + one range [0, new length) whose game-bytes hash is the original file's; `gameplay`.
  Incoming slots are .ptr entries 18,700 / 18,699 / 18,698 (values changed only). Served payloads: .lvl copy FNV
  83d602c36ddc63b0 (SHA-256 ab9321da...e59d84c7), mod 09e24c126e209aa0 (15a9d548...b5d217d8ac); .ptr (both)
  26f144f85e2a8084 (184c69bf...a8ae7f3f). Offline gate 20/20 PASS, including a simulated relocation of the new
  .lvl / .ptr (own-file entries): 143-node walk forward and back, node 13 = the copy, no duplicate slot, and the
  relocated area equal to the original's except the three incoming slots.
EXPECTED live (area base B from the block-8 table; E-465a / E-467: 0x40F5509C): copy node at B + 0x74E90C, words
  {B+0x542628, B+0x5425F0, B+0x542494, B+0x74E934, 0x40000, 0x40000, B+0x545478}; waypoint copy at B + 0x74E934;
  the three incoming slots = B + 0x74E90C (copy, mod) or B + 0x54260C (base, nogate); original waypoint B + 0x545464.
CASES (one hidden run each; m9_license_run.py: hidden window, muted, no physical pad, isolated private profile,
  `--test-level intro_10`, no input, no captures; 150 s, generator sampled every 0.1 s for 75 s, tail every 1 s):
  A base: no plan.  B copy: copy plan + R3HD_G3A_TEST_GROW=intro_10.  C mod: mod plan + gate env.
  D nogate: mod plan, gate env unset (refused as a whole).
PROTOCOL (committed before any run; tolerances from E-464 / E-467: noise 0.15, tolerance 0.5, effect 1.5 / 1.0)
  R1 resource: B / C `M36 grow size` lines name exactly intro_10.lvl 7661836 -> 7661900 and intro_10.ptr 209068 -> 209108
     (no other file), grow reads only of those two, kind=tail; served files only those two; A `M33 mods=off`;
     D `grow_not_allowed` and no grow line; SHA-256 of the area's first 7,661,832 bytes at its first appearance with
     the three incoming slots zeroed equal in A, B, C, D; the tail's fixed bytes (pads, the five pointer words of the
     copy relocated as expected, the waypoint copy) equal at every read for 60 s (B, C; the copy's +0x10 / +0x14
     recorded, not judged); the original waypoint's live bytes equal the file's in all cases at the end.
  R2 new relocations: after load (first live read) and at the end, the copy's five pointer words = the EXPECTED
     relocated values (each needs its new entry; an unprocessed entry leaves a bare offset < 0x1000000) in B / C;
     the three incoming slots as EXPECTED in all cases; the live save table (495 x 8 bytes) identical in A, B, C, D
     (the moved cross-file table was read at its new place).
  R3 connectivity: at first read and at the end, walking the live graph from its first node by +0 gives 143
     distinct nodes, each with +8 = the graph and +4 = the node before, the 143rd = the graph's last and the count
     word 143; node 13 of the walk = the copy (B / C) or the original (A / D); node 12's arc target = that node.
  R4 consumption: generator variable 8 equals the waypoint copy's address (reachable only through the copy's +0xC,
     a new entry) in >= 3 samples and never the original waypoint's in B and C; the reverse in A and D; at those
     samples C's variable 10 = W'' (1e-4) at least once and never W; B's = W.
  R5 identical copy: B's path (after the latest first sample of the four runs + 0.5 s) within 0.5 of A's path and
     B's closest approach to W'' within 0.5 of A's; D the same.
  R6 effect: C's maximum distance from A's path >= 1.5 at a sample within 25 units of W, toward W''; C's closest
     approach to W'' >= 1.0 smaller than A's; C's samples more than 25 from W within 0.5 of A's path.
  R7 safety: valid block-8 walk in every snapshot after the first valid one; area 7,661,896 bytes, chunk words
     words_for(7,661,896) in B / C (7,661,832 in A / D); free after load 13,088,464 (B / C), 13,088,528 (A / D);
     haptics policy line, M21 / M22 / M23 0, runner exit 0, no game process left; gate reverted and rebuilt after.
  Invalid (new tag, not judged): file hashes differ, level not opened, area or generator not found, fewer than 60 s
  of samples, or a run's first sample after A's closest approach to W.
  Classes: R2 + R3 = relocation and connectivity; R4 = consumption; R6 = functional effect (not without R4).

usage: g3a_ab.py check | TAG [--cases base,copy,mod,nogate] | judge TAG
Outputs stay under private/work/e468/.
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

GAME = ROOT / "private" / "extracted" / "5841123F"
LDIR = GAME / "GAMEDATAbin" / "intro_10"
LVL, PTR = LDIR / "intro_10.lvl", LDIR / "intro_10.ptr"
RUNS = ROOT / "private" / "work" / "m6_runs"
PREFIX = "e468"
SIZE, PSIZE = 7661836, 209068
ORIG_SHA = "a37638bf1370357db21f33df5c4d37ae806b3c4b9f81b331503ba62d1b19e2ee"
ORIG_FNV = "7982c1135516c2b6"
PTR_SHA = "6c9dd70c488a1cac95efc0a55a6086255dae2d851bacd93f5abefdcc8200e940"
PTR_FNV = "744dddc6c7d81e7b"
GRAPH, NODE, NODE12, NODE14, WPO, ARCS13 = 0x542498, 0x542610, 0x5425F4, 0x54262C, 0x545468, 0x54547C
INCOMING = (0x5425F4, 0x542630, 0x5454D4)       # node 12 +0, node 14 +4, node 12's arc +0xC (file offsets)

N, K = 64, 5
FN, FW = SIZE + 4, SIZE + 44
NODE_FIELDS = (0, 4, 8, 0xC, 0x18)
AREA = SIZE - 4
N_ORIG, M = 25143, 495
W = (19.20733070373535, -32.90321350097656, -40.1010627746582)
W2 = (25.20733070373535, -32.90321350097656, -40.1010627746582)
W2X = bytes.fromhex("41c9a89d")
FREE0 = 13088528
SECONDS, WATCH = 150, 75
CASES = ("base", "copy", "mod", "nogate")
GEN = "NIN_m_GenFlyIntro_10"
GATE_ENV = ("R3HD_G3A_TEST_GROW", "intro_10")


def fnv(b):
    h = 0xCBF29CE484222325
    for x in b:
        h = ((h ^ x) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def files():
    data, ptr = LVL.read_bytes(), PTR.read_bytes()
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != ORIG_SHA or f"{fnv(data):016x}" != ORIG_FNV:
        raise SystemExit("file check: intro_10.lvl is not the protocol's file")
    if len(ptr) != PSIZE or hashlib.sha256(ptr).hexdigest() != PTR_SHA or f"{fnv(ptr):016x}" != PTR_FNV:
        raise SystemExit("file check: intro_10.ptr is not the protocol's file")
    return data, ptr


def construct(data, ptr, variant):
    """(new .lvl, new .ptr, tail): every change of the protocol and nothing else."""
    new = bytearray(data)
    for s in INCOMING:
        new[s:s + 4] = struct.pack(">I", FN - 4)
    node = bytearray(data[NODE:NODE + 0x1C])
    node[0xC:0x10] = struct.pack(">I", FW - 4)
    wp = data[WPO:WPO + 0x14]
    wcopy = wp if variant == "copy" else W2X + wp[4:]
    tail = b"\0" * 4 + bytes(node) + b"\0" * 12 + wcopy
    assert len(tail) == N and SIZE + 4 == FN and FN + 0x1C + 12 == FW
    n = u32(ptr, 0)
    entries = b"".join(struct.pack(">iI", 1, FN - 4 + k) for k in NODE_FIELDS)
    nptr = struct.pack(">I", n + K) + ptr[4:4 + 8 * n] + entries + ptr[4 + 8 * n:]
    return bytes(new) + tail, nptr, tail


def relocate(lvl, ptr, base1):
    """Offline model of 827CDE64 for own-file entries (file 1): returns the relocated area words as a dict
    {area offset: value} for every own-file slot, plus the set of slots relocated more than once."""
    n = u32(ptr, 0)
    area = bytearray(lvl[4:])
    seen, dup = set(), set()
    for i in range(n):
        f, slot = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        if f != 1:
            continue
        if slot in seen:
            dup.add(slot)
        seen.add(slot)
        struct.pack_into(">I", area, slot, (u32(area, slot) + base1) & 0xFFFFFFFF)
    return bytes(area), seen, dup


def walk_graph(area, base1, graph_addr, read=None):
    """Walk a relocated graph (offline area bytes or live via read(addr, 4)) -> (nodes, problems)."""
    rd = read or (lambda a: u32(area, a - base1))
    first, last, count = rd(graph_addr), rd(graph_addr + 4), rd(graph_addr + 8)
    nodes, prev, problems = [], None, []
    nd = first
    for i in range(count):
        if nd in nodes:
            problems.append(f"cycle at {i}")
            break
        if rd(nd + 8) != graph_addr:
            problems.append(f"node {i} graph")
        if i and rd(nd + 4) != prev:
            problems.append(f"node {i} previous")
        nodes.append(nd)
        prev, nd = nd, rd(nd)
    if count != 143 or len(nodes) != 143 or nodes[-1] != last:
        problems.append(f"count {count} / walked {len(nodes)} / last")
    back, nd = [], last
    for _ in range(count):
        back.append(nd)
        nd = rd(nd + 4)
    if back[::-1] != nodes:
        problems.append("backward walk differs")
    return nodes, problems


def check():
    """Offline safety gate (all-or-nothing): structure, construction and a simulated relocation."""
    data, ptr = files()
    n, m = u32(ptr, 0), u32(data, 0)
    res = {}
    ents = [struct.unpack_from(">iI", ptr, 4 + 8 * i) for i in range(n)]
    slots = {loc + 4: (f, i) for i, (f, loc) in enumerate(ents)}

    def target(o):
        return u32(data, o) + 4 if slots.get(o, (None,))[0] == 1 else None
    res["ptr_layout"] = n == N_ORIG and m == M and 4 + 8 * n + 16 * m == len(ptr) and len(slots) == n
    res["node13_fields"] = (target(NODE) == NODE14 and target(NODE + 4) == NODE12 and target(NODE + 8) == GRAPH
                            and target(NODE + 0xC) == WPO and target(NODE + 0x18) == ARCS13
                            and all(NODE + k in slots for k in NODE_FIELDS)
                            and not any(NODE + k in slots for k in (0x10, 0x14))
                            and u32(data, NODE + 0x10) == u32(data, NODE + 0x14) == 0x40000)
    into_node = sorted(o for o in slots if target(o) is not None and NODE <= target(o) < NODE + 0x1C)
    res["incoming_exactly_three"] = into_node == sorted(INCOMING) and all(target(o) == NODE for o in INCOMING)
    res["incoming_roles"] = (INCOMING[0] == NODE12 and INCOMING[1] == NODE14 + 4
                             and target(NODE12 + 0x18) is not None
                             and u32(data, target(NODE12 + 0x18) + 8) == 1
                             and target(target(NODE12 + 0x18)) == INCOMING[2] - 0xC)
    arcs_in = sorted(o for o in slots if target(o) == ARCS13)
    res["arc_list_owned"] = (arcs_in == sorted([NODE + 0x18, target(ARCS13) + 8]) and u32(data, ARCS13 + 8) == 1
                             and target(target(ARCS13) + 0xC) == NODE14)
    cross = [struct.unpack_from(">IiIi", ptr, 4 + 8 * n + 16 * j) for j in range(m)]
    res["no_cross_entry"] = not any((fa == 1 and NODE <= oa + 4 < NODE + 0x1C) or (fb == 1 and NODE <= ob + 4 < NODE + 0x1C)
                                    for oa, fa, ob, fb in cross)
    tl, tp = (LDIR / "transit.lvl").read_bytes(), (LDIR / "transit.ptr").read_bytes()
    res["no_transit_reference"] = not any(
        struct.unpack_from(">iI", tp, 4 + 8 * i)[0] == 1
        and NODE <= u32(tl, struct.unpack_from(">iI", tp, 4 + 8 * i)[1] + 4) + 4 < NODE + 0x1C
        for i in range(u32(tp, 0)))
    fp = (GAME / "GAMEDATAbin" / "fix.ptr").read_bytes()
    res["no_fix_reference"] = not any(struct.unpack_from(">iI", fp, 4 + 8 * i)[0] == 1 for i in range(u32(fp, 0)))
    wp = data[WPO:WPO + 0x14]
    res["waypoint_value"] = struct.unpack(">3f", wp[:12]) == W and wp[12:16] == b"\x3f\x80\0\0" and wp[16:] == b"\0" * 4
    res["w2_bits"] = struct.unpack(">f", W2X)[0] == W2[0]
    res["alignment"] = FN % 16 == NODE % 16 and FW % 16 == WPO % 16 and FN % 4 == 0
    B1 = 0x40F5509C
    base_area, _, _ = relocate(data, ptr, B1)
    nodes0, prob0 = walk_graph(base_area, B1, B1 + GRAPH - 4)
    res["original_graph_walk"] = not prob0 and nodes0[13] == B1 + NODE - 4
    desc = {}
    for variant in ("copy", "mod"):
        nl, np_, tail = construct(data, ptr, variant)
        diff = sorted({i & ~3 for i in range(SIZE) if nl[i] != data[i]})
        ok = len(nl) == SIZE + N and diff == sorted(INCOMING) and all(u32(nl, s) == FN - 4 for s in INCOMING)
        ok = ok and nl[SIZE:FN] == b"\0" * 4 and nl[FN + 0x1C:FW] == b"\0" * 12
        cn = nl[FN:FN + 0x1C]
        ok = ok and cn[:0xC] == data[NODE:NODE + 0xC] and cn[0x10:] == data[NODE + 0x10:NODE + 0x1C] \
            and u32(cn, 0xC) == FW - 4
        wc = nl[FW:FW + 0x14]
        cdiff = [i for i in range(0x14) if wc[i] != wp[i]]
        ok = ok and (cdiff == [] if variant == "copy" else cdiff == [1] and wc[:4] == W2X)
        res[f"lvl_{variant}"] = bool(ok)
        n2 = u32(np_, 0)
        new_ents = [struct.unpack_from(">iI", np_, 4 + 8 * i) for i in range(n, n2)]
        pok = (n2 == n + K and len(np_) == 4 + 8 * n2 + 16 * m == PSIZE + 8 * K
               and np_[4:4 + 8 * n] == ptr[4:4 + 8 * n] and np_[4 + 8 * n2:] == ptr[4 + 8 * n:]
               and new_ents == [(1, FN - 4 + k) for k in NODE_FIELDS]
               and not any(loc + 4 in slots for _, loc in new_ents)
               and len({loc for _, loc in new_ents}) == K
               and all(loc + 4 <= len(nl) - 4 and u32(nl, loc + 4) + 4 + 4 <= len(nl) for _, loc in new_ents))
        res[f"ptr_{variant}"] = bool(pok)
        area, seen, dup = relocate(nl, np_, B1)
        nodes, prob = walk_graph(area, B1, B1 + GRAPH - 4)
        copy_addr = B1 + FN - 4
        sim = (not dup and not prob and nodes[:13] == nodes0[:13] and nodes[14:] == nodes0[14:]
               and nodes[13] == copy_addr and u32(area, FN - 4 + 0xC) == B1 + FW - 4
               and u32(area, FN - 4 + 0x18) == B1 + ARCS13 - 4
               and u32(area, INCOMING[2] - 4) == copy_addr)
        same = [o for o in range(0, AREA, 4) if u32(area, o) != u32(base_area, o)]
        sim = sim and sorted(same) == sorted(s - 4 for s in INCOMING)
        res[f"simulated_relocation_{variant}"] = bool(sim)
        desc[variant] = {"lvl_length": len(nl), "lvl_changed_words": [f"0x{s:X}: 0054260C -> {FN - 4:08X}" for s in diff],
                         "tail_hex": tail.hex(), "lvl_fnv": f"{fnv(nl):016x}", "lvl_sha256": hashlib.sha256(nl).hexdigest(),
                         "ptr_length": len(np_), "ptr_n": n2, "ptr_new_entries": [f"{{1, 0x{loc:X}}}" for _, loc in new_ents],
                         "ptr_fnv": f"{fnv(np_):016x}", "ptr_sha256": hashlib.sha256(np_).hexdigest(),
                         "waypoint_copy_changed_bytes": cdiff}
    res["capacity"] = (bp.words_for(AREA + N) - bp.words_for(AREA)) * 4 == N and N + 8 * K <= FREE0 - 868496
    prod = (TOOLS / "m33_mod_overlay.h").read_text(encoding="utf-8")
    res["production_refuses_growth"] = ('kGrowNames[] = {"VS.sub"}' in prod and "intro_10" not in prod
                                        and "G3A" not in prod and "E465" not in prod)
    out = {"checks": res, "pass": all(res.values()), "constructions": desc,
           "ptr_fnv": f"{fnv(ptr):016x}", "incoming_ptr_entries": [slots[s][1] for s in INCOMING]}
    d = ROOT / "private" / "work" / PREFIX
    d.mkdir(parents=True, exist_ok=True)
    (d / "offline.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0 if out["pass"] else 1


def write_plan(work, data, ptr, variant):
    nl, np_, _ = construct(data, ptr, variant)
    lb, pb = work / "lvl_range.bin", work / "ptr_range.bin"
    lb.write_bytes(nl)
    pb.write_bytes(np_)
    plan = work / "plan.txt"
    plan.write_text("R3HD_MOD_PLAN 1\n# E-468 test-only plan (g3a_ab.py)\nmod e468.g3a 1.0.0\n"
                    f"file {SIZE} {LVL}\nfile {PSIZE} {PTR}\n"
                    f"grow 0 {len(nl)}\nrange 0 0 {len(nl)} {ORIG_FNV} {fnv(nl):016x} e468.g3a {lb}\n"
                    f"grow 1 {len(np_)}\nrange 1 0 {len(np_)} {PTR_FNV} {fnv(np_):016x} e468.g3a {pb}\n"
                    "gameplay e468.g3a\nend 2 2\n", encoding="utf-8")
    return plan


def alive(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in r.stdout


def game_left(pid, run, wait=5.0, image="r3hd.exe"):
    """G5-P5b (E-483 revision 1): (left, detail). `alive(pid)` alone cannot tell a surviving game from a process still
    tearing down after its exit was reported, or from another program that got the same pid. Left = `wait` seconds
    after the runner ended, an r3hd.exe whose command line names this run (its --log_file) still exists. The detail
    keeps the immediate pid-only result and who holds the pid then."""
    import time as _t
    detail = {"pid_alive_immediately": bool(pid and alive(pid))}
    _t.sleep(wait)
    ps = ("$r = @(Get-CimInstance Win32_Process -Filter \"Name='" + image + "'\" | Where-Object { $_.CommandLine -like '*"
          + run + "*' } | ForEach-Object { $_.ProcessId }) -join ','; "
          "$h = Get-CimInstance Win32_Process -Filter \"ProcessId=" + str(int(pid or 0)) + "\"; "
          "Write-Output ($r + '|' + $(if ($h) { $h.Name } else { '' }))")
    q = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    left_ids, _, holder = q.stdout.strip().partition("|")
    detail.update(run_game_processes=left_ids, pid_holder_after_wait=holder or None, wait_s=wait)
    return bool(left_ids) or q.returncode != 0, detail


def run_case(tag, case):
    from m5_live import Actor, Process
    data, ptr = files()
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
        env["R3HD_MODS_PLAN"] = row["plan"] = str(write_plan(work, data, ptr, "copy" if case == "copy" else "mod"))
    if case in ("copy", "mod"):
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
                m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", lp.read_text(errors="replace"))
                base = m.group(1) if m else None
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
                            for sl in INCOMING:
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
                    return w[0] if w else None

                def live(label):
                    r = {"incoming": [rd(ab + s - 4) for s in INCOMING],
                         "orig_wp": (p.read(ab + WPO - 4, 0x14) or b"").hex(),
                         "copy_node": list(p.words(ab + FN - 4, 7) or []) if area["length"] == AREA + N else None,
                         "save_table_sha256": None}
                    sv = p.read(int(area["save"], 16), area["count"] * 8) if area.get("save") else None
                    r["save_table_sha256"] = hashlib.sha256(sv).hexdigest() if sv else None
                    try:
                        nodes, prob = walk_graph(None, ab, ab + GRAPH - 4, read=rd)
                        arc12 = rd(rd(ab + NODE12 - 4 + 0x18))
                        r["graph"] = {"problems": prob, "count": len(nodes), "node13": nodes[13] if len(nodes) > 13 else None,
                                      "arc12_target": rd(arc12 + 0xC) if arc12 else None}
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
        row["process_left"] = bool(pid and alive(pid))
    for name, obj in (("states", states), ("tails", tails), ("samples", samples), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1) + "\n")
    return row


def seg(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]
    n2 = sum(v * v for v in ab)
    t = 0.0 if not n2 else max(0.0, min(1.0, sum((p[i] - a[i]) * ab[i] for i in range(3)) / n2))
    q = [a[i] + t * ab[i] for i in range(3)]
    return math.dist(p, q), q


def to_path(p, path):
    return min((seg(p, a, b) for a, b in zip(path, path[1:])), key=lambda x: x[0])


def judge(tag):
    data, ptr = files()
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
    grown = ("copy", "mod")
    invalid = [c for c, r in out.items() if r.get("error") or not r["samples"]
               or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60]
    t_close = min(A["samples"], key=lambda s: math.dist(s["pos"], W))["t"] if A["samples"] else 0
    invalid += [c for c, r in out.items() if r["samples"] and r["samples"][0]["t"] >= t_close and c not in invalid]
    start = max(r["samples"][0]["t"] for r in out.values() if r["samples"]) + 0.5 if not invalid else 0
    path = [s["pos"] for s in A["samples"] if s["t"] >= start - 1.0]

    def pts(r):
        return [s["pos"] for s in r["samples"] if s["t"] >= start]

    def maxdev(r, region=None):
        o = [(to_path(q, path), q) for q in pts(r)]
        if region is not None:
            o = [x for x in o if math.dist(x[1], W) > region]
        return max(o, key=lambda x: x[0][0]) if o else None

    def closest(r, target):
        q = pts(r)
        return to_path(target, q)[0] if len(q) > 1 else None

    def abase(r):
        return int(r["area"]["base"], 16) if r.get("area") else None

    def expect_node(ab):
        return [ab + 0x542628, ab + 0x5425F0, ab + 0x542494, ab + FW - 4, 0x40000, 0x40000, ab + 0x545478]

    # R1
    want_sizes = sorted([("intro_10.lvl", str(SIZE), str(SIZE + N)), ("intro_10.ptr", str(PSIZE), str(PSIZE + 8 * K))])
    r1 = all(out[c]["grow_size"] == want_sizes and out[c]["served_files"] == ["intro_10.lvl", "intro_10.ptr"]
             and {x[0] for x in out[c]["grow_reads"]} == {"intro_10.lvl", "intro_10.ptr"}
             and all(x[5] == "tail" for x in out[c]["grow_reads"]) for c in grown)
    r1 = r1 and not A["grow_size"] and A["mods_off"] and not D["grow_size"] and D["refused"]
    shas = {c: r.get("original_readback_sha256") for c, r in out.items()}
    r1 = r1 and shas["base"] is not None and len(set(shas.values())) == 1
    tail_ok = {}
    for c in grown:
        ab = abase(out[c])
        wc = construct(data, ptr, c)[2][FW - SIZE:]
        want = [ab + v if i in (0, 1, 2, 3, 6) else None for i, v in
                enumerate([0x542628, 0x5425F0, 0x542494, FW - 4, 0, 0, 0x545478])] if ab else None

        def fixed(h):
            if not h or not want:
                return False
            b = bytes.fromhex(h)
            nw = struct.unpack_from(">7I", b, 4)
            return (b[:4] == b"\0" * 4 and b[32:44] == b"\0" * 12 and b[44:] == wc
                    and all(want[i] is None or nw[i] == want[i] for i in range(7)))
        ts = out[c]["tails"]
        tail_ok[c] = {"reads": len(ts), "all_fixed_equal": all(fixed(t["hex"]) for t in ts),
                      "span": round(ts[-1]["t"] - ts[0]["t"], 2) if ts else 0,
                      "node_words_10_14": sorted({t["hex"][8 + 32:8 + 48] for t in ts if t["hex"]})}
    r1 = r1 and all(v["reads"] >= 55 and v["all_fixed_equal"] and v["span"] >= 55 for v in tail_ok.values())
    wp_hex = data[WPO:WPO + 0x14].hex()
    r1 = r1 and all((r.get("live_end") or {}).get("orig_wp") == wp_hex for r in out.values())
    # R2
    def r2_case(c):
        r, ab = out[c], abase(out[c])
        if not ab:
            return False
        ok = True
        for k in ("live_first", "live_end"):
            lv = r.get(k) or {}
            inc = ab + (FN - 4 if c in grown else NODE - 4)
            ok = ok and lv.get("incoming") == [inc] * 3
            if c in grown:
                cn = lv.get("copy_node") or []
                ok = ok and len(cn) == 7 and all(cn[i] == expect_node(ab)[i] for i in (0, 1, 2, 3, 6))
        return ok
    saves = {c: [(r.get(k) or {}).get("save_table_sha256") for k in ("live_first", "live_end")] for c, r in out.items()}
    r2 = all(r2_case(c) for c in CASES) and saves["base"][0] is not None and \
        len({s for v in saves.values() for s in v}) == 1
    # R3
    def r3_case(c):
        r, ab = out[c], abase(out[c])
        want13 = ab + (FN - 4 if c in grown else NODE - 4) if ab else None
        return all((r.get(k) or {}).get("graph", {}).get("problems") == [] and r[k]["graph"]["count"] == 143
                   and r[k]["graph"]["node13"] == want13 and r[k]["graph"]["arc12_target"] == want13
                   for k in ("live_first", "live_end"))
    r3 = all(r3_case(c) for c in CASES)
    # R4
    v8 = {}
    for c, r in out.items():
        ab = abase(r) or 0
        cp = [s for s in r["samples"] if s["v8"] == ab + FW - 4]
        og = [s for s in r["samples"] if s["v8"] == ab + WPO - 4]
        v8[c] = {"copy_samples": len(cp), "orig_samples": len(og), "_cp": cp,
                 "v10_at_copy": sorted({tuple(round(x, 4) for x in s["v10"]) for s in cp}),
                 "v10_at_orig": sorted({tuple(round(x, 4) for x in s["v10"]) for s in og})}
    near = lambda p, q: all(abs(p[i] - q[i]) <= 1e-4 for i in range(3))   # noqa: E731
    r4 = (all(v8[c]["copy_samples"] >= 3 and v8[c]["orig_samples"] == 0 for c in grown)
          and all(v8[c]["orig_samples"] >= 3 and v8[c]["copy_samples"] == 0 for c in ("base", "nogate"))
          and any(near(s["v10"], W2) for s in v8["mod"]["_cp"]) and not any(near(s["v10"], W) for s in v8["mod"]["_cp"])
          and any(near(s["v10"], W) for s in v8["copy"]["_cp"]))
    for c in v8:
        del v8[c]["_cp"]
    summary = {}
    if not invalid:
        cA2 = closest(A, W2)
        for c in ("copy", "mod", "nogate"):
            f, fo = maxdev(out[c]), maxdev(out[c], 25)
            summary[c] = {"max_off": round(f[0][0], 3) if f else None,
                          "max_off_dist_to_W": round(math.dist(f[1], W), 2) if f else None,
                          "max_off_toward_W2": (sum((f[1][i] - f[0][1][i]) * (W2[i] - W[i]) for i in range(3)) > 0)
                          if f else None,
                          "max_off_outside_25": round(fo[0][0], 3) if fo else 0.0,
                          "closest_to_W2": round(closest(out[c], W2), 3)}
        summary["base"] = {"closest_to_W2": round(cA2, 3), "closest_to_W": round(closest(A, W), 3), "t_closest_W": t_close}
        r5 = all(summary[c]["max_off"] is not None and summary[c]["max_off"] <= 0.5
                 and abs(summary[c]["closest_to_W2"] - cA2) <= 0.5 for c in ("copy", "nogate"))
        m = summary["mod"]
        r6 = (m["max_off"] >= 1.5 and m["max_off_dist_to_W"] <= 25 and m["max_off_toward_W2"] is True
              and m["closest_to_W2"] <= cA2 - 1.0 and m["max_off_outside_25"] <= 0.5)
    else:
        r5 = r6 = False

    # R7
    def walk_ok(r):
        st = r["states"]
        i = next((k for k, x in enumerate(st) if "invalid" not in x), None)
        return i is not None and not any("invalid" in x for x in st[i:])
    alloc = {}
    for c, r in out.items():
        used = [s for s in r["states"] if "invalid" not in s and "1" in s.get("areas", {})]
        L = AREA + (N if c in grown else 0)
        alloc[c] = {"length": (r.get("area") or {}).get("length"), "words": (r.get("area") or {}).get("words"),
                    "free_after": used[-1]["free_bytes"] if used else None}
        alloc[c]["ok"] = (walk_ok(r) and alloc[c]["length"] == L and alloc[c]["words"] == bp.words_for(L)
                          and bool(used) and all(s["areas"]["1"]["length"] == L for s in used)
                          and alloc[c]["free_after"] == FREE0 - (N if c in grown else 0))
    r7 = all(a["ok"] for a in alloc.values()) and all(
        r["haptics_policy"] and not any(r["judges"].values()) and r["runner_exit"] == 0 and not r["process_left"]
        for r in out.values())
    checks = {"R1_resource": bool(r1), "R2_new_relocations": bool(r2), "R3_connectivity": bool(r3),
              "R4_consumption": bool(r4), "R5_identical_copy": bool(r5), "R6_effect": bool(r6),
              "R7_safety": bool(r7)}
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()), "start": start,
              "summary": summary, "var8": v8, "alloc": alloc, "readback_sha256": shas, "save_table_sha256": saves,
              "tails": tail_ok, "live": {c: {k: r.get(k) for k in ("live_first", "live_end")} for c, r in out.items()},
              "grow_size": {c: r["grow_size"] for c, r in out.items()},
              "grow_reads": {c: r["grow_reads"][:4] for c, r in out.items()},
              "served": {c: r["served_files"] for c, r in out.items()}, "nogate_refused": D["refused"],
              "judges": {c: r["judges"] for c, r in out.items()},
              "runner_exit": {c: r["runner_exit"] for c, r in out.items()}}
    (ROOT / "private" / "work" / PREFIX / tag / "judgement.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))
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
