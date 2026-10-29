"""E-304 private hidden knaar_69 fixture; real pickups, read-only guest watch.

run NAME --mode observe|timed|countdown|delayed-countdown [--replay RUN] [--captures] [--timer-captures]
analyze NAME

Requires the existing private format-2 actor scan. Uses M19/M9/M6 only. Captures
are opt-in (eight maximum); all schedules, traces and pictures remain private.
Replay uses the recorded input events at engine-timer checkpoints, not guest
state injection. Sampling/replay granularity is recorded and is not frame exact.
"""
import argparse
import json
import os
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import m17_frame_trace as ft
import m19_campaign_check as m19
from m5_live import Actor, Process, f32, i32, u8

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'private/work'
RUNS = WORK / 'm6_runs'
LEVEL = 'knaar_69'


def run(a):
    trace = WORK / (a.name + '.trace')
    ranges = ft.TIMER_WATCH + [(0x8288D528, 0x140), (0x82837E9C, 8), (0x828A3E28, 0xE0), (0x8288B414, 4)]
    ft.write_watch(trace, ranges)
    steps = Path(a.combat_steps).resolve() if a.combat_steps and not (a.replay or a.input_plan) else WORK / (a.name + '_idle.txt')
    if not a.combat_steps or a.replay or a.input_plan:
        steps.write_bytes(b'wait 58\n')
    replay = (json.loads(Path(a.input_plan).read_text()) if a.input_plan else
              json.loads((RUNS / a.replay / 'input_events.json').read_text()) if a.replay else None)

    def beside(run_dir, game, log):
        if not m19.wait_for_log(run_dir, LEVEL + '\\' + LEVEL + '.lvl result=00000000', game, 60):
            return ['level not opened']
        (run_dir / 'fixture.json').write_text(json.dumps(vars(a), indent=1))
        # Attach early on replay so no recorded event has already passed.
        time.sleep(1 if replay else 6)
        pid, base = m19.attach(run_dir)
        p = Process(pid, int(base, 16))
        records = json.loads((WORK / 'm14/scan_v2' / LEVEL / 'actors.json').read_text())
        live = []
        for r in records['actors']:
            try:
                actor = Actor(p, int(r['so'], 16))
                if actor.alive() and actor.model == r['model']:
                    live.append((r, actor))
            except (OSError, TypeError, IndexError):
                pass
        player = next(x for _, x in live if x.model == 'YLT_RaymanModel')
        grat = next(x for _, x in live if x.model == 'YAM_GenGratificator')
        mem = p.words(grat.mind[3], 3)
        var = p.words(p.words(mem[0], 1)[0], 4)
        assert mem[2] == 0x40CDD5BC and var[2] == 325, 'fixture designer buffer differs'
        watch = ranges + [(mem[2], var[2]), (grat.mind[1], 0x10)]
        enemies = [(r, actor) for r, actor in live if actor.model == 'YAM_M_CagouSnipeBase']
        if a.combat_steps:
            watch += [(actor.std + 0x1D, 2) for _, actor in enemies]
        ft.write_watch(trace, watch)
        (run_dir / 'layout.json').write_text(json.dumps(dict(dsg=hex(mem[2]),
            vars=[x[1] for x in grat.dsg()], ranges=watch,
            enemies=[dict(model=r['model'], perso=r['perso'], hp_address=hex(actor.std + 0x1D))
                     for r, actor in enemies] if a.combat_steps else [])))
        stop = threading.Event()
        failures, inputs, replay_actual, pause_events = [], [], [], []

        def sample():
            last_lines = len((run_dir / 'schedule.txt').read_text().splitlines())
            paid, reentered, seen, captured_bonus = None, None, False, False
            first_nonzero = None
            captures, milestones, replay_index = 0, set(), 0
            pause_schedule = None
            long_start = None
            with (run_dir / 'cashout_watch.jsonl').open('w') as out:
                while not stop.is_set() and p.running():
                    try:
                        now = time.monotonic()
                        timer = ft.timer_fields({addr: p.read(addr, size) for addr, size in ft.TIMER_WATCH})
                        ms = timer['total_ms']
                        if replay:
                            while replay_index < len(replay) and ms >= replay[replay_index]['engine']:
                                event = replay[replay_index]
                                with (run_dir / 'schedule.txt').open('a', encoding='ascii', newline='') as stream:
                                    stream.write('\n'.join(event['lines']) + '\n')
                                replay_actual.append(dict(expected=event['engine'], actual=ms, lines=event['lines']))
                                replay_index += 1
                        lines = (run_dir / 'schedule.txt').read_text().splitlines()
                        if len(lines) > last_lines:
                            inputs.append(dict(engine=ms, lines=lines[last_lines:]))
                            last_lines = len(lines)
                        d = grat.dsg()
                        score, bonus = i32(d[36]), f32(d[24])
                        hud = p.words(0x8288D528, 80)
                        # Additional test after all pickup inputs: pause during the
                        # second close, then select the title's Resume Game with A.
                        pause_after = (1300 if a.mode == 'delayed-countdown' else
                                       600 if a.mode == 'countdown' else 2600)
                        pause_due = ((a.pause and reentered and ms >= reentered + pause_after) or
                                     (a.pause_first and u8(d[29]) and
                                      ms - i32(d[26]) >= i32(d[25]) - 800))
                        if (pause_due and pause_schedule is None
                                and hud[(0x8288D618-0x8288D528)//4] == 3):
                            pause_schedule = [(now, 40, 1), (now + .2, 40, 0),
                                              (now + 2.2, 44, 1), (now + 2.4, 44, 0)]
                        if pause_schedule:
                            while pause_schedule and now >= pause_schedule[0][0]:
                                _, key, value = pause_schedule.pop(0)
                                with (run_dir / 'schedule.txt').open('a', encoding='ascii') as stream:
                                    stream.write(f'0 {key} {value}\n')
                                pause_events.append(dict(engine=ms, key=key, value=value,
                                                         hud_state=hud[(0x8288D618-0x8288D528)//4]))
                        row = dict(engine=ms, score=score, bonus=bonus, pending=u8(d[29]),
                                   hud=hud, player=player.position(), wall=now,
                                   objects=p.words(0x828A3E28, 56))
                        label = None
                        if bonus > 0:
                            seen = True
                            if first_nonzero is None:
                                first_nonzero = ms
                            if not captured_bonus:
                                label, captured_bonus = 'nonzero', True
                        if (a.delayed_captures and not seen and hud[(0x8288D618-0x8288D528)//4] == 3
                                and 'initial_close' not in milestones):
                            label = 'initial_close'
                            milestones.add(label)
                        if seen and bonus == 0 and paid is None:
                            paid = (ms, score)
                        if paid and score > paid[1] and reentered is None:
                            reentered = ms
                        if a.timer_captures and first_nonzero:
                            for delay in ((600, 1100, 1600) if a.delayed_captures else (600, 1300)):
                                key = 'countdown_' + str(delay)
                                if ms >= first_nonzero + delay and key not in milestones:
                                    label = key
                                    milestones.add(key)
                                    break
                            if paid and 'expiry' not in milestones:
                                label = 'expiry'
                                milestones.add(label)
                        if paid and not a.timer_captures:
                            for delay in (0, 600, 1300, 2000):
                                key = 'close_' + str(delay)
                                if ms >= paid[0] + delay and key not in milestones:
                                    label = key
                                    milestones.add(key)
                                    break
                        if reentered:
                            for delay in ((0, 1100) if a.delayed_captures else (0, 600)):
                                key = 'reentry_' + str(delay)
                                if ms >= reentered + delay and key not in milestones:
                                    label = key
                                    milestones.add(key)
                                    break
                            if ms >= reentered + 8500 and 'settled' not in milestones:
                                label = 'settled'
                                milestones.add(label)
                        if a.six_second_captures:
                            # Observe genuine target writes; never manufacture a window.
                            label = None
                            if i32(d[25]) == 6000 and u8(d[29]):
                                long_start = i32(d[26])
                            if long_start is not None:
                                for delay in (0, 1000, 4000, 4900, 5150, 5600, 5900, 6050):
                                    key = 'six_second_' + str(delay)
                                    if ms >= long_start + delay and key not in milestones:
                                        label = key
                                        milestones.add(key)
                                        break
                        if a.captures and label and captures < 8:
                            captures += 1
                            (run_dir / 'frame.request').write_bytes(f'{captures}\n'.encode())
                            row.update(capture=captures, label=label)
                        out.write(json.dumps(row) + '\n')
                        out.flush()
                        time.sleep(.01)
                    except (OSError, TypeError, IndexError, ValueError) as exc:
                        failures.append(f'watch failed: {exc}')
                        break
            (run_dir / 'input_events.json').write_text(json.dumps(inputs, indent=1))
            (run_dir / 'replay_actual.json').write_text(json.dumps(replay_actual, indent=1))
            (run_dir / 'pause_events.json').write_text(json.dumps(pause_events, indent=1))

        thread = threading.Thread(target=sample)
        thread.start()

        def walk(perso):
            chosen = next(r for r, actor in live if actor.perso == perso)
            selected = dict(records, actors=[r for r, actor in live if actor.model == 'YLT_RaymanModel'] + [chosen])
            path = run_dir / f'selected_{perso:x}.json'
            path.write_text(json.dumps(selected))
            subprocess.run([sys.executable, str(ROOT / 'tools/m19_walk_to.py'), str(run_dir), str(path),
                            'NIK_mPickup', '--seconds', '7', '--stop', '1.8', '--log',
                            str(run_dir / f'walk_{perso:x}.json')], stdout=log, stderr=subprocess.STDOUT,
                           timeout=12, check=True)

        try:
            if replay:
                time.sleep(40 if a.combat_steps else 28)
            elif a.combat_steps:
                if a.combat_pickup_delay is not None:
                    end = time.monotonic() + 30
                    while time.monotonic() < end and p.running():
                        if p.words(0x40CDD648, 1)[0] == 6000 and p.read(0x40CDD6FE, 1) == b'\x01':
                            break
                        time.sleep(.02)
                    else:
                        raise RuntimeError('No genuine six-second combat event before pickup route')
                    time.sleep(a.combat_pickup_delay)
                    walk(0x41031EF0)
                    with (run_dir / 'schedule.txt').open('a', encoding='ascii') as stream:
                        stream.write('0 44 1\n')
                    time.sleep(.6)
                    with (run_dir / 'schedule.txt').open('a', encoding='ascii') as stream:
                        stream.write('0 44 0\n')
                    time.sleep(10)
                else:
                    time.sleep(40)
            else:
                walk(0x41031EF0)
                time.sleep(a.pre_jump_delay)
                with (run_dir / 'schedule.txt').open('a', encoding='ascii') as stream:
                    stream.write('0 44 1\n')
                time.sleep(a.jump_hold)
                with (run_dir / 'schedule.txt').open('a', encoding='ascii') as stream:
                    stream.write('0 44 0\n')
                if not a.first_only:
                    time.sleep(a.pickup_delay)
                    walk(0x41031130)
                time.sleep(14)
        finally:
            stop.set()
            thread.join(5)
        return failures

    env = {'R3HD_FRAME_TRACE': str(trace)}
    # Normal profile acceptance: use the same resolver and Play dry-run plan as
    # a person, but execute exclusively through the existing hidden M6 runner.
    # No private animation flag may reach a profile test process.
    if a.preset or a.settings_file:
        from r3hd_settings import load_registry, load_settings_file, resolve
        if a.mode != 'off':
            raise ValueError('--preset requires --mode off (no private animation override)')
        if a.settings_file:
            source = Path(a.settings_file).resolve()
            if not source.is_relative_to((ROOT / 'private/work').resolve()):
                raise ValueError('--settings-file must be an isolated private/work configuration')
            snapshot = WORK / (a.name + '_settings.json')
            snapshot.write_bytes(source.read_bytes())
            saved = load_settings_file(snapshot)
            planned = resolve(load_registry(), settings=saved)['values']['combo_close']
            selection = ['-SettingsFile', str(snapshot)]
            a.settings_file = str(snapshot)
        else:
            planned = resolve(load_registry(), a.preset)['values']['combo_close']
            selection = ['-Preset', a.preset]
        a.profile_combo_close = planned
        plan = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
            '-File', str(ROOT / 'tools/play.ps1'), '-DryRun', *selection],
            cwd=ROOT, capture_output=True, text=True, check=True)
        assert f'combo close: {planned}' in plan.stdout
        os.environ.pop('R3HD_TEST_COMBO_PLAYTEST', None)
        os.environ.pop('R3HD_TEST_COMBO_CAPTURE', None)
        env['R3HD_COMBO_CLOSE'] = planned
        # The launch plan is evidence, not a visible process invocation.
        (WORK / (a.name + '_profile_plan.txt')).write_text(plan.stdout)
    else:
        os.environ.pop('R3HD_COMBO_CLOSE', None)
    if a.mode == 'off':
        os.environ.pop('R3HD_TEST_COMBO_CLOSE', None)
    else:
        env['R3HD_TEST_COMBO_CLOSE'] = a.mode
    if a.captures:
        env['R3HD_M22_DRAW_TRACE'] = '1'
    reasons = m19.hidden_run(a.name, steps, 65, test_level=LEVEL, env=env, beside=beside)
    print(json.dumps(reasons))
    return bool(reasons)


def analyze(name):
    run_dir = RUNS / name
    layout = json.loads((run_dir / 'layout.json').read_text())
    base, offsets = int(layout['dsg'], 16), layout['vars']
    events, last = [], None
    for swap, host, guest, ranges in ft.frames(WORK / (name + '.trace')):
        d, hud, visible = ranges.get(base), ranges.get(0x8288D528), ranges.get(0x82837E9C)
        if not d or not hud or not visible:
            continue
        def integer(index):
            return struct.unpack_from('>i', d, offsets[index])[0]
        def floating(index):
            return round(struct.unpack_from('>f', d, offsets[index])[0], 4)
        def word(address):
            return struct.unpack_from('>I', hud, address - 0x8288D528)[0]
        def number(address):
            return round(struct.unpack_from('>f', hud, address - 0x8288D528)[0], 4)
        values = dict(score=integer(36), bonus=floating(24), start_ms=integer(26), expiry_ms=integer(25),
            pending=d[offsets[29]], hud_state=word(0x8288D618), visible=list(struct.unpack('>II', visible)),
            duration=number(0x8288D5AC), digits=[word(0x8288D570 + 4*i) for i in range(5)],
            handles=[word(0x8288D654), word(0x8288D658)])
        if events and swap == events[-1]['swap'] + 1:
            events[-1]['next_elapsed'] = number(0x8288D614)
        signature = json.dumps(values, sort_keys=True)
        if signature != last:
            events.append(dict(swap=swap, engine=ft.timer_fields(ranges)['total_ms'],
                               elapsed=number(0x8288D614), **values))
            last = signature
    (run_dir / 'frame_events.json').write_text(json.dumps(events, indent=1))
    for event in events:
        print(json.dumps(event))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    runner = sub.add_parser('run')
    runner.add_argument('name')
    runner.add_argument('--mode', required=True, choices=('off', 'observe', 'timed', 'countdown', 'delayed-countdown'))
    production = runner.add_mutually_exclusive_group()
    production.add_argument('--settings-file', help='isolated saved Settings file; production resolver and Play plan')
    production.add_argument('--preset', choices=('vanilla', 'hdplus'),
                        help='verify normal Play profile plan and use production Combo configuration; mode must be off')
    runner.add_argument('--replay')
    runner.add_argument('--input-plan', help='recorded scoped input JSON, for the shortened manual observer')
    runner.add_argument('--combat-steps', help='existing scoped combat schedule; omit adaptive pickup inputs')
    runner.add_argument('--six-second-captures', action='store_true',
                        help='capture only genuine 6000ms-window boundaries, max8')
    runner.add_argument('--combat-pickup-delay', type=float,
                        help='after a real six-second scoring event, wait then use the existing pickup route')
    runner.add_argument('--captures', action='store_true')
    runner.add_argument('--timer-captures', action='store_true',
                        help='with --captures, select pre-expiry 0/.6/1.3s and expiry/re-entry events (max8)')
    runner.add_argument('--pause', action='store_true', help='pause/resume during the second close')
    runner.add_argument('--pause-first', action='store_true', help='pause/resume during the first final-second close')
    runner.add_argument('--delayed-captures', action='store_true',
                        help='with timer captures, sample .6/1.1/1.6s plus expiry and delayed re-entry (max8)')
    runner.add_argument('--jump-hold', type=float, default=.6,
                        help='duration of scoped A hold in adaptive fixture; replay uses recorded events')
    runner.add_argument('--first-only', action='store_true',
                        help='omit the later walk, matching the watch-only manual observer')
    runner.add_argument('--pre-jump-delay', type=float, default=0,
                        help='scoped fixture wait after the first walk, before jumping to refresh its combo')
    runner.add_argument('--pickup-delay', type=float, default=.7,
                        help='post-jump wait before the later pickup walk (E-303 used 3)')
    reader = sub.add_parser('analyze')
    reader.add_argument('name')
    args = parser.parse_args()
    raise SystemExit(run(args) if args.command == 'run' else analyze(args.name))
