#!/usr/bin/env python3
"""G6-P12: is a level's static collision file-backed, and what would a same-size collision edit touch?

    python -I tools/experiments/modding_feasibility/g6p12_collision_file_audit.py LEVEL [--snap DIR]
        [--probe X Y Z] [--json FILE]

Read-only, offline, counts only (no game process, no write to any game file). Starting from the level's own
relocation table (`m25_mesh_audit.Level`: every pointer is checked against the `.ptr` slots), it finds the
SuperObjects of type IPO (0x20) / IPO_2 (0x40) and follows IPO +0 PhysicalObject -> +4 collide set -> +0xC zdr
mesh (RE_NOTES "Static collision"), with the R3 mesh header as Raymap 2df1383 reads it (+0 u16 vertices,
+2 u16 elements, +8 vertices, +0xC element types, +0x10 elements, +0x18 parallel boxes, +0x1C sphere radius,
+0x20 sphere centre). It reports:

  * meshes / triangles reachable from the file, element types, parent sector of each IPO;
  * whether any vertex / index / normal word is relocated or pointed into from elsewhere (sharing);
  * how many fields reference each mesh, vertex array and collide set (sharing between IPOs);
  * whether every vertex lies inside the mesh's own bounding sphere (constraint for a vertex edit);
  * the triangle elements' parallel-box index values (a field Raymap does not decode);
  * with --snap: a retained read-only snapshot (E-50 format) of the same level is decoded with
    `m7_collision_map`, the level's load base is derived from the mesh addresses, and every non-pointer word of
    every mesh header, vertex array, index array and normal array is compared with the file;
  * with --probe: the meshes that have a triangle under (X, Y) within 2 units below / above Z.
Output is numbers only.
"""
import argparse
import json
import math
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))
import m25_mesh_audit as m25          # noqa: E402

IPO_TYPES = (0x20, 0x40)


def parse_mesh(L, zdr):
    """File-side zdr mesh: dict or None when any link fails the relocation check."""
    nv, ne = struct.unpack_from(">HH", L.b, zdr + 4)
    vo, to, eo = L.ptr(zdr + 8), L.ptr(zdr + 0xC), L.ptr(zdr + 0x10)
    if not nv or not ne or ne > 512 or vo is None or to is None or eo is None:
        return None
    verts = [L.f32s(vo + 12 * i, 3) for i in range(nv)]
    if not all(math.isfinite(c) for v in verts for c in v):
        return None
    types = struct.unpack_from(f">{ne}H", L.b, to + 4)
    elems = []
    for i, t in enumerate(types):
        blk = L.ptr(eo + 4 * i)
        if blk is None:
            return None
        if t != 1:
            elems.append({"type": t, "blk": blk})
            continue
        tri, nrm = L.ptr(blk + 4), L.ptr(blk + 8)
        nt, pbox = struct.unpack_from(">Hh", L.b, blk + 0xC + 4)
        if tri is None:
            return None
        idx = struct.unpack_from(f">{3 * nt}H", L.b, tri + 4) if nt else ()
        elems.append({"type": 1, "blk": blk, "mat": L.ptr(blk), "tri": tri, "nrm": nrm, "nt": nt, "pbox": pbox,
                      "idx": idx})
    radius = L.f32s(zdr + 0x1C, 1)[0]
    centre = L.f32s(zdr + 0x20, 3)
    return {"zdr": zdr, "nv": nv, "ne": ne, "vo": vo, "to": to, "eo": eo, "verts": verts, "elems": elems,
            "pboxes": L.ptr(zdr + 0x18), "pbox_raw": L.u32(zdr + 0x18), "radius": radius, "centre": centre,
            "w4": L.u32(zdr + 4), "w14": L.u32(zdr + 0x14)}


def in_range_slots(L, start, size):
    return sum(1 for a in range(start, start + size, 4) if a in L.slots)


def pointed_into(L, start, size):
    return sum(len(L.by_value.get(a, [])) for a in range(start + 4, start + size, 4))


def sector_of(L, so):
    seen = 0
    while so is not None and seen < 64:
        if L.u32(so) == 4:
            return so
        if L.slots.get(so + 0x1C) not in (None, L.file_id):
            return "other-file"
        so, seen = L.ptr(so + 0x1C), seen + 1
    return None


