"""M40 (D-077, E-201): AddressSanitizer checks of host code, outside the game process.

  host            builds the self-contained host tests (the patch headers of M18 ... M33 with their test drivers)
                  with clang-cl /fsanitize=address and runs them; each must pass and print no ASan report.
  xma [--iterations N] [--seeds a,b] [--mutate p,q]
                  builds the SDK's FFmpeg (its own source lists) and tools/m40_asan/xma_fuzz.c with ASan, cuts a
                  frame corpus from the game's Stream.h00 (private/work/m40, game-derived) and runs the harness for
                  every mutate share x seed; each run must end with exit 0, an XMA_FUZZ line and decoded frames.
                  A positive control first: the harness's planted one-byte heap overflow must be reported.
  all             both.
Starts no game executable and needs no window. Output: private/work/m40/asan (logs, binaries, corpus).
Last line: M40_ASAN_CHECK PASS|FAIL ..."""
import argparse
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, 'private', 'work', 'm40', 'asan')
HOST_TESTS = ['m18_revisit_test', 'm20_save_commit_test', 'm21_host_test', 'm23_water_test', 'm23_haptics_test',
              'm26_texture_orient_test', 'm33_mod_overlay_test']
SDK_THIRDPARTY = os.path.join(ROOT, 'external', 'rexglue-sdk', 'thirdparty')


def devenv(command, log):
    with open(log, 'w', encoding='utf-8', errors='replace') as f:
        # One command string: a list would have its quotes backslash-escaped, which cmd keeps literally.
        return subprocess.call('cmd /c tools\\devenv.bat ' + command, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)


def asan_env():
    env = dict(os.environ)
    dirs = sorted(glob.glob(r'C:\Program Files\LLVM\lib\clang\*\lib\windows'))
    if dirs:
        env['PATH'] = dirs[-1] + os.pathsep + env.get('PATH', '')
    return env


def run(exe, args, log):
    with open(log, 'w', encoding='utf-8', errors='replace') as f:
        code = subprocess.call([exe] + args, cwd=WORK, stdout=f, stderr=subprocess.STDOUT, env=asan_env())
    text = open(log, encoding='utf-8', errors='replace').read()
    return code, text


def check_host():
    os.makedirs(WORK, exist_ok=True)
    ok = 0
    for t in HOST_TESTS:
        exe = os.path.join(WORK, t + '_asan.exe')
        rel = os.path.relpath(WORK, ROOT)  # relative: no quoting of a trailing backslash for cmd
        cmd = (f'clang-cl /nologo /std:c++20 /EHsc /O1 /Zi /MD /fsanitize=address /w /Itools '
               f'/Iexternal\\rexglue-sdk\\include tools\\{t}.cpp /Fe{rel}\\{t}_asan.exe /Fo{rel}\\ '
               f'/link /incremental:no')
        if devenv(cmd, os.path.join(WORK, t + '_build.log')) != 0:
            print(f'M40_ASAN host {t} BUILD_FAIL')
            continue
        code, text = run(exe, [], os.path.join(WORK, t + '_run.log'))
        report = 'AddressSanitizer' in text
        last = text.strip().splitlines()[-1] if text.strip() else ''
        good = code == 0 and not report
        ok += good
        print(f'M40_ASAN host {t} {"PASS" if good else "FAIL"} exit={code} asan_report={int(report)} | {last[:100]}')
    return ok, len(HOST_TESTS)


def ffmpeg_section():
    text = open(os.path.join(SDK_THIRDPARTY, 'CMakeLists.txt'), encoding='utf-8').read()
    start = text.index('# FFmpeg - Audio/video codec library')
    end = text.index('FOLDER "FFmpeg")', start) + len('FOLDER "FFmpeg")')
    section = text[start:end].replace('${CMAKE_CURRENT_SOURCE_DIR}', SDK_THIRDPARTY.replace('\\', '/'))
    path = os.path.join(WORK, 'ffmpeg.cmake')
    with open(path, 'wb') as f:
        f.write(section.encode('utf-8'))
    return path


def check_xma(iterations, seeds, mutates):
    os.makedirs(WORK, exist_ok=True)
    game = os.environ.get('R3HD_GAME_DIR') or os.path.join(ROOT, 'private', 'extracted', '5841123F')
    source = os.path.join(game, 'GAMEDATAbin', 'WORLD', 'SOUND', 'Stream.h00')
    corpus = os.path.join(WORK, 'corpus_h00.bin')
    if not os.path.exists(corpus):
        if not os.path.exists(source):
            print(f'M40_ASAN xma NO_GAME_DATA {source}')
            return 0, 1
        subprocess.check_call([sys.executable, '-I', os.path.join(ROOT, 'tools', 'm40_xma_frames.py'), source,
                               corpus])
    build = os.path.join(WORK, 'ffbuild')
    cfg = (f'cmake -S tools\\m40_asan -B "{build}" -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo '
           f'-DCMAKE_C_COMPILER=clang -DFFMPEG_CMAKE="{ffmpeg_section()}"')
    if devenv(cfg, os.path.join(WORK, 'ff_configure.log')) != 0 or \
            devenv(f'cmake --build "{build}" -j 12', os.path.join(WORK, 'ff_build.log')) != 0:
        print('M40_ASAN xma BUILD_FAIL (see ff_configure.log / ff_build.log)')
        return 0, 1
    exe = os.path.join(build, 'xma_fuzz.exe')
    code, text = run(exe, [corpus, '1', '1', '0', 'control'], os.path.join(WORK, 'xma_control.log'))
    fired = code != 0 and 'heap-buffer-overflow' in text
    print(f'M40_ASAN xma control {"PASS" if fired else "FAIL"} exit={code} (ASan must report the planted overflow)')
    ok, total = int(fired), 1
    for m in mutates:
        for s in seeds:
            total += 1
            code, text = run(exe, [corpus, str(iterations), str(s), str(m)],
                             os.path.join(WORK, f'xma_m{m}_s{s}.log'))
            line = re.search(r'XMA_FUZZ .*', text)
            dec = re.search(r'decoded=(\d+)', text)
            report = 'AddressSanitizer' in text
            good = code == 0 and line is not None and not report and dec is not None and int(dec.group(1)) > 0
            ok += good
            print(f'M40_ASAN xma mutate={m} seed={s} {"PASS" if good else "FAIL"} exit={code} '
                  f'asan_report={int(report)} | {line.group(0) if line else "no XMA_FUZZ line"}')
    return ok, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('what', choices=['host', 'xma', 'all'])
    ap.add_argument('--iterations', type=int, default=3000)
    ap.add_argument('--seeds', default='1,2')
    ap.add_argument('--mutate', default='0,20,60')
    a = ap.parse_args()
    results = []
    if a.what in ('host', 'all'):
        results.append(('host',) + check_host())
    if a.what in ('xma', 'all'):
        results.append(('xma',) + check_xma(a.iterations, [int(x) for x in a.seeds.split(',')],
                                            [int(x) for x in a.mutate.split(',')]))
    good = all(ok == n for _, ok, n in results)
    print('M40_ASAN_CHECK ' + ('PASS' if good else 'FAIL') + ' ' + ' '.join(f'{k}={ok}/{n}' for k, ok, n in results))
    return 0 if good else 1


if __name__ == '__main__':
    sys.exit(main())
