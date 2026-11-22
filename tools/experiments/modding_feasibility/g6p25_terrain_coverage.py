#!/usr/bin/env python3
"""E-514 (D-281) G6-P25: bounded intro_20 terrain-coverage feasibility study (read-only, offline).

    g6p25_terrain_coverage.py check   O1-O5 of region start-floor-v2 (vertex 6) and the west-basin example
    g6p25_terrain_coverage.py study   candidate table of the first ring of collision vertices around region
                                      start-floor-v1 (0 / 2 / 4): position, floor / steep triangle membership, visual
                                      twins, and representative trials through the unchanged compiler validator
                                      (rm.collision_edit) plus the independent G6-P22 geometry checker
Outputs: private/work/e514/ (numbers only). Reuses the G6-P19 mesh / visual decoders; no new decoder.
`check` also takes --identity X / --bin DIR for its build identity row (build_identity.py; G6-P64, D-313).
"""
import json
import math
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import r3hd_mods as rm  # noqa: E402
import g6p22_intro20_terrain as g22  # noqa: E402

g19 = g22.g19
ROOT, LEVEL = g22.ROOT, g22.LEVEL
WORK = ROOT / "private" / "work" / "e514"
REGION = (0, 2, 4)
PRIOR = {9: "E-508: triangle 1/189 (9, 36, 37) at normal z 0.908, at the 0.9 floor",
         10: "E-508: no visual twin within 0.001 (visual 1368 is 0.0058 above)",
         1: "E-508: rim / wall bottom", 5: "E-508: rim / wall bottom", 8: "E-508: rim / wall bottom",
         36: "E-508: rim / wall bottom", 37: "E-508: rim / wall bottom",
         42: "E-508: breaks ring pairing and octree membership", 6: "E-508: adds only one visual triangle"}


def spec_for(lvl, groups, vp, twins):
    """collision_edit spec (the terrain_spec form) for {vertex: dz} groups; twins {collision: visual}."""
    vo = g19.mesh(lvl)[1]["vo"]
    hx = lambda off: lvl[off:off + 12].hex()   # noqa: E731
    moved = [v for g, _ in groups for v in g]
    return {"bounds": "keep", "min_normal_z": 0.9,
            "groups": [{"dz": dz, "vertices": {v: hx(vo + 4 + 12 * v) for v in g}} for g, dz in groups],
            "visual": {"object": 0xBA80, "vertices_total": 3650, "elements": 11, "ring": "collision", "match": 0.001,
                       "complete": True, "pair": True,
                       "map": {twins[v]: (hx(vp + 12 * twins[v]), v) for v in moved}}}


def trial(lvl, ptr, groups, vp, twins):
    t0 = time.perf_counter()
    try:
        eds = rm.collision_edit(lvl, ptr, LEVEL, spec_for(lvl, [(g, dz) for g, dz in groups], vp, twins), "g6p25")
    except rm.Refusal as x:
        return {"compiler": "refused", "why": x.detail.split(": ", 1)[-1], "s": round(time.perf_counter() - t0, 2)}
    new = bytearray(lvl)
    for off, d, _ in eds:
        new[off:off + len(d)] = d
    moved = {v: dz for g, dz in groups for v in g}
    ok, f, _, z = g22.geometry(lvl, bytes(new), moved)
    return {"compiler": "accepted", "ranges": len(eds), "independent_ok": ok, "settled_z": z,
            "ring": [f["collision_ring"], f["visual_ring"]], "ring_normal_z_min": f["ring_normal_z_min"],
            "box_margin_z_min": min(f["bound_margins_z_below"].values()), "octree_new": f["octree_new_unlisted"],
            "s": round(time.perf_counter() - t0, 2)}


