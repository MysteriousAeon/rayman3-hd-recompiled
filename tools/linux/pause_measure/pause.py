"""One personally attended normal-launch pause/navigation capture; never unattended."""
import argparse
from datetime import datetime
import gzip
import json
import math
import os
from pathlib import Path
import select
import shutil
import signal
import stat
import subprocess
import sys
import time
import zipfile

import cpu as C
import review as R
T = C.T
VIDEO_LIMIT = 250 * 1024 * 1024
EXPECTED_LOGS = {C.LOG, '9a3c3defd944f494dfe7b99a7992b48e28071f9c510ef8424dfb77a40425eca2'}
PHASES = [(0, 'gameplay'), (10, 'escape_pause_idle'), (20, 'pause_navigation'),
          (35, 'pause_idle'), (45, 'resume_gameplay'), (55, 'sequence_end')]


class MediaPrivacyError(ValueError):
    pass


def command(args, timeout=15):
    return subprocess.run(args, check=True, capture_output=True, timeout=timeout).stdout


def tool_identity(path):
    T.need(path.resolve() == path and path.is_file(), 'tool path must be canonical regular file')
    s = path.stat()
    T.need(s.st_uid == 0 and not s.st_mode & 0o022 and s.st_mode & stat.S_IXUSR, 'untrusted system executable')
    return {'sha256': T.digest(T.read_stable(path, 128000000)), 'dev': s.st_dev, 'ino': s.st_ino}


def seal():
    here = Path(__file__).resolve().parent
    expected = {'pause.py', 'cpu.py', 'timing.py', 'review.py', 'HANDOFF.md'}
    seen = set()
    for line in T.read_stable(here / 'SHA256SUMS', 10000).decode('ascii').splitlines():
        h, n = line.split('  ')
        T.need(n in expected and n not in seen, 'toolkit inventory'); seen.add(n)
        T.need(T.digest(T.read_stable(here / n, 100000)) == h, 'toolkit file changed')
    T.need(seen == expected, 'toolkit incomplete')


def preflight():
    C.native(); seal()
    task = Path.home() / 'Projects/R3HD-noble-portable-01'
    out = Path.home() / 'Projects/R3HD-pause-measure-01'
    T.need(out.parent.resolve() == out.parent and not out.exists() and not out.is_symlink(),
           'attempt exists/linked parent; preserve and STOP')
    previous = Path.home() / 'Projects/R3HD-menu-cpu-01/cpu-private-evidence.zip'
    R.analyze(R.authenticate(previous))
    identity = T.authenticate(task); home = task / 'portable'
    T.need(T.digest(T.read_stable(home / 'mods/state.json', 2000000)) == C.MODS, 'mod state changed')
    sessions = sorted((home / 'sessions').iterdir())
    T.need(len(sessions) == 2 and all(p.resolve() == p and p.is_dir() for p in sessions), 'expected two retained sessions')
    logs = [p for s in sessions for p in sorted(s.glob('runtime*.log'))]
    hashes = {str(p): T.digest(T.read_stable(p, 32000000)) for p in logs}
    T.need(len(logs) == 2 and set(hashes.values()) == EXPECTED_LOGS, 'retained session provenance differs')
    I = C.helpers(); desktop = I.session_metadata(); env = I.environment(task, desktop)
    T.need(desktop['bus'], 'existing session bus required')
    T.need(not any(k.startswith('R3HD_') for k in env), 'feature/probe overrides refused')
    installed = T.strict(T.read_stable(home / 'installer.json', 2000000))
    payload = T.strict(T.read_stable(home / 'payload.json', 1000000))
    T.need(I.snapshot(home)['installer'] and installed['distribution'] == 'portable' and
           installed['payload_id'] == payload['payload_id'], 'installed payload differs; no setup fallback')
    T.need(T.digest(T.read_stable(home / 'data/content/Default.xex', 10000000)) ==
           '77a4df54340aebcc79eb0f0053938c03b8efd2efdd3ffee26c00fdfef3c6e8ca', 'existing game entry differs')
    T.need(command(['/usr/bin/pacman', '-Q', 'gpu-screen-recorder']).decode().strip() ==
           'gpu-screen-recorder 6.1.0-1.1', 'native recorder package changed; no guessing')
    recorder = tool_identity(Path('/usr/bin/gpu-screen-recorder'))
    probe = tool_identity(Path('/usr/bin/ffprobe'))
    raw = T.read_stable(Path('/usr/share/man/man1/gpu-screen-recorder.1.gz'), 1000000)
    manual = gzip.decompress(raw).decode().replace('\\-', '-')
    for option in ('-fm', 'vfr', 'mkv', '-encoder', '-fallback-cpu-encoding',
                   '-write-first-frame-ts', '-portal-session-token-filepath', '-restore-portal-session'):
        T.need(option in manual, 'required installed recorder documentation missing: ' + option)
    T.need(shutil.disk_usage(out.parent).free >= 3000000000, 'need 3GB headroom; do not relocate/delete')
    return task, out, env, identity, sessions, hashes, desktop, recorder, probe


