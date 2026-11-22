"""G6-P55 (D-301 / D-303): the F5 score HUD toggle from Settings to the game's environment, on synthetic homes only.

  python tools/hud_toggle_settings_regression.py      prints HUD_TOGGLE_SETTINGS_REGRESSION PASS/FAIL

tools/hud_toggle_state_test.cpp covers the in-game F5 rules and m18_regression.py the guest gate; this covers the
path in between that an ordinary Windows player depends on: the Settings check box (G6-P49) stores hud_toggle as a
preference, a preset switch keeps it, the resolver play.ps1 runs (r3hd_settings.py resolve, as a subprocess with the
same arguments) turns it into the value play.ps1 assigns to $HudToggle, an explicit -HudToggle wins over the saved
choice, and play.ps1 hands exactly that value to the runtime as R3HD_HUD_TOGGLE and restores the caller's value
afterwards. The stored and resolved spelling must be the one value the runtime accepts ("f5", case-sensitive,
r3hd_hud_state.h); anything else would leave the toggle silently off. No game, window, build or PowerShell run.
"""
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import r3hd_installer as engine  # noqa: E402
import r3hd_settings as settings  # noqa: E402

KEY, PARAM, ENV = "hud_toggle", "HudToggle", "R3HD_HUD_TOGGLE"


def read(path):
    return Path(path).read_text(encoding="utf-8")


def home_at(root, preset="vanilla"):
    home = Path(root)
    engine.write_json(home / "settings.json", settings.make_settings(settings.load_registry(), preset))
    engine.write_json(home / engine.STATE, {"schema": 1, "distribution": "portable", "version": "synthetic",
                                          "files": {}, "data": {"release": "synthetic"}})
    return home


def saved(home):
    return json.loads((home / "settings.json").read_text(encoding="utf-8"))


def runtime_enabled_values():
    """The values r3hd_hud::EnabledValue accepts, read from the header (strcmp against literals)."""
    header = read(TOOLS / "m2_host/r3hd_hud_state.h")
    body = re.search(r"inline bool EnabledValue\(const char\* v\) \{(.*?)\}\n", header, re.S)
    return set(re.findall(r'!std::strcmp\(v, "([^"]*)"\)', body.group(1))) if body else set()


def resolve_cli(*args):
    """r3hd_settings.py resolve as play.ps1 runs it; returns what play.ps1 would assign to $HudToggle."""
    r = subprocess.run([sys.executable, "-B", str(TOOLS / "r3hd_settings.py"), "resolve", *args],
                       capture_output=True, text=True, cwd=ROOT)
    out = json.loads(r.stdout)
    return (out["values"][KEY] if r.returncode == 0 and out.get("result") == "resolved" else None), out


class Registry(unittest.TestCase):
    def test_off_everywhere_and_on_matches_runtime(self):
        reg = settings.load_registry()
        s = reg["settings"][KEY]
        self.assertEqual((s["scope"], s["launcher"], s["values"]), ("preference", PARAM, ["off", "f5"]))
        self.assertEqual((s["vanilla"], s["hdplus"]), ("off", "off"))
        self.assertNotIn("install_default", s)  # a new installation starts with the HUD as the title draws it
        for preset in ("vanilla", "hdplus", "custom"):
            self.assertEqual(settings.resolve(reg, preset=preset)["values"][KEY], "off")
        enabled = runtime_enabled_values()
        self.assertEqual(enabled, {"f5"})
        # Exactly one stored value turns the runtime toggle on; Off is never accepted by the runtime.
        self.assertEqual([v for v in s["values"] if v in enabled], ["f5"])


