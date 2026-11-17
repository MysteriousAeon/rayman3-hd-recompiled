#!/usr/bin/env python3
"""E-496 (D-263) G6-P10: G6-P9's development-only two-Toad composition (`insert-toad-intro-pair`, mod g6p9.toad-pair,
`level-tx 2 intro_10 g6p9.toad-pair 9a287c36ac38d6fa`) through G5-P3's same-process Pause -> Load reload and G5-P4b's
ownership-checked forced termination and recovery. Development-only; hidden; disposable private profiles.

usage:
  g6p10_pair_lifecycle.py check            offline O1-O8 (no game)
  g6p10_pair_lifecycle.py reload TAG       phase F: hidden runs ra (pair) and rb (no plan) on G5-P3's route
  g6p10_pair_lifecycle.py recover TAG      phase G: G5-P4b's phases A / C / D, then reactivation phase E
  g6p10_pair_lifecycle.py judge-reload TAG / judge-recover TAG
Outputs: private/work/e496/.

REUSED: g5p3_reentry.run_case (route, entries, block-8 snapshots, plan / marker / controlled end) and g5p4b_recovery
  (launcher functions, ownership-checked kill, recovery, clear) through their default-None hooks OBSERVE / SAMPLER /
  KILL_READY and the new EARLY hook (added for this milestone, default None: unchanged behaviour); G6-P8's actor
  readers (toad_state, element_list) and G6-P3's list reads; G6-P9's compiler binding, offline check and K1-K5.
OBSERVATION (read-only, this file): EARLY at each intro_10 area appearance, before the discovery probe: every 4 ms the
  engine timer and, per tracked actor, 3dData +342 / +343 / +344 (P, counter, AI runs) and Intelligence +8 / +0xC at
  fixed in-block live addresses, until every tracked actor has shown counter 0xFF then 0 (its first scheduler visit)
  and 1 s more, at most 15 s. OBSERVE (after the probe): full read (G6-P8's toad_state per actor, the four lists,
  the +0x4A8 guest list walked from the source's element). SAMPLER every 0.1 s: per actor position, Intelligence +8 /
  +0xC, P, counter, AI runs, StdGame +0x14 stamp; the 200th sample also carries a second full read ("late").
  Tracked: the four original Toads t0-t3 and, in a grown area only, copies A 0x74E918 / B 0x74EDD8. X(o) = area base
  + o - 4.
CALIBRATION (G6-P9 run p1, before this protocol): the Init visit came 5.3 s after the area appeared (inside G6-P8's
  6 s window, hence the event-ended early phase here); the StdGame stamp is written in bursts of about 4.5 s every
  about 16.4 s and can stay constant for 12 s, so G6-P8's (d') (>= 3,000 over about 98 s) does not scale to G5-P3's
  route (load 1 about 38 s): (d'') below; a 20 s window contains at least one burst (about 40 increasing samples).
  Earlier recovery C phases (e481 / e483 / e485 / e488) all pass a fix-only state (20,795,836 free) between intro_10
  and intro_15 and show the same first intro_15 state (12,234,744 free, 4 / 1 chunks): E's cleanup term below.

OFFLINE (check, before the protocol commit and the build): O1-O8 PASS.
  O1 identity: the compiler equals 51276fe (no change); the original hashes; recompiled twice, images lvl ff969957...
     / ptr bab5a96a... / transit 8addf2c0... (7,664,720 / 209,708 / 41,508; growth 2,884 / 640 within 4,096 / 1,024),
     plan `level-tx 2 intro_10 g6p9.toad-pair 9a287c36ac38d6fa`, deterministic.
  O2 G6-P9's check O1-O10 re-run (e496/g6p9): copies, 80 entries, ten edits, the independent simulator, dev 15 / 15 and
     production 2 / 2 transaction cases, refusals, determinism. O3 K1-K5 re-run PASS.
  O4 G5-P4b's preflight with the pair: 14 / 14 (orderly-exit decision, arm at plan, abnormal child keeps the marker,
     wrong owner never terminated, second launch refused, other session / wrong plan cannot clear, malformed marker,
     orderly exit clears, exit 0 alone keeps the marker, profile-scoped clear, production refusal, play.ps1 dry run,
     G5-P2b R1-R8).
  O5 recovery roots: RA (pair + e478.lums-6) and RB (pair) plans both carry exactly
     `level-tx 2 intro_10 g6p9.toad-pair 9a287c36ac38d6fa` (the ordinary mod does not change the transaction id).
  O6 the judgement terms on G6-P9 run p1 (judged PASS): REG / OWN / LIST at both reads, ORACLE for the six actors,
     fresh state, the not-grown terms on A and D, address reuse accepted; eight mutations each rejected (copy missing
     from the world or the guest list, shared buffer, cross-block pointer, stale Jump state before the first visit
     (fresh and oracle), a second AI run, copies on an unmodified load).
  O7 hooks None in a fresh interpreter (G5-P3 / G5-P4b behaviour unchanged without this file), G5-P3's steps unchanged
     (sha256 0ef22a70...), hidden runner options, area lengths. O8 gate production at the start; private profiles.

ORACLE(actor, load) = G6-P8's one-run-then-idle witness with (d'') for (d'):
  (a) the early phase holds a sample with counter 0xFF and Intelligence +8 = Init (file or relocated record), and the
      first later sample with counter 0 shows AI runs = that value + 1 and (+8, +0xC) = X(Jump, Wait);
  (b) at the first full read Mind +0 = Intelligence +0 = X(0x580C78), Intelligence (+8, +0xC, +0x14) = X(Jump, Wait,
      Init);
  (c) in every 0.1-s sample of the load AI runs = (a)'s value, (+8, +0xC) = X(Jump, Wait), P 1, counter 0, one
      position;
  (d'') the stamp never decreases and increases in >= 20 samples; the load's sample window >= 20 s.
PAIR TERMS(read, control read) (G6-P9's P2 / P3, a control read of the same load without the copies):
  REG: area = 7,661,832 + 2,884; union (dynamic + inactive) = the control's + X(A), X(B), no duplicate, both walks'
    previous links consistent; dynamic world: X(source), X(A), X(B) consecutive; SO records = control + 2, the last two
    the copies, each once; backup targets = control + 2, X(copy + 0xC4) once each; personal types 71, last
    XAP_ToadIntro_G6P9; personal indices A 69, B 70, source 0x1D; both copies alive, model NIN_m_ToadIntro.
  OWN: per copy Perso / 3dData / StdGame / Brain = X(copy + 0x80 / 0xAC / 0x2B4 / 0x318), Brain +0 = X(copy + 0x324),
    Mind +4 = X(copy + 0x338), Mind +0 = the source's = X(0x580C78), Mind +0xC = 0, Intelligence +0x10 / +0x18 =
    X(copy + 0x350 / 0x358), Brain +4 = 0xCDCDCDCD; 3dData buffer words non-zero, different from each other and from
    the four originals'; every word of the source / A / B blocks pointing into another of the three is a world link
    (source +0x14 -> A, A +0x18 -> source, A +0x14 -> B, B +0x18 -> A) or that block's guest-list element next / prev
    as walked.
  LIST (the +0x4A8 guest list): reciprocal, owners unique, one header, ends 0 / 0, length = the control's + 2, the
    owners without the copies = the control's owners, both copies right after the source (order recorded; predicted
    source, A, B), each copy's element owner = the copy and header = the source's.
  Addresses equal across loads are not aliasing (legitimate reuse after release); every term is per load.

PROSPECTIVE PROTOCOL — RELOAD (committed before the development build and before any modified run)
Build: g5p1_dev_gate.py apply + tools\\build_incremental.bat (development); production restored afterwards.
Runs on one build: e496_TAG_ra = G5-P3's route exactly (copy of save entry intro_10_fresh as the run's disposable user
  root; Title -> Load -> intro_10; Pause -> Load -> Yes -> intro_10 again in the same process; Pause -> Exit Game ->
  title; 220 s; guest-scoped input, hidden, non-activating, muted, no physical pad, no captures); plan = g6p9.toad-pair
  only, session = run (marker armed), R3HD_DEV_STRUCTURAL_TX=intro_10. e496_TAG_rb = the same route, no plan, no
  variable (matched control: same build, same route, same observation).
INVALID (new tag, kept): process not found; in ra or rb fewer than two intro_10 entries or load bursts not menumap,
  intro_10, intro_10; a tracked actor unreadable at an entry's first read; an entry's sample window < 20 s; rb's
  originals failing ORACLE in either entry.
  L1 initial activation: ra one `M33 mods state=active`; exactly one `G5P1 level-tx active level=intro_10
     mod=g6p9.toad-pair id=9a287c36ac38d6fa` = the plan's level-tx; one `G6P1 level-tx version=2
     members=lvl,ptr,transit`; exactly three `G5P3 tx snapshot` lines intro_10.lvl 7,664,720 / intro_10.ptr 209,708 /
     transit.lvl 41,508, each disk_reads=3, all before the first `G5P3 tx read`; marker armed before the start
     (session = run, plan SHA-256).
  L2 first registration: entry 1: REG and OWN at the first read and OWN at the late read (control: rb entry 1's read).
  L3 first guest behaviour: entry 1: ORACLE for A, B and t0-t3; the copies' positions = the source's; each copy's
     stamp = the source's in >= 95 % of the samples; LIST at the first and the late read.
  L4 first unload: entry 1 left before entry 2 appeared; a fix-only block-8 state between (20,795,836 free, 1 allocated
     / 1 free chunk) = rb's; D(phase) = ra minus rb (free, largest, allocated / free chunks, every area's base and
     length): D(menu before) = {}, D(entry 1) = {area1_length +2,884, free -2,884, largest -2,884}, D(fix between) = {}.
  L5 second activation: one process for the run (runner exit 0, nothing left); `G5P3 tx pass` >= 2 for each member;
     every pass's image_bytes = its member's snapshot; still one level-tx line and three snapshot lines (both loads
     served from the one validated snapshot), no `G5P3 tx host_changed`, no `M36 grow read` naming a member (no host
     re-read, no partially patched image); entry 2 area length 7,661,832 + 2,884.
  L6 fresh identities and state: entry 2: REG and OWN at the first and late reads (control: rb entry 2); fresh: in entry
     2's early phase both copies show counter 0xFF with Intelligence +8 = Init (the file state, not entry 1's Jump)
     before their first visit (ORACLE (a) on entry 2); entry 2's copy addresses / buffers recorded (reuse allowed).
  L7 second guest behaviour: L3's terms on entry 2.
  L8 final cleanup and safety: D(entry 2) = D(entry 1)'s value, D(menu after) = {}; within ra entry 1 = entry 2 and
     menu before = menu after; block-8 walks valid after the first valid snapshot (`changed` tolerated outside
     intro_10, up to two); the marker cleared by the controlled end (marker_after none); M21 / M22 / M23 0, haptics
     policy line, runner exit 0, no game process naming the run left, game foreground events / samples 0 / 0, exception
     codes of ra within rb's plus 406D1388, no access-violation / engine-error line; protected files unchanged.
  Class (reload): L1-L8 = RELOAD VERIFIED; else NOT PASSED (named terms).

PROSPECTIVE PROTOCOL — FORCED TERMINATION (committed before any forced termination)
G5-P4b's phases with RA = g6p9.toad-pair + e478.lums-6 (designer default, not structural; makes intro_10 exit to
  intro_15 about 62 s after it opens) and RB = g6p9.toad-pair (isolation witness, never launched);
  R3HD_DEV_STRUCTURAL_TX=intro_10; `--test-level intro_10`, no input.
  A: plan(RA, e496_TAG_A) (arms the marker); hidden run up to 140 s; termination 3 s after KILL_READY (>= 30 samples
     holding both copies and each copy's stamp increased >= 10 times), at most 45 s after the area appears (else
     INVALID, nothing terminated); G5-P4b's ownership checks (r3hd.exe, the build's exe path, command line naming this
     run's log file, created after the harness started the runner, the runner as grandparent; creation time
     re-verified by the kill) or nothing is terminated (BLOCKED); Complete-R3hdStructuralSession after the runner ends.
  C: plan(RA, e496_TAG_C); hidden run 110 s; nothing clears the marker.
  D: `structural-recovery clear`; dry run; plan(RA, e496_TAG_D) (re-armed); final clear (G5-P4b).
  E (reactivation, this file): plan(RA, e496_TAG_E); hidden run 110 s (intro_10 -> intro_15 by e478.lums-6, then the
     runner's orderly window close); Complete-R3hdStructuralSession with run.json's exit code.
  R1 clean start: RA's root did not exist before the run (created fresh); A's plan ok with both mods active and no
     refusal code; RB unmarked before A.
  R2 marker preparation: A's marker session e496_TAG_A, mods [g6p9.toad-pair], levels [intro_10], plan_sha256 = A's
     plan file, whose level-tx = O5's RA line; marker mtime < process creation < first `M36 grow size` naming
     intro_10; A's log: one `G5P1 level-tx active` = that line's (level, mod, id), one `G6P1 level-tx version=2
     members=lvl,ptr,transit`, three `G5P3 tx snapshot` lines with the pair's sizes.
  R3 active composition: A's first read: REG and OWN (control: C's first read); A's early phase: ORACLE (a) for both
     copies; A's samples before the kill: ORACLE (c) for both copies, each copy's stamp = the source's in >= 95 %
     and increasing >= 10 times; LIST (control: C's first read).
  R4 verified ownership: G5-P4b's R1 (marker session and plan, every ownership check true).
  R5 forced termination: G5-P4b's R4 (only that pid; exit code != 0; the runner saw the end early; no process left;
     Test-R3hdOrderlyExit false, also with exit code 0 substituted).
  R6 marker persistence: G5-P4b's R5 (Complete returned cleared = false; marker byte-identical before the launch, after
     the termination and after Complete).
  R7 whole-transaction refusal: C's plan refuses g6p9.toad-pair with STRUCTURAL_RECOVERY, recovery armed, no new
     marker, no level-tx / tx-file record; C's log one `M33 mods state=active`, no G5P1 / G5P3 / G6P1 / M36 grow line,
     nothing served from intro_10.ptr or transit.lvl; C's first read: area 7,661,832, union = the 66-actor reference
     (E-484), no copy SuperObject in either world, records 122, personal types 69, guest list without copy owners (no
     single copy active); the marker byte-identical after C.
  R8 ordinary-mod continuity: e478.lums-6 active in A's and C's plans, C's log serves it in intro_10.lvl, C leaves
     intro_10 for intro_15.
  R9 profile isolation: RB has no marker before A, after A, after C, after D and after E; RB's dry run lists the pair
     active after C; preflight's profile-scoped clear case passed.
  R10 recovery completion and safety: G5-P4b's R9 (clear, dry run lists the pair, stamp-D plan carries its level-tx and
     arms a marker naming e496_TAG_D, final clear); E: marker armed for e496_TAG_E with E's plan, E's plan level-tx =
     A's, E's log activates it (one G5P1 line, three snapshots); E's first read REG and OWN (control: C), early ORACLE
     (a) for both copies, LIST; E leaves intro_10 with a fix-only state (20,795,836 free) before intro_15 and E's first
     intro_15 state = C's (free, largest, chunks, areas); Complete for E: controlled true, cleared true, marker none
     afterwards; G5-P4b's R10 (production refusal in preflight, protected files unchanged, A / C / E game foreground 0
     / 0, hook ready / stopped, M21 / M22 / M23 0, no process left, C and E runner exit 0); C's and E's exception codes
     within {406D1388}.
  Class (recovery): R1-R10 = RECOVERY VERIFIED; G5-P4b invalid conditions = INVALID (new tag); else NOT PASSED.
Milestone: reload VERIFIED and recovery VERIFIED and production regressions PASS = G6-P10 VERIFIED — PAIR RELOAD &
  FORCED-TERMINATION RECOVERY; otherwise the brief's partial / blocked / failed classes. Failures are kept; stop on a
  guest fault, partial activation, a stale state, retained memory, a lost marker, structural data in recovery or a
  safety violation.

RESULTS (recorded after the runs; protocol 7b0383d unchanged, no revision)
RUN r1 (reload, first run): RELOAD VERIFIED, L1-L8 PASS (judgement_reload_r1.json). Load 1 43.4 -> 81.9 s, load 2
  82.0 -> 130.3 s, both at 0x40F5509C / 7,664,716; one level-tx line, three snapshots, two passes per member from the
  snapshot; both loads: union 66 -> 68, records 124, backups 183, personal 71, world source -> A -> B, guest list 20 ->
  22 (source, A, B), own state, shared model, no unexplained cross-block word (first and late read); A / B
  0x416A39B0 / 0x416A3E70 and buffers 0x426E07EC / 0x426E0868 in both loads (reused after release); first early
  sample of each load: counter 0xFF, Intelligence +8 = Init; Init draws A 9 -> 10 / B 5 -> 6 (load 1), A 7 -> 8 / B
  12 -> 13 (load 2); stamps = the source's 274 / 274 and 369 / 369; memory vs rb: loads +2,884, menu / between / after
  none; fix-only 20,795,836 between; marker armed and cleared; faults = rb's (406D1388 x1, E0473458 x2).
RUN k1 (recovery, first run): RECOVERY VERIFIED, R1-R10 PASS (judgement_recover_k1.json). Marker 12:27:18.780 <
  process 19.803 < first grow 20.459; A: both copies registered, Init A 11 -> 12 / B 6 -> 7, stamps 57 / 57; kill of
  the verified pid 2968 at 19.3 s (five ownership checks; exit -1); marker 9e59d509... unchanged after the kill,
  Complete (cleared false) and C; C: STRUCTURAL_RECOVERY, no tx, no G5P1 / G5P3 / G6P1 / grow line, reference union,
  69 types, no copy; e478.lums-6 served, C -> intro_15; RB never marked; D clear / re-arm / clear; E: one activation,
  both copies registered with Init, fix-only before intro_15, intro_15 state = C's, orderly Complete cleared the
  marker; faults only 406D1388.
"""
import json
import re
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE))
import r3hd_mods as rm  # noqa: E402
import g3a_ab as g3a  # noqa: E402
import block8_probe as bp  # noqa: E402
import g5p1_pilot as p1  # noqa: E402
import g5p3_reentry as r3  # noqa: E402
import g5p4b_recovery as p4b  # noqa: E402
import g6p1b_lifecycle as g6b  # noqa: E402
import g6p3_pilot as g6p3  # noqa: E402
import g6p8_toad as g8  # noqa: E402
import g6p9_toad_pair as g9  # noqa: E402

