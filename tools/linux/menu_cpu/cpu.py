"""One attended normal Play.sh launch; read-only CPU counters, no gameplay automation."""
import argparse
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import time
import zipfile

import timing as T

try:
    import resource
except ImportError:
    resource = None

RETAINED = '92ea935c528694589dfdfee31d44e508ad17d014e9194457b34abb26bf6d8b64'
RUNNER_SEAL = 'd710dec30c88b83291ed9c0be9ac2254e33d08011314e2f5c903a682838504eb'
MODS = 'cfbde6f09a55295b1c182beddcd84bb174e70b2c0b16c246a992c5c69993fc41'
LOG = '6dbabb0d5261b12e96802cd5e11237a3322e17015d4044de93425a150c5fd45e'
SECONDS = 45
LIMIT = 900


def write(path, row):
    with path.open('x', encoding='utf-8') as f:
        json.dump(row, f, indent=2, sort_keys=True); f.write('\n')


def reason(error):
    return type(error).__name__ if isinstance(error, (OSError, subprocess.SubprocessError)) else str(error)


def native():
    T.need(sys.platform == 'linux' and os.getuid() != 0 and resource is not None, 'native nonroot Linux only')
    T.need('microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower(), 'WSL fixtures only')


def helpers():
    runner = Path.home() / 'Downloads/r3hd-normal-portable-01'
    seal = T.read_stable(runner / 'SHA256SUMS', 10000)
    T.need(T.digest(seal) == RUNNER_SEAL, 'original E-409 helper seal differs; preserve runner')
    expected = {'integration.py', 'checks.py', 'settings_core.py', 'registry.json', 'ABI_HASHES.json',
                'EVIDENCE_LOCK.json', 'HANDOFF.md', 'content_manifest.tsv'}
    seen = set()
    for line in seal.decode('ascii').splitlines():
        h, n = line.split('  ')
        T.need(n in expected and n not in seen, 'helper inventory'); seen.add(n)
        T.need(T.digest(T.read_stable(runner / n, 1000000)) == h, 'helper changed')
    T.need(seen == expected, 'helper missing')
    sys.path.insert(0, str(runner))
    module = importlib.import_module('integration')
    module.seal()  # Pure seal/environment functions only; never its old human controller.
    return module


def preflight():
    native()
    task = Path.home() / 'Projects/R3HD-noble-portable-01'
    out = Path.home() / 'Projects/R3HD-menu-cpu-01'
    T.need(not out.exists() and not out.is_symlink(), 'attempt/output exists; preserve it, no retry')
    T.need(out.parent.resolve() == out.parent, 'linked output parent')
    identity = T.authenticate(task)
    prior = Path.home() / 'Projects/R3HD-menu-evidence-01/menu-private-evidence.zip'
    T.need(T.digest(T.read_stable(prior, 1000000)) == RETAINED, 'retained evidence differs')
    home = task / 'portable'
    T.need(T.digest(T.read_stable(home / 'mods/state.json', 2000000)) == MODS, 'accepted mod state changed')
    sessions = sorted((home / 'sessions').iterdir())
    T.need(len(sessions) == 1 and sessions[0].resolve() == sessions[0], 'unexpected sessions; preserve and review')
    logs = sorted(sessions[0].glob('runtime*.log'))
    T.need(len(logs) == 1 and T.digest(T.read_stable(logs[0], 32000000)) == LOG, 'original log changed')
    I = helpers()
    T.need(I.snapshot(home)['installer'] is True, 'normal home no longer installed; no setup fallback')
    previous = T.strict(T.read_stable(home / 'installer.json', 2000000))
    payload = T.strict(T.read_stable(home / 'payload.json', 1000000))
    T.need(previous.get('distribution') == 'portable' and previous['payload_id'] == payload['payload_id'],
           'installed portable payload differs; no repair/setup fallback')
    T.need(T.digest(T.read_stable(home / 'data/content/Default.xex', 10000000)) ==
           '77a4df54340aebcc79eb0f0053938c03b8efd2efdd3ffee26c00fdfef3c6e8ca', 'existing game entry data differs')
    env = I.environment(task, I.session_metadata())
    T.need(not any(k.startswith('R3HD_') for k in env), 'no feature/probe overrides')
    T.need(shutil.disk_usage(out.parent).free >= 3000000000, 'need 3GB free; no disk changes')
    return task, out, I, env, identity, sessions, logs


def proc_stat(raw):
    # comm may contain spaces and parentheses: never trust it as identity.
    left = raw.index('('); end = raw.rindex(')')
    pid = int(raw[:left].strip()); f = raw[end + 2:].split()
    return {'id': pid, 'state': f[0], 'ppid': int(f[1]), 'group': int(f[2]),
            'ticks': int(f[11]) + int(f[12]), 'start': int(f[19])}


def proc(pid, base=Path('/proc')):
    p = base / str(pid)
    a = proc_stat((p / 'stat').read_text()); uid = (p / 'stat').stat().st_uid
    b = proc_stat((p / 'stat').read_text())
    T.need(a['id'] == b['id'] == pid and a['start'] == b['start'], 'PID changed')
    return {**b, 'uid': uid}


def game_identity(pid, executable, group, base=Path('/proc')):
    before = proc(pid, base); image = (base / str(pid) / 'exe').stat(); wanted = executable.stat()
    after = proc(pid, base)
    T.need(before['start'] == after['start'] and after['uid'] == os.getuid()
           and after['group'] == group and (image.st_dev, image.st_ino) == (wanted.st_dev, wanted.st_ino),
           'ambiguous game identity; STOP')
    return {'pid': pid, 'start': after['start'], 'group': group, 'dev': image.st_dev, 'ino': image.st_ino}


def find_game(root, start, executable):
    queue = [root]; seen = set(); games = []
    while queue:
        pid = queue.pop()
        if pid in seen: continue
        seen.add(pid); T.need(len(seen) <= 32, 'owned descendant bound')
        try:
            row = proc(pid)
            T.need(row['uid'] == os.getuid() and row['group'] == root, 'owned descendant changed identity')
            if pid == root: T.need(row['start'] == start, 'launcher PID reused')
            image = Path('/proc', str(pid), 'exe').stat()
            target = executable.stat()
            if (image.st_dev, image.st_ino) == (target.st_dev, target.st_ino):
                games.append(game_identity(pid, executable, root))
            children = Path('/proc', str(pid), 'task', str(pid), 'children').read_text().split()
            T.need(proc(pid)['start'] == row['start'], 'descendant PID reused')
            queue.extend(int(n) for n in children)
        except FileNotFoundError:
            continue  # Exited descendant, never a protected unrelated desktop helper.
    T.need(len(games) <= 1, 'multiple owned games')
    return games[0] if games else None


def sample(identity, executable):
    read_started = time.monotonic()
    current = game_identity(identity['pid'], executable, identity['group'])
    T.need(current == identity, 'game PID/image replaced')
    base = Path('/proc', str(identity['pid']))
    process = proc(identity['pid']); threads = {}; missing = []
    entries = sorted((base / 'task').iterdir())
    T.need(len(entries) <= 256, 'thread bound')
    for p in entries:
        tid = int(p.name)
        try:
            a = proc_stat((p / 'stat').read_text()); b = proc_stat((p / 'stat').read_text())
            T.need(a['id'] == b['id'] == tid and a['start'] == b['start'], 'thread identity raced')
            threads[str(tid) + ':' + str(b['start'])] = {'ticks': b['ticks'], 'state': b['state']}
        except (FileNotFoundError, PermissionError):
            missing.append(tid)  # Explicit incomplete sample, never silently certified complete.
    T.need(game_identity(identity['pid'], executable, identity['group']) == identity, 'game changed during sample')
    finished = time.monotonic()
    return {'monotonic': finished, 'counter_read_seconds': finished - read_started,
            'wall': datetime.now().astimezone().isoformat(),
            'process_ticks': process['ticks'], 'threads': threads, 'unreadable_or_exited_tids': missing}


def deltas(a, b, hz):
    dt = b['monotonic'] - a['monotonic']; T.need(dt > 0 and hz > 0, 'counter clock')
    total = b['process_ticks'] - a['process_ticks']; T.need(total >= 0, 'process CPU counter regressed')
    common = set(a['threads']) & set(b['threads']); cpu = {}
    for key in common:
        n = b['threads'][key]['ticks'] - a['threads'][key]['ticks']; T.need(n >= 0, 'thread CPU regressed')
        cpu[key] = 100 * n / hz / dt
    return {'seconds': dt, 'process_one_core_percent': 100 * total / hz / dt,
            'thread_one_core_percent': cpu, 'new_threads': sorted(set(b['threads']) - common),
            'ended_threads': sorted(set(a['threads']) - common)}


def backup_profiles(home, out):
    src = home / 'profiles'; rows = []; total = 0
    T.need(src.resolve() == src and src.is_dir(), 'existing private test profiles required')
    for path in sorted(src.rglob('*')):
        T.need(path.resolve() == path and not path.is_symlink(), 'linked profile input')
        if path.is_dir(): continue
        raw = T.read_stable(path, 64000000); total += len(raw)
        T.need(total <= 64000000 and len(rows) < 512, 'profile backup bound')
        dest = out / 'profile-backup-local' / path.relative_to(src); dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as f: f.write(raw)
        shutil.copystat(path, dest, follow_symlinks=False)
        T.need(T.digest(dest.read_bytes()) == T.digest(raw), 'profile backup verification')
        rows.append({'size': len(raw), 'sha256': T.digest(raw)})
    return {'files': len(rows), 'bytes': total, 'verified': True, 'content': 'PRIVATE LOCAL BACKUP; NOT EXPORTED'}


class Guard:
    def __init__(self, child, out, home, start):
        self.child = child; self.out = out; self.home = home; self.start = start
        self.deadline = time.monotonic() + LIMIT

    def check(self, allow_exit=False):
        T.need(time.monotonic() < self.deadline, '15-minute safety limit')
        if allow_exit and self.child.poll() is not None: return
        T.need(self.child.poll() is None, 'launcher exited before protocol finished')
        try: row = proc(self.child.pid)
        except FileNotFoundError:
            if allow_exit and self.child.poll() is not None: return
            raise
        T.need(row['start'] == self.start and row['group'] == self.child.pid and row['uid'] == os.getuid(), 'launcher changed')
        T.need(shutil.disk_usage(self.out).free >= 2000000000, '2GB disk floor')
        files = list((self.home / 'sessions').glob('*/runtime*.log')) + [self.out / 'console-local.txt']
        total = 0
        for f in files:
            T.need(f.resolve() == f and not f.is_symlink(), 'linked live log')
            total += f.stat().st_size
        T.need(total < 64000000, '64MB retained log ceiling')

    def delay(self, seconds):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            self.check(); time.sleep(min(.25, max(0, until - time.monotonic())))

    def prompt(self, phrase):
        print('When ready type ' + phrase + ': ', flush=True)
        while True:
            self.check()
            if select.select([sys.stdin], [], [], .25)[0]:
                T.need(sys.stdin.readline().strip() == phrase, 'phrase not confirmed; STOP without retry')
                return


def stop_owned(child, start):
    if child.poll() is not None: return []
    row = proc(child.pid)
    T.need(row['start'] == start and row['uid'] == os.getuid() and row['group'] == child.pid,
           'refuse signal: owned launcher identity unavailable')
    os.killpg(child.pid, signal.SIGTERM)
    try: child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        # Still our unreaped direct child; PID cannot be reused before wait/reap.
        os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=3)
        return ['SIGTERM', 'SIGKILL']
    return ['SIGTERM']


