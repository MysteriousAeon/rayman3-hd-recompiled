#!/usr/bin/env python3
"""M25: static audit of the meshes that use a named texture, straight from a level's .lvl / .ptr files.

    python tools/m25_mesh_audit.py LEVEL TEXTURE_SUBSTRING [--elements] [--out DIR] [--json FILE]

Follows the title's own data: texture record (name inline) <- visual material layer <- triangle element <-
geometric object, with the struct layouts Raymap documents for Rayman 3 (RESEARCH "M25"; every link is checked
against the level's relocation table, so a wrong layout fails instead of producing numbers). Prints, per element:
object and element names, the texture layers of its material, triangle / coordinate counts, the coordinate
bounding box, and how the object's triangles and deformation (skinning) data are stored. With --out it also writes
one PNG per texture with the elements' coordinate triangles drawn over the decoded texture (game-derived: keep it
under private/). Read-only; no game process.
"""
import argparse
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "private" / "extracted" / "5841123F" / "GAMEDATAbin"
VM_TEXTURES, VM_LAYER, VM_LAYERS = 0x68, 0x48, 4


class Level:
    def __init__(self, name: str):
        self.name = name
        self.dir = DATA if name == "fix" else DATA / name      # "fix" = the bundle every level shares
        self.file_id = 0 if name == "fix" else 1
        self.b = (self.dir / f"{name}.lvl").read_bytes()
        p = (self.dir / f"{name}.ptr").read_bytes()
        n, = struct.unpack_from(">I", p, 0)
        self.slots = {}                                     # offset of a pointer field -> target file id
        for i in range(n):
            fid, where = struct.unpack_from(">iI", p, 4 + 8 * i)
            self.slots[where] = fid
        self.by_value = defaultdict(list)                   # target offset (same file) -> pointer fields
        for where, fid in self.slots.items():
            if fid == self.file_id and where + 8 <= len(self.b):
                self.by_value[self.u32(where)].append(where)

    def u32(self, off): return struct.unpack_from(">I", self.b, off + 4)[0]
    def u16(self, off): return struct.unpack_from(">H", self.b, off + 4)[0]
    def i16s(self, off, n): return struct.unpack_from(f">{n}h", self.b, off + 4)
    def f32s(self, off, n): return struct.unpack_from(f">{n}f", self.b, off + 4)
    def text(self, off, size): return self.b[off + 4:off + 4 + size].split(b"\0")[0].decode("latin1")

    def ptr(self, off):
        """Target offset of the pointer field at off, or None when the field is not a relocated pointer."""
        return self.u32(off) if self.slots.get(off) == self.file_id else None

    def textures(self, needle: str):
        """Texture records whose inline name contains needle: {record offset: name}."""
        out, at, key = {}, 0, needle.lower().encode()
        low = self.b.lower()
        while (at := low.find(key, at)) >= 0:
            start = at
            while self.b[start - 1] >= 0x20:
                start -= 1
            name = self.b[start:self.b.index(b"\0", start)].decode("latin1")
            if name.lower().endswith(".tga"):
                out[start - 4 - 0x4A] = name
            at += 1
        return out

    def material_layers(self, vm):
        names = []
        for k in range(VM_LAYERS):
            t = self.ptr(vm + VM_TEXTURES + k * VM_LAYER)
            if t is None:
                break
            names.append((t, self.text(t + 0x4A, 0x80)))
        return names


