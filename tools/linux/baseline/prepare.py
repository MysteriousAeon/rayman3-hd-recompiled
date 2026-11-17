#!/usr/bin/env python3
"""Private Stage 2A source sealing. No patch chain/build/download/system change.

seal reads committed project 0414e72 + explicitly listed preparation files, Git object
databases at configured SDK pins (ignoring patched worktrees), and the existing LM-A ZIP.
verify reads the archive without extracting. unpack is Linux-only into the one new task path.
All output stays under private/work/linux_build/baseline_2a_final; refuses existing destinations.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import platform
import posixpath
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PREP = ('LOCK.json', 'Containerfile', 'ubuntu.sources', 'feature.cpp', 'probe.sh',
        'preflight.py', 'prepare.py', 'test_preparation.py', 'preflight_update.py',
        'validate_apt_sources.sh', 'resume_gate_c.sh', 'gate_c_update.py', 'test_gate_c.py',
        'bootstrap_apt.sh', 'validate_snapshot_lists.sh', 'BOOTSTRAP_LOCK.json',
        'bootstrap_update.py', 'resume_gate_c_tls.sh', 'test_bootstrap.py')
sha = lambda b: hashlib.sha256(b).hexdigest()


def need(condition, message):
    if not condition:
        raise ValueError(message)


def git(repo, *args, data=None):
    return subprocess.check_output(['git', '-c', 'core.autocrlf=false', '-C', str(repo), *args], input=data)


def safe_name(name):
    p = PurePosixPath(name)
    need(name and not p.is_absolute() and '..' not in p.parts and '\\' not in name
         and ':' not in name and str(p) == name, 'unsafe archive path: '+name)


def safe_link(name, target):
    need(target and not target.startswith('/') and '\\' not in target and ':' not in target, 'unsafe symlink')
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
    need(resolved != '..' and not resolved.startswith('../'), 'symlink escapes kit')


class Writer:
    def __init__(self, tar):
        self.tar, self.entries = tar, {}

    def add(self, name, data, mode=0o644, link=False):
        safe_name(name)
        need(name not in self.entries, 'duplicate '+name)
        if link:
            safe_link(name, data.decode())
        meta = tarfile.TarInfo(name)
        meta.mode, meta.mtime = mode, 0
        if link:
            meta.type, meta.linkname = tarfile.SYMTYPE, data.decode()
        else:
            meta.size = len(data)
        self.tar.addfile(meta, None if link else io.BytesIO(data))
        self.entries[name] = {'sha256': sha(data), 'size': len(data), 'mode': mode,
                              'type': 'symlink' if link else 'file'}

    def archive(self, repo, rev, prefix, source=False):
        raw = git(repo, 'archive', '--format=tar', rev)
        with tarfile.open(fileobj=io.BytesIO(raw)) as src:
            for m in src:
                if m.isdir():
                    continue
                if source:
                    need(not m.name.startswith(('private/', 'external/', 'generated/')), 'forbidden project input')
                need(m.isfile() or m.issym(), 'unsupported Git archive member')
                data = m.linkname.encode() if m.issym() else src.extractfile(m).read()
                self.add(prefix+m.name, data, m.mode, m.issym())


def sdk_export(writer, repo, pin, prefix, identities):
    # Traverse committed gitlinks, never the dirty SDK/submodule worktrees.
    need(git(repo, 'rev-parse', 'HEAD').decode().strip() == pin, 'checkout pin mismatch '+str(repo))
    rows = git(repo, 'ls-tree', '-r', '-t', '-z', pin).split(b'\0')
    objects, modules = {pin, git(repo, 'rev-parse', pin+'^{tree}').decode().strip()}, []
    blobs = []
    for row in filter(None, rows):
        head, name = row.split(b'\t', 1)
        mode, typ, oid = head.decode().split()
        if mode == '160000':
            modules.append((name.decode(), oid))
        else:
            objects.add(oid)
            if typ == 'blob':
                blobs.append((name.decode(), oid, mode))
    # Git archive can honor export-ignore/export-subst. SDK must instead retain every
    # exact committed blob, otherwise its pristine-state check can falsely fail later.
    batch = io.BytesIO(git(repo, 'cat-file', '--batch', data=('\n'.join(r[1] for r in blobs)+'\n').encode()))
    for name, oid, mode in blobs:
        header = batch.readline().decode().split()
        need(header[:2] == [oid, 'blob'], 'Git blob read failed')
        data = batch.read(int(header[2]))
        need(batch.read(1) == b'\n', 'Git batch separator')
        writer.add(prefix+name, data, 0o755 if mode == '100755' else 0o644, mode == '120000')
    # A shallow single original commit, its tree/blob closure; no development history,
    # remote, alternates, local paths, hooks, reflogs, index or build outputs.
    pack = git(repo, 'pack-objects', '--stdout', '--threads=1', data=('\n'.join(sorted(objects))+'\n').encode())
    with tempfile.TemporaryDirectory(prefix='r3hd-baseline-git-') as tmp:
        git(Path(tmp), 'init', '--bare', '--quiet')
        git(Path(tmp), 'index-pack', '--stdin', data=pack)
        for p in sorted((Path(tmp)/'objects/pack').iterdir()):
            writer.add(prefix+'.git/objects/pack/'+p.name, p.read_bytes())
    writer.add(prefix+'.git/HEAD', (pin+'\n').encode())
    writer.add(prefix+'.git/refs/heads/baseline-input', (pin+'\n').encode())
    writer.add(prefix+'.git/shallow', (pin+'\n').encode())
    writer.add(prefix+'.git/config', b'[core]\n repositoryformatversion = 0\n bare = false\n filemode = true\n symlinks = true\n autocrlf = false\n')
    identities[prefix.rstrip('/')] = pin
    for name, commit in modules:
        sdk_export(writer, repo/name, commit, prefix+name+'/', identities)


def lma_entries():
    source = ROOT/'private/work/linux_build/lma-private-tree.zip'
    with zipfile.ZipFile(source) as z:
        names = z.namelist()
        need(len(names) == len(set(names)), 'duplicate LM-A ZIP member')
        entries = {n: z.read(n) for n in names if not n.endswith('/')}
    for name in entries:
        safe_name(name)
        need(name.startswith('rex_lma/'), 'unexpected LM-A member')
    old = json.loads(entries['rex_lma/PRIVATE_MANIFEST.json'])
    need(set(entries) == {'rex_lma/'+n for n in old} | {'rex_lma/PRIVATE_MANIFEST.json'}, 'LM-A file inventory')
    for name, digest in old.items():
        need(sha(entries['rex_lma/'+name]) == digest, 'LM-A input manifest '+name)
    sys.path.insert(0, str(ROOT/'tools/linux'))
    import r3hd_linux_build as driver
    with tempfile.TemporaryDirectory(prefix='r3hd-lma-verify-') as tmp:
        tree = Path(tmp)
        for name, data in entries.items():
            p = tree/name.removeprefix('rex_lma/')
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        driver.verify_tree(tree)
        sys.path.insert(0, str(ROOT/'tools'))
        import r3hd_build_step
        observed = r3hd_build_step.digest(tree/'generated/default')
        pin = json.loads(git(ROOT, 'show', '0414e72:config/build/toolchain.json'))['codegen']
        need(observed == (pin['files'], pin['digest']), 'pinned codegen digest mismatch')
        # Existing verified LX-4 host-only update, solely on this temporary private copy.
        need(driver.hostupdate(argparse.Namespace(tree=tree)) == 0, 'LM-A host update failed')
        for name in entries:
            entries[name] = (tree/name.removeprefix('rex_lma/')).read_bytes()
    entries['rex_lma/PRIVATE_MANIFEST.json'] = (json.dumps({n.removeprefix('rex_lma/'): sha(b)
        for n,b in sorted(entries.items()) if not n.endswith('/PRIVATE_MANIFEST.json')}, indent=2)+'\n').encode()
    return entries, {'original_zip_sha256': sha(source.read_bytes()), 'codegen': pin,
                     'host_update': 'existing LX-4 hostupdate; generated bytes unchanged'}


def seal():
    lock = json.loads((HERE/'LOCK.json').read_text())
    commit = git(ROOT, 'rev-parse', lock['source_commit']+'^{commit}').decode().strip()
    need(git(ROOT, 'merge-base', commit, 'HEAD').decode().strip() == commit,
         'frozen source commit must be an ancestor of HEAD; review source_commit rather than silently changing it')
    out = ROOT/'private/work/linux_build/baseline_2a_final'
    need(not out.exists(), 'output exists; never overwrite/delete it; inspect before choosing a new reviewed checkpoint')
    lma, lma_identity = lma_entries()
    pins = json.loads(git(ROOT, 'show', commit+':config/build/toolchain.json'))['rexglue_sdk']
    out.mkdir()
    archive = out/'r3hd-baseline-2a.tar.gz'
    identities = {}
    with archive.open('xb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode='w') as tar:
            writer = Writer(tar)
            writer.archive(ROOT, commit, 'work/', source=True)
            for name in PREP:
                data = (HERE/name).read_bytes().replace(b'\r\n', b'\n')
                writer.add('work/tools/linux/baseline/'+name, data)
            # Source export remains repository-shaped without a root .git.
            source_files = {n.removeprefix('work/'): m['sha256'] for n,m in writer.entries.items()}
            writer.add('work/SOURCE_MANIFEST.json', (json.dumps(source_files, indent=2)+'\n').encode())
            writer.add('work/IMPLEMENTATION_ID.json', (json.dumps({'commit': commit, 'preparation_overlay': list(PREP)})+'\n').encode())
            for name, data in sorted(lma.items()):
                writer.add('work/private/lma/'+name, data)
            sdk_export(writer, ROOT/pins['path'], pins['commit'], 'work/external/rexglue-sdk/', identities)
            for path, pin in pins['submodules'].items():
                need(identities['work/external/rexglue-sdk/'+path] == pin, 'configured submodule pin mismatch '+path)
            sys.path.insert(0, str(HERE))
            import bootstrap_update
            for name, data in bootstrap_update.inputs().items():
                writer.add('recipe/'+name, data)
            manifest = {'format': 'R3HD_BASELINE_2A_V1', 'project_commit': commit, 'lock': lock,
                        'sdk_repositories': identities, 'lma': lma_identity, 'entries': dict(writer.entries)}
            writer.add('KIT_MANIFEST.json', (json.dumps(manifest, indent=2, sort_keys=True)+'\n').encode())
    verify(archive)
    digest = sha(archive.read_bytes())
    (out/'SHA256SUMS').write_text(digest+'  '+archive.name+'\n', encoding='ascii')
    (out/'KIT_MANIFEST.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    for name in ('prepare.py', 'preflight.py'):
        (out/name).write_bytes((HERE/name).read_bytes().replace(b'\r\n', b'\n'))
    print(json.dumps({'path': str(archive), 'bytes': archive.stat().st_size, 'sha256': digest,
                      'payload_entries': len(manifest['entries']), 'repositories': len(identities)}))


def verify(archive):
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        names = [m.name for m in members]
        need(len(names) == len(set(names)), 'duplicate archive member')
        manifest = json.load(tar.extractfile('KIT_MANIFEST.json'))
        need(manifest['format'] == 'R3HD_BASELINE_2A_V1', 'unknown kit format')
        need(set(names) == set(manifest['entries']) | {'KIT_MANIFEST.json'}, 'kit inventory mismatch')
        links = {m.name for m in members if m.issym()}
        for m in members:
            safe_name(m.name)
            need(m.isfile() or m.issym(), 'unsupported member '+m.name)
            need(not any(str(p) in links for p in PurePosixPath(m.name).parents), 'symlink ancestor')
            data = m.linkname.encode() if m.issym() else tar.extractfile(m).read()
            if m.issym():
                safe_link(m.name, m.linkname)
            if m.name != 'KIT_MANIFEST.json':
                need({'sha256': sha(data), 'size': len(data), 'mode': m.mode,
                      'type': 'symlink' if m.issym() else 'file'} == manifest['entries'][m.name], 'kit hash/type/mode '+m.name)
    print('R3HD_BASELINE_KIT_VERIFY PASS entries='+str(len(names)))
    return manifest


def unpack(archive):
    need(platform.system() == 'Linux', 'unpack only on Linux; verify works on Windows')
    manifest = verify(archive)
    task = Path.home()/'Projects/R3HD-baseline-noble-01'
    need(task.exists() and task.resolve() == task, 'create exact task directory first, no symlink path')
    for name in ('work', 'recipe', 'KIT_MANIFEST.json'):
        need(not (task/name).exists(), 'destination already exists: '+name)
    # All members checked before any extraction; no link can have an extracted child.
    with tarfile.open(archive, 'r:gz') as tar:
        for m in tar:
            p = task/m.name
            p.parent.mkdir(parents=True, exist_ok=True)
            if m.issym():
                p.symlink_to(m.linkname)
            else:
                with p.open('xb') as f:
                    f.write(tar.extractfile(m).read())
                p.chmod(m.mode)
    for name, pin in sorted(manifest['sdk_repositories'].items(), key=lambda row: -len(row[0])):
        repo = task/name
        git(repo, 'read-tree', 'HEAD')  # initialize index only; never checkout or patch files
        need(git(repo, 'rev-parse', 'HEAD').decode().strip() == pin, 'unpacked pin mismatch')
        need(not git(repo, 'status', '--porcelain', '--untracked-files=all'), 'unpacked SDK not pristine '+name)
        git(repo, 'fsck', '--connectivity-only', '--no-reflogs')
    print('R3HD_BASELINE_UNPACK PASS; STOP before SDK/game build')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('seal', 'verify', 'unpack'))
    parser.add_argument('archive', nargs='?', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'seal':
            seal()
        else:
            need(args.archive is not None, 'archive required')
            (verify if args.action == 'verify' else unpack)(args.archive)
    except (ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError, KeyError) as error:
        print('R3HD_BASELINE_STOP:', error, file=sys.stderr)
        sys.exit(2)
