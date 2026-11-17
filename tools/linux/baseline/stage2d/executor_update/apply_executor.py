"""Exact executor-path delta: copy authenticated guard-01 to new guard-02 only."""
import argparse
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent


def sha(b):return hashlib.sha256(b).hexdigest()


def apply(source,dest):
    lock=json.loads((HERE/'EXECUTOR_LOCK.json').read_bytes())
    if set(lock['replacements'])!={'protected_read.py','resume.py'}:raise ValueError('unexpected replacement inventory')
    if any(not isinstance(n,str) or n in ('.','..') or not n or any(c in n for c in '/\\:\0') for n in lock['expected_runner']):raise ValueError('unsafe runner member name')
    if source.resolve()!=source or not source.is_dir():raise ValueError('real absolute source runner required')
    if dest.exists() or dest.is_symlink() or dest.parent.resolve()!=dest.parent:raise ValueError('fresh real destination required; preserve existing')
    files={}
    for n,h in lock['expected_runner'].items():
        f=source/n
        if f.is_symlink() or not f.is_file():raise ValueError('missing/linked runner file: '+n)
        b=f.read_bytes()
        if sha(b)!=h:raise ValueError('runner local edit: '+n)
        files[n]=b
    for n,h in lock['replacements'].items():
        f=HERE/n;b=f.read_bytes()
        if f.is_symlink() or sha(b)!=h:raise ValueError('changed executor update: '+n)
        files[n]=b
    files['SHA256SUMS']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(files.items()) if n!='SHA256SUMS').encode()
    dest.mkdir()
    for n,b in files.items():
        with (dest/n).open('xb') as f:f.write(b)
    print('R3HD_EXECUTOR_UPDATE PASS; prior runner/receipts/workspace unchanged; NO GAME EXECUTION')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    try:apply(a.source,a.output)
    except (OSError,ValueError,KeyError) as e:raise SystemExit('R3HD_EXECUTOR_UPDATE STOP: '+str(e))
