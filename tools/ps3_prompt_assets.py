"""Private, targeted PS3 prompt extraction; no GUI, installation, executable or licence processing.

Requires the pinned official PyKG source and the project's existing PyCryptodome.
Only its container reader/decryptor runs. No key material is embedded in this file.
Outputs are proprietary: private directories only, never public/release payloads.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct

import r3hd_mods as m

ROOT = Path(__file__).resolve().parents[1]
TOOL_COMMIT = "9be170666040639a526065bceea8ee75bf709a0d"
TOOL_SHA256 = "77ccbd417b5fa6b63fdb7edbd0a4de4eeeb34ca24854e9e72ffd10da4b3ce4a1"
PKG_SHA256 = "5724342d23e503b6e91b2624bdffd7aecf1936241860ba60280a6b991a1ee95e"
SELECTED = {
    "USRDIR/GamedataBIN/fix.lvl": "09feaa792e75cba43de7a2a6e9fa57307f79a80edf0975a923bd250d08877ebe",
    "USRDIR/Gamedata/World/Graphics/TexturesDDS/texts/typoray3_ps2.dds":
        "89647acd43d5053c5cd29b884ba5dd1c539cdc378c0b2dffdd4ac957f3eaf45f",
}


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def reader(tool):
    """Load exactly the reviewed reader routines and their constant dependencies.

    Avoid importing GUI/repacking/install paths or installing their dependencies.
    The tool's original source remains unmodified under external/.
    """
    if digest(tool) != TOOL_SHA256:
        raise ValueError("PyKG source differs from the reviewed pin")
    from Crypto.Cipher import AES
    from Crypto.Util import Counter
    tree = ast.parse(tool.read_text(encoding="utf-8-sig"))
    names = {"read_header", "decrypt_region", "get_debug_keystream_block"}
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in functions} != names:
        raise ValueError("missing pinned container reader")
    constants = {n.targets[0].id: n for n in tree.body if isinstance(n, ast.Assign)
                 and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)}
    needed = {n.id for fn in functions for n in ast.walk(fn) if isinstance(n, ast.Name)} | {
        "ITEM_FMT", "ITEM_RECORD_SIZE"}
    selected = set()
    while True:
        more = {name for name in needed if name in constants and name not in selected
                and name not in ("AES", "Counter")}
        if not more:
            break
        selected |= more
        needed |= {n.id for name in more for n in ast.walk(constants[name]) if isinstance(n, ast.Name)}
    nodes = [n for n in tree.body if n in functions or
             (isinstance(n, ast.Assign) and len(n.targets) == 1 and
              isinstance(n.targets[0], ast.Name) and n.targets[0].id in selected)]
    namespace = {"AES": AES, "Counter": Counter, "struct": struct, "hashlib": hashlib}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(tool), "exec"), namespace)
    return namespace


def extract(pkg, tool, out):
    pkg, tool, out = pkg.resolve(), tool.resolve(), out.resolve()
    out.relative_to((ROOT / "private").resolve())
    if out.exists():
        raise ValueError("destination exists; preserve it and select a fresh private directory")
    if digest(pkg) != PKG_SHA256:
        raise ValueError("package differs from the reviewed full PKG")
    core = reader(tool)
    inventory, payloads = [], {}
    with pkg.open("rb") as f:
        hdr = core["read_header"](f)
        if hdr["item_count"] != 3296 or hdr["release_type"] != 0x8000:
            raise ValueError("unexpected package layout")
        table = core["decrypt_region"](f, hdr, 0, hdr["item_count"] * core["ITEM_RECORD_SIZE"])
        for i in range(hdr["item_count"]):
            no, nl, off, size, flags, _ = struct.unpack_from(core["ITEM_FMT"], table, i * core["ITEM_RECORD_SIZE"])
            if not 0 < nl < 4096 or hdr["data_offset"] + off + size > pkg.stat().st_size:
                raise ValueError("package entry outside source bounds")
            name = core["decrypt_region"](f, hdr, no, nl).rstrip(b"\0").decode("utf-8")
            inventory.append({"name": name, "offset": off, "size": size, "flags": flags})
            if name in SELECTED:
                if name in payloads or size > 8 * 1024 * 1024:
                    raise ValueError("duplicate or oversized selected asset")
                data = core["decrypt_region"](f, hdr, off, size)
                if m.sha256_bytes(data) != SELECTED[name]:
                    raise ValueError("selected asset identity changed")
                payloads[name] = data
    if payloads.keys() != SELECTED.keys():
        raise ValueError("native font assets missing")
    result = crop_native(payloads["USRDIR/GamedataBIN/fix.lvl"],
                         payloads[next(name for name in SELECTED if name.endswith(".dds"))], out)
    (out / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    if digest(pkg) != PKG_SHA256:
        raise ValueError("source package changed during extraction")
    return dict(result, extracted_files=2, package_unchanged=True, inventory_entries=len(inventory))


def crop_native(fix, dds, out):
    """D-202: reuse exact extracted font inputs; no new PKG/dependency needed."""
    import r3hd_button_prompts as prompts
    out = out.resolve()
    out.relative_to((ROOT / "private").resolve())
    if out.exists():
        raise ValueError("destination exists; choose a fresh private directory")
    if (m.sha256_bytes(fix) != SELECTED["USRDIR/GamedataBIN/fix.lvl"] or
            m.sha256_bytes(dds) != SELECTED[next(n for n in SELECTED if n.endswith(".dds"))]):
        raise ValueError("extracted native font identity changed")
    if dds[:4] != b"DDS " or struct.unpack_from("<II", dds, 12) != (512, 512) or dds[84:88] != b"DXT5":
        raise ValueError("unsupported native font format")
    base = dds[128:128 + 512 * 512]
    rgba = m.decode_level(512, 512, [base[i * 2048:(i + 1) * 2048] for i in range(128)], "DXT5")
    records = m.font_records(fix, 0x63A2)
    output, glyphs = {}, {}
    for code, name in prompts.BUTTONS.items():
        x, y, h, w, _, descent, bitmap, defined = records[code]
        if not defined or bitmap != 0 or x + w > 512 or y + h > 512:
            raise ValueError("native glyph outside atlas")
        crop = b"".join(rgba[((y + j) * 512 + x) * 4:((y + j) * 512 + x + w) * 4] for j in range(h))
        if (w, h, descent, m.sha256_bytes(crop)) != prompts.NATIVE_GLYPHS[name]:
            raise ValueError("native glyph differs from accepted source identity")
        output[name + ".png"] = m.write_png(w, h, crop)
        glyphs[name] = {"code": code, "rect": [x, y, w, h], "descent": descent,
                        "rgba_sha256": m.sha256_bytes(crop)}
    manifest = {"schema": 2, "kind": "r3hd-private-ps3-button-glyphs", "glyphs": glyphs,
                "assets": SELECTED}
    out.mkdir(parents=True)
    for name, data in output.items():
        (out / name).write_bytes(data)
    (out / "glyphs.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {"manifest": str(out / "glyphs.json"), "glyphs": glyphs, "source_files": 2}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--pkg", type=Path)
    source.add_argument("--extracted-dir", type=Path, help="existing verified fix.lvl and typoray3_ps2.dds")
    ap.add_argument("--tool", type=Path, default=ROOT / "external/ps3-pykg/PyKG.py")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.extracted_dir:
        result = crop_native((a.extracted_dir / "fix.lvl").read_bytes(),
                             (a.extracted_dir / "typoray3_ps2.dds").read_bytes(), a.out)
    else:
        result = extract(a.pkg, a.tool, a.out)
    print(json.dumps(result))
