"""D-220 display V-Sync: static and settings regression. Synthetic homes and launch plans only; no game, window,
device or display access.

  python tools/r3hd_display_vsync_regression.py      prints R3HD_DISPLAY_VSYNC_REGRESSION PASS/FAIL

Checks the registry preference (Display group, Off default in every preset, launch-time), its EN/TR catalog
entries, revision-checked persistence and preservation of unrelated data, preset switches, the Windows and Linux
launch plans, the in-game panel's restart-required treatment, the patch-chain position and (once the chain has
been replayed) the patched D3D12 presenter text. The SDK's guest-vblank `vsync` cvar must never be the setting.
"""
import copy
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "linux"))

import r3hd_installer as engine  # noqa: E402
import r3hd_settings as settings  # noqa: E402
import r3hd_ui_locale as locale  # noqa: E402
import r3hd_play as play  # noqa: E402
import r3hd_settings_gui as gui  # noqa: E402

KEY = "display_vsync"
VALUES = ("off", "on")
SDK = ROOT / "external/rexglue-sdk"
PRESENTER = SDK / "src/ui/d3d12/d3d12_presenter.cpp"


def read(path):
    return Path(path).read_text(encoding="utf-8")


def temporary_home():
    work = ROOT / "private" / "work" / "display_vsync" / "settings_test"
    work.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=work)


def home_at(root, preset="vanilla"):
    home = Path(root)
    engine.write_json(home / "settings.json", settings.make_settings(settings.load_registry(), preset))
    engine.write_json(home / engine.STATE, {"schema": 1, "distribution": "portable", "version": "synthetic",
                                          "files": {}, "data": {"release": "synthetic"}})
    return home


def saved(home):
    return json.loads((home / "settings.json").read_text(encoding="utf-8"))


class Registry(unittest.TestCase):
    def test_preference_shape_and_off_default(self):
        reg = settings.load_registry()
        s = reg["settings"][KEY]
        self.assertEqual((s["group"], s["scope"], s["category"]), ("display", "preference", "platform"))
        self.assertEqual(s["values"], list(VALUES))
        self.assertEqual((s["vanilla"], s["hdplus"]), ("off", "off"))
        self.assertNotIn("install_default", s)  # a new installation also starts with the pinned presentation
        self.assertEqual(s["launcher"], "VSync")
        self.assertIn("D-220", s["decision"])
        for preset in ("vanilla", "hdplus", "custom"):
            self.assertEqual(settings.resolve(reg, preset=preset)["values"][KEY], "off")
        # The SDK cvar `vsync` schedules the guest's vblank (E-265); it must never be a registry setting.
        self.assertNotIn("vsync", reg["settings"])

    def test_bilingual_catalog(self):
        option = next(o for o in engine.describe_options() if o["key"] == KEY)
        self.assertEqual(option["value_labels"], {"off": "Off", "on": "On"})
        self.assertIn("tearing", option["help"])
        self.assertIn("Windows only", option["help"])
        self.assertIn("override", option["help"])
        catalog = locale.load()
        for text in (option["label"], option["help"], *option["value_labels"].values()):
            self.assertEqual(set(catalog[text]), {"en", "tr"}, text)
            self.assertTrue(catalog[text]["tr"].strip(), text)
        self.assertIn(option["label"], locale.model_keys())


