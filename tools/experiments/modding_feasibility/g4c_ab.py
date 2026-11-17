#!/usr/bin/env python3
"""E-472 (D-239) G4c: one additional scripted actor (MAN_mGenSound_Frog, model NIK_mGenSound) in intro_10 with its
own designer-variable buffers. Private, test-only (G3a gate reused for intro_10.lvl / .ptr growth; transit.lvl as a
same-size range); hidden, read-only instrumentation.

CANDIDATES (intro_10, file offsets; Phase A)
  Lums (G4b): no designer variables (Mind +0xC = 0): cannot test designer state. REJECTED for G4c.
  NIN_m_CagousnipeIntro_I1..I16 (15 instances, one model): graph / waypoint / actor variables, graph-following
    hoodlums of the intro cinematic, inactive at level start: progression- and cinematic-coupled. REJECTED.
  Flight generator, ChangeMap, Murfy, Mano, GlobIntro10, World: unique controllers / progression. REJECTED.
  MAN_mGenManager_Frog: moves the Frog generator (its designer variable 0 = that actor; procedure 219 with the
    position of the nearest waypoint of its graph): references another actor. REJECTED.
  XAP_ToadIntro_*: no designer variables. REJECTED.
  NIK_mGenSound instances (Frog 0x53BED0, SmallRiver 0x53B9B0, AmbGeneral_Forest 0x53A09C; one model 0x53A3D4):
    no Dynam (Perso +8 = 0), no collision set (Perso +0x14 = 0), always active at level start, no progression role.
    Only the Frog instance (v4 = 1, v5 = 500, v6 = 1) runs the looping behaviour. CHOSEN: Frog.
SCRIPT (offline decode of the model; bool call 49 = 8227DD10, value call 66 = 82257AE8, both on the engine timer
  word 0x82C0628C, advanced each frame by 8210D5B8)
  NIK_C_mGenSound_Init: (bool 87(28) -> TestAllIFunctions; not this instance) custom bits 35 / 14 / 16; if v7
  (actor, null here) valid -> LoopSwitch; else if v6: procedure 373 (own 3dData flag), v8 = now (value call 66),
  -> NIK_C_mGenSound_LoopOneShot; else macro 0 once.
  NIK_C_mGenSound_LoopOneShot: if |now - v8| >= v5 (bool 49): v8 = now; macro 0 (sound launch, event v0).
  So v8 (current buffer offset 24) is a script-written timestamp, rewritten every v5 timer units.
DESIGNER VARIABLES (Phase B): DsgVar (model, shared, level 0x53A3DC) {default buffer, info, length 30, count 9};
  types [14,14,14,14,2,5,0,18,5] at offsets [0,4,8,12,29,16,28,20,24]. Instance DsgMem = block +0x490 {-> the model's
  +8 (its DsgVar pointer, shared), -> initial (block +0x49C), -> current (block +0x4BC)}; both buffers inside the actor block,
  referenced only by its DsgMem (no other word, no transit or cross-file entry); no relocated word in either buffer
  (sound events are ids, v7 null). The copy therefore gets its own buffers by rebasing its DsgMem.
OWNERSHIP (Phase C): in-block (rebased): SO, Perso, 3dData, StdGame (+8 personal index), Brain, Mind, normal
  Intelligence (+8 current behaviour), DsgMem and buffers, Perso +0x18 / +0x20 / +0x28 components. Shared (kept):
  AI model, behaviour records, DsgVar, family / bounding data (SO +0x34 / +0x38 are the same for all four Gen_Sound
  actors), transit parent. Procedures 373 / 189 act on the calling actor only. GenManager_Frog's variable 0 keeps
  pointing at the source only (not replicated: the copy is not moved by the manager).
REGISTRATIONS of the source, each mirrored for the copy:
  sibling chain (GenManager -> Frog -> SmallRiver): copy after the source;
  SO record (0x48) -> new last record (count 122 -> 123);
  backup list: 4 records (inline 4-byte backups of block +0x518 / +0x514 / +0x510, type 0x10320200 / 0x30320200,
  and the matrix 0x54 copy, type 0x50320200) -> 4 new records for the copy, appended in the source's order;
  always-active list (level header 0x1CA8 {first, last, count 17}, kind 212 -> global 0x82C06820; elements 0x14
  {next, prev, -> owner header 0x53A090 (a copy of {first, last, count}), -> SO, 0x01000000}; members: 5 fix and 12
  level actors incl. all four Gen_Sound actors) -> new element appended, both headers last / count 17 -> 18;
  personal object type -> new index 69 (element copied from the source's, name MAN_mGenSound_Frog_G4C), count 70;
  transit dynamic-world count 60 -> 61.
  The live always-active list is rebuilt by the engine (20-byte live elements {?, -> SO, next, prev, owner} from
  821313C0; reset path 82103D98): not read as a criterion; its effect (the copy active like its source) is.
CONSTRUCTION (`check` re-verifies it from the files and fails closed; 20 checks): copy block 0x520 at 7,661,840
  (19 in-block pointers rebased, 15 shared kept, transit parent kept), personal element + name, SO record, 4 backup
  records + 0x54 matrix copy, always-active element; .lvl 7,661,836 -> 7,663,472 (N = 1,636); .ptr 209,068 ->
  209,500 (K = 54 new same-file entries, cross-file table identical and moved); transit.lvl only byte 0x9C7.
  Changed original words: 0x1C78 / 0x1C7C (personal), 0x1CAC / 0x1CB0 and 0x53A094 / 0x53A098 (always headers),
  0x53A07C (old last always element), 0x1CF0 / 0x5A59D4 (backup last), 0x539320 (old last personal element),
  0x53B9C8 (SmallRiver prev), 0x53BEE4 (source next), 0x5A7438 / 0x5A743C / 0x5A9648 (records); E adds the
  generator's variable-5 bytes. Offline-check corrections before this protocol was committed: the DsgMem +0 check
  expected the DsgVar record, but DsgMem +0 holds the model's +8 (as RE_NOTES records); check fixed, construction
  unchanged.
RUN n1 (protocol 03d230a; judged by that version: INVALID in all five cases, kept):
  harness defect: the reader took block +0x490 as a pointer to the DsgMem (the record lies there), so the buffer
  reads failed, sampling stopped at once and the watch loop ended (no samples, no level change seen in E);
  construction defect, a guest fault: B / C / E each ended in "Unhandled guest access violation: read of guest
  0x0058001A" (runner exit 1; minidumps written by the crash handler, deleted after diagnosis). 0x00580006 is
  designer variable 0 (type 14, sound event) as stored in the file. Live: the source's v0 was 0x406D901C and its
  v1..v3 (0xFFFFFFFF) 0 in both buffers, the copy's still the raw ids. Cause: a level-wide sound-event resolve table
  (header 0x1CE8 -> 0x5A43A4, 339 raw file-domain words: 0x1CE4 = 1 entry of a first group, 0x1CE0 = 338 of the
  level group; parser 822A5918 calls 822A51F0(base, entry) = *(base + entry) = 821412B0(id) for each) lists exactly
  the source's 8 type-14 words (block +0x49C..+0x4A8, +0x4BC..+0x4C8) and not the copy's. (No G4b lum word is in it.)
  S1 and S2 structural reads passed; free after load B / C / E = FREE0 - N (no extra allocation).
REVISION 1 (committed before run n2; construction and reader only; S1-S8 unchanged except as noted):
  construction: a copy of the table with the copy's 8 words appended (sorted order kept) after the always element;
  0x1CE8 (an existing slot) -> it, 0x1CE0 338 -> 346; the original table is left in place, unused.
  N = 3,028 (.lvl 7,664,864), K = 54 (.ptr 209,500), changed original words + 0x1CE0 / 0x1CE8 (masked).
  offline: check "resolve_table" added (21 checks).
  reader: DsgMem address = the live address of block +0x490.
  S3 adds: DsgMem +0 == live model + 8 for both; the copy's eight type-14 words read live equal the source's and
  none is the raw id 0x00580006.
RUN n2 (revision 1; recorded after the run, criteria unchanged): 7 / 8, S6 FAIL. Periods (ms) source / copy:
  A 500 / -, B 933 / 550, C 933 / 2200 (whole frame counts from level start); see the G4c report. Not re-run.
VARIANTS: base (A); same (B: copy, v5 = 500); diff (C: copy, v5 = 2000 in its initial and current buffers);
  nogate (D: C's plan without the gate, must be refused); exit (E: C + flight generator variable 5 = 6, the E-460
  exit: the first junction ends the flight and intro_15 opens).

PRE-REGISTERED CRITERIA (E-472; committed before any run)
S1 resource: grown cases: M36 grow lines intro_10.lvl SIZE -> SIZE + N and intro_10.ptr PSIZE -> PSIZE + 8K; served
   files exactly intro_10.lvl, intro_10.ptr, transit.lvl; A: mods off, no growth; D: refused, nothing served; the
   masked original-area read-back hash equal in all five cases.
S2 registration: union of the active and inactive dynamic worlds = A's + exactly the copy (no duplicates, prev links
   consistent), the copy in the ACTIVE world at the first and last structural read of B / C (source active there
   too); SO records 123 with the copy last; backup targets contain copy +0xC4, +0x510, +0x514, +0x518; personal
   count 70 with the new name; A / D: 66 actors, 122 records, 69 personal.
S3 independent initialization (first structural read, B / C / E): copy DsgMem live {+0 == source DsgMem +0 (the
   shared DsgVar), +4 == copy initial buffer address, +8 == copy current buffer address}, both != the source's;
   copy Mind +0 == source Mind +0 (shared model); copy Brain / Mind / Intelligence / DsgMem pointers are the
   copy's own block addresses; copy 3dData buffer (block +0x14C) is nonzero and != the source's iff the source's
   is nonzero; Brain +4 equal for source and copy.
S4 script execution (B / C, watch window): copy Intelligence +8 == live LoopOneShot record in every sample after
   the first change, and the copy's current v8 takes >= 10 distinct nonzero values; each new v8 value lies within
   [timer at the previous sample, timer at the sample] (a script write of `now`); the same holds for the source.
S5 designer-variable independence: in every sample of A / B / C, source initial v5 == current v5 == 500; copy
   initial v5 == current v5 == 500 (B) / 2000 (C); the copy's and source's v8 sequences are not identical; the
   source's buffers are never written with the copy's v5.
S6 functional effect: retrigger intervals (differences of consecutive distinct v8 values): copy min >= v5_copy and
   median in [v5_copy, v5_copy + 100] in B and C; source median in [500, 600] in A / B / C; median(copy C) /
   median(source C) in [3.6, 4.4]; median(copy B) / median(source B) in [0.9, 1.1]; no flight progression change in
   A-D (no level change, intro_15 not opened).
S7 cleanup: block-8 walks valid; area length AREA + N in grown cases; free after load: A / D = FREE0, B / C in
   {FREE0 - N, FREE0 - N - 24} (24 = one 20-byte allocation (ceil(20/4)+1 words) if the always list is rebuilt
   per element); E: level change to intro_15 within 130 s and the block-8 layout after the change = E-465a exactly
   (intro_15 area at 0x40F5F320, free 12,234,744).
S8 safety: M21 / M22 / M23 judges 0, haptics policy line, runner exit 0, no process left.
Invalid run (not judged): process / level area not found, structural read error, or fewer than 60 s of samples in
A-D.
"""
import argparse
import hashlib
import json
import math
import os
import re
import statistics
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
import g4b_ab as g4b  # noqa: E402

