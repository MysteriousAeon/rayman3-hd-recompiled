#!/usr/bin/env python3
"""Focused bilingual Settings checks; synthetic data and private desktops only.

No game launch, personal installation, system DPI change or setup lifecycle.
Artifacts remain in private/work/settings-localization-test/<timestamp>.
The DPI commands simulate WM_DPICHANGED; they do not verify a physical monitor.
"""
import argparse
import copy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys

import m30_launcher_regression as launcher
import r3hd_installer as engine
import r3hd_settings as settings
import r3hd_ui_locale as locale

ROOT = Path(__file__).resolve().parents[1]


def digest_tree(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--catalog-only', action='store_true')
    args = ap.parse_args()
    out = ROOT / 'private/work/settings-localization-test' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out.mkdir(parents=True)
    checks = []

    def check(name, condition, detail=None):
        checks.append({'name': name, 'pass': bool(condition), 'detail': detail})

    catalog = locale.load()
    result = locale.check()
    check('source and model strings: both locales, no missing/unused/invalid keys',
          not any(result[k] for k in ('missing', 'unused', 'invalid')), result)
    check('English fallback for an unknown locale', locale.rows('unknown') == locale.rows('en'))
    check('Turkish Unicode characters survive UTF-8 catalog decoding',
          set('çğıöşüİ') <= set(''.join(v['tr'] for v in catalog.values())))
    for english, turkish in {'Bog of Murk': 'Kasvet Bataklığı',
                             'Land of the Livid Dead': 'Solgun Ölüler Diyarı',
                             'Hoodlum Headquarters': 'Hoodlum Karargâhı'}.items():
        relevant = [v for v in catalog.values() if english in v['en']]
        check('approved Turkish level name: ' + english,
              bool(relevant) and all(turkish in v['tr'] and english not in v['tr'] for v in relevant)
              and not any(english in v['tr'] for v in catalog.values()))
    original_load = locale.load
    try:
        sample = next(iter(locale.model_keys()))
        cases = []
        damaged = copy.deepcopy(catalog)
        del damaged[sample]
        cases.append(('missing key', damaged, 'missing', sample))
        damaged = copy.deepcopy(catalog)
        damaged['Unused localization audit sentinel'] = {'en': 'Unused localization audit sentinel', 'tr': 'Sentinel'}
        cases.append(('unused key', damaged, 'unused', 'Unused localization audit sentinel'))
        damaged = copy.deepcopy(catalog)
        damaged[sample]['tr'] = ''
        cases.append(('empty translation', damaged, 'invalid', sample))
        damaged = copy.deepcopy(catalog)
        damaged[sample]['tr'] += ' {unexpected}'
        cases.append(('placeholder mismatch', damaged, 'invalid', sample))
        for name, data, field, key in cases:
            locale.load = lambda data=data: data
            check('catalog refuses ' + name, key in locale.check()[field])
    finally:
        locale.load = original_load

    if not args.catalog_only:
        check('built launcher exists', launcher.LAUNCHER.is_file())
        if launcher.LAUNCHER.is_file():
            saved_env = {k: os.environ.get(k) for k in engine.HOOKS}
            sys32 = out / 'sys32'
            sys32.mkdir()
            for name in engine.VC_RUNTIME:
                (sys32 / name).write_bytes(b'synthetic-runtime-presence')
            os.environ.update(R3HD_INSTALL_SYSTEM32=str(sys32), R3HD_INSTALL_FAKE_RUNNING='0',
                              R3HD_INSTALL_FAKE_LAUNCHER='0')
            try:
                payload, tree, releases = engine.make_fixture(out)

                def values(home):
                    return settings.resolve(settings.load_registry(), settings=launcher.settings(home))

                def run(home, name, commands):
                    code, dumps, log, _ = launcher.ui(home, out, name, '\n'.join(commands) + '\n')
                    check(name + ': private-desktop script succeeds', code == 0, {'code': code, 'log': log})
                    return dumps, log

                homes = {}
                for language in ('en', 'tr'):
                    home = out / ('fresh_' + language)
                    engine.install(home, payload, tree, 'hdplus', releases=releases,
                                   ui_language=language, log=lambda *_: None)
                    homes[language] = home
                    initial = values(home)
                    check('fresh ' + language + ': initial UI language and HD+ subtitles',
                          initial['values']['ui_language'] == language and initial['label'] == 'hdplus'
                          and initial['values']['gameplay_subtitles'] == 'all')
                    before = launcher.settings(home)
                    engine.install(home, payload, tree, releases=releases,
                                   ui_language='tr' if language == 'en' else 'en', log=lambda *_: None)
                    check('upgrade ' + language + ': explicit language and settings preserved',
                          launcher.settings(home) == before)
                    commands = []
                    for dpi in (96, 120, 144):
                        commands.append('dpi ' + str(dpi))
                        for page in ('settings', 'controls', 'advanced', 'mods'):
                            tag = page + '_' + str(dpi)
                            commands.extend(['page ' + page, 'dump ' + tag, 'shot ' + tag])
                    commands.append('click close')
                    dumps, _ = run(home, 'pages_' + language, commands)
                    for dpi in (96, 120, 144):
                        for page in ('settings', 'controls', 'advanced', 'mods'):
                            tag = page + '_' + str(dpi)
                            d = dumps.get(tag, {})
                            check(language + ' ' + tag + ': layout, locale and visible captions',
                                  launcher.layout_ok(d) and d.get('ui_language') == language
                                  and d.get('page') == page and bool(d.get('window_title'))
                                  and any(k.startswith('visible.') and v for k, v in d.items()), d)
                            check(language + ' ' + tag + ': persistent interface selector and version fit',
                                  d.get('interface_language_visible') == '1' and d.get('version_visible') == '1'
                                  and d.get('interface_language_label') == ('Arayüz dili' if language == 'tr' else 'Interface language')
                                  and d.get('interface_language_options') == 'English,Türkçe'
                                  and d.get('header_clipped') == '0' and d.get('turkish_glyphs') == '1', d)
                            if page == 'controls':
                                check(language + ' ' + tag + ': fixed summary absent; rebinding instructions retained',
                                      d.get('layout_text') == '' and
                                      catalog['Click a key to change it, then press the new key (Esc cancels). Right-click a key or press Delete to remove it. '][language]
                                      in d.get('controls_note', ''), d)
                            if page == 'settings':
                                visible = '\n'.join(v for k, v in d.items() if k.startswith('visible.'))
                                check(language + ' ' + tag + ': concise correction copy has no development qualifier',
                                      catalog['Correct Robo-Pirate statue textures'][language] in visible
                                      and not any(s in visible for s in ('provisional', 'deneme aşamasında', 'Part of HD+', 'HD+ kapsamında')), visible)
                            check(language + ' ' + tag + ': mod state tokens stay language-neutral',
                                  d.get('mod_state.active') == catalog['Active'][language]
                                  and d.get('mod_state.partial') == catalog['Active (partly covered by a mod above it)'][language]
                                  and d.get('mod_state.off') == catalog['Off'][language]
                                  and catalog['The mod package is invalid. Choose a valid mod ZIP or folder.'][language] in d.get('mod_state.invalid', ''))
                            if language == 'tr':
                                check('Turkish ' + tag + ': Unicode title and navigation',
                                      'Ayarlar' in d.get('window_title', '')
                                      and any('Kaydet' in v for k, v in d.items() if k.startswith('visible.')))

                    commands = ['page controls', 'layout original_pc']
                    for dpi in (96, 120, 144):
                        commands += ['dpi ' + str(dpi), 'dump original_' + str(dpi), 'shot original_' + str(dpi)]
                    commands += ['click close']
                    dumps, _ = run(home, 'original_controls_' + language, commands)
                    for dpi in (96, 120, 144):
                        d = dumps.get('original_' + str(dpi), {})
                        check(language + ' original controls ' + str(dpi) + ': summary absent and table fits',
                              launcher.layout_ok(d) and d.get('layout_text') == ''
                              and d.get('key_layout') == 'original_pc' and bool(d.get('controls_note'))
                              and d.get('key.a', '').startswith('C,'), d)

                home = homes['en']
                for path, data in [('profiles/test/save.bin', b'synthetic-save'),
                                   ('mods/state.json', b'{"schema":1,"mods":[]}\n'),
                                   ('mods/personal-note.txt', b'synthetic-mod-order-sentinel'),
                                   ('save_history/session/slot.bin', b'synthetic-history')]:
                    p = home / path
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(data)
                protected = {name: digest_tree(home / name) for name in ('profiles', 'mods', 'save_history', 'data', 'app')}
                persisted = launcher.settings(home)
                dumps, _ = run(home, 'unsaved', [
                    'profile vanilla', 'set render_scale 2', 'set gameplay_subtitles original',
                    'page controls', 'key x 0', 'press 2F', 'dump before',
                    'language tr', 'dump after_tr', 'language en', 'dump after_en', 'click close'])
                before = dumps.get('before', {})
                fields = ['profile', 'custom_base', 'dirty', 'key_layout', 'page']
                fields += [k for k in before if k.startswith('setting.')]
                # Captions/actions translate, physical binding tokens do not.
                def edits(d):
                    return {**{k: d.get(k) for k in fields},
                            **{k: v.split(' caption=', 1)[0] for k, v in d.items() if k.startswith('key.')}}
                check('unsaved edits remain dirty before switching', before.get('dirty') == '1')
                for language in ('tr', 'en'):
                    d = dumps.get('after_' + language, {})
                    check('switch ' + language + ': unsaved profile/options/keys/page retained',
                          d.get('ui_language') == language and edits(d) == edits(before), d)
                check('language-only persistence leaves saved gameplay settings byte-equivalent',
                      {k: v for k, v in launcher.settings(home).items() if k != 'preferences'} ==
                      {k: v for k, v in persisted.items() if k != 'preferences'}
                      and {k: v for k, v in launcher.settings(home).get('preferences', {}).items() if k != 'ui_language'} ==
                      {k: v for k, v in persisted.get('preferences', {}).items() if k != 'ui_language'})
                dumps, log = run(home, 'save_reload', ['language tr', 'reload', 'dump reloaded',
                                                     'page controls', 'key a 0', 'press 3E',
                                                     'dump reserved', 'press 01', 'click close'])
                check('saved locale loads in a new model', dumps.get('reloaded', {}).get('ui_language') == 'tr')
                check('reserved key feedback translated',
                      any(v['tr'] in log or v['tr'] in dumps.get('reserved', {}).get('status', '')
                          for key, v in catalog.items() if 'debug overlay' in key or 'settings overlay' in key), log)
                for name, digests in protected.items():
                    check('language changes preserve synthetic ' + name + ' bytes', digest_tree(home / name) == digests)
                # Application-owned mod failures and confirmations use the active locale, without a modal UI.
                bad = out / 'not-a-mod.zip'
                import zipfile
                with zipfile.ZipFile(bad, 'w') as archive:
                    archive.writestr('README.txt', 'synthetic invalid package')
                for language in ('en', 'tr'):
                    d, journal = run(home, 'messages_' + language, [
                        'language ' + language, 'page mods', 'mod import ' + str(bad), 'dump refused',
                        'page controls', 'key a 0', 'press 3E', 'press 01',
                        'page settings', 'set render_scale 2', 'click close'])
                    refused = d.get('refused', {}).get('status', '')
                    check(language + ': mod rejection is localized and actionable',
                          catalog['The mod package is invalid. Choose a valid mod ZIP or folder.'][language] in refused,
                          refused)
                    check(language + ': unsaved-close confirmation is localized',
                          catalog['Save your changes before closing?'][language] in journal, journal)
                legacy = out / 'legacy'
                engine.install(legacy, payload, tree, 'vanilla', releases=releases, log=lambda *_: None)
                doc = launcher.settings(legacy)
                doc.get('preferences', {}).pop('ui_language', None)
                (legacy / 'settings.json').write_bytes((json.dumps(doc) + '\n').encode())
                check('legacy settings without language default to English', values(legacy)['values']['ui_language'] == 'en')
            finally:
                for key, value in saved_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
    report = {'checks': checks, 'passed': sum(c['pass'] for c in checks), 'total': len(checks),
              'dpi_scope': 'simulated WM_DPICHANGED on a private desktop; not physical monitor verification',
              'catalog_only': args.catalog_only}
    (out / 'result.json').write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    failures = [c['name'] for c in checks if not c['pass']]
    print('SETTINGS_LOCALIZATION_TEST ' + ('FAIL' if failures else 'PASS') +
          f" {report['passed']}/{report['total']}")
    for failure in failures:
        print('FAIL ' + failure)
    print('Detailed results: ' + str(out / 'result.json'))
    return int(bool(failures))


if __name__ == '__main__':
    sys.exit(main())
