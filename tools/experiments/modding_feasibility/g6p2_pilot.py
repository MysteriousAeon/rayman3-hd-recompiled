#!/usr/bin/env python3
"""E-487 (D-254) G6-P2: typed scripted-actor insertion. `insert-scripted-frog` (tools/r3hd_mods.py) reproduces G4c's
additional MAN_mGenSound_Frog (E-472 revision 1; functional closure G4d-1, E-474) through the compiler and the
development version-2 transaction (intro_10.lvl + .ptr + transit.lvl). Development-only; private; hidden.

  g6p2_pilot.py check            offline O1-O8 (writes private/work/e487/offline.json)
  g6p2_pilot.py negtest          deterministic transaction tests (dev + production headers) and G6-P1's negtest
  g6p2_pilot.py run TAG          hidden runs A base, B1 Frog 500 ms, B2 Frog 2000 ms, C gate off, D exit
                                 (G4d-1's runner for A-C, G4c's for D, both unchanged; plans from the compiler)
  g6p2_pilot.py judge TAG        P1-P8
Outputs: private/work/e487/.

OPERATION (manifest): {"type": "insert-scripted-frog", "level": "intro_10", "model": FROG10 (NIK_mGenSound's
  first-behaviour key), "instance": 2 (SO 0x53BED0), "lvl_sha256", "ptr_sha256", "transit_sha256" (exact originals),
  "placement": "at_source" (the only verified placement: G4c kept the source's position), "period_ms": 500 | 2000
  (designer variable 5 in both buffers; the two values G4d-1 predicted and observed)}. No offsets, addresses, slots,
  script bytes, designer payloads or Brain / Mind records are accepted. One per mod; no other structural operation.
TRANSACTION: version 2 unchanged (G6-P1): every Frog change lies in the level file (blocks, lists, the always list,
  the extended sound-event resolve table), its pointer table and transit's dynamic-world count. Growth +3,028 /
  +432 bytes, inside the development runtime's 4,096 / 1,024 bounds. No runtime change for G6-P2.

OFFLINE (committed with the implementation; any failure blocks the runs)
  O1 G4 equivalence: for period 500 / 2000 the compiler's three images = g4c.construct(same / diff) = the files G4c n2
     served (private/work/e472/n2/<v>/*_range.bin), directly and through import -> resolve -> plan; the exit
     composition (Frog 2000 + the ordinary designer default e478.lums-6) = construct(exit) = n2/exit.
  O2 identity / hierarchy: G4c's own simulator (g4c.simulate) on the compiler's images: 61 world actors with the copy
     right after the source, 123 SO records (copy last), the copy's four backup targets, 70 personal types (new name
     last), 18 always elements all owned by 0x53A090 with the copy once; and G4c's offline gate (21 checks) passes.
  O3 Brain / Mind / instance state: the copy's Brain, Mind, Intelligence, DsgMem and both buffers are its own block
     offsets (+0x318 / +0x324 / +0x338 / +0x490 / +0x49C / +0x4BC); Mind +0 and DsgMem +0 (the model) equal the
     source's; no copy word points into the source except its previous-sibling link; 3dData buffer word as source.
  O4 designer / script: copy buffers = source buffers except variable 5 (= period, both buffers); the eight type-14
     words raw as the source's; the resolve table holds exactly the source's and the copy's eight words each once.
  O5 relocations / fixups: 54 new own-file entries, no duplicate slot, every new slot inside a new object or an old
     list end, none inside the resolve table; the 8 new resolve entries are file-domain words of the copy's buffers.
  O6 transaction / budget: the plan carries `level-tx 2 intro_10 <mod> <id>` with three tx-file members (original
     size / sha, guest size, result sha = the images) and an id recomputed here; budget headroom >= 0.
  O7 negatives (compiler): gate off; other level; other instance / model; placement / period outside the presets;
     extra / missing key; wrong file hash; two Frogs; Frog + lum; Frog + graph node; damaged inputs (duplicate
     slot, wrong personal count, missing resolve entry, existing new name) and a damaged output (simulator) refuse
     with nothing compiled. (Runtime: `negtest`.)
  O8 backward compatibility: G6-P1's lum images and tx id unchanged; selftest; `negtest` re-runs G6-P1's (versions
     1 / 2, G5 suites, production refusal).

RUNTIME PROTOCOL (committed before the first modified run; derived from G4c n2 / G4d-1 c2 and G4d-0's model)
  Cases (hidden, non-activating, private profiles, --test-level intro_10, no input, no captures; development build
  with the gate applied): A base (no mods); B1 Frog 500; B2 Frog 2000; C B2's plan with R3HD_DEV_STRUCTURAL_TX unset;
  D B2 + e478.lums-6 (generator variable 5 = 6: the first junction ends the flight, intro_15 opens). A-C: G4d-1's
  runner (150 s, samples every 0.1 s for 75 s: timer; per actor P (3dData +342), counter (+343), AI runs (+344),
  behaviour, v5 both buffers, v8). D: G4c's runner (exit case).
  P1 resource transaction: B1 / B2 / D: `G5P1 level-tx active level=intro_10 mod=g6p2.frog id=<plan id>`, `G6P1
     level-tx version=2 members=lvl,ptr,transit`, three `G5P3 tx snapshot` lines, M36 grow intro_10.lvl 7,661,836 ->
     7,664,864 and intro_10.ptr 209,068 -> 209,500, served exactly intro_10.lvl / .ptr / transit.lvl; A `M33
     mods=off`; masked original-area read-back equal in A, B1, B2, C, D.
  P2 registration (first and last structural read, A-C; first in D): union of the active / inactive worlds = A's +
     exactly the copy, no duplicates, previous links consistent, copy active; records 123 with the copy last; backup
     targets copy +0xC4 / +0x510 / +0x514 / +0x518; personal 70, last `MAN_mGenSound_Frog_G4C`. A / C: 66 / 122 / 69.
  P3 Brain / Mind initialization (B1 / B2): the copy's DsgMem, initial / current buffers, Brain, Mind, Intelligence,
     3dData = its own block addresses; DsgMem +0 = source's = model + 8; Mind +0 = source's; Brain +4 equal; the copy's
     eight sound-event words live = the source's and none the raw id 0x00580006; the source's addresses equal in A-C.
  P4 script execution (guest evidence; G4d-1 C3 + C4): both actors' behaviour = the live LoopOneShot record in every
     sample, >= 10 distinct v8 values each within the timer readings bracketing its sample; live P constant = 28 for
     the source and 33 for the copy in B1 / B2 (30 for the source in A / C); AI runs per frame within 3 % of 1 / P;
     every v8 interval = m * P frames (F = 1000/60 ms) within max(3, 0.004 x interval) ms, m in {2} source B1 / B2,
     {1} copy B1, {4} copy B2, {1, 2} source A / C; no phase violation (tolerance F + 3 ms + 0.4 % of the elapsed).
  P5 observable independent behaviour (G4d-1 C5 + C6): v5 = 500 in both source buffers in every sample of A-C; copy
     500 (B1) / 2000 (B2) in both buffers; four distinct buffer addresses; the v8 sequences differ; copy median
     interval within 3 ms of 33 F (B1) and 8 ms of 132 F (B2); the source's intervals 56 frames in both B1 and B2; no
     level change in A-C.
  P6 runtime integrity: block-8 walks valid in every snapshot; P2's list consistency at the last read; no `access
     violation`, engine error or invalid-target line; P3's resolution holds.
  P7 exit / cleanup: area length AREA + 3,028 in B1 / B2 / D and AREA in A / C; free after load A / C 13,088,528, B1 /
     B2 13,085,500; D: intro_15 opened within 130 s and the block-8 layout after the change = E-465a (intro_15 area
     at 0x40F5F320, free 12,234,744): the grown area, records and copy released.
  P8 production / desktop safety: C `state=refused reason=level_tx_not_enabled`, no grow, nothing served, no G5P1 /
     G5P3 / G6P1 line; every run: M21 / M22 / M23 0, haptics policy line, runner exit 0, game_foreground_events /
     samples 0 / 0, fault codes within {406D1388}, D-250 ownership check (no r3hd.exe naming the run left); `check`
     and `negtest` passed first.
  Invalid (new tag, kept): process / area not found, structural read error, < 60 s of samples in A-C.
  Stop: a guest fault, registration corruption or desktop-safety violation.
  Revision 1 (after run h1, before h2; h1 kept: judgement_h1_original.json, P1 / P4 / P5 FAIL):
    P1: the version-2 transaction also logs `M36 grow size file=transit.lvl host_size=41508 guest_size=41508` (its
    same-size member); P1 requires that line in addition to the two growth lines (h1 expected only the two).
    P4 (c) / (d) and P5's source-interval term: intervals are counted in the guest's own AI runs (3dData +344 at the
    sample where v8 changed; m runs = m x P frames), and every v8 change must follow an AI run since the previous
    sample. h1's B1 had one shared slow-frame stretch (timer 4.4-6.6 s into the level): the source's two intervals
    949 / 951 ms and the copy's 566 / 567 ms each held one extra frame of timer time, so the nominal-60 Hz conversion
    failed while both actors still ran on their own phase. Everything else unchanged (P, runs per frame, v8 = timer,
    medians in ms, all other criteria).
  All eight = G6-P2 VERIFIED — TYPED SCRIPTED ACTOR INSERTION; P1-P3 with P4 failing = PARTIAL — ACTOR REGISTERED,
  SCRIPT UNVERIFIED.
"""
import hashlib
import json
import os
import re
import shutil
import statistics
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
import g4b_ab as g4b  # noqa: E402
import g4c_ab as g4c  # noqa: E402
import g4d1_closure as g4d1  # noqa: E402
import g5p1_pilot as p1  # noqa: E402
import g5p2b_lifecycle as p2b  # noqa: E402
import g6p1_pilot as g6  # noqa: E402

