#!/usr/bin/env python
"""Offline decoder for the static level collision geometry in a guest-memory snapshot.

Usage:
  python tools/m7_collision_map.py SNAPSHOT_DIR [--query X Y] [--rayman 0x40C52514] [--rebuild]
  python tools/m7_collision_map.py private/work/m7_snap --query 4.84 21.46

SNAPSHOT_DIR holds index.json plus <ADDRESS>.bin files (raw big-endian guest memory, file name =
guest start address). The hierarchy is found from Rayman's SuperObject by following parent links up
to the root, then walking the child lists (reciprocal sibling/parent links are checked). Every
IPO / PhysicalObject SuperObject contributes its collide mesh (zdr), transformed by the accumulated
SuperObject matrices into world space.

Layout (hypothesis from the pinned Raymap R3 readers, every offset validated against the snapshot):
  SuperObject +0 type, +4 data, +8 child head, +0xC tail, +0x10 count, +0x14 next, +0x18 prev,
              +0x1C parent, +0x20 matrix
  Matrix      +0 type, +4 4x4 floats stored column by column (translation = column 3 at +0x34)
  IPO         +0 PhysicalObject;  PhysicalObject +4 collide set;  collide set +0xC zdr mesh
  Mesh        +0 u16 vertices, u16 elements, +8 vertex floats (x,y,z), +0xC u16 element types,
              +0x10 element pointers
  Triangles   +0 material, +4 u16[3] indices, +8 float[3] normals, +0xC u16 count
  Material    +4 collide material {u16 type, u16 identifier}

Pure Python (no numpy/PIL). Outputs under SNAPSHOT_DIR: collision.tris (float32 x9 + u16 material
identifier + u16 material type per triangle), collision.json (summary), heightmap.png, levels.png.
"""
import argparse
import json
import math
import os
import struct
import sys
import zlib
from collections import Counter

SO_TYPES = {1: 'World', 2: 'Perso', 4: 'Sector', 8: 'PhysicalObject', 0x20: 'IPO', 0x40: 'IPO_2'}
X0, X1, Y0, Y1, CELL = -110.0, 420.0, -60.0, 140.0, 0.5
ACCEPT = [(-97.59, 75.09, -7.97), (-13.37, 20.29, -4.29), (-1.40, 19.50, -4.71), (4.84, 21.46, -1.50),
          (3.94, 10.34, 6.43), (41.30, 21.08, 2.57), (87.05, 63.07, -7.14), (-33.49, 22.76, -6.88)]
WALK_NZ = 0.5          # surfaces with world normal z above this count as walkable
STACK_GAP = 0.6        # surfaces closer than this (in z) in one cell count as one level


class Mem:
    def __init__(self, d):
        self.regions = []
        for r in json.load(open(os.path.join(d, 'index.json')))['regions']:
            data = open(os.path.join(d, '%08X.bin' % r['address']), 'rb').read()
            self.regions.append((r['address'], data))

    def rd(self, a, n):
        for b, d in self.regions:
            if b <= a and a + n <= b + len(d):
                return d[a - b:a - b + n]
        return None

    def u32(self, a):
        x = self.rd(a, 4)
        return struct.unpack('>I', x)[0] if x else None

    def u16s(self, a, n):
        x = self.rd(a, 2 * n)
        return struct.unpack('>%dH' % n, x) if x else None

    def f32s(self, a, n):
        x = self.rd(a, 4 * n)
        return struct.unpack('>%df' % n, x) if x else None


def mat_mul(a, b):  # 4x4 as rows[r][c]; returns a*b
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


IDENT = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]


def read_matrix(m, ptr):
    f = m.f32s(ptr + 4, 16) if ptr else None
    if not f or not all(math.isfinite(v) for v in f):
        return IDENT
    return [[f[4 * c + r] for c in range(4)] for r in range(4)]  # column c = floats 4c..4c+3


