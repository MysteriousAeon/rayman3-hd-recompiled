"""Closed-loop normal-input pilot for the intro_10 carried flight.

Reads actor transforms and the fly generator's designer variables (read-only) and appends
host key events to the live input schedule, which the runtime dispatches through
WindowSDL -> MnK -> XAM (run_milestone5.ps1 -Follow). It never writes guest memory.
Variable roles come from the decoded NIN_m_GenFlyIntro_10 scripts (RE_NOTES.md):
5 = red lums collected, 10/11 = current/next waypoint position, 20/21 = lateral offset /
its target (+-3.5 from the left-stick sign), 3 = next voice line, 27 = arcs at the waypoint.

usage: m5_flight_pilot.py PID BASE_HEX ACTORS_JSON SCHEDULE LOG [--seconds N] [--observe]
"""
import argparse, json, math, time
from pathlib import Path
from m5_live import Process, Actor, f32, u8, i32, vec

ap = argparse.ArgumentParser()
ap.add_argument('pid', type=int); ap.add_argument('base', type=lambda x: int(x, 16))
ap.add_argument('actors', type=Path); ap.add_argument('schedule', type=Path); ap.add_argument('log', type=Path)
ap.add_argument('--seconds', type=int, default=300); ap.add_argument('--observe', action='store_true')
ap.add_argument('--sign', type=float, default=1.0)
a = ap.parse_args()
process = Process(a.pid, a.base)
def sub(p, q): return tuple(x - y for x, y in zip(p, q))
def dot(p, q): return sum(x * y for x, y in zip(p, q))

actors = [Actor(process, int(x['so'], 16)) for x in json.loads(a.actors.read_text())['actors']]
def one(name): return next(x for x in actors if x.model == name)
gen, murfy, rayman = one('NIN_m_GenFlyIntro_10'), one('NIN_m_MurfyIntro10'), one('YLT_RaymanModel')
lums = [x for x in actors if x.model == 'NIN_m_Lums_Int10']
KEYS = {1: 7, -1: 4}  # SDL scancodes D / A = left stick right / left through the existing MnK bindings
held = 0
def press(direction):
    global held
    if direction == held or a.observe: return
    with open(a.schedule, 'a') as f:
        if held: f.write(f'0 {KEYS[held]} 0\n')
        if direction: f.write(f'0 {KEYS[direction]} 1\n')
    held = direction
end = time.monotonic() + a.seconds; last = None; held_since = 0.0
with open(a.log, 'a') as log:
    def emit(**item): log.write(json.dumps(dict(t=round(time.time(), 3), **item)) + '\n'); log.flush()
    while time.monotonic() < end:
        if not gen.alive() or not murfy.alive(): emit(event='flight_actor_gone'); break
        d = gen.dsg(); g, m = gen.position(), murfy.position()
        forward = sub(vec(d[11]), vec(d[10]))  # current -> next waypoint
        n = math.hypot(forward[0], forward[1]) or 1.0
        fwd = (forward[0] / n, forward[1] / n, 0.0)
        right = (fwd[1] * a.sign, -fwd[0] * a.sign, 0.0)
        best = None
        for l in lums:
            if not l.alive() or not l.custom_bits() & 0x10000: continue  # custom bit 17: still collectable
            rel = sub(l.position(), g); ahead, lateral = dot(rel, fwd), dot(rel, right)
            if 2.0 < ahead < 60.0 and abs(lateral) < 8.0 and (best is None or ahead < best[0]): best = (ahead, lateral, l.so)
        want = 0
        if best: want = 1 if best[1] > 1.2 else -1 if best[1] < -1.2 else 0
        if u8(d[5]) >= 6: want = 0  # exit condition met (junction test in the arrival macro); stop steering
        lateral_now = dot(sub(m, g), right)
        if held and time.monotonic() - held_since > 0.8 and abs(lateral_now) > 1.5 and (lateral_now > 0) != (held > 0):
            a.sign = -a.sign; emit(event='lateral_sign_flipped', sign=a.sign)
            press(0); continue
        if want != held: held_since = time.monotonic()
        press(want)
        state = dict(lums=u8(d[5]), voice_index=i32(d[3]), offset=round(f32(d[20]), 2), target_offset=round(f32(d[21]), 2),
                     arcs=i32(d[27]), murfy_lateral=round(lateral_now, 2), held=held,
                     target=[round(best[0], 1), round(best[1], 1), f'{best[2]:08X}'] if best else None,
                     rayman=[round(x, 1) for x in rayman.position()], gen=[round(x, 1) for x in g],
                     live_lums=sum(1 for l in lums if l.alive() and l.custom_bits() & 0x10000),
                     comports=[gen.comport(), murfy.comport(), rayman.comport()])
        key = (state['lums'], state['held'], state['target'] and state['target'][2], state['voice_index'], tuple(state['comports']))
        if key != last or int(time.monotonic() * 2) % 4 == 0: emit(**state)
        last = key
        time.sleep(0.05)
press(0)
