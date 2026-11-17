#!/usr/bin/env python3
"""E-484 (D-251) G6-P1: one typed, development-only `insert-passive-lum` operation that reproduces G4b's additional
intro_10 lum (E-471, D-238) through the G5 compiler (tools/r3hd_mods.py) and a version-2 `level-tx` (intro_10.lvl,
intro_10.ptr and transit.lvl) of the development transaction gate (g5p1_dev_gate.py, G6-P1 edits).

usage:
  g6p1_pilot.py check        offline O1-O8 (real game files read-only; no game started)
  g6p1_pilot.py negtest      runtime-transaction cases (g5p1_tx_test.cpp against the development and production
                             headers) and G5-P5's negtest re-run against the extended development header
  g6p1_pilot.py TAG          hidden runs A, B, C, D (development build; G4b's runner, g4b_ab.run_case, unchanged)
  g6p1_pilot.py judge TAG    P1-P8
Outputs stay under private/work/e484/.

OPERATION (manifest): {"type": "insert-passive-lum", "level": "intro_10", "model": LUM10 (the lum model's key),
  "instance": 6 (actor index in file order; SuperObject 0x549A30, G4b's source), "lvl_sha256", "ptr_sha256",
  "transit_sha256" (exact original files), "position": [x, y, z] within 1 unit of an approved anchor (G4b B
  `beside_source` = source + 5 z; G4b C / E `flight_path` = (17.87, -101.22, -44.18))}. No addresses, offsets,
  relocation slots, record bytes or pointers are accepted. One per mod; never with insert-graph-node.
TRANSACTION: `level-tx 2 intro_10 <mod> <id>`; members lvl (grown), ptr (grown, one whole range), transit (same size,
  one 4-byte range on the dynamic world's count); id = SHA-256 of "level-tx 2 ..." + the three tx-file lines (role
  order lvl, ptr, transit). Version 1 is unchanged (`render --no-g6` = the f0fe6ac header byte for byte).

EXPECTED (G4b's verified values; E-471 offline gate and m4):
  .lvl 7,661,836 -> 7,663,280 (+1,444; copy at 7,661,840); .ptr 209,068 -> 209,388 (40 entries: 39 own-file, 1 to
  transit); transit.lvl 41,508 bytes, only 0x9C4 60 -> 61; 10 edited words 0x1C78 0x1C7C 0x1CF0 0x539320 0x549A44
  0x549F00 0x5A59D4 0x5A7438 0x5A743C 0x5A9648; new personal index 69 (`NIN_m_Lums_Int10_G4B`); records 122 -> 123;
  backups + 1; personal 69 -> 70; dynamic world 60 -> 61 with the copy right after the source. Exit plan: the same
  structural mod plus an ordinary `designer-default` mod (generator NIN_m_GenFlyIntro_10 instance 0, variable 5,
  byte 5): its two bytes are G4b E's edit, so the composed .lvl image is G4b's exit image.
  Memory: area growth 1,444, free after load 13,088,528 - 1,444 = 13,087,084 (G4b m4 measured), loader temporary
  bound 4 x (1,444 + 209,388 + 8 x 495) = 859,168, headroom >= 0 beyond the 1 MiB margin; pre-read 7,663,280 <=
  8,474,200; development snapshot (load-time host copies) 7,661,836 + 7,663,280 + 209,068 + 209,388 + 2 x 41,508 =
  15,826,588 <= 16 MiB; the copy's 3dData buffer is allocated at init outside block 8 (G4b A7).

OFFLINE (check):
  O1 G4b equivalence: for `flight_path` and `beside_source` the compiler's three images equal g4b_ab.construct (the
     G4b constructor, offline oracle) AND the retained images the verified m4 run served (private/work/e471/m4/
     {on,off}/*_range.bin); the full pipeline (import, resolve, plan) gives the same images from the plan; the exit
     composition equals construct(exit) and m4/exit. Byte for byte, all lengths.
  O2 actor identity: independent simulation (g4b_ab.simulate, g3a.relocate): 61 actors, the copy distinct and right
     after the source, nothing else added; personal index 69 = the old count, its name unique; one SO record each.
  O3 hierarchy and registration: records 123 with the copy's last; backups end with the copy's matrix, its copy the
     new translation; personal 70; previous links consistent; transit count 61; source's lists unchanged.
  O4 relocation: 40 new entries, unique, none an original slot, each inside the new objects or one of the 3 old list
     ends; 39 own-file targets inside the level, 1 to transit 0x9B4 (the parent); originals and the cross-file table
     byte-identical; only the 10 words changed; no duplicate slot after relocation.
  O5 atomic transaction: the plan has one `level-tx 2`, three `tx-file` (lvl, ptr, transit), grows for lvl and ptr
     only, transit one 4-byte range; the id recomputed independently; a repeat compile gives identical images, ranges
     and id; the mod is marked gameplay; the runtime cases are in negtest.
  O6 memory: the values above, from the compiler's structural_budget; growth caps (4,096 / 1,024) hold.
  O7 negative rejection (compile time, whole mod refused, nothing installed or no transaction): opt-in unset or for
     another level; wrong lvl / ptr / transit hash; missing transit.lvl; other instance or model; position 1.5 units
     from an anchor or non-finite; extra key; two lums or lum + graph node in one mod; lum mod + graph mod on intro_10
     (both STRUCTURAL_CONFLICT). Simulator (the compiler's verify_passive_lum) on mutated results: duplicate
     personal index, broken sibling link, record list count, transit count, duplicate and out-of-object relocation
     entries, an alias into the source, a changed extra word: all refused.
  O8 compatibility: G5-P5's check (43) and negtest re-run under e484/o8_g5p5 (G5-P1, G5-P2a, G5-P4a, G5-P3
     included) against the extended header; insert-graph-node output (sites 13, 22, dual, intro_20 site 3: ranges,
     images, plan text without the timestamp) identical to the f0fe6ac compiler; selftest; production header unchanged
     (tools/m33_mod_overlay.h has no level-tx); the production test executable refuses the version-2 plan.

PROSPECTIVE PROTOCOL (committed before any modified run; constants from `check`, not from a run)
Build: g5p1_dev_gate.py apply + tools\\build_incremental.bat; afterwards revert + rebuild (production).
Runs: G4b's runner g4b_ab.run_case, unchanged, bound here (PREFIX e484, the gate variable R3HD_DEV_STRUCTURAL_TX =
  intro_10, the plan from the compiler): hidden, non-activating, muted, no physical pad, private user root,
  `--test-level intro_10`, no input, no captures, 150 s; generator every 0.1 s for 75 s, copy / source blocks and
  lists every 1 s (first live read, end read).
  A `base` (no plan).  B `on`: the lum mod at `flight_path`.  C `nogate`: B's plan, gate variable unset.
  D `exit`: B's mod + the generator variable-5 designer-default mod (G4b E's controlled collection and exit).
  (G4b's off-path case is not repeated: B's pickup interval and the first live read cover independent state.)
Criteria:
  P1 resource identity (B, D): one `M33 mods state=active`; one `G5P1 level-tx active` with the plan's level, mod and
     id and one `G6P1 level-tx version=2 members=lvl,ptr,transit`; `G5P3 tx snapshot` lines exactly intro_10.lvl
     image 7,663,280, intro_10.ptr 209,388, transit.lvl 41,508, the last disk_reads=3; `M36 grow size` contains
     exactly intro_10.lvl 7,661,836 -> 7,663,280 and intro_10.ptr 209,068 -> 209,388 (and transit.lvl, if present,
     41,508 -> 41,508); `M33 mods served` files exactly {intro_10.lvl, intro_10.ptr, transit.lvl}; no `G5P3 tx
     host_changed`; masked read-back of the original area (G4b's mask) equal in A, B, C, D.
  P2 actor registration (B, D at the first live read): the union U of the dynamic and inactive dynamic worlds has no
     SuperObject twice and both walks' previous links hold; U = U(A) + the copy exactly; the copy in the dynamic world;
     SO-record header count = walk = 123 with the copy's record last; the backup list holds the copy's matrix;
     personal count 70, last name NIN_m_Lums_Int10_G4B.
  P3 independent state (B, D): the copy's 3dData buffer word (+0x14C) non-zero and different from the source's;
     Brain +4 = 0xCDCDCDCD in both; no live word of the copy points into the source's block except its previous link
     (+0x18) and no live word of the source points into the copy except its next link (+0x14); across the pickup
     interval the copy changes >= 1 block offset the source does not; the source keeps its file translation and
     personal index.
  P4 functional collection: B: generator variable 5 0 -> 1 exactly once, minimum generator-to-copy distance <= 3.0
     within 2 s of the change, then stays 1; D: 5 -> 6 first, same distance rule; A, C: 0 throughout, no change.
  P5 registry consistency after collection (B, end read, after its collection): no duplicates, previous links hold,
     U = U(A at its first read) + the copy, records 123 with the copy's last, personal 70, the copy's matrix in the
     backup list (G4b m4 C's recorded end state: 42 + 25 = 67, 123, 70, 182 backups).
  P6 level transition and cleanup (D; every run): valid block-8 walks in every snapshot after the first valid one;
     intro_10 area length 7,661,832 + 1,444 (B, D) / 7,661,832 (A, C); free after load 13,087,084 (B) and 13,088,528
     (A, C); D: intro_15.lvl opened and the level changed within 130 s of open, then intro_15's area at 0x40F5F320
     and free 12,234,744 (E-465a's / G4b m4 E's exact values: the grown intro_10 area, records and copy freed).
  P7 negative transaction control (C): `state=refused reason=level_tx_not_enabled`; no `M36 grow`, no `M33 mods
     served`, no `G5P1` / `G5P3` / `G6P1` line; U = U(A), records 122, personal 69, variable 5 0 throughout.
  P8 desktop and runtime safety (every run): haptics policy line; M21 / M22 / M23 0; runner exit 0;
     game_foreground_events = game_foreground_samples = 0 in run.json; no engine error / crash line; m2_faults.log
     has no exception code other than 406D1388 (the MSVC thread-naming notice present in every prior hidden run, e.g.
     E-471 m4, E-482 r1); no game process left = D-250's ownership check (g3a.game_left: 5 s after the runner ended,
     no r3hd.exe whose command line names the run; recorded by this script's `run` around G4b's unchanged runner, whose
     pid-only value is kept but not judged); `check` and `negtest` passed before the runs.
  Correction before any run (same session, before the first modified run): P8's leftover-process check was first
  written with G4b's pid-only value, which D-250 superseded after E-483 l1; it now uses g3a.game_left.
  Invalid (new tag, not judged): file hashes differ, level not opened, area / generator not found, < 60 s of samples
  in A, B, C. Stop: a guest fault, registration corruption or desktop-safety violation in any case.
  All eight = G6-P1 VERIFIED — TYPED PASSIVE ACTOR INSERTION; P2 and P3 passing with P4 failing = PARTIAL.
"""
import argparse
import hashlib
import json
import math
import os
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
import g4b_ab as g4b  # noqa: E402
import g5p1_pilot as p1  # noqa: E402

