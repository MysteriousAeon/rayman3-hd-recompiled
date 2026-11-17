"""Frozen-source transfer and wrapper boundaries; never starts a target game."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock,patch
import zipfile
import build_update as B
sys.path.append(str(B.HERE.parent))
import scoped_resume as R
ROOT=B.HERE.parents[4]


class Tests(unittest.TestCase):
    def test_spawn_adapter_only_target_inherits_and_original_supervisor_keeps_child(self):
        child=types.SimpleNamespace(pid=42)
        module=types.SimpleNamespace(Popen=Mock(return_value=child),run=Mock())
        control=types.SimpleNamespace(fd=7,register=Mock(),registration_error=False)
        proxy=R.SpawnAdapter(module,control,{},'/verified/r3hd')
        with patch.object(R,'examine'):
            self.assertIs(proxy.Popen(['/verified/r3hd'],start_new_session=True),child)
            self.assertEqual(module.Popen.call_args.kwargs['pass_fds'],(7,))
            self.assertTrue(module.Popen.call_args.kwargs['start_new_session'])
            self.assertIs(proxy.run,module.run)
            with self.assertRaises(ValueError):proxy.Popen(['/wrong/target'])
            control.register.side_effect=OSError('fixture metadata failure')
            self.assertIs(proxy.Popen(['/verified/r3hd']),child);self.assertTrue(control.registration_error)
        self.assertEqual(module.Popen.call_count,2)

    def test_human_attestation_mandatory_unknown_external_is_not_automatic_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            ctl=types.SimpleNamespace(registration_error=False)
            cm=Mock();cm.__enter__=Mock(return_value=ctl);cm.__exit__=Mock(return_value=False)
            summary={'unresolved_external_identities':3,'external_attestation_required':True}
            with patch.object(sys,'argv',['scoped_resume.py','human','a','--human-present']),patch.object(R,'HERE',p),patch.object(R,'seal'),patch.object(R.G.N,'native'),patch.object(R.S,'require_unprivileged'),patch.object(R.G,'workspace',return_value=p),patch.object(R.S,'identity',return_value={}),patch.object(R.S,'Control',return_value=cm),patch.object(R,'examine',return_value=summary),patch.object(sys.stdin,'isatty',return_value=True),patch('builtins.input',return_value='no'),patch.object(R.G,'run') as run:
                with self.assertRaisesRegex(ValueError,'attestation'):R.main()
                run.assert_not_called()

    def test_actual_guard02_copy_and_old_evidence_preserved_no_privileged_modules(self):
        sha=lambda b:hashlib.sha256(b).hexdigest();base=ROOT/'private/work/linux_build'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve();old=p/'guard02';old.mkdir()
            with zipfile.ZipFile(base/'stage2d_handoff_checked/r3hd-stage2d.zip') as z:files={n:z.read(n) for n in z.namelist()}
            for path,names in [('stage2d_guard_update_ready/r3hd-stage2d-guard-update.zip',('proc_guard.py','protected_read.py','resume.py')),('stage2d_executor_update_checked/r3hd-stage2d-executor-update.zip',('protected_read.py','resume.py'))]:
                with zipfile.ZipFile(base/path) as z:
                    for n in names:files[n]=z.read(n)
            files['SHA256SUMS']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items()) if n!='SHA256SUMS').encode()
            files['guard-preflight.json']=b'{"result":"STOP","reason":"historical fixture"}\n'
            for n,b in files.items():(old/n).write_bytes(b)
            B.build(p/'export');update=p/'update';update.mkdir()
            with zipfile.ZipFile(p/'export/r3hd-stage2d-scoped-update.zip') as z:
                self.assertIsNone(z.testzip())
                for row in z.read('SHA256SUMS').decode().splitlines():
                    h,n=row.split('  ');self.assertEqual(sha(z.read(n)),h)
                for n in z.namelist():(update/n).write_bytes(z.read(n))
            def apply(dest):return subprocess.run([sys.executable,'-B',str(update/'apply_scoped.py'),'--source',str(old),'--output',str(dest)],capture_output=True,text=True)
            dest=p/'scoped';r=apply(dest);self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(files,{f.name:f.read_bytes() for f in old.iterdir()})
            for n in ('resume.py','protected_read.py','proc_guard.py','guard-preflight.json'):self.assertFalse((dest/n).exists())
            self.assertEqual((dest/'gameplay.py').read_bytes(),files['gameplay.py'])
            for row in (dest/'SHA256SUMS').read_text().splitlines():
                h,n=row.split('  ');self.assertEqual(sha((dest/n).read_bytes()),h)
            self.assertNotEqual(apply(dest).returncode,0)
            for args in (['--help'],['check']):
                r=subprocess.run([sys.executable,'-B',str(dest/'scoped_resume.py'),*args],capture_output=True,text=True)
                self.assertEqual(r.returncode==0,args==['--help']) # Windows/WSL native refusal before any launch
            (old/'gameplay.py').write_bytes(files['gameplay.py']+b'# edit\n')
            r=apply(p/'bad');self.assertNotEqual(r.returncode,0);self.assertIn('local source edit',r.stderr)
            self.assertFalse((p/'bad').exists());(old/'gameplay.py').write_bytes(files['gameplay.py'])
            (update/'scoped_guard.py').write_bytes(b'# tamper\n')
            r=apply(p/'bad-update');self.assertNotEqual(r.returncode,0);self.assertIn('changed update',r.stderr)
            self.assertEqual(files,{f.name:f.read_bytes() for f in old.iterdir()})


if __name__=='__main__':unittest.main()