PREFIX = "e496"
WORK = ROOT / "private" / "work" / PREFIX
RUNS = g3a.RUNS
LEVEL = "intro_10"
AREA, N, NP = g3a.AREA, g9.N_LVL, g9.N_PTR
SRC, BLK, COPY_A, COPY_B = g9.SRC, g9.BLK, g9.COPY_A, g9.COPY_B
MOD = g9.MOD
NAME_B = g9.NAMES[1].decode()
TX = "9a287c36ac38d6fa"
TX_LINE = f"level-tx 2 {LEVEL} {MOD} {TX}"
IMAGES = {"lvl": "ff969957dee35a83372c2e1f7369494f4563c02fa5da67fb9c5a0cfa3564b91b",
          "ptr": "bab5a96a82b21edea813434c6ff4bee92a2e247187c76d9c00c2b8f439f9e4aa",
          "transit": "8addf2c04919ee35dfbcc643562747981c5419bc337866533d0bb5923b3b3d44"}
SIZES = {"lvl": g9.SIZE + N, "ptr": g9.PSIZE + NP, "transit": g9.TSIZE}
SNAP = sorted([("intro_10.lvl", str(SIZES["lvl"])), ("intro_10.ptr", str(SIZES["ptr"])),
               ("transit.lvl", str(SIZES["transit"]))])
