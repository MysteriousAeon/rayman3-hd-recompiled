"""Stage2D fixtures only; never executes r3hd, SDL or audio."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import gameplay as G


class Tests(unittest.TestCase):
    def observations(self):return dict.fromkeys(G.QUESTIONS,'yes')|{'anomaly':'no','anomaly_kind':'none','exit_method':'window-x','furthest_location':'intro_10'}
    def machine(self):return {'startup_markers':{'wayland':True},'audio_endpoint_opens':2,'stream_open_failures':0,
        'guest_fatal':False,'device_lost':False,'unexpected_error_lines':0,'lsfg_active':False,'sdk_hard_exit':True}

    def test_independent_gates_no_save_or_intro15_requirement(self):
        r=G.verdict(self.machine(),self.observations(),0,None,True,{}, {},'a')
        self.assertTrue(r['phase_A_eligible']);self.assertEqual(r['F_save_write'],'NOT ESTABLISHED')
        self.assertEqual(r['F_saved_progress_load'],'NOT ESTABLISHED')
        o=self.observations();o['jump']='unknown'
        r=G.verdict(self.machine(),o,0,None,True,{}, {},'a')
        self.assertEqual(r['A_startup_menu'],'PASS');self.assertEqual(r['C_human_actions'],'NOT ESTABLISHED');self.assertFalse(r['phase_A_eligible'])

    def test_fatal_or_forced_exit_blocks_phaseB_without_erasing_observations(self):
        for code,reason,integrity in ((-5,None,True),(0,'LOG_BUDGET',True),(0,None,False)):
            r=G.verdict(self.machine(),self.observations(),code,reason,integrity,{}, {},'a')
            self.assertFalse(r['phase_A_eligible']);self.assertEqual(r['B_natural_gameplay'],'PASS')
        m=self.machine();m['guest_fatal']=True
        self.assertFalse(G.verdict(m,self.observations(),0,None,True,{}, {},'a')['phase_A_eligible'])

    def test_real_save_type_metadata_not_settings_and_genuine_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);user=p/'test-user';user.mkdir();(user/'settings.json').write_text('fixture')
            self.assertEqual(G.saves(p),{})
            f=user/'1234567890ABCDEF/5841123F/00000001/slot/save';f.parent.mkdir(parents=True);f.write_bytes(b'fixture')
            s=G.saves(p);self.assertEqual(len(s),1)
            r=G.verdict(self.machine(),self.observations(),0,None,True,{},s,'a');self.assertEqual(r['F_save_write'],'PASS')
            o=self.observations();o['loaded_progress']='no'
            self.assertEqual(G.verdict(self.machine(),o,0,None,True,s,s,'load')['F_saved_progress_load'],'NOT ESTABLISHED')
            self.assertEqual(G.verdict(self.machine(),self.observations(),0,None,True,s,s,'load')['F_saved_progress_load'],'PASS')

    def test_no_unattended_or_failedA_launch(self):
        with patch.object(G.N,'native'),patch.object(sys.stdin,'isatty',return_value=False),patch.object(G,'launch') as launch:
            with self.assertRaisesRegex(ValueError,'realTTY'):G.run('a',True)
            launch.assert_not_called()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'a').mkdir();G.C.write(p/'a/result.json',{'phase_A_eligible':False})
            with patch.object(G.N,'native'),patch.object(sys.stdin,'isatty',return_value=True),patch.object(G,'workspace',return_value=p),patch.object(G,'launch') as launch:
                with self.assertRaisesRegex(ValueError,'Phase A'):G.run('save',True)
                launch.assert_not_called()

    def test_existing_game_refusal_never_kills_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'123').mkdir()
            with patch.object(os,'getuid',return_value=1000,create=True),patch.object(Path,'stat',return_value=types.SimpleNamespace(st_uid=1000)),patch.object(os,'readlink',return_value='/test/r3hd'),patch.object(os,'kill',create=True) as kill:
                with self.assertRaisesRegex(ValueError,'another game'):G.no_other_game(p)
                kill.assert_not_called()

    def test_prepare_uses_verified_cow_data_only_and_starts_no_game(self):
        for failure in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp).resolve();old=p/'Projects/R3HD-baseline-noble-2c-pulse-01/installation/data'
                old.mkdir(parents=True);(old/'fixture').write_text('fixture');dest=p/'Projects/new';out=p/'artifacts';out.mkdir()
                plan={'data_inventory':{'fixture':G.C.sha(old/'fixture')},'source_sha256':'fixture'}
                def files(package,abi,install=None):
                    if install:(install/'bin').mkdir()
                def clone(args,**kw):
                    self.assertIn('--reflink=always',args);self.assertNotIn('--link',args)
                    if failure:raise subprocess.CalledProcessError(1,args)
                    shutil.copytree(args[-2],args[-1])
                with patch.object(G.N,'native'),patch.object(G,'native_checkpoint',return_value=plan),patch.object(G.N,'inputs',return_value=(out,{})),patch.object(G,'root',return_value=dest),patch.object(Path,'home',return_value=p),patch.object(G.shutil,'disk_usage',return_value=types.SimpleNamespace(free=12_000_000_000)),patch.object(G.A,'host_audio',return_value={}),patch.object(G.C,'package_files',side_effect=files),patch.object(G.subprocess,'run',side_effect=clone),patch.object(G.V,'programs'),patch.object(G.V,'content_check'),patch.object(G,'launch') as launch:
                    if failure:
                        with self.assertRaises(subprocess.CalledProcessError):G.prepare(old)
                    else:
                        G.prepare(old)
                        with self.assertRaisesRegex(ValueError,'fresh'):G.prepare(old)
                    launch.assert_not_called()
                self.assertEqual((old/'fixture').read_text(),'fixture')

    def test_machine_info_logs_no_d3d_marker_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'runtime.log').write_text("M2 host_start\nM2 runtime_initialized\naudio endpoint 'fixture'\nWindow closing, shutting down...\nTitle terminated; hard-exiting process.")
            m=G.machine(p);self.assertEqual(m['audio_endpoint_opens'],1);self.assertEqual(m['gpu_present_path_debug_records'],0)
            self.assertIn('NOT MEASURED',m['host_pacing'])
            with (p/'runtime.log').open('a') as f:f.write('\n(service trap) R6025\n[error] unexpected')
            self.assertTrue(G.machine(p)['guest_fatal']);self.assertEqual(G.machine(p)['unexpected_error_lines'],1)

    def test_pinned_sdk_logging_limits_and_saved_game_layout(self):
        repo=G.HERE.parents[3]/'external/rexglue-sdk';pin='c94f5ebdcb3c9d1a460ca48e04f9758448f8d518'
        def source(name):return subprocess.check_output(['git','-C',str(repo),'show',pin+':'+name]).decode()
        log=source('src/core/logging.cpp')
        for name in ('log_max_file_size_mb','log_max_files','log_level','log_flush_interval'):self.assertIn(name,log)
        self.assertIn('kSavedGame = 0x00000001',source('include/rex/system/xcontent.h'))
        self.assertIn('root_path_ / xuid_str / title_id_str / content_type_str',source('src/system/xam/content_manager.cpp'))

    def test_rotation_growth_counts_writes_without_double_counting_rename(self):
        with tempfile.TemporaryDirectory(dir=G.HERE.parents[3]/'private/work/linux_build') as tmp:
            p=Path(tmp);f=p/'runtime.log';f.write_bytes(b'1234');seen={}
            self.assertEqual(G.log_growth(p,seen),4);self.assertEqual(G.log_growth(p,seen),0)
            f.rename(p/'runtime.1.log');f.write_bytes(b'123')
            self.assertEqual(G.log_growth(p,seen),3)

    def test_same_private_home_and_audio_route_across_phases(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve()
            def env(folder,mode):(folder/'os-home').mkdir();return {'HOME':str(folder/'os-home'),'XDG_RUNTIME_DIR':'dummy','WAYLAND_DISPLAY':'/owned/wayland'}
            with patch.object(G.N,'environment',side_effect=env),patch.object(G.A,'host_audio',return_value={'socket':'/run/user/1000/pulse/native'}):
                envs=[]
                for n in ('a','load'):
                    folder=p/n;folder.mkdir();envs.append(G.environment(p,folder))
                self.assertEqual(envs[0],envs[1]);self.assertEqual(envs[0]['SDL_AUDIO_DRIVER'],'pulseaudio')
                self.assertEqual(envs[0]['HOME'],str(p/'session-home'))

    def test_export_excludes_saves_raw_logs_paths_and_cache_collision_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve();(p/'OWNER.txt').write_text(G.OWNER);G.C.write(p/'prepared-receipt.json',{'execution':'NOT RUN'})
            for name in ('test-user/save','session-home/secret','a/runtime.log','a/saves-after-local.json','installation/data/content/game'):
                f=p/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('private fixture')
            with patch.object(G,'root',return_value=p):
                G.collect()
                with self.assertRaisesRegex(ValueError,'exists'):G.collect()
            with G.zipfile.ZipFile(p/'stage2d-private-evidence.zip') as z:
                self.assertEqual(set(z.namelist()),{'OWNER.txt','prepared-receipt.json','SHA256SUMS'})

    @unittest.skipUnless(os.name=='posix','POSIX owned child fixture only')
    def test_supervisor_owned_non_game_child_exit_and_log_budget(self):
        for cap in (G.LOG_BUDGET,0):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp).resolve();(p/'installation/bin').mkdir(parents=True);f=p/'a';f.mkdir()
                with patch.object(G,'root',return_value=p),patch.object(G,'LOG_BUDGET',cap):
                    code,reason=G.launch([sys.executable,'-B','-c','import time;time.sleep(.1)'],f,{'PATH':'/usr/bin:/bin'})
                if cap:self.assertEqual((code,reason),(0,None))
                else:self.assertEqual(reason,'LOG_BUDGET');self.assertNotEqual(code,0)


if __name__=='__main__':unittest.main()
