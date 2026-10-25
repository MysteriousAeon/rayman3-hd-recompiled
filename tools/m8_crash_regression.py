"""Regression for the M8 last-chance crash record (no game process, no dialog)."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / 'private/work/rex/out/build/win-amd64-release/m8_crash_test.exe'


def main():
    checks = failures = 0

    def check(ok, what):
        nonlocal checks, failures
        checks += 1
        if not ok:
            failures += 1
            print('FAIL', what)

    env = dict(os.environ, R3HD_NONINTRUSIVE='1')  # the reporter must stay silent in hidden mode
    with tempfile.TemporaryDirectory(dir=ROOT / 'private/work') as work:
        work = Path(work)
        ok = subprocess.run([str(EXE), 'ok'], cwd=work, env=env, timeout=30)
        check(ok.returncode == 0, 'normal exit code')
        check(not list(work.iterdir()), 'no files without a fault')

        fault = subprocess.run([str(EXE), 'fault'], cwd=work, env=env, timeout=30)
        check(fault.returncode & 0xFFFFFFFF == 0xC0000005, f'fault exit code {fault.returncode & 0xFFFFFFFF:08X}')
        report = work / 'r3hd_crash.txt'
        dump = work / 'r3hd_crash.dmp'
        check(report.is_file(), 'report written')
        text = report.read_text() if report.is_file() else ''
        check('code=C0000005' in text, 'exception code recorded')
        check('access=write target=0000000000000000' in text, 'faulting access recorded')
        check('m8_crash_test.exe offset=' in text, 'faulting module recorded')
        check('last_entered_function=fixture_function lr=82001234' in text, 'host context callback recorded')
        check('minidump=r3hd_crash.dmp written=1' in text, 'minidump status recorded')
        check(dump.is_file() and dump.read_bytes()[:4] == b'MDMP', 'minidump signature')
        check(sorted(p.name for p in work.iterdir()) == ['r3hd_crash.dmp', 'r3hd_crash.txt'], 'only the two files')
    print(f'm8 crash report: {checks} checks, {failures} failures: {"FAIL" if failures else "PASS"}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
