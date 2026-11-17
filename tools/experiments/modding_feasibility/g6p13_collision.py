"""G6-P13 (D-266 / E-499): does an edited static-collision surface change where Rayman stands? Offline + hidden runs.

    python -I tools/experiments/modding_feasibility/g6p13_collision.py check          offline O1-O5
    python -I tools/experiments/modding_feasibility/g6p13_collision.py run TAG        hidden base / mod / control
    python -I tools/experiments/modding_feasibility/g6p13_collision.py judge TAG

Outputs stay under private/work/e499/. The development compile gate (R3HD_DEV_STRUCTURAL_TX=intro_15) is set only in
the environment of the mod-tool subprocesses this script starts, never for the game process; the plan holds ordinary
same-size `range` records that the unchanged production runtime serves.

PROTOCOL (written and committed before any modified run; thresholds fixed here and not changed after results)
Known before the protocol: E-462 (D-229), retained run c1, same entry route (m9_license_run, `--test-level intro_15`,
hidden, muted, no physical pad, isolated test profile, no input, no captures, 230 s): the opening cinematic places
Rayman at (-95.896, 56.433, -9.094) at about 34 s; YAM_C_Attente at about 71 s; settled (median of the samples 5..60 s
after his first Attente) (-95.896, 56.433, -9.104), spread 0.000, identical in its three runs. E-498 / E-499 (files):
the surface under that point is element 3 triangle 33 of mesh 0x5A77C, z -9.118 there; the guest holds the file's
collision bytes at level base + file offset - 4. The base case is rerun here (not reused from E-462) because the
executable has been rebuilt many times since E-462; the same base also fixes the guest base address for P2.
Cases (one hidden run each, in this order):
  base     no mod plan
  mod      preset spawn-drop-1.50: vertices 365 / 392 / 393 (the corners of the triangle under the spawn point) z - 1.50,
           with the 14 ring face normals, the touched edge normals / scalars and 8 octree bounds + header (61 ranges,
           588 bytes); the triangle is translated rigidly, so the surface at the spawn point becomes z -10.618
  control  preset control-far-drop-1.50: the same operation on element 3 triangle 19 (vertices 355 / 356 / 380),
           30.4 units from the spawn point (58 ranges, 552 bytes): the same delivery path, the same kinds of edited
           data, and no change to the surface under Rayman
Observed (read-only, m5_live): Rayman's position and behaviour every 0.2 s from discovery to 185 s after the level
opens; the level's guest base from the seven NIK_mSpoPont SuperObjects (guest SO - file SO + 4, all seven equal);
every plan range of BOTH presets read back at discovery and at the last sample.
Criteria (judged separately):
  P1 delivery: mod and control serve exactly their plan's ranges of intro_15.lvl (the set of (offset, length) equals the
     plan's range records) and nothing else; base logs mods=off and serves nothing.
  P2 guest identity: in mod, every spawn-preset range reads back as the plan's new bytes and every control-preset range
     as the original bytes, at discovery and at the last sample; in control the converse; in base both presets read
     the original bytes; the base address is the same from all seven bridges in each run.
  P3 physical effect: mod's settled z in [base settled z - 1.85, base settled z - 0.75], its settled x, y within 1.0 of
     base's, settled spread <= 0.05, and no mod sample below z -12.618 (2 units under the lowered surface: falling
     through); mod reaches YAM_C_Attente. Expected value: base - 1.50.
  P4 control: control's settled position within 0.02 of base's, its behaviours only YAM_C_Init / YAM_C_Attente, its
     placed position (first sample after the cinematic's jump of > 5 units) within 0.02 of base's and its Attente
     within 5 s of base's; mod's placed x, y within 0.02 of base's.
  P5 runtime safety: haptics policy line, M21 / M22 / M23 judges 0, runner exit 0, no game process left, no level
     file other than intro_15's opened after it, no fatal / trap / stub / invalid-indirect / host-catch log line beyond
     base's count.
  P6 policy: the gameplay record line in mod and control only; the compile without the development gate is refused
     (offline O4 / O5 evidence, re-run by `judge`).
Result classes: all PASS -> G6-P13 VERIFIED; P1 P2 PASS, P3 FAIL with mod at base's height -> PARTIAL (edit loads,
physics unaffected: another collision copy or structure); P3 FAIL by falling or dying -> EXPERIMENT FAILED
(inconsistent derived data); P1 or P2 FAIL -> BLOCKED (delivery). Invalid (rerun the case alone, not judged): the level
does not open, Rayman or the bridges are not found, base never reaches Attente, sampling ends before base's Attente +
60 s, or base's settled position differs from E-462's by more than 0.02.
Not measured: rendering (the visual surface is not edited: Rayman is expected to stand sunk into it), walking or
jumping on the edit, other actors, sectors, saves.
"""
import argparse
import copy
import json
import math
import os
import re
import statistics
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_mods as rm  # noqa: E402

GAME = ROOT / "private" / "extracted" / "5841123F"
RUNS = ROOT / "private" / "work" / "m6_runs"
LEVEL, BRIDGE, RAY = "intro_15", "NIK_mSpoPont", "YLT_RaymanModel"
PREFIX, SECONDS = "e499", 230
PRESETS = {"mod": "spawn-drop-1.50", "control": "control-far-drop-1.50"}
CASES = ("base", "mod", "control")
E462_SETTLED = (-95.896, 56.433, -9.104)
SPAWN_XY = (-95.896, 56.433)
CALM = {"YAM_C_Init", "YAM_C_Attente"}
GATE = {rm.STRUCT_ENV: LEVEL}
RING_SPAWN = {(2, 52), (2, 57), (2, 188), (2, 205), (2, 207), (2, 208), (2, 209),
              (3, 33), (3, 39), (3, 49), (3, 52), (3, 54), (3, 55), (3, 56)}
FAULT = re.compile(r"(?i)\b(fatal|trap|unimplemented stub|invalid indirect|host catch)\b")


def files():
    d = GAME / "GAMEDATAbin" / LEVEL
    return (d / f"{LEVEL}.lvl").read_bytes(), (d / f"{LEVEL}.ptr").read_bytes()


def edits(preset, lvl=None, ptr=None, spec=None, check_files=True):
    if lvl is None:
        lvl, ptr = files()
    spec = spec or rm.COLLISION_ALLOW[LEVEL]["presets"][preset]
    return rm.collision_edit(lvl, ptr, LEVEL, spec, preset, check_files)


def manifest(mid, *overrides):
    return {"format": 1, "id": mid, "name": f"{PREFIX} test", "version": "1.0.0",
            "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids({"home": None}), "min_port_version": "0.0.1"},
            "overrides": list(overrides)}


def op(preset, **kw):
    lvl, _ = files()
    return {"type": "collision-vertex-offset", "level": LEVEL, "preset": preset, "lvl_sha256": rm.sha256_bytes(lvl), **kw}


def tool(work, args, env_extra=None):
    env = dict(os.environ)
    env.pop(rm.STRUCT_ENV, None)
    env.update(env_extra or {})
    common = ["--mods-root", str(work / "mods"), "--cache", str(work / "cache"), "--game-dir", str(GAME), "--json"]
    r = subprocess.run([sys.executable, "-I", str(TOOLS / "r3hd_mods.py"), *args, *common], capture_output=True,
                       text=True, cwd=ROOT, env=env)
    return json.loads(r.stdout)


def make_plan(work, mods, env_extra=GATE):
    """Import (enabled) each manifest in order and write a plan; returns (import results, plan result)."""
    imps = []
    for k, m in enumerate(mods):
        src = work / f"src{k}"
        src.mkdir(parents=True)
        (src / "mod.json").write_text(json.dumps(m), encoding="utf-8")
        imps.append(tool(work, ["import", str(src), "--enable"], env_extra))
    return imps, tool(work, ["plan"], env_extra)


def plan_ranges(plan_path):
    text = Path(plan_path).read_text(encoding="utf-8")
    files_ = [ln.split(" ", 2)[2] for ln in text.splitlines() if ln.startswith("file ")]
    out = []
    for ln in text.splitlines():
        if ln.startswith("range "):
            f, o, n = (int(x) for x in ln.split()[1:4])
            out.append((Path(files_[f]).name.lower(), o, n))
    return text, sorted(out)


def apply(lvl, eds):
    b = bytearray(lvl)
    for o, d, _ in eds:
        b[o:o + len(d)] = d
    return bytes(b)


# ------------------------------------------------------------------------------------------------- offline O1-O5
def integrity(Lx, data, mx):
    """Face / edge normal rule errors and edge-scalar classes over the whole mesh of one copy."""
    def unit(v):
        n_ = math.sqrt(sum(x * x for x in v))
        return [x / n_ for x in v] if n_ > 1e-12 else None
    fe = ee = se = 0.0
    classes = {"one": 0, "min-dot": 0, "kept-1.0": 0, "other": 0}
    for e in mx["elems"]:
        b = e["blk"]
        mp, u1, u2 = Lx.ptr(b + 0x14), Lx.ptr(b + 0x18), Lx.ptr(b + 0x1C)
        fn = [Lx.f32s(e["nrm"] + 12 * j, 3) for j in range(e["nt"])]
        for j in range(e["nt"]):
            a_, b_, c_ = (mx["verts"][q] for q in e["idx"][3 * j:3 * j + 3])
            f = unit([(b_[1] - a_[1]) * (c_[2] - a_[2]) - (b_[2] - a_[2]) * (c_[1] - a_[1]),
                      (b_[2] - a_[2]) * (c_[0] - a_[0]) - (b_[0] - a_[0]) * (c_[2] - a_[2]),
                      (b_[0] - a_[0]) * (c_[1] - a_[1]) - (b_[1] - a_[1]) * (c_[0] - a_[0])])
            if f:
                fe = max(fe, math.dist(f, fn[j]))
        mapping = struct.unpack_from(f">{3 * e['nt']}H", data, mp + 4)
        members = {}
        for j in range(e["nt"]):
            for c in range(3):
                members.setdefault(mapping[3 * j + c], []).append(j)
        for s_, js in members.items():
            en = Lx.f32s(u1 + 12 * s_, 3)
            u = unit([sum(fn[j][i] for j in js) for i in range(3)])
            if u is not None:
                ee = max(ee, math.dist(u, en))
            sc = Lx.f32s(u2 + 4 * s_, 1)[0]
            md = min(sum(fn[j][i] * en[i] for i in range(3)) for j in js)
            if len(js) == 1:
                classes["one"] += 1
                se = max(se, abs(sc - 1))
            elif abs(sc - md) < 2e-6:
                classes["min-dot"] += 1
            elif sc == 1.0:
                classes["kept-1.0"] += 1
            else:
                classes["other"] += 1
    excess = max(math.dist(v, mx["centre"]) - mx["radius"] for v in mx["verts"])
    return fe, ee, se, classes, excess


