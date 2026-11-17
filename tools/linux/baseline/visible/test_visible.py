"""Preparation fixtures only. Never execute the target, SDL or GPU."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile
import visible as V
R=V.R;C=V.C
ROOT=Path(__file__).resolve().parents[4]
EVIDENCE=ROOT/'private/work/linux_build/stage2c_native_startup_evidence_20261109/startup-private-evidence.zip'


class Tests(unittest.TestCase):
    def test_actual_returned_evidence_and_tampering(self):
        self.assertEqual(R.review(EVIDENCE)['runtime_guest'],'NOT REACHED')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/EVIDENCE.name;p.write_bytes(EVIDENCE.read_bytes()+b'changed')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):R.review(p)
        with patch.dict(R.LOCK,zip_sha256=C.sha(EVIDENCE)):
            lock=dict(R.LOCK['members']);lock['wayland/exit.json']='0'*64
            with patch.dict(R.LOCK,members=lock),self.assertRaisesRegex(ValueError,'startup member'):R.review(EVIDENCE)

    def test_pinned_message_and_window_mapping_sources(self):
        texts={}
        for name,row in R.LOCK['source_facts'].items():
            repo='external/rexglue-sdk/thirdparty/sdl3' if '/thirdparty/sdl3/' in name else 'external/rexglue-sdk'
            raw=subprocess.check_output(['git','-C',str(ROOT/repo),'show',row['commit']+':'+name[len(repo)+1:]])
            self.assertEqual(C.digest(raw),row['sha256']);texts[name]=raw.decode()
        posix=texts['external/rexglue-sdk/src/core/system_posix.cpp']
        self.assertIn('std::fprintf(stderr',posix);self.assertNotIn('SDL_ShowSimpleMessageBox(',posix)
        main=texts['external/rexglue-sdk/src/ui/windowed_app_main_sdl.cpp']
        self.assertIn('app->OnInitialize() ? app_context.RunMainMessageLoop() : EXIT_FAILURE',main)
        sdl=texts['external/rexglue-sdk/thirdparty/sdl3/src/video/wayland/SDL_waylandwindow.c']
        self.assertIn('wl_surface_attach(data->surface, NULL, 0, 0);',sdl)

    def test_no_automatic_authorization_or_retry(self):
        for terminal,present,answer in ((False,True,''),(True,False,''),(True,True,'yes')):
            with patch.object(V.N,'native'),patch.object(sys.stdin,'isatty',return_value=terminal),patch('builtins.input',return_value=answer),patch.object(V.N,'launch') as launch:
                with self.assertRaises(ValueError):V.human(present)
                launch.assert_not_called()

    def test_program_integrity_refuses_extra_config_and_edit(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'bin').mkdir();(p/'app').mkdir();(p/'bin/r3hd').write_bytes(b'fixture')
            expected={'bin/r3hd':C.sha(p/'bin/r3hd')}
            with patch.object(V.N,'archive_inventory',return_value=expected):
                V.programs(p,None)
                (p/'bin/r3hd.toml').write_text('unexpected')
                with self.assertRaisesRegex(ValueError,'unexpected program'):V.programs(p,None)
                (p/'bin/r3hd').write_bytes(b'edit')
                with self.assertRaisesRegex(ValueError,'hash mismatch'):V.programs(p,None)

    def test_judge_requires_visual_observation_and_natural_zero(self):
        text='\n'.join(('SDL video driver: wayland',"GPU plugin 'xenos' loaded",'VulkanPresenter: Created',
            'M2 xex_loaded entry=820E13F8','M2 runtime_initialized','M2 launch_prepared','M11 pacing series=host_present'))
        self.assertEqual(V.judge(0,False,text,'yes')['status'],'PASS')
        for code,forced,log,seen in ((1,False,text,'yes'),(-11,False,text,'yes'),(0,True,text,'yes'),(0,False,text,'no'),(0,False,text.replace('M2 xex_loaded','absent'),'yes'),(0,False,text+' VK_LAYER_LS_frame_generation','yes'),(0,False,text+' VK_ERROR_DEVICE_LOST','yes')):
            self.assertEqual(V.judge(code,forced,log,seen)['status'],'FAIL')
        self.assertEqual(V.judge(0,False,text,'yes')['gameplay_acceptance'],'UNKNOWN')

    def test_prepare_uses_explicit_package_no_game_entry_and_preserves_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve();source=p/'owned-package';source.write_bytes(b'fixture package');dest=p/'new-work'
            out=p/'out';out.mkdir();package=out/C.PACKAGE;package.write_bytes(b'fixture archive')
            def extract(package,abi,install=None):
                if install:
                    (install/'app/tools').mkdir(parents=True);(install/'app/tools/r3hd_portable.py').write_text('# fixture')
            def command(args,**kw):
                self.assertIn('prepare',args);self.assertIn('--no-input',args);self.assertEqual(args[-1],str(source))
                self.assertNotIn('WAYLAND_DISPLAY',kw['env']);self.assertNotIn('DISPLAY',kw['env'])
                f=dest/'installation/data/content/Default.xex';f.parent.mkdir(parents=True);f.write_bytes(b'fixture')
                kw['stdout'].write('R3HD_PORTABLE READY {}');return types.SimpleNamespace(returncode=0)
            with patch.object(V.N,'native'),patch.object(V,'receipt'),patch.object(V.N,'inputs',return_value=(out,{})),patch.object(V,'root',return_value=dest),patch.object(C,'package_files',side_effect=extract),patch.object(V,'programs'),patch.object(C,'file_hash'),patch.dict(R.LOCK,raw_package_size=source.stat().st_size),patch.object(V.subprocess,'run',side_effect=command),patch.object(V.N,'launch') as launch,patch.object(V.shutil,'disk_usage',return_value=types.SimpleNamespace(free=12_000_000_000)):
                with patch.object(V.shutil,'disk_usage',return_value=types.SimpleNamespace(free=11_999_999_999)):
                    with self.assertRaisesRegex(ValueError,'available bytes'):V.prepare(source)
                    self.assertFalse(dest.exists())
                V.prepare(source);launch.assert_not_called()
                with self.assertRaisesRegex(ValueError,'exists'):V.prepare(source)
            self.assertEqual(source.read_bytes(),b'fixture package')
            self.assertFalse(C.read_json((dest/'prepared.json').read_bytes())['game_executed'])

    def test_attended_fixture_argv_environment_and_single_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve();install=p/'installation';(install/'bin').mkdir(parents=True);(install/'data').mkdir()
            (p/'OWNER.txt').write_text('R3HD_STAGE2C_VISIBLE_01')
            C.write(p/'prepared.json',{'game_executed':False,'unattended_authorized':False,'package_sha256':C.LOCK['package_sha256'],'data_inventory':{}})
            abi={n:{'sha256':'0'*64} for n in C.COMPONENTS}
            def env(folder,mode):
                self.assertEqual(mode,'wayland');return {'HOME':str(folder),'WAYLAND_DISPLAY':'/fixture/socket'}
            def run(args,**kw):
                if 'verify' in args:
                    kw['stdout'].write('{"result":"supported","kind":"tree","files":915,"missing":[],"extra":[],"wrong_size":[],"wrong_hash":[]}')
                else:self.assertEqual(args[1],'--list')
                return types.SimpleNamespace(returncode=0)
            def launch(args,folder,environment,seconds):
                self.assertEqual(seconds,120);self.assertEqual(environment['DISABLE_LSFG'],'1')
                self.assertNotIn('R3HD_PLAY',environment);self.assertNotIn('R3HD_NONINTRUSIVE',environment)
                self.assertIn('--fullscreen=false',args);self.assertIn('--video_driver=wayland',args)
                self.assertIn('--user_data_root='+str(p/'test-user'),args)
                (p/'runtime.log').write_text('SDL video driver: wayland\nGPU plugin \'xenos\' loaded\nVulkanPresenter: Created\nM2 xex_loaded entry=820E13F8\nM2 runtime_initialized\nM2 launch_prepared\nM11 pacing series=host_present')
                return 0,False
            with patch.object(V.N,'native'),patch.object(V,'root',return_value=p),patch.object(V,'receipt'),patch.object(V.N,'inputs',return_value=(p,abi)),patch.object(V,'programs'),patch.object(C,'file_hash'),patch.object(V.N,'environment',side_effect=env),patch.object(sys.stdin,'isatty',return_value=True),patch('builtins.input',side_effect=['AUTHORIZE VISIBLE AUDIO INPUT STARTUP','yes','AUTHORIZE VISIBLE AUDIO INPUT STARTUP']),patch.object(V.subprocess,'run',side_effect=run),patch.object(V.N,'launch',side_effect=launch):
                V.human(True)
                with self.assertRaisesRegex(ValueError,'attempt exists'):V.human(True)
            self.assertEqual(C.read_json((p/'result.json').read_bytes())['status'],'PASS')

    def test_collector_excludes_data_profiles_installations(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve();(p/'OWNER.txt').write_text('R3HD_STAGE2C_VISIBLE_01');(p/'runtime.log').write_text('technical fixture')
            (p/'test-user').mkdir();(p/'test-user/save').write_text('do not transfer');(p/'installation').mkdir();(p/'installation/copyrighted').write_text('fixture')
            with patch.object(V,'root',return_value=p):
                V.collect()
                with self.assertRaisesRegex(ValueError,'exists'):V.collect()
            with zipfile.ZipFile(p/'visible-private-evidence.zip') as z:self.assertEqual(set(z.namelist()),{'OWNER.txt','runtime.log'})

    def test_authoritative_content_check_refuses_failure_or_bad_receipt(self):
        valid='{"result":"supported","kind":"tree","files":915,"missing":[],"extra":[],"wrong_size":[],"wrong_hash":[]}'
        for code,text in ((0,valid),(2,valid),(0,valid.replace('915','914')),(0,valid.replace('"wrong_hash":[]','"wrong_hash":["tampered"]')),(0,'R3HD_INTAKE '+valid)):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);(p/'installation').mkdir()
                def run(args,**kw):
                    self.assertIn('verify',args);self.assertIn('--json',args)
                    kw['stdout'].write(text);return types.SimpleNamespace(returncode=code)
                with patch.object(V.subprocess,'run',side_effect=run):
                    if code==0 and text==valid:V.content_check(p,{},'before')
                    else:
                        with self.assertRaises(ValueError):V.content_check(p,{},'before')


if __name__=='__main__':unittest.main()
