"""Button prompt preference: synthetic homes and launch plans only; no game or device access."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

import r3hd_installer as engine
import r3hd_settings as settings
import r3hd_ui_locale as locale

sys.path.insert(0, str(Path(__file__).resolve().parent / "linux"))
import r3hd_play as play
import r3hd_settings_gui as gui

KEY = "controller_prompts"
VALUES = ("auto", "xbox", "playstation")


def temporary_home():
    work = Path(__file__).resolve().parents[1] / "private" / "work" / "button_prompt_settings_test"
    work.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=work)


def home_at(root, preset="vanilla"):
    home = Path(root)
    data = settings.make_settings(settings.load_registry(), preset)
    engine.write_json(home / "settings.json", data)
    engine.write_json(home / engine.STATE, {"schema": 1, "distribution": "portable", "version": "synthetic",
                                          "files": {}, "data": {"release": "synthetic"}})
    return home


def read(home):
    return json.loads((home / "settings.json").read_text(encoding="utf-8"))


class ButtonPromptSettings(unittest.TestCase):
    def setUp(self):
        running = mock.patch.object(engine, "game_running", return_value=False)
        running.start()
        self.addCleanup(running.stop)

    def test_saved_auto_is_preserved_not_coerced(self):
        reg = settings.load_registry()
        for section in ("preferences", "overrides"):
            data = {"schema": 2, "preset": "custom", "base": "hdplus", section:
                    {KEY: "auto", "display": "windowed"}}
            result = settings.resolve(reg, settings=data)
            self.assertEqual(result["values"][KEY], "auto")
            saved = settings.make_settings(reg, "vanilla", keep_preferences=settings.preferences_of(reg, data))
            self.assertEqual(settings.resolve(reg, settings=saved)["values"][KEY], "auto")
            self.assertEqual(settings.resolve(reg, settings=saved)["values"]["display"], "windowed")

    def test_defaults_and_preference_scope(self):
        reg = settings.load_registry()
        self.assertEqual(reg["settings"][KEY]["scope"], "preference")
        self.assertEqual(reg["settings"][KEY]["values"], list(VALUES))
        for preset in ("vanilla", "hdplus", "custom"):
            self.assertEqual(settings.resolve(reg, preset=preset)["values"][KEY], "auto")

    def test_f4_persistence_reopen_and_unrelated_data(self):
        with temporary_home() as root:
            home = home_at(root)
            data = read(home)
            data["schema"] = 4
            data["keyboard"] = {"layout": "original", "keys": {}}
            data["controller"] = settings.controller_section(settings.load_padmap(), {"a": "b", "b": "a"})
            engine.write_json(home / "settings.json", data)
            for value in VALUES:
                before = read(home)
                engine.set_preferences(home, [f"{KEY}={value}"], engine.settings_revision(home))
                after = read(home)
                expected = copy.deepcopy(before)
                expected["preferences"][KEY] = value
                self.assertEqual(after, expected)
                reopened = gui.Model(home)
                self.assertEqual(reopened.chosen[KEY], value)
                self.assertEqual(reopened.tab(reopened.by_key[KEY]), "controller")

    def test_preset_switches_keep_artwork_preference(self):
        with temporary_home() as root:
            home = home_at(root)
            engine.set_preferences(home, [f"{KEY}=playstation"])
            for preset in ("hdplus", "custom", "vanilla"):
                engine.set_preset(home, preset)
                result = settings.resolve(settings.load_registry(), settings=read(home))
                self.assertEqual(result["values"][KEY], "playstation")
                reference = settings.resolve(settings.load_registry(), preset=preset)
                self.assertEqual({k: v for k, v in result["values"].items() if k != KEY},
                                 {k: v for k, v in reference["values"].items() if k != KEY})

    def test_invalid_and_stale_writes_preserve_file(self):
        with temporary_home() as root:
            home = home_at(root)
            revision = engine.settings_revision(home)
            engine.set_preferences(home, [f"{KEY}=xbox"], revision)
            before = (home / "settings.json").read_bytes()
            for value, rev in (("invalid", None), ("playstation", revision)):
                with self.assertRaises(engine.Refusal):
                    engine.set_preferences(home, [f"{KEY}={value}"], rev)
                self.assertEqual((home / "settings.json").read_bytes(), before)

    def test_model_and_bilingual_labels(self):
        option = next(o for o in engine.describe_options() if o["key"] == KEY)
        self.assertEqual(option["value_labels"], dict(zip(VALUES, ("Auto", "Xbox", "PlayStation"))))
        self.assertIn("at launch", option["help"])
        catalog = locale.load()
        for label in (option["label"], option["help"], *option["value_labels"].values()):
            self.assertEqual(set(catalog[label]), {"en", "tr"})
            self.assertTrue(catalog[label]["tr"])

    def test_launch_plans_and_session_snapshot(self):
        with temporary_home() as root:
            home = home_at(root)
            for value in VALUES:
                engine.set_preferences(home, [f"{KEY}={value}"])
                args = play.argparse.Namespace(bin="/synthetic/bin", game="/synthetic/content", home=str(home),
                    profile="default", preset=None, settings=None, set=[], key_layout=None, mods="off",
                    license="full", no_keyboard=False, dev_overlay=False, log_level="info", extra=[],
                    dry_run=True, check=False)
                with mock.patch.object(play, "prepare_button_prompt_plan") as generate:
                    plan = play.build_plan(args)
                    generate.assert_not_called()  # dry plans never generate artwork
                self.assertEqual(plan["env"]["R3HD_BUTTON_PROMPTS"], value)
                self.assertIn(f"{KEY}={value}", plan["env"]["R3HD_PCSET_SESSION"])
                self.assertEqual(plan["env"]["R3HD_PAD_MAP"], "")

    def test_artwork_generation_only_at_launch_and_fallback(self):
        plan = {"arguments": ["--game_data_root=/synthetic/content", "--cache_root=/synthetic/cache"],
                "env": {"R3HD_BUTTON_PROMPTS": "playstation", "R3HD_MODS_PLAN": "/synthetic/mod.plan"}}
        run = mock.Mock(return_value=SimpleNamespace(returncode=0,
                        stdout=json.dumps({"result": "ok", "plan": "/synthetic/prompts.plan"})))
        play.prepare_button_prompt_plan(plan, run)
        self.assertEqual(plan["env"]["R3HD_BUTTON_PROMPTS_PLAN"], "/synthetic/prompts.plan")
        self.assertEqual(run.call_args.args[0][-2:], ["--mods-plan", "/synthetic/mod.plan"])
        plan["env"]["R3HD_BUTTON_PROMPTS"] = "auto"
        run.reset_mock()
        play.prepare_button_prompt_plan(plan, run)
        self.assertEqual(plan["env"]["R3HD_BUTTON_PROMPTS_PLAN"], "/synthetic/prompts.plan")
        run.assert_called_once()
        plan["env"]["R3HD_BUTTON_PROMPTS"] = "xbox"
        run.reset_mock()
        play.prepare_button_prompt_plan(plan, run)
        run.assert_not_called()
        self.assertEqual(plan["env"]["R3HD_BUTTON_PROMPTS_PLAN"], "")
        plan["env"]["R3HD_BUTTON_PROMPTS"] = "playstation"
        run.return_value = SimpleNamespace(returncode=2, stdout='{"result":"refused","reason":"mod overlap"}')
        with mock.patch.object(sys, "stderr"):
            play.prepare_button_prompt_plan(plan, run)
        self.assertEqual(plan["env"]["R3HD_BUTTON_PROMPTS_PLAN"], "")
        self.assertIn("mod overlap", plan["notes"][-1])


if __name__ == "__main__":
    unittest.main()
