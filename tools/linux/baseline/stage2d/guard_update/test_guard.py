"""Protected-process fixtures, real Linux proc metadata and isolated update tests. No game."""
import contextlib
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
import proc_guard as G
P=G.P


class Tests(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack()
        for n in ('O_CLOEXEC','O_NOFOLLOW','O_DIRECTORY'):
            self.stack.enter_context(patch.object(os,n,getattr(os,n,0),create=True))
        self.stack.enter_context(patch.object(os,'getuid',return_value=1000,create=True))
        self.before={'uids':[1000]*4,'start':123,'state':'S'}
        self.proc=types.SimpleNamespace(st_dev=1,st_ino=2)
        self.image=types.SimpleNamespace(st_dev=3,st_ino=4,st_size=5,st_uid=0,st_mode=stat.S_IFREG|0o755)

    def tearDown(self):self.stack.close()

    def proof(self,path):return {'pid':42,'start':123,'uids':[1000]*4,'proc_dev':1,'proc_ino':2,
        'executable':path,'root_service_inode_verified':True,'image_dev':3,'image_ino':4}

    def protected(self,allow=True,proof=None):
        with patch.object(P,'snapshot',return_value=self.before),patch.object(P,'dead',return_value=False),patch.object(os,'fstat',return_value=self.proc),patch.object(os,'readlink',side_effect=PermissionError),patch.object(G,'privileged',return_value=proof or self.proof(P.ALLOWED[0])):
            return G.inspect(3,42,(5,8,9),allow)

    def test_protected_system_processes_require_kernel_inode_proof_not_names(self):
        # sd-pam can use either supported systemd image; comm is not identity proof.
        for name,path in [('systemd',P.ALLOWED[0]),('(sd-pam)',P.ALLOWED[0]),('kwin_wayland',P.ALLOWED[1]),('polkit-kde-auth',P.ALLOWED[2]),('(sd-pam)',P.ALLOWED[3])]:
            with self.subTest(name=name):self.assertEqual(self.protected(proof=self.proof(path))['result'],'verified protected service')
        with self.assertRaisesRegex(ValueError,'administrator observer'):self.protected(False)

    def test_denial_unknown_service_and_spoofed_or_reused_identity_stop(self):
        for change in ({'executable':'/home/user/kwin_wayland'},{'root_service_inode_verified':False},
                       {'pid':43},{'start':124},{'proc_ino':99},{'uids':[999]*4}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.protected(proof=dict(self.proof(P.ALLOWED[0]),**change))
        with patch.object(G,'privileged',side_effect=PermissionError):
            # Missing elevation never becomes an exemption.
            with self.assertRaises(PermissionError):G.privileged(42,self.before,self.proc)

    def readable(self,path,digest='not-game',after=None,identity=(5,8,9),stat_after=None):
        with patch.object(P,'snapshot',side_effect=[self.before,after or self.before]),patch.object(P,'dead',return_value=False),patch.object(os,'fstat',side_effect=lambda fd:self.proc if fd==3 else self.image),patch.object(os,'readlink',return_value=path),patch.object(os,'open',return_value=4),patch.object(os,'close'),patch.object(os,'stat',return_value=stat_after or self.image),patch.object(G,'digest',return_value=digest):
            return G.inspect(3,42,identity,False)

    def test_concurrent_games_basename_inode_and_renamed_copy(self):
        for path,digest in (('/test/r3hd','not-game'),('/test/r3hd (deleted)','not-game'),('/test/systemd',G.GAME_SHA),('/test/systemd-executor',G.GAME_SHA)):
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,'concurrent'):self.readable(path,digest)
        self.assertEqual(self.readable('/usr/bin/other')['result'],'readable executable checked')
        with self.assertRaisesRegex(ValueError,'inode'):self.readable('/test/renamed',identity=(5,3,4))

    def test_state_scheduling_change_allowed_but_uid_or_start_race_stops(self):
        self.readable('/usr/bin/other',after=dict(self.before,state='R'))
        for after in (dict(self.before,start=999),dict(self.before,uids=[999]*4)):
            with self.assertRaisesRegex(ValueError,'identity changed'):self.readable('/usr/bin/other',after=after)
        changed=types.SimpleNamespace(**vars(self.image));changed.st_ino=999
        with self.assertRaisesRegex(ValueError,'exec raced'):self.readable('/usr/bin/other',stat_after=changed)

    def test_missing_exe_is_not_silently_an_exit_or_dead_leader_with_workers(self):
        for state in ('S','Z'):
            snap=dict(self.before,state=state)
            with patch.object(P,'snapshot',return_value=snap),patch.object(P,'dead',return_value=False),patch.object(os,'fstat',return_value=self.proc),patch.object(os,'readlink',side_effect=FileNotFoundError),self.assertRaisesRegex(ValueError,'live process'):
                G.inspect(3,42,(5,8,9),False)
        with patch.object(P,'snapshot',side_effect=[self.before,FileNotFoundError()]),patch.object(P,'dead',return_value=False),patch.object(os,'fstat',return_value=self.proc),patch.object(os,'readlink',side_effect=FileNotFoundError):
            self.assertEqual(G.inspect(3,42,(5,8,9),False)['result'],'bound process exited')

    def test_admin_observer_rejects_inode_mismatch_and_unknown_root_image(self):
        for path in ('/tmp/systemd',P.ALLOWED[0]):
            with patch.object(os,'geteuid',return_value=0,create=True),patch.object(os,'open',return_value=3),patch.object(os,'close'),patch.object(os,'fstat',return_value=self.proc),patch.object(P,'snapshot',return_value=self.before),patch.object(os,'readlink',return_value=path),patch.object(P,'trusted_path'):
                with self.assertRaises(ValueError):P.inspect(42,123,1000,99,99)
        with patch.object(os,'geteuid',return_value=0,create=True),patch.object(os,'open',return_value=3),patch.object(os,'close'),patch.object(os,'fstat',return_value=self.proc),patch.object(P,'snapshot',return_value=self.before),patch.object(os,'readlink',return_value='/tmp/kwin_wayland'),self.assertRaisesRegex(ValueError,'allowed service'):
            P.inspect(42,123,1000,1,2)

    def test_admin_observer_actually_binds_root_owned_service_image(self):
        for bad in (None,'writable','different inode','exec race'):
            image=types.SimpleNamespace(**vars(self.image))
            if bad=='writable':image.st_mode|=0o002
            known=types.SimpleNamespace(**vars(image))
            if bad=='different inode':known.st_ino=999
            after=types.SimpleNamespace(**vars(known))
            if bad=='exec race':after.st_ino=999
            with patch.object(os,'geteuid',return_value=0,create=True),patch.object(os,'open',side_effect=[3,4]),patch.object(os,'close'),patch.object(os,'fstat',side_effect=[self.proc,image]),patch.object(P,'snapshot',return_value=self.before),patch.object(os,'readlink',return_value=P.ALLOWED[1]),patch.object(P,'trusted_path') as trust,patch.object(os,'stat',side_effect=[known,after]):
                if bad:
                    with self.assertRaises(ValueError):P.inspect(42,123,1000,1,2)
                else:
                    self.assertTrue(P.inspect(42,123,1000,1,2)['root_service_inode_verified']);trust.assert_called_once_with(P.ALLOWED[1])

    def test_trusted_path_refuses_nonroot_or_writable_chain(self):
        path=str(Path.cwd()/'fixture-service')
        for uid,mode in ((0,stat.S_IFREG|0o755),(1000,stat.S_IFREG|0o755),(0,stat.S_IFREG|0o777)):
            with patch.object(Path,'resolve',lambda self,**kw:self),patch.object(Path,'lstat',return_value=types.SimpleNamespace(st_uid=uid,st_mode=mode)),patch.object(Path,'is_file',return_value=True):
                if uid==0 and not mode&0o022:P.trusted_path(path)
                else:
                    with self.assertRaisesRegex(ValueError,'untrusted'):P.trusted_path(path)

    def test_observer_invocation_is_fixed_isolated_no_bytecode_numeric_arguments(self):
        result=self.proof(P.ALLOWED[0])
        with patch.object(P,'trusted_path'),patch.object(Path,'resolve',return_value=Path('/usr/bin/python3')),patch.object(subprocess,'run',return_value=types.SimpleNamespace(stdout=json.dumps(result))) as run:
            self.assertEqual(G.privileged(42,self.before,self.proc),result)
            args=run.call_args.args[0];self.assertEqual(args[:7],['/usr/bin/sudo','--','/usr/bin/python3','-I','-S','-B','-c'])
            self.assertEqual(args[-5:],['42','123','1000','1','2']);self.assertNotIn('shell',run.call_args.kwargs)

    @unittest.skipUnless(os.name=='posix','Linux proc fd test')
    def test_actual_bound_proc_snapshot_no_game_or_privilege(self):
        fd=os.open('/proc/self',os.O_RDONLY|os.O_DIRECTORY)
        try:
            s=P.snapshot(fd);self.assertGreater(s['start'],0);self.assertEqual(len(s['uids']),4)
            image=os.open('exe',os.O_RDONLY,dir_fd=fd)
            try:self.assertTrue(stat.S_ISREG(os.fstat(image).st_mode))
            finally:os.close(image)
        finally:os.close(fd)

    @unittest.skipUnless(os.name=='posix','Linux proc exit race test')
    def test_actual_bound_fd_after_non_game_child_exit_does_not_follow_reused_pid(self):
        child=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(30)'])
        try:
            fd=os.open('/proc/'+str(child.pid),os.O_RDONLY|os.O_DIRECTORY)
            try:
                child.terminate();child.wait(timeout=5)
                with self.assertRaises((FileNotFoundError,ProcessLookupError)):P.snapshot(fd)
            finally:os.close(fd)
        finally:
            if child.poll() is None:child.kill();child.wait()


if __name__=='__main__':unittest.main()
