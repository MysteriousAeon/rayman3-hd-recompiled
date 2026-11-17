#!/usr/bin/env python3
"""D-220: mechanical check of one run's host presentation mode from its runtime log.

usage: r3hd_display_vsync_check.py RUN_DIR|runtime.log --expect on|off [--json OUT]

Reads the `R3HD display_vsync=` swap-chain lines and the `R3HD present_stats` summaries (one per 600 presents)
written by the D3D12 presenter patch (tools/r3hd_display_vsync_patch.py), and the `M3 host_swapchain_create`
line for the UI thread id.

PASS needs, for every swap chain and every summary of the run:
  off: sync_interval 0, Present flags RESTART (+ ALLOW_TEARING when the swap chain allows tearing), no waitable
       object, implicit_vsync 0 (the pinned presentation);
  on:  sync_interval 0 never appears; Present(1, 0); FRAME_LATENCY_WAITABLE_OBJECT set, maximum latency 1 and a
       waitable object; implicit_vsync 1; every summary logged by the UI thread (the swap chain's creating thread)
       and not by the guest-output thread; no failed presents.
Always reported (not judged): Present call and latency wait percentiles, wait timeouts, occluded presents and
the DXGI frame statistics (refreshes per present and the refresh period they imply, where available). For a hidden
(never shown, not composed) test window DXGI updates those counters only sporadically or not at all (E-449): they
are indicative, never a pass criterion.

This establishes what the application requested from DXGI and how the calls behaved. It does not establish
what a display showed: a driver (forced V-Sync, G-Sync/FreeSync) or the compositor may change it.
Final line: DISPLAY_VSYNC_CHECK PASS|FAIL ...; exit 0 / 1 (2 = no usable data).
"""
import argparse
import ctypes
import json
import re
import sys
from pathlib import Path

TID = r"\[t(\d+)\] "
MODE = re.compile(TID + r"R3HD display_vsync=(on|off) swapchain_flags=0x([0-9A-F]+) tearing_supported=(\d) "
                  r"sync_interval=(\d+) present_flags=0x([0-9A-F]+) max_frame_latency=(\d+) latency_hr=([0-9A-F]{8}) "
                  r"waitable=(\d) implicit_vsync=(\d)")
STATS = re.compile(TID + r"R3HD present_stats window=(\d+) n=(\d+) vsync=(on|off) sync_interval=(\d+) "
                   r"flags=0x([0-9A-F]+) call_p50_us=(\d+) call_p95_us=(\d+) call_max_us=(\d+) wait_p50_us=(\d+) "
                   r"wait_p95_us=(\d+) wait_max_us=(\d+) wait_timeouts=(\d+) occluded=(\d+) failed=(\d+) "
                   r"fs_hr=([0-9A-F]{8}) fs_present_count=(\d+) fs_present_refresh=(\d+) fs_sync_refresh=(\d+) "
                   r"fs_sync_qpc=(-?\d+) last_present_count=(\d+)")
CREATE = re.compile(TID + r"M3 host_swapchain_create ")
RESTART, ALLOW_TEARING = 0x4, 0x200
SC_TEARING, SC_WAITABLE = 2048, 64


