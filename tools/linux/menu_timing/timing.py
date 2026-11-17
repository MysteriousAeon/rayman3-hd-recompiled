"""Read-only retained-log collection. No launch, process control or installed-code imports."""
import collections
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import zipfile

PORTABLE = 'b334b012bba15e31fa006abdc72b5f925b23bd8e414ed31e7bda11c70b1045e6'
ACCEPTED = 'f4f1192c57dc4133228ab7e514f81ee97070a6a924731209b0ae9c78df24f551'
SETTINGS = 'c722f072cfd91e06fe1fd4387bd5061fb92f472bbd55ebf556b40d22119c7ee8'
REQUIRED = ('Play.sh', 'Settings.sh', 'bin/r3hd', 'bin/librexruntime.so',
            'bin/librexgpu-xenos.so', 'bin/libffmpeg.so', 'bin/libmspack.so')
STAMP = re.compile(r'^\[([0-9-]+ [0-9:.]+)\]')
PACE = re.compile(r'\bM11 pacing series=(guest_swap|host_present) ((?:\w+=-?\d+ ?)+)$')
VBLANK = re.compile(r'\bM16 vblank mode=(deadline|poll) ((?:\w+=\d+ ?)+)$')
SCENE = re.compile(r'\blevel=(menumap|intro_10|intro_15)\b')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(b):
    return hashlib.sha256(b).hexdigest()


