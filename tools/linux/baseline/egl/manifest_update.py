"""Small manifest-check update; clone authenticated old toolkit, never overwrite it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OLD_BUNDLE='40f53419d374dcf9a02558d188de58f3f5b311a130a9db5d5efaf3764cca111a'
OLD_ZIP='47749cc5395c5bcbe11ed2033a045e65ee23f19eb088370a5dabd73a7224e92c'


def need(ok,message):
    if not ok:raise ValueError(message)


def sha(data):return hashlib.sha256(data).hexdigest()


def inventory(folder,record):
    need(all(Path(n).name==n for n in record['files']),'unsafe toolkit name')
    need({p.name for p in folder.iterdir()}==set(record['files'])|{'BUNDLE.json'},'toolkit inventory differs')
    for n,h in record['files'].items():
        p=folder/n
        need(p.is_file() and not p.is_symlink() and sha(p.read_bytes())==h,'toolkit local edit/type: '+n)


def apply(old,dest,package=HERE):
    old=old.absolute();dest=dest.absolute()
    need(old.is_dir() and old.resolve()==old,'old toolkit path must be real, without symlink ancestors')
    need(dest.parent.resolve()==dest.parent and dest.parent.is_dir(),'destination parent must be real')
    need(not dest.exists() and not dest.is_symlink(),'destination exists; preserve it')
    need(not dest.is_relative_to(old) and not old.is_relative_to(dest),'overlapping toolkit paths')
    p=old/'BUNDLE.json'
    need(p.is_file() and not p.is_symlink() and sha(p.read_bytes())==OLD_BUNDLE,'not the original EGL toolkit')
    before=json.loads(p.read_bytes());inventory(old,before)
    meta=json.loads((package/'UPDATE.json').read_bytes())
    need(meta['format']=='R3HD_EGL_MANIFEST_UPDATE_V1' and meta['old_bundle_sha256']==OLD_BUNDLE,'wrong update identity')
    need(set(meta['files'])=={'retry.py','BUNDLE.json'},'unexpected replacement set')
    payload={}
    for n,h in meta['files'].items():
        p=package/n
        need(p.is_file() and not p.is_symlink(),'unsafe update payload')
        payload[n]=p.read_bytes();need(sha(payload[n])==h,'update payload hash: '+n)
    after=json.loads(payload['BUNDLE.json'])
    expected=json.loads(json.dumps(before));expected['files']['retry.py']=sha(payload['retry.py'])
    need(after==expected,'update changes more than retry.py')
    # Every original file was authenticated before the first write. Never touch old.
    dest.mkdir()
    for n in sorted(set(before['files'])|{'BUNDLE.json'}):
        with (dest/n).open('xb') as f:f.write(payload[n] if n in payload else (old/n).read_bytes())
        shutil.copymode(old/n,dest/n)
    inventory(dest,after)
    need(sha((dest/'BUNDLE.json').read_bytes())==meta['files']['BUNDLE.json'],'new bundle mismatch')
    print('R3HD_EGL_MANIFEST_UPDATE PASS; original toolkit/workspaces/images unchanged')


def build(out):
    need(not out.exists() and not out.is_symlink(),'output exists; preserve it')
    source=ROOT/'private/work/linux_build/baseline_2b_egl_ready/r3hd-stage2b-egl.zip'
    need(sha(source.read_bytes())==OLD_ZIP,'original transfer ZIP changed')
    with zipfile.ZipFile(source) as z:
        before=z.read('BUNDLE.json');need(sha(before)==OLD_BUNDLE,'original bundle changed')
    raw=(HERE/'retry.py').read_bytes().replace(b'\r\n',b'\n')
    after=json.loads(before);after['files']['retry.py']=sha(raw)
    payload={'retry.py':raw,'BUNDLE.json':(json.dumps(after,indent=2)+'\n').encode()}
    meta={'format':'R3HD_EGL_MANIFEST_UPDATE_V1','old_bundle_sha256':OLD_BUNDLE,
          'files':{n:sha(b) for n,b in payload.items()}}
    payload['UPDATE.json']=(json.dumps(meta,indent=2)+'\n').encode()
    payload['manifest_update.py']=(HERE/'manifest_update.py').read_bytes().replace(b'\r\n',b'\n')
    payload['MANIFEST_HANDOFF.md']=(HERE/'MANIFEST_HANDOFF.md').read_bytes().replace(b'\r\n',b'\n')
    payload['SHA256SUMS']=''.join(sha(b)+'  '+n+'\n' for n,b in sorted(payload.items())).encode()
    out.mkdir();dest=out/'r3hd-egl-manifest-update.zip'
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(payload.items()):
            i=zipfile.ZipInfo(n,(1980,1,1,0,0,0));i.create_system=3
            i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16
            z.writestr(i,b,compresslevel=9)
    digest=sha(dest.read_bytes())
    (out/(dest.name+'.sha256')).write_text(digest+'  '+dest.name+'\n',encoding='ascii')
    (out/'MANIFEST_HANDOFF.md').write_bytes(payload['MANIFEST_HANDOFF.md'])
    print(json.dumps({'path':str(dest),'bytes':dest.stat().st_size,'sha256':digest}))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='action',required=True)
    p=sub.add_parser('build');p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('apply');p.add_argument('--old',type=Path,required=True);p.add_argument('--dest',type=Path,required=True)
    a=ap.parse_args()
    try:
        if a.action=='build':build(a.out)
        else:apply(a.old,a.dest)
    except (ValueError,KeyError,OSError) as e:raise SystemExit('R3HD_EGL_MANIFEST_UPDATE STOP: '+str(e))
