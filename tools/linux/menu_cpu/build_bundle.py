"""Checked controller + pinned read-only verifier; no game/SDK payload."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import zipfile


def build(out):
    if out.exists() or out.is_symlink(): raise ValueError('output exists; preserve it')
    here = Path(__file__).resolve().parent; root = here.parents[2]
    files = {n: (here / n).read_bytes().replace(b'\r\n', b'\n') for n in ('cpu.py', 'HANDOFF.md')}
    files['timing.py'] = subprocess.check_output(['git', '-C', str(root), 'show',
        '1d5b948b795832943e5d14be2e9d59f794e99ed2:tools/linux/menu_timing/timing.py'])
    sha = lambda b: hashlib.sha256(b).hexdigest()
    files['SHA256SUMS'] = ''.join(sha(b) + '  ' + n + '\n' for n, b in sorted(files.items())).encode()
    out.mkdir(); p = out / 'r3hd-menu-cpu.zip'
    with zipfile.ZipFile(p, 'x', zipfile.ZIP_DEFLATED) as z:
        for n, raw in sorted(files.items()):
            i = zipfile.ZipInfo(n, (1980, 1, 1, 0, 0, 0)); i.create_system = 3
            i.external_attr = 0o100644 << 16; i.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(i, raw, compresslevel=9)
    Path(str(p) + '.sha256').write_text(sha(p.read_bytes()) + '  ' + p.name + '\n', encoding='ascii')
    print(p, p.stat().st_size, sha(p.read_bytes()))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--out', type=Path, required=True)
    build(p.parse_args().out)
