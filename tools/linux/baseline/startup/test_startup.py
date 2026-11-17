"""Read-only source/evidence checks and isolated fixtures; never invoke target ELF."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile
import supplements as S
import startup as N
import source_audit as A
C=S.C
HERE=Path(__file__).resolve().parent
ROOT=Path(__file__).resolve().parents[4]


class StartupTests(unittest.TestCase):
    def test_wsl_is_refused_for_target_preparation_and_execution(self):
        with patch.object(N.platform,'system',return_value='Linux'),patch.object(N.platform,'machine',return_value='x86_64'),patch.object(N.os,'getuid',return_value=1000,create=True),patch.object(Path,'read_text',return_value='6.6-microsoft-standard-WSL2'):
            with self.assertRaisesRegex(ValueError,'WSL target execution prohibited'):N.native()

    def test_prepare_and_attended_command_fixture_preserve_sources(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('final_fixture',HERE.parent/'finalize/test_final.py')
        F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve();out=p/'source';out.mkdir();source,package,files,abi,_=F.fixture(out)
            dest=p/'test-home';before=C.sha(package)
            with patch.object(N,'native'),patch.object(N,'root',return_value=dest),patch.object(N,'inputs',return_value=(out,abi)),patch.dict(C.LOCK,lgpl_sha256=C.sha(source)):
                N.prepare()
                with self.assertRaisesRegex(ValueError,'exists'):N.prepare()
                def run(args,**kw):
                    self.assertEqual(args[1],'--list');return types.SimpleNamespace(returncode=0)
                def launch(args,folder,env,seconds):
                    self.assertEqual(seconds,15);self.assertEqual(args[1],'--video_driver='+N.TOKEN)
                    self.assertIn('--fullscreen=false',args);self.assertIn('--gpu_plugin=xenos',args)
                    self.assertFalse(any(k in env for k in ('DISPLAY','WAYLAND_DISPLAY','LD_PRELOAD','R3HD_PLAY')))
                    self.assertTrue(any(a.startswith('--game_data_root=') and 'absent-game-data' in a for a in args if isinstance(a,str)))
                    (folder/'process.log').write_text('SDL_InitSubSystem(SDL_INIT_VIDEO) failed: '+N.TOKEN+' not available')
                    return 1,False
                with patch.object(sys.stdin,'isatty',return_value=True),patch('builtins.input',return_value='AUTHORIZE ATTENDED REJECT'),patch.object(N.subprocess,'run',side_effect=run),patch.object(N,'launch',side_effect=launch):
                    N.human('reject',True)
                    with self.assertRaisesRegex(ValueError,'attempt already exists'):N.human('reject',True)
                self.assertFalse(C.read_json((dest/'reject/result.json').read_bytes())['normal_startup_pass'])
            self.assertEqual(C.sha(package),before)
            changed=dest/'reject/installation/extra';changed.write_bytes(b'not from archive')
            self.assertNotEqual(N.inventory(changed.parent),N.archive_inventory(package))

    def test_native_supplements_all_hashes_and_assertions(self):
        p=ROOT/'private/work/linux_build/stage2b_native_evidence_20261109'
        result=S.review(p/'finalization/supplemental-private-evidence.zip',p/'stage2c/supplemental-private-evidence.zip')
        self.assertEqual(result['original_orchestration_exit'],2);self.assertEqual(result['game_entrypoint'],'NOT EXECUTED')
        with tempfile.TemporaryDirectory() as tmp:
            copy=Path(tmp)/'supplemental-private-evidence.zip';copy.write_bytes((p/'stage2c'/copy.name).read_bytes()+b'edit')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):S.archive(copy,'stage2c')

    def test_pinned_startup_source_order_and_no_safe_help_assumption(self):
        self.assertEqual(A.audit()['unattended_startup'],'NOT ESTABLISHED')

    def test_no_unattended_or_noninteractive_authorization(self):
        with patch.object(N,'native'),patch.object(sys.stdin,'isatty',return_value=False),patch.object(N,'launch') as launch:
            with self.assertRaisesRegex(ValueError,'interactive terminal'):N.human('reject',True)
            launch.assert_not_called()
        with patch.object(N,'native'),patch.object(sys.stdin,'isatty',return_value=True),patch('builtins.input',return_value='yes'),patch.object(N,'launch') as launch:
            with self.assertRaisesRegex(ValueError,'not authorized'):N.human('reject',True)
            launch.assert_not_called()

    def test_expected_rejection_is_not_normal_startup_or_gameplay(self):
        log='SDL_InitSubSystem(SDL_INIT_VIDEO) failed: '+N.TOKEN+' not available'
        result=N.judge('reject',1,False,log);self.assertEqual(result['renderer'],'NOT REACHED')
        for code,timeout,text in ((0,False,log),(1,True,log),(-11,False,log),(1,False,'other error'),(1,False,log+' M2 xex_loaded'),(1,False,log+' SDL video driver: wayland')):
            with self.assertRaises(ValueError):N.judge('reject',code,timeout,text)
        normal='SDL video driver: wayland\nM2 host_start\n--game_data_root does not exist: /private/absent'
        self.assertIn('SUPPORTED',N.judge('wayland',1,False,normal)['renderer'])
        with self.assertRaises(ValueError):N.judge('wayland',1,False,normal+' M2 runtime_initialized')

    def test_inventory_and_collector_do_not_ship_installations_or_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve();(p/'OWNER.txt').write_text('R3HD_STAGE2C_HUMAN_STARTUP_01')
            for rel in ('reject/installation/bin/r3hd','reject/os-home/cache/private','reject/user-data/save','wayland/cache/shader'):
                f=p/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(b'private fixture')
            (p/'reject/process.log').write_text('expected rejection')
            (p/'prepared.json').write_text('{}')
            with patch.object(N,'root',return_value=p):N.collect()
            with zipfile.ZipFile(p/'startup-private-evidence.zip') as z:
                self.assertEqual(set(z.namelist()),{'OWNER.txt','prepared.json','reject/process.log'})
            with patch.object(N,'root',return_value=p),self.assertRaises(ValueError):N.collect()

    @unittest.skipUnless(os.name=='posix','POSIX process ownership and signal fixture')
    def test_bounded_process_wait_and_timeout_only_own_group(self):
        # Non-game Python child only: tests direct-child group handling, no SDK/SDL.
        for script,seconds,timeout in (('raise SystemExit(1)',5,False),('import time;time.sleep(30)',0.05,True)):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);(p/'installation/bin').mkdir(parents=True)
                code,timed=N.launch([sys.executable,'-B','-c',script],p,{'PATH':'/usr/bin:/bin'},seconds)
                self.assertEqual(timed,timeout)
                if not timeout:self.assertEqual(code,1)
                self.assertTrue((p/'process.json').is_file())


if __name__=='__main__':unittest.main()
