"""Prepare an isolated owned-data installation; human-only bounded visible startup.

Never use this as an unattended runner. No automatic data/home discovery or import.
"""
import argparse
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import review as R
N=R.N
C=N.C


def root():return Path.home()/'Projects/R3HD-baseline-noble-2c-visible-01'


def receipt():
    return R.review(Path.home()/'Projects/R3HD-baseline-noble-2c-startup-01/startup-private-evidence.zip')


def workspace():
    p=root();C.need(p.resolve()==p and (p/'OWNER.txt').read_text().strip()=='R3HD_STAGE2C_VISIBLE_01','wrong/linked workspace')
    return p


def programs(folder,package):
    C.need(folder.resolve()==folder,'linked program root')
    expected=N.archive_inventory(package)
    for rel,h in expected.items():C.file_hash(folder/rel,h)
    for directory in ('bin','app'):
        C.need((folder/directory).resolve()==folder/directory,'linked program directory')
        actual=N.inventory(folder/directory)
        C.need(actual=={n[len(directory)+1:]:h for n,h in expected.items() if n.startswith(directory+'/')},'unexpected program/config files')


def prepare(source):
    N.native();receipt();out,abi=N.inputs();p=root()
    C.need(p.parent.resolve()==p.parent and not p.exists() and not p.is_symlink(),'workspace exists or linked; preserve it')
    C.need(source.is_absolute() and source.resolve()==source,'supply absolute real original package file; no linked paths')
    C.file_hash(source,R.LOCK['raw_package_sha256'])
    C.need(source.stat().st_size==R.LOCK['raw_package_size'],'wrong original package size')
    C.need(shutil.disk_usage(p.parent).free>=12_000_000_000,'need 12,000,000,000 available bytes on existing filesystem')
    C.package_files(out/C.PACKAGE,abi)
    p.mkdir();(p/'OWNER.txt').write_text('R3HD_STAGE2C_VISIBLE_01\n')
    install=p/'installation';install.mkdir();C.package_files(out/C.PACKAGE,abi,install)
    # Independent preparation HOME, no desktop/session socket, and prepare action only.
    env=N.environment(p,'reject')
    env['DISABLE_LSFG']='1'
    cmd=[sys.executable,'-B',str(install/'app/tools/r3hd_portable.py'),'prepare','--no-input','--source',str(source)]
    with (p/'data-prepare.log').open('x') as f:
        result=subprocess.run(cmd,cwd=install,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=900)
    C.need(result.returncode==0 and 'R3HD_PORTABLE READY' in (p/'data-prepare.log').read_text(),'owned data preparation failed; preserve workspace/log and STOP')
    C.file_hash(source,R.LOCK['raw_package_sha256']);programs(install,out/C.PACKAGE)
    C.file_hash(install/'data/content/Default.xex','77a4df54340aebcc79eb0f0053938c03b8efd2efdd3ffee26c00fdfef3c6e8ca')
    C.write(p/'prepared.json',{'package_sha256':C.LOCK['package_sha256'],'source_sha256':R.LOCK['raw_package_sha256'],
        'data_inventory':N.inventory(install/'data'),'game_executed':False,'unattended_authorized':False})
    print('R3HD_STAGE2C_VISIBLE_PREPARED; NO GAME EXECUTION; STOP for separate human authorization')


def content_check(p,env,phase):
    # Revalidate against the authenticated shipped manifest, not just mutable prepared.json.
    install=p/'installation'
    cmd=[sys.executable,'-B',str(install/'app/tools/r3hd_intake.py'),'verify',str(install/'data/content'),'--json']
    output=p/('content-'+phase+'.json')
    with output.open('x') as f,(p/('content-'+phase+'.stderr.txt')).open('x') as err:
        r=subprocess.run(cmd,cwd=install,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=err,timeout=900)
    C.need(r.returncode==0,'content manifest verification failed; preserve evidence')
    j=C.read_json(output.read_bytes())
    C.need(j['result']=='supported' and j['kind']=='tree' and j['files']==915 and
           all(j[n]==[] for n in ('missing','extra','wrong_size','wrong_hash')),'content receipt not complete PASS')


