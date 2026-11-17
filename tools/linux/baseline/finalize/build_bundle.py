"""Prepare only the small finalization/probe toolkit. No source archive or downloads."""
import argparse
from pathlib import Path
import zipfile
import checks as C


def build(out):
    C.need(not out.exists() and not out.is_symlink(),'output exists; preserve it')
    files={n:(C.HERE/n).read_bytes().replace(b'\r\n',b'\n') for n in ('checks.py','native.py','EVIDENCE_LOCK.json','HANDOFF.md')}
    files['SHA256SUMS']=''.join(C.digest(b)+'  '+n+'\n' for n,b in sorted(files.items())).encode()
    out.mkdir();dest=out/'r3hd-baseline-final-and-probe.zip'
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):
            i=zipfile.ZipInfo(n,(1980,1,1,0,0,0));i.create_system=3;i.external_attr=0o100644<<16;i.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(i,b,compresslevel=9)
    with Path(str(dest)+'.sha256').open('x',encoding='ascii',newline='\n') as f:f.write(C.sha(dest)+'  '+dest.name+'\n')
    (out/'HANDOFF.md').write_bytes(files['HANDOFF.md'])
    print(dest, dest.stat().st_size,C.sha(dest))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    build(p.parse_args().out)
