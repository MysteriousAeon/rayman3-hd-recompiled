#!/usr/bin/env python3
"""E-379, E-380: the Linux Settings window's model and first start (setup) against the real engine (any platform; no window is opened).

  python3 tools/linux/test_r3hd_settings_gui.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import r3hd_settings_gui as G  # noqa: E402
import r3hd_installer as engine  # noqa: E402
import r3hd_portable as portable  # noqa: E402
import r3hd_play as P  # noqa: E402

HDPLUS_CORRECTIONS = {"combo_close": "delayed", "layer_coords": "separate", "red_correction": "bypass",
                      "texture_orient": "corrected", "sky_clear": "background", "lit_uv_scroll": "applied"}


def home_with(root, settings):
    home = Path(root).resolve()
    engine.write_json(home / "settings.json", settings)
    engine.write_json(home / engine.STATE, {"schema": 1, "distribution": "portable", "version": "test", "files": {},
                                            "data": {"release": engine.load_releases()[0]["id"]}})
    return home


def fresh(root, preset):
    home = Path(root).resolve()
    return home_with(root, engine.settings_from_args(preset, None, (), False, home, fresh=True))


def saved(home):
    return json.loads((home / "settings.json").read_text(encoding="utf-8"))


class SettingsModel(unittest.TestCase):
    def test_every_shown_setting_is_offered(self):
        with tempfile.TemporaryDirectory() as root:
            m = G.Model(fresh(root, "hdplus"))
            self.assertEqual([s["key"] for s in m.settings], [o["key"] for o in engine.describe_options()])
            self.assertTrue(all(s["values"] for s in m.settings))
            self.assertEqual(set(m.presets), set(G.PRESETS))
            self.assertEqual(m.presets["hdplus"][0], "HD+ (Recommended)")

    def test_maintainer_case_hdplus_plus_two_preferences(self):
        """LX2D: HD+ corrections with the DualSense speaker and gameplay subtitles: a preference change keeps HD+."""
        with tempfile.TemporaryDirectory() as root:
            home = fresh(root, "hdplus")
            m = G.Model(home)
            m.set_value("dualsense_speaker", "on")
            m.set_value("gameplay_subtitles", "all")
            self.assertEqual(m.profile, "hdplus")
            ok, _ = m.save()
            d = saved(home)
            self.assertTrue(ok)
            self.assertEqual((d["preset"], d.get("overrides")), ("hdplus", None))
            self.assertEqual((d["preferences"]["dualsense_speaker"], d["preferences"]["gameplay_subtitles"]), ("on", "all"))
            self.assertEqual(d["preferences"]["dualsense_light"], "on")  # install default kept

    def test_one_correction_becomes_custom_on_that_preset(self):
        with tempfile.TemporaryDirectory() as root:
            home = fresh(root, "hdplus")
            m = G.Model(home)
            m.set_value("combo_close", "original")
            self.assertEqual((m.profile, m.custom_base), ("custom", "hdplus"))
            self.assertEqual(m.profile_label(), "Custom (based on HD+ (Recommended))")
            self.assertEqual(m.chosen["red_correction"], "bypass")  # the other HD+ corrections stay
            m.save()
            d = saved(home)
            self.assertEqual((d["preset"], d["base"], d["overrides"]), ("custom", "hdplus", {"combo_close": "original"}))

    def test_lx2d_custom_equal_to_hdplus_is_recognised(self):
        """The LX2D file: Custom on Vanilla with every HD+ correction typed in by hand."""
        with tempfile.TemporaryDirectory() as root:
            home = home_with(root, {"schema": 3, "preset": "custom", "base": "vanilla", "overrides": HDPLUS_CORRECTIONS,
                                    "preferences": {"display": "windowed", "dualsense_speaker": "on",
                                                    "gameplay_subtitles": "all", "dualsense_light": "on"}})
            m = G.Model(home)
            self.assertEqual(m.matches_fixed(), "hdplus")
            m.choose_profile("hdplus")
            m.save()
            d = saved(home)
            self.assertEqual((d["preset"], d.get("overrides")), ("hdplus", None))
            self.assertEqual(d["preferences"]["dualsense_speaker"], "on")

    def test_choose_profile_matches_the_windows_launcher(self):
        with tempfile.TemporaryDirectory() as root:
            m = G.Model(fresh(root, "vanilla"))
            m.choose_profile("hdplus")
            m.choose_profile("custom")  # Custom starts from what was shown last: HD+
            self.assertEqual(m.custom_base, "hdplus")
            self.assertEqual(m.chosen["sky_clear"], "background")
            m.set_value("sky_clear", "original")
            m.choose_profile("vanilla")
            m.choose_profile("custom")  # the Custom choices made in this session come back
            self.assertEqual((m.custom_base, m.chosen["sky_clear"], m.chosen["red_correction"]),
                             ("hdplus", "original", "bypass"))

    def test_requirements_disable_dependent_settings(self):
        with tempfile.TemporaryDirectory() as root:
            m = G.Model(fresh(root, "vanilla"))
            m.set_value("dualsense_trigger", "off")
            self.assertFalse(m.enabled("dualsense_trigger_strength"))
            m.set_value("dualsense_trigger", "on")
            self.assertTrue(m.enabled("dualsense_trigger_strength"))
            self.assertEqual(m.tab(m.by_key["dualsense_speaker"]), "controller")
            with self.assertRaises(ValueError):
                m.set_value("dualsense_trigger_strength", "101")

    def test_f4_and_the_window_never_overwrite_each_other(self):
        with tempfile.TemporaryDirectory() as root:
            home = fresh(root, "hdplus")
            m = G.Model(home)
            m.set_value("mouse_camera", "on")
            engine.set_preferences(home, ["dualsense_speaker=on"], m.revision)  # F4 saves in the game meanwhile
            ok, message = m.save()
            self.assertFalse(ok)
            self.assertIn("changed elsewhere", message)
            self.assertEqual(saved(home)["preferences"]["dualsense_speaker"], "on")  # F4's change kept
            self.assertEqual(m.chosen["dualsense_speaker"], "on")  # the window reloaded it
            m.set_value("mouse_camera", "on")
            self.assertTrue(m.save()[0])
            d = saved(home)["preferences"]
            self.assertEqual((d["mouse_camera"], d["dualsense_speaker"]), ("on", "on"))

    def test_desktop_message_without_a_terminal(self):
        calls = []
        with mock.patch.object(portable.shutil, "which", lambda n: "/usr/bin/" + n if n == "zenity" else None):
            self.assertEqual(portable.desktop_message("x", run=lambda argv, **k: calls.append(argv)), "zenity")
        self.assertEqual(calls, [["zenity", "--error", "--text", "x"]])

    def test_gui_needs_a_display(self):
        with mock.patch.dict(G.os.environ, {"DISPLAY": ""}):
            self.assertFalse(G.gui_available())


def windows_setup_strings():
    out = {}
    for line in (HERE.parent / "installer" / "r3hd_en.isl").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.startswith(";"):
            k, v = line.split("=", 1)
            out[k] = v.replace("%n", "\n")
    return out


NO_WINDOW = object()


class Blocked(AssertionError):
    pass


def no_process(*a, **k):
    raise Blocked(f"a process was started: {a}")


REAL_POPEN = G.subprocess.Popen
GAME = ("Play.sh", "Settings.sh", "r3hd_play.py", "r3hd", "r3hd.exe", "r3hd_launcher.exe")


def no_game(args, *a, **k):
    """subprocess.Popen for the tests: the engine's own helpers (tasklist, ...) run; starting the game fails."""
    argv = [args] if isinstance(args, (str, Path)) else list(args)
    if any(Path(str(x)).name in GAME for x in argv):
        raise Blocked(f"the game was started: {argv}")
    return REAL_POPEN(args, *a, **k)