def check():
    res, lvl, ptr = {}, *files()
    allow = rm.COLLISION_ALLOW[LEVEL]
    import m25_mesh_audit as m25
    import g6p12_collision_file_audit as g6
    L = m25.Level(LEVEL)
    mesh = g6.parse_mesh(L, allow["zdr"] - 4)
    spec = allow["presets"]["spawn-drop-1.50"]
    ring = {(ei, j) for ei, e in enumerate(mesh["elems"]) for j in range(e["nt"])
            if set(spec["vertices"]) & set(e["idx"][3 * j:3 * j + 3])}
    e3 = mesh["elems"][3]
    t33 = [mesh["verts"][q] for q in e3["idx"][3 * 33:3 * 33 + 3]]

    def bary(t, x, y):
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        l1 = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / d
        l2 = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / d
        return l1, l2, 1 - l1 - l2, l1 * az + l2 * bz + (1 - l1 - l2) * cz
    l1, l2, l3, z_spawn = bary(t33, *SPAWN_XY)
    res["O1 source and target"] = {
        "lvl": [len(lvl), rm.sha256_bytes(lvl)], "ptr": [len(ptr), rm.sha256_bytes(ptr)],
        "ok": ((len(lvl), rm.sha256_bytes(lvl)) == allow["lvl"] and (len(ptr), rm.sha256_bytes(ptr)) == allow["ptr"]
               and (mesh["nv"], mesh["ne"]) == (667, 7) and ring == RING_SPAWN and min(l1, l2, l3) > 0
               and abs(z_spawn + 9.118) < 0.005
               and all(lvl[mesh["vo"] + 4 + 12 * k:mesh["vo"] + 16 + 12 * k].hex() == h
                       for p in allow["presets"].values() for k, h in p["vertices"].items())),
        "ring": sorted(ring), "spawn_surface_z": round(z_spawn, 4), "spawn_barycentric": [round(l1, 3), round(l2, 3), round(l3, 3)]}

    out = {}
    for case, preset in PRESETS.items():
        eds = edits(preset)
        new = apply(lvl, eds)
        diff = [i for i in range(len(lvl)) if lvl[i] != new[i]]   # (8 MB scan, offline only)
        inside = all(any(o <= i < o + len(d) for o, d, _ in eds) for i in diff)
        kinds = {}
        for _, d, w in eds:
            k = ("vertex" if " vertex " in w or w.startswith("vertex") else "octree" if "octree" in w
                 else "face normal" if "triangle" in w else "edge normal" if w.endswith("normal") else "edge scalar")
            kinds[k] = kinds.get(k, 0) + 1
        # independent re-read with the G6-P12 reader on the edited copy
        L2 = m25.Level.__new__(m25.Level)
        L2.__dict__.update(L.__dict__)
        L2.b = new
        m2 = g6.parse_mesh(L2, allow["zdr"] - 4)
        moved = [k for k in range(m2["nv"]) if m2["verts"][k] != mesh["verts"][k]]
        dz_ok = all(abs(m2["verts"][k][2] - (mesh["verts"][k][2] - 1.5)) < 1e-5 and m2["verts"][k][:2] ==
                    mesh["verts"][k][:2] for k in moved)
        out[case] = {"preset": preset, "edits": eds, "new": new, "m2": m2, "moved": moved}
        res[f"O2 exact modification ({case})"] = {
            "ranges": len(eds), "bytes": sum(len(d) for _, d, _ in eds), "kinds": kinds,
            "differing_bytes": len(diff), "ok": len(new) == len(lvl) and inside and sorted(moved) == sorted(
                allow["presets"][preset]["vertices"]) and dz_ok and kinds.get("face normal") == 14
                and kinds.get("vertex") == 3 and edits(preset) == eds}

        fe, ee, se, classes, excess = integrity(L2, new, m2)
        fe0, ee0, se0, classes0, excess0 = integrity(L, lvl, mesh)
        moved_excess = max(math.dist(m2["verts"][k], m2["centre"]) - m2["radius"] for k in out[case]["moved"])
        sphere = moved_excess <= 0 and excess <= excess0
        # octree: every leaf's exact intersection with the edited geometry is within its list; boxes nest
        oct_ok, nest_ok, oct_n = True, True, 0
        root = L2.ptr(L2.ptr(allow["zdr"] - 4 + 0x14))
        stack = [(root, None)]
        tris = [(ei, j) for ei, e in enumerate(m2["elems"]) for j in range(e["nt"])]
        tpts = {t: [m2["verts"][q] for q in m2["elems"][t[0]]["idx"][3 * t[1]:3 * t[1] + 3]] for t in tris}
        tbox = {t: ([min(p[i] for p in v) for i in range(3)], [max(p[i] for p in v) for i in range(3)])
                for t, v in tpts.items()}
        while stack:
            nd, parent = stack.pop()
            oct_n += 1
            lo, hi = L2.f32s(nd, 3), L2.f32s(nd + 12, 3)
            if parent and not all(parent[0][i] <= lo[i] and hi[i] <= parent[1][i] for i in range(3)):
                nest_ok = False
            kids, lst = L2.ptr(nd + 0x18), L2.ptr(nd + 0x1C)
            if kids is not None:
                stack += [(L2.ptr(kids + 4 * q), (lo, hi)) for q in range(8) if L2.ptr(kids + 4 * q) is not None]
                continue
            items = set()
            if lst is not None:
                cnt, p = struct.unpack_from("<H", new, lst + 4)[0], lst + 6
                for _ in range(cnt):
                    el, x = new[p], new[p + 1]
                    tr, p = (((x & 0x7F) << 8) | new[p + 2], p + 3) if x & 0x80 else (x, p + 2)
                    items.add((el, tr))
            exact = {t for t in tris if all(tbox[t][0][i] <= hi[i] + 1e-4 and tbox[t][1][i] >= lo[i] - 1e-4
                                            for i in range(3)) and rm._tri_box(tpts[t], lo, hi)}
            if not exact <= items:
                oct_ok = False
        hdr = L2.f32s(L2.ptr(allow["zdr"] - 4 + 0x14) + 0xC, 6) == L2.f32s(root, 6)
        res[f"O3 geometry integrity ({case})"] = {
            "face_normal_max_err": fe, "edge_normal_max_err": ee, "one_triangle_scalar_max_err": se,
            "edge_scalar_classes": classes, "original": {"face": fe0, "edge": ee0, "classes": classes0,
                                                         "sphere_excess": excess0},
            "moved_vertices_sphere_margin": round(-moved_excess, 3), "inside_sphere": sphere, "octree_nodes": oct_n,
            "octree_leaves_cover_edited_triangles": oct_ok, "octree_boxes_nest": nest_ok, "octree_header_eq_root": hdr,
            "ok": fe <= max(fe0, 2.5e-5) and ee < 2e-6 and se < 2e-6 and classes["other"] == classes0["other"]
                  and classes["one"] == classes0["one"] and sphere and oct_ok and nest_ok
                  and hdr}
    m2 = out["mod"]["m2"]
    t33n = [m2["verts"][q] for q in m2["elems"][3]["idx"][3 * 33:3 * 33 + 3]]
    res["O3 lowered surface at the spawn point"] = round(bary(t33n, *SPAWN_XY)[3], 4)
    res["O2 presets disjoint"] = not ({o for o, _, _ in out["mod"]["edits"] if "octree" not in _}
                                     & {o for o, _, _ in out["control"]["edits"] if "octree" not in _})

    # O4 negative cases
    def refused(fn, code=None):
        try:
            fn()
        except rm.Refusal as x:
            return code is None or x.code == code
        return False
    vo = mesh["vo"] + 4
    base_spec = allow["presets"]["spawn-drop-1.50"]
    e3n = e3["nrm"] + 4 + 12 * 33
    e3en = L.ptr(e3["blk"] + 0x18) + 4

    def mut(o, b):
        x = bytearray(lvl)
        x[o:o + len(b)] = b
        return bytes(x)
    sp = lambda **kw: {**copy.deepcopy(base_spec), **kw}   # noqa: E731
    neg = {
        "wrong file hash (one byte changed)": refused(lambda: edits("spawn-drop-1.50", mut(0x100, b"\xAA"), ptr), "TARGET_CHANGED"),
        "wrong pointer-table hash": refused(lambda: edits("spawn-drop-1.50", lvl, ptr[:-4]), "TARGET_CHANGED"),
        "unexpected original vertex word": refused(lambda: edits("spawn-drop-1.50", mut(vo + 12 * 365 + 8, b"\xc1\x1a\x76\x39"), ptr, check_files=False), "TARGET_CHANGED"),
        "invalid vertex index": refused(lambda: edits("x", lvl, ptr, sp(vertices={9999: "00" * 12}), False), "TARGET_CHANGED"),
        "malformed face normal": refused(lambda: edits("spawn-drop-1.50", mut(e3n, struct.pack(">3f", 0.0, 0.6, 0.8)), ptr, check_files=False), "TARGET_CHANGED"),
        "malformed edge normal": refused(lambda: edits("spawn-drop-1.50", mut(e3en + 12 * rm_slot(L, e3, 33), struct.pack(">3f", 0.0, 0.6, 0.8)), ptr, check_files=False), "TARGET_CHANGED"),
        "displacement below the octree floor (-5.0)": refused(lambda: edits("x", lvl, ptr, sp(dz=-5.0), False), "TARGET_CHANGED"),
        "upward displacement (+1.0)": refused(lambda: edits("x", lvl, ptr, sp(dz=1.0), False), "TARGET_CHANGED"),
        "too small displacement (-0.1)": refused(lambda: edits("x", lvl, ptr, sp(dz=-0.1), False), "TARGET_CHANGED"),
        "integer displacement": refused(lambda: edits("x", lvl, ptr, sp(dz=-1), False), "TARGET_CHANGED"),
        "corrupted octree leaf list": refused(lambda: edits("spawn-drop-1.50", corrupt_leaf(lvl, ptr), ptr, check_files=False), "TARGET_CHANGED"),
    }
    gate_off = {}
    for name, o in (("gate off", op("spawn-drop-1.50")),):
        try:
            os.environ.pop(rm.STRUCT_ENV, None)
            rm.parse_collision_vertex_offset(o, "o")
            gate_off[name] = False
        except rm.Refusal as x:
            gate_off[name] = x.code == "UNSUPPORTED"
    os.environ[rm.STRUCT_ENV] = LEVEL
    try:
        manif = {
            "unknown preset": refused(lambda: rm.parse_collision_vertex_offset(op("spawn-drop-9.00"), "o"), "UNSUPPORTED"),
            "other level": refused(lambda: rm.parse_collision_vertex_offset({**op("spawn-drop-1.50"), "level": "intro_10"}, "o"), "UNSUPPORTED"),
            "extra key (an offset)": refused(lambda: rm.parse_collision_vertex_offset({**op("spawn-drop-1.50"), "offset": 1}, "o"), "BAD_MANIFEST"),
            "extra key (a displacement)": refused(lambda: rm.parse_collision_vertex_offset({**op("spawn-drop-1.50"), "dz": -1.5}, "o"), "BAD_MANIFEST"),
            "bad sha format": refused(lambda: rm.parse_collision_vertex_offset({**op("spawn-drop-1.50"), "lvl_sha256": "x"}, "o"), "BAD_MANIFEST"),
            "two presets in one mod": refused(lambda: rm.parse_manifest({"mod.json": json.dumps(manifest("t.two", op("spawn-drop-1.50"), op("control-far-drop-1.50"))).encode()}), "BAD_MANIFEST"),
            "manifest file hash differs": refused(lambda: rm.compile_collision_vertex_offset({**op("spawn-drop-1.50"), "lvl_sha256": "0" * 64}, {"game": GAME}), "TARGET_CHANGED"),
            "gameplay-affecting": rm.changes_game_logic({"overrides": [op("spawn-drop-1.50")]}),
        }
    finally:
        os.environ.pop(rm.STRUCT_ENV, None)
    res["O4 negative cases"] = {"edit": neg, "gate": gate_off, "manifest": manif,
                                "ok": all(neg.values()) and all(gate_off.values()) and all(manif.values())}

    # O5 delivery through the real mod tool (temporary mods root), determinism, priority conflict, gate
    o5 = {}
    with tempfile.TemporaryDirectory(dir=ROOT / "private" / "work") as td:
        td = Path(td)
        plans = {}
        for case, preset in PRESETS.items():
            for rep in (1, 2):
                w = td / f"{case}{rep}"
                imps, pl = make_plan(w, [manifest(f"{PREFIX}.{case}", op(preset))])
                text, rg = plan_ranges(pl["plan"]) if pl.get("plan") else ("", [])
                plans[(case, rep)] = (pl, text, rg)
            pl, text, rg = plans[(case, 1)]
            want = sorted(("intro_15.lvl", o, len(d)) for o, d, _ in out[case]["edits"])
            covered = sorted(rg) == want or (sum(n for _, _, n in rg) == sum(n for _, _, n in want) and all(
                any(o2 <= o < o2 + n2 for _, o2, n2 in rg) for _, o, _ in want))
            o5[case] = {"imports": [i.get("result") for i in imps], "plan_ranges": len(rg),
                        "covers_compiled_ranges": covered,
                        "deterministic": plans[(case, 1)][2] == plans[(case, 2)][2],
                        "gameplay_record": f"\ngameplay {PREFIX}.{case}\n" in text,
                        "non_overlapping": all(a[1] + a[2] <= b[1] for a, b in zip(rg, rg[1:]))}
        w = td / "nogate"
        imps, pl = make_plan(w, [manifest(f"{PREFIX}.ng", op("spawn-drop-1.50"))], env_extra={})
        o5["gate off: import refused"] = imps[0].get("result") != "ok" and "UNSUPPORTED" in json.dumps(imps[0])
        w = td / "conflict"
        imps, pl = make_plan(w, [manifest(f"{PREFIX}.a", op("spawn-drop-1.50")),
                                 manifest(f"{PREFIX}.b", op("spawn-drop-1.50"))])
        o5["conflicting second mod refused whole"] = {"plan_result": pl.get("result"), "active": pl.get("active"),
                                                      "shadowed": [x for x in pl.get("mods", []) if x.get("shadowed")]}
        o5["conflict ok"] = len(pl.get("active", [])) == 1
    o5["ok"] = all(o5[c]["covers_compiled_ranges"] and o5[c]["deterministic"] and o5[c]["gameplay_record"]
                   and o5[c]["non_overlapping"] and o5[c]["imports"] == ["ok"] for c in PRESETS) \
        and o5["gate off: import refused"] and o5["conflict ok"]
    res["O5 delivery and isolation"] = o5
    verdict = {k: v["ok"] if isinstance(v, dict) and "ok" in v else v for k, v in res.items()}
    print(json.dumps(verdict, indent=1))
    (ROOT / "private" / "work" / PREFIX).mkdir(parents=True, exist_ok=True)
    (ROOT / "private" / "work" / PREFIX / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    return 0 if all(v is True or (not isinstance(v, bool)) for v in verdict.values()) else 1


def rm_slot(L, e, j):
    """The edge slot of corner 0 of triangle j of element e (original file)."""
    mp = L.ptr(e["blk"] + 0x14)
    return struct.unpack_from(">H", L.b, mp + 4 + 6 * j)[0]


def corrupt_leaf(lvl, ptr):
    """A copy whose first octree leaf listing element 3 triangle 33 names another triangle instead."""
    eds = edits("spawn-drop-1.50")
    nodes = sorted(int(w.split("0x")[1].split()[0], 16) for _, _, w in eds if "octree node" in w)
    for nd in nodes:
        lst = struct.unpack_from(">I", lvl, nd + 0x1C)[0]
        if not lst:
            continue
        lst += 4
        cnt, p = struct.unpack_from("<H", lvl, lst)[0], lst + 2
        for _ in range(cnt):
            el, x = lvl[p], lvl[p + 1]
            tr, width = ((((x & 0x7F) << 8) | lvl[p + 2]), 3) if x & 0x80 else (x, 2)
            if (el, tr) == (3, 33):
                b = bytearray(lvl)
                b[p + width - 1] ^= 0x01            # triangle 33 -> 32
                return bytes(b)
            p += width
    raise SystemExit("no leaf lists element 3 triangle 33")


# ------------------------------------------------------------------------------------------------- hidden runs
def alive(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in r.stdout


def readback(process, gbase, eds):
    return [process.read(gbase + o - 4, len(d)) for o, d, _ in eds]


def run_case(tag, case, prefix=PREFIX, presets=None, read=None, steps=None, extra_env=None):
    """G6-P13 defaults; G6-P13b passes its own prefix, case -> preset map and the presets to read back (by name);
    G6-P15 also passes a frame schedule (steps text) and the draw-trace switch (extra_env)."""
    from m5_live import Actor, Process
    presets = PRESETS if presets is None else presets
    lvl, ptr = files()
    ix = rm.read_script_index(GAME, LEVEL)
    key = next(k for k in ix["placements"] if BRIDGE in k.split("\\"))
    bridge_so = [i["so"] for i in ix["placements"][key]]
    all_edits = ({c: edits(p) for c, p in PRESETS.items()} if read is None else {p: edits(p) for p in read})
    work = ROOT / "private" / "work" / prefix / tag / case
    run = f"{prefix}_{tag}_{case}"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    env.pop(rm.STRUCT_ENV, None)            # the game process never sees the development gate
    row = {"case": case, "run": run}
    if case in presets:
        imps, pl = make_plan(work, [manifest(f"{prefix}.{case}", op(presets[case]))])
        if pl.get("result") != "ok" or not pl.get("plan"):
            raise SystemExit(f"plan: {imps} {pl}")
        env["R3HD_MODS_PLAN"] = row["plan"] = pl["plan"]
        row["plan_ranges"] = plan_ranges(pl["plan"])[1]
    env.update(extra_env or {})
    (work / "steps.txt").write_text(steps or f"wait {SECONDS - 8}\n", encoding="ascii")
    samples, reads = [], {}
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(SECONDS), "--play", "--test-level", LEVEL,
                                 "--user-root", run], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        needle = re.compile(rf"[\\/]{LEVEL}\.lvl result=00000000", re.IGNORECASE)
        opened, vbase, end = None, None, time.monotonic() + 90
        while time.monotonic() < end and game.poll() is None and opened is None:
            time.sleep(0.5)
            lp = RUNS / run / "runtime.log"
            if lp.is_file():
                text = lp.read_text(errors="replace")
                opened = time.monotonic() if needle.search(text) else None
                m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
                vbase = m.group(1) if m else vbase
        pid = None
        if opened is None or vbase is None:
            row["error"] = "level did not open"
        else:
            pid = json.loads((RUNS / run / "process.json").read_text(encoding="utf-8-sig"))["pid"]
            disc = work / "discovery.json"
            p = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), vbase, str(disc),
                                "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
            process = Process(pid, int(vbase, 16))
            ray, bridges = None, []
            for x in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if p.returncode == 0 else []):
                try:
                    act = Actor(process, int(x["so"], 16))
                except Exception:
                    continue
                if act.model == RAY and ray is None:
                    ray = act
                elif act.model == BRIDGE:
                    bridges.append(act)
            cands = {}
            for b in bridges:
                for so in bridge_so:
                    cands.setdefault(b.so - so + 4, set()).add(b.so)
            gbase = max(cands, key=lambda k: len(cands[k])) if cands else None
            row["guest_base"] = hex(gbase) if gbase else None
            row["base_votes"] = len(cands[gbase]) if gbase else 0
            if ray is None or gbase is None:
                row["error"] = "rayman or bridges not found"
            else:
                reads["first"] = {c: [r.hex() if r else None for r in readback(process, gbase, e)]
                                  for c, e in all_edits.items()}
                t_end = time.monotonic() + SECONDS - 45
                while time.monotonic() < t_end and process.running():
                    try:
                        samples.append({"t": round(time.monotonic() - opened, 2), "pos": ray.position(),
                                        "beh": ray.comport()})
                    except Exception as x:
                        row["sampling_stopped"] = type(x).__name__
                        break
                    time.sleep(0.2)
                if process.running():
                    reads["last"] = {c: [r.hex() if r else None for r in readback(process, gbase, e)]
                                     for c, e in all_edits.items()}
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and alive(pid))
    row["reads"] = reads
    (work / "samples.json").write_text(json.dumps(samples) + "\n")
    (work / "row.json").write_text(json.dumps(row, indent=1) + "\n")
    return {k: v for k, v in row.items() if k not in ("reads", "plan_ranges")}


