"""Preparation only by default. Explicit, interactive human authorization per real launch.

No unattended launch route or automatic visible fallback. No game data is imported.
"""
import argparse
import os
from pathlib import Path
import platform
try:import resource
except ImportError:resource=None  # Windows tests inspect/fixture only; launch is Linux-only.
import signal
import stat
import subprocess
import sys
import tarfile
import zipfile
import supplements as S
C=S.C
TOKEN='r3hd_stage2c_reject'


def root():return Path.home()/'Projects/R3HD-baseline-noble-2c-startup-01'


def inventory(folder):
    C.need(not any(p.is_symlink() for p in folder.rglob('*')),'linked installation')
    return {p.relative_to(folder).as_posix():C.sha(p) for p in folder.rglob('*') if p.is_file()}


def archive_inventory(package):
    # Called only after inputs() authenticates the exact previously audited archive.
    with tarfile.open(package,'r:gz') as t:
        return {m.name.removeprefix(C.TOP+'/'):C.digest(t.extractfile(m).read()) for m in t}


def native():
    C.need(platform.system()=='Linux' and platform.machine()=='x86_64' and os.getuid()!=0,'non-root native Linux amd64 required')
    C.need('microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower() and
           not os.environ.get('WSL_DISTRO_NAME'),'WSL target execution prohibited; native CachyOS only')


def inputs():
    home=Path.home()/'Projects'
    S.review(home/'R3HD-baseline-noble-2b-final-01/supplemental-private-evidence.zip',
             home/'R3HD-baseline-noble-2c-01/supplemental-private-evidence.zip')
    out=home/'R3HD-baseline-noble-2b-egl-01'/C.REL
    C.file_hash(out/C.PACKAGE,C.LOCK['package_sha256']);C.file_hash(out/'lgpl'/C.SOURCE,C.LOCK['lgpl_sha256'])
    C.file_hash(out/'abi.json',C.LOCK['native_records'][C.REL+'abi.json'])
    return out,C.read_json((out/'abi.json').read_bytes())['components']


def prepare():
    native();out,abi=inputs();dest=root()
    C.need(dest.parent.resolve()==dest.parent,'linked workspace parent')
    C.need(not dest.exists() and not dest.is_symlink(),'preparation exists; preserve it')
    import shutil
    C.need(shutil.disk_usage(dest.parent).free>=1_000_000_000,'need 1,000,000,000 available bytes')
    C.package_files(out/C.PACKAGE,abi)
    dest.mkdir();(dest/'OWNER.txt').write_text('R3HD_STAGE2C_HUMAN_STARTUP_01\n')
    plan={'package_sha256':C.LOCK['package_sha256'],'unattended_authorized':False,'modes':{}}
    for mode in ('reject','wayland'):
        folder=dest/mode;folder.mkdir();install=folder/'installation';install.mkdir()
        C.package_files(out/C.PACKAGE,abi,install)
        C.need(not (install/'bin/r3hd.toml').exists(),'unexpected application config')
        plan['modes'][mode]={'files':inventory(install),'state':'PREPARED; NOT EXECUTED'}
    C.write(dest/'prepared.json',plan)
    print('R3HD_STAGE2C_STARTUP_PREPARED; NO EXECUTABLE ENTRY; separate human authorization required')


