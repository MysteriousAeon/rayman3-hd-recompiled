"""G6-P17 (D-273 / E-506): declarative terrain patches (terrain-patch-v1) on intro_15, development only.

    python -I tools/experiments/modding_feasibility/g6p17_terrain.py check      offline O1-O5 (needs the private files)

The patches in terrain_patches/ are authored data only (format, level, the level file's SHA-256, region, names, vertex
numbers of the allow-listed region, z displacements). They are compiled by `r3hd_mods.py terrain-patch` / the
`terrain-patch` manifest override into the verified G6-P16 geometry edit (collision_edit). Acceptance:
  O1 schema and resource: exact hashes, allow-list, malformed-input refusals (game data only for the compile ones);
  O2 reference equivalence: shallow-bowl.json == preset spawn-multi-surface-v1 byte for byte (offsets, lengths, bytes,
     edit labels), the plan written through import / plan equals the retained G6-P16 run plan (e504 v1) record for
     record, and the resource image is identical;
  O3 independent patch: east-tilt.json compiles through the CLI with no code change into a distinct valid deformation;
  O4 geometry integrity per patch: face / edge rules, edge-scalar classes, octree cover, every bound, ground
     steepness, visual on collision, visual face normals, visual / collision triangle pairing;
  O5 policy and regressions: determinism and canonicalization, gate-off / other-level refusal, one terrain edit per mod,
     a conflicting second mod refused whole, gameplay record, existing presets byte-identical to retained plans.
"""
import copy
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g6p13_collision as h  # noqa: E402
import g6p16_multi_surface as p16  # noqa: E402

rm, ROOT, LEVEL = h.rm, h.ROOT, h.LEVEL
PATCHES = HERE / "terrain_patches"
BOWL, TILT = PATCHES / "shallow-bowl.json", PATCHES / "east-tilt.json"
OUT = ROOT / "private" / "work" / "e506"
E504_PLAN = ROOT / "private" / "work" / "e504" / "v1" / "ms_trace" / "cache" / "plan.txt"
TILT_DZ = {391: -0.30, 392: -0.30, 387: -0.30, 365: -0.175, 394: -0.05, 393: -0.05, 388: -0.05}


def load(p):
    return rm._terrain_json(Path(p).read_bytes(), Path(p).name)


def compile_patch(patch, lvl=None, ptr=None, check_files=True):
    if lvl is None:
        lvl, ptr = h.files()
    canon = rm.parse_terrain_patch(patch, "p")
    return rm.collision_edit(lvl, ptr, LEVEL, rm.terrain_spec(canon), "p", check_files)


def cli(args, env_extra=h.GATE):
    env = dict(os.environ)
    env.pop(rm.STRUCT_ENV, None)
    env.update(env_extra or {})
    r = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / "r3hd_mods.py"), *args, "--game-dir", str(h.GAME),
                        "--json"], capture_output=True, text=True, cwd=ROOT, env=env)
    return json.loads(r.stdout)


def refused(fn, code="TARGET_CHANGED"):
    try:
        fn()
    except rm.Refusal as x:
        return x.code == code
    return False


