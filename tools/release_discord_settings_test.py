"""Discord preference persistence through real Settings on a private desktop; synthetic homes only."""
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import sys

import m30_launcher_regression as launcher
import r3hd_installer as engine
import r3hd_settings as settings

ROOT = Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv) > 1:
        launcher.LAUNCHER = Path(sys.argv[1]).resolve()
    out = ROOT / 'private/work/release_discord' / ('settings_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir(parents=True)
    sys32 = out / 'sys32'
    sys32.mkdir()
    for name in engine.VC_RUNTIME:
        (sys32 / name).write_bytes(b'synthetic-runtime-presence')
    os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING='0',
                      R3HD_INSTALL_FAKE_LAUNCHER='0')
    reg = settings.load_registry()
    checks = []
    for language in ('en', 'tr'):
        t = out / language
        t.mkdir()
        home = launcher.make_home(t, 'home')
        engine.set_option(home, 'ui_language', language)
        engine.set_preset(home, 'hdplus', pairs=['gameplay_subtitles=all'], keyboard=('modern', {}))
        before = launcher.settings(home)
        assert settings.resolve(reg, settings=before)['values']['discord_presence'] == 'on'
        engine.set_option(home, 'discord_presence', 'off')
        after = launcher.settings(home)
        wanted = copy.deepcopy(before)
        wanted.setdefault('preferences', {})['discord_presence'] = 'off'
        assert after == wanted, (after, wanted)
        payload, tree, releases = engine.make_fixture(t)
        engine.install(home, payload, tree, releases=releases, log=lambda *_: None)
        assert launcher.settings(home) == after
        for value in ('on', 'off'):
            code, dumps, log, _ = launcher.ui(home, t, value,
                f'page advanced\nset discord_presence {value}\nclick save\nreload\ndump saved\nshot saved\nclick close\n')
            assert code == 0, log
            resolved = settings.resolve(reg, settings=launcher.settings(home))
            assert resolved['values']['discord_presence'] == value
            actual = launcher.settings(home)
            expected = copy.deepcopy(before)
            if value == 'off':
                expected.setdefault('preferences', {})['discord_presence'] = value
            assert actual == expected, (actual, expected)
            assert launcher.layout_ok(dumps['saved']), dumps['saved']
            checks.append({'language': language, 'value': value, 'pass': True})
    (out / 'result.json').write_bytes((json.dumps(checks, indent=2) + '\n').encode())
    print(f'DISCORD_SETTINGS PASS {len(checks)}/{len(checks)}; independent preference, upgrade, private-desktop persistence')


if __name__ == '__main__':
    main()