def recorder_args(out):
    return ['/usr/bin/gpu-screen-recorder', '-w', 'portal', '-f', '60', '-fm', 'vfr', '-c', 'mkv',
            '-k', 'h264', '-encoder', 'gpu', '-fallback-cpu-encoding', 'no', '-bm', 'cbr', '-q', '12000',
            '-restore-portal-session', 'no', '-portal-session-token-filepath', str(out / 'portal-token-local'),
            '-write-first-frame-ts', 'yes', '-o', str(out / 'pause-private.mkv')]


def recorder_environment(out, desktop):
    # Separate recorder state, not another game home; real session bus/socket only.
    root = out / 'recorder-state-local'
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
           'HOME': str(root), 'XDG_CONFIG_HOME': str(root / 'config'),
           'XDG_CACHE_HOME': str(root / 'cache'), 'XDG_DATA_HOME': str(root / 'data'),
           'TMPDIR': str(root / 'tmp'), 'XDG_RUNTIME_DIR': os.environ['XDG_RUNTIME_DIR'],
           'XDG_SESSION_TYPE': 'wayland', 'XDG_CURRENT_DESKTOP': desktop['desktop'],
           'WAYLAND_DISPLAY': desktop['wayland'], 'DISPLAY': desktop['display']}
    T.need(desktop['bus'], 'existing session bus required')
    env['DBUS_SESSION_BUS_ADDRESS'] = desktop['bus']
    if desktop['xauth']: env['XAUTHORITY'] = desktop['xauth']
    for p in (root, root / 'config', root / 'cache', root / 'data', root / 'tmp'):
        p.mkdir(mode=0o700)
    return env


def first_timestamp(raw, spawned, now):
    lines = raw.decode('ascii').splitlines()
    T.need(len(lines) == 2 and lines[0].split() == ['monotonic_microsec', 'realtime_microsec'], 'first-frame timestamp header')
    values = lines[1].split(); T.need(len(values) == 2 and all(v.isdecimal() for v in values), 'first-frame timestamp values')
    mono, wall = [int(v) / 1000000 for v in values]
    T.need(spawned - 1 <= mono <= now + 1 and wall > 0, 'first-frame clock alignment invalid')
    return {'monotonic': mono, 'realtime': wall}


def media_metadata(out):
    video = out / 'pause-private.mkv'
    T.need(0 < video.stat().st_size <= VIDEO_LIMIT and video.resolve() == video, 'video missing/oversize/linked')
    base = ['/usr/bin/ffprobe', '-v', 'error', '-of', 'json']
    info = T.strict(command(base + ['-show_streams', '-show_format', str(video)]))
    streams = info['streams']
    if any(s.get('codec_type') == 'audio' for s in streams):
        raise MediaPrivacyError('unexpected audio stream; original clip stays local, no video export')
    T.need(len(streams) == 1 and streams[0]['codec_type'] == 'video' and streams[0]['codec_name'] == 'h264',
           'expected one H264 video stream and NO audio')
    T.need('matroska' in info['format']['format_name'], 'expected MKV')
    duration = float(info['format']['duration'])
    T.need(math.isfinite(duration) and 0 < duration <= 75, 'recorded duration exceeds bound/invalid')
    frames = T.strict(command(base + ['-select_streams', 'v:0', '-show_frames',
        '-show_entries', 'frame=best_effort_timestamp_time,pkt_duration_time', str(video)], timeout=60))['frames']
    T.need(2 <= len(frames) <= 5000, 'frame timestamp count')
    pts = [float(f['best_effort_timestamp_time']) for f in frames]
    T.need(all(math.isfinite(x) for x in pts) and all(b > a for a, b in zip(pts, pts[1:])), 'timestamps missing/nonmonotonic')
    T.need(pts[-1] - pts[0] <= 75, 'timestamp span exceeds bound')
    s = streams[0]
    tags = [str(v) for tags in (s.get('tags', {}), info['format'].get('tags', {})) for v in tags.values()]
    return {'bytes': video.stat().st_size, 'sha256': T.digest(T.read_stable(video, VIDEO_LIMIT)),
            'duration_seconds': duration, 'width': s['width'], 'height': s['height'], 'audio_streams': 0,
            'codec': 'h264', 'container': 'matroska', 'decoded_frame_pts_seconds': pts,
            'nvenc_tag_present': any('nvenc' in tag.lower() for tag in tags),
            'nominal_max_fps_requested': 60, 'physical_input_latency': 'UNKNOWN',
            'unique_game_frames_or_panel_fps': 'UNKNOWN; encoded frames are not unique game images',
            'guest_simulation_clock': 'UNKNOWN'}