def summarize(samples):
    if not samples:
        return {"samples": 0}
    jump = next((b for a, b in zip(samples, samples[1:]) if math.dist(a["pos"], b["pos"]) > 5), None)
    att = next((s for s in samples if s["beh"] == "YAM_C_Attente"), None)
    settled = [s["pos"] for s in samples if att and att["t"] + 5 <= s["t"] <= att["t"] + 60]
    med = [statistics.median(p[i] for p in settled) for i in range(3)] if settled else None
    return {"samples": len(samples), "first_t": samples[0]["t"], "last_t": samples[-1]["t"],
            "placed": jump["pos"] if jump else None, "placed_t": jump["t"] if jump else None,
            "attente_t": att["t"] if att else None, "settled": med, "settled_n": len(settled),
            "settled_spread": round(max(math.dist(p, med) for p in settled), 4) if settled else None,
            "min_z": min(s["pos"][2] for s in samples), "behaviours": sorted({s["beh"] for s in samples})}


def judge(tag):
    lvl, _ = files()
    all_edits = {c: edits(p) for c, p in PRESETS.items()}
    orig = {c: [lvl[o:o + len(d)].hex() for o, d, _ in e] for c, e in all_edits.items()}
    newb = {c: [d.hex() for _, d, _ in e] for c, e in all_edits.items()}
    out = {}
    for case in CASES:
        work = ROOT / "private" / "work" / PREFIX / tag / case
        run = f"{PREFIX}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        log = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / run).glob("runtime*.log")))
        row["mods_off"] = "M33 mods=off" in log
        row["served"] = sorted({(f.lower(), int(o), int(n)) for _, f, o, n in
                                re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+) length=(\d+)", log)})
        row["gameplay_line"] = bool(re.search(r"M33 mods gameplay mod=\S+ achievements=not_awarded", log))
        row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
        opens = re.findall(r"[\\/]([A-Za-z0-9_]+)\.lvl result=00000000", log)
        after = opens[opens.index(LEVEL) + 1:] if LEVEL in opens else opens
        row["other_levels_after"] = [x for x in after if x.lower() not in (LEVEL, "transit", "fix")]
        row["fault_lines"] = len(FAULT.findall(log))
        judges = {}
        for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
            r = subprocess.run([sys.executable, str(TOOLS / t), "--run", run], cwd=ROOT, capture_output=True, text=True)
            judges[t] = r.returncode
            (work / f"{t}.log").write_text(r.stdout + r.stderr)
        row["judges"] = judges
        row["summary"] = summarize(json.loads((work / "samples.json").read_text()))
        out[case] = row
    b, m, c = (out[k]["summary"] for k in CASES)

    def reads_are(case, want):
        r = out[case].get("reads", {})
        return bool(r.get("first") and r.get("last")) and all(r[w][p] == want[p] for w in ("first", "last")
                                                               for p in PRESETS)

    def within(x, ref, d, dims=3):
        return bool(x and ref) and math.dist(x[:dims], ref[:dims]) < d
    invalid = [k for k in out if "error" in out[k] or not out[k]["summary"].get("samples")]
    if not b.get("attente_t") or b.get("last_t", 0) < (b.get("attente_t") or 1e9) + 60:
        invalid.append("base: no Attente or sampling too short")
    if not within(b.get("settled"), E462_SETTLED, 0.02):
        invalid.append("base: settled position differs from E-462 by more than 0.02")
    surf = -9.118 - 1.5
    checks = {
        "P1 delivery: exactly the plan's ranges served in mod / control; base mods=off, none served":
            out["base"]["mods_off"] and not out["base"]["served"]
            and all(out[k]["served"] == sorted((f, o, n) for f, o, n in out[k]["plan_ranges"]) for k in PRESETS),
        "P2 guest identity: edited bytes of its own preset, original bytes of the other, at both reads; base original":
            reads_are("mod", {"mod": newb["mod"], "control": orig["control"]})
            and reads_are("control", {"mod": orig["mod"], "control": newb["control"]})
            and reads_are("base", orig) and all(out[k].get("base_votes") == 7 for k in CASES),
        "P3 physical effect: mod settled z in [base - 1.85, base - 0.75], x, y within 1.0, spread <= 0.05, no fall":
            bool(m.get("settled") and b.get("settled")) and b["settled"][2] - 1.85 <= m["settled"][2] <= b["settled"][2] - 0.75
            and within(m["settled"], b["settled"], 1.0, 2) and (m.get("settled_spread") or 9) <= 0.05
            and m.get("min_z", -99) >= surf - 2.0 and m.get("attente_t") is not None,
        "P4 control: settled within 0.02 of base, calm behaviours, placed within 0.02 and Attente within 5 s":
            within(c.get("settled"), b.get("settled"), 0.02) and set(c.get("behaviours", [])) <= CALM
            and within(c.get("placed"), b.get("placed"), 0.02) and c.get("attente_t") is not None
            and abs(c["attente_t"] - b["attente_t"]) < 5 and within(m.get("placed"), b.get("placed"), 0.02, 2),
        "P5 safety: haptics line, M21/M22/M23 0, exit 0, no process left, no other level, no extra fault lines":
            all(out[k]["haptics_policy"] and not any(out[k]["judges"].values()) and out[k].get("runner_exit") == 0
                and not out[k].get("process_left") and not out[k]["other_levels_after"]
                and out[k]["fault_lines"] <= out["base"]["fault_lines"] for k in CASES),
        "P6 policy: gameplay line in mod and control only; gate-off compile refused":
            not out["base"]["gameplay_line"] and out["mod"]["gameplay_line"] and out["control"]["gameplay_line"]
            and gate_off_refused(),
    }
    delta = [round(m["settled"][i] - b["settled"][i], 4) for i in range(3)] if m.get("settled") and b.get(
        "settled") else None
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()),
              "mod_minus_base_settled": delta,
              "control_minus_base_settled": [round(c["settled"][i] - b["settled"][i], 4) for i in range(3)]
              if c.get("settled") and b.get("settled") else None,
              "base": b, "mod": m, "control": c,
              "secondary": {k: {x: out[k].get(x) for x in ("runner_exit", "sampling_stopped", "guest_base", "base_votes",
                                                           "fault_lines", "other_levels_after")} for k in out}}
    (ROOT / "private" / "work" / PREFIX / tag / "judge.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("invalid", "checks", "pass", "mod_minus_base_settled",
                                              "control_minus_base_settled", "secondary")}, indent=1))
    return 0 if result["pass"] else 1


