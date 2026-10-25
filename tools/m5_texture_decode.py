"""Decode a private guest-memory DXT4/5 dump (m5_texture_<base>_<w>x<h>.bin) to PNG for
inspection. Assumes linear (untiled) layout and 8-in-16 endianness, as stated by the
fetch constants recorded with the dump. Output is game-derived: keep it under private/.

usage: m5_texture_decode.py DUMP OUTPUT_PNG
"""
import re, struct, sys, io
from PIL import Image
src, out = sys.argv[1:3]
w, h = map(int, re.search(r'_(\d+)x(\d+)\.bin$', src).groups())
raw = bytearray(open(src, 'rb').read())
raw[0::2], raw[1::2] = raw[1::2], raw[0::2]
header = (b'DDS ' + struct.pack('<7I44x', 124, 0x81007, h, w, len(raw), 0, 1) + struct.pack('<II4s20x', 32, 4, b'DXT5') +
          struct.pack('<I16x', 0x1000))
assert len(header) == 128
Image.open(io.BytesIO(header + bytes(raw))).save(out)