def audit(level: Level, needle: str):
    tex = level.textures(needle)
    rows = []
    for t_off, t_name in sorted(tex.items()):
        for slot in level.by_value.get(t_off, []):
            for k in range(VM_LAYERS):                       # which layer of which material is this field?
                vm = slot - VM_TEXTURES - k * VM_LAYER
                for el in level.by_value.get(vm, []):        # element: material pointer is its first field
                    ntri, nuv, nmaps = level.u16(el + 4), level.u16(el + 6), level.u16(el + 8)
                    p_tri, p_map, p_uv = level.ptr(el + 0x0C), level.ptr(el + 0x10), level.ptr(el + 0x18)
                    if p_uv is None or not 0 < nuv < 20000 or nmaps > 4:
                        continue
                    rows.append(dict(texture=t_name, texture_off=t_off, layer=k, material=vm, element=el,
                                     element_name=level.text(el + 0x48, 0x34), triangles=ntri, uvs=nuv, uv_maps=nmaps,
                                     p_tri=p_tri, p_map=p_map, p_uv=p_uv,
                                     opt_entries=level.u16(el + 0x32), opt_strip=level.u16(el + 0x3C),
                                     opt_tris=level.u16(el + 0x3E), p_opt_map_uv=level.ptr(el + 0x38),
                                     p_opt_tris=level.ptr(el + 0x44), p_opt_strip=level.ptr(el + 0x40),
                                     layers=[n for _, n in level.material_layers(vm)]))
    for r in rows:                                           # owner object: the element list that holds it
        r["object"] = None
        for slot in level.by_value.get(r["element"], []):
            for i in range(64):
                arr = slot - 4 * i
                for go_field in level.by_value.get(arr, []):
                    go = go_field - 0x14
                    nel = level.u16(go + 0x26)
                    if i < nel <= 64 and level.ptr(go + 0x10) is not None:
                        types = level.i16s(level.ptr(go + 0x10), nel)
                        r["object"] = dict(offset=go, name=level.text(go + 0x46, 0x32), vertices=level.u16(go + 0x24),
                                           elements=nel, element_types=list(types), index=i,
                                           p_vertices=level.ptr(go), p_weights=level.ptr(go + 8),
                                           p_elements=arr)
                if r["object"]:
                    break
            if r["object"]:
                break
        uv = level.f32s(r["p_uv"], 2 * r["uvs"])
        r["uv_list"] = [(uv[2 * i], uv[2 * i + 1]) for i in range(r["uvs"])]
        us, vs = uv[0::2], uv[1::2]
        r["uv_box"] = [round(min(us), 3), round(min(vs), 3), round(max(us), 3), round(max(vs), 3)]
        tris = []
        if r["p_map"] is not None and r["triangles"]:
            m = level.i16s(r["p_map"], 3 * r["triangles"])
            tris = [m[3 * i:3 * i + 3] for i in range(r["triangles"])]
        elif r["p_opt_map_uv"] is not None and r["opt_entries"]:
            e = level.i16s(r["p_opt_map_uv"], r["opt_entries"] * max(1, r["uv_maps"]))[::max(1, r["uv_maps"])]
            if r["p_opt_tris"] is not None and r["opt_tris"]:
                d = level.i16s(r["p_opt_tris"], 3 * r["opt_tris"])
                tris += [tuple(e[x] for x in d[3 * i:3 * i + 3]) for i in range(r["opt_tris"])]
            if r["p_opt_strip"] is not None and r["opt_strip"]:
                s = level.i16s(r["p_opt_strip"], r["opt_strip"])
                tris += [(e[s[i]], e[s[i + 1]], e[s[i + 2]]) for i in range(len(s) - 2)
                         if len({s[i], s[i + 1], s[i + 2]}) == 3]
        r["uv_tris"] = [t for t in tris if all(0 <= x < r["uvs"] for x in t)]
        r["uv_tris_bad"] = len(tris) - len(r["uv_tris"])
    return tex, rows


def deform(level: Level, obj: dict):
    """Deformation (skinning) elements of an object: bones, weighted vertices, largest bone index used."""
    out = []
    for i, kind in enumerate(obj["element_types"]):
        if kind not in (13, 15):
            continue
        d = level.ptr(obj["p_elements"] + 4 * i)
        p_w, p_b, nw, nb = level.ptr(d), level.ptr(d + 4), level.u16(d + 8), level.b[d + 4 + 10]
        top, per_vertex, bad_vertex = 0, defaultdict(int), 0
        for j in range(nw if p_w is not None else 0):
            p_list, vi, cnt = level.ptr(p_w + 8 * j), level.u16(p_w + 8 * j + 4), level.b[p_w + 8 * j + 4 + 6]
            per_vertex[cnt] += 1
            bad_vertex += vi >= obj["vertices"]
            for k in range(cnt if p_list is not None else 0):
                top = max(top, level.b[p_list + 4 * k + 4 + 2])
        out.append(dict(element_index=i, bones=nb, weighted_vertices=nw, max_bone_index=top,
                        influences=dict(per_vertex), vertex_index_out_of_range=bad_vertex))
    return out


IDENT = [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]
SO_TYPES = (2, 8, 0x20, 0x40)


def mat_mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def so_matrix(level: Level, so):
    """World matrix of a SuperObject: its own matrix times every parent's (layout: RE_NOTES "M7")."""
    w, depth, chain = IDENT, 0, []
    while so is not None and depth < 32:
        chain.append(so)
        mp = level.ptr(so + 0x20)
        if mp is not None:
            f = level.f32s(mp + 4, 16)
            w = mat_mul([[f[4 * c + r] for c in range(4)] for r in range(4)], w)
        so, depth = level.ptr(so + 0x1C), depth + 1
    return w, chain