PREFIX = "e484"
WORK = ROOT / "private" / "work" / PREFIX
p1.WORK = WORK
LEVEL = "intro_10"
ENV = rm.STRUCT_ENV
MOD, EXIT_MOD = "g6p1.lum", "g6p1.gen5"
BASELINE = "f0fe6ac"
M4 = ROOT / "private" / "work" / "e471" / "m4"
u32, fnv = g3a.u32, g3a.fnv
SIZE, PSIZE, AREA, FREE0 = g3a.SIZE, g3a.PSIZE, g3a.AREA, g3a.FREE0
TSIZE = g4b.TSIZE
N, K = 1444, 40
EDITED = [0x1C78, 0x1C7C, 0x1CF0, 0x539320, 0x549A44, 0x549F00, 0x5A59D4, 0x5A7438, 0x5A743C, 0x5A9648]
TEMP_BOUND = 4 * (N + PSIZE + 8 * K + 8 * 495)
SNAPSHOT = SIZE + SIZE + N + PSIZE + PSIZE + 8 * K + 2 * TSIZE
NEW_NAME = "NIN_m_Lums_Int10_G4B"
VARIANT_ANCHOR = {"on": "flight_path", "off": "beside_source"}


def files():
    return g4b.files()


def anchor(variant):
    with p1.dev_env():
        return list(rm.lum_anchors(files()[0], rm.LUM_ALLOW[LEVEL])[VARIANT_ANCHOR[variant]])


def lum(variant="on", **kw):
    data, ptr, tl = files()
    o = {"type": "insert-passive-lum", "level": LEVEL, "model": rm.LUM10, "instance": 6,
         "lvl_sha256": hashlib.sha256(data).hexdigest(), "ptr_sha256": hashlib.sha256(ptr).hexdigest(),
         "transit_sha256": hashlib.sha256(tl).hexdigest(), "position": anchor(variant)}
    o.update(kw)
    return o


def gen5():
    ix = rm.read_script_index(g3a.GAME, LEVEL)
    entry = ix["defaults"][rm.FLY10]
    return {"type": "designer-default", "level": LEVEL, "model": rm.FLY10, "instance": 0, "variable": 5,
            "initial_sha256": rm.designer_hash(ix, entry["instances"][0], entry["length"]), "kind": "byte",
            "value": 5}


def mods_for(variant):
    return [(MOD, [lum("on" if variant == "exit" else variant)])] + ([(EXIT_MOD, [gen5()])] if variant == "exit"
                                                                      else [])


def compiled(variant="on", **kw):
    with p1.dev_env():
        return rm.compile_insert_passive_lum(lum(variant, **kw), {"game": g3a.GAME})


def refused(fn, code, env=LEVEL):
    with p1.dev_env(env):
        return p1.refused(fn, code)


def import_refused(name, mods, code, env=LEVEL):
    """A mod set imported into a fresh root: (the first mod's import refused with `code`) or (resolved: the codes)."""
    paths = p1.fresh(name)
    with p1.dev_env(env):
        for mid, ov in mods:
            try:
                p1.install(paths, mid, ov)
            except rm.Refusal as x:
                return x.code == code or f"import {x.code}: {x.detail}"
        res = rm.resolve_all(paths, write_plan=paths["cache"])
    codes = [r.get("code") for r in res["mods"]]
    return (all(c == code for c in codes) and not res["active"]) or f"resolved {codes} active {res['active']}"


def plan_tx(text):
    m = p1.parse_plan(text)
    return m, [ln.split(" ") for ln in m["txs"]]


def canonical_id(m):
    """The transaction id from the plan's own records, recomputed here (not by the compiler)."""
    _, version, level, mod, _ = m["txs"][0].split(" ")
    rows = []
    for f in m["files"]:
        for t in f["tx"]:
            role, orig, guest, result = t.split(" ")
            rows.append((role, Path(f["path"]).name.lower(), f["size"], orig, guest, result))
    text = f"level-tx {version} {level} {mod}\n" + "".join(f"tx-file {r} {n} {s} {o} {g} {x}\n"
                                                         for r, n, s, o, g, x in sorted(rows))
    return hashlib.sha256(text.encode("ascii")).hexdigest()[:16]


