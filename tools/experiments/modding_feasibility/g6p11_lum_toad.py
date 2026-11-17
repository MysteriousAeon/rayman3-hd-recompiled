#!/usr/bin/env python3
"""E-497 (D-264) G6-P11: heterogeneous actor composition. One additional intro_10 NIN_m_Lums_Int10 (G6-P1's source,
instance 6, preset `flight_path`) and one additional NIN_m_ToadIntro (G6-P8's source, instance 1, `at_source`) built
by ONE coordinated construction (`insert-lum-toad-pair`, development-only) into ONE version-2 transaction.
Development-only; private; hidden. Outputs: private/work/e497/.

  g6p11_lum_toad.py check        O-A..O-E offline (check.json; runtime transaction cases in negtest_het/)
  g6p11_lum_toad.py recovery     G6-P9's K1-K5 marker check, unchanged, on the heterogeneous mod (recovery.json)
  g6p11_lum_toad.py run TAG      hidden runs A, B, C (development build)
  g6p11_lum_toad.py judge TAG    P1-P6

DESIGN (derived from the original files before the first compile): both sources are 0x4B8 blocks with census 14 / 16
/ 1 and parse to the SAME list state (personal types 69, SO records 122, 181 backup links, world 60). The Toad source
0x581268 is world child 20 (next 0x581720), the Lum source 0x549A30 child 33 (next 0x549EE8): not adjacent, so the
world gets two independent insertion sites (Lum copy after the Lum source, Toad copy after the Toad source) and FOUR
chain words change (each source's +0x14, each next's +0x18) plus the eight list words: TWELVE original words, each
edited once (counts + 2), transit's actor count + 2. Each copy keeps its own recipe (class map, personal-type
template, SO record, matrix backup, shared targets: the two shared-target sets are disjoint). Layout (S = 7,661,836,
S % 16 = 12): Lum copy 0x74E910 (phase 0 = G6-P1's copy offset), Toad copy 0x74EDC8 (phase 8, no pad), then the
Lum's registration (element 0x14, name 24, record 0x48, backup 0x18, matrix copy 0x54) and the Toad's (name 20);
tail 2,868; .ptr + 80 entries = 640 (Lum's 31 block words, Toad's 31, Lum's 9, Toad's 9 registration words). Personal
indices: Lum 69, Toad 70; names NIN_m_Lums_Int10_G4B (G6-P1's) and XAP_ToadIntro_G6P7 (G6-P8's). The Lum copy block
is predicted byte-identical to G6-P1's single copy (same offset, links, index and position).

OFFLINE ACCEPTANCE (before any build): O-A identity and ownership, O-B structural integrity, O-C transaction and
refusal (runtime transaction cases dev 15 / 15, prod 2 / 2 + compile / builder / independent-simulator negatives),
O-D compatibility (G6-P5 frozen compare, selftest, G6-P9 pair images = its retained hashes, single Toad images =
G6-P8's), O-E determinism. The independent simulator (simulate_het) shares no code with the compiler's builder or
verifier and derives every expectation from the original files.

OFFLINE RESULT (check, first run, before any build or modified run): O-A..O-E PASS. Plan `level-tx 2 intro_10
g6p11.lum-toad b0382292dec88103`; images lvl 47a19a1e... (7,664,704), ptr b6e8a2e8... (209,708), transit 8addf2c0...
(41,508, count +2: the same transit image as G6-P9's pair); copies 0x74E910 / 0x74EDC8 as designed, indices 69 / 70;
each copy 14 owned / 14 shared (7 distinct targets each, the two sets disjoint) / 1 other-file / 2 links; the Lum copy
= G6-P1's single copy byte for byte; twelve original words; 80 entries (78 own-file, 2 transit) exactly as derived;
budget: free after load 13,085,660, headroom 11,170,940. Runtime transaction cases dev 15 / 15, prod 2 / 2; 19 compile
refusals (STRUCTURAL_CONFLICT for the three conflicting mods), 14 builder / simulator and 6 independent-simulator
refusals; G6-P5 compare PASS, selftest 337 / 337, G6-P9 pair images = its retained hashes, single Toad = G6-P8's.
RECOVERY: G6-P9's K1-K5, unchanged, PASS on this mod (no marker or loader code changed).

RUNTIME PROTOCOL (committed before the development build and before any modified run)
Build: g5p1_dev_gate.py apply (unchanged gate) + build_incremental; afterwards revert + production rebuild. Runner:
G6-P8's run_case (hidden, non-activating, muted, no physical pad, private user root, --test-level intro_10, 150 s,
guest-scoped Exit Game 85 s after intro_10.lvl opened; early 4-ms reads; full reads at 6 s and 80 s; 0.1-s samples)
with its new default-None sample_hook reading the Lum generator (NIN_m_GenFlyIntro_10 instance 0) variable 5 and
position each sample (read-only). Tracked: t0-t3, lum (0x549A30), and in B lumC 0x74E910 / toadC 0x74EDC8. Fresh
controls on the same build (memory baselines must be matched). X(o) = area base + o - 4.
  A: no plan.  B: insert-lum-toad-pair (mod g6p11.lum-toad, real compiler, marker armed, gate on).  C: B's plan
  compiled the same way, gate variable unset.
  P1 atomic activation (B): one `M33 mods state=active`; exactly one `G5P1 level-tx active level=intro_10
     mod=g6p11.lum-toad id=<plan id>`; `G6P1 level-tx version=2 members=lvl,ptr,transit`; snapshots 7,664,704 /
     209,708 / 41,508; grow 7661836 -> 7664704, 209068 -> 209708, 41508 -> 41508; served exactly the three; no host
     change; A `M33 mods=off`.
  P2 registration and ownership (B; first read unless stated): union = A's + exactly X(lumC), X(toadC), no
     duplicate, walks consistent; dynamic world X(lumC) right after X(lum), X(toadC) right after X(t1); lumC alive
     with model NIN_m_Lums_Int10, toadC with NIN_m_ToadIntro; SO records A + 2, last two [X(lumC), X(toadC)], each of
     the two copies and two sources once; backup targets A's + 2 with X(lumC + 0xC4), X(toadC + 0xC4) once each;
     personal types 71, last XAP_ToadIntro_G6P7; personal index lumC 69, toadC 70, lum 42, t1 0x1D. At both full
     reads: each copy's Perso / 3dData / StdGame / Brain / Mind / Intelligence = X(copy + its source's file chain
     offset), Mind +0 = its source's Mind +0 (toadC: X(0x580C78)), Brain +4 = 0xCDCDCDCD (copies and sources),
     3dData buffer word non-zero, distinct between the copies and from t0-t3 and lum; any live word of the lum /
     lumC / t1 / toadC blocks that points into another of the four must be a world link (lum +0x14 = X(lumC), lumC
     +0x18 = X(lum), t1 +0x14 = X(toadC), toadC +0x18 = X(t1)) or a +0x4A8 guest-list next / prev equal to the walked
     list. The +0x4A8 guest list: reciprocal, owners unique, one header, ends 0 / 0, length A + 2, owners minus the
     two copies = A's owners, both copies' elements present with the common header, toadC's element right after
     t1's (G6-P8 / P9 precedent). The Lum copy's place in that list is a prediction (right after the Lum source's:
     recorded, not judged). C: A's union / records, 69 types, no copy.
  P3 Lum behaviour (G6-P1's witness, A5r form): B: generator variable 5 is 0 at the first sample and changes exactly
     once, 0 -> 1, and the minimum generator-to-flight_path-anchor distance over samples within 2 s of the change
     is <= 3.0 (the nearest original lum is 29.5 units from that spot); it stays 1 to the last sample in intro_10;
     lumC's position at the first read = the anchor (each coordinate within 0.01) and lum's = its file position.
     A and C: variable 5 is 0 throughout (no change).
  P4 Toad behaviour (G6-P8's oracle): toadC meets oracle (a)-(d') (one Init run 0xFF -> 0, draw + 1, (Init, Init)
     -> (Jump, Wait) through the shared model, then idle, one position, stamp visits); position = t1's; StdGame stamp
     = t1's in >= 95 % of samples; t0-t3 meet the oracle in B and C.
  P5 cleanup: route intro_10 -> menumap in A, B, C; loaded B - A = {area 1 length +2,868, free -2,868, largest
     -2,868}, C - A = {}; between levels fix only (20,795,836, 1 / 1) in all; menumap state = A's in B and C; at the
     80-s read both copies are still once in the union (the collected Lum stays registered, as G6-P1 P5).
  P6 isolation and safety: C `state=refused reason=level_tx_not_enabled`, nothing served, no grow, no G5P1 / G5P3 /
     G6P1 line; every run M21 / M22 / M23 0, haptics policy line, runner exit 0, no game process left, walks
     consistent and no duplicate at both reads, no access-violation / engine-error line, fault codes within
     {406D1388}; B's marker armed (session, plan SHA-256) and cleared after the controlled end; check / recovery /
     negtest passed first.
  Invalid (new tag, kept): process / area not found, a tracked actor unreadable at the first read, < 60 s of samples,
     no generator samples, B's first variable-5 sample already 1 (sampling started after the pickup), A's originals
     failing the Toad oracle, A's route not taken.
  Stop: a guest fault, bad ownership / aliasing, list corruption or a desktop-safety violation.
  Verdict: PASS = P1-P6; P1 + P2 true with P3, P4 or P5 false = PARTIAL (named); otherwise FAIL (named); BLOCKED
  decided by hand and recorded.
RUN h1 (protocol 29023bc; recorded after the run): FAIL (P2 only); kept. P1, P3 (variable 5 0 -> 1 once at 11.5 s,
  0.499 units from the anchor), P4, P5 (B - A = +2,868 / -2,868 / -2,868, fix only, menumap = A's) and P6 true. P2's
  failing terms were three predictions about the LUM copy's run-time placement, each contradicted the same way by
  G6-P1's retained verified run (private/work/e484/h1/on): (1) the guest re-sorts actors between the dynamic and
  inactive worlds at run time (A's own Lum source is world child 21 of 41 at 9 s, inactive at 83 s), so "X(lumC)
  right after X(lum) in the live dynamic world" was a file-order assumption (G6-P1 judged union membership only);
  (2) the +0x4A8 lists are several (HYPOTHESIS: per sector): the Lum copy's element is {X(lumC), .., X(0x549A20),
  header X(0x122658)}, not in the Toad source's list (header X(0x2FE1A8)), exactly as G6-P1 h1's copy element (same
  header, same prev), so "Toad list length A + 2" was wrong; (3) after the pickup the Lum copy's 3dData buffer word is
  0 at the 80-s read (G6-P1 h1's end read: 0 too), so "non-zero at both reads" was wrong for a collected Lum. No
  construction, ownership or list defect: every other P2 term held (registration 68 / 124 / 183 / 71, indices 69 /
  70 / 42 / 0x1D, own chains, shared models, no unexplained cross-block word, Toad list order t1 -> toadC).
REVISION 1 (committed before run h2; h1's verdict stands): P2 changes only these three terms, each from G6-P1 h1's
  retained data: (1) the Lum copy once in the union (the Toad copy still right after t1 in the dynamic world), and
  the Lum source's / copy's +0x14 / +0x18 words equal their walked live-world neighbours (h1: always; the Toad
  pair keeps t1 +0x14 = X(toadC), toadC +0x18 = X(t1));
  (2) the Toad source's +0x4A8 list: length A + 1, owners minus toadC = A's, toadC right after t1, lumC absent; the
  Lum copy's own element = {owner X(lumC), prev X(0x549A20), header X(0x122658)} (G6-P1 h1's values) at both reads;
  (3) the Lum copy's buffer word non-zero and distinct at the first read; at the 80-s read 0 if variable 5 changed
  before that read (non-zero otherwise). Everything else unchanged. A fresh run h2 (A, B, C) decides.
RUN h2 (revision 1, 621426d; recorded after the run): PASS, P1-P6. Transaction b0382292dec88103 active (7,664,704 /
  209,708 / 41,508); union 66 -> 68, records 124 (Lum, Toad last), backups 183, personal 71, indices 69 / 70; own
  chains and buffers (Lum 0x426E0B70, Toad 0x426E07EC), shared models; Toad list 20 -> 21 (t1 -> copy), the Lum
  copy's element as G6-P1's; variable 5 0 -> 1 once at 11.56 s, 0.499 units; Toad Init 11 -> 12 then idle, stamps
  892 / 894; B - A = +2,868 / -2,868 / -2,868, C - A = none, fix only 20,795,836, menumap 13,274,536; C refused;
  marker armed and cleared; safety clean.
"""
import hashlib
import json
import math
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(TOOLS), str(HERE)]

