#!/usr/bin/env python3
"""E-494 (D-261) G6-P8: runtime validation of G6-P7's fifth-actor prototype (one additional intro_10
NIN_m_ToadIntro, a copy of instance 1) and, only after its runtime gate passes, a typed `insert-toad-intro`.
Development-only; private; hidden. Outputs: private/work/e494/.

  g6p8_toad.py revalidate        Phase A: G6-P7 prototype re-built and re-checked (revalidate.json)
  g6p8_toad.py plan              Phase B: the prototype as a version-2 transaction through the compiler's own
                                 resolve pipeline (in-process private spec only; nothing in r3hd_mods knows it),
                                 compile-time negatives (plan.json)
  g6p8_toad.py observe TAG       Phase C: one hidden run of the UNMODIFIED level (production build): the four
                                 original Toads' AI state, then the Exit Game route
  g6p8_toad.py run TAG           Gate A: hidden runs A (no plan), B (prototype), C (B's plan, gate unset)
  g6p8_toad.py judge TAG         P1-P8
  g6p8_toad.py negtest           runtime transaction cases (dev 15 / production 2) for the prototype plan

PHASE A-C RESULTS (before the protocol; recorded, not judged here)
  revalidate PASS: images = G6-P7's (lvl be480d1a..., ptr aba64802..., transit 321de2e4...), deterministic, the
    independent simulator passes, 31 / 31 words supported provisional (14 owned, 14 shared, 1 other-file, 2 sibling
    links), Mind +0 / Intelligence +0 = the AI model 0x580C78 in instance 0's block; Intelligence +8 / +0xC / +0x14
    the model's behaviour records (shared), +0x10 / +0x18 the copy's own +0x350 / +0x358; no model object copied (the
    tail is exactly copy, personal element, name, SO record, backup record, backup copy); 40 entries (39 own-file, 1
    transit), 10 edited words, +1,444 / +320.
  plan PASS: one `level-tx 2 intro_10 g6p8.toad-prototype 36f245da186fe465`, images = the prototype's, id
    recomputed, deterministic; refused whole: gate unset / other level, wrong hashes, other instance, instance 0,
    other model, placement 0.5 off, two Toads, Toad + Frog, Toad mod + Frog mod (STRUCTURAL_CONFLICT), armed marker
    (STRUCTURAL_RECOVERY). negtest PASS (dev 15 / 15 incl. open orders, aliasing / partial / tamper / id / role /
    host-change refusals; production 2 / 2 unknown_record).
  observe x1, x2 (production build, unmodified, Exit Game at 85 s): ORIGINAL TOAD ORACLE. Each of the four original
    Toads is visited once by the AI scheduler at level start: the 3dData initializer leaves counter +343 = 0xFF and
    +344 = a random draw; the first visit wraps +343 to 0 and runs the AI once (+344 = draw + 1); in that one run its
    Intelligence goes from the file's (+8, +0xC) = (Init, Init) to (Jump, Wait) (records 0x580DA8 / 0x580EB4 of the
    shared model; +0x14 stays Init). After that the AI never runs again (+344 constant for 98 s, P = 1, counter 0,
    position constant): the model is idle by design in an inputless run. The engine still processes every Toad each
    frame: StdGame +0x14 (HYPOTHESIS: a per-frame visit stamp) increases by one per frame, equal for all four. All
    four in the dynamic world; x1 / x2 identical in pattern; Exit Game -> menumap at 106.6 s; fix only 20,795,836
    (1 / 1) between; menumap 13,274,536 free.

RUNTIME PROTOCOL (committed before the development build and before any modified run)
Build: g5p1_dev_gate.py apply (unchanged gate: intro_10 version 2 already allowed) + tools\\build_incremental.bat;
production restored afterwards (revert + rebuild). Runs: m9_license_run.py hidden, non-activating, muted, no physical
pad, private user root, `--test-level intro_10`, 150 s, no input except G6-P4's guest-scoped Exit Game sequence 85 s
after intro_10.lvl opened. Reads (read-only): block-8 snapshot at every area-table change; from the area's appearance
until the first read every 4 ms the tracked actors' 3dData +340..+347, Intelligence +8 / +0xC, Brain, StdGame (fixed
in-block live addresses); 6 s after the area appears a full read (chains, Mind, Intelligence, buffer word, personal
index, position, whole block, actor lists); then every 0.1 s per actor: position, Intelligence +8 / +0xC, 3dData
P / counter / AI runs, StdGame +0x14; a second full read 80 s after the area appeared. X(o) = area base + o - 4.
  A: no plan.  B: the prototype plan (mod g6p8.toad-prototype through resolve_all with the private spec, session =
  run, marker armed, R3HD_DEV_STRUCTURAL_TX=intro_10).  C: B's plan compiled the same way, the variable unset.
  (D omitted: B's Exit Game route proves cleanup.)
  Tracked: t0-t3 (the originals, file SuperObjects 0x580940 / 0x581268 / 0x581720 / 0x581BD8) and in B the copy
  (0x74E918). Oracle(actor) = (a) an early sample with counter 0xFF and Intelligence +8 = Init, and the first early
  sample with counter 0 shows AI runs = the previous value + 1 and (+8, +0xC) = (Jump, Wait); (b) at the first read
  Mind +0 = Intelligence +0 = X(0x580C78), (+8, +0xC, +0x14) = X(Jump, Wait, Init); (c) in every 0.1-s sample AI runs
  = (a)'s value, (+8, +0xC) = (Jump, Wait), P = 1, counter 0, one position; (d) the StdGame +0x14 stamp never
  decreases and rises by >= 50 x the window in seconds (nominal 60).
  P1 transaction: B one `M33 mods state=active`; `G5P1 level-tx active level=intro_10 mod=g6p8.toad-prototype
     id=<plan id>`; `G6P1 level-tx version=2 members=lvl,ptr,transit`; snapshots intro_10.lvl 7663280,
     intro_10.ptr 209388, transit.lvl 41508; grow 7661836 -> 7663280, 209068 -> 209388, 41508 -> 41508; served
     exactly the three; no host change. A `M33 mods=off`.
  P2 registration (first read): the copy X(0x74E918) alive, model NIN_m_ToadIntro; the world union (dynamic +
     inactive) = A's + exactly the copy, no duplicate, both walks' links consistent; in the dynamic world the copy
     right after the source X(0x581268); SO records A + 1, the copy's once and last; backup targets A's + X(copy +
     0xC4) once; personal types 70, last `XAP_ToadIntro_G6P7`; the copy's personal index 69, the source's 0x1D. A / C:
     69 types, A's union and records, no copy.
  P3 independent ownership (B, first and 80-s reads): the copy's Perso / 3dData / StdGame / Brain = X(copy + 0x80 /
     0xAC / 0x2B4 / 0x318), Brain +0 = X(copy + 0x324), Mind +4 = X(copy + 0x338), Intelligence +0x10 / +0x18 =
     X(copy + 0x350 / 0x358); Mind +0 = the source's = X(0x580C78); Mind +0xC = 0 in both; Brain +4 = 0xCDCDCDCD in
     both; the copy's 3dData buffer word (+0x14C) non-zero and different from all four originals'; no live word of
     the copy's block points into the source's block except +0x18 (= X(source)) and none of the source's into the
     copy's except +0x14 (= X(copy)); the source's personal index 0x1D.
  P4 guest initialization (B): the copy satisfies oracle (a) and (b): its own Init run under the scheduler, through
     the shared model's records.
  P5 guest behaviour (B, C): oracle (a)-(d) for the copy and the four originals in B, for the four in C; the copy's
     position = the source's.
  P6 integrity: both reads: walks' links consistent, no duplicate in the union, no list read error; the copy alive and
     once in the union at the 80-s read (B); no access violation / engine error line; fault codes within {406D1388}.
  P7 exit / cleanup: route taken in A, B, C (intro_10 -> menumap, area left); loaded B - A = {area 1 length +1,444,
     free -1,444, largest -1,444}, C - A = {}; block 8 between intro_10 and menumap fix only (20,795,836, 1 / 1) in
     all; menumap state equal to A's in B and C.
  P8 safety: C `state=refused reason=level_tx_not_enabled`, nothing served, no grow, no G5P1 / G5P3 / G6P1 line;
     every run M21 / M22 / M23 0, haptics policy line, runner exit 0, no game process naming the run left; B marker
     armed (session, plan SHA-256) and cleared after the controlled end; revalidate, plan, negtest passed first.
  Invalid (new tag, kept): process / area not found, a tracked actor unreadable at the first read, < 60 s of samples,
     A's originals failing the oracle, the route not taken in A.
  Stop: a guest fault, bad actor ownership / aliasing, registration corruption or a desktop-safety violation.
  Gate A: all eight = A-PASS; P2 + P3 with P4, P5 or P7 failing = A-PARTIAL; otherwise A-FAIL (a missing safe
  observation = A-BLOCKED, decided by hand and recorded).
RUN g1 (protocol 24c570c; judgement_g1.json kept): INVALID (A:oracle). Every original Toad in A met oracle (a)-(c)
  (one Init run: draw 6 / 4 / 11 / 6 -> 7 / 5 / 12 / 7, (Jump, Wait), then idle 98 s); (d) failed for all four: the
  stamp rose 340 -> 4693 = 44.5 per second, not >= 50. Incorrect assumption: (d) took StdGame +0x14 for a per-frame
  stamp from 6 s of early samples. Over the whole window it is the current frame number written in bursts (+60 per
  second for about 5 s, then constant for about 11 s, repeating: 668 at 14.2 s, 777 from 19.7 to 25.2 s, 1652 at
  30.6 s = 340 + 21.9 s x 60), identical for all four originals.
REVISION 1 (committed after g1, before g2; B and C of g1 not judged): oracle (d') = the stamp never decreases,
  increases in >= 50 samples and by >= 3,000 over the window (A g1: 4,353); P5 adds: in B the copy's stamp equals the
  source's in >= 95 % of the samples (both processed at the same frames). Everything else unchanged; g2 re-runs A, B,
  C with fresh tags.
RUN g2 (revision 1; judgement_g2.json kept): A-FAIL on P3 only (P1, P2, P4-P8 PASS; the copy: own chain, shared model,
  own buffer word, one Init run 11 -> 12 then idle, stamp = the source's in 893 / 895 samples). P3's cross-block term
  found the copy's +0x4B0 pointing into the source's block and the source's +0x4AC into the copy's. Incorrect
  assumption: P3 took the file's world links (+0x14 / +0x18) for the only cross-block words. The Toad block ends with
  a 16-byte element at +0x4A8 {owner SuperObject, next element, prev element, header}, all zero in the file and built
  by the guest at load (header in the level at file 0x2FE1A8; the list spans models: t1's prev is instance 0's
  element at +0x918, t3's next the red lum's at 0x549A30 + 0x4A8; HYPOTHESIS: a per-sector character list). In A the
  guest links t1 -> t2 -> t3; in B it inserted the copy's element between t1 and t2 with every pair reciprocal and the
  copy's owner word = X(copy). No pointer of the copy aliases the source's state.
REVISION 2 (committed after g2, before g3): the full reads also walk that list from the source's element (both
  directions, to 0). P3 allows exactly copy +0x4B0 (= X(source + 0x4A8)) and source +0x4AC (= X(copy + 0x4A8)) in
  addition to the world links, and requires at both reads: the walk reciprocal, every owner once, one header, ends 0
  / 0; the copy's element {X(copy), next, X(source element), the source's header} right after the source's; B's owner
  sequence = A's with X(copy) inserted after X(source). Everything else unchanged; g3 re-runs A, B, C.
RUN g3 (revision 2; recorded after the run): A-PASS, P1-P8 all true. Transaction id 36f245da186fe465 active, members
  7,663,280 / 209,388 / 41,508; the copy X(0x74E918) alive, union 66 -> 67, records 122 -> 123, backups 181 -> 182,
  personal 70 (`XAP_ToadIntro_G6P7`, index 69); own Perso / 3dData / Brain / Mind / Intelligence / buffer, shared
  model; list 20 -> 21 elements, the copy's right after the source's; the copy: draw 11 -> 12 (one Init run), (Jump,
  Wait), idle 97.7 s, stamp = the source's in 893 / 894 samples; loaded B - A = +1,444 area / -1,444 free / largest,
  C - A = {}; fix only 20,795,836 and menumap 13,274,536 in A / B / C; C refused, nothing served; safety clean.

GATE B (typed `insert-toad-intro`, D-261; implemented only after g3's A-PASS)
  g6p8_toad.py typed-check        I1-I7 offline (typed_check.json)
  g6p8_toad.py run-typed TAG      I8: one hidden run T (typed plan through the real compiler, session marker armed,
                                  R3HD_DEV_STRUCTURAL_TX=intro_10), same build, runner, reads and exit as Gate A
  g6p8_toad.py judge-typed g3 TAG I8 = revision 2's P1-P8 with T in B's place and g3's A / C as the matched controls
  typed-check (before the typed run): I1-I7 PASS (images = the prototype's and = g3 B's served plan, range for range;
  G6-P7's simulator; 14 / 14 / 1 / 1 / 1 classes; dev 15 / 15, prod 2 / 2; 23 refusals; G6-P5 compare; production
  header without transaction code).
  I8 PROTOCOL (committed before the typed run): I8-PASS = all of P1-P8 (revision 2, unchanged) with T as B: the typed
  plan's id active, the same sizes / served files / registration / ownership / list / one Init run / idle / stamp /
  +1,444 cleanup / safety and marker witnesses; g3's A and C stand as the control and the gate-off case (same
  development build, no rebuild between). Anything else = I8-FAIL (named); invalid as Gate A (new tag).
"""
import contextlib
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
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
import g6p3_pilot as g6p3  # noqa: E402  (lists, safety, load_log)
import g6p4_pilot as g6p4  # noqa: E402  (exit_steps)
import g6p7_fifth_actor as g7  # noqa: E402

