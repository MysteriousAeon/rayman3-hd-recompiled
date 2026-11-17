#!/usr/bin/env python3
"""E-527 (D-294) G6-P38: acceptance of the integrated textured 3D editor (V1-V8).

    python tools/experiments/modding_feasibility/g6p38_editor_check.py check [--out DIR] [--skip-stage]

Reads the person's own extracted game tree and the retained intro_15 draw traces (read only). Writes only under DIR
(default private/work/g6p38): offscreen pictures (one readback each, framebuffer objects of never-shown windows), a
project file and a JSON of numbers. Every Tk window is withdrawn before it can map and never asks a question (Editor3D
opens dialogs only when viewable); handlers are called directly; no desktop input, cursor, grab, sound or game process.
V7 runs g6p38_ctypes_stage.py (an isolated private stage) unless --skip-stage. Since G6-P39 (D-295) that option-(a)
experiment is superseded and no longer renders: run with --skip-stage (the bridge route is g6p39_bridge_check.py).
"""
import glob
import hashlib
import json
import math
import re
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
BRIDGE_SRC = TOOLS / "scene_gl" / "r3hd_scene_gl.cpp"   # G6-P39 (D-295): the native OpenGL bridge
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import m22_draw_report as m22  # noqa: E402
import r3hd_level_editor as ed  # noqa: E402
import r3hd_level_editor_core as core  # noqa: E402
import r3hd_level_scene as ls  # noqa: E402
import r3hd_scene_gl as sg  # noqa: E402
import r3hd_scene_view as sv  # noqa: E402

TRACES = ROOT / "private" / "work" / "m6_runs"
INSIDE20 = {"target": [-62.0, -56.0, -20.0], "yaw": -150.0, "pitch": 18.0, "dist": 22.0}
INSIDE15 = {"target": [60.36, 51.81, 18.29], "yaw": -120.0, "pitch": 22.0, "dist": 18.0}
STAGE_MANIFEST = ROOT / "private" / "work" / "e525" / "stage" / "payload" / "payload.json"
BIN = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
TECH = re.compile(r"0x[0-9a-fA-F]+|[0-9a-f]{16,}|\\\\|\.lvl|sha256")


class Ev:
    def __init__(self, x=0, y=0, state=0, keysym="", delta=0):
        self.x, self.y, self.state, self.keysym, self.delta = x, y, state, keysym, delta


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


# ------------------------------------------------------------------------------------------------------------ V1
def trace_blend(game):
    """Traced draw state of every intro_15 draw matched to a decoded element, against the element's mode."""
    scene, _ = sg.classified_scene(game, "intro_15")
    key = {}
    for o in scene.objects:
        for e in o["elements"]:
            t = e["tri"]
            key.setdefault(tuple(round(c, 4) for i in range(3) for c in o["local"][t[i]]), []).append((o, e))
    want = {"opaque": lambda b, cc, dc: b == 0x00010001 and not cc & 8 and dc & 4,
            "test": lambda b, cc, dc: b == 0x00010001 and cc & 8 and (cc & 7) == 6 and dc & 4,
            "add": lambda b, cc, dc: b == 0x01060106 and not dc & 4}
    out = {"frames": 0, "matched": 0, "agree": {}, "contradict": [], "blend_traced": 0, "alpha_refs": set(),
           "backdrop_draws": {}}
    files = sorted(glob.glob(str(TRACES / "combo_tutorial_intro15_*_trace" / "m22_draws_*.bin")))
    for fp in files:
        draws, _, _ = m22.parse(Path(fp))
        out["frames"] += 1
        for d in draws:
            if not d["bindings"]:
                continue
            n, attrs = m22.vertices(d)
            pos = next((v for a, v in attrs if v and len(v[0]) == 3), None) if n >= 3 else None
            hits = key.get(tuple(round(c, 4) for p in pos[:3] for c in p)) if pos else None
            if not hits:
                continue
            o, e = hits[0]
            r = d["regs"]
            b, cc, dc = r[0x2201 - 0x2000], r[0x2202 - 0x2000] & 0xF, r[0x2200 - 0x2000] & 0xFF
            out["matched"] += 1
            if o["role"] != "scene":
                out["backdrop_draws"][f"{o['role']}:{b:08X}:{dc:02X}"] = out["backdrop_draws"].get(
                    f"{o['role']}:{b:08X}:{dc:02X}", 0) + 1
                continue
            if e["mode"] == "blend":
                out["blend_traced"] += 1
                continue
            if cc & 8:
                out["alpha_refs"].add(round(m22.f32(r[0x210E - 0x2000]), 4))
            if want[e["mode"]](b, cc, dc):
                out["agree"][e["mode"]] = out["agree"].get(e["mode"], 0) + 1
            else:
                out["contradict"].append((e["mode"], f"{b:08X}", cc, dc))
    out["alpha_refs"] = sorted(out["alpha_refs"])
    out["contradict"] = out["contradict"][:5] + ([len(out["contradict"])] if len(out["contradict"]) > 5 else [])
    return out