def placements(level: Level, go, depth=6):
    """SuperObjects whose data reaches the object within depth pointer steps: [(super object, steps)]."""
    found, frontier, seen = [], {go}, {go}
    for step in range(depth):
        nxt = set()
        for target in frontier:
            for field in level.by_value.get(target, []):
                so = field - 4                                # a SuperObject points at its data from +4
                if level.u32(so) in SO_TYPES and level.ptr(so + 0x20) is not None and level.slots.get(so + 0x1C) == level.file_id:
                    found.append((so, step))
                for back in range(0, 0x60, 4):                # the field sits somewhere inside its owner
                    owner = field - back
                    if owner not in seen and (owner in level.by_value or back == 0):
                        seen.add(owner)
                        nxt.add(owner)
        frontier = nxt
        if found:
            break
    return found


def render(level: Level, rows, out: Path, size=1100, views="abcd", prefix="render"):
    """Software picture of the placed parts (z up, three horizontal view directions), alpha test at 128."""
    from PIL import Image
    pages = {}
    tris, unplaced = [], 0
    for r in rows:
        o = r["object"]
        if not o or o["p_vertices"] is None or r["p_tri"] is None:
            continue
        place = placements(level, o["offset"])
        if not place:
            unplaced += 1
            continue
        v = level.f32s(o["p_vertices"], 3 * o["vertices"])
        idx = level.i16s(r["p_tri"], 3 * r["triangles"])
        if r["texture"] not in pages:
            pages[r["texture"]] = Image.open(out / f"page_{r['texture'].split(chr(92))[-1].rsplit('.', 1)[0]}.png").convert("RGBA").load()
        for so, _ in place:
            w, _ = so_matrix(level, so)
            pts = [[w[k][0] * v[3 * i] + w[k][1] * v[3 * i + 1] + w[k][2] * v[3 * i + 2] + w[k][3] for k in range(3)]
                   for i in range(o["vertices"])]
            for t in range(r["triangles"]):
                a = idx[3 * t:3 * t + 3]
                if all(0 <= x < o["vertices"] for x in a) and t < len(r["uv_tris"]):
                    tris.append(([pts[x] for x in a], [r["uv_list"][x] for x in r["uv_tris"][t]], pages[r["texture"]]))
    if not tris:
        print(f"  render: nothing placed ({unplaced} elements without a SuperObject)")
        return
    allp = [p for t in tris for p in t[0]]
    lo = [min(p[k] for p in allp) for k in range(3)]
    hi = [max(p[k] for p in allp) for k in range(3)]
    print(f"  render: {len(tris)} triangles placed, {unplaced} elements unplaced, world box {[round(x, 1) for x in lo]} .. {[round(x, 1) for x in hi]}")
    import math
    centre = [(lo[k] + hi[k]) / 2 for k in range(3)]
    span = max(hi[k] - lo[k] for k in range(3)) * 0.6
    for view, ang in (("a", 0), ("b", 90), ("c", 180), ("d", 270)):
        if view not in views:
            continue
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        img = Image.new("RGB", (size, size), (40, 40, 60))
        px = img.load()
        zb = [[1e30] * size for _ in range(size)]
        for pts, uvs, tex in tris:
            sp = []
            for x, y, z in pts:
                dx, dy = x - centre[0], y - centre[1]
                sp.append(((dx * ca + dy * sa) / span * size / 2 + size / 2, size / 2 - (z - centre[2]) / span * size / 2,
                           -dx * sa + dy * ca))
            (x0, y0, d0), (x1, y1, d1), (x2, y2, d2) = sp
            area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(area) < 1e-6:
                continue
            for py in range(max(0, int(min(y0, y1, y2))), min(size - 1, int(max(y0, y1, y2)) + 1) + 1):
                for qx in range(max(0, int(min(x0, x1, x2))), min(size - 1, int(max(x0, x1, x2)) + 1) + 1):
                    fx, fy = qx + 0.5, py + 0.5
                    b0 = ((x1 - fx) * (y2 - fy) - (x2 - fx) * (y1 - fy)) / area
                    b1 = ((x2 - fx) * (y0 - fy) - (x0 - fx) * (y2 - fy)) / area
                    b2 = 1 - b0 - b1
                    if b0 < 0 or b1 < 0 or b2 < 0:
                        continue
                    d = b0 * d0 + b1 * d1 + b2 * d2
                    if d >= zb[py][qx]:
                        continue
                    u = b0 * uvs[0][0] + b1 * uvs[1][0] + b2 * uvs[2][0]
                    vv = b0 * uvs[0][1] + b1 * uvs[1][1] + b2 * uvs[2][1]
                    c = tex[int(u % 1.0 * 512) % 512, int(vv % 1.0 * 512) % 512]
                    if c[3] < 128:
                        continue
                    zb[py][qx] = d
                    px[qx, py] = c[:3]
        img.save(out / f"{prefix}_{view}.png")


