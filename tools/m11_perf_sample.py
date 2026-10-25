#!/usr/bin/env python3
"""Sample the resource use of a hidden run from outside the process (M11 performance baseline).

    python tools/m11_perf_sample.py RUN [--interval 1.0] [--no-gpu]

Waits for private/work/m6_runs/RUN/process.json (written by run_milestone6.ps1), then samples that process until
it ends and writes perf_samples.json next to the run's log. Read-only: process times, memory counters, handle and
thread counts, per-thread CPU time (every fifth sample), I/O byte counters, and (unless --no-gpu) the Windows per-process GPU performance counters through
one `typeperf` child. It opens no window, sends no input and reads no guest memory.

CPU is reported in "percent of one logical processor" (100 = one core busy); divide by `logical_processors` for
the share of the whole machine. GPU engine utilisation comes from "\\GPU Engine(pid_N_*)\\Utilization Percentage"
(summed per engine type) and GPU memory from "\\GPU Process Memory(pid_N_*)"; these are WDDM scheduler counters,
good for order of magnitude, not a substitute for a vendor profiler.
"""
import argparse
import csv
import ctypes
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.OpenThread.restype = wintypes.HANDLE
k32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
for fn in (k32.GetProcessTimes, k32.GetExitCodeProcess, k32.GetProcessHandleCount, k32.GetProcessIoCounters,
           k32.CloseHandle, k32.Thread32First, k32.Thread32Next, psapi.GetProcessMemoryInfo):
    fn.argtypes = None


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]


class ThreadEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG),
                ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]


def filetime(ft) -> float:
    return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7


def thread_ids(pid: int) -> list:
    snap = k32.CreateToolhelp32Snapshot(0x4, 0)
    if not snap or snap == wintypes.HANDLE(-1).value:
        return []
    entry = ThreadEntry()
    entry.dwSize = ctypes.sizeof(entry)
    ids = []
    ok = k32.Thread32First(wintypes.HANDLE(snap), ctypes.byref(entry))
    while ok:
        if entry.th32OwnerProcessID == pid:
            ids.append(entry.th32ThreadID)
        ok = k32.Thread32Next(wintypes.HANDLE(snap), ctypes.byref(entry))
    k32.CloseHandle(wintypes.HANDLE(snap))
    return ids


def thread_cpu(ids: list) -> dict:
    """Cumulative CPU seconds per thread id (the ids match the [tNNN] tags of the runtime log)."""
    out = {}
    for tid in ids:
        handle = k32.OpenThread(0x0800, False, tid)  # THREAD_QUERY_LIMITED_INFORMATION
        if not handle:
            continue
        handle = wintypes.HANDLE(handle)
        creation, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if k32.GetThreadTimes(handle, ctypes.byref(creation), ctypes.byref(exited), ctypes.byref(kernel),
                              ctypes.byref(user)):
            out[str(tid)] = round(filetime(kernel) + filetime(user), 4)
        k32.CloseHandle(handle)
    return out


