"""Structural isolation checks for E-305; no executable is launched.

Actual timing/scoring evidence is judged separately by combo_countdown_check.py.
"""
import re
import tomllib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root / 'tools/m2_host/m2_trace.cpp').read_text()
body = source.split('void ComboCountdownTest(PPCRegister& object) {', 1)[1].split('\n}\n', 1)[0]
hooks = tomllib.loads((root / 'config/rexglue/r3hd_compat.toml').read_text())['midasm_hook']
checks = {
    'exact private update hook': [h for h in hooks if h['name'] == 'ComboCountdownTest'] ==
        [dict(address=0x8219F2D8, name='ComboCountdownTest', registers=['r3'])],
    'private mode and hidden gate': 'std::getenv("R3HD_NONINTRUSIVE")' in body and
        '!std::strcmp(v, "countdown")' in body and 'if (!enabled) return;' in body,
    'delayed mode waits for final second without changing the old mode':
        'if (!std::strcmp(v, "delayed-countdown")) return 2;' in body and
        'if (enabled == 2 && window - age > 1000) return;' in body and
        body.index('window - age > 1000') < body.index('M18Store('),
    'live fixture object and pending guard': all(s in body for s in
        ('"knaar_69\\0"', '0x8200FE2C', 'M18Load(object.u32 + 0x58) != 1',
         'M18Base()[0x40CDD6FE] != 1', 'M18Load(0x8288D618) != 2')),
    'only four presentation stores, no timer or score writes':
        re.findall(r'M18Store\((0x[0-9A-F]+),', body) ==
        ['0x8288D5AC', '0x8288D5B0', '0x8288D614', '0x8288D618'],
    'authoritative tick, preserved long remainder and earlier exact guard':
        'M18Load(0x82C0628C)' in body and '(window != 2000 && window != 6000)' in body and
        'enabled == 2 ? (window < 2000 || window > 6000)' in body and
        'age >= window' in body and 'float(window - age) / 1000.0f' in body,
    'no custom interpolation or command execution': all(s not in body for s in
        ('new ', 'malloc(', 'sub_8219', '0x8288D53C', 'sleep', 'thread')),
    'profile mode uses normal configuration independently of private mode':
        'std::getenv("R3HD_COMBO_CLOSE")' in source and
        'if (!v) return ComboProfileEnabled() ? 2 : 0;' in body,
    'public play clears option': "'R3HD_TEST_COMBO_CLOSE'" in (root / 'tools/play.ps1').read_text(),
    'playable gate requires both exact private flags':
        'std::getenv("R3HD_TEST_COMBO_PLAYTEST")' in source and
        '!std::strcmp(manual, "1")' in source and
        '!std::strcmp(mode, "delayed-countdown")' in source,
    'playable layout fails closed before presentation stores':
        '!ComboPlayableObject(object.u32) || !ComboPlayableLayout()' in body and
        'M18Load(mem + 8) != 0x40CDD5BC' in source and
        'M18Load(vars + 8) != 325' in source,
    'public play also clears manual opt-in':
        "'R3HD_TEST_COMBO_PLAYTEST'" in (root / 'tools/play.ps1').read_text(),
}
for label, ok in checks.items():
    print(('PASS ' if ok else 'FAIL ') + label)
print(f'COMBO_COUNTDOWN_SOURCE {"PASS" if all(checks.values()) else "FAIL"} checks={len(checks)}')
raise SystemExit(0 if all(checks.values()) else 1)
