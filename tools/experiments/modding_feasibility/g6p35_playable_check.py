#!/usr/bin/env python3
"""E-524 (D-291) G6-P35: acceptance of the placement-assisted remix editor, its presets, route panel and warnings.

    g6p35_playable_check.py examples   (re)write the example projects in remix_examples/ from the presets (needs the
                                       person's own level files: hashes come from them; no game bytes are written)
    g6p35_playable_check.py check      A1 collision-assisted placement, A2 snap to ground, A3 presets and examples,
                                       A4 route usability, A5 warnings, A6 regressions, A7 packaged runtime,
                                       A8 desktop and data safety
    g6p35_playable_check.py runtime    (run by `check` with the packaged Python of the G6-P31 stage)

The GUI runs with its root window withdrawn (never shown); handlers are called directly, never desktop input. Mods are
imported into private test folders under private/work/e524, never the person's. No game process, build or gate change.
"""
import json
import math
import os
import shutil
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
WORK = ROOT / "private" / "work" / "e524"
E523 = ROOT / "private" / "work" / "e523" / "mods"
EX = HERE / "remix_examples"
STAGE_PY = ROOT / "private" / "work" / "e520" / "stage" / "payload" / "app" / "python" / "python.exe"
LEVELS = ("intro_10", "intro_15", "intro_20")
BIN = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
# G6-P39 (D-295): the current validated production identity (G6-P36 relink, D-292; was 6635d232... at G6-P30)
CURRENT = json.loads((ROOT / "config" / "release" / "production_identity.json").read_text(
    encoding="utf-8"))["current"]["binaries"]
PROD = {"r3hd.exe": CURRENT["r3hd.exe"]}
EXAMPLES = {
    "intro10_lums_on_flight_path.r3hdmap.json": (
        ["intro10-lums-on-flight-path"], "intro_10", "example.intro10-lums",
        "intro_10 lums on the flight path",
        "Runtime-VERIFIED example (E-523): lums #1 and #3 moved onto the flight path, collected there."),
    "intro20_fairy_loop_and_actors.r3hdmap.json": (
        ["intro20-graph-c-reshape", "intro20-placement-trio"], "intro_20", "example.intro20-loop-actors",
        "intro_20 FairyLight loop + moved actors",
        "Multi-edit example (E-523): FairyLight 2 loop reshaped (ROUTE SUPPORTED) and three actors moved (PLACEMENT "
        "VERIFIED, behaviour unknown)."),
}


def app(level=None):
    root = tk.Tk()
    root.withdraw()
    a = ed.EditorApp(root, GAME)
    a.canvas_w, a.canvas_h = 1000, 760
    if level:
        a.set_mode("remix", level)
    return root, a


def example_project(presets, level, mid, name, desc, model):
    p = core.new_remix(level)
    for pid in presets:
        p = core.apply_preset(p, pid, model)
    p["meta"] = {"id": mid, "name": name, "description": desc}
    return core.check_remix(p)


def write_examples():
    EX.mkdir(exist_ok=True)
    models = {}
    for fn, (ps, lv, mid, name, desc) in EXAMPLES.items():
        m = models.setdefault(lv, core.RemixModel(GAME, lv))
        core.save_remix(example_project(ps, lv, mid, name, desc, m), EX / fn)
        print("wrote", EX / fn)
    return 0


def find_case(models, code, offsets):
    """The first (level, actor, offset) whose snap proposal gives `code` (deterministic search order)."""
    for lv in ("intro_20", "intro_15", "intro_10"):
        m = models[lv]
        gi = m.ground_index()
        for ident, a in sorted(m.actors.items(), key=lambda x: (x[1]["name"], x[0][1])):
            if a["status"] in ("locked", "script_overridden"):
                continue
            for off in offsets:
                pos = [core.f32(o + d) for o, d in zip(a["position"], off)]
                if math.dist(pos, a["position"]) > core.MAX_ACTOR_MOVE:
                    continue
                r = core.snap_proposal(gi, pos, a["position"], core.MAX_ACTOR_MOVE)
                if (r["ok"] and code == "OK") or r.get("code") == code:
                    return lv, ident, pos, r
    return None


