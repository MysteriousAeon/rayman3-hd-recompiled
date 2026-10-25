#!/usr/bin/env python3
"""Address-space breakdown of a running hidden game process, from outside (M12 memory investigation).

    python tools/m12_mem_map.py RUN [--label NAME] [--top 25] [--no-resident]

Reads private/work/m6_runs/RUN/process.json for the pid, walks the process's address space with VirtualQueryEx
and writes private/work/m6_runs/RUN/mem_map_<label>.json; prints a short table. Read-only: no window, no input,
no guest or host memory contents are read (only region metadata, working-set attributes and image names).

What the figures mean:
  private commit  MEM_PRIVATE + MEM_COMMIT. This is what "private bytes" / PagefileUsage counts.
  mapped commit   MEM_MAPPED + MEM_COMMIT: views of sections. Pagefile-backed sections (the guest address space
                  is one) are charged to the system commit limit when their pages are committed, but not to the
                  process's private bytes; the same section page can appear in several views.
  image           MEM_IMAGE: executables and DLLs.
  reserve         address space only, no commit charge.
  resident        pages currently in the working set (QueryWorkingSetEx), per region.
Allocations are grouped by AllocationBase (one VirtualAlloc / MapViewOfFile / image each).
"""
import argparse
import ctypes
import json
import re
import sys
from collections import defaultdict
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

MEM_COMMIT, MEM_RESERVE, MEM_FREE = 0x1000, 0x2000, 0x10000
MEM_PRIVATE, MEM_MAPPED, MEM_IMAGE = 0x20000, 0x40000, 0x1000000
PAGE = 4096
KINDS = {MEM_PRIVATE: "private", MEM_MAPPED: "mapped", MEM_IMAGE: "image"}


class Mbi(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wintypes.DWORD), ("PartitionId", wintypes.WORD),
                ("RegionSize", ctypes.c_ulonglong), ("State", wintypes.DWORD), ("Protect", wintypes.DWORD),
                ("Type", wintypes.DWORD)]


class WsEx(ctypes.Structure):
    _fields_ = [("VirtualAddress", ctypes.c_ulonglong), ("Attributes", ctypes.c_ulonglong)]


k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_ulonglong, ctypes.POINTER(Mbi), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
psapi.QueryWorkingSetEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
psapi.GetMappedFileNameW.argtypes = [wintypes.HANDLE, ctypes.c_ulonglong, wintypes.LPWSTR, wintypes.DWORD]


