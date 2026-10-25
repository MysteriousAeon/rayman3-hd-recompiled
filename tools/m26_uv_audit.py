#!/usr/bin/env python3
"""M26: does a mesh's coordinate set fit the texture it is bound to, and under which orientation?

    python tools/m26_uv_audit.py LEVEL TEXTURE_SUBSTRING [--parts] [--controls] [--json FILE]
    python tools/m26_uv_audit.py selftest

Read-only, no game process. For every triangle element that uses a matching texture (found as
`m25_mesh_audit.py` finds them) the coordinate triangles are laid over the decoded texture four times: as
stored, with v mirrored (v -> 1 - v), with u mirrored, with both. Two measures that use nothing but the
target's own files:

  seam    mean colour step, across the texture's own cell borders (lines at multiples of 1/16 of the page where
          the picture is discontinuous), of the texels that lie strictly inside a coordinate triangle. An atlas
          island that sits in its cell crosses no border; one that is laid over the wrong place does.
  cut     share of the triangles' area on texels with alpha below 128.

The orientation with the lowest seam value is reported per element and per texture, with the margin to the
stored orientation. --controls runs the same measure over every other texture of the level (the expected answer
there is "as stored"; elements whose coordinates leave the 0..1 square are tiled surfaces and are skipped
there). The measure says which orientation is consistent with the texture's layout; it does not
say what the authors intended (RE_NOTES "M26"). Output is numbers only; decoded textures stay in memory.
"""
import argparse
import io
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import m25_mesh_audit as mesh

ORIENT = ("stored", "vflip", "uflip", "both")
GRID = 16
MARGIN = 2.0          # texels a border texel must lie inside the triangle


def orient(uv, how):
    u, v = uv
    return (1 - u if how in ("uflip", "both") else u, 1 - v if how in ("vflip", "both") else v)


