#!/usr/bin/env python3
"""G6-P38: the Level Remix Editor's 3D window - one textured viewport, three tools, one inspector.

    python tools/r3hd_scene_view.py [LEVEL] [--project FILE] [--game-dir DIR] [--home HOME]

Opens the unchanged Level Remix Editor (`r3hd_level_editor.EditorApp`) with its classic 2D window hidden, and this
3D window as the primary interface. Every edit goes through the editor's own methods - selection (`select`), actor
and waypoint moves (`set_remix_position`: bounds, LOCKED refusals, float32, undo), terrain lowering
(`set_vertex_dz`: verified ranges), `revert_selected`, `cmd_undo`, `save_project`, `validate_now`, `export_mod`,
`import_mod` - so the project format and the compiler path are the existing ones. The seam is instance-level only:
`EditorApp.refresh` and `flash` of that one instance are wrapped to keep this window in step (D-294).

Input is bound to this window's own widgets; there are no global hooks, no injected events, no grabs and no cursor
moves. A held button is the operating system's ordinary capture and ends with the release; drags and held keys are
dropped on focus loss and Escape. The view draws only after an input, resize, expose or editor change; flying with a
held key runs a 16 ms timer that stops with the last key release or focus loss (D-294).
"""
import argparse
import math
import os
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_level_editor as ed  # noqa: E402
import r3hd_level_editor_core as core  # noqa: E402
import r3hd_level_scene as ls  # noqa: E402
import r3hd_scene_gl as sg  # noqa: E402

PLAIN_STATUS = {"verified": "Tested in game: works at a new place",
                "placement": "Tested in game: stays where it is placed (what it does there is not tested)",
                "supported": "Tested in game: follows a moved route (partly confirmed)",
                "experimental": "Not tested in game yet: it may or may not behave as expected",
                "locked": "Cannot be moved: the game itself positions it",
                "script_overridden": "Cannot be moved: the game itself positions it"}
STATUS_FG = {"verified": "#1d8a4a", "placement": "#1d8a4a", "supported": "#2e6db4", "experimental": "#b9770e",
             "locked": "#777777", "script_overridden": "#777777"}
TOOLS = (("objects", "Objects"), ("paths", "Paths"), ("terrain", "Terrain"))
TOOL_FOR_KIND = {"actor": "objects", "rwp": "paths", "vtx": "terrain"}
WHY_DISABLED = {
    "remix": "Terrain lowering belongs to the intro_20 terrain + FairyLight project: choose it under Level.",
    "patch": "Objects and Paths belong to the actor and waypoint remix projects: choose one under Level. "
             "The FairyLight route of this project is edited in the classic 2D editor."}
HINT = ("Left-drag: orbit   Right-drag: look   Middle-drag: pan   Wheel: zoom   W A S D Q E: fly (Shift: faster)   "
        "F: focus   Home: whole level   Enter: apply   Esc: cancel   Ctrl+Z: undo")
FLY_KEYS = {"w": (1, 0, 0), "s": (-1, 0, 0), "a": (0, -1, 0), "d": (0, 1, 0), "q": (0, 0, -1), "e": (0, 0, 1)}


def friendly(name):
    """'NIK_mChameleon' -> 'Chameleon'; the technical key stays under Advanced details."""
    base = name.split("_m", 1)[1] if "_m" in name[:6] else name.split("_", 1)[-1]
    return base.replace("_", " ").strip() or name


def dim(rgb, k=0.55):
    return tuple(c * k for c in rgb)


