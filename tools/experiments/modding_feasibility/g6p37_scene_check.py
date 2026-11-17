#!/usr/bin/env python3
"""G6-P37: checks of the textured scene foundation (T1-T5, T7 and the Gate D editor connection).

    python tools/experiments/modding_feasibility/g6p37_scene_check.py check [--out DIR]

Reads the person's own extracted game tree (read-only). Writes only under DIR (default private/work/g6p37): two
offscreen pictures (one readback each, drawn into a framebuffer object of a window that is never shown) and a JSON of
numbers. Tk roots and the 3D window are withdrawn before they can map; handlers are called directly; no desktop
input, no cursor, no game process. Output contains no geometry or pixels.
"""
import hashlib
import json
import math
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import r3hd_level_editor as ed  # noqa: E402
import r3hd_level_editor_core as core  # noqa: E402
import r3hd_level_scene as ls  # noqa: E402
import r3hd_scene_gl as sg  # noqa: E402
import r3hd_scene_view as sv  # noqa: E402

LEVEL = "intro_20"
# fix.lvl / fix.ptr identities as recorded in reports/post_release/ISSUE_2_FRENCH_LOCALIZATION_FEASIBILITY.md
FIX = {"fix_lvl": "f929551622ad62394367ae65f94cd942a6c8176dbe8d63aec73e8dfecac5d3e5",
       "fix_ptr": "d16441083dc29065ce1fb8cb18583fa73b9352a9e0c3c12964465779eafbb4db"}
INSIDE = {"target": [-62.0, -56.0, -20.0], "yaw": -150.0, "pitch": 18.0, "dist": 22.0}


class Ev:
    def __init__(self, x, y, state=0):
        self.x, self.y, self.state, self.delta = x, y, state, 0


def surface_test(scene, actors, use_world):
    """Actors with a visual surface between 1.0 below and 0.5 above them (2D grid over triangle boxes)."""
    cell, grid = 4.0, {}
    for o in scene.objects:
        V = o["vertices"] if use_world else o["local"]
        for e in o["elements"]:
            t = e["tri"]
            for j in range(e["triangles"]):
                tri = (V[t[3 * j]], V[t[3 * j + 1]], V[t[3 * j + 2]], not o["identity"])
                xs, ys = [p[0] for p in tri[:3]], [p[1] for p in tri[:3]]
                for gx in range(int(math.floor(min(xs) / cell)), int(math.floor(max(xs) / cell)) + 1):
                    for gy in range(int(math.floor(min(ys) / cell)), int(math.floor(max(ys) / cell)) + 1):
                        grid.setdefault((gx, gy), []).append(tri)
    near = on_ni = 0
    for p in actors:
        best = None
        for a, b, c, ni in grid.get((int(math.floor(p[0] / cell)), int(math.floor(p[1] / cell))), ()):
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[1] - c[1])) / d
            l2 = ((c[1] - a[1]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[1] - c[1])) / d
            if min(l1, l2, 1 - l1 - l2) < -1e-6:
                continue
            dz = p[2] - (l1 * a[2] + l2 * b[2] + (1 - l1 - l2) * c[2])
            if -0.5 <= dz <= 1.0 and (best is None or dz < best[0]):
                best = (dz, ni)
        if best:
            near += 1
            on_ni += best[1]
    return near, on_ni


TRACE_RUN = ROOT / "private" / "work" / "m6_runs" / "combo_tutorial_intro15_a_trace"   # E-501's retained trace


