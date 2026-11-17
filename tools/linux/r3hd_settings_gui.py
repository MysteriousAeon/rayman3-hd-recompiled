#!/usr/bin/env python3
"""Linux Settings window and first-start setup (E-379, E-380): the counterpart of app/r3hd_launcher.exe on Windows.

It holds no setting of its own, exactly like the Windows launcher (M30, D-067): it shows the engine's launcher-model
(tools/r3hd_installer.py: presets, the registry's shown settings with their labels, help, values, requirements and
sliders, the current choice and the settings revision) and saves through the engine's set-preset with
--expect-revision (D-139), so the resolver validates every choice and the in-game F4 panel (set-preferences, same
revision check) and this window never overwrite each other: a stale save is refused and the window reloads.

Model (no GUI, tested on any platform): a port of the Windows launcher's ChooseProfile / Save. Preferences (display,
rendering, mouse, subtitles, DualSense, language, diagnostics) belong to no preset and are kept under every preset.
Preset corrections follow the chosen preset; Custom starts from what the previous preset showed (its base). One
deliberate convenience over the Windows window: changing a correction while Vanilla or HD+ is shown switches to
Custom based on that preset, so one correction can differ without re-entering the others.

View: tkinter (Python's standard GUI; on some distributions a separate package, e.g. `tk` on Arch). Without it, or
without a display, Settings.sh keeps the console configuration (r3hd_installer.py configure).

  python3 app/tools/linux/r3hd_settings_gui.py --home HOME [--setup]
"""
import argparse
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_installer as engine  # noqa: E402

PRESETS = ("vanilla", "hdplus", "custom")
# Button prompts use the registry's controller group. Legacy DualSense preferences
# remain under advanced in the registry; this window also presents them on Controller.
TABS = (("display", "Display"), ("corrections", "Corrections"), ("controller", "Controller"), ("mouse", "Mouse"),
        ("advanced", "Troubleshooting"))
LINUX_NOTES = {"discord_presence": "Windows only: no effect on Linux yet."}


def gui_available():
    """tkinter importable and an X11 display (Wayland desktops provide XWayland's DISPLAY)."""
    if not os.environ.get("DISPLAY"):
        return False
    try:
        import tkinter  # noqa: F401
        return True
    except ImportError:
        return False


