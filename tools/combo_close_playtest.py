"""Private, explicitly user-invoked playable launch. --check never starts a game."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import time
import uuid

from r3hd_settings import load_keymap, resolve_keyboard

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / 'private/work/combo_playtest_runtime'
HOME = ROOT / 'private/manual_playtests/combo_delayed'
HASHES = {
    'r3hd.exe': '47fbca3904134c86c0110d6b24cc147c9b93bf8f3e28e49976de8a2d779137e4',
    'rexruntime.dll': '088cbf2966636c58e27fceb74f109892c3f0906126eb30ef2ab449a6906c9c4e',
    'rexgpu-xenos.dll': '1c14b54b51540b47537d8617ce473f7b148f66609e6c9893396c80a6a1226876',
    'ffmpeg.dll': '68dd542c69763e8ceebedcc8eeaf3173bc14221d6ab08010575841513ad55229',
    'mspack.dll': 'fa48bfb0b688d2366cc4131b2cd98d3b1e1417a8c5d44448103bbbf61676bd97',
}
MARKER = 'Rayman3HD private delayed Combo manual playtest v1\n'


def safe_home():
    # Refuse junctions/symlinks anywhere in the destination, including user/save
    # subdirectories from an earlier session. Never copy an existing profile.
    for p in (HOME, *HOME.parents):
        if p.is_symlink() or (p.exists() and p.lstat().st_file_attributes & 0x400):
            raise RuntimeError(f'Redirected destination refused: {p}')
    if HOME.exists():
        if (HOME / 'owner.txt').read_text(encoding='utf-8') != MARKER:
            raise RuntimeError('Private home ownership marker differs')
        for directory, dirs, files in os.walk(HOME, followlinks=False):
            for name in dirs + files:
                p = Path(directory) / name
                if p.is_symlink() or p.lstat().st_file_attributes & 0x400:
                    raise RuntimeError(f'Redirected private data refused: {p}')


def configuration():
    safe_home()
    for name, expected in HASHES.items():
        if hashlib.sha256((BIN / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Pinned playable artifact mismatch: {name}')
    if (BIN / 'r3hd.toml').exists():
        raise RuntimeError('Unexpected runtime configuration beside private executable')
    data = (ROOT / 'private/extracted/5841123F').resolve(strict=True)
    for name in ('Gamedata', 'GAMEDATAbin', 'psm'):
        if not (data / name).is_dir():
            raise RuntimeError(f'Owned extracted game data missing {name}')
    return data


def environment():
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('R3HD_')}
    env.update(R3HD_PLAY='1', R3HD_TEST_COMBO_CLOSE='delayed-countdown',
               R3HD_TEST_COMBO_PLAYTEST='1', R3HD_DISCORD='off')
    return env


def arguments(data, session):
    return [str(BIN / 'r3hd.exe'), f'--game_data_root={data}',
            f'--user_data_root={HOME / "user"}', f'--cache_root={HOME / "cache"}',
            f'--log_file={session / "runtime.log"}', '--gpu_plugin=xenos',
            '--log_level=info', '--log_flush_interval=1', '--log_max_files=2',
            '--mnk_mode=true', '--fullscreen=false', '--window_width=1280',
            '--window_height=720', '--bind_settings=None', '--bind_debug_overlay=None',
            *resolve_keyboard(load_keymap())['args']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--manual', action='store_true')
    diagnostics = parser.add_mutually_exclusive_group()
    diagnostics.add_argument('--hud-diagnostic', choices=('off', 'delayed'),
                        help='private copied-profile comparison; bounded scoring-event captures')
    diagnostics.add_argument('--intro15-diagnostic', choices=('off', 'delayed'),
                             help='copy verified intro_15 save; capture first handless scoring event')
    args = parser.parse_args()
    intro15 = bool(args.intro15_diagnostic)
    args.hud_diagnostic = args.hud_diagnostic or args.intro15_diagnostic
    data = configuration()
    profile_source = HOME / 'user'
    if intro15:
        from m12_save_entry import load_entry, stored_profile_matches, find_saves, read_save_meta
        entry = load_entry('intro_15_human')
        profile_source = ROOT / 'private/saves/intro_15_human/profile'
        for p in (profile_source, *profile_source.parents, *profile_source.rglob('*')):
            if p.is_symlink() or p.lstat().st_file_attributes & 0x400:
                raise RuntimeError('Redirected intro_15 entry refused')
        slots = find_saves(profile_source)
        if (entry['level_key'] != 'intro_15' or not stored_profile_matches(entry)
                or len(slots) != 1 or read_save_meta(slots[0]) != (True, 'intro_15')):
            raise RuntimeError('Registered intro_15 source identity differs; launch refused')
    session = HOME / 'sessions' / (time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
    command, env = arguments(data, session), environment()
    if args.hud_diagnostic:
        from combo_hud_diagnostic import configure
        command, env = configure(command, env, session, args.hud_diagnostic)
        if intro15:
            env['R3HD_FRAME_TRACE'] = str(session / 'intro15.trace')
    assert '--mnk_mode=true' in command
    assert not any(k in env for k in ('R3HD_NONINTRUSIVE', 'R3HD_INPUT_SCHEDULE', 'R3HD_KEYMAP_TEST'))
    print('Private HUD diagnostic: Vanilla control (prototype OFF).' if args.hud_diagnostic == 'off'
          else 'Private playable Delayed Countdown (final one second).')
    writable_user = session / 'user' if args.hud_diagnostic else HOME / 'user'
    print(f'Executable: {BIN / "r3hd.exe"}\nSaves/profile: {writable_user}')
    if not args.hud_diagnostic:
        print('No existing saves are copied. This profile persists for later playtests.')
    if args.hud_diagnostic:
        print(f'DIAGNOSTIC: copies ONLY {profile_source} to a new session.')
        print('The source profile is read-only; diagnostic progress is disposable.')
        if not intro15:
            print('Load Game, repeat the same pickup in each mode. First four score increases: at most eight captures.')
    if intro15:
        print('INTRO_15 ONLY: Load Game / RAY. Wait through Murfy dropping Rayman until YOU can move.')
        print('While still handless, collect a visible jewel, then stop scoring for at least 3 seconds.')
        print('Watch Combo, then exit normally. First handless intro_15 score event: eight captures through expiry.')
        print('No scripted input. Loading this save includes the opening cinematic; it is not the tested event.')
    if args.check:
        print(json.dumps(dict(command=command, private_environment={k: v for k, v in env.items()
                           if k.startswith('R3HD_')}, hashes=HASHES), indent=2))
        print('COMBO_PLAYTEST_CHECK PASS (no game or writable data created)')
        return
    if subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq r3hd.exe', '/FO', 'CSV'],
                               text=True).lower().find('"r3hd.exe"') >= 0:
        raise RuntimeError('Close the other game before starting this private playtest')
    print('Use Load Game / RAY for intro_15. Normal keyboard/controller input.' if intro15
          else 'Use New Game on first launch, Load Game later. Normal keyboard/controller input.')
    print('Collect points, then stop scoring: watch the final-second upward slide.')
    input('Press Enter to launch visibly, or close this console to cancel: ')
    safe_home()
    if not HOME.exists():
        HOME.mkdir(parents=True)
        (HOME / 'owner.txt').write_text(MARKER, encoding='utf-8')
    for p in (HOME / 'user', HOME / 'cache', session):
        p.mkdir(parents=True, exist_ok=True)
    if args.hud_diagnostic:
        from combo_hud_diagnostic import profile_hashes
        before = profile_hashes(profile_source)
        shutil.copytree(profile_source, session / 'user')
        if before != profile_hashes(profile_source) or before != profile_hashes(session / 'user'):
            raise RuntimeError('Private source profile changed during diagnostic copy; launch refused')
        (session / 'source_profile_hashes.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
        if intro15:
            from m17_frame_trace import write_watch, TIMER_WATCH
            write_watch(session / 'intro15.trace', TIMER_WATCH + [
                (0x82C06221, 32), (0x40CDD5BC, 325), (0x8288D528, 0x134),
                (0x828A3E98, 0x5C), (0x8288B4D4, 4), (0x82837E9C, 8)])
    (session / 'launch.json').write_text(json.dumps(dict(command=command, hashes=HASHES,
        private_environment={k: v for k, v in env.items() if k.startswith('R3HD_')}), indent=2), encoding='utf-8')
    # User invocation only: no schedules or window APIs. Optional diagnostics
    # read only this child; the ordinary playable path has no memory observer.
    try:
        if args.hud_diagnostic:
            from combo_hud_diagnostic import start
            result = subprocess.Popen(command, cwd=session, env=env)
            stop, observer = start(session, result.pid, intro15=intro15)
            result.wait()
        else:
            result = subprocess.run(command, cwd=session, env=env, check=False)
    finally:
        if args.hud_diagnostic and 'observer' in locals():
            stop.set()
            observer.join(5)
    print(f'Game exited {result.returncode}. Private saves retained at {session / "user" if args.hud_diagnostic else HOME / "user"}')


if __name__ == '__main__':
    main()