class Persistence(unittest.TestCase):
    def setUp(self):
        running = mock.patch.object(engine, "game_running", return_value=False)
        running.start()
        self.addCleanup(running.stop)

    def test_set_reopen_and_unrelated_data(self):
        with temporary_home() as root:
            home = home_at(root, "hdplus")
            data = saved(home)
            data["schema"] = 4
            data["keyboard"] = {"layout": "original", "keys": {}}
            data["controller"] = settings.controller_section(settings.load_padmap(), {"a": "b", "b": "a"})
            data.setdefault("preferences", {})["display"] = "windowed"
            data["preferences"]["render_scale"] = "2"
            engine.write_json(home / "settings.json", data)
            for value in ("on", "off", "on"):
                before = saved(home)
                engine.set_preferences(home, [f"{KEY}={value}"], engine.settings_revision(home))
                after = saved(home)
                expected = copy.deepcopy(before)
                expected["preferences"][KEY] = value
                self.assertEqual(after, expected)
                resolved = settings.resolve(settings.load_registry(), settings=after)["values"]
                self.assertEqual((resolved[KEY], resolved["display"], resolved["render_scale"]), (value, "windowed", "2"))
                reopened = gui.Model(home)
                self.assertEqual(reopened.chosen[KEY], value)
                self.assertEqual(reopened.tab(reopened.by_key[KEY]), "display")

    def test_preset_switches_keep_preference(self):
        with temporary_home() as root:
            home = home_at(root)
            engine.set_preferences(home, [f"{KEY}=on"])
            for preset in ("hdplus", "custom", "vanilla"):
                engine.set_preset(home, preset)
                result = settings.resolve(settings.load_registry(), settings=saved(home))
                self.assertEqual(result["values"][KEY], "on")
                reference = settings.resolve(settings.load_registry(), preset=preset)
                self.assertEqual({k: v for k, v in result["values"].items() if k != KEY},
                                 {k: v for k, v in reference["values"].items() if k != KEY})

    def test_invalid_and_stale_writes_preserve_file(self):
        with temporary_home() as root:
            home = home_at(root)
            revision = engine.settings_revision(home)
            engine.set_preferences(home, [f"{KEY}=on"], revision)
            before = (home / "settings.json").read_bytes()
            for value, rev in (("adaptive", None), ("1", None), ("off", revision)):
                with self.assertRaises(engine.Refusal):
                    engine.set_preferences(home, [f"{KEY}={value}"], rev)
                self.assertEqual((home / "settings.json").read_bytes(), before)

    def test_linux_launch_plan(self):
        with temporary_home() as root:
            home = home_at(root)
            for value in VALUES:
                engine.set_preferences(home, [f"{KEY}={value}"])
                args = play.argparse.Namespace(bin="/synthetic/bin", game="/synthetic/content", home=str(home),
                    profile="default", preset=None, settings=None, set=[], key_layout=None, mods="off",
                    license="full", no_keyboard=False, dev_overlay=False, log_level="info", extra=[],
                    dry_run=True, check=False)
                with mock.patch.object(play, "prepare_button_prompt_plan"):
                    plan = play.build_plan(args)
                self.assertEqual(plan["env"]["R3HD_DISPLAY_VSYNC"], value)
                self.assertIn(f"{KEY}={value}", plan["env"]["R3HD_PCSET_SESSION"])
                self.assertFalse(any(a.startswith("--vsync") for a in plan["arguments"]))


LABELS = {"en": "V-Sync", "tr": "V-Sync (Dikey Eşitleme)"}
HELP_TR = ("Ekran yırtılmasını önler ancak giriş gecikmesini biraz artırabilir. Ekran kartı sürücüsü ayarları "
           "bu seçeneği geçersiz kılabilir. Yalnızca Windows'ta kullanılabilir.")


class Localization(unittest.TestCase):
    def test_approved_turkish_wording(self):
        catalog = locale.load()
        reg = settings.load_registry()["settings"][KEY]
        self.assertEqual(catalog[reg["label"]]["tr"], LABELS["tr"])
        self.assertEqual(catalog[reg["help"]]["tr"], HELP_TR)
        self.assertEqual([catalog[reg["value_labels"][v]]["tr"] for v in VALUES], ["Kapalı", "Açık"])
        self.assertIn("Windows only", reg["help"])
        self.assertIn("Windows", reg["why"])


