#!/usr/bin/env python3
"""E-485 (D-252) G6-P1b: G6-P1's development-only passive lum (mod `g6p1.lum`, one `level-tx 2` over intro_10.lvl,
intro_10.ptr and transit.lvl; G4b's additional NIN_m_Lums_Int10 at `flight_path`) through G5-P3's same-process
Pause -> Load reload and G5-P4b's ownership-checked abnormal termination and recovery.

usage:
  g6p1b_lifecycle.py check          offline O1-O7 (no game)
  g6p1b_lifecycle.py reload TAG     phase 1: one hidden run of G5-P3's route with the lum mod (case ra)
  g6p1b_lifecycle.py recover TAG    phase 2: G5-P4b's phases A (armed launch, registration and collection, forced
                                    termination), C (recovery launch), D (explicit clear)
  g6p1b_lifecycle.py judge-reload TAG / judge-recover TAG
Outputs stay under private/work/e485/.

REUSED MECHANISMS: g5p3_reentry.run_case (route, steps, entry detection, block-8 snapshots, discovery, generator) and
  g5p4b_recovery (preflight, plan / complete through tools\\play.ps1's functions, launch, ownership-checked kill, phase
  runner, judge). Their only change (committed with this file): optional module hooks OBSERVE / SAMPLER (and
  KILL_READY in g5p4b_recovery) that default to None = the graph walk, variable-8 sample and site-pass trigger
  exactly as before. Here they observe the lum instead of the graph: at each intro_10 entry (after the discovery
  probe, the point where the graph was walked) the dynamic and inactive dynamic worlds, the SO-record list, the backup
  list and the personal object-type list (G4b's reads: globals 0x82C05F48, 0x82C07D78, 0x82876314, 0x82C44A78,
  0x82C061E0) and the source / copy blocks; every 0.1 s generator variables 5 (lum count) and 8 and its position;
  every 1 s both blocks; once, 2 s after variable 5 first changes in the entry, the lists again (post-collection).
  The termination of phase 2 waits for variable 5's first change (the collection), then 3 s, at most 45 s after the
  area appears (else INVALID, nothing killed).
ROUTE vs COLLECTION (checked before this protocol, from retained runs): in E-484 h1 the generator collected the new
  lum 8.8 s after intro_10's area appeared (area 2.9 s, pickup 11.7 s; direct --test-level load). G5-P3's route keeps
  load 1 for about 38 s (E-479 r2 rb: area 42.4 s, Pause -> Load at the 20 s step after the file opens, the area left
  at 80.9 s) and load 2 for about 48 s (81.0 -> 129.3 s); the flight timing from the area's appearance is the same
  on this route (E-483 l2: node 13 at +6.2 s in both). The legitimate route therefore reaches the lum in BOTH loads
  with the existing guest-scoped inputs (no new input, no state write). Load 2 starts from the saved state (the save
  entry `intro_10_fresh` was written before any lum was collected), so its lum count restarts at 0.

OFFLINE (check), before any build:
  O1 resource identity: the compiled lum images are G6-P1's (.lvl cbf9fce3..., .ptr 09d81158..., transit
     321de2e4...; 7,663,280 / 209,388 / 41,508) and the plan's transaction is `level-tx 2 intro_10 g6p1.lum
     ccb07d2f770147cb`.
  O2 three-member integrity / immutable snapshots: on private copies of the three files (identical bytes, so the
     allow-listed name, size and hash match), the development header serves the declared images after each member
     is changed ON DISK after activation (flip_transit, flip_lvl, flip_ptr between opens), and refuses the whole plan
     (tx_identity, nothing served) when transit.lvl is changed before activation.
  O3 repeated and reversed opens: the copies opened transit, transit, ptr, lvl, ptr, transit give the images every
     time (sizes and bytes); G6-P1's negtest cases (three orders, a repeated transit) re-run.
  O4 fail-closed: G6-P1's negtest re-run (missing / tampered / wrong-hash / grown / plain-range transit, missing lvl
     or ptr, partial words, version 1 with transit, version 3, corrupt id, two transactions, gate off, other level;
     production unknown_record).
  O5 actor structure: G6-P1's check re-run (8 / 8: G4b equivalence, personal index 69, registration, 40 relocation
     entries, transaction, budget, negatives, compatibility).
  O6 recovery compatibility: G5-P4b's preflight with g6p1.lum (14 checks: orderly-exit decision, arm at plan,
     synthetic abnormal child keeps the marker, wrong owner not terminated, concurrent launch refused, other session /
     wrong plan cannot clear, malformed marker, orderly exit clears, exit 0 alone keeps, profile-scoped clear,
     production refusal of the version-2 plan, play.ps1 -DryRun, G5-P2b R1-R8).
  O7 backward compatibility: G6-P1 check O8 (f0fe6ac compiler identity for version 1, selftest), G5-P5 check 43 / 43
     and negtest (G5-P1, G5-P2a, G5-P3), all re-run into e485.

PROSPECTIVE PROTOCOL (committed before the development build and any modified run)
Build: g5p1_dev_gate.py apply + tools\\build_incremental.bat; production restored afterwards (revert + rebuild).
PHASE 1 (reload), run e485_TAG_ra: G5-P3's route exactly (disposable copy of the save entry intro_10_fresh; Title ->
  Load -> intro_10; 20 s after the file opens Pause -> Load -> Yes -> intro_10 again in the same process; 30 s later
  Pause -> Exit Game -> title; 220 s; guest-scoped input, hidden, non-activating, muted, no captures). Plan: g6p1.lum
  only (flight_path), resolve_all with session = run (marker armed), R3HD_DEV_STRUCTURAL_TX=intro_10; the harness ends
  the session after a controlled exit. Control: NOT re-run: E-479 r2 rb (same route and runner, no plan; a no-plan run
  never reaches the transaction code). Reference actor set: E-484 h1 base's first-read union of both worlds (66
  SuperObjects, offsets relative to the level area; the same file and level).
  Route valid: load bursts menumap, intro_10, intro_10 in order and two intro_10 entries observed; otherwise
  INVALID-ROUTE (no verdict; documented and corrected before a fresh tag).
  L1 first-load transaction: one `M33 mods state=active`; exactly one `G5P1 level-tx active` = the plan's (intro_10,
     g6p1.lum, its id) and one `G6P1 level-tx version=2 members=lvl,ptr,transit`; `G5P3 tx snapshot` exactly
     intro_10.lvl 7,663,280, intro_10.ptr 209,388, transit.lvl 41,508 (image bytes), disk_reads=3, all before the
     first `G5P3 tx read`.
  L2 first-load registration (entry 1 first read): area length 7,661,832 + 1,444; union of both worlds = the
     reference + the copy (offsets relative to the area), no duplicates, both walks' previous links hold; SO records
     count = walk = 123 with the copy's last; the backup list holds the copy's matrix; personal count 70, last name
     NIN_m_Lums_Int10_G4B; the copy's 3dData buffer word non-zero and different from the source's; Brain +4 0xCDCDCDCD
     in both; no copy word points into the source's block except +0x18 and no source word into the copy except +0x14.
  L3 first-load collection (expectation: one collection, at about +9 s): variable 5 starts at 0 and changes exactly
     once in entry 1, 0 -> 1; generator within 3.0 units of the copy's position within 2 s of the change; across that
     change the copy changes >= 1 block offset the source does not; the post-collection lists: union = reference +
     copy without duplicates, records 123 (copy last), personal 70, the copy's matrix in the backups.
  L4 genuine reload: route valid; entry 1 left before entry 2 appeared, with a fix-only block-8 state between them;
     `G5P3 tx pass` >= 2 for each of the three members; one game process for the whole run, runner exit 0.
  L5 second-load registration (entry 2 first read): L2's criteria (an address equal to entry 1's after a proper
     release is not aliasing); variable 5 starts at 0 again.
  L6 second-load collection: L3's criteria in entry 2 (exactly one 0 -> 1 change, distance, pickup-specific offsets,
     post-collection lists).
  L7 memory and transaction consistency: valid block-8 walks after the first valid snapshot; versus the control
     D(menumap before) = {}, D(entry 1) = D(entry 2) = {area1_length +1444, free -1444, largest -1444}, D(fix between) =
     {}, D(menumap after) = {}; within the run entry 1 = entry 2 (area slots ignored), menumap before = after, fix
     between = the control's fix-only state (20,795,836 free); one level-tx line, exactly three snapshot lines (no
     re-snapshot), no `G5P3 tx host_changed`, no `M36 grow read` naming a member, every `G5P3 tx pass` image_bytes
     equal to its member's snapshot; entries 1 and 2 have the same area base and length; host snapshot images
     7,663,280 + 209,388 + 41,508 = 7,914,176 bytes (<= 16 MiB, not block 8).
  L8 safety: M21 / M22 / M23 0, haptics policy line, runner exit 0; run.json game_foreground_events =
     game_foreground_samples = 0; m2_faults.log codes only 406D1388; no game process left (D-250 ownership check,
     g3a.game_left); the marker armed before the start (session = run, plan SHA-256) and cleared by the controlled
     end; G5-P4b's protected() equal before / after.
  If L3 holds but L6's collection is not observed while L5 holds: PARTIAL — COLLECTION AFTER RELOAD UNVERIFIED.
PHASE 2 (recovery), tag TAG: G5-P4b's phases with mods root RA = g6p1.lum + e478.lums-6 (generator variable 5 = 6,
  an ordinary designer-default), RB = g6p1.lum only (isolation witness); A 140 s, termination 3 s after variable 5
  first changes (6 -> 7, the collection), at most 45 s after the area appears; C 110 s; D clear / dry run / re-arm /
  clear. `--test-level intro_10` (G5-P4b's launch).
  R1 marker ordering: marker mtime < game process creation < first `M36 grow size` naming intro_10; A's log has one
     `G5P1 level-tx active`, one `G6P1 level-tx version=2` and exactly three `G5P3 tx snapshot` lines.
  R2 version-2 activation: A's snapshots are the three members' image sizes above; A's first read: union = reference +
     copy, records 123 (copy last), personal 70, the copy's matrix in the backups; variable 5 6 -> 7 before the kill.
  R3 ownership: G5-P4b R1 (marker session e485_TAG_A and RA's plan SHA-256; the terminated pid passed every check:
     r3hd.exe, the runner's exe path, this run's --log_file, created after the runner start, grandparent = the runner).
  R4 forced termination, R5 marker persistence: G5-P4b R4 / R5 unchanged.
  R6 whole-transaction refusal: C's plan refuses g6p1.lum with STRUCTURAL_RECOVERY, the recovery state armed, no
     level-tx / tx-file in the plan; C's log has no `G5P1`, `G5P3`, `G6P1` or `M36 grow` line and no `M33 mods served`
     naming transit.lvl (the same-size edit is refused too); marker unchanged after C.
  R7 original actor state: C's first read: union = the reference (no copy), records 122, personal 69; intro_10's area
     7,661,832 bytes.
  R8 ordinary mod: G5-P4b R7 (e478.lums-6 active in A and C, served in intro_10.lvl, C leaves for intro_15).
  R9 isolation and clear: G5-P4b R8 and R9 (RB never marked and still lists g6p1.lum; clear, dry run lists it, the
     stamp-D plan carries its level-tx and arms e485_TAG_D, final clear).
  R10 production and desktop safety: G5-P4b R10 (production refusal in preflight, protected files equal, game
     foreground events / samples 0, monitor clean, M21-M23 0, no process left, C exit 0) and A's / C's m2_faults.log
     codes only 406D1388 apart from A's termination.
REVISION 1 (after reload run l1; l1 stays as judged: L1-L6 PASS, L7 and L8 FAIL, NOT PASSED; its judgement is kept):
  l1's functional results: the lum registered in both loads (same area base 0x40F5509C, union = reference + copy,
  records 123, personal 70, own 3dData buffer, no aliases) and was collected exactly once in each (0 -> 1 at +8.42 s
  and +8.44 s after the area appeared, 0.506 / 0.006 units); D(entry 1) = D(entry 2) = +1,444 area / -1,444 free, fix
  between = the control, menumap after = before; three snapshots, two passes per member, no host change.
  Causes (harness assumptions, not the transaction or the actor):
  (a) L8's exception rule ("only 406D1388") was taken from direct-load runs. On this route every run has two host
      exceptions code E0473458 raised from guest function 820EB7D8: the no-mod control E-479 r2 rb, E-479 r2 ra and
      E-483 l2 ra each have exactly 406D1388 x 1 + E0473458 x 2, as l1 does. Revised L8: the run's exception codes and
      counts equal those of the same-route no-mod control (E-479 r2 rb).
  (b) L7's "every snapshot after the first valid one valid" failed on one snapshot block8_probe marked `changed` (its
      torn-read guard: the area table or allocator descriptor changed during the copy, three retries) at 9.1 s, during
      the title's boot before any level was opened; the next snapshot 16 ms later is valid; no walk error (tiling or
      area) anywhere. 1 of 105 retained runs shows one. Revised L7: every snapshot after the first valid one is valid
      or marked `changed` (any other reason still fails), at most two `changed`, and none while intro_10 is loaded.
  Nothing else changes (route, steps, plan, other criteria, thresholds). Fresh reload run: l2. The recovery phase has
  not run; its criteria are unchanged.
Class: L1-L8 and R1-R10 PASS = G6-P1b VERIFIED — PASSIVE ACTOR LIFECYCLE & RECOVERY. Stop conditions (partial
activation, missing / duplicated actor, invalid instance state, corrupted lists, retained memory, marker cleared after
the kill, structural data in recovery, other process terminated, focus theft) stop the affected phase; results kept.
"""
import json
import math
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
import g4b_ab as g4b  # noqa: E402
import block8_probe as bp  # noqa: E402
import g5p1_pilot as p1  # noqa: E402
import g5p3_reentry as r3  # noqa: E402
import g5p4b_recovery as p4b  # noqa: E402
import g6p1_pilot as g6  # noqa: E402

