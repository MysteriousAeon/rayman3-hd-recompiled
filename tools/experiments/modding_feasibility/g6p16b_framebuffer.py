"""G6-P16b (D-272 / E-505): camera-aware framebuffer attribution, one rule for identical and shifted cameras. Offline.

    python -I tools/experiments/modding_feasibility/g6p16b_framebuffer.py selftest   synthetic cases (no game data)
    python -I tools/experiments/modding_feasibility/g6p16b_framebuffer.py controls   O1 + O3 on retained references
    python -I tools/experiments/modding_feasibility/g6p16b_framebuffer.py evaluate   O1-O4, cases A and B

Inputs (private, retained; nothing new is captured): R1 e502_v1_ref, R2 e502_d1_ref_trace (collision-only spawn drop,
original visual), case A V = e502_v1_vis (G6-P15 single-surface visual edit, camera shifted 0.08), case B V =
e504_v1_ms_trace (G6-P16 multi-surface edit, camera identical to R1). Output private/work/e505/*.json, numbers only.

FROZEN DECISION RULE (written, validated on synthetic data and on the reference-only controls, and committed before
`evaluate` is run; not changed after)
Correspondence (as G6-P15b Method A): surface points = barycentric samples (step 1/12, 55 per triangle) of a visual
triangle; a 3D point is projected with the camera constants of the frame's own traced draw of that triangle's element;
pixel = floor; colour error = max |dR|, |dG|, |dB|. A sample is valid in an observation if w > 0, it is inside the
frame, >= 2 px from every projected edge of its triangle, and outside the occluder box (Rayman: the G6-P15b box).
Hypotheses for a modified frame V against a reference frame R (R has the original geometry):
  H0 original: V at (original point, V camera)  vs  R at (original point, R camera)  -> e0
  H1 edited:   V at (edited point,   V camera)  vs  R at (original point, R camera)  -> e1
(the texture is attached to the surface: the edit moves vertices, not UVs, so the same surface point carries the same
colour under the true hypothesis.)
Unit of analysis = one TRIANGLE (not one pixel or sample): samples inside a triangle are spatially correlated.
  A triangle is usable if >= 5 of its samples are valid in all three observations and discriminative (the H0 and H1
  projections in V are >= 2 px apart). d_t = mean(e0) - mean(e1) over those samples; a win if d_t > 0, a loss if
  d_t < 0, a tie otherwise (excluded). No colour epsilon is used.
Per comparison (one frame label, one reference):
  (a) n = usable edited triangles >= 8;
  (b) wins / (wins + losses) >= 0.80 and the one-sided binomial tail at TRIANGLE level <= 0.01. Assumption: triangles
      as independent units. They are not fully independent (shared vertices, shared texture, one camera), so p is an
      indicator, not proof; the criterion must also hold in every frame / reference comparison separately;
  (c) explanatory power, zero-safe: e0_bar, e1_bar = means over usable triangles of their mean e0 / e1; u_bar = mean
      over unchanged triangles (>= 5 valid samples each) of the mean V-vs-R error at the same surface point (each frame
      its own camera: it carries the same camera difference and the same resampling). E = (e0_bar - e1_bar) /
      (e0_bar - u_bar) is the share of the excess error that H1 removes. Needs e0_bar > u_bar (there is something to
      explain); E >= 0.5;
  (d) spatial association / placebo: on unchanged triangles of the same frames, a fake H1 that lowers the triangle by
      the edit's largest |dz| must not win: fake-win fraction <= 0.5 over >= 8 usable unchanged triangles.
  SUPPORT if (a)-(d) all hold. REJECT if the win fraction <= 0.5, or e0_bar <= u_bar, or E <= 0. Otherwise
  INCONCLUSIVE (including n < 8 or too few placebo triangles).
Negative control per case: R2 treated as V against R1 (no visual edit in either), under the case's H1, both labels:
  must be REJECT (O3). It fails if SUPPORT; INCONCLUSIVE is reported.
Case verdict: O1 (identity) and O2 (selftest) and O3 must pass first. VERIFIED if every modified comparison (2 labels x
2 references) is SUPPORT; FAILED if every one is REJECT; otherwise PARTIAL. Not used as evidence: same-screen-pixel
differences; pointwise p-values; any synthetic case on its own.
"""
import json
import math
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

