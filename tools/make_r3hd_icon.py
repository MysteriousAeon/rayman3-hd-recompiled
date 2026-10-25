#!/usr/bin/env python3
"""Deterministic application and Settings icons from pinned Microsoft Fluent SVG sources.

The MIT-licensed sources, provenance and hashes are in tools/icons/fluent/README.md.
Only these small filled path assets are supported; no SVG library, font or game artwork is used.
The standard-library rasterizer uses cubic flattening and supersampled nonzero-winding fills.
The game variant is a neutral application symbol for setup and the executable fallback.
A locally extracted package icon takes precedence for the actual game window and Play shortcuts.
Icon files are build outputs only; never commit them.
"""
import argparse
import math
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "private" / "work" / "launcher" / "r3hd.ico"
DEFAULT_SETTINGS = ROOT / "private" / "work" / "launcher" / "r3hd_settings.ico"
SIZES = (16, 24, 32, 48, 64, 256)


def clamp(v, lo=0.0, hi=1.0):
    return min(hi, max(lo, v))


def contours(path):
    """Flatten the absolute M/L/H/V/C/Z subset in the pinned filled icons; reject anything else."""
    tokens = re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", path)
    out, points, cursor, index, command = [], [], (0., 0.), 0, None
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
        if command == "Z":
            if points:
                points.append(points[0])
                out.append(points)
                cursor = points[0]
                points = []
            command = None
            continue
        if command not in ("M", "L", "H", "V", "C"):
            raise ValueError(f"Unsupported icon path command: {command}")
        count = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6}[command]
        args = list(map(float, tokens[index:index + count]))
        index += count
        if command == "C":
            x0, y0 = cursor
            x1, y1, x2, y2, x3, y3 = args
            for step in range(1, 33):
                t = step / 32
                u = 1 - t
                points.append((u**3*x0 + 3*u*u*t*x1 + 3*u*t*t*x2 + t**3*x3,
                               u**3*y0 + 3*u*u*t*y1 + 3*u*t*t*y2 + t**3*y3))
            cursor = (x3, y3)
        else:
            cursor = ((args[0], cursor[1]) if command == "H" else
                      (cursor[0], args[0]) if command == "V" else tuple(args))
            points.append(cursor)
            if command == "M":
                command = "L"
    if points:
        raise ValueError("Unclosed icon path")
    return out


def render(size: int, variant: str = "game") -> bytes:
    """RGBA rows, top first, with a restrained blue tile and white Fluent symbol."""
    name = "settings" if variant == "settings" else "app_generic"
    source_size = min(48, size if size in (16, 24, 32, 48) else 48)
    if name == "app_generic" and source_size == 16:
        source_size = 24
    svg = ET.fromstring((ROOT / "tools/icons/fluent" / f"ic_fluent_{name}_{source_size}_filled.svg").read_bytes())
    scale = size / source_size
    paths = []
    for el in svg:
        if el.tag.rsplit("}", 1)[-1] != "path":
            raise ValueError("Unexpected icon element")
        paths += contours(el.attrib["d"])
    edges = [(x1 * scale, y1 * scale, x2 * scale, y2 * scale)
             for points in paths for (x1, y1), (x2, y2) in zip(points, points[1:]) if y1 != y2]
    ss = 4
    coverage = [0] * (size * size)
    for row in range(size * ss):
        y = (row + .5) / ss
        hits = sorted((x1 + (y - y1) * (x2 - x1) / (y2 - y1), 1 if y2 > y1 else -1)
                      for x1, y1, x2, y2 in edges if min(y1, y2) <= y < max(y1, y2))
        winding, previous = 0, 0.
        for x, delta in hits:
            if winding:
                start = max(0, math.ceil(previous * ss - .5))
                stop = min(size * ss, math.ceil(x * ss - .5))
                for col in range(start, stop):
                    coverage[(row // ss) * size + col // ss] += 1
            winding += delta
            previous = x
    tile = (57, 78, 104) if variant == "settings" else (29, 94, 154)
    out = bytearray()
    for y in range(size):
        for x in range(size):
            # Rounded tile, clear silhouette on either light or dark Windows surfaces.
            qx, qy = abs((x + .5) / size - .5) - .31, abs((y + .5) / size - .5) - .31
            distance = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - .16
            alpha = round(255 * clamp(.5 - distance * size))
            cov = coverage[y * size + x] / (ss * ss)
            out += bytes(round(c + (255 - c) * cov) for c in tile) + bytes([alpha])
    return bytes(out)


def png(size: int, rgba: bytes) -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + rgba[y * size * 4:(y + 1) * size * 4] for y in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def bmp(size: int, rgba: bytes) -> bytes:
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    rows = []
    for y in reversed(range(size)):
        row = rgba[y * size * 4:(y + 1) * size * 4]
        rows.append(b"".join(bytes((row[i + 2], row[i + 1], row[i], row[i + 3])) for i in range(0, len(row), 4)))
    mask_stride = ((size + 31) // 32) * 4
    mask = bytearray()
    for y in reversed(range(size)):
        bits = bytearray(mask_stride)
        for x in range(size):
            if rgba[(y * size + x) * 4 + 3] == 0:
                bits[x // 8] |= 0x80 >> (x % 8)
        mask += bits
    return header + b"".join(rows) + bytes(mask)


def build(variant: str = "game") -> bytes:
    images = []
    for size in SIZES:
        rgba = render(size, variant)
        images.append((size, png(size, rgba) if size >= 256 else bmp(size, rgba)))
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, data = b"", b""
    for size, blob in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset + len(data))
        data += blob
    return head + entries + data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--variant", choices=["game", "settings"], default="game")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--check", type=Path)
    a = ap.parse_args()
    a.out = a.out or (DEFAULT_SETTINGS if a.variant == "settings" else DEFAULT)
    icon = build(a.variant)
    if a.check:
        ok = a.check.is_file() and a.check.read_bytes() == icon
        print(f"R3HD_ICON {'OK' if ok else 'DIFFERS'} {a.check}")
        return 0 if ok else 1
    a.out.parent.mkdir(parents=True, exist_ok=True)
    if not a.out.is_file() or a.out.read_bytes() != icon:  # unchanged bytes keep the time stamp (no needless relink)
        a.out.write_bytes(icon)
    print(f"R3HD_ICON WRITTEN {a.out} ({len(icon)} bytes, sizes {', '.join(map(str, SIZES))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
