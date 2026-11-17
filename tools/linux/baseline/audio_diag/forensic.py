"""Read-only authentication of the failed owned-data native startup."""
import json
from pathlib import Path
import sys
import zipfile
HERE=Path(__file__).resolve().parent
if not (HERE/'visible.py').exists():sys.path.insert(0,str(HERE.parent/'visible'))
import visible as V
C=V.C;N=V.N
LOCK=C.read_json((HERE/'DIAG_LOCK.json').read_bytes())


def review(path):
    C.file_hash(path,LOCK['zip_sha256']);side=Path(str(path)+'.sha256');C.file_hash(side,LOCK['sidecar_sha256'])
    C.need(side.read_text().strip()==LOCK['zip_sha256']+'  visible-private-evidence.zip','failed-startup sidecar')
    with zipfile.ZipFile(path) as z:
        C.need(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(LOCK['members']),'failed-startup inventory')
        data={n:z.read(n) for n in z.namelist()}
    for n,b in data.items():C.need(C.digest(b)==LOCK['members'][n],'failed-startup member: '+n)
    j=lambda n:C.read_json(data[n+'.json'])
    p=j('prepared');a=j('attempt');e=j('exit');proc=j('process')
    C.need(data['OWNER.txt'].strip()==b'R3HD_STAGE2C_VISIBLE_01','failed-startup owner')
    C.need(p['game_executed'] is False and p['unattended_authorized'] is False and p['package_sha256']==C.LOCK['package_sha256'] and p['source_sha256']==V.R.LOCK['raw_package_sha256'],'preparation provenance')
    C.need(len(p['data_inventory'])==917,'prepared data inventory count')
    content={n.removeprefix('content/'):h for n,h in p['data_inventory'].items() if n.startswith('content/')}
    C.need(len(content)==915 and C.digest(json.dumps(content,sort_keys=True,separators=(',',':')).encode())==LOCK['content_inventory_sha256'],'prepared content differs from tracked manifest')
    base='/home/<user>/Projects/R3HD-baseline-noble-2c-visible-01'
    expected=[base+'/installation/bin/r3hd','--video_driver=wayland','--fullscreen=false','--gpu_plugin=xenos',
       '--game_data_root='+base+'/installation/data/content','--user_data_root='+base+'/test-user',
       '--cache_root='+base+'/test-cache','--log_file='+base+'/runtime.log','--log_level=debug','--log_flush_interval=1']
    C.need(a=={'DISABLE_LSFG':'1','argv':expected,'human_authorization':'AUTHORIZE VISIBLE AUDIO INPUT STARTUP',
        'package_sha256':C.LOCK['package_sha256'],'timeout_seconds':120,'unattended':False},'failed-startup argv/authorization')
    C.need(proc=={'owned_process_group':5159,'pid':5159,'timeout_seconds':120},'process identity')
    C.need(e=={'exit':-5,'timed_out_or_interrupted_or_remaining_group':False},'not recorded SIGTRAP termination')
    for phase in ('before','after'):
        C.need(j('content-'+phase)=={'result':'supported','kind':'tree','release':'x360-xbla-5841123F-v1','files':915,
            'missing':[],'extra':[],'wrong_size':[],'wrong_hash':[]},'content verification')
        C.need(data['content-'+phase+'.stderr.txt'].decode().strip()=='R3HD_INTAKE OK verify release=x360-xbla-5841123F-v1','content stderr')
    text=data['process.log'].decode()+'\n'+data['runtime.log'].decode()
    C.need(j('result')==V.judge(-5,False,text,'no'),'failure classification changed')
    for n in C.COMPONENTS:
        loader=data[n+'.loader.txt'].decode();C.need('not found' not in loader and '/usr/lib/' in loader,'host closure')
    timeline=data['runtime.log'].decode()
    markers=['M2 host_start',"GPU plugin 'xenos' loaded",'VulkanPresenter: Created',
        'M2 xex_loaded entry=820E13F8','M2 runtime_initialized','M2 launch_prepared','XELOG_GPU PRESENT:',
        'SDL_OpenAudioDeviceStream() failed: ALSA:', '(service trap) R6025','import=__imp__KeBugCheck']
    positions=[timeline.index(m) for m in markers];C.need(positions==sorted(positions),'timeline order')
    C.need(timeline.count('XELOG_GPU PRESENT:')==5 and timeline.count('SDL_OpenAudioDeviceStream() failed:')==2 and timeline.count('import=__imp__KeBugCheck')==2,'event counts')
    C.need('VK_LAYER_LS_frame_generation' not in timeline and 'VK_ERROR_DEVICE_LOST' not in timeline,'unexpected graphics failure/layer')
    return {'status':'AUTHENTICATED FAILURE','exit':-5,'signal':'SIGTRAP','wrapper_termination':False,
        'xex_runtime_guest':'VERIFIED','gpu_present_path_records':5,'audio_device_open_failures':2,
        'guest_R6025_and_bugcheck':'VERIFIED','recognizable_content':'NOT OBSERVED',
        'leading_trigger':'audio endpoint unavailable under isolated environment; causal confirmation pending',
        'normal_startup':'FAIL','other_linux_or_Deck':'UNKNOWN'}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('zip',type=Path)
    print(json.dumps(review(p.parse_args().zip),indent=2))
