"""Isolated original-transfer copy tests; no host probes, image or SDK builds."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import manifest_update as M


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.old=self.root/'old';self.old.mkdir()
        with zipfile.ZipFile(M.ROOT/'private/work/linux_build/baseline_2b_egl_ready/r3hd-stage2b-egl.zip') as z:
            z.extractall(self.old)
        self.out=self.root/'package';M.build(self.out);self.package=self.root/'update';self.package.mkdir()
        with zipfile.ZipFile(self.out/'r3hd-egl-manifest-update.zip') as z:z.extractall(self.package)
        self.dest=self.root/'new'

    def snapshot(self,p):return {n.name:n.read_bytes() for n in p.iterdir()}

    def test_real_transfer_copy_and_only_two_changed_files(self):
        before=self.snapshot(self.old);M.apply(self.old,self.dest,self.package)
        self.assertEqual(before,self.snapshot(self.old))
        after=self.snapshot(self.dest)
        self.assertEqual({n for n in before if before[n]!=after[n]},{'retry.py','BUNDLE.json'})
        M.inventory(self.dest,json.loads(after['BUNDLE.json']))
        with self.assertRaisesRegex(ValueError,'destination exists'):M.apply(self.old,self.dest,self.package)
        self.assertEqual(after,self.snapshot(self.dest))

    def test_local_edit_refused_before_destination_write(self):
        p=self.old/'Containerfile';p.write_bytes(p.read_bytes()+b'#local edit\n')
        with self.assertRaisesRegex(ValueError,'local edit'):M.apply(self.old,self.dest,self.package)
        self.assertFalse(self.dest.exists())

    def test_unknown_file_and_bundle_edit_refused(self):
        p=self.old/'unknown';p.write_text('keep')
        with self.assertRaisesRegex(ValueError,'inventory'):M.apply(self.old,self.dest,self.package)
        self.assertFalse(self.dest.exists());p.unlink()  # temporary fixture only
        p=self.old/'BUNDLE.json';p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'original EGL toolkit'):M.apply(self.old,self.dest,self.package)
        self.assertFalse(self.dest.exists())

    def test_update_payload_edit_refused(self):
        p=self.package/'retry.py';p.write_bytes(p.read_bytes()+b'#edit\n')
        with self.assertRaisesRegex(ValueError,'payload hash'):M.apply(self.old,self.dest,self.package)
        self.assertFalse(self.dest.exists())

    def test_reproducible_and_build_overwrite_refusal(self):
        other=self.root/'second';M.build(other)
        self.assertEqual((self.out/'r3hd-egl-manifest-update.zip').read_bytes(),
                         (other/'r3hd-egl-manifest-update.zip').read_bytes())
        with self.assertRaisesRegex(ValueError,'output exists'):M.build(self.out)


if __name__=='__main__':unittest.main()