PREFIX = "e494"
WORK = ROOT / "private" / "work" / PREFIX
LEVEL, ENV = "intro_10", rm.STRUCT_ENV
GAME, RUNS = g3a.GAME, g3a.RUNS
SIZE, PSIZE, TSIZE = 7661836, 209068, 41508
N_LVL, N_PTR = 1444, 320
LVL_SHA = "a37638bf1370357db21f33df5c4d37ae806b3c4b9f81b331503ba62d1b19e2ee"
PTR_SHA = "6c9dd70c488a1cac95efc0a55a6086255dae2d851bacd93f5abefdcc8200e940"
TRANSIT_SHA = "d300ba3a4a3c03cec6a73eb9da8a8d820fcc3a669591e976b357e804315bf275"
TOAD = "Toad\\NIN_m_ToadIntro\\NIN_m_ToadIntro.rul^CreateIntelligence^CreateComport:NIN_C_ToadInit"
TOADS = {"t0": 0x580940, "t1": 0x581268, "t2": 0x581720, "t3": 0x581BD8}   # file SuperObjects, file order
SRC, COPY, BLK = 0x581268, 0x74E918, 0x4B8
AI_MODEL = 0x580C78                                   # in instance 0's block (+0x338)
CHAIN = {"perso": 0x80, "3ddata": 0xAC, "stdgame": 0x2B4, "brain": 0x318, "mind": 0x324, "intel": 0x338}
TIMER = 0x82C0628C                                    # engine timer word (ms), guest address
ELEM = 0x4A8                                          # revision 2: the guest-built list element in the block
INTEL_OFF = {"t0": 0x7A8}                              # instance 0's Intelligence (its block holds the model)
BUFFER = 0x14C                                        # the 3dData buffer word (0 in the file, set at init)
PROTO = {"lvl": "be480d1a64b358924d2a2ea2c97e321add1082b93dd02506a039996a517c3d5a",
         "ptr": "aba6480254be610581fb967e9959c5e192cf7dbf91e5f0af12b19bbcb9c87571",
         "transit": "321de2e4be2077720e8a6cc6660ff373bcabaed6c5089989a1ed594aa370c34e"}
NEW_NAME = "XAP_ToadIntro_G6P7"
MOD = "g6p8.toad-prototype"
RUN_SECONDS, EXIT_AFTER, END_READ, FIRST_READ = 150, 85, 80, 6
sha = lambda b: hashlib.sha256(b).hexdigest()   # noqa: E731


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def gate_status():
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    return st.stdout.strip()


# --- the hidden runner ------------------------------------------------------------------------------------------------

def toad_state(p, so):
    """One read-only snapshot of an actor's identity chain (live addresses)."""
    from m5_live import Actor
    a = Actor(p, so)
    pw = p.words(a.perso, 4)
    st = {"so": so, "alive": a.alive(), "model": a.model, "perso": a.perso, "3ddata": pw[0], "stdgame": pw[1],
          "dynam": pw[2], "brain": pw[3], "matrix": a.matrix}
    st["brain_words"] = list(p.words(pw[3], 2)) if pw[3] else None
    st["mind"] = list(a.mind) if a.mind else None
    if a.mind:
        st["intel_words"] = list(p.words(a.mind[1], 8))
        st["model_words"] = list(p.words(a.mind[0], 4))
    st["buffer"] = p.words(so + BUFFER, 1)[0]
    st["std_personal"] = p.words(pw[1] + 8, 1)[0]
    st["position"] = list(a.position())
    blk = p.read(so, BLK)
    st["block_words"] = list(struct.unpack(f">{BLK // 4}I", blk)) if blk else None
    return st


def element_list(p, start):
    """Revision 2: the guest-built doubly-linked list whose 16-byte elements {owner SuperObject, next, prev, header}
    end the Toad blocks (+0x4A8; zero in the file). Walked from the source's element both ways; read-only."""
    def el(a):
        w = p.words(a, 4)
        return {"at": a, "owner": w[0], "next": w[1], "prev": w[2], "header": w[3]}
    try:
        fwd, seen, x = [], set(), start
        while x and x not in seen and len(fwd) < 2000:
            seen.add(x)
            fwd.append(el(x))
            x = fwd[-1]["next"]
        back, x = [], fwd[0]["prev"] if fwd else 0
        while x and x not in seen and len(back) < 2000:
            seen.add(x)
            back.append(el(x))
            x = back[-1]["prev"]
        chain = list(reversed(back)) + fwd
        hdr = chain[0]["header"] if chain else 0
        return {"chain": chain, "header": hdr, "header_words": list(p.words(hdr, 4)) if hdr else None,
                "ends": [chain[0]["prev"], chain[-1]["next"]] if chain else None}
    except Exception as x:
        return {"error": repr(x)}


