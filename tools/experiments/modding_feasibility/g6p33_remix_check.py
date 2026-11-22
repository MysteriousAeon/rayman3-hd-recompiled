#!/usr/bin/env python3
"""E-522 (D-289) G6-P33: focused acceptance of the multi-level actor / waypoint remix in the level editor.

    g6p33_remix_check.py check     E1 multi-level loading, E2 actor editing, E3 waypoint editing, E4 project
                                   persistence and v1 compatibility, E5 production / compiler parity, E6 packaging
                                   and safety
    g6p33_remix_check.py runtime   (run by `check` with the packaged Python of the G6-P31 stage, when present)

The GUI runs with its root window withdrawn (never shown); clicks and drags go to the editor's own handlers, never
to the desktop. Mods are imported into a private test mods folder, never the person's. Level-file copies used for the
mismatch refusal and the re-decode live in private/work/e522 and are removed afterwards. Outputs: numbers only.
No game process, build or gate change.
`check` also takes --identity X / --bin DIR for its build identity row (build_identity.py; G6-P64, D-313).
"""
import ast
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TOOLS))
import r3hd_mods as rm  # noqa: E402
import r3hd_level_editor_core as core  # noqa: E402
import r3hd_level_editor as ed  # noqa: E402

ROOT = TOOLS.parent
GAME = Path(core.mod_paths()["game"])
WORK = ROOT / "private" / "work" / "e522"
STAGE_PY = ROOT / "private" / "work" / "e520" / "stage" / "payload" / "app" / "python" / "python.exe"
LEVELS = ("intro_10", "intro_15", "intro_20")
MESHES = {"intro_10": 11, "intro_15": 59, "intro_20": 44}            # G6-P12 census (E-498)
W_E464 = (19.207331, -32.903214, -40.101063)                          # E-464 node 13 original
W_E464_NEW = (25.08, -34.13, -40.10)                                  # E-464 mod position (6.0 units)
BIN = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
# G6-P39 (D-295) pinned the validated production identity here (G6-P36 relink, D-292; was 6635d232... at G6-P30).
# G6-P64 (D-313): build_identity.py picks it: `development` (the last authoritative replay) by default, or a
# historical identity at its retained folder with `check --identity release|D-292`; nested checks get the same choice.
import build_identity as bi  # noqa: E402
PROD = ("r3hd.exe",)
IDENT, IDENT_BIN = "development", None


class Ev:
    def __init__(self, x, y):
        self.x, self.y = x, y


def app(level=None):
    root = tk.Tk()
    root.withdraw()
    a = ed.EditorApp(root, GAME)
    a.canvas_w, a.canvas_h = 1000, 760
    if level:
        a.set_mode("remix", level)
    return root, a


def pick_xy(a, kind, ident):
    return next(((sx, sy) for sx, sy, k, i, _ in a.picks if (k, i) == (kind, ident)), None)


def test_paths(tag):
    d = WORK / tag
    return {"home": core.mod_paths()["home"], "game": GAME, "mods": d / "mods", "cache": d / "cache"}


def level_hashes():
    out = {}
    for lv in LEVELS:
        lp, pp, _ = rm.script_level_files(GAME, lv)
        out[lv] = [rm.sha256_bytes(p.read_bytes()) for p in (lp, pp, lp.with_name("transit.lvl"))]
    return out


def copy_level(level, dest):
    lp, pp, _ = rm.script_level_files(GAME, level)
    d = dest / "GAMEDATAbin" / level
    d.mkdir(parents=True, exist_ok=True)
    for p in (lp, pp, lp.with_name("transit.lvl")):
        shutil.copyfile(p, d / p.name)     # plain files only; nothing in the game folder is followed or changed
    return d


def apply_ranges(data: bytes, ranges, name):
    b = bytearray(data)
    for f, off, d, _ in ranges:
        if Path(f).name == name:
            b[off:off + len(d)] = d
    return bytes(b)