def gate_off_refused():
    os.environ.pop(rm.STRUCT_ENV, None)
    try:
        rm.parse_collision_vertex_offset(op("spawn-drop-1.50"), "o")
    except rm.Refusal as x:
        return x.code == "UNSUPPORTED"
    return False


# ================================================================================================ G6-P13b (E-500)
P13B_DOC = """G6-P13b (D-267 / E-500): bounded collision deformation. PROTOCOL (committed before the modified run; not changed
after results).
Case `small`: one hidden run, same runner, entry and timing as G6-P13 g1, preset spawn-small-drop-0.30 (vertices
365 / 392 / 393 z - 0.30; 3 vertex words, 43 normal ranges, 6 edge scalars: 52 ranges, 552 bytes; no octree or bounding
box word changes; every moved vertex stays inside the octree root, the IPO +0x34 and +0x38 boxes and the AABB copy).
References reused, not rerun: G6-P13 g1 base and control (private/work/e499/g1): the same executable
(SHA-256 b7c6d5aa...b417, checked by `run.json`), the same level files and the same harness path; base settled
(-95.896, 56.433, -9.10416), spread 0, Attente 71.33 s.
Geometry (E-500 offline): within 0.5 units of the spawn point the edited surface lies exactly 0.300 lower (-9.4178
under the point); within 1.0 unit it is at least 0.251 lower; base stands 0.0136 above the surface. Expected settled
z -9.404 (base - 0.300).
Criteria (judged separately):
  P1 delivery: the run serves exactly its plan's ranges of intro_15.lvl (set of (file, offset, length) = plan records).
  P2 loaded bytes (corrected judge): at both reads (discovery, last sample), every range of all three presets reads as
     the original file with this run's own plan applied (shared words compared with the value the plan puts there);
     the plan's ranges must equal the compiled ranges and their new-byte hashes (judge independent of the run).
  P3 stable displacement: settled z - base settled z in [-0.35, -0.20] (excludes base and falling); settled x, y within
     0.25 of base's; settled spread <= 0.02; Attente reached, within 5 s of base's; no sample below z -9.60.
  P4 safety: haptics line, M21 / M22 / M23 0, runner exit 0, no process left, no other level opened, fault lines <= base.
  P5 isolation: gameplay record line present; gate-off compile refused; retained base logged mods=off; the G6-P13
     presets still compile byte-identical to g1's plans.
Classes: all PASS -> VERIFIED; P1 P2 PASS and P3 FAIL at base height -> PARTIAL; P3 FAIL by falling -> EXPERIMENT
FAILED; P1 / P2 FAIL -> BLOCKED. Invalid (rerun alone): level not opened, Rayman / bridges not found, sampling ends
before Attente + 60 s.
"""
P13B, SMALL = "e500", "spawn-small-drop-0.30"
ALL_PRESETS = ("spawn-drop-1.50", "control-far-drop-1.50", SMALL)
G1 = ROOT / "private" / "work" / "e499" / "g1"
G1_READ_KEYS = {"mod": "spawn-drop-1.50", "control": "control-far-drop-1.50"}


