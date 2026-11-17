#!/usr/bin/env python3
"""E-511 (D-278) G6-P22: declarative intro_20 terrain authoring + level-patch integration. Offline; private outputs.

    g6p22_intro20_terrain.py sweep   Phase A: every grid combination of region start-floor-v1 (vertices 0 / 2 / 4, 2-3
                                     groups, delta_z -0.30..-0.05 step 0.05) through the compiler's whole-deformation
                                     validator AND the independent geometry checker below; agreement required
    g6p22_intro20_terrain.py check   O1-O5 (schema, R1 / R2 / R3 reference equivalence, the authored terrain, combined
                                     final-image integrity, atomicity / refusals / regressions)
Outputs: private/work/e511/ (numbers only).

The independent geometry checker (`geometry`) takes the original files, a final image and the declared displacements
{collision vertex: dz}; it never reads compiler ranges. Visual twins are found by distance (exactly one visual vertex
of object 0xBA80 within 0.001 of each moved collision vertex); the words an edit may change are derived from the mesh
structure (moved vertex words, face normals of triangles touching them, edge normals / scalars of their edge slots,
visual face normals of visual triangles touching the twins); every other byte of the original file must be
unchanged; whole-mesh face / edge rules, octree membership, bounds, ground steepness and visual / collision agreement
are re-checked (the G6-P19 O2 model, parameterized). The expected settled z of Rayman is the probe-l1 standing height
offset by the change of the collision surface under his settled (x, y) (same method as G6-P19 / G6-P20).
"""
import itertools
import json
import math
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import r3hd_mods as rm  # noqa: E402
import g6p20_fairy_terrain as g20  # noqa: E402
import g6p21_level_patch as g21  # noqa: E402

g3, p1, g19, h = g20.g3, g20.p1, g20.g19, g20.h
ROOT, TOOLS, GAME = g20.ROOT, g20.TOOLS, g20.GAME
WORK = ROOT / "private" / "work" / "e511"
LEVEL, REGION = "intro_20", "start-floor-v1"
EX = HERE / "level_patch_examples"
ALLOWED = (0, 2, 4)
GRID = (-0.30, -0.25, -0.20, -0.15, -0.10, -0.05)


def jdump(name, obj):
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / name).write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")


def doc(name):
    return json.loads((EX / name).read_text(encoding="utf-8"))


def tpatch(groups, name="t"):
    lvl, _ = g19.files()
    return {"format": rm.TERRAIN_FORMAT, "level": LEVEL, "lvl_sha256": rm.sha256_bytes(lvl), "region": REGION,
            "name": name, "groups": [{"name": f"g{i}", "vertices": list(vs), "delta_z": dz}
                                     for i, (vs, dz) in enumerate(groups)]}


def moved_of(patch):
    return {v: float(g["delta_z"]) for g in patch["groups"] for v in g["vertices"]}