def run_case(tag, case, plan=None, env_level=None, session_paths=None, copy=False, seconds=RUN_SECONDS,
             exit_after=EXIT_AFTER, sample_hook=None):
    """One hidden intro_10 run (m9_license_run.py: hidden, non-activating, muted, no physical pad, private user root).
    Tracked: the four original Toads and, if `copy`, the copy (file SuperObject COPY). Every 0.1 s per actor: alive,
    position, Intelligence +8 (current behaviour record), 3dData +340..+347 (P, counter, AI runs u16, ...).
    G6-P11 (D-264): `sample_hook(p, area base)` (default None: nothing changes) adds one read-only dict per sample
    under "x" (the Lum generator's variable 5 and position)."""
    from m5_live import Process
    work = WORK / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_E465_TEST_GROW", "R3HD_G3A_TEST_GROW", ENV):
        env.pop(k, None)
    row = {"case": case, "run": run, "marker_before_start": ["none", None]}
    if plan is not None:
        shutil.copyfile(plan, work / "plan_copy.txt")
        row["plan_sha256"] = sha(Path(plan).read_bytes())
        env["R3HD_MODS_PLAN"] = str(plan)
        if session_paths is not None:
            row["marker_before_start"] = rm.read_structural_marker(session_paths)
    if env_level:
        env[ENV] = env_level
    tracked = dict(TOADS)
    if copy:
        tracked["copy"] = COPY
    row["tracked"] = dict(tracked)
    (work / "steps.txt").write_text("\n".join(g6p4.exit_steps(exit_after)) + "\n", encoding="ascii")
    states, samples, live, names, early = [], [], {}, {}, []
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(seconds), "--play", "--test-level", LEVEL,
                                 "--user-root", run], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        t0 = time.monotonic()
        base = pid = None
        while time.monotonic() < t0 + 60 and game.poll() is None and (base is None or pid is None):
            lp_, pj = RUNS / run / "runtime.log", RUNS / run / "process.json"
            if base is None and lp_.is_file():
                mm = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", lp_.read_text(errors="replace"))
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
            last, t_end, area_t, ab, aend, chains, nxt = "none", t0 + seconds - 5, None, None, None, None, 0.0
            nxt_e = 0.0

            def read_all(ab_):
                r = {"t": round(time.monotonic() - t0, 3), "ab": ab_, "actors": {}}
                for label, off in tracked.items():
                    try:
                        r["actors"][label] = toad_state(p, ab_ + off - 4)
                    except Exception as x:
                        r["actors"][label] = {"error": repr(x)}
                r["lists"] = g6p3.lists(p)
                r["elist"] = element_list(p, ab_ + SRC + ELEM - 4)
                return r

            def name_of(rec):
                if rec not in names:
                    try:
                        w = p.words(rec, 3)
                        names[rec] = p.cstr(w[2]).rsplit(":", 1)[-1] if w and w[2] else None
                    except Exception:
                        names[rec] = None
                return names[rec]
            while time.monotonic() < t_end and p.running():
                ar = bp.areas(p)
                key = json.dumps({k: (v["base"], v["end"]) for k, v in (ar or {}).items()})
                if ar is not None and key != last:
                    last = key
                    s = bp.snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="areas_changed", area_keys=sorted(ar))
                    states.append(s)
                    if ar.get(1) and area_t is None:
                        area_t, ab, aend = time.monotonic(), ar[1]["base"], ar[1]["end"]
                    elif area_t is not None and "level_change_t" not in row and \
                            (not ar.get(1) or (ar[1]["base"], ar[1]["end"]) != (ab, aend)):
                        row["level_change_t"] = round(time.monotonic() - t0, 3)
                        chains = {}
                if area_t is not None and chains is None and nxt_e <= time.monotonic() < area_t + FIRST_READ:
                    # early phase (area appeared, before the first full read): fixed in-block live addresses only
                    e = {"t": round(time.monotonic() - t0, 4)}
                    try:
                        e["timer"] = p.words(TIMER, 1)[0]
                    except Exception:
                        e["timer"] = None
                    for label, off in tracked.items():
                        X = ab + off - 4
                        io = INTEL_OFF.get(label, CHAIN["intel"])
                        try:
                            sb = p.read(X + CHAIN["3ddata"] + 340, 8)
                            iw = p.words(X + io + 8, 2)
                            bw = p.words(X + CHAIN["brain"], 4)
                            e[label] = {"P": sb[2], "ctr": sb[3], "runs": struct.unpack_from(">H", sb, 4)[0],
                                        "beh": iw[0], "prev": iw[1], "brain": list(bw),
                                        "std": p.read(X + CHAIN["stdgame"], 0x30).hex()}
                        except Exception as x:
                            e[label] = {"error": type(x).__name__}
                    early.append(e)
                    nxt_e = time.monotonic() + 0.004
                if area_t is not None and chains is None and time.monotonic() >= area_t + FIRST_READ:
                    live["first"] = read_all(ab)
                    chains = {}
                    for label, st in live["first"]["actors"].items():
                        if "error" not in st and st.get("mind"):
                            chains[label] = (st["so"], st["matrix"], st["mind"][1], st["3ddata"])
                if area_t is not None and "end" not in live and "level_change_t" not in row and \
                        time.monotonic() >= area_t + END_READ:
                    live["end"] = read_all(ab)
                now = time.monotonic()
                if chains and now >= nxt:
                    smp = {"t": round(now - t0, 3), "a": {}}
                    for label, (so, mx, intel, d3) in list(chains.items()):
                        try:
                            s2 = p.words(so, 2)
                            m = p.read(mx + 0x34, 12)
                            beh, prev = p.words(intel + 8, 2)
                            stamp = p.words(so + CHAIN["stdgame"] + 0x14, 1)[0]
                            sb = p.read(d3 + 340, 8)
                            smp["a"][label] = {"pos": list(struct.unpack(">3f", m)), "beh": beh,
                                               "name": name_of(beh) if beh else None, "P": sb[2], "ctr": sb[3],
                                               "runs": struct.unpack_from(">H", sb, 4)[0], "so0": s2[0],
                                               "prev": prev, "stamp": stamp}
                        except Exception as x:
                            row.setdefault("sampling_stopped", {})[label] = type(x).__name__
                            chains.pop(label)
                    if sample_hook is not None:
                        smp["x"] = sample_hook(p, ab)
                    samples.append(smp)
                    nxt = now + 0.1
                time.sleep(0.005)
            if p.running() and ab is not None:
                if "level_change_t" not in row and "end" not in live:
                    live["end"] = read_all(ab)
                s = bp.snapshot(p)
                s.update(t=round(time.monotonic() - t0, 3), state="final", area_keys=sorted(bp.areas(p) or {}))
                states.append(s)
        game.wait(timeout=seconds + 240)
        row["runner_exit"] = game.returncode
    left, detail = g3a.game_left(pid, run) if pid else (False, {"pid": None})
    row["game_left"], row["game_left_detail"] = left, detail
    controlled = row["runner_exit"] == 0 and not (RUNS / run / "r3hd_crash.txt").exists()
    row["controlled"] = controlled
    if session_paths is not None:
        if row["marker_before_start"][0] == "armed":
            row["session_end"] = rm.end_structural_session(session_paths, run, row["plan_sha256"], controlled)
        row["marker_after"] = rm.read_structural_marker(session_paths)[0]
    row["names"] = {f"{k:#x}": v for k, v in names.items()}
    for name, obj in (("states", states), ("samples", samples), ("live", live), ("early", early), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1, default=str) + "\n")
    return row


# --- Phase C: the original Toads (production build, no plan) ----------------------------------------------------------

def summarize(tag, case):
    """Per tracked actor: behaviour names seen and transitions, AI runs (first, last, increments), P values,
    distance travelled, sample count; plus the level route and safety."""
    w = WORK / tag / case
    row = json.loads((w / "row.json").read_text())
    samples = json.loads((w / "samples.json").read_text())
    out = {"run": row["run"], "level_change_t": row.get("level_change_t"), "n_samples": len(samples),
           "window_s": round(samples[-1]["t"] - samples[0]["t"], 1) if samples else 0, "actors": {}}
    for label in row["tracked"]:
        seq = [s["a"][label] for s in samples if label in s["a"]]
        if not seq:
            out["actors"][label] = {"n": 0}
            continue
        trans, prev = [], None
        for s, smp in zip(seq, [s for s in samples if label in s["a"]]):
            if s["name"] != prev:
                trans.append((smp["t"], s["name"]))
                prev = s["name"]
        runs = [s["runs"] for s in seq]
        inc = sum(1 for a, b in zip(runs, runs[1:]) if b != a)
        dist = sum(sum((x - y) ** 2 for x, y in zip(a["pos"], b["pos"])) ** 0.5 for a, b in zip(seq, seq[1:]))
        out["actors"][label] = {"n": len(seq), "names": sorted({s["name"] for s in seq if s["name"]}),
                                "transitions": len(trans) - 1, "first_transitions": trans[:12],
                                "runs_first": runs[0], "runs_last": runs[-1], "runs_changes": inc,
                                "P": sorted({s["P"] for s in seq}), "distance": round(dist, 3),
                                "pos_first": seq[0]["pos"], "pos_last": seq[-1]["pos"]}
    log = g6p3.load_log(row["run"])
    out["lvl_opens"] = [o.rsplit("\\", 1)[-1].lower() for o in
                        re.findall(r"vfs_open path=(\S+?\.lvl) result=00000000", log)]
    out["safe"], out["safety"] = g6p3.safety(row)
    states = json.loads((w / "states.json").read_text())
    out["states"] = [(x["t"], sorted(x.get("areas", {})), x.get("free_bytes"), x.get("allocated_chunks"),
                      x.get("free_chunks")) for x in states]
    live = json.loads((w / "live.json").read_text())
    if live.get("first"):
        lf = live["first"]["lists"]
        out["lists_first"] = {k: (lf[k]["count"], len(lf[k]["walk"])) for k in ("dw", "inactive") if k in lf}
        out["toads_in"] = {lab: ("dw" if st.get("so") in lf.get("dw", {}).get("walk", []) else
                                 "inactive" if st.get("so") in lf.get("inactive", {}).get("walk", []) else "none")
                           for lab, st in live["first"]["actors"].items()}
    return out


