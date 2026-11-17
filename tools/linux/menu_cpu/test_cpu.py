"""Fixtures and owned Python helpers only. Never launch target/SDL/physical devices."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'menu_timing'))
import cpu as C


def stat_text(pid, start=100, ticks=10, name='spoof (r3hd)'):
    f = ['S', '1', str(pid)] + ['0'] * 18
    f[11] = str(ticks); f[12] = '2'; f[19] = str(start)
    return str(pid) + ' (' + name + ') ' + ' '.join(f)


class CpuTests(unittest.TestCase):
    def test_stat_comm_spoof_and_start(self):
        row = C.proc_stat(stat_text(12))
        self.assertEqual((row['id'], row['start'], row['ticks']), (12, 100, 12))

    def test_cpu_units_thread_reuse_and_gaps(self):
        a = {'monotonic': 5., 'process_ticks': 100, 'threads': {'7:10': {'ticks': 10}, '8:20': {'ticks': 5}}}
        b = {'monotonic': 7., 'process_ticks': 300, 'threads': {'7:10': {'ticks': 210}, '8:30': {'ticks': 8}}}
        r = C.deltas(a, b, 100)
        self.assertEqual(r['process_one_core_percent'], 100)
        self.assertEqual(r['thread_one_core_percent'], {'7:10': 100})
        self.assertEqual(r['ended_threads'], ['8:20']); self.assertEqual(r['new_threads'], ['8:30'])
        b['process_ticks'] = 0
        with self.assertRaises(ValueError): C.deltas(a, b, 100)

    def test_backup_preserves_inputs_and_private_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d).resolve(); home = p / 'home'; out = p / 'out'; out.mkdir()
            f = home / 'profiles/default/user/secret'; f.parent.mkdir(parents=True); f.write_bytes(b'PRIVATE SAVE')
            r = C.backup_profiles(home, out)
            self.assertEqual(f.read_bytes(), b'PRIVATE SAVE')
            self.assertEqual((out / 'profile-backup-local/default/user/secret').read_bytes(), b'PRIVATE SAVE')
            self.assertNotIn('secret', json.dumps(r)); self.assertEqual(r['files'], 1)

    def test_untrusted_helper_before_import(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            with patch.object(C.Path, 'home', return_value=root):
                with self.assertRaises(OSError): C.helpers()
                runner = root / 'Downloads/r3hd-normal-portable-01'; runner.mkdir(parents=True)
                (runner / 'SHA256SUMS').write_bytes(b'UNTRUSTED')
                with self.assertRaises(ValueError): C.helpers()
        self.assertEqual(C.reason(PermissionError('/private/path')), 'PermissionError')

    def test_relevant_denied_metadata_fails_closed(self):
        with patch.object(C, 'proc', side_effect=PermissionError('fixture')):
            with self.assertRaises(PermissionError): C.game_identity(12, Path('not-used'), 12)

    def test_normal_launcher_exit_race_and_timeout(self):
        class Child:
            pid = 12
            def poll(self): return 0
        g = C.Guard(Child(), Path('not-used'), Path('not-used'), 10)
        with patch.object(C, 'proc', side_effect=AssertionError('must not inspect reaped PID')):
            g.check(allow_exit=True)
            self.assertEqual(C.stop_owned(Child(), 10), [])
        g.deadline = 0
        with self.assertRaises(ValueError): g.check(allow_exit=True)

    def flow(self, root, fail=False):
        task = root / 'task'; home = task / 'portable'; out = root / 'out'
        old = home / 'sessions/old'; old.mkdir(parents=True)
        log = old / 'runtime.log'; log.write_bytes(b'OLD LOG')
        mods = home / 'mods/state.json'; mods.parent.mkdir(); mods.write_bytes(b'MODS')
        for name in ('settings.json', 'installer.json'): (home / name).write_bytes(b'PRIVATE CONFIG')
        profile = home / 'profiles/default/user/save'; profile.parent.mkdir(parents=True); profile.write_bytes(b'PRIVATE SAVE')
        class Child:
            pid = 987654; returncode = None
            def poll(self): return self.returncode
        child = Child()
        class Guard:
            def __init__(self, *args): pass
            def check(self, **kw): pass
            def delay(self, *args): pass
            def prompt(self, phrase):
                if fail is True: raise ValueError('fixture stop')
                if phrase == 'BOTH WINDOWS KEPT GAME FOCUSED': child.returncode = 0
        def popen(*args, **kwargs):
            self.assertEqual(args[0], [str(home / 'Play.sh')])
            self.assertEqual(kwargs['env'], {'NORMAL': 'UNCHANGED'})
            new = home / 'sessions/new'; new.mkdir(); (new / 'runtime.log').write_bytes(b'M16 cp_wait mode=vblank_event sleeps=1\n')
            return child
        calls = []
        def stop(ch, start):
            calls.append(ch.pid); ch.returncode = -15 if fail else ch.returncode
            return ['SIGTERM'] if fail else []
        times = iter(range(1, 20))
        def point(*args):
            n = next(times)
            if fail == 'sample' and n > 1: raise ValueError('fixture partial sample')
            return {'monotonic': n, 'process_ticks': 100, 'threads': {}, 'unreadable_or_exited_tids': []}
        with patch.object(C, 'Guard', Guard), patch.object(C, 'SECONDS', 2), \
             patch.object(C, 'proc', return_value={'start': 10}), patch.object(C, 'find_game', return_value={'pid': 123, 'group': 987654}), \
             patch.object(C, 'sample', point), patch.object(C, 'game_identity', side_effect=FileNotFoundError), \
             patch.object(C.subprocess, 'Popen', popen), patch.object(C, 'stop_owned', stop), \
             patch.object(C.T, 'authenticate', return_value={'verified': True}), \
             patch.object(C, 'MODS', C.T.digest(b'MODS')), patch.object(C, 'LOG', C.T.digest(b'OLD LOG')), \
             patch.object(C.os, 'sysconf', return_value=100, create=True), patch('builtins.input', return_value='yes'):
            result = C.run(task, out, None, {'NORMAL': 'UNCHANGED'}, {'verified': True}, [old], [log])
        with zipfile.ZipFile(out / 'cpu-private-evidence.zip') as z:
            receipt = json.loads(z.read('receipt.json'))
            self.assertNotIn(b'PRIVATE SAVE', b''.join(z.read(n) for n in z.namelist()))
            self.assertFalse(any('backup' in n or 'console' in n for n in z.namelist()))
            for line in z.read('SHA256SUMS').decode().splitlines():
                h, n = line.split('  '); self.assertEqual(h, C.T.digest(z.read(n)))
        self.assertEqual(log.read_bytes(), b'OLD LOG'); self.assertEqual(profile.read_bytes(), b'PRIVATE SAVE')
        return result, receipt, calls

    def test_exact_normal_launch_and_export(self):
        with tempfile.TemporaryDirectory() as d:
            result, r, _ = self.flow(Path(d).resolve())
            self.assertEqual(result, 0); self.assertTrue(r['complete_comparison'])
            self.assertEqual(r['windows'], ['MENU', 'GAMEPLAY'])
            self.assertIsNone(r['forced_reason']); self.assertIsNone(r['stop_reason'])
            self.assertEqual(r['termination_actions'], [])

    def test_partial_failure_no_retry(self):
        with tempfile.TemporaryDirectory() as d:
            result, r, calls = self.flow(Path(d).resolve(), fail=True)
            self.assertEqual(result, 2); self.assertFalse(r['complete_comparison'])
            self.assertEqual(calls, [987654]); self.assertIn('fixture stop', r['forced_reason'])

    def test_partial_window_kept(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve(); result, r, _ = self.flow(root, fail='sample')
            self.assertEqual(result, 2)
            row = json.loads((root / 'out/menu.json').read_bytes())
            self.assertFalse(row['window_complete']); self.assertEqual(len(row['samples']), 1)

    @unittest.skipUnless(os.name == 'posix', 'real /proc helper test')
    def test_owned_nongame_identity_sampling_and_stop(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(5)'], start_new_session=True)
        try:
            start = C.proc(child.pid)['start']; exe = Path(sys.executable).resolve()
            who = C.game_identity(child.pid, exe, child.pid)
            with self.assertRaises(ValueError): C.game_identity(child.pid, Path('/usr/bin/false'), child.pid)
            with self.assertRaises(ValueError): C.game_identity(child.pid, exe, child.pid + 1)
            a = C.sample(who, exe); time.sleep(.03); b = C.sample(who, exe)
            self.assertGreater(C.deltas(a, b, os.sysconf('SC_CLK_TCK'))['seconds'], 0)
            altered = {**who, 'start': who['start'] + 1}
            with self.assertRaises(ValueError): C.sample(altered, exe)
            reader = Path.read_text
            def denied(path, *args, **kw):
                if '/task/' in str(path) and path.name == 'stat': raise PermissionError('fixture')
                return reader(path, *args, **kw)
            with patch.object(Path, 'read_text', denied):
                incomplete = C.sample(who, exe)
                self.assertTrue(incomplete['unreadable_or_exited_tids'])
            with self.assertRaises(ValueError): C.stop_owned(child, start + 1)
            self.assertIsNone(child.poll())
            C.stop_owned(child, start); self.assertIsNotNone(child.poll())
        finally:
            if child.poll() is None: child.terminate(); child.wait(timeout=3)


if __name__ == '__main__': unittest.main()
