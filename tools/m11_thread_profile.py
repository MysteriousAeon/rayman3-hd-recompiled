#!/usr/bin/env python3
"""Statistical instruction-pointer profile of the busiest thread of a hidden run (M11).

    python tools/m11_thread_profile.py RUN --after NEEDLE [--delay 20] [--seconds 60] [--interval-ms 20]
                                       [--map MODULE=MAP ...] [--out FILE.json]

Waits until the run's log contains NEEDLE, waits --delay seconds, picks the thread that used the most CPU over
two seconds, then repeatedly suspends it for a few microseconds, reads its instruction pointer and resumes it.
Nothing is written to the process: no guest memory access, no breakpoints, no window or input interaction.
Samples are attributed to module + nearest map symbol. Generated game functions appear under their guest
address name (`sub_82xxxxxx`), so the output is addresses, names of host functions and counts only.
"""
import argparse
import bisect
import collections
import ctypes
import json
import re
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from m11_symbolize import load_map  # noqa: E402

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenThread.restype = wintypes.HANDLE
k32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
k32.SuspendThread.argtypes = [wintypes.HANDLE]
k32.ResumeThread.argtypes = [wintypes.HANDLE]
k32.GetThreadContext.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
k32.GetThreadTimes.argtypes = [wintypes.HANDLE] + [ctypes.c_void_p] * 4
k32.CloseHandle.argtypes = [wintypes.HANDLE]


class ThreadEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG),
                ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]


class ModuleEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("GlblcntUsage", wintypes.DWORD), ("ProccntUsage", wintypes.DWORD),
                ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", wintypes.DWORD), ("hModule", wintypes.HMODULE),
                ("szModule", wintypes.WCHAR * 256), ("szExePath", wintypes.WCHAR * 260)]


def snapshot(flags, pid, entry_type, first, following):
    snap = k32.CreateToolhelp32Snapshot(flags, pid)
    out = []
    if not snap or snap == wintypes.HANDLE(-1).value:
        return out
    entry = entry_type()
    entry.dwSize = ctypes.sizeof(entry)
    ok = first(wintypes.HANDLE(snap), ctypes.byref(entry))
    while ok:
        out.append(entry_type.from_buffer_copy(entry))
        ok = following(wintypes.HANDLE(snap), ctypes.byref(entry))
    k32.CloseHandle(wintypes.HANDLE(snap))
    return out


def cpu_seconds(handle):
    times = [wintypes.FILETIME() for _ in range(4)]
    k32.GetThreadTimes(handle, *[ctypes.byref(t) for t in times])
    return sum(((t.dwHighDateTime << 32) | t.dwLowDateTime) / 1e7 for t in times[2:])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--after", required=True)
    ap.add_argument("--delay", type=float, default=20.0)
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--interval-ms", type=float, default=20.0)
    ap.add_argument("--map", action="append", default=[])
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.run) or not 1 <= a.seconds <= 300 or not 5 <= a.interval_ms <= 1000:
        ap.error("invalid arguments")
    run_dir = ROOT / "private" / "work" / "m6_runs" / a.run
    end = time.monotonic() + 600
    while True:
        if time.monotonic() > end:
            print("needle not seen", file=sys.stderr)
            return 2
        logs = sorted(run_dir.glob("runtime*.log")) if run_dir.exists() else []
        if any(a.after in p.read_text(errors="replace") for p in logs):
            break
        time.sleep(1.0)
    time.sleep(a.delay)
    pid = int(json.loads((run_dir / "process.json").read_text(encoding="utf-8-sig"))["pid"])

    maps = {}
    for spec in a.map:
        name, path = spec.split("=", 1)
        maps[name.lower()] = load_map(path)
    modules = sorted((m.modBaseAddr, m.modBaseSize, m.szModule) for m in
                     snapshot(0x18, pid, ModuleEntry, k32.Module32FirstW, k32.Module32NextW))
    bases = [m[0] for m in modules]

    handles = {}
    for t in snapshot(0x4, 0, ThreadEntry, k32.Thread32First, k32.Thread32Next):
        if t.th32OwnerProcessID == pid:
            h = k32.OpenThread(0x0002 | 0x0008 | 0x0040 | 0x0800, False, t.th32ThreadID)
            if h:
                handles[t.th32ThreadID] = wintypes.HANDLE(h)
    before = {tid: cpu_seconds(h) for tid, h in handles.items()}
    time.sleep(2.0)
    used = {tid: cpu_seconds(h) - before[tid] for tid, h in handles.items()}
    tid = max(used, key=used.get)
    target = handles[tid]

    raw = ctypes.create_string_buffer(1232 + 16)
    address = (ctypes.addressof(raw) + 15) & ~15
    flags = ctypes.c_uint32.from_address(address + 0x30)
    rip = ctypes.c_uint64.from_address(address + 0xF8)
    counts = collections.Counter()
    by_module = collections.Counter()
    total = failed = 0
    stop = time.monotonic() + a.seconds
    while time.monotonic() < stop:
        if k32.SuspendThread(target) == 0xFFFFFFFF:
            break
        flags.value = 0x00100001  # CONTEXT_AMD64 | CONTEXT_CONTROL
        ok = k32.GetThreadContext(target, address)
        pc = rip.value
        k32.ResumeThread(target)
        if not ok:
            failed += 1
        else:
            total += 1
            i = bisect.bisect_right(bases, pc) - 1
            if i >= 0 and pc < modules[i][0] + modules[i][1]:
                module = modules[i][2]
                offset = pc - modules[i][0]
                symbol = f"+{offset >> 12:X}xxx"
                if module.lower() in maps:
                    addrs, names = maps[module.lower()]
                    j = bisect.bisect_right(addrs, offset) - 1
                    if j >= 0:
                        symbol = names[j]
                by_module[module] += 1
                counts[(module, symbol)] += 1
            else:
                by_module["(outside modules)"] += 1
                counts[("(outside modules)", "")] += 1
        time.sleep(a.interval_ms / 1000.0)
    for h in handles.values():
        k32.CloseHandle(h)

    result = {
        "run": a.run, "thread_id": tid, "thread_cpu_percent_one_core_before": round(50 * used[tid], 1),
        "samples": total, "failed": failed, "interval_ms": a.interval_ms,
        "by_module": [{"module": m, "percent": round(100 * n / max(1, total), 1)} for m, n in by_module.most_common()],
        "top": [{"module": m, "symbol": s, "percent": round(100 * n / max(1, total), 2)}
                for (m, s), n in counts.most_common(40)],
    }
    text = json.dumps(result, indent=1) + "\n"
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
    print(f"thread {tid}: {total} samples ({failed} failed), {result['thread_cpu_percent_one_core_before']}% of one core")
    for row in result["by_module"][:8]:
        print(f"  {row['percent']:5.1f}%  {row['module']}")
    for row in result["top"][:25]:
        print(f"  {row['percent']:6.2f}%  {row['module']}  {row['symbol'][:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
