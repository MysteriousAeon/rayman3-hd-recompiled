"""Clearleaf sky (E-350, D-153): compare hidden runs of the sky clear diagnostic. Standard library only.

usage: sky_clear_ab.py ORIGINAL_RUN BACKGROUND_RUN [--control ORIGINAL_RUN_2] [--png OUT_DIR]

Each RUN is a private/work/m6_runs directory made with the same schedule (config/sky/sky_ab_frames.txt); the n-th
captured frame of one run is compared with the n-th of the other. BACKGROUND_RUN is made with
R3HD_TEST_SKY_CLEAR=background, ORIGINAL_RUN without it. --control is a second original run: the A/A difference
it gives is what two runs differ by without the diagnostic (timing, animation), so only a pixel that is identical
in the two original runs and different in the background run is counted as changed by the diagnostic.

The diagnostic only replaces the scene clear's colour (black) by the level's background colour, which reaches the
picture through what is drawn over it with alpha below 1; it can only add light there. Per frame:
  stable     pixels identical in ORIGINAL_RUN and the control (all pixels without --control)
  changed    stable pixels that differ in BACKGROUND_RUN
  brighter   changed pixels no channel of which got darker (what adding the clear colour can do)
  other      changed pixels with a channel that got darker (not explained by the clear colour)
  black      stable pixels that are black (max channel <= 8) in ORIGINAL_RUN, and how many of them changed
with the share of changed pixels in each quarter of the height (top first). --png writes a 2x reduced strip per
frame (original | background | mask: white = brighter, red = other, grey = not stable) into OUT_DIR (keep it under
private/).
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from m22_frame_png import read_bmp, write_png


def frames(run: Path) -> list:
    return sorted(run.glob("m3_frame_*.bmp"))


def judge(a: Path, b: Path, c: Path, png: Path = None) -> dict:
    w, h, ra = read_bmp(a)
    wb, hb, rb = read_bmp(b)
    assert (w, h) == (wb, hb), f"{b.name}: size {wb}x{hb}, expected {w}x{h}"
    rc = read_bmp(c)[2] if c else None
    n = {"stable": 0, "changed": 0, "brighter": 0, "other": 0, "black": 0, "black_changed": 0}
    bands = [[0, 0] for _ in range(4)]
    mask = []
    for y in range(h):
        la, lb, lc = ra[y], rb[y], rc[y] if rc else None
        band = bands[min(3, y * 4 // h)]
        out = bytearray(w * 3)
        for x in range(0, w * 3, 3):
            pa, pb = la[x:x + 3], lb[x:x + 3]
            if lc is not None and lc[x:x + 3] != pa:
                out[x:x + 3] = b"\x60\x60\x60"
                continue
            n["stable"] += 1
            band[1] += 1
            black = max(pa) <= 8
            n["black"] += black
            if pa == pb:
                continue
            n["changed"] += 1
            n["black_changed"] += black
            band[0] += 1
            if all(pb[i] >= pa[i] for i in range(3)):
                n["brighter"] += 1
                out[x:x + 3] = b"\xff\xff\xff"
            else:
                n["other"] += 1
                out[x:x + 3] = b"\xff\x00\x00"
        mask.append(bytes(out))
    n["bands"] = [round(k / t, 4) if t else 0.0 for k, t in bands]
    n["pixels"] = w * h
    if png:
        png.mkdir(parents=True, exist_ok=True)
        half = lambda row: b"".join(row[i:i + 3] for i in range(0, len(row), 6))  # noqa: E731
        rows = [half(ra[y]) + half(rb[y]) + half(mask[y]) for y in range(0, h, 2)]
        write_png(png / f"{b.parent.name}_{b.stem}.png", 3 * ((w + 1) // 2), len(rows), rows)
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("original", type=Path)
    ap.add_argument("background", type=Path)
    ap.add_argument("--control", type=Path)
    ap.add_argument("--png", type=Path)
    args = ap.parse_args()
    fa, fb = frames(args.original), frames(args.background)
    fc = frames(args.control) if args.control else [None] * len(fa)
    if not fa or len(fa) != len(fb) or len(fa) != len(fc):
        print(f"SKY_AB FAIL frame counts original={len(fa)} background={len(fb)} control={len(fc)}")
        return 1
    other = 0
    for a, b, c in zip(fa, fb, fc):
        n = judge(a, b, c, args.png)
        other += n["other"]
        print(f"{b.parent.name} {a.stem} vs {b.stem}: stable {n['stable'] / n['pixels']:.4f} changed {n['changed']} "
              f"(brighter {n['brighter']}, other {n['other']}) black {n['black']} of which changed "
              f"{n['black_changed']}; changed share by quarter (top first) {n['bands']}")
    print(f"SKY_AB {'PASS' if other == 0 else 'CHECK'} frames={len(fa)} other={other}")
    return 0 if other == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
