"""Metadata/project-authored portable acceptance kit only; no SDK/game rebuild or archive reseal."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
REF = '504faf44d12cdc88ad6fe5ca3a4a0020b8812007'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def build(out):
    if out.exists() or out.is_symlink():
        raise ValueError('output exists; preserve it')
    files = {n: (HERE / n).read_bytes().replace(b'\r\n', b'\n') for n in ('integration.py', 'HANDOFF.md')}
    mapping = {'checks.py': 'tools/linux/baseline/finalize/checks.py',
               'EVIDENCE_LOCK.json': 'tools/linux/baseline/finalize/EVIDENCE_LOCK.json',
               'ABI_HASHES.json': 'tools/linux/baseline/startup/ABI_HASHES.json',
               'settings_core.py': 'tools/r3hd_settings.py', 'registry.json': 'config/settings/registry.json',
               'content_manifest.tsv': 'reports/milestone1/data/content_manifest.tsv'}
    for name, source in mapping.items():
        files[name] = subprocess.check_output(['git', '-C', str(ROOT), 'show', REF + ':' + source])
    files['SHA256SUMS'] = ''.join(sha(b) + '  ' + n + '\n' for n, b in sorted(files.items())).encode()
    out.mkdir()
    path = out / 'r3hd-normal-portable.zip'
    with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED) as z:
        for n, b in sorted(files.items()):
            item = zipfile.ZipInfo(n, (1980, 1, 1, 0, 0, 0)); item.create_system = 3
            item.compress_type = zipfile.ZIP_DEFLATED; item.external_attr = 0o100644 << 16
            z.writestr(item, b, compresslevel=9)
    Path(str(path) + '.sha256').write_text(sha(path.read_bytes()) + '  ' + path.name + '\n', encoding='ascii')
    (out / 'HANDOFF.md').write_bytes(files['HANDOFF.md'])
    print(path, path.stat().st_size, sha(path.read_bytes()))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', required=True, type=Path)
    build(p.parse_args().out)
