"""Regression for the M8 last-chance crash record (no game process, no dialog)."""
from pathlib import Path
import os
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / 'private/work/rex/out/build/win-amd64-release/m8_crash_test.exe'
if len(sys.argv) > 1:  # a standalone fixture build (host-only A/B before a full replay)
    EXE = Path(sys.argv[1]).resolve()

# crash_test.cpp markers of the two objects that must be captured, as stored in memory
LEVEL1, LEVEL2 = (struct.pack('<Q', v) for v in (0x315645444C483352, 0x325645444C483352))


def dump_memory(data):
    """(base, bytes) of every MemoryListStream (5) and Memory64ListStream (9) range of a minidump."""
    if data[:4] != b'MDMP':
        return []
    count, directory = struct.unpack_from('<II', data, 8)
    ranges = []
    for i in range(count):
        kind, _, rva = struct.unpack_from('<III', data, directory + 12 * i)
        if kind == 5:
            n, = struct.unpack_from('<I', data, rva)
            for k in range(n):
                base, size, at = struct.unpack_from('<QII', data, rva + 4 + 16 * k)
                ranges.append((base, data[at:at + size]))
        elif kind == 9:
            n, at = struct.unpack_from('<QQ', data, rva)
            for k in range(n):
                base, size = struct.unpack_from('<QQ', data, rva + 16 + 16 * k)
                ranges.append((base, data[at:at + size]))
                at += size
    return ranges


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
        check(re.search(r'^register_memory ranges=\d+ level1=\d+ bytes=\d+$', text, re.M) is not None,
              'register memory line recorded')
        for p in work.iterdir():
            p.unlink()

        # D-311: host heap near the faulting thread's registers, two levels, bounded; never a file mapping
        heap = subprocess.run([str(EXE), 'heap'], cwd=work, env=env, timeout=30, capture_output=True, text=True)
        where = dict((k, int(v, 16)) for k, v in re.findall(r'(\w+)=([0-9A-Fa-f]{8,16})', heap.stdout))
        check(heap.returncode & 0xFFFFFFFF == 0xC0000005, f'heap fault exit code {heap.returncode & 0xFFFFFFFF:08X}')
        text = report.read_text() if report.is_file() else ''
        check('access=write target=0000000000000000' in text, 'heap: faulting access recorded')
        check('minidump=r3hd_crash.dmp written=1' in text, 'heap: minidump written')
        found = re.search(r'^register_memory ranges=(\d+) level1=(\d+) bytes=(\d+)$', text, re.M)
        ranges, level1, size = (int(g) for g in found.groups()) if found else (0, 0, 0)
        check(0 < level1 <= 16 and level1 < ranges <= 160, f'heap: range counts {ranges} / {level1}')
        check(0 < size <= 64 * 1024, f'heap: captured bytes {size} within 64 KiB')
        memory = dump_memory(dump.read_bytes()) if dump.is_file() else []
        def at(name):  # the 8 dumped bytes at a printed address, or None when no range covers it
            address = where.get(name)
            for base, data in memory:
                if address is not None and base <= address and address + 8 <= base + len(data):
                    return data[address - base:address - base + 8]
            return None

        check(sorted(where) == ['level1', 'level2', 'level3', 'mapped'], f'heap: fixture addresses {heap.stdout!r}')
        check(at('level1') == LEVEL1, 'heap: object named by a register captured (level 1)')
        check(at('level2') == LEVEL2, 'heap: object it points to captured (level 2)')
        check(at('level3') is None, 'heap: no third level')
        check(at('mapped') is None, 'heap: file-mapping view (guest-memory kind) never captured')
        bases = sorted((base, base + len(data)) for base, data in memory)
        check(all(a[1] <= b[0] for a, b in zip(bases, bases[1:])), 'heap: dump ranges do not overlap')
        check(len(dump.read_bytes()) < 1024 * 1024 if dump.is_file() else False, 'heap: dump stays small')
    print(f'm8 crash report: {checks} checks, {failures} failures: {"FAIL" if failures else "PASS"}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
