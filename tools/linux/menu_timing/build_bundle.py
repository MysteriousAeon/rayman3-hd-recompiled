"""Deterministic project-authored metadata collector only; no binary/data payload."""
import argparse
import hashlib
from pathlib import Path
import zipfile


def build(out):
    if out.exists() or out.is_symlink():
        raise ValueError('output exists; preserve it')
    here = Path(__file__).resolve().parent
    files = {n: (here / n).read_bytes().replace(b'\r\n', b'\n') for n in ('timing.py', 'HANDOFF.md')}
    sha = lambda b: hashlib.sha256(b).hexdigest()
    files['SHA256SUMS'] = ''.join(sha(b) + '  ' + n + '\n' for n, b in sorted(files.items())).encode()
    out.mkdir()
    path = out / 'r3hd-menu-retained.zip'
    with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED) as z:
        for n, b in sorted(files.items()):
            entry = zipfile.ZipInfo(n, (1980, 1, 1, 0, 0, 0))
            entry.create_system = 3; entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, b, compresslevel=9)
    Path(str(path) + '.sha256').write_text(sha(path.read_bytes()) + '  ' + path.name + '\n', encoding='ascii')
    print(path, path.stat().st_size, sha(path.read_bytes()))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--out', required=True, type=Path)
    build(p.parse_args().out)
