"""Authenticate supplemental native receipts; never modifies received evidence."""
import json
from pathlib import Path
import re
import sys
import zipfile
HERE=Path(__file__).resolve().parent
if not (HERE/'checks.py').exists():sys.path.insert(0,str(HERE.parent/'finalize'))
import checks as C
LOCK=C.read_json((HERE/'STARTUP_LOCK.json').read_bytes())


def archive(path,group):
    row=LOCK['groups'][group];C.file_hash(path,row['zip_sha256'])
    side=Path(str(path)+'.sha256');C.file_hash(side,row['sidecar_sha256'])
    C.need(side.read_text().strip()==row['zip_sha256']+'  '+path.name,'ZIP sidecar contents')
    with zipfile.ZipFile(path) as z:
        names=z.namelist();C.need(len(names)==len(set(names)) and set(names)==set(row['members']),'supplement inventory')
        data={n:z.read(n) for n in names}
    for n,b in data.items():C.need(C.digest(b)==row['members'][n],'supplement member hash: '+n)
    sums={}
    for line in data['SHA256SUMS'].decode().splitlines():
        m=re.fullmatch('([0-9a-f]{64})  ([^/\\\\]+)',line);C.need(m and m[2] not in sums,'invalid/duplicate internal checksum')
        sums[m[2]]=m[1]
    C.need(set(sums)==set(data)-{'SHA256SUMS'},'internal checksum inventory')
    for n,h in sums.items():C.need(C.digest(data[n])==h,'internal checksum mismatch')
    C.need(data['OWNER.txt'].strip()==b'R3HD_BASELINE_FINAL_AND_PROBE_01','supplement owner')
    return data


def review(final,probe):
    a=archive(final,'finalization');b=archive(probe,'stage2c')
    f=C.read_json(a['finalization.json']);p=C.read_json(b['probe.json'])
    C.need(f['status']=='PASS' and f['kind']=='SUPPLEMENTAL_FINALIZATION' and f['original_orchestration_exit']==2 and
           f['uninterrupted_workflow_pass'] is False and f['game_executed'] is False and f['publishable'] is False,'finalization assertions')
    C.need(f['package_sha256']==C.LOCK['package_sha256'] and f['lgpl_source_sha256']==C.LOCK['lgpl_sha256'] and
           f['original_evidence_zip_sha256']==C.LOCK['files']['stage2b-private-evidence.zip'],'finalization artifact identity')
    C.need(a['DELIVERABLES.sha256'].decode()==C.LOCK['package_sha256']+'  '+f['package']+'\n'+C.LOCK['lgpl_sha256']+'  '+f['lgpl_source']+'\n','supplemental ledger contents')
    C.need(C.digest(a['immutable-recheck.json'])==C.LOCK['native_records']['evidence/sealed-inputs-after.json'],'immutable recheck differs')
    C.need(C.digest(a['package-recheck.txt'])==C.LOCK['files']['package-check-original-prefixed.txt'],'fresh package recheck differs')
    C.need(p['status']=='PASS' and p['package_sha256']==C.LOCK['package_sha256'] and p['game_entrypoint_executed'] is False and
           p['portable_exit']==2 and p['graphics_audio_input']=='NOT TESTED' and p['gameplay']=='UNKNOWN','probe assertions')
    C.need(set(p['loaders'])==set(C.COMPONENTS),'loader inventory')
    # Values cross-bind to the original native ABI record, not just this new receipt.
    original=C.read_json((HERE/'ABI_HASHES.json').read_bytes())
    for n,row in p['loaders'].items():
        C.need(row=={'exit':0,'sha256':original[n]},'loader receipt identity: '+n)
        text=b[n+'.loader.txt'].decode();C.need('not found' not in text and '/usr/lib/libc.so.6' in text,'host loader provider')
        if n in ('r3hd','librexruntime.so','librexgpu-xenos.so'):
            C.need('/R3HD-baseline-noble-2c-01/installation/bin/libffmpeg.so' in text,'packaged loader provider missing')
    C.need(b'PACKAGE_REQUIRED' in b['portable-prepare.txt'],'expected portable data stop missing')
    return {'supplemental_stage2b':'VERIFIED PASS','original_orchestration_exit':2,
            'stage2c_loader_portable':'VERIFIED PASS','game_entrypoint':'NOT EXECUTED',
            'native_return_codes':'zero supplied by maintainer; PASS receipts are final operations in scripts',
            'runtime_acceptance':'PARTIAL'}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=review(a.folder/'finalization/supplemental-private-evidence.zip',a.folder/'stage2c/supplemental-private-evidence.zip')
    C.write(a.out,result);print(json.dumps(result))