def run(task, out, I, env, identity, sessions, old_logs):
    out.mkdir(mode=0o700)
    receipt = {'owner': 'R3HD_MENU_CPU_01', 'program_identity': identity, 'windows': [],
               'helper_seal_sha256': RUNNER_SEAL, 'retained_evidence_sha256': RETAINED,
               'stop_reason': None, 'forced_reason': None, 'termination_actions': [],
               'script_exit': None, 'complete_comparison': False,
               'scope': 'CPU counters and vblank worker only; no displayed FPS/loop attribution'}
    child = None; start = None; target = None
    home = task / 'portable'; executable = home / 'bin/r3hd'
    try:
        receipt['profile_backup'] = backup_profiles(home, out)
        for name in ('settings.json', 'installer.json', 'mods/state.json'):
            raw = T.read_stable(home / name, 2000000)
            dest = out / 'configuration-backup-local' / name; dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as f: f.write(raw)
            T.need(T.digest(dest.read_bytes()) == T.digest(raw), 'configuration backup verification')
        receipt['configuration_backup'] = '3 files verified; private local only'
        write(out / 'before.json', receipt)
        def limits(): resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        with (out / 'console-local.txt').open('xb') as log:
            child = subprocess.Popen([str(home / 'Play.sh')], cwd=home, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=limits)
            start = proc(child.pid)['start']; guard = Guard(child, out, home, start)
            until = time.monotonic() + 120
            while target is None:
                guard.check(); T.need(time.monotonic() < until, '120s executable entry limit')
                target = find_game(child.pid, start, executable)
                if target is None: guard.delay(.25)
            receipt['process_identity'] = target; receipt['clock_ticks_per_second'] = os.sysconf('SC_CLK_TCK')
            for scene in ('MENU', 'GAMEPLAY'):
                print('Human only: reach ' + scene + ' naturally. No F4/settings/mod changes. '
                      'Return to terminal only to mark ready; then physically return to game within 8s. '
                      'Keep game focused for at least 75s by your own watch; no automated focus/sound/input.')
                guard.prompt(scene + ' READY'); points = []; completed = False
                try:
                    guard.delay(8); points.append(sample(target, executable))
                    for _ in range(SECONDS):
                        guard.delay(1); points.append(sample(target, executable))
                    T.need(points[-1]['monotonic'] - points[0]['monotonic'] < 60, 'excessive sampling overhead; STOP')
                    completed = True
                finally:
                    if points:
                        row = {'scene_human_label': scene, 'samples': points, 'window_complete': completed,
                               'thread_samples_complete': not any(p['unreadable_or_exited_tids'] for p in points),
                               'deltas': [deltas(a, b, receipt['clock_ticks_per_second']) for a, b in zip(points, points[1:])],
                               'focus': 'human must confirm; terminal switching can perturb focus/presentation'}
                        write(out / (scene.lower() + '.json'), row)
                receipt['windows'].append(scene)
                print(scene + ' window saved. Return physically to terminal when ready; no focus automation.', flush=True)
            guard.prompt('BOTH WINDOWS KEPT GAME FOCUSED')
            receipt['focus_confirmed_human'] = True
            print('Exit normally through the game now. No further progression/save action required. Return to this terminal after exit.', flush=True)
            while child.poll() is None:
                guard.check(allow_exit=True); time.sleep(.25)
            receipt['script_exit'] = child.returncode
            T.need(child.returncode == 0, 'normal launcher exit is nonzero')
            receipt['human_observations'] = {}
            for key in ('menu_slowdown_seen', 'gameplay_speed_looked_normal'):
                value = input(key + ' [yes/no/unknown]: ').strip().lower()
                T.need(value in ('yes', 'no', 'unknown'), 'invalid observation; preserve evidence')
                receipt['human_observations'][key] = value
            receipt['complete_comparison'] = True
    except (ValueError, OSError, KeyboardInterrupt) as e:
        receipt['stop_reason'] = 'HUMAN_INTERRUPT' if isinstance(e, KeyboardInterrupt) else reason(e)
    finally:
        if child is not None:
            try:
                if start is not None:
                    receipt['termination_actions'] = stop_owned(child, start)
                    if receipt['termination_actions']:
                        receipt['forced_reason'] = receipt['stop_reason'] or 'SUPERVISOR_CLEANUP'
            except (OSError, ValueError, subprocess.TimeoutExpired) as e:
                receipt['cleanup_uncertain'] = reason(e) + '; close only test windows yourself; no retry'
            receipt['script_exit'] = child.poll()
            if child.poll() is None:
                receipt['cleanup_uncertain'] = 'launcher still alive; close only test windows yourself, no retry'
            elif target is not None:
                try:
                    game_identity(target['pid'], executable, target['group'])
                except FileNotFoundError: pass
                except (OSError, ValueError):
                    receipt['cleanup_uncertain'] = 'game exit identity ambiguous; inspect/close test windows yourself'
                else:
                    receipt['cleanup_uncertain'] = 'game survived launcher; close only test window yourself'
        receipt['complete_comparison'] &= receipt['stop_reason'] is None and receipt['script_exit'] == 0 and 'cleanup_uncertain' not in receipt
        try:
            receipt['after_program_identity'] = T.authenticate(task)
            T.need(T.digest(T.read_stable(home / 'mods/state.json', 2000000)) == MODS, 'mod state changed')
            for f in old_logs: T.need(T.digest(T.read_stable(f, 32000000)) == LOG, 'old log changed')
            new = [p for p in (home / 'sessions').iterdir() if p not in sessions]
            T.need(len(new) == 1 and new[0].resolve() == new[0], 'new session ambiguous')
            logs = sorted(new[0].glob('runtime*.log')); T.need(1 <= len(logs) <= 3, 'new log inventory')
            receipt['new_retained_logs'] = []
            for f in logs:
                raw = T.read_stable(f, 32000000)
                receipt['new_retained_logs'].append({'sha256': T.digest(raw), 'size': len(raw), **T.analyze(raw)})
        except (ValueError, OSError) as e:
            receipt['integrity_or_log_review'] = reason(e); receipt['complete_comparison'] = False
        write(out / 'receipt.json', receipt)
        files = {n: (out / n).read_bytes() for n in ('before.json', 'receipt.json', 'menu.json', 'gameplay.json') if (out / n).is_file()}
        T.need(sum(map(len, files.values())) < 8000000, '8MB export ceiling; preserve local evidence')
        with zipfile.ZipFile(out / 'cpu-private-evidence.zip', 'x', zipfile.ZIP_DEFLATED) as z:
            for n, raw in files.items(): z.writestr(n, raw)
            z.writestr('SHA256SUMS', ''.join(T.digest(b) + '  ' + n + '\n' for n, b in sorted(files.items())))
        with (out / 'cpu-private-evidence.zip.sha256').open('x', encoding='ascii') as f:
            f.write(T.digest((out / 'cpu-private-evidence.zip').read_bytes()) + '  cpu-private-evidence.zip\n')
    print('R3HD_MENU_CPU EVIDENCE READY; measurement only, no causal/compatibility PASS')
    return 0 if receipt['complete_comparison'] else 2


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=('check', 'human'))
    p.add_argument('--human-present', action='store_true'); args = p.parse_args()
    context = preflight()
    if args.action == 'check': print('R3HD_MENU_CPU PREFLIGHT; NO GAME EXECUTION'); return 0
    T.need(args.human_present and sys.stdin.isatty(), 'human and realTTY required')
    print('One visible normal Play.sh launch, sound and configured controller outputs. Same private test profile; verified local backup before launch. No automated gameplay.')
    T.need(input('Type AUTHORIZE ONE MENU CPU COMPARISON: ') == 'AUTHORIZE ONE MENU CPU COMPARISON', 'not authorized')
    T.need(input('Type I CLOSED OTHER R3HD INSTANCES: ') == 'I CLOSED OTHER R3HD INSTANCES', 'close other games yourself')
    return run(*context)


if __name__ == '__main__':
    try: sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError) as e:
        print('R3HD_MENU_CPU STOP: ' + str(e), file=sys.stderr); sys.exit(2)
