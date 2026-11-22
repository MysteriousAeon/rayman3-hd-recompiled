#!/usr/bin/env python3
"""G6-P68 (D-317 / E-554): read-only level browsing in the Experimental 3D Level Viewer.

    python tools/g6p68_view_catalog_check.py measure       -> tools/r3hd_view_levels.json + private/work/g6p68/measure.json
    python tools/g6p68_view_catalog_check.py --selftest    -> G6P68_SELFTEST PASS n/n   (no game data needed)
    python tools/g6p68_view_catalog_check.py --mutations   -> G6P68_MUTATIONS PASS n/n (selftest on mutated copies)
    python tools/g6p68_view_catalog_check.py check         -> G6P68_CHECK PASS n/n     (the person's data, read only)

measure: every level folder of the person's extracted game, in one process: exact lvl / ptr / transit SHA-256, the
static scene, every texture at the viewer's size, the never-editable ViewModel, and the viewer's own Renderer in one
never-shown offscreen context (no readback): build time, five timed frames, GL error, bridge handles before and after
close, process memory. Writes the tracked catalog (hashes, counts, limits; no game content) and private timings.
check: the catalog against the files, all catalogued levels switched through the real 3D window (withdrawn, offscreen
context, no readback), read-only enforcement, the intro and wood_10 workflows, missing / damaged files, memory and
bridge cleanup, the packed-tail texture evidence, and at most six offscreen readbacks to private PNGs. Game files are
only read (hashed and stat'ed before and after). No game process. Pictures are NOT proof of visual fidelity.
"""
import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
if os.environ.get("G6P68_MUTANT_DIR"):          # --mutations: mutated copies are imported first
    sys.path.insert(0, os.environ["G6P68_MUTANT_DIR"])
sys.path.insert(1 if os.environ.get("G6P68_MUTANT_DIR") else 0, str(TOOLS))
import r3hd_mods as rm  # noqa: E402
import r3hd_level_editor_core as core  # noqa: E402

WORK = ROOT / "private" / "work" / "g6p68"
MIN_TRIANGLES = 100          # below this a level file is a 2D page (menu / text / credits), not a 3D scene
FRAMES = 5
INTRO_COUNTS = {"intro_10": (39, 60, 209, 211), "intro_15": (21, 101, 172, 175), "intro_20": (61, 108, 112, 138)}
PACKED = {"sk8_00": "templeptz\\ptz_sk8_special.tga", "sk8_10": "templeptz\\ptz_sk8_special.tga",
          "sk8_20": "templeptz\\ptz_sk8_special.tga", "ten_map": "sfx\\white.tga"}
READBACK_LEVELS = ("wood_11", "sk8_00", "ten_map", "swamp_50", "knaar_69")   # + one repeat: six readbacks


# ------------------------------------------------------------------------------------------------ helpers
def report(results, tag):
    ok = sum(1 for _, v in results if v)
    for k, v in results:
        print(f"{'PASS' if v else 'FAIL'} {k}")
    verdict = "PASS" if ok == len(results) else "FAIL"
    print(f"{tag} {verdict} {ok}/{len(results)}")
    return 0 if verdict == "PASS" else 1


