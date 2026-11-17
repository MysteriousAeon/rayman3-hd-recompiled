"""HD+ beam colour restoration (D-219): focused profile, launcher, patch-order and run-log regressions; never starts a game.

  python tools/r3hd_beam_regression.py                 static checks (registry, launchers, patch chain, SDK text)
  python tools/r3hd_beam_regression.py --run RUN...    also judge hidden runs under private/work/m6_runs: one mode
                                                       line, and restored pages only in runs named *_on_*
"""
import re
import sys
from pathlib import Path

import r3hd_settings as settings

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / 'external' / 'rexglue-sdk'
reg = settings.load_registry()
checks = 0


def check(ok, label):
    global checks
    checks += 1
    if not ok:
        raise AssertionError(label)


def read(path):
    return Path(path).read_text(encoding='utf-8')


# Profiles: Vanilla keeps the HD pages, HD+ restores, Custom keeps its base and override, explicit A/B override wins.
check(settings.resolve(reg, 'vanilla')['values']['beam_color'] == 'original', 'Vanilla')
check(settings.resolve(reg, 'hdplus')['values']['beam_color'] == 'restored', 'HD+')
for base in ('vanilla', 'hdplus'):
    for value in ('original', 'restored'):
        doc = settings.make_settings(reg, 'custom', base, [f'beam_color={value}'])
        resolved = settings.resolve(reg, settings=doc)
        check(resolved['values']['beam_color'] == value, f'Custom {base}/{value}')
        check(resolved['base'] == base, 'Custom base retained')
check(settings.resolve(reg, 'hdplus', explicit={'beam_color': 'original'})['values']['beam_color'] == 'original',
      'explicit A/B override')
entry = reg['settings']['beam_color']
check(entry['category'] == 'hd_correction' and entry['launcher'] == 'BeamColor', 'registry entry')
# Independent of the accepted swirl restoration.
check(settings.resolve(reg, 'hdplus')['values']['power_swirl'] == 'restored', 'swirl HD+ unchanged')
doc = settings.make_settings(reg, 'custom', 'hdplus', ['beam_color=original'])
check(settings.resolve(reg, settings=doc)['values']['power_swirl'] == 'restored', 'beam override leaves swirl alone')

# Launchers: parameter, mapping, environment set and restored, session record.
play = read(ROOT / 'tools/play.ps1')
check("[ValidateSet('original', 'restored')][string]$BeamColor = 'original'" in play, 'parameter contract')
for token in ("BeamColor = 'beam_color'", "$env:R3HD_BEAM_COLOR = $BeamColor",
              "$env:R3HD_BEAM_COLOR = $savedBeamColor", "beam_color = $BeamColor"):
    check(token in play, 'launcher lifecycle ' + token)
linux = read(ROOT / 'tools/linux/r3hd_play.py')
check('"BeamColor": "beam_color"' in linux and '"R3HD_BEAM_COLOR": "BeamColor"' in linux, 'Linux launcher maps')

# Header: no texel bytes, gating and switch.
header = read(ROOT / 'tools/r3hd_beam_color.h')
check('R3HD_BEAM_COLOR' in header and 'strcmp(value, "restored") == 0' in header, 'exact switch value')
check('kRefusedStored' in header and 'kRefusedResult' in header and 'kRefusedSize' in header, 'hash and size gates')
check(len(re.findall(r'\{"trans_(?:ray|colonne)\.dds"', header)) == 78, "78 beam pages")
check(len(re.findall(r'\{"ago_blueripple\.dds"', header)) == 1, 'one ring page')
check('{"fix.btf", ' in header, 'ring page in the shared fix bundle')
check(not re.search(r'\{(?:\s*0x[0-9A-Fa-f]{2},){32}', header), 'no byte arrays (no title texels)')

# Patch chain: last step, between M26 and M33 so a mod wins; no earlier anchor moved.
bat = read(ROOT / 'tools/build_milestone8.bat')
check(bat.index('r3hd_button_prompts_patch.py') < bat.index('r3hd_beam_runtime_patch.py') < bat.index('cmake -S external'),
      'patch runs last, before the SDK configure')
check('call tools\\build_beam_test.bat' in bat, 'focused test in the replay')
hpf = SDK / 'src/filesystem/devices/host_path_file.cpp'
if hpf.exists() and 'r3hdbeam::' in read(hpf):
    text = read(hpf)
    i26, ib, i33 = text.index('m26tex::AfterRead('), text.index('r3hdbeam::AfterRead('), text.index('m33mods::AfterRead(')
    check(i26 < ib < i33, 'SDK: M26, beam, then M33 (mods win)')
    check(text.count('r3hdbeam::AfterRead(') == 1, 'SDK: one call')
    cp = read(SDK / 'src/graphics/d3d12/command_processor.cpp')
    check(cp.count('REXGPU_INFO("R3HD beam_color={}"') == 1, 'SDK: one mode line')
    check('REXGPU_INFO("M23 layer_coords={}", m23water::Enabled() ? "separate" : "original");\n'
          '  REXGPU_INFO("M15 draw_scale' in cp, 'SDK: M23 / M15 lines still together')
    check('REXGPU_INFO("M44 gameplay_subtitles={}", m44sub::ModeName());\n  REXGPU_INFO("M33 mods={}"' in cp,
          'SDK: M44 / M33 lines still together')
else:
    print('r3hd_beam_regression note: SDK tree not patched with the beam step; SDK text checks skipped')

if '--run' in sys.argv:
    for name in sys.argv[sys.argv.index('--run') + 1:]:
        run = ROOT / 'private/work/m6_runs' / name
        log = '\n'.join(p.read_text(encoding='utf-8', errors='replace') for p in sorted(run.glob('runtime*.log')))
        check(bool(log), name + ' log')
        modes = re.findall(r'R3HD beam_color=(\w+)', log)
        expected = 'restored' if '_on_' in name else 'original'
        check(modes == [expected], name + ' mode ' + repr(modes))
        states = re.findall(r'R3HD beam_color file=\S+ page=(\S+) state=(\w+)', log)
        served = re.findall(r'R3HD beam_color file=\S+ page=(\S+) served_bytes=32768', log)
        if expected == 'restored':
            # canister_* runs (E-447 rings) also need the fix ring page; earlier beam_* runs predate it.
            want = {'trans_ray.dds', 'trans_colonne.dds'} | ({'ago_blueripple.dds'} if name.startswith('canister_') else set())
            check(sorted(p for p, _ in states) == sorted(want) and all(s == 'restored' for _, s in states),
                  name + ' listed pages restored ' + repr(states))
            check(sorted(served) == sorted(want), name + ' listed pages fully served')
        else:
            check(not states, name + ' nothing restored')
print(f'R3HD_BEAM_REGRESSION PASS checks={checks}')