LVL, PTR, LDIR, RUNS = g3a.LVL, g3a.PTR, g3a.LDIR, g3a.RUNS
TRANSIT = g4b.TRANSIT
PREFIX = "e472"
SIZE, PSIZE, AREA, FREE0 = g3a.SIZE, g3a.PSIZE, g3a.AREA, g3a.FREE0
ORIG_FNV, PTR_FNV = g3a.ORIG_FNV, g3a.PTR_FNV
TSIZE = g4b.TSIZE
u32, fnv = g3a.u32, g3a.fnv
files, index, tgt = g4b.files, g4b.index, g4b.tgt
SRC, BLK, NEXT_SO, PREV_SO = 0x53BED0, 0x520, 0x53B9B0, 0x53C3F0
MODEL = 0x53A3D4
DW_COUNT = g4b.DW_COUNT
PHDR, RHDR, BHDR = g4b.PHDR, g4b.RHDR, g4b.BHDR
AHDR, AOWN = 0x1CA8, 0x53A090          # always-active list: level header, in-data owner header
NEW_NAME = b"MAN_mGenSound_Frog_G4C\0\0"
DSGMEM, INI, CUR = 0x490, 0x49C, 0x4BC  # block offsets
V5, V8, VLEN = 16, 24, 30
INTEL, MIND, BRAIN = 0x338, 0x324, 0x318
LOOP_ONESHOT = 0x53A610                 # behaviour record (file offset)
TIMER = 0x82C0628C
V5_SAME, V5_DIFF = 500, 2000
G_DW, G_INACT, G_REC, G_BAK, G_OBJ = g4b.G_DW, g4b.G_INACT, g4b.G_REC, g4b.G_BAK, g4b.G_OBJ
SECONDS, WATCH = 150, 75
CASES = ("base", "same", "diff", "nogate", "exit")
GROWN = ("same", "diff", "exit")
GATE_ENV = g3a.GATE_ENV
BAK_INLINE = (0x518, 0x514, 0x510)
STAB, STAB_N, STAB_PTR, STAB_CNT, STAB_G1 = 0x5A43A4, 339, 0x1CE8, 0x1CE0, 0x1CE4   # revision 1
RAW_EVENT = 0x00580006


