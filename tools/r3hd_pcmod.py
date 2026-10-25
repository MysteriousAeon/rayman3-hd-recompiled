#!/usr/bin/env python3
"""M34: converts original-PC Rayman 3 texture mods (Rayman Control Panel packages of `.gf` textures) into format-1
data mods of this port (tools/r3hd_mods.py). A proof of concept for one category of PC mods, not general compatibility.

Source: an RCP mod folder or .zip: `metadata.jsonc` (id, name, version, author, website ...; comments allowed) and
texture files under `.../<archive>.cnt/<dir>/<name>.gf` (e.g. files/added_files/Gamedatabin/tex32_1.cnt/charact/
rayman.gf). The HD bundles name their entries after the PC CNT paths, `<dir>\\<name>.dds` (RESEARCH "M33"), so each GF
maps to the HD entry of that name, in every bundle that holds it.

GF (Rayman 3 PC; RESEARCH "M34", from Raymap and RCP, both reference only): little-endian u32 format (8888, 888, 565, 1555,
4444, 88; 888 = three channels, M35), u32 width, u32 height, u8 channels (1-4), u8 mip levels, u8 repeat byte; with one channel a 256-entry BGRA
palette; then each channel's bytes in turn (base level and mips), run-length coded: the repeat byte is followed by a
value and a count. Three or four channels are B, G, R(, A); two channels are a 16-bit pixel of the format. Rows are
stored bottom row first.

Conversion of one texture: decode (bounded), turn upright, resize to the HD entry's exact size (fixed by the level's
texture record; bilinear up, area-average down), alpha from the source when it has one, else the HD entry's own
alpha (cut-outs stay), then the M33 encoder takes over at plan time (format, mips, console layout). The new mod
carries the original's name, version, authors and website, and its description says where it came from; the rights
stay with the original authors (and Ubisoft for derived art): convert only what you may use, do not redistribute
what you may not.

usage:
  r3hd_pcmod.py inspect SOURCE                    what the package holds and where each texture would go
  r3hd_pcmod.py convert SOURCE OUT [--id ID]      write the port's mod folder OUT (PNG + mod.json)
  r3hd_pcmod.py make-sample OUT.zip [--entry charact/rayman] [--size 256]   a synthetic RCP-shaped package with a
                                                  project-drawn GF (quadrant colours, an orientation mark), for tests
  r3hd_pcmod.py selftest
Common: --game-dir DIR, --json. Exit 0 ok, 2 refused.
"""
import argparse
import json
import os
import re
import stat
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_mods as rm  # noqa: E402

MAX_SIDE = 2048
MAX_PIXELS = 16 << 20   # all GF pixels of one package (M34 review: bounded work for untrusted input)
MAX_MEMBERS = 8192
MAX_MEMBER = 64 << 20
MAX_TOTAL = 512 << 20
GF_RE = re.compile(r"(?i)^(?:.*/)?[^/]+\.cnt/((?:[A-Za-z0-9_ .-]+/){1,4})([A-Za-z0-9_ .-]+)\.gf$")


class Refused(Exception):
    pass


# ---------------------------------------------------------------------------------------------------------------
# GF