def environment(folder,mode):
    home=folder/'os-home';home.mkdir();env={'PATH':'/usr/bin:/bin','HOME':str(home),'LANG':'C.UTF-8',
        'LC_ALL':'C.UTF-8','TZ':'UTC','TMPDIR':str(home),'LD_LIBRARY_PATH':str(folder/'installation/bin')}
    for k,n in (('XDG_DATA_HOME','data'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('XDG_RUNTIME_DIR','run')):
        p=home/n;p.mkdir(mode=0o700);env[k]=str(p)
    env['DBUS_SESSION_BUS_ADDRESS']='unix:path='+env['XDG_RUNTIME_DIR']+'/no-session-bus'
    env['DBUS_SYSTEM_BUS_ADDRESS']='unix:path='+env['XDG_RUNTIME_DIR']+'/no-system-bus'
    if mode=='wayland':
        C.need(os.environ.get('XDG_SESSION_TYPE')=='wayland','Wayland session required; no X11 fallback')
        display=os.environ.get('WAYLAND_DISPLAY','');runtime=os.environ.get('XDG_RUNTIME_DIR','')
        C.need(display and runtime,'host Wayland session variables missing')
        p=Path(display) if Path(display).is_absolute() else Path(runtime)/display
        C.need(p.is_absolute() and p.resolve()==p and stat.S_ISSOCK(p.stat().st_mode) and p.stat().st_uid==os.getuid(),'owned real Wayland socket required')
        env['WAYLAND_DISPLAY']=str(p)  # private XDG dirs; only this explicitly authorized session socket.
    return env


def launch(args,folder,env,seconds):
    def limits():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    with (folder/'process.log').open('x') as log:
        p=subprocess.Popen(list(map(str,args)),cwd=folder/'installation/bin',env=env,
                           stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                           start_new_session=True,preexec_fn=limits)
        C.write(folder/'process.json',{'pid':p.pid,'owned_process_group':p.pid,'timeout_seconds':seconds})
        timed_out=False
        try:code=p.wait(timeout=seconds)
        except (subprocess.TimeoutExpired,KeyboardInterrupt):
            timed_out=True
            try:os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:code=p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                code=p.wait()
        # Even a naturally exiting parent must not leave its owned group running.
        try:os.killpg(p.pid,0)
        except ProcessLookupError:pass
        else:
            timed_out=True
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
    return code,timed_out


def judge(mode,code,timed_out,log):
    forbidden=('M2 xex_loaded','M2 runtime_initialized','M2 launch_prepared','M2 guest_thread_exit')
    C.need(code==1 and not timed_out,'expected natural rejection exit1 not observed')
    C.need(not any(s in log for s in forbidden),'unexpected progress into runtime/guest')
    if mode=='reject':
        C.need('SDL_InitSubSystem(SDL_INIT_VIDEO) failed: '+TOKEN+' not available' in log,'exact deliberate SDL rejection absent')
        C.need('SDL video driver:' not in log and 'M2 host_start' not in log,'unexpected SDL/application progress')
        return {'application_entry':'VERIFIED by targeted SDL error','sdl_attempt':'VERIFIED',
                'window_system_initialization':'EXPECTED REJECTION; NOT PASS','renderer':'NOT REACHED',
                'game_data':'NOT USED','exit':'EXPECTED NATURAL EXIT 1'}
    C.need('SDL video driver: wayland' in log and 'M2 host_start' in log and
           '--game_data_root does not exist:' in log,'Wayland/application/missing-data milestones absent')
    return {'application_entry':'VERIFIED','window_system_initialization':'VERIFIED Wayland backend selected',
            'renderer':'SUPPORTED presentation setup returned with explicit xenos plugin; runtime rendering NOT TESTED',
            'game_data':'INTENTIONALLY ABSENT; stopped before Runtime construction','exit':'EXPECTED NATURAL EXIT 1'}


def human(mode,present):
    native()
    C.need(present and sys.stdin.isatty(),'human-present flag and interactive terminal required; NO unattended launch')
    phrase='AUTHORIZE ATTENDED '+mode.upper()
    print('This is NOT an unattended-safe test. It may show a window/dialog and affect focus. No game data will be loaded.')
    C.need(input('Remain at the terminal; type '+phrase+': ')==phrase,'launch not authorized')
    dest=root();C.need(dest.resolve()==dest,'linked startup root')
    C.need((dest/'OWNER.txt').read_text().strip()=='R3HD_STAGE2C_HUMAN_STARTUP_01','wrong workspace')
    plan=C.read_json((dest/'prepared.json').read_bytes());folder=dest/mode
    C.need(folder.resolve()==folder and (folder/'installation').resolve()==folder/'installation','linked mode or installation path')
    C.need(not (folder/'attempt.json').exists(),'attempt already exists; preserve it, no rerun')
    if mode=='wayland':
        prior=C.read_json((dest/'reject/result.json').read_bytes());C.need(prior['status']=='PASS','entry rejection probe must pass first')
    C.need(inventory(folder/'installation')==plan['modes'][mode]['files'],'installation changed')
    out,abi=inputs();env=environment(folder,mode)
    C.need(inventory(folder/'installation')==archive_inventory(out/C.PACKAGE),'installation differs from authenticated source package')
    for n in C.COMPONENTS:C.file_hash(folder/'installation/bin'/n,abi[n]['sha256'])
    C.need(not (folder/'installation/bin/r3hd.toml').exists(),'unreviewed application config appeared')
    missing=folder/'absent-game-data';C.need(not missing.exists() and not missing.is_symlink(),'game-data guard path must NOT exist')
    args=[folder/'installation/bin/r3hd','--video_driver='+(TOKEN if mode=='reject' else 'wayland'),
          '--fullscreen=false','--gpu_plugin=xenos','--game_data_root='+str(missing),
          '--user_data_root='+str(folder/'user-data'),'--cache_root='+str(folder/'cache'),
          '--log_file='+str(folder/'runtime.log'),'--log_level=debug','--log_flush_interval=1']
    C.write(folder/'attempt.json',{'human_authorization':phrase,'mode':mode,'argv':list(map(str,args)),
             'package_sha256':C.LOCK['package_sha256'],'unattended':False})
    # Fresh native closure immediately before real entry. This never calls the game.
    for n in C.COMPONENTS:
        with (folder/(n+'.loader.txt')).open('x') as f:
            r=subprocess.run(['/lib64/ld-linux-x86-64.so.2','--list',str(folder/'installation/bin'/n)],
                 env=env,cwd=folder,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=15)
        C.need(r.returncode==0 and 'not found' not in (folder/(n+'.loader.txt')).read_text(),'loader failed before entry')
    code,timeout=launch(args,folder,env,15 if mode=='reject' else 45)
    C.write(folder/'exit.json',{'exit':code,'timed_out_or_interrupted':timeout})
    log='\n'.join(p.read_text(errors='replace') for p in (folder/'process.log',folder/'runtime.log') if p.exists())
    try:
        if mode=='wayland':C.need('--game_data_root does not exist: '+str(missing) in log,'wrong missing-data guard path')
        milestones=judge(mode,code,timeout,log)
        C.need(inventory(folder/'installation')==plan['modes'][mode]['files'],'program files changed')
        for n in C.COMPONENTS:C.file_hash(folder/'installation/bin'/n,abi[n]['sha256'])
        C.need(not missing.exists(),'game data unexpectedly appeared')
        C.write(folder/'result.json',{'status':'PASS','mode':mode,'milestones':milestones,
            'expected_failure_probe':True,'normal_startup_pass':False,'gameplay':'UNKNOWN','guest_executed':False})
    except ValueError as e:
        C.write(folder/'result.json',{'status':'FAIL','reason':str(e),'guest_executed':'UNKNOWN; inspect logs'})
        raise
    print('R3HD_STAGE2C_ATTENDED_'+mode.upper()+' PASS (expected rejection only); STOP')


def collect():
    dest=root();C.need(dest.resolve()==dest and (dest/'OWNER.txt').read_text().strip()=='R3HD_STAGE2C_HUMAN_STARTUP_01','wrong workspace')
    p=dest/'startup-private-evidence.zip';C.need(not p.exists(),'evidence exists; preserve it')
    with zipfile.ZipFile(p,'x',zipfile.ZIP_DEFLATED) as z:
        for f in dest.rglob('*'):
            rel=f.relative_to(dest)
            if any(n in ('installation','os-home','user-data','cache') for n in rel.parts):continue
            if f.is_file() and not f.is_symlink() and f.suffix in ('.json','.txt','.log'):z.write(f,rel.as_posix())
    with Path(str(p)+'.sha256').open('x',encoding='ascii',newline='\n') as f:f.write(C.sha(p)+'  '+p.name+'\n')
    print(p)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    s.add_parser('prepare');a=s.add_parser('human');a.add_argument('--mode',choices=('reject','wayland'),required=True);a.add_argument('--human-present',action='store_true');s.add_parser('collect')
    a=p.parse_args()
    try:
        if a.action=='prepare':prepare()
        elif a.action=='human':human(a.mode,a.human_present)
        else:collect()
    except (ValueError,KeyError,OSError,subprocess.SubprocessError) as e:raise SystemExit('R3HD_STARTUP STOP: '+str(e))
