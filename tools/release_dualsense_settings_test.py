"""D-102 / D-108: the DualSense preferences through the engine and the real Settings window on a private desktop;
synthetic homes only, no game, no controller.
D-108: a new installation stores light bar and R2 resistance on; Adaptive Trigger Strength is a 0..100 % slider
(default 30, stored when chosen, shown disabled while the R2 option is off); an update from 1.0.0 (no such options)
turns both on, a 1.0.1 home keeps what it holds (an absent choice there may be an explicit Off: off); every option is
independent of the others, of the preset and of Discord, survives an update, and the page lays out in en / tr."""
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

import m30_launcher_regression as launcher
import r3hd_installer as engine
import r3hd_settings as settings

ROOT = Path(__file__).resolve().parents[1]
KEYS = ('dualsense_light', 'dualsense_trigger')
STRENGTH = 'dualsense_trigger_strength'
QUIET = lambda *_: None  # noqa: E731
checks = []


def check(name, ok, detail=''):
    checks.append({'name': name, 'pass': bool(ok)})
    print(('ok   ' if ok else 'FAIL ') + name, flush=True)
    assert ok, (name, detail)


def values(reg, home):
    return settings.resolve(reg, settings=launcher.settings(home))['values']


def refused(fn):
    try:
        fn()
    except (engine.Refusal, settings.Refused):
        return True
    return False


def engine_checks(reg, t):
    for preset in ('vanilla', 'hdplus'):
        r = settings.resolve(reg, preset=preset)['values']
        check(f'{preset}: an absent choice resolves off / off / 30 (the play.ps1 defaults)',
              [r[k] for k in (*KEYS, STRENGTH)] == ['off', 'off', '30'])
    check('a new installation stores both options on', {k: settings.install_defaults(reg).get(k) for k in KEYS}
          == {'dualsense_light': 'on', 'dualsense_trigger': 'on'} and STRENGTH not in settings.install_defaults(reg))
    check('strength values are 0 ... 100, integers only', reg['settings'][STRENGTH]['values'] == [str(i) for i in range(101)])
    home = launcher.make_home(t, 'fresh')
    v = values(reg, home)
    check('fresh home: light on, trigger on, strength 30', [v[k] for k in (*KEYS, STRENGTH)] == ['on', 'on', '30'])
    for pct in ('0', '100', '30', '57'):
        engine.set_option(home, STRENGTH, pct)
        stored = launcher.settings(home)['preferences'].get(STRENGTH)
        check(f'strength {pct}: kept ({"the default, not stored" if pct == "30" else "stored"})',
              stored == (None if pct == '30' else pct) and values(reg, home)[STRENGTH] == pct)
    for bad in ('101', '-1', '30.5', 'abc', ''):
        check(f'strength {bad!r} refused, the stored value kept',
              refused(lambda: engine.set_option(home, STRENGTH, bad)) and values(reg, home)[STRENGTH] == '57')
    engine.set_option(home, 'dualsense_trigger', 'off')
    engine.set_option(home, 'dualsense_light', 'off')
    prefs = launcher.settings(home)['preferences']
    check('explicit Off is stored (preserve_default) and the strength kept',
          prefs.get('dualsense_light') == 'off' and prefs.get('dualsense_trigger') == 'off' and prefs.get(STRENGTH) == '57')
    engine.set_preset(home, 'hdplus', keyboard=('modern', {}))
    v = values(reg, home)
    check('a preset change keeps all three', [v[k] for k in (*KEYS, STRENGTH)] == ['off', 'off', '57'])
    # Updates. The engine under test writes the new defaults itself, so an older home is made by removing the keys
    # from a fresh one: exactly what the 1.0.0 engine wrote (it had no DualSense options).
    t2 = t / 'upgrade'
    t2.mkdir()
    p100, tree, rels = engine.make_fixture(t2, '1.0.0', b'v100')
    p101, _, _ = engine.make_fixture(t2, '1.0.1', b'v101')
    p102, _, _ = engine.make_fixture(t2, '1.0.2', b'v102')

    def old_home(name, version_payload, extra=None):
        h = t2 / name
        engine.install(h, version_payload, tree, 'hdplus', releases=rels, log=QUIET)
        s = launcher.settings(h)
        for k in (*KEYS, STRENGTH):
            s['preferences'].pop(k, None)
        s['preferences'].update(extra or {})
        engine.write_json(h / 'settings.json', s)
        return h, s

    h, before = old_home('h100', p100, {'cursor': 'visible'})
    r = engine.install(h, p101, None, releases=rels, log=QUIET)
    after = launcher.settings(h)
    want = copy.deepcopy(before)
    want['preferences'].update({'dualsense_light': 'on', 'dualsense_trigger': 'on'})
    want['preferences'] = dict(sorted(want['preferences'].items()))
    check('update 1.0.0 -> 1.0.1: both options on, strength absent (30), everything else byte-equal',
          r['settings'] == 'written' and after == want and values(reg, h)[STRENGTH] == '30', (after, want))
    r = engine.install(h, p101, None, releases=rels, log=QUIET)
    check('repair of that 1.0.1 home: settings kept', r['settings'] == 'kept' and launcher.settings(h) == after)
    h, before = old_home('h101', p101)
    r = engine.install(h, p102, None, releases=rels, log=QUIET)
    check('update of a 1.0.1 home without a stored choice: kept off (it may be an explicit Off)',
          r['settings'] == 'kept' and launcher.settings(h) == before
          and [values(reg, h)[k] for k in KEYS] == ['off', 'off'])
    h, before = old_home('h100b', p100, {'dualsense_trigger': 'off', STRENGTH: '80'})
    engine.install(h, p101, None, releases=rels, log=QUIET)
    v = values(reg, h)
    check('update 1.0.0 -> 1.0.1 never changes a named value: trigger off and strength 80 kept, light on',
          [v[k] for k in (*KEYS, STRENGTH)] == ['on', 'off', '80'])
    h, before = old_home('h100c', p100)
    engine.install(h, p101, None, 'vanilla', releases=rels, log=QUIET)
    check('update 1.0.0 -> 1.0.1 with an explicit preset: the same defaults',
          [values(reg, h)[k] for k in KEYS] == ['on', 'on'] and launcher.settings(h)['preset'] == 'vanilla')
    check('upgrade_defaults leaves schema 1 files alone', engine.upgrade_defaults({'schema': 1, 'preset': 'vanilla'}) is None)


