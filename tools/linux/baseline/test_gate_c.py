#!/usr/bin/env python3
"""Offline fixture tests only; mock Podman never builds/pulls/runs an actual image."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('gate_c_update', HERE/'gate_c_update.py')
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)
SHELL = shutil.which('sh') or (r'C:\Program Files\Git\bin\bash.exe' if os.name == 'nt' else None)


def package_at(folder):
    folder.mkdir()
    for n in (*update.PAYLOAD, 'gate_c_update.py'):
        target = folder/('apply_update.py' if n == 'gate_c_update.py' else n)
        target.write_bytes((HERE/n).read_bytes().replace(b'\r\n', b'\n'))
    m = {'format':'R3HD_GATE_C_COMMENTS_V1', 'original_containerfile':update.OLD_RECIPE,
         'ubuntu_sources':update.SOURCES, 'payload':{n:update.sha((folder/n).read_bytes()) for n in update.PAYLOAD}}
    (folder/'UPDATE.json').write_text(json.dumps(m))


class GateCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        override = os.environ.get('R3HD_TEST_OLD_RECIPE')
        cls.old = (Path(override).read_bytes() if override else subprocess.check_output(
            ['git','show','45d8eb3:tools/linux/baseline/Containerfile'],cwd=ROOT))
        assert update.sha(cls.old) == update.OLD_RECIPE
        # This updater's acceptance gate intentionally models the historical HTTP recipe.
        cls.old_sources = (HERE/'ubuntu.sources').read_bytes().replace(b'https://',b'http://').replace(b'\r\n',b'\n')
        assert update.sha(cls.old_sources) == update.SOURCES

    def fixture(self, root):
        apt = root/'etc/apt'
        (apt/'sources.list.d').mkdir(parents=True)
        (apt/'sources.list.d/ubuntu.sources').write_bytes((HERE/'ubuntu.sources').read_bytes().replace(b'\r\n',b'\n'))
        return apt

    def validate(self, root, env=None):
        return subprocess.run([SHELL, (HERE/'validate_apt_sources.sh').as_posix(), root.as_posix()],
                              env=env, capture_output=True, text=True)

    def test_comment_only_legacy_and_absent_empty(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); apt = self.fixture(root)
            for content in (None, '', '# Ubuntu now uses deb822 .sources files\n  # comment\n\t# comment\n \t\n# no newline'):
                if content is not None:
                    (apt/'sources.list').write_text(content)
                result = self.validate(root)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn('R3HD_APT_SOURCES PASS', result.stdout)

    def test_active_legacy_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); apt=self.fixture(root)
            for content in ('deb http://archive.ubuntu.com/ubuntu noble main\n',
                            '# comment\n deb http://snapshot.ubuntu.com/ubuntu/20261108T000000Z/ noble main',
                            'deb-src http://example.invalid noble main', 'Types: deb\n'):
                (apt/'sources.list').write_text(content)
                self.assertEqual(self.validate(root).returncode,2)

    def test_extra_sources_and_snapshot_edits_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); apt=self.fixture(root); parts=apt/'sources.list.d'
            for name in ('extra.list','extra.sources','.hidden','ubuntu.sources.save'):
                p=parts/name; p.write_text('# even inert unexpected files need review\n')
                self.assertEqual(self.validate(root).returncode,2,name); p.unlink()
            source=parts/'ubuntu.sources'; original=source.read_bytes()
            for content in (original.replace(b'snapshot.ubuntu.com',b'archive.ubuntu.com'),
                            original+b'Trusted: yes\n', original+b'URIs: http://example.invalid/\n',
                            original.replace(b'Signed-By:',b'Other-Key:'), b''):
                source.write_bytes(content)
                self.assertEqual(self.validate(root).returncode,2)
            source.unlink()
            self.assertEqual(self.validate(root).returncode,2)

    @unittest.skipIf(os.name == 'nt', 'real POSIX symlink coverage runs under WSL')
    def test_symlinks_and_environment_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); apt=self.fixture(root); source=apt/'sources.list.d/ubuntu.sources'
            original=source.read_bytes(); source.unlink()
            (root/'original.sources').write_bytes(original)
            source.symlink_to(root/'original.sources')
            self.assertEqual(self.validate(root).returncode,2)
            source.unlink(); source.write_bytes(original)
            (apt/'sources.list').symlink_to(root/'missing')
            self.assertEqual(self.validate(root).returncode,2)
            (apt/'sources.list').unlink()
            env=dict(os.environ,APT_CONFIG='/unreviewed')
            self.assertEqual(self.validate(root,env).returncode,2)

    def make_task(self, task):
        (task/'recipe').mkdir(parents=True); (task/'evidence').mkdir()
        (task/'recipe/Containerfile').write_bytes(self.old)
        (task/'recipe/ubuntu.sources').write_bytes(self.old_sources)
        (task/'evidence/image-build.log').write_bytes(b'original STEP 4 failure\n')
        (task/'evidence/build-image.id').write_bytes(b'preserve partial ID\n')
        (task/'sdk-sentinel').write_bytes(b'untouched SDK stand-in')

    def test_update_integrity_local_edits_and_preservation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); task=root/'task'; self.make_task(task)
            package=root/'package'; package_at(package)
            for n in ('Containerfile','ubuntu.sources'):
                p=task/'recipe'/n; old=p.read_bytes(); p.write_bytes(old+b'# local edit\n')
                with self.assertRaises(ValueError): update.apply(task,package)
                self.assertFalse((task/'evidence'/update.BACKUP).exists()); p.write_bytes(old)
            script=package/'validate_apt_sources.sh'; old=script.read_bytes(); script.write_bytes(b'corrupt')
            with self.assertRaises(ValueError): update.apply(task,package)
            script.write_bytes(old)
            with contextlib.redirect_stdout(io.StringIO()): update.apply(task,package)
            self.assertEqual((task/'evidence'/update.BACKUP/'Containerfile').read_bytes(),self.old)
            self.assertEqual((task/'evidence/image-build.log').read_bytes(),b'original STEP 4 failure\n')
            self.assertEqual((task/'evidence/build-image.id').read_bytes(),b'preserve partial ID\n')
            self.assertEqual((task/'sdk-sentinel').read_bytes(),b'untouched SDK stand-in')
            with self.assertRaises(ValueError): update.apply(task,package)

    @unittest.skipIf(os.name == 'nt', 'mock engine procedure runs under real Linux shell in WSL')
    def test_resume_with_mock_engine(self):
        for mode in ('success','build-failure','tag-collision'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as td:
                root=Path(td); task=root/'Projects/R3HD-baseline-noble-01'; self.make_task(task)
                package=root/'package'; package_at(package)
                with contextlib.redirect_stdout(io.StringIO()): update.apply(task,package)
                transfer=root/'Downloads/r3hd-baseline-2a'; transfer.mkdir(parents=True)
                (transfer/'preflight.py').write_text('print(\'{"status":"STATIC_PREFLIGHT_PASS","synthetic":true}\')\n')
                bins=root/'bin'; bins.mkdir()
                (bins/'id').write_text('#!/bin/sh\nprintf "1000\\n"\n'); (bins/'id').chmod(0o755)
                mock = '''#!PYTHON
import json,os,sys
from pathlib import Path
a=sys.argv[1:]
with open(os.environ['MOCK_LOG'],'a') as f: f.write(json.dumps(a)+'\\n')
mode=os.environ['MOCK_MODE']
if a[:2]==['image','exists']: sys.exit(0 if mode=='tag-collision' else 1)
if a[:2]==['image','inspect']: print(json.dumps([{'Architecture':'amd64','Os':'linux'}]))
elif a and a[0]=='build':
 if mode=='build-failure': sys.exit(42)
 Path(a[a.index('--iidfile')+1]).write_text('sha256:'+'a'*64+'\\n')
elif a and a[0]=='save': Path(a[a.index('--output')+1]).write_bytes(b'SYNTHETIC OCI PLACEHOLDER')
'''.replace('PYTHON',sys.executable)
                (bins/'podman').write_text(mock); (bins/'podman').chmod(0o755)
                env=dict(os.environ, HOME=str(root), PATH=str(bins)+os.pathsep+os.environ['PATH'],
                         MOCK_LOG=str(root/'calls.jsonl'), MOCK_MODE=mode)
                result=subprocess.run(['bash',str(package/'resume_gate_c.sh')],env=env,capture_output=True,text=True)
                calls=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
                self.assertFalse(any(a[0] in ('rm','rmi','prune','pull','run','stop','system') for a in calls))
                self.assertEqual((task/'evidence/image-build.log').read_bytes(),b'original STEP 4 failure\n')
                self.assertEqual((task/'evidence/build-image.id').read_bytes(),b'preserve partial ID\n')
                if mode=='success':
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertIn('R3HD_BASELINE_GATE_C_IMAGE PASS',result.stdout)
                    build=next(a for a in calls if a[0]=='build')
                    self.assertTrue(all(x in build for x in ('--pull=never','--no-cache','--rm=false')))
                else:
                    self.assertNotEqual(result.returncode,0)
                    self.assertNotIn('R3HD_BASELINE_GATE_C_IMAGE PASS',result.stdout)
                    self.assertFalse(any(a[0]=='save' for a in calls))


if __name__=='__main__':
    unittest.main()
