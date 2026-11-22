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

G6-P69 (D-318): a VIEW ONLY level is read on one background thread (`LevelLoader`): the never-editable model, the
scene, its vertex batches and its decoded textures - CPU work on the person's files only. That thread never calls Tk
or OpenGL. This window's thread polls for the result, uploads it to its own GL context and updates the widgets. The
latest selection wins: older requests are cancelled cooperatively and their results are dropped twice (by the loader
and again before the commit). The level shown stays shown, and navigable, until the new one is ready; a level that
cannot be read leaves it in place with an error. Editor levels still load on this thread (the editor owns their model).
"""
import argparse
import math
import os
import sys
import threading
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
# G6-P68 (D-317): view-only levels from the read-only catalog. Nothing of such a level can be selected for editing,
# saved, validated, exported or installed; the editor's own project (if any) is kept untouched in the background.
PLAIN_STATUS["view"] = "View only: this level is shown, never edited"
STATUS_FG["view"] = "#2e6db4"
VIEW_RGB = (0.55, 0.72, 0.95)
VIEW_SUFFIX = " - VIEW ONLY"
WHY_DISABLED["view"] = ("This level is VIEW ONLY: it cannot be edited, saved, validated, exported or installed as a "
                        "mod. Choose an editable level under Level to edit; your project there is kept.")
VIEW_LIMITS = ("Approximate picture: draw modes were traced only on intro_15; sky, water, animation, lighting and "
               "shaders are not reproduced; objects the game places at run time are hidden or shown where the file "
               "puts them.")
EDIT_COMMANDS = ("open", "save", "validate", "export", "import", "classic")


def view_label(level):
    return f"{level}{VIEW_SUFFIX}"


HINT = ("Left-drag: orbit   Right-drag: look   Middle-drag: pan   Wheel: zoom   W A S D Q E: fly (Shift: faster)   "
        "F: focus   Home: whole level   Enter: apply   Esc: cancel   Ctrl+Z: undo")
FLY_KEYS = {"w": (1, 0, 0), "s": (-1, 0, 0), "a": (0, -1, 0), "d": (0, 1, 0), "q": (0, 0, -1), "e": (0, 0, 1)}


def friendly(name):
    """'NIK_mChameleon' -> 'Chameleon'; the technical key stays under Advanced details."""
    base = name.split("_m", 1)[1] if "_m" in name[:6] else name.split("_", 1)[-1]
    return base.replace("_", " ").strip() or name


def dim(rgb, k=0.55):
    return tuple(c * k for c in rgb)


# -------------------------------------------------------------------------------------------------- G6-P69 loading
POLL_MS = 15                 # how often this window looks for a finished background load (only while one is pending)
JOIN_SECONDS = 10.0          # closing waits this long for the loader thread (it stops at its next checkpoint)
# While a background load runs, both threads want the interpreter lock: every Tk call releases it, and getting it back
# from the busy loader thread takes up to the switch interval (5 ms by default) - so a handler making 50 Tk calls
# would wait about 250 ms. Only while a load is pending, the interval is 0.5 ms (restored afterwards; it costs the
# loader nothing while this thread is idle in the event loop). Measured in G6-P69 (E-555).
SWITCH_SECONDS = 0.0005
LOAD_ERRORS = (ls.SceneError, core.EditorError, OSError, MemoryError)


def load_view_level(game_dir, level, cancelled):
    """The CPU part of showing a VIEW ONLY level (G6-P69): the never-editable model, the scene with its roles, the
    vertex batches and the decoded textures. Runs on the loader's thread: no Tk, no OpenGL, no shared editor state;
    it only reads the person's files. Raises sg.Cancelled when `cancelled()` turns true at a checkpoint."""
    t0 = time.perf_counter()
    try:
        model, err = core.ViewModel(game_dir, level), None
    except core.EditorError as x:                     # actors unreadable: the picture alone, unclassified
        model, err = None, x.detail
    t1 = time.perf_counter()
    if cancelled():
        raise sg.Cancelled()
    scene = ls.Scene(game_dir, level) if model is None else sg.classified_scene(game_dir, level, model)[0]
    if not scene.objects:                             # G6-P68: e.g. a truncated file that parses to nothing
        raise ls.SceneError("EMPTY", f"{level} has no drawable geometry (the files may be damaged)")
    t2 = time.perf_counter()
    if cancelled():
        raise sg.Cancelled()
    prepared = sg.Prepared(scene, cancelled=cancelled)
    return {"level": level, "model": model, "error": err, "scene": scene, "prepared": prepared,
            "seconds": {"model": round(t1 - t0, 4), "scene": round(t2 - t1, 4), **prepared.seconds,
                        "cpu_total": round(time.perf_counter() - t0, 4)}}