class Model:
    def __init__(self, home, model_text=None):
        self.home = Path(home).resolve()
        self.load(model_text)

    def load(self, text=None):
        text = engine.launcher_model(self.home) if text is None else text
        self.presets, self.groups, self.settings, self.state = {}, {}, [], {}
        by_key = {}
        for line in text.splitlines():
            r = line.split("\t")
            kind = r[0]
            if kind in ("INSTALL", "DATA", "RUNNING", "REVISION"):
                self.state[kind] = r[1:]
            elif kind == "SETTINGS":
                self.state["SETTINGS"] = r[1:]
            elif kind == "PRESET":
                self.presets[r[1]] = (r[2], r[3])
            elif kind == "GROUP":
                self.groups[r[1]] = r[2]
            elif kind == "SETTING":
                s = dict(zip(("key", "group", "scope", "category", "label", "help", "note", "vanilla", "hdplus",
                              "current"), r[1:11]))
                s.update(values=[], requires={}, slider=None)
                self.settings.append(s)
                by_key[s["key"]] = s
            elif kind == "VALUE":
                by_key[r[1]]["values"].append((r[2], r[3]))
            elif kind == "REQUIRES":
                by_key[r[1]]["requires"][r[2]] = r[3]
            elif kind == "SLIDER":
                by_key[r[1]]["slider"] = (int(r[2]), int(r[3]), r[4])
        self.by_key = by_key
        state, preset, base = (self.state.get("SETTINGS") or ["missing", "vanilla", "vanilla"])[:3]
        self.settings_state = state
        self.revision = (self.state.get("REVISION") or ["none"])[0]
        self.profile = preset if preset in PRESETS else "vanilla"
        self.have_custom = self.profile == "custom"
        self.custom_base = base if self.have_custom and base in ("vanilla", "hdplus") else "vanilla"
        self.shown_fixed = self.profile if self.profile != "custom" else self.custom_base
        self.chosen = {s["key"]: s["current"] for s in self.settings}
        self.custom_values = {s["key"]: s["current"] for s in self.settings if s["scope"] == "preset"} \
            if self.have_custom else {}
        self.dirty = False

    @staticmethod
    def column(s, preset):
        return s["hdplus"] if preset == "hdplus" else s["vanilla"]

    def tab(self, s):
        return "controller" if s["key"].startswith("dualsense_") else s["group"] or "advanced"

    def choose_profile(self, preset):
        """The Windows launcher's ChooseProfile: Custom starts from what the previous preset showed."""
        if preset == self.profile:
            return
        if self.profile == "custom":
            self.custom_values = {s["key"]: self.chosen[s["key"]] for s in self.settings if s["scope"] == "preset"}
        else:
            self.shown_fixed = self.profile
        self.profile = preset
        if preset == "custom" and not self.have_custom:
            self.custom_base = self.shown_fixed
            self.custom_values = {s["key"]: self.column(s, self.custom_base) for s in self.settings
                                  if s["scope"] == "preset"}
            self.have_custom = True
        for s in self.settings:
            if s["scope"] == "preset":
                self.chosen[s["key"]] = self.custom_values[s["key"]] if preset == "custom" else self.column(s, preset)
        self.dirty = True

    def set_value(self, key, value):
        """A changed correction under Vanilla / HD+ becomes Custom based on that preset (nothing else changes)."""
        s = self.by_key[key]
        if value not in [v for v, _ in s["values"]]:
            raise ValueError(f"{key}: {value!r}")
        if s["scope"] == "preset" and self.profile != "custom" and value != self.chosen[key]:
            self.have_custom = False  # a fresh Custom from the preset now shown, not an older Custom choice
            self.choose_profile("custom")
        self.chosen[key] = value
        if s["scope"] == "preset":
            self.custom_values[key] = value
        self.dirty = True

    def enabled(self, key):
        return all(self.chosen.get(o) == v for o, v in self.by_key[key]["requires"].items())

    def matches_fixed(self):
        """Custom whose corrections equal a fixed preset (e.g. every HD+ correction chosen by hand), else None."""
        if self.profile != "custom":
            return None
        for preset in ("hdplus", "vanilla"):
            if all(self.chosen[s["key"]] == self.column(s, preset) for s in self.settings if s["scope"] == "preset"):
                return preset
        return None

    def profile_label(self):
        name = self.presets.get(self.profile, (self.profile,))[0]
        if self.profile == "custom":
            return f"{name} (based on {self.presets.get(self.custom_base, (self.custom_base,))[0]})"
        return name

    def save_args(self):
        """The Windows launcher's Save: preferences always (stored only when not the default), corrections only for
        Custom and only where they differ from its base."""
        base = self.custom_base if self.profile == "custom" else None
        pairs = []
        for s in self.settings:
            v = self.chosen[s["key"]]
            if s["scope"] == "preference":
                pairs.append(f"{s['key']}={v}")
            elif self.profile == "custom" and v != self.column(s, self.custom_base):
                pairs.append(f"{s['key']}={v}")
        allow = any(self.by_key[p.split("=", 1)[0]]["category"] == "experimental" and self.profile == "custom"
                    and self.by_key[p.split("=", 1)[0]]["scope"] == "preset" for p in pairs)
        return self.profile, base, pairs, allow

    def save(self, set_preset=None):
        """Through the engine with the revision this window read. Returns (ok, message); STALE reloads."""
        preset, base, pairs, allow = self.save_args()
        try:
            (set_preset or engine.set_preset)(self.home, preset, base, pairs, allow, None, None, self.revision)
        except engine.Refusal as e:
            if e.code == "STALE":
                self.load()
                return False, "Settings were changed elsewhere (for example with F4 in the game). Reloaded; " \
                              "make your change again."
            return False, f"Not saved: {e}"
        self.load()
        return True, f"Saved: {self.profile_label()}."


def launch_play(home):
    """Start the game through Play.sh, detached from this window."""
    return subprocess.Popen([str(Path(home) / "Play.sh")], cwd=str(home), start_new_session=True,
                            stdin=subprocess.DEVNULL)


class Mods:
    """Windows RunMods counterpart: all policy and persistence belong to r3hd_mods.py.

    Explicit paths prevent a developer's R3HD_GAME_DIR from overriding this home. No shell, replacement import,
    automatic enabling, or setting writes. JSON preserves Unicode and multiline descriptions/refusals.
    """
    def __init__(self, home):
        self.home = Path(home).resolve()

    def call(self, command, *args):
        cmd = [sys.executable, "-B", str(TOOLS / "r3hd_mods.py"), command, *map(str, args), "--json",
               "--home", str(self.home), "--mods-root", str(self.home / "mods"),
               "--cache", str(self.home / "cache/mods"), "--game-dir", str(self.home / "data/content")]
        try:
            r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=15 * 60)
            out = json.loads(r.stdout)
            if not isinstance(out, dict):
                raise ValueError("expected a result object")
        except (OSError, ValueError, subprocess.TimeoutExpired) as e:
            raise RuntimeError(f"The mod tool could not be used: {e}") from e
        if r.returncode or out.get("result") != "ok":
            raise RuntimeError(" ".join(str(out.get(k) or "") for k in ("code", "detail", "advice")).strip()
                               or f"The mod tool failed (exit {r.returncode}).")
        return out


