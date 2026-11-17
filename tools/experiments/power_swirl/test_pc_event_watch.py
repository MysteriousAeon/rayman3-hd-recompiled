"""Synthetic observer safety/layout checks; never opens a game process."""
import ctypes
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import pc_event_watch as watch


class Fixture:
    def __init__(self):
        self.data = bytearray(0x10000)
        for address, value in {
            0x10000: 0, 0x10100: 0x11000,
            0x11000: 2, 0x11004: 0x12000,
            0x12000: 0x13000, 0x12004: 0x14000, 0x1200C: 0x15000,
            0x15000: 0x15100, 0x15100: 0x15200, 0x1510C: 0x15300,
            0x15200: 0x15400, 0x15208: 0x15500,
            0x15404: 72, 0x15504: 0x15600, 0x1550C: 3,
            0x15620: 0, 0x15624: 5,
            0x15300: 0x15208, 0x15308: 0x15700, 0x15700: 3,
            0x13004: 0x15800, 0x15804: 0x15900, 0x1590C: 91,
            0x13188: 0x16000, 0x1600C: 0x16100,
            0x16104: 0x16200, 0x1620C: 169, 0x1601C: 1,
        }.items():
            self.word(address, value)
        self.data[0x6020:0x6024] = struct.pack('<f', 12.5)

    def word(self, address, value):
        struct.pack_into('<I', self.data, address - 0x10000, value)

    def read(self, address, length):
        offset = address - 0x10000
        return bytes(self.data[offset:offset + length])


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.r = watch.Reader(self.f.read)

    def test_world_and_animation_chain(self):
        with patch.object(watch, 'ROOTS', (0x10000, 0x10100)):
            actor = watch.discover(self.r)
        self.assertEqual(actor, 0x12000)
        self.assertEqual(watch.sample(self.r, actor), {
            'power_mirror': 3, 'main_animation': 91,
            'subanimations': [{'animation': 169, 'flag': 1, 'frame_parameter': 12.5}],
            'known_helix_animation_active': True})

    def test_schema_mismatch_refused(self):
        self.f.word(0x15300, 0x15200)
        with self.assertRaisesRegex(watch.Refused, 'schema'):
            watch.sample(self.r, 0x12000)

    def test_invalid_power_refused(self):
        self.f.word(0x15700, 6)
        with self.assertRaisesRegex(watch.Refused, 'power'):
            watch.sample(self.r, 0x12000)

    def test_subanimation_cycle_refused(self):
        self.f.word(0x16000, 0x16000)
        with self.assertRaisesRegex(watch.Refused, 'chain'):
            watch.sample(self.r, 0x12000)

    def test_world_cycle_terminates_without_scan(self):
        self.f.word(0x11000, 0)
        self.f.word(0x11008, 0x11000)
        with patch.object(watch, 'ROOTS', (0x10000, 0x10100)):
            with self.assertRaisesRegex(watch.Refused, 'no scan fallback'):
                watch.discover(self.r)

    def test_read_limits_and_short_reads(self):
        for address, length in ((0, 4), (0x10001, 4), (0x10000, 257)):
            with self.assertRaises(watch.Refused):
                self.r.read(address, length)
        self.r.total = 8 * 1024 * 1024
        with self.assertRaisesRegex(watch.Refused, 'budget'):
            self.r.read(0x10000, 4)
        with self.assertRaisesRegex(watch.Refused, 'incomplete'):
            watch.Reader(lambda a, n: b'').read(0x10000, 4)

    def test_output_containment_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            private = root / 'private/work/power_swirl/pc_pickup'
            private.mkdir(parents=True)
            with patch.object(watch, 'ROOT', root), patch.object(watch, 'OUTPUT_ROOT', private):
                allowed = private / 'new.jsonl'
                self.assertEqual(watch.output_path(allowed), allowed.resolve())
                for bad in (root / 'outside.jsonl', private / '..' / 'escape.jsonl',
                            private / 'wrong.json'):
                    with self.assertRaises(watch.Refused):
                        watch.output_path(bad)
                allowed.write_text('existing evidence', encoding='utf-8')
                with self.assertRaisesRegex(watch.Refused, 'overwrite'):
                    watch.output_path(allowed)
                self.assertEqual(allowed.read_text(), 'existing evidence')
                with patch.object(watch, 'OUTPUT_ROOT', root / 'redirected'):
                    with self.assertRaisesRegex(watch.Refused, 'redirects'):
                        watch.output_path(root / 'redirected' / 'new.jsonl')

    def test_process_access_requests_only_read_rights(self):
        class ApiCall:
            def __init__(self):
                self.args = None
            def __call__(self, *args):
                self.args = args
                return 0
        class Api:
            OpenProcess = ApiCall()
            ReadProcessMemory = ApiCall()
            QueryFullProcessImageNameW = ApiCall()
            IsWow64Process2 = ApiCall()
            CloseHandle = ApiCall()
        api = Api()
        with patch.object(ctypes, 'WinDLL', return_value=api):
            with self.assertRaisesRegex(watch.Refused, 'read-only'):
                watch.Process(123)
        self.assertEqual(api.OpenProcess.args, (0x1010, False, 123))
        self.assertIsNone(api.ReadProcessMemory.args)

    def test_wrong_process_image_closes_handle_without_reading(self):
        class Call:
            def __init__(self, result):
                self.result = result
                self.calls = []
            def __call__(self, *args):
                self.calls.append(args)
                if callable(self.result):
                    return self.result(*args)
                return self.result
        class Api:
            OpenProcess = Call(42)
            ReadProcessMemory = Call(0)
            QueryFullProcessImageNameW = Call(
                lambda handle, flags, value, size: setattr(value, 'value', 'C:/other.exe') or 1)
            CloseHandle = Call(1)
            IsWow64Process2 = Call(0)
        api = Api()
        with patch.object(ctypes, 'WinDLL', return_value=api):
            with self.assertRaisesRegex(watch.Refused, 'identity mismatch'):
                watch.Process(123)
        self.assertEqual(api.CloseHandle.calls, [(42,)])
        self.assertEqual(api.ReadProcessMemory.calls, [])

    def test_wrong_architecture_refused_before_player_reads(self):
        class Call:
            def __init__(self, result):
                self.result = result
            def __call__(self, *args):
                return self.result(*args) if callable(self.result) else self.result
        class Api:
            OpenProcess = Call(42)
            QueryFullProcessImageNameW = Call(
                lambda handle, flags, value, size: setattr(value, 'value', str(watch.DEFAULT_GAME)) or 1)
            IsWow64Process2 = Call(lambda handle, machine, native: 1)  # zero/zero: invalid
            CloseHandle = Call(1)
        with patch.object(watch, 'windows_api', return_value=Api()), \
             patch.object(watch, 'verify_executable'), patch.object(watch.Process, 'read') as read:
            with self.assertRaisesRegex(watch.Refused, 'WOW64'):
                watch.Process(123)
            read.assert_not_called()

    def test_racing_sample_refused_as_unstable(self):
        original = self.f.read
        reads = 0
        def changing(address, size):
            nonlocal reads
            if address == 0x15700:
                reads += 1
                if reads == 2:
                    return struct.pack('<I', 2)
            return original(address, size)
        with self.assertRaises(watch.UnstableSample):
            watch.sample(watch.Reader(changing), 0x12000)

    def test_out_of_bank_animation_refused(self):
        self.f.word(0x1590C, 185)
        with self.assertRaisesRegex(watch.Refused, 'bank'):
            watch.sample(self.r, 0x12000)

    def test_power_marker_distinguishes_expiry(self):
        pickup = watch.power_event(5, 3, 2.5)
        self.assertTrue(pickup['acquisition_candidate'])
        self.assertEqual((pickup['elapsed_s'], pickup['after_name']), (2.5, 'Shock Rocket'))
        self.assertFalse(watch.power_event(3, 5, 4)['acquisition_candidate'])

    def test_bounded_recording_marker_heartbeat_and_gap(self):
        first = watch.sample(self.r, 0x12000)
        changed = dict(first, power_mirror=2)
        class Clock:
            value = 0.0
            def now(self): return self.value
            def sleep(self, seconds): self.value += seconds
        clock, log = Clock(), io.StringIO()
        with patch.object(watch.time, 'monotonic', clock.now), \
             patch.object(watch.time, 'sleep', clock.sleep), \
             patch.object(watch, 'sample', return_value=changed):
            watch.observe(log, self.r, 0x12000, first, 1, 0)
        rows = [json.loads(line) for line in log.getvalue().splitlines()]
        events = [r for r in rows if r['kind'] == 'power_change']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['elapsed_s'], 0.05)
        self.assertEqual(rows[-1]['status'], 'complete')
        self.assertLessEqual(rows[-1]['attempts'], 20)
        self.assertGreater(len([r for r in rows if r['kind'] == 'sample']), 2)
        self.assertAlmostEqual(rows[-1]['max_valid_sample_gap_ms'], 50)

    def test_aborted_recording_has_explicit_footer(self):
        first = watch.sample(self.r, 0x12000)
        log = io.StringIO()
        with patch.object(watch.time, 'sleep'), patch.object(watch, 'sample', side_effect=watch.Refused('gone')):
            with self.assertRaisesRegex(watch.Refused, 'gone'):
                watch.observe(log, self.r, 0x12000, first, 1, watch.time.monotonic())
        footer = json.loads(log.getvalue().splitlines()[-1])
        self.assertEqual((footer['status'], footer['reason']), ('aborted', 'gone'))

    def test_log_budget_preserves_footer_space(self):
        log = io.StringIO('x' * (watch.MAX_LOG_BYTES - 1024))
        log.seek(0, 2)
        with self.assertRaisesRegex(watch.Refused, 'budget'):
            watch.record(log, {'kind': 'sample'})
        watch.record(log, {'kind': 'end', 'status': 'aborted'}, footer=True)
        self.assertLess(len(log.getvalue()), watch.MAX_LOG_BYTES)

    def test_main_creates_only_new_bounded_metadata_log(self):
        class FakeProcess:
            closed = False
            def __init__(self, pid, path): pass
            def read(inner, address, size): return self.f.read(address, size)
            def close(inner): FakeProcess.closed = True
        class Clock:
            value = 0.0
            def now(self): return self.value
            def sleep(self, seconds): self.value += seconds
        clock = Clock()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            private = root / 'private/work/power_swirl/pc_pickup'
            out = private / 'new' / 'sample.jsonl'
            with patch.object(watch, 'ROOT', root), patch.object(watch, 'OUTPUT_ROOT', private), \
                 patch.object(watch, 'ROOTS', (0x10000, 0x10100)), \
                 patch.object(watch, 'Process', FakeProcess), \
                 patch.object(watch.time, 'monotonic', clock.now), \
                 patch.object(watch.time, 'sleep', clock.sleep), \
                 patch.object(sys, 'argv', ['observer', '--pid', '123', '--seconds', '1', '--out', str(out)]), \
                 patch('builtins.print'):
                self.assertEqual(watch.main(), 0)
                before = out.read_bytes()
                self.assertEqual(watch.main(), 2)  # exclusive output: never replaces evidence
                self.assertEqual(out.read_bytes(), before)
            rows = [json.loads(line) for line in before.decode().splitlines()]
            self.assertFalse(rows[0]['objects_directly_observed'])
            self.assertFalse(rows[0]['frame_parameter_is_current_frame'])
            self.assertEqual(rows[-1]['status'], 'complete')
            self.assertEqual([p for p in root.rglob('*') if p.is_file()], [out])
            self.assertTrue(FakeProcess.closed)

    @unittest.skipUnless(os.name == 'nt', 'Windows API binding check')
    def test_real_read_only_api_on_own_synthetic_buffer(self):
        # Our own test process only: validates 64-bit HANDLE/pointer ctypes signatures.
        api = watch.windows_api()
        handle = api.OpenProcess(watch.READ_RIGHTS, False, os.getpid())
        self.assertTrue(handle)
        try:
            source = ctypes.create_string_buffer(b'synthetic-observer-fixture')
            target = ctypes.create_string_buffer(len(source))
            count = ctypes.c_size_t()
            self.assertTrue(api.ReadProcessMemory(handle, ctypes.addressof(source), target,
                                                 len(source), ctypes.byref(count)))
            self.assertEqual(target.raw, source.raw)
            self.assertEqual(count.value, len(source))
            machine, native = watch.wintypes.USHORT(), watch.wintypes.USHORT()
            self.assertTrue(api.IsWow64Process2(handle, ctypes.byref(machine), ctypes.byref(native)))
            self.assertEqual((machine.value, native.value), (0, 0x8664))
            name, size = ctypes.create_unicode_buffer(32768), watch.wintypes.DWORD(32768)
            self.assertTrue(api.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)))
            self.assertEqual(Path(name.value).suffix.lower(), '.exe')
        finally:
            api.CloseHandle(handle)


if __name__ == '__main__':
    unittest.main()
