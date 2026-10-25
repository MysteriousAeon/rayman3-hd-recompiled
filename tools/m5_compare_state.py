"""Compare metadata-only transform samples from identical new-game sequences.
usage: m5_compare_state.py IDLE_RUN INPUT_RUN OUTPUT_JSON
All offsets are discovery-derived; report labels distinguish observation/type inference.
"""
import bisect, datetime, json, math, re, sys
from pathlib import Path
idle, active, output = map(Path,sys.argv[1:4])
def load(run):
    # Align normal level-open events, retaining actual wall-clock timing rather
    # than assuming fixed process startup speed.
    logs = sorted(run.glob('runtime.*.log'),key=lambda p:-int(p.name.split('.')[1]))+[run/'runtime.log']
    lines = [l for p in logs for l in p.read_text(errors='replace').splitlines()]
    line = next(l for l in lines if 'M2 vfs_open' in l and re.search(r'intro_10\\intro_10.lvl.*result=00000000',l,re.I))
    opened = datetime.datetime.fromisoformat(line[1:24]).replace(tzinfo=datetime.timezone(datetime.timedelta(hours=3))).timestamp()
    state = json.loads((run/'state.json').read_text())
    samples=[]
    for sample in state['samples']:
        actors={tuple(a['object_types']):a for a in sample['actors']}
        if all(k in actors for k in ((0,0,0),(1,1,1),(7,9,9))):
            p=actors[(0,0,0)]['position']; c=actors[(1,1,1)]['position']
            samples.append(dict(murfy=actors[(7,9,9)]['position'], t=sample['time_ns']/1e9-opened, rayman=p,camera=c,
                                relative=[x-y for x,y in zip(p,c)]))
    return samples, opened
a, at = load(idle); b, bt = load(active)
ta=[s['t'] for s in a]
pairs=[]
for r in b:
    if not 10 <= r['t'] <= 70: continue
    index=bisect.bisect_left(ta,r['t']); index=min(index,len(a)-1)
    if index and abs(ta[index-1]-r['t'])<abs(ta[index]-r['t']): index-=1
    q=a[index]
    pairs.append(dict(seconds_after_level_open=round(r['t'],4), alignment_error_seconds=abs(q['t']-r['t']),
                      input_position=r['rayman'], idle_position=q['rayman'],
                      position_distance=math.dist(r['rayman'],q['rayman']),
                      camera_distance=math.dist(r['camera'],q['camera']),
                      relative_distance=math.dist(r['relative'],q['relative'])))
# Match path position as a second comparison, since scripted flight timing drifts.
# Restrict to +/-2 seconds to avoid matching another circuit of the flight.
path_pairs=[]
for r in b:
    if not 10 <= r['t'] <= 70: continue
    candidates=[q for q in a if abs(q['t']-r['t'])<2]
    if not candidates: continue
    q=min(candidates,key=lambda q:math.dist(q['camera'],r['camera']))
    path_pairs.append(dict(seconds_after_level_open=r['t'],
        camera_distance=math.dist(q['camera'],r['camera']),
        rayman_distance=math.dist(q['rayman'],r['rayman']),
        murfy_distance=math.dist(q['murfy'],r['murfy']),
        murfy_relative_distance=math.dist([x-y for x,y in zip(q['murfy'],q['camera'])],
                                        [x-y for x,y in zip(r['murfy'],r['camera'])])))
def path_stats(lo,hi):
    selected=[p for p in path_pairs if lo <= p['seconds_after_level_open'] < hi]
    return dict(samples=len(selected), **{k:dict(min=min(p[k] for p in selected),max=max(p[k] for p in selected),mean=sum(p[k] for p in selected)/len(selected))
        for k in ('camera_distance','rayman_distance','murfy_distance','murfy_relative_distance')}) if selected else None
def stats(lo,hi):
    selected=[p for p in pairs if lo <= p['seconds_after_level_open'] < hi]
    return dict(samples=len(selected), **{k:dict(min=min(p[k] for p in selected),max=max(p[k] for p in selected),mean=sum(p[k] for p in selected)/len(selected))
                                         for k in ('position_distance','camera_distance','relative_distance','alignment_error_seconds')}) if selected else None
result=dict(idle=idle.name, input=active.name, alignment='first successful intro_10.lvl open',
            layout='Reciprocal SO/Perso/StdGame chain locally checked; matrix/name interpretation compared to local runtime and pinned R3 reader',
            before_input=stats(12,18), right_held=stats(22,29), right_released=stats(31,38), left_held=stats(42,49),
            path_matched=dict(before_input=path_stats(12,18),right_held=path_stats(22,29),right_released=path_stats(31,38),left_held=path_stats(42,49)), samples=pairs)
output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='samples'},indent=2))