class Supervisor:
    def __init__(self, game, out, home, target, start, row, stream):
        self.game = game; self.out = out; self.home = home; self.target = target
        self.guard = C.Guard(game, out, home, start); self.row = row; self.stream = stream
        self.next_sample = 0.; self.previous = None; self.rec = None; self.rec_start = None
        self.spawned = None; self.first = None; self.stopping = None; self.last_signal = None
        self.first_output = None

    def event(self, name):
        self.row['events'].append({'event': name, 'monotonic': time.monotonic(),
                                   'wall': datetime.now().astimezone().isoformat()})

    def signal_recorder(self, sig):
        if self.rec.poll() is not None: return
        C.game_identity(self.rec.pid, Path('/usr/bin/gpu-screen-recorder'), self.rec.pid)
        T.need(C.proc(self.rec.pid)['start'] == self.rec_start, 'recorder PID replaced; no signal')
        os.killpg(self.rec.pid, sig)
        self.row['recorder_signals'].append(signal.Signals(sig).name)
        self.last_signal = sig

    def request_stop(self):
        if self.stopping is None:
            self.stopping = time.monotonic(); self.signal_recorder(signal.SIGINT)

    def tick(self, allow_game_exit=False):
        self.guard.check(allow_exit=allow_game_exit)
        now = time.monotonic()
        if self.game.poll() is None and now >= self.next_sample:
            try: p = C.sample(self.target, self.home / 'bin/r3hd')
            except FileNotFoundError:
                if not allow_game_exit: raise
                # Guest can exit just before its normal Play.sh parent. Never invent zero CPU.
                self.row['cpu_exit_gap_observed'] = True
                return
            row = {'sample': p, 'deltas': C.deltas(self.previous, p, self.row['clock_ticks_per_second']) if self.previous else None}
            self.stream.write(json.dumps(row, sort_keys=True) + '\n'); self.stream.flush()
            self.previous = p; self.next_sample = time.monotonic() + 1
            T.need(self.stream.tell() < 16000000, 'CPU evidence bound')
        for n, bound in [('recorder-local.log', 4000000), ('pause-private.mkv', VIDEO_LIMIT)]:
            p = self.out / n
            if p.exists():
                T.need(p.resolve() == p and p.stat().st_size <= bound, 'capture/log output bound')
                if n.endswith('.mkv') and p.stat().st_size > 0 and self.first_output is None:
                    self.first_output = now
        if self.rec is not None:
            if self.first is None:
                p = self.out / 'pause-private.mkv.ts'
                if p.exists():
                    raw = T.read_stable(p, 1000)
                    # A newly created sidecar may not have its second line yet. No alternative clock is accepted.
                    if len(raw.splitlines()) >= 2:
                        self.first = first_timestamp(raw, self.spawned, now)
                        self.row['first_frame_timestamp'] = self.first; self.event('first_frame_timestamp_observed')
                T.need(now - self.spawned < 90, 'portal/first frame timeout; no fallback')
            if self.rec.poll() is None:
                clock = self.first['monotonic'] if self.first else self.first_output
                if clock is not None and now - clock >= 70 and self.stopping is None:
                    self.request_stop(); raise ValueError('capture safety time bound; partial evidence')
                if self.stopping is not None:
                    age = now - self.stopping
                    if age >= 4 and self.last_signal != signal.SIGKILL: self.signal_recorder(signal.SIGKILL)
                    elif age >= 3 and self.last_signal == signal.SIGINT: self.signal_recorder(signal.SIGTERM)
                    T.need(age < 5, 'recorder did not exit; cleanup uncertain')
            elif self.stopping is None:
                raise ValueError('recorder exited unexpectedly; no retry')

    def delay(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.tick(); time.sleep(min(.1, max(0., end - time.monotonic())))

    def answer(self, prompt, choices):
        print(prompt, flush=True)
        while True:
            self.tick()
            if select.select([sys.stdin], [], [], .1)[0]:
                value = sys.stdin.readline().strip()
                T.need(value in choices, 'answer not confirmed; STOP, no retry')
                return value


def export(out, row):
    C.write(out / 'receipt.json', row)
    names = ['receipt.json'] + [n for n in ('before.json', 'cpu.jsonl', 'media.json', 'recorder-local.log') if (out / n).exists()]
    files = {n: T.read_stable(out / n, 16000000) for n in names}
    T.need(len(files.get('recorder-local.log', b'')) <= 4000000, 'recorder diagnostic export bound')
    T.need(sum(map(len, files.values())) <= 20000000, 'metadata export bound')
    video = out / 'pause-private.mkv'
    if (video.exists() and row.get('recorder_exit') is not None and 'recorder_cleanup_uncertain' not in row
            and row.get('human', {}).get('window_only_selection') is True and not row.get('media_privacy_hold')):
        files['pause-private.mkv'] = T.read_stable(video, VIDEO_LIMIT)
        if 'media.json' in files:
            T.need(T.strict(files['media.json'])['sha256'] == T.digest(files['pause-private.mkv']), 'video changed after validation')
    p = out / 'pause-private-evidence.zip'
    with zipfile.ZipFile(p, 'x', zipfile.ZIP_DEFLATED) as z:
        for n, raw in files.items():
            z.writestr(n, raw, compress_type=zipfile.ZIP_STORED if n.endswith('.mkv') else zipfile.ZIP_DEFLATED)
        z.writestr('SHA256SUMS', ''.join(T.digest(raw) + '  ' + n + '\n' for n, raw in sorted(files.items())))
    Path(str(p) + '.sha256').write_text(T.digest(p.read_bytes()) + '  ' + p.name + '\n', encoding='ascii')
    # Original video/recorder diagnostics are private evidence. Game logs/tokens/settings/saves stay local.


def run(task, out, env, identity, sessions, old_hashes, desktop, recorder, probe):
    out.mkdir(mode=0o700)
    row = {'owner': 'R3HD_PAUSE_MEASURE_01', 'identity': identity, 'recorder_identity': recorder,
           'ffprobe_identity': probe, 'events': [], 'recorder_signals': [], 'game_termination_actions': [],
           'stop_reason': None, 'protocol_complete': False, 'physical_input_latency': 'UNKNOWN',
           'native_preflight': 'maintainer reported E-415 metadata only; no prior encode/capture test',
           'human': {}, 'clock_ticks_per_second': os.sysconf('SC_CLK_TCK')}
    game = None; start = None; sup = None
    home = task / 'portable'
    try:
        row['profile_backup'] = C.backup_profiles(home, out)
        for n in ('settings.json', 'installer.json', 'mods/state.json'):
            raw = T.read_stable(home / n, 2000000); dest = out / 'config-backup-local' / n
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
            T.need(T.digest(dest.read_bytes()) == T.digest(raw), 'configuration backup verification')
        C.write(out / 'before.json', row)
        recenv = recorder_environment(out, desktop)
        def game_limits(): C.resource.setrlimit(C.resource.RLIMIT_CORE, (0, 0))
        def rec_limits():
            game_limits(); C.resource.setrlimit(C.resource.RLIMIT_FSIZE, (VIDEO_LIMIT, VIDEO_LIMIT))
        with (out / 'console-local.txt').open('xb') as log, (out / 'cpu.jsonl').open('x', encoding='utf-8') as stream:
            game = subprocess.Popen([str(home / 'Play.sh')], cwd=home, env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=game_limits)
            start = C.proc(game.pid)['start']; guard = C.Guard(game, out, home, start)
            target = None; until = time.monotonic() + 120
            while target is None:
                guard.check(); T.need(time.monotonic() < until, '120s executable entry limit')
                target = C.find_game(game.pid, start, home / 'bin/r3hd')
                if target is None: guard.delay(.1)
            row['game_identity'] = target; sup = Supervisor(game, out, home, target, start, row, stream)
            sup.event('cpu_sampling_start')
            sup.answer('Naturally reach gameplay; Escape -> pause idle -> discrete option navigation -> resume. '
                       'Then return to terminal: type OFF CONTROL DONE', {'OFF CONTROL DONE'})
            row['human']['off_before_slowdown'] = sup.answer('off_before_slowdown [yes/no/unknown]', {'yes', 'no', 'unknown'})
            sup.event('off_before_reported')
            sup.answer('Read the HANDOFF timeline first. Select ONLY the game window, NEVER a display. '
                       'After chooser closes, immediately return here (<8s) and type WINDOW ONLY READY; '
                       'then refocus game within5s and follow55s timeline by your watch. '
                       'Type AUTHORIZE WINDOW ONLY CAPTURE', {'AUTHORIZE WINDOW ONLY CAPTURE'})
            T.need(tool_identity(Path('/usr/bin/gpu-screen-recorder')) == recorder, 'recorder changed')
            with (out / 'recorder-local.log').open('xb') as rec_log:
                sup.spawned = time.monotonic(); sup.event('recorder_spawn_requested')
                sup.rec = subprocess.Popen(recorder_args(out), cwd=out, env=recenv, stdin=subprocess.DEVNULL,
                    stdout=rec_log, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=rec_limits)
                sup.rec_start = C.proc(sup.rec.pid)['start']
                while sup.first is None: sup.tick(); time.sleep(.05)
                sup.answer('Confirm you selected ONLY the game window: WINDOW ONLY READY', {'WINDOW ONLY READY'})
                T.need(time.monotonic() - sup.first['monotonic'] <= 8, 'window confirmation too late; preserve partial, no retry')
                row['human']['window_only_selection'] = True
                sup.delay(5); sup.event('planned_sequence_start'); sequence_start = time.monotonic()
                row['planned_phases'] = [{'offset_seconds': n, 'phase': phase} for n, phase in PHASES]
                while time.monotonic() - sequence_start < 55: sup.delay(.1)
                sup.event('planned_sequence_end'); sup.request_stop()
                while sup.rec.poll() is None: sup.tick(); time.sleep(.05)
                row['recorder_exit'] = sup.rec.returncode; sup.event('recorder_stopped')
            T.need(row['recorder_signals'] == ['SIGINT'], 'recorder required forced shutdown; preserve partial')
            T.need(row['recorder_exit'] in (0, 130), 'recorder exit unexpected; preserve partial media and STOP')
            sup.answer('Recorder is OFF. Reproduce Escape/pause navigation once more, resume; '
                       'return and type OFF AFTER DONE', {'OFF AFTER DONE'})
            sup.event('off_after_reported')
            for key in ('off_after_slowdown', 'on_slowdown', 'all_five_recorded_phases_done',
                        'game_focused_during_sequence', 'animation_looked_slow', 'input_felt_delayed',
                        'recording_changed_symptom', 'resume_gameplay_looked_normal'):
                row['human'][key] = sup.answer(key + ' [yes/no/unknown]', {'yes', 'no', 'unknown'})
            print('Exit normally through the game now; no further testing or retry.', flush=True)
            while game.poll() is None: sup.tick(allow_game_exit=True); time.sleep(.1)
            row['game_exit'] = game.returncode
            T.need(game.returncode == 0, 'game/normal launcher exit nonzero')
            T.need(tool_identity(Path('/usr/bin/ffprobe')) == probe, 'ffprobe changed')
            media = media_metadata(out); C.write(out / 'media.json', media)
            row['media_timestamp_validation'] = 'PASS; captured frames only, not panel FPS or physical latency'
            row['measurement_validity'] = ('SUITABLE_FOR_REVIEW; no causal/performance PASS'
                if all(row['human'][k] == 'yes' for k in ('all_five_recorded_phases_done', 'game_focused_during_sequence'))
                and row['human']['recording_changed_symptom'] == 'no' else 'INCONCLUSIVE; scene/focus/recording perturbation')
            row['protocol_complete'] = True
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, KeyboardInterrupt) as e:
        row['stop_reason'] = 'HUMAN_INTERRUPT' if isinstance(e, KeyboardInterrupt) else C.reason(e)
        if isinstance(e, MediaPrivacyError): row['media_privacy_hold'] = True
    finally:
        if sup is not None and sup.rec is not None:
            try:
                if sup.rec.poll() is None:
                    sup.request_stop()
                    # Cleanup remains bounded even after a game/protocol failure.
                    try: sup.rec.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        sup.signal_recorder(signal.SIGTERM)
                        try: sup.rec.wait(timeout=1)
                        except subprocess.TimeoutExpired: sup.signal_recorder(signal.SIGKILL); sup.rec.wait(timeout=1)
                row['recorder_exit'] = sup.rec.poll()
            except (OSError, ValueError, subprocess.SubprocessError) as e:
                row['recorder_cleanup_uncertain'] = C.reason(e)
        if game is not None:
            try:
                if start is not None: row['game_termination_actions'] = C.stop_owned(game, start)
                row['game_exit'] = game.poll()
                if row['game_exit'] is None: row['game_cleanup_uncertain'] = True
                elif sup is not None:
                    try: C.game_identity(sup.target['pid'], home / 'bin/r3hd', sup.target['group'])
                    except FileNotFoundError: pass
                    except (ValueError, OSError): row['game_cleanup_uncertain'] = 'guest exit identity ambiguous'
                    else: row['game_cleanup_uncertain'] = 'guest survived launcher; close only test window yourself'
            except (OSError, ValueError, subprocess.SubprocessError) as e:
                row['game_cleanup_uncertain'] = C.reason(e)
        try:
            row['after_identity'] = T.authenticate(task)
            T.need(row['after_identity'] == identity and T.digest(T.read_stable(home / 'mods/state.json', 2000000)) == C.MODS,
                   'program/settings/mod integrity changed')
            for n, h in old_hashes.items(): T.need(T.digest(T.read_stable(Path(n), 32000000)) == h, 'old log changed')
            new = [p for p in (home / 'sessions').iterdir() if p not in sessions]
            T.need(len(new) == 1 and new[0].resolve() == new[0], 'new session ambiguous')
            logs = sorted(new[0].glob('runtime*.log')); T.need(1 <= len(logs) <= 3, 'new log inventory')
            row['retained_log_metadata'] = []
            for p in logs:
                raw = T.read_stable(p, 32000000)
                row['retained_log_metadata'].append({'sha256': T.digest(raw), 'bytes': len(raw), **T.analyze(raw)})
        except (ValueError, OSError, KeyError) as e:
            row['after_review_error'] = C.reason(e); row['protocol_complete'] = False
        row['protocol_complete'] &= row['stop_reason'] is None and not any('cleanup_uncertain' in k for k in row)
        export(out, row)
    if not row['protocol_complete']:
        print('R3HD_PAUSE STOP: ' + str(row.get('stop_reason') or row.get('after_review_error') or 'incomplete/cleanup uncertain'), file=sys.stderr)
    print('R3HD_PAUSE EVIDENCE READY; private video/metadata only; no causal/performance PASS')
    return 0 if row['protocol_complete'] else 2


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=('check', 'human'))
    p.add_argument('--human-present', action='store_true'); args = p.parse_args()
    context = preflight()
    if args.action == 'check': print('R3HD_PAUSE PREFLIGHT; NO GAME OR RECORDER EXECUTION'); return 0
    T.need(args.human_present and sys.stdin.isatty(), 'person and realTTY required')
    for phrase in ('AUTHORIZE ONE ATTENDED PAUSE MEASUREMENT', 'I CLOSED OTHER GAMES AND RECORDERS'):
        T.need(input('Type ' + phrase + ': ') == phrase, 'not personally confirmed')
    return run(*context)


if __name__ == '__main__':
    try: sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as e:
        print('R3HD_PAUSE STOP: ' + C.reason(e), file=sys.stderr); sys.exit(2)