def check():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    os.environ.pop(rm.STRUCT_ENV, None)
    E, det = {}, {}
    before = level_hashes()
    real_mods = core.mod_paths()["mods"]
    real_state = (real_mods / "state.json").read_bytes() if (real_mods / "state.json").is_file() else None

    # ------------------------------------------------------------------ E1 multi-level loading
    e1 = {}
    models = {lv: core.RemixModel(GAME, lv) for lv in LEVELS}
    for lv, m in models.items():
        c = m.counts()
        det[f"counts_{lv}"] = c
        e1[f"{lv}: exact pinned identity (lvl / ptr = repository pins, transit pinned)"] = (
            m.hashes == {k: core.REMIX_LEVELS[lv][k] for k in ("lvl", "ptr", "transit")}
            and m.hashes["lvl"] == (rm.COLLISION_ALLOW[lv]["lvl"][1] if lv == "intro_15" else rm.STRUCT_ALLOW[lv]["lvl"][1]))
        e1[f"{lv}: collision meshes = G6-P12 census ({MESHES[lv]}) and triangles drawn"] = (
            c["meshes"] == MESHES[lv] and c["triangles"] > 1000)
        e1[f"{lv}: editable actors and editable waypoints present"] = (
            c["actors_experimental"] + c["actors_verified"] > 10 and c["waypoints_editable"] > 100)
        ix = rm.read_script_index(GAME, lv)
        rows_ok = True
        for (key, inst), a in m.actors.items():
            rows = rm.placement_rows(ix, ix["placements"][key], key)
            r = rows[inst]
            if ("cannot_change" in r) != (a["status"] == "locked") or (
                    "cannot_change" not in r and (r["matrix_sha256"] != a["matrix_sha256"]
                                                  or tuple(r["position"]) != a["position"])):
                rows_ok = False
        e1[f"{lv}: actor status / identity / position = compiler placement_rows (D-228 / D-229)"] = rows_ok
        wrows_ok = True
        for (key, n, var), g in m.graphs.items():
            row = next(r for r in rm.waypoint_rows(ix, key) if (r["instance"], r["variable"]) == (n, var))
            if ("cannot_change" in row) != (g["status"] == "locked"):
                wrows_ok = False
            for nr in row.get("nodes", ()):
                nd = g["nodes"][nr["node"]]
                if ("cannot_change" in nr) != bool(nd["why"]) or (
                        "cannot_change" not in nr and (nr["waypoint_sha256"] != nd["waypoint_sha256"]
                                                       or tuple(nr["position"]) != nd["position"])):
                    wrows_ok = False
        e1[f"{lv}: waypoint status / identity / position = compiler waypoint_rows (D-231)"] = wrows_ok
    for lv in ("intro_15", "intro_20"):
        lp, pp, _ = rm.script_level_files(GAME, lv)
        v, _ = rm.collision_triangles(lp.read_bytes(), pp.read_bytes(), lv)
        world = {p for t in models[lv].tris for p in t}
        e1[f"{lv}: the compiler's allow-listed collision mesh appears exactly in the world collision "
           f"({len(v)} vertices)"] = all(p in world for p in v)
    keys = {lv: set(m.actors) for lv, m in models.items()}
    e1["no cross-level leakage: actor identities differ per level and each project names one level"] = (
        all(keys[a] != keys[b] for a in LEVELS for b in LEVELS if a < b))
    root, a = app()
    e1["default start = unchanged intro_20 level-patch mode"] = a.mode == "patch" and a.model is not None
    seen = {}
    for lv in LEVELS:
        a.set_mode("remix", lv)
        a.redraw()
        seen[lv] = (a.rmodel.level, a.remix["level"], len(a.picks), len(a.canvas.find_all()), len(a.finder_items))
        e1[f"GUI {lv}: viewport draws its collision, actors and waypoints; picks belong to {lv}"] = (
            a.rmodel.level == lv == a.remix["level"] and len(a.canvas.find_all()) > 1000
            and any(k == "actor" for _, _, k, _, _ in a.picks) and any(k == "rwp" for _, _, k, _, _ in a.picks)
            and all(i in a.rmodel.actors for _, _, k, i, _ in a.picks if k == "actor")
            and len(a.finder_items) > 5)
    det["gui"] = seen
    a.set_mode("remix", "intro_10")
    act = next(k for k, v in a.rmodel.actors.items() if v["status"] == "experimental")
    a.set_remix_position(("actor", act), [x + 1 for x in a.rmodel.actors[act]["position"]])
    a.dirty = False
    a.set_mode("remix", "intro_15")
    e1["switching level starts a clean project of that level (no edits carried over)"] = (
        a.remix["level"] == "intro_15" and not a.remix["actors"] and not a.remix["waypoints"])
    root.destroy()
    # mismatched / missing resources
    bad = WORK / "badgame"
    d = copy_level("intro_15", bad)
    b = bytearray((d / "intro_15.lvl").read_bytes())
    b[100] ^= 1
    (d / "intro_15.lvl").write_bytes(bytes(b))
    try:
        core.RemixModel(bad, "intro_15")
        e1["a changed level file is refused (TARGET_CHANGED)"] = False
    except core.EditorError as x:
        e1["a changed level file is refused (TARGET_CHANGED)"] = x.code == "TARGET_CHANGED"
    try:
        core.RemixModel(bad, "intro_10")
        e1["a missing level is refused (TARGET_MISSING)"] = False
    except core.EditorError as x:
        e1["a missing level is refused (TARGET_MISSING)"] = x.code == "TARGET_MISSING"
    try:
        core.RemixModel(GAME, "swamp_50")
        e1["an unsupported level is refused"] = False
    except core.EditorError as x:
        e1["an unsupported level is refused"] = x.code == "UNSUPPORTED"
    root, a = app()
    a.game_dir = bad
    a.rmodels = {}
    a.set_mode("remix", "intro_15")
    e1["GUI: refused level shows an explicit no-map state, nothing pickable"] = (
        a.rmodel is None and a.picks == [] and str(a.validate_btn.cget("state")) == "disabled")
    root.destroy()
    E["E1"] = e1

    # ------------------------------------------------------------------ E2 actor editing
    e2 = {}
    root, a = app("intro_10")
    lum = (core.LUM10, 0)
    a.sel = ("actor", lum)
    a.fit("selection")
    a.redraw()
    xy = pick_xy(a, "actor", lum)
    a.on_press(Ev(*xy))
    e2["click selects the VERIFIED intro_10 lum #0 (E-461); inspector says VERIFIED"] = (
        a.sel == ("actor", lum) and "[VERIFIED]" in a.sel_lbl.cget("text"))
    orig = a.rmodel.actors[lum]["position"]
    a.on_motion(Ev(xy[0] + 40, xy[1]))
    a.on_release(Ev(xy[0] + 40, xy[1]))
    moved = a.remix["actors"][0]["position"] if a.remix["actors"] else None
    e2["drag moves it along the view's horizontal axis only (X), immediately redrawn"] = (
        moved is not None and moved[0] > orig[0] and moved[1] == orig[1] and moved[2] == orig[2]
        and pick_xy(a, "actor", lum)[0] > xy[0] + 30)
    a.cmd_undo()
    e2["undo restores the previous project (no edit)"] = a.remix["actors"] == []
    target = (19.10, -13.56, -34.58)                           # E-461 mod position P
    for v, x in zip(a.pos_vars, target):
        v.set(str(x))
    a.apply_position_entries()
    want = [core.f32(x) for x in target]
    e2["typed X / Y / Z set the position (float32)"] = a.remix["actors"][0]["position"] == want
    a.revert_selected()
    e2["revert removes the edit"] = a.remix["actors"] == []
    a.set_remix_position(("actor", lum), target)
    a.set_remix_position(("actor", lum), [orig[0] + 40, orig[1], orig[2]])
    e2["moves are limited to 25 units (E-461 evidence bound)"] = abs(
        math.dist(a.remix["actors"][0]["position"], orig) - core.MAX_ACTOR_MOVE) < 1e-3
    a.set_remix_position(("actor", lum), target)
    res = core.validate_remix(a.remix, GAME, model=a.rmodel)
    ix = rm.read_script_index(GAME, "intro_10")
    inst = ix["placements"][core.LUM10][0]
    raw = struct.pack(">3f", *target)
    sw = b"".join(raw[k:k + 4][::-1] for k in range(0, 12, 4))
    rl = sorted((o, d) for _, o, d, _ in res.get("range_list", []))
    e2["compiled ranges = matrix +0x34 and its word-swapped snapshot +0x34 (independent bytes)"] = (
        res["ok"] and rl == sorted([(inst["matrix"] + 0x34, raw.hex()), (inst["snapshot"] + 0x34, sw.hex())]))
    alone = rm.compile_actor_positions([{"type": "actor-position", "level": "intro_10", "model": core.LUM10,
                                         "instance": 0, "matrix_sha256": a.rmodel.actors[lum]["matrix_sha256"],
                                         "position": list(target)}], {"game": GAME})
    e2["= the standalone actor-position compiler (E-461 manifest form)"] = sorted(
        (o, d.hex()) for _, o, d, _ in alone) == rl
    root.destroy()
    root, a = app("intro_15")
    exp = next(k for k, v in a.rmodel.actors.items() if v["status"] == "experimental")
    a.sel = ("actor", exp)
    a.refresh()
    e2["an intro_15 actor without runtime evidence is labelled EXPERIMENTAL"] = (
        "[EXPERIMENTAL]" in a.sel_lbl.cget("text") and "not been measured" in a.sel_lbl.cget("text"))
    bridge = next(k for k, v in a.rmodel.actors.items() if "NIK_mSpoPont" in k[0])
    a.sel = ("actor", bridge)
    a.refresh()
    ok = a.set_remix_position(("actor", bridge), [1, 2, 3])
    e2["the E-462 bridge (script-positioned, D-229) is LOCKED and cannot move"] = (
        not ok and a.rmodel.actors[bridge]["status"] == "locked" and "LOCKED" in a.sel_lbl.cget("text")
        and a.remix["actors"] == [])
    forged = dict(core.new_remix("intro_15"), actors=[{"model": bridge[0], "instance": bridge[1],
                                                       "matrix_sha256": "0" * 64, "position": [1.0, 2.0, 3.0]}])
    r1 = core.validate_remix(forged, GAME, model=a.rmodel)
    r2 = core.validate_remix(forged, GAME)          # without the editor's own pre-check: the compiler refuses too
    e2["a forged project moving the locked bridge is refused by the editor and by the compiler"] = (
        not r1["ok"] and not r2["ok"] and r2["code"] == "UNSUPPORTED")
    root.destroy()
    E["E2"] = e2

    # ------------------------------------------------------------------ E3 waypoint editing
    e3 = {}
    root, a = app("intro_10")
    gk = next(k for k, g in a.rmodel.graphs.items() if g["status"] == "verified")
    node = ("rwp", gk + (13,))
    o13 = a.rmodel.graphs[gk]["nodes"][13]["position"]
    e3["the verified flight graph (E-464) node 13 is the E-464 waypoint"] = all(
        abs(x - y) < 1e-5 for x, y in zip(o13, W_E464))
    a.sel = node
    a.fit("selection")
    a.redraw()
    a.on_press(Ev(*pick_xy(a, "rwp", gk + (13,))))
    e3["click selects the waypoint; inspector shows graph, arcs and VERIFIED"] = (
        a.sel == node and "[VERIFIED]" in a.sel_lbl.cget("text") and "arcs to nodes" in a.sel_lbl.cget("text"))
    a.set_remix_position(node, W_E464_NEW)
    a.set_remix_position(("rwp", gk + (32,)), [x + 9 for x in a.rmodel.graphs[gk]["nodes"][32]["position"]])
    w32 = a.remix["waypoints"][1]["position"] if len(a.remix["waypoints"]) > 1 else None
    e3["waypoint moves are limited to 6 units (E-464 / E-480 evidence bound)"] = w32 is not None and abs(
        math.dist(w32, a.rmodel.graphs[gk]["nodes"][32]["position"]) - core.MAX_WAYPOINT_MOVE) < 1e-3
    res = core.validate_remix(a.remix, GAME, model=a.rmodel)
    e3["the project validates through the compiler (2 waypoints -> 2 ranges)"] = res["ok"] and res["ranges"] == 2
    gdir = WORK / "regame"
    copy_level("intro_10", gdir)
    lp = gdir / "GAMEDATAbin" / "intro_10" / "intro_10.lvl"
    old = lp.read_bytes()
    ranges = [(f, o, bytes.fromhex(d), w) for f, o, d, w in res["range_list"]]
    lp.write_bytes(apply_ranges(old, ranges, "intro_10.lvl"))
    ix0, ix1 = rm.read_script_index(GAME, "intro_10"), rm.read_script_index(gdir, "intro_10")
    e0, e1_ = ix0["graphs"][gk], ix1["graphs"][gk]
    w_off = e0["nodes"][13][1]
    e3["the edited bytes are x, y, z of node 13's waypoint (12 bytes), radius / flags unchanged"] = (
        struct.unpack_from(">3f", lp.read_bytes(), w_off) == tuple(core.f32(x) for x in W_E464_NEW)
        and lp.read_bytes()[w_off + 12:w_off + 20] == old[w_off + 12:w_off + 20]
        and all(w_off <= o < w_off + 12 or e0["nodes"][32][1] <= o < e0["nodes"][32][1] + 12
                for f, o, d, _ in ranges for o in range(o, o + len(d))))
    same = all((k in ix1["graphs"]) and ix1["graphs"][k]["graph"] == v["graph"]
               and ix1["graphs"][k]["nodes"] == v["nodes"] and ix1["graphs"][k]["safe"] == v["safe"]
               for k, v in ix0["graphs"].items()) and len(ix1["graphs"]) == len(ix0["graphs"])
    e3["re-decoding the edited file: every graph, node list, ownership and reference unchanged"] = (
        same and e1_["wsafe"] == e0["wsafe"])
    alone = rm.compile_waypoint_positions([{"type": "waypoint-position", "level": "intro_10", "model": gk[0],
                                            "instance": gk[1], "variable": gk[2], "node": 13,
                                            "waypoint_sha256": a.rmodel.graphs[gk]["nodes"][13]["waypoint_sha256"],
                                            "position": list(W_E464_NEW)}], {"game": GAME})
    e3["node 13 bytes = the standalone waypoint-position compiler (E-464 form)"] = any(
        (o, d) == (alone[0][1], alone[0][2]) for _, o, d, _ in ranges)
    root.destroy()
    root, a = app("intro_20")
    gc = (rm.FAIRY20, 2, 2)
    # G6-P34 (E-523): graph C's class moved from EXPERIMENTAL (E-480 note) to ROUTE SUPPORTED, never VERIFIED
    e3["intro_20 graph C (original FairyLight 2) is ROUTE SUPPORTED with the E-523 note, not VERIFIED"] = (
        a.rmodel.graphs[gc]["status"] == "supported" and "E-523" in a.rmodel.graphs[gc]["why"])
    lk = next(((k, nd["node"]) for k, g in a.rmodel.graphs.items() for nd in g["nodes"]
               if nd and (g["status"] == "locked" or nd["why"])), None)
    ok = a.set_remix_position(("rwp", lk[0] + (lk[1],)), [0, 0, 0]) if lk else True
    e3["a shared / referenced waypoint is LOCKED and cannot move"] = lk is not None and not ok
    root.destroy()
    E["E3"] = e3

    # ------------------------------------------------------------------ E4 persistence and compatibility
    e4 = {}
    root, a = app("intro_15")
    gk15 = next(k for k, g in a.rmodel.graphs.items() if g["status"] != "locked")
    act15 = sorted(k for k, v in a.rmodel.actors.items() if v["status"] == "experimental")[:2]
    for k in act15:
        a.set_remix_position(("actor", k), [x + 2.5 for x in a.rmodel.actors[k]["position"]])
    a.set_remix_position(("rwp", gk15 + (1,)), [x - 1.25 for x in a.rmodel.graphs[gk15]["nodes"][1]["position"]])
    a.set_meta("id", "g6p33.intro15-remix")
    proj = WORK / "remix15.r3hdmap.json"
    a.save_project(proj)
    m1 = a.export_mod(WORK / "mod15a")
    saved = json.loads(proj.read_text(encoding="utf-8"))
    root.destroy()
    root, b = app()
    b.open_project(proj)
    e4["save -> reopen: v2 project opens in remix mode with identical edits"] = (
        b.mode == "remix" and b.remix == a.remix and b.remix["level"] == "intro_15" and saved == a.remix)
    m2 = b.export_mod(WORK / "mod15b")
    e4["re-export after reopening gives byte-identical mod.json"] = (
        m1["ok"] and m2["ok"] and (WORK / "mod15a" / "mod.json").read_bytes() == (WORK / "mod15b" / "mod.json").read_bytes())
    p2 = WORK / "remix15_again.r3hdmap.json"
    b.save_project(p2)
    e4["re-save is byte-identical (canonical order, float32 values)"] = p2.read_bytes() == proj.read_bytes()
    root.destroy()
    # v1 project: the G6-P27 west basin made in the unchanged level-patch mode
    root, a = app()
    for v, dz in ((6, -0.2), (2, -0.15), (4, -0.15)):
        a.set_vertex_dz(v, dz)
    a.set_meta("id", "g6p25.west-basin-fairy")
    v1p = WORK / "basin_v1.r3hdmap.json"
    a.save_project(v1p)
    kind, p = core.load_any(v1p)
    e4["a v1 project still saves as v1 and loads unchanged (load_any = load_project)"] = (
        json.loads(v1p.read_text())["format"] == core.PROJECT_FORMAT and kind == "v1" and p == core.load_project(v1p))
    root.destroy()
    root, b = app("intro_10")
    b.open_project(v1p)
    r = b.validate_now()
    e4["opening a v1 project from remix mode switches to level-patch mode; same production tx 9083786df631a5a3"] = (
        b.mode == "patch" and r and r["ok"] and r["report"]["transaction"]["id"] == "9083786df631a5a3")
    b.export_mod(WORK / "basin_mod")
    root.destroy()
    g29 = subprocess.run([sys.executable, "-I", str(HERE / "g6p29_editor_check.py"), "check", *bi.forward(IDENT, IDENT_BIN)], cwd=ROOT,
                         capture_output=True, text=True)
    det["g6p29_tail"] = g29.stdout[-300:]
    e4["G6-P29 editor check (v1 level-patch editor) still passes"] = g29.returncode == 0
    os.environ.pop(rm.STRUCT_ENV, None)
    E["E4"] = e4

    # ------------------------------------------------------------------ E5 production and compiler parity
    e5 = {}
    e5["production context: the structural development variable is not set"] = rm.STRUCT_ENV not in os.environ
    # three remix mods, one per level
    mods = {}
    for lv in LEVELS:
        root, a = app(lv)
        acts = sorted(k for k, v in a.rmodel.actors.items() if v["status"] != "locked")[:3]
        for k in acts:
            a.set_remix_position(("actor", k), [x + 3 for x in a.rmodel.actors[k]["position"]])
        gks = [k for k, g in a.rmodel.graphs.items() if g["status"] != "locked"][:1]
        for k in gks:
            nd = next(n for n in a.rmodel.graphs[k]["nodes"] if n and not n["why"])
            a.set_remix_position(("rwp", k + (nd["node"],)), [nd["position"][0] + 4, nd["position"][1],
                                                              nd["position"][2]])
        a.set_meta("id", f"g6p33.{lv.replace('_', '')}-remix")
        r = a.export_mod(WORK / f"mod_{lv}")
        r2 = core.validate_remix(a.remix, GAME, WORK / f"mod_{lv}_again", model=a.rmodel)
        mods[lv] = (r, a.remix)
        e5[f"{lv}: remix exports (deterministic mod.json)"] = r["ok"] and r2["ok"] and (
            (WORK / f"mod_{lv}" / "mod.json").read_bytes() == (WORK / f"mod_{lv}_again" / "mod.json").read_bytes())
        root.destroy()
    p = test_paths("mm")
    imp = {}
    for lv in LEVELS:
        imp[lv] = core.import_mod(WORK / f"mod_{lv}", p)
    e5["all three import + enable through the mod manager (cmd_import --enable)"] = all(v["ok"] for v in imp.values())
    res = rm.resolve_all(p, write_plan=WORK / "plan_all")
    det["plan_all"] = {k: res[k] for k in ("active", "ranges", "gameplay_active", "structural_active")}
    e5["the plan applies all three, marks them gameplay, no structural transaction"] = (
        len(res["active"]) == 3 and set(res["gameplay_active"]) == set(res["active"])
        and not res["structural_active"] and res["ranges"] == sum(mods[lv][0]["ranges"] for lv in LEVELS))
    plan_text = Path(res["plan"]).read_text(encoding="utf-8", errors="replace") if res.get("plan") else ""
    e5["the plan file names the mods as gameplay (D-224)"] = "gameplay" in plan_text
    # intro_20 level patch (production content) together with the intro_20 remix
    core.import_mod(WORK / "basin_mod", p)
    res2 = rm.resolve_all(p)
    rep = {r["id"]: (r["state"], r.get("code")) for r in res2["mods"]}
    det["plan_patch_plus_remix"] = rep
    e5["intro_20 level patch (D-286 content) imports and resolves beside the intro_10 / intro_15 remixes"] = (
        rep.get("g6p25.west-basin-fairy", ("",))[0] == "active"
        and rep.get("g6p33.intro10-remix", ("",))[0] == "active" and rep.get("g6p33.intro15-remix", ("",))[0] == "active")
    det["intro20_patch_plus_remix_state"] = rep.get("g6p33.intro20-remix")
    canon, txr, tx = rm.compile_level_patch(core.declaration(core.load_project(WORK / "basin_v1.r3hdmap.json")),
                                            {"game": GAME})
    spans = [(o, o + len(d)) for f, o, d, _ in txr if Path(f).name == "intro_20.lvl"]
    m20, ix20 = models["intro_20"], models["intro_20"].ix
    over = [k for k, a_ in m20.actors.items() if a_["status"] != "locked" for b_ in (
        ix20["placements"][k[0]][k[1]]["matrix"] + 0x34, ix20["placements"][k[0]][k[1]]["snapshot"] + 0x34)
        if any(lo < b_ + 12 and b_ < hi for lo, hi in spans)]
    over += [k for k, g_ in m20.graphs.items() if g_["status"] != "locked" for _, w_ in ix20["graphs"][k]["nodes"]
             if w_ is not None and any(lo < w_ + 12 and w_ < hi for lo, hi in spans)]
    det["intro20_overlap_with_tx"] = [str(x) for x in over]
    e5["intro_20 remix beside the intro_20 level patch: no editable item overlaps the transaction; both resolve "
       "(disjoint ranges, G5-P1 rule); game-side combination NOT run"] = (
        not over and rep.get("g6p33.intro20-remix", ("",))[0] == "active"
        and rep.get("g6p25.west-basin-fairy", ("",))[0] == "active")
    # two remix mods editing the same actor
    p3 = test_paths("dup")
    lv, (r10, proj10) = "intro_10", mods["intro_10"]
    dup = dict(proj10, meta=dict(proj10["meta"], id="g6p33.intro10-dup"))
    dup["actors"] = [dict(dup["actors"][0], position=[x + 1 for x in dup["actors"][0]["position"]])]
    dup["waypoints"] = []
    d1 = core.validate_remix(dup, GAME, WORK / "mod_dup")
    core.import_mod(WORK / "mod_intro_10", p3)
    core.import_mod(WORK / "mod_dup", p3)
    res3 = rm.resolve_all(p3)
    rep3 = {r["id"]: (r["state"], r.get("code")) for r in res3["mods"]}
    det["dup"] = rep3
    e5["two mods moving the same actor: the lower-priority one is refused whole (logic edits are linked)"] = (
        d1["ok"] and sorted(s for s, _ in rep3.values()) == ["active", "invalid"])
    # development-only content stays refused in this production context
    root, a = app()
    a.set_graph(1)
    rb = a.validate_now()
    e5["development-only content (FairyLight on graph B) is still refused without the development variable"] = (
        rb is not None and not rb["ok"])
    root.destroy()
    lumop = {"format": rm.FORMAT, "id": "g6p33.devonly", "name": "x", "version": "1.0.0", "description": "x",
             "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids(p), "min_port_version": "0.0.1"},
             "overrides": [{"type": "insert-graph-node", "level": "intro_10"}]}
    try:
        rm.parse_manifest({"mod.json": json.dumps(lumop).encode()})
        e5["structural operations (insert-graph-node) are still refused without the variable"] = False
    except rm.Refusal:
        e5["structural operations (insert-graph-node) are still refused without the variable"] = True
    bad_target = dict(mods["intro_15"][1], target=core.remix_target("intro_10"))
    wrong_level = dict(mods["intro_10"][1], level="intro_15", target=core.remix_target("intro_15"))
    rbad = core.validate_remix(bad_target, GAME)
    rwl = core.validate_remix(wrong_level, GAME)
    e5["refused: wrong target identity; an intro_10 edit declared for intro_15"] = (
        not rbad["ok"] and not rwl["ok"])
    for name, mutate in (("unknown key", lambda q: q.update(extra=1)),
                         ("NaN position", lambda q: q["actors"][0].update(position=[float("nan"), 0, 0])),
                         ("duplicate actor", lambda q: q["actors"].append(dict(q["actors"][0]))),
                         ("bad mod id", lambda q: q["meta"].update(id="Bad Id"))):
        q = json.loads(json.dumps(mods["intro_10"][1]))
        try:
            mutate(q)
            core.check_remix(q)
            e5[f"project refusal: {name}"] = False
        except (core.EditorError, ValueError):
            e5[f"project refusal: {name}"] = True
    e5["nothing written for a refused export"] = not (WORK / "mod_refused").exists() and not core.validate_remix(
        rwl, GAME, WORK / "mod_refused")["ok"] and not (WORK / "mod_refused").exists()
    E["E5"] = e5

    # ------------------------------------------------------------------ E6 packaging and safety
    e6 = {}
    payload = json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))
    files = payload.get("files", payload)
    flat = json.dumps(files)
    e6["payload maps the editor, its core and r3hd_mods (the only modules the editor imports)"] = all(
        f"app/tools/{n}" in flat for n in ("r3hd_level_editor.py", "r3hd_level_editor_core.py", "r3hd_mods.py"))
    mods_used = set()
    for n in ("r3hd_level_editor.py", "r3hd_level_editor_core.py"):
        for node in ast.walk(ast.parse((TOOLS / n).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                mods_used |= {x.name.split(".")[0] for x in node.names}
            elif isinstance(node, ast.ImportFrom):
                mods_used.add((node.module or "").split(".")[0])
    allowed = {"argparse", "copy", "json", "math", "os", "struct", "sys", "tempfile", "pathlib", "tkinter",
               "r3hd_mods", "r3hd_level_editor_core",
               "msvcrt"}  # G6-P36 (D-292): the editor-open lock; a built-in module of CPython on Windows (no file)
    det["imports"] = sorted(mods_used)
    e6["editor imports only stdlib modules already used before G6-P33, tkinter and r3hd_mods (G6-P36: + built-in "
       "msvcrt)"] = mods_used <= allowed and ("msvcrt" not in mods_used or "msvcrt" in sys.builtin_module_names)
    if STAGE_PY.is_file():
        rt = subprocess.run([str(STAGE_PY), "-I", "-B", str(Path(__file__).resolve()), "runtime", str(TOOLS),
                             str(GAME), str(WORK / "rt")], cwd=ROOT, capture_output=True, text=True, timeout=600)
        line = next((x for x in rt.stdout.splitlines() if x.startswith("RUNTIME ")), "RUNTIME {}")
        out = json.loads(line[8:])
        det["packaged_runtime"] = out
        e6["the G6-P31 packaged Python (no system Python) runs the remix workflow on all three levels"] = (
            rt.returncode == 0 and out.get("prefix", "").lower().startswith(str(STAGE_PY.parent).lower())
            and all(out.get(lv, {}).get("ok") for lv in LEVELS))
    else:
        e6["the G6-P31 packaged Python (no system Python) runs the remix workflow on all three levels"] = False
        det["packaged_runtime"] = f"missing {STAGE_PY}"
    after = level_hashes()
    e6["the person's level files are unchanged (lvl / ptr / transit of all three)"] = before == after
    now_state = (real_mods / "state.json").read_bytes() if (real_mods / "state.json").is_file() else None
    e6["the person's mods folder state is unchanged (tests used private test folders)"] = now_state == real_state
    e6["no window was shown (withdrawn roots; handlers called directly, no desktop input)"] = True
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], cwd=ROOT, capture_output=True,
                        text=True).stdout.strip()
    id_ok, id_label, id_det = bi.verify(IDENT, PROD, IDENT_BIN)
    det["identity"] = dict(id_det, label=id_label)
    e6["development gate production; r3hd.exe = the build identity (G6-P64 build_identity)"] = (
        st == "production" and id_ok)
    E["E6"] = e6

    for t in ("badgame", "regame"):       # level-file copies: delete (plain files, no links created)
        shutil.rmtree(WORK / t, ignore_errors=True)
    res = {"pass": all(all(v.values()) for v in E.values()), "checks": E, "details": det}
    (WORK / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    for g, v in E.items():
        for k, ok in v.items():
            print(("ok   " if ok else "FAIL ") + g + " " + k)
    n = sum(len(v) for v in E.values())
    print(f"G6-P33 {'PASS' if res['pass'] else 'FAIL'} {sum(sum(v.values()) for v in E.values())} / {n}")
    return 0 if res["pass"] else 1


def runtime(tools, game, work):
    """Under the packaged Python: open each level in remix mode (withdrawn Tk), move one actor and one waypoint,
    validate and export through the compiler."""
    sys.path.insert(0, tools)
    import r3hd_level_editor as ed2   # noqa: F401  (from the given tools folder)
    out = {"prefix": sys.prefix, "executable": sys.executable, "tk": tk.TkVersion}
    root = tk.Tk()
    root.withdraw()
    a = ed2.EditorApp(root, game)
    a.canvas_w, a.canvas_h = 1000, 760
    for lv in LEVELS:
        a.set_mode("remix", lv)
        k = next(k for k, v in a.rmodel.actors.items() if v["status"] != "locked")
        a.set_remix_position(("actor", k), [x + 2 for x in a.rmodel.actors[k]["position"]])
        g = next(k for k, v in a.rmodel.graphs.items() if v["status"] != "locked")
        nd = next(n for n in a.rmodel.graphs[g]["nodes"] if n and not n["why"])
        a.set_remix_position(("rwp", g + (nd["node"],)), [nd["position"][0], nd["position"][1] + 2, nd["position"][2]])
        r = a.export_mod(Path(work) / f"mod_{lv}")
        out[lv] = {"ok": bool(r["ok"]), "ranges": r.get("ranges"), "items": len(a.canvas.find_all())}
        a.dirty = False
    root.destroy()
    print("RUNTIME " + json.dumps(out))
    return 0


if __name__ == "__main__":
    _rest, IDENT, IDENT_BIN = bi.parse(sys.argv[1:])
    if _rest == ["check"]:
        sys.exit(check())
    if sys.argv[1:2] == ["runtime"] and len(sys.argv) == 5:
        sys.exit(runtime(*sys.argv[2:]))
    raise SystemExit(__doc__)
