"""D-199: build a private, sparse, launch-time PlayStation texture plan.

No game files or profiles are written. Reuses M33's codec/plan format; all generated
pixels remain in the requested private/user cache. D-202 native glyph assets use
a complete native private source; accepted shoulders and separate menu art are kept.
"""
import argparse
import json
import math
import os
import struct
import sys
from pathlib import Path

# The packaged interpreter's ._pth omits the script directory. Use only the installed sibling tools.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_mods as m  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

IDENTITIES = {
    "texts\\typoray3.dds": "c835eacf29b274f99949fbcb42600227257c5476106ca00b8ee287bdc044dcbf",
    "menu\\mnu_xb512_en.dds": "8c89fbd3a5d8dabfdedc9befd636e874be1010868393c4cf5eaad7335ca1387b",
    "menu\\mnu_gen.dds": "56a1df97865ef9b75046a2714f44a5c959e97717b33672342e005d79bc224c84",
}
# D-200: metadata only. Native proprietary pixels are supplied privately, never embedded.
NATIVE_SHOULDERS = {
    "L1": (70, 35, 5, "6992eb169915eedc2ba986e103ae41b732fb150756af6520ee628974454e03f7"),
    "R1": (70, 34, 6, "19a3fc7c9d16659abbf4e37148be2836d668ef3bb238c4cb2c1b0663fe121720"),
    "L2": (62, 50, 13, "809510f84c6b1860232672ee5132a9e647f757fcdd871677d1bb942eb8a91c01"),
    "R2": (63, 49, 13, "901f6e9ad0c71d63e508a76a7814019649e2c10b059f261100e7e1177550b8c9"),
}
NATIVE_FACES = {
    "cross": (49, 49, 12, "9698ed8530474f0b64d37d95e0f62c99f66fb0bff005f9aeed5cb0c569043f10"),
    "circle": (50, 49, 12, "d66af60168242d62e1a2551ef25f42862dd9be3d7cbcef93d21b63f5308e16c6"),
    "square": (51, 49, 12, "69f4094f4682a5fc0a0d3be2888a6dff55b9337046a6244499d32ea5f44c726b"),
    "triangle": (49, 49, 12, "42c534c7900ff8671df81035e0258ee2320212917214de9b65c4ea0fdc1f96e9"),
}
NATIVE_START = {
    "start": (46, 28, 2, "928ba6b9e8ed77372a820d0ae3b9724d639ad466e572a8a7cbe191ffbf543578"),
}
NATIVE_GLYPHS = NATIVE_SHOULDERS | NATIVE_FACES | NATIVE_START
# Original physical-position codes in FontPADRay copy 1. These are NOT ASCII A/B/X/Y.
FACES = {0x63: "cross", 0x61: "circle", 0x62: "square", 0x64: "triangle"}
SHOULDERS = {0x31: "L1", 0x32: "R1", 0x33: "L2", 0x34: "R2"}
BUTTONS = FACES | SHOULDERS | {0x54: "start"}
MENU_RECTS = ((44, 456, 160, 572), (644, 492, 760, 628), (748, 620, 804, 952))
# Exact font output of the pinned bundled Turkish 1.0.1 mod. It writes whole
# atlas regions, including unchanged blocks. Preserve its changed blocks.
BUNDLED_TR_FONT = (
    "5fbaa07dd61318356e4e7dde2ed09865c80428aa09e536983265565751e2281b",
    "50dba7b46838ae1c306335445ad1a83482b58a7ed43925a1b485e4e59ecb82c3",
)


def texture(game, name):
    bhf, entry, w, h, fmt = m.resolve_texture(game, {
        "entry": name, "bundles": ["GAMEDATAbin/fix"]})[0]
    expected_side = 512 if name == m.FONT["atlas"] else 1024
    if (w, h, fmt) != (expected_side, expected_side, "DXT5"):
        raise ValueError("target texture dimensions or format changed")
    with bhf.with_suffix(".btf").open("rb") as f:
        f.seek(entry[2]); base = f.read(entry[1])
        f.seek(entry[4]); mip = f.read(entry[3])
    if m.sha256_bytes(base + mip) != IDENTITIES[name]:
        raise ValueError("target texture identity changed")
    lay = m.layout(w, h, fmt)[2]
    image = m.decode_level(w, h, m.level_rows((base, mip), lay[0], fmt), fmt)
    return bhf.with_suffix(".btf"), entry, w, h, lay, (base, mip), image


def read_shoulders(source=None):
    """Historical four-shoulder verifier, retained for D-200 comparisons only."""
    return _read_native(source or os.environ.get("R3HD_PS3_PROMPT_SOURCE") or
                        ROOT / "assets/playstation_prompts/shoulders.json", NATIVE_SHOULDERS,
                        1, "r3hd-private-ps3-shoulders")


def read_glyphs(source=None):
    return _read_native(source or os.environ.get("R3HD_PS3_PROMPT_SOURCE") or
                        ROOT / "assets/playstation_prompts/glyphs.json", NATIVE_GLYPHS,
                        2, "r3hd-private-ps3-button-glyphs")


