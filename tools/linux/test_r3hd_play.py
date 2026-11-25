"""Regression for tools/linux/r3hd_play.py (LX-2): it must stay equal to tools/play.ps1, which it mirrors.

Parses play.ps1 for the setting -> parameter table, the `$env:R3HD_X = $Param` pass-through assignments, the game
language ids and the test-only variable list, and compares them with the Linux launcher's tables. Then builds dry-run
plans (no executable, no game data needed) and checks the HD+ preset switches the features on.
"""
import re
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import r3hd_play as P  # noqa: E402
sys.path.insert(0, str(HERE.parent))
import r3hd_installer as engine  # noqa: E402

PS1 = (HERE.parent / "play.ps1").read_text(encoding="utf-8")


def plan(*extra):
    with tempfile.TemporaryDirectory() as home:
        ns = dict(bin="/opt/r3hd", game="/data/content", home=home, profile="default", preset=None, settings=None,
                  set=[], key_layout=None, mods="on", license="full", no_keyboard=False, dev_overlay=False,
                  log_level="info", extra=[], dry_run=True, check=False)
        ns.update(dict(extra))
        return P.build_plan(P.argparse.Namespace(**ns), now=P.datetime.datetime(2026, 11, 7, 12, 0, 0))


def plan_home(home, *extra):
    ns = dict(bin=None, game=None, home=str(home), profile="default", preset=None, settings=None, set=[],
              key_layout=None, mods="on", license="full", no_keyboard=False, dev_overlay=False, log_level="info",
              extra=[], dry_run=True, check=False)
    ns.update(dict(extra))
    return P.build_plan(P.argparse.Namespace(**ns), now=P.datetime.datetime(2026, 11, 7, 12, 0, 0))


def installed_home(root, preset="hdplus"):
    """An installed (portable-prepared) home as the engine writes it: installer.json and a fresh settings.json."""
    home = Path(root)
    engine.write_json(home / "settings.json", engine.settings_from_args(preset, None, (), False, home, fresh=True))
    engine.write_json(home / engine.STATE, {"schema": 1, "distribution": "portable"})
    return home


class Mirror(unittest.TestCase):
    def test_setting_params(self):
        m = re.search(r"\$settingParams = \[ordered\]@\{(.*?)\}\n", PS1, re.S)
        pairs = re.findall(r"(\w+) = '(\w+)'", m.group(1))
        self.assertEqual(pairs, list(P.SETTING_PARAMS.items()))

    def test_env_pass_through(self):
        ps = dict(re.findall(r"^\$env:(R3HD_\w+) = (?:\[string\])?\$(\w+)\s*(?:#.*)?$", PS1, re.M))
        ps = {k: v for k, v in ps.items() if v in P.SETTING_PARAMS}
        self.assertEqual(ps, P.ENV_FROM_PARAM)

    def test_vblank_and_language(self):
        self.assertIn("$env:R3HD_VBLANK = $(if ($Pacing -eq 'precise') { 'deadline' } else { 'poll' })", PS1)
        m = re.search(r"\$gameLanguageId = @\{ (.*?) \}", PS1)
        self.assertEqual({k: int(v) for k, v in re.findall(r"(\w+) = (\d+)", m.group(1))}, P.GAME_LANGUAGE_ID)

    def test_xex_and_test_only(self):
        self.assertIn(f"$xexSha256 = '{P.XEX_SHA256}'", PS1)
        m = re.search(r"\$testOnly = (.*?)\n(?!\s+')", PS1, re.S)
        self.assertEqual(re.findall(r"'(R3HD_\w+)'", m.group(1)), list(P.TEST_ONLY))

    def test_fixed_arguments(self):
        for token in ("'--gpu_plugin=xenos'", "'--log_flush_interval=1'", "'--bind_settings=None'",
                      "'--bind_debug_overlay=None'", "'--log_max_files=2'", "'--mnk_mouse=true'",
                      "'--mnk_mouse_buttons=true'"):
            self.assertIn(token, PS1)