OUT = HERE.parents[2] / "private" / "work" / "e505"
STEP = 12


# ------------------------------------------------------------------------------------------------- core rule
def project(m, p, W, H):
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


def samples(step=STEP):
    return [(i / step, j / step, 1 - (i + j) / step) for i in range(step + 1) for j in range(step + 1 - i)
            if min(i / step, j / step, 1 - (i + j) / step) >= 1 / (2 * step)]


def bary(tri, l):
    return [l[0] * tri[0][i] + l[1] * tri[1][i] + l[2] * tri[2][i] for i in range(3)]


def binom_tail(k, n):
    if k <= 0:
        return 1.0
    lg = math.lgamma
    terms = [lg(n + 1) - lg(i + 1) - lg(n - i + 1) - n * math.log(2) for i in range(k, n + 1)]
    mx = max(terms)
    return min(1.0, math.exp(mx) * sum(math.exp(t - mx) for t in terms))


def compare(V, R, tris, W, H, boxV=None, boxR=None, fake_dz=0.3):
    """One comparison. V, R: {(x, y): (r, g, b)}; tris: [{"o": 3 pts, "m": 3 pts, "edited": bool, "cV": 4x4, "cR": 4x4}].
    Returns the per-comparison numbers and its class (SUPPORT / REJECT / INCONCLUSIVE)."""
    S = samples()

    def valid(m, tri3, pt, box):
        if pt is None or not (0 <= pt[0] < W and 0 <= pt[1] < H):
            return False
        sp = [project(m, v, W, H) for v in tri3]
        if any(s is None for s in sp) or edge_dist(pt, [s[:2] for s in sp]) < 2:
            return False
        return not (box and box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3])

    def look(img, p):
        return img.get((int(math.floor(p[0])), int(math.floor(p[1]))))

    def err(a, b):
        return max(abs(a[i] - b[i]) for i in range(3))

    def pair(t, hyp):
        """(e0 list, e1 list) over discriminative valid samples of triangle t under hypothesis triangle hyp."""
        e0, e1 = [], []
        for lb in S:
            po, pm = bary(t["o"], lb), bary(hyp, lb)
            v0, v1, r0 = project(t["cV"], po, W, H), project(t["cV"], pm, W, H), project(t["cR"], po, W, H)
            if not (valid(t["cV"], t["o"], v0, boxV) and valid(t["cV"], hyp, v1, boxV) and valid(t["cR"], t["o"], r0, boxR)):
                continue
            if math.hypot(v1[0] - v0[0], v1[1] - v0[1]) < 2:
                continue
            a, b, c = look(V, v0), look(V, v1), look(R, r0)
            if a is None or b is None or c is None:
                continue
            e0.append(err(a, c))
            e1.append(err(b, c))
        return e0, e1
    wins = losses = ties = 0
    e0m, e1m, per = [], [], []
    for t in tris:
        if not t["edited"]:
            continue
        e0, e1 = pair(t, t["m"])
        if len(e0) < 5:
            continue
        d = sum(e0) / len(e0) - sum(e1) / len(e1)
        wins, losses, ties = wins + (d > 0), losses + (d < 0), ties + (d == 0)
        e0m.append(sum(e0) / len(e0))
        e1m.append(sum(e1) / len(e1))
        per.append(round(d, 3))
    ures, fw, fl = [], 0, 0
    for t in tris:
        if t["edited"]:
            continue
        es = []
        for lb in S:
            p = bary(t["o"], lb)
            v, r = project(t["cV"], p, W, H), project(t["cR"], p, W, H)
            if valid(t["cV"], t["o"], v, boxV) and valid(t["cR"], t["o"], r, boxR):
                a, b = look(V, v), look(R, r)
                if a is not None and b is not None:
                    es.append(err(a, b))
        if len(es) >= 5:
            ures.append(sum(es) / len(es))
        fake = [[q[0], q[1], q[2] - fake_dz] for q in t["o"]]
        e0, e1 = pair(t, fake)
        if len(e0) >= 5:
            d = sum(e0) / len(e0) - sum(e1) / len(e1)
            fw, fl = fw + (d > 0), fl + (d < 0)
    n = len(e0m)
    dec = wins + losses
    frac = wins / dec if dec else None
    p = binom_tail(wins, dec) if dec else 1.0
    e0b = sum(e0m) / n if n else None
    e1b = sum(e1m) / n if n else None
    ub = sum(ures) / len(ures) if ures else None
    E = (e0b - e1b) / (e0b - ub) if n and ub is not None and e0b > ub else None
    pf = fw / (fw + fl) if fw + fl else None
    res = {"usable": n, "wins": wins, "losses": losses, "ties": ties, "win_frac": round(frac, 4) if frac is not None else None,
           "p_triangle": p, "e0_bar": e0b and round(e0b, 3), "e1_bar": e1b and round(e1b, 3),
           "u_bar": ub if ub is None else round(ub, 3), "unchanged_triangles": len(ures), "E": E if E is None else round(E, 4),
           "placebo_usable": fw + fl, "placebo_win_frac": pf if pf is None else round(pf, 4), "d_per_triangle": per}
    res["a"] = n >= 8
    res["b"] = frac is not None and frac >= 0.8 and p <= 0.01
    res["c"] = E is not None and E >= 0.5
    res["d"] = pf is not None and fw + fl >= 8 and pf <= 0.5
    if res["a"] and res["b"] and res["c"] and res["d"]:
        res["class"] = "SUPPORT"
    elif (frac is not None and frac <= 0.5) or (n and ub is not None and e0b <= ub) or (E is not None and E <= 0):
        res["class"] = "REJECT"
    else:
        res["class"] = "INCONCLUSIVE"
    return res


