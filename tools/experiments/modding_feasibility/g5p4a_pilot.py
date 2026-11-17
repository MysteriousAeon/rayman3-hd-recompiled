#!/usr/bin/env python3
"""E-480 (D-247) G5-P4a: the development-only `insert-graph-node` on a second level, intro_20's fairy light.

usage:
  g5p4a_pilot.py check         offline O1-O8 (real game files read-only; no game started)
  g5p4a_pilot.py negtest       runtime transaction cases for intro_20 through g5p1_tx_test.cpp (dev and production
                               headers; no game started)
  g5p4a_pilot.py TAG           hidden runs A, B, C, D (development build)
  g5p4a_pilot.py judge TAG     P1-P8
Outputs stay under private/work/e480/.

TARGET (read-only survey s1, `g5p4a_survey.py`): intro_20.lvl 6,135,684 bytes (sha256 a21aa769...), intro_20.ptr
273,540 bytes (be90b58a...); `NIN_m_FairyLight` instance 2, designer variable 2 (type 20) -> graph at file offset
0x336050, 6 nodes, editable (referenced only by its owner). Unmodified and without input, its owner flies 0 -> 1 ->
2 -> 3 -> 4 -> 5 -> 0 (about 23.3 s a loop from about 11 s after the level opens) and passes within 0.20-0.27 units of
every waypoint. Site: after node 3 (one arc, no capabilities or weight, exclusive references; the same checks and
construction as intro_10: +112 `.lvl`, +72 `.ptr`, 9 new own-file slots, 4 asserted edits).
Positions: B neutral = midpoint M of waypoints 3 and 4 = (-17.0295, -51.4579, -22.0739); C offset = M + 6 units
horizontally perpendicular to the 3 -> 4 segment = (-11.5506, -49.0109, -22.0739) (in the survey the unmodified path
came 0.9 units from M and 6.1 from C's point).

PROSPECTIVE PROTOCOL (committed before any modified run)
Build: g5p1_dev_gate.py apply (G5-P3 snapshot + the intro_20 members) + tools\\build_incremental.bat; production
restored afterwards. Runs: m9_license_run.py hidden, non-activating, muted, no physical pad, private user root,
`--test-level intro_20`, no input, no frames, 130 s. Block-8 snapshot at every change of the area table; 6 s after
intro_20's area appears the actors are discovered once; the fairy is the `NIN_m_FairyLight` whose designer variable 2
equals the live graph (area base + 0x336050 - 4); its position is sampled every 0.1 s; the live graph is walked once
and the 9 new slots and 4 edited words are read once.
  A: no plan (control).  B: neutral plan (resolve_all, session = run; development variable intro_20).
  C: offset plan (same).  D: B's plan with the development variable unset (gate off).
Arrival: within 1.0 unit of an original waypoint; the new waypoint is "reached" within 0.6 units (B; A's path came
0.9 from M) or 1.0 (C). A 3 -> 4 pass = an arrival at node 3 followed by the next arrival at node 4.
  P1 resource integrity (B, C): one `M33 mods state=active`, one `G5P1 level-tx active level=intro_20` with the plan's
     id, `G5P3 tx snapshot` intro_20.lvl image_bytes 6135796 and intro_20.ptr 273612 with disk_reads=2, `M36 grow
     size` for both; no `G5P3 tx host_changed`.
  P2 guest relocation (B, C): each of the 9 new slots holds area base + its planned target - 4; the 4 edited words
     hold their planned values relocated; the fairy's variable 2 still equals the graph.
  P3 graph registration (B, C): live walk 7 distinct nodes, no problems, header count 7, the new node at index 4 with
     its waypoint at the planned address and position (within 0.001); A and D: 6 nodes, count 6.
  P4 consumption (B, C): >= 3 passes 3 -> 4, and in every one of them the new waypoint is reached between the two
     arrivals; A never comes within 0.6 of M nor within 1.0 of C's point.
  P5 neutral (B): the cyclic arrival order of the original nodes equals A's (0..5) and the mean loop period (between
     node-0 arrivals) is within 10 % of A's.
  P6 offset (C): the new waypoint (C's point) reached in every 3 -> 4 pass (>= 3); A's minimum distance to C's point
     >= 3.0; arrival order equals A's; loop period within 15 % of A's.
  P7 memory and lifecycle: every snapshot after the first valid one valid; B - A and C - A at intro_20 loaded =
     {area1 length +112, free -112, largest -112, nothing else}; D - A = {}; fix-only state before the level equal in
     all four (20,795,836 free, 1 / 1 chunks).
  P8 production and desktop safety: D logs `state=refused reason=level_tx_not_enabled` and no `M33 mods served`; M21 /
     M22 / M23 0, haptics policy line, runner exit 0, no game process left, in all four; B / C markers armed before the
     start (session, plan SHA-256) and cleared after the controlled end.
  Invalid (new tag): fairy not found, intro_20 never loaded, fewer than 3 passes 3 -> 4 in A.
  Classes: P1-P8 PASS = G5-P4a VERIFIED — CROSS-LEVEL STRUCTURAL MOD FUNCTIONAL.
"""
import json
import math
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
import g3b_ab as g3b  # noqa: E402
import block8_probe as bp  # noqa: E402
import g5p1_pilot as p1  # noqa: E402