class Plans(unittest.TestCase):
    def test_vanilla_defaults_off(self):
        p = plan()
        self.assertEqual(p["env"]["R3HD_COMBO_CLOSE"], "original")
        self.assertEqual(p["env"]["R3HD_DS_LIGHT"], "off")
        self.assertIn("--resolution_scale=1", p["arguments"])
        self.assertIn("--user_language=1", p["arguments"])
        self.assertIn("--bind_settings=None", p["arguments"])
        self.assertEqual(p["env"]["R3HD_PLAY"], "1")

    def test_hdplus_switches_features_on(self):
        e = plan(("preset", "hdplus"))["env"]
        self.assertEqual((e["R3HD_COMBO_CLOSE"], e["R3HD_LAYER_COORDS"], e["R3HD_RED_CORRECTION"], e["R3HD_SKY_CLEAR"],
                          e["R3HD_LIT_UV_SCROLL"]), ("delayed", "separate", "bypass", "background", "applied"))
        self.assertEqual(e["R3HD_VBLANK"], "deadline")
        # Windows v1.2.0 / post-v1.3.1 HD+ corrections (D-218, D-219, D-221, D-363) reach the Linux launch as on Windows.
        self.assertEqual((e["R3HD_POWER_SWIRL"], e["R3HD_BEAM_COLOR"], e["R3HD_LOCKON_COLOR"], e["R3HD_CROWN_CUTOUT"]),
                         ("restored", "restored", "restored", "cutout"))
        v = plan(("preset", "vanilla"))["env"]
        self.assertEqual((v["R3HD_POWER_SWIRL"], v["R3HD_BEAM_COLOR"], v["R3HD_LOCKON_COLOR"], v["R3HD_CROWN_CUTOUT"]),
                         ("original", "original", "original", "original"))

    def test_hud_toggle_and_prompts_reach_the_launch(self):
        e = plan(("set", ["hud_toggle=f5", "controller_prompts=playstation"]))["env"]
        self.assertEqual((e["R3HD_HUD_TOGGLE"], e["R3HD_BUTTON_PROMPTS"]), ("f5", "playstation"))
        self.assertEqual(plan()["env"]["R3HD_HUD_TOGGLE"], "off")

    def test_vsync_selects_vulkan_fifo(self):
        """G6-P59 (D-310): On refuses the three tearing / frame-dropping Vulkan modes; Off passes nothing."""
        off = plan()
        self.assertFalse([a for a in off["arguments"] if a.startswith("--vulkan_allow_present_mode_")])
        self.assertTrue(off["vsync"].startswith("off"))
        self.assertEqual(off["env"]["R3HD_DISPLAY_VSYNC"], "off")
        on = plan(("set", ["display_vsync=on"]))
        self.assertEqual([a for a in on["arguments"] if a.startswith("--vulkan_allow_present_mode_")],
                         list(P.VSYNC_ON_ARGS))
        self.assertEqual(set(P.VSYNC_ON_ARGS), {"--vulkan_allow_present_mode_immediate=false",
                                                "--vulkan_allow_present_mode_mailbox=false",
                                                "--vulkan_allow_present_mode_fifo_relaxed=false"})
        self.assertTrue(on["vsync"].startswith("on"))
        self.assertNotIn("--vsync=false", on["arguments"])  # the guest-vblank cvar is never touched (E-265)
        with self.assertRaises(P.Refused):  # the setting owns these cvars
            plan(("set", ["display_vsync=on"]), ("extra", ["--vulkan_allow_present_mode_mailbox=true"]))

    def test_vsync_cvars_exist_in_the_pinned_presenter(self):
        """The three cvars and their FIFO fallback are the pinned SDK's (skipped without the SDK checkout)."""
        src = HERE.parents[1] / "external/rexglue-sdk/src/ui/vulkan/vulkan_presenter.cpp"
        if not src.is_file():
            self.skipTest("no SDK checkout")
        text = src.read_text(encoding="utf-8", errors="replace")
        for arg in P.VSYNC_ON_ARGS:
            self.assertIn(f"REXCVAR_DEFINE_BOOL({arg[2:].split('=')[0]}, true,", text)
        self.assertIn("swapchain_create_info.presentMode = VK_PRESENT_MODE_FIFO_KHR;", text)
        self.assertIn("is_vsync_implicit_out = paint_context_.swapchain_is_fifo;", text)

    def test_explicit_preferences(self):
        p = plan(("set", ["dualsense_light=on", "gameplay_subtitles=all", "window_size=1920x1080", "render_scale=auto",
                          "mouse_camera=on", "mouse_sensitivity=75"]))
        self.assertEqual((p["env"]["R3HD_DS_LIGHT"], p["env"]["R3HD_GAMEPLAY_SUBTITLES"]), ("on", "all"))
        self.assertIn("--window_width=1920", p["arguments"])
        self.assertIn("--resolution_scale=2", p["arguments"])
        self.assertIn("--mnk_sensitivity=2", p["arguments"])
        self.assertTrue(any(a.startswith("--keybind_") for a in p["arguments"]))
        self.assertIn("dualsense_light=on", p["env"]["R3HD_PCSET_SESSION"])

    def test_refusals(self):
        for extra in (["--license_mask=0"], ["--user_language=3"], ["nonsense"]):
            with self.assertRaises(P.Refused):
                plan(("extra", extra))