COMPILER_COMMIT = "51276fe"
FIX_ONLY_FREE = g6b.FIX_ONLY_FREE
EARLY_CAP, LATE_SAMPLE = 15.0, 200
COPIES = ("copyA", "copyB")
REC = g8.REC
sha = lambda b: __import__("hashlib").sha256(b).hexdigest() if b is not None else None   # noqa: E731


# --- live observation (hooks) -----------------------------------------------------------------------------------------

def grown(p, ab):
    a1 = (bp.areas(p) or {}).get(1)
    return bool(a1 and a1["base"] == ab and a1["end"] - a1["base"] == AREA + N)


def tracked(p, ab):
    t = dict(g8.TOADS)
    if grown(p, ab):
        t.update(copyA=COPY_A, copyB=COPY_B)
    return t


def early(p, ab, t0, cap=EARLY_CAP):
    labels = tracked(p, ab)
    out, seen, start, done = [], {}, time.monotonic(), None
    while time.monotonic() < start + cap and p.running():
        e = {"t": round(time.monotonic() - t0, 4)}
        try:
            e["timer"] = p.words(g8.TIMER, 1)[0]
        except Exception:
            e["timer"] = None
        for label, off in labels.items():
            X = ab + off - 4
            io = g8.INTEL_OFF.get(label, g8.CHAIN["intel"])
            try:
                sb = p.read(X + g8.CHAIN["3ddata"] + 340, 8)
                iw = p.words(X + io + 8, 2)
                e[label] = {"P": sb[2], "ctr": sb[3], "runs": struct.unpack_from(">H", sb, 4)[0], "beh": iw[0],
                            "prev": iw[1]}
                if seen.get(label, 0) == 0 and sb[3] == 255:
                    seen[label] = 1
                elif seen.get(label) == 1 and sb[3] == 0:
                    seen[label] = 2
            except Exception as x:
                e[label] = {"error": type(x).__name__}
        out.append(e)
        if done is None and all(seen.get(k) == 2 for k in labels):
            done = time.monotonic()
        if done is not None and time.monotonic() >= done + 1.0:
            break
        time.sleep(0.004)
    return out


def full_read(p, ab):
    r = {"actors": {}}
    for label, off in tracked(p, ab).items():
        try:
            r["actors"][label] = g8.toad_state(p, ab + off - 4)
        except Exception as x:
            r["actors"][label] = {"error": repr(x)}
    r["lists"] = g6p3.lists(p)
    r["elist"] = g8.element_list(p, ab + SRC + g8.ELEM - 4)
    return r


def observe(rd, p, ab):
    return full_read(p, ab)


class Sampler:
    def __init__(self, p, ab):
        self.p, self.ab, self.chains, self.n = p, ab, None, 0

    def __call__(self, gen, t):
        p = self.p
        if self.chains is None:
            self.chains = {}
            for label, off in tracked(p, self.ab).items():
                st = g8.toad_state(p, self.ab + off - 4)
                self.chains[label] = (st["so"], st["matrix"], st["mind"][1], st["3ddata"])
        self.n += 1
        out = {"a": {}}
        for label, (so, mx, intel, d3) in self.chains.items():
            m = p.read(mx + 0x34, 12)
            beh, prev = p.words(intel + 8, 2)
            sb = p.read(d3 + 340, 8)
            out["a"][label] = {"pos": list(struct.unpack(">3f", m)), "beh": beh, "prev": prev, "P": sb[2],
                               "ctr": sb[3], "runs": struct.unpack_from(">H", sb, 4)[0],
                               "stamp": p.words(so + g8.CHAIN["stdgame"] + 0x14, 1)[0]}
        out["v8"] = out["a"].get("copyA", out["a"].get("t1", {})).get("stamp")   # G5-P4b's loop reads "v8"
        if self.n == LATE_SAMPLE:
            out["late"] = full_read(p, self.ab)
        return out


def kill_ready(samples):
    c = [s["a"] for s in samples if all(k in s.get("a", {}) for k in COPIES)]
    inc = lambda k: sum(1 for x, y in zip(c, c[1:]) if y[k]["stamp"] > x[k]["stamp"])   # noqa: E731
    return len(c) >= 30 and inc("copyA") >= 10 and inc("copyB") >= 10


def setup():
    WORK.mkdir(parents=True, exist_ok=True)
    p1.WORK = WORK
    r3.PREFIX, r3.WORK = PREFIX, WORK
    r3.PLAN_MOD = (MOD, lambda: [g9.pair_op()])
    r3.EXTRA_MODS = []
    r3.AREA10 = (AREA, AREA + N)
    r3.OBSERVE, r3.SAMPLER, r3.TICK, r3.EARLY = observe, Sampler, None, early
    p4b.PREFIX, p4b.WORK = PREFIX, WORK
    p4b.STRUCT_ID = MOD
    p4b.STRUCT_OV = lambda: [g9.pair_op()]
    p4b.GROWN_AREA = AREA + N
    p4b.GROWN_NODES = -1
    p4b.sites = lambda: []
    p4b.new_nodes = lambda: []
    p4b.OBSERVE, p4b.SAMPLER, p4b.KILL_READY, p4b.EARLY = observe, Sampler, kill_ready, early


# --- judgement terms (pure functions of recorded reads) ---------------------------------------------------------------

def union(read):
    ls = read["lists"]
    return ls["dw"]["walk"] + ls["inactive"]["walk"]


def reg_terms(read, ctl, ab):
    """REG: the pair's registration against a control read of the same load without the copies."""
    X = lambda o: ab + o - 4   # noqa: E731
    ls, la, fa = read["lists"], ctl["lists"], read["actors"]
    cps = [X(COPY_A), X(COPY_B)]
    try:
        dw, u, ua, bt = ls["dw"]["walk"], union(read), union(ctl), ls["bak_targets"]
        i = dw.index(X(SRC)) if X(SRC) in dw else -9
        t = {"lists_ok": "error" not in ls and ls["dw"]["prev_ok"] and ls["inactive"]["prev_ok"] and len(u) == len(set(u)),
             "union_control_plus_two": sorted(u) == sorted(ua + cps),
             "world_source_A_B": i >= 0 and dw[i:i + 3] == [X(SRC)] + cps,
             "alive_model": all(fa[k].get("alive") and fa[k].get("model") == "NIN_m_ToadIntro" for k in COPIES),
             "records": ls["rec"]["count"] == la["rec"]["count"] + 2 and ls["rec"]["owners"][-2:] == cps
             and all(ls["rec"]["owners"].count(x) == 1 for x in cps + [X(SRC)]),
             "backups": len(bt) == len(la["bak_targets"]) + 2 and all(bt.count(x + 0xC4) == 1 for x in cps),
             "personal": ls["personal"] == {"count": 71, "last_name": NAME_B},
             "personal_index": [fa["copyA"].get("std_personal"), fa["copyB"].get("std_personal"),
                                fa["t1"].get("std_personal")] == [69, 70, 0x1D]}
    except Exception as x:
        t = {"error": repr(x)}
    return all(v is True for v in t.values()), t


