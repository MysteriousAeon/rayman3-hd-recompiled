"""Copy verified frozen runner to a new directory, overlay only guard additions."""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def sha(b):return hashlib.sha256(b).hexdigest()


def apply(original,dest):
    lock=json.loads((HERE/'UPDATE_LOCK.json').read_bytes())
    if original.resolve()!=original or not original.is_dir():raise ValueError('real absolute original toolkit required')
    if dest.exists() or dest.is_symlink() or dest.parent.resolve()!=dest.parent:raise ValueError('fresh real output required; preserve existing')
    files={}
    for n,h in lock['original_members'].items():
        p=original/n
        if not p.is_file() or p.is_symlink() or sha(p.read_bytes())!=h:raise ValueError('original toolkit local edit/missing file: '+n)
        files[n]=p.read_bytes()
    for n in ('proc_guard.py','protected_read.py','resume.py'):
        p=HERE/n;b=p.read_bytes()
        if p.is_symlink() or sha(b)!=lock['additions'][n]:raise ValueError('changed update: '+n)
        files[n]=b
    files['SHA256SUMS']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items()) if n!='SHA256SUMS').encode()
    dest.mkdir()
    for n,b in files.items():
        with (dest/n).open('xb') as f:f.write(b)
    print('R3HD_STAGE2D_GUARD_UPDATE PASS; original runner unchanged; NO GAME EXECUTION')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--original',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:apply(a.original,a.output)
    except (OSError,ValueError,KeyError) as e:raise SystemExit('R3HD_GUARD_UPDATE STOP: '+str(e))
