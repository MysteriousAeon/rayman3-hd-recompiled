"""M22: turn a private frame capture (24 / 32-bit BMP) into a PNG for viewing, optionally reduced or cropped,
and print coarse luminance statistics per horizontal band. Standard library only; output stays under private/.

usage: m22_frame_png.py IN.bmp OUT.png [--div N] [--crop X0,Y0,X1,Y1] [--bands N]
"""
import argparse
import struct
import zlib
from pathlib import Path


def read_bmp(path: Path):
    b = path.read_bytes()
    assert b[:2] == b"BM", "not a BMP"
    off, = struct.unpack_from("<I", b, 10)
    w, h, _, bpp = struct.unpack_from("<iiHH", b, 18)
    assert bpp in (24, 32), bpp
    step, flip = bpp // 8, h > 0
    h = abs(h)
    stride = (w * step + 3) & ~3
    rows = []
    for y in range(h):
        src = (h - 1 - y) if flip else y
        line = b[off + src * stride: off + src * stride + w * step]
        rgb = bytearray(w * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = line[2::step], line[1::step], line[0::step]
        rows.append(bytes(rgb))
    return w, h, rows


def write_png(path: Path, w: int, h: int, rows) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    raw = b"".join(b"\0" + r for r in rows)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--div", type=int, default=1)
    ap.add_argument("--crop", default="")
    ap.add_argument("--bands", type=int, default=0)
    a = ap.parse_args()
    w, h, rows = read_bmp(a.src)
    if a.crop:
        x0, y0, x1, y1 = map(int, a.crop.split(","))
        rows = [r[x0 * 3:x1 * 3] for r in rows[y0:y1]]
        w, h = x1 - x0, y1 - y0
    if a.bands:
        for i in range(a.bands):
            part = rows[i * h // a.bands:(i + 1) * h // a.bands]
            n = sum(len(r) for r in part)
            mean = sum(sum(r) for r in part) / n
            black = sum(1 for r in part for x in range(0, len(r), 3) if r[x] + r[x + 1] + r[x + 2] < 12) * 3 / n
            print(f"band {i}: mean={mean:.1f} black_share={black:.3f}")
    if a.div > 1:
        d = a.div
        rows = [bytes(rows[y][x * 3 + c] for x in range(0, w - d + 1, d) for c in range(3)) for y in range(0, h - d + 1, d)]
        w, h = len(rows[0]) // 3, len(rows)
    write_png(a.dst, w, h, rows)
    print(f"{a.dst} {w}x{h}")


if __name__ == "__main__":
    main()
