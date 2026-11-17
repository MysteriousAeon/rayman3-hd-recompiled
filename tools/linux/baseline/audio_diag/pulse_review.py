"""Read-only historical Pulse diagnostic audit. Never launches or regrades a run."""
import argparse
import json
from pathlib import Path
import subprocess
import zipfile
import audio_diag as A

C=A.C
HERE=Path(__file__).resolve().parent
LOCK=C.read_json((HERE/'PULSE_RESULT_LOCK.json').read_bytes())
ROOT=HERE.parents[3]


def authenticated(path):
    C.file_hash(path,LOCK['zip_sha256'])
    C.need(path.stat().st_size==LOCK['zip_size'],'Pulse archive size')
    side=Path(str(path)+'.sha256');C.file_hash(side,LOCK['sidecar_sha256'])
    C.need(side.read_text().strip()==LOCK['zip_sha256']+'  pulse-private-evidence.zip','Pulse sidecar')
    with zipfile.ZipFile(path) as z:
        C.need(len(z.namelist())==len(set(z.namelist())) and set(z.namelist())==set(LOCK['members']),'Pulse member inventory')
        data={n:z.read(n) for n in z.namelist()}  # read checks every member CRC
    for n,b in data.items():C.need(C.digest(b)==LOCK['members'][n],'Pulse member: '+n)
    return data


def sources():
    blobs={}
    for name,row in LOCK['sources'].items():
        sdk=name.startswith('SDK/')
        repo=ROOT/'external/rexglue-sdk' if sdk else ROOT
        b=subprocess.check_output(['git','-C',str(repo),'show',row['commit']+':'+name.removeprefix('SDK/')])
        C.need(C.digest(b)==row['sha256'],'source identity: '+name);blobs[name]=b.decode()
    patch=blobs['tools/m11_runtime_patch.py']
    C.need("patch_once('src/ui/d3d12/d3d12_presenter.cpp'" in patch and 'm11pace::HostPresent();' in patch,'D3D hook')
    C.need('m11pace' not in blobs['SDK/src/ui/vulkan/vulkan_presenter.cpp'],'unexpected Vulkan M11 instrumentation')
    C.need('std::_Exit(0);' in blobs['SDK/src/ui/rex_app.cpp'],'close-path source')
    replay=json.loads(blobs['tools/linux/baseline/stage2b/SDK_REPLAY.json'])
    hooks=[]
    for step in replay['patch_steps']:
        b=subprocess.check_output(['git','-C',str(ROOT),'show',replay['source_commit']+':tools/'+step])
        if b'm11pace::HostPresent()' in b:hooks.append(step)
    C.need(hooks==['m11_runtime_patch.py','m24_runtime_patch.py'],'unexpected host-present replay hook')
    return blobs


