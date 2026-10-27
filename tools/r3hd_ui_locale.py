#!/usr/bin/env python3
"""Settings UI catalog. English source keys are canonical; unknown locales fall back to English.

No game strings, mod operations or platform locale dependency. check() audits live source/model coverage.
"""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'config/settings/ui_strings.json'


def load():
    data = json.loads(CATALOG.read_text(encoding='utf-8'))
    if data.get('schema') != 1:
        raise ValueError('unsupported UI catalog schema')
    return data['strings']


def rows(language):
    language = language if language in ('en', 'tr') else 'en'
    return [(key, value.get(language) or value['en']) for key, value in load().items()]


def model_keys():
    reg = json.loads((ROOT / 'config/settings/registry.json').read_text(encoding='utf-8'))
    km = json.loads((ROOT / 'config/controls/keymap.json').read_text(encoding='utf-8'))
    out = set(reg['groups'].values())
    for v in reg['preset_ui'].values():
        out.update((v['name'], v['text']))
    for s in reg['settings'].values():
        if s['category'] == 'mandatory':
            continue
        out.update([s['label'], s.get('help', ''), *s.get('value_labels', {}).values()])
    for v in km['layouts'].values():
        out.update((v['name'], v['text']))
    out.update(g['name'] for g in km['groups'])
    for i in km['inputs']:
        out.update((i['action'], i['pad']))
    out.update(k.get('label', k['name']) for k in km['keys'])
    out.update(km['reserved'].values())
    pm = json.loads((ROOT / 'config/controls/padmap.json').read_text(encoding='utf-8'))  # D-115: drop-down labels
    out.update(b['xbox'] if b['xbox'] == b['playstation'] else f"{b['xbox']} / {b['playstation']}"
               for b in pm['buttons'] + pm['analog'])
    out.update(g['name'] for g in pm['groups'])  # D-116: the Controller tab's groups and actions
    out.update(a['name'] for a in pm['actions'])
    import r3hd_installer
    out.update(o['note'] for o in r3hd_installer.describe_options() if o['note'])
    out.add('Escape and Enter also work as Back and Start when no other control uses them.')
    return out - {''}


def source_keys():
    source = (ROOT / 'tools/launcher/r3hd_launcher.cpp').read_text(encoding='utf-8')
    # Explicit T/F calls are also the source inventory; concatenated literals are allowed.
    keys = set()
    for m in re.finditer(r'\b(?:T|F)\((L"(?:[^"\\]|\\.)*"(?:\s*L"(?:[^"\\]|\\.)*")*)', source):
        keys.add(''.join(json.loads('"' + s + '"') for s in re.findall(r'L"((?:[^"\\]|\\.)*)"', m[1])))
    return keys


def check():
    catalog = load()
    required = source_keys() | model_keys()
    missing = required - catalog.keys()
    unused = catalog.keys() - required
    invalid = [k for k, v in catalog.items() if set(v) != {'en', 'tr'} or v['en'] != k or not v['tr']
               or set(re.findall(r'\{\w+\}', k)) != set(re.findall(r'\{\w+\}', v['tr']))]
    source = (ROOT / 'tools/launcher/r3hd_launcher.cpp').read_text(encoding='utf-8')
    if re.search(r'(?:==|!=)\s*T\(', source):
        invalid.append('translated comparison: internal tokens must stay language-neutral')
    return {'missing': sorted(missing), 'unused': sorted(unused), 'invalid': invalid, 'keys': len(catalog)}


if __name__ == '__main__':
    r = check()
    print(json.dumps(r, ensure_ascii=True, indent=2))
    raise SystemExit(bool(r['missing'] or r['unused'] or r['invalid']))