class Editor3D:
    def __init__(self, app, top):
        self.app, self.top = app, top
        self.ctx = self.r = self.scene = None
        self.scene_key = None
        self.cam = sg.Camera()
        self.preview = None                  # {"sel": selection, "pos": (x, y, z)} or {"sel": ("vtx", v), "dz": d}
        self.drag, self.mats = None, None
        self.keys, self.fast, self._fly_job, self._fly_t = set(), False, None, None
        self._redraw_pending, self._closing = False, False
        self.timing = {"frames": 0, "last_ms": None, "max_ms": 0.0, "load_seconds": None}
        self.picks = []                      # [(position, selection)] of the current tool
        self._build()
        self._hook()

    # ---------------------------------------------------------------------------------------------- editor seam
    def _hook(self):
        """Instance-level wrappers only: the editor module and class stay unchanged."""
        app = self.app
        orig_refresh, orig_flash = app.refresh, app.flash

        def refresh(redraw=True):
            out = orig_refresh(redraw)
            self.sync()
            return out

        def flash(text, error=False):
            orig_flash(text, error)
            self.status(text, error)
        app.refresh, app.flash = refresh, flash
        app.scene3d = self

    # ---------------------------------------------------------------------------------------------- layout
    def _build(self):
        t = self.top
        t.geometry("1440x860")
        t.minsize(900, 560)
        bar = ttk.Frame(t, padding=(8, 6))
        bar.pack(side="top", fill="x")
        ttk.Label(bar, text="Level").pack(side="left")
        self.level_var = tk.StringVar()
        self.level_cb = ttk.Combobox(bar, textvariable=self.level_var, state="readonly", width=44,
                                     values=[c[2] for c in ed.CHOICES])
        self.level_cb.pack(side="left", padx=(4, 12))
        self.level_cb.bind("<<ComboboxSelected>>", lambda e: self.choose_level(self.level_var.get()))
        self.tool = tk.StringVar(value="objects")
        self.tool_btns = {}
        for key, label in TOOLS:
            b = ttk.Radiobutton(bar, text=label, value=key, variable=self.tool, style="Toolbutton",
                                command=self.tool_changed)
            b.pack(side="left", padx=1)
            self.tool_btns[key] = b
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        self.undo_btn = ttk.Button(bar, text="Undo", command=self.undo)
        self.undo_btn.pack(side="left")
        for label, fn in (("Save", self.save), ("Validate", self.validate), ("Export mod...", self.export),
                          ("Import + enable...", self.import_mod)):
            ttk.Button(bar, text=label, command=fn).pack(side="left", padx=1)
        self.adv = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Advanced details", variable=self.adv, command=self.refresh_panel).pack(side="right")
        ttk.Button(bar, text="Classic 2D editor", command=self.show_2d).pack(side="right", padx=6)

        body = ttk.Frame(t)
        body.pack(side="top", fill="both", expand=True)
        side = ttk.Frame(body, padding=8, width=330)
        side.pack(side="right", fill="y")
        side.pack_propagate(False)
        # background "" : Tk never paints this frame; OpenGL owns its pixels
        self.vp = tk.Frame(body, background="", takefocus=1, cursor="crosshair")
        self.vp.pack(side="left", fill="both", expand=True)

        self.insp = ttk.LabelFrame(side, text="Selected", padding=6)
        self.insp.pack(fill="x")
        self.name_lbl = ttk.Label(self.insp, text="", font=("Segoe UI", 11, "bold"), wraplength=300)
        self.name_lbl.pack(anchor="w")
        self.status_lbl = tk.Label(self.insp, text="", anchor="w", justify="left", wraplength=300)
        self.status_lbl.pack(fill="x")
        self.detail_lbl = tk.Label(self.insp, text="", anchor="w", justify="left", wraplength=300,
                                   font=("Segoe UI", 9))
        self.detail_lbl.pack(fill="x", pady=(4, 0))
        row = ttk.Frame(self.insp)
        row.pack(fill="x", pady=(6, 0))
        self.apply_btn = ttk.Button(row, text="Apply", command=self.apply)
        self.cancel_btn = ttk.Button(row, text="Cancel", command=self.cancel)
        self.revert_btn = ttk.Button(row, text="Revert to original", command=self.revert)
        self.focus_btn = ttk.Button(row, text="Focus", command=self.focus_selection)
        for b in (self.apply_btn, self.cancel_btn, self.revert_btn, self.focus_btn):
            b.pack(side="left", padx=(0, 3))
        self.msg = tk.Label(self.insp, text="", anchor="w", justify="left", wraplength=300, fg="#555555")
        self.msg.pack(fill="x", pady=(4, 0))
        self.region_row = ttk.Frame(self.insp)
        ttk.Label(self.region_row, text="Floor area").pack(side="left")
        self.region_var = tk.StringVar()
        self.region_cb = ttk.Combobox(self.region_row, textvariable=self.region_var, values=core.REGIONS,
                                      state="readonly", width=18)
        self.region_cb.pack(side="left", padx=4)
        self.region_cb.bind("<<ComboboxSelected>>", lambda e: self.app.set_region(self.region_var.get()))

        sf = ttk.LabelFrame(side, text="Show", padding=6)
        sf.pack(fill="x", pady=(8, 0))
        self.show = {k: tk.BooleanVar(value=v) for k, v in (("scene", True), ("backdrop", True), ("collision", False))}
        for k, label in (("scene", "Level (textured)"), ("backdrop", "Sky (approximate)"),
                         ("collision", "Walkable surfaces (collision)")):
            ttk.Checkbutton(sf, text=label, variable=self.show[k], command=self.request).pack(anchor="w")
        cf = ttk.Frame(side)
        cf.pack(fill="x", pady=6)
        ttk.Button(cf, text="Whole level", command=self.fit_level).pack(side="left")
        ttk.Button(cf, text="Editable area", command=self.fit_content).pack(side="left", padx=4)
        self.adv_lbl = tk.Label(side, text="", anchor="nw", justify="left", wraplength=310, fg="#555555",
                                font=("Consolas", 8))

        bottom = ttk.Frame(t, padding=(8, 2))
        bottom.pack(side="bottom", fill="x", before=body)
        self.status_bar = tk.Label(bottom, text="", anchor="w", justify="left", wraplength=1380)
        self.status_bar.pack(fill="x")
        ttk.Label(bottom, text=HINT, foreground="#666666", font=("Segoe UI", 8)).pack(fill="x")

        v = self.vp
        v.bind("<Map>", lambda e: self.ensure_gl())
        v.bind("<Configure>", lambda e: self.request())
        v.bind("<Expose>", lambda e: self.request())
        v.bind("<ButtonPress-1>", self.on_press)
        v.bind("<B1-Motion>", self.on_drag)
        v.bind("<ButtonRelease-1>", self.on_release)
        v.bind("<ButtonPress-3>", lambda e: self.start_aux(e, "look"))
        v.bind("<B3-Motion>", self.on_aux)
        v.bind("<ButtonRelease-3>", self.end_aux)
        v.bind("<ButtonPress-2>", lambda e: self.start_aux(e, "pan"))
        v.bind("<B2-Motion>", self.on_aux)
        v.bind("<ButtonRelease-2>", self.end_aux)
        v.bind("<MouseWheel>", self.on_wheel)
        v.bind("<KeyPress>", self.on_key)
        v.bind("<KeyRelease>", self.on_key_release)
        v.bind("<FocusOut>", self.on_focus_out)
        v.bind("<Return>", lambda e: self.apply())
        v.bind("<Escape>", lambda e: self.escape())
        v.bind("<Control-z>", lambda e: self.undo())
        v.bind("<Delete>", lambda e: self.revert())
        t.protocol("WM_DELETE_WINDOW", self.close)

    # ---------------------------------------------------------------------------------------------- GL and scene
    def ensure_gl(self):
        if self.ctx is not None:
            return True
        try:
            self.top.update_idletasks()
            self.ctx = sg.Context(self.vp.winfo_id())
        except (ls.SceneError, OSError) as x:
            self.ctx = None
            self.status(f"The 3D view could not start ({x}). The classic 2D editor still works.", True)
            return False
        self.sync()
        return True

    def level_key(self):
        a = self.app
        return ("remix", a.remix["level"]) if a.mode == "remix" else ("patch", core.LEVEL)

    def ensure_scene(self):
        key = self.level_key()
        if self.r is not None and self.scene_key == key:
            return
        if self.r is not None and self.scene_key and self.scene_key[1] == key[1]:
            self.scene_key = key                       # same level, other project kind: keep the scene
            self.r.set_collision(self.collision_tris(key))
            self.fit_content()
            return
        self.status(f"Loading {key[1]} from your game files...")
        t0 = time.perf_counter()
        old, self.r = self.r, None
        if old is not None:
            self.ctx.current()
            old.close()                                # free the previous level's textures before loading
        model = self.app.rmodel if key[0] == "remix" else None
        try:
            self.scene, _ = sg.classified_scene(self.app.game_dir, key[1], model)
            self.ctx.current()
            self.r = sg.Renderer(self.ctx, self.scene)
        except (ls.SceneError, core.EditorError, OSError) as x:
            self.scene = None
            self.status(f"The level's scene could not be read: {getattr(x, 'detail', x)}", True)
            return
        self.r.set_collision(self.collision_tris(key))
        self.scene_key = key
        self.timing["load_seconds"] = round(time.perf_counter() - t0, 3)
        self.fit_content()
        self.status(f"{key[1]} loaded from your game files.")

    def collision_tris(self, key):
        if key[0] == "remix" and self.app.rmodel:
            return self.app.rmodel.tris
        return core.RemixModel(self.app.game_dir, core.LEVEL).tris if key[0] == "patch" else []

    def asks(self):
        """Dialogs only for a person: a window that is not viewable (tests, withdrawn) never opens one."""
        try:
            return bool(self.top.winfo_viewable())
        except tk.TclError:
            return False

    def close(self, ask=True):
        if self._closing:
            return
        if ask and self.asks() and self.app.dirty and not messagebox.askyesno(
                "Unsaved changes", "Discard the unsaved changes and close?",
                                                      parent=self.top):
            return
        self._closing = True
        self.stop_fly()
        self.free_gl()
        try:
            self.app.root.destroy()
        except tk.TclError:
            pass

    def free_gl(self):
        if self.ctx:
            self.ctx.current()
            if self.r:
                self.r.close()
            self.ctx.close()
        self.ctx = self.r = None

    def request(self):
        """At most one draw per idle period; nothing is drawn without an event."""
        if not self._redraw_pending and not self._closing:
            self._redraw_pending = True
            self.top.after_idle(self._draw)

    def _draw(self):
        self._redraw_pending = False
        if not self.ctx or not self.r:
            return
        w, h = max(self.vp.winfo_width(), 1), max(self.vp.winfo_height(), 1)
        t0 = time.perf_counter()
        self.ctx.current()
        for k in ("scene", "backdrop", "collision"):
            self.r.show[k] = self.show[k].get()
        self.mats = self.r.draw(self.cam, w, h) + (w, h)
        self.ctx.swap()
        ms = (time.perf_counter() - t0) * 1000
        self.timing["frames"] += 1
        self.timing["last_ms"] = round(ms, 2)
        if self.timing["frames"] > 1:                  # the first frame carries driver warm-up
            self.timing["max_ms"] = max(self.timing["max_ms"], ms)

    # ---------------------------------------------------------------------------------------------- sync from editor
    def sync(self):
        """Rebuild what the current tool shows from the editor's state; then one redraw."""
        if self._closing or self.ctx is None:
            return
        app = self.app
        self.ensure_scene()
        name = app.path.name if app.path else "unsaved project"
        self.top.title(f"Experimental 3D Level Viewer - {self.level_key()[1]} - {name}{' *' if app.dirty else ''}")
        self.level_var.set(app.current_choice()[2])
        kind = self.level_key()[0]
        for key, b in self.tool_btns.items():
            ok = (key != "terrain") if kind == "remix" else (key == "terrain")
            b.config(state="normal" if ok else "disabled")
        if app.sel and TOOL_FOR_KIND.get(app.sel[0]) and TOOL_FOR_KIND[app.sel[0]] != self.tool.get():
            self.tool.set(TOOL_FOR_KIND[app.sel[0]])
        if str(self.tool_btns[self.tool.get()].cget("state")) == "disabled":
            self.tool.set("objects" if kind == "remix" else "terrain")
        self.undo_btn.config(state="normal" if kind == "remix" and app.undo else "disabled")
        if self.preview and self.preview["sel"] != app.sel:
            self.preview = None
        self.build_overlays()
        self.refresh_panel()
        self.request()

    def selected_pos(self, sel):
        """Current (edited) position of a selection, from the editor."""
        app = self.app
        if sel[0] in ("actor", "rwp"):
            p = app.remix_position(sel)
            return tuple(p) if p else None
        if sel[0] == "vtx" and app.model:
            return tuple(app.model.edited_verts({int(k): v for k, v in app.project["terrain"].items()})[sel[1]])
        return None

    def original_pos(self, sel):
        it = self.app.remix_item(sel) if sel[0] in ("actor", "rwp") else None
        if it:
            return tuple(it[0])
        if sel[0] == "vtx" and self.app.model:
            return tuple(self.app.model.verts[sel[1]])
        return None

    def build_overlays(self):
        if not self.r:
            return
        app, tool = self.app, self.tool.get()
        pts, lines, picks = [], [], []
        m = app.rmodel if self.level_key()[0] == "remix" else None
        if tool == "objects" and m:
            for ident, a in m.actors.items():
                sel = ("actor", ident)
                p = tuple(app.remix_position(sel))
                pts.append((p, sg.STATUS_RGB.get(a["status"], (1, 1, 1)), sel))
                picks.append((p, sel))
                if math.dist(p, a["position"]) > 1e-6:          # where an edited object came from
                    lines.append((a["position"], p, (0.8, 0.8, 0.8), 1.0, True, False))
        elif tool == "paths" and m:
            cur_g = app.sel[1][:3] if app.sel and app.sel[0] == "rwp" else None
            for gid, g in m.graphs.items():
                rgb = sg.STATUS_RGB.get(g["status"], (1, 1, 1))
                strong = gid == cur_g
                pos = {}
                for nd in g["nodes"]:
                    if not nd:
                        continue
                    sel = ("rwp", gid + (nd["node"],))
                    p = tuple(app.remix_position(sel))
                    pos[nd["node"]] = p
                    editable = g["status"] not in ed.REFUSED and not nd["why"]
                    pts.append((p, (rgb if strong else dim(rgb, 0.8)) if editable else sg.STATUS_RGB["locked"], sel))
                    picks.append((p, sel))
                    if math.dist(p, nd["position"]) > 1e-6:      # original place of an edited waypoint
                        lines.append((nd["position"], p, (0.8, 0.8, 0.8), 1.0, True, False))
                for i, j in g["edges"]:
                    if i in pos and j in pos:
                        lines.append((pos[i], pos[j], rgb if strong else dim(rgb), 3.0 if strong else 1.5,
                                      False, True))
            owner = (cur_g[0], cur_g[1]) if cur_g else None
            if owner in m.actors:                              # the selected route's storage owner (not pickable)
                pts.append((tuple(app.remix_position(("actor", owner))), (1.0, 1.0, 1.0), None))
        elif tool == "terrain" and app.model:
            terr = {int(k): v for k, v in app.project["terrain"].items()}
            verts = app.model.edited_verts(terr)
            region = app.model.regions[app.project["region"]]["vertices"]
            tris = set()
            for v in region:
                sel = ("vtx", v)
                rgb = (1.0, 0.63, 0.25) if v in terr else (0.25, 0.76, 0.5)
                pts.append((tuple(verts[v]), rgb, sel))
                picks.append((tuple(verts[v]), sel))
                tris.update(app.model.vertex_triangles(v))
            for t in sorted(tris):
                ix = app.model.tris[t]
                for a_, b_ in ((0, 1), (1, 2), (2, 0)):
                    lines.append((tuple(verts[ix[a_]]), tuple(verts[ix[b_]]), (0.95, 0.9, 0.4), 1.5, False, False))
        sel = app.sel if app.sel and TOOL_FOR_KIND.get(app.sel[0]) == tool else None
        self.r.overlays.update(points=pts, lines=lines, selected=self.selected_pos(sel) if sel else None, ghost=None)
        if self.preview and sel == self.preview["sel"]:
            self.r.overlays["ghost"] = (self.selected_pos(sel), self.preview_pos())
        self.picks = picks

    def preview_pos(self):
        p = self.preview
        if not p:
            return None
        if "pos" in p:
            return tuple(p["pos"])
        x, y, z = self.app.model.verts[p["sel"][1]]
        return (x, y, core.f32(z + p["dz"]))

    # ---------------------------------------------------------------------------------------------- inspector
    def item_info(self, sel):
        """(title, status key, plain detail lines, editable, limit text) of a selection."""
        app = self.app
        if sel[0] == "actor":
            a = app.rmodel.actors[sel[1]]
            return (f"{friendly(a['name'])} #{a['instance']}", a["status"], [], a["status"] not in ed.REFUSED,
                    f"may move up to {core.MAX_ACTOR_MOVE:g} units (the largest move tested in game)")
        if sel[0] == "rwp":
            gid, n = sel[1][:3], sel[1][3]
            g = app.rmodel.graphs[gid]
            nd = g["nodes"][n]
            st = "locked" if g["status"] in ed.REFUSED or nd["why"] else g["status"]
            _, follower = core.graph_owner(app.rmodel, gid)
            kind, _ = core.route_sequence(g)
            lines = [f"Route of {friendly(g['name'])} #{gid[1]} ({kind}, {len(g['nodes'])} points)",
                     f"Who follows it: {follower if follower != 'UNKNOWN' else 'not measured'}"]
            return (f"Route point {n}", st, lines, st not in ed.REFUSED,
                    f"may move up to {core.MAX_WAYPOINT_MOVE:g} units (the largest move tested in game)")
        if sel[0] == "vtx":
            lo, hi = app.editable_range(sel[1])
            return (f"Start-floor point {sel[1]}", "verified",
                    ["Lowers the walkable (collision) floor; the textured picture keeps the original floor."], True,
                    f"may be lowered by {-hi:.2f} to {-lo:.2f} units (the tested range)")
        return ("", None, [], False, "")

    def refresh_panel(self):
        app, tool = self.app, self.tool.get()
        sel = app.sel if app.sel and TOOL_FOR_KIND.get(app.sel[0]) == tool else None
        titles = {"objects": "Selected object", "paths": "Selected route point", "terrain": "Selected floor point"}
        self.insp.config(text=titles[tool])
        if tool == "terrain" and self.level_key()[0] == "patch":
            self.region_var.set(app.project["region"])
            self.region_row.pack(fill="x", pady=(6, 0))
        else:
            self.region_row.pack_forget()
        if sel is None:
            self.name_lbl.config(text="Nothing selected")
            hint = {"objects": "Click a marker to select an object. Markers are editor symbols, not the objects' "
                               "3D models.",
                    "paths": "Click a route point. Arrows show the direction of travel; the selected route is bright.",
                    "terrain": "Click a green floor point (the start floor of intro_20)."}[tool]
            self.status_lbl.config(text=hint, fg="#555555")
            self.detail_lbl.config(text=WHY_DISABLED[self.level_key()[0]])
            for b in (self.apply_btn, self.cancel_btn, self.revert_btn, self.focus_btn):
                b.config(state="disabled")
        else:
            title, st, lines, editable, limit = self.item_info(sel)
            orig, cur, prop = self.original_pos(sel), self.selected_pos(sel), self.preview_pos()
            self.name_lbl.config(text=title)
            self.status_lbl.config(text=PLAIN_STATUS.get(st, st) if sel[0] != "vtx" else
                                   "Tested in game: Rayman stands on the lowered floor", fg=STATUS_FG.get(st, "#555555"))
            fmt = lambda p: f"{p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f}"   # noqa: E731
            out = list(lines) + [f"Original: {fmt(orig)}", f"Now: {fmt(cur)}"
                                 + (f"  (moved {math.dist(cur, orig):.2f})" if math.dist(cur, orig) > 1e-6 else "")]
            if prop:
                out.append(f"Proposed: {fmt(prop)}  ({math.dist(prop, orig):.2f} from original)")
            out.append(("It " + limit + ".") if editable else "It cannot be changed here.")
            self.detail_lbl.config(text="\n".join(out))
            self.apply_btn.config(state="normal" if prop and editable else "disabled")
            self.cancel_btn.config(state="normal" if prop else "disabled")
            self.revert_btn.config(state="normal" if editable and math.dist(cur, orig) > 1e-6 else "disabled")
            self.focus_btn.config(state="normal")
        self.advanced(sel)

    def advanced(self, sel):
        if not self.adv.get():
            self.adv_lbl.pack_forget()
            return
        lines = []
        if self.scene:
            s = self.scene.summary()
            lines += [f"scene {s['objects']} objects, {s['triangles']} triangles; roles {s['roles']}",
                      f"modes {s['modes']}", f"lvl {s['hashes']['lvl'][:16]}.."]
        if self.r:
            lines.append(f"textures {self.r.stats['textures']} ({self.r.stats['texels']} texels), "
                         f"hidden runtime-placed {self.r.stats['hidden_runtime_placed']}")
        if self.ctx:
            lines.append(f"GL {self.ctx.info['renderer']}")
        lines.append(f"load {self.timing['load_seconds']} s; frame {self.timing['last_ms']} ms "
                     f"(max {round(self.timing['max_ms'], 2)}) over {self.timing['frames']} frames")
        if sel and sel[0] == "actor":
            a = self.app.rmodel.actors[sel[1]]
            lines += [f"key {a['key']}", f"instance {a['instance']} status {a['status']}",
                      f"matrix {str(a.get('matrix_sha256'))[:16]}..", f"why: {a['why']}"]
        elif sel and sel[0] == "rwp":
            g = self.app.rmodel.graphs[sel[1][:3]]
            nd = g["nodes"][sel[1][3]]
            lines += [f"graph {g['key']} inst {sel[1][1]} var {sel[1][2]} node {sel[1][3]}",
                      f"status {g['status']}; graph at {g['graph_offset']:#x}",
                      f"waypoint {str(nd.get('waypoint_sha256'))[:16]}..", f"why: {nd['why'] or g['why']}"]
        elif sel and sel[0] == "vtx":
            lines += [f"collision vertex {sel[1]} region {self.app.project['region']}",
                      f"triangles {self.app.model.vertex_triangles(sel[1])}"]
        self.adv_lbl.config(text="\n".join(lines))
        self.adv_lbl.pack(fill="x", pady=(8, 0))

    def status(self, text, error=False):
        self.status_bar.config(text=text, fg="#c0392b" if error else "#333333")

    # ---------------------------------------------------------------------------------------------- picking
    def pick(self, x, y, radius=12):
        if not self.mats:
            return None
        proj, view, w, h = self.mats
        best = None
        for p, sel in self.picks:
            s = sg.project(proj, view, w, h, p)
            if s is None:
                continue
            d = math.hypot(s[0] - x, s[1] - y)
            if d <= radius and (best is None or (d, s[2]) < best[:2]):
                best = (d, s[2], sel)
        return best[2] if best else None

    def editable(self, sel):
        return bool(sel) and self.item_info(sel)[3]

    # ---------------------------------------------------------------------------------------------- mouse
    def on_press(self, e):
        self.vp.focus_set()
        hit = self.pick(e.x, e.y)
        self.drag = {"kind": "orbit", "x": e.x, "y": e.y, "hit": hit, "moved": False}
        if hit is not None and hit == self.app.sel:
            if not self.editable(hit):
                self.msg.config(text="This cannot be moved here.", fg="#c0392b")
                return
            start = self.preview_pos() or self.selected_pos(hit)
            self.drag.update(kind="move", p0=list(start), dz0=(self.preview or {}).get("dz", self.current_dz(hit)))

    def current_dz(self, sel):
        return self.app.project["terrain"].get(str(sel[1]), 0.0) if sel[0] == "vtx" else 0.0

    def on_drag(self, e):
        d = self.drag
        if not d:
            return
        if abs(e.x - d["x"]) + abs(e.y - d["y"]) > 3:
            d["moved"] = True
        if d["kind"] == "orbit":
            if d["moved"]:
                self.cam.orbit(e.x - d["x"], e.y - d["y"])
                d["x"], d["y"] = e.x, e.y
                self.request()
            return
        if d["kind"] != "move" or not d["moved"] or not self.mats:
            return
        sel = self.app.sel
        proj, view, w, h = self.mats
        k = 2 * self.cam.dist * math.tan(math.radians(self.cam.fov) / 2) / max(h, 1)
        if sel[0] == "vtx":
            lo, hi = self.app.editable_range(sel[1])
            dz = round(max(lo, min(hi, d["dz0"] - (e.y - d["y"]) * k)), 2)
            self.preview = {"sel": sel, "dz": dz}
            self.msg.config(text="Preview only: Apply keeps it, Cancel drops it.", fg="#555555")
        else:
            p0 = d["p0"]
            if e.state & 0x1:                                 # Shift: height only
                p = [p0[0], p0[1], p0[2] - (e.y - d["y"]) * k]
            else:                                             # the horizontal plane through the object
                o, r = sg.unproject_ray(proj, view, w, h, e.x, e.y)
                if abs(r[2]) < 1e-4:
                    return
                t = (p0[2] - o[2]) / r[2]
                if t <= 0:
                    return
                p = [o[0] + r[0] * t, o[1] + r[1] * t, p0[2]]
            self.preview = {"sel": sel, "pos": tuple(self.limit(sel, p))}
        self.build_overlays()
        self.refresh_panel()
        self.request()

    def limit(self, sel, p):
        """The place the editor would keep: within the tested bound around the original (shown, never hidden)."""
        orig = self.original_pos(sel)
        mx = core.MAX_ACTOR_MOVE if sel[0] == "actor" else core.MAX_WAYPOINT_MOVE
        dv = [a - b for a, b in zip(p, orig)]
        ln = math.sqrt(sum(c * c for c in dv))
        if ln > mx:
            self.msg.config(text=f"Held at {mx:g} units from the original place: the largest move tested in game.",
                            fg="#b9770e")
            return [b + c * (mx / ln) * (1 - 1e-6) for b, c in zip(orig, dv)]
        self.msg.config(text="Preview only: Apply keeps it, Cancel drops it.", fg="#555555")
        return p

    def on_release(self, e):
        d, self.drag = self.drag, None
        if d and d["kind"] == "orbit" and not d["moved"]:
            self.select(d["hit"])

    def select(self, sel):
        self.preview = None
        self.msg.config(text="")
        self.app.select(sel)                                  # the editor's selection and its own inspector

    def start_aux(self, e, kind):
        self.vp.focus_set()
        self.drag = {"kind": kind, "x": e.x, "y": e.y, "moved": True}

    def on_aux(self, e):
        d = self.drag
        if not d or d["kind"] not in ("look", "pan"):
            return
        if d["kind"] == "look":
            self.cam.look(e.x - d["x"], e.y - d["y"])
        else:
            self.cam.pan(e.x - d["x"], e.y - d["y"], max(self.vp.winfo_height(), 1))
        d["x"], d["y"] = e.x, e.y
        self.request()

    def end_aux(self, e):
        self.drag = None

    def on_wheel(self, e):
        self.cam.zoom(0.85 if e.delta > 0 else 1 / 0.85)
        self.request()

    # ---------------------------------------------------------------------------------------------- keyboard fly
    def fly_speed(self):
        lo, hi = self.scene.view_bounds() if self.scene else ([0, 0, 0], [100, 100, 100])
        return max(2.0, min(60.0, math.dist(lo, hi) * 0.12))     # world units per second

    def on_key(self, e):
        k = e.keysym.lower()
        if k in FLY_KEYS and not (e.state & 0x4):              # not with Ctrl (Ctrl+Z etc.)
            self.keys.add(k)
            self.fast = bool(e.state & 0x1)
            if self._fly_job is None:
                self._fly_t = time.perf_counter()
                self._fly_job = self.top.after(16, self._fly_step)
        elif k == "f":
            self.focus_selection()
        elif k == "home":
            self.fit_level()

    def on_key_release(self, e):
        self.keys.discard(e.keysym.lower())
        if not self.keys:
            self.stop_fly()

    def _fly_step(self):
        self._fly_job = None
        if not self.keys:
            return
        now = time.perf_counter()
        dt = min(0.05, now - self._fly_t)
        self._fly_t = now
        f = sum(FLY_KEYS[k][0] for k in self.keys)
        s = sum(FLY_KEYS[k][1] for k in self.keys)
        u = sum(FLY_KEYS[k][2] for k in self.keys)
        self.cam.fly(f, s, u, self.fly_speed() * (3.0 if self.fast else 1.0) * dt)
        self._draw()
        self._fly_job = self.top.after(16, self._fly_step)

    def stop_fly(self):
        self.keys.clear()
        if self._fly_job is not None:
            self.top.after_cancel(self._fly_job)
            self._fly_job = None

    def on_focus_out(self, e):
        """Losing focus ends every held key and drag immediately (a preview itself is kept)."""
        self.stop_fly()
        self.drag = None

    def escape(self):
        self.drag = None
        self.stop_fly()
        self.cancel()

    # ---------------------------------------------------------------------------------------------- camera helpers
    def fit_level(self):
        if self.scene:
            self.cam.fit(*self.scene.view_bounds())
            self.request()

    def fit_content(self):
        """The editable content of the current project: the central 80 % of actor positions, or the terrain area."""
        app = self.app
        if self.level_key()[0] == "remix" and app.rmodel and app.rmodel.actors:
            cols = [sorted(a["position"][k] for a in app.rmodel.actors.values()) for k in range(3)]
            q = lambda v, f: v[min(len(v) - 1, int(f * len(v)))]   # noqa: E731
            lo, hi = [q(c, 0.1) for c in cols], [q(c, 0.9) for c in cols]
        elif app.model:
            vs = [app.model.verts[v] for v in app.model.regions[app.project["region"]]["vertices"]]
            lo = [min(p[k] for p in vs) - 6 for k in range(3)]
            hi = [max(p[k] for p in vs) + 6 for k in range(3)]
        else:
            return self.fit_level()
        self.cam.fit(lo, hi)
        self.cam.pitch, self.cam.yaw = 35.0, -60.0
        self.request()

    def focus_selection(self):
        sel = self.app.sel
        p = (self.preview_pos() or self.selected_pos(sel)) if sel else None
        if p:
            self.cam.target, self.cam.dist = list(p), 12.0
            self.request()

    # ---------------------------------------------------------------------------------------------- commands
    def tool_changed(self):
        app = self.app
        self.preview = None
        if app.sel and TOOL_FOR_KIND.get(app.sel[0]) != self.tool.get():
            app.select(None)
        else:
            self.sync()

    def apply(self):
        p, app = self.preview, self.app
        if not p or p["sel"] != app.sel:
            return
        if "dz" in p:
            ok = app.set_vertex_dz(p["sel"][1], p["dz"])
        else:
            if app.mode != "remix":
                self.status("The editor is not editing a remix project; nothing was changed.", True)
                return
            ok = app.set_remix_position(p["sel"], list(p["pos"]), clamp=False)
        self.preview = None
        self.msg.config(text="Applied. Undo or Revert takes it back." if ok else "The editor refused this change.",
                        fg="#1d8a4a" if ok else "#c0392b")
        self.sync()

    def cancel(self):
        if self.preview:
            self.preview = None
            self.msg.config(text="Preview cancelled.", fg="#555555")
            self.sync()

    def revert(self):
        if self.app.sel:
            self.preview = None
            self.app.revert_selected()
            self.sync()

    def undo(self):
        if self.app.mode == "remix":
            self.preview = None
            self.app.cmd_undo()

    def choose_level(self, label):
        c = next(c for c in ed.CHOICES if c[2] == label)
        if c[:2] == self.app.current_choice()[:2]:
            return
        if self.asks() and self.app.dirty and not messagebox.askyesno(
                "Unsaved changes", "Discard the unsaved changes?",
                                                      parent=self.top):
            self.level_var.set(self.app.current_choice()[2])
            return
        self.preview = None
        self.app.set_mode(c[0], c[1])

    def save(self):
        app = self.app
        path = app.path or filedialog.asksaveasfilename(parent=self.top, defaultextension=".r3hdmap.json",
                                                        filetypes=ed.PROJECT_TYPES)
        if path:
            app.save_project(path)
            self.status(f"Saved {Path(path).name}.")

    def validate(self):
        self.app.validate_now()
        self.status(self.app.status_var.get(), "REFUSED" in self.app.status_var.get())

    def export(self):
        d = filedialog.askdirectory(parent=self.top, title="New or empty folder for the mod (mod.json)")
        if d:
            self.app.export_mod(d)
            self.status(self.app.status_var.get(), "REFUSED" in self.app.status_var.get())

    def import_mod(self):
        d = filedialog.askdirectory(parent=self.top, title="Exported mod folder (contains mod.json)")
        if d:
            self.app.import_mod(d)
            self.status(self.app.status_var.get(), "NOT IMPORTED" in self.app.status_var.get())

    def show_2d(self):
        self.app.root.deiconify()
        self.app.root.lift()


