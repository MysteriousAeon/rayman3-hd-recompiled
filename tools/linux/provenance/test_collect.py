"""Synthetic metadata fixtures only; never execute game, launcher or installed code."""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import collect as C
import build_bundle as B


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = B.make_lock()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def fixture(self, label='home'):
        root = self.root / label
        root.mkdir()
        files = {'bin/' + n: (b'fixture ' + n.encode()) for n in C.COMPONENTS}
        files.update({n: b'fixture program' for n in self.lock['contract_files']})
        payload = {'files': {n: {'sha256': C.digest(b), 'size': len(b), 'role': 'fixture'} for n, b in files.items() if n not in ('Play.sh', 'Settings.sh')},
                   'publishable': False, 'requires': {'glibc': '2.38', 'glibcxx': '3.4.32'}}
        files['payload.json'] = C.encode(payload)
        portable = {'files': {n: {'sha256': C.digest(b), 'size': len(b)} for n, b in files.items()},
                    'development_id': 'fixture', 'application_version': '1.1.0-linux-experimental', 'payload_id': 'f' * 64,
                    'lgpl': {'corresponding_source': {'archive': 'r3hd-lgpl-source-1.1.0-linux-x86_64.zip', 'sha256': 'e' * 64}}, 'publishable': False}
        files['portable.json'] = C.encode(portable)
        for n, b in files.items():
            p = root / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
        return root, files

    def archive(self, files, name='fixture.tar.gz'):
        path = self.root / name
        with tarfile.open(path, 'w:gz') as t:
            for n, b in files.items():
                i = tarfile.TarInfo(C.TOP + n)
                i.mode = 0o755 if n in ('Play.sh', 'Settings.sh', 'bin/r3hd') else 0o644
                i.size = len(b)
                t.addfile(i, io.BytesIO(b))
        return path

    def test_package_install_identities_and_configuration_only_comparison(self):
        a, files = self.fixture('a')
        b, _ = self.fixture('b')
        arc = self.archive(files)
        lock = dict(self.lock, packages={arc.name: C.digest(arc.read_bytes())})
        archive = C.package(C.Reader(self.root), arc.name, lock)
        self.assertEqual(archive['authentication'], 'PINNED_SHA256')
        (a / 'settings.json').write_text(json.dumps({'schema': 3, 'preset': 'hdplus', 'preferences': {}, 'comment': 'PRIVATE-SENTINEL'}))
        (a / 'mods').mkdir()
        (a / 'mods/state.json').write_text(json.dumps({'schema': 1, 'mods': [{'id': 'secret.mod', 'enabled': True, 'installed_at': 'PRIVATE-SENTINEL'}]}))
        x = C.installation(C.Reader(self.root), 'a', lock, {'fixture': archive})
        y = C.installation(C.Reader(self.root), 'b', lock, {'fixture': archive})
        self.assertEqual(x['authentication'], 'PINNED_ARCHIVE_MATCH')
        self.assertEqual(x['manifest_mismatches'], [])
        self.assertEqual(x['configuration']['mods']['enabled_entries'], 1)
        self.assertNotIn(b'PRIVATE-SENTINEL', C.encode(x))
        self.assertNotIn(b'secret.mod', C.encode(x))
        comparison = C.compare({'a': x, 'b': y})['a__b']
        self.assertEqual(comparison['different_binaries'], [])
        self.assertFalse(comparison['same_configuration_metadata'])
        (b / 'bin/r3hd').write_bytes(b'changed fixture')
        y = C.installation(C.Reader(self.root), 'b', lock, {})
        self.assertEqual(y['manifest_mismatches'], ['bin/r3hd'])
        self.assertEqual(C.compare({'a': x, 'b': y})['a__b']['different_binaries'], ['bin/r3hd'])

    def test_malformed_untrusted_inventory_and_archive_tamper_refuse(self):
        root, files = self.fixture()
        arc = self.archive(files)
        lock = dict(self.lock, packages={arc.name: '0' * 64})
        with self.assertRaisesRegex(ValueError, 'pinned archive'):
            C.package(C.Reader(self.root), arc.name, lock)
        for n in ('../data/save', '/bin/r3hd', 'app/../../data', 'data/content/secret', 'app/unexpected.py'):
            bad = C.encode({'files': {n: {'size': 1, 'sha256': 'a' * 64}}})
            with self.assertRaises(ValueError):
                C.manifest(bad, self.lock['allowed'])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            C.parse(b'{"files":{},"files":{}}')
        bad = dict(files)
        bad['bin/r3hd'] += b'tamper'
        arc = self.archive(bad, 'untrusted.tar.gz')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            C.package(C.Reader(self.root), arc.name, self.lock)

    def test_reader_changes_limits_and_absence(self):
        p = self.root / 'meta'
        p.write_bytes(b'first')
        reader = C.Reader(self.root)
        reader.read('meta')
        p.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            reader.read('meta')
        with self.assertRaises(ValueError):
            reader.unchanged()
        with self.assertRaisesRegex(ValueError, 'metadata size'):
            C.Reader(self.root).read('meta', limit=1)
        reader = C.Reader(self.root)
        self.assertIsNone(reader.optional('missing')[0])
        (self.root / 'missing').write_bytes(b'new')
        with self.assertRaises(ValueError):
            reader.unchanged()
        with self.assertRaises(ValueError):
            C.Reader(self.root, seconds=-1).read('meta')
        budget = C.ArchiveBudget(io.BytesIO(b'x'), C.Reader(self.root))
        budget.total = 500_000_000
        with self.assertRaisesRegex(ValueError, 'decompression budget'):
            budget.read(1)

    @unittest.skipUnless(os.name == 'posix', 'actual Linux nofollow descriptor tests')
    def test_symlink_fifo_and_permission_error_are_not_absence(self):
        (self.root / 'target').write_bytes(b'fixture')
        (self.root / 'link').symlink_to('target')
        (self.root / 'dangling').symlink_to('absent')
        for n in ('link', 'dangling'):
            with self.assertRaises(ValueError):
                C.Reader(self.root).optional(n)
        os.mkfifo(self.root / 'fifo')
        with self.assertRaises(ValueError):
            C.Reader(self.root).read('fifo')
        with patch.object(C.Reader, 'read', side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                C.Reader(self.root).optional('target')

    def test_schema_filters_and_no_installed_execution_or_private_traversal(self):
        root, _ = self.fixture()
        (root / 'settings.json').write_text(json.dumps({'schema': 3, 'preset': 'vanilla', 'base': None}))
        self.assertEqual(C.settings(C.Reader(root), self.lock)['preset'], 'vanilla')
        (root / 'settings.json').write_text(json.dumps({'schema': 3, 'preset': 'custom', 'base': 'hdplus', 'preferences': {'dualsense_light': 'ARBITRARY'}}))
        with self.assertRaises(ValueError):
            C.settings(C.Reader(root), self.lock)
        parsed = ast.parse((C.HERE / 'collect.py').read_text(encoding='utf-8'))
        imported = [n.names[0].name for n in ast.walk(parsed) if isinstance(n, ast.Import)]
        self.assertNotIn('subprocess', imported)
        self.assertNotIn('importlib', imported)
        calls = [n.func.attr for n in ast.walk(parsed) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        for prohibited in ('execv', 'spawnv', 'Popen', 'kill', 'unlink', 'rmtree', 'extractall', 'rglob'):
            self.assertNotIn(prohibited, calls)
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and
                             isinstance(n.func.value, ast.Name) and n.func.value.id == 'os' and
                             n.func.attr == 'system' for n in ast.walk(parsed)))

    def test_reproducible_toolkit_tamper_and_output_collision(self):
        a, b = self.root / 'kit-a', self.root / 'kit-b'
        B.build(a)
        B.build(b)
        self.assertEqual((a / 'r3hd-linux-provenance.zip').read_bytes(), (b / 'r3hd-linux-provenance.zip').read_bytes())
        extracted = self.root / 'runner'
        with zipfile.ZipFile(a / 'r3hd-linux-provenance.zip') as z:
            self.assertEqual(len(z.namelist()), 4)
            self.assertIsNone(z.testzip())
            z.extractall(extracted)  # test-only trusted fixture; native handoff checks flat names/types first.
        with patch.object(C, 'HERE', extracted):
            C.seal()
            (extracted / 'LOCK.json').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                C.seal()
        before = (a / 'r3hd-linux-provenance.zip').read_bytes()
        with self.assertRaises(ValueError):
            B.build(a)
        self.assertEqual(before, (a / 'r3hd-linux-provenance.zip').read_bytes())

    def test_complete_collect_fixture_no_input_writes_and_collision(self):
        # Run whole orchestration with synthetic HOME and mocked native prerequisites only.
        home = self.root / 'synthetic'
        home.mkdir()
        (home / 'Projects').mkdir()
        programs, files = self.fixture('programs')
        for n in ('f', 'r', 'n'):
            shutil.copytree(programs, home / n)
        archive = self.archive(files)
        shutil.copyfile(archive, home / 'fixture.tar.gz')
        lock = dict(self.lock, packages={'fixture.tar.gz': C.digest(archive.read_bytes())},
                    archive_paths={'noble': 'fixture.tar.gz'}, installation_paths={'lx2f': ['f'], 'lx2red': ['r'], 'noble_stage2d': ['n']},
                    source_files={n: C.digest(files[n]) for n in self.lock['contract_files']})
        runner = self.root / 'test-runner'
        runner.mkdir()
        (runner / 'LOCK.json').write_bytes(C.encode(lock))
        (runner / 'SHA256SUMS').write_bytes(b'fixture seal')
        before = {p.relative_to(home).as_posix(): C.digest(p.read_bytes()) for p in home.rglob('*') if p.is_file()}
        # Native gating is mocked here, not evidence of native host or target execution.
        with patch.object(C, 'HERE', runner), patch.object(C, 'seal'), patch.object(C.Path, 'home', return_value=home), \
             patch.object(C.platform, 'system', return_value='Linux'), patch.object(C.platform, 'machine', return_value='x86_64'), \
             patch.object(C.os, 'getuid', return_value=1000, create=True), patch.object(C.Path, 'read_text', return_value='fixture-linux'):
            self.assertEqual(C.collect(), 0)
            with self.assertRaisesRegex(ValueError, 'fresh output'):
                C.collect()
        for n, h in before.items():
            self.assertEqual(C.digest((home / n).read_bytes()), h)
        with zipfile.ZipFile(home / 'Projects/R3HD-linux-provenance-01/provenance-private-evidence.zip') as z:
            receipt = C.parse(z.read('metadata.json'))
            self.assertEqual(receipt['collection'], 'COMPLETE_METADATA_ONLY')
            self.assertIn('NOT VERIFIED', receipt['canonical_candidate'])
            self.assertEqual(set(z.namelist()), {'metadata.json', 'SHA256SUMS'})
        evidence = home / 'Projects/R3HD-linux-provenance-01/provenance-private-evidence.zip'
        with patch.object(C, 'HERE', runner), patch.object(C, 'seal'):
            self.assertEqual(C.review(evidence)['collection'], 'COMPLETE_METADATA_ONLY')
            Path(str(evidence) + '.sha256').write_text('wrong checksum')
            with self.assertRaisesRegex(ValueError, 'evidence sidecar'):
                C.review(evidence)

    def test_gaps_still_produce_checked_partial_evidence(self):
        home = self.root / 'missing-fixture-home'
        (home / 'Projects').mkdir(parents=True)
        runner = self.root / 'runner'
        runner.mkdir()
        lock = dict(self.lock, archive_paths={'noble': 'absent.tar.gz'},
                    installation_paths={'lx2f': ['absent-f'], 'lx2red': ['absent-r'], 'noble_stage2d': ['absent-n']})
        (runner / 'LOCK.json').write_bytes(C.encode(lock))
        (runner / 'SHA256SUMS').write_bytes(b'fixture seal')
        with patch.object(C, 'HERE', runner), patch.object(C, 'seal'), patch.object(C.Path, 'home', return_value=home), \
             patch.object(C.platform, 'system', return_value='Linux'), patch.object(C.platform, 'machine', return_value='x86_64'), \
             patch.object(C.os, 'getuid', return_value=1000, create=True), patch.object(C.Path, 'read_text', return_value='fixture-linux'):
            self.assertEqual(C.collect(), 2)
        with patch.object(C, 'HERE', runner), patch.object(C, 'seal'):
            j = C.review(home / 'Projects/R3HD-linux-provenance-01/provenance-private-evidence.zip')
            self.assertTrue(j['collection'].startswith('STOP_WITH_GAPS'))
            self.assertTrue(all('files' not in x for x in j['installations'].values()))


if __name__ == '__main__':
    unittest.main()
