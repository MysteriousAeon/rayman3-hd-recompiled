"""One separately authorized PulseAudio-route diagnostic; never an automatic retry."""
import argparse
import ctypes
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile
import forensic as F
V=F.V;N=F.N;C=F.C
BASE_ENV=N.environment
BASE_JUDGE=V.judge


def root():return Path.home()/'Projects/R3HD-baseline-noble-2c-pulse-01'


def prior():return Path.home()/'Projects/R3HD-baseline-noble-2c-visible-01'


def evidence():return F.review(prior()/'visible-private-evidence.zip')


def host_audio():
    """Metadata/library availability only: no server connection, audio or SDL calls."""
    runtime=Path(os.environ.get('XDG_RUNTIME_DIR',''))
    C.need(runtime.is_absolute() and runtime.resolve()==runtime,'real absolute host XDG_RUNTIME_DIR required')
    s=runtime.stat();C.need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'host runtime must be owned mode0700 directory')
    socket=runtime/'pulse/native'
    C.need(socket.resolve()==socket,'linked PulseAudio socket path')
    s=socket.stat();C.need(stat.S_ISSOCK(s.st_mode) and s.st_uid==os.getuid(),'owned existing PulseAudio-compatible socket required; no daemon startup/fallback')
    lib=ctypes.CDLL('libpulse.so.0');lib.pa_get_library_version.restype=ctypes.c_char_p
    version=lib.pa_get_library_version().decode('ascii')
    return {'socket':str(socket),'libpulse_version':version,'device_stream':'NOT TESTED','metadata_only':True}


def prepare(data_source):
    N.native();evidence();out,abi=N.inputs();p=root()
    C.need(p.parent.resolve()==p.parent and not p.exists() and not p.is_symlink(),'new workspace exists/linked; preserve it')
    source=prior()/'installation/data'
    C.need(data_source==source and source.resolve()==source,'explicit failed-test data path required; no known-good home import')
    C.file_hash(prior()/'prepared.json',F.LOCK['members']['prepared.json'])
    old=C.read_json((prior()/'prepared.json').read_bytes())
    expected=old['data_inventory']
    C.need(N.inventory(source)==expected,'old immutable content changed')
    audio=host_audio()
    C.need(shutil.disk_usage(p.parent).free>=12_000_000_000,'need 12,000,000,000 available bytes on existing filesystem')
    C.package_files(out/C.PACKAGE,abi)
    p.mkdir();(p/'OWNER.txt').write_text('R3HD_STAGE2C_VISIBLE_01\n')
    C.write(p/'audio-preflight.json',audio)
    install=p/'installation';install.mkdir();C.package_files(out/C.PACKAGE,abi,install)
    # CoW only, never hardlinks, old profiles, old cache or old HOME. No copy fallback.
    subprocess.run(['cp','-R','--reflink=always','--no-preserve=ownership','--',str(source),str(install/'data')],check=True,timeout=120)
    C.need(N.inventory(source)==expected and N.inventory(install/'data')==expected,'content clone/source verification')
    env=BASE_ENV(p,'reject')
    V.programs(install,out/C.PACKAGE);V.content_check(p,env,'clone')
    C.write(p/'prepared.json',{'package_sha256':C.LOCK['package_sha256'],'source_sha256':old['source_sha256'],
        'data_inventory':N.inventory(install/'data'),'game_executed':False,'unattended_authorized':False})
    C.write(p/'diagnostic.json',{'kind':'PULSE_ROUTE_01','prior_evidence_sha256':F.LOCK['zip_sha256'],
        'content_source':str(source),'copy':'cp --reflink=always; no fallback','game_executed':False})
    print('R3HD_PULSE_PREPARED; NO GAME EXECUTION; STOP for separate human authorization')


