"""M22: decode one texture of a level's BTF / BHF bundle (layout: RESEARCH "Raymap", verified locally) to a PNG
for inspection, and print coarse statistics. Assumes what the bundle shows for the textures examined so far:
first part = top mip, DXT1 (8 bytes per 4x4 block) or DXT5 (16), 16-bit byte-swapped, linear (not tiled).
Output is game-derived: keep it under private/.

usage: m22_btf_texture.py LEVEL_DIR/NAME_2.bhf --list
       m22_btf_texture.py LEVEL_DIR/NAME_2.bhf TEXTURE_NAME OUT.png [--fmt DXT1|DXT5] [--size WxH]
"""
import argparse
import io
import struct
from pathlib import Path

from PIL import Image


def entries(bhf: Path):
    b = bhf.read_bytes()
    n, = struct.unpack_from(">I", b, 0)
    assert len(b) == 4 + n * 0x114
    for i in range(n):
        o = 4 + i * 0x114
        s1, o1, s2, o2 = struct.unpack_from(">4I", b, o)
        yield i, b[o + 16:o + 0x114].split(b"\0")[0].decode("latin1"), s1, o1, s2, o2


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bhf", type=Path)
    ap.add_argument("name", nargs="?")
    ap.add_argument("out", nargs="?", type=Path)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--fmt", default="")
    ap.add_argument("--size", default="")
    a = ap.parse_args()
    rows = list(entries(a.bhf))
    if a.list or not a.name:
        for r in rows:
            print("%3d %-44s top=%7d rest=%7d" % (r[0], r[1], r[2], r[4]))
        return
    _, name, s1, o1, _, _ = next(r for r in rows if r[1].lower().endswith(a.name.lower()))
    raw = bytearray(a.bhf.with_suffix(".btf").read_bytes()[o1:o1 + s1])
    raw[0::2], raw[1::2] = raw[1::2], raw[0::2]
    if a.size:
        w, h = map(int, a.size.split("x"))
        fmt = a.fmt or ("DXT1" if w * h // 2 == s1 else "DXT5")
    else:
        fmt = a.fmt or "DXT1"
        side = int((s1 * (2 if fmt == "DXT1" else 1)) ** 0.5)
        w = h = side
    assert (w * h // 2 if fmt == "DXT1" else w * h) == s1, (w, h, fmt, s1)
    header = (b"DDS " + struct.pack("<7I44x", 124, 0x81007, h, w, len(raw), 0, 1)
              + struct.pack("<II4s20x", 32, 4, fmt.encode()) + struct.pack("<I16x", 0x1000))
    im = Image.open(io.BytesIO(header + bytes(raw))).convert("RGBA")
    im.save(a.out)
    px = list(im.getdata())
    bands = 8
    print(f"{name}: {w}x{h} {fmt}")
    for i in range(bands):
        part = px[i * h // bands * w:(i + 1) * h // bands * w]
        mean = [sum(p[c] for p in part) / len(part) for c in range(4)]
        dark = sum(1 for p in part if p[0] + p[1] + p[2] < 24) / len(part)
        print(f"  rows {i * h // bands:4d}..{(i + 1) * h // bands - 1:4d}: mean rgba = {mean[0]:5.1f} {mean[1]:5.1f} {mean[2]:5.1f} {mean[3]:5.1f}  dark share {dark:.3f}")


if __name__ == "__main__":
    main()
