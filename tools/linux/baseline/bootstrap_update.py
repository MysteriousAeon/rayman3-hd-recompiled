#!/usr/bin/env python3
"""Checked E-388 TLS-bootstrap update; no container or host configuration operations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

HERE = Path(__file__).resolve().parent
OLD = {'Containerfile':'9984d177b947254385df42fa8ee1ea1a76b1f6ef36526226c5eda8cac71459e0',
       'ubuntu.sources':'df2fdea0e7c79cf06f8a5703c9df02017b19198d715318c70c5bae304d833e2e',
       'validate_apt_sources.sh':'7c00d2368f86ce83a035cc802d341543d767e3891e13173b3060b54746975bae'}
TEXT = ('Containerfile','ubuntu.sources','validate_apt_sources.sh','bootstrap_apt.sh','validate_snapshot_lists.sh')
DATA = {'bootstrap/InRelease':('noble-updates.InRelease','inrelease_sha256'),
        'bootstrap/Packages.gz':('noble-updates-main.Packages.gz','index_sha256'),
        'bootstrap/ca-certificates.deb':('ca-certificates.deb','ca_sha256')}
BACKUP = 'gate-c-tls-update'


def sha(data): return hashlib.sha256(data).hexdigest()
def need(value, message):
    if not value: raise ValueError(message)
def read(path):
    need(path.is_file() and not path.is_symlink(), 'regular file required: '+str(path))
    return path.read_bytes()


def package_info(package):
    m=json.loads(read(package/'UPDATE.json'))
    need(m['format']=='R3HD_GATE_C_TLS_V1' and m['before']==OLD, 'update identity mismatch')
    need(set(m['recipe'])==set(TEXT)|set(DATA), 'recipe inventory mismatch')
    need(set(m['extra'])=={'resume_gate_c_tls.sh','BOOTSTRAP_LOCK.json'}, 'extra inventory mismatch')
    for n,h in dict(m['recipe'],**m['extra']).items():
        need(sha(read(package/n))==h, 'payload hash mismatch: '+n)
    lock=json.loads(read(package/'BOOTSTRAP_LOCK.json'))
    for n,(_,key) in DATA.items(): need(m['recipe'][n]==lock[key], 'bootstrap provenance mismatch: '+n)
    return m


def layout(task, expected):
    need(task.is_dir() and task.absolute()==task.resolve(), 'task path must be real, no symlink ancestors')
    for n in ('recipe','evidence'): need((task/n).is_dir() and not (task/n).is_symlink(), 'invalid task directory: '+n)
    recipe=task/'recipe'
    allowed=set(expected) | ({'bootstrap'} if any(n.startswith('bootstrap/') for n in expected) else set())
    paths=list(recipe.rglob('*'))
    need({p.relative_to(recipe).as_posix() for p in paths}==allowed, 'unexpected/missing recipe entries; no overwrite/reapply')
    need(all(not p.is_symlink() for p in paths), 'symlink recipe input')
    for n,h in expected.items(): need(sha(read(recipe/n))==h, 'local edit/hash mismatch: '+n)
    return recipe,task/'evidence'/BACKUP


def check(task,package=HERE):
    m=package_info(package)
    _,backup=layout(task,m['recipe'])
    need(backup.is_dir() and not backup.is_symlink(), 'backup missing')
    for n,h in OLD.items(): need(sha(read(backup/n))==h, 'original backup mismatch: '+n)
    need(read(backup/'UPDATE.json')==read(package/'UPDATE.json'), 'receipt mismatch')
    print('R3HD_GATE_C_TLS_CHECK PASS (inputs only; native image build NOT tested)')


def apply(task,package=HERE):
    m=package_info(package)
    recipe,backup=layout(task,OLD)
    need(not backup.exists() and not backup.is_symlink(), 'backup already exists')
    backup.mkdir()
    for n in OLD:
        with (backup/n).open('xb') as f: f.write(read(recipe/n))
    with (backup/'UPDATE.json').open('xb') as f: f.write(read(package/'UPDATE.json'))
    (recipe/'bootstrap').mkdir()
    for n in m['recipe']:
        target=recipe/n
        temp=target.with_name(target.name+'.tls-update.tmp')
        with temp.open('xb') as f:
            f.write(read(package/n));f.flush();os.fsync(f.fileno())
        os.replace(temp,target)
    check(task,package)
    print('R3HD_GATE_C_TLS_UPDATE PASS; preserve all previous attempts')


def inputs():
    root=HERE.parents[2]
    audit=root/'private/work/linux_build/bootstrap_audit'
    lock=json.loads(read(HERE/'BOOTSTRAP_LOCK.json'))
    result={n:read(HERE/n).replace(b'\r\n',b'\n') for n in TEXT}
    for n,(source,key) in DATA.items():
        result[n]=read(audit/source)
        need(sha(result[n])==lock[key], 'authenticated audit input missing/changed: '+source)
    return result


def build():
    root=HERE.parents[2];out=root/'private/work/linux_build/baseline_tls_update_final'
    need(not out.exists(), 'output exists; preserve it')
    recipe=inputs();entries=dict(recipe)
    for n in ('resume_gate_c_tls.sh','BOOTSTRAP_LOCK.json'):
        entries[n]=read(HERE/n).replace(b'\r\n',b'\n')
    m={'format':'R3HD_GATE_C_TLS_V1','before':OLD,'recipe':{n:sha(b) for n,b in recipe.items()},
       'extra':{n:sha(entries[n]) for n in ('resume_gate_c_tls.sh','BOOTSTRAP_LOCK.json')}}
    entries['UPDATE.json']=(json.dumps(m,indent=2)+'\n').encode()
    entries['apply_update.py']=Path(__file__).read_bytes().replace(b'\r\n',b'\n')
    out.mkdir();archive=out/'r3hd-stage2a-tls-update.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(entries.items()):
            info=zipfile.ZipInfo(n,date_time=(2026,11,8,0,0,0));info.external_attr=0o644<<16
            info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,b)
    digest=sha(read(archive))
    (out/(archive.name+'.sha256')).write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps({'path':str(archive),'bytes':archive.stat().st_size,'sha256':digest}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('build','apply','check'));p.add_argument('--task',type=Path)
    a=p.parse_args()
    try:
        if a.action=='build': build()
        else:
            need(a.task is not None,'--task required');(apply if a.action=='apply' else check)(a.task)
    except (ValueError,OSError,KeyError) as e:
        print('R3HD_GATE_C_TLS_UPDATE STOP:',e,file=sys.stderr);sys.exit(2)
