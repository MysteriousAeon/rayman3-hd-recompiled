"""M45 regression (D-083): the DXBC container hash is the DXC-derived one and AMD's DXBCChecksum is gone.

Static checks over the patched SDK working tree (run after the patch chain of build_milestone8.bat), then builds
tools/m45_dxbc_hash_test.cpp with the pinned clang++ and runs it (known answers recorded from the retired AMD routine,
FXC-written hashes of SDK shaders, invariance). With --build-tree, the generated Release build of the SDK must not
compile or link DXBCChecksum.cpp into rexgpu-xenos (run after the SDK build). Prints M45_REGRESSION PASS / FAIL.
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SDK = ROOT / 'external' / 'rexglue-sdk'
failures = 0
checks = 0


def check(name, ok):
    global failures, checks
    checks += 1
    failures += not ok
    print(('ok   ' if ok else 'FAIL ') + name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--build-tree', action='store_true', help='check the generated SDK Release build files')
    args = ap.parse_args()

    check('AMD sources removed from the SDK working tree',
          not (SDK / 'thirdparty/dxbc/DXBCChecksum.cpp').exists() and not (SDK / 'thirdparty/dxbc/DXBCChecksum.h').exists())
    installed = SDK / 'include/rex/m45_dxbc_hash.h'
    check('hash header installed unchanged', installed.is_file()
          and installed.read_bytes() == (ROOT / 'tools/m45_dxbc_hash.h').read_bytes())
    stale = []
    for top in ('src', 'include', 'CMakeLists.txt', 'cmake'):
        base = SDK / top
        files = [base] if base.is_file() else (p for p in base.rglob('*') if p.is_file()) if base.exists() else []
        for p in files:
            if p.suffix.lower() not in ('.c', '.cc', '.cpp', '.h', '.hpp', '.inl', '.txt', '.cmake'):
                continue
            t = p.read_bytes()
            if b'CalculateDXBCChecksum' in t or b'thirdparty/dxbc' in t or b'MD5_CTX' in t:
                stale.append(str(p.relative_to(SDK)))
    check('no AMD routine, include or MD5 context in SDK sources or CMake (%s)' % (', '.join(stale) or 'none'),
          not stale)
    sites = {'src/graphics/pipeline/shader/dxbc_translator.cpp': 1, 'src/graphics/d3d12/pipeline_cache.cpp': 1,
             'src/graphics/d3d12/render_target_cache.cpp': 2}
    check('four call sites use m45dxbc::ContainerHash',
          all((SDK / f).read_bytes().count(b'm45dxbc::ContainerHash(') == n for f, n in sites.items()))
    header = (ROOT / 'tools/m45_dxbc_hash.h').read_text(encoding='utf-8')
    check('header keeps the Microsoft notice, the NCSA reference and the RSA MD5 attribution',
          'Copyright (C) Microsoft Corporation. All rights reserved.' in header
          and 'University of Illinois Open Source' in header and 'RSA Data Security, Inc. MD5 Message-Digest Algorithm' in header)
    lic = (ROOT / 'tools/installer/DirectXShaderCompiler-LICENSE.txt').read_text(encoding='utf-8')
    check('licence text: NCSA terms and the upstream commit', 'University of Illinois/NCSA' in lic
          and 'Redistributions in binary form must reproduce' in lic and '194bb75bea2becb42810d72a16195089c1908e10' in lic)
    bat = (ROOT / 'tools/build_milestone8.bat').read_text(encoding='utf-8')
    check('build replays the M45 patch after M44 and runs this regression',
          0 < bat.find(r'python tools\m44_runtime_patch.py') < bat.find(r'python tools\m45_runtime_patch.py') and 'm45_regression.py' in bat)

    clang = Path(os.environ.get('R3HD_LLVM_BIN', r'C:\Program Files\LLVM\bin')) / 'clang++.exe'
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / 'm45_dxbc_hash_test.exe'
        build = subprocess.run([str(clang), '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
                                '-I' + str(SDK / 'src/graphics/shaders/bytecode/d3d12_5_1'),
                                str(ROOT / 'tools/m45_dxbc_hash_test.cpp'), '-o', str(exe)],
                               capture_output=True, text=True)
        check('hash test builds (clang++ -Wall -Wextra -Werror)', build.returncode == 0)
        if build.returncode:
            print(build.stderr[-2000:])
        else:
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            print(run.stdout.strip())
            check('hash test passes', run.returncode == 0 and 'M45_HASH_TEST PASS' in run.stdout)
    if args.build_tree:
        ninja = SDK / 'out/build/win-amd64/CMakeFiles/impl-Release.ninja'
        text = ninja.read_text(encoding='utf-8', errors='replace') if ninja.is_file() else ''
        check('SDK Release build: rexgpu-xenos built without DXBCChecksum.cpp',
              'rexgpu-xenos' in text and 'DXBCChecksum' not in text)

    print('M45_REGRESSION %s checks=%d failures=%d' % ('PASS' if not failures else 'FAIL', checks, failures))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
