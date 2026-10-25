"""Metadata-only M5 traces. Captures and shader dump contents stay private.

usage: python tools/m5_summarize.py private/work/m5_runs/NAME reports/milestone5/NAME
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

run, output = map(Path, sys.argv[1:3])
output.mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, 'tools/m3_summarize.py', str(run),
                'reports/milestone3/data/eh_map.json', str(output/'runtime.json')], check=True, stdout=subprocess.DEVNULL)
subprocess.run([sys.executable, 'tools/m4_summarize.py', str(run), str(output/'compatibility.json')],
               check=True, stdout=subprocess.DEVNULL)
parts = sorted(run.glob('runtime.*.log'), key=lambda p: -int(p.name.split('.')[1])) + [run/'runtime.log']
lines = [line for p in parts for line in p.read_text(errors='replace').splitlines()]
def events(token):
    return [dict(timestamp=l[1:24], **dict(re.findall(r'(\w+)=(\S+)', l.split(token, 1)[1])))
            for l in lines if token in l]
data = dict(schedule=events('M5 schedule '), consumed=events('M5 consumed '),
            menu_draws=events('M5 menu_draw '),
            frames=[dict(file=p.name, size=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                    for p in sorted(run.glob('m3_frame_*.bmp'))])
(output/'observations.json').write_text(json.dumps(data, indent=2) + '\n')
print(json.dumps(dict(schedule_events=len(data['schedule']), consumed_events=len(data['consumed']),
                      menu_draws=len(data['menu_draws']), private_frames=len(data['frames']))))
