"""Contract, evidence, isolation and finalization fixtures; no game/SDK execution."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
import zipfile
from unittest.mock import patch

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path[:0]=[str(HERE),str(ROOT/'tools/linux')]
import checks as C
import native as N
import review as R
import r3hd_linux_package as P
spec=importlib.util.spec_from_file_location('current_stage2b',HERE.parent/'stage2b/stage2b.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)


def fixture(root):
    source=root/'source.zip';source.write_bytes(b'synthetic LGPL source')
    files={'bin/'+n:('synthetic '+n).encode() for n in C.COMPONENTS}
    files.update({'Play.sh':b'exit 99','Settings.sh':b'exit 99','app/tools/r3hd_portable.py':b'raise RuntimeError("never execute fixture")'})
    files['payload.json']=json.dumps({'publishable':False}).encode()
    portable={'publishable':False,'lgpl':{'corresponding_source':{'archive':C.SOURCE,'sha256':C.sha(source)}},
              'files':{n:{'size':len(b),'sha256':C.digest(b)} for n,b in files.items()}}
    files['portable.json']=json.dumps(portable).encode()
    package=root/C.PACKAGE
    def pack(members=files):
        with tarfile.open(package,'w:gz') as t:
            for n,b in members.items():
                m=tarfile.TarInfo(C.TOP+'/'+n);m.mode=0o755 if n in ('Play.sh','Settings.sh','bin/r3hd') else 0o644
                m.size=len(b);t.addfile(m,io.BytesIO(b))
    pack();abi={n:{'sha256':C.digest(files['bin/'+n]),'needed':[]} for n in C.COMPONENTS}
    return source,package,files,abi,pack


class FinalTests(unittest.TestCase):
    def test_cli_stdout_json_stderr_marker_and_failure_status(self):
        record={'result':'PASS','publishable':False,'sha256':'a'*64}
        for cmd in ('check','build'):
            argv=['tool','check','unused'] if cmd=='check' else ['tool','build','--bin','b','--lib','l','--out','o','--development-id','test']
            with patch.object(sys,'argv',argv),patch.object(P,cmd,return_value=record),contextlib.redirect_stdout(io.StringIO()) as out,contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(P.main(),0);self.assertEqual(json.loads(out.getvalue()),record)
                self.assertEqual(err.getvalue(),'R3HD_LINUX_PACKAGE PASS\n')
        with patch.object(sys,'argv',['tool','check','unused']),patch.object(P,'check',side_effect=ValueError('tampered archive')),contextlib.redirect_stdout(io.StringIO()) as out,contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(P.main(),2);self.assertEqual(out.getvalue(),'');self.assertIn('REFUSED',err.getvalue())

    def test_acceptance_json_is_strict_not_prefix_or_duplicate_fallback(self):
        good=b'{"result":"PASS","publishable":false,"sha256":"'+b'a'*64+b'"}'
        self.assertEqual(B.package_record(good)['sha256'],'a'*64)
        for raw in (b'R3HD_LINUX_PACKAGE '+good,b'',b'[]',good+b'junk',
                    good.replace(b'false',b'true'),good.replace(b'PASS',b'FAIL'),
                    good.replace(b'a'*64,b'not-a-hash'),good.replace(b'"result":',b'"result":"FAIL","result":'),
                    good[:-1]+b',"extra":NaN}'):
            with self.subTest(raw=raw),self.assertRaises((ValueError,KeyError)):B.package_record(raw)
        self.assertEqual(C.old_record(b'R3HD_LINUX_PACKAGE '+good),C.private_record(good))
        with self.assertRaises(ValueError):C.old_record(b'noise\nR3HD_LINUX_PACKAGE '+good)

    def test_package_extraction_binds_inventory_and_binary_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source,package,files,abi,pack=fixture(root)
            with patch.dict(C.LOCK,lgpl_sha256=C.sha(source)):
                C.package_files(package,abi)
                dest=root/'install';dest.mkdir();C.package_files(package,abi,dest)
                self.assertEqual((dest/'bin/r3hd').read_bytes(),files['bin/r3hd'])
                for name,value in [('bin/r3hd',b'tampered'),('extra',b'unknown'),('../escape',b'bad')]:
                    pack({**files,name:value})
                    with self.assertRaises(ValueError):C.package_files(package,abi)
                pack();bad={**abi,'r3hd':{'sha256':'0'*64}}
                with self.assertRaises(ValueError):C.package_files(package,bad)

    def test_isolated_environment_and_collision_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            with patch.dict(os.environ,{'DISPLAY':':0','WAYLAND_DISPLAY':'wayland-0','LD_PRELOAD':'bad','R3HD_PLAY':'1'}):
                env=N.environment(root/'os-home',root/'installation/bin')
            self.assertFalse(set(env)&{'DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','LD_PRELOAD','LD_AUDIT','R3HD_PLAY'})
            self.assertEqual(env['HOME'],str(root/'os-home'))
            dest=root/'exists';dest.mkdir();(dest/'preserve').write_text('keep')
            with patch.object(N.platform,'system',return_value='Linux'),patch.object(N.platform,'machine',return_value='x86_64'),patch.object(N.os,'getuid',return_value=1000,create=True):
                with self.assertRaisesRegex(ValueError,'destination exists'):N.start(dest)
            self.assertEqual((dest/'preserve').read_text(),'keep')

    def test_stage2c_command_allowlist_and_expected_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp).resolve();out=home/'Projects/R3HD-baseline-noble-2b-egl-01'/C.REL;out.mkdir(parents=True)
            source,package,files,abi,_=fixture(out);(out/'lgpl').mkdir();(out/'lgpl'/C.SOURCE).write_bytes(source.read_bytes())
            (out/'abi.json').write_text(json.dumps({'components':abi}))
            final=home/'Projects/R3HD-baseline-noble-2b-final-01';final.mkdir()
            C.write(final/'finalization.json',{'status':'PASS','kind':'SUPPLEMENTAL_FINALIZATION','original_orchestration_exit':2,
                  'uninterrupted_workflow_pass':False,'package':str(package),'lgpl_source':str(out/'lgpl'/C.SOURCE)})
            dest=home/'Projects/R3HD-baseline-noble-2c-01';calls=[]
            def command(args,log,env,cwd):
                calls.append(list(map(str,args)))
                if '--list' in args:code,text=0,'synthetic loader closure'
                else:
                    self.assertEqual(list(args)[-2:],['prepare','--no-input']);code,text=2,'PACKAGE_REQUIRED'
                log.write_text(text);return code,text
            lock={**C.LOCK,'package_sha256':C.sha(package),'lgpl_sha256':C.sha(out/'lgpl'/C.SOURCE),
                  'native_records':{C.REL+'abi.json':C.sha(out/'abi.json')}}
            # Platform/file guards are native-only; fixture exercises the complete
            # extraction, dependency command sequence, refusal and result path.
            def start(p):p.mkdir();(p/'OWNER.txt').write_text('R3HD_BASELINE_FINAL_AND_PROBE_01')
            with patch.object(Path,'home',return_value=home),patch.object(N,'start',side_effect=start),patch.object(N,'command',side_effect=command),patch.object(C,'LOCK',lock),patch.object(Path,'is_file',autospec=True,side_effect=lambda p:True if p.as_posix().startswith(('/lib64/','/usr/bin/python3')) else p.exists() and not p.is_dir()):
                N.probe(final,dest)
            self.assertEqual(len(calls),6)
            self.assertTrue(all(a[1]=='--list' for a in calls[:5]))
            j=C.read_json((dest/'probe.json').read_bytes());self.assertFalse(j['game_entrypoint_executed'])
            N.collect(dest)
            with zipfile.ZipFile(dest/'supplemental-private-evidence.zip') as z:
                self.assertFalse(any('installation' in n or 'os-home' in n for n in z.namelist()))
            with self.assertRaises(ValueError):N.collect(dest)

    def test_finalization_existing_artifacts_no_rebuild_or_old_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp).resolve();task=home/'Projects/R3HD-baseline-noble-2b-egl-01'
            out=task/C.REL;out.mkdir(parents=True);e=task/'evidence';e.mkdir()
            source,package,files,abi,_=fixture(out);(out/'lgpl').mkdir();(out/'lgpl'/C.SOURCE).write_bytes(source.read_bytes())
            (out/'abi.json').write_text(json.dumps({'components':abi}))
            checked={'result':'PASS','publishable':False,'sha256':C.sha(package)}
            raw=json.dumps(checked).encode();(out/'package-check.json').write_bytes(raw)
            (out/'acceptance.json').write_text('{"status":"PASS"}')
            (e/'package-check-original-prefixed.txt').write_bytes(b'R3HD_LINUX_PACKAGE '+raw)
            (e/'exit-status.txt').write_text('2');(task/'stage2b-private-evidence.zip').write_bytes(b'fixture ZIP')
            (e/'OWNER.txt').write_text('R3HD_STAGE2B_EGL_01')
            (task/'KIT_MANIFEST.json').write_bytes(b'{}')
            runner=home/'runner';runner.mkdir()
            (runner/'stage2b.py').write_text('import os\ndef immutable(work, manifest):\n    assert os.environ["GIT_OPTIONAL_LOCKS"] == "0"\n    return {"immutable_project_and_lma": True}\n')
            (runner/'EGL_LOCK.json').write_text(json.dumps({'kit_manifest_sha256':C.digest(b'{}')}))
            C.write(runner/'BUNDLE.json',{'files':{n:C.sha(runner/n) for n in ('stage2b.py','EGL_LOCK.json')}})
            lock={**C.LOCK,'runner_bundle_sha256':C.sha(runner/'BUNDLE.json'),'package_sha256':C.sha(package),
                  'lgpl_sha256':C.sha(out/'lgpl'/C.SOURCE),'native_records':{'evidence/exit-status.txt':C.sha(e/'exit-status.txt')},
                  'files':{n:C.sha(p) for n,p in {'stage2b-private-evidence.zip':task/'stage2b-private-evidence.zip',
                    'package-check.json':out/'package-check.json','acceptance.json':out/'acceptance.json',
                    'package-check-original-prefixed.txt':e/'package-check-original-prefixed.txt'}.items()}}
            before={p.relative_to(task).as_posix():C.sha(p) for p in task.rglob('*') if p.is_file()};calls=[]
            def command(args,log,env,cwd):
                calls.append(list(map(str,args)));text='R3HD_LINUX_PACKAGE '+raw.decode();log.write_text(text);return 0,text
            def start(p):
                if p.exists():raise ValueError('destination exists')
                p.mkdir();(p/'OWNER.txt').write_text('R3HD_BASELINE_FINAL_AND_PROBE_01')
            dest=home/'Projects/R3HD-baseline-noble-2b-final-01'
            with patch.object(Path,'home',return_value=home),patch.object(C,'LOCK',lock),patch.object(N,'start',side_effect=start),patch.object(N,'command',side_effect=command):
                N.finish(task,runner,dest)
                with self.assertRaisesRegex(ValueError,'destination exists'):N.finish(task,runner,dest)
            self.assertEqual(before,{p.relative_to(task).as_posix():C.sha(p) for p in task.rglob('*') if p.is_file()})
            self.assertEqual(len(calls),1);self.assertEqual(calls[0][-2:],['check',str(package)])
            j=C.read_json((dest/'finalization.json').read_bytes());self.assertEqual(j['original_orchestration_exit'],2)
            self.assertFalse(j['uninterrupted_workflow_pass']);self.assertEqual(len((dest/'DELIVERABLES.sha256').read_text().splitlines()),2)

    def test_review_authenticates_all_actual_evidence_and_supplements(self):
        folder=ROOT/'private/work/linux_build/stage2b_native_evidence_20261109'
        if not folder.exists():self.skipTest('private native evidence not supplied')
        j=R.review(folder);self.assertEqual(j['original_orchestration_exit'],2)
        self.assertEqual(j['original_zip_members'],83);self.assertTrue(j['supplements_separate'])

    def test_changed_supplement_is_not_accepted_as_native_evidence(self):
        folder=ROOT/'private/work/linux_build/stage2b_native_evidence_20261109'
        if not folder.exists():self.skipTest('private native evidence not supplied')
        with tempfile.TemporaryDirectory() as tmp:
            copy=Path(tmp)
            for n in C.LOCK['files']:(copy/n).write_bytes((folder/n).read_bytes())
            p=copy/'acceptance.json';p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):R.review(copy)


if __name__=='__main__':unittest.main()
