#!/usr/bin/env python3
"""Group the address-space maps of one or more measured runs into named categories (M12).

    python tools/m12_mem_compare.py RUN [RUN ...] [--label level] [--out reports/milestone12/perf/memory.json]

Reads private/work/m6_runs/RUN/mem_map_<label>.json (tools/m12_mem_map.py --top 400) and prints commit / resident
per category in MB. Categories are recognised by allocation kind and total size; the basis of each name is given
in reports/milestone12/REPORT.md (source constants for stacks, heap segment size, guest memory layout). The
output holds sizes and counts only.
"""
import argparse
import json
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MB = 1048576


def category(entry) -> str:
    kind, total = entry["kind"], entry["commit"] + entry["reserve"]
    if kind == "private":
        if total == 16 * MB:
            return "host stacks of guest threads (16 MiB each)"
        if total == 4 * MB:
            return "host stacks of runtime threads (4 MiB each)"
        if total in (MB, 2 * MB) and entry["guard_or_noaccess"]:
            return "other thread stacks"
        if total == 0xFD0000:
            return "process heap segments (CRT malloc, blocks < 512 KB)"
        if total == 32 * MB and entry["commit"] > MB:
            return "32 MiB blocks (graphics stack, see report)"
        if total >= 256 * MB:
            return "large private reservations (no commit)"
        if total >= MB:
            return "other private allocations >= 1 MiB"
        return "private allocations < 1 MiB"
    if kind == "mapped":
        if total == 512 * MB:
            return "guest physical memory views (4 views of one 512 MiB section)"
        if total >= 128 * MB:
            return "guest virtual address space views"
        return "other mapped views"
    return "images"


def load(run: str, label: str) -> dict:
    data = json.loads((ROOT / "private" / "work" / "m6_runs" / run / f"mem_map_{label}.json").read_text())
    groups = OrderedDict()
    listed = {"private": 0, "mapped": 0}
    for entry in data["largest_allocations"]:
        group = groups.setdefault(category(entry), {"count": 0, "commit_mb": 0.0, "resident_mb": 0.0})
        group["count"] += 1
        group["commit_mb"] += entry["commit"] / MB
        group["resident_mb"] += entry["resident"] / MB
        listed[entry["kind"]] += entry["commit"]
    totals = data["totals"]
    groups["images"] = {"count": data["image_count"], "commit_mb": totals.get("image_commit", 0) / MB,
                        "resident_mb": totals.get("image_resident", 0) / MB}
    for group in groups.values():
        group["commit_mb"], group["resident_mb"] = round(group["commit_mb"], 1), round(group["resident_mb"], 1)
    return {"run": run, "label": label, "allocations": data["allocation_count"],
            "private_commit_mb": round(totals.get("private_commit", 0) / MB, 1),
            "private_resident_mb": round(totals.get("private_resident", 0) / MB, 1),
            "mapped_commit_mb": round(totals.get("mapped_commit", 0) / MB, 1),
            "private_commit_not_listed_mb": round((totals.get("private_commit", 0) - listed["private"]) / MB, 1),
            "categories": groups}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--label", default="level")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    results = [load(run, a.label) for run in a.runs]
    names = list(OrderedDict.fromkeys(name for r in results for name in r["categories"]))
    print(f"{'category (count commit/resident MB)':62}" + "".join(f"{r['run']:>26}" for r in results))
    for name in sorted(names):
        cells = []
        for r in results:
            g = r["categories"].get(name)
            cells.append(f"{g['count']:4} {g['commit_mb']:8.1f} /{g['resident_mb']:7.1f}" if g else " " * 22)
        print(f"{name:62}" + "".join(f"{c:>26}" for c in cells))
    for key in ("private_commit_mb", "private_resident_mb", "mapped_commit_mb"):
        print(f"{key:62}" + "".join(f"{r[key]:>26}" for r in results))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