def audit(level, snap=None, probe=None):
    L = m25.Level(level)
    out = {"level": level, "file_bytes": len(L.b), "slots": len(L.slots)}
    ipos = []
    for where, fid in L.slots.items():
        so = where - 4
        if fid != L.file_id or so < 0 or so % 4 or L.u32(so) not in IPO_TYPES:
            continue
        data = L.ptr(so + 4)
        po = L.ptr(data) if data is not None else None
        cs = L.ptr(po + 4) if po is not None else None
        if cs is None:
            continue
        ipos.append((so, data, po, cs))
    meshes, cs_fields, tri_total, etypes, sectors = {}, Counter(), 0, Counter(), Counter()
    reloc_in_data = shared_into = outside_sphere = 0
    pbox_vals, mat_ids, ref_counts = Counter(), Counter(), Counter()
    owners = defaultdict(set)
    for so, data, po, cs in ipos:
        for k, name in enumerate(("zdm", "zdd", "zde", "zdr")):
            if L.ptr(cs + 4 * k) is not None:
                cs_fields[name] += 1
        zdr = L.ptr(cs + 0xC)
        if zdr is None:
            continue
        owners[zdr].add(so)
        sectors[str(sector_of(L, so) is not None)] += 1
        if zdr in meshes:
            continue
        m = parse_mesh(L, zdr)
        if m is None:
            continue
        m["so"] = so
        meshes[zdr] = m
        ref_counts[len(L.by_value.get(zdr, []))] += 1
        reloc_in_data += in_range_slots(L, m["vo"], 12 * m["nv"])
        shared_into += pointed_into(L, m["vo"], 12 * m["nv"])
        r = m["radius"]
        c = m["centre"]
        for v in m["verts"]:
            if math.dist(v, c) > r * 1.0001 + 1e-4:
                outside_sphere += 1
        for e in m["elems"]:
            etypes[e["type"]] += 1
            if e["type"] == 1:
                tri_total += e["nt"]
                pbox_vals["-1" if e["pbox"] < 0 else ">=0"] += 1
                reloc_in_data += in_range_slots(L, e["tri"], 6 * e["nt"])
                if e["nrm"] is not None:
                    reloc_in_data += in_range_slots(L, e["nrm"], 12 * e["nt"])
                cm = L.ptr(e["mat"] + 4) if e["mat"] is not None else None
                if cm is not None:
                    mat_ids[struct.unpack_from(">HH", L.b, cm + 4)] += 1
    out.update({
        "ipo_superobjects_with_collide_set": len(ipos),
        "collide_set_fields_nonnull": dict(cs_fields),
        "meshes": len(meshes), "triangles": tri_total, "element_types": dict(etypes),
        "ipos_under_a_sector_in_file": dict(sectors),
        "meshes_used_by_n_ipos": dict(Counter(len(owners[z]) for z in meshes)),
        "mesh_reference_fields_histogram": dict(ref_counts),
        "relocated_words_inside_vertex_index_normal_arrays": reloc_in_data,
        "pointers_into_vertex_arrays_after_start": shared_into,
        "vertices_outside_own_sphere": outside_sphere,
        "vertices_total": sum(m["nv"] for m in meshes.values()),
        "parallel_box_pointer_nonnull": sum(1 for m in meshes.values() if m["pboxes"] is not None),
        "parallel_box_raw_nonzero": sum(1 for m in meshes.values() if m["pbox_raw"]),
        "triangle_element_parallel_box_index": dict(pbox_vals),
        "collide_material_type_id_top": [[f"{t}/{i}", n] for (t, i), n in mat_ids.most_common(8)],
    })
    if probe:
        px, py, pz = probe
        hits = []
        for z, m in meshes.items():
            w, _ = m25.so_matrix(L, m["so"])
            vw = [[w[r][0] * v[0] + w[r][1] * v[1] + w[r][2] * v[2] + w[r][3] for r in range(3)] for v in m["verts"]]
            ident = all(abs(w[r][c] - (1.0 if r == c else 0.0)) < 1e-6 for r in range(4) for c in range(4))
            best = None
            for e in m["elems"]:
                if e["type"] != 1:
                    continue
                for j in range(e["nt"]):
                    a, b, c = (vw[k] for k in e["idx"][3 * j:3 * j + 3])
                    d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
                    if abs(d) < 1e-9:
                        continue
                    l1 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / d
                    l2 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / d
                    l3 = 1 - l1 - l2
                    if min(l1, l2, l3) < -1e-6:
                        continue
                    zz = l1 * a[2] + l2 * b[2] + l3 * c[2]
                    if abs(zz - pz) <= 2.0 and (best is None or abs(zz - pz) < abs(best - pz)):
                        best = zz
            if best is not None:
                xs, ys, zs = zip(*vw)
                hits.append({"zdr": hex(z), "surface_z": round(best, 3), "nv": m["nv"],
                             "tris": sum(e.get("nt", 0) for e in m["elems"]), "identity_world": ident,
                             "bbox": [round(min(xs), 1), round(max(xs), 1), round(min(ys), 1), round(max(ys), 1),
                                      round(min(zs), 2), round(max(zs), 2)],
                             "radius": round(m["radius"], 2), "ipo_users": len(owners[z]),
                             "ref_fields": len(L.by_value.get(z, [])),
                             "sector": sector_of(L, m["so"]) is not None})
        out["probe"] = {"point": probe, "meshes": hits}
    if snap:
        out["snapshot"] = compare_snapshot(L, meshes, snap)
    return out


