"""Normal packaged portable integration. Preparation never launches UI/game; human command requires real TTY."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
import zipfile
try:
    import fcntl
    import resource
except ImportError:
    fcntl = None
    resource = None
import checks as C
import settings_core as S

HERE = Path(__file__).resolve().parent
OWNER = 'R3HD_NORMAL_PORTABLE_01'
PHASES = ('setup', 'settings', 'reopen', 'play', 'verify')
LIMIT = 1800
BUDGET = 96_000_000
PROVENANCE = '589fe24073b62719c0fce0c8b1e6d4ee769e166c84bbcf26ba3035bcfbc37762'


def root():
    return Path.home() / 'Projects/R3HD-noble-portable-01'


def source():
    return Path.home() / 'Projects/R3HD-baseline-noble-2d-01/installation/data/content'


def package():
    return Path.home() / ('Projects/R3HD-baseline-noble-2b-egl-01/' + C.REL + C.PACKAGE)


def native():
    C.need(sys.platform == 'linux' and platform.machine() == 'x86_64' and os.getuid() != 0 and fcntl is not None, 'native nonroot Linux x86-64 required')
    C.need('microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower(), 'WSL is fixture-only')


def seal():
    expected = {'integration.py', 'checks.py', 'EVIDENCE_LOCK.json', 'ABI_HASHES.json', 'settings_core.py', 'registry.json', 'content_manifest.tsv', 'HANDOFF.md'}
    rows = {}
    for line in (HERE / 'SHA256SUMS').read_text(encoding='ascii').splitlines():
        h, n = line.split('  ')
        C.need(n in expected and n not in rows, 'toolkit inventory')
        C.file_hash(HERE / n, h)
        rows[n] = h
    C.need(set(rows) == expected, 'toolkit files missing')


def workspace():
    p = root()
    C.need(p.resolve() == p and (p / 'OWNER.txt').read_text().strip() == OWNER, 'wrong/linked workspace')
    return p


def data_check(folder):
    C.need(folder.resolve() == folder and folder.is_dir(), 'real content source required')
    expected = {}
    for line in (HERE / 'content_manifest.tsv').read_text(encoding='utf-8').splitlines():
        n, size, h = line.split('\t')
        C.need(n.casefold() not in expected, 'manifest collision')
        expected[n.casefold()] = (int(size), h)
    actual = {}
    for f in folder.rglob('*'):
        C.need(not f.is_symlink() and f.resolve() == f, 'linked content')
        if f.is_file():
            n = f.relative_to(folder).as_posix().casefold()
            C.need(n in expected and n not in actual, 'unexpected/colliding content file')
            actual[n] = (f.stat().st_size, C.sha(f))
    C.need(actual == expected and len(actual) == 915, 'verified content mismatch')
    return {'files': len(actual), 'hashes': 'PASS; fixed manifest, no content exported'}


def programs(home):
    C.file_hash(package(), C.LOCK['package_sha256'])
    C.need((home / 'portable.json').resolve() == home / 'portable.json', 'linked manifest')
    original = C.package_files(package(), {n: {'sha256': h} for n, h in C.read_json((HERE / 'ABI_HASHES.json').read_bytes()).items()})
    manifest = C.read_json((home / 'portable.json').read_bytes())
    C.need(manifest == original and manifest['publishable'] is False, 'manifest differs from authenticated package')
    for n, row in manifest['files'].items():
        parts = C.PurePosixPath(n).parts
        C.need(n == '/'.join(parts) and not any(x in ('.', '..') for x in parts) and not C.PurePosixPath(n).is_absolute(), 'program path')
        f = home / n
        C.need(f.resolve() == f and not f.is_symlink() and f.stat().st_size == row['size'], 'program replaced/linked')
        C.file_hash(f, row['sha256'])
    # Bind the entire program manifest to the known package, not merely its own hashes.
    return manifest


def session_metadata():
    C.need(os.environ.get('XDG_SESSION_TYPE') == 'wayland' and os.environ.get('DISPLAY'), 'KDE Wayland plus XWayland DISPLAY required for packaged tkinter GUI')
    C.need(importlib.util.find_spec('tkinter') is not None, 'existing tkinter unavailable; STOP, do not install here')
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', ''))
    C.need(runtime.is_absolute() and runtime.resolve() == runtime and runtime.stat().st_uid == os.getuid(), 'owned host runtime required')
    wayland = Path(os.environ.get('WAYLAND_DISPLAY', ''))
    if not wayland.is_absolute():
        wayland = runtime / wayland
    pulse = runtime / 'pulse/native'
    for f in (wayland, pulse):
        C.need(f.resolve() == f and stat.S_ISSOCK(f.stat().st_mode) and f.stat().st_uid == os.getuid(), 'owned existing desktop socket required')
    auth = os.environ.get('XAUTHORITY')
    if not auth and (Path.home() / '.Xauthority').exists():
        auth = str(Path.home() / '.Xauthority')
    if auth:
        f = Path(auth)
        C.need(f.is_absolute() and f.resolve() == f and f.is_file() and f.stat().st_uid == os.getuid(), 'untrusted X authority path')
    return {'wayland': str(wayland), 'pulse': str(pulse), 'display': os.environ['DISPLAY'], 'xauth': auth,
            'bus': os.environ.get('DBUS_SESSION_BUS_ADDRESS'), 'desktop': os.environ.get('XDG_CURRENT_DESKTOP', 'KDE')}


def environment(p, desktop):
    home = p / 'os-home'
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
           'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(home / 'tmp'), 'XDG_SESSION_TYPE': 'wayland',
           'DISPLAY': desktop['display'], 'WAYLAND_DISPLAY': desktop['wayland'], 'XDG_CURRENT_DESKTOP': desktop['desktop'],
           'LD_LIBRARY_PATH': str(p / 'portable/bin'), 'SDL_AUDIO_DRIVER': 'pulseaudio',
           'PULSE_SERVER': 'unix:' + desktop['pulse'], 'PULSE_CLIENTCONFIG': str(home / 'pulse-client.conf'), 'DISABLE_LSFG': '1'}
    for key, leaf in [('XDG_DATA_HOME', 'data'), ('XDG_CONFIG_HOME', 'config'), ('XDG_CACHE_HOME', 'cache'), ('XDG_RUNTIME_DIR', 'run')]:
        env[key] = str(home / leaf)
    if desktop['xauth']:
        env['XAUTHORITY'] = desktop['xauth']
    if desktop['bus']:
        env['DBUS_SESSION_BUS_ADDRESS'] = desktop['bus']
    # No R3HD_* overrides, fake process hooks, SDL test inputs or feature-disable flags.
    return env


def prepare():
    native(); seal()
    desktop = session_metadata()  # Metadata/importability only; no Tk, SDL or audio initialization.
    p = root()
    C.need(p.parent.resolve() == p.parent and not p.exists() and not p.is_symlink(), 'fresh workspace required; preserve earlier attempts')
    C.need(shutil.disk_usage(p.parent).free >= 12_000_000_000, 'need 12,000,000,000 free bytes')
    evidence = Path.home() / 'Projects/R3HD-linux-provenance-01/provenance-private-evidence.zip'
    C.file_hash(evidence, PROVENANCE)
    C.file_hash(package(), C.LOCK['package_sha256'])
    before = data_check(source())
    p.mkdir(mode=0o700); (p / 'OWNER.txt').write_text(OWNER + '\n')
    home = p / 'portable'; home.mkdir()
    abi = {n: {'sha256': h} for n, h in C.read_json((HERE / 'ABI_HASHES.json').read_bytes()).items()}
    C.package_files(package(), abi, home)
    # Leave data/settings/installer state absent so actual packaged setup runs.
    os_home = p / 'os-home'; os_home.mkdir(mode=0o700)
    for n in ('tmp', 'data', 'config', 'cache', 'run'):
        (os_home / n).mkdir(mode=0o700)
    (os_home / 'pulse-client.conf').write_text('autospawn = no\nauto-connect-localhost = no\nauto-connect-display = no\n')
    env = environment(p, desktop)
    loaders = {}
    for n in C.COMPONENTS:
        with (p / (n + '.loader-local.txt')).open('x') as log:
            r = subprocess.run(['/lib64/ld-linux-x86-64.so.2', '--list', str(home / 'bin' / n)], env=env, stdin=subprocess.DEVNULL,
                               stdout=log, stderr=subprocess.STDOUT, timeout=20)
        C.need(r.returncode == 0 and 'not found' not in (p / (n + '.loader-local.txt')).read_text(), 'loader resolution failed')
        loaders[n] = {'exit': r.returncode, 'sha256': abi[n]['sha256']}
    programs(home)
    C.write(p / 'prepared.json', {'owner': OWNER, 'toolkit_sha256': C.sha(HERE / 'SHA256SUMS'), 'package_sha256': C.LOCK['package_sha256'], 'data': before, 'loaders': loaders,
                                'game_execution': 'NOT RUN', 'normal_setup': 'NOT RUN', 'content_source': str(source())})
    print('R3HD_PORTABLE_PREPARED; NO UI OR GAME EXECUTION')


def snapshot(home):
    settings = home / 'settings.json'
    if not settings.exists():
        return {'settings': 'ABSENT', 'installer': (home / 'installer.json').exists()}
    C.need(settings.resolve() == settings and settings.stat().st_size < 2_000_000, 'linked/oversized settings')
    j = C.read_json(settings.read_bytes())
    resolved = S.resolve_presets(S.load_registry(HERE / 'registry.json'), settings=j)
    state = home / 'mods/state.json'
    mods = {'entries': 0, 'enabled': 0, 'identity': None, 'selection_sha256': None}
    if state.exists():
        C.need(state.resolve() == state and not state.is_symlink() and state.stat().st_size < 2_000_000, 'linked/oversized mod state')
        row = C.read_json(state.read_bytes())
        C.need(isinstance(row, dict) and type(row.get('schema')) is int and row['schema'] == 1 and isinstance(row.get('mods'), list) and len(row['mods']) <= 1000, 'invalid mod state')
        selected = [(x['id'], x['enabled']) for x in row['mods']]
        C.need(all(isinstance(n, str) and re.fullmatch('[a-z0-9][a-z0-9._-]{1,63}', n) and type(e) is bool for n, e in selected), 'invalid mod selection')
        C.need(len({n for n, e in selected}) == len(selected), 'duplicate mod selection')
        mods = {'entries': len(selected), 'enabled': sum(e for n, e in selected), 'identity': C.sha(state),
                'selection_sha256': C.digest(json.dumps(selected, separators=(',', ':')).encode())}
    return {'settings': C.sha(settings), 'installer': (home / 'installer.json').is_file(), 'preset': resolved['preset'],
            'values': resolved['values'], 'mods': mods}


def log_files(p):
    # Only new test console/runtime logs, no other installation/session tree.
    return list((p / 'steps').glob('*/console-local.txt')) + list((p / 'portable/sessions').glob('*/runtime*.log'))


def supervise(args, p, step, env):
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    with (step / 'console-local.txt').open('x') as log:
        child = subprocess.Popen(list(map(str, args)), cwd=p / 'portable', env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True, preexec_fn=limits)
        C.write(step / 'process-local.json', {'pid': child.pid, 'group': child.pid})
        started = time.monotonic(); reason = None; seen = {}; growth = 0
        try:
            while child.poll() is None:
                if time.monotonic() - started >= LIMIT: reason = 'SAFETY_TIME_LIMIT'; break
                for f in log_files(p):
                    C.need(f.resolve() == f and not f.is_symlink(), 'linked log')
                    key = (f.stat().st_dev, f.stat().st_ino); size = f.stat().st_size
                    growth += max(0, size - seen.get(key, 0)); seen[key] = size
                if growth >= BUDGET: reason = 'LOG_BUDGET'; break
                if shutil.disk_usage(p).free < 2_000_000_000: reason = 'LOW_DISK'; break
                time.sleep(.25)
        except KeyboardInterrupt:
            reason = 'HUMAN_INTERRUPT'
        finally:
            if child.poll() is None:
                reason = reason or 'SUPERVISOR_EXCEPTION'
                try: os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError: pass
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    child.wait()
            try: os.killpg(child.pid, 0)
            except ProcessLookupError: pass
            else:
                reason = reason or 'REMAINING_OWNED_GROUP'
                try: os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError: pass
    return {'exit': child.returncode, 'forced_reason': reason, 'log_growth_bytes': growth}


def ask(text):
    value = input(text + ' [yes/no/not-exercised]: ').strip()
    C.need(value in ('yes', 'no', 'not-exercised'), 'invalid observation; preserve attempt')
    return value


QUESTIONS = {'subtitles': 'Personally saw voice subtitles during gameplay OUTSIDE cutscenes (game Subtitles On)?',
             'combo': 'Personally saw the restored smooth final-second Combo meter exit?',
             'dualsense_input': 'Personally used the connected DualSense to control the game?',
             'dualsense_light': 'Personally saw the configured DualSense light-bar response (not just a pre-existing LED)?',
             'dualsense_trigger': 'Personally felt the configured R2 adaptive resistance?',
             'dualsense_speaker': 'Personally heard a supported cue FROM THE CONTROLLER speaker, separately from desktop sound?'}


def launch_plan(p):
    home = p / 'portable'
    plans = list((home / 'sessions').glob('*/session.json'))
    if len(plans) != 1:
        return {'count': len(plans), 'contract_verified': False}
    f = plans[0]
    C.need(f.resolve() == f and f.stat().st_size < 2_000_000, 'linked/oversized launch plan')
    plan = C.read_json(f.read_bytes())
    values = plan['settings']['values']; env = plan['env']; args = plan['arguments']
    reg = S.load_registry(HERE / 'registry.json')['settings']
    C.need(set(values) == set(reg) and all(v in reg[k]['values'] for k, v in values.items()), 'invalid launch selections')
    mapping = {'R3HD_COMBO_CLOSE': 'combo_close', 'R3HD_GAMEPLAY_SUBTITLES': 'gameplay_subtitles',
               'R3HD_DS_LIGHT': 'dualsense_light', 'R3HD_DS_TRIGGER': 'dualsense_trigger', 'R3HD_DS_SPEAKER': 'dualsense_speaker'}
    flags = {'home_executable': plan['executable'] == str(home / 'bin/r3hd'), 'installed_home': plan['installed'] is True,
             'home_settings': plan['settings']['file'] == str(home / 'settings.json'),
             'F4_home': env.get('R3HD_PCSET_HOME') == str(home),
             'SDK_overlays_suppressed': all(x in args for x in ('--bind_settings=None', '--bind_debug_overlay=None')),
             'isolated_data_user_cache': all(x in args for x in ('--game_data_root=' + str(home / 'data/content'),
                    '--user_data_root=' + str(home / 'profiles/default/user'), '--cache_root=' + str(home / 'cache'))),
             'feature_mapping': all(env.get(k) == values[v] for k, v in mapping.items()),
             'normal_progression': not any('level:' in a or '--level=' in a for a in args)}
    return {'count': 1, 'contract_verified': all(flags.values()), 'checks': flags, 'selected_values': values,
            'mod_plan_selected': bool(env.get('R3HD_MODS_PLAN')), 'raw_paths_bindings_mod_ids': 'NOT EXPORTED'}


def machine(p):
    texts = []
    for f in log_files(p):
        C.need(f.resolve() == f and not f.is_symlink() and f.stat().st_size <= 128_000_000, 'log size/link')
        texts.append(f.read_text(errors='replace'))
    text = '\n'.join(texts)
    benign = re.compile(r'^\[[^\]\r\n]+\] \[error\] \[fs\] \[t[0-9]+\] ResolvePath\(\\D:\\Gamedata\) failed - device not found$')
    markers = ['M2 launch_prepared', 'M2 runtime_initialized', 'VulkanPresenter: Created', 'SDL video driver: wayland',
               'ComboClose profile_mode=delayed', 'M44 gameplay_subtitles mode=all state=applied', 'R3HD pcset saved',
               'R3HD dualsense light=set', 'R3HD dualsense trigger=written', 'R3HD ds_speaker endpoint=opened',
               'R3HD pcset open persistence=home']
    return {'markers': {s: s in text for s in markers}, 'launch_plan': launch_plan(p), 'audio_endpoints': text.count('audio endpoint '),
            'gpu_present_debug_records': text.count('XELOG_GPU PRESENT:'),
            'guest_fatal': 'R6025' in text or 'import=__imp__KeBugCheck' in text,
            'device_lost': 'VK_ERROR_DEVICE_LOST' in text, 'audio_open_failures': text.count('SDL_OpenAudioDeviceStream() failed:'),
            'unexpected_error_lines': sum(('[error]' in line.lower() or '[critical]' in line.lower()) and not benign.fullmatch(line) for line in text.splitlines()),
            'speaker_submissions': sum('ds_speaker' in line and 'output=submitted' in line for line in text.splitlines()),
            'warning_lines': text.count('[warning]'),
            'log_scope': 'retained normal logs only; standard rotation may discard startup/API records; no complete-history absence proof',
            'host_present_pacing': 'NOT MEASURED; no D3D12-only/DEBUG marker gate'}


def results(steps, m, obs):
    clean = all(x['exit']['exit'] == 0 and x['exit']['forced_reason'] is None for x in steps.values()) and not m['guest_fatal'] and not m['device_lost'] and not m['unexpected_error_lines']
    gate = lambda keys, extra=True: 'PASS' if extra and all(obs.get(k) == 'yes' for k in keys) else 'NOT ESTABLISHED'
    stable = lambda a, b: a.get('values') == b.get('values') and a.get('preset') == b.get('preset')
    plan_ok = m['launch_plan']['contract_verified'] and m['launch_plan']['selected_values'] == steps['play']['before']['values']
    selected = m['launch_plan'].get('selected_values', {})
    return {'setup': gate(['setup_gui', 'finish_no_game'], steps['setup']['after']['installer']),
            'settings_persistence': gate(['preferences_saved', 'preferences_reopened'], stable(steps['settings']['after'], steps['reopen']['before']) and stable(steps['reopen']['before'], steps['reopen']['after'])),
            'mods_tab': gate(['mods_tab']),
            'mods_configuration_persistence': gate(['mods_persisted'], steps['settings']['after']['mods']['entries'] > 0 and steps['settings']['after']['mods']['selection_sha256'] == steps['reopen']['after']['mods']['selection_sha256']),
            'mod_runtime_application': gate(['mod_applied'], m['launch_plan'].get('mod_plan_selected', False)),
            'launch_configuration': 'PASS' if plan_ok else 'NOT ESTABLISHED',
            'normal_play': gate(['menu', 'basic_gameplay', 'audio_clear'], plan_ok and clean and not m['audio_open_failures']),
            'F3_F4': gate(['f3_correct', 'f4_panel', 'f4_persisted'], plan_ok and steps['play']['before'].get('values') != steps['play']['after'].get('values') and stable(steps['play']['after'], steps['verify']['after'])),
            'subtitles': gate(['subtitles'], plan_ok and selected.get('gameplay_subtitles') == 'all'),
            'combo_restoration': gate(['combo'], plan_ok and selected.get('combo_close') == 'delayed'),
            'dualsense_detection': gate(['dualsense_input']),
            'dualsense_light': gate(['dualsense_light'], plan_ok and selected.get('dualsense_light') == 'on'),
            'dualsense_trigger': gate(['dualsense_trigger'], plan_ok and selected.get('dualsense_trigger') == 'on'),
            'dualsense_speaker': gate(['dualsense_speaker'], plan_ok and selected.get('dualsense_speaker') == 'on'),
            'normal_exit': gate(['normal_exit'], clean), 'runtime_clean': clean,
            'evidence_labels': {'normal_play': 'authenticated launch plan + human content/actions/audio + script exits',
                                'subtitles_combo_devices': 'human observations + actual selected launch configuration; retained API logs corroborate only',
                                'F4': 'human F4 operation + changed resolved settings + Settings restart persistence',
                                'runtime_clean': 'all script exits and retained log flags only, not complete-history certification'},
            'menu_slowdown': 'OPEN; reported issue retained regardless of smoke observations',
            'save_reload_full_game_SteamOS_Deck_performance_resolution': 'OUT OF SCOPE / UNKNOWN',
            'overall': 'NO AGGREGATE PASS; independent integration/device/mod observations'}


def human(present):
    native(); seal()
    C.need(present and sys.stdin.isatty(), 'realTTY and --human-present required')
    p = workspace(); home = p / 'portable'
    C.need((p / 'prepared.json').is_file() and not (p / 'steps').exists(), 'prepared one-attempt workspace required; never repeat')
    C.need(C.read_json((p / 'prepared.json').read_bytes())['toolkit_sha256'] == C.sha(HERE / 'SHA256SUMS'), 'prepared toolkit differs; preserve workspace')
    C.need(shutil.disk_usage(p).free >= 4_000_000_000, 'need 4,000,000,000 free bytes')
    desktop = session_metadata(); env = environment(p, desktop)
    print('Human only: visible setup/Settings/game, sound, physical input, DualSense LED/trigger/speaker outputs when enabled. Close all other games/Settings yourself. No automation. Each window must close before continuing. Do not click Play from setup/Settings; launch only at the documented Play stage.')
    C.need(input('Type AUTHORIZE NORMAL PORTABLE INTEGRATION: ') == 'AUTHORIZE NORMAL PORTABLE INTEGRATION', 'not authorized')
    C.need(input('Type I CLOSED OTHER R3HD INSTANCES: ') == 'I CLOSED OTHER R3HD INSTANCES', 'external-game attestation required')
    with (p / 'task.lock').open('x+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        (p / 'steps').mkdir(); steps = {}; obs = {}
        for phase in PHASES:
            programs(home)
            if phase == 'setup':
                C.need(not (home / 'settings.json').exists() and not (home / 'installer.json').exists() and not (home / 'data').exists(), 'setup must be genuinely fresh')
                print('SETUP: Settings.sh. Choose Folder: ' + str(source()) + '. Select HD+. Uncheck menu entry (isolated XDG regardless). Finish with neither Play nor Settings; close setup.')
            elif phase == 'settings':
                print('SETTINGS: use HD+. Save one recognizable preference change. Confirm Mods tab; optionally use a personally supplied authorized mod in this test home only. Do not click Play. Speaker is opt-in: enable only if you want/authorize its separate test. Close.')
            elif phase == 'reopen':
                print('REOPEN: verify saved preference and Mods selections. Do not change them; close. Do not click Play or change menu entries.')
            elif phase == 'verify':
                print('VERIFY: Settings.sh after game exit. Confirm the F4 preference saved in-game is visible here; do not change it. Close Settings. This is not a save/reload test.')
            else:
                print('PLAY: actual Play.sh. Turn ON the game own Subtitles option through its normal menu; Gameplay subtitles preference alone does not enable it. Human New Game/ordinary play only. Check F3 has no SDK overlay; F4 PC Settings opens, change/save one preference. Observe subtitles/Combo when naturally available. Observe each connected DualSense output separately. No required level/save deadline. Exit normally; 30min safety ceiling. Unknown/unreached events stay not-exercised.')
                C.need(input('Type AUTHORIZE PLAY AND CONFIGURED DEVICE OUTPUTS: ') == 'AUTHORIZE PLAY AND CONFIGURED DEVICE OUTPUTS', 'play/device outputs not authorized')
            C.need(input('Type START ' + phase.upper() + ': ') == 'START ' + phase.upper(), 'stage not authorized')
            step = p / 'steps' / phase; step.mkdir()
            before = snapshot(home)
            C.write(step / 'before.json', before)
            exit_row = supervise([home / ('Play.sh' if phase == 'play' else 'Settings.sh')], p, step, env)
            C.write(step / 'exit.json', exit_row)
            programs(home)
            after = snapshot(home)
            C.write(step / 'after.json', after)
            steps[phase] = {'before': before, 'after': after, 'exit': exit_row}
            keys = {'setup': ['setup_gui', 'finish_no_game'], 'settings': ['preferences_saved', 'mods_tab'],
                    'reopen': ['preferences_reopened', 'mods_persisted'], 'verify': ['f4_persisted'],
                    'play': ['menu', 'basic_gameplay', 'audio_clear', 'f3_correct', 'f4_panel', 'subtitles', 'combo', 'mod_applied', 'dualsense_input', 'dualsense_light', 'dualsense_trigger', 'dualsense_speaker', 'normal_exit', 'slowdown_seen']}[phase]
            for key in keys: obs[key] = ask(QUESTIONS.get(key, key.replace('_', ' ')))
            C.write(step / 'observations.json', {key: obs[key] for key in keys})
            # A bad exit must not erase what the person actually saw/heard. Record,
            # then STOP before the next script; these answers never override exit failure.
            C.need(exit_row['exit'] == 0 and exit_row['forced_reason'] is None, 'script failed/stopped; preserve, no fallback/retry')
            if phase in ('setup', 'settings', 'reopen'):
                C.need(not list((home / 'sessions').glob('*/session.json')), 'unexpected game launch before Play stage; STOP')
        C.write(p / 'observations.json', obs)
        measured = machine(p)
        C.write(p / 'machine.json', measured)
        C.write(p / 'results.json', results(steps, measured, obs))
    print('R3HD_PORTABLE_RECORDED; independent results, no blanket compatibility PASS')


def collect():
    native(); seal(); p = workspace()
    dest = p / 'portable-private-evidence.zip'
    C.need(not dest.exists() and not Path(str(dest) + '.sha256').exists(), 'evidence exists; preserve it')
    C.need(sys.stdin.isatty() and input('Type TEST WINDOWS ARE CLOSED: ') == 'TEST WINDOWS ARE CLOSED', 'close only test windows yourself before collection')
    integrity = {}
    for label, check in [('programs', lambda: programs(p / 'portable')), ('source', lambda: data_check(source()))]:
        try: check(); integrity[label] = 'PASS'
        except (ValueError, OSError): integrity[label] = 'STOP_UNVERIFIED; preserve artifacts'
    files = {}
    for n in ('prepared.json', 'observations.json', 'machine.json', 'results.json'):
        if (p / n).is_file():
            C.need((p / n).resolve() == p / n and not (p / n).is_symlink(), 'linked receipt')
            row = C.read_json((p / n).read_bytes())
            if n == 'prepared.json': row.pop('content_source', None)
            files[n] = (json.dumps(row, indent=2, sort_keys=True) + '\n').encode()
    for phase in PHASES:
        for n in ('before.json', 'after.json', 'exit.json', 'observations.json'):
            f = p / 'steps' / phase / n
            if f.is_file():
                C.need(f.resolve() == f and not f.is_symlink(), 'linked stage receipt')
                files[phase + '/' + n] = f.read_bytes()
    try: current_machine = machine(p)
    except (ValueError, OSError, KeyError, TypeError): current_machine = {'status': 'STOP_UNVERIFIED_LOGS; raw logs remain native'}
    files['collection.json'] = (json.dumps({'integrity': integrity, 'machine_at_collection': current_machine,
                                            'completed_steps': [n for n in PHASES if (p / 'steps' / n / 'after.json').is_file()],
                                            'scope': 'private portable integration; no blanket gameplay/Deck acceptance'}) + '\n').encode()
    files['SHA256SUMS'] = ''.join(C.digest(b) + '  ' + n + '\n' for n, b in sorted(files.items())).encode()
    with zipfile.ZipFile(dest, 'x', zipfile.ZIP_DEFLATED) as z:
        for n, b in files.items(): z.writestr(n, b)
    Path(str(dest) + '.sha256').write_text(C.sha(dest) + '  ' + dest.name + '\n', encoding='ascii')
    print('R3HD_PORTABLE_EVIDENCE READY; raw logs/data/saves/profiles remain native')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('check', 'prepare', 'human', 'collect'))
    p.add_argument('--human-present', action='store_true')
    try:
        a = p.parse_args()
        if a.action == 'check': seal(); print('R3HD_PORTABLE_TOOLKIT PASS; NO GAME EXECUTION')
        elif a.action == 'prepare': prepare()
        elif a.action == 'human': human(a.human_present)
        else: collect()
    except (ValueError, KeyError, OSError, S.Refused, subprocess.SubprocessError) as e:
        raise SystemExit('R3HD_PORTABLE STOP: ' + str(e) + '; preserve workspace, no retry/fallback')
