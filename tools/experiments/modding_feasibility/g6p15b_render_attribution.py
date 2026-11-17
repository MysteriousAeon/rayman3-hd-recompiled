"""G6-P15b (D-270 / E-503): camera-independent render attribution on the retained G6-P15 frames. Offline only.

    python -I tools/experiments/modding_feasibility/g6p15b_render_attribution.py selftest
    python -I tools/experiments/modding_feasibility/g6p15b_render_attribution.py analyse

Inputs (private, retained; nothing new is captured): runs e502_v1_ref (R1), e502_v1_vis (V), e502_d1_ref_trace (R2),
two traced frames each (labels a = first, b = second). Outputs private/work/e503/analysis.json; numbers only.

METHOD AND DECISION RULE (written and committed before the analysis is run; not changed after results)
Method A, surface-coordinate correspondence. Surface points = barycentric samples (grid step 1/12, every coordinate
>= 1/24) of the 14 edited visual triangles (element 14: the ring of vertices 1134 / 1187 / 1188; element 0: its
ring). A point is projected with the camera constants (c0..c3) of the matching traced draw of each frame (element 14
or element 0 draw whose corner positions equal that run's expected geometry), viewport 1280 x 720 as
tools/hdl_raycast.py (x = (ndc_x + 1) * 640, y = (1 - ndc_y) * 360), pixel = floor. Colour error between two
observations = max over R, G, B of the absolute difference (0..255).
A sample is used only if, in every frame of the comparison, its projection has w > 0, lies inside the frame, lies at
least 2 px from each edge of its projected triangle (rasterization ambiguity), and lies outside the Rayman box (the
3D box x +- 0.8, y +- 0.8, z -9.404 .. -6.904 around his settled position, projected with that frame's camera, plus
4 px). Discriminative samples: additionally, the projections of the original and of the modified point under V's
camera are at least 2 px apart.
Errors (per frame label, per reference Rk in {R1, R2}):
  e_mod   = V at (modified point, V camera)  vs  Rk at (original point, Rk camera)
  e_orig  = V at (original point, V camera)  vs  Rk at (original point, Rk camera)   [counterfactual: not lowered]
  e_ctrl  = R2 at (original point, R2 camera) vs R1 at (original point, R1 camera)   [negative control]
  e_ctrl_mod = R2 at (modified point, R2 camera) vs R1 at (original point, R1 camera) [control under the edit's
               hypothesis: must not be favoured]
  Projection check (O2): unchanged triangles of element 14 (not in the ring), same filters: e_aware = V at (point,
  V camera) vs R1 at (point, R1 camera); e_naive = V at R1's pixel vs R1 at R1's pixel.
Criteria:
  O1 identity: 6 frames found, the same executable for all runs, the element-14 draw with the run's expected geometry
     in every frame (element 0 also), level file hash as D-269.
  O2 projection: synthetic selftest PASS; on unchanged triangles median(e_aware) <= median(e_naive) and
     median(e_aware) <= Q90(e_ctrl) (the camera-aware correspondence is no worse than natural variation).
  O3 negative control: on the discriminative samples, fraction(e_ctrl_mod < e_ctrl) <= 0.5 (R2 shows no preference for
     the modified geometry), reported with median and Q90 of e_ctrl.
  O4 attribution, for both frame labels and both references: (i) >= 100 discriminative samples; (ii) among samples where
     e_mod != e_orig, fraction(e_mod < e_orig) >= 0.70 with one-sided binomial p < 1e-6; (iii) median(e_mod) <=
     Q90(e_ctrl) of the same samples (the lowered surface matches the reference about as well as natural variation).
Classes: O1-O4 PASS -> VERIFIED; O1-O3 PASS and O4 (ii) PASS but (iii) FAIL anywhere -> PARTIAL (supported, not
verified); O4 (ii) FAIL -> FAILED; O1 FAIL (data missing) -> BLOCKED.
Not used as evidence: any synthetic projection on its own; same-screen-pixel differences (G6-P15's measure).
"""
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

