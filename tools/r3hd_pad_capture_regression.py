#!/usr/bin/env python3
"""Compile and test the actual Settings Sony decoder, without opening a device.

Only extracted production declarations plus our independently structured fixtures;
no copy of decoder logic. Native build/output remain private. Physical B8 is a
separate human gate. Run before the padmap private-desktop UI regression.
"""
import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, default=ROOT / 'tools/launcher/r3hd_launcher.cpp',
                    help='optional historical source snapshot for a negative control')
    source = ap.parse_args().source.read_text(encoding='utf-8')
    sample = source[source.index('struct PadSample {'):source.index('\nstruct Ui {')]
    decoder = source[source.index('enum class Sony {'):source.index('// The controllers connected now')]
    out = ROOT / 'private/work/b8_capture/decoder'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'decoder.h').write_bytes((sample + '\n' + decoder).encode('utf-8'))
    exe = out / 'test.exe'
    cmd = (f'tools\\devenv.bat clang-cl /nologo /std:c++17 /EHsc /W4 /MT '
           f'/I"{out}" /Fo"{out / "test.obj"}" /Fe"{exe}" tools\\r3hd_pad_capture_test.cpp')
    result = subprocess.run('cmd /c ' + cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        print(result.stdout, result.stderr)
        return result.returncode
    return subprocess.run([str(exe)], cwd=ROOT).returncode


if __name__ == '__main__':
    raise SystemExit(main())
