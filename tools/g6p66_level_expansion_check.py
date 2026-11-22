#!/usr/bin/env python3
"""G6-P66 (D-315 / E-552): development-only wood_10 entry of the Experimental 3D Level Viewer / editor.

    python tools/g6p66_level_expansion_check.py --selftest     -> G6P66_SELFTEST PASS n/n   (no game data needed)
    python tools/g6p66_level_expansion_check.py --mutations    -> G6P66_MUTATIONS PASS n/n (selftest on mutated core)
    python tools/g6p66_level_expansion_check.py check          -> G6P66_CHECK PASS n/n     (the person's data, read only)

selftest: the gate (R3HD_DEV_EDITOR_LEVELS), the pinned identity, the narrowed edit class (YAM_mPowerz /
NIK_mChameleon actor positions, no waypoints) and the 5-unit bound, against synthetic projects and a stub level model.
mutations: the selftest must fail on copies of the editor core with one safeguard removed each.
check: the person's own extracted files, read only (hashed before and after); outputs and level copies under
private/work/g6p66 (numbers only). It loads, renders offscreen (never-shown window, one readback), edits, exports,
reopens, installs into an isolated mods folder and compares bytes. No game process: in-game behaviour is NOT
verified here.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
if os.environ.get("G6P66_MUTANT_DIR"):          # --mutations: a mutated copy of the editor core is imported first
    sys.path.insert(0, os.environ["G6P66_MUTANT_DIR"])
import r3hd_mods as rm  # noqa: E402
import r3hd_level_editor_core as core  # noqa: E402

WORK = ROOT / "private" / "work" / "g6p66"
LEVEL = "wood_10"
ENV = core.DEV_LEVELS_ENV
FAKE = "ab" * 32
POWERZ = "YAM_mPowerz"
CHAMELEON = "NIK_mChameleon"
# G6-P63 inventory (editable / all actors; editable / all waypoints) of the supported levels; must not change
INTRO_COUNTS = {"intro_10": (39, 60, 209, 211), "intro_15": (21, 101, 172, 175), "intro_20": (61, 108, 112, 138)}
# wood_10 enumeration recorded by G6-P66 (E-552) from the pinned files
WOOD10_COUNTS = {"actors": 211, "actors_experimental": 7, "actors_locked": 204, "graphs": 37, "waypoints": 265,
                 "waypoints_editable": 0, "triangles": 4954, "meshes": 61}
WOOD10_EDITABLE = [(CHAMELEON, 0), (CHAMELEON, 1), (POWERZ, 0), (POWERZ, 1), (POWERZ, 2), (POWERZ, 3), (POWERZ, 4)]


def tree_hashes(d: Path) -> dict:
    out = {}
    if not d.is_dir():
        return out
    for dp, dn, fn in os.walk(d, followlinks=False):
        dn[:] = [x for x in dn if not os.path.islink(os.path.join(dp, x))]
        for f in fn:
            p = Path(dp) / f
            if not p.is_symlink():
                out[p.relative_to(d).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def refused(fn, code=None):
    try:
        fn()
    except core.EditorError as x:
        return code is None or x.code == code
    return False


def report(results, tag):
    ok = sum(1 for _, v in results if v)
    for k, v in results:
        print(f"{'PASS' if v else 'FAIL'} {k}")
    verdict = "PASS" if ok == len(results) else "FAIL"
    print(f"{tag} {verdict} {ok}/{len(results)}")
    return 0 if verdict == "PASS" else 1


def key(name):
    return f"synthetic\\{name}\\{name}.rul^x"


def wood_project(actors=(), waypoints=()):
    p = core.new_remix(LEVEL)
    p["actors"] = [{"model": key(n), "instance": i, "matrix_sha256": FAKE, "position": list(pos)}
                   for n, i, pos in actors]
    p["waypoints"] = [{"model": key(n), "instance": 0, "variable": 0, "node": 0, "waypoint_sha256": FAKE,
                       "position": list(pos)} for n, pos in waypoints]
    return p


class StubModel:
    """A RemixModel-shaped level with two editable actors (synthetic keys); no game data."""

    def __init__(self, level=LEVEL):
        self.level, self.dev, self.max_actor_move = level, core.is_dev_level(level), core.actor_move_limit(level)
        self.actors = {(key(POWERZ), 0): {"name": POWERZ, "instance": 0, "status": "experimental", "why": "",
                                          "matrix_sha256": FAKE, "position": (0.0, 0.0, 0.0)},
                       (key(CHAMELEON), 1): {"name": CHAMELEON, "instance": 1, "status": "experimental", "why": "",
                                             "matrix_sha256": FAKE, "position": (10.0, 0.0, 0.0)}}
        self.graphs = {}


# ------------------------------------------------------------------------------------------------ selftest
def selftest() -> int:
    R = []
    saved = os.environ.pop(ENV, None)
    try:
        R.append(("S1 wood_10 is not a supported level and is refused while the variable is absent",
                  LEVEL not in core.REMIX_LEVELS and LEVEL not in core.remix_level_names()
                  and refused(lambda: core.new_remix(LEVEL), "UNSUPPORTED")
                  and refused(lambda: core.level_entry(LEVEL), "UNSUPPORTED")))
        R.append(("S2 the variable parses as a comma list and ignores unknown names",
                  core.dev_levels_enabled({ENV: " wood_10 , knaar_30,,"}) == [LEVEL]
                  and core.dev_levels_enabled({ENV: "intro_10"}) == [] and core.dev_levels_enabled({}) == []))
        os.environ[ENV] = LEVEL
        p = wood_project([(POWERZ, 0, (3.0, 0.0, 0.0))])
        q = core.check_remix(p)
        e = core.DEV_LEVELS[LEVEL]
        R.append(("S3 enabled: the project targets the exact pinned lvl / ptr / transit hashes",
                  LEVEL in core.remix_level_names() and q["target"] == {f"{k}_sha256": e[k] for k in
                                                                         ("lvl", "ptr", "transit")}
                  and all(len(e[k]) == 64 for k in ("lvl", "ptr", "transit"))))
        bad = json.loads(json.dumps(p))
        bad["target"]["lvl_sha256"] = FAKE
        R.append(("S4 a project with any other target hash is refused", refused(lambda: core.check_remix(bad),
                                                                                "UNSUPPORTED")))
        R.append(("S5 an actor outside the Powerz / Chameleon class is refused before any game data is read",
                  refused(lambda: core.check_remix(wood_project([("NIK_mGenSound", 0, (1.0, 0.0, 0.0))])),
                          "UNSUPPORTED")))
        R.append(("S6 any waypoint edit on wood_10 is refused",
                  refused(lambda: core.check_remix(wood_project(waypoints=[(POWERZ, (1.0, 0.0, 0.0))])),
                          "UNSUPPORTED")))
        m = StubModel()
        ok = core.check_remix_level(wood_project([(POWERZ, 0, (4.99, 0.0, 0.0)),
                                                  (CHAMELEON, 1, (10.0, 0.0, -5.0))]), m)
        far = core.check_remix_level(wood_project([(POWERZ, 0, (5.01, 0.0, 0.0))]), m)
        R.append(("S7 wood_10 moves of at most 5 units pass; 5.01 is refused (the supported levels keep 25)",
                  ok == [] and len(far) == 1 and "at most 5" in far[0] and core.actor_move_limit(LEVEL) == 5.0
                  and core.actor_move_limit("intro_10") == core.MAX_ACTOR_MOVE == 25.0))
        mp = core.mod_paths()
        man = core.remix_manifest(q, mp)
        td = Path(tempfile.mkdtemp(prefix="g6p66-self-"))
        try:
            (td / "mod").mkdir()
            (td / "mod" / "mod.json").write_bytes(core.manifest_bytes(man))
            kind, back = core.project_from_mod(td / "mod")
            R.append(("S8 an exported wood_10 mod is labelled DEVELOPMENT ONLY and reopens as the same project while "
                      "enabled", kind == "v2" and back == q and "DEVELOPMENT ONLY" in man["description"]
                      and "DEVELOPMENT" not in core.remix_manifest(core.new_remix("intro_10"), mp)["description"]))
            os.environ.pop(ENV)
            R.append(("S9 with the variable absent the same mod and project are refused (reopen, load, validate)",
                      refused(lambda: core.project_from_mod(td / "mod"), "UNSUPPORTED")
                      and refused(lambda: core.check_remix(q), "UNSUPPORTED")
                      and core.validate_remix(q, td / "nogame")["code"] == "UNSUPPORTED"))
        finally:
            shutil.rmtree(td, ignore_errors=True)
        ip = core.new_remix("intro_10")
        R.append(("S10 the supported levels are unaffected: no variable needed, 25-unit bound, waypoints allowed",
                  core.remix_level_names() == ["intro_10", "intro_15", "intro_20"]
                  and core.check_remix(dict(ip, waypoints=[{"model": key("G"), "instance": 0, "variable": 0,
                                                            "node": 0, "waypoint_sha256": FAKE,
                                                            "position": [1.0, 2.0, 3.0]}]))["level"] == "intro_10"))
        os.environ[ENV] = LEVEL
        sm = StubModel()
        cls = core.RemixModel._narrow_dev
        fake = type("M", (), {})()
        fake.level, fake.max_actor_move = LEVEL, 5.0
        fake.actors = {1: {"name": POWERZ, "status": "experimental", "why": "w"},
                       2: {"name": "NIK_mGenSound", "status": "experimental", "why": "w"},
                       3: {"name": CHAMELEON, "status": "locked", "why": "script"}}
        fake.graphs = {1: {"status": "experimental", "why": "g"}, 2: {"status": "locked", "why": "shared"}}
        cls(fake, core.DEV_LEVELS[LEVEL])
        R.append(("S11 the level model keeps Powerz editable, locks other models and every graph, keeps compiler locks",
                  fake.actors[1]["status"] == "experimental" and "DEVELOPMENT ONLY" in fake.actors[1]["why"]
                  and fake.actors[2]["status"] == "locked" and fake.actors[3]["why"] == "script"
                  and all(g["status"] == "locked" for g in fake.graphs.values())
                  and fake.graphs[2]["why"] == "shared" and sm.dev))
    finally:
        os.environ.pop(ENV, None)
        if saved is not None:
            os.environ[ENV] = saved
    return report(R, "G6P66_SELFTEST")


# ------------------------------------------------------------------------------------------------ mutations
MUTATIONS = [
    ("gate ignored", "    if level in DEV_LEVELS and level in dev_levels_enabled():",
     "    if level in DEV_LEVELS:"),
    ("class not narrowed", "            if short_name(a[\"model\"]) not in allowed:", "            if False:"),
    ("waypoints allowed", "        if wps and not entry.get(\"waypoints\"):", "        if False:"),
    ("bound not level-specific", "        elif math.dist(a[\"position\"], x[\"position\"]) > actor_move_limit(p[\"level\"]) + 1e-4:",
     "        elif math.dist(a[\"position\"], x[\"position\"]) > MAX_ACTOR_MOVE + 1e-4:"),
    ("graphs left editable", "                if g[\"status\"] != \"locked\":", "                if False:"),
]


def mutations() -> int:
    R = []
    src = (TOOLS / "r3hd_level_editor_core.py").read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in src else "\n"
    for name, old, new in MUTATIONS:
        old, new = old.replace("\n", nl), new.replace("\n", nl)
        td = Path(tempfile.mkdtemp(prefix="g6p66-mut-"))
        try:
            if src.count(old) != 1:
                R.append((f"M {name}: anchor present once", False))
                continue
            (td / "r3hd_level_editor_core.py").write_bytes(src.replace(old, new).encode("utf-8"))
            env = dict(os.environ, G6P66_MUTANT_DIR=str(td))
            env.pop(ENV, None)
            r = subprocess.run([sys.executable, str(Path(__file__)), "--selftest"], capture_output=True, text=True,
                               env=env, timeout=300)
            caught = r.returncode != 0 and "G6P66_SELFTEST FAIL" in r.stdout
            fails = [ln[5:] for ln in r.stdout.splitlines() if ln.startswith("FAIL ")]
            R.append((f"M {name}: caught by the selftest ({', '.join(f.split(' ')[0] for f in fails) or 'none'})",
                      caught))
        finally:
            shutil.rmtree(td, ignore_errors=True)
    return report(R, "G6P66_MUTATIONS")


# ------------------------------------------------------------------------------------------------ check
def gate_off_probe():
    """In a fresh process without the variable: the editor's level lists and the level model refuse wood_10."""
    code = ("import sys, json; sys.path.insert(0, %r); import r3hd_level_editor_core as c, r3hd_level_editor as e; "
            "import r3hd_scene_view as v\n"
            "try:\n c.RemixModel(c.mod_paths()['game'], 'wood_10'); r = 'opened'\n"
            "except c.EditorError as x:\n r = x.code\n"
            "print(json.dumps({'choices': [x[1] for x in e.CHOICES], 'names': c.remix_level_names(), 'model': r}))"
            % str(TOOLS))
    env = dict(os.environ)
    env.pop(ENV, None)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=300)
    return json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {"error": r.stderr[-400:]}


