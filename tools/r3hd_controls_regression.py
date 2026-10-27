#!/usr/bin/env python3
"""D-120: controls inventory and the narrowly shared Original PC V key.

Synthetic homes / private desktops only; no game, physical input or device output.
The real keyboard driver states are exercised by m32_regression.py (including 0x0300 for V).
"""
import json
import os
from pathlib import Path
import tempfile

import m30_launcher_regression as ui
import r3hd_installer as engine
import r3hd_settings as rs


def main():
    checks = []

    def check(name, ok):
        checks.append(bool(ok))
        print(('ok   ' if ok else 'FAIL ') + name)

    km = rs.load_keymap()
    original = rs.resolve_keyboard(km, explicit_layout='original_pc')
    modern = rs.resolve_keyboard(km)
    check('defaults: original W / X / V / V; Modern keeps Escape+Backspace / R / 1 / 3',
          [original['keys'][i] for i in ('b', 'y', 'left_shoulder', 'right_shoulder')]
          == [['W', 'Backspace'], ['X', ''], ['V', ''], ['V', '']]
          and [modern['keys'][i] for i in ('b', 'y', 'left_shoulder', 'right_shoulder')]
          == [['Escape', 'Backspace'], ['R', ''], ['1', ''], ['3', '']])
    check('menu safety: V produces no navigation / confirm / cancel / pause input',
          [i for i, keys in original['effective'].items() if 'V' in keys]
          == ['left_shoulder', 'right_shoulder'])
    check('Original PC camera retains Num8, W belongs only to Roll',
          original['effective']['rstick_up'] == ['Numpad8']
          and [i for i, keys in original['effective'].items() if 'W' in keys] == ['b'])
    for layout, changes in [('original_pc', {'left_shoulder': 'H'}),
                            ('original_pc', {'right_shoulder': 'H'}),
                            ('modern', {'left_shoulder': 'V', 'right_shoulder': 'V'})]:
        section = rs.keyboard_section(km, layout, changes)
        check(f'valid saved overrides roundtrip: {layout} {changes}',
              rs.resolve_keyboard(km, json.loads(json.dumps(section)))['state'] == 'saved')
    for changes in ({'left_shoulder': 'H', 'right_shoulder': 'H'},
                    {'a': 'V', 'left_shoulder': 'V', 'right_shoulder': 'V'},
                    {'x': 'V', 'left_shoulder': 'V', 'right_shoulder': 'V'}):
        try:
            rs.keyboard_section(km, 'original_pc', changes)
            refused = False
        except rs.Refused as e:
            refused = e.code == 'KEY_CONFLICT'
        check(f'collision protection: {changes}', refused)
    for changes, yielded in [({'x': 'V'}, {'left_shoulder': '1', 'right_shoulder': '3'}),
                              ({'x': 'X'}, {'y': 'R'}),
                              ({'rstick_up': 'W'}, {'b': 'Backspace'})]:
        section = rs.keyboard_section(km, 'original_pc', changes)
        resolved = rs.resolve_keyboard(km, section)
        check(f'older explicit overrides survive corrected defaults: {changes}',
              section['keys'] == {i: [v] for i, v in changes.items()}
              and all(resolved['keys'][i][0] == v for i, v in yielded.items()))

    saved = {k: os.environ.get(k) for k in engine.HOOKS}
    try:
        with tempfile.TemporaryDirectory(prefix='r3hd_controls_') as tmp:
            t = Path(tmp)
            sys32 = t / 'sys32'
            sys32.mkdir()
            for name in engine.VC_RUNTIME:
                (sys32 / name).write_bytes(b'x')
            os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING='0',
                              R3HD_INSTALL_FAKE_LAUNCHER='0')
            home = ui.make_home(t, 'home')

            def run(name, lines):
                code, dumps, log, out = ui.ui(home, t, name, '\n'.join(lines + ['click close', '']))
                check('private desktop: ' + name, code == 0)
                if code or not dumps:
                    raise RuntimeError(log or 'private desktop unavailable')
                return dumps

            def keys(d, name):
                return d['key.' + name].split(' caption=')[0]

            d = run('shared', ['page keys', 'layout original_pc', 'dump defaults',
                              'key left_shoulder 0', 'press 23', 'dump detached',
                              'key left_shoulder 0', 'press 2F', 'dump shared',
                              'key x 0', 'press 2F', 'dump refused',
                              'key right_shoulder 0', 'press 39', 'dump swaprefused',
                              'click save', 'dump saved'])
            check('capture V shares only the shoulders', keys(d['detached'], 'left_shoulder') == 'H,'
                  and keys(d['shared'], 'left_shoulder') == keys(d['shared'], 'right_shoulder') == 'V,')
            check('verified menu D-pad inputs are also visible on Keyboard',
                  all('visible=1 action=Menu ' in d['defaults']['key.' + i] for i in ('dpad_up', 'dpad_down')))
            check('third-input capture and swap of an old shared key are refused atomically',
                  all(keys(d[n], i) == keys(d['shared'], i)
                      for n in ('refused', 'swaprefused') for i in ('x', 'left_shoulder', 'right_shoulder'))
                  and all('This key is shared.' in d[n]['status'] for n in ('refused', 'swaprefused')))
            check('shared defaults persist as the layout, no redundant override',
                  ui.settings(home)['keyboard'] == {'layout': 'original_pc', 'keys': {}})
            d = run('reload', ['page keys', 'dump reloaded', 'key left_shoulder 0', 'press 23',
                              'click save', 'dump changed'])
            check('reopen restores both V assignments; detached override persists',
                  keys(d['reloaded'], 'left_shoulder') == keys(d['reloaded'], 'right_shoulder') == 'V,'
                  and ui.settings(home)['keyboard'] == {'layout': 'original_pc', 'keys': {'left_shoulder': ['H']}})
            d = run('restore', ['page keys', 'dump saved', 'click restore', 'dump restored', 'click save',
                               'layout modern', 'dump modern'])
            check('Restore Defaults restores shared V after reopening an override',
                  keys(d['saved'], 'left_shoulder') == 'H,'
                  and keys(d['restored'], 'left_shoulder') == keys(d['restored'], 'right_shoulder') == 'V,')
            check('Modern unaffected after switching layouts',
                  all(keys(d['modern'], i) == ','.join(modern['keys'][i]) for i in modern['keys']))
    finally:
        for k, value in saved.items():
            if value is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = value
    print(f'CONTROLS_REGRESSION {"PASS" if all(checks) else "FAIL"} checks={len(checks)} failures={checks.count(False)}')
    return int(not all(checks))


if __name__ == '__main__':
    raise SystemExit(main())
