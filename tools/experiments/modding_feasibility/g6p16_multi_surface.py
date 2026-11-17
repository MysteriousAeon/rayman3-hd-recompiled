"""G6-P16 (D-271 / E-504): multi-surface playable environment edit on intro_15 (development only).

    python -I tools/experiments/modding_feasibility/g6p16_multi_surface.py check      offline O1-O5
    python -I tools/experiments/modding_feasibility/g6p16_multi_surface.py validate   render rule on retained G6-P15 data
    python -I tools/experiments/modding_feasibility/g6p16_multi_surface.py run TAG    one hidden traced run, then judge
    python -I tools/experiments/modding_feasibility/g6p16_multi_surface.py judge TAG

Preset `spawn-multi-surface-v1` (tools/r3hd_mods.py): a two-step shallow bowl around the spawn point. Group A, the
spawn triangle's vertices 365 / 392 / 393, is lowered 0.30; group B, the adjacent ground vertices 387 / 388 / 391 / 394,
is lowered 0.15. 25 collision triangles (elements 2 and 3) and their 25 visual counterparts (visual object 0x15C74,
elements 0 and 14; one visual twin per moved vertex) change with their derived data. Everything stays inside every known
bound, with no octree or box words.

PROTOCOL (committed before the modified run; thresholds are not changed after results)
Run: one hidden run `e504_<tag>_ms_trace` (the M22 rule needs `*_trace`). Same runner, entry (--test-level intro_15),
230 s and private profile as G6-P15, plus R3HD_M22_DRAW_TRACE=1. Steps: frame a at 120 s, frame b at 140 s (2 explicit
readbacks, cap 8), then from 150 s four slow forward walks (left stick ly +11469 = length 0.35, about 2.1 units/s, E-233;
0.8 s each, 4 s apart) through the existing scoped XAM schedule. The camera looks south (forward (0.24, -0.95), retained
traces), so the walks cross the bowl from the spawn triangle towards vertex 382. References (retained, same executable,
level files, entry, no input before the frames, same frame schedule): R1 e502_v1_ref and R2 e502_d1_ref_trace (collision
preset spawn-small-drop-0.30, original visual). Rayman idles at the same spawn point in all of them (the spawn triangle
is lowered 0.30 in all three), so the frame comparisons happen before any input.
Observed: Rayman's position and behaviour every 0.2 s; every preset range read back at discovery and at the last sample.
Criteria (judged separately):
  P1 delivery: the run serves exactly its plan's ranges (123).
  P2 guest geometry: corrected judge (D-267): every preset range reads as the original file with the plan applied, at
     both reads.
  P3 GPU draw: in both frames, the element-14 draw (240 corners, stride 32) and the element-0 draw (1,593, stride 24) are
     present with corner positions equal to the modified visual geometry in element order. Against R1's frame with the
     same label, exactly the corners that use the 7 edited visual vertices differ, and every other byte is equal.
  P4 playable physics, from the samples (surface height h = the plane of the collision triangle under (x, y), modified
     h_mod or original h_orig; "ring" = the 25 edited collision triangles):
     (a) the idle settled z (G6-P13 summary window) is within 0.02 of -9.40416, with spread <= 0.02;
     (b) after the walks Rayman has moved >= 2.0 units (x, y) from the settled point (not stuck);
     (c) stops = runs of >= 5 consecutive samples moving <= 0.01 each (after the first move of > 0.3). >= 2 stops at
         least 0.5 apart lie in the ring; every in-ring stop has |z - h_mod| <= 0.03; at least one in-ring stop lies
         where 0.05 <= |h_mod - h_orig| <= 0.27 (a surface other than the uniform -0.30 spawn triangle) with
         |z - h_orig| >= 0.05;
     (d) no sample over the ring has z < h_mod - 0.10, and no sample is below -10.5 (no fall-through or sinking);
     (e) the last sample's behaviour is YAM_C_Attente, and sampling ran to the end without stopping.
     (a), (b) and (d) failing = physical failure; only (c) with too few stops = insufficient traversal.
  P5 framebuffer attribution, the G6-P15b Method A (g6p15b_render_attribution: barycentric samples, step 1/12, of the
     25 edited visual triangles; each frame's own element-14 / element-0 draw constants; the same edge, frame and
     Rayman-box filters; discriminative = original and modified projections under the run's camera >= 2 px apart).
     For both labels and both references (V = this run):
       (i) >= 100 discriminative samples;
       (ii) among samples with e_mod != e_orig, fraction(e_mod < e_orig) >= 0.70, one-sided binomial p < 1e-6;
       (iii) camera-matched noise (G6-P15b lesson, D-270): T = Q90 of e_aware = V at (p, V camera) vs Rk at (p, Rk
            camera) over the same sampling of the UNCHANGED triangles of elements 0 and 14, i.e. the same pair and the
            same camera difference. It needs >= 100 samples and T >= 1; otherwise the comparison is DEGENERATE and P5
            cannot pass. Pass if median(e_mod) <= T and median(e_orig) > T.
     Control (per label): R2 vs R1 under the edit's hypothesis, fraction(e_ctrl_mod < e_ctrl) <= 0.5 on the
     discriminative samples.
     Occlusion: only Rayman is masked (no depth buffer). Clipping: projections with w <= 0 or off frame are dropped.
     Fog: per-vertex, depth dependent, not modelled; it is part of the measured errors. Camera differences: each
     observation uses its own frame's constants.
  P6 safety: M21 / M22 / M23 = 0, runner exit 0, no process left, no other level opened, fault lines <= G6-P13 g1 base,
     haptics policy line, gameplay line (achievements not awarded).
Classes: P1-P6 PASS -> VERIFIED. P1-P4 and P6 PASS with P5 not passing -> PARTIAL (geometry and physics verified,
render unverified). P5 PASS with P4 insufficient traversal -> PARTIAL (render verified, playability unverified).
P2 / P3 FAIL or a P4 physical failure -> EXPERIMENT FAILED. Invalid (the run may be repeated once, unchanged): level not
opened, Rayman not found, a traced frame missing, or a draw absent from a frame. Not used as evidence: same-screen-pixel
differences; any synthetic projection on its own.
"""
import argparse
import copy
import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g6p13_collision as h  # noqa: E402
import g6p15b_render_attribution as pb  # noqa: E402