def plan_overlay(plan_path, preset):
    """{offset: new bytes} of one run's plan, checked against the compiled preset (offsets, lengths, new-byte hashes)."""
    if plan_path is None:
        return {}
    text = Path(plan_path).read_text(encoding="utf-8")
    recs = sorted((int(r[2]), int(r[3]), r[5]) for r in (ln.split() for ln in text.splitlines()
                                                         if ln.startswith("range ")))
    eds = edits(preset)
    mine = sorted((o, len(d), f"{rm.fnv1a64(d):016x}") for o, d, _ in eds)
    if recs != mine:
        raise SystemExit(f"plan {plan_path} does not match the compiled preset {preset}")
    return {o: d for o, d, _ in eds}


def p2_corrected(reads, read_keys, overlay):
    """Every read range must equal the original file with this run's overlay applied (byte level)."""
    lvl, _ = files()
    img = bytearray(lvl)
    for o, d in overlay.items():
        img[o:o + len(d)] = d
    compared = bad = 0
    for when in ("first", "last"):
        if when not in reads:
            return {"ok": False, "why": f"no {when} read"}
        for key, preset in read_keys.items():
            for (o, d, _), got in zip(edits(preset), reads[when][key]):
                compared += 1
                bad += got != bytes(img[o:o + len(d)]).hex()
    return {"ok": bad == 0 and compared > 0, "compared": compared, "mismatched": bad}


def replay_p2():
    """The corrected judge on G6-P13 g1's retained reads (base: no plan; mod / control: their own plans)."""
    out = {}
    for case, preset in (("base", None), ("mod", "spawn-drop-1.50"), ("control", "control-far-drop-1.50")):
        row = json.loads((G1 / case / "row.json").read_text())
        ov = plan_overlay(row.get("plan"), preset) if preset else {}
        out[case] = p2_corrected(row["reads"], G1_READ_KEYS, ov)
    # sensitivity: the same reads judged against the wrong plan must fail
    row = json.loads((G1 / "mod" / "row.json").read_text())
    out["mod judged as base (must fail)"] = p2_corrected(row["reads"], G1_READ_KEYS, {})
    out["base judged as mod (must fail)"] = p2_corrected(json.loads((G1 / "base" / "row.json").read_text())["reads"],
                                                        G1_READ_KEYS, plan_overlay(row["plan"], "spawn-drop-1.50"))
    return out


def check13b():
    res, (lvl, ptr) = {}, files()
    allow = rm.COLLISION_ALLOW[LEVEL]
    spec = allow["presets"][SMALL]
    eds = edits(SMALL)
    big = edits("spawn-drop-1.50")
    # O1 source identity (same files, mesh, vertices and ring as G6-P13)
    import m25_mesh_audit as m25
    import g6p12_collision_file_audit as g6
    L = m25.Level(LEVEL)
    mesh = g6.parse_mesh(L, allow["zdr"] - 4)
    ring = {(ei, j) for ei, e in enumerate(mesh["elems"]) for j in range(e["nt"])
            if set(spec["vertices"]) & set(e["idx"][3 * j:3 * j + 3])}
    res["O1 source identity"] = ((len(lvl), rm.sha256_bytes(lvl)) == allow["lvl"]
                                 and (len(ptr), rm.sha256_bytes(ptr)) == allow["ptr"] and ring == RING_SPAWN
                                 and spec["vertices"] == allow["presets"]["spawn-drop-1.50"]["vertices"])
    # O2 valid small deformation: derived data consistent over the whole mesh; octree lists cover; within bounds
    new = apply(lvl, eds)
    L2 = m25.Level.__new__(m25.Level)
    L2.__dict__.update(L.__dict__)
    L2.b = new
    m2 = g6.parse_mesh(L2, allow["zdr"] - 4)
    fe, ee, se, classes, excess = integrity(L2, new, m2)
    fe0, ee0, se0, classes0, excess0 = integrity(L, lvl, mesh)
    tris = [(ei, j) for ei, e in enumerate(m2["elems"]) for j in range(e["nt"])]
    tp = {t: [m2["verts"][q] for q in m2["elems"][t[0]]["idx"][3 * t[1]:3 * t[1] + 3]] for t in tris}
    tb = {t: ([min(p[i] for p in v) for i in range(3)], [max(p[i] for p in v) for i in range(3)]) for t, v in tp.items()}
    root = L2.ptr(L2.ptr(allow["zdr"] - 4 + 0x14))
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
    moved = [k for k in range(m2["nv"]) if m2["verts"][k] != mesh["verts"][k]]
    boxes = {"octree root": (L.f32s(root, 3), L.f32s(root + 12, 3)), "IPO +0x38": (L.f32s(0x159450, 3), L.f32s(0x159450 + 12, 3)),
             "IPO +0x34": (L.f32s(0x159438, 3), L.f32s(0x159438 + 12, 3)), "copy 0x378180": (L.f32s(0x37817C, 3), L.f32s(0x37817C + 12, 3))}
    inside = {n: all(lo[i] <= m2["verts"][k][i] <= hi[i] for k in moved for i in range(3)) for n, (lo, hi) in boxes.items()}
    margin = min(m2["verts"][k][2] for k in moved) - L.f32s(root, 3)[2]
    nondeg = all(rm._face(*tp[t]) is not None for t in ring)
    up = all(rm._face(*tp[t])[2] > 0.5 for t in ring)
    res["O2 valid small deformation"] = {
        "moved": sorted(moved), "dz": [round(m2["verts"][k][2] - mesh["verts"][k][2], 6) for k in sorted(moved)],
        "face_err": fe, "edge_err": ee, "scalar_one_err": se, "classes": classes, "classes_original": classes0,
        "octree_leaves": leaves, "octree_cover": cover, "inside_bounds": inside, "floor_margin": round(margin, 4),
        "ring_nondegenerate_upward": nondeg and up,
        "ok": sorted(moved) == sorted(spec["vertices"]) and fe <= max(fe0, 2.5e-5) and ee < 2e-6 and se < 2e-6
              and classes["other"] == classes0["other"] and classes["one"] == classes0["one"] and cover
              and all(inside.values()) and margin > 0 and nondeg and up}
    # O3 same-size modification
    diff = [i for i in range(len(lvl)) if lvl[i] != new[i]]
    no_bounds = not any("octree" in w for _, _, w in eds)
    res["O3 same-size modification"] = {
        "ranges": len(eds), "bytes": sum(len(d) for _, d, _ in eds), "differing_bytes": len(diff),
        "octree_or_box_words": not no_bounds,
        "ok": len(new) == len(lvl) and all(any(o <= i < o + len(d) for o, d, _ in eds) for i in diff)
              and no_bounds and edits(SMALL) == eds
              and all(a[0] + len(a[1]) <= b[0] for a, b in zip(eds, eds[1:]))
              and {o for o, _, _ in eds} <= {o for o, _, _ in big}}

    # O4 negative cases (small preset)
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
    vo = mesh["vo"] + 4
    sp = lambda **kw: {**copy.deepcopy(spec), **kw}   # noqa: E731
    box_mut = mut(0x159454 + 8, struct.pack(">f", -9.2))   # IPO box min z raised above the moved vertices
    neg = {
        "wrong file hash": refused(lambda: edits(SMALL, mut(0x100, b"\xAA"), ptr)),
        "original vertex word changed": refused(lambda: edits(SMALL, mut(vo + 12 * 393 + 8, b"\xc1\x0f\xb3\xad"), ptr,
                                                             check_files=False)),
        "a moved vertex would leave the IPO +0x38 box": refused(lambda: edits(SMALL, box_mut, ptr, check_files=False)),
        "AABB copy differs from the IPO box": refused(lambda: edits(SMALL, mut(0x378180, b"\x00\x00\x00\x00"), ptr,
                                                                   check_files=False)),
        "bounds kept but displacement leaves the octree root (-0.9)": refused(lambda: edits("x", lvl, ptr, sp(dz=-0.9), False)),
        "displacement -0.2 (outside the guard)": refused(lambda: edits("x", lvl, ptr, sp(dz=-0.2), False)),
        "corrupted octree leaf list": refused(lambda: edits(SMALL, corrupt_leaf(lvl, ptr), ptr, check_files=False)),
    }
    os.environ[rm.STRUCT_ENV] = LEVEL
    try:
        neg["unknown preset"] = refused(lambda: rm.parse_collision_vertex_offset(op("spawn-small-drop-0.40"), "o"), "UNSUPPORTED")
        neg["raw displacement key"] = refused(lambda: rm.parse_collision_vertex_offset({**op(SMALL), "dz": -0.3}, "o"), "BAD_MANIFEST")
        neg["two presets in one mod"] = refused(lambda: rm.parse_manifest({"mod.json": json.dumps(
            manifest("t.two", op(SMALL), op("control-far-drop-1.50"))).encode()}), "BAD_MANIFEST")
    finally:
        os.environ.pop(rm.STRUCT_ENV, None)
    res["O4 negative cases"] = {"cases": neg, "ok": all(neg.values())}
    # O5 policy and regression: gate, gameplay, real plan, G6-P13 presets unchanged, corrected P2 replay
    o5 = {"gate off refused": gate_off_refused(),
          "gameplay-affecting": rm.changes_game_logic({"overrides": [op(SMALL)]})}
    for case, preset in G1_READ_KEYS.items():
        row = json.loads((G1 / case / "row.json").read_text())
        try:
            plan_overlay(row["plan"], preset)
            o5[f"{preset} byte-identical to g1 plan"] = True
        except SystemExit:
            o5[f"{preset} byte-identical to g1 plan"] = False
    with tempfile.TemporaryDirectory(dir=ROOT / "private" / "work") as td:
        imps, pl = make_plan(Path(td) / "a", [manifest(f"{P13B}.small", op(SMALL))])
        o5["plan ok"] = pl.get("result") == "ok" and bool(pl.get("plan"))
        if o5["plan ok"]:
            plan_overlay(pl["plan"], SMALL)
            o5["plan gameplay record"] = f"\ngameplay {P13B}.small\n" in Path(pl["plan"]).read_text(encoding="utf-8")
        imps, pl = make_plan(Path(td) / "b", [manifest(f"{P13B}.ng", op(SMALL))], env_extra={})
        o5["gate-off import refused"] = imps[0].get("result") != "ok"
    rp = replay_p2()
    o5["corrected P2 replay on g1"] = rp
    o5["ok"] = (all(v for k, v in o5.items() if isinstance(v, bool)) and rp["base"]["ok"] and rp["mod"]["ok"]
                and rp["control"]["ok"] and not rp["mod judged as base (must fail)"]["ok"]
                and not rp["base judged as mod (must fail)"]["ok"])
    res["O5 policy and regression"] = o5
    verdict = {k: (v if isinstance(v, bool) else v["ok"]) for k, v in res.items()}
    print(json.dumps(verdict, indent=1))
    (ROOT / "private" / "work" / P13B).mkdir(parents=True, exist_ok=True)
    (ROOT / "private" / "work" / P13B / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    return 0 if all(verdict.values()) else 1


def run13b(tag):
    exe = json.loads((RUNS / "e499_g1_base" / "run.json").read_text(encoding="utf-8-sig"))["executable_sha256"]
    cur = rm.sha256_bytes((ROOT / "private/work/rex/out/build/win-amd64-release/r3hd.exe").read_bytes())
    if exe != cur:
        raise SystemExit("the executable differs from the retained references' (run fresh controls)")
    return run_case(tag, "small", prefix=P13B, presets={"small": SMALL}, read=ALL_PRESETS)


def judge13b(tag):
    work = ROOT / "private" / "work" / P13B / tag / "small"
    run = f"{P13B}_{tag}_small"
    row = json.loads((work / "row.json").read_text())
    log = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / run).glob("runtime*.log")))
    served = sorted({(f.lower(), int(o), int(n)) for _, f, o, n in
                     re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+) length=(\d+)", log)})
    s = summarize(json.loads((work / "samples.json").read_text()))
    b = summarize(json.loads((G1 / "base" / "samples.json").read_text()))
    blog = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / "e499_g1_base").glob("runtime*.log")))
    judges = {}
    for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        r = subprocess.run([sys.executable, str(TOOLS / t), "--run", run], cwd=ROOT, capture_output=True, text=True)
        judges[t] = r.returncode
        (work / f"{t}.log").write_text(r.stdout + r.stderr)
    opens = re.findall(r"[\\/]([A-Za-z0-9_]+)\.lvl result=00000000", log)
    after = opens[opens.index(LEVEL) + 1:] if LEVEL in opens else opens
    other = [x for x in after if x.lower() not in (LEVEL, "transit", "fix")]
    p2 = p2_corrected(row.get("reads", {}), {p: p for p in ALL_PRESETS}, plan_overlay(row["plan"], SMALL))
    dz = s["settled"][2] - b["settled"][2] if s.get("settled") and b.get("settled") else None
    invalid = []
    if "error" in row or not s.get("samples"):
        invalid.append(row.get("error", "no samples"))
    if s.get("attente_t") and s.get("last_t", 0) < s["attente_t"] + 60:
        invalid.append("sampling ended before Attente + 60 s")
    pre = []
    for preset in G1_READ_KEYS.values():
        try:
            plan_overlay(json.loads((G1 / {v: k for k, v in G1_READ_KEYS.items()}[preset] / "row.json").read_text())["plan"],
                         preset)
            pre.append(True)
        except SystemExit:
            pre.append(False)
    checks = {
        "P1 delivery: exactly the plan's ranges served": served == sorted(plan_ranges(row["plan"])[1]),
        "P2 loaded bytes (corrected): every read equals the original with this run's plan applied": p2["ok"],
        "P3 stable displacement: dz in [-0.35, -0.20], x, y within 0.25, spread <= 0.02, Attente within 5 s, min z >= -9.60":
            dz is not None and -0.35 <= dz <= -0.20 and math.dist(s["settled"][:2], b["settled"][:2]) <= 0.25
            and (s.get("settled_spread") if s.get("settled_spread") is not None else 9) <= 0.02
            and s.get("attente_t") is not None and abs(s["attente_t"] - b["attente_t"]) < 5 and s["min_z"] >= -9.60,
        "P4 safety: haptics, M21/M22/M23 0, exit 0, no process left, no other level, fault lines <= base":
            "M23 haptics policy=suppressed physical_pad_drivers=none" in log and not any(judges.values())
            and row.get("runner_exit") == 0 and not row.get("process_left") and not other
            and len(FAULT.findall(log)) <= len(FAULT.findall(blog)),
        "P5 isolation: gameplay line, gate-off refused, retained base mods=off, G6-P13 presets unchanged":
            bool(re.search(r"M33 mods gameplay mod=\S+ achievements=not_awarded", log)) and gate_off_refused()
            and "M33 mods=off" in blog and all(pre),
    }
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()),
              "small_minus_base_settled_z": round(dz, 5) if dz is not None else None, "p2": p2,
              "small": s, "base_retained": b, "guest_base": row.get("guest_base"), "base_votes": row.get("base_votes"),
              "runner_exit": row.get("runner_exit"), "judges": judges, "other_levels": other}
    (work.parent / "judge.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: result[k] for k in ("invalid", "checks", "pass", "small_minus_base_settled_z", "p2",
                                              "guest_base", "base_votes")}, indent=1))
    return 0 if result["pass"] else 1


