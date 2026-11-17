"""Build one metadata-only kit; reads pinned project source, never SDK/game inputs."""
import argparse
from pathlib import Path
import subprocess
import zipfile
import collect as C

ROOT = Path(__file__).resolve().parents[3]
REF = '0414e72ed512cd3057eea63d7b06f7d4ad3c4734'


def source(n):
    return subprocess.check_output(['git', '-C', str(ROOT), 'show', REF + ':' + n])


def make_lock():
    definition = C.parse(source('config/release/payload.json'))
    project = {n: p for n, p in definition['app_files'].items() if n not in
               {'app/tools/play.ps1', 'app/tools/play_savekeeper.ps1', 'app/play.cmd', 'app/settings.cmd'}}
    project.update({'app/tools/r3hd_portable.py': 'tools/r3hd_portable.py',
                    'app/tools/linux/r3hd_play.py': 'tools/linux/r3hd_play.py',
                    'app/tools/linux/r3hd_settings_gui.py': 'tools/linux/r3hd_settings_gui.py',
                    'app/README-LINUX.txt': 'tools/linux/README-LINUX.txt',
                    'app/licenses/LGPL-SOURCE.txt': 'tools/linux/LGPL-SOURCE-LINUX.txt'})
    hashes = {n: C.digest(source(p).replace(b'\r\n', b'\n')) for n, p in project.items()}
    for action, n in [('play', 'Play.sh'), ('settings', 'Settings.sh')]:
        text = ('#!/bin/sh\n# Rayman 3 HD Recompiled (Linux Experimental): ' + action + '. Needs python3 (3.10+).\n'
                'HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\nexport PYTHONDONTWRITEBYTECODE=1\n'
                'exec python3 -B "$HERE/app/tools/r3hd_portable.py" ' + action + ' "$@"\n')
        hashes[n] = C.digest(text.encode())
    allowed = set(project) | set(definition['licenses']['files']) | {'Play.sh', 'Settings.sh', 'payload.json', 'portable.json',
               'app/icons/rayman3hd-recompiled.png', 'app/icons/rayman3hd-recompiled-settings.png'} | {'bin/' + n for n in C.COMPONENTS}
    reg = C.parse(source('config/settings/registry.json'))
    enums = {k: s.get('values', [str(v) for v in range(s.get('range', {}).get('min', 0), s.get('range', {}).get('max', -1) + 1)]) for k, s in reg['settings'].items()}
    package_dir = 'Projects/RaymanLM1/private/work/linux_build/native_lma/'
    noble_dir = 'Projects/R3HD-baseline-noble-2b-egl-01/work/private/work/linux_build/noble_2b01/'
    return {'schema': 1, 'source_commit': REF, 'allowed': sorted(allowed), 'source_files': hashes,
            'settings_values': enums,
            'contract_files': ['Play.sh', 'Settings.sh', 'app/tools/r3hd_portable.py', 'app/tools/linux/r3hd_play.py',
                               'app/tools/r3hd_installer.py', 'app/tools/r3hd_settings.py', 'app/tools/r3hd_mods.py',
                               'app/tools/linux/r3hd_settings_gui.py', 'app/config/settings/registry.json'],
            'packages': {'r3hd-linux-noble-2b01.tar.gz': '54d17f45b8bca9431fe98af48a37f93a6500282932c5543b765fa101d1fda15f',
                         'r3hd-linux-lx2d.tar.gz': 'd8371b5a4e6421ed7c31075a6a5b10e31a18f1f781e4d8c0826c76333dcf50a7'},
            'archive_paths': {'noble': noble_dir + 'r3hd-linux-noble-2b01.tar.gz',
                              **{k: package_dir + 'r3hd-linux-' + k + '.tar.gz' for k in ('lx2f', 'lx2red', 'lx2d')}},
            'installation_paths': {'lx2f': ['Games/R3HD-LX2F/Rayman3HDRecompiled-Linux', 'Games/R3HD-LX2F'],
                                   'lx2red': ['Games/R3HD-LX2RED/Rayman3HDRecompiled-Linux', 'Games/R3HD-LX2RED'],
                                   'noble_stage2d': ['Projects/R3HD-baseline-noble-2d-01/installation']}}


def build(out):
    C.need(not out.exists() and not out.is_symlink(), 'output exists; preserve it')
    files = {n: (C.HERE / n).read_bytes().replace(b'\r\n', b'\n') for n in ('collect.py', 'HANDOFF.md')}
    files['LOCK.json'] = C.encode(make_lock())
    files['SHA256SUMS'] = ''.join(C.digest(b) + '  ' + n + '\n' for n, b in sorted(files.items())).encode()
    out.mkdir()
    dest = out / 'r3hd-linux-provenance.zip'
    with zipfile.ZipFile(dest, 'x', zipfile.ZIP_DEFLATED) as z:
        for n, b in sorted(files.items()):
            i = zipfile.ZipInfo(n, (1980, 1, 1, 0, 0, 0))
            i.create_system = 3
            i.compress_type = zipfile.ZIP_DEFLATED
            i.external_attr = 0o100644 << 16
            z.writestr(i, b, compresslevel=9)
    Path(str(dest) + '.sha256').write_text(C.digest(dest.read_bytes()) + '  ' + dest.name + '\n', encoding='ascii')
    (out / 'HANDOFF.md').write_bytes(files['HANDOFF.md'])
    print(dest, dest.stat().st_size, C.digest(dest.read_bytes()))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    build(p.parse_args().out)