def overlay(level: Level, rows, out: Path):
    from PIL import Image, ImageDraw
    sys.path.insert(0, str(Path(__file__).parent))
    import io
    out.mkdir(parents=True, exist_ok=True)
    bhf = level.dir / ("fix.bhf" if level.name == "fix" else f"{level.name}_2.bhf")
    head = bhf.read_bytes()
    count, = struct.unpack_from(">I", head, 0)
    table = {}
    for i in range(count):
        o = 4 + i * 0x114
        s1, o1 = struct.unpack_from(">2I", head, o)
        table[head[o + 16:o + 0x114].split(b"\0")[0].decode("latin1").lower()] = (s1, o1)
    btf = bhf.with_suffix(".btf").read_bytes()
    by_tex = defaultdict(list)
    for r in rows:
        by_tex[r["texture"]].append(r)
    for name, group in by_tex.items():
        key = next(k for k in table if k.rsplit(".", 1)[0].endswith(name.lower().rsplit(".", 1)[0].split("\\")[-1]))
        s1, o1 = table[key]
        raw = bytearray(btf[o1:o1 + s1])
        raw[0::2], raw[1::2] = raw[1::2], raw[0::2]
        side = int(s1 ** 0.5)
        fmt = "DXT5" if side * side == s1 and side & (side - 1) == 0 else "DXT1"
        side = side if fmt == "DXT5" else int((2 * s1) ** 0.5)
        dds = (b"DDS " + struct.pack("<7I44x", 124, 0x81007, side, side, len(raw), 0, 1)
               + struct.pack("<II4s20x", 32, 4, fmt.encode()) + struct.pack("<I16x", 0x1000))
        full = Image.open(io.BytesIO(dds + bytes(raw))).convert("RGBA").resize((512, 512))
        full.save(out / f"page_{name.split(chr(92))[-1].rsplit('.', 1)[0]}.png")
        im = full.convert("RGB").resize((1024, 1024))
        for flip in (False, True):
            page = im.copy()
            draw = ImageDraw.Draw(page)
            for r in group:
                for t in r["uv_tris"]:
                    pts = [((r["uv_list"][x][0] % 1.0) * 1024, ((1 - r["uv_list"][x][1] if flip else r["uv_list"][x][1]) % 1.0) * 1024)
                           for x in t]
                    draw.polygon(pts, outline=(255, 0, 255))
            page.save(out / f"{name.split(chr(92))[-1].rsplit('.', 1)[0]}_{'vflip' if flip else 'v'}.png")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("level")
    ap.add_argument("texture")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--render", action="store_true", help="with --out: software picture of the placed parts")
    ap.add_argument("--elements", action="store_true", help="one line per element")
    a = ap.parse_args()
    level = Level(a.level)
    tex, rows = audit(level, a.texture)
    print(f"{a.level}: {len(level.slots)} relocated pointers; {len(tex)} texture records matching '{a.texture}'")
    for off, name in sorted(tex.items()):
        w, h = level.u16(off + 0x1E), level.u16(off + 0x1C)
        print(f"  texture {name} record={off:#x} size={w}x{h} flags={level.u32(off + 0x14):#x} users={sum(1 for r in rows if r['texture_off'] == off)}")
    objects = {}
    for r in rows:
        o = r["object"]
        if o:
            objects[o["offset"]] = o
        if not a.elements:
            continue
        print(f"  element {r['element']:#x} '{r['element_name']}' object='{o['name'] if o else '?'}' layers={r['layers']} "
              f"tris={r['triangles']} uvs={r['uvs']} maps={r['uv_maps']} opt={r['opt_entries']}/{r['opt_strip']}/{r['opt_tris']} "
              f"uv_box={r['uv_box']} uv_tris={len(r['uv_tris'])} bad={r['uv_tris_bad']}")
    print(f"  elements={len(rows)} with_object={sum(1 for r in rows if r['object'])} triangles={sum(r['triangles'] for r in rows)} "
          f"coordinate_triangles_out_of_range={sum(r['uv_tris_bad'] for r in rows)} "
          f"multi_layer={sum(1 for r in rows if len(r['layers']) > 1)}")
    for off, o in sorted(objects.items()):
        o["deform"] = deform(level, o)
        print(f"  object {off:#x} '{o['name']}' vertices={o['vertices']} element_types={o['element_types']} "
              f"weights={'yes' if o['p_weights'] is not None else 'no'} deform={o['deform']}")
    if a.out:
        overlay(level, rows, a.out)
        if a.render:
            render(level, rows, a.out)
    if a.json:
        for r in rows:
            r.pop("uv_list"), r.pop("uv_tris")
        a.json.write_text(json.dumps(dict(level=a.level, textures=list(tex.values()), elements=rows), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
