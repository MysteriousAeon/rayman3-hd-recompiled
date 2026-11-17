#!/usr/bin/env python3
"""E-493 (D-260) G6-P7: targeted model / behaviour decoding and fifth-actor readiness. Offline; private; no game run.

  g6p7_fifth_actor.py calibrate    D1-D8 basis: the four verified actors with census rules revision 1 (G6-P6) and 2
                                   (G6-P7) against the compiler's captured class maps (g6p6_census_check.oracle)
  g6p7_fifth_actor.py dossier      the selected candidate's (intro_10 NIN_m_ToadIntro instance 1) ownership dossier:
                                   the census proposals AND an independent verification of each class from the files
  g6p7_fifth_actor.py prototype    the private offline constructor (G6-P5 primitives through build_passive_lum with a
                                   private Toad spec; no manifest operation, no plan, nothing served) and an
                                   independent simulator of its output
  g6p7_fifth_actor.py tests        D4 / D5 / D7 and the regressions (G6-P6 tests, G6-P5 compare, selftest, gate)
Outputs: private/work/e493/.
"""
import hashlib
import json
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
import actor_pointer_census as apc  # noqa: E402
import g6p6_census_check as chk  # noqa: E402

WORK = ROOT / "private" / "work" / "e493"
GAME = chk.GAME
LEVEL = "intro_10"
TOAD = "NIN_m_ToadIntro"
SOURCE_INSTANCE = 1
NEW_NAME = b"XAP_ToadIntro_G6P7"


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


# --- calibration before / after --------------------------------------------------------------------------------------

