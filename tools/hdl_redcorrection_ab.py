"""HD+ lighting L1 (D-150): judge hidden same-frame A/B runs of the red-correction bypass. Standard library only.

usage: hdl_redcorrection_ab.py RUN [RUN ...] [--png OUT_DIR]

RUN is a private/work/m6_runs directory made with config/lighting/redcorr_split_frames.txt and
R3HD_RED_CORRECTION_AB=split. In every captured frame the left half L is the left half of the picture through the
title's red-correction pass and the right half R is the same pixels through the bypass (same frame, same game
state, same camera and resolution).

The pass reads and writes 8-bit colour (k_8_8_8_8 texture and render target); the capture is taken after the
guest's 256-entry display gamma ramp, which the split run logs ("HDL red_correction ramp"). So the judge works
forwards through that chain: every pass input I whose ramped value is R (the bypass writes I unchanged), then the
shader's own correction of I (psm/redcorrection.psh, written to 8 bits: rounded either way), then the ramp
again, which must give L. Per pixel of the left half:
  same        L == R and the pass leaves (some) such I alone: untouched in both modes
  expected    L != R and L is what the pass makes of such an I: the bypass removes exactly the correction
  unexpected  L != R and no such I explains it: a change the bypass must not cause
  missed      L == R although the pass would change every such I
Prints per frame the share of the half that changes, where (4 x 4 grid of the left half) and samples, and
`HDL_SPLIT PASS` when every frame has 0 unexpected and 0 missed pixels and every run has changed pixels. --png writes a 2x reduced strip per
frame (L | R | changed mask: white = expected, red = unexpected / missed) into OUT_DIR (keep it under private/).
"""
import argparse
import itertools
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from m22_frame_png import read_bmp, write_png


def acts(i, x):
    s = i[0] + i[1] + i[2]
    return s > 0 and i[0] / s >= x


def corrected(i, x, y):
    """The shader's correction of 8-bit input i, as the 8-bit values the render target may store."""
    r, g, b = i[0] / 255, i[1] / 255 + 0.0001, i[2] / 255 + 0.0001
    k = y * r / x / (g + b)
    gs, bs = min(255.0, g * k * 255), min(255.0, b * k * 255)
    return [(i[0], gg, bb) for gg in {int(gs), min(255, int(gs) + 1)} for bb in {int(bs), min(255, int(bs) + 1)}]


class Chain:
    def __init__(self, ramp, x, y):
        self.ramp, self.x, self.y = ramp, x, y
        # The presenter turns the 10-bit ramp entry into the 8-bit capture.
        self.out = [[round(v * 255 / 1023) for v in ch] for ch in ramp]
        self.pre = [{} for _ in range(3)]
        for c in range(3):
            for i, v in enumerate(self.out[c]):
                self.pre[c].setdefault(v, []).append(i)
        self.memo = {}

    def shown(self, o):
        return tuple(self.out[c][o[c]] for c in range(3))

    def classify(self, L, R):
        key = (L, R)
        if key in self.memo:
            return self.memo[key]
        inputs = list(itertools.product(*(self.pre[c].get(R[c], []) for c in range(3))))
        if not inputs:
            verdict = "unexpected"  # R is not a value the ramp can produce
        else:
            identity = any(not acts(i, self.x) for i in inputs)
            results = {self.shown(o) for i in inputs if acts(i, self.x) for o in corrected(i, self.x, self.y)}
            if L == R:
                verdict = "same" if identity or L in results else "missed"
            else:
                verdict = "expected" if L in results else "unexpected"
        self.memo[key] = verdict
        return verdict


def run_info(run: Path):
    log = "\n".join(p.read_text(errors="replace") for p in sorted(run.glob("runtime*.log")))
    swaps = [int(s) for s in re.findall(r"M6 frame_capture request_id=\d+ swap=(\d+) .*saved=true", log)]
    c0 = re.search(r"HDL red_correction pass=\w+ c0=\(([\d.e-]+),([\d.e-]+)\)", log)
    split = re.search(r"HDL red_correction pass=split .* shift=(\d+)", log)
    ramp = {m[0]: [int(v) for v in m[1].split(",")]
            for m in re.findall(r"HDL red_correction ramp channel=(\w) values=([\d,]+)", log)}
    return ([run / f"m3_frame_{s:05d}.bmp" for s in swaps], (float(c0[1]), float(c0[2])) if c0 else None,
            int(split[1]) if split else None, [ramp[c] for c in "rgb"] if len(ramp) == 3 else None)


