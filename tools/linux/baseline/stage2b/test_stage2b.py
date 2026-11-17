"""Synthetic acceptance tests; no host inspection, container or SDK/game build."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tarfile
import unittest
import zipfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('stage2b', HERE/'stage2b.py')
B = importlib.util.module_from_spec(spec); spec.loader.exec_module(B)


class Gates(unittest.TestCase):
    def test_abi_ceilings_and_private_abi(self):
        self.assertEqual(B.version_limits('GLIBC_2.39 GLIBCXX_3.4.33')['GLIBC'], '2.39')
        self.assertEqual(B.version_limits('GLIBC_2.2.5')['GLIBCXX'], None)
        for data in ('GLIBC_2.40', 'GLIBCXX_3.4.34', 'GLIBC_PRIVATE'):
            with self.subTest(data=data), self.assertRaises(ValueError): B.version_limits(data)

    def native_fixture(self, root):
        p = root/'evidence/expected19-01'; (p/'probe').mkdir(parents=True)
        (p/'exit-status.txt').write_text('0\n')
        (p/'image.id').write_text('sha256:'+'a'*64)
        (p/'probe.log').write_text('19.1.1\nR3HD_BASELINE_FEATURE PASS 42:42\n'
            'R3HD_BASELINE_PROBE PASS (feature only; full SDK/game not built)\n')
        (p/'probe/compiler-search.txt').write_text('Selected GCC installation: /usr/lib/gcc/x86_64-linux-gnu/13\n')
        for name in ('feature','r3hd-packages.tsv'): (p/'probe'/name).write_bytes(name.encode())
        (p/'probe/SHA256SUMS').write_text(''.join(B.sha(p/'probe'/n)+'  /original/'+n+'\n'
                                              for n in ('feature','r3hd-packages.tsv')))
        return p

    def test_native_evidence_requires_all_markers_and_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=self.native_fixture(root)
            self.assertEqual(B.feature_evidence(root)['image_id'], 'sha256:'+'a'*64)
            for file, bad in [('exit-status.txt','1'), ('image.id','mutable:tag'),
                              ('probe.log','19.1.1 only'), ('probe/compiler-search.txt','Selected GCC installation: /usr/14'),
                              ('probe/feature','edited'), ('probe/SHA256SUMS','bad')]:
                q=p/file;old=q.read_bytes();q.write_text(bad)
                with self.subTest(file=file), self.assertRaises(ValueError): B.feature_evidence(root)
                q.write_bytes(old)
            q=p/'probe/SHA256SUMS';q.write_text(q.read_text().splitlines()[0]+'\n')
            with self.assertRaises(ValueError): B.feature_evidence(root)

    def test_bundle_rejects_extra_and_edited_files(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(B,'HERE',Path(tmp)):
            p=Path(tmp);(p/'a').write_bytes(b'ok')
            (p/'BUNDLE.json').write_text(json.dumps({'files':{'a':B.sha(p/'a')}}))
            with contextlib.redirect_stdout(io.StringIO()): B.bundle_check()
            (p/'extra').write_bytes(b'unknown')
            with self.assertRaises(ValueError): B.bundle_check()
            (p/'extra').unlink();(p/'a').write_bytes(b'edited')
            with self.assertRaises(ValueError): B.bundle_check()

    def test_write_never_overwrites_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'evidence.json';B.write(p,{'first':True})
            with self.assertRaises(FileExistsError): B.write(p,{'first':False})
            self.assertTrue(json.loads(p.read_text())['first'])

    def test_extract_refuses_bad_archive_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);a=p/'kit.tar.gz';a.write_bytes(b'not a kit')
            with self.assertRaisesRegex(ValueError,'SHA'): B.extract(a,p)
            self.assertEqual([q.name for q in p.iterdir()],['kit.tar.gz'])

    def test_engine_rejects_security_mapping_storage_and_budget_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=Path(tmp)
            pre={'status':'STATIC_PREFLIGHT_PASS','failures':[], 'checks':{'storage':{
                'graphroot_predicted':str(t),'image_copy_tmp_dir_predicted':str(t)}}}
            info={'host':{'arch':'amd64','serviceIsRemote':False,'security':{'rootless':True,'seccompEnabled':True},
                'idMappings':{'uidmap':[{'size':65537}],'gidmap':[{'size':65537}]}},'store':{
                    'graphDriverName':'overlay','graphRoot':str(t),'imageCopyTmpDir':str(t),'runRoot':'/run/user/1000/containers'}}
            def fs(path):
                return {'requested':str(path),'uuid':'same-uuid','source':'/dev/test[/subvolume]',
                        'fstype':'btrfs','options':'rw','available_bytes':70_000_000_000}
            original=B.engine_check
            def check(pre,info,task,filesystem=fs): return original(pre,info,task,filesystem)
            with patch.object(os,'getuid',return_value=1000,create=True):
                self.assertEqual(len(check(pre,info,t)),3)
                for field,bad in [('graphDriverName','vfs'),('graphRoot',str(t/'other')),('runRoot','/var/run')]:
                    j=copy.deepcopy(info);j['store'][field]=bad
                    with self.subTest(field=field), self.assertRaises(ValueError): check(pre,j,t)
                for key in ('rootless','seccompEnabled'):
                    j=copy.deepcopy(info);j['host']['security'][key]=False
                    with self.assertRaises(ValueError): check(pre,j,t)
                for key,bad in [('serviceIsRemote',True),('arch','arm64')]:
                    j=copy.deepcopy(info);j['host'][key]=bad
                    with self.assertRaises(ValueError): check(pre,j,t)
                j=copy.deepcopy(info);j['host']['idMappings']['uidmap'][0]['size']=65536
                with self.assertRaises(ValueError): check(pre,j,t)
                for key,value in [('available_bytes',49_999_999_999),('fstype','tmpfs'),('options','ro')]:
                    def badfs(path):return {**fs(path),key:value}
                    with self.assertRaises(ValueError):check(pre,info,t,badfs)
                rows=[fs(t),{**fs(t),'source':'/dev/test[/another-subvolume]'},fs(t)]
                self.assertEqual(len(check(pre,info,t,lambda p:rows.pop(0))),3)
                rows=[fs(t),{**fs(t),'uuid':'another-disk'},fs(t)]
                with self.assertRaises(ValueError):check(pre,info,t,lambda p:rows.pop(0))

    def test_audit_rejects_foreign_elf_absolute_rpath_and_loader_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);elf=p/'libtest.so'
            elf.write_bytes(b'\x7fELF\x02\x01'+b'\0'*12+b'\x3e\x00')
            def cmd(*args,**kwargs):
                return ' (RUNPATH) Library runpath: [$ORIGIN]\n' if args[0]=='readelf' else '*UND* (GLIBC_2.39) test'
            with patch.object(B,'command',side_effect=cmd), patch.object(B.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'closure')):
                self.assertEqual(B.audit_elf(elf,p,p)['requires']['GLIBC'],'2.39')
                with patch.object(B,'command',return_value=' (RUNPATH) Library runpath: [/host/lib]'):
                    with self.assertRaisesRegex(ValueError,'RPATH'): B.audit_elf(elf,p,p)
                with patch.object(B.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'not found')):
                    with self.assertRaisesRegex(ValueError,'closure'): B.audit_elf(elf,p,p)
            elf.write_bytes(b'not elf')
            with self.assertRaisesRegex(ValueError,'ELF'): B.audit_elf(elf,p,p)

    def test_runner_enforces_isolation_and_compiler_without_stage2a_mutation(self):
        host=(HERE/'run_native.sh').read_text();inside=(HERE/'build_inside.sh').read_text()
        for flag in ('--network=none','--cap-drop=ALL','--security-opt=no-new-privileges','--read-only','--pull=never'):
            self.assertIn(flag,host)
        self.assertIn('test ! -e "$TASK"',host)
        for forbidden in ('system prune','image rm','menu-run','replace-test','git checkout','git clean','apt-get'):
            self.assertNotIn(forbidden,host+inside)
        for name in ('clang','clang++'):
            text=(HERE/name).read_text()
            self.assertIn('/usr/bin/'+name+'-19',text)
            self.assertIn('--gcc-install-dir=/usr/lib/gcc/x86_64-linux-gnu/13',text)
        self.assertLess(inside.index('stage2b.py abi'),inside.index('r3hd_linux_package.py build'))
        self.assertIn('m46_lgpl.py rebuild',inside)
        self.assertLess(inside.index('cmp /opt/r3hd-packages.tsv'),inside.index('r3hd_linux_build.py run'))

    def test_multiconfig_backend_check_requires_release_compiled_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);work=p/'work';out=p/'out';out.mkdir()
            build=work/'external/rexglue-sdk/out/build/linux-amd64';build.mkdir(parents=True)
            required=('SDL_X11','SDL_WAYLAND','SDL_VULKAN','SDL_ALSA','SDL_PULSEAUDIO','SDL_PIPEWIRE')
            (build/'CMakeCache.txt').write_text(''.join(n+':BOOL=ON\n' for n in required))
            macros=('SDL_VIDEO_DRIVER_X11','SDL_VIDEO_DRIVER_WAYLAND','SDL_VIDEO_VULKAN',
                    'SDL_AUDIO_DRIVER_ALSA','SDL_AUDIO_DRIVER_PULSEAUDIO','SDL_AUDIO_DRIVER_PIPEWIRE')
            for config in ('release','debug','relwithdebinfo'):
                h=build/('include-config-'+config)/'build_config/SDL_build_config.h';h.parent.mkdir(parents=True)
                h.write_text(''.join('#define '+n+' 1\n' for n in macros))
            with contextlib.redirect_stdout(io.StringIO()): B.backend_check(work,out)
            header=build/'include-config-release/build_config/SDL_build_config.h'
            header.write_text('#define SDL_VIDEO_DRIVER_X11 1\n')
            with self.assertRaisesRegex(ValueError,'compiled backend'): B.backend_check(work,out)
            header.unlink()
            with self.assertRaisesRegex(ValueError,'Release'): B.backend_check(work,out)

    def test_package_binds_audited_binaries_private_flag_and_lgpl_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);(out/'lgpl').mkdir();source=out/'lgpl/source.zip';source.write_bytes(b'synthetic source')
            members={'bin/'+n:n.encode() for n in B.COMPONENTS}
            portable={'publishable':False,'lgpl':{'corresponding_source':{
                'archive':'source.zip','sha256':B.sha(source)}}}
            (out/'abi.json').write_text(json.dumps({'components':{n:{'sha256':hashlib.sha256(n.encode()).hexdigest()}
                                                                  for n in B.COMPONENTS}}))
            def archive():
                path=out/'r3hd-linux-noble-2b01.tar.gz'
                with tarfile.open(path,'w:gz') as tar:
                    for n,raw in {**members,'portable.json':json.dumps(portable).encode()}.items():
                        m=tarfile.TarInfo('Rayman3HDRecompiled-Linux/'+n);m.size=len(raw);tar.addfile(m,io.BytesIO(raw))
                (out/'package-check.json').write_text(json.dumps({'result':'PASS','publishable':False,'sha256':B.sha(path)}))
            archive()
            with contextlib.redirect_stdout(io.StringIO()): B.package_accept(out)
            source.write_bytes(b'changed source')
            with self.assertRaisesRegex(ValueError,'LGPL source hash'): B.package_accept(out)
            source.write_bytes(b'synthetic source');portable['publishable']=True;archive()
            with self.assertRaisesRegex(ValueError,'publishable'): B.package_accept(out)
            portable['publishable']=False;members['bin/r3hd']=b'not the audited r3hd';archive()
            with self.assertRaisesRegex(ValueError,'ABI audit'): B.package_accept(out)

    def test_collector_is_private_metadata_only_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);task=home/'Projects/R3HD-baseline-noble-2b-01';e=task/'evidence';e.mkdir(parents=True)
            (e/'OWNER.txt').write_text('R3HD_STAGE2B_01\n');(e/'exit-status.txt').write_text('2\n')
            (e/'build.log').write_text('synthetic failure');(e/'unknown.bin').write_bytes(b'preserve')
            (e/'verified-2a-packages.tsv').write_text('synthetic\tversion\tamd64\n')
            out=task/'work/private/work/linux_build/noble_2b01';out.mkdir(parents=True)
            (out/'results.json').write_text('{"status":"FAIL"}')
            (out/'guest.cpp').write_text('not evidence');(out/'r3hd').write_bytes(b'not evidence')
            env=dict(os.environ,HOME=str(home),USERPROFILE=str(home),PYTHONDONTWRITEBYTECODE='1')
            p=subprocess.run([sys.executable,'-B',str(HERE/'collect.py')],env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            dest=task/'stage2b-private-evidence.zip';original=dest.read_bytes()
            with zipfile.ZipFile(dest) as z:
                self.assertIn('evidence/build.log',z.namelist())
                self.assertIn('evidence/verified-2a-packages.tsv',z.namelist())
                self.assertFalse(any(n.endswith(('unknown.bin','guest.cpp','/r3hd')) for n in z.namelist()))
            p=subprocess.run([sys.executable,'-B',str(HERE/'collect.py')],env=env,capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0);self.assertEqual(dest.read_bytes(),original)
            self.assertEqual((e/'unknown.bin').read_bytes(),b'preserve')


if __name__=='__main__': unittest.main()