def review(path,previous):
    A.F.review(previous)  # independently authenticate the original SIGTRAP attempt
    data=authenticated(path);sources()
    j=lambda n:C.read_json(data[n+'.json'])
    with zipfile.ZipFile(previous) as z:old={n:z.read(n) for n in z.namelist()}
    C.need(j('prepared')==C.read_json(old['prepared.json']),'original package/source/all917 data identities differ')
    C.need(data['OWNER.txt']==old['OWNER.txt'],'owner')
    expected=C.read_json(old['attempt.json'])
    expected['argv']=[s.replace('2c-visible-01','2c-pulse-01') for s in expected['argv']]
    C.need(j('attempt')==expected,'launch policy/configuration differs beyond workspace')
    C.need(j('diagnostic')=={'content_source':'/home/<user>/Projects/R3HD-baseline-noble-2c-visible-01/installation/data',
        'copy':'cp --reflink=always; no fallback','game_executed':False,'kind':'PULSE_ROUTE_01',
        'prior_evidence_sha256':A.F.LOCK['zip_sha256']},'diagnostic provenance')
    C.need(j('process')=={'owned_process_group':5180,'pid':5180,'timeout_seconds':120},'process identity')
    C.need(j('exit')=={'exit':0,'timed_out_or_interrupted_or_remaining_group':False},'exit/termination')
    pre=j('audio-preflight');route=j('audio-route')
    C.need(pre=={'device_stream':'NOT TESTED','libpulse_version':'17.0.0','metadata_only':True,'socket':'/run/user/1000/pulse/native'},'audio preflight')
    config=b'autospawn = no\nauto-connect-localhost = no\nauto-connect-display = no\n'
    C.need(route==dict(pre,PULSE_SERVER='unix:/run/user/1000/pulse/native',SDL_AUDIO_DRIVER='pulseaudio',
        autospawn=False,client_config_sha256=C.digest(config),
        private_runtime='/home/<user>/Projects/R3HD-baseline-noble-2c-pulse-01/launch-environment/os-home/run'),'audio route')
    for phase in ('clone','before','after'):
        C.need(data['content-'+phase+'.json']==old['content-before.json'] and
               data['content-'+phase+'.stderr.txt']==old['content-before.stderr.txt'],'content receipt: '+phase)
    for component in C.COMPONENTS:
        # Addresses vary; verify complete authenticated loader records, no missing objects.
        t=data[component+'.loader.txt'].decode();C.need('not found' not in t and '/usr/lib/' in t,'loader closure')
    runtime=data['runtime.log'].decode();text=data['process.log'].decode()+'\n'+runtime
    base=A.BASE_JUDGE(0,False,text,'yes')
    result=dict(base,experiment='PULSE_ROUTE_01; causal diagnostic only',audio_endpoint_opened=True,
        prior_guest_fatal_recurred=False,audio_correctness='UNKNOWN; stream open is not subjective audio acceptance')
    C.need(j('result')==result,'historical acceptance result not reproduced')
    missing=[m for m,passed in base['milestones'].items() if not passed]
    C.need(missing==['M11 pacing series=host_present'],'unexpected missing milestone')
    # Check other independent acceptance failures; do not insert a synthetic marker.
    benign=A.V.re.compile(r'^\[[^\]\r\n]+\] \[error\] \[fs\] \[t[0-9]+\] ResolvePath\(\\D:\\Gamedata\) failed - device not found$')
    errors=[s for s in text.splitlines() if ('[error]' in s.lower() or '[critical]' in s.lower()) and not benign.fullmatch(s)]
    C.need(not errors,'unexpected error/critical record')
    for token in ('R6025','import=__imp__KeBugCheck','SDL_OpenAudioDeviceStream() failed:',
                  'VK_ERROR_DEVICE_LOST','VK_LAYER_LS_frame_generation','M6 window hidden=true'):
        C.need(token not in text,'unexpected fatal/failure: '+token)
    C.need(runtime.count('audio endpoint ')==2 and runtime.count('XELOG_GPU PRESENT:')==858,'audio/GPU event counts')
    markers=['M2 host_start',"GPU plugin 'xenos' loaded",'VulkanPresenter: Created',
        'M2 xex_loaded entry=820E13F8','M2 runtime_initialized','M2 launch_prepared','XELOG_GPU PRESENT:',
        'audio endpoint ', 'Window closing, shutting down...','KernelState::TerminateTitle','Title terminated; hard-exiting process.']
    positions=[runtime.index(m) for m in markers];C.need(positions==sorted(positions),'startup/close order')
    C.need(base['status']=='FAIL' and base['natural_exit_zero'] and base['human_saw_game_content']=='yes','historical verdict')
    return {'authentication':'PASS; all22 members; original failure independently authenticated',
        'historical_wrapper_verdict':'FAIL; unchanged','sole_failed_acceptance_criterion':missing[0],
        'child_exit':0,'wrapper_timeout_interrupt_or_group_cleanup':False,
        'close_path':'window close -> TerminateTitle -> SDK _Exit(0); not full destructor teardown',
        'audio_endpoint_opens':2,'gpu_present_path_records':858,'R6025_or_KeBugCheck_recurrence':False,
        'recognizable_content_receipt':'yes; exact logo/menu identity supplied separately by human',
        'pacing_acceptance':'NOT MEASURED; required M11 hook is D3D12-only',
        'audio_trigger_hypothesis':'SUPPORTED; not a controlled causal proof',
        'gameplay_audio_input_save_Deck':'UNKNOWN'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('zip',type=Path);p.add_argument('--previous',type=Path,required=True)
    args=p.parse_args();print(json.dumps(review(args.zip,args.previous),indent=2))