class LevelLoader:
    """G6-P69: one background thread, at most one waiting request and at most one finished result.

    submit() replaces any waiting request and supersedes the running one (its `cancelled()` turns true; it stops at
    its next checkpoint, never by force). A result is kept only if its request is still the latest when it finishes;
    take() hands it to the owner's thread. shutdown() cancels everything, stops the thread and waits for it. The work
    function runs on the thread and must not touch Tk or OpenGL; any exception it raises becomes a failed result."""

    def __init__(self, work):
        self._work = work
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._gen = 0
        self._request = None            # (gen, args) not yet started
        self._result = None             # (gen, result) of the latest request
        self._thread = None
        self._stopped = False
        self.busy = False               # a request is running on the thread (diagnostics / tests)

    def submit(self, *args):
        with self._lock:
            if self._stopped:
                raise RuntimeError("the level loader has been shut down")
            self._gen += 1
            self._request, self._result = (self._gen, args), None
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="r3hd-level-loader", daemon=True)
                self._thread.start()
            self._wake.notify()
            return self._gen

    def cancel(self):
        """Supersede the waiting and the running request; nothing of them will be delivered."""
        with self._lock:
            self._gen += 1
            self._request, self._result = None, None

    def is_current(self, gen):
        with self._lock:
            return gen == self._gen and not self._stopped

    def take(self):
        """(gen, result) of a finished request, or None. The caller still checks gen against what it is waiting for."""
        with self._lock:
            out, self._result = self._result, None
            return out

    def shutdown(self, timeout=JOIN_SECONDS):
        """Cancel, stop and join the thread. True when no loader thread is left running."""
        with self._lock:
            self._stopped = True
            self._gen += 1
            self._request, self._result = None, None
            self._wake.notify_all()
            t = self._thread
        if t is not None:
            t.join(timeout)
            return not t.is_alive()
        return True

    def alive(self):
        return self._thread is not None and self._thread.is_alive()

    def _run(self):
        while True:
            with self._lock:
                while self._request is None and not self._stopped:
                    self._wake.wait()
                if self._stopped:
                    return
                (gen, args), self._request = self._request, None
                self.busy = True

            def cancelled(gen=gen):
                return self._gen != gen or self._stopped   # a plain read: an int / bool, set under the lock
            try:
                res = self._work(*args, cancelled)
            except sg.Cancelled:
                res = None
            except LOAD_ERRORS as x:
                res = {"failed": getattr(x, "detail", None) or str(x) or type(x).__name__}
            except Exception as x:      # noqa: BLE001 - the thread must outlive any defect of one level
                res = {"failed": f"unexpected {type(x).__name__}: {x}"}
            with self._lock:
                self.busy = False
                if res is not None and gen == self._gen and not self._stopped:
                    self._result = (gen, res)
                # else: superseded while running - dropped here, before the owner can ever see it
            res = args = None   # this thread keeps no level alive while it waits (found in G6-P69 measurement)


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
        self.view = None                     # G6-P68: {"level", "model", "error", "entry"} while a view-only level shows
        self.vsel = None                     # the viewer's own selection on a view-only level (never the editor's)
        self.view_levels = core.view_level_names()
        self.pending = None                  # G6-P69: {"level", "gen", "t0"} while a view-only level loads
        self.loader = LevelLoader(load_view_level)
        self.loader_stopped = None           # G6-P69: True once closing has joined the loader thread
        self._poll_job, self._busy_prev, self._switch_prev = None, None, None
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
                                     values=[c[2] for c in ed.CHOICES] + [view_label(lv) for lv in self.view_levels])
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
        self.cmd_btns = {}
        for key, label, fn in (("open", "Open...", self.open), ("save", "Save", self.save),
                               ("validate", "Validate", self.validate), ("export", "Export mod...", self.export),
                               ("import", "Import + enable...", self.import_mod)):
            self.cmd_btns[key] = ttk.Button(bar, text=label, command=fn)
            self.cmd_btns[key].pack(side="left", padx=1)
        self.adv = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Advanced details", variable=self.adv, command=self.refresh_panel).pack(side="right")
        self.cmd_btns["classic"] = ttk.Button(bar, text="Classic 2D editor", command=self.show_2d)
        self.cmd_btns["classic"].pack(side="right", padx=6)

        body = ttk.Frame(t)
        body.pack(side="top", fill="both", expand=True)
        side = ttk.Frame(body, padding=8, width=330)
        side.pack(side="right", fill="y")
        side.pack_propagate(False)
        # background "" : Tk never paints this frame; OpenGL owns its pixels
        self.vp = tk.Frame(body, background="", takefocus=1, cursor="crosshair")
        self.vp.pack(side="left", fill="both", expand=True)

        self.cap_lbl = tk.Label(side, text="", anchor="w", justify="left", wraplength=310,
                                font=("Segoe UI", 9, "bold"))
        self.cap_lbl.pack(fill="x", pady=(0, 6))
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
        if self.view:
            return ("view", self.view["level"])
        a = self.app
        return ("remix", a.remix["level"]) if a.mode == "remix" else ("patch", core.LEVEL)

    def cur_sel(self):
        """The selection this window shows: its own on a view-only level, else the editor's."""
        return self.vsel if self.view else self.app.sel

    def cur_model(self):
        """The level model whose actors and routes are shown: the ViewModel of a view-only level, the editor's remix
        model, or None (the intro_20 level patch)."""
        if self.view:
            return self.view["model"]
        return self.app.rmodel if self.app.mode == "remix" else None

    def ensure_scene(self):
        key = self.level_key()
        if self.r is not None and self.scene_key == key:
            return
        if key[0] == "view":                           # G6-P69: never read here; installed from a finished load
            self._install_view()
            return
        if self.r is not None and self.scene_key and self.scene_key[1] == key[1]:
            self.scene_key = key                       # same level, other project kind: keep the scene
            self.r.set_collision(self.collision_tris(key))
            self.fit_content()
            return
        self.status(f"Loading {key[1]} from your game files...")
        t0 = time.perf_counter()
        old, self.r = self.r, None
        self.scene = None
        if old is not None:
            self.ctx.current()
            old.close()                                # free the previous level's textures before loading
        model = self.cur_model() if key[0] == "remix" else None
        busy = self._busy(True)
        try:
            self.scene, _ = sg.classified_scene(self.app.game_dir, key[1], model)
            if not self.scene.objects:                 # G6-P68: e.g. a truncated file that parses to nothing
                raise ls.SceneError("EMPTY", f"{key[1]} has no drawable geometry (the files may be damaged)")
            self.ctx.current()
            self.r = sg.Renderer(self.ctx, self.scene)
        except (ls.SceneError, core.EditorError, OSError, MemoryError) as x:
            self.scene = None
            self.status(f"The level's scene could not be read: {getattr(x, 'detail', x)}", True)
            return
        finally:
            self._busy(False, busy)
        self.r.set_collision(self.collision_tris(key))
        self.scene_key = key
        self.timing["load_seconds"] = round(time.perf_counter() - t0, 3)
        self.fit_content()
        self.status(f"{key[1]} loaded from your game files.")

    def _install_view(self):
        """G6-P69: put a committed view-only level on screen: the renderer built at commit time, or - when the GL
        context started only afterwards - an upload of its prepared data now. Old level freed after the new one is
        in place. Never reads a file."""
        v = self.view
        r = v.pop("ready", None)
        if r is None:
            if self.ctx is None or v.get("prepared") is None:
                return
            try:
                self.ctx.current()
                r = sg.Renderer(self.ctx, v["scene"], prepared=v["prepared"])
            except (ls.SceneError, OSError, MemoryError) as x:
                v["prepared"] = None
                self.status(f"The level's scene could not be shown: {getattr(x, 'detail', x)}", True)
                return
        v["prepared"] = None                           # decoded pixels now live in the bridge only
        old, self.r = self.r, r
        if old is not None:
            self.ctx.current()
            old.close()
        self.scene, self.scene_key = v["scene"], ("view", v["level"])
        self.r.set_collision(self.collision_tris(self.scene_key))
        self.timing["load_seconds"] = v.get("seconds", {}).get("shown")
        self.fit_content()
        errs = len(self.r.stats["texture_errors"])
        self.status(f"{v['level']} loaded from your game files - VIEW ONLY"
                    + (f"; {errs} texture(s) could not be shown (drawn untextured)" if errs else "") + ".")

    def _busy(self, on, prev=None, cursor="watch"):
        """A wait cursor on this window while a level loads (no grab, no global cursor change). G6-P69: "starting"
        (arrow and hourglass) while a view-only level loads in the background and the window still responds."""
        try:
            if on:
                prev = self.top.cget("cursor")
                self.top.config(cursor=cursor)
                if cursor == "watch":
                    self.top.update_idletasks()
                return prev
            self.top.config(cursor=prev or "")
        except tk.TclError:
            pass
        return None

    # ---------------------------------------------------------------------------------------------- G6-P69 loading
    def _start_pending(self, level):
        """Mark the level as loading (the caller updates the widgets), then _submit_pending hands it to the loader."""
        self.cancel_pending(quiet=True)
        self.pending = {"level": level, "gen": None, "t0": time.perf_counter()}
        self._busy_prev = self._busy(True, cursor="starting")

    def _submit_pending(self):
        """After the widgets show the pending state: start the CPU work and poll for it. While it runs, this thread
        gets the interpreter lock back quickly after each Tk call (see SWITCH_SECONDS)."""
        self._fast_switch(True)
        self.pending["gen"] = self.loader.submit(self.app.game_dir, self.pending["level"])
        self._poll_job = self.top.after(POLL_MS, self._poll)

    def _fast_switch(self, on):
        if on and self._switch_prev is None:
            self._switch_prev = sys.getswitchinterval()
            sys.setswitchinterval(min(self._switch_prev, SWITCH_SECONDS))
        elif not on and self._switch_prev is not None:
            sys.setswitchinterval(self._switch_prev)
            self._switch_prev = None

    def cancel_pending(self, quiet=False):
        """Forget the level being loaded (a newer choice, an editor level, or closing). The loader drops its result."""
        if not self.pending:
            return False
        level = self.pending["level"]
        self.loader.cancel()
        self._fast_switch(False)
        self.pending = None
        if self._poll_job is not None:
            try:
                self.top.after_cancel(self._poll_job)
            except tk.TclError:
                pass
            self._poll_job = None
        self._busy(False, self._busy_prev)
        self._busy_prev = None
        if not quiet and not self._closing:
            self.status(f"Loading {level} was cancelled.")
        return True

    def _poll(self):
        """This window's thread: look for the finished load; commit it only if it is the latest request."""
        self._poll_job = None
        if self._closing or not self.pending:
            return
        got = self.loader.take()
        if got is not None and got[0] == self.pending["gen"] and self.loader.is_current(got[0]):
            self._commit(got[1])
            return
        self._poll_job = self.top.after(POLL_MS, self._poll)   # nothing yet, or an obsolete result (dropped)

    def _commit(self, res):
        p = self.pending
        self.pending = None
        self._fast_switch(False)
        self._busy(False, self._busy_prev)
        self._busy_prev = None
        shown = self.view["level"] + VIEW_SUFFIX if self.view else self.level_key()[1]
        if "failed" in res:                            # the level shown stays as it is
            self.status(f"{p['level']} could not be shown: {res['failed']}. Still showing {shown}.", True)
            self.sync()
            return
        r = None
        if self.ctx is not None:                       # upload first: if it fails, nothing of the shown level changed
            try:
                self.ctx.current()
                r = sg.Renderer(self.ctx, res["scene"], prepared=res["prepared"])
            except (ls.SceneError, OSError, MemoryError) as x:
                self.status(f"{p['level']} could not be shown: {getattr(x, 'detail', x)}. Still showing {shown}.",
                            True)
                self.sync()
                return
        self.preview, self.vsel, self.drag = None, None, None
        self.stop_fly()
        secs = dict(res.get("seconds", {}), shown=round(time.perf_counter() - p["t0"], 3))
        self.view = {"level": p["level"], "model": res["model"], "error": res["error"],
                     "entry": core.view_catalog().get(p["level"]), "scene": res["scene"],
                     "prepared": res["prepared"], "seconds": secs}
        if r is not None:
            self.view["ready"] = r
        self.sync()
        if self.ctx is None:
            err = res["error"]
            self.status(f"{p['level']} is VIEW ONLY." + (f" Objects could not be read: {err}" if err else ""),
                        bool(err))

    def finish_pending(self, timeout=120.0):
        """Tests and tools only: run this window's timer and idle events (the poll, queued redraws) until no view-only
        load is pending, then the idle events once more. No window events, so a withdrawn test window keeps its size
        (as G6-P68's update_idletasks did)."""
        import _tkinter
        end = time.monotonic() + timeout
        flags = _tkinter.TIMER_EVENTS | _tkinter.IDLE_EVENTS | _tkinter.DONT_WAIT
        while self.pending and time.monotonic() < end and not self._closing:
            while self.top.tk.dooneevent(flags):
                pass
            time.sleep(0.002)
        if not self._closing:
            self.top.update_idletasks()
        return not self.pending

    def collision_tris(self, key):
        if key[0] == "view":
            return self.view["model"].tris if self.view and self.view["model"] else []
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
        self.cancel_pending(quiet=True)                # G6-P69: no load is committed after this point
        self.loader_stopped = self.loader.shutdown()   # cooperative: the thread stops at its next checkpoint
        if self.view:
            self.view["prepared"] = None
            ready = self.view.pop("ready", None)       # (normally installed by sync at once; never left in the bridge)
            if ready is not None and self.ctx:
                self.ctx.current()
                ready.close()
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
        if self._closing:
            return
        if self.ctx is None:                           # G6-P68: no 3D view, but the capability state still applies
            self.sync_controls()
            return
        app = self.app
        self.ensure_scene()
        self.sync_controls()
        kind = self.level_key()[0]
        sel = self.cur_sel()
        if sel and TOOL_FOR_KIND.get(sel[0]) and TOOL_FOR_KIND[sel[0]] != self.tool.get():
            self.tool.set(TOOL_FOR_KIND[sel[0]])
        if str(self.tool_btns[self.tool.get()].cget("state")) == "disabled":
            self.tool.set("terrain" if kind == "patch" else "objects")
        self.undo_btn.config(state="normal" if kind == "remix" and app.undo and not self.pending else "disabled")
        if self.preview and (self.view or self.preview["sel"] != app.sel):
            self.preview = None
        self.build_overlays()
        self.refresh_panel()
        self.request()

    def sync_controls(self):
        """Title, level selector, capability line, tool and command states from what is shown (G6-P68). A view-only
        level disables every command that edits, saves, validates, exports or installs."""
        self._sync_controls_shown()
        if self.pending:                               # G6-P69: the shown level stays; editing pauses until it is replaced
            lv = self.pending["level"]
            self.level_var.set(view_label(lv))
            for key in self.cmd_btns:
                self.cmd_btns[key].config(state="disabled")
            self.undo_btn.config(state="disabled")
            self.top.title(f"Experimental 3D Level Viewer - loading {lv} (VIEW ONLY)")
            self.cap_lbl.config(text=f"LOADING {lv} (VIEW ONLY) - the level shown stays until it is ready; editing "
                                     "commands are paused.", fg=STATUS_FG["view"])

    def _sync_controls_shown(self):
        app = self.app
        kind, level = self.level_key()
        if kind == "view":
            self.top.title(f"Experimental 3D Level Viewer - {level} - VIEW ONLY")
            self.level_var.set(view_label(level))
            m = self.view["model"]
            for key, b in self.tool_btns.items():
                b.config(state="normal" if key != "terrain" and m is not None else "disabled")
            for b in self.cmd_btns.values():
                b.config(state="disabled")
            ident = {"measured": "", "differs": " Your files differ from the measured copy: the picture is untested.",
                     "uncatalogued": " This level was not measured."}.get(getattr(m, "identity", ""), "")
            self.cap_lbl.config(text=f"VIEW ONLY - nothing on this level can be changed, exported or installed."
                                     f"{ident}", fg=STATUS_FG["view"])
            return
        name = app.path.name if app.path else "unsaved project"
        self.top.title(f"Experimental 3D Level Viewer - {level} - {name}{' *' if app.dirty else ''}")
        self.level_var.set(app.current_choice()[2])
        for key, b in self.tool_btns.items():
            ok = (key != "terrain") if kind == "remix" else (key == "terrain")
            b.config(state="normal" if ok else "disabled")
        for b in self.cmd_btns.values():
            b.config(state="normal")
        dev = kind == "remix" and core.is_dev_level(level)
        self.cap_lbl.config(text="EDITABLE - DEVELOPMENT ONLY level (not verified in game)" if dev else "EDITABLE",
                            fg=STATUS_FG["experimental"] if dev else STATUS_FG["verified"])

    def selected_pos(self, sel):
        """Current (edited) position of a selection, from the editor; the file's position on a view-only level."""
        app = self.app
        if self.view:
            return self.original_pos(sel)
        if sel[0] in ("actor", "rwp"):
            p = app.remix_position(sel)
            return tuple(p) if p else None
        if sel[0] == "vtx" and app.model:
            return tuple(app.model.edited_verts({int(k): v for k, v in app.project["terrain"].items()})[sel[1]])
        return None

    def original_pos(self, sel):
        if self.view:
            m = self.view["model"]
            if m is None:
                return None
            if sel[0] == "actor" and sel[1] in m.actors:
                return tuple(m.actors[sel[1]]["position"])
            if sel[0] == "rwp" and sel[1][:3] in m.graphs:
                nodes = m.graphs[sel[1][:3]]["nodes"]
                nd = nodes[sel[1][3]] if sel[1][3] < len(nodes) else None
                return tuple(nd["position"]) if nd else None
            return None
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
        m = self.cur_model() if self.level_key()[0] in ("remix", "view") else None
        view = bool(self.view)
        where = (lambda s: self.original_pos(s)) if view else (lambda s: tuple(app.remix_position(s)))  # noqa: E731
        cur = self.cur_sel()
        if tool == "objects" and m:
            for ident, a in m.actors.items():
                sel = ("actor", ident)
                p = where(sel)
                pts.append((p, VIEW_RGB if view else sg.STATUS_RGB.get(a["status"], (1, 1, 1)), sel))
                picks.append((p, sel))
                if math.dist(p, a["position"]) > 1e-6:          # where an edited object came from
                    lines.append((a["position"], p, (0.8, 0.8, 0.8), 1.0, True, False))
        elif tool == "paths" and m:
            cur_g = cur[1][:3] if cur and cur[0] == "rwp" else None
            for gid, g in m.graphs.items():
                rgb = VIEW_RGB if view else sg.STATUS_RGB.get(g["status"], (1, 1, 1))
                strong = gid == cur_g
                pos = {}
                for nd in g["nodes"]:
                    if not nd:
                        continue
                    sel = ("rwp", gid + (nd["node"],))
                    p = where(sel)
                    pos[nd["node"]] = p
                    editable = g["status"] not in ed.REFUSED and not nd["why"]
                    shown = (rgb if strong else dim(rgb, 0.8)) if editable or view else sg.STATUS_RGB["locked"]
                    pts.append((p, shown, sel))
                    picks.append((p, sel))
                    if math.dist(p, nd["position"]) > 1e-6:      # original place of an edited waypoint
                        lines.append((nd["position"], p, (0.8, 0.8, 0.8), 1.0, True, False))
                for i, j in g["edges"]:
                    if i in pos and j in pos:
                        lines.append((pos[i], pos[j], rgb if strong else dim(rgb), 3.0 if strong else 1.5,
                                      False, True))
            owner = (cur_g[0], cur_g[1]) if cur_g else None
            if owner in m.actors:                              # the selected route's storage owner (not pickable)
                pts.append((where(("actor", owner)), (1.0, 1.0, 1.0), None))
        elif tool == "terrain" and app.model and not view:
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
        sel = cur if cur and TOOL_FOR_KIND.get(cur[0]) == tool else None
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
        if self.view:                                         # G6-P68: never editable
            m = self.view["model"]
            if m and sel[0] == "actor" and sel[1] in m.actors:
                a = m.actors[sel[1]]
                return (f"{friendly(a['name'])} #{a['instance']}", "view",
                        [f"Model {a['name']}", "Shown where the level file places it; the game may move it."],
                        False, "")
            if m and sel[0] == "rwp" and sel[1][:3] in m.graphs:
                g = m.graphs[sel[1][:3]]
                return (f"Route point {sel[1][3]}", "view",
                        [f"Route of {friendly(g['name'])} #{sel[1][1]} ({len(g['nodes'])} points)"], False, "")
            return ("", None, [], False, "")
        if sel[0] == "actor":
            a = app.rmodel.actors[sel[1]]
            return (f"{friendly(a['name'])} #{a['instance']}", a["status"], [], a["status"] not in ed.REFUSED,
                    f"may move up to {getattr(app.rmodel, 'max_actor_move', core.MAX_ACTOR_MOVE):g} units"
                    + (" (development-only level)" if getattr(app.rmodel, "dev", False)
                       else " (the largest move tested in game)"))
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
        cur = self.cur_sel()
        sel = cur if cur and TOOL_FOR_KIND.get(cur[0]) == tool else None
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
            if self.view:
                hint = {"objects": "Click a marker to inspect an object. Markers are viewer symbols, not the "
                                   "objects' 3D models.",
                        "paths": "Click a route point to inspect it. Routes are shown as the level file stores them.",
                        "terrain": ""}[tool]
            self.status_lbl.config(text=hint, fg="#555555")
            why = WHY_DISABLED[self.level_key()[0]]
            if self.view:
                why += "\n\n" + VIEW_LIMITS + (f"\n\nObjects and routes could not be read: {self.view['error']}"
                                                if self.view["error"] else "")
            self.detail_lbl.config(text=why)
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
            if self.r.stats["texture_errors"]:
                lines.append(f"textures not shown: {len(self.r.stats['texture_errors'])}")
        if self.ctx:
            lines.append(f"GL {self.ctx.info['renderer']}")
        lines.append(f"load {self.timing['load_seconds']} s; frame {self.timing['last_ms']} ms "
                     f"(max {round(self.timing['max_ms'], 2)}) over {self.timing['frames']} frames")
        if sel and sel[0] == "actor":
            a = self.cur_model().actors[sel[1]]
            lines += [f"key {a['key']}", f"instance {a['instance']} status {a['status']}",
                      f"matrix {str(a.get('matrix_sha256'))[:16]}..", f"why: {a['why']}"]
            if "compiler_status" in a:
                lines.append(f"compiler (not offered here): {a['compiler_status']}")
        elif sel and sel[0] == "rwp":
            g = self.cur_model().graphs[sel[1][:3]]
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
        if self.pending and not self.view:                    # G6-P69: no move starts while a level loads
            return
        if self.view:                                         # G6-P68: select to inspect, never move
            if hit is not None and hit == self.vsel:
                self.msg.config(text="View only: nothing on this level can be moved.", fg="#2e6db4")
            return
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
        if d["kind"] != "move" or not d["moved"] or not self.mats or self.view or self.pending:
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
        mx = getattr(self.app.rmodel, "max_actor_move", core.MAX_ACTOR_MOVE) if sel[0] == "actor" \
            else core.MAX_WAYPOINT_MOVE
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
        if self.view:                                         # the viewer's own selection; the editor is untouched
            self.vsel = sel
            self.sync()
            return
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
        m = self.cur_model()
        if self.level_key()[0] in ("remix", "view") and m and m.actors:
            cols = [sorted(a["position"][k] for a in m.actors.values()) for k in range(3)]
            q = lambda v, f: v[min(len(v) - 1, int(f * len(v)))]   # noqa: E731
            lo, hi = [q(c, 0.1) for c in cols], [q(c, 0.9) for c in cols]
        elif app.model and not self.view:
            vs = [app.model.verts[v] for v in app.model.regions[app.project["region"]]["vertices"]]
            lo = [min(p[k] for p in vs) - 6 for k in range(3)]
            hi = [max(p[k] for p in vs) + 6 for k in range(3)]
        else:
            return self.fit_level()
        self.cam.fit(lo, hi)
        self.cam.pitch, self.cam.yaw = 35.0, -60.0
        self.request()

    def focus_selection(self):
        sel = self.cur_sel()
        p = (self.preview_pos() or self.selected_pos(sel)) if sel else None
        if p:
            self.cam.target, self.cam.dist = list(p), 12.0
            self.request()

    # ---------------------------------------------------------------------------------------------- commands
    def tool_changed(self):
        app = self.app
        self.preview = None
        if self.view:
            if self.vsel and TOOL_FOR_KIND.get(self.vsel[0]) != self.tool.get():
                self.vsel = None
            self.sync()
        elif app.sel and TOOL_FOR_KIND.get(app.sel[0]) != self.tool.get():
            app.select(None)
        else:
            self.sync()

    def refuse_view(self, what):
        """G6-P68: every edit, save, validation, export and import is refused on a view-only level. G6-P69: and while a
        view-only level loads (whatever is shown), so no command overlaps the switch."""
        if self.pending:
            self.preview = None
            self.status(f"{what} is not available while {self.pending['level']} (VIEW ONLY) loads. Choose an "
                        "editable level under Level to cancel the load.", True)
            return True
        if not self.view:
            return False
        self.preview = None
        self.status(f"{what} is not available: {self.view['level']} is VIEW ONLY. Choose an editable level under "
                    "Level.", True)
        return True

    def apply(self):
        if self.refuse_view("Applying a change"):
            return
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
        if self.refuse_view("Reverting"):
            return
        if self.app.sel:
            self.preview = None
            self.app.revert_selected()
            self.sync()

    def undo(self):
        if self.refuse_view("Undo"):
            return
        if self.app.mode == "remix":
            self.preview = None
            self.app.cmd_undo()

    def choose_level(self, label):
        view = next((lv for lv in self.view_levels if view_label(lv) == label), None)
        if view is not None:
            self.enter_view(view)
            return
        c = next(c for c in ed.CHOICES if c[2] == label)
        cancelled = self.cancel_pending()              # G6-P69: an editor level supersedes a pending view-only load
        if c[:2] == self.app.current_choice()[:2]:
            if self.view:                              # back to the kept project, unchanged
                self.leave_view()
            elif cancelled:
                self.sync()
            return
        if self.asks() and self.app.dirty and not messagebox.askyesno(
                "Unsaved changes", "Discard the unsaved changes?",
                                                      parent=self.top):
            self.level_var.set(view_label(self.view["level"]) if self.view else self.app.current_choice()[2])
            return
        self.preview = None
        self.view = self.vsel = None
        self.app.set_mode(c[0], c[1])

    def enter_view(self, level):
        """G6-P68: show a catalogued level VIEW ONLY. The editor's project (and its unsaved changes) stays as it is; no
        project, model or file of the viewed level is given to the editor."""
        if level not in self.view_levels:
            self.status(f"{level} is not offered by the viewer.", True)
            return False
        if self._closing:
            return False
        if self.pending and self.pending["level"] == level:
            return True                                # already loading
        if self.view and self.view["level"] == level:
            if self.cancel_pending():                  # back to the level still shown: the newer load is dropped
                self.sync()
            return True
        # G6-P69: the CPU work runs on the loader thread; the level shown stays (and can be navigated) meanwhile.
        self.preview, self.drag = None, None
        self.stop_fly()
        self._start_pending(level)
        self.status(f"Loading {level} (view only) from your game files... The level shown stays until it is ready.")
        self.sync_controls()
        if not self.view:                              # an editor level is shown: drop its preview overlay at once
            self.build_overlays()
            self.refresh_panel()
            self.request()
        self._submit_pending()                         # widgets first: they are updated before the CPU work starts
        return True

    def leave_view(self):
        self.preview, self.vsel, self.view = None, None, None
        self.sync()

    def open(self):
        """G6-P63: a project file or an exported editor mod (reopened as a new unsaved project)."""
        if self.refuse_view("Opening a project"):
            return
        if self.asks() and self.app.dirty and not messagebox.askyesno(
                "Unsaved changes", "Discard the unsaved changes?", parent=self.top):
            return
        f = filedialog.askopenfilename(parent=self.top, filetypes=ed.OPEN_TYPES)
        if f:
            self.preview = None
            self.app.open_project(f)   # its messages reach this window through the flash wrapper (D-294)

    def save(self):
        if self.refuse_view("Saving"):
            return
        app = self.app
        path = app.path or filedialog.asksaveasfilename(parent=self.top, defaultextension=".r3hdmap.json",
                                                        filetypes=ed.PROJECT_TYPES)
        if path:
            app.save_project(path)
            self.status(f"Saved {Path(path).name}.")

    def validate(self):
        if self.refuse_view("Validation"):
            return
        self.app.validate_now()
        self.status(self.app.status_var.get(), "REFUSED" in self.app.status_var.get())

    def export(self):
        if self.refuse_view("Exporting a mod"):
            return
        d = filedialog.askdirectory(parent=self.top, title="New or empty folder for the mod (mod.json)")
        if d:
            self.app.export_mod(d)
            self.status(self.app.status_var.get(), "REFUSED" in self.app.status_var.get())

    def import_mod(self):
        if self.refuse_view("Importing a mod"):
            return
        d = filedialog.askdirectory(parent=self.top, title="Exported mod folder (contains mod.json)")
        if d:
            self.app.import_mod_asking(d, self.top)   # G6-P63: replacing an installed mod needs a person's yes
            self.status(self.app.status_var.get(), "NOT IMPORTED" in self.app.status_var.get())

    def show_2d(self):
        if self.refuse_view("The classic 2D editor"):
            return
        self.app.root.deiconify()
        self.app.root.lift()


def open_editor(root, game_dir=None, project=None, level=None, show=True):
    """The editor with its 2D window hidden and this 3D window on top. show=False keeps the 3D window withdrawn
    (tests: nothing is mapped, handlers are called directly)."""
    app = ed.EditorApp(root, game_dir, project)
    root.withdraw()
    view_only = level is not None and level not in core.remix_level_names()   # G6-P68: a view-only start
    if project is None:
        app.set_mode("remix", "intro_20" if view_only or not level else level)
    top = tk.Toplevel(root)
    if not show:
        top.withdraw()
    view = Editor3D(app, top)
    root.protocol("WM_DELETE_WINDOW", view.close)
    if view_only:
        view.enter_view(level)
    return app, view


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("level", nargs="?", choices=sorted(core.remix_level_names()) + core.view_level_names(),
                    help="an editable level, or a catalogued level shown VIEW ONLY (G6-P68)")
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
    ok = level in core.remix_level_names() or level in core.view_level_names()
    return main(["--game-dir", str(game)] + ([level] if ok else []))


if __name__ == "__main__":
    sys.exit(main())
