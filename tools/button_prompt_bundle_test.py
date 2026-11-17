"""D-202: bounded package/discovery tests, no game, GPU, controller or desktop access."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import r3hd_button_prompts as prompts
import r3hd_installer as engine
import r3hd_prompt_bundle as bundle
import r3hd_release_audit as audit
import r3hd_stage as stage

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads((ROOT / "config/release/controller_prompts.json").read_bytes())
DESC = {"record": "config/release/controller_prompts.json", "source_manifest": RECORD["source_manifest"]}
SOURCE = ROOT / DESC["source_manifest"]


class Discovery(unittest.TestCase):
    def test_bundled_translation_keeps_its_changed_blocks_only_for_exact_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = (root / "fix.btf").resolve()
            original = (bytes(32), bytes(32))
            localized = (original[0], b"t" * 16 + bytes(16))
            font = (path, (0, 32, 0, 32, 32), 0, 0, (), original, None)
            ranges = [(path, offset, b"p" * 16, "prompts") for offset in (0, 32, 48, 64)]
            overlaps = []
            for offset, data in zip((0, 32), localized):
                blob = root / f"localized-{offset}"
                blob.write_bytes(data)
                overlaps.append((path, offset, len(data), "tr.full.dev", blob))
            with patch.object(prompts, "BUNDLED_TR_FONT", tuple(hashlib.sha256(d).hexdigest() for d in localized)):
                self.assertEqual(prompts.preserve_bundled_translation(overlaps, font, ranges),
                                 [ranges[i] for i in (0, 2, 3)])
                extra = (path, 64, 16, "community.texture", overlaps[0][-1])
                self.assertEqual(prompts.preserve_bundled_translation([*overlaps, extra], font, ranges), [])
                overlaps[1][-1].write_bytes(bytes(32))
                self.assertEqual(prompts.preserve_bundled_translation(overlaps, font, ranges), [])

    def test_exact_authorization_keeps_audit_gate(self):
        self.assertEqual(json.loads((ROOT / "config/release/payload.json").read_bytes())["controller_prompts"], DESC)
        self.assertIs(RECORD["bundling_authorized"], True)
        self.assertIs(RECORD["publication_authorized"], False)
        if SOURCE.is_file():
            self.assertEqual(bundle.collect(ROOT, DESC), bundle.candidate(ROOT, DESC))

    def test_stage_collector_optional_resources_collision_and_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "LICENSE.txt").write_bytes(b"fixture")
            digest = hashlib.sha256(b"fixture").hexdigest()
            d = {"binaries": {"files": []}, "app_files": {},
                 "python": {"version": "fixture", "files": {"LICENSE.txt": digest},
                            "stdlib_exclude": [], "stdlib_zip_sha256": digest}, "controller_prompts": {}}
            with patch.object(stage, "stdlib_zip", return_value=b"fixture"):
                self.assertFalse(any(p.startswith(bundle.PREFIX) for p in stage.collect(d, root, root, root, root)))
                d["controller_prompts"] = {"record": "fixture"}
                resource = {bundle.PREFIX + "glyphs.json": bundle.MANIFEST}
                with patch.object(bundle, "collect", return_value=resource):
                    self.assertEqual(stage.collect(d, root, root, root, root)[bundle.PREFIX + "glyphs.json"],
                                     (bundle.MANIFEST, "controller_prompt_resource"))
                    d["app_files"] = {bundle.PREFIX + "glyphs.json": "LICENSE.txt"}
                    with self.assertRaises(stage.Refusal) as collision:
                        stage.collect(d, root, root, root, root)
                    self.assertEqual(collision.exception.code, "CONTROLLER_PROMPT_ASSETS")
                d["app_files"] = {}
                with patch.object(bundle, "collect", side_effect=ValueError("bad pin")):
                    with self.assertRaises(stage.Refusal) as bad:
                        stage.collect(d, root, root, root, root)
                    self.assertEqual(bad.exception.code, "CONTROLLER_PROMPT_ASSETS")

    def test_installed_default_and_override_precedence(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(prompts, "ROOT", Path(tmp)), patch.dict(os.environ, {}, clear=True):
            default = Path(tmp) / "assets/playstation_prompts/glyphs.json"
            # Deliberately different errors prove the selected path; invalid overrides must not fall back.
            default.parent.mkdir(parents=True)
            default.write_text("{}")
            with self.assertRaisesRegex(ValueError, "invalid native"):
                prompts.read_glyphs()
            with patch.dict(os.environ, {"R3HD_PS3_PROMPT_SOURCE": str(Path(tmp) / "missing-env")}):
                with self.assertRaises(FileNotFoundError) as env:
                    prompts.read_glyphs()
                self.assertIn("missing-env", str(env.exception))
                with self.assertRaises(FileNotFoundError) as explicit:
                    prompts.read_glyphs(Path(tmp) / "missing-explicit")
                self.assertIn("missing-explicit", str(explicit.exception))


@unittest.skipUnless(SOURCE.is_file(), "private accepted glyph source unavailable")
class NativeBundle(unittest.TestCase):
    def setUp(self):
        work = ROOT / "private/work/button_prompt_bundle_test"
        work.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = bundle.candidate(ROOT, DESC)

    def test_exact_minimum_and_installed_pixels(self):
        self.assertEqual(len(self.files), 10)
        self.assertEqual(sum(map(len, self.files.values())), 16291)
        for rel, data in self.files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        with patch.object(prompts, "ROOT", self.root / "app"), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(prompts.read_glyphs(), prompts.read_glyphs(SOURCE))

    def test_corruption_record_and_extra_inputs(self):
        src = self.root / "source"
        shutil.copytree(SOURCE.parent, src)
        (src / "unrelated.dds").write_bytes(b"must never be bundled")
        record = self.root / "record.json"
        shutil.copyfile(ROOT / DESC["record"], record)
        desc = {"record": "record.json", "source_manifest": "source/glyphs.json"}
        self.assertEqual(bundle.candidate(self.root, desc), self.files)
        data = json.loads(record.read_bytes())
        data["files"][bundle.PREFIX + "L1.png"]["sha256"] = "0" * 64
        record.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "pin mismatch"):
            bundle.candidate(self.root, desc)
        shutil.copyfile(ROOT / DESC["record"], record)
        (src / "L1.png").write_bytes(b"broken")
        with self.assertRaisesRegex(ValueError, "dimensions"):
            bundle.candidate(self.root, desc)
        data["files"][bundle.PREFIX + "extra.png"] = {}
        record.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "invalid controller"):
            bundle.candidate(self.root, desc)

    def test_complete_source_requires_faces_and_new_manifest(self):
        with self.assertRaisesRegex(ValueError, "invalid native glyph manifest"):
            prompts.read_glyphs(ROOT / "private/work/ps3_button_prompts/native_source/shoulders.json")
        src = self.root / "incomplete"
        shutil.copytree(SOURCE.parent, src)
        (src / "cross.png").unlink()
        with self.assertRaises(FileNotFoundError):
            prompts.read_glyphs(src / "glyphs.json")

    def test_exact_resource_policy_keeps_negative_controls(self):
        allow, binaries, pins = audit.load_payload_rules(audit.DEFAULT_PAYLOAD_ALLOWLIST, str(stage.DEFINITION))
        hashes = audit.GameHashes([audit.DEFAULT_MANIFEST], audit.DEFAULT_RELEASES)
        def judge(name, files, public=False, version=None):
            component = self.root / name
            mf = {"publishable": public, "version": version, "files": {r: {"size": len(d), "sha256": hashlib.sha256(d).hexdigest()}
                                                  for r, d in files.items()}}
            stage.write_tree(component, {r: (d, "controller_prompt_resource") for r, d in files.items()}, mf)
            return audit.audit_payload(str(component), allow, binaries, pins, hashes, public)
        self.assertEqual(judge("exact", self.files)["verdict"], "PASS")
        damaged = dict(self.files)
        damaged[bundle.PREFIX + "L1.png"] += b"modified"
        self.assertIn("PIN_MISMATCH", judge("corrupt", damaged)["reason_counts"])
        del damaged[bundle.PREFIX + "L1.png"]
        self.assertIn("RESOURCE_INCOMPLETE", judge("incomplete", damaged)["reason_counts"])
        extra = dict(self.files)
        extra[bundle.PREFIX + "L3.png"] = self.files[bundle.PREFIX + "L1.png"]
        rejected = judge("extra", extra)
        self.assertEqual(rejected["verdict"], "FAIL")
        self.assertIn("NOT_ALLOWLISTED", rejected["reason_counts"])
        self.assertIn("CAPTURE", rejected["reason_counts"])
        self.assertIn("RESOURCE_PUBLIC_AUTHORIZATION", judge("public", self.files, True)["reason_counts"])
        self.assertIn("RESOURCE_PUBLIC_AUTHORIZATION", judge("other-release", self.files, True, "1.2.1")["reason_counts"])
        self.assertEqual(judge("v120-candidate", self.files, True, "1.2.0")["verdict"], "PASS")
        extra[bundle.PREFIX + "L1.png"] += b"modified"
        candidate_findings = judge("v120-invalid", extra, True, "1.2.0")["reason_counts"]
        self.assertIn("PIN_MISMATCH", candidate_findings)
        self.assertIn("NOT_ALLOWLISTED", candidate_findings)

    def add_resources(self, payload):
        mf = engine.read_json(payload / "payload.json")
        for rel, data in self.files.items():
            p = payload / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            mf["files"][rel] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "role": "test"}
        mf["payload_id"] = hashlib.sha256("".join(f"{r}\t{e['size']}\t{e['sha256']}\n"
                                                   for r, e in sorted(mf["files"].items())).encode()).hexdigest()
        engine.write_json(payload / "payload.json", mf)

    def test_synthetic_install_update_repair_preserves_user_files(self):
        # Synthetic installer fixture, not a production stage or audit bypass.
        pl, tree, rels = engine.make_fixture(self.root)
        self.add_resources(pl)
        sys32 = self.root / "sys32"
        sys32.mkdir()
        for name in engine.VC_RUNTIME:
            (sys32 / name).write_bytes(b"fixture")
        home = self.root / "Home"
        env = {"R3HD_INSTALL_SYSTEM32": str(sys32), "R3HD_INSTALL_FAKE_RUNNING": "0",
               "R3HD_INSTALL_FAKE_LAUNCHER": "0"}
        with patch.dict(os.environ, env):
            engine.install(home, pl, tree, "vanilla", releases=rels, log=lambda *_: None)
            import r3hd_settings as settings
            self.assertEqual(settings.resolve(settings.load_registry(), settings=engine.read_json(home / "settings.json"))["values"]["controller_prompts"], "auto")
            engine.set_preferences(home, ["controller_prompts=playstation"])
            protected = {"settings.json": (home / "settings.json").read_bytes(),
                         "profiles/fixture/save.dat": b"save", "mods/fixture.txt": b"mod", "unknown.txt": b"unknown"}
            for rel, data in protected.items():
                p = home / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            damaged = home / (bundle.PREFIX + "L1.png")
            damaged.unlink()
            self.assertIn("FILES\tok\t0\t", engine.launcher_model(home, rels))
            with patch.object(prompts, "ROOT", home / "app"), patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(FileNotFoundError):
                    prompts.read_glyphs()  # launch builder refuses the plan: Xbox fallback
            damaged.write_bytes(b"damaged")
            engine.repair(home, pl, releases=rels, log=lambda *_: None)
            self.assertEqual(damaged.read_bytes(), self.files[bundle.PREFIX + "L1.png"])
            pl2 = engine.make_fixture(self.root, "0.30.0", b"v2")[0]
            self.add_resources(pl2)
            engine.install(home, pl2, releases=rels, log=lambda *_: None)
            for rel, data in protected.items():
                self.assertEqual((home / rel).read_bytes(), data)
            with patch.object(prompts, "ROOT", home / "app"), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(prompts.read_glyphs(), prompts.read_glyphs(SOURCE))


if __name__ == "__main__":
    unittest.main()
