#!/usr/bin/env python3
"""E-518 (D-285) G6-P29: focused acceptance of the private visual level editor (tools/r3hd_level_editor.py).

    g6p29_editor_check.py check   E1 real spatial data, E2 interaction, E3 round-trip, E4 compiler parity + the
                                  end-to-end example, E5 refusal and safety
The GUI runs with its root window withdrawn (never shown); clicks and drags are delivered to the editor's own event
handlers. Outputs: private/work/e518/ (numbers only). No game process, build or gate change.
"""
import copy
import json
import os
import shutil
import struct
import subprocess
import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import r3hd_mods as rm  # noqa: E402
import r3hd_level_editor_core as core  # noqa: E402
import r3hd_level_editor as ed  # noqa: E402
import g6p28_fairy_route as g28  # noqa: E402

g24 = g28.g24
ROOT, GAME, LEVEL, EX = g28.ROOT, g28.GAME, g28.LEVEL, g28.EX
WORK = ROOT / "private" / "work" / "e518"
ROUTE_TX = "e44d20f9e0dd62cd"   # G6-P28 example (same images and mod id)


class Ev:
    def __init__(self, x, y):
        self.x, self.y = x, y


def app_new(game=GAME):
    root = tk.Tk()
    root.withdraw()
    a = ed.EditorApp(root, game)
    a.canvas_w, a.canvas_h = 1000, 760
    a.fit("supported")
    a.redraw()
    return root, a


def pick_xy(a, kind, ident):
    return next((sx, sy) for sx, sy, k, i, _ in a.picks if (k, i) == (kind, ident))


def gate(value):
    if value:
        os.environ[rm.STRUCT_ENV] = value
    else:
        os.environ.pop(rm.STRUCT_ENV, None)


def compiled(decl):
    with g28.p1.dev_env(LEVEL):
        return rm.compile_level_patch(decl, {"game": GAME})