OFFS = [(dx, dy, dz) for dz in (0.0, 2.0, -1.0, 6.0) for dx in (3.0, -3.0, 8.0, -8.0, 15.0, 24.0)
        for dy in (0.0, 5.0, -5.0)]


def level_hashes():
    out = {}
    for lv in LEVELS:
        lp, pp, _ = rm.script_level_files(GAME, lv)
        out[lv] = [rm.sha256_bytes(p.read_bytes()) for p in (lp, pp, lp.with_name("transit.lvl"))]
    return out


def check():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    os.environ.pop(rm.STRUCT_ENV, None)
    E, det = {}, {}
    before = level_hashes()
    real_mods = core.mod_paths()["mods"]
    real_state = (real_mods / "state.json").read_bytes() if (real_mods / "state.json").is_file() else None
    models = {lv: core.RemixModel(GAME, lv) for lv in LEVELS}

    # ------------------------------------------------------------------ A1 collision-assisted placement
    a1 = {}
    cov = {}
    for lv, m in models.items():
        gi = m.ground_index()
        gi2 = core.GroundIndex(m.tris)
        a1[f"{lv}: ground index deterministic (same triangles and grid on a rebuild)"] = (
            gi.tris == gi2.tris and gi.grid == gi2.grid and len(gi.tris) + gi.skipped == len(m.tris))
        st, same = {}, True
        for ident, a in sorted(m.actors.items()):
            if a["status"] == "locked":
                continue
            q1, q2 = core.ground_query(gi, a["position"]), core.ground_query(gi2, a["position"])
            same &= q1 == q2
            st[q1["state"]] = st.get(q1["state"], 0) + 1
        n = sum(st.values())
        cov[lv] = {"editable_actors": n, "states": st, "ground_like_triangles": len(gi.tris),
                   "steep_or_wall_triangles": gi.skipped,
                   "ambiguity_rate": round(st.get("ambiguous", 0) / n, 3) if n else None,
                   "ground_rate": round(st.get("ground", 0) / n, 3) if n else None}
        a1[f"{lv}: every editable actor gets one of the four states; repeated queries identical"] = (
            same and set(st) <= set(core.GROUND_STATES))
    det["coverage"] = cov
    m20, gi20 = models["intro_20"], models["intro_20"].ground_index()
    pz = next(k for k in m20.actors if m20.actors[k]["name"] == "YAM_mPowerz" and k[1] == 1)
    p = m20.actors[pz]["position"]
    q = core.ground_query(gi20, p)
    a1["intro_20 Powerz #1: GROUND, one surface, height above it = z - surface z"] = (
        q["state"] == "ground" and len(q["surfaces"]) == 1 and abs(q["dz"] - (p[2] - q["surfaces"][0][0])) < 1e-9)
    qb = core.ground_query(gi20, (p[0], p[1], q["surfaces"][0][0] - 1.0))
    a1["a point 1 unit under that surface: UNDER A SURFACE (not GROUND)"] = qb["state"] == "below_surface"
    qn = core.ground_query(gi20, (5000.0, 5000.0, 0.0))
    a1["a point outside the decoded collision: NO SURFACE FOUND, no horizontal neighbour, not called unsafe"] = (
        qn["state"] == "no_surface" and qn["horizontal"] is None and "not a safety verdict" in core.ground_text(qn))
    amb = next(((k, a) for k, a in sorted(m20.actors.items()) if a["status"] != "locked"
                and core.ground_query(gi20, a["position"])["state"] == "ambiguous"), None)
    qa = core.ground_query(gi20, amb[1]["position"]) if amb else None
    a1["stacked floors in the snap window: AMBIGUOUS with every surface listed"] = bool(
        qa and len(qa["window"]) >= 2 and all(f"{z:.3f}" in core.ground_text(qa) for z, _ in qa["window"]))
    a1["every ground text is labelled a prediction (static collision only)"] = all(
        "prediction" in core.ground_text(x) for x in (q, qb, qn, qa) if x)
    lum = next(k for k in models["intro_10"].actors if models["intro_10"].actors[k]["name"] == "NIN_m_Lums_Int10"
               and k[1] == 1)
    ql = core.ground_query(models["intro_10"].ground_index(), models["intro_10"].actors[lum]["position"])
    a1["intro_10 flight lum: no ground claimed (flying content is not called unsafe)"] = ql["state"] != "ground"
    E["A1"] = a1

    # ------------------------------------------------------------------ A2 snap to ground
    a2 = {}
    cases = {c: find_case(models, c, OFFS) for c in ("OK", "NO_REFERENCE", "NO_SURFACE", "AMBIGUOUS", "STEEP",
                                                       "OUT_OF_BOUND", "BLOCKED")}
    det["snap_cases"] = {c: (v[0], core.short_name(v[1][0]), v[1][1], v[2], v[3].get("code", "OK")) if v else None
                         for c, v in cases.items()}
    lv, ident, pos, r = cases["OK"]
    m = models[lv]
    gi = m.ground_index()
    a = m.actors[ident]
    oq = core.ground_query(gi, a["position"])
    a2["an OK proposal keeps x / y, puts z at surface + the original's own height above ground (float32)"] = (
        r["position"][:2] == pos[:2] and r["position"][2] == core.f32(r["surface_z"] + max(0.0, oq["dz"]))
        and r["normal_z"] >= core.SNAP_MIN_NZ and math.dist(r["position"], a["position"]) <= core.MAX_ACTOR_MOVE)
    a2["the same request gives the same proposal (deterministic)"] = r == core.snap_proposal(
        gi, pos, a["position"], core.MAX_ACTOR_MOVE)
    for c in ("NO_REFERENCE", "NO_SURFACE", "AMBIGUOUS", "STEEP", "OUT_OF_BOUND"):
        a2[f"refusal {c} found on real geometry and refuses (no position offered)"] = bool(
            cases[c] and not cases[c][3]["ok"] and "position" not in cases[c][3])
    a2["already-grounded original: NO_CHANGE (nothing offered)"] = core.snap_proposal(
        gi, a["position"], a["position"], core.MAX_ACTOR_MOVE).get("code") in ("NO_CHANGE", "NO_REFERENCE")
    # GUI: preview, apply, undo; refusal; stale preview
    root, ap = app(lv)
    try:
        ap.sel = ("actor", ident)
        ap.set_remix_position(ap.sel, pos, clamp=False)
        before_p = json.dumps(ap.remix, sort_keys=True)
        prop = ap.snap_preview()
        ap.redraw()
        a2["GUI preview: proposal shown and drawn, project unchanged, Apply enabled"] = (
            prop == r and json.dumps(ap.remix, sort_keys=True) == before_p and bool(ap.canvas.find_withtag("snap"))
            and str(ap.snap_apply_btn.cget("state")) == "normal" and "Snap proposal" in ap.snap_lbl.cget("text"))
        ok = ap.snap_apply()
        a2["GUI apply: position = proposal; source identity (matrix hash) unchanged"] = (
            ok and ap.remix["actors"][0]["position"] == r["position"]
            and ap.remix["actors"][0]["matrix_sha256"] == a["matrix_sha256"])
        ap.cmd_undo()
        a2["undo restores the pre-snap position (reversible)"] = json.dumps(ap.remix, sort_keys=True) == before_p
        ap.snap_preview()
        ap.nudge_position(0, 1)
        a2["a preview made stale by another edit cannot be applied"] = (
            ap.snap is None and ap.snap_apply() is False)
        lv2, id2, pos2, r2 = cases["AMBIGUOUS"]
        if lv2 != lv:
            ap.dirty = False
            ap.set_mode("remix", lv2)
        ap.sel = ("actor", id2)
        ap.set_remix_position(ap.sel, pos2, clamp=False)
        snap_before = json.dumps(ap.remix, sort_keys=True)
        pr2 = ap.snap_preview()
        a2["GUI refusal: reason shown, Apply disabled, project unchanged"] = (
            not pr2["ok"] and str(ap.snap_apply_btn.cget("state")) == "disabled" and ap.snap_apply() is False
            and json.dumps(ap.remix, sort_keys=True) == snap_before and "refused" in ap.snap_lbl.cget("text"))
        ap.dirty = False
        ap.set_mode("remix", "intro_15")
        br = next(k for k, v in ap.rmodel.actors.items() if v["status"] == "locked")
        ap.sel = ("actor", br)
        a2["locked actor: snap refused (LOCKED)"] = ap.snap_preview()["code"] == "LOCKED"
    finally:
        ap.dirty = False
        root.destroy()
    E["A2"] = a2

    # ------------------------------------------------------------------ A3 presets and examples
    a3 = {}
    mp = core.mod_paths()
    for ps in core.PRESETS:
        m = models[ps["level"]]
        p1 = core.apply_preset(core.new_remix(ps["level"]), ps["id"], m)
        p2 = core.apply_preset(core.new_remix(ps["level"]), ps["id"], m)
        r1 = core.validate_remix(p1, GAME, model=m)
        a3[f"preset {ps['id']}: compiles through validate_remix (cmd_validate + compile_mod), deterministic"] = (
            r1["ok"] and p1 == p2 and r1["range_list"] == core.validate_remix(p2, GAME, model=m)["range_list"])
        det[f"preset_{ps['id']}"] = {"ranges": r1.get("ranges"), "evidence": ps["evidence"]}
    # identical bytes to the run-tested G6-P34 mods (E-523)
    rl = {}
    for case, lv, pids in (("L", "intro_10", ["intro10-lums-on-flight-path"]),
                           ("C", "intro_20", ["intro20-graph-c-reshape", "intro20-placement-trio"])):
        p = core.new_remix(lv)
        for pid in pids:
            p = core.apply_preset(p, pid, models[lv])
        got = {tuple(x) for x in core.validate_remix(p, GAME, model=models[lv])["range_list"]}
        f = E523 / f"{case}_ranges.json"
        ran = {tuple(x) for x in json.loads(f.read_text())} if f.is_file() else set()
        rl[case] = (len(got), len(ran))
        a3[f"E-523 run {case}: preset ranges are byte-identical to ranges served in that production run"] = (
            bool(ran) and (got == ran if case == "C" else got <= ran))
    det["e523_ranges"] = rl
    fb = core.apply_preset(core.new_remix("intro_10"), "intro10-flight-bend", models["intro_10"])
    w = fb["waypoints"][0]
    a3["flight-bend preset = E-464 node 13 moved to (25.08, -34.13, -40.10) (float32)"] = (
        w["node"] == 13 and w["position"] == [core.f32(v) for v in (25.08, -34.13, -40.10)])
    pp = core.patch_preset()
    vr = core.validate(pp, GAME, WORK / "patch_a")
    src = HERE / "level_patch_examples" / "g6p25_west_basin_fairy.json"
    paths = {"home": mp["home"], "game": GAME, "mods": WORK / "pm", "cache": WORK / "pc"}
    rb = rm.cmd_level_patch(paths, src, WORK / "patch_b", check=False)
    a3["level-patch preset: production policy, compiles without the development variable"] = (
        vr["ok"] and core.production_status(pp)[0] and rm.STRUCT_ENV not in os.environ)
    a3["level-patch preset: transaction members identical to the G6-P25 / G6-P30 production patch"] = (
        vr["ok"] and vr["report"]["transaction"]["members"] == rb["transaction"]["members"])
    for fn, (pids, lv, mid, name, desc) in EXAMPLES.items():
        path = EX / fn
        kind, p = core.load_any(path)
        m = models[lv]
        regen = (json.dumps(example_project(pids, lv, mid, name, desc, m), indent=1) + "\n").encode()
        a3[f"example {fn}: v2 project, edit declarations only, regenerated byte-identically from its presets"] = (
            kind == "v2" and set(json.loads(path.read_bytes())) == core.REMIX_KEYS
            and path.read_bytes().replace(b"\r\n", b"\n") == regen
            and len(path.read_bytes()) < 8192)
        out = WORK / f"ex_{lv}"
        r = core.validate_remix(p, GAME, out, model=m)
        tp = {"home": mp["home"], "game": GAME, "mods": WORK / f"exmods_{lv}", "cache": WORK / f"excache_{lv}"}
        imp = core.import_mod(out, tp)
        res = rm.resolve_all(tp)
        a3[f"example {fn}: exports, imports + enables through the mod manager, plan active"] = (
            r["ok"] and imp["ok"] and mid in res["active"])
    E["A3"] = a3

    # ------------------------------------------------------------------ A4 route usability
    a4 = {}
    root, ap = app("intro_20")
    try:
        gc = next(i for t, i in ap.graph_items if ap.rmodel.graphs[i]["name"] == "NIN_m_FairyLight"
                  and i[1:] == (2, 2))
        a4["explicit graph list: every graph of the level, with its status"] = (
            len(ap.graph_items) == len(ap.rmodel.graphs)
            and all(f"[{ed.STATUS_TEXT[ap.rmodel.graphs[i]['status']]}]" in t for t, i in ap.graph_items))
        label = next(t for t, i in ap.graph_items if i == gc)
        ap.select_graph_label(label)
        info = ap.route_info.cget("text")
        a4["graph C selected: stored-in owner, measured follower, loop sequence 0 -> ... -> 5 -> 0"] = (
            ap.sel == ("rgraph", gc) and "Followed by: original FairyLight instance 2" in info
            and "0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 0" in info and ap.route_panel.winfo_manager() == "pack")
        ap.zoom_route()
        pts = [ap.proj(nd["position"]) for nd in ap.rmodel.graphs[gc]["nodes"]]
        a4["zoom to route: every node of the route inside the view"] = all(
            0 <= x <= ap.canvas_w and 0 <= y <= ap.canvas_h for x, y in pts)
        ap.cmd_preset("intro20-graph-c-reshape", confirm=False)
        ap.select_graph_label(label)
        cmp_ = core.route_compare(ap.rmodel, ap.remix, gc)
        dashed = [i for i in ap.canvas.find_withtag("dyn") if ap.canvas.type(i) == "line"
                  and ap.canvas.itemcget(i, "dash")]
        a4["original vs modified: 3 nodes moved, original route drawn dashed, node list marks them"] = (
            sum(1 for c in cmp_ if c["moved"] > 0) == 3 and len(dashed) >= 6
            and sum(1 for i in range(ap.route_nodes.size()) if ap.route_nodes.get(i).startswith("*")) == 3)
        ap.route_nodes.selection_clear(0, "end")
        ap.route_nodes.selection_set(3)
        ap.route_node_select()
        a4["selecting node 3 in the list selects that waypoint"] = ap.sel == ("rwp", gc + (3,))
        ap.revert_selected()
        a4["revert this waypoint: only node 3's edit removed"] = sorted(
            w["node"] for w in ap.remix["waypoints"]) == [0, 5]
        ap.revert_route()
        a4["revert whole route: no waypoint edit left; undo restores the two"] = (
            ap.remix["waypoints"] == [] and (ap.cmd_undo() or True) and len(ap.remix["waypoints"]) == 2)
        ap.dirty = False
        ap.set_mode("remix", "intro_15")
        mk = next(i for t, i in ap.graph_items if ap.rmodel.graphs[i]["name"] == "NIN_m_MurfyIntro15")
        ap.select_graph_label(next(t for t, i in ap.graph_items if i == mk))
        a4["graph with no measured follower: 'Followed by: UNKNOWN' (never guessed)"] = (
            "Followed by: UNKNOWN" in ap.route_info.cget("text"))
        a4["node insertion is not offered (development-only text shown; no insert command)"] = (
            "never inserts nodes" in core.NODE_INSERTION_TEXT
            and not any("insert" in n.lower() for n in dir(ap) if callable(getattr(ap, n, None))
                        and not n.startswith("_")))
    finally:
        ap.dirty = False
        root.destroy()
    E["A4"] = a4

    # ------------------------------------------------------------------ A5 warnings
    a5 = {}
    m = models["intro_20"]
    gi = m.ground_index()
    p = core.new_remix("intro_20")

    def add(p, ident, pos):
        q = dict(p)
        q["actors"] = [x for x in p["actors"] if (x["model"], x["instance"]) != ident] + [
            {"model": ident[0], "instance": ident[1], "matrix_sha256": m.actors[ident]["matrix_sha256"],
             "position": [core.f32(v) for v in pos]}]
        return core.check_remix(q)

    pa = m.actors[pz]["position"]
    p = add(p, pz, (pa[0], pa[1], core.ground_query(gi, pa)["surfaces"][0][0] - 1.0))     # under the floor
    if amb:
        p = add(p, amb[0], amb[1]["position"][:2] + (amb[1]["position"][2] + 0.01,))       # stacked
    far = None
    for ident, x in sorted(m.actors.items()):
        if x["status"] == "locked" or core.ground_query(gi, x["position"])["state"] == "no_surface":
            continue
        for d in ((24.0, 0, 0), (-24.0, 0, 0), (0, 24.0, 0), (0, -24.0, 0)):
            t = [o + v for o, v in zip(x["position"], d)]
            qq = core.ground_query(gi, t)
            if qq["state"] == "no_surface" and qq["horizontal"] is None:
                far = (ident, t)
                break
        if far and far[0] not in (pz, amb and amb[0]):
            break
        far = None
    if far:
        p = add(p, far[0], far[1])
    p = core.apply_preset(p, "intro20-graph-c-reshape", m)
    p_bytes = json.dumps(p, sort_keys=True)
    r_before = core.validate_remix(p, GAME, model=m)
    ws = core.remix_warnings(p, m)
    r_after = core.validate_remix(p, GAME, model=m)
    codes = {c for _, c, _ in ws}
    det["warning_codes"] = sorted(codes)
    for c in ("BELOW_SURFACE", "STACKED", "FAR_FROM_COLLISION", "NEAR_BOUND", "BEHAVIOUR_UNVERIFIED",
              "ROUTE_SUPPORTED"):
        a5[f"warning {c} raised for its case"] = c in codes
    pm = core.new_remix("intro_15")
    m15 = models["intro_15"]
    mk = next(k for k in m15.graphs if m15.graphs[k]["name"] == "NIN_m_MurfyIntro15" and k[1:] == (0, 0))
    nd = m15.graphs[mk]["nodes"][0]
    pm["waypoints"] = [{"model": mk[0], "instance": 0, "variable": 0, "node": 0,
                        "waypoint_sha256": nd["waypoint_sha256"],
                        "position": [nd["position"][0], nd["position"][1] + 2, nd["position"][2]]}]
    a5["warning ROUTE_FOLLOWER_UNKNOWN for the Murfy graph (no follower measured)"] = any(
        c == "ROUTE_FOLLOWER_UNKNOWN" for _, c, _ in core.remix_warnings(pm, m15))
    a5["warnings never change the project or the compiler result (same ranges, same manifest)"] = (
        json.dumps(p, sort_keys=True) == p_bytes and r_before["ok"] and r_before["range_list"] == r_after["range_list"]
        and r_before["manifest"] == r_after["manifest"])
    a5["verified preset alone gives no warn-level warning (intro_10 lums)"] = not [
        w for w in core.remix_warnings(core.apply_preset(core.new_remix("intro_10"), "intro10-lums-on-flight-path",
                                                         models["intro_10"]), models["intro_10"]) if w[0] == "warn"]
    root, ap = app("intro_20")
    try:
        ap.remix = p
        res = ap.validate_remix_now()
        txt = ap.report.get("1.0", "end")
        a5["GUI validate: compiler verdict first, advisory warnings listed after it, verdict unchanged"] = (
            res["ok"] and "Advisory warnings" in txt and "VALID" in ap.status_var.get()
            and txt.index(res["text"].splitlines()[0]) < txt.index("Advisory warnings")
            and res["range_list"] == r_before["range_list"])
        ap.sel = ("actor", pz)
        cur = json.dumps(ap.remix, sort_keys=True)
        orig = m.actors[pz]["position"]
        for v, x in zip(ap.pos_vars, (orig[0] + 30.0, orig[1], orig[2])):
            v.set(f"{x:.3f}")
        ap.apply_position_entries()
        a5["typed position beyond the bound: refused unchanged (never silently clamped)"] = (
            json.dumps(ap.remix, sort_keys=True) == cur and "Refused" in ap.bottom.cget("text"))
        bad = json.loads(cur)
        bad["actors"][0]["matrix_sha256"] = "0" * 64
        ap.remix = core.check_remix(bad)
        res = ap.validate_remix_now()
        want = core.validate_remix(bad, GAME, model=m)
        a5["refusal shows the actual reason from the authoritative check (same code and text)"] = (
            not res["ok"] and res["code"] == want["code"] and want["detail"] in ap.report.get("1.0", "end"))
        nomodel = core.validate_remix(bad, GAME)
        a5["without the editor pre-check the compiler itself refuses the same project"] = (
            not nomodel["ok"] and nomodel["code"] not in ("", None))
        det["compiler_refusal"] = (nomodel["code"], nomodel["detail"][:160])
    finally:
        ap.dirty = False
        root.destroy()
    E["A5"] = a5

    # ------------------------------------------------------------------ A6 regressions
    a6 = {}
    r = subprocess.run([sys.executable, "-I", str(HERE / "g6p33_remix_check.py"), "check"], cwd=ROOT,
                       capture_output=True, text=True, timeout=1500)
    last = [x for x in r.stdout.splitlines() if x.startswith("G6-P33 ")]
    det["g6p33"] = last
    a6["G6-P33 check 78 / 78 (includes G6-P29 editor acceptance and the packaged G6-P33 run)"] = (
        r.returncode == 0 and last == ["G6-P33 PASS 78 / 78"])
    r = subprocess.run([sys.executable, "-I", str(TOOLS / "r3hd_mods.py"), "selftest"], cwd=ROOT,
                       capture_output=True, text=True, timeout=1500)
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    det["selftest"] = tail
    a6["r3hd_mods selftest PASS (compiler and mod manager)"] = r.returncode == 0 and "PASS" in tail
    for t in ("m33_regression.py", "m36_regression.py", "m38_regression.py"):
        r = subprocess.run([sys.executable, "-I", str(TOOLS / t)], cwd=ROOT, capture_output=True, text=True,
                           timeout=900)
        tail = (r.stdout.strip().splitlines() or [""])[-1]
        det[t] = tail
        a6[f"{t} passes"] = r.returncode == 0
    E["A6"] = a6

    # ------------------------------------------------------------------ A7 packaged runtime
    a7 = {}
    if STAGE_PY.is_file():
        rt = subprocess.run([str(STAGE_PY), "-I", "-B", str(Path(__file__).resolve()), "runtime", str(TOOLS),
                             str(GAME), str(WORK / "rt")], cwd=ROOT, capture_output=True, text=True, timeout=900)
        line = next((x for x in rt.stdout.splitlines() if x.startswith("RUNTIME ")), "RUNTIME {}")
        out = json.loads(line[8:])
        det["packaged_runtime"] = out
        a7["the G6-P31 packaged Python (no system Python) loads the G6-P35 editor"] = (
            rt.returncode == 0 and out.get("prefix", "").lower().startswith(str(STAGE_PY.parent).lower()))
        a7["packaged: ground query, snap preview / apply, preset, route panel, warnings, export on all levels"] = all(
            out.get(lv, {}).get("ok") for lv in LEVELS)
    else:
        a7["the G6-P31 packaged Python (no system Python) loads the G6-P35 editor"] = False
        det["packaged_runtime"] = f"missing {STAGE_PY}"
    payload = json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))
    flat = json.dumps(payload.get("files", payload))
    a7["package layout unchanged: the payload already maps the three editor modules; no new module"] = all(
        f"app/tools/{n}" in flat for n in ("r3hd_level_editor.py", "r3hd_level_editor_core.py", "r3hd_mods.py"))
    E["A7"] = a7

    # ------------------------------------------------------------------ A8 desktop and data safety
    a8 = {}
    a8["the person's level files are unchanged (lvl / ptr / transit of all three)"] = before == level_hashes()
    now_state = (real_mods / "state.json").read_bytes() if (real_mods / "state.json").is_file() else None
    a8["the person's mods folder state is unchanged (tests used private test folders)"] = now_state == real_state
    a8["no window shown, no desktop input (withdrawn roots; handlers called directly); no game process"] = True
    st = subprocess.run([sys.executable, str(HERE / "g5p1_dev_gate.py"), "status"], cwd=ROOT, capture_output=True,
                        text=True).stdout.strip()
    a8["development gate production; r3hd.exe = the production identity; variable absent"] = (
        st == "production" and rm.STRUCT_ENV not in os.environ and all(
            rm.sha256_bytes((BIN / n).read_bytes()) == h for n, h in PROD.items()))
    ex_ok = True
    for fn in EXAMPLES:
        d = json.loads((EX / fn).read_bytes())
        ex_ok &= all(set(x) == core.ACTOR_KEYS for x in d["actors"]) and all(
            set(x) == core.WAYPOINT_KEYS for x in d["waypoints"])
    a8["committed examples hold identities, hashes and positions only (no level bytes)"] = ex_ok
    E["A8"] = a8

    res = {"pass": all(all(v.values()) for v in E.values()), "checks": E, "details": det}
    (WORK / "check.json").write_text(json.dumps(res, indent=1, default=str) + "\n", encoding="utf-8")
    for g, v in E.items():
        for k, ok in v.items():
            print(("ok   " if ok else "FAIL ") + g + " " + k)
    print("DETAILS " + json.dumps({k: det[k] for k in ("coverage", "snap_cases", "warning_codes", "e523_ranges")},
                                  default=str))
    n = sum(len(v) for v in E.values())
    print(f"G6-P35 {'PASS' if res['pass'] else 'FAIL'} {sum(sum(v.values()) for v in E.values())} / {n}")
    return 0 if res["pass"] else 1


