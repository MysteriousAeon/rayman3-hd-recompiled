#!/usr/bin/env python3
"""Private compiled lifecycle evidence. Silent setups, independent copies, no game or visible UI.

SETUP PREVIOUS_SETUP PACKAGE PAYLOAD OUT --protected-home EXISTING_HOME
OUT must be new. The protected home is read/hash/copy-only; its data tree is never traversed.
This validates development outputs, not their version alignment or release approval.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import m48_replay_check as replay

PROTECTED = ('app', 'bin', 'settings.json', 'installer.json', 'r3hd_home.json',
             'profiles', 'save_history', 'mods', 'sessions', 'extras', 'unins000.exe', 'unins000.dat')
USER = ('settings.json', 'profiles', 'save_history', 'mods', 'sessions')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hashes(home, names):
    result = {}
    for name in names:
        top = home / name
        paths = [top] if top.exists() else []
        while paths:
            path = paths.pop()
            if path.lstat().st_file_attributes & 0x400:
                raise RuntimeError(f'reparse point in protected/copy tree: {path}')
            if path.is_file():
                result[path.relative_to(home).as_posix()] = digest(path)
            elif path.is_dir():
                paths.extend(sorted(path.iterdir()))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('setup', 'previous', 'package', 'payload', 'out'):
        ap.add_argument(name, type=Path)
    ap.add_argument('--protected-home', type=Path, required=True)
    ap.add_argument('--resume-after-published-install', action='store_true',
                    help='resume only after a refused fixture-key write; retains failed results')
    a = ap.parse_args()
    for name in ('setup', 'previous', 'package', 'payload', 'out', 'protected_home'):
        setattr(a, name, getattr(a, name).resolve())
    assert a.out.is_dir() if a.resume_after_published_install else not a.out.exists(), 'OUT state differs'
    assert a.protected_home not in a.out.parents and a.out not in a.protected_home.parents
    assert a.package.is_file() and a.setup.is_file() and a.previous.is_file()
    a.out.mkdir(exist_ok=a.resume_after_published_install)
    checks = []
    if a.resume_after_published_install:
        previous_results = (a.out / 'results.json').read_bytes()
        prior = json.loads(previous_results)
        assert [r['name'] for r in prior if not r['ok']] == ['published engine persists custom keys']
        (a.out / 'results.failed_key_fixture.json').write_bytes(previous_results)
        (a.out / 'old_custom_keys.failed_fixture.txt').write_bytes((a.out / 'old_custom_keys.txt').read_bytes())
        checks = prior[:4]
    identities = {str(p): {'sha256': digest(p), 'bytes': p.stat().st_size}
                  for p in (a.setup, a.previous, a.package, a.payload / 'payload.json')}
    for path in sorted((a.payload / 'bin').glob('*')) + [a.payload / 'app/r3hd_launcher.exe']:
        identities[str(path)] = {'sha256': digest(path), 'bytes': path.stat().st_size}
    if a.resume_after_published_install:
        assert json.loads((a.out / 'identities.json').read_bytes()) == identities
    else:
        (a.out / 'identities.json').write_bytes(json.dumps(identities, indent=2).encode())
    before = hashes(a.protected_home, PROTECTED)
    if a.resume_after_published_install:
        assert json.loads((a.out / 'protected_before.json').read_bytes()) == before
    else:
        (a.out / 'protected_before.json').write_bytes(json.dumps(before, indent=2).encode())
    env = dict(os.environ)
    assert not any(k.startswith('R3HD_INSTALL_') for k in env), 'no installer test hooks in compiled lifecycle'
    for key in ('R3HD_HOME', 'R3HD_GAME_DIR', 'R3HD_BIN_DIR', 'R3HD_PLAY_ROOT', 'R3HD_MODS_PLAN'):
        env.pop(key, None)

    def save():
        (a.out / 'results.json').write_bytes(json.dumps(checks, indent=2).encode())

    def check(name, condition, detail=''):
        checks.append({'name': name, 'ok': bool(condition), 'detail': str(detail)})
        save()
        print(('PASS ' if condition else 'FAIL ') + name, flush=True)
        if not condition:
            raise AssertionError(str(detail)[-1000:])

    def run(tag, cmd, timeout=600, overrides=None):
        start = time.monotonic()
        proc = subprocess.run(list(map(str, cmd)), capture_output=True, timeout=timeout, env={**env, **(overrides or {})},
                              creationflags=subprocess.CREATE_NO_WINDOW)
        text = (proc.stdout + proc.stderr).decode('utf-8', errors='replace')
        (a.out / (tag + '.txt')).write_bytes(text.encode())
        print(f'RUN {tag} exit={proc.returncode} seconds={time.monotonic()-start:.1f}', flush=True)
        return proc.returncode, text

    def setup(tag, home, exe=None, *extra):
        assert home.parent == a.out and not home.is_symlink()
        return run(tag, [exe or a.setup, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/R3HDTEST=1',
                         f'/DIR={home}', f'/LOG={a.out / (tag + ".log")}', '/LANG=en', *extra], 900)

    def engine(tag, home, *args):
        return run(tag, [home / 'app/python/python.exe', '-B', home / 'app/tools/r3hd_installer.py',
                         *args, '--home', home])

    def verify(tag, home):
        code, text = engine(tag, home, 'verify')
        check(tag, code == 0, text[-500:])

    def compiled_identity(home):
        manifest = json.loads((a.payload / 'payload.json').read_bytes())
        return all(digest(home / rel) == info['sha256'] for rel, info in manifest['files'].items())

    try:
        fresh, upgrade, rollback = (a.out / n for n in ('fresh', 'upgrade', 'rollback'))
        if not a.resume_after_published_install:
            code, text = setup('fresh_install', fresh, None, f'/PACKAGE={a.package}', '/PRESET=vanilla')
            check('fresh supported package extraction', code == 0, text)
            verify('fresh_verify', fresh)
            check('fresh exact compiled payload identity', compiled_identity(fresh))
            # Install a representative actual published application, never a writable data junction.
            code, text = setup('published_install', upgrade, a.previous, f'/PACKAGE={a.package}', '/PRESET=hdplus')
            check('published v1.0.1 silent install', code == 0, text)
        for name in ('profiles', 'mods'):
            src, dst = a.protected_home / name, upgrade / name
            if src.exists():
                hashes(a.protected_home, (name,))  # reject links before any copy
                shutil.copytree(src, dst, dirs_exist_ok=True)
        shutil.copyfile(a.protected_home / 'settings.json', upgrade / 'settings.json')
        code, text = engine('old_custom_keys', upgrade, 'set-preset', '--preset', 'hdplus',
                            '--keyboard', 'modern', '--key', 'a=C')
        check('published engine persists custom keys', code == 0, text)
        old_settings = (upgrade / 'settings.json').read_bytes()
        check('published settings schema 3', json.loads(old_settings)['schema'] == 3)
        recovery = a.out / 'recovery'
        recovery.mkdir()
        (recovery / 'settings.pre-upgrade.json').write_bytes(old_settings)
        # Actual old compiled application files retained for isolated downgrade checks.
        rollback.mkdir()
        for name in ('app', 'bin'):
            shutil.copytree(upgrade / name, rollback / name)
        for name in ('installer.json', 'r3hd_home.json'):
            shutil.copyfile(upgrade / name, rollback / name)
        # Stand-ins exercise history/session preservation without copying private logs unnecessarily.
        for rel in ('save_history/lifecycle/001/marker', 'sessions/lifecycle/marker'):
            p = upgrade / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'private lifecycle preservation marker')
        before_user = hashes(upgrade, USER)
        (a.out / 'upgrade_user_before.json').write_bytes(json.dumps(before_user, indent=2).encode())
        overlay = b'[overlay]\nenabled = true\n'
        (upgrade / 'bin/r3hd.toml').write_bytes(overlay)
        code, text = setup('upgrade_install', upgrade)
        check('compiled upgrade of published payload', code == 0, text)
        check('upgrade exact compiled payload identity', compiled_identity(upgrade))
        check('upgrade user files byte-identical', hashes(upgrade, USER) == before_user)
        backups = list((upgrade / 'dev_overlay_config').glob('*.toml'))
        check('F4 old bin config preserved outside bin', not (upgrade / 'bin/r3hd.toml').exists()
              and any(p.read_bytes() == overlay for p in backups))
        verify('upgrade_verify', upgrade)
        probe = r'''
import sys, subprocess
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
import r3hd_installer as e
base = b'"System","4","Services","0","100 K"\r\n'
original = subprocess.run
count = 0
try:
    for raw, rc, expected in ((base, 0, False), (base + b'"R3HD.EXE","123","Console","1","100 K"', 0, True),
                              (base, 1, None), (None, 0, None), (b'', 0, None), (b'bad', 0, None)):
        subprocess.run = lambda *a, **k: SimpleNamespace(stdout=raw, returncode=rc)
        try:
            result = e.game_running()
            assert expected is not None and result == expected
        except e.Refusal as exc:
            assert expected is None and exc.code == 'PROCESS_QUERY_FAILED'
        count += 1
    for error in (OSError('injected'), subprocess.TimeoutExpired('tasklist', 30),
                  UnicodeDecodeError('ascii', b'\xff', 0, 1, 'injected')):
        def fail(*a, **k):
            raise error
        subprocess.run = fail
        try:
            e.check_not_running()
            raise AssertionError('query failed open')
        except e.Refusal as exc:
            assert exc.code == 'PROCESS_QUERY_FAILED'
        assert e.process_alive(999)
        count += 1
    german = '"other.exe","77","Dienste für Benutzer","1","100 K"'.encode('cp850')
    assert e._parse_process_snapshot(german, 'cp850') == [('other.exe', 77)]
    count += 1
finally:
    subprocess.run = original
assert e.process_alive(__import__('os').getpid())
print('INSTALLED_ISSUE3 PASS', count, 'plus native PID')
'''
        code, text = run('installed_issue3', [upgrade / 'app/python/python.exe', '-B', '-c', probe,
                                             upgrade / 'app/tools'])
        check('installed embedded Python Issue3 cases', code == 0 and 'INSTALLED_ISSUE3 PASS 10' in text, text)
        code, text = engine('new_mapping', upgrade, 'set-preset', '--preset', 'hdplus', '--pad', 'a=y', 'y=a')
        check('new controller mapping saved by installed engine', code == 0, text)
        schema4 = (upgrade / 'settings.json').read_bytes()
        mapped = json.loads(schema4)
        check('schema 3 to 4 retains keys and language/DualSense preferences', mapped['schema'] == 4
              and mapped['controller']['buttons'] == {'a': 'y', 'y': 'a'}
              and mapped['keyboard'] == json.loads(old_settings)['keyboard']
              and mapped['preferences'] == json.loads(old_settings)['preferences'])
        (recovery / 'settings.schema4.json').write_bytes(schema4)
        code, text = run('new_compiled_model', [upgrade / 'app/r3hd_launcher.exe', '--no-ui'])
        check('new compiled Settings accepts mapped installation', code == 0 and 'MODEL_OK' in text, text)
        code, fields, text = replay.play_dry(upgrade)
        (a.out / 'new_play_dry.txt').write_bytes(text.encode('utf-8'))
        check('new installed Play dry-run', code == 0, text[-500:])
        # Old compiled Settings + old embedded resolver, on an independent settings copy.
        (rollback / 'settings.json').write_bytes(schema4)
        code, text = run('old_schema4_model', [rollback / 'app/r3hd_launcher.exe', '--no-ui'])
        old_code, old_model = engine('old_schema4_details', rollback, 'launcher-model')
        check('old compiled Settings model reports schema4 invalid', code == 0 and old_code == 0
              and 'SETTINGS_NEWER' in old_model and 'SETTINGS\tinvalid' in old_model, old_model[-1000:])
        check('old read leaves schema4 bytes unchanged', (rollback / 'settings.json').read_bytes() == schema4)
        code, text = run('old_schema4_play_dry', [rollback / 'app/r3hd_launcher.exe', '--play', '--dry-run', '--no-ui'])
        check('old compiled Play refuses schema4', code != 0 and 'SETTINGS_NEWER' in text, text[-1000:])
        # Explicit recovery, only in the disposable downgrade home; both originals remain outside it.
        (rollback / 'settings.json').write_bytes((recovery / 'settings.pre-upgrade.json').read_bytes())
        code, text = run('old_recovered_model', [rollback / 'app/r3hd_launcher.exe', '--no-ui'])
        old_code, old_model = engine('old_recovered_details', rollback, 'launcher-model')
        check('explicit pre-upgrade recovery restores old compiled Settings', code == 0 and old_code == 0
              and 'SETTINGS\tok' in old_model and 'SETTINGS_NEWER' not in old_model, old_model[-600:])
        code, text = run('old_recovered_play_dry', [rollback / 'app/r3hd_launcher.exe', '--play', '--dry-run', '--no-ui'],
                         overrides={'R3HD_GAME_DIR': str(fresh / 'data/content')})
        check('recovered old compiled Play dry-run uses pre-upgrade keys', code == 0 and '--keybind_a=C' in text, text[-800:])
        check('recovery retains both settings versions byte-exact',
              (recovery / 'settings.schema4.json').read_bytes() == schema4
              and (recovery / 'settings.pre-upgrade.json').read_bytes() == old_settings
              and (upgrade / 'settings.json').read_bytes() == schema4)
        # Same-source reinstall must keep the new mapping.
        before_mapped = hashes(upgrade, USER)
        code, text = setup('mapped_reinstall', upgrade)
        check('compiled reinstall preserves schema4 and user files', code == 0 and hashes(upgrade, USER) == before_mapped, text)
        # Repair the exact current payload through its installed embedded Python.
        (upgrade / 'app/r3hd_launcher.exe').unlink()
        code, text = engine('repair', upgrade, 'repair', '--payload', str(a.payload))
        check('repair restores compiled Settings and preserves user files', code == 0 and compiled_identity(upgrade)
              and hashes(upgrade, USER) == before_mapped, text[-500:])
        verify('repair_verify', upgrade)
        # Controlled real launcher process on a private desktop; one refusal, then let it finish.
        ui_script = a.out / 'hold_settings.txt'
        ui_script.write_bytes(b'wait 15000\ndump held\n')
        ui_out = a.out / 'held_settings'
        launcher = subprocess.Popen([str(upgrade / 'app/r3hd_launcher.exe'), '--ui-test', str(ui_script),
                                     '--out', str(ui_out)], env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            time.sleep(2)
            check('private Settings process remains alive for refusal probe', launcher.poll() is None)
            code, text = engine('running_launcher_refusal', upgrade, 'uninstall', '--check')
            check('installed process guard blocks real private Settings', code == 2 and 'LAUNCHER_RUNNING' in text, text)
        finally:
            launcher.wait(timeout=120)
        check('private Settings test exited cleanly', launcher.returncode == 0)
        check('process guard left user files unchanged', hashes(upgrade, USER) == before_mapped)
        # Uninstaller must operate on owned extracted data, never a data junction.
        check('uninstall targets have no data reparse point', not ((upgrade / 'data/content').lstat().st_file_attributes & 0x400))
        code, text = run('uninstall_keep', [upgrade / 'unins000.exe', '/VERYSILENT', '/SUPPRESSMSGBOXES',
                                          f'/LOG={a.out / "uninstall_keep.log"}'])
        check('compiled uninstall keeps user data and overlay backups', code == 0 and hashes(upgrade, USER) == before_mapped
              and any(p.exists() and p.read_bytes() == overlay for p in backups), text)
        check('retained uninstall removes owned applications', not (upgrade / 'app').exists() and not (upgrade / 'bin/r3hd.exe').exists())
        code, text = setup('retained_reinstall', upgrade, None, f'/PACKAGE={a.package}')
        check('compiled reinstall reuses retained schema4 user data', code == 0 and hashes(upgrade, USER) == before_mapped, text)
        unknown = upgrade / 'keep-unrelated.txt'
        unknown.write_bytes(b'unknown file survives')
        code, text = run('uninstall_delete', [upgrade / 'unins000.exe', '/VERYSILENT', '/SUPPRESSMSGBOXES',
                                            '/REMOVEUSERDATA=1', f'/LOG={a.out / "uninstall_delete.log"}'])
        check('explicit disposable user-data deletion', code == 0 and not any((upgrade / n).exists() for n in USER)
              and not (upgrade / 'dev_overlay_config').exists(), text)
        check('explicit deletion preserves unrelated file', unknown.read_bytes() == b'unknown file survives')
    finally:
        after = hashes(a.protected_home, PROTECTED)
        (a.out / 'protected_after.json').write_bytes(json.dumps(after, indent=2).encode())
        checks.append({'name': 'production protected files unchanged', 'ok': before == after,
                       'detail': f'{len(before)} files; exact hashes in protected_before/after.json'})
        save()
        print(f'PROTECTED unchanged={before == after} files={len(before)}', flush=True)
    assert all(c['ok'] for c in checks), 'a lifecycle check failed'
    print(f'V102_COMPILED_LIFECYCLE PASS {len(checks)}/{len(checks)}', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