PREFIX = "e485"
WORK = ROOT / "private" / "work" / PREFIX
RUNS = g3a.RUNS
SIZE, PSIZE, AREA = g3a.SIZE, g3a.PSIZE, g3a.AREA
N, K, TSIZE = g6.N, g6.K, g6.TSIZE
CONTROL = ROOT / "private" / "work" / "e479" / "r2" / "rb", "e479_r2_rb"
REF = ROOT / "private" / "work" / "e484" / "h1" / "base" / "row.json"
G6_IMAGES = {"lvl": "cbf9fce38e8735c39f4190f0bf833dfa87785f2b9ab0c95a0c9902e0217eaf2c",
             "ptr": "09d81158842462166a202b29ec07f159b792b6b8945ae1ed60d9a202a2907ce5",
             "transit": "321de2e4be2077720e8a6cc6660ff373bcabaed6c5089989a1ed594aa370c34e"}
TX_G6 = "ccb07d2f770147cb"
FIX_ONLY_FREE = 20795836
SRC, BLK = g4b.SRC, g4b.BLK
FC = SIZE + (SRC % 16 - SIZE % 16) % 16          # the copy's file offset (7,661,840)
COPY_REL, SRC_REL = FC - 4, SRC - 4              # SuperObject addresses relative to the area base
G_DW, G_INACT, G_REC, G_BAK, G_OBJ = g4b.G_DW, g4b.G_INACT, g4b.G_REC, g4b.G_BAK, g4b.G_OBJ
NEW_NAME = g6.NEW_NAME
SNAP = [("intro_10.lvl", str(SIZE + N)), ("intro_10.ptr", str(PSIZE + 8 * K)), ("transit.lvl", str(TSIZE))]