PREFIX = "e480"
WORK = ROOT / "private" / "work" / PREFIX
p1.WORK = WORK
LEVEL, ENV = "intro_20", rm.STRUCT_ENV
GAME = g3a.GAME
RUNS = g3a.RUNS
SIZE, PSIZE = 6135684, 273540
LVL_SHA = "a21aa7691db4cedb3892e685e5395fd23b530b0bde4d64a09035dfb5f2d0b11f"
PTR_SHA = "be90b58a3bfa78d19f3335489edcc79214442d52cbde04c6ad5a465f9fb17cb1"
G, AFTER, INST, VAR = 0x336050, 3, 2, 2
POS = {"neutral": (-17.0295, -51.4579, -22.0739), "offset": (-11.5506, -49.0109, -22.0739)}
SECONDS = 130
FIX_ONLY_FREE = 20795836


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def site():
    ix = rm.read_script_index(GAME, LEVEL)
    lp, pp, me = rm.script_level_files(GAME, LEVEL)
    entry = ix["graphs"][(rm.FAIRY20, INST, VAR)]
    return ix, lp, pp, me, entry


def igm(variant, **kw):
    o = {"type": "insert-graph-node", "level": LEVEL, "model": rm.FAIRY20, "instance": INST, "variable": VAR,
         "after_node": AFTER, "lvl_sha256": LVL_SHA, "ptr_sha256": PTR_SHA, "position": list(POS[variant])}
    o.update(kw)
    return o


def compiled(variant, **kw):
    with p1.dev_env(LEVEL):
        return rm.compile_insert_graph_node(igm(variant, **kw), {"game": GAME})


def refused(fn, code, env=LEVEL):
    with p1.dev_env(env):
        return p1.refused(fn, code)


def compile_plan(name, mods, session=None):
    paths = p1.fresh(name)
    with p1.dev_env(LEVEL):
        for mid, ov in mods:
            p1.install(paths, mid, ov)
        res = rm.resolve_all(paths, write_plan=paths["cache"], session=session)
    plan = paths["cache"] / rm.PLAN_NAME
    return res, (plan.read_text(encoding="utf-8") if plan.is_file() else None), paths


# --- offline O1-O8 ----------------------------------------------------------------------------------------------

def walk_file(lvl, ptr, me):
    n = u32(ptr, 0)
    slots = {}
    for i in range(n):
        f, loc = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        slots.setdefault(loc + 4, []).append(f)

    def target(o):
        return u32(lvl, o) + 4 if slots.get(o) == [me] and o + 4 <= len(lvl) and u32(lvl, o) + 4 < len(lvl) else None
    nodes, nd = [], target(G)
    while nd is not None and len(nodes) < 64:
        nodes.append(nd)
        nd = target(nd)
    return slots, target, nodes