def qpc_frequency():
    try:
        f = ctypes.c_int64()
        if ctypes.windll.kernel32.QueryPerformanceFrequency(ctypes.byref(f)):
            return f.value
    except (AttributeError, OSError):
        pass
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--expect", choices=("on", "off"), required=True)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    if a.run.is_dir():
        # The log rotates: runtime.N.log are older parts (larger N older), runtime.log is the newest.
        def age(p):
            m = re.fullmatch(r"runtime\.(\d+)\.log", p.name)
            return -int(m.group(1)) if m else 0
        parts = sorted(a.run.glob("runtime*.log"), key=age)
    else:
        parts = [a.run]
    text = "".join(p.read_text(encoding="utf-8", errors="replace") for p in parts)
    modes = [m.groups() for m in MODE.finditer(text)]
    stats = [m.groups() for m in STATS.finditer(text)]
    creators = {m.group(1) for m in CREATE.finditer(text)}
    if not modes:
        print("DISPLAY_VSYNC_CHECK FAIL no swap-chain mode line (unpatched build?)")
        return 2
    fails = []
    for tid, mode, flags, tearing, interval, pflags, latency, hr, waitable, implicit in modes:
        flags, pflags, interval = int(flags, 16), int(pflags, 16), int(interval)
        if mode != a.expect:
            fails.append(f"swap chain mode {mode}")
        if a.expect == "off":
            want = RESTART | (ALLOW_TEARING if flags & SC_TEARING else 0)
            if interval != 0 or pflags != want or flags & SC_WAITABLE or waitable != "0" or implicit != "0":
                fails.append(f"off not pinned: interval={interval} flags=0x{pflags:X} sc=0x{flags:X}")
        else:
            if interval != 1 or pflags != 0:
                fails.append(f"on: Present({interval}, 0x{pflags:X})")
            if not flags & SC_WAITABLE or latency != "1" or waitable != "1" or hr != "00000000":
                fails.append(f"on: latency object sc=0x{flags:X} latency={latency} hr={hr} waitable={waitable}")
            if implicit != "1":
                fails.append("on: implicit V-Sync not reported")
    windows = []
    threads = set()
    for g in stats:
        (tid, window, n, mode, interval, flags, c50, c95, cmax, w50, w95, wmax, timeouts, occluded, failed,
         fs_hr, fs_pc, fs_pr, fs_sr, fs_qpc, last) = g
        threads.add(tid)
        if mode != a.expect:
            fails.append(f"summary {window} mode {mode}")
        if a.expect == "on":
            if interval != "1" or flags != "0":
                fails.append(f"summary {window}: Present({interval}, 0x{flags})")
            if int(failed):
                fails.append(f"summary {window}: {failed} failed presents")
        elif interval != "0":
            fails.append(f"summary {window}: sync interval {interval}")
        windows.append({"tid": tid, "window": int(window), "call_p50_us": int(c50), "call_p95_us": int(c95),
                        "call_max_us": int(cmax), "wait_p50_us": int(w50), "wait_p95_us": int(w95),
                        "wait_max_us": int(wmax), "wait_timeouts": int(timeouts), "occluded": int(occluded),
                        "failed": int(failed), "fs_hr": fs_hr, "fs_present_count": int(fs_pc),
                        "fs_present_refresh": int(fs_pr), "fs_sync_refresh": int(fs_sr), "fs_sync_qpc": int(fs_qpc),
                        "last_present_count": int(last)})
    if a.expect == "on" and threads - creators:
        fails.append(f"presents from threads {sorted(threads - creators)} other than the UI thread {sorted(creators)}")
    # DXGI frame statistics between consecutive summaries (only where both are valid and increasing).
    freq = qpc_frequency()
    fs = []
    for p, q in zip(windows, windows[1:]):
        if p["fs_hr"] != "00000000" or q["fs_hr"] != "00000000":
            continue
        if not (p["fs_present_count"] and p["fs_sync_refresh"] and p["fs_sync_qpc"]):
            continue  # counters not yet populated (a window that is not composed may never update them)
        dp, dr = q["fs_present_count"] - p["fs_present_count"], q["fs_present_refresh"] - p["fs_present_refresh"]
        ds, dq = q["fs_sync_refresh"] - p["fs_sync_refresh"], q["fs_sync_qpc"] - p["fs_sync_qpc"]
        if dp > 0 and ds > 0 and dq > 0:
            fs.append({"presents": dp, "refreshes_per_present": round(dr / dp, 3),
                       "refresh_hz": round(ds * freq / dq, 2) if freq else None})
    def med(key, rows):
        v = sorted(r[key] for r in rows if r[key] is not None)
        return v[len(v) // 2] if v else None
    summary = {
        "run": str(a.run), "expect": a.expect, "swap_chains": len(modes), "summaries": len(windows),
        "present_threads": sorted(threads), "ui_threads": sorted(creators),
        "call_p50_us_median": med("call_p50_us", windows), "call_p95_us_median": med("call_p95_us", windows),
        "wait_p50_us_median": med("wait_p50_us", windows), "wait_p95_us_median": med("wait_p95_us", windows),
        "wait_timeouts": sum(w["wait_timeouts"] for w in windows), "occluded": sum(w["occluded"] for w in windows),
        "failed": sum(w["failed"] for w in windows),
        "frame_stats_hr": sorted({w["fs_hr"] for w in windows}), "frame_stats_windows": len(fs),
        "refreshes_per_present_median": med("refreshes_per_present", fs), "refresh_hz_median": med("refresh_hz", fs),
        "fails": fails,
    }
    if not windows:
        fails.append("no present summary (fewer than 600 presents)")
    if a.json:
        a.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    keys = ("swap_chains", "summaries", "call_p50_us_median", "call_p95_us_median", "wait_p50_us_median",
            "wait_p95_us_median", "wait_timeouts", "occluded", "failed", "frame_stats_hr",
            "refreshes_per_present_median", "refresh_hz_median")
    print(f"DISPLAY_VSYNC_CHECK {'PASS' if not fails else 'FAIL'} expect={a.expect} "
          + " ".join(f"{k}={summary[k]}" for k in keys) + (f" fails={fails}" if fails else ""))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