def trace_checks(game):
    """Against the retained intro_15 draw trace (E-501; no new run): draws whose first three corners equal a decoded
    visual element's local vertices; their UV corners, bound texture names (first 32 bytes, ambiguous heads counted
    apart) and shared view-projection constants c0..c3."""
    import struct
    import m22_draw_report as m22
    scene = ls.Scene(game, "intro_15")
    key = {}
    for o in scene.objects:
        for e in o["elements"]:
            t = e["tri"]
            key.setdefault(tuple(round(c, 4) for i in range(3) for c in o["local"][t[i]]), []).append((o, e))
    heads = {}
    for bhf in [game / "GAMEDATAbin" / "fix.bhf"] + sorted((game / "GAMEDATAbin" / "intro_15").glob("*.bhf")):
        b, data = bhf.read_bytes(), bhf.with_suffix(".btf").read_bytes()
        n, = struct.unpack_from(">I", b, 0)
        for i in range(n):
            o = 4 + i * 0x114
            s1, o1, s2, o2 = struct.unpack_from(">4I", b, o)
            name = b[o + 16:o + 0x114].split(b"\0")[0].decode("latin1").lower().rsplit(".", 1)[0]
            for size, off in ((s1, o1), (s2, o2)):
                if size:
                    heads.setdefault(data[off:off + 32], set()).add(name)
    out = {"frames": 0, "matched_draws": 0, "positions_equal": 0, "uv_equal": 0, "uv_differ": 0, "tex_agree": 0,
           "tex_ambiguous": 0, "tex_contradict": 0, "identity_draws": 0, "identity_vp_sets": [],
           "transformed_draws": 0}
    for fpath in sorted(TRACE_RUN.glob("m22_draws_*.bin"))[:3]:
        draws, _, _ = m22.parse(fpath)
        out["frames"] += 1
        vps = set()
        for d in draws:
            if not d["bindings"]:
                continue
            n, attrs = m22.vertices(d)
            pos = next((v for a, v in attrs if v and len(v[0]) == 3), None) if n >= 3 else None
            hits = key.get(tuple(round(c, 4) for p in pos[:3] for c in p)) if pos else None
            if not hits:
                continue
            o, e = hits[0]
            out["matched_draws"] += 1
            exp = [o["local"][e["tri"][i]] for i in range(min(len(pos), 3 * e["triangles"]))]
            out["positions_equal"] += all(abs(a - b) < 1e-5 for p, q in zip(pos, exp) for a, b in zip(p, q))
            uv = next((v for a, v in attrs if v and len(v[0]) == 2), None)
            if uv and e["uvt"]:
                eu = [(e["uv"][2 * e["uvt"][i]], e["uv"][2 * e["uvt"][i] + 1]) for i in range(min(len(uv), 3 * e["triangles"]))]
                ok = all(abs(a - b) < 1e-6 for p, q in zip(uv, eu) for a, b in zip(p, q))
                out["uv_equal" if ok else "uv_differ"] += 1
            want = scene.textures[e["texture"]]["name"].lower().rsplit(".", 1)[0] if e["texture"] else None
            cands = [heads.get(t["head"][:32], set()) for t in d["textures"] if t["head"]]
            if want and any(want in c for c in cands):
                if any(c == {want} for c in cands):
                    out["tex_agree"] += 1
                else:
                    out["tex_ambiguous"] += 1
            else:
                out["tex_contradict"] += 1
            if all(x[0]["identity"] for x in hits):
                out["identity_draws"] += 1
                vps.add(tuple(d["consts"][:16]))
            else:
                out["transformed_draws"] += 1
        out["identity_vp_sets"].append(len(vps))
    return out