def _read_native(source, identities, schema, kind):
    source = Path(source)
    if source.stat().st_size > 16384:
        raise ValueError("oversized native glyph manifest")
    manifest = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != schema or manifest.get("kind") != kind:
        raise ValueError("invalid native glyph manifest")
    glyphs = {}
    for name, (w, h, descent, sha) in identities.items():
        path = source.parent / f"{name}.png"
        if path.stat().st_size > 65536:
            raise ValueError("oversized native glyph image")
        data = path.read_bytes()
        if len(data) < 24 or struct.unpack_from(">II", data, 16) != (w, h):
            raise ValueError("native glyph dimensions changed")
        pw, ph, rgba = m.read_png(data)
        if (pw, ph) != (w, h) or m.sha256_bytes(rgba) != sha:
            raise ValueError("native glyph pixels changed")
        glyphs[name] = (w, h, descent, rgba)
    return glyphs


def shoulder_placement(rect, native):
    """Fit native proportions and baseline inside immutable Xbox cell/metrics."""
    _, _, h, w, _, descent = rect[:6]
    sw, sh, sd = native[:3]
    scale = min(1.0, (w - 2) / sw, (h - 2) / sh)
    tw, th = max(1, round(sw * scale)), max(1, round(sh * scale))
    left = (w - tw) // 2
    top = min(h - th, max(0, round(h - descent - (sh - sd) * scale)))
    return left, top, tw, th


def resize_native(sw, sh, rgba, tw, th):
    if (sw, sh) == (tw, th):
        return rgba
    out = bytearray(tw * th * 4)
    for y in range(th):
        y0, y1 = y * sh / th, (y + 1) * sh / th
        for x in range(tw):
            x0, x1 = x * sw / tw, (x + 1) * sw / tw
            alpha, area, color = 0.0, 0.0, [0.0] * 3
            for sy in range(int(y0), math.ceil(y1)):
                for sx in range(int(x0), math.ceil(x1)):
                    weight = (min(x1, sx + 1) - max(x0, sx)) * (min(y1, sy + 1) - max(y0, sy))
                    at = (sy * sw + sx) * 4
                    area += weight
                    a = weight * rgba[at + 3]
                    alpha += a
                    for c in range(3):
                        color[c] += a * rgba[at + c]
            at = (y * tw + x) * 4
            out[at:at + 4] = bytes([round(v / alpha) if alpha else 255 for v in color] + [round(alpha / area)])
    return bytes(out)