def open_editor(root, game_dir=None, project=None, level=None, show=True):
    """The editor with its 2D window hidden and this 3D window on top. show=False keeps the 3D window withdrawn
    (tests: nothing is mapped, handlers are called directly)."""
    app = ed.EditorApp(root, game_dir, project)
    root.withdraw()
    if project is None:
        app.set_mode("remix", level or "intro_20")
    top = tk.Toplevel(root)
    if not show:
        top.withdraw()
    view = Editor3D(app, top)
    root.protocol("WM_DELETE_WINDOW", view.close)
    return app, view


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("level", nargs="?", choices=sorted(core.REMIX_LEVELS))
    ap.add_argument("--project")
    ap.add_argument("--game-dir")
    ap.add_argument("--home", help="installation or portable folder: its data/content and mod folders are used")
    a = ap.parse_args(argv)
    lock = None
    if a.home:
        os.environ["R3HD_HOME"] = os.path.abspath(a.home)
        lock = ed.hold_home_lock(a.home)
    try:
        root = tk.Tk()
        open_editor(root, a.game_dir, a.project, a.level)
        root.mainloop()
    finally:
        ed.release_home_lock(lock)
    return 0


def standalone(game, level):
    return main(["--game-dir", str(game)] + ([level] if level in core.REMIX_LEVELS else []))


if __name__ == "__main__":
    sys.exit(main())
