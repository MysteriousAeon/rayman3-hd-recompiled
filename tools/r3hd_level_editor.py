#!/usr/bin/env python3
r"""G6-P29 (D-285) / G6-P30 (D-286) / G6-P31 (D-287): the constrained visual level editor for intro_20.

    installed / portable: Rayman 3 HD Recompiled - Level Editor (r3hd_launcher.exe --level-editor runs
                          app\python\pythonw.exe -B app\tools\r3hd_level_editor.py --home HOME)
    repository:           python -I tools/r3hd_level_editor.py [PROJECT.r3hdmap.json] [--game-dir DIR] [--home HOME]

Edits an EXISTING level only (intro_20); it does not create new maps. Production-supported (D-286): lowering the
verified start-floor vertices and the inserted FairyLight on graph A. Development-only (refused by the production game,
labelled in the editor): graph B and moved graph C waypoints. The viewport draws data decoded by the compiler's own
readers from your game files; validation and export call the authoritative level-patch compiler
(r3hd_level_editor_core); Import + enable goes through the mod manager (r3hd_mods). --home names the installation
(or portable folder) whose game data and mod folders are used; without it the mod manager's own defaults apply.

G6-P33 (D-289): a second mode, the actor and waypoint remix of intro_10, intro_15 or intro_20 (project format
r3hd-level-editor-project-v2, one level per project): the full static collision of the level (read-only), every placed
actor and actor-owned waypoint graph, classified VERIFIED / EXPERIMENTAL / LOCKED from the compiler's own eligibility
rules and recorded runtime evidence; edits compile to the existing actor-position / waypoint-position overrides.

G6-P35 (D-291): advisory ground readout and snap-to-ground preview from the static collision, evidence presets
(Presets menu), a route panel (graph list, storage owner, measured follower or UNKNOWN, sequence, per-node revert)
and advisory warnings after the compiler's verdict. None of it changes what the compiler accepts.
"""
import argparse
import math
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_level_editor_core as core  # noqa: E402
import r3hd_mods as rm  # noqa: E402

VIEWS = {"top": ("Top (X-Y)", 0, 1), "xz": ("Side (X-Z)", 0, 2), "yz": ("Side (Y-Z)", 1, 2)}
COL = {"bg": "#14171c", "grid": "#262b33", "grid_label": "#6c7480", "tri": "#3a414c", "tri_region": "#6f8aa8",
       "tri_edit": "#f0a040", "vtx": "#59616d", "editable": "#3fc380", "edited": "#f0a040", "sel": "#ffffff",
       "route": "#e05fd0", "route_orig": "#7a3f73", "graph_a": "#3fb6d8", "graph_b": "#9b8cf0",
       "fairy": "#ffe066", "probe": "#ff6b6b", "text": "#d8dde5"}
SCOPE_TEXT = (
    "Level Remix Editor: it changes three EXISTING levels of your own game data - intro_10, intro_15 and intro_20 - "
    "and saves the result as a mod. It does not create new levels or maps, and it is not a free-form level editor.\n\n"
    "Two modes (choose at the top right):\n"
    "  - intro_20 terrain + FairyLight level patch\n"
    "  - actor and waypoint remix of intro_10, intro_15 or intro_20\n\n"
    "While a mod made here is enabled the game awards no new achievements (achievements you already have are "
    "kept). Saves are never changed by the editor, but progress saved with a remix may depend on it: back up your "
    "saves first.\n\n"
    "Terrain + FairyLight patch (intro_20)\n"
    "Production-supported (the released game loads it):\n"
    "  - lowering the start-floor vertices (green points) within their verified range\n"
    "  - the inserted FairyLight following graph A\n\n"
    "Development-only (the released game refuses a mod that contains it):\n"
    "  - the FairyLight on graph B\n"
    "  - moved graph C waypoints\n\n"
    "Workflow: edit, Validate, File > Export mod folder, File > Import + enable exported mod, then start the game. "
    "Your game files and saves are never changed; disable or remove the mod in Settings > Mods.\n\n"
    "Actor and waypoint remix (intro_10, intro_15, intro_20; choose it at the top right):\n"
    "  - move existing actors (up to 25 units) and waypoints of actor-owned graphs (up to 6 units)\n"
    "  - VERIFIED items have runtime evidence; EXPERIMENTAL items are checked byte for byte but their behaviour "
    "at the new position has not been measured; LOCKED items cannot move (for example actors whose scripts place "
    "them)\n"
    "  - no new actors, no rotation, no new waypoints or arcs; one level per project and per mod\n"
    "  - an intro_20 remix mod beside an intro_20 terrain + FairyLight mod: the mod manager accepts them when their "
    "bytes do not overlap; one production run of that combination is SUPPORTED, not verified (E-523)\n"
    "  - the ground readout and Snap to ground use the static collision only: a geometric prediction, never a "
    "behaviour guarantee; presets carry exactly the evidence of their tested items\n"
    "Remix mods are production-compatible and marked as changing game logic.")
# G6-P33 (D-289): (mode, level, label) of the level / mode selector; the first entry is the default
CHOICES = [("patch", "intro_20", "intro_20 - terrain + FairyLight level patch"),
           ("remix", "intro_10", "intro_10 - actor and waypoint remix"),
           ("remix", "intro_15", "intro_15 - actor and waypoint remix"),
           ("remix", "intro_20", "intro_20 - actor and waypoint remix")]
# G6-P66 (D-315): development-only levels appear only while R3HD_DEV_EDITOR_LEVELS names them at start
CHOICES += [("remix", lv, f"{lv} - DEVELOPMENT ONLY: Powerz / Chameleon positions")
            for lv in core.dev_levels_enabled() if lv not in core.REMIX_LEVELS]
STATUS_TEXT = {"verified": "VERIFIED", "placement": "PLACEMENT VERIFIED", "supported": "ROUTE SUPPORTED",
               "experimental": "EXPERIMENTAL", "script_overridden": "SCRIPT-OVERRIDDEN", "locked": "LOCKED"}
COL.update({"actor_verified": "#3fc380", "actor_placement": "#9bd36a", "actor_experimental": "#e8c547",
            "actor_script_overridden": "#c0392b", "actor_locked": "#5c636e",
            "graph_verified": "#3fb6d8", "graph_supported": "#7fa8e8", "graph_experimental": "#e05fd0",
            "graph_locked": "#4a505a"})
REFUSED = ("locked", "script_overridden")   # G6-P34: statuses that cannot be edited


def json_bytes(p):
    import json
    return json.dumps(p, sort_keys=True).encode("utf-8")


PROJECT_TYPES = [("Level editor project", "*.r3hdmap.json"), ("JSON", "*.json"), ("All files", "*.*")]
# G6-P63: File > Open also reopens an exported editor mod (its mod.json); Save never offers that name
OPEN_TYPES = [("Project or exported mod", "*.r3hdmap.json mod.json")] + PROJECT_TYPES


def height_colour(z, lo, hi):
    t = 0.0 if hi <= lo else max(0.0, min(1.0, (z - lo) / (hi - lo)))
    r, g, b = int(40 + 150 * t), int(48 + 110 * t), int(70 + 30 * t)   # low: slate, high: sand
    return f"#{r:02x}{g:02x}{b:02x}"


