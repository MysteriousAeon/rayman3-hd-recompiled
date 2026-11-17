"""G6-P19 (E-508): intro_20 terrain feasibility (development only).

    python -I tools/experiments/modding_feasibility/g6p19_intro20.py probe TAG    one read-only hidden location probe
    python -I tools/experiments/modding_feasibility/g6p19_intro20.py ground TAG   offline: meshes under the settled point
    python -I tools/experiments/modding_feasibility/g6p19_intro20.py region TAG ZDR  offline: ownership, twins, neighbours
    python -I tools/experiments/modding_feasibility/g6p19_intro20.py check        offline O1-O5 of start-two-step-v1
    python -I tools/experiments/modding_feasibility/g6p19_intro20.py run TAG      the modified traced run V (protocol RUN_DOC)
    python -I tools/experiments/modding_feasibility/g6p19_intro20.py ref TAG r1|r2  reference runs, only if the P5 gate passes
    python -I tools/experiments/modding_feasibility/g6p19_intro20.py judge TAG    P1-P6 of V (RUN_DOC below)

PROBE PROTOCOL (read-only; no plan, no input, no gate): retained intro_20 runs (E-480 s1 / f1, E-489) sampled only
graph-owning actors, so Rayman's position in intro_20 is unknown. One hidden run through m9_license_run.py
(--test-level intro_20, 230 s, disposable profile, license mask 1, steps: wait only), as E-480 / E-499. After the level
opens: one actor discovery (m5_memory_probe.py), then Rayman's (YLT_RaymanModel) position and behaviour every 0.2 s,
read-only. Judges: M21 / M22 / M23 = 0, haptics policy line, runner exit 0, no process left. Output private
(private/work/e508/TAG). Used only to choose a region; not a baseline for any modified-run criterion unless a later
protocol says so explicitly.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g6p13_collision as h  # noqa: E402

rm, ROOT, TOOLS, RUNS = h.rm, h.ROOT, h.TOOLS, h.RUNS
LEVEL, PREFIX, SECONDS, RAY = "intro_20", "e508", 230, "YLT_RaymanModel"


def probe(tag):
    from m5_live import Actor, Process
    import os
    work = ROOT / "private" / "work" / PREFIX / tag
    run = f"{PREFIX}_{tag}_probe"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    env.pop(rm.STRUCT_ENV, None)
    (work / "steps.txt").write_text(f"wait {SECONDS - 8}\n", encoding="ascii")
    row, samples, actors = {"run": run}, [], []
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(SECONDS), "--play", "--test-level", LEVEL,
                                 "--user-root", run], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        needle = re.compile(rf"[\\/]{LEVEL}\.lvl result=00000000", re.IGNORECASE)
        opened, vbase, end = None, None, time.monotonic() + 90
        while time.monotonic() < end and game.poll() is None and opened is None:
            time.sleep(0.5)
            lp = RUNS / run / "runtime.log"
            if lp.is_file():
                text = lp.read_text(errors="replace")
                opened = time.monotonic() if needle.search(text) else None
                m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
                vbase = m.group(1) if m else vbase
        pid = None
        if opened is None or vbase is None:
            row["error"] = "level did not open"
        else:
            pid = json.loads((RUNS / run / "process.json").read_text(encoding="utf-8-sig"))["pid"]
            process, ray = Process(pid, int(vbase, 16)), None
            t_end = time.monotonic() + SECONDS - 45
            while ray is None and time.monotonic() < opened + 80 and process.running():   # Rayman may load late
                disc = work / "discovery.json"
                p = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), vbase, str(disc),
                                    "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
                for x in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if p.returncode == 0 else []):
                    try:
                        act = Actor(process, int(x["so"], 16))
                    except Exception:
                        continue
                    actors.append(act.model)
                    if act.model == RAY and ray is None:
                        ray = act
                row["discovery_t"] = round(time.monotonic() - opened, 2)
                if ray is None:
                    time.sleep(10)
            if ray is None:
                row["error"] = "rayman not found"
            else:
                while time.monotonic() < t_end and process.running():
                    try:
                        samples.append({"t": round(time.monotonic() - opened, 2), "pos": ray.position(),
                                        "beh": ray.comport()})
                    except Exception as x:
                        row["sampling_stopped"] = type(x).__name__
                        break
                    time.sleep(0.2)
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and h.alive(pid))
    row["actor_models"] = sorted(set(actors))
    (work / "samples.json").write_text(json.dumps(samples) + "\n")
    log = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / run).glob("runtime*.log")))
    row["haptics_policy"] = "M23 haptics policy=suppressed physical_pad_drivers=none" in log
    row["mods_off"] = "M33 mods=off" in log
    opens = re.findall(r"[\\/]([A-Za-z0-9_]+)\.lvl result=00000000", log)
    row["levels_opened"] = opens
    row["fault_lines"] = len(h.FAULT.findall(log))
    row["judges"] = {}
    for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        r = subprocess.run([sys.executable, str(TOOLS / t), "--run", run], cwd=ROOT, capture_output=True, text=True)
        row["judges"][t] = r.returncode
        (work / f"{t}.log").write_text(r.stdout + r.stderr)
    row["summary"] = h.summarize(samples)
    (work / "row.json").write_text(json.dumps(row, indent=1) + "\n")
    print(json.dumps({k: v for k, v in row.items() if k != "actor_models"}, indent=1))
    return 0


def ground(tag):
    import g6p12_collision_file_audit as g6
    s = json.loads((ROOT / "private" / "work" / PREFIX / tag / "row.json").read_text())["summary"]
    pt = s.get("settled") or (s.get("placed"))
    out = g6.audit(LEVEL, probe=pt)
    print(json.dumps({"point": pt, "meshes": out["meshes"], "triangles": out["triangles"],
                      "probe": out.get("probe")}, indent=1))
    return 0


def region(tag, zdr_file):
    """Offline: ownership chain, visual object, twins and the triangles under / around the settled point of one mesh."""
    import math
    import struct
    import m25_mesh_audit as m25
    import g6p12_collision_file_audit as g6
    s = json.loads((ROOT / "private" / "work" / PREFIX / tag / "row.json").read_text())["summary"]
    px, py, pz = s["settled"]
    L = m25.Level(LEVEL)
    z = zdr_file - 4
    m = g6.parse_mesh(L, z)
    refs = L.by_value.get(z, [])                 # fields (m25 coordinates) that point at the mesh
    cs = refs[0] - 0xC if len(refs) == 1 else None   # collide set +0xC -> zdr
    pos_ = L.by_value.get(cs, []) if cs is not None else []   # PO +4 -> collide set
    po = pos_[0] - 4 if len(pos_) == 1 else None   # validated on intro_15: PO 0x15C44 -> object 0x15C74
    vs = L.ptr(po) if po is not None else None
    vo = L.ptr(L.ptr(vs + 0xC)) if vs is not None else None
    out = {"settled": s["settled"], "zdr": hex(zdr_file), "nv": m["nv"], "tris": sum(e["nt"] for e in m["elems"]),
           "collide_set": hex(cs + 4) if cs is not None else None, "po": hex(po + 4) if po is not None else None,
           "visual_set": hex(vs + 4) if vs is not None else None, "visual_object": hex(vo + 4) if vo is not None else None}
    if vo is None:
        print(json.dumps(out, indent=1))
        return 1
    nvv, nev = struct.unpack_from(">HH", L.b, vo + 4 + 0x24)
    vp = L.ptr(vo)
    vverts = [struct.unpack_from(">3f", L.b, vp + 4 + 12 * k) for k in range(nvv)]
    out["visual_vertices"], out["visual_elements"] = nvv, nev
    # triangles of the collision mesh under the point and their neighbourhood (vertices within 6 units in x, y)
    near = [k for k, v in enumerate(m["verts"]) if math.hypot(v[0] - px, v[1] - py) < 6.0 and abs(v[2] - pz) < 2.0]
    twins = {}
    for k in near:
        c = [q for q, w in enumerate(vverts) if math.dist(w, m["verts"][k]) <= 0.001]
        twins[k] = c
    under = []
    for ei, e in enumerate(m["elems"]):
        for j in range(e["nt"]):
            a, b, c = (m["verts"][q] for q in e["idx"][3 * j:3 * j + 3])
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / d
            l2 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / d
            if min(l1, l2, 1 - l1 - l2) >= -1e-6:
                n = rm._face(a, b, c)
                under.append({"tri": [ei, j], "idx": e["idx"][3 * j:3 * j + 3], "z": round(l1 * a[2] + l2 * b[2] + (1 - l1 - l2) * c[2], 4),
                              "nz": round(n[2], 4) if n else None})
    out["under"] = under
    out["near_vertices"] = {k: {"pos": [round(x, 3) for x in m["verts"][k]], "twins": twins[k]} for k in near}
    print(json.dumps(out, indent=1))
    return 0


# ================================================================================================ preset, offline, run
PRESET, ZDR, VOBJ = "start-two-step-v1", 0x4B3F0, 0xBA80
SETTLED_L1 = (-66.63662719726562, -64.2138671875, -25.077850341796875)   # probe l1 (E-508), spread 0
FAIRY = rm.FAIRY20
GATE = {rm.STRUCT_ENV: LEVEL}
IPO_BOX, BOX_COPY = 0x939BC, 0x215D6C   # file offsets: IPO +0x38 box (24 bytes) and its unowned copy
EXE = ROOT / "private/work/rex/out/build/win-amd64-release/r3hd.exe"
RUN_DOC = """PROSPECTIVE RUNTIME PROTOCOL (committed before the modified run; thresholds are not changed after results)
Modified run V: one hidden run `e508_<tag>_v_trace` (the M22 rule needs `*_trace`), same runner, entry
(--test-level intro_20), 230 s, disposable profile and license mask as probe l1, plus R3HD_M22_DRAW_TRACE=1 and the
plan of preset start-two-step-v1 (development gate only in the compiler, never in the game process). Steps: frame a at
120 s, frame b at 140 s (2 explicit readbacks, cap 8), no input. Observed: Rayman's position and behaviour every 0.2 s;
every preset range read back at discovery and at the last sample (guest base by the six fairy-light SuperObjects, as
the intro_15 bridges).
Baseline for P4 (stated here explicitly): retained probe l1 (same executable SHA-256 required, same entry and timing,
no plan, no trace): Rayman stands at (-66.637, -64.214, -25.0779), spread 0, from 3.5 s; surface under him h_orig.
Criteria (judged separately):
  P1 delivery: the run serves exactly its plan's ranges (50; set of (file, offset, length)).
  P2 guest geometry: every preset range reads as the plan's new bytes at both reads.
  P3 GPU draw: in both frames, for every visual element with an edited triangle, a draw is found whose corner positions
     equal that element's MODIFIED file geometry in element order (de-indexed, any stride 24-48), and its corners that use
     the edited visual vertices differ from the original geometry.
  P4 playable physics (h_mod / h_orig = plane of collision triangle 1/11 under the settled x, y; gap = l1 z - h_orig):
     (a) settled z (summary window) within 0.02 of h_mod + gap, spread <= 0.02, x / y within 0.05 of l1's;
     (b) settled z - l1 settled z <= -0.10 (distinguished from the baseline; expected -0.189);
     (c) no sample below h_mod - 0.10; last behaviour YAM_C_Attente; sampling to the end.
  P5 framebuffer attribution, the frozen G6-P16b rule (g6p16b_framebuffer.compare, unchanged) - EVALUABILITY GATE
     first, from V's own frames and camera only (no colours): an edited visual triangle is countable if >= 5 of its
     samples are valid under V's camera (inside the frame, >= 2 px from its edges, outside the Rayman box) and
     discriminative (original vs modified projections >= 2 px apart). If fewer than 8 edited triangles are countable in
     either frame, P5 = NOT EVALUABLE (edit too small for the method); no reference runs are made. Otherwise two traced
     reference runs R1, R2 (no plan, same schedule) are made and the rule is applied as in G6-P16b (both labels, both
     references; R2-vs-R1 control must REJECT); classes as there.
  P6 safety: M21 / M22 / M23 = 0, haptics policy line, runner exit 0, no process left, only fix / transit / intro_20
     opened, no fault line, gameplay line (achievements not awarded).
