#!/usr/bin/env python3
"""Focused Settings language tests: synthetic, tiny homes; no GUI or game execution."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import r3hd_installer as installer
import r3hd_settings as settings


class SettingsLanguageTests(unittest.TestCase):
    def setUp(self):
        work = Path(__file__).resolve().parents[1] / "private" / "work" / "settings_language"
        work.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="synthetic_", dir=work)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.payload, self.source, self.releases = installer.make_fixture(self.root)
        self.system = self.root / "system32"
        self.system.mkdir()
        for name in installer.VC_RUNTIME:
            (self.system / name).write_bytes(b"synthetic")
        self.env = patch.dict(os.environ, {
            "R3HD_INSTALL_FAKE_RUNNING": "0", "R3HD_INSTALL_FAKE_LAUNCHER": "0",
            "R3HD_INSTALL_SYSTEM32": str(self.system)}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    def install(self, home, language, preset="hdplus"):
        return installer.install(home, self.payload, self.source, preset, releases=self.releases,
                                 log=lambda *_: None, ui_language=language)

    def test_fresh_setup_languages_and_subtitle_defaults(self):
        for language in ("en", "tr"):
            for preset in ("hdplus", "vanilla"):
                home = self.root / f"{language}_{preset}"
                self.install(home, language, preset)
                data = installer.read_json(home / "settings.json")
                self.assertEqual(data["preferences"]["ui_language"], language)
                values = installer.settings_state(home)["values"]
                self.assertEqual(values["gameplay_subtitles"], "all" if preset == "hdplus" else "original")

    def test_upgrade_repair_and_profile_changes_preserve_language(self):
        home = self.root / "home"
        self.install(home, "tr")
        installer.set_option(home, "ui_language", "en")
        installer.set_preset(home, "vanilla")
        before = (home / "settings.json").read_bytes()
        self.install(home, "tr", None)
        self.assertEqual((home / "settings.json").read_bytes(), before)
        installer.repair(home, self.payload, releases=self.releases, log=lambda *_: None)
        self.assertEqual((home / "settings.json").read_bytes(), before)
        self.install(home, "tr", "hdplus")
        self.assertEqual(installer.read_json(home / "settings.json")["preferences"]["ui_language"], "en")

    def test_legacy_without_preference_defaults_english_on_upgrade(self):
        home = self.root / "legacy"
        self.install(home, None)
        before = (home / "settings.json").read_bytes()
        self.install(home, "tr", None)
        self.assertEqual((home / "settings.json").read_bytes(), before)
        self.assertEqual(installer.settings_state(home)["values"]["ui_language"], "en")

    def test_language_only_changes_language_and_preserves_user_files(self):
        home = self.root / "independent"
        self.install(home, None)
        installer.set_preset(home, "hdplus", pairs=["display=windowed", "window_size=1920x1080"],
                             keyboard=("original_pc", {}))
        for relative in ("profiles/default/user/save.dat", "mods/state.json", "mods/example/mod.json"):
            path = home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic user bytes")
        before_files = {str(path.relative_to(home)): path.read_bytes()
                        for folder in ("profiles", "mods") for path in (home / folder).rglob("*") if path.is_file()}
        before = installer.read_json(home / "settings.json")
        for language in ("tr", "en"):
            installer.set_option(home, "ui_language", language)
            after = installer.read_json(home / "settings.json")
            self.assertEqual(after["preferences"].pop("ui_language"), language)
            self.assertEqual(after, before)
        self.assertEqual(before_files, {str(path.relative_to(home)): path.read_bytes()
                         for folder in ("profiles", "mods") for path in (home / folder).rglob("*") if path.is_file()})

    def test_explicit_default_is_saved_without_switching_profile(self):
        home = self.root / "explicit"
        self.install(home, None)
        self.assertTrue(installer.set_option(home, "ui_language", "en")["changed"])
        self.assertFalse(installer.set_option(home, "ui_language", "en")["changed"])
        data = installer.read_json(home / "settings.json")
        self.assertEqual(data["preset"], "hdplus")
        self.assertEqual(data["preferences"]["ui_language"], "en")

    def test_registry_preference_is_neutral_and_hidden(self):
        entry = settings.load_registry()["settings"]["ui_language"]
        self.assertEqual((entry["vanilla"], entry["hdplus"]), ("en", "en"))
        self.assertEqual((entry["scope"], entry["ui"]), ("preference", "hidden"))
        self.assertNotIn("launcher", entry)

    def test_schema_one_keeps_existing_fields_and_resolved_preferences(self):
        home = self.root / "schema_one"
        self.install(home, None)
        legacy = {"schema": 1, "preset": "custom", "base": "hdplus",
                  "overrides": {"display": "fullscreen", "gameplay_subtitles": "all",
                                "layer_coords": "original"},
                  "allow_experimental": True, "comment": "retained user note"}
        installer.write_json(home / "settings.json", legacy)
        before_values = installer.settings_state(home)["values"]
        installer.set_option(home, "ui_language", "tr")
        after = installer.read_json(home / "settings.json")
        self.assertEqual(after.pop("preferences"), {"ui_language": "tr"})
        self.assertEqual(after.pop("schema"), 2)
        self.assertEqual(after, {key: value for key, value in legacy.items() if key != "schema"})
        after_values = installer.settings_state(home)["values"]
        self.assertEqual(after_values.pop("ui_language"), "tr")
        before_values.pop("ui_language")
        self.assertEqual(after_values, before_values)

    def test_invalid_saved_keyboard_is_preserved_on_language_change(self):
        home = self.root / "invalid_keyboard"
        self.install(home, None)
        before = installer.read_json(home / "settings.json")
        before["keyboard"] = {"layout": "missing-layout", "keys": {"a": ["unknown-key"]}}
        before["comment"] = "saved preferences must survive locale changes"
        installer.write_json(home / "settings.json", before)
        for language in ("tr", "en"):
            installer.set_option(home, "ui_language", language)
            after = installer.read_json(home / "settings.json")
            self.assertEqual(after["preferences"].pop("ui_language"), language)
            self.assertEqual(after, before)
            self.assertEqual(installer.read_state(home)["settings"]["keyboard"], before["keyboard"])

    def test_damaged_settings_refusal_keeps_file_and_install_record(self):
        home = self.root / "damaged_settings"
        self.install(home, None)
        for damaged in (b"{not valid JSON", b'{"schema":3,"preset":"hdplus","preferences":[]}'):
            (home / "settings.json").write_bytes(damaged)
            before_state = (home / installer.STATE).read_bytes()
            with self.assertRaises(installer.Refusal) as raised:
                installer.set_option(home, "ui_language", "tr")
            self.assertEqual(raised.exception.code, "SETTINGS_REFUSED")
            self.assertEqual((home / "settings.json").read_bytes(), damaged)
            self.assertEqual((home / installer.STATE).read_bytes(), before_state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