class FirstStart(unittest.TestCase):
    """E-380: the first start is Windows setup's flow; a successful preparation starts nothing by itself."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.menu = self.root / "share"
        patches = [mock.patch.object(G.subprocess, "Popen", no_game),
                   mock.patch.object(portable.subprocess, "call", no_process),
                   mock.patch.object(G, "launch_play", no_process),
                   mock.patch.object(P, "refresh_desktop_cache", lambda *a, **k: None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def fake_prepare(self, calls):
        def prepare(home, source, preset=None, log=print):
            log("identified")
            calls.append((Path(source).name, preset))
            return {"home": str(home), "data": "verified", "version": "test", "installed": True}
        return prepare

    def test_setup_speaks_with_windows_setup_words(self):
        isl = windows_setup_strings()
        for key, text in G.SETUP_TEXT.items():
            self.assertEqual(text, isl[key], key)
        self.assertEqual((G.SETUP_TEXT["RunPlay"], G.SETUP_TEXT["RunSettings"]),
                         ("Launch Rayman 3 HD Recompiled", "Open Settings"))
        self.assertTrue(G.LINUX_SETUP_TEXT["FinishedBase"].startswith(isl["FinishedBase"].split("\n")[0]))

    def test_package_page_validates_with_the_engine(self):
        s = G.Setup(self.home, self.fake_prepare([]), data_home=self.menu)
        self.assertEqual(s.check(""), (False, G.SETUP_TEXT["PackageNeeded"]))
        junk = self.root / "not-a-package.bin"
        junk.write_bytes(b"\0" * 4096)
        ok, message = s.check(str(junk))
        self.assertFalse(ok)
        self.assertTrue(message.startswith(G.SETUP_TEXT["PackageUnusable"] + "\n\n"), message)
        self.assertIsNone(s.source)

    def test_successful_preparation_starts_nothing_and_adds_the_menu_entries(self):
        calls = []
        pkg = self.root / "5841123F-package"
        pkg.write_bytes(b"x")
        s = G.Setup(self.home, self.fake_prepare(calls), data_home=self.menu)
        self.assertEqual(s.preset, "vanilla")  # Windows setup's preselection
        with mock.patch.object(engine, "check_source", lambda p, r: {"kind": "package", "display_name": "Rayman 3 HD"}):
            self.assertEqual(s.check(str(pkg)), (True, "Rayman 3 HD"))
        s.preset = "hdplus"
        log = []
        self.assertEqual(s.run(log.append), (True, G.LINUX_SETUP_TEXT["FinishedBase"]))  # no Blocked raised
        self.assertEqual(calls, [(pkg.name, "hdplus")])
        entries = sorted(p.name for p in (self.menu / "applications").iterdir())
        self.assertEqual(entries, ["rayman3hd-recompiled-settings.desktop", "rayman3hd-recompiled.desktop"])
        self.assertIn(f"X-R3HD-Home={self.home}", (self.menu / "applications/rayman3hd-recompiled.desktop").read_text())

    def test_menu_entries_of_another_installation_are_kept(self):
        other = self.root / "other"
        other.mkdir()
        P.desktop_entry(other, self.menu)
        before = (self.menu / "applications/rayman3hd-recompiled.desktop").read_text()
        s = G.Setup(self.home, self.fake_prepare([]), data_home=self.menu)
        self.assertFalse(s.menu)
        self.assertIn(str(other), s.menu_text())
        s.source = self.root / "pkg"
        self.assertTrue(s.run(lambda *_: None)[0])
        self.assertEqual((self.menu / "applications/rayman3hd-recompiled.desktop").read_text(), before)

    def test_existing_settings_are_kept_or_replaced_as_setup_does(self):
        """Windows setup's "Keep my current settings": preselected when settings.json exists; another choice keeps
        the preferences (here the LX2D speaker and subtitles)."""
        for choice, expect in (("keep", "hdplus"), ("vanilla", "vanilla")):
            (self.root / choice).mkdir()
            home = fresh(self.root / choice, "hdplus")
            m = G.Model(home)
            m.set_value("dualsense_speaker", "on")
            m.set_value("gameplay_subtitles", "all")
            self.assertTrue(m.save()[0])
            calls = []
            s = G.Setup(home, self.fake_prepare(calls), data_home=self.menu)
            self.assertEqual((s.keep, s.preset), (True, "keep"))
            s.source, s.menu, s.preset = self.root / "pkg", False, choice
            self.assertTrue(s.run(lambda *_: None)[0])
            self.assertEqual(calls, [("pkg", None if choice == "keep" else choice)])
            d = saved(home)
            self.assertEqual(d["preset"], expect, choice)
            self.assertEqual((d["preferences"]["dualsense_speaker"], d["preferences"]["gameplay_subtitles"]),
                             ("on", "all"), choice)
        self.assertFalse(G.Setup(self.home, self.fake_prepare([]), data_home=self.menu).keep)

    def test_refused_preparation_stays_in_setup(self):
        def prepare(home, source, preset=None, log=print):
            raise engine.Refusal("RELEASE_MISMATCH", "Package does not match this application")
        s = G.Setup(self.home, prepare, data_home=self.menu)
        s.source = self.root / "pkg"
        self.assertEqual(s.run(print), (False, "Setup stopped: Package does not match this application"))
        self.assertFalse((self.menu / "applications").exists())

    # ---- the entry point (Play.sh / Settings.sh -> r3hd_portable.main) with a stand-in preparation

    def main(self, action, *, prepare_result=None, setup=NO_WINDOW, console=None, extra=()):
        """Runs portable.main as Linux; returns (exit code, processes started, Settings windows opened)."""
        started, windows = [], []

        def prepare(home, source=None, ask=False, **k):
            if prepare_result is None:
                raise engine.Refusal("PACKAGE_REQUIRED", "Game data missing; run Play.cmd and supply your package")
            return dict(prepare_result)
        tty = mock.Mock()
        tty.isatty.return_value = console is not None
        with mock.patch.object(portable, "LINUX", True), mock.patch.object(portable, "prepare", prepare), \
                mock.patch.object(portable.subprocess, "call", lambda args, **k: started.append(args) or 0), \
                mock.patch.object(portable.sys, "stdin", tty), \
                mock.patch.object(portable.sys, "argv", ["r3hd_portable.py", action, *extra]), \
                mock.patch.object(G, "gui_available", lambda: setup is not NO_WINDOW), \
                mock.patch.object(G, "run_setup", lambda home, prep: setup() if callable(setup) else setup), \
                mock.patch.object(portable, "desktop_message", lambda text: None), \
                mock.patch.object(G, "run_settings", lambda home: windows.append(home) or 0), \
                mock.patch("builtins.input", lambda prompt="": console.pop(0)), \
                mock.patch.dict(portable.os.environ, {}):
            code = portable.main()
        return code, started, windows

    def test_window_finish_starts_nothing(self):
        for action in ("play", "settings"):
            code, started, windows = self.main(action, setup=({"data": "verified"}, None))
            self.assertEqual((code, started, windows), (0, [], []), action)

    def test_window_launch_starts_the_game_once(self):
        code, started, windows = self.main("settings", setup=({"data": "verified"}, "play"))
        self.assertEqual((code, len(started), windows), (0, 1, []))
        self.assertTrue(started[0][2].endswith("r3hd_play.py"), started)

    def test_window_open_settings_opens_settings_only(self):
        code, started, windows = self.main("play", setup=({"data": "verified"}, "settings"))
        self.assertEqual((code, started, len(windows)), (0, [], 1))

    def test_cancelled_setup_starts_nothing(self):
        self.assertEqual(self.main("play", setup=None), (2, [], []))

    def test_a_ready_home_skips_setup(self):
        code, started, windows = self.main("play", prepare_result={"data": "verified"},
                                           setup=lambda: no_process("setup window"))
        self.assertEqual((code, len(started)), (0, 1))
        code, started, windows = self.main("settings", prepare_result={"data": "verified"}, setup=("unused", None))
        self.assertEqual((code, started, len(windows)), (0, [], 1))

    def test_console_finish_page(self):
        installed = {"data": "verified", "installed": True}
        self.assertEqual(self.main("play", prepare_result=installed, console=[""], extra=("--console",))[:2], (0, []))
        code, started, _ = self.main("play", prepare_result=installed, console=["x", "1"], extra=("--console",))
        self.assertTrue(started[0][2].endswith("r3hd_play.py"))
        code, started, _ = self.main("play", prepare_result=installed, console=["2"], extra=("--console",))
        self.assertTrue(started[0][2].endswith("r3hd_installer.py") and "configure" in started[0], started)

    def test_installed_without_a_terminal_or_window_starts_nothing(self):
        code, started, windows = self.main("play", prepare_result={"data": "verified", "installed": True},
                                           extra=("--console",))
        self.assertEqual((code, started, windows), (0, [], []))


def _tk_usable():
    try:
        import tkinter  # noqa: F401
    except ImportError:
        return False
    return G.os.name == "nt" or bool(G.os.environ.get("DISPLAY"))


@unittest.skipUnless(_tk_usable(), "tkinter or a display missing (the model tests above still ran)")
class WindowSmoke(unittest.TestCase):
    """The real windows built hidden (R3HD_GUI_SMOKE=1: withdrawn, exercised, destroyed; never shown)."""

    def test_settings_window_builds_every_setting(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(G.os.environ, {"R3HD_GUI_SMOKE": "1"}):
            home = fresh(root, "hdplus")
            orig = G.Model.load

            def load(self, text=None):  # a test home has no game data: skip the setup branch
                orig(self, text)
                self.state["DATA"], self.state["INSTALL"] = ["ok"], ["ok"]
            with mock.patch.object(G.Model, "load", load):
                self.assertEqual(G.run_settings(home), 0)

    def test_setup_window_pages_and_finish(self):
        """Package page, game profile page, installation, Finish page; Finish and both actions start nothing here."""
        for action in ("", "play", "settings"):
            calls = []

            def prepare(home, source, preset=None, log=print):
                log("identified")
                calls.append((source.name, preset))
                return {"data": "verified"}
            with tempfile.TemporaryDirectory() as root,                     mock.patch.object(engine, "check_source", lambda p, r: {"kind": "package"}),                     mock.patch.object(G.subprocess, "Popen", no_game),                     mock.patch.object(G, "launch_play", no_process),                     mock.patch.dict(G.os.environ, {"R3HD_GUI_SMOKE": "1", "R3HD_GUI_SMOKE_SOURCE": "pkg.bin",
                                                   "R3HD_GUI_SMOKE_ACTION": action, "XDG_DATA_HOME": root}):
                self.assertEqual(G.run_setup(Path(root), prepare), ({"data": "verified"}, action or None))
            self.assertEqual(calls, [("pkg.bin", "hdplus")])

if __name__ == "__main__":
    unittest.main()
