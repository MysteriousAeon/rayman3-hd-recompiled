"""Small EGL retry toolkit from frozen 5c0729b tooling; never reseals source/SDK inputs."""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess
import zipfile

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
FILES=('Containerfile','image_guard.py','retry.py','retry_inside.sh','run_egl.sh','EGL_LOCK.json','EGL_HANDOFF.md','test_egl.py')


def original(name):
    return subprocess.check_output(['git','-C',str(ROOT),'show','5c0729b:'+name])


def build(out):
    if out.exists():raise ValueError('output exists; preserve it')
    names=('stage2b.py','run_native.sh','build_inside.sh','clang','clang++','collect.py','test_stage2b.py','HANDOFF.md','SDK_REPLAY.json')
    data={n:original('tools/linux/baseline/stage2b/'+n) for n in names}
    data['preflight.py']=original('tools/linux/baseline/preflight.py');data['kit_verify.py']=original('tools/linux/baseline/prepare.py')
    # Keep the frozen collector as evidence, and make a separate collector for the new task only.
    raw=data['collect.py'];assert raw.count(b'R3HD-baseline-noble-2b-01')==1 and raw.count(b'R3HD_STAGE2B_01')==1
    data['collect_egl.py']=raw.replace(b'R3HD-baseline-noble-2b-01',b'R3HD-baseline-noble-2b-egl-01').replace(b'R3HD_STAGE2B_01',b'R3HD_STAGE2B_EGL_01')
    data.update({n:(HERE/n).read_bytes().replace(b'\r\n',b'\n') for n in FILES})
    data['BUNDLE.json']=(json.dumps({'schema':1,'source_commit':'0414e72','retry':'EGL only; 5c0729b acceptance unchanged',
        'files':{n:hashlib.sha256(b).hexdigest() for n,b in sorted(data.items())}},indent=2)+'\n').encode()
    out.mkdir();dest=out/'r3hd-stage2b-egl.zip'
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(data.items()):
            i=zipfile.ZipInfo(n,(1980,1,1,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16;z.writestr(i,b,compresslevel=9)
    digest=hashlib.sha256(dest.read_bytes()).hexdigest()
    (out/(dest.name+'.sha256')).write_text(digest+'  '+dest.name+'\n',encoding='ascii')
    (out/'EGL_HANDOFF.md').write_bytes(data['EGL_HANDOFF.md'])
    print(json.dumps({'path':str(dest),'bytes':dest.stat().st_size,'sha256':digest}));return dest


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,
        default=ROOT/'private/work/linux_build/baseline_2b_egl_ready')
    build(ap.parse_args().out)