def gf_decode(data: bytes):
    """GF bytes -> (width, height, upright RGBA bytes, has_alpha, info). Every size is checked before use."""
    if len(data) < 15:
        raise Refused("GF: too short")
    fmt, w, h, ch, mips, rep = struct.unpack_from("<IIIBBB", data, 0)
    if not (1 <= w <= MAX_SIDE and 1 <= h <= MAX_SIDE) or ch not in (1, 2, 3, 4) or mips > 16:
        raise Refused(f"GF: unsupported header ({w}x{h}, {ch} channels, {mips} mip levels)")
    if fmt not in (8888, 888, 565, 1555, 4444, 88):
        raise Refused(f"GF: unknown pixel format {fmt}")
    if fmt == 888 and ch != 3:   # M35: 24-bit B, G, R planes, seen in a real RCP package (RESEARCH M35)
        raise Refused(f"GF: format 888 with {ch} channels")
    pos = 15
    count = w * h
    if mips > 1:
        lw, lh = w, h
        for _ in range(mips - 1):
            lw, lh = max(lw >> 1, 1), max(lh >> 1, 1)
            count += lw * lh
    palette = None
    if ch == 1:
        palette = data[pos:pos + 1024]
        if len(palette) != 1024:
            raise Refused("GF: truncated palette")
        pos += 1024
    planes = bytearray(ch * count)
    for c in range(ch):
        i = 0
        while i < count:
            if pos >= len(data):
                raise Refused("GF: truncated pixel data")
            b = data[pos]
            pos += 1
            if b == rep:
                if pos + 2 > len(data):
                    raise Refused("GF: truncated run")
                v, n = data[pos], data[pos + 1]
                pos += 2
                if i + n > count:
                    raise Refused("GF: a run passes the end of the channel")
                planes[c + i * ch:c + (i + n) * ch:ch] = bytes([v]) * n
                i += n
            else:
                planes[c + i * ch] = b
                i += 1
    if pos != len(data):
        raise Refused(f"GF: {len(data) - pos} bytes after the pixel data")
    out = bytearray(w * h * 4)
    alpha = False
    for i in range(w * h):
        p = planes[i * ch:(i + 1) * ch]
        if ch >= 3:
            r, g, b, a = p[2], p[1], p[0], (p[3] if ch == 4 else 255)
        elif ch == 2:
            v = p[0] | p[1] << 8
            if fmt == 4444:
                a, r, g, b = (v >> 12) * 17, (v >> 8 & 15) * 17, (v >> 4 & 15) * 17, (v & 15) * 17
            elif fmt == 1555:
                a, r, g, b = (255 if v >> 15 else 0), (v >> 10 & 31) * 255 // 31, (v >> 5 & 31) * 255 // 31, (v & 31) * 255 // 31
            elif fmt == 88:
                r = g = b = p[0]
                a = p[1]
            else:
                a, r, g, b = 255, (v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31
        else:
            k = p[0] * 4
            b, g, r, a = palette[k], palette[k + 1], palette[k + 2], palette[k + 3]
        alpha |= a != 255
        # stored bottom row first: pixel i is row h-1-(i // w) of the upright picture
        y, x = h - 1 - i // w, i % w
        out[(y * w + x) * 4:(y * w + x) * 4 + 4] = bytes((r, g, b, a))
    has_alpha = ch == 4 or (ch == 2 and fmt in (4444, 1555, 88)) or (ch == 1 and alpha)
    return w, h, bytes(out), has_alpha, {"format": fmt, "width": w, "height": h, "channels": ch, "mip_levels": mips}


def gf_encode(w: int, h: int, rgba: bytes, channels=3, rep=0xA5) -> bytes:
    """Upright RGBA -> GF (8888, no mips), for synthetic test packages only."""
    planes = [bytearray() for _ in range(channels)]
    for i in range(w * h):
        y, x = h - 1 - i // w, i % w
        r, g, b, a = rgba[(y * w + x) * 4:(y * w + x) * 4 + 4]
        for c, v in enumerate((b, g, r, a)[:channels]):
            planes[c].append(v)
    out = bytearray(struct.pack("<IIIBBB", 8888, w, h, channels, 1, rep))
    for p in planes:
        i = 0
        while i < len(p):
            n = 1
            while i + n < len(p) and p[i + n] == p[i] and n < 255:
                n += 1
            if n >= 4 or p[i] == rep:
                out += bytes((rep, p[i], n))
                i += n
            else:
                out.append(p[i])
                i += 1
    return bytes(out)


# ---------------------------------------------------------------------------------------------------------------
# Pictures

def resize(w, h, rgba, nw, nh):
    """Bilinear when growing, area average when shrinking (per axis), on straight RGBA."""
    if (w, h) == (nw, nh):
        return rgba

    def axis(n_src, n_dst):
        # for every destination index: list of (source index, weight)
        out = []
        if n_dst >= n_src:
            for i in range(n_dst):
                s = (i + 0.5) * n_src / n_dst - 0.5
                s0 = max(int(s // 1), 0)
                f = min(max(s - s0, 0.0), 1.0)
                s1 = min(s0 + 1, n_src - 1)
                out.append([(s0, 1 - f), (s1, f)])
        else:
            r = n_src / n_dst
            for i in range(n_dst):
                lo, hi = i * r, (i + 1) * r
                ws = []
                j = int(lo)
                while j < hi and j < n_src:
                    ws.append((j, min(hi, j + 1) - max(lo, j)))
                    j += 1
                t = sum(x[1] for x in ws)
                out.append([(j, wgt / t) for j, wgt in ws])
        return out
    ax, ay = axis(w, nw), axis(h, nh)
    tmp = [0.0] * (nw * h * 4)
    for y in range(h):
        for x in range(nw):
            for c in range(4):
                tmp[(y * nw + x) * 4 + c] = sum(rgba[(y * w + sx) * 4 + c] * f for sx, f in ax[x])
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        for x in range(nw):
            for c in range(4):
                v = sum(tmp[(sy * nw + x) * 4 + c] * f for sy, f in ay[y])
                out[(y * nw + x) * 4 + c] = min(255, max(0, int(v + 0.5)))
    return bytes(out)


# ---------------------------------------------------------------------------------------------------------------
# Packages

def strip_jsonc(text: str) -> str:
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def read_source(src: Path):
    """{relative path: bytes} of the metadata and the GF files of an RCP package (folder or zip), read in memory with
    the M33 package limits; other members are listed, never read."""
    files, skipped, total = {}, [], 0
    st = os.lstat(src)
    if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & 0x400:
        raise Refused("the source is a link")

    def want(rel):
        low = rel.lower()
        return low.endswith(".gf") or low.split("/")[-1] == "metadata.jsonc"
    if stat.S_ISDIR(st.st_mode):
        for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
            for name in dirnames + filenames:
                s = os.lstat(Path(dirpath) / name)
                if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
                    raise Refused(f"links are not allowed: {name}")
            for name in filenames:
                p = Path(dirpath) / name
                rel = p.relative_to(src).as_posix()
                if not want(rel):
                    skipped.append(rel)
                    continue
                if p.stat().st_size > MAX_MEMBER:
                    raise Refused(f"{rel} is too large")
                total += p.stat().st_size
                if total > MAX_TOTAL or len(files) >= MAX_MEMBERS:
                    raise Refused("the package is too large")
                files[rel] = p.read_bytes()
    elif stat.S_ISREG(st.st_mode) and src.suffix.lower() == ".zip":
        with zipfile.ZipFile(src) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_MEMBERS:
                raise Refused("too many entries")
            for info in infos:
                rel = info.filename
                if rel.endswith("/"):
                    continue
                if "\\" in rel or rel.startswith("/") or ":" in rel or ".." in rel.split("/") \
                        or ((info.external_attr >> 16) & 0o170000) == stat.S_IFLNK or info.flag_bits & 1:
                    raise Refused(f"member not allowed: {rel!r}")
                if not want(rel):
                    skipped.append(rel)
                    continue
                if info.file_size > MAX_MEMBER or (info.file_size > (1 << 20)
                                                   and info.file_size > 100 * max(info.compress_size, 1)):
                    raise Refused(f"{rel} is too large or expands too much")
                total += info.file_size
                if total > MAX_TOTAL:
                    raise Refused("the package is too large")
                with zf.open(info) as f:
                    data = f.read(MAX_MEMBER + 1)
                if len(data) != info.file_size:
                    raise Refused(f"{rel}: size does not match its header")
                files[rel] = data
    else:
        raise Refused("choose an RCP mod folder or .zip")
    return files, skipped


def metadata(files):
    meta = [r for r in files if r.lower().split("/")[-1] == "metadata.jsonc"]
    if len(meta) != 1:
        raise Refused("no single metadata.jsonc (not a Rayman Control Panel mod)")
    try:
        m = json.loads(strip_jsonc(files[meta[0]].decode("utf-8-sig")))
    except (UnicodeDecodeError, ValueError) as x:
        raise Refused(f"metadata.jsonc: {x}")
    if not isinstance(m, dict):
        raise Refused("metadata.jsonc is not an object")
    return m


def text_of(v, limit):
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v)
    return str(v)[:limit] if v not in (None, "") else None


def plan_textures(files, game: Path):
    """[(gf path, HD entry, hits or refusal)] for every GF of the package."""
    out = []
    for rel in sorted(r for r in files if r.lower().endswith(".gf")):
        m = GF_RE.match(rel)
        if not m:
            out.append((rel, None, "not under <archive>.cnt/<dir>/: no HD name"))
            continue
        entry = (m.group(1).replace("/", "\\") + m.group(2) + ".dds").lower()
        try:
            hits = rm.resolve_texture(game, {"entry": entry, "bundles": "all"})
            out.append((rel, entry, hits))
        except rm.Refusal as x:
            out.append((rel, entry, f"{x.code}: {x.detail}"))
    return out


def hd_alpha(hit):
    bhf, e, w, h, fmt = hit
    with open(bhf.with_suffix(".btf"), "rb") as f:
        f.seek(e[2])
        raw = f.read(e[1])
    lay = rm.layout(w, h, fmt)[2]
    return rm.decode_level(w, h, rm.level_rows((raw, b""), lay[0], fmt), fmt)


def cmd_inspect(paths, src: Path):
    files, skipped = read_source(src)
    meta = metadata(files)
    rows = []
    for rel, entry, hits in plan_textures(files, paths["game"]):
        row = {"gf": rel, "entry": entry}
        try:
            w, h, _, has_alpha, info = gf_decode(files[rel])
            row["source"] = info | {"alpha": has_alpha}
        except Refused as x:
            row["problem"] = str(x)
        if isinstance(hits, str):
            row["problem"] = row.get("problem") or hits
        else:
            hw, hh, fmt = hits[0][2], hits[0][3], hits[0][4]
            row["target"] = {"width": hw, "height": hh, "format": fmt, "bundles": len(hits)}
            if "source" in row:
                notes = []
                if row["source"]["width"] * hh != row["source"]["height"] * hw:
                    notes.append("aspect ratio differs from the HD texture")
                if has_alpha and fmt == "DXT1":
                    notes.append("the source's alpha becomes 1-bit (DXT1)")
                if not has_alpha:
                    notes.append("no alpha in the source: the HD texture's own alpha is kept")
                row["notes"] = notes
        rows.append(row)
    return {"mod": {k: meta.get(k) for k in ("id", "name", "version", "author", "website")}, "textures": rows,
            "ignored_files": len(skipped)}


def cmd_convert(paths, src: Path, out: Path, mod_id=None):
    files, skipped = read_source(src)
    meta = metadata(files)
    name = text_of(meta.get("name"), 60) or src.stem
    raw_id = mod_id or "pc." + re.sub(r"[^a-z0-9._-]+", "-", str(meta.get("id") or name).lower()).strip("-.")[:56]
    if not rm.ID_RE.match(raw_id):
        raise Refused(f"no usable mod id ({raw_id!r}); pass --id")
    version = str(meta.get("version") or "1.0.0")
    if not rm.VERSION_RE.match(version):
        version = "1.0.0"
    if out.exists() and any(out.iterdir()):
        raise Refused(f"{out} is not empty")
    overrides, report = [], []
    images = {}
    budget = MAX_PIXELS
    first = {}   # M35: an entry already converted (a real package holds the same picture in tex32_1 and tex32_2)
    for rel, entry, hits in plan_textures(files, paths["game"]):
        if isinstance(hits, str) or entry is None:
            report.append({"gf": rel, "skipped": hits})
            continue
        if entry in first:
            same = files[first[entry]] == files[rel]
            report.append({"gf": rel, "entry": entry, "same_as" if same else "skipped":
                           first[entry] if same else f"differs from {first[entry]}, which is used (one HD entry, one "
                           "picture)"})
            continue
        first[entry] = rel
        if len(files[rel]) >= 15:
            gw, gh = struct.unpack_from("<II", files[rel], 4)
            budget -= gw * gh
            if budget < 0:
                raise Refused(f"the package holds more than {MAX_PIXELS} texture pixels")
        try:
            w, h, rgba, has_alpha, info = gf_decode(files[rel])
        except Refused as x:
            report.append({"gf": rel, "skipped": str(x)})
            continue
        sizes = {(t[2], t[3]) for t in hits}
        if len(sizes) != 1:
            report.append({"gf": rel, "skipped": f"the HD copies differ in size {sorted(sizes)}"})
            continue
        tw, th = sizes.pop()
        pic = resize(w, h, rgba, tw, th)
        alpha_from = "source"
        if not has_alpha:
            own = hd_alpha(hits[0])
            pic = bytes(b for i in range(tw * th) for b in (pic[i * 4], pic[i * 4 + 1], pic[i * 4 + 2], own[i * 4 + 3]))
            alpha_from = "HD texture"
        png_rel = "textures/" + entry.replace("\\", "/")[:-4] + ".png"
        images[png_rel] = rm.write_png(tw, th, pic)
        overrides.append({"type": "texture", "entry": entry, "bundles": "all", "image": png_rel})
        report.append({"gf": rel, "entry": entry, "from": f"{w}x{h}", "to": f"{tw}x{th} {hits[0][4]}",
                       "bundles": len(hits), "alpha": alpha_from})
    if not overrides:
        raise Refused("no texture of the package maps to an HD texture")
    author = text_of(meta.get("author") or meta.get("authors"), 80)
    desc = (f"Converted from the PC Rayman 3 mod '{name}' (Rayman Control Panel package, "
            f"{len(overrides)} textures) by r3hd_pcmod.py. Rights stay with the original author(s).")
    m = {"format": 1, "id": raw_id, "name": name[:80], "version": version, "description": desc,
         "authors": [author] if author else [], "target": {"title_id": rm.TITLE_ID, "releases": rm.release_ids(paths),
                                                          "min_port_version": "0.33.0"},
         "overrides": overrides}
    if not m["authors"]:
        del m["authors"]
    for k in ("license", "website"):
        if text_of(meta.get(k), 200):
            m[k] = text_of(meta.get(k), 200)
    out.mkdir(parents=True, exist_ok=True)
    (out / "mod.json").write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for rel, data in images.items():
        p = out.joinpath(*rel.split("/"))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return {"mod": str(out), "id": raw_id, "textures": report, "ignored_files": len(skipped),
            "note": "the converted pictures carry the original mod's rights: keep them private unless you may share them"}


def sample_picture(n: int) -> bytes:
    """A project-drawn test picture: four quadrant colours (red top-left, blue top-right, green bottom-left, magenta
    bottom-right), a dark grid every n/8, and a white 'F' in the top-left quadrant that shows the orientation."""
    q = {(0, 0): (230, 40, 40), (1, 0): (40, 80, 240), (0, 1): (40, 210, 70), (1, 1): (220, 40, 220)}
    out = bytearray(n * n * 4)
    step = max(n // 8, 2)
    for y in range(n):
        for x in range(n):
            c = q[(x * 2 // n, y * 2 // n)]
            if x % step < max(n // 128, 1) or y % step < max(n // 128, 1):
                c = (20, 20, 20)
            u, v = x / n, y / n   # the F: a stem and two bars
            if 0.10 <= u <= 0.16 and 0.08 <= v <= 0.40 or 0.10 <= u <= 0.36 and 0.08 <= v <= 0.14 \
                    or 0.10 <= u <= 0.30 and 0.22 <= v <= 0.28:
                c = (250, 250, 250)
            out[(y * n + x) * 4:(y * n + x) * 4 + 4] = bytes(c) + b"\xff"
    return bytes(out)


def cmd_make_sample(out: Path, entry: str, size: int):
    if not re.fullmatch(r"[a-z0-9_]+/[a-z0-9_]+", entry) or not 8 <= size <= 1024:
        raise Refused("--entry dir/name (lower case), --size 8..1024")
    meta = ('{\n  // M34 synthetic test package in the Rayman Control Panel layout (project-drawn picture)\n'
            '  "id": "r3hd.m34-sample", "format": 1, "games": ["Rayman3_Win32"], "name": "M34 sample texture mod",\n'
            '  "description": "Quadrant colours and an F mark", "author": "Rayman 3 HD Recompiled project (test)",\n'
            '  "version": "1.0.0", "website": "", "archives": [],\n}\n')
    gf = gf_encode(size, size, sample_picture(size))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, data in (("metadata.jsonc", meta.encode()),
                          (f"files/added_files/Gamedatabin/tex32_1.cnt/{entry}.gf", gf)):
            zi = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zi, data)
    return {"out": str(out), "gf": f"tex32_1.cnt/{entry}.gf", "size": size, "gf_bytes": len(gf)}


# ---------------------------------------------------------------------------------------------------------------

def selftest() -> int:
    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ' :: ' + str(detail)}")

    def refused(fn):
        try:
            fn()
        except Refused:
            return True
        return False
    pic = sample_picture(32)
    for ch in (3, 4):
        w, h, back, has_alpha, info = gf_decode(gf_encode(32, 32, pic, channels=ch))
        check(f"gf: {ch}-channel round trip (RLE, upright)", (w, h) == (32, 32) and back == pic and has_alpha == (ch == 4))
    # orientation: stored bottom row first
    tall = bytes([255, 0, 0, 255] * 4 + [0, 0, 255, 255] * 4)   # 4x2: red top row, blue bottom row
    g = gf_encode(4, 2, tall)
    check("gf: the first stored row is the picture's bottom row", g[15:19] == bytes([255] * 4) and g[19:23] == bytes([0] * 4)
          or g[15] == 0xA5 and g[16] == 255, g[15:24].hex())
    check("gf: decode puts it back upright", gf_decode(g)[2] == tall)
    # a GF holding the repeat byte as a value
    lit = bytes([0xA5, 0xA5, 0xA5, 255] * 4)
    check("gf: the repeat byte as a pixel value survives", gf_decode(gf_encode(2, 2, lit, channels=3))[2] == lit)
    # palette (1 channel) and 565 / 4444 two-channel pixels
    pal = bytearray(1024)
    pal[4:8] = bytes((10, 20, 30, 128))
    one = struct.pack("<IIIBBB", 8888, 2, 1, 1, 1, 0xA5) + bytes(pal) + bytes((1, 0))
    w, h, px, ha, _ = gf_decode(one)
    check("gf: 1 channel through a BGRA palette", px[:4] == bytes((30, 20, 10, 128)) and ha)
    two = struct.pack("<IIIBBB", 565, 1, 1, 2, 1, 0xA5) + bytes((0x1F, 0xF8))   # LE 0xF81F: r 31, g 0, b 31
    check("gf: 565", gf_decode(two)[2] == bytes((255, 0, 255, 255)))
    four = struct.pack("<IIIBBB", 4444, 1, 1, 2, 1, 0xA5) + bytes((0x34, 0x12))  # LE 0x1234: a1 r2 g3 b4
    check("gf: 4444", gf_decode(four)[2] == bytes((34, 51, 68, 17)))
    # malformed input is refused, never over-read or over-allocated
    check("refuse: a size beyond the limit", refused(lambda: gf_decode(struct.pack("<IIIBBB", 8888, 70000, 1, 3, 1, 0))))
    check("refuse: a run past the channel's end", refused(lambda: gf_decode(struct.pack("<IIIBBB", 8888, 2, 1, 1, 1, 0xA5)
                                                                             + bytes(1024) + bytes((0xA5, 1, 9)))))
    check("refuse: truncated data", refused(lambda: gf_decode(gf_encode(8, 8, sample_picture(8))[:-3])))
    check("refuse: trailing bytes", refused(lambda: gf_decode(gf_encode(8, 8, sample_picture(8)) + b"x")))
    check("refuse: unknown format", refused(lambda: gf_decode(struct.pack("<IIIBBB", 1234, 1, 1, 3, 1, 0) + b"abc")))
    # M35: format 888 (24-bit, three planes) as a real RCP package stores it; with a mip chain
    g888 = bytearray(gf_encode(32, 32, pic, channels=3))
    g888[0:4] = struct.pack("<I", 888)
    check("gf: 888 decodes like three B, G, R planes", gf_decode(bytes(g888))[2] == pic)
    check("refuse: 888 with four channels", refused(lambda: gf_decode(struct.pack("<IIIBBB", 888, 1, 1, 4, 1, 0xA5)
                                                                        + bytes(4))))
    mip = struct.pack("<IIIBBB", 888, 2, 2, 3, 2, 0xA5) + bytes(5) + bytes(5) + bytes(5)   # 2x2 + 1x1 per plane
    check("gf: 888 with a mip chain (base level kept)", gf_decode(mip)[:2] == (2, 2))
    # resizing keeps the quadrants and the orientation
    big = resize(32, 32, pic, 64, 64)
    small = resize(32, 32, pic, 16, 16)
    check("resize: bilinear up / area down keep the quadrant colours",
          big[(54 * 64 + 54) * 4:(54 * 64 + 54) * 4 + 3] == bytes((220, 40, 220))
          and abs(small[(3 * 16 + 13) * 4 + 2] - 240) <= 2, (big[(54 * 64 + 54) * 4:(54 * 64 + 54) * 4 + 3],
                                                             small[(3 * 16 + 13) * 4:(3 * 16 + 13) * 4 + 3]))
    check("jsonc: comments and trailing commas", json.loads(strip_jsonc('{"a": "x//y", // c\n "b": [1,], /* d */}'))
          == {"a": "x//y", "b": [1]})
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        z = td / "s.zip"
        cmd_make_sample(z, "charact/test", 16)
        files, skipped = read_source(z)
        check("package: the sample's metadata and GF are read", len(files) == 2 and metadata(files)["name"])
        m = GF_RE.match("files/added_files/Gamedatabin/tex32_1.cnt/charact/test.gf")
        check("mapping: <archive>.cnt/<dir>/<name>.gf -> <dir>\\<name>.dds", m and m.group(1) + m.group(2) == "charact/test")
        for label, members in (("traversal", {"metadata.jsonc": b"{}", "../x.gf": b"x"}),
                               ("absolute", {"metadata.jsonc": b"{}", "/x.gf": b"x"}),
                               ("backslash traversal", {"metadata.jsonc": b"{}", "a\\..\\x.gf": b"x"})):
            zz = td / f"{label}.zip"
            with zipfile.ZipFile(zz, "w") as zf:
                for n, d in members.items():
                    zi = zipfile.ZipInfo("x")
                    zi.filename = n   # set after construction: the constructor turns "\\" into "/" on Windows
                    zf.writestr(zi, d)
            check(f"refuse package: {label}", refused(lambda zz=zz: read_source(zz)))
        zz = td / "exe.zip"
        with zipfile.ZipFile(zz, "w") as zf:
            zf.writestr("metadata.jsonc", "{}")
            zf.writestr("Ray3Fix.dll", b"MZ")
        files, skipped = read_source(zz)
        check("package: code files are never read (listed as ignored)", skipped == ["Ray3Fix.dll"] and len(files) == 1)
    n = results.count(False)
    print(f"R3HD_PCMOD_SELFTEST {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}")
    return 1 if n else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["inspect", "convert", "make-sample", "selftest"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--id")
    ap.add_argument("--entry", default="charact/rayman")
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--game-dir")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    paths = rm.resolve_paths(argparse.Namespace(home=None, mods_root=None, cache=None, game_dir=a.game_dir))
    try:
        if a.cmd == "inspect" and len(a.args) == 1:
            r = cmd_inspect(paths, Path(a.args[0]))
        elif a.cmd == "convert" and len(a.args) == 2:
            r = cmd_convert(paths, Path(a.args[0]), Path(a.args[1]), a.id)
        elif a.cmd == "make-sample" and len(a.args) == 1:
            r = cmd_make_sample(Path(a.args[0]), a.entry, a.size)
        else:
            raise Refused("usage: see --help")
        r, code = {"result": "ok", **r}, 0
    except (Refused, rm.Refusal) as x:
        r, code = {"result": "refused", "detail": getattr(x, "detail", str(x))}, 2
    except (OSError, zipfile.BadZipFile, ValueError, struct.error) as x:
        r, code = {"result": "refused", "detail": f"{type(x).__name__}: {x}"}, 2
    sys.stdout.buffer.write((json.dumps(r, indent=1, ensure_ascii=a.json, default=str) + "\n").encode("utf-8"))
    return code


if __name__ == "__main__":
    sys.exit(main())