W, H = 1280, 720
RUNS = {"R1": "e502_v1_ref", "V": "e502_v1_vis", "R2": "e502_d1_ref_trace"}
EDITED = {1134, 1187, 1188}
RAY = (-95.89602661132812, 56.432716369628906, -9.404156684875488)


def project(m, p):
    """Clip -> screen (x, y, w) with the hdl_raycast viewport convention; None when w <= 0."""
    c = [sum(m[r][j] * (p[j] if j < 3 else 1.0) for j in range(4)) for r in range(4)]
    if c[3] <= 1e-6:
        return None
    return ((c[0] / c[3] + 1) * W / 2, (1 - c[1] / c[3]) * H / 2, c[3])


def edge_dist(pt, tri):
    d = []
    for k in range(3):
        (ax, ay), (bx, by) = tri[k], tri[(k + 1) % 3]
        L = math.hypot(bx - ax, by - ay)
        d.append(abs((bx - ax) * (ay - pt[1]) - (ax - pt[0]) * (by - ay)) / L if L > 1e-9 else 0.0)
    return min(d)


def samples(step=12):
    out = []
    for i in range(step + 1):
        for j in range(step + 1 - i):
            l1, l2 = i / step, j / step
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) >= 1 / (2 * step):
                out.append((l1, l2, l3))
    return out


def bary(tri, l):
    return [l[0] * tri[0][i] + l[1] * tri[1][i] + l[2] * tri[2][i] for i in range(3)]


def selftest():
    ok = []
    ident = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    ok.append(project(ident, (0, 0, 0)) == (640.0, 360.0, 1.0))
    ok.append(project(ident, (1, 1, 0))[:2] == (1280.0, 0.0))          # +y up -> top row
    persp = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 1, 0]]   # w = z
    a, b = project(persp, (1, 0, 2)), project(persp, (1, 0, 4))
    ok.append(a[0] > b[0] > 640)                                       # farther -> closer to centre
    ok.append(project(persp, (0, 0, -1)) is None)
    ok.append(abs(edge_dist((2, 3), [(0, 0), (10, 0), (0, 10)]) - 2.0) < 1e-9)       # nearest edge x = 0
    ok.append(abs(edge_dist((5, 5), [(0, 0), (10, 0), (0, 10)])) < 1e-9)             # on the hypotenuse
    s = samples()
    ok.append(all(min(x) >= 1 / 24 and abs(sum(x) - 1) < 1e-12 for x in s) and len(s) == 55)
    print(json.dumps({"selftest": all(ok), "cases": ok}))
    return 0 if all(ok) else 1