def check():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    E, det = {}, {}
    lp, pp, _ = rm.script_level_files(GAME, LEVEL)
    lvl, ptr = lp.read_bytes(), pp.read_bytes()
    before = [rm.sha256_bytes(x.read_bytes()) for x in (lp, pp, lp.with_name("transit.lvl"))]
    gate(LEVEL)

    # E1 real spatial data
    e1 = {}
    root, a = app_new()
    m = a.model
    v, t = rm.collision_triangles(lvl, ptr, LEVEL)
    e1["viewport mesh = compiler collision_triangles (432 vertices / 768 triangles)"] = (
        m.verts == v and m.tris == t and len(v) == 432 and len(t) == 768)
    wps = g28.walk_graph_c(lvl)
    e1["graph C = independent walk (6 waypoints)"] = m.route == [struct.unpack_from(">3f", lvl, w) for _, w in wps]
    e1["editable vertices = the region allow-lists (v1 0 2 4; v2 0 2 4 6)"] = (
        list(m.regions["start-floor-v1"]["vertices"]) == [0, 2, 4]
        and list(m.regions["start-floor-v2"]["vertices"]) == [0, 2, 4, 6])
    e1["drawn pick positions = projected decoded coordinates"] = all(
        abs(sx - a.proj(m.verts[i] if k == "vtx" else m.route[i])[0]) < 1e-6
        and abs(sy - a.proj(m.verts[i] if k == "vtx" else m.route[i])[1]) < 1e-6
        for sx, sy, k, i, _ in a.picks if k in ("vtx", "wp"))
    e1["canvas holds triangles, editable vertices and the six graph C waypoints"] = (
        len(a.canvas.find_all()) > 500 and sum(1 for p in a.picks if p[2] == "wp") == 6
        and sorted(p[3] for p in a.picks if p[2] == "vtx" and p[4]) == [0, 2, 4, 6])
    a.set_vertex_dz(6, -0.2)
    a.set_vertex_dz(2, -0.15)
    a.set_waypoint_offset(3, (0, -5, 3))
    canon, ranges, tx = compiled(core.declaration(a.project))
    v2, _ = rm.collision_triangles(tx["images"]["lvl"][:len(lvl)], ptr, LEVEL)
    shown = m.edited_verts({int(k): d for k, d in a.project["terrain"].items()})
    e1["displayed edited vertices = the compiled image's collision vertices (exact)"] = shown == v2
    w3 = wps[3][1]
    e1["displayed edited waypoint = the compiled image's waypoint (exact)"] = (
        m.edited_route({3: [0.0, -5.0, 3.0]})[3] == struct.unpack_from(">3f", tx["images"]["lvl"], w3))
    root.destroy()
    root, b = app_new(WORK / "no_game")
    e1["no game data: explicit unsupported state, nothing pickable, no fabricated map"] = (
        b.model is None and b.picks == [] and any("No map" in b.canvas.itemcget(i, "text")
                                                  for i in b.canvas.find_all() if b.canvas.type(i) == "text"))
    root.destroy()
    E["E1"] = e1

    # E2 interaction (clicks / drags into the editor's own handlers)
    e2 = {}
    root, a = app_new()
    x, y = pick_xy(a, "vtx", 6)
    a.on_press(Ev(x + 2, y + 1))
    a.on_release(Ev(x, y))
    e2["click selects editable vertex 6; inspector shows range 0.05-0.20 and triangles 1/2 1/3 1/4"] = (
        a.sel == ("vtx", 6) and "lower 0.05 to 0.20" in a.sel_lbl.cget("text")
        and "1/2 1/3 1/4" in a.sel_lbl.cget("text"))
    a._on_dz(-0.17)
    e2["slider lowers vertex 6 (0.01 steps); proposed z shown"] = (
        a.project["terrain"] == {"6": -0.17} and "proposed z" in a.sel_lbl.cget("text"))
    a._on_dz(-0.30)
    e2["slider clamps vertex 6 to its verified -0.20"] = a.project["terrain"]["6"] == -0.2
    a.nudge_dz(0.01)
    e2["nudge raises the lowering by 0.01 within range"] = a.project["terrain"]["6"] == -0.19
    nonedit = next(p for p in a.picks if p[2] == "vtx" and not p[4])
    a.on_press(Ev(nonedit[0], nonedit[1]))
    ok = a.set_vertex_dz(nonedit[3], -0.1)
    e2["a non-editable vertex selects as NOT EDITABLE and cannot be changed"] = (
        a.sel == ("vtx", nonedit[3]) and "NOT EDITABLE" in a.sel_lbl.cget("text") and ok is False
        and str(nonedit[3]) not in a.project["terrain"])
    x, y = pick_xy(a, "wp", 3)
    a.on_press(Ev(x, y))
    a.on_motion(Ev(x + 3 * a.scale, y))
    a.on_release(Ev(x + 3 * a.scale, y))
    e2["dragging waypoint C3 in the top view moves it +3 in X"] = (
        a.sel == ("wp", 3) and abs(a.project["route"]["3"][0] - 3.0) < 0.01 and abs(a.project["route"]["3"][1]) < 0.01)
    a.on_press(Ev(*pick_xy(a, "wp", 3)))
    xx, yy = pick_xy(a, "wp", 3)
    a.on_motion(Ev(xx + 40 * a.scale, yy))
    off = a.project["route"]["3"]
    e2["a drag beyond 6 units is limited to 6 units"] = abs(sum(v * v for v in off) ** 0.5 - 6.0) < 0.01
    a.on_release(Ev(0, 0))
    for var, val in zip(a.off_vars, ("1", "-2", "0.5")):
        var.set(val)
    a.apply_offset_entries()
    e2["X/Y/Z offset entries set the waypoint offset"] = a.project["route"]["3"] == [1.0, -2.0, 0.5]
    a.revert_selected()
    e2["revert removes the waypoint edit"] = "3" not in a.project["route"]
    a.select(("vtx", 6))
    a.revert_selected()
    e2["revert removes the vertex edit"] = "6" not in a.project["terrain"]
    a.set_vertex_dz(6, -0.1)
    a.set_vertex_dz(0, -0.1)
    a.set_region("start-floor-v1")
    e2["switching to start-floor-v1 drops vertex 6 (not editable there) and keeps vertex 0"] = (
        a.project["terrain"] == {"0": -0.1} and a.project["region"] == "start-floor-v1")
    a.set_graph(1)
    e2["FairyLight graph B selectable; insertion control fixed on (required by the format)"] = (
        a.project["fairylight"] == {"follow_graph_of": 1} and a.fairy_on.get() is True)
    a.set_view("xz")
    a.set_exag(20)
    e2["side view with height exaggeration redraws; zoom and pan change the transform"] = a.view == "xz" and bool(
        a.picks)
    s0 = (a.scale, a.ox, a.oy)
    a.zoom(1.2, 500, 380)
    a._pan_start(Ev(100, 100))
    a._pan_move(Ev(130, 90))
    e2["zoom / pan"] = (a.scale, a.ox, a.oy) != s0
    e2["dirty state shown in the title"] = a.dirty and a.root.title().endswith("*")
    a.export_svg(WORK / "view_xz.svg")
    root.destroy()
    E["E2"] = e2

    # E3 round-trip
    e3 = {}
    root, a = app_new()
    a.set_vertex_dz(6, -0.2)
    a.set_vertex_dz(4, -0.12)
    a.set_waypoint_offset(0, (-4, -3, -2))
    a.set_waypoint_offset(5, (-3, 0, -4))
    a.set_graph(1)
    a.set_meta("id", "e518.roundtrip")
    a.set_meta("name", "Round trip")
    proj, decl = copy.deepcopy(a.project), core.declaration(a.project)
    f = WORK / "rt.r3hdmap.json"
    a.save_project(f)
    e3["save clears the dirty state; file is a small description (no game bytes)"] = (
        not a.dirty and f.stat().st_size < 2048 and set(json.loads(f.read_text())) == core.PROJECT_KEYS)
    root.destroy()
    root, b = app_new()
    b.open_project(f)
    e3["reopen: identical project and declaration, not dirty"] = (
        b.project == proj and core.declaration(b.project) == decl and not b.dirty)
    b.save_project(WORK / "rt2.r3hdmap.json")
    e3["re-save is byte-identical"] = (WORK / "rt2.r3hdmap.json").read_bytes() == f.read_bytes()
    b.restore_defaults()
    e3["restore defaults removes every edit"] = b.project["terrain"] == {} and b.project["route"] == {} and b.dirty
    left = [p for p in WORK.iterdir() if p.name.startswith(".rt")]
    e3["atomic save leaves no temporary file"] = not left
    root.destroy()
    E["E3"] = e3

    # E4 compiler parity + end-to-end example
    e4 = {}
    root, a = app_new()                                              # 1 open intro_20
    a.set_vertex_dz(6, -0.2)                                         # 2 lower vertex 6 (+ vertex 2: >= 2 groups)
    a.set_vertex_dz(2, -0.15)
    a.set_vertex_dz(4, -0.15)
    a.set_waypoint_offset(3, (0, -5, 3))                             # 3 move graph C waypoints
    a.set_waypoint_offset(0, (-4, -3, -2))
    a.set_waypoint_offset(5, (-3, 0, -4))
    a.set_graph(0)                                                   # 4 inserted FairyLight on graph A
    a.set_meta("id", "g6p28.fairy-route")
    res = a.validate_now()                                           # 5 validate
    e4["validate: VALID, the G6-P28 transaction e44d20f9e0dd62cd, 58 ranges, route evidence not runtime"] = (
        res["ok"] and res["report"]["transaction"]["id"] == ROUTE_TX and res["report"]["range_count"] == 58
        and "VALID" in a.status_var.get() and "UNTESTED" in a.report.get("1.0", "end"))
    pf = WORK / "e2e.r3hdmap.json"
    a.save_project(pf)                                               # 6 save
    root.destroy()
    root, b = app_new()
    b.open_project(pf)                                               # 7 reopen
    r1 = b.export_mod(WORK / "mod1")                                 # 8 export
    r2 = b.export_mod(WORK / "mod2")
    m1, m2 = (WORK / "mod1" / "mod.json"), (WORK / "mod2" / "mod.json")
    e4["export writes only mod.json; two exports byte-identical (deterministic)"] = (
        r1["ok"] and r2["ok"] and sorted(p.name for p in (WORK / "mod1").iterdir()) == ["mod.json"]
        and m1.read_bytes() == m2.read_bytes())
    e4["status says exported, NOT imported or enabled"] = "NOT imported or enabled" in b.status_var.get()
    root.destroy()
    dpath = WORK / "e2e_decl.json"
    core.export_declaration(core.load_project(pf), dpath)
    rc, out, _ = g24.cli(["level-patch", str(dpath), "--out", str(WORK / "mod_cli")], extra=("--json",))
    e4["= the CLI compiler on the exported declaration (mod.json byte-identical)"] = (
        rc == 0 and (WORK / "mod_cli" / "mod.json").read_bytes() == m1.read_bytes())
    cr, rr, tr = compiled(core.declaration(core.load_project(pf)))
    cx, rx, tx_ = compiled(g28.doc(EX / "g6p28_fairy_route.json"))
    e4["editor declaration = G6-P28 example: same ranges and guest images"] = (
        g28.sig(rr, tr)[1] == g28.sig(rx, tx_)[1]
        and [(o, rm.sha256_bytes(d)) for _, o, d, _ in rr] == [(o, rm.sha256_bytes(d)) for _, o, d, _ in rx])
    w = WORK / "walk"
    priv = ("--mods-root", str(w / "mods"), "--cache", str(w / "cache"))
    rc2, _, _ = g24.cli(["import", str(WORK / "mod1"), "--enable"], extra=("--json", *priv))
    rc3, _, _ = g24.cli(["plan"], extra=("--json", *priv))
    text = (w / "cache" / rm.PLAN_NAME).read_text(encoding="utf-8") if rc3 == 0 else ""
    mp = g28.p1.parse_plan(text) if text else None
    e4["exported mod imports and plans (private folders) as one re-derived level-tx"] = (
        rc2 == 0 and mp is not None and g28.tx_rederived(mp, "g6p28.fairy-route"))
    E["E4"] = e4

    # E5 refusal and safety
    e5 = {}
    base = json.loads(pf.read_text())
    bad = {
        "unknown top-level key": dict(base, extra=1),
        "unsupported version": dict(base, format="r3hd-level-editor-project-v2"),
        "other level": dict(base, level="intro_15"),
        "wrong target hash": dict(base, target=dict(base["target"], lvl_sha256="0" * 64)),
        "non-editable vertex 9": dict(base, terrain={"9": -0.1}),
        "vertex 6 below -0.20": dict(base, terrain={"6": -0.25, "2": -0.1}),
        "raising": dict(base, terrain={"0": 0.1, "2": -0.1}),
        "vertex 6 in start-floor-v1": dict(base, region="start-floor-v1"),
        "route move 7 units": dict(base, route={"1": [7, 0, 0]}),
        "route node 6": dict(base, route={"6": [1, 0, 0]}),
        "unknown meta key": dict(base, meta=dict(base["meta"], author="x")),
        "bad mod id": dict(base, meta=dict(base["meta"], id="Bad Id")),
    }
    ref = {}
    for i, (n, p) in enumerate(bad.items()):
        fp = WORK / f"bad_{i}.json"
        fp.write_text(json.dumps(p), encoding="utf-8")
        try:
            core.load_project(fp)
            ref[n] = False
        except core.EditorError:
            ref[n] = True
    for n, raw in (("duplicate key", b'{"format": 1, "format": 2}'), ("NaN literal", b'{"x": NaN}'),
                   ("oversized", b" " * (core.MAX_PROJECT_BYTES + 1)), ("not JSON", b"{")):
        fp = WORK / f"bad_{n.replace(' ', '_')}.json"
        fp.write_bytes(raw)
        try:
            core.load_project(fp)
            ref[n] = False
        except core.EditorError:
            ref[n] = True
    root, a = app_new()
    ok = a.open_project(WORK / "bad_0.json")
    e5["invalid project files are refused (16 cases); the open project is untouched"] = (
        all(ref.values()) and ok is False and a.project == core.new_project())
    det["E5_refusals"] = ref
    a.set_vertex_dz(6, -0.2)
    r = a.validate_now()
    e5["one lowered vertex: compiler refusal shown (groups), nothing written"] = (
        not r["ok"] and r["code"] == "BAD_MANIFEST" and "REFUSED" in a.status_var.get()
        and any("lower at least 2" in t for _, t in core.precheck(a.project, a.model)))
    (WORK / "full").mkdir()
    (WORK / "full" / "x.txt").write_text("keep")
    a.set_vertex_dz(2, -0.1)
    r = a.export_mod(WORK / "full")
    e5["export into a non-empty folder refused; its file kept"] = (
        not r["ok"] and sorted(p.name for p in (WORK / "full").iterdir()) == ["x.txt"])
    # G6-P30 (D-286): without the development variable only production-policy content validates / exports
    gate(None)
    a.set_waypoint_offset(1, (1, 1, 0))
    a.refresh()
    r = a.validate_now()
    r2 = a.export_mod(WORK / "gate_off")
    e5["variable unset: a route project shows DEVELOPMENT-ONLY and is refused (UNSUPPORTED), nothing written"] = (
        "DEVELOPMENT-ONLY" in a.prod_var.get() and not r["ok"] and r["code"] == "UNSUPPORTED"
        and "development-only" in r["detail"] and not r2["ok"] and not (WORK / "gate_off").exists())
    a.set_waypoint_offset(1, (0, 0, 0))
    a.set_graph(1)
    r = a.validate_now()
    e5["variable unset: graph B is DEVELOPMENT-ONLY and refused"] = (
        "DEVELOPMENT-ONLY" in a.prod_var.get() and not r["ok"] and r["code"] == "UNSUPPORTED")
    gate(LEVEL)
    root.destroy()

    # E6 production flow (G6-P30): variable unset; validate -> export -> import + enable -> plan, private folders
    e6 = {}
    gate(None)
    root, a = app_new()
    a.set_vertex_dz(6, -0.2)
    a.set_vertex_dz(2, -0.15)
    a.set_vertex_dz(4, -0.15)
    a.set_meta("id", "g6p25.west-basin-fairy")
    e6["status shows PRODUCTION-SUPPORTED; Validate / Export enabled without the variable"] = (
        "PRODUCTION-SUPPORTED" in a.prod_var.get() and str(a.validate_btn.cget("state")) == "normal"
        and not core.gate_enabled())
    r = a.validate_now()
    e6["validate: VALID production-supported, tx 9083786df631a5a3 (= G6-P27's runtime images), report says D-286"] = (
        r["ok"] and r["report"]["transaction"]["id"] == "9083786df631a5a3" and not r["report"]["development_only"]
        and "Production-supported" in a.status_var.get() and "production policy D-286" in a.report.get("1.0", "end"))
    r = a.export_mod(WORK / "prod_mod")
    e6["export writes mod.json; status says not imported / enabled yet"] = (
        r["ok"] and (WORK / "prod_mod" / "mod.json").is_file() and "NOT imported" in a.status_var.get())
    priv = {"home": None, "game": GAME, "mods": WORK / "prod_root" / "mods", "cache": WORK / "prod_root" / "cache"}
    ri = a.import_mod(WORK / "prod_mod", priv)
    res = rm.resolve_all(priv, write_plan=priv["cache"])
    text = (priv["cache"] / rm.PLAN_NAME).read_text(encoding="utf-8") if (priv["cache"] / rm.PLAN_NAME).is_file() else ""
    mp = g28.p1.parse_plan(text) if text else None
    e6["import + enable through the mod manager; plan (variable unset) carries one re-derived level-tx = G6-P27's"] = (
        ri["ok"] and "IMPORTED and ENABLED" in a.status_var.get() and res["active"] == ["g6p25.west-basin-fairy"]
        and mp is not None and g28.tx_rederived(mp, "g6p25.west-basin-fairy") and "9083786df631a5a3" in mp["txs"][0])
    root.destroy()
    gate(LEVEL)
    E["E6"] = e6
    fake = WORK / "fake_game" / "GAMEDATAbin" / "intro_20"
    fake.mkdir(parents=True)
    for n in ("intro_20.lvl", "intro_20.ptr", "transit.lvl"):
        (fake / n).write_bytes(b"\0" * 64)
    try:
        core.LevelModel(WORK / "fake_game")
        e5["other level files: refused (TARGET_CHANGED)"] = False
    except core.EditorError as x:
        e5["other level files: refused (TARGET_CHANGED)"] = x.code == "TARGET_CHANGED"
    after = [rm.sha256_bytes(x.read_bytes()) for x in (lp, pp, lp.with_name("transit.lvl"))]
    e5["original game files unchanged"] = before == after
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], cwd=ROOT, capture_output=True,
                        text=True).stdout.strip()
    e5["development gate production; binaries = the production identity"] = st == "production" and {
        n: rm.sha256_bytes((g24.BIN / n).read_bytes()) for n in g24.PROD} == g24.PROD
    E["E5"] = e5
    gate(None)

    res = {"pass": all(all(v.values()) for v in E.values()), "checks": E, "details": det}
    (WORK / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"pass": res["pass"], "checks": E}, indent=1))
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        sys.exit(check())
    raise SystemExit(__doc__)