def own_terms(read, ab):
    """OWN: each copy's own chain / Intelligence locals / buffer, the shared model, no unexplained cross-block word."""
    X = lambda o: ab + o - 4   # noqa: E731
    acts = read["actors"]
    try:
        sr = acts["t1"]
        cps = [X(COPY_A), X(COPY_B)]
        blocks = {"t1": X(SRC), "copyA": cps[0], "copyB": cps[1]}
        at = {e["at"]: e for e in (read.get("elist", {}).get("chain") or [])}
        world = {("t1", 0x14): cps[0], ("copyA", 0x18): X(SRC), ("copyA", 0x14): cps[1], ("copyB", 0x18): cps[0]}
        cross = {}
        for lab, base in blocks.items():
            words = acts[lab].get("block_words") or []
            for k, w_ in enumerate(words):
                for lab2, b2 in blocks.items():
                    if lab2 != lab and b2 <= w_ < b2 + BLK:
                        e = at.get(base + g8.ELEM)
                        okw = world.get((lab, 4 * k)) == w_ or (e is not None and (
                            (4 * k == g8.ELEM + 4 and e["next"] == w_) or (4 * k == g8.ELEM + 8 and e["prev"] == w_)))
                        if not okw:
                            cross.setdefault(lab, []).append(hex(4 * k))
        t = {"no_unexplained_cross_block_words": not cross,
             "world_links": all(len(acts[lab].get("block_words") or []) == BLK // 4
                                and acts[lab]["block_words"][k // 4] == v for (lab, k), v in world.items())}
        others = [acts[k].get("buffer") for k in g8.TOADS]
        bufs = []
        for lab, C0 in (("copyA", COPY_A), ("copyB", COPY_B)):
            cp = acts[lab]
            mind, smind = cp.get("mind") or [None] * 4, sr.get("mind") or [None] * 4
            iw = cp.get("intel_words") or [None] * 8
            t[lab] = {"chain_own": {k: cp.get(k) for k in ("perso", "3ddata", "stdgame", "brain")}
                      == {k: X(C0 + g8.CHAIN[k]) for k in ("perso", "3ddata", "stdgame", "brain")},
                      "brain0_mind": (cp.get("brain_words") or [None])[0] == X(C0 + g8.CHAIN["mind"]),
                      "mind1_intel": mind[1] == X(C0 + g8.CHAIN["intel"]),
                      "model_shared": mind[0] == smind[0] == X(g8.AI_MODEL), "no_dsgmem": mind[3] == 0 == smind[3],
                      "intel_local_own": [iw[4], iw[6]] == [X(C0 + g8.INTEL_LOCAL[0]), X(C0 + g8.INTEL_LOCAL[1])],
                      "brain4": (cp.get("brain_words") or [0, 0])[1] == 0xCDCDCDCD
                      == (sr.get("brain_words") or [0, 0])[1],
                      "buffer_own": bool(cp.get("buffer")) and cp.get("buffer") not in others}
            bufs.append(cp.get("buffer"))
        t["buffers_distinct"] = bufs[0] != bufs[1]
        t["source_personal"] = sr.get("std_personal") == 0x1D
        t["cross"] = cross
        ok = (t["no_unexplained_cross_block_words"] and t["world_links"] and t["buffers_distinct"]
              and t["source_personal"] and all(all(t[k].values()) for k in COPIES))
    except Exception as x:
        t, ok = {"error": repr(x)}, False
    return bool(ok), t


def list_terms(read, ctl, ab):
    """LIST: the guest-built +0x4A8 list with both copies right after the source."""
    X = lambda o: ab + o - 4   # noqa: E731
    try:
        el, ec = read["elist"], ctl["elist"]
        ch = el.get("chain") or []
        at = {e["at"]: e for e in ch}
        cps = [X(COPY_A), X(COPY_B)]
        recip = all(at[e["next"]]["prev"] == e["at"] for e in ch if e["next"] in at) and \
            all(at[e["prev"]]["next"] == e["at"] for e in ch if e["prev"] in at)
        own = [e["owner"] for e in ch]
        oc = [e["owner"] for e in (ec.get("chain") or [])]
        j = own.index(X(SRC)) if X(SRC) in own else -9
        se = at.get(X(SRC + g8.ELEM))
        els = [at.get(c + g8.ELEM) for c in cps]
        t = {"len": len(ch), "len_control": len(oc), "reciprocal": recip, "owners_unique": len(own) == len(set(own)),
             "one_header": len({e["header"] for e in ch}) == 1, "ends": el.get("ends"),
             "order_after_source": [hex(x) for x in own[j:j + 3]] if j >= 0 else None,
             "predicted_order": own[j:j + 3] == [X(SRC)] + cps}
        ok = bool(ch and "error" not in el and recip and t["owners_unique"] and t["one_header"]
                  and el.get("ends") == [0, 0] and len(ch) == len(oc) + 2 and se is not None
                  and all(e is not None and e["owner"] == c and e["header"] == se["header"] for e, c in zip(els, cps))
                  and [x for x in own if x not in cps] == oc and j >= 0 and sorted(own[j + 1:j + 3]) == sorted(cps))
    except Exception as x:
        t, ok = {"error": repr(x)}, False
    return ok, t


def not_grown_terms(read, ab):
    """No copy registered: the 66-actor reference union, 122 records, 69 personal types, no copy owner in the list."""
    try:
        U = union(read)
        rel = {x - ab for x in U}
        ls = read["lists"]
        cps = {ab + COPY_A - 4, ab + COPY_B - 4}
        own = [e["owner"] for e in (read.get("elist", {}).get("chain") or [])]
        t = {"union_reference": rel == g6b.reference_union() and len(U) == len(set(U)),
             "no_copy_in_worlds": not (set(U) & cps), "records_122": ls["rec"]["count"] == 122,
             "personal_69": ls["personal"]["count"] == 69, "list_without_copies": bool(own) and not (set(own) & cps)}
    except Exception as x:
        t = {"error": repr(x)}
    return all(v is True for v in t.values()), t


def oracle(early_, samples, read, ab, label, min_window=20.0):
    """ORACLE (a)-(c) and (d'') for one actor in one load. Returns (ok, detail)."""
    X = lambda o: ab + o - 4   # noqa: E731
    d = {}
    ea = [e[label] for e in early_ if label in e and "error" not in e[label]]
    ipre = [i for i, e in enumerate(ea) if e["ctr"] == 255 and e["beh"] in (REC["init"] - 4, X(REC["init"]))]
    pre = [ea[i] for i in ipre]
    post = [e for e in ea[ipre[-1] + 1:] if e["ctr"] == 0] if ipre else []
    d["pre_run_samples"], d["post_run_samples"] = len(pre), len(post)
    a = bool(pre and post) and post[0]["runs"] == (pre[-1]["runs"] + 1) % 0x10000 \
        and [post[0]["beh"], post[0]["prev"]] == [X(REC["jump"]), X(REC["wait"])]
    d["init_draw_then_run"] = [pre[-1]["runs"] if pre else None, post[0]["runs"] if post else None]
    lf = read["actors"].get(label, {})
    iw = lf.get("intel_words") or [None] * 8
    b = iw[0] == X(g8.AI_MODEL) and iw[2:4] == [X(REC["jump"]), X(REC["wait"])] and iw[5] == X(REC["init"]) \
        and (lf.get("mind") or [None])[0] == X(g8.AI_MODEL)
    sm = [s["a"][label] for s in samples if label in s.get("a", {})]
    ts = [s["t"] for s in samples if label in s.get("a", {})]
    runs = {s["runs"] for s in sm}
    c = bool(sm) and len(runs) == 1 and bool(post) and runs == {post[0]["runs"]} and all(
        s["beh"] == X(REC["jump"]) and s["prev"] == X(REC["wait"]) and s["P"] == 1 and s["ctr"] == 0 for s in sm) \
        and len({tuple(s["pos"]) for s in sm}) == 1
    st = [s["stamp"] for s in sm]
    incs = sum(1 for x, y in zip(st, st[1:]) if y > x)
    window = ts[-1] - ts[0] if ts else 0
    dd = len(st) > 1 and all(y >= x for x, y in zip(st, st[1:])) and incs >= 20 and window >= min_window
    d.update(a=a, b=b, c=c, d=dd, runs=sorted(runs), stamp=[st[0], st[-1]] if st else None, stamp_increases=incs,
             window=round(window, 1), n=len(sm), intel_first=[hex(x) if x else x for x in iw[:7]])
    return bool(a and b and c and dd), d


def stamps_equal(samples, k):
    both = [(s["a"][k]["stamp"], s["a"]["t1"]["stamp"]) for s in samples if k in s.get("a", {}) and "t1" in s["a"]]
    return [sum(1 for x, y in both if x == y), len(both)]


def behaviour_terms(early_, samples, read, ab, labels):
    o = {k: oracle(early_, samples, read, ab, k) for k in labels}
    eq = {k: stamps_equal(samples, k) for k in COPIES if k in labels}
    sp = read["actors"]["t1"].get("position")
    pos = all(read["actors"][k].get("position") == sp for k in COPIES if k in labels)
    ok = all(v[0] for v in o.values()) and pos and all(n and s >= 0.95 * n for s, n in eq.values())
    return ok, {"oracle": {k: v[1] for k, v in o.items()}, "oracle_ok": {k: v[0] for k, v in o.items()},
                "stamp_equal_source": eq, "position_equal_source": pos}


def fresh_terms(early_, ab):
    """L6 fresh state: each copy shows the file state (counter 0xFF, Intelligence +8 = Init) before its first visit."""
    X = lambda o: ab + o - 4   # noqa: E731
    t = {}
    for k in COPIES:
        ea = [e[k] for e in early_ if k in e and "error" not in e[k]]
        first = ea[0] if ea else None
        t[k] = {"first_early": first, "pre_init_state": bool(first and first["ctr"] == 255
                                                            and first["beh"] in (REC["init"] - 4, X(REC["init"])))}
    return all(t[k]["pre_init_state"] for k in COPIES), t


# --- offline ----------------------------------------------------------------------------------------------------------

def p1_trace():
    """G6-P9 run p1 (judged PASS): C (pair) and A (control) in this file's read format, for O6."""
    out = {}
    for c in ("A", "C", "D"):
        w = g9.WORK / "p1" / c
        lv = json.loads((w / "live.json").read_text())
        out[c] = {"early": json.loads((w / "early.json").read_text()),
                  "samples": json.loads((w / "samples.json").read_text()), "first": lv["first"], "end": lv["end"],
                  "ab": lv["first"]["ab"]}
    return out


def validate_judge():
    """O6: the terms on G6-P9's known-good trace, and on mutated copies of it (each mutation must fail its term)."""
    import copy
    tr = p1_trace()
    C, A, D = tr["C"], tr["A"], tr["D"]
    ab = C["ab"]
    res = {}
    res["reg_first"] = reg_terms(C["first"], A["first"], ab)[0]
    res["own_first_end"] = own_terms(C["first"], ab)[0] and own_terms(C["end"], ab)[0]
    res["list_first_end"] = list_terms(C["first"], A["first"], ab)[0] and list_terms(C["end"], A["end"], ab)[0]
    res["behaviour"] = behaviour_terms(C["early"], C["samples"], C["first"], ab, list(g8.TOADS) + list(COPIES))[0]
    res["control_behaviour"] = behaviour_terms(A["early"], A["samples"], A["first"], A["ab"], list(g8.TOADS))[0]
    res["fresh"] = fresh_terms(C["early"], ab)[0]
    res["not_grown_D"] = not_grown_terms(D["first"], D["ab"])[0]
    res["not_grown_A"] = not_grown_terms(A["first"], A["ab"])[0]
    # the same addresses in a second load are not aliasing: entry 2 = a copy of entry 1 passes every term
    res["address_reuse_accepted"] = reg_terms(copy.deepcopy(C["first"]), A["first"], ab)[0]
    neg = {}
    m = copy.deepcopy(C["first"])
    m["lists"]["dw"]["walk"].remove(ab + COPY_B - 4)
    neg["copy_B_missing_from_world"] = not reg_terms(m, A["first"], ab)[0]
    m = copy.deepcopy(C["first"])
    m["actors"]["copyB"]["buffer"] = m["actors"]["copyA"]["buffer"]
    neg["shared_buffer"] = not own_terms(m, ab)[0]
    m = copy.deepcopy(C["first"])
    m["actors"]["copyB"]["block_words"][0x40] = ab + SRC - 4 + 0x100
    neg["cross_block_pointer"] = not own_terms(m, ab)[0]
    m = copy.deepcopy(C["first"])
    m["elist"]["chain"] = [e for e in m["elist"]["chain"] if e["owner"] != ab + COPY_A - 4]
    neg["copy_A_missing_from_guest_list"] = not list_terms(m, A["first"], ab)[0]
    stale = [dict(e, copyB=dict(e["copyB"], beh=ab + REC["jump"] - 4)) if "copyB" in e and "error" not in e["copyB"]
             else e for e in C["early"]]
    neg["stale_state_not_fresh"] = not fresh_terms(stale, ab)[0]
    neg["stale_state_fails_oracle"] = not oracle(stale, C["samples"], C["first"], ab, "copyB")[0]
    sm = copy.deepcopy(C["samples"])
    for s in sm[100:]:
        if "copyA" in s["a"]:
            s["a"]["copyA"]["runs"] += 1
    neg["second_ai_run_fails_oracle"] = not oracle(C["early"], sm, C["first"], ab, "copyA")[0]
    neg["copies_on_unmodified_load"] = not not_grown_terms(C["first"], ab)[0]
    res["negatives"] = neg
    return all(v for k, v in res.items() if k != "negatives") and all(neg.values()), res


def check():
    setup()
    O, det = {}, {}
    saved = (g9.WORK, g8.WORK)
    g9.WORK = WORK / "g6p9"   # G6-P9's helpers write here, never into e495
    g9.WORK.mkdir(parents=True, exist_ok=True)
    # O1 transaction identity: recompile from the verified original resources, no compiler change
    lvl, ptr, tl = g8.files()
    res, text, paths = g9.compile_mods("o1_pair", [(MOD, [g9.pair_op()])])
    m, imgs = g8.plan_images(text)
    res2, text2, _ = g9.compile_mods("o1_pair_again", [(MOD, [g9.pair_op()])])
    m2, imgs2 = g8.plan_images(text2)
    gd = subprocess.run(["git", "diff", "--quiet", COMPILER_COMMIT, "--", "tools/r3hd_mods.py"], cwd=ROOT).returncode
    det["O1"] = {"txs": m["txs"], "hashes": {k: sha(b) for k, b in imgs.items()}, "sizes": {k: len(b) for k, b in
                                                                                            imgs.items()},
                 "compiler_equal_to": COMPILER_COMMIT if gd == 0 else None}
    O["O1_transaction_identity"] = (
        [sha(lvl), sha(ptr), sha(tl)] == [g8.LVL_SHA, g8.PTR_SHA, g8.TRANSIT_SHA] and res["active"] == [MOD]
        and m["txs"] == [TX_LINE] and m2["txs"] == [TX_LINE] and imgs2 == imgs
        and {k: sha(b) for k, b in imgs.items()} == IMAGES and {k: len(b) for k, b in imgs.items()} == SIZES
        and gd == 0 and N <= 4096 and NP <= 1024)
    # O2 G6-P9's offline check (O1-O10: identities, allocation, registration plan, 80 entries, ten edits, the
    # independent simulator, dev / production transaction tests, refusals, determinism), outputs in e496/g6p9
    try:
        rc9 = g9.check()
        c9 = json.loads((g9.WORK / "check.json").read_text())
        rck = g9.recovery()
        k9 = json.loads((g9.WORK / "recovery.json").read_text())
    finally:
        g9.WORK, g8.WORK = saved
        setup()
    det["O2"] = {"O": c9["O"], "slots": c9["details"]["info"]["slots"], "edits": c9["details"]["info"]["edits"],
                 "memory": c9["details"]["info"]["memory"], "tx_id": c9["details"].get("tx_id")}
    O["O2_g6p9_offline_check"] = (rc9 == 0 and c9["pass"] and c9["details"]["info"]["slots"] == 80
                                  and len(c9["details"]["info"]["edits"]) == 10 and c9["details"].get("tx_id") == TX)
    # O3 K1-K5
    det["O3"] = k9["K"]
    O["O3_recovery_marker_K1_K5"] = rck == 0 and k9["pass"]
    # O4 the recovery runner's deterministic preflight with the pair (14 checks)
    rcp = p4b.preflight()
    pre = json.loads((WORK / "preflight.json").read_text())
    det["O4"] = pre["res"]
    O["O4_recovery_preflight"] = rcp in (0, None) and pre["pass"] and len(pre["res"]) == 14
    # O5 the recovery roots' plans: RA (pair + e478.lums-6) and RB (pair)
    ra = p4b.root("o5_RA")
    rb = p4b.root("o5_RB", lums=False)
    pa = p4b.plan(ra, "o5-a", dry=False)
    pb = p4b.plan(rb, "o5-b", dry=False)
    ta = [x for x in Path(pa["plan"]).read_text(encoding="utf-8").splitlines() if x.startswith("level-tx")]
    tb = [x for x in Path(pb["plan"]).read_text(encoding="utf-8").splitlines() if x.startswith("level-tx")]
    for r_ in (ra, rb):
        subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "structural-recovery", "clear", "--json",
                        "--mods-root", str(r_["mods"]), "--cache", str(r_["cache"]), "--game-dir", str(g3a.GAME)],
                       capture_output=True, text=True)
    det["O5"] = {"RA_active": pa.get("active"), "RA_tx": ta, "RB_active": pb.get("active"), "RB_tx": tb}
    O["O5_recovery_roots"] = (sorted(pa.get("active", [])) == sorted([MOD, "e478.lums-6"]) and len(ta) == 1
                              and ta[0].startswith(f"level-tx 2 {LEVEL} {MOD} ") and pb.get("active") == [MOD]
                              and tb == [TX_LINE] and p4b.marker_bytes(ra) is None and p4b.marker_bytes(rb) is None)
    # O6 the judgement terms on G6-P9's known-good trace and mutations
    ok6, d6 = validate_judge()
    det["O6"] = d6
    O["O6_judge_validation"] = ok6
    # O7 runner configuration: hooks default None before setup (fresh interpreter), G5-P3's route steps unchanged,
    # hidden runner options, the area lengths the runners accept
    q = subprocess.run([sys.executable, "-c", "import sys; sys.path[:0] = [r'%s', r'%s']; import g5p3_reentry as r3, "
                        "g5p4b_recovery as p4b; print(r3.EARLY is None and r3.OBSERVE is None and r3.SAMPLER is None "
                        "and p4b.EARLY is None and p4b.OBSERVE is None and p4b.KILL_READY is None)" % (TOOLS, HERE)],
                       capture_output=True, text=True)
    src3 = Path(r3.__file__).read_text(encoding="utf-8")
    src4 = Path(p4b.__file__).read_text(encoding="utf-8")
    det["O7"] = {"defaults_none": q.stdout.strip(), "steps_sha": sha("\n".join(r3.STEPS).encode())}
    O["O7_runner_configuration"] = (q.stdout.strip() == "True" and r3.EARLY is early and p4b.EARLY is early
                                    and r3.AREA10 == (AREA, AREA + N) and p4b.GROWN_AREA == AREA + N
                                    and all('"--play"' in s and '"--user-root"' in s for s in (src3, src4))
                                    and "--visible" not in src3 + src4 and r3.ENTRY == "intro_10_fresh")
    # O8 gate and isolation: production at the start; profiles are private copies (m9_profiles / e496 roots)
    gs = g8.gate_status()
    det["O8"] = {"gate": gs, "profiles": str(r3.m12.PROFILES), "work": str(WORK)}
    O["O8_gate_isolation"] = gs in ("production", "patched") and "private" in r3.m12.PROFILES.parts \
        and "private" in WORK.parts
    out = {"pass": all(O.values()), "O": O, "details": det}
    (WORK / "check.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(O, indent=1))
    print("CHECK_G6P10", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


# --- runs -------------------------------------------------------------------------------------------------------------

def require():
    if g8.gate_status() != "patched":
        raise SystemExit("the development gate is not applied")
    if not json.loads((WORK / "check.json").read_text())["pass"]:
        raise SystemExit("check did not pass")


def reload(tag):
    require()
    setup()
    before = p4b.protected()
    for case in ("ra", "rb"):
        row = r3.run_case(tag, case)
        print(case, json.dumps({k: row.get(k) for k in ("run", "runner_exit", "process_left", "controlled",
                                                        "marker_after", "bursts")}, default=str), flush=True)
    (WORK / tag / "protected.json").write_text(json.dumps({"before": before, "after": p4b.protected()}) + "\n")
    return 0


def root_paths(tag, name):
    d = WORK / "roots" / f"run_{tag}_{name}"
    return {"home": None, "mods": d / "mods", "cache": d / "cache", "game": g3a.GAME, "_dir": d}


def recover(tag):
    require()
    setup()
    ev = {"RA_root_existed_before": root_paths(tag, "RA")["_dir"].exists(),
          "RB_root_existed_before": root_paths(tag, "RB")["_dir"].exists()}
    if ev["RA_root_existed_before"] or ev["RB_root_existed_before"]:
        raise SystemExit("roots exist")
    rc = p4b.run(tag)
    RA, RB = root_paths(tag, "RA"), root_paths(tag, "RB")
    ev["marker_before_E"] = sha(p4b.marker_bytes(RA))
    sE = f"{PREFIX}_{tag}_E"
    pe = p4b.plan(RA, sE)
    ev["E_plan"] = {k: pe.get(k) for k in ("result", "active", "structural_marker", "structural_recovery", "plan")}
    ev["E_plan"]["codes"] = {m["id"]: m.get("code") for m in pe.get("mods", []) if m.get("state") != "active"}
    etext = Path(pe["plan"]).read_text(encoding="utf-8") if pe.get("plan") else ""
    shutil.copyfile(pe["plan"], WORK / f"plan_{tag}_E.txt")
    ev["E_plan_tx"] = [x for x in etext.splitlines() if x.startswith("level-tx")]
    ev["E_plan_sha256"] = sha(Path(pe["plan"]).read_bytes()) if pe.get("plan") else None
    mk = p4b.marker_bytes(RA)
    ev["marker_E"] = {"sha256": sha(mk), "json": json.loads(mk) if mk else None}
    rowE = p4b.launch(tag, "E", pe["plan"], 110, False)
    code = (rowE.get("run_json") or {}).get("exit_code")
    ev["E_complete"] = p4b.end(RA, sE, pe["structural_marker"], RUNS / rowE["run"], code)
    ev["marker_after_E"] = sha(p4b.marker_bytes(RA))
    ev["RB_marker_after_E"] = sha(p4b.marker_bytes(RB))
    ev["protected_after_E"] = p4b.protected()
    (WORK / tag / "evidence_E.json").write_text(json.dumps(ev, indent=1, default=str) + "\n")
    print(json.dumps({k: ev[k] for k in ("marker_before_E", "E_plan_tx", "marker_after_E", "RB_marker_after_E")},
                     default=str))
    return rc


# --- judgements -------------------------------------------------------------------------------------------------------

def entry_view(e):
    """One reload entry: early, samples, first read, late read."""
    lv = e.get("live") or {}
    late = next((s["late"] for s in e.get("samples", []) if "late" in s), None)
    return {"early": e.get("early") or [], "samples": e.get("samples", []), "first": lv, "late": late, "ab": e["ab"]}


def mem_norm(x):
    b = r3.brief(x)
    return b and {k: b[k] for k in ("free", "largest", "alloc", "free_chunks")} | {"areas": sorted(b["areas"].values())}


def judge_reload(tag):
    setup()
    ra = g6b._load(WORK / tag / "ra", f"{PREFIX}_{tag}_ra")
    rb = g6b._load(WORK / tag / "rb", f"{PREFIX}_{tag}_rb")
    det, L, invalid = {}, {}, []
    for c, r in (("ra", ra), ("rb", rb)):
        b = iter(r["bursts"])
        if not (all(any(n == s for s in b) for n in ("menumap", "intro_10", "intro_10")) and len(r["entries"]) >= 2
                and r["phases"]["e2"] is not None):
            invalid.append(f"{c}:route")
            continue
        for i, e in enumerate(r["entries"][:2], 1):
            v = entry_view(e)
            if not v["first"].get("actors") or any("error" in a for a in v["first"]["actors"].values()):
                invalid.append(f"{c}:read{i}")
            ts = [s["t"] for s in v["samples"]]
            if not ts or ts[-1] - ts[0] < 20:
                invalid.append(f"{c}:samples{i}")
    if not invalid:
        for i in (1, 2):
            v = entry_view(rb["entries"][i - 1])
            ok, d = behaviour_terms(v["early"], v["samples"], v["first"], v["ab"], list(g8.TOADS))
            det[f"rb_oracle_{i}"] = d
            if not ok:
                invalid.append(f"rb:oracle{i}")
    if invalid:
        res = {"invalid": invalid, "verdict": "INVALID", "details": det, "bursts": [ra["bursts"], rb["bursts"]]}
        (WORK / f"judgement_reload_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
        print(json.dumps({"invalid": invalid, "verdict": "INVALID"}))
        return 1
    log = ra["log"]
    lines = log.splitlines()
    ptx = p1.parse_plan((WORK / tag / "ra" / "plan_copy.txt").read_text(encoding="utf-8"))["txs"]
    tx = [tuple(x) for x in re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log)]
    g6l = re.findall(r"G6P1 level-tx version=(\d+) members=(\S+)", log)
    snaps = re.findall(r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", log)
    snap_sizes = {f: b_ for f, _, b_, _ in snaps}
    first = {k: next((i for i, ln in enumerate(lines) if k in ln), None)
             for k in ("M33 mods state=active", "G5P3 tx snapshot", "G5P3 tx read")}
    mb = ra["marker_before_start"]
    det["L1"] = {"plan_tx": ptx, "tx": tx, "g6p1": g6l, "snapshots": snaps}
    L["L1_initial_activation"] = bool(
        log.count("M33 mods state=active") == 1 and ptx == [TX_LINE] and tx == [(LEVEL, MOD, TX)]
        and g6l == [("2", "lvl,ptr,transit")] and sorted((f, b_) for f, _, b_, _ in snaps) == SNAP
        and all(d_ == "3" for *_, d_ in snaps) and None not in first.values()
        and first["G5P3 tx snapshot"] < first["G5P3 tx read"] and first["M33 mods state=active"] < first["G5P3 tx read"]
        and mb[0] == "armed" and mb[1]["session"] == ra["run"] and mb[1]["plan_sha256"] == ra["plan_sha256"])
    ent = {}
    for i in (1, 2):
        v, vc = entry_view(ra["entries"][i - 1]), entry_view(rb["entries"][i - 1])
        ab = v["ab"]
        rg = reg_terms(v["first"], vc["first"], ab)
        o1, o2 = own_terms(v["first"], ab), (own_terms(v["late"], ab) if v["late"] else (False, {"missing": "late"}))
        l1 = list_terms(v["first"], vc["first"], ab)
        l2 = list_terms(v["late"], vc["late"] or vc["first"], ab) if v["late"] else (False, {"missing": "late"})
        bh = behaviour_terms(v["early"], v["samples"], v["first"], ab, list(g8.TOADS) + list(COPIES))
        fr = fresh_terms(v["early"], ab)
        ent[i] = {"ab": hex(ab), "length": ra["entries"][i - 1]["length"], "t": ra["entries"][i - 1]["t"],
                  "left_t": ra["entries"][i - 1].get("left_t"), "reg": rg, "own_first": o1, "own_late": o2,
                  "list_first": l1, "list_late": l2, "behaviour": bh, "fresh": fr,
                  "identities": {k: {f: (hex(x) if isinstance(x, int) else x) for f, x in v["first"]["actors"][k].items()
                                     if f in ("so", "perso", "3ddata", "stdgame", "brain", "buffer", "std_personal")}
                                 for k in COPIES if k in v["first"]["actors"]},
                  "early_n": len(v["early"]), "samples_n": len(v["samples"]), "late_read": v["late"] is not None}
    det["entries"] = ent
    e1, e2 = ent[1], ent[2]
    L["L2_first_registration"] = bool(e1["length"] == AREA + N and e1["reg"][0] and e1["own_first"][0]
                                      and e1["own_late"][0])
    L["L3_first_guest_behaviour"] = bool(e1["behaviour"][0] and e1["list_first"][0] and e1["list_late"][0])
    ph, pc = ra["phases"], rb["phases"]
    D = {k: r3.diff(r3.brief(ph[k]), r3.brief(pc[k])) for k in ("menu_before", "e1", "e2", "fix_between", "menu_after")}
    want = {"area1_length": N, "free": -N, "largest": -N}
    fixb = r3.brief(ph["fix_between"])
    det["memory"] = {"D": D, "phases": {k: r3.brief(v) for k, v in ph.items() if isinstance(v, dict)},
                     "control_phases": {k: r3.brief(v) for k, v in pc.items() if isinstance(v, dict)}}
    E1, E2 = ra["entries"][0], ra["entries"][1]
    L["L4_first_unload"] = bool(E1.get("left_t") is not None and E1["left_t"] <= E2["t"] and fixb
                                and (ph["fix_between"] or {}).get("free_bytes") == FIX_ONLY_FREE
                                and fixb["alloc"] == 1 and fixb["free_chunks"] == 1
                                and mem_norm(ph["fix_between"]) == mem_norm(pc["fix_between"])
                                and D["menu_before"] == {} and D["e1"] == want and D["fix_between"] == {})
    passes = re.findall(r"G5P3 tx pass file=(\S+) pass=(\d+) reads_before=\d+ image_bytes=(\d+)", log)
    det["tx_passes"] = {f: sum(1 for x, _, _ in passes if x == f) for f, _ in SNAP}
    L["L5_second_activation"] = bool(
        ra["runner_exit"] == 0 and ra.get("process_left") is False and all(n >= 2 for n in det["tx_passes"].values())
        and all(b_ == snap_sizes.get(f) for f, _, b_ in passes) and len(tx) == 1 and len(snaps) == 3
        and "G5P3 tx host_changed" not in log
        and not re.search(r"M36 grow read file=(intro_10\.(lvl|ptr)|transit\.lvl)", log) and e2["length"] == AREA + N)
    L["L6_fresh_identities_state"] = bool(e2["reg"][0] and e2["own_first"][0] and e2["own_late"][0] and e2["fresh"][0]
                                          and all(e2["behaviour"][1]["oracle"][k]["a"] for k in COPIES))
    L["L7_second_guest_behaviour"] = bool(e2["behaviour"][0] and e2["list_first"][0] and e2["list_late"][0])
    st = ra["states"]
    i0 = next((i for i, x in enumerate(st) if "invalid" not in x), None)
    bad = [x for x in (st[i0 + 1:] if i0 is not None else []) if "invalid" in x]
    windows = [(e["t"], e.get("left_t") or 1e9) for e in ra["entries"][:2]]
    walk_ok = (i0 is not None and all(x["invalid"] == "changed" for x in bad) and len(bad) <= 2
               and not any(a <= x["t"] <= b_ for x in bad for a, b_ in windows))
    within = {"e1_eq_e2": mem_norm(ph["e1"]) == mem_norm(ph["e2"]),
              "menu_before_eq_after": mem_norm(ph["menu_before"]) == mem_norm(ph["menu_after"])}
    rj = ra["run_json"]
    prot = json.loads((WORK / tag / "protected.json").read_text())
    judges = {t: subprocess.run([sys.executable, str(TOOLS / t), "--run", ra["run"]], cwd=ROOT, capture_output=True,
                                text=True).returncode
              for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py")}
    fault = bool(re.search(r"access violation|engine error|[Ii]nvalid.*(indirect|function)|Unresolved indirect", log))
    det["safety"] = {"judges": judges, "fault_codes": [ra["fault_codes"], rb["fault_codes"]],
                     "fault_counts": [g6b.fault_counts(ra["run"]), g6b.fault_counts(rb["run"])],
                     "foreground": (rj.get("game_foreground_events"), rj.get("game_foreground_samples")),
                     "session_end": ra.get("session_end"), "marker_after": ra.get("marker_after"), "walk_bad": bad,
                     "within": within, "fault_line": fault, "process_detail": ra.get("process_detail")}
    L["L8_final_cleanup_safety"] = bool(
        D["e2"] == want and D["menu_after"] == {} and all(within.values()) and walk_ok
        and ra["controlled"] is True and (ra.get("session_end") or {}).get("cleared") is True
        and ra.get("marker_after") == "none" and not any(judges.values())
        and "M23 haptics policy=suppressed physical_pad_drivers=none" in log and ra["runner_exit"] == 0
        and ra.get("process_left") is False and rb.get("process_left") is False
        and rj.get("game_foreground_events") == 0 and rj.get("game_foreground_samples") == 0
        and set(ra["fault_codes"]) <= set(rb["fault_codes"]) | {"406D1388"} and not fault
        and prot["before"] == prot["after"])
    ok = all(L.values())
    res = {"invalid": [], "L": L, "verdict": "RELOAD VERIFIED" if ok else "NOT PASSED", "details": det}
    (WORK / f"judgement_reload_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({"L": L, "verdict": res["verdict"]}, indent=1))
    return 0 if ok else 1


def load_phase(tag, ph):
    w = WORK / tag / ph
    if not (w / "row.json").is_file():
        return None
    r = {n: json.loads((w / f"{n}.json").read_text()) for n in ("row", "live", "samples", "states")}
    r["early"] = json.loads((w / "early.json").read_text()) if (w / "early.json").is_file() else []
    run = r["row"]["run"]
    r["log"] = g6p3.load_log(run)
    mf = RUNS / run / "m2_faults.log"
    r["faults"] = sorted(set(re.findall(r"M2 exception code=([0-9A-Fa-f]+)", mf.read_text(errors="replace")))) \
        if mf.is_file() else []
    r["judges"] = {t: subprocess.run([sys.executable, str(TOOLS / t), "--run", run], cwd=ROOT, capture_output=True,
                                     text=True).returncode
                   for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py")}
    return r


def judge_recover(tag):
    setup()
    p4b.judge(tag)
    j = json.loads((WORK / f"judgement_{tag}.json").read_text())
    (WORK / f"judgement_{tag}.json").replace(WORK / f"judgement_{tag}_g5p4b.json")
    Rp, det = j["R"], {"g5p4b": j["details"]}
    ev = json.loads((WORK / tag / "evidence.json").read_text())
    evE = json.loads((WORK / tag / "evidence_E.json").read_text())
    chk = json.loads((WORK / "check.json").read_text())
    ra_tx = chk["details"]["O5"]["RA_tx"]
    A, C, E = (load_phase(tag, x) for x in ("A", "C", "E"))
    R = {}
    R["R1_clean_start"] = bool(not evE["RA_root_existed_before"] and not evE["RB_root_existed_before"]
                               and ev["A_plan"]["result"] == "ok" and sorted(ev["A_plan"]["active"] or [])
                               == sorted([MOD, "e478.lums-6"]) and not ev["A_plan"]["codes"]
                               and ev["RB_marker"]["before"] is None)
    mA = ev["marker_A"]["json"] or {}
    atext = (WORK / f"plan_{tag}_A.txt").read_text(encoding="utf-8")
    a_tx = [x for x in atext.splitlines() if x.startswith("level-tx")]
    alog = A["log"] if A else ""
    snaps = re.findall(r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", alog)
    o = j["details"].get("ordering", {})

    def ts(x):
        try:
            return datetime.fromisoformat(x) if x and x != "None" else None
        except ValueError:
            return None
    tm, tp_, tg = (ts(o.get(k)) for k in ("marker_mtime", "process_created", "first_grow_size"))
    want_tx = tuple(a_tx[0].split(" ")[2:5]) if a_tx else None
    R["R2_marker_preparation"] = bool(
        A and mA.get("session") == f"{PREFIX}_{tag}_A" and mA.get("mods") == [MOD] and mA.get("levels") == [LEVEL]
        and mA.get("plan_sha256") == ev["A_plan_sha256"] and a_tx == ra_tx and tm and tp_ and tg and tm < tp_ < tg
        and [tuple(x) for x in re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", alog)] == [want_tx]
        and len(re.findall(r"G6P1 level-tx version=2 members=lvl,ptr,transit", alog)) == 1
        and sorted((f, b_) for f, _, b_, _ in snaps) == SNAP)
    lvA, lvC = (A or {}).get("live") or {}, (C or {}).get("live") or {}
    ab = lvA.get("ab")
    kill_t = (A or {}).get("row", {}).get("kill_t")
    smA = [x for x in (A or {}).get("samples", []) if kill_t is None or x["t"] <= kill_t]
    if A and C and ab and lvC.get("ab"):
        rg, ow, li = reg_terms(lvA, lvC, ab), own_terms(lvA, ab), list_terms(lvA, lvC, ab)
        oa = {k: oracle(A["early"], smA, lvA, ab, k, min_window=0) for k in COPIES}
        eq = {k: stamps_equal(smA, k) for k in COPIES}
        inc = {k: sum(1 for x, y in zip(smA, smA[1:]) if k in x["a"] and k in y["a"]
                      and y["a"][k]["stamp"] > x["a"][k]["stamp"]) for k in COPIES}
        det["A"] = {"reg": rg, "own": ow, "list": li, "oracle": {k: v[1] for k, v in oa.items()}, "stamps": eq,
                    "stamp_increases": inc, "kill_t": kill_t, "samples_before_kill": len(smA)}
        R["R3_active_composition"] = bool(
            kill_t is not None and rg[0] and ow[0] and li[0] and all(v[1]["a"] and v[1]["b"] and v[1]["c"]
                                                                      for v in oa.values())
            and all(n and s >= 0.95 * n for s, n in eq.values()) and all(v >= 10 for v in inc.values()))
    else:
        R["R3_active_composition"] = False
    R["R4_verified_ownership"] = Rp["R1_session_ownership"]
    R["R5_forced_termination"] = Rp["R4_abnormal_termination"]
    R["R6_marker_persistence"] = Rp["R5_marker_persistence"]
    cl = C["log"] if C else ""
    ng = not_grown_terms(lvC, lvC["ab"]) if C and lvC.get("ab") else (False, {})
    det["C"] = {"not_grown": ng, "plan": ev["C_plan"]}
    R["R7_whole_transaction_refusal"] = bool(
        C and ev["C_plan"]["codes"] == {MOD: "STRUCTURAL_RECOVERY"} and ev["C_plan"]["structural_recovery"] == "armed"
        and not ev["C_plan"]["structural_marker"] and not ev["C_plan_has_tx"] and cl.count("M33 mods state=active") == 1
        and not re.search(r"G5P1|G5P3|G6P1|M36 grow", cl)
        and not re.search(r"M33 mods served mod=\S+ file=(transit\.lvl|intro_10\.ptr)", cl)
        and ev["marker_after_C"] == ev["marker_A"]["sha256"] and ng[0]
        and any(s.get("areas", {}).get("1", {}).get("length") == AREA for s in C["states"] if "invalid" not in s))
    R["R8_ordinary_mod_continuity"] = Rp["R7_nonstructural"]
    rbm = dict(ev["RB_marker"], after_E=evE["RB_marker_after_E"])
    R["R9_profile_isolation"] = bool(all(v is None for v in rbm.values()) and Rp["R8_profile_isolation"])
    det["RB_markers"] = rbm
    # R10 recovery completion
    elog = E["log"] if E else ""
    lvE = (E or {}).get("live") or {}
    mE = evE["marker_E"]["json"] or {}
    e_terms = {}
    if E and lvE.get("ab") and C:
        abE = lvE["ab"]
        e_terms = {"reg": reg_terms(lvE, lvC, abE), "own": own_terms(lvE, abE), "list": list_terms(lvE, lvC, abE),
                   "oracle_a": {k: oracle(E["early"], E["samples"], lvE, abE, k, min_window=0)[1]["a"] for k in COPIES}}

    def first15(r):
        st = [x for x in (r or {}).get("states", []) if "invalid" not in x and "areas" in x]
        x = next((s for s in st if s.get("areas", {}).get("1", {}).get("base") == hex(p4b.INTRO15_BASE)), None)
        return r3.brief(x) if x else None

    def fix_before15(r):
        st = [x for x in (r or {}).get("states", []) if "invalid" not in x and "areas" in x]
        k = next((i for i, s in enumerate(st) if s.get("areas", {}).get("1", {}).get("base") == hex(p4b.INTRO15_BASE)),
                 None)
        prev = [s for s in st[:k] if set(s["areas"]) == {"0"}] if k else []
        return prev[-1] if prev else None
    fE = fix_before15(E)
    s15 = {"E": first15(E), "C": first15(C)}
    comp = evE["E_complete"]
    det["E"] = {"terms": e_terms, "intro15": s15, "fix_before_intro15": r3.brief(fE), "complete": comp,
                "plan_tx": evE["E_plan_tx"], "faults": (E or {}).get("faults")}
    eE = [tuple(x) for x in re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", elog)]
    esn = re.findall(r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", elog)
    rjs = {k: (r or {}).get("row", {}).get("run_json") or {} for k, r in (("A", A), ("C", C), ("E", E))}
    safe = all(r and not any(r["judges"].values()) and not r["row"].get("process_left")
               and rjs[k].get("game_foreground_events") == 0 and rjs[k].get("game_foreground_samples") == 0
               and rjs[k].get("monitor_hook_ready") is True and rjs[k].get("monitor_stop_clean") is True
               and rjs[k].get("r3hd_foreground_events") == 0 for k, r in (("A", A), ("C", C), ("E", E)))
    det["safety"] = {"run_json": rjs, "judges": {k: (r or {}).get("judges") for k, r in (("A", A), ("C", C), ("E", E))},
                     "faults": {k: (r or {}).get("faults") for k, r in (("A", A), ("C", C), ("E", E))}}
    R["R10_recovery_completion_safety"] = bool(
        Rp["R9_explicit_recovery"] and E and mE.get("session") == f"{PREFIX}_{tag}_E"
        and mE.get("plan_sha256") == evE["E_plan_sha256"] and evE["E_plan_tx"] == a_tx and evE["marker_before_E"] is None
        and eE == [want_tx] and sorted((f, b_) for f, _, b_, _ in esn) == SNAP
        and e_terms and e_terms["reg"][0] and e_terms["own"][0] and e_terms["list"][0]
        and all(e_terms["oracle_a"].values())
        and fE is not None and fE.get("free_bytes") == FIX_ONLY_FREE and s15["E"] is not None and s15["E"] == s15["C"]
        and (comp.get("exit") or {}).get("controlled") is True and (comp.get("end") or {}).get("cleared") is True
        and evE["marker_after_E"] is None and Rp["R10_production_desktop"] and safe
        and E["row"].get("runner_exit") == 0 and C["row"].get("runner_exit") == 0
        and set(C["faults"]) <= {"406D1388"} and set(E["faults"]) <= {"406D1388"}
        and ev["protected_before"] == evE["protected_after_E"])
    invalid = j["invalid"]
    ok = not invalid and all(R.values())
    res = {"invalid": invalid, "R": R, "verdict": "RECOVERY VERIFIED" if ok else ("INVALID" if invalid else "NOT PASSED"),
           "g5p4b_judge": Rp, "details": det}
    (WORK / f"judgement_recover_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("invalid", "R", "verdict")}, indent=1, default=str))
    return 0 if ok else 1


def main():
    a = sys.argv[1:]
    ok_tag = len(a) == 2 and re.fullmatch(r"[A-Za-z0-9-]{1,24}", a[1])
    if a == ["check"]:
        return check()
    if ok_tag and a[0] in ("reload", "recover", "judge-reload", "judge-recover"):
        return {"reload": reload, "recover": recover, "judge-reload": judge_reload,
                "judge-recover": judge_recover}[a[0]](a[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