# ================================================================================================ G6-P15 (E-502)
P15_DOC = """G6-P15 (D-269 / E-502): synchronized visual + collision surface edit. PROTOCOL (committed before the modified
runs; thresholds not changed after results).
Cases (one hidden run each, same runner / entry / 230 s / no input as G6-P13b, plus R3HD_M22_DRAW_TRACE=1 and two
explicit frame requests, `frame a` at 120 s and `frame b` at 140 s after the runner starts; 2 readbacks per run, 4 in
total, cap 8):
  ref  preset spawn-small-drop-0.30 (the verified collision-only edit; the retained G6-P13b run s1 has no frames or
       draw traces, so a fresh traced reference is needed)
  vis  preset spawn-small-drop-0.30-visual (the same 52 collision ranges + 3 visual z words + 14 visual face normals:
       69 ranges / 732 bytes)
Observed: as G6-P13b (Rayman every 0.2 s; every range of the combined preset read back at discovery and at the last
sample) plus the two traced frames per run.
Criteria (judged separately):
  P1 delivery: each run serves exactly its plan's ranges of intro_15.lvl.
  P2 loaded geometry: corrected judge (D-267): every combined-preset range reads as the original file with the run's
     own plan applied, at both reads (vis: visual and collision edited; ref: visual original, collision edited).
  P3 GPU draw data: in every traced frame of both runs, a draw whose first vertex binding is element 14's de-indexed
     triangle list (240 corners, stride 32) is present; its corner positions equal the run's expected element 14
     geometry in element order (vis: the three edited vertices' corners carry the new z; ref: originals); all its
     other bytes are equal between ref and vis. Element 0's draw (1,593 corners, stride 24) is checked the same way
     when present (reported, not required).
  P4 physics and camera: vis settled position within 0.02 of ref's, and both within 0.02 of -9.40416 (G6-P13b);
     spread <= 0.02 each; no sample below -9.60; the element-14 draw's c0..c3 equal between ref and vis frames of the
     same label within 1e-3 (same camera).
  P5 visual result and safety: footprint mask = the screen pixels of the 14 edited visual triangles (ref and vis
     positions, c0..c3 of the element-14 draw of that frame, 1280 x 720 viewport mapping as tools/hdl_raycast.py,
     dilated 2 px); D = pixels whose RGB differs by more than 4 in any channel between ref and vis frames of the same
     label; N = the same between frames a and b of one run, inside the mask (max over runs). Pass needs, for frame a:
     D inside the mask >= max(20, 3 x N); plus haptics line, M21 / M22 / M23 0, runner exit 0, no process left, no
     other level, fault lines <= base's (G6-P13 g1). Locality (share of D inside the mask) is reported, not judged.
Classes: P1-P5 PASS -> VERIFIED; P1 P2 PASS and P3 FAIL -> PARTIAL (geometry loaded, render effect unverified) or
EXPERIMENT FAILED if the draw keeps the old z; P3 PASS and P5 pixel test FAIL -> PARTIAL; P4 FAIL -> PHYSICS
MISMATCH. Invalid (rerun the case alone): level not opened, Rayman not found, a traced frame missing, or element 14's
draw absent from a frame in both runs (camera does not see the surface: a new decision, not a threshold change).
"""
P15, VISP = "e502", "spawn-small-drop-0.30-visual"
P15_CASES = {"ref": SMALL, "vis": VISP}
P15_STEPS = "wait 120\nframe a\nwait 20\nframe b\nwait 82\n"
E14 = (240, 32)
E0 = (1593, 24)


def visual_model(img):
    """Element 14 / element 0 corner positions (bytes, element order) of the visual object in a file image."""
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
        out[k] = ([img[vp + 4 + 12 * j:vp + 16 + 12 * j] for j in idx], idx)
    return out