rm, ROOT, LEVEL = h.rm, h.ROOT, h.LEVEL
PRESET, P16, CASE = "spawn-multi-surface-v1", "e504", "ms_trace"
A_GROUP, B_GROUP = (365, 392, 393), (387, 388, 391, 394)
TWIN = {365: 1134, 392: 1187, 393: 1188, 387: 1181, 388: 1182, 391: 1186, 394: 1189}
EDITED_VIS = set(TWIN.values())
RING_COLL = {(2, t) for t in (45, 52, 57, 187, 188, 205, 206, 207, 208, 209, 210)} | {
    (3, t) for t in (2, 6, 7, 33, 34, 39, 40, 49, 52, 53, 54, 55, 56, 57)}
STICK = 11469
STEPS = ("wait 120\nframe a\nwait 20\nframe b\nwait 10\n"
         + f"axis 301 {STICK}\nwait 0.8\naxis 301 0\nwait 4\n" * 4 + "wait 36\n")
REFS = {"R1": "e502_v1_ref", "R2": "e502_d1_ref_trace"}
SETTLED_Z = -9.40416
OUT = ROOT / "private" / "work" / P16


def edits(lvl=None, ptr=None, spec=None, check_files=True):
    return h.edits(PRESET, lvl, ptr, spec, check_files)


def mesh(img):
    import m25_mesh_audit as m25
    import g6p12_collision_file_audit as g6
    L = m25.Level(LEVEL)
    L.b = img
    return L, g6.parse_mesh(L, rm.COLLISION_ALLOW[LEVEL]["zdr"] - 4)


def surface(m, x, y, ring=None):
    """[(triangle, z of its plane at (x, y), normal z)] of upward collision triangles under (x, y)."""
    out = []
    for ei, e in enumerate(m["elems"]):
        for j in range(e["nt"]):
            if ring is not None and (ei, j) not in ring:
                continue
            a, b, c = (m["verts"][q] for q in e["idx"][3 * j:3 * j + 3])
            den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(den) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / den
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / den
            l3 = 1 - l1 - l2
            n = rm._face(a, b, c)
            if min(l1, l2, l3) >= -1e-6 and n and n[2] > 0.5:
                out.append(((ei, j), l1 * a[2] + l2 * b[2] + l3 * c[2], n[2]))
    return out


def octree_cover(L2, new, m2):
    """Every leaf lists every triangle that intersects its cell (modified geometry)."""
    tris = [(ei, j) for ei, e in enumerate(m2["elems"]) for j in range(e["nt"])]
    tp = {t: [m2["verts"][q] for q in m2["elems"][t[0]]["idx"][3 * t[1]:3 * t[1] + 3]] for t in tris}
    tb = {t: ([min(p[i] for p in v) for i in range(3)], [max(p[i] for p in v) for i in range(3)]) for t, v in tp.items()}
    root = L2.ptr(L2.ptr(rm.COLLISION_ALLOW[LEVEL]["zdr"] - 4 + 0x14))
    stack, cover, leaves = [root], True, 0
    while stack:
        nd = stack.pop()
        kids, lst = L2.ptr(nd + 0x18), L2.ptr(nd + 0x1C)
        if kids is not None:
            stack += [L2.ptr(kids + 4 * q) for q in range(8) if L2.ptr(kids + 4 * q) is not None]
            continue
        leaves += 1
        lo, hi = L2.f32s(nd, 3), L2.f32s(nd + 12, 3)
        items = set()
        if lst is not None:
            cnt, p = struct.unpack_from("<H", new, lst + 4)[0], lst + 6
            for _ in range(cnt):
                el, x = new[p], new[p + 1]
                tr, p = (((x & 0x7F) << 8) | new[p + 2], p + 3) if x & 0x80 else (x, p + 2)
                items.add((el, tr))
        exact = {t for t in tris if all(tb[t][0][i] <= hi[i] + 1e-4 and tb[t][1][i] >= lo[i] - 1e-4 for i in range(3))
                 and rm._tri_box(tp[t], lo, hi)}
        cover &= exact <= items
    return cover, leaves, root


def visual_tris(img):
    """{(element, triangle): (index triple, [3 positions])} for visual elements 0 and 14 (file image)."""
    import m25_mesh_audit as m25
    L = m25.Level(LEVEL)
    L.b = img
    go = 0x15C74 - 4
    vp, ep = L.ptr(go), L.ptr(go + 0x14)
    out = {}
    for k in (0, 14):
        el = L.ptr(ep + 4 * k)
        nt = struct.unpack_from(">H", img, el + 8)[0]
        idx = struct.unpack_from(f">{3 * nt}H", img, L.ptr(el + 0xC) + 4)
        for t in range(nt):
            tri = idx[3 * t:3 * t + 3]
            out[(k, t)] = (tri, [struct.unpack_from(">3f", img, vp + 4 + 12 * q) for q in tri])
    return out


