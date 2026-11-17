"""Focused native swirl pickup/expiry check via the approved hidden runner.

No guest writes or global input. Optional captures are capped at two. All game
metadata and test profiles remain private. Not played progression or human proof.
"""
from pathlib import Path
import argparse
import ctypes
import json
import math
import re
import struct
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import m19_campaign_check as m19
import r3hd_settings as settings
from m5_live import _k
_k.CloseHandle.argtypes=[ctypes.c_void_p]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('run');ap.add_argument('--level',default='menu_20')
    ap.add_argument('--power',type=int,default=3,choices=range(5))
    ap.add_argument('--preset',default='hdplus',choices=['vanilla','hdplus','custom'])
    ap.add_argument('--base',default='hdplus');ap.add_argument('--value',choices=['original','restored'])
    ap.add_argument('--expiry',action='store_true');ap.add_argument('--captures',action='store_true')
    ap.add_argument('--mod-plan',type=Path)
    a=ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',a.run):ap.error('invalid bounded run name')
    reg=settings.load_registry()
    doc=settings.make_settings(reg,'custom',a.base,[f'power_swirl={a.value}'] if a.value else []) if a.preset=='custom' else None
    resolved=settings.resolve(reg,None if doc else a.preset,doc)
    mode=resolved['values']['power_swirl']
    work=ROOT/'private/work/power_swirl/integration';work.mkdir(parents=True,exist_ok=True)
    plan=work/(a.run+'.steps');plan.write_text('wait 45\n',encoding='ascii')
    env={'R3HD_POWER_SWIRL':mode,'R3HD_SWIRL_TRACE':'1','R3HD_M22_DRAW_TRACE':'1' if a.captures else '0',
         'R3HD_MODS_PLAN':str(a.mod_plan.resolve()) if a.mod_plan else ''}
    all_rows=[]
    def beside(run,game,log):
        if not m19.wait_for_log(run,f'{a.level}\\{a.level}.lvl result=00000000',game,90):return ['level did not open']
        (run/'swirl_settings.json').write_text(json.dumps(resolved,indent=2),encoding='utf-8')
        time.sleep(6);pid,base=m19.attach(run);actors=run/'actors.json'
        subprocess.run([sys.executable,str(ROOT/'tools/m5_memory_probe.py'),str(pid),base,str(actors),'--regions'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        p=m19.Process(pid,int(base,16));players=m19.live_actors(p,actors,'YLT_RaymanModel');cans=m19.live_actors(p,actors,m19.CAN)
        if len(players)!=1:_k.CloseHandle(p.handle);return ['player identity unavailable']
        player=players[0];inventory=[];eligible=[]
        for can in cans:
            buf,off=can.dsg()[0];code=struct.unpack_from('>I',buf,off)[0]
            inventory.append(dict(so=f'{can.so:08X}',code=code,comport=can.comport(),position=can.position(),distance=math.dist(can.position(),player.position())))
            if code==a.power and 'Wait' in can.comport():eligible.append(can)
        (run/'swirl_cans.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
        if not eligible:_k.CloseHandle(p.handle);return ['requested power has no offered can']
        target=min(eligible,key=lambda c:math.dist(c.position(),player.position()))
        subset=json.loads(actors.read_text());subset['actors']=[r for r in subset['actors'] if int(r['so'],16) in [target.so,player.so]]
        chosen=run/'chosen_actors.json';chosen.write_text(json.dumps(subset),encoding='utf-8')
        start=time.monotonic();errors=[];captures=0;budget=0
        def read(addr,n):
            nonlocal budget
            budget+=n
            if budget>32*1024*1024:raise ValueError('bounded read budget exhausted')
            b=p.read(addr,n)
            if b is None:raise ValueError('native read unavailable')
            return b
        def sample():
            nonlocal captures
            try:
                seen_power=False
                with (run/'swirl_events.jsonl').open('x',encoding='utf-8') as f:
                    for _ in range(360 if a.expiry else 80):
                        count=struct.unpack('>I',read(0x8288B3DC,4))[0]
                        if count>800:raise ValueError('particle count exceeds native limit')
                        pool=read(0x82C21D80,count*132) if count else b'';targets=[]
                        for i in range(count):
                            b=pool[i*132:(i+1)*132];kind=struct.unpack_from('>I',b)[0]
                            if kind&255==20:targets.append(dict(type=kind,material=hex(struct.unpack_from('>I',b,108)[0]),alpha=struct.unpack_from('>f',b,112)[0],radius=struct.unpack_from('>f',b,80)[0]))
                        buf,off=player.dsg()[2];power=struct.unpack_from('>I',buf,off)[0];seen_power|=power==a.power
                        row=dict(seconds=round(time.monotonic()-start,4),power=power,targets=targets,position=player.position())
                        if a.captures and targets and ((captures==0 and row['seconds']>=.85) or (captures==1 and seen_power and power==5 and row['seconds']>3)):
                            captures+=1;(run/'frame.request').write_text(str(captures)+'\n',encoding='ascii')
                        f.write(json.dumps(row)+'\n');all_rows.append(row);time.sleep(.05)
            except Exception as exc:errors.append(str(exc))
        thread=threading.Thread(target=sample);thread.start();time.sleep(.2)
        walk=subprocess.run([sys.executable,str(ROOT/'tools/m19_walk_to.py'),str(run),str(chosen),m19.CAN,'--seconds','8','--stop','1.0','--log',str(run/'walk.json')],stdout=log,stderr=subprocess.STDOUT,timeout=20)
        if walk.returncode:errors.append('walk did not reach target')
        if a.expiry:
            try:
                with (run/'schedule.txt').open('a',encoding='ascii') as f:f.write('0 300 0\n0 301 -32767\n')
                time.sleep(.8)
            finally:
                with (run/'schedule.txt').open('a',encoding='ascii') as f:f.write('0 300 0\n0 301 0\n')
        thread.join(timeout=24);_k.CloseHandle(p.handle)
        if thread.is_alive():errors.append('sampler did not complete')
        transitions=[]
        for r in all_rows:
            if not transitions or transitions[-1][1]!=r['power']:transitions.append([r['seconds'],r['power']])
        wanted=[5,a.power,5] if a.expiry else [5,a.power]
        if [v for _,v in transitions]!=wanted:errors.append('requested transition coverage missing')
        (run/'swirl_summary.json').write_text(json.dumps(dict(mode=mode,transitions=transitions,capture_requests=captures,bytes_read=budget,errors=errors),indent=2),encoding='utf-8')
        return errors
    reasons=m19.hidden_run(a.run,plan,50,test_level=a.level,env=env,beside=beside)
    print('SWIRL_HIDDEN_CHECK',json.dumps(dict(run=a.run,mode=mode,reasons=reasons)))
    return bool(reasons)
if __name__=='__main__':raise SystemExit(main())
