#!/usr/bin/env python3
"""G6-P37: the textured static scene of a level, read from the person's own Xbox 360 HD files (stdlib only).

    python tools/r3hd_level_scene.py summary LEVEL [--game DIR] [--json FILE]
    python tools/r3hd_level_scene.py check LEVEL [--game DIR]        # T1 / T2 / T4 cross-checks, numbers only
    python tools/r3hd_level_scene.py selftest                        # synthetic fixtures, no game data

Read-only. Walks the title's own data with layouts already VERIFIED in RE_NOTES:
  IPO SuperObject (type 0x20 / 0x40) +4 -> data +0 -> PhysicalObject +0 -> visual set {+4 u16 LOD count, +6 u16 type,
  +0xC -> LOD object array} -> visual geometric object {+0 vertices (f32 x, y, z), +8 colours, +0x10 element types,
  +0x14 elements, +0x24 / +0x26 vertex / element counts}; triangle element (type 1) {+0 material, +4 u16 triangles,
  +6 u16 UVs, +0xC vertex triples, +0x10 UV triples, +0x18 UVs} (E-501 / D-268); visual material +0x68 -> layer 0
  texture record, name inline at +0x4A (M25); bundle `<level>_2.bhf` / `fix.bhf` entries and the linear DXT layout of
  `r3hd_mods.py` (M26 / M33); world matrix = SuperObject +0x20 matrix times every parent's (+0x1C), RE_NOTES "M7", the
  same walk the editor's collision backdrop uses. A link that does not decode is skipped, never guessed.

Everything returned is game-derived: it lives in memory (or under private/) and is never written to the repository.
"""
import argparse
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_mods as rm  # noqa: E402

IPO_TYPES = (0x20, 0x40)
VM_LAYER0 = 0x68
MAX_ELEMENTS = 512
BLEND_MODES = {0x02: "opaque", 0x08: "test", 0x01: "add", 0x03: "blend"}   # layer byte -> draw mode (E-527)
TRACED_MODES = {"opaque", "test", "add"}                                    # "blend" (0x03) is an approximation
ALPHA_REF = 0.7529                                                          # traced RB_ALPHA_REF, GEQUAL
MAX_UV = 1.0e4     # intro_10 has one element (0x46E90) with 36 of 710 UVs near 1e10: shown untextured, not guessed
# fix.lvl / fix.ptr of the pinned title (the shared bundle the level's materials may point into)
FIX_SHA256 = None   # filled from the person's files and reported; the level pins below are the gate


