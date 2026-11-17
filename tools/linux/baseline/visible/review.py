"""Authenticate the returned attended negative tests. No extraction or execution."""
from pathlib import Path
import sys
import zipfile
HERE=Path(__file__).resolve().parent
if not (HERE/'startup.py').exists():sys.path.insert(0,str(HERE.parent/'startup'))
import startup as N
C=N.C
LOCK=C.read_json((HERE/'VISIBLE_LOCK.json').read_bytes())


def review(path):
    C.file_hash(path,LOCK['zip_sha256'])
    side=Path(str(path)+'.sha256');C.file_hash(side,LOCK['sidecar_sha256'])
    C.need(side.read_text().strip()==LOCK['zip_sha256']+'  startup-private-evidence.zip','startup sidecar contents')
    with zipfile.ZipFile(path) as z:
        C.need(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(LOCK['members']),'startup inventory')
        data={n:z.read(n) for n in z.namelist()}
    for n,b in data.items():C.need(C.digest(b)==LOCK['members'][n],'startup member: '+n)
    C.need(data['OWNER.txt'].strip()==b'R3HD_STAGE2C_HUMAN_STARTUP_01','startup owner')
    plan=C.read_json(data['prepared.json'])
    C.need(plan['unattended_authorized'] is False and plan['package_sha256']==C.LOCK['package_sha256'],'prepared assertions')
    hashes=C.read_json((HERE/'ABI_HASHES.json' if (HERE/'ABI_HASHES.json').exists() else HERE.parent/'startup/ABI_HASHES.json').read_bytes())
    C.need(plan['modes']['reject']['files']==plan['modes']['wayland']['files'],'prepared program inventories differ')
    C.need(len(plan['modes']['reject']['files'])==57,'prepared file count')
    for n,h in hashes.items():C.need(plan['modes']['reject']['files']['bin/'+n]==h,'prepared binary identity')
    for mode,seconds in (('reject',15),('wayland',45)):
        j=lambda n:C.read_json(data[mode+'/'+n+'.json'])
        a=j('attempt');p=j('process');e=j('exit');r=j('result')
        base='/home/<user>/Projects/R3HD-baseline-noble-2c-startup-01/'+mode
        expected=[base+'/installation/bin/r3hd','--video_driver='+(N.TOKEN if mode=='reject' else 'wayland'),
          '--fullscreen=false','--gpu_plugin=xenos','--game_data_root='+base+'/absent-game-data',
          '--user_data_root='+base+'/user-data','--cache_root='+base+'/cache',
          '--log_file='+base+'/runtime.log','--log_level=debug','--log_flush_interval=1']
        C.need(a['argv']==expected and a['human_authorization']=='AUTHORIZE ATTENDED '+mode.upper() and a['unattended'] is False and a['package_sha256']==C.LOCK['package_sha256'],'attended command')
        C.need(type(p['pid']) is int and p['pid']>1 and p['pid']==p['owned_process_group'] and p['timeout_seconds']==seconds,'owned process')
        C.need(e=={'exit':1,'timed_out_or_interrupted':False},'not natural negative exit')
        text='\n'.join(data[n].decode() for n in (mode+'/process.log',mode+'/runtime.log') if n in data)
        C.need(r=={'status':'PASS','mode':mode,'milestones':N.judge(mode,1,False,text),
            'expected_failure_probe':True,'normal_startup_pass':False,'gameplay':'UNKNOWN','guest_executed':False},'receipt classification')
        for n in C.COMPONENTS:
            loader=data[mode+'/'+n+'.loader.txt'].decode()
            C.need('not found' not in loader and '/usr/lib/' in loader,'host closure')
        if mode=='wayland':
            text=data['wayland/runtime.log'].decode()
            markers=['M2 host_start',"GPU plugin 'xenos' loaded",'Vulkan instance API version',
                "Vulkan device 'NVIDIA GeForce RTX 4070 SUPER'",'M15 window fullscreen_requested=false',
                'VulkanPresenter: Created 1280x720 swapchain','--game_data_root does not exist: '+base+'/absent-game-data']
            positions=[text.index(x) for x in markers]
            C.need(positions==sorted(positions),'startup milestone order')
            C.need('VK_LAYER_LS_frame_generation' in text and 'Disable Env Var:  DISABLE_LSFG' in text,'implicit layer evidence')
    return {'status':'PASS','zip_sha256':LOCK['zip_sha256'],'negative_tests':'both VERIFIED expected natural exit1',
        'application_entry':'VERIFIED','wayland_vulkan_device_swapchain':'VERIFIED',
        'visible_frame':'NOT OBSERVED by maintainer; not proved by swapchain',
        'runtime_guest':'NOT REACHED','normal_startup':'UNKNOWN','gameplay':'UNKNOWN',
        'process_cleanup':'wrapper reports no remaining owned group; no system-wide census',
        'host_layer':'LSFG implicit layer observed; next test disables only this layer per process'}


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('zip',type=Path)
    print(json.dumps(review(p.parse_args().zip),indent=2))
