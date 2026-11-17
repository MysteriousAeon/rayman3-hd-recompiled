"""Read focused swirl evidence. Raw draws/assets remain private; no game launch."""
import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import m22_draw_report as draw

def load_run(name):
    root=ROOT/'private/work/m6_runs'/name
    log='\n'.join(p.read_text(encoding='utf-8',errors='replace') for p in sorted(root.glob('runtime*.log')))
    events=[json.loads(x) for x in (root/'swirl_events.jsonl').read_text().splitlines()]
    traces=[]
    for p in sorted(root.glob('m22_draws_*.bin')):traces.append(draw.parse(p)[0])
    return root,log,events,traces

def restored_draws(ds,bases):
    ids=[]
    for d in ds:
        if d['index_count']!=6 or not d['bindings'] or d['bindings'][0]['stride']!=24:continue
        if not d['textures'] or d['textures'][0]['base'] not in bases:continue
        n,attrs=draw.vertices(d);off=d['regs'][0x102];ix=sorted({i+off for i in draw.indices(d)})
        pos=next((v for a,v in attrs if a['format']==57),None);uv=next((v for a,v in attrs if a['format']==37),None)
        if len(ix)==4 and pos and uv and max(ix)<n and [pos[i] for i in ix]==[(1.,-1.,0.),(-1.,-1.,0.),(-1.,1.,0.),(1.,1.,0.)] and [uv[i] for i in ix]==[(1.,0.),(0.,0.),(0.,1.),(1.,1.)]:ids.append(d['draw'])
    return ids