Classes: P1-P6 PASS -> VERIFIED. P1-P4 and P6 PASS with P5 not passing or NOT EVALUABLE -> PARTIAL (geometry and physics
verified, render unverified). P2 / P3 FAIL or a P4 (a) / (c) failure -> EXPERIMENT FAILED. Invalid (the run may be
repeated once, unchanged): level not opened, Rayman / fairies not found, a traced frame missing.
"""


def files():
    d = h.GAME / "GAMEDATAbin" / LEVEL
    return (d / f"{LEVEL}.lvl").read_bytes(), (d / f"{LEVEL}.ptr").read_bytes()


def edits(lvl=None, ptr=None, spec=None, check_files=True):
    if lvl is None:
        lvl, ptr = files()
    return rm.collision_edit(lvl, ptr, LEVEL, spec or rm.COLLISION_ALLOW[LEVEL]["presets"][PRESET], PRESET, check_files)


def level(img):
    import m25_mesh_audit as m25
    L = m25.Level(LEVEL)
    L.b = img
    return L


def mesh(img):
    import g6p12_collision_file_audit as g6
    L = level(img)
    return L, g6.parse_mesh(L, ZDR - 4)


def visual(img):
    """{element: (corner bytes in element order, index triples)} of the visual object, all elements."""
    import struct
    L = level(img)
    go = VOBJ - 4
    vp, ep = L.ptr(go), L.ptr(go + 0x14)
    ne = struct.unpack_from(">H", img, VOBJ + 0x26)[0]
    out = {}
    for k in range(ne):
        el = L.ptr(ep + 4 * k)
        nt = struct.unpack_from(">H", img, el + 8)[0]
        idx = struct.unpack_from(f">{3 * nt}H", img, L.ptr(el + 0xC) + 4)
        out[k] = ([img[vp + 4 + 12 * j:vp + 16 + 12 * j] for j in idx], idx)
    return out


def op(**kw):
    lvl, _ = files()
    return {"type": "collision-vertex-offset", "level": LEVEL, "preset": PRESET, "lvl_sha256": rm.sha256_bytes(lvl), **kw}


def octree_cover(L2, new, m2):
    import struct
    tris = [(ei, j) for ei, e in enumerate(m2["elems"]) for j in range(e["nt"])]
    tp = {t: [m2["verts"][q] for q in m2["elems"][t[0]]["idx"][3 * t[1]:3 * t[1] + 3]] for t in tris}
    root = L2.ptr(L2.ptr(ZDR - 4 + 0x14))
    stack, cover, leaves = [root], set(), 0   # cover: (leaf, triangle) pairs intersecting but not listed
    while stack:
        nd = stack.pop()
        kids, lst = L2.ptr(nd + 0x18), L2.ptr(nd + 0x1C)
        if kids is not None:
            stack += [L2.ptr(kids + 4 * q) for q in range(8) if L2.ptr(kids + 4 * q) is not None]
            continue
        leaves += 1
        lo, hi = L2.f32s(nd, 3), L2.f32s(nd + 12, 3)
        items = set()
        if lst is not None:
            cnt, p = struct.unpack_from("<H", new, lst + 4)[0], lst + 6
            for _ in range(cnt):
                el, x = new[p], new[p + 1]
                tr, p = (((x & 0x7F) << 8) | new[p + 2], p + 3) if x & 0x80 else (x, p + 2)
                items.add((el, tr))
        cover |= {(nd + 4, t) for t in tris if t not in items and rm._tri_box(tp[t], lo, hi)}
    return cover, leaves, root


def corrupt_leaf(lvl):
    """A copy whose first octree leaf listing element 1 triangle 11 (the spawn triangle) names triangle 10 instead."""
    import struct
    L = level(lvl)
    stack = [L.ptr(L.ptr(ZDR - 4 + 0x14))]
    while stack:
        nd = stack.pop()
        kids, lst = L.ptr(nd + 0x18), L.ptr(nd + 0x1C)
        if kids is not None:
            stack += [L.ptr(kids + 4 * q) for q in range(8) if L.ptr(kids + 4 * q) is not None]
            continue
        if lst is None:
            continue
        cnt, p = struct.unpack_from("<H", lvl, lst + 4)[0], lst + 6
        for _ in range(cnt):
            el, x = lvl[p], lvl[p + 1]
            tr, w = ((((x & 0x7F) << 8) | lvl[p + 2]), 3) if x & 0x80 else (x, 2)
            if (el, tr) == (1, 11) and w == 2:
                b = bytearray(lvl)
                b[p + 1] = 10
                return bytes(b)
            p += w
    raise SystemExit("no leaf lists element 1 triangle 11")


def check():
    import copy
    import math
    import os
    import struct
    import tempfile
    import m25_mesh_audit as m25
    import g6p16_multi_surface as p16
    import g6p17_terrain as p17
    res, (lvl, ptr) = {}, files()
    allow = rm.COLLISION_ALLOW[LEVEL]
    spec = allow["presets"][PRESET]
    eds = edits()
    L, m0 = mesh(lvl)
    new = h.apply(lvl, eds)
    L2, m2 = mesh(new)
    moved = {k: g["dz"] for g in spec["groups"] for k in g["vertices"]}
    twin = {c: v for v, (_, c) in spec["visual"]["map"].items()}
    # O1 source identity and ownership
    refs = L.by_value.get(ZDR - 4, [])
    cs = refs[0] - 0xC if len(refs) == 1 else None
    pos_ = L.by_value.get(cs, [])
    po = pos_[0] - 4 if len(pos_) == 1 else None
    data = L.by_value.get(po, []) if po is not None else []
    sos = L.by_value.get(data[0], []) if len(data) == 1 else []
    so = sos[0] - 4 if len(sos) == 1 else None
    vobj = L.ptr(L.ptr(L.ptr(po) + 0xC)) + 4 if po is not None else None
    w, _ = m25.so_matrix(L, so) if so is not None else (None, None)
    ident = w is not None and all(abs(w[r][c] - (1.0 if r == c else 0.0)) < 1e-6 for r in range(4) for c in range(4))
    vp = L.ptr(VOBJ - 4) + 4
    vo = m0["vo"] + 4
    twin_d = {c: math.dist(struct.unpack_from(">3f", lvl, vp + 12 * v), m0["verts"][c]) for c, v in twin.items()}
    under = p16.surface(m0, *SETTLED_L1[:2])
    o1 = {"hashes": (len(lvl), rm.sha256_bytes(lvl)) == allow["lvl"] and (len(ptr), rm.sha256_bytes(ptr)) == allow["ptr"],
          "same files as the intro_20 structural allow-list": allow["lvl"] == rm.STRUCT_ALLOW[LEVEL]["lvl"]
          and allow["ptr"] == rm.STRUCT_ALLOW[LEVEL]["ptr"],
          "mesh referenced once / collide set / PO / IPO unique": so is not None and L.u32(so) == 0x20,
          "PO": hex(po + 4) if po is not None else None, "IPO SuperObject": hex(so + 4) if so is not None else None,
          "under a sector": __import__("g6p12_collision_file_audit").sector_of(L, so) is not None,
          "identity world transform": ident, "visual object from PO": hex(vobj) if vobj else None,
          "collision originals": all(lvl[vo + 12 * k:vo + 12 * k + 12].hex() == wv for g in spec["groups"]
                                     for k, wv in g["vertices"].items()),
          "visual originals": all(lvl[vp + 12 * v:vp + 12 * v + 12].hex() == wv for v, (wv, _) in spec["visual"]["map"].items()),
          "twin distance max": max(twin_d.values()),
          "settled point over": [(t, round(z, 4)) for t, z, _ in under], "rayman above surface": round(SETTLED_L1[2] - under[0][1], 4)
          if under else None}
    o1["ok"] = (o1["hashes"] and o1["same files as the intro_20 structural allow-list"]
                and o1["mesh referenced once / collide set / PO / IPO unique"] and o1["under a sector"] and ident
                and vobj == VOBJ and o1["collision originals"] and o1["visual originals"] and max(twin_d.values()) < 0.001
                and len(under) == 1 and under[0][0] == (1, 11) and 0 <= SETTLED_L1[2] - under[0][1] < 0.02)
    res["O1 source identity and ownership"] = o1
    # O2 deformation integrity
    fe, ee, se, classes, excess = h.integrity(L2, new, m2)
    fe0, ee0, se0, classes0, excess0 = h.integrity(L, lvl, m0)
    cover, leaves, root = octree_cover(L2, new, m2)
    cover0, _, _ = octree_cover(L, lvl, m0)   # E-508: the original already has one such pair (1e-4 model); none new
    dzs = {k: round(m2["verts"][k][2] - m0["verts"][k][2], 5) for k in range(m2["nv"]) if m2["verts"][k] != m0["verts"][k]}
    boxes = {"octree root": (L.f32s(root, 3), L.f32s(root + 12, 3)),
             "IPO +0x38": (struct.unpack_from(">3f", lvl, IPO_BOX), struct.unpack_from(">3f", lvl, IPO_BOX + 12)),
             "IPO +0x34": (struct.unpack_from(">3f", lvl, IPO_BOX - 24), struct.unpack_from(">3f", lvl, IPO_BOX - 12)),
             "copy 0x215D6C": (struct.unpack_from(">3f", lvl, BOX_COPY), struct.unpack_from(">3f", lvl, BOX_COPY + 12))}
    margins = {n: round(min(min(m2["verts"][k][i] - lo[i], hi[i] - m2["verts"][k][i]) for k in dzs for i in range(3)), 4)
               for n, (lo, hi) in boxes.items()}
    margins_z = {n: round(min(m2["verts"][k][2] - lo[2] for k in dzs), 4) for n, (lo, hi) in boxes.items()}
    ring = {(ei, j) for ei, e in enumerate(m0["elems"]) for j in range(e["nt"]) if set(moved) & set(e["idx"][3 * j:3 * j + 3])}
    tp = lambda m, t: [m["verts"][q] for q in m["elems"][t[0]]["idx"][3 * t[1]:3 * t[1] + 3]]   # noqa: E731
    nz = {t: (rm._face(*tp(m0, t))[2], rm._face(*tp(m2, t))[2]) for t in ring}
    ground_ok = all(b >= 0.9 for a, b in nz.values() if a >= 0.9) and all(a * b > 0 for a, b in nz.values())
    agree = max(math.dist(struct.unpack_from(">3f", new, vp + 12 * twin[c]), m2["verts"][c]) for c in moved)
    V0, V1 = visual(lvl), visual(new)
    ed_vis = set(twin.values())
    vring = [(k, t) for k, (_, idx) in V0.items() for t in range(len(idx) // 3) if set(idx[3 * t:3 * t + 3]) & ed_vis]
    fn_err = 0.0
    for k, t in vring:
        el = L2.ptr(L2.ptr(VOBJ - 4 + 0x14) + 4 * k)
        pts = [struct.unpack(">3f", c) for c in V1[k][0][3 * t:3 * t + 3]]
        fn_err = max(fn_err, math.dist(rm._face(*pts), struct.unpack_from(">3f", new, L2.ptr(el + 0x14) + 4 + 12 * t)))
    amb = p17.ambiguous_scalars(L, L2, lvl, m0)
    amb_ok = all(x["coplanar_orig"] and x["new"][0] == 1.0 and x["rule_gap"] <= 1e-3 for x in amb)
    # visual / collision divergence over the edited visual triangles (vertical, collision plane under each sample)
    div = []
    for img_v, m_ in ((V0, m0), (V1, m2)):
        worst = 0.0
        for k, t in vring:
            pts = [struct.unpack(">3f", c) for c in img_v[k][0][3 * t:3 * t + 3]]
            for lb in ((1 / 3, 1 / 3, 1 / 3), (0.6, 0.2, 0.2), (0.2, 0.6, 0.2), (0.2, 0.2, 0.6)):
                p = [sum(lb[i] * pts[i][c] for i in range(3)) for c in range(3)]
                s_ = [z for _, z, _ in p16.surface(m_, p[0], p[1]) if abs(z - p[2]) < 1.0]
                if s_:
                    worst = max(worst, min(abs(z - p[2]) for z in s_))
        div.append(round(worst, 4))
    h0, h1 = p16.surface(m0, *SETTLED_L1[:2]), p16.surface(m2, *SETTLED_L1[:2])
    o2 = {"moved": dzs, "face_err": fe, "edge_err": ee, "scalar_one_err": se, "classes": classes, "classes_original": classes0,
          "sphere_excess": excess, "octree_leaves": leaves, "octree_unlisted_pairs_orig": sorted(cover0), "octree_unlisted_pairs_mod": sorted(cover),
          "octree_no_new_unlisted": cover <= cover0, "bound_margins": margins, "bound_margins_z_below": margins_z,
          "collision_ring": len(ring), "visual_ring": len(vring), "ring_normal_z_min": round(min(b for _, b in nz.values()), 4),
          "ground_ok": ground_ok, "visual_on_collision_max": agree, "visual_face_err": fn_err,
          "ambiguous_edge_scalars": amb, "visual_collision_divergence_orig_mod": div,
          "spawn_surface": {"orig": round(h0[0][1], 4), "mod": round(h1[0][1], 4), "dz": round(h1[0][1] - h0[0][1], 4)},
          "expected_settled_z": round(h1[0][1] + (SETTLED_L1[2] - h0[0][1]), 4)}
    o2["ok"] = (all(abs(dzs.get(k, 0) - d) < 1e-5 for k, d in moved.items()) and sorted(dzs) == sorted(moved)
                and fe <= max(fe0, 2.5e-5) and ee < 2e-6 and se < 2e-6 and excess <= max(excess0, 0)
                and classes["one"] == classes0["one"] and classes["other"] == classes0["other"] and amb_ok and cover <= cover0
                and not {t for _, t in cover} & ring and min(margins.values()) > 0 and min(margins_z.values()) > 0.05
                and ground_ok and agree < 0.001 and fn_err < 1e-6 and len(ring) == len(vring) and div[1] <= div[0] + 0.30)
    res["O2 deformation integrity"] = o2
    # O3 compiler integrity
    diff = [i for i in range(len(lvl)) if lvl[i] != new[i]]
    kinds = {}
    for _, _, w_ in eds:
        key = ("visual " if w_.startswith("visual") else "") + ("edge " if " edge " in w_ else "") + w_.split()[-1]
        kinds[key] = kinds.get(key, 0) + 1
    o3 = {"ranges": len(eds), "bytes": sum(len(d) for _, d, _ in eds), "kinds": kinds, "differing_bytes": len(diff),
          "deterministic": edits() == eds, "same size": len(new) == len(lvl),
          "every difference inside a range": all(any(o <= i < o + len(d) for o, d, _ in eds) for i in diff),
          "no octree / box words": not any("octree" in w_ or "box" in w_ for _, _, w_ in eds),
          "non-overlapping, ordered": all(a[0] + len(a[1]) <= b[0] for a, b in zip(eds, eds[1:])),
          "no relocated word written": not any(any((o + q) in L.slots for q in range(-4, len(d))) for o, d, _ in eds)}
    o3["ok"] = all(v for v in o3.values() if isinstance(v, bool)) and kinds.get("z") == 3 and kinds.get("visual z") == 3
    res["O3 compiler integrity"] = o3

    # O4 refusal safety
    def refused(fn, code="TARGET_CHANGED", text=None):
        try:
            fn()
        except rm.Refusal as x:
            return x.code == code and (text is None or text in x.detail)
        return False

    def mut(*ed):
        b = bytearray(lvl)
        for o, d in ed:
            b[o:o + len(d)] = d
        return bytes(b)

    def sp(f):
        s = copy.deepcopy(spec)
        f(s)
        return s
    # pairing: a fully twinned edited visual triangle; move one of its unmoved corners onto another collision vertex
    pair_case = None
    for k, t in vring:
        idx = V0[k][1][3 * t:3 * t + 3]
        others = [q for q in idx if q not in ed_vis]
        if others:
            pair_case = (others[0], m0["verts"][3])
            break
    neg = {
        "wrong file hash": refused(lambda: edits(mut((0x100, b"\xAA")), ptr)),
        "collision original changed": refused(lambda: edits(mut((vo + 12 * 0 + 8, b"\xc1\xc9\x80\x09")), ptr, check_files=False),
                                              text="not the original value"),
        "visual original changed": refused(lambda: edits(mut((vp + 12 * 131 + 8, b"\xc1\xc9\x80\x09")), ptr, check_files=False),
                                           text="not the original value"),
        "second visual vertex on a moved collision vertex (crack)": refused(lambda: edits(
            mut((vp + 12 * 133, lvl[vp + 12 * 131:vp + 12 * 131 + 12])), ptr, check_files=False), text="would crack"),
        "visual corner moved onto another collision vertex (pairing)": pair_case is not None and refused(lambda: edits(
            mut((vp + 12 * pair_case[0], struct.pack(">3f", *pair_case[1]))), ptr, check_files=False), text="pairs with no"),
        "unsafe bounds (IPO +0x38 box and its copy: min z above the edit)": refused(lambda: edits(
            mut((IPO_BOX + 8, struct.pack(">f", -25.3)), (BOX_COPY + 8, struct.pack(">f", -25.3))), ptr, check_files=False),
            text="would leave the IPO +0x38 box"),
        "corrupted octree leaf": refused(lambda: edits(corrupt_leaf(lvl), ptr, check_files=False), text="octree leaf"),
        "vertex 9 moved (too steep, triangle 1/189)": refused(lambda: edits(lvl, ptr, sp(lambda s: s["groups"][1]["vertices"].update(
            {9: "c27727d5c2844a75c1c98008"})), False), text="too steep"),
        "displacement outside the group guard (-0.35)": refused(lambda: edits(lvl, ptr, sp(lambda s: s["groups"][0].update(dz=-0.35)), False)),
        "visual map incomplete": refused(lambda: edits(lvl, ptr, sp(lambda s: s["visual"]["map"].pop(196)), False)),
        "deterministic": edits() == eds,
    }
    os.environ[rm.STRUCT_ENV] = LEVEL
    try:
        neg["unknown preset"] = refused(lambda: rm.parse_collision_vertex_offset(op(preset=PRESET + "x"), "o"), "UNSUPPORTED")
        neg["raw groups key in the manifest"] = refused(lambda: rm.parse_collision_vertex_offset(op(groups=[]), "o"), "BAD_MANIFEST")
        neg["two terrain edits in one mod (intro_20 + intro_15 presets)"] = refused(lambda: rm.parse_manifest({"mod.json": json.dumps(
            h.manifest("t.two", op(), h.op("spawn-multi-surface-v1"))).encode()}), "BAD_MANIFEST")
        lt = {"type": "insert-fairy-on-graph", "level": "intro_20", "model": FAIRY, "instance": 2, "lvl_sha256": "0" * 64,
              "ptr_sha256": "0" * 64, "transit_sha256": "0" * 64, "follow_graph_of": 0}
        neg["terrain + intro_20 FairyLight insertion in one mod refused (D-274); each alone parses"] = (
            rm.parse_insert_fairy_on_graph(dict(lt), "o") is None
            and refused(lambda: rm.parse_manifest({"mod.json": json.dumps(h.manifest("t.mix", op(), lt)).encode()}),
                        "BAD_MANIFEST"))
        os.environ[rm.STRUCT_ENV] = "intro_15"
        neg["gate naming another level: compile refused"] = refused(lambda: rm.compile_collision_vertex_offset(op(), {"game": h.GAME}),
                                                                    "UNSUPPORTED")
    finally:
        os.environ.pop(rm.STRUCT_ENV, None)
    neg["gate off: parse refused"] = refused(lambda: rm.parse_collision_vertex_offset(op(), "o"), "UNSUPPORTED")
    with tempfile.TemporaryDirectory(dir=ROOT / "private" / "work") as td:
        imps, pl = h.make_plan(Path(td) / "c", [h.manifest("e508.a", op()), h.manifest("e508.b", op())], env_extra=GATE)
        neg["conflicting second mod refused whole"] = [a_ if isinstance(a_, str) else a_.get("id") for a_ in pl.get("active", [])] == ["e508.a"]
        imps, pl = h.make_plan(Path(td) / "d", [h.manifest("e508.n", op())], env_extra={})
        neg["gate-off import refused"] = imps[0].get("result") != "ok"
    res["O4 refusal safety"] = {"cases": neg, "ok": all(neg.values())}
    # O5 regression and policy
    o5 = {"gameplay-affecting": rm.changes_game_logic({"overrides": [op()]})}
    with tempfile.TemporaryDirectory(dir=ROOT / "private" / "work") as td:
        imps, pl = h.make_plan(Path(td) / "a", [h.manifest("e508.v", op())], env_extra=GATE)
        o5["plan ok"] = pl.get("result") == "ok" and bool(pl.get("plan"))
        if o5["plan ok"]:
            text = Path(pl["plan"]).read_text(encoding="utf-8")
            recs = sorted((int(r[2]), int(r[3]), r[5]) for r in (ln.split() for ln in text.splitlines() if ln.startswith("range ")))
            o5["plan records = compiled preset"] = recs == sorted((o, len(d), f"{rm.fnv1a64(d):016x}") for o, d, _ in eds)
            o5["plan gameplay record"] = "\ngameplay e508.v\n" in text
            o5["no level-tx / grow records"] = "level-tx" not in text and "\ngrow " not in text
    r17 = subprocess.run([sys.executable, "-I", str(HERE / "g6p17_terrain.py"), "check"], cwd=ROOT, capture_output=True, text=True)
    o5["G6-P17 check (intro_15 presets, shallow-bowl, retained plans) exit 0"] = r17.returncode == 0
    o5["ok"] = all(v for v in o5.values() if isinstance(v, bool))
    res["O5 regression and policy"] = o5
    verdict = {k: v["ok"] for k, v in res.items()}
    print(json.dumps(verdict, indent=1))
    out = ROOT / "private" / "work" / PREFIX
    out.mkdir(parents=True, exist_ok=True)
    (out / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    return 0 if all(verdict.values()) else 1


STEPS = "wait 120\nframe a\nwait 20\nframe b\nwait 82\n"


def hidden_run(tag, case, with_plan):
    """V (with_plan) or a reference R1 / R2 (no plan): the probe runner plus plan, draw trace, frames and readbacks."""
    import os
    from m5_live import Actor, Process
    l1 = json.loads((RUNS / f"{PREFIX}_l1_probe" / "run.json").read_text(encoding="utf-8-sig"))["executable_sha256"]
    if rm.sha256_bytes(EXE.read_bytes()) != l1:
        raise SystemExit("the executable differs from probe l1's")
    eds = edits()
    work = ROOT / "private" / "work" / PREFIX / tag / case
    run = f"{PREFIX}_{tag}_{case}_trace"
    if work.exists() or (RUNS / run).exists():
        raise SystemExit(f"exists: {work} or {RUNS / run}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    env.pop("R3HD_MODS_PLAN", None)
    env.pop(rm.STRUCT_ENV, None)
    env["R3HD_M22_DRAW_TRACE"] = "1"
    row = {"case": case, "run": run}
    if with_plan:
        imps, pl = h.make_plan(work, [h.manifest(f"{PREFIX}.{case}", op())], env_extra=GATE)
        if pl.get("result") != "ok" or not pl.get("plan"):
            raise SystemExit(f"plan: {imps} {pl}")
        env["R3HD_MODS_PLAN"] = row["plan"] = pl["plan"]
        row["plan_ranges"] = h.plan_ranges(pl["plan"])[1]
    (work / "steps.txt").write_text(STEPS, encoding="ascii")
    ix = rm.read_script_index(h.GAME, LEVEL)
    fairy_so = [i["so"] for i in ix["placements"][FAIRY]]
    samples, reads = [], {}
    with (work / "driver.log").open("w") as log:
        game = subprocess.Popen([sys.executable, str(TOOLS / "m9_license_run.py"), run, str(work / "steps.txt"),
                                 "--license-mask", "1", "--seconds", str(SECONDS), "--play", "--test-level", LEVEL,
                                 "--user-root", run], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        needle = re.compile(rf"[\\/]{LEVEL}\.lvl result=00000000", re.IGNORECASE)
        opened, vbase, end = None, None, time.monotonic() + 90
        while time.monotonic() < end and game.poll() is None and opened is None:
            time.sleep(0.5)
            lp = RUNS / run / "runtime.log"
            if lp.is_file():
                text = lp.read_text(errors="replace")
                opened = time.monotonic() if needle.search(text) else None
                m = re.search(r"virtual base 0x0*([0-9A-Fa-f]+),", text)
                vbase = m.group(1) if m else vbase
        pid = None
        if opened is None or vbase is None:
            row["error"] = "level did not open"
        else:
            pid = json.loads((RUNS / run / "process.json").read_text(encoding="utf-8-sig"))["pid"]
            disc = work / "discovery.json"
            p = subprocess.run([sys.executable, str(TOOLS / "m5_memory_probe.py"), str(pid), vbase, str(disc),
                                "--regions"], cwd=ROOT, capture_output=True, text=True, timeout=180)
            process, ray, fairies = Process(pid, int(vbase, 16)), None, []
            for x in (json.loads(disc.read_text(encoding="utf-8"))["actors"] if p.returncode == 0 else []):
                try:
                    act = Actor(process, int(x["so"], 16))
                except Exception:
                    continue
                if act.model == RAY and ray is None:
                    ray = act
                elif act.model == "NIN_m_FairyLight":
                    fairies.append(act)
            cands = {}
            for f in fairies:
                for s_ in fairy_so:
                    cands.setdefault(f.so - s_ + 4, set()).add(f.so)
            gbase = max(cands, key=lambda k: len(cands[k])) if cands else None
            row["guest_base"] = hex(gbase) if gbase else None
            row["base_votes"] = len(cands[gbase]) if gbase else 0
            row["discovery_t"] = round(time.monotonic() - opened, 2)
            if ray is None or gbase is None:
                row["error"] = "rayman or fairies not found"
            else:
                reads["first"] = [r.hex() if r else None for r in h.readback(process, gbase, eds)]
                t_end = time.monotonic() + SECONDS - 45
                while time.monotonic() < t_end and process.running():
                    try:
                        samples.append({"t": round(time.monotonic() - opened, 2), "pos": ray.position(),
                                        "beh": ray.comport()})
                    except Exception as x:
                        row["sampling_stopped"] = type(x).__name__
                        break
                    time.sleep(0.2)
                if process.running():
                    reads["last"] = [r.hex() if r else None for r in h.readback(process, gbase, eds)]
        game.wait(timeout=SECONDS + 240)
        row["runner_exit"] = game.returncode
        row["process_left"] = bool(pid and h.alive(pid))
    row["reads"] = reads
    (work / "samples.json").write_text(json.dumps(samples) + "\n")
    (work / "row.json").write_text(json.dumps(row, indent=1) + "\n")
    print(json.dumps({k: v for k, v in row.items() if k not in ("reads", "plan_ranges")}, indent=1))
    return 0


def frames(run, img):
    """[(label, {element: 4x4 camera}, pixels)] for the run's traced frames, matching every element's corner positions."""
    import m22_draw_report as rep
    want = visual(img)
    out = []
    for name, draws, bmp in h._frames(run):
        cams = {}
        for el, (corners, _) in want.items():
            n = len(corners)
            for d in draws:
                b = d["bindings"][0] if d["bindings"] else None
                if not b or b["size"] % n or not 24 <= b["size"] // n <= 48:
                    continue
                st = b["size"] // n
                if all(b["data"][i * st:i * st + 12] == corners[i] for i in range(n)):
                    c = d["consts"]
                    cams[el] = [[rep.f32(c[r_ * 4 + j]) for j in range(4)] for r_ in range(4)]
                    break
        out.append((name, cams, h._pixels(bmp)[2] if Path(bmp).is_file() else None))
    return out


def judge(tag):
    import math
    import struct
    import g6p16_multi_surface as p16
    import g6p16b_framebuffer as fb
    lvl, _ = files()
    eds = edits()
    newimg = h.apply(lvl, eds)
    spec = rm.COLLISION_ALLOW[LEVEL]["presets"][PRESET]
    ed_vis = set(spec["visual"]["map"])
    work = ROOT / "private" / "work" / PREFIX / tag / "v"
    run = f"{PREFIX}_{tag}_v_trace"
    row = json.loads((work / "row.json").read_text())
    log = "\n".join(p.read_text(errors="replace") for p in sorted((RUNS / run).glob("runtime*.log")))
    served = sorted({(f.lower(), int(o), int(n)) for _, f, o, n in
                     re.findall(r"M33 mods served mod=(\S+) file=(\S+) offset=(\d+) length=(\d+)", log)})
    opens = re.findall(r"[\\/]([A-Za-z0-9_]+)\.lvl result=00000000", log)
    judges = {}
    for t in ("m21_regression.py", "m22_regression.py", "m23_haptics_regression.py"):
        r = subprocess.run([sys.executable, str(TOOLS / t), "--run", run], cwd=ROOT, capture_output=True, text=True)
        judges[t] = r.returncode
        (work / f"{t}.log").write_text(r.stdout + r.stderr)
    s = json.loads((work / "samples.json").read_text())
    summ = h.summarize(s)
    l1 = json.loads((ROOT / "private" / "work" / PREFIX / "l1" / "row.json").read_text())["summary"]
    exe_v = json.loads((RUNS / run / "run.json").read_text(encoding="utf-8-sig"))["executable_sha256"]
    exe_l1 = json.loads((RUNS / f"{PREFIX}_l1_probe" / "run.json").read_text(encoding="utf-8-sig"))["executable_sha256"]
    _, m0 = mesh(lvl)
    _, m2 = mesh(newimg)
    invalid = []
    if "error" in row or not s:
        invalid.append(row.get("error", "no samples"))
    st = summ.get("settled")
    P = {}
    P["P1 delivery"] = served == sorted((f, o, n) for f, o, n in row.get("plan_ranges", [])) and len(served) == len(eds)
    newh = [d.hex() for _, d, _ in eds]
    P["P2 guest geometry"] = bool(row["reads"].get("first") and row["reads"].get("last")) and all(
        row["reads"][w] == newh for w in ("first", "last"))
    fr = frames(run, newimg)
    fr_orig = frames(run, lvl)
    V0, V1 = visual(lvl), visual(newimg)
    affected = sorted({k for k, (_, idx) in V0.items() if set(idx) & ed_vis})
    if len(fr) < 2:
        invalid.append("a traced frame missing")
    p3 = {name: {el: el in cams for el in affected} for name, cams, _ in fr}
    p3_orig_match = {name: [el for el in affected if el in cams] for name, cams, _ in fr_orig}
    diff_ok = all(any(V0[el][0][i] != V1[el][0][i] for i in range(len(V0[el][0]))) for el in affected)
    P["P3 GPU draw"] = len(fr) >= 2 and all(all(v.values()) for v in p3.values()) and diff_ok \
        and not any(p3_orig_match.values())
    h0, h1 = p16.surface(m0, *SETTLED_L1[:2]), p16.surface(m2, *SETTLED_L1[:2])
    gap = SETTLED_L1[2] - h0[0][1]
    want = h1[0][1] + gap
    p4 = {"settled": st, "expected_z": round(want, 4), "l1_settled": l1.get("settled"),
          "same executable as l1": exe_v == exe_l1, "spread": summ.get("settled_spread"), "min_z": summ.get("min_z"),
          "last_behaviour": s[-1]["beh"] if s else None}
    # judge defect fixed after the first call (E-508): `spread or 9` turned a measured spread of 0.0 into 9; threshold unchanged
    p4["a"] = bool(st) and abs(st[2] - want) <= 0.02 and summ.get("settled_spread") is not None \
        and summ["settled_spread"] <= 0.02 and \
        math.dist(st[:2], SETTLED_L1[:2]) <= 0.05 * math.sqrt(2) and exe_v == exe_l1
    p4["b"] = bool(st) and st[2] - SETTLED_L1[2] <= -0.10
    p4["c"] = bool(s) and min(x["pos"][2] for x in s) >= h1[0][1] - 0.10 and s[-1]["beh"] == "YAM_C_Attente" \
        and "sampling_stopped" not in row
    p4["dz_vs_l1"] = round(st[2] - SETTLED_L1[2], 4) if st else None
    P["P4 playable physics"] = p4["a"] and p4["b"] and p4["c"]
    # P5 evaluability gate (V's own camera, no colours)
    ray = st or SETTLED_L1
    S_ = fb.samples()
    gate = {}
    for name, cams, _ in fr:
        countable = 0
        for el in affected:
            if el not in cams:
                continue
            m_ = cams[el]
            pts = [fb.project(m_, (ray[0] + dx, ray[1] + dy, ray[2] + dz), 1280, 720) for dx in (-0.8, 0.8)
                   for dy in (-0.8, 0.8) for dz in (0.0, 2.5)]
            pts = [p for p in pts if p]
            box = (min(p[0] for p in pts) - 4, min(p[1] for p in pts) - 4, max(p[0] for p in pts) + 4,
                   max(p[1] for p in pts) + 4) if pts else None
            idx = V0[el][1]
            for t in range(len(idx) // 3):
                if not set(idx[3 * t:3 * t + 3]) & ed_vis:
                    continue
                po = [struct.unpack(">3f", c) for c in V0[el][0][3 * t:3 * t + 3]]
                pm = [struct.unpack(">3f", c) for c in V1[el][0][3 * t:3 * t + 3]]
                sp0 = [fb.project(m_, v, 1280, 720) for v in po]
                spm = [fb.project(m_, v, 1280, 720) for v in pm]
                if any(x is None for x in sp0 + spm):
                    continue
                n = 0
                for lb in S_:
                    a, b = fb.project(m_, fb.bary(po, lb), 1280, 720), fb.project(m_, fb.bary(pm, lb), 1280, 720)
                    ok = all(q and 0 <= q[0] < 1280 and 0 <= q[1] < 720 for q in (a, b)) \
                        and fb.edge_dist(a, [x[:2] for x in sp0]) >= 2 and fb.edge_dist(b, [x[:2] for x in spm]) >= 2 \
                        and not (box and any(box[0] <= q[0] <= box[2] and box[1] <= q[1] <= box[3] for q in (a, b))) \
                        and math.hypot(a[0] - b[0], a[1] - b[1]) >= 2
                    n += ok
                countable += n >= 5
        gate[name] = countable
    p5_evaluable = len(gate) >= 2 and min(gate.values()) >= 8
    P["P5 framebuffer"] = "NOT EVALUABLE (edit too small for the method)" if not p5_evaluable else "REFERENCE RUNS REQUIRED"
    P["P6 safety"] = (all(v == 0 for v in judges.values()) and "M23 haptics policy=suppressed physical_pad_drivers=none" in log
                      and row.get("runner_exit") == 0 and not row.get("process_left")
                      and all(x.lower() in ("fix", "transit", LEVEL) for x in opens) and len(h.FAULT.findall(log)) == 0
                      and bool(re.search(r"M33 mods gameplay mod=\S+ achievements=not_awarded", log)))
    core = all(P[k] is True for k in ("P1 delivery", "P2 guest geometry", "P3 GPU draw", "P4 playable physics", "P6 safety"))
    if invalid:
        verdict = "INVALID"
    elif not (P["P2 guest geometry"] and P["P3 GPU draw"]) or not (p4["a"] and p4["c"]):
        verdict = "EXPERIMENT FAILED"
    elif core and not p5_evaluable:
        verdict = "PARTIAL - GEOMETRY AND PHYSICS VERIFIED, RENDER UNVERIFIED (P5 not evaluable)"
    elif core:
        verdict = "P1-P4, P6 PASS; P5 pending reference runs"
    else:
        verdict = "PARTIAL / see criteria"
    res = {"invalid": invalid, "P": P, "verdict": verdict, "p3": p3, "p3_original_geometry_matches": p3_orig_match,
           "affected_elements": affected, "p4": p4, "p5_gate_countable": gate, "summary": summ, "judges": judges,
           "served": len(served), "levels": opens, "guest_base": row.get("guest_base"), "base_votes": row.get("base_votes")}
    (work.parent / "judge.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] in ("probe", "ground"):
        sys.exit({"probe": probe, "ground": ground}[sys.argv[1]](sys.argv[2]))
    if len(sys.argv) == 4 and sys.argv[1] == "region":
        sys.exit(region(sys.argv[2], int(sys.argv[3], 16)))
    if sys.argv[1:] == ["check"]:
        sys.exit(check())
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        sys.exit(hidden_run(sys.argv[2], "v", True))
    if len(sys.argv) == 4 and sys.argv[1] == "ref" and sys.argv[3] in ("r1", "r2"):
        sys.exit(hidden_run(sys.argv[2], sys.argv[3], False))
    if len(sys.argv) == 3 and sys.argv[1] == "judge":
        sys.exit(judge(sys.argv[2]))
    print(__doc__)
    sys.exit(2)