# --- live observation (hooks of the reused runners) -------------------------------------------------------------

def read_lists(p):
    """G4b's list reads (g4b_ab.run_case): both worlds, SO records, backup links, personal count and last name."""
    def w(a):
        x = p.words(a, 1)
        if not x:
            raise ValueError(f"read {a:#x}")
        return x[0]
    r = {}
    try:
        for key, g in (("dw", G_DW), ("inactive", G_INACT)):
            wo = w(g)
            walk, so = [], w(wo + 8)
            while so and len(walk) < 400:
                walk.append(so)
                so = w(so + 0x14)
            r[key] = {"count": w(wo + 0x10), "walk": walk,
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
        r["personal"] = {"count": pc, "last_name": nm.split(b"\0")[0].decode("ascii", "replace") if nm else None}
    except Exception as x:
        r["error"] = repr(x)
    return r


def read_blocks(p, ab):
    a1 = (bp.areas(p) or {}).get(1)
    out = {"src": (p.read(ab + SRC_REL, BLK) or b"").hex()}
    if a1 and a1["base"] == ab and a1["end"] - a1["base"] == AREA + N:
        out["copy"] = (p.read(ab + COPY_REL, BLK) or b"").hex()
    return out


def observe(rd, p, ab):
    return {"lists": read_lists(p), "blocks": read_blocks(p, ab)}


class Sampler:
    """Per entry: variables 5 and 8 and the generator's position every call (0.1 s); both blocks every 1 s; the lists
    once, 2 s after variable 5 first changes."""

    def __init__(self, p, ab):
        self.p, self.ab, self.next_blocks, self.first, self.change_t, self.after_done = p, ab, 0.0, None, None, False

    def __call__(self, gen, t):
        v = gen.dsg()
        v5 = v[5][0][v[5][1]]
        out = {"v5": v5, "v8": g3a.u32(*v[8]), "pos": gen.position()}
        if self.first is None:
            self.first = v5
        if self.change_t is None and v5 != self.first:
            self.change_t = t
        if t >= self.next_blocks:
            out.update(read_blocks(self.p, self.ab))
            self.next_blocks = t + 1.0
        if self.change_t is not None and not self.after_done and t >= self.change_t + 2.0:
            self.after_done = True
            out["lists_after"] = read_lists(self.p)
        return out


def kill_ready(samples):
    return bool(samples) and any(x["v5"] != samples[0]["v5"] for x in samples)


def setup():
    WORK.mkdir(parents=True, exist_ok=True)
    p1.WORK = WORK
    r3.PREFIX, r3.WORK = PREFIX, WORK
    r3.PLAN_MOD = (g6.MOD, lambda: [g6.lum("on")])
    r3.AREA10 = (AREA, AREA + N)
    r3.OBSERVE, r3.SAMPLER = observe, Sampler
    p4b.PREFIX, p4b.WORK = PREFIX, WORK
    p4b.STRUCT_ID = g6.MOD
    p4b.STRUCT_OV = lambda: [g6.lum("on")]
    p4b.GROWN_AREA = AREA + N
    p4b.GROWN_NODES = -1
    p4b.sites = lambda: []
    p4b.new_nodes = lambda: []
    p4b.OBSERVE, p4b.SAMPLER, p4b.KILL_READY = observe, Sampler, kill_ready


# --- offline -----------------------------------------------------------------------------------------------------

def check():
    setup()
    res, det = {}, {}
    data, ptr, tl = g6.files()
    # O1 resource identity
    _, tx = g6.compiled("on")
    im = tx["images"]
    r, text, _ = p1.compile_plan("o1", g6.mods_for("on"))
    txs = p1.parse_plan(text or "")["txs"]
    res["O1_resource_identity"] = ({k: rm.sha256_bytes(im[k]) for k in G6_IMAGES} == G6_IMAGES
                                   and (len(im["lvl"]), len(im["ptr"]), len(im["transit"])) == (SIZE + N, PSIZE + 8 * K,
                                                                                               TSIZE)
                                   and txs == [f"level-tx 2 intro_10 {g6.MOD} {TX_G6}"] and r["active"] == [g6.MOD])
    det["O1"] = {"tx": txs, "sha": {k: rm.sha256_bytes(im[k]) for k in G6_IMAGES}}
    # O2 / O3 on private copies: host changes after activation, repeated / reversed opens, change before activation
    cp = WORK / "copies"
    if cp.exists():
        shutil.rmtree(cp)
    cp.mkdir(parents=True)
    paths = {}
    for k, src in (("lvl", g3a.LVL), ("ptr", g3a.PTR), ("transit", g4b.TRANSIT)):
        paths[k] = cp / src.name
    exe = p1.build_test("dev")
    m = p1.parse_plan(text)
    for f in m["files"]:
        name = Path(f["path"]).name
        f["path"] = str(paths[{"intro_10.lvl": "lvl", "intro_10.ptr": "ptr", "transit.lvl": "transit"}[name]])
    plan_c = cp / "plan_copies.txt"
    plan_c.write_text(p1.emit(m), encoding="utf-8")
    exp = {}
    for k in ("lvl", "ptr", "transit"):
        exp[k] = cp / f"expect_{k}.bin"
        exp[k].write_bytes(im[k])
    E = (exp["lvl"], exp["ptr"], exp["transit"])
    O = ("-", "-", "-")
    cases = [("copies: valid, host changes after activation", "lvl,flip_transit,transit,flip_lvl,lvl,flip_ptr,ptr",
              "active", E),
             ("copies: repeated and reversed opens", "transit,transit,ptr,lvl,ptr,transit", "active", E),
             ("copies: transit changed before activation", "flip_transit,lvl,ptr,transit", "tx_identity", O)]
    results = []
    for i, (name, order, want, e) in enumerate(cases):
        for k, src in (("lvl", g3a.LVL), ("ptr", g3a.PTR), ("transit", g4b.TRANSIT)):
            shutil.copyfile(src, paths[k])   # pristine copies before every case
        cf = cp / f"case_{i}.tsv"
        cf.write_text("\t".join([name, str(plan_c), "intro_10", want, order, str(paths["lvl"]), str(paths["ptr"]),
                                 str(e[0]), str(e[1]), str(paths["transit"]), str(e[2])]) + "\n", encoding="utf-8")
        q = subprocess.run([str(exe), str(cf)], capture_output=True, text=True, timeout=600)
        results.append({"case": name, "rc": q.returncode, "out": q.stdout.strip().splitlines()[:2]})
    for k in paths.values():
        k.unlink()
    det["O2_O3_copies"] = results
    copies_ok = all(x["rc"] == 0 for x in results)
    # G6-P1's check and negtest, re-run into e485/g6p1
    g6.WORK = WORK / "g6p1"
    g6.WORK.mkdir(parents=True, exist_ok=True)
    p1.WORK = g6.WORK
    rc_check = g6.check()
    p1.WORK = g6.WORK
    rc_neg = g6.negtest()
    rc_g5 = g6.g5p5_check()
    p1.WORK = WORK
    off = json.loads((g6.WORK / "offline.json").read_text())
    neg = json.loads((g6.WORK / "negtest" / "summary.json").read_text())
    det["g6p1_check"] = off["checks"]
    det["g6p1_negtest"] = {k: neg.get(k) for k in ("dev", "prod", "g5p5_negtest_rc")}
    det["g5p5_check_rc"] = rc_g5
    res["O2_three_member_integrity"] = copies_ok and results[0]["rc"] == 0 and rc_neg == 0
    res["O3_repeated_opens"] = copies_ok and results[1]["rc"] == 0 and neg["dev"]["exit"] == 0
    res["O4_fail_closed"] = rc_neg == 0 and neg["dev"]["exit"] == 0 and neg["prod"]["exit"] == 0 and results[2]["rc"] == 0
    c = off["checks"]
    res["O5_actor_structure"] = rc_check == 0 and all(c[k] for k in ("O1_g4b_equivalence", "O2_actor_identity",
                                                                     "O3_hierarchy_registration", "O4_relocation"))
    # O6 G5-P4b's preflight with the lum mod (writes e485/preflight.json, which phase 2 requires)
    setup()
    rc_pre = p4b.preflight()
    pre = json.loads((WORK / "preflight.json").read_text())
    det["preflight"] = pre["res"]
    res["O6_recovery_compatibility"] = rc_pre in (0, None) and pre["pass"] and len(pre["res"]) == 14
    res["O7_backward_compatibility"] = (c["O8_compatibility"] and rc_g5 == 0 and neg.get("g5p5_negtest_rc") == 0
                                        and pre["res"]["production_refuses"])
    out = {"res": res, "details": det, "pass": all(res.values())}
    (WORK / "check.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"res": res, "copies": results, "preflight": pre["res"]}, indent=1, default=str))
    print("CHECK_G6P1B", "PASS" if out["pass"] else "FAIL", f"{sum(res.values())}/{len(res)}")
    return 0 if out["pass"] else 1


# --- phase 1: reload --------------------------------------------------------------------------------------------

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
    print(json.dumps(row, default=str)[:3000])
    return 0


def _load(work, run):
    r = json.loads((work / "row.json").read_text())
    r["states"] = json.loads((work / "states.json").read_text())
    r["entries"] = json.loads((work / "entries.json").read_text())
    r["log"] = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / run).glob("runtime*.log")))
    r["phases"] = r3.phases(r["states"])
    rj = RUNS / run / "run.json"
    r["run_json"] = json.loads(rj.read_text(encoding="utf-8-sig")) if rj.is_file() else {}
    mf = RUNS / run / "m2_faults.log"
    r["fault_codes"] = sorted(set(re.findall(r"M2 exception code=([0-9A-Fa-f]+)", mf.read_text(errors="replace")))) \
        if mf.is_file() else []
    return r


