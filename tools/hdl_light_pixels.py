"""HD+ lighting research (E-344). Host check of the point-light path: for static 1t_d_8s world vertices visible in
several traced frames with an unchanged camera, correlate the change of the rendered pixel with the change of the
light the title's shader formula predicts from that frame's guest constants. Usage: hdl_light_pixels.py RUN_DIR
(a run with R3HD_M22_DRAW_TRACE=1 and two or more frames; prints statistics only)."""
import struct, sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m22_draw_report as R
from hdl_light_census import VS8S, vc, group, light_at


def bmp(path):
    b = Path(path).read_bytes()
    off, w, h, bpp = struct.unpack_from("<I", b, 10)[0], *struct.unpack_from("<iiH", b, 18)[:2], struct.unpack_from("<H", b, 28)[0]
    return b, off, w, h, bpp


def pix(img, x, y):
    b, off, w, h, bpp = img
    bh = abs(h)
    row = (bh - 1 - y) if h > 0 else y
    stride = ((w * bpp // 8) + 3) & ~3
    o = off + row * stride + x * (bpp // 8)
    return b[o + 2], b[o + 1], b[o]  # R, G, B


def mvp(d):
    return [vc(d, k) for k in range(4)]


def main(run):
    run = Path(run)
    traces = sorted(run.glob("m22_draws_*.bin"))
    frames = []
    for t in traces:
        draws, _, _ = R.parse(t)
        img = bmp(run / t.name.replace("m22_draws_", "m3_frame_").replace(".bin", ".bmp"))
        frames.append((t.name, {(d["bindings"][0]["address"], d["index_count"]): d for d in draws if d["vs"] == VS8S}, img))
    keys = set(frames[0][1])
    for f in frames[1:]:
        keys &= set(f[1])
    samples = []  # (delta predicted rgb, delta pixel rgb)
    cam_same = True
    for k in sorted(keys):
        ds = [f[1][k] for f in frames]
        if any(mvp(d) != mvp(ds[0]) for d in ds):
            cam_same = False
            continue
        n, attrs = R.vertices(ds[0])
        posv = next((v for a, v in attrs if v and len(v[0]) == 3 and a["offset"] == 0), None)
        nrm = next((v for a, v in attrs if v and len(v[0]) == 3 and a["offset"] != 0), None)
        M = mvp(ds[0])
        for i in range(0, n, 3):
            p = posv[i]
            c = [sum(M[r][j] * (p[j] if j < 3 else 1.0) for j in range(4)) for r in range(4)]
            if c[3] <= 0.1:
                continue
            x, y = (c[0] / c[3] * 0.5 + 0.5) * 1280, (0.5 - c[1] / c[3] * 0.5) * 720
            if not (2 <= x < 1278 and 2 <= y < 718):
                continue
            pred = []
            px = []
            for d, f in zip(ds, frames):
                g1, g2 = group(d, 20, 24, 28), group(d, 40, 44, 48)
                l1, l2 = light_at(p, nrm[i], g1), light_at(p, nrm[i], g2)
                pred.append([l1[ch] + l2[ch] for ch in range(3)])
                px.append(pix(f[2], int(x), int(y)))
            for a in range(len(ds)):
                for b in range(a + 1, len(ds)):
                    dp = [pred[b][ch] - pred[a][ch] for ch in range(3)]
                    dx = [px[b][ch] - px[a][ch] for ch in range(3)]
                    samples.append((dp, dx))
    print("camera identical across frames for every shared draw:", cam_same, "samples:", len(samples))
    moving = [s for s in samples if abs(s[0][0]) > 0.05]
    still = [s for s in samples if abs(s[0][0]) < 0.005]
    print("pairs with predicted red change > 0.05:", len(moving), " with < 0.005:", len(still))
    for ch, name in enumerate("RGB"):
        xs = [s[0][ch] for s in samples]
        ys = [s[1][ch] for s in samples]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        sxx = sum((a - mx) ** 2 for a in xs)
        syy = sum((b - my) ** 2 for b in ys)
        r = sxy / math.sqrt(sxx * syy) if sxx and syy else float("nan")
        print(f"  {name}: corr(predicted delta, pixel delta) = {r:.3f}  slope = {sxy / sxx if sxx else float('nan'):.1f} per unit")
    if still:
        print("  mean |pixel delta| where predicted change ~0:",
              [round(sum(abs(s[1][ch]) for s in still) / len(still), 2) for ch in range(3)])
    if moving:
        print("  mean |pixel delta| where predicted red change > 0.05:",
              [round(sum(abs(s[1][ch]) for s in moving) / len(moving), 2) for ch in range(3)])


main(sys.argv[1])
