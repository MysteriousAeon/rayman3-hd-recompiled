#!/usr/bin/env python3
"""E-471 (D-238) G4b: one additional NIN_m_Lums_Int10 lum in intro_10 (60 -> 61 dynamic-world actors). Private,
test-only (G3a gate reused for intro_10.lvl / .ptr growth; transit.lvl as a same-size range); hidden, read-only.

STATIC FINDINGS (guest code; see the report)
A1 personal index (StdGame +8): index into the level's personal object-type list, a linked list of 0x14-byte
   elements {next, previous, -> header, -> name, flags} whose header {first, last, count} is level `0x1C74` (69
   elements, indices 0..68, all used; copied with the family / model headers (record kind 195, 36 bytes, level
   0x1C5C) into the engine globals 0x82C061E0..). Readers: 8212F6C8(i) (byte +17 of element i, NO null check),
   8212F6F0(i) (name); callers 82126DE0, 822A6950, 822A5918 (byte +17 into the set at 0x82BD6C20; every element's
   byte +17 is 0xFF), 8227C4E8 (name). A new index therefore needs its own element: index 69, element copied from
   the source's (flags 02FF0000), new name, count 69 -> 70.
A2a SO record list: header at level 0x5A7434 {first, last, count 122, +0xC} reached from level 0x1CFC (copied to
   global 0x82876314); records 0x48 {+0 next, +4 -> SuperObject, +8 / +9 / +0x46 state bytes}. 82114D08(so) finds an
   SO's record (0 if none), 82114CB0(so) its index; 82114D50 resets state; 82117A98 removes (count - 1); 82115DC8 /
   82117B18 (object-state save / restore) walk it. Every actor has exactly one; the walk stops at next 0 or self.
   New actor: one new record at the end (index 122), count 123.
A2b backup (snapshot) list: {first, last} at level 0x1CEC (kind 218, global 0x82C44A78); records 0x18 {+0, +4 link
   to the next record's +4, +8 -> data, +0xC -> copy, +0x10 size 0x54, +0x14 type 0x50320200}; 822196D8 finds a
   record by address, 822199D8 inserts one at run time (reinit backups). New actor: one record for the copy's
   matrix with its own 0x54-byte copy (words byte-swapped as in the file), linked after the last record.
A3 transit: dynamic world (transit 0x9B4) count +0x10 = 60 -> 61; first / last child unchanged (cross-file entries
   untouched; the copy is inserted mid-chain); a same-size transit.lvl range (no growth, production rules).
B ownership: Brain +4 = 0xCDCDCDCD is WRITTEN by the brain initializer 82123FB8 (a sentinel, not an allocation);
   the only init-time allocation found is 3dData's 821257F0 (n x 6 bytes at 3dData +160 = block +0x14C, file 0):
   the copy gets its own at init. All 14 in-block pointers are rebased; 16 shared model / family / table pointers
   and the transit parent keep their values.
CONSTRUCTION (`check` re-verifies everything from the files and fails closed)
  Source lum SO 0x549A30 (personal index in SRC_PERSONAL, 112.8 units from the flight path, not progression-critical),
  block 1,208 bytes. Copy at file FC (16-byte congruent with the source), inserted after the source in the sibling
  chain (source +0x14 and its next's +0x18 -> copy). Personal element (0x14) + name string, SO record (0x48),
  backup record (0x18) + copy (0x54) appended after the copy. Changed original words: source +0x14, next +0x18,
  personal header last / count (0x1C78 / 0x1C7C), old last personal element +0 (0 -> new; new .ptr entry),
  SO-record header last / count (0x5A7438 / 0x5A743C), old last SO record +0 (new entry), backup header last
  (0x1CF0), old last backup link (new entry); transit 0x9C4 60 -> 61. Positions (all four translation copies:
  matrix +0x34, second matrix, component 8, backup copy byte-swapped):
  B off path: source + (0, 0, 5); C on path: (17.87, -101.22, -44.18) (E-469 k1 base path at t 11.6 s, 31 units
  before the first junction pass, 29.5 from the nearest lum); E = C + generator variable 5 initial value 5
  (initial and current buffer byte +328, the E-460 edit) so that collecting the copy gives 6 at the junction and
  ends the flight (level change to intro_15 = unload of the grown intro_10).
CASES (hidden, muted, no pad, private profile, --test-level intro_10, no input, no captures; 150 s; generator every
  0.1 s for 75 s; copy / source blocks and lists every 1 s): A base; B off path + gate; C on path + gate;
  D gate off (C plan: refused as a whole); E C + variable 5 = 5 + gate.
PROTOCOL (committed before any run)
  A1 resource: B / C / E grow lines exactly intro_10.lvl SIZE -> SIZE + N and intro_10.ptr PSIZE -> PSIZE + 8 K;
     served files exactly intro_10.lvl, intro_10.ptr, transit.lvl; A mods off; D refused (grow_not_allowed), no grow
     line, nothing served; read-back of the area's first 7,661,832 bytes at first appearance with every changed word
     zeroed equal in all five cases.
  A2 registration (B, C, E at the first live read; B also at the end; C's end state is recorded, not judged, because
     a collected lum may legitimately leave the dynamic world): dynamic-world count word 61 and the walk
     (+8, +0x14 until 0) = 61 distinct SuperObjects = A's 60 with the copy inserted right after the source; previous
     links consistent; SO-record list: walk count = header count = 123, the copy's record last; backup list contains
     a record whose +8 is the copy's matrix; personal list count 70, element 69's name = the new name. A / D: 60, 122,
     69 and no copy.
  A3 initialization (first live read): copy and source block words re-relocated as expected for every in-file
     pointer; the set of block offsets whose live value differs from the relocated file value is the same for the
     copy and the source in B (both idle); in all grown cases the copy's 3dData buffer word (block +0x14C) is non-zero
     and differs from the source's, and Brain +4 reads 0xCDCDCDCD in both.
  A4 activity: in C and E, the copy's block changes between the last 1-s read before variable 5 increments and the
     first read after it (the pickup query processed the copy), while the source block shows no change at those
     offsets in that interval.
  A5 collection: variable 5 = 0 throughout in A, B, D; in C it becomes exactly 1 once, at a sample within 2 s of the
     generator's closest approach to the copy's position (closest approach <= 3.0 units), and stays 1; in E it goes
     from 5 to 6 at such a sample and the level changes to intro_15 within 120 s of level open.
  A6 isolation: in every case the source SuperObject is in the walk (A2) with its file translation; its personal
     index (live StdGame +8) unchanged; the copy's addresses are all inside the appended tail; B's / C's walk minus the copy = A's walk.
  A7 allocation and cleanup: valid block-8 walks in every snapshot after the first valid one; intro_10 area length
     SIZE - 4 + N in B / C / E, SIZE - 4 in A / D; free after load in B / C within [FREE0 - N - 4096, FREE0 - N]
     (exact value recorded); in E after the change to intro_15: intro_10's area gone, intro_15's area 8,474,196 bytes
     at 0x40F5F320 and free 12,234,744 (E-465a's measured values), walk valid.
  A8 safety: haptics policy line, M21 / M22 / M23 0, runner exit 0, no process left; gate reverted and rebuilt.
  Invalid (new tag): file hashes differ, level not opened, area / generator not found, < 60 s of samples.
  Stop: an engine error line or crash in any case -> record PC / code / case, no rerun without a new hypothesis.

OFFLINE GATE (before commit): 18 / 18 PASS. .lvl 7,661,836 -> 7,663,280 (N 1,444; copy at 7,661,840), .ptr 209,068 ->
  209,388 (40 new entries: 31 copy block, 3 personal element, 1 old last element, 1 SO record, 1 old last record,
  2 backup record, 1 old last link); changed original words 0x1C78 0x1C7C 0x1CF0 0x539320 0x549A44 0x549F00 0x5A59D4
  0x5A7438 0x5A743C 0x5A9648 (+ 0x542494 / 0x545908 bytes in E); transit 0x9C7 only. FNV: .lvl off 02d022e0dd1553ff,
  on 1029cf4b9a2ada31, exit 7d0b815fd47c4bc1; .ptr e728b3f2447b944d; transit 9f32154370bee13a (original
  4f45f6827e7cc035). New personal index 69. B position (87.605, -223.54, -43.848).

REVISION after run m1 (recorded in E-471; applies to fresh runs only):
  m1 INVALID (all five cases: no generator samples): harness defect, the level-change detector compared
  block8_probe.areas()' integer base with the snapshot's hex string and fired at once, stopping all sampling
  (fixed: integer comparison). m1's structural reads also showed three INVALID CRITERIA (they would have failed in
  any run): (1) at run time the dynamic world holds only the ACTIVE actors (live count 23 in A / B / D, 24 in C / E
  with the copy), the others are moved to the inactive dynamic world (global 0x82C07D78, transit 0xA34) by the
  activation code, so "count 61 / walk 61" is a wrong prediction; (2) the same moves rewrite sibling links, so the
  source's +0x18 differs from the file in A3's comparison; (3) A6's walk equality has the same flaw. Revised (judged
  only on fresh runs):
  A2r: at the first live read (and B at the end) the union U of the children of the dynamic world (0x82C05F48) and
     the inactive dynamic world (0x82C07D78) has no SuperObject twice; U(grown case) = U(A) + the copy exactly;
     the copy is in the dynamic world in C and E and in the same list as the source in B; SO-record list count =
     walk = 123 with the copy's record last; backup list has the copy's matrix; personal count 70, last name new.
     A / D: U = U(A) (D: same set), 122, 69, no copy.
  A3r: as A3 with the link words +0x14 / +0x18 / +0x1C excluded from both difference sets.
  A6r: as A6 with U(case) minus the copy = U(A) (sets) instead of the walk equality.
  A1, A4, A5, A7, A8 unchanged.
REVISION 2 after run m2 (recorded in E-471; fresh runs only; m2 keeps A4 / A5 FAIL):
  m2: A1, A2r, A3r, A6r, A7, A8 PASS; A4, A5 FAIL. Causes: A4 assumed an idle source lum is static, but 7 of its
  block words change between 1-s reads in every lum (per-frame processing), so "no source change at those offsets"
  is a wrong prediction (the copy also changed 10 offsets the source did not: pickup-specific); A5 took the
  generator's closest approach to the copy's spot over the whole run, but the flight passes that spot every loop
  (after the copy is gone), so the global minimum (0.047 at 60.3 s) is not the pickup pass (the increment was at
  11.4 s; E's 5 -> 6 at 11.2 s with 1.5 units at that time). Revised:
  A4r: B: the copy and the source change at the same non-empty set of block offsets between consecutive 1-s reads
     over the run; C and E: the copy changes at least one offset across the pickup interval that the source does
     not change in that interval.
  A5r: as A5, with the distance condition taken as the minimum generator-to-copy distance over samples within 2 s
     of the first variable-5 change (<= 3.0) instead of the whole-run closest approach.
  All other criteria (A1, A2r, A3r, A6r, A7, A8) unchanged.
REVISION 3 after run m3 (recorded in E-471; fresh runs only; m3 keeps A4r FAIL):
  m3: A1, A2r, A3r, A5r, A6r, A7, A8 PASS; A4r FAIL only because B's source changing-offset set contains +0x18 (its
  previous-sibling link, rewritten by activation moves of its neighbour) and the copy's does not: the link-word
  exclusion of A3r was omitted from A4r (same cause as revision 1's A3 finding). Revised A4r: the B comparison
  excludes the link words +0x14 / +0x18 / +0x1C, as A3r does. Nothing else changed.

usage: g4b_ab.py check | TAG [--cases base,off,on,nogate,exit] | judge TAG
Outputs stay under private/work/e471/.
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
import g3a_ab as g3a  # noqa: E402

LVL, PTR, GAME, LDIR, RUNS = g3a.LVL, g3a.PTR, g3a.GAME, g3a.LDIR, g3a.RUNS
TRANSIT = LDIR / "transit.lvl"
TPTR = LDIR / "transit.ptr"
PREFIX = "e471"
SIZE, PSIZE, AREA = g3a.SIZE, g3a.PSIZE, g3a.AREA
ORIG_FNV, PTR_FNV = g3a.ORIG_FNV, g3a.PTR_FNV
TSIZE, TSHA = 41508, "d300ba3a4a3c03cec6a73eb9da8a8d820fcc3a669591e976b357e804315bf275"
u32, fnv = g3a.u32, g3a.fnv
SRC, BLK = 0x549A30, 0x4B8
DW, DW_COUNT = 0x9B4, 0x9C4
PHDR = 0x1C74                     # personal object-type list header {first, last, count}
RHDR = 0x5A7434                   # SO record list header {first, last, count, ...}
BHDR = 0x1CEC                     # backup list {first link, last link}
NEW_NAME = b"NIN_m_Lums_Int10_G4B\0\0\0\0"
GEN_INIT_OFF = None               # generator instance initial / current + 328 (resolved in gen_offsets)
POS_C = (17.87, -101.22, -44.18)
G_DW, G_REC, G_BAK, G_OBJ = 0x82C05F48, 0x82876314, 0x82C44A78, 0x82C061E0
G_INACT = 0x82C07D78
FREE0 = g3a.FREE0
SECONDS, WATCH = 150, 75
CASES = ("base", "off", "on", "nogate", "exit")
GROWN = ("off", "on", "exit")
GEN = g3a.GEN
GATE_ENV = g3a.GATE_ENV
f32 = lambda v: struct.unpack(">f", struct.pack(">f", v))[0]   # noqa: E731


def files():
    data, ptr = g3a.files()
    tl = TRANSIT.read_bytes()
    if len(tl) != TSIZE or hashlib.sha256(tl).hexdigest() != TSHA:
        raise SystemExit("file check: transit.lvl is not the protocol's file")
    return data, ptr, tl


def index(data, ptr):
    n = u32(ptr, 0)
    slots = {}
    for i in range(n):
        f, loc = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        slots[loc + 4] = f
    cross = [struct.unpack_from(">IiIi", ptr, 4 + 8 * n + 16 * j) for j in range(u32(data, 0))]
    return slots, cross


def tgt(data, slots, o):
    return (slots[o], u32(data, o) + 4) if o in slots else None


def gen_offsets():
    import waypoint_ab
    ix, key, e, nodes = waypoint_ab.role()
    inst = ix["defaults"][key]["instances"][0]
    return inst["initial"] + 328, inst["current"] + 328


def layout(data, slots):
    """File offsets of everything new, appended after SIZE (alignments as the originals)."""
    pad = (SRC % 16 - SIZE % 16) % 16
    fc = SIZE + pad                                   # copy block (same 16-byte phase as the source)
    pe = fc + BLK                                     # personal element (0x14), 4-aligned
    name = pe + 0x14                                  # 24 bytes
    rec = name + len(NEW_NAME)                        # SO record (0x48)
    bak = rec + 0x48                                  # backup record (0x18)
    bcopy = bak + 0x18                                # 0x54 copy
    end = bcopy + 0x54
    end += (-end) % 16
    return {"pad": pad, "fc": fc, "pe": pe, "name": name, "rec": rec, "bak": bak, "bcopy": bcopy, "end": end}


def chain_last(data, slots, start, link_off=0):
    """Follow own-file pointers at +link_off from start until 0; returns the last node."""
    c, seen = start, set()
    while True:
        seen.add(c)
        t = tgt(data, slots, c + link_off)
        if not t or t[0] != 1 or t[1] in seen:
            return c
        c = t[1]


def construct(data, ptr, tl, variant):
    """(new lvl, new ptr, new transit, info) for variant off / on / exit."""
    slots, cross = index(data, ptr)
    L = layout(data, slots)
    fc = L["fc"]
    new = bytearray(data) + bytearray(L["end"] - SIZE)
    newslots = []                                     # (file, slot file offset) in order

    def put(o, v):
        struct.pack_into(">I", new, o, v)
    # 1. copy block, rebasing in-block pointers
    blk = bytearray(data[SRC:SRC + BLK])
    for o in range(SRC, SRC + BLK, 4):
        if o in slots:
            f, a = tgt(data, slots, o)
            if f == 1 and SRC <= a < SRC + BLK:
                struct.pack_into(">I", blk, o - SRC, a - SRC + fc - 4)
            newslots.append((f, o - SRC + fc))
    new[fc:fc + BLK] = blk
    nxt = tgt(data, slots, SRC + 0x14)[1]
    put(fc + 0x14, nxt - 4)                            # copy.next = source's old next
    put(fc + 0x18, SRC - 4)                            # copy.prev = source
    put(SRC + 0x14, fc - 4)                            # source.next = copy
    put(nxt + 0x18, fc - 4)                            # next.prev = copy
    # translation in all four copies
    pos = (tuple(f32(x) for x in struct.unpack_from(">3f", data, SRC + 0xC4 + 0x34)[:2])
           + (f32(struct.unpack_from(">f", data, SRC + 0xC4 + 0x3C)[0] + 5.0),)) if variant == "off" \
        else tuple(f32(x) for x in POS_C)
    for o in (0xC4 + 0x34, 0x260 + 0x34, 0x498):
        struct.pack_into(">3f", new, fc + o, *pos)
    # 2. personal element + name
    pfirst, plast = tgt(data, slots, PHDR)[1], tgt(data, slots, PHDR + 4)[1]
    pcount = u32(data, PHDR + 8)
    src_std = tgt(data, slots, tgt(data, slots, SRC + 4)[1] + 4)[1]
    new_index = pcount
    put(fc + (src_std - SRC) + 8, new_index)          # copy StdGame personal index
    pe = L["pe"]
    tmpl, k = pfirst, u32(data, src_std + 8)
    for _ in range(k):
        tmpl = tgt(data, slots, tmpl)[1]
    new[pe:pe + 0x14] = data[tmpl:tmpl + 0x14]
    put(pe, 0)
    put(pe + 4, plast - 4)
    put(pe + 0xC, L["name"] - 4)
    new[L["name"]:L["name"] + len(NEW_NAME)] = NEW_NAME
    newslots += [(1, pe + 4), (1, pe + 8), (1, pe + 0xC)]
    put(plast, pe - 4)
    newslots.append((1, plast))                        # old last element +0: 0 -> new (new entry)
    put(PHDR + 4, pe - 4)
    put(PHDR + 8, pcount + 1)
    # 3. SO record
    rlast = tgt(data, slots, RHDR + 4)[1]
    rec = L["rec"]
    srec = [x - 4 for x in slots if slots[x] == 1 and u32(data, x) + 4 == SRC and x - 4 != SRC + 0x14 - 4
            and u32(data, x + 4) == 0x01000000][0]
    new[rec:rec + 0x48] = data[srec:srec + 0x48]
    put(rec, 0)
    put(rec + 4, fc - 4)
    newslots.append((1, rec + 4))
    put(rlast, rec - 4)
    newslots.append((1, rlast))
    put(RHDR + 4, rec - 4)
    put(RHDR + 8, u32(data, RHDR + 8) + 1)
    # 4. backup record + copy (link at +4; the list links point at the next record's +4)
    blink = tgt(data, slots, BHDR + 4)[1]              # last link (a record's +4)
    src_bak = [x for x in slots if slots[x] == 1 and tgt(data, slots, x)[1] == SRC + 0xC4 and x != SRC + 0x20]
    sb = src_bak[0] - 8
    bak = L["bak"]
    new[bak:bak + 0x18] = data[sb:sb + 0x18]
    put(bak + 4, 0)
    put(bak + 8, fc + 0xC4 - 4)
    put(bak + 0xC, L["bcopy"] - 4)
    newslots += [(1, bak + 8), (1, bak + 0xC)]
    scopy = tgt(data, slots, sb + 0xC)[1]
    bc = bytearray(data[scopy:scopy + 0x54])
    for i, v in enumerate(pos):                        # byte-swapped translation words (matrix +0x34)
        bc[0x34 + 4 * i:0x38 + 4 * i] = struct.pack(">f", v)[::-1]
    new[L["bcopy"]:L["bcopy"] + 0x54] = bc
    put(blink, bak + 4 - 4)
    newslots.append((1, blink))
    put(BHDR + 4, bak + 4 - 4)
    # 5. generator variable 5 (exit only)
    if variant == "exit":
        for o in gen_offsets():
            new[o] = 5
    # .ptr: same-file entries appended after the n-list
    n = u32(ptr, 0)
    entries = b"".join(struct.pack(">iI", f, s - 4) for f, s in newslots)
    nptr = struct.pack(">I", n + len(newslots)) + ptr[4:4 + 8 * n] + entries + ptr[4 + 8 * n:]
    ntl = bytearray(tl)
    struct.pack_into(">I", ntl, DW_COUNT, u32(tl, DW_COUNT) + 1)
    info = {"layout": L, "newslots": newslots, "next": nxt, "personal_template": tmpl, "src_record": srec, "new_index": new_index, "pos": pos, "src_std": src_std,
            "plast": plast, "rlast": rlast, "blink": blink, "src_backup": sb, "src_backup_copy": scopy}
    return bytes(new), nptr, bytes(ntl), info


def simulate(lvl, ptr, tl, base1=0x40F5509C, base2=0x40F4AE78):
    """Relocate own-file and transit-parent entries; walk the dynamic world, record, backup and personal lists."""
    area, seen, dup = g3a.relocate(lvl, ptr, base1)
    slots, cross = index(lvl, ptr)
    rd = lambda a: u32(area, a - base1)               # noqa: E731
    first = last = None
    for oa, fa, ob, fb in cross:
        if fa == 2 and oa + 4 == DW + 8:
            first = base1 + ob
        if fa == 2 and oa + 4 == DW + 0xC:
            last = base1 + ob
    walk, so = [], first
    while so and len(walk) < 1000:
        walk.append(so)
        so = rd(so + 0x14)
    prev_ok = all(rd(b + 0x18) == a for a, b in zip(walk, walk[1:]))
    recs, r = [], rd(base1 + RHDR - 4)
    while r and len(recs) < 1000:
        recs.append(r)
        nx = rd(r)
        if nx == r:
            break
        r = nx
    links, l_ = [], rd(base1 + BHDR - 4)
    while l_ and len(links) < 1000:
        links.append(l_)
        l_ = rd(l_)
    pel, e = [], rd(base1 + PHDR - 4)
    while e and len(pel) < 1000:
        pel.append(e)
        e = rd(e)
    return {"area": area, "rd": rd, "dup": dup, "walk": walk, "last": last, "prev_ok": prev_ok,
            "dw_count": u32(tl, DW_COUNT), "recs": recs, "rec_count": rd(base1 + RHDR - 4 + 8),
            "rec_last": rd(base1 + RHDR - 4 + 4), "links": links, "bak_last": rd(base1 + BHDR - 4 + 4),
            "pel": pel, "p_count": rd(base1 + PHDR - 4 + 8), "p_last": rd(base1 + PHDR - 4 + 4)}


def check():
    data, ptr, tl = files()
    slots, cross = index(data, ptr)
    res = {}
    B1 = 0x40F5509C
    s0 = simulate(data, ptr, tl)
    res["original_lists"] = (len(s0["walk"]) == 60 == s0["dw_count"] and s0["walk"][-1] == s0["last"]
                             and s0["prev_ok"] and len(s0["recs"]) == s0["rec_count"] == 122
                             and s0["recs"][-1] == s0["rec_last"] and s0["links"][-1] == s0["bak_last"]
                             and len(s0["pel"]) == s0["p_count"] == 69 and s0["pel"][-1] == s0["p_last"])
    res["source_is_lum"] = (u32(data, SRC) == 2 and B1 + SRC - 4 in s0["walk"]
                            and tgt(data, slots, tgt(data, slots, tgt(data, slots, tgt(data, slots, SRC + 4)[1]
                                                                                + 0xC)[1])[1]) == (1, 0x547D7C)
                            and math.dist(struct.unpack_from(">3f", data, SRC + 0xC4 + 0x34), POS_C) > 100)
    census = {"in": 0, "ext": 0, "f2": 0}
    for o in range(SRC, SRC + BLK, 4):
        if o in slots:
            f, a = tgt(data, slots, o)
            census["in" if f == 1 and SRC <= a < SRC + BLK else ("ext" if f == 1 else "f2")] += 1
    res["source_census_31"] = census == {"in": 14, "ext": 16, "f2": 1}
    outside = [o for o in slots if slots[o] == 1 and not SRC <= o < SRC + BLK
               and SRC <= u32(data, o) + 4 < SRC + BLK]
    nx = tgt(data, slots, SRC + 0x14)[1]
    pv = tgt(data, slots, SRC + 0x18)[1]
    sb = [x for x in outside if u32(data, x) + 4 == SRC + 0xC4]
    rec = [x for x in outside if u32(data, x) + 4 == SRC and x not in (nx + 0x18, pv + 0x14)]
    res["incoming_known"] = (sorted(outside) == sorted([nx + 0x18, pv + 0x14] + rec + sb) and len(rec) == 1
                             and len(sb) == 1 and not any((fb == 1 and SRC <= ob + 4 < SRC + BLK)
                                                          or (fa == 1 and SRC <= oa + 4 < SRC + BLK)
                                                          for oa, fa, ob, fb in cross))
    desc = {}
    for variant in GROWN:
        nl, np_, ntl, info = construct(data, ptr, tl, variant)
        L = info["layout"]
        s1 = simulate(nl, np_, ntl)
        copy_so = B1 + L["fc"] - 4
        walk0 = [x for x in s1["walk"] if x != copy_so]
        ok = (not s1["dup"] and len(s1["walk"]) == 61 == s1["dw_count"] and len(set(s1["walk"])) == 61
              and s1["prev_ok"] and walk0 == s0["walk"] and s1["walk"][-1] == s1["last"]
              and s1["walk"][s1["walk"].index(B1 + SRC - 4) + 1] == copy_so
              and len(s1["recs"]) == s1["rec_count"] == 123 and s1["recs"][-1] == s1["rec_last"] == B1 + L["rec"] - 4
              and s1["rd"](s1["recs"][-1] + 4) == copy_so and s1["recs"][:-1] == s0["recs"]
              and s1["links"][-1] == s1["bak_last"] == B1 + L["bak"] and s1["links"][:-1] == s0["links"]
              and s1["rd"](B1 + L["bak"] + 4) == copy_so + 0xC4
              and len(s1["pel"]) == s1["p_count"] == 70 and s1["pel"][:-1] == s0["pel"]
              and s1["pel"][-1] == B1 + L["pe"] - 4)
        res[f"lists_{variant}"] = bool(ok)
        # copy block: every relocated word points where the source's does (rebased in-block) ; independent
        rd = s1["rd"]
        cok = True
        for k in range(0, BLK, 4):
            so_, co_ = SRC + k, L["fc"] + k
            if so_ in slots:
                f, a = tgt(data, slots, so_)
                if k in (0x14, 0x18):
                    continue
                want = (B1 + a - 4) if f == 1 and not SRC <= a < SRC + BLK else \
                    (B1 + a - SRC + L["fc"] - 4 if f == 1 else None)
                if f == 1 and rd(B1 + co_ - 4) != want:
                    cok = False
            elif k not in (0xC4 + 0x34, 0xC4 + 0x38, 0xC4 + 0x3C, 0x260 + 0x34, 0x260 + 0x38, 0x260 + 0x3C,
                           0x498, 0x49C, 0x4A0) and k != info["src_std"] - SRC + 8:
                cok = cok and nl[co_:co_ + 4] == data[so_:so_ + 4]
        cok = cok and u32(nl, L["fc"] + info["src_std"] - SRC + 8) == 69 and u32(nl, L["fc"] + 0x14C) == 0 \
            and u32(nl, L["fc"] + 0x31C) == u32(data, SRC + 0x31C)
        res[f"copy_block_{variant}"] = bool(cok)
        # every changed original word is in the approved list; transit only the count
        approved = {SRC + 0x14, info["next"] + 0x18, PHDR + 4, PHDR + 8, info["plast"], RHDR + 4, RHDR + 8,
                    info["rlast"], BHDR + 4, info["blink"]}
        if variant == "exit":
            approved |= set(o & ~3 for o in gen_offsets())
        diff = {i & ~3 for i in range(SIZE) if nl[i] != data[i]}
        res[f"changes_{variant}"] = diff == approved and [i for i in range(TSIZE) if ntl[i] != tl[i]] == \
            list(range(DW_COUNT + 3, DW_COUNT + 4))
        newslots = [s for _, s in info["newslots"]]
        n = u32(ptr, 0)
        res[f"ptr_{variant}"] = (len(set(newslots)) == len(newslots) == 40 and not any(s in slots for s in newslots)
                                 and np_[4:4 + 8 * n] == ptr[4:4 + 8 * n]
                                 and np_[4 + 8 * (n + 40):] == ptr[4 + 8 * n:]
                                 and len(np_) == PSIZE + 8 * 40 and len(nl) == SIZE + L["end"] - SIZE)
        desc[variant] = {"lvl_len": len(nl), "ptr_len": len(np_), "N": L["end"] - SIZE, "layout": L,
                         "copy_so_file": L["fc"], "pos": info["pos"], "new_index": info["new_index"],
                         "changed_words": sorted(f"0x{x:X}" for x in diff),
                         "lvl_fnv": f"{fnv(nl):016x}", "ptr_fnv": f"{fnv(np_):016x}", "transit_fnv": f"{fnv(ntl):016x}",
                         "lvl_sha256": hashlib.sha256(nl).hexdigest(), "ptr_sha256": hashlib.sha256(np_).hexdigest()}
    N = desc["on"]["N"]
    res["capacity"] = N <= 65536 and 8 * 40 <= 4096 and N + 4096 <= FREE0 - 868496
    prod = (TOOLS / "m33_mod_overlay.h").read_text(encoding="utf-8")
    res["production_refuses_growth"] = ('kGrowNames[] = {"VS.sub"}' in prod and "intro_10" not in prod
                                        and "G3A" not in prod)
    out = {"checks": res, "pass": all(res.values()), "constructions": desc, "source_census": census,
           "transit_fnv": f"{fnv(tl):016x}"}
    d = ROOT / "private" / "work" / PREFIX
    d.mkdir(parents=True, exist_ok=True)
    (d / "offline.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0 if out["pass"] else 1


def mask_words(data, ptr, tl):
    """Original-file words any variant changes (zeroed in the read-back comparison)."""
    i = construct(data, ptr, tl, "on")[3]
    return {SRC + 0x14, i["next"] + 0x18, PHDR + 4, PHDR + 8, i["plast"], RHDR + 4, RHDR + 8, i["rlast"],
            BHDR + 4, i["blink"]} | set(o & ~3 for o in gen_offsets())


def write_plan(work, data, ptr, tl, variant):
    nl, np_, ntl, info = construct(data, ptr, tl, variant)
    paths = {k: work / f"{k}_range.bin" for k in ("lvl", "ptr", "transit")}
    paths["lvl"].write_bytes(nl)
    paths["ptr"].write_bytes(np_)
    paths["transit"].write_bytes(ntl)
    plan = work / "plan.txt"
    plan.write_text("R3HD_MOD_PLAN 1\n# E-471 test-only plan (g4b_ab.py)\nmod e471.g4b 1.0.0\n"
                    f"file {SIZE} {LVL}\nfile {PSIZE} {PTR}\nfile {TSIZE} {TRANSIT}\n"
                    f"grow 0 {len(nl)}\nrange 0 0 {len(nl)} {ORIG_FNV} {fnv(nl):016x} e471.g4b {paths['lvl']}\n"
                    f"grow 1 {len(np_)}\nrange 1 0 {len(np_)} {PTR_FNV} {fnv(np_):016x} e471.g4b {paths['ptr']}\n"
                    f"range 2 0 {TSIZE} {fnv(tl):016x} {fnv(ntl):016x} e471.g4b {paths['transit']}\n"
                    "gameplay e471.g4b\nend 3 3\n", encoding="utf-8")
    return plan, info


def run_case(tag, case):
    from m5_live import Actor, Process
    data, ptr, tl = files()
    work = ROOT / "private" / "work" / PREFIX / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_E465_TEST_GROW", GATE_ENV[0]):
        env.pop(k, None)
    row = {"case": case, "run": run}
    variant = {"off": "off", "on": "on", "nogate": "on", "exit": "exit"}.get(case)
    info = None
    if variant:
        plan, info = write_plan(work, data, ptr, tl, variant)
        env["R3HD_MODS_PLAN"] = row["plan"] = str(plan)
    if case in GROWN:
        env[GATE_ENV[0]] = GATE_ENV[1]
    L = layout(data, index(data, ptr)[0])
    MASK = mask_words(data, ptr, tl)
    (work / "steps.txt").write_text(f"wait {SECONDS - 8}\n", encoding="ascii")
    states, reads, samples = [], [], []
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
                    if a1 and a1["length"] >= AREA:
                        area = a1
                        blob = p.read(int(a1["base"], 16), AREA)
                        if blob:
                            blob = bytearray(blob)
                            for o in MASK:
                                blob[o - 4:o] = bytes(4)
                        row["original_readback_sha256"] = hashlib.sha256(blob).hexdigest() if blob else None
                time.sleep(0.005)
            if area is None:
                row["error"] = "level area not seen"
            else:
                row["area"] = area
                ab = int(area["base"], 16)

                def w(a):
                    x = p.words(a, 1)
                    if not x:
                        raise ValueError(f"read {a:#x}")
                    return x[0]

                def lists():
                    r = {}
                    try:
                        dw = w(G_DW)
                        walk, so = [], w(dw + 8)
                        while so and len(walk) < 400:
                            walk.append(so)
                            so = w(so + 0x14)
                        r["dw"] = {"so": dw, "count": w(dw + 0x10), "walk": walk, "last": w(dw + 0xC),
                                   "prev_ok": all(w(b + 0x18) == a for a, b in zip(walk, walk[1:]))}
                        iw = w(G_INACT)
                        iwalk, so = [], w(iw + 8)
                        while so and len(iwalk) < 400:
                            iwalk.append(so)
                            so = w(so + 0x14)
                        r["inactive"] = {"so": iw, "count": w(iw + 0x10), "walk": iwalk,
                                         "prev_ok": all(w(b + 0x18) == a for a, b in zip(iwalk, iwalk[1:]))}
                        h = w(G_REC)
                        recs, c = [], w(h)
                        while c and len(recs) < 1000:
                            recs.append([c, w(c + 4)])
                            nx = w(c)
                            if nx == c:
                                break
                            c = nx
                        r["rec"] = {"count": w(h + 8), "n": len(recs), "last_so": recs[-1][1] if recs else None,
                                    "index_of": {f"{so:08x}": i for i, (_, so) in enumerate(recs)}}
                        links, l_ = [], w(G_BAK)
                        while l_ and len(links) < 2000:
                            links.append(w(l_ + 4))
                            l_ = w(l_)
                        r["bak_targets"] = links
                        pc = w(G_OBJ + 0x20)
                        e, i = w(G_OBJ + 0x18), 0
                        while e and i < pc - 1:
                            e, i = w(e), i + 1
                        nm = p.read(w(e + 0xC), 24) if e else None
                        r["personal"] = {"count": pc, "last_name": nm.split(b"\0")[0].decode("ascii", "replace")
                                         if nm else None}
                    except Exception as x:
                        r["error"] = repr(x)
                    return r

                def blocks():
                    out = {"src": (p.read(ab + SRC - 4, BLK) or b"").hex()}
                    if area["length"] > AREA:
                        out["copy"] = (p.read(ab + L["fc"] - 4, BLK) or b"").hex()
                    return out
                disc = work / "discovery.json"
                q = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc),
                                    "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
                row["live_first"] = {"lists": lists(), "blocks": blocks()}
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
                t_end, next_read = time.monotonic() + WATCH, 0.0
                level_changed = False
                while time.monotonic() < t_end and p.running():
                    now = time.monotonic()
                    ar = bp.areas(p)
                    a1 = (ar or {}).get(1)
                    if a1 and a1["base"] != int(area["base"], 16) and not level_changed:
                        level_changed = True
                        row["level_change_t"] = round(now - t0, 3)
                        gen = None
                    if level_changed:
                        key = json.dumps({k: (v["base"], v["end"]) for k, v in (ar or {}).items()})
                        if key != last:
                            last = key
                            s = bp.snapshot(p)
                            s.update(t=round(now - t0, 3), state="after_change", area_keys=sorted(ar or {}))
                            states.append(s)
                        time.sleep(0.05)
                        continue
                    if now >= next_read:
                        reads.append({"t": round(now - t0, 3), **blocks()})
                        next_read = now + 1.0
                    if gen is not None:
                        try:
                            v = gen.dsg()
                            samples.append({"t": round(now - t0, 3), "pos": gen.position(), "v5": v[5][0][v[5][1]]})
                        except Exception as x:
                            row["sampling_stopped"] = type(x).__name__
                            gen = None
                    time.sleep(0.1)
                if p.running():
                    if not level_changed:
                        row["live_end"] = {"lists": lists(), "blocks": blocks()}
                    s = bp.snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="final", area_keys=sorted(bp.areas(p) or {}))
                    states.append(s)
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and g3a.alive(pid))
    for name, obj in (("states", states), ("reads", reads), ("samples", samples), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj) + "\n")
    return {k: v for k, v in row.items() if k not in ("live_first", "live_end")}


def judge(tag):
    data, ptr, tl = files()
    slots, _ = index(data, ptr)
    L = layout(data, slots)
    out = {}
    for case in CASES:
        work = ROOT / "private" / "work" / PREFIX / tag / case
        run = f"{PREFIX}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        for k in ("states", "reads", "samples"):
            row[k] = json.loads((work / f"{k}.json").read_text())
        log = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / run).glob("runtime*.log")))
        row["grow_size"] = sorted(set(re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)))
        row["served_files"] = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
        row["mods_off"] = "M33 mods=off" in log
        row["refused"] = "grow_not_allowed" in log
        row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
        row["lvl_opens"] = [o.rsplit("\\", 1)[-1].lower() for o in
                            re.findall(r"vfs_open path=(\S+?\.lvl) result=00000000", log)]
        judges = {}
        for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
            r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run], cwd=ROOT, capture_output=True,
                               text=True)
            judges[tool] = r.returncode
            (work / f"{tool}.log").write_text(r.stdout + r.stderr)
        row["judges"] = judges
        out[case] = row
    A = out["base"]
    invalid = [c for c, r in out.items() if r.get("error") or not r["samples"]
               or (c != "exit" and r["samples"][-1]["t"] - r["samples"][0]["t"] < 60)]
    info = {v: construct(data, ptr, tl, v)[3] for v in GROWN}
    N = L["end"] - SIZE
    K = 40

    def ab(r):
        return int(r["area"]["base"], 16) if r.get("area") else 0
    # A1
    want = sorted([("intro_10.lvl", str(SIZE), str(SIZE + N)), ("intro_10.ptr", str(PSIZE), str(PSIZE + 8 * K))])
    a1 = all(out[c]["grow_size"] == want and out[c]["served_files"] == ["intro_10.lvl", "intro_10.ptr", "transit.lvl"]
             for c in GROWN)
    a1 = a1 and A["mods_off"] and not A["grow_size"] and out["nogate"]["refused"] and not out["nogate"]["grow_size"] \
        and not out["nogate"]["served_files"]
    shas = {c: r.get("original_readback_sha256") for c, r in out.items()}
    a1 = a1 and shas["base"] is not None and len(set(shas.values())) == 1
    # A2r / A6r (revision after m1)
    def union(lst):
        d, i = lst.get("dw", {}), lst.get("inactive", {})
        both = d.get("walk", []) + i.get("walk", [])
        return set(both), len(both) == len(set(both)) and d.get("prev_ok") and i.get("prev_ok"),             set(d.get("walk", [])), set(i.get("walk", []))
    a_u = union(((A.get("live_first") or {}).get("lists")) or {})[0]
    reg = {}
    for c, r in out.items():
        b = ab(r)
        copy_so, src_so = b + L["fc"] - 4, b + SRC - 4
        ok, iso = bool(b), bool(b)
        for k in ("live_first", "live_end"):
            if k == "live_end" and c != "off":
                continue
            lst = ((r.get(k) or {}).get("lists")) or {}
            U, nodup, dws, ins = union(lst)
            rec, per = lst.get("rec", {}), lst.get("personal", {})
            ok = ok and nodup
            if c in GROWN:
                ok = ok and U == a_u | {copy_so} and copy_so not in a_u                     and rec.get("count") == rec.get("n") == 123 and rec.get("last_so") == copy_so                     and (copy_so + 0xC4) in lst.get("bak_targets", []) and per.get("count") == 70                     and per.get("last_name") == NEW_NAME.split(bytes(1))[0].decode()
                if c == "off":
                    ok = ok and ((copy_so in dws) == (src_so in dws))
                else:
                    ok = ok and copy_so in dws
            else:
                ok = ok and U == a_u and rec.get("count") == rec.get("n") == 122 and per.get("count") == 69
            iso = iso and src_so in U and (U - {copy_so}) == a_u
        reg[c] = {"A2": ok, "A6_walk": iso}
    a2 = all(v["A2"] for v in reg.values())
    # A3: init-written offsets vs relocated file values

    def reloc_expect(blk, slotfile, b):
        """File block -> expected live words: own-file pointers + area base; other files skipped."""
        exp, skip = bytearray(blk), set()
        for k, f in slotfile.items():
            if f == 1:
                struct.pack_into(">I", exp, k, (u32(blk, k) + b) & 0xFFFFFFFF)
            else:
                skip.add(k)
        return exp, skip
    init = {}
    for c in GROWN:
        r, b = out[c], ab(out[c])
        nl = construct(data, ptr, tl, c)[0]
        bl = (r.get("live_first") or {}).get("blocks") or {}
        src_live, copy_live = bytes.fromhex(bl.get("src", "")), bytes.fromhex(bl.get("copy", ""))
        sf = {o - SRC: slots[o] for o in range(SRC, SRC + BLK, 4) if o in slots}
        cf = {s - L["fc"]: f for f, s in info[c]["newslots"] if L["fc"] <= s < L["fc"] + BLK}
        cf.update({0x14: 1, 0x18: 1})
        exp_src, skip_s = reloc_expect(data[SRC:SRC + BLK], sf, b)
        exp_src = bytearray(exp_src)
        struct.pack_into(">I", exp_src, 0x14, b + L["fc"] - 4)          # source.next = copy (grown cases)
        exp_copy, skip_c = reloc_expect(nl[L["fc"]:L["fc"] + BLK], cf, b)
        ok_len = len(src_live) == BLK and len(copy_live) == BLK
        links = {0x14, 0x18, 0x1C}                                     # A3r: re-parenting rewrites these
        dsrc = {k for k in range(0, BLK, 4) if ok_len and k not in skip_s | links
                and src_live[k:k + 4] != exp_src[k:k + 4]}
        dcopy = {k for k in range(0, BLK, 4) if ok_len and k not in skip_c | links
                 and copy_live[k:k + 4] != exp_copy[k:k + 4]}
        cbuf = struct.unpack_from(">I", copy_live, 0x14C)[0] if ok_len else 0
        sbuf = struct.unpack_from(">I", src_live, 0x14C)[0] if ok_len else 0
        init[c] = {"src_diff": sorted(dsrc), "copy_diff": sorted(dcopy), "copy_3d_buf": f"{cbuf:08x}",
                   "src_3d_buf": f"{sbuf:08x}",
                   "brain4": [struct.unpack_from(">I", x, 0x31C)[0] if ok_len else None
                              for x in (src_live, copy_live)]}
    a3 = (init["off"]["src_diff"] == init["off"]["copy_diff"]
          and all(init[c]["copy_3d_buf"] not in ("00000000", init[c]["src_3d_buf"]) and
                  init[c]["brain4"] == [0xCDCDCDCD, 0xCDCDCDCD] for c in GROWN))
    # A4 / A5
    coll = {}
    for c, r in out.items():
        s = r["samples"]
        v5 = [x["v5"] for x in s]
        ch = [i for i in range(1, len(s)) if s[i]["v5"] != s[i - 1]["v5"]]
        pos = info["on"]["pos"] if c in ("on", "exit") else None
        close = min(s, key=lambda x: math.dist(x["pos"], pos)) if pos and s else None
        coll[c] = {"v5_first": v5[0] if v5 else None, "v5_last": v5[-1] if v5 else None,
                   "changes": [(s[i]["t"], s[i - 1]["v5"], s[i]["v5"]) for i in ch],
                   "closest": round(math.dist(close["pos"], pos), 3) if close else None,
                   "t_closest": close["t"] if close else None, "level_change_t": r.get("level_change_t"),
                   "lvl_opens": r["lvl_opens"]}
        if c in ("on", "exit") and ch:
            ti = s[ch[0]]["t"]
            before = [x for x in r["reads"] if x["t"] <= ti]
            after = [x for x in r["reads"] if x["t"] > ti]
            if before and after and before[-1].get("copy") and after[0].get("copy"):
                cb, ca = bytes.fromhex(before[-1]["copy"]), bytes.fromhex(after[0]["copy"])
                sb_, sa_ = bytes.fromhex(before[-1]["src"]), bytes.fromhex(after[0]["src"])
                cch = [k for k in range(0, BLK, 4) if cb[k:k + 4] != ca[k:k + 4]]
                coll[c]["copy_changed_at_pickup"] = cch
                coll[c]["src_changed_same_offsets"] = [k for k in cch if sb_[k:k + 4] != sa_[k:k + 4]]
    on, ex = coll["on"], coll["exit"]
    revised2 = tag not in ("m1", "m2")
    if not revised2:
        a4 = all(coll[c].get("copy_changed_at_pickup") and not coll[c].get("src_changed_same_offsets")
                 for c in ("on", "exit"))
        a5 = (all(coll[c]["v5_first"] == 0 and not coll[c]["changes"] for c in ("base", "off", "nogate"))
              and on["v5_first"] == 0 and [x[1:] for x in on["changes"]] == [(0, 1)] and on["closest"] is not None
              and on["closest"] <= 3.0 and abs(on["changes"][0][0] - on["t_closest"]) <= 2.0
              and ex["v5_first"] == 5 and ex["changes"] and ex["changes"][0][1:] == (5, 6)
              and ex["closest"] is not None
              and ex["closest"] <= 3.0 and abs(ex["changes"][0][0] - ex["t_closest"]) <= 2.0
              and "intro_15.lvl" in ex["lvl_opens"] and (ex["level_change_t"] or 1e9) <= 120 + 10)
    else:
        # A4r (revision 2): B: the copy and the source change at the same, non-empty set of offsets between
        # consecutive 1-s reads over the run (both processed by the engine); C / E: offsets the copy changes across
        # the pickup interval that the source does not change in that interval (pickup-specific) are non-empty.
        rb = out["off"]["reads"]

        def changing(key):
            ks = set()
            for x, y in zip(rb, rb[1:]):
                a_, b_ = bytes.fromhex(x.get(key) or ""), bytes.fromhex(y.get(key) or "")
                if len(a_) == len(b_) == BLK:
                    ks |= {k for k in range(0, BLK, 4) if a_[k:k + 4] != b_[k:k + 4]}
            return ks
        coll["off"]["copy_changing"], coll["off"]["src_changing"] = sorted(changing("copy")), sorted(changing("src"))
        if tag not in ("m1", "m2", "m3"):      # revision 3: link words excluded, as in A3r
            for k in ("copy_changing", "src_changing"):
                coll["off"][k] = [x for x in coll["off"][k] if x not in (0x14, 0x18, 0x1C)]
        for c in ("on", "exit"):
            coll[c]["pickup_specific"] = sorted(set(coll[c].get("copy_changed_at_pickup") or [])
                                                - set(coll[c].get("src_changed_same_offsets") or []))
        a4 = (bool(coll["off"]["copy_changing"]) and coll["off"]["copy_changing"] == coll["off"]["src_changing"]
              and all(coll[c]["pickup_specific"] for c in ("on", "exit")))
        # A5r (revision 2): the distance condition is taken at the increment (minimum generator-to-copy distance
        # over samples within 2 s of the first change), not over the whole run (the flight passes the spot every loop)
        pos = info["on"]["pos"]

        def near_change(c):
            s = out[c]["samples"]
            if not coll[c]["changes"]:
                return None
            tc = coll[c]["changes"][0][0]
            d = [math.dist(x["pos"], pos) for x in s if abs(x["t"] - tc) <= 2.0]
            return round(min(d), 3) if d else None
        for c in ("on", "exit"):
            coll[c]["near_change"] = near_change(c)
        a5 = (all(coll[c]["v5_first"] == 0 and not coll[c]["changes"] for c in ("base", "off", "nogate"))
              and on["v5_first"] == 0 and [x[1:] for x in on["changes"]] == [(0, 1)]
              and on["near_change"] is not None and on["near_change"] <= 3.0
              and ex["v5_first"] == 5 and ex["changes"] and ex["changes"][0][1:] == (5, 6)
              and ex["near_change"] is not None and ex["near_change"] <= 3.0
              and "intro_15.lvl" in ex["lvl_opens"] and (ex["level_change_t"] or 1e9) <= 120 + 10)
    # A6: source translation and personal index (live), copy addresses in tail
    iso = all(v["A6_walk"] for v in reg.values())
    for c in CASES:
        bl = (out[c].get("live_first") or {}).get("blocks") or {}
        sl = bytes.fromhex(bl.get("src", ""))
        iso = iso and len(sl) == BLK and sl[0xC4 + 0x34:0xC4 + 0x40] == data[SRC + 0xC4 + 0x34:SRC + 0xC4 + 0x40]
        sstd = info["on"]["src_std"] - SRC
        iso = iso and sl[sstd + 8:sstd + 12] == data[SRC + sstd + 8:SRC + sstd + 12]
    # A7
    alloc = {}
    for c, r in out.items():
        st = r["states"]
        i0 = next((k for k, x in enumerate(st) if "invalid" not in x), None)
        valid = i0 is not None and not any("invalid" in x for x in st[i0:])
        used = [s for s in st if "invalid" not in s and "1" in s.get("areas", {}) and s.get("state") != "after_change"]
        Lc = AREA + (N if c in GROWN else 0)
        fa = [s for s in st if s.get("state") in ("after_change", "final") and "invalid" not in s
              and "1" in s.get("areas", {}) and s["areas"]["1"]["length"] == 8474196]
        alloc[c] = {"valid": valid, "length": (r.get("area") or {}).get("length"),
                    "free_after": used[-1]["free_bytes"] if used else None,
                    "after_change": [(s["areas"]["1"]["base"], s["free_bytes"]) for s in fa][-1:]}
    a7 = all(alloc[c]["valid"] and alloc[c]["length"] == AREA + (N if c in GROWN else 0) for c in CASES)
    a7 = a7 and alloc["base"]["free_after"] == FREE0 and alloc["nogate"]["free_after"] == FREE0
    a7 = a7 and all(alloc[c]["free_after"] is not None and FREE0 - N - 4096 <= alloc[c]["free_after"] <= FREE0 - N
                    for c in ("off", "on"))
    a7 = a7 and alloc["exit"]["after_change"] == [("0x40f5f320", 12234744)]
    a8 = all(r["haptics_policy"] and not any(r["judges"].values()) and r["runner_exit"] == 0 and not r["process_left"]
             for r in out.values())
    checks = {"A1_resource": bool(a1), "A2_registration": bool(a2), "A3_initialization": bool(a3),
              "A4_activity": bool(a4), "A5_collection": bool(a5), "A6_isolation": bool(iso),
              "A7_allocation_cleanup": bool(a7), "A8_safety": bool(a8)}
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()),
              "registration": reg, "init": init, "collection": coll, "alloc": alloc, "readback": shas,
              "grow_size": {c: r["grow_size"] for c, r in out.items()},
              "served": {c: r["served_files"] for c, r in out.items()},
              "lists_first": {c: {k: v for k, v in (((r.get("live_first") or {}).get("lists")) or {}).items()
                                  if k in ("personal",)} | {"dw_count": (((r.get("live_first") or {}).get("lists"))
                                                                         or {}).get("dw", {}).get("count"),
                                                            "rec_count": (((r.get("live_first") or {}).get("lists"))
                                                                          or {}).get("rec", {}).get("count")}
                              for c, r in out.items()},
              "judges": {c: r["judges"] for c, r in out.items()},
              "runner_exit": {c: r["runner_exit"] for c, r in out.items()}}
    (ROOT / "private" / "work" / PREFIX / tag / "judgement.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("invalid", "checks", "pass", "init", "collection", "alloc")}, indent=1))
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