def reference_union():
    row = json.loads(REF.read_text())
    ab = int(row["area"]["base"], 16)
    lst = row["live_first"]["lists"]
    return {x - ab for x in lst["dw"]["walk"] + lst["inactive"]["walk"]}


def union(lst):
    d, i = lst.get("dw", {}), lst.get("inactive", {})
    both = d.get("walk", []) + i.get("walk", [])
    return set(both), len(both) == len(set(both)) and bool(d.get("prev_ok")) and bool(i.get("prev_ok"))


def registered(lst, ab, ref, grown=True):
    U, nodup = union(lst)
    rel = {x - ab for x in U}
    rec, per = lst.get("rec", {}), lst.get("personal", {})
    if not grown:
        return bool(nodup and rel == ref and rec.get("count") == rec.get("n") == 122 and per.get("count") == 69)
    return bool(nodup and rel == ref | {COPY_REL} and rec.get("count") == rec.get("n") == 123
                and rec.get("last_so") == ab + COPY_REL and (ab + COPY_REL + 0xC4) in lst.get("bak_targets", [])
                and per.get("count") == 70 and per.get("last_name") == NEW_NAME)


def instance_state(blocks, ab):
    sl, cl = bytes.fromhex(blocks.get("src", "")), bytes.fromhex(blocks.get("copy", ""))
    if len(sl) != BLK or len(cl) != BLK:
        return {"ok": False, "reason": "blocks"}
    w = lambda x, k: struct.unpack_from(">I", x, k)[0]   # noqa: E731
    s_lo, c_lo = ab + SRC_REL, ab + COPY_REL
    c_into = [k for k in range(0, BLK, 4) if s_lo <= w(cl, k) < s_lo + BLK and k != 0x18]
    s_into = [k for k in range(0, BLK, 4) if c_lo <= w(sl, k) < c_lo + BLK and k != 0x14]
    out = {"copy_3d_buf": f"{w(cl, 0x14C):08x}", "src_3d_buf": f"{w(sl, 0x14C):08x}",
           "brain4": [w(sl, 0x31C), w(cl, 0x31C)], "copy_into_src": c_into, "src_into_copy": s_into}
    out["ok"] = (out["copy_3d_buf"] not in ("00000000", out["src_3d_buf"]) and out["brain4"] == [0xCDCDCDCD] * 2
                 and not c_into and not s_into)
    return out