def layout():
    pad = (SRC % 16 - SIZE % 16) % 16
    fc = SIZE + pad
    pe = fc + BLK
    name = pe + 0x14
    rec = name + len(NEW_NAME)
    bak = rec + 0x48                                  # 4 records of 0x18 (source order: +0x518, +0x514, +0x510, matrix)
    bcopy = bak + 4 * 0x18
    ael = bcopy + 0x54                                # always-active element (0x14)
    stab = ael + 0x14                                 # revision 1: sound-event resolve table, 339 + 8 words
    end = stab + 4 * (STAB_N + 8)
    end += (-end) % 16
    return {"pad": pad, "fc": fc, "pe": pe, "name": name, "rec": rec, "bak": bak, "bcopy": bcopy, "ael": ael,
            "stab": stab, "end": end}


def src_backups(data, slots):
    """The source's backup records (record base, data target), in list order."""
    out, l_ = [], tgt(data, slots, BHDR)[1]
    while True:
        t = tgt(data, slots, l_ + 4)
        if t and t[0] == 1 and SRC <= t[1] < SRC + BLK:
            out.append((l_ - 4, t[1]))
        n = tgt(data, slots, l_)
        if not n:
            return out
        l_ = n[1]


def construct(data, ptr, tl, variant):
    """(new lvl, new ptr, new transit, info) for variant same / diff / exit."""
    slots, cross = index(data, ptr)
    L = layout()
    fc = L["fc"]
    new = bytearray(data) + bytearray(L["end"] - SIZE)
    newslots = []

    def put(o, v):
        struct.pack_into(">I", new, o, v)
    # 1. block copy, in-block pointers rebased
    blk = bytearray(data[SRC:SRC + BLK])
    for o in range(SRC, SRC + BLK, 4):
        if o in slots:
            f, a = tgt(data, slots, o)
            if f == 1 and SRC <= a < SRC + BLK:
                struct.pack_into(">I", blk, o - SRC, a - SRC + fc - 4)
            newslots.append((f, o - SRC + fc))
    new[fc:fc + BLK] = blk
    nxt = tgt(data, slots, SRC + 0x14)[1]
    put(fc + 0x14, nxt - 4)
    put(fc + 0x18, SRC - 4)
    put(SRC + 0x14, fc - 4)
    put(nxt + 0x18, fc - 4)
    v5 = V5_SAME if variant == "same" else V5_DIFF
    for b in (INI, CUR):
        struct.pack_into(">i", new, fc + b + V5, v5)
    # 2. personal element + name
    plast = tgt(data, slots, PHDR + 4)[1]
    pcount = u32(data, PHDR + 8)
    src_std = tgt(data, slots, tgt(data, slots, SRC + 4)[1] + 4)[1]
    put(fc + (src_std - SRC) + 8, pcount)
    tmpl, k = tgt(data, slots, PHDR)[1], u32(data, src_std + 8)
    for _ in range(k):
        tmpl = tgt(data, slots, tmpl)[1]
    pe = L["pe"]
    new[pe:pe + 0x14] = data[tmpl:tmpl + 0x14]
    put(pe, 0)
    put(pe + 4, plast - 4)
    put(pe + 0xC, L["name"] - 4)
    new[L["name"]:L["name"] + len(NEW_NAME)] = NEW_NAME
    newslots += [(1, pe + 4), (1, pe + 8), (1, pe + 0xC)]
    put(plast, pe - 4)
    newslots.append((1, plast))
    put(PHDR + 4, pe - 4)
    put(PHDR + 8, pcount + 1)
    # 3. SO record
    rlast = tgt(data, slots, RHDR + 4)[1]
    srecs = [x - 4 for x in slots if slots[x] == 1 and u32(data, x) + 4 == SRC and u32(data, x + 4) == 0x01000000
             and RHDR < x < RHDR + 0x10000]
    srec = srecs[0]
    rec = L["rec"]
    new[rec:rec + 0x48] = data[srec:srec + 0x48]
    put(rec, 0)
    put(rec + 4, fc - 4)
    newslots.append((1, rec + 4))
    put(rlast, rec - 4)
    newslots.append((1, rlast))
    put(RHDR + 4, rec - 4)
    put(RHDR + 8, u32(data, RHDR + 8) + 1)
    # 4. backup records (source order), the matrix record with its own 0x54 copy
    sbs = src_backups(data, slots)
    blink = tgt(data, slots, BHDR + 4)[1]
    prev_link = blink
    for i, (sb, t) in enumerate(sbs):
        r = L["bak"] + 0x18 * i
        new[r:r + 0x18] = data[sb:sb + 0x18]
        put(r + 4, 0)
        put(r + 8, t - SRC + fc - 4)
        newslots.append((1, r + 8))
        if slots.get(sb + 0xC) == 1:                  # pointer to a copy (matrix): own copy
            scopy = tgt(data, slots, sb + 0xC)[1]
            new[L["bcopy"]:L["bcopy"] + 0x54] = data[scopy:scopy + 0x54]
            put(r + 0xC, L["bcopy"] - 4)
            newslots.append((1, r + 0xC))
        put(prev_link, r + 4 - 4)
        newslots.append((1, prev_link))
        prev_link = r + 4
    put(BHDR + 4, prev_link - 4)
    # 5. always-active element
    alast = tgt(data, slots, AHDR + 4)[1]
    ael = L["ael"]
    put(ael, 0)
    put(ael + 4, alast - 4)
    put(ael + 8, AOWN - 4)
    put(ael + 0xC, fc - 4)
    new[ael + 0x10:ael + 0x14] = data[alast + 0x10:alast + 0x14]
    newslots += [(1, ael + 4), (1, ael + 8), (1, ael + 0xC)]
    put(alast, ael - 4)
    newslots.append((1, alast))
    for h in (AHDR, AOWN):
        put(h + 4, ael - 4)
        put(h + 8, u32(data, h + 8) + 1)
    # 6. (revision 1) sound-event resolve table: the original 339 entries + the copy's 8 type-14 words, sorted;
    #    the level header pointer (an existing slot) moves to it and the level-group count grows by 8
    old = [u32(data, STAB + 4 * i) for i in range(STAB_N)]
    add = [L["fc"] + b + 4 * j - 4 for b in (INI, CUR) for j in range(4)]
    tab = old + add
    for i, v in enumerate(tab):
        put(L["stab"] + 4 * i, v)
    put(STAB_PTR, L["stab"] - 4)
    put(STAB_CNT, u32(data, STAB_CNT) + 8)
    # 7. flight generator variable 5 = 6 (exit only; E-460)
    if variant == "exit":
        for o in g4b.gen_offsets():
            new[o] = 6
    n = u32(ptr, 0)
    entries = b"".join(struct.pack(">iI", f, s - 4) for f, s in newslots)
    nptr = struct.pack(">I", n + len(newslots)) + ptr[4:4 + 8 * n] + entries + ptr[4 + 8 * n:]
    ntl = bytearray(tl)
    struct.pack_into(">I", ntl, DW_COUNT, u32(tl, DW_COUNT) + 1)
    info = {"layout": L, "newslots": newslots, "next": nxt, "src_std": src_std, "plast": plast, "rlast": rlast,
            "src_record": srec, "blink": blink, "src_backups": sbs, "alast": alast, "new_index": pcount, "v5": v5}
    return bytes(new), nptr, bytes(ntl), info


