"""Offline synthetic records only; no launcher or native execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import review as R


def fixture():
    r = {'owner': 'R3HD_MENU_CPU_01', 'program_identity': R.IDENTITY,
         'helper_seal_sha256': R.C.RUNNER_SEAL, 'retained_evidence_sha256': R.C.RETAINED,
         'after_program_identity': R.IDENTITY, 'complete_comparison': True, 'script_exit': 0,
         'stop_reason': None, 'forced_reason': None, 'termination_actions': [],
         'focus_confirmed_human': True, 'windows': ['MENU', 'GAMEPLAY'], 'clock_ticks_per_second': 100,
         'human_observations': {'menu_slowdown_seen': 'unknown', 'gameplay_speed_looked_normal': 'yes'}}
    rows = {'before.json': copy.deepcopy(r), 'receipt.json': r}
    for j, name in enumerate(('menu', 'gameplay')):
        points = [{'monotonic': j * 60 + i, 'wall': f'2026-11-09T00:0{j}:{i:02}+03:00',
                   'counter_read_seconds': .002, 'process_ticks': i * 100,
                   'threads': {'7:3': {'ticks': i * 100, 'state': 'R'}}, 'unreadable_or_exited_tids': []}
                  for i in range(46)]
        rows[name + '.json'] = {'scene_human_label': name.upper(), 'window_complete': True,
            'thread_samples_complete': True, 'samples': points,
            'deltas': [R.C.deltas(a, b, 100) for a, b in zip(points, points[1:])]}
    return rows


class ReviewTests(unittest.TestCase):
    def test_recompute_and_keep_unknown(self):
        result = R.analyze(fixture())
        self.assertEqual(result['windows']['menu']['process_one_core_percent'], 100)
        self.assertEqual(result['human_observations']['menu_slowdown_seen'], 'unknown')
        self.assertIn('pause navigation NOT MEASURED', result['scope'])

    def test_semantic_tampering(self):
        for change in ('calculation', 'settings', 'forced', 'missing', 'scene', 'clock', 'reuse'):
            rows = fixture()
            if change == 'calculation': rows['menu.json']['deltas'][0]['process_one_core_percent'] = 0
            if change == 'settings': rows['receipt.json']['after_program_identity'] = {}
            if change == 'forced': rows['receipt.json']['termination_actions'] = ['SIGTERM']
            if change == 'missing': rows['menu.json']['samples'][0]['unreadable_or_exited_tids'] = [7]
            if change == 'scene': rows['menu.json']['scene_human_label'] = 'PAUSE_NAVIGATION'
            if change == 'clock': rows['receipt.json']['clock_ticks_per_second'] = True
            if change == 'reuse': rows['menu.json']['samples'][1]['process_ticks'] = -1
            with self.subTest(change=change), self.assertRaises(ValueError): R.analyze(rows)

    def test_archive_ledger_and_hash(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d).resolve() / 'fixture.zip'
            files = {n: json.dumps(row).encode() for n, row in fixture().items()}
            with zipfile.ZipFile(path, 'x') as z:
                for n, raw in files.items(): z.writestr(n, raw)
                z.writestr('SHA256SUMS', ''.join(R.T.digest(raw) + '  ' + n + '\n' for n, raw in sorted(files.items())))
            digest = R.T.digest(path.read_bytes())
            side = Path(str(path) + '.sha256'); side.write_text(digest + '  fixture.zip\n')
            self.assertEqual(R.analyze(R.authenticate(path, digest))['windows']['gameplay']['seconds'], 45)
            with self.assertRaises(ValueError): R.authenticate(path, '0' * 64)
            side.write_text(digest + '  other.zip\n')
            with self.assertRaises(ValueError): R.authenticate(path, digest)

    def test_invalid_ledger_json_and_extra_member(self):
        for defect in ('ledger', 'duplicate_json', 'nan', 'extra_member'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as d:
                path = Path(d).resolve() / 'fixture.zip'
                files = {n: json.dumps(row).encode() for n, row in fixture().items()}
                if defect == 'duplicate_json': files['before.json'] = b'{"owner":1,"owner":2}'
                if defect == 'nan': files['before.json'] = b'{"owner":NaN}'
                with zipfile.ZipFile(path, 'x') as z:
                    for n, raw in files.items(): z.writestr(n, raw)
                    ledger = ''.join(R.T.digest(raw) + '  ' + n + '\n' for n, raw in sorted(files.items()))
                    if defect == 'ledger': ledger = '0' * 64 + ledger[64:]
                    z.writestr('SHA256SUMS', ledger)
                    if defect == 'extra_member': z.writestr('../untrusted', b'not extracted')
                digest = R.T.digest(path.read_bytes())
                Path(str(path) + '.sha256').write_text(digest + '  fixture.zip\n')
                with self.assertRaises(ValueError): R.authenticate(path, digest)


if __name__ == '__main__': unittest.main()