@unittest.skipUnless(sys.platform == "win32", "Windows Settings app")
class SettingsAppUi(unittest.TestCase):
    """The real Settings app (test-only UI script on its private desktop; synthetic home, dry nothing played)."""

    @classmethod
    def setUpClass(cls):
        import m30_launcher_regression as launcher
        cls.launcher = launcher
        if not launcher.LAUNCHER.is_file():
            raise unittest.SkipTest("launcher not built (tools/launcher/build_launcher.bat)")
        cls.saved_env = {k: os.environ.get(k) for k in ("R3HD_INSTALL_SYSTEM32", "R3HD_INSTALL_FAKE_RUNNING",
                                                        "R3HD_INSTALL_FAKE_LAUNCHER")}
        cls.tmp = temporary_home()
        cls.root = Path(cls.tmp.name)
        sys32 = cls.root / "sys32"
        sys32.mkdir()
        for name in engine.VC_RUNTIME:
            (sys32 / name).write_bytes(b"synthetic-runtime-presence")
        os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING="0",
                          R3HD_INSTALL_FAKE_LAUNCHER="0")

    @classmethod
    def tearDownClass(cls):
        for k, v in cls.saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        cls.tmp.cleanup()

    def test_label_save_and_fit_en_tr(self):
        L = self.launcher
        for language in ("en", "tr"):
            lt = self.root / language
            lt.mkdir()
            home = L.make_home(lt, "home")
            engine.set_option(home, "ui_language", language)
            before = L.settings(home)
            code, dumps, log, _ = L.ui(home, lt, "vsync",
                f"page settings\nset {KEY} on\nclick save\nreload\ndump saved\ndpi 144\ndump d144\nclick close\n")
            d, d144 = dumps.get("saved", {}), dumps.get("d144", {})
            self.assertEqual(code, 0, log[-400:])
            self.assertEqual(d.get(f"setting.{KEY}"), "on enabled=1", language)
            self.assertIn(LABELS[language], d.values(), f"{language}: localized check box label shown")
            after = L.settings(home)
            self.assertEqual(after["preferences"][KEY], "on")
            self.assertEqual({k: v for k, v in after["preferences"].items() if k != KEY},
                             {k: v for k, v in before.get("preferences", {}).items() if k != KEY})
            for name, dump in (("96 DPI", d), ("144 DPI", d144)):
                self.assertTrue(L.layout_ok(dump), f"{language} {name}: {dump.get('controls')}")
            height = int(d144["client"].split("x")[1].split()[0])
            self.assertLessEqual(height, 1020, f"{language}: Settings page at 144 DPI ({d144['client']})")