# ------------------------------------------------------------------------------------------------- offline O1-O5
def check():
    res, (lvl, ptr) = {}, h.files()
    allow = rm.COLLISION_ALLOW[LEVEL]
    spec = allow["presets"][PRESET]
    eds = edits()
    L, m0 = mesh(lvl)
    new = h.apply(lvl, eds)
    L2, m2 = mesh(new)
    vo = m0["vo"] + 4
    go = 0x15C74 - 4
    vp = L.ptr(go) + 4
    ring = {(ei, j) for ei, e in enumerate(m0["elems"]) for j in range(e["nt"])
            if set(TWIN) & set(e["idx"][3 * j:3 * j + 3])}
    vis0, vis1 = visual_tris(lvl), visual_tris(new)
    vring = {k for k, (tri, _) in vis0.items() if set(tri) & EDITED_VIS}
    twin_d = {c: math.dist(struct.unpack_from(">3f", lvl, vp + 12 * v), m0["verts"][c]) for c, v in TWIN.items()}
    res["O1 source and mapping"] = {
        "hashes": (len(lvl), rm.sha256_bytes(lvl)) == allow["lvl"] and (len(ptr), rm.sha256_bytes(ptr)) == allow["ptr"],
        "collision originals": all(lvl[vo + 12 * k:vo + 12 * k + 12].hex() == w
                                   for g in spec["groups"] for k, w in g["vertices"].items()),
        "visual originals": all(lvl[vp + 12 * v:vp + 12 * v + 12].hex() == w for v, (w, _) in spec["visual"]["map"].items()),
        "twin distance max": max(twin_d.values()), "collision ring": len(ring), "visual ring": len(vring),
        "visual ring by element": {k: sum(1 for e, _ in vring if e == k) for k in (0, 14)}}
    res["O1 source and mapping"]["ok"] = (
        res["O1 source and mapping"]["hashes"] and res["O1 source and mapping"]["collision originals"]
        and res["O1 source and mapping"]["visual originals"] and max(twin_d.values()) < 0.001 and ring == RING_COLL
        and len(vring) == 25)
    # O2 multi-surface geometry integrity
    fe, ee, se, classes, excess = h.integrity(L2, new, m2)
    fe0, ee0, se0, classes0, excess0 = h.integrity(L, lvl, m0)
    cover, leaves, root = octree_cover(L2, new, m2)
    moved = [k for k in range(m2["nv"]) if m2["verts"][k] != m0["verts"][k]]
    dzs = {k: round(m2["verts"][k][2] - m0["verts"][k][2], 5) for k in moved}
    boxes = {"octree root": (L.f32s(root, 3), L.f32s(root + 12, 3)),
             "IPO +0x38": (L.f32s(0x159450, 3), L.f32s(0x159450 + 12, 3)),
             "IPO +0x34": (L.f32s(0x159438, 3), L.f32s(0x159438 + 12, 3)),
             "copy 0x378180": (L.f32s(0x37817C, 3), L.f32s(0x37817C + 12, 3)),
             "sector +0x34": (L.f32s(0x378164, 3), L.f32s(0x378164 + 12, 3)),
             "sector +0x38": (L.f32s(0x37817C, 3), L.f32s(0x37817C + 12, 3))}
    margins = {n: round(min(min(m2["verts"][k][i] - lo[i], hi[i] - m2["verts"][k][i]) for k in moved for i in range(3)), 4)
               for n, (lo, hi) in boxes.items()}
    tp = lambda m, t: [m["verts"][q] for q in m["elems"][t[0]]["idx"][3 * t[1]:3 * t[1] + 3]]   # noqa: E731
    nz = {t: (rm._face(*tp(m0, t))[2], rm._face(*tp(m2, t))[2]) for t in ring}
    ground_ok = all(b >= 0.9 for a, b in nz.values() if a >= 0.9) and all(a * b > 0 for a, b in nz.values())
    # visual / collision agreement: every edited visual vertex sits on its moved collision twin; visual ring triangles
    # whose three corners are twins of one collision ring triangle (identical surfaces)
    inv = {v: c for c, v in TWIN.items()}
    agree = max(math.dist(struct.unpack_from(">3f", new, vp + 12 * v), m2["verts"][c]) for c, v in TWIN.items())
    vis_face = 0.0
    for k in vring:
        tri, pts = vis1[k]
        vis_face = max(vis_face, math.dist(rm._face(*pts), struct.unpack_from(
            ">3f", new, L.ptr(L.ptr(L.ptr(go + 0x14) + 4 * k[0]) + 0x14) + 4 + 12 * k[1])))
    # profile along the walk line (expected shape): heights at y = 56 .. 50.5
    prof = []
    for y in (56.4, 55, 54, 53, 52, 51, 50.5):
        x = -95.896 + 0.255 * (56.433 - y)
        a, b = surface(m0, x, y), surface(m2, x, y)
        if a and b:
            prof.append({"y": y, "tri": a[0][0], "h_orig": round(a[0][1], 4), "h_mod": round(b[0][1], 4),
                         "dz": round(b[0][1] - a[0][1], 4)})
    # edge-scalar class (unresolved rule, D-266): a shared edge whose original faces were coplanar satisfies both
    # rules (1.0 = min-dot); the compiler keeps 1.0. Allowed class changes: only such edges, and the min-dot
    # alternative must stay within 1e-3 of the kept 1.0
    amb = []
    for ei, e in enumerate(m0["elems"]):
        b = e["blk"]
        mp, u1, u2 = L.ptr(b + 0x14), L.ptr(b + 0x18), L.ptr(b + 0x1C)
        mapping = struct.unpack_from(f">{3 * e['nt']}H", lvl, mp + 4)
        mem = {}
        for j in range(e["nt"]):
            for c_ in range(3):
                mem.setdefault(mapping[3 * j + c_], []).append(j)
        for s_, js in mem.items():
            if len(js) < 2:
                continue
            st = []
            for LL in (L, L2):
                fn = [LL.f32s(e["nrm"] + 12 * j, 3) for j in js]
                en, sc = LL.f32s(u1 + 12 * s_, 3), LL.f32s(u2 + 4 * s_, 1)[0]
                md = min(sum(f[i] * en[i] for i in range(3)) for f in fn)
                st.append((sc, md, "min" if abs(sc - md) < 2e-6 else "kept" if sc == 1.0 else "other"))
            if st[0][2] != st[1][2]:
                amb.append({"element": ei, "slot": s_, "orig": st[0], "new": st[1],
                            "coplanar_orig": abs(st[0][1] - 1.0) < 2e-6 and st[0][0] == 1.0,
                            "rule_gap": round(1.0 - st[1][1], 7)})
    amb_ok = all(x["coplanar_orig"] and x["new"][0] == 1.0 and x["rule_gap"] <= 1e-3 for x in amb)
    res["O2 multi-surface geometry"] = {
        "ambiguous_edge_scalars": amb,
        "moved": dzs, "face_err": fe, "edge_err": ee, "scalar_one_err": se, "classes": classes,
        "classes_original": classes0, "sphere_excess": excess, "octree_leaves": leaves, "octree_cover": cover,
        "bound_margins": margins, "ring_normal_z_min": round(min(b for _, b in nz.values()), 4),
        "ground_ok": ground_ok, "visual_on_collision_max": agree, "visual_face_err": vis_face, "walk_profile": prof}
    res["O2 multi-surface geometry"]["ok"] = (
        dzs == {**{k: -0.3 for k in A_GROUP}, **{k: -0.15 for k in B_GROUP}}
        or all(abs(dzs[k] - (-0.3 if k in A_GROUP else -0.15)) < 1e-5 for k in dzs) and sorted(dzs) == sorted(TWIN)) \
        and fe <= max(fe0, 2.5e-5) and ee < 2e-6 and se < 2e-6 and excess <= max(excess0, 0) \
        and classes["one"] == classes0["one"] and classes["other"] == classes0["other"] and amb_ok \
        and cover and min(margins.values()) > 0 and ground_ok and agree < 0.001 and vis_face < 1e-6
    # O3 combined edit integrity
    diff = [i for i in range(len(lvl)) if lvl[i] != new[i]]
    kinds = {}
    for _, _, w in eds:
        key = ("visual " if w.startswith("visual") else "") + w.split()[-1]
        kinds[key] = kinds.get(key, 0) + 1
    res["O3 combined edit"] = {
        "ranges": len(eds), "bytes": sum(len(d) for _, d, _ in eds), "kinds": kinds, "differing_bytes": len(diff),
        "ok": len(new) == len(lvl) and all(any(o <= i < o + len(d) for o, d, _ in eds) for i in diff)
              and not any("octree" in w or "box" in w for _, _, w in eds) and edits() == eds
              and all(a[0] + len(a[1]) <= b[0] for a, b in zip(eds, eds[1:]))
              and kinds.get("visual z") == 7 and kinds.get("z") == 7 and kinds.get("visual normal") == 25}

    # O4 negative cases
    def refused(fn, code="TARGET_CHANGED"):
        try:
            fn()
        except rm.Refusal as x:
            return x.code == code
        return False

    def mut(o, b):
        x = bytearray(lvl)
        x[o:o + len(b)] = b
        return bytes(x)

    def sp(f):
        s = copy.deepcopy(spec)
        f(s)
        return s
    ep = L.ptr(go + 0x14)
    fn14 = L.ptr(L.ptr(ep + 4 * 14) + 0x14) + 4
    other_v = 1190   # a visual vertex outside the map, moved onto collision vertex 387 (a crack)
    neg = {
        "wrong file hash": refused(lambda: edits(mut(0x100, b"\xAA"), ptr)),
        "group B collision original changed": refused(lambda: edits(mut(vo + 12 * 387 + 8, b"\xc1\x1a\x76\x39"), ptr, check_files=False)),
        "group B visual original changed": refused(lambda: edits(mut(vp + 12 * 1181 + 8, b"\xc1\x1a\x76\x3d"), ptr, check_files=False)),
        "vertex in two groups": refused(lambda: edits(lvl, ptr, sp(lambda s: s["groups"][1]["vertices"].update(
            {365: s["groups"][0]["vertices"][365]})), False)),
        "group displacement outside the guard (-0.35)": refused(lambda: edits(lvl, ptr, sp(lambda s: s["groups"][0].update(dz=-0.35)), False)),
        "collision ring mismatch (bad topology)": refused(lambda: edits(lvl, ptr, sp(lambda s: s.update(ring=24)), False)),
        "visual ring mismatch": refused(lambda: edits(lvl, ptr, sp(lambda s: s["visual"].update(ring=24)), False)),
        "visual map incomplete": refused(lambda: edits(lvl, ptr, sp(lambda s: s["visual"]["map"].pop(1189)), False)),
        "second visual vertex on a moved collision vertex (crack)": refused(lambda: edits(
            mut(vp + 12 * other_v, lvl[vp + 12 * 1181:vp + 12 * 1181 + 12]), ptr, check_files=False)),
        "unsafe bounds (IPO +0x38 min z above the bowl)": refused(lambda: edits(mut(0x159454 + 8, struct.pack(">f", -9.85)), ptr, check_files=False)),
        "too steep (ground limit 0.995; triangle 3/2 0.9956 -> 0.9931)": refused(
            lambda: edits(lvl, ptr, sp(lambda s: s.update(min_normal_z=0.995)), False)),
        "malformed visual face normal": refused(lambda: edits(mut(fn14 + 12 * 32, struct.pack(">3f", 0.0, 0.6, 0.8)), ptr, check_files=False)),
        "corrupted octree leaf list": refused(lambda: edits(h.corrupt_leaf(lvl, ptr), ptr, check_files=False)),
        "deterministic": edits() == eds,
    }
    os.environ[rm.STRUCT_ENV] = LEVEL
    try:
        neg["unknown preset"] = refused(lambda: rm.parse_collision_vertex_offset(h.op(PRESET + "x"), "o"), "UNSUPPORTED")
        neg["raw groups key in the manifest"] = refused(lambda: rm.parse_collision_vertex_offset(
            {**h.op(PRESET), "groups": []}, "o"), "BAD_MANIFEST")
        neg["two presets in one mod"] = refused(lambda: rm.parse_manifest({"mod.json": json.dumps(
            h.manifest("t.two", h.op(h.VISP), h.op(PRESET))).encode()}), "BAD_MANIFEST")
    finally:
        os.environ.pop(rm.STRUCT_ENV, None)
    res["O4 negative cases"] = {"cases": neg, "ok": all(neg.values())}
    # O5 regression and policy
    o5 = {"gate off refused": h.gate_off_refused(),
          "gameplay-affecting": rm.changes_game_logic({"overrides": [h.op(PRESET)]})}
    with tempfile.TemporaryDirectory(dir=ROOT / "private" / "work") as td:
        imps, pl = h.make_plan(Path(td) / "a", [h.manifest(f"{P16}.ms", h.op(PRESET))])
        o5["plan ok"] = pl.get("result") == "ok" and bool(pl.get("plan"))
        if o5["plan ok"]:
            h.plan_overlay(pl["plan"], PRESET)
            o5["plan gameplay record"] = f"\ngameplay {P16}.ms\n" in Path(pl["plan"]).read_text(encoding="utf-8")
            o5["plan ranges"] = len(h.plan_ranges(pl["plan"])[1])
        imps, pl = h.make_plan(Path(td) / "b", [h.manifest(f"{P16}.a", h.op(h.VISP)), h.manifest(f"{P16}.b", h.op(PRESET))])
        o5["conflicting second mod refused whole"] = len(pl.get("active", [])) == 1
        imps, pl = h.make_plan(Path(td) / "c", [h.manifest(f"{P16}.ng", h.op(PRESET))], env_extra={})
        o5["gate-off import refused"] = imps[0].get("result") != "ok"
    retained = [("e499/g1/mod", "spawn-drop-1.50"), ("e499/g1/control", "control-far-drop-1.50"),
                ("e500/s1/small", h.SMALL), ("e502/v1/ref", h.SMALL), ("e502/v1/vis", h.VISP)]
    for where, preset in retained:
        try:
            h.plan_overlay(json.loads((ROOT / "private" / "work" / where / "row.json").read_text())["plan"], preset)
            o5[f"{preset} byte-identical to {where} plan"] = True
        except SystemExit:
            o5[f"{preset} byte-identical to {where} plan"] = False
    o5["ok"] = all(v for v in o5.values() if isinstance(v, bool)) and o5.get("plan ranges") == len(eds)
    res["O5 regression and policy"] = o5
    verdict = {k: v["ok"] for k, v in res.items()}
    print(json.dumps(verdict, indent=1))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    return 0 if all(verdict.values()) else 1


