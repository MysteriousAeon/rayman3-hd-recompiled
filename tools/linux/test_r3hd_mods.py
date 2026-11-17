#!/usr/bin/env python3
"""Host-only Linux Mods parity: real GUI adapter -> shared CLI -> launch -> optional C++ read overlay.

No game process. Synthetic fixtures by default. --turkish ZIP --game-dir CONTENT additionally tests the unchanged
authorized local Turkish archive on private copies of fix.* and VS.sub. --probe EXE consumes the actual plans.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import r3hd_settings_gui as G
import r3hd_mods as M
from test_r3hd_settings_gui import fresh, _tk_usable
from test_r3hd_play import plan_home

OPTIONS = argparse.Namespace(turkish=None, game_dir=None, probe=None)


class ModsParity(unittest.TestCase):
    def setUp(self):
        # Authorized game/translation copies must stay private, including on WSL. Synthetic cases may use /tmp
        # so their case-sensitivity checks exercise the Linux filesystem rather than a Windows-mounted tree.
        base = None
        if OPTIONS.turkish and self._testMethodName == "test_released_turkish_zip_unchanged":
            base = HERE.parents[1] / "private/work/linux_mod_parity"
            base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="r3hd-mods-", dir=base)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        home = self.root / "Home İ with spaces"
        home.mkdir()
        self.home = fresh(home, "hdplus")
        state = json.loads((self.home / "installer.json").read_text())
        state["version"] = "1.1.0"
        (self.home / "installer.json").write_text(json.dumps(state))
        self.service = G.Mods(self.home)
        self.game = self.home / "data/content/GAMEDATAbin"
        self.game.mkdir(parents=True)
        self.fix = bytearray(128)
        self.fix[64:80] = b"Original text\0\0\0"
        (self.game / "fix.lvl").write_bytes(self.fix)
        self.source = self.root / "source.zip"
        self.manifest = {"format": 1, "id": "test.turkish", "name": "Türkçe fixture", "version": "1.0.0",
                         "target": {"title_id": M.TITLE_ID, "releases": M.release_ids({"home": self.home}),
                                    "min_port_version": "0.33.0"},
                         "overrides": [{"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": 64,
                                        "slot_sha256": M.sha256_bytes(M.text_slot(self.fix, 64)),
                                        "text": "Seçenekler"}]}
        self.write_zip()

    def write_zip(self):
        with zipfile.ZipFile(self.source, "w") as z:
            z.writestr("mod.json", json.dumps(self.manifest, ensure_ascii=False).encode())

    def probe(self, plan):
        if OPTIONS.probe:
            subprocess.run([str(OPTIONS.probe.resolve()), plan], check=True)

    def test_lifecycle_persistence_and_launch(self):
        settings = (self.home / "settings.json").read_bytes()
        with mock.patch.dict(os.environ, {"R3HD_GAME_DIR": str(self.root / "wrong")}):
            self.assertFalse(self.service.call("import", self.source)["enabled"])
        self.assertEqual(self.service.call("list")["mods"][0]["state"], "disabled")
        self.assertEqual(plan_home(self.home)["env"]["R3HD_MODS_PLAN"], "")
        with self.assertRaisesRegex(RuntimeError, "EXISTS"):
            self.service.call("import", self.source)
        self.service.call("enable", "test.turkish")
        launch = plan_home(self.home)
        plan = launch["env"]["R3HD_MODS_PLAN"]
        self.assertTrue(Path(plan).is_file())
        self.probe(plan)
        records = Path(plan).read_text(encoding="utf-8").splitlines()
        blob = next(r.split(" ", 7)[7] for r in records if r.startswith("range "))
        self.assertTrue(Path(blob).read_bytes().startswith("Seçenekler".encode("cp1252")))
        self.assertEqual((self.home / "settings.json").read_bytes(), settings)
        model = G.Model(self.home)
        model.set_value("mouse_camera", "on")
        self.assertTrue(model.save()[0])
        self.assertTrue(G.Mods(self.home).call("list")["mods"][0]["enabled"])
        self.assertEqual(plan_home(self.home, ("mods", "off"))["env"]["R3HD_MODS_PLAN"], "")
        self.service.call("disable", "test.turkish")
        self.assertEqual(plan_home(self.home)["env"]["R3HD_MODS_PLAN"], "")
        marker = self.home / "mods/keep.txt"
        marker.write_text("unknown")
        self.service.call("remove", "test.turkish")
        self.assertEqual(self.service.call("list")["mods"], [])
        self.assertTrue(marker.is_file())
        self.assertEqual((self.game / "fix.lvl").read_bytes(), self.fix)

    def test_order_and_damaged_mod_failure(self):
        self.service.call("import", self.source)
        self.manifest["id"] = "test.second"
        self.write_zip()
        self.service.call("import", self.source)
        self.service.call("move", "test.second", "up")
        self.assertEqual(self.service.call("list")["mods"][0]["id"], "test.second")
        self.service.call("enable", "test.turkish")
        (self.home / "mods/installed/test.turkish/mod.json").write_text("{}")
        row = self.service.call("list")["mods"][1]
        self.assertEqual(row["code"], "DAMAGED")
        plan = plan_home(self.home)
        self.assertEqual(plan["env"]["R3HD_MODS_PLAN"], "")
        self.assertTrue(any("DAMAGED" in note for note in plan["notes"]))

    def test_source_drift_refuses_application(self):
        self.service.call("import", self.source)
        self.service.call("enable", "test.turkish")
        self.fix[64] ^= 1
        (self.game / "fix.lvl").write_bytes(self.fix)
        row = self.service.call("list")["mods"][0]
        self.assertEqual(row["code"], "TARGET_CHANGED")
        self.assertEqual(plan_home(self.home)["env"]["R3HD_MODS_PLAN"], "")

    def test_tool_failure_is_reported(self):
        with mock.patch.object(G.subprocess, "run", return_value=mock.Mock(stdout="broken", returncode=1)):
            with self.assertRaisesRegex(RuntimeError, "could not be used"):
                self.service.call("list")
        with mock.patch.object(G.subprocess, "run", side_effect=OSError("unavailable")):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                self.service.call("list")

    def test_unsafe_zip_and_unknown_manifest_refused(self):
        with zipfile.ZipFile(self.source, "w") as z:
            z.writestr("../mod.json", "{}")
        with self.assertRaisesRegex(RuntimeError, "UNSAFE_PACKAGE"):
            self.service.call("import", self.source)
        self.manifest["executable"] = "bad"
        self.write_zip()
        with self.assertRaisesRegex(RuntimeError, "BAD_MANIFEST"):
            self.service.call("import", self.source)
        self.assertEqual(self.service.call("list")["mods"], [])

    @unittest.skipUnless(_tk_usable(), "tkinter or a display missing")
    def test_withdrawn_mods_tab_actions(self):
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        status = tk.StringVar(root)
        book = ttk.Notebook(root)
        book.pack()
        view = G.mods_page(book, self.home, status)

        def drain():
            deadline = time.monotonic() + 30
            while view.busy() and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            self.assertFalse(view.busy())
            root.update()

        # Suppress dialogs only: the actual callbacks, background worker and shared CLI all run.
        with mock.patch.object(filedialog, "askopenfilename", return_value=str(self.source)), \
                mock.patch.object(messagebox, "showerror") as error, \
                mock.patch.object(messagebox, "askyesno", return_value=False) as confirm:
            root.update()
            drain()
            view.buttons["zip"].invoke()
            drain()
            self.assertEqual(view.tree.selection(), ("test.turkish",))
            self.assertIn("off", view.tree.item("test.turkish", "values"))
            view.buttons["toggle"].invoke()
            drain()
            self.assertIn("Active", view.tree.item("test.turkish", "values"))
            view.buttons["toggle"].invoke()
            drain()
            self.assertIn("off", view.tree.item("test.turkish", "values"))
            folder = self.root / "folder mod"
            folder.mkdir()
            self.manifest["id"] = "test.folder"
            (folder / "mod.json").write_text(json.dumps(self.manifest), encoding="utf-8")
            with mock.patch.object(filedialog, "askdirectory", return_value=str(folder)):
                view.buttons["folder"].invoke()
            drain()
            view.buttons["up"].invoke()
            drain()
            self.assertEqual(view.tree.get_children()[0], "test.folder")
            view.buttons["down"].invoke()
            drain()
            view.buttons["reload"].invoke()
            drain()
            self.assertEqual(view.tree.get_children()[-1], "test.folder")
            confirm.return_value = True
            view.buttons["remove"].invoke()
            drain()
            view.tree.selection_set("test.turkish")
            root.update()
            confirm.reset_mock()
            confirm.return_value = False
            view.buttons["remove"].invoke()
            confirm.assert_called_once()
            self.assertTrue(view.tree.get_children())  # Cancel preserves the mod.
            confirm.return_value = True
            view.buttons["remove"].invoke()
            drain()
            self.assertFalse(view.tree.get_children())
            error.assert_not_called()
            self.source.write_bytes(b"broken zip")
            view.buttons["zip"].invoke()
            drain()
            error.assert_called_once()
            self.assertIn("Not done:", status.get())

    @unittest.skipIf(os.name == "nt", "requires case-sensitive Linux filesystem")
    def test_case_distinct_game_file_is_not_silently_substituted(self):
        (self.game / "fix.lvl").rename(self.game / "FIX.LVL")
        with self.assertRaisesRegex(RuntimeError, "UNREADABLE"):
            self.service.call("import", self.source)

    def test_released_turkish_zip_unchanged(self):
        if not OPTIONS.turkish:
            self.skipTest("optional authorized Turkish ZIP not supplied")
        before = hashlib.sha256(OPTIONS.turkish.read_bytes()).hexdigest()
        for name in ("fix.lvl", "fix.ptr", "fix.bhf", "fix.btf", "VS.sub"):
            shutil.copyfile(OPTIONS.game_dir / "GAMEDATAbin" / name, self.game / name)
        original = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.game.iterdir()}
        imported = self.service.call("import", OPTIONS.turkish)
        mid = imported["id"]
        self.assertFalse(imported["enabled"])
        self.service.call("enable", mid)
        report = self.service.call("list")
        self.assertEqual(report["active"], [mid])
        self.assertGreater(report["ranges"], 1000)
        self.probe(plan_home(self.home)["env"]["R3HD_MODS_PLAN"])
        self.assertTrue(G.Mods(self.home).call("list")["mods"][0]["enabled"])
        self.service.call("disable", mid)
        self.assertEqual(plan_home(self.home)["env"]["R3HD_MODS_PLAN"], "")
        self.service.call("remove", mid)
        self.assertEqual(self.service.call("list")["mods"], [])
        self.assertEqual(original, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.game.iterdir()})
        self.assertEqual(before, hashlib.sha256(OPTIONS.turkish.read_bytes()).hexdigest())
        print(f"TURKISH_ZIP PASS sha256={before} ranges={report['ranges']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turkish", type=Path)
    parser.add_argument("--game-dir", type=Path)
    parser.add_argument("--probe", type=Path)
    OPTIONS, rest = parser.parse_known_args()
    if bool(OPTIONS.turkish) != bool(OPTIONS.game_dir):
        parser.error("--turkish and --game-dir must be supplied together")
    unittest.main(argv=[sys.argv[0], *rest])
