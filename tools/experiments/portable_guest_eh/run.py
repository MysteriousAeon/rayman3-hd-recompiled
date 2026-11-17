"""Build/run only the synthetic probe; never imports project runtime tooling."""
import argparse
import json
from pathlib import Path
import platform
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default='clang++')
    parser.add_argument('--out', type=Path, default=Path('private/work/portable_guest_eh'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    source = Path(__file__).with_name('prototype.cpp').resolve()
    results = {'platform': platform.platform(), 'compiler': subprocess.check_output(
        [args.cxx, '--version'], text=True), 'runs': []}
    for optimization in ('-O0', '-O2'):
        exe = (args.out / ('probe_' + optimization[1:] +
                         ('.exe' if platform.system() == 'Windows' else ''))).resolve()
        command = [args.cxx, '-std=c++20', optimization, '-Wall', '-Wextra', '-Werror',
                   '-fexceptions', '-fno-fast-math', str(source), '-o', str(exe)]
        if platform.system() != 'Windows':
            command.append('-pthread')
        subprocess.run(command, check=True, capture_output=True, text=True)
        for repeat in range(20):
            run = subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=10)
            assert run.stdout.startswith('PORTABLE_GUEST_EH PASS checks='), run.stdout
            results['runs'].append({'optimization': optimization, 'repeat': repeat,
                                    'result': run.stdout.strip()})
    (args.out / 'results.json').write_bytes((json.dumps(results, indent=2) + '\n').encode())
    print(f"PORTABLE_GUEST_EH_MATRIX PASS runs={len(results['runs'])}")
    print(results['runs'][0]['result'])


if __name__ == '__main__':
    main()