def check15():
    res, (lvl, ptr) = {}, files()
    allow = rm.COLLISION_ALLOW[LEVEL]
    spec = allow["presets"][VISP]
    v, s = edits(VISP), edits(SMALL)
    vis = [x for x in v if x[2].startswith("visual")]
    col = [x for x in v if not x[2].startswith("visual")]
    import m25_mesh_audit as m25
    import g6p12_collision_file_audit as g6
    L = m25.Level(LEVEL)
    go = 0x15C74 - 4
    nv, ne = struct.unpack_from(">HH", L.b, go + 0x24 + 4)
    vp = L.ptr(go)
    cm = g6.parse_mesh(L, allow["zdr"] - 4)
    mapping = {k: math.dist(L.f32s(vp + 12 * k, 3), cm["verts"][c]) for k, (_, c) in spec["visual"]["map"].items()}
    model = visual_model(lvl)
    spawn_tri = model[14][1][3 * 32:3 * 32 + 3]
    res["O1 source identity"] = ((len(lvl), rm.sha256_bytes(lvl)) == allow["lvl"]
                                 and (len(ptr), rm.sha256_bytes(ptr)) == allow["ptr"] and (nv, ne) == (3543, 15)
                                 and all(d < 0.001 for d in mapping.values()) and spawn_tri == (1188, 1134, 1187)
                                 and all(lvl[vp + 4 + 12 * k:vp + 16 + 12 * k].hex() == h
                                         for k, (h, _) in spec["visual"]["map"].items()))
    # O2 combined integrity: image check with the G6-P12 reader + face-normal rule on the edited visual ring
    new = apply(lvl, v)
    L2 = m25.Level.__new__(m25.Level)
    L2.__dict__.update(L.__dict__)
    L2.b = new
    moved = [k for k in range(nv) if L2.f32s(vp + 12 * k, 3) != L.f32s(vp + 12 * k, 3)]
    dz_ok = all(abs(L2.f32s(vp + 12 * k, 3)[2] - L.f32s(vp + 12 * k, 3)[2] + 0.3) < 1e-5 for k in moved)
    ep = L.ptr(go + 0x14)
    fe, ring = 0.0, 0
    for k in range(ne):
        el = L.ptr(ep + 4 * k)
        nt = struct.unpack_from(">H", new, el + 8)[0]
        idx = struct.unpack_from(f">{3 * nt}H", new, L.ptr(el + 0xC) + 4)
        fn = L.ptr(el + 0x14)
        for j in range(nt):
            t = idx[3 * j:3 * j + 3]
            if set(t) & set(moved):
                ring += 1
                f = rm._face(*(L2.f32s(vp + 12 * q, 3) for q in t))
                fe = max(fe, math.dist(f, L2.f32s(fn + 12 * j, 3)))
    diff = [i for i in range(len(lvl)) if lvl[i] != new[i]]
    # collision spawn surface and visual spawn surface after the edit (both -0.30)
    res["O2 combined edit integrity"] = {
        "ranges": len(v), "bytes": sum(len(d) for _, d, _ in v), "visual_ranges": len(vis),
        "visual_bytes": sum(len(d) for _, d, _ in vis), "moved_visual": moved, "ring": ring,
        "visual_face_normal_err": fe, "differing_bytes": len(diff),
        "ok": len(new) == len(lvl) and sorted(moved) == sorted(spec["visual"]["map"]) and dz_ok and ring == 14
              and fe < 1e-6 and all(any(o <= i < o + len(d) for o, d, _ in v) for i in diff)}
    res["O3 collision equivalence"] = col == s and not any(
        allow["zdr"] - 0x100 > o for o, _, _ in col)   # all collision ranges after the visual data
    # O4 negatives + determinism
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
    sp = copy.deepcopy(spec)
    sp["visual"]["map"][1134] = ("00" * 12, 365)
    sp2 = copy.deepcopy(spec)
    sp2["visual"]["ring"] = 13
    sp3 = copy.deepcopy(spec)
    sp3["visual"]["map"][1135] = (lvl[vp + 4 + 12 * 1135:vp + 16 + 12 * 1135].hex(), 365)
    fn14 = L.ptr(L.ptr(ep + 4 * 14) + 0x14) + 4
    neg = {
        "wrong file hash": refused(lambda: edits(VISP, mut(0x100, b"\xAA"), ptr)),
        "visual original word changed": refused(lambda: edits(VISP, mut(0x19200, b"\xc1\x1a\x76\x3d"), ptr, check_files=False)),
        "visual expected value wrong in preset": refused(lambda: edits("x", lvl, ptr, sp, False)),
        "visual vertex not coincident with its collision vertex": refused(lambda: edits("x", lvl, ptr, sp3, False)),
        "visual ring count mismatch": refused(lambda: edits("x", lvl, ptr, sp2, False)),
        "malformed visual face normal": refused(lambda: edits(VISP, mut(fn14 + 12 * 32, struct.pack(">3f", 0.0, 0.6, 0.8)), ptr, check_files=False)),
        "collision original word changed": refused(lambda: edits(VISP, mut(cm["vo"] + 4 + 12 * 365 + 8, b"\xc1\x1a\x76\x39"), ptr, check_files=False)),
        "deterministic": edits(VISP) == v,
    }
    os.environ[rm.STRUCT_ENV] = LEVEL
    try:
        neg["unknown preset"] = refused(lambda: rm.parse_collision_vertex_offset(op(VISP + "x"), "o"), "UNSUPPORTED")
        neg["raw offset key"] = refused(lambda: rm.parse_collision_vertex_offset({**op(VISP), "offset": 0x19200}, "o"), "BAD_MANIFEST")
        neg["two presets in one mod (collision + combined)"] = refused(lambda: rm.parse_manifest({"mod.json": json.dumps(
            manifest("t.two", op(SMALL), op(VISP))).encode()}), "BAD_MANIFEST")
    finally:
        os.environ.pop(rm.STRUCT_ENV, None)
    res["O4 negative and deterministic"] = {"cases": neg, "ok": all(neg.values())}
    # O5 delivery and policy
    o5 = {"gate off refused": gate_off_refused(),
          "gameplay-affecting": rm.changes_game_logic({"overrides": [op(VISP)]})}
    with tempfile.TemporaryDirectory(dir=ROOT / "private" / "work") as td:
        imps, pl = make_plan(Path(td) / "a", [manifest(f"{P15}.vis", op(VISP))])
        o5["plan ok"] = pl.get("result") == "ok" and bool(pl.get("plan"))
        if o5["plan ok"]:
            plan_overlay(pl["plan"], VISP)
            text = Path(pl["plan"]).read_text(encoding="utf-8")
            o5["plan gameplay record"] = f"\ngameplay {P15}.vis\n" in text
            o5["plan ranges"] = len(plan_ranges(pl["plan"])[1])
        imps, pl = make_plan(Path(td) / "b", [manifest(f"{P15}.a", op(SMALL)), manifest(f"{P15}.b", op(VISP))])
        o5["conflicting second mod refused whole"] = len(pl.get("active", [])) == 1
        imps, pl = make_plan(Path(td) / "c", [manifest(f"{P15}.ng", op(VISP))], env_extra={})
        o5["gate-off import refused"] = imps[0].get("result") != "ok"
    for case, preset in G1_READ_KEYS.items():
        row = json.loads((G1 / case / "row.json").read_text())
        try:
            plan_overlay(row["plan"], preset)
            o5[f"{preset} unchanged (g1 plan)"] = True
        except SystemExit:
            o5[f"{preset} unchanged (g1 plan)"] = False
    try:
        plan_overlay(json.loads((ROOT / "private/work/e500/s1/small/row.json").read_text())["plan"], SMALL)
        o5[f"{SMALL} unchanged (s1 plan)"] = True
    except SystemExit:
        o5[f"{SMALL} unchanged (s1 plan)"] = False
    o5["ok"] = all(x for x in o5.values() if isinstance(x, bool))
    res["O5 delivery and policy"] = o5
    verdict = {k: (x if isinstance(x, bool) else x["ok"]) for k, x in res.items()}
    print(json.dumps(verdict, indent=1))
    (ROOT / "private" / "work" / P15).mkdir(parents=True, exist_ok=True)
    (ROOT / "private" / "work" / P15 / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    return 0 if all(verdict.values()) else 1


def run15(tag):
    exe = json.loads((RUNS / "e499_g1_base" / "run.json").read_text(encoding="utf-8-sig"))["executable_sha256"]
    cur = rm.sha256_bytes((ROOT / "private/work/rex/out/build/win-amd64-release/r3hd.exe").read_bytes())
    if exe != cur:
        raise SystemExit("the executable differs from the retained references'")
    return [run_case(tag, c, prefix=P15, presets=P15_CASES, read=(VISP,), steps=P15_STEPS,
                     extra_env={"R3HD_M22_DRAW_TRACE": "1"}) for c in P15_CASES]


def _frames(run):
    import m22_draw_report as rep
    d = RUNS / run
    out = []
    for t in sorted(d.glob("m22_draws_*.bin")):
        draws, _, _ = rep.parse(t)
        out.append((t.name, draws, d / t.name.replace("m22_draws_", "m3_frame_").replace(".bin", ".bmp")))
    return out


def _find(draws, shape):
    n, st = shape
    return [x for x in draws if x["bindings"] and x["bindings"][0]["stride"] == st
            and x["bindings"][0]["size"] == n * st]


def _clip(d, p):
    import m22_draw_report as rep
    c = d["consts"]
    m = [[rep.f32(c[r * 4 + j]) for j in range(4)] for r in range(4)]
    return [sum(m[r][j] * (p[j] if j < 3 else 1.0) for j in range(4)) for r in range(4)]


def _mask(d, tris_pts, w, h, dil=2):
    mask = set()
    for tri in tris_pts:
        cl = [_clip(d, p) for p in tri]
        if any(c[3] <= 1e-6 for c in cl):
            continue
        sp = [((c[0] / c[3] + 1) * w / 2, (1 - c[1] / c[3]) * h / 2) for c in cl]
        x0, x1 = int(max(0, min(x for x, _ in sp) - dil)), int(min(w - 1, max(x for x, _ in sp) + dil))
        y0, y1 = int(max(0, min(y for _, y in sp) - dil)), int(min(h - 1, max(y for _, y in sp) + dil))
        (ax, ay), (bx, by), (cx, cy) = sp
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                for ox, oy in ((0, 0), (dil, 0), (-dil, 0), (0, dil), (0, -dil)):
                    px, py = x + 0.5 + ox, y + 0.5 + oy
                    l1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
                    l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
                    if min(l1, l2, 1 - l1 - l2) >= -1e-6:
                        mask.add((x, y))
                        break
    return mask


def _pixels(path):
    """Uncompressed 24 / 32-bit BMP -> (w, h, {(x, y): (R, G, B)}), top row y = 0 (as tools/hdl_light_pixels.py)."""
    b = Path(path).read_bytes()
    off = struct.unpack_from("<I", b, 10)[0]
    w, h = struct.unpack_from("<ii", b, 18)
    bpp = struct.unpack_from("<H", b, 28)[0]
    bh, step = abs(h), bpp // 8
    stride = ((w * bpp // 8) + 3) & ~3
    out = {}
    for y in range(bh):
        row = off + ((bh - 1 - y) if h > 0 else y) * stride
        for x in range(w):
            o = row + x * step
            out[(x, y)] = (b[o + 2], b[o + 1], b[o])
    return w, bh, out


def _diff(a, b, thr=4):
    return {k for k, v in a.items() if max(abs(v[i] - b[k][i]) for i in range(3)) > thr}


def judge15(tag):
    lvl, _ = files()
    out = {}
    for case, preset in P15_CASES.items():
        work = ROOT / "private" / "work" / P15 / tag / case
        run = f"{P15}_{tag}_{case}"
        row = json.loads((work / "row.json").read_text())
        log = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / run).glob("runtime*.log")))
        served = sorted({(f.lower(), int(o), int(n)) for _, f, o, n in
                         re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+) length=(\d+)", log)})
        ov = plan_overlay(row["plan"], preset)
        img = bytearray(lvl)
        for o, d in ov.items():
            img[o:o + len(d)] = d
        judges = {}
        for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
            r = subprocess.run([sys.executable, str(TOOLS / t), "--run", run], cwd=ROOT, capture_output=True, text=True)
            judges[t] = r.returncode
            (work / f"{t}.log").write_text(r.stdout + r.stderr)
        opens = re.findall(r"[\\/]([A-Za-z0-9_]+)\.lvl result=00000000", log)
        after = opens[opens.index(LEVEL) + 1:] if LEVEL in opens else opens
        out[case] = {"row": row, "log": log, "served": served, "plan": sorted(plan_ranges(row["plan"])[1]),
                     "p2": p2_corrected(row.get("reads", {}), {VISP: VISP}, ov), "model": visual_model(bytes(img)),
                     "summary": summarize(json.loads((work / "samples.json").read_text())), "judges": judges,
                     "other": [x for x in after if x.lower() not in (LEVEL, "transit", "fix")],
                     "frames": _frames(run)}
    orig = visual_model(lvl)
    R, V = out["ref"], out["vis"]
    invalid = [c for c in out if "error" in out[c]["row"] or len(out[c]["frames"]) != 2]
    # P3: element 14 (and 0) draws per frame
    p3, e0, cams, footprint = [], [], [], {}
    for fi in range(min(len(R["frames"]), len(V["frames"]))):
        per = {}
        for case, x in (("ref", R), ("vis", V)):
            name, draws, _ = x["frames"][fi]
            per[case] = {k: _find(draws, shape) for k, shape in ((14, E14), (0, E0))}
        ok = True
        for k in (14, 0):
            for case, x in (("ref", R), ("vis", V)):
                want = x["model"][k][0]
                hit = [d for d in per[case][k] if [d["bindings"][0]["data"][i * d["bindings"][0]["stride"]:
                                                                               i * d["bindings"][0]["stride"] + 12]
                                                   for i in range(len(want))] == want]
                per[case][f"match{k}"] = hit
            if per["ref"][f"match{k}"] and per["vis"][f"match{k}"]:
                a, b = per["ref"][f"match{k}"][0]["bindings"][0], per["vis"][f"match{k}"][0]["bindings"][0]
                st = a["stride"]
                rest_equal = all(a["data"][i * st + 12:(i + 1) * st] == b["data"][i * st + 12:(i + 1) * st]
                                 for i in range(len(a["data"]) // st))
                changed = [i for i in range(len(a["data"]) // st) if a["data"][i * st:i * st + 12] !=
                           b["data"][i * st:i * st + 12]]
                corners = [i for i, j in enumerate(orig[k][1]) if j in (1134, 1187, 1188)]
                res_k = {"rest_equal": rest_equal, "changed_corners": len(changed),
                         "edited_corners": len(corners), "changed_are_edited": sorted(changed) == sorted(corners)}
            else:
                res_k = {"present": {c: bool(per[c][f"match{k}"]) for c in per},
                         "candidates": {c: len(per[c][k]) for c in per}}
            if k == 14:
                ok = ok and bool(res_k.get("rest_equal")) and res_k.get("changed_are_edited", False)
                p3.append(res_k)
            else:
                e0.append(res_k)
        if per["ref"]["match14"] and per["vis"]["match14"]:
            ca, cb = per["ref"]["match14"][0]["consts"][:16], per["vis"]["match14"][0]["consts"][:16]
            import m22_draw_report as rep
            cams.append(max(abs(rep.f32(x) - rep.f32(y)) for x, y in zip(ca, cb)))
            footprint[fi] = (per["ref"]["match14"][0], per["vis"]["match14"][0])
    rs, vs = R["summary"], V["summary"]
    # P5 pixels
    pix = {}
    if len(R["frames"]) == 2 and len(V["frames"]) == 2 and 0 in footprint:
        w, h, ra = _pixels(R["frames"][0][2])
        _, _, va = _pixels(V["frames"][0][2])
        _, _, rb = _pixels(R["frames"][1][2])
        _, _, vb = _pixels(V["frames"][1][2])
        dref, dvis = footprint[0]
        verts_o = [struct.unpack(">3f", c) for c in orig[14][0]]
        verts_n = [struct.unpack(">3f", c) for c in V["model"][14][0]]
        ring = [t for t in range(len(verts_o) // 3) if set(orig[14][1][3 * t:3 * t + 3]) & {1134, 1187, 1188}]
        tris = [verts_o[3 * t:3 * t + 3] for t in ring] + [verts_n[3 * t:3 * t + 3] for t in ring]
        m0 = orig[0]
        ring0 = [t for t in range(len(m0[1]) // 3) if set(m0[1][3 * t:3 * t + 3]) & {1134, 1187, 1188}]
        tris += [[struct.unpack(">3f", c) for c in m0[0][3 * t:3 * t + 3]] for t in ring0]
        tris += [[struct.unpack(">3f", c) for c in V["model"][0][0][3 * t:3 * t + 3]] for t in ring0]
        mask = _mask(dvis, tris, w, h)
        D = _diff(ra, va)
        Nr, Nv = _diff(ra, rb), _diff(va, vb)
        n_in = max(len(Nr & mask), len(Nv & mask))
        pix = {"size": [w, h], "mask_px": len(mask), "D_total": len(D), "D_in_mask": len(D & mask),
               "noise_in_mask": n_in, "noise_total": max(len(Nr), len(Nv)),
               "locality": round(len(D & mask) / len(D), 4) if D else None,
               "D_bbox": [min(x for x, _ in D), min(y for _, y in D), max(x for x, _ in D), max(y for _, y in D)] if D else None,
               "mask_bbox": [min(x for x, _ in mask), min(y for _, y in mask), max(x for x, _ in mask), max(y for _, y in mask)] if mask else None,
               "D_mean_abs_in_mask": round(sum(max(abs(ra[k][i] - va[k][i]) for i in range(3)) for k in D & mask) / max(1, len(D & mask)), 2)}
    blog = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / "e499_g1_base").glob("runtime*.log")))
    checks = {
        "P1 delivery": all(x["served"] == x["plan"] for x in out.values()),
        "P2 loaded geometry (corrected)": all(x["p2"]["ok"] for x in out.values()),
        "P3 GPU draw data: element 14 draw present, corners as expected, only the edited corners differ": bool(p3) and all(
            q.get("rest_equal") and q.get("changed_are_edited") for q in p3),
        "P4 physics and camera": bool(rs.get("settled") and vs.get("settled"))
            and math.dist(rs["settled"], vs["settled"]) <= 0.02 and abs(vs["settled"][2] + 9.40416) <= 0.02
            and abs(rs["settled"][2] + 9.40416) <= 0.02 and max(rs["settled_spread"], vs["settled_spread"]) <= 0.02
            and min(rs["min_z"], vs["min_z"]) >= -9.60 and bool(cams) and max(cams) <= 1e-3,
        "P5 visual result and safety": bool(pix) and pix["D_in_mask"] >= max(20, 3 * pix["noise_in_mask"])
            and all("M23 haptics policy=suppressed physical_pad_drivers=none" in x["log"] and not any(x["judges"].values())
                    and x["row"].get("runner_exit") == 0 and not x["row"].get("process_left") and not x["other"]
                    and len(FAULT.findall(x["log"])) <= len(FAULT.findall(blog)) for x in out.values()),
    }
    result = {"invalid": invalid, "checks": checks, "pass": not invalid and all(checks.values()),
              "p2": {c: out[c]["p2"] for c in out}, "p3_element14": p3, "element0": e0, "camera_max_diff": cams,
              "pixels": pix, "ref": rs, "vis": vs, "frames": {c: [f[0] for f in out[c]["frames"]] for c in out},
              "guest_base": {c: out[c]["row"].get("guest_base") for c in out}, "judges": {c: out[c]["judges"] for c in out}}
    (ROOT / "private" / "work" / P15 / tag / "judge.json").write_text(json.dumps(result, indent=1, default=str) + "\n")
    print(json.dumps({k: result[k] for k in ("invalid", "checks", "pass", "p2", "p3_element14", "element0",
                                              "camera_max_diff", "pixels")}, indent=1, default=str))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("check", "run", "judge", "check13b", "run13b", "judge13b", "replay-p2",
                                    "check15", "run15", "judge15"))
    ap.add_argument("tag", nargs="?")
    ap.add_argument("--cases", default=",".join(CASES))
    a = ap.parse_args()
    if a.cmd == "check":
        sys.exit(check())
    if a.cmd == "check13b":
        sys.exit(check13b())
    if a.cmd == "check15":
        sys.exit(check15())
    if a.cmd in ("run15", "judge15"):
        if not a.tag or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", a.tag):
            ap.error("bad tag")
        if a.cmd == "run15":
            for r in run15(a.tag):
                print(json.dumps(r), flush=True)
        sys.exit(judge15(a.tag))
    if a.cmd == "replay-p2":
        print(json.dumps(replay_p2(), indent=1))
        sys.exit(0)
    if a.cmd in ("run13b", "judge13b"):
        if not a.tag or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", a.tag):
            ap.error("bad tag")
        if a.cmd == "run13b":
            print(json.dumps(run13b(a.tag)), flush=True)
        sys.exit(judge13b(a.tag))
    if not a.tag or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", a.tag):
        ap.error("bad tag")
    if a.cmd == "judge":
        sys.exit(judge(a.tag))
    for case in a.cases.split(","):
        print(json.dumps(run_case(a.tag, case)), flush=True)
    sys.exit(judge(a.tag) if a.cases == ",".join(CASES) else 0)