def study():
    WORK.mkdir(parents=True, exist_ok=True)
    lvl, ptr = g19.files()
    L, m = g19.mesh(lvl)
    V = m["verts"]
    vp = L.ptr(g19.VOBJ - 4) + 4
    nvv = struct.unpack_from(">H", lvl, g19.VOBJ + 0x24)[0]
    vverts = [struct.unpack_from(">3f", lvl, vp + 12 * k) for k in range(nvv)]
    tris = [(ei, j, e["idx"][3 * j:3 * j + 3]) for ei, e in enumerate(m["elems"]) for j in range(e["nt"])]
    nz = {(ei, j): (rm._face(*(V[q] for q in t)) or [0, 0, 0])[2] for ei, j, t in tris}
    star = lambda v: [(ei, j) for ei, j, t in tris if v in t]   # noqa: E731
    ring1 = sorted({q for v in REGION for ei, j, t in tris if v in t for q in t} - set(REGION))
    # second ring: through the FLOOR triangles of the first ring only (no walls), capped
    ring2 = sorted({q for v in ring1 for ei, j, t in tris if v in t and nz[(ei, j)] >= 0.9 for q in t}
                   - set(REGION) - set(ring1))
    cands = ring1 + [v for v in ring2 if abs(V[v][2] - V[0][2]) < 1.0][:max(0, 12 - len(ring1))]
    rows, twins = {}, {}
    for v in cands:
        d = sorted((math.dist(w, V[v]), k) for k, w in enumerate(vverts))[:2]
        tw = [k for dist, k in d if dist <= 0.001]
        if len(tw) == 1 and d[1][0] > 0.001:
            twins[v] = tw[0]
        st = star(v)
        rows[v] = {"pos": [round(x, 3) for x in V[v]], "ring": 1 if v in ring1 else 2,
                   "twin": tw, "twin_err": round(d[0][0], 5), "next_visual": round(d[1][0], 4),
                   "floor_tris": [list(t) for t in st if nz[t] >= 0.9],
                   "steep_tris": [[*t, round(nz[t], 3)] for t in st if nz[t] < 0.9],
                   "shares_region": sorted({q for ei, j, t in tris if v in t for q in t} & set(REGION)),
                   "prior": PRIOR.get(v)}
    for v, r in rows.items():
        if v not in twins or r["steep_tris"]:
            r["trial"] = "not tried (no unique twin)" if v not in twins else "not tried (on a steep / wall triangle)"
            continue
        r["trial_min"] = trial(lvl, ptr, [([v], -0.05), ([0], -0.05)], vp, {**twins, 0: 131})
        r["trial_max"] = trial(lvl, ptr, [([v], -0.30), ([0], -0.05)], vp, {**twins, 0: 131})
    out = {"region": REGION, "ring1": ring1, "ring2_considered": ring2, "candidates": rows}
    (WORK / "study.json").write_text(json.dumps(out, indent=1, default=str) + "\n", encoding="utf-8")
    for v, r in rows.items():
        print(v, json.dumps(r, default=str))
    return 0


# ------------------------------------------------------------------------------------------------- O1-O5 acceptance
EX, TP = g22.EX, HERE / "terrain_patches"
BASIN, BASIN_LP = TP / "intro20-west-basin.json", EX / "g6p25_west_basin_fairy.json"
KNOWN = {"g6p22_west_dip_fairy.json": "3e74d122bdb042e3", "g6p22_reference_patch.json": "1b1f404eaf81a240",
         "g6p20_reference.json": "1b1f404eaf81a240", "graph_b.json": "3cdb5be5ebafc590"}
REPR = {   # representative displacements (no sweep): minimum, maximum, mixed 4-group, shared group, the example
    "min 6 -0.05, 0 -0.05": [([6], -0.05), ([0], -0.05)],
    "max 6 -0.20, 2/4 -0.30, 0 -0.30": [([6], -0.20), ([2, 4], -0.30), ([0], -0.30)],
    "mixed 6 -0.20, 2 -0.30, 4 -0.05, 0 -0.10": [([6], -0.20), ([2], -0.30), ([4], -0.05), ([0], -0.10)],
    "shared 4/6 -0.20, 2 -0.30, 0 -0.05": [([4, 6], -0.20), ([2], -0.30), ([0], -0.05)],
    "west-basin 6 -0.20, 2/4 -0.15": [([6], -0.20), ([2, 4], -0.15)]}


def v2patch(groups, name="t"):
    return dict(g22.tpatch(groups, name), region="start-floor-v2")


