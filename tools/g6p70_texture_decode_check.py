#!/usr/bin/env python3
"""G6-P70 (D-319 / E-556): the 3D Level Viewer's texture decoder - byte-exact oracle, mutations and A/B timing.

    python tools/g6p70_texture_decode_check.py --selftest     -> G6P70_SELFTEST PASS n/n   (synthetic, no game data)
    python tools/g6p70_texture_decode_check.py --mutations    -> G6P70_MUTATIONS PASS n/n  (each mutant must be caught)
    python tools/g6p70_texture_decode_check.py make-oracle --code DIR --out DIR   (frozen oracle from a code version)
    python tools/g6p70_texture_decode_check.py check          -> G6P70_CHECK PASS n/n      (the person's data, read only)
    python tools/g6p70_texture_decode_check.py bench --rev REV --runs N --out FILE (decode A/B, same inputs)

The viewer decodes with r3hd_level_scene.decode_stored (G6-P70); the reference is decode_stored_reference, i.e.
r3hd_mods.decode_level (the mod pipeline's decoder, unchanged) followed by the vertical flip the viewer used before.

selftest: decode_stored == reference on a seeded synthetic corpus (every power-of-two shape 4..256, both DXT1 colour
modes, both DXT5 alpha modes, equal endpoints, short / missing / extra rows and blocks, non-bytes rows, non-multiple-
of-4 sides); independent expected pixels for hand-built blocks (channel order, interpolation, transparent index,
both alpha palettes, storage row order); synthetic bundles through Scene.decode_texture (linear mip chain, the
G6-P68 packed 16 x 16 base, truncated data) equal the reference path; unsupported shapes and format / size mismatches
still raise LAYOUT, missing bundles / entries TEXTURE_MISSING; the per-Scene bundle index keeps the first entry of a
name, does not cache a read error, and is owned by the Scene (a new Scene sees a changed bundle; no module cache).

make-oracle: every drawn texture of every catalogued view level decoded by the code in DIR at max_side 256 (sha256,
length, size, format); the representative levels and every packed-tail record also at 32 with the exact bytes (zlib).
Pixels stay under private/. check: the person's level files are the oracle's; every oracle record matches (exact bytes
where kept, hash / length / size otherwise; errors stay errors); every drawn texture of the 58 levels decodes to the
exact bytes of the reference path; the game files are unchanged. bench: fresh Scene per run, every drawn texture,
REV's r3hd_level_scene.py against the working tree's, alternating, in separate processes; tracemalloc peak in a
separate pass. Statistics only.
"""
import argparse
import gc
import hashlib
import json
import os
import random
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
CODE = os.environ.get("G6P70_CODE_DIR")
if CODE:                                          # a mutated copy / another code version is imported first
    sys.path.insert(0, CODE)
sys.path.insert(1 if CODE else 0, str(TOOLS))
import r3hd_level_scene as ls  # noqa: E402
import r3hd_mods as rm  # noqa: E402

WORK = ROOT / "private" / "work" / "g6p70"
ORACLE = WORK / "oracle"
REPRESENTATIVE = ("wood_11", "moor_00", "sk8_00", "ten_map", "menumap")


def sha_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def view_levels():
    cat = json.loads((TOOLS / "r3hd_view_levels.json").read_text(encoding="utf-8"))["levels"]
    return sorted(k for k, v in cat.items() if v["class"] == "view")


def catalog_textures():
    """Texture records of the view levels as measured in the catalog (1,726; G6-P68's 1,727 includes an excluded page)."""
    cat = json.loads((TOOLS / "r3hd_view_levels.json").read_text(encoding="utf-8"))["levels"]
    return sum(v["measured"]["textures"] for v in cat.values() if v["class"] == "view")


def game_dir():
    import r3hd_level_editor_core as core
    return Path(core.mod_paths()["game"])


def drawn_keys(scene):
    """Texture keys of the viewer's drawn batches, in batch order (as r3hd_scene_gl.Prepared decodes them)."""
    import r3hd_scene_gl as sg
    p = sg.Prepared.__new__(sg.Prepared)
    p.groups, p.boxes, p.textures, p.hidden_runtime_placed, p.max_side, p.shade = {}, {}, {}, 0, 256, True
    p._expand(scene, lambda: False)
    out = []
    for key in p.groups:
        if key[0] is not None and key[0] not in out:
            out.append(key[0])
    return out