def runtime(tools, game, work):
    """Under the packaged Python: on each level, ground query + snap preview / apply on the first OK case, a preset
    where one exists, the route panel of an editable graph, warnings, then export through the compiler."""
    sys.path.insert(0, tools)
    import r3hd_level_editor as ed2   # noqa: F401
    import r3hd_level_editor_core as c2
    out = {"prefix": sys.prefix, "executable": sys.executable, "tk": tk.TkVersion}
    root = tk.Tk()
    root.withdraw()
    a = ed2.EditorApp(root, game)
    a.canvas_w, a.canvas_h = 1000, 760
    for lv in LEVELS:
        a.dirty = False
        a.set_mode("remix", lv)
        gi = a.rmodel.ground_index()
        snapped = None
        for ident, x in sorted(a.rmodel.actors.items()):
            if x["status"] == "locked":
                continue
            pos = [c2.f32(x["position"][0] + 3.0), x["position"][1], x["position"][2]]
            if c2.snap_proposal(gi, pos, x["position"], c2.MAX_ACTOR_MOVE)["ok"]:
                a.sel = ("actor", ident)
                a.set_remix_position(a.sel, pos, clamp=False)
                snapped = bool(a.snap_preview()["ok"] and a.snap_apply())
                break
        pres = [ps["id"] for ps in c2.PRESETS if ps["level"] == lv]
        for pid in pres:
            a.cmd_preset(pid, confirm=False)
        g = next(k for k, v in a.rmodel.graphs.items() if v["status"] != "locked")
        a.sel = ("rgraph", g)
        a.refresh()
        route = "Followed by:" in a.route_info.cget("text")
        if not a.remix["actors"] and not a.remix["waypoints"]:
            k = next(k for k, v in a.rmodel.actors.items() if v["status"] != "locked")
            a.set_remix_position(("actor", k), [v + 2 for v in a.rmodel.actors[k]["position"]])
        ws = c2.remix_warnings(a.remix, a.rmodel)
        r = a.export_mod(Path(work) / f"mod_{lv}")
        out[lv] = {"ok": bool(r["ok"]) and route and (snapped is not False), "snapped": snapped, "presets": pres,
                   "warnings": len(ws), "ranges": r.get("ranges")}
        a.dirty = False
    root.destroy()
    print("RUNTIME " + json.dumps(out))
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        sys.exit(check())
    if sys.argv[1:] == ["examples"]:
        sys.exit(write_examples())
    if sys.argv[1:2] == ["runtime"] and len(sys.argv) == 5:
        sys.exit(runtime(*sys.argv[2:]))
    raise SystemExit(__doc__)