def calibrate():
    WORK.mkdir(parents=True, exist_ok=True)
    out, ok = {}, True
    for case, (op, level, model, inst) in chk.CASES.items():
        orc, blk = chk.oracle(op)
        r1 = apc.census(GAME, level, model, inst, revision=1)
        r2 = apc.census(GAME, level, model, inst, revision=2)
        j1, j2 = chk.judge(r1["rows"], orc), chk.judge(r2["rows"], orc)
        p1 = {r["offset"]: r for r in r1["rows"]}
        newly = []
        for r in r2["rows"]:
            a = p1[r["offset"]]["proposal"]
            if a != r["proposal"]:
                rules = sorted({e["rule"] for v in r["candidates"].values() for e in v})
                newly.append({"field": f"+{r['field']:#x}", "before": a, "after": r["proposal"],
                              "oracle": orc.get(r["offset"]), "rules": rules,
                              "evidence": [e["evidence"] for v in r["candidates"].values() for e in v]})
        d2_bad = [n for n in newly if n["before"] in ("UNKNOWN", "CONFLICTING") and n["after"] in apc.CLASSES
                  and not set(n["rules"]) & {"R-model-object", "R-peer-layout"}]
        regress = [n for n in newly if n["before"] in apc.CLASSES]
        res = {"total": r2["total"], "before": r1["counts"], "after": r2["counts"],
               "coverage": [r1["coverage"], r2["coverage"]],
               "agree": [len(j1["agree"]), len(j2["agree"])], "unknown": [len(j1["unknown"]), len(j2["unknown"])],
               "incorrect": [j1["incorrect"], j2["incorrect"]],
               "left_out_unsafe": [j1["left_out_unsafe"], j2["left_out_unsafe"]],
               "conflicting": [len(j1["conflicting"]), len(j2["conflicting"])],
               "left_out": {k: len(j2[k]) for k in ("left_out_keep", "left_out_unsafe", "left_out_unknown")},
               "newly_resolved": newly, "unexplained_promotions": d2_bad, "changed_confident": regress,
               "enumeration": sorted(r["offset"] for r in r2["rows"]) == sorted(orc)
               and [r["offset"] for r in r1["rows"]] == [r["offset"] for r in r2["rows"]],
               "remaining_unknown": [f"+{t['field']:#x}:{t['oracle']}" for t in j2["unknown"]]}
        out[case] = res
        ok &= not j2["incorrect"] and not j2["left_out_unsafe"] and not j2["conflicting"] and not d2_bad \
            and not regress and res["enumeration"]
    r = {"pass": ok, "cases": out}
    (WORK / "calibration_before_after.json").write_text(json.dumps(r, indent=1) + "\n")
    for case, v in out.items():
        print(case, "agree", v["agree"], "unknown", v["unknown"], "incorrect", [len(x) for x in v["incorrect"]],
              "unsafe", [len(x) for x in v["left_out_unsafe"]], "conflicting", v["conflicting"], "new",
              len(v["newly_resolved"]), "enum", v["enumeration"])
    print("CALIBRATION_G6P7", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# --- the fifth-actor candidate ---------------------------------------------------------------------------------------

def toad_inputs():
    L = apc.load_level(GAME, LEVEL)
    ix = rm.read_script_index(GAME, LEVEL)
    key = apc.resolve_model(ix, TOAD)
    insts = ix["placements"][key]
    return L, ix, key, insts


def toad_spec(key, insts, lvl):
    """A PRIVATE spec for the lum recipe (G6-P1's verified source checks and construction), Toad facts only. Not an
    allow-list entry: nothing in r3hd_mods knows it."""
    so = insts[SOURCE_INSTANCE]["so"]
    spec = dict(rm.LUM_ALLOW[LEVEL])
    spec.update(model=key, instance=SOURCE_INSTANCE, so=so, new_name=NEW_NAME,
                anchors={"at_source": ("source", (0.0, 0.0, 0.0))}, radius=0.0)
    return spec


def independent_check(L, ix, key, insts):
    """Verification line 2 (does not use the census): G6-P1's verified lum source preconditions (rm._lum_source) on
    the Toad, plus explicit file facts. Returns (source dict, facts) or raises."""
    lvl, ptr, tl, me = L["data"]["lvl"], L["data"]["ptr"], L["data"]["transit"], L["me"]
    spec = toad_spec(key, insts, lvl)
    peers = [i["so"] for n, i in enumerate(insts) if n != SOURCE_INSTANCE]
    s = rm._lum_source(lvl, ptr, tl, me, spec, peers, "g6p7 toad")
    slots, cross, target, tail = rm.actor_tables(lvl, ptr, tl, me, lambda w: (_ for _ in ()).throw(ValueError(w)))
    SO, BLK = spec["so"], spec["block"]
    R = rm.FROG_ALLOW[LEVEL]["resolve"]
    st, cnt = target(R["ref"]), sum(u32(lvl, g) for g in R["groups"])
    resolve_in_block = [u32(lvl, st + 4 * i) + 4 for i in range(cnt) if SO <= u32(lvl, st + 4 * i) + 4 < SO + BLK]
    al = rm.actor_walk(target(rm.FROG_ALLOW[LEVEL]["always"]), target, 4096)
    perso = target(SO + 4)
    brain = target(perso + 0xC)
    mind = target(brain)
    intel = target(mind + 4)
    facts = {
        "superobject": SO, "block": BLK, "census": [len(s["inner"]), len(s["ext"]), 1],
        "instances": [i["so"] for i in insts], "instance_blocks_identical_to_source": [
            p for p in peers if p != insts[0]["so"]],
        "personal_index": s["index"], "personal_name": s["names"][s["index"]].decode(),
        "personal_count": s["pcount"], "new_name_unique_in_family": NEW_NAME not in s["names"],
        "so_record": s["srec"], "backup_record": s["sb"], "backup_copy": s["scopy"],
        "always_active": [hex(target(e + 0xC)) for e in al if target(e + 0xC) == SO],
        "siblings": [s["prev"], s["next"]], "world_count": s["world_count"],
        "chain": {"perso": perso - SO, "3dData": target(perso) - SO, "stdgame": target(perso + 4) - SO,
                  "brain": brain - SO, "mind": mind - SO, "intelligence": intel - SO, "ai_model": target(mind),
                  "ai_model_in": "instance 0's block" if insts[0]["so"] <= target(mind) < SO else "elsewhere",
                  "dsgmem": target(mind + 0xC)},
        "designer_variables": ix["defaults"].get(key), "sets_position": rm.model_sets_position(ix, key),
        "resolve_entries_in_block": resolve_in_block,
        "cross_file_refs_into_block": [c for c in cross if (c[3] == me and SO <= c[2] + 4 < SO + BLK)
                                       or (c[1] == me and SO <= c[0] + 4 < SO + BLK)],
        "other_file_words": [o - SO for o in range(SO, SO + BLK, 4) if o in slots and slots[o] != me],
        "translations_equal": len({lvl[SO + t:SO + t + 12] for t in spec["translations"]}) == 1,
    }
    return s, facts, spec, peers


def dossier():
    WORK.mkdir(parents=True, exist_ok=True)
    L, ix, key, insts = toad_inputs()
    c = apc.census(GAME, LEVEL, key, SOURCE_INSTANCE)
    s, facts, spec, peers = independent_check(L, ix, key, insts)
    SO = spec["so"]
    line2 = {}
    for o in s["inner"]:
        line2[o] = "owned"
    for o in s["ext"]:
        line2[o] = "sibling link" if o in (SO + 0x14, SO + 0x18) else "shared"
    line2[SO + 0x1C] = "other-file"
    rows, agree = [], True
    for r in c["rows"]:
        two = line2.get(r["offset"])
        status = ("supported provisional" if r["proposal"] == two and r["proposal"] in apc.CLASSES
                  else "CONFLICTING" if r["proposal"] in apc.CLASSES and two and r["proposal"] != two
                  else "UNKNOWN")
        agree &= status == "supported provisional"
        rows.append({"field": r["field"], "census": r["proposal"], "census_rules": sorted(
            {e["rule"] for v in r["candidates"].values() for e in v}), "lum_recipe": two, "status": status,
            "target": r["target"], "target_resource": r["target_resource"]})
    growth = {"lvl": None, "ptr": None}
    out = {"candidate": {"level": LEVEL, "model": key, "instance": SOURCE_INSTANCE},
           "resources": c["resources"], "facts": facts, "rows": rows, "all_supported": agree,
           "census_counts": c["counts"], "verified_runtime": False,
           "status_note": "no class is runtime-verified for this model; 'supported provisional' = the census "
                          "(rules revision 2) and G6-P1's verified lum source preconditions agree independently",
           "growth": growth}
    (WORK / "toad_dossier.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print("rows", len(rows), "supported provisional", sum(r["status"] == "supported provisional" for r in rows),
          "UNKNOWN", sum(r["status"] == "UNKNOWN" for r in rows), "CONFLICTING",
          sum(r["status"] == "CONFLICTING" for r in rows))
    print(json.dumps({k: v for k, v in facts.items() if k not in ("designer_variables",)}, default=str))
    print("DOSSIER_G6P7", "COMPLETE" if agree else "INCOMPLETE")
    return 0 if agree else 1


# --- the private offline prototype and its independent simulator ----------------------------------------------------

def prototype():
    WORK.mkdir(parents=True, exist_ok=True)
    L, ix, key, insts = toad_inputs()
    lvl, ptr, tl, me = L["data"]["lvl"], L["data"]["ptr"], L["data"]["transit"], L["me"]
    s, facts, spec, peers = independent_check(L, ix, key, insts)
    SO = spec["so"]
    pos = struct.unpack(">3f", lvl[SO + spec["translations"][0]:SO + spec["translations"][0] + 12])   # at_source
    nl, np_, nt, edits, info = rm.build_passive_lum(lvl, ptr, tl, me, spec, peers, pos, "g6p7 toad prototype")
    budget = rm.structural_budget(LEVEL, len(lvl), len(nl), len(np_), u32(lvl, 0), "g6p7 toad prototype")
    grow = {"lvl": len(nl) - len(lvl), "ptr": len(np_) - len(ptr)}
    within = all(0 < grow[k] <= rm.STRUCT_MAX_GROW[k] for k in grow)
    sim = simulate(lvl, ptr, tl, nl, np_, nt, me, SO, spec["block"], insts, s)
    h = {"lvl": hashlib.sha256(nl).hexdigest(), "ptr": hashlib.sha256(np_).hexdigest(),
         "transit": hashlib.sha256(nt).hexdigest()}
    again = rm.build_passive_lum(lvl, ptr, tl, me, spec, peers, pos, "g6p7 toad prototype")
    det = [hashlib.sha256(b).hexdigest() for b in again[:3]] == [h["lvl"], h["ptr"], h["transit"]]
    for name, b in (("lvl", nl), ("ptr", np_), ("transit", nt)):
        (WORK / f"toad_prototype.{name}.bin").write_bytes(b)   # private only (derived from game data)
    out = {"pass": sim["pass"] and within and det and info["objects"]["copy"] == sim["copy"], "growth": grow,
           "within_bounds": within, "budget": budget, "edits": [lbl for _, lbl in edits], "slots": info["slots"],
           "objects": info["objects"], "hashes": h, "deterministic": det, "simulator": sim,
           "position": list(pos), "personal_index": info["personal_index"], "actors": info["actors"]}
    (WORK / "toad_prototype.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k not in ("simulator", "objects")}, indent=1, default=str))
    print("simulator:", {k: v for k, v in sim.items() if k != "details"})
    print("PROTOTYPE_G6P7", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


def simulate(lvl, ptr, tl, nl, np_, nt, me, SO, BLK, insts, s):
    """Independent of the compiler's verifier: re-reads the new files as the loader would (own-file slots resolved,
    the new .ptr entries parsed afresh) and checks the hierarchy and every copied word by its class, derived here
    from the ORIGINAL files only (in-block target -> owned; outside -> same target; +0x14 / +0x18 links; other-file
    kept)."""
    d = {}
    n0, n = u32(ptr, 0), u32(np_, 0)
    m = u32(lvl, 0)
    ent = lambda b, i: struct.unpack_from(">iI", b, 4 + 8 * i)   # noqa: E731
    d["ptr_layout"] = 4 + 8 * n + 16 * m == len(np_) and np_[4:4 + 8 * n0] == ptr[4:4 + 8 * n0] \
        and np_[4 + 8 * n:] == ptr[4 + 8 * n0:]
    old = {loc + 4: f for f, loc in (ent(ptr, i) for i in range(n0))}
    new = {loc + 4: f for f, loc in (ent(np_, i) for i in range(n))}
    tgt = lambda b, sl, o: u32(b, o) + 4 if sl.get(o) == me else None   # noqa: E731
    size = len(lvl)
    C = size + (SO % 16 - size % 16) % 16
    d["copy_phase"] = C % 16 == SO % 16 and nl[size:C] == bytes(C - size)
    words = {}
    for k in range(0, BLK, 4):
        so_, co = SO + k, C + k
        if so_ not in old:
            words[k] = (co not in new and (nl[co:co + 4] == lvl[so_:so_ + 4] or k in (0x2BC,)
                                           or any(t <= k < t + 12 for t in (0xF8, 0x294, 0x498))), "data")
            continue
        f = old[so_]
        if f != me:
            words[k] = (new.get(co) == f and nl[co:co + 4] == lvl[so_:so_ + 4], "other-file")
            continue
        t = tgt(lvl, old, so_)
        if k == 0x14:
            words[k] = (tgt(nl, new, co) == tgt(lvl, old, SO + 0x14), "link next")
        elif k == 0x18:
            words[k] = (tgt(nl, new, co) == SO, "link previous")
        elif SO <= t < SO + BLK:
            words[k] = (tgt(nl, new, co) == C + (t - SO), "owned")
        else:
            words[k] = (tgt(nl, new, co) == t, "shared")
    bad = {hex(k): v[1] for k, v in words.items() if not v[0]}
    d["copied_words"] = not bad
    d["copy_kinds"] = {kind: sum(1 for ok, kk in words.values() if kk == kind) for kind in
                       ("owned", "shared", "other-file", "link next", "link previous")}
    # the model the copy runs: its Mind+0 and Intelligence+0 name the AI model in instance 0's block
    mind = tgt(nl, new, tgt(nl, new, tgt(nl, new, C + 4) + 0xC))
    intel = tgt(nl, new, mind + 4)
    src_mind = tgt(lvl, old, tgt(lvl, old, tgt(lvl, old, SO + 4) + 0xC))
    d["model_shared"] = tgt(nl, new, mind) == tgt(lvl, old, src_mind) \
        and insts[0]["so"] <= tgt(nl, new, mind) < insts[1]["so"] and tgt(nl, new, intel) == tgt(nl, new, mind) \
        and C <= mind < C + BLK and C <= intel < C + BLK
    d["no_pointer_into_source"] = [k for k in range(0, BLK, 4) if C + k in new and tgt(nl, new, C + k) is not None
                                   and SO <= tgt(nl, new, C + k) < SO + BLK and k != 0x18] == []
    # lists: world chain (the copy right after the source), SO records, backups, personal types, transit count
    W = 0x9B4
    nxt = tgt(lvl, old, SO + 0x14)
    d["world"] = tgt(nl, new, SO + 0x14) == C and tgt(nl, new, nxt + 0x18) == C and u32(nt, W + 0x10) == \
        u32(tl, W + 0x10) + 1 and [o for o in range(0, len(tl), 4) if tl[o:o + 4] != nt[o:o + 4]] == [W + 0x10]

    def walk(b, sl, start):
        out, x = [], start
        while x is not None and x not in out and len(out) < 70000:
            out.append(x)
            x = tgt(b, sl, x)
        return out
    rh = tgt(nl, new, 0x1CFC)
    recs = walk(nl, new, tgt(nl, new, rh))
    owners = [tgt(nl, new, r + 4) for r in recs]
    d["records"] = owners.count(C) == 1 and owners[-1] == C and u32(nl, rh + 8) == len(recs) \
        and len(recs) == len(walk(lvl, old, tgt(lvl, old, rh))) + 1
    bl = walk(nl, new, tgt(nl, new, 0x1CEC))
    last = bl[-1] - 4
    bcopy = tgt(nl, new, last + 0xC)
    d["backup"] = tgt(nl, new, last + 8) == C + 0xC4 and bcopy is not None and b"".join(
        nl[bcopy + q:bcopy + q + 4][::-1] for q in range(0, 0x54, 4)) == nl[C + 0xC4:C + 0xC4 + 0x54] \
        and len(bl) == len(walk(lvl, old, tgt(lvl, old, 0x1CEC))) + 1
    pl = walk(nl, new, tgt(nl, new, 0x1C74))
    std = tgt(nl, new, tgt(nl, new, C + 4) + 4)
    nm = tgt(nl, new, pl[-1] + 0xC)
    names = [nl[tgt(nl, new, e + 0xC):tgt(nl, new, e + 0xC) + 0x40].split(b"\0")[0] for e in pl]
    d["personal"] = u32(nl, std + 8) == len(pl) - 1 and nl[nm:nm + 0x40].split(b"\0")[0] == NEW_NAME \
        and names.count(NEW_NAME) == 1 and u32(nl, 0x1C74 + 8) == len(pl)
    changed = [o for o in range(0, size, 4) if nl[o:o + 4] != lvl[o:o + 4]]
    d["original_words_changed"] = len(changed)
    d["resolve_table_untouched"] = all(nl[o:o + 4] == lvl[o:o + 4] for o in (0x1CE0, 0x1CE4, 0x1CE8))
    ok = all(v for k, v in d.items() if isinstance(v, bool)) and d["original_words_changed"] == 10
    return {"pass": ok, "copy": C, "bad_words": bad, **d}


def resource_hashes():
    out = {}
    for lv in ("intro_10", "intro_20"):
        lvl, ptr, _ = rm.script_level_files(GAME, lv)
        for q in (lvl, ptr, lvl.with_name("transit.lvl")):
            out[f"{lv}/{q.name}"] = (hashlib.sha256(q.read_bytes()).hexdigest(), q.stat().st_mtime_ns)
    fx = GAME / "GAMEDATAbin" / "fix.lvl"
    out["fix.lvl"] = (hashlib.sha256(fx.read_bytes()).hexdigest(), fx.stat().st_mtime_ns)
    return out


def tests():
    WORK.mkdir(parents=True, exist_ok=True)
    D, det = {}, {}
    before = resource_hashes()
    q = subprocess.run([sys.executable, str(Path(__file__)), "calibrate"], capture_output=True, text=True)
    cal = json.loads((WORK / "calibration_before_after.json").read_text())
    D["D1_no_confident_regression"] = q.returncode == 0 and all(
        not v["incorrect"][1] and not v["left_out_unsafe"][1] for v in cal["cases"].values())
    D["D2_no_unsafe_promotion"] = all(not v["unexplained_promotions"] and not v["changed_confident"]
                                      for v in cal["cases"].values())
    D["D3_explicit_evidence"] = all(n["rules"] and n["evidence"] for v in cal["cases"].values()
                                    for n in v["newly_resolved"])
    runs = []
    for _ in range(2):
        r = subprocess.run([sys.executable, str(TOOLS / "actor_pointer_census.py"), "--level", LEVEL, "--model", TOAD,
                            "--instance", str(SOURCE_INSTANCE), "--json", "-"], capture_output=True, text=True)
        runs.append(r.stdout)
    D["D4_deterministic"] = runs[0] == runs[1] and json.loads(runs[0])["total"] == 31
    D["D5_enumeration"] = all(v["enumeration"] for v in cal["cases"].values())
    g6 = subprocess.run([sys.executable, str(HERE / "g6p6_census_check.py"), "tests"], capture_output=True, text=True)
    D["D6_compiler_isolation"] = g6.returncode == 0   # includes G6-P5's frozen compare, gate, the compiler diff
    det["g6p6_tests"] = g6.stdout.strip().splitlines()[-13:]
    # the prototype's simulator rejects a misclassified word (an owned word left pointing into the source)
    L, ix, key, insts = toad_inputs()
    lvl, ptr, tl, me = L["data"]["lvl"], L["data"]["ptr"], L["data"]["transit"], L["me"]
    s, facts, spec, peers = independent_check(L, ix, key, insts)
    SO = spec["so"]
    pos = struct.unpack(">3f", lvl[SO + 0xF8:SO + 0x104])
    nl, np_, nt, _, _ = rm.build_passive_lum(lvl, ptr, tl, me, spec, peers, pos, "g6p7 neg")
    C = len(lvl) + (SO % 16 - len(lvl) % 16) % 16
    bad = bytearray(nl)
    struct.pack_into(">I", bad, C + 0x348, u32(lvl, SO + 0x348))   # Intelligence+0x10 as if shared
    sim_bad = simulate(lvl, ptr, tl, bytes(bad), np_, nt, me, SO, spec["block"], insts, s)
    bad2 = bytearray(nl)
    struct.pack_into(">I", bad2, C + 0x340, u32(lvl, SO + 0x340) - SO + C)   # a behaviour pointer "rebased"
    sim_bad2 = simulate(lvl, ptr, tl, bytes(bad2), np_, nt, me, SO, spec["block"], insts, s)
    D["simulator_rejects_misclassification"] = not sim_bad["pass"] and "0x348" in sim_bad["bad_words"] \
        and not sim_bad2["pass"] and "0x340" in sim_bad2["bad_words"]
    after = resource_hashes()
    D["D7_resource_integrity"] = before == after
    D["D8_before_after_recorded"] = all("newly_resolved" in v and "remaining_unknown" in v
                                        for v in cal["cases"].values())
    st = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "selftest"], capture_output=True, text=True)
    det["selftest"] = st.stdout.strip().splitlines()[-1]
    D["selftest"] = det["selftest"].startswith("R3HD_MODS_SELFTEST PASS")
    out = {"pass": all(D.values()), "D": D, "details": det}
    (WORK / "tests.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps(D, indent=1))
    print("TESTS_G6P7", "PASS" if out["pass"] else "FAIL")
    return 0 if out["pass"] else 1


def main():
    a = sys.argv[1:]
    if a == ["tests"]:
        return tests()
    if a == ["calibrate"]:
        return calibrate()
    if a == ["dossier"]:
        return dossier()
    if a == ["prototype"]:
        return prototype()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