def matched_following_states(on, off, own):
    """Compare identical native geometry after the added draws despite scene timing.

    Exact used vertex bytes/indices and texture content identify each draw; shader
    and pipeline state are deliberately excluded from its identity, then checked.
    Camera/animation floats and transient vertex-buffer addresses are reported
    separately, never equated across asynchronous captures.
    """
    def key(d):
        if not d['bindings']: return None
        b=d['bindings'][0];stride=b['stride'];off=d['regs'][0x102]
        ix=[i+off for i in draw.indices(d)]
        if not ix or max(ix)*stride>=len(b['data']): return None
        used=b''.join(b['data'][i*stride:(i+1)*stride] for i in ix)
        return d['primitive'],d['index_count'],hashlib.sha256(used).digest(),tuple(t['head'] for t in d['textures'])
    controls=collections.defaultdict(list)
    for d in off: controls[key(d)].append(d)
    rows=[]
    fields=['vs','ps','surface_info','color_info','depth_control','blend0','color_control','clip_cntl','su_sc_mode','vte_cntl','mode_control','color_mask','viewport']
    for x in on:
        if x['draw'] in own or x['draw']<min(own): continue
        k=key(x)
        if k is None or len(controls[k])!=1: continue
        y=controls[k][0];sx=draw.state_row(x,{});sy=draw.state_row(y,{})
        differences=[f for f in fields if sx[f]!=sy[f]]
        textures_equal=all(x['consts'][0x800+6*t['fetch']:0x806+6*t['fetch']]==y['consts'][0x800+6*t['fetch']:0x806+6*t['fetch']] for t in x['textures'])
        rows.append(dict(on=x['draw'],off=y['draw'],pipeline_differences=differences,sampled_fetch_equal=textures_equal,
            float_word_differences=sum(u!=v for u,v in zip(x['consts'][:2048],y['consts'][:2048]))))
    assert rows,'no identical following native geometry to compare'
    assert all(not r['pipeline_differences'] and r['sampled_fetch_equal'] for r in rows),'following native pipeline/resource isolation mismatch'
    return rows

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--on',required=True);ap.add_argument('--off')
    ap.add_argument('--expected-hash',required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();root,log,ev,frames=load_run(a.on)
    records=re.findall(r'texture=(\S+) resource=([0-9A-F]+) physical=([0-9A-F]+) fetch=([0-9A-F]+) hash=([0-9A-F]+)',log)
    assert records,'no resource evidence'
    assert all(p==f and h.upper()==a.expected_hash.upper() for _,_,p,f,h in records),'texture ownership/hash mismatch'
    assert 'constant restoration failed' not in log and 'SWIRL rejected' not in log
    bases={int(p,16) for _,_,p,_,_ in records};results=[]
    other=load_run(a.off) if a.off else None
    fields=['prim','indices','vs','ps','surface_info','color_info','depth_control','blend0','color_control','clip_cntl','su_sc_mode','vte_cntl','mode_control','color_mask','textures']
    for i,ds in enumerate(frames):
        own=set(restored_draws(ds,bases));assert own,'no restored quads in captured transition'
        rows=[draw.state_row(d,{}) for d in ds if d['draw'] in own]
        assert all(x['blend0']=='01060106' and x['depth_control']=='00708732' and int(x['color_control'],16)&8==0 for x in rows),'blend/depth/alpha mismatch'
        result=dict(added_quads=len(own),blend=rows[0]['blend0'],depth=rows[0]['depth_control'])
        if other and i<len(other[3]):
            control=other[3][i];ar=[draw.state_row(d,{}) for d in ds if d['draw'] not in own];br=[draw.state_row(d,{}) for d in control]
            diffs=[dict(index=j,fields=[k for k in fields if x[k]!=y[k]]) for j,(x,y) in enumerate(zip(ar,br)) if any(x[k]!=y[k] for k in fields)]
            result.update(native_draws=len(ar),control_draws=len(br),state_differences=diffs)
            result['matched_following_states']=matched_following_states(ds,control,own)
            # Timing/camera can change native draw order. Preserve details instead
            # of treating every unmatched scene sample as state-equivalent.
            result['native_schedule_equal']=len(ar)==len(br) and not diffs
            # Compare all shader floats/constants, boolean/loop and texture fetch
            # state as evidence. Native animation/camera changes are not masked.
            if len(ar)==len(br) and not diffs:
                nd=[d for d in ds if d['draw'] not in own]
                result['constant_word_differences']=[sum(x!=y for x,y in zip(xd['consts'],yd['consts'])) for xd,yd in zip(nd,control)]
                result['constant_register_differences']=[sorted({j//4 for j,(x,y) in enumerate(zip(xd['consts'],yd['consts'])) if x!=y}) for xd,yd in zip(nd,control)]
                result['register_differences']=[['%04X'%(0x2000+j) for j,(x,y) in enumerate(zip(xd['regs'],yd['regs'])) if x!=y] for xd,yd in zip(nd,control)]
                result['sampled_texture_fetch_equal']=[all(xd['consts'][0x800+6*t['fetch']:0x806+6*t['fetch']]==yd['consts'][0x800+6*t['fetch']:0x806+6*t['fetch']] for t in xd['textures']) for xd,yd in zip(nd,control)]
        results.append(result)
    groups=[]
    for e in ev:
        if e['targets']:
            if not groups or e['seconds']-groups[-1][-1]['seconds']>.3:groups.append([])
            groups[-1].append(e)
    lifetimes=[dict(start=g[0]['seconds'],end=g[-1]['seconds'],alpha_first=max(t['alpha'] for t in g[0]['targets']),alpha_last=max(t['alpha'] for t in g[-1]['targets']),material=sorted({t['material'] for e in g for t in e['targets']})) for g in groups]
    assert all(.3<x['end']-x['start']<2 and x['alpha_last']<x['alpha_first'] for x in lifetimes),'unexpected native lifetime/fade'
    out=dict(run=a.on,resource_names=sorted({x[0] for x in records}),resource_hash=a.expected_hash,frames=results,lifetimes=lifetimes,
             transition_summary=json.loads((root/'swirl_summary.json').read_text()))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2),encoding='utf-8')
    print('SWIRL_JUDGE PASS',a.on,'frames',len(results),'bursts',len(lifetimes))
if __name__=='__main__':main()