def analyse():
    import g6p13_collision as h
    import m22_draw_report as rep
    lvl, _ = h.files()
    orig = h.visual_model(lvl)
    mod = h.visual_model(h.apply(lvl, h.edits(h.VISP)))
    res = {"O1": {}, "O2": {}, "O3": {}, "O4": {}}
    exes = {k: json.loads((h.RUNS / r / "run.json").read_text(encoding="utf-8-sig"))["executable_sha256"]
            for k, r in RUNS.items()}
    frames, cams, imgs = {}, {}, {}
    for k, r in RUNS.items():
        fr = h._frames(r)
        frames[k] = [f[0] for f in fr]
        expect = mod if k == "V" else orig
        for li, (name, draws, bmp) in enumerate(fr):
            for el, shape in ((14, h.E14), (0, h.E0)):
                want = expect[el][0]
                hit = [d for d in h._find(draws, shape) if [d["bindings"][0]["data"][i * shape[1]:i * shape[1] + 12]
                                                            for i in range(len(want))] == want]
                if hit:
                    c = hit[0]["consts"]
                    cams[(k, li, el)] = [[rep.f32(c[r_ * 4 + j]) for j in range(4)] for r_ in range(4)]
            imgs[(k, li)] = h._pixels(bmp)[2]
    res["O1"] = {"executables": {k: v[:16] for k, v in exes.items()}, "frames": frames,
                 "camera_draws_found": sorted(f"{k}/{li}/e{el}" for (k, li, el) in cams),
                 "level_sha256": h.rm.sha256_bytes(lvl)[:16],
                 "ok": len(set(exes.values())) == 1 and all(len(v) == 2 for v in frames.values())
                       and all((k, li, el) in cams for k in RUNS for li in (0, 1) for el in (14, 0))
                       and h.rm.sha256_bytes(lvl) == h.rm.COLLISION_ALLOW["intro_15"]["lvl"][1]}
    if not res["O1"]["ok"]:
        return finish(res, "BLOCKED")

    def tris(model, el, ring=True):
        pos, idx = model[el]
        P = [struct.unpack(">3f", c) for c in pos]
        out = []
        for t in range(len(idx) // 3):
            in_ring = bool(set(idx[3 * t:3 * t + 3]) & EDITED)
            if in_ring == ring:
                out.append((t, P[3 * t:3 * t + 3]))
        return out

    def ray_box(m):
        pts = [project(m, (RAY[0] + dx, RAY[1] + dy, RAY[2] + dz)) for dx in (-0.8, 0.8) for dy in (-0.8, 0.8)
               for dz in (0.0, 2.5)]
        pts = [p for p in pts if p]
        return (min(p[0] for p in pts) - 4, min(p[1] for p in pts) - 4, max(p[0] for p in pts) + 4,
                max(p[1] for p in pts) + 4) if pts else None

    def look(img, p):
        x, y = int(math.floor(p[0])), int(math.floor(p[1]))
        return img.get((x, y)) if 0 <= x < W and 0 <= y < H else None

    def err(a, b):
        return max(abs(a[i] - b[i]) for i in range(3))

    def valid(m, tri3, pt, box):
        sp = [project(m, v) for v in tri3]
        if pt is None or any(s is None for s in sp) or not (0 <= pt[0] < W and 0 <= pt[1] < H):
            return False
        if edge_dist(pt, [s[:2] for s in sp]) < 2:
            return False
        return not (box and box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3])

    def q(xs, f):
        s = sorted(xs)
        return s[min(len(s) - 1, int(f * len(s)))] if s else None
    S = samples()
    verdict = {}
    for li in (0, 1):
        label = "ab"[li]
        boxes = {k: ray_box(cams[(k, li, 14)]) for k in RUNS}
        rows = []
        for el in (14, 0):
            mV, m1, m2 = cams[("V", li, el)], cams[("R1", li, el)], cams[("R2", li, el)]
            mt = dict(tris(mod, el))
            for t, to in tris(orig, el):
                tm = mt[t]
                for l in S:
                    po, pm = bary(to, l), bary(tm, l)
                    pV_m, pV_o = project(mV, pm), project(mV, po)
                    p1, p2, p2_m = project(m1, po), project(m2, po), project(m2, pm)
                    if not (valid(mV, tm, pV_m, boxes["V"]) and valid(mV, to, pV_o, boxes["V"])
                            and valid(m1, to, p1, boxes["R1"]) and valid(m2, to, p2, boxes["R2"])
                            and valid(m2, tm, p2_m, boxes["R2"])):
                        continue
                    disc = math.hypot(pV_m[0] - pV_o[0], pV_m[1] - pV_o[1]) >= 2
                    c = {n: look(imgs[(k, li)], p) for n, k, p in (("Vm", "V", pV_m), ("Vo", "V", pV_o),
                                                                   ("R1", "R1", p1), ("R2", "R2", p2),
                                                                   ("R2m", "R2", p2_m))}
                    if any(v is None for v in c.values()):
                        continue
                    rows.append({"disc": disc, "e_mod1": err(c["Vm"], c["R1"]), "e_orig1": err(c["Vo"], c["R1"]),
                                 "e_mod2": err(c["Vm"], c["R2"]), "e_orig2": err(c["Vo"], c["R2"]),
                                 "e_ctrl": err(c["R2"], c["R1"]), "e_ctrl_mod": err(c["R2m"], c["R1"]),
                                 "shift_px": math.hypot(pV_m[0] - pV_o[0], pV_m[1] - pV_o[1])})
        D = [r for r in rows if r["disc"]]
        ctrl = [r["e_ctrl"] for r in D]
        # O2: unchanged element-14 triangles
        aware, naive = [], []
        mV, m1 = cams[("V", li, 14)], cams[("R1", li, 14)]
        for t, tt in tris(orig, 14, ring=False):
            for l in S[::5]:
                p = bary(tt, l)
                pv, p1 = project(mV, p), project(m1, p)
                if not (valid(mV, tt, pv, boxes["V"]) and valid(m1, tt, p1, boxes["R1"])):
                    continue
                a, b, c_ = look(imgs[("V", li)], pv), look(imgs[("R1", li)], p1), look(imgs[("V", li)], p1)
                if a and b and c_:
                    aware.append(err(a, b))
                    naive.append(err(c_, b))
        o2 = {"unchanged_samples": len(aware), "median_aware": q(aware, 0.5), "median_naive": q(naive, 0.5),
              "q90_ctrl": q(ctrl, 0.9)}
        o2["ok"] = bool(aware) and o2["median_aware"] <= o2["median_naive"] and o2["median_aware"] <= (o2["q90_ctrl"] or 0)
        res["O2"][label] = o2
        neq = [r for r in D if r["e_ctrl_mod"] != r["e_ctrl"]]
        o3 = {"disc_samples": len(D), "median_ctrl": q(ctrl, 0.5), "q90_ctrl": q(ctrl, 0.9),
              "frac_ctrl_mod_better": round(sum(r["e_ctrl_mod"] < r["e_ctrl"] for r in neq) / len(neq), 4) if neq else None}
        o3["ok"] = o3["frac_ctrl_mod_better"] is not None and o3["frac_ctrl_mod_better"] <= 0.5
        res["O3"][label] = o3
        for ref in ("1", "2"):
            ne = [r for r in D if r["e_mod" + ref] != r["e_orig" + ref]]
            n, k = len(ne), sum(r["e_mod" + ref] < r["e_orig" + ref] for r in ne)
            p = binom_tail(k, n) if n else 1.0
            em = [r["e_mod" + ref] for r in D]
            o4 = {"disc_samples": len(D), "decisive": n, "mod_better": k, "frac": round(k / n, 4) if n else None,
                  "p_one_sided": p, "median_e_mod": q(em, 0.5), "median_e_orig": q([r["e_orig" + ref] for r in D], 0.5),
                  "q90_ctrl": q(ctrl, 0.9), "median_shift_px": round(q([r["shift_px"] for r in D], 0.5), 2) if D else None}
            o4["ii"] = n > 0 and k / n >= 0.70 and p < 1e-6
            o4["iii"] = bool(D) and o4["median_e_mod"] <= o4["q90_ctrl"]
            o4["i"] = len(D) >= 100
            res["O4"][f"{label}/R{ref}"] = o4
        res.setdefault("all_samples", {})[label] = len(rows)
    O2 = all(v["ok"] for v in res["O2"].values())
    O3 = all(v["ok"] for v in res["O3"].values())
    O4ii = all(v["i"] and v["ii"] for v in res["O4"].values())
    O4iii = all(v["iii"] for v in res["O4"].values())
    cls = ("VERIFIED" if O2 and O3 and O4ii and O4iii else "PARTIAL" if O2 and O3 and O4ii else
           "FAILED" if not O4ii else "PARTIAL")
    return finish(res, cls)


def binom_tail(k, n):
    """P(X >= k), X ~ Binomial(n, 0.5), in log space."""
    if k <= 0:
        return 1.0
    lg = math.lgamma
    terms = [lg(n + 1) - lg(i + 1) - lg(n - i + 1) - n * math.log(2) for i in range(k, n + 1)]
    mx = max(terms)
    return min(1.0, math.exp(mx) * sum(math.exp(t - mx) for t in terms))


def finish(res, cls):
    res["class"] = cls
    out = ROOT / "private" / "work" / "e503"
    out.mkdir(parents=True, exist_ok=True)
    (out / "analysis.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        sys.exit(selftest())
    if cmd == "analyse":
        sys.exit(analyse())
    print(__doc__)
    sys.exit(2)
