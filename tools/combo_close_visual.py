"""User-invoked, watch-only private visual comparison. --check never starts a game.

The unchanged compiled hook requires NONINTRUSIVE. Retain its device/input gates
and reveal only this child PID's window with SW_SHOWNOACTIVATE. This is an
explicit manual observer, not an unattended M6 run or normal playable session.
"""
import argparse
import ctypes
from ctypes import wintypes as wt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'private/work/combo_e305_runtime'
SCAN = ROOT / 'private/work/m14/scan_v2/knaar_69/actors.json'
HASHES = {
    'r3hd.exe': '97a6201adcabd67b3bc951a4b6fbe45176b07749a5eb1e9d423b9fd68e4b6e27',
    'rexruntime.dll': 'dd3e79cd574497e2d657ca31cfef6b0ba24d076546317bfbf24c90b01ebdda60',
    'rexgpu-xenos.dll': 'd7646e66e11bbf422c7b892502deb8d0fc1a58bac35ca1c21c9c3856fdb8bd03',
    'ffmpeg.dll': '68dd542c69763e8ceebedcc8eeaf3173bc14221d6ab08010575841513ad55229',
    'mspack.dll': 'fa48bfb0b688d2366cc4131b2cd98d3b1e1417a8c5d44448103bbbf61676bd97',
}
DELAYED_BIN = ROOT / 'private/work/combo_e306_runtime'
DELAYED_HASHES = dict(HASHES, **{
    'r3hd.exe': '388da6b0c7fb90a31c90a053dcaaca018ea193aa935016640b3053bb3a51dc88',
})
SIX_INPUTS = ROOT / 'config/combo/six_second_inputs.json'
SIX_BIN = ROOT / 'private/work/combo_e307_runtime'
SIX_HASHES = dict(DELAYED_HASHES, **{
    'r3hd.exe': 'a03bb0ac94d62c9b99d8a047a0a05409130256e6239134eacb3819940a8e6e53',
})


