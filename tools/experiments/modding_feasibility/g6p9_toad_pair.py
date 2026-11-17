#!/usr/bin/env python3
"""E-495 (D-262) G6-P9: structural operation composition, two-actor pilot. Two additional intro_10 NIN_m_ToadIntro
(copies of instance 1) built by ONE coordinated construction (`insert-toad-intro-pair`, development-only) into ONE
version-2 transaction. Development-only; private; hidden. Outputs: private/work/e495/.

  g6p9_toad_pair.py check         O1-O10 offline (check.json; runtime transaction cases in negtest_pair/)
  g6p9_toad_pair.py recovery      K1-K5 offline: the session marker over the composed transaction (recovery.json)
  g6p9_toad_pair.py run TAG       hidden runs A, B, C, D (development build)
  g6p9_toad_pair.py judge TAG     P1-P8 (C) and the single-operation control (B)

PHASE A (audit, before the compiler change; recorded in the report): every single-actor builder parses the source
and its four lists, allocates one copy, edits ten original words and appends one pointer-table block; manifests allow
one actor operation per mod and resolve_all one structural transaction per level (STRUCTURAL_CONFLICT). Reusable
from G5-P5's graph composition: one allocator, one count edit per list, one pointer table, canonical order, whole-mod
refusal, one simulator. Actor-specific: the world sibling chain, three level lists + transit's actor count, a
personal type / name / SO record / backup record + matrix copy per copy, the personal index, and the guest-built
16-byte list element at block +0x4A8 (runtime only, zero in the file). Two Toads touch exactly the same ten original
words as one Toad (source next, next's previous, personal last / count / old last, records last / count / old last,
backups last / old last): each is edited once with the pair's value; transit's count + 2.

DESIGN (predicted before the first compile): copy A at S + 12 = 0x74E918 (= insert-toad-intro's copy), copy B at
0x74EDD8 (A + 1,216: the source's 16-byte phase), then A's and B's registration objects (personal element 0x14, name
20, SO record 0x48, backup record 0x18, matrix copy 0x54); tail 2,884 (not 2 x 1,444: one lead pad, B's phase pad,
one end pad); .ptr + 80 entries = 640 (A's 31 block words, B's 31, then A's 9 and B's 9 registration words: 78
own-file, 2 transit = each copy's parent +0x1C); world chain source -> A -> B -> next.

OFFLINE RESULT (check, before any build or modified run): O1-O10 PASS. Plan `level-tx 2 intro_10 g6p9.toad-pair
9a287c36ac38d6fa`; images lvl ff969957... (7,664,720), ptr bab5a96a... (209,708), transit 8addf2c0... (41,508, count
+2); copies 0x74E918 / 0x74EDD8, personal indices 69 / 70, names XAP_ToadIntro_G6P7 / _G6P9; each copy 14 owned / 14
shared / 1 other-file / 2 links, no word into the source or the other copy but the chain; copy A = insert-toad-intro's
copy except +0x14; 80 entries exactly as expected; ten original words; runtime cases dev 15 / 15, prod 2 / 2; 18
compile + 12 builder + 5 independent-simulator refusals; G6-P5 compare, selftest 335 / 335, single-Toad hashes = G6-P8.
First check run: O1 false on a harness defect (it read the tx-file record's role field as the hash); corrected to
compare (role, original hash) per member before the second run; no compiler change between the two runs.
RECOVERY (offline): K1-K5 PASS: one plan with the pair and G5-P1's ordinary waypoint mod arms one marker naming the
plan (one level-tx, three tx-file); after an unfinished session the next plan refuses the WHOLE pair
(STRUCTURAL_RECOVERY, no level-tx / tx-file) and keeps the waypoint mod; explicit clear re-enables it; a controlled
end clears; without the gate the pair is UNSUPPORTED, the waypoint mod active, nothing armed. No session-marker or
resource-open code changed, so no hidden crash-recovery run is added (brief section 12).

RUNTIME PROTOCOL (committed before the development build and before any modified run; thresholds from G6-P8)
Build: g5p1_dev_gate.py apply (unchanged gate: intro_10 version 2, growth bounds 4,096 / 1,024) + build_incremental;
production restored afterwards (revert + rebuild). Runner, reads, timings and Exit Game sequence: G6-P8's run_case,
unchanged (hidden, non-activating, muted, no physical pad, private user root, --test-level intro_10, 150 s, guest-scoped
Exit Game 85 s after intro_10.lvl opened; early 4-ms reads; full reads at 6 s and 80 s incl. the +0x4A8 list from the
source's element; 0.1-s samples). Fresh controls on the same build (G6-P8's g3 controls are from an earlier build, so
memory comparisons would not be matched). X(o) = area base + o - 4.
  A: no plan.  B: the existing insert-toad-intro (mod g6p9.single, real compiler, marker armed, gate on), tracked
  "copy" = 0x74E918.  C: insert-toad-intro-pair (mod g6p9.toad-pair, real compiler, marker armed, gate on), tracked
  copyA 0x74E918 / copyB 0x74EDD8.  D: C's plan compiled the same way, gate variable unset.
  Single-operation control: G6-P8's judge, unchanged (revision 2), with B as its typed run and A / D as its controls
  (I8-PASS required: +1,444 etc. exactly as G6-P8).
  P1 atomic transaction (C): one `M33 mods state=active`; exactly one `G5P1 level-tx active level=intro_10
     mod=g6p9.toad-pair id=<plan id>`; `G6P1 level-tx version=2 members=lvl,ptr,transit`; snapshots 7,664,720 /
     209,708 / 41,508; grow 7661836 -> 7664720, 209068 -> 209708, 41508 -> 41508; served exactly the three; no host
     change; A `M33 mods=off`.
  P2 registration (C, first read): union = A's + exactly X(A), X(B), no duplicate, walks consistent; dynamic world
     ... X(source), X(A), X(B) ...; both alive, model NIN_m_ToadIntro; SO records A + 2, last two = X(A), X(B), each
     of A, B, source once; backup targets A's + 2 with X(A + 0xC4), X(B + 0xC4) once each; personal types 71, last
     XAP_ToadIntro_G6P9; personal index A 69, B 70, source 0x1D. D: A's union / records, 69 types, no copy.
  P3 independent ownership (C, both full reads): for each copy its own Perso / 3dData / StdGame / Brain = X(copy +
     0x80 / 0xAC / 0x2B4 / 0x318), Brain +0 = X(copy + 0x324), Mind +4 = X(copy + 0x338), Intelligence +0x10 / +0x18
     = X(copy + 0x350 / 0x358), Mind +0 = the source's = X(0x580C78), Mind +0xC = 0, Brain +4 = 0xCDCDCDCD; 3dData
     buffer words non-zero, different from each other and from all four originals'; world links source +0x14 = X(A),
     A +0x18 = X(source), A +0x14 = X(B), B +0x18 = X(A); any other live word of the source / A / B blocks pointing
     into another of the three must be that block's guest-list element next (+0x4AC) / prev (+0x4B0) equal to the
     walked list; the guest list: reciprocal, every owner once, one header, ends 0 / 0, length A + 2, both copies'
     elements {X(copy), .., .., the source's header}, C's owners minus the two copies = A's owners, the two copies in
     the two places right after the source (either order; predicted source, A, B: recorded, not judged).
  P4 guest initialization (C): each copy meets oracle (a) and (b): its own Init run (counter 0xFF -> 0, AI runs
     draw + 1, (Init, Init) -> (Jump, Wait) through the shared model's records).
  P5 scheduler behaviour: G6-P8's oracle (a)-(d') (revision 1 / 2) for both copies and the four originals in C and for
     the four in D; both copies' positions = the source's; each copy's StdGame stamp = the source's in >= 95 % of
     samples.
  P6 structural integrity: every run, both reads: walks consistent, no duplicate in the union, no list read error; in C
     both copies alive and once in the union at 80 s; no access-violation / engine-error line; fault codes within
     {406D1388}.
  P7 cleanup: route intro_10 -> menumap in A, B, C, D; loaded C - A = {area 1 length +2,884, free -2,884, largest
     -2,884}, D - A = {}; between levels fix only (20,795,836, 1 / 1) in all; menumap state = A's in B, C, D.
  P8 isolation and safety: D `state=refused reason=level_tx_not_enabled`, nothing served, no grow, no G5P1 / G5P3 /
     G6P1 line; every run M21 / M22 / M23 0, haptics policy line, runner exit 0, no game process left; C's marker armed
     (session, plan SHA-256) and cleared after the controlled end; check / recovery / negtest passed first.
  Invalid (new tag, kept): process / area not found, a tracked actor unreadable at the first read, < 60 s of samples,
     A's originals failing the oracle, the route not taken in A.
  Stop: a guest fault, bad ownership / aliasing, list corruption or a desktop-safety violation.
  Verdict: PASS = P1-P8 and the single-operation control I8-PASS; P1-P8 with the control failing = FAIL (named);
  P2 + P3 with P4, P5 or P7 failing = PARTIAL; otherwise FAIL (named); BLOCKED decided by hand and recorded.
RUN p1 (protocol cd6d896; recorded after the run): PASS on the first run, P1-P8 all true, single-operation control
  I8-PASS. Transaction 9a287c36ac38d6fa active, members 7,664,720 / 209,708 / 41,508; union 66 -> 68, records 122 ->
  124 (A, B last), backups 181 -> 183, personal 71 (last XAP_ToadIntro_G6P9, indices 69 / 70); world source -> A -> B;
  own chains / buffers, shared model, no unexplained cross-block word; guest list 20 -> 22 in the predicted order
  source, A, B; one Init run each (A 11 -> 12, B 6 -> 7), idle 97.9 s, stamps = the source's 896 / 896 for both;
  loaded C - A = +2,884 area / -2,884 free / largest, B - A = +1,444, D - A = {}; fix only 20,795,836 and menumap
  13,274,536 in all four; D refused, nothing served; marker armed and cleared; safety clean.
"""
import hashlib
import json
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
import g5p1_pilot as p1  # noqa: E402
import g6p7_fifth_actor as g7  # noqa: E402
import g6p8_toad as g8  # noqa: E402