PREFIX = "e487"
WORK = ROOT / "private" / "work" / PREFIX
LEVEL, ENV = "intro_10", rm.STRUCT_ENV
MOD, EXIT_MOD = "g6p2.frog", "e478.lums-6"
SIZE, PSIZE, AREA, FREE0, TSIZE = g3a.SIZE, g3a.PSIZE, g3a.AREA, g3a.FREE0, g4c.TSIZE
N, K = 3028, 54
N2 = WORK.parent / "e472" / "n2"
SRC, BLK = g4c.SRC, g4c.BLK
VARIANT = {"same": 500, "diff": 2000, "exit": 2000}
CASES = {"A": "base", "B1": "same", "B2": "diff", "C": "nogate", "D": "exit"}
G6_IMAGES = {"lvl": "cbf9fce38e8735c39f4190f0bf833dfa87785f2b9ab0c95a0c9902e0217eaf2c",
             "ptr": "09d81158842462166a202b29ec07f159b792b6b8945ae1ed60d9a202a2907ce5",
             "transit": "321de2e4be2077720e8a6cc6660ff373bcabaed6c5089989a1ed594aa370c34e"}
sha = lambda b: hashlib.sha256(b).hexdigest()   # noqa: E731


def files():
    return g4c.files()


def frog(period=500, **kw):
    data, ptr, tl = files()
    o = {"type": "insert-scripted-frog", "level": LEVEL, "model": rm.FROG10, "instance": 2,
         "lvl_sha256": sha(data), "ptr_sha256": sha(ptr), "transit_sha256": sha(tl), "placement": "at_source",
         "period_ms": period}
    o.update(kw)
    return o


def mods_for(variant):
    return [(MOD, [frog(VARIANT[variant])])] + ([(EXIT_MOD, [p2b.lums6()])] if variant == "exit" else [])


def compiled(period=500, **kw):
    with p1.dev_env():
        return rm.compile_insert_scripted_frog(frog(period, **kw), {"game": g3a.GAME})


def served(v):
    return {k: (N2 / v / f"{k}_range.bin").read_bytes() for k in ("lvl", "ptr", "transit")}


# --- offline -----------------------------------------------------------------------------------------------------

