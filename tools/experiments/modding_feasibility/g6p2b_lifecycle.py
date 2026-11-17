#!/usr/bin/env python3
"""E-488 (D-255) G6-P2b: G6-P2's development-only scripted Frog (mod `g6p2.frog`, period 500 ms, `level-tx 2
intro_10 g6p2.frog e3ae1bf9c342f6a4` over intro_10.lvl / .ptr / transit.lvl) through G5-P3's same-process Pause ->
Load reload and G5-P4b's ownership-checked abnormal termination and recovery.

usage:
  g6p2b_lifecycle.py check          offline O1-O7 (no game)
  g6p2b_lifecycle.py reload TAG     phase 1: one hidden run of G5-P3's route with the Frog mod (case ra)
  g6p2b_lifecycle.py recover TAG    phase 2: G5-P4b's phases A / C / D
  g6p2b_lifecycle.py judge-reload TAG / judge-recover TAG
Outputs: private/work/e488/.

REUSED, UNCHANGED: g5p3_reentry.run_case and g5p4b_recovery (route, entries, block-8 snapshots, plan / marker /
  ownership-checked kill / recovery / clear) through their existing default-None hooks OBSERVE / SAMPLER / KILL_READY
  (G6-P1b); g6p1b_lifecycle's list reads, registration test, loader and fault counts; G6-P2's compiler binding and
  offline / transaction tests. Frog observation (this file): at each intro_10 entry the lists and both actors'
  live records (G4d-1's reader: DsgMem, buffers, 3dData, Brain, Mind, Intelligence, sound events); every 0.1 s for
  source and copy the scheduler period P (3dData +342), counter (+343), AI runs (+344, u16), behaviour (Intelligence
  +8), v5 in both buffers and v8, plus the engine timer 0x82C0628C.
SCHEDULER MODEL (G4d-0 / G4d-1, unchanged): the actor's AI runs every P frames (P drawn once at Init from the shared
  random stream, in [28, 35]); LoopOneShot re-stamps v8 = timer on a run when |timer - v8| >= v5. Intervals are judged
  in AI runs (D-254): with v5 = 500 and a 60 Hz frame, m = 2 runs for P 28-29, m in {1, 2} for P 30 (threshold), m = 1
  for P >= 31. The draws on this route differ from a direct load, so P is read, not predicted.
ROUTE TIME (checked before this protocol): G5-P3's route keeps load 1 about 38 s and load 2 about 48 s (E-479 r2 rb,
  E-485 l2); the copy re-stamps every 1-2 runs of about 0.5-0.6 s, so each load gives dozens of updates.

OFFLINE (check), before any build:
  O1 compiler stability: G6-P2's compiled period-500 images = lvl 12e5f919..., ptr 134e861c..., transit 321de2e4...
     (7,664,864 / 209,500 / 41,508) and the plan's transaction `level-tx 2 intro_10 g6p2.frog e3ae1bf9c342f6a4`.
  O2 resource consistency: G6-P2's negtest re-run (dev: three orders, repeated opens, exit composition, gate off,
     other level, missing transit, tampered ptr, dropped resolve words, corrupt id, private-copy host changes after
     activation served as images and before activation refused; production unknown_record).
  O3 ownership / O4 fixups: G6-P2's check re-run (8 / 8: G4c equivalence, own blocks, buffers, 347-entry resolve
     table, 54 relocation entries, always list, budget, negatives, lum compatibility).
  O5 lifecycle observation: on the compiled image, the reader's relative addresses land where the sampler expects:
     the copy's 3dData / Brain / Mind / Intelligence / DsgMem / buffers in its block and the LoopOneShot record shared;
     the reused runners need no change (hooks only).
  O6 recovery compatibility: G5-P4b's preflight with g6p2.frog (14 checks).
  O7 backward compatibility: G6-P1 negtest (versions 1 / 2, G5 suites, production refusal) via G6-P2's negtest,
     G6-P2 check O8 (lum images / tx, selftest).

PROSPECTIVE PROTOCOL (committed before the development build and any modified run)
PHASE 1 (reload), run e488_TAG_ra: G5-P3's route exactly (copy of save entry intro_10_fresh; Title -> Load -> intro_10;
  Pause -> Load -> Yes -> intro_10; Pause -> Exit Game; 220 s; guest-scoped input, hidden, muted, no captures). Plan
  g6p2.frog (period 500) only, session = run (marker armed), R3HD_DEV_STRUCTURAL_TX=intro_10. Control (not re-run):
  E-479 r2 rb (same route, no plan). Reference actors: E-484 h1 base's 66 SuperObjects.
  Route valid: level bursts menumap, intro_10, intro_10 and two intro_10 entries; else INVALID-ROUTE.
  L1 first-load transaction: one `M33 mods state=active`; one `G5P1 level-tx active` = the plan's (intro_10,
     g6p2.frog, id); one `G6P1 level-tx version=2 members=lvl,ptr,transit`; `G5P3 tx snapshot` exactly intro_10.lvl
     7,664,864, intro_10.ptr 209,500, transit.lvl 41,508, disk_reads=3, before the first `G5P3 tx read`.
  L2 first-load registration (entry 1 first read): area 7,661,832 + 3,028; union = reference + copy, no duplicates,
     previous links; records 123 (copy last); copy +0xC4 in the backups; personal 70, last MAN_mGenSound_Frog_G4C;
     the copy's DsgMem / buffers / 3dData / Brain / Mind / Intelligence its own block addresses; DsgMem +0 and Mind +0
     the source's; Brain +4 equal; the copy's eight sound-event words live = the source's and none 0x00580006; no
     copy word points into the source block except +0x18 and no source word into the copy except +0x14.
  L3 first-load script execution (entry 1 samples, copy; the source for independence): behaviour = live LoopOneShot
     in every sample; >= 10 distinct v8 values, each within the timer readings bracketing its sample; P constant and in
     [28, 35]; every v8 change follows an AI-run increment since the previous sample; every interval between v8
     changes, in AI runs, is in the model's set for that P; v5 = 500 in both copy buffers and both source buffers;
     source and copy v8 sequences differ.
  L4 genuine reload: route valid; entry 1 left before entry 2 appeared, a fix-only block-8 state between them;
     `G5P3 tx pass` >= 2 per member; one process for the run, runner exit 0.
  L5 second-load registration and fresh state (entry 2): L2 again (an address equal to entry 1's after release is not
     aliasing); fresh lifecycle at entry 2's first sample: the copy's AI-run count below entry 1's last and <= 60, its
     behaviour LoopOneShot, v5 = 500 in both buffers, 0 < v8 <= timer and timer - v8 <= 2 x P x 1000/60 + 100 ms (a
     stamp written in this load's current period window, not a leftover), and the copy's buffers and records at its
     own block addresses of entry 2.
  L6 second-load script execution: L3's criteria on entry 2.
  L7 memory and transaction consistency: valid block-8 walks after the first valid snapshot, `changed` (torn read)
     tolerated outside intro_10 up to two (E-485 revision 1); against the control D(menu before) = {}, D(entry 1) =
     D(entry 2) = {area1_length +3028, free -3028, largest -3028}, D(fix between) = {}, D(menu after) = {}; within the
     run entry 1 = entry 2, menu before = after, fix between = 20,795,836 free; one level-tx line, exactly three
     snapshot lines, no host change, no `M36 grow read` naming a member, every pass's image_bytes = its snapshot;
     entries 1 and 2 same area base and length; host snapshot bytes 7,664,864 + 209,500 + 41,508 = 7,915,872.
  L8 safety: M21 / M22 / M23 0, haptics policy line, runner exit 0, foreground events / samples 0 / 0, exception codes
     and counts = the same-route no-mod control (E-479 r2 rb; E-485 revision 1), D-250 ownership check, marker armed
     before (session, plan SHA-256) and cleared by the controlled end, protected() equal.
  L3 and L5 holding with L6 failing = PARTIAL — RELOAD SCRIPT UNVERIFIED.
PHASE 2 (recovery), tag TAG: G5-P4b's phases; RA = g6p2.frog + e478.lums-6, RB = g6p2.frog (isolation witness);
  A 140 s, termination when the copy has re-stamped v8 at least 3 times after the first sample (G5-P4b's existing
  wait, at most 45 s after the area appears; else INVALID, nothing killed); C 110 s; D clear / dry run / re-arm /
  clear. `--test-level intro_10`.
  R1 marker ordering: marker mtime < process creation < first `M36 grow size` naming intro_10; one `G5P1 level-tx
     active`, one `G6P1 level-tx version=2`, three `G5P3 tx snapshot` lines in A.
  R2 activation: A's snapshots = the three image sizes; A's first read: L2's registration test.
  R3 script before termination: in A's samples before the kill, copy behaviour LoopOneShot, >= 3 v8 changes each
     following an AI-run increment and within the bracketing timer readings.
  R4 ownership (G5-P4b R1), R5 forced termination (R4), R6 marker persistence (R5): unchanged.
  R7 whole-transaction refusal: C's plan refuses g6p2.frog with STRUCTURAL_RECOVERY, recovery armed, no level-tx in
     the plan; C's log no G5P1 / G5P3 / G6P1 / M36 grow line and nothing served from transit.lvl; marker unchanged.
  R8 original state and ordinary mod: C's first read: union = reference, records 122, personal 69, area 7,661,832;
     G5-P4b R7 (e478.lums-6 active in A and C, served in intro_10.lvl, C leaves for intro_15).
  R9 isolation and clear: G5-P4b R8 and R9 (RB never marked; clear; dry run lists the mod; stamp-D plan carries its
     level-tx; final clear).
  R10 production / desktop: G5-P4b R10 and C's exception codes only 406D1388.
REVISION 1 (after reload run f1; f1 kept as judged: L1 L3 L4 L6 L7 L8 PASS, L2 / L5 FAIL, NOT PASSED;
  judgement_reload_f1_original.json): the observer took g6p1b_lifecycle.read_blocks, which reads the LUM's source
  offset and block size and the copy only when the area is the lum's grown length, so the copy's block was never read
  and L2 / L5's no-alias term saw an empty block (every other L2 / L5 term passed: lists, the copy's own records,
  fresh state). Revision: a Frog block reader (source 0x53BED0, copy at the appended offset, 0x520 bytes, area +3,028).
  Criteria unchanged. Fresh reload run f2; the recovery phase (not yet run) uses the same reader.
REVISION 2 (after reload run f2; f2 kept: L2 / L5 FAIL only on no-alias, NOT PASSED; judgement_reload_f2_original.json):
  with the Frog blocks read, the only crossing words are source +0x504 -> copy +0x500 and copy +0x508 -> source +0x500.
  Block +0x500 is a runtime node the engine fills {-> owner SO, next node, previous node} (+0x504 / +0x508 are not
  relocation slots in the file): source node owner = source, copy node owner = copy, source.next = copy node,
  copy.prev = source node, copy.next = the next sibling's (SmallRiver's) node: the engine links the copy after the
  source in a runtime actor list, as in the sibling chain. The no-alias rule (from the lum, which has no such node)
  now allows exactly that pair when both owner words name their own actor; any other crossing pointer still fails.
  Fresh reload run f3; the recovery phase (not yet run) uses the same test.
RECOVERY k1: INVALID, not judged (harness crash): G5-P4b's phase-A loop reads a top-level `v8` from each sample
  (its site-window sequence), which the Frog sampler did not provide (KeyError after the first sample); the runner
  ended its test-owned game at its own deadline (ownership checked: profile e488_k1_A, its log file, the runner's
  child). Fix: the sampler also returns the copy's v8 at top level (unused by the Frog's empty site list). Criteria
  unchanged; fresh recovery run k2.
Class: L1-L8 and R1-R10 = G6-P2b VERIFIED — SCRIPTED ACTOR LIFECYCLE & RECOVERY; failures kept; stop conditions as
the brief (partial activation, registration error, stale state, aliasing, missing script, retained memory, marker lost,
structural data in recovery, safety).
"""
import json
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
import g4c_ab as g4c  # noqa: E402
import block8_probe as bp  # noqa: E402
import g5p1_pilot as p1  # noqa: E402
import g5p3_reentry as r3  # noqa: E402
import g5p4b_recovery as p4b  # noqa: E402
import g6p1b_lifecycle as g6b  # noqa: E402
import g6p2_pilot as g62  # noqa: E402