def walk(m, root):
    """Yield (so, parent, depth, world_matrix); validates sibling/parent reciprocity."""
    stats = {'bad_links': 0, 'count_mismatch': 0}
    out, seen = [], set()

    def rec(so, par, wm):
        if so in seen:
            stats['bad_links'] += 1
            return
        seen.add(so)
        local = read_matrix(m, m.u32(so + 0x20))
        w = mat_mul(wm, local)
        out.append((so, par, w))
        c, prev, k = m.u32(so + 8), 0, 0
        while c and k < 100000:
            if m.u32(c + 0x1C) != so or m.u32(c + 0x18) != prev:
                stats['bad_links'] += 1
            rec(c, so, w)
            prev, c, k = c, m.u32(c + 0x14), k + 1
        if k != m.u32(so + 0x10):
            stats['count_mismatch'] += 1
    rec(root, 0, IDENT)
    return out, stats


def read_mesh(m, zdr, skipped):
    nv, ne = m.u16s(zdr, 2)
    if nv == 0 or ne == 0 or ne > 512:
        return None
    voff, toff, eoff = m.u32(zdr + 8), m.u32(zdr + 0xC), m.u32(zdr + 0x10)
    vf = m.f32s(voff, 3 * nv)
    types = m.u16s(toff, ne)
    if vf is None or types is None or not all(math.isfinite(v) for v in vf):
        return None
    verts = [vf[i:i + 3] for i in range(0, 3 * nv, 3)]
    tris = []  # (v0, v1, v2, normal, material identifier, material type)
    for i, t in enumerate(types):
        if t != 1:
            skipped[t] += 1
            continue
        blk = m.u32(eoff + 4 * i)
        mat, toffs, noffs = m.u32(blk), m.u32(blk + 4), m.u32(blk + 8)
        nt = m.u16s(blk + 0xC, 1)[0]
        idx = m.u16s(toffs, 3 * nt) if nt else ()
        nrm = m.f32s(noffs, 3 * nt) if nt and noffs else None
        cm = m.u32(mat + 4) if mat else None
        mt, mid = m.u16s(cm, 2) if cm and m.rd(cm, 4) else (0xFFFF, 0xFFFF)
        for j in range(nt):
            a, b, c = idx[3 * j:3 * j + 3]
            if max(a, b, c) >= nv:
                skipped['bad_index'] += 1
                continue
            n = nrm[3 * j:3 * j + 3] if nrm else None
            tris.append((verts[a], verts[b], verts[c], n, mid, mt))
    return tris


def xform(w, v):
    return [w[r][0] * v[0] + w[r][1] * v[1] + w[r][2] * v[2] + w[r][3] for r in range(3)]


def xform_dir(w, v):
    return [w[r][0] * v[0] + w[r][1] * v[1] + w[r][2] * v[2] for r in range(3)]


def decode(m, rayman):
    chain = [rayman]
    while m.u32(chain[-1] + 0x1C):
        chain.append(m.u32(chain[-1] + 0x1C))
    root = chain[-1]
    nodes, stats = walk(m, root)
    hist = Counter(SO_TYPES.get(m.u32(so), hex(m.u32(so))) for so, _, _ in nodes)
    skipped, tris, meshes, nipo, flipped = Counter(), [], 0, 0, 0
    for so, _, w in nodes:
        t = m.u32(so)
        if t not in (0x20, 0x40, 8):
            continue
        data = m.u32(so + 4)
        po = m.u32(data) if t != 8 else data
        nipo += 1
        cs = m.u32(po + 4) if po else None
        zdr = m.u32(cs + 0xC) if cs else None
        mesh = read_mesh(m, zdr, skipped) if zdr else None
        if not mesh:
            continue
        meshes += 1
        for v0, v1, v2, n, mid, mt in mesh:
            p = [xform(w, v) for v in (v0, v1, v2)]
            if n is None:
                continue
            nw = xform_dir(w, n)
            tris.append((p, nw, mid, mt))
    return {'root': root, 'chain': chain, 'hist': dict(hist), 'link_stats': stats, 'nipo': nipo,
            'meshes': meshes, 'skipped': dict(skipped)}, tris