PREFIX = "e495"
WORK = ROOT / "private" / "work" / PREFIX
LEVEL = "intro_10"
SIZE, PSIZE, TSIZE = g8.SIZE, g8.PSIZE, g8.TSIZE
N_LVL, N_PTR, N_SLOTS = 2884, 640, 80
SRC, BLK = g8.SRC, g8.BLK
COPY_A, COPY_B = 0x74E918, 0x74EDD8
NAMES = (b"XAP_ToadIntro_G6P7", b"XAP_ToadIntro_G6P9")
PH, BH, RREF, W = 0x1C74, 0x1CEC, 0x1CFC, 0x9B4      # personal / backup headers, records reference, transit world
MOD = "g6p9.toad-pair"
sha = lambda b: hashlib.sha256(b).hexdigest()   # noqa: E731
u32 = g8.u32


def pair_op(**kw):
    o = g8.typed_op(type="insert-toad-intro-pair", count=2)
    o.update(kw)
    return o


def compile_mods(name, mods, session=None, env=LEVEL):
    """The real compiler (import + resolve_all) in e495."""
    g8.WORK = WORK
    return g8.compile_typed(name, mods, session=session, env=env)


# --- the independent simulator (shares no code with the compiler's builder or verifier) -------------------------------

def simulate_pair(lvl, ptr, tl, nl, np_, nt, me):
    """Re-reads the composed files as the loader would (own-file slots resolved; the new .ptr parsed afresh), derives
    every expectation from the ORIGINAL files only, and walks both copies and every list."""
    d = {}
    n0, n, m = u32(ptr, 0), u32(np_, 0), u32(lvl, 0)
    ent = lambda b, i: struct.unpack_from(">iI", b, 4 + 8 * i)   # noqa: E731
    d["ptr_layout"] = 4 + 8 * n + 16 * m == len(np_) and np_[4:4 + 8 * n0] == ptr[4:4 + 8 * n0] \
        and np_[4 + 8 * n:] == ptr[4 + 8 * n0:]
    old = {loc + 4: f for f, loc in (ent(ptr, i) for i in range(n0))}
    added = [(f, loc + 4) for f, loc in (ent(np_, i) for i in range(n0, n))]
    new = dict(old)
    dup = False
    for f, o in added:
        dup = dup or o in new
        new[o] = f
    d["new_entries"], d["new_slots_unique"] = len(added), not dup
    tgt = lambda b, sl, o: u32(b, o) + 4 if sl.get(o) == me and o + 4 <= len(b) else None   # noqa: E731
    size = len(lvl)

    def walk(b, sl, start, step=None):
        out, x = [], start
        while x is not None and x not in out and len(out) < 70000:
            out.append(x)
            x = tgt(b, sl, x + (step or 0))
        return out
    nxt = tgt(lvl, old, SRC + 0x14)
    A = tgt(nl, new, SRC + 0x14)
    B = tgt(nl, new, A + 0x14) if A else None
    d["copies"] = [A, B]
    d["chain"] = bool(A and B and size <= A < B and A % 16 == SRC % 16 == B % 16 and B >= A + BLK
                      and tgt(nl, new, A + 0x18) == SRC and tgt(nl, new, B + 0x18) == A
                      and tgt(nl, new, B + 0x14) == nxt and tgt(nl, new, nxt + 0x18) == B)
    if not d["chain"]:
        return {"pass": False, **d}
    link = {(A, 0x14): B, (A, 0x18): SRC, (B, 0x14): nxt, (B, 0x18): A}
    std_k = tgt(lvl, old, tgt(lvl, old, SRC + 4) + 4) - SRC
    d["kinds"], bad = {}, {}
    for C in (A, B):
        kinds = {}
        for k in range(0, BLK, 4):
            so_, co = SRC + k, C + k
            if so_ not in old:
                same = co not in new and (nl[co:co + 4] == lvl[so_:so_ + 4] or k == std_k + 8)
                kind = "data"
            elif old[so_] != me:
                same, kind = new.get(co) == old[so_] and nl[co:co + 4] == lvl[so_:so_ + 4], "other-file"
            elif k in (0x14, 0x18):
                same, kind = tgt(nl, new, co) == link[(C, k)], "link"
            elif SRC <= tgt(lvl, old, so_) < SRC + BLK:
                same, kind = tgt(nl, new, co) == C + tgt(lvl, old, so_) - SRC, "owned"
            else:
                same, kind = tgt(nl, new, co) == tgt(lvl, old, so_), "shared"
            kinds[kind] = kinds.get(kind, 0) + 1
            if not same:
                bad[f"{C:#x}+{k:#x}"] = kind
        d["kinds"][f"{C:#x}"] = kinds
        mind = tgt(nl, new, tgt(nl, new, tgt(nl, new, C + 4) + 0xC))
        intel = tgt(nl, new, mind + 4)
        d.setdefault("model_shared", []).append(
            tgt(nl, new, mind) == g8.AI_MODEL and tgt(nl, new, intel) == g8.AI_MODEL and C <= mind < C + BLK
            and C <= intel < C + BLK and [tgt(nl, new, intel + 0x10), tgt(nl, new, intel + 0x18)] ==
            [C + g8.INTEL_LOCAL[0], C + g8.INTEL_LOCAL[1]])
        d.setdefault("cross_block", []).append(
            [hex(k) for k in range(0, BLK, 4) if (C + k) in new and (C, k) not in link
             and tgt(nl, new, C + k) is not None
             and any(b != C and b <= tgt(nl, new, C + k) < b + BLK for b in (SRC, A, B))])
        d.setdefault("std_index", []).append(u32(nl, C + std_k + 8))
    d["bad_words"] = bad
    pcount = u32(lvl, PH + 8)
    d["std_index_ok"] = d["std_index"] == [pcount, pcount + 1]
    # the world: from transit's first child (cross-file table), the old walk with A, B after the source
    cross = [struct.unpack_from(">IiIi", ptr, 4 + 8 * n0 + 16 * j) for j in range(m)]
    first = [ob + 4 for oa, fa, ob, fb in cross if fa != me and fb == me and oa + 4 == W + 8]
    ow, nw = walk(lvl, old, first[0], 0x14), walk(nl, new, first[0], 0x14)
    want = ow[:ow.index(SRC) + 1] + [A, B] + ow[ow.index(SRC) + 1:]
    d["world"] = nw == want and u32(nt, W + 0x10) == u32(tl, W + 0x10) + 2 == len(nw) \
        and all(tgt(nl, new, y + 0x18) == x for x, y in zip(nw, nw[1:])) \
        and [o for o in range(0, len(tl), 4) if tl[o:o + 4] != nt[o:o + 4]] == [W + 0x10]
    rh = tgt(lvl, old, RREF)
    orl, nrl = walk(lvl, old, tgt(lvl, old, rh)), walk(nl, new, tgt(nl, new, rh))
    owners = [tgt(nl, new, r + 4) for r in nrl]
    d["records"] = nrl[:-2] == orl and owners[-2:] == [A, B] and u32(nl, rh + 8) == len(nrl) \
        and tgt(nl, new, rh + 4) == nrl[-1] and all(owners.count(x) == 1 for x in (SRC, A, B))
    obl, nbl = walk(lvl, old, tgt(lvl, old, BH)), walk(nl, new, tgt(nl, new, BH))
    bk = []
    for C, ln in zip((A, B), nbl[-2:]):
        r = ln - 4
        bc = tgt(nl, new, r + 0xC)
        bk.append(tgt(nl, new, r + 8) == C + 0xC4 and bc is not None and size <= bc and b"".join(
            nl[bc + q:bc + q + 4][::-1] for q in range(0, 0x54, 4)) == nl[C + 0xC4:C + 0xC4 + 0x54])
    d["backups"] = nbl[:-2] == obl and len(nbl) == len(obl) + 2 and all(bk) and tgt(nl, new, BH + 4) == nbl[-1]
    opl, npl = walk(lvl, old, tgt(lvl, old, PH)), walk(nl, new, tgt(nl, new, PH))
    nm = lambda e: nl[tgt(nl, new, e + 0xC):tgt(nl, new, e + 0xC) + 0x40].split(b"\0")[0]   # noqa: E731
    names = [nm(e) for e in npl]
    d["personal"] = npl[:-2] == opl and names[-2:] == list(NAMES) and len(set(names)) == len(names) \
        and u32(nl, PH + 8) == len(npl) == pcount + 2 and tgt(nl, new, PH + 4) == npl[-1] \
        and all(tgt(nl, new, y + 4) == x for x, y in zip(npl, npl[1:]))
    # original words: exactly the ten list / chain words, derived from the original files
    ten = sorted({SRC + 0x14, nxt + 0x18, PH + 4, PH + 8, opl[-1], rh + 4, rh + 8, orl[-1], BH + 4, obl[-1]})
    changed = [o for o in range(0, size, 4) if nl[o:o + 4] != lvl[o:o + 4]]
    d["original_words"] = changed == ten
    # the expected new relocation entries, in order: A's block words, B's, then A's and B's registration words
    exp = []
    for C in (A, B):
        exp += [(old[SRC + k], C + k) for k in range(0, BLK, 4) if SRC + k in old]
    pp, rp, bp = opl[-1], orl[-1], obl[-1]
    for i in range(2):
        pe, rec, ln = npl[-2 + i], nrl[-2 + i], nbl[-2 + i]
        exp += [(me, pe + 4), (me, pe + 8), (me, pe + 0xC), (me, pp), (me, rec + 4), (me, rp),
                (me, ln - 4 + 8), (me, ln - 4 + 0xC), (me, bp)]
        pp, rp, bp = pe, rec, ln
    d["entries_as_expected"] = added == exp
    d["entries_inside_new_or_tails"] = all(o >= size or o in (opl[-1], orl[-1], obl[-1]) for _, o in added)
    d["padding_zero"] = nl[size:A] == bytes(A - size)
    ok = all(v for k, v in d.items() if isinstance(v, bool)) and not bad and all(d["model_shared"]) \
        and d["cross_block"] == [[], []] and d["new_entries"] == N_SLOTS
    return {"pass": ok, **d}


