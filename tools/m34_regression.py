#!/usr/bin/env python3
"""M34 regression (no game run): Turkish glyphs, text moves, the translation workflow and the PC texture converter on
the person's own game data, plus the selftests of the two new tools. Game data is never written; everything this
writes stays in a temporary folder. Skips the real-data part (with a SKIP line) when the game data is absent.

usage: m34_regression.py
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import r3hd_mods as rm  # noqa: E402
import r3hd_loc as rl  # noqa: E402
import r3hd_pcmod as pc  # noqa: E402

results = []


def check(ok, label):
    results.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'} {label}", flush=True)


def run(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def main() -> int:
    sys.stdout.reconfigure(errors="backslashreplace")
    for tool, marker in (("r3hd_loc.py", "R3HD_LOC_SELFTEST PASS"), ("r3hd_pcmod.py", "R3HD_PCMOD_SELFTEST PASS")):
        r = run(str(TOOLS / tool), "selftest")
        check(r.returncode == 0 and marker in r.stdout, f"{tool} selftest ({r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]})")
    pay = json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))
    check(pay["version"].startswith(("0.34.0", "0.35.0", "0.36.0", "0.49.0", "0.50.0", "1.0.0", "1.0.1", "1.0.2")) and "app/tools/r3hd_mods.py" in json.dumps(pay),
          f"payload: version {pay['version']}, ships the mod tool (glyphs, moved text)")
    src = ROOT / "config" / "localization" / "tr" / "tr.json"
    if not src.is_file():
        # The game-derived sample is left out of the public source export (config/release/public_export.json).
        print("SKIP sample checks: config/localization/tr/tr.json is absent", flush=True)
        return finish()
    doc = json.loads(src.read_text(encoding="utf-8"))
    check(all(set(e) <= {"source_sha256", "text", "note"} for e in doc["strings"].values()),
          "sample source: strings carry a source hash, never the source text")
    game = rm.ROOT / "private" / "extracted" / rm.TITLE_ID
    if not (game / "GAMEDATAbin" / "fix.lvl").is_file():
        print("SKIP real-data checks: no game data", flush=True)
        return finish()
    watched = [game / "GAMEDATAbin" / n for n in ("fix.lvl", "fix.ptr", "fix.btf", "fix.bhf")]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    fix = watched[0].read_bytes()
    font = rm.read_font(fix)
    check(font is not None and len(font["defined"]) == 150 and not set(rm.TURKISH.values()) - {0xDD} & font["defined"],
          "font: the four definitions are the shipped ones; FontRay defines 150 codes, no Turkish one (Ý at DD)")
    t = rl.tables(fix)
    check(sorted(t) == sorted(rl.LANGS) and all(n == rl.HANDLES for _, n in t.values()),
          f"text tables: five languages of {rl.HANDLES} handles")
    off, slot = rl.string_at(fix, t, "en.471")
    check(off == 153136 and len(slot) == 52, "text tables: en.471 is the intro_10 tutorial line (offset 153136)")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ns = argparse.Namespace(cache=str(td / "cache"), game_dir=None)
        paths = rl.game_paths(ns)
        res = rl.cmd_check(paths, src)
        check(not res["errors"] and res["moved"] == 2 and res["glyphs"] == "ĞğİıŞş",
              f"sample source: no errors, two strings moved, six glyphs ({res})")
        a, b = rl.cmd_build(paths, src, td / "a", True), rl.cmd_build(paths, src, td / "b", True)
        check(a["sha256"] == b["sha256"] and a["zip_sha256"] == b["zip_sha256"],
              "build: the same source gives the same mod.json and zip, byte for byte")
        m = rm.parse_manifest({"mod.json": (td / "a" / "mod.json").read_bytes()})
        paths_m = dict(paths, cache=td / "cache2")
        ranges = rm.compile_mod(m, {}, paths_m)
        recs = {r[1]: struct.unpack(">6H2B", r[2]) for r in ranges if r[3].startswith("glyph ")}
        check(len(recs) == 12 and all(v[7] == 1 and v[6] == 0 for v in recs.values()) and m["_linked"],
              "glyphs: six records in each FontRay copy; the mod applies whole (linked)")
        bhf, e, w, h, fmt = rm.resolve_texture(game, {"entry": rm.FONT["atlas"], "bundles": [rm.FONT["bundle"]]})[0]
        with open(bhf.with_suffix(".btf"), "rb") as f:
            f.seek(e[2])
            o0 = f.read(e[1])
            f.seek(e[4])
            o1 = f.read(e[3])
        n0 = next(r[2] for r in ranges if r[3].endswith("#base"))
        n1 = next(r[2] for r in ranges if r[3].endswith("#mips"))
        lay = rm.layout(w, h, fmt)[2]
        old = rm.decode_level(w, h, rm.level_rows((o0, o1), lay[0], fmt), fmt)
        new = rm.decode_level(w, h, rm.level_rows((n0, n1), lay[0], fmt), fmt)
        same = all(old[(y * w + x) * 4:(y * w + x) * 4 + 4] == new[(y * w + x) * 4:(y * w + x) * 4 + 4]
                   for x0, y0, x1, y1 in font["cells"] for y in range(y0, y1) for x in range(x0, x1))
        check(same and old != new, "atlas: every texel of every mapped glyph cell keeps its value at the base level")
        cells = [(v[0], v[1], v[0] + v[3], v[1] + v[2]) for v in recs.values()]
        drawn = all(any(new[(y * w + x) * 4 + 3] > 128 for y in range(y0, y1) for x in range(x0, x1)) for x0, y0, x1, y1 in cells)
        check(drawn, "atlas: each new glyph cell holds ink")
        ptrs = [r for r in ranges if r[3].startswith("pointer")]
        check(len(ptrs) == 2 and all(len(r[2]) == 4 for r in ptrs),
              f"text: the two longer strings (New, the quit question) are moved by their table pointers ({[r[3] for r in ptrs]})")
        # PC conversion of the synthetic RCP package
        z = td / "pc.zip"
        pc.cmd_make_sample(z, "charact/rayman", 64)
        conv = pc.cmd_convert(paths, z, td / "pcmod")
        tx = conv["textures"][0]
        check(tx.get("entry") == "charact\\rayman.dds" and tx.get("to") == "512x512 DXT1" and tx.get("alpha") == "HD texture",
              f"pc: the GF maps to charact\\rayman.dds, resized to 512x512 DXT1, the HD alpha kept ({tx})")
        tx_png = "textures/charact/rayman.png"
        pfiles = {"mod.json": (td / "pcmod" / "mod.json").read_bytes(), tx_png: (td / "pcmod" / tx_png).read_bytes()}
        pr = rm.compile_mod(rm.parse_manifest(pfiles), pfiles, dict(paths, cache=td / "cache3"))
        base = next(r[2] for r in pr if r[3].endswith("#base"))
        lay = rm.layout(512, 512, "DXT1")[2]
        pic = rm.decode_level(512, 512, rm.level_rows((base, b""), lay[0], "DXT1"), "DXT1")

        def at(x, y):
            return tuple(pic[(y * 512 + x) * 4:(y * 512 + x) * 4 + 3])
        near = lambda c, ref: all(abs(a - b) <= 24 for a, b in zip(c, ref))  # noqa: E731
        check(near(at(228, 164), (230, 40, 40)) and near(at(356, 164), (40, 80, 240)) and near(at(164, 356), (40, 210, 70))
              and near(at(356, 356), (220, 40, 220)) and near(at(76, 100), (250, 250, 250)),
              f"pc: the encoded HD texture is upright (red top left with its white F, blue top right, green bottom left, "
              f"magenta bottom right: {at(228, 164)} {at(356, 164)} {at(164, 356)} {at(356, 356)} {at(76, 100)})")
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched}
    check(before == after, "game data never written")
    return finish()


def finish() -> int:
    n = results.count(False)
    print(f"M34_REGRESSION {'PASS' if not n else 'FAIL'} {len(results) - n}/{len(results)}", flush=True)
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