def reference_decode(scene, key, max_side=256):
    """Scene.decode_texture with the pre-G6-P70 decoder (the same mip / offset logic, reference pixels)."""
    fast = ls.decode_stored
    ls.decode_stored = ls.decode_stored_reference
    try:
        return scene.decode_texture(key, max_side)
    finally:
        ls.decode_stored = fast


# --------------------------------------------------------------------------------------------------------- selftest
def _bhf(entries):
    """Bundle header bytes: [(name, s1, o1, s2, o2)]."""
    out = struct.pack(">I", len(entries))
    for name, s1, o1, s2, o2 in entries:
        out += struct.pack(">4I", s1, o1, s2, o2) + name.encode("latin1").ljust(0x114 - 16, b"\0")
    return out


def _scene(bundle, textures):
    s = ls.Scene.__new__(ls.Scene)
    s.textures = textures
    s.bundles = {1: bundle}
    return s


def selftest() -> int:
    R = []

    def check(name, cond):
        R.append((name, bool(cond)))
        print(f"{'PASS' if cond else 'FAIL'} {name}")

    rnd = random.Random(556)
    # S1 corpus equivalence
    n = bad = 0
    sides = (4, 8, 16, 32, 64, 128, 256)
    for fmt in ("DXT1", "DXT5"):
        bpb = 16 if fmt == "DXT5" else 8
        for w in sides:
            for h in sides:
                if w * h > 128 * 256:
                    continue
                nbx, nby = w // 4, h // 4
                rows = [bytes(rnd.getrandbits(8) for _ in range(nbx * bpb)) for _ in range(nby)]
                rows = [bytes(r) for r in rows]
                for j in range(0, nby, 2):                    # equal / reversed endpoints, equal / reversed alpha ends
                    r = bytearray(rows[j])
                    r[bpb - 8:bpb - 4] = r[bpb - 6:bpb - 4] * 2 if j % 4 else bytes((1, 0, 2, 0))
                    if fmt == "DXT5":
                        r[0:2] = bytes((5, 5)) if j % 4 else bytes((0, 255))
                    rows[j] = bytes(r)
                for v in (rows, rows[:max(nby // 2, 1)], rows + rows[:1], [rows[0][:bpb * 2 + 5]] + rows[1:],
                          [memoryview(rows[0])] + rows[1:]):
                    n += 1
                    bad += ls.decode_stored(w, h, v, fmt) != ls.decode_stored_reference(w, h, v, fmt)
    for fmt in ("DXT1", "DXT5"):                              # sides that take the reference path
        for w, h in ((6, 6), (2, 4), (12, 3), (1, 1)):
            bpb = 16 if fmt == "DXT5" else 8
            rows = [bytes(rnd.getrandbits(8) for _ in range(((w + 3) // 4) * bpb)) for _ in range((h + 3) // 4)]
            n += 1
            bad += ls.decode_stored(w, h, rows, fmt) != ls.decode_stored_reference(w, h, rows, fmt)
    check(f"S1 decode_stored == reference on {n} synthetic levels (shapes 4..256, both modes, short / extra rows)",
          bad == 0 and n == 2 * (sum(1 for w in sides for h in sides if w * h <= 128 * 256) * 5 + 4))

    # S2 independent expected pixels (not derived from either decoder)
    row = 0b11100100                                           # texel indices 0, 1, 2, 3 in every texel row
    four = struct.pack("<HH", 0xF800, 0x001F) + bytes([row] * 4)
    three = struct.pack("<HH", 0x001F, 0xF800) + bytes([row] * 4)
    got4 = ls.decode_stored(4, 4, [four], "DXT1")
    got3 = ls.decode_stored(4, 4, [three], "DXT1")
    want4 = bytes((255, 0, 0, 255, 0, 0, 255, 255, 170, 0, 85, 255, 85, 0, 170, 255)) * 4
    want3 = bytes((0, 0, 255, 255, 255, 0, 0, 255, 127, 0, 127, 255, 0, 0, 0, 0)) * 4
    check("S2a DXT1 four-colour block: R, G, B, A order and 2/3 - 1/3 interpolation", got4 == want4)
    check("S2b DXT1 three-colour block (c0 <= c1): midpoint and transparent black", got3 == want3)
    abits = sum((t % 8) << (3 * t) for t in range(16))       # texel t uses alpha index t % 8
    a8 = bytes((255, 0)) + abits.to_bytes(6, "little") + four
    a6 = bytes((0, 255)) + abits.to_bytes(6, "little") + three
    pal8 = (255, 0, 219, 182, 146, 109, 73, 36)
    pal6 = (0, 255, 51, 102, 153, 204, 0, 255)
    g8, g6 = ls.decode_stored(4, 4, [a8], "DXT5"), ls.decode_stored(4, 4, [a6], "DXT5")
    check("S2c DXT5 eight-alpha block: alpha palette per texel, colour always four-colour",
          bytes(g8[3::4]) == bytes(pal8[t % 8] for t in range(16))
          and bytes(b for i, b in enumerate(g8) if i % 4 != 3) == bytes(b for i, b in enumerate(want4) if i % 4 != 3))
    check("S2d DXT5 six-alpha block (a0 <= a1): 0 and 255 entries; three-colour endpoints read as four-colour",
          bytes(g6[3::4]) == bytes(pal6[t % 8] for t in range(16)) and g6[8:11] == bytes((85, 0, 170)))
    red = struct.pack("<HHI", 0xF800, 0xF800, 0)
    blue = struct.pack("<HHI", 0x001F, 0x001F, 0)
    st = ls.decode_stored(8, 8, [red + blue, blue + red], "DXT1")
    check("S2e storage order: texel row r is block row r // 4, blocks left to right",
          st[0:4] == bytes((255, 0, 0, 255)) and st[16:20] == bytes((0, 0, 255, 255))
          and st[4 * 32:4 * 32 + 4] == bytes((0, 0, 255, 255)) and len(st) == 8 * 8 * 4)
    check("S2f a missing block decodes to zero texels (as the reference)",
          ls.decode_stored(8, 4, [red], "DXT1")[16:32] == bytes(16)
          and ls.decode_stored(8, 4, [b""], "DXT5") == bytes(8 * 4 * 4))

    # S3 synthetic bundles through Scene.decode_texture
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        base, mips, _ = rm.layout(64, 64, "DXT1")
        base5, mips5, _ = rm.layout(64, 32, "DXT5")
        tail1, tail5 = ls.packed_base_tile(16, 16, "DXT1"), ls.packed_base_tile(16, 16, "DXT5")
        blobs = [bytes(rnd.getrandbits(8) for _ in range(s)) for s in (base, mips, base5, mips5, tail1, tail5)]
        entries, data, off = [], b"", 0
        for name, (s1, s2) in (("lin", (base, mips)), ("lin5", (base5, mips5)), ("pk", (tail1, 0)), ("pk5", (tail5, 0))):
            entries.append((name + ".dds", s1, off, s2, off + s1))
            off += s1 + s2
        data = blobs[0] + blobs[1] + blobs[2] + blobs[3] + blobs[4] + blobs[5]
        entries += [("lin.dds", 8, 0, 8, 0),                  # a later duplicate name (first one wins)
                    ("tiny.dds", 64, 0, 0, 0), ("wrong.dds", base, 0, mips, base), ("pkbad.dds", tail1 - 256, 0, 0, 0),
                    ("tiny8.dds", tail1, 0, 0, 0)]                # an 8 x 8 record on a tail-page-sized entry
        (d / "t_2.bhf").write_bytes(_bhf(entries))
        (d / "t_2.btf").write_bytes(data)
        tex = {}
        for i, (nm, w, h, fmt) in enumerate((("lin", 64, 64, "DXT1"), ("lin5", 64, 32, "DXT5"), ("pk", 16, 16, "DXT1"),
                                             ("pk5", 16, 16, "DXT5"), ("tiny", 8, 8, "DXT1"), ("wrong", 64, 64, "DXT5"),
                                             ("pkbad", 16, 16, "DXT1"), ("absent", 64, 64, "DXT1"),
                                             ("tiny8", 8, 8, "DXT1"))):
            tex[(1, i)] = {"name": nm + ".tga", "file": 1, "record": i, "width": w, "height": h, "format": fmt}
        s = _scene(d / "t_2.bhf", tex)
        ok = all(s.decode_texture((1, i), ms) == reference_decode(s, (1, i), ms) for i in range(4) for ms in (256, 32, 8))
        sizes = [s.decode_texture((1, i))[:2] for i in range(4)]
        check("S3a linear chains (DXT1 64x64, DXT5 64x32) and G6-P68 packed 16x16 bases equal the reference path",
              ok and sizes == [(64, 64), (64, 32), (16, 16), (16, 16)])
        lowmip = s.decode_texture((1, 0), 16)
        check("S3b mip selection unchanged (max_side 16 on a 64x64 chain -> 32x32: smaller levels are in the packed "
              "tail and skipped)", lowmip[:2] == (32, 32)
              and lowmip == reference_decode(s, (1, 0), 16))

        def code(i):
            try:
                s.decode_texture((1, i))
                return None
            except ls.SceneError as x:
                return x.code
        check("S3c unsupported 8x8 bases (also on a tail-page-sized entry), DXT5 record on DXT1 sizes, short packed "
              "page: LAYOUT; absent entry: TEXTURE_MISSING", [code(i) for i in (4, 8, 5, 6, 7)]
              == ["LAYOUT", "LAYOUT", "LAYOUT", "LAYOUT", "TEXTURE_MISSING"])
        s2 = _scene(d / "nope_2.bhf", {(1, 0): tex[(1, 0)]})
        try:
            s2.decode_texture((1, 0))
            miss = None
        except ls.SceneError as x:
            miss = x.code
        check("S3d missing bundle: TEXTURE_MISSING", miss == "TEXTURE_MISSING")
        (d / "t_2.btf").write_bytes(data[:base // 3])          # truncated data: zero texels exactly as before
        s3 = _scene(d / "t_2.bhf", tex)
        tr = s3.decode_texture((1, 0), 64)
        check("S3e truncated data decodes like the reference (missing blocks zero)",
              tr == reference_decode(s3, (1, 0), 64) and tr[2].endswith(bytes(64)))
        (d / "t_2.btf").write_bytes(data)

        # S4 the per-Scene bundle index
        idx = s.__dict__.get("_bundle_index", {})
        check("S4a first entry of a duplicated name wins (as the former linear search)",
              idx.get(d / "t_2.bhf", {}).get("lin.dds", (None, 0))[1] == base)
        (d / "t_2.bhf").write_bytes(_bhf([("lin.dds", 8, 0, 8, 0)]))
        fresh = _scene(d / "t_2.bhf", tex)
        try:
            fresh.texture_entry((1, 0))
            changed = None
        except ls.SceneError as x:
            changed = x.code
        globals_dicts = [k for k, v in vars(ls).items() if isinstance(v, dict) and len(v) > 0 and not k.startswith("__")]
        check("S4b the index is the Scene's own: a new Scene reads the changed bundle; no module-level cache",
              changed == "LAYOUT" and "_bundle_index" not in vars(ls.Scene) and globals_dicts == ["BLEND_MODES"])
        s4 = _scene(d / "t_2.bhf", {(1, 0): tex[(1, 0)]})     # the bundle read fails (a sharing violation, say)
        real = ls.rm.bhf_entries

        def failing(path):
            raise PermissionError(13, "simulated read failure", str(path))
        errs = []
        ls.rm.bhf_entries = failing
        try:
            for _ in range(2):
                try:
                    s4.texture_entry((1, 0))
                except ls.SceneError as x:
                    errs.append(x.code)
                except OSError as x:
                    errs.append(type(x).__name__)
        finally:
            ls.rm.bhf_entries = real
        check("S4c an unreadable bundle stays an error on every call (not cached as empty)",
              len(errs) == 2 and errs[0] == errs[1] and errs[0] != "TEXTURE_MISSING"
              and not s4.__dict__.get("_bundle_index"))
    passed = sum(ok for _, ok in R)
    print(f"G6P70_SELFTEST {'PASS' if passed == len(R) else 'FAIL'} {passed}/{len(R)}")
    return 0 if passed == len(R) else 1


# --------------------------------------------------------------------------------------------------------- oracle
def make_oracle(out: Path) -> int:
    game = game_dir()
    out.mkdir(parents=True, exist_ok=True)
    idx = {"code": str(Path(ls.__file__).resolve()), "sources": {"r3hd_level_scene.py": sha_file(ls.__file__),
           "r3hd_mods.py": sha_file(rm.__file__)}, "levels": {}, "records": []}
    n = 0
    for lv in view_levels():
        s = ls.Scene(game, lv)
        idx["levels"][lv] = s.hashes
        for k in drawn_keys(s):
            t = s.textures[k]
            packed = rm.layout(t["width"], t["height"], t["format"])[0] is None
            keep = lv in REPRESENTATIVE or packed
            for ms in ((256, 32) if keep else (256,)):
                rec = {"level": lv, "key": list(k), "name": t["name"], "fmt": t["format"],
                       "base": [t["width"], t["height"]], "max_side": ms, "packed": packed}
                try:
                    w, h, px = s.decode_texture(k, ms)
                except ls.SceneError as x:
                    rec["error"] = [x.code, x.detail]
                else:
                    rec.update(w=w, h=h, len=len(px), sha256=hashlib.sha256(px).hexdigest())
                    if keep:
                        rec["blob"] = f"{n:05d}.z"
                        (out / rec["blob"]).write_bytes(zlib.compress(px, 6))
                n += 1
                idx["records"].append(rec)
    (out / "index.json").write_text(json.dumps(idx, indent=0), encoding="utf-8")
    print(f"G6P70_ORACLE records={len(idx['records'])} blobs={sum('blob' in r for r in idx['records'])} "
          f"errors={sum('error' in r for r in idx['records'])}")
    return 0


def oracle_compare(levels=None, oracle=ORACLE):
    """(records compared, mismatch descriptions) of the code on sys.path against the frozen oracle."""
    idx = json.loads((oracle / "index.json").read_text(encoding="utf-8"))
    game = game_dir()
    bad, n, scenes = [], 0, {}
    for r in idx["records"]:
        if levels and r["level"] not in levels:
            continue
        s = scenes.get(r["level"])
        if s is None:
            scenes.clear()
            s = scenes[r["level"]] = ls.Scene(game, r["level"])
            if s.hashes != idx["levels"][r["level"]]:
                bad.append(f"{r['level']}: level files differ from the oracle's")
        n += 1
        k = tuple(r["key"])
        t = s.textures.get(k)
        if t is None or [t["name"], t["format"], t["width"], t["height"]] != [r["name"], r["fmt"], *r["base"]]:
            bad.append(f"{r['level']} {r['name']}: texture record differs")
            continue
        try:
            w, h, px = s.decode_texture(k, r["max_side"])
        except ls.SceneError as x:
            if r.get("error") != [x.code, x.detail]:
                bad.append(f"{r['level']} {r['name']}@{r['max_side']}: {x.code} (oracle {r.get('error')})")
            continue
        if "error" in r:
            bad.append(f"{r['level']} {r['name']}@{r['max_side']}: decoded, oracle {r['error'][0]}")
        elif (w, h, len(px)) != (r["w"], r["h"], r["len"]):
            bad.append(f"{r['level']} {r['name']}@{r['max_side']}: {w}x{h}/{len(px)} vs {r['w']}x{r['h']}/{r['len']}")
        elif "blob" in r and px != zlib.decompress((oracle / r["blob"]).read_bytes()):
            bad.append(f"{r['level']} {r['name']}@{r['max_side']}: bytes differ")
        elif hashlib.sha256(px).hexdigest() != r["sha256"]:
            bad.append(f"{r['level']} {r['name']}@{r['max_side']}: sha256 differs")
    return n, bad


def watched_files(game, levels):
    g = game / "GAMEDATAbin"
    files = {g / "fix.lvl", g / "fix.ptr", g / "fix.bhf", g / "fix.btf"}
    for lv in levels:
        files |= {p for p in (g / lv).glob("*") if p.suffix in (".lvl", ".ptr", ".bhf", ".btf")}
    return sorted(files)


def check() -> int:
    R = []

    def row(name, ok):
        R.append((name, bool(ok)))
        print(f"{'PASS' if ok else 'FAIL'} {name}", flush=True)

    game = game_dir()
    levels = view_levels()
    idx = json.loads((ORACLE / "index.json").read_text(encoding="utf-8"))
    watch = watched_files(game, levels)
    before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in watch}
    deep = [p for p in watch if p.parent.name in REPRESENTATIVE or p.parent.name == "GAMEDATAbin"]
    deep_before = {p: sha_file(p) for p in deep}
    row(f"C1 oracle covers the {len(levels)} catalogued view levels; made by HEAD-era sources "
        f"({idx['sources']['r3hd_level_scene.py'][:8]})", sorted(idx["levels"]) == levels)
    t = time.perf_counter()
    n, bad = oracle_compare()
    row(f"C2 frozen oracle: {n} records ({sum('blob' in r for r in idx['records'])} exact-byte, the rest sha256 + "
        f"size + length) match, errors identical ({time.perf_counter() - t:.0f} s){'; ' + '; '.join(bad[:5]) if bad else ''}",
        n == len(idx["records"]) and not bad)
    t = time.perf_counter()
    m, diff, texels, fmts = 0, [], 0, {}
    for lv in levels:
        s = ls.Scene(game, lv)
        for k in drawn_keys(s):
            m += 1
            a = s.decode_texture(k)
            if a != reference_decode(s, k):
                diff.append(f"{lv} {s.textures[k]['name']}")
            texels += a[0] * a[1]
            f = s.textures[k]["format"] + (" packed" if rm.layout(s.textures[k]["width"], s.textures[k]["height"],
                                                                   s.textures[k]["format"])[0] is None else "")
            fmts[f] = fmts.get(f, 0) + 1
    row(f"C3 live reference: {m} / {catalog_textures()} drawn textures of {len(levels)} levels ({texels} texels; "
        f"{fmts}) decode to the exact bytes of the reference path ({time.perf_counter() - t:.0f} s){'; ' + '; '.join(diff[:5]) if diff else ''}",
        m == catalog_textures() and not diff)
    after = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in watch}
    row(f"C4 game files unchanged ({len(watch)} size / time; {len(deep)} sha256)",
        before == after and all(sha_file(p) == h for p, h in deep_before.items()))
    passed = sum(ok for _, ok in R)
    print(f"G6P70_CHECK {'PASS' if passed == len(R) else 'FAIL'} {passed}/{len(R)}")
    return 0 if passed == len(R) else 1


# --------------------------------------------------------------------------------------------------------- mutations
MUTATIONS = [
    ("U1 channel order (R and B swapped)", "bytes((r0, g0, b0, 255))", "bytes((b0, g0, r0, 255))"),
    ("U2 wrong block offset in a row", "rows = [raw[area + j * pitch:area + j * pitch + ((lw + 3) // 4) * bpb]",
     "rows = [raw[area + j * pitch + bpb:area + j * pitch + bpb + ((lw + 3) // 4) * bpb]"),
    ("U3 wrong row pitch", "rows = [raw[area + j * pitch:area + j * pitch + ((lw + 3) // 4) * bpb]",
     "rows = [raw[area + j * (pitch + 256):area + j * (pitch + 256) + ((lw + 3) // 4) * bpb]"),
    ("U4 texel rows swapped inside a block", "lines += (join(p0), pad, join(p1), pad,",
     "lines += (join(p1), pad, join(p0), pad,"),
    ("U5 truncated data", "            raw = rm.swap16(fh.read(size))\n", "            raw = rm.swap16(fh.read(size // 2))\n"),
    ("U6 wrong packed-tail offset", "x, y = rm.packed_mip_offset(w, h, 0)", "x, y = rm.packed_mip_offset(w, h, 1)"),
    ("U7 wrong mip selection", "                pick = i  ", "                pick = max(i - 1, 0)  "),
    ("U8 DXT5 colour read in DXT1 three-colour mode", "_colour_palette(k, dxt5)", "_colour_palette(k, False)"),
    ("U9 record format substituted", '"format": "DXT5" if flags & 0x8 else "DXT1"', '"format": "DXT1" if flags & 0x8 else "DXT5"'),
    ("U10 alpha bits of the last texel row", "ai[bits >> 36]", "ai[(bits >> 35) & 4095]"),
    ("U11 alpha palette mode boundary", "    if a0 > a1:\n        pal = [a0, a1]", "    if a0 >= a1:\n        pal = [a0, a1]"),
    ("U12 missing blocks not zero-filled", "        pad = bytes(16 * (nbx - n))\n", "        pad = b''\n"),
    ("U13 last duplicate bundle entry wins", "names.setdefault(e[0].lower(), e)", "names[e[0].lower()] = e"),
    ("U14 module-wide bundle index", 'index = self.__dict__.setdefault("_bundle_index", {})',
     'index = vars(Scene).get("_bundle_index") or (setattr(Scene, "_bundle_index", {}) or Scene._bundle_index)'),
    ("U15 unsupported shape accepted as packed", "if (w, h) != (16, 16) or fmt not in", "if fmt not in"),
    ("U16 DXT5 alpha not applied", "    buf[3::4] = join(alpha)\n", "    buf[3:3] = b''\n"),
    ("U17 read error cached as an empty bundle", "            names = {}\n            for e in rm.bhf_entries(bhf):",
     "            names = index[bhf] = {}\n            for e in rm.bhf_entries(bhf):"),
]


def _run(args, code_dir, timeout=900):
    env = dict(os.environ, G6P70_CODE_DIR=str(code_dir), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, str(Path(__file__).resolve()), *args], env=env, capture_output=True,
                          text=True, timeout=timeout)


def mutations() -> int:
    src = (TOOLS / "r3hd_level_scene.py").read_text(encoding="utf-8")
    have_oracle = (ORACLE / "index.json").is_file()
    R = []
    for name, old, new in MUTATIONS:
        if src.count(old) < 1:
            R.append((name, False, "anchor not found"))
            print(f"FAIL {name}: anchor not found")
            continue
        with tempfile.TemporaryDirectory() as d:
            mutant = src.replace(old, new)
            (Path(d) / "r3hd_level_scene.py").write_text(mutant, encoding="utf-8")
            try:
                compile(mutant, "mutant", "exec")
            except SyntaxError as x:
                R.append((name, False, f"mutant does not compile ({x})"))
                print(f"FAIL {name}: mutant does not compile")
                continue
            how = []
            if _run(["--selftest"], d).returncode != 0:
                how.append("selftest")
            if have_oracle and _run(["_oracle-rep"], d).returncode != 0:
                how.append("oracle")
        R.append((name, bool(how), "+".join(how) or "NOT caught"))
        print(f"{'PASS' if how else 'FAIL'} {name}: caught by {'+'.join(how) or 'nothing'}", flush=True)
    passed = sum(ok for _, ok, _ in R)
    print(f"G6P70_MUTATIONS {'PASS' if passed == len(R) else 'FAIL'} {passed}/{len(R)}"
          f"{'' if have_oracle else ' (no private oracle: selftest only)'}")
    return 0 if passed == len(R) else 1


def oracle_rep() -> int:
    n, bad = oracle_compare(set(REPRESENTATIVE))
    print(f"oracle (representative) {n} records, {len(bad)} mismatches")
    return 0 if n and not bad else 1


# --------------------------------------------------------------------------------------------------------- bench
def bench_worker(levels, runs, out: Path) -> int:
    """One code version (the one on sys.path): per level, fresh Scene per run, decode every drawn texture."""
    import tracemalloc
    game = game_dir()
    res = {"code": str(Path(ls.__file__).resolve()), "sha256": sha_file(ls.__file__), "levels": {}}
    for lv in levels:
        keys = drawn_keys(ls.Scene(game, lv))
        times, digest = [], None
        for _ in range(runs):
            s = ls.Scene(game, lv)
            gc.collect()
            t = time.perf_counter()
            px = [s.decode_texture(k) for k in keys]
            times.append(time.perf_counter() - t)
            h = hashlib.sha256()
            for w_, h_, b in px:
                h.update(struct.pack("<II", w_, h_) + b)
            digest = digest or h.hexdigest()
            if digest != h.hexdigest():
                raise SystemExit("nondeterministic decode")
            del px, s
        s = ls.Scene(game, lv)
        gc.collect()
        tracemalloc.start()
        px = [s.decode_texture(k) for k in keys]
        cur, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        res["levels"][lv] = {"textures": len(keys), "seconds": [round(x, 4) for x in times],
                             "median": round(statistics.median(times), 4), "min": round(min(times), 4),
                             "max": round(max(times), 4), "output_mib": round(sum(len(b) for _, _, b in px) / 2**20, 2),
                             "traced_retained_mib": round(cur / 2**20, 2), "traced_peak_mib": round(peak / 2**20, 2),
                             "digest": digest}
        del px, s
    out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    return 0


def bench(rev, runs, rounds, levels, out: Path) -> int:
    with tempfile.TemporaryDirectory() as d:
        old = Path(d) / "old"
        old.mkdir()
        (old / "r3hd_level_scene.py").write_bytes(
            subprocess.check_output(["git", "-C", str(ROOT), "show", f"{rev}:tools/r3hd_level_scene.py"]))
        both = {"before": [], "after": []}
        for i in range(rounds):                         # alternating processes, same inputs
            for tag, code in (("before", old), ("after", TOOLS)):
                f = Path(d) / f"{tag}_{i}.json"
                p = _run(["_bench", "--levels", ",".join(levels), "--runs", str(runs), "--out", str(f)], code, 3600)
                if p.returncode:
                    print(p.stdout, p.stderr)
                    return 1
                both[tag].append(json.loads(f.read_text(encoding="utf-8")))
    summary = {"rev": rev, "runs_per_process": runs, "processes": rounds, "levels": {}}
    for lv in levels:
        b = [x for r in both["before"] for x in r["levels"][lv]["seconds"]]
        a = [x for r in both["after"] for x in r["levels"][lv]["seconds"]]
        same = {r["levels"][lv]["digest"] for r in both["before"] + both["after"]}
        summary["levels"][lv] = {
            "textures": both["after"][0]["levels"][lv]["textures"],
            "before_median": round(statistics.median(b), 3), "before_range": [min(b), max(b)],
            "after_median": round(statistics.median(a), 3), "after_range": [min(a), max(a)],
            "speedup": round(statistics.median(b) / statistics.median(a), 2), "identical_output": len(same) == 1,
            "traced_peak_mib": [both["before"][0]["levels"][lv]["traced_peak_mib"],
                                both["after"][0]["levels"][lv]["traced_peak_mib"]],
            "traced_retained_mib": [both["before"][0]["levels"][lv]["traced_retained_mib"],
                                    both["after"][0]["levels"][lv]["traced_retained_mib"]],
            "output_mib": both["after"][0]["levels"][lv]["output_mib"]}
        print(lv, json.dumps(summary["levels"][lv]))
    summary["sources"] = {"before": both["before"][0]["sha256"], "after": both["after"][0]["sha256"]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "raw": both}, indent=1), encoding="utf-8")
    ok = all(v["identical_output"] for v in summary["levels"].values())
    print(f"G6P70_BENCH {'PASS' if ok else 'FAIL'} identical output on {len(levels)} levels")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", nargs="?", choices=("check", "make-oracle", "bench", "_oracle-rep", "_bench"))
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mutations", action="store_true")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--rev", default="b00cb95")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--levels", default=",".join(REPRESENTATIVE))
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.mutations:
        return mutations()
    if a.cmd == "check":
        return check()
    if a.cmd == "make-oracle":
        return make_oracle(a.out or ORACLE)
    if a.cmd == "_oracle-rep":
        return oracle_rep()
    if a.cmd == "_bench":
        return bench_worker(a.levels.split(","), a.runs, a.out)
    if a.cmd == "bench":
        return bench(a.rev, a.runs, a.rounds, a.levels.split(","), a.out or WORK / "bench.json")
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