class EditorApp:
    def __init__(self, root, game_dir=None, project_path=None):
        self.root = root
        self.game_dir = Path(game_dir) if game_dir else core.default_game_dir()
        self.model, self.load_error = None, None
        self.project, self.path, self.dirty = core.new_project(), None, False
        self.sel = None                      # ("vtx", index) | ("wp", node) | ("info", label)
        self.view = "top"
        self.scale, self.ox, self.oy, self.exag = 8.0, 0.0, 0.0, 1
        self.picks = []                      # [(sx, sy, kind, id, editable)]
        self.drag = None
        self.last_check = None               # (project bytes, result)
        self.canvas_w, self.canvas_h = 900, 720
        self.mode, self.remix, self.rmodels, self.rmodel, self.rload_error = "patch", None, {}, None, None
        self.undo, self.rz = [], (0.0, 1.0)
        self._build()
        self.load_level(self.game_dir)
        if project_path:
            self.open_project(project_path)
        self.fit("supported")
        self.refresh()

    def cmd_scope(self):
        messagebox.showinfo("Level editor scope", SCOPE_TEXT, parent=self.root)

    # ------------------------------------------------------------------------------------------ layout
    def _build(self):
        r = self.root
        r.title("Rayman 3 HD Recompiled - Level Remix Editor")
        r.geometry("1400x860")
        mb = tk.Menu(r)
        fm = tk.Menu(mb, tearoff=0)
        fm.add_command(label="New project", command=self.cmd_new, accelerator="Ctrl+N")
        fm.add_command(label="Open project...", command=self.cmd_open, accelerator="Ctrl+O")
        fm.add_command(label="Save project", command=self.cmd_save, accelerator="Ctrl+S")
        fm.add_command(label="Save project as...", command=self.cmd_save_as)
        fm.add_separator()
        fm.add_command(label="Game data folder...", command=self.cmd_game_dir)
        fm.add_separator()
        fm.add_command(label="Export level-patch declaration...", command=self.cmd_export_decl)
        fm.add_command(label="Export mod folder...", command=self.cmd_export_mod)
        fm.add_command(label="Import + enable exported mod...", command=self.cmd_import_mod)
        fm.add_separator()
        fm.add_command(label="Quit", command=self.cmd_quit)
        mb.add_cascade(label="File", menu=fm)
        em = tk.Menu(mb, tearoff=0)
        em.add_command(label="Undo (remix)", command=self.cmd_undo, accelerator="Ctrl+Z")
        em.add_command(label="Revert selected", command=self.revert_selected, accelerator="Del")
        em.add_command(label="Restore defaults (remove all edits)", command=self.cmd_restore)
        mb.add_cascade(label="Edit", menu=em)
        pm = tk.Menu(mb, tearoff=0)   # G6-P35 (D-291): edit sets from accepted runtime evidence
        for ps in core.PRESETS:
            pm.add_command(label=ps["title"], command=lambda i=ps["id"]: self.cmd_preset(i))
        pm.add_separator()
        pm.add_command(label=core.PATCH_PRESET["title"], command=lambda: self.cmd_preset(core.PATCH_PRESET["id"]))
        pm.add_separator()
        pm.add_command(label="What do the presets prove?", command=self.cmd_preset_help)
        mb.add_cascade(label="Presets", menu=pm)
        vm = tk.Menu(mb, tearoff=0)
        for k, (label, _, _) in VIEWS.items():
            vm.add_command(label=label, command=lambda k=k: self.set_view(k))
        vm.add_separator()
        vm.add_command(label="Fit supported area", command=lambda: (self.fit("supported"), self.redraw()))
        vm.add_command(label="Fit whole collision mesh", command=lambda: (self.fit("all"), self.redraw()))
        vm.add_separator()
        vm.add_command(label="Export view as SVG...", command=self.cmd_export_svg)
        mb.add_cascade(label="View", menu=vm)
        hm = tk.Menu(mb, tearoff=0)
        hm.add_command(label="What can this editor change?", command=self.cmd_scope)
        mb.add_cascade(label="Help", menu=hm)
        r.config(menu=mb)
        for seq, fn in (("<Control-n>", self.cmd_new), ("<Control-o>", self.cmd_open), ("<Control-s>", self.cmd_save),
                        ("<Control-z>", self.cmd_undo),
                        ("<Delete>", self.revert_selected), ("<f>", self.zoom_selection)):
            r.bind(seq, lambda e, fn=fn: fn())
        r.protocol("WM_DELETE_WINDOW", self.cmd_quit)

        main = ttk.PanedWindow(r, orient="horizontal")
        main.pack(fill="both", expand=True)
        left = ttk.Frame(main)
        bar = ttk.Frame(left)
        bar.pack(fill="x")
        self.view_var = tk.StringVar(value="top")
        for k, (label, _, _) in VIEWS.items():
            ttk.Radiobutton(bar, text=label, value=k, variable=self.view_var,
                            command=lambda: self.set_view(self.view_var.get())).pack(side="left", padx=4)
        ttk.Button(bar, text="Fit", command=lambda: (self.fit("supported"), self.redraw())).pack(side="left", padx=8)
        ttk.Button(bar, text="Zoom to selection (F)", command=self.zoom_selection).pack(side="left")
        ttk.Label(bar, text="  side-view height x").pack(side="left")
        self.exag_var = tk.StringVar(value="1")
        cb = ttk.Combobox(bar, values=("1", "5", "20", "50"), textvariable=self.exag_var, width=4, state="readonly")
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_exag(int(self.exag_var.get())))
        ttk.Label(bar, text="wheel: zoom  |  drag empty space: pan  |  click: select  |  drag a graph C waypoint: move"
                  ).pack(side="left", padx=8)
        self.canvas = tk.Canvas(left, bg=COL["bg"], width=self.canvas_w, height=self.canvas_h, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_motion)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        for b in ("<ButtonPress-2>", "<ButtonPress-3>"):
            self.canvas.bind(b, lambda e: self._pan_start(e))
        for b in ("<B2-Motion>", "<B3-Motion>"):
            self.canvas.bind(b, lambda e: self._pan_move(e))
        self.canvas.bind("<MouseWheel>", lambda e: self.zoom(1.2 if e.delta > 0 else 1 / 1.2, e.x, e.y))
        self.canvas.bind("<Button-4>", lambda e: self.zoom(1.2, e.x, e.y))
        self.canvas.bind("<Button-5>", lambda e: self.zoom(1 / 1.2, e.x, e.y))
        main.add(left, weight=3)

        side = ttk.Frame(main, padding=6)
        main.add(side, weight=1)
        self.side = side
        cf = ttk.Frame(side)
        cf.pack(fill="x", pady=(0, 4))
        ttk.Label(cf, text="Level / editing mode:").pack(side="left")
        self.choice_var = tk.StringVar(value=CHOICES[0][2])
        self.choice_cb = ttk.Combobox(cf, values=[c[2] for c in CHOICES], textvariable=self.choice_var,
                                      state="readonly", width=46)
        self.choice_cb.pack(side="left", padx=4)
        self.choice_cb.bind("<<ComboboxSelected>>", lambda e: self.cmd_choice(self.choice_var.get()))
        lf = ttk.LabelFrame(side, text="Level", padding=4)
        lf.pack(fill="x")
        self.level_frame = lf
        self.level_lbl = ttk.Label(lf, text="", wraplength=430, justify="left")
        self.level_lbl.pack(fill="x")
        row = ttk.Frame(lf)
        self.region_row = row
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Terrain region:").pack(side="left")
        self.region_var = tk.StringVar(value=self.project["region"])
        self.region_cb = ttk.Combobox(row, values=core.REGIONS, textvariable=self.region_var, state="readonly",
                                      width=18)
        self.region_cb.pack(side="left", padx=4)
        self.region_cb.bind("<<ComboboxSelected>>", lambda e: self.set_region(self.region_var.get()))

        sf = ttk.LabelFrame(side, text="Selection", padding=4)
        sf.pack(fill="x", pady=4)
        self.sel_lbl = ttk.Label(sf, text="Click a vertex or a waypoint in the map.", wraplength=430, justify="left")
        self.sel_lbl.pack(fill="x")
        self.terrain_box = ttk.Frame(sf)
        self.dz_var = tk.DoubleVar(value=-0.05)
        self.dz_scale = ttk.Scale(self.terrain_box, orient="horizontal", length=260, variable=self.dz_var,
                                  command=lambda v: self._on_dz(float(v)))
        self.dz_scale.grid(row=0, column=0, columnspan=3, sticky="we")
        self.dz_lbl = ttk.Label(self.terrain_box, text="")
        self.dz_lbl.grid(row=1, column=0, sticky="w")
        ttk.Button(self.terrain_box, text="Lower 0.01", command=lambda: self.nudge_dz(-0.01)).grid(row=1, column=1)
        ttk.Button(self.terrain_box, text="Raise 0.01", command=lambda: self.nudge_dz(0.01)).grid(row=1, column=2)
        self.route_box = ttk.Frame(sf)
        self.off_vars = [tk.StringVar(value="0") for _ in range(3)]
        for i, a in enumerate("XYZ"):
            ttk.Label(self.route_box, text=f"d{a}").grid(row=0, column=2 * i)
            e = ttk.Entry(self.route_box, textvariable=self.off_vars[i], width=8)
            e.grid(row=0, column=2 * i + 1, padx=2)
            e.bind("<Return>", lambda ev: self.apply_offset_entries())
        ttk.Button(self.route_box, text="Apply offset", command=self.apply_offset_entries).grid(row=1, column=0,
                                                                                               columnspan=3, pady=2)
        self.revert_btn = ttk.Button(sf, text="Revert this edit", command=self.revert_selected)

        self._build_remix(sf)
        ff = ttk.LabelFrame(side, text="Inserted FairyLight", padding=4)
        self.fairy_frame = ff
        ff.pack(fill="x", pady=4)
        self.fairy_on = tk.BooleanVar(value=True)
        ttk.Checkbutton(ff, text="Insert one FairyLight (a copy of original instance 2)", variable=self.fairy_on,
                        state="disabled").pack(anchor="w")
        ttk.Label(ff, text="Required by level-patch-v1: every patch inserts exactly one. It is a different actor from "
                           "original FairyLight instance 2, which flies graph C.", wraplength=430,
                  justify="left").pack(fill="x")
        self.graph_var = tk.IntVar(value=0)
        row = ttk.Frame(ff)
        row.pack(fill="x")
        ttk.Label(row, text="It follows:").pack(side="left")
        for k, name in core.GRAPH_NAMES.items():
            ttk.Radiobutton(row, text=name, value=k, variable=self.graph_var,
                            command=lambda: self.set_graph(self.graph_var.get())).pack(side="left", padx=4)
        self.fairy_lbl = ttk.Label(ff, text="", wraplength=430, justify="left")
        self.fairy_lbl.pack(fill="x")

        mf = ttk.LabelFrame(side, text="Project", padding=4)
        self.meta_frame = mf
        mf.pack(fill="x", pady=4)
        self.meta_vars, self.meta_entries = {}, {}
        for i, (k, label) in enumerate((("id", "Mod id"), ("name", "Name"), ("description", "Description"))):
            ttk.Label(mf, text=label).grid(row=i, column=0, sticky="w")
            v = tk.StringVar()
            e = ttk.Entry(mf, textvariable=v, width=44)
            e.grid(row=i, column=1, sticky="we", padx=2)
            e.bind("<FocusOut>", lambda ev, k=k: self.set_meta(k, self.meta_vars[k].get()))
            e.bind("<Return>", lambda ev, k=k: self.set_meta(k, self.meta_vars[k].get()))
            self.meta_vars[k] = v
            self.meta_entries[k] = e

        vf = ttk.LabelFrame(side, text="Validation (authoritative compiler)", padding=4)
        vf.pack(fill="both", expand=True, pady=4)
        row = ttk.Frame(vf)
        row.pack(fill="x")
        self.validate_btn = ttk.Button(row, text="Validate", command=self.validate_now)
        self.validate_btn.pack(side="left")
        self.export_btn = ttk.Button(row, text="Export mod...", command=self.cmd_export_mod)
        self.export_btn.pack(side="left", padx=4)
        self.import_btn = ttk.Button(row, text="Import + enable mod...", command=self.cmd_import_mod)
        self.import_btn.pack(side="left")
        self.prod_var = tk.StringVar(value="")
        self.prod_lbl = tk.Label(vf, textvariable=self.prod_var, anchor="w", justify="left", wraplength=430,
                                 font=("Segoe UI", 9, "bold"))
        self.prod_lbl.pack(fill="x", pady=2)
        self.status_var = tk.StringVar(value="")
        self.status_lbl = tk.Label(vf, textvariable=self.status_var, anchor="w", justify="left", wraplength=430)
        self.status_lbl.pack(fill="x", pady=2)
        self.report = tk.Text(vf, height=16, wrap="word", font=("Consolas", 9))
        self.report.pack(fill="both", expand=True)
        self.bottom = ttk.Label(r, text="", anchor="w", relief="sunken")
        self.bottom.pack(fill="x", side="bottom")

    # ------------------------------------------------------------------------------------------ G6-P33 remix mode
    def _build_remix(self, sf):
        """Remix inspector (inside the Selection frame) and the layers / finder frame (packed in remix mode only)."""
        self.remix_box = ttk.Frame(sf)
        self.pos_vars = [tk.StringVar(value="0") for _ in range(3)]
        for i, a in enumerate("XYZ"):
            ttk.Label(self.remix_box, text=a).grid(row=0, column=2 * i)
            e = ttk.Entry(self.remix_box, textvariable=self.pos_vars[i], width=10)
            e.grid(row=0, column=2 * i + 1, padx=2)
            e.bind("<Return>", lambda ev: self.apply_position_entries())
        ttk.Button(self.remix_box, text="Apply position", command=self.apply_position_entries).grid(
            row=1, column=0, columnspan=3, pady=2, sticky="w")
        nb = ttk.Frame(self.remix_box)
        nb.grid(row=2, column=0, columnspan=6, sticky="w")
        for i, a in enumerate("XYZ"):
            ttk.Button(nb, text=f"{a}-", width=3, command=lambda i=i: self.nudge_position(i, -1)).pack(side="left")
            ttk.Button(nb, text=f"{a}+", width=3, command=lambda i=i: self.nudge_position(i, 1)).pack(
                side="left", padx=(0, 6))
        ttk.Label(nb, text="step").pack(side="left")
        self.step_var = tk.StringVar(value="0.5")
        ttk.Combobox(nb, values=("0.1", "0.5", "1", "2", "5"), textvariable=self.step_var, width=4,
                     state="readonly").pack(side="left")
        # G6-P35 (D-291): ground observation and snap-to-ground (static collision only; advisory)
        pl = ttk.Frame(self.remix_box)
        pl.grid(row=3, column=0, columnspan=6, sticky="we", pady=(4, 0))
        self.ground_lbl = tk.Label(pl, text="", anchor="w", justify="left", wraplength=420, fg="#555555")
        self.ground_lbl.pack(fill="x")
        row = ttk.Frame(pl)
        row.pack(fill="x")
        ttk.Button(row, text="Snap to ground: preview", command=self.snap_preview).pack(side="left")
        self.snap_apply_btn = ttk.Button(row, text="Apply snap", command=self.snap_apply, state="disabled")
        self.snap_apply_btn.pack(side="left", padx=4)
        self.snap_lbl = tk.Label(pl, text="", anchor="w", justify="left", wraplength=420)
        self.snap_lbl.pack(fill="x")
        self.snap = None                     # (selection, project bytes, proposal)
        # G6-P35: route panel (shown for a selected graph or waypoint)
        self.route_panel = ttk.Frame(self.sel_lbl.master)
        self.route_info = tk.Label(self.route_panel, text="", anchor="w", justify="left", wraplength=420)
        self.route_info.pack(fill="x")
        self.route_nodes = tk.Listbox(self.route_panel, height=6, font=("Consolas", 9), exportselection=False)
        self.route_nodes.pack(fill="x")
        self.route_nodes.bind("<<ListboxSelect>>", lambda e: self.route_node_select())
        self.route_node_ids = []
        row = ttk.Frame(self.route_panel)
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="Zoom to route", command=self.zoom_route).pack(side="left")
        self.revert_wp_btn = ttk.Button(row, text="Revert this waypoint", command=self.revert_selected)
        self.revert_wp_btn.pack(side="left", padx=4)
        self.revert_route_btn = ttk.Button(row, text="Revert whole route", command=self.revert_route)
        self.revert_route_btn.pack(side="left")
        tk.Label(self.route_panel, text=core.NODE_INSERTION_TEXT, anchor="w", justify="left", wraplength=420,
                 fg="#777777", font=("Segoe UI", 8)).pack(fill="x")
        lay = ttk.LabelFrame(self.side, text="Layers and finder", padding=4)
        self.layer_frame = lay
        self.show = {k: tk.BooleanVar(value=v) for k, v in (("collision", True), ("actors", True), ("locked", False),
                                                             ("waypoints", True))}
        row = ttk.Frame(lay)
        row.pack(fill="x")
        for k, label in (("collision", "collision"), ("actors", "actors"), ("locked", "locked actors"),
                         ("waypoints", "waypoint graphs")):
            ttk.Checkbutton(row, text=label, variable=self.show[k], command=self.redraw).pack(side="left")
        row = ttk.Frame(lay)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Find:").pack(side="left")
        self.find_var = tk.StringVar()
        fe = ttk.Entry(row, textvariable=self.find_var, width=22)
        fe.pack(side="left", padx=4)
        fe.bind("<KeyRelease>", lambda e: self.fill_finder())
        self.editable_only = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="editable only", variable=self.editable_only, command=self.fill_finder).pack(
            side="left")
        self.finder = tk.Listbox(lay, height=8, font=("Consolas", 9), exportselection=False)
        self.finder.pack(fill="x")
        self.finder.bind("<<ListboxSelect>>", lambda e: self.finder_select())
        self.finder_items = []
        row = ttk.Frame(lay)
        row.pack(fill="x", pady=(4, 0))
        ttk.Label(row, text="Route:").pack(side="left")
        self.graph_sel_var = tk.StringVar()
        self.graph_cb = ttk.Combobox(row, textvariable=self.graph_sel_var, state="readonly", width=48)
        self.graph_cb.pack(side="left", padx=4)
        self.graph_cb.bind("<<ComboboxSelected>>", lambda e: self.select_graph_label(self.graph_sel_var.get()))
        self.graph_items = []

    def cur(self):
        return self.remix if self.mode == "remix" else self.project

    def current_choice(self):
        if self.mode == "patch":
            return CHOICES[0]
        return next(c for c in CHOICES if c[0] == "remix" and c[1] == self.remix["level"])

    def cmd_choice(self, label):
        c = next(c for c in CHOICES if c[2] == label)
        cur = self.current_choice()
        if c[:2] == cur[:2]:
            return
        if not self._confirm_discard():
            self.choice_var.set(cur[2])
            return
        self.set_mode(c[0], c[1])

    def set_mode(self, mode, level=None, project=None, path=None):
        """Switch between the intro_20 level patch (v1 project) and a remix project of one level (v2 project). One
        level per remix project; different levels are separate projects and separate mods."""
        self.sel, self.last_check, self.undo, self.drag = None, None, [], None
        if mode == "patch":
            self.mode = "patch"
            self.project = core.check_project(project or core.new_project())
        else:
            self.mode = "remix"
            self.remix = core.check_remix(project) if project else core.new_remix(level)
            self.load_remix_level(self.remix["level"])
        self.path, self.dirty = (Path(path) if path else None), False
        self._apply_mode_layout()
        self.choice_var.set(self.current_choice()[2])
        self.fit("supported")
        self.fill_finder()
        self.refresh()

    def load_remix_level(self, level):
        if level not in self.rmodels:
            try:
                self.rmodels[level] = (core.RemixModel(self.game_dir, level), None)
            except core.EditorError as x:
                self.rmodels[level] = (None, x)
        self.rmodel, self.rload_error = self.rmodels[level]
        if self.rmodel:
            zs = sorted(p[2] for t in self.rmodel.tris[::7] for p in t) or [0.0, 1.0]
            self.rz = (zs[len(zs) // 20], zs[-1 - len(zs) // 20])

    def _apply_mode_layout(self):
        if self.mode == "remix":
            self.region_row.pack_forget()
            self.fairy_frame.pack_forget()
            self.layer_frame.pack(fill="x", pady=4, before=self.meta_frame)
        else:
            self.layer_frame.pack_forget()
            self.region_row.pack(fill="x", pady=2)
            self.fairy_frame.pack(fill="x", pady=4, before=self.meta_frame)

    def remix_edits(self):
        r = self.remix
        out = {("actor", (a["model"], a["instance"])): tuple(a["position"]) for a in r["actors"]}
        out.update({("rwp", (w["model"], w["instance"], w["variable"], w["node"])): tuple(w["position"])
                    for w in r["waypoints"]})
        return out

    def remix_item(self, sel):
        """(original position, status, why, maximum move) of an actor / waypoint selection, or None."""
        m = self.rmodel
        if not m or not sel:
            return None
        kind, ident = sel
        if kind == "actor":
            a = m.actors.get(ident)
            return a and (a["position"], a["status"], a["why"], getattr(m, "max_actor_move", core.MAX_ACTOR_MOVE))
        if kind == "rwp":
            g = m.graphs.get(ident[:3])
            nd = g["nodes"][ident[3]] if g and ident[3] < len(g["nodes"]) else None
            if not nd:
                return None
            st = "locked" if g["status"] == "locked" or nd["why"] else g["status"]
            return nd["position"], st, (nd["why"] or g["why"]), core.MAX_WAYPOINT_MOVE
        return None

    def push_undo(self):
        self.undo = (self.undo + [core.check_remix(self.remix)])[-200:]

    def cmd_undo(self):
        if self.mode != "remix" or not self.undo:
            return
        self.remix = self.undo.pop()
        self.dirty = True
        self.refresh()

    def set_remix_position(self, sel, pos, record=True, full=True, clamp=True):
        """Move an editable actor / waypoint to pos (float32, limited to its evidence bound around the original); a
        position equal to the original removes the edit. Refused for locked items. clamp=False (typed values, snap,
        G6-P35): a position beyond the bound is refused unchanged instead of being pulled back."""
        it = self.remix_item(sel)
        if it is None:
            return False
        orig, st, why, mx = it
        if st in REFUSED and not (math.dist(pos, orig) == 0 if len(pos) == 3 else False):
            self.flash(f"{STATUS_TEXT[st]}: {why}" + (" Use Edit > Revert selected to remove an existing edit."
                                                      if sel in self.remix_edits() else ""), error=True)
            return False
        try:
            pos = [float(v) for v in pos]
        except (TypeError, ValueError):
            pos = [math.nan]
        if len(pos) != 3 or not all(math.isfinite(v) for v in pos):
            self.flash("Positions must be numbers.", error=True)
            return False
        d = [p - o for p, o in zip(pos, orig)]
        ln = math.sqrt(sum(v * v for v in d))
        if ln > mx + 1e-4 and not clamp:
            self.flash(f"Refused: ({pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}) is {ln:.3f} units from the original "
                       f"position; at most {mx:g} (the largest move with runtime evidence). Nothing was changed.",
                       error=True)
            return False
        if ln > mx:
            pos = [o + v * mx / ln for o, v in zip(orig, d)]
            self.flash(f"Limited to {mx:g} units from the original position (the largest move with runtime "
                       "evidence).")
        pos = [core.f32(v) for v in pos]
        dist = math.dist(pos, orig)
        if dist > mx:   # float32 rounding past the bound: pull back by a hair
            pos = [core.f32(o + (p - o) * (mx / dist) * (1 - 1e-6)) for p, o in zip(pos, orig)]
        if record:
            self.push_undo()
        r = dict(self.remix)
        kind, ident = sel
        if kind == "actor":
            key, inst = ident
            r["actors"] = [a for a in r["actors"] if (a["model"], a["instance"]) != ident]
            if math.dist(pos, orig) > 0:
                r["actors"].append({"model": key, "instance": inst,
                                    "matrix_sha256": self.rmodel.actors[ident]["matrix_sha256"], "position": pos})
        else:
            key, inst, var, node = ident
            r["waypoints"] = [w for w in r["waypoints"] if (w["model"], w["instance"], w["variable"], w["node"]) != ident]
            if math.dist(pos, orig) > 0:
                nd = self.rmodel.graphs[ident[:3]]["nodes"][node]
                r["waypoints"].append({"model": key, "instance": inst, "variable": var, "node": node,
                                       "waypoint_sha256": nd["waypoint_sha256"], "position": pos})
        self.remix = core.check_remix(r)
        self.dirty = True
        self.refresh(redraw=False)
        self.redraw_remix(static=full)
        return True

    def remix_position(self, sel):
        it = self.remix_item(sel)
        return self.remix_edits().get(sel, it[0] if it else None)

    def apply_position_entries(self):
        if self.mode != "remix" or not self.sel or self.sel[0] not in ("actor", "rwp"):
            return
        cur = self.remix_position(self.sel)
        try:   # an axis whose text still shows the current value keeps its exact float32 value
            pos = [c if v.get().strip() == f"{c:.3f}" else float(v.get()) for v, c in zip(self.pos_vars, cur)]
        except ValueError:
            self.flash("Positions must be numbers.", error=True)
            return
        self.set_remix_position(self.sel, pos, clamp=False)

    def nudge_position(self, axis, sign):
        if self.mode != "remix" or not self.sel or self.sel[0] not in ("actor", "rwp"):
            return
        pos = list(self.remix_position(self.sel))
        pos[axis] += sign * float(self.step_var.get())
        self.set_remix_position(self.sel, pos)

    def fill_finder(self):
        if self.mode != "remix" or not self.rmodel:
            self.finder.delete(0, "end")
            self.finder_items = []
            return
        q, only = self.find_var.get().strip().lower(), self.editable_only.get()
        edits = self.remix_edits()
        items = []
        for ident, a in sorted(self.rmodel.actors.items(), key=lambda x: (x[1]["name"], x[0][1])):
            if only and a["status"] == "locked":
                continue
            label = (f"{'*' if ('actor', ident) in edits else ' '}A {a['name']} #{ident[1]} "
                     f"[{STATUS_TEXT[a['status']]}]")
            items.append((label, ("actor", ident)))
        for ident, g in sorted(self.rmodel.graphs.items(), key=lambda x: (x[1]["name"], x[0][1:])):
            if only and g["status"] == "locked":
                continue
            n = sum(1 for k in edits if k[0] == "rwp" and k[1][:3] == ident)
            label = (f"{'*' if n else ' '}G {g['name']} #{ident[1]} var {ident[2]} ({len(g['nodes'])} nodes) "
                     f"[{STATUS_TEXT[g['status']]}]")
            items.append((label, ("rgraph", ident)))
        self.finder_items = [it for it in items if q in it[0].lower()]
        self.finder.delete(0, "end")
        for label, _ in self.finder_items:
            self.finder.insert("end", label)
        self.graph_items = [(f"{g['name']} #{ident[1]} var {ident[2]} - {len(g['nodes'])} nodes "
                             f"[{STATUS_TEXT[g['status']]}]", ident)
                            for ident, g in sorted(self.rmodel.graphs.items(),
                                                   key=lambda x: (x[1]["status"] == "locked", x[1]["name"], x[0][1:]))]
        self.graph_cb.config(values=[x[0] for x in self.graph_items])

    # ------------------------------------------------------------------------------------------ G6-P35 routes
    def selected_graph(self):
        if self.mode != "remix" or not self.sel or not self.rmodel:
            return None
        if self.sel[0] == "rgraph":
            return self.sel[1]
        if self.sel[0] == "rwp":
            return self.sel[1][:3]
        return None

    def select_graph_label(self, label):
        ident = next((i for t, i in self.graph_items if t == label), None)
        if ident is None:
            return
        self.sel = ("rgraph", ident)
        self.fit("selection")
        self.refresh()

    def route_node_select(self):
        cur = self.route_nodes.curselection()
        if not cur or not self.route_node_ids:
            return
        self.sel = ("rwp", self.route_node_ids[cur[0]])
        self.refresh()

    def zoom_route(self):
        gid = self.selected_graph()
        if gid is None:
            return
        keep = self.sel
        self.sel = ("rgraph", gid)
        self.fit("selection")
        self.sel = keep
        self.redraw()

    def revert_route(self):
        gid = self.selected_graph()
        if gid is None or not any(w for w in self.remix["waypoints"]
                                  if (w["model"], w["instance"], w["variable"]) == gid):
            return
        self.push_undo()
        self.remix = core.revert_route(self.remix, gid)
        self.dirty = True
        self.refresh()

    # ------------------------------------------------------------------------------------------ G6-P35 snap
    def snap_preview(self):
        """Compute (not apply) a snap-to-ground proposal for the selected actor / waypoint; shown on the map."""
        self.snap = None
        if self.mode != "remix" or not self.sel or self.sel[0] not in ("actor", "rwp") or not self.rmodel:
            return None
        orig, st, why, mx = self.remix_item(self.sel)
        if st in REFUSED:
            prop = {"ok": False, "code": "LOCKED", "text": f"Snap refused: {STATUS_TEXT[st]} ({why})."}
        else:
            prop = core.snap_proposal(self.rmodel.ground_index(), self.remix_position(self.sel), orig, mx)
        self.snap = (self.sel, json_bytes(self.remix), prop)
        self.refresh()
        return prop

    def snap_apply(self):
        s = self.snap
        if not s or s[0] != self.sel or s[1] != json_bytes(self.remix) or not s[2]["ok"]:
            self.flash("Preview the snap again: the selection or the project changed.", error=True)
            return False
        ok = self.set_remix_position(self.sel, s[2]["position"], clamp=False)
        self.snap = None
        if ok:
            self.flash("Snapped (Ctrl+Z undoes it). Geometry only: not a behaviour guarantee.")
        self.refresh()
        return ok

    # ------------------------------------------------------------------------------------------ G6-P35 presets
    def cmd_preset(self, pid, confirm=True):
        """Apply a preset: a remix preset adds its edits to the open remix of its level (switching level / mode
        first, after the usual discard question); the level-patch preset opens a new intro_20 patch project."""
        ps = core.preset_by_id(pid)
        if ps is core.PATCH_PRESET:
            if confirm and not self._confirm_discard():
                return False
            self.set_mode("patch", project=core.patch_preset())
            self.dirty = True
        else:
            if self.mode != "remix" or self.remix["level"] != ps["level"]:
                if confirm and not self._confirm_discard():
                    return False
                self.set_mode("remix", ps["level"])
            try:
                q = core.apply_preset(self.remix, pid, self.rmodel)
            except core.EditorError as x:
                self.flash(f"Preset refused: {x.detail}", error=True)
                return False
            self.push_undo()
            self.remix, self.dirty = q, True
        self.refresh()
        self.report.delete("1.0", "end")
        self.report.insert("end", f"Preset applied: {ps['title']}\n\nEvidence limit: {ps['limit']}\n\n"
                                  "Validate, then Export / Import + enable as usual (the same compiler as manual "
                                  "edits).\n")
        return True

    def cmd_preset_help(self):
        txt = "\n\n".join(f"{ps['title']}\n{ps['limit']}" for ps in core.PRESETS + [core.PATCH_PRESET])
        messagebox.showinfo("Presets and their evidence", txt + "\n\nA preset's evidence covers its exact items and "
                            "positions only, never every actor of the same type.", parent=self.root)

    def finder_select(self):
        cur = self.finder.curselection()
        if not cur:
            return
        self.sel = self.finder_items[cur[0]][1]
        self.fit("selection")
        self.refresh()

    def remix_refresh(self, redraw=True):
        r, m = self.remix, self.rmodel
        name = self.path.name if self.path else "unsaved project"
        self.root.title(f"Level Remix Editor - {r['level']} remix - {name}{' *' if self.dirty else ''}")
        try:
            focus = self.root.focus_get()
        except (KeyError, tk.TclError):
            focus = None
        for k, v in self.meta_vars.items():
            if focus is not self.meta_entries[k]:
                v.set(r["meta"][k])
        if m:
            c, hs = m.counts(), m.hashes
            self.level_lbl.config(text=(
                f"{r['level']} (existing level; {core.level_entry(r['level'])['note']})\n{self.game_dir}\n"
                f"exact supported originals: lvl {hs['lvl'][:8]}, ptr {hs['ptr'][:8]}, transit {hs['transit'][:8]}\n"
                f"actors: {c['actors_verified']} verified, {c['actors_placement']} placement-verified, "
                f"{c['actors_experimental']} experimental, "
                f"{c['actors_locked']} locked; waypoints: {c['waypoints_editable']} editable of {c['waypoints']} in "
                f"{c['graphs']} graphs; collision {c['triangles']} triangles (read-only)"))
        else:
            self.level_lbl.config(text=f"NOT LOADED: {self.rload_error.detail}\nUse File > Game data folder.")
        if self.snap and (self.snap[0] != self.sel or self.snap[1] != json_bytes(r)):
            self.snap = None
        self._remix_selection()
        stale = self.last_check is None or self.last_check[0] != json_bytes(r)
        probs = core.check_remix_level(r, m) if m else []
        exp = sum(1 for sel in self.remix_edits() if (self.remix_item(sel) or (0, ""))[1] == "experimental")
        nw = sum(1 for w in (core.remix_warnings(r, m) if m and not probs else []) if w[0] == "warn")
        if stale:
            self.status_var.set("Not validated since the last change. " + " ".join(f"[error] {t}" for t in probs)
                                + (f" {nw} advisory warning(s): Validate lists them." if nw else ""))
            self.status_lbl.config(fg="#c0392b" if probs else "#555555")
        st = "normal" if m else "disabled"
        self.validate_btn.config(state=st)
        self.export_btn.config(state=st)
        self.prod_var.set("Content: PRODUCTION-COMPATIBLE - in-place actor / waypoint positions (no level transaction); "
                          "marked as changing game logic (no new achievements while enabled)."
                          + (f" {exp} EXPERIMENTAL edit(s): gameplay behaviour not measured." if exp else "")
                          + (" Together with an intro_20 terrain + FairyLight mod: SUPPORTED by one run, not verified."
                             if r["level"] == "intro_20" else ""))
        self.prod_lbl.config(fg="#1d8a4a" if not exp else "#b9770e")
        self.bottom.config(text=(f"{'*' if self.dirty else ''}{name} | {r['level']} remix | actor edits "
                                 f"{len(r['actors'])}, waypoint edits {len(r['waypoints'])}"
                                 + (f" | {len(probs)} problem(s)" if probs else "")), foreground="")
        if redraw:
            self.redraw()

    def _route_panel(self, gid):
        """G6-P35: storage owner, follower (or UNKNOWN), sequence and per-node original / current of one graph."""
        m = self.rmodel
        g = m.graphs[gid]
        store, follower = core.graph_owner(m, gid)
        kind, seq = core.route_sequence(g)
        if kind in ("loop", "path"):
            s = " -> ".join(map(str, seq)) + (f" -> {seq[0]}" if kind == "loop" else "")
        elif kind == "branching":
            s = "branching: " + ", ".join(f"{i}->{j}" for i, j in seq)
        else:
            s = "no arcs decoded"
        cmp_ = core.route_compare(m, self.remix, gid)
        moved = [c for c in cmp_ if c["moved"] > 0]
        self.route_info.config(text=(
            f"Route {g['name']} #{gid[1]} var {gid[2]} [{STATUS_TEXT[g['status']]}]\n"
            f"Stored in: {store}\nFollowed by: {follower}\nSequence ({kind}): {s}\n"
            f"{len(moved)} of {len(g['nodes'])} waypoints moved (original route dashed on the map)"))
        self.route_nodes.delete(0, "end")
        self.route_node_ids = []
        for c in cmp_:
            nd = g["nodes"][c["node"]]
            if nd is None:
                continue
            lock = g["status"] == "locked" or nd["why"]
            o = c["original"]
            self.route_nodes.insert("end", f"{'*' if c['moved'] else ' '}n{c['node']:<3} "
                                           f"{'locked ' if lock else ''}moved {c['moved']:6.3f}  "
                                           f"orig ({o[0]:.2f}, {o[1]:.2f}, {o[2]:.2f})")
            self.route_node_ids.append(gid + (c["node"],))
            if self.sel == ("rwp", gid + (c["node"],)):
                self.route_nodes.selection_set("end")
        self.revert_route_btn.config(state="normal" if moved else "disabled")
        self.revert_wp_btn.config(state="normal" if self.sel and self.sel[0] == "rwp"
                                  and self.sel in self.remix_edits() else "disabled")
        self.route_panel.pack(fill="x", pady=(4, 0))

    def _remix_selection(self):
        for w in (self.terrain_box, self.route_box, self.remix_box, self.revert_btn, self.route_panel):
            w.pack_forget()
        s, m = self.sel, self.rmodel
        if not s or not m:
            self.sel_lbl.config(text="Click an actor (circle) or a waypoint (square), or use the finder. Green = "
                                     "verified, yellow = experimental (bytes verified, behaviour unmeasured), grey = "
                                     "locked.")
            return
        kind, ident = s
        if kind == "rgraph":
            g = m.graphs[ident]
            n_ed = sum(1 for nd in g["nodes"] if nd and not nd["why"] and g["status"] != "locked")
            self.sel_lbl.config(text=(
                f"Graph of {g['name']} (designer-variable instance {ident[1]}, variable {ident[2]}) "
                f"[{STATUS_TEXT[g['status']]}]\n{len(g['nodes'])} nodes, {len(g['edges'])} arcs, {n_ed} editable "
                f"waypoints\n{g['why']}\n"
                "Click one of its squares (or a node in the list) to move a waypoint."))
            self._route_panel(ident)
            return
        it = self.remix_item(s)
        orig, st, why, mx = it
        new = self.remix_position(s)
        if kind == "actor":
            a = m.actors[ident]
            head = f"Actor {a['name']} #{ident[1]} [{STATUS_TEXT[st]}]\nmodel {a['key']}"
        else:
            g = m.graphs[ident[:3]]
            outs = [j for i, j in g["edges"] if i == ident[3]]
            head = (f"Waypoint node {ident[3]} of graph {g['name']} #{ident[1]} var {ident[2]} [{STATUS_TEXT[st]}]\n"
                    f"arcs to nodes: {', '.join(map(str, outs)) or 'none decoded'}")
        moved = math.dist(new, orig)
        self.sel_lbl.config(text=(
            f"{head}\noriginal ({orig[0]:.3f}, {orig[1]:.3f}, {orig[2]:.3f})\n"
            f"proposed ({new[0]:.3f}, {new[1]:.3f}, {new[2]:.3f})  moved {moved:.3f} of at most {mx:g}\n"
            + (f"{STATUS_TEXT[st]}: {why}" if st in REFUSED else why)))
        if st in REFUSED:
            if kind == "rwp":
                self._route_panel(ident[:3])
            return
        for v, x in zip(self.pos_vars, new):
            v.set(f"{x:.3f}")
        gi = m.ground_index()
        q, oq = core.ground_query(gi, new), core.ground_query(gi, orig)
        self.ground_lbl.config(text=core.ground_text(q) + f"\n(original position: {oq['label']}"
                               + (f", {oq['dz']:.3f} above the surface below" if oq["dz"] is not None else "") + ")",
                               fg={"ground": "#1d6a3a", "ambiguous": "#b9770e", "below_surface": "#c0392b"}.get(
                                   q["state"], "#555555"))
        sp = self.snap[2] if self.snap and self.snap[0] == s else None
        self.snap_lbl.config(text=sp["text"] if sp else "", fg="#1d6a3a" if sp and sp["ok"] else "#b9770e")
        self.snap_apply_btn.config(state="normal" if sp and sp["ok"] else "disabled")
        self.remix_box.pack(fill="x")
        if moved > 0:
            self.revert_btn.pack(anchor="w")
        if kind == "rwp":
            self._route_panel(ident[:3])

    def fit_remix(self, what):
        m = self.rmodel
        if not m:
            return
        if what == "selection":
            if not self.sel:
                return
            if self.sel[0] == "rgraph":
                pts = [nd["position"] for nd in m.graphs[self.sel[1]]["nodes"] if nd]
            else:
                c = self.remix_position(self.sel)
                pts = [(c[0] - 15, c[1] - 15, c[2] - 15), (c[0] + 15, c[1] + 15, c[2] + 15)]
        elif what == "all":
            pts = [p for t in m.tris[::3] for p in t] or [a["position"] for a in m.actors.values()]
        else:
            pts = [a["position"] for a in m.actors.values() if a["status"] != "locked"]
            pts += [nd["position"] for g in m.graphs.values() if g["status"] != "locked" for nd in g["nodes"] if nd]
            pts = pts or [a["position"] for a in m.actors.values()] or [(0, 0, 0)]
        _, a, b = VIEWS[self.view]
        us, vs = [p[a] for p in pts], [p[b] for p in pts]
        w, h = max(us) - min(us) or 1, max(vs) - min(vs) or 1
        e = self.exag if self.view != "top" else 1
        self.scale = max(0.5, min(2000.0, (self.canvas_w - 140) / w, (self.canvas_h - 140) / (h * e)))
        self.ox = self.canvas_w / 2 - (min(us) + max(us)) / 2 * self.scale
        self.oy = self.canvas_h / 2 + (min(vs) + max(vs)) / 2 * self.vscale()

    def redraw_remix(self, static=True):
        c, W, H = self.canvas, self.canvas_w, self.canvas_h
        if static:
            c.delete("all")
        else:
            c.delete("dyn")
        self.picks = []
        m = self.rmodel
        if not m:
            c.delete("all")
            c.create_text(W / 2, H / 2, fill=COL["probe"], width=W - 80, font=("Segoe UI", 12),
                          text="No map: " + (self.rload_error.detail if self.rload_error else "not loaded") +
                          "\n\nThe editor only draws data decoded from your own level files. "
                          "Choose File > Game data folder.")
            return
        if static:
            self._grid()
            if self.show["collision"].get():
                zlo, zhi = self.rz
                for t in m.tris:
                    pts = [self.proj(p) for p in t]
                    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                    if max(xs) < 0 or min(xs) > W or max(ys) < 0 or min(ys) > H:
                        continue
                    fill = height_colour(sum(p[2] for p in t) / 3, zlo, zhi) if self.view == "top" else ""
                    c.create_polygon(*[q for xy in pts for q in xy], outline=COL["tri"], fill=fill, tags="static")
        edits = self.remix_edits()
        sel = self.sel
        sg = self.selected_graph()
        if self.show["waypoints"].get():
            for ident, g in m.graphs.items():
                col = COL["graph_" + g["status"]]
                cur = [None if nd is None else edits.get(("rwp", ident + (nd["node"],)), nd["position"])
                       for nd in g["nodes"]]
                pairs = g["edges"] or [(i, i + 1) for i in range(len(cur) - 1)]
                moved = any(("rwp", ident + (i,)) in edits for i in range(len(cur)))
                for i, j in pairs:
                    if cur[i] is None or cur[j] is None:
                        continue
                    if moved:
                        o1, o2 = g["nodes"][i]["position"], g["nodes"][j]["position"]
                        c.create_line(*self.proj(o1), *self.proj(o2), fill=COL["route_orig"], dash=(3, 3), tags="dyn",
                                      width=2 if sg == ident else 1)
                    c.create_line(*self.proj(cur[i]), *self.proj(cur[j]), fill=col, tags="dyn",
                                  width=3 if sg == ident else 1,
                                  arrow="last" if g["edges"] else None, arrowshape=(7, 8, 3))
                for i, p in enumerate(cur):
                    if p is None:
                        continue
                    sx, sy = self.proj(p)
                    if not (-10 < sx < W + 10 and -10 < sy < H + 10):
                        continue
                    nd = g["nodes"][i]
                    ok = g["status"] != "locked" and not nd["why"]
                    key = ("rwp", ident + (i,))
                    r = 4
                    if key in edits:
                        ox_, oy_ = self.proj(nd["position"])
                        c.create_rectangle(ox_ - 3, oy_ - 3, ox_ + 3, oy_ + 3, outline=COL["route_orig"], tags="dyn")
                    c.create_rectangle(sx - r, sy - r, sx + r, sy + r, fill=COL["edited"] if key in edits else col,
                                       outline=COL["sel"] if sel == key else "", width=2, tags="dyn")
                    if sel == key or key in edits or sg == ident:
                        c.create_text(sx + 7, sy + 8, anchor="w", fill=COL["text"], font=("Segoe UI", 8), tags="dyn",
                                      text=f"n{i}" if sg == ident and sel != key else f"{g['name']}#{ident[1]} n{i}")
                    self.picks.append((sx, sy, "rwp", ident + (i,), ok))
        if self.show["actors"].get():
            for ident, a in m.actors.items():
                if a["status"] == "locked" and not self.show["locked"].get():
                    continue
                key = ("actor", ident)
                p = edits.get(key, a["position"])
                sx, sy = self.proj(p)
                if not (-10 < sx < W + 10 and -10 < sy < H + 10):
                    continue
                if key in edits:
                    ox_, oy_ = self.proj(a["position"])
                    c.create_line(ox_, oy_, sx, sy, fill=COL["edited"], dash=(3, 2), tags="dyn")
                    c.create_oval(ox_ - 5, oy_ - 5, ox_ + 5, oy_ + 5, outline=COL["edited"], tags="dyn")
                r = 6
                c.create_oval(sx - r, sy - r, sx + r, sy + r, fill=COL["edited"] if key in edits else
                              COL["actor_" + a["status"]], outline=COL["sel"] if sel == key else "#000000",
                              width=3 if sel == key else 1, tags="dyn")
                if sel == key or key in edits:
                    c.create_text(sx + 9, sy - 9, anchor="w", fill=COL["text"], font=("Segoe UI", 9, "bold"),
                                  text=f"{a['name']} #{ident[1]}", tags="dyn")
                self.picks.append((sx, sy, "actor", ident, a["status"] not in REFUSED))
        if self.snap and self.snap[0] == sel and self.snap[2]["ok"]:   # G6-P35 snap preview: not applied yet
            fx, fy = self.proj(self.remix_position(sel))
            tx, ty = self.proj(self.snap[2]["position"])
            c.create_line(fx, fy, tx, ty, fill="#00d0ff", dash=(2, 2), arrow="last", tags=("dyn", "snap"))
            c.create_line(tx - 7, ty, tx + 7, ty, fill="#00d0ff", width=2, tags=("dyn", "snap"))
            c.create_line(tx, ty - 7, tx, ty + 7, fill="#00d0ff", width=2, tags=("dyn", "snap"))
            c.create_text(tx + 9, ty + 9, anchor="w", fill="#00d0ff", font=("Segoe UI", 8), tags=("dyn", "snap"),
                          text="snap preview (not applied)")
        items = [(COL["actor_verified"], "actor: VERIFIED (moved and behaved)"),
                 (COL["actor_placement"], "actor: PLACEMENT VERIFIED (behaviour unknown)"),
                 (COL["actor_experimental"], "actor: EXPERIMENTAL (bytes only)"),
                 (COL["actor_locked"], "actor: locked"), (COL["edited"], "edited (original: hollow)"),
                 (COL["graph_verified"], "waypoint graph: VERIFIED"),
                 (COL["graph_supported"], "waypoint graph: ROUTE SUPPORTED"),
                 (COL["graph_experimental"], "waypoint graph: EXPERIMENTAL"),
                 (COL["graph_locked"], "waypoint graph: locked")]
        c.create_rectangle(8, 8, 262, 14 + 15 * len(items), fill="#1d2128", outline=COL["grid"], tags="dyn")
        for i, (col, t) in enumerate(items):
            y = 18 + 15 * i
            c.create_oval(14, y - 4, 22, y + 4, fill=col, outline="", tags="dyn")
            c.create_text(28, y, anchor="w", fill=COL["text"], text=t, font=("Segoe UI", 8), tags="dyn")
        c.create_text(8, 22 + 15 * len(items), anchor="nw", fill=COL["grid_label"], font=("Segoe UI", 8), tags="dyn",
                      text=f"geometry: static collision decoded from your {self.remix['level']}.lvl (read-only)")

    def validate_remix_now(self, out_dir=None):
        if not self.rmodel:
            res = {"ok": False, "code": "TARGET_MISSING", "detail": str(self.rload_error.detail), "advice": ""}
        else:
            self.root.config(cursor="watch")
            self.root.update_idletasks()
            try:
                res = core.validate_remix(self.remix, self.game_dir, out_dir, model=self.rmodel)
            finally:
                self.root.config(cursor="")
        self.last_check = (json_bytes(self.remix), res)
        self.report.delete("1.0", "end")
        if res["ok"]:
            msg = (f"VALID - {res['ranges']} same-size range(s); production-compatible in-place edits (gameplay mod).")
            if out_dir:
                msg = (f"EXPORTED mod folder {out_dir} (mod.json, mod id {res['manifest']['id']}). It is NOT imported "
                       "or enabled yet: use 'Import + enable mod...' (the game applies enabled mods at its next start).")
            self.status_var.set(msg)
            self.status_lbl.config(fg="#1d8a4a")
            self.report.insert("end", res["text"])
        else:
            self.status_var.set(f"REFUSED ({res['code']}) - nothing was written.")
            self.status_lbl.config(fg="#c0392b")
            self.report.insert("end", f"Compiler / editor reason:\n{res['detail']}\n\n{res.get('advice', '')}\n")
        if self.rmodel and res.get("code") not in ("UNSUPPORTED", "BAD_PROJECT"):
            ws = core.remix_warnings(self.remix, self.rmodel)
            res["warnings"] = ws
            if ws:   # G6-P35: advisory only; the verdict above is the compiler's and is not changed by these
                self.report.insert("end", "\nAdvisory warnings (geometry and evidence; they do not change the "
                                          "verdict above):\n" + "".join(f"  [{sv}] {t}\n" for sv, _, t in ws))
        return res

    # ------------------------------------------------------------------------------------------ level / project
    def load_level(self, game_dir):
        self.game_dir = Path(game_dir)
        try:
            self.model, self.load_error = core.LevelModel(self.game_dir), None
        except core.EditorError as x:
            self.model, self.load_error = None, x

    def set_project(self, p, path=None, dirty=False):
        self.project, self.path, self.dirty = core.check_project(p), path, dirty
        self.sel, self.last_check = None, None
        self.refresh()

    def edited(self):
        self.dirty = True
        self.refresh()

    def set_region(self, region):
        if region == self.project["region"]:
            return
        p = dict(self.project, region=region)
        allowed = self.model.regions[region]["vertices"] if self.model else ()
        lo, hi = rm.terrain_region(core.LEVEL, region)["delta_z"]
        vr = rm.terrain_region(core.LEVEL, region).get("vertex_delta_z", {})
        p["terrain"] = {v: dz for v, dz in self.project["terrain"].items() if int(v) in allowed
                        and vr.get(int(v), (lo, hi))[0] <= dz <= vr.get(int(v), (lo, hi))[1]}
        dropped = sorted(set(self.project["terrain"]) - set(p["terrain"]), key=int)
        self.project = core.check_project(p)
        if self.sel and self.sel[0] == "vtx" and self.sel[1] not in allowed:
            self.sel = None
        self.edited()
        if dropped:
            self.flash(f"Region {region}: removed edits of vertices {', '.join(dropped)} (not editable there).")

    def set_graph(self, g):
        if g != self.project["fairylight"]["follow_graph_of"]:
            self.project = core.check_project(dict(self.project, fairylight={"follow_graph_of": g}))
            self.edited()

    def set_meta(self, key, value):
        cur = self.cur()
        if cur["meta"].get(key) == value:
            return
        p = dict(cur, meta=dict(cur["meta"], **{key: value}))
        try:
            if self.mode == "remix":
                self.remix = core.check_remix(p)
            else:
                self.project = core.check_project(p)
        except core.EditorError as x:
            self.meta_vars[key].set(cur["meta"][key])
            self.flash(f"Not changed: {x.detail}", error=True)
            return
        self.edited()

    def editable_range(self, v):
        reg = rm.terrain_region(core.LEVEL, self.project["region"])
        lo, hi = reg["delta_z"]
        return reg.get("vertex_delta_z", {}).get(v, (lo, hi))

    def set_vertex_dz(self, v, dz):
        """Lower editable vertex v by dz (clamped to its verified range, 0.01 steps); refused for others."""
        if not self.model or v not in self.model.regions[self.project["region"]]["vertices"]:
            self.flash(f"Vertex {v} is not editable in {self.project['region']}.", error=True)
            return False
        lo, hi = self.editable_range(v)
        dz = round(max(lo, min(hi, dz)), 2)
        t = dict(self.project["terrain"], **{str(v): dz})
        self.project = core.check_project(dict(self.project, terrain=t))
        self.edited()
        return True

    def set_waypoint_offset(self, n, off):
        """Move graph C node n by off (scaled down to the 6-unit limit); a zero offset reverts the waypoint."""
        off = [float(v) for v in off]
        if not all(math.isfinite(v) for v in off):
            self.flash("Offsets must be numbers.", error=True)
            return False
        mx = rm.LEVEL_PATCH_ROUTES[core.LEVEL]["max_move"]
        length = math.sqrt(sum(v * v for v in off))
        if length > mx:
            off = [v * mx / length for v in off]
            self.flash(f"Graph C node {n}: limited to {mx:g} units from its original position.")
        off = [round(v, 3) for v in off]
        r = dict(self.project["route"])
        if math.sqrt(sum(v * v for v in off)) == 0:
            r.pop(str(n), None)
        else:
            r[str(n)] = off
        self.project = core.check_project(dict(self.project, route=r))
        self.edited()
        return True

    def revert_selected(self):
        if not self.sel:
            return
        if self.mode == "remix":
            it = self.remix_item(self.sel)
            if it and self.sel in self.remix_edits():
                self.set_remix_position(self.sel, it[0])
            return
        k, i = self.sel
        if k == "vtx" and str(i) in self.project["terrain"]:
            t = {v: d for v, d in self.project["terrain"].items() if v != str(i)}
            self.project = core.check_project(dict(self.project, terrain=t))
            self.edited()
        elif k == "wp" and str(i) in self.project["route"]:
            self.set_waypoint_offset(i, (0, 0, 0))

    def restore_defaults(self):
        if self.mode == "remix":
            self.push_undo()
            self.remix = core.check_remix(dict(self.remix, actors=[], waypoints=[]))
            return self.edited()
        self.project = core.check_project(dict(self.project, terrain={}, route={}, fairylight={"follow_graph_of": 0}))
        self.edited()

    def open_project(self, path):
        """A project file, or (G6-P63) an exported editor mod - its folder or mod.json - reopened as a new unsaved
        project: it keeps no path, so Save asks for a project file and never writes over the mod."""
        try:
            kind, p, source = core.open_file(path)
        except (core.EditorError, OSError) as x:
            self.flash(f"Could not open {Path(path).name}: {getattr(x, 'detail', x)}", error=True)
            return False
        keep = None if source == "mod" else Path(path)
        if kind == "v2":
            self.set_mode("remix", project=p, path=keep)
        else:
            if self.mode != "patch":
                self.set_mode("patch")
            self.set_project(p, keep)
        if source == "mod":
            self.flash(f"Opened the exported mod {p['meta']['id']} as a new project (not saved yet). Save writes a "
                       "project file; Export writes a new mod folder.")
        return True

    def save_project(self, path):
        if self.mode == "remix":
            core.save_remix(self.remix, path)
        else:
            core.save_project(self.project, path)
        self.path, self.dirty = Path(path), False
        self.refresh()

    # ------------------------------------------------------------------------------------------ menu commands
    def _confirm_discard(self):
        return not self.dirty or messagebox.askyesno("Unsaved changes", "Discard the unsaved changes?")

    def cmd_new(self):
        if self._confirm_discard():
            if self.mode == "remix":
                self.set_mode("remix", self.remix["level"])
            else:
                self.set_project(core.new_project())

    def cmd_open(self):
        if not self._confirm_discard():
            return
        f = filedialog.askopenfilename(filetypes=OPEN_TYPES)
        if f:
            self.open_project(f)

    def cmd_save(self):
        if self.path is None:
            return self.cmd_save_as()
        self.save_project(self.path)

    def cmd_save_as(self):
        f = filedialog.asksaveasfilename(defaultextension=".r3hdmap.json", filetypes=PROJECT_TYPES)
        if f:
            self.save_project(f)

    def cmd_restore(self):
        if messagebox.askyesno("Restore defaults", "Remove every actor and waypoint edit?" if self.mode == "remix"
                               else "Remove every terrain and route edit and select graph A?"):
            self.restore_defaults()

    def cmd_game_dir(self):
        d = filedialog.askdirectory(title="Folder that contains GAMEDATAbin (your extracted game data)")
        if d:
            self.load_level(d)
            self.rmodels = {}
            if self.mode == "remix":
                self.load_remix_level(self.remix["level"])
                self.fill_finder()
            self.fit("supported")
            self.refresh()

    def cmd_export_decl(self):
        if self.mode == "remix":
            self.flash("A remix project has no level-patch declaration; use Export mod folder.", error=True)
            return
        f = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Level patch", "*.json")])
        if f:
            core.export_declaration(self.project, f)
            self.flash(f"Wrote the level-patch-v1 declaration {Path(f).name} (not validated; use Validate).")

    def cmd_export_mod(self):
        d = filedialog.askdirectory(title="New or empty folder for the mod (mod.json)")
        if d:
            self.export_mod(d)

    def cmd_export_svg(self):
        f = filedialog.asksaveasfilename(defaultextension=".svg", filetypes=[("SVG image", "*.svg")])
        if f:
            self.export_svg(f)

    def export_svg(self, path):
        """The current viewport as an SVG image (the canvas items as drawn)."""
        c, out = self.canvas, []
        esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")   # noqa: E731
        for it in c.find_all():
            t, xy = c.type(it), c.coords(it)
            g = lambda o: c.itemcget(it, o)   # noqa: E731
            dash = ' stroke-dasharray="4,3"' if t in ("line", "polygon", "oval") and g("dash") else ""
            if t == "line":
                pts = " ".join(f"{xy[i]:.1f},{xy[i + 1]:.1f}" for i in range(0, len(xy), 2))
                out.append(f'<polyline points="{pts}" fill="none" stroke="{g("fill")}" stroke-width="{g("width")}"'
                           f"{dash}/>")
            elif t == "polygon":
                pts = " ".join(f"{xy[i]:.1f},{xy[i + 1]:.1f}" for i in range(0, len(xy), 2))
                out.append(f'<polygon points="{pts}" fill="{g("fill") or "none"}" stroke="{g("outline") or "none"}" '
                           f'stroke-width="{g("width")}"{dash}/>')
            elif t in ("oval", "rectangle"):
                x0, y0, x1, y1 = xy
                st = f'fill="{g("fill") or "none"}" stroke="{g("outline") or "none"}" stroke-width="{g("width")}"'
                if t == "oval":
                    out.append(f'<ellipse cx="{(x0 + x1) / 2:.1f}" cy="{(y0 + y1) / 2:.1f}" rx="{(x1 - x0) / 2:.1f}" '
                               f'ry="{(y1 - y0) / 2:.1f}" {st}{dash}/>')
                else:
                    out.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" {st}/>')
            elif t == "text":
                anc = g("anchor")
                ta = "end" if "e" in anc else "start" if "w" in anc else "middle"
                dy = "0.9em" if anc.startswith("n") else "0" if anc.startswith("s") else "0.35em"
                out.append(f'<text x="{xy[0]:.1f}" y="{xy[1]:.1f}" dy="{dy}" fill="{g("fill")}" text-anchor="{ta}" '
                           f'font-family="Segoe UI, sans-serif" font-size="11">{esc(g("text"))}</text>')
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.canvas_w}" height="{self.canvas_h}">'
               f'<rect width="100%" height="100%" fill="{COL["bg"]}"/>' + "".join(out) + "</svg>\n")
        core.atomic_write(path, svg.encode("utf-8"))

    def cmd_import_mod(self):
        d = filedialog.askdirectory(title="Exported mod folder (contains mod.json)")
        if d:
            self.import_mod_asking(d, self.root)

    def import_mod_asking(self, folder, parent, paths=None):
        """G6-P63: import; when another mod already has the id, a person decides in a dialog whether to replace it.
        A window that is not viewable (tests, withdrawn) never opens a dialog and leaves the refusal in place."""
        res = self.import_mod(folder, paths)
        if res.get("code") != "EXISTS":
            return res
        try:
            viewable = bool(parent.winfo_viewable())
        except tk.TclError:
            viewable = False
        if viewable and messagebox.askyesno(
                "Replace installed mod?", f"{res['detail']}\n\nReplace it with the mod in {Path(folder).name}? The "
                "installed copy is removed; its place in the mod order is kept.", icon="warning", default="no",
                parent=parent):
            res = self.import_mod(folder, paths, replace=True)
        return res

    def import_mod(self, folder, paths=None, replace=False):
        """Through the existing mod manager (r3hd_mods import --enable); the game applies it at its next start.
        G6-P63: an installed mod with the same id is replaced only with replace=True."""
        res = core.import_mod(folder, paths, replace=replace)
        self.report.delete("1.0", "end")
        if res["ok"]:
            r = res["result"]
            what = (" (the same package was already installed)" if r.get("unchanged") else
                    f" (replaced the installed {r['id']})" if r.get("replaced") else "")
            self.status_var.set(f"IMPORTED and ENABLED in {res['mods']}{what}. The game applies it at its next "
                                "start; a production game accepts only production-supported content.")
            self.status_lbl.config(fg="#1d8a4a")
        else:
            self.status_var.set(f"NOT IMPORTED ({res['code']}) - nothing was changed.")
            self.status_lbl.config(fg="#c0392b")
            self.report.insert("end", res["detail"] + "\n" + (f"\n{res['advice']}\n" if res.get("advice") else ""))
        return res

    def cmd_quit(self):
        if self._confirm_discard():
            self.root.destroy()

    # ------------------------------------------------------------------------------------------ validation / export
    def validate_now(self):
        if self.mode == "remix":
            return self.validate_remix_now()
        if not self.model:
            self.show_result({"ok": False, "code": "TARGET_MISSING", "detail": str(self.load_error.detail), "advice": ""})
            return None
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            res = core.validate(self.project, self.game_dir)
        finally:
            self.root.config(cursor="")
        self.last_check = (core.project_bytes(self.project), res)
        self.show_result(res)
        return res

    def export_mod(self, out_dir):
        if self.mode == "remix":
            return self.validate_remix_now(out_dir)
        res = core.export_mod(self.project, self.game_dir, out_dir)
        self.last_check = (core.project_bytes(self.project), res)
        self.show_result(res, exported=out_dir if res["ok"] else None)
        return res

    def show_result(self, res, exported=None):
        self.report.delete("1.0", "end")
        if res["ok"]:
            r = res["report"]
            dev = r.get("development_only", True)
            msg = (f"VALID - transaction {r['transaction']['id']}, {r['range_count']} ranges. "
                   + ("DEVELOPMENT-ONLY content: the production game refuses it." if dev else
                      "Production-supported content (D-286)."))
            if exported:
                msg = (f"EXPORTED mod folder {exported} (mod.json, mod id {r['mod']['id']}). It is NOT imported or "
                       "enabled yet: use 'Import + enable mod...' (the game applies enabled mods at its next start)"
                       + (", on a development runtime build only." if dev else "."))
            self.status_var.set(msg)
            self.status_lbl.config(fg="#1d8a4a")
            self.report.insert("end", res["text"])
        else:
            self.status_var.set(f"REFUSED ({res['code']}) - nothing was written.")
            self.status_lbl.config(fg="#c0392b")
            self.report.insert("end", f"{res['detail']}\n\n{res.get('advice', '')}\n")
        self.refresh(redraw=False)

    # ------------------------------------------------------------------------------------------ view transform
    def _on_resize(self, e):
        self.canvas_w, self.canvas_h = e.width, e.height
        self.redraw()

    def proj(self, p):
        _, a, b = VIEWS[self.view]
        return self.ox + p[a] * self.scale, self.oy - p[b] * self.vscale()

    def vscale(self):
        return self.scale * (self.exag if self.view != "top" else 1)

    def unproj(self, sx, sy):
        return (sx - self.ox) / self.scale, (self.oy - sy) / self.vscale()

    def set_view(self, v):
        self.view = v
        self.view_var.set(v)
        self.fit("supported")
        self.redraw()

    def fit(self, what):
        if self.mode == "remix":
            return self.fit_remix(what)
        if not self.model:
            return
        m = self.model
        if what == "selection" and self.sel and self.sel[0] in ("vtx", "wp"):
            terrain = {int(v): d for v, d in self.project["terrain"].items()}
            c = (m.edited_verts(terrain)[self.sel[1]] if self.sel[0] == "vtx"
                 else m.edited_route({int(k): v for k, v in self.project["route"].items()})[self.sel[1]])
            r = 4.0 if self.sel[0] == "vtx" else 10.0
            pts = [(c[0] - r, c[1] - r, c[2] - r / max(self.exag, 1)), (c[0] + r, c[1] + r, c[2] + r / max(self.exag, 1))]
        elif what == "selection":
            return
        elif what == "all":
            pts = list(m.verts)
        else:
            reg = set(m.regions["start-floor-v2"]["vertices"])
            near = {i for t, ix in m.tris.items() if reg & set(ix) for i in ix}
            pts = [m.verts[i] for i in near] + list(m.route) + [p for _, p in m.probes] + [m.fairy_source]
        _, a, b = VIEWS[self.view]
        us, vs = [p[a] for p in pts], [p[b] for p in pts]
        w, h = max(us) - min(us) or 1, max(vs) - min(vs) or 1
        e = self.exag if self.view != "top" else 1
        self.scale = min((self.canvas_w - 140) / w, (self.canvas_h - 140) / (h * e))
        self.ox = self.canvas_w / 2 - (min(us) + max(us)) / 2 * self.scale
        self.oy = self.canvas_h / 2 + (min(vs) + max(vs)) / 2 * self.vscale()

    def zoom_selection(self):
        self.fit("selection")
        self.redraw()

    def set_exag(self, e):
        self.exag = e
        self.exag_var.set(str(e))
        if self.sel:
            self.fit("selection")
        else:
            self.fit("supported")
        self.redraw()

    def zoom(self, f, x, y):
        u, v = self.unproj(x, y)
        self.scale = max(0.5, min(2000.0, self.scale * f))
        self.ox, self.oy = x - u * self.scale, y + v * self.vscale()
        self.redraw()

    def _pan_start(self, e):
        self.drag = ("pan", e.x, e.y)

    def _pan_move(self, e):
        if self.drag and self.drag[0] == "pan":
            self.ox += e.x - self.drag[1]
            self.oy += e.y - self.drag[2]
            self.drag = ("pan", e.x, e.y)
            self.redraw()

    # ------------------------------------------------------------------------------------------ interaction
    def pick(self, x, y, radius=9):
        best = None
        for sx, sy, kind, ident, editable in self.picks:
            d = math.hypot(sx - x, sy - y)
            if d <= radius and (best is None or (editable, -d) > (best[0], -best[1])):
                best = (editable, d, kind, ident)
        return (best[2], best[3]) if best else None

    def select(self, s):
        self.sel = s
        self.refresh()

    def on_press(self, e):
        s = self.pick(e.x, e.y)
        if s is None:
            self._pan_start(e)
            return
        if self.mode == "remix":
            self.sel = s
            it = self.remix_item(s)
            self.drag = None
            if it and it[1] not in REFUSED:
                self.push_undo()
                self.drag = ("remix", s, e.x, e.y, list(self.remix_position(s)))
            self.refresh(redraw=False)
            self.redraw_remix(static=False)
            return
        self.select(s)
        if s[0] == "wp":
            n = s[1]
            self.drag = ("wp", n, e.x, e.y, list(self.project["route"].get(str(n), [0.0, 0.0, 0.0])))
        else:
            self.drag = None

    def on_motion(self, e):
        if not self.drag:
            return
        if self.drag[0] == "pan":
            return self._pan_move(e)
        if self.drag[0] == "remix":
            _, s, x0, y0, p0 = self.drag
            _, a, b = VIEWS[self.view]
            p = list(p0)
            p[a] += (e.x - x0) / self.scale
            p[b] -= (e.y - y0) / self.vscale()
            self.set_remix_position(s, p, record=False, full=False)
            return
        _, n, x0, y0, off0 = self.drag
        _, a, b = VIEWS[self.view]
        off = list(off0)
        off[a] += (e.x - x0) / self.scale
        off[b] -= (e.y - y0) / self.vscale()
        mx = rm.LEVEL_PATCH_ROUTES[core.LEVEL]["max_move"]
        ln = math.sqrt(sum(v * v for v in off))
        if ln > mx:
            off = [v * mx / ln for v in off]
        self.set_waypoint_offset(n, off)

    def on_release(self, e):
        self.drag = None

    def _on_dz(self, v):
        if self.sel and self.sel[0] == "vtx" and not self._updating:
            self.set_vertex_dz(self.sel[1], v)

    def nudge_dz(self, d):
        if self.sel and self.sel[0] == "vtx":
            cur = self.project["terrain"].get(str(self.sel[1]))
            self.set_vertex_dz(self.sel[1], (cur if cur is not None else -0.04) + d)

    def apply_offset_entries(self):
        if not (self.sel and self.sel[0] == "wp"):
            return
        try:
            off = [float(v.get()) for v in self.off_vars]
        except ValueError:
            self.flash("Offsets must be numbers.", error=True)
            return
        self.set_waypoint_offset(self.sel[1], off)

    def flash(self, text, error=False):
        self.bottom.config(text=text, foreground="#c0392b" if error else "")

    # ------------------------------------------------------------------------------------------ refresh / draw
    _updating = False

    def refresh(self, redraw=True):
        if self.mode == "remix":
            return self.remix_refresh(redraw)
        p = self.project
        name = self.path.name if self.path else "unsaved project"
        self.root.title(f"Level Remix Editor - {name}{' *' if self.dirty else ''}")
        self.region_var.set(p["region"])
        self.graph_var.set(p["fairylight"]["follow_graph_of"])
        try:
            focus = self.root.focus_get()
        except (KeyError, tk.TclError):
            focus = None
        for k, v in self.meta_vars.items():
            if focus is not self.meta_entries[k]:
                v.set(p["meta"][k])
        if self.model:
            hs = self.model.hashes
            self.level_lbl.config(text=f"intro_20 (existing level; this editor cannot create new levels)\n"
                                       f"{self.game_dir}\nexact supported originals: lvl {hs['lvl_sha256'][:8]}, "
                                       f"ptr {hs['ptr_sha256'][:8]}, transit {hs['transit_sha256'][:8]}")
            fs = self.model.fairy_source
            self.fairy_lbl.config(text=f"Source: original instance 2 at ({fs[0]:.2f}, {fs[1]:.2f}, {fs[2]:.2f}); the "
                                       "copy starts there and flies to the chosen graph (placement is not editable).")
        else:
            self.level_lbl.config(text=f"NOT LOADED: {self.load_error.detail}\nUse File > Game data folder.")
        self._update_selection()
        stale = self.last_check is None or self.last_check[0] != core.project_bytes(p)
        if stale:
            pre = core.precheck(p, self.model)
            self.status_var.set("Not validated since the last change. " + " ".join(
                f"[{s}] {t}" for s, t in pre))
            self.status_lbl.config(fg="#b9770e" if pre else "#555555")
        gate = core.gate_enabled()
        st = "normal" if self.model else "disabled"
        self.validate_btn.config(state=st)
        self.export_btn.config(state=st)
        prod, why = core.production_status(p)
        self.prod_var.set(("Content: PRODUCTION-SUPPORTED - " if prod else "Content: DEVELOPMENT-ONLY - ") + why)
        self.prod_lbl.config(fg="#1d8a4a" if prod else "#b9770e")
        self.bottom.config(text=(f"{'*' if self.dirty else ''}{name} | terrain edits {len(p['terrain'])}, route edits "
                                 f"{len(p['route'])}, FairyLight {core.GRAPH_NAMES[p['fairylight']['follow_graph_of']]} | "
                                 + ("production-supported" if prod else "development-only")
                                 + (" | development variable set (private development setup)" if gate else "")),
                           foreground="")
        if redraw:
            self.redraw()

    def _update_selection(self):
        for w in (self.terrain_box, self.route_box, self.remix_box, self.revert_btn):
            w.pack_forget()
        s, m, p = self.sel, self.model, self.project
        if not s or not m:
            self.sel_lbl.config(text="Click a vertex or a waypoint in the map. Green circles are editable terrain "
                                     "vertices; magenta circles are graph C waypoints.")
            return
        kind, i = s
        if kind == "vtx":
            reg = m.regions[p["region"]]["vertices"]
            x, y, z = m.verts[i]
            tris = m.vertex_triangles(i)
            if i not in reg:
                self.sel_lbl.config(text=f"Collision vertex {i} at ({x:.3f}, {y:.3f}, {z:.3f})\nNOT EDITABLE: only "
                                         f"vertices {', '.join(map(str, reg))} of region {p['region']} have verified "
                                         "bounds, visual twins and octree checks.")
                return
            lo, hi = self.editable_range(i)
            dz = p["terrain"].get(str(i))
            vs = m.edited_verts({int(v): d for v, d in p["terrain"].items()})
            nz = min(core.triangle_normal_z(*(vs[k] for k in m.tris[t])) for t in tris)
            on_probe = [label for label, tri in m.probe_triangles if i in m.tris[tri]]
            self.sel_lbl.config(text=(
                f"Terrain vertex {i} (editable, {p['region']})\nposition ({x:.3f}, {y:.3f}); original z {z:.4f}\n"
                f"proposed z {vs[i][2]:.4f}" + (f" (lowered {-dz:.2f})" if dz is not None else " (unchanged)") +
                f"\nallowed: lower {-hi:.2f} to {-lo:.2f} (no raising, no horizontal moves)\n"
                f"triangles: {' '.join(f'{a}/{b}' for a, b in tris)}; lowest normal z {nz:.4f} (displayed shape)\n"
                f"standing prediction affected: {', '.join(on_probe) if on_probe else 'none'} (exact values: "
                "Validate)"))
            self._updating = True
            self.dz_scale.config(from_=hi, to=lo)
            self.dz_var.set(dz if dz is not None else hi)
            self._updating = False
            self.dz_lbl.config(text=f"delta z {dz:.2f}" if dz is not None else "not lowered (move the slider)")
            self.terrain_box.pack(fill="x")
            if dz is not None:
                self.revert_btn.pack(anchor="w")
        elif kind == "wp":
            o = m.route[i]
            off = p["route"].get(str(i), [0.0, 0.0, 0.0])
            nw = m.edited_route({int(k): v for k, v in p["route"].items()})[i]
            ln = math.sqrt(sum(v * v for v in off))
            self.sel_lbl.config(text=(
                f"Graph C waypoint {i} (loop of ORIGINAL FairyLight instance 2, not the inserted one)\n"
                f"original ({o[0]:.3f}, {o[1]:.3f}, {o[2]:.3f})\nnew      ({nw[0]:.3f}, {nw[1]:.3f}, {nw[2]:.3f})\n"
                f"move {ln:.3f} of at most {rm.LEVEL_PATCH_ROUTES[core.LEVEL]['max_move']:g} units. Compiler: "
                "offline-verified; the flight through moved waypoints is NOT measured in the game. Route edits are "
                "DEVELOPMENT-ONLY: the production game refuses a mod that contains them."))
            for v, x in zip(self.off_vars, off):
                v.set(f"{x:g}")
            self.route_box.pack(fill="x")
            if str(i) in p["route"]:
                self.revert_btn.pack(anchor="w")
        else:
            self.sel_lbl.config(text=f"{i}\n(read-only reference)")

    def redraw(self):
        if self.mode == "remix":
            return self.redraw_remix(static=True)
        c = self.canvas
        c.delete("all")
        self.picks = []
        W, H = self.canvas_w, self.canvas_h
        if not self.model:
            c.create_text(W / 2, H / 2, fill=COL["probe"], width=W - 80, font=("Segoe UI", 12),
                          text="No map: " + (self.load_error.detail if self.load_error else "not loaded") +
                          "\n\nThe editor only draws geometry decoded from your own intro_20 files. "
                          "Choose File > Game data folder.")
            return
        m, p = self.model, self.project
        self._grid()
        terrain = {int(v): d for v, d in p["terrain"].items()}
        verts = m.edited_verts(terrain)
        reg = set(m.regions[p["region"]]["vertices"])
        _, a, b = VIEWS[self.view]
        zs = [v[2] for v in m.verts]
        near = [v[2] for t, ix in m.tris.items() if reg & set(ix) for v in (m.verts[k] for k in ix)]
        zlo, zhi = (min(near) - 3, max(near) + 3) if near else (min(zs), max(zs))
        for t, ix in m.tris.items():
            pts = [self.proj(verts[k]) for k in ix]
            if max(x for x, _ in pts) < -50 or min(x for x, _ in pts) > W + 50 or \
                    max(y for _, y in pts) < -50 or min(y for _, y in pts) > H + 50:
                continue
            touched = set(ix) & reg
            edited = set(ix) & set(terrain)
            outline = COL["tri_edit"] if edited else COL["tri_region"] if touched else COL["tri"]
            fill = height_colour(sum(verts[k][2] for k in ix) / 3, zlo, zhi) if self.view == "top" else ""
            c.create_polygon(*[q for xy in pts for q in xy], outline=outline, fill=fill,
                             width=2 if edited else 1)
        for k, v in enumerate(verts):
            sx, sy = self.proj(v)
            if not (-10 < sx < W + 10 and -10 < sy < H + 10):
                continue
            if k in reg:
                continue
            c.create_oval(sx - 2, sy - 2, sx + 2, sy + 2, fill=COL["vtx"], outline="")
            self.picks.append((sx, sy, "vtx", k, False))
        for k in sorted(reg):
            sx, sy = self.proj(verts[k])
            if k in terrain and self.view != "top":
                ox_, oy_ = self.proj(m.verts[k])
                c.create_line(ox_, oy_, sx, sy, fill=COL["edited"], dash=(3, 2))
                c.create_oval(ox_ - 5, oy_ - 5, ox_ + 5, oy_ + 5, outline=COL["edited"])
            col = COL["edited"] if k in terrain else COL["editable"]
            r = 7
            c.create_oval(sx - r, sy - r, sx + r, sy + r, fill=col, outline=COL["sel"] if self.sel == ("vtx", k) else "",
                          width=3)
            c.create_text(sx + 11, sy - 10, text=f"v{k}" + (f" {terrain[k]:+.2f}" if k in terrain else ""),
                          fill=COL["text"], anchor="w", font=("Segoe UI", 9, "bold"))
            self.picks.append((sx, sy, "vtx", k, True))
        sel_g = p["fairylight"]["follow_graph_of"]
        for g, pts in m.graphs.items():
            if len(pts) < 2:
                continue
            xy = [q for pt in pts + pts[:1] for q in self.proj(pt)]
            c.create_line(*xy, fill=COL["graph_a" if g == 0 else "graph_b"], dash=() if g == sel_g else (4, 4),
                          width=2 if g == sel_g else 1)
            lx, ly = self.proj(pts[0])
            c.create_text(lx + 6, ly + 10, anchor="w", fill=COL["graph_a" if g == 0 else "graph_b"],
                          text=core.GRAPH_NAMES[g] + (" (inserted FairyLight)" if g == sel_g else ""),
                          font=("Segoe UI", 8))
        route = {int(k): v for k, v in p["route"].items()}
        new = m.edited_route(route)
        if route:
            c.create_line(*[q for pt in m.route + m.route[:1] for q in self.proj(pt)], fill=COL["route_orig"],
                          dash=(4, 3))
        c.create_line(*[q for pt in new + new[:1] for q in self.proj(pt)], fill=COL["route"], width=2,
                      arrow="last", arrowshape=(10, 12, 4))
        for n, pt in enumerate(new):
            sx, sy = self.proj(pt)
            if n in route:
                ox_, oy_ = self.proj(m.route[n])
                c.create_oval(ox_ - 4, oy_ - 4, ox_ + 4, oy_ + 4, outline=COL["route_orig"])
                c.create_line(ox_, oy_, sx, sy, fill=COL["route_orig"], dash=(2, 2))
            r = 7
            c.create_oval(sx - r, sy - r, sx + r, sy + r, fill=COL["route"],
                          outline=COL["sel"] if self.sel == ("wp", n) else "", width=3)
            c.create_text(sx + 10, sy + 10, text=f"C{n}", fill=COL["route"], anchor="w", font=("Segoe UI", 9, "bold"))
            self.picks.append((sx, sy, "wp", n, True))
        fx, fy = self.proj(m.fairy_source)
        c.create_polygon(fx, fy - 8, fx + 8, fy, fx, fy + 8, fx - 8, fy, fill=COL["fairy"], outline="")
        c.create_text(fx + 10, fy, anchor="w", fill=COL["fairy"], text="FairyLight source (instance 2)",
                      font=("Segoe UI", 8))
        self.picks.append((fx, fy, "info", "FairyLight instance 2: the inserted copy is built from it and starts here",
                           False))
        for label, xyz in m.probes:
            sx, sy = self.proj(xyz)
            c.create_line(sx - 6, sy - 6, sx + 6, sy + 6, fill=COL["probe"], width=2)
            c.create_line(sx - 6, sy + 6, sx + 6, sy - 6, fill=COL["probe"], width=2)
            c.create_text(sx + 8, sy - 8, anchor="w", fill=COL["probe"], text=f"Rayman: {label}", font=("Segoe UI", 8))
            self.picks.append((sx, sy, "info", f"Measured standing point '{label}' at ({xyz[0]:.3f}, {xyz[1]:.3f}, "
                                               f"{xyz[2]:.3f})", False))
        self._legend()

    def _grid(self):
        c, W, H = self.canvas, self.canvas_w, self.canvas_h
        steps = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500)
        step = next(s for s in steps if s * self.scale >= 60)
        vstep = next(s for s in steps if s * self.vscale() >= 40)
        u0, v1 = self.unproj(0, 0)
        u1, v0 = self.unproj(W, H)
        _, a, b = VIEWS[self.view]
        names = "XYZ"
        k = math.floor(u0 / step)
        while k * step <= u1:
            sx, _ = self.proj_uv(k * step, 0)
            c.create_line(sx, 0, sx, H, fill=COL["grid"])
            c.create_text(sx + 2, H - 4, anchor="sw", fill=COL["grid_label"], text=f"{k * step:g}", font=("Segoe UI", 7))
            k += 1
        k = math.floor(v0 / vstep)
        while k * vstep <= v1:
            _, sy = self.proj_uv(0, k * vstep)
            c.create_line(0, sy, W, sy, fill=COL["grid"])
            c.create_text(4, sy - 2, anchor="sw", fill=COL["grid_label"], text=f"{round(k * vstep, 4):g}",
                          font=("Segoe UI", 7))
            k += 1
        c.create_text(W - 8, H - 18, anchor="se", fill=COL["grid_label"],
                      text=f"{VIEWS[self.view][0]}: horizontal {names[a]} (grid {step:g}), vertical {names[b]} (grid {vstep:g})"
                           + (f"; heights exaggerated x{self.exag}" if self.view != "top" and self.exag != 1 else ""),
                      font=("Segoe UI", 8))

    def proj_uv(self, u, v):
        return self.ox + u * self.scale, self.oy - v * self.vscale()

    def _legend(self):
        c = self.canvas
        items = [(COL["editable"], "editable terrain vertex"), (COL["edited"], "lowered vertex / edited triangles"),
                 (COL["vtx"], "collision vertex (not editable)"), (COL["route"], "graph C (original FairyLight 2)"),
                 (COL["graph_a"], "graph A"), (COL["graph_b"], "graph B"), (COL["probe"], "measured standing point")]
        c.create_rectangle(8, 8, 250, 14 + 15 * len(items), fill="#1d2128", outline=COL["grid"])
        for i, (col, t) in enumerate(items):
            y = 18 + 15 * i
            c.create_oval(14, y - 4, 22, y + 4, fill=col, outline="")
            c.create_text(28, y, anchor="w", fill=COL["text"], text=t, font=("Segoe UI", 8))
        c.create_text(8, 22 + 15 * len(items), anchor="nw", fill=COL["grid_label"], font=("Segoe UI", 8),
                      text="geometry: static collision decoded from your intro_20.lvl (no textures)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", nargs="?")
    ap.add_argument("--game-dir")
    ap.add_argument("--home", help="installation or portable folder: its data/content and mod folders are used")
    a = ap.parse_args(argv)
    lock = None
    if a.home:
        # the mod manager's own resolution (r3hd_mods.resolve_paths): HOME\data\content, HOME\mods
        os.environ["R3HD_HOME"] = os.path.abspath(a.home)
        lock = hold_home_lock(a.home)
    try:
        root = tk.Tk()
        EditorApp(root, a.game_dir, a.project)
        root.mainloop()
    finally:
        release_home_lock(lock)
    return 0


# G6-P36 (D-292): while the editor runs for an installation it holds an OS lock on HOME\level_editor.lock, so the
# installer engine (r3hd_installer.check_not_running) refuses uninstall / repair / update instead of meeting locked
# files. The lock ends with the process, also after a crash; nothing is ever killed. Windows only (msvcrt).
EDITOR_LOCK_NAME = "level_editor.lock"


def hold_home_lock(home):
    if os.name != "nt":
        return None
    import msvcrt
    try:
        f = open(os.path.join(os.path.abspath(home), EDITOR_LOCK_NAME), "a+b")
    except OSError:
        return None  # a read-only folder: the editor still works; the engine then sees no lock
    try:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()  # another editor of this installation holds it; that one keeps the refusal in place
        return None
    return f


def release_home_lock(f):
    if f is None:
        return
    import msvcrt
    path = f.name
    try:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    f.close()
    try:
        os.remove(path)
    except OSError:
        pass  # another editor of this installation may hold it now


if __name__ == "__main__":
    sys.exit(main())