def check():
    res, det = {}, {}
    # O1: the two intro_10 sites pass their own deterministic offline checks unchanged
    o1 = {s: subprocess.run([sys.executable, str(HERE / s), "check"], cwd=ROOT, capture_output=True, text=True)
          for s in ("g5p1_pilot.py", "g5p2a_pilot.py")}
    det["O1"] = {s: (r.returncode, r.stdout.strip().splitlines()[-1][:200] if r.stdout.strip() else "") for s, r in
                 o1.items()}
    res["O1_original_sites"] = all(r.returncode == 0 for r in o1.values())
    # O2: exact identity of the target files and graph
    ix, lp, pp, me, entry = site()
    lvl, ptr = lp.read_bytes(), pp.read_bytes()
    allow = rm.STRUCT_ALLOW[LEVEL]
    res["O2_identity"] = ((len(lvl), rm.sha256_bytes(lvl)) == allow["lvl"] == (SIZE, LVL_SHA)
                          and (len(ptr), rm.sha256_bytes(ptr)) == allow["ptr"] == (PSIZE, PTR_SHA)
                          and entry["graph"] == G and len(entry["nodes"]) == 6 and not entry["safe"]
                          and allow["graphs"] == {(rm.FAIRY20, INST, VAR): (AFTER,)} and me == 1)
    # O3 / O4: graph and relocation integrity of both variants, checked independently of the compiler's simulator
    o3, o4 = True, True
    for v in POS:
        ranges, tx = compiled(v)
        L, P = tx["images"]["lvl"], tx["images"]["ptr"]
        info = tx["info"]
        slots, target, nodes = walk_file(L, P, me)
        old_slots, _, old_nodes = walk_file(lvl, ptr, me)
        FN, FW, FL, FA = (info["objects"][k] for k in ("node", "waypoint", "list", "arc"))
        refs_w = [s for s in slots if target(s) == FW]
        g3 = {
            "count": u32(L, G + 8) == 7 == len(nodes),
            "order": nodes == old_nodes[:4] + [FN] + old_nodes[4:],
            "waypoint": target(FN + 0xC) == FW and refs_w == [FN + 0xC]
            and all(abs(a - b) < 1e-4 for a, b in zip(struct.unpack_from(">3f", L, FW), POS[v]))
            and L[FW + 12:FW + 20] == lvl[entry["nodes"][3][1] + 12:entry["nodes"][3][1] + 20],
            "arcs": target(target(target(old_nodes[3] + 0x18)) + 0xC) == FN and target(FN + 0x18) == FL
            and target(FL) == FA and u32(L, FL + 8) == 1 and target(FA + 0xC) == old_nodes[4],
            "backward": target(FN + 4) == old_nodes[3] and target(old_nodes[4] + 4) == FN,
        }
        n0, n1 = u32(ptr, 0), u32(P, 0)
        g4 = {
            "unique": all(len(f) == 1 for f in slots.values()),
            "bounds": all(s + 4 <= len(L) and (f[0] != me or u32(L, s) + 4 < len(L)) for s, f in slots.items()),
            "prefix": P[4:4 + 8 * n0] == ptr[4:4 + 8 * n0] and n1 == n0 + 9,
            "cross_table": P[4 + 8 * n1:] == ptr[4 + 8 * n0:],
            "new_slots_in_tail": all(s >= len(lvl) for s in set(slots) - set(old_slots)) and
            len(set(slots) - set(old_slots)) == 9,
            "sizes": (len(L) - len(lvl), len(P) - len(ptr)) == (112, 72),
            "only_edits": [o for o in range(0, len(lvl), 4) if L[o:o + 4] != lvl[o:o + 4]]
            == sorted([old_nodes[3], old_nodes[4] + 4, target(old_nodes[3] + 0x18) and
                       target(target(old_nodes[3] + 0x18)) + 0xC, G + 8]),
        }
        det[f"O3_{v}"], det[f"O4_{v}"] = g3, g4
        o3 &= all(g3.values())
        o4 &= all(g4.values())
        det[f"memory_{v}"] = info["memory"]
    res["O3_graph"], res["O4_relocation"] = o3, o4
    # O5: one coherent transaction (plan, images, ids), the gameplay record
    r, text, paths = compile_plan("o5_neutral", [("g5p4a.neutral", [igm("neutral")])])
    m = p1.parse_plan(text or "")
    im = p1.images(m) if text else {}
    _, tx = compiled("neutral")
    txf = {Path(f["path"]).name: f["tx"] for f in m["files"]}
    sha = lambda b: rm.sha256_bytes(b)  # noqa: E731
    members = [("lvl", "intro_20.lvl", SIZE, LVL_SHA, SIZE + 112, sha(tx["images"]["lvl"])),
               ("ptr", "intro_20.ptr", PSIZE, PTR_SHA, PSIZE + 72, sha(tx["images"]["ptr"]))]
    res["O5_transaction"] = bool(
        r["active"] == ["g5p4a.neutral"] and len(m["txs"]) == 1 and m["txs"][0].split(" ")[1:4] == ["1", LEVEL,
                                                                                                   "g5p4a.neutral"]
        and m["txs"][0].split(" ")[4] == rm.tx_id(LEVEL, "g5p4a.neutral", members)
        and im.get("intro_20.lvl") == tx["images"]["lvl"] and im.get("intro_20.ptr") == tx["images"]["ptr"]
        and txf.get("intro_20.lvl") == [f"lvl {LVL_SHA} {SIZE + 112} {members[0][5]}"]
        and txf.get("intro_20.ptr") == [f"ptr {PTR_SHA} {PSIZE + 72} {members[1][5]}"]
        and m["gameplay"] == ["gameplay g5p4a.neutral"])
    det["O5"] = {"txs": m["txs"], "tx_files": txf}
    # O6: measured budget for intro_20
    mem = det["memory_neutral"]
    res["O6_memory"] = (mem["free_after_load"] == 14630936 - 112 and mem["headroom"] > 0
                        and mem["preread"] == SIZE + 112 <= mem["preread_verified"])
    # O7: fail closed
    d = POS["neutral"]
    wp3 = entry["nodes"][3][1]
    other = ("Fairylum\\NIN_m_FairyLight\\NIN_m_FairyLight.rul^CreateIntelligence^CreateComport:NIN_C_InitLight")
    G7 = {
        "no_env": refused(lambda: rm.parse_insert_graph_node(igm("neutral"), "o"), "UNSUPPORTED", env=None),
        "env_other_level": refused(lambda: rm.compile_insert_graph_node(igm("neutral"), {"game": GAME}),
                                   "UNSUPPORTED", env="intro_10"),
        "level_not_allowed": refused(lambda: rm.parse_insert_graph_node(igm("neutral", level="intro_17"), "o"),
                                     "UNSUPPORTED"),
        "wrong_lvl_sha": refused(lambda: compiled("neutral", lvl_sha256="0" * 64), "TARGET_CHANGED"),
        "wrong_ptr_sha": refused(lambda: compiled("neutral", ptr_sha256="1" * 64), "TARGET_CHANGED"),
        "node_2": refused(lambda: compiled("neutral", after_node=2), "UNSUPPORTED"),
        "node_4": refused(lambda: compiled("neutral", after_node=4), "UNSUPPORTED"),
        "shared_graph_instance_0": refused(lambda: compiled("neutral", instance=0), "UNSUPPORTED"),
        "other_instance_6": refused(lambda: compiled("neutral", instance=6), "UNSUPPORTED"),
        "non_graph_variable": refused(lambda: compiled("neutral", variable=1), "TARGET_MISSING"),
        "intro_10_model_here": refused(lambda: compiled("neutral", model=rm.FLY10), "TARGET_MISSING"),
        "too_far": refused(lambda: compiled("neutral", position=[d[0] + 20, d[1], d[2]]), "UNSUPPORTED"),
        "extra_key": refused(lambda: rm.parse_insert_graph_node(dict(igm("neutral"), offset=4), "o"), "BAD_MANIFEST"),
    }
    assert other == rm.FAIRY20
    # simulator as oracle: a duplicate slot and a slot pointing nowhere known are refused
    _, tx = compiled("neutral")
    L, P = tx["images"]["lvl"], tx["images"]["ptr"]
    info = tx["info"]
    nodes = [nd for nd, _ in entry["nodes"]]
    n1 = u32(P, 0)
    place = info["objects"]
    new_slots = [place["node"], place["node"] + 4, place["node"] + 8, place["node"] + 0xC, place["node"] + 0x18,
                 place["list"], place["list"] + 4, place["arc"] + 8, place["arc"] + 0xC]
    edits = [(nodes[3], ""), (nodes[4] + 4, ""), (None, ""), (G + 8, "")]
    arc3 = u32(lvl, u32(lvl, nodes[3] + 0x18) + 4) + 4
    edits[2] = (arc3 + 0xC, "")
    dup = bytearray(P)
    struct.pack_into(">iI", dup, 4 + 8 * (n1 - 1), 1, new_slots[0] - 4)   # last new entry names the first new slot
    bad_target = bytearray(L)
    struct.pack_into(">I", bad_target, place["node"] + 0xC, 0x100 - 4)     # waypoint slot -> unrelated data

    def sim(LL, PP):
        return lambda: rm.verify_insert(lvl, ptr, bytes(LL), bytes(PP), 1, G, nodes, AFTER, place, new_slots, edits,
                                        "o")
    G7["sim_valid_passes"] = sim(L, P)() is None
    G7["sim_duplicate_slot"] = p1.refused(sim(L, dup), "STRUCTURE_CHECK")
    G7["sim_invalid_target"] = p1.refused(sim(bad_target, P), "STRUCTURE_CHECK")
    # composition: a second structural mod on intro_20, and a fixed-size edit of the same graph's waypoint
    # (expectations corrected after the first check run, before any game run: the existing D-243 policy refuses BOTH
    # structural mods of one level, as G5-P1's comp_two_structural_both_refused; and a waypoint-position edit of node
    # 3 overlaps no byte the transaction owns, so it composes -- the overlap case is G5-P1's synthetic count-word one)
    codes = lambda r: {x["id"]: x.get("code") for x in r["mods"] if x["state"] != "active"}  # noqa: E731
    r2, _, _ = compile_plan("o7_two", [("g5p4a.neutral", [igm("neutral")]), ("g5p4a.offset", [igm("offset")])])
    G7["two_structural_both_refused"] = r2["active"] == [] and codes(r2) == {
        "g5p4a.neutral": "STRUCTURAL_CONFLICT", "g5p4a.offset": "STRUCTURAL_CONFLICT"}
    wpm = {"type": "waypoint-position", "level": LEVEL, "model": rm.FAIRY20, "instance": INST, "variable": VAR,
           "node": 3, "waypoint_sha256": rm.sha256_bytes(lvl[wp3:wp3 + 0x14]), "position": [-15.0, -55.0, -28.0]}
    r3, t3, _ = compile_plan("o7_fixed", [("g5p4a.neutral", [igm("neutral")]), ("g5p4a.wp3", [wpm])])
    m3 = p1.parse_plan(t3 or "")
    G7["disjoint_fixed_composes"] = (r3["active"] == ["g5p4a.neutral", "g5p4a.wp3"] and len(m3["txs"]) == 1
                                     and p1.images(m3)["intro_20.lvl"][wp3:wp3 + 12]
                                     == struct.pack(">3f", -15.0, -55.0, -28.0))
    real_compile = rm.compile_mod
    lvl_p = lp

    def fake_compile(m, files, paths, manifests=None):
        if m["id"].startswith("f."):
            return [(lvl_p, G + 8, struct.pack(">I", 7), "synthetic.count")]
        return real_compile(m, files, paths, manifests)
    rm.compile_mod = fake_compile
    try:
        for label, order_, want_active, want in (
                ("structural_over_fixed", [("s.a", [igm("neutral")]), ("f.fixed", [wpm])], ["s.a"],
                 {"f.fixed": "STRUCTURAL_CONFLICT"}),
                ("fixed_over_structural", [("f.fixed", [wpm]), ("s.a", [igm("neutral")])], ["f.fixed"],
                 {"s.a": "STRUCTURAL_CONFLICT"})):
            r4, _, _ = compile_plan(f"o7_{label}", order_)
            G7[label] = r4["active"] == want_active and codes(r4) == want
    finally:
        rm.compile_mod = real_compile
    det["O7"] = G7
    det["O7_mods"] = {"two": r2["mods"], "fixed": r3["mods"]}
    res["O7_fail_closed"] = all(v is True for v in G7.values())
    # O8: compatibility (selftest; production refusal and VS.sub growth are runtime tests after the rebuild)
    st = subprocess.run([sys.executable, str(TOOLS / "r3hd_mods.py"), "selftest"], cwd=ROOT, capture_output=True,
                        text=True)
    det["O8_selftest"] = st.stdout.strip().splitlines()[-1] if st.stdout.strip() else st.stderr[-300:]
    res["O8_compatibility"] = st.returncode == 0
    out = {"res": res, "details": det, "pass": all(res.values())}
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "check.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(json.dumps({"res": res, "O7": {k: v for k, v in G7.items() if v is not True}}, indent=1, default=str))
    return 0 if out["pass"] else 1


