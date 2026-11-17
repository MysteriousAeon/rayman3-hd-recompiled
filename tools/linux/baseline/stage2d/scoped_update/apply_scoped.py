"""Copy authenticated guard-02 to fresh scoped-01; preserve all previous receipts."""
import argparse
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()


def apply(source,dest):
    lock=json.loads((HERE/'SCOPED_LOCK.json').read_bytes())
    if source.resolve()!=source or not source.is_dir():raise ValueError('real absolute source runner required')
    if dest.exists() or dest.is_symlink() or dest.parent.resolve()!=dest.parent:raise ValueError('fresh real destination required')
    if set(lock['additions'])!={'scoped_guard.py','scoped_resume.py'}:raise ValueError('unexpected additions')
    files={}
    for n,h in lock['expected_runner'].items():
        if not n or n in ('.','..') or any(c in n for c in '/\\:\0'):raise ValueError('unsafe runner member')
        f=source/n
        if f.is_symlink() or not f.is_file():raise ValueError('missing/linked source file: '+n)
        b=f.read_bytes()
        if sha(b)!=h:raise ValueError('local source edit: '+n)
        files[n]=b
    # The new runner does not carry the superseded privileged observer/entrypoint.
    # Source files/receipts remain untouched in the historical runner.
    for n in ('resume.py','proc_guard.py','protected_read.py'):files.pop(n)
    for n,h in lock['additions'].items():
        f=HERE/n;b=f.read_bytes()
        if f.is_symlink() or sha(b)!=h:raise ValueError('changed update: '+n)
        files[n]=b
    files['SHA256SUMS']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items()) if n!='SHA256SUMS').encode()
    dest.mkdir()
    for n,b in files.items():
        with (dest/n).open('xb') as f:f.write(b)
    print('R3HD_SCOPED_UPDATE PASS; previous runners/workspace unchanged; NO GAME EXECUTION')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:apply(a.source,a.output)
    except (ValueError,KeyError,OSError) as e:raise SystemExit('R3HD_SCOPED_UPDATE STOP: '+str(e))
