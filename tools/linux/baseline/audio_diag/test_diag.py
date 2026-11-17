"""Evidence/source review and isolated fixtures; no target, SDL or audio execution."""
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import signal
import tempfile
import types
import unittest
import zipfile
from unittest.mock import patch
import audio_diag as A
F=A.F;V=A.V;C=A.C;N=A.N
ROOT=Path(__file__).resolve().parents[4]
EVIDENCE=ROOT/'private/work/linux_build/stage2c_visible_native_evidence_20261109/visible-private-evidence.zip'


class Tests(unittest.TestCase):
    def tearDown(self):
        N.environment=A.BASE_ENV;V.judge=A.BASE_JUDGE

    def test_full_actual_failure_and_altered_archive_refused(self):
        result=F.review(EVIDENCE)
        self.assertEqual(result['exit'],-5);self.assertEqual(result['gpu_present_path_records'],5)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/EVIDENCE.name;p.write_bytes(EVIDENCE.read_bytes()+b'edit')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):F.review(p)
        members=dict(F.LOCK['members']);members['exit.json']='0'*64
        with patch.dict(F.LOCK,members=members),self.assertRaisesRegex(ValueError,'member'):F.review(EVIDENCE)

    def test_pinned_failure_chain_and_audio_backend_selection_sources(self):
        texts={}
        for name,row in F.LOCK['source_facts'].items():
            sub=name.startswith('thirdparty/sdl3/');repo=ROOT/'external/rexglue-sdk'/('thirdparty/sdl3' if sub else '')
            raw=subprocess.check_output(['git','-C',str(repo),'show',row['commit']+':'+(name.removeprefix('thirdparty/sdl3/') if sub else name)])
            self.assertEqual(C.digest(raw),row['sha256']);texts[name]=raw.decode()
        self.assertIn('std::raise(SIGTRAP)',texts['src/core/dbg_posix.cpp'])
        self.assertIn('rex::debug::Break()',texts['src/kernel/xboxkrnl/xboxkrnl_debug.cpp'])
        self.assertIn('return X_STATUS_UNSUCCESSFUL;',texts['src/audio/sdl/sdl_audio_system.cpp'])
        self.assertIn('return result;',texts['src/audio/audio_system.cpp'])
        self.assertIn('PULSEAUDIO_pa_context_connect(pulseaudio_context, NULL, 0, NULL)',texts['thirdparty/sdl3/src/audio/pulseaudio/SDL_pulseaudio.c'])
        self.assertIn('#define SDL_HINT_AUDIO_DRIVER "SDL_AUDIO_DRIVER"',texts['thirdparty/sdl3/include/SDL3/SDL_hints.h'])

    def test_authenticated_successful_comparison_only_exact_probe_is_benign(self):
        row=F.LOCK['comparison_log'];p=ROOT/row['path'];C.file_hash(p,row['sha256']);log=p.read_text()
        self.assertIn("audio endpoint '",log)
        harmless='[2026-11-06 23:22:30.907] [error] [fs] [t11512] ResolvePath(\\D:\\Gamedata) failed - device not found'
        self.assertIn(harmless,log)
        milestones='SDL video driver: wayland\nGPU plugin \'xenos\' loaded\nVulkanPresenter: Created\nM2 xex_loaded entry=820E13F8\nM2 runtime_initialized\nM2 launch_prepared\nM11 pacing series=host_present'
        self.assertEqual(V.judge(0,False,milestones+'\n'+harmless,'yes')['status'],'PASS')
        for error in (harmless.replace('Gamedata','Other'),harmless.replace('[fs]','[apu]'),harmless+' extra','[error] SDL_OpenAudioDeviceStream() failed'):
            self.assertEqual(V.judge(0,False,milestones+'\n'+error,'yes')['status'],'FAIL')
        self.assertEqual(V.judge(-5,False,milestones+'\n'+harmless,'no')['status'],'FAIL')

    def test_audio_metadata_guard_socket_owner_and_runtime_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve();(p/'pulse').mkdir();s=p/'pulse/native';s.write_bytes(b'not a socket')
            version=types.SimpleNamespace(restype=None,__call__=None)
            fn=lambda:b'17.0'
            lib=types.SimpleNamespace(pa_get_library_version=fn)
            with patch.dict(os.environ,XDG_RUNTIME_DIR=str(p)),patch.object(os,'getuid',return_value=1000,create=True),patch.object(Path,'stat',return_value=types.SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=1000)):
                with self.assertRaisesRegex(ValueError,'socket'):A.host_audio()
            def st(path,*args,**kwargs):return types.SimpleNamespace(st_mode=(stat.S_IFDIR|0o700 if path==p else stat.S_IFSOCK|0o600),st_uid=1000)
            with patch.dict(os.environ,XDG_RUNTIME_DIR=str(p)),patch.object(os,'getuid',return_value=1000,create=True),patch.object(Path,'stat',st),patch.object(Path,'resolve',lambda self:self),patch.object(A.ctypes,'CDLL',return_value=lib):
                self.assertTrue(A.host_audio()['metadata_only'])
            with patch.dict(os.environ,XDG_RUNTIME_DIR='relative'),self.assertRaisesRegex(ValueError,'absolute'):A.host_audio()

    def test_route_preserves_private_home_and_only_explicit_audio_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);folder=p/'launch';folder.mkdir();(folder/'os-home').mkdir()
            env={'HOME':str(folder/'os-home'),'XDG_RUNTIME_DIR':str(folder/'os-home/run'),'WAYLAND_DISPLAY':'/owned/wayland'}
            with patch.object(A,'BASE_ENV',return_value=dict(env)),patch.object(A,'host_audio',return_value={'socket':'/run/user/1000/pulse/native','metadata_only':True}),patch.object(A,'root',return_value=p):
                actual=A.routed_environment(folder,'wayland')
            self.assertEqual(actual['HOME'],env['HOME']);self.assertEqual(actual['XDG_RUNTIME_DIR'],env['XDG_RUNTIME_DIR'])
            self.assertEqual(actual['SDL_AUDIO_DRIVER'],'pulseaudio');self.assertEqual(actual['PULSE_SERVER'],'unix:/run/user/1000/pulse/native')
            self.assertNotIn('autospawn = yes',Path(actual['PULSE_CLIENTCONFIG']).read_text())

    def test_preparation_clones_only_verified_content_and_no_fallback(self):
        for failure in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp).resolve();old=p/'old';source=old/'installation/data';(source/'content').mkdir(parents=True);(source/'content/Default.xex').write_bytes(b'fixture')
                dest=p/'new';out=p/'artifacts';out.mkdir()
                prep={'data_inventory':{'content/Default.xex':C.sha(source/'content/Default.xex')},'source_sha256':'fixture'};C.write(old/'prepared.json',prep)
                def files(package,abi,install=None):
                    if install:(install/'bin').mkdir()
                def clone(args,**kw):
                    self.assertIn('--reflink=always',args);self.assertNotIn('--link',args)
                    if failure:raise subprocess.CalledProcessError(1,args)
                    shutil.copytree(args[-2],args[-1])
                with patch.object(N,'native'),patch.object(A,'evidence'),patch.object(N,'inputs',return_value=(out,{})),patch.object(A,'root',return_value=dest),patch.object(A,'prior',return_value=old),patch.object(C,'file_hash'),patch.object(A,'host_audio',return_value={'metadata_only':True}),patch.object(A.shutil,'disk_usage',return_value=types.SimpleNamespace(free=12_000_000_000)),patch.object(C,'package_files',side_effect=files),patch.object(A.subprocess,'run',side_effect=clone),patch.object(V,'programs'),patch.object(V,'content_check'),patch.object(N,'launch') as launch:
                    if failure:
                        with self.assertRaises(subprocess.CalledProcessError):A.prepare(source)
                    else:
                        A.prepare(source)
                        with self.assertRaisesRegex(ValueError,'exists'):A.prepare(source)
                    launch.assert_not_called()
                self.assertEqual((source/'content/Default.xex').read_bytes(),b'fixture')

    def test_no_unattended_authorization_and_diagnostic_strictness(self):
        with patch.object(N,'native'),patch.object(sys.stdin,'isatty',return_value=False),patch.object(V,'human') as human:
            with self.assertRaisesRegex(ValueError,'realTTY'):A.human(True)
            human.assert_not_called()
        with patch.object(A,'BASE_JUDGE',return_value={'status':'PASS'}):
            self.assertEqual(A.judge(0,False,'audio endpoint opened','yes')['status'],'PASS')
        for text in ('no endpoint','audio endpoint opened (service trap) R6025'):
            with patch.object(A,'BASE_JUDGE',return_value={'status':'PASS'}):self.assertEqual(A.judge(0,False,text,'yes')['status'],'FAIL')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for n,text in (('process.log','early'),('runtime.2.log','old audio endpoint opened'),('runtime.1.log','middle'),('runtime.log','latest')):(p/n).write_text(text)
            def assembled(code,forced,text,seen):
                self.assertEqual(text,'early\nold audio endpoint opened\nmiddle\nlatest');return {'status':'PASS'}
            with patch.object(A,'root',return_value=p),patch.object(A,'BASE_JUDGE',side_effect=assembled):self.assertEqual(A.judge(0,False,'current only','yes')['status'],'PASS')

    @unittest.skipUnless(os.name=='posix','POSIX signal receipt fixture')
    def test_non_game_signal_child_is_not_timeout_or_natural_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'installation/bin').mkdir(parents=True)
            code,forced=N.launch([sys.executable,'-B','-c','import os,signal;os.kill(os.getpid(),signal.SIGTRAP)'],p,{'PATH':'/usr/bin:/bin'},5)
            self.assertEqual(code,-signal.SIGTRAP);self.assertFalse(forced)

    def test_collector_never_includes_content_homes_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve();(p/'OWNER.txt').write_text('R3HD_STAGE2C_VISIBLE_01');C.write(p/'audio-route.json',{'metadata_only':True});(p/'runtime.1.log').write_text('older technical log')
            for n in ('installation/data/content/copyrighted','test-user/save','test-cache/shader','launch-environment/os-home/private'):
                f=p/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('fixture')
            old=V.root
            try:
                with patch.object(A,'root',return_value=p):
                    A.collect()
                    with self.assertRaisesRegex(ValueError,'exists'):A.collect()
            finally:V.root=old
            with zipfile.ZipFile(p/'pulse-private-evidence.zip') as z:self.assertEqual(set(z.namelist()),{'OWNER.txt','audio-route.json','runtime.1.log'})


if __name__=='__main__':unittest.main()
