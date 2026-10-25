#!/usr/bin/env python3
"""M49 (D-088): a small kit for mod authors, on top of the mod engine (tools/r3hd_mods.py). See MODDING.md.

    r3hd_modkit.py template OUT [--id ID] [--entry ENTRY] [--bundles B[,B]] [--find TEXT --text NEW]
    r3hd_modkit.py pack DIR OUT.zip
    r3hd_modkit.py check SOURCE                                 r3hd_mods.py validate, with a short verdict
    r3hd_modkit.py selftest
Common: --home H (an installation; else R3HD_HOME, else the repository layout), --game-dir DIR, --cache DIR
(repository use: always a cache of your own, never private/play/cache), --json.

template  writes a working example mod into the new folder OUT, made only of synthetic data: a texture override whose
          PNG is a drawn test pattern (diagonal stripes, a frame and an arrow pointing up, so the picture's
          orientation can be checked in the game) at the exact size of ENTRY in the person's own game files, and, with
          --find, one text override (the game string TEXT found in fix.lvl -> NEW). The offset and slot hash come from
          the person's game files when the template is made; nothing of the game is copied into the folder. Then the
          folder is validated against those files.
pack      a deterministic .zip of a mod folder (mod.json first, sorted names, fixed time stamps; only the file kinds
          a mod may hold: .json .png .txt .md), validated before it is written.
check     validate a folder or .zip (format, names, sizes, every override against the game files) and say why not.

Nothing here installs a mod or writes game data: Settings > Mods > Install .zip (or r3hd_mods.py import) does that.
Standard library only (the installed Python has no extensions). Exit 0 ok, 2 refused, 1 internal error.
"""
import argparse
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3hd_mods as mods  # noqa: E402

DEFAULT_ENTRY = "menu\\mnu_jard.dds"
DEFAULT_BUNDLES = ["GAMEDATAbin/fix"]
PORT_MIN = "0.36.0"
RELEASES = ["x360-xbla-5841123F-v1"]


def paths_of(a) -> dict:
    return mods.resolve_paths(SimpleNamespace(home=a.home, mods_root=None, cache=a.cache, game_dir=a.game_dir))