def mod_state(row):
    if row.get("gameplay"):   # D-224: validated script-constant overrides (English-only Linux UI)
        return mod_state({**row, "gameplay": False}) + "; changes game logic: no new achievements, back up saves"
    if row["state"] == "active":
        return "Active (partly covered)" if row.get("shadowed") else "Active"
    if row["state"] == "disabled":
        return "Off"
    return ("Off; cannot apply: " if not row["enabled"] else "Not applied: ") + row.get("code", row["state"])


def mods_page(book, home, status):  # pragma: no cover - view exercised by the withdrawn GUI smoke
    """Same actions as the Windows Mods page; long imports run off the UI thread, with input disabled."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    page = ttk.Frame(book, padding=10)
    book.add(page, text="Mods")
    ttk.Label(page, text="Changes apply the next time the game starts. Restart a running game.\n"
                        "Mods are independent of the preset. The first mod wins where ranges overlap.",
              wraplength=690).pack(anchor="w")
    table = ttk.Frame(page)
    table.pack(fill="both", expand=True, pady=8)
    tree = ttk.Treeview(table, columns=("enabled", "name", "version", "state"), show="headings", height=6,
                        selectmode="browse")
    for key, title, width in (("enabled", "On / off", 65), ("name", "Mod (priority order)", 240),
                              ("version", "Version", 80), ("state", "State", 180)):
        tree.heading(key, text=title)
        tree.column(key, width=width, stretch=key in ("name", "state"))
    scroll = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    tree.pack(fill="both", expand=True)
    details = ttk.Frame(page)
    details.pack(fill="both", expand=True)
    detail = tk.Text(details, height=5, wrap="word", state="disabled")
    detail_scroll = ttk.Scrollbar(details, orient="vertical", command=detail.yview)
    detail.configure(yscrollcommand=detail_scroll.set)
    detail_scroll.pack(side="right", fill="y")
    detail.pack(fill="both", expand=True)
    bar = ttk.Frame(page)
    bar.pack(fill="x", pady=(8, 0))
    service, rows, buttons, results = Mods(home), {}, {}, queue.Queue()
    busy = False

    def selected():
        sel = tree.selection()
        return rows.get(sel[0]) if sel else None

    def describe(_event=None):
        row = selected()
        text = "No mods are installed. Install a mod from a .zip file or a folder." if not rows else "Select a mod."
        if row:
            text = f"{row['name']} {row['version']} ({row['id']})\nState: {mod_state(row)}\n" + row.get("description", "")
            text += "\n" + " ".join(str(row.get(k) or "") for k in ("code", "detail"))
            if row.get("shadowed"):
                text += "\nCovered by higher mods:\n" + "\n".join(row["shadowed"])
        detail.configure(state="normal")
        detail.delete("1.0", "end")
        detail.insert("1.0", text)
        detail.configure(state="disabled")
        order = list(rows)
        for key, button in buttons.items():
            enabled = not busy and (key in ("zip", "folder", "reload") or row is not None)
            if key in ("up", "down") and row:
                enabled &= order.index(row["id"]) > 0 if key == "up" else order.index(row["id"]) < len(order) - 1
            button.state(["!disabled"] if enabled else ["disabled"])
        buttons["toggle"].configure(text="Disable" if row and row["enabled"] else "Enable")

    def work(command="list", *args):
        nonlocal busy
        if busy:
            return
        busy = True
        sel = selected()
        keep = sel["id"] if sel else None
        describe()
        status.set("Checking mods...")

        def worker():
            error, result = None, {}
            try:
                result = service.call(command, *args)
            except RuntimeError as e:
                error = str(e)
            try:
                listing = result if command == "list" and not error else service.call("list")
            except RuntimeError as e:
                listing, error = {}, (error or "") + "\nThe mod list cannot be read: " + str(e)
            results.put((listing, error, result.get("id", keep)))

        def poll():
            nonlocal busy
            try:
                listing, error, keep = results.get_nowait()
            except queue.Empty:
                page.after(50, poll)
                return
            tree.delete(*tree.get_children())
            rows.clear()
            for i, row in enumerate(listing.get("mods", [])):
                rows[row["id"]] = row
                tree.insert("", "end", iid=row["id"], values=("on" if row["enabled"] else "off",
                            f"{i + 1}. {row['name']}", row["version"], mod_state(row)))
            if keep in rows:
                tree.selection_set(keep)
                tree.see(keep)
            busy = False
            describe()
            status.set("Not done: " + error if error else "Mods reloaded." if command == "list" else
                       "The mod was installed. Enable it to use it." if command == "import" else
                       "Mod change saved. Restart the game to apply it.")
            if error:
                messagebox.showerror("Mods", error, parent=page)
        threading.Thread(target=worker, daemon=True).start()
        page.after(50, poll)

    def install(folder=False):
        extras = Path(home) / "extras"
        options = dict(parent=page, initialdir=str(extras if extras.is_dir() else home), title="Install a mod")
        source = filedialog.askdirectory(**options) if folder else filedialog.askopenfilename(
            **options, filetypes=[("Mod archive (*.zip)", "*.zip")])
        if source:
            work("import", source)

    def action(command):
        row = selected()
        if not row or busy:
            return
        if command == "remove" and not messagebox.askyesno("Remove mod", f"Remove {row['name']}?\n"
                "Only this installed mod will be removed. Game data and saves are kept.", parent=page):
            return
        if command == "toggle":
            work("disable" if row["enabled"] else "enable", row["id"])
        elif command in ("up", "down"):
            work("move", row["id"], command)
        else:
            work(command, row["id"])

    for key, label, callback in (("zip", "Install .zip", lambda: install()),
                                 ("folder", "Install folder", lambda: install(True)),
                                 ("toggle", "Enable", lambda: action("toggle")),
                                 ("up", "Up", lambda: action("up")), ("down", "Down", lambda: action("down")),
                                 ("remove", "Remove", lambda: action("remove")), ("reload", "Reload", work)):
        buttons[key] = ttk.Button(bar, text=label, command=callback)
        buttons[key].pack(side="left", padx=(0, 4))
    tree.bind("<<TreeviewSelect>>", describe)
    describe()
    # Lazy as on Windows: no compilation until the person opens this page.
    def opened(_event=None):
        if book.select() == str(page):
            work()
    book.bind("<<NotebookTabChanged>>", opened, add="+")
    return SimpleNamespace(busy=lambda: busy, work=work, tree=tree, buttons=buttons, page=page)


# ------------------------------------------------------------------------------------------------- first start
# E-380: the Linux first start is Windows setup (tools/installer/r3hd_setup.iss), not a design of its own: the package
# page (validated with the engine's check-source before going on), the game profile page (Vanilla preselected, as
# setup), the installation (the shared portable preparation), then a Finish page that starts NOTHING by itself and
# offers the setup Finish page's two actions. Setup's own English words (r3hd_en.isl; test_r3hd_settings_gui.py keeps
# them equal):
SETUP_TEXT = {
    'PackageTitle': 'Your game package',
    'PackageDesc': 'Select your own Rayman 3 HD package for Xbox 360.',
    'PackageText': 'Click Browse and select the single Xbox 360 Xbox Live Arcade package file copied from your console: Content\\0000000000000000\\5841123F\\000D0000\\... The file usually has a long hexadecimal name and no extension. Select the file itself, not its folder, an ISO, a ZIP or a PC copy of the game. Setup checks that it is the supported Rayman 3 HD package and extracts the game files; your original is never changed. For an update or repair, leave this empty if the installed game files are intact.',
    'PackageLabel': 'Package file:',
    'PackageNeeded': 'Select your Rayman 3 HD package: the game files are extracted from it.',
    'PackageUnusable': 'This package cannot be used.',
    'PresetTitle': 'Game profile',
    'PresetDesc': 'How should the game look? You can change this at any time in Rayman 3 HD Settings.',
    'PresetText': 'Display and graphics options, such as fullscreen and the rendering resolution, are set in Rayman 3 HD Settings after installation; nothing about them needs to be decided now.',
    'PresetVanilla': 'Vanilla - the Xbox 360 release, with the fixes it needs on PC',
    'PresetHdplus': 'HD+ (Recommended) - Vanilla plus fixes for visual mistakes of the Xbox 360 release',
    'PresetCustom': 'Custom - pick each correction yourself afterwards, in Rayman 3 HD Settings',
    'PresetKeep': 'Keep my current settings (existing installation)',
    'RunPlay': 'Launch Rayman 3 HD Recompiled',
    'RunSettings': 'Open Settings',
}
# Where Linux has to differ: the application menu instead of the desktop / Start menu, and the extracted folder the
# Windows portable build also accepts.
LINUX_SETUP_TEXT = {
    "FinishedBase": "Rayman 3 HD Recompiled is installed.\n\nYou can start the game from the application menu, or with "
                    "Play.sh and Settings.sh in its folder.",
    "Folder": "Extracted folder...",
    "FolderNote": "A verified extracted content folder (Default.xex at its root) is accepted too, as in the Windows "
                  "portable build.",
    "Menu": "Add Rayman 3 HD Recompiled and its Settings to the application menu",
}


def menu_base(data_home=None):
    return Path(data_home or os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share").expanduser()


class Setup:
    """The first-start steps without a window, so tests drive the code the window runs. Windows setup creates its
    Start menu entries with the installation; here the application-menu entries are offered checked, except when they
    belong to another folder's installation (kept unless the person ticks the box)."""

    def __init__(self, home, prepare, releases=None, data_home=None):
        self.home = Path(home).resolve()
        self.prepare_fn, self.releases, self.data_home = prepare, releases, data_home
        self.source = self.checked = self.result = self.menu_result = None
        self.preset = "vanilla"  # setup's preselection (index 0); see E-379 / D-170 for the "Recommended" note
        # Setup's fourth choice: an existing settings.json (for example game data lost, settings kept) is offered and
        # preselected as "Keep my current settings"; another choice is applied through the engine, which keeps the
        # display / graphics preferences, as setup's explicit choice does.
        self.keep = engine.settings_state(self.home)["state"] == "ok"
        if self.keep:
            self.preset = "keep"
        import r3hd_play
        self.owner = r3hd_play.entry_home(menu_base(data_home) / "applications" / f"{r3hd_play.APP_ID}.desktop")
        self.menu = self.owner in (None, str(self.home))

    def menu_text(self):
        if self.owner in (None, str(self.home)):
            return LINUX_SETUP_TEXT["Menu"]
        return LINUX_SETUP_TEXT["Menu"] + f" (replaces the entries of {self.owner})"

    def check(self, source):
        """The package page's Next: (ok, message). Setup's words; the engine's reason, as setup shows it."""
        if not str(source or "").strip():
            return False, SETUP_TEXT["PackageNeeded"]
        path = Path(str(source).strip().strip('"')).expanduser()
        try:
            self.checked = engine.check_source(path, self.releases if self.releases is not None else
                                               engine.load_releases())
        except engine.Refusal as e:
            return False, SETUP_TEXT["PackageUnusable"] + "\n\n" + e.detail
        self.source = path
        return True, self.checked.get("display_name") or self.checked["kind"]

    def run(self, log):
        """Install: the shared preparation, then the menu entries. (ok, message); never starts the game."""
        try:
            self.result = self.prepare_fn(self.home, self.source, preset=None if self.preset == "keep" else self.preset,
                                          log=log)
            if self.keep and self.preset != "keep":
                engine.set_preset(self.home, self.preset, "vanilla" if self.preset == "custom" else None)
        except (engine.Refusal, OSError, ValueError) as e:
            return False, f"Setup stopped: {getattr(e, 'detail', e)}"
        if self.menu:
            import r3hd_play
            try:
                self.menu_result = r3hd_play.desktop_entry(self.home, self.data_home,
                                                           package=self.source if self.source.is_file() else None)
            except OSError as e:
                log(f"The application menu entries could not be written: {e}")
        return True, LINUX_SETUP_TEXT["FinishedBase"]


