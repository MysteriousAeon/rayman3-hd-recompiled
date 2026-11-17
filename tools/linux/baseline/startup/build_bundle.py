"""Small preparation/manual-handoff export; never exports SDK/game material."""
import argparse
from pathlib import Path
import subprocess
import zipfile
import supplements as S
C=S.C
ROOT=Path(__file__).resolve().parents[4]


def build(out):
    C.need(not out.exists() and not out.is_symlink(),'output exists; preserve it')
    files={n:(S.HERE/n).read_bytes().replace(b'\r\n',b'\n') for n in
           ('startup.py','supplements.py','STARTUP_LOCK.json','ABI_HASHES.json','HANDOFF.md')}
    for n in ('checks.py','EVIDENCE_LOCK.json'):
        files[n]=subprocess.check_output(['git','-C',str(ROOT),'show','29c5ea3:tools/linux/baseline/finalize/'+n])
    files['SHA256SUMS']=''.join(C.digest(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    out.mkdir();dest=out/'r3hd-stage2c-attended-startup.zip'
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):
            i=zipfile.ZipInfo(n,(1980,1,1,0,0,0));i.create_system=3;i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16
            z.writestr(i,b,compresslevel=9)
    with Path(str(dest)+'.sha256').open('x',encoding='ascii',newline='\n') as f:f.write(C.sha(dest)+'  '+dest.name+'\n')
    (out/'HANDOFF.md').write_bytes(files['HANDOFF.md']);print(dest,dest.stat().st_size,C.sha(dest))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    build(p.parse_args().out)
