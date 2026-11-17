"""Exact executor extension, unchanged security invariants and real sealed-runner delta."""
import ast
import contextlib
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile
import build_update as B
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
sys.path.append(str(HERE.parent/'guard_update'))
import protected_read as P
EXECUTOR='/usr/lib/systemd/systemd-executor'


class Tests(unittest.TestCase):
    def test_only_exact_allowlist_extension_and_display_count_changed(self):
        name='tools/linux/baseline/stage2d/guard_update/protected_read.py'
        old=subprocess.check_output(['git','-C',str(ROOT),'show','d530bbf:'+name]).decode()
        new=(ROOT/name).read_text()
        def tree(text):
            t=ast.parse(text)
            t.body=[n for n in t.body if not isinstance(n,ast.Assign) or not any(isinstance(v,ast.Name) and v.id=='ALLOWED' for v in n.targets)]
            return ast.dump(t)
        self.assertEqual(tree(old),tree(new))
        old_paths=ast.literal_eval(next(n.value for n in ast.parse(old).body if isinstance(n,ast.Assign) and n.targets[0].id=='ALLOWED'))
        self.assertEqual(P.ALLOWED,old_paths+(EXECUTOR,))
        resume='tools/linux/baseline/stage2d/guard_update/resume.py'
        original=subprocess.check_output(['git','-C',str(ROOT),'show','d530bbf:'+resume]).decode()
        self.assertEqual((ROOT/resume).read_text(),original.replace('Only three root-owned','Only four root-owned'))
        guard='tools/linux/baseline/stage2d/guard_update/proc_guard.py'
        self.assertEqual((ROOT/guard).read_text(),subprocess.check_output(['git','-C',str(ROOT),'show','d530bbf:'+guard]).decode())

    def test_real_observer_logic_executor_spoofs_inodes_permissions_and_exec_races(self):
        cases=('good','user path','unknown','deleted','inode mismatch','exec race','owner','writable','start')
        for case in cases:
            with self.subTest(case=case),contextlib.ExitStack() as stack:
                for n in ('O_CLOEXEC','O_NOFOLLOW','O_DIRECTORY'):stack.enter_context(patch.object(os,n,getattr(os,n,0),create=True))
                stack.enter_context(patch.object(os,'geteuid',return_value=0,create=True))
                proc=types.SimpleNamespace(st_dev=1,st_ino=2)
                image=types.SimpleNamespace(st_dev=3,st_ino=4,st_uid=1000 if case=='owner' else 0,st_mode=stat.S_IFREG|(0o777 if case=='writable' else 0o755))
                known=types.SimpleNamespace(st_dev=3,st_ino=99 if case=='inode mismatch' else 4)
                after=types.SimpleNamespace(st_dev=3,st_ino=99 if case=='exec race' else 4)
                path={'user path':'/home/<user>/systemd-executor','unknown':'/usr/lib/systemd/unknown','deleted':EXECUTOR+' (deleted)'}.get(case,EXECUTOR)
                snap={'uids':[1000]*4,'start':999 if case=='start' else 123,'state':'S'}
                for obj,name,kw in ((os,'open',{'side_effect':[3,4]}),(os,'close',{}),(os,'fstat',{'side_effect':[proc,image]}),(os,'readlink',{'return_value':path}),(os,'stat',{'side_effect':[known,after]}),(P,'snapshot',{'return_value':snap}),(P,'trusted_path',{})):
                    stack.enter_context(patch.object(obj,name,**kw))
                if case=='good':self.assertEqual(P.inspect(42,123,1000,1,2)['executable'],EXECUTOR)
                else:
                    with self.assertRaises(ValueError):P.inspect(42,123,1000,1,2)

    def test_executor_canonical_path_and_ancestor_permissions_still_required(self):
        target=Path(EXECUTOR)
        with patch.object(Path,'resolve',return_value=Path('/different')),self.assertRaisesRegex(ValueError,'noncanonical'):P.trusted_path(EXECUTOR)
        for uid,mode in ((1000,0o755),(0,0o775)):
            with patch.object(Path,'is_absolute',return_value=True),patch.object(Path,'resolve',lambda self,**kw:self),patch.object(Path,'lstat',return_value=types.SimpleNamespace(st_uid=uid,st_mode=stat.S_IFREG|mode)),self.assertRaisesRegex(ValueError,'untrusted'):
                P.trusted_path(EXECUTOR)

    def test_actual_previous_transfer_and_failed_receipt_preserved_edits_refused(self):
        base=ROOT/'private/work/linux_build';sha=lambda b:hashlib.sha256(b).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve();old=p/'guard-01';old.mkdir()
            with zipfile.ZipFile(base/'stage2d_handoff_checked/r3hd-stage2d.zip') as z:
                files={n:z.read(n) for n in z.namelist()}
            with zipfile.ZipFile(base/'stage2d_guard_update_ready/r3hd-stage2d-guard-update.zip') as z:
                for n in ('proc_guard.py','protected_read.py','resume.py'):files[n]=z.read(n)
            files['SHA256SUMS']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items()) if n!='SHA256SUMS').encode()
            files['guard-preflight.json']=b'{"result":"STOP","reason":"historical failure fixture"}\n'
            for n,b in files.items():(old/n).write_bytes(b)
            B.build(p/'export');update=p/'update';update.mkdir()
            with zipfile.ZipFile(p/'export/r3hd-stage2d-executor-update.zip') as z:
                self.assertIsNone(z.testzip())
                for row in z.read('SHA256SUMS').decode().splitlines():
                    h,n=row.split('  ');self.assertEqual(sha(z.read(n)),h)
                for n in z.namelist():(update/n).write_bytes(z.read(n))
            def apply(dest):return subprocess.run([sys.executable,'-B',str(update/'apply_executor.py'),'--source',str(old),'--output',str(dest)],capture_output=True,text=True)
            dest=p/'guard-02';r=apply(dest);self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(files,{f.name:f.read_bytes() for f in old.iterdir()});self.assertFalse((dest/'guard-preflight.json').exists())
            changed={n for n in files if n!='guard-preflight.json' and (dest/n).read_bytes()!=files[n]}
            self.assertEqual(changed,{'protected_read.py','resume.py','SHA256SUMS'})
            for row in (dest/'SHA256SUMS').read_text().splitlines():
                h,n=row.split('  ');self.assertEqual(sha((dest/n).read_bytes()),h)
            self.assertNotEqual(apply(dest).returncode,0)
            r=subprocess.run([sys.executable,'-B',str(dest/'resume.py'),'--help'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            (old/'proc_guard.py').write_bytes(files['proc_guard.py']+b'# edit\n')
            r=apply(p/'bad-source');self.assertNotEqual(r.returncode,0);self.assertIn('local edit',r.stderr);self.assertFalse((p/'bad-source').exists())
            (old/'proc_guard.py').write_bytes(files['proc_guard.py'])
            (update/'protected_read.py').write_bytes(b'# tamper\n')
            r=apply(p/'bad-update');self.assertNotEqual(r.returncode,0);self.assertIn('changed executor',r.stderr)
            self.assertEqual(files,{f.name:f.read_bytes() for f in old.iterdir()})


if __name__=='__main__':unittest.main()