def geometry(lvl, eds, dz_want):
    """O4 for one compiled patch (modified image vs original)."""
    L, m0 = p16.mesh(lvl)
    new = h.apply(lvl, eds)
    L2, m2 = p16.mesh(new)
    fe, ee, se, classes, excess = h.integrity(L2, new, m2)
    fe0, ee0, se0, classes0, excess0 = h.integrity(L, lvl, m0)
    cover, leaves, root = p16.octree_cover(L2, new, m2)
    moved = [k for k in range(m2["nv"]) if m2["verts"][k] != m0["verts"][k]]
    dzs = {k: round(m2["verts"][k][2] - m0["verts"][k][2], 5) for k in moved}
    boxes = {"octree root": (L.f32s(root, 3), L.f32s(root + 12, 3)),
             "IPO +0x38": (L.f32s(0x159450, 3), L.f32s(0x159450 + 12, 3)),
             "IPO +0x34": (L.f32s(0x159438, 3), L.f32s(0x159438 + 12, 3)),
             "sector +0x34": (L.f32s(0x378164, 3), L.f32s(0x378164 + 12, 3)),
             "copy / sector +0x38": (L.f32s(0x37817C, 3), L.f32s(0x37817C + 12, 3))}
    margins = {n: round(min(min(m2["verts"][k][i] - lo[i], hi[i] - m2["verts"][k][i]) for k in moved for i in range(3)), 4)
               for n, (lo, hi) in boxes.items()}
    ring = {(ei, j) for ei, e in enumerate(m0["elems"]) for j in range(e["nt"]) if set(moved) & set(e["idx"][3 * j:3 * j + 3])}
    tp = lambda m, t: [m["verts"][q] for q in m["elems"][t[0]]["idx"][3 * t[1]:3 * t[1] + 3]]   # noqa: E731
    nz = {t: (rm._face(*tp(m0, t))[2], rm._face(*tp(m2, t))[2]) for t in ring}
    ground_ok = all(b >= 0.9 for a, b in nz.values() if a >= 0.9) and all(a * b > 0 for a, b in nz.values())
    vp = L.ptr(0x15C74 - 4) + 4
    twin = {c: v for v, (_, c) in rm.terrain_spec(rm.parse_terrain_patch(load(BOWL), "p"))["visual"]["map"].items()}
    agree = max(math.dist(struct.unpack_from(">3f", new, vp + 12 * twin[c]), m2["verts"][c]) for c in moved)
    vis0, vis1 = p16.visual_tris(lvl), p16.visual_tris(new)
    ed_vis = {twin[c] for c in moved}
    vring = [k for k, (tri, _) in vis0.items() if set(tri) & ed_vis]
    go = 0x15C74 - 4
    vis_face = max(math.dist(rm._face(*vis1[k][1]), struct.unpack_from(
        ">3f", new, L.ptr(L.ptr(L.ptr(go + 0x14) + 4 * k[0]) + 0x14) + 4 + 12 * k[1])) for k in vring)
    amb = ambiguous_scalars(L, L2, lvl, m0)
    amb_ok = all(x["coplanar_orig"] and x["new"][0] == 1.0 and x["rule_gap"] <= 1e-3 for x in amb)
    sp0, sp1 = p16.surface(m0, *h.SPAWN_XY), p16.surface(m2, *h.SPAWN_XY)
    ew = []
    for x in (-91.5, -93.0, -94.5, -96.0, -97.5, -99.0):
        a, b = p16.surface(m0, x, 55.0), p16.surface(m2, x, 55.0)
        if a and b:
            ew.append({"x": x, "tri": a[0][0], "dz": round(b[0][1] - a[0][1], 4)})
    r = {"moved": dzs, "face_err": fe, "edge_err": ee, "scalar_one_err": se, "classes": classes,
         "classes_original": classes0, "sphere_excess": excess, "octree_leaves": leaves, "octree_cover": cover,
         "bound_margins": margins, "collision_ring": len(ring), "visual_ring": len(vring),
         "ring_normal_z_min": round(min(b for _, b in nz.values()), 4), "ground_ok": ground_ok,
         "visual_on_collision_max": agree, "visual_face_err": vis_face, "ambiguous_edge_scalars": amb,
         "spawn_surface": {"orig": round(sp0[0][1], 4), "mod": round(sp1[0][1], 4), "dz": round(sp1[0][1] - sp0[0][1], 4),
                           "tri": sp0[0][0]},
         "east_west_profile_y55": ew, "length_equal": len(new) == len(lvl)}
    r["ok"] = (all(abs(dzs.get(k, 0) - d) < 1e-5 for k, d in dz_want.items()) and sorted(dzs) == sorted(dz_want)
               and fe <= max(fe0, 2.5e-5) and ee < 2e-6 and se < 2e-6 and excess <= max(excess0, 0)
               and classes["one"] == classes0["one"] and classes["other"] == classes0["other"] and amb_ok and cover
               and min(margins.values()) > 0 and ground_ok and agree < 0.001 and vis_face < 1e-6
               and len(ring) == len(vring) and r["length_equal"])
    return r, new


