"""HD+ lighting research (E-345). Usage: hdl_raycast.py TRACE.bin X,Y [X,Y...]

Offline depth ray-cast of one M22 draw trace: for each screen point (1280x720 pixels) every triangle-list or
triangle-strip draw with a float3 position and an 8_8_8_8 colour that covers the point, with its depth (z/w), w,
interpolated vertex colour (bytes A, R, G, B) and the fog factor the HD world shader 1t_d computes (per vertex
saturate((end - w) / (end - start)) from vertex constant c4, then interpolated). Shows which coplanar surfaces
compete for a pixel and how much fog a large polygon gets. Prints numbers only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m22_draw_report as R


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def prepare(draws):
    out = []
    for d in draws:
        if d["primitive"] not in (4, 6) or not d["bindings"]:
            continue
        n, attrs = R.vertices(d)
        pos = next((v for a, v in attrs if a["format"] == 57 and v), None)
        col = next((v for a, v in attrs if a["format"] == 6 and v), None)
        if not n or pos is None or col is None:
            continue
        c = d["consts"]
        m = [[R.f32(c[r * 4 + j]) for j in range(4)] for r in range(4)]
        fog = [R.f32(x) for x in c[16:20]]
        clip = [[sum(m[r][j] * (p[j] if j < 3 else 1.0) for j in range(4)) for r in range(4)] for p in pos]
        idx = R.indices(d)
        step = 1 if d["primitive"] == 6 else 3
        tris = [idx[k:k + 3] for k in range(0, len(idx) - 2, step)]
        tris = [t for t in tris if max(t) < n and len(set(t)) == 3]
        out.append((d, clip, col, fog, tris))
    return out


def fog_factor(fog, w):
    return min(1.0, max(0.0, (fog[2] - w) / (fog[2] - fog[1]))) if fog[0] else 1.0


def cast(prepared, sx, sy):
    x, y = sx / 640 - 1, 1 - sy / 360
    hits = []
    for d, clip, col, fog, tris in prepared:
        best = None
        for t in tris:
            tri = [clip[i] for i in t]
            a = cross([v[0] - x * v[3] for v in tri], [v[1] - y * v[3] for v in tri])
            s = sum(a)
            if abs(s) < 1e-12:
                continue
            a = [k / s for k in a]
            if min(a) < -1e-6:
                continue
            w = sum(a[k] * tri[k][3] for k in range(3))
            if w <= 0:
                continue
            z = sum(a[k] * tri[k][2] for k in range(3)) / w
            if not 0 <= z <= 1 or (best and z >= best[0]):
                continue
            colour = [round(sum(a[k] * col[t[k]][m] for k in range(3))) for m in range(4)]
            best = (z, w, colour, sum(a[k] * fog_factor(fog, tri[k][3]) for k in range(3)), fog_factor(fog, w))
        if best:
            hits.append((d, best))
    return hits


def main():
    draws, _, _ = R.parse(Path(sys.argv[1]))
    prepared = prepare(draws)
    for p in sys.argv[2:]:
        sx, sy = map(int, p.split(","))
        print(f"== screen ({sx},{sy})")
        for d, (z, w, colour, fog_hd, fog_pixel) in cast(prepared, sx, sy):
            r = d["regs"]
            print(f"  draw {d['draw']:3d} z/w {z:.5f} w {w:7.2f} colour {colour} fog_hd {fog_hd:.3f} "
                  f"fog_per_pixel {fog_pixel:.3f} depth {r[0x200]:08X} blend {r[0x201]:08X}")


if __name__ == "__main__":
    main()
