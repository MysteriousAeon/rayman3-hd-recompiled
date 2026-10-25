#!/usr/bin/env python3
"""Compile the actual setup against a tiny synthetic payload and test shortcut tasks.

No game is executable: the fixture's EXE/DLL files are text. Silent test mode
creates shortcuts only below a new OUT directory; no registry or launch action.
The established installer-only running-process hook applies to this synthetic
engine, never the launcher or a real home. Frozen candidates are read only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import r3hd_installer as engine

ROOT = Path(__file__).resolve().parents[1]
PLAY = 'Rayman 3 HD Recompiled.lnk'
SETTINGS = 'Rayman 3 HD Recompiled - Settings.lnk'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('out', type=Path)
    ap.add_argument('--python-dir', type=Path, required=True,
                    help='read-only bundled Python directory from an existing staged payload')
    ap.add_argument('--iscc', type=Path, default=ROOT / 'external/innosetup/ISCC.exe')
    ap.add_argument('--icon', type=Path, default=ROOT / 'private/work/launcher/r3hd.ico')
    a = ap.parse_args()
    out = a.out.resolve()
    safe_root = (ROOT / 'private/work/release_presentation').resolve()
    if not out.is_relative_to(safe_root) or out == safe_root:
        raise SystemExit('OUT must be a new child of private/work/release_presentation')
    out.mkdir(parents=True, exist_ok=False)
    # Record a host-visible inventory before any test starts. A live game is
    # allowed: only the isolated synthetic installer engine runs below OUT.
    inventory = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('r3hd.exe','r3hd_launcher.exe') } | "
        'Select-Object ProcessId,Name,ExecutablePath | ConvertTo-Json -Compress'],
        capture_output=True, timeout=60)
    if inventory.returncode:
        raise SystemExit('Host process inventory failed; no test launched')
    (out / 'host_processes.json').write_bytes(inventory.stdout or b'[]')
    payload, tree, _ = engine.make_fixture(out)
    shutil.copytree(a.python_dir, payload / 'app/python')
    for name in ('r3hd_installer.py', 'r3hd_intake.py', 'r3hd_settings.py', 'r3hd_ui_locale.py'):
        shutil.copyfile(ROOT / 'tools' / name, payload / 'app/tools' / name)
    for name in ('settings', 'controls', 'localization'):
        src = ROOT / 'config' / name
        if src.exists():
            shutil.copytree(src, payload / 'app/config' / name, dirs_exist_ok=True)
    intake = payload / 'app/config/intake'
    intake.mkdir(parents=True)
    shutil.copyfile(out / 'releases.json', intake / 'known_releases.json')
    manifest = engine.read_json(payload / 'payload.json')
    manifest['files'] = {p.relative_to(payload).as_posix(): {
        'size': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'role': 'test'}
        for p in sorted(payload.rglob('*')) if p.is_file() and p.name != 'payload.json'}
    manifest['payload_id'] = hashlib.sha256(''.join(
        f"{r}\t{e['size']}\t{e['sha256']}\n" for r, e in sorted(manifest['files'].items())).encode()).hexdigest()
    engine.write_json(payload / 'payload.json', manifest)
    def compile_setup(tag, version):
        manifest['version'] = version
        engine.write_json(payload / 'payload.json', manifest)
        destination = out / tag
        destination.mkdir()
        result = subprocess.run([str(a.iscc.resolve()), f'/DPayloadDir={payload}',
            f'/DOutputDir={destination}', f'/DIconFile={a.icon.resolve()}', '/DFastCompression',
            str(ROOT / 'tools/installer/r3hd_setup.iss')], capture_output=True, timeout=180)
        (destination / 'compile.log').write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit(f'Setup compile failed; see {tag}/compile.log')
        return next(destination.glob('*-setup.exe'))

    previous = compile_setup('previous', '0.28.0')
    setup = compile_setup('current', '0.29.0')
    env = os.environ.copy()
    env.update(R3HD_INSTALL_FAKE_RUNNING='0', R3HD_INSTALL_FAKE_LAUNCHER='0')
    rows = []

    def run(home, tag, tasks=None, installer=None):
        desktop, menu = out / (home.name + '_desktop'), out / (home.name + '_menu')
        desktop.mkdir(exist_ok=True)
        menu.mkdir(exist_ok=True)
        args = [str(installer or setup), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/R3HDTEST=1', '/LANG=en',
                f'/DIR={home}', f'/PACKAGE={tree}', '/PRESET=vanilla',
                f'/DESKTOPDIR={desktop}', f'/STARTMENUDIR={menu}', f'/LOG={out / (tag + ".log")}']
        if tasks is not None:
            args.append('/MERGETASKS=' + tasks)
        result = subprocess.run(args, env=env, timeout=120)
        if result.returncode:
            raise RuntimeError(f'{tag}: setup exit {result.returncode}; see log')
        state = engine.read_json(home / 'installer.json')['shortcuts']
        return desktop, menu, state

    def check(tag, home, expected, tasks=None, installer=None):
        desktop, menu, state = run(home, tag, tasks, installer)
        actual = tuple((desktop / name).is_file() for name in (PLAY, SETTINGS))
        ok = actual == expected and all((menu / name).is_file() for name in (PLAY, SETTINGS))
        ok = ok and tuple(state[k] for k in ('desktop', 'desktop_settings')) == expected
        rows.append({'name': tag, 'ok': ok, 'expected': expected, 'actual': actual, 'record': state})
        print(f'{"ok" if ok else "FAIL"} {tag}', flush=True)

    check('fresh_defaults', out / 'default_home', (True, True))
    for play, settings in ((False, False), (True, False), (False, True), (True, True)):
        suffix = f'{int(play)}{int(settings)}'
        tasks = ','.join(('' if value else '!') + name
                         for name, value in (('desktopicon', play), ('settingsicon', settings)))
        home = out / ('home_' + suffix)
        check('fresh_' + suffix, home, (play, settings), tasks, previous)
        check('upgrade_preserves_' + suffix, home, (play, settings))
        action = engine.read_json(home / 'installer.json')['history'][-1]['action']
        if action != 'update':
            raise RuntimeError(f'Expected a genuine synthetic version update, got {action}')
    home = out / 'default_home'
    for name in (PLAY, SETTINGS):
        (out / (home.name + '_desktop') / name).unlink()
    check('upgrade_preserves_deleted', home, (False, False))
    check('upgrade_explicit_play', home, (True, False), 'desktopicon,!settingsicon')
    check('upgrade_explicit_settings', home, (False, True), '!desktopicon,settingsicon')
    check('upgrade_explicit_both', home, (True, True), 'desktopicon,settingsicon')
    check('upgrade_explicit_neither', home, (False, False), '!desktopicon,!settingsicon')
    report = {'synthetic_only': True, 'setup_sha256': hashlib.sha256(setup.read_bytes()).hexdigest(), 'checks': rows}
    (out / 'result.json').write_bytes((json.dumps(report, indent=2) + '\n').encode())
    ok = sum(row['ok'] for row in rows)
    print(f'PRESENTATION_SHORTCUTS {"PASS" if ok == len(rows) else "FAIL"} {ok}/{len(rows)}')
    return int(ok != len(rows))


if __name__ == '__main__':
    sys.exit(main())