class SceneError(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class _File:
    """One relocated level file: bytes plus {pointer field offset (raw file offset) -> target file id}."""

    def __init__(self, lvl: bytes, ptr: bytes, file_id: int):
        self.b, self.id = lvl, file_id
        n, = struct.unpack_from(">I", ptr, 0)
        self.slots = {}
        for i in range(n):
            fid, where = struct.unpack_from(">iI", ptr, 4 + 8 * i)
            self.slots[where + 4] = fid

    def u16(self, o): return struct.unpack_from(">H", self.b, o)[0]
    def u32(self, o): return struct.unpack_from(">I", self.b, o)[0]

    def link(self, o):
        """(target file id, raw target offset) of the pointer field at raw offset o, or None."""
        fid = self.slots.get(o)
        if fid is None or o + 4 > len(self.b):
            return None
        return fid, struct.unpack_from(">I", self.b, o)[0] + 4

    def ptr(self, o):
        """Raw target offset when the field at o is a pointer into this same file."""
        t = self.link(o)
        if t is None or t[0] != self.id or t[1] >= len(self.b):
            return None
        return t[1]


def _identity():
    return [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]


def world_matrix(f: _File, so):
    """SuperObject world matrix (row-major 4x4): own matrix times every parent's, as the collision backdrop."""
    w, depth = _identity(), 0
    while so is not None and depth < 32:
        mp = f.ptr(so + 0x20)
        if mp is not None and mp + 0x44 <= len(f.b):
            v = struct.unpack_from(">16f", f.b, mp + 4)
            m = [[v[4 * c + r] for c in range(4)] for r in range(4)]
            w = [[sum(m[r][k] * w[k][c] for k in range(4)) for c in range(4)] for r in range(4)]
        so, depth = f.ptr(so + 0x1C), depth + 1
    return w


def transform(w, v):
    return tuple(w[r][0] * v[0] + w[r][1] * v[1] + w[r][2] * v[2] + w[r][3] for r in range(3))


class Scene:
    """Static visual geometry of one level: objects (world-space vertices) with textured triangle elements."""

    def __init__(self, game_dir, level):
        self.game, self.level = Path(game_dir), level
        lvl_p, ptr_p, fid = rm.script_level_files(self.game, level)
        fix_l, fix_p, _ = rm.script_level_files(self.game, "fix")
        try:
            raw = {"lvl": lvl_p.read_bytes(), "ptr": ptr_p.read_bytes(),
                   "fix_lvl": fix_l.read_bytes(), "fix_ptr": fix_p.read_bytes()}
        except OSError as x:
            raise SceneError("TARGET_MISSING", f"{level} / fix files not found under {self.game} ({x})")
        # transit.lvl / .ptr (pointer file id 2; memory areas 2 / 3 are transit, RE_NOTES "level memory") carries
        # materials and textures the level shares with its neighbours; its bundle is transit_<n>.bhf
        tr_l, tr_p = lvl_p.with_name("transit.lvl"), lvl_p.with_name("transit.ptr")
        if tr_l.is_file() and tr_p.is_file():
            raw["transit_lvl"], raw["transit_ptr"] = tr_l.read_bytes(), tr_p.read_bytes()
        self.hashes = {k: rm.sha256_bytes(b) for k, b in raw.items()}
        try:
            self.lvl = _File(raw["lvl"], raw["ptr"], fid)
            self.fix = _File(raw["fix_lvl"], raw["fix_ptr"], 0)
            self.files = {fid: self.lvl, 0: self.fix}
            self.bundles = {fid: lvl_p.with_name(f"{level}_2.bhf"), 0: fix_l.with_name("fix.bhf")}
            if "transit_lvl" in raw:
                self.files[2] = _File(raw["transit_lvl"], raw["transit_ptr"], 2)
                self.bundles[2] = next(iter(sorted(lvl_p.parent.glob("transit_*.bhf"))), None)
            self.objects, self.textures, self.skipped = [], {}, {}
            self._walk()
        except (struct.error, IndexError, KeyError, ValueError, TypeError, OverflowError, RecursionError) as x:
            # G6-P39: damaged or foreign level files are refused, never a crash of the editor's event handler
            raise SceneError("TARGET_UNREADABLE", f"{level}: the level files could not be read ({type(x).__name__})")

    def _skip(self, why):
        self.skipped[why] = self.skipped.get(why, 0) + 1

    def _texture(self, mat_link):
        """Texture key (file id, record offset) of a material's layer 0, registered with its name; or None."""
        if mat_link is None:
            self._skip("element without material")
            return None
        mf = self.files.get(mat_link[0])
        if mf is None:
            self._skip("material in an unknown file")
            return None
        t = mf.link(mat_link[1] + VM_LAYER0)
        if t is None or t[0] not in self.files:
            self._skip("material without a layer-0 texture")
            return None
        tf = self.files[t[0]]
        name = tf.b[t[1] + 0x4A:t[1] + 0x4A + 0x80].split(b"\0")[0].decode("latin1")
        if not name.lower().endswith(".tga"):
            self._skip("texture record without a name")
            return None
        key = (t[0], t[1])
        if key not in self.textures:
            h, w = struct.unpack_from(">HH", tf.b, t[1] + 0x1C)
            flags = tf.u32(t[1] + 0x14)
            self.textures[key] = {"name": name, "file": t[0], "record": t[1], "width": w, "height": h,
                                  "flags": flags, "format": "DXT5" if flags & 0x8 else "DXT1"}
        return key

    def _blend(self, mat_link):
        """Draw mode of a material from its layer-0 byte at +0x6C (layer +4), G6-P38 / E-527, from 21 traced intro_15
        frames: 0x02 opaque (blend ONE/ZERO, depth write, no alpha test); 0x08 alpha-tested (alpha >= 0.7529, depth
        write); 0x01 additive (SRC_ALPHA, ONE; no depth write). 0x03 never appeared in a traced draw: drawn alpha-
        blended (SRC_ALPHA, 1-SRC_ALPHA, no depth write) as a labelled approximation. Anything else: opaque."""
        mf = self.files.get(mat_link[0]) if mat_link else None
        if mf is None or mat_link[1] + 0x6D > len(mf.b):
            return {"blend_byte": None, "mode": "opaque"}
        b = mf.b[mat_link[1] + 0x6C]
        return {"blend_byte": b, "mode": BLEND_MODES.get(b, "opaque")}

    def _walk(self):
        f = self.lvl
        seen = set()
        for field in sorted(f.slots):
            so = field - 4
            if field % 4 or so < 0 or so + 0x24 > len(f.b) or f.u32(so) not in IPO_TYPES:
                continue
            data = f.ptr(so + 4)
            po = f.ptr(data) if data is not None else None
            vs = f.ptr(po) if po is not None else None
            if vs is None:
                self._skip("IPO without a visual set")
                continue
            if f.u16(vs + 6) != 0 or f.u16(vs + 4) < 1:
                self._skip("visual set of another type")
                continue
            arr = f.ptr(vs + 0xC)
            go = f.ptr(arr) if arr is not None else None                # LOD 0, the most detailed
            if go is None or (go, so) in seen:
                continue
            seen.add((go, so))
            obj = self._object(so, go, po)
            if obj:
                anc, p = [], f.ptr(so + 0x1C)
                while p is not None and len(anc) < 32:
                    anc.append(p)
                    p = f.ptr(p + 0x1C)
                obj["ancestors"], obj["role"] = anc, "scene"
                self.objects.append(obj)

    # ---------------------------------------------------------------------------------------------------- roles
    def classify(self, playable_points):
        """G6-P38 (D-294) scene roles, a labelled editor approximation:
        - "backdrop": an untransformed object whose box extends more than 25 % of the playable box's extent beyond it on
          at least two axes (the sky domes: intro_15 stars / clouds / animated stars, intro_10 stars). The title draws
          such domes with the frame's own view-projection (E-526), so they are world-static; they only look wrong from
          outside, so the view draws them first, without depth writes, and only while the camera is inside them.
        - "runtime_placed": a transformed object hanging under a backdrop; the title re-places it per frame (E-526: the
          intro_15 star sprite's constants differ in rotation from the view-projection). Hidden, never guessed.
        playable_points: static collision vertices and actor positions of the level (the space a player can reach)."""
        pts = list(playable_points)
        if not pts:
            return
        lo = [min(p[k] for p in pts) for k in range(3)]
        hi = [max(p[k] for p in pts) for k in range(3)]
        self.playable = (lo, hi)
        backdrop = set()
        for o in self.objects:
            olo = [min(v[k] for v in o["vertices"]) for k in range(3)]
            ohi = [max(v[k] for v in o["vertices"]) for k in range(3)]
            o["box"] = (olo, ohi)
            out = sum(1 for k in range(3) if olo[k] < lo[k] - 0.25 * (hi[k] - lo[k])
                      or ohi[k] > hi[k] + 0.25 * (hi[k] - lo[k]))
            if o["identity"] and out >= 2:
                o["role"] = "backdrop"
                backdrop.add(o["superobject"])
        for o in self.objects:
            if not o["identity"] and backdrop.intersection(o["ancestors"]):
                o["role"] = "runtime_placed"

    def view_bounds(self):
        """Bounds for fitting the camera: the playable box when classified (static collision + actors), else the ordinary
        scene without backdrops and runtime-placed objects."""
        if getattr(self, "playable", None):
            return self.playable
        pts =[v for o in self.objects if o["role"] == "scene" for v in o["vertices"]]
        if not pts:
            return self.bounds()
        return [min(p[k] for p in pts) for k in range(3)], [max(p[k] for p in pts) for k in range(3)]

    def _object(self, so, go, po):
        f = self.lvl
        nv, ne = f.u16(go + 0x24), f.u16(go + 0x26)
        vo, co, to, eo = f.ptr(go), f.ptr(go + 8), f.ptr(go + 0x10), f.ptr(go + 0x14)
        if not nv or not ne or ne > MAX_ELEMENTS or None in (vo, to, eo) or vo + 12 * nv > len(f.b):
            self._skip("geometric object that does not decode")
            return None
        local = [struct.unpack_from(">3f", f.b, vo + 12 * i) for i in range(nv)]
        if not all(math.isfinite(c) for v in local for c in v):
            self._skip("non-finite vertices")
            return None
        w = world_matrix(f, so)
        colours = None
        if co is not None and co + 4 * nv <= len(f.b):
            colours = [f.b[co + 4 * i:co + 4 * i + 4] for i in range(nv)]
        elements = []
        for i, kind in enumerate(struct.unpack_from(f">{ne}h", f.b, to)):
            if kind != 1:
                self._skip(f"element type {kind}")
                continue
            el = f.ptr(eo + 4 * i)
            if el is None:
                continue
            nt, nuv = f.u16(el + 4), f.u16(el + 6)
            p_tri, p_map, p_uv = f.ptr(el + 0xC), f.ptr(el + 0x10), f.ptr(el + 0x18)
            if not nt or p_tri is None or p_tri + 6 * nt > len(f.b):
                self._skip("element without vertex triples")
                continue
            tri = struct.unpack_from(f">{3 * nt}H", f.b, p_tri)
            if max(tri) >= nv:
                self._skip("element with vertex index out of range")
                continue
            uv, uvt, why = None, None, "element without UV triples"
            if p_map is not None and p_uv is not None and nuv and p_uv + 8 * nuv <= len(f.b):
                m = struct.unpack_from(f">{3 * nt}H", f.b, p_map)
                if max(m) < nuv:
                    vals = struct.unpack_from(f">{2 * nuv}f", f.b, p_uv)
                    if all(math.isfinite(c) and abs(c) <= MAX_UV for c in vals):
                        uv, uvt = vals, m
                    else:
                        why = "element with UVs outside a plausible range (shown untextured)"
            if uvt is None:
                self._skip(why)
            mat = f.link(el)
            elements.append({"element": el, "triangles": nt, "tri": tri, "uv": uv, "uvt": uvt, "material": mat,
                             "texture": self._texture(mat) if uvt else None, **self._blend(mat)})
        if not elements:
            return None
        return {"superobject": so, "geometric_object": go, "physical_object": po, "matrix": w,
                "identity": w == _identity(), "local": local, "vertices": [transform(w, v) for v in local],
                "colours": colours, "elements": elements}

    # ---------------------------------------------------------------------------------------------------- textures
    def texture_entry(self, key):
        """(bhf path, entry tuple) of a texture key in its file's bundle, sizes checked against the record."""
        t = self.textures[key]
        bhf = self.bundles.get(t["file"])
        if bhf is None or not bhf.is_file():
            raise SceneError("TEXTURE_MISSING", f"{t['name']}: no bundle for file id {t['file']}")
        want = t["name"].lower()[:-4] + ".dds"
        for e in rm.bhf_entries(bhf):
            if e[0].lower() == want:
                base, mips, _ = rm.layout(t["width"], t["height"], t["format"])
                if (base, mips) != (e[1], e[3]):
                    raise SceneError("LAYOUT", f"{t['name']}: stored sizes {e[1]} / {e[3]} differ from {base} / {mips}")
                return bhf, e
        raise SceneError("TEXTURE_MISSING", f"{t['name']} is not in {bhf.name}")

    def decode_texture(self, key, max_side=256):
        """(width, height, RGBA bytes in storage row order) of the smallest stored mip level whose larger side is at
        least min(max_side, base side). Storage order = row 0 is the bundle's first block row, the row the title
        samples at v = 0 (pages are stored bottom row first, RE_NOTES "M26"), so v maps to rows directly."""
        t = self.textures[key]
        bhf, e = self.texture_entry(key)
        w, h, fmt = t["width"], t["height"], t["format"]
        base_size, _, levels = rm.layout(w, h, fmt)
        bpb = 16 if fmt == "DXT5" else 8
        pick = 0
        for i, lv in enumerate(levels):
            if max(lv[5], lv[6]) >= min(max_side, max(w, h)) and lv[3] == 0 and lv[4] == 0 and min(lv[5], lv[6]) >= 4:
                pick = i                                              # skip packed-tail levels (x / y offsets)
        blob, area, pitch, bx0, by0, lw, lh = levels[pick]
        start, size = (e[2], e[1]) if blob == 0 else (e[4], e[3])
        with open(bhf.with_suffix(".btf"), "rb") as fh:
            fh.seek(start)
            raw = rm.swap16(fh.read(size))
        rows = [raw[area + j * pitch:area + j * pitch + ((lw + 3) // 4) * bpb] for j in range((lh + 3) // 4)]
        upright = rm.decode_level(lw, lh, rows, fmt)
        stride = lw * 4
        stored = b"".join(upright[(lh - 1 - y) * stride:(lh - y) * stride] for y in range(lh))
        return lw, lh, stored

    # ---------------------------------------------------------------------------------------------------- summaries
    def triangle_count(self):
        return sum(e["triangles"] for o in self.objects for e in o["elements"])

    def bounds(self):
        pts = [v for o in self.objects for v in o["vertices"]]
        return [min(p[k] for p in pts) for k in range(3)], [max(p[k] for p in pts) for k in range(3)]

    def summary(self):
        lo, hi = self.bounds()
        tex_tris = {}
        for o in self.objects:
            for e in o["elements"]:
                if e["texture"] is not None:
                    tex_tris[e["texture"]] = tex_tris.get(e["texture"], 0) + e["triangles"]
        return {"level": self.level, "hashes": self.hashes, "objects": len(self.objects),
                "objects_non_identity": sum(1 for o in self.objects if not o["identity"]),
                "elements": sum(len(o["elements"]) for o in self.objects),
                "triangles": self.triangle_count(),
                "textured_triangles": sum(tex_tris.values()),
                "textures": sorted(({"name": self.textures[k]["name"], "file": "fix" if k[0] == 0 else "level",
                                     "size": f"{self.textures[k]['width']}x{self.textures[k]['height']}",
                                     "format": self.textures[k]["format"], "triangles": n}
                                    for k, n in tex_tris.items()), key=lambda r: -r["triangles"]),
                "bounds": [[round(x, 3) for x in lo], [round(x, 3) for x in hi]], "skipped": self.skipped,
                "modes": {m: sum(e["triangles"] for o in self.objects for e in o["elements"] if e["mode"] == m)
                          for m in sorted({e["mode"] for o in self.objects for e in o["elements"]})},
                "roles": {r: sum(1 for o in self.objects if o.get("role") == r)
                          for r in sorted({o.get("role", "scene") for o in self.objects})},
                "note": "game-derived statistics; keep any geometry or pixels under private/"}


# ---------------------------------------------------------------------------------------------------------- checks
def collision_agreement(scene: Scene):
    """T4 cross-check. The collision copy of the same PhysicalObject (+4 collide set +0xC zdr, file-backed and VERIFIED
    against guest memory, E-498) is transformed by the same world matrix; every visual vertex should have a collision
    vertex within about 3e-4 (E-501) when the two copies share it. Reports per object the share of visual vertices
    within 0.001 of a collision vertex, in object space and in world space."""
    f = scene.lvl
    rows = []
    for o in scene.objects:
        cs = f.ptr(o["physical_object"] + 4)
        zdr = f.ptr(cs + 0xC) if cs is not None else None
        if zdr is None:
            continue
        nv = f.u16(zdr)
        vo = f.ptr(zdr + 8)
        if not nv or vo is None:
            continue
        col = [struct.unpack_from(">3f", f.b, vo + 12 * i) for i in range(nv)]
        cw = [transform(o["matrix"], v) for v in col]
        grid = {}
        for p in cw:
            grid.setdefault(tuple(int(math.floor(c / 0.5)) for c in p), []).append(p)

        def near(p):
            k = tuple(int(math.floor(c / 0.5)) for c in p)
            best = 1e9
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for q in grid.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                            best = min(best, max(abs(p[i] - q[i]) for i in range(3)))
            return best

        d = [near(p) for p in o["vertices"]]
        rows.append({"superobject": o["superobject"], "identity": o["identity"], "visual": len(d),
                     "collision": nv, "within_0.001": sum(1 for x in d if x <= 1e-3),
                     "max_shared": max((x for x in d if x <= 1e-3), default=None)})
    return rows


def uv_sanity(scene: Scene):
    """T3 support: UV triples index in range (enforced while reading), UV bounding boxes, textured share."""
    out = {"elements_textured": 0, "elements_untextured": 0, "uv_min": [1e9, 1e9], "uv_max": [-1e9, -1e9]}
    for o in scene.objects:
        for e in o["elements"]:
            if e["texture"] is None:
                out["elements_untextured"] += 1
                continue
            out["elements_textured"] += 1
            us, vs = e["uv"][0::2], e["uv"][1::2]
            out["uv_min"] = [min(out["uv_min"][0], min(us)), min(out["uv_min"][1], min(vs))]
            out["uv_max"] = [max(out["uv_max"][0], max(us)), max(out["uv_max"][1], max(vs))]
    return out


# ---------------------------------------------------------------------------------------------------------- selftest
def _synthetic_files():
    """A minimal relocated level: one IPO -> PhysicalObject -> visual set -> one 4-vertex object, two triangles."""
    b = bytearray(0x400)
    slots = []

    def put_ptr(at, target):                  # raw offsets; stored value = target - 4 (the .lvl 4-byte header)
        struct.pack_into(">I", b, at, target - 4)
        slots.append((1, at - 4))
    so, data, po, vs, arr, go, el, verts, types, elems, tri, uvt, uv, mat = (
        0x10, 0x60, 0x70, 0x80, 0xA0, 0xB0, 0x120, 0x180, 0x1C0, 0x1C8, 0x1D0, 0x1E0, 0x1F0, 0x240)
    struct.pack_into(">I", b, so, 0x20)
    put_ptr(so + 4, data)
    put_ptr(data, po)
    put_ptr(po, vs)
    struct.pack_into(">HH", b, vs + 4, 1, 0)
    put_ptr(vs + 0xC, arr)
    put_ptr(arr, go)
    put_ptr(go, verts)
    put_ptr(go + 0x10, types)
    put_ptr(go + 0x14, elems)
    struct.pack_into(">HH", b, go + 0x24, 4, 1)
    struct.pack_into(">12f", b, verts, 0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0)
    struct.pack_into(">h", b, types, 1)
    put_ptr(elems, el)
    struct.pack_into(">HH", b, el + 4, 2, 4)
    put_ptr(el, mat)
    put_ptr(el + 0xC, tri)
    put_ptr(el + 0x10, uvt)
    put_ptr(el + 0x18, uv)
    struct.pack_into(">6H", b, tri, 0, 1, 2, 0, 2, 3)
    struct.pack_into(">6H", b, uvt, 0, 1, 2, 0, 2, 3)
    struct.pack_into(">8f", b, uv, 0, 0, 1, 0, 1, 1, 0, 1)
    ptr = struct.pack(">I", len(slots)) + b"".join(struct.pack(">iI", fid, at) for fid, at in slots)
    return bytes(b), ptr


def selftest() -> int:
    import tempfile
    ok = []

    def check(name, cond):
        ok.append(bool(cond))
        print(f"{'PASS' if cond else 'FAIL'} {name}")
    lvl, ptr = _synthetic_files()
    with tempfile.TemporaryDirectory() as d:
        g = Path(d) / "GAMEDATAbin"
        (g / "synth").mkdir(parents=True)
        (g / "synth" / "synth.lvl").write_bytes(lvl)
        (g / "synth" / "synth.ptr").write_bytes(ptr)
        (g / "fix.lvl").write_bytes(b"\0" * 8)
        (g / "fix.ptr").write_bytes(struct.pack(">I", 0))
        s = Scene(Path(d), "synth")
        check("one object decoded", len(s.objects) == 1)
        o = s.objects[0]
        check("identity world matrix without a matrix pointer", o["identity"])
        check("two triangles, UV triples in range", o["elements"][0]["triangles"] == 2 and o["elements"][0]["uvt"])
        check("material without layer-0 texture is untextured, not guessed", o["elements"][0]["texture"] is None
              and s.skipped.get("material without a layer-0 texture") == 1)
        check("bounds", s.bounds() == ([0.0, 0.0, 0.0], [1.0, 1.0, 0.0]))
    w = [[0, -1, 0, 5], [1, 0, 0, 0], [0, 0, 1, 2], [0, 0, 0, 1]]
    check("transform rotates then translates", transform(w, (1, 0, 0)) == (5, 1, 2))
    # storage-order texture rows: a 4x8 DXT1 page whose two block rows are distinct colours
    red = struct.pack("<HHI", 0xF800, 0xF800, 0)
    blue = struct.pack("<HHI", 0x001F, 0x001F, 0)
    up = rm.decode_level(4, 8, [red, blue], "DXT1")
    check("decode_level is upright (stored first row at the bottom)", up[0:4] == bytes((0, 0, 255, 255)))
    print(f"r3hd_level_scene selftest {sum(ok)}/{len(ok)}")
    return 0 if all(ok) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("summary", "check", "selftest"))
    ap.add_argument("level", nargs="?", default="intro_20")
    ap.add_argument("--game", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    game = a.game
    if game is None:
        import r3hd_level_editor_core as core
        game = core.default_game_dir()
    s = Scene(game, a.level)
    out = s.summary()
    if a.cmd == "check":
        rows = collision_agreement(s)
        out = {"level": a.level, "hashes": s.hashes, "uv": uv_sanity(s), "collision_agreement": {
            "objects_with_collision": len(rows),
            "objects_all_shared_within_0.001": sum(1 for r in rows if r["within_0.001"] == r["visual"]),
            "objects_none_within_0.001": sum(1 for r in rows if r["within_0.001"] == 0),
            "non_identity_objects": sum(1 for r in rows if not r["identity"]),
            "non_identity_majority_shared": sum(1 for r in rows if not r["identity"]
                                                and r["within_0.001"] * 2 >= r["visual"]),
            "visual_vertices": sum(r["visual"] for r in rows),
            "visual_vertices_within_0.001": sum(r["within_0.001"] for r in rows),
            "max_shared_distance": max((r["max_shared"] for r in rows if r["max_shared"] is not None), default=None)}}
        for key in s.textures:
            try:
                s.texture_entry(key)
            except SceneError as x:
                out.setdefault("texture_errors", []).append(x.code + " " + x.detail)
    text = json.dumps(out, indent=1, default=str)
    if a.json:
        a.json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