def ui_checks(reg, t):
    for language in ('en', 'tr'):
        lt = t / language
        lt.mkdir()
        home = launcher.make_home(lt, 'home')
        engine.set_option(home, 'ui_language', language)
        engine.set_preset(home, 'hdplus', pairs=['gameplay_subtitles=all'], keyboard=('modern', {}))
        payload, tree, releases = engine.make_fixture(lt)
        before = launcher.settings(home)
        engine.install(home, payload, tree, releases=releases, log=QUIET)
        check(f'{language}: an update keeps the settings file', launcher.settings(home) == before)
        label = 'Adaptive Trigger Strength' if language == 'en' else 'Uyarlanabilir Tetik Sertliği'
        for key in KEYS:
            other = KEYS[1 - KEYS.index(key)]
            for value in ('off', 'on'):
                code, dumps, log, _ = launcher.ui(home, lt, f'{key}_{value}',
                    f'page advanced\nset {key} {value}\nclick save\nreload\ndump saved\nshot saved\nclick close\n')
                v = values(reg, home)
                check(f'{language}: {key}={value} through the window, the other option untouched',
                      code == 0 and v[key] == value and v[other] == 'on' and launcher.layout_ok(dumps['saved']), log)
        for pct in ('0', '100', '57', '30'):
            code, dumps, log, _ = launcher.ui(home, lt, f'strength_{pct}',
                f'page advanced\nset {STRENGTH} {pct}\nclick save\nreload\npage advanced\ndump saved\nshot saved\n'
                'click close\n')
            d = dumps.get('saved', {})
            shown = (f'{pct}%' if language == 'en' else f'%{pct}')
            check(f'{language}: slider {pct}: saved, shown as {shown}, labelled, layout clean',
                  code == 0 and values(reg, home)[STRENGTH] == pct and d.get(f'setting.{STRENGTH}') == f'{pct} enabled=1'
                  and d.get(f'slider.{STRENGTH}') == f'pos={pct} max=100 visible=1 value={shown} label={label}'
                  and launcher.layout_ok(d), (log, {k: v for k, v in d.items() if 'slider' in k or 'controls' in k}))
        engine.set_option(home, 'dualsense_trigger', 'off')
        code, dumps, log, _ = launcher.ui(home, lt, 'strength_disabled',
            f'page advanced\ndump off\nset {STRENGTH} 80\ndump tried\nclick close\n')
        check(f'{language}: R2 option off: slider disabled, the stored strength kept',
              dumps.get('off', {}).get(f'setting.{STRENGTH}') == '30 enabled=0' and 'control disabled' in log
              and values(reg, home)[STRENGTH] == '30', (log, dumps.get('off')))
        engine.set_option(home, 'dualsense_trigger', 'on')