def six_second_inputs():
    for name, expected in SIX_HASHES.items():
        if hashlib.sha256((SIX_BIN / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Pinned six-second artifact mismatch: {name}')
    events = json.loads(SIX_INPUTS.read_text())
    expected = [9382, 10983, 11982, 13583, 14583, 16182, 17183, 18783]
    if ([e['engine'] for e in events] != expected or
            any(e['lines'] != [f'0 15 {1 if i % 2 == 0 else 0}'] for i, e in enumerate(events))):
        raise RuntimeError('Six-second observer input fixture differs from the verified four charges')
    return events


def observe_six_second(run, game, process, grat):
    """Replay only process-local X input; observe real target timer writes."""
    from m5_live import i32, f32
    events, index, seen_long, seen_close = six_second_inputs(), 0, False, False
    if process.words(0x82C0628C, 1)[0] >= events[0]['engine']:
        raise RuntimeError('Observer attached too late for the recorded fight; close and retry')
    last = None
    with (run / 'observations.jsonl').open('w') as out:
        end = time.monotonic() + 40
        while game.poll() is None and time.monotonic() < end:
            tick = process.words(0x82C0628C, 1)[0]
            while index < len(events) and tick >= events[index]['engine']:
                with (run / 'schedule.txt').open('a', encoding='ascii') as stream:
                    stream.write('\n'.join(events[index]['lines']) + '\n')
                index += 1
            d = grat.dsg()
            state = process.words(0x8288D618, 1)[0]
            window, start = i32(d[25]), i32(d[26])
            pending = process.read(0x40CDD6FE, 1) == b'\x01'
            row = dict(score=i32(d[36]), bonus=f32(d[24]), window=window,
                       start=start, pending=pending, hud_state=state)
            if window == 6000 and pending and not seen_long:
                seen_long = True
                print('REAL 6s window observed. WATCH UPPER LEFT: open for five seconds, then one-second slide.', flush=True)
            if window == 6000 and pending and state == 3 and not seen_close:
                seen_close = True
                print(f'Final-second slide observed at age {tick-start} ms.', flush=True)
            if row != last:
                out.write(json.dumps(dict(tick=tick, **row)) + '\n')
                out.flush()
                print(row, flush=True)
                last = row
            time.sleep(.01)
    print('Six-second event + closing state observed.' if seen_long and seen_close else
          'Fixture MISSED: not a successful six-second test; close and retry.', flush=True)
    print('This kill has zero unpaid bonus; it demonstrates the timer and slide, not a nonzero payout.')
    print('Close X to finish. Re-run the launcher to repeat.', flush=True)


def binary(combo_mode):
    return DELAYED_BIN if combo_mode == 'delayed-countdown' else BIN


def configuration(combo_mode='timed'):
    hashes = DELAYED_HASHES if combo_mode == 'delayed-countdown' else HASHES
    for name, expected in hashes.items():
        if hashlib.sha256((binary(combo_mode) / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Pinned artifact mismatch: {name}; refusing another build')
    data = Path(os.environ.get('R3HD_GAME_DIR') or ROOT / 'private/extracted/5841123F').resolve()
    if not (data / 'Gamedata').is_dir() or not (data / 'psm').is_dir():
        raise RuntimeError('Configured extracted game-data folder is missing')
    if not (data / 'GAMEDATAbin/knaar_69/knaar_69.lvl').is_file():
        raise RuntimeError('Configured game data lacks the knaar_69 fixture level')
    records = json.loads(SCAN.read_text())
    selected = [r for r in records['actors'] if r['model'] == 'YLT_RaymanModel'
                or int(r['perso'], 16) == 0x41031EF0]
    if not any(int(r['perso'], 16) == 0x41031EF0 for r in selected):
        raise RuntimeError('Existing pickup fixture is missing')
    return data, dict(records, actors=selected)


def arguments(data, run, combo_mode='timed'):
    return [str(binary(combo_mode) / 'r3hd.exe'), f'--game_data_root={data}',
            f'--user_data_root={run / "user"}', f'--cache_root={run / "cache"}',
            f'--log_file={run / "runtime.log"}', '--gpu_plugin=xenos',
            '--log_level=info', '--log_flush_interval=1', '--mnk_mode=false',
            '--fullscreen=false', '--window_width=1280', '--window_height=720',
            '--cl=-level:knaar_69']


def environment(run, combo_mode):
    # Child-only allowlist: no inherited mods, faults, traces, licence override,
    # audible output, key tests, play home, or unrelated experimental switches.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('R3HD_')}
    if combo_mode not in ('timed', 'countdown', 'delayed-countdown'):
        raise ValueError('Unsupported private Combo mode')
    env.update(R3HD_NONINTRUSIVE='1', R3HD_TEST_COMBO_CLOSE=combo_mode,
               R3HD_TEST_SECONDS='180', R3HD_INPUT_SCHEDULE=str(run / 'schedule.txt'),
               R3HD_PLAY='1')
    return env


def reveal_owned_window(pid):
    ui = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    ui.EnumWindows.argtypes = [callback_type, wt.LPARAM]
    ui.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    ui.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    ui.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    found = []

    @callback_type
    def visit(hwnd, _):
        owner = wt.DWORD()
        ui.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        name = ctypes.create_unicode_buffer(256)
        ui.GetClassNameW(hwnd, name, len(name))
        if owner.value == pid and name.value.startswith('SDL'):
            ui.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE; never SetForegroundWindow.
            found.append(int(hwnd))
        return True

    ui.EnumWindows(visit, 0)
    if len(found) != 1:
        raise RuntimeError(f'Expected one SDL window belonging to child PID {pid}, got {found}')
    return found[0]


def manual(data, selected, combo_mode, six_second=False):
    from m19_campaign_check import wait_for_log, attach
    from m5_live import Process, Actor, i32, f32

    running = subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq r3hd.exe', '/NH'], text=True)
    if 'r3hd.exe' in running.lower():
        raise RuntimeError('Close the other game before starting this isolated test')
    print('PRIVATE COMBO VISUAL TEST - watch only; no keyboard/controller gameplay.')
    print(f'Mode: {combo_mode}; pinned executable and retained E-298 DLLs.')
    print('A fresh disposable profile/cache will be used. Sound and haptics stay off.')
    print('The game window will appear without taking focus. Do not move or collect anything.')
    print('The script uses four charged fists against the nearby Hoodlum.' if six_second else
          'The script triggers the combo with the existing pickup walk and jump.')
    if six_second:
        print('Watch when score becomes 100: Combo stays fully open for FIVE seconds,')
        print('then slides UP during the final ONE second. No physical input is needed.')
    elif combo_mode == 'timed':
        print('Watch Combo gain 10, expire about two seconds after scoring, then slide UP over six seconds.')
    elif combo_mode == 'countdown':
        print('Watch the row slide UP during the roughly two-second active combo countdown.')
        print('WARNING: Countdown may obscure Combo digits BEFORE scoring expires.')
    else:
        print('Watch after the jump: Combo stays fully open for about ONE second after scoring,')
        print('then slides UP during the FINAL one second before normal expiry/cash-out.')
    print('Use the window X to finish; automatic limit is three minutes.')
    input('Press Enter to open the manual test, or Ctrl+C to cancel: ')
    run = ROOT / 'private/work/combo_visual' / (time.strftime('%Y%m%d_%H%M%S_') + combo_mode + '_' + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    for child in ('user', 'cache'):
        (run / child).mkdir()
    (run / 'schedule.txt').write_bytes(b'0 300 0\n0 301 0\n')
    (run / 'actors.json').write_text(json.dumps(selected))
    command, env = arguments(data, run, combo_mode), environment(run, combo_mode)
    if six_second:
        command[0] = str(SIX_BIN / 'r3hd.exe')
    (run / 'launch.json').write_text(json.dumps(dict(arguments=command,
        environment={k: v for k, v in env.items() if k.startswith('R3HD_')},
        kind='user-invoked visible observer; not M6 nonintrusive acceptance'), indent=2))
    print(f'Test files: {run}', flush=True)
    game = subprocess.Popen(command, cwd=run, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    (run / 'process.json').write_text(json.dumps(dict(pid=game.pid)))
    try:
        if not wait_for_log(run, 'knaar_69\\knaar_69.lvl result=00000000', game, 60):
            raise RuntimeError('Test level did not open; see runtime.log')
        hwnd = reveal_owned_window(game.pid)
        print(f'Revealed child window {hwnd}; click it yourself if desired. Starting in six seconds.', flush=True)
        time.sleep(6)
        pid, base = attach(run)
        p = Process(pid, int(base, 16))
        grat = next(Actor(p, int(r['so'], 16)) for r in json.loads(SCAN.read_text())['actors']
                    if r['model'] == 'YAM_GenGratificator')
        if six_second:
            observe_six_second(run, game, p, grat)
            game.wait(timeout=180)
            return
        with (run / 'driver.log').open('w') as driver:
            subprocess.run([sys.executable, str(ROOT / 'tools/m19_walk_to.py'), str(run),
                str(run / 'actors.json'), 'NIK_mPickup', '--seconds', '7', '--stop', '1.8',
                '--log', str(run / 'walk.json')], stdout=driver, stderr=subprocess.STDOUT,
                timeout=12, check=True)
        with (run / 'schedule.txt').open('a') as stream:
            stream.write('0 44 1\n')
        time.sleep(.6)
        with (run / 'schedule.txt').open('a') as stream:
            stream.write('0 44 0\n')
        # Intentionally omit the second pickup walk: let the entire close finish.
        last, seen_bonus, seen_close = None, False, False
        deadline = time.monotonic() + 25
        with (run / 'observations.jsonl').open('w') as out:
            while game.poll() is None and time.monotonic() < deadline:
                d = grat.dsg()
                hud = p.words(0x8288D618, 1)
                row = dict(score=i32(d[36]), bonus=f32(d[24]), hud_state=hud[0])
                seen_bonus |= row['bonus'] > 0
                seen_close |= seen_bonus and row['hud_state'] == 3
                if row != last:
                    out.write(json.dumps(dict(wall=time.time(), **row)) + '\n')
                    out.flush()
                    print(row, flush=True)
                    last = row
                time.sleep(.02)
        print('Nonzero + closing state observed.' if seen_close else
              'Fixture missed: NOT a successful visual test. Close and run again.', flush=True)
        print('Only you can accept the visible movement/readability. Close the game window to finish.', flush=True)
        game.wait(timeout=180)
    finally:
        # Only this launcher-owned child; no system-wide game termination.
        if game.poll() is None:
            game.terminate()
            game.wait(timeout=15)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--manual', action='store_true')
    parser.add_argument('--mode', choices=('timed', 'countdown', 'delayed-countdown'), default='timed')
    parser.add_argument('--six-second', action='store_true', help='verified charged-fist six-second combat observer')
    a = parser.parse_args()
    try:
        data, selected = configuration(a.mode)
        if a.six_second:
            if a.mode != 'delayed-countdown':
                raise ValueError('Six-second observer requires delayed-countdown')
            six_second_inputs()
        if a.check:
            print('CHECK PASS: five pinned hashes, game data and pickup fixture present.')
            print('Private mode:', a.mode)
            print('Game data:', data)
            print('Executable:', (SIX_BIN if a.six_second else binary(a.mode)) / 'r3hd.exe')
            print('Fresh profiles/cache:', ROOT / 'private/work/combo_visual/<unique-session>')
            print('No game started; no session created. Manual window reveal NOT TESTED.')
        else:
            manual(data, selected, a.mode, a.six_second)
    except (Exception, KeyboardInterrupt) as exc:
        print(f'Test stopped: {exc}', file=sys.stderr)
        sys.exit(1)