def resident_pages(handle, base: int, size: int) -> tuple:
    """(resident, resident and shareable) page counts of a committed range."""
    resident = shared = 0
    step = 16384
    for start in range(0, size // PAGE, step):
        count = min(step, size // PAGE - start)
        block = (WsEx * count)()
        for i in range(count):
            block[i].VirtualAddress = base + (start + i) * PAGE
        if not psapi.QueryWorkingSetEx(handle, block, ctypes.sizeof(block)):
            continue
        for i in range(count):
            attributes = block[i].Attributes
            if attributes & 1:
                resident += 1
                if attributes & 0x8000:  # Shared
                    shared += 1
    return resident, shared


def size_class(size: int) -> str:
    for limit, name in ((1 << 16, "<64K"), (1 << 20, "64K..1M"), (1 << 24, "1M..16M"), (1 << 26, "16M..64M"),
                        (1 << 28, "64M..256M")):
        if size < limit:
            return name
    return ">=256M"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--label", default="")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--no-resident", action="store_true")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", a.run) or not re.fullmatch(r"[A-Za-z0-9_-]*", a.label):
        ap.error("invalid arguments")
    run_dir = ROOT / "private" / "work" / "m6_runs" / a.run
    pid = int(json.loads((run_dir / "process.json").read_text(encoding="utf-8-sig"))["pid"])
    handle = k32.OpenProcess(0x0400 | 0x0010, False, pid)  # QUERY_INFORMATION | VM_READ (names, working set)
    if not handle:
        print("cannot open process", file=sys.stderr)
        return 2
    handle = wintypes.HANDLE(handle)

    allocations = {}
    totals = defaultdict(int)
    address, mbi = 0x10000, Mbi()
    try:
        while k32.VirtualQueryEx(handle, address, ctypes.byref(mbi), ctypes.sizeof(mbi)):
            size = mbi.RegionSize
            if mbi.State != MEM_FREE:
                kind = KINDS.get(mbi.Type, "other")
                entry = allocations.setdefault(mbi.AllocationBase, {
                    "base": mbi.AllocationBase, "kind": kind, "commit": 0, "reserve": 0, "resident": 0,
                    "resident_shared": 0, "regions": 0, "writable": 0, "executable": 0, "guard_or_noaccess": 0})
                entry["regions"] += 1
                if mbi.State == MEM_COMMIT:
                    entry["commit"] += size
                    totals[kind + "_commit"] += size
                    protect = mbi.Protect & 0xFF
                    if protect in (0x04, 0x08, 0x40, 0x80):
                        entry["writable"] += size
                    if protect in (0x10, 0x20, 0x40, 0x80):
                        entry["executable"] += size
                    if protect == 0x01 or mbi.Protect & 0x100:
                        entry["guard_or_noaccess"] += size
                    elif not a.no_resident:
                        pages, shared = resident_pages(handle, mbi.BaseAddress, size)
                        entry["resident"] += pages * PAGE
                        entry["resident_shared"] += shared * PAGE
                        totals[kind + "_resident"] += pages * PAGE
                else:
                    entry["reserve"] += size
                    totals[kind + "_reserve"] += size
            address = mbi.BaseAddress + size
            if address >= 0x7FFFFFFF0000:
                break
        name = ctypes.create_unicode_buffer(1024)
        for entry in allocations.values():
            if entry["kind"] in ("image", "mapped"):
                if psapi.GetMappedFileNameW(handle, entry["base"], name, 1024):
                    entry["file"] = name.value.rsplit("\\", 1)[-1]
    finally:
        k32.CloseHandle(handle)

    classes = defaultdict(lambda: {"count": 0, "commit": 0, "reserve": 0, "resident": 0})
    for entry in allocations.values():
        key = f'{entry["kind"]} {size_class(entry["commit"] + entry["reserve"])}'
        bucket = classes[key]
        bucket["count"] += 1
        for field in ("commit", "reserve", "resident"):
            bucket[field] += entry[field]
    images = sorted((e for e in allocations.values() if e["kind"] == "image"), key=lambda e: -e["commit"])
    top = sorted((e for e in allocations.values() if e["kind"] != "image"),
                 key=lambda e: -(e["commit"] + e["reserve"]))[:a.top]
    for entry in top:
        entry["base"] = f'{entry["base"]:012X}'
    result = {
        "run": a.run, "pid": pid, "label": a.label or None,
        "local": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "totals": dict(totals), "allocation_count": len(allocations),
        "size_classes": dict(sorted(classes.items())),
        "images": [{"file": e.get("file"), "commit": e["commit"], "resident": e["resident"]} for e in images[:20]],
        "image_count": len(images),
        "largest_allocations": top,
    }
    out = run_dir / f"mem_map_{a.label or datetime.now().strftime('%H%M%S')}.json"
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")

    def mb(value):
        return f"{value / 1048576:9.1f}"
    print(f"pid {pid}  {len(allocations)} allocations  -> {out}")
    for kind in ("private", "mapped", "image"):
        print(f"{kind:8} commit {mb(totals[kind + '_commit'])} MB  reserve {mb(totals[kind + '_reserve'])} MB  "
              f"resident {mb(totals[kind + '_resident'])} MB")
    print("class                 count    commit MB  reserve MB resident MB")
    for key, bucket in sorted(classes.items()):
        print(f"{key:20} {bucket['count']:6} {mb(bucket['commit'])} {mb(bucket['reserve'])} {mb(bucket['resident'])}")
    print("largest non-image allocations (base, kind, commit, reserve, resident MB, file)")
    for entry in top:
        print(f"  {entry['base']} {entry['kind']:7} {mb(entry['commit'])} {mb(entry['reserve'])} "
              f"{mb(entry['resident'])} {entry.get('file', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
