#!/usr/bin/env python3
"""Collect private build/static evidence only; no binaries, sources, assets or execution."""
import hashlib
import json
from pathlib import Path
import zipfile

task=Path.home()/'Projects/R3HD-baseline-noble-2b-01'
if task.resolve()!=task or (task/'evidence/OWNER.txt').read_text().strip()!='R3HD_STAGE2B_01':
    raise SystemExit('STOP: not this task workspace')
dest=task/'stage2b-private-evidence.zip'
if dest.exists(): raise SystemExit('STOP: evidence ZIP exists; preserve it')
out=task/'work/private/work/linux_build/noble_2b01'
files=[p for p in (task/'evidence').rglob('*') if p.suffix in ('.json','.txt','.log','.sha256','.id','.tsv')]
if out.exists():
    for p in out.rglob('*'):
        rel=p.relative_to(out)
        if any(part in ('build','host-clang','lgpl-plain','lgpl-modified','lgpl','abi-payload') for part in rel.parts): continue
        if p.suffix in ('.json','.txt','.log','.tsv') or p.name=='DELIVERABLES.sha256': files.append(p)
with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(set(files)):
        if p.is_file() and not p.is_symlink(): z.write(p,p.relative_to(task).as_posix())
    z.writestr('PRIVATE.txt','PRIVATE technical evidence; may name game symbols or SDK diagnostics. No publication.\n')
digest=hashlib.sha256(dest.read_bytes()).hexdigest()
with (task/(dest.name+'.sha256')).open('x',encoding='ascii') as f: f.write(digest+'  '+dest.name+'\n')
print(json.dumps({'path':str(dest),'sha256':digest,'native_exit_status':(task/'evidence/exit-status.txt').read_text().strip()}))