def save(d, info, tris):
    with open(os.path.join(d, 'collision.tris'), 'wb') as f:
        for p, n, mid, mt in tris:
            f.write(struct.pack('>9f3f2H', *p[0], *p[1], *p[2], *n, mid, mt))
    info = dict(info, triangles=len(tris), root=hex(info['root']), chain=[hex(c) for c in info['chain']])
    json.dump(info, open(os.path.join(d, 'collision.json'), 'w'), indent=1)


def load(d):
    raw = open(os.path.join(d, 'collision.tris'), 'rb').read()
    sz = struct.calcsize('>9f3f2H')
    return [(((u[0], u[1], u[2]), (u[3], u[4], u[5]), (u[6], u[7], u[8])), u[9:12], u[12], u[13])
            for u in (struct.unpack_from('>9f3f2H', raw, o) for o in range(0, len(raw), sz))]


def tri_z_at(p, x, y):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = p
    den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if den == 0:
        return None
    l1 = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / den
    l2 = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / den
    l3 = 1 - l1 - l2
    if min(l1, l2, l3) < -1e-6:
        return None
    return l1 * az + l2 * bz + l3 * cz


def unit_nz(n):
    L = math.sqrt(sum(c * c for c in n))
    return n[2] / L if L else 0.0


def query(tris, x, y, up_only=False):
    hits = []
    for p, n, mid, mt in tris:
        if min(p[0][0], p[1][0], p[2][0]) > x or max(p[0][0], p[1][0], p[2][0]) < x:
            continue
        if min(p[0][1], p[1][1], p[2][1]) > y or max(p[0][1], p[1][1], p[2][1]) < y:
            continue
        z = tri_z_at(p, x, y)
        if z is not None and (not up_only or unit_nz(n) > 0):
            hits.append((z, unit_nz(n), mid, mt))
    return sorted(hits)


# ---------------------------------------------------------------- rasters + PNG
FONT = {'0': '111101101101111', '1': '010110010010111', '2': '111001111100111', '3': '111001111001111',
        '4': '101101111001001', '5': '111100111001111', '6': '111100111101111', '7': '111001001001001',
        '8': '111101111101111', '9': '111101111001111', '-': '000000111000000', 'x': '101101010101101',
        'y': '101101010010010', 'z': '111001010100111', '.': '000000000000010'}