def read_gpu(path: Path, pid: int) -> dict:
    """typeperf CSV -> {local 'HH:MM:SS' second: {metric: value}}; engine utilisation summed per engine type."""
    out = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="mbcs", errors="replace") as stream:
        rows = list(csv.reader(stream))
    if len(rows) < 2:
        return out
    header = rows[0]
    kinds = []
    for name in header[1:]:
        low = name.lower()
        m = re.search(r"engtype_([a-z0-9 ]+)\)", low)
        if "gpu engine" in low and m:
            kinds.append("gpu_util_" + m.group(1).strip().replace(" ", "_"))
        elif "dedicated usage" in low:
            kinds.append("gpu_dedicated_bytes")
        elif "shared usage" in low:
            kinds.append("gpu_shared_bytes")
        else:
            kinds.append(None)
    for row in rows[1:]:
        if len(row) != len(header):
            continue
        try:
            stamp = datetime.strptime(row[0], "%m/%d/%Y %H:%M:%S.%f")
        except ValueError:
            continue
        values = {}
        for kind, cell in zip(kinds, row[1:]):
            if kind is None:
                continue
            try:
                values[kind] = values.get(kind, 0.0) + float(cell)
            except ValueError:
                pass
        out[stamp.strftime("%H:%M:%S")] = values
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--wait", type=float, default=120.0, help="seconds to wait for the run to start")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.run) or not 0.2 <= a.interval <= 10:
        ap.error("invalid arguments")
    run_dir = ROOT / "private" / "work" / "m6_runs" / a.run
    info_path = run_dir / "process.json"
    end = time.monotonic() + a.wait
    while not info_path.exists():
        if time.monotonic() > end:
            print("run did not start", file=sys.stderr)
            return 2
        time.sleep(0.2)
    time.sleep(0.2)
    pid = int(json.loads(info_path.read_text(encoding="utf-8-sig"))["pid"])
    handle = k32.OpenProcess(0x1000 | 0x100000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
    if not handle:
        print("cannot open process", file=sys.stderr)
        return 2
    handle = wintypes.HANDLE(handle)

    gpu_proc, gpu_csv = None, None
    samples = []
    last_cpu = last_t = None
    started = time.monotonic()
    try:
        while True:
            code = wintypes.DWORD()
            k32.GetExitCodeProcess(handle, ctypes.byref(code))
            if code.value != 259:
                break
            now = time.monotonic()
            # The GPU engine instances exist only once the process has created its device.
            if not a.no_gpu and gpu_proc is None and now - started >= 4.0:
                gpu_csv = Path(tempfile.mkdtemp(prefix="m11gpu_")) / "gpu.csv"
                counters = [rf"\GPU Engine(pid_{pid}_*)\Utilization Percentage",
                            rf"\GPU Process Memory(pid_{pid}_*)\Dedicated Usage",
                            rf"\GPU Process Memory(pid_{pid}_*)\Shared Usage"]
                gpu_proc = subprocess.Popen(["typeperf", *counters, "-si", "1", "-f", "CSV", "-y", "-o", str(gpu_csv)],
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            creationflags=0x08000000)  # CREATE_NO_WINDOW
            creation, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            k32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exited), ctypes.byref(kernel),
                                ctypes.byref(user))
            cpu = filetime(kernel) + filetime(user)
            mem = MemoryCounters()
            mem.cb = ctypes.sizeof(mem)
            psapi.GetProcessMemoryInfo(handle, ctypes.byref(mem), mem.cb)
            io = IoCounters()
            k32.GetProcessIoCounters(handle, ctypes.byref(io))
            ids = thread_ids(pid)
            handles = wintypes.DWORD()
            k32.GetProcessHandleCount(handle, ctypes.byref(handles))
            sample = {
                "t": round(now - started, 3),
                "local": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "cpu_seconds": round(cpu, 4),
                "cpu_kernel_seconds": round(filetime(kernel), 4),
                "cpu_percent_one_core": None if last_cpu is None else round(100 * (cpu - last_cpu) / (now - last_t), 2),
                "working_set": mem.WorkingSetSize, "peak_working_set": mem.PeakWorkingSetSize,
                "private_bytes": mem.PrivateUsage, "peak_commit": mem.PeakPagefileUsage,
                "page_faults": mem.PageFaultCount,
                "read_bytes": io.ReadBytes, "write_bytes": io.WriteBytes,
                "handles": handles.value, "threads": len(ids),
            }
            if len(samples) % 5 == 0:
                sample["thread_cpu_seconds"] = thread_cpu(ids)
            samples.append(sample)
            last_cpu, last_t = cpu, now
            time.sleep(max(0.0, a.interval - (time.monotonic() - now)))
    finally:
        k32.CloseHandle(handle)
        if gpu_proc is not None:
            gpu_proc.terminate()
            try:
                gpu_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                gpu_proc.kill()
    gpu = read_gpu(gpu_csv, pid) if gpu_csv else {}
    matched = 0
    for sample in samples:
        values = gpu.get(sample["local"][11:19])
        if values:
            sample.update({key: round(value, 3) for key, value in values.items()})
            matched += 1
    if gpu_csv:
        try:
            gpu_csv.unlink()
            gpu_csv.parent.rmdir()
        except OSError:
            pass
    result = {
        "run": a.run, "pid": pid, "interval_seconds": a.interval,
        "logical_processors": os.cpu_count(),
        "gpu_counter_source": None if a.no_gpu else "typeperf: GPU Engine / GPU Process Memory (per process)",
        "gpu_samples_matched": matched,
        "samples": samples,
    }
    (run_dir / "perf_samples.json").write_text(json.dumps(result) + "\n", encoding="utf-8")
    print(f"{len(samples)} samples, {matched} with GPU counters -> {run_dir / 'perf_samples.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