def old_compiler():
    """The f0fe6ac compiler (before G6-P1), loaded under another module name from a private copy."""
    d = WORK / "old_compiler"
    d.mkdir(parents=True, exist_ok=True)
    src = subprocess.run(["git", "show", f"{BASELINE}:tools/r3hd_mods.py"], cwd=ROOT, capture_output=True,
                         check=True).stdout
    (d / "r3hd_mods_f0fe6ac.py").write_bytes(src)
    import importlib.util
    spec = importlib.util.spec_from_file_location("r3hd_mods_f0fe6ac", d / "r3hd_mods_f0fe6ac.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.TOOLS, mod.ROOT = TOOLS, ROOT   # release tables and default paths: the repository's (used at call time)
    return mod


# --- offline -----------------------------------------------------------------------------------------------------

def check():
    data, ptr, tl = files()
    slots, cross = g4b.index(data, ptr)
    res, det = {}, {}
    B1 = 0x40F5509C
    # O1 G4b equivalence: compiler images = the G4b constructor = the images the verified m4 run served
    eq = {}
    for v in ("on", "off"):
        _, tx = compiled(v)
        im = tx["images"]
        nl, np_, ntl, _ = g4b.construct(data, ptr, tl, v)
        m4 = {k: (M4 / v / f"{k}_range.bin").read_bytes() for k in ("lvl", "ptr", "transit")}
        r, text, _ = p1.compile_plan(f"eq_{v}", mods_for(v))
        pim = p1.images(p1.parse_plan(text)) if text else {}
        eq[v] = {"construct": (im["lvl"], im["ptr"], im["transit"]) == (nl, np_, ntl),
                 "m4": (im["lvl"], im["ptr"], im["transit"]) == (m4["lvl"], m4["ptr"], m4["transit"]),
                 "plan": (pim.get("intro_10.lvl"), pim.get("intro_10.ptr"), pim.get("transit.lvl")) == (nl, np_, ntl),
                 "lengths": (len(im["lvl"]), len(im["ptr"]), len(im["transit"])) == (SIZE + N, PSIZE + 8 * K, TSIZE),
                 "sha256": [hashlib.sha256(im[k]).hexdigest() for k in ("lvl", "ptr", "transit")],
                 "active": r["active"] == [MOD]}
    r, text, _ = p1.compile_plan("eq_exit", mods_for("exit"))
    pim = p1.images(p1.parse_plan(text)) if text else {}
    nl, np_, ntl, _ = g4b.construct(data, ptr, tl, "exit")
    m4 = {k: (M4 / "exit" / f"{k}_range.bin").read_bytes() for k in ("lvl", "ptr", "transit")}
    got = (pim.get("intro_10.lvl"), pim.get("intro_10.ptr"), pim.get("transit.lvl"))
    eq["exit"] = {"construct": got == (nl, np_, ntl), "m4": got == (m4["lvl"], m4["ptr"], m4["transit"]),
                  "active": r["active"] == [MOD, EXIT_MOD], "gameplay": sorted(r["gameplay_active"]) == [EXIT_MOD, MOD]}
    det["O1"] = eq
    res["O1_g4b_equivalence"] = all(all(v for k, v in e.items() if k != "sha256") for e in eq.values())
    # O2 / O3 identity, hierarchy and registration: G4b's independent simulator on the compiler's images
    s0 = g4b.simulate(data, ptr, tl)
    reg = {}
    for v in ("on", "off"):
        _, tx = compiled(v)
        L = tx["info"]["objects"]
        s1 = g4b.simulate(tx["images"]["lvl"], tx["images"]["ptr"], tx["images"]["transit"])
        copy = B1 + L["copy"] - 4
        rd = s1["rd"]
        std = g4b.construct(data, ptr, tl, v)[3]["src_std"]
        names = []
        for e in s1["pel"]:
            nm = rd(e + 0xC)
            names.append(bytes(s1["area"][nm - B1:nm - B1 + 0x40]).split(b"\0")[0].decode("ascii", "replace"))
        o2 = (not s1["dup"] and len(s1["walk"]) == len(set(s1["walk"])) == 61 and copy not in s0["walk"]
              and [x for x in s1["walk"] if x != copy] == s0["walk"]
              and s1["walk"][s1["walk"].index(B1 + g4b.SRC - 4) + 1] == copy
              and u32(tx["images"]["lvl"], L["copy"] + std - g4b.SRC + 8) == 69 == s0["p_count"]
              and names[-1] == NEW_NAME and names.count(NEW_NAME) == 1
              and [rd(r + 4) for r in s1["recs"]].count(copy) == 1
              and [rd(r + 4) for r in s1["recs"]].count(B1 + g4b.SRC - 4) == 1)
        o3 = (s1["prev_ok"] and s1["dw_count"] == 61 and s1["walk"][-1] == s1["last"] == s0["last"]
              and len(s1["recs"]) == s1["rec_count"] == 123 and s1["recs"][:-1] == s0["recs"]
              and s1["recs"][-1] == s1["rec_last"] == B1 + L["record"] - 4 and rd(s1["recs"][-1] + 4) == copy
              and s1["links"][:-1] == s0["links"] and s1["links"][-1] == s1["bak_last"] == B1 + L["backup"]
              and rd(B1 + L["backup"] + 4) == copy + 0xC4
              and len(s1["pel"]) == s1["p_count"] == 70 and s1["pel"][:-1] == s0["pel"]
              and s1["pel"][-1] == s1["p_last"] == B1 + L["personal"] - 4)
        reg[v] = {"O2": o2, "O3": o3, "copy_file": L["copy"], "new_index": 69, "actors": len(s1["walk"]),
                  "records": len(s1["recs"]), "personal": len(s1["pel"]), "backups": len(s1["links"])}
    det["O2_O3"] = reg
    res["O2_actor_identity"] = all(r["O2"] for r in reg.values())
    res["O3_hierarchy_registration"] = all(r["O3"] for r in reg.values())
    # O4 relocation and fixups
    _, tx = compiled("on")
    nl, np_, ntl = tx["images"]["lvl"], tx["images"]["ptr"], tx["images"]["transit"]
    n0, n1 = u32(ptr, 0), u32(np_, 0)
    new = [struct.unpack_from(">iI", np_, 4 + 8 * i) for i in range(n0, n1)]
    new_slots = [loc + 4 for _, loc in new]
    L = tx["info"]["objects"]
    objs = [(L["copy"], g4b.BLK), (L["personal"], 0x14), (L["name"], 24), (L["record"], 0x48), (L["backup"], 0x18),
            (L["backup_copy"], 0x54)]
    tails = {0x539320, 0x5A9648, 0x5A59D4}
    area, seen, dup = g3a.relocate(nl, np_, B1)
    own = [s for f, s in zip([f for f, _ in new], new_slots) if f == 1]
    other = [(f, s) for f, s in zip([f for f, _ in new], new_slots) if f != 1]
    changed = sorted({i & ~3 for i in range(SIZE) if nl[i] != data[i]})
    o4 = (n1 - n0 == K and len(set(new_slots)) == K and not any(s in slots for s in new_slots)
          and all(any(a <= s < a + z for a, z in objs) or s in tails for s in new_slots)
          and all(u32(nl, s) + 4 < len(nl) for s in own) and len(own) == 39
          and other == [(2, L["copy"] + 0x1C)] and u32(nl, L["copy"] + 0x1C) + 4 == 0x9B4
          and np_[4:4 + 8 * n0] == ptr[4:4 + 8 * n0] and np_[4 + 8 * n1:] == ptr[4 + 8 * n0:]
          and not dup and changed == EDITED and [i for i in range(TSIZE) if ntl[i] != tl[i]] == [0x9C7]
          and u32(ntl, 0x9C4) == 61 and len(nl) == SIZE + N and len(np_) == PSIZE + 8 * K)
    det["O4"] = {"entries": n1 - n0, "own": len(own), "other": [(f, hex(s)) for f, s in other],
                 "changed": [hex(x) for x in changed], "relocation_duplicates": bool(dup)}
    res["O4_relocation"] = bool(o4)
    # O5 atomic transaction: the plan's records, the id recomputed independently, determinism, gameplay
    r1, t1, paths1 = p1.compile_plan("o5_a", mods_for("on"))
    r2, t2, paths2 = p1.compile_plan("o5_b", mods_for("on"))
    m, txs = plan_tx(t1 or "")
    roles = {Path(f["path"]).name: [t.split(" ")[0] for t in f["tx"]] for f in m["files"]}
    grows = {Path(f["path"]).name: f["grow"] for f in m["files"]}
    tr = next((f for f in m["files"] if Path(f["path"]).name == "transit.lvl"), {"range": []})
    def strip(t, paths):
        """The plan text without its timestamp comment and with the fresh root's folder (range blobs) normalized."""
        return "\n".join(x.replace(str(paths["_dir"].resolve()), "<root>") for x in (t or "").splitlines()
                         if not x.startswith("#"))
    _, txb = compiled("on")
    o5 = (len(txs) == 1 and txs[0][1] == "2" and txs[0][2] == LEVEL and txs[0][3] == MOD
          and roles == {"intro_10.lvl": ["lvl"], "intro_10.ptr": ["ptr"], "transit.lvl": ["transit"]}
          and grows == {"intro_10.lvl": [str(SIZE + N)], "intro_10.ptr": [str(PSIZE + 8 * K)], "transit.lvl": []}
          and [x.split(" ")[:2] for x in tr["range"]] == [["2500", "4"]] and canonical_id(m) == txs[0][4]
          and strip(t1, paths1) == strip(t2, paths2) and r1["gameplay_active"] == [MOD] and r1["structural_active"] == {MOD: LEVEL}
          and txb["images"] == tx["images"] and rm.tx_id(LEVEL, MOD, []) != rm.tx_id(LEVEL, MOD, [], 2))
    det["O5"] = {"tx": txs, "roles": roles, "grows": grows, "transit_ranges": tr["range"], "id_recomputed":
                 canonical_id(m) if m["txs"] else None}
    res["O5_atomic_transaction"] = bool(o5)
    # O6 memory budget
    mem = tx["info"]["memory"]
    o6 = (mem["area_growth"] == N and mem["free_after_load"] == FREE0 - N == 13087084
          and mem["temporary_bound"] == TEMP_BOUND == 859168 and mem["headroom"] >= 0
          and mem["preread"] == SIZE + N <= mem["preread_verified"] and N <= rm.STRUCT_MAX_GROW["lvl"]
          and 8 * K <= rm.STRUCT_MAX_GROW["ptr"] and SNAPSHOT == 15826588 <= 16 << 20)
    det["O6"] = dict(mem, snapshot=SNAPSHOT, snapshot_budget=16 << 20)
    res["O6_memory"] = bool(o6)
    # O7 negative rejection
    neg = {}
    ok_o = lum("on")
    neg["no_opt_in_parse"] = refused(lambda: rm.parse_insert_passive_lum(ok_o, "o"), "UNSUPPORTED", None)
    neg["no_opt_in_compile"] = refused(lambda: rm.compile_insert_passive_lum(ok_o, {"game": g3a.GAME}),
                                       "UNSUPPORTED", None)
    neg["opt_in_other_level"] = refused(lambda: rm.compile_insert_passive_lum(ok_o, {"game": g3a.GAME}),
                                        "UNSUPPORTED", "intro_20")
    neg["other_level"] = refused(lambda: rm.parse_insert_passive_lum(dict(ok_o, level="intro_20"), "o"),
                                 "UNSUPPORTED")
    neg["extra_key"] = refused(lambda: rm.parse_insert_passive_lum(dict(ok_o, offset=4), "o"), "BAD_MANIFEST")
    neg["address_key"] = refused(lambda: rm.parse_insert_passive_lum(dict(ok_o, so=0x549A30), "o"), "BAD_MANIFEST")
    for k in ("lvl_sha256", "ptr_sha256", "transit_sha256"):
        neg[f"wrong_{k}"] = refused(lambda: compiled("on", **{k: "0" * 64}), "TARGET_CHANGED")
    neg["other_instance"] = refused(lambda: compiled("on", instance=5), "UNSUPPORTED")
    neg["other_model"] = refused(lambda: compiled("on", model=rm.FLY10), "UNSUPPORTED")
    a = anchor("on")
    neg["position_1_5_units"] = refused(lambda: compiled("on", position=[a[0] + 1.5, a[1], a[2]]), "UNSUPPORTED")
    neg["position_0_9_units_accepted"] = compiled("on", position=[a[0] + 0.9, a[1], a[2]])[1]["info"]["anchor"] \
        == "flight_path"
    neg["position_nan"] = refused(lambda: rm.parse_insert_passive_lum(dict(ok_o, position=[float("nan"), 0, 0]),
                                                                      "o"), "BAD_MANIFEST")
    fake = WORK / "fake_game"
    if fake.exists():
        shutil.rmtree(fake)
    (fake / "GAMEDATAbin" / LEVEL).mkdir(parents=True)
    for p in (g3a.LVL, g3a.PTR):
        shutil.copyfile(p, fake / "GAMEDATAbin" / LEVEL / p.name)
    neg["missing_transit"] = refused(lambda: rm.compile_insert_passive_lum(ok_o, {"game": fake}), "TARGET_MISSING")
    shutil.rmtree(fake)
    graph13 = {"type": "insert-graph-node", "level": LEVEL, "model": rm.FLY10, "instance": 0, "variable": 0,
               "after_node": 13, "lvl_sha256": ok_o["lvl_sha256"], "ptr_sha256": ok_o["ptr_sha256"],
               "position": [18.0, -33.0, -42.0]}
    neg["two_lums_one_mod"] = import_refused("o7_two", [("g6p1.two", [ok_o, lum("off")])], "BAD_MANIFEST")
    neg["lum_and_graph_one_mod"] = import_refused("o7_mix", [("g6p1.mix", [ok_o, graph13])], "BAD_MANIFEST")
    neg["lum_mod_and_graph_mod"] = import_refused("o7_both", [(MOD, [ok_o]), ("g6p1.graph", [graph13])],
                                                  "STRUCTURAL_CONFLICT")
    neg["production_compiler_no_env"] = import_refused("o7_prod", [(MOD, [ok_o])], "UNSUPPORTED", None)
    # the simulator refuses mutated results (the compiler's own verify_passive_lum, called on edited images)
    spec = rm.LUM_ALLOW[LEVEL]
    with p1.dev_env():
        ix = rm.read_script_index(g3a.GAME, LEVEL)
    peers = [i["so"] for n, i in enumerate(ix["placements"][rm.LUM10]) if n != 6]
    pos = tuple(a)
    s = rm._lum_source(data, ptr, tl, 1, spec, peers, "neg")
    Lb = tx["info"]["objects"]
    added = [(f, loc + 4) for f, loc in new]
    edits = [(o, "") for o in EDITED]

    def mut(lvl=None, ptr_=None, tl_=None, slots_=None):
        def run():
            rm.verify_passive_lum(data, ptr, tl, lvl or nl, ptr_ or np_, tl_ or ntl, 1, spec, s, Lb, slots_ or added,
                                  edits, pos, "neg")
        return p1.refused(run, "STRUCTURE_CHECK")

    def word(buf, o, v):
        b = bytearray(buf)
        struct.pack_into(">I", b, o, v)
        return bytes(b)
    neg["sim_valid_accepted"] = p1.refused(lambda: rm.verify_passive_lum(
        data, ptr, tl, nl, np_, ntl, 1, spec, s, Lb, added, edits, pos, "neg"), "STRUCTURE_CHECK") is False
    std = s["std"] - g4b.SRC + Lb["copy"]
    neg["sim_duplicate_personal_index"] = mut(lvl=word(nl, std + 8, 42))
    neg["sim_broken_sibling_link"] = mut(lvl=word(nl, s["next"] + 0x18, g4b.SRC - 4))
    neg["sim_record_count"] = mut(lvl=word(nl, spec["records"] + 8, 122))
    neg["sim_transit_count"] = mut(tl_=tl)
    dup_ptr = bytearray(np_)
    dup_ptr[4 + 8 * (n1 - 1):4 + 8 * n1] = dup_ptr[4 + 8 * (n1 - 2):4 + 8 * (n1 - 1)]
    neg["sim_duplicate_relocation"] = mut(ptr_=bytes(dup_ptr))
    out_ptr = bytearray(np_)
    struct.pack_into(">iI", out_ptr, 4 + 8 * (n1 - 1), 1, 0x100 - 4)
    neg["sim_relocation_outside_objects"] = mut(ptr_=bytes(out_ptr), slots_=added[:-1] + [(1, 0x100)])
    neg["sim_alias_into_source"] = mut(lvl=word(nl, Lb["copy"] + 0x20, g4b.SRC + 0xC4 - 4))
    neg["sim_extra_word_changed"] = mut(lvl=word(nl, 0x1000, u32(nl, 0x1000) ^ 1))
    det["O7"] = neg
    res["O7_negative_rejection"] = all(v is True for v in neg.values())
    # O8 compatibility: insert-graph-node output identical to the f0fe6ac compiler; selftest; production header
    old = old_compiler()
    import g5p2a_pilot as p2
    import g5p4a_pilot as p4
    comp = {}
    cases = [("intro_10_13", [p2.igm(13, "neutral")]), ("intro_10_22", [p2.igm(22, "offset")]),
             ("intro_10_dual", [p2.igm(13, "neutral"), p2.igm(22, "neutral")])]
    for name, ops in cases:
        with p1.dev_env():
            a_ = rm.compile_insert_graph_nodes(ops, {"game": g3a.GAME})
            b_ = old.compile_insert_graph_nodes(ops, {"game": g3a.GAME})
        comp[name] = a_[0] == b_[0] and a_[1]["images"] == b_[1]["images"] and a_[1]["files"] == b_[1]["files"]
    with p1.dev_env("intro_20"):
        o20 = p4.igm("neutral")
        a_ = rm.compile_insert_graph_node(o20, {"game": g3a.GAME})
        b_ = old.compile_insert_graph_node(o20, {"game": g3a.GAME})
        comp["intro_20_3"] = a_[0] == b_[0] and a_[1]["images"] == b_[1]["images"]
    # the whole plan text of the dual mod (without its timestamp) from both compilers
    texts = []
    for mod in (rm, old):
        saved = p1.rm
        p1.rm = mod
        try:
            _, t, pp = p1.compile_plan(f"o8_plan_{mod.__name__}", [("g5p5.dual", [p2.igm(13, "neutral"),
                                                                                p2.igm(22, "neutral")])])
            texts.append(strip(t, pp) if t else "")
        finally:
            p1.rm = saved
    comp["dual_plan_text"] = texts[0] == texts[1] and bool(texts[0])
    comp["tx_id_v1_unchanged"] = all(rm.tx_id(lv, "m", [("lvl", "a.lvl", 1, "0" * 64, 2, "1" * 64)])
                                     == old.tx_id(lv, "m", [("lvl", "a.lvl", 1, "0" * 64, 2, "1" * 64)])
                                     for lv in ("intro_10", "intro_20"))
    st = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "selftest"], cwd=ROOT, capture_output=True,
                        text=True, timeout=1800)
    comp["selftest"] = st.returncode == 0
    comp["selftest_summary"] = (st.stdout.strip().splitlines() or [""])[-1]
    prod = (TOOLS / "m33_mod_overlay.h").read_text(encoding="utf-8")
    comp["production_header_unchanged"] = subprocess.run(
        ["git", "diff", "--quiet", BASELINE, "--", "tools/m33_mod_overlay.h"], cwd=ROOT).returncode == 0 \
        and "level-tx" not in prod and 'kGrowNames[] = {"VS.sub"}' in prod
    det["O8"] = comp
    res["O8_compatibility"] = all(v for k, v in comp.items() if k != "selftest_summary")
    out = {"checks": res, "pass": all(res.values()), "details": det}
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "offline.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"checks": res, "O7": neg, "O8": comp}, indent=1, default=str))
    print("CHECK_G6P1", "PASS" if out["pass"] else "FAIL", f"{sum(res.values())}/{len(res)}")
    return 0 if out["pass"] else 1