# ------------------------------------------------------------------------------------------------- render (P5)
def attribution(vrun, mod_img, edited, refs=REFS, ray=pb.RAY):
    """The P5 rule (module docstring) for one modified run against two references; numbers and per-test verdicts."""
    import m22_draw_report as rep
    lvl, _ = h.files()
    orig, mod = h.visual_model(lvl), h.visual_model(mod_img)
    runs = {"V": vrun, **refs}
    cams, imgs, frames = {}, {}, {}
    for k, r in runs.items():
        fr = h._frames(r)
        frames[k] = [f[0] for f in fr]
        expect = mod if k == "V" else orig
        for li, (name, draws, bmp) in enumerate(fr):
            for el, shape in ((14, h.E14), (0, h.E0)):
                want = expect[el][0]
                hit = [d for d in h._find(draws, shape) if [d["bindings"][0]["data"][i * shape[1]:i * shape[1] + 12]
                                                            for i in range(len(want))] == want]
                if hit:
                    c = hit[0]["consts"]
                    cams[(k, li, el)] = [[rep.f32(c[r_ * 4 + j]) for j in range(4)] for r_ in range(4)]
            imgs[(k, li)] = h._pixels(bmp)[2]
    found = all((k, li, el) in cams for k in runs for li in (0, 1) for el in (14, 0)) and all(
        len(v) == 2 for v in frames.values())
    res = {"frames": frames, "cameras_found": found}
    if not found:
        res["class"] = "INVALID"
        return res

    def tris(model, el, ring=True):
        pos, idx = model[el]
        P = [struct.unpack(">3f", c) for c in pos]
        return [(t, P[3 * t:3 * t + 3]) for t in range(len(idx) // 3)
                if bool(set(idx[3 * t:3 * t + 3]) & edited) == ring]

    def ray_box(m):
        pts = [pb.project(m, (ray[0] + dx, ray[1] + dy, ray[2] + dz)) for dx in (-0.8, 0.8) for dy in (-0.8, 0.8)
               for dz in (0.0, 2.5)]
        pts = [p for p in pts if p]
        return (min(p[0] for p in pts) - 4, min(p[1] for p in pts) - 4, max(p[0] for p in pts) + 4,
                max(p[1] for p in pts) + 4) if pts else None

    def look(img, p):
        x, y = int(math.floor(p[0])), int(math.floor(p[1]))
        return img.get((x, y)) if 0 <= x < pb.W and 0 <= y < pb.H else None

    def err(a, b):
        return max(abs(a[i] - b[i]) for i in range(3))

    def valid(m, tri3, pt, box):
        sp = [pb.project(m, v) for v in tri3]
        if pt is None or any(s is None for s in sp) or not (0 <= pt[0] < pb.W and 0 <= pt[1] < pb.H):
            return False
        if pb.edge_dist(pt, [s[:2] for s in sp]) < 2:
            return False
        return not (box and box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3])

    def q(xs, f):
        s = sorted(xs)
        return s[min(len(s) - 1, int(f * len(s)))] if s else None
    S = pb.samples()
    tests, ctrl_ok = {}, {}
    for li in (0, 1):
        label = "ab"[li]
        boxes = {k: ray_box(cams[(k, li, 14)]) for k in runs}
        rows, unchanged = [], {"R1": [], "R2": []}
        for el in (14, 0):
            mV, m1, m2 = cams[("V", li, el)], cams[("R1", li, el)], cams[("R2", li, el)]
            mt = dict(tris(mod, el))
            for t, to in tris(orig, el):
                tm = mt[t]
                for lb in S:
                    po, pm = pb.bary(to, lb), pb.bary(tm, lb)
                    pV_m, pV_o = pb.project(mV, pm), pb.project(mV, po)
                    p1, p2, p2_m = pb.project(m1, po), pb.project(m2, po), pb.project(m2, pm)
                    if not (valid(mV, tm, pV_m, boxes["V"]) and valid(mV, to, pV_o, boxes["V"])
                            and valid(m1, to, p1, boxes["R1"]) and valid(m2, to, p2, boxes["R2"])
                            and valid(m2, tm, p2_m, boxes["R2"])):
                        continue
                    c = {n: look(imgs[(k, li)], p) for n, k, p in (("Vm", "V", pV_m), ("Vo", "V", pV_o),
                                                                   ("R1", "R1", p1), ("R2", "R2", p2),
                                                                   ("R2m", "R2", p2_m))}
                    if any(v is None for v in c.values()):
                        continue
                    rows.append({"disc": math.hypot(pV_m[0] - pV_o[0], pV_m[1] - pV_o[1]) >= 2,
                                 "e_mod1": err(c["Vm"], c["R1"]), "e_orig1": err(c["Vo"], c["R1"]),
                                 "e_mod2": err(c["Vm"], c["R2"]), "e_orig2": err(c["Vo"], c["R2"]),
                                 "e_ctrl": err(c["R2"], c["R1"]), "e_ctrl_mod": err(c["R2m"], c["R1"]),
                                 "shift_px": math.hypot(pV_m[0] - pV_o[0], pV_m[1] - pV_o[1])})
            # camera-matched noise: the unchanged triangles of the same element, same pair, same cameras
            for t, tt in tris(orig, el, ring=False):
                for lb in S:
                    p = pb.bary(tt, lb)
                    pv = pb.project(mV, p)
                    if not valid(mV, tt, pv, boxes["V"]):
                        continue
                    for rk, mk in (("R1", m1), ("R2", m2)):
                        pr = pb.project(mk, p)
                        if valid(mk, tt, pr, boxes[rk]):
                            a, b = look(imgs[("V", li)], pv), look(imgs[(rk, li)], pr)
                            if a and b:
                                unchanged[rk].append(err(a, b))
        D = [r for r in rows if r["disc"]]
        neq = [r for r in D if r["e_ctrl_mod"] != r["e_ctrl"]]
        frac_c = round(sum(r["e_ctrl_mod"] < r["e_ctrl"] for r in neq) / len(neq), 4) if neq else None
        ctrl_ok[label] = {"frac_ctrl_mod_better": frac_c, "ok": frac_c is not None and frac_c <= 0.5,
                          "median_ctrl": q([r["e_ctrl"] for r in D], 0.5)}
        for ref in ("1", "2"):
            rk = "R" + ref
            ne = [r for r in D if r["e_mod" + ref] != r["e_orig" + ref]]
            n, k = len(ne), sum(r["e_mod" + ref] < r["e_orig" + ref] for r in ne)
            p = pb.binom_tail(k, n) if n else 1.0
            T = q(unchanged[rk], 0.9)
            em, eo = q([r["e_mod" + ref] for r in D], 0.5), q([r["e_orig" + ref] for r in D], 0.5)
            t_ = {"disc_samples": len(D), "decisive": n, "mod_better": k, "frac": round(k / n, 4) if n else None,
                  "p_one_sided": p, "median_e_mod": em, "median_e_orig": eo, "unchanged_samples": len(unchanged[rk]),
                  "T_q90_unchanged": T, "median_unchanged": q(unchanged[rk], 0.5),
                  "median_shift_px": round(q([r["shift_px"] for r in D], 0.5), 2) if D else None}
            t_["i"] = len(D) >= 100
            t_["ii"] = n > 0 and k / n >= 0.70 and p < 1e-6
            t_["degenerate"] = len(unchanged[rk]) < 100 or T is None or T < 1
            t_["iii"] = not t_["degenerate"] and em is not None and em <= T and eo > T
            tests[f"{label}/{rk}"] = t_
    res.update({"tests": tests, "control": ctrl_ok})
    ok_c = all(v["ok"] for v in ctrl_ok.values())
    i_ii = all(t["i"] and t["ii"] for t in tests.values())
    iii = all(t["iii"] for t in tests.values())
    res["class"] = ("PASS" if ok_c and i_ii and iii else "SUPPORTED" if ok_c and i_ii else
                    "DEGENERATE" if any(t["degenerate"] for t in tests.values()) and ok_c and i_ii else "FAIL")
    return res


