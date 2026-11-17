#!/usr/bin/env python3
"""Build/apply/check a private Gate C recipe-only update. No container/build calls.

Only a fresh task's original exact two-file recipe is accepted. Backups/evidence stay
under that task. Existing source kit, SDK, work tree, transfer and image logs are untouched.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

HERE = Path(__file__).resolve().parent
OLD_RECIPE = 'aad5ef2125ab6a53f7186f3694c1e0da0c947075bb93f38a52e197ded7a4ce33'
SOURCES = 'df2fdea0e7c79cf06f8a5703c9df02017b19198d715318c70c5bae304d833e2e'
PAYLOAD = ('Containerfile', 'validate_apt_sources.sh', 'resume_gate_c.sh')
BACKUP = 'gate-c-comments-update'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def need(condition, message):
    if not condition:
        raise ValueError(message)


def regular(path):
    need(path.is_file() and not path.is_symlink(), 'expected regular file: '+str(path))
    return path.read_bytes()


def manifest(package):
    data = json.loads(regular(package/'UPDATE.json'))
    need(data['format'] == 'R3HD_GATE_C_COMMENTS_V1' and set(data['payload']) == set(PAYLOAD), 'invalid update inventory')
    need(data['original_containerfile'] == OLD_RECIPE and data['ubuntu_sources'] == SOURCES, 'unexpected original recipe identity')
    for n, h in data['payload'].items():
        need(sha(regular(package/n)) == h, 'package payload hash mismatch: '+n)
    return data


def task_recipe(task):
    need(task.is_dir() and task.absolute() == task.resolve(), 'task must be a real directory without symlink ancestors')
    recipe, evidence = task/'recipe', task/'evidence'
    for path in (recipe, evidence):
        need(path.is_dir() and not path.is_symlink(), 'missing or symlink task directory: '+str(path))
    need(sha(regular(recipe/'ubuntu.sources')) == SOURCES, 'snapshot source local edit; preserve and stop')
    return recipe, evidence


def check(task, package=HERE):
    data = manifest(package)
    recipe, evidence = task_recipe(task)
    need({p.name for p in recipe.iterdir()} == {'Containerfile','ubuntu.sources','validate_apt_sources.sh'}, 'unexpected recipe entries')
    for n in ('Containerfile','validate_apt_sources.sh'):
        need(sha(regular(recipe/n)) == data['payload'][n], 'updated recipe hash mismatch: '+n)
    backup = evidence/BACKUP
    need(backup.is_dir() and not backup.is_symlink(), 'update backup missing')
    need(sha(regular(backup/'Containerfile')) == OLD_RECIPE, 'original backup mismatch')
    need(sha(regular(backup/'ubuntu.sources')) == SOURCES, 'source backup mismatch')
    need(regular(backup/'UPDATE.json') == regular(package/'UPDATE.json'), 'update receipt mismatch')
    print('R3HD_GATE_C_RECIPE_CHECK PASS (recipe only; native image build NOT tested)')


def apply(task, package=HERE):
    data = manifest(package)
    recipe, evidence = task_recipe(task)
    need({p.name for p in recipe.iterdir()} == {'Containerfile','ubuntu.sources'}, 'recipe has unexpected/new files; no overwrite/reapply')
    need(sha(regular(recipe/'Containerfile')) == OLD_RECIPE, 'Containerfile local edit; preserve and stop')
    backup = evidence/BACKUP
    need(not backup.exists() and not backup.is_symlink(), 'update evidence already exists')
    temp = recipe/'Containerfile.comments-update.tmp'
    need(not temp.exists() and not temp.is_symlink(), 'update temporary path already exists')
    backup.mkdir()
    for n in ('Containerfile','ubuntu.sources'):
        with (backup/n).open('xb') as f:
            f.write(regular(recipe/n))
    with (backup/'UPDATE.json').open('xb') as f:
        f.write(regular(package/'UPDATE.json'))
    with (recipe/'validate_apt_sources.sh').open('xb') as f:
        f.write(regular(package/'validate_apt_sources.sh'))
    with temp.open('xb') as f:
        f.write(regular(package/'Containerfile'))
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, recipe/'Containerfile')
    check(task, package)
    print('R3HD_GATE_C_RECIPE_UPDATE PASS; STOP until explicit native resume')


def build():
    need(sha(regular(HERE/'Containerfile')) == '9984d177b947254385df42fa8ee1ea1a76b1f6ef36526226c5eda8cac71459e0',
         'E-387 builder superseded: use bootstrap_update.py for the TLS-bootstrap recipe')
    root = HERE.parents[2]
    out = root/'private/work/linux_build/baseline_gate_c_update'
    need(not out.exists(), 'output already exists; preserve it')
    entries = {n: (HERE/n).read_bytes().replace(b'\r\n',b'\n') for n in PAYLOAD}
    entries['apply_update.py'] = Path(__file__).read_bytes().replace(b'\r\n',b'\n')
    data = {'format':'R3HD_GATE_C_COMMENTS_V1', 'original_containerfile':OLD_RECIPE, 'ubuntu_sources':SOURCES,
            'payload':{n:sha(entries[n]) for n in PAYLOAD}}
    entries['UPDATE.json'] = (json.dumps(data, indent=2)+'\n').encode()
    out.mkdir()
    archive = out/'r3hd-stage2a-gate-c-update.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(2026,11,8,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info,content)
    digest = sha(archive.read_bytes())
    (out/(archive.name+'.sha256')).write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps({'path':str(archive),'bytes':archive.stat().st_size,'sha256':digest}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('build','apply','check'))
    parser.add_argument('--task',type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'build':
            build()
        else:
            need(args.task is not None, '--task required')
            (apply if args.action == 'apply' else check)(args.task)
    except (ValueError,OSError,KeyError) as e:
        print('R3HD_GATE_C_UPDATE STOP:',e,file=sys.stderr)
        sys.exit(2)
