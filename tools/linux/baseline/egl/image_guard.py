"""Image-only guard: no removals/version changes; only signed, locked EGL closure additions."""
import json
from pathlib import Path
import sys


def manifest(text):
    rows={}
    for line in text.splitlines():
        name,version,arch=line.split('\t');key=(name.split(':')[0],arch)
        if key in rows: raise ValueError('duplicate package '+name)
        rows[key]=version
    return rows


def check(before,after,lock):
    if any(after.get(k)!=v for k,v in before.items()): raise ValueError('existing image package removed/version changed')
    for key in after.keys()-before.keys():
        allowed=lock['allowed_transaction'].get(key[0])
        if not allowed or allowed['Architecture']!=key[1] or allowed['Version']!=after[key]:
            raise ValueError('unexpected image package/version: '+str(key))
    if after.get(('libegl-dev','amd64'))!='1.7.0-1build1': raise ValueError('wrong/missing libegl-dev')
    print('R3HD_EGL_IMAGE_PACKAGES PASS additions='+str(len(after.keys()-before.keys())))


if __name__=='__main__':
    p=Path(sys.argv[1]);check(manifest((p/'parent-packages.tsv').read_text()),
        manifest(Path('/opt/r3hd-packages.tsv').read_text()),json.loads((p/'EGL_LOCK.json').read_bytes()))
