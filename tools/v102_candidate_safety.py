#!/usr/bin/env python3
"""Bounded candidate commit/recovery checks on a disposable, already installed home.

PAYLOAD SETUP HOME OUT: HOME must be below OUT.parent, contain no reparse points,
and be an isolated lifecycle fixture. Uses packaged Python outside HOME so a killed
commit cannot strand the test driver. Faults are explicit engine fault injections,
not evidence of UI cancellation or power-loss safety.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

from v102_installer_lifecycle import hashes, USER


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('payload', 'setup', 'home', 'out'):
        ap.add_argument(name, type=Path)
    a = ap.parse_args()
    for name in ('payload', 'setup', 'home', 'out'):
        setattr(a, name, getattr(a, name).resolve())
    assert a.out.parent in a.home.parents and not a.out.exists()
    assert not any(k.startswith('R3HD_INSTALL_') for k in os.environ)
    assert json.loads((a.home / 'installer.json').read_bytes())['version'] == json.loads((a.payload / 'payload.json').read_bytes())['version']
    # Reject any fixture link before launching a mutating operation.
    hashes(a.home, tuple(p.name for p in a.home.iterdir()))
    a.out.mkdir()
    rows = []
    env = {k: v for k, v in os.environ.items() if k not in
           ('R3HD_HOME', 'R3HD_GAME_DIR', 'R3HD_BIN_DIR', 'R3HD_PLAY_ROOT')}

    def check(name, ok):
        rows.append({'name': name, 'ok': bool(ok)})
        (a.out / 'results.json').write_bytes(json.dumps(rows, indent=2).encode())
        print(('PASS ' if ok else 'FAIL ') + name, flush=True)
        assert ok, name

    def run(tag, cmd, extra=None):
        r = subprocess.run(list(map(str, cmd)), env={**env, **(extra or {})},
                           capture_output=True, timeout=600, creationflags=subprocess.CREATE_NO_WINDOW)
        (a.out / (tag + '.txt')).write_bytes(r.stdout + r.stderr)
        return r.returncode, (r.stdout + r.stderr).decode('utf-8', errors='replace')

    py = a.payload / 'app/python/python.exe'
    engine = a.payload / 'app/tools/r3hd_installer.py'
    for rel in ('profiles/safety/user/save-marker', 'mods/safety/preservation-marker',
                'save_history/safety/001/marker', 'sessions/safety/marker'):
        p = a.home / rel
        assert not p.exists()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'synthetic preservation fixture; not game data')
    before_user = hashes(a.home, USER)
    before_app = hashes(a.home, ('app', 'bin', 'installer.json'))
    overlay = b'[overlay]\nenabled = true\n# candidate recovery fixture\n'
    for point, engine_exit in (('commit:bin', 2), ('kill:commit:bin', 70), ('before_cleanup', 0)):
        tag = point.replace(':', '_')
        (a.home / 'bin/r3hd.toml').write_bytes(overlay)
        rc, _ = run(tag, [a.setup, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/R3HDTEST=1',
                         '/LANG=en', f'/DIR={a.home}', f'/LOG={a.out / (tag + ".log")}'],
                    {'R3HD_INSTALL_FAULT': point})
        log = (a.out / (tag + '.log')).read_text(encoding='utf-8-sig', errors='strict')
        engine_lines = [s for s in log.splitlines() if 'engine: install ' in s]
        check(tag + f' compiled setup exit={rc}, engine={engine_exit}',
              (rc == 0 if engine_exit == 0 else rc != 0) and len(engine_lines) == 1
              and engine_lines[0].endswith(' -> ' + str(engine_exit)))
        check(tag + ' user bytes retained', hashes(a.home, USER) == before_user)
        check(tag + ' overlay quarantined byte-exact',
              any(p.read_bytes() == overlay for p in (a.home / 'dev_overlay_config').glob('*.toml'))
              and not (a.home / 'bin/r3hd.toml').exists())
        journal = a.home / '.r3hd_txn.json'
        check(tag + ' journal disposition', journal.exists() == (point != 'commit:bin'))
        rc, text = run(tag + '_recover', [py, '-B', engine, 'uninstall', '--check', '--home', a.home])
        check(tag + ' packaged check recovery', rc == 0 and not journal.exists())
        rc, _ = run(tag + '_verify', [py, '-B', engine, 'verify', '--home', a.home])
        check(tag + ' healthy after recovery', rc == 0)
        check(tag + ' recovered user bytes', hashes(a.home, USER) == before_user)
        # Successful commit legitimately appends install history; application bytes must stay exact.
        now = hashes(a.home, ('app', 'bin', 'installer.json'))
        if point != 'before_cleanup':
            check(tag + ' restored previous transaction bytes', now == before_app)
        else:
            check(tag + ' committed application bytes',
                  {k: v for k, v in now.items() if k != 'installer.json'} ==
                  {k: v for k, v in before_app.items() if k != 'installer.json'})
    print(f'V102_CANDIDATE_SAFETY PASS {len(rows)}/{len(rows)}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
