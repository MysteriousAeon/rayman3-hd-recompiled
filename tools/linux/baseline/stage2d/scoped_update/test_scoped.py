"""Bounded concurrency fixtures only. No r3hd/SDL/audio/GPU or privileged observer."""
import contextlib
import errno
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
import scoped_guard as S
HERE=Path(__file__).resolve().parent


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack()
        for n in ('O_CLOEXEC','O_NOFOLLOW','O_DIRECTORY'):self.stack.enter_context(patch.object(os,n,getattr(os,n,0),create=True))
        self.snap={'uids':[1000]*4,'caps':0,'start':12,'state':'S','threads':1,'proc_dev':1,'proc_ino':2}
        self.ref={'size':100,'dev':3,'ino':4,'sha256':'game'}
    def tearDown(self):self.stack.close()

    def test_protected_helpers_are_outside_target_credentials_not_service_names(self):
        for credentials,caps in (([1000,0,0,0],0),([0]*4,0),([1000]*4,128)):
            s=dict(self.snap,uids=credentials,caps=caps)
            with patch.object(S,'hint',return_value=False),patch.object(S,'snapshot',return_value=s),patch.object(os,'readlink') as exe:
                kind=S.probe(3,self.ref,1000)
                self.assertIn(kind,('OTHER_UID_NOT_CHECKED','OUTSIDE_UNPRIVILEGED_TARGET_MODEL'));exe.assert_not_called()
        # A positive game indicator does not get a privileged-helper exemption.
        with patch.object(S,'hint',return_value=True),patch.object(S,'snapshot',return_value=dict(self.snap,uids=[1000,0,0,0])),patch.object(os,'readlink',side_effect=PermissionError),self.assertRaisesRegex(ValueError,'relevant game'):
            S.probe(3,self.ref,1000)

    def test_inaccessible_image_unknown_retained_but_relevant_ambiguity_blocks(self):
        for suspect in (False,True):
            with patch.object(S,'hint',return_value=suspect),patch.object(S,'snapshot',return_value=self.snap),patch.object(os,'readlink',side_effect=PermissionError):
                if suspect:
                    with self.assertRaisesRegex(ValueError,'inaccessible'):S.probe(3,self.ref,1000)
                else:self.assertEqual(S.probe(3,self.ref,1000),'UNKNOWN_IMAGE')

    def test_other_installation_and_spoofed_comm_do_not_hide_real_image(self):
        obj=types.SimpleNamespace(st_dev=5,st_ino=6,st_size=100)
        for target,digest in (('/other/installation/bin/r3hd','other-build'),('/tmp/not-a-game-name','game')):
            with patch.object(S,'hint',return_value=False),patch.object(S,'snapshot',return_value=self.snap),patch.object(os,'readlink',return_value=target),patch.object(os,'open',return_value=4),patch.object(os,'close'),patch.object(os,'fstat',return_value=obj),patch.object(S,'digest',return_value=digest),self.assertRaisesRegex(ValueError,'concurrent'):
                S.probe(3,self.ref,1000)

    def test_positive_name_spoof_only_blocks_never_exempts_and_no_signals(self):
        obj=types.SimpleNamespace(st_dev=5,st_ino=6,st_size=123)
        with patch.object(S,'hint',return_value=True),patch.object(S,'snapshot',return_value=self.snap),patch.object(os,'readlink',return_value='/usr/bin/python3'),patch.object(os,'open',return_value=4),patch.object(os,'close'),patch.object(os,'fstat',return_value=obj),patch.object(os,'stat',return_value=obj),self.assertRaisesRegex(ValueError,'indicator remains ambiguous'):
            S.probe(3,self.ref,1000)
        source=(HERE/'scoped_guard.py').read_text()
        self.assertNotIn('os.kill',source);self.assertNotIn('import subprocess',source);self.assertNotIn('ALLOWED=',source)

    def test_exit_race_and_dead_leader_with_workers(self):
        with patch.object(S,'hint',return_value=False),patch.object(S,'snapshot',side_effect=[self.snap,FileNotFoundError()]),patch.object(os,'readlink',side_effect=FileNotFoundError):
            self.assertEqual(S.probe(3,self.ref,1000),'EXITED')
        with patch.object(S,'hint',return_value=True),patch.object(S,'snapshot',return_value=dict(self.snap,state='Z',threads=2)),patch.object(os,'readlink',side_effect=FileNotFoundError),self.assertRaisesRegex(ValueError,'inaccessible'):
            S.probe(3,self.ref,1000)

    def test_registered_identity_uses_boot_start_inode_not_bare_pid(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve();record={'schema':1,'expected_game_sha256':S.GAME_SHA,'boot':'boot','pid':42,'start':12,'proc_dev':1,'proc_ino':2}
            f=p/'child-fixture.json';f.write_text(json.dumps(record));f.chmod(0o600)
            ctl=object.__new__(S.Control);ctl.path=p;ctl.boot='boot'
            # Only record metadata is real; proc identity is a synthetic observation.
            meta=types.SimpleNamespace(st_uid=f.stat().st_uid,st_mode=stat.S_IFREG|0o600,st_nlink=1)
            with patch.object(Path,'lstat',return_value=meta),patch.object(os,'getuid',return_value=meta.st_uid,create=True),patch.object(os,'open',return_value=3),patch.object(os,'close'):
                with patch.object(S,'snapshot',return_value=dict(self.snap,start=99)):ctl.check_children()
                with patch.object(S,'snapshot',return_value=self.snap),self.assertRaisesRegex(ValueError,'still live'):ctl.check_children()
                with patch.object(S,'snapshot',side_effect=PermissionError),self.assertRaises(PermissionError):ctl.check_children()
                record['start']='corrupt';f.write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError,'invalid recorded'):ctl.check_children()

    def test_target_file_model_rejects_privilege_bits_and_capabilities(self):
        for mode,cap in ((0o755,b''),(0o4755,b''),(0o775,b''),(0o755,b'capability')):
            obj=types.SimpleNamespace(st_uid=1000,st_mode=stat.S_IFREG|mode,st_size=100,st_dev=1,st_ino=2)
            with patch.object(os,'open',return_value=3),patch.object(os,'close'),patch.object(os,'fstat',return_value=obj),patch.object(os,'getuid',return_value=1000,create=True),patch.object(os,'getxattr',return_value=cap,create=True),patch.object(S,'digest',return_value=S.GAME_SHA):
                if mode==0o755 and not cap:self.assertEqual(S.identity(Path('/fixture'))['sha256'],S.GAME_SHA)
                else:
                    with self.assertRaises(ValueError):S.identity(Path('/fixture'))

    def test_caller_cannot_be_setuid_or_carry_capabilities(self):
        baseline=dict(self.snap,caps=0,permitted=0,ambient=0)
        for change in ({},{'uids':[1000,0,0,0]},{'caps':1},{'permitted':1},{'ambient':1}):
            with patch.object(os,'open',return_value=3),patch.object(os,'close'),patch.object(os,'getuid',return_value=1000,create=True),patch.object(S,'snapshot',return_value=dict(baseline,**change)):
                if change:
                    with self.assertRaisesRegex(ValueError,'unprivileged caller'):S.require_unprivileged()
                else:S.require_unprivileged()


