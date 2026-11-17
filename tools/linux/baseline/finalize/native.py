"""CachyOS read-only Stage2B finalization, then isolated loader/portable probe only.

Never invokes r3hd, a game launcher, compiler, container build or physical device.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile
import checks as C


def command(args,log,env,cwd):
    with log.open('x',encoding='utf-8') as f:
        try:
            p=subprocess.run(list(map(str,args)),env=env,cwd=cwd,stdin=subprocess.DEVNULL,
                             stdout=f,stderr=subprocess.STDOUT,timeout=120)
        except subprocess.TimeoutExpired:
            # subprocess.run kills/waits only its own direct child. These commands
            # have no long-lived child trees or game process; no process-name kill.
            raise ValueError('bounded command timeout; preserve '+str(log)) from None
    return p.returncode,log.read_text()


def environment(home,binpath=None):
    home.mkdir()
    env={'PATH':'/usr/bin:/bin','HOME':str(home),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8',
         'TZ':'UTC','PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(home)}
    for key,name in (('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('XDG_DATA_HOME','data'),('XDG_RUNTIME_DIR','run')):
        p=home/name;p.mkdir(mode=0o700);env[key]=str(p)
    if binpath is not None:env['LD_LIBRARY_PATH']=str(binpath)
    return env


def start(dest):
    C.need(platform.system()=='Linux' and platform.machine()=='x86_64' and os.getuid()!=0,'native non-root Linux amd64 required')
    C.need(dest.parent.resolve()==dest.parent and dest.parent.is_dir(),'real destination parent required')
    C.need(not dest.exists() and not dest.is_symlink(),'destination exists: preserve; do not reapply')
    C.need(shutil.disk_usage(dest.parent).free>=1_000_000_000,'at least 1,000,000,000 free bytes required')
    dest.mkdir();(dest/'OWNER.txt').write_text('R3HD_BASELINE_FINAL_AND_PROBE_01\n')


def receipts(dest):
    files=sorted(p for p in dest.rglob('*') if p.is_file())
    # Probe home contains package binaries; never archive that tree in evidence.
    files=[p for p in files if not p.relative_to(dest).parts[0] in ('installation','os-home')]
    with (dest/'SHA256SUMS').open('x',encoding='ascii',newline='\n') as f:
        for p in files:f.write(C.sha(p)+'  '+p.relative_to(dest).as_posix()+'\n')


def finish(task,runner,dest):
    task=task.absolute();runner=runner.absolute();dest=dest.absolute()
    C.need(task==Path.home()/'Projects/R3HD-baseline-noble-2b-egl-01' and task.resolve()==task,'wrong original workspace')
    C.need((task/'evidence/OWNER.txt').read_text().strip()=='R3HD_STAGE2B_EGL_01','wrong original workspace owner')
    C.need(runner.resolve()==runner,'linked original toolkit path')
    C.file_hash(runner/'BUNDLE.json',C.LOCK['runner_bundle_sha256'])
    record=C.read_json((runner/'BUNDLE.json').read_bytes())
    C.need({p.name for p in runner.iterdir()}==set(record['files'])|{'BUNDLE.json'},'original toolkit inventory differs')
    for n,h in record['files'].items():
        C.need(Path(n).name==n,'unsafe toolkit name');C.file_hash(runner/n,h)
    C.file_hash(task/'stage2b-private-evidence.zip',C.LOCK['files']['stage2b-private-evidence.zip'])
    for n,h in C.LOCK['native_records'].items():C.file_hash(task/n,h)
    out=task/C.REL
    C.file_hash(out/'package-check.json',C.LOCK['files']['package-check.json'])
    C.file_hash(out/'acceptance.json',C.LOCK['files']['acceptance.json'])
    C.file_hash(task/'evidence/package-check-original-prefixed.txt',C.LOCK['files']['package-check-original-prefixed.txt'])
    C.file_hash(out/C.PACKAGE,C.LOCK['package_sha256']);C.file_hash(out/'lgpl'/C.SOURCE,C.LOCK['lgpl_sha256'])
    C.need(not (out/'DELIVERABLES.sha256').exists() and not (out/'DELIVERABLES.sha256').is_symlink(),
           'unexpected original ledger now exists; preserve and review')
    C.need(dest==Path.home()/'Projects/R3HD-baseline-noble-2b-final-01','wrong finalization destination')
    start(dest);env=environment(dest/'os-home')
    # Import the exact authenticated original acceptance implementation for read-only
    # immutable checks. Do not run its exclusive-writing package/ABI actions again.
    spec=importlib.util.spec_from_file_location('frozen_stage2b',runner/'stage2b.py');B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
    manifest=(task/'KIT_MANIFEST.json').read_bytes()
    normalized=manifest.replace(b'\r\n',b'\n')
    C.need(b'\r' not in normalized and C.digest(normalized.replace(b'\n',b'\r\n'))==
           C.read_json((runner/'EGL_LOCK.json').read_bytes())['kit_manifest_sha256'],'sealed manifest changed')
    previous_locks=os.environ.get('GIT_OPTIONAL_LOCKS')
    os.environ['GIT_OPTIONAL_LOCKS']='0'  # git status must not refresh the old index.
    try:checked=B.immutable(task/'work',C.read_json(manifest))
    finally:
        if previous_locks is None:os.environ.pop('GIT_OPTIONAL_LOCKS',None)
        else:os.environ['GIT_OPTIONAL_LOCKS']=previous_locks
    C.write(dest/'immutable-recheck.json',checked)
    # Frozen package checker still has the historical prefix. Decode exactly one
    # authenticated command output; do not rewrite any old *.json or source file.
    code,raw=command(['/usr/bin/python3','-B',task/'work/tools/linux/r3hd_linux_package.py','check',out/C.PACKAGE],
                     dest/'package-recheck.txt',env,task/'work')
    C.need(code==0,'original static package recheck failed')
    new=C.old_record(raw.encode());old=C.private_record((out/'package-check.json').read_bytes())
    C.need(new==old,'fresh package check differs from supplemental record')
    abi=C.read_json((out/'abi.json').read_bytes())['components']
    C.package_files(out/C.PACKAGE,abi)
    ledger=''.join(C.sha(p)+'  '+str(p)+'\n' for p in (out/C.PACKAGE,out/'lgpl'/C.SOURCE))
    with (dest/'DELIVERABLES.sha256').open('x',encoding='ascii',newline='\n') as f:f.write(ledger)
    C.write(dest/'finalization.json',{'status':'PASS','kind':'SUPPLEMENTAL_FINALIZATION',
        'original_orchestration_exit':2,'uninterrupted_workflow_pass':False,
        'package_sha256':C.LOCK['package_sha256'],'lgpl_source_sha256':C.LOCK['lgpl_sha256'],
        'task':str(task),'package':str(out/C.PACKAGE),'lgpl_source':str(out/'lgpl'/C.SOURCE),
        'original_evidence_zip_sha256':C.LOCK['files']['stage2b-private-evidence.zip'],
        'game_executed':False,'publishable':False})
    receipts(dest);print('R3HD_STAGE2B_SUPPLEMENTAL_FINALIZATION PASS; original orchestration exit=2 retained')


def probe(final,dest):
    final=final.absolute();dest=dest.absolute()
    C.need(final==Path.home()/'Projects/R3HD-baseline-noble-2b-final-01' and final.resolve()==final,'wrong supplemental finalization')
    f=C.read_json((final/'finalization.json').read_bytes())
    C.need(f['status']=='PASS' and f['kind']=='SUPPLEMENTAL_FINALIZATION' and
           f['original_orchestration_exit']==2 and f['uninterrupted_workflow_pass'] is False,'finalization not accepted')
    expected=Path.home()/'Projects/R3HD-baseline-noble-2b-egl-01'/C.REL
    C.need(f['package']==str(expected/C.PACKAGE) and f['lgpl_source']==str(expected/'lgpl'/C.SOURCE),'unexpected artifact paths')
    package=Path(f['package']);C.file_hash(package,C.LOCK['package_sha256']);C.file_hash(Path(f['lgpl_source']),C.LOCK['lgpl_sha256'])
    C.file_hash(expected/'abi.json',C.LOCK['native_records'][C.REL+'abi.json'])
    C.need(dest==Path.home()/'Projects/R3HD-baseline-noble-2c-01','wrong isolated probe destination')
    C.need(Path('/lib64/ld-linux-x86-64.so.2').is_file() and Path('/usr/bin/python3').is_file(),'existing host loader/python required')
    start(dest);install=dest/'installation';install.mkdir()
    abi=C.read_json((expected/'abi.json').read_bytes())['components']
    # Validate completely before the first member is written, then verify again
    # during extraction. Package hash pins all Python/launcher code as well as ELFs.
    C.package_files(package,abi);C.package_files(package,abi,install)
    C.need(not any((install/n).exists() for n in ('data','profiles','settings.json','installer.json','sessions')),'test installation already has user state')
    env=environment(dest/'os-home',install/'bin');rows={}
    for n in C.COMPONENTS:
        C.file_hash(install/'bin'/n,abi[n]['sha256'])
        code,log=command(['/lib64/ld-linux-x86-64.so.2','--list',install/'bin'/n],dest/(n+'.loader.txt'),env,install)
        C.need(code==0 and 'not found' not in log,'native loader closure failed: '+n)
        for dep in abi[n]['needed']:
            if dep in C.COMPONENTS:
                C.need(str(install/'bin'/dep) in log,'packaged dependency not selected: '+dep)
        rows[n]={'exit':code,'sha256':C.sha(install/'bin'/n)}
    # The packaged prepare action verifies files/platform and intentionally stops
    # on absent game data. No Play.sh, settings GUI, r3hd or r3hd --help execution.
    code,log=command(['/usr/bin/python3','-B',install/'app/tools/r3hd_portable.py','prepare','--no-input'],
                     dest/'portable-prepare.txt',env,install)
    C.need(code==2 and 'PACKAGE_REQUIRED' in log,'expected data-free portable stop not reached')
    for n in C.COMPONENTS:C.file_hash(install/'bin'/n,abi[n]['sha256'])
    C.need(not any((install/n).exists() for n in ('data','profiles','settings.json','installer.json','sessions')),'unexpected user state created')
    C.write(dest/'probe.json',{'status':'PASS','scope':'native loader closure + packaged Python preparation only',
        'package_sha256':C.LOCK['package_sha256'],'loaders':rows,'portable_exit':code,
        'game_entrypoint_executed':False,'graphics_audio_input':'NOT TESTED','gameplay':'UNKNOWN',
        'runtime_acceptance':'PARTIAL; real r3hd startup requires approved nonintrusive runner or explicit human launch'})
    receipts(dest);print('R3HD_STAGE2C_LOADER_PORTABLE PASS; r3hd entrypoint NOT EXECUTED; runtime acceptance PARTIAL')


def collect(dest):
    C.need(dest.resolve()==dest and dest.name in ('R3HD-baseline-noble-2b-final-01','R3HD-baseline-noble-2c-01'),'wrong collection destination')
    C.need((dest/'OWNER.txt').read_text().strip()=='R3HD_BASELINE_FINAL_AND_PROBE_01','wrong evidence owner')
    archive=dest/'supplemental-private-evidence.zip';C.need(not archive.exists(),'evidence ZIP exists; preserve it')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(dest.iterdir()):
            if p.is_file() and not p.is_symlink() and (p.suffix in ('.json','.txt','.sha256') or p.name=='SHA256SUMS'):
                z.write(p,p.name)
    with Path(str(archive)+'.sha256').open('x',encoding='ascii',newline='\n') as f:f.write(C.sha(archive)+'  '+archive.name+'\n')
    print(archive)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('finish');a.add_argument('--task',type=Path,required=True);a.add_argument('--runner',type=Path,required=True);a.add_argument('--dest',type=Path,required=True)
    a=s.add_parser('probe');a.add_argument('--final',type=Path,required=True);a.add_argument('--dest',type=Path,required=True)
    a=s.add_parser('collect');a.add_argument('--dest',type=Path,required=True)
    a=p.parse_args()
    try:
        if a.action=='finish':finish(a.task,a.runner,a.dest)
        elif a.action=='probe':probe(a.final,a.dest)
        else:collect(a.dest.absolute())
    except (ValueError,KeyError,OSError,subprocess.SubprocessError) as e:raise SystemExit('R3HD_BASELINE STOP: '+str(e))
