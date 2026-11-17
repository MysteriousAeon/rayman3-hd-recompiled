"""Apply the delta to an isolated copy of the actual sealed original transfer."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import build_update as B

ROOT=B.HERE.parents[4]
ORIGINAL=ROOT/'private/work/linux_build/stage2d_handoff_checked/r3hd-stage2d.zip'


class Tests(unittest.TestCase):
    def test_actual_transfer_update_integrity_and_local_edit_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve();old=p/'original';old.mkdir()
            with zipfile.ZipFile(ORIGINAL) as z:
                for n in z.namelist():(old/n).write_bytes(z.read(n))
            snapshot={f.name:f.read_bytes() for f in old.iterdir()}
            B.build(p/'export');update=p/'update';update.mkdir()
            with zipfile.ZipFile(p/'export/r3hd-stage2d-guard-update.zip') as z:
                self.assertIsNone(z.testzip())
                for row in z.read('SHA256SUMS').decode().splitlines():
                    h,n=row.split('  ');self.assertEqual(hashlib.sha256(z.read(n)).hexdigest(),h)
                for n in z.namelist():(update/n).write_bytes(z.read(n))
            def apply(dest):return subprocess.run([sys.executable,'-B',str(update/'apply_update.py'),'--original',str(old),'--output',str(dest)],capture_output=True,text=True)
            dest=p/'guarded';self.assertEqual(apply(dest).returncode,0)
            self.assertEqual(snapshot,{f.name:f.read_bytes() for f in old.iterdir()})
            self.assertEqual((dest/'gameplay.py').read_bytes(),snapshot['gameplay.py'])
            self.assertNotEqual(apply(dest).returncode,0)
            for row in (dest/'SHA256SUMS').read_text().splitlines():
                h,n=row.split('  ');self.assertEqual(hashlib.sha256((dest/n).read_bytes()).hexdigest(),h)
            r=subprocess.run([sys.executable,'-B',str(dest/'resume.py'),'--help'],capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
            r=subprocess.run([sys.executable,'-B',str(dest/'resume.py'),'check'],capture_output=True,text=True)
            # Windows native refusal, WSL refusal, or real Linux missing workspace. Never launches.
            self.assertNotEqual(r.returncode,0)
            (old/'gameplay.py').write_bytes(snapshot['gameplay.py']+b'\n# local edit\n')
            r=apply(p/'edited');self.assertNotEqual(r.returncode,0);self.assertIn('local edit',r.stderr);self.assertFalse((p/'edited').exists())
            (old/'gameplay.py').write_bytes(snapshot['gameplay.py'])
            with (update/'protected_read.py').open('ab') as f:f.write(b'\n# edit\n')
            r=apply(p/'bad-update');self.assertNotEqual(r.returncode,0);self.assertIn('changed update',r.stderr)
            self.assertEqual(snapshot,{f.name:f.read_bytes() for f in old.iterdir()})


if __name__=='__main__':unittest.main()