def glyph_placement(rect, native):
    """Native faces/Start already fit: no artificial inset or upscaling."""
    _, _, h, w, _, descent = rect[:6]
    sw, sh, sd = native[:3]
    scale = min(1.0, w / sw, h / sh)
    tw, th = max(1, round(sw * scale)), max(1, round(sh * scale))
    return ((w - tw) // 2, min(h - th, max(0, round(h - descent - (sh - sd) * scale))), tw, th)


def paint_shoulder(img, width, rect, native, placement=shoulder_placement):
    x0, y0, h, w = rect[:4]
    left, top, tw, th = placement(rect, native)
    pixels = resize_native(native[0], native[1], native[3], tw, th)
    for y in range(h):
        at = ((y0 + y) * width + x0) * 4
        img[at:at + w * 4] = b"\xff\xff\xff\0" * w
    for y in range(th):
        at = ((y0 + top + y) * width + x0 + left) * 4
        img[at:at + tw * 4] = pixels[y * tw * 4:(y + 1) * tw * 4]


def sparse_ranges(tex, img, rectangles):
    path, entry, w, h, lay, blobs, original = tex
    # Only touched compression blocks, preserving every other base/mip block exactly.
    changed = {(x, y) for x0, y0, x1, y1 in rectangles
               for y in range(y0, y1) for x in range(x0, x1)}
    prev, pw, ph = img, w, h
    ranges = []
    for i, lv in enumerate(lay):
        lw, lh = lv[5:7]
        if i:
            cur = bytearray(m.decode_level(lw, lh, m.level_rows(blobs, lv, "DXT5"), "DXT5"))
            changed = {(x // 2, y // 2) for x, y in changed if x // 2 < lw and y // 2 < lh}
            for x, y in changed:
                for c in range(4):
                    cur[(y * lw + x) * 4 + c] = (sum(prev[(min(y * 2 + dy, ph - 1) * pw +
                        min(x * 2 + dx, pw - 1)) * 4 + c] for dy in (0, 1) for dx in (0, 1)) + 2) // 4
        else:
            cur = img
        for bx, by in sorted({(x // 4, y // 4) for x, y in changed}, key=lambda b: (b[1], b[0])):
            off = lv[1] + (lv[4] + (lh + 3) // 4 - 1 - by) * lv[2] + (lv[3] + bx) * 16
            block = m.swap16(m.encode_block(cur, lw, lh, bx, by, "DXT5"))
            if block != blobs[lv[0]][off:off + 16]:
                absolute = (entry[2] if lv[0] == 0 else entry[4]) + off
                ranges.append((path, absolute, block, "r3hd.button-prompts"))
        prev, pw, ph = cur, lw, lh
    return ranges


def coalesce(ranges):
    out = []
    for path, off, data, mid in sorted(ranges, key=lambda r: (str(r[0]), r[1])):
        if out and out[-1][0] == path and out[-1][1] + len(out[-1][2]) == off:
            p, o, b, mid = out[-1]; out[-1] = (p, o, b + data, mid)
        else:
            out.append((path, off, data, mid))
    return out


def overlapping_mod_ranges(plan, ranges):
    if not plan:
        return []
    targets = {}
    for path, offset, data, _ in ranges:
        targets.setdefault(path, []).append((offset, offset + len(data)))
    targets = {path.resolve(): spans for path, spans in targets.items()}
    files = []
    overlaps = []
    for line in Path(plan).read_text(encoding="utf-8").splitlines():
        if line.startswith("file "):
            files.append(Path(line.split(" ", 2)[2]).resolve())
        elif line.startswith("range "):
            _, file_index, offset, size, _, _, mod, blob = line.split(" ", 7)
            path, offset, size = files[int(file_index)], int(offset), int(size)
            if any(offset < end and start < offset + size for start, end in targets.get(path, ())):
                overlaps.append((path, offset, size, mod, Path(blob)))
    return overlaps


def overlaps_mod(plan, ranges):
    return bool(overlapping_mod_ranges(plan, ranges))


def preserve_bundled_translation(overlaps, font, ranges):
    path, entry, _, _, _, originals, _ = font
    base, mip = entry[2], entry[4]
    expected = {(offset, len(data)): (data, pin)
                for offset, data, pin in zip((base, mip), originals, BUNDLED_TR_FONT)}
    translated = {}
    for file, offset, size, mod, blob in overlaps:
        spec = expected.get((offset, size))
        if file != path.resolve() or mod != "tr.full.dev" or spec is None or offset in translated:
            return []
        original, pin = spec
        with blob.open("rb") as stream:
            data = stream.read(size + 1)
        if len(data) != size or m.sha256_bytes(data) != pin:
            return []
        translated[offset] = (original, data)
    if translated.keys() != {base, mip}:
        return []

    def untouched(offset, size):
        for start, (original, data) in translated.items():
            pos = offset - start
            if 0 <= pos < len(original):
                return original[pos:pos + size] == data[pos:pos + size]
        return True  # menu art is outside the translation's font atlas

    return [row for row in ranges if untouched(row[1], len(row[2]))]


def prepare(game, cache, mods_plan=None, shoulder_source=None):
    native = read_glyphs(shoulder_source)
    fix = (game / "GAMEDATAbin/fix.lvl").read_bytes()
    if m.read_font(fix) is None:
        raise ValueError("font identity changed")
    font = texture(game, m.FONT["atlas"])
    img, rects = bytearray(font[-1]), []
    records = m.font_records(fix, m.FONT["others"][0])
    for code, kind in BUTTONS.items():
        rec = records[code]
        paint_shoulder(img, font[2], rec, native[kind],
                       shoulder_placement if code in SHOULDERS else glyph_placement)
        x, y, h, w = rec[:4]; rects.append((x, y, x + w, y + h))
    ranges = sparse_ranges(font, img, rects)
    menu = texture(game, "menu\\mnu_xb512_en.dds")
    ps = texture(game, "menu\\mnu_gen.dds")
    img = bytearray(menu[-1])
    for x0, y0, x1, y1 in MENU_RECTS:
        for y in range(y0, y1):
            a, b = (y * menu[2] + x0) * 4, (y * menu[2] + x1) * 4
            img[a:b] = ps[-1][a:b]
    ranges += sparse_ranges(menu, img, MENU_RECTS)
    overlaps = overlapping_mod_ranges(mods_plan, ranges)
    reason = "launch-time"
    if overlaps:
        ranges = preserve_bundled_translation(overlaps, font, ranges)
        if not ranges:
            return {"result": "ok", "plan": "", "reason": "mod overlap; existing mod retained"}
        reason = "launch-time; bundled Turkish atlas edits retained"
    ranges = coalesce(ranges)
    plan = m.write_plan_files({"cache": cache}, cache, ranges, [("r3hd.button-prompts", "1")])
    return {"result": "ok", "plan": plan, "ranges": len(ranges), "reason": reason}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--game-dir", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--mods-plan")
    ap.add_argument("--glyph-source", "--shoulder-source", dest="shoulder_source", type=Path,
                    help="native glyph manifest; else R3HD_PS3_PROMPT_SOURCE, then installed resources")
    args = ap.parse_args()
    try:
        result = prepare(args.game_dir.resolve(), args.cache.resolve(), args.mods_plan, args.shoulder_source)
    except (OSError, ValueError, KeyError, IndexError, m.Refusal) as e:
        result = {"result": "refused", "plan": "", "reason": str(e)}
    print(json.dumps(result))