def judge(path: Path, chain: Chain, shift: int, png: Path = None):
    w, h, rows = read_bmp(path)
    half = w // 2
    if shift != half:
        print(f"  {path.name}: split shift {shift} is not half the width {w}")
        return False, 0
    n = {"same": 0, "expected": 0, "unexpected": 0, "missed": 0}
    where, grid, samples, masks = [], [[0] * 4 for _ in range(4)], {}, []
    colour = {"expected": b"\xff\xff\xff", "unexpected": b"\xff\x00\x00", "missed": b"\xff\x00\x00"}
    for yy in range(h):
        line = rows[yy]
        mask = bytearray(half * 3)
        for xx in range(half):
            L = tuple(line[xx * 3:xx * 3 + 3])
            R = tuple(line[(xx + half) * 3:(xx + half) * 3 + 3])
            v = chain.classify(L, R)
            n[v] += 1
            if v == "same":
                continue
            mask[xx * 3:xx * 3 + 3] = colour[v]
            if v == "expected":
                grid[yy * 4 // h][xx * 4 // half] += 1
                samples[(R, L)] = samples.get((R, L), 0) + 1
            elif len(where) < 5:
                where.append((v, xx, yy, L, R))
        masks.append(bytes(mask))
    total = half * h
    ok = n["unexpected"] == 0 and n["missed"] == 0
    print(f"  {path.name}: changed {n['expected']} of {total} ({100 * n['expected'] / total:.2f}%), "
          f"same {n['same']}, unexpected {n['unexpected']}, missed {n['missed']} -> {'ok' if ok else 'FAIL'}")
    if where:
        print(f"    first problems (kind, x, y, L, R): {where}")
    if n["expected"]:
        print(f"    changed per quarter of the left half (rows top to bottom): {grid}")
        common = sorted(samples.items(), key=lambda kv: -kv[1])[:4]
        print(f"    most common changes, bypass -> title (count): {[(r, l, c) for (r, l), c in common]}")
    if png:
        png.mkdir(parents=True, exist_ok=True)
        out = []
        for yy in range(0, h, 2):
            line, strip = rows[yy], bytearray()
            for src, off in ((line, 0), (line, half), (masks[yy], 0)):
                strip += b"".join(src[(off + xx) * 3:(off + xx) * 3 + 3] for xx in range(0, half, 2))
            out.append(bytes(strip))
        write_png(png / f"{path.parent.name}_{path.stem}.png", 3 * (half // 2), len(out), out)
    return ok, n["expected"]


def above_cap(run: Path, ramp, c0) -> list:
    """--cap: per frame, the pixels the title's pass cannot have written: every 8-bit value the ramp maps to the
    captured one has a red share above c0.x even with green and blue each rounded down by up to 1 by the render
    target (r / (r + g + b + 2) > c0.x). The pass caps the share at c0.x (c0.x + c0.y = 1), so a run with the pass
    leaves none; a bypassed run keeps the scene's deep reds."""
    chain, counts, memo = Chain(ramp, *c0), [], {}
    for path in run_info(run)[0]:
        w, h, rows = read_bmp(path)
        n = 0
        for line in rows:
            for xx in range(w):
                px = tuple(line[xx * 3:xx * 3 + 3])
                if px not in memo:
                    inputs = itertools.product(*(chain.pre[c].get(px[c], []) for c in range(3)))
                    memo[px] = all(i[0] / (sum(i) + 2) > c0[0] for i in inputs)
                n += memo[px]
        counts.append(n)
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", type=Path, nargs="+")
    ap.add_argument("--png", type=Path)
    ap.add_argument("--cap", nargs=2, type=Path, metavar=("ORIGINAL_RUN", "BYPASS_RUN"),
                    help="also check a whole-frame run with the title's pass (no pixel above the cap) and one with "
                         "R3HD_RED_CORRECTION=bypass (pixels above the cap); the ramp and c0 come from the first "
                         "split RUN")
    a = ap.parse_args()
    ok = True
    if a.cap:
        _, c0, _, ramp = run_info(a.runs[0])
        original, bypass = above_cap(a.cap[0], ramp, c0), above_cap(a.cap[1], ramp, c0)
        cap_ok = bool(original) and bool(bypass) and not any(original) and all(bypass)
        ok &= cap_ok
        print(f"cap c0.x={c0[0]:.2f}: pixels above it per frame, {a.cap[0].name} {original}, "
              f"{a.cap[1].name} {bypass} -> {'ok' if cap_ok else 'FAIL'}")
    for run in a.runs:
        paths, c0, shift, ramp = run_info(run)
        if not paths or not c0 or shift is None or not ramp:
            print(f"{run.name}: frames {len(paths)}, c0 {c0}, split {shift}, ramp {bool(ramp)}: not a split run")
            ok = False
            continue
        chain = Chain(ramp, *c0)
        print(f"{run.name}: c0=({c0[0]:.4f}, {c0[1]:.4f}), {len(paths)} frames, ramp entry 32 = {ramp[0][32]} / 1023")
        changed = 0
        for p in paths:
            frame_ok, frame_changed = judge(p, chain, shift, a.png)
            ok &= frame_ok
            changed += frame_changed
        # A bypass that did nothing would leave every pixel "same": the run must show the correction somewhere.
        if not changed:
            print(f"  {run.name}: no pixel changed in any frame (the pass never acted, or the split did nothing)")
            ok = False
    print(f"HDL_SPLIT {'PASS' if ok else 'FAIL'} runs={len(a.runs)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
