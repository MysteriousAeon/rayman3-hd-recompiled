"""Synthetic retained-log fixtures only; never launch game, SDL or installed scripts."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import timing as T


class TimingTests(unittest.TestCase):
    def test_timing_privacy_and_labels(self):
        raw = b'''[2026-11-09 00:05:10.296] [info] [core] [t2] M16 vblank mode=deadline window=1 n=600 late_mean_us=0 late_max_us=90 spin_us=600
[2026-11-09 00:05:11.000] [info] [gpu] [t3] M11 pacing series=guest_swap window=1 n=600 mean_us=16666 lag1_milli=-500
[2026-11-09 00:05:11.001] [info] [gpu] [t3] M16 cp_wait mode=vblank_event sleeps=1
[2026-11-09 00:05:11.002] [warning] [gpu] [t3] Texture fetch constant (PRIVATE_WORDS) has "invalid" type!
[2026-11-09 00:05:11.003] [warning] [gpu] [t3] PRIVATE_UNKNOWN
[2026-11-09 00:05:11.004] [info] [core] [t4] level=intro_15
[2026-11-09 00:05:11.005] [info] [gpu] [t3] M31 sampled invalid_type_warning count=1000 (first 8, then every 1000)
'''
        row = T.analyze(raw)
        self.assertEqual(len(row['timing']), 2)
        self.assertEqual(row['timing'][1]['fields']['lag1_milli'], -500)
        self.assertEqual(row['warnings'], {'invalid_texture_fetch_constant': 1, 'unclassified_warning': 1})
        self.assertEqual(row['m16_cp_wait_labels'], {'vblank_event': 1})
        self.assertEqual(row['diagnostic_sampling'][0]['count'], 1000)
        text = json.dumps(row)
        self.assertNotIn('PRIVATE', text)
        self.assertIn('UNKNOWN', row['cpu_per_thread'])

    def test_missing_not_zero_cadence(self):
        row = T.analyze(b'M11 pacing corrupt\n[warning] [t4] missing detail\n')
        self.assertEqual(row['timing'], [])
        self.assertEqual(row['malformed_timing_lines'], 1)
        self.assertIn('UNKNOWN', row['visible_frame_cadence'])

    def test_bounds_and_strict_json(self):
        with self.assertRaises(ValueError): T.analyze(b'x' * 65537)
        with self.assertRaises(ValueError): T.strict(b'{"a":1,"a":2}')
        with self.assertRaises(ValueError): T.strict(b'{"a":NaN}')

    def fixture(self, root):
        task = root / 'task'; home = task / 'portable'; home.mkdir(parents=True)
        # Actual package layout: launchers at root, all ELF payloads under bin/.
        names = ('Play.sh', 'Settings.sh', 'bin/r3hd', 'bin/librexruntime.so',
                 'bin/librexgpu-xenos.so', 'bin/libffmpeg.so', 'bin/libmspack.so')
        files = {}
        for name in names:
            raw = b'SYNTHETIC NEVER EXECUTED ' + name.encode()
            (home / name).parent.mkdir(exist_ok=True); (home / name).write_bytes(raw)
            files[name] = {'size': len(raw), 'sha256': T.digest(raw)}
        manifest = json.dumps({'publishable': False, 'files': files}).encode()
        (home / 'portable.json').write_bytes(manifest)
        (home / 'settings.json').write_bytes(b'PRIVATE SETTINGS')
        (task / 'portable-private-evidence.zip').write_bytes(b'SYNTHETIC ACCEPTED')
        session = home / 'sessions/one'; session.mkdir(parents=True)
        (session / 'runtime.log').write_bytes(b'[warning] [t1] PRIVATE WARNING\n')
        (session / 'session.json').write_bytes(b'PRIVATE PATHS')
        return task, {'PORTABLE': T.digest(manifest), 'SETTINGS': T.digest(b'PRIVATE SETTINGS'),
                      'ACCEPTED': T.digest(b'SYNTHETIC ACCEPTED')}

    def test_collect_integrity_privacy_collision(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve(); task, pins = self.fixture(root); out = root / 'out'
            before = {p: p.read_bytes() for p in task.rglob('*') if p.is_file()}
            with patch.multiple(T, **pins): T.collect(task, out)
            with zipfile.ZipFile(out / 'menu-private-evidence.zip') as z:
                self.assertEqual(set(z.namelist()), {'retained.json', 'SHA256SUMS'})
                raw = z.read('retained.json'); self.assertNotIn(b'PRIVATE', raw)
                self.assertEqual(z.read('SHA256SUMS').decode().split()[0], T.digest(raw))
            self.assertTrue(all(p.read_bytes() == raw for p, raw in before.items()))
            with self.assertRaises(ValueError): T.collect(task, out)

    def test_local_edits_and_multiple_sessions_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve(); task, pins = self.fixture(root)
            game = task / 'portable/bin/r3hd'; original = game.read_bytes()
            with patch.multiple(T, **pins):
                game.write_bytes(b'changed')
                with self.assertRaises(ValueError): T.collect(task, root / 'out')
                self.assertFalse((root / 'out').exists())
                game.write_bytes(original)
                (task / 'portable/sessions/two').mkdir()
                with self.assertRaises(ValueError): T.collect(task, root / 'out')

    def test_changed_manifest_settings_evidence_and_size_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve(); task, pins = self.fixture(root)
            for path in [task / 'portable/portable.json', task / 'portable/settings.json',
                         task / 'portable-private-evidence.zip']:
                raw = path.read_bytes(); path.write_bytes(raw + b' ')
                with patch.multiple(T, **pins), self.assertRaises(ValueError):
                    T.collect(task, root / 'out')
                self.assertFalse((root / 'out').exists()); path.write_bytes(raw)
            with self.assertRaises(ValueError): T.read_stable(task / 'portable/bin/r3hd', 1)

    def test_log_change_refused_without_output(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve(); task, pins = self.fixture(root)
            reader = T.read_stable; reads = []
            def changing(path, limit):
                raw = reader(path, limit)
                if path.name == 'runtime.log':
                    reads.append(1)
                    if len(reads) == 1: path.write_bytes(raw + b'changed\n')
                return raw
            with patch.multiple(T, **pins), patch.object(T, 'read_stable', changing):
                with self.assertRaises(ValueError): T.collect(task, root / 'out')
            self.assertFalse((root / 'out').exists())

    @unittest.skipUnless(__import__('os').name == 'posix', 'POSIX link test')
    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve(); (root / 'real').write_bytes(b'x'); (root / 'link').symlink_to(root / 'real')
            with self.assertRaises(ValueError): T.read_stable(root / 'link', 100)


if __name__ == '__main__':
    unittest.main()