def scene_digest(game):
    import r3hd_level_scene as ls
    s = ls.Scene(game, LEVEL)
    body = json.dumps([[o["superobject"], len(o["vertices"]), [(e["triangles"], e["texture"], e["mode"])
                                                               for e in o["elements"]]] for o in s.objects],
                      default=str).encode()
    return s, hashlib.sha256(body).hexdigest()


def model_digest(m):
    body = json.dumps([sorted((str(k), a["status"], a["position"], a["matrix_sha256"]) for k, a in m.actors.items()),
                       sorted((str(k), g["status"], [n and n["position"] for n in g["nodes"]])
                              for k, g in m.graphs.items()), len(m.tris)], default=str).encode()
    return hashlib.sha256(body).hexdigest()


def check() -> int:
    os.environ[ENV] = LEVEL
    import tkinter as tk
    import r3hd_level_editor as ed
    import r3hd_level_scene as ls
    import r3hd_scene_gl as sg
    R, det = [], {}
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    game = Path(core.mod_paths()["game"])
    person_mods = Path(core.mod_paths()["mods"])
    watched = {}
    for lv in (LEVEL, "intro_10", "intro_15", "intro_20"):
        lp, pp, _ = rm.script_level_files(game, lv)
        for f in (lp, pp, lp.with_name("transit.lvl"), lp.with_name(f"{lv}_2.bhf")):
            watched[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
    for f in ("fix.lvl", "fix.ptr"):
        watched[str(game / "GAMEDATAbin" / f)] = hashlib.sha256((game / "GAMEDATAbin" / f).read_bytes()).hexdigest()
    mods_before = tree_hashes(person_mods)

    # C1 identity
    lp, pp, _ = rm.script_level_files(game, LEVEL)
    have = {"lvl": watched[str(lp)], "ptr": watched[str(pp)], "transit": watched[str(lp.with_name("transit.lvl"))]}
    pin = {k: core.DEV_LEVELS[LEVEL][k] for k in have}
    det["identity"] = have
    R.append(("C1 the person's wood_10 lvl / ptr / transit equal the pinned identity", have == pin))

    # C2 gate off in a fresh process
    off = gate_off_probe()
    det["gate_off"] = off
    R.append(("C2 without R3HD_DEV_EDITOR_LEVELS the editor offers only the three supported levels and refuses to "
              "open wood_10", off.get("names") == ["intro_10", "intro_15", "intro_20"]
              and LEVEL not in off.get("choices", [LEVEL]) and off.get("model") == "UNSUPPORTED"))

    # C3 deterministic loading and enumeration
    s1, d1 = scene_digest(game)
    s2, d2 = scene_digest(game)
    m1, m2 = core.RemixModel(game, LEVEL), core.RemixModel(game, LEVEL)
    tex_ok = 0
    for k in s1.textures:
        try:
            w, h, px = s1.decode_texture(k, max_side=32)
            tex_ok += 1 if len(px) == w * h * 4 else 0
        except ls.SceneError:
            pass
    sm = s1.summary()
    det["scene"] = {k: sm[k] for k in ("objects", "elements", "triangles", "textured_triangles", "skipped", "modes")}
    det["scene"]["textures"], det["scene"]["textures_decoded"], det["scene"]["digest"] = len(s1.textures), tex_ok, d1
    R.append(("C3 two scene loads give the same objects, elements and textures; every texture decodes",
              d1 == d2 and tex_ok == len(s1.textures) > 0 and sm["triangles"] > 0))
    c = m1.counts()
    det["counts"] = c
    editable = sorted((a["name"], a["instance"]) for a in m1.actors.values() if a["status"] not in ("locked",
                                                                                                     "script_overridden"))
    R.append(("C4 two level models enumerate the same actors / graphs / collision; counts as recorded "
              f"({c['actors']} actors, {c['actors_experimental']} editable, {c['graphs']} graphs read-only)",
              model_digest(m1) == model_digest(m2) and {k: c[k] for k in WOOD10_COUNTS} == WOOD10_COUNTS
              and editable == WOOD10_EDITABLE and c["actors_verified"] == c["actors_placement"] == 0
              and all(g["status"] == "locked" for g in m1.graphs.values())))

    # C5 offscreen render (Tier A): never-shown window, one readback, private picture
    shots = [sg.render_test(game, LEVEL, WORK / f"wood_10_overview_{k}.png", markers=True, frames=5) for k in (1, 2)]
    rt = shots[0]
    pngs = [hashlib.sha256(Path(r_["out"]).read_bytes()).hexdigest() for r_ in shots]
    det["render"] = {k: rt[k] for k in ("window_visible", "readbacks", "gl_error", "covered_share_sampled",
                                        "distinct_colours_sampled", "first_frame_ms", "roles")}
    det["render"]["png_sha256"] = [h[:16] for h in pngs]
    # first written as covered > 0.3 (an unmeasured guess; the overview covers 0.257); revised before commit to the
    # G6-P37 T5 / T7 criteria (reproducible, offscreen-safe) plus a non-empty, textured frame
    R.append(("C5 the 3D renderer draws wood_10 offscreen: no visible window, one readback each, no GL error; two "
              "renders are byte-identical; the frame is non-empty and textured",
              all(r_["window_visible"] is False and r_["readbacks"] == 1 and not r_["gl_error"] for r_ in shots)
              and pngs[0] == pngs[1] and rt["covered_share_sampled"] > 0.1 and rt["distinct_colours_sampled"] > 500))

    def paths(tag):
        return {"home": core.mod_paths()["home"], "game": game, "mods": WORK / tag / "mods",
                "cache": WORK / tag / "cache"}

    root = tk.Tk()
    root.withdraw()
    try:
        a = ed.EditorApp(root, game)
        a.canvas_w, a.canvas_h = 1000, 760
        R.append(("C6 with the variable the level list offers wood_10 marked DEVELOPMENT ONLY",
                  any(ch[1] == LEVEL and "DEVELOPMENT ONLY" in ch[2] for ch in ed.CHOICES)))
        a.set_mode("remix", LEVEL)
        pk = (next(k for k, v in a.rmodel.actors.items() if v["name"] == POWERZ and v["instance"] == 0))
        ck = (next(k for k, v in a.rmodel.actors.items() if v["name"] == CHAMELEON and v["instance"] == 0))
        p0, c0 = a.rmodel.actors[pk]["position"], a.rmodel.actors[ck]["position"]
        a.set_remix_position(("actor", pk), [p0[0] + 3.0, p0[1], p0[2]])
        a.set_remix_position(("actor", ck), [c0[0] + 3.0, c0[1], c0[2]])
        proj = json.loads(json.dumps(a.remix))
        e1, e2 = a.export_mod(WORK / "w_a"), a.export_mod(WORK / "w_b")
        b1, b2 = (WORK / "w_a" / "mod.json").read_bytes(), (WORK / "w_b" / "mod.json").read_bytes()
        v = rm.cmd_validate(paths("validate"), WORK / "w_a")
        val = core.validate_remix(proj, game, model=a.rmodel)
        rl = val.get("range_list", [])
        ix = a.rmodel.ix
        want = sorted([("wood_10.lvl", ix["placements"][k][0]["matrix"] + 0x34) for k in (pk[0], ck[0])]
                      + [("wood_10.lvl", ix["placements"][k][0]["snapshot"] + 0x34) for k in (pk[0], ck[0])])
        det["export"] = {"mod_json_sha256": hashlib.sha256(b1).hexdigest(), "ranges": e1.get("ranges"),
                         "range_offsets": sorted((f, o) for f, o, _, _ in rl),
                         "edits": [[core.short_name(x["model"]), x["instance"], x["position"]] for x in proj["actors"]],
                         "originals": {"powerz0": p0, "chameleon0": c0}}
        R.append(("C7 Powerz #0 and Chameleon #0 moved 3 units export twice to identical bytes; the mod manager "
                  "validates 4 same-size ranges at the two matrices and snapshots",
                  e1["ok"] and e2["ok"] and b1 == b2 and v["ranges"] == 4 == e1["ranges"]
                  and val["text"].startswith("DEVELOPMENT ONLY") and "DEVELOPMENT ONLY" in json.loads(b1)["description"]
                  and sorted((f, o) for f, o, _, _ in rl) == want and all(len(bytes.fromhex(d)) == 12
                                                                             for _, _, d, _ in rl)))
        # C8 byte preservation: applying the ranges to a copy changes only those 48 bytes
        orig = lp.read_bytes()
        img = bytearray(orig)
        for _, o, d, _ in rl:
            img[o:o + 12] = bytes.fromhex(d)
        diff = [i for i in range(len(orig)) if img[i] != orig[i]]
        inside = all(any(o <= i < o + 12 for _, o, _, _ in rl) for i in diff)
        R.append(("C8 the mod changes only bytes inside its 4 ranges of wood_10.lvl (same size; ptr, transit, "
                  f"bundles untouched; {len(diff)} bytes differ)", inside and 0 < len(diff) <= 48
                  and len(img) == len(orig) and all(Path(f).name == "wood_10.lvl" for f, _, _, _ in rl)))
        opened = a.open_project(WORK / "w_a" / "mod.json")
        e3 = a.export_mod(WORK / "w_c")
        R.append(("C9 the exported mod reopens as the same project and re-exports to the same bytes",
                  opened and a.remix == proj and a.path is None and e3["ok"]
                  and (WORK / "w_c" / "mod.json").read_bytes() == b1))
        # refusals, nothing written
        far = json.loads(json.dumps(proj))
        far["actors"][0]["position"][0] += 2.5          # 5.5 units from the original
        rf = core.validate_remix(far, game, WORK / "far", model=a.rmodel)
        gen = next(v_ for v_ in a.rmodel.actors.values() if v_["name"] == "NIK_mGenSound")
        other = json.loads(json.dumps(proj))
        other["actors"] = [{"model": gen["key"], "instance": gen["instance"], "matrix_sha256": gen["matrix_sha256"],
                            "position": [gen["position"][0] + 1.0, gen["position"][1], gen["position"][2]]}]
        ro = core.validate_remix(other, game, WORK / "other", model=a.rmodel)
        gk, g = next(iter(sorted(a.rmodel.graphs.items())))
        nd = next(n for n in g["nodes"] if n)
        wp = json.loads(json.dumps(proj))
        wp["waypoints"] = [{"model": gk[0], "instance": gk[1], "variable": gk[2], "node": nd["node"],
                            "waypoint_sha256": FAKE, "position": [nd["position"][0] + 1.0, nd["position"][1],
                                                                  nd["position"][2]]}]
        rw = core.validate_remix(wp, game, WORK / "wp", model=a.rmodel)
        det["refusals"] = {"far": rf.get("detail"), "other": ro.get("detail"), "waypoint": rw.get("detail")}
        R.append(("C10 refused and nothing written: a 5.5-unit move, a compiler-accepted actor outside the class "
                  "(NIK_mGenSound), a waypoint edit",
                  not rf["ok"] and not ro["ok"] and not rw["ok"]
                  and not any((WORK / d).exists() for d in ("far", "other", "wp"))))
        # changed source files: a private copy with one byte flipped
        fake_game = WORK / "tampered"
        dst = fake_game / "GAMEDATAbin" / LEVEL
        dst.mkdir(parents=True)
        for f in (lp, pp, lp.with_name("transit.lvl")):
            shutil.copyfile(f, dst / f.name)
        b = bytearray((dst / lp.name).read_bytes())
        b[len(b) // 2] ^= 0x01
        (dst / lp.name).write_bytes(bytes(b))
        R.append(("C11 a level copy that differs by one byte is refused (TARGET_CHANGED)",
                  refused(lambda: core.RemixModel(fake_game, LEVEL), "TARGET_CHANGED")))
        shutil.rmtree(fake_game)

        # install, conflict and identical re-import in an isolated mods folder
        p = paths("install")
        imp = a.import_mod(WORK / "w_a", p)
        res = rm.resolve_all(p)
        R.append(("C12 the wood_10 mod imports + enables in an isolated mods folder; the plan applies it as a gameplay "
                  "mod with 4 ranges", imp["ok"] and len(res["active"]) == 1 and res["gameplay_active"] == res["active"]
                  and res["ranges"] == 4))
        mid = imp["result"]["id"]
        a.set_mode("remix", LEVEL)
        a.set_remix_position(("actor", pk), [p0[0], p0[1] + 2.0, p0[2]])
        a.set_meta("id", mid)
        a.export_mod(WORK / "w_other")
        before = tree_hashes(p["mods"])
        r = a.import_mod_asking(WORK / "w_other", root, p)
        R.append(("C13 a different wood_10 mod with the same id is refused (EXISTS) without a dialog; nothing "
                  "changes", not r["ok"] and r["code"] == "EXISTS" and tree_hashes(p["mods"]) == before))
        order = [(e["id"], e["enabled"]) for e in rm.load_state(p)["mods"]]
        r = a.import_mod(WORK / "w_a", p)
        R.append(("C14 re-importing the identical package is not a replacement (installed mod.json, order and "
                  "enabled state unchanged)",
                  r["ok"] and r["result"].get("unchanged") and tree_hashes(p["mods"]).get(f"installed/{mid}/mod.json")
                  == before.get(f"installed/{mid}/mod.json") == hashlib.sha256(b1).hexdigest()
                  and [(e["id"], e["enabled"]) for e in rm.load_state(p)["mods"]] == order))

        # the supported levels keep their behaviour
        got = {}
        for lv in INTRO_COUNTS:
            a.set_mode("remix", lv)
            cc = a.rmodel.counts()
            got[lv] = (cc["actors_verified"] + cc["actors_placement"] + cc["actors_experimental"], cc["actors"],
                       cc["waypoints_editable"], cc["waypoints"])
        det["intro_counts"] = got
        R.append(("C15 intro_10 / intro_15 / intro_20 keep the G6-P63 editable counts and the 25-unit bound",
                  got == INTRO_COUNTS and all(core.actor_move_limit(lv) == 25.0 for lv in INTRO_COUNTS)))

        # the 3D window (withdrawn) opens wood_10 and shows the development bound
        import r3hd_scene_view as sv
        root3 = tk.Tk()
        root3.withdraw()
        try:
            app3, view = sv.open_editor(root3, game, level=LEVEL, show=False)
            info = view.item_info(("actor", pk))
            locked = view.item_info(("actor", next(k for k, v_ in app3.rmodel.actors.items()
                                                   if v_["name"] == "NIK_mGenSound")))
            det["view_info"] = [info[1], info[3], info[4], locked[1], locked[3]]
            R.append(("C16 3D viewer (withdrawn): wood_10 opens; Powerz is editable with a 5-unit development limit; "
                      "other actors are view only", app3.remix["level"] == LEVEL and info[3] and "5 units" in info[4]
                      and "development" in info[4] and locked[1] == "locked" and not locked[3]))
            view.close(ask=False)
        finally:
            try:
                root3.destroy()
            except tk.TclError:
                pass
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass

    after = {k: hashlib.sha256(Path(k).read_bytes()).hexdigest() for k in watched}
    R.append(("C17 the person's level, bundle and fix files are byte-identical before and after", after == watched))
    R.append(("C18 the person's own mods folder is untouched", tree_hashes(person_mods) == mods_before))
    (WORK / "details.json").write_text(json.dumps(det, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(det, indent=1, default=str))
    return report(R, "G6P66_CHECK")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", nargs="?", choices=["check"])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutations", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.mutations:
        return mutations()
    if a.mode == "check":
        return check()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
