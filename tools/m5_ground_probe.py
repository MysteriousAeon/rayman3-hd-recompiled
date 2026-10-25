"""Grounded-control test driver for the level reached after the intro_10 flight.

Waits for LEVEL to load, rediscovers actors (addresses are never assumed), then samples
Rayman and the camera at ~20 Hz while playing a key plan through the live input schedule
(normal WindowSDL -> MnK -> XAM path). Read-only: no guest memory is written.

usage: m5_ground_probe.py PID BASE_HEX RUN_DIR [--level intro_15] [--plan FILE] [--seconds N]
PLAN lines: "<seconds after control> <label> <scancode> <hold seconds>"; scancode 0 = idle
marker. "control" is the first sample at which --ready-comport is Rayman's normal behaviour
(or --ready-after seconds when no behaviour is given). Output: RUN_DIR/ground.jsonl (private).
"""
import argparse, glob, json, subprocess, sys, time
from pathlib import Path
from m5_live import Process, Actor

ap = argparse.ArgumentParser()
ap.add_argument('pid', type=int); ap.add_argument('base'); ap.add_argument('run', type=Path)
ap.add_argument('--level', default='intro_15'); ap.add_argument('--plan', type=Path)
ap.add_argument('--seconds', type=int, default=120); ap.add_argument('--settle', type=float, default=8.0)
ap.add_argument('--ready-comport', default=''); ap.add_argument('--ready-after', type=float, default=0.0)
ap.add_argument('--output', default='ground.jsonl')
a = ap.parse_args()
needle = f'{a.level}.lvl result=00000000'
def loaded(): return any(needle in open(p, errors='replace').read() for p in glob.glob(str(a.run/'runtime*.log')))
deadline = time.monotonic() + 240
while not loaded():
    if time.monotonic() > deadline: sys.exit(f'{a.level} never loaded')
    time.sleep(1)
time.sleep(a.settle)
actors_json = a.run/f'actors_{a.level}.json'
subprocess.run([sys.executable, str(Path(__file__).with_name('m5_memory_probe.py')), str(a.pid), a.base, str(actors_json), '--regions'], check=True)
process = Process(a.pid, int(a.base, 16))
actors = [Actor(process, int(x['so'], 16)) for x in json.loads(actors_json.read_text())['actors']]
rayman = next(x for x in actors if x.model == 'YLT_RaymanModel')
camera = next(x for x in actors if x.model == 'StdCam')
plan = []
for line in (a.plan.read_text().splitlines() if a.plan else []):
    if line.strip() and not line.startswith('#'):
        t, label, scan, hold = line.split(); plan.append((float(t), label, int(scan), float(hold)))
events = []  # (absolute monotonic time, schedule line or None, label)
def key(scan, down):
    with open(a.run/'schedule.txt', 'a') as f: f.write(f'0 {scan} {down}\n')
start = time.monotonic(); control = None; label = 'pre_control'; previous = None
with open(a.run/a.output, 'a') as log:
    def emit(**item): log.write(json.dumps(dict(t=round(time.time(), 3), **item)) + '\n'); log.flush()
    emit(event='models', models=sorted({x.model for x in actors}), rayman=f'{rayman.so:08X}', camera=f'{camera.so:08X}')
    while time.monotonic() - start < a.seconds and process.running() and rayman.alive():
        now = time.monotonic()
        comports = [rayman.comport(), rayman.comport(reflex=True)]
        if control is None and ((a.ready_comport and comports[0] == a.ready_comport) or (not a.ready_comport and now - start >= a.ready_after)):
            control = now; emit(event='control', comports=comports)
            for t, name, scan, hold in plan:
                events.append((control + t, name, scan, 1))
                if scan: events.append((control + t + hold, name + '_released', scan, 0))
            events.sort()
        while events and events[0][0] <= now:
            _, name, scan, down = events.pop(0); label = name
            if scan: key(scan, down)
            emit(event='plan', label=name, scancode=scan, down=down)
        dsg = rayman.dsg()
        sample = dict(label=label, rayman=[round(x, 3) for x in rayman.position()], camera=[round(x, 3) for x in camera.position()],
                      comports=comports, main_state=int.from_bytes(dsg[0][0][dsg[0][1]:dsg[0][1] + 4], 'big'))
        if comports != previous: emit(event='comport', comports=comports); previous = comports
        emit(**sample)
        time.sleep(0.05)
    emit(event='end', running=process.running(), rayman_alive=rayman.alive())