class Static(unittest.TestCase):
    def test_play_ps1(self):
        ps1 = read(TOOLS / "play.ps1")
        self.assertIn("[ValidateSet('off', 'on')][string]$VSync = 'off',", ps1)
        self.assertIn("VSync = 'display_vsync';", ps1)
        self.assertEqual(ps1.count("$env:R3HD_DISPLAY_VSYNC = $VSync"), 1)
        self.assertEqual(ps1.count("$env:R3HD_DISPLAY_VSYNC = $savedDisplayVSync"), 1)  # restored after the run
        self.assertLess(ps1.index("$env:R3HD_DISPLAY_VSYNC = $VSync"), ps1.index("$env:R3HD_DISPLAY_VSYNC = $savedDisplayVSync"))
        # The preference never reaches the SDK guest-vblank cvar `vsync`: $VSync is used only in these places.
        uses = [ln.strip() for ln in ps1.splitlines() if "$VSync" in ln]
        self.assertEqual(uses, [
            "[ValidateSet('off', 'on')][string]$VSync = 'off',",
            'Write-Host "v-sync     : $VSync"',
            next(u for u in uses if u.startswith("[ordered]@{ session = $stamp;")),
            "$env:R3HD_DISPLAY_VSYNC = $VSync",
            "display_vsync = $VSync",
            "display_vsync = $VSync",  # D-322 (G6-P73): the launcher-only session.json of a refused start
        ])
        self.assertFalse(any("--vsync" in u for u in uses))

    def test_panel_is_restart_required(self):
        panel = read(TOOLS / "m2_host/r3hd_pc_settings.h")
        live = re.search(r"inline bool IsLive\(const std::string& key\) \{\n(.*?)\n\}", panel, re.S).group(1)
        self.assertNotIn(KEY, live)  # shown as "Applies the next time the game starts."
        self.assertIn('T("Applies the next time the game starts.")', panel)

    def test_patch_chain(self):
        bat = read(TOOLS / "build_milestone8.bat")
        chain = [ln.strip() for ln in bat.splitlines() if ln.strip().startswith("python tools\\") and "_patch.py" in ln]
        # D-221: the lock-on colour read overlay (host file read path, no presenter anchor) follows it;
        # D-324: the controller-motor stop (input / SDL driver files and ReXApp::OnClosing only) follows;
        # D-328: the test-only profile handoff prototype (XAM user / input / UI files only) follows;
        # D-345: the SDL_DefaultAudioDeviceChanged prev-pointer fix (thirdparty/sdl3/src/audio/SDL_audio.c only) follows;
        # D-346: the AudioSystem client-lifetime fix (audio_system.h/cpp only) follows;
        # D-362: the Grand Minimus crown blend_byte overlay (host_path_file.cpp and one D3D12 mode line) follows;
        # D-370: native 3:2 (1.5x) D3D12 renderer (g6p89_scale32_patch.py) is last.
        self.assertEqual(chain[-8:], ["python tools\\r3hd_display_vsync_patch.py || exit /b 1",
                                      "python tools\\r3hd_lockon_runtime_patch.py || exit /b 1",
                                      "python tools\\r3hd_pad_motors_patch.py || exit /b 1",
                                      "python tools\\g6p79_profile_handoff_patch.py || exit /b 1",
                                      "python tools\\g6p106_sdl_audio_migration_patch.py || exit /b 1",
                                      "python tools\\g6p109_audio_client_lifetime_patch.py || exit /b 1",
                                      "python tools\\g6p127_crown_blend_patch.py || exit /b 1",
                                      "python tools\\g6p89_scale32_patch.py || exit /b 1"])
        self.assertLess(bat.index("r3hd_display_vsync_patch.py"), bat.index("cmake -S external"))
        self.assertIn("call tools\\build_display_vsync_test.bat || exit /b 1\n"
                      "call tools\\build_lockon_test.bat || exit /b 1\n"
                      "call tools\\build_pad_motors_test.bat || exit /b 1\n"
                      "python tools\\g6p79_handoff_regression.py || exit /b 1\n"
                      "python tools\\g6p82_signin_notify_regression.py || exit /b 1\n"
                      "python tools\\g6p106_sdl_audio_migration_regression.py || exit /b 1\n"
                      "python tools\\g6p108_audio_client_lifetime_regression.py || exit /b 1\n"
                      "python tools\\g6p127_crown_blend_regression.py || exit /b 1\n"
                      "python tools\\g6p89_scale32_regression.py || exit /b 1\npython tools\\g6p141_scale32_acceptance.py || exit /b 1\necho M8_BUILD_OK",  # D-370, D-371
                      bat.replace("\r\n", "\n"))

    def test_header_has_no_dxgi_dependency(self):
        header = read(TOOLS / "r3hd_display_vsync.h")
        self.assertNotIn("#include <dxgi", header)
        self.assertIn('std::getenv("R3HD_DISPLAY_VSYNC")', header)

    @unittest.skipUnless(PRESENTER.exists() and "r3hdvsync::" in (PRESENTER.read_text(encoding="utf-8") if PRESENTER.exists() else ""),
                         "patch chain not replayed in this tree")
    def test_patched_presenter(self):
        cpp = read(PRESENTER)
        self.assertEqual(cpp.count("->Present("), 1)
        self.assertIn("paint_context_.swap_chain->Present(UINT(r3hd_args.sync_interval), UINT(r3hd_args.flags));", cpp)
        self.assertNotIn("0, DXGI_PRESENT_RESTART |", cpp)  # the literal pinned call now comes from Choose()
        self.assertEqual(cpp.count("is_vsync_implicit_out = r3hdvsync::Enabled();  // D-220"), 2)
        self.assertNotIn("is_vsync_implicit_out = false;", cpp)
        self.assertEqual(cpp.count("ResizeBuffers("), 1)
        self.assertIn("r3hdvsync::SwapChainFlags(paint_context_.r3hd_latency_flag,", cpp)
        self.assertIn("CloseHandle(r3hd_latency_waitable);", cpp)
        # The wait is the first statement of the paint, before any back buffer is acquired.
        body = cpp[cpp.index("D3D12Presenter::PaintAndPresentImpl(bool execute_ui_drawers) {"):]
        self.assertLess(body.index("WaitForSingleObjectEx("), body.index("GetCurrentBackBufferIndex()"))
        self.assertLess(body.index("GetCurrentBackBufferIndex()"), body.index("->Present("))
        header = read(SDK / "include/rex/ui/d3d12/d3d12_presenter.h")
        self.assertIn("HANDLE r3hd_latency_waitable = nullptr;", header)
        # Only the D3D12 presenter changes; the generic presenter and Vulkan keep their own policy.
        self.assertNotIn("r3hdvsync", read(SDK / "src/ui/presenter.cpp"))
        self.assertNotIn("r3hdvsync", read(SDK / "src/ui/vulkan/vulkan_presenter.cpp"))


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    ok = result.wasSuccessful()
    print(f"R3HD_DISPLAY_VSYNC_REGRESSION {'PASS' if ok else 'FAIL'} {result.testsRun} tests "
          f"{len(result.skipped)} skipped")
    sys.exit(0 if ok else 1)