def judge(code,forced,text,observation):
    milestones={n:n in text for n in ('SDL video driver: wayland',"GPU plugin 'xenos' loaded",
       'VulkanPresenter: Created','M2 xex_loaded entry=820E13F8','M2 runtime_initialized','M2 launch_prepared','M11 pacing series=host_present')}
    # launch_prepared is pre-thread; even pacing alone is not a gameplay acceptance.
    ok=code==0 and not forced and all(milestones.values()) and observation=='yes'
    fatal=('--game_data_root does not exist:','Entrypoint XEX not found:','Failed to load XEX','Runtime setup failed:',
           'VK_ERROR_DEVICE_LOST','VK_LAYER_LS_frame_generation','M6 window hidden=true')
    # E-399: this exact optional path probe also occurs in the authenticated LM-C
    # successful menu run. Retain it in logs; no general error-category exemption.
    benign=re.compile(r'^\[[^\]\r\n]+\] \[error\] \[fs\] \[t[0-9]+\] ResolvePath\(\\D:\\Gamedata\) failed - device not found$')
    errors=[line for line in text.splitlines() if ('[error]' in line.lower() or '[critical]' in line.lower()) and not benign.fullmatch(line)]
    ok=ok and not any(x in text for x in fatal) and not errors
    ordered=('M2 xex_loaded entry=820E13F8','M2 runtime_initialized','M2 launch_prepared','M11 pacing series=host_present')
    if all(n in text for n in ordered):ok=ok and [text.index(n) for n in ordered]==sorted(text.index(n) for n in ordered)
    return {'status':'PASS' if ok else 'FAIL','scope':'bounded attended startup only','milestones':milestones,
        'human_saw_game_content':observation,'natural_exit_zero':code==0 and not forced,
        'gameplay_acceptance':'UNKNOWN','audio_input_save_correctness':'UNKNOWN',
        'other_distributions_and_Deck':'UNKNOWN'}