PREFIX = "e488"
WORK = ROOT / "private" / "work" / PREFIX
RUNS = g3a.RUNS
AREA, N = g3a.AREA, 3028
SRC, BLK = g4c.SRC, g4c.BLK
FC = g4c.layout()["fc"]
COPY_REL, SRC_REL = FC - 4, SRC - 4
NEW_NAME = "MAN_mGenSound_Frog_G4C"
IMAGES = {"lvl": "12e5f919", "ptr": "134e861c", "transit": "321de2e4"}
TX = "e3ae1bf9c342f6a4"
SNAP = [("intro_10.lvl", "7664864"), ("intro_10.ptr", "209500"), ("transit.lvl", "41508")]
HOST_BYTES = 7664864 + 209500 + 41508
F = 1000 / 60
CONTROL = g6b.CONTROL


def m_set(P):
    return {2} if P in (28, 29) else {1, 2} if P == 30 else {1} if 31 <= P <= 35 else set()


# --- live observation (hooks of the reused runners) ---------------------------------------------------------------

def actor(p, ab, fo):
    def w(a):
        x = p.words(a, 1)
        if not x:
            raise ValueError(f"read {a:#x}")
        return x[0]
    live = lambda o: ab + o - 4   # noqa: E731
    dm = live(fo + g4c.DSGMEM)
    ini, cur = w(dm + 4), w(dm + 8)
    ev = list(p.words(ini, 4) or []) + list(p.words(cur, 4) or [])
    return {"dsgmem": dm, "dsgvar": w(dm), "ini": ini, "cur": cur, "mind0": w(live(fo + g4c.MIND)),
            "d3": w(live(fo + 0x80)), "brain": w(live(fo + 0x80 + 0xC)), "mind": w(live(fo + g4c.BRAIN)),
            "intel": w(live(fo + g4c.MIND + 4)), "mind_dsgmem": w(live(fo + g4c.MIND + 0xC)),
            "brain4": w(live(fo + g4c.BRAIN + 4)), "events": ev}