# --- O1-O10 -----------------------------------------------------------------------------------------------------------

def check():
    WORK.mkdir(parents=True, exist_ok=True)
    O, det = {}, {}
    lvl, ptr, tl = g8.files()
    Lv, ix, key, insts = g7.toad_inputs()
    me = Lv["me"]
    res, text, paths = compile_mods("pair_valid", [(MOD, [pair_op()])])
    m, imgs = g8.plan_images(text)
    nl, np_, nt = imgs["lvl"], imgs["ptr"], imgs["transit"]
    shutil.copyfile(paths["cache"] / rm.PLAN_NAME, WORK / "plan_pair.txt")
    with p1.dev_env(LEVEL):
        ranges, tx = rm.compile_insert_toad_intro_pair(pair_op(), paths)
    info = tx["info"]
    det["info"] = {k: info[k] for k in ("objects", "tail", "slots", "edits", "personal_index", "actors", "records",
                                        "personal_types", "names", "memory")}
    det["hashes"] = {k: sha(b) for k, b in imgs.items()}
    det["sizes"] = {k: len(b) for k, b in imgs.items()}
    det["txs"] = m["txs"]

    # O1 original-source validation
    O["O1_original_sources"] = ([sha(lvl), sha(ptr), sha(tl)] == [g8.LVL_SHA, g8.PTR_SHA, g8.TRANSIT_SHA]
                                and (len(lvl), len(ptr), len(tl)) == (SIZE, PSIZE, TSIZE)
                                and [Path(f["path"]).name for f in m["files"]] ==
                                [f"{LEVEL}.lvl", f"{LEVEL}.ptr", "transit.lvl"]
                                and [t.split(" ")[:2] for f in m["files"] for t in f["tx"]] ==
                                [["lvl", g8.LVL_SHA], ["ptr", g8.PTR_SHA], ["transit", g8.TRANSIT_SHA]])
    # O9 independent simulation (computed first: O2-O5 read its walks)
    sim = simulate_pair(lvl, ptr, tl, nl, np_, nt, me)
    det["simulation"] = sim
    O["O9_independent_simulation"] = sim["pass"]
    # O2 actor identity
    O["O2_actor_identity"] = (res["active"] == [MOD] and sim["copies"] == [COPY_A, COPY_B]
                              and info["objects"]["copy"] == [COPY_A, COPY_B] and sim["std_index_ok"]
                              and info["personal_index"] == [69, 70] and info["names"] == [n.decode() for n in NAMES]
                              and info["actors"] == u32(tl, W + 0x10) + 2 and sim["records"] and sim["personal"])
    # O3 ownership: each copy 14 owned / 14 shared / 1 other-file / 2 links, owned into its own block, the model
    # shared, Intelligence locals own, no word into the source or the other copy except the chain links; copy A =
    # the single operation's copy except its next link
    res1, text1, _ = compile_mods("single_ref", [("g6p9.single", [g8.typed_op()])])
    _, imgs1 = g8.plan_images(text1)
    diffA = [k for k in range(0, BLK, 4) if nl[COPY_A + k:COPY_A + k + 4] != imgs1["lvl"][COPY_A + k:COPY_A + k + 4]]
    diffAB = [k for k in range(0, BLK, 4) if nl[COPY_A + k:COPY_A + k + 4] != nl[COPY_B + k:COPY_B + k + 4]]
    det["O3"] = {"copyA_vs_single_words": [hex(k) for k in diffA], "copyA_vs_copyB_words": len(diffAB),
                 "kinds": sim["kinds"]}
    want_k = {"owned": 14, "shared": 14, "other-file": 1, "link": 2}
    O["O3_ownership"] = (all({k: v for k, v in kd.items() if k != "data"} == want_k for kd in sim["kinds"].values())
                         and not sim["bad_words"] and all(sim["model_shared"]) and sim["cross_block"] == [[], []]
                         and diffA == [0x14] and {sha(imgs1[k]) for k in ("lvl",)} == {g8.PROTO["lvl"]})
    # O4 list topology
    O["O4_list_topology"] = sim["world"] and sim["records"] and sim["backups"] and sim["personal"]
    # O5 relocations
    n0 = u32(ptr, 0)
    slots_new = [struct.unpack_from(">iI", np_, 4 + 8 * i) for i in range(n0, u32(np_, 0))]
    det["O5"] = {"entries": len(slots_new), "own_file": sum(f == me for f, _ in slots_new),
                 "other_file": sum(f != me for f, _ in slots_new)}
    O["O5_relocations"] = (sim["entries_as_expected"] and sim["new_slots_unique"] and sim["entries_inside_new_or_tails"]
                           and sim["ptr_layout"] and len(slots_new) == N_SLOTS and info["slots"] == N_SLOTS
                           and sim["original_words"] and len(info["edits"]) == 10
                           and det["sizes"] == {"lvl": SIZE + N_LVL, "ptr": PSIZE + N_PTR, "transit": TSIZE})
    # O6 atomicity: one transaction over the three members; the runtime cases on this plan
    tx_files = [x for f in m["files"] for x in f["tx"]]
    members = []
    for f in m["files"]:
        role = {f"{LEVEL}.lvl": "lvl", f"{LEVEL}.ptr": "ptr", "transit.lvl": "transit"}[Path(f["path"]).name]
        orig = Path(f["path"]).read_bytes()
        members.append((role, Path(f["path"]).name, len(orig), sha(orig), len(imgs[role]), sha(imgs[role])))
    want_id = rm.tx_id(LEVEL, MOD, sorted(members), 2)
    det["tx_id"] = want_id
    g8.WORK = WORK
    neg_rt = g8.negtest(text, "pair", WORK / "negtest_pair") == 0
    O["O6_atomicity"] = (m["txs"] == [f"level-tx 2 {LEVEL} {MOD} {want_id}"] and len(tx_files) == 3
                         and sum(1 for f in m["files"] if f.get("grow")) == 2 and neg_rt)
    # O7 negatives
    lum = {"type": "insert-passive-lum", "level": LEVEL, "model": rm.LUM10, "instance": 6, "lvl_sha256": sha(lvl),
           "ptr_sha256": sha(ptr), "transit_sha256": sha(tl), "position": [17.87, -101.22, -44.18]}

    def outcome(name, mods, env=LEVEL):
        r_, t_, _ = compile_mods(f"neg_{name}", mods, env=env)
        refused_ = "import_refused" in r_ or (not r_["active"] and all(x.get("code") for x in r_["mods"]))
        return {"refused": refused_, "code": r_["import_refused"][1] if "import_refused" in r_ else
                {x["id"]: x.get("code") for x in r_["mods"]}, "plan": bool(t_ and "level-tx" in t_)}
    neg = {
        "count 1 (use insert-toad-intro)": outcome("c1", [(MOD, [pair_op(count=1)])]),
        "count 3": outcome("c3", [(MOD, [pair_op(count=3)])]),
        "count missing": outcome("cmiss", [(MOD, [{k: v for k, v in pair_op().items() if k != "count"}])]),
        "two pair operations in one mod": outcome("twopairs", [(MOD, [pair_op(), pair_op()])]),
        "pair + single Toad in one mod": outcome("withsingle", [(MOD, [pair_op(), g8.typed_op()])]),
        "pair + lum in one mod": outcome("withlum", [(MOD, [pair_op(), lum])]),
        "pair mod + single Toad mod (one level)": outcome("conflict", [(MOD, [pair_op()]),
                                                                      ("g6p9.single", [g8.typed_op()])]),
        "wrong lvl hash": outcome("lvlsha", [(MOD, [pair_op(lvl_sha256="0" * 64)])]),
        "wrong ptr hash": outcome("ptrsha", [(MOD, [pair_op(ptr_sha256="1" * 64)])]),
        "wrong transit hash": outcome("tlsha", [(MOD, [pair_op(transit_sha256="2" * 64)])]),
        "unsupported level": outcome("lvl20", [(MOD, [pair_op(level="intro_20")])]),
        "source instance 0": outcome("i0", [(MOD, [pair_op(instance=0)])]),
        "source instance 2": outcome("i2", [(MOD, [pair_op(instance=2)])]),
        "other model": outcome("model", [(MOD, [pair_op(model=rm.FROG10)])]),
        "other placement": outcome("pl", [(MOD, [pair_op(placement="beside_source")])]),
        "raw address key": outcome("raw", [(MOD, [dict(pair_op(), copy_b=COPY_B)])]),
        "gate unset": outcome("nogate", [(MOD, [pair_op()])], env=None),
        "gate for another level": outcome("gate20", [(MOD, [pair_op()])], env="intro_20"),
    }
    det["O7_conflict_codes"] = neg["pair mod + single Toad mod (one level)"]["code"]
    # builder / simulator negatives on the composed structure
    spec = rm.TOAD_PAIR_ALLOW[LEVEL]
    pos = struct.unpack_from(">3f", lvl, SRC + 0xC4 + 0x34)
    peers = [i["so"] for n_, i in enumerate(insts) if n_ != 1]

    def build(lvl_=lvl, ptr_=ptr, tl_=tl, spec_=spec):
        return rm.build_toad_pair(lvl_, ptr_, tl_, me, spec_, peers, pos, "neg")
    new_b, nptr_b, ntl_b, edits_b, info_b = build()
    s = rm._lum_source(lvl, ptr, tl, me, spec, peers, "neg")
    L, _ = rm.toad_pair_layout(SIZE, SRC, BLK, [20, 20], 1, lambda w: None)
    new_slots = [(f, o + 4) for f, o in slots_new]

    def verify(nl_=new_b, np2=nptr_b, nt_=ntl_b, L_=L):
        return rm.verify_toad_pair(lvl, ptr, tl, nl_, np2, nt_, me, spec, s, L_, new_slots, edits_b, pos, "neg")

    def mut(img, o, v):
        b = bytearray(img)
        struct.pack_into(">I", b, o, v)
        return bytes(b)
    recB = L["record"][1]
    dup_identity = mut(new_b, recB + 4, COPY_A - 4)                 # copy B's SO record names copy A
    alias = mut(new_b, COPY_B + g8.CHAIN["intel"] + 0x10, COPY_A + g8.INTEL_LOCAL[0] - 4)   # B's local -> A's
    half = mut(new_b, PH + 8, u32(lvl, PH + 8) + 1)                 # personal count + 1 only (incomplete)
    drop = bytearray(nptr_b)                                         # B's last block entry removed (incomplete)
    nB = u32(ptr, 0) + 62
    drop = bytes(struct.pack(">I", u32(nptr_b, 0) - 1) + nptr_b[4:4 + 8 * (nB - 1)] + nptr_b[4 + 8 * nB:])
    dslot = bytearray(nptr_b)                                        # a new entry names another new entry's slot
    dslot[4 + 8 * (u32(ptr, 0) + 79):4 + 8 * (u32(ptr, 0) + 80)] = dslot[4 + 8 * (u32(ptr, 0) + 78):4 + 8 * (u32(ptr, 0) + 79)]
    ofile = bytearray(nptr_b)                                        # a new own-file entry relabelled as other-file
    struct.pack_into(">i", ofile, 4 + 8 * (u32(ptr, 0) + 70), 0)
    overlap = {k: list(v) for k, v in L.items()}
    overlap["copy"] = [COPY_A, COPY_A + 0x10]                        # bad allocation: B inside A
    pc = mut(lvl, PH + 8, u32(lvl, PH + 8) + 1)
    sp_dup = dict(spec, new_names=(NAMES[0], NAMES[0]))
    sp_old = dict(spec, new_names=(NAMES[0], b"XAP_ToadIntro_04"))
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
        "duplicate identity (B's SO record names A)": ref(lambda: verify(nl_=dup_identity)),
        "aliasing (B's Intelligence local into A's block)": ref(lambda: verify(nl_=alias)),
        "incomplete composition (personal count + 1)": ref(lambda: verify(nl_=half)),
        "incomplete relocations (B's last block entry dropped)": ref(lambda: verify(np2=drop)),
        "malformed relocation (duplicate new slot)": ref(lambda: verify(np2=bytes(dslot))),
        "malformed relocation (own-file entry as other-file)": ref(lambda: verify(np2=bytes(ofile))),
        "bad allocation (B overlapping A)": ref(lambda: verify(L_=overlap)),
        "duplicate personal-type names": ref(lambda: build(spec_=sp_dup)),
        "name of an existing personal type": ref(lambda: build(spec_=sp_old)),
        "damaged input (personal count)": ref(lambda: build(lvl_=pc)),
        "conflicting original-word edits (one word twice)": edit_refused(conflicting),
        "original word not the expected value": edit_refused(wrong_old),
    }
    sneg = {k: not simulate_pair(lvl, ptr, tl, nl_, np2, ntl_b, me)["pass"] for k, nl_, np2 in (
        ("independent: duplicate identity", dup_identity, nptr_b), ("independent: aliasing", alias, nptr_b),
        ("independent: incomplete composition", half, nptr_b), ("independent: dropped entry", new_b, drop),
        ("independent: duplicate slot", new_b, bytes(dslot)))}
    det["O7"] = {"compile": neg, "builder": bneg, "independent": sneg}
    O["O7_negatives"] = (all(v["refused"] and not v["plan"] for v in neg.values()) and all(bneg.values())
                         and all(sneg.values())
                         and set(det["O7_conflict_codes"].values()) == {"STRUCTURAL_CONFLICT"}
                         and (new_b, nptr_b, ntl_b) == (nl, np_, nt))
    # O8 backward compatibility
    eq = subprocess.run([sys.executable, str(HERE / "g6p5_equivalence.py"), "compare"], capture_output=True, text=True)
    st = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "selftest"], capture_output=True, text=True)
    det["O8"] = {"g6p5_compare": eq.stdout.strip().splitlines()[-1:], "selftest": st.stdout.strip().splitlines()[-1:],
                 "single_hashes": {k: sha(b) for k, b in imgs1.items()}}
    O["O8_backward_compatibility"] = (eq.returncode == 0 and st.returncode == 0
                                      and {k: sha(b) for k, b in imgs1.items()} == g8.PROTO
                                      and res1["active"] == ["g6p9.single"])
    # O10 determinism
    res2, text2, _ = compile_mods("pair_again", [(MOD, [pair_op()])])
    strip = lambda t: "\n".join(x for x in t.splitlines() if not x.startswith(("# written by", "range ")))  # noqa
    rng = lambda mm: [[(r.split(" ")[:2], Path(r.split(" ", 5)[5]).read_bytes()) for r in f["range"]]   # noqa: E731
                      for f in mm["files"]]
    m2, imgs2 = g8.plan_images(text2)
    b2 = build()
    O["O10_determinism"] = (strip(text) == strip(text2) and imgs2 == imgs and rng(m) == rng(m2) and m2["txs"] == m["txs"]
                            and b2[:3] == (new_b, nptr_b, ntl_b) and b2[3] == edits_b)
    out = {"pass": all(O.values()), "O": O, "details": det}
    (WORK / "check.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(O, indent=1))
    print(json.dumps({k: det[k] for k in ("hashes", "sizes", "txs", "tx_id", "O3", "O5")}, indent=1, default=str))
    print("CHECK_G6P9", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


def cli(paths, *args):
    """The mod tool as play.ps1 invokes it (JSON on stdout)."""
    import os
    r = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), *args, "--json", "--mods-root", str(paths["mods"]),
                        "--cache", str(paths["cache"]), "--game-dir", str(paths["game"])], capture_output=True,
                       text=True, env=dict(os.environ))
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"result": "error", "stderr": r.stderr[-400:]}