def compare_snapshot(L, meshes, snap):
    import m7_collision_map as m7
    mem = m7.Mem(snap)
    info = json.load(open(Path(snap) / "collision.json"))
    nodes, _ = m7.walk(mem, int(info["root"], 16))
    zdrs = set()
    for so, _, _ in nodes:
        t = mem.u32(so)
        if t not in (0x20, 0x40, 8):
            continue
        data = mem.u32(so + 4)
        po = mem.u32(data) if t != 8 else data
        cs = mem.u32(po + 4) if po else None
        z = mem.u32(cs + 0xC) if cs else None
        if z:
            zdrs.add(z)
    # load base: the difference that maps the most snapshot meshes onto file meshes
    diffs = Counter(a - f for a in zdrs for f in meshes)
    base, votes = diffs.most_common(1)[0]
    res = {"snapshot_meshes": len(zdrs), "base": hex(base), "base_votes": votes,
           "snapshot_meshes_outside_this_file": sum(1 for a in zdrs if a - base not in meshes)}
    words = differ = ptr_ok = ptr_bad = 0
    for f, m in meshes.items():
        a = f + base
        if a not in zdrs:
            continue
        ranges = [(f, 0x2C, {f + 8, f + 0xC, f + 0x10, f + 0x14, f + 0x18})]
        ranges.append((m["vo"], 12 * m["nv"], set()))
        for e in m["elems"]:
            if e["type"] == 1:
                ranges.append((e["blk"], 0x10, {e["blk"], e["blk"] + 4, e["blk"] + 8}))
                ranges.append((e["tri"], (6 * e["nt"] + 3) & ~3, set()))
                if e["nrm"] is not None:
                    ranges.append((e["nrm"], 12 * e["nt"], set()))
        for start, size, ptrs in ranges:
            for off in range(start, start + size, 4):
                fw = L.u32(off)
                sw = mem.u32(off + base)
                if off in L.slots:
                    if L.slots[off] == L.file_id:
                        if sw == fw + base:
                            ptr_ok += 1
                        else:
                            ptr_bad += 1
                    continue
                words += 1
                if fw != sw:
                    differ += 1
    res.update({"compared_non_pointer_words": words, "differing_words": differ,
                "same_file_pointers_equal_base_plus_offset": ptr_ok, "pointers_differing": ptr_bad})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("level")
    ap.add_argument("--snap")
    ap.add_argument("--probe", nargs=3, type=float)
    ap.add_argument("--json")
    a = ap.parse_args()
    out = audit(a.level, a.snap, a.probe)
    text = json.dumps(out, indent=1)
    print(text)
    if a.json:
        Path(a.json).write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