def read_blocks(p, ab):
    """Revision 1: the Frog's blocks (source 0x53BED0 and the copy, 0x520 bytes each; the copy only in a grown area).
    f1 used g6p1b's reader, which has the lum's source, block size and grown length."""
    a1 = (bp.areas(p) or {}).get(1)
    out = {"src": (p.read(ab + SRC_REL, BLK) or b"").hex()}
    if a1 and a1["base"] == ab and a1["end"] - a1["base"] == AREA + N:
        out["copy"] = (p.read(ab + COPY_REL, BLK) or b"").hex()
    return out


def observe(rd, p, ab):
    out = {"lists": g6b.read_lists(p), "blocks": read_blocks(p, ab), "loop_oneshot": ab + g4c.LOOP_ONESHOT - 4}
    try:
        out["actors"] = {"src": actor(p, ab, SRC)}
        a1 = (bp.areas(p) or {}).get(1)
        if a1 and a1["base"] == ab and a1["end"] - a1["base"] == AREA + N:
            out["actors"]["copy"] = actor(p, ab, FC)
    except Exception as x:
        out["actors_error"] = repr(x)
    return out


class Sampler:
    """Per entry, every call (0.1 s): timer; for source and copy P, counter, AI runs, behaviour, v5 both, v8."""

    def __init__(self, p, ab):
        self.p, self.ab, self.acts = p, ab, None

    def __call__(self, gen, t):
        p = self.p
        if self.acts is None:
            self.acts = {"src": actor(p, self.ab, SRC)}
            a1 = (bp.areas(p) or {}).get(1)
            if a1 and a1["base"] == self.ab and a1["end"] - a1["base"] == AREA + N:
                self.acts["copy"] = actor(p, self.ab, FC)
        out = {"timer": p.words(g4c.TIMER, 1)[0]}
        for k, a in self.acts.items():
            sb = p.read(a["d3"] + 340, 8)
            ib, cb = p.read(a["ini"], g4c.VLEN), p.read(a["cur"], g4c.VLEN)
            out[k] = {"P": sb[2], "ctr": sb[3], "runs": struct.unpack_from(">H", sb, 4)[0],
                      "beh": p.words(a["intel"] + 8, 1)[0], "ini_v5": struct.unpack_from(">i", ib, g4c.V5)[0],
                      "cur_v5": struct.unpack_from(">i", cb, g4c.V5)[0], "v8": struct.unpack_from(">I", cb, g4c.V8)[0]}
        out["timer2"] = p.words(g4c.TIMER, 1)[0]
        out["v8"] = out.get("copy", out["src"])["v8"]   # G5-P4b's launch loop reads a top-level v8 (k1 crash fix)
        return out


