"""Deterministic private handoff; project tooling only, no game or SDK inputs."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import zipfile


def build(out):
    if out.exists() or out.is_symlink(): raise ValueError('output exists; preserve it')
    here = Path(__file__).resolve().parent; root = here.parents[2]
    files = {n: (here / n).read_bytes().replace(b'\r\n', b'\n') for n in ('pause.py', 'HANDOFF.md')}
    for n, source in [('cpu.py', 'menu_cpu/cpu.py'), ('review.py', 'menu_cpu/review.py'),
                      ('timing.py', 'menu_timing/timing.py')]:
        files[n] = subprocess.check_output(['git', '-C', str(root), 'show',
            '6bb9fd64467652995190e302d02655e7355719c8:tools/linux/' + source])
    digest = lambda b: hashlib.sha256(b).hexdigest()
    files['SHA256SUMS'] = ''.join(digest(b) + '  ' + n + '\n' for n, b in sorted(files.items())).encode()
    out.mkdir(); path = out / 'r3hd-pause-measure.zip'
    with zipfile.ZipFile(path, 'x', zipfile.ZIP_DEFLATED) as z:
        for n, raw in sorted(files.items()):
            item = zipfile.ZipInfo(n, (1980, 1, 1, 0, 0, 0)); item.create_system = 3
            item.external_attr = 0o100644 << 16; item.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(item, raw, compresslevel=9)
    Path(str(path) + '.sha256').write_text(digest(path.read_bytes()) + '  ' + path.name + '\n', encoding='ascii')
    print(path, path.stat().st_size, digest(path.read_bytes()))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--out', type=Path, required=True)
    build(p.parse_args().out)
