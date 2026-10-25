#!/usr/bin/env python3
"""M50 (D-089, R-02): classify every tracked file by origin and licence scope (config/release/provenance.json).

    python tools/m50_provenance.py check [--list ORIGIN]

Fails (exit 1) when a tracked file matches no rule, when a file a rule names exactly is not tracked (unless the rule is "optional"), or when a
'project' file outside the declared third-party / derived set carries a foreign copyright line. Prints counts per
origin and licence, then M50_PROVENANCE PASS|FAIL. Technical check only, not a legal clearance.
"""
import argparse
import fnmatch
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "config" / "release" / "provenance.json"
# A copyright line of someone else in a file declared as the project's own would contradict the record.
FOREIGN = re.compile(rb"^\s*(//|#|\*|;)?\s*Copyright \(c\)", re.I | re.M)


def classify(paths, rules):
    out, unmatched = {}, []
    for p in paths:
        for r in rules:
            if any(fnmatch.fnmatchcase(p, pat) for pat in r["paths"]):
                out[p] = r
                break
        else:
            unmatched.append(p)
    return out, unmatched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("--list")
    a = ap.parse_args()
    rules = json.loads(RULES.read_text(encoding="utf-8"))["rules"]
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    # Files written but not yet committed count as well, so the check can run before a commit.
    tracked += subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.split()
    tracked = sorted(set(tracked))
    got, unmatched = classify(tracked, rules)
    # An "optional" rule names a file the public source export leaves out (config/release/public_export.json).
    exact = [pat for r in rules if not r.get("optional") for pat in r["paths"] if not any(c in pat for c in "*?[")]
    missing = [p for p in exact if p not in tracked]
    foreign = []
    for p, r in got.items():
        if r["origin"] == "project" and p.endswith((".py", ".cpp", ".h", ".c", ".cmake", ".bat", ".ps1", ".iss")):
            if FOREIGN.search((ROOT / p).read_bytes()[:4096]):
                foreign.append(p)
    counts = Counter((r["origin"], r["licence"]) for r in got.values())
    for (origin, lic), n in sorted(counts.items()):
        print(f"{n:5d}  {origin:17s} {lic}")
    if a.list:
        for p, r in got.items():
            if r["origin"] == a.list:
                print("   ", p)
    ok = not unmatched and not missing and not foreign
    for label, items in (("unmatched", unmatched), ("missing", missing), ("foreign copyright in project file", foreign)):
        if items:
            print(f"  {label}: {items[:10]}")
    print(f"M50_PROVENANCE {'PASS' if ok else 'FAIL'} {len(tracked)} files")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