def collection(samples, ab, pos, start):
    """Variable-5 changes in one entry / phase, the generator's distance to the copy at the first change, offsets the
    copy changed across it that the source did not, and the post-collection lists."""
    ch = [(samples[i]["t"], samples[i - 1]["v5"], samples[i]["v5"]) for i in range(1, len(samples))
          if samples[i]["v5"] != samples[i - 1]["v5"]]
    out = {"v5_first": samples[0]["v5"] if samples else None, "changes": ch, "near": None, "pickup_specific": [],
           "lists_after": next((x["lists_after"] for x in samples if "lists_after" in x), None)}
    if ch:
        tc = ch[0][0]
        d = [math.dist(x["pos"], pos) for x in samples if abs(x["t"] - tc) <= 2.0]
        out["near"] = round(min(d), 3) if d else None
        out["t_rel"] = round(tc - start, 3)
        bl = [x for x in samples if x.get("copy")]
        before = [x for x in bl if x["t"] <= tc]
        after = [x for x in bl if x["t"] > tc]
        if before and after:
            cb, ca = bytes.fromhex(before[-1]["copy"]), bytes.fromhex(after[0]["copy"])
            sb, sa = bytes.fromhex(before[-1]["src"]), bytes.fromhex(after[0]["src"])
            out["pickup_specific"] = sorted({k for k in range(0, BLK, 4) if cb[k:k + 4] != ca[k:k + 4]}
                                            - {k for k in range(0, BLK, 4) if sb[k:k + 4] != sa[k:k + 4]})
    return out