def approved_words(data, ptr, tl, variant):
    i = construct(data, ptr, tl, variant)[3]
    w = {SRC + 0x14, i["next"] + 0x18, PHDR + 4, PHDR + 8, i["plast"], RHDR + 4, RHDR + 8, i["rlast"], BHDR + 4,
         i["blink"], i["alast"], AHDR + 4, AHDR + 8, AOWN + 4, AOWN + 8, STAB_PTR, STAB_CNT}
    if variant == "exit":
        w |= {o & ~3 for o in g4b.gen_offsets()}
    return w


def simulate(lvl, ptr, tl, base1=0x40F5509C):
    s = g4b.simulate(lvl, ptr, tl, base1)
    rd = s["rd"]
    al, e = [], rd(base1 + AHDR - 4)
    while e and len(al) < 1000:
        al.append(e)
        e = rd(e)
    s["always"] = al
    s["always_so"] = [rd(x + 0xC) for x in al]
    s["a_count"], s["a_last"] = rd(base1 + AHDR - 4 + 8), rd(base1 + AHDR - 4 + 4)
    s["o_count"], s["o_last"] = rd(base1 + AOWN - 4 + 8), rd(base1 + AOWN - 4 + 4)
    s["a_owner_ok"] = all(rd(x + 8) == base1 + AOWN - 4 for x in al)
    return s


