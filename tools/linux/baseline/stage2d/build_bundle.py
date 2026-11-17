"""Reproducible private Stage2D preparation export; no game or SDK contents."""
import argparse
from pathlib import Path
import subprocess
import zipfile
import gameplay as G
C=G.C
ROOT=Path(__file__).resolve().parents[4]


def build(out):
    C.need(not out.exists() and not out.is_symlink(),'output exists; preserve it')
    files={n:(G.HERE/n).read_bytes().replace(b'\r\n',b'\n') for n in ('gameplay.py','HANDOFF.md')}
    groups={'audio_diag':('audio_diag.py','forensic.py','DIAG_LOCK.json','pulse_review.py','PULSE_RESULT_LOCK.json'),
        'visible':('visible.py','review.py','VISIBLE_LOCK.json'),
        'startup':('startup.py','supplements.py','STARTUP_LOCK.json','ABI_HASHES.json'),
        'finalize':('checks.py','EVIDENCE_LOCK.json')}
    for group,names in groups.items():
        for n in names:files[n]=subprocess.check_output(['git','-C',str(ROOT),'show','00a00f4737480d1d80f9d5f8324868676e63548e:tools/linux/baseline/'+group+'/'+n])
    files['SHA256SUMS']=''.join(C.digest(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    out.mkdir();dest=out/'r3hd-stage2d.zip'
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):
            i=zipfile.ZipInfo(n,(1980,1,1,0,0,0));i.create_system=3;i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16
            z.writestr(i,b,compresslevel=9)
    with Path(str(dest)+'.sha256').open('x',encoding='ascii',newline='\n') as f:f.write(C.sha(dest)+'  '+dest.name+'\n')
    (out/'HANDOFF.md').write_bytes(files['HANDOFF.md']);print(dest,dest.stat().st_size,C.sha(dest))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);build(p.parse_args().out)
