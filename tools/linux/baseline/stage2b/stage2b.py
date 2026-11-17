#!/usr/bin/env python3
"""Stage 2B isolated preparation and static acceptance. Never launches the game."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA = '441a173c2e3911859373c5bf55686cf51ff247669ab6bb8605d438b9a406224d'
CEILINGS = {'GLIBC': (2, 39), 'GLIBCXX': (3, 4, 33)}
COMPONENTS = ('r3hd', 'librexruntime.so', 'librexgpu-xenos.so', 'libffmpeg.so', 'libmspack.so')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(1024*1024), b''):
            h.update(data)
    return h.hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write('\n')


def command(*args, cwd=None):
    return subprocess.check_output(list(map(str, args)), cwd=cwd, text=True, stderr=subprocess.STDOUT)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bundle_check():
    record = json.loads((HERE/'BUNDLE.json').read_bytes())
    files = {p.relative_to(HERE).as_posix() for p in HERE.rglob('*') if not p.is_dir()}
    need(files == set(record['files']) | {'BUNDLE.json'}, 'toolkit inventory changed')
    for name, digest in record['files'].items():
        p = HERE/name
        need(not p.is_symlink() and sha(p) == digest, 'toolkit hash/type: '+name)
    print('R3HD_STAGE2B_TOOLKIT PASS')


def version_limits(text):
    result = {}
    need('GLIBC_PRIVATE' not in text, 'private glibc ABI referenced')
    for prefix, ceiling in CEILINGS.items():
        values = {tuple(map(int, v.split('.'))) for v in re.findall(r'\b'+prefix+r'_(\d+(?:\.\d+)+)', text)}
        need(not values or max(values) <= ceiling, 'ABI ceiling exceeded: '+prefix)
        result[prefix] = '.'.join(map(str, max(values))) if values else None
    return result


def feature_evidence(old):
    out = old/'evidence/expected19-01'
    need((out/'exit-status.txt').read_text().strip() == '0', 'native D exit status is not zero')
    log = (out/'probe.log').read_text()
    for marker in ('R3HD_BASELINE_FEATURE PASS 42:42',
                   'R3HD_BASELINE_PROBE PASS (feature only; full SDK/game not built)'):
        need(marker in log, 'native D marker missing: '+marker)
    need('19.1.1' in log, 'native D compiler version missing')
    search = (out/'probe/compiler-search.txt').read_text()
    need(re.search(r'Selected GCC installation: .*/13\s*$', search, re.M), 'native D did not select GCC13')
    seen = set()
    for line in (out/'probe/SHA256SUMS').read_text().splitlines():
        m = re.fullmatch(r'([0-9a-f]{64}) [ *](.+)', line)
        need(m, 'malformed native D checksum')
        name = Path(m[2]).name
        need(name in ('feature', 'r3hd-packages.tsv') and name not in seen, 'unexpected/duplicate native D checksum')
        need(sha(out/'probe'/name) == m[1], 'native D checksum mismatch: '+name)
        seen.add(name)
    need(len(seen) == 2, 'both native D checksums required')
    image = (out/'image.id').read_text().strip()
    need(re.fullmatch(r'sha256:[0-9a-f]{64}', image), 'native D image ID malformed')
    return {'image_id': image, 'probe_sha256': sha(out/'probe/feature'),
            'packages_sha256': sha(out/'probe/r3hd-packages.tsv')}


def engine_check(pre, info, task, filesystem=None):
    storage = pre['checks']['storage']; h, s = info['host'], info['store']
    need(pre['status'] == 'STATIC_PREFLIGHT_PASS' and not pre['failures'], 'static preflight failed')
    need(h['security']['rootless'] is True and h['security']['seccompEnabled'] is True,
         'rootless/seccomp required')
    need(h.get('serviceIsRemote') is False and h['arch'] == 'amd64', 'local amd64 engine required')
    need(s['graphDriverName'] == 'overlay', 'rootless overlay required')
    for actual, expected in (('graphRoot', 'graphroot_predicted'), ('imageCopyTmpDir', 'image_copy_tmp_dir_predicted')):
        need(Path(s[actual]).resolve() == Path(storage[expected]).resolve(), 'engine storage differs: '+actual)
    need(Path(s['runRoot']).resolve().is_relative_to((Path('/run/user')/str(os.getuid())).resolve()), 'unexpected runroot')
    for name in ('uidmap', 'gidmap'):
        need(sum(row['size'] for row in h['idMappings'][name]) >= 65537, 'insufficient '+name)
    # Keep the approved Stage2A UUID/source identity rule, including Btrfs subvolumes.
    # st_dev alone is not the preflight's definition of one backing filesystem.
    if filesystem is None:
        filesystem = load_module('preflight_storage', HERE/'preflight.py').filesystem
    rows = [filesystem(p) for p in (task, Path(s['graphRoot']), Path(s['imageCopyTmpDir']))]
    need(len({r.get('uuid') or r['source'].split('[')[0] for r in rows}) == 1, 'one shared filesystem required')
    for row in rows:
        need(row['fstype'] in ('ext4','btrfs','xfs') and 'ro' not in row['options'].split(','), 'unsupported/read-only backing filesystem')
        need(row['available_bytes'] >= 50_000_000_000, 'less than 50,000,000,000 free bytes')
    return rows


def extract(archive, task):
    """Exact original kit, checked in full before any member write. Destination already empty."""
    need(sha(archive) == ARCHIVE_SHA, 'sealed archive SHA mismatch')
    verify = load_module('kit_verify', HERE/'kit_verify.py')
    manifest = verify.verify(archive)
    need(not any((task/n).exists() or (task/n).is_symlink() for n in ('work', 'recipe', 'KIT_MANIFEST.json')),
         'extraction destination already occupied')
    with tarfile.open(archive, 'r:gz') as tar:
        # Create each directory once (important for read-only archive reuse across filesystems).
        dirs = {p for m in tar.getmembers() for p in (task/m.name).parents if p != task and task in p.parents}
        for p in sorted(dirs, key=lambda x: len(x.parts)):
            p.mkdir(exist_ok=True)
        for m in tar:
            p = task/m.name
            if m.issym():
                p.symlink_to(m.linkname)
            else:
                with p.open('xb') as f:
                    shutil.copyfileobj(tar.extractfile(m), f, length=4*1024*1024)
                p.chmod(m.mode)
    for name, pin in sorted(manifest['sdk_repositories'].items(), key=lambda x: -len(x[0])):
        repo = task/name
        command('git', '-C', repo, 'read-tree', 'HEAD')
        need(command('git', '-C', repo, 'rev-parse', 'HEAD').strip() == pin, 'SDK pin mismatch')
        need(not command('git', '-C', repo, 'status', '--porcelain', '--untracked-files=all'), 'SDK not pristine: '+name)
        command('git', '-C', repo, 'fsck', '--connectivity-only', '--no-reflogs')
    print('R3HD_STAGE2B_EXTRACT PASS repositories=24')


def immutable(work, manifest):
    """Project + entire LM-A tree remain byte-identical; SDK worktree patching is deliberate."""
    for name, meta in manifest['entries'].items():
        if not name.startswith('work/') or name.startswith('work/external/'):
            continue
        p = work/name.removeprefix('work/')
        need(p.is_symlink() == (meta['type'] == 'symlink'), 'sealed file type changed: '+name)
        actual = hashlib.sha256(os.readlink(p).encode()).hexdigest() if p.is_symlink() else sha(p)
        need(actual == meta['sha256'], 'sealed project/LM-A file changed: '+name)
    for name, pin in manifest['sdk_repositories'].items():
        repo = work.parent/name
        need(command('git', '-C', repo, 'rev-parse', 'HEAD').strip() == pin, 'SDK pin moved: '+name)
        if name != 'work/external/rexglue-sdk':
            need(not command('git', '-C', repo, 'status', '--porcelain', '--untracked-files=no'), 'submodule source changed: '+name)
    # Compare the whole existing patch replay, including new headers, not only its pin.
    sys.path.insert(0, str(work/'tools'))
    import r3hd_build_doctor
    actual = r3hd_build_doctor.sdk_digest(work/'external/rexglue-sdk')
    expected = json.loads((HERE/'SDK_REPLAY.json').read_bytes())
    need(actual == (expected['files'], expected['digest']), 'SDK replay differs from isolated source-only preparation')
    return {'immutable_project_and_lma': True, 'sdk_pins': manifest['sdk_repositories']}


def audit_elf(path, out, library_path):
    need(path.is_file() and not path.is_symlink(), 'missing ELF: '+str(path))
    head = path.read_bytes()[:20]
    need(head[:6] == b'\x7fELF\x02\x01' and head[18:20] == b'\x3e\x00', 'not amd64 ELF: '+str(path))
    raw = command('readelf', '-h', '-l', '-d', '-V', '-W', path)
    symbols = command('objdump', '-T', path)
    undefined = '\n'.join(l for l in symbols.splitlines() if '*UND*' in l)
    limits = version_limits(undefined)
    needed = re.findall(r'\(NEEDED\).*\[(.*?)\]', raw)
    interpreter = re.findall(r'Requesting program interpreter: ([^\]]+)', raw)
    if path.name == 'r3hd':
        need(interpreter == ['/lib64/ld-linux-x86-64.so.2'], 'unexpected executable interpreter')
    rpaths = re.findall(r'\((?:RUNPATH|RPATH)\).*\[(.*?)\]', raw)
    # Build/private absolute RPATHs must not silently become portable package dependencies.
    for group in rpaths:
        for item in group.split(':'):
            need(item in ('$ORIGIN', '$ORIGIN/../lib'), 'unsupported packaged RPATH: '+item)
    env = dict(os.environ, LD_LIBRARY_PATH=str(library_path))
    env.pop('LD_PRELOAD', None); env.pop('LD_AUDIT', None)
    loader = '/lib64/ld-linux-x86-64.so.2'
    p = subprocess.run([loader, '--list', str(path)], env=env, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
    (out/(path.name+'.readelf.txt')).write_text(raw)
    (out/(path.name+'.symbols.txt')).write_text(symbols)
    (out/(path.name+'.loader.txt')).write_text(p.stdout)
    need(p.returncode == 0 and 'not found' not in p.stdout, 'loader/version closure failure: '+path.name)
    return {'sha256': sha(path), 'bytes': path.stat().st_size, 'requires': limits,
            'needed': needed, 'interpreter': interpreter, 'rpath': rpaths, 'loader_exit': p.returncode}


def results(work, out):
    build = out/'build/game-lma'; lib = work/'external/rexglue-sdk/out/install/linux-amd64/lib'
    for name in ('results.json', 'results-game-lma.json', 'results-gamesync.json'):
        record = json.loads((out/name).read_bytes())
        need(record['status'] == 'PASS', name+' did not pass')
    stage = out/'abi-payload'; stage.mkdir()
    for name in COMPONENTS:
        shutil.copy2((build if name in ('r3hd', 'librexgpu-xenos.so') else lib)/name, stage/name)
    evidence = out/'abi'; evidence.mkdir()
    row = {name: audit_elf(stage/name, evidence, stage) for name in COMPONENTS}
    need(row['r3hd']['requires']['GLIBC'] and row['r3hd']['requires']['GLIBCXX'], 'executable requirements missing')
    for mode in ('plain', 'modified'):
        folder = out/('lgpl-'+mode)/'r3hd-lgpl-source/build'
        dest = out/('abi-'+mode); dest.mkdir()
        for name in ('libffmpeg.so', 'libmspack.so'):
            # Replacement may have no RPATH, and must resolve against the same Noble providers.
            row[mode+'/'+name] = audit_elf(folder/name, dest, folder)
    write(out/'abi.json', {'status': 'PASS', 'ceilings': {'GLIBC': '2.39', 'GLIBCXX': '3.4.33'}, 'components': row})
    print('R3HD_STAGE2B_ABI PASS payload=5 replacements=4 (loader list only; no game entrypoint)')


def backend_check(work, out):
    cache = work/'external/rexglue-sdk/out/build/linux-amd64/CMakeCache.txt'
    text = cache.read_text()
    values = dict(re.findall(r'^([^/#][^:=\n]*):[^=\n]*=(.*)$', text, re.M))
    required = ('SDL_X11', 'SDL_WAYLAND', 'SDL_VULKAN', 'SDL_ALSA', 'SDL_PULSEAUDIO', 'SDL_PIPEWIRE')
    need(all(values.get(n) in ('ON', 'TRUE', '1') for n in required), 'required SDL backend option missing/off')
    # Confirm compiled SDL backend configuration, not merely requested CMake options.
    # Pinned SDL generates one header per Multi-Config configuration. Judge Release only.
    candidates = [p for p in cache.parent.rglob('SDL_build_config.h') if 'include-config-release' in p.parts]
    need(len(candidates) == 1, 'expected one Release SDL_build_config.h')
    config = candidates[0].read_text()
    macros = ('SDL_VIDEO_DRIVER_X11', 'SDL_VIDEO_DRIVER_WAYLAND', 'SDL_VIDEO_VULKAN', 'SDL_AUDIO_DRIVER_ALSA',
              'SDL_AUDIO_DRIVER_PULSEAUDIO', 'SDL_AUDIO_DRIVER_PIPEWIRE')
    need(all(re.search(r'^#define '+n+r'\s+1\s*$', config, re.M) for n in macros), 'SDL compiled backend absent')
    shutil.copy2(cache, out/'sdk-CMakeCache.txt')
    shutil.copy2(candidates[0], out/'SDL_build_config.h')
    write(out/'backends.json', {'status': 'PASS', 'cmake': {n: values[n] for n in required}, 'compiled': list(macros),
          'runtime_audio_video_devices': 'UNKNOWN; no game or device execution'})
    print('R3HD_STAGE2B_BACKENDS PASS (compiled availability only)')


def package_record(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate package record key: '+key)
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError('non-JSON package record constant: '+value)
    checked = json.loads(data, object_pairs_hook=unique, parse_constant=invalid_constant)
    need(isinstance(checked, dict), 'package record is not an object')
    need(checked.get('result') == 'PASS' and checked.get('publishable') is False,
         'package check not private PASS')
    need(isinstance(checked.get('sha256'), str) and
         re.fullmatch('[0-9a-f]{64}', checked['sha256']), 'invalid package record hash')
    return checked


def package_accept(out):
    checked = package_record((out/'package-check.json').read_bytes())
    need(checked['result'] == 'PASS' and checked['publishable'] is False, 'package check not private PASS')
    package = out/'r3hd-linux-noble-2b01.tar.gz'
    need(sha(package) == checked['sha256'], 'package changed after check')
    abi = json.loads((out/'abi.json').read_bytes())['components']
    observed = set(); portable = None
    with tarfile.open(package, 'r:gz') as tar:
        for m in tar:
            prefix = 'Rayman3HDRecompiled-Linux/'
            name = m.name.removeprefix(prefix)
            if name.startswith('bin/'):
                leaf = name.removeprefix('bin/')
                need(leaf in COMPONENTS and leaf not in observed and m.isfile(), 'unexpected package native component')
                h = hashlib.sha256()
                with tar.extractfile(m) as f:
                    for chunk in iter(lambda: f.read(1024*1024), b''):
                        h.update(chunk)
                need(h.hexdigest() == abi[leaf]['sha256'], 'packaged component differs from ABI audit: '+leaf)
                observed.add(leaf)
            elif name == 'portable.json':
                portable = json.load(tar.extractfile(m))
    need(observed == set(COMPONENTS) and portable is not None, 'package native inventory incomplete')
    need(portable['publishable'] is False, 'portable is publishable')
    source = portable['lgpl']['corresponding_source']
    need(isinstance(source, dict) and Path(source['archive']).name == source['archive'], 'LGPL source archive missing')
    need(sha(out/'lgpl'/source['archive']) == source['sha256'], 'LGPL source hash mismatch')
    write(out/'acceptance.json', {'status': 'PASS', 'package_sha256': checked['sha256'],
          'lgpl_source_sha256': source['sha256'], 'native_components': sorted(observed),
          'game_executed': False, 'publishable': False})
    print('R3HD_STAGE2B_ACCEPT PASS (private build/static package only)')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=('check', 'evidence', 'engine', 'extract', 'immutable', 'backends', 'abi', 'package'))
    ap.add_argument('--task', type=Path); ap.add_argument('--archive', type=Path); ap.add_argument('--old', type=Path)
    a = ap.parse_args()
    bundle_check()
    if a.action == 'check':
        return
    if a.action == 'evidence':
        print(feature_evidence(a.old)['image_id']); return
    task = a.task.resolve(); work = task/'work'; out = work/'private/work/linux_build/noble_2b01'
    if a.action == 'engine':
        rows = engine_check(json.loads((task/'evidence/preflight.json').read_bytes()),
                            json.loads((task/'evidence/podman-info.json').read_bytes()), task)
        write(task/'evidence/disk-budget.json', rows)
    elif a.action == 'extract':
        need(task == Path.home()/'Projects/R3HD-baseline-noble-2b-01', 'unexpected native workspace')
        extract(a.archive, task)
    elif a.action == 'immutable':
        result = immutable(work, json.loads((task/'KIT_MANIFEST.json').read_bytes()))
        write(task/'evidence/sealed-inputs-after.json', result)
        print('R3HD_STAGE2B_IMMUTABLE PASS')
    elif a.action == 'backends':
        backend_check(work, out)
    elif a.action == 'abi':
        results(work, out)
    elif a.action == 'package':
        package_accept(out)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        print('R3HD_STAGE2B STOP:', error, file=sys.stderr)
        sys.exit(2)
