"""Authenticate complete transferred pre-failure evidence and separate supplements."""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import zipfile
import checks as C


def review(folder):
    extra={p.name for p in folder.iterdir()}-set(C.LOCK['files'])
    C.need(extra<= {'finalization','stage2c'} and all((folder/n).is_dir() and not (folder/n).is_symlink() for n in extra),
           'transferred inventory differs')
    C.need(set(C.LOCK['files'])<={p.name for p in folder.iterdir()},'transferred files missing')
    for n,h in C.LOCK['files'].items():C.file_hash(folder/n,h)
    with zipfile.ZipFile(folder/'stage2b-private-evidence.zip') as z:
        names=z.namelist();C.need(len(names)==len(set(names)) and set(names)==set(C.LOCK['zip_inventory']),'ZIP inventory')
        blobs={n:z.read(n) for n in names}  # Read every member; CRC checked by ZipFile.
    for n,b in blobs.items():
        C.need(C.digest(b)==C.LOCK['zip_inventory'][n],'ZIP member hash: '+n)
        if n.endswith('.json') and not n.endswith(('package-build.json','package-check.json')):C.read_json(b)
    j=lambda n:C.read_json(blobs[n])
    corrected=C.private_record((folder/'package-check.json').read_bytes())
    historical=C.old_record(blobs[C.REL+'package-check.json'])
    C.need(historical==corrected,'normalization changed parsed package record')
    C.need(blobs[C.REL+'package-check.json']==(folder/'package-check-original-prefixed.txt').read_bytes(),'historical prefix evidence differs')
    C.need(corrected['sha256']==C.LOCK['package_sha256'],'package identity')
    a=C.read_json((folder/'acceptance.json').read_bytes())
    C.need(a=={'status':'PASS','package_sha256':C.LOCK['package_sha256'],
        'lgpl_source_sha256':C.LOCK['lgpl_sha256'],'native_components':sorted(C.COMPONENTS),
        'publishable':False,'game_executed':False},'supplemental acceptance values')
    C.need(blobs['evidence/exit-status.txt'].strip()==b'2','original orchestration exit')
    C.need(not any(n.endswith(('acceptance.json','DELIVERABLES.sha256','images-after.txt')) for n in names),'unexpected pre-failure finalization')
    toolkit=blobs['evidence/TOOLKIT.json'];C.need(C.digest(toolkit)==C.LOCK['runner_bundle_sha256'],'native toolkit')
    root=Path(__file__).resolve().parents[4]
    C.need(blobs['evidence/EGL_LOCK.json']==(root/'tools/linux/baseline/egl/EGL_LOCK.json').read_bytes().replace(b'\r\n',b'\n'),'image lock differs')
    for n,commit,path in [('stage2b.py','5c0729b','tools/linux/baseline/stage2b/stage2b.py'),
                          ('build_inside.sh','5c0729b','tools/linux/baseline/stage2b/build_inside.sh'),
                          ('retry.py','abc5688','tools/linux/baseline/egl/retry.py')]:
        b=subprocess.check_output(['git','-C',str(root),'show',commit+':'+path])
        C.need(C.digest(b)==C.read_json(toolkit)['files'][n],'committed native tool differs: '+n)
    before=j('evidence/retry-inputs-before.json');after=j('evidence/sealed-inputs-after.json')
    C.need(before==after and after['immutable_project_and_lma'] is True,'source immutability')
    sealed=C.read_json((root/'private/work/linux_build/baseline_2a_final/KIT_MANIFEST.json').read_bytes())
    C.need(after['sdk_pins']==sealed['sdk_repositories'],'all 24 original SDK pins')
    back=j(C.REL+'backends.json');C.need(back['status']=='PASS' and all(v=='ON' for v in back['cmake'].values()) and len(back['compiled'])==6,'SDL backends')
    for n in ('results.json','results-game-lma.json','results-gamesync.json'):
        C.need(j(C.REL+n)['status']=='PASS','failed build: '+n)
    sdk=j(C.REL+'results.json');C.need(all(sdk['sdk'][k]==0 for k in ('configure_exit','build_exit','install_exit')),'SDK build exits')
    C.need(not any(sdk['configurations']['clang']['host_tests'].values()),'CPU tests')
    for n in ('original','plain','modified'):
        lg=j(C.REL+'lgpl-'+n+'.json');C.need(lg['verdict']=='PASS' and not lg['failed'],'LGPL '+n)
    abi=j(C.REL+'abi.json');C.need(abi['status']=='PASS' and len(abi['components'])==9,'ABI inventory')
    for n,row in abi['components'].items():
        mode,name=n.split('/') if '/' in n else ('',n)
        base=C.REL+('abi-'+mode if mode else 'abi')+'/'+name
        undefined='\n'.join(l for l in blobs[base+'.symbols.txt'].decode().splitlines() if '*UND*' in l)
        for prefix,ceiling in (('GLIBC',(2,39)),('GLIBCXX',(3,4,33))):
            vals=[tuple(map(int,v.split('.'))) for v in re.findall(r'\b'+prefix+r'_(\d+(?:\.\d+)+)',undefined)]
            value='.'.join(map(str,max(vals))) if vals else None
            C.need(row['requires'][prefix]==value and (not vals or max(vals)<=ceiling),'ABI imports '+n)
        C.need('GLIBC_PRIVATE' not in undefined and row['loader_exit']==0 and b'not found' not in blobs[base+'.loader.txt'],'loader '+n)
    log=blobs['evidence/build.log'].decode()
    for marker in ('R3HD_BASELINE_FEATURE PASS 42:42','R3HD_STAGE2B_BACKENDS PASS',
        'R3HD_EGL_SDK_RECONFIGURE_BUILD_INSTALL PASS','R3HD_STAGE2B_ABI PASS payload=5 replacements=4',
        'R3HD_STAGE2B_IMMUTABLE PASS','R3HD_STAGE2B STOP: Expecting value:'):
        C.need(marker in log,'missing log marker '+marker)
    C.need('R3HD_STAGE2B_BUILD_PACKAGE PASS' not in log,'original final marker unexpectedly present')
    build=C.old_record(blobs[C.REL+'package-build.json'])
    C.need(build['sha256']==corrected['sha256'] and build['requires']=={'glibc':'2.38','glibcxx':'3.4.32'},'build/package binding')
    container=j('evidence/container-final.json')[0]
    C.need(container['State']['ExitCode']==2 and not container['State']['Running'],'container state')
    C.need(container['Image'].removeprefix('sha256:')==blobs['evidence/image.id'].decode().strip().removeprefix('sha256:'),'image identity')
    C.need(container['HostConfig']['NetworkMode']=='none' and container['HostConfig']['ReadonlyRootfs'] is True and
           'no-new-privileges' in container['HostConfig']['SecurityOpt'],'container safety configuration')
    info=j('evidence/podman-info.json')
    C.need(info['host']['security']['rootless'] is True and info['host']['security']['seccompEnabled'] is True,'native engine security')
    # Re-evaluate the image transaction from the original and derived manifests.
    sys.path.insert(0,str(root/'tools/linux/baseline/egl'))
    import image_guard as G
    G.check(G.manifest(blobs['evidence/verified-2a-packages.tsv'].decode()),
            G.manifest(blobs[C.REL+'image-packages.tsv'].decode()),C.read_json(blobs['evidence/EGL_LOCK.json']))
    return {'status':'VERIFIED_BUILD_ABI_AND_SUPPLEMENTAL_STATIC_ACCEPTANCE',
        'original_orchestration_exit':2,'full_automated_stage2b':'FAILED_FINALIZATION',
        'original_zip_members':len(names),'supplements_separate':True,
        'payload_components':{n:abi['components'][n] for n in C.COMPONENTS},
        'finalization':'ORIGINAL ZIP: absent; authenticate later supplements separately',
        'runtime':'UNKNOWN; no r3hd entrypoint executed'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=review(a.folder);C.write(a.out,result);print(result['status'])