import r3hd_mods as rm  # noqa: E402
import g5p1_pilot as p1  # noqa: E402
import g6p7_fifth_actor as g7  # noqa: E402
import g6p8_toad as g8  # noqa: E402
import g6p9_toad_pair as g9  # noqa: E402

PREFIX = "e497"
WORK = ROOT / "private" / "work" / PREFIX
LEVEL = "intro_10"
SIZE, PSIZE, TSIZE = g8.SIZE, g8.PSIZE, g8.TSIZE
N_LVL, N_PTR, N_SLOTS = 2868, 640, 80
BLK = 0x4B8
LUM_SRC, TOAD_SRC = 0x549A30, 0x581268
LUM_COPY, TOAD_COPY = 0x74E910, 0x74EDC8
NAMES = (b"NIN_m_Lums_Int10_G4B", b"XAP_ToadIntro_G6P7")
ANCHOR = (17.87, -101.22, -44.18)                      # G4b C / E, G6-P1's runtime-verified flight_path preset
PH, BH, RREF, W = 0x1C74, 0x1CEC, 0x1CFC, 0x9B4
MOD = "g6p11.lum-toad"
sha = lambda b: hashlib.sha256(b).hexdigest()   # noqa: E731
u32 = g8.u32
f32 = lambda v: struct.unpack(">f", struct.pack(">f", v))[0]   # noqa: E731


def het_op(**kw):
    lvl, ptr, tl = g8.files()
    o = {"type": "insert-lum-toad-pair", "level": LEVEL, "lvl_sha256": sha(lvl), "ptr_sha256": sha(ptr),
         "transit_sha256": sha(tl), "lum_model": rm.LUM10, "lum_instance": 6, "lum_placement": "flight_path",
         "toad_model": g8.TOAD, "toad_instance": 1, "toad_placement": "at_source", "owner": "dynamic_world"}
    o.update(kw)
    return o


def lum_op(**kw):
    lvl, ptr, tl = g8.files()
    o = {"type": "insert-passive-lum", "level": LEVEL, "model": rm.LUM10, "instance": 6, "lvl_sha256": sha(lvl),
         "ptr_sha256": sha(ptr), "transit_sha256": sha(tl), "position": [f32(v) for v in ANCHOR]}
    o.update(kw)
    return o


def compile_mods(name, mods, session=None, env=LEVEL):
    """The real compiler (import + resolve_all) in e497."""
    g8.WORK = WORK
    return g8.compile_typed(name, mods, session=session, env=env)


# --- the independent simulator (shares no code with the compiler's builder or verifier) -------------------------------