def png_bytes(w: int, h: int, rgba: bytes) -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def test_pattern(w: int, h: int) -> bytes:
    """Magenta / yellow diagonal stripes, a dark frame and a white arrow pointing to the top edge: synthetic data."""
    out = bytearray()
    band = max(4, min(w, h) // 8)
    for y in range(h):
        for x in range(w):
            nx, ny = (x + 0.5) / w, (y + 0.5) / h
            c = (0xE0, 0x30, 0xC0) if ((x + y) // band) % 2 == 0 else (0xFF, 0xD8, 0x30)
            if min(x, y, w - 1 - x, h - 1 - y) < max(1, min(w, h) // 32):
                c = (0x20, 0x10, 0x40)
            in_head = ny < 0.45 and ny > 0.12 and abs(nx - 0.5) < (ny - 0.12) * 0.75
            in_shaft = 0.45 <= ny < 0.85 and abs(nx - 0.5) < 0.08
            if in_head or in_shaft:
                c = (0xFF, 0xFF, 0xFF)
            out += bytes(c) + b"\xff"
    return bytes(out)


def make_template(paths, out: Path, mod_id: str, entry: str, bundles, find: str = None, new_text: str = None) -> dict:
    if out.exists():
        raise mods.Refusal("EXISTS", f"{out} exists; choose a new folder")
    info = mods.cmd_texture_info(paths, entry)
    hits = [b for b in info["bundles"] if bundles == "all" or b["bundle"] in bundles]
    if not hits:
        raise mods.Refusal("NOT_FOUND", f"{entry}: no such texture entry in {bundles} (r3hd_mods.py texture-info)")
    sizes = {(b["width"], b["height"]) for b in hits}
    if len(sizes) != 1:
        raise mods.Refusal("UNSUPPORTED", f"{entry} has different sizes in {bundles}: name one bundle with --bundles")
    w, h = sizes.pop()
    overrides = [{"type": "texture", "entry": entry, "bundles": bundles, "image": "textures/test_pattern.png"}]
    if find:
        found = mods.cmd_text_find(paths, find)["matches"]
        if len(found) != 1:
            raise mods.Refusal("NOT_FOUND", f"{find!r}: {len(found)} matches in fix.lvl; it must be exactly one")
        overrides.append({"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": found[0]["offset"],
                          "slot_sha256": found[0]["slot_sha256"], "text": new_text or find.upper()})
    manifest = {"format": 1, "id": mod_id, "name": "Example mod", "version": "1.0.0",
                "description": "An example made by r3hd_modkit.py template: a test pattern on one texture"
                               + (" and one changed text." if find else "."),
                "authors": ["Your name"], "license": "CC0-1.0",
                "target": {"title_id": mods.TITLE_ID, "releases": RELEASES, "min_port_version": PORT_MIN},
                "overrides": overrides}
    (out / "textures").mkdir(parents=True)
    (out / "textures" / "test_pattern.png").write_bytes(png_bytes(w, h, test_pattern(w, h)))
    (out / "mod.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "README.txt").write_text(
        f"{manifest['name']} {manifest['version']}\n\nMade with r3hd_modkit.py template. Replace textures/test_pattern.png"
        f" with your own picture of exactly {w} x {h} pixels (PNG), change the id, name and description in mod.json,"
        " then: r3hd_modkit.py pack THIS_FOLDER my_mod.zip, and install the .zip in Settings > Mods.\n", encoding="utf-8")
    try:
        result = mods.cmd_validate(paths, out)
    except mods.Refusal:
        shutil.rmtree(out, ignore_errors=True)  # a template that does not validate is not left behind
        raise
    return {"out": str(out), "entry": entry, "size": f"{w}x{h}", "overrides": len(overrides), "validate": result}


def pack(paths, src: Path, out: Path) -> dict:
    if not (src / "mod.json").is_file():
        raise mods.Refusal("BAD_PACKAGE", f"{src}: no mod.json")
    names = []
    for p in sorted(src.rglob("*")):
        if p.is_file():
            rel = p.relative_to(src).as_posix()
            if p.suffix.lower() not in mods.ALLOWED_EXT:
                raise mods.Refusal("BAD_PACKAGE", f"{rel}: a mod holds only {', '.join(sorted(mods.ALLOWED_EXT))} files")
            names.append(rel)
    result = mods.cmd_validate(paths, src)
    names.sort(key=lambda n: (n != "mod.json", n))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    with zipfile.ZipFile(tmp, "w") as z:
        for n in names:
            zi = zipfile.ZipInfo(n, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, (src / n).read_bytes())
    os.replace(tmp, out)
    mods.cmd_validate(paths, out)
    return {"out": str(out), "files": len(names), "validate": result}


def selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append(bool(cond))
        print(("ok   " if cond else "FAIL ") + name)
    pat = test_pattern(64, 32)
    check("test pattern: size, opaque, arrow at the top centre", len(pat) == 64 * 32 * 4
          and all(pat[i + 3] == 255 for i in range(0, len(pat), 4)) and pat[(10 * 64 + 32) * 4:(10 * 64 + 32) * 4 + 3] == b"\xff\xff\xff")
    png = png_bytes(64, 32, pat)
    check("png: signature and IHDR size", png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (64, 32))
    with tempfile.TemporaryDirectory() as t:
        d = Path(t) / "m"
        d.mkdir()
        (d / "mod.json").write_text("{}", encoding="utf-8")
        (d / "x.exe").write_bytes(b"MZ")
        try:
            pack({"game": Path(t)}, d, Path(t) / "o.zip")
            refused = False
        except mods.Refusal as e:
            refused = e.code == "BAD_PACKAGE"
        check("pack: refuses a file kind a mod may not hold", refused)
    ok = all(checks)
    print(f"R3HD_MODKIT_SELFTEST {'PASS' if ok else 'FAIL'} checks={len(checks)}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["template", "pack", "check", "selftest"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--home")
    ap.add_argument("--game-dir")
    ap.add_argument("--cache", help="the encoder cache (default: the installation's cache folder)")
    ap.add_argument("--id", default="example.test-pattern")
    ap.add_argument("--entry", default=DEFAULT_ENTRY)
    ap.add_argument("--bundles", default=",".join(DEFAULT_BUNDLES))
    ap.add_argument("--find")
    ap.add_argument("--text")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    try:
        paths = paths_of(a)
        if a.cmd == "template" and len(a.args) == 1:
            bundles = "all" if a.bundles == "all" else [b for b in a.bundles.split(",") if b]
            r = make_template(paths, Path(a.args[0]), a.id, a.entry, bundles, a.find, a.text)
        elif a.cmd == "pack" and len(a.args) == 2:
            r = pack(paths, Path(a.args[0]), Path(a.args[1]))
        elif a.cmd == "check" and len(a.args) == 1:
            r = {"verdict": "OK", **mods.cmd_validate(paths, Path(a.args[0]))}
        else:
            raise mods.Refusal("USAGE", __doc__.splitlines()[2].strip())
        print(json.dumps(r, indent=1, ensure_ascii=not a.json))
        print(f"R3HD_MODKIT {a.cmd.upper()} OK")
        return 0
    except mods.Refusal as x:
        print(f"R3HD_MODKIT REFUSED {x.code}: {x.detail}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