def ambiguous_scalars(L, L2, lvl, m0):
    """Shared edges whose scalar class changes (the D-266 unresolved rule: coplanar originals keep 1.0)."""
    out = []
    for ei, e in enumerate(m0["elems"]):
        b = e["blk"]
        mp, u1, u2 = L.ptr(b + 0x14), L.ptr(b + 0x18), L.ptr(b + 0x1C)
        mapping = struct.unpack_from(f">{3 * e['nt']}H", lvl, mp + 4)
        mem = {}
        for j in range(e["nt"]):
            for c in range(3):
                mem.setdefault(mapping[3 * j + c], []).append(j)
        for s, js in mem.items():
            if len(js) < 2:
                continue
            st = []
            for LL in (L, L2):
                fn = [LL.f32s(e["nrm"] + 12 * j, 3) for j in js]
                en, sc = LL.f32s(u1 + 12 * s, 3), LL.f32s(u2 + 4 * s, 1)[0]
                md = min(sum(f[i] * en[i] for i in range(3)) for f in fn)
                st.append((sc, md, "min" if abs(sc - md) < 2e-6 else "kept" if sc == 1.0 else "other"))
            if st[0][2] != st[1][2]:
                out.append({"element": ei, "slot": s, "orig": st[0], "new": st[1],
                            "coplanar_orig": abs(st[0][1] - 1.0) < 2e-6 and st[0][0] == 1.0,
                            "rule_gap": round(1.0 - st[1][1], 7)})
    return out