def fault_counts(run):
    """Revision 1 (a): {exception code: count} of a run's m2_faults.log."""
    mf = RUNS / run / "m2_faults.log"
    out = {}
    for c in re.findall(r"M2 exception code=([0-9A-Fa-f]+)", mf.read_text(errors="replace")) if mf.is_file() else []:
        out[c] = out.get(c, 0) + 1
    return out


def L7_rest(ph, D, within, host, tx, snaps, log, passes, snap_sizes, e1, e2):
    """L7 without its walk-validity term (revision 1 replaces only that term)."""
    want = {"area1_length": N, "free": -N, "largest": -N}
    return (D["menu_before"] == {} and D["e1"] == want and D["e2"] == want and D["fix_between"] == {}
            and D["menu_after"] == {} and all(within.values()) and host == 7914176 <= 16 << 20
            and len(tx) == 1 and len(snaps) == 3 and "G5P3 tx host_changed" not in log
            and not re.search(r"M36 grow read file=(intro_10\.(lvl|ptr)|transit\.lvl)", log)
            and all(b_ == snap_sizes.get(f) for f, _, b_ in passes) and (e1["ab"], e1["length"]) == (e2["ab"], e2["length"]))


def judge_reload(tag):
    setup()
    run = f"{PREFIX}_{tag}_ra"
    ra = _load(WORK / tag / "ra", run)
    rb = _load(*CONTROL)
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
    L["L1_first_load_transaction"] = (log.count("M33 mods state=active") == 1 and tx == want_tx
                                      and ptx and ptx[0].split(" ")[1] == "2" and g6l == [("2", "lvl,ptr,transit")]
                                      and sorted((f, b_) for f, _, b_, _ in snaps) == SNAP
                                      and all(d == "3" for *_, d in snaps)
                                      and None not in first.values() and first["G5P3 tx snapshot"] < first["G5P3 tx read"]
                                      and first["M33 mods state=active"] < first["G5P3 tx read"])
    ref = reference_union()
    pos = g4b.construct(*g6.files(), "on")[3]["pos"]
    ent = {}
    for i, e in enumerate(ra["entries"][:2], 1):
        lv = e.get("live", {})
        ab = e["ab"]
        reg = registered(lv.get("lists", {}), ab, ref) and e["length"] == AREA + N
        st = instance_state(lv.get("blocks", {}), ab)
        co = collection(e["samples"], ab, pos, e["t"])
        la = co["lists_after"] or {}
        co_ok = (co["v5_first"] == 0 and [c[1:] for c in co["changes"]] == [(0, 1)] and co["near"] is not None
                 and co["near"] <= 3.0 and bool(co["pickup_specific"]) and registered(la, ab, ref))
        ent[i] = {"ab": hex(ab), "length": e["length"], "registered": reg, "state": st, "collection": co,
                  "collection_ok": co_ok, "generator": e.get("generator"), "live_error": lv.get("error")}
    det["entries"] = ent
    L["L2_first_load_registration"] = ent[1]["registered"] and ent[1]["state"]["ok"]
    L["L3_first_load_collection"] = ent[1]["collection_ok"]
    passes = re.findall(r"G5P3 tx pass file=(\S+) pass=(\d+) reads_before=\d+ image_bytes=(\d+)", log)
    det["tx_passes"] = {f: sum(1 for x, _, _ in passes if x == f) for f, _ in SNAP}
    ph = ra["phases"]
    e1, e2 = ra["entries"][0], ra["entries"][1]
    gl = ra.get("process_left")
    L["L4_genuine_reload"] = (e1.get("left_t") is not None and e1["left_t"] <= e2["t"] and ph["fix_between"] is not None
                              and all(n >= 2 for n in det["tx_passes"].values()) and ra["runner_exit"] == 0
                              and gl is False)
    L["L5_second_load_registration"] = (ent[2]["registered"] and ent[2]["state"]["ok"]
                                        and ent[2]["collection"]["v5_first"] == 0)
    L["L6_second_load_collection"] = ent[2]["collection_ok"]
    D = {k: r3.diff(r3.brief(ph[k]), r3.brief(rb["phases"][k]))
         for k in ("menu_before", "e1", "e2", "fix_between", "menu_after")}

    def norm(x):
        bb = r3.brief(x)
        return bb and {k: bb[k] for k in ("free", "largest", "alloc", "free_chunks")} | {
            "areas": sorted(bb["areas"].values())}
    within = {"e1_eq_e2": norm(ph["e1"]) == norm(ph["e2"]),
              "menu_before_eq_after": norm(ph["menu_before"]) == norm(ph["menu_after"]),
              "fix_between": norm(ph["fix_between"]) == norm(rb["phases"]["fix_between"])
              and (ph["fix_between"] or {}).get("free_bytes") == FIX_ONLY_FREE}
    want = {"area1_length": N, "free": -N, "largest": -N}
    host = sum(int(b_) for b_ in snap_sizes.values())
    det["memory"] = {"D": D, "within": within, "host_snapshot_bytes": host,
                     "phases": {k: r3.brief(v) for k, v in ph.items() if isinstance(v, dict)}}
    L["L7_memory_transaction_consistency"] = (
        ph["walk_ok"] and D["menu_before"] == {} and D["e1"] == want and D["e2"] == want and D["fix_between"] == {}
        and D["menu_after"] == {} and all(within.values()) and host == 7914176 <= 16 << 20
        and len(tx) == 1 and len(snaps) == 3 and "G5P3 tx host_changed" not in log
        and not re.search(r"M36 grow read file=(intro_10\.(lvl|ptr)|transit\.lvl)", log)
        and all(b_ == snap_sizes.get(f) for f, _, b_ in passes) and (e1["ab"], e1["length"]) == (e2["ab"], e2["length"]))
    revised = tag != "l1"
    if revised:   # revision 1 (b): `changed` (torn read) snapshots tolerated outside intro_10, at most two
        st = ra["states"]
        i0 = next((i for i, x in enumerate(st) if "invalid" not in x), None)
        later = [x for x in st[i0 + 1:]] if i0 is not None else []
        bad = [x for x in later if "invalid" in x]
        windows = [(e["t"], e.get("left_t") or 1e9) for e in ra["entries"][:2]]
        walk_rev = (i0 is not None and all(x["invalid"] == "changed" for x in bad) and len(bad) <= 2
                    and not any(a <= x["t"] <= b for x in bad for a, b in windows))
        det["walk_revision1"] = {"changed": [x["t"] for x in bad], "ok": walk_rev}
        L["L7_memory_transaction_consistency"] = L["L7_memory_transaction_consistency"] or (
            walk_rev and not ph["walk_ok"] and L7_rest(ph, D, within, host, tx, snaps, log, passes, snap_sizes, e1, e2))
    rj = ra["run_json"]
    prot = json.loads((WORK / tag / "protected.json").read_text())
    mb = ra["marker_before_start"]
    faults_ok = (fault_counts(run) == fault_counts(CONTROL[1])) if revised else set(ra["fault_codes"]) <= {"406D1388"}
    det["fault_counts"] = {"run": fault_counts(run), "control": fault_counts(CONTROL[1])}
    L["L8_safety"] = ("M23 haptics policy=suppressed physical_pad_drivers=none" in log and not any(ra["judges"].values())
                      and ra["runner_exit"] == 0 and gl is False and faults_ok
                      and rj.get("game_foreground_events") == 0 and rj.get("game_foreground_samples") == 0
                      and mb[0] == "armed" and mb[1]["session"] == run and mb[1]["plan_sha256"] == ra["plan_sha256"]
                      and ra["controlled"] is True and ra["session_end"]["cleared"] is True
                      and ra["marker_after"] == "none" and prot["before"] == prot["after"])
    det["safety"] = {"judges": ra["judges"], "foreground": (rj.get("game_foreground_events"),
                                                            rj.get("game_foreground_samples")),
                     "faults": ra["fault_codes"], "session_end": ra.get("session_end"), "tx": tx, "g6p1": g6l,
                     "snapshots": snaps, "process_detail": ra.get("process_detail")}
    ok = all(v is True for v in L.values())
    if ok:
        verdict = "RELOAD VERIFIED"
    elif all(v for k, v in L.items() if k != "L6_second_load_collection") and ent[2]["collection"]["changes"] == []:
        verdict = "PARTIAL — COLLECTION AFTER RELOAD UNVERIFIED"
    else:
        verdict = "NOT PASSED"
    res = {"L": L, "verdict": verdict, "details": det}
    (WORK / f"judgement_reload_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({"L": L, "verdict": verdict, "entries": ent, "D": D, "within": within,
                      "tx_passes": det["tx_passes"]}, indent=1, default=str))
    return 0 if ok else 1