def check():
    data, ptr, tl = files()
    slots, cross = index(data, ptr)
    res = {}
    B1 = 0x40F5509C
    W = lambda o: u32(data, o)                          # noqa: E731
    s0 = simulate(data, ptr, tl)
    res["original_lists"] = (len(s0["walk"]) == 60 == s0["dw_count"] and s0["prev_ok"] and len(s0["recs"]) == 122
                             and len(s0["pel"]) == s0["p_count"] == 69 and len(s0["always"]) == s0["a_count"] == 17
                             == s0["o_count"] and s0["always"][-1] == s0["a_last"] == s0["o_last"]
                             and s0["a_owner_ok"])
    # source identity: type 2, model NIK_mGenSound, personal name, in the dynamic-world chain and the always list
    perso = tgt(data, slots, SRC + 4)[1]
    std = tgt(data, slots, perso + 4)[1]
    mind = tgt(data, slots, tgt(data, slots, perso + 0xC)[1])[1]
    pel0 = tgt(data, slots, PHDR)[1]
    e = pel0
    for _ in range(W(std + 8)):
        e = tgt(data, slots, e)[1]
    pname = data[tgt(data, slots, e + 0xC)[1]:][:24].split(b"\0")[0]
    res["source_identity"] = (W(SRC) == 2 and perso == SRC + 0x80 and B1 + SRC - 4 in s0["walk"]
                              and tgt(data, slots, mind) == (1, MODEL) and mind == SRC + MIND
                              and tgt(data, slots, mind + 0xC) == (1, SRC + DSGMEM) and pname == b"MAN_mGenSound_Frog"
                              and W(std + 8) == 66 and B1 + SRC - 4 in s0["always_so"]
                              and slots.get(perso + 8) is None and slots.get(perso + 0x14) is None
                              and data[LOOP_ONESHOT:LOOP_ONESHOT + 0x100].split(b"\0")[0]
                              .endswith(b"NIK_C_mGenSound_LoopOneShot")
                              and tgt(data, slots, SRC + INTEL + 8) == (1, 0x53A3F8))
    # designer variables: model DsgVar, layout, buffers in the block, only referenced by the DsgMem, values
    dv = tgt(data, slots, MODEL + 8)[1]
    info_ = tgt(data, slots, dv + 4)[1]
    vars_ = [(W(info_ + 16 * i), W(info_ + 16 * i + 4)) for i in range(data[dv + 0xC])]
    refs = {}
    for o in slots:
        if slots[o] == 1:
            refs.setdefault(W(o) + 4, []).append(o)
    buf_refs = [o for b in (INI, CUR) for t in range(SRC + b, SRC + b + VLEN) for o in refs.get(t, [])]
    res["designer_layout"] = (vars_ == [(0, 14), (4, 14), (8, 14), (12, 14), (29, 2), (16, 5), (28, 0), (20, 18),
                                        (24, 5)] and W(dv + 8) == VLEN
                              and tgt(data, slots, SRC + DSGMEM) == (1, MODEL + 8)
                              and tgt(data, slots, SRC + DSGMEM + 4) == (1, SRC + INI)
                              and tgt(data, slots, SRC + DSGMEM + 8) == (1, SRC + CUR)
                              and sorted(buf_refs) == [SRC + DSGMEM + 4, SRC + DSGMEM + 8]
                              and not any(o in slots for b in (INI, CUR) for o in range(SRC + b, SRC + b + VLEN + 2))
                              and data[SRC + INI:SRC + INI + VLEN] == data[SRC + CUR:SRC + CUR + VLEN]
                              and struct.unpack_from(">i", data, SRC + CUR + V5)[0] == 500
                              and data[SRC + CUR + 28] == 1 and W(SRC + CUR + 20) == 0)
    census = {"in": 0, "ext": 0, "f2": 0}
    for o in range(SRC, SRC + BLK, 4):
        if o in slots:
            f, a = tgt(data, slots, o)
            census["in" if f == 1 and SRC <= a < SRC + BLK else ("ext" if f == 1 else "f2")] += 1
    res["source_census_35"] = census == {"in": 19, "ext": 15, "f2": 1}
    outside = sorted(o for o in slots if slots[o] == 1 and not SRC <= o < SRC + BLK
                     and SRC <= W(o) + 4 < SRC + BLK)
    gm_dsg = tgt(data, slots, PREV_SO + 4)
    gm_buf = []
    if gm_dsg:
        gm_mind = tgt(data, slots, tgt(data, slots, gm_dsg[1] + 0xC)[1])[1]
        dm = tgt(data, slots, gm_mind + 0xC)[1]
        gm_buf = [tgt(data, slots, dm + 4)[1], tgt(data, slots, dm + 8)[1]]
    sbs = src_backups(data, slots)
    srec = [x for x in outside if RHDR < x < RHDR + 0x10000]
    expect = sorted([NEXT_SO + 0x18, PREV_SO + 0x14, 0x53A060] + gm_buf + [b + 8 for b, _ in sbs] + srec)
    res["incoming_known"] = (outside == expect and len(sbs) == 4 and len(srec) == 1
                             and sorted(t - SRC for _, t in sbs) == [0xC4, 0x510, 0x514, 0x518]
                             and not any((fb == 1 and SRC <= ob + 4 < SRC + BLK) or (fa == 1 and SRC <= oa + 4 < SRC + BLK)
                                         for oa, fa, ob, fb in cross))
    tp = g4b.TPTR.read_bytes()
    nt = u32(tp, 0)
    res["no_transit_refs"] = not any(f == 1 and SRC <= u32(tl, loc + 4) + 4 < SRC + BLK
                                     for f, loc in (struct.unpack_from(">iI", tp, 4 + 8 * i) for i in range(nt)))
    desc = {}
    for variant in GROWN:
        nl, np_, ntl, info = construct(data, ptr, tl, variant)
        L = info["layout"]
        s1 = simulate(nl, np_, ntl)
        rd = s1["rd"]
        copy_so = B1 + L["fc"] - 4
        ok = (not s1["dup"] and len(s1["walk"]) == 61 == s1["dw_count"] and len(set(s1["walk"])) == 61
              and s1["prev_ok"] and [x for x in s1["walk"] if x != copy_so] == s0["walk"]
              and s1["walk"][s1["walk"].index(B1 + SRC - 4) + 1] == copy_so
              and len(s1["recs"]) == s1["rec_count"] == 123 and s1["recs"][:-1] == s0["recs"]
              and s1["recs"][-1] == s1["rec_last"] == B1 + L["rec"] - 4 and rd(s1["recs"][-1] + 4) == copy_so
              and s1["links"][:-4] == s0["links"] and s1["links"][-1] == s1["bak_last"]
              and [rd(x + 4) for x in s1["links"][-4:]] == [copy_so + o for o in (0x518, 0x514, 0x510, 0xC4)]
              and len(s1["pel"]) == s1["p_count"] == 70 and s1["pel"][:-1] == s0["pel"]
              and s1["pel"][-1] == B1 + L["pe"] - 4
              and len(s1["always"]) == s1["a_count"] == s1["o_count"] == 18 and s1["always"][:-1] == s0["always"]
              and s1["always"][-1] == s1["a_last"] == s1["o_last"] == B1 + L["ael"] - 4
              and s1["always_so"][-1] == copy_so and s1["a_owner_ok"])
        res[f"lists_{variant}"] = bool(ok)
        # the copy's pointers: in-block rebased, shared kept; DsgMem / buffers / Brain / Mind / Intelligence own
        cok = True
        for k in range(0, BLK, 4):
            so_, co_ = SRC + k, L["fc"] + k
            if so_ in slots:
                if k in (0x14, 0x18):
                    continue
                f, a = tgt(data, slots, so_)
                if f == 1:
                    want = B1 + a - 4 if not SRC <= a < SRC + BLK else B1 + a - SRC + L["fc"] - 4
                    cok = cok and rd(B1 + co_ - 4) == want
            elif k not in (INI + V5, CUR + V5, info["src_std"] - SRC + 8):
                cok = cok and nl[co_:co_ + 4] == data[so_:so_ + 4]
        cdm = B1 + L["fc"] + DSGMEM - 4
        cok = (cok and rd(cdm) == B1 + MODEL + 8 - 4 and rd(cdm + 4) == B1 + L["fc"] + INI - 4
               and rd(cdm + 8) == B1 + L["fc"] + CUR - 4 and u32(nl, L["fc"] + 0x14C) == 0
               and struct.unpack_from(">i", nl, L["fc"] + INI + V5)[0] == info["v5"]
               and struct.unpack_from(">i", nl, L["fc"] + CUR + V5)[0] == info["v5"]
               and nl[SRC + INI:SRC + CUR + VLEN] == data[SRC + INI:SRC + CUR + VLEN]
               and rd(B1 + L["fc"] + MIND - 4 + 0xC) == cdm and u32(nl, L["fc"] + (info["src_std"] - SRC) + 8) == 69)
        res[f"copy_block_{variant}"] = bool(cok)
        diff = {i & ~3 for i in range(SIZE) if nl[i] != data[i]}
        res[f"changes_{variant}"] = (diff == approved_words(data, ptr, tl, variant)
                                     and [i for i in range(TSIZE) if ntl[i] != tl[i]] == [DW_COUNT + 3])
        newslots = [s for _, s in info["newslots"]]
        K = len(newslots)
        n = u32(ptr, 0)
        res[f"ptr_{variant}"] = (K == 54 and len(set(newslots)) == K and not any(s in slots for s in newslots)
                                 and np_[4:4 + 8 * n] == ptr[4:4 + 8 * n] and np_[4 + 8 * (n + K):] == ptr[4 + 8 * n:]
                                 and len(np_) == PSIZE + 8 * K and len(nl) == L["end"])
        desc[variant] = {"lvl_len": len(nl), "ptr_len": len(np_), "N": L["end"] - SIZE, "K": K, "layout": L,
                         "v5": info["v5"], "new_index": info["new_index"],
                         "changed_words": sorted(f"0x{x:X}" for x in diff),
                         "lvl_fnv": f"{fnv(nl):016x}", "ptr_fnv": f"{fnv(np_):016x}", "transit_fnv": f"{fnv(ntl):016x}",
                         "lvl_sha256": hashlib.sha256(nl).hexdigest(), "ptr_sha256": hashlib.sha256(np_).hexdigest()}
    N = desc["diff"]["N"]
    # revision 1: the sound-event resolve table (level 0x1CE8 -> table; 0x1CE4 entries of group 1, 0x1CE0 of the
    # level group; 822A51F0 resolves *(base + entry) in place): source's 8 type-14 words listed, copy's added
    old = [W(STAB + 4 * i) for i in range(STAB_N)]
    src_ent = [x + 4 - SRC for x in old if SRC <= x + 4 < SRC + BLK]
    rt = (tgt(data, slots, STAB_PTR) == (1, STAB) and W(STAB_G1) + W(STAB_CNT) == STAB_N
          and src_ent == [INI, INI + 4, INI + 8, INI + 12, CUR, CUR + 4, CUR + 8, CUR + 12]
          and old[W(STAB_G1):] == sorted(old[W(STAB_G1):]) and not any(x + 4 in slots for x in old)
          and STAB + 4 * STAB_N == tgt(data, slots, BHDR)[1] - 4)
    for variant in GROWN:
        nl = construct(data, ptr, tl, variant)[0]
        L = layout()
        nt = [u32(nl, L["stab"] + 4 * i) for i in range(STAB_N + 8)]
        rt = (rt and u32(nl, STAB_PTR) + 4 == L["stab"] and u32(nl, STAB_CNT) == W(STAB_CNT) + 8
              and u32(nl, STAB_G1) == W(STAB_G1) and nt[:STAB_N] == old
              and nt[STAB_N:] == [L["fc"] + e - 4 for e in src_ent] and nt[1:] == sorted(nt[1:])
              and all(u32(nl, x + 4) == u32(data, x + 4 - L["fc"] + SRC) for x in nt[STAB_N:])
              and nl[STAB:STAB + 4 * STAB_N] == data[STAB:STAB + 4 * STAB_N])
    res["resolve_table"] = bool(rt)
    res["capacity"] = N <= 65536 and 8 * 54 <= 4096 and N + 4096 <= FREE0 - 868496
    prod = (TOOLS / "m33_mod_overlay.h").read_text(encoding="utf-8")
    res["production_refuses_growth"] = ('kGrowNames[] = {"VS.sub"}' in prod and "intro_10" not in prod
                                        and "G3A" not in prod)
    out = {"checks": res, "pass": all(res.values()), "constructions": desc, "source_census": census,
           "incoming": [hex(x) for x in outside], "transit_fnv": f"{fnv(tl):016x}"}
    d = ROOT / "private" / "work" / PREFIX
    d.mkdir(parents=True, exist_ok=True)
    (d / "offline.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0 if out["pass"] else 1


def write_plan(work, data, ptr, tl, variant):
    nl, np_, ntl, info = construct(data, ptr, tl, variant)
    paths = {k: work / f"{k}_range.bin" for k in ("lvl", "ptr", "transit")}
    paths["lvl"].write_bytes(nl)
    paths["ptr"].write_bytes(np_)
    paths["transit"].write_bytes(ntl)
    plan = work / "plan.txt"
    plan.write_text("R3HD_MOD_PLAN 1\n# E-472 test-only plan (g4c_ab.py)\nmod e472.g4c 1.0.0\n"
                    f"file {SIZE} {LVL}\nfile {PSIZE} {PTR}\nfile {TSIZE} {TRANSIT}\n"
                    f"grow 0 {len(nl)}\nrange 0 0 {len(nl)} {ORIG_FNV} {fnv(nl):016x} e472.g4c {paths['lvl']}\n"
                    f"grow 1 {len(np_)}\nrange 1 0 {len(np_)} {PTR_FNV} {fnv(np_):016x} e472.g4c {paths['ptr']}\n"
                    f"range 2 0 {TSIZE} {fnv(tl):016x} {fnv(ntl):016x} e472.g4c {paths['transit']}\n"
                    "gameplay e472.g4c\nend 3 3\n", encoding="utf-8")
    return plan, info


def mask_words(data, ptr, tl):
    return approved_words(data, ptr, tl, "exit")


def run_case(tag, case):
    from m5_live import Process
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
    variant = {"same": "same", "diff": "diff", "nogate": "diff", "exit": "exit"}.get(case)
    if variant:
        plan, _ = write_plan(work, data, ptr, tl, variant)
        env["R3HD_MODS_PLAN"] = row["plan"] = str(plan)
    if case in GROWN:
        env[GATE_ENV[0]] = GATE_ENV[1]
    L = layout()
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
                grown = area["length"] > AREA
                live = lambda fo: ab + fo - 4                 # noqa: E731

                def w(a):
                    x = p.words(a, 1)
                    if not x:
                        raise ValueError(f"read {a:#x}")
                    return x[0]

                def lists():
                    r = {}
                    try:
                        for key, g_ in (("dw", G_DW), ("inactive", G_INACT)):
                            h = w(g_)
                            walk, so = [], w(h + 8)
                            while so and len(walk) < 400:
                                walk.append(so)
                                so = w(so + 0x14)
                            r[key] = {"count": w(h + 0x10), "walk": walk,
                                      "prev_ok": all(w(b + 0x18) == a for a, b in zip(walk, walk[1:]))}
                        h = w(G_REC)
                        recs, c = [], w(h)
                        while c and len(recs) < 1000:
                            recs.append(w(c + 4))
                            nx = w(c)
                            if nx == c:
                                break
                            c = nx
                        r["rec"] = {"count": w(h + 8), "n": len(recs), "last_so": recs[-1] if recs else None}
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
                        r["personal"] = {"count": pc, "last_name": nm.split(bytes(1))[0].decode("ascii", "replace")
                                         if nm else None}
                        # diagnostic only (live format assumed {?, -> SO, next, prev, owner}; not a criterion)
                        al, e = [], w(0x82C06820)
                        while e and len(al) < 64:
                            al.append(w(e + 4))
                            e = w(e + 8)
                        r["always_diag"] = {"head": w(0x82C06820), "count": w(0x82C06828), "so": al}
                    except Exception as x:
                        r["error"] = repr(x)
                    return r

                def blocks():
                    out = {"src": (p.read(live(SRC), BLK) or b"").hex()}
                    if grown:
                        out["copy"] = (p.read(live(L["fc"]), BLK) or b"").hex()
                    return out

                def actor(fo):
                    dm = live(fo + DSGMEM)             # revision 1: the DsgMem record lies at block +0x490
                    ini, cur = w(dm + 4), w(dm + 8)
                    ev = list(p.words(ini, 4) or []) + list(p.words(cur, 4) or [])
                    return {"dsgmem": dm, "dsgvar": w(dm), "ini": ini, "cur": cur, "mind0": w(live(fo + MIND)),
                            "brain": w(live(fo + 0x80 + 0xC)), "mind": w(live(fo + BRAIN)),
                            "intel": w(live(fo + MIND + 4)), "mind_dsgmem": w(live(fo + MIND + 0xC)),
                            "brain4": w(live(fo + BRAIN + 4)), "buf3d": w(live(fo + 0x14C)), "events": ev}
                time.sleep(1.0)
                row["live_first"] = {"lists": lists(), "blocks": blocks()}
                try:
                    acts = {"src": actor(SRC)}
                    if grown:
                        acts["copy"] = actor(L["fc"])
                    row["actors"] = acts
                except Exception as x:
                    row["error"] = f"actor read {x!r}"
                    acts = {}
                row["loop_oneshot"] = live(LOOP_ONESHOT)
                t_end, next_read = time.monotonic() + WATCH, 0.0
                level_changed = False
                while time.monotonic() < t_end and p.running() and acts:
                    now = time.monotonic()
                    ar = bp.areas(p)
                    a1 = (ar or {}).get(1)
                    if a1 and a1["base"] != ab and not level_changed:
                        level_changed = True
                        row["level_change_t"] = round(now - t0, 3)
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
                    try:
                        smp = {"t": round(now - t0, 3), "timer": w(TIMER)}
                        for k, a in acts.items():
                            ib, cb = p.read(a["ini"], VLEN), p.read(a["cur"], VLEN)
                            smp[k] = {"beh": w(a["intel"] + 8), "ini_v5": struct.unpack_from(">i", ib, V5)[0],
                                      "cur_v5": struct.unpack_from(">i", cb, V5)[0],
                                      "v8": struct.unpack_from(">I", cb, V8)[0]}
                        smp["timer2"] = w(TIMER)
                        samples.append(smp)
                    except Exception as x:
                        row["sampling_stopped"] = type(x).__name__
                        acts = {}
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


def intervals(samples, key):
    """Distinct nonzero v8 values in order; their differences; and whether each new value lies in the timer window."""
    vals, inwin, prev = [], [], None
    for s in samples:
        if key not in s:
            continue
        v = s[key]["v8"]
        if v and (not vals or v != vals[-1]):
            vals.append(v)
            if prev is not None:
                inwin.append(prev["timer"] <= v <= s["timer2"])
        prev = s
    d = [b - a for a, b in zip(vals, vals[1:])]
    return vals, d, inwin


def judge(tag):
    data, ptr, tl = files()
    L = layout()
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
    invalid = [c for c, r in out.items() if r.get("error") or not r["samples"]
               or ((r.get("live_first") or {}).get("lists") or {}).get("error")
               or (c != "exit" and r["samples"][-1]["t"] - r["samples"][0]["t"] < 60)]
    N = L["end"] - SIZE
    K = len(construct(data, ptr, tl, "diff")[3]["newslots"])

    def ab(r):
        return int(r["area"]["base"], 16) if r.get("area") else 0
    # S1
    want = sorted([("intro_10.lvl", str(SIZE), str(SIZE + N)), ("intro_10.ptr", str(PSIZE), str(PSIZE + 8 * K))])
    s1 = all(out[c]["grow_size"] == want and out[c]["served_files"] == ["intro_10.lvl", "intro_10.ptr", "transit.lvl"]
             for c in GROWN)
    s1 = s1 and out["base"]["mods_off"] and not out["base"]["grow_size"] and out["nogate"]["refused"] \
        and not out["nogate"]["grow_size"] and not out["nogate"]["served_files"]
    shas = {c: r.get("original_readback_sha256") for c, r in out.items()}
    s1 = s1 and shas["base"] is not None and len(set(shas.values())) == 1

    # S2
    def union(lst):
        d, i = lst.get("dw", {}), lst.get("inactive", {})
        both = d.get("walk", []) + i.get("walk", [])
        return set(both), len(both) == len(set(both)) and d.get("prev_ok") and i.get("prev_ok"), set(d.get("walk", []))
    a_u = union(((out["base"].get("live_first") or {}).get("lists")) or {})[0]
    reg = {}
    for c, r in out.items():
        b = ab(r)
        copy_so, src_so = b + L["fc"] - 4, b + SRC - 4
        ok = bool(b) and len(a_u) == 66
        for k in ("live_first", "live_end"):
            if k == "live_end" and c == "exit":
                continue
            lst = ((r.get(k) or {}).get("lists")) or {}
            U, nodup, dws = union(lst)
            rec, per = lst.get("rec", {}), lst.get("personal", {})
            ok = ok and nodup and src_so in dws
            if c in GROWN:
                ok = (ok and U == a_u | {copy_so} and copy_so not in a_u and copy_so in dws
                      and rec.get("count") == rec.get("n") == 123 and rec.get("last_so") == copy_so
                      and all(copy_so + o in lst.get("bak_targets", []) for o in (0xC4, 0x510, 0x514, 0x518))
                      and per.get("count") == 70 and per.get("last_name") == NEW_NAME.split(bytes(1))[0].decode())
            else:
                ok = ok and U == a_u and rec.get("count") == rec.get("n") == 122 and per.get("count") == 69
        reg[c] = {"ok": bool(ok), "always_diag": {k: (((r.get(k) or {}).get("lists")) or {}).get("always_diag")
                                                  for k in ("live_first", "live_end")}}
    s2 = all(v["ok"] for v in reg.values())
    # S3
    init = {}
    for c in GROWN:
        r, b = out[c], ab(out[c])
        a = r.get("actors") or {}
        sa, ca = a.get("src") or {}, a.get("copy") or {}
        lv = lambda fo: b + fo - 4                    # noqa: E731
        ok = bool(sa and ca)
        if ok:
            ok = (ca["dsgvar"] == sa["dsgvar"] and ca["ini"] == lv(L["fc"] + INI) and ca["cur"] == lv(L["fc"] + CUR)
                  and sa["ini"] == lv(SRC + INI) and sa["cur"] == lv(SRC + CUR)
                  and len({ca["ini"], ca["cur"], sa["ini"], sa["cur"]}) == 4 and ca["mind0"] == sa["mind0"]
                  and ca["dsgmem"] == lv(L["fc"] + DSGMEM) and ca["mind_dsgmem"] == ca["dsgmem"]
                  and ca["brain"] == lv(L["fc"] + BRAIN) and ca["mind"] == lv(L["fc"] + MIND)
                  and ca["intel"] == lv(L["fc"] + INTEL) and ca["brain4"] == sa["brain4"]
                  and ((ca["buf3d"] != 0 and ca["buf3d"] != sa["buf3d"]) if sa["buf3d"] else ca["buf3d"] == 0)
                  # revision 1: DsgMem +0 = the shared model +8; the copy's type-14 words resolved like the source's
                  and ca["dsgvar"] == sa["dsgvar"] == lv(MODEL + 8)
                  and len(ca["events"]) == len(sa["events"]) == 8 and ca["events"] == sa["events"]
                  and RAW_EVENT not in ca["events"])

        def fmt(d):
            return {k: ([f"{x:08x}" for x in v] if isinstance(v, list) else f"{v:08x}") for k, v in d.items()}
        init[c] = {"ok": bool(ok), "src": fmt(sa), "copy": fmt(ca)}
    s3 = all(v["ok"] for v in init.values())
    # S4 / S5 / S6
    beh = {}
    for c in ("base", "same", "diff"):
        r = out[c]
        sm = r["samples"]
        lo = r.get("loop_oneshot")
        e = {}
        for k in ("src", "copy"):
            if c == "base" and k == "copy":
                continue
            vals, d, inwin = intervals(sm, k)
            bs = [s[k]["beh"] for s in sm if k in s]
            first = next((i for i, x in enumerate(bs) if x == lo), None)
            e[k] = {"n_values": len(vals), "inwin_all": bool(inwin) and all(inwin),
                    "beh_ok": first is not None and all(x == lo for x in bs[first:]),
                    "min": min(d) if d else None, "median": statistics.median(d) if d else None,
                    "max": max(d) if d else None, "ini_v5": sorted({s[k]["ini_v5"] for s in sm if k in s}),
                    "cur_v5": sorted({s[k]["cur_v5"] for s in sm if k in s}), "v8_seq": vals[:6]}
        e["seq_identical"] = (c != "base" and intervals(sm, "src")[0] == intervals(sm, "copy")[0])
        beh[c] = e
    s4 = all(beh[c][k]["beh_ok"] and beh[c][k]["n_values"] >= 10 and beh[c][k]["inwin_all"]
             for c in ("same", "diff") for k in ("src", "copy"))
    s5 = (all(beh[c]["src"]["ini_v5"] == beh[c]["src"]["cur_v5"] == [500] for c in ("base", "same", "diff"))
          and beh["same"]["copy"]["ini_v5"] == beh["same"]["copy"]["cur_v5"] == [V5_SAME]
          and beh["diff"]["copy"]["ini_v5"] == beh["diff"]["copy"]["cur_v5"] == [V5_DIFF]
          and not beh["same"]["seq_identical"] and not beh["diff"]["seq_identical"])

    def med_in(x, lo_, hi_):
        return x is not None and lo_ <= x <= hi_
    s6 = (all(beh[c]["copy"]["min"] is not None and beh[c]["copy"]["min"] >= v and
              med_in(beh[c]["copy"]["median"], v, v + 100) for c, v in (("same", V5_SAME), ("diff", V5_DIFF)))
          and all(med_in(beh[c]["src"]["median"], 500, 600) for c in ("base", "same", "diff"))
          and med_in(beh["diff"]["copy"]["median"] / beh["diff"]["src"]["median"], 3.6, 4.4)
          and med_in(beh["same"]["copy"]["median"] / beh["same"]["src"]["median"], 0.9, 1.1)
          and all(not out[c].get("level_change_t") and "intro_15.lvl" not in out[c]["lvl_opens"]
                  for c in ("base", "same", "diff", "nogate")))
    # S7
    alloc = {}
    for c, r in out.items():
        st = r["states"]
        i0 = next((k for k, x in enumerate(st) if "invalid" not in x), None)
        valid = i0 is not None and not any("invalid" in x for x in st[i0:])
        used = [s for s in st if "invalid" not in s and "1" in s.get("areas", {}) and s.get("state") != "after_change"]
        fa = [s for s in st if s.get("state") in ("after_change", "final") and "invalid" not in s
              and "1" in s.get("areas", {}) and s["areas"]["1"]["length"] == 8474196]
        alloc[c] = {"valid": valid, "length": (r.get("area") or {}).get("length"),
                    "free_after": used[-1]["free_bytes"] if used else None,
                    "after_change": [(s["areas"]["1"]["base"], s["free_bytes"]) for s in fa][-1:],
                    "level_change_t": r.get("level_change_t")}
    s7 = all(alloc[c]["valid"] and alloc[c]["length"] == AREA + (N if c in GROWN else 0) for c in CASES)
    s7 = s7 and alloc["base"]["free_after"] == FREE0 and alloc["nogate"]["free_after"] == FREE0
    s7 = s7 and all(alloc[c]["free_after"] in (FREE0 - N, FREE0 - N - 24) for c in ("same", "diff"))
    s7 = s7 and alloc["exit"]["after_change"] == [("0x40f5f320", 12234744)] \
        and (alloc["exit"]["level_change_t"] or 1e9) <= 130 and "intro_15.lvl" in out["exit"]["lvl_opens"]
    s8 = all(r["haptics_policy"] and not any(r["judges"].values()) and r["runner_exit"] == 0 and not r["process_left"]
             for r in out.values())
    checks = {"S1_resource": bool(s1), "S2_registration": bool(s2), "S3_initialization": bool(s3),
              "S4_script_execution": bool(s4), "S5_designer_independence": bool(s5), "S6_functional_effect": bool(s6),
              "S7_cleanup": bool(s7), "S8_safety": bool(s8)}
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()),
              "registration": reg, "init": init, "behaviour": beh, "alloc": alloc, "readback": shas,
              "grow_size": {c: r["grow_size"] for c, r in out.items()},
              "served": {c: r["served_files"] for c, r in out.items()},
              "judges": {c: r["judges"] for c, r in out.items()},
              "runner_exit": {c: r["runner_exit"] for c, r in out.items()}}
    (ROOT / "private" / "work" / PREFIX / tag / "judgement.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("invalid", "checks", "pass", "init", "behaviour", "alloc")}, indent=1))
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