# --- runtime transaction cases ----------------------------------------------------------------------------------

def negtest():
    nd = WORK / "negtest"
    nd.mkdir(parents=True, exist_ok=True)
    exes = {k: p1.build_test(k) for k in ("dev", "prod")}
    _, text, _ = compile_plan("neg_valid", [("g5p4a.neutral", [igm("neutral")])])
    base = p1.parse_plan(text)
    im = p1.images(base)
    (nd / "n20_lvl.bin").write_bytes(im["intro_20.lvl"])
    (nd / "n20_ptr.bin").write_bytes(im["intro_20.ptr"])
    li = next(i for i, f in enumerate(base["files"]) if f["path"].endswith("intro_20.lvl"))
    pi = 1 - li
    _, lp, pp, _, _ = site()
    stale = nd / "stale"
    if stale.exists():
        shutil.rmtree(stale)
    stale.mkdir()
    sl, sp = stale / "intro_20.lvl", stale / "intro_20.ptr"
    shutil.copyfile(lp, sl)
    shutil.copyfile(pp, sp)
    b = bytearray(sl.read_bytes())
    b[3000000] ^= 0x01                              # a same-size change of a private copy (never the game files)
    sl.write_bytes(bytes(b))

    def variant(name, fn=None):
        m = json.loads(json.dumps(base))
        if fn:
            fn(m)
        p = nd / f"plan_n20_{name}.txt"
        p.write_text(p1.emit(m), encoding="utf-8")
        return p

    def tamper(m, i, ri):
        off, length, gb, nb, mid, blob = m["files"][i]["range"][ri].split(" ", 5)
        bb = bytearray(Path(blob).read_bytes())
        bb[len(bb) // 2] ^= 0x33
        q = nd / f"n20_tampered_{i}_{ri}.bin"
        q.write_bytes(bytes(bb))
        h = 0xCBF29CE484222325
        for x in bb:
            h = ((h ^ x) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
        m["files"][i]["range"][ri] = " ".join([off, length, gb, f"{h:016x}", mid, str(q)])

    def retx(m, i, k, v):
        t = m["files"][i]["tx"][0].split(" ")
        t[k] = v
        m["files"][i]["tx"][0] = " ".join(t)

    def txline(m, k, v):
        t = m["txs"][0].split(" ")
        t[k] = v
        m["txs"][0] = " ".join(t)

    def to_stale(m):
        m["files"][li]["path"] = str(sl)
        m["files"][pi]["path"] = str(sp)
    plans = {
        "valid": variant("valid"),
        "missing_lvl": variant("missing_lvl", lambda m: m["files"].pop(li)),
        "missing_ptr": variant("missing_ptr", lambda m: m["files"].pop(pi)),
        "tampered_ptr": variant("tampered_ptr", lambda m: tamper(m, pi, 0)),
        "wrong_lvl_sha": variant("wrong_lvl_sha", lambda m: retx(m, li, 1, "0" * 64)),
        "corrupt_id": variant("corrupt_id", lambda m: txline(m, 4, m["txs"][0].split(" ")[4][:-1] + (
            "0" if m["txs"][0][-1] != "0" else "1"))),
        # G6-P3 (D-256, E-489) expectation correction, before any G6-P3 game run (the G6-P1 precedent, E-484): intro_20
        # now has version-2 members (its transit.lvl), so the unsupported-version case claims version 3 (still
        # `tx_version`), and the version-1 plan relabelled as version 2 is its own case: refused whole, missing the
        # transit member (`tx_incomplete`). The original G5-P4a result for "2" (`tx_version`, E-480) stays in its logs.
        "version_2": variant("version_2", lambda m: txline(m, 1, "3")),
        "relabelled_2": variant("relabelled_2", lambda m: txline(m, 1, "2")),
        "duplicate_tx": variant("duplicate_tx", lambda m: m["txs"].append(m["txs"][0])),
        "intro_10_level": variant("intro_10_level", lambda m: txline(m, 2, "intro_10")),
        "stale_copy": variant("stale_copy", to_stale),
    }
    O = ("-", "-")
    V = (nd / "n20_lvl.bin", nd / "n20_ptr.bin")
    lvl_p, ptr_p = str(lp), str(pp)
    dev = [("intro_20 valid, .lvl first", "valid", LEVEL, "active", "lvl,ptr", V, None),
           ("intro_20 valid, .ptr first", "valid", LEVEL, "active", "ptr,lvl", V, None),
           ("intro_20 valid, repeated opens", "valid", LEVEL, "active", "lvl,ptr,lvl,ptr,ptr,lvl", V, None),
           ("intro_20 not enabled (.lvl first)", "valid", "-", "level_tx_not_enabled", "lvl,ptr", O, None),
           ("intro_20 not enabled (.ptr first)", "valid", "-", "level_tx_not_enabled", "ptr,lvl", O, None),
           ("intro_20 plan, variable names intro_10", "valid", "intro_10", "tx_level", "lvl,ptr", O, None),
           ("intro_20 missing .lvl member", "missing_lvl", LEVEL, "tx_incomplete", "ptr,lvl", O, None),
           ("intro_20 missing .ptr member", "missing_ptr", LEVEL, "tx_incomplete", "lvl,ptr", O, None),
           ("intro_20 tampered .ptr, rehashed", "tampered_ptr", LEVEL, "tx_result_hash", "ptr,lvl", O, None),
           ("intro_20 wrong original .lvl hash", "wrong_lvl_sha", LEVEL, "tx_identity", "lvl,ptr", O, None),
           ("intro_20 corrupted id", "corrupt_id", LEVEL, "tx_id", "lvl,ptr", O, None),
           ("intro_20 unsupported version", "version_2", LEVEL, "tx_version", "lvl,ptr", O, None),
           ("intro_20 version-1 plan relabelled as version 2 (G6-P3)", "relabelled_2", LEVEL, "tx_incomplete",
            "lvl,ptr", O, None),
           ("intro_20 duplicate transaction", "duplicate_tx", LEVEL, "tx_count", "lvl,ptr", O, None),
           ("intro_20 members under the intro_10 level", "intro_10_level", LEVEL, "tx_level", "lvl,ptr", O, None),
           ("intro_20 tampered .lvl copy (same size)", "stale_copy", LEVEL, "tx_identity", "ptr,lvl", O,
            (str(sl), str(sp)))]
    prod = [("production: intro_20 transaction (.lvl first)", "valid", LEVEL, "unknown_record", "lvl,ptr", O, None),
            ("production: intro_20 transaction (.ptr first)", "valid", LEVEL, "unknown_record", "ptr,lvl", O, None)]
    out = {}
    for kind, cases in (("dev", dev), ("prod", prod)):
        cf = nd / f"cases_n20_{kind}.tsv"
        cf.write_text("".join("\t".join([n, str(plans[p]), env, want, order, (f or (lvl_p, ptr_p))[0],
                                         (f or (lvl_p, ptr_p))[1], str(e[0]), str(e[1])]) + "\n"
                              for n, p, env, want, order, e, f in cases), encoding="utf-8")
        r = subprocess.run([str(exes[kind]), str(cf)], capture_output=True, text=True, timeout=600)
        (nd / f"result_n20_{kind}.txt").write_text(r.stdout + r.stderr)
        print(r.stdout)
        out[kind] = {"exit": r.returncode, "summary": r.stdout.strip().splitlines()[-1] if r.stdout else ""}
    shutil.rmtree(stale)   # private copies of the game files: not kept
    ok = all(v["exit"] == 0 for v in out.values())
    (nd / "summary_n20.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out), "NEGTEST_P4A", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# --- hidden runs ------------------------------------------------------------------------------------------------

def run_case(tag, case):
    from m5_live import Actor, Process
    work = WORK / tag / case
    run = f"{PREFIX}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    for k in ("R3HD_MODS_PLAN", "R3HD_E465_TEST_GROW", "R3HD_G3A_TEST_GROW", ENV):
        env.pop(k, None)
    row = {"case": case, "run": run, "marker_before_start": ["none", None]}
    paths, info = None, None
    if case in ("B", "C", "D"):
        v = "offset" if case == "C" else "neutral"
        _, tx = compiled(v)
        info = tx["info"]
        res, text, paths = compile_plan(f"run_{tag}_{case}", [(f"g5p4a.{v}", [igm(v)])],
                                        session=run if case != "D" else None)
        if res["active"] != [f"g5p4a.{v}"]:
            raise SystemExit(f"plan: {res['mods']}")
        plan = paths["cache"] / rm.PLAN_NAME
        shutil.copyfile(plan, work / "plan_copy.txt")
        row["plan_sha256"] = rm.sha256_bytes(plan.read_bytes())
        row["marker_before_start"] = rm.read_structural_marker(paths)
        env["R3HD_MODS_PLAN"] = str(plan)
        if case != "D":
            env[ENV] = LEVEL
        row["objects"] = info["objects"]
    (work / "steps.txt").write_text(f"wait {SECONDS - 8}\n", encoding="ascii")
    states, samples, live = [], [], {}
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(SECONDS), "--play", "--test-level", LEVEL,
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
            last, t_end, area_t, ab, fairy, nxt, done = "none", t0 + SECONDS - 5, None, None, None, 0.0, False

            def rd(a):
                w = p.words(a, 1)
                if not w:
                    raise ValueError(f"read {a:#x}")
                return w[0]
            while time.monotonic() < t_end and p.running():
                ar = bp.areas(p)
                key = json.dumps({k: (v["base"], v["end"]) for k, v in (ar or {}).items()})
                if ar is not None and key != last:
                    last = key
                    s = bp.snapshot(p)
                    s.update(t=round(time.monotonic() - t0, 3), state="areas_changed", area_keys=sorted(ar))
                    states.append(s)
                    if ar.get(1) and area_t is None:
                        area_t, ab = time.monotonic(), ar[1]["base"]
                if area_t is not None and not done and time.monotonic() >= area_t + 6:
                    done = True
                    gl = ab + G - 4
                    disc = work / "discovery.json"
                    q = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), base, str(disc),
                                        "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
                    for a in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if q.returncode == 0 else []):
                        try:
                            act = Actor(p, int(a["so"], 16))
                            if act.model == "NIN_m_FairyLight" and act.mind:
                                d = act.dsg()
                                if struct.unpack_from(">I", *d[VAR])[0] == gl:
                                    fairy = act
                                    break
                        except Exception:
                            continue
                    try:
                        nodes, prob, hdr = g3b.walk_null(rd, gl)
                        live = {"t": round(time.monotonic() - t0, 3), "ab": ab, "nodes": nodes, "problems": prob,
                                "header": hdr, "fairy": hex(fairy.so) if fairy else None}
                        if fairy:
                            live["fairy_var2"] = struct.unpack_from(">I", *fairy.dsg()[VAR])[0]
                        if info:
                            o = info["objects"]
                            FN, FL, FA = o["node"], o["list"], o["arc"]
                            new_slots = [FN, FN + 4, FN + 8, FN + 0xC, FN + 0x18, FL, FL + 4, FA + 8, FA + 0xC]
                            live["new_slots"] = {hex(s_): rd(ab + s_ - 4) for s_ in new_slots}
                            live["waypoint_pos"] = list(struct.unpack(">3f", p.read(ab + o["waypoint"] - 4, 12)))
                    except Exception as x:
                        live = {"error": repr(x)}
                now = time.monotonic()
                if fairy is not None and now >= nxt:
                    try:
                        samples.append({"t": round(now - t0, 3), "p": list(fairy.position())})
                    except Exception as x:
                        row["sampling_stopped"] = type(x).__name__
                        fairy = None
                    nxt = now + 0.1
                time.sleep(0.005)
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and g3a.alive(pid))
    controlled = row["runner_exit"] == 0 and not (RUNS / run / "r3hd_crash.txt").exists()
    row["controlled"] = controlled
    if paths is not None:
        if row["marker_before_start"][0] == "armed":
            row["session_end"] = rm.end_structural_session(paths, run, row["plan_sha256"], controlled)
        row["marker_after"] = rm.read_structural_marker(paths)[0]
    for name, obj in (("states", states), ("samples", samples), ("live", live), ("row", row)):
        (work / f"{name}.json").write_text(json.dumps(obj, indent=1, default=str) + "\n")
    return row


