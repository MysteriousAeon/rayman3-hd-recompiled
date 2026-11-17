#!/usr/bin/env python3
"""Offline metadata-only promotion of the authenticated Noble archive. Never compiles or publishes."""
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import tarfile
import zipfile
import zlib

import r3hd_linux_package as P

ROOT = P.ROOT
POLICY = ROOT / 'config/release/linux-1.1.0.json'
MAX_ARCHIVE = 200_000_000
MAX_EXPANDED = 500_000_000


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def strict(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            need(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    def constant(_):
        raise ValueError('invalid JSON constant')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode()


def stable(path, limit=MAX_ARCHIVE):
    path = Path(path).absolute()
    need(path.resolve() == path and not path.is_symlink(), 'linked/noncanonical input')
    before = path.stat()
    need(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'input type/size')
    with path.open('rb') as f:
        opened = f.fileno()
        import os
        a = os.fstat(opened)
        raw = f.read(limit + 1)
        b = os.fstat(opened)
    fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    need(fields(before) == fields(a) == fields(b) == fields(path.stat()) and len(raw) == before.st_size,
         'input changed while reading')
    return raw


def policy():
    return strict(stable(POLICY, 100_000))


def relative(name):
    p = PurePosixPath(name)
    need(name == p.as_posix() and not p.is_absolute() and not any(x in ('.', '..') for x in p.parts)
         and not any(c in name for c in '\\:\x00') and bool(p.parts), 'unsafe archive path')


def unpack(raw, canonical=False):
    files = {}
    total = 0
    if canonical:
        try:
            decoder = zlib.decompressobj(31)
            decoded = decoder.decompress(raw, MAX_EXPANDED + 1_000_001)
        except zlib.error as e:
            raise ValueError('invalid gzip stream/CRC') from e
        need(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
             and len(decoded) <= MAX_EXPANDED + 1_000_000, 'trailing/oversize gzip data')
    with tarfile.open(fileobj=io.BytesIO(decoded if canonical else raw), mode='r:' if canonical else 'r:gz') as archive:
        for entry in archive:
            relative(entry.name)
            need(entry.name.startswith(P.TOP + '/') and entry.isfile(), 'unexpected archive member/type')
            name = entry.name[len(P.TOP) + 1:]
            need(name not in files and len(files) < 100, 'duplicate/oversize archive inventory')
            need(entry.mode == (0o755 if name in P.EXECUTABLE else 0o644), 'unexpected archive mode')
            need(entry.uid == entry.gid == 0 and not entry.uname and not entry.gname
                 and entry.mtime == P.MTIME, 'archive owner/time metadata')
            need(not set(entry.pax_headers) - {'path'}, 'unexpected PAX metadata')
            total += entry.size
            need(0 <= entry.size <= MAX_ARCHIVE and total <= MAX_EXPANDED, 'archive expansion budget')
            data = archive.extractfile(entry).read(entry.size + 1)
            need(len(data) == entry.size, 'truncated archive member')
            files[name] = data
    if canonical:
        need(decoded == tar_bytes(files), 'noncanonical/trailing tar data')
    return files


def inventory(files):
    return {n: {'size': len(b), 'sha256': P.digest(b)} for n, b in sorted(files.items())}


def source_archive(path, lock):
    need(Path(path).name == lock['lgpl']['archive'], 'LGPL archive name')
    raw = stable(path)
    need(len(raw) == lock['lgpl']['bytes'] and P.digest(raw) == lock['lgpl']['sha256'], 'LGPL source identity')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        need(len(names) == len(set(names)) and len(names) == lock['lgpl']['files'] + 1, 'LGPL inventory')
        need(sum(i.file_size for i in z.infolist()) <= 200_000_000, 'LGPL expansion budget')
        for i in z.infolist():
            relative(i.filename)
            need(i.filename.startswith('r3hd-lgpl-source/') and not i.is_dir() and not i.flag_bits & 1
                 and not stat.S_ISLNK(i.external_attr >> 16), 'unsafe LGPL entry')
        man = strict(z.read('r3hd-lgpl-source/MANIFEST.json'))
        need(man['platform'] == 'linux-x86_64' and man['program_version'] == lock['version'], 'LGPL platform/version')
        need({k: v['commit'] for k, v in man['components'].items()} == lock['lgpl']['commits'], 'LGPL pins')
        need(set(names) == {'r3hd-lgpl-source/' + n for n in man['files']} | {'r3hd-lgpl-source/MANIFEST.json'},
             'LGPL manifest inventory')
        for n, sha in man['files'].items():
            need(P.digest(z.read('r3hd-lgpl-source/' + n)) == sha, 'LGPL file hash')
    return raw


def key_boundary(files):
    # Existing audit's key resolver; values stay in memory and are never printed or serialized.
    import m50_r01_audit as K
    keys = K.load_keys()
    need(all(k['value'] is not None for k in keys), 'key-boundary resolver unavailable')
    def occurrences(data, value):
        total, pos = 0, data.find(value)
        while pos >= 0:
            total += 1
            pos = data.find(value, pos + 1)
        return total
    return {n: hits for n in P.BINARIES
            if (hits := {k['name']: occurrences(files[n], k['value']) for k in keys
                         if len(set(k['value'])) > 1 and k['value'] in files[n]})}


def inspect_content(files):
    game = P.audit.GameHashes([P.audit.DEFAULT_MANIFEST], P.audit.DEFAULT_RELEASES)
    for n, data in files.items():
        need(P.digest(data) not in game.hashes, 'bundled original game file')
        if n in P.BINARIES:
            need(P.elf_ok(data) and not P.audit.binary_dev_paths(data), 'ELF format/private path')
        elif n.startswith('app/icons/'):
            need(data.startswith(b'\x89PNG\r\n\x1a\n'), 'icon format')
        else:
            need(b'\0' not in data, 'nontext application member')
            findings, _ = P.audit.scan_text(data.decode('utf-8'))
            need(not findings, 'text privacy/content finding in ' + n + ': ' + ','.join(findings))
    need(key_boundary(files) == P.KEY_BOUNDARY, 'established key boundary changed')


def additions(lock):
    files = {}
    for dest, source in lock['replacements'].items():
        files[dest] = stable(ROOT / source, 100_000).replace(b'\r\n', b'\n')
    for dest, row in lock['license_additions'].items():
        raw = stable(ROOT / row['source'], 100_000).replace(b'\r\n', b'\n')
        need(P.digest(raw) == row['sha256'], 'pinned license differs: ' + dest)
        files[dest] = raw
    return files


def payload_id(entries):
    return P.digest(''.join(f"{n}\t{r['size']}\t{r['sha256']}\n" for n, r in sorted(entries.items())).encode())


def original(files, lock):
    need(inventory(files) == lock['original_files'], 'canonical Noble file inventory differs')
    payload, portable = (strict(files[n]) for n in ('payload.json', 'portable.json'))
    need(payload['publishable'] is False and portable['publishable'] is False, 'original is not private Noble')
    need({n: v for n, v in inventory(files).items() if n != 'portable.json'} == portable['files'], 'original portable hashes')
    need(portable['lgpl']['corresponding_source']['sha256'] == lock['lgpl']['sha256'], 'original source pairing')
    return payload, portable


def promoted(files, lock):
    original(files, lock)
    result = dict(files)
    result.update(additions(lock))
    result.pop('payload.json')
    result.pop('portable.json')
    entries = {n: {**v, 'role': 'native' if n in P.BINARIES else 'app'}
               for n, v in inventory(result).items() if n not in ('Play.sh', 'Settings.sh')}
    payload = {**lock['original_payload_core'], 'version': lock['version'], 'publishable': True,
               'files': entries, 'payload_id': payload_id(entries),
               'note': "Linux portable distribution. Game data is prepared locally from the owner's supported copy."}
    result['payload.json'] = P.encoded(payload)
    portable = {k: v for k, v in lock['original_portable_core'].items() if k != 'development_id'}
    portable.update({'publishable': True, 'release_version': lock['version'], 'application_version': lock['version'],
                     'payload_id': payload['payload_id'], 'files': inventory(result)})
    result['portable.json'] = P.encoded(portable)
    return result


def validate_public(files, lock):
    base = lock['original_files']
    edits = additions(lock)
    need(set(files) == set(base) | set(edits), 'public inventory differs')
    for n, row in base.items():
        if n not in edits and n not in ('payload.json', 'portable.json'):
            need(len(files[n]) == row['size'] and P.digest(files[n]) == row['sha256'], 'accepted bytes changed: ' + n)
    need(all(files[n] == b for n, b in edits.items()), 'release notices/help differ')
    payload = strict(files['payload.json'])
    portable = strict(files['portable.json'])
    # Compare complete manifests, not selected fields; extra keys cannot smuggle paths or policy changes.
    entries = {n: {**v, 'role': 'native' if n in P.BINARIES else 'app'}
               for n, v in inventory(files).items() if n not in ('Play.sh', 'Settings.sh', 'payload.json', 'portable.json')}
    expected_payload = {**lock['original_payload_core'], 'version': lock['version'], 'publishable': True,
                        'files': entries, 'payload_id': payload_id(entries),
                        'note': "Linux portable distribution. Game data is prepared locally from the owner's supported copy."}
    need(payload == expected_payload and files['payload.json'] == P.encoded(expected_payload), 'public payload differs')
    expected_portable = {k: v for k, v in lock['original_portable_core'].items() if k != 'development_id'}
    expected_portable.update({'publishable': True, 'release_version': lock['version'], 'application_version': lock['version'],
                             'payload_id': payload['payload_id'],
                             'files': {n: v for n, v in inventory(files).items() if n != 'portable.json'}})
    need(portable == expected_portable and files['portable.json'] == P.encoded(expected_portable), 'public portable differs')
    inspect_content(files)


def tar_bytes(files):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w', format=tarfile.PAX_FORMAT) as archive:
        for n, raw in sorted(files.items()):
            info = tarfile.TarInfo(P.TOP + '/' + n)
            info.size, info.mtime, info.mode = len(raw), P.MTIME, 0o755 if n in P.EXECUTABLE else 0o644
            archive.addfile(info, io.BytesIO(raw))
    return output.getvalue()


def pack(files):
    output = io.BytesIO()
    with gzip.GzipFile(filename='', fileobj=output, mode='wb', mtime=0) as gz:
        gz.write(tar_bytes(files))
    return output.getvalue()


def check_public(path, lgpl_source):
    lock = policy()
    source_archive(lgpl_source, lock)
    raw = stable(path)
    need(Path(path).name == lock['archive'], 'public archive name')
    need(len(raw) >= 10 and raw[:3] == b'\x1f\x8b\x08' and raw[3] == 0 and raw[4:8] == b'\0' * 4,
         'noncanonical gzip header')
    files = unpack(raw, canonical=True)
    validate_public(files, lock)
    return {'result': 'PASS', 'publishable': True, 'bytes': len(raw), 'sha256': P.digest(raw), 'files': len(files),
            'version': lock['version'], 'binaries': {n: P.digest(files[n]) for n in P.BINARIES},
            'lgpl_source_sha256': lock['lgpl']['sha256'], 'publication_authorized': False}


def buildinfo(raw, lock):
    return {'schema': 1, 'product': P.engine.PRODUCT, 'version': lock['version'], 'platform': lock['platform'],
            'build': lock['build'], 'canonical_binary_archive_sha256': lock['input_archive']['sha256'],
            'binaries': {n: lock['original_files'][n]['sha256'] for n in P.BINARIES},
            'portable_archive_sha256': P.digest(raw), 'lgpl_source': lock['lgpl'],
            'packaging_only': True, 'native_binaries_modified': False,
            'packaging_recipe_sha256': P.digest(stable(Path(__file__)).replace(b'\r\n', b'\n')),
            'packaging_policy_sha256': P.digest(stable(POLICY).replace(b'\r\n', b'\n'))}


def release_files(raw, source, lock):
    files = {lock['archive']: raw, lock['lgpl']['archive']: source, 'BUILDINFO.json': encoded(buildinfo(raw, lock))}
    manifest = {'schema': 1, 'version': lock['version'], 'platform': lock['platform'],
                'github_proposal': {k: lock['github'][k] for k in ('repository', 'tag', 'title', 'prerelease', 'make_latest')},
                'assets': inventory(files)}
    files['release-manifest.json'] = encoded(manifest)
    files['SHA256SUMS.txt'] = ''.join(f'{P.digest(b)}  {n}\n' for n, b in sorted(files.items())).encode()
    return files


def audit_directory(out):
    out = Path(out).absolute()
    lock = policy()
    names = {lock['archive'], lock['lgpl']['archive'], 'BUILDINFO.json', 'release-manifest.json', 'SHA256SUMS.txt'}
    need(out.resolve() == out and {p.name for p in out.iterdir()} == names, 'release directory inventory/path')
    report = check_public(out / lock['archive'], out / lock['lgpl']['archive'])
    actual = {n: stable(out / n) for n in names}
    expected = release_files(actual[lock['archive']], actual[lock['lgpl']['archive']], lock)
    need(actual == expected, 'release metadata/checksums differ')
    for name in ('BUILDINFO.json', 'release-manifest.json', 'SHA256SUMS.txt'):
        need(not P.audit.scan_text(actual[name].decode('utf-8'))[0], 'release metadata privacy finding')
    return {**report, 'assets': inventory(actual), 'audit': 'COMPLETE_OFFLINE_RELEASE_AUDIT', 'notes_finalized': False}


def promote(source, lgpl_source, out):
    out = Path(out).absolute()
    need(not out.exists() and not out.is_symlink() and out.parent.resolve() == out.parent, 'output exists/linked parent')
    lock = policy()
    raw = stable(source)
    need(len(raw) == lock['input_archive']['bytes'] and P.digest(raw) == lock['input_archive']['sha256'],
         'original Noble archive unavailable or wrong identity')
    source_raw = source_archive(lgpl_source, lock)
    original_files = unpack(raw)
    original(original_files, lock)
    inspect_content(original_files)
    result = promoted(original_files, lock)
    validate_public(result, lock)
    packed = pack(result)
    need(unpack(packed) == result, 'archive round-trip differs')
    # All validation precedes mutation. Exclusive fresh output; a failed write is preserved, never retried/overwritten.
    out.mkdir(mode=0o700)
    for n, b in release_files(packed, source_raw, lock).items():
        with (out / n).open('xb') as f:
            f.write(b)
    return audit_directory(out)