def finished_choice(log=print, ask=None):
    """The Finish page in a terminal (no window): nothing starts until the person chooses. Returns "play", "settings"
    or None."""
    ask = ask or input
    log(LINUX_SETUP_TEXT["FinishedBase"].replace("\n\n", " "))
    log(f"  1  {SETUP_TEXT['RunPlay']}")
    log(f"  2  {SETUP_TEXT['RunSettings']}")
    while True:
        try:
            answer = ask("Choice (1-2, Enter = finish): ").strip()
        except EOFError:
            return None
        if answer in ("", "1", "2"):
            return {"": None, "1": "play", "2": "settings"}[answer]


# ------------------------------------------------------------------------------------------------- the window

def run_settings(home):  # pragma: no cover - interactive
    import tkinter as tk
    from tkinter import messagebox, ttk
    import r3hd_play
    m = Model(home)
    if m.state.get("INSTALL", ["not_installed"])[0] != "ok" or m.state.get("DATA", ["missing"])[0] != "ok":
        import r3hd_portable
        done = run_setup(home, r3hd_portable.prepare)
        if done is None:
            return 2
        if done[1] == "play":
            launch_play(home)
        if done[1] != "settings":
            return 0
        m.load()
    root = tk.Tk()
    smoke = os.environ.get("R3HD_GUI_SMOKE") == "1"  # tests: build, exercise and destroy, never shown
    if smoke:
        root.withdraw()
    root.title("Rayman 3 HD Recompiled - Settings")
    root.minsize(760, 560)
    status = tk.StringVar(value=f"{m.home}")
    profile = tk.StringVar(value=m.profile)
    profile_text = tk.StringVar()
    widgets = {}

    top = ttk.Frame(root, padding=10)
    top.pack(fill="x")
    ttk.Label(top, text="Preset", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w")
    for i, key in enumerate(PRESETS):
        name, text = m.presets.get(key, (key, ""))
        ttk.Radiobutton(top, text=name, value=key, variable=profile,
                        command=lambda k=key: (m.choose_profile(k), refresh())).grid(row=i + 1, column=0, sticky="w")
        ttk.Label(top, text=text, foreground="#555").grid(row=i + 1, column=1, sticky="w", padx=8)
    ttk.Label(top, textvariable=profile_text).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
    simplify = ttk.Button(top, text="Use the preset", command=lambda: (m.choose_profile(m.matches_fixed()), refresh()))

    book = ttk.Notebook(root)
    book.pack(fill="both", expand=True, padx=10)
    pages = {}
    for key, title in TABS:
        if not any(m.tab(s) == key for s in m.settings):
            continue
        outer = ttk.Frame(book, padding=10)
        book.add(outer, text=m.groups.get(key, title) if key != "controller" else title)
        pages[key] = outer
        outer.columnconfigure(1, weight=1)
    rows = {k: 0 for k in pages}
    for s in m.settings:
        page = pages[m.tab(s)]
        r = rows[m.tab(s)]
        rows[m.tab(s)] += 2
        label = s["label"] + (f"  ({s['note']})" if s["note"] else "")
        ttk.Label(page, text=label).grid(row=r, column=0, sticky="w", pady=(6, 0))
        if s["slider"]:
            lo, hi, unit = s["slider"]
            var = tk.IntVar(value=int(m.chosen[s["key"]]))
            text = tk.StringVar(value=f"{var.get()} %" if unit == "percent" else str(var.get()))

            def moved(_v, key=s["key"], var=var, text=text, unit=unit):
                v = str(int(float(var.get())))
                text.set(f"{v} %" if unit == "percent" else v)
                if v in [x for x, _ in m.by_key[key]["values"]] and v != m.chosen[key]:
                    m.set_value(key, v)
                    refresh(keep=key)
            w = ttk.Scale(page, from_=lo, to=hi, variable=var, command=moved)
            w.grid(row=r, column=1, sticky="we", padx=8, pady=(6, 0))
            ttk.Label(page, textvariable=text, width=6).grid(row=r, column=2, sticky="w")
            widgets[s["key"]] = (w, var, "slider")
        else:
            labels = [lbl for _, lbl in s["values"]]
            var = tk.StringVar()
            w = ttk.Combobox(page, values=labels, textvariable=var, state="readonly", width=34)

            def picked(_e, key=s["key"], var=var):
                value = next(v for v, lbl in m.by_key[key]["values"] if lbl == var.get())
                m.set_value(key, value)
                refresh(keep=key)
            w.bind("<<ComboboxSelected>>", picked)
            w.grid(row=r, column=1, sticky="w", padx=8, pady=(6, 0))
            widgets[s["key"]] = (w, var, "combo")
        help_text = " ".join(x for x in (s["help"], LINUX_NOTES.get(s["key"], "")) if x)
        ttk.Label(page, text=help_text, foreground="#555", wraplength=640).grid(row=r + 1, column=0, columnspan=3,
                                                                               sticky="w")

    mods_view = mods_page(book, m.home, status)

    def refresh(keep=None):
        profile.set(m.profile)
        same = m.matches_fixed()
        profile_text.set(f"Now: {m.profile_label()}" + ("   (unsaved changes)" if m.dirty else ""))
        if same:
            simplify.configure(text=f"These choices equal {m.presets[same][0]}: use that preset")
            simplify.grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
        else:
            simplify.grid_remove()
        for key, (w, var, kind) in widgets.items():
            if key != keep:
                if kind == "slider":
                    var.set(int(m.chosen[key]))
                else:
                    var.set(dict(m.by_key[key]["values"]).get(m.chosen[key], m.chosen[key]))
            w.state(["!disabled"] if m.enabled(key) else ["disabled"])

    def save():
        ok, message = m.save()
        status.set(message)
        refresh()
        return ok

    def play():  # the Windows launcher's Play: saves unsaved changes first, starts the game, closes the window
        if mods_view.busy():
            status.set("Wait for the mod operation to finish before starting the game.")
            return
        if m.dirty and not save():
            return
        launch_play(m.home)
        root.destroy()

    def desktop(add):
        r = r3hd_play.desktop_entry(m.home) if add else r3hd_play.remove_desktop_entry(m.home)
        if add:
            status.set("Added to the application menu" + (" with the game's icon." if r["icon"] == "package" else
                       " (neutral icon: supply your package file once to use the game's icon)."))
        else:
            status.set("Removed from the application menu." if r.get("removed") else r.get("kept", "Nothing to remove."))

    def close():  # the Windows launcher's ConfirmClose: Yes saves, No discards, Cancel stays
        if mods_view.busy():
            status.set("Wait for the mod operation to finish before closing Settings.")
            return
        if m.dirty:
            answer = messagebox.askyesnocancel("Settings", "Save your changes before closing?")
            if answer is None or answer and not save():
                return
        root.destroy()

    bar = ttk.Frame(root, padding=10)
    bar.pack(fill="x")
    ttk.Button(bar, text="Save", command=save).pack(side="left")
    ttk.Button(bar, text="Play", command=play).pack(side="left", padx=6)
    ttk.Button(bar, text="Reload", command=lambda: (m.load(), refresh(), status.set("Reloaded."))).pack(side="left")
    ttk.Button(bar, text="Close", command=close).pack(side="right")
    ttk.Button(bar, text="Remove menu entry", command=lambda: desktop(False)).pack(side="right", padx=6)
    ttk.Button(bar, text="Add to application menu", command=lambda: desktop(True)).pack(side="right")
    ttk.Label(root, textvariable=status, padding=(10, 0, 10, 8), foreground="#333").pack(fill="x")
    root.protocol("WM_DELETE_WINDOW", close)
    refresh()
    if smoke:
        for key in PRESETS:
            m.choose_profile(key)
            refresh()
        m.set_value("red_correction", "original")
        refresh(keep="red_correction")
        print("R3HD_GUI_SMOKE widgets=%d tabs=%d label=%s" % (len(widgets), len(pages), m.profile_label()))
        root.destroy()
        return 0
    root.mainloop()
    return 0


def run_setup(home, prepare, releases=None, data_home=None):  # pragma: no cover - interactive
    """First start (E-380): Windows setup's pages over the shared preparation (Setup above). Returns
    (prepare's result, action) with action "play", "settings" or None (Finish); None when cancelled. It never starts
    the game itself: the caller acts on the person's explicit choice."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    s = Setup(home, prepare, releases, data_home)
    root = tk.Tk()
    smoke = os.environ.get("R3HD_GUI_SMOKE") == "1"  # tests: built, driven and destroyed; never shown
    if smoke:
        root.withdraw()
    root.title("Rayman 3 HD Recompiled - Setup")
    root.minsize(680, 460)
    out = {"value": None}
    log = queue.Queue()
    source = tk.StringVar()
    preset = tk.StringVar(value=s.preset)
    menu = tk.BooleanVar(value=s.menu)
    heading = tk.StringVar()
    sub = tk.StringVar()
    seen = []

    head = ttk.Frame(root, padding=(12, 10))
    head.pack(fill="x")
    ttk.Label(head, textvariable=heading, font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
    ttk.Label(head, textvariable=sub).pack(anchor="w")
    ttk.Separator(root).pack(fill="x")
    body = ttk.Frame(root, padding=12)
    body.pack(fill="both", expand=True)
    pages = {k: ttk.Frame(body) for k in ("package", "preset", "install", "finished")}

    p = pages["package"]
    ttk.Label(p, wraplength=640, text=SETUP_TEXT["PackageText"]).pack(anchor="w")
    ttk.Label(p, wraplength=640, foreground="#555", text=LINUX_SETUP_TEXT["FolderNote"]).pack(anchor="w", pady=(6, 0))
    ttk.Label(p, text=SETUP_TEXT["PackageLabel"]).pack(anchor="w", pady=(10, 0))
    row = ttk.Frame(p)
    row.pack(fill="x", pady=4)
    ttk.Entry(row, textvariable=source).pack(side="left", fill="x", expand=True)
    ttk.Button(row, text="Browse...", command=lambda: source.set(filedialog.askopenfilename(
        title=SETUP_TEXT["PackageDesc"]) or source.get())).pack(side="left", padx=4)
    ttk.Button(row, text=LINUX_SETUP_TEXT["Folder"], command=lambda: source.set(filedialog.askdirectory(
        title="Extracted content (Default.xex at its root)") or source.get())).pack(side="left")
    ttk.Checkbutton(p, text=s.menu_text(), variable=menu).pack(anchor="w", pady=(12, 0))

    p = pages["preset"]
    ttk.Label(p, wraplength=640, text=SETUP_TEXT["PresetText"]).pack(anchor="w", pady=(0, 10))
    for key, name in zip(PRESETS + ("keep",), ("PresetVanilla", "PresetHdplus", "PresetCustom", "PresetKeep")):
        if key != "keep" or s.keep:
            ttk.Radiobutton(p, text=SETUP_TEXT[name], value=key, variable=preset).pack(anchor="w", pady=2)

    text = tk.Text(pages["install"], height=12, state="disabled")
    text.pack(fill="both", expand=True)
    done = tk.StringVar()
    p = pages["finished"]
    ttk.Label(p, textvariable=done, wraplength=640, justify="left").pack(anchor="w")
    acts = ttk.Frame(p)
    acts.pack(anchor="w", pady=16)

    nav = ttk.Frame(root, padding=10)
    nav.pack(fill="x")
    back = ttk.Button(nav, text="< Back")
    nxt = ttk.Button(nav, text="Next >")
    cancel = ttk.Button(nav, text="Cancel")
    finish = ttk.Button(nav, text="Finish", command=lambda: end(None))
    cancel.pack(side="right")
    nxt.pack(side="right", padx=6)
    back.pack(side="right")

    def end(action):
        out["value"] = (s.result, action)
        root.destroy()

    ttk.Button(acts, text=SETUP_TEXT["RunPlay"], command=lambda: end("play")).pack(side="left")
    ttk.Button(acts, text=SETUP_TEXT["RunSettings"], command=lambda: end("settings")).pack(side="left", padx=8)

    def show(name):
        seen.append(name)
        for f in pages.values():
            f.pack_forget()
        pages[name].pack(fill="both", expand=True)
        titles = {"package": (SETUP_TEXT["PackageTitle"], SETUP_TEXT["PackageDesc"]),
                  "preset": (SETUP_TEXT["PresetTitle"], SETUP_TEXT["PresetDesc"]),
                  "install": ("Installing", "Identifying, extracting and checking your game files..."),
                  "finished": ("Setup finished", "")}
        heading.set(titles[name][0])
        sub.set(titles[name][1])
        back.state(["!disabled"] if name == "preset" else ["disabled"])
        nxt.state(["!disabled"] if name in ("package", "preset") else ["disabled"])
        nxt.configure(text="Install" if name == "preset" else "Next >")
        cancel.state(["disabled"] if name == "install" else ["!disabled"])
        if name == "finished":
            for w in (back, nxt, cancel):
                w.pack_forget()
            finish.pack(side="right")
        show.current = name

    def error(message):
        if smoke:
            print("R3HD_GUI_SMOKE message=" + message.splitlines()[0])
        else:
            messagebox.showerror("Rayman 3 HD Recompiled", message, parent=root)

    def work():
        ok, message = s.run(log.put)
        log.put(("end", ok, message))

    def poll():
        try:
            while True:
                item = log.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "end":
                    _, ok, message = item
                    if ok:
                        done.set(message)
                        show("finished")
                    else:
                        error(message)
                        show("preset")
                    return
                text.configure(state="normal")
                text.insert("end", str(item) + "\n")
                text.see("end")
                text.configure(state="disabled")
        except queue.Empty:
            pass
        root.after(150, poll)

    def go_next():
        if show.current == "package":
            ok, message = s.check(source.get())
            if not ok:
                error(message)
                return
            s.menu = bool(menu.get())
            show("preset")
        elif show.current == "preset":
            s.preset = preset.get()
            show("install")
            threading.Thread(target=work, daemon=True).start()
            root.after(150, poll)

    def go_cancel():
        if smoke or messagebox.askyesno("Rayman 3 HD Recompiled", "Exit setup? Nothing has been installed.",
                                        parent=root):
            out["value"] = None
            root.destroy()

    back.configure(command=lambda: show("package"))
    nxt.configure(command=go_next)
    cancel.configure(command=go_cancel)
    root.protocol("WM_DELETE_WINDOW", lambda: end(None) if show.current == "finished" else
                  (None if show.current == "install" else go_cancel()))
    show("package")
    if smoke:  # tests: package page, profile page, installation, Finish page; the env chooses the final action
        source.set(os.environ.get("R3HD_GUI_SMOKE_SOURCE", ""))
        go_next()
        preset.set(os.environ.get("R3HD_GUI_SMOKE_PRESET", "hdplus"))
        go_next()
        while show.current == "install":
            root.update()
        print("R3HD_GUI_SMOKE setup pages=%s" % ",".join(seen))
        action = os.environ.get("R3HD_GUI_SMOKE_ACTION") or None
        if show.current == "finished":
            end(action)
        else:
            root.destroy()
        return out["value"]
    root.mainloop()
    return out["value"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--home", required=True)
    ap.add_argument("--setup", action="store_true", help="the first-start window only")
    a = ap.parse_args(argv)
    if not gui_available():
        print("R3HD_SETTINGS_GUI unavailable (tkinter or a display missing); use ./Settings.sh --console", file=sys.stderr)
        return 3
    if a.setup:
        import r3hd_portable
        done = run_setup(Path(a.home), r3hd_portable.prepare)
        if done is None:
            return 2
        if done[1] == "play":
            launch_play(Path(a.home))
        return run_settings(Path(a.home)) if done[1] == "settings" else 0
    return run_settings(Path(a.home))


if __name__ == "__main__":
    sys.exit(main())