def kill_ready(samples):
    c = [s["copy"]["v8"] for s in samples if "copy" in s]
    return sum(1 for a, b in zip(c, c[1:]) if a != b) >= 3


def setup():
    WORK.mkdir(parents=True, exist_ok=True)
    p1.WORK = WORK
    g6b.NEW_NAME = NEW_NAME   # registered(): the Frog's personal-type name (COPY_REL is the same offset)
    assert g6b.COPY_REL == COPY_REL
    r3.PREFIX, r3.WORK = PREFIX, WORK
    r3.PLAN_MOD = (g62.MOD, lambda: [g62.frog(500)])
    r3.EXTRA_MODS = []
    r3.AREA10 = (AREA, AREA + N)
    r3.OBSERVE, r3.SAMPLER, r3.TICK = observe, Sampler, None
    p4b.PREFIX, p4b.WORK = PREFIX, WORK
    p4b.STRUCT_ID = g62.MOD
    p4b.STRUCT_OV = lambda: [g62.frog(500)]
    p4b.GROWN_AREA = AREA + N
    p4b.GROWN_NODES = -1
    p4b.sites = lambda: []
    p4b.new_nodes = lambda: []
    p4b.OBSERVE, p4b.SAMPLER, p4b.KILL_READY = observe, Sampler, kill_ready


# --- offline -------------------------------------------------------------------------------------------------------