def dry_run_checks(t):
    tasks = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq r3hd.exe', '/NH'], capture_output=True, text=True).stdout
    if 'r3hd.exe' in tasks.lower():
        print('skip dry runs: r3hd.exe is running (play.ps1 refuses dry runs then)')
        return
    play = ROOT / 'tools' / 'play.ps1'
    sf = t / 'strength.json'
    sf.write_bytes(json.dumps({'schema': 3, 'preset': 'hdplus', 'preferences': {
        'dualsense_light': 'on', 'dualsense_trigger': 'on', STRENGTH: '57'}}).encode())
    for args, want in ((['-SettingsFile', str(sf)], 'light=on trigger=on strength=57'),
                       (['-SettingsFile', str(sf), '-DualSenseTriggerStrength', '0'], 'light=on trigger=on strength=0'),
                       ([], 'light=off trigger=off strength=30')):
        r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(play), '-DryRun', *args],
                           capture_output=True, text=True, timeout=300, env=launcher.launcher_env())
        line = next((l for l in r.stdout.splitlines() if l.startswith('dualsense')), '')
        check(f'play.ps1 dry run {" ".join(args[-2:]) or "(defaults)"}: {want}', r.returncode == 0 and line.endswith(want),
              r.stdout[-800:] + r.stderr[-800:])
    r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(play), '-DryRun',
                        '-DualSenseTriggerStrength', '101'], capture_output=True, text=True, timeout=300)
    check('play.ps1 refuses a strength of 101', r.returncode != 0)


def main():
    if len(sys.argv) > 1:
        launcher.LAUNCHER = Path(sys.argv[1]).resolve()
    out = ROOT / 'private/work/release_dualsense' / ('settings_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir(parents=True)
    sys32 = out / 'sys32'
    sys32.mkdir()
    for name in engine.VC_RUNTIME:
        (sys32 / name).write_bytes(b'synthetic-runtime-presence')
    os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING='0',
                      R3HD_INSTALL_FAKE_LAUNCHER='0')
    reg = settings.load_registry()
    (out / 'engine').mkdir()
    engine_checks(reg, out / 'engine')
    ui_checks(reg, out)
    dry_run_checks(out)
    (out / 'result.json').write_bytes((json.dumps(checks, indent=2) + '\n').encode())
    print(f'DUALSENSE_SETTINGS PASS {len(checks)}/{len(checks)}; new installs on, 1.0.0 updates on, 1.0.1 homes kept, '
          'strength 0..100 slider (default 30), private-desktop persistence en/tr')


if __name__ == '__main__':
    main()
