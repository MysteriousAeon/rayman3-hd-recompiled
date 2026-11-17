"""EGL retry checks and incremental SDK reconfigure; no patch replay or game execution."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import stage2b as B
LOCK=json.loads((HERE/'EGL_LOCK.json').read_bytes())


def sealed_manifest(path):
    """Authenticate every byte except LF/CRLF representation against the original lock.

    Stage2A wrote the sidecar via Windows text I/O (CRLF), but the sealed tar
    member via encoded bytes (LF). Stage2B extracted that member unchanged.
    Reconstruct only the locked CRLF representation; never accept an observed
    native hash or general JSON equality as a replacement trust anchor.
    """
    B.need(path.is_file() and not path.is_symlink(),'prior manifest must be a regular file')
    raw=path.read_bytes().replace(b'\r\n',b'\n')
    B.need(b'\r' not in raw,'unsupported manifest line endings')
    locked=raw.replace(b'\n',b'\r\n')
    B.need(hashlib.sha256(locked).hexdigest()==LOCK['kit_manifest_sha256'],
           'prior sealed manifest differs (beyond LF/CRLF)')


def previous(old):
    e=old/'evidence';out=old/'work/private/work/linux_build/noble_2b01'
    B.need((e/'OWNER.txt').read_text().strip()=='R3HD_STAGE2B_01','wrong prior workspace owner')
    B.need((e/'exit-status.txt').read_text().strip()=='2','prior result is not the reported gate stop')
    B.need(B.sha(e/'TOOLKIT.json')==LOCK['previous_bundle_sha256'],'prior toolkit differs')
    sealed_manifest(old/'KIT_MANIFEST.json')
    j=json.loads((out/'results.json').read_bytes());s=j['sdk']
    B.need(j['status']=='PASS' and all(s.get(k)==0 for k in ('configure_exit','build_exit','install_exit')),'prior SDK build/install not PASS')
    B.need(j['configurations']['clang']['host_tests'] and not any(j['configurations']['clang']['host_tests'].values()),'prior CPU tests not PASS')
    B.need(not (out/'build/game-lma').exists(),'unexpected completed/partial game build; review required')
    return j


def cache_check(work):
    cache=work/'external/rexglue-sdk/out/build/linux-amd64/CMakeCache.txt'
    values=dict(re.findall(r'^([^/#][^:=\n]*):[^=\n]*=(.*)$',cache.read_text(),re.M))
    for k,v in {'CMAKE_HOME_DIRECTORY':'/task/work/external/rexglue-sdk','CMAKE_CACHEFILE_DIR':'/task/work/external/rexglue-sdk/out/build/linux-amd64',
                'CMAKE_C_COMPILER':'/runner/clang','CMAKE_CXX_COMPILER':'/runner/clang++',
                'CMAKE_C_FLAGS':'-march=x86-64-v2 -ffile-prefix-map=/task/work=.',
                'CMAKE_CXX_FLAGS':'-march=x86-64-v2 -ffile-prefix-map=/task/work=.'}.items():
        B.need(values.get(k)==v,'unreviewed cached configuration: '+k)
    B.need(values.get('CMAKE_GENERATOR')=='Ninja Multi-Config','wrong cached generator')


def tail(data):
    B.need(hashlib.sha256(data).hexdigest()==LOCK['build_inside_sha256'],'original acceptance script changed')
    anchor=b'python3 -B /runner/stage2b.py backends --task /task\n'
    B.need(data.count(anchor)==1,'ambiguous acceptance boundary')
    return anchor+data.split(anchor)[1]


def sdk_retry(task):
    work=task/'work';out=work/'private/work/linux_build/noble_2b01'
    B.immutable(work,json.loads((task/'KIT_MANIFEST.json').read_bytes()))
    cache_check(work)
    sys.path.insert(0,str(work/'tools/linux'));import r3hd_linux_build as D
    saved=out/'before-egl';saved.mkdir()
    for name in ('results.json','sdk-clang.log','compiler-search.txt','compiler-version.txt','image-packages.tsv','feature','feature.log'):
        p=out/name
        if p.exists(): shutil.copy2(p,saved/name)
    result=json.loads((out/'results.json').read_bytes())
    log=out/'sdk-egl.log';s={};flags='-march=x86-64-v2 -ffile-prefix-map=/task/work=.'
    # Invalidate only negative Wayland pkg-config cache entries, not SDK features or objects.
    args=['cmake','--preset','linux-amd64','-DCMAKE_C_FLAGS='+flags,'-DCMAKE_CXX_FLAGS='+flags,
          '-U__pkg_config_checked_PC_WAYLAND','-UPC_WAYLAND_*','-Upkgcfg_lib_PC_WAYLAND_*']
    build=work/'external/rexglue-sdk/out/build/linux-amd64'
    s['configure_exit'],_=D.sh(args,log,cwd=work/'external/rexglue-sdk',check=False)
    B.need(s['configure_exit']==0,'SDK EGL reconfigure failed')
    s['build_exit'],_=D.sh(['cmake','--build',build,'--config','Release','--target',*D.sdk_targets(),'-j','4'],log,check=False)
    B.need(s['build_exit']==0,'SDK EGL build failed')
    s['install_exit'],_=D.sh(['cmake','--install',build,'--config','Release'],log,check=False)
    B.need(s['install_exit']==0,'SDK EGL install failed')
    s['installed']='external/rexglue-sdk/out/install/linux-amd64';result['sdk']=s
    row=result['configurations']['clang'];row['host']=D.compile_host(out,'clang',None);row['host_tests']=D.host_tests(out,'clang')
    B.need(D.sdk_passed(s) and D.passed(row),'SDK/host revalidation failed')
    result['status']='PASS';result['egl_retry']='incremental; original clean SDK checkpoint preserved in before-egl'
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('R3HD_EGL_SDK_RECONFIGURE_BUILD_INSTALL PASS (incremental, not a second clean build)')


if __name__=='__main__':
    try:
        B.bundle_check()
        action=sys.argv[1]
        if action=='previous': previous(Path(sys.argv[2]));print('R3HD_EGL_PREVIOUS PASS')
        elif action=='sources':
            task=Path('/task');work=task/'work'
            checked=B.immutable(work,json.loads((task/'KIT_MANIFEST.json').read_bytes()))
            cache_check(work);B.write(task/'evidence/retry-inputs-before.json',checked)
            print('R3HD_EGL_RETRY_INPUTS PASS (before all source compilation/execution)')
        elif action=='sdk': sdk_retry(Path('/task'))
        elif action=='tail': Path(sys.argv[2]).write_bytes(tail((HERE/'build_inside.sh').read_bytes()))
        else: raise ValueError('unknown retry action')
    except (ValueError,KeyError,OSError) as error: raise SystemExit('R3HD_EGL STOP: '+str(error))
