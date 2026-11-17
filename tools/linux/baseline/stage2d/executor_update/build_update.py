"""Minimal deterministic executor delta. Does not touch any earlier package."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
HERE=Path(__file__).resolve().parent


def build(out):
    if out.exists() or out.is_symlink():raise ValueError('output exists; preserve it')
    files={n:(HERE/n).read_bytes().replace(b'\r\n',b'\n') for n in ('apply_executor.py','EXECUTOR_LOCK.json','HANDOFF.md')}
    for n in ('protected_read.py','resume.py'):files[n]=(HERE.parent/'guard_update'/n).read_bytes().replace(b'\r\n',b'\n')
    lock=json.loads(files['EXECUTOR_LOCK.json']);lock['replacements']={n:hashlib.sha256(files[n]).hexdigest() for n in ('protected_read.py','resume.py')}
    files['EXECUTOR_LOCK.json']=(json.dumps(lock,indent=2,sort_keys=True)+'\n').encode()
    files['SHA256SUMS']=''.join(hashlib.sha256(b).hexdigest()+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    out.mkdir();dest=out/'r3hd-stage2d-executor-update.zip'
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):
            i=zipfile.ZipInfo(n,(1980,1,1,0,0,0));i.create_system=3;i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16
            z.writestr(i,b,compresslevel=9)
    h=hashlib.sha256(dest.read_bytes()).hexdigest();(out/(dest.name+'.sha256')).write_bytes((h+'  '+dest.name+'\n').encode())
    (out/'HANDOFF.md').write_bytes(files['HANDOFF.md']);print(dest,dest.stat().st_size,h)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);build(p.parse_args().out)
