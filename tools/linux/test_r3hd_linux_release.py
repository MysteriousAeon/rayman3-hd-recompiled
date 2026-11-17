"""Synthetic archive tests only. No compiler, game, desktop, network or installation."""
import copy
import gzip
import io
import json
from pathlib import Path
import struct
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_linux_release as R
P = R.P


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.lock = copy.deepcopy(R.policy())
        # Private fixture tree contains synthetic binaries and copies of license/help text only.
        for rel in self.lock['replacements'].values():
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((R.ROOT / rel).read_bytes())
        for row in self.lock['license_additions'].values():
            dest = self.root / row['source']
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((R.ROOT / row['source']).read_bytes())
        source_files = {'README.txt': b'Synthetic source fixture, never compiled.\n'}
        man = {'platform': 'linux-x86_64', 'program_version': self.lock['version'],
               'components': {k: {'commit': v} for k, v in self.lock['lgpl']['commits'].items()},
               'files': {n: P.digest(b) for n, b in source_files.items()}}
        self.source = self.root / self.lock['lgpl']['archive']
        with zipfile.ZipFile(self.source, 'x') as z:
            for n, b in {**source_files, 'MANIFEST.json': R.encoded(man)}.items():
                z.writestr('r3hd-lgpl-source/' + n, b)
        self.lock['lgpl'].update({'files': 1, 'bytes': self.source.stat().st_size,
                                 'sha256': P.digest(self.source.read_bytes())})
        self.lock['original_portable_core']['lgpl']['corresponding_source'] = {
            k: self.lock['lgpl'][k] for k in ('archive', 'sha256', 'files', 'commits')}
        self.files = {}
        for n in self.lock['original_files']:
            if n in ('portable.json', 'payload.json'):
                continue
            if n in P.BINARIES:
                b = bytearray(64)
                b[:6] = b'\x7fELF\x02\x01'
                struct.pack_into('<HH', b, 16, 3, 62)
                self.files[n] = bytes(b) + n.encode()
            elif n.startswith('app/icons/'):
                self.files[n] = b'\x89PNG\r\n\x1a\nfixture'
            elif n in P.EXECUTABLE:
                self.files[n] = b'#!/bin/sh\nexit 99\n'
            else:
                self.files[n] = ('Original fixture ' + n + '\n').encode()
        entries = {n: {**v, 'role': 'native' if n in P.BINARIES else 'app'}
                   for n, v in R.inventory(self.files).items() if n not in ('Play.sh', 'Settings.sh')}
        payload = {**self.lock['original_payload_core'], 'files': entries, 'payload_id': R.payload_id(entries)}
        self.files['payload.json'] = P.encoded(payload)
        portable = {**self.lock['original_portable_core'], 'files': R.inventory(self.files), 'payload_id': payload['payload_id']}
        self.files['portable.json'] = P.encoded(portable)
        self.lock['original_files'] = R.inventory(self.files)
        self.input = self.root / 'original.tar.gz'
        self.input.write_bytes(R.pack(self.files))
        self.lock['input_archive'] = {'bytes': self.input.stat().st_size, 'sha256': P.digest(self.input.read_bytes())}
        self.policy_file = self.root / 'policy.json'
        self.policy_file.write_bytes(R.encoded(self.lock))
        self.patches = [patch.object(R, 'policy', lambda: copy.deepcopy(self.lock)),
                        patch.object(R, 'ROOT', self.root), patch.object(R, 'POLICY', self.policy_file),
                        patch.object(R, 'key_boundary', return_value=P.KEY_BOUNDARY),
                        patch.object(P, 'build', side_effect=AssertionError('NO BUILD ALLOWED'))]
        for p in self.patches:
            p.start()
        self.out = self.root / 'rc1'

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def promote(self):
        return R.promote(self.input, self.source, self.out)

    def reseal(self, files):
        payload = R.strict(files['payload.json'])
        payload['files'] = {n: {**v, 'role': 'native' if n in P.BINARIES else 'app'}
                            for n, v in R.inventory(files).items()
                            if n not in ('Play.sh', 'Settings.sh', 'payload.json', 'portable.json')}
        payload['payload_id'] = R.payload_id(payload['files'])
        files['payload.json'] = P.encoded(payload)
        portable = R.strict(files['portable.json'])
        portable['payload_id'] = payload['payload_id']
        portable['files'] = {n: v for n, v in R.inventory(files).items() if n != 'portable.json'}
        files['portable.json'] = P.encoded(portable)

    def test_complete_promotion_and_all_five_binaries_unchanged(self):
        report = self.promote()
        self.assertEqual(report['result'], 'PASS')
        self.assertTrue(report['publishable'])
        self.assertFalse(report['publication_authorized'])
        self.assertFalse(report['notes_finalized'])
        self.assertEqual(len(report['assets']), 5)
        result = R.unpack((self.out / self.lock['archive']).read_bytes())
        for n in P.BINARIES:
            self.assertEqual(result[n], self.files[n])
        for n in self.files:
            if n not in ('payload.json', 'portable.json') and n not in self.lock['replacements']:
                self.assertEqual(result[n], self.files[n])
        self.assertEqual((self.out / self.source.name).read_bytes(), self.source.read_bytes())
        self.assertEqual(R.audit_directory(self.out), report)

    def test_deterministic_and_no_overwrite(self):
        self.promote()
        out2 = self.root / 'rc2'
        R.promote(self.input, self.source, out2)
        self.assertEqual({p.name: p.read_bytes() for p in self.out.iterdir()},
                         {p.name: p.read_bytes() for p in out2.iterdir()})
        with self.assertRaisesRegex(ValueError, 'output exists'):
            self.promote()
        archive = (self.out / self.lock['archive']).read_bytes()
        self.assertEqual(archive[4:8], b'\0' * 4)  # no wall-clock timestamp
        self.assertFalse(archive[3] & 8)  # no gzip filename

    def test_packaging_provenance_is_independent_of_checkout_line_endings(self):
        first = R.buildinfo(b'synthetic archive', self.lock)
        original = R.stable
        def windows_text(path, *args):
            return original(path, *args).replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        with patch.object(R, 'stable', side_effect=windows_text):
            self.assertEqual(R.buildinfo(b'synthetic archive', self.lock), first)

    def test_wrong_input_refused_before_output(self):
        self.input.write_bytes(self.input.read_bytes() + b'edited')
        with self.assertRaisesRegex(ValueError, 'wrong identity'):
            self.promote()
        self.assertFalse(self.out.exists())

    def test_resealed_changed_binary_and_launcher_are_refused(self):
        public = R.promoted(self.files, self.lock)
        for n in ('bin/r3hd', 'bin/libffmpeg.so', 'Play.sh', 'app/tools/linux/r3hd_play.py'):
            with self.subTest(n=n):
                tampered = dict(public)
                tampered[n] += b'edit'
                self.reseal(tampered)
                with self.assertRaisesRegex(ValueError, 'accepted bytes changed'):
                    R.validate_public(tampered, self.lock)

    def test_unknown_files_settings_saves_and_original_data_refused(self):
        public = R.promoted(self.files, self.lock)
        for name in ('data/content/Default.xex', 'settings.json', 'profiles/test/save', 'sessions/log', 'app/extra'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'inventory'):
                R.validate_public({**public, name: b'fixture'}, self.lock)

    def test_metadata_floor_source_pair_and_flags_cannot_be_resealed(self):
        public = R.promoted(self.files, self.lock)
        mutations = [lambda p: p.update(publishable=False),
                     lambda p: p['requires'].update(glibc='2.17'),
                     lambda p: p['requires'].update(token='untrusted'),
                     lambda p: p.update(extra='/home/' + 'example/private')]
        for change in mutations:
            tampered = dict(public)
            j = R.strict(tampered['payload.json'])
            change(j)
            tampered['payload.json'] = P.encoded(j)
            with self.assertRaisesRegex(ValueError, 'payload differs'):
                R.validate_public(tampered, self.lock)
        for change in [lambda p: p.update(publishable=False),
                       lambda p: p['lgpl']['corresponding_source'].update(sha256='0' * 64),
                       lambda p: p.update(extra='private')]:
            tampered = dict(public)
            j = R.strict(tampered['portable.json'])
            change(j)
            tampered['portable.json'] = P.encoded(j)
            with self.assertRaisesRegex(ValueError, 'portable differs'):
                R.validate_public(tampered, self.lock)

    def test_missing_or_changed_licenses_refused(self):
        public = R.promoted(self.files, self.lock)
        n = next(iter(self.lock['license_additions']))
        for missing in (True, False):
            tampered = dict(public)
            if missing:
                del tampered[n]
            else:
                tampered[n] += b'edit'
            with self.assertRaises(ValueError):
                R.validate_public(tampered, self.lock)
        row = self.lock['license_additions'][n]
        (self.root / row['source']).write_bytes(b'changed pinned input')
        with self.assertRaisesRegex(ValueError, 'pinned license differs'):
            self.promote()
        self.assertFalse(self.out.exists())

    def test_wrong_lgpl_source_refused(self):
        self.source.write_bytes(self.source.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'source identity'):
            self.promote()
        self.assertFalse(self.out.exists())

    def test_unsafe_archive_modes_links_duplicate_paths_refused(self):
        for name, mode, kind in [('Rayman3HDRecompiled-Linux/../escape', 0o644, tarfile.REGTYPE),
                                 ('Rayman3HDRecompiled-Linux/Play.sh', 0o4755, tarfile.REGTYPE),
                                 ('Rayman3HDRecompiled-Linux/link', 0o644, tarfile.SYMTYPE)]:
            b = io.BytesIO()
            with tarfile.open(fileobj=b, mode='w:gz') as t:
                info = tarfile.TarInfo(name)
                info.mode, info.type = mode, kind
                t.addfile(info, io.BytesIO())
            with self.assertRaises(ValueError):
                R.unpack(b.getvalue())
        b = io.BytesIO()
        with tarfile.open(fileobj=b, mode='w:gz') as t:
            for _ in range(2):
                info = tarfile.TarInfo(P.TOP + '/same')
                info.mtime = P.MTIME
                t.addfile(info, io.BytesIO())
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            R.unpack(b.getvalue())

    def test_exact_final_asset_set_and_checksums(self):
        self.promote()
        (self.out / 'SHA256SUMS.txt').write_text('bad')
        with self.assertRaisesRegex(ValueError, 'metadata/checksums'):
            R.audit_directory(self.out)
        (self.out / 'save.dat').write_bytes(b'private')
        with self.assertRaisesRegex(ValueError, 'directory inventory'):
            R.audit_directory(self.out)

    def test_key_boundary_and_text_privacy_remain_enforced(self):
        with patch.object(R, 'key_boundary', return_value={}):
            with self.assertRaisesRegex(ValueError, 'key boundary'):
                self.promote()
        n = 'app/README-LINUX.txt'
        self.lock['replacements'][n] = 'private.txt'
        (self.root / 'private.txt').write_text('Developer /home/' + 'example/private/secret')
        with self.assertRaisesRegex(ValueError, 'privacy/content'):
            self.promote()
        self.assertFalse(self.out.exists())

    def test_private_mode_preserved(self):
        expected = {n: b for n, b in self.files.items()
                    if n not in P.BINARIES and n not in ('Play.sh', 'Settings.sh', 'payload.json', 'portable.json')}
        with patch.object(P, 'definition_files', return_value=({'version': '1.1.0'}, expected)), \
             patch.object(P, 'key_hits', return_value=P.KEY_BOUNDARY):
            self.assertFalse(P.check(self.input)['publishable'])
            public = self.root / 'public.tar.gz'
            public.write_bytes(R.pack(R.promoted(self.files, self.lock)))
            with self.assertRaises(ValueError):
                P.check(public)

    def test_duplicate_json_and_unmatched_original_files(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            R.strict(b'{"publishable":true,"publishable":false}')
        bad = dict(self.files)
        bad['Play.sh'] += b'edit'
        with self.assertRaisesRegex(ValueError, 'canonical Noble'):
            R.promoted(bad, self.lock)

    def test_public_cli_requires_explicit_mode_and_source(self):
        from contextlib import redirect_stderr, redirect_stdout
        for args in [('promote', str(self.input), '--lgpl-source', str(self.source), '--out', str(self.out)),
                     ('check', str(self.input), '--public-release')]:
            with patch.object(sys, 'argv', ['package'] + list(args)), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                if args[0] == 'promote':
                    with self.assertRaises(SystemExit) as e:
                        P.main()
                    self.assertEqual(e.exception.code, 2)
                else:
                    self.assertEqual(P.main(), 2)
        self.assertFalse(self.out.exists())

    def test_public_cli_json_contract(self):
        from contextlib import redirect_stderr, redirect_stdout
        stdout, stderr = io.StringIO(), io.StringIO()
        args = ['package', 'promote', str(self.input), '--lgpl-source', str(self.source),
                '--out', str(self.out), '--public-release']
        with patch.object(sys, 'argv', args), redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(P.main(), 0)
        self.assertTrue(json.loads(stdout.getvalue())['publishable'])
        self.assertEqual(stderr.getvalue(), 'R3HD_LINUX_PACKAGE PASS\n')

    def test_unchanged_portable_engine_accepts_public_manifest_and_lgpl_replacement(self):
        import r3hd_portable as Q
        files = R.promoted(self.files, self.lock)
        home = self.root / 'synthetic-portable'
        for n, b in files.items():
            dest = home / n
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b)
        with patch.object(Q, 'LINUX', True), \
             patch.object(Q, 'REPLACEABLE_LGPL', frozenset(('bin/libffmpeg.so', 'bin/libmspack.so'))), \
             patch.object(Q.subprocess, 'Popen', side_effect=AssertionError('NO PROCESS ALLOWED')):
            self.assertEqual(Q.check_files(home)['version'], '1.1.0')
            ffmpeg = home / 'bin/libffmpeg.so'
            ffmpeg.write_bytes(ffmpeg.read_bytes() + b'synthetic compatible replacement')
            self.assertEqual(Q.check_files(home)['version'], '1.1.0')
        files['bin/libffmpeg.so'] = ffmpeg.read_bytes()
        with self.assertRaisesRegex(ValueError, 'accepted bytes changed'):
            R.validate_public(files, self.lock)

    def test_truncated_gzip_and_source_manifest_tampering(self):
        bad = self.root / self.lock['archive']
        bad.write_bytes(b'\x1f\x8b\x08')
        with self.assertRaisesRegex(ValueError, 'gzip header'):
            R.check_public(bad, self.source)
        with zipfile.ZipFile(self.source) as z:
            data = {n: z.read(n) for n in z.namelist()}
        data['r3hd-lgpl-source/README.txt'] = b'tampered source'
        with zipfile.ZipFile(self.source, 'w') as z:
            for n, b in data.items():
                z.writestr(n, b)
        self.lock['lgpl']['bytes'] = self.source.stat().st_size
        self.lock['lgpl']['sha256'] = P.digest(self.source.read_bytes())
        with self.assertRaisesRegex(ValueError, 'LGPL file hash'):
            R.source_archive(self.source, self.lock)

    def test_hidden_trailing_data_and_crc_refused(self):
        public = R.promoted(self.files, self.lock)
        raw = R.pack(public)
        bad = self.root / self.lock['archive']
        cases = [raw + b'private trailing bytes', raw + raw,
                 gzip.compress(R.tar_bytes(public) + b'private trailing tar bytes', mtime=0),
                 raw[:-8] + bytes([raw[-8] ^ 1]) + raw[-7:]]
        for data in cases:
            bad.write_bytes(data)
            with self.assertRaises(ValueError):
                R.check_public(bad, self.source)


if __name__ == '__main__':
    unittest.main()