def check():
    res, (lvl, ptr) = {}, h.files()
    allow = rm.COLLISION_ALLOW[LEVEL]
    bowl, tilt = load(BOWL), load(TILT)
    sha = allow["lvl"][1]

    # O1 schema and resource validation
    def bad(f, code):
        p = copy.deepcopy(bowl)
        f(p)
        return refused(lambda: rm.parse_terrain_patch(p, "p"), code)
    neg = {
        "unsupported format": bad(lambda p: p.update(format="terrain-patch-v2"), "UNSUPPORTED"),
        "unsupported level": bad(lambda p: p.update(level="intro_10"), "UNSUPPORTED"),
        "wrong resource hash": bad(lambda p: p.update(lvl_sha256="0" * 64), "TARGET_CHANGED"),
        "malformed hash": bad(lambda p: p.update(lvl_sha256=sha.upper()), "BAD_MANIFEST"),
        "invalid region": bad(lambda p: p.update(region="spawn-ground-v2"), "UNSUPPORTED"),
        "vertex outside the allow-list": bad(lambda p: p["groups"][0]["vertices"].append(382), "UNSUPPORTED"),
        "duplicate vertex": bad(lambda p: p["groups"][1]["vertices"].append(365), "BAD_MANIFEST"),
        "out-of-range displacement (-0.35)": bad(lambda p: p["groups"][0].update(delta_z=-0.35), "UNSUPPORTED"),
        "raising displacement (+0.10)": bad(lambda p: p["groups"][0].update(delta_z=0.10), "UNSUPPORTED"),
        "NaN displacement": bad(lambda p: p["groups"][0].update(delta_z=float("nan")), "BAD_MANIFEST"),
        "infinite displacement": bad(lambda p: p["groups"][0].update(delta_z=float("-inf")), "BAD_MANIFEST"),
        "string displacement": bad(lambda p: p["groups"][0].update(delta_z="-0.3"), "BAD_MANIFEST"),
        "unexpected top-level key (offset)": bad(lambda p: p.update(offset=0x5A77C), "BAD_MANIFEST"),
        "unexpected group key (dz)": bad(lambda p: p["groups"][0].update(dz=-0.3), "BAD_MANIFEST"),
        "missing key": bad(lambda p: p.pop("region"), "BAD_MANIFEST"),
        "one group only": bad(lambda p: p["groups"].pop(), "BAD_MANIFEST"),
        "five groups": bad(lambda p: p.update(groups=[{"name": f"g{v}", "vertices": [v], "delta_z": -0.1}
                                                       for v in (365, 387, 388, 391, 392)]), "BAD_MANIFEST"),
        "empty group": bad(lambda p: p["groups"][0].update(vertices=[]), "BAD_MANIFEST"),
        "vertex as string": bad(lambda p: p["groups"][0].update(vertices=["365"]), "BAD_MANIFEST"),
        "groups not a list": bad(lambda p: p.update(groups={"a": 1}), "BAD_MANIFEST"),
        "duplicate group name": bad(lambda p: p["groups"][1].update(name="centre"), "BAD_MANIFEST"),
        "NaN literal in the file": refused(lambda: rm._terrain_json(BOWL.read_bytes().replace(b"-0.15", b"NaN"), "f"),
                                           "BAD_MANIFEST"),
        "duplicate JSON key in the file": refused(lambda: rm._terrain_json(
            BOWL.read_bytes().replace(b'"name": "shallow-bowl",', b'"name": "a", "name": "b",'), "f"), "BAD_MANIFEST"),
    }
    res["O1 schema and resource"] = {
        "hashes": (len(lvl), rm.sha256_bytes(lvl)) == allow["lvl"] and (len(ptr), rm.sha256_bytes(ptr)) == allow["ptr"],
        "region vertices": sorted(rm.terrain_region(LEVEL, "spawn-ground-v1")["vertices"]), "refusals": neg}
    res["O1 schema and resource"]["ok"] = res["O1 schema and resource"]["hashes"] and all(neg.values())

    # O2 reference equivalence
    ref = h.edits("spawn-multi-surface-v1")
    got = compile_patch(bowl)
    img_ref, img_got = h.apply(lvl, ref), h.apply(lvl, got)
    plan_e504 = sorted((int(r[2]), int(r[3]), r[5]) for r in (ln.split() for ln in E504_PLAN.read_text(
        encoding="utf-8").splitlines() if ln.startswith("range ")))
    o2 = {"ranges": [len(ref), len(got)], "bytes": [sum(len(d) for _, d, _ in ref), sum(len(d) for _, d, _ in got)],
          "offsets_lengths_bytes_identical": [(o, d) for o, d, _ in ref] == [(o, d) for o, d, _ in got],
          "edit_labels_identical": [w for _, _, w in ref] == [w for _, _, w in got],
          "image_identical": img_ref == img_got, "length_identical": len(img_got) == len(lvl)}
    with tempfile.TemporaryDirectory(dir=ROOT / "private" / "work") as td:
        mod = cli(["terrain-patch", str(BOWL), "--out", str(Path(td) / "bowlmod")])
        o2["cli ok"] = mod.get("result") == "ok" and mod.get("range_count") == 123 and mod.get("bytes") == 1284
        m = json.loads((Path(td) / "bowlmod" / "mod.json").read_text(encoding="utf-8")) if o2["cli ok"] else None
        imps, pl = h.make_plan(Path(td) / "a", [m]) if m else ([], {})
        o2["import ok"] = bool(imps) and imps[0].get("result") == "ok"
        if pl.get("plan"):
            mine = sorted((int(r[2]), int(r[3]), r[5]) for r in (ln.split() for ln in Path(pl["plan"]).read_text(
                encoding="utf-8").splitlines() if ln.startswith("range ")))
            o2["plan records equal the retained e504 v1 plan"] = mine == plan_e504
            o2["plan gameplay record"] = f"\ngameplay {m['id']}\n" in Path(pl["plan"]).read_text(encoding="utf-8")
            o2["plan_ranges"] = len(mine)
    o2["ok"] = all(v for k, v in o2.items() if isinstance(v, bool)) and o2.get("plan_ranges") == 123
    res["O2 reference equivalence"] = o2

    # O3 independent patch (CLI only: no code change, no preset)
    with tempfile.TemporaryDirectory(dir=ROOT / "private" / "work") as td:
        t = cli(["terrain-patch", str(TILT), "--out", str(Path(td) / "tiltmod")])
        b = cli(["terrain-patch", str(BOWL)])
        mt = json.loads((Path(td) / "tiltmod" / "mod.json").read_text(encoding="utf-8")) if t.get("result") == "ok" else None
        imps, pl = h.make_plan(Path(td) / "a", [mt]) if mt else ([], {})
    teds = compile_patch(tilt)
    o3 = {"cli": {k: t.get(k) for k in ("result", "range_count", "bytes", "file")}, "identity": t.get("patch", {}).get(
          "identity_sha256"), "groups": t.get("patch", {}).get("groups"),
          "cli ok": t.get("result") == "ok" and t.get("range_count") == len(teds),
          "cli ranges equal the library compile": [(r_["offset"], r_["length"]) for r_ in t.get("ranges", [])]
          == [(o, len(d)) for o, d, _ in teds],
          "distinct from the bowl": h.apply(lvl, teds) != img_ref and t.get("patch", {}).get("identity_sha256")
          != b.get("patch", {}).get("identity_sha256"),
          "same range layout as the bowl (values differ)": [(o, len(d)) for o, d, _ in teds] == [(o, len(d)) for o, d, _ in ref],
          "differing ranges vs bowl": sum(1 for (_, d1, _), (_, d2, _) in zip(teds, ref) if d1 != d2),
          "import and plan ok": bool(imps) and imps[0].get("result") == "ok" and bool(pl.get("plan")),
          "no preset named east-tilt": all("tilt" not in k for k in allow["presets"])}
    o3["ok"] = all(v for v in o3.values() if isinstance(v, bool))
    res["O3 independent patch"] = o3

    # O4 geometry integrity (each patch) and mutated-data refusals through the terrain path
    gb, _ = geometry(lvl, got, {**{k: -0.3 for k in (365, 392, 393)}, **{k: -0.15 for k in (387, 388, 391, 394)}})
    gt, _ = geometry(lvl, teds, TILT_DZ)

    def mut(o, b_):
        x = bytearray(lvl)
        x[o:o + len(b_)] = b_
        return bytes(x)
    def mut2(*edits_):
        x = bytearray(lvl)
        for o, b_ in edits_:
            x[o:o + len(b_)] = b_
        return bytes(x)

    def refused_why(fn, text):
        try:
            fn()
        except rm.Refusal as x:
            return x.code == "TARGET_CHANGED" and text in x.detail
        return False
    L, m0 = p16.mesh(lvl)
    vo, vp = m0["vo"] + 4, L.ptr(0x15C74 - 4) + 4
    m4 = {
        "collision original changed": refused(lambda: compile_patch(tilt, mut(vo + 12 * 391 + 8, b"\xc1\x0c\x04\x65"), ptr, False)),
        "visual original changed": refused(lambda: compile_patch(tilt, mut(vp + 12 * 1186 + 8, b"\xc1\x0c\x04\x69"), ptr, False)),
        "second visual vertex on a moved collision vertex (crack)": refused_why(lambda: compile_patch(
            tilt, mut(vp + 12 * 1190, lvl[vp + 12 * 1181:vp + 12 * 1181 + 12]), ptr, False), "would crack"),
        "visual corner moved onto another collision vertex (pairing)": refused_why(lambda: compile_patch(
            tilt, mut(vp + 12 * 401, struct.pack(">3f", *m0["verts"][174])), ptr, False), "pairs with no"),
        "unsafe bounds (IPO +0x38 box and its copy: min z above the edit)": refused_why(lambda: compile_patch(
            tilt, mut2((0x159454 + 8, struct.pack(">f", -9.85)), (0x378180 + 8, struct.pack(">f", -9.85))), ptr, False),
            "would leave the IPO +0x38 box"),
        "corrupted octree leaf list (invalid topology)": refused(lambda: compile_patch(tilt, h.corrupt_leaf(lvl, ptr), ptr, False)),
        "wrong file (hash) at compile": refused(lambda: compile_patch(tilt, mut(0x100, b"\xAA"), ptr)),
    }
    res["O4 geometry integrity"] = {"shallow-bowl": gb, "east-tilt": gt, "mutated-data refusals": m4,
                                    "ok": gb["ok"] and gt["ok"] and all(m4.values())}

    # O5 policy and regressions
    perm = copy.deepcopy(tilt)
    perm["groups"] = [dict(g, vertices=list(reversed(g["vertices"]))) for g in reversed(perm["groups"])]
    o5 = {"deterministic": compile_patch(tilt) == teds and compile_patch(bowl) == got,
          "canonical (group / vertex order irrelevant)": rm.parse_terrain_patch(perm, "p") == rm.parse_terrain_patch(tilt, "p")
          and compile_patch(perm) == teds,
          "gate-off CLI refused": cli(["terrain-patch", str(TILT)], env_extra={}).get("code") == "UNSUPPORTED",
          "gate naming another level refused": cli(["terrain-patch", str(TILT)],
                                                   env_extra={rm.STRUCT_ENV: "intro_10"}).get("code") == "UNSUPPORTED",
          "gameplay-affecting": rm.changes_game_logic({"overrides": [{"type": "terrain-patch", "patch": tilt}]})}
    os.environ.pop(rm.STRUCT_ENV, None)
    o5["gate-off manifest refused"] = refused(lambda: rm.parse_terrain_override({"type": "terrain-patch", "patch": tilt}, "o"),
                                             "UNSUPPORTED")
    os.environ[rm.STRUCT_ENV] = LEVEL
    try:
        o5["terrain-patch + collision-vertex-offset in one mod refused"] = refused(lambda: rm.parse_manifest({"mod.json": json.dumps(
            h.manifest("t.two", {"type": "terrain-patch", "patch": tilt}, h.op("spawn-multi-surface-v1"))).encode()}),
            "BAD_MANIFEST")
        o5["two terrain patches in one mod refused"] = refused(lambda: rm.parse_manifest({"mod.json": json.dumps(
            h.manifest("t.two", {"type": "terrain-patch", "patch": tilt}, {"type": "terrain-patch", "patch": bowl})).encode()}),
            "BAD_MANIFEST")
        o5["override with extra key refused"] = refused(lambda: rm.parse_terrain_override(
            {"type": "terrain-patch", "patch": tilt, "offset": 4}, "o"), "BAD_MANIFEST")
    finally:
        os.environ.pop(rm.STRUCT_ENV, None)
    with tempfile.TemporaryDirectory(dir=ROOT / "private" / "work") as td:
        imps, pl = h.make_plan(Path(td) / "c", [h.manifest("e506.tilt", {"type": "terrain-patch", "patch": tilt}),
                                                h.manifest("e506.bowl", {"type": "terrain-patch", "patch": bowl})])
        o5["conflicting second terrain mod refused whole"] = [a_["id"] for a_ in pl.get("active", [])] == ["e506.tilt"] \
            if pl.get("active") and isinstance(pl["active"][0], dict) else len(pl.get("active", [])) == 1
        o5["conflict detail"] = {k: pl.get(k) for k in ("active",) if k in pl}
    retained = [("e499/g1/mod", "spawn-drop-1.50"), ("e499/g1/control", "control-far-drop-1.50"),
                ("e500/s1/small", h.SMALL), ("e502/v1/ref", h.SMALL), ("e502/v1/vis", h.VISP),
                ("e504/v1/ms_trace", "spawn-multi-surface-v1")]
    for where, preset in retained:
        try:
            h.plan_overlay(json.loads((ROOT / "private" / "work" / where / "row.json").read_text())["plan"], preset)
            o5[f"{preset} byte-identical to {where} plan"] = True
        except SystemExit:
            o5[f"{preset} byte-identical to {where} plan"] = False
    o5["ok"] = all(v for v in o5.values() if isinstance(v, bool))
    res["O5 policy and regressions"] = o5
    verdict = {k: v["ok"] for k, v in res.items()}
    print(json.dumps(verdict, indent=1))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    return 0 if all(verdict.values()) else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        sys.exit(check())
    print(__doc__)
    sys.exit(2)