def png(path, w, h, px):  # px: list of rows of (r,g,b)
    raw = b''.join(b'\0' + bytes(c for p in row for c in p) for row in px)

    def chunk(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def text(px, x, y, s, col=(255, 255, 255), sc=2):
    for ch in s:
        g = FONT.get(ch)
        if g:
            for i, bit in enumerate(g):
                if bit == '1':
                    for dy in range(sc):
                        for dx in range(sc):
                            yy, xx = y + (i // 3) * sc + dy, x + (i % 3) * sc + dx
                            if 0 <= yy < len(px) and 0 <= xx < len(px[0]):
                                px[yy][xx] = col
        x += 4 * sc


def rasterize(tris):
    nx, ny = int((X1 - X0) / CELL), int((Y1 - Y0) / CELL)
    zs = {}  # (ix, iy) -> list of z of walkable surfaces
    for p, n, mid, mt in tris:
        if unit_nz(n) < WALK_NZ:
            continue
        xs, ys = [q[0] for q in p], [q[1] for q in p]
        i0, i1 = max(0, int((min(xs) - X0) / CELL)), min(nx - 1, int((max(xs) - X0) / CELL))
        j0, j1 = max(0, int((min(ys) - Y0) / CELL)), min(ny - 1, int((max(ys) - Y0) / CELL))
        for i in range(i0, i1 + 1):
            cx = X0 + (i + 0.5) * CELL
            for j in range(j0, j1 + 1):
                z = tri_z_at(p, cx, Y0 + (j + 0.5) * CELL)
                if z is not None:
                    zs.setdefault((i, j), []).append(z)
    return nx, ny, zs


def levels(zl):
    zl = sorted(zl)
    n, last = 0, None
    for z in zl:
        if last is None or z - last > STACK_GAP:
            n += 1
        last = z
    return n


def render(d, tris):
    nx, ny, zs = rasterize(tris)
    S, M = 2, 40
    W, H = nx * S + M + 10, ny * S + M + 10
    allz = sorted(max(v) for v in zs.values())
    lo, hi = (allz[len(allz) // 50], allz[-len(allz) // 50 - 1]) if allz else (-1, 1)

    def colour_z(z):
        t = min(1, max(0, (z - lo) / (hi - lo or 1)))
        return (int(255 * t), int(255 * (1 - abs(2 * t - 1))), int(255 * (1 - t)))
    pal = [(0, 0, 0), (60, 120, 220), (60, 200, 90), (240, 220, 60), (240, 130, 40), (230, 50, 50)]
    for name, fn in (('heightmap.png', lambda v: colour_z(max(v))), ('levels.png', lambda v: pal[min(levels(v), 5)])):
        px = [[(20, 20, 20)] * W for _ in range(H)]
        for (i, j), v in zs.items():
            c = fn(v)
            for dy in range(S):
                for dx in range(S):
                    px[M + (ny - 1 - j) * S + dy][M + i * S + dx] = c  # y up
        for gx in range(int(X0), int(X1) + 1, 10):
            xx = M + int((gx - X0) / CELL) * S
            for yy in range(M, M + ny * S, 1):
                if gx % 50 == 0 or yy % 4 == 0:
                    px[yy][xx] = (90, 90, 90)
            if gx % 20 == 0:
                text(px, xx - 6, M - 14, str(gx), sc=1) if False else text(px, xx - 6, 4 + (gx // 10 % 2) * 12, str(gx), sc=2)
        for gy in range(int(Y0), int(Y1) + 1, 10):
            yy = M + (ny - 1 - int((gy - Y0) / CELL)) * S
            for xx in range(M, M + nx * S, 1):
                if gy % 50 == 0 or xx % 4 == 0:
                    px[yy][xx] = (90, 90, 90)
            text(px, 0, yy - 4, str(gy), sc=1)
        png(os.path.join(d, name), W, H, px)
    return zs, (lo, hi)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('snapshot')
    ap.add_argument('--query', nargs=2, type=float, metavar=('X', 'Y'))
    ap.add_argument('--rayman', type=lambda s: int(s, 0), default=0x40C52514)
    ap.add_argument('--rebuild', action='store_true', help='re-decode even if collision.tris exists')
    a = ap.parse_args()
    d = a.snapshot
    if a.rebuild or not os.path.exists(os.path.join(d, 'collision.tris')):
        m = Mem(d)
        info, tris = decode(m, a.rayman)
        save(d, info, tris)
        print('root %s  hierarchy %s  link_stats %s' % (hex(info['root']), info['hist'], info['link_stats']))
        print('physical-object SOs %d  meshes %d  triangles %d  skipped element types %s' %
              (info['nipo'], info['meshes'], len(tris), info['skipped']))
        zs, rng = render(d, tris)
        print('cells %d, colour range z %.1f..%.1f' % (len(zs), *rng))
    else:
        tris = load(d)
    if a.query:
        for z, nz, mid, mt in query(tris, *a.query):
            print('z=%.3f nz=%+.3f material id=%s type=%s' % (z, nz, mid, mt))
    elif not a.query:
        print('acceptance (expected z vs nearest upward surface at/below, and nearest any):')
        for x, y, z in ACCEPT:
            up = [h for h in query(tris, x, y) if h[1] > 0.0]
            below = [h for h in up if h[0] <= z + 0.05]
            near = min(up, key=lambda h: abs(h[0] - z)) if up else None
            b = max(below, key=lambda h: h[0]) if below else None
            print('(%7.2f,%6.2f) expected %6.2f  nearest up-surface %s  highest at-or-below %s  all up z=%s' % (
                x, y, z, '%.2f (d=%+.2f)' % (near[0], near[0] - z) if near else 'none',
                '%.2f (d=%+.2f)' % (b[0], b[0] - z) if b else 'none', [round(h[0], 2) for h in up]))


if __name__ == '__main__':
    sys.exit(main())
