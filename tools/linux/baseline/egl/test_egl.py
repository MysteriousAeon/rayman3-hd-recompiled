"""Offline fixtures only; no native host checks, image build or SDK compilation."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent/'stage2b'))
import image_guard as G
import retry as R


class EGLTests(unittest.TestCase):
    def test_manifest_line_endings_only_and_content_tampering(self):
        # The lock always authenticates the Windows sidecar, not a supplied LF hash.
        value={'entries':{'work/a':{'sha256':'a'*64,'mode':420,'size':3,'type':'file'}},
               'sdk_repositories':{'work/external/sdk':'b'*40},'format':'sealed'}
        raw=(json.dumps(value,indent=2,sort_keys=True)+'\n').encode()
        lock={**R.LOCK,'kit_manifest_sha256':hashlib.sha256(raw.replace(b'\n',b'\r\n')).hexdigest()}
        with tempfile.TemporaryDirectory() as tmp,patch.object(R,'LOCK',lock):
            p=Path(tmp)/'KIT_MANIFEST.json'
            for good in (raw,raw.replace(b'\n',b'\r\n'),raw.replace(b'\n',b'\r\n',1)):
                p.write_bytes(good);R.sealed_manifest(p)
            bads=[raw.replace(b'a'*64,b'c'*64),raw.replace(b'b'*40,b'c'*40),
                  raw.replace(b'420',b'493'),raw.replace(b'"size": 3',b'"size": 4'),
                  raw.replace(b'"file"',b'"symlink"'),raw.replace(b'work/a',b'work/b'),
                  raw.replace(b'\n',b'\r'),raw[:-1],raw+b' ',
                  raw.replace(b'"format": "sealed"',b'"format": "changed", "format": "sealed"'),
                  json.dumps(value,sort_keys=True).encode()]
            for bad in bads:
                p.write_bytes(bad)
                with self.assertRaises(ValueError):R.sealed_manifest(p)

    def test_image_transaction_preserves_old_packages_and_rejects_expansion(self):
        old={('clang-19','amd64'):'locked'}
        good={**old,('libegl-dev','amd64'):'1.7.0-1build1'}
        G.check(old,good,R.LOCK)
        for data in ({('libegl-dev','amd64'):'1.7.0-1build1'},
                     {**good,('clang-19','amd64'):'changed'},
                     {**good,('libthai-dev','amd64'):'1'},
                     {**good,('libegl-dev','amd64'):'other'},old):
            with self.assertRaises(ValueError):G.check(old,data,R.LOCK)
        with self.assertRaises(ValueError):G.manifest('p\t1\tamd64\np\t1\tamd64\n')

    def test_tail_keeps_every_original_acceptance_line(self):
        p=HERE/'build_inside.sh'
        if not p.exists():p=HERE.parent/'stage2b/build_inside.sh'
        raw=p.read_bytes();tail=R.tail(raw)
        anchor=b'python3 -B /runner/stage2b.py backends --task /task\n'
        self.assertEqual(tail,raw[raw.index(anchor):])
        for required in (b'stage2b.py abi',b'stage2b.py immutable',b'm46_lgpl.py rebuild',b'r3hd_linux_package.py check'):
            self.assertIn(required,tail)
        with self.assertRaises(ValueError):R.tail(raw+b'#edited\n')

    def test_prior_checkpoint_and_local_edit_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            old=Path(tmp);e=old/'evidence';e.mkdir();out=old/'work/private/work/linux_build/noble_2b01';out.mkdir(parents=True)
            (e/'OWNER.txt').write_text('R3HD_STAGE2B_01');(e/'exit-status.txt').write_text('2')
            (e/'TOOLKIT.json').write_text('{}');(old/'KIT_MANIFEST.json').write_text('{}')
            j={'status':'PASS','sdk':dict(configure_exit=0,build_exit=0,install_exit=0),
               'configurations':{'clang':{'host_tests':{'cpu':0}}}}
            p=out/'results.json';p.write_text(json.dumps(j))
            lock={**R.LOCK,'previous_bundle_sha256':R.B.sha(e/'TOOLKIT.json'),'kit_manifest_sha256':R.B.sha(old/'KIT_MANIFEST.json')}
            with patch.object(R,'LOCK',lock):
                R.previous(old)
                for k in ('configure_exit','build_exit','install_exit'):
                    bad=copy.deepcopy(j);bad['sdk'][k]=1;p.write_text(json.dumps(bad))
                    with self.assertRaises(ValueError):R.previous(old)
                p.write_text(json.dumps(j));(e/'TOOLKIT.json').write_text('local edit')
                with self.assertRaises(ValueError):R.previous(old)

    def test_cache_paths_flags_and_generator_are_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);p=work/'external/rexglue-sdk/out/build/linux-amd64/CMakeCache.txt';p.parent.mkdir(parents=True)
            d={'CMAKE_HOME_DIRECTORY':'/task/work/external/rexglue-sdk',
               'CMAKE_CACHEFILE_DIR':'/task/work/external/rexglue-sdk/out/build/linux-amd64',
               'CMAKE_C_COMPILER':'/runner/clang','CMAKE_CXX_COMPILER':'/runner/clang++',
               'CMAKE_C_FLAGS':'-march=x86-64-v2 -ffile-prefix-map=/task/work=.',
               'CMAKE_CXX_FLAGS':'-march=x86-64-v2 -ffile-prefix-map=/task/work=.', 'CMAKE_GENERATOR':'Ninja Multi-Config'}
            def save(v):p.write_text(''.join(k+':STRING='+x+'\n' for k,x in v.items()))
            save(d);R.cache_check(work)
            for k in d:
                save({**d,k:'other'})
                with self.assertRaises(ValueError):R.cache_check(work)

    def test_no_host_install_no_feature_disable_no_cache_deletion(self):
        host=(HERE/'run_egl.sh').read_text();inside=(HERE/'retry_inside.sh').read_text();recipe=(HERE/'Containerfile').read_text()
        self.assertIn('cp -a --reflink=always',host)
        for text in (host,inside):
            for bad in ('apt-get','sudo ','rm -rf','system prune','menu-run','git reset','git checkout'):
                self.assertNotIn(bad,text)
        self.assertIn('--network=none',host);self.assertIn('--pull=never',host)
        self.assertIn('libegl-dev=1.7.0-1build1',recipe)
        self.assertIn("'wayland-client >= 1.18'",recipe)
        for bad in ('trusted=yes','AllowUnauthenticated','Verify-Peer=false','libdrm-dev','libgbm-dev','libthai-dev','SDL_WAYLAND=OFF'):
            self.assertNotIn(bad,recipe+host+inside)
        self.assertNotIn('apply_patches', (HERE/'retry.py').read_text())
        self.assertLess(inside.index('retry.py sources'),inside.index('clang++ -std=c++23'))

    def test_incremental_sdk_commands_and_failure_stop(self):
        for fail in (False,True):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as tmp:
                task=Path(tmp);out=task/'work/private/work/linux_build/noble_2b01';out.mkdir(parents=True)
                (task/'KIT_MANIFEST.json').write_text('{}')
                record={'status':'PASS','configurations':{'clang':{}},'sdk':{'old':True}}
                raw=json.dumps(record);(out/'results.json').write_text(raw);calls=[]
                def sh(args,*a,**kw):
                    calls.append(list(map(str,args)));return (1 if fail else 0),'synthetic'
                fake=types.SimpleNamespace(sh=sh,sdk_targets=lambda:['rexruntime','rexgpu-xenos','SDL3_test'],
                    compile_host=lambda *a:{'status':'pass'},host_tests=lambda *a:{'cpu':0},
                    sdk_passed=lambda s:all(s.get(k)==0 for k in ('configure_exit','build_exit','install_exit')),
                    passed=lambda row:row['host']['status']=='pass' and not any(row['host_tests'].values()))
                with patch.object(R.B,'immutable'),patch.object(R,'cache_check'),patch.dict(sys.modules,{'r3hd_linux_build':fake}):
                    if fail:
                        with self.assertRaisesRegex(ValueError,'reconfigure'):R.sdk_retry(task)
                        self.assertEqual(len(calls),1)
                        self.assertEqual((out/'results.json').read_text(),raw)
                    else:
                        R.sdk_retry(task);self.assertEqual(len(calls),3)
                        self.assertIn('-UPC_WAYLAND_*',calls[0]);self.assertIn('-Upkgcfg_lib_PC_WAYLAND_*',calls[0])
                        self.assertIn('SDL3_test',calls[1]);self.assertIn('--install',calls[2])
                        self.assertEqual(json.loads((out/'results.json').read_text())['status'],'PASS')
                    self.assertEqual((out/'before-egl/results.json').read_text(),raw)


if __name__=='__main__':unittest.main()
