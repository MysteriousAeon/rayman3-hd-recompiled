"""Metadata summary of a closed-loop M5 run: flight pilot result, level transition and the
grounded-control plan segments, each joined to the guest-visible input (XAM) and to the
game's consumption observer (function 822331D8) from the runtime log. Samples stay private.

usage: m5_ground_summarize.py private/work/m5_runs/RUN reports/milestone5/RUN/ground.json
"""
import datetime, json, math, re, sys
from pathlib import Path

run, output = Path(sys.argv[1]), Path(sys.argv[2])
parts = sorted(run.glob('runtime.*.log'), key=lambda p: -int(p.name.split('.')[1])) + [run/'runtime.log']
lines = [l for p in parts for l in p.read_text(errors='replace').splitlines()]
def stamp(line): return datetime.datetime.strptime(line[1:24], '%Y-%m-%d %H:%M:%S.%f').timestamp()
consumed = []
for l in lines:
    if 'M5 consumed ' in l:
        f = dict(re.findall(r'(\w+)=(\S+)', l.split('M5 consumed ', 1)[1]))
        consumed.append((stamp(l), int(f['buttons'], 16), int(f['a']), float(f['normalized_lx']), float(f['normalized_ly']), float(f['normalized_rx'])))
xam = []
for l in lines:
    m = re.search(r'buttons=([0-9A-F]{4}) lx=(-?\d+) ly=(-?\d+) rx=(-?\d+) ry=(-?\d+)', l)
    if m and 'XamInputGetState' in l: xam.append((stamp(l), int(m[1], 16), *map(int, m.groups()[1:])))
levels = [dict(time=l[1:24], level=m[1].lower()) for l in lines
          if (m := re.search(r'vfs_open path=D:\\GamedataBIN\\(\w+)\\\1\.lvl result=00000000', l, re.I))]
levels = [x for i, x in enumerate(levels) if not i or levels[i - 1]['level'] != x['level']]

pilot = [json.loads(l) for l in (run/'pilot.log').read_text().splitlines()] if (run/'pilot.log').exists() else []
flight = [p for p in pilot if 'lums' in p]
result = dict(levels=levels, flight=dict(
    samples=len(flight), lums_start=flight[0]['lums'] if flight else None, lums_end=flight[-1]['lums'] if flight else None,
    lum_times=[round(p['t'] - flight[0]['t'], 2) for i, p in enumerate(flight) if i and p['lums'] > flight[i - 1]['lums']],
    key_presses=sum(1 for i, p in enumerate(flight) if i and p['held'] and p['held'] != flight[i - 1]['held']),
    sign_flips=sum(1 for p in pilot if p.get('event') == 'lateral_sign_flipped'),
    max_abs_lateral_offset=max((abs(p['offset']) for p in flight), default=None),
    behaviours=sorted({tuple(p['comports']) for p in flight if 'comports' in p}),
    ended_by_actor_removal=any(p.get('event') == 'flight_actor_gone' for p in pilot)))

rows = [json.loads(l) for l in (run/'ground.jsonl').read_text().splitlines()] if (run/'ground.jsonl').exists() else []
samples = [r for r in rows if 'rayman' in r and 'event' not in r]
control = next((r for r in rows if r.get('event') == 'control'), None)
segments = []
if control:
    labels = []
    for r in samples:
        if r['t'] < control['t']: continue
        if not labels or labels[-1][0] != r['label']: labels.append((r['label'], []))
        labels[-1][1].append(r)
    for label, g in labels:
        a, b = g[0], g[-1]; t0, t1 = a['t'], b['t']
        zs = [r['rayman'][2] for r in g]
        relative = lambda r: [c - p for c, p in zip(r['camera'], r['rayman'])]
        angle = lambda r: math.degrees(math.atan2(relative(r)[1], relative(r)[0]))
        turn = (angle(b) - angle(a) + 180) % 360 - 180
        cs = [c for c in consumed if t0 <= c[0] <= t1]; xs = [x for x in xam if t0 <= x[0] <= t1]
        segments.append(dict(
            label=label, seconds=round(t1 - t0, 2), samples=len(g),
            horizontal_displacement=round(math.dist(a['rayman'][:2], b['rayman'][:2]), 3),
            path_length=round(sum(math.dist(p['rayman'][:2], q['rayman'][:2]) for p, q in zip(g, g[1:])), 3),
            z_rise=round(max(zs) - zs[0], 3), z_end_minus_start=round(zs[-1] - zs[0], 3),
            camera_orbit_degrees=round(turn, 2), camera_distance_change=round(math.hypot(*relative(b)) - math.hypot(*relative(a)), 3),
            behaviours=[x for i, x in enumerate([r['comports'][0] for r in g]) if not i or g[i - 1]['comports'][0] != x],
            reflexes=sorted({r['comports'][1] for r in g if r['comports'][1]}),
            xam=dict(samples=len(xs), buttons=sorted({f'{x[1]:04X}' for x in xs}), lx=[min((x[2] for x in xs), default=0), max((x[2] for x in xs), default=0)],
                     ly=[min((x[3] for x in xs), default=0), max((x[3] for x in xs), default=0)], rx=[min((x[4] for x in xs), default=0), max((x[4] for x in xs), default=0)]),
            consumed=dict(events=len(cs), a_pressed=any(c[2] for c in cs), normalized_lx=[min((c[3] for c in cs), default=0), max((c[3] for c in cs), default=0)],
                          normalized_ly=[min((c[4] for c in cs), default=0), max((c[4] for c in cs), default=0)],
                          normalized_rx=[min((c[5] for c in cs), default=0), max((c[5] for c in cs), default=0)])))
pre = [r for r in samples if control and r['t'] < control['t']]
result['ground'] = dict(
    control_behaviour=control and control['comports'], seconds_from_probe_start_to_control=control and samples and round(control['t'] - samples[0]['t'], 2),
    pre_control_behaviours=sorted({r['comports'][0] for r in pre}), segments=segments,
    ended=next((r for r in rows if r.get('event') == 'end'), None) and {k: v for k, v in rows[-1].items() if k != 't'})
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=1) + '\n')
for s in segments:
    print(f"{s['label']:20s} disp={s['horizontal_displacement']:7.2f} zrise={s['z_rise']:5.2f} orbit={s['camera_orbit_degrees']:7.2f} {s['behaviours']} xam={s['xam']['buttons']} lx={s['xam']['lx']} ly={s['xam']['ly']} rx={s['xam']['rx']} consumed={s['consumed']['events']}")
print(json.dumps(result['flight'])[:400]); print(levels)