def run(tag):
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], capture_output=True, text=True)
    if st.stdout.strip() != "patched":
        raise SystemExit("the development gate is not applied")
    for case in ("A", "B", "C", "D"):
        print(json.dumps(run_case(tag, case), default=str), flush=True)
    return 0


def judge(tag):
    ix, lp, pp, me, entry = site()
    lvl = lp.read_bytes()
    wps = [struct.unpack_from(">3f", lvl, w) for _, w in entry["nodes"]]
    out = {}
    for case in ("A", "B", "C", "D"):
        w = WORK / tag / case
        r = json.loads((w / "row.json").read_text())
        for k in ("states", "samples", "live"):
            r[k] = json.loads((w / f"{k}.json").read_text())
        r["log"] = "\n".join(q.read_text(errors="replace") for q in sorted((RUNS / r["run"]).glob("runtime*.log")))
        r["judges"] = {t: subprocess.run([sys.executable, str(TOOLS / t), "--run", r["run"]], cwd=ROOT,
                                         capture_output=True, text=True).returncode
                       for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py")}
        out[case] = r
    A, B, C, D = (out[c] for c in "ABCD")
    det, P = {}, {}

    def arrivals(r, newpos=None, rnew=1.0):
        seq = []
        for s in r["samples"]:
            p = s["p"]
            hit = None
            for i, wpt in enumerate(wps):
                if math.dist(p, wpt) < 1.0:
                    hit = i
            if newpos is not None and math.dist(p, newpos) < rnew:
                hit = "N"
            if hit is not None and (not seq or seq[-1][1] != hit):
                seq.append((s["t"], hit))
        return seq

    def passes(seq):
        """3 -> 4 passes: (count, with N between)."""
        orig = [(t, h) for t, h in seq]
        n = withn = 0
        for i, (t, h) in enumerate(orig):
            if h != 3:
                continue
            j = next((k for k in range(i + 1, len(orig)) if orig[k][1] in (0, 1, 2, 3, 4, 5)), None)
            if j is None or orig[j][1] != 4:
                continue
            n += 1
            withn += any(orig[k][1] == "N" for k in range(i + 1, j))
        return n, withn

    def order(seq):
        o = [h for _, h in seq if h != "N"]
        return o

    def period(seq):
        z = [t for t, h in seq if h == 0]
        return (z[-1] - z[0]) / (len(z) - 1) if len(z) >= 2 else None

    def mind(r, pt):
        return min((math.dist(s["p"], pt) for s in r["samples"]), default=None)
    sA = arrivals(A)
    sB = arrivals(B, POS["neutral"], 0.6)
    sC = arrivals(C, POS["offset"], 1.0)
    sD = arrivals(D)
    pa = {c: passes(s) for c, s in (("A", sA), ("B", sB), ("C", sC), ("D", sD))}
    per = {c: period(s) for c, s in (("A", sA), ("B", sB), ("C", sC), ("D", sD))}

    def cyc(o):
        """True if consecutive arrivals step by +1 mod 6 throughout."""
        return all((b - a) % 6 == 1 for a, b in zip(o, o[1:]))
    det.update(passes=pa, period=per, minA_M=mind(A, POS["neutral"]), minA_W=mind(A, POS["offset"]),
               minB_N=mind(B, POS["neutral"]), minC_N=mind(C, POS["offset"]),
               seq={c: s[:60] for c, s in (("A", sA), ("B", sB), ("C", sC), ("D", sD))})
    invalid = [c for c in out if out[c].get("error") or not out[c]["live"].get("fairy")] + (
        ["A:passes"] if pa["A"][0] < 3 else [])
    tx = re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", B["log"] + "\n" + C["log"])

    def p1ok(r):
        log = r["log"]
        ptx = p1.parse_plan((WORK / tag / r["case"] / "plan_copy.txt").read_text(encoding="utf-8"))["txs"]
        want = [tuple(ptx[0].split(" ")[2:5])]
        t = [tuple(x) for x in re.findall(r"G5P1 level-tx active level=(\S+) mod=(\S+) id=(\S+)", log)]
        snaps = sorted((f, b, d) for f, _, b, d in re.findall(
            r"G5P3 tx snapshot file=(\S+) host_size=(\d+) image_bytes=(\d+) disk_reads=(\d+)", log))
        grow = sorted(set(re.findall(r"M36 grow size file=(\S+) host_size=(\d+) guest_size=(\d+)", log)))
        return (log.count("M33 mods state=active") == 1 and t == want
                and snaps == [("intro_20.lvl", "6135796", "2"), ("intro_20.ptr", "273612", "2")]
                and grow == [("intro_20.lvl", "6135684", "6135796"), ("intro_20.ptr", "273540", "273612")]
                and "G5P3 tx host_changed" not in log)
    P["P1_resource_integrity"] = p1ok(B) and p1ok(C)
    det["tx"] = tx

    def p2ok(r):
        lv, o, ab = r["live"], r["objects"], r["live"].get("ab")
        if not ab or "new_slots" not in lv:
            return False
        FN, FW, FL, FA = o["node"], o["waypoint"], o["list"], o["arc"]
        nodes = [nd for nd, _ in entry["nodes"]]
        want = {FN: nodes[4], FN + 4: nodes[3], FN + 8: G, FN + 0xC: FW, FN + 0x18: FL, FL: FA, FL + 4: FA,
                FA + 8: FL, FA + 0xC: nodes[4]}
        ok = all(lv["new_slots"][hex(s)] == ab + t - 4 for s, t in want.items())
        ln = lv["nodes"]
        return ok and lv.get("fairy_var2") == ab + G - 4 and len(ln) == 7 and ln[3] == ab + nodes[3] - 4 and \
            ln[4] == ab + FN - 4 and ln[5] == ab + nodes[4] - 4
    P["P2_guest_relocation"] = p2ok(B) and p2ok(C)

    def p3(r, n, newnode=None, pos=None):
        lv = r["live"]
        ok = lv.get("problems") == [] and len(lv.get("nodes", [])) == n == len(set(lv["nodes"])) and \
            lv["header"]["count"] == n
        if newnode is not None:
            ok = ok and lv["nodes"][4] == lv["ab"] + newnode - 4 and all(
                abs(a - b) < 1e-3 for a, b in zip(lv["waypoint_pos"], pos))
        return ok
    P["P3_graph_registration"] = (p3(B, 7, B["objects"]["node"], POS["neutral"])
                                  and p3(C, 7, C["objects"]["node"], POS["offset"]) and p3(A, 6) and p3(D, 6))
    P["P4_consumption"] = (pa["B"][0] >= 3 and pa["B"][1] == pa["B"][0] and pa["C"][0] >= 3
                           and pa["C"][1] == pa["C"][0] and det["minA_M"] >= 0.6 and det["minA_W"] >= 1.0)
    oA = order(sA)
    P["P5_neutral"] = (cyc(oA) and cyc(order(sB)) and per["A"] and per["B"]
                       and abs(per["B"] - per["A"]) <= 0.10 * per["A"])
    P["P6_offset"] = (pa["C"][0] >= 3 and pa["C"][1] == pa["C"][0] and det["minA_W"] >= 3.0 and cyc(order(sC))
                      and per["C"] and abs(per["C"] - per["A"]) <= 0.15 * per["A"])

    def brief(x):
        return None if not x else {"free": x["free_bytes"], "largest": x["largest_free"],
                                   "alloc": x["allocated_chunks"], "free_chunks": x["free_chunks"],
                                   "areas": {k: (v["base"], v["length"], v.get("save_words"))
                                             for k, v in x["areas"].items()}}

    def phase(r):
        st = r["states"]
        i0 = next((i for i, x in enumerate(st) if "invalid" not in x), None)
        ok = i0 is not None and not any("invalid" in x for x in st[i0:])
        valid = [x for x in st if "invalid" not in x]
        fix = next((x for x in valid if set(x["areas"]) == {"0"}), None)
        lvl_ = next((x for x in valid if "1" in x["areas"]), None)
        return ok, brief(fix), brief(lvl_)

    def diff(a, b):
        d = {k: a[k] - b[k] for k in ("free", "largest", "alloc", "free_chunks") if a[k] != b[k]}
        for k in sorted(set(a["areas"]) | set(b["areas"])):
            x, y = a["areas"].get(k), b["areas"].get(k)
            if x == y:
                continue
            if x and y and x[0] == y[0] and x[2] == y[2]:
                d[f"area{k}_length"] = x[1] - y[1]
            else:
                d[f"area{k}"] = [x, y]
        return d
    ph = {c: phase(out[c]) for c in out}
    det["phases"] = ph
    want = {"area1_length": 112, "free": -112, "largest": -112}
    try:
        D7 = {c: diff(ph[c][2], ph["A"][2]) for c in "BCD"}
        det["D"] = D7
        P["P7_memory"] = (all(ph[c][0] for c in out) and D7["B"] == want and D7["C"] == want and D7["D"] == {}
                          and all(ph[c][1] == ph["A"][1] for c in "BCD") and ph["A"][1]["free"] == FIX_ONLY_FREE
                          and ph["A"][1]["alloc"] == 1 and ph["A"][1]["free_chunks"] == 1)
    except Exception as x:
        det["D"] = repr(x)
        P["P7_memory"] = False
    safe = all("M23 haptics policy=suppressed physical_pad_drivers=none" in r["log"] and not any(r["judges"].values())
               and r["runner_exit"] == 0 and not r["process_left"] for r in out.values())
    marks = all(r["marker_before_start"][0] == "armed" and r["marker_before_start"][1]["session"] == r["run"]
                and r["marker_before_start"][1]["plan_sha256"] == r["plan_sha256"] and r["controlled"] is True
                and r["session_end"]["cleared"] is True and r["marker_after"] == "none" for r in (B, C))
    P["P8_safety"] = (safe and marks and "state=refused reason=level_tx_not_enabled" in D["log"]
                      and "M33 mods served" not in D["log"])
    passed = [k for k, v in P.items() if v is True]
    verdict = ("G5-P4a VERIFIED — CROSS-LEVEL STRUCTURAL MOD FUNCTIONAL" if not invalid and len(passed) == 8
               else ("INVALID" if invalid else "NOT PASSED"))
    res = {"invalid": invalid, "P": P, "verdict": verdict, "details": det,
           "judges": {c: r["judges"] for c, r in out.items()}}
    (WORK / f"judgement_{tag}.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({k: res[k] for k in ("invalid", "P", "verdict")}, indent=1))
    print(json.dumps({k: det[k] for k in ("passes", "period", "minA_M", "minA_W", "minB_N", "minC_N", "D")},
                     indent=1, default=str))
    return 0 if verdict.startswith("G5-P4a") else 1


def main():
    a = sys.argv[1:]
    if a and a[0] == "check":
        return check()
    if a and a[0] == "negtest":
        return negtest()
    if len(a) == 2 and a[0] == "judge":
        return judge(a[1])
    if len(a) == 1 and re.fullmatch(r"[A-Za-z0-9-]{1,24}", a[0]):
        return run(a[0])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
