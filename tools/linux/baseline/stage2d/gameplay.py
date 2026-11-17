"""Stage2D preparation and separately authorized human gameplay. No unattended route."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import zipfile
HERE=Path(__file__).resolve().parent
if not (HERE/'audio_diag.py').exists():sys.path.insert(0,str(HERE.parent/'audio_diag'))
import audio_diag as A
C=A.C;N=A.N;V=A.V
OWNER='R3HD_STAGE2D_01'
LIMIT=1800  # safety ceiling, not a deadline for any level/save milestone
LOG_BUDGET=48*1024*1024


def root():return Path.home()/'Projects/R3HD-baseline-noble-2d-01'


def workspace():
    p=root();C.need(p.resolve()==p and (p/'OWNER.txt').read_text().strip()==OWNER,'wrong/linked Stage2D workspace');return p


def no_other_game(proc=Path('/proc')):
    """Same-user executable metadata only, never memory or process termination."""
    for d in proc.iterdir():
        if not d.name.isdigit():continue
        try:
            if d.stat().st_uid!=os.getuid():continue
            target=os.readlink(d/'exe')
        except FileNotFoundError:continue  # process exited during enumeration
        except PermissionError:raise ValueError('cannot verify same-user executable; STOP')
        C.need(Path(target.removesuffix(' (deleted)')).name not in ('r3hd','r3hd.exe'),'another game process is running; close it yourself first')


def native_checkpoint():
    """Hash-only native receipt authentication. No source checkout/tool installation needed."""
    import pulse_review as P
    p=Path.home()/'Projects'
    data=P.authenticated(p/'R3HD-baseline-noble-2c-pulse-01/pulse-private-evidence.zip')
    A.F.review(p/'R3HD-baseline-noble-2c-visible-01/visible-private-evidence.zip')
    V.R.review(p/'R3HD-baseline-noble-2c-startup-01/startup-private-evidence.zip')
    C.need(C.read_json(data['exit.json'])=={'exit':0,'timed_out_or_interrupted_or_remaining_group':False},'native checkpoint exit')
    return C.read_json(data['prepared.json'])


def prepare(source):
    N.native();old=native_checkpoint();out,abi=N.inputs();p=root()
    expected_source=Path.home()/'Projects/R3HD-baseline-noble-2c-pulse-01/installation/data'
    C.need(source==expected_source and source.resolve()==source,'explicit verified Pulse test data tree only')
    C.need(not p.exists() and not p.is_symlink() and p.parent.resolve()==p.parent,'fresh real workspace required; preserve existing')
    C.need(shutil.disk_usage(p.parent).free>=12_000_000_000,'need 12,000,000,000 free bytes on existing filesystem')
    C.need(N.inventory(source)==old['data_inventory'],'source content changed')
    audio=A.host_audio();C.package_files(out/C.PACKAGE,abi)
    p.mkdir(mode=0o700);(p/'OWNER.txt').write_text(OWNER+'\n');install=p/'installation';install.mkdir()
    C.package_files(out/C.PACKAGE,abi,install)
    subprocess.run(['cp','-R','--reflink=always','--no-preserve=ownership','--',str(source),str(install/'data')],check=True,timeout=120)
    C.need(N.inventory(source)==old['data_inventory'] and N.inventory(install/'data')==old['data_inventory'],'CoW data/source verification')
    env=N.environment(p,'reject');V.content_check(p,env,'clone');V.programs(install,out/C.PACKAGE)
    C.write(p/'prepared.json',dict(old,stage='2D',game_executed=False))
    C.write(p/'prepared-receipt.json',{'stage':'2D','package_sha256':C.LOCK['package_sha256'],
        'content_files':915,'imported_profiles_saves_mods':False,'execution':'NOT RUN',
        'audio_prerequisites':'owned existing socket/libpulse metadata only','free_bytes_required':12_000_000_000})
    print('R3HD_STAGE2D_PREPARED; NO GAME EXECUTION; STOP for personal launch authorization')


def log_bytes(folder):return sum(f.stat().st_size for f in folder.glob('*.log') if f.is_file())


def log_growth(folder,seen):
    """Account bytes across renames/rotation, not merely the retained log footprint."""
    added=0
    for f in folder.glob('*.log'):
        C.need(not f.is_symlink(),'linked log')
        s=f.stat();key=(s.st_dev,s.st_ino)
        added+=max(0,s.st_size-seen.get(key,0));seen[key]=max(s.st_size,seen.get(key,0))
    return added


def launch(args,folder,env):
    """Owned group only, core0, 30min ceiling, 48MiB logs, no input or desktop actions."""
    def limits():N.resource.setrlimit(N.resource.RLIMIT_CORE,(0,0))
    with (folder/'process.log').open('x') as f:
        p=subprocess.Popen(list(map(str,args)),cwd=root()/'installation/bin',env=env,stdin=subprocess.DEVNULL,
            stdout=f,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=limits)
        reason=None;started=time.monotonic();seen={};written=0
        try:
            C.write(folder/'process.json',{'pid':p.pid,'owned_process_group':p.pid})
            while p.poll() is None:
                if time.monotonic()-started>=LIMIT:reason='SAFETY_TIME_LIMIT';break
                written+=log_growth(folder,seen)
                if written>=LOG_BUDGET:reason='LOG_BUDGET';break
                if shutil.disk_usage(folder).free<2_000_000_000:reason='LOW_DISK';break
                time.sleep(.25)
        except KeyboardInterrupt:reason='HUMAN_INTERRUPT'
        finally:
            if p.poll() is None:
                reason=reason or 'SUPERVISOR_EXCEPTION'
                try:os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    p.wait()
            try:os.killpg(p.pid,0)
            except ProcessLookupError:pass
            else:
                reason=reason or 'REMAINING_OWNED_GROUP'
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        return p.returncode,reason


def environment(p,folder):
    # Validate the current desktop socket with the frozen helper. The persistent
    # private HOME/XDG and test-user/cache are shared only across this test's phases.
    env=N.environment(folder,'wayland')
    home=p/'session-home'
    if not home.exists():home.mkdir(mode=0o700)
    C.need(home.resolve()==home,'linked private HOME')
    env.update(HOME=str(home),TMPDIR=str(home))
    for key,name in (('XDG_DATA_HOME','data'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('XDG_RUNTIME_DIR','run')):
        d=home/name
        if not d.exists():d.mkdir(mode=0o700)
        C.need(d.resolve()==d and d.is_dir(),'linked private XDG directory');env[key]=str(d)
    env['DBUS_SESSION_BUS_ADDRESS']='unix:path='+env['XDG_RUNTIME_DIR']+'/no-session-bus'
    env['DBUS_SYSTEM_BUS_ADDRESS']='unix:path='+env['XDG_RUNTIME_DIR']+'/no-system-bus'
    config=home/'pulse-client.conf';raw=b'autospawn = no\nauto-connect-localhost = no\nauto-connect-display = no\n'
    if not config.exists():
        with config.open('xb') as f:f.write(raw)
    C.need(config.resolve()==config and config.read_bytes()==raw,'changed private audio config')
    audio=A.host_audio()
    env.update(SDL_AUDIO_DRIVER='pulseaudio',PULSE_SERVER='unix:'+audio['socket'],PULSE_CLIENTCONFIG=str(config),
        LD_LIBRARY_PATH=str(p/'installation/bin'),DISABLE_LSFG='1',R3HD_DS_LIGHT='off',R3HD_DS_TRIGGER='off',R3HD_DS_SPEAKER='off',R3HD_DISCORD='off')
    return env


def saves(p):
    """Local metadata only: actual SDK saved-game content type, never settings alone."""
    user=p/'test-user';result={}
    if not user.exists():return result
    C.need(user.resolve()==user,'linked test profile')
    for f in user.rglob('*'):
        C.need(not f.is_symlink(),'linked test state')
        parts=f.relative_to(user).parts
        if f.is_file() and len(parts)>=5 and re.fullmatch('[0-9A-Fa-f]{16}',parts[0]) and parts[1].upper()=='5841123F' and parts[2]=='00000001':
            C.need(f.stat().st_size<=64*1024*1024,'unexpected large save; STOP')
            if f.stat().st_size:result[f.relative_to(user).as_posix()]=C.sha(f)
    return result


def machine(folder):
    logs=[folder/'process.log']+[folder/('runtime.'+str(i)+'.log') for i in range(20,0,-1)]+[folder/'runtime.log']
    C.need(all(not f.is_symlink() for f in logs),'linked technical log')
    text='\n'.join(f.read_text(errors='replace') for f in logs if f.is_file())
    benign=re.compile(r'^\[[^\]\r\n]+\] \[error\] \[fs\] \[t[0-9]+\] ResolvePath\(\\D:\\Gamedata\) failed - device not found$')
    errors=[s for s in text.splitlines() if ('[error]' in s.lower() or '[critical]' in s.lower()) and not benign.fullmatch(s)]
    markers={s:s in text for s in ('SDL video driver: wayland',"GPU plugin 'xenos' loaded",'VulkanPresenter: Created',
        'M2 xex_loaded entry=820E13F8','M2 runtime_initialized','M2 launch_prepared')}
    return {'startup_markers':markers,'audio_endpoint_opens':text.count('audio endpoint '),
        'stream_open_failures':text.count('SDL_OpenAudioDeviceStream() failed:'),
        'guest_fatal':('R6025' in text or 'import=__imp__KeBugCheck' in text),
        'device_lost':'VK_ERROR_DEVICE_LOST' in text,'unexpected_error_lines':len(errors),
        'lsfg_active':'VK_LAYER_LS_frame_generation' in text,
        'gpu_present_path_debug_records':text.count('XELOG_GPU PRESENT:'),
        'vblank_timing_records':text.count('M16 vblank mode='),'warning_lines':text.count('[warning]'),
        'window_close':'Window closing, shutting down...' in text,
        'sdk_hard_exit':'Title terminated; hard-exiting process.' in text,
        'host_pacing':'NOT MEASURED; no Vulkan M11 hook; debug GPU logs may be absent at info level'}


QUESTIONS={'menu':'Recognizable title/main menu?', 'natural_gameplay':'Entered gameplay by New Game/Continue normally (no level shortcut)?',
    'movement':'Human movement worked?', 'camera':'Human camera control worked?', 'jump':'Human jumping worked?',
    'audible_clear':'Game audio audible with no obvious distortion?',
    'anomaly':'Any visible anomaly, stall, crash or unexpected behavior?',
    'save_seen':'Personally observed a genuine in-game save action/indicator completing?',
    'loaded_progress':'Loaded the previously remembered saved progression (not just a menu)?'}


def observations():
    out={}
    for key,question in QUESTIONS.items():
        answer=input(question+' [yes/no/unknown]: ').strip()
        C.need(answer in ('yes','no','unknown'),'invalid response; preserve logs, do not relaunch')
        out[key]=answer
    level=input('Furthest naturally reached location [menu/intro_10/intro_15/other/unknown]: ').strip()
    C.need(level in ('menu','intro_10','intro_15','other','unknown'),'invalid location response')
    out['furthest_location']=level
    anomaly=input('Main anomaly [none/graphics/stall/crash/input/audio/other/unknown]: ').strip()
    C.need(anomaly in ('none','graphics','stall','crash','input','audio','other','unknown'),'invalid anomaly response')
    out['anomaly_kind']=anomaly
    method=input('How did you exit? [guest-menu/window-x/other/unknown]: ').strip()
    C.need(method in ('guest-menu','window-x','other','unknown'),'invalid exit response');out['exit_method']=method
    return out


def verdict(m,o,code,reason,integrity,before,after,mode):
    clean=not reason and code==0 and integrity and not any((m['guest_fatal'],m['device_lost'],m['stream_open_failures'],m['unexpected_error_lines'],m['lsfg_active']))
    gate=lambda yes:'PASS' if yes else 'NOT ESTABLISHED'
    changed=bool(after) and after!=before
    return {'A_startup_menu':gate(all(m['startup_markers'].values()) and o['menu']=='yes'),
        'B_natural_gameplay':gate(o['natural_gameplay']=='yes'),
        'C_human_actions':gate(all(o[k]=='yes' for k in ('movement','camera','jump'))),
        'D_audio':gate(m['audio_endpoint_opens']>0 and not m['stream_open_failures'] and o['audible_clear']=='yes'),
        'E_exit':gate(code==0 and reason is None and o['exit_method'] in ('guest-menu','window-x')),'exit_detail':'SDK window-close hard exit, not full teardown' if m['sdk_hard_exit'] else 'see local log',
        'F_save_write':gate(changed and o['save_seen']=='yes'),
        'F_saved_progress_load':gate(mode=='load' and bool(before) and o['loaded_progress']=='yes' and o['natural_gameplay']=='yes' and all(m['startup_markers'].values()) and clean),
        'integrity':integrity,'runtime_clean':clean,'anomaly_observed':o['anomaly'],
        'phase_A_eligible':clean and m['audio_endpoint_opens']>0 and o['exit_method'] in ('guest-menu','window-x') and all(m['startup_markers'].values()) and all(o[k]=='yes' for k in ('menu','natural_gameplay','movement','camera','jump','audible_clear')) and o['anomaly']=='no' and o['anomaly_kind']=='none',
        'evidence_labels':{'A':'machine initialization + human menu','B_C':'human observations',
            'D':'machine endpoint + human sound','E':'machine exit + human context','F':'content-type file metadata + human save/load'},
        'gameplay_completion_other_distributions_Deck':'UNKNOWN'}


def run(mode,present):
    N.native();C.need(present and sys.stdin.isatty(),'realTTY and human-present required; no unattended game')
    p=workspace();folder=p/mode;C.need(not folder.exists() and not folder.is_symlink(),'attempt exists; preserve it, no retry')
    if mode!='a':
        a=C.read_json((p/'a/result.json').read_bytes());C.need(a['phase_A_eligible'] is True,'Phase A has not passed all independent prerequisites; STOP')
    if mode=='load':
        candidates=[p/n/'result.json' for n in ('save','a')]
        C.need(any(f.exists() and C.read_json(f.read_bytes())['F_save_write']=='PASS' for f in candidates),'no verified genuine save write; STOP, menu is not a save')
        if (p/'save').exists():C.need(C.read_json((p/'save/result.json').read_bytes())['runtime_clean'],'save attempt failed; STOP')
    print('Human-only visible gameplay: may affect focus/cursor, play audible sound, open physical input/controllers and cause haptics/device outputs. Disconnect unwanted controllers. Remain present. No automation. Close only test window or Ctrl+C on failure. 30min safety ceiling is not a progression deadline.')
    C.need(input('Type AUTHORIZE STAGE2D '+mode.upper()+': ')=='AUTHORIZE STAGE2D '+mode.upper(),'not authorized')
    no_other_game();native_checkpoint();out,abi=N.inputs();plan=C.read_json((p/'prepared.json').read_bytes());install=p/'installation'
    V.programs(install,out/C.PACKAGE);C.need(N.inventory(install/'data')==plan['data_inventory'],'immutable data changed')
    C.need(shutil.disk_usage(p).free>=4_000_000_000,'need 4,000,000,000 free bytes before launch')
    if mode=='a':C.need(not (p/'test-user').exists() and not (p/'test-cache').exists(),'Phase A needs fresh state')
    for name in ('test-user','test-cache'):
        state=p/name;C.need(state.resolve()==state and not state.is_symlink(),'linked test state')
    before=saves(p)
    if mode=='load':
        previous='save' if (p/'save').exists() else 'a'
        C.need(before==C.read_json((p/previous/'saves-after-local.json').read_bytes()),'saved-game bytes changed since previous run; STOP')
    folder.mkdir();(folder/'installation').mkdir()
    env=environment(p,folder)
    V.content_check(p,env,mode+'-before')
    for n in C.COMPONENTS:
        C.file_hash(install/'bin'/n,abi[n]['sha256'])
        with (folder/(n+'.loader.txt')).open('x') as f:
            r=subprocess.run(['/lib64/ld-linux-x86-64.so.2','--list',str(install/'bin'/n)],env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=15)
        C.need(r.returncode==0 and 'not found' not in (folder/(n+'.loader.txt')).read_text(),'loader failed; no execution')
    args=[install/'bin/r3hd','--video_driver=wayland','--fullscreen=false','--gpu_plugin=xenos',
        '--game_data_root='+str(install/'data/content'),'--user_data_root='+str(p/'test-user'),'--cache_root='+str(p/'test-cache'),
        '--log_file='+str(folder/'runtime.log'),'--log_level=info','--log_flush_interval=1',
        '--log_max_file_size_mb=4','--log_max_files=8']
    C.write(folder/'attempt.json',{'argv':list(map(str,args)),'human_authorized':True,'phase':mode,'timeout_seconds':LIMIT,'log_budget_bytes':LOG_BUDGET})
    C.write(folder/'saves-before-local.json',before)
    code,reason=launch(args,folder,env);C.write(folder/'exit.json',{'exit':code,'forced_reason':reason})
    m=machine(folder);C.write(folder/'machine.json',m);integrity=True
    try:
        V.programs(install,out/C.PACKAGE);C.need(N.inventory(install/'data')==plan['data_inventory'],'data changed')
        V.content_check(p,env,mode+'-after')
    except (ValueError,OSError,subprocess.SubprocessError):integrity=False
    after=saves(p);C.write(folder/'saves-after-local.json',after)
    C.write(folder/'save-summary.json',{'before_nonempty_files':len(before),'after_nonempty_files':len(after),
        'changed':before!=after,'scope':'SDK saved-game content type 00000001 only; not proof of genuine progression by itself'})
    o=observations();C.write(folder/'observation.json',o)
    result=verdict(m,o,code,reason,integrity,before,after,mode);C.write(folder/'result.json',result)
    print(json.dumps(result,indent=2));print('R3HD_STAGE2D_RECORDED; independent gates, no overall gameplay PASS')


def collect():
    p=workspace();dest=p/'stage2d-private-evidence.zip'
    C.need(not dest.exists() and not Path(str(dest)+'.sha256').exists(),'evidence exists; preserve it')
    # Technical derived summaries and fixed-choice observations only. Raw runtime logs,
    # profile filenames, XUIDs, save bytes/hashes, data, HOME and caches remain native.
    names=['OWNER.txt','prepared-receipt.json']
    names += [mode+'/'+n+'.json' for mode in ('a','save','load') for n in ('exit','machine','observation','result','save-summary')]
    files={}
    for n in names:
        f=p/n
        if f.exists():C.need(f.is_file() and f.resolve()==f and not f.is_symlink(),'linked evidence');files[n]=f.read_bytes()
    files['SHA256SUMS']=''.join(C.digest(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as z:
        for n,b in files.items():z.writestr(n,b)
    with Path(str(dest)+'.sha256').open('x',encoding='ascii',newline='\n') as f:f.write(C.sha(dest)+'  '+dest.name+'\n')
    print(dest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare');a.add_argument('--data-source',type=Path,required=True)
    a=sub.add_parser('human');a.add_argument('phase',choices=('a','save','load'));a.add_argument('--human-present',action='store_true')
    sub.add_parser('collect');a=p.parse_args()
    try:
        if a.action=='prepare':prepare(a.data_source)
        elif a.action=='human':run(a.phase,a.human_present)
        else:collect()
    except (ValueError,KeyError,OSError,subprocess.SubprocessError) as e:raise SystemExit('R3HD_STAGE2D STOP: '+str(e)+'; preserve workspace, no fallback/retry')
