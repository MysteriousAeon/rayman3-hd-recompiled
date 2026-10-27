#!/usr/bin/env python3
"""Issue #3: deterministic process-query safety; synthetic homes, no locale change or game launch."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import r3hd_installer as engine

BASE = b'"System","4","Services","0","100 K"\r\n'


class ProcessChecks(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ)
        self.env.start()
        for key in engine.HOOKS:
            os.environ.pop(key, None)

    def tearDown(self):
        self.env.stop()

    def query(self, stdout=BASE, returncode=0):
        return subprocess.CompletedProcess([], returncode, stdout, b'')

    def test_reporter_encoding_and_original_crash(self):
        message = 'INFORMATION: Es werden keine Aufgaben mit den angegebenen Kriterien ausgeführt.'
        raw = message.encode('cp850')
        self.assertEqual(raw[74], 0x81)
        with self.assertRaises(UnicodeDecodeError):
            raw.decode('cp1252')
        with self.assertRaises(AttributeError):
            self.query(None).stdout.lower()

    def test_english_and_german_oem_rows(self):
        for session in ('Console', 'Dienste für Benutzer'):
            for target in ('r3hd.exe', 'r3hd_launcher.exe', 'other.exe'):
                raw = BASE + f'"{target.upper()}","234","{session}","1","1.234 K"\r\n'.encode('cp850')
                # Decode the OEM fixture independently of this host's OEM code page.
                rows = engine._parse_process_snapshot(raw, 'cp850')
                with patch.object(engine, '_process_snapshot', return_value=rows):
                    self.assertEqual(engine.game_running(), target == 'r3hd.exe')
                    self.assertEqual(engine.image_running('r3hd_launcher.exe', 'R3HD_INSTALL_FAKE_LAUNCHER'),
                                     target == 'r3hd_launcher.exe')

    def test_exact_image_and_pid_match(self):
        rows = engine._parse_process_snapshot(BASE + b'"not-r3hd.exe","1234","Console","1","100 K"', 'ascii')
        with patch.object(engine, '_process_snapshot', return_value=rows):
            self.assertFalse(engine.game_running())
            self.assertFalse(engine.process_alive(234))
            self.assertTrue(engine.process_alive(1234))

    def test_bad_stdout_refuses(self):
        for stdout in (None, '', b'', b'\r\n', b'garbage', b'"r3hd.exe","x","a","1","x"',
                       b'"r3hd.exe","123"', b'"unclosed', b'"","4","a","1","x"',
                       b'"a\x00b","4","a","1","x"', BASE + b'ERROR'):
            with self.subTest(stdout=stdout), patch.object(engine.subprocess, 'run', return_value=self.query(stdout)):
                with self.assertRaises(engine.Refusal) as exc:
                    engine.check_not_running()
                self.assertEqual(exc.exception.code, 'PROCESS_QUERY_FAILED')
                self.assertTrue(engine.process_alive(99))

    def test_decode_failure_refuses(self):
        with patch.object(engine.subprocess, 'run', return_value=self.query()), patch.object(
                engine, '_parse_process_snapshot', side_effect=UnicodeDecodeError('ascii', b'\xff', 0, 1, 'test')):
            with self.assertRaises(engine.Refusal) as exc:
                engine.game_running()
            self.assertEqual(exc.exception.code, 'PROCESS_QUERY_FAILED')

    def test_exit_timeout_and_launch_failures(self):
        for failure in (self.query(BASE, 1), subprocess.TimeoutExpired('tasklist', 30), OSError('denied')):
            kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure}
            with self.subTest(failure=failure), patch.object(engine.subprocess, 'run', **kwargs):
                with self.assertRaises(engine.Refusal) as exc:
                    engine.check_not_running()
                self.assertEqual(exc.exception.code, 'PROCESS_QUERY_FAILED')
                self.assertTrue(engine.process_alive(99))

    def test_binary_hidden_full_snapshot_contract(self):
        with patch.object(engine.subprocess, 'run', return_value=self.query()) as run:
            self.assertFalse(engine.game_running())
        args, kwargs = run.call_args
        self.assertEqual(args[0][1:], ['/FO', 'CSV', '/NH'])
        self.assertTrue(Path(args[0][0]).is_absolute())
        self.assertFalse(kwargs.get('text', False))
        self.assertEqual(kwargs['timeout'], 30)
        self.assertEqual(kwargs['creationflags'], subprocess.CREATE_NO_WINDOW)

    def test_existing_hooks(self):
        for key, fn in (('R3HD_INSTALL_FAKE_RUNNING', engine.game_running),
                        ('R3HD_INSTALL_FAKE_LAUNCHER', lambda: engine.image_running('r3hd_launcher.exe',
                                                                                 'R3HD_INSTALL_FAKE_LAUNCHER'))):
            for value in ('0', '1', 'invalid'):
                with patch.dict(os.environ, {key: value}), patch.object(engine, '_process_snapshot', return_value=[]) as query:
                    self.assertEqual(fn(), value == '1')
                    self.assertEqual(query.call_count, int(value == 'invalid'))

    def test_operation_paths_refuse_and_preserve_files(self):
        with tempfile.TemporaryDirectory(prefix='r3hd_issue3_') as tmp, patch.object(engine, 'check_platform'):
            root = Path(tmp)
            payload, source, releases = engine.make_fixture(root)
            home = root / 'home'
            with patch.object(engine, '_process_snapshot', return_value=[('system', 4)]):
                engine.install(home, payload, source, 'vanilla', releases=releases, log=lambda *_: None)
            before = {p.relative_to(home).as_posix(): p.read_bytes() for p in home.rglob('*') if p.is_file()}
            for rows, code in (([('r3hd.exe', 123)], 'GAME_RUNNING'),
                               ([('r3hd_launcher.exe', 123)], 'LAUNCHER_RUNNING'), (None, 'PROCESS_QUERY_FAILED')):
                kwargs = {'return_value': rows} if rows else {'side_effect': engine.Refusal(code, 'injected')}
                operations = (
                    lambda: engine.preflight(root / 'fresh', payload, source, releases),
                    lambda: engine.install(root / 'fresh', payload, source, 'vanilla', releases=releases),
                    lambda: engine.install(home, payload, releases=releases),
                    lambda: engine.repair(home, payload, releases=releases),
                    lambda: engine.uninstall(home, releases=releases),
                    lambda: engine.uninstall(home, check_only=True, releases=releases),
                    lambda: engine.uninstall(home, remove_user_data=True, confirm=str(home), releases=releases))
                for index, operation in enumerate(operations):
                    with self.subTest(code=code, operation=index), patch.object(engine, '_process_snapshot', **kwargs):
                        with self.assertRaises(engine.Refusal) as exc:
                            operation()
                        self.assertEqual(exc.exception.code, code)
                        self.assertEqual(before, {p.relative_to(home).as_posix(): p.read_bytes()
                                                  for p in home.rglob('*') if p.is_file()})
                        self.assertFalse((root / 'fresh').exists())

    def test_real_hidden_query_own_pid(self):
        self.assertTrue(engine.process_alive(os.getpid()))
        self.assertTrue(engine._process_snapshot())


if __name__ == '__main__':
    unittest.main(verbosity=2)
