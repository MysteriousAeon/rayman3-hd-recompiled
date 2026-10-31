"""HD+ lighting research (E-344). Usage: hdl_light_census.py TRACE...

Census of 1t_d_8s (41B1B4CEE9BA516E) draws in M22 draw traces: guest-supplied point-light constants and, per draw,
the light the shader's formula adds at the captured vertices (offline evaluation of the title's HLSL). Also counts
1t_d_lighting (D64D176416571592) draws. Reads private traces; prints numbers only."""
import math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m22_draw_report as R

VS8S = 0x41B1B4CEE9BA516E
VSLIT = 0xD64D176416571592


def vc(d, i):
    w = d["consts"][i * 4:i * 4 + 4]
    return tuple(R.f32(x) for x in w)


def group(d, base_col, base_pos, rng):
    cols = [vc(d, base_col + k) for k in range(4)]  # rows R,G,B,A in the original's dp4 sense
    pos = [vc(d, base_pos + k) for k in range(4)]
    ranges = vc(d, rng)
    return cols, pos, ranges


def light_at(p, n, grp):
    cols, pos, ranges = grp
    vec = []
    for k in range(4):
        dx = [pos[k][j] - p[j] for j in range(3)]
        dist = math.sqrt(sum(x * x for x in dx)) or 1e-9
        dirm = max(0.0, sum(n[j] * dx[j] / dist for j in range(3)))
        r = ranges[k]
        m = 1.0 if (r > 0 and dist <= r) else 0.0
        vec.append(((r - dist) / r if r else 0.0) * m * dirm)
    return [sum(vec[k] * cols[c][k] for k in range(4)) for c in range(4)]


def main():
    for tr in sys.argv[1:]:
        draws, _, _ = R.parse(Path(tr))
        n8 = [d for d in draws if d["vs"] == VS8S]
        nl = [d for d in draws if d["vs"] == VSLIT]
        print(f"== {tr}: draws {len(draws)}, 1t_d_8s {len(n8)}, 1t_d_lighting {len(nl)}")
        for d in n8:
            g1 = group(d, 20, 24, 28)
            g2 = group(d, 40, 44, 48)
            active = []
            for gi, g in enumerate((g1, g2)):
                for k in range(4):
                    col = tuple(g[0][c][k] for c in range(4))
                    if g[2][k] > 0 and any(abs(x) > 1e-6 for x in col[:3]):
                        active.append((gi * 4 + k, tuple(round(x, 3) for x in g[1][k][:3]), round(g[2][k], 2),
                                       tuple(round(x, 3) for x in col)))
            # evaluate at vertices: need position + normal attributes
            n, attrs = R.vertices(d)
            posv = next((v for a, v in attrs if v and len(v[0]) == 3 and a["offset"] == 0), None)
            nrm = next((v for a, v in attrs if v and len(v[0]) == 3 and a["offset"] != 0), None)
            peak = 0.0
            lit = 0
            if posv and nrm and active:
                for i in range(min(n, len(posv), len(nrm))):
                    l1 = light_at(posv[i], nrm[i], g1)
                    l2 = light_at(posv[i], nrm[i], g2)
                    s = max(l1[c] + l2[c] for c in range(3))
                    peak = max(peak, s)
                    lit += s > 1 / 255
            print(f"  draw {d['draw']:4d} ps {d['ps']:016X} idx {d['index_count']:6d} verts {n:5d} "
                  f"active {len(active)} peak_add {peak:.3f} lit_verts {lit}")
            for a in active:
                print(f"      light {a[0]} pos {a[1]} range {a[2]} colour {a[3]}")


if __name__ == "__main__":
    main()