def validate():
    """The P5 rule on the retained G6-P15 data (V e502_v1_vis, R1, R2): method check, not a new verdict."""
    lvl, _ = h.files()
    r = attribution("e502_v1_vis", h.apply(lvl, h.edits(h.VISP)), {1134, 1187, 1188})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "validate.json").write_text(json.dumps(r, indent=1, default=str) + "\n")
    print(json.dumps({"class": r["class"], "control": r.get("control"),
                      "tests": {k: {x: v[x] for x in ("disc_samples", "frac", "median_e_mod", "median_e_orig",
                                                       "unchanged_samples", "T_q90_unchanged", "median_unchanged",
                                                       "degenerate", "ii", "iii")}
                                for k, v in r.get("tests", {}).items()}}, indent=1))
    return 0


# ------------------------------------------------------------------------------------------------- run and judge
def run(tag):
    exe = json.loads((h.RUNS / "e499_g1_base" / "run.json").read_text(encoding="utf-8-sig"))["executable_sha256"]
    cur = rm.sha256_bytes((ROOT / "private/work/rex/out/build/win-amd64-release/r3hd.exe").read_bytes())
    if exe != cur:
        raise SystemExit("the executable differs from the retained references'")
    return h.run_case(tag, CASE, prefix=P16, presets={CASE: PRESET}, read=(PRESET,), steps=STEPS,
                      extra_env={"R3HD_M22_DRAW_TRACE": "1"})


