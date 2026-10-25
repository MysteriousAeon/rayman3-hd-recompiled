#!/usr/bin/env python3
"""Campaign evidence from a human session (M21): level timeline, save commits, pacing, warnings, imports.

    python tools/m21_session_report.py SESSION [--json OUT]

Reads private/play/sessions/SESSION/{runtime[.N].log,m2_faults.log,session.json} and
private/play/save_history/SESSION/*/snapshot.json. Read-only; prints metadata only (level names, times, counts,
import names, file names of failed opens), never save bytes. Every load of a level opens its .lvl file again and
is logged again (a death restart that reloads the level shows as a second entry); "seconds" is the time until
the next level load. Movies opened inside a level are listed with it.
"""
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})\] \[(\w+)\] \[(\w+)\]")
LEVEL = re.compile(r"M2 vfs_open path=D:\\GamedataBIN\\([^\\]+)\\([^\\]+)\.lvl result=00000000", re.I)
MOVIE = re.compile(r"M2 vfs_open path=D:\\VIDEOS\\(\w+\.bik) result=00000000", re.I)
STAGE = re.compile(r"M20 save stage result=(\w+) content=(\w+) stage=([\d.]+) replaces_existing=(\w+)")
COMMIT = re.compile(r"M20 save commit result=(\w+)(?: files=(\d+) header=(\w+))?")
PACING = re.compile(r"M11 pacing series=guest_swap window=\d+ n=(\d+) mean_us=(\d+) .*?over_33ms=(\d+) over_50ms=(\d+) "
                    r"over_100ms=(\d+) core_n=\d+ core_sd_us=(\d+)")
VBLANK = re.compile(r"M16 vblank mode=(\w+) .*?late_p99_us=(\d+) late_max_us=(\d+)")
IMPORT = re.compile(r"M2 import=__imp__(\w+) stub=(\w+)")
FAILED = re.compile(r"\[NtCreateFile\] FAILED: path='([^']+)'")
ACH = re.compile(r"M16 achievements_ui (\w+)")
FAULT = re.compile(r"M2 exception code=([0-9A-F]{8})")