def observe(tag):
    if gate_status() != "production":
        raise SystemExit("the observation runs on the production build (gate status must be production)")
    run_case(tag, "X")
    res = summarize(tag, "X")
    (WORK / f"observe_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1, default=str)[:6000])
    return 0


# --- Phase A: revalidate G6-P7's offline prototype ---------------------------------------------------------------------

def files():
    d = GAME / "GAMEDATAbin" / LEVEL
    return (d / f"{LEVEL}.lvl").read_bytes(), (d / f"{LEVEL}.ptr").read_bytes(), (d / "transit.lvl").read_bytes()


def revalidate():
    """A1-A9 of the brief's Phase A on the exact files; G6-P7's own functions re-run into WORK/g6p7_rerun (the
    committed E-493 outputs are not touched)."""
    WORK.mkdir(parents=True, exist_ok=True)
    g7.WORK = WORK / "g6p7_rerun"
    lvl, ptr, tl = files()
    r = {"resources": {"lvl": sha(lvl) == LVL_SHA and len(lvl) == SIZE, "ptr": sha(ptr) == PTR_SHA and len(ptr) == PSIZE,
                       "transit": sha(tl) == TRANSIT_SHA and len(tl) == TSIZE}}
    r["prototype_rc"] = g7.prototype()
    r["dossier_rc"] = g7.dossier()
    pj = json.loads((g7.WORK / "toad_prototype.json").read_text())
    dj = json.loads((g7.WORK / "toad_dossier.json").read_text())
    nl, np_, nt = ((g7.WORK / f"toad_prototype.{k}.bin").read_bytes() for k in ("lvl", "ptr", "transit"))
    r["hashes_equal_g6p7"] = pj["hashes"] == PROTO and {k: sha(b) for k, b in
                                                         (("lvl", nl), ("ptr", np_), ("transit", nt))} == PROTO
    r["deterministic"] = pj["deterministic"]
    r["simulator"] = {k: v for k, v in pj["simulator"].items() if k != "details"}
    rows = dj["rows"]
    kinds = {}
    for x in rows:
        kinds[x["census"]] = kinds.get(x["census"], 0) + 1
    r["classes"] = {"rows": len(rows), "supported": sum(x["status"] == "supported provisional" for x in rows),
                    "unknown": sum(x["status"] == "UNKNOWN" for x in rows),
                    "conflicting": sum(x["status"] == "CONFLICTING" for x in rows), "by_class": kinds}
    # owned vs shared model pointers, file level (the loader adds the area base to own-file slots)
    n0, n = u32(ptr, 0), u32(np_, 0)
    old = {u32(ptr, 8 + 8 * i) + 4: struct.unpack_from(">i", ptr, 4 + 8 * i)[0] for i in range(n0)}
    new = {u32(np_, 8 + 8 * i) + 4: struct.unpack_from(">i", np_, 4 + 8 * i)[0] for i in range(n)}
    me = old[SRC + 4]
    t = lambda b, o: u32(b, o) + 4          # noqa: E731  (file offset a relocated own-file word names)
    C = COPY
    ch = {"perso": t(nl, C + 4), "3ddata": t(nl, t(nl, C + 4)), "stdgame": t(nl, t(nl, C + 4) + 4),
          "brain": t(nl, t(nl, C + 4) + 0xC)}
    ch["mind"] = t(nl, ch["brain"])
    ch["intel"] = t(nl, ch["mind"] + 4)
    own = {k: ch[k] - C == CHAIN[k] for k in CHAIN}
    intel = [t(nl, ch["intel"] + q) if ch["intel"] + q in new else None for q in range(0, 0x1C, 4)]
    src_intel = [t(lvl, SRC + CHAIN["intel"] + q) if SRC + CHAIN["intel"] + q in old else None
                 for q in range(0, 0x1C, 4)]
    r["model"] = {
        "chain_own_block_offsets": own,
        "mind_model_shared": t(nl, ch["mind"]) == AI_MODEL == t(lvl, SRC + CHAIN["mind"]),
        "model_in_instance0_block": TOADS["t0"] <= AI_MODEL < TOADS["t1"],
        "intel_model": intel[0] == AI_MODEL,
        "intel_behaviours_shared": all(intel[q // 4] == src_intel[q // 4] and TOADS["t0"] <= intel[q // 4] < TOADS["t1"]
                                       for q in (8, 0xC, 0x14) if src_intel[q // 4] is not None),
        "intel_local_owned": all(intel[q // 4] == src_intel[q // 4] - SRC + C for q in (0x10, 0x18)
                                 if src_intel[q // 4] is not None),
        "intel_words": {f"+{q:#x}": [hex(intel[q // 4]) if intel[q // 4] else None,
                                     hex(src_intel[q // 4]) if src_intel[q // 4] else None] for q in range(0, 0x1C, 4)},
        "dsgmem_absent": u32(nl, ch["mind"] + 0xC) == 0 and u32(lvl, SRC + CHAIN["mind"] + 0xC) == 0,
        "brain4_equal": nl[ch["brain"] + 4:ch["brain"] + 8] == lvl[SRC + CHAIN["brain"] + 4:SRC + CHAIN["brain"] + 8],
        "transit_parent_other_file": new.get(C + 0x1C) == old.get(SRC + 0x1C) != me
        and nl[C + 0x1C:C + 0x20] == lvl[SRC + 0x1C:SRC + 0x20],
        "buffer_word_zero": u32(nl, C + BUFFER) == 0,
    }
    # never a silent copy of the embedded model: the tail is exactly the six planned objects (zero padding between
    # them), the copy comes from instance 1's block only, and every decoded object of the model (the AI model record,
    # the behaviour-list header, the behaviours' script arrays) lies in instance 0's block, before the source
    ob = pj["objects"]
    spans = sorted([(ob["copy"], BLK), (ob["personal"], rm.ACTOR_PERSONAL), (ob["name"], ob["record"] - ob["name"]),
                    (ob["record"], rm.ACTOR_RECORD), (ob["backup"], rm.ACTOR_BACKUP),
                    (ob["backup_copy"], rm.ACTOR_BACKUP_DATA)])
    gaps, pos_ = [], SIZE
    for a, ln in spans:
        gaps.append(nl[pos_:a])
        pos_ = a + ln
    gaps.append(nl[pos_:])
    L_, ix, key, insts = g7.toad_inputs()
    mobj = [AI_MODEL] + [h for h, nm in ix["headers"].items() if key in nm] + \
        [a for nm, lst in ix["behaviours"].items() if nm.startswith(key.rsplit(":", 1)[0]) for a, _ in lst]
    r["model"]["tail_is_planned_objects"] = all(not any(g_) for g_ in gaps) and spans[0][0] - SIZE < 16 \
        and len(nl) - pos_ < 16
    r["model"]["model_objects_in_instance0_block"] = [hex(x) for x in mobj]
    r["model"]["model_bytes_not_copied"] = all(TOADS["t0"] <= x < SRC for x in mobj) and len(mobj) >= 5
    r["model"]["copy_from_instance1_only"] = all(
        nl[C + k:C + k + 4] == lvl[SRC + k:SRC + k + 4] for k in range(0, BLK, 4)
        if SRC + k not in old and k != 0x2BC and not any(q <= k < q + 12 for q in (0xF8, 0x294, 0x498)))
    # relocations and edits
    newslots = sorted(set(new) - set(old))
    objs = pj["objects"]
    r["relocation"] = {"entries": n - n0, "unique": len(new) == n, "originals_kept": np_[4:4 + 8 * n0] == ptr[4:4 + 8 * n0],
                       "cross_file_table_kept": np_[4 + 8 * n:] == ptr[4 + 8 * n0:],
                       "own_file": sum(1 for s_ in newslots if new[s_] == me),
                       "other_file": [hex(s_) for s_ in newslots if new[s_] != me],
                       }
    changed = [o for o in range(0, SIZE, 4) if nl[o:o + 4] != lvl[o:o + 4]]
    r["relocation"]["outside_tail_only_edited_list_ends"] = [hex(s_) for s_ in newslots if s_ < SIZE]
    r["relocation"]["all_new_in_tail_or_edited"] = all(s_ >= SIZE or s_ in changed for s_ in newslots)
    r["edits"] = {"labels": pj["edits"], "changed_original_words": [hex(o) for o in changed],
                  "ten": len(changed) == 10 == len(pj["edits"])}
    r["registration"] = {k: r["simulator"].get(k) for k in ("world", "records", "backup", "personal")}
    r["growth"] = {"lvl": len(nl) - SIZE, "ptr": len(np_) - PSIZE, "transit_same_size": len(nt) == TSIZE,
                   "expected": [N_LVL, N_PTR], "budget": pj["budget"]}
    r["pass"] = (all(r["resources"].values()) and r["prototype_rc"] == 0 and r["dossier_rc"] == 0
                 and r["hashes_equal_g6p7"] and r["deterministic"] and r["simulator"]["pass"]
                 and r["classes"] == {"rows": 31, "supported": 31, "unknown": 0, "conflicting": 0,
                                      "by_class": r["classes"]["by_class"]}
                 and all(v for k, v in r["model"].items() if isinstance(v, bool)) and all(own.values())
                 and r["relocation"]["entries"] == 40 and r["relocation"]["unique"]
                 and r["relocation"]["originals_kept"] and r["relocation"]["cross_file_table_kept"]
                 and r["relocation"]["all_new_in_tail_or_edited"] and r["relocation"]["own_file"] == 39
                 and r["edits"]["ten"] and all(r["registration"].values())
                 and [r["growth"]["lvl"], r["growth"]["ptr"]] == [N_LVL, N_PTR] and r["growth"]["transit_same_size"])
    (WORK / "revalidate.json").write_text(json.dumps(r, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in r.items() if k not in ("growth",)}, indent=1, default=str)[:5000])
    print("REVALIDATE_G6P8", "PASS" if r["pass"] else "FAIL")
    return 0 if r["pass"] else 1


# --- Phase B: the prototype as a private version-2 transaction ---------------------------------------------------------

@contextlib.contextmanager
def private_spec():
    """In THIS process only: G6-P1's verified lum recipe (compile_insert_passive_lum and everything behind it: exact
    hashes, source checks, build, simulator, actor_transaction, resolve_all, plan, marker) is pointed at the Toad by
    swapping its allow-list entry for G6-P7's private Toad spec. Nothing is written to r3hd_mods; the original entry
    is restored on exit."""
    L, ix, key, insts = g7.toad_inputs()
    spec = g7.toad_spec(key, insts, L["data"]["lvl"])
    old = rm.LUM_ALLOW[LEVEL]
    rm.LUM_ALLOW[LEVEL] = spec
    try:
        yield spec
    finally:
        rm.LUM_ALLOW[LEVEL] = old


def toad_op(**kw):
    lvl, ptr, tl = files()
    pos = struct.unpack_from(">3f", lvl, SRC + 0xC4 + 0x34)
    o = {"type": "insert-passive-lum", "level": LEVEL, "model": TOAD, "instance": 1, "lvl_sha256": sha(lvl),
         "ptr_sha256": sha(ptr), "transit_sha256": sha(tl), "position": list(pos)}
    o.update(kw)
    return o


def compile_proto(name, mods, session=None, env=LEVEL):
    """resolve_all over freshly installed mods with the private spec in effect. Returns (result, plan text, paths)."""
    p1.WORK = WORK
    paths = p1.fresh(name)
    with private_spec(), p1.dev_env(env):
        for mid, ov in mods:
            try:
                p1.install(paths, mid, ov)
            except rm.Refusal as x:
                return {"import_refused": [mid, x.code, x.detail], "active": [], "mods": []}, None, paths
        res = rm.resolve_all(paths, write_plan=paths["cache"], session=session)
    plan = paths["cache"] / rm.PLAN_NAME
    return res, (plan.read_text(encoding="utf-8") if plan.is_file() else None), paths


def plan_images(text):
    """The guest images a plan describes (originals + its ranges), by member role."""
    m = p1.parse_plan(text)
    out = {}
    for f in m["files"]:
        data = bytearray(Path(f["path"]).read_bytes())
        for r in f["range"]:
            off, length, _, _, _, blob = r.split(" ", 5)
            b = Path(blob).read_bytes()
            off = int(off)
            if off + len(b) > len(data):
                data += bytes(off + len(b) - len(data))
            data[off:off + len(b)] = b
        out[{f"{LEVEL}.lvl": "lvl", f"{LEVEL}.ptr": "ptr", "transit.lvl": "transit"}[Path(f["path"]).name]] = bytes(data)
    return m, out


def plan():
    """Phase B (compile side): the prototype transaction through resolve_all; plan structure, identity, determinism
    and compile-time refusals. The runtime-side cases are `negtest`."""
    WORK.mkdir(parents=True, exist_ok=True)
    r = {}
    res, text, paths = compile_proto("plan_valid", [(MOD, [toad_op()])])
    r["active"] = res["active"]
    m, imgs = plan_images(text)
    txs = m["txs"]
    r["txs"] = txs
    tx_files = [x for f in m["files"] for x in f["tx"]]
    r["images_equal_prototype"] = {k: sha(b) == PROTO[k] for k, b in imgs.items()}
    r["sizes"] = {k: len(b) for k, b in imgs.items()}
    members = []
    for f in m["files"]:
        role = {f"{LEVEL}.lvl": "lvl", f"{LEVEL}.ptr": "ptr", "transit.lvl": "transit"}[Path(f["path"]).name]
        orig = Path(f["path"]).read_bytes()
        members.append((role, Path(f["path"]).name, len(orig), sha(orig), len(imgs[role]), sha(imgs[role])))
    want_id = rm.tx_id(LEVEL, MOD, sorted(members), 2)
    r["tx_id_recomputed"] = txs == [f"level-tx 2 {LEVEL} {MOD} {want_id}"]
    r["records"] = {"level-tx": len(txs), "tx-file": len(tx_files), "files": len(m["files"]),
                    "grow": sum(1 for f in m["files"] if f.get("grow")),
                    "ranges": {Path(f["path"]).name: len(f["range"]) for f in m["files"]}}
    r["gameplay"] = m.get("gameplay")
    res2, text2, _ = compile_proto("plan_again", [(MOD, [toad_op()])])
    strip = lambda s: "\n".join(x for x in s.splitlines() if not x.startswith("# written by")    # noqa: E731
                                and not x.startswith("range "))
    r["deterministic"] = strip(text) == strip(text2) and plan_images(text2)[1] == imgs
    shutil.copyfile(paths["cache"] / rm.PLAN_NAME, WORK / "plan_prototype.txt")
    # compile-time refusals (whole mod, nothing in the plan)
    lvl, ptr, tl = files()
    frog = {"type": "insert-scripted-frog", "level": LEVEL, "model": rm.FROG10, "instance": 2, "lvl_sha256": sha(lvl),
            "ptr_sha256": sha(ptr), "transit_sha256": sha(tl), "placement": "at_source", "period_ms": 500}

    def outcome(name, mods, env=LEVEL):
        res_, text_, _ = compile_proto(f"neg_{name}", mods, env=env)
        if "import_refused" in res_:
            return {"import": res_["import_refused"][1], "plan": text_ is not None and "level-tx" in (text_ or "")}
        return {"codes": {x["id"]: x.get("code") for x in res_["mods"]}, "active": res_["active"],
                "plan": text_ is not None and "level-tx" in (text_ or "")}
    neg = {
        "gate unset": outcome("gate_unset", [(MOD, [toad_op()])], env=None),
        "gate for another level": outcome("gate_other", [(MOD, [toad_op()])], env="intro_20"),
        "wrong lvl hash": outcome("wrong_lvl", [(MOD, [toad_op(lvl_sha256="0" * 64)])]),
        "wrong transit hash": outcome("wrong_transit", [(MOD, [toad_op(transit_sha256="1" * 64)])]),
        "other instance (2)": outcome("inst2", [(MOD, [toad_op(instance=2)])]),
        "instance 0 (embeds the model)": outcome("inst0", [(MOD, [toad_op(instance=0)])]),
        "other model": outcome("model", [(MOD, [toad_op(model=rm.LUM10)])]),
        "placement 0.5 from the source": outcome("place", [(MOD, [toad_op(position=[toad_op()["position"][0] + 0.5,
                                                                              *toad_op()["position"][1:]])])]),
        "two Toads in one mod": outcome("two", [(MOD, [toad_op(), toad_op()])]),
        "Toad + Frog in one mod": outcome("withfrog", [(MOD, [toad_op(), frog])]),
        "Toad mod + Frog mod (one level)": outcome("twomods", [(MOD, [toad_op()]), ("g6p8.frog", [frog])]),
    }
    r["negatives"] = neg
    ok_neg = all(not v["plan"] and (v.get("import") or (not v["active"] and all(v["codes"].values())))
                 for v in neg.values())
    r["negatives_pass"] = ok_neg
    # the recovery protection: an armed marker from an unfinished session turns the structural mod off
    res3, text3, paths3 = compile_proto("recovery", [(MOD, [toad_op()])], session="g6p8-recovery-probe")
    marker = rm.read_structural_marker(paths3)[0]
    with private_spec(), p1.dev_env(LEVEL):
        res4 = rm.resolve_all(paths3, write_plan=paths3["cache"], session="g6p8-recovery-probe-2")
    r["recovery"] = {"armed_after_first": marker, "second_codes": {x["id"]: x.get("code") for x in res4["mods"]},
                     "second_active": res4["active"]}
    r["recovery_pass"] = marker == "armed" and res4["active"] == [] and \
        set(r["recovery"]["second_codes"].values()) == {"STRUCTURAL_RECOVERY"}
    # the compiler's allow-list is back to the lum after every swap
    r["allow_list_restored"] = rm.LUM_ALLOW[LEVEL]["model"] == rm.LUM10 and rm.LUM_ALLOW[LEVEL]["so"] == 0x549A30
    r["pass"] = (r["active"] == [MOD] and all(r["images_equal_prototype"].values()) and r["tx_id_recomputed"]
                 and r["records"]["level-tx"] == 1 and r["records"]["tx-file"] == 3 and r["records"]["grow"] == 2
                 and r["sizes"] == {"lvl": SIZE + N_LVL, "ptr": PSIZE + N_PTR, "transit": TSIZE}
                 and r["deterministic"] and ok_neg and r["recovery_pass"] and r["allow_list_restored"])
    (WORK / "plan.json").write_text(json.dumps(r, indent=1, default=str) + "\n")
    print(json.dumps(r, indent=1, default=str)[:6000])
    print("PLAN_G6P8", "PASS" if r["pass"] else "FAIL")
    return 0 if r["pass"] else 1


def negtest(text=None, label="prototype", nd=None):
    """Runtime transaction cases for a Toad plan: the deterministic transaction test (g5p1_tx_test.cpp) built
    against the development header (g5p1_dev_gate.py render) and against the production header (G5-P1's
    p1.build_test). Private copies of the files only, never the game files."""
    nd = nd or WORK / f"negtest_{label}"
    if nd.exists():
        shutil.rmtree(nd)
    nd.mkdir(parents=True)
    p1.WORK = WORK
    d = GAME / "GAMEDATAbin" / LEVEL
    LVL, PTR, TRANSIT = d / f"{LEVEL}.lvl", d / f"{LEVEL}.ptr", d / "transit.lvl"
    exes = {k: p1.build_test(k) for k in ("dev", "prod")}
    if text is None:
        text = compile_proto("neg_runtime", [(MOD, [toad_op()])])[1]
    base = p1.parse_plan(text)
    _, imgs = plan_images(text)
    V = {}
    for k, b in imgs.items():
        V[k] = nd / f"img_{k}.bin"
        V[k].write_bytes(b)
    idx = {Path(f["path"]).name: i for i, f in enumerate(base["files"])}
    li, pi, ti = idx[f"{LEVEL}.lvl"], idx[f"{LEVEL}.ptr"], idx["transit.lvl"]

    def variant(name, fn=None):
        m = json.loads(json.dumps(base))
        if fn:
            fn(m)
        q = nd / f"plan_{name}.txt"
        q.write_text(p1.emit(m), encoding="utf-8")
        return q

    def tamper(m, i, ri):
        off, length, gb, nb, mid, blob = m["files"][i]["range"][ri].split(" ", 5)
        b = bytearray(Path(blob).read_bytes())
        b[len(b) // 2] ^= 0x33
        q = nd / f"tampered_{i}_{ri}.bin"
        q.write_bytes(bytes(b))
        m["files"][i]["range"][ri] = " ".join([off, length, gb, f"{g3a.fnv(bytes(b)):016x}", mid, str(q)])

    def alias(m):
        """The copy's Intelligence +0x10 (instance-local, owned) pointed into the SOURCE's block after compilation:
        an aliasing defect the result hash must refuse."""
        for k, r_ in enumerate(m["files"][li]["range"]):
            off, length, gb, nb, mid, blob = r_.split(" ", 5)
            if int(off) == SIZE:
                b = bytearray(Path(blob).read_bytes())
                w_ = COPY + CHAIN["intel"] + 0x10 - SIZE
                struct.pack_into(">I", b, w_, struct.unpack_from(">I", b, w_)[0] - (COPY - SRC))
                q = nd / "aliased_tail.bin"
                q.write_bytes(bytes(b))
                m["files"][li]["range"][k] = " ".join([off, length, gb, f"{g3a.fnv(bytes(b)):016x}", mid, str(q)])
    plans = {
        "valid": variant("valid"),
        "missing_transit": variant("missing_transit", lambda m: m["files"].pop(ti)),
        "missing_lvl": variant("missing_lvl", lambda m: m["files"].pop(li)),
        "tampered_ptr": variant("tampered_ptr", lambda m: tamper(m, pi, 0)),
        "aliased": variant("aliased", alias),
        "partial_records": variant("partial_records", lambda m: m["files"][li].update(
            range=[r_ for r_ in m["files"][li]["range"] if int(r_.split(" ")[0]) != 0x5A743C])),
        "corrupt_id": variant("corrupt_id", lambda m: m.update(
            txs=[m["txs"][0][:-1] + ("0" if m["txs"][0][-1] != "0" else "1")])),
        "version_1": variant("version_1", lambda m: m.update(txs=[m["txs"][0].replace("level-tx 2 ", "level-tx 1 ")])),
    }
    O = ("-", "-", "-")
    Va = (V["lvl"], V["ptr"], V["transit"])
    cp = nd / "copies"
    cp.mkdir()
    cps = {k: cp / src.name for k, src in (("lvl", LVL), ("ptr", PTR), ("transit", TRANSIT))}
    mc = json.loads(json.dumps(base))
    for f in mc["files"]:
        f["path"] = str(cps[{f"{LEVEL}.lvl": "lvl", f"{LEVEL}.ptr": "ptr", "transit.lvl": "transit"}[Path(f["path"]).name]])
    plans["copies"] = nd / "plan_copies.txt"
    plans["copies"].write_text(p1.emit(mc), encoding="utf-8")
    paths = (str(LVL), str(PTR), str(TRANSIT))
    cpaths = (str(cps["lvl"]), str(cps["ptr"]), str(cps["transit"]))
    dev = [("toad valid, lvl,ptr,transit", "valid", LEVEL, "active", "lvl,ptr,transit", Va, paths),
           ("toad valid, transit,ptr,lvl", "valid", LEVEL, "active", "transit,ptr,lvl", Va, paths),
           ("toad valid, ptr,lvl,transit", "valid", LEVEL, "active", "ptr,lvl,transit", Va, paths),
           ("toad valid, repeated opens", "valid", LEVEL, "active", "ptr,transit,lvl,transit,ptr", Va, paths),
           ("toad not enabled", "valid", "-", "level_tx_not_enabled", "lvl,ptr,transit", O, paths),
           ("toad enabled for another level", "valid", "intro_20", "tx_level", "transit,lvl,ptr", O, paths),
           ("toad missing transit member", "missing_transit", LEVEL, "tx_incomplete", "transit,lvl,ptr", O, paths),
           ("toad missing lvl member", "missing_lvl", LEVEL, "tx_incomplete", "ptr,transit,lvl", O, paths),
           ("toad tampered ptr, rehashed", "tampered_ptr", LEVEL, "tx_result_hash", "lvl,ptr,transit", O, paths),
           ("toad owned word aliased into the source", "aliased", LEVEL, "tx_result_hash", "lvl,ptr,transit", O,
            paths),
           ("toad partial: records-count edit dropped", "partial_records", LEVEL, "tx_result_hash",
            "transit,ptr,lvl", O, paths),
           ("toad corrupted id", "corrupt_id", LEVEL, "tx_id", "transit,lvl,ptr", O, paths),
           ("toad relabelled version 1", "version_1", LEVEL, "tx_role", "lvl,ptr,transit", O, paths),
           ("toad copies: host changes after activation", "copies", LEVEL, "active",
            "lvl,flip_transit,transit,flip_lvl,lvl,flip_ptr,ptr", Va, cpaths),
           ("toad copies: lvl changed before activation", "copies", LEVEL, "tx_identity",
            "flip_lvl,transit,lvl,ptr", O, cpaths)]
    prod = [("production: toad transaction (lvl first)", "valid", LEVEL, "unknown_record", "lvl,ptr,transit", O, paths),
            ("production: toad transaction (transit first)", "valid", LEVEL, "unknown_record", "transit,ptr,lvl", O,
             paths)]
    out = {}
    for kind, cases in (("dev", dev), ("prod", prod)):
        res_k = []
        for i, (n, p_, env, want, order, e, pa) in enumerate(cases):
            for k, src in (("lvl", LVL), ("ptr", PTR), ("transit", TRANSIT)):
                shutil.copyfile(src, cps[k])
            cf = nd / f"case_{kind}_{i}.tsv"
            cf.write_text("\t".join([n, str(plans[p_]), env, want, order, pa[0], pa[1], str(e[0]), str(e[1]), pa[2],
                                     str(e[2])]) + "\n", encoding="utf-8")
            r_ = subprocess.run([str(exes[kind]), str(cf)], capture_output=True, text=True, timeout=600)
            res_k.append({"case": n, "rc": r_.returncode, "out": r_.stdout.strip().splitlines()[:2]})
        out[kind] = {"cases": len(cases), "passed": sum(x["rc"] == 0 for x in res_k), "results": res_k}
        print(kind, out[kind]["passed"], "/", out[kind]["cases"])
    for k in cps.values():
        k.unlink()
    out["pass"] = all(out[k]["passed"] == out[k]["cases"] for k in ("dev", "prod"))
    (nd / "summary.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"NEGTEST_G6P8_{label.upper()}", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


# --- Gate A: the modified runs (development build) ---------------------------------------------------------------------

REC = {"init": 0x580C9C, "jump": 0x580DA8, "wait": 0x580EB4}   # NIN_m_ToadIntro's behaviour records (file offsets)
CASES = ("A", "B", "C")
REVISION = 2   # see REVISION 1 / 2 in the module docstring; 0 reproduces the original criteria
INTEL_LOCAL = (0x350, 0x358)                                  # the source's Intelligence +0x10 / +0x18 targets


def compile_run_plan(name, session=None):
    res, text, paths = compile_proto(name, [(MOD, [toad_op()])], session=session)
    if res["active"] != [MOD] or text is None:
        raise SystemExit(f"compiler refused the run's mod: {res.get('mods') or res}")
    return paths["cache"] / rm.PLAN_NAME, text, paths


def run(tag, cases=CASES):
    if gate_status() != "patched":
        raise SystemExit("the development gate is not applied")
    for f in ("revalidate.json", "plan.json", "negtest_prototype/summary.json"):
        if not json.loads((WORK / f).read_text()).get("pass"):
            raise SystemExit(f"{f} did not pass")
    for case in cases:
        run_ = f"{PREFIX}_{tag}_{case}"
        if case == "A":
            row = run_case(tag, case)
        elif case == "B":
            plan_, text, paths = compile_run_plan(f"run_{tag}_B", session=run_)
            row = run_case(tag, case, plan=plan_, env_level=LEVEL, session_paths=paths, copy=True)
        else:
            plan_, text, paths = compile_run_plan(f"run_{tag}_C")
            row = run_case(tag, case, plan=plan_, env_level=None)
        print(case, json.dumps(row, default=str)[:400], flush=True)
    return 0


def load_case(tag, case):
    w = WORK / tag / case
    r = json.loads((w / "row.json").read_text())
    for k in ("samples", "live", "states", "early"):
        r[k] = json.loads((w / f"{k}.json").read_text())
    r["log"] = g6p3.load_log(r["run"])
    r["safe"], r["safety"] = g6p3.safety(r)
    return r


def behaviour_oracle(r, label):
    """Per actor: the one-run-then-idle witness (G6-P8 Phase C). Returns (ok, detail)."""
    ab = r["live"]["first"]["ab"]
    X = lambda o: ab + o - 4   # noqa: E731
    d = {}
    early = [e[label] for e in r["early"] if label in e and "error" not in e[label]]
    pre = [e for e in early if e["ctr"] == 255 and e["beh"] in (REC["init"] - 4, X(REC["init"]))]
    post = [e for e in early if e["ctr"] == 0]
    d["pre_run_samples"], d["post_run_samples"] = len(pre), len(post)
    one_run = bool(pre and post) and post[0]["runs"] == (pre[-1]["runs"] + 1) % 0x10000 \
        and [post[0]["beh"], post[0]["prev"]] == [X(REC["jump"]), X(REC["wait"])]
    d["init_draw_then_run"] = [pre[-1]["runs"] if pre else None, post[0]["runs"] if post else None]
    sm = [s["a"][label] for s in r["samples"] if label in s["a"]]
    lf = r["live"]["first"]["actors"][label]
    iw = lf.get("intel_words") or [None] * 8
    d["intel_first"] = [hex(x) if x else x for x in iw[:7]]
    init_ok = iw[0] == X(AI_MODEL) and iw[2:4] == [X(REC["jump"]), X(REC["wait"])] and iw[5] == X(REC["init"]) \
        and (lf.get("mind") or [None])[0] == X(AI_MODEL)
    runs = {s["runs"] for s in sm}
    idle = len(runs) == 1 and post and runs == {post[0]["runs"]} and all(
        s["beh"] == X(REC["jump"]) and s["prev"] == X(REC["wait"]) and s["P"] == 1 and s["ctr"] == 0 for s in sm)
    pos = {tuple(s["pos"]) for s in sm}
    st = [s["stamp"] for s in sm]
    window = (r["samples"][-1]["t"] - r["samples"][0]["t"]) if r["samples"] else 0
    incs = sum(1 for a, b in zip(st, st[1:]) if b > a)
    if REVISION == 0:   # the original term (d), kept for the record (g1: INVALID, A failed it)
        visits = len(st) > 1 and all(b >= a for a, b in zip(st, st[1:])) and st[-1] - st[0] >= 50 * window
    else:               # revision 1 (d'): written in bursts with the current frame number; never decreases
        visits = len(st) > 1 and all(b >= a for a, b in zip(st, st[1:])) and incs >= 50 and st[-1] - st[0] >= 3000
    d["stamp_increases"] = incs
    d.update(runs=sorted(runs), positions=len(pos), stamp=[st[0], st[-1]] if st else None, window=round(window, 1),
             one_run=one_run, init_ok=init_ok, idle=bool(idle), visits=visits)
    return bool(one_run and init_ok and idle and len(pos) == 1 and visits), d


def judge(tag, btag=None):
    """Gate A (btag None) or I8 (btag = the typed run's tag: its case T stands in for B; A and C from `tag`)."""
    if btag is None:
        out = {c: load_case(tag, c) for c in CASES}
    else:
        out = {"A": load_case(tag, "A"), "B": load_case(btag, "T"), "C": load_case(tag, "C")}
    bdir = WORK / (btag or tag) / ("T" if btag else "B")
    A, B, C = (out[c] for c in CASES)
    det, P, invalid = {}, {}, []
    for c, r in out.items():
        lf = r["live"].get("first")
        if r.get("error") or not lf or any("error" in a for a in lf["actors"].values()):
            invalid.append(f"{c}:read")
        if not r["samples"] or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60:
            invalid.append(f"{c}:samples")
    opens = {c: [o.rsplit("\\", 1)[-1].lower() for o in re.findall(r"vfs_open path=(\S+?\.lvl) result=00000000",
                                                                   r["log"])] for c, r in out.items()}
    route_ok = {c: f"{LEVEL}.lvl" in o and "menumap.lvl" in o[o.index(f"{LEVEL}.lvl"):] and
                bool(out[c].get("level_change_t")) for c, o in opens.items()}
    det["route"] = {c: [opens[c], out[c].get("level_change_t")] for c in out}
    if not invalid:
        oa = {k: behaviour_oracle(A, k) for k in TOADS}
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

    def X_(r):
        ab = r["live"]["first"]["ab"]
        return lambda o: ab + o - 4

    # P1 transaction integrity
    log = B["log"]
    ptx = p1.parse_plan((bdir / "plan_copy.txt").read_text(encoding="utf-8"))["txs"]
    want = [tuple(ptx[0].split(" ")[2:5])]
    t = [tuple(x) for x in re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log)]
    snaps = sorted((f, b) for f, _, b, _ in re.findall(
        r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", log))
    grow = sorted(set(re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)))
    served = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
    P["P1_transaction"] = (log.count("M33 mods state=active") == 1 and t == want
                           and "G6P1 level-tx version=2 members=lvl,ptr,transit" in log
                           and snaps == sorted([(f"{LEVEL}.lvl", str(SIZE + N_LVL)), (f"{LEVEL}.ptr", str(PSIZE + N_PTR)),
                                                ("transit.lvl", str(TSIZE))])
                           and grow == sorted([(f"{LEVEL}.lvl", str(SIZE), str(SIZE + N_LVL)),
                                               (f"{LEVEL}.ptr", str(PSIZE), str(PSIZE + N_PTR)),
                                               ("transit.lvl", str(TSIZE), str(TSIZE))])
                           and served == sorted([f"{LEVEL}.lvl", f"{LEVEL}.ptr", "transit.lvl"])
                           and "G5P3 tx host_changed" not in log and "M33 mods=off" in A["log"])
    det["P1"] = {"tx": t, "want": want, "snaps": snaps, "grow": grow, "served": served}

    def union(r, which="first"):
        ls = r["live"][which]["lists"]
        return ls["dw"]["walk"] + ls["inactive"]["walk"]

    # P2 actor registration
    def p2(r, grown):
        X = X_(r)
        ls, la = r["live"]["first"]["lists"], A["live"]["first"]["lists"]
        u, ua = union(r), union(A)
        ok = "error" not in ls and ls["dw"]["prev_ok"] and ls["inactive"]["prev_ok"] and len(u) == len(set(u))
        if not grown:
            return ok and sorted(u) == sorted(ua) and ls["personal"]["count"] == 69 and X(COPY) not in u \
                and ls["rec"]["count"] == la["rec"]["count"]
        cp, sr = r["live"]["first"]["actors"]["copy"], r["live"]["first"]["actors"]["t1"]
        dw = ls["dw"]["walk"]
        bt = ls["bak_targets"]
        return (ok and cp.get("alive") and cp.get("model") == "NIN_m_ToadIntro" and sorted(u) == sorted(ua + [X(COPY)])
                and X(SRC) in dw and dw.index(X(SRC)) + 1 < len(dw) and dw[dw.index(X(SRC)) + 1] == X(COPY)
                and ls["rec"]["count"] == la["rec"]["count"] + 1 and ls["rec"]["owners"].count(X(COPY)) == 1
                and ls["rec"]["owners"][-1] == X(COPY)
                and len(bt) == len(la["bak_targets"]) + 1 and bt.count(X(COPY + 0xC4)) == 1
                and ls["personal"] == {"count": 70, "last_name": NEW_NAME}
                and cp.get("std_personal") == 69 and sr.get("std_personal") == 0x1D)
    P["P2_registration"] = p2(B, True) and p2(A, False) and p2(C, False)
    det["P2"] = {c: {"union": len(union(r)), "rec": r["live"]["first"]["lists"].get("rec", {}).get("count"),
                     "bak": len(r["live"]["first"]["lists"].get("bak_targets", [])),
                     "personal": r["live"]["first"]["lists"].get("personal")} for c, r in out.items()}

    # P3 independent instance ownership (B, first and end reads)
    def p3(r):
        X = X_(r)
        ok, d = True, {}
        for which in ("first", "end"):
            lv = r["live"].get(which)
            if not lv:
                return False, {"missing": which}
            cp, sr = lv["actors"]["copy"], lv["actors"]["t1"]
            own = {"perso": X(COPY + CHAIN["perso"]), "3ddata": X(COPY + CHAIN["3ddata"]),
                   "stdgame": X(COPY + CHAIN["stdgame"]), "brain": X(COPY + CHAIN["brain"])}
            got = {k: cp.get(k) for k in own}
            mind, smind = cp.get("mind") or [None] * 4, sr.get("mind") or [None] * 4
            iw = cp.get("intel_words") or [None] * 8
            others = [lv["actors"][k].get("buffer") for k in TOADS]
            blk, sblk = cp.get("block_words") or [], sr.get("block_words") or []
            ok_c, ok_s = ((0x18,), (0x14,)) if REVISION < 2 else ((0x18, ELEM + 8), (0x14, ELEM + 4))
            into_src = [4 * i for i, w in enumerate(blk) if X(SRC) <= w < X(SRC) + BLK and 4 * i not in ok_c]
            into_copy = [4 * i for i, w in enumerate(sblk) if X(COPY) <= w < X(COPY) + BLK and 4 * i not in ok_s]
            c = {"chain_own": got == own, "brain0_mind": (cp.get("brain_words") or [None])[0] == X(COPY + CHAIN["mind"]),
                 "mind1_intel": mind[1] == X(COPY + CHAIN["intel"]), "model_shared": mind[0] == smind[0] == X(AI_MODEL),
                 "no_dsgmem": mind[3] == 0 == smind[3],
                 "intel_local_own": [iw[4], iw[6]] == [X(COPY + INTEL_LOCAL[0]), X(COPY + INTEL_LOCAL[1])],
                 "brain4": (cp.get("brain_words") or [0, 0])[1] == 0xCDCDCDCD == (sr.get("brain_words") or [0, 0])[1],
                 "buffer_own": bool(cp.get("buffer")) and cp.get("buffer") not in others,
                 "copy_into_source": into_src, "source_into_copy": into_copy,
                 "links": [blk[0x18 // 4] == X(SRC), sblk[0x14 // 4] == X(COPY)] if blk and sblk else None,
                 "source_personal": sr.get("std_personal") == 0x1D}
            d[which] = c
            ok = ok and all(v is True for k, v in c.items() if k not in ("copy_into_source", "source_into_copy",
                                                                       "links")) \
                and not into_src and not into_copy and c["links"] == [True, True]
            if REVISION >= 2:
                c["element_list"] = elist_ok(r, which)
                ok = ok and c["element_list"]["ok"]
        return ok, d

    def owners(r, which):
        return [e["owner"] for e in r["live"][which]["elist"]["chain"]]

    def elist_ok(r, which):
        """Revision 2: the copy's list element = {X(copy), X(source element)... } inserted right after the source's;
        the whole walked list reciprocal, every owner once, one header; B's owners = A's with the copy after the
        source; the walk ends at 0 both ways."""
        X = X_(r)
        el = r["live"][which].get("elist", {})
        ch = el.get("chain") or []
        at = {e["at"]: e for e in ch}
        recip = all(at[e["next"]]["prev"] == e["at"] for e in ch if e["next"] in at) and             all(at[e["prev"]]["next"] == e["at"] for e in ch if e["prev"] in at)
        own = [e["owner"] for e in ch]
        ce, se = at.get(X(COPY + ELEM)), at.get(X(SRC + ELEM))
        oa = owners(A, which)
        want = oa[:oa.index(X(SRC)) + 1] + [X(COPY)] + oa[oa.index(X(SRC)) + 1:] if X(SRC) in oa else None
        d = {"len": len(ch), "len_A": len(oa), "reciprocal": recip, "owners_unique": len(own) == len(set(own)),
             "one_header": len({e["header"] for e in ch}) == 1, "ends": el.get("ends"),
             "copy_element": bool(ce and se and ce["owner"] == X(COPY) and ce["prev"] == se["at"]
                                  and se["next"] == ce["at"] and ce["header"] == se["header"]),
             "owners_B_eq_A_plus_copy": own == want, "header_words": el.get("header_words")}
        d["ok"] = bool(ch and "error" not in el and recip and d["owners_unique"] and d["one_header"]
                       and el.get("ends") == [0, 0] and d["copy_element"] and d["owners_B_eq_A_plus_copy"])
        return d
    p3ok, det["P3"] = p3(B)
    P["P3_independent_state"] = p3ok

    # P4 guest initialization / P5 guest behaviour (the Phase C oracle)
    ob = {k: behaviour_oracle(B, k) for k in list(TOADS) + ["copy"]}
    oc = {k: behaviour_oracle(C, k) for k in TOADS}
    det["P4_P5"] = {"B": {k: v[1] for k, v in ob.items()}, "C": {k: v[1] for k, v in oc.items()}}
    cpd = ob["copy"][1]
    srcpos = B["live"]["first"]["actors"]["t1"]["position"]
    P["P4_initialization"] = cpd["init_ok"] and cpd["one_run"] and cpd["pre_run_samples"] > 0
    both = [(x["a"]["copy"]["stamp"], x["a"]["t1"]["stamp"]) for x in B["samples"] if "copy" in x["a"] and "t1" in x["a"]]
    same = sum(1 for a_, b_ in both if a_ == b_)
    det["P5_copy_stamp_equal_source"] = [same, len(both)]
    P["P5_guest_behaviour"] = (all(v[0] for v in ob.values()) and all(v[0] for v in oc.values())
                               and B["live"]["first"]["actors"]["copy"]["position"] == srcpos
                               and (REVISION == 0 or (both and same >= 0.95 * len(both))))

    # P6 structural integrity
    def p6(r, grown):
        ok = True
        for which in ("first", "end"):
            ls = r["live"].get(which, {}).get("lists", {})
            ok = ok and "error" not in ls and ls.get("dw", {}).get("prev_ok") and ls.get("inactive", {}).get("prev_ok")
            u = union(r, which) if ls else []
            ok = ok and len(u) == len(set(u))
        if grown:
            X = X_(r)
            ok = ok and union(r, "end").count(X(COPY)) == 1 and r["live"]["end"]["actors"]["copy"].get("alive")
        return bool(ok) and r["safety"]["fault_line"] is False and set(r["safety"]["fault_codes"]) <= {"406D1388"}
    P["P6_integrity"] = all(p6(out[c], c == "B") for c in out)

    # P7 exit and cleanup
    def brief(x):
        return None if not x else {"free": x["free_bytes"], "largest": x["largest_free"],
                                   "alloc": x["allocated_chunks"], "free_chunks": x["free_chunks"],
                                   "areas": {k: (v["base"], v["length"]) for k, v in x["areas"].items()}}

    def phases(r):
        st = [x for x in r["states"] if "invalid" not in x and "areas" in x]
        lvl_ = next((x for x in st if set(x["areas"]) == {"0", "1", "3"}), None)
        i = st.index(lvl_) if lvl_ else None
        after = st[i + 1:] if i is not None else []
        fix = next((x for x in after if set(x["areas"]) == {"0"}), None)
        menu = next((x for x in after if set(x["areas"]) == {"0", "1", "2"}), None)
        return brief(lvl_), brief(fix), brief(menu)

    def diff(a, b):
        d = {k: a[k] - b[k] for k in ("free", "largest", "alloc", "free_chunks") if a[k] != b[k]}
        for k in sorted(set(a["areas"]) | set(b["areas"])):
            x, y = a["areas"].get(k), b["areas"].get(k)
            if x == y:
                continue
            if x and y and x[0] == y[0]:
                d[f"area{k}_length"] = x[1] - y[1]
            else:
                d[f"area{k}"] = [x, y]
        return d
    ph = {c: phases(r) for c, r in out.items()}
    det["phases"] = ph
    try:
        grown = {"area1_length": N_LVL, "free": -N_LVL, "largest": -N_LVL}
        dl = {c: diff(ph[c][0], ph["A"][0]) for c in "BC"}
        det["P7_loaded_diff"] = dl
        fix_ok = all(ph[c][1] and ph[c][1]["free"] == 20795836 and ph[c][1]["alloc"] == 1 and
                     ph[c][1]["free_chunks"] == 1 for c in out)
        menu_ok = all(ph[c][2] and ph[c][2] == ph["A"][2] for c in "BC")
        P["P7_exit_cleanup"] = all(route_ok.values()) and dl["B"] == grown and dl["C"] == {} and fix_ok and menu_ok
    except Exception as x:
        det["P7_error"] = repr(x)
        P["P7_exit_cleanup"] = False

    # P8 production and desktop safety
    marks = (B["marker_before_start"][0] == "armed" and B["marker_before_start"][1]["session"] == B["run"]
             and B["marker_before_start"][1]["plan_sha256"] == B["plan_sha256"] and B["controlled"] is True
             and B.get("session_end", {}).get("cleared") is True and B.get("marker_after") == "none")
    c_ok = ("state=refused reason=level_tx_not_enabled" in C["log"] and "M33 mods served" not in C["log"]
            and "M36 grow" not in C["log"] and not re.search(r"G5P1|G5P3|G6P1", C["log"]))
    P["P8_safety"] = all(r["safe"] for r in out.values()) and marks and c_ok
    det["P8"] = {"marks": marks, "C_refused": c_ok, "safety": {c: r["safety"] for c, r in out.items()}}
    if all(P.values()):
        verdict = "A-PASS"
    elif P["P2_registration"] and P["P3_independent_state"] and not (P["P4_initialization"] and P["P5_guest_behaviour"]
                                                                     and P["P7_exit_cleanup"]):
        verdict = "A-PARTIAL"
    else:
        verdict = "A-FAIL"
    if btag is not None:
        verdict = "I8-PASS" if verdict == "A-PASS" else f"I8-FAIL ({verdict})"
    res = {"invalid": invalid, "P": P, "verdict": verdict, "details": det}
    (WORK / f"judgement_{btag or tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("invalid", "P", "verdict")}, indent=1))
    return 0 if verdict in ("A-PASS", "I8-PASS") else 1


def run_typed(tag):
    """I8: one hidden run T with the typed operation (real compiler, no private spec), session marker armed."""
    if gate_status() != "patched":
        raise SystemExit("the development gate is not applied")
    if not json.loads((WORK / "typed_check.json").read_text()).get("pass"):
        raise SystemExit("typed_check.json did not pass")
    run_ = f"{PREFIX}_{tag}_T"
    res, text, paths = compile_typed(f"run_{tag}_T", [(MOD_T, [typed_op()])], session=run_)
    if res["active"] != [MOD_T] or text is None:
        raise SystemExit(f"compiler refused the typed mod: {res.get('mods') or res}")
    row = run_case(tag, "T", plan=paths["cache"] / rm.PLAN_NAME, env_level=LEVEL, session_paths=paths, copy=True)
    print("T", json.dumps(row, default=str)[:400], flush=True)
    return 0


# --- Gate B: the typed operation (only after Gate A's A-PASS, run g3) --------------------------------------------------

MOD_T = "g6p8.toad"


def typed_op(**kw):
    lvl, ptr, tl = files()
    o = {"type": "insert-toad-intro", "level": LEVEL, "model": TOAD, "instance": 1, "lvl_sha256": sha(lvl),
         "ptr_sha256": sha(ptr), "transit_sha256": sha(tl), "placement": "at_source", "owner": "dynamic_world"}
    o.update(kw)
    return o


def compile_typed(name, mods, session=None, env=LEVEL):
    """The real compiler, no private spec: import + resolve_all."""
    p1.WORK = WORK
    paths = p1.fresh(name)
    with p1.dev_env(env):
        for mid, ov in mods:
            try:
                p1.install(paths, mid, ov)
            except rm.Refusal as x:
                return {"import_refused": [mid, x.code, x.detail], "active": [], "mods": []}, None, paths
        res = rm.resolve_all(paths, write_plan=paths["cache"], session=session)
    plan_ = paths["cache"] / rm.PLAN_NAME
    return res, (plan_.read_text(encoding="utf-8") if plan_.is_file() else None), paths


def typed_check():
    """I1-I7 offline."""
    WORK.mkdir(parents=True, exist_ok=True)
    I, det = {}, {}
    lvl, ptr, tl = files()
    res, text, paths = compile_typed("typed_valid", [(MOD_T, [typed_op()])])
    m, imgs = plan_images(text)
    shutil.copyfile(paths["cache"] / rm.PLAN_NAME, WORK / "plan_typed.txt")
    g3plan = (WORK / "g3" / "B" / "plan_copy.txt").read_text(encoding="utf-8")
    m3, imgs3 = plan_images(g3plan)
    shape = lambda mm: [(Path(f["path"]).name, f["size"], f["grow"], [r.split(" ")[:2] for r in f["range"]])   # noqa
                        for f in mm["files"]]
    rng = lambda mm: [[Path(r.split(" ", 5)[5]).read_bytes() for r in f["range"]] for f in mm["files"]]   # noqa
    I["I1_prototype_equivalence"] = (res["active"] == [MOD_T] and {k: sha(b) for k, b in imgs.items()} == PROTO
                                     and imgs == imgs3 and shape(m) == shape(m3) and rng(m) == rng(m3)
                                     and [t.split(" ", 5)[1:] for f in m["files"] for t in f["tx"]] ==
                                     [t.split(" ", 5)[1:] for f in m3["files"] for t in f["tx"]])
    det["I1"] = {"hashes": {k: sha(b) for k, b in imgs.items()}, "same_ranges_as_g3": rng(m) == rng(m3),
                 "txs": m["txs"], "g3_txs": m3["txs"]}
    # I2 independent simulation (G6-P7's simulator, which shares no code with the compiler's verifier)
    L, ix, key, insts = g7.toad_inputs()
    s, facts, spec, peers = g7.independent_check(L, ix, key, insts)
    sim = g7.simulate(lvl, ptr, tl, imgs["lvl"], imgs["ptr"], imgs["transit"], L["me"], SRC, BLK, insts, s)
    I["I2_independent_simulation"] = sim["pass"] and sim["copy"] == COPY
    det["I2"] = {k: v for k, v in sim.items() if k != "details"}
    # I3 ownership: all 31 copied words keep their verified classes and the prototype's targets
    I["I3_ownership"] = (sim["copy_kinds"] == {"owned": 14, "shared": 14, "other-file": 1, "link next": 1,
                                               "link previous": 1} and not sim["bad_words"]
                         and imgs["lvl"][COPY:COPY + BLK] == imgs3["lvl"][COPY:COPY + BLK]
                         and imgs["ptr"] == imgs3["ptr"])
    # I4 transaction: the runtime cases on the typed plan
    I["I4_transaction"] = negtest(text, "typed") == 0
    # I5 negatives (whole mod refused, no level-tx in any plan)
    frog = {"type": "insert-scripted-frog", "level": LEVEL, "model": rm.FROG10, "instance": 2, "lvl_sha256": sha(lvl),
            "ptr_sha256": sha(ptr), "transit_sha256": sha(tl), "placement": "at_source", "period_ms": 500}
    lum = {"type": "insert-passive-lum", "level": LEVEL, "model": rm.LUM10, "instance": 6, "lvl_sha256": sha(lvl),
           "ptr_sha256": sha(ptr), "transit_sha256": sha(tl), "position": [17.87, -101.22, -44.18]}

    def outcome(name, mods, env=LEVEL):
        r_, t_, _ = compile_typed(f"tneg_{name}", mods, env=env)
        refused_ = "import_refused" in r_ or (not r_["active"] and all(x.get("code") for x in r_["mods"]))
        return {"refused": refused_, "code": r_["import_refused"][1] if "import_refused" in r_ else
                {x["id"]: x.get("code") for x in r_["mods"]}, "plan": bool(t_ and "level-tx" in t_)}
    neg = {
        "unsupported model (the lum key)": outcome("model", [(MOD_T, [typed_op(model=rm.LUM10)])]),
        "unsupported model (another family)": outcome("model2", [(MOD_T, [typed_op(model=rm.FROG10)])]),
        "wrong lvl hash": outcome("lvlsha", [(MOD_T, [typed_op(lvl_sha256="0" * 64)])]),
        "wrong ptr hash": outcome("ptrsha", [(MOD_T, [typed_op(ptr_sha256="1" * 64)])]),
        "wrong transit hash": outcome("tlsha", [(MOD_T, [typed_op(transit_sha256="2" * 64)])]),
        "invalid source instance 0 (holds the model)": outcome("i0", [(MOD_T, [typed_op(instance=0)])]),
        "invalid source instance 2": outcome("i2", [(MOD_T, [typed_op(instance=2)])]),
        "invalid source instance 9": outcome("i9", [(MOD_T, [typed_op(instance=9)])]),
        "unsupported placement (raw position)": outcome("pos", [(MOD_T, [typed_op(placement=[59.0, -256.0, -56.0])])]),
        "unsupported placement (name)": outcome("pl", [(MOD_T, [typed_op(placement="beside_source")])]),
        "unsupported owner": outcome("own", [(MOD_T, [typed_op(owner="always_active")])]),
        "raw pointer key": outcome("raw", [(MOD_T, [dict(typed_op(), so=0x581268)])]),
        "other level": outcome("lvl20", [(MOD_T, [typed_op(level="intro_20")])]),
        "duplicate actors (two in one mod)": outcome("two", [(MOD_T, [typed_op(), typed_op()])]),
        "composition with the lum (one mod)": outcome("withlum", [(MOD_T, [typed_op(), lum])]),
        "structural conflict (Toad mod + Frog mod)": outcome("conflict", [(MOD_T, [typed_op()]), ("g6p8.frog", [frog])]),
        "gate unset": outcome("nogate", [(MOD_T, [typed_op()])], env=None),
        "gate for another level": outcome("gate20", [(MOD_T, [typed_op()])], env="intro_20"),
    }
    # bad pointer classes / damaged inputs at the builder, and a misclassified output at the independent simulator
    spec_t = rm.TOAD_ALLOW[LEVEL]
    pos = struct.unpack_from(">3f", lvl, SRC + 0xC4 + 0x34)
    me = L["me"]

    def build(lvl_=lvl, ptr_=ptr, tl_=tl, spec_=spec_t):
        return rm.build_passive_lum(lvl_, ptr_, tl_, me, spec_, peers, pos, "neg")
    n0 = u32(ptr, 0)
    dup = bytearray(ptr)
    dup[4 + 8 * (n0 - 1) + 4:4 + 8 * n0] = dup[4 + 4:4 + 8]
    unrel = bytearray(ptr)   # the source's Perso word (an owned in-block pointer) no longer relocated
    k = next(i for i in range(n0) if u32(ptr, 8 + 8 * i) + 4 == SRC + 4)
    struct.pack_into(">I", unrel, 8 + 8 * k, u32(ptr, 8 + 8 * k) ^ 0x1000)
    pc = bytearray(lvl)
    struct.pack_into(">I", pc, 0x1C7C, u32(lvl, 0x1C7C) + 1)
    wrongcensus = dict(spec_t, census=(15, 15, 1))
    neg["damaged input: duplicate relocation slot"] = {"refused": p1.refused(lambda: build(ptr_=bytes(dup)),
                                                                             "STRUCTURE_CHECK") is True}
    neg["bad pointer class: an owned word unrelocated"] = {"refused": p1.refused(lambda: build(ptr_=bytes(unrel)),
                                                                                 "STRUCTURE_CHECK") is True}
    neg["damaged input: personal count"] = {"refused": p1.refused(lambda: build(lvl_=bytes(pc)),
                                                                  "STRUCTURE_CHECK") is True}
    neg["census mismatch (classes not the verified 14 / 16 / 1)"] = {
        "refused": p1.refused(lambda: build(spec_=wrongcensus), "STRUCTURE_CHECK") is True}
    bad = bytearray(imgs["lvl"])
    w_ = COPY + CHAIN["intel"]          # Intelligence +0 (shared model) rebased as if owned
    struct.pack_into(">I", bad, w_, u32(bad, w_) + (COPY - SRC))
    sim_bad = g7.simulate(lvl, ptr, tl, bytes(bad), imgs["ptr"], imgs["transit"], me, SRC, BLK, insts, s)
    neg["simulator: shared model word rebased (misclassified)"] = {"refused": not sim_bad["pass"]}
    I["I5_negatives"] = all(v["refused"] and not v.get("plan") for v in neg.values())
    det["I5"] = neg
    # I6 frozen compatibility of the four previous operations
    eq = subprocess.run([sys.executable, str(HERE / "g6p5_equivalence.py"), "compare"], capture_output=True, text=True)
    I["I6_frozen_compatibility"] = eq.returncode == 0
    det["I6"] = eq.stdout.strip().splitlines()[-3:]
    # I7 production isolation: the production header has no transaction code; no development env -> refused (above);
    # the production test executable refuses the typed plan (I4's prod cases); the gate status after restore is
    # checked again in the regression step
    hdr = (TOOLS / "m33_mod_overlay.h").read_text(encoding="utf-8", errors="replace")
    ts = json.loads((WORK / "negtest_typed" / "summary.json").read_text())
    I["I7_production_isolation"] = ("level-tx" not in hdr and neg["gate unset"]["refused"]
                                    and ts["prod"]["passed"] == ts["prod"]["cases"] == 2
                                    and subprocess.run(["git", "diff", "--quiet", "HEAD", "--",
                                                        "tools/m33_mod_overlay.h"], cwd=ROOT).returncode == 0)
    out = {"pass": all(I.values()), "I": I, "details": det}
    (WORK / "typed_check.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(I, indent=1))
    print("TYPED_CHECK_G6P8", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


def main():
    a = sys.argv[1:]
    if a == ["typed-check"]:
        return typed_check()
    if a[:1] == ["run"] and len(a) == 2:
        return run(a[1])
    if a[:1] == ["judge"] and len(a) == 2:
        return judge(a[1])
    if a[:1] == ["run-typed"] and len(a) == 2:
        return run_typed(a[1])
    if a[:1] == ["judge-typed"] and len(a) == 3:
        return judge(a[1], a[2])
    if a == ["negtest"]:
        return negtest()
    if a == ["revalidate"]:
        return revalidate()
    if a == ["plan"]:
        return plan()
    if a[:1] == ["observe"] and len(a) == 2:
        return observe(a[1])
    if a[:1] == ["summarize"] and len(a) == 3:
        print(json.dumps(summarize(a[1], a[2]), indent=1, default=str))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
