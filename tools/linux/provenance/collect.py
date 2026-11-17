"""Bounded metadata only. Never imports installed code, spawns a process or reads game/save assets."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import tarfile
import time
import zipfile

HERE = Path(__file__).resolve().parent
COMPONENTS = ('r3hd', 'librexruntime.so', 'librexgpu-xenos.so', 'libffmpeg.so', 'libmspack.so')
TOP = 'Rayman3HDRecompiled-Linux/'
META = 2_000_000
MAX_FILE = 200_000_000


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(b):
    return hashlib.sha256(b).hexdigest()


def encode(o):
    return (json.dumps(o, indent=2, sort_keys=True) + '\n').encode()


def parse(b):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            need(k not in out, 'duplicate JSON key')
            out[k] = v
        return out
    def invalid(_):
        raise ValueError('non-JSON constant')
    return json.loads(b, object_pairs_hook=unique, parse_constant=invalid)


def relative(n):
    need(isinstance(n, str) and len(n) < 240 and re.fullmatch(r'[A-Za-z0-9_.\-/]+', n), 'unsafe relative path')
    p = PurePosixPath(n)
    need(not p.is_absolute() and n == '/'.join(p.parts) and all(x not in ('.', '..') for x in p.parts), 'unsafe path segments')
    return p.parts


def stamp(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode)


class Reader:
    """Read-only descriptors; Linux path traversal uses O_NOFOLLOW at every component."""
    def __init__(self, root, seconds=180):
        self.root = Path(root).absolute()
        need(self.root.resolve() == self.root and self.root.is_dir(), 'noncanonical input root')
        self.end = time.monotonic() + seconds
        self.seen = {}

    def clock(self):
        need(time.monotonic() < self.end, 'collection time budget reached')

    def open(self, rel):
        parts = relative(rel)
        self.clock()
        p = self.root.joinpath(*parts)
        need(p.resolve() == p, 'linked input path')
        if os.name == 'posix':
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                for part in parts[:-1]:
                    nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(fd)
                    fd = nxt
                leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            finally:
                os.close(fd)
            f = os.fdopen(leaf, 'rb')
        else:  # fixture verification only; collect itself refuses Windows/WSL.
            f = p.open('rb')
        try:
            s = os.fstat(f.fileno())
            need(stat.S_ISREG(s.st_mode) and s.st_size <= MAX_FILE, 'unsupported input file/size')
            need(stamp(s) == stamp(p.stat(follow_symlinks=False)), 'input replaced while opening')
            need(rel not in self.seen or self.seen[rel] == stamp(s), 'input changed between reads')
            self.seen[rel] = stamp(s)
            return f
        except BaseException:
            f.close()
            raise

    def finish(self, rel, f):
        need(stamp(os.fstat(f.fileno())) == self.seen[rel], 'input changed while reading')
        p = self.root / rel
        need(p.resolve() == p and stamp(p.stat(follow_symlinks=False)) == self.seen[rel], 'input path changed')

    def read(self, rel, capture=False, limit=MAX_FILE):
        with self.open(rel) as f:
            need(os.fstat(f.fileno()).st_size <= limit, 'metadata size budget')
            h, blocks, size = hashlib.sha256(), [], 0
            while True:
                self.clock()
                b = f.read(1024 * 1024)
                if not b:
                    break
                size += len(b)
                need(size <= limit, 'read size budget')
                h.update(b)
                if capture:
                    blocks.append(b)
            self.finish(rel, f)
        return {'sha256': h.hexdigest(), 'size': size}, b''.join(blocks)

    def optional(self, rel, capture=False):
        try:
            return self.read(rel, capture, META)
        except FileNotFoundError:
            # Distinguish absent leaf/parent from a dangling link, not a permission exemption.
            p = self.root / rel
            need(p.resolve() == p and not p.is_symlink(), 'dangling linked input')
            self.seen[rel] = None
            return None, b''

    def unchanged(self):
        for rel, old in self.seen.items():
            self.clock()
            p = self.root / rel
            need(p.resolve() == p and not p.is_symlink(), 'input link changed')
            try:
                now = stamp(p.stat(follow_symlinks=False))
            except FileNotFoundError:
                now = None
            need(old == now, 'input changed during collection')


def manifest(b, allowed):
    j = parse(b)
    need(isinstance(j, dict) and isinstance(j.get('files'), dict) and len(j['files']) <= 100, 'manifest shape')
    for n, row in j['files'].items():
        relative(n)
        need(n in allowed and isinstance(row, dict), 'unexpected program manifest entry')
        need(type(row.get('size')) is int and 0 <= row['size'] <= MAX_FILE, 'manifest file size')
        need(isinstance(row.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'manifest hash')
    return j


def summary(portable, payload):
    out = {}
    for k in ('development_id', 'application_version', 'payload_id'):
        v = portable.get(k)
        need(isinstance(v, str) and re.fullmatch('[A-Za-z0-9._-]{1,100}', v), 'manifest identity field')
        out[k] = v
    out['requires'] = {}
    for k in ('glibc', 'glibcxx'):
        v = payload.get('requires', {}).get(k)
        need(v is None or isinstance(v, str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}', v), 'ABI metadata field')
        out['requires'][k] = v
    source = portable.get('lgpl', {}).get('corresponding_source')
    need(isinstance(source, dict), 'missing corresponding-source identity')
    need(isinstance(source.get('archive'), str) and re.fullmatch(r'r3hd-lgpl-source-[0-9.]+-linux-x86_64\.zip', source['archive']), 'corresponding-source filename')
    need(isinstance(source.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', source['sha256']), 'corresponding-source hash')
    out['corresponding_source'] = {k: source[k] for k in ('archive', 'sha256')}
    return out


class ArchiveBudget:
    def __init__(self, stream, reader):
        self.stream, self.reader, self.total = stream, reader, 0

    def read(self, size):
        self.reader.clock()
        b = self.stream.read(min(size, 1024 * 1024))
        self.total += len(b)
        need(self.total <= 500_000_000, 'archive decompression budget')
        return b


def package(reader, rel, lock):
    identity, _ = reader.read(rel)
    expected = lock['packages'].get(Path(rel).name)
    if expected:
        need(identity['sha256'] == expected, 'pinned archive hash mismatch')
    files, blobs, total = {}, {}, 0
    with reader.open(rel) as f:
        with gzip.GzipFile(fileobj=f, mode='rb') as decoded, tarfile.open(fileobj=ArchiveBudget(decoded, reader), mode='r|') as t:
            for m in t:
                reader.clock()
                need(m.isfile() and m.name.startswith(TOP), 'unsupported archive member')
                n = m.name[len(TOP):]
                relative(n)
                need(n in lock['allowed'] and n not in files, 'archive inventory')
                need(0 <= m.size <= MAX_FILE and m.mode in (0o644, 0o755), 'archive size/mode')
                need((m.mode == 0o755) == (n in ('Play.sh', 'Settings.sh', 'bin/r3hd')), 'archive executable mode')
                total += m.size
                need(total <= 500_000_000, 'archive expansion budget')
                h, size = hashlib.sha256(), 0
                with t.extractfile(m) as member:
                    chunks = []
                    for b in iter(lambda: member.read(1024 * 1024), b''):
                        reader.clock()
                        h.update(b)
                        size += len(b)
                        if n in ('portable.json', 'payload.json'):
                            need(size <= META, 'archive metadata budget')
                            chunks.append(b)
                need(size == m.size, 'archive truncated')
                files[n] = {'sha256': h.hexdigest(), 'size': size}
                if chunks:
                    blobs[n] = b''.join(chunks)
        reader.finish(rel, f)
    portable = manifest(blobs['portable.json'], lock['allowed'])
    payload = manifest(blobs['payload.json'], lock['allowed'])
    need(set(files) == set(portable['files']) | {'portable.json'}, 'archive portable inventory')
    need(all(files[n] == v for n, v in portable['files'].items()), 'archive checksum mismatch')
    need(set(portable['files']) == set(payload['files']) | {'payload.json', 'Play.sh', 'Settings.sh'}, 'archive payload inventory')
    need(all(files[n] == {k: v[k] for k in ('size', 'sha256')} for n, v in payload['files'].items()), 'archive payload hashes')
    need({n[4:] for n in files if n.startswith('bin/')} == set(COMPONENTS), 'archive components')
    need(portable.get('publishable') is False and payload.get('publishable') is False, 'unexpected publication policy')
    return {'identity': identity, 'authentication': 'PINNED_SHA256' if expected else 'SELF_CONSISTENT_NOT_EXTERNALLY_PINNED',
            'files': files, 'metadata': summary(portable, payload)}


def settings(reader, lock):
    row, b = reader.optional('settings.json', True)
    if row is None:
        return {'status': 'ABSENT; portable setup/default choice not established'}
    j = parse(b)
    need(isinstance(j, dict) and type(j.get('schema')) is int and j['schema'] in (1, 2, 3, 4), 'settings schema')
    need(j.get('preset') in ('vanilla', 'hdplus', 'custom') and j.get('base') in (None, 'vanilla', 'hdplus'), 'settings preset')
    out = {'identity': row, 'schema': j['schema'], 'preset': j['preset'], 'base': j.get('base'),
           'allow_experimental': j.get('allow_experimental') is True, 'keyboard_section_present': 'keyboard' in j,
           'controller_section_present': 'controller' in j, 'effective_launch_values': 'NOT EXECUTED/RESOLVED; review trusted resolver offline'}
    for key in ('preferences', 'overrides'):
        values = j.get(key) or {}
        need(isinstance(values, dict) and len(values) <= len(lock['settings_values']), 'settings selections')
        for k, v in values.items():
            need(k in lock['settings_values'] and type(v) is str and v in lock['settings_values'][k], 'unsupported settings selection')
        out[key] = values
    # No comments, arbitrary fields, keyboard mappings or controller mappings are exported.
    out['unrecognized_field_count'] = len(set(j) - {'schema', 'preset', 'base', 'allow_experimental', 'preferences', 'overrides', 'keyboard', 'controller', 'comment'})
    return out


def mods(reader):
    row, b = reader.optional('mods/state.json', True)
    if row is None:
        return {'status': 'ABSENT; no mod selection recorded'}
    j = parse(b)
    need(isinstance(j, dict) and j.get('schema') == 1 and isinstance(j.get('mods'), list) and len(j['mods']) <= 1000, 'mod-state shape')
    ids = set()
    for e in j['mods']:
        need(isinstance(e, dict) and isinstance(e.get('id'), str) and re.fullmatch('[a-z0-9][a-z0-9._-]{1,63}', e['id']), 'mod-state identifier')
        need(e['id'] not in ids and type(e.get('enabled')) is bool, 'mod-state duplicate/enable flag')
        ids.add(e['id'])
    return {'identity': row, 'installed_entries': len(ids), 'enabled_entries': sum(e['enabled'] for e in j['mods']),
            'application': 'NOT CHECKED; no assets/plans read and no mod engine executed'}


def installation(reader, rel, lock, archives):
    base = rel + '/'
    row, b = reader.read(base + 'portable.json', True, META)
    portable = manifest(b, lock['allowed'])
    prows, pb = reader.read(base + 'payload.json', True, META)
    payload = manifest(pb, lock['allowed'])
    need(set(portable['files']) == set(payload['files']) | {'payload.json', 'Play.sh', 'Settings.sh'}, 'installed manifest inventories disagree')
    files, differences = {}, []
    for n, expected in portable['files'].items():
        observed, _ = reader.read(base + n, limit=MAX_FILE if n.startswith('bin/') else META)
        files[n] = observed
        if observed != {k: expected[k] for k in ('size', 'sha256')}:
            differences.append(n)
        if n in payload['files']:
            need({k: payload['files'][n][k] for k in ('size', 'sha256')} == {k: expected[k] for k in ('size', 'sha256')}, 'payload/portable hashes disagree')
    files['portable.json'] = row
    need(files['payload.json'] == prows, 'payload changed between reads')
    need({n[4:] for n in files if n.startswith('bin/')} == set(COMPONENTS), 'installed component inventory')
    # Fixed configuration files only, through the same guarded reader; no directory traversal into user data.
    local = ReaderView(reader, base)
    configs = {'settings': settings(local, lock), 'mods': mods(local)}
    for n in ('installer.json', 'bin/r3hd.toml'):
        configs[n] = local.optional(n)[0]
    matches = [k for k, a in archives.items() if a.get('files') == files]
    source_matches = {n: files[n]['sha256'] == h for n, h in lock['source_files'].items() if n in files}
    pinned = [k for k in matches if archives[k]['authentication'] == 'PINNED_SHA256']
    return {'files': files, 'manifest_mismatches': differences, 'configuration': configs,
            'metadata': summary(portable, payload),
            'matching_archives': matches, 'pinned_matching_archives': pinned,
            'authentication': 'PINNED_ARCHIVE_MATCH' if pinned else 'LOCAL_MANIFEST_ONLY' if not differences else 'MANIFEST_MISMATCH',
            'source_0414e72_matches': source_matches,
            'normal_play_contract': 'KNOWN_STATIC_SOURCE' if all(source_matches.get(n) for n in lock['contract_files']) else 'UNKNOWN_SOURCE_VARIANT',
            'runtime_or_mod_feature_acceptance': 'NOT TESTED'}


class ReaderView:
    def __init__(self, reader, prefix):
        self.reader, self.prefix = reader, prefix

    def optional(self, rel, capture=False):
        return self.reader.optional(self.prefix + rel, capture)


def compare(installs):
    pairs = {}
    labels = list(installs)
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            x, y = installs[a], installs[b]
            if 'files' not in x or 'files' not in y:
                continue
            binary = [n for n in ('bin/' + c for c in COMPONENTS) if x['files'].get(n) != y['files'].get(n)]
            program = [n for n in sorted(set(x['files']) | set(y['files'])) if not n.startswith('bin/') and x['files'].get(n) != y['files'].get(n)]
            pairs[a + '__' + b] = {'different_binaries': binary, 'different_program_or_manifest_files': program,
                                  'same_configuration_metadata': x['configuration'] == y['configuration'],
                                  'same_filtered_settings_selections':
                                      {k: v for k, v in x['configuration']['settings'].items() if k != 'identity'} ==
                                      {k: v for k, v in y['configuration']['settings'].items() if k != 'identity'},
                                  'interpretation': 'BINARY_DIFFERENCES' if binary else 'SAME_BINARIES; program/configuration differences separate'}
    return pairs


def seal():
    sums = (HERE / 'SHA256SUMS').read_text(encoding='ascii').splitlines()
    need(len(sums) == 3, 'toolkit inventory')
    names = set()
    for line in sums:
        h, n = line.split('  ')
        need(n in ('collect.py', 'LOCK.json', 'HANDOFF.md') and n not in names, 'toolkit name')
        need((HERE / n).is_file() and not (HERE / n).is_symlink() and digest((HERE / n).read_bytes()) == h, 'toolkit hash')
        names.add(n)


def collect():
    seal()
    need(platform.system() == 'Linux' and platform.machine() == 'x86_64' and os.getuid() != 0, 'native unprivileged Linux x86-64 required')
    need('microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower(), 'WSL is fixture-only, not native collection')
    lock = parse((HERE / 'LOCK.json').read_bytes())
    home = Path.home().absolute()
    out = home / 'Projects/R3HD-linux-provenance-01'
    need(out.parent.resolve() == out.parent and out.parent.is_dir() and not out.exists() and not out.is_symlink(), 'fresh output directory required; preserve any earlier attempt')
    need(shutil.disk_usage(out.parent).free >= 16_000_000, 'need 16,000,000 free bytes for metadata evidence')
    reader = Reader(home)
    result = {'schema': 1, 'scope': 'READ_ONLY_METADATA_NO_TARGET_EXECUTION', 'toolkit_sha256': digest((HERE / 'SHA256SUMS').read_bytes()),
              'archives': {}, 'installations': {}, 'input_stability': 'PENDING', 'privacy': 'no game/data/save/asset/log contents or arbitrary config text'}
    # No modifications of inputs, caches or old receipts. Only this new output is written.
    out.mkdir(mode=0o700)
    for label, rel in lock['archive_paths'].items():
        try:
            result['archives'][label] = package(reader, rel, lock)
        except FileNotFoundError:
            reader.seen.setdefault(rel, None)
            result['archives'][label] = {'status': 'ABSENT'}
        except (OSError, ValueError, KeyError, TypeError, tarfile.TarError) as e:
            result['archives'][label] = {'status': 'STOP_UNVERIFIED_ARCHIVE', 'check': str(e) if type(e) is ValueError else type(e).__name__}
            try:
                result['archives'][label]['unverified_observed_identity'] = reader.read(rel)[0]
            except (OSError, ValueError):
                pass  # Explicit STOP remains; never convert read errors to an authenticated/absent archive.
    for label, candidates in lock['installation_paths'].items():
        try:
            found = []
            for rel in candidates:
                row, _ = reader.optional(rel + '/portable.json')
                if row is not None:
                    found.append(rel)
            need(len(found) == 1, 'missing or ambiguous installation location')
            result['installations'][label] = installation(reader, found[0], lock, result['archives'])
            result['installations'][label]['location_key'] = candidates.index(found[0])
        except (OSError, ValueError, KeyError, TypeError) as e:
            partial = {}
            if len(found) == 1:
                for n in ('portable.json', 'payload.json', 'Play.sh', 'Settings.sh') + tuple('bin/' + c for c in COMPONENTS):
                    try:
                        partial[n] = reader.read(found[0] + '/' + n)[0]
                    except (OSError, ValueError):
                        partial[n] = {'status': 'UNAVAILABLE_OR_CHANGED'}
            result['installations'][label] = {'status': 'STOP_UNVERIFIED_INSTALLATION', 'check': str(e) if type(e) is ValueError else type(e).__name__,
                                               'partial_identities_not_authenticated': partial}
    try:
        reader.unchanged()
        result['input_stability'] = 'PASS_OBSERVED_METADATA_UNCHANGED'
    except (OSError, ValueError):
        result['input_stability'] = 'STOP_INPUT_CHANGED_OR_UNREADABLE'
    result['comparisons'] = compare(result['installations'])
    noble = result['installations'].get('noble_stage2d', {})
    result['canonical_candidate'] = ('EXISTING_NOBLE_PROGRAM_HOME; setup/normal launcher execution NOT VERIFIED'
                                     if noble.get('pinned_matching_archives') and noble.get('normal_play_contract') == 'KNOWN_STATIC_SOURCE'
                                     else 'NOT ESTABLISHED')
    okay = (result['input_stability'].startswith('PASS') and all('files' in x and not x['manifest_mismatches'] for x in result['installations'].values())
            and not any(x.get('status', '').startswith('STOP') for x in result['archives'].values())
            and result['archives'].get('noble', {}).get('authentication') == 'PINNED_SHA256'
            and result['canonical_candidate'] != 'NOT ESTABLISHED')
    result['collection'] = 'COMPLETE_METADATA_ONLY' if okay else 'STOP_WITH_GAPS; return evidence, do not retry or repair'
    payloads = {'metadata.json': encode(result)}
    payloads['SHA256SUMS'] = ''.join(digest(b) + '  ' + n + '\n' for n, b in payloads.items()).encode()
    dest = out / 'provenance-private-evidence.zip'
    with zipfile.ZipFile(dest, 'x', zipfile.ZIP_DEFLATED) as z:
        for n, b in payloads.items():
            z.writestr(n, b)
    with Path(str(dest) + '.sha256').open('x', encoding='ascii', newline='\n') as f:
        f.write(digest(dest.read_bytes()) + '  ' + dest.name + '\n')
    print('R3HD_PROVENANCE ' + result['collection'])
    print('Evidence: ~/Projects/R3HD-linux-provenance-01/provenance-private-evidence.zip (+ .sha256)')
    return 0 if okay else 2


def review(path):
    """Windows/WSL-safe transport verification; never performs native collection."""
    seal()
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 1_000_000, 'evidence size/type')
    h = digest(path.read_bytes())
    need(Path(str(path) + '.sha256').read_text(encoding='ascii').strip() == h + '  ' + path.name, 'evidence sidecar')
    with zipfile.ZipFile(path) as z:
        need(len(z.namelist()) == 2 and set(z.namelist()) == {'metadata.json', 'SHA256SUMS'}, 'evidence inventory')
        need(all(i.file_size <= 1_000_000 for i in z.infolist()), 'evidence expansion budget')
        raw = z.read('metadata.json')
        need(z.read('SHA256SUMS') == (digest(raw) + '  metadata.json\n').encode(), 'internal evidence ledger')
    j = parse(raw)
    need(j['schema'] == 1 and j['scope'] == 'READ_ONLY_METADATA_NO_TARGET_EXECUTION', 'evidence kind')
    need(j['toolkit_sha256'] == digest((HERE / 'SHA256SUMS').read_bytes()), 'evidence toolkit binding')
    need(j['comparisons'] == compare(j['installations']), 'derived comparisons inconsistent')
    return j


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('check', 'collect', 'review'))
    p.add_argument('--evidence', type=Path)
    try:
        a = p.parse_args()
        if a.action == 'check':
            seal()
            print('R3HD_PROVENANCE_TOOLKIT PASS; NO NATIVE CHECKS OR GAME EXECUTION')
        elif a.action == 'collect':
            raise SystemExit(collect())
        else:
            need(a.evidence is not None, 'evidence path required')
            j = review(a.evidence)
            print('R3HD_PROVENANCE_EVIDENCE HASHES PASS; ' + j['collection'])
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as e:
        raise SystemExit('R3HD_PROVENANCE STOP; preserve attempt, no repair/retry (' + type(e).__name__ + ')')
