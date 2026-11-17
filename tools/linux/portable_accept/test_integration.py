"""Synthetic only: no target, SDL, Tk, physical input/audio or launcher execution."""
import atexit
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile
import build_bundle as B

BOOT = tempfile.TemporaryDirectory()
atexit.register(BOOT.cleanup)
BOOTROOT = Path(BOOT.name).resolve()
B.build(BOOTROOT / 'kit')
with zipfile.ZipFile(BOOTROOT / 'kit/r3hd-normal-portable.zip') as z:
    z.extractall(BOOTROOT / 'runner')  # Only our freshly built, trusted synthetic kit.
sys.path.insert(0, str(BOOTROOT / 'runner'))
import integration as I
C = I.C


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def m(self):
        keys = ['M2 launch_prepared', 'M2 runtime_initialized', 'VulkanPresenter: Created', 'M44 gameplay_subtitles mode=all state=applied',
                'ComboClose profile_mode=delayed', 'R3HD pcset saved', 'R3HD dualsense light=set', 'R3HD dualsense trigger=written']
        values = {'display': 'windowed', 'combo_close': 'delayed', 'gameplay_subtitles': 'all', 'dualsense_light': 'on', 'dualsense_trigger': 'on', 'dualsense_speaker': 'on'}
        return {'markers': dict.fromkeys(keys, True), 'launch_plan': {'contract_verified': True, 'selected_values': values, 'mod_plan_selected': True}, 'guest_fatal': False, 'device_lost': False, 'unexpected_error_lines': 0,
                'audio_endpoints': 2, 'audio_open_failures': 0, 'speaker_submissions': 1}

    def steps(self):
        mods = {'entries': 1, 'selection_sha256': 'a', 'identity': 'serialized'}
        values = dict(self.m()['launch_plan']['selected_values'], display='fullscreen')
        s = {'settings': 'a', 'installer': True, 'preset': 'hdplus', 'values': values, 'mods': mods}
        rows = {n: {'before': copy.deepcopy(s), 'after': copy.deepcopy(s), 'exit': {'exit': 0, 'forced_reason': None}} for n in I.PHASES}
        rows['play']['before']['values'] = dict(values, display='windowed')
        return rows

    def observations(self):
        return dict.fromkeys(['setup_gui', 'finish_no_game', 'preferences_saved', 'preferences_reopened', 'mods_tab', 'mods_persisted',
                              'menu', 'basic_gameplay', 'audio_clear', 'f3_correct', 'f4_panel', 'f4_persisted', 'subtitles', 'combo',
                              'dualsense_input', 'dualsense_light', 'dualsense_trigger', 'dualsense_speaker', 'normal_exit', 'mod_applied'], 'yes')

    def test_results_require_human_not_d3d_debug_and_devices_independent(self):
        m, o, steps = self.m(), self.observations(), self.steps()
        r = I.results(steps, m, o)
        self.assertEqual(r['normal_play'], 'PASS')
        self.assertEqual(r['subtitles'], 'PASS')
        o['subtitles'] = 'not-exercised'
        o['dualsense_speaker'] = 'no'
        o['slowdown_seen'] = 'yes'
        r = I.results(steps, m, o)
        self.assertEqual(r['subtitles'], 'NOT ESTABLISHED')
        self.assertEqual(r['dualsense_speaker'], 'NOT ESTABLISHED')
        self.assertEqual(r['dualsense_detection'], 'PASS')
        self.assertEqual(r['dualsense_light'], 'PASS')
        self.assertEqual(r['normal_play'], 'PASS')
        self.assertTrue(r['menu_slowdown'].startswith('OPEN'))
        m['speaker_submissions'] = 0; o['dualsense_speaker'] = 'yes'; m['launch_plan']['selected_values']['dualsense_speaker'] = 'off'
        steps['play']['before']['values']['dualsense_speaker'] = 'off'
        self.assertEqual(I.results(steps, m, o)['dualsense_speaker'], 'NOT ESTABLISHED')
        m['guest_fatal'] = True
        self.assertEqual(I.results(steps, m, o)['normal_exit'], 'NOT ESTABLISHED')
        m = self.m(); m['markers'] = dict.fromkeys(m['markers'], False); m['audio_endpoints'] = 0
        self.assertEqual(I.results(self.steps(), m, self.observations())['normal_play'], 'PASS')

    def test_persistence_semantics_f4_change_and_empty_mod_is_not_acceptance(self):
        steps = self.steps()
        steps['reopen']['after']['settings'] = 'serialization differs'
        self.assertEqual(I.results(steps, self.m(), self.observations())['settings_persistence'], 'PASS')
        steps['play']['before']['values'] = steps['play']['after']['values']
        self.assertEqual(I.results(steps, self.m(), self.observations())['F3_F4'], 'NOT ESTABLISHED')
        steps['settings']['after']['mods']['entries'] = 0
        self.assertEqual(I.results(steps, self.m(), self.observations())['mods_configuration_persistence'], 'NOT ESTABLISHED')
        self.assertEqual(I.results(steps, self.m(), self.observations())['mods_tab'], 'PASS')

    def test_environment_preserves_normal_feature_selection(self):
        env = I.environment(self.root, {'wayland': '/test/wayland', 'pulse': '/test/pulse', 'display': ':1', 'xauth': '/test/auth', 'bus': 'unix:path=/test/bus', 'desktop': 'KDE'})
        self.assertFalse(any(k.startswith('R3HD_') for k in env))
        self.assertNotIn('SDL_VIDEO_DRIVER', env)
        self.assertEqual(env['SDL_AUDIO_DRIVER'], 'pulseaudio')
        self.assertEqual(env['HOME'], str(self.root / 'os-home'))
        self.assertEqual(env['XDG_DATA_HOME'], str(self.root / 'os-home/data'))
        self.assertEqual(env['XAUTHORITY'], '/test/auth')

    def test_preparation_never_starts_gui_or_game_and_leaves_first_run_fresh(self):
        p = self.root / 'test'
        with patch.object(I, 'native'), patch.object(I, 'seal'), patch.object(I, 'session_metadata', return_value={}), \
             patch.object(I, 'root', return_value=p), patch.object(I, 'data_check', return_value={'files': 915}), \
             patch.object(C, 'file_hash'), patch.object(C, 'package_files'), patch.object(I, 'programs'), \
             patch.object(I, 'environment', return_value={}), patch.object(I.shutil, 'disk_usage', return_value=type('D', (), {'free': 20_000_000_000})()), \
             patch.object(I.subprocess, 'run', return_value=type('R', (), {'returncode': 0})()) as run, patch.object(I.subprocess, 'Popen') as popen:
            I.prepare()
        self.assertFalse(popen.called)
        self.assertEqual(run.call_count, 5)
        self.assertTrue(all(c.args[0][0] == '/lib64/ld-linux-x86-64.so.2' and c.args[0][1] == '--list' for c in run.call_args_list))
        self.assertFalse((p / 'portable/data').exists())
        self.assertFalse((p / 'portable/settings.json').exists())
        self.assertFalse((p / 'portable/installer.json').exists())
        self.assertEqual(C.read_json((p / 'prepared.json').read_bytes())['game_execution'], 'NOT RUN')

    def test_packaged_integrity_and_local_edit_refusal(self):
        home = self.root / 'portable'; home.mkdir()
        files = {'bin/' + n: n.encode() for n in C.COMPONENTS}
        files.update({'Play.sh': b'fixture', 'Settings.sh': b'fixture', 'payload.json': b'{"publishable": false}'})
        portable = {'files': {n: {'size': len(b), 'sha256': C.digest(b)} for n, b in files.items()}, 'publishable': False,
                    'lgpl': {'corresponding_source': {'archive': C.SOURCE, 'sha256': C.LOCK['lgpl_sha256']}}}
        files['portable.json'] = json.dumps(portable).encode()
        archive = self.root / 'fixture.tar.gz'
        with tarfile.open(archive, 'w:gz') as t:
            for n, b in files.items():
                i = tarfile.TarInfo(C.TOP + '/' + n); i.size = len(b); i.mode = 0o755 if n in ('Play.sh', 'Settings.sh', 'bin/r3hd') else 0o644
                t.addfile(i, io.BytesIO(b))
                f = home / n; f.parent.mkdir(parents=True, exist_ok=True); f.write_bytes(b)
        here = self.root / 'runner'; here.mkdir()
        (here / 'ABI_HASHES.json').write_text(json.dumps({n: C.digest(n.encode()) for n in C.COMPONENTS}))
        with patch.object(I, 'HERE', here), patch.object(I, 'package', return_value=archive), patch.object(C, 'LOCK', dict(C.LOCK, package_sha256=C.sha(archive))):
            I.programs(home)
            (home / 'Play.sh').write_bytes(b'edited')
            with self.assertRaises(ValueError): I.programs(home)

    def test_machine_info_markers_privacy_and_no_debug_requirement(self):
        p = self.root; (p / 'steps/play').mkdir(parents=True)
        (p / 'steps/play/console-local.txt').write_text('M2 launch_prepared\nM2 runtime_initialized\nVulkanPresenter: Created\nComboClose profile_mode=delayed\nR3HD ds_speaker endpoint=opened name=PRIVATE\nR3HD ds_speaker cue output=submitted\n')
        row = I.machine(p)
        self.assertEqual(row['gpu_present_debug_records'], 0)
        self.assertTrue(row['markers']['M2 launch_prepared'])
        self.assertEqual(row['speaker_submissions'], 1)
        self.assertNotIn('PRIVATE', json.dumps(row))

    def test_existing_launcher_plan_is_required_and_paths_are_not_exported(self):
        p = self.root; home = p / 'portable'; session = home / 'sessions/fixture'; session.mkdir(parents=True)
        values = I.S.resolve_presets(I.S.load_registry(I.HERE / 'registry.json'), preset='hdplus')['values']
        values['dualsense_light'] = 'on'
        mapping = {'R3HD_COMBO_CLOSE': 'combo_close', 'R3HD_GAMEPLAY_SUBTITLES': 'gameplay_subtitles',
                   'R3HD_DS_LIGHT': 'dualsense_light', 'R3HD_DS_TRIGGER': 'dualsense_trigger', 'R3HD_DS_SPEAKER': 'dualsense_speaker'}
        plan = {'executable': str(home / 'bin/r3hd'), 'installed': True, 'settings': {'file': str(home / 'settings.json'), 'values': values},
                'env': {k: values[v] for k, v in mapping.items()},
                'arguments': ['--bind_settings=None', '--bind_debug_overlay=None', '--game_data_root=' + str(home / 'data/content'),
                              '--user_data_root=' + str(home / 'profiles/default/user'), '--cache_root=' + str(home / 'cache')]}
        plan['env'].update(R3HD_PCSET_HOME=str(home), R3HD_MODS_PLAN='PRIVATE/PATH')
        file = session / 'session.json'; file.write_text(json.dumps(plan))
        row = I.launch_plan(p)
        self.assertTrue(row['contract_verified'])
        self.assertNotIn('PRIVATE/PATH', json.dumps(row))
        self.assertNotIn(str(home), json.dumps(row))
        plan['env']['R3HD_DS_LIGHT'] = 'off'; file.write_text(json.dumps(plan))
        self.assertFalse(I.launch_plan(p)['contract_verified'])

    def test_five_stage_controller_uses_only_real_packaged_entries_and_no_repeat(self):
        p = self.root
        (p / 'prepared.json').write_text(json.dumps({'toolkit_sha256': C.sha(I.HERE / 'SHA256SUMS')}))
        steps = self.steps()
        sequence = [copy.deepcopy(steps[n][k]) for n in I.PHASES for k in ('before', 'after')]
        sequence[0] = {'settings': 'ABSENT', 'installer': False}
        desktop = {'wayland': '/test/wayland', 'pulse': '/test/pulse', 'display': ':1', 'xauth': None, 'bus': None, 'desktop': 'KDE'}
        answers = ['AUTHORIZE NORMAL PORTABLE INTEGRATION', 'I CLOSED OTHER R3HD INSTANCES', 'START SETUP', 'START SETTINGS',
                   'START REOPEN', 'AUTHORIZE PLAY AND CONFIGURED DEVICE OUTPUTS', 'START PLAY', 'START VERIFY']
        locks = types.SimpleNamespace(flock=lambda *a: None, LOCK_EX=1, LOCK_NB=2)
        with patch.object(I, 'native'), patch.object(I, 'seal'), patch.object(I, 'workspace', return_value=p), \
             patch.object(I, 'session_metadata', return_value=desktop), patch.object(I, 'programs'), \
             patch.object(I, 'snapshot', side_effect=sequence), patch.object(I, 'machine', return_value=self.m()), \
             patch.object(I, 'ask', return_value='yes'), patch.object(I.sys.stdin, 'isatty', return_value=True), \
             patch('builtins.input', side_effect=answers), patch.object(I, 'fcntl', locks), \
             patch.object(I.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=20_000_000_000)), \
             patch.object(I, 'supervise', return_value={'exit': 0, 'forced_reason': None}) as run:
            I.human(True)
            self.assertEqual([c.args[0][0].name for c in run.call_args_list], ['Settings.sh', 'Settings.sh', 'Settings.sh', 'Play.sh', 'Settings.sh'])
            for c in run.call_args_list:
                self.assertFalse(any(k.startswith('R3HD_') for k in c.args[3]))
            with self.assertRaises(ValueError): I.human(True)
            self.assertEqual(run.call_count, 5)
        self.assertTrue((p / 'results.json').exists())
        failed = p / 'failed-fixture'; failed.mkdir()
        (failed / 'prepared.json').write_text(json.dumps({'toolkit_sha256': C.sha(I.HERE / 'SHA256SUMS')}))
        exits = [{'exit': 0, 'forced_reason': None}] * 3 + [{'exit': -5, 'forced_reason': None}]
        with patch.object(I, 'native'), patch.object(I, 'seal'), patch.object(I, 'workspace', return_value=failed), \
             patch.object(I, 'session_metadata', return_value=desktop), patch.object(I, 'programs'), \
             patch.object(I, 'snapshot', side_effect=sequence), patch.object(I, 'ask', return_value='yes'), \
             patch.object(I.sys.stdin, 'isatty', return_value=True), patch('builtins.input', side_effect=answers), \
             patch.object(I, 'fcntl', locks), patch.object(I.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=20_000_000_000)), \
             patch.object(I, 'supervise', side_effect=exits) as run:
            with self.assertRaisesRegex(ValueError, 'script failed'): I.human(True)
            self.assertEqual(run.call_count, 4)
        self.assertEqual(C.read_json((failed / 'steps/play/observations.json').read_bytes())['menu'], 'yes')
        self.assertFalse((failed / 'steps/verify').exists())

    def test_data_manifest_validation_is_read_only_and_refuses_corruption(self):
        folder = self.root / 'content'; folder.mkdir()
        here = self.root / 'runner'; here.mkdir()
        lines = []
        for n in range(915):
            name = 'fixture_' + str(n)
            (folder / name).write_bytes(b'fixture')
            lines.append(name + '\t7\t' + C.digest(b'fixture'))
        (here / 'content_manifest.tsv').write_text('\n'.join(lines) + '\n')
        before = {f.name: f.read_bytes() for f in folder.iterdir()}
        with patch.object(I, 'HERE', here):
            self.assertEqual(I.data_check(folder)['files'], 915)
            self.assertEqual(before, {f.name: f.read_bytes() for f in folder.iterdir()})
            (folder / 'fixture_0').write_bytes(b'corrupt')
            with self.assertRaises(ValueError): I.data_check(folder)

    def test_one_collection_excludes_assets_raw_logs_and_retains_partial_failures(self):
        p = self.root
        (p / 'prepared.json').write_text(json.dumps({'content_source': 'PRIVATE', 'game_execution': 'NOT RUN'}))
        (p / 'raw-private.log').write_text('DO NOT EXPORT')
        (p / 'steps/play').mkdir(parents=True)
        (p / 'steps/play/exit.json').write_text('{"exit": -5}')
        with patch.object(I, 'native'), patch.object(I, 'seal'), patch.object(I, 'workspace', return_value=p), \
             patch.object(I, 'programs', side_effect=ValueError), patch.object(I, 'data_check', return_value={'files': 915}), \
             patch.object(I.sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value='TEST WINDOWS ARE CLOSED'):
            I.collect()
            original = (p / 'portable-private-evidence.zip').read_bytes()
            with self.assertRaises(ValueError): I.collect()
            self.assertEqual(original, (p / 'portable-private-evidence.zip').read_bytes())
        with zipfile.ZipFile(p / 'portable-private-evidence.zip') as z:
            all_bytes = b''.join(z.read(n) for n in z.namelist())
            self.assertNotIn(b'DO NOT EXPORT', all_bytes)
            self.assertNotIn(b'PRIVATE', all_bytes)
            self.assertNotIn('raw-private.log', z.namelist())
            self.assertTrue(C.read_json(z.read('collection.json'))['integrity']['programs'].startswith('STOP'))
            for line in z.read('SHA256SUMS').decode().splitlines():
                h, n = line.split('  '); self.assertEqual(h, C.digest(z.read(n)))

    def test_seal_and_native_authorization_refusals(self):
        I.seal()
        with patch.object(I, 'native'), patch.object(I, 'seal'), patch.object(I.sys.stdin, 'isatty', return_value=False), patch.object(I, 'supervise') as run:
            with self.assertRaises(ValueError): I.human(True)
            self.assertFalse(run.called)
        if sys.platform != 'linux' or 'microsoft' in Path('/proc/sys/kernel/osrelease').read_text().lower() or os.getuid() == 0:
            with self.assertRaises(ValueError): I.native()
        out = self.root / 'kit'
        B.build(out)
        self.assertEqual((out / 'r3hd-normal-portable.zip').read_bytes(), (BOOTROOT / 'kit/r3hd-normal-portable.zip').read_bytes())
        with self.assertRaises(ValueError): B.build(out)

    @unittest.skipUnless(os.name == 'posix', 'own non-game process group supervisor')
    def test_supervisor_only_own_nongame_child_and_timeout(self):
        p = self.root; (p / 'portable').mkdir(); (p / 'steps').mkdir()
        for name, command in [('normal', 'print("fixture")'), ('timeout', 'import time;time.sleep(5)')]:
            step = p / 'steps' / name; step.mkdir()
            with patch.object(I, 'LIMIT', .1 if name == 'timeout' else 3):
                row = I.supervise([sys.executable, '-c', command], p, step, os.environ.copy())
            if name == 'normal': self.assertEqual(row['exit'], 0); self.assertIsNone(row['forced_reason'])
            else: self.assertEqual(row['forced_reason'], 'SAFETY_TIME_LIMIT'); self.assertIsNotNone(row['exit'])


if __name__ == '__main__':
    unittest.main()