def check():
    WORK.mkdir(parents=True, exist_ok=True)
    p1.WORK = WORK
    data, ptr, tl = files()
    res, det = {}, {}
    # O1
    eq = {}
    for v in ("same", "diff", "exit"):
        nl, np_, nt, _ = g4c.construct(data, ptr, tl, v)
        r, text, _ = p1.compile_plan(f"o1_{v}", mods_for(v))
        im = p1.images(p1.parse_plan(text or "")) if text else {}
        plan_im = (im.get("intro_10.lvl"), im.get("intro_10.ptr"), im.get("transit.lvl"))
        sv = served(v)
        e = {"plan_eq_oracle": plan_im == (nl, np_, nt), "oracle_eq_served": (nl, np_, nt) == (sv["lvl"], sv["ptr"],
                                                                                              sv["transit"]),
             "active": r["active"], "sha": [sha(x)[:16] if x else None for x in plan_im]}
        if v != "exit":
            _, tx = compiled(VARIANT[v])
            e["direct_eq_oracle"] = (tx["images"]["lvl"], tx["images"]["ptr"], tx["images"]["transit"]) == (nl, np_, nt)
        eq[v] = e
    det["O1"] = eq
    res["O1_g4_equivalence"] = all(e["plan_eq_oracle"] and e["oracle_eq_served"] and e.get("direct_eq_oracle", True)
                                   for e in eq.values())
    # O2: G4c's own simulator and gate on the compiler's images
    o2 = {}
    for period in (500, 2000):
        _, tx = compiled(period)
        im = tx["images"]
        s = g4c.simulate(im["lvl"], im["ptr"], im["transit"])
        B1 = 0x40F5509C
        L = g4c.layout()
        copy, src = B1 + L["fc"] - 4, B1 + SRC - 4
        w = s.get("walk") or s.get("dw_walk") or []
        o2[period] = {"keys": sorted(k for k in s if k != "rd"), "always": len(s["always"]),
                      "always_copy": s["always_so"].count(copy), "a_count": s["a_count"], "o_count": s["o_count"],
                      "owner_ok": s["a_owner_ok"], "info": tx["info"]}
        o2[period]["sim"] = {k: (v if not isinstance(v, (list, dict)) else len(v)) for k, v in s.items() if k != "rd"}
    gate = subprocess.run([sys.executable, str(HERE / "g4c_ab.py"), "check"], cwd=ROOT, capture_output=True, text=True)
    (WORK / "g4c_gate.log").write_text(gate.stdout + gate.stderr)
    det["O2"] = {"sim": o2, "g4c_gate_rc": gate.returncode}
    res["O2_identity_hierarchy"] = gate.returncode == 0 and all(
        x["always"] == 18 == x["a_count"] == x["o_count"] and x["always_copy"] == 1 and x["owner_ok"]
        and x["info"]["actors"] == 61 and x["info"]["records"] == 123 and x["info"]["personal_types"] == 70
        for x in o2.values())
    # O3 / O4 / O5 on the compiler's images, independent of its simulator
    o345 = {}
    slots0, _ = g4b.index(data, ptr)
    for period in (500, 2000):
        _, tx = compiled(period)
        lvl, nptr = tx["images"]["lvl"], tx["images"]["ptr"]
        slots, _ = g4b.index(lvl, nptr)
        C = tx["info"]["objects"]["copy"]
        T = tx["info"]["objects"]["table"]
        u = lambda o, b=lvl: struct.unpack_from(">I", b, o)[0]   # noqa: E731
        tgt = lambda o: u(o) + 4 if slots.get(o) == 1 else None   # noqa: E731
        own = sorted({tgt(o) - C for o in range(C, C + BLK, 4) if tgt(o) is not None and C <= tgt(o) < C + BLK})
        into_src = [o - C for o in range(C, C + BLK, 4) if tgt(o) is not None and SRC <= tgt(o) < SRC + BLK]
        o3 = (set(rm.FROG_ALLOW[LEVEL]["owned"]) <= set(own) and into_src == [0x18]
              and lvl[C + 0x490:C + 0x494] == lvl[SRC + 0x490:SRC + 0x494]
              and lvl[C + 0x324:C + 0x328] == lvl[SRC + 0x324:SRC + 0x328]
              and lvl[C + 0x14C:C + 0x150] == lvl[SRC + 0x14C:SRC + 0x150])
        bufs_ok = all(
            lvl[C + b:C + b + 16] == lvl[SRC + b:SRC + b + 16] and lvl[C + b + 20:C + b + 30] == lvl[SRC + b + 20:SRC + b + 30]
            and struct.unpack_from(">i", lvl, C + b + 16)[0] == period for b in (0x49C, 0x4BC))
        cnt = u(0x1CE4) + u(0x1CE0)
        tab = [u(T + 4 * i) for i in range(cnt)] if tgt(0x1CE8) == T else []
        ev = lambda base: [base + b + j - 4 for b in (0x49C, 0x4BC) for j in (0, 4, 8, 12)]   # noqa: E731
        o4 = bufs_ok and cnt == 347 and all(tab.count(x) == 1 for x in ev(SRC) + ev(C)) and tab == sorted(tab)
        n0, n1 = struct.unpack_from(">I", ptr, 0)[0], struct.unpack_from(">I", nptr, 0)[0]
        new = [struct.unpack_from(">iI", nptr, 4 + 8 * i) for i in range(n0, n1)]
        locs = [loc + 4 for _, loc in new]
        ends = {g4c.construct(data, ptr, tl, "same")[3][k] for k in ("plast", "rlast", "blink", "alast")}
        o5 = (n1 - n0 == K and len(set(locs)) == len(locs) and not set(locs) & set(slots0)
              and not any(T <= x < T + 4 * cnt for x in locs) and all(SIZE <= x < len(lvl) or x in ends for x in locs)
              and sum(x in ends for x in locs) == 4
              and all(not any(T + 4 * i == x for x in slots) for i in range(cnt)))
        o345[period] = {"own": [hex(x) for x in own], "into_src": into_src, "o3": o3, "o4": o4, "o5": o5,
                        "new_entries": n1 - n0, "resolve_entries": cnt}
    det["O3_O5"] = o345
    res["O3_brain_mind_instance"] = all(x["o3"] for x in o345.values())
    res["O4_designer_script"] = all(x["o4"] for x in o345.values())
    res["O5_relocations_fixups"] = all(x["o5"] for x in o345.values())
    # O6
    r, text, _ = p1.compile_plan("o6", mods_for("same"))
    m, txs = g6.plan_tx(text or "")
    mm = p1.parse_plan(text or "")
    members = sorted(t.split(" ")[0] for f in mm["files"] for t in f["tx"])
    _, tx = compiled(500)
    want = {"lvl": sha(tx["images"]["lvl"]), "ptr": sha(tx["images"]["ptr"]), "transit": sha(tx["images"]["transit"])}
    got = {t.split(" ")[0]: t.split(" ")[3] for f in mm["files"] for t in f["tx"]}
    det["O6"] = {"txs": mm["txs"], "members": members, "id_recomputed": g6.canonical_id(mm) if mm["txs"] else None,
                 "memory": tx["info"]["memory"], "gameplay": mm["gameplay"]}
    res["O6_transaction_budget"] = (len(txs) == 1 and txs[0][:4] == ["level-tx", "2", LEVEL, MOD]
                                    and txs[0][4] == det["O6"]["id_recomputed"] and members == ["lvl", "ptr", "transit"]
                                    and got == want and tx["info"]["memory"]["headroom"] >= 0
                                    and f"gameplay {MOD}" in mm["gameplay"])
    # O7 compiler negatives
    o7 = negatives(data, ptr, tl)
    det["O7"] = o7
    res["O7_negatives"] = all(v is True for v in o7.values())
    # O8
    with p1.dev_env():
        _, ltx = rm.compile_insert_passive_lum(g6.lum("on"), {"game": g3a.GAME})
    st = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "selftest"], cwd=ROOT, capture_output=True,
                        text=True)
    r, text, _ = p1.compile_plan("o8_lum", g6.mods_for("on"))
    lt = g6.plan_tx(text or "")[1]
    det["O8"] = {"lum": {k: sha(ltx["images"][k]) == G6_IMAGES[k] for k in G6_IMAGES}, "lum_tx": lt,
                 "selftest": st.stdout.strip().splitlines()[-1] if st.stdout else st.stderr[-200:]}
    res["O8_backward_compatibility"] = (all(det["O8"]["lum"].values()) and st.returncode == 0
                                        and lt and lt[0][4] == g6b_tx())
    out = {"pass": all(res.values()), "checks": res, "details": det}
    (WORK / "offline.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1))
    print("CHECK_G6P2", "PASS" if out["pass"] else "FAIL", f"{sum(res.values())}/{len(res)}")
    return 0 if out["pass"] else 1


def g6b_tx():
    return "ccb07d2f770147cb"


def negatives(data, ptr, tl):
    R = lambda fn, code, env=LEVEL: g6.refused(fn, code, env)   # noqa: E731
    o = frog(500)
    g = {"game": g3a.GAME}
    spec = rm.FROG_ALLOW[LEVEL]
    slots, _ = g4b.index(data, ptr)
    ix = rm.read_script_index(g3a.GAME, LEVEL)
    insts = ix["placements"][rm.FROG10]
    peers = [i["so"] for n, i in enumerate(insts) if n != 2]
    foreign = [(inst[k], e["length"]) for key, e in ix["defaults"].items() if e and key != rm.FROG10
               for inst in e["instances"] for k in ("initial", "current") if isinstance(inst.get(k), int)]

    def build(lvl=data, p=ptr, t=tl, s=spec):
        with p1.dev_env():
            return rm.build_scripted_frog(lvl, p, t, 1, s, peers, foreign, 500, "neg")

    def dup_slot():
        n = struct.unpack_from(">I", ptr, 0)[0]
        e = ptr[4:12]
        b = struct.pack(">I", n + 1) + ptr[4:4 + 8 * n] + e + ptr[4 + 8 * n:]
        return build(p=b)

    def bad_pcount():
        b = bytearray(data)
        struct.pack_into(">I", b, 0x1C74 + 8, struct.unpack_from(">I", data, 0x1C7C)[0] + 1)
        return build(lvl=bytes(b))

    def missing_resolve():
        b = bytearray(data)
        ST = struct.unpack_from(">I", data, 0x1CE8)[0] + 4
        tab = [struct.unpack_from(">I", data, ST + 4 * i)[0] for i in range(339)]
        i = tab.index(SRC + 0x49C - 4)
        struct.pack_into(">I", b, ST + 4 * i, tab[i - 1])   # the source's first sound word no longer listed
        return build(lvl=bytes(b))

    def existing_name():
        return build(s=dict(spec, new_name=b"MAN_mGenSound_Frog"))

    def bad_output():
        new, nptr, ntl, edits, info = build()
        s = rm._frog_source(data, ptr, tl, 1, spec, peers, foreign, "neg")
        L = info["objects"]
        t = bytearray(new)
        struct.pack_into(">I", t, L["table"], 0)       # drop the first resolve entry
        with p1.dev_env():
            return rm.verify_scripted_frog(data, ptr, tl, bytes(t), nptr, ntl, 1, spec, s, L,
                                           [(f, loc + 4) for f, loc in (struct.unpack_from(">iI", nptr, 4 + 8 * i) for i in
                                            range(struct.unpack_from(">I", ptr, 0)[0], struct.unpack_from(">I", nptr, 0)[0]))],
                                           edits, 500, "neg")

    def two(mods):
        return g6.import_refused("neg_two", mods, "BAD_MANIFEST")
    igs = None
    try:
        igs = p1.igm("neutral")
    except Exception:
        pass
    out = {
        "gate_off": R(lambda: rm.parse_insert_scripted_frog(o, "o"), "UNSUPPORTED", None),
        "gate_off_compile": R(lambda: rm.compile_insert_scripted_frog(o, g), "UNSUPPORTED", None),
        "other_level": R(lambda: rm.parse_insert_scripted_frog(dict(o, level="intro_20"), "o"), "UNSUPPORTED"),
        "other_instance": R(lambda: rm.compile_insert_scripted_frog(dict(o, instance=1), g), "UNSUPPORTED"),
        "other_model": R(lambda: rm.compile_insert_scripted_frog(dict(o, model=rm.LUM10, instance=2), g), "UNSUPPORTED"),
        "placement": R(lambda: rm.parse_insert_scripted_frog(dict(o, placement="flight_path"), "o"), "UNSUPPORTED"),
        "position_key": R(lambda: rm.parse_insert_scripted_frog(dict(o, position=[0, 0, 0]), "o"), "BAD_MANIFEST"),
        "period": R(lambda: rm.parse_insert_scripted_frog(dict(o, period_ms=1000), "o"), "UNSUPPORTED"),
        "period_bool": R(lambda: rm.parse_insert_scripted_frog(dict(o, period_ms=True), "o"), "UNSUPPORTED"),
        "extra_key": R(lambda: rm.parse_insert_scripted_frog(dict(o, offset=4), "o"), "BAD_MANIFEST"),
        "missing_key": R(lambda: rm.parse_insert_scripted_frog({k: v for k, v in o.items() if k != "period_ms"}, "o"),
                         "BAD_MANIFEST"),
        "wrong_hash": R(lambda: rm.compile_insert_scripted_frog(dict(o, transit_sha256="0" * 64), g), "TARGET_CHANGED"),
        "two_frogs": two([("x.frog", [o, dict(o)])]),
        "frog_and_lum": two([("x.mix", [o, g6.lum("on")])]),
        "frog_and_graph": two([("x.mixg", [o, igs])]) if igs else "no graph op",
        "duplicate_slot": R(dup_slot, "STRUCTURE_CHECK"),
        "personal_count": R(bad_pcount, "STRUCTURE_CHECK"),
        "missing_resolve_entry": R(missing_resolve, "STRUCTURE_CHECK"),
        "existing_name": R(existing_name, "STRUCTURE_CHECK"),
        "damaged_output": R(bad_output, "STRUCTURE_CHECK"),
    }
    return out


# --- deterministic transaction tests -------------------------------------------------------------------------------

def negtest():
    WORK.mkdir(parents=True, exist_ok=True)
    nd = WORK / "negtest"
    if nd.exists():
        shutil.rmtree(nd)
    nd.mkdir(parents=True)
    p1.WORK = WORK
    data, ptr, tl = files()
    exes = {k: p1.build_test(k) for k in ("dev", "prod")}
    _, text, _ = p1.compile_plan("neg_frog", mods_for("same"))
    _, text_x, _ = p1.compile_plan("neg_frog_exit", mods_for("exit"))
    base = p1.parse_plan(text)
    nl, np_, nt, _ = g4c.construct(data, ptr, tl, "same")
    xl, xp, xt, _ = g4c.construct(data, ptr, tl, "exit")
    V = {}
    for k, b in (("lvl", nl), ("ptr", np_), ("transit", nt), ("xlvl", xl), ("xptr", xp), ("xtransit", xt)):
        V[k] = nd / f"img_{k}.bin"
        V[k].write_bytes(b)
    idx = {Path(f["path"]).name: i for i, f in enumerate(base["files"])}
    li, pi, ti = idx["intro_10.lvl"], idx["intro_10.ptr"], idx["transit.lvl"]

    def variant(name, fn=None, src=base):
        m = json.loads(json.dumps(src))
        if fn:
            fn(m)
        p = nd / f"plan_{name}.txt"
        p.write_text(p1.emit(m), encoding="utf-8")
        return p

    def tamper(m, i, ri):
        off, length, gb, nb, mid, blob = m["files"][i]["range"][ri].split(" ", 5)
        b = bytearray(Path(blob).read_bytes())
        b[len(b) // 2] ^= 0x33
        q = nd / f"tampered_{i}_{ri}.bin"
        q.write_bytes(bytes(b))
        m["files"][i]["range"][ri] = " ".join([off, length, gb, f"{g3a.fnv(bytes(b)):016x}", mid, str(q)])
    resolve_words = {0x1CE0, 0x1CE8}
    plans = {
        "valid": variant("valid"),
        "exit_valid": variant("exit_valid", src=p1.parse_plan(text_x)),
        "missing_transit": variant("missing_transit", lambda m: m["files"].pop(ti)),
        "tampered_ptr": variant("tampered_ptr", lambda m: tamper(m, pi, 0)),
        "partial_resolve_words": variant("partial_resolve_words", lambda m: m["files"][li].update(
            range=[r for r in m["files"][li]["range"] if int(r.split(" ")[0]) not in resolve_words])),
        "corrupt_id": variant("corrupt_id", lambda m: m.update(
            txs=[m["txs"][0][:-1] + ("0" if m["txs"][0][-1] != "0" else "1")])),
    }
    O = ("-", "-", "-")
    Vv, Vx = (V["lvl"], V["ptr"], V["transit"]), (V["xlvl"], V["xptr"], V["xtransit"])
    # private copies of the three originals for the host-change cases (the game's own files are never written)
    cp = nd / "copies"
    cp.mkdir()
    cps = {k: cp / src.name for k, src in (("lvl", g3a.LVL), ("ptr", g3a.PTR), ("transit", g4b.TRANSIT))}
    for k, src in (("lvl", g3a.LVL), ("ptr", g3a.PTR), ("transit", g4b.TRANSIT)):
        shutil.copyfile(src, cps[k])
    mc = json.loads(json.dumps(base))
    for f in mc["files"]:
        f["path"] = str(cps[{"intro_10.lvl": "lvl", "intro_10.ptr": "ptr", "transit.lvl": "transit"}[Path(f["path"]).name]])
    plans["copies"] = nd / "plan_copies.txt"
    plans["copies"].write_text(p1.emit(mc), encoding="utf-8")
    paths = (str(g3a.LVL), str(g3a.PTR), str(g4b.TRANSIT))
    cpaths = (str(cps["lvl"]), str(cps["ptr"]), str(cps["transit"]))
    dev = [("frog valid, lvl,ptr,transit", "valid", LEVEL, "active", "lvl,ptr,transit", Vv, paths),
           ("frog valid, transit,ptr,lvl", "valid", LEVEL, "active", "transit,ptr,lvl", Vv, paths),
           ("frog valid, repeated opens", "valid", LEVEL, "active", "ptr,transit,lvl,transit,ptr", Vv, paths),
           ("frog exit composition valid", "exit_valid", LEVEL, "active", "transit,lvl,ptr", Vx, paths),
           ("frog not enabled", "valid", "-", "level_tx_not_enabled", "lvl,ptr,transit", O, paths),
           ("frog enabled for another level", "valid", "intro_20", "tx_level", "transit,lvl,ptr", O, paths),
           ("frog missing transit member", "missing_transit", LEVEL, "tx_incomplete", "transit,lvl,ptr", O, paths),
           ("frog tampered ptr, rehashed", "tampered_ptr", LEVEL, "tx_result_hash", "lvl,ptr,transit", O, paths),
           ("frog partial: resolve-table words dropped", "partial_resolve_words", LEVEL, "tx_result_hash",
            "lvl,ptr,transit", O, paths),
           ("frog corrupted id", "corrupt_id", LEVEL, "tx_id", "transit,lvl,ptr", O, paths),
           ("frog copies: host changes after activation", "copies", LEVEL, "active",
            "lvl,flip_transit,transit,flip_lvl,lvl,flip_ptr,ptr", Vv, cpaths),
           ("frog copies: lvl changed before activation", "copies", LEVEL, "tx_identity", "flip_lvl,transit,lvl,ptr", O,
            cpaths)]
    prod = [("production: frog transaction (lvl first)", "valid", LEVEL, "unknown_record", "lvl,ptr,transit", O, paths),
            ("production: frog transaction (transit first)", "valid", LEVEL, "unknown_record", "transit,ptr,lvl", O,
             paths)]
    out = {}
    for kind, cases in (("dev", dev), ("prod", prod)):
        res_k = []
        for i, (n, p, env, want, order, e, pa) in enumerate(cases):
            for k, src in (("lvl", g3a.LVL), ("ptr", g3a.PTR), ("transit", g4b.TRANSIT)):
                shutil.copyfile(src, cps[k])   # pristine copies before every case
            cf = nd / f"case_{kind}_{i}.tsv"
            cf.write_text("\t".join([n, str(plans[p]), env, want, order, pa[0], pa[1], str(e[0]), str(e[1]), pa[2],
                                     str(e[2])]) + "\n", encoding="utf-8")
            r = subprocess.run([str(exes[kind]), str(cf)], capture_output=True, text=True, timeout=600)
            res_k.append({"case": n, "rc": r.returncode, "out": r.stdout.strip().splitlines()[:1]})
        out[kind] = {"cases": len(cases), "passed": sum(x["rc"] == 0 for x in res_k), "results": res_k}
        print(kind, out[kind]["passed"], "/", out[kind]["cases"])
    for k in cps.values():
        k.unlink()
    g6.WORK = WORK / "g6p1"
    g6.WORK.mkdir(parents=True, exist_ok=True)
    p1.WORK = g6.WORK
    out["g6p1_negtest_rc"] = g6.negtest()
    p1.WORK = WORK
    out["pass"] = out["g6p1_negtest_rc"] == 0 and all(out[k]["passed"] == out[k]["cases"] for k in ("dev", "prod"))
    (nd / "summary.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("NEGTEST_G6P2", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


# --- runs ----------------------------------------------------------------------------------------------------------

def plan_for_run(work, data, ptr, tl, variant):
    res, text, paths = p1.compile_plan(f"run_{work.parent.name}_{work.name}", mods_for(variant))
    want = sorted([MOD] + ([EXIT_MOD] if variant == "exit" else []))
    if text is None or sorted(res["active"]) != want:
        raise SystemExit(f"compiler refused the run's mods: {res['mods']}")
    plan = paths["cache"] / rm.PLAN_NAME
    shutil.copyfile(plan, work / "plan_copy.txt")
    return plan, g4c.construct(data, ptr, tl, variant)[3]


def bind():
    p1.WORK = WORK
    for mod in (g4d1, g4c):
        mod.PREFIX = PREFIX
        mod.GATE_ENV = (ENV, LEVEL)
    g4c.write_plan = plan_for_run
    for k in ("R3HD_G3A_TEST_GROW", ENV, "R3HD_MODS_PLAN", "R3HD_E465_TEST_GROW"):
        os.environ.pop(k, None)


def run(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    for f in ("offline.json", "negtest/summary.json"):
        if not json.loads((WORK / f).read_text()).get("pass"):
            raise SystemExit(f"{f} did not pass")
    bind()
    for label, case in CASES.items():
        row = (g4c if case == "exit" else g4d1).run_case(tag, case)
        run_ = f"{PREFIX}_{tag}_{case}"
        pj = g3a.RUNS / run_ / "process.json"
        pid = json.loads(pj.read_text(encoding="utf-8-sig")).get("pid") if pj.is_file() else None
        left, detail = g3a.game_left(pid, run_)
        (WORK / tag / case / "process_left.json").write_text(json.dumps({"left": left, **detail}) + "\n")
        print(label, json.dumps(dict(row, game_left=left), default=str)[:600], flush=True)
    return 0


# --- judgement -----------------------------------------------------------------------------------------------------

def load(tag, case):
    work = WORK / tag / case
    run_ = f"{PREFIX}_{tag}_{case}"
    r = json.loads((work / "row.json").read_text())
    r["states"] = json.loads((work / "states.json").read_text())
    r["samples"] = json.loads((work / "samples.json").read_text())
    log = "\n".join(q.read_text(errors="replace") for q in sorted((g3a.RUNS / run_).glob("runtime*.log")))
    r["grow_size"] = sorted(set(re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)))
    r["served_files"] = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
    r["mods_off"] = "M33 mods=off" in log
    r["refused"] = re.findall(r"state=refused reason=([A-Za-z_]+)", log)
    r["g5p1"] = re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log)
    r["g6p1"] = re.findall(r"G6P1 level-tx version=(\d+) members=(\S+)", log)
    r["snap"] = re.findall(r"G5P3 tx snapshot file=(\S+) host_size=(\d+)", log)
    r["any_dev"] = len(re.findall(r"G5P1|G5P3|G6P1", log))
    r["fault"] = bool(re.search(r"access violation|engine error|[Ii]nvalid.*(indirect|function)|Unresolved indirect",
                                log))
    r["haptics"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
    r["lvl_opens"] = [o.rsplit("\\", 1)[-1].lower() for o in re.findall(r"vfs_open path=(\S+?\.lvl) result=00000000", log)]
    pc = work / "plan_copy.txt"
    r["plan_tx"] = g6.plan_tx(pc.read_text(encoding="utf-8"))[1] if pc.is_file() else []
    rj = g3a.RUNS / run_ / "run.json"
    rjd = json.loads(rj.read_text(encoding="utf-8-sig")) if rj.is_file() else {}
    r["fg"] = (rjd.get("game_foreground_events"), rjd.get("game_foreground_samples"))
    pl = work / "process_left.json"
    r["game_left"] = json.loads(pl.read_text()) if pl.is_file() else {"left": True, "missing": True}
    mf = g3a.RUNS / run_ / "m2_faults.log"
    r["fault_codes"] = sorted(set(re.findall(r"M2 exception code=([0-9A-Fa-f]+)", mf.read_text(errors="replace")))) \
        if mf.is_file() else []
    judges = {}
    for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        q = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run_], cwd=ROOT, capture_output=True, text=True)
        judges[tool] = q.returncode
        (work / f"{tool}.log").write_text(q.stdout + q.stderr)
    r["judges"] = judges
    return r


def judge(tag):
    L = g4c.layout()
    out = {lab: load(tag, case) for lab, case in CASES.items()}
    A, B1, B2, C, D = (out[k] for k in CASES)
    grown = {"B1": B1, "B2": B2, "D": D}
    watch = {"A": A, "B1": B1, "B2": B2, "C": C}
    invalid = [k for k, r in out.items() if r.get("error") or ((r.get("live_first") or {}).get("lists") or {}).get("error")
               or (k != "D" and (not r["samples"] or r["samples"][-1]["t"] - r["samples"][0]["t"] < 60))]

    def ab(r):
        return int(r["area"]["base"], 16) if r.get("area") else 0
    P, det = {}, {}
    # P1
    want_grow = sorted([("intro_10.lvl", str(SIZE), str(SIZE + N)), ("intro_10.ptr", str(PSIZE), str(PSIZE + 8 * K))])
    p1r = {}
    for k, r in grown.items():
        tid = r["plan_tx"][0][4] if r["plan_tx"] else None
        tline = ("transit.lvl", str(TSIZE), str(TSIZE))   # revision 1: the same-size member's line, required
        grow_ok = (r["grow_size"] == want_grow if tag == "h1"
                   else sorted(x for x in r["grow_size"] if x != tline) == want_grow and tline in r["grow_size"])
        p1r[k] = (grow_ok and r["served_files"] == ["intro_10.lvl", "intro_10.ptr", "transit.lvl"]
                  and r["g5p1"] == [(LEVEL, MOD, tid)] and r["g6p1"] == [("2", "lvl,ptr,transit")]
                  and sorted(x[0] for x in r["snap"]) == sorted(["intro_10.lvl", "intro_10.ptr", "transit.lvl"])
                  and not r["refused"])
    shas = {k: r.get("original_readback_sha256") for k, r in out.items()}
    P["P1_resource_transaction"] = all(p1r.values()) and A["mods_off"] and not A["grow_size"] \
        and shas["A"] is not None and len(set(shas.values())) == 1
    det["P1"] = {"per_case": p1r, "readback": shas, "grow": {k: r["grow_size"] for k, r in out.items()}}

    # P2 / P3 (G4d-1 C2 logic; D's first read only)
    def union(lst):
        d, i = lst.get("dw", {}), lst.get("inactive", {})
        both = d.get("walk", []) + i.get("walk", [])
        return set(both), len(both) == len(set(both)) and d.get("prev_ok") and i.get("prev_ok"), set(d.get("walk", []))
    a_u = union(((A.get("live_first") or {}).get("lists")) or {})[0]
    p2, p3, reg = len(a_u) == 66, True, {}
    for k, r in out.items():
        b = ab(r)
        copy_so, src_so = b + L["fc"] - 4, b + SRC - 4
        ok2 = bool(b)
        for when in ("live_first", "live_end") if k != "D" else ("live_first",):
            lst = ((r.get(when) or {}).get("lists")) or {}
            U, nodup, dws = union(lst)
            rec, per = lst.get("rec", {}), lst.get("personal", {})
            ok2 = ok2 and nodup and src_so in dws
            if k in grown:
                ok2 = (ok2 and U == a_u | {copy_so} and copy_so in dws and rec.get("count") == rec.get("n") == 123
                       and rec.get("last_so") == copy_so
                       and all(copy_so + o in lst.get("bak_targets", []) for o in (0xC4, 0x510, 0x514, 0x518))
                       and per.get("count") == 70 and per.get("last_name") == "MAN_mGenSound_Frog_G4C")
            else:
                ok2 = ok2 and U == a_u and rec.get("count") == rec.get("n") == 122 and per.get("count") == 69
        p2 = p2 and ok2
        if k in watch:
            a = r.get("actors") or {}
            sa, ca = a.get("src") or {}, a.get("copy") or {}
            lv = lambda fo: b + fo - 4                            # noqa: E731
            ok3 = bool(sa) and sa["ini"] == lv(SRC + g4c.INI) and sa["cur"] == lv(SRC + g4c.CUR)
            if k in ("B1", "B2"):
                ok3 = (ok3 and bool(ca) and ca["dsgvar"] == sa["dsgvar"] == lv(g4c.MODEL + 8)
                       and ca["ini"] == lv(L["fc"] + g4c.INI) and ca["cur"] == lv(L["fc"] + g4c.CUR)
                       and ca["mind0"] == sa["mind0"] and ca["dsgmem"] == lv(L["fc"] + g4c.DSGMEM)
                       and ca["mind_dsgmem"] == ca["dsgmem"] and ca["brain"] == lv(L["fc"] + g4c.BRAIN)
                       and ca["mind"] == lv(L["fc"] + g4c.MIND) and ca["intel"] == lv(L["fc"] + g4c.INTEL)
                       and ca["d3"] == lv(L["fc"] + g4d1.D3) and ca["brain4"] == sa["brain4"]
                       and ca["events"] == sa["events"] and len(ca["events"]) == 8 and g4c.RAW_EVENT not in ca["events"])
            reg[k] = {"ok": bool(ok3), "src": {x: v for x, v in sa.items() if x != "events"},
                      "copy": {x: v for x, v in ca.items() if x != "events"}}
            p3 = p3 and ok3
    src_ids = [{x: v for x, v in reg[k]["src"].items() if x in ("d3", "brain", "mind", "dsgmem", "ini", "cur")}
               for k in watch]
    P["P2_registration"] = bool(p2)
    P["P3_brain_mind_init"] = bool(p3) and all(x == src_ids[0] for x in src_ids)
    det["P3"] = reg
    # P4 / P5 (G4d-1 C3-C6, revision-1 estimator: nominal frame)
    F = g4d1.F
    pred_p = {"A": {"src": 30}, "C": {"src": 30}, "B1": {"src": 28, "copy": 33}, "B2": {"src": 28, "copy": 33}}
    pred_m = {"A": {"src": {1, 2}}, "C": {"src": {1, 2}}, "B1": {"src": {2}, "copy": {1}},
              "B2": {"src": {2}, "copy": {4}}}
    v5 = {"src": 500, "B1": 500, "B2": 2000}
    beh, p4, p5 = {}, True, True
    rev1 = tag != "h1"   # revision 1 applies to runs after h1; h1 stays judged by the protocol it ran under
    for k, r in watch.items():
        sm = r["samples"]
        lo = r.get("loop_oneshot")
        ms = sm[-1]["timer"] - sm[0]["timer"] if sm else 0
        for a in pred_p[k]:
            vals, iv, inwin = g4d1.seq(sm, a)
            Ps = sorted({s[a]["P"] for s in sm})
            runs = (sm[-1][a]["runs"] - sm[0][a]["runs"]) % 65536 if sm else 0
            frames = ms / F if ms else 0
            Pv = Ps[0] if len(Ps) == 1 else None
            ms_m = {m: [x for x in iv if Pv and abs(x - m * Pv * F) <= max(3, 0.004 * x)] for m in pred_m[k][a]}
            matched = sum(len(v) for v in ms_m.values())
            bad = 0
            if rev1:   # revision 1: intervals and phase in the guest's own AI-run counter (3dData +344)
                at, prev = [], None
                for i, s in enumerate(sm):
                    if prev is not None and s[a]["v8"] != prev[a]["v8"] and s[a]["v8"]:
                        at.append(s[a]["runs"])
                        if s[a]["runs"] == prev[a]["runs"]:
                            bad += 1          # a v8 write without an AI run since the previous sample
                    prev = s
                riv = [(y - x) % 65536 for x, y in zip(at, at[1:])]
                ms_m = {m: [x for x in riv if x == m] for m in pred_m[k][a]}
                matched, iv_n = sum(len(v) for v in ms_m.values()), len(riv)
            elif Pv:
                for s in sm:
                    rt = s["timer"] - s[a]["ctr"] * F
                    d = (rt - s[a]["v8"]) / (Pv * F)
                    if s[a]["v8"] and abs(d - round(d)) * Pv * F > F + 3 + 0.004 * max(0, rt - s[a]["v8"]):
                        bad += 1
            e = {"P": Ps, "runs": runs, "frames": round(frames, 1),
                 "runs_per_frame": round(runs / frames, 5) if frames else None, "n_values": len(vals),
                 "intervals": len(iv), "by_m": {m: len(v) for m, v in ms_m.items()},
                 "unmatched": sorted(set(riv if rev1 else iv) - {x for v in ms_m.values() for x in v})[:10],
                 "run_intervals": len(riv) if rev1 else None, "ms_unmatched_nominal": sorted(
                     set(iv) - {x for x in iv if Pv and any(abs(x - m * Pv * F) <= max(3, 0.004 * x)
                                                            for m in pred_m[k][a])})[:10],
                 "median": statistics.median(iv) if iv else None, "phase_bad": bad, "v8_first": vals[:6],
                 "ini_v5": sorted({s[a]["ini_v5"] for s in sm}), "cur_v5": sorted({s[a]["cur_v5"] for s in sm}),
                 "beh_ok": bool(sm) and all(s[a]["beh"] == lo for s in sm), "inwin_all": bool(inwin) and all(inwin)}
            beh[f"{k}_{a}"] = e
            p4 = (p4 and e["beh_ok"] and e["n_values"] >= 10 and e["inwin_all"] and Pv == pred_p[k][a] and frames
                  and abs(runs / frames - 1 / Pv) <= 0.03 / Pv and matched == (iv_n if rev1 else len(iv)) > 0 and bad == 0)
            want = v5["src"] if a == "src" else v5[k]
            p5 = p5 and e["ini_v5"] == e["cur_v5"] == [want]
        if k in ("B1", "B2"):
            p5 = (p5 and g4d1.seq(sm, "src")[0] != g4d1.seq(sm, "copy")[0]
                  and len({reg[k]["src"]["ini"], reg[k]["src"]["cur"], reg[k]["copy"]["ini"], reg[k]["copy"]["cur"]}) == 4)
    p5 = (p5 and beh["B1_copy"]["median"] is not None and abs(beh["B1_copy"]["median"] - 33 * F) <= 3
          and beh["B2_copy"]["median"] is not None and abs(beh["B2_copy"]["median"] - 132 * F) <= 8
          and beh["B1_src"]["by_m"] == {2: beh["B1_src"]["run_intervals" if rev1 else "intervals"]}
          and beh["B2_src"]["by_m"] == {2: beh["B2_src"]["run_intervals" if rev1 else "intervals"]}
          and all(not r.get("level_change_t") and "intro_15.lvl" not in r["lvl_opens"] for r in watch.values()))
    P["P4_script_execution"] = bool(p4)
    P["P5_independent_behaviour"] = bool(p5)
    det["behaviour"] = beh
    # P6 / P7
    alloc = {}
    for k, r in out.items():
        st = r["states"]
        i0 = next((j for j, x in enumerate(st) if "invalid" not in x), None)
        valid = i0 is not None and not any("invalid" in x for x in st[i0:])
        used = [s for s in st if "invalid" not in s and "1" in s.get("areas", {}) and s.get("state") != "after_change"]
        fa = [s for s in st if s.get("state") in ("after_change", "final") and "invalid" not in s
              and "1" in s.get("areas", {}) and s["areas"]["1"]["length"] == 8474196]
        alloc[k] = {"valid": valid, "length": (r.get("area") or {}).get("length"),
                    "free_after": used[-1]["free_bytes"] if used else None,
                    "after_change": [(s["areas"]["1"]["base"], s["free_bytes"]) for s in fa][-1:],
                    "level_change_t": r.get("level_change_t")}
    P["P6_runtime_integrity"] = all(a["valid"] for a in alloc.values()) and P["P2_registration"] \
        and not any(r["fault"] for r in out.values()) and P["P3_brain_mind_init"]
    p7 = all(alloc[k]["length"] == AREA + (N if k in grown else 0) for k in out)
    p7 = p7 and alloc["A"]["free_after"] == FREE0 == alloc["C"]["free_after"] \
        and alloc["B1"]["free_after"] == FREE0 - N == alloc["B2"]["free_after"]
    p7 = p7 and alloc["D"]["after_change"] == [("0x40f5f320", 12234744)] \
        and (alloc["D"]["level_change_t"] or 1e9) <= 130 and "intro_15.lvl" in D["lvl_opens"]
    P["P7_exit_cleanup"] = bool(p7)
    det["alloc"] = alloc
    # P8
    off = json.loads((WORK / "offline.json").read_text()).get("pass")
    neg = json.loads((WORK / "negtest" / "summary.json").read_text()).get("pass")
    P["P8_production_safety"] = (C["refused"] == ["level_tx_not_enabled"] and not C["grow_size"] and not C["served_files"]
                                 and C["any_dev"] == 0 and off and neg
                                 and all(r["haptics"] and not any(r["judges"].values()) and r["runner_exit"] == 0
                                         and r["game_left"].get("left") is False and r["fg"] == (0, 0)
                                         and set(r["fault_codes"]) <= {"406D1388"} for r in out.values()))
    det["P8"] = {k: {"refused": r["refused"], "exit": r["runner_exit"], "left": r["game_left"].get("left"), "fg": r["fg"],
                     "faults": r["fault_codes"], "judges": r["judges"], "any_dev": r["any_dev"]} for k, r in out.items()}
    result = {"tag": tag, "invalid": invalid, "criteria": P, "pass": not invalid and all(P.values()), "details": det}
    (WORK / f"judgement_{tag}.json").write_text(json.dumps(result, indent=1, default=str) + "\n")
    print(json.dumps({"invalid": invalid, "criteria": P}, indent=1))
    return 0 if result["pass"] else 1


def main():
    a = sys.argv[1:]
    if a == ["check"]:
        return check()
    if a == ["negtest"]:
        return negtest()
    if len(a) == 2 and a[0] == "run" and re.fullmatch(r"[A-Za-z0-9_-]{1,16}", a[1]):
        return run(a[1])
    if len(a) == 2 and a[0] == "judge":
        return judge(a[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