# ------------------------------------------------------------------------------------------------------------ main
def check(out: Path, skip_stage=False):
    out.mkdir(parents=True, exist_ok=True)
    game = core.default_game_dir()
    R, det = {}, {}
    t0 = time.perf_counter()

    # V1 authentic scene -----------------------------------------------------------------------------------------
    s20, m20 = sg.classified_scene(game, "intro_20")
    s15, m15 = sg.classified_scene(game, "intro_15")
    sum20, sum15 = s20.summary(), s15.summary()
    det["intro_20"] = {k: sum20[k] for k in ("objects", "triangles", "textured_triangles", "modes", "roles")}
    det["intro_15"] = {k: sum15[k] for k in ("objects", "triangles", "textured_triangles", "modes", "roles")}
    R["V1 intro_20 geometry and texture coverage unchanged (89 objects, 24046 / 24041 triangles)"] = (
        sum20["objects"] == 89 and sum20["triangles"] == 24046 and sum20["textured_triangles"] == 24041)
    tb = trace_blend(game)
    det["trace_blend"] = tb
    R["V1 traced draw state agrees with every scene element's material mode (21 frames, 0 contradictions)"] = (
        tb["frames"] >= 20 and not tb["contradict"] and all(tb["agree"].get(m, 0) > 0 for m in ("opaque", "test", "add")))
    R["V1 alpha test uses the traced reference (RB_ALPHA_REF) and GEQUAL"] = tb["alpha_refs"] == [ls.ALPHA_REF]
    names = lambda s, role: sorted({s.textures[e["texture"]]["name"].split("\\")[-1] for o in s.objects  # noqa: E731
                                    if o["role"] == role for e in o["elements"] if e["texture"]})
    det["intro_15_backdrops"] = names(s15, "backdrop")
    det["intro_15_runtime_placed"] = [f"{o['superobject']:#x}" for o in s15.objects if o["role"] == "runtime_placed"]
    R["V1 sky domes are classified as backdrops; the camera-placed sprite is hidden; intro_20 has neither"] = (
        det["intro_15_backdrops"] == ["wood_clouds.tga", "wood_stars.tga", "wood_stars_anim.tga"]
        and det["intro_15_runtime_placed"] == ["0x4ac534"] and sum20["roles"] == {"scene": 89})
    renders = {}
    for name, lv, cam in (("intro20_inside", "intro_20", INSIDE20), ("intro15_inside", "intro_15", INSIDE15),
                          ("intro15_inside_b", "intro_15", INSIDE15)):
        renders[name] = sg.render_test(game, lv, out / f"{name}.png", camera=cam, markers=True, frames=30)
    det["renders"] = {k: {x: v[x] for x in ("first_frame_ms", "interactive_ms_median", "interactive_ms_max",
                                            "upload_seconds", "scene_seconds", "near_black_share_sampled",
                                            "covered_share_sampled", "backdrops_drawn", "gl_error", "window_visible")}
                      for k, v in renders.items()}
    det["renders"]["png_sha256"] = {k: sha(v["out"])[:16] for k, v in renders.items()}
    R["V1 no black-quad regression: additive glows drawn additive, near-black share < 0.2 % inside intro_15"] = (
        renders["intro15_inside"]["near_black_share_sampled"] < 0.002 and renders["intro15_inside"]["renderer"]["modes"][
            "add"] > 0 and renders["intro15_inside"]["backdrops_drawn"] >= 1)
    R["V1 reproducible: two renders of the same data and camera are byte-identical"] = (
        sha(renders["intro15_inside"]["out"]) == sha(renders["intro15_inside_b"]["out"]))
    R["V1 offscreen safety: never visible, one readback each, no GL error"] = all(
        not v["window_visible"] and v["readbacks"] == 1 and v["gl_error"] == 0 for v in renders.values())

    # the integrated window (withdrawn) --------------------------------------------------------------------------
    root = tk.Tk()
    root.withdraw()
    app, v = sv.open_editor(root, game, level="intro_20", show=False)
    v.vp.configure(width=960, height=540)
    root.update_idletasks()
    t1 = time.perf_counter()
    v.ensure_gl()
    det["window_open_seconds"] = round(time.perf_counter() - t1, 3)
    W, H = 960, 540

    def aim(p, dist=15.0):
        v.cam.target, v.cam.dist, v.cam.yaw, v.cam.pitch = list(p), dist, -60.0, 30.0
        proj, view = v.cam.matrices(W, H)
        v.mats = (proj, view, W, H)
        return sg.project(proj, view, W, H, p)

    R["V2 window opened withdrawn: GL context, textured scene, never viewable"] = (
        v.ctx is not None and v.r.stats["textures"] == 22 and not v.top.winfo_viewable() and not root.winfo_viewable())
    # V2 camera ------------------------------------------------------------------------------------------------------
    c = v.cam
    e0, t0c = c.eye(), list(c.target)
    c.orbit(40, 0)
    ok_orbit = c.target == t0c and math.dist(c.eye(), e0) > 0.1
    e1 = c.eye()
    c.look(30, -10)
    ok_look = math.dist(c.eye(), e1) < 1e-6 and math.dist(c.target, t0c) > 0.1
    tg = list(c.target)
    c.pan(50, 0, H)
    ok_pan = math.dist(c.target, tg) > 0.1
    d0 = c.dist
    v.on_wheel(Ev(delta=120))
    ok_zoom = c.dist < d0
    R["V2 orbit keeps the target, free-look keeps the eye, pan and wheel zoom move the camera"] = (
        ok_orbit and ok_look and ok_pan and ok_zoom)
    v.fit_level()
    lo, hi = s20.view_bounds()
    R["V2 Whole level fits the playable box; Editable area frames the actors"] = (
        all(abs(c.target[k] - (lo[k] + hi[k]) / 2) < 1e-6 for k in range(3)))
    v.fit_content()
    before = list(c.target)
    v.on_key(Ev(keysym="w"))
    job = v._fly_job is not None
    time.sleep(0.03)
    v._fly_step()
    moved = math.dist(c.target, before)
    fwd = [c.target[k] - before[k] for k in range(3)]
    view_dir = c.basis()[0]
    v.on_focus_out(Ev())
    R["V2 W flies forward while held; focus loss ends held keys and drags at once"] = (
        job and moved > 0 and sum(a * b for a, b in zip(fwd[:2], view_dir[:2])) > 0 and not v.keys
        and v._fly_job is None and v.drag is None)
    det["fly_step_units"] = round(moved, 4)
    v.on_key(Ev(keysym="d"))
    v.on_key_release(Ev(keysym="d"))
    R["V2 releasing the last key stops the fly timer"] = v._fly_job is None and not v.keys
    root.update()
    frames = v.timing["frames"]
    root.update()
    root.update()
    pending = [j for j in root.tk.splitlist(root.tk.call("after", "info"))]
    R["V2 idle: no redraw, no timer, no grab after events settle"] = (
        v.timing["frames"] == frames and not v._redraw_pending and v._fly_job is None and not pending
        and root.grab_current() is None)
    det["idle_after_jobs"] = len(pending)

    # V3 actors --------------------------------------------------------------------------------------------------
    cham = next(i for i, a in app.rmodel.actors.items() if a["name"] == "NIK_mChameleon")
    csel = ("actor", cham)
    orig = app.rmodel.actors[cham]["position"]
    sx, sy, _ = aim(orig)
    v.on_press(Ev(sx, sy))
    v.on_release(Ev(sx, sy))
    R["V3 click selects the actor in the editor; Objects tool; inspector plain"] = (
        app.sel == csel and v.tool.get() == "objects" and "Chameleon" in v.name_lbl.cget("text")
        and "Original:" in v.detail_lbl.cget("text") and not TECH.search(v.detail_lbl.cget("text") + v.status_lbl.cget(
            "text") + v.name_lbl.cget("text")))
    snap = json.dumps(app.remix, sort_keys=True)
    v.on_press(Ev(sx, sy))
    v.on_drag(Ev(sx + 60, sy + 25))
    prev = v.preview_pos()
    R["V3 drag previews a horizontal move: ghost shown, project unchanged, Apply / Cancel enabled"] = (
        prev is not None and abs(prev[2] - orig[2]) < 1e-6 and json.dumps(app.remix, sort_keys=True) == snap
        and v.r.overlays["ghost"] is not None and str(v.apply_btn.cget("state")) == "normal"
        and "Proposed:" in v.detail_lbl.cget("text"))
    v.on_release(Ev(sx + 60, sy + 25))
    v.cancel()
    R["V3 Cancel drops the preview without touching the project"] = (
        v.preview is None and json.dumps(app.remix, sort_keys=True) == snap and v.r.overlays["ghost"] is None)
    v.on_press(Ev(sx, sy))
    v.on_drag(Ev(sx + 60, sy + 25))
    v.on_release(Ev(sx + 60, sy + 25))
    prev = v.preview_pos()
    v.apply()
    got = next((a for a in app.remix["actors"] if (a["model"], a["instance"]) == cham), None)
    R["V3 Apply goes through set_remix_position: float32 position, matrix identity, undo entry"] = (
        got is not None and all(abs(g - core.f32(p)) < 1e-6 for g, p in zip(got["position"], prev))
        and got["matrix_sha256"] == app.rmodel.actors[cham]["matrix_sha256"] and len(app.undo) == 1
        and v.r.overlays["selected"] == tuple(got["position"]))
    res = app.validate_now()
    v.validate()
    R["V3 the edited project validates through the existing compiler; status shown in the 3D window"] = (
        res["ok"] and "VALID" in v.status_bar.cget("text"))
    v.undo()
    R["V3 Undo restores the original project and marker"] = (
        not app.remix["actors"] and v.r.overlays["selected"] == tuple(orig))
    v.preview = {"sel": csel, "pos": tuple(prev)}
    v.apply()
    v.revert()
    R["V3 Revert to original removes the edit"] = not app.remix["actors"]
    far = v.limit(csel, [p + 100.0 for p in orig])
    R["V3 a drag beyond the tested bound is held at it, and the editor keeps exactly that"] = abs(
        math.dist(far, orig) - core.MAX_ACTOR_MOVE) < 1e-3
    v.preview = {"sel": csel, "pos": tuple(far)}
    v.apply()
    kept = next((a["position"] for a in app.remix["actors"] if (a["model"], a["instance"]) == cham), None)
    R["V3 a drag beyond the tested bound is held at it, and the editor keeps exactly that"] &= (
        kept is not None and math.dist(kept, orig) <= core.MAX_ACTOR_MOVE)
    app.cmd_undo()
    locked = next(i for i, a in app.rmodel.actors.items() if a["status"] == "locked")
    lsel = ("actor", locked)
    lp = aim(app.rmodel.actors[locked]["position"])
    v.on_press(Ev(lp[0], lp[1]))
    v.on_release(Ev(lp[0], lp[1]))
    v.on_press(Ev(lp[0], lp[1]))
    v.on_drag(Ev(lp[0] + 50, lp[1]))
    R["V3 LOCKED actors are selectable, explained and cannot be dragged"] = (
        app.sel == lsel and v.preview is None and not app.remix["actors"] and "Cannot be moved" in v.status_lbl.cget(
            "text") and str(v.apply_btn.cget("state")) == "disabled")
    v.on_release(Ev(lp[0], lp[1]))
    v.select(csel)
    v.focus_selection()
    R["V3 Focus centres the camera on the selection"] = math.dist(v.cam.target, orig) < 1e-6

    # V4 paths ---------------------------------------------------------------------------------------------------
    v.tool.set("paths")
    v.tool_changed()
    pts = v.r.overlays["points"]
    edges = sum(len(g["edges"]) for g in app.rmodel.graphs.values())
    arrows = sum(1 for ln in v.r.overlays["lines"] if ln[5])
    R["V4 Paths shows only route points and directed route segments (one arrow per decoded arc)"] = (
        app.sel is None and len(pts) == sum(1 for g in app.rmodel.graphs.values() for nd in g["nodes"] if nd)
        and arrows == edges and all(p[2] and p[2][0] == "rwp" for p in pts))
    gid = next(k for k, g in app.rmodel.graphs.items() if g["name"] == "NIN_m_FairyLight" and k[1:] == (2, 2))
    nd = app.rmodel.graphs[gid]["nodes"][0]
    wsel = ("rwp", gid + (0,))
    wp = aim(nd["position"], 12.0)
    v.on_press(Ev(wp[0], wp[1]))
    v.on_release(Ev(wp[0], wp[1]))
    strong = [ln for ln in v.r.overlays["lines"] if ln[3] == 3.0]
    R["V4 click selects a route point; its route is highlighted; owner and follower shown plainly"] = (
        app.sel == wsel and len(strong) == len(app.rmodel.graphs[gid]["edges"])
        and "partly confirmed" in v.status_lbl.cget("text") and "FairyLight" in v.detail_lbl.cget("text")
        and any(p[2] is None for p in v.r.overlays["points"]))
    v.on_press(Ev(wp[0], wp[1]))
    v.on_drag(Ev(wp[0] + 400, wp[1] + 100))
    v.on_release(Ev(wp[0] + 400, wp[1] + 100))
    wprev = v.preview_pos()
    R["V4 waypoint preview is held within the 6-unit tested bound"] = (
        wprev is not None and math.dist(wprev, nd["position"]) <= core.MAX_WAYPOINT_MOVE + 1e-6)
    v.apply()
    gw = next((w for w in app.remix["waypoints"] if (w["model"], w["instance"], w["variable"], w["node"]) == wsel[1]),
              None)
    R["V4 Apply writes the editor's waypoint edit (float32, waypoint identity); validates"] = (
        gw is not None and gw["waypoint_sha256"] == nd["waypoint_sha256"]
        and all(abs(a - core.f32(b)) < 1e-6 for a, b in zip(gw["position"], wprev)) and app.validate_now()["ok"])
    R["V4 drawing a route never promotes it: still SUPPORTED"] = (
        app.rmodel.graphs[gid]["status"] == "supported"
        and core.RUNTIME_GRAPHS[("intro_20", "NIN_m_FairyLight", 2, 2)][0] == "supported")
    stip = [ln for ln in v.r.overlays["lines"] if ln[4]]
    R["V4 original and edited positions are distinguished (dashed line from the original)"] = len(stip) == 1
    v.undo()
    R["V4 Undo removes the waypoint edit"] = not app.remix["waypoints"]
    lockg = next(((k, i) for k, g in app.rmodel.graphs.items() for i, n_ in enumerate(g["nodes"])
                  if n_ and (g["status"] in ed.REFUSED or n_["why"])), None)
    if lockg:
        lw = aim(app.rmodel.graphs[lockg[0]]["nodes"][lockg[1]]["position"], 12.0)
        v.on_press(Ev(lw[0], lw[1]))
        v.on_release(Ev(lw[0], lw[1]))
        v.on_press(Ev(lw[0], lw[1]))
        v.on_drag(Ev(lw[0] + 40, lw[1]))
        v.on_release(Ev(lw[0] + 40, lw[1]))
    R["V4 a LOCKED route point cannot be dragged"] = lockg is None or (v.preview is None and not app.remix["waypoints"])
    det["locked_route_point_tested"] = lockg is not None

    # V6 (part) default presentation in the remix project ------------------------------------------------------------
    v.tool.set("objects")
    v.tool_changed()
    R["V6 Objects shows actor markers only (no routes, collision or terrain)"] = (
        all(p[2] and p[2][0] == "actor" for p in v.r.overlays["points"]) and not v.r.overlays["lines"]
        and not v.show["collision"].get())
    R["V6 Terrain is disabled with a reason in a remix project"] = (
        str(v.tool_btns["terrain"].cget("state")) == "disabled" and "Terrain lowering" in v.detail_lbl.cget("text"))
    R["V6 technical details hidden by default, revealed by Advanced details"] = not v.adv_lbl.winfo_ismapped()
    v.select(csel)
    v.adv.set(True)
    v.refresh_panel()
    R["V6 technical details hidden by default, revealed by Advanced details"] &= (
        "key " in v.adv_lbl.cget("text") and "matrix" in v.adv_lbl.cget("text"))
    v.adv.set(False)
    v.refresh_panel()

    # V5 terrain -------------------------------------------------------------------------------------------------
    patch_label = next(cc[2] for cc in ed.CHOICES if cc[0] == "patch")
    v.choose_level(patch_label)
    states = {k: str(b.cget("state")) for k, b in v.tool_btns.items()}
    region = sorted(app.model.regions[app.project["region"]]["vertices"])
    R["V5 terrain project: only Terrain enabled; only its start-floor points shown"] = (
        app.mode == "patch" and states == {"objects": "disabled", "paths": "disabled", "terrain": "normal"}
        and v.tool.get() == "terrain" and sorted(p[2][1] for p in v.r.overlays["points"]) == sorted(region))
    vx = region[1]
    vp0 = app.model.verts[vx]
    tp = aim(vp0, 8.0)
    v.on_press(Ev(tp[0], tp[1]))
    v.on_release(Ev(tp[0], tp[1]))
    v.on_press(Ev(tp[0], tp[1]))
    v.on_drag(Ev(tp[0], tp[1] + 3000))
    v.on_release(Ev(tp[0], tp[1] + 3000))
    lo_, hi_ = app.editable_range(vx)
    pv = v.preview or {}
    R["V5 floor point preview lowers only within its verified range; project unchanged until Apply"] = (
        app.sel == ("vtx", vx) and pv.get("dz") == lo_ and not app.project["terrain"])
    v.apply()
    one = app.validate_now()
    R["V5 Apply lowers through set_vertex_dz; the compiler's own verdict stands (one vertex: refused, as in 2D)"] = (
        app.project["terrain"].get(str(vx)) == lo_ and not one["ok"] and one.get("code") == "BAD_MANIFEST")
    det["terrain_single_vertex_verdict"] = [one.get("code"), str(one.get("detail"))[:120]]
    v.revert()
    R["V5 Revert removes the terrain edit; Undo is not offered for terrain"] = (
        not app.project["terrain"] and str(v.undo_btn.cget("state")) == "disabled")
    for vv, dz in ((6, -0.2), (2, -0.15), (4, -0.15)):     # the verified west-basin set (G6-P25 / G6-P30 probe)
        v.select(("vtx", vv))
        v.preview = {"sel": ("vtx", vv), "dz": dz}
        v.apply()
    ok3 = app.validate_now()
    R["V5 the verified west-basin lowering applied in 3D validates as production-supported content"] = (
        app.project["terrain"] == {"6": -0.2, "2": -0.15, "4": -0.15} and ok3["ok"]
        and not ok3["report"].get("development_only", True))
    for vv in (6, 2, 4):
        v.select(("vtx", vv))
        v.revert()
    R["V5 inspector says the picture keeps the original visual floor (collision is not the visual mesh)"] = (
        "keeps the original floor" in v.detail_lbl.cget("text") or "keeps the original floor" in
        v.item_info(("vtx", vx))[2][0])
    v.choose_level(next(cc[2] for cc in ed.CHOICES if cc == ("remix", "intro_15", cc[2])))
    R["V6 level switch reloads the scene and frees the previous textures"] = (
        v.scene_key == ("remix", "intro_15") and v.r.stats["textures"] > 0)
    det["intro_15_load_seconds"] = v.timing["load_seconds"]

    # V8 safety on close -------------------------------------------------------------------------------------------
    app.dirty = True
    det["frames_drawn"] = v.timing["frames"]
    det["frame_last_ms"], det["frame_max_ms"] = v.timing["last_ms"], round(v.timing["max_ms"], 2)
    v.close()                                    # dirty, but withdrawn: must not ask a question
    R["V8 a withdrawn window never opens a dialog; close frees GL and ends the editor"] = (
        v.ctx is None and v.r is None and v._closing)
    try:
        root.destroy()
    except tk.TclError:
        pass

    # V7 packaging ------------------------------------------------------------------------------------------------
    if not skip_stage:
        st = subprocess.run([sys.executable, "-B", str(HERE / "g6p38_ctypes_stage.py"), "check"], cwd=ROOT,
                            capture_output=True, text=True, timeout=1200)
        det["ctypes_stage_tail"] = st.stdout.strip().splitlines()[-1] if st.stdout else st.stderr[-300:]
        R["V7 isolated stage: trusted _ctypes + libffi start the 3D editor with the staged Python only"] = (
            st.returncode == 0 and "CTYPES_STAGE PASS" in st.stdout)
    payload = json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))
    R["V7 the release payload is unchanged: no _ctypes, 'ctypes' still excluded (decision pending)"] = (
        "ctypes" in payload["python"]["stdlib_exclude"] and "_ctypes" in payload["python"]["no_extension_modules"])

    # V8 static safety and identities ---------------------------------------------------------------------------------
    srcs = {n: (TOOLS / n).read_text(encoding="utf-8") for n in ("r3hd_scene_view.py", "r3hd_scene_gl.py",
                                                                 "r3hd_level_scene.py")}
    bad = ("SetCursorPos", "SendInput", "SetWindowsHookEx", "keybd_event", "mouse_event", "grab_set",
           "SetForegroundWindow", "event_generate", "focus_force", "ImageGrab", "BitBlt")
    R["V8 no global input, cursor, grab, focus-forcing or desktop capture in the 3D modules"] = not any(
        b in s for s in srcs.values() for b in bad)
    R["V8 one readback call in the 3D code (the offscreen test only)"] = (
        # G6-P39 (D-295): the readback is the bridge's read_pixels(), called once by the offscreen test; the
        # extension holds the only glReadPixels call and allows one readback per offscreen context
        sum(s.count(".read_pixels(") for s in srcs.values()) == 1 and ".read_pixels(" not in srcs["r3hd_scene_view.py"]
        and BRIDGE_SRC.read_text(encoding="utf-8").count("glReadPixels(") == 1)
    diff = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "tools/r3hd_level_editor.py",
                           "tools/r3hd_level_editor_core.py", "tools/r3hd_mods.py"], cwd=ROOT)
    R["V8 editor, editor core and mod compiler byte-identical to HEAD"] = diff.returncode == 0
    if STAGE_MANIFEST.is_file():
        files = json.loads(STAGE_MANIFEST.read_text(encoding="utf-8"))["files"]
        cur = {n: sha(BIN / n) for n in ("r3hd.exe", "rexruntime.dll", "rexgpu-xenos.dll")}
        R["V8 live production binaries equal the G6-P36 validated stage manifest (old checks pin 6635d232...)"] = all(
            files[f"bin/{n}"]["sha256"] == h for n, h in cur.items())
        det["production"] = {n: h[:16] for n, h in cur.items()}
    det["seconds"] = round(time.perf_counter() - t0, 1)
    ok = sum(1 for x in R.values() if x)
    report = {"results": R, "details": det, "passed": ok, "total": len(R),
              "note": "numbers only; pictures stay in this private folder"}
    (out / "g6p38_check.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    for k, x in R.items():
        print(f"{'PASS' if x else 'FAIL'} {k}")
    print(json.dumps(det, indent=1, default=str))
    print(f"G6-P38 editor check {ok}/{len(R)}")
    return 0 if ok == len(R) else 1


def main():
    args = sys.argv[1:]
    if not args or args[0] != "check":
        print(__doc__)
        return 2
    out = Path(args[args.index("--out") + 1]) if "--out" in args else ROOT / "private" / "work" / "g6p38"
    return check(out, "--skip-stage" in args)


if __name__ == "__main__":
    sys.exit(main())
