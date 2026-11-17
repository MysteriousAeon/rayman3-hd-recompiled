"""HD+ out-of-range lock-on colour (D-221): focused profile, launcher, patch-order and run-log regressions; never
starts a game.

  python tools/r3hd_lockon_regression.py                 static checks (registry, launchers, patch chain, SDK text)
  python tools/r3hd_lockon_regression.py --run RUN...    also judge hidden runs under private/work/m6_runs: one mode
                                                         line, and the restored page only in runs named *_on_*
"""
import json
import re
import sys
from pathlib import Path

import r3hd_settings as settings

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / 'external' / 'rexglue-sdk'
KEY = 'lockon_far_color'
reg = settings.load_registry()
checks = 0


def check(ok, label):
    global checks
    checks += 1
    if not ok:
        raise AssertionError(label)


def read(path):
    return Path(path).read_text(encoding='utf-8')


# Profiles: Vanilla keeps the HD page, HD+ restores, Custom keeps its base and override, explicit A/B override wins.
check(settings.resolve(reg, 'vanilla')['values'][KEY] == 'original', 'Vanilla keeps Xbox 360 HD')
check(settings.resolve(reg, 'hdplus')['values'][KEY] == 'restored', 'HD+')
for base in ('vanilla', 'hdplus'):
    for value in ('original', 'restored'):
        doc = settings.make_settings(reg, 'custom', base, [f'{KEY}={value}'])
        resolved = settings.resolve(reg, settings=doc)
        check(resolved['values'][KEY] == value, f'Custom {base}/{value}')
        check(resolved['base'] == base, 'Custom base retained')
check(settings.resolve(reg, 'hdplus', explicit={KEY: 'original'})['values'][KEY] == 'original', 'explicit A/B override')
entry = reg['settings'][KEY]
check(entry['category'] == 'hd_correction' and entry['launcher'] == 'LockonColor', 'registry entry')
check(entry['values'] == ['original', 'restored'], 'registry values')
# Independent of the accepted swirl and canister restorations.
for other in ('power_swirl', 'beam_color'):
    check(settings.resolve(reg, 'hdplus')['values'][other] == 'restored', other + ' HD+ unchanged')
    doc = settings.make_settings(reg, 'custom', 'hdplus', [f'{KEY}=original'])
    check(settings.resolve(reg, settings=doc)['values'][other] == 'restored', 'override leaves ' + other + ' alone')

# Localization: label and help present in English and Turkish.
strings = json.loads(read(ROOT / 'config/settings/ui_strings.json'))['strings']
for text in (entry['label'], entry['help']):
    row = strings.get(text, {})
    check(row.get('en') == text and bool(row.get('tr')), 'ui string ' + text[:40])

# Launchers: parameter, mapping, environment set and restored, session record; Windows/Linux parity.
play = read(ROOT / 'tools/play.ps1')
check("[ValidateSet('original', 'restored')][string]$LockonColor = 'original'" in play, 'parameter contract')
for token in ("LockonColor = 'lockon_far_color'", "$env:R3HD_LOCKON_COLOR = $LockonColor",
              "$env:R3HD_LOCKON_COLOR = $savedLockonColor", "lockon_far_color = $LockonColor"):
    check(token in play, 'launcher lifecycle ' + token)
check(play.count('lockon_far_color = $LockonColor') == 2, 'launch record and result record')
linux = read(ROOT / 'tools/linux/r3hd_play.py')
check('"LockonColor": "lockon_far_color"' in linux and '"R3HD_LOCKON_COLOR": "LockonColor"' in linux,
      'Linux launcher maps')

# Header: one page in the fix bundle, no texel bytes, gating and switch; normal reticle pages not listed.
header = read(ROOT / 'tools/r3hd_lockon_color.h')
check('R3HD_LOCKON_COLOR' in header and 'strcmp(value, "restored") == 0' in header, 'exact switch value')
check('kRefusedStored' in header and 'kRefusedResult' in header and 'kRefusedSize' in header, 'hash and size gates')
check(re.findall(r'\{"([a-z_]+\.dds)"', header) == ['ago_targetfar.dds'], 'only the far-indicator page')
check(re.findall(r'\{"([a-z_0-9]+\.btf)", ', header) == ['fix.btf'], 'fix bundle only')
check(not re.search(r'\{(?:\s*0x[0-9A-Fa-f]{2},){32}', header), 'no byte arrays (no title texels)')

# Patch chain: last step, so no earlier anchor moves; focused test in the replay.
bat = read(ROOT / 'tools/build_milestone8.bat')
check(bat.index('r3hd_beam_runtime_patch.py') < bat.index('r3hd_display_vsync_patch.py')
      < bat.index('r3hd_lockon_runtime_patch.py') < bat.index('cmake -S external'), 'patch runs last, before configure')
check('call tools\\build_lockon_test.bat' in bat, 'focused test in the replay')
hpf = SDK / 'src/filesystem/devices/host_path_file.cpp'
if hpf.exists() and 'r3hdlockon::' in read(hpf):
    text = read(hpf)
    i26, ib, il, i33 = (text.index(x) for x in ('m26tex::AfterRead(', 'r3hdbeam::AfterRead(', 'r3hdlockon::AfterRead(',
                                                  'm33mods::AfterRead('))
    check(i26 < ib < il < i33, 'SDK: M26, beam, lock-on, then M33 (mods win)')
    check(text.count('r3hdlockon::AfterRead(') == 1, 'SDK: one call')
    cp = read(SDK / 'src/graphics/d3d12/command_processor.cpp')
    check(cp.count('REXGPU_INFO("R3HD lockon_color={}"') == 1, 'SDK: one mode line')
    check('R3HD beam_color={}", r3hdbeam::Enabled() ? "restored" : "original");\n'
          '  REXGPU_INFO("R3HD lockon_color={}"' in cp, 'SDK: mode line beside the beam line')
else:
    print('r3hd_lockon_regression note: SDK tree not patched with the lock-on step; SDK text checks skipped')

if '--run' in sys.argv:
    for name in sys.argv[sys.argv.index('--run') + 1:]:
        run = ROOT / 'private/work/m6_runs' / name
        log = '\n'.join(p.read_text(encoding='utf-8', errors='replace') for p in sorted(run.glob('runtime*.log')))
        check(bool(log), name + ' log')
        modes = re.findall(r'R3HD lockon_color=(\w+)', log)
        expected = 'restored' if '_on_' in name else 'original'
        check(modes == [expected], name + ' mode ' + repr(modes))
        states = re.findall(r'R3HD lockon_color file=\S+ page=(\S+) state=(\w+)', log)
        served = re.findall(r'R3HD lockon_color file=\S+ page=(\S+) served_bytes=32768', log)
        if expected == 'restored':
            check(states == [('ago_targetfar.dds', 'restored')], name + ' page restored ' + repr(states))
            check(served == ['ago_targetfar.dds'], name + ' page fully served')
        else:
            check(not states, name + ' nothing restored')
print(f'R3HD_LOCKON_REGRESSION PASS checks={checks}')