def memory_mb():
    """(working set, peak working set, private commit) of this process in MiB (Windows), or Nones."""
    try:
        from ctypes import wintypes as wt

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [
                (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                               "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                               "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        k32.GetCurrentProcess.restype = wt.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return None, None, None
        mb = 1024 * 1024
        return round(c.WorkingSetSize / mb, 1), round(c.PeakWorkingSetSize / mb, 1), round(c.PagefileUsage / mb, 1)
    except (OSError, AttributeError):
        return None, None, None


def level_names(game):
    g = Path(game) / "GAMEDATAbin"
    return sorted(p.name for p in g.iterdir() if p.is_dir() and (p / f"{p.name}.lvl").is_file())


def level_hashes(game, lv):
    lp, pp, _ = rm.script_level_files(Path(game), lv)
    tp = lp.with_name("transit.lvl")
    return {"lvl": rm.sha256_bytes(lp.read_bytes()), "ptr": rm.sha256_bytes(pp.read_bytes()),
            "transit": rm.sha256_bytes(tp.read_bytes()) if tp.is_file() else None}


def tree_stat(d: Path) -> dict:
    """{relative path: (size, mtime_ns)} of every regular file below d; junctions and links are not followed."""
    out = {}
    for dp, dn, fn in os.walk(d, followlinks=False):
        dn[:] = [x for x in dn if not os.path.islink(os.path.join(dp, x)) and not _junction(os.path.join(dp, x))]
        for f in fn:
            p = Path(dp) / f
            if not p.is_symlink():
                s = p.stat()
                out[p.relative_to(d).as_posix()] = (s.st_size, s.st_mtime_ns)
    return out


def _junction(path):
    try:
        return bool(os.lstat(path).st_file_attributes & 0x400)     # FILE_ATTRIBUTE_REPARSE_POINT
    except (OSError, AttributeError):
        return False


def bridge_live(r):
    """(textures, batches) the renderer itself holds in the bridge."""
    return (sum(1 for t in r.tex_ids.values() if t), len(r.batches) + (1 if r.collision else 0))


def limits_of(summary, rstats, model_err, packed):
    lim = ["draw modes traced on intro_15 only (E-527); the same byte table is applied here, unverified"]
    if summary["modes"].get("blend"):
        lim.append("blend mode 0x03 is an approximation (never seen in a traced draw)")
    lim.append("sky / backdrop roles and runtime-placed objects are a labelled heuristic (G6-P38)")
    if rstats["texture_errors"]:
        lim.append(f"{len(rstats['texture_errors'])} texture(s) not shown (drawn untextured)")
    if packed:
        lim.append(f"{packed} 16x16 packed-tail texture(s) decoded by the G6-P68 rule (E-554)")
    sk = sum(summary["skipped"].values())
    if sk:
        lim.append(f"{sk} scene link(s) skipped, never guessed")
    if model_err:
        lim.append(f"objects and routes not readable ({model_err})")
    return lim


# ------------------------------------------------------------------------------------------------ measure
def measure() -> int:
    import r3hd_level_scene as ls
    import r3hd_scene_gl as sg
    game = Path(core.mod_paths()["game"])
    levels = level_names(game)
    stats_before = tree_stat(game / "GAMEDATAbin")
    ctx = sg.Context(offscreen=(640, 360))
    cat, det = {}, {"levels": {}, "memory_start": memory_mb(), "gl": ctx.info}
    try:
        for lv in levels:
            d = {}
            t0 = time.perf_counter()
            hashes = level_hashes(game, lv)
            try:
                scene = ls.Scene(game, lv)
            except ls.SceneError as x:
                cat[lv] = dict(hashes, **{"class": "excluded", "reason": f"scene not readable ({x.code})",
                                          "measured": {}, "limits": []})
                det["levels"][lv] = {"error": x.code}
                continue
            t_scene = time.perf_counter() - t0
            try:
                model, merr = core.ViewModel(game, lv), None
                scene.classify([p for t in model.tris for p in t] + [a["position"] for a in model.actors.values()])
            except core.EditorError as x:
                model, merr = None, x.code
            t_model = time.perf_counter() - t0 - t_scene
            ctx.current()
            t1 = time.perf_counter()
            r = sg.Renderer(ctx, scene)
            if model:
                r.set_collision(model.tris)
            t_build = time.perf_counter() - t1
            cam = sg.Camera()
            cam.fit(*scene.view_bounds())
            times = []
            for _ in range(FRAMES):
                cam.orbit(4.0, 0.0)
                ts = time.perf_counter()
                r.draw(cam, 640, 360)
                ctx.finish()
                times.append((time.perf_counter() - ts) * 1000)
            err = ctx.n.error()
            live = bridge_live(r)
            info = ctx.n.info()
            sm = scene.summary()
            packed = sum(1 for t in scene.textures.values() if t["width"] <= 16 and t["height"] <= 16)
            rstats = dict(r.stats)
            decoded = rstats["textures"] + sum(1 for k in scene.textures if k not in r.tex_ids and _decodes(scene, k))
            r.close()
            after = ctx.n.info()
            mem = memory_mb()
            ok = sm["triangles"] >= MIN_TRIANGLES and r.stats["batches"] > 0 and not err
            reason = ("" if ok else f"{sm['triangles']} triangle(s): a 2D page, not a 3D scene"
                      if sm["triangles"] < MIN_TRIANGLES else f"renderer: batches {rstats['batches']}, GL error {err}")
            c = model.counts() if model else {}
            cat[lv] = dict(hashes, **{
                "class": "view" if ok else "excluded", "reason": reason,
                "measured": {"objects": sm["objects"], "triangles": sm["triangles"], "textures": len(scene.textures),
                             "textures_shown": rstats["textures"], "textures_decoded": decoded,
                             "actors": c.get("actors"),
                             "graphs": c.get("graphs"), "waypoints": c.get("waypoints"),
                             "collision_triangles": c.get("triangles"),
                             "hidden_runtime_placed": rstats["hidden_runtime_placed"]},
                "limits": limits_of(sm, rstats, merr, packed)})
            d.update(scene_s=round(t_scene, 3), model_s=round(t_model, 3), build_s=round(t_build, 3),
                     load_s=round(t_scene + t_model + t_build, 3),
                     frame_ms_median=round(sorted(times)[len(times) // 2], 2), frame_ms_max=round(max(times), 2),
                     gl_error=err, bridge_live_match=(info["textures"], info["batches"]) == live,
                     bridge_after_close={k: after[k] for k in ("textures", "batches", "bytes")},
                     bridge_bytes=info["bytes"], texels=rstats["texels"], memory=mem,
                     texture_errors=len(rstats["texture_errors"]))
            det["levels"][lv] = d
            print(lv, cat[lv]["class"], json.dumps(d), flush=True)
            del scene, model, r
    finally:
        info = ctx.n.info()
        det["readbacks"], det["window_visible"] = info["readbacks"], info["window_visible"]
        ctx.close()
    det["memory_end"] = memory_mb()
    det["game_tree_unchanged"] = tree_stat(game / "GAMEDATAbin") == stats_before
    body = {"format": core.VIEW_CATALOG_FORMAT,
            "note": "G6-P68 (D-317 / E-554): measured by tools/g6p68_view_catalog_check.py measure on the person's "
                    "extracted Xbox 360 HD files; hashes and counts only. 'view' = the 3D viewer may show it read "
                    "only; editable levels are never offered as view-only.",
            "min_triangles": MIN_TRIANGLES, "levels": cat}
    core.VIEW_CATALOG_FILE.write_bytes((json.dumps(body, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "measure.json").write_text(json.dumps(det, indent=1, default=str) + "\n", encoding="utf-8")
    nv = sum(1 for e in cat.values() if e["class"] == "view")
    print(f"G6P68_MEASURE levels {len(cat)} view {nv} excluded {len(cat) - nv}; readbacks {det['readbacks']}; "
          f"game tree unchanged {det['game_tree_unchanged']}")
    return 0 if det["game_tree_unchanged"] and det["readbacks"] == 0 else 1


# ------------------------------------------------------------------------------------------------ selftest
class StubApp:
    """The parts of EditorApp the 3D window reads, with every editing entry point counted."""

    def __init__(self, root):
        self.root, self.game_dir = root, Path(tempfile.gettempdir())
        self.mode, self.remix = "remix", {"level": "intro_15"}
        self.sel, self.rmodel, self.model, self.undo, self.dirty, self.path = None, None, None, [], True, None
        self.calls = []
        self.project = {"region": core.REGIONS[0], "terrain": {}}
        self.status_var = type("V", (), {"get": staticmethod(lambda: "")})()

    def refresh(self, redraw=True):
        pass

    def flash(self, text, error=False):
        pass

    def current_choice(self):
        return ("remix", "intro_15", "intro_15 - actor and waypoint remix")

    def __getattr__(self, name):                      # any other editor method is an edit attempt: counted
        if name.startswith("_"):
            raise AttributeError(name)

        def f(*a, **k):
            self.calls.append(name)
            return True
        return f


def synthetic_level(game_dir, level):
    """G6-P69: r3hd_level_scene's synthetic one-object level (no game data) as `level`, with an empty fix file."""
    import struct
    import r3hd_level_scene as ls
    lvl, ptr = ls._synthetic_files()
    g = Path(game_dir) / "GAMEDATAbin"
    (g / level).mkdir(parents=True, exist_ok=True)
    (g / level / f"{level}.lvl").write_bytes(lvl)
    (g / level / f"{level}.ptr").write_bytes(ptr)
    (g / "fix.lvl").write_bytes(b"\0" * 8)
    (g / "fix.ptr").write_bytes(struct.pack(">I", 0))


class StubView(core.RemixModel):
    """A ViewModel-shaped level without game data (core.ViewModel's own locking applied)."""
    view_only = True

    def __init__(self, game_dir, level):
        self.level, self.game, self.dev, self.max_actor_move, self.tris, self.meshes = level, game_dir, False, 0.0, [], 0
        self.hashes = {"lvl": "0" * 64, "ptr": "0" * 64, "transit": None}
        self.actors = {("k\\A_mThing\\x", 0): {"key": "k\\A_mThing\\x", "name": "A_mThing", "instance": 0,
                                                "position": (1.0, 2.0, 3.0), "status": "experimental", "why": "w",
                                                "matrix_sha256": "ab" * 32}}
        self.graphs = {("k\\A_mThing\\x", 0, 0): {"key": "k", "name": "A_mThing", "instance": 0, "variable": 0,
                                                   "nodes": [{"node": 0, "position": (0.0, 0.0, 0.0), "why": "",
                                                              "waypoint_sha256": "cd" * 32}],
                                                   "edges": [], "graph_offset": 0, "status": "experimental",
                                                   "why": ""}}
        core.ViewModel._lock_all(self)


def selftest() -> int:
    import r3hd_level_scene as ls
    R = []
    td = Path(tempfile.mkdtemp(prefix="g6p68-st-"))
    try:
        # S1 catalog loader: a valid file, and every malformed variant refused to an empty or filtered catalog
        good = {"lvl": "a" * 64, "ptr": "b" * 64, "transit": None, "class": "view", "reason": "", "measured": {},
                "limits": []}
        f = td / "c.json"
        f.write_text(json.dumps({"format": core.VIEW_CATALOG_FORMAT, "levels": {
            "abc_10": good, "../x": good, "ABC": good, "def_20": dict(good, extra=1), "ghi_30": dict(good, lvl="x"),
            "jkl_40": dict(good, **{"class": "edit"}), "mno_50": dict(good, **{"class": "excluded"})}}))
        cat = core.load_view_catalog(f)
        R.append(("S1 catalog: only well-formed entries with a safe level name are kept",
                  sorted(cat) == ["abc_10", "mno_50"]))
        bad = []
        for i, text in enumerate(("{", "[]", json.dumps({"format": "other", "levels": {"abc_10": good}}),
                                  json.dumps({"format": core.VIEW_CATALOG_FORMAT, "levels": []}))):
            (td / f"b{i}.json").write_text(text)
            bad.append(core.load_view_catalog(td / f"b{i}.json"))
        R.append(("S2 catalog: malformed, foreign or absent files give an empty catalog, never an error",
                  bad == [{}, {}, {}, {}] and core.load_view_catalog(td / "absent.json") == {}))

        # S3 offered view-only levels never include an editable level, with or without the development variable
        cat2 = {lv: dict(good) for lv in ("intro_10", "intro_15", "intro_20", "wood_10", "wood_11")}
        cat2["menu_00"] = dict(good, **{"class": "excluded"})
        env0 = os.environ.pop(core.DEV_LEVELS_ENV, None)
        try:
            off = core.view_level_names(cat2)
            os.environ[core.DEV_LEVELS_ENV] = "wood_10"
            on = core.view_level_names(cat2)
        finally:
            os.environ.pop(core.DEV_LEVELS_ENV, None)
            if env0 is not None:
                os.environ[core.DEV_LEVELS_ENV] = env0
        R.append(("S3 view-only list: intros never; wood_10 only while its development gate is off; excluded never",
                  off == ["wood_10", "wood_11"] and on == ["wood_11"]))

        # S4 ViewModel: bad names refused before any file; every item locked, the compiler verdict kept
        refused = []
        for name in ("../intro_10", "Intro_10", "", "a" * 40, "x/y", None):
            try:
                core.ViewModel(td, name)
                refused.append(False)
            except core.EditorError as x:
                refused.append(x.code == "UNSUPPORTED")
        sm = StubView(td, "abc_10")
        a = next(iter(sm.actors.values()))
        g = next(iter(sm.graphs.values()))
        R.append(("S4 ViewModel refuses unsafe level names; locks every actor and graph, keeps compiler_status",
                  all(refused) and a["status"] == g["status"] == "locked" and a["compiler_status"] == "experimental"
                  and "view only" in a["why"] and sm.identity == "uncatalogued"))

        # S5 a view-only model never validates an edit
        p = core.new_remix("intro_15")
        sm.level = "intro_15"
        probs = core.check_remix_level(p, sm)
        try:
            core.new_remix("abc_10")
            nr = False
        except core.EditorError as x:
            nr = x.code == "UNSUPPORTED"
        R.append(("S5 check_remix_level refuses a view-only model; a view-only level cannot start a project",
                  bool(probs) and "view only" in probs[0] and nr))

        # S6 packed-tail base: only the evidenced 16 x 16 shape is accepted
        R.append(("S6 packed-base page size: 16x16 DXT5 16384, DXT1 8192; every other shape unsupported",
                  ls.packed_base_tile(16, 16, "DXT5") == 16384 and ls.packed_base_tile(16, 16, "DXT1") == 8192
                  and all(ls.packed_base_tile(w, h, f_) is None for w, h, f_ in
                          ((8, 8, "DXT1"), (16, 8, "DXT5"), (32, 32, "DXT1"), (16, 16, "DXN")))))

        # S7 synthetic packed page: one solid colour block grid at the SDK offset, noise everywhere else
        def dxt1(c565):
            return c565.to_bytes(2, "little") * 2 + b"\0\0\0\0"            # both endpoints = colour, indices 0
        pitch = 256
        page = bytearray(hashlib.sha256(str(i).encode()).digest()[i % 32] for i in range(8192))
        x, y = rm.packed_mip_offset(16, 16, 0)
        for j in range(4):
            for i in range(4):
                o = (y // 4 + j) * pitch + (x // 4 + i) * 8
                page[o:o + 8] = dxt1(0xF800)                               # pure red
        btf = td / "t.btf"
        btf.write_bytes(b"\0" * 64 + rm.swap16(bytes(page)))
        w, h, px = ls.Scene._decode_packed_base(btf.with_suffix(".bhf"), ("x", 8192, 64, 0, 0), 16, 16, "DXT1")
        cols = {px[k:k + 4] for k in range(0, len(px), 4)}
        shifted = bytearray(page)
        for j in range(4):
            o = (y // 4 + j) * pitch + (x // 4) * 8
            shifted[o:o + 8] = b"\x1f\x00\x1f\x00\0\0\0\0"                 # blue in one column only
        btf.write_bytes(b"\0" * 64 + rm.swap16(bytes(shifted)))
        _, _, px2 = ls.Scene._decode_packed_base(btf.with_suffix(".bhf"), ("x", 8192, 64, 0, 0), 16, 16, "DXT1")
        R.append(("S7 synthetic packed page: the base is read at the SDK offset (all red), and a change there shows",
                  (w, h) == (16, 16) and cols == {bytes((255, 0, 0, 255))} and px2 != px))

        # S8-S11 the 3D window's view-only mode (withdrawn window, no GL, stub editor)
        import tkinter as tk
        mut = os.environ.get("G6P68_MUTANT_DIR")
        if mut:                                       # imported modules put tools/ first again; the mutant wins
            sys.path.insert(0, mut)
        import r3hd_scene_view as sv
        if mut and (TOOLS / "r3hd_scene_view.py").read_bytes() != Path(sv.__file__).read_bytes() \
                and Path(sv.__file__).parent != Path(mut):
            raise SystemExit("mutant harness: r3hd_scene_view was not imported from the mutant folder")
        root = tk.Tk()
        root.withdraw()
        orig_vm, orig_fd = core.ViewModel, sv.filedialog
        dialogs = []

        class FD:
            def __getattr__(self, n):
                return lambda *a, **k: dialogs.append(n) or ""
        try:
            core.ViewModel, sv.filedialog = StubView, FD()
            app = StubApp(root)
            # G6-P69 (D-318): a view-only level is entered once its scene has been read on the loader thread, so a
            # synthetic one-object level (r3hd_level_scene's own fixture) stands in for the person's files
            synthetic_level(td, "abc_10")
            app.game_dir = td
            top = tk.Toplevel(root)
            top.withdraw()
            v = sv.Editor3D(app, top)
            v.view_levels = ["abc_10"]
            v.choose_level(sv.view_label("abc_10"))
            v.finish_pending(60)
            disabled = all(str(b.cget("state")) == "disabled" for b in v.cmd_btns.values())
            terr = str(v.tool_btns["terrain"].cget("state")) == "disabled"
            objs = str(v.tool_btns["objects"].cget("state")) == "normal"
            R.append(("S8 choosing a view-only level: VIEW ONLY shown; Open / Save / Validate / Export / Import / "
                      "Classic 2D disabled; Terrain disabled; Objects available to inspect",
                      v.view is not None and v.level_key() == ("view", "abc_10") and disabled and terr and objs
                      and "VIEW ONLY" in v.cap_lbl.cget("text") and "VIEW ONLY" in top.title()))
            ident = next(iter(v.view["model"].actors))
            v.select(("actor", ident))
            info = v.item_info(("actor", ident))
            v.pick = lambda x_, y_, radius=12: ("actor", ident)
            ev = type("E", (), {"x": 5, "y": 5, "state": 0})()
            v.on_press(ev)
            v.drag["moved"] = True
            v.on_drag(type("E", (), {"x": 50, "y": 60, "state": 0})())
            R.append(("S9 a view-only selection is the window's own; it is not editable and a drag never makes a "
                      "preview", v.vsel == ("actor", ident) and app.sel is None and info[3] is False
                      and info[1] == "view" and v.preview is None and v.drag["kind"] == "orbit"))
            for fn in (v.apply, v.revert, v.undo, v.save, v.validate, v.export, v.import_mod, v.open, v.show_2d):
                fn()
            R.append(("S10 Apply / Revert / Undo / Save / Validate / Export / Import / Open / Classic 2D are refused: "
                      "no editor call, no file dialog", app.calls == [] and dialogs == []
                      and "VIEW ONLY" in v.status_bar.cget("text")))
            v.choose_level(app.current_choice()[2])
            enabled = all(str(b.cget("state")) == "normal" for b in v.cmd_btns.values())
            R.append(("S11 choosing the editor's level again leaves view-only mode with the project kept and the "
                      "commands enabled", v.view is None and v.vsel is None and enabled and app.dirty
                      and v.level_key() == ("remix", "intro_15") and "EDITABLE" in v.cap_lbl.cget("text")))
            v.close(ask=False)
        finally:
            core.ViewModel, sv.filedialog = orig_vm, orig_fd
            try:
                root.destroy()
            except tk.TclError:
                pass
    finally:
        shutil.rmtree(td, ignore_errors=True)
    return report(R, "G6P68_SELFTEST")


def mutations() -> int:
    """The selftest must fail on copies with one safeguard removed each."""
    muts = {
        "M1 refusals removed": ("r3hd_scene_view.py", "        if not self.view:\n            return False\n",
                                "        return False\n"),
        "M2 commands left enabled": ("r3hd_scene_view.py", "            for b in self.cmd_btns.values():\n"
                                     "                b.config(state=\"disabled\")\n",
                                     "            for b in self.cmd_btns.values():\n"
                                     "                b.config(state=\"normal\")\n"),
        "M3 editable levels offered as view-only": ("r3hd_level_editor_core.py",
                                                    "e[\"class\"] == \"view\" and lv not in editable)",
                                                    "e[\"class\"] == \"view\")"),
        "M4 view model validates edits": ("r3hd_level_editor_core.py",
                                          "    if getattr(model, \"view_only\", False):",
                                          "    if False:"),
        "M5 items left editable": ("r3hd_level_editor_core.py", "            a[\"status\"], a[\"why\"] = \"locked\", why",
                                   "            a[\"why\"] = why"),
        "M6 any small texture accepted": ("r3hd_level_scene.py", "    if (w, h) != (16, 16) or fmt not in",
                                          "    if w > 16 or fmt not in"),
        # (a mutation of the press guard alone is NOT caught, by design: on_drag and item_info refuse independently)
        "M7 controls not updated without a GL context": ("r3hd_scene_view.py",
                                                         "            self.sync_controls()\n            return\n",
                                                         "            return\n"),
        "M8 unsafe level names accepted": ("r3hd_level_editor_core.py", "        if not _level_name_ok(level):\n",
                                           "        if level is None:\n"),
    }
    R = []
    for name, (fname, old, new) in muts.items():
        with tempfile.TemporaryDirectory(prefix="g6p68-mut-") as td:
            src = (TOOLS / fname).read_bytes().decode("utf-8")
            nl = "\r\n" if "\r\n" in src else "\n"
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            if src.count(o) != 1:
                R.append((f"{name}: mutation site found once", False))
                continue
            (Path(td) / fname).write_bytes(src.replace(o, n).encode("utf-8"))
            env = dict(os.environ, G6P68_MUTANT_DIR=td)
            env.pop(core.DEV_LEVELS_ENV, None)
            r = subprocess.run([sys.executable, str(Path(__file__)), "--selftest"], capture_output=True, text=True,
                               env=env, timeout=600)
            caught = r.returncode != 0 and "G6P68_SELFTEST FAIL" in r.stdout
            R.append((f"{name}: caught", caught))
    return report(R, "G6P68_MUTATIONS")


# ------------------------------------------------------------------------------------------------ check
def gate_probe(env_value):
    code = ("import sys, json; sys.path.insert(0, %r); import r3hd_level_editor_core as c, r3hd_level_editor as e\n"
            "g = c.mod_paths()['game']\n"
            "try:\n c.RemixModel(g, 'wood_10'); r = 'opened'\n"
            "except c.EditorError as x:\n r = x.code\n"
            "v = c.ViewModel(g, 'wood_10')\n"
            "print(json.dumps({'choices': [x[1] for x in e.CHOICES], 'names': c.remix_level_names(), 'model': r,"
            " 'view': c.view_level_names(), 'view_unlocked': sum(1 for a in v.actors.values() if a['status'] != 'locked')"
            " + sum(1 for g_ in v.graphs.values() if g_['status'] != 'locked')}))" % str(TOOLS))
    env = dict(os.environ)
    env.pop(core.DEV_LEVELS_ENV, None)
    if env_value:
        env[core.DEV_LEVELS_ENV] = env_value
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=300)
    return json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else {"error": r.stderr[-400:]}


def check() -> int:
    os.environ.pop(core.DEV_LEVELS_ENV, None)
    import tkinter as tk
    import r3hd_level_editor as ed
    import r3hd_level_scene as ls
    import r3hd_scene_gl as sg
    import r3hd_scene_view as sv
    R, det = [], {}
    if WORK.exists():
        shutil.rmtree(WORK / "check", ignore_errors=True)
    out = WORK / "check"
    out.mkdir(parents=True)
    game = Path(core.mod_paths()["game"])
    gdir = game / "GAMEDATAbin"
    stat_before = tree_stat(gdir)
    levels = level_names(game)
    watched = {}
    for lv in levels + ["fix"]:
        lp, pp, _ = rm.script_level_files(game, lv)
        for fp in (lp, pp, lp.with_name("transit.lvl"), lp.with_name(f"{lv}_2.bhf"), lp.with_name("fix.bhf")):
            if fp.is_file() and str(fp) not in watched:
                watched[str(fp)] = hashlib.sha256(fp.read_bytes()).hexdigest()
    for lv in PACKED:
        fp = gdir / lv / f"{lv}_2.btf"
        watched[str(fp)] = hashlib.sha256(fp.read_bytes()).hexdigest()

    # K1 catalog: present, well formed, one entry per level folder, identities equal the person's files
    cat = core.load_view_catalog()
    ident = {lv: level_hashes(game, lv) for lv in levels}
    same = [lv for lv in levels if lv in cat and all(cat[lv][k] == ident[lv][k] for k in ("lvl", "ptr", "transit"))]
    view = sorted(lv for lv, e in cat.items() if e["class"] == "view")
    det["catalog"] = {"levels": len(cat), "view": len(view), "excluded": sorted(set(cat) - set(view)),
                      "identity_equal": len(same)}
    R.append((f"K1 the catalog covers every level folder ({len(levels)}) with the person's exact lvl / ptr / transit "
              f"SHA-256; {len(view)} viewable, excluded: {', '.join(det['catalog']['excluded']) or 'none'}",
              sorted(cat) == levels and len(same) == len(levels) and view
              and all(cat[lv]["measured"].get("triangles", 0) < MIN_TRIANGLES for lv in set(cat) - set(view))))

    # K2 offered list = viewable minus editable; the 2D editor's choices are unchanged
    offered = core.view_level_names()
    R.append(("K2 the viewer offers every viewable level except the editor's own (intros; wood_10 only while its gate "
              "is off); the 2D level list still has only the four editor choices",
              offered == sorted(set(view) - set(core.remix_level_names()))
              and not set(offered) & set(core.REMIX_LEVELS) and "wood_10" in offered
              and [c[1] for c in ed.CHOICES] == ["intro_20", "intro_10", "intro_15", "intro_20"]))

    # K3 the packed-tail textures (the four G6-P66 census failures): evidence on the real data
    pk = {}
    for lv, name in PACKED.items():
        s = ls.Scene(game, lv)
        key = next(k for k, t in s.textures.items() if t["name"] == name)
        w, h, px = s.decode_texture(key)
        bhf, e = s.texture_entry(key)
        with open(bhf.with_suffix(".btf"), "rb") as fh:
            fh.seek(e[2])
            page = rm.swap16(fh.read(e[1]))
        fmt = s.textures[key]["format"]
        bpb, pitch = (16, 512) if fmt == "DXT5" else (8, 256)

        def at(bx, by, side):
            rows = [page[(by + j) * pitch + bx * bpb:(by + j) * pitch + (bx + side // 4) * bpb]
                    for j in range(side // 4)]
            return rm.decode_level(side, side, rows, fmt)

        def mip_err(m0, m1):
            return max(abs(sum(m0[((2 * yy + dy) * 16 + 2 * xx + dx) * 4 + c] for dy in (0, 1) for dx in (0, 1)) / 4
                           - m1[(yy * 8 + xx) * 4 + c]) for yy in range(8) for xx in range(8) for c in range(4))
        x0, y0 = rm.packed_mip_offset(16, 16, 0)
        x1, y1 = rm.packed_mip_offset(16, 16, 1)
        base = at(x0 // 4, y0 // 4, 16)
        good = mip_err(base, at(x1 // 4, y1 // 4, 8))
        wrong = [mip_err(at(bx, by, 16), at(mx, my, 8)) for bx, by, mx, my in ((0, 0, 0, 0), (0, 4, 0, 2),
                                                                                  (8, 0, 4, 0), (4, 0, 0, 2))]
        all_ok = sum(1 for k in s.textures if _decodes(s, k))
        pk[lv] = {"texture": name, "format": fmt, "page_sha256": hashlib.sha256(page).hexdigest(),
                  "base_sha256": hashlib.sha256(px).hexdigest(), "colours": len({px[i:i + 4] for i in
                                                                                 range(0, len(px), 4)}),
                  "mip1_err": good, "wrong_offset_err_min": min(wrong), "decoded": all_ok, "textures": len(s.textures),
                  "size": [w, h]}
    det["packed"] = pk
    sk = [pk[lv] for lv in ("sk8_00", "sk8_10", "sk8_20")]
    R.append(("K3 the four census failures are 16x16 packed-tail bases and now decode: sfx\\white is one colour "
              "(255,255,255,255); mip 1 = box(base) within DXT rounding (<= 6); three different sk8 pages give one "
              "base; four wrong offsets fail (>= 200); every texture of the four levels decodes",
              all(p["mip1_err"] <= 6 and p["wrong_offset_err_min"] >= 200 and p["decoded"] == p["textures"]
                  for p in pk.values())
              and pk["ten_map"]["colours"] == 1 and len({p["page_sha256"] for p in sk}) == 3
              and len({p["base_sha256"] for p in sk}) == 1
              and _white_is_white(game)))

    # K4 representative read-only models: all locked, counts equal the catalog, compiler verdict retained
    reps = ["wood_11", "sk8_00", "ten_map", "swamp_50", "knaar_69", "wood_10"]
    rep_ok = {}
    for lv in reps:
        m = core.ViewModel(game, lv)
        c = m.counts()
        ms = cat[lv]["measured"]
        rep_ok[lv] = (c["actors"] == ms["actors"] and c["graphs"] == ms["graphs"] and c["waypoints"] == ms["waypoints"]
                      and c["triangles"] == ms["collision_triangles"] and c["actors_locked"] == c["actors"]
                      and c["waypoints_editable"] == 0 and m.identity == "measured" and not m.dev
                      and all("compiler_status" in a for a in m.actors.values()))
    det["representative_models"] = rep_ok
    R.append(("K4 six representative ViewModels (incl. wood_10 without its gate): every actor and route locked, "
              "counts equal the catalog, identity 'measured'", all(rep_ok.values())))

    # K5-K11: the real 3D window, withdrawn, with a never-shown offscreen context (no readback)
    root = tk.Tk()
    root.withdraw()
    orig_fd = sv.filedialog
    dialogs = []

    class FD:
        def __getattr__(self, n):
            return lambda *a, **k: dialogs.append(n) or ""
    sv.filedialog = FD()
    try:
        app, v = sv.open_editor(root, game, level="intro_15", show=False)
        ctx = sg.Context(offscreen=(640, 360))
        ctx.swap = ctx.finish                         # an offscreen target has nothing to present
        # G6-P69: the withdrawn viewport reports 1 x 1 until a relayout gives it its real size (larger than the
        # offscreen target); frames are drawn at the target's size
        v.vp.winfo_width, v.vp.winfo_height = (lambda: 640), (lambda: 360)
        v.ctx = ctx
        v.sync()
        R.append(("K5 the 3D window opens intro_15 EDITABLE with every command enabled",
                  v.level_key() == ("remix", "intro_15") and v.r is not None and "EDITABLE" in v.cap_lbl.cget("text")
                  and all(str(b.cget("state")) == "normal" for b in v.cmd_btns.values())))
        # an edit before browsing: it must survive the browsing untouched
        ident = next(k for k, a in app.rmodel.actors.items() if a["status"] not in ed.REFUSED)
        p0 = list(app.rmodel.actors[ident]["position"])
        app.set_remix_position(("actor", ident), [p0[0] + 1.0, p0[1], p0[2]], clamp=False)
        before_proj = json.dumps(app.remix, sort_keys=True)
        dirty_before = app.dirty

        # K6 switch through every offered level in the window: scene, renderer, overlays, one frame each
        sweep, mem0 = {}, memory_mb()
        for lv in offered:
            t0 = time.perf_counter()
            v.choose_level(sv.view_label(lv))
            v.finish_pending()                        # G6-P69: the load runs on the loader thread
            v._draw()
            dt = time.perf_counter() - t0
            info = ctx.n.info()
            r = v.r
            sweep[lv] = {"s": round(dt, 3), "loaded": r is not None, "frames": v.timing["frames"],
                         "bridge_match": r is not None and (info["textures"], info["batches"]) == bridge_live(r),
                         "markers": len(r.overlays["points"]) if r else 0,
                         "textures": r.stats["textures"] if r else 0,
                         "texture_errors": len(r.stats["texture_errors"]) if r else None,
                         "error_status": v.status_bar.cget("fg") == "#c0392b",
                         "buttons_disabled": all(str(b.cget("state")) == "disabled" for b in v.cmd_btns.values()),
                         "title": "VIEW ONLY" in v.top.title(), "mem": memory_mb()[0]}
        r = None                                      # G6-P69: K11 measures the viewer, not this loop's last reference
        mem1 = memory_mb()
        det["sweep"] = sweep
        det["sweep_memory"] = {"before": mem0, "after": mem1}
        times = sorted(x["s"] for x in sweep.values())
        det["sweep_seconds"] = {"median": times[len(times) // 2], "max": times[-1], "total": round(sum(times), 1)}
        R.append((f"K6 all {len(offered)} offered levels open in the real 3D window one after another: scene and "
                  "renderer built, a frame drawn, no error, bridge holds exactly the current level's textures and "
                  "batches, VIEW ONLY title, every command disabled",
                  all(x["loaded"] and not x["error_status"] and x["bridge_match"] and x["buttons_disabled"]
                      and x["title"] for x in sweep.values()) and len(sweep) == len(offered) > 0))
        shown = sum(x["textures"] for x in sweep.values())
        want = sum(cat[lv]["measured"]["textures_shown"] for lv in offered)
        recs = sum(cat[lv]["measured"]["textures"] for lv in offered)
        det["sweep_textures"] = {"uploaded": shown, "measured": want, "records": recs}
        # first compared with every texture record (1,620); the renderer uploads only the textures of drawn objects,
        # and objects classified runtime-placed are hidden (G6-P38), so the baseline is the measured upload count
        R.append((f"K7 the window uploads exactly the measured textures of the offered levels ({shown} / {want}; "
                  f"{recs - want} records belong only to hidden runtime-placed objects) and no texture fails",
                  shown == want and all(x["texture_errors"] == 0 for x in sweep.values())
                  and all(cat[lv]["measured"]["textures_decoded"] == cat[lv]["measured"]["textures"]
                          for lv in cat if cat[lv]["measured"])))

        # K8 read-only enforcement on a viewed level, with an attempted drag of a selected actor
        v.choose_level(sv.view_label("wood_11"))
        v.finish_pending()
        m = v.view["model"]
        sel = ("actor", next(iter(m.actors)))
        v.select(sel)
        v.pick = lambda x_, y_, radius=12: sel
        v.on_press(type("E", (), {"x": 5, "y": 5, "state": 0})())
        v.drag["moved"] = True
        v.on_drag(type("E", (), {"x": 80, "y": 90, "state": 0})())
        del v.pick
        n_before = len(app.undo)
        for fn in (v.apply, v.revert, v.undo, v.save, v.validate, v.export, v.import_mod, v.open, v.show_2d):
            fn()
        R.append(("K8 on a viewed level nothing can be moved, applied, reverted, undone, saved, validated, exported, "
                  "imported or opened, and the 2D editor stays hidden: no dialog, no editor change",
                  v.preview is None and v.drag["kind"] == "orbit" and dialogs == [] and len(app.undo) == n_before
                  and json.dumps(app.remix, sort_keys=True) == before_proj and not v.item_info(sel)[3]
                  and not root.winfo_viewable() and m.actors[sel[1]]["status"] == "locked"))

        # K9 back to intro_15: the project and its unsaved edit are intact and editing still works
        v.choose_level(app.current_choice()[2])
        kept = json.dumps(app.remix, sort_keys=True) == before_proj and app.dirty == dirty_before
        v.select(("actor", ident))
        v.preview = {"sel": ("actor", ident), "pos": (p0[0] + 2.0, p0[1], p0[2])}
        v.apply()
        moved = abs(app.remix_position(("actor", ident))[0] - (p0[0] + 2.0)) < 1e-3
        val = core.validate_remix(app.remix, game, model=app.rmodel)
        counts = {}
        for lv in INTRO_COUNTS:
            cc = core.RemixModel(game, lv).counts()
            counts[lv] = (cc["actors_verified"] + cc["actors_placement"] + cc["actors_experimental"], cc["actors"],
                          cc["waypoints_editable"], cc["waypoints"])
        det["intro_counts"] = counts
        R.append(("K9 leaving the viewer for intro_15 keeps the unsaved project byte-identical; Apply moves an actor; "
                  "the project validates; intro editable counts and the 25-unit bound unchanged",
                  kept and moved and val.get("ok") and v.view is None and counts == INTRO_COUNTS
                  and all(core.actor_move_limit(lv) == 25.0 for lv in INTRO_COUNTS)
                  and all(str(b.cget("state")) == "normal" for b in v.cmd_btns.values())))

        # K10 missing and damaged files: refused with a message, the window keeps working
        fx = out / "fixtures"
        cases = _fixtures(game, fx)
        res = {}
        real_game = app.game_dir
        # G6-P69 (D-318): a level that cannot be read no longer replaces the level shown; it stays, intact
        for name, gd in cases.items():
            v.choose_level(sv.view_label("wood_11"))   # a good level is shown before each damaged one
            v.finish_pending()
            before_r = v.r
            app.game_dir = gd
            v.choose_level(sv.view_label("sk8_00"))
            v.finish_pending()
            v._draw()
            info = ctx.n.info()
            res[name] = {"shown": v.level_key()[1], "model": v.view["model"] is not None if v.view else None,
                         "same_renderer": v.r is before_r, "error_status": v.status_bar.cget("fg") == "#c0392b",
                         "message": "sk8_00" in v.status_bar.cget("text"),
                         "bridge_match": v.r is not None and (info["textures"], info["batches"]) == bridge_live(v.r),
                         "texture_errors": len(v.r.stats["texture_errors"]) if v.r else None,
                         "selector": v.level_var.get(), "title_view_only": "VIEW ONLY" in v.top.title(),
                         "buttons_disabled": all(str(b.cget("state")) == "disabled" for b in v.cmd_btns.values())}
            app.game_dir = real_game
            v.choose_level(sv.view_label("ten_map"))   # recovery onto another good level
            v.finish_pending()
            res[name]["recovered"] = v.r is not None and v.level_key() == ("view", "ten_map") \
                and not v.r.stats["texture_errors"]
            before_r = None                            # G6-P69: the harness must not pin a closed level's scene (K11)
        det["missing"] = res
        R.append(("K10 missing ptr / truncated lvl: refused with a message naming the level; the level shown (wood_11) "
                  "stays with the same renderer, selector and VIEW ONLY state; missing texture bundles: shown "
                  "untextured with the textures counted; every case keeps the bridge consistent and the next level "
                  "loads",
                  all(res[k]["shown"] == "wood_11" and res[k]["same_renderer"] and res[k]["error_status"]
                      and res[k]["message"] and res[k]["selector"] == sv.view_label("wood_11")
                      for k in ("missing_ptr", "truncated_lvl"))
                  and res["no_bundles"]["shown"] == "sk8_00" and not res["no_bundles"]["same_renderer"]
                  and res["no_bundles"]["texture_errors"] > 0
                  and all(r_["buttons_disabled"] and r_["recovered"] and r_["title_view_only"] and r_["bridge_match"]
                          for r_ in res.values())))
        shutil.rmtree(fx, ignore_errors=True)

        # K11 cleanup: after a second sweep and closing, the bridge holds nothing; memory bounded across passes
        for lv in offered:
            v.choose_level(sv.view_label(lv))
            v.finish_pending()
        mem2 = memory_mb()
        v.choose_level(app.current_choice()[2])
        r = v.r
        live_ok = (ctx.n.info()["textures"], ctx.n.info()["batches"]) == bridge_live(r)
        r.close()
        empty = {k: ctx.n.info()[k] for k in ("textures", "batches", "bytes")}
        v.r = None
        det["cleanup"] = {"after_second_sweep": mem2, "bridge_after_close": empty,
                          "readbacks": ctx.n.info()["readbacks"], "window_visible": ctx.n.info()["window_visible"]}
        growth = (mem2[0] - mem1[0]) if mem1[0] and mem2[0] else 0
        R.append(("K11 after two full sweeps and closing the last renderer the bridge holds 0 textures / batches / "
                  f"bytes; working set grows {growth:+.0f} MiB between the first and second sweep (< 150); no readback, "
                  "no visible window", live_ok and empty == {"textures": 0, "batches": 0, "bytes": 0}
                  and growth < 150 and det["cleanup"]["readbacks"] == 0
                  and det["cleanup"]["window_visible"] is False))
        v.ctx = None
        ctx.close()
        v.close(ask=False)
    finally:
        sv.filedialog = orig_fd
        try:
            root.destroy()
        except tk.TclError:
            pass

    # K12 the development gate of wood_10, in fresh processes
    off, on = gate_probe(None), gate_probe("wood_10")
    det["gate"] = {"off": off, "on": on}
    R.append(("K12 wood_10: without R3HD_DEV_EDITOR_LEVELS it is only viewable (editor list = intros, model refused, "
              "offered view only); with it, it is editable and not offered view only; its ViewModel is all locked",
              off.get("names") == ["intro_10", "intro_15", "intro_20"] and off.get("model") == "UNSUPPORTED"
              and "wood_10" in off.get("view", []) and "wood_10" not in off.get("choices", ["wood_10"])
              and on.get("model") == "opened" and "wood_10" in on.get("names", [])
              and "wood_10" not in on.get("view", ["wood_10"]) and off.get("view_unlocked") == 0
              and on.get("view_unlocked") == 0))

    # K13 representative offscreen pictures (six readbacks, private PNGs): non-empty, textured, reproducible
    shots = {}
    for lv in READBACK_LEVELS:
        shots[lv] = sg.render_test(game, lv, out / f"{lv}.png", frames=3, view_only=True)
    again = sg.render_test(game, "sk8_00", out / "sk8_00_again.png", frames=3, view_only=True)
    png = {lv: hashlib.sha256(Path(s["out"]).read_bytes()).hexdigest() for lv, s in shots.items()}
    det["renders"] = {lv: {k: s[k] for k in ("covered_share_sampled", "distinct_colours_sampled", "first_frame_ms",
                                             "interactive_ms_median", "upload_seconds", "scene_seconds", "readbacks",
                                             "window_visible", "gl_error")} | {"png": png[lv][:16]}
                      for lv, s in shots.items()}
    # first written with markers and covered > 0.05 / colours > 200 (unmeasured guesses); revised before commit after
    # the whole-level overview of sk8_00 (0.028) and knaar_69 (0.010) proved to frame small textured content inside
    # bounds that include distant objects: scene only (no markers), non-empty and more than a flat fill
    R.append(("K13 five representative levels drawn offscreen without markers (one readback each, never-shown window, "
              "no GL error): non-empty and not a flat fill; sk8_00 drawn twice is byte-identical. Not proof of visual "
              "fidelity",
              all(s["window_visible"] is False and s["readbacks"] == 1 and not s["gl_error"]
                  and s["covered_share_sampled"] > 0.005 and s["distinct_colours_sampled"] >= 8 for s in shots.values())
              and hashlib.sha256(Path(again["out"]).read_bytes()).hexdigest() == png["sk8_00"]))

    # K14 nothing in the game folder changed
    after = {k: hashlib.sha256(Path(k).read_bytes()).hexdigest() for k in watched}
    R.append((f"K14 the person's game files are unchanged: {len(watched)} level / pointer / transit / bundle / texture "
              "files hash identical, and no file in GAMEDATAbin changed size or time",
              after == watched and tree_stat(gdir) == stat_before))
    (out / "details.json").write_text(json.dumps(det, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: det[k] for k in det if k not in ("sweep",)}, indent=1, default=str))
    return report(R, "G6P68_CHECK")


def _decodes(s, k):
    try:
        w, h, px = s.decode_texture(k, max_side=32)
        return len(px) == w * h * 4
    except Exception:  # noqa: BLE001 - counted, not raised
        return False


def _white_is_white(game):
    import r3hd_level_scene as ls
    s = ls.Scene(game, "ten_map")
    k = next(k for k, t in s.textures.items() if t["name"] == PACKED["ten_map"])
    w, h, px = s.decode_texture(k)
    return px == bytes((255, 255, 255, 255)) * (w * h)


def _fixtures(game, fx):
    """Private damaged copies (sk8_00 + fix level files, never the textures' .btf of fix): missing ptr, truncated lvl,
    no level / transit bundles. Deleted after the check."""
    src = game / "GAMEDATAbin"
    cases = {}
    for name in ("missing_ptr", "truncated_lvl", "no_bundles"):
        g = fx / name / "GAMEDATAbin"
        (g / "sk8_00").mkdir(parents=True)
        for f in ("fix.lvl", "fix.ptr"):
            shutil.copyfile(src / f, g / f)
        for f in ("sk8_00.lvl", "sk8_00.ptr", "transit.lvl", "transit.ptr"):
            shutil.copyfile(src / "sk8_00" / f, g / "sk8_00" / f)
        cases[name] = fx / name
    (fx / "missing_ptr" / "GAMEDATAbin" / "sk8_00" / "sk8_00.ptr").unlink()
    lp = fx / "truncated_lvl" / "GAMEDATAbin" / "sk8_00" / "sk8_00.lvl"
    lp.write_bytes(lp.read_bytes()[:4096])
    return cases


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", nargs="?", choices=["check", "measure"])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutations", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.mutations:
        return mutations()
    if a.mode == "measure":
        return measure()
    if a.mode == "check":
        return check()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