def check():
    setup()
    res, det = {}, {}
    _, tx = g62.compiled(500)
    im = tx["images"]
    r, text, _ = p1.compile_plan("o1", g62.mods_for("same"))
    txs = p1.parse_plan(text or "")["txs"]
    res["O1_compiler_stability"] = ({k: rm.sha256_bytes(im[k])[:8] for k in IMAGES} == IMAGES
                                    and [len(im[k]) for k in ("lvl", "ptr", "transit")] == [7664864, 209500, 41508]
                                    and txs == [f"level-tx 2 intro_10 {g62.MOD} {TX}"])
    det["O1"] = {"tx": txs, "sha": {k: rm.sha256_bytes(im[k]) for k in IMAGES}}
    g62.WORK = WORK / "g6p2"
    g62.WORK.mkdir(parents=True, exist_ok=True)
    rc_neg = g62.negtest()
    neg = json.loads((g62.WORK / "negtest" / "summary.json").read_text())
    rc_chk = g62.check()
    off = json.loads((g62.WORK / "offline.json").read_text())
    p1.WORK = WORK
    det["g6p2_negtest"] = {k: neg[k].get("passed") if isinstance(neg.get(k), dict) else neg.get(k)
                           for k in ("dev", "prod", "g6p1_negtest_rc")}
    det["g6p2_check"] = off["checks"]
    res["O2_resource_consistency"] = rc_neg == 0 and neg["dev"]["passed"] == neg["dev"]["cases"]
    res["O3_O4_ownership_fixups"] = rc_chk == 0 and all(off["checks"][k] for k in (
        "O1_g4_equivalence", "O2_identity_hierarchy", "O3_brain_mind_instance", "O4_designer_script",
        "O5_relocations_fixups", "O6_transaction_budget"))
    # O5: the reader's relative addresses on the compiled image (as the loader relocates own-file words)
    lvl, ptr = im["lvl"], im["ptr"]
    slots, _ = g4c.index(lvl, ptr)
    u = lambda o: struct.unpack_from(">I", lvl, o)[0]   # noqa: E731
    t = lambda o: u(o) + 4 if slots.get(o) == 1 else None   # noqa: E731
    o5 = {"d3": t(FC + 0x80), "brain": t(FC + 0x80 + 0xC), "mind": t(FC + g4c.BRAIN), "intel": t(FC + g4c.MIND + 4),
          "dsgmem_ini": t(FC + g4c.DSGMEM + 4), "dsgmem_cur": t(FC + g4c.DSGMEM + 8), "model": t(FC + g4c.DSGMEM)}
    rel = {k: (v - FC if v is not None and FC <= v < FC + BLK else None) for k, v in o5.items()}
    det["O5"] = {k: (hex(v) if v is not None else None) for k, v in rel.items()}
    src_model = t(SRC + g4c.DSGMEM)
    res["O5_lifecycle_observation"] = (rel["d3"] == 0xAC and rel["brain"] == g4c.BRAIN and rel["mind"] == g4c.MIND
                                       and rel["intel"] == g4c.INTEL and rel["dsgmem_ini"] == g4c.INI
                                       and rel["dsgmem_cur"] == g4c.CUR and o5["model"] == src_model
                                       and rel["model"] is None and r3.OBSERVE is observe and p4b.SAMPLER is Sampler)
    rc_pre = p4b.preflight()
    pre = json.loads((WORK / "preflight.json").read_text())
    det["preflight"] = pre["res"]
    res["O6_recovery_compatibility"] = rc_pre in (0, None) and pre["pass"] and len(pre["res"]) == 14
    res["O7_backward_compatibility"] = (neg.get("g6p1_negtest_rc") == 0 and neg["prod"]["passed"] == neg["prod"]["cases"]
                                        and off["checks"]["O8_backward_compatibility"] and pre["res"]["production_refuses"])
    out = {"res": res, "details": det, "pass": all(res.values())}
    (WORK / "check.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1))
    print("CHECK_G6P2B", "PASS" if out["pass"] else "FAIL", f"{sum(res.values())}/{len(res)}")
    return 0 if out["pass"] else 1


def gate_patched():
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    return st.stdout.strip() == "patched"


def reload(tag):
    if not gate_patched():
        raise SystemExit("the development gate is not applied")
    if not json.loads((WORK / "check.json").read_text())["pass"]:
        raise SystemExit("check did not pass")
    setup()
    before = p4b.protected()
    row = r3.run_case(tag, "ra")
    (WORK / tag / "protected.json").write_text(json.dumps({"before": before, "after": p4b.protected()}) + "\n")
    print(json.dumps(row, default=str)[:2000])
    return 0


def recover(tag):
    if not gate_patched():
        raise SystemExit("the development gate is not applied")
    if not json.loads((WORK / "check.json").read_text())["pass"]:
        raise SystemExit("check did not pass")
    setup()
    return p4b.run(tag)


# --- judgement helpers ---------------------------------------------------------------------------------------------

def registration(live, ab):
    """L2: lists (G6-P1b's test with the Frog's name) and the copy's own records."""
    lst = live.get("lists", {})
    reg = g6b.registered(lst, ab, g6b.reference_union())
    a = live.get("actors") or {}
    sa, ca = a.get("src") or {}, a.get("copy") or {}
    lv = lambda fo: ab + fo - 4   # noqa: E731
    own = bool(sa and ca and ca["dsgvar"] == sa["dsgvar"] == lv(g4c.MODEL + 8)
               and ca["ini"] == lv(FC + g4c.INI) and ca["cur"] == lv(FC + g4c.CUR) and ca["mind0"] == sa["mind0"]
               and ca["dsgmem"] == lv(FC + g4c.DSGMEM) and ca["mind_dsgmem"] == ca["dsgmem"]
               and ca["brain"] == lv(FC + g4c.BRAIN) and ca["mind"] == lv(FC + g4c.MIND)
               and ca["intel"] == lv(FC + g4c.INTEL) and ca["d3"] == lv(FC + 0xAC) and ca["brain4"] == sa["brain4"]
               and ca["events"] == sa["events"] and len(ca["events"]) == 8 and g4c.RAW_EVENT not in ca["events"]
               and sa["ini"] == lv(SRC + g4c.INI) and sa["cur"] == lv(SRC + g4c.CUR))
    bl = live.get("blocks", {})
    sl, cl = bytes.fromhex(bl.get("src", "")), bytes.fromhex(bl.get("copy", ""))
    w = lambda x, k: struct.unpack_from(">I", x, k)[0]   # noqa: E731
    s_lo, c_lo = ab + SRC_REL, ab + COPY_REL
    # revision 2: the engine's runtime actor-list node at block +0x500 {-> owner SO, next node, previous node} links
    # neighbours; the copy follows the source there as in the sibling chain. Allowed exactly: source +0x504 -> copy
    # +0x500 and copy +0x508 -> source +0x500, with each node's owner word naming its own actor. Nothing else.
    node = (len(sl) == BLK and len(cl) == BLK and w(sl, 0x500) == s_lo and w(cl, 0x500) == c_lo
            and w(sl, 0x504) == c_lo + 0x500 and w(cl, 0x508) == s_lo + 0x500)
    c_ok, s_ok = {0x18} | ({0x508} if node else set()), {0x14} | ({0x504} if node else set())
    alias = (len(sl) != BLK or len(cl) != BLK
             or any(s_lo <= w(cl, k) < s_lo + BLK and k not in c_ok for k in range(0, BLK, 4))
             or any(c_lo <= w(sl, k) < c_lo + BLK and k not in s_ok for k in range(0, BLK, 4)))
    return {"lists": reg, "own": own, "no_alias": not alias, "runtime_node_link": node, "ok": bool(reg and own and not alias),
            "copy": {k: (hex(v) if isinstance(v, int) else v) for k, v in ca.items() if k != "events"}}


def script(samples, lo):
    """L3 / L6 / R3: the copy's script on its own schedule, judged in AI runs."""
    sm = [s for s in samples if "copy" in s and "src" in s]
    out = {"n": len(sm)}
    if len(sm) < 2:
        return dict(out, ok=False)
    c = [s["copy"] for s in sm]
    Ps = sorted({x["P"] for x in c})
    changes, bad_run, inwin, vals = [], 0, [], []
    for i in range(1, len(sm)):
        a, b = c[i - 1], c[i]
        if b["v8"] != a["v8"] and b["v8"]:
            changes.append(b["runs"])
            vals.append(b["v8"])
            if b["runs"] == a["runs"]:
                bad_run += 1
            inwin.append(sm[i - 1]["timer"] <= b["v8"] <= sm[i]["timer2"])
    riv = [(y - x) % 65536 for x, y in zip(changes, changes[1:])]
    P = Ps[0] if len(Ps) == 1 else None
    ms = m_set(P) if P else set()
    srcv8 = [s["src"]["v8"] for s in sm]
    out.update(P=Ps, updates=len(vals), distinct=len(set(vals)), run_intervals=sorted(set(riv)),
               off_model=[x for x in riv if x not in ms], run_without_ai=bad_run, inwin=all(inwin) if inwin else False,
               beh_ok=all(x["beh"] == lo for x in c), copy_v5=sorted({(x["ini_v5"], x["cur_v5"]) for x in c}),
               src_v5=sorted({(s["src"]["ini_v5"], s["src"]["cur_v5"]) for s in sm}), runs_first=c[0]["runs"],
               runs_last=c[-1]["runs"], first={"timer": sm[0]["timer"], **c[0]}, src_P=sorted({s["src"]["P"] for s in sm}))
    out["ok"] = bool(out["beh_ok"] and out["distinct"] >= 10 and out["inwin"] and P is not None and 28 <= P <= 35
                     and bad_run == 0 and not out["off_model"] and riv and out["copy_v5"] == [(500, 500)]
                     and out["src_v5"] == [(500, 500)] and set(vals) != {v for v in srcv8 if v})
    return out


# --- judgements ----------------------------------------------------------------------------------------------------

def judge_reload(tag):
    setup()
    run = f"{PREFIX}_{tag}_ra"
    ra = g6b._load(WORK / tag / "ra", run)
    rb = g6b._load(*CONTROL)
    ra["judges"] = {t: subprocess.run([sys.executable, str(TOOLS / t), "--run", run], cwd=ROOT, capture_output=True,
                                      text=True).returncode
                    for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py")}
    det, L = {}, {}
    b = iter(ra["bursts"])
    route = (all(any(n == s for s in b) for n in ("menumap", "intro_10", "intro_10")) and len(ra["entries"]) >= 2
             and ra["phases"]["e2"] is not None)
    if not route:
        res = {"verdict": "INVALID-ROUTE", "bursts": ra["bursts"], "entries": len(ra["entries"])}
        (WORK / f"judgement_reload_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
        print(json.dumps(res, indent=1, default=str))
        return 1
    log = ra["log"]
    lines = log.splitlines()
    ptx = p1.parse_plan((WORK / tag / "ra" / "plan_copy.txt").read_text(encoding="utf-8"))["txs"]
    want_tx = [tuple(ptx[0].split(" ")[2:5])] if ptx else None
    tx = [tuple(x) for x in re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log)]
    g6l = re.findall(r"G6P1 level-tx version=(\d+) members=(\S+)", log)
    snaps = re.findall(r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", log)
    snap_sizes = {f: b_ for f, _, b_, _ in snaps}
    first = {k: next((i for i, ln in enumerate(lines) if k in ln), None)
             for k in ("M33 mods state=active", "G5P3 tx snapshot", "G5P3 tx read")}
    L["L1_first_load_transaction"] = bool(
        log.count("M33 mods state=active") == 1 and tx == want_tx and want_tx == [("intro_10", g62.MOD, TX)]
        and g6l == [("2", "lvl,ptr,transit")] and sorted((f, b_) for f, _, b_, _ in snaps) == SNAP
        and all(d == "3" for *_, d in snaps) and None not in first.values()
        and first["G5P3 tx snapshot"] < first["G5P3 tx read"] and first["M33 mods state=active"] < first["G5P3 tx read"])
    ent = {}
    for i, e in enumerate(ra["entries"][:2], 1):
        lv = e.get("live", {})
        reg = registration(lv, e["ab"])
        sc = script(e["samples"], lv.get("loop_oneshot"))
        ent[i] = {"ab": hex(e["ab"]), "length": e["length"], "reg": reg, "script": sc,
                  "left_t": e.get("left_t"), "t": e["t"], "live_error": lv.get("error") or lv.get("actors_error")}
    det["entries"] = ent
    L["L2_first_load_registration"] = ent[1]["reg"]["ok"] and ent[1]["length"] == AREA + N
    L["L3_first_load_script"] = ent[1]["script"]["ok"]
    passes = re.findall(r"G5P3 tx pass file=(\S+) pass=(\d+) reads_before=\d+ image_bytes=(\d+)", log)
    det["tx_passes"] = {f: sum(1 for x, _, _ in passes if x == f) for f, _ in SNAP}
    ph = ra["phases"]
    e1, e2 = ra["entries"][0], ra["entries"][1]
    gl = ra.get("process_left")
    L["L4_genuine_reload"] = bool(e1.get("left_t") is not None and e1["left_t"] <= e2["t"]
                                  and ph["fix_between"] is not None and all(n >= 2 for n in det["tx_passes"].values())
                                  and ra["runner_exit"] == 0 and gl is False)
    s1, s2 = ent[1]["script"], ent[2]["script"]
    f2 = s2.get("first", {})
    fresh = bool(f2 and s1.get("runs_last") is not None and f2["runs"] < s1["runs_last"] and f2["runs"] <= 60
                 and f2["beh"] == (e2.get("live") or {}).get("loop_oneshot") and (f2["ini_v5"], f2["cur_v5"]) == (500, 500)
                 and 0 < f2["v8"] <= f2["timer"] and f2["timer"] - f2["v8"] <= 2 * max(s2["P"] or [35]) * F + 100)
    det["fresh"] = {"entry2_first": f2, "entry1_runs_last": s1.get("runs_last"), "ok": fresh}
    L["L5_second_load_registration_fresh_state"] = ent[2]["reg"]["ok"] and ent[2]["length"] == AREA + N and fresh
    L["L6_second_load_script"] = s2["ok"]
    D = {k: r3.diff(r3.brief(ph[k]), r3.brief(rb["phases"][k]))
         for k in ("menu_before", "e1", "e2", "fix_between", "menu_after")}

    def norm(x):
        bb = r3.brief(x)
        return bb and {k: bb[k] for k in ("free", "largest", "alloc", "free_chunks")} | {
            "areas": sorted(bb["areas"].values())}
    within = {"e1_eq_e2": norm(ph["e1"]) == norm(ph["e2"]),
              "menu_before_eq_after": norm(ph["menu_before"]) == norm(ph["menu_after"]),
              "fix_between": norm(ph["fix_between"]) == norm(rb["phases"]["fix_between"])
              and (ph["fix_between"] or {}).get("free_bytes") == g6b.FIX_ONLY_FREE}
    want = {"area1_length": N, "free": -N, "largest": -N}
    host = sum(int(b_) for b_ in snap_sizes.values())
    st = ra["states"]
    i0 = next((i for i, x in enumerate(st) if "invalid" not in x), None)
    bad = [x for x in (st[i0 + 1:] if i0 is not None else []) if "invalid" in x]
    windows = [(e["t"], e.get("left_t") or 1e9) for e in ra["entries"][:2]]
    walk_ok = (i0 is not None and all(x["invalid"] == "changed" for x in bad) and len(bad) <= 2
               and not any(a <= x["t"] <= b_ for x in bad for a, b_ in windows))
    det["memory"] = {"D": D, "within": within, "host_snapshot_bytes": host, "changed": [x["t"] for x in bad],
                     "phases": {k: r3.brief(v) for k, v in ph.items() if isinstance(v, dict)}}
    L["L7_memory_transaction_consistency"] = bool(
        walk_ok and D["menu_before"] == {} and D["e1"] == want and D["e2"] == want and D["fix_between"] == {}
        and D["menu_after"] == {} and all(within.values()) and host == HOST_BYTES
        and len(tx) == 1 and len(snaps) == 3 and "G5P3 tx host_changed" not in log
        and not re.search(r"M36 grow read file=(intro_10\.(lvl|ptr)|transit\.lvl)", log)
        and all(b_ == snap_sizes.get(f) for f, _, b_ in passes) and (e1["ab"], e1["length"]) == (e2["ab"], e2["length"]))
    rj = ra["run_json"]
    prot = json.loads((WORK / tag / "protected.json").read_text())
    mb = ra["marker_before_start"]
    det["fault_counts"] = {"run": g6b.fault_counts(run), "control": g6b.fault_counts(CONTROL[1])}
    L["L8_safety"] = bool("M23 haptics policy=suppressed physical_pad_drivers=none" in log
                          and not any(ra["judges"].values()) and ra["runner_exit"] == 0 and gl is False
                          and det["fault_counts"]["run"] == det["fault_counts"]["control"]
                          and rj.get("game_foreground_events") == 0 and rj.get("game_foreground_samples") == 0
                          and mb[0] == "armed" and mb[1]["session"] == run and mb[1]["plan_sha256"] == ra["plan_sha256"]
                          and ra["controlled"] is True and ra["session_end"]["cleared"] is True
                          and ra["marker_after"] == "none" and prot["before"] == prot["after"])
    det["safety"] = {"judges": ra["judges"], "foreground": (rj.get("game_foreground_events"),
                                                            rj.get("game_foreground_samples")),
                     "session_end": ra.get("session_end"), "tx": tx, "g6p1": g6l, "snapshots": snaps,
                     "process_detail": ra.get("process_detail")}
    ok = all(L.values())
    if ok:
        verdict = "RELOAD VERIFIED"
    elif all(v for k, v in L.items() if k != "L6_second_load_script"):
        verdict = "PARTIAL — RELOAD SCRIPT UNVERIFIED"
    else:
        verdict = "NOT PASSED"
    res = {"L": L, "verdict": verdict, "details": det}
    (WORK / f"judgement_reload_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({"L": L, "verdict": verdict}, indent=1, default=str))
    return 0 if ok else 1


def judge_recover(tag):
    setup()
    p4b.judge(tag)
    j = json.loads((WORK / f"judgement_{tag}.json").read_text())
    Rp, det = j["R"], j["details"]
    ev = json.loads((WORK / tag / "evidence.json").read_text())
    ph = {}
    for k in ("A", "C"):
        w = WORK / tag / k
        if (w / "row.json").is_file():
            ph[k] = {n: json.loads((w / f"{n}.json").read_text()) for n in ("row", "live", "samples", "states")}
            run = ph[k]["row"]["run"]
            ph[k]["log"] = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / run).glob("runtime*.log")))
            mf = RUNS / run / "m2_faults.log"
            ph[k]["faults"] = sorted(set(re.findall(r"M2 exception code=([0-9A-Fa-f]+)", mf.read_text(
                errors="replace")))) if mf.is_file() else []
    A, C = ph.get("A"), ph.get("C")
    ref = g6b.reference_union()
    R = {}
    alog = A["log"] if A else ""
    snaps = re.findall(r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", alog)
    o = det.get("ordering", {})
    from datetime import datetime

    def ts(x):
        try:
            return datetime.fromisoformat(x) if x and x != "None" else None
        except ValueError:
            return None
    tm, tp_, tg = (ts(o.get(k)) for k in ("marker_mtime", "process_created", "first_grow_size"))
    R["R1_marker_ordering"] = bool(A and tm and tp_ and tg and tm < tp_ < tg
                                   and alog.count("G5P1 level-tx active level=intro_10") == 1
                                   and len(re.findall(r"G6P1 level-tx version=2 members=lvl,ptr,transit", alog)) == 1
                                   and len(snaps) == 3)
    lv = (A or {}).get("live") or {}
    ab = lv.get("ab")
    reg = registration(lv, ab) if ab else {"ok": False}
    R["R2_activation"] = bool(A and ab and sorted((f, b_) for f, _, b_, _ in snaps) == SNAP and reg["ok"])
    kill_t = (A or {}).get("row", {}).get("kill_t")
    sm = [x for x in (A or {}).get("samples", []) if kill_t is None or x["t"] <= kill_t]
    sc = script(sm, lv.get("loop_oneshot"))
    R["R3_script_before_termination"] = bool(sm and kill_t is not None and sc.get("beh_ok") and sc.get("updates", 0) >= 3
                                             and sc.get("run_without_ai") == 0 and sc.get("inwin"))
    det["A_registration"], det["A_script"] = reg, {k: v for k, v in sc.items() if k != "first"}
    R["R4_ownership"] = Rp["R1_session_ownership"]
    R["R5_forced_termination"] = Rp["R4_abnormal_termination"]
    R["R6_marker_persistence"] = Rp["R5_marker_persistence"]
    cl = C["log"] if C else ""
    R["R7_whole_transaction_refusal"] = bool(
        C and ev["C_plan"]["codes"] == {g62.MOD: "STRUCTURAL_RECOVERY"} and ev["C_plan"]["structural_recovery"] == "armed"
        and not ev["C_plan"]["structural_marker"] and not ev["C_plan_has_tx"] and cl.count("M33 mods state=active") == 1
        and not re.search(r"G5P1|G5P3|G6P1|M36 grow", cl) and not re.search(r"M33 mods served mod=\S+ file=transit\.lvl", cl)
        and ev["marker_after_C"] == ev["marker_A"]["sha256"])
    clv = (C or {}).get("live") or {}
    cab = clv.get("ab")
    R["R8_original_state_ordinary_mod"] = bool(
        C and cab and g6b.registered(clv.get("lists", {}), cab, ref, grown=False)
        and any(s.get("areas", {}).get("1", {}).get("length") == AREA for s in C["states"] if "invalid" not in s)
        and Rp["R7_nonstructural"])
    R["R9_isolation_and_clear"] = Rp["R8_profile_isolation"] and Rp["R9_explicit_recovery"]
    R["R10_production_desktop"] = bool(Rp["R10_production_desktop"] and C and set(C["faults"]) <= {"406D1388"})
    det["faults"] = {k: v.get("faults") for k, v in ph.items()}
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
    if ok_tag and a[0] == "reload":
        return reload(a[1])
    if ok_tag and a[0] == "recover":
        return recover(a[1])
    if ok_tag and a[0] == "judge-reload":
        return judge_reload(a[1])
    if ok_tag and a[0] == "judge-recover":
        return judge_recover(a[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
