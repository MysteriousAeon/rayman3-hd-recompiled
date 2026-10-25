"""Isolated Win32 fake-pipe contract tests. Never contact a real Discord pipe or launch the game."""
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
K = c.WinDLL('kernel32', use_last_error=True)
K.CreateNamedPipeW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, w.DWORD, c.c_void_p]
K.CreateNamedPipeW.restype = w.HANDLE
K.ConnectNamedPipe.argtypes = [w.HANDLE, c.c_void_p]
K.ReadFile.argtypes = [w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p]
K.WriteFile.argtypes = K.ReadFile.argtypes
K.CloseHandle.argtypes = [w.HANDLE]
K.DisconnectNamedPipe.argtypes = [w.HANDLE]


def main():
    prepared = ROOT / 'private/work/rex/src/r3hd_app.h'
    if prepared.is_file():
        host = prepared.read_text(encoding='utf-8')
        assert host.count('void OnShutdown() override') == 1
        assert all(call in host for call in ('m5_input_.Stop();', 'discord_.Stop();', 'icon_.image.Reset();'))
    exe = Path(sys.argv[1]).resolve()
    out = ROOT / 'private/work/release_discord/contracts'
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for mode in ('absent', 'normal', 'late', 'restart', 'no_ready', 'oversized', 'malformed', 'refused', 'partial'):
        prefix = r'\\?\pipe\r3hd-discord-test-' + uuid.uuid4().hex + '-'
        seen, errors = [], []
        ready = threading.Event()

        def server():
            try:
                if mode == 'late':
                    ready.set()
                    time.sleep(.18)
                for connection in range(2 if mode == 'restart' else 1):
                    pipe = K.CreateNamedPipeW(prefix + '0', 3, 0, 1, 65536, 65536, 0, None)
                    assert pipe != w.HANDLE(-1).value
                    ready.set()
                    try:
                        assert K.ConnectNamedPipe(pipe, None) or c.get_last_error() == 535

                        def read(size):
                            data = b''
                            while len(data) < size:
                                b = c.create_string_buffer(size - len(data))
                                done = w.DWORD()
                                if not K.ReadFile(pipe, b, len(b), c.byref(done), None) or not done.value:
                                    raise EOFError()
                                data += b.raw[:done.value]
                            return data

                        def frame():
                            op, size = struct.unpack('<II', read(8))
                            return op, read(size)

                        def write(op, payload):
                            data = struct.pack('<II', op, len(payload)) + payload
                            for piece in ([data[:3], data[3:9], data[9:]] if mode == 'partial' else [data]):
                                done = w.DWORD()
                                assert K.WriteFile(pipe, piece, len(piece), c.byref(done), None)
                                assert done.value == len(piece)

                        op, data = frame()
                        seen.append(['handshake', json.loads(data)])
                        assert op == 0 and json.loads(data) == {'v': 1, 'client_id': '1561411727084486686'}
                        if mode == 'no_ready':
                            time.sleep(.9)
                            continue
                        if mode == 'oversized':
                            raw = struct.pack('<II', 1, 65537)
                            done = w.DWORD()
                            K.WriteFile(pipe, raw, len(raw), c.byref(done), None)
                            continue
                        write(1, b'broken' if mode == 'malformed' else b'{"evt": "READY"}')
                        if mode == 'malformed':
                            continue
                        op, data = frame()
                        activity = json.loads(data)
                        seen.append(['activity', activity])
                        assert op == 1 and activity['cmd'] == 'SET_ACTIVITY'
                        a = activity['args']['activity']
                        assert set(a) == {'type', 'timestamps', 'assets'}
                        assert a['assets'] == {'large_image': 'rayman3hd'} and a['type'] == 0
                        assert abs(time.time() - a['timestamps']['start']) < 3
                        if mode == 'restart' and connection == 0:
                            time.sleep(1.1)  # crosses a second: a recomputed timestamp would fail
                            continue
                        if mode == 'refused':
                            write(1, b'{"evt":"ERROR","data":{"code":4006}}')
                            continue
                        write(3, b'ping')
                        assert frame() == (4, b'ping')
                        write(1, b'{"evt":null,"cmd":"SET_ACTIVITY","nonce":"session"}')
                        op, data = frame()
                        assert op == 1 and json.loads(data)['args']['activity'] is None
                        seen.append(['clear', True])
                    finally:
                        K.DisconnectNamedPipe(pipe)
                        K.CloseHandle(pipe)
            except Exception as error:
                errors.append(repr(error))
                ready.set()

        thread = None
        if mode != 'absent':
            thread = threading.Thread(target=server, daemon=True)
            thread.start()
            assert ready.wait(2)
        result = subprocess.run([str(exe), prefix, '1750' if mode == 'restart' else '650'],
                                capture_output=True, text=True, timeout=5)
        if thread:
            thread.join(2)
        assert result.returncode == 0, (mode, result.stdout, result.stderr)
        assert not errors and (not thread or not thread.is_alive()), (mode, errors)
        activities = [v for k, v in seen if k == 'activity']
        if mode in ('normal', 'late', 'restart', 'partial'):
            assert len(activities) == (2 if mode == 'restart' else 1), (mode, seen)
            assert len({a['args']['activity']['timestamps']['start'] for a in activities}) == 1
            assert any(k == 'clear' for k, _ in seen)
        results.append({'case': mode, 'pass': True, 'native': json.loads(result.stdout), 'events': seen})
    (out / 'results.json').write_bytes((json.dumps(results, indent=2) + '\n').encode())
    print(f'DISCORD_CONTRACT PASS {len(results)}/{len(results)} (fake IPC; no real Discord observation)')


if __name__ == '__main__':
    main()
