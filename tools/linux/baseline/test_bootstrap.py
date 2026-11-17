#!/usr/bin/env python3
"""Offline E-388 tests; require private authenticated bootstrap_audit inputs. No installs."""
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

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('bootstrap_update',HERE/'bootstrap_update.py')
u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
AUDIT=ROOT/'private/work/linux_build/bootstrap_audit'


def package_at(p):
    p.mkdir();recipe=u.inputs()
    for n,b in recipe.items():
        f=p/n;f.parent.mkdir(exist_ok=True);f.write_bytes(b)
    for n in ('resume_gate_c_tls.sh','BOOTSTRAP_LOCK.json'):
        (p/n).write_bytes((HERE/n).read_bytes().replace(b'\r\n',b'\n'))
    (p/'apply_update.py').write_bytes((HERE/'bootstrap_update.py').read_bytes().replace(b'\r\n',b'\n'))
    m={'format':'R3HD_GATE_C_TLS_V1','before':u.OLD,'recipe':{n:u.sha(b) for n,b in recipe.items()},
       'extra':{n:u.sha((p/n).read_bytes()) for n in ('resume_gate_c_tls.sh','BOOTSTRAP_LOCK.json')}}
    (p/'UPDATE.json').write_text(json.dumps(m))


class BootstrapTests(unittest.TestCase):
    def fixture(self,p):
        s=p/'opt/r3hd-bootstrap';s.mkdir(parents=True)
        k=p/'usr/share/keyrings';k.mkdir(parents=True)
        shutil.copyfile(AUDIT/'base/usr/share/keyrings/ubuntu-archive-keyring.gpg',k/'ubuntu-archive-keyring.gpg')
        for _,(src,_) in u.DATA.items():
            name={'noble-updates.InRelease':'InRelease','noble-updates-main.Packages.gz':'Packages.gz'}.get(src,src)
            shutil.copyfile(AUDIT/src,s/name)
        return s

    @unittest.skipIf(os.name=='nt','real gpgv/dpkg-deb execution covered in WSL')
    def test_actual_signature_index_package_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);self.fixture(p)
            r=subprocess.run(['sh',str(HERE/'bootstrap_apt.sh'),str(p)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('R3HD_CA_BOOTSTRAP PASS',r.stdout)
            lock=json.loads((HERE/'BOOTSTRAP_LOCK.json').read_text())
            self.assertEqual(u.sha((p/'opt/r3hd-bootstrap/ca-bundle.crt').read_bytes()),lock['bundle_sha256'])
            self.assertEqual((p/'opt/r3hd-bootstrap/ca-bundle.crt').stat().st_mode & 0o777,0o644)
            self.assertEqual((p/'opt/r3hd-bootstrap').stat().st_mode & 0o777,0o755)
            self.assertFalse((p/'etc/ssl').exists()) # no system CA installation/registration

    @unittest.skipIf(os.name=='nt','real shell validation covered in WSL')
    def test_tampered_inputs_and_stale_bundle(self):
        for name in ('InRelease','Packages.gz','ca-certificates.deb','keyring','existing-bundle'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as td:
                p=Path(td);seed=self.fixture(p)
                target=(p/'usr/share/keyrings/ubuntu-archive-keyring.gpg' if name=='keyring' else
                        seed/('ca-bundle.crt' if name=='existing-bundle' else name))
                target.write_bytes(b'untrusted')
                r=subprocess.run(['sh',str(HERE/'bootstrap_apt.sh'),str(p)],capture_output=True,text=True)
                self.assertNotEqual(r.returncode,0)
                self.assertFalse((seed/'extracted').exists())

    @unittest.skipIf(os.name=='nt','shell snapshot proof covered in WSL')
    def test_snapshot_release_hash_guard(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);lists=p/'var/lib/apt/lists';lists.mkdir(parents=True)
            for s in ('noble','noble-updates','noble-security'):
                shutil.copyfile(AUDIT/(s+'.InRelease'),lists/('snapshot.ubuntu.com_ubuntu_20261108T000000Z_dists_'+s+'_InRelease'))
            run=lambda:subprocess.run(['sh',str(HERE/'validate_snapshot_lists.sh'),str(p)],capture_output=True,text=True)
            self.assertEqual(run().returncode,0)
            next(lists.iterdir()).write_bytes(b'different signed snapshot is not this snapshot')
            self.assertNotEqual(run().returncode,0)

    def test_update_integrity_local_edit_backup_preservation(self):
        # Historical E-387 bytes come from its already sealed private update; never regenerate them.
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);task=p/'task';recipe=task/'recipe';recipe.mkdir(parents=True);(task/'evidence').mkdir()
            with zipfile.ZipFile(ROOT/'private/work/linux_build/baseline_gate_c_update/r3hd-stage2a-gate-c-update.zip') as z:
                for n in ('Containerfile','validate_apt_sources.sh'):(recipe/n).write_bytes(z.read(n))
            (recipe/'ubuntu.sources').write_bytes((HERE/'ubuntu.sources').read_bytes().replace(b'https://',b'http://').replace(b'\r\n',b'\n'))
            (task/'evidence/old-tls-failure.log').write_bytes(b'preserve exit 100')
            package=p/'package';package_at(package)
            file=recipe/'Containerfile';old=file.read_bytes();file.write_bytes(old+b'# local edit')
            with self.assertRaises(ValueError):u.apply(task,package)
            self.assertFalse((task/'evidence'/u.BACKUP).exists());file.write_bytes(old)
            seed=package/'bootstrap/ca-certificates.deb';oldseed=seed.read_bytes();seed.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):u.apply(task,package)
            seed.write_bytes(oldseed)
            with contextlib.redirect_stdout(io.StringIO()):u.apply(task,package)
            self.assertEqual((task/'evidence'/u.BACKUP/'Containerfile').read_bytes(),old)
            self.assertEqual((task/'evidence/old-tls-failure.log').read_bytes(),b'preserve exit 100')
            with self.assertRaises(ValueError):u.apply(task,package)

    def test_no_tls_or_signature_bypass_and_order(self):
        text=(HERE/'Containerfile').read_text()
        self.assertLess(text.index('sh /opt/r3hd-bootstrap-apt.sh'),text.index('update --error-on=any'))
        self.assertLess(text.index('ca-certificates=20260816ubuntu0.24.04.2'),text.index('test -s /etc/ssl/certs/ca-certificates.crt'))
        for bad in ('Verify-Peer=false','Verify-Host=false','allow-unauthenticated','AllowInsecureRepositories=true'):
            self.assertNotIn(bad,text)

    @unittest.skipIf(os.name=='nt','mock-engine resume runs under WSL')
    def test_tls_resume_mock_failure_and_id_formats(self):
        import zipfile
        for mode in ('success','bare-id','build-failure','invalid-id','collision'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
                root=Path(td);task=root/'Projects/R3HD-baseline-noble-01'
                recipe=task/'recipe';recipe.mkdir(parents=True);(task/'evidence').mkdir()
                with zipfile.ZipFile(ROOT/'private/work/linux_build/baseline_gate_c_update/r3hd-stage2a-gate-c-update.zip') as z:
                    for n in ('Containerfile','validate_apt_sources.sh'):(recipe/n).write_bytes(z.read(n))
                (recipe/'ubuntu.sources').write_bytes((HERE/'ubuntu.sources').read_bytes().replace(b'https://',b'http://').replace(b'\r\n',b'\n'))
                old=task/'evidence/gate-c-comments-01';old.mkdir();(old/'image-build.log').write_bytes(b'old TLS exit100')
                package=root/'package';package_at(package)
                with contextlib.redirect_stdout(io.StringIO()):u.apply(task,package)
                transfer=root/'Downloads/r3hd-baseline-2a';transfer.mkdir(parents=True)
                (transfer/'preflight.py').write_text('print(\'{"synthetic":true,"status":"STATIC_PREFLIGHT_PASS"}\')\n')
                bins=root/'bin';bins.mkdir()
                (bins/'id').write_text('#!/bin/sh\nprintf "1000\\n"\n');(bins/'id').chmod(0o755)
                script='''#!PYTHON
import sys,os,json
from pathlib import Path
a=sys.argv[1:];mode=os.environ['MOCK_MODE']
with open(os.environ['MOCK_LOG'],'a') as f:f.write(json.dumps(a)+'\\n')
if a[:2]==['image','exists']:sys.exit(0 if mode=='collision' else 1)
if a[:2]==['image','inspect']:print(json.dumps([{'Architecture':'amd64','Os':'linux'}]))
elif a and a[0]=='build':
 if mode=='build-failure':sys.exit(42)
 value=('b'*64 if mode=='bare-id' else 'invalid' if mode=='invalid-id' else 'sha256:'+'b'*64)
 Path(a[a.index('--iidfile')+1]).write_text(value)
elif a and a[0]=='save':Path(a[a.index('--output')+1]).write_bytes(b'MOCK OCI ONLY')
'''.replace('PYTHON',sys.executable)
                (bins/'podman').write_text(script);(bins/'podman').chmod(0o755)
                env=dict(os.environ,HOME=str(root),PATH=str(bins)+os.pathsep+os.environ['PATH'],MOCK_MODE=mode,MOCK_LOG=str(root/'calls'))
                r=subprocess.run(['bash',str(package/'resume_gate_c_tls.sh')],env=env,capture_output=True,text=True)
                calls=[json.loads(line) for line in (root/'calls').read_text().splitlines()]
                self.assertFalse(any(a[0] in ('pull','run','rm','rmi','prune','system','stop') for a in calls))
                self.assertEqual((old/'image-build.log').read_bytes(),b'old TLS exit100')
                if mode in ('success','bare-id'):
                    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
                    self.assertEqual((task/'evidence/gate-c-tls-01/build-image.id').read_text(),'sha256:'+'b'*64)
                else:
                    self.assertNotEqual(r.returncode,0)
                    self.assertNotIn('R3HD_BASELINE_GATE_C_IMAGE PASS',r.stdout)
                    self.assertFalse(any(a[0]=='save' for a in calls))


if __name__=='__main__':unittest.main()
