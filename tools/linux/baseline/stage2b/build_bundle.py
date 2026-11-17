#!/usr/bin/env python3
"""Build only the small private preparation toolkit. No source archive rebuild."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
FILES=('stage2b.py','run_native.sh','build_inside.sh','clang','clang++','collect.py','test_stage2b.py','HANDOFF.md','SDK_REPLAY.json')


def build(out):
    if out.exists(): raise ValueError('output exists; preserve it')
    data={n:(HERE/n).read_bytes().replace(b'\r\n',b'\n') for n in FILES}
    data['preflight.py']=(HERE.parent/'preflight.py').read_bytes().replace(b'\r\n',b'\n')
    data['kit_verify.py']=(HERE.parent/'prepare.py').read_bytes().replace(b'\r\n',b'\n')
    data['BUNDLE.json']=(json.dumps({'schema':1,'source_commit':'0414e72','files':{
        n:hashlib.sha256(b).hexdigest() for n,b in sorted(data.items())}},indent=2)+'\n').encode()
    out.mkdir()
    dest=out/'r3hd-stage2b-prep.zip'
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(data.items()):
            i=zipfile.ZipInfo(name,(1980,1,1,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED
            i.external_attr=(0o100755 if name in ('clang','clang++') else 0o100644)<<16
            z.writestr(i,raw)
    digest=hashlib.sha256(dest.read_bytes()).hexdigest()
    (out/(dest.name+'.sha256')).write_text(digest+'  '+dest.name+'\n',encoding='ascii')
    (out/'HANDOFF.md').write_bytes(data['HANDOFF.md'])
    print(json.dumps({'path':str(dest),'bytes':dest.stat().st_size,'sha256':digest}))
    return dest


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,
        default=ROOT/'private/work/linux_build/baseline_2b_prep_01')
    try: build(ap.parse_args().out)
    except (ValueError,OSError) as error: ap.exit(2,'STOP: '+str(error)+'\n')
