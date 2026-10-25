#!/usr/bin/env python3
"""Synthetic installer + real bundled-mod policy: fresh, upgrade, reused settings.

No game, registry, shortcuts or real homes. Uses a tiny fabricated release/text
mod, not the Turkish release content. OUT must be a new directory under private/.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

import r3hd_bundled_mods as bundled
import r3hd_installer as engine
import r3hd_mods as mods
import r3hd_settings as settings

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('out', type=Path)
    a = ap.parse_args()
    out = a.out.resolve()
    if not out.is_relative_to(ROOT / 'private'):
        ap.error('OUT must be under private/')
    out.mkdir(parents=True, exist_ok=False)
    # The full build supplies its canonical game path. This fixture must resolve
    # only its fabricated HOME/data/content, never that inherited path.
    for key in ('R3HD_GAME_DIR', 'R3HD_HOME', 'R3HD_MODS_PLAN', 'R3HD_TEXT_PACKER'):
        os.environ.pop(key, None)
    # Only fabricated, non-executable payloads below this test's new OUT.
    os.environ['R3HD_INSTALL_FAKE_RUNNING'] = '0'
    os.environ['R3HD_INSTALL_FAKE_LAUNCHER'] = '0'
    payload, tree, _ = engine.make_fixture(out, version='1.0.1')
    fix = bytearray(128)
    slot = b'Hello\0'
    fix[64:70] = slot
    (tree / 'GAMEDATAbin/fix.lvl').write_bytes(fix)
    manifest = out / 'manifest.tsv'
    files = sorted(p for p in tree.rglob('*') if p.is_file())
    manifest.write_bytes(('\n'.join(f'{p.relative_to(tree).as_posix()}\t{p.stat().st_size}\t'
                                    f'{hashlib.sha256(p.read_bytes()).hexdigest()}' for p in files) + '\n').encode())
    release = engine.read_json(out / 'releases.json')
    release['releases'][0]['content'].update(files=len(files), bytes=sum(p.stat().st_size for p in files),
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
    engine.write_json(out / 'releases.json', release)
    releases = engine.load_releases(out / 'releases.json')
    reg = settings.load_registry()
    package = out / 'synthetic.zip'
    with zipfile.ZipFile(package, 'w') as z:
        z.writestr('mod.json', json.dumps({'format': 1, 'id': 'test.locale', 'name': 'Synthetic', 'version': '1.0.0',
            'target': {'title_id': '5841123F', 'releases': ['synthetic-release'], 'min_port_version': '0.29.0'},
            'overrides': [{'type': 'text', 'file': 'GAMEDATAbin/fix.lvl', 'offset': 64,
                           'slot_sha256': hashlib.sha256(mods.text_slot(bytes(fix), 64)).hexdigest(), 'text': 'Selam'}]}))
    checks = []

    def check(name, condition):
        checks.append({'name': name, 'pass': bool(condition)})
        print(('ok ' if condition else 'FAIL ') + name, flush=True)

    def install(home, lang):
        # Match the wizard: Installed comes from THIS home, not the global Inno AppId.
        existing = engine.read_state(home) is not None
        engine.install(home, payload, source=tree, preset='vanilla', releases=releases, ui_language=lang,
                       log=lambda _: None)
        return bundled.apply(home, package, 3 if existing else int(lang == 'tr'))

    def language(home):
        return settings.resolve(reg, settings=engine.read_json(home / 'settings.json'))['values']['ui_language']

    for lang in ('en', 'tr'):
        home = out / ('fresh_' + lang)
        r = install(home, lang)
        check('fresh ' + lang + ': UI language', language(home) == lang)
        check('fresh ' + lang + ': mod follows wizard',
              r['enabled'] == int(lang == 'tr') and (r['installed_version'] is not None) == (lang == 'tr'))
    for lang in ('en', 'tr'):
        for enabled in (False, True):
            home = out / f'upgrade_{lang}_{int(enabled)}'
            install(home, 'tr')
            engine.set_ui_language(home, lang)
            mods.cmd_set(bundled.paths_for(home), 'test.locale', enabled)
            before = (home / 'settings.json').read_bytes(), (home / 'mods/state.json').read_bytes()
            install(home, 'tr' if lang == 'en' else 'en')
            check(f'upgrade {lang} mod={enabled}: explicit choices preserved',
                  language(home) == lang and bundled.installed_info(bundled.paths_for(home), 'test.locale')['enabled'] == enabled
                  and before == ((home / 'settings.json').read_bytes(), (home / 'mods/state.json').read_bytes()))
    home = out / 'legacy'
    install(home, 'tr')
    doc = engine.read_json(home / 'settings.json')
    doc.get('preferences', {}).pop('ui_language', None)
    engine.write_json(home / 'settings.json', doc)
    install(home, 'tr')
    check('legacy no explicit locale: documented English fallback', language(home) == 'en')
    # Uninstall deliberately keeps user data. Reinstalling the same folder must keep
    # its language/mod choices even though Inno no longer sees an installed record.
    home = out / 'reused'
    install(home, 'en')
    bundled.apply(home, package, 2)
    mods.cmd_set(bundled.paths_for(home), 'test.locale', False)
    before = (home / 'settings.json').read_bytes(), (home / 'mods/state.json').read_bytes()
    engine.uninstall(home, releases=releases, log=lambda _: None)
    check('uninstall preserves configuration and removes installation identity',
          not (home / 'installer.json').exists() and (home / 'settings.json').exists())
    install(home, 'tr')
    check('reused folder with no record: English and disabled mod preserved',
          language(home) == 'en' and not bundled.installed_info(bundled.paths_for(home), 'test.locale')['enabled']
          and before == ((home / 'settings.json').read_bytes(), (home / 'mods/state.json').read_bytes()))
    # The person's 2026-10-18/19 setup logs: English setup into a new folder, uninstall, Turkish setup into the
    # same folder (no record, settings.json kept), then Turkish upgrades. The Settings language stays English
    # throughout and the Turkish game translation follows the setup independently of it.
    home = out / 'reused_then_upgrade'
    install(home, 'en')
    engine.uninstall(home, releases=releases, log=lambda _: None)
    install(home, 'tr')
    kept = (home / 'settings.json').read_bytes()
    check('reused folder: English Settings kept, Turkish translation added by the Turkish setup',
          language(home) == 'en' and bundled.installed_info(bundled.paths_for(home), 'test.locale')['enabled'])
    install(home, 'tr')
    check('later Turkish upgrade: English Settings and enabled translation kept, settings.json unchanged',
          language(home) == 'en' and bundled.installed_info(bundled.paths_for(home), 'test.locale')['enabled']
          and (home / 'settings.json').read_bytes() == kept)
    engine.set_ui_language(home, 'tr')
    install(home, 'en')
    check('Settings language chosen after that survives an English upgrade', language(home) == 'tr')
    # A different new folder is fresh, regardless of another installed home/AppId.
    home = out / 'new_path'
    install(home, 'tr')
    check('new empty path alongside prior homes is fresh Turkish',
          language(home) == 'tr' and bundled.installed_info(bundled.paths_for(home), 'test.locale')['enabled'])
    report = {'synthetic_only': True, 'checks': checks}
    (out / 'result.json').write_bytes((json.dumps(report, indent=1) + '\n').encode())
    ok = sum(x['pass'] for x in checks)
    print(f'UX_DEFAULTS {"PASS" if ok == len(checks) else "FAIL"} {ok}/{len(checks)}')
    return int(ok != len(checks))


if __name__ == '__main__':
    raise SystemExit(main())
