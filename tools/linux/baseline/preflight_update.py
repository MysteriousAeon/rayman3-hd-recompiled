#!/usr/bin/env python3
"""Small private external-preflight update. Never edits/reseals the frozen source archive.

build: Windows preparation; apply --transfer PATH: verify original kit, back up three
small files, replace preflight/HANDOFF/checksums only. No host checks or container calls.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORIGINAL_SUMS = '33dea3b0521c793d0a497befb6ccd6c478382c8dc6f6fd5c04f9e11277fb6264'
NAMES = ('r3hd-baseline-2a.tar.gz', 'prepare.py', 'preflight.py', 'KIT_MANIFEST.json', 'HANDOFF.md')
BACKUP = 'baseline-arch-dropin-backup'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sums_map(data):
    rows = [line.split('  ') for line in data.decode('ascii').splitlines()]
    need(all(len(r) == 2 for r in rows), 'invalid checksums')
    values = {n: h for h, n in rows}
    need(len(rows) == len(values) and set(values) == set(NAMES), 'unexpected checksum inventory')
    return values


def apply(transfer, package=HERE):
    need(transfer.is_dir() and transfer.resolve() == transfer.absolute(), 'transfer must be a real directory, no symlink ancestors')
    manifest_path = package/'UPDATE.json'
    need(not manifest_path.is_symlink(), 'symlink update manifest')
    manifest = json.loads(manifest_path.read_text())
    need(manifest['format'] == 'R3HD_PREFLIGHT_ARCH_UPDATE_V1', 'unknown update format')
    need(manifest['original_checksums_sha256'] == ORIGINAL_SUMS, 'unexpected original checksum identity')
    need(set(manifest['replacement']) == {'preflight.py', 'HANDOFF.md'}, 'unexpected update files')
    for n, expected in manifest['replacement'].items():
        need((package/n).is_file() and not (package/n).is_symlink() and digest(package/n) == expected,
             'update payload hash mismatch: '+n)
    checksum = transfer/'SHA256SUMS'
    need(checksum.is_file() and not checksum.is_symlink() and digest(checksum) == ORIGINAL_SUMS,
         'not the original Stage 2A checksum file; no overwrite/reapply')
    original = sums_map(checksum.read_bytes())
    for n, expected in original.items():
        p = transfer/n
        need(p.is_file() and not p.is_symlink() and digest(p) == expected, 'original transfer hash mismatch: '+n)
    backup = transfer/BACKUP
    need(not backup.exists() and not backup.is_symlink(), 'backup already exists; preserve and diagnose')
    # Validate all content/destinations before writing. Existing diagnostics/unknown files are untouched.
    replacements = {n: (package/n).read_bytes() for n in manifest['replacement']}
    final_sums = dict(original, **manifest['replacement'])
    replacements['SHA256SUMS'] = ''.join(final_sums[n]+'  '+n+'\n' for n in NAMES).encode('ascii')
    for n in replacements:
        need(not (transfer/(n+'.arch-update.tmp')).exists()
             and not (transfer/(n+'.arch-update.tmp')).is_symlink(), 'update temporary path exists')
    backup.mkdir()
    for n in replacements:
        with (backup/n).open('xb') as f:
            f.write((transfer/n).read_bytes())
    # Individual atomic replacements; an interruption stops further use and leaves complete originals.
    for n, data in replacements.items():
        temp = transfer/(n+'.arch-update.tmp')
        with temp.open('xb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, transfer/n)
    for n, expected in final_sums.items():
        need(digest(transfer/n) == expected, 'post-update hash mismatch: '+n)
    print('R3HD_PREFLIGHT_ARCH_UPDATE PASS; source archive unchanged; native preflight NOT run')


def build():
    original = ROOT/'private/work/linux_build/baseline_2a_final'
    need(digest(original/'SHA256SUMS') == ORIGINAL_SUMS, 'original private kit changed')
    for n, expected in sums_map((original/'SHA256SUMS').read_bytes()).items():
        need(digest(original/n) == expected, 'original kit hash mismatch: '+n)
    new_preflight = (HERE/'preflight.py').read_bytes().replace(b'\r\n', b'\n')
    old_hash = digest(original/'preflight.py')
    new_hash = hashlib.sha256(new_preflight).hexdigest()
    handoff = (original/'HANDOFF.md').read_text(encoding='utf-8')
    handoff = handoff.replace(old_hash, new_hash).replace('| 9269 |', '| '+str(len(new_preflight))+' |')
    handoff = handoff.replace('paths. Unsupported/split/transient storage, drop-ins or environment overrides stop rather',
        'paths. Only the exact reviewed Arch vendor drop-in (journald/nftables) is accepted;\n'
        'unexpected files/settings, duplicate/conflicting assignments, unsupported/split/transient\n'
        'storage or environment overrides stop rather')
    handoff += ('\n## Arch preflight correction (E-386)\n\n'
                'External preflight.py is updated; the 231,630,973-byte source archive and its internal\n'
                'manifests remain frozen. Later Gates B–D call $TRANSFER/preflight.py, not the old copy\n'
                'inside the extracted work tree. Original preflight/HANDOFF/SHA256SUMS are preserved\n'
                'in baseline-arch-dropin-backup. Native preflight rerun remains pending.\n')
    entries = {'preflight.py': new_preflight, 'HANDOFF.md': handoff.encode(),
               'apply_update.py': Path(__file__).read_bytes().replace(b'\r\n', b'\n')}
    manifest = {'format': 'R3HD_PREFLIGHT_ARCH_UPDATE_V1', 'original_checksums_sha256': ORIGINAL_SUMS,
                'replacement': {n: hashlib.sha256(entries[n]).hexdigest() for n in ('preflight.py','HANDOFF.md')}}
    entries['UPDATE.json'] = (json.dumps(manifest, indent=2)+'\n').encode()
    out = ROOT/'private/work/linux_build/baseline_arch_update'
    need(not out.exists(), 'update output exists; preserve it')
    out.mkdir()
    archive = out/'r3hd-stage2a-arch-update.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for n, data in sorted(entries.items()):
            info = zipfile.ZipInfo(n, date_time=(2026,11,8,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    (out/(archive.name+'.sha256')).write_text(digest(archive)+'  '+archive.name+'\n', encoding='ascii')
    print(archive, archive.stat().st_size, digest(archive))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build','apply'))
    parser.add_argument('--transfer', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'build':
            build()
        else:
            need(args.transfer is not None, '--transfer required')
            apply(args.transfer)
    except (ValueError, OSError, KeyError) as e:
        print('R3HD_PREFLIGHT_ARCH_UPDATE STOP:', e, file=sys.stderr)
        sys.exit(2)
