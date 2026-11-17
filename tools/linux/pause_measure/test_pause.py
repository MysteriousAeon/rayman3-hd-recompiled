"""Synthetic fixtures/mocked dispatch only. Never launch game, GSR, SDL or devices."""
import copy
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0] / 'menu_cpu'))
sys.path.insert(0, str(HERE.parents[0] / 'menu_timing'))
import pause as P


class Child:
    def __init__(self, pid): self.pid = pid; self.returncode = None
    def poll(self): return self.returncode
    def wait(self, timeout=None): self.returncode = 0; return 0


class PauseTests(unittest.TestCase):
    def test_seal_local_edit_and_inventory_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d).resolve(); names=['pause.py','cpu.py','review.py','timing.py','HANDOFF.md']
            for n in names:(out/n).write_bytes(b'SYNTHETIC TOOL SOURCE')
            (out/'SHA256SUMS').write_text(''.join(P.T.digest((out/n).read_bytes())+'  '+n+'\n' for n in names))
            with patch.object(P,'__file__',str(out/'pause.py')):
                P.seal()
                (out/'cpu.py').write_bytes(b'LOCAL EDIT')
                with self.assertRaises(ValueError):P.seal()

    def test_existing_attempt_refused_before_tool_or_evidence_queries(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve(); (root/'Projects/R3HD-pause-measure-01').mkdir(parents=True)
            with patch.object(P.C,'native'),patch.object(P,'seal'),patch.object(P.Path,'home',return_value=root), \
                 patch.object(P,'command') as query,patch.object(P.R,'authenticate') as prior:
                with self.assertRaisesRegex(ValueError,'attempt exists'):P.preflight()
                query.assert_not_called();prior.assert_not_called()

    def test_recorder_contract_and_contained_state(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d).resolve(); argv = P.recorder_args(out)
            for flag, value in [('-w', 'portal'), ('-f', '60'), ('-fm', 'vfr'), ('-c', 'mkv'),
                                ('-encoder', 'gpu'), ('-fallback-cpu-encoding', 'no'), ('-k', 'h264'),
                                ('-bm', 'cbr'), ('-q', '12000'), ('-restore-portal-session', 'no'),
                                ('-write-first-frame-ts', 'yes')]:
                self.assertEqual(argv[argv.index(flag) + 1], value)
            self.assertFalse(set(argv) & {'-a', '-r', '-ro', '-p', '-sc', '-k h264_vulkan'})
            desktop = {'bus': 'unix:abstract=fixture', 'wayland': '/fixture/wayland', 'desktop': 'KDE', 'display': ':1', 'xauth': None}
            with patch.dict(P.os.environ, {'XDG_RUNTIME_DIR': '/fixture/runtime', 'LD_PRELOAD': 'UNTRUSTED'}):
                env = P.recorder_environment(out, desktop)
            self.assertTrue(Path(env['HOME']).is_relative_to(out)); self.assertNotIn('LD_PRELOAD', env)
            self.assertNotIn('LD_LIBRARY_PATH', env); self.assertFalse(any(k.startswith('R3HD_') for k in env))

    def test_first_frame_time_contract(self):
        raw = b'monotonic_microsec\trealtime_microsec\n101000000\t200000000\n'
        self.assertEqual(P.first_timestamp(raw, 100, 102)['monotonic'], 101)
        for raw in [b'', b'wrong\n1 2\n', b'monotonic_microsec realtime_microsec\nNaN 2\n',
                    b'monotonic_microsec realtime_microsec\n1000 2000000\n']:
            with self.assertRaises(ValueError): P.first_timestamp(raw, 100, 102)

    def test_video_pts_audio_and_duration_gates(self):
        info = {'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 1920, 'height': 1080}],
                'format': {'format_name': 'matroska,webm', 'duration': '60.0'}}
        frames = {'frames': [{'best_effort_timestamp_time': x} for x in ('0', '.016', '.050')]}
        with tempfile.TemporaryDirectory() as d:
            out = Path(d).resolve(); (out / 'pause-private.mkv').write_bytes(b'SYNTHETIC VIDEO')
            for issue in (None, 'audio', 'duration', 'nan', 'repeat', 'reverse'):
                i, f = copy.deepcopy(info), copy.deepcopy(frames)
                if issue == 'audio': i['streams'].append({'codec_type': 'audio'})
                if issue == 'duration': i['format']['duration'] = '76'
                if issue == 'nan': f['frames'][1]['best_effort_timestamp_time'] = 'nan'
                if issue == 'repeat': f['frames'][1]['best_effort_timestamp_time'] = '0'
                if issue == 'reverse': f['frames'][2]['best_effort_timestamp_time'] = '.001'
                with self.subTest(issue=issue), patch.object(P, 'command', side_effect=[json.dumps(i).encode(), json.dumps(f).encode()]):
                    if issue:
                        with self.assertRaises(ValueError): P.media_metadata(out)
                    else:
                        r = P.media_metadata(out)
                        self.assertEqual(r['decoded_frame_pts_seconds'], [0, .016, .05])
                        self.assertEqual(r['physical_input_latency'], 'UNKNOWN')

    def test_export_original_video_no_private_state(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d).resolve(); (out / 'pause-private.mkv').write_bytes(b'ORIGINAL VFR PTS BYTES')
            (out / 'cpu.jsonl').write_bytes(b'{}\n'); (out / 'secret-save').write_bytes(b'PRIVATE SAVE')
            (out / 'portal-token-local').write_bytes(b'SECRET TOKEN')
            P.export(out, {'recorder_exit': 0, 'human': {'window_only_selection': True}})
            with zipfile.ZipFile(out / 'pause-private-evidence.zip') as z:
                self.assertEqual(set(z.namelist()), {'receipt.json', 'cpu.jsonl', 'pause-private.mkv', 'SHA256SUMS'})
                self.assertEqual(z.read('pause-private.mkv'), b'ORIGINAL VFR PTS BYTES')
                self.assertEqual(z.getinfo('pause-private.mkv').compress_type, zipfile.ZIP_STORED)
                for line in z.read('SHA256SUMS').decode().splitlines():
                    h, n = line.split('  '); self.assertEqual(P.T.digest(z.read(n)), h)
            with self.assertRaises(FileExistsError): P.export(out, {})

    def test_unconfirmed_source_video_never_exported(self):
        for row in ({'recorder_exit': 0, 'human': {}},
                    {'recorder_exit':0,'human':{'window_only_selection':True},'media_privacy_hold':True}):
            with tempfile.TemporaryDirectory() as d:
                out = Path(d).resolve(); (out / 'pause-private.mkv').write_bytes(b'UNCONFIRMED OR AUDIO SOURCE')
                P.export(out, row)
                with zipfile.ZipFile(out / 'pause-private-evidence.zip') as z:
                    self.assertNotIn('pause-private.mkv', z.namelist())

    def test_check_and_human_authorization_never_dispatch_without_person(self):
        with patch.object(P, 'preflight', return_value=()), patch.object(P, 'run') as run:
            with patch.object(P.sys, 'argv', ['pause.py', 'check']): self.assertEqual(P.main(), 0)
            with patch.object(P.sys, 'argv', ['pause.py', 'human']):
                with self.assertRaises(ValueError): P.main()
            with patch.object(P.sys, 'argv', ['pause.py', 'human', '--human-present']), patch.object(P.sys.stdin, 'isatty', return_value=False):
                with self.assertRaises(ValueError): P.main()
            run.assert_not_called()

    @unittest.skipUnless(os.name == 'posix', 'POSIX signal fixture; no actual signals')
    def test_owned_signals_and_safety_bound(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d).resolve(); row = {'recorder_signals': [], 'clock_ticks_per_second': 100, 'events': []}
            game, rec = Child(10), Child(20)
            with (out / 'cpu.jsonl').open('w') as stream, patch.object(P.C, 'Guard'):
                s = P.Supervisor(game, out, out, {}, 1, row, stream)
                s.rec = rec; s.rec_start = 123; s.spawned = 90; s.first = {'monotonic': 100}
                game.returncode = 0
                with patch.object(P.C, 'game_identity'), patch.object(P.C, 'proc', return_value={'start': 999}), patch.object(P.os, 'killpg') as kill:
                    with self.assertRaises(ValueError): s.signal_recorder(signal.SIGINT)
                    kill.assert_not_called()
                with patch.object(P.C, 'game_identity'), patch.object(P.C, 'proc', return_value={'start': 123}), \
                     patch.object(P.os, 'killpg') as kill, patch.object(P.time, 'monotonic', return_value=170):
                    with self.assertRaisesRegex(ValueError, 'time bound'): s.tick(allow_game_exit=True)
                    kill.assert_called_once_with(20, signal.SIGINT)
                self.assertEqual(row['recorder_signals'], ['SIGINT'])
                with patch.object(P.C, 'game_identity'), patch.object(P.C, 'proc', return_value={'start': 123}), \
                     patch.object(P.os, 'killpg') as kill, patch.object(P.time, 'monotonic', return_value=174):
                    s.tick(allow_game_exit=True); kill.assert_called_once_with(20, signal.SIGKILL)
                # Incomplete first-frame sidecar is never used as a clock. Positive output
                # still has a safety watchdog, without accepting a substitute measurement anchor.
                (out/'pause-private.mkv').write_bytes(b'PARTIAL HEADER')
                (out/'pause-private.mkv.ts').write_bytes(b'monotonic_microsec\trealtime_microsec\n')
                row['recorder_signals']=[]
                s=P.Supervisor(game,out,out,{},1,row,stream);s.rec=rec;s.rec_start=123;s.spawned=90
                with patch.object(P.time,'monotonic',return_value=100):s.tick(allow_game_exit=True)
                self.assertIsNone(s.first);self.assertEqual(s.first_output,100)
                with patch.object(P.C,'game_identity'),patch.object(P.C,'proc',return_value={'start':123}), \
                     patch.object(P.os,'killpg') as kill,patch.object(P.time,'monotonic',return_value=170):
                    with self.assertRaisesRegex(ValueError,'time bound'):s.tick(allow_game_exit=True)
                    kill.assert_called_once_with(20,signal.SIGINT)

    def flow(self, root, fail=False):
        task = root / 'task'; home = task / 'portable'; (home / 'mods').mkdir(parents=True)
        (home / 'profiles').mkdir(); (home / 'profiles/save').write_bytes(b'PRIVATE SAVE')
        for n, raw in [('settings.json', b'SETTINGS'), ('installer.json', b'INSTALLER'), ('mods/state.json', b'MODS')]:
            (home / n).write_bytes(raw)
        old = home / 'sessions/old'; new = home / 'sessions/new'; old.mkdir(parents=True)
        oldlog = old / 'runtime.log'; oldlog.write_bytes(b'OLD LOG')
        out = root / 'out'; game, rec = Child(987001), Child(987002); calls = []; clock = [100.]
        def popen(argv, **kw):
            calls.append((argv, kw))
            if len(calls) == 1:
                new.mkdir(); (new / 'runtime.log').write_bytes(b'NEW LOG'); return game
            if fail is True: raise OSError('fixture recorder failure')
            (out / 'pause-private.mkv').write_bytes(b'SYNTHETIC ORIGINAL VIDEO'); return rec
        class Sup:
            def __init__(self, *a): self.rec=None; self.rec_start=None; self.first=None; self.target={'pid': 987003, 'group': 987001}; self.spawned=None
            def event(self, name): pass
            def answer(self, prompt, choices):
                if fail == 'interrupt': raise KeyboardInterrupt()
                if 'WINDOW ONLY READY' in choices: clock[0] = 109 if fail == 'late' else 101
                return 'no' if 'no' in choices else next(iter(choices))
            def tick(self, allow_game_exit=False):
                if self.rec: self.first={'monotonic': 100, 'realtime': 200}
                if allow_game_exit: game.returncode=0
            def delay(self, n): clock[0]+=n
            def request_stop(self): rec.returncode=0
        with patch.object(P.subprocess, 'Popen', side_effect=popen), patch.object(P.C, 'proc', return_value={'start': 7}), \
             patch.object(P.C, 'Guard'), patch.object(P.C, 'find_game', return_value={'pid': 987003}), \
             patch.object(P, 'Supervisor', Sup), patch.object(P.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(P.time, 'sleep'), patch.object(P.os, 'sysconf', return_value=100, create=True), \
             patch.object(P, 'tool_identity', return_value={'fixture': True}), patch.object(P, 'recorder_environment', return_value={'RECORDER': 'PRIVATE'}), \
             patch.object(P, 'media_metadata', return_value={'physical_input_latency': 'UNKNOWN', 'sha256':P.T.digest(b'SYNTHETIC ORIGINAL VIDEO')}), \
             patch.object(P.T, 'authenticate', return_value={'fixture': True}), patch.object(P.T, 'analyze', return_value={}), \
             patch.object(P.C, 'MODS', P.T.digest(b'MODS')), patch.object(P.C, 'game_identity', side_effect=FileNotFoundError), \
             patch.object(P.C, 'stop_owned', side_effect=lambda child, start: setattr(child, 'returncode', 0) or []):
            # Signal gate is tested independently; fixture sets it before the controller checks it.
            old_request=Sup.request_stop
            def request_stop(self):
                old_request(self)
                # row is the controller-owned object passed at construction (set below).
                self.row['recorder_signals']=['SIGINT']
            old_init=Sup.__init__
            def init(self,*a): old_init(self,*a); self.row=a[5]
            with patch.object(Sup,'request_stop',request_stop), patch.object(Sup,'__init__',init):
                result=P.run(task,out,{'NORMAL':'UNCHANGED'},{'fixture':True},[old],{str(oldlog):P.T.digest(b'OLD LOG')},{},{'fixture':True},{'fixture':True})
        row=json.loads((out/'receipt.json').read_bytes())
        self.assertEqual(calls[0][0],[str(home/'Play.sh')]); self.assertEqual(calls[0][1]['env'],{'NORMAL':'UNCHANGED'})
        self.assertEqual(oldlog.read_bytes(),b'OLD LOG'); self.assertEqual((home/'profiles/save').read_bytes(),b'PRIVATE SAVE')
        return result,row,calls,out

    def test_normal_flow_one_launch_one_capture(self):
        with tempfile.TemporaryDirectory() as d:
            result,row,calls,out=self.flow(Path(d).resolve())
            self.assertEqual(result,0); self.assertEqual(len(calls),2); self.assertTrue(row['protocol_complete'])
            self.assertEqual(row['physical_input_latency'],'UNKNOWN'); self.assertEqual(row['measurement_validity'],'INCONCLUSIVE; scene/focus/recording perturbation')

    def test_recorder_failure_no_retry_partial_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            result,row,calls,out=self.flow(Path(d).resolve(),True)
            self.assertEqual(result,2); self.assertEqual(len(calls),2); self.assertFalse(row['protocol_complete'])
            self.assertTrue((out/'pause-private-evidence.zip').exists()); self.assertEqual(row['stop_reason'],'OSError')

    def test_late_confirmation_and_interrupt_no_retry(self):
        for issue in ('late','interrupt'):
            with self.subTest(issue=issue), tempfile.TemporaryDirectory() as d:
                result,row,calls,out=self.flow(Path(d).resolve(),issue)
                self.assertEqual(result,2); self.assertFalse(row['protocol_complete'])
                self.assertEqual(len(calls),2 if issue=='late' else 1)
                self.assertEqual(row['stop_reason'],'HUMAN_INTERRUPT' if issue=='interrupt' else 'window confirmation too late; preserve partial, no retry')
                with zipfile.ZipFile(out/'pause-private-evidence.zip') as z:
                    self.assertNotIn('pause-private.mkv',z.namelist())


if __name__ == '__main__': unittest.main()
