"""Prepare an isolated HD+ out-of-range lock-on colour A/B (D-221): two copies of a registered save; never launches
gameplay.

A: HD+ with lockon_far_color=original (orange HD out-of-range indicator). B: identical options with
lockon_far_color=restored (blue). The restoration lives in rexruntime.dll, so the manifest pins both the executable and
that library; the launcher refuses a changed build.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import m12_save_entry as saves  # noqa: E402
import r3hd_settings as settings  # noqa: E402

BUILD = ROOT / 'private/work/rex/out/build/win-amd64-release'
PINNED = ('r3hd.exe', 'rexruntime.dll')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--entry', default='knaar_20_human')
    a = ap.parse_args()
    entry = saves.load_entry(a.entry)
    if not saves.stored_profile_matches(entry):
        raise SystemExit('Registered source save differs; no copies made')
    pins = {name: hashlib.sha256((BUILD / name).read_bytes()).hexdigest() for name in PINNED}
    source = ROOT / 'private/saves' / a.entry / 'profile'
    if any(p.is_symlink() or p.lstat().st_file_attributes & 0x400 for p in [source, *source.rglob('*')]):
        raise SystemExit('Redirected source refused')
    root = ROOT / 'private/work/lockon_color/acceptance' / f'{time.strftime("%Y%m%d_%H%M%S")}_{uuid.uuid4().hex[:8]}'
    root.mkdir(parents=True, exist_ok=False)
    reg = settings.load_registry()
    for mode, value in [('A', 'original'), ('B', 'restored')]:
        shutil.copytree(source, root / 'play/profiles' / mode / 'user')
        doc = settings.make_settings(reg, 'custom', 'hdplus', [f'lockon_far_color={value}'])
        (root / (mode + '.json')).write_text(json.dumps(doc, indent=2), encoding='utf-8')
        command = (f'@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File '
                   f'"{Path(__file__).with_name("visual_ab.ps1")}" -Workspace "{root}" -Mode {mode} -Manual\r\n')
        (root / (mode + '.cmd')).write_text(command, encoding='utf-8', newline='')
    (root / 'acceptance.json').write_text(json.dumps(dict(
        schema=1, entry=a.entry, source_files=entry['files'], candidate_sha256=pins,
        created=time.strftime('%Y-%m-%d %H:%M:%S'),
        checklist=['Lock on (right trigger) to an enemy, then back away until the indicator changes',
                   'Out-of-range eight-dash ring: orange in A, blue in B (compare with the PC screenshot)',
                   'Dash shape, size, brightness and pulsing otherwise unchanged',
                   'Close-range ring and direction arrows: unchanged red/orange in both A and B',
                   'Canister beam/rings, power-up swirl and other effects unchanged']), indent=2), encoding='utf-8')
    if not saves.stored_profile_matches(entry):
        raise SystemExit('Source identity changed while copying')
    print(root)


if __name__ == '__main__':
    main()