class Persistence(unittest.TestCase):
    def setUp(self):
        running = mock.patch.object(engine, "game_running", return_value=False)
        running.start()
        self.addCleanup(running.stop)

    def test_saved_choice_reaches_play_and_keeps_unrelated_data(self):
        with tempfile.TemporaryDirectory(prefix="g6p55_") as root:
            home = home_at(root, "hdplus")
            data = saved(home)
            data.setdefault("preferences", {})["display"] = "fullscreen"
            data["preferences"]["controller_prompts"] = "playstation"
            engine.write_json(home / "settings.json", data)
            for value in ("f5", "off", "f5"):
                before = saved(home)
                engine.set_preferences(home, [f"{KEY}={value}"], engine.settings_revision(home))
                after = saved(home)
                expected = copy.deepcopy(before)
                expected["preferences"][KEY] = value
                self.assertEqual(after, expected)
                got, out = resolve_cli("--settings", str(home / "settings.json"))
                self.assertEqual((got, out["values"]["display"], out["values"]["controller_prompts"]),
                                 (value, "fullscreen", "playstation"))
                self.assertEqual(got in runtime_enabled_values(), value == "f5")

    def test_preset_switches_keep_the_choice(self):
        with tempfile.TemporaryDirectory(prefix="g6p55_") as root:
            home = home_at(root)
            engine.set_preferences(home, [f"{KEY}=f5"])
            reg = settings.load_registry()
            for preset in ("hdplus", "custom", "vanilla", "hdplus"):
                engine.set_preset(home, preset)
                result = settings.resolve(reg, settings=saved(home))["values"]
                self.assertEqual(result[KEY], "f5", preset)
                reference = settings.resolve(reg, preset=preset)["values"]
                self.assertEqual({k: v for k, v in result.items() if k != KEY},
                                 {k: v for k, v in reference.items() if k != KEY}, preset)

    def test_explicit_parameter_wins_over_saved_choice(self):
        with tempfile.TemporaryDirectory(prefix="g6p55_") as root:
            home = home_at(root)
            f = str(home / "settings.json")
            engine.set_preferences(home, [f"{KEY}=f5"])
            self.assertEqual(resolve_cli("--settings", f, "--explicit", f"{KEY}=off")[0], "off")
            engine.set_preferences(home, [f"{KEY}=off"])
            self.assertEqual(resolve_cli("--settings", f, "--explicit", f"{KEY}=f5")[0], "f5")
            self.assertEqual(resolve_cli("--preset", "hdplus", "--explicit", f"{KEY}=f5")[0], "f5")
            self.assertEqual(resolve_cli("--preset", "hdplus")[0], "off")

    def test_other_spellings_refused_and_file_unchanged(self):
        with tempfile.TemporaryDirectory(prefix="g6p55_") as root:
            home = home_at(root)
            engine.set_preferences(home, [f"{KEY}=f5"])
            before = (home / "settings.json").read_bytes()
            for value in ("F5", "on", "1", ""):
                with self.assertRaises(engine.Refusal):
                    engine.set_preferences(home, [f"{KEY}={value}"])
                self.assertEqual((home / "settings.json").read_bytes(), before)
                self.assertIsNone(resolve_cli("--explicit", f"{KEY}={value}")[0])
            # A hand-edited settings file with another spelling is refused, never read as Off or On silently.
            data = saved(home)
            data["preferences"][KEY] = "F5"
            bad = Path(root) / "bad.json"
            engine.write_json(bad, data)
            self.assertIsNone(resolve_cli("--settings", str(bad))[0])


class PlayScript(unittest.TestCase):
    def test_resolved_value_is_the_runtime_environment(self):
        ps1 = read(TOOLS / "play.ps1")
        self.assertIn(f"[ValidateSet('off', 'f5')][string]${PARAM} = 'off',", ps1)
        self.assertIn(f"{PARAM} = '{KEY}';", ps1[ps1.index("$settingParams"):ps1.index("$resolverArgs")])
        setter, restore = f"$env:{ENV} = ${PARAM}", f"$env:{ENV} = $savedHudToggle"
        self.assertEqual((ps1.count(setter), ps1.count(restore), ps1.count(f"$savedHudToggle = $env:{ENV}")), (1, 1, 1))
        # Resolved before it is handed over; handed over before the game starts; the caller's value restored after.
        resolved = ps1.index("Set-Variable -Name $name -Value ([string]$resolved.values.($settingParams[$name]))")
        start = ps1.index(setter)
        self.assertLess(resolved, start)
        self.assertLess(ps1.index(f"$savedHudToggle = $env:{ENV}"), start)
        self.assertLess(start, ps1.index(restore))
        # Nothing between the resolver and the hand-over reassigns the parameter.
        between = ps1[resolved + 1:start]
        self.assertFalse(re.search(rf"\${PARAM}\s*=", between))
        # A value from the caller's environment never stays: the variable is always assigned, Off included.
        self.assertNotIn(f"if ($HudToggle", ps1)
        # Recorded with the session (launch.json and session.json).
        self.assertEqual(ps1.count(f"{KEY} = ${PARAM}"), 2)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    ok = result.wasSuccessful()
    print(f"HUD_TOGGLE_SETTINGS_REGRESSION {'PASS' if ok else 'FAIL'} {result.testsRun} tests "
          f"{len(result.skipped)} skipped")
    sys.exit(0 if ok else 1)