def simulate_het(lvl, ptr, tl, nl, np_, nt, me):
    """Re-reads the composed files as the loader would (own-file slots resolved; the new .ptr parsed afresh), derives
    every expectation from the ORIGINAL files only, and walks both copies and every list."""
    d = {}
    n0, n, m = u32(ptr, 0), u32(np_, 0), u32(lvl, 0)
    ent = lambda b, i: struct.unpack_from(">iI", b, 4 + 8 * i)   # noqa: E731
    d["ptr_layout"] = 4 + 8 * n + 16 * m == len(np_) and np_[4:4 + 8 * n0] == ptr[4:4 + 8 * n0] \
        and np_[4 + 8 * n:] == ptr[4 + 8 * n0:]
    old = {loc + 4: f for f, loc in (ent(ptr, i) for i in range(n0))}
    added = [(f, loc + 4) for f, loc in (ent(np_, i) for i in range(n0, n))]
    new, dup = dict(old), False
    for f, o in added:
        dup = dup or o in new
        new[o] = f
    d["new_entries"], d["new_slots_unique"] = len(added), not dup
    tgt = lambda b, sl, o: u32(b, o) + 4 if sl.get(o) == me and o + 4 <= len(b) else None   # noqa: E731
    size = len(lvl)

    def walk(b, sl, start, step=0):
        out, x = [], start
        while x is not None and x not in out and len(out) < 70000:
            out.append(x)
            x = tgt(b, sl, x + step)
        return out
    srcs = (LUM_SRC, TOAD_SRC)
    nxt = [tgt(lvl, old, s + 0x14) for s in srcs]
    cps = [tgt(nl, new, s + 0x14) for s in srcs]
    d["copies"] = cps
    d["chain"] = bool(all(cps) and size <= cps[0] < cps[1] and cps[1] >= cps[0] + BLK
                      and all(c % 16 == s % 16 for c, s in zip(cps, srcs))
                      and all(tgt(nl, new, c + 0x18) == s and tgt(nl, new, c + 0x14) == x
                              and tgt(nl, new, x + 0x18) == c for c, s, x in zip(cps, srcs, nxt)))
    if not d["chain"]:
        return {"pass": False, **d}
    blocks = list(srcs) + cps

    def chain_offsets(b, sl, so):
        perso = tgt(b, sl, so + 4)
        brain = tgt(b, sl, perso + 0xC)
        mind = tgt(b, sl, brain)
        return {"perso": perso - so, "3ddata": tgt(b, sl, perso) - so, "stdgame": tgt(b, sl, perso + 4) - so,
                "brain": brain - so, "mind": mind - so, "intel": tgt(b, sl, mind + 4) - so}
    d["kinds"], bad, d["chain_offsets"], d["shared_targets"] = {}, {}, {}, []
    for C, S, X in zip(cps, srcs, nxt):
        link = {0x14: X, 0x18: S}
        std_k = tgt(lvl, old, tgt(lvl, old, S + 4) + 4) - S
        kinds, shared = {}, set()
        for k in range(0, BLK, 4):
            so_, co = S + k, C + k
            if so_ not in old:
                same = co not in new and (nl[co:co + 4] == lvl[so_:so_ + 4] or k == std_k + 8
                                          or (C == cps[0] and 0 <= k - 0xC4 - 0x34 < 12)
                                          or (C == cps[0] and 0 <= k - 0x260 - 0x34 < 12)
                                          or (C == cps[0] and 0 <= k - 0x498 < 12))
                kind = "data"
            elif old[so_] != me:
                same, kind = new.get(co) == old[so_] and nl[co:co + 4] == lvl[so_:so_ + 4], "other-file"
            elif k in link:
                same, kind = tgt(nl, new, co) == link[k], "link"
            elif S <= tgt(lvl, old, so_) < S + BLK:
                same, kind = tgt(nl, new, co) == C + tgt(lvl, old, so_) - S, "owned"
            else:
                same, kind = tgt(nl, new, co) == tgt(lvl, old, so_), "shared"
                shared.add(tgt(lvl, old, so_))
            kinds[kind] = kinds.get(kind, 0) + 1
            if not same:
                bad[f"{C:#x}+{k:#x}"] = kind
        d["kinds"][f"{C:#x}"] = kinds
        d["shared_targets"].append(shared)
        co_s, co_c = chain_offsets(lvl, old, S), chain_offsets(nl, new, C)
        d["chain_offsets"][f"{C:#x}"] = co_c
        mind_s, mind_c = S + co_s["mind"], C + co_c["mind"]
        d.setdefault("model_shared", []).append(
            co_c == co_s and all(0 <= v < BLK for v in co_c.values())
            and tgt(nl, new, mind_c) == tgt(lvl, old, mind_s) is not None
            and not any(b <= tgt(nl, new, mind_c) < b + BLK for b in blocks))
        d.setdefault("cross_block", []).append(
            [hex(k) for k in range(0, BLK, 4) if (C + k) in new and k not in link and tgt(nl, new, C + k) is not None
             and any(b != C and b <= tgt(nl, new, C + k) < b + BLK for b in blocks)])
        d.setdefault("std_index", []).append(u32(nl, C + std_k + 8))
    d["toad_model"] = tgt(nl, new, cps[1] + d["chain_offsets"][f"{cps[1]:#x}"]["mind"]) == g8.AI_MODEL
    d["shared_disjoint"] = not (d["shared_targets"][0] & d["shared_targets"][1])
    d["shared_targets"] = [len(x) for x in d["shared_targets"]]
    d["bad_words"] = bad
    pcount = u32(lvl, PH + 8)
    d["std_index_ok"] = d["std_index"] == [pcount, pcount + 1]
    anchor = struct.pack(">3f", *ANCHOR)
    d["positions"] = all(nl[cps[0] + t:cps[0] + t + 12] == anchor for t in (0xC4 + 0x34, 0x260 + 0x34, 0x498)) \
        and all(nl[cps[1] + t:cps[1] + t + 12] == lvl[TOAD_SRC + t:TOAD_SRC + t + 12]
                for t in (0xC4 + 0x34, 0x260 + 0x34, 0x498))
    # the world: from transit's first child (cross-file table), each copy right after its own source
    cross = [struct.unpack_from(">IiIi", ptr, 4 + 8 * n0 + 16 * j) for j in range(m)]
    first = [ob + 4 for oa, fa, ob, fb in cross if fa != me and fb == me and oa + 4 == W + 8]
    ow, nw = walk(lvl, old, first[0], 0x14), walk(nl, new, first[0], 0x14)
    want = []
    for x in ow:
        want += [x] + ([cps[srcs.index(x)]] if x in srcs else [])
    d["world_positions"] = [ow.index(s) for s in srcs]
    d["world"] = nw == want and u32(nt, W + 0x10) == u32(tl, W + 0x10) + 2 == len(nw) \
        and all(tgt(nl, new, y + 0x18) == x for x, y in zip(nw, nw[1:])) \
        and [o for o in range(0, len(tl), 4) if tl[o:o + 4] != nt[o:o + 4]] == [W + 0x10]
    rh = tgt(lvl, old, RREF)
    orl, nrl = walk(lvl, old, tgt(lvl, old, rh)), walk(nl, new, tgt(nl, new, rh))
    owners = [tgt(nl, new, r + 4) for r in nrl]
    srec = [next(r for r in orl if tgt(lvl, old, r + 4) == s) for s in srcs]
    d["records"] = nrl[:-2] == orl and owners[-2:] == cps and u32(nl, rh + 8) == len(nrl) \
        and tgt(nl, new, rh + 4) == nrl[-1] and all(owners.count(x) == 1 for x in blocks) \
        and all(nl[r + 8:r + 0x48] == lvl[s + 8:s + 0x48] for r, s in zip(nrl[-2:], srec))
    obl, nbl = walk(lvl, old, tgt(lvl, old, BH)), walk(nl, new, tgt(nl, new, BH))
    sbk = [next(ln - 4 for ln in obl if tgt(lvl, old, ln + 4) == s + 0xC4) for s in srcs]
    bk = []
    for C, ln, sb in zip(cps, nbl[-2:], sbk):
        r = ln - 4
        bc = tgt(nl, new, r + 0xC)
        bk.append(tgt(nl, new, r + 8) == C + 0xC4 and bc is not None and size <= bc and b"".join(
            nl[bc + q:bc + q + 4][::-1] for q in range(0, 0x54, 4)) == nl[C + 0xC4:C + 0xC4 + 0x54]
            and nl[r + 0x10:r + 0x18] == lvl[sb + 0x10:sb + 0x18])
    d["backups"] = nbl[:-2] == obl and len(nbl) == len(obl) + 2 and all(bk) and tgt(nl, new, BH + 4) == nbl[-1]
    opl, npl = walk(lvl, old, tgt(lvl, old, PH)), walk(nl, new, tgt(nl, new, PH))
    nm = lambda e: nl[tgt(nl, new, e + 0xC):tgt(nl, new, e + 0xC) + 0x40].split(b"\0")[0]   # noqa: E731
    names = [nm(e) for e in npl]
    tmpl = [opl[u32(lvl, s + tgt(lvl, old, tgt(lvl, old, s + 4) + 4) - s + 8)] for s in srcs]   # each source's type
    d["personal"] = npl[:-2] == opl and names[-2:] == list(NAMES) and len(set(names)) == len(names) \
        and u32(nl, PH + 8) == len(npl) == pcount + 2 and tgt(nl, new, PH + 4) == npl[-1] \
        and all(tgt(nl, new, y + 4) == x for x, y in zip(npl, npl[1:])) \
        and all(nl[e + 8:e + 0xC] == lvl[t + 8:t + 0xC] and nl[e + 0x10:e + 0x14] == lvl[t + 0x10:t + 0x14]
                for e, t in zip(npl[-2:], tmpl))
    # original words: exactly the four chain words and the eight list words, derived from the original files
    twelve = sorted({LUM_SRC + 0x14, nxt[0] + 0x18, TOAD_SRC + 0x14, nxt[1] + 0x18, PH + 4, PH + 8, opl[-1], rh + 4,
                     rh + 8, orl[-1], BH + 4, obl[-1]})
    changed = [o for o in range(0, size, 4) if nl[o:o + 4] != lvl[o:o + 4]]
    d["original_words"] = changed == twelve and len(twelve) == 12
    # the expected new relocation entries, in order: the Lum's block words, the Toad's, the Lum's and the Toad's
    # registration words
    exp = []
    for C, S in zip(cps, srcs):
        exp += [(old[S + k], C + k) for k in range(0, BLK, 4) if S + k in old]
    pp, rp, bp = opl[-1], orl[-1], obl[-1]
    for i in range(2):
        pe, rec, ln = npl[-2 + i], nrl[-2 + i], nbl[-2 + i]
        exp += [(me, pe + 4), (me, pe + 8), (me, pe + 0xC), (me, pp), (me, rec + 4), (me, rp),
                (me, ln - 4 + 8), (me, ln - 4 + 0xC), (me, bp)]
        pp, rp, bp = pe, rec, ln
    d["entries_as_expected"] = added == exp
    d["entries_inside_new_or_tails"] = all(o >= size or o in (opl[-1], orl[-1], obl[-1]) for _, o in added)
    d["padding_zero"] = nl[size:cps[0]] == bytes(cps[0] - size) and nl[cps[0] + BLK:cps[1]] == bytes(cps[1] - cps[0] - BLK)
    ok = all(v for k, v in d.items() if isinstance(v, bool)) and not bad and all(d["model_shared"]) \
        and d["cross_block"] == [[], []] and d["new_entries"] == N_SLOTS
    return {"pass": ok, **d}