def decode(level: mesh.Level, name: str):
    """RGBA texels of a bundle texture as (side, rows of tuples), or None when it is not a plain DXT page."""
    from PIL import Image
    bhf = level.dir / ("fix.bhf" if level.name == "fix" else f"{level.name}_2.bhf")
    head = bhf.read_bytes()
    count, = struct.unpack_from(">I", head, 0)
    want = name.lower().rsplit(".", 1)[0]
    for i in range(count):
        o = 4 + i * 0x114
        s1, o1 = struct.unpack_from(">2I", head, o)
        if head[o + 16:o + 0x114].split(b"\0")[0].decode("latin1").lower().rsplit(".", 1)[0] != want:
            continue
        with open(bhf.with_suffix(".btf"), "rb") as f:
            f.seek(o1)
            raw = bytearray(f.read(s1))
        raw[0::2], raw[1::2] = raw[1::2], raw[0::2]
        side = int(s1 ** 0.5)
        fmt = "DXT5" if side * side == s1 and side & (side - 1) == 0 else "DXT1"
        side = side if fmt == "DXT5" else int((2 * s1) ** 0.5)
        if side < 16 or side & (side - 1) or len(raw) != (side * side if fmt == "DXT5" else side * side // 2):
            return None
        dds = (b"DDS " + struct.pack("<7I44x", 124, 0x81007, side, side, len(raw), 0, 1)
               + struct.pack("<II4s20x", 32, 4, fmt.encode()) + struct.pack("<I16x", 0x1000))
        try:
            im = Image.open(io.BytesIO(dds + bytes(raw))).convert("RGBA")
        except Exception:
            return None
        px = list(im.get_flattened_data()) if hasattr(im, 'get_flattened_data') else list(im.getdata())
        return side, [px[y * side:(y + 1) * side] for y in range(side)]
    return None


def borders(side, px, threshold=90):
    """{(x, y): step} for texels on a 1/16 grid line where the picture changes abruptly across the line."""
    step = side // GRID
    out = {}
    if step < 2:
        return out
    def d(a, b):
        return sum(abs(a[k] - b[k]) for k in range(4))
    for k in range(1, GRID):
        g = k * step
        for t in range(side):
            a = d(px[t][g - 1], px[t][g])                       # vertical line x = g
            inner = max(d(px[t][g - 2], px[t][g - 1]), d(px[t][g], px[t][g + 1]))
            if a > threshold and a > 2 * inner:
                out[(g, t)] = out.get((g, t), 0) + a
            a = d(px[g - 1][t], px[g][t])                       # horizontal line y = g
            inner = max(d(px[g - 2][t], px[g - 1][t]), d(px[g][t], px[g + 1][t]))
            if a > threshold and a > 2 * inner:
                out[(t, g)] = out.get((t, g), 0) + a
    return out


def measure(side, px, edge, tris):
    """(seam, cut, area in texels) of coordinate triangles [(p0, p1, p2)] over one texture."""
    area = cut = seam = 0.0
    for tri in tris:
        (x0, y0), (x1, y1), (x2, y2) = [(u * side, v * side) for u, v in tri]
        a2 = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(a2) < 1e-6:
            continue
        lens = [((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5, ((x0 - x2) ** 2 + (y0 - y2) ** 2) ** 0.5,
                ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5]
        height = [abs(a2) / max(l, 1e-9) for l in lens]         # distance of a corner from the opposite edge
        for py in range(int(min(y0, y1, y2)), int(max(y0, y1, y2)) + 1):
            for qx in range(int(min(x0, x1, x2)), int(max(x0, x1, x2)) + 1):
                fx, fy = qx + 0.5, py + 0.5
                b0 = ((x1 - fx) * (y2 - fy) - (x2 - fx) * (y1 - fy)) / a2
                b1 = ((x2 - fx) * (y0 - fy) - (x0 - fx) * (y2 - fy)) / a2
                b2 = 1 - b0 - b1
                if b0 < 0 or b1 < 0 or b2 < 0:
                    continue
                tx, ty = qx % side, py % side
                area += 1
                cut += px[ty][tx][3] < 128
                if min(b0 * height[0], b1 * height[1], b2 * height[2]) >= MARGIN:
                    seam += edge.get((tx, ty), 0)
    return (seam / area if area else 0.0, cut / area if area else 0.0, area)


def audit(level: mesh.Level, needle: str):
    tex, rows = mesh.audit(level, needle)
    pages, edges, out = {}, {}, []
    for r in rows:
        if len(r["layers"]) != 1 or not r["uv_tris"]:
            continue
        b = r["uv_box"]                                      # atlas use only: a tiled surface has no cell to sit in
        if b[0] < -0.06 or b[1] < -0.06 or b[2] > 1.06 or b[3] > 1.06:
            if needle == ".tga":
                continue
        name = r["texture"]
        if name not in pages:
            pages[name] = decode(level, name)
            edges[name] = borders(*pages[name]) if pages[name] else None
        if not pages[name]:
            continue
        side, px = pages[name]
        row = dict(texture=name, element=r["element"], object=r["object"]["offset"] if r["object"] else None,
                   vertices=r["object"]["vertices"] if r["object"] else 0, triangles=r["triangles"])
        for how in ORIENT:
            tris = [[orient(r["uv_list"][x], how) for x in t] for t in r["uv_tris"]]
            s, c, a = measure(side, px, edges[name], tris)
            row[how] = dict(seam=round(s, 3), cut=round(c, 3))
            row["area"] = round(a)
        out.append(row)
    return out


def summarize(rows):
    """Per texture: area-weighted seam / cut per orientation, and how many elements prefer each."""
    by = defaultdict(list)
    for r in rows:
        by[r["texture"]].append(r)
    res = {}
    for name, rs in sorted(by.items()):
        area = sum(r["area"] for r in rs) or 1
        tot = {h: dict(seam=round(sum(r[h]["seam"] * r["area"] for r in rs) / area, 3),
                       cut=round(sum(r[h]["cut"] * r["area"] for r in rs) / area, 3)) for h in ORIENT}
        votes = defaultdict(int)
        for r in rs:
            best = min(ORIENT, key=lambda h: (r[h]["seam"], ORIENT.index(h)))
            votes[best if r[best]["seam"] < r["stored"]["seam"] else "stored"] += 1
        best = min(ORIENT, key=lambda h: (tot[h]["seam"], ORIENT.index(h)))
        res[name] = dict(elements=len(rs), totals=tot, votes=dict(votes), best=best)
    return res


def selftest() -> int:
    side = 64
    px = [[(200, 0, 0, 255) if y < 32 else (0, 0, 200, 255) if y < 35 else (0, 0, 200, 0) for x in range(side)] for y in range(side)]
    edge = borders(side, px)
    ok = all((x, 32) in edge for x in range(4, 60)) and (20, 10) not in edge
    top = [[(0.05, 0.05), (0.95, 0.05), (0.5, 0.45)]]
    across = [[(0.05, 0.05), (0.95, 0.05), (0.5, 0.95)]]
    s0, c0, _ = measure(side, px, edge, top)
    s1, c1, _ = measure(side, px, edge, across)
    s2, c2, _ = measure(side, px, edge, [[orient(p, "vflip") for p in top[0]]])
    ok &= s0 == 0 and c0 == 0 and s1 > 0 and s2 == 0 and c2 > 0.9
    ok &= orient((0.25, 0.1), "both") == (0.75, 0.9) and orient((0.25, 0.1), "stored") == (0.25, 0.1)
    print("M26_UV_AUDIT_SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "selftest":
        return selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("level")
    ap.add_argument("texture")
    ap.add_argument("--parts", action="store_true", help="one line per element")
    ap.add_argument("--controls", action="store_true", help="also every other single-layer texture of the level")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    level = mesh.Level(a.level)
    rows = audit(level, ".tga" if a.controls else a.texture)
    res = summarize(rows)
    for name, s in res.items():
        mark = "*" if a.texture.lower() in name.lower() else " "
        t = s["totals"]
        print(f"{mark} {name:42s} elements={s['elements']:3d} best={s['best']:6s} "
              + " ".join(f"{h}={t[h]['seam']:.2f}/{t[h]['cut']:.2f}" for h in ORIENT) + f" votes={s['votes']}")
    if a.parts:
        for r in rows:
            if a.texture.lower() in r["texture"].lower():
                print(f"  {r['texture'][-12:]} element={r['element']:#x} v={r['vertices']} t={r['triangles']} area={r['area']} "
                      + " ".join(f"{h}={r[h]['seam']:.2f}/{r[h]['cut']:.2f}" for h in ORIENT))
    if a.controls:
        ctl = [s for n, s in res.items() if a.texture.lower() not in n.lower() and max(v["seam"] for v in s["totals"].values()) > 0]
        print(f"controls with any border crossing: {len(ctl)}; stored is best in {sum(1 for s in ctl if s['best'] == 'stored')}")
    if a.json:
        a.json.write_text(json.dumps(dict(level=a.level, summary=res, elements=rows), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
