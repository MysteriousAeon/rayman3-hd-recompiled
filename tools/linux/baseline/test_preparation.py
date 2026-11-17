#!/usr/bin/env python3
"""Host-safe synthetic tests. No Podman, SDK replay, Linux host inspection or compilation."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p = load('prepare')
f = load('preflight')


class PreparationTests(unittest.TestCase):
    def test_arch_dropin_acceptance_and_rejections(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            configs = [root/p/'containers.conf' for p in ('vendor', 'system', 'user')]
            approved = configs[0].parent/'containers.conf.d/00-containers-arch.conf'
            approved.parent.mkdir(parents=True)
            good = '[containers]\nlog_driver = "journald"\n\n[network]\nfirewall_driver = "nftables"\n'
            approved.write_text(good)
            temp, records = f.containers_configuration(configs, approved)
            self.assertEqual(temp, '/var/tmp')
            self.assertEqual(records[str(approved)], f.ARCH_SETTINGS)
            bad_contents = [good.replace('journald', 'k8s-file'), good.replace('nftables', 'iptables'),
                            good+'\n[engine]\nimage_copy_tmp_dir="/other"\n',
                            good+'\n[storage]\ngraphroot="/other"\n',
                            good.replace('[network]', 'extra = true\n[network]'),
                            good+'\n[containers]\nlog_driver="journald"\n',
                            good.replace('[network]', 'log_driver="journald"\n[network]'),
                            '[containers]\nlog_driver="journald"\n', 'invalid TOML !!!']
            for contents in bad_contents:
                with self.subTest(contents=contents):
                    approved.write_text(contents)
                    with self.assertRaises(ValueError):
                        f.containers_configuration(configs, approved)
            approved.write_text(good)
            for conf in configs:
                conf.parent.mkdir(parents=True, exist_ok=True)
                conf.write_text('[containers]\nlog_driver="journald"\n')
                with self.subTest(duplicate=str(conf)), self.assertRaises(ValueError):
                    f.containers_configuration(configs, approved)
                conf.unlink()
            for directory in (approved.parent, configs[1].parent/'containers.conf.d',
                              configs[2].parent/'containers.conf.d'):
                directory.mkdir(parents=True, exist_ok=True)
                for filename in ('unexpected.conf', '.hidden', '00-containers-arch.conf' if directory != approved.parent else 'extra.txt'):
                    extra = directory/filename
                    extra.write_text(good)
                    with self.subTest(extra=str(extra)), self.assertRaises(ValueError):
                        f.containers_configuration(configs, approved)
                    extra.unlink()
            approved.unlink()
            self.assertEqual(f.containers_configuration(configs, approved), ('/var/tmp', {}))
            configs[0].write_text('[engine]\nimage_copy_tmp_dir="/var/tmp"\n')
            configs[1].write_text('[engine]\nimage_copy_tmp_dir="/other"\n')
            with self.assertRaises(ValueError):
                f.containers_configuration(configs, approved)

    def test_arch_dropin_symlinks_and_structural_conflicts(self):
        with tempfile.TemporaryDirectory() as td:
            conf = Path(td)/'containers.conf'
            approved = Path(td)/'containers.conf.d/00-containers-arch.conf'
            approved.parent.mkdir()
            approved.write_text('[containers]\nlog_driver="journald"\n[network]\nfirewall_driver="nftables"\n')
            original = Path.is_symlink
            for bad in (approved, approved.parent):
                with patch.object(Path, 'is_symlink', lambda p: p == bad or original(p)):
                    with self.assertRaises(ValueError):
                        f.containers_configuration([conf], approved)
            conf.write_text('containers="conflicting scalar"\n')
            with self.assertRaises(ValueError):
                f.containers_configuration([conf], approved)

    def test_preflight_update_guards_and_backup(self):
        update = load('preflight_update')
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target, package = root/'transfer', root/'package'
            target.mkdir(); package.mkdir()
            for name in update.NAMES:
                (target/name).write_bytes(('old '+name).encode())
            (target/'diagnostics.json').write_bytes(b'preserve unknown file')
            checksums = ''.join(update.digest(target/n)+'  '+n+'\n' for n in update.NAMES).encode()
            (target/'SHA256SUMS').write_bytes(checksums)
            original = update.digest(target/'SHA256SUMS')
            for n in ('preflight.py','HANDOFF.md'):
                (package/n).write_bytes(('new '+n).encode())
            manifest = {'format':'R3HD_PREFLIGHT_ARCH_UPDATE_V1', 'original_checksums_sha256':original,
                        'replacement':{n:update.digest(package/n) for n in ('preflight.py','HANDOFF.md')}}
            (package/'UPDATE.json').write_text(json.dumps(manifest))
            with patch.object(update, 'ORIGINAL_SUMS', original):
                (package/'preflight.py').write_bytes(b'corrupt update')
                with self.assertRaises(ValueError):
                    update.apply(target,package)
                self.assertFalse((target/update.BACKUP).exists())
                (package/'preflight.py').write_bytes(b'new preflight.py')
                (target/'prepare.py').write_bytes(b'corrupt original')
                with self.assertRaises(ValueError):
                    update.apply(target,package)
                self.assertFalse((target/update.BACKUP).exists())
                (target/'prepare.py').write_bytes(b'old prepare.py')
                with contextlib.redirect_stdout(io.StringIO()):
                    update.apply(target,package)
                self.assertEqual((target/update.BACKUP/'SHA256SUMS').read_bytes(), checksums)
                self.assertEqual((target/update.BACKUP/'preflight.py').read_bytes(), b'old preflight.py')
                self.assertEqual((target/'preflight.py').read_bytes(), b'new preflight.py')
                self.assertEqual((target/'diagnostics.json').read_bytes(), b'preserve unknown file')
                self.assertEqual((target/'r3hd-baseline-2a.tar.gz').read_bytes(), b'old r3hd-baseline-2a.tar.gz')
                for n,h in update.sums_map((target/'SHA256SUMS').read_bytes()).items():
                    self.assertEqual(update.digest(target/n),h)
                with self.assertRaises(ValueError):
                    update.apply(target,package)

    def test_safe_paths(self):
        for name in ('/etc/passwd', '../bad', 'x/../../bad', 'C:/bad', 'x\\y', './x'):
            with self.assertRaises(ValueError):
                p.safe_name(name)
        p.safe_name('work/private/lma/rex_lma/generated/default/sources.cmake')

    def test_links(self):
        p.safe_link('work/sdk/mspack/link.c', '../real.c')
        for link in ('../../../../bad', '/etc/passwd', 'C:/bad'):
            with self.assertRaises(ValueError):
                p.safe_link('work/link', link)

    def test_archive_corruption_inventory_and_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td)/'fixture.tar.gz'
            def write(extra=False, corrupt=False, duplicate=False):
                with tarfile.open(archive, 'w:gz') as t:
                    w = p.Writer(t)
                    w.add('work/source.txt', b'fixture')
                    manifest = dict(w.entries)
                    if corrupt:
                        manifest['work/source.txt']['sha256'] = '0'*64
                    w.add('KIT_MANIFEST.json', json.dumps({'format':'R3HD_BASELINE_2A_V1', 'entries':manifest}).encode())
                    if extra:
                        w.add('unlisted.txt', b'bad')
                    if duplicate:
                        m = tarfile.TarInfo('work/source.txt')
                        m.size = 1
                        t.addfile(m, io.BytesIO(b'x'))
            write()
            with contextlib.redirect_stdout(io.StringIO()):
                p.verify(archive)
            for args in ({'extra':True}, {'corrupt':True}, {'duplicate':True}):
                write(**args)
                with self.assertRaises(ValueError):
                    p.verify(archive)

    def test_subordinate_ids(self):
        self.assertEqual(f.allocation('alice:100000:65536\nbob:200000:65536', 'alice', 1000), [('alice',100000,65536)])
        for text in ('', 'alice:100000:1', 'alice:100000:65536\nbob:120000:65536', 'alice:1000:65536'):
            with self.assertRaises(ValueError):
                f.allocation(text, 'alice', 1000)

    def test_shared_disk_count_once(self):
        row = {'source':'/dev/test[/home]', 'uuid':'fixture', 'fstype':'btrfs',
               'options':'rw,relatime', 'available_bytes':50_000_000_000}
        self.assertIn('minimum', f.check_storage([row]*3))
        for other in (dict(row, available_bytes=49_999_999_999), dict(row, uuid='different'),
                      dict(row, fstype='nfs'), dict(row, options='ro')):
            with self.assertRaises(ValueError):
                f.check_storage([row, other])

    def test_wrong_host_stops_before_inspection(self):
        with patch.object(f.platform, 'system', return_value='Windows'), \
             patch.object(f.subprocess, 'run', side_effect=AssertionError('must not inspect Linux')), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(f.main(), 2)
        self.assertEqual(json.loads(output.getvalue())['status'], 'STOP')

    def test_single_commit_git_export(self):
        # Tiny throwaway repository: no reads/writes to shared SDK or build outputs.
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)/'repo'
            repo.mkdir()
            p.git(repo, 'init', '--quiet')
            (repo/'sample.txt').write_bytes(b'pristine\n')
            p.git(repo, 'add', 'sample.txt')
            p.git(repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
            pin = p.git(repo, 'rev-parse', 'HEAD').decode().strip()
            (repo/'sample.txt').write_bytes(b'dirty ignored\n')
            archive = Path(td)/'sdk.tar'
            with tarfile.open(archive, 'w') as t:
                writer = p.Writer(t)
                identities = {}
                p.sdk_export(writer, repo, pin, 'sdk/', identities)
            with tarfile.open(archive) as t:
                self.assertEqual(t.extractfile('sdk/sample.txt').read(), b'pristine\n')
                # Only test-owned regular files; no synthetic symlinks here.
                dest = Path(td)/'extract'
                for member in t:
                    target = dest/member.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(t.extractfile(member).read())
            target = dest/'sdk'
            p.git(target, 'read-tree', 'HEAD')
            p.git(target, 'fsck', '--connectivity-only', '--no-reflogs')
            self.assertEqual(p.git(target, 'status', '--porcelain'), b'')
            self.assertEqual(identities, {'sdk':pin})


if __name__ == '__main__':
    unittest.main()