class Home(unittest.TestCase):
    """LX-4: the play.ps1 home layout (M28), F4 persistence condition (D-139), session limit (M31), desktop identity."""

    def test_layout_mirrors_play_ps1(self):
        self.assertIn("Resolve-R3hdPath $BinDir 'R3HD_BIN_DIR' 'bin'", PS1)
        self.assertIn("Resolve-R3hdPath $GameDir 'R3HD_GAME_DIR' 'data\\content'", PS1)
        with tempfile.TemporaryDirectory() as root:
            p = plan_home(Path(root).resolve())
            self.assertEqual(p["executable"], str(Path(root).resolve() / "bin" / "r3hd"))
            self.assertIn(f"--game_data_root={Path(root).resolve() / 'data' / 'content'}", p["arguments"])
            self.assertFalse(p["installed"])

    def test_pcset_persistence_mirrors_play_ps1(self):
        self.assertIn("if ($installed -and $homeSettings -and $SettingsFile -eq $homeSettings) {", PS1)
        self.assertEqual(set(re.findall(r"\$env:(R3HD_PCSET_\w+) = \$pcset", PS1)) - {"R3HD_PCSET_SETTINGS_APP"},
                         {"R3HD_PCSET_HOME", "R3HD_PCSET_PYTHON"})
        self.assertIn("$env:R3HD_PCSET_TOOLS = $PSScriptRoot", PS1)
        with tempfile.TemporaryDirectory() as root:
            home = installed_home(Path(root).resolve())
            e = plan_home(home)["env"]
            self.assertEqual(e["R3HD_PCSET_HOME"], str(home))
            self.assertTrue((Path(e["R3HD_PCSET_TOOLS"]) / "r3hd_installer.py").is_file())
            self.assertEqual(e["R3HD_PCSET_PYTHON"], sys.executable)
            self.assertNotIn("R3HD_PCSET_SETTINGS_APP", e)
            self.assertNotIn("R3HD_PCSET_HOME", plan_home(home, ("preset", "hdplus"))["env"])  # session-only
            (home / engine.STATE).unlink()
            self.assertNotIn("R3HD_PCSET_HOME", plan_home(home)["env"])  # not an installed home

    def test_fresh_install_defaults_reach_the_launch(self):
        # D-108 / D-090 / M31: a new installation's light bar, R2 resistance, HD+ subtitles and fullscreen.
        with tempfile.TemporaryDirectory() as root:
            p = plan_home(installed_home(Path(root).resolve()))
            e = p["env"]
            self.assertEqual((e["R3HD_DS_LIGHT"], e["R3HD_DS_TRIGGER"], e["R3HD_GAMEPLAY_SUBTITLES"]), ("on", "on", "all"))
            self.assertIn("--fullscreen=true", p["arguments"])

    def test_session_limit(self):
        self.assertIn(f"$sessionLimit = {P.SESSION_LIMIT}", PS1)
        with tempfile.TemporaryDirectory() as root:
            home = installed_home(Path(root).resolve())
            names = [f"202611{d:02d}-120000" for d in range(1, 13)]
            for n in names + ["keep-me", "20261101-12000"]:
                (home / "sessions" / n).mkdir(parents=True)
            self.assertEqual(plan_home(home)["prune_sessions"], names[:3])  # 12 - 9: the new one is the 10th

    def test_desktop_entry_and_identity(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (64).to_bytes(4, "big") * 2 + bytes(9)
        # r3hd_installer.play_icon_bytes: a one-image ICO whose entry is the package's PNG at offset 22.
        ico = (bytes([0, 0, 1, 0, 1, 0, 64, 64, 0, 0]) + (1).to_bytes(2, "little") + (32).to_bytes(2, "little")
               + len(png).to_bytes(4, "little") + (22).to_bytes(4, "little") + png)
        fallback = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (256).to_bytes(4, "big") * 2 + bytes(9)
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as xdg:
            home = Path(root).resolve() / "R3HD $home"  # a space and a $ must survive the Exec quoting
            (home / "data").mkdir(parents=True)
            (home / "app/icons").mkdir(parents=True)
            (home / "app/icons/rayman3hd-recompiled.png").write_bytes(fallback)
            (home / "app/icons/rayman3hd-recompiled-settings.png").write_bytes(fallback)
            self.assertEqual(plan_home(home)["env"]["SDL_APP_ID"], P.APP_ID)
            # E-379 (LX2D: generic Wayland icon): extracted data has no game icon -> the shipped neutral fallback,
            # never no icon at all
            r = P.desktop_entry(home, xdg, refresh=False)
            entry = (Path(xdg) / "applications" / f"{P.APP_ID}.desktop").read_text(encoding="utf-8")
            big = Path(xdg) / "icons/hicolor/256x256/apps" / f"{P.APP_ID}.png"
            self.assertEqual((r["icon"], big.read_bytes()), ("fallback", fallback))
            self.assertIn(f"Icon={big}\n", entry)
            self.assertIn(f"StartupWMClass={P.APP_ID}\n", entry)
            self.assertIn("Exec=" + P.desktop_escape(home / "Play.sh") + "\n", entry)
            self.assertIn("\\$home", P.desktop_escape(home / "Play.sh"))
            settings = (Path(xdg) / "applications" / f"{P.SETTINGS_ID}.desktop").read_text(encoding="utf-8")
            self.assertIn("Settings.sh", settings)
            # the game's own thumbnail (written by the engine from the person's package) replaces the fallback icon
            (home / "data" / "play_icon.ico").write_bytes(ico)
            r = P.desktop_entry(home, xdg, refresh=False)
            icon = Path(xdg) / "icons/hicolor/64x64/apps" / f"{P.APP_ID}.png"
            entry = (Path(xdg) / "applications" / f"{P.APP_ID}.desktop").read_text(encoding="utf-8")
            self.assertEqual((r["icon"], icon.read_bytes()), ("package", png))
            self.assertIn(f"Icon={icon}\n", entry)
            self.assertFalse(big.exists(), "the 256 px fallback must not shadow the game icon")
            # an existing entry of this home is kept current; another home's entry is never touched
            self.assertIsNotNone(P.update_desktop_entry_if_present(home, xdg))
            other = Path(root).resolve() / "other"
            other.mkdir()
            self.assertIsNone(P.update_desktop_entry_if_present(other, xdg))
            self.assertEqual(P.remove_desktop_entry(other, xdg, refresh=False)["removed"], [])
            r = P.remove_desktop_entry(home, xdg, refresh=False)
            self.assertEqual(len(r["removed"]), 4)
            self.assertFalse(list(Path(xdg).rglob("rayman3hd-recompiled*")))

    def test_game_icon_from_the_persons_package(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + (64).to_bytes(4, "big") * 2 + bytes(9)
        ico = (bytes([0, 0, 1, 0, 1, 0, 64, 64, 0, 0]) + (1).to_bytes(2, "little") + (32).to_bytes(2, "little")
               + len(png).to_bytes(4, "little") + (22).to_bytes(4, "little") + png)
        sys.path.insert(0, str(P.TOOLS))
        import r3hd_installer as engine
        with tempfile.TemporaryDirectory() as root:
            home = Path(root).resolve()
            (home / "data").mkdir()
            seen = []
            with mock.patch.object(engine, "play_icon_bytes", lambda pkg, cid: seen.append(cid) or ico):
                self.assertEqual(P.game_icon(home, home / "pkg.bin"), (png, "package"))
            self.assertEqual(seen, [engine.load_releases()[0]["package"]["content_id"]])  # identity checked
            self.assertEqual((home / "data" / "play_icon.ico").read_bytes(), ico)  # kept for the next start
            (home / "data" / "play_icon.ico").unlink()
            with mock.patch.object(engine, "play_icon_bytes", lambda pkg, cid: None):
                self.assertIsNone(P.game_icon(home, home / "other.bin")[0])


class FirstLaunch(unittest.TestCase):
    """E-377: LX2B first-launch findings: the fullscreen target and the preset choice."""
    TWO = ("Screen 0: minimum 16 x 16, current 4480 x 1440, maximum 32767 x 32767\n"
           "DP-1 connected primary 2560x1440+0+0 (normal left inverted right x axis y axis) 597mm x 336mm\n"
           "   2560x1440    143.97*+\n"
           "HDMI-A-1 connected 1920x1080+2560+0 (normal left inverted right x axis y axis) 527mm x 296mm\n"
           "   1920x1080     60.00*+\n")

    def test_primary_mode_not_the_combined_screen(self):
        self.assertIn("source = 'primary display mode'", PS1)  # play.ps1 takes the primary display mode
        self.assertEqual(P.primary_mode(self.TWO), (2560, 1440))
        self.assertEqual(P.render_scale("auto", P.primary_mode(self.TWO)), 2)  # 2560x1440 internal, not 3840x2160
        self.assertEqual(P.render_scale("auto", (4480, 1440)), 3)  # what the combined screen gave (LX2B)

    def test_primary_mode_without_a_primary_flag(self):
        xwayland = ("Screen 0: minimum 16 x 16, current 4480 x 1440, maximum 32767 x 32767\n"
                    "XWAYLAND1 connected 1920x1080+2560+0 (normal) 527mm x 296mm\n"
                    "XWAYLAND0 connected 2560x1440+0+0 (normal) 597mm x 336mm\n")
        self.assertEqual(P.primary_mode(xwayland), (2560, 1440))  # the output at +0+0
        self.assertEqual(P.primary_mode("HDMI-1 disconnected (normal)\nDP-2 connected 1920x1200+0+0 x\n"), (1920, 1200))
        self.assertIsNone(P.primary_mode("Screen 0: current 4480 x 1440\nDP-1 connected (normal)\n"))

    def test_first_run_preset_question(self):
        import r3hd_portable as portable
        lines = []
        answers = iter(["x", "2"])
        self.assertEqual(portable.ask_preset(lines.append, ask=lambda q: next(answers)), "hdplus")
        self.assertTrue(any("HD+ (Recommended)" in line for line in lines))  # the installer's label
        self.assertEqual(portable.ask_preset(lines.append, ask=lambda q: ""), "vanilla")  # installer preselection
        iss = (HERE.parent / "installer").glob("*.iss")
        self.assertTrue(any("PresetPage.SelectedValueIndex := 0;" in p.read_text(encoding="utf-8", errors="replace")
                            for p in iss))


if __name__ == "__main__":
    unittest.main(verbosity=1)