def check(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    game = core.default_game_dir()
    R, det = {}, {}
    t0 = time.perf_counter()
    scene = ls.Scene(game, LEVEL)
    det["scene_seconds"] = round(time.perf_counter() - t0, 3)
    pins = core.REMIX_LEVELS[LEVEL]
    R["T1 level lvl / ptr / transit equal the editor's pins"] = (
        scene.hashes["lvl"] == pins["lvl"] and scene.hashes["ptr"] == pins["ptr"]
        and scene.hashes["transit_lvl"] == pins["transit"])
    R["T1 fix.lvl / fix.ptr equal the recorded identities"] = all(scene.hashes[k] == v for k, v in FIX.items())
    s = scene.summary()
    det["summary"] = {k: s[k] for k in ("objects", "objects_non_identity", "elements", "triangles",
                                        "textured_triangles", "bounds", "skipped")}
    det["textures"] = [(t["name"], t["size"], t["format"], t["triangles"]) for t in s["textures"]]
    R["T2 visual objects decoded from the level's IPO visual sets (89 objects, 24046 triangles)"] = (
        s["objects"] == 89 and s["triangles"] == 24046)
    R["T2 every vertex index of every element is in range (enforced, none skipped)"] = not any(
        "index out of range" in k for k in s["skipped"])
    rows = ls.collision_agreement(scene)
    shared = sum(1 for r in rows if r["within_0.001"])
    det["collision_copies"] = {"objects_with_collision": len(rows), "objects_sharing_vertices": shared,
                               "max_shared_distance": max(r["max_shared"] for r in rows if r["max_shared"] is not None)}
    R["T2 visual and collision copies of one PhysicalObject share vertices (E-501 relation)"] = shared >= 20
    errors = []
    for key in scene.textures:
        try:
            scene.texture_entry(key)
        except ls.SceneError as x:
            errors.append(x.detail)
    det["texture_errors"] = errors
    R["T3 every layer-0 texture resolves to a bundle entry whose stored sizes match its record"] = not errors
    R["T3 textured share of triangles >= 99.9 %"] = s["textured_triangles"] >= 0.999 * s["triangles"]
    model = core.RemixModel(game, LEVEL)
    pos = [a["position"] for a in model.actors.values()]
    w_near, w_ni = surface_test(scene, pos, True)
    i_near, i_ni = surface_test(scene, pos, False)
    det["actor_surface"] = {"actors": len(pos), "world_near": w_near, "world_on_transformed": w_ni,
                            "identity_near": i_near, "identity_on_transformed": i_ni}
    R["T4 more actors rest on visual surfaces with world matrices than without"] = w_near > i_near and w_ni > i_ni
    if TRACE_RUN.is_dir():
        tr = trace_checks(game)
        det["trace_intro15"] = tr
        R["T2 (trace) traced world draws equal decoded visual elements corner for corner"] = (
            tr["matched_draws"] >= 60 and tr["positions_equal"] == tr["matched_draws"])
        R["T3 (trace) UV corners equal the element's UV triples"] = tr["uv_equal"] >= 60 and tr["uv_differ"] == 0
        R["T3 (trace) bound texture = the element's layer-0 texture (no contradiction)"] = (
            tr["tex_agree"] >= 50 and tr["tex_contradict"] == 0)
        R["T4 (trace) every identity-object draw of a frame shares one view-projection (world = file coordinates)"] = (
            tr["identity_draws"] >= 40 and all(n == 1 for n in tr["identity_vp_sets"]))
    else:
        det["trace_intro15"] = f"missing {TRACE_RUN} (optional retained evidence)"
    # T5 / T7: two independent offscreen renders of the same camera -> identical pictures
    shots = []
    for k in (1, 2):
        res = sg.render_test(game, LEVEL, out / f"inside_{k}.png", camera=INSIDE, markers=True)
        shots.append(res)
    hashes = [hashlib.sha256(Path(r["out"]).read_bytes()).hexdigest() for r in shots]
    det["render"] = {k: shots[0][k] for k in ("gl", "size", "renderer", "upload_seconds", "first_frame_ms",
                                               "covered_share_sampled", "distinct_colours_sampled", "gl_error")}
    det["render"]["png_sha256"] = hashes
    R["T5 two renders of the same data and camera are byte-identical"] = hashes[0] == hashes[1]
    R["T7 offscreen: window never visible, one readback per render, no GL error"] = all(
        not r["window_visible"] and r["readbacks"] == 1 and r["gl_error"] == 0 for r in shots)
    R["T7 the interactive modules never read pixels back"] = all(
        "glReadPixels(" not in (TOOLS / n).read_text(encoding="utf-8") for n in ("r3hd_scene_view.py",)) and (
        (TOOLS / "r3hd_scene_gl.py").read_text(encoding="utf-8").count(".read_pixels(") == 1   # G6-P39 bridge
        and (TOOLS / "scene_gl" / "r3hd_scene_gl.cpp").read_text(encoding="utf-8").count("glReadPixels(") == 1)
    R["T7 no global input or cursor APIs in the 3D modules"] = not any(
        bad in (TOOLS / n).read_text(encoding="utf-8") for n in ("r3hd_scene_view.py", "r3hd_scene_gl.py")
        for bad in ("SetCursorPos", "SendInput", "SetWindowsHookEx", "keybd_event", "mouse_event", "grab_set_global",
                    "SetForegroundWindow"))
    # Gate D: the 3D window on an unchanged editor (withdrawn), handlers called directly. G6-P38 (E-527) ported these
    # assertions unchanged in meaning to the integrated window `r3hd_scene_view.Editor3D` (open_editor, show=False).
    root = tk.Tk()
    root.withdraw()
    app, view = sv.open_editor(root, game, level=LEVEL, show=False)
    view.vp.configure(width=960, height=540)
    root.update_idletasks()
    view.ensure_gl()
    R["D GL context on the (withdrawn) view, textures uploaded"] = view.ctx is not None and view.r.stats["textures"] == 22
    det["view_gl"] = view.ctx.info if view.ctx else None
    R["D the 3D window was never viewable"] = not view.top.winfo_viewable() and not root.winfo_viewable()
    R["D one marker per editor actor"] = len([q for q in view.r.overlays["points"] if q[2]]) == len(model.actors)
    cham = next(i for i, a in app.rmodel.actors.items() if a["name"] == "NIK_mChameleon")
    csel = ("actor", cham)
    view.cam.target, view.cam.dist, view.cam.yaw, view.cam.pitch = list(app.rmodel.actors[cham]["position"]), 15.0, -60, 30
    w, h = 960, 540
    proj, viewm = view.cam.matrices(w, h)
    view.mats = (proj, viewm, w, h)
    sx, sy, _ = sg.project(proj, viewm, w, h, app.rmodel.actors[cham]["position"])
    R["D picking a marker at its screen position finds that actor"] = view.pick(sx + 3, sy - 2) == csel
    view.on_press(Ev(sx, sy))
    view.on_release(Ev(sx, sy))
    R["D a click selects the actor in the editor (its own inspector)"] = app.sel == csel
    R["D the 3D inspector speaks plainly (no key, hash or address by default)"] = (
        "Chameleon" in view.name_lbl.cget("text") and "Tested in game" in view.status_lbl.cget("text")
        and "\\" not in view.status_lbl.cget("text") and not view.adv_lbl.winfo_ismapped())
    before = json.dumps(app.remix, sort_keys=True)
    view.on_press(Ev(sx, sy))
    view.on_drag(Ev(sx + 60, sy + 25))
    prev = view.preview_pos()
    R["D dragging the selected marker previews a horizontal move without changing the project"] = (
        prev is not None and abs(prev[2] - app.rmodel.actors[cham]["position"][2]) < 1e-6
        and json.dumps(app.remix, sort_keys=True) == before and str(view.apply_btn.cget("state")) == "normal")
    view.on_release(Ev(sx + 60, sy + 25))
    view.apply()
    got = next((a for a in app.remix["actors"] if (a["model"], a["instance"]) == cham), None)
    R["D Apply moves the actor through the editor's validated path (float32, undoable)"] = (
        got is not None and all(abs(g - core.f32(p)) < 1e-6 for g, p in zip(got["position"], prev))
        and len(app.undo) >= 1 and view.r.overlays["selected"] == tuple(got["position"]))
    det["moved"] = {"by": round(math.dist(got["position"], app.rmodel.actors[cham]["position"]), 3) if got else None}
    pre = json.dumps(app.remix, sort_keys=True)
    res = core.validate_remix(app.remix, game)
    det["validate_ok"] = res["ok"]
    R["D the moved project validates through the existing compiler path"] = res["ok"]
    app.cmd_undo()
    R["D editor Undo reverts it and the 3D markers follow"] = (
        not app.remix["actors"] and view.r.overlays["selected"] == tuple(app.rmodel.actors[cham]["position"])
        and json.dumps(app.remix, sort_keys=True) != pre)
    far = view.limit(csel, [p + 100.0 for p in app.rmodel.actors[cham]["position"]])
    R["D a drag beyond the tested bound is shown at the bound the editor keeps"] = abs(
        math.dist(far, app.rmodel.actors[cham]["position"]) - core.MAX_ACTOR_MOVE) < 1e-4
    locked = next(i for i, a in app.rmodel.actors.items() if a["status"] == "locked")
    lsel = ("actor", locked)
    view.select(lsel)
    view.cam.target, view.cam.dist = list(view.selected_pos(lsel)), 15.0
    proj, viewm = view.cam.matrices(w, h)
    view.mats = (proj, viewm, w, h)
    lp = sg.project(proj, viewm, w, h, view.selected_pos(lsel))
    hit = view.pick(lp[0], lp[1]) if lp else None
    if lp:
        view.on_press(Ev(lp[0], lp[1]))
        view.on_drag(Ev(lp[0] + 50, lp[1]))
    R["D a locked object is pickable but cannot be dragged"] = (
        hit == lsel and app.sel == lsel and view.preview is None and not app.remix["actors"]
        and "cannot be moved" in view.msg.cget("text"))
    view.adv.set(True)
    view.refresh_panel()
    R["D Advanced details reveals the technical key"] = "key " in view.adv_lbl.cget("text")
    view.close(ask=False)
    det["seconds"] = round(time.perf_counter() - t0, 1)
    ok = sum(1 for v in R.values() if v)
    report = {"results": R, "details": det, "passed": ok, "total": len(R),
              "note": "numbers only; pictures stay in this private folder"}
    (out / "g6p37_check.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    for k, v in R.items():
        print(f"{'PASS' if v else 'FAIL'} {k}")
    print(json.dumps(det, indent=1, default=str))
    print(f"G6-P37 scene check {ok}/{len(R)}")
    return 0 if ok == len(R) else 1


def main():
    args = sys.argv[1:]
    if not args or args[0] != "check":
        print(__doc__)
        return 2
    out = Path(args[args.index("--out") + 1]) if "--out" in args else ROOT / "private" / "work" / "g6p37"
    return check(out)


if __name__ == "__main__":
    sys.exit(main())