def traversal(samples, m0, m2):
    s = h.summarize(samples)
    ring_hits = lambda x, y: surface(m2, x, y, RING_COLL)   # noqa: E731
    res = {"settled": s.get("settled"), "settled_spread": s.get("settled_spread"), "attente_t": s.get("attente_t"),
           "behaviours": s.get("behaviours"), "samples": len(samples)}
    if not s.get("settled"):
        res["physical_fail"], res["why"] = True, "no settled position"
        return res
    st = s["settled"]
    first = next((i for i, x in enumerate(samples) if x["t"] > (s["attente_t"] or 0)
                  and math.dist(x["pos"][:2], st[:2]) > 0.3), None)
    moved = max((math.dist(x["pos"][:2], st[:2]) for x in samples[first:]), default=0.0) if first is not None else 0.0
    stops, i = [], first if first is not None else len(samples)
    while i < len(samples) - 4:
        j = i
        while j + 1 < len(samples) and math.dist(samples[j + 1]["pos"], samples[j]["pos"]) <= 0.01:
            j += 1
        if j - i + 1 >= 5:
            p = samples[(i + j) // 2]["pos"]
            hm = ring_hits(p[0], p[1])
            ho = surface(m0, p[0], p[1], RING_COLL)
            stops.append({"t": samples[i]["t"], "n": j - i + 1, "pos": [round(c, 5) for c in p],
                          "tri": hm[0][0] if hm else None, "h_mod": round(hm[0][1], 5) if hm else None,
                          "h_orig": round(ho[0][1], 5) if ho else None,
                          "z_minus_h_mod": round(p[2] - hm[0][1], 5) if hm else None,
                          "z_minus_h_orig": round(p[2] - ho[0][1], 5) if ho else None})
        i = j + 1
    ring_stops = [x for x in stops if x["tri"] is not None]
    distinct = []
    for x in ring_stops:
        if all(math.dist(x["pos"][:2], y["pos"][:2]) >= 0.5 for y in distinct):
            distinct.append(x)
    sink = []
    for x in samples:
        hm = ring_hits(x["pos"][0], x["pos"][1])
        if hm and x["pos"][2] < hm[0][1] - 0.10:
            sink.append(x)
    a = abs(st[2] - SETTLED_Z) <= 0.02 and (s["settled_spread"] or 0) <= 0.02
    b = moved >= 2.0
    c_fit = all(abs(x["z_minus_h_mod"]) <= 0.03 for x in ring_stops)
    c_mid = any(0.05 <= abs(x["h_mod"] - x["h_orig"]) <= 0.27 and abs(x["z_minus_h_orig"]) >= 0.05 for x in ring_stops)
    d = not sink and min(x["pos"][2] for x in samples) >= -10.5
    e = bool(samples) and samples[-1]["beh"] == "YAM_C_Attente"
    res.update({"moved_max": round(moved, 3), "stops": stops, "ring_stops_distinct": len(distinct),
                "sink_samples": len(sink), "min_z": round(min(x["pos"][2] for x in samples), 5),
                "a_settled": a, "b_moved": b, "c_enough_stops": len(distinct) >= 2, "c_fit_mod": c_fit,
                "c_intermediate_surface": c_mid, "d_no_sinking": d, "e_calm_end": e})
    res["physical_fail"] = not (a and b and d) or (ring_stops and not c_fit)
    res["insufficient"] = not res["physical_fail"] and not (len(distinct) >= 2 and c_mid)
    res["pass"] = not res["physical_fail"] and not res["insufficient"] and e
    return res


def judge(tag):
    lvl, _ = h.files()
    work = OUT / tag / CASE
    run_name = f"{P16}_{tag}_{CASE}"
    row = json.loads((work / "row.json").read_text())
    log = "\n".join(p.read_text(errors="replace") for p in sorted((h.RUNS / run_name).glob("runtime*.log")))
    served = sorted({(f.lower(), int(o), int(n)) for _, f, o, n in
                     re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+) length=(\d+)", log)})
    ov = h.plan_overlay(row["plan"], PRESET)
    img = bytearray(lvl)
    for o, d in ov.items():
        img[o:o + len(d)] = d
    img = bytes(img)
    judges = {}
    for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        r = subprocess.run([sys.executable, str(h.TOOLS / t), "--run", run_name], cwd=ROOT, capture_output=True, text=True)
        judges[t] = r.returncode
        (work / f"{t}.log").write_text(r.stdout + r.stderr)
    opens = re.findall(r"[\\/]([A-Za-z0-9_]+)\.lvl result=00000000", log)
    after = opens[opens.index(LEVEL) + 1:] if LEVEL in opens else opens
    other = [x for x in after if x.lower() not in (LEVEL, "transit", "fix")]
    p2 = h.p2_corrected(row.get("reads", {}), {PRESET: PRESET}, ov)
    frames = h._frames(run_name)
    rframes = h._frames(REFS["R1"])
    orig, mod = h.visual_model(lvl), h.visual_model(img)
    invalid = ["error: " + row["error"]] if "error" in row else []
    if len(frames) != 2:
        invalid.append("traced frames missing")
    p3 = []
    for fi in range(min(len(frames), len(rframes))):
        for k, shape in ((14, h.E14), (0, h.E0)):
            got = {}
            for case, fr, model in (("V", frames, mod), ("R1", rframes, orig)):
                want = model[k][0]
                got[case] = [d for d in h._find(fr[fi][1], shape) if [d["bindings"][0]["data"][
                    i * shape[1]:i * shape[1] + 12] for i in range(len(want))] == want]
            if not got["V"] or not got["R1"]:
                p3.append({"frame": fi, "element": k, "present": {c: bool(v) for c, v in got.items()}})
                invalid.append(f"element {k} draw absent from frame {fi}")
                continue
            a, b = got["R1"][0]["bindings"][0], got["V"][0]["bindings"][0]
            st = a["stride"]
            n = len(a["data"]) // st
            changed = [i for i in range(n) if a["data"][i * st:i * st + 12] != b["data"][i * st:i * st + 12]]
            rest = all(a["data"][i * st + 12:(i + 1) * st] == b["data"][i * st + 12:(i + 1) * st] for i in range(n))
            corners = [i for i, j in enumerate(orig[k][1]) if j in EDITED_VIS]
            p3.append({"frame": fi, "element": k, "changed": len(changed), "edited_corners": len(corners),
                       "changed_are_edited": sorted(changed) == sorted(corners), "rest_equal": rest})
    _, m0 = mesh(lvl)
    _, m2 = mesh(img)
    samples = json.loads((work / "samples.json").read_text())
    p4 = traversal(samples, m0, m2) if samples else {"physical_fail": True, "why": "no samples"}
    p5 = attribution(run_name, img, EDITED_VIS) if len(frames) == 2 else {"class": "INVALID"}
    if p5.get("class") == "INVALID" and "traced frames missing" not in invalid:
        invalid.append("camera draws not found")
    blog = "\n".join(p.read_text(errors="replace") for p in sorted((h.RUNS / "e499_g1_base").glob("runtime*.log")))
    checks = {
        "P1 delivery": served == sorted(h.plan_ranges(row["plan"])[1]) and len(served) == len(ov),
        "P2 guest geometry": p2["ok"],
        "P3 GPU draw": len(p3) == 4 and all(x.get("changed_are_edited") and x.get("rest_equal") for x in p3),
        "P4 playable physics": bool(p4.get("pass")),
        "P5 framebuffer attribution": p5.get("class") == "PASS",
        "P6 safety": not any(judges.values()) and row.get("runner_exit") == 0 and not row.get("process_left")
                     and not other and len(h.FAULT.findall(log)) <= len(h.FAULT.findall(blog))
                     and "M23 haptics policy=suppressed physical_pad_drivers=none" in log
                     and bool(re.search(r"M33 mods gameplay mod=\S+ achievements=not_awarded", log)),
    }
    c = checks
    if invalid:
        cls = "INVALID"
    elif not c["P2 guest geometry"] or not c["P3 GPU draw"] or p4.get("physical_fail"):
        cls = "EXPERIMENT FAILED"
    elif all(c.values()):
        cls = "VERIFIED"
    elif c["P1 delivery"] and c["P4 playable physics"] and c["P6 safety"]:
        cls = "PARTIAL - GEOMETRY AND PHYSICS VERIFIED, RENDER UNVERIFIED"
    elif c["P5 framebuffer attribution"] and p4.get("insufficient"):
        cls = "PARTIAL - RENDER VERIFIED, PLAYABILITY UNVERIFIED"
    else:
        cls = "PARTIAL (see checks)"
    result = {"class": cls, "invalid": invalid, "checks": checks, "p2": p2, "p3": p3, "p4": p4, "p5": p5,
              "served": len(served), "guest_base": row.get("guest_base"), "base_votes": row.get("base_votes"),
              "runner_exit": row.get("runner_exit"), "judges": judges, "other_levels": other,
              "frames": [f[0] for f in frames]}
    (OUT / tag / "judge.json").write_text(json.dumps(result, indent=1, default=str) + "\n")
    print(json.dumps({k: result[k] for k in ("class", "invalid", "checks", "p2", "p3", "judges")}, indent=1, default=str))
    print(json.dumps({k: p4.get(k) for k in ("settled", "moved_max", "ring_stops_distinct", "sink_samples", "min_z",
                                             "a_settled", "b_moved", "c_enough_stops", "c_fit_mod",
                                             "c_intermediate_surface", "d_no_sinking", "e_calm_end", "behaviours")},
                     default=str))
    print(json.dumps({"p5": p5.get("class"), "control": p5.get("control"),
                      "tests": {k: {x: v[x] for x in ("disc_samples", "frac", "p_one_sided", "median_e_mod",
                                                       "median_e_orig", "T_q90_unchanged", "degenerate", "ii", "iii")}
                                for k, v in p5.get("tests", {}).items()}}, indent=1, default=str))
    return 0 if cls == "VERIFIED" else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("check", "validate", "run", "judge"))
    ap.add_argument("tag", nargs="?")
    a = ap.parse_args()
    if a.cmd == "check":
        sys.exit(check())
    if a.cmd == "validate":
        sys.exit(validate())
    if not a.tag or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", a.tag):
        ap.error("bad tag")
    if a.cmd == "run":
        print(json.dumps(run(a.tag)), flush=True)
    sys.exit(judge(a.tag))
