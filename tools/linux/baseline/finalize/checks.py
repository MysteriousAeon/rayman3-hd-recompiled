"""Read-only integrity primitives for bounded finalization and loader probes."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

HERE=Path(__file__).resolve().parent
LOCK=json.loads((HERE/'EVIDENCE_LOCK.json').read_bytes())
REL='work/private/work/linux_build/noble_2b01/'
PACKAGE='r3hd-linux-noble-2b01.tar.gz'
SOURCE='r3hd-lgpl-source-1.1.0-linux-x86_64.zip'
COMPONENTS=('r3hd','librexruntime.so','librexgpu-xenos.so','libffmpeg.so','libmspack.so')
TOP='Rayman3HDRecompiled-Linux'


def need(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def digest(b):return hashlib.sha256(b).hexdigest()


def read_json(raw):
    def unique(pairs):
        out={}
        for k,v in pairs:
            need(k not in out,'duplicate JSON key: '+k);out[k]=v
        return out
    def invalid_constant(value):raise ValueError('non-JSON constant: '+value)
    return json.loads(raw,object_pairs_hook=unique,parse_constant=invalid_constant)


def old_record(raw):
    prefix=b'R3HD_LINUX_PACKAGE '
    need(raw.startswith(prefix),'unexpected historical package output prefix')
    return private_record(raw[len(prefix):])


def private_record(raw):
    j=read_json(raw)
    need(isinstance(j,dict) and j.get('result')=='PASS' and j.get('publishable') is False,'not private package PASS')
    need(isinstance(j.get('sha256'),str) and re.fullmatch('[a-f0-9]{64}',j['sha256']),'invalid package hash')
    return j


def file_hash(path,expected):
    need(path.is_file() and not path.is_symlink(),'not a regular file: '+str(path))
    need(sha(path)==expected,'hash mismatch: '+str(path))


def write(path,j):
    with path.open('x',encoding='utf-8',newline='\n') as f:json.dump(j,f,indent=2,sort_keys=True);f.write('\n')


def package_files(package,abi,dest=None):
    """Authenticated package only. No tar extractall, links, traversal or unbounded size."""
    seen={};data={};total=0
    with tarfile.open(package,'r:gz') as t:
        for m in t:
            parts=PurePosixPath(m.name).parts
            need(m.isfile() and len(parts)>1 and parts[0]==TOP and
                 m.name=='/'.join(parts) and not any(p in ('.','..') for p in parts) and
                 '\\' not in m.name and ':' not in m.name,'unsafe package member')
            rel='/'.join(parts[1:]);need(rel not in seen,'duplicate package member')
            need(m.mode in (0o644,0o755) and (m.mode==0o755)==(rel in ('Play.sh','Settings.sh','bin/r3hd')),'unexpected package mode')
            total+=m.size;need(0<=m.size<=200_000_000 and total<=500_000_000,'package size budget exceeded')
            b=t.extractfile(m).read();seen[rel]={'sha256':digest(b),'size':len(b)}
            if rel in ('portable.json','payload.json'):data[rel]=read_json(b)
            if rel.startswith('bin/'):
                n=rel[4:];need(n in COMPONENTS and digest(b)==abi[n]['sha256'],'package binary/ABI mismatch')
            if dest is not None:
                p=dest/rel;p.parent.mkdir(parents=True,exist_ok=True)
                with p.open('xb') as f:f.write(b)
                p.chmod(m.mode)
    portable=data['portable.json'];payload=data['payload.json']
    need(portable['publishable'] is False and payload['publishable'] is False,'publishable package refused')
    need(set(seen)==set(portable['files'])|{'portable.json'},'portable inventory mismatch')
    need(all(seen[n]==v for n,v in portable['files'].items()),'portable file integrity mismatch')
    need({n[4:] for n in seen if n.startswith('bin/')}==set(COMPONENTS),'native component inventory')
    src=portable['lgpl']['corresponding_source']
    need(src['archive']==SOURCE and src['sha256']==LOCK['lgpl_sha256'],'LGPL source binding')
    return portable