# --- phase 2: abnormal termination and recovery ------------------------------------------------------------------

def recover(tag):
    if not gate_patched():
        raise SystemExit("the development gate is not applied")
    if not json.loads((WORK / "check.json").read_text())["pass"]:
        raise SystemExit("check did not pass")
    setup()
    return p4b.run(tag)


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
    ref = reference_union()
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
    ordered = bool(tm and tp_ and tg and tm < tp_ < tg)
    # G5-P4b's R2 also requires exactly two snapshot lines (version 1); here: the same ordering and three lines
    R["R1_marker_ordering"] = bool(A and ordered and alog.count("G5P1 level-tx active level=intro_10") == 1
                                   and len(re.findall(r"G6P1 level-tx version=2 members=lvl,ptr,transit", alog)) == 1
                                   and len(snaps) == 3)
    lv = (A or {}).get("live") or {}
    ab = lv.get("ab")
    kill_t = (A or {}).get("row", {}).get("kill_t")
    pos = g4b.construct(*g6.files(), "on")[3]["pos"]
    co = collection([x for x in (A or {}).get("samples", []) if kill_t is None or x["t"] <= kill_t], ab or 0, pos, 0)
    det["A_collection"] = {k: co[k] for k in ("v5_first", "changes", "near")}
    det["A_state"] = instance_state(lv.get("blocks", {}), ab) if ab else None
    R["R2_v2_activation"] = bool(A and ab and sorted((f, b_) for f, _, b_, _ in snaps) == SNAP
                                 and registered(lv.get("lists", {}), ab, ref) and co["v5_first"] == 6
                                 and co["changes"][:1] and co["changes"][0][1:] == (6, 7))
    R["R3_ownership"] = Rp["R1_session_ownership"]
    R["R4_forced_termination"] = Rp["R4_abnormal_termination"]
    R["R5_marker_persistence"] = Rp["R5_marker_persistence"]
    cl = C["log"] if C else ""
    R["R6_whole_transaction_refusal"] = bool(
        C and ev["C_plan"]["codes"] == {g6.MOD: "STRUCTURAL_RECOVERY"} and ev["C_plan"]["structural_recovery"] == "armed"
        and not ev["C_plan"]["structural_marker"] and not ev["C_plan_has_tx"] and cl.count("M33 mods state=active") == 1
        and not re.search(r"G5P1|G5P3|G6P1|M36 grow", cl) and not re.search(r"M33 mods served mod=\S+ file=transit\.lvl", cl)
        and ev["marker_after_C"] == ev["marker_A"]["sha256"])
    clv = (C or {}).get("live") or {}
    cab = clv.get("ab")
    R["R7_original_actor_state"] = bool(C and cab and registered(clv.get("lists", {}), cab, ref, grown=False)
                                        and any(s.get("areas", {}).get("1", {}).get("length") == AREA
                                                for s in C["states"] if "invalid" not in s))
    R["R8_ordinary_mod"] = Rp["R7_nonstructural"]
    R["R9_isolation_and_clear"] = Rp["R8_profile_isolation"] and Rp["R9_explicit_recovery"]
    R["R10_production_desktop"] = bool(Rp["R10_production_desktop"] and C and set(C["faults"]) <= {"406D1388"})
    det["faults"] = {k: v.get("faults") for k, v in ph.items()}
    invalid = j["invalid"]
    ok = not invalid and all(R.values())
    res = {"invalid": invalid, "R": R, "verdict": "RECOVERY VERIFIED" if ok else ("INVALID" if invalid else "NOT PASSED"),
           "g5p4b_judge": Rp, "details": det}
    (WORK / f"judgement_recover_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("invalid", "R", "verdict")} | {"A_collection": det["A_collection"],
                                                                          "A_state": det["A_state"]},
                     indent=1, default=str))
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
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
