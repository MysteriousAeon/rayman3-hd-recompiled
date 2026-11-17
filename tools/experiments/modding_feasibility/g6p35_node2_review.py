#!/usr/bin/env python3
"""E-524 (G6-P35): offline review of the G6-P34 run C graph C measurement (no game run).

    g6p35_node2_review.py      reads private/work/e523/runs_c/r1/M/samples.json (FairyLight 2 positions, run e523c_r1_M)
                               and writes private/work/e523/node2_offline.json

For every graph C node (moved nodes at their authored position, unmoved ones at the original) it reports:
  point_min   - the G6-P34 C4 measure: the closest SAMPLE (positions every ~0.11 s)
  segment_min - the closest point of the straight segments between consecutive samples
  passes      - per visit (samples within 1.5 units): (time, closest sample, closest segment)
and the sampling interval and the distance FairyLight 2 travels between samples. The pre-registered G6-P34 verdict
is not changed by this review; it only explains the measurement.
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import g6p34_remix_runtime as g  # noqa: E402

ROOT = HERE.parents[2]
SRC = ROOT / "private" / "work" / "e523" / "runs_c" / "r1" / "M" / "samples.json"
OUT = ROOT / "private" / "work" / "e523" / "node2_offline.json"


def segdist(p, a, b):
    ab = [b[i] - a[i] for i in range(3)]
    L = sum(c * c for c in ab)
    t = 0 if L == 0 else max(0, min(1, sum(ab[i] * (p[i] - a[i]) for i in range(3)) / L))
    return math.dist(p, [a[i] + t * ab[i] for i in range(3)])


def main():
    S = json.loads(SRC.read_text())
    f2 = [(x["t"], x["p"]["f2"]) for x in S if "f2" in x["p"]]
    m, s, _ = g.project("C")
    tg = {t[0]: t for t in g.targets_so(m, s)}
    gr = m.graphs[(g.FAIRY20, 2, 2)]
    nodes = {n: (tg[f"c{n}"][3] if f"c{n}" in tg else gr["nodes"][n]["position"]) for n in range(6)}
    steps = [math.dist(f2[i][1], f2[i + 1][1]) for i in range(len(f2) - 1)]
    dts = sorted(f2[i + 1][0] - f2[i][0] for i in range(len(f2) - 1))
    mv = sorted(x for x in steps if x > 0.01)
    res = {}
    for n, P in nodes.items():
        pt = [math.dist(f, P) for _, f in f2]
        sd = [segdist(P, f2[i][1], f2[i + 1][1]) for i in range(len(f2) - 1)]
        passes, i = [], 0
        while i < len(pt):
            if pt[i] >= 1.5:
                i += 1
                continue
            j = i
            while j < len(pt) and pt[j] < 1.5:
                j += 1
            k = min(range(i, j), key=lambda q: pt[q])
            passes.append((round(f2[k][0], 2), round(pt[k], 3), round(min(sd[max(i - 1, 0):min(j, len(sd))]), 3)))
            i = j
        res[n] = {"moved": f"c{n}" in tg, "point_min": round(min(pt), 3), "segment_min": round(min(sd), 3),
                  "passes": passes}
    out = {"samples": len(f2), "dt_median": round(dts[len(dts) // 2], 4), "step_median": round(mv[len(mv) // 2], 3),
           "step_max": round(max(steps), 3), "nodes": res}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