# ------------------------------------------------------------------------------------------------- synthetic (O2)
def _cam(eye, target, W, H, fov=0.9):
    def sub(a, b): return [a[i] - b[i] for i in range(3)]
    def nrm(a): n = math.sqrt(sum(x * x for x in a)); return [x / n for x in a]   # noqa: E702
    def crs(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    f = nrm(sub(target, eye))
    r = nrm(crs(f, [0, 0, 1]))
    u = crs(r, f)
    t = 1 / math.tan(fov / 2)
    a = W / H
    dot = lambda x, y: sum(x[i] * y[i] for i in range(3))   # noqa: E731
    return [[t / a * r[0], t / a * r[1], t / a * r[2], -t / a * dot(r, eye)],
            [t * u[0], t * u[1], t * u[2], -t * dot(u, eye)],
            [f[0], f[1], f[2], -dot(f, eye)],
            [f[0], f[1], f[2], -dot(f, eye)]]


def _scene(dz_a=-0.6, dz_b=-0.3):
    """A 6 x 6 textured ground grid (original synthetic shapes and colours); vertex (3, 3) and its two neighbours
    lowered dz_a, the next ring dz_b (a two-step bowl like the real edit). Returns (orig tris, mod tris, edited flags,
    per-vertex uv)."""
    N = 6
    V = {(i, j): [2.0 * i, 2.0 * j, 0.0] for i in range(N + 1) for j in range(N + 1)}
    A = {(3, 3), (3, 2), (2, 3)}
    B = {(2, 2), (4, 3), (3, 4), (4, 2), (2, 4)}
    M = {k: [v[0], v[1], v[2] + (dz_a if k in A else dz_b if k in B else 0.0)] for k, v in V.items()}
    tris = []
    for i in range(N):
        for j in range(N):
            for t in (((i, j), (i + 1, j), (i + 1, j + 1)), ((i, j), (i + 1, j + 1), (i, j + 1))):
                tris.append((t, bool(set(t) & (A | B))))
    return V, M, tris


def _tex(u, v):
    return (int(128 + 100 * math.sin(2.3 * u) * math.cos(1.9 * v)), int(128 + 100 * math.sin(1.7 * u + 0.8 * v)),
            int(128 + 100 * math.cos(2.9 * v - 0.6 * u)))


def _render(verts, tris, cam, W, H):
    img = {(x, y): (40, 40, 40) for x in range(W) for y in range(H)}
    depth = {}
    for t, _ in tris:
        P = [project(cam, verts[k], W, H) for k in t]
        if any(p is None for p in P):
            continue
        uv = [(verts_uv[0], verts_uv[1]) for verts_uv in (_UV[k] for k in t)]
        (ax, ay, aw), (bx, by, bw), (cx, cy, cw) = P
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-9:
            continue
        for y in range(max(0, int(min(ay, by, cy))), min(H, int(max(ay, by, cy)) + 1)):
            for x in range(max(0, int(min(ax, bx, cx))), min(W, int(max(ax, bx, cx)) + 1)):
                px, py = x + 0.5, y + 0.5
                l1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
                l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
                l3 = 1 - l1 - l2
                if min(l1, l2, l3) < 0:
                    continue
                q = [l1 / aw, l2 / bw, l3 / cw]
                s = sum(q)
                w = 1 / s
                if depth.get((x, y), 1e9) <= w:
                    continue
                depth[(x, y)] = w
                u = sum(q[i] * uv[i][0] for i in range(3)) / s
                v = sum(q[i] * uv[i][1] for i in range(3)) / s
                img[(x, y)] = _tex(u, v)
    return img


_UV = {}


def selftest():
    W, H = 320, 180
    V0, VM, grid = _scene()
    _UV.clear()
    _UV.update({k: (v[0], v[1]) for k, v in V0.items()})   # texture attached to the surface (edit keeps UVs)
    cam = _cam([6.0, -4.0, 6.0], [6.0, 6.0, 0.0], W, H)
    cam2 = _cam([6.05, -4.03, 6.04], [6.02, 6.0, 0.0], W, H)   # slightly shifted camera
    away = _cam([6.0, -4.0, 6.0], [6.0, -14.0, 0.0], W, H)     # looks away: edited surface off screen

    def tris_for(cV, cR):
        return [{"o": [V0[k] for k in t], "m": [VM[k] for k in t], "edited": e, "cV": cV, "cR": cR} for t, e in grid]
    R = _render(V0, grid, cam, W, H)
    out = {}

    def case(name, Vimg, cV, cR, expect, Rimg=None, **kw):
        r = compare(Vimg, Rimg or R, tris_for(cV, cR), W, H, **kw)
        out[name] = {"class": r["class"], "expect": expect, "ok": r["class"] in expect,
                     **{k: r[k] for k in ("usable", "wins", "losses", "win_frac", "E", "u_bar", "placebo_win_frac")}}
    case("1 identical camera, no change", R, cam, cam, ("REJECT",), fake_dz=0.6)
    case("2 identical camera, surface lowered", _render(VM, grid, cam, W, H), cam, cam, ("SUPPORT",), fake_dz=0.6)
    case("3 shifted camera, no change", _render(V0, grid, cam2, W, H), cam2, cam, ("REJECT",), fake_dz=0.6)
    case("4 shifted camera, surface lowered", _render(VM, grid, cam2, W, H), cam2, cam, ("SUPPORT",), fake_dz=0.6)
    blob_out = dict(R)
    blob_in = dict(R)
    for x in range(10, 60):
        for y in range(5, 40):
            blob_out[(x, y)] = (250, 10, 200)      # far corner, away from the edited triangles
    ed = [project(cam, bary([V0[k] for k in t], (1 / 3, 1 / 3, 1 / 3)), W, H) for t, e in grid if e]
    cx, cy = sum(p[0] for p in ed) / len(ed), sum(p[1] for p in ed) / len(ed)
    for x in range(int(cx) - 25, int(cx) + 25):
        for y in range(int(cy) - 12, int(cy) + 12):
            blob_in[(x, y)] = ((x * 37) % 256, (y * 53) % 256, (x * y) % 256)   # unrelated change inside the region
    case("5a unrelated change outside the region, no geometry change", blob_out, cam, cam, ("REJECT", "INCONCLUSIVE"),
         fake_dz=0.6)
    case("5b unrelated change inside the region, no geometry change", blob_in, cam, cam, ("REJECT", "INCONCLUSIVE"),
         fake_dz=0.6)
    case("6a edited surface off screen", _render(VM, grid, away, W, H), away, away, ("INCONCLUSIVE",),
         Rimg=_render(V0, grid, away, W, H), fake_dz=0.6)
    case("6b edited surface occluded", _render(VM, grid, cam, W, H), cam, cam, ("INCONCLUSIVE",),
         boxV=(0, 0, W, H * 0.75), boxR=(0, 0, W, H * 0.75), fake_dz=0.6)
    ok = all(v["ok"] for v in out.values())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "selftest.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: (v["class"], v["ok"]) for k, v in out.items()}, indent=1))
    print(json.dumps({"selftest": ok}))
    return 0 if ok else 1


# ------------------------------------------------------------------------------------------------- retained data
RUNS = {"R1": "e502_v1_ref", "R2": "e502_d1_ref_trace", "A": "e502_v1_vis", "B": "e504_v1_ms_trace"}
RAY = (-95.89602661132812, 56.432716369628906, -9.404156684875488)


def load():
    import g6p13_collision as h
    import g6p16_multi_surface as ms
    import m22_draw_report as rep
    lvl, _ = h.files()
    orig = h.visual_model(lvl)
    mods = {"A": h.visual_model(h.apply(lvl, h.edits(h.VISP))), "B": h.visual_model(h.apply(lvl, ms.edits()))}
    edited = {"A": {1134, 1187, 1188}, "B": set(ms.EDITED_VIS)}
    cams, imgs, frames, exes = {}, {}, {}, {}
    for k, r in RUNS.items():
        exes[k] = json.loads((h.RUNS / r / "run.json").read_text(encoding="utf-8-sig"))["executable_sha256"]
        fr = h._frames(r)
        frames[k] = [f[0] for f in fr]
        expect = mods[k] if k in mods else orig
        for li, (_, draws, bmp) in enumerate(fr):
            for el, shape in ((14, h.E14), (0, h.E0)):
                want = expect[el][0]
                hit = [d for d in h._find(draws, shape) if [d["bindings"][0]["data"][i * shape[1]:i * shape[1] + 12]
                                                            for i in range(len(want))] == want]
                if hit:
                    c = hit[0]["consts"]
                    cams[(k, li, el)] = [[rep.f32(c[r_ * 4 + j]) for j in range(4)] for r_ in range(4)]
            imgs[(k, li)] = h._pixels(bmp)[2]
    o1 = {"executables": {k: v[:16] for k, v in exes.items()}, "frames": frames,
          "level_sha256": h.rm.sha256_bytes(lvl)[:16],
          "camera_draws": len(cams),
          "camera_diff_vs_R1": {f"{k}/{'ab'[li]}": max(abs(a - b) for ra, rb in zip(cams[(k, li, 14)], cams[("R1", li, 14)])
                                                       for a, b in zip(ra, rb))
                                for k in RUNS for li in (0, 1) if (k, li, 14) in cams and ("R1", li, 14) in cams}}
    o1["ok"] = (len(set(exes.values())) == 1 and all(len(v) == 2 for v in frames.values()) and len(cams) == 16
                and h.rm.sha256_bytes(lvl) == h.rm.COLLISION_ALLOW["intro_15"]["lvl"][1])
    return {"orig": orig, "mods": mods, "edited": edited, "cams": cams, "imgs": imgs, "O1": o1}


def real_compare(D, vk, rk, li, case):
    import g6p15b_render_attribution as pb
    orig, mod, edited = D["orig"], D["mods"][case], D["edited"][case]
    tris = []
    for el in (14, 0):
        po = [struct.unpack(">3f", c) for c in orig[el][0]]
        pm = [struct.unpack(">3f", c) for c in mod[el][0]]
        idx = orig[el][1]
        for t in range(len(idx) // 3):
            tris.append({"o": po[3 * t:3 * t + 3], "m": pm[3 * t:3 * t + 3], "edited": bool(set(idx[3 * t:3 * t + 3]) & edited),
                         "cV": D["cams"][(vk, li, el)], "cR": D["cams"][(rk, li, el)]})

    def box(m):
        pts = [pb.project(m, (RAY[0] + dx, RAY[1] + dy, RAY[2] + dz)) for dx in (-0.8, 0.8) for dy in (-0.8, 0.8)
               for dz in (0.0, 2.5)]
        pts = [p for p in pts if p]
        return (min(p[0] for p in pts) - 4, min(p[1] for p in pts) - 4, max(p[0] for p in pts) + 4,
                max(p[1] for p in pts) + 4) if pts else None
    return compare(D["imgs"][(vk, li)], D["imgs"][(rk, li)], tris, 1280, 720, box(D["cams"][(vk, li, 14)]),
                   box(D["cams"][(rk, li, 14)]), fake_dz=0.3)


def controls(D=None, write=True):
    D = D or load()
    o3 = {}
    for case in ("A", "B"):
        for li in (0, 1):
            r = real_compare(D, "R2", "R1", li, case)
            o3[f"{case}/{'ab'[li]}"] = {k: v for k, v in r.items() if k != "d_per_triangle"}
    ok3 = all(v["class"] == "REJECT" for v in o3.values())
    res = {"O1": D["O1"], "O3": {"comparisons": o3, "ok": ok3}}
    if write:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "controls.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
        print(json.dumps({"O1": D["O1"]["ok"], "O3": {k: (v["class"], v["usable"], v["win_frac"], v["E"], v["e0_bar"],
                                                       v["u_bar"]) for k, v in o3.items()}, "O3 ok": ok3}, indent=1))
    return res, D


def evaluate():
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        o2 = selftest() == 0
    res, D = controls(write=False)
    res["O2"] = {"ok": o2}
    o4 = {}
    for case in ("A", "B"):
        comps = {}
        for rk in ("R1", "R2"):
            for li in (0, 1):
                comps[f"{'ab'[li]}/{rk}"] = real_compare(D, case, rk, li, case)
        cl = [c["class"] for c in comps.values()]
        verdict = ("VERIFIED" if all(c == "SUPPORT" for c in cl) else "FAILED" if all(c == "REJECT" for c in cl)
                   else "PARTIAL")
        if not (res["O1"]["ok"] and o2 and res["O3"]["ok"]):
            verdict = "NOT INTERPRETED (O1-O3)"
        o4[case] = {"comparisons": comps, "verdict": verdict}
    res["O4"] = o4
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "evaluate.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps({"O1": res["O1"]["ok"], "O2": o2, "O3": res["O3"]["ok"],
                      "O4": {c: {"verdict": v["verdict"], **{k: {x: r[x] for x in (
                          "class", "usable", "wins", "losses", "win_frac", "p_triangle", "e0_bar", "e1_bar", "u_bar",
                          "E", "placebo_usable", "placebo_win_frac")} for k, r in v["comparisons"].items()}}
                             for c, v in o4.items()}}, indent=1))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        sys.exit(selftest())
    if cmd == "controls":
        controls()
        sys.exit(0)
    if cmd == "evaluate":
        sys.exit(evaluate())
    print(__doc__)
    sys.exit(2)