def when(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f")


def main() -> int:
    session = sys.argv[1]
    base = ROOT / "private/play/sessions" / session
    # A long session rotates its log: runtime.N.log are the older parts (highest N first), runtime.log the last.
    parts = sorted(base.glob("runtime.*.log"), key=lambda p: -int(p.suffixes[0][1:])) + [base / "runtime.log"]
    lines = [line for part in parts for line in part.read_text(encoding="utf-8", errors="replace").splitlines()]
    first = last = None
    levels, saves, pacing, failed, imports, stubs = [], [], [], Counter(), Counter(), Counter()
    warnings, errors, vblank, ach = Counter(), [], Counter(), Counter()
    pending = None
    for line in lines:
        m = STAMP.match(line)
        if not m:
            continue
        t = when(m.group(1))
        first = first or t
        last = t
        if m.group(2) == "warning":
            warnings["texture fetch constant of type 0" if "Texture fetch constant" in line
                     else "file open failed" if "NtCreateFile" in line else re.sub(r"\[t\d+\] ", "", line[40:100])] += 1
        elif m.group(2) in ("error", "critical"):
            errors.append((m.group(2), line.split("] ", 4)[-1][:120]))
        if (x := LEVEL.search(line)) and x.group(2).lower() == x.group(1).lower():
            levels.append({"level": x.group(1), "time": t, "movies": []})
        elif (x := MOVIE.search(line)) and levels and x.group(1) not in levels[-1]["movies"]:
            levels[-1]["movies"].append(x.group(1))
        elif x := STAGE.search(line):
            pending = {"time": t, "stage_result": x.group(1), "content": x.group(2), "stage": x.group(3), "replaces_existing": x.group(4)}
        elif x := COMMIT.search(line):
            entry = pending or {"time": t}
            entry.update(commit_result=x.group(1), files=x.group(2), header=x.group(3), commit_ms=round((t - entry["time"]).total_seconds() * 1000))
            saves.append(entry)
            pending = None
        elif x := PACING.search(line):
            pacing.append((t, *map(int, x.groups())))
        elif x := VBLANK.search(line):
            vblank[x.group(1)] += 1
        elif x := FAILED.search(line):
            failed[x.group(1)] += 1
        elif x := ACH.search(line):
            ach[x.group(1)] += 1
        if x := IMPORT.search(line):
            imports[x.group(1)] += 1
            if x.group(2) != "false":
                stubs[x.group(1)] += 1
    if pending:
        saves.append({**pending, "commit_result": "MISSING"})
    for i, level in enumerate(levels):
        end = levels[i + 1]["time"] if i + 1 < len(levels) else last
        level["seconds"] = round((end - level["time"]).total_seconds(), 1)
        window = [p for p in pacing if level["time"] <= p[0] < end]
        frames = sum(p[1] for p in window)
        level["pacing"] = {
            "frames": frames,
            "mean_us": round(sum(p[1] * p[2] for p in window) / frames) if frames else None,
            "over_33ms": sum(p[3] for p in window), "over_50ms": sum(p[4] for p in window), "over_100ms": sum(p[5] for p in window),
            "core_sd_us_median": sorted(p[6] for p in window)[len(window) // 2] if window else None,
        }
        level["saves"] = [s["time"].strftime("%H:%M:%S") for s in saves if level["time"] <= s["time"] < end]
        level["time"] = level["time"].strftime("%H:%M:%S")
    faults = Counter()
    fault_log = base / "m2_faults.log"
    if fault_log.is_file():
        faults.update(FAULT.findall(fault_log.read_text(encoding="utf-8", errors="replace")))
    snapshots = []
    for snap in sorted((ROOT / "private/play/save_history" / session).glob("*/snapshot.json")):
        data = json.loads(snap.read_text(encoding="utf-8-sig"))
        slots = data["slots"][0] if data["slots"] and isinstance(data["slots"][0], list) else data["slots"]
        snapshots.append({"index": data["index"], "time": data["time"][11:19], "reason": data["reason"],
                          "slots": {s["slot"]: f"{s['level']} ({s['state']}, highest world {s['highest_world']}, revisit {s['revisit']})" for s in slots}})
    for s in saves:
        s["time"] = s["time"].strftime("%H:%M:%S")
    report = {
        "session": session, "log_first": first.strftime("%H:%M:%S"), "log_last": last.strftime("%H:%M:%S"),
        "levels": levels, "saves": saves,
        "save_commits_ok": sum(1 for s in saves if s.get("stage_result") == "ok" and s["commit_result"] == "ok"),
        "save_commits_total": len(saves), "snapshots": snapshots, "warnings": dict(warnings), "errors": errors,
        "failed_opens": dict(sorted(failed.items())), "imports_distinct": len(imports), "imports": sorted(imports),
        "stubbed_imports": dict(stubs), "vblank_modes": dict(vblank), "achievements_ui": dict(ach), "fault_codes": dict(faults),
    }
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"session {session}: log {report['log_first']} .. {report['log_last']}")
    for level in levels:
        p = level["pacing"]
        print(f"  {level['time']} {level['level']:<10} {level['seconds']:>7.1f} s  frames={p['frames']} mean_us={p['mean_us']} "
              f">33ms={p['over_33ms']} >50ms={p['over_50ms']} >100ms={p['over_100ms']} core_sd_us~{p['core_sd_us_median']} saves={level['saves']} movies={level['movies']}")
    for s in saves:
        print(f"  save {s['time']} stage={s.get('stage_result')} {s.get('content')} {s.get('stage')} replaces={s.get('replaces_existing')} "
              f"commit={s['commit_result']} files={s.get('files')} header={s.get('header')} {s.get('commit_ms')} ms")
    print(f"  save commits ok {report['save_commits_ok']}/{report['save_commits_total']}; snapshots {len(snapshots)}")
    for snap in snapshots:
        print(f"  snapshot {snap['index']:03d} {snap['time']} {snap['slots']}")
    print(f"  warnings {dict(warnings)}; errors {errors}")
    print(f"  imports distinct={len(imports)} stubbed={dict(stubs)}; vblank={dict(vblank)}; achievements_ui={dict(ach)}; faults={dict(faults)}")
    print(f"  failed opens: {len(failed)} distinct paths, {sum(failed.values())} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