def check():
    import os
    import shutil
    import g6p24_authoring_ux as g24
    WORK.mkdir(parents=True, exist_ok=True)
    O, det, t_start = {}, {}, time.perf_counter()
    lvl, ptr = g19.files()
    L, m = g19.mesh(lvl)
    V = m["verts"]
    vp = L.ptr(g19.VOBJ - 4) + 4
    reg = rm.terrain_region(LEVEL, "start-floor-v2")
    tris = {(ei, j): e["idx"][3 * j:3 * j + 3] for ei, e in enumerate(m["elems"]) for j in range(e["nt"])}
    star6 = {t: q for t, q in tris.items() if 6 in q}
    nz6 = {t: rm._face(*(V[q] for q in idx))[2] for t, idx in star6.items()}
    nvv = struct.unpack_from(">H", lvl, g19.VOBJ + 0x24)[0]
    near = sorted(math.dist(struct.unpack_from(">3f", lvl, vp + 12 * k), V[6]) for k in range(nvv))[:2]
    # O1 target evidence
    o1 = {"vertex 6 original bytes = the region constant (collision and visual twin 204)":
          reg["vertices"][6] == (lvl[m["vo"] + 4 + 72:m["vo"] + 16 + 72].hex(), 204, lvl[vp + 12 * 204:vp + 12 * 204 + 12].hex()),
          "twin 204 is the only visual vertex within 0.001 (next >= 1.0 away)": near[0] <= 0.001 and near[1] >= 1.0,
          "vertex 6 lies only on floor triangles (normal z >= 0.9), no wall / steep triangle": all(z >= 0.9 for z in nz6.values()),
          "new traversable triangle 1/2 = (6, 5, 7) outside start-floor-v1; adjacent via 1/3, 1/4":
              tuple(tris[(1, 2)]) == (6, 5, 7) and not set(tris[(1, 2)]) & {0, 2, 4}
              and set(star6) == {(1, 2), (1, 3), (1, 4)} and all(set(tris[t]) & {2, 4} for t in ((1, 3), (1, 4))),
          "start-floor-v1 unchanged (0 / 2 / 4)": list(rm.terrain_region(LEVEL, "start-floor-v1")["vertices"]) == [0, 2, 4]}
    det["o1"] = {"star6": {f"{a}/{b}": [list(star6[(a, b)]), round(nz6[(a, b)], 4)] for a, b in star6},
                 "twin_dist": [round(x, 5) for x in near]}
    O["O1"] = o1
    # O2 whole-deformation safety through the product path (parse -> terrain_spec -> collision_edit) + independent check
    o2, d2 = {}, {}
    for n, gs in REPR.items():
        t0 = time.perf_counter()
        canon = rm.parse_terrain_patch(v2patch([(g, dz) for g, dz in gs]), "o2")
        eds = rm.collision_edit(lvl, ptr, LEVEL, rm.terrain_spec(canon), "o2")
        new = bytearray(lvl)
        for off, dd, _ in eds:
            new[off:off + len(dd)] = dd
        ok, f, _, z = g22.geometry(lvl, bytes(new), {v: dz for g, dz in gs for v in g})
        d2[n] = {"ranges": len(eds), "ring": [f["collision_ring"], f["visual_ring"]], "nz_min": f["ring_normal_z_min"],
                 "box_margin_z": min(f["bound_margins_z_below"].values()), "octree_new": f["octree_new_unlisted"],
                 "z": z, "s": round(time.perf_counter() - t0, 1)}
        o2[f"{n}: compiler accepts, independent geometry ok, rings paired, no new octree pair"] = (
            ok and f["collision_ring"] == f["visual_ring"] and not f["octree_new_unlisted"])
    try:   # the reason for the cap, through the same independent checker on the raw edit
        sp = rm.terrain_spec(rm.parse_terrain_patch(v2patch([([6], -0.20), ([0], -0.05)]), "cap"))
        sp["groups"][0]["dz"] = -0.25
        eds = rm.collision_edit(lvl, ptr, LEVEL, sp, "cap")
        new = bytearray(lvl)
        for off, dd, _ in eds:
            new[off:off + len(dd)] = dd
        ok25 = g22.geometry(lvl, bytes(new), {6: -0.25, 0: -0.05})[0]
    except rm.Refusal:
        ok25 = False
    o2["cap evidence: vertex 6 at -0.25 fails the independent checker (D-266 scalar class); the schema refuses it"] = (
        ok25 is False and g24.cli(["level-patch", str(_write(WORK / "v6_025.json", BASIN_LP, -0.25)), "--check"],
                                  extra=("--json",))[1].get("code") == "UNSUPPORTED")
    det["o2"] = d2
    O["O2"] = o2
    # O3 declarative authoring through the CLI
    o3 = {}
    rc, r, _ = g24.cli(["level-patch", str(BASIN_LP), "--check"], extra=("--json",))
    rct, txt, _ = g24.cli(["level-patch", str(BASIN_LP), "--check"])
    pv = r.get("preview", {})
    rc_t, rt, _ = g24.cli(["terrain-patch", str(BASIN)], extra=("--json",))
    o3["west-basin level patch: --check exit 0, edits triangle 1/2 (outside start-floor-v1)"] = (
        rc == rct == 0 and "1/2" in pv["terrain"]["collision_triangle_ids"])
    o3["preview: standing prediction unchanged -25.0779 and says no moved vertex changes it"] = (
        pv["standing"]["predicted_settled_z"] == -25.0779 and pv["standing"]["moved_vertices_on_probe_triangle"] == []
        and "none of the moved vertices changes his height" in txt)
    o3["preview: region start-floor-v2, vertex-6 range shown, vertex-6 limitation, runtime OBSERVED (G6-P27)"] = (
        pv["terrain"]["region"] == "start-floor-v2" and "(vertex 6: 0.05..0.20)" in txt
        and any("vertex 6" in x for x in pv["limitations"]) and pv["evidence"]["runtime"].startswith("OBSERVED"))   # G6-P27 run m1 (was UNTESTED until E-516)
    o3["standalone terrain-patch of the same terrain: exit 0, its ranges = the level patch's terrain ranges"] = (
        rc_t == 0 and rt.get("range_count") == r.get("terrain_ranges"))
    det["o3"] = {"tx": r.get("transaction", {}).get("id"), "ranges": [r.get("range_count"), r.get("terrain_ranges")],
                 "triangles": pv.get("terrain", {}).get("collision_triangle_ids"), "text": txt}
    O["O3"] = o3
    # O4 combined resource: compile -> import -> plan in private folders -> independent combined checker
    o4 = {}
    w = WORK / "walk"
    if w.exists():
        shutil.rmtree(w)
    priv = ("--mods-root", str(w / "mods"), "--cache", str(w / "cache"))
    rc1, _, _ = g24.cli(["level-patch", str(BASIN_LP), "--out", str(w / "mod")], extra=("--json",))
    rc2, _, _ = g24.cli(["import", str(w / "mod"), "--enable"], extra=("--json", *priv))
    rc3, r3, _ = g24.cli(["plan"], extra=("--json", *priv))
    text = (w / "cache" / rm.PLAN_NAME).read_text(encoding="utf-8") if rc3 == 0 else ""
    mid = json.loads(BASIN_LP.read_text(encoding="utf-8"))["id"]
    tcanon = rm.parse_terrain_patch(json.loads(BASIN.read_text(encoding="utf-8")), "b") if text else None
    with g24.p1.dev_env(LEVEL):
        fc = g22.combined_check(text, "a", mid, {k: v for k, v in tcanon.items() if k != "description"}) if text else {}
    txs = g24.p1.parse_plan(text)["txs"] if text else []
    o4["compile / import / plan: one level-tx = the preview's transaction"] = (
        rc1 == rc2 == rc3 == 0 and txs == [f"level-tx 2 {LEVEL} {mid} {det['o3']['tx']}"])
    o4["independent combined checker (final_check + geometry) ok; growth +2,892 / +408 / 0 as before"] = (
        bool(fc.get("ok")) and r.get("growth") == {"lvl": 2892, "ptr": 408, "transit": 0})
    det["o4"] = {"txs": txs, "combined": {k: v for k, v in fc.items() if not isinstance(v, dict)}}
    O["O4"] = o4
    # O5 backward compatibility and refusal
    o5 = {}
    for n, tx in KNOWN.items():
        rc, r, _ = g24.cli(["level-patch", str(EX / n), "--check"], extra=("--json",))
        o5[f"{n}: tx {tx} unchanged"] = rc == 0 and r["transaction"]["id"] == tx
    base = json.loads(BASIN_LP.read_text(encoding="utf-8"))
    bad = {"vertex 6 in start-floor-v1": ("UNSUPPORTED", lambda d: d["components"][1]["patch"].update(region="start-floor-v1")),
           "vertex 9 in start-floor-v2": ("UNSUPPORTED", lambda d: d["components"][1]["patch"]["groups"][0].update(vertices=[9])),
           "vertex 6 raised": ("UNSUPPORTED", lambda d: d["components"][1]["patch"]["groups"][0].update(delta_z=0.1)),
           "five groups": ("BAD_MANIFEST", lambda d: d["components"][1]["patch"].update(groups=[
               {"name": f"g{i}", "vertices": [v], "delta_z": -0.1} for i, v in enumerate((0, 2, 4, 6, 9))]))}
    for n, (code, f) in bad.items():
        d = json.loads(json.dumps(base))
        f(d)
        p = WORK / f"bad_{n.replace(' ', '_')}.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        rc, r, _ = g24.cli(["level-patch", str(p), "--out", str(WORK / "bad_out")], extra=("--json",))
        o5[f"refused: {n} ({code}), nothing written"] = rc == 2 and r.get("code") == code and not (WORK / "bad_out").exists()
        # G6-P65 (D-314): the production scope (gate off) enforces the same region and bounds
        rc_p, rp, _ = g24.cli(["level-patch", str(p), "--out", str(WORK / "bad_out")], gate=None, extra=("--json",))
        o5[f"gate off: {n} refused identically, nothing written"] = (
            rc_p == 2 and (rp.get("code"), rp.get("detail")) == (r.get("code"), r.get("detail"))
            and not (WORK / "bad_out").exists())
    # G6-P65 (D-314): was "gate off: refused (UNSUPPORTED)", stale since D-286 (G6-P30) made start-floor terrain +
    # FairyLight graph A production content. The west-basin (start-floor-v2) now validates with the gate off, with the
    # transaction of the gated compile; its graph B variant stays development-only and is refused.
    rc, r, _ = g24.cli(["level-patch", str(BASIN_LP), "--check"], gate=None, extra=("--json",))
    pv = r.get("preview", {}) if isinstance(r, dict) else {}
    o5["gate off: west-basin (start-floor-v2 + FairyLight graph A, D-286) validates, tx 9083786df631a5a3, "
       "production-eligible"] = (
        rc == 0 and r["transaction"]["id"] == "9083786df631a5a3" and r.get("development_only") is False
        and pv.get("production", {}).get("eligible") is True)
    d = json.loads(json.dumps(base))
    d["components"][0]["follow_graph_of"] = 1
    p = WORK / "gate_off_graph_b.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    rc_p, rp, _ = g24.cli(["level-patch", str(p), "--out", str(WORK / "bad_out")], gate=None, extra=("--json",))
    rc_d, _, _ = g24.cli(["level-patch", str(p), "--check"], extra=("--json",))
    o5["gate off: the same terrain with the FairyLight on graph B is refused as development-only (valid gated)"] = (
        rc_p == 2 and rp.get("code") == "UNSUPPORTED" and "only the FairyLight on graph A" in rp.get("detail", "")
        and not (WORK / "bad_out").exists() and rc_d == 0)
    st = subprocess_run([sys.executable, "-I", str(ROOT / "tools" / "r3hd_mods.py"), "selftest"])
    o5["selftest PASS"] = st.strip().splitlines()[-1].startswith("R3HD_MODS_SELFTEST PASS")
    det["selftest"] = st.strip().splitlines()[-1]
    gate = subprocess_run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"]).strip()
    o5["development gate production; binaries unchanged"] = gate == "production" and g24.identity_ok()
    O["O5"] = o5
    det["elapsed_s"] = round(time.perf_counter() - t_start, 1)
    res = {"pass": all(all(v.values()) for v in O.values()), "checks": O, "details": det}
    (WORK / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"pass": res["pass"], "checks": O, "elapsed_s": det["elapsed_s"]}, indent=1))
    return 0 if res["pass"] else 1


def subprocess_run(cmd):
    import subprocess
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout


def _write(path, src, dz6):
    d = json.loads(src.read_text(encoding="utf-8"))
    next(g for g in d["components"][1]["patch"]["groups"] if 6 in g["vertices"])["delta_z"] = dz6
    path.write_text(json.dumps(d), encoding="utf-8")
    return path


if __name__ == "__main__":
    import g6p24_authoring_ux as _g24
    cmd = _g24.take_identity(sys.argv[1:])     # G6-P64 (D-313): --identity / --bin for the O5 identity row
    if cmd == ["study"]:
        sys.exit(study())
    if cmd == ["check"]:
        sys.exit(check())
    raise SystemExit(__doc__)