def recovery():
    """K1-K5: the session marker covers the whole composed transaction (the existing marker code, unchanged); an
    ordinary mod (G5-P1's waypoint-position on intro_10) stays available whenever the pair is refused."""
    p1.WORK = WORK
    K = {}

    def setup(name):
        paths = p1.fresh(name)
        with p1.dev_env(LEVEL):
            p1.install(paths, MOD, [pair_op()])
            p1.install(paths, "w.13", [p1.waypoint13()])
        return paths

    def plan(paths, session, env=LEVEL):
        with p1.dev_env(env):
            return cli(paths, "plan", "--session", session)

    def txt(r):
        return Path(r["plan"]).read_text(encoding="utf-8") if r.get("plan") else ""
    pa = setup("k1")
    r1 = plan(pa, "sess-k1")
    st, d = rm.read_structural_marker(pa)
    psha = sha(Path(r1["plan"]).read_bytes()) if r1.get("plan") else None
    lt = [ln for ln in txt(r1).splitlines() if ln.startswith("level-tx")]
    K["K1_marker_armed_for_the_whole_pair"] = (sorted(r1.get("active", [])) == sorted([MOD, "w.13"]) and st == "armed"
                                               and d["session"] == "sess-k1" and d["plan_sha256"] == psha
                                               and len(lt) == 1 and lt[0].startswith(f"level-tx 2 {LEVEL} {MOD} ")
                                               and txt(r1).count("tx-file") == 3)
    before = rm.structural_marker_path(pa).read_bytes()
    e = cli(pa, "structural-end", "--session", "sess-k1", "--plan-sha", psha, "--controlled", "no")
    r2 = plan(pa, "sess-k1-next")
    codes = {m["id"]: m.get("code") for m in r2.get("mods", [])}
    K["K2_unfinished_session_refuses_whole_pair_ordinary_kept"] = (
        e.get("cleared") is False and codes.get(MOD) == "STRUCTURAL_RECOVERY" and r2.get("active") == ["w.13"]
        and "level-tx" not in txt(r2) and "tx-file" not in txt(r2) and r2.get("structural_recovery") == "armed"
        and rm.structural_marker_path(pa).read_bytes() == before)
    c = cli(pa, "structural-recovery", "clear")
    r3 = plan(pa, "sess-k1-reauth")
    K["K3_explicit_reauthorization"] = (c.get("cleared") is True and sorted(r3.get("active", [])) ==
                                        sorted([MOD, "w.13"]) and rm.read_structural_marker(pa)[1]["session"] ==
                                        "sess-k1-reauth")
    s3 = sha(Path(r3["plan"]).read_bytes())
    e4 = cli(pa, "structural-end", "--session", "sess-k1-reauth", "--plan-sha", s3, "--controlled", "yes")
    K["K4_controlled_end_clears"] = e4.get("cleared") is True and rm.read_structural_marker(pa)[0] == "none"
    pp = setup("k5")
    r5 = plan(pp, "sess-k5", env=None)
    codes5 = {m["id"]: m.get("code") for m in r5.get("mods", [])}
    K["K5_without_gate_pair_refused_ordinary_kept_nothing_armed"] = (
        codes5.get(MOD) == "UNSUPPORTED" and r5.get("active") == ["w.13"] and "level-tx" not in txt(r5)
        and not rm.structural_marker_path(pp).exists())
    out = {"pass": all(K.values()), "K": K}
    (WORK / "recovery.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(K, indent=1))
    print("RECOVERY_G6P9", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


# --- the runtime (development build) ----------------------------------------------------------------------------------

CASES = ("A", "B", "C", "D")
MOD_S = "g6p9.single"
GROWN = {"B": (1444, 320), "C": (N_LVL, N_PTR)}


def compile_case(name, case, session=None):
    mods = [(MOD_S, [g8.typed_op()])] if case == "B" else [(MOD, [pair_op()])]
    res, text, paths = compile_mods(name, mods, session=session)
    if res["active"] != [mods[0][0]] or text is None:
        raise SystemExit(f"compiler refused the run's mod: {res.get('mods') or res}")
    return paths["cache"] / rm.PLAN_NAME, paths


@__import__("contextlib").contextmanager
def harness(extra=None):
    """G6-P8's hidden runner and reads, unchanged, writing to e495; `extra` adds tracked actors (file SuperObjects)."""
    saved = (g8.WORK, g8.PREFIX, g8.TOADS)
    g8.WORK, g8.PREFIX = WORK, PREFIX
    if extra:
        g8.TOADS = dict(g8.TOADS, **extra)
    try:
        yield
    finally:
        g8.WORK, g8.PREFIX, g8.TOADS = saved


def run(tag, cases=CASES):
    if g8.gate_status() != "patched":
        raise SystemExit("the development gate is not applied")
    for f in ("check.json", "recovery.json", "negtest_pair/summary.json"):
        if not json.loads((WORK / f).read_text()).get("pass"):
            raise SystemExit(f"{f} did not pass")
    for case in cases:
        run_ = f"{PREFIX}_{tag}_{case}"
        if case == "A":
            with harness():
                row = g8.run_case(tag, case)
        elif case == "B":
            plan_, paths = compile_case(f"run_{tag}_B", "B", session=run_)
            with harness():
                row = g8.run_case(tag, case, plan=plan_, env_level=LEVEL, session_paths=paths, copy=True)
        elif case == "C":
            plan_, paths = compile_case(f"run_{tag}_C", "C", session=run_)
            with harness({"copyA": COPY_A, "copyB": COPY_B}):
                row = g8.run_case(tag, case, plan=plan_, env_level=LEVEL, session_paths=paths)
        else:
            plan_, paths = compile_case(f"run_{tag}_D", "D")
            with harness():
                row = g8.run_case(tag, case, plan=plan_, env_level=None)
        print(case, json.dumps(row, default=str)[:400], flush=True)
    return 0


def judge(tag):
    """P1-P8 for C (A control, D gate-off) and the single-operation control B (G6-P8's revision-2 criteria, A and D
    as its controls)."""
    with harness():
        out = {c: g8.load_case(tag, c) for c in CASES}
    A, B, C, D = (out[c] for c in CASES)
    X = lambda o: C["live"]["first"]["ab"] + o - 4   # noqa: E731
    det, P, invalid = {}, {}, []
    for c, r in out.items():
        lf = r["live"].get("first")
        if r.get("error") or not lf or any("error" in a for a in lf["actors"].values()):
            invalid.append(f"{c}:read")
        if not r["samples"] or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60:
            invalid.append(f"{c}:samples")
    opens = {c: [o.rsplit("\\", 1)[-1].lower() for o in __import__("re").findall(
        r"vfs_open path=(\S+?\.lvl) result=00000000", r["log"])] for c, r in out.items()}
    route_ok = {c: f"{LEVEL}.lvl" in o and "menumap.lvl" in o[o.index(f"{LEVEL}.lvl"):]
                and bool(out[c].get("level_change_t")) for c, o in opens.items()}
    det["route"] = {c: [opens[c], out[c].get("level_change_t")] for c in out}
    if not invalid:
        oa = {k: g8.behaviour_oracle(A, k) for k in g8.TOADS}
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
    import re
    # the single-operation control: G6-P8's judge, unchanged, with B as its typed run and A / D as its controls
    tdir = WORK / tag / "T"
    tdir.mkdir(exist_ok=True)
    shutil.copyfile(WORK / tag / "B" / "plan_copy.txt", tdir / "plan_copy.txt")
    real_load = g8.load_case
    with harness():
        g8.load_case = lambda t, c: real_load(t, {"T": "B", "C": "D"}.get(c, c))
        try:
            rc_single = g8.judge(tag, tag)
        finally:
            g8.load_case = real_load
    single = json.loads((WORK / f"judgement_{tag}.json").read_text())
    (WORK / f"judgement_{tag}.json").replace(WORK / f"judgement_{tag}_single.json")
    det["single_control"] = {"verdict": single["verdict"], "P": single["P"]}
    log = C["log"]
    # P1 atomic transaction
    ptx = p1.parse_plan((WORK / tag / "C" / "plan_copy.txt").read_text(encoding="utf-8"))["txs"]
    want = [tuple(ptx[0].split(" ")[2:5])]
    t = [tuple(x) for x in re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log)]
    snaps = sorted((f, b) for f, _, b, _ in re.findall(
        r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", log))
    grow = sorted(set(re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)))
    served = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
    P["P1_atomic_transaction"] = (
        log.count("M33 mods state=active") == 1 and t == want and want[0][1] == MOD
        and log.count("G6P1 level-tx version=2 members=lvl,ptr,transit") >= 1
        and snaps == sorted([(f"{LEVEL}.lvl", str(SIZE + N_LVL)), (f"{LEVEL}.ptr", str(PSIZE + N_PTR)),
                             ("transit.lvl", str(TSIZE))])
        and grow == sorted([(f"{LEVEL}.lvl", str(SIZE), str(SIZE + N_LVL)), (f"{LEVEL}.ptr", str(PSIZE),
                                                                             str(PSIZE + N_PTR)),
                            ("transit.lvl", str(TSIZE), str(TSIZE))])
        and served == sorted([f"{LEVEL}.lvl", f"{LEVEL}.ptr", "transit.lvl"])
        and "G5P3 tx host_changed" not in log and "M33 mods=off" in A["log"])
    det["P1"] = {"tx": t, "want": want, "snaps": snaps, "grow": grow, "served": served}

    def union(r, which="first"):
        ls = r["live"][which]["lists"]
        return ls["dw"]["walk"] + ls["inactive"]["walk"]
    cps = [X(COPY_A), X(COPY_B)]
    # P2 registration
    ls, la = C["live"]["first"]["lists"], A["live"]["first"]["lists"]
    fa = C["live"]["first"]["actors"]
    dw, u, ua, bt = ls["dw"]["walk"], union(C), union(A), ls["bak_targets"]
    i = dw.index(X(SRC)) if X(SRC) in dw else -9
    p2c = ("error" not in ls and ls["dw"]["prev_ok"] and ls["inactive"]["prev_ok"] and len(u) == len(set(u))
           and sorted(u) == sorted(ua + cps) and dw[i + 1:i + 3] == cps
           and all(fa[k].get("alive") and fa[k].get("model") == "NIN_m_ToadIntro" for k in ("copyA", "copyB"))
           and ls["rec"]["count"] == la["rec"]["count"] + 2 and ls["rec"]["owners"][-2:] == cps
           and all(ls["rec"]["owners"].count(x) == 1 for x in cps + [X(SRC)])
           and len(bt) == len(la["bak_targets"]) + 2 and all(bt.count(x + 0xC4) == 1 for x in cps)
           and ls["personal"] == {"count": 71, "last_name": NAMES[1].decode()}
           and [fa["copyA"].get("std_personal"), fa["copyB"].get("std_personal"), fa["t1"].get("std_personal")]
           == [69, 70, 0x1D])
    lsd = D["live"]["first"]["lists"]
    p2d = (sorted(union(D)) == sorted(ua) and lsd["personal"]["count"] == 69 and lsd["rec"]["count"] ==
           la["rec"]["count"] and not set(cps) & set(union(D)))
    P["P2_registration"] = bool(p2c and p2d)
    det["P2"] = {c: {"union": len(union(r)), "rec": r["live"]["first"]["lists"].get("rec", {}).get("count"),
                     "bak": len(r["live"]["first"]["lists"].get("bak_targets", [])),
                     "personal": r["live"]["first"]["lists"].get("personal")} for c, r in out.items()}
    det["P2"]["C_dw_after_source"] = [hex(x) for x in dw[i:i + 4]]

    # P3 independent ownership, at both reads
    def owners(r, which):
        return [e["owner"] for e in r["live"][which]["elist"]["chain"]]

    def p3(which):
        lv = C["live"].get(which)
        if not lv:
            return False, {"missing": which}
        acts = lv["actors"]
        sr = acts["t1"]
        d, ok = {}, True
        others = [acts[k].get("buffer") for k in g8.TOADS]
        blocks = {"t1": X(SRC), "copyA": cps[0], "copyB": cps[1]}
        el = lv.get("elist", {})
        ch = el.get("chain") or []
        at = {e["at"]: e for e in ch}
        # every live word of a block that points into another of the three blocks must be a world link or a guest
        # list link consistent with the walked lists
        world_ok = {("t1", 0x14): cps[0], ("copyA", 0x18): X(SRC), ("copyA", 0x14): cps[1],
                    ("copyB", 0x18): cps[0]}
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
        for lab, C0 in (("copyA", COPY_A), ("copyB", COPY_B)):
            cp = acts[lab]
            mind, smind = cp.get("mind") or [None] * 4, sr.get("mind") or [None] * 4
            iw = cp.get("intel_words") or [None] * 8
            c = {"chain_own": {k: cp.get(k) for k in ("perso", "3ddata", "stdgame", "brain")} ==
                 {k: X(C0 + g8.CHAIN[k]) for k in ("perso", "3ddata", "stdgame", "brain")},
                 "brain0_mind": (cp.get("brain_words") or [None])[0] == X(C0 + g8.CHAIN["mind"]),
                 "mind1_intel": mind[1] == X(C0 + g8.CHAIN["intel"]),
                 "model_shared": mind[0] == smind[0] == X(g8.AI_MODEL), "no_dsgmem": mind[3] == 0 == smind[3],
                 "intel_local_own": [iw[4], iw[6]] == [X(C0 + g8.INTEL_LOCAL[0]), X(C0 + g8.INTEL_LOCAL[1])],
                 "brain4": (cp.get("brain_words") or [0, 0])[1] == 0xCDCDCDCD == (sr.get("brain_words") or [0, 0])[1],
                 "buffer_nonzero_not_original": bool(cp.get("buffer")) and cp.get("buffer") not in others}
            bufs.append(cp.get("buffer"))
            d[lab] = c
            ok = ok and all(c.values())
        d["buffers_distinct"] = bufs[0] != bufs[1]
        d["source_personal"] = sr.get("std_personal") == 0x1D
        # the guest's list: reciprocal, every owner once, one header, ends 0 / 0; C's owners = A's with the two copies
        # occupying the two places right after the source (either order; predicted source, A, B)
        recip = all(at[e["next"]]["prev"] == e["at"] for e in ch if e["next"] in at) and \
            all(at[e["prev"]]["next"] == e["at"] for e in ch if e["prev"] in at)
        own = [e["owner"] for e in ch]
        oa = owners(A, which)
        j = own.index(X(SRC)) if X(SRC) in own else -9
        se = at.get(X(SRC + g8.ELEM))
        els = [at.get(c_ + g8.ELEM) for c_ in cps]
        d["elist"] = {"len": len(ch), "len_A": len(oa), "reciprocal": recip, "owners_unique": len(own) == len(set(own)),
                      "one_header": len({e["header"] for e in ch}) == 1, "ends": el.get("ends"),
                      "order_after_source": [hex(x) for x in own[j:j + 3]] if j >= 0 else None,
                      "predicted_order": own[j:j + 3] == [X(SRC)] + cps}
        eok = bool(ch and "error" not in el and recip and d["elist"]["owners_unique"] and d["elist"]["one_header"]
                   and el.get("ends") == [0, 0] and len(ch) == len(oa) + 2 and se is not None
                   and all(e_ is not None and e_["owner"] == c_ and e_["header"] == se["header"]
                           for e_, c_ in zip(els, cps))
                   and [x for x in own if x not in cps] == oa and sorted(own[j + 1:j + 3]) == sorted(cps))
        d["elist"]["ok"] = eok
        return bool(ok and d["buffers_distinct"] and d["source_personal"] and eok), d
    p3f, d3f = p3("first")
    p3e, d3e = p3("end")
    P["P3_independent_ownership"] = p3f and p3e
    det["P3"] = {"first": d3f, "end": d3e}
    # P4 / P5 guest initialization and behaviour (G6-P8's oracle)
    oc = {k: g8.behaviour_oracle(C, k) for k in list(g8.TOADS) + ["copyA", "copyB"]}
    od = {k: g8.behaviour_oracle(D, k) for k in g8.TOADS}
    det["P4_P5"] = {"C": {k: v[1] for k, v in oc.items()}, "D": {k: v[1] for k, v in od.items()}}
    P["P4_initialization"] = all(oc[k][1]["init_ok"] and oc[k][1]["one_run"] and oc[k][1]["pre_run_samples"] > 0
                                 for k in ("copyA", "copyB"))
    stamps = {}
    for k in ("copyA", "copyB"):
        both = [(x["a"][k]["stamp"], x["a"]["t1"]["stamp"]) for x in C["samples"] if k in x["a"] and "t1" in x["a"]]
        stamps[k] = [sum(1 for a_, b_ in both if a_ == b_), len(both)]
    det["P5_stamp_equal_source"] = stamps
    srcpos = fa["t1"]["position"]
    P["P5_scheduler_behaviour"] = (all(v[0] for v in oc.values()) and all(v[0] for v in od.values())
                                   and all(fa[k]["position"] == srcpos for k in ("copyA", "copyB"))
                                   and all(n_ and s_ >= 0.95 * n_ for s_, n_ in stamps.values()))

    # P6 structural integrity
    def p6(r, grown):
        ok = True
        for which in ("first", "end"):
            ls_ = r["live"].get(which, {}).get("lists", {})
            ok = ok and "error" not in ls_ and ls_.get("dw", {}).get("prev_ok") and ls_.get("inactive", {}).get("prev_ok")
            u_ = union(r, which) if ls_ else []
            ok = ok and len(u_) == len(set(u_))
        if grown:
            ok = ok and all(union(r, "end").count(x) == 1 for x in cps) and all(
                r["live"]["end"]["actors"][k].get("alive") for k in ("copyA", "copyB"))
        return bool(ok) and r["safety"]["fault_line"] is False and set(r["safety"]["fault_codes"]) <= {"406D1388"}
    P["P6_structural_integrity"] = all(p6(out[c], c == "C") for c in out)

    # P7 cleanup
    def brief(x):
        return None if not x else {"free": x["free_bytes"], "largest": x["largest_free"],
                                   "alloc": x["allocated_chunks"], "free_chunks": x["free_chunks"],
                                   "areas": {k: (v["base"], v["length"]) for k, v in x["areas"].items()}}

    def phases(r):
        st = [x for x in r["states"] if "invalid" not in x and "areas" in x]
        lvl_ = next((x for x in st if set(x["areas"]) == {"0", "1", "3"}), None)
        k = st.index(lvl_) if lvl_ else None
        after = st[k + 1:] if k is not None else []
        fix = next((x for x in after if set(x["areas"]) == {"0"}), None)
        menu = next((x for x in after if set(x["areas"]) == {"0", "1", "2"}), None)
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
        dl = {c: diff(ph[c][0], ph["A"][0]) for c in "BCD"}
        det["P7_loaded_diff"] = dl
        fix_ok = all(ph[c][1] and ph[c][1]["free"] == 20795836 and ph[c][1]["alloc"] == 1
                     and ph[c][1]["free_chunks"] == 1 for c in out)
        menu_ok = all(ph[c][2] and ph[c][2] == ph["A"][2] for c in "BCD")
        P["P7_cleanup"] = (all(route_ok.values()) and dl["C"] == {"area1_length": N_LVL, "free": -N_LVL,
                                                                  "largest": -N_LVL}
                           and dl["D"] == {} and fix_ok and menu_ok)
    except Exception as x:
        det["P7_error"] = repr(x)
        P["P7_cleanup"] = False
    # P8 production isolation and desktop safety
    marks = (C["marker_before_start"][0] == "armed" and C["marker_before_start"][1]["session"] == C["run"]
             and C["marker_before_start"][1]["plan_sha256"] == C["plan_sha256"] and C["controlled"] is True
             and C.get("session_end", {}).get("cleared") is True and C.get("marker_after") == "none")
    d_ok = ("state=refused reason=level_tx_not_enabled" in D["log"] and "M33 mods served" not in D["log"]
            and "M36 grow" not in D["log"] and not re.search(r"G5P1|G5P3|G6P1", D["log"]))
    P["P8_isolation_safety"] = all(r["safe"] for r in out.values()) and marks and d_ok
    det["P8"] = {"marks": marks, "D_refused": d_ok, "safety": {c: r["safety"] for c, r in out.items()}}
    single_ok = single["verdict"] == "I8-PASS" and rc_single == 0
    if all(P.values()) and single_ok:
        verdict = "PASS"
    elif all(P.values()):
        verdict = "FAIL (single-operation control)"
    elif P["P2_registration"] and P["P3_independent_ownership"] and not (
            P["P4_initialization"] and P["P5_scheduler_behaviour"] and P["P7_cleanup"]):
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"
    res = {"invalid": invalid, "P": P, "single_control": single["verdict"], "verdict": verdict, "details": det}
    (WORK / f"judgement_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("invalid", "P", "single_control", "verdict")}, indent=1))
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