def strict(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            need(k not in out, 'duplicate JSON key')
            out[k] = v
        return out
    def invalid(_):
        raise ValueError('non-JSON constant')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def read_stable(path, limit):
    """Bounded regular-file read; detect links, active writes, replacements and races."""
    need(path.resolve() == path and not path.is_symlink(), 'noncanonical/linked input')
    before = path.stat()
    need(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'input size/type')
    with path.open('rb') as f:
        opened = os.fstat(f.fileno())
        raw = f.read(limit + 1)
        end = os.fstat(f.fileno())
    after = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    need(path.resolve() == path and not path.is_symlink() and
         identity(before) == identity(opened) == identity(end) == identity(after)
         and len(raw) == before.st_size, 'input changed; STOP, preserve output, no automatic retry')
    return raw


def warning_kind(line):
    # Never export shader words, file paths, assets or arbitrary warning strings.
    if 'Texture fetch constant' in line and '"invalid" type' in line:
        return 'invalid_texture_fetch_constant'
    if '[NtCreateFile] FAILED:' in line:
        return 'guest_file_open_failed'
    if 'SDL GameControllerDB:' in line:
        return 'controller_database_warning'
    if 'Available Vulkan physical devices' in line or re.search(r'\* \d+:', line):
        return 'device_enumeration_warning'
    if 'VFS:' in line:
        return 'vfs_warning'
    return 'unclassified_warning'


def analyze(raw):
    result = {'timing': [], 'scene_hints': [], 'diagnostic_sampling': [], 'warnings': {}, 'warning_fingerprints': {},
              'm16_cp_wait_labels': {}, 'errors': 0, 'gpu_debug_present_records': 0,
              'linux_gpu_wait_unmodified': False, 'malformed_timing_lines': 0}
    warnings = collections.Counter(); fingerprints = collections.Counter(); cp = collections.Counter()
    lines = raw.splitlines()
    for b in lines:
        need(len(b) <= 65536, 'oversized log line')
        line = b.decode('utf-8', errors='replace')
        ts = STAMP.match(line)
        stamp = ts[1] if ts else None
        if stamp:
            datetime.fromisoformat(stamp)  # Reject malformed numerical time fields.
        if '[warning]' in line:
            warnings[warning_kind(line)] += 1
            # Stable across timestamp/TID prefixes; actual text remains private/native.
            message = re.sub(r'^.*?\[t\d+\] ', '', line)
            fingerprints[digest(message.encode())] += 1
        result['errors'] += bool('[error]' in line or '[critical]' in line)
        result['gpu_debug_present_records'] += 'XELOG_GPU PRESENT:' in line
        result['linux_gpu_wait_unmodified'] |= 'M11 gpu_wait timed sleep unavailable on Linux' in line
        if 'M16 cp_wait' in line:
            match = re.search(r'\bmode=(vblank_event|sleep)\b', line)
            cp[match[1] if match else 'unparsed'] += 1
        sampled = re.search(r'\bM31 sampled (invalid_fetch|invalid_type_warning) count=(\d+) \(first (\d+), then every (\d+)\)', line)
        if sampled:
            need(len(result['diagnostic_sampling']) < 2000, 'diagnostic sampling bound')
            result['diagnostic_sampling'].append({'time': stamp, 'kind': sampled[1],
                                                   'count': int(sampled[2]), 'first': int(sampled[3]),
                                                   'every': int(sampled[4])})
        match = PACE.search(line) or VBLANK.search(line)
        if match:
            need(len(result['timing']) < 2000, 'timing bound')
            fields = {k: int(v) for k, v in re.findall(r'(\w+)=(-?\d+)', match[2])}
            result['timing'].append({'kind': 'M11' if 'M11 pacing' in line else 'M16',
                                     'mode_or_series': match[1], 'time': stamp, 'fields': fields})
        elif 'M11 pacing' in line or 'M16 vblank' in line:
            result['malformed_timing_lines'] += 1
        scene = SCENE.search(line)
        if scene:
            need(len(result['scene_hints']) < 2000, 'scene-hint bound')
            result['scene_hints'].append({'time': stamp, 'level_hint': scene[1]})
        need(len(fingerprints) <= 2000, 'warning diversity bound')
    result['warnings'] = dict(warnings)
    result['warning_fingerprints'] = dict(fingerprints)
    result['m16_cp_wait_labels'] = dict(cp)
    result['cpu_per_thread'] = 'UNKNOWN; not reconstructible from these logs'
    result['visible_frame_cadence'] = 'UNKNOWN; no display measurement'
    return result


def authenticate(task):
    home = task / 'portable'
    need(digest(read_stable(task / 'portable-private-evidence.zip', 1000000)) == ACCEPTED,
         'accepted E-410 evidence differs; do not rerun integration')
    manifest_raw = read_stable(home / 'portable.json', 1000000)
    need(digest(manifest_raw) == PORTABLE, 'canonical portable manifest differs')
    manifest = strict(manifest_raw)
    need(manifest['publishable'] is False, 'private baseline required')
    names = manifest['files']
    need(all(n in names for n in REQUIRED), 'program inventory')
    for n, row in names.items():
        parts = PurePosixPath(n).parts
        need(n == '/'.join(parts) and not PurePosixPath(n).is_absolute()
             and not any(p in ('.', '..') for p in parts), 'program path')
        raw = read_stable(home / n, 300000000)
        need(len(raw) == row['size'] and digest(raw) == row['sha256'], 'program integrity mismatch')
    settings = read_stable(home / 'settings.json', 1000000)
    need(digest(settings) == SETTINGS, 'settings changed since acceptance; STOP for review')
    return {'portable_manifest_sha256': PORTABLE, 'accepted_evidence_sha256': ACCEPTED,
            'settings_sha256': SETTINGS, 'programs_checked': len(names)}


def collect(task, out):
    need(task.resolve() == task and task.is_dir(), 'real existing task required')
    need(not out.exists() and not out.is_symlink(), 'output exists; preserve it')
    need(out.parent.resolve() == out.parent and out.parent.is_dir(), 'output parent must already be real')
    verified = authenticate(task)
    sessions_root = task / 'portable/sessions'
    need(sessions_root.resolve() == sessions_root, 'linked sessions')
    sessions = sorted(sessions_root.iterdir())
    need(len(sessions) == 1 and sessions[0].is_dir() and sessions[0].resolve() == sessions[0],
         'expected one accepted normal launch; no guessing another session')
    session = sessions[0]
    files = sorted(session.glob('runtime*.log'))
    need(1 <= len(files) <= 8, 'retained runtime inventory')
    before = {}; rows = []; total = 0
    for i, path in enumerate(files):
        raw = read_stable(path, 32000000); total += len(raw)
        need(total <= 96000000, '96MB read bound')
        before[path] = digest(raw)
        rows.append({'index': i, 'size': len(raw), 'sha256': digest(raw), **analyze(raw)})
    # The export intentionally omits session names, paths and raw lines.
    need(files == sorted(session.glob('runtime*.log')), 'log rotation during collection')
    for path, h in before.items():
        need(digest(read_stable(path, 32000000)) == h, 'logs changed during collection')
    need(authenticate(task) == verified, 'program/settings identity changed')
    report = {'owner': 'R3HD_MENU_RETAINED_01', 'identity': verified, 'logs': rows,
              'scope': 'READ ONLY; no game launch/process inspection or CPU measurement',
              'limitations': ['No new launch; CPU and actual visible cadence UNKNOWN',
                              'M11 guest_swap and host_present hooks are D3D12-only',
                              'Linux M16 cp_wait vblank_event label does not prove an event wait',
                              'Rotated/omitted logs and scene-boundary gaps remain explicit',
                              'Warnings counted/classified, never certified harmless']}
    payload = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    need(len(payload) <= 4000000, 'output bound')
    out.mkdir(mode=0o700)
    zpath = out / 'menu-private-evidence.zip'
    with zipfile.ZipFile(zpath, 'x', zipfile.ZIP_DEFLATED) as z:
        z.writestr('retained.json', payload)
        z.writestr('SHA256SUMS', digest(payload) + '  retained.json\n')
    with Path(str(zpath) + '.sha256').open('x', encoding='ascii') as f:
        f.write(digest(zpath.read_bytes()) + '  ' + zpath.name + '\n')
    print('R3HD_MENU_RETAINED READY; NO GAME EXECUTION; CPU UNKNOWN')


def main():
    need(len(sys.argv) == 1, 'no arguments; fixed accepted home only')
    need(sys.platform == 'linux' and os.getuid() != 0, 'native nonroot Linux only')
    need('microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower(), 'WSL fixtures only')
    collect(Path.home() / 'Projects/R3HD-noble-portable-01',
            Path.home() / 'Projects/R3HD-menu-evidence-01')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as e:
        print('R3HD_MENU_RETAINED STOP: ' + str(e), file=sys.stderr)
        sys.exit(2)