# --- runtime transaction cases (no game) -----------------------------------------------------------------------

def negtest():
    data, ptr, tl = files()
    out = {}
    nd = WORK / "negtest"
    if nd.exists():
        shutil.rmtree(nd)
    nd.mkdir(parents=True)
    exes = {k: p1.build_test(k) for k in ("dev", "prod")}
    _, text, _ = p1.compile_plan("neg_lum", mods_for("on"))
    _, text_exit, _ = p1.compile_plan("neg_exit", mods_for("exit"))
    base = p1.parse_plan(text)
    im = p1.images(base)
    nl, np_, ntl, _ = g4b.construct(data, ptr, tl, "on")
    assert (im["intro_10.lvl"], im["intro_10.ptr"], im["transit.lvl"]) == (nl, np_, ntl)
    xl, xp, xt, _ = g4b.construct(data, ptr, tl, "exit")
    V = {}
    for k, b in (("lvl", nl), ("ptr", np_), ("transit", ntl), ("xlvl", xl), ("xptr", xp), ("xtransit", xt)):
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
        m["files"][i]["range"][ri] = " ".join([off, length, gb, f"{fnv(bytes(b)):016x}", mid, str(q)])

    def retx(m, i, k, v):
        t = m["files"][i]["tx"][0].split(" ")
        t[k] = v
        m["files"][i]["tx"][0] = " ".join(t)

    def reversion(m, v):
        t = m["txs"][0].split(" ")
        t[1] = v
        m["txs"][0] = " ".join(t)
        t[4] = canonical_id(m)   # a consistent id for the claimed version
        m["txs"][0] = " ".join(t)

    def drop_file(m, i):
        m["files"].pop(i)

    personal = {0x1C78, 0x1C7C, 0x539320}
    plans = {
        "valid": variant("valid"),
        "exit_valid": variant("exit_valid", src=p1.parse_plan(text_exit)),
        "missing_transit": variant("missing_transit", lambda m: drop_file(m, ti)),
        "missing_lvl": variant("missing_lvl", lambda m: drop_file(m, li)),
        "missing_ptr": variant("missing_ptr", lambda m: drop_file(m, pi)),
        "transit_not_member": variant("transit_not_member", lambda m: m["files"][ti].update(tx=[])),
        "transit_range_dropped": variant("transit_range_dropped", lambda m: m["files"][ti].update(range=[])),
        "tampered_transit": variant("tampered_transit", lambda m: tamper(m, ti, 0)),
        "tampered_ptr": variant("tampered_ptr", lambda m: tamper(m, pi, 0)),
        "wrong_transit_sha": variant("wrong_transit_sha", lambda m: retx(m, ti, 1, "0" * 64)),
        "transit_grown": variant("transit_grown", lambda m: (retx(m, ti, 2, str(TSIZE + 4)),
                                                             m["files"][ti].update(grow=[str(TSIZE + 4)]))),
        "version1_with_transit": variant("version1_with_transit", lambda m: reversion(m, "1")),
        "version3": variant("version3", lambda m: reversion(m, "3")),
        "partial_personal_words": variant("partial_personal_words", lambda m: m["files"][li].update(
            range=[r for r in m["files"][li]["range"] if int(r.split(" ")[0]) not in personal])),
        "corrupt_id": variant("corrupt_id", lambda m: m.update(
            txs=[m["txs"][0][:-1] + ("0" if m["txs"][0][-1] != "0" else "1")])),
        "two_tx": variant("two_tx", lambda m: m.update(txs=m["txs"] * 2)),
    }
    O = ("-", "-", "-")
    Vv = (V["lvl"], V["ptr"], V["transit"])
    Vx = (V["xlvl"], V["xptr"], V["xtransit"])
    paths = (str(g3a.LVL), str(g3a.PTR), str(g4b.TRANSIT))
    dev = [("lum valid, lvl,ptr,transit", "valid", LEVEL, "active", "lvl,ptr,transit", Vv),
           ("lum valid, transit,ptr,lvl", "valid", LEVEL, "active", "transit,ptr,lvl", Vv),
           ("lum valid, ptr,transit,lvl,transit", "valid", LEVEL, "active", "ptr,transit,lvl,transit", Vv),
           ("exit composition valid (lum + designer-default)", "exit_valid", LEVEL, "active", "transit,lvl,ptr", Vx),
           ("lum not enabled (transit first)", "valid", "-", "level_tx_not_enabled", "transit,lvl,ptr", O),
           ("lum not enabled (lvl first)", "valid", "-", "level_tx_not_enabled", "lvl,ptr,transit", O),
           ("lum enabled for another level", "valid", "intro_20", "tx_level", "transit,lvl,ptr", O),
           ("missing transit member", "missing_transit", LEVEL, "tx_incomplete", "transit,lvl,ptr", O),
           ("missing lvl member", "missing_lvl", LEVEL, "tx_incomplete", "transit,lvl,ptr", O),
           ("missing ptr member", "missing_ptr", LEVEL, "tx_incomplete", "lvl,transit,ptr", O),
           ("transit as a plain range (no tx-file)", "transit_not_member", LEVEL, "tx_incomplete", "transit,lvl,ptr", O),
           ("transit member without its range", "transit_range_dropped", LEVEL, "tx_incomplete", "transit,lvl,ptr", O),
           ("tampered transit range, rehashed", "tampered_transit", LEVEL, "tx_result_hash", "transit,lvl,ptr", O),
           ("tampered ptr, rehashed", "tampered_ptr", LEVEL, "tx_result_hash", "lvl,ptr,transit", O),
           ("wrong original transit hash", "wrong_transit_sha", LEVEL, "tx_identity", "transit,lvl,ptr", O),
           ("transit declared grown", "transit_grown", LEVEL, "tx_bounds", "transit,lvl,ptr", O),
           ("version 1 naming a transit member", "version1_with_transit", LEVEL, "tx_role", "lvl,ptr,transit", O),
           ("version 3", "version3", LEVEL, "tx_version", "lvl,ptr,transit", O),
           ("partial: personal-list words dropped", "partial_personal_words", LEVEL, "tx_result_hash",
            "lvl,ptr,transit", O),
           ("corrupted id", "corrupt_id", LEVEL, "tx_id", "transit,lvl,ptr", O),
           ("two transactions", "two_tx", LEVEL, "tx_count", "lvl,ptr,transit", O)]
    prod = [("production: lum transaction (lvl first)", "valid", LEVEL, "unknown_record", "lvl,ptr,transit", O),
            ("production: lum transaction (transit first)", "valid", LEVEL, "unknown_record", "transit,ptr,lvl", O)]
    for kind, cases in (("dev", dev), ("prod", prod)):
        cf = nd / f"cases_lum_{kind}.tsv"
        cf.write_text("".join("\t".join([n, str(plans[p]), env, want, order, paths[0], paths[1], str(e[0]), str(e[1]),
                                         paths[2], str(e[2])]) + "\n"
                              for n, p, env, want, order, e in cases), encoding="utf-8")
        r = subprocess.run([str(exes[kind]), str(cf)], capture_output=True, text=True, timeout=600)
        (nd / f"result_lum_{kind}.txt").write_text(r.stdout + r.stderr)
        print(r.stdout)
        out[kind] = {"exit": r.returncode, "cases": len(cases),
                     "summary": r.stdout.strip().splitlines()[-1] if r.stdout else ""}
    # G5-P5's negtest (G5-P2a's incl. G5-P1's, the dual plan, G5-P3's integrity) against the extended header
    import g5p5_pilot as p5
    p5.WORK = WORK / "o8_g5p5"
    out["g5p5_negtest_rc"] = p5.negtest()
    p1.WORK = WORK
    ok = out["g5p5_negtest_rc"] == 0 and all(out[k]["exit"] == 0 for k in ("dev", "prod"))
    out["pass"] = ok
    (nd / "summary.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(out, default=str), "NEGTEST_G6P1", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def g5p5_check():
    """G5-P5's offline check (43, with G5-P1 / G5-P2a / G5-P4a re-runs), redirected to e484/o8_g5p5."""
    import g5p5_pilot as p5
    p5.WORK = WORK / "o8_g5p5"
    p5.WORK.mkdir(parents=True, exist_ok=True)
    rc = p5.check()
    p1.WORK = WORK
    return rc


# --- hidden runs -------------------------------------------------------------------------------------------------

CASES = ("base", "on", "nogate", "exit")
LABEL = {"base": "A", "on": "B", "nogate": "C", "exit": "D"}


def bind():
    """Point G4b's runner at the compiler and the development transaction gate (constants used by run_case)."""
    g4b.PREFIX = PREFIX
    g4b.GATE_ENV = (ENV, LEVEL)
    g4b.write_plan = plan_for_run
    for k in ("R3HD_G3A_TEST_GROW", ENV, "R3HD_MODS_PLAN"):
        os.environ.pop(k, None)


def plan_for_run(work, data, ptr, tl, variant):
    res, text, paths = p1.compile_plan(f"run_{work.parent.name}_{work.name}", mods_for(variant))
    want = [MOD] + ([EXIT_MOD] if variant == "exit" else [])
    if text is None or res["active"] != want:
        raise SystemExit(f"compiler refused the run's mods: {res['mods']}")
    plan = paths["cache"] / rm.PLAN_NAME
    shutil.copyfile(plan, work / "plan_copy.txt")
    return plan, g4b.construct(data, ptr, tl, variant)[3]


def run(tag, cases):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    bind()
    for case in cases:
        row = g4b.run_case(tag, case)
        # D-250 (E-483 revision 1): the leftover-process criterion is ownership-based, 5 s after the runner ended
        run_ = f"{PREFIX}_{tag}_{case}"
        pj = g3a.RUNS / run_ / "process.json"
        pid = json.loads(pj.read_text(encoding="utf-8-sig")).get("pid") if pj.is_file() else None
        left, detail = g3a.game_left(pid, run_)
        (WORK / tag / case / "process_left.json").write_text(json.dumps({"left": left, **detail}) + "\n")
        print(json.dumps(dict(row, game_left=left)), flush=True)
    return 0


def judge(tag):
    data, ptr, tl = files()
    slots, _ = g4b.index(data, ptr)
    L = g4b.layout(data, slots)
    BLK, SRC = g4b.BLK, g4b.SRC
    out = {}
    for case in CASES:
        work = WORK / tag / case
        run_ = f"{PREFIX}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        for k in ("states", "reads", "samples"):
            row[k] = json.loads((work / f"{k}.json").read_text())
        log = "\n".join(q.read_text(errors="replace") for q in sorted((g3a.RUNS / run_).glob("runtime*.log")))
        row["log_lines"] = {
            "active": len(re.findall(r"^.*M33 mods state=active", log, re.M)),
            "refused": re.findall(r"state=refused reason=([A-Za-z_]+)", log),
            "g5p1": re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log),
            "g6p1": re.findall(r"G6P1 level-tx version=(\d+) members=(\S+)", log),
            "snap": re.findall(r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", log),
            "host_changed": len(re.findall(r"G5P3 tx host_changed", log)),
            "any_dev": len(re.findall(r"G5P1|G5P3|G6P1", log)),
            "error": re.findall(r"(?:engine error|unhandled exception|guest fault|crash)[^\n]{0,120}", log, re.I)[:5]}
        row["grow_size"] = sorted(set(re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)))
        row["served_files"] = sorted(set(re.findall(r"M33 mods served mod=\S+ file=(\S+)", log)))
        row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
        row["lvl_opens"] = [o.rsplit("\\", 1)[-1].lower() for o in
                            re.findall(r"vfs_open path=(\S+?\.lvl) result=00000000", log)]
        pc = work / "plan_copy.txt"
        row["plan_tx"] = plan_tx(pc.read_text(encoding="utf-8"))[1] if pc.is_file() else []
        rj = g3a.RUNS / run_ / "run.json"
        row["run_json"] = json.loads(rj.read_text(encoding="utf-8-sig")) if rj.is_file() else {}
        pl = work / "process_left.json"
        row["game_left"] = json.loads(pl.read_text()) if pl.is_file() else {"left": True, "missing": True}
        mf = g3a.RUNS / run_ / "m2_faults.log"
        row["fault_codes"] = sorted(set(re.findall(r"M2 exception code=([0-9A-Fa-f]+)",
                                                   mf.read_text(errors="replace")))) if mf.is_file() else []
        judges = {}
        for tool in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
            r = subprocess.run([sys.executable, str(TOOLS / tool), "--run", run_], cwd=ROOT, capture_output=True,
                               text=True)
            judges[tool] = r.returncode
            (work / f"{tool}.log").write_text(r.stdout + r.stderr)
        row["judges"] = judges
        out[case] = row
    A, B, C, D = (out[c] for c in CASES)
    invalid = [c for c, r in out.items() if r.get("error") or not r["samples"]
               or (c != "exit" and r["samples"][-1]["t"] - r["samples"][0]["t"] < 60)]
    info = g4b.construct(data, ptr, tl, "on")[3]

    def ab(r):
        return int(r["area"]["base"], 16) if r.get("area") else 0
    P = {}
    # P1 resource identity
    want_grow = {("intro_10.lvl", str(SIZE), str(SIZE + N)), ("intro_10.ptr", str(PSIZE), str(PSIZE + 8 * K))}
    p1_ = {}
    for c in ("on", "exit"):
        r, ll = out[c], out[c]["log_lines"]
        tx = r["plan_tx"][0] if r["plan_tx"] else None
        snap = sorted((f, b) for f, _, b, _ in ll["snap"])
        gs = set(r["grow_size"])
        p1_[c] = (ll["active"] == 1 and tx is not None and ll["g5p1"] == [(tx[2], tx[3], tx[4])] and tx[1] == "2"
                  and ll["g6p1"] == [("2", "lvl,ptr,transit")]
                  and snap == [("intro_10.lvl", str(SIZE + N)), ("intro_10.ptr", str(PSIZE + 8 * K)),
                               ("transit.lvl", str(TSIZE))]
                  and ll["snap"][-1][3] == "3" and want_grow <= gs
                  and gs - want_grow <= {("transit.lvl", str(TSIZE), str(TSIZE))}
                  and r["served_files"] == ["intro_10.lvl", "intro_10.ptr", "transit.lvl"] and not ll["host_changed"])
    shas = {c: r.get("original_readback_sha256") for c, r in out.items()}
    P["P1_resource_identity"] = all(p1_.values()) and shas["base"] is not None and len(set(shas.values())) == 1

    def union(lst):
        d, i = lst.get("dw", {}), lst.get("inactive", {})
        both = d.get("walk", []) + i.get("walk", [])
        return set(both), len(both) == len(set(both)) and bool(d.get("prev_ok")) and bool(i.get("prev_ok")), \
            set(d.get("walk", []))

    def lists(r, k):
        return ((r.get(k) or {}).get("lists")) or {}
    a_u = union(lists(A, "live_first"))[0]
    reg = {}
    for c in CASES:
        r, b = out[c], ab(out[c])
        copy_so = b + L["fc"] - 4
        lst = lists(r, "live_first")
        U, nodup, dws = union(lst)
        rec, per = lst.get("rec", {}), lst.get("personal", {})
        if c in ("on", "exit"):
            ok = (bool(b) and nodup and U == a_u | {copy_so} and copy_so not in a_u and copy_so in dws
                  and rec.get("count") == rec.get("n") == 123 and rec.get("last_so") == copy_so
                  and (copy_so + 0xC4) in lst.get("bak_targets", []) and per.get("count") == 70
                  and per.get("last_name") == NEW_NAME)
        else:
            ok = bool(b) and nodup and U == a_u and rec.get("count") == rec.get("n") == 122 and per.get("count") == 69
        reg[c] = ok
    P["P2_actor_registration"] = reg["on"] and reg["exit"]
    # P3 independent state
    ind = {}
    for c in ("on", "exit"):
        r, b = out[c], ab(out[c])
        bl = (r.get("live_first") or {}).get("blocks") or {}
        sl, cl = bytes.fromhex(bl.get("src", "")), bytes.fromhex(bl.get("copy", ""))
        ok_len = len(sl) == BLK and len(cl) == BLK
        src_lo, copy_lo = b + SRC - 4, b + L["fc"] - 4
        w = lambda x, k: struct.unpack_from(">I", x, k)[0]   # noqa: E731
        copy_into_src = [k for k in range(0, BLK, 4) if ok_len and src_lo <= w(cl, k) < src_lo + BLK and k != 0x18]
        src_into_copy = [k for k in range(0, BLK, 4) if ok_len and copy_lo <= w(sl, k) < copy_lo + BLK and k != 0x14]
        s = r["samples"]
        ch = [i for i in range(1, len(s)) if s[i]["v5"] != s[i - 1]["v5"]]
        pickup = []
        if ch:
            ti = s[ch[0]]["t"]
            before = [x for x in r["reads"] if x["t"] <= ti and x.get("copy")]
            after = [x for x in r["reads"] if x["t"] > ti and x.get("copy")]
            if before and after:
                cb, ca = bytes.fromhex(before[-1]["copy"]), bytes.fromhex(after[0]["copy"])
                sb_, sa_ = bytes.fromhex(before[-1]["src"]), bytes.fromhex(after[0]["src"])
                pickup = sorted({k for k in range(0, BLK, 4) if cb[k:k + 4] != ca[k:k + 4]}
                                - {k for k in range(0, BLK, 4) if sb_[k:k + 4] != sa_[k:k + 4]})
        sstd = info["src_std"] - SRC
        ind[c] = {"copy_3d_buf": f"{w(cl, 0x14C):08x}" if ok_len else None,
                  "src_3d_buf": f"{w(sl, 0x14C):08x}" if ok_len else None,
                  "brain4": [w(x, 0x31C) for x in (sl, cl)] if ok_len else None,
                  "copy_into_src": copy_into_src, "src_into_copy": src_into_copy, "pickup_specific": pickup,
                  "src_translation_kept": ok_len and sl[0xC4 + 0x34:0xC4 + 0x40] == data[SRC + 0xC4 + 0x34:SRC + 0xC4 + 0x40],
                  "src_index_kept": ok_len and sl[sstd + 8:sstd + 12] == data[SRC + sstd + 8:SRC + sstd + 12]}
        ind[c]["ok"] = (ok_len and ind[c]["copy_3d_buf"] not in ("00000000", ind[c]["src_3d_buf"])
                        and ind[c]["brain4"] == [0xCDCDCDCD, 0xCDCDCDCD] and not copy_into_src and not src_into_copy
                        and bool(pickup) and ind[c]["src_translation_kept"] and ind[c]["src_index_kept"])
    P["P3_independent_state"] = all(v["ok"] for v in ind.values())
    # P4 collection
    pos = info["pos"]
    coll = {}
    for c, r in out.items():
        s = r["samples"]
        ch = [i for i in range(1, len(s)) if s[i]["v5"] != s[i - 1]["v5"]]
        changes = [(s[i]["t"], s[i - 1]["v5"], s[i]["v5"]) for i in ch]
        near = None
        if changes:
            d = [math.dist(x["pos"], pos) for x in s if abs(x["t"] - changes[0][0]) <= 2.0]
            near = round(min(d), 3) if d else None
        coll[c] = {"v5_first": s[0]["v5"] if s else None, "v5_last": s[-1]["v5"] if s else None, "changes": changes,
                   "near_change": near, "level_change_t": r.get("level_change_t"), "lvl_opens": r["lvl_opens"]}
    on, ex = coll["on"], coll["exit"]
    P["P4_collection"] = (all(coll[c]["v5_first"] == 0 and not coll[c]["changes"] for c in ("base", "nogate"))
                          and on["v5_first"] == 0 and [x[1:] for x in on["changes"]] == [(0, 1)]
                          and on["near_change"] is not None and on["near_change"] <= 3.0
                          and ex["v5_first"] == 5 and bool(ex["changes"]) and ex["changes"][0][1:] == (5, 6)
                          and ex["near_change"] is not None and ex["near_change"] <= 3.0)
    # P5 registry after collection (B's end read)
    b = ab(B)
    copy_so = b + L["fc"] - 4
    le = lists(B, "live_end")
    U, nodup, _ = union(le)
    rec, per = le.get("rec", {}), le.get("personal", {})
    p5 = {"union": len(U), "rec": rec.get("count"), "personal": per.get("count"), "backups": len(le.get("bak_targets", [])),
          "after_collection": bool(on["changes"]) and bool(B["reads"]) and B["reads"][-1]["t"] > on["changes"][0][0]}
    P["P5_registry_after_collection"] = (bool(le) and nodup and U == a_u | {copy_so} and rec.get("count") == rec.get("n")
                                         == 123 and rec.get("last_so") == copy_so and per.get("count") == 70
                                         and (copy_so + 0xC4) in le.get("bak_targets", []) and p5["after_collection"])
    # P6 transition and cleanup
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
                    "after_change": [(s["areas"]["1"]["base"], s["free_bytes"]) for s in fa][-1:]}
    P["P6_transition_cleanup"] = (all(alloc[c]["valid"] and alloc[c]["length"] == AREA + (N if c in ("on", "exit") else 0)
                                      for c in CASES)
                                  and alloc["base"]["free_after"] == FREE0 and alloc["nogate"]["free_after"] == FREE0
                                  and alloc["on"]["free_after"] == FREE0 - N
                                  and "intro_15.lvl" in ex["lvl_opens"] and (ex["level_change_t"] or 1e9) <= 130
                                  and alloc["exit"]["after_change"] == [("0x40f5f320", 12234744)])
    # P7 negative control
    llc = C["log_lines"]
    P["P7_negative_control"] = (llc["refused"] == ["level_tx_not_enabled"] and not C["grow_size"]
                                and not C["served_files"] and llc["any_dev"] == 0 and reg["nogate"]
                                and coll["nogate"]["v5_first"] == 0 and not coll["nogate"]["changes"])
    # P8 safety
    fg = {c: (r["run_json"].get("game_foreground_events"), r["run_json"].get("game_foreground_samples"))
          for c, r in out.items()}
    P["P8_safety"] = all(r["haptics_policy"] and not any(r["judges"].values()) and r["runner_exit"] == 0
                         and r["game_left"].get("left") is False and fg[c] == (0, 0) and not r["log_lines"]["error"]
                         and set(r["fault_codes"]) <= {"406D1388"}
                         for c, r in out.items()) and (WORK / "offline.json").is_file() \
        and json.loads((WORK / "offline.json").read_text()).get("pass") is True \
        and json.loads((WORK / "negtest" / "summary.json").read_text()).get("pass") is True
    result = {"invalid": invalid, "P": P, "pass": not invalid and all(P.values()), "resource": p1_, "readback": shas,
              "registration": reg, "independent": ind, "collection": coll, "after_collection": p5, "alloc": alloc,
              "foreground": fg, "judges": {c: r["judges"] for c, r in out.items()},
              "fault_codes": {c: r["fault_codes"] for c, r in out.items()},
              "log_lines": {c: r["log_lines"] for c, r in out.items()},
              "grow_size": {c: r["grow_size"] for c, r in out.items()},
              "served": {c: r["served_files"] for c, r in out.items()},
              "runner_exit": {c: r["runner_exit"] for c, r in out.items()},
              "process_left_pid_only": {c: r["process_left"] for c, r in out.items()},
              "game_left": {c: r["game_left"] for c, r in out.items()}}
    (WORK / tag / "judgement.json").write_text(json.dumps(result, indent=1, default=str) + "\n")
    print(json.dumps({k: result[k] for k in ("invalid", "P", "pass", "independent", "collection", "after_collection",
                                             "alloc", "foreground")}, indent=1, default=str))
    return 0 if result["pass"] else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        return check()
    if len(sys.argv) > 1 and sys.argv[1] == "negtest":
        return negtest()
    if len(sys.argv) > 1 and sys.argv[1] == "g5p5check":
        return g5p5_check()
    if len(sys.argv) > 2 and sys.argv[1] == "judge":
        return judge(sys.argv[2])
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--cases", default=",".join(CASES))
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9-]{1,24}", a.tag):
        ap.error("bad tag")
    WORK.mkdir(parents=True, exist_ok=True)
    return run(a.tag, a.cases.split(","))


if __name__ == "__main__":
    sys.exit(main())