def human(present):
    N.native();C.need(present and sys.stdin.isatty(),'human-present and interactive terminal required; NO unattended run')
    print('Visible startup may affect focus/cursor, play sound, open physical input devices and cause controller outputs. Disconnect controllers if unwanted. Remain present; no automated input. Close ONLY this test window before 120 seconds; do not start gameplay.')
    C.need(input('Type AUTHORIZE VISIBLE AUDIO INPUT STARTUP: ')=='AUTHORIZE VISIBLE AUDIO INPUT STARTUP','not authorized')
    p=workspace();C.need(not (p/'attempt.json').exists(),'attempt exists; preserve it, no automatic retry')
    receipt();out,abi=N.inputs();install=p/'installation';C.need(install.resolve()==install,'linked installation')
    programs(install,out/C.PACKAGE)
    C.need((install/'data').resolve()==install/'data','linked data root')
    C.need(all(not (p/n).exists() and not (p/n).is_symlink() for n in ('test-user','test-cache','launch-environment')),'test state already exists; preserve it')
    plan=C.read_json((p/'prepared.json').read_bytes())
    C.need(plan['game_executed'] is False and plan['unattended_authorized'] is False and plan['package_sha256']==C.LOCK['package_sha256'],'preparation record')
    C.need(N.inventory(install/'data')==plan['data_inventory'],'data changed since verified extraction')
    C.file_hash(install/'data/content/Default.xex','77a4df54340aebcc79eb0f0053938c03b8efd2efdd3ffee26c00fdfef3c6e8ca')
    # Launch HOME distinct even from Python preparation; only explicit Wayland socket is shared.
    envroot=p/'launch-environment';envroot.mkdir();(envroot/'installation').mkdir()
    env=N.environment(envroot,'wayland');env['LD_LIBRARY_PATH']=str(install/'bin')
    env['DISABLE_LSFG']='1'  # Native log identifies this layer's advertised disable variable.
    env['R3HD_DS_LIGHT']='off';env['R3HD_DS_TRIGGER']='off';env['R3HD_DS_SPEAKER']='off';env['R3HD_DISCORD']='off'
    content_check(p,env,'before')
    args=[install/'bin/r3hd','--video_driver=wayland','--fullscreen=false','--gpu_plugin=xenos',
       '--game_data_root='+str(install/'data/content'),'--user_data_root='+str(p/'test-user'),
       '--cache_root='+str(p/'test-cache'),'--log_file='+str(p/'runtime.log'),'--log_level=debug','--log_flush_interval=1']
    for n in C.COMPONENTS:
        C.file_hash(install/'bin'/n,abi[n]['sha256'])
        with (p/(n+'.loader.txt')).open('x') as f:
            r=subprocess.run(['/lib64/ld-linux-x86-64.so.2','--list',str(install/'bin'/n)],env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=15)
        C.need(r.returncode==0 and 'not found' not in (p/(n+'.loader.txt')).read_text(),'native loader failure')
    C.write(p/'attempt.json',{'human_authorization':'AUTHORIZE VISIBLE AUDIO INPUT STARTUP','unattended':False,
        'argv':list(map(str,args)),'package_sha256':C.LOCK['package_sha256'],'DISABLE_LSFG':'1','timeout_seconds':120})
    # Reuse previously tested owned-process-group timeout and core suppression.
    code,forced=N.launch(args,p,env,120)
    C.write(p/'exit.json',{'exit':code,'timed_out_or_interrupted_or_remaining_group':forced})
    text='\n'.join(f.read_text(errors='replace') for f in (p/'process.log',p/'runtime.log') if f.exists())
    observation=input('Did you personally see recognizable game content (not just a blank window)? Type yes/no: ').strip()
    result=judge(code,forced,text,observation)
    try:
        programs(install,out/C.PACKAGE)
        C.need(N.inventory(install/'data')==plan['data_inventory'],'data modified during run')
        content_check(p,env,'after')
    except (ValueError,OSError,subprocess.SubprocessError) as e:result.update(status='FAIL',integrity_error=str(e))
    C.write(p/'result.json',result)
    C.need(result['status']=='PASS','startup criteria not met; preserve logs and STOP, no fallback/retry')
    print('R3HD_STAGE2C_VISIBLE_STARTUP PASS (bounded startup only; no gameplay acceptance)')


def collect():
    p=workspace();dest=p/'visible-private-evidence.zip'
    C.need(not dest.exists() and not Path(str(dest)+'.sha256').exists(),'evidence exists; preserve it')
    names=['OWNER.txt','prepared.json','data-prepare.log','attempt.json','process.json','exit.json','process.log','runtime.log','result.json']+[n+'.loader.txt' for n in C.COMPONENTS]
    names += ['content-'+phase+suffix for phase in ('before','after') for suffix in ('.json','.stderr.txt')]
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as z:
        for n in names:
            f=p/n
            if f.exists():
                C.need(f.is_file() and not f.is_symlink(),'linked evidence');z.write(f,n)
    with Path(str(dest)+'.sha256').open('x',encoding='ascii',newline='\n') as f:f.write(C.sha(dest)+'  '+dest.name+'\n')
    print(dest)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='action',required=True)
    p=sub.add_parser('prepare');p.add_argument('--source',type=Path,required=True)
    p=sub.add_parser('human');p.add_argument('--human-present',action='store_true');sub.add_parser('collect')
    a=ap.parse_args()
    try:
        if a.action=='prepare':prepare(a.source)
        elif a.action=='human':human(a.human_present)
        else:collect()
    except (ValueError,KeyError,OSError,subprocess.SubprocessError) as e:raise SystemExit('R3HD_VISIBLE STOP: '+str(e))