def routed_environment(folder,mode):
    env=BASE_ENV(folder,mode)
    if mode=='wayland':
        a=host_audio()
        # Keep HOME/all XDG dirs private; grant only this explicit owned audio socket.
        config=folder/'os-home/pulse-client.conf'
        with config.open('x') as f:f.write('autospawn = no\nauto-connect-localhost = no\nauto-connect-display = no\n')
        env.update(SDL_AUDIO_DRIVER='pulseaudio',PULSE_SERVER='unix:'+a['socket'],PULSE_CLIENTCONFIG=str(config))
        C.write(root()/'audio-route.json',dict(a,SDL_AUDIO_DRIVER='pulseaudio',PULSE_SERVER=env['PULSE_SERVER'],
           private_runtime=env['XDG_RUNTIME_DIR'],client_config_sha256=C.sha(config),autospawn=False))
    return env


def judge(code,forced,text,observation):
    # Frozen runner reads current log only. Preserve/analyze complete default20-file
    # rotation if this longer run reaches it; oldest numbered segment comes first.
    rotated=[root()/('runtime.'+str(i)+'.log') for i in range(20,0,-1)]
    if any(p.exists() for p in rotated):
        files=[root()/'process.log']+rotated+[root()/'runtime.log']
        C.need(all(not p.is_symlink() for p in files),'linked runtime log')
        text='\n'.join(p.read_text(errors='replace') for p in files if p.is_file())
    result=BASE_JUDGE(code,forced,text,observation)
    endpoint='audio endpoint ' in text
    result.update(experiment='PULSE_ROUTE_01; causal diagnostic only',audio_endpoint_opened=endpoint,
        prior_guest_fatal_recurred='(service trap) R6025' in text or 'import=__imp__KeBugCheck' in text,
        audio_correctness='UNKNOWN; stream open is not subjective audio acceptance')
    if not endpoint or result['prior_guest_fatal_recurred']:result['status']='FAIL'
    return result


def human(present):
    N.native();C.need(present and sys.stdin.isatty(),'realTTY and human-present required; NO unattended launch')
    evidence();host_audio()
    d=C.read_json((root()/'diagnostic.json').read_bytes())
    C.need(d['kind']=='PULSE_ROUTE_01' and d['prior_evidence_sha256']==F.LOCK['zip_sha256'],'prepare the new diagnostic workspace first')
    print('Audio-route diagnostic: explicitly connects to your existing desktop PulseAudio-compatible socket; may play sound and affect devices/focus. No fallback. Prior failure/workspace remains untouched.')
    # The frozen runner still requires the exact personally typed authorization.
    V.root=root;N.environment=routed_environment;V.judge=judge
    V.human(present)
    print('R3HD_PULSE_DIAGNOSTIC PASS (bounded startup only; audio causation supported, not proved)')


def collect():
    V.root=root;p=V.workspace();dest=p/'pulse-private-evidence.zip'
    C.need(not dest.exists() and not Path(str(dest)+'.sha256').exists(),'evidence exists; preserve it')
    names=['OWNER.txt','diagnostic.json','audio-preflight.json','audio-route.json','prepared.json','attempt.json',
       'process.json','exit.json','process.log','runtime.log','result.json']+[n+'.loader.txt' for n in C.COMPONENTS]
    names += ['content-'+phase+suffix for phase in ('clone','before','after') for suffix in ('.json','.stderr.txt')]
    names += ['runtime.'+str(i)+'.log' for i in range(1,21)]
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as z:
        for n in names:
            f=p/n
            if f.exists():C.need(f.is_file() and not f.is_symlink(),'linked evidence');z.write(f,n)
    with Path(str(dest)+'.sha256').open('x',encoding='ascii',newline='\n') as f:f.write(C.sha(dest)+'  '+dest.name+'\n')
    print(dest)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare');a.add_argument('--data-source',type=Path,required=True)
    a=sub.add_parser('human');a.add_argument('--human-present',action='store_true');sub.add_parser('collect')
    a=ap.parse_args()
    try:
        if a.action=='prepare':prepare(a.data_source)
        elif a.action=='human':human(a.human_present)
        else:collect()
    except (ValueError,KeyError,OSError,subprocess.SubprocessError) as e:raise SystemExit('R3HD_PULSE STOP: '+str(e))
