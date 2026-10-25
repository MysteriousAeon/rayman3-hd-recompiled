"""Metadata only: hidden run/focus, license, content paths and bounded PCM statistics."""
import argparse, hashlib, json, math, re, struct
from pathlib import Path
ap=argparse.ArgumentParser(); ap.add_argument('run',type=Path); ap.add_argument('output',type=Path)
a=ap.parse_args()
parts=sorted(a.run.glob('runtime.*.log'),key=lambda p:-int(p.name.split('.')[1]))+[a.run/'runtime.log']
lines=[l for p in parts if p.exists() for l in p.read_text(errors='replace').splitlines()]
def events(token):
    return [dict(timestamp=l[1:24],**dict(re.findall(r'(\w+)=(\S+)',l.split(token,1)[1]))) for l in lines if token in l]
result=dict(run=json.loads((a.run/'run.json').read_text(encoding='utf-8-sig')),license=events('M6 license '),window=events('M6 window '),exit=events('M6 bounded_exit '),focus_requests=events('M6 focus_request '),levels=sorted({m[1] for l in lines if (m:=re.search(r'path=.*?([A-Za-z_0-9]+)\.lvl result=00000000',l))}),content_imports=[l for l in lines if 'M2 import=__imp__XamContent' in l],profile_files=[dict(path=str(p.relative_to(a.run/'user')),size=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (a.run/'user').rglob('*') if p.is_file()])
# Preserve the detailed monitor record privately; durable metadata keeps intervals
# and event counts rather than thousands of duplicate samples.
result['run_record_sha256']=hashlib.sha256((a.run/'run.json').read_bytes()).hexdigest()
result['run']['foreground_event_count']=len(result['run'].pop('foreground_events', []))
result['run'].pop('foreground_samples', None)
result['content_events']=events('M6 content ')
result['capture_requests']=events('M6 frame_capture ')
result['private_bmp_count']=len(list(a.run.glob('m3_frame_*.bmp')))
result['menu_resource_dump_count']=len(list(a.run.glob('m5_*.bin')))
result['shader_microcode_dump_count']=len(list(a.run.glob('m3_shader_*.bin')))
result['shader_backend_dump_count']=sum(p.is_file() for p in (a.run/'shaders').rglob('*'))
p=a.run/'audio.f32'
if p.exists():
    raw=p.read_bytes(); values=[x[0] for x in struct.iter_unpack('<f',raw)]
    channel_events=events('M4 audio_output '); channels=int(channel_events[-1]['channels']) if channel_events else 0
    finite=[x for x in values if math.isfinite(x)]
    silent_blocks=0; max_silent=0
    if channels:
        for i in range(0,len(values),512*channels):
            silent_blocks=silent_blocks+1 if all(x==0 for x in values[i:i+512*channels]) else 0
            max_silent=max(max_silent,silent_blocks)
    result['audio']=dict(format='float32 LE interleaved',rate=48000,channels=channels,size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),samples=len(values),seconds=len(values)/channels/48000 if channels else None,nonzero=sum(x!=0 for x in finite),nonfinite=len(values)-len(finite),peak=max(map(abs,finite),default=0),rms=math.sqrt(sum(x*x for x in finite)/max(1,len(finite))),at_or_over_one=sum(abs(x)>=1 for x in finite),max_silent_block_seconds=max_silent*512/48000,channel_rms=[math.sqrt(sum(x*x for x in values[c::channels])/max(1,len(values[c::channels]))) for c in range(channels)])
a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2)+'\n')
# Reused M4 summaries embed the runner's raw monitor. Keep the same compact
# representation when all three summary commands target one report directory.
for name in ('compatibility.json', 'runtime.json'):
    companion=a.output.parent/name
    if companion.exists():
        data=json.loads(companion.read_text())
        if isinstance(data.get('run'),dict): data['run']=result['run']
        companion.write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('run','license','levels')},indent=2))
