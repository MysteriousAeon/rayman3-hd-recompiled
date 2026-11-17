"""Synthetic release-isolation checks; does not build, launch, or read game data."""
import io
import tempfile
import subprocess
import sys
import json
from pathlib import Path
import r3hd_release_audit as audit
import r3hd_stage as stage
import trailer_capture_prepare as prepare

class Allow:
    max_bytes = 1024 * 1024
    def denied(self, path): return False
    def kind_of(self, path): return 'text'

class Hashes:
    hashes = {}
    def wants(self, size): return False

def main():
    count = 0
    for encoding in ('ascii', 'utf-16le'):
        data = b'MZ' + bytes(100) + 'R3HD_PRIVATE_CAPTURE_BUILD_V1'.encode(encoding)
        for name in ('r3hd.exe', 'renamed.dll', 'innocent.dat'):
            entry = audit.Entry(name, len(data), lambda: io.BytesIO(data))
            assert any(x['code'] == 'CAPTURE_BUILD' for x in audit.audit_entry(entry, Allow(), Hashes()))
            with tempfile.TemporaryDirectory() as td:
                p = Path(td); (p / name).write_bytes(data)
                try:
                    stage.collect({'binaries': {'files': [name]}}, p, p, p, p)
                except stage.Refusal as exc:
                    assert exc.code == 'CAPTURE_BUILD'
                else:
                    raise AssertionError('staging accepted capture binary')
            count += 2
    assert not audit.capture_binary(b'MZ' + bytes(100))
    assert not audit.capture_binary(b'ordinary source R3HD_PRIVATE_CAPTURE_BUILD_V1')
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / 'capture_session.json').write_bytes(json.dumps({'kind': 'R3HD_PRIVATE_CAPTURE_BUILD_V1'}).encode())
        (p / 'hud.control').write_bytes(b'0 show\n')
        for n, mode in enumerate(('hide', 'show'), 1):
            subprocess.run([sys.executable, str(Path(__file__).with_name('trailer_capture_control.py')), str(p), mode], check=True, capture_output=True)
            assert (p / 'hud.control').read_bytes() == f'{n} {mode}\n'.encode()
    # Regression for the omitted host-timer replay found during F5 integration.
    app = prepare.prepared_app()
    assert b'm5_input_.Start(window())' in app and b'm5_input_.Stop()' in app
    if prepare.DEST.exists():
        assert (prepare.DEST / 'src/r3hd_app.h').read_bytes() == app
        timer = (prepare.DEST / 'src/m5_host_input.h').read_bytes()
        assert b'R3HD_TEST_SECONDS' in timer and b'M6 bounded_exit request_close=true' in timer
    assert 'R3HD_PRIVATE_CAPTURE' not in (prepare.ROOT / 'tools/build_milestone8.bat').read_text()
    print(f'CAPTURE_ISOLATION PASS {count + 7}/{count + 7}')

if __name__ == '__main__': main()
