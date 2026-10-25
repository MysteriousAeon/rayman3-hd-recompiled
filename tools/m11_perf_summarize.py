#!/usr/bin/env python3
"""Summarise a sampled hidden run into per-phase resource and pacing figures (M11 performance baseline).

    python tools/m11_perf_summarize.py RUN [RUN ...] [--out reports/milestone11/perf/NAME.json]

Inputs, all in private/work/m6_runs/RUN: perf_samples.json (tools/m11_perf_sample.py), runtime*.log, run.json.
Phases are cut at the first open of each movie (*.bik) and level (*.lvl, without fix / transit) in the log, so a
phase is "from this content's first open to the next one's". Output is metadata only: counts, sizes, times.

Per phase: CPU (percent of one logical processor), working set, private bytes, GPU counters, the `M11 pacing`
windows (600 intervals each) of guest swaps and host presents, and the duration of the file-open burst that
starts the phase (opens less than one second apart), a proxy for its loading time.
"""
import argparse
import json
import re
import statistics
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})\]")
OPEN = re.compile(r"M2 vfs_open path=(\S+) result=([0-9A-F]{8})")
PACING = re.compile(r"M11 pacing series=(\w+) window=(\d+) n=(\d+) mean_us=(\d+) min_us=(\d+) p50_us=(\d+) "
                    r"p95_us=(\d+) p99_us=(\d+) max_us=(\d+) over_20ms=(\d+) over_33ms=(\d+) over_50ms=(\d+) "
                    r"over_100ms=(\d+)")
SWAP = re.compile(r"M3 swap count=(\d+) .*draws_since=(\d+)")


