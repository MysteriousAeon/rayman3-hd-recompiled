#!/usr/bin/env python3
"""Bounded 1.0.1 integration on synthetic homes; no game or visible desktop.

SETUP PREVIOUS PACKAGE OUT: install EN/HD+ and TR/Vanilla, upgrade 1.0.0,
check installed Settings on a private desktop. OUT must be new. Game data is
retained for separately logged verification/cleanup; no user installation is used.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import m48_replay_check as rc
from m48p_lifecycle import mod_rows, stand_ins, user_hashes
import r3hd_installer as engine
import r3hd_settings as settings


def same_keyboard(before, after):
    """Saving can make a yielded Walk binding explicitly empty; effective bindings must remain identical."""
    km = settings.load_keymap()
    old, new = (settings.resolve_keyboard(km, doc) for doc in (before, after))
    return old['layout'] == new['layout'] and old['args'] == new['args'] and not new['warnings']


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('setup', 'previous', 'package', 'out'):
        ap.add_argument(name, type=Path)
    a = ap.parse_args()
    a.setup, a.previous, a.package, a.out = (p.resolve() for p in (a.setup, a.previous, a.package, a.out))
    a.out.mkdir(parents=True, exist_ok=False)
    menu, desk = a.out / 'menu', a.out / 'desktop'
    menu.mkdir()
    desk.mkdir()
    sc = [f'/STARTMENUDIR={menu}', f'/DESKTOPDIR={desk}']
    reg = settings.load_registry()

    def install(setup, home, tag, language, preset=None):
        args = [f'/LANG={language}', f'/DIR={home}', *sc]
        if preset:
            args += [f'/PACKAGE={a.package}', f'/PRESET={preset}']
        code, _, log = rc.setup(setup, a.out, tag, *args)
        rc.check(tag + ': setup exit zero', code == 0, log[-500:])
        if code:
            raise RuntimeError(tag + ': setup failed; see log')

    def resolve(home):
        return settings.resolve(reg, settings=engine.read_json(home / 'settings.json'))

    def ui(home, tag, commands):
        out = a.out / tag
        out.mkdir()
        script = out / 'commands.txt'
        script.write_bytes(('\n'.join(commands) + '\n').encode())
        env = {k: v for k, v in os.environ.items() if k not in ('R3HD_HOME', 'R3HD_GAME_DIR', 'R3HD_BIN_DIR', 'R3HD_PLAY_ROOT')}
        r = subprocess.run([str(home / 'app/r3hd_launcher.exe'), '--home', str(home),
                            '--ui-test', str(script), '--out', str(out)], capture_output=True, env=env, timeout=180)
        (out / 'process.log').write_bytes(r.stdout + r.stderr)
        rc.check(tag + ': actual installed Settings exit zero', r.returncode == 0, r.stdout + r.stderr)
        return {p.stem: dict(line.split('=', 1) for line in p.read_text(encoding='utf-8').splitlines() if '=' in line)
                for p in out.glob('*.txt') if p != script}

    for lang, preset, subs in [('en', 'hdplus', 'all'), ('tr', 'vanilla', 'original')]:
        home = a.out / ('fresh_' + lang)
        install(a.setup, home, 'fresh_' + lang, lang, preset)
        result = resolve(home)
        rc.check(lang + ': fresh locale/profile/subtitle defaults',
                 result['values']['ui_language'] == lang and result['preset'] == preset
                 and result['values']['gameplay_subtitles'] == subs, result)
        rc.check(lang + ': Turkish mod follows setup language',
                 mod_rows(home) == ([('tr.full.dev', '1.0.0', True)] if lang == 'tr' else []))
        rc.check(lang + ': local thumbnail icon equals package thumbnail',
                 (home / 'data/play_icon.ico').read_bytes() == engine.play_icon_bytes(a.package))
        dumps = ui(home, 'ui_' + lang, ['dump initial', 'page controls', 'dump controls',
                   'page mods', 'dump mods', 'page advanced', 'dump advanced', 'page settings',
                   'set render_scale 2', 'dump edited', 'language ' + ('tr' if lang == 'en' else 'en'),
                   'dump switched', 'click close'])
        rc.check(lang + ': all pages keep the header/version and fit',
                 all(dumps.get(p, {}).get('interface_language_visible') == '1'
                     and dumps.get(p, {}).get('version_visible') == '1'
                     and 'overlaps=0' in dumps.get(p, {}).get('controls', '')
                     and 'outside=0' in dumps.get(p, {}).get('controls', '')
                     for p in ('initial', 'controls', 'mods', 'advanced')), dumps)
        rc.check(lang + ': immediate switch keeps dirty edits',
                 dumps.get('edited', {}).get('dirty') == dumps.get('switched', {}).get('dirty') == '1'
                 and all(dumps.get('edited', {}).get(k) == dumps.get('switched', {}).get(k)
                         for k in dumps.get('edited', {}) if k.startswith('setting.') or k in ('profile', 'page')))
        rc.check(lang + ': locale changes leave mods independent',
                 mod_rows(home) == ([('tr.full.dev', '1.0.0', True)] if lang == 'tr' else []))

    home = a.out / 'upgrade'
    install(a.previous, home, 'previous_100', 'tr', 'hdplus')
    stand_ins(home)
    rc.mods(home, 'disable', 'tr.full.dev')
    doc = engine.read_json(home / 'settings.json')
    # Reproduce 1.0.0's preference-only Custom, with explicit future locale and key edits.
    doc.update(preset='custom', base='hdplus', overrides={'gameplay_subtitles': 'all'},
               keyboard={'layout': 'modern', 'keys': {'x': ['Control']}})
    doc.setdefault('preferences', {}).update(ui_language='tr', render_scale='2')
    (home / 'settings.json').write_bytes((json.dumps(doc) + '\n').encode())
    before = user_hashes(home)
    mods_before = {n: rc.tree_hash(home / 'mods' / n) for n in ('state.json', 'installed')}
    install(a.setup, home, 'upgrade_101_en', 'en')
    rc.check('1.0.0 upgrade: saves/history/sessions/settings byte-identical', user_hashes(home) == before)
    rc.check('1.0.0 upgrade: mod order/state/content byte-identical',
             {n: rc.tree_hash(home / 'mods' / n) for n in mods_before} == mods_before)
    v = resolve(home)
    rc.check('1.0.0 upgrade: preference-only Custom resolves HD+; language/subtitles/keys retained',
             v['preset'] == 'hdplus' and v['values']['ui_language'] == 'tr'
             and v['values']['gameplay_subtitles'] == 'all'
             and engine.read_json(home / 'settings.json')['keyboard'] == doc['keyboard'], v)
    dumps = ui(home, 'ui_upgrade', ['dump before', 'set render_scale 3', 'set render_scale 2',
                                  'click save', 'reload', 'dump after', 'click close'])
    saved = engine.read_json(home / 'settings.json')
    rc.check('1.0.0 upgrade: installed Settings saves migrated HD+ with independent subtitles',
             saved['preset'] == 'hdplus' and saved['preferences']['gameplay_subtitles'] == 'all'
             and saved['preferences']['ui_language'] == 'tr' and same_keyboard(doc['keyboard'], saved['keyboard']), saved)
    # Off is also an independent explicit choice across another-language repair/update.
    code, _, text = rc.run_json(home, 'r3hd_installer.py', 'set-option', '--set', 'gameplay_subtitles=original')
    rc.check('subtitles Off set without changing HD+', code == 0 and resolve(home)['preset'] == 'hdplus', text)
    before = user_hashes(home)
    install(a.setup, home, 'upgrade_101_tr_off', 'tr')
    rc.check('update/repair preserves Off and all saved preferences', user_hashes(home) == before
             and resolve(home)['values']['gameplay_subtitles'] == 'original')
    report = {'version': '1.0.1', 'checks': rc.checks}
    (a.out / 'result.json').write_bytes((json.dumps(report, indent=1) + '\n').encode())
    ok = sum(c['ok'] for c in rc.checks)
    print(f'RELEASE_101_CHECK {"PASS" if ok == len(rc.checks) else "FAIL"} {ok}/{len(rc.checks)}')
    return int(ok != len(rc.checks))


if __name__ == '__main__':
    sys.exit(main())