# ------------------------------------------------------------------------------------------- independent geometry check
def geometry(lvl, new, moved):
    """Independent check of a terrain edit on image `new` (same length or longer than `lvl`) against the declared
    {collision vertex: dz}. Returns (ok, facts, allowed byte set, expected settled z)."""
    import g6p16_multi_surface as p16
    import g6p17_terrain as p17
    L, m0 = g19.mesh(lvl)
    L2, m2 = g19.mesh(new)
    vp = L.ptr(g19.VOBJ - 4) + 4
    V0, V1 = g19.visual(lvl), g19.visual(new)
    vis_used = sorted({q for _, idx in V0.values() for q in idx})
    twins = {}
    for c in moved:
        near = [v for v in vis_used if math.dist(struct.unpack_from(">3f", lvl, vp + 12 * v), m0["verts"][c]) < 0.001]
        twins[c] = near
    f = {"twins": twins, "one visual twin per moved vertex": all(len(v) == 1 for v in twins.values())}
    twin = {c: v[0] for c, v in twins.items() if len(v) == 1}
    # expected vertex values (float32 of original + dz), collision and visual
    exp_ok = True
    for c, dz in moved.items():
        x, y, z = m0["verts"][c]
        exp_ok &= tuple(m2["verts"][c]) == (x, y, rm._f32(z + dz))
        if c in twin:
            vx, vy, vz = struct.unpack_from(">3f", lvl, vp + 12 * twin[c])
            exp_ok &= struct.unpack_from(">3f", new, vp + 12 * twin[c]) == (vx, vy, rm._f32(vz + dz))
    f["moved vertices = float32(original + declared dz)"] = exp_ok
    f["no other collision vertex moved"] = all(m2["verts"][k] == m0["verts"][k] for k in range(m0["nv"]) if k not in moved)
    # allowed words, from the mesh structure
    allowed = set()
    for c in moved:
        allowed.update(range(m0["vo"] + 4 + 12 * c, m0["vo"] + 16 + 12 * c))
        if c in twin:
            allowed.update(range(vp + 12 * twin[c], vp + 12 * twin[c] + 12))
    ring = set()
    for ei, e in enumerate(m0["elems"]):
        if e.get("type") != 1:
            continue
        b = e["blk"]
        mp, u1, u2 = L.ptr(b + 0x14), L.ptr(b + 0x18), L.ptr(b + 0x1C)
        mapping = struct.unpack_from(f">{3 * e['nt']}H", lvl, mp + 4)
        for j in range(e["nt"]):
            if set(moved) & set(e["idx"][3 * j:3 * j + 3]):
                ring.add((ei, j))
                allowed.update(range(e["nrm"] + 4 + 12 * j, e["nrm"] + 16 + 12 * j))
                for s_ in mapping[3 * j:3 * j + 3]:
                    allowed.update(range(u1 + 4 + 12 * s_, u1 + 16 + 12 * s_))
                    allowed.update(range(u2 + 4 + 4 * s_, u2 + 8 + 4 * s_))
    ed_vis = set(twin.values())
    vring = [(k, t) for k, (_, idx) in V0.items() for t in range(len(idx) // 3) if set(idx[3 * t:3 * t + 3]) & ed_vis]
    for k, t in vring:
        el = L.ptr(L.ptr(g19.VOBJ - 4 + 0x14) + 4 * k)
        a = L.ptr(el + 0x14) + 4 + 12 * t
        allowed.update(range(a, a + 12))
    diff = {i for i in range(len(lvl)) if lvl[i] != new[i]}
    f["changed bytes in the original file"] = len(diff)
    f["every change inside the derived words"] = diff <= allowed
    f["derived words"] = len(allowed)
    # whole-mesh rules, octree, bounds, steepness, visual agreement (G6-P19 O2 model)
    fe, ee, se, classes, excess = h.integrity(L2, new, m2)
    fe0, ee0, se0, classes0, excess0 = h.integrity(L, lvl, m0)
    cover, leaves, root = g19.octree_cover(L2, new, m2)
    cover0, _, _ = g19.octree_cover(L, lvl, m0)
    boxes = {"octree root": (L.f32s(root, 3), L.f32s(root + 12, 3)),
             "IPO +0x38": (struct.unpack_from(">3f", lvl, g19.IPO_BOX), struct.unpack_from(">3f", lvl, g19.IPO_BOX + 12)),
             "IPO +0x34": (struct.unpack_from(">3f", lvl, g19.IPO_BOX - 24),
                           struct.unpack_from(">3f", lvl, g19.IPO_BOX - 12)),
             "copy": (struct.unpack_from(">3f", lvl, g19.BOX_COPY), struct.unpack_from(">3f", lvl, g19.BOX_COPY + 12))}
    margins_z = {n: round(min(m2["verts"][k][2] - lo[2] for k in moved), 4) for n, (lo, hi) in boxes.items()}
    margins = {n: round(min(min(m2["verts"][k][i] - lo[i], hi[i] - m2["verts"][k][i]) for k in moved for i in range(3)), 4)
               for n, (lo, hi) in boxes.items()}
    tp = lambda m, t: [m["verts"][q] for q in m["elems"][t[0]]["idx"][3 * t[1]:3 * t[1] + 3]]   # noqa: E731
    nz = {t: (rm._face(*tp(m0, t))[2], rm._face(*tp(m2, t))[2]) for t in ring}
    ground_ok = all(b >= 0.9 for a, b in nz.values() if a >= 0.9) and all(a * b > 0 for a, b in nz.values())
    agree = max(math.dist(struct.unpack_from(">3f", new, vp + 12 * twin[c]), m2["verts"][c]) for c in twin) if twin else 9
    fn_err = 0.0
    for k, t in vring:
        el = L2.ptr(L2.ptr(g19.VOBJ - 4 + 0x14) + 4 * k)
        pts = [struct.unpack(">3f", c) for c in V1[k][0][3 * t:3 * t + 3]]
        fn_err = max(fn_err, math.dist(rm._face(*pts), struct.unpack_from(">3f", new, L2.ptr(el + 0x14) + 4 + 12 * t)))
    amb = p17.ambiguous_scalars(L, L2, lvl, m0)
    amb_ok = all(x["coplanar_orig"] and x["new"][0] == 1.0 and x["rule_gap"] <= 1e-3 for x in amb)
    div = []
    for img_v, m_ in ((V0, m0), (V1, m2)):
        worst = 0.0
        for k, t in vring:
            pts = [struct.unpack(">3f", c) for c in img_v[k][0][3 * t:3 * t + 3]]
            for lb in ((1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6)):
                p = [sum(lb[i] * pts[i][c] for i in range(3)) for c in range(3)]
                s_ = [z for _, z, _ in p16.surface(m_, p[0], p[1]) if abs(z - p[2]) < 1.0]
                if s_:
                    worst = max(worst, min(abs(z - p[2]) for z in s_))
        div.append(round(worst, 4))
    S = g19.SETTLED_L1
    h0, h1 = p16.surface(m0, *S[:2]), p16.surface(m2, *S[:2])
    settled = round(h1[0][1] + (S[2] - h0[0][1]), 4) if h0 and h1 else None
    f.update({"face_err": fe, "edge_err": ee, "scalar_one_err": se, "classes": classes, "classes_original": classes0,
              "octree_new_unlisted": sorted(cover - cover0), "bound_margins_z_below": margins_z,
              "collision_ring": len(ring), "visual_ring": len(vring),
              "ring_normal_z_min": round(min(b for _, b in nz.values()), 4) if nz else None, "ground_ok": ground_ok,
              "visual_on_collision_max": agree, "visual_face_err": fn_err, "ambiguous_scalars_ok": amb_ok,
              "divergence_orig_mod": div, "spawn_surface_dz": round(h1[0][1] - h0[0][1], 4) if h0 and h1 else None,
              "spawn_triangle": h1[0][0] if h1 else None, "expected_settled_z": settled})
    ok = (f["one visual twin per moved vertex"] and exp_ok and f["no other collision vertex moved"]
          and f["every change inside the derived words"] and fe <= max(fe0, 2.5e-5) and ee < 2e-6 and se < 2e-6
          and excess <= max(excess0, 0) and classes["one"] == classes0["one"] and classes["other"] == classes0["other"]
          and amb_ok and cover <= cover0 and not {t for _, t in cover} & ring and min(margins.values()) > 0
          and min(margins_z.values()) > 0.05 and ground_ok and agree < 0.001 and fn_err < 1e-6
          and len(ring) == len(vring) and div[1] <= div[0] + 0.30 and h1 and h1[0][0] == (1, 11))
    f["ok"] = bool(ok)
    return bool(ok), f, allowed, settled


# ------------------------------------------------------------------------------------------------- Phase A sweep
def configs():
    """Every assignment of a subset of {0, 2, 4} to 2-3 groups (as a set partition) and every grid dz per group."""
    seen = set()
    for r in (2, 3):
        for verts in itertools.combinations(ALLOWED, r):
            for labels in itertools.product(range(3), repeat=r):
                parts = {}
                for v, l_ in zip(verts, labels):
                    parts.setdefault(l_, []).append(v)
                groups = tuple(sorted(tuple(p) for p in parts.values()))
                if len(groups) < 2 or groups in seen:
                    continue
                seen.add(groups)
                for dzs in itertools.product(GRID, repeat=len(groups)):
                    yield list(zip(groups, dzs))


def sweep():
    lvl, ptr = g19.files()
    rows, agree, comp_ok, ind_ok = [], True, 0, 0
    lo_z = []
    with p1.dev_env(LEVEL):
        for cfg in configs():
            patch = tpatch(cfg)
            try:
                canon = rm.parse_terrain_patch(patch, "sweep")
                eds = rm.collision_edit(lvl, ptr, LEVEL, rm.terrain_spec(canon), "sweep")
                c_ok, why = True, None
            except rm.Refusal as x:
                c_ok, why, eds = False, f"{x.code}: {x.detail[-90:]}", None
            i_ok = None
            if eds is not None:
                ok, f, _, z = geometry(lvl, h.apply(lvl, eds), moved_of(patch))
                i_ok = ok
                lo_z.append((f["ring_normal_z_min"], z))
            agree &= (c_ok == bool(i_ok))
            comp_ok += c_ok
            ind_ok += bool(i_ok)
            rows.append({"groups": [[list(g), dz] for g, dz in cfg], "compiler": c_ok, "independent": i_ok,
                         "refusal": why})
    res = {"configurations": len(rows), "compiler accepts": comp_ok, "independent accepts": ind_ok,
           "compiler == independent on every configuration": agree,
           "min ring normal z over accepted": min(a for a, _ in lo_z) if lo_z else None,
           "expected settled z range": [min(z for _, z in lo_z), max(z for _, z in lo_z)] if lo_z else None,
           "refused": [r for r in rows if not r["compiler"]][:20]}
    jdump("sweep.json", {"summary": res, "rows": rows})
    print(json.dumps(res, indent=1))
    return res


# ------------------------------------------------------------------------------------------------- combined final image
def combined_check(text, sel, mid, tpatch_canon):
    """G6-P20's final_check (fairy part: G6-P3 independent constructor + simulator; transaction lines re-derived)
    pointed at the declared terrain (its expected dz come from the declaration; its byte set from the STANDALONE
    terrain-patch compile, not from the combined compile), plus the independent geometry check on the combined image
    against the constructor's fairy-only image (every difference must be a derived terrain word)."""
    key = "__g6p22_check"
    spec = rm.terrain_spec(tpatch_canon)
    old = (g20.SEL, g20.MID, g20.PRESET, g20.terrain_edits)
    lvl, ptr = g19.files()
    rm.COLLISION_ALLOW[LEVEL]["presets"][key] = spec
    g20.SEL, g20.MID, g20.PRESET = sel, mid, key
    g20.terrain_edits = lambda: rm.collision_edit(lvl, ptr, LEVEL, spec, "standalone")
    try:
        out = g20.final_check(text)
    finally:
        g20.SEL, g20.MID, g20.PRESET, g20.terrain_edits = old
        del rm.COLLISION_ALLOW[LEVEL]["presets"][key]
    m = p1.parse_plan(text)
    img = p1.images(m)
    L_ = img.get(f"{LEVEL}.lvl")
    data, ptr_, tl = g3.files()
    cl, _, _, _ = g3.construct(data, ptr_, tl, sel)
    moved = {v: g["delta_z"] for g in tpatch_canon["groups"] for v in g["vertices"]}
    if L_ is None or len(L_) != len(cl):
        out["independent geometry ok"] = False
        out["ok"] = False
        return out
    ok, f, allowed, z = geometry(cl[:len(data)], L_[:len(data)], moved)
    tail_same = L_[len(data):] == cl[len(data):]
    out["independent geometry (combined vs fairy-only image)"] = {k: f[k] for k in (
        "changed bytes in the original file", "every change inside the derived words", "face_err", "edge_err",
        "octree_new_unlisted", "ring_normal_z_min", "collision_ring", "visual_ring", "expected_settled_z")}
    out["independent geometry ok"] = ok and tail_same
    out["expected_settled_z"] = z
    out["ok"] = all(v for k, v in out.items() if isinstance(v, bool))
    return out


# ------------------------------------------------------------------------------------------------- offline O1-O5
def check():
    WORK.mkdir(parents=True, exist_ok=True)
    g3.WORK = WORK
    p1.WORK = WORK
    O, det = {}, {}
    P = {"game": GAME}
    ref = lambda fn, code, env=LEVEL: g3.refused(fn, code, env)   # noqa: E731
    TP = HERE / "terrain_patches"
    T_ref = json.loads((TP / "intro20-start-two-step.json").read_text(encoding="utf-8"))
    T_dip = json.loads((TP / "intro20-west-dip.json").read_text(encoding="utf-8"))
    LR, LD = doc("g6p22_reference_patch.json"), doc("g6p22_west_dip_fairy.json")
    A21, B21 = doc("g6p20_reference.json"), doc("graph_b.json")
    lvl, ptr = g19.files()
    tmp = WORK / "cli"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    # O1 schema and resource validation
    o1 = {}
    for name, f_, args in (("terrain reference", TP / "intro20-start-two-step.json", "terrain-patch"),
                           ("terrain west-dip", TP / "intro20-west-dip.json", "terrain-patch"),
                           ("level patch reference", EX / "g6p22_reference_patch.json", "level-patch"),
                           ("level patch west-dip", EX / "g6p22_west_dip_fairy.json", "level-patch")):
        rc, out = g21.cli([args, str(f_)], LEVEL, tmp / name.replace(" ", "_"))
        det[f"cli {name}"] = out
        o1[f"CLI compiles {name} (exit 0, mod folder written)"] = rc == 0 and (
            tmp / name.replace(" ", "_") / "mod.json").is_file()
    g0 = T_ref["groups"]
    tb = {
        "format v2": (dict(T_ref, format="terrain-patch-v2"), "UNSUPPORTED"),
        "unknown key (offset)": (dict(T_ref, offset=4096), "BAD_MANIFEST"),
        "missing key (region)": ({k: v for k, v in T_ref.items() if k != "region"}, "BAD_MANIFEST"),
        "wrong lvl hash": (dict(T_ref, lvl_sha256="0" * 64), "TARGET_CHANGED"),
        "unknown region": (dict(T_ref, region="spawn-ground-v1"), "UNSUPPORTED"),
        "other level (intro_10)": (dict(T_ref, level="intro_10"), "UNSUPPORTED"),
        "vertex 9 (slope-limited corner)": (dict(T_ref, groups=[g0[0], dict(g0[1], vertices=[2, 9])]), "UNSUPPORTED"),
        "vertex 1 (wall bottom)": (dict(T_ref, groups=[g0[0], dict(g0[1], vertices=[1])]), "UNSUPPORTED"),
        "vertex 10 (no visual twin)": (dict(T_ref, groups=[g0[0], dict(g0[1], vertices=[10])]), "UNSUPPORTED"),
        "duplicate vertex": (dict(T_ref, groups=[g0[0], dict(g0[1], vertices=[0, 2])]), "BAD_MANIFEST"),
        "delta_z -0.35 (too deep)": (dict(T_ref, groups=[dict(g0[0], delta_z=-0.35), g0[1]]), "UNSUPPORTED"),
        "delta_z +0.05 (raise)": (dict(T_ref, groups=[dict(g0[0], delta_z=0.05), g0[1]]), "UNSUPPORTED"),
        "delta_z string": (dict(T_ref, groups=[dict(g0[0], delta_z="-0.2"), g0[1]]), "BAD_MANIFEST"),
        "vertex as bool": (dict(T_ref, groups=[dict(g0[0], vertices=[True]), g0[1]]), "BAD_MANIFEST"),
        "one group": (dict(T_ref, groups=[dict(g0[0], vertices=[0, 2, 4])]), "BAD_MANIFEST"),
        "four groups": (dict(T_ref, groups=[g0[0], dict(g0[1], vertices=[2]), dict(g0[1], name="c", vertices=[4]),
                                            dict(g0[1], name="d", vertices=[2])]), "BAD_MANIFEST"),
        "duplicate group name": (dict(T_ref, groups=[g0[0], dict(g0[1], name=g0[0]["name"])]), "BAD_MANIFEST"),
        "group key (normal)": (dict(T_ref, groups=[dict(g0[0], normal=[0, 0, 1]), g0[1]]), "BAD_MANIFEST"),
    }
    neg = {}
    for i, (name, (p, code)) in enumerate(tb.items()):
        f_ = tmp / f"tbad_{i}.json"
        f_.write_text(json.dumps(p), encoding="utf-8")
        rc, out = g21.cli(["terrain-patch", str(f_)], LEVEL, tmp / f"out_tbad_{i}")
        neg[f"terrain: {name}"] = rc == 2 and out.get("code") == code and not (tmp / f"out_tbad_{i}").exists()
    f_ = tmp / "tbad_nan.json"
    f_.write_text(json.dumps(T_ref).replace("-0.3", "NaN", 1), encoding="utf-8")
    rc, out = g21.cli(["terrain-patch", str(f_)], LEVEL, tmp / "out_tbad_nan")
    neg["terrain: NaN delta_z"] = rc == 2 and out.get("code") == "BAD_MANIFEST" and not (tmp / "out_tbad_nan").exists()
    tc, fc = LR["components"][0], LR["components"][1]
    lb = {
        "terrain with preset AND patch": (dict(LR, components=[dict(tc, preset="start-two-step-v1"), fc]),
                                          "BAD_MANIFEST"),
        "patch not an object": (dict(LR, components=[dict(tc, patch="west-dip"), fc]), "BAD_MANIFEST"),
        "embedded description": (dict(LR, components=[dict(tc, patch=dict(tc["patch"], description="x")), fc]),
                                 "BAD_MANIFEST"),
        "embedded intro_15 patch": (dict(LR, components=[dict(tc, patch={k: v for k, v in json.loads(
            (TP / "shallow-bowl.json").read_text(encoding="utf-8")).items() if k != "description"}), fc]),
                                    "UNSUPPORTED"),
        "embedded unsupported vertex": (dict(LR, components=[dict(tc, patch=dict(tc["patch"], groups=[
            tc["patch"]["groups"][0], dict(tc["patch"]["groups"][1], vertices=[9])])), fc]), "UNSUPPORTED"),
        "embedded wrong lvl hash": (dict(LR, components=[dict(tc, patch=dict(tc["patch"], lvl_sha256="0" * 64)), fc]),
                                    "TARGET_CHANGED"),
        "embedded too deep": (dict(LR, components=[dict(tc, patch=dict(tc["patch"], groups=[
            dict(tc["patch"]["groups"][0], delta_z=-0.4), tc["patch"]["groups"][1]])), fc]), "UNSUPPORTED"),
        "two terrain components": (dict(LR, components=[tc, {"type": "terrain", "preset": "start-two-step-v1"}, fc]),
                                   "BAD_MANIFEST"),
        "terrain only": (dict(LR, components=[tc]), "BAD_MANIFEST"),
        "two fairylights": (dict(LR, components=[tc, fc, dict(fc, follow_graph_of=1)]), "BAD_MANIFEST"),
        "graph 2": (dict(LR, components=[tc, dict(fc, follow_graph_of=2)]), "UNSUPPORTED"),
    }
    for i, (name, (p, code)) in enumerate(lb.items()):
        f_ = tmp / f"lbad_{i}.json"
        f_.write_text(json.dumps(p), encoding="utf-8")
        rc, out = g21.cli(["level-patch", str(f_)], LEVEL, tmp / f"out_lbad_{i}")
        neg[f"level patch: {name}"] = rc == 2 and out.get("code") == code and not (tmp / f"out_lbad_{i}").exists() \
            and ref(lambda p=p: rm.compile_level_patch(p, P), code) is True
    o1["refusals (CLI exit 2, expected code, no output folder; library refuses the same)"] = all(neg.values())
    det["O1_refusals"] = neg
    O["O1"] = all(o1.values())
    det["O1"] = o1

    # O2 reference equivalence R1 / R2 / R3
    o2 = {}
    ct_ref, r_tref = rm.compile_terrain_patch(T_ref, P)
    r_pre = rm.compile_collision_vertex_offset(g19.op(), P)
    o2["R1 terrain: (file, offset, bytes, order) = G6-P19 preset, 50 ranges / 512 bytes"] = (
        [(a, b, c) for a, b, c, _ in r_tref] == [(a, b, c) for a, b, c, _ in r_pre] and len(r_tref) == 50
        and sum(len(c) for _, _, c, _ in r_tref) == 512)
    o2["R1 terrain: labels differ only in the prefix (terrain.<name> vs collision.<preset>), same word names"] = all(
        a[3].split(" ", 1)[1] == b[3].split(" ", 1)[1] for a, b in zip(r_tref, r_pre))
    o2["R1 terrain: compiler spec = preset spec"] = rm.terrain_spec(ct_ref) == rm.COLLISION_ALLOW[LEVEL]["presets"][
        "start-two-step-v1"]
    img_ref = h.apply(lvl, [(o, d, w) for _, o, d, w in r_tref])
    ok_r1, f_r1, _, z_r1 = geometry(lvl, img_ref, moved_of(T_ref))
    o2["R1 terrain: independent geometry ok; expected settled z = G6-P19 -25.2668"] = ok_r1 and len(img_ref) == len(
        lvl) and abs(z_r1 - g20.EXPECTED_Z) < 1e-4
    det["R1_geometry"] = f_r1
    res_r, text_r, _ = g21.plan("g6p22_r2", LR)
    ref_text = g21.REF_PLAN.read_text(encoding="utf-8")
    br, bref = g21.body(text_r), g21.body(ref_text)
    o2["R2 plan = retained G6-P20 run plan (all lines incl. labels; blobs by content)"] = br == bref
    if br != bref:
        det["R2_plan_diff"] = [(x, y) for x, y in zip(br, bref) if x != y][:6] + [("lengths", len(br), len(bref))]
    m_r = p1.parse_plan(text_r)
    o2["R2 level-tx = 2 intro_20 g6p20.fairy-terrain 1b1f404eaf81a240; member results = G6-P20"] = (
        m_r["txs"] == [f"level-tx 2 {LEVEL} g6p20.fairy-terrain {g21.REF_ID}"]
        and {f["tx"][0].split(" ")[0]: f["tx"][0].split(" ")[3] for f in m_r["files"]} == g21.REF_RESULTS)
    with p1.dev_env(LEVEL):
        _, r_lr, tx_lr = rm.compile_level_patch(LR, P)
        r_fix, tx_fix = rm.compile_insert_fairy_with_terrain(g20.op(), P)
    o2["R2 ranges and transaction = fixed G6-P20 operation (63 ranges, images, files)"] = (
        r_lr == r_fix and len(r_lr) == 63 and tx_lr["images"] == tx_fix["images"] and tx_lr["files"] == tx_fix["files"])
    r3 = {}
    for name, d_, want_id, want_ident in ((("reference", A21, g21.REF_ID,
                                            "48308548d66bc90bd2e1dbb19edc69531f214d7aec418e6d1be5b5d0aa0ffe21")),
                                          ("graph B", B21, "3cdb5be5ebafc590",
                                           "b2205eba84e1ff8bdc389a625333a5522c93848fa6b9fea50e6f80fbe2e63289")):
        with p1.dev_env(LEVEL):
            c_, r_, tx_ = rm.compile_level_patch(d_, P)
        r3[name] = (rm.level_patch_identity(c_) == want_ident
                    and rm.transaction_summary(d_["id"], tx_)["id"] == want_id)
    _, text_a21, _ = g21.plan("g6p21_ref_again", A21)
    r3["reference plan = retained run plan"] = g21.body(text_a21) == bref
    o2["R3 G6-P21 declarations: identities and transaction ids unchanged (A 1b1f404e…, B 3cdb5be5…)"] = all(r3.values())
    det["R3"] = r3
    O["O2"] = all(o2.values())
    det["O2"] = o2

    # O3 the authored terrain (standalone)
    o3 = {}
    ct_dip, r_dip = rm.compile_terrain_patch(T_dip, P)
    img_dip = h.apply(lvl, [(o, d, w) for _, o, d, w in r_dip])
    ok3, f3, _, z3 = geometry(lvl, img_dip, moved_of(T_dip))
    det["west_dip_geometry"] = f3
    o3["west-dip: independent geometry ok (twins, derived words, face / edge rules, octree, bounds, slope)"] = ok3
    o3["west-dip: deterministic (two compiles equal)"] = rm.compile_terrain_patch(T_dip, P)[1] == r_dip
    T_dip2 = dict(T_dip, groups=list(reversed(T_dip["groups"])))
    T_dip2.pop("description")
    o3["west-dip: group order / description do not change the output"] = rm.compile_terrain_patch(T_dip2, P)[1] == r_dip
    o3["west-dip: distinct from start-two-step-v1 (bytes and identity)"] = img_dip != img_ref and rm.terrain_identity(
        ct_dip) != rm.terrain_identity(ct_ref)
    o3["west-dip: same-size, lvl only, ranges inside the original file"] = len(img_dip) == len(lvl) and all(
        Path(p_).name == f"{LEVEL}.lvl" and o + len(d) <= len(lvl) for p_, o, d, _ in r_dip)
    z_pre = g20.EXPECTED_Z
    o3["west-dip: predicted settled z differs from start-two-step-v1 by >= 0.05"] = z3 is not None and abs(
        z3 - z_pre) >= 0.05
    det["west_dip_prediction"] = {"expected_settled_z": z3, "start_two_step_expected": z_pre,
                                  "probe_l1_original": round(g19.SETTLED_L1[2], 4), "ranges": len(r_dip),
                                  "bytes": sum(len(d) for _, _, d, _ in r_dip),
                                  "identity": rm.terrain_identity(ct_dip)}
    O["O3"] = all(o3.values())
    det["O3"] = o3

    # O4 combined final image (authored terrain + FairyLight; graph A, plus graph B variant)
    o4 = {}
    res_d, text_d, _ = g21.plan("g6p22_dip", LD)
    m_d = p1.parse_plan(text_d) if text_d else None
    fd = combined_check(text_d, "a", LD["id"], ct_dip) if text_d else {"ok": False}
    det["final_dip_a"] = fd
    o4["combined west-dip + graph A: final_check + independent geometry pass"] = bool(fd.get("ok"))
    with p1.dev_env(LEVEL):
        cd_, r_d, tx_d = rm.compile_level_patch(LD, P)
    o4["63 ranges (13 fairy + 50 terrain); growth +2892 / +408 / 0"] = len(r_d) == 63 and sum(
        ".terrain." in r[3] for r in r_d) == 50 and {k: len(tx_d["images"][k]) - tx_d["files"][k][1] for k in
                                                       ("lvl", "ptr", "transit")} == {"lvl": 2892, "ptr": 408,
                                                                                       "transit": 0}
    o4["fairy part = G6-P20's (ptr / transit images equal; fairy ranges equal)"] = (
        tx_d["images"]["ptr"] == tx_fix["images"]["ptr"] and tx_d["images"]["transit"] == tx_fix["images"]["transit"]
        and [r for r in r_d if ".terrain." not in r[3]] == [r for r in r_fix if ".terrain." not in r[3]])
    o4["terrain ranges = standalone west-dip (offset, bytes, order)"] = [(o, d) for _, o, d, w in r_d if ".terrain." in w] \
        == [(o, d) for _, o, d, _ in r_dip]
    sd = rm.transaction_summary(LD["id"], tx_d)
    o4["distinct transaction id and lvl result from G6-P20; ptr / transit results equal"] = (
        sd["id"] != g21.REF_ID and sd["members"]["lvl"]["result_sha256"] != g21.REF_RESULTS["lvl"]
        and sd["members"]["ptr"]["result_sha256"] == g21.REF_RESULTS["ptr"]
        and sd["members"]["transit"]["result_sha256"] == g21.REF_RESULTS["transit"])
    o4["plan level-tx = summary id"] = m_d is not None and m_d["txs"] == [f"level-tx 2 {LEVEL} {LD['id']} {sd['id']}"]
    det["dip_tx"] = sd
    det["dip_identity"] = rm.level_patch_identity(cd_)
    LDb = dict(LD, id="g6p22.custom-terrain-fairy-b", components=[{"type": "fairylight", "follow_graph_of": 1},
                                                                  LD["components"][1]])
    _, text_db, _ = g21.plan("g6p22_dip_b", LDb)
    fdb = combined_check(text_db, "b", LDb["id"], ct_dip) if text_db else {"ok": False}
    det["final_dip_b"] = {k: v for k, v in fdb.items() if not isinstance(v, dict)}
    o4["combined west-dip + graph B: final_check + independent geometry pass"] = bool(fdb.get("ok"))
    li = next(i for i, f in enumerate(m_d["files"]) if f["path"].endswith(f"{LEVEL}.lvl"))
    ter = {o for _, o, _, _ in r_dip}
    cdir = WORK / "corrupt"
    if cdir.exists():
        shutil.rmtree(cdir)
    cdir.mkdir(parents=True)

    def corrupt(fn, sel="a", canon=ct_dip):
        m = json.loads(json.dumps(m_d))
        fn(m)
        return not combined_check(p1.emit(m), sel, LD["id"], canon).get("ok")

    def flip(m, pick):
        for k, r in enumerate(m["files"][li]["range"]):
            off, length, gb, nb, mid, blob = r.split(" ", 5)
            if pick(int(off)):
                b = bytearray(Path(blob).read_bytes())
                b[0] ^= 1
                q = cdir / f"blob_{off}.bin"
                q.write_bytes(bytes(b))
                m["files"][li]["range"][k] = " ".join([off, length, gb, nb, mid, str(q)])
                return
    o4["corrupted terrain byte refused"] = corrupt(lambda m: flip(m, lambda o: o in ter))
    o4["corrupted fairy word refused"] = corrupt(lambda m: flip(m, lambda o: o not in ter and o < g3.SIZE))
    o4["dropped terrain range refused"] = corrupt(lambda m: m["files"][li].update(
        range=[r for r in m["files"][li]["range"] if int(r.split(" ")[0]) != min(ter)]))
    o4["missing transit member refused"] = corrupt(lambda m: m["files"].pop(
        next(i for i, f in enumerate(m["files"]) if f["path"].endswith("transit.lvl"))))
    o4["corrupted transaction id refused"] = corrupt(lambda m: m.update(
        txs=[m["txs"][0][:-1] + ("0" if m["txs"][0][-1] != "0" else "1")]))
    o4["west-dip plan judged against the start-two-step declaration refused"] = corrupt(lambda m: None, canon=ct_ref)
    o4["west-dip plan judged as graph B refused"] = corrupt(lambda m: None, sel="b")
    O["O4"] = all(o4.values())
    det["O4"] = o4

    # O5 atomicity, refusal, regressions
    o5 = {}
    tpo = {"type": "terrain-patch", "patch": T_dip}
    lpo = {"type": "level-patch", "patch": LD}

    def man(mid, *ovs):
        return lambda: rm.parse_manifest({"mod.json": json.dumps(p1.manifest(mid, list(ovs))).encode()})
    o5["level-patch + terrain-patch / fixed composition / fairy / preset / second level-patch refused"] = all(
        ref(man(LD["id"], lpo, x), "BAD_MANIFEST") is True for x in (tpo, g20.op(), g3.fairy("a"), g19.op(), lpo))
    o5["standalone intro_20 terrain-patch mod parses alone; with a fairy refused (D-274)"] = (
        ref(man("t.t", tpo), "BAD_MANIFEST") is False and ref(man("t.t", tpo, g3.fairy("a")), "BAD_MANIFEST") is True)
    o5["level-patch whose id is not the mod id refused"] = ref(man("t.other", lpo), "BAD_MANIFEST") is True
    for args, f_ in (("level-patch", EX / "g6p22_west_dip_fairy.json"), ("terrain-patch", TP / "intro20-west-dip.json")):
        rc, out = g21.cli([args, str(f_)], None, tmp / f"out_prod_{args}")
        o5[f"{args} CLI without the gate refused, nothing written"] = rc == 2 and out.get("code") == "UNSUPPORTED" \
            and not (tmp / f"out_prod_{args}").exists()
        rc, out = g21.cli([args, str(f_)], "intro_15", tmp / f"out_other_{args}")
        o5[f"{args} CLI with the gate naming intro_15 refused, nothing written"] = rc == 2 and out.get(
            "code") == "UNSUPPORTED" and not (tmp / f"out_other_{args}").exists()
    o5["manifests without the gate refused"] = ref(man(LD["id"], lpo), "UNSUPPORTED", env=None) is True and ref(
        man("t.t", tpo), "UNSUPPORTED", env=None) is True
    rp = p1.fresh("refused")
    with p1.dev_env(LEVEL):
        bad = dict(LD, id="t.bad", components=[LD["components"][0], dict(LD["components"][1], patch=dict(
            LD["components"][1]["patch"], groups=[dict(LD["components"][1]["patch"]["groups"][0], delta_z=-0.31),
                                                  *LD["components"][1]["patch"]["groups"][1:]]))])
        try:
            p1.install(rp, "t.bad", [{"type": "level-patch", "patch": bad}])
            imported = True
        except rm.Refusal as x:
            imported = x.code
        r2 = rm.resolve_all(rp, write_plan=rp["cache"])
    o5["refused level-patch import: no plan, no active mod"] = imported == "UNSUPPORTED" \
        and not (rp["cache"] / rm.PLAN_NAME).is_file() and not r2.get("active")
    o5["CLI --out mod.json (west-dip) plans identically to the direct declaration"] = False
    mjp = tmp / "level_patch_west-dip" / "mod.json"
    if mjp.is_file() and text_d:
        mj = json.loads(mjp.read_text(encoding="utf-8"))
        _, text_c, _ = g3.compile_plan("cli_mod", [(mj["id"], mj["overrides"])])
        o5["CLI --out mod.json (west-dip) plans identically to the direct declaration"] = text_c is not None \
            and g21.body(text_c) == g21.body(text_d)
    for name in ("shallow-bowl", "east-tilt"):   # G6-P17 intro_15 patches unchanged
        old_env = os.environ.get(rm.STRUCT_ENV)
        os.environ[rm.STRUCT_ENV] = "intro_15"
        try:
            c15, r15 = rm.compile_terrain_patch(json.loads((TP / f"{name}.json").read_text(encoding="utf-8")), P)
            if name == "shallow-bowl":
                pre = rm.collision_edit((GAME / "GAMEDATAbin/intro_15/intro_15.lvl").read_bytes(),
                                        (GAME / "GAMEDATAbin/intro_15/intro_15.ptr").read_bytes(), "intro_15",
                                        rm.COLLISION_ALLOW["intro_15"]["presets"]["spawn-multi-surface-v1"], "p")
                o5["G6-P17 intro_15 shallow-bowl = spawn-multi-surface-v1 bytes"] = [(o, d) for _, o, d, _ in r15] == \
                    [(o, d) for o, d, _ in pre]
            else:
                o5["G6-P17 intro_15 east-tilt still compiles"] = len(r15) > 0
        finally:
            if old_env is None:
                os.environ.pop(rm.STRUCT_ENV, None)
            else:
                os.environ[rm.STRUCT_ENV] = old_env
    o5["intro_15 region refuses intro_20 vertex numbers"] = g3.refused(lambda: rm.parse_terrain_patch(
        dict(json.loads((TP / "shallow-bowl.json").read_text(encoding="utf-8")), groups=T_dip["groups"]), "x"),
        "UNSUPPORTED", "intro_15") is True
    _, txs = g3.compiled("a")
    data, ptr_, tl = g3.files()
    o5["standalone fairy (graph A) = independent constructor"] = (txs["images"]["lvl"], txs["images"]["ptr"],
                                                                  txs["images"]["transit"]) == g3.construct(
        data, ptr_, tl, "a")[:3]
    st = subprocess.run([sys.executable, "-I", str(TOOLS / "r3hd_mods.py"), "selftest"], cwd=ROOT, capture_output=True,
                        text=True)
    o5["r3hd_mods selftest"] = st.stdout.strip().splitlines()[-1] if st.stdout.strip() else st.stderr[-200:]
    o5["selftest pass"] = "PASS" in o5["r3hd_mods selftest"]
    O["O5"] = all(v for v in o5.values() if isinstance(v, bool))
    det["O5"] = o5

    res = {"O": O, "pass": all(O.values()), "details": det}
    (WORK / "offline.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({"O": O, "pass": res["pass"]}, indent=1))
    for k in ("O1", "O2", "O3", "O4", "O5"):
        for n, v in det[k].items():
            if v is False:
                print("FAIL", k, n)
    for n, v in det["O1_refusals"].items():
        if v is not True:
            print("FAIL O1 refusal", n)
    for k in ("final_dip_a", "final_dip_b"):
        for n, v in det[k].items():
            if v is False:
                print("FAIL", k, n)
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sweep":
        sweep()
    elif cmd == "check":
        with p1.dev_env(LEVEL):
            sys.exit(check())
    else:
        print(__doc__)
        sys.exit(2)