@unittest.skipUnless(os.name=='posix','Linux locks/proc fixture')
class LinuxTests(unittest.TestCase):
    def test_two_cooperative_launches_and_stale_lock_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'control'
            with S.Control(p):
                with self.assertRaisesRegex(ValueError,'task lock'):S.Control(p).__enter__()
            ino=(p/'task.lock').stat().st_ino
            with S.Control(p):pass  # kernel releases locks, no stale PID-file lockout
            self.assertEqual((p/'task.lock').stat().st_ino,ino)

    def test_inherited_lock_survives_parent_close_and_child_registry_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'control';ctl=S.Control(p).__enter__()
            code='import os,sys;print("ready",flush=True);sys.stdin.readline();os.close(int(sys.argv[1]));print("closed",flush=True);sys.stdin.readline()'
            child=subprocess.Popen([sys.executable,'-B','-c',code,str(ctl.fd)],pass_fds=(ctl.fd,),stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'ready');image=os.stat(sys.executable);ctl.register(child,{'dev':image.st_dev,'ino':image.st_ino})
                self.assertFalse(ctl.registration_error)
                # Closing parent reference alone must NOT issue LOCK_UN.
                ctl.__exit__();self.assertRaisesRegex(ValueError,'task lock',S.Control(p).__enter__)
                child.stdin.write('close\n');child.stdin.flush();self.assertEqual(child.stdout.readline().strip(),'closed')
                with S.Control(p) as second:
                    with self.assertRaisesRegex(ValueError,'still live'):second.check_children()
                child.stdin.write('exit\n');child.stdin.flush();child.wait(timeout=5)
                with S.Control(p) as final:final.check_children()  # record kept, dead child not a lock
                self.assertTrue(list(p.glob('child-*.json')))
            finally:
                if ctl.fd is not None:ctl.__exit__()
                if child.poll() is None:child.kill();child.wait()
                child.stdin.close();child.stdout.close()

    def test_abrupt_launcher_exit_keeps_orphan_fixture_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'control'
            code='import os,sys,subprocess;sys.path.insert(0,sys.argv[1]);import scoped_guard as S;c=S.Control(__import__("pathlib").Path(sys.argv[2])).__enter__();p=subprocess.Popen([sys.executable,"-B","-c","import time;time.sleep(1.5)"],pass_fds=(c.fd,),stdout=subprocess.DEVNULL);s=os.stat(sys.executable);c.register(p,{"dev":s.st_dev,"ino":s.st_ino});print(p.pid,flush=True);os._exit(17)'
            parent=subprocess.Popen([sys.executable,'-B','-c',code,str(HERE),str(p)],stdout=subprocess.PIPE,text=True)
            try:
                self.assertTrue(parent.stdout.readline().strip().isdigit());self.assertEqual(parent.wait(timeout=5),17)
                with self.assertRaisesRegex(ValueError,'task lock'):S.Control(p).__enter__()
                import time
                time.sleep(1.7)
                with S.Control(p) as ctl:ctl.check_children()
            finally:parent.stdout.close()


if __name__=='__main__':unittest.main()