def when(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f")


def stats(values, digits=1):
    values = [v for v in values if v is not None]
    if not values:
        return None
    ordered = sorted(values)
    return {"n": len(values), "mean": round(statistics.fmean(values), digits),
            "p50": round(ordered[len(ordered) // 2], digits),
            "p95": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], digits),
            "max": round(ordered[-1], digits)}


def summarize(run):
    run_dir = ROOT / "private" / "work" / "m6_runs" / run
    perf = json.loads((run_dir / "perf_samples.json").read_text(encoding="utf-8"))
    meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8-sig"))
    lines, log_bytes = [], 0
    for path in sorted(run_dir.glob("runtime*.log")):
        log_bytes += path.stat().st_size
        lines += path.read_text(encoding="utf-8", errors="replace").splitlines()

    marks, opens, pacing, swaps, levels = [], [], [], [], {}
    first = last = None
    for line in lines:
        m = STAMP.match(line)
        if not m:
            continue
        t = when(m.group(1))
        first = first or t
        last = t
        o = OPEN.search(line)
        if o:
            opens.append(t)
            name = o.group(1).replace("/", "\\").split("\\")[-1].lower()
            if o.group(2) == "00000000" and (name.endswith(".bik") or name.endswith(".lvl")) \
                    and name not in ("fix.lvl", "transit.lvl") and (not marks or marks[-1][1] != name):
                marks.append((t, name))
            continue
        p = PACING.search(line)
        if p:
            keys = ("window", "n", "mean_us", "min_us", "p50_us", "p95_us", "p99_us", "max_us", "over_20ms",
                    "over_33ms", "over_50ms", "over_100ms")
            pacing.append((t, p.group(1), dict(zip(keys, map(int, p.groups()[1:])))))
            continue
        s = SWAP.search(line)
        if s:
            swaps.append((t, int(s.group(1)), int(s.group(2))))

    # Role of a thread = the log categories it writes under and its most frequent traced import.
    tags, calls = {}, {}
    for line in lines:
        m = re.match(r"^\[[^\]]+\] \[\w+\] \[(\w+)\] \[t(\d+)\] (?:M2 import=__imp__(\w+))?", line)
        if m:
            tags.setdefault(m.group(2), {}).setdefault(m.group(1), 0)
            tags[m.group(2)][m.group(1)] += 1
            if m.group(3):
                calls.setdefault(m.group(2), {}).setdefault(m.group(3), 0)
                calls[m.group(2)][m.group(3)] += 1
    roles = {}
    for tid, seen in tags.items():
        imports = sorted(calls.get(tid, {}).items(), key=lambda kv: -kv[1])[:3]
        roles[tid] = "/".join(sorted(seen, key=lambda k: -seen[k])[:2]) + (": " + ", ".join(n for n, _ in imports) if imports else "")

    bounds = [(first, "startup")] + marks + [(last, None)]
    phases = []
    for (start, name), (end, _) in zip(bounds, bounds[1:]):
        seconds = (end - start).total_seconds()
        chosen = [s for s in perf["samples"] if start <= when(s["local"]) < end]
        burst_end = start
        for t in opens:
            if t < start:
                continue
            if (t - burst_end).total_seconds() > 1.0:
                break
            burst_end = t
        phase = {
            "phase": name, "seconds": round(seconds, 1), "samples": len(chosen),
            "open_burst_seconds": round((burst_end - start).total_seconds(), 2),
            "cpu_percent_one_core": stats([s["cpu_percent_one_core"] for s in chosen]),
            "working_set_mb": stats([s["working_set"] / 2**20 for s in chosen]),
            "private_mb": stats([s["private_bytes"] / 2**20 for s in chosen]),
            "threads": stats([s["threads"] for s in chosen], 0),
            "gpu_util_3d_percent": stats([s.get("gpu_util_3d") for s in chosen]),
            "gpu_dedicated_mb": stats([s["gpu_dedicated_bytes"] / 2**20 for s in chosen if "gpu_dedicated_bytes" in s]),
            "gpu_shared_mb": stats([s["gpu_shared_bytes"] / 2**20 for s in chosen if "gpu_shared_bytes" in s]),
            "draws_per_swap": stats([d for t, _, d in swaps if start <= t < end], 0),
        }
        with_threads = [s for s in chosen if "thread_cpu_seconds" in s]
        if len(with_threads) >= 2:
            a0, a1 = with_threads[0], with_threads[-1]
            span = a1["t"] - a0["t"]
            top = sorted(((a1["thread_cpu_seconds"][tid] - a0["thread_cpu_seconds"].get(tid, 0.0), tid)
                          for tid in a1["thread_cpu_seconds"]), reverse=True)[:8]
            phase["top_threads"] = [{"tid": tid, "cpu_percent_one_core": round(100 * cpu / span, 1),
                                     "role": roles.get(tid, "no log line")} for cpu, tid in top if cpu > 0 and span > 0]
        if chosen:
            phase["read_mb"] = round((chosen[-1]["read_bytes"] - chosen[0]["read_bytes"]) / 2**20, 1)
        for series in ("guest_swap", "host_present"):
            windows = [w for t, kind, w in pacing if kind == series and start <= t < end]
            if windows:
                intervals = sum(w["n"] for w in windows)
                phase[series] = {
                    "windows": len(windows), "intervals": intervals,
                    "mean_ms": round(sum(w["mean_us"] * w["n"] for w in windows) / intervals / 1000, 3),
                    "p50_ms_median_of_windows": round(statistics.median(w["p50_us"] for w in windows) / 1000, 3),
                    "p95_ms_worst_window": round(max(w["p95_us"] for w in windows) / 1000, 2),
                    "p99_ms_worst_window": round(max(w["p99_us"] for w in windows) / 1000, 2),
                    "max_ms": round(max(w["max_us"] for w in windows) / 1000, 1),
                    "min_ms": round(min(w["min_us"] for w in windows) / 1000, 3),
                    "over_20ms": sum(w["over_20ms"] for w in windows),
                    "over_33ms": sum(w["over_33ms"] for w in windows),
                    "over_50ms": sum(w["over_50ms"] for w in windows),
                    "over_100ms": sum(w["over_100ms"] for w in windows),
                }
        phases.append(phase)

    samples = perf["samples"]
    seconds = (last - first).total_seconds() if first else 0
    total = {
        "run": run, "seconds_logged": round(seconds, 1), "exit_code": meta.get("exit_code"),
        "play_profile": meta.get("play_profile"), "executable_sha256": meta.get("executable_sha256"),
        "logical_processors": perf["logical_processors"], "samples": len(samples),
        "gpu_samples": perf["gpu_samples_matched"],
        "cpu_seconds": samples[-1]["cpu_seconds"] if samples else None,
        "cpu_kernel_seconds": samples[-1]["cpu_kernel_seconds"] if samples else None,
        "cpu_percent_one_core": stats([s["cpu_percent_one_core"] for s in samples]),
        "peak_working_set_mb": round(max(s["peak_working_set"] for s in samples) / 2**20, 1) if samples else None,
        "peak_commit_mb": round(max(s["peak_commit"] for s in samples) / 2**20, 1) if samples else None,
        "private_mb": stats([s["private_bytes"] / 2**20 for s in samples]),
        "handles": stats([s["handles"] for s in samples], 0),
        "threads": stats([s["threads"] for s in samples], 0),
        "read_mb": round(samples[-1]["read_bytes"] / 2**20, 1) if samples else None,
        "write_mb": round(samples[-1]["write_bytes"] / 2**20, 1) if samples else None,
        "log_lines": len(lines), "log_mb": round(log_bytes / 2**20, 2),
        "log_lines_per_second": round(len(lines) / seconds, 1) if seconds else None,
        "game_foreground_events": meta.get("game_foreground_events"),
        "game_foreground_samples": meta.get("game_foreground_samples"),
        "phases": phases,
    }
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    result = [summarize(run) for run in a.runs]
    text = json.dumps(result, indent=1) + "\n"
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
    for r in result:
        print(f"{r['run']}: {r['seconds_logged']} s, exit {r['exit_code']}, CPU mean {r['cpu_percent_one_core'] and r['cpu_percent_one_core']['mean']}% of one core, "
              f"peak WS {r['peak_working_set_mb']} MB, peak commit {r['peak_commit_mb']} MB, log {r['log_mb']} MB")
        for p in r["phases"]:
            g = p.get("guest_swap")
            print(f"  {str(p['phase']):22s} {p['seconds']:7.1f}s cpu {p['cpu_percent_one_core'] and p['cpu_percent_one_core']['mean']} "
                  f"ws {p['working_set_mb'] and p['working_set_mb']['max']} gpu3d {p['gpu_util_3d_percent'] and p['gpu_util_3d_percent']['mean']} "
                  f"vram {p['gpu_dedicated_mb'] and p['gpu_dedicated_mb']['max']} burst {p['open_burst_seconds']}s "
                  + (f"swap mean {g['mean_ms']} ms p99w {g['p99_ms_worst_window']} max {g['max_ms']} >33ms {g['over_33ms']}/{g['intervals']}" if g else "swap -"))


if __name__ == "__main__":
    main()
