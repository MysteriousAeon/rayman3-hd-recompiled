#!/usr/bin/env python3
"""M48-P: the two language-selector flags of the playtest setup, drawn from their geometric specifications (no
artwork is copied; national flags, no game material). Build-time only (Pillow); the PNGs are build outputs.

    python tools/m48p_flags.py OUTDIR [--widths 96,120,144,192]

Writes OUTDIR/flag_tr_<W>.png (Turkey, 3:2) and OUTDIR/flag_en_<W>.png (United Kingdom, the 1:2 Union Flag
centre-cropped to 3:2) for every width W (W x W*2/3, a 1 px grey border, 4x supersampled): one per DPI step (100, 125,
150, 200 %), so the setup shows an unscaled bitmap.
"""
import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

SS = 4


def star(cx, cy, r, rot_deg):
    pts = []
    for i in range(10):
        a = math.radians(rot_deg + i * 36)
        rr = r if i % 2 == 0 else r * 0.381966  # regular five-pointed star
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def turkey(w, h):
    # Wikimedia geometry on a 1200 x 800 field: outer circle (425, 400) r 200, inner (475, 400) r 160, star centre
    # (683.334, 400) circumradius 100 with one point towards the hoist.
    W, H = w * SS, h * SS
    k = H / 800
    im = Image.new("RGB", (W, H), (227, 10, 23))
    d = ImageDraw.Draw(im)
    for cx, r, col in ((425, 200, (255, 255, 255)), (475, 160, (227, 10, 23))):
        d.ellipse([(cx - r) * k, (400 - r) * k, (cx + r) * k, (400 + r) * k], fill=col)
    d.polygon(star(683.334 * k, 400 * k, 100 * k, 180), fill=(255, 255, 255))
    return im


def union(w, h):
    # The Union Flag on its 60 x 30 construction grid, then the centre 45 x 30 (3:2).
    W, H = w * SS, h * SS
    u = H / 30
    full = Image.new("RGB", (int(60 * u), H), (1, 33, 105))
    d = ImageDraw.Draw(full)
    white, red = (255, 255, 255), (200, 16, 46)
    P = lambda x, y: (x * u, y * u)  # noqa: E731
    d.line([P(-6, -3), P(66, 33)], fill=white, width=int(6 * u))
    d.line([P(-6, 33), P(66, -3)], fill=white, width=int(6 * u))
    # counterchanged red diagonals: a 4-unit red line clipped to one half of each white band
    reds = Image.new("RGB", full.size, red)
    line_mask = Image.new("L", full.size, 0)
    lm = ImageDraw.Draw(line_mask)
    lm.line([P(-6, -3), P(66, 33)], fill=255, width=int(4 * u))
    lm.line([P(-6, 33), P(66, -3)], fill=255, width=int(4 * u))
    clip = Image.new("L", full.size, 0)
    cd = ImageDraw.Draw(clip)
    for tri in (((30, 15), (60, 15), (60, 30)), ((30, 15), (30, 30), (0, 30)),
                ((30, 15), (0, 15), (0, 0)), ((30, 15), (30, 0), (60, 0))):
        cd.polygon([P(*p) for p in tri], fill=255)
    mask = Image.new("L", full.size, 0)
    mask.paste(line_mask, (0, 0), clip)
    full.paste(reds, (0, 0), mask)
    d.rectangle([P(25, 0), P(35, 30)], fill=white)
    d.rectangle([P(0, 10), P(60, 20)], fill=white)
    d.rectangle([P(27, 0), P(33, 30)], fill=red)
    d.rectangle([P(0, 12), P(60, 18)], fill=red)
    left = (full.width - W) // 2
    return full.crop((left, 0, left + W, H))


def finish(im, w, h):
    im = im.resize((w, h), Image.LANCZOS)
    ImageDraw.Draw(im).rectangle([0, 0, w - 1, h - 1], outline=(150, 150, 150))
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--widths", default="96,120,144,192")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for w in (int(x) for x in a.widths.split(",")):
        h = w * 2 // 3
        finish(turkey(w, h), w, h).save(a.out / f"flag_tr_{w}.png", optimize=True)
        finish(union(w, h), w, h).save(a.out / f"flag_en_{w}.png", optimize=True)
    print(f"M48P_FLAGS {a.out} widths={a.widths}")


if __name__ == "__main__":
    main()