# --- O-A..O-E ---------------------------------------------------------------------------------------------------------

def check():
    WORK.mkdir(parents=True, exist_ok=True)
    O, det = {}, {}
    lvl, ptr, tl = g8.files()
    Lv, ix, key, insts = g7.toad_inputs()
    me = Lv["me"]
    res, text, paths = compile_mods("het_valid", [(MOD, [het_op()])])
    m, imgs = g8.plan_images(text)
    nl, np_, nt = imgs["lvl"], imgs["ptr"], imgs["transit"]
    shutil.copyfile(paths["cache"] / rm.PLAN_NAME, WORK / "plan_het.txt")
    with p1.dev_env(LEVEL):
        ranges, tx = rm.compile_insert_lum_toad_pair(het_op(), paths)
    info = tx["info"]
    det["info"] = {k: info[k] for k in ("objects", "tail", "slots", "edits", "personal_index", "actors", "records",
                                        "personal_types", "names", "memory", "positions")}
    det["hashes"] = {k: sha(b) for k, b in imgs.items()}
    det["sizes"] = {k: len(b) for k, b in imgs.items()}
    det["txs"] = m["txs"]
    sources_ok = ([sha(lvl), sha(ptr), sha(tl)] == [g8.LVL_SHA, g8.PTR_SHA, g8.TRANSIT_SHA]
                  and (len(lvl), len(ptr), len(tl)) == (SIZE, PSIZE, TSIZE)
                  and [t.split(" ")[:2] for f in m["files"] for t in f["tx"]] ==
                  [["lvl", g8.LVL_SHA], ["ptr", g8.PTR_SHA], ["transit", g8.TRANSIT_SHA]])
    sim = simulate_het(lvl, ptr, tl, nl, np_, nt, me)
    det["simulation"] = sim
    # O-A identity and ownership; the Lum copy = G6-P1's single copy byte for byte
    r1, t1, _ = compile_mods("single_lum", [("g6p11.single-lum", [lum_op()])])
    _, im1 = g8.plan_images(t1)
    lum_same = nl[LUM_COPY:LUM_COPY + BLK] == im1["lvl"][LUM_COPY:LUM_COPY + BLK]
    rt, tt, _ = compile_mods("single_toad", [("g6p11.single-toad", [g8.typed_op()])])
    _, imt = g8.plan_images(tt)
    tdiff = [k for k in range(0, BLK, 4) if nl[TOAD_COPY + k:TOAD_COPY + k + 4] != imt["lvl"][0x74E918 + k:0x74E918 + k + 4]]
    det["O-A"] = {"copies": [hex(c) for c in sim["copies"] or []], "kinds": sim["kinds"],
                  "lum_copy_equals_single": lum_same, "toad_copy_vs_single_words": len(tdiff),
                  "chain_offsets": sim.get("chain_offsets"), "shared_targets": sim.get("shared_targets")}
    want_k = {"owned": 14, "shared": 14, "other-file": 1, "link": 2}
    O["O-A_identity_ownership"] = (
        sources_ok and res["active"] == [MOD] and sim["copies"] == [LUM_COPY, TOAD_COPY]
        and info["objects"]["copy"] == [LUM_COPY, TOAD_COPY] and sim["std_index_ok"]
        and info["personal_index"] == [69, 70] and info["names"] == [n.decode() for n in NAMES]
        and all({k: v for k, v in kd.items() if k != "data"} == want_k for kd in sim["kinds"].values())
        and not sim["bad_words"] and all(sim["model_shared"]) and sim["toad_model"] and sim["shared_disjoint"]
        and sim["cross_block"] == [[], []] and sim["positions"] and lum_same and r1["active"] == ["g6p11.single-lum"])
    # O-B structural integrity
    n0 = u32(ptr, 0)
    slots_new = [struct.unpack_from(">iI", np_, 4 + 8 * i) for i in range(n0, u32(np_, 0))]
    det["O-B"] = {"entries": len(slots_new), "own_file": sum(f == me for f, _ in slots_new),
                  "other_file": sum(f != me for f, _ in slots_new), "edits": info["edits"],
                  "world_positions": sim.get("world_positions")}
    O["O-B_structural_integrity"] = (
        sim["pass"] and sim["world"] and sim["records"] and sim["backups"] and sim["personal"]
        and sim["original_words"] and len(info["edits"]) == 12 and sim["entries_as_expected"]
        and sim["new_slots_unique"] and sim["entries_inside_new_or_tails"] and sim["ptr_layout"]
        and len(slots_new) == N_SLOTS and info["slots"] == N_SLOTS and info["tail"] == N_LVL
        and info["actors"] == u32(tl, W + 0x10) + 2
        and det["sizes"] == {"lvl": SIZE + N_LVL, "ptr": PSIZE + N_PTR, "transit": TSIZE})
    # O-C transaction and refusal
    members = []
    for f in m["files"]:
        role = {f"{LEVEL}.lvl": "lvl", f"{LEVEL}.ptr": "ptr", "transit.lvl": "transit"}[Path(f["path"]).name]
        orig = Path(f["path"]).read_bytes()
        members.append((role, Path(f["path"]).name, len(orig), sha(orig), len(imgs[role]), sha(imgs[role])))
    want_id = rm.tx_id(LEVEL, MOD, sorted(members), 2)
    det["tx_id"] = want_id
    g8.WORK = WORK
    saved_copy = g8.COPY
    g8.COPY = TOAD_COPY   # the runtime "aliased" case: the Toad copy's Intelligence local pointed into its source
    try:
        neg_rt = g8.negtest(text, "het", WORK / "negtest_het") == 0
    finally:
        g8.COPY = saved_copy
    tx_ok = (m["txs"] == [f"level-tx 2 {LEVEL} {MOD} {want_id}"] and len([x for f in m["files"] for x in f["tx"]]) == 3
             and sum(1 for f in m["files"] if f.get("grow")) == 2)

    def outcome(name, mods, env=LEVEL):
        r_, t_, _ = compile_mods(f"neg_{name}", mods, env=env)
        refused_ = "import_refused" in r_ or (not r_["active"] and all(x.get("code") for x in r_["mods"]))
        return {"refused": refused_, "code": r_["import_refused"][1] if "import_refused" in r_ else
                {x["id"]: x.get("code") for x in r_["mods"]}, "plan": bool(t_ and "level-tx" in t_)}
    pair = g9.pair_op()
    neg = {
        "wrong lvl hash": outcome("lvlsha", [(MOD, [het_op(lvl_sha256="0" * 64)])]),
        "wrong ptr hash": outcome("ptrsha", [(MOD, [het_op(ptr_sha256="1" * 64)])]),
        "wrong transit hash": outcome("tlsha", [(MOD, [het_op(transit_sha256="2" * 64)])]),
        "two operations in one mod": outcome("two", [(MOD, [het_op(), het_op()])]),
        "with a single Lum in one mod": outcome("withlum", [(MOD, [het_op(), lum_op()])]),
        "with a Toad pair in one mod": outcome("withpair", [(MOD, [het_op(), pair])]),
        "conflict: + single Lum mod": outcome("conflum", [(MOD, [het_op()]), ("g6p11.single-lum", [lum_op()])]),
        "conflict: + single Toad mod": outcome("conftoad", [(MOD, [het_op()]), ("g6p11.single-toad",
                                                                                 [g8.typed_op()])]),
        "conflict: + Toad pair mod": outcome("confpair", [(MOD, [het_op()]), ("g6p11.pair", [pair])]),
        "unsupported level": outcome("lvl20", [(MOD, [het_op(level="intro_20")])]),
        "other Lum instance": outcome("li5", [(MOD, [het_op(lum_instance=5)])]),
        "other Toad instance": outcome("ti0", [(MOD, [het_op(toad_instance=0)])]),
        "Toad model as the Lum": outcome("lmodel", [(MOD, [het_op(lum_model=g8.TOAD)])]),
        "unsupported model": outcome("fmodel", [(MOD, [het_op(toad_model=rm.FROG10)])]),
        "other Lum placement": outcome("lpl", [(MOD, [het_op(lum_placement="beside_source")])]),
        "raw Lum coordinates": outcome("lraw", [(MOD, [het_op(lum_placement=list(ANCHOR))])]),
        "raw address key": outcome("raw", [(MOD, [dict(het_op(), toad_copy=TOAD_COPY)])]),
        "gate unset": outcome("nogate", [(MOD, [het_op()])], env=None),
        "gate for another level": outcome("gate20", [(MOD, [het_op()])], env="intro_20"),
    }
    conflict_codes = [neg[k]["code"] for k in neg if k.startswith("conflict")]
    # builder / simulator negatives on the composed structure
    al = rm.LUM_TOAD_ALLOW[LEVEL]
    specs = [al["lum"], al["toad"]]
    linsts = ix["placements"][rm.LUM10]
    peers = [[i["so"] for n_, i in enumerate(linsts) if n_ != 6], [i["so"] for n_, i in enumerate(insts) if n_ != 1]]
    poss = [tuple(f32(v) for v in ANCHOR), struct.unpack_from(">3f", lvl, TOAD_SRC + 0xC4 + 0x34)]

    def build(lvl_=lvl, specs_=specs):
        return rm.build_lum_toad_pair(lvl_, ptr, tl, me, specs_, peers, poss, "neg")
    new_b, nptr_b, ntl_b, edits_b, info_b = build()
    ss = [rm._lum_source(lvl, ptr, tl, me, sp, pr, "neg") for sp, pr in zip(specs, peers)]
    L, _ = rm.lum_toad_layout(SIZE, LUM_SRC, TOAD_SRC, BLK, [24, 20], [1, 1], lambda w: None)
    new_slots = [(f, o + 4) for f, o in slots_new]

    def verify(nl_=new_b, np2=nptr_b, nt_=ntl_b, L_=L):
        return rm.verify_lum_toad_pair(lvl, ptr, tl, nl_, np2, nt_, me, specs, ss, L_, new_slots, edits_b, poss, "neg")

    def mut(img, o, v):
        b = bytearray(img)
        struct.pack_into(">I", b, o, v)
        return bytes(b)
    dup_identity = mut(new_b, L["record"][1] + 4, LUM_COPY - 4)          # the Toad's SO record names the Lum copy
    alias = mut(new_b, TOAD_COPY + g8.CHAIN["intel"] + 0x10, LUM_COPY + 0x350 - 4)   # Toad local -> Lum block
    model_swap = mut(new_b, TOAD_COPY + g8.CHAIN["mind"], u32(lvl, LUM_SRC + g8.CHAIN["mind"]))   # Toad Mind -> Lum
    half = mut(new_b, PH + 8, u32(lvl, PH + 8) + 1)                      # personal count + 1 only (incomplete)
    nT = u32(ptr, 0) + 62
    drop = bytes(struct.pack(">I", u32(nptr_b, 0) - 1) + nptr_b[4:4 + 8 * (nT - 1)] + nptr_b[4 + 8 * nT:])
    dslot = bytearray(nptr_b)
    dslot[4 + 8 * (u32(ptr, 0) + 79):4 + 8 * (u32(ptr, 0) + 80)] = \
        dslot[4 + 8 * (u32(ptr, 0) + 78):4 + 8 * (u32(ptr, 0) + 79)]
    ofile = bytearray(nptr_b)
    struct.pack_into(">i", ofile, 4 + 8 * (u32(ptr, 0) + 70), 0)
    overlap = {k: list(v) for k, v in L.items()}
    overlap["copy"] = [LUM_COPY, LUM_COPY + 0x18]                          # the Toad copy inside the Lum copy
    pc = mut(lvl, PH + 8, u32(lvl, PH + 8) + 1)
    sp_same = [dict(specs[0]), dict(specs[1], new_name=NAMES[0])]
    sp_old = [dict(specs[0]), dict(specs[1], new_name=b"XAP_ToadIntro_04")]
    sp_two_toads = [dict(specs[1]), dict(specs[1], new_name=b"XAP_ToadIntro_G6P9")]
    conflicting = [(PH + 8, u32(lvl, PH + 8), u32(lvl, PH + 8) + 1, "a"), (PH + 8, u32(lvl, PH + 8),
                                                                           u32(lvl, PH + 8) + 2, "b")]
    wrong_old = [(PH + 8, u32(lvl, PH + 8) + 5, 0, "personal.count")]

    def ref(fn):
        return p1.refused(fn, "STRUCTURE_CHECK") is True

    def edit_refused(plan):
        try:
            rm.apply_original_edits(lvl, bytearray(lvl), plan, lambda why: (_ for _ in ()).throw(ValueError(why)))
        except ValueError:
            return True
        return False
    bneg = {
        "duplicate identity (the Toad's SO record names the Lum copy)": ref(lambda: verify(nl_=dup_identity)),
        "aliasing (the Toad's Intelligence local into the Lum copy)": ref(lambda: verify(nl_=alias)),
        "wrong shared model (the Toad's Mind into the Lum's block)": ref(lambda: verify(nl_=model_swap)),
        "incomplete composition (personal count + 1)": ref(lambda: verify(nl_=half)),
        "incomplete relocations (the Toad's last block entry dropped)": ref(lambda: verify(np2=drop)),
        "malformed relocation (duplicate new slot)": ref(lambda: verify(np2=bytes(dslot))),
        "malformed relocation (own-file entry as other-file)": ref(lambda: verify(np2=bytes(ofile))),
        "overlapping allocation (the Toad copy inside the Lum copy)": ref(lambda: verify(L_=overlap)),
        "duplicate personal-type names": ref(lambda: build(specs_=sp_same)),
        "name of an existing personal type": ref(lambda: build(specs_=sp_old)),
        "the same source twice": ref(lambda: build(specs_=sp_two_toads)),
        "damaged input (personal count)": ref(lambda: build(lvl_=pc)),
        "conflicting original-word edits (one word twice)": edit_refused(conflicting),
        "original word not the expected value": edit_refused(wrong_old),
    }
    sneg = {k: not simulate_het(lvl, ptr, tl, nl_, np2, ntl_b, me)["pass"] for k, nl_, np2 in (
        ("independent: duplicate identity", dup_identity, nptr_b), ("independent: aliasing", alias, nptr_b),
        ("independent: wrong shared model", model_swap, nptr_b),
        ("independent: incomplete composition", half, nptr_b), ("independent: dropped entry", new_b, drop),
        ("independent: duplicate slot", new_b, bytes(dslot)))}
    det["O-C"] = {"tx_ok": tx_ok, "negtest_runtime": neg_rt, "compile": neg, "builder": bneg, "independent": sneg}
    O["O-C_transaction_refusal"] = (
        tx_ok and neg_rt and all(v["refused"] and not v["plan"] for v in neg.values()) and all(bneg.values())
        and all(sneg.values()) and all(set(c.values()) == {"STRUCTURAL_CONFLICT"} for c in conflict_codes)
        and (new_b, nptr_b, ntl_b) == (nl, np_, nt))
    # O-D compatibility: G6-P5 frozen compare, selftest, G6-P9 pair = its retained images, single Toad = G6-P8's
    eq = subprocess.run([sys.executable, str(HERE / "g6p5_equivalence.py"), "compare"], capture_output=True, text=True)
    st = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "selftest"], capture_output=True, text=True)
    rp, tp, _ = compile_mods("pair_ref", [("g6p9.toad-pair", [pair])])
    mp, imp = g8.plan_images(tp)
    retained = json.loads((ROOT / "private" / "work" / "e495" / "check.json").read_text())["details"]
    det["O-D"] = {"g6p5_compare": eq.stdout.strip().splitlines()[-1:], "selftest": st.stdout.strip().splitlines()[-1:],
                  "pair_hashes": {k: sha(b) for k, b in imp.items()}, "pair_txs": mp["txs"],
                  "single_toad_hashes": {k: sha(b) for k, b in imt.items()}}
    O["O-D_compatibility"] = (eq.returncode == 0 and st.returncode == 0
                              and det["O-D"]["pair_hashes"] == retained["hashes"] and mp["txs"] == retained["txs"]
                              and det["O-D"]["single_toad_hashes"] == g8.PROTO
                              and rt["active"] == ["g6p11.single-toad"] and rp["active"] == ["g6p9.toad-pair"])
    # O-E determinism
    res2, text2, _ = compile_mods("het_again", [(MOD, [het_op()])])
    strip = lambda t: "\n".join(x for x in t.splitlines() if not x.startswith(("# written by", "range ")))  # noqa
    rng = lambda mm: [[(r.split(" ")[:2], Path(r.split(" ", 5)[5]).read_bytes()) for r in f["range"]]   # noqa: E731
                      for f in mm["files"]]
    m2, imgs2 = g8.plan_images(text2)
    b2 = build()
    O["O-E_determinism"] = (strip(text) == strip(text2) and imgs2 == imgs and rng(m) == rng(m2)
                            and m2["txs"] == m["txs"] and b2[:4] == (new_b, nptr_b, ntl_b, edits_b))
    out = {"pass": all(O.values()), "O": O, "details": det}
    (WORK / "check.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(O, indent=1))
    print(json.dumps({k: det[k] for k in ("hashes", "sizes", "txs", "tx_id", "O-A", "O-B", "info")}, indent=1,
                     default=str))
    print("CHECK_G6P11", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


def recovery():
    """G6-P9's K1-K5, unchanged, on the heterogeneous mod: the marker names the whole transaction; an unfinished session
    refuses all of it (the ordinary waypoint mod stays active); clear re-enables; a controlled end clears; gate off."""
    saved = (g9.MOD, g9.pair_op, g9.WORK)
    g9.MOD, g9.pair_op, g9.WORK = MOD, het_op, WORK
    try:
        return g9.recovery()
    finally:
        g9.MOD, g9.pair_op, g9.WORK = saved


# --- the runtime (development build) ----------------------------------------------------------------------------------

CASES = ("A", "B", "C")
TRACK = {"lum": LUM_SRC}
REVISION = 1   # 0 reproduces run h1's original P2 terms (see RUN h1 / REVISION 1 above)
LUM_ELEM_PREV, LUM_ELEM_HEADER = 0x549A20, 0x122658   # G6-P1 h1's Lum copy element (file offsets), revision 1


def compile_case(name, session=None):
    res, text, paths = compile_mods(name, [(MOD, [het_op()])], session=session)
    if res["active"] != [MOD] or text is None:
        raise SystemExit(f"compiler refused the run's mod: {res.get('mods') or res}")
    return paths["cache"] / rm.PLAN_NAME, paths


def gen_hook():
    """Read-only: the Lum generator (NIN_m_GenFlyIntro_10 instance 0) variable 5 and position, each sample."""
    so = rm.read_script_index(g8.GAME, LEVEL)["placements"][rm.FLY10][0]["so"]
    st = {}

    def hook(p, ab):
        from m5_live import Actor
        try:
            if "a" not in st:
                st["a"] = Actor(p, ab + so - 4)
            v = st["a"].dsg()
            return {"v5": v[5][0][v[5][1]], "pos": list(st["a"].position())}
        except Exception as x:
            st.pop("a", None)
            return {"error": type(x).__name__}
    return hook


@__import__("contextlib").contextmanager
def harness(extra=None):
    saved = (g8.WORK, g8.PREFIX, g8.TOADS)
    g8.WORK, g8.PREFIX = WORK, PREFIX
    g8.TOADS = dict(g8.TOADS, **TRACK, **(extra or {}))
    try:
        yield
    finally:
        g8.WORK, g8.PREFIX, g8.TOADS = saved


def run(tag, cases=CASES):
    if g8.gate_status() != "patched":
        raise SystemExit("the development gate is not applied")
    for f in ("check.json", "recovery.json", "negtest_het/summary.json"):
        if not json.loads((WORK / f).read_text()).get("pass"):
            raise SystemExit(f"{f} did not pass")
    for case in cases:
        run_ = f"{PREFIX}_{tag}_{case}"
        if case == "A":
            with harness():
                row = g8.run_case(tag, case, sample_hook=gen_hook())
        elif case == "B":
            plan_, paths = compile_case(f"run_{tag}_B", session=run_)
            with harness({"lumC": LUM_COPY, "toadC": TOAD_COPY}):
                row = g8.run_case(tag, case, plan=plan_, env_level=LEVEL, session_paths=paths,
                                  sample_hook=gen_hook())
        else:
            plan_, paths = compile_case(f"run_{tag}_C")
            with harness():
                row = g8.run_case(tag, case, plan=plan_, env_level=None, sample_hook=gen_hook())
        print(case, json.dumps(row, default=str)[:400], flush=True)
    return 0


def judge(tag):
    import re
    with harness():
        out = {c: g8.load_case(tag, c) for c in CASES}
    A, B, C = (out[c] for c in CASES)
    X = lambda o: B["live"]["first"]["ab"] + o - 4   # noqa: E731
    det, P, invalid = {}, {}, []
    for c, r in out.items():
        lf = r["live"].get("first")
        if r.get("error") or not lf or any("error" in a for a in lf["actors"].values()):
            invalid.append(f"{c}:read")
        if not r["samples"] or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60:
            invalid.append(f"{c}:samples")
        if not [s for s in r["samples"] if "v5" in s.get("x", {})]:
            invalid.append(f"{c}:generator")
    opens = {c: [o.rsplit("\\", 1)[-1].lower() for o in re.findall(
        r"vfs_open path=(\S+?\.lvl) result=00000000", r["log"])] for c, r in out.items()}
    route_ok = {c: f"{LEVEL}.lvl" in o and "menumap.lvl" in o[o.index(f"{LEVEL}.lvl"):]
                and bool(out[c].get("level_change_t")) for c, o in opens.items()}
    det["route"] = {c: [opens[c], out[c].get("level_change_t")] for c in out}
    gen = {c: [(s["t"], s["x"]["v5"], s["x"]["pos"]) for s in r["samples"] if "v5" in s.get("x", {})]
           for c, r in out.items()}
    if gen["B"] and gen["B"][0][1] != 0:
        invalid.append("B:sampling_after_pickup")
    if not invalid:
        oa = {k: g8.behaviour_oracle(A, k) for k in ("t0", "t1", "t2", "t3")}
        det["oracle_A"] = {k: v[1] for k, v in oa.items()}
        if not all(v[0] for v in oa.values()):
            invalid.append("A:oracle")
        if not route_ok["A"]:
            invalid.append("A:route")
    if invalid:
        res = {"invalid": invalid, "verdict": "INVALID", "details": det}
        (WORK / f"judgement_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
        print(json.dumps({"invalid": invalid, "verdict": "INVALID"}))
        return 1
    log = B["log"]
    # P1 atomic activation
    ptx = p1.parse_plan((WORK / tag / "B" / "plan_copy.txt").read_text(encoding="utf-8"))["txs"]
    want = [tuple(ptx[0].split(" ")[2:5])]
    t = [tuple(x) for x in re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log)]
    snaps = sorted((f, b) for f, _, b, _ in re.findall(
        r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", log))
    grow = sorted(set(re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)))
    served = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
    P["P1_atomic_activation"] = (
        log.count("M33 mods state=active") == 1 and t == want and want[0][1] == MOD
        and log.count("G6P1 level-tx version=2 members=lvl,ptr,transit") >= 1
        and snaps == sorted([(f"{LEVEL}.lvl", str(SIZE + N_LVL)), (f"{LEVEL}.ptr", str(PSIZE + N_PTR)),
                             ("transit.lvl", str(TSIZE))])
        and grow == sorted([(f"{LEVEL}.lvl", str(SIZE), str(SIZE + N_LVL)),
                            (f"{LEVEL}.ptr", str(PSIZE), str(PSIZE + N_PTR)), ("transit.lvl", str(TSIZE), str(TSIZE))])
        and served == sorted([f"{LEVEL}.lvl", f"{LEVEL}.ptr", "transit.lvl"])
        and "G5P3 tx host_changed" not in log and "M33 mods=off" in A["log"])
    det["P1"] = {"tx": t, "want": want, "snaps": snaps, "grow": grow, "served": served}

    def union(r, which="first"):
        ls = r["live"][which]["lists"]
        return ls["dw"]["walk"] + ls["inactive"]["walk"]
    cps = [X(LUM_COPY), X(TOAD_COPY)]
    srcs = [X(LUM_SRC), X(TOAD_SRC)]
    lvl = g8.files()[0]
    old_slots = rm.actor_tables(lvl, g8.files()[1], g8.files()[2], g7.toad_inputs()[0]["me"], lambda w: None)
    tg = old_slots[2]

    def chain_offsets(so):
        perso = tg(so + 4)
        brain = tg(perso + 0xC)
        mind = tg(brain)
        return {"perso": perso - so, "3ddata": tg(perso) - so, "stdgame": tg(perso + 4) - so, "brain": brain - so,
                "mind": mind - so, "intel": tg(mind + 4) - so}
    offs = {"lumC": chain_offsets(LUM_SRC), "toadC": chain_offsets(TOAD_SRC)}
    det["chain_offsets"] = offs
    # P2 registration and ownership
    ls, la = B["live"]["first"]["lists"], A["live"]["first"]["lists"]
    fa = B["live"]["first"]["actors"]
    dw, u, ua, bt = ls["dw"]["walk"], union(B), union(A), ls["bak_targets"]
    after = lambda s: dw[dw.index(s) + 1] if s in dw and dw.index(s) + 1 < len(dw) else None   # noqa: E731
    reg = ("error" not in ls and ls["dw"]["prev_ok"] and ls["inactive"]["prev_ok"] and len(u) == len(set(u))
           and sorted(u) == sorted(ua + cps)
           and ([after(s) for s in srcs] == cps if REVISION == 0 else after(srcs[1]) == cps[1] and u.count(cps[0]) == 1)
           and fa["lumC"].get("alive") and fa["lumC"].get("model") == "NIN_m_Lums_Int10"
           and fa["toadC"].get("alive") and fa["toadC"].get("model") == "NIN_m_ToadIntro"
           and ls["rec"]["count"] == la["rec"]["count"] + 2 and ls["rec"]["owners"][-2:] == cps
           and all(ls["rec"]["owners"].count(x) == 1 for x in cps + srcs)
           and len(bt) == len(la["bak_targets"]) + 2 and all(bt.count(x + 0xC4) == 1 for x in cps)
           and ls["personal"] == {"count": 71, "last_name": NAMES[1].decode()}
           and [fa[k].get("std_personal") for k in ("lumC", "toadC", "lum", "t1")] == [69, 70, 42, 0x1D])
    lsc = C["live"]["first"]["lists"]
    regc = (sorted(union(C)) == sorted(ua) and lsc["personal"]["count"] == 69
            and lsc["rec"]["count"] == la["rec"]["count"] and not set(cps) & set(union(C)))
    det["P2_registration"] = {c: {"union": len(union(r)), "rec": r["live"]["first"]["lists"].get("rec", {}).get("count"),
                                  "bak": len(r["live"]["first"]["lists"].get("bak_targets", [])),
                                  "personal": r["live"]["first"]["lists"].get("personal")} for c, r in out.items()}
    det["P2_registration"]["B_after_sources"] = [hex(after(s) or 0) for s in srcs]

    def owners(r, which):
        return [e["owner"] for e in r["live"][which]["elist"]["chain"]]
    gb = gen["B"]
    coll_changes = [(gb[i][0], gb[i - 1][1], gb[i][1]) for i in range(1, len(gb)) if gb[i][1] != gb[i - 1][1]]

    def own(which):
        lv = B["live"].get(which)
        if not lv:
            return False, {"missing": which}
        acts = lv["actors"]
        d, ok = {}, True
        others = [acts[k].get("buffer") for k in ("t0", "t1", "t2", "t3", "lum")]
        blocks = {"lum": srcs[0], "lumC": cps[0], "t1": srcs[1], "toadC": cps[1]}
        el = lv.get("elist", {})
        ch = el.get("chain") or []
        at = {e["at"]: e for e in ch}
        world_ok = {("lum", 0x14): cps[0], ("lumC", 0x18): srcs[0], ("t1", 0x14): cps[1], ("toadC", 0x18): srcs[1]}
        if REVISION:   # revision 1 (1): the Lum pair's links follow the guest's live worlds (walked neighbours)
            walks = [lv["lists"]["dw"]["walk"], lv["lists"]["inactive"]["walk"]]

            def nb(x):
                for wk in walks:
                    if x in wk:
                        i = wk.index(x)
                        return (wk[i + 1] if i + 1 < len(wk) else 0), (wk[i - 1] if i else 0)
                return None, None
            del world_ok[("lum", 0x14)], world_ok[("lumC", 0x18)]
            for lab in ("lum", "lumC"):
                n_, p_ = nb(blocks[lab])
                world_ok[(lab, 0x14)], world_ok[(lab, 0x18)] = n_, p_
            d["lum_links_walked"] = {f"{k[0]}+{k[1]:#x}": hex(v or 0) for k, v in world_ok.items() if k[0] in
                                     ("lum", "lumC")}
        cross = {}
        for lab, base in blocks.items():
            words = acts[lab].get("block_words") or []
            for k, w_ in enumerate(words):
                for lab2, b2 in blocks.items():
                    if lab2 != lab and b2 <= w_ < b2 + BLK:
                        e = at.get(base + g8.ELEM)
                        okw = world_ok.get((lab, 4 * k)) == w_ or (
                            e is not None and ((4 * k == g8.ELEM + 4 and e["next"] == w_)
                                               or (4 * k == g8.ELEM + 8 and e["prev"] == w_)))
                        if not okw:
                            cross.setdefault(lab, []).append(hex(4 * k))
        d["unexplained_cross_block_words"] = cross
        ok = ok and not cross and all((acts[lab].get("block_words") or [None] * (BLK // 4))[k // 4] == v
                                      for (lab, k), v in world_ok.items())
        bufs = []
        for lab, src_lab, C0 in (("lumC", "lum", LUM_COPY), ("toadC", "t1", TOAD_COPY)):
            cp, sr, o_ = acts[lab], acts[src_lab], offs[lab]
            mind, smind = cp.get("mind") or [None] * 4, sr.get("mind") or [None] * 4
            buf_ok = bool(cp.get("buffer")) and cp.get("buffer") not in others
            if REVISION and lab == "lumC" and which == "end":   # revision 1 (3): a collected Lum's buffer word is 0
                ch_t = [x[0] for x in coll_changes]
                buf_ok = cp.get("buffer") == 0 if ch_t and ch_t[0] < lv["t"] else buf_ok
            c = {"chain_own": {k: cp.get(k) for k in ("perso", "3ddata", "stdgame", "brain")} ==
                 {k: X(C0 + o_[k]) for k in ("perso", "3ddata", "stdgame", "brain")},
                 "brain0_mind": (cp.get("brain_words") or [None])[0] == X(C0 + o_["mind"]),
                 "mind1_intel": mind[1] == X(C0 + o_["intel"]),
                 "model_shared": mind[0] == smind[0] and mind[0] is not None
                 and not any(b <= mind[0] < b + BLK for b in blocks.values()),
                 "brain4": (cp.get("brain_words") or [0, 0])[1] == 0xCDCDCDCD == (sr.get("brain_words") or [0, 0])[1],
                 "buffer_nonzero_not_original": buf_ok}
            if lab == "toadC":
                c["toad_ai_model"] = mind[0] == X(g8.AI_MODEL)
            bufs.append(cp.get("buffer"))
            d[lab] = c
            ok = ok and all(c.values())
        d["buffers_distinct"] = bufs[0] != bufs[1]
        recip = all(at[e["next"]]["prev"] == e["at"] for e in ch if e["next"] in at) and \
            all(at[e["prev"]]["next"] == e["at"] for e in ch if e["prev"] in at)
        ow = [e["owner"] for e in ch]
        oa = owners(A, which)
        els = [at.get(c_ + g8.ELEM) for c_ in cps]
        hdr = at.get(srcs[1] + g8.ELEM)
        nxt_owner = lambda s: ow[ow.index(s) + 1] if s in ow and ow.index(s) + 1 < len(ow) else None   # noqa: E731
        d["elist"] = {"len": len(ch), "len_A": len(oa), "reciprocal": recip, "owners_unique": len(ow) == len(set(ow)),
                      "one_header": len({e["header"] for e in ch}) == 1, "ends": el.get("ends"),
                      "after_toad_source": hex(nxt_owner(srcs[1]) or 0), "after_lum_source": hex(nxt_owner(srcs[0]) or 0),
                      "lum_predicted_order": nxt_owner(srcs[0]) == cps[0]}
        base_ok = bool(ch and "error" not in el and recip and d["elist"]["owners_unique"]
                       and d["elist"]["one_header"] and el.get("ends") == [0, 0] and hdr is not None
                       and nxt_owner(srcs[1]) == cps[1])
        if REVISION == 0:
            eok = base_ok and len(ch) == len(oa) + 2 and [x for x in ow if x not in cps] == oa \
                and all(e_ is not None and e_["owner"] == c_ and e_["header"] == hdr["header"] for e_, c_ in zip(els, cps))
        else:   # revision 1 (2): the Toad source's list gains toadC only; the Lum copy's own element as G6-P1 h1's
            lw = (acts["lumC"].get("block_words") or [None] * (BLK // 4))[g8.ELEM // 4:g8.ELEM // 4 + 4]
            d["lumC_element"] = [hex(x) if x is not None else None for x in lw]
            eok = base_ok and len(ch) == len(oa) + 1 and [x for x in ow if x != cps[1]] == oa \
                and cps[0] not in ow and els[1] is not None and els[1]["owner"] == cps[1] \
                and els[1]["header"] == hdr["header"] \
                and [lw[0], lw[2], lw[3]] == [cps[0], X(LUM_ELEM_PREV), X(LUM_ELEM_HEADER)]
        d["elist"]["ok"] = eok
        return bool(ok and d["buffers_distinct"] and eok), d
    of, dof = own("first")
    oe, doe = own("end")
    P["P2_registration_ownership"] = bool(reg and regc and of and oe)
    det["P2_ownership"] = {"registration_B": reg, "gate_off_C": regc, "first": dof, "end": doe}
    # P3 Lum behaviour
    anchor = [f32(v) for v in ANCHOR]
    coll = {}
    for c in CASES:
        s = gen[c]
        changes = [(s[i][0], s[i - 1][1], s[i][1]) for i in range(1, len(s)) if s[i][1] != s[i - 1][1]]
        near = None
        if changes:
            dd = [math.dist(x[2], anchor) for x in s if abs(x[0] - changes[0][0]) <= 2.0]
            near = round(min(dd), 3) if dd else None
        coll[c] = {"v5_first": s[0][1] if s else None, "v5_last": s[-1][1] if s else None, "changes": changes,
                   "near_change": near, "samples": len(s)}
    lpos = fa["lumC"].get("position") or [None] * 3
    spos = fa["lum"].get("position") or [None] * 3
    file_lum = list(struct.unpack_from(">3f", lvl, LUM_SRC + 0xC4 + 0x34))
    coll["lumC_first_position"], coll["lum_first_position"] = lpos, spos
    b_ = coll["B"]
    P["P3_lum_behaviour"] = bool(
        b_["v5_first"] == 0 and [x[1:] for x in b_["changes"]] == [(0, 1)] and b_["near_change"] is not None
        and b_["near_change"] <= 3.0 and b_["v5_last"] == 1
        and all(v is not None and abs(v - a_) <= 0.01 for v, a_ in zip(lpos, anchor))
        and all(v is not None and abs(v - a_) <= 0.01 for v, a_ in zip(spos, file_lum))
        and all(coll[c]["v5_first"] == 0 and not coll[c]["changes"] for c in ("A", "C")))
    det["P3_collection"] = coll
    # P4 Toad behaviour (G6-P8's oracle)
    ob = {k: g8.behaviour_oracle(B, k) for k in ("t0", "t1", "t2", "t3", "toadC")}
    oc = {k: g8.behaviour_oracle(C, k) for k in ("t0", "t1", "t2", "t3")}
    both = [(x["a"]["toadC"]["stamp"], x["a"]["t1"]["stamp"]) for x in B["samples"] if "toadC" in x["a"] and "t1" in x["a"]]
    stamps = [sum(1 for a_, b2 in both if a_ == b2), len(both)]
    det["P4_toad"] = {"B": {k: v[1] for k, v in ob.items()}, "C": {k: v[1] for k, v in oc.items()},
                      "stamp_equal_source": stamps}
    P["P4_toad_behaviour"] = bool(all(v[0] for v in ob.values()) and all(v[0] for v in oc.values())
                                  and ob["toadC"][1]["init_ok"] and ob["toadC"][1]["one_run"]
                                  and fa["toadC"]["position"] == fa["t1"]["position"]
                                  and stamps[1] and stamps[0] >= 0.95 * stamps[1])

    # P5 cleanup
    def brief(x):
        return None if not x else {"free": x["free_bytes"], "largest": x["largest_free"],
                                   "alloc": x["allocated_chunks"], "free_chunks": x["free_chunks"],
                                   "areas": {k: (v["base"], v["length"]) for k, v in x["areas"].items()}}

    def phases(r):
        st_ = [x for x in r["states"] if "invalid" not in x and "areas" in x]
        lvl_ = next((x for x in st_ if set(x["areas"]) == {"0", "1", "3"}), None)
        k = st_.index(lvl_) if lvl_ else None
        aft = st_[k + 1:] if k is not None else []
        fix = next((x for x in aft if set(x["areas"]) == {"0"}), None)
        menu = next((x for x in aft if set(x["areas"]) == {"0", "1", "2"}), None)
        return brief(lvl_), brief(fix), brief(menu)

    def diff(a, b):
        d = {k: a[k] - b[k] for k in ("free", "largest", "alloc", "free_chunks") if a[k] != b[k]}
        for k in sorted(set(a["areas"]) | set(b["areas"])):
            x, y = a["areas"].get(k), b["areas"].get(k)
            if x != y:
                d[f"area{k}_length" if x and y and x[0] == y[0] else f"area{k}"] = \
                    x[1] - y[1] if x and y and x[0] == y[0] else [x, y]
        return d
    ph = {c: phases(r) for c, r in out.items()}
    det["phases"] = ph
    try:
        dl = {c: diff(ph[c][0], ph["A"][0]) for c in "BC"}
        det["P5_loaded_diff"] = dl
        fix_ok = all(ph[c][1] and ph[c][1]["free"] == 20795836 and ph[c][1]["alloc"] == 1
                     and ph[c][1]["free_chunks"] == 1 for c in out)
        menu_ok = all(ph[c][2] and ph[c][2] == ph["A"][2] for c in "BC")
        end_ok = all(union(B, "end").count(x) == 1 for x in cps)
        det["P5_flags"] = {"route": route_ok, "fix_only": fix_ok, "menumap_equal": menu_ok, "copies_at_end": end_ok}
        P["P5_cleanup"] = bool(all(route_ok.values()) and dl["B"] == {"area1_length": N_LVL, "free": -N_LVL,
                                                                      "largest": -N_LVL}
                               and dl["C"] == {} and fix_ok and menu_ok and end_ok)
    except Exception as x:
        det["P5_error"] = repr(x)
        P["P5_cleanup"] = False

    # P6 isolation and safety
    def integ(r):
        ok = True
        for which in ("first", "end"):
            ls_ = r["live"].get(which, {}).get("lists", {})
            ok = ok and "error" not in ls_ and ls_.get("dw", {}).get("prev_ok") and ls_.get("inactive", {}).get("prev_ok")
            u_ = union(r, which) if ls_ else []
            ok = ok and len(u_) == len(set(u_))
        return bool(ok) and r["safety"]["fault_line"] is False and set(r["safety"]["fault_codes"]) <= {"406D1388"}
    marks = (B["marker_before_start"][0] == "armed" and B["marker_before_start"][1]["session"] == B["run"]
             and B["marker_before_start"][1]["plan_sha256"] == B["plan_sha256"] and B["controlled"] is True
             and B.get("session_end", {}).get("cleared") is True and B.get("marker_after") == "none")
    c_ok = ("state=refused reason=level_tx_not_enabled" in C["log"] and "M33 mods served" not in C["log"]
            and "M36 grow" not in C["log"] and not re.search(r"G5P1|G5P3|G6P1", C["log"]))
    P["P6_isolation_safety"] = bool(all(r["safe"] for r in out.values()) and all(integ(r) for r in out.values())
                                    and marks and c_ok)
    det["P6"] = {"marks": marks, "C_refused": c_ok, "integrity": {c: integ(r) for c, r in out.items()},
                 "safety": {c: r["safety"] for c, r in out.items()}}
    if all(P.values()):
        verdict = "PASS"
    elif P["P1_atomic_activation"] and P["P2_registration_ownership"]:
        verdict = "PARTIAL (" + ", ".join(k for k, v in P.items() if not v) + ")"
    else:
        verdict = "FAIL (" + ", ".join(k for k, v in P.items() if not v) + ")"
    res = {"invalid": invalid, "P": P, "verdict": verdict, "details": det}
    (WORK / f"judgement_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("invalid", "P", "verdict")}, indent=1))
    return 0 if verdict == "PASS" else 1


def main():
    a = sys.argv[1:]
    if a == ["check"]:
        return check()
    if a == ["recovery"]:
        return recovery()
    if a[:1] == ["run"] and len(a) == 2:
        return run(a[1])
    if a[:1] == ["judge"] and len(a) == 2:
        return judge(a[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
