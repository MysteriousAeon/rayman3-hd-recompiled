#!/usr/bin/env python3
"""M33 (D-070): data-only mods for Rayman 3 HD Recompiled: package validation, controlled import, enable / disable /
priority / remove, and the launch plan the runtime overlays on game-file reads (tools/m33_mod_overlay.h).

A mod is a folder or a .zip holding mod.json (format 1) and the files it names. It declares overrides; nothing in it
is executed and nothing in the game data is ever written:
  texture   one texture entry of the game's bundles (`NAME.bhf` / `NAME.btf`), from a PNG of the entry's exact size;
            encoded here into the entry's own format (DXT1 or DXT5), mip chain and console layout, same byte sizes
  text      one string of the game's text table in `GAMEDATAbin/fix.lvl`, identified by its offset and the SHA-256 of
            its slot (the string, its NUL and the alignment padding). A text that fits its slot replaces it in place;
            a longer one (M34) is moved into space this mod's other text overrides free, and every language-table
            pointer to the string (fix.ptr) is redirected to it. When that packer finds no contiguous room, the
            compacting packer (M38, D-075) refills whole runs of this mod's adjacent slots, moving strings that fit
            too (--text-packer / R3HD_TEXT_PACKER = auto | m34 | compact). Turkish letters need glyphs (below)
  glyph     (M34) one Turkish letter (ğ Ğ ş Ş ı İ) for the game's font FontRay at its Windows-1254 code: composed from
            the font's own glyphs (crops) and small accent bitmaps written as text in the manifest (or a PNG's alpha),
            placed in free or unmapped cells of the font atlas `texts\\typoray3`, with the glyph record written to both
            FontRay copies in fix.lvl; mapped glyphs keep their exact base-level bytes. A text may use a Turkish letter only when
            a glyph for it comes from the same mod or a mod it requires
Mods live under MODS = HOME\\mods (an installation) or private\\play\\mods (the repository layout):
  MODS\\state.json              {"schema": 1, "mods": [{"id", "enabled", "installed_at"}]}: list order = priority,
                                the first wins an overlap
  MODS\\installed\\<id>\\        the imported files and installed.json (every file's size and SHA-256)
The plan (`plan`) is written under the cache (HOME\\cache\\mods or private\\play\\cache\\mods): plan.txt and one
replacement file per range; play.ps1 passes it in R3HD_MODS_PLAN. The runtime re-verifies the whole plan and uses
all of it or nothing.

usage:
  r3hd_mods.py validate SOURCE [--game-dir G]           check a mod folder / .zip without installing it
  r3hd_mods.py import SOURCE [--replace] [--enable]     controlled import (refuses unsafe or invalid packages)
  r3hd_mods.py list                                     installed mods, state and the reason a mod is not applied
  r3hd_mods.py enable ID | disable ID | remove ID
  r3hd_mods.py move ID up|down|top|bottom               change the priority
  r3hd_mods.py plan [--out DIR]                         compile the enabled mods into the launch plan
  r3hd_mods.py text-find TEXT [--game-dir G]            authoring: offset, capacity and slot hash of a string
  r3hd_mods.py texture-info ENTRY [--game-dir G]        authoring: the bundles, size and format of a texture entry
  r3hd_mods.py texture-export ENTRY OUT.png             authoring: the entry's base level as an upright PNG
  r3hd_mods.py selftest                                 synthetic fixtures only
Common: --home H (else R3HD_HOME, else the repository layout), --mods-root DIR, --cache DIR, --game-dir DIR, --json,
--text-packer auto|m34|compact.
Exit 0 ok, 2 refused (reason code), 1 internal error. Standard library only (the installed Python has no extensions).
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
FORMAT = 1
STATE_SCHEMA = 1
TITLE_ID = "5841123F"
PLAN_NAME = "plan.txt"
# D-101: optional display text of the host Achievements overlay / toast, carried by a mod beside mod.json. It is not
# an override: it never enters the byte plan, never refuses a mod, and the runtime shows it only for English it
# was made from (source SHA-256 checked against the title's XDBF in the runtime).
ACH_FILE = "achievements/achievements.json"
ACH_KIND = "r3hd-achievement-text"
ACH_TEXT_NAME = "achievement_text.tsv"
ACH_FIELDS = ("label", "description", "unachieved")
ACH_MAX = {"label": 64, "description": 160, "unachieved": 160}

# Package limits (fail closed): a mod is small data; anything beyond these is refused, never truncated.
MAX_FILES = 2048
MAX_FILE_BYTES = 64 << 20
MAX_TOTAL_BYTES = 256 << 20
MAX_RATIO = 100          # uncompressed / compressed, for zip members above 1 MiB
MAX_NAME = 160
MAX_DEPTH = 6
MAX_OVERRIDES = 4096
MAX_PNG_SIDE = 4096
ALLOWED_EXT = {".json", ".png", ".txt", ".md"}
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
VERSION_RE = re.compile(r"^[0-9]+(\.[0-9]+){0,3}([-+][A-Za-z0-9.]{1,32})?$")
# Characters the game's font atlas `texts\typoray3` is seen to hold (M33 inspection of the decoded atlas): ASCII and
# the Latin-1 letters of the five shipped languages. Turkish g-breve, s-cedilla, dotless i and dotted capital I are
# not in it, and they have no Windows-1252 byte either.
TURKISH_MISSING = "ğĞşŞıİ"
# M34: their Windows-1254 bytes. No shipped string uses these codes; D0 DE F0 FD FE are undefined in FontRay and DD is
# Ý, which no shipped string uses either (RE_NOTES "M34"). A glyph override defines the code; text then encodes the
# letter as that byte.
TURKISH = {"Ğ": 0xD0, "İ": 0xDD, "Ş": 0xDE, "ğ": 0xF0, "ı": 0xFD, "ş": 0xFE}
# Every character a glyph override may add, with its byte: Turkish letters, ellipsis and French ligatures, Windows-1252 /
# Windows-1254 0x85 (undefined in FontRay; only en.18 and en.448 use it, where it draws nothing; RE_NOTES "M37 font
# gaps"). Text encodes such a character as its byte only when a glyph of the mod (or of a mod it requires) adds it.
GLYPH_CODES = {**TURKISH, "…": 0x85, "Œ": 0x8C, "œ": 0x9C}
# The font as shipped in the one supported release (RE_NOTES "M33" / "M34"): FontDefine = name[50] + 256 records of
# 14 bytes (u16 x, y, height, width, pixel size, descent (signed); u8 bitmap; u8 defined), big-endian. FontRay twice
# (the two copies differ in ten button / symbol records, never in a letter), FontPADRay twice, all on one atlas.
# The SHA-256 of each definition (name + records) ties a glyph override to exactly this data.
FONT = {
    "fontray": (0x2AF2, 0x50BE),
    "others": (0x3DD6, 0x63A2),
    "sha256": {0x2AF2: "304e6f32e7f68b25065b5357c8fa880e72c0883b99c7f5d7f5bc6de6a9aae3e0",
               0x50BE: "aa19a41edb9a98c4570f79788d7e2482fd02df130259ddfe8a2ac2fb8b679098",
               0x3DD6: "f3c295cc81f55965a8970cd1441b59b7eb3a79570620180461182c66092160b5",
               0x63A2: "5ca6cdfb3e6f67385087239afb98c9a8c3d9230a350b914e04208d361df0c18a"},
    "atlas": "texts\\typoray3.dds",
    "bundle": "GAMEDATAbin/fix",
    "atlas_size": (512, 512, "DXT5"),
}
FONTDEF_BYTES = 50 + 256 * 14
GLYPH_MAX_SIDE = 64
# Accent bitmaps in a manifest: one character per pixel, alpha from transparent to opaque.
BITMAP_LEVELS = " .:-=+*#%@"
# Language-table pointers in fix.lvl hold the string's file offset minus this (the level file's header), and fix.ptr
# lists every pointer location (RE_NOTES "M34").
REF_BIAS = 4

ADVICE = {
    "NOT_A_MOD": "No mod.json was found at the top of the package (or in its single top-level folder).",
    "UNSAFE_PACKAGE": "The package contains a path, link or file type that is not allowed in a mod.",
    "TOO_LARGE": "The package is larger than a data mod may be.",
    "BAD_MANIFEST": "mod.json is not a valid format-1 mod manifest.",
    "INCOMPATIBLE": "The mod was made for another game, release or a newer version of this port.",
    "TARGET_MISSING": "A file or texture the mod overrides does not exist in your game data.",
    "TARGET_CHANGED": "The game data the mod overrides is not the data it was made for.",
    "BAD_IMAGE": "An image of the mod is not a valid PNG of the texture's exact size.",
    "TEXT_TOO_LONG": "A replacement text is longer than the original string's space.",
    "TEXT_GLYPH_MISSING": "A replacement text uses characters the game's font cannot show. Turkish letters need a "
                          "font mod that adds them, required by this mod.",
    "UNSUPPORTED": "The mod asks for something this port's mod format does not support.",
    "EXISTS": "A mod with this ID is installed already (use replace to update it).",
    "NOT_INSTALLED": "No installed mod has this ID.",
    "DAMAGED": "The installed mod's files changed since it was imported. Remove it and import it again.",
    "CONFLICT": "The mod declares a conflict with another enabled mod of higher priority, or it adds glyphs or "
                "moves text where a higher-priority mod changes the same data.",
    "MISSING_DEPENDENCY": "A mod this one requires is not installed, enabled and valid.",
    "NO_GAME_DATA": "The game data folder was not found.",
    "STATE_DAMAGED": "The mod list (mods\\state.json) is damaged; it was left unchanged.",
    "USAGE": "Invalid arguments.",
    "UNREADABLE": "A file could not be read or written (a damaged archive, a file in use, or permissions).",
}


class Refusal(Exception):
    def __init__(self, code, detail, **extra):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.extra = code, detail, extra


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fnv1a64(data: bytes) -> int:
    h = 0xCBF29CE484222325
    for x in data:
        h = ((h ^ x) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def version_key(v: str):
    parts = re.split(r"[-+]", v, 1)[0].split(".")
    return tuple(int(p) for p in parts) + (0,) * (4 - len(parts))


# ---------------------------------------------------------------------------------------------------------------
# Paths

def resolve_paths(a) -> dict:
    home = a.home or os.environ.get("R3HD_HOME") or ""
    if home:
        home = Path(os.path.abspath(home))
        d = {"home": home, "mods": home / "mods", "cache": home / "cache" / "mods", "game": home / "data" / "content"}
    else:
        d = {"home": None, "mods": ROOT / "private" / "play" / "mods", "cache": ROOT / "private" / "play" / "cache" / "mods",
             "game": ROOT / "private" / "extracted" / TITLE_ID}
    if os.environ.get("R3HD_GAME_DIR"):
        d["game"] = Path(os.environ["R3HD_GAME_DIR"])
    for key, opt in (("mods", "mods_root"), ("cache", "cache"), ("game", "game_dir")):
        if getattr(a, opt, None):
            d[key] = Path(os.path.abspath(getattr(a, opt)))
    return d


def port_version(paths) -> str:
    """The installed version (installer.json) or, in the repository, the payload definition's version."""
    candidates = []
    if paths.get("home"):
        candidates.append(paths["home"] / "installer.json")
    # An installed copy runs from HOME\app\tools (HOME\installer.json); a staged payload from PAYLOAD\app\tools
    # (PAYLOAD\payload.json); the repository has the payload definition.
    candidates += [ROOT.parent / "installer.json", ROOT.parent / "payload.json",
                   ROOT / "config" / "release" / "payload.json"]
    for c in candidates:
        try:
            return str(json.loads(c.read_text(encoding="utf-8"))["version"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return "0.0.0"


def release_ids(paths) -> list:
    """Which supported release the game data is. An installation records it (data\\intake.json); the repository
    layout is the one supported release by construction (M27)."""
    rec = None
    if paths.get("home"):
        try:
            rec = json.loads((paths["home"] / "data" / "intake.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rec = None
    if isinstance(rec, dict) and isinstance(rec.get("release"), str):
        return [rec["release"]]
    try:
        rel = json.loads((ROOT / "config" / "intake" / "known_releases.json").read_text(encoding="utf-8"))
        return [r["id"] for r in rel["releases"]]
    except (OSError, ValueError, KeyError):
        return []


# ---------------------------------------------------------------------------------------------------------------
# Package intake: a folder or a .zip, read without following links and copied file by file.

def check_member_name(rel: str):
    if not rel or len(rel) > MAX_NAME or "\\" in rel or ":" in rel or rel.startswith("/") or "\0" in rel:
        raise Refusal("UNSAFE_PACKAGE", f"path not allowed: {rel!r}")
    parts = rel.split("/")
    if len(parts) > MAX_DEPTH:
        raise Refusal("UNSAFE_PACKAGE", f"path too deep: {rel!r}")
    for p in parts:
        # A device name stays reserved with spaces before its extension ("nul .txt"; M33 review).
        if p in ("", ".", "..") or not NAME_RE.match(p) or p.endswith((".", " ")) \
                or p.split(".")[0].rstrip(" ").lower() in RESERVED:
            raise Refusal("UNSAFE_PACKAGE", f"path not allowed: {rel!r}")


def check_member_type(rel: str):
    ext = os.path.splitext(rel)[1].lower()
    if ext not in ALLOWED_EXT:
        raise Refusal("UNSAFE_PACKAGE", f"file type not allowed in a data mod: {rel!r}")


def read_package(source: Path) -> dict:
    """{relative path: bytes} of a package, with the mod at its root. Every check fails closed."""
    files = {}
    total = 0
    st = os.lstat(source)
    if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & 0x400:
        raise Refusal("UNSAFE_PACKAGE", "the package is a link")
    if stat.S_ISDIR(st.st_mode):
        for dirpath, dirnames, filenames in os.walk(source, followlinks=False):
            for name in dirnames + filenames:
                p = Path(dirpath) / name
                s = os.lstat(p)
                if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
                    raise Refusal("UNSAFE_PACKAGE", f"links are not allowed: {p.relative_to(source).as_posix()}")
            for name in filenames:
                p = Path(dirpath) / name
                rel = p.relative_to(source).as_posix()
                check_member_name(rel)
                check_member_type(rel)
                s = os.lstat(p)
                if not stat.S_ISREG(s.st_mode):
                    raise Refusal("UNSAFE_PACKAGE", f"not a plain file: {rel}")
                if s.st_size > MAX_FILE_BYTES:
                    raise Refusal("TOO_LARGE", f"{rel} is {s.st_size} bytes")
                total += s.st_size
                if total > MAX_TOTAL_BYTES or len(files) >= MAX_FILES:
                    raise Refusal("TOO_LARGE", "the package exceeds the size or file-count limit")
                files[rel] = p.read_bytes()
    elif stat.S_ISREG(st.st_mode) and source.suffix.lower() == ".zip":
        try:
            zf = zipfile.ZipFile(source)
        except (zipfile.BadZipFile, OSError) as e:
            raise Refusal("UNSAFE_PACKAGE", f"not a readable zip: {e}")
        with zf:
            infos = zf.infolist()
            if len(infos) > MAX_FILES * 2:
                raise Refusal("TOO_LARGE", "too many entries")
            seen = set()
            for info in infos:
                rel = info.filename
                mode = (info.external_attr >> 16) & 0o170000
                if mode == stat.S_IFLNK:
                    raise Refusal("UNSAFE_PACKAGE", f"links are not allowed: {rel!r}")
                if info.flag_bits & 0x1:
                    raise Refusal("UNSAFE_PACKAGE", f"encrypted entries are not allowed: {rel!r}")
                if rel.endswith("/"):
                    check_member_name(rel.rstrip("/"))
                    continue
                check_member_name(rel)
                check_member_type(rel)
                key = rel.lower()
                if key in seen:
                    raise Refusal("UNSAFE_PACKAGE", f"duplicate name: {rel!r}")
                seen.add(key)
                if info.file_size > MAX_FILE_BYTES:
                    raise Refusal("TOO_LARGE", f"{rel} is {info.file_size} bytes")
                if info.file_size > (1 << 20) and info.file_size > MAX_RATIO * max(info.compress_size, 1):
                    raise Refusal("TOO_LARGE", f"{rel} expands {info.file_size // max(info.compress_size, 1)} times")
                total += info.file_size
                if total > MAX_TOTAL_BYTES or len(files) >= MAX_FILES:
                    raise Refusal("TOO_LARGE", "the package exceeds the size or file-count limit")
                with zf.open(info) as f:
                    data = f.read(MAX_FILE_BYTES + 1)  # the header's size is not trusted
                if len(data) != info.file_size:
                    raise Refusal("UNSAFE_PACKAGE", f"{rel}: size does not match its header")
                files[rel] = data
    else:
        raise Refusal("NOT_A_MOD", "choose a mod folder or a .zip file")
    if "mod.json" not in files:
        tops = {r.split("/")[0] for r in files}
        if len(tops) == 1 and "/" in next(iter(files), "") and f"{next(iter(tops))}/mod.json" in files:
            top = next(iter(tops)) + "/"
            files = {r[len(top):]: b for r, b in files.items()}
        else:
            raise Refusal("NOT_A_MOD", "mod.json missing")
    seen = set()
    for r in files:
        if r.lower() in seen:
            raise Refusal("UNSAFE_PACKAGE", f"duplicate name: {r!r}")
        seen.add(r.lower())
    return files


# ---------------------------------------------------------------------------------------------------------------
# Manifest

TOP_KEYS = {"format", "id", "name", "version", "description", "authors", "license", "website", "target", "requires",
            "conflicts", "overrides"}
TARGET_KEYS = {"title_id", "releases", "min_port_version"}
TEXTURE_KEYS = {"type", "entry", "bundles", "image"}
TEXT_KEYS = {"type", "file", "offset", "slot_sha256", "text"}
GLYPH_KEYS = {"type", "char", "width", "height", "descent", "layers"}


def _int(o, key, lo, hi, where):
    v = o.get(key)
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise Refusal("BAD_MANIFEST", f"{where}: '{key}' must be a whole number from {lo} to {hi}")
    return v


def parse_glyph(o: dict, files: dict, where: str):
    """M34: checks one glyph override's shape (no game data needed)."""
    if set(o) - GLYPH_KEYS or not isinstance(o.get("char"), str) or o["char"] not in GLYPH_CODES:
        raise Refusal("UNSUPPORTED", f"{where}: a glyph needs 'char' (one of {''.join(GLYPH_CODES)}), 'width', 'height', "
                      "'descent' and 'layers'")
    w = _int(o, "width", 1, GLYPH_MAX_SIDE, where)
    h = _int(o, "height", 1, GLYPH_MAX_SIDE, where)
    _int(o, "descent", -32, 32, where)
    layers = o.get("layers")
    if not isinstance(layers, list) or not 1 <= len(layers) <= 8:
        raise Refusal("BAD_MANIFEST", f"{where}: 'layers' must list 1 to 8 layers")
    for j, ly in enumerate(layers):
        lw = f"{where}.layers[{j}]"
        if not isinstance(ly, dict) or len({"glyph", "bitmap", "image"} & set(ly)) != 1:
            raise Refusal("BAD_MANIFEST", f"{lw}: a layer is one of 'glyph', 'bitmap' or 'image'")
        if set(ly) - {"glyph", "bitmap", "image", "crop", "x", "y"} or ("crop" in ly and "glyph" not in ly):
            raise Refusal("BAD_MANIFEST", f"{lw}: unknown keys")
        _int(ly, "x", -GLYPH_MAX_SIDE, GLYPH_MAX_SIDE, lw)
        _int(ly, "y", -GLYPH_MAX_SIDE, GLYPH_MAX_SIDE, lw)
        if "glyph" in ly:
            g = ly["glyph"]
            if not isinstance(g, str) or len(g) != 1 or g in GLYPH_CODES:
                raise Refusal("BAD_MANIFEST", f"{lw}: 'glyph' must be one character of the game's font")
            try:
                g.encode("cp1252")
            except UnicodeEncodeError:
                raise Refusal("BAD_MANIFEST", f"{lw}: 'glyph' {g!r} is not a character of the game's font")
            c = ly.get("crop")
            if c is not None and (not isinstance(c, list) or len(c) != 4 or not all(
                    isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 512 for v in c) or c[0] >= c[2] or c[1] >= c[3]):
                raise Refusal("BAD_MANIFEST", f"{lw}: 'crop' must be [x0, y0, x1, y1] inside the glyph")
        elif "bitmap" in ly:
            b = ly["bitmap"]
            if not isinstance(b, list) or not 1 <= len(b) <= GLYPH_MAX_SIDE or not all(
                    isinstance(r, str) and 1 <= len(r) <= GLYPH_MAX_SIDE and len(r) == len(b[0])
                    and all(ch in BITMAP_LEVELS for ch in r) for r in b):
                raise Refusal("BAD_MANIFEST", f"{lw}: 'bitmap' must be rows of equal length using {BITMAP_LEVELS!r}")
        else:
            if not isinstance(ly["image"], str) or ly["image"] not in files or not ly["image"].lower().endswith(".png"):
                raise Refusal("BAD_MANIFEST", f"{lw}: 'image' must name a .png file of the package")
    return w, h


def _str(m, key, limit, required=True):
    v = m.get(key)
    if v is None and not required:
        return None
    if not isinstance(v, str) or not v.strip() or len(v) > limit or any(ord(c) < 0x20 and c not in "\n\t" for c in v):
        raise Refusal("BAD_MANIFEST", f"'{key}' must be a text of at most {limit} characters")
    return v


def parse_manifest(files: dict) -> dict:
    raw = files["mod.json"]
    if len(raw) > (1 << 20):
        raise Refusal("BAD_MANIFEST", "mod.json is too large")
    try:
        m = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as e:
        raise Refusal("BAD_MANIFEST", f"mod.json is not JSON: {e}")
    if not isinstance(m, dict):
        raise Refusal("BAD_MANIFEST", "mod.json must be an object")
    unknown = set(m) - TOP_KEYS
    if unknown:
        raise Refusal("BAD_MANIFEST", f"unknown keys {sorted(unknown)}")
    if m.get("format") != FORMAT:
        raise Refusal("UNSUPPORTED", f"mod format {m.get('format')!r}; this port reads format {FORMAT}")
    if not isinstance(m.get("id"), str) or not ID_RE.match(m["id"]):
        raise Refusal("BAD_MANIFEST", "'id' must be 2-64 characters of a-z 0-9 . _ - (lower case)")
    _str(m, "name", 80)
    if not isinstance(m.get("version"), str) or not VERSION_RE.match(m["version"]):
        raise Refusal("BAD_MANIFEST", "'version' must look like 1.0.0")
    _str(m, "description", 2000, required=False)
    _str(m, "license", 200, required=False)
    _str(m, "website", 300, required=False)
    if "authors" in m and (not isinstance(m["authors"], list) or len(m["authors"]) > 32
                           or not all(isinstance(x, str) and 0 < len(x) <= 80 for x in m["authors"])):
        raise Refusal("BAD_MANIFEST", "'authors' must be a list of names")
    t = m.get("target")
    if not isinstance(t, dict) or set(t) - TARGET_KEYS or t.get("title_id") != TITLE_ID:
        raise Refusal("INCOMPATIBLE", f"'target.title_id' must be {TITLE_ID} (Rayman 3 HD, Xbox 360)")
    if not isinstance(t.get("releases"), list) or not t["releases"] or not all(isinstance(r, str) for r in t["releases"]):
        raise Refusal("BAD_MANIFEST", "'target.releases' must list the supported game releases")
    if not isinstance(t.get("min_port_version"), str) or not VERSION_RE.match(t["min_port_version"]):
        raise Refusal("BAD_MANIFEST", "'target.min_port_version' must look like 0.33.0")
    for key in ("requires", "conflicts"):
        v = m.get(key, [])
        if not isinstance(v, list) or len(v) > 32 or not all(isinstance(x, str) and ID_RE.match(x) for x in v) \
                or m["id"] in v:
            raise Refusal("BAD_MANIFEST", f"'{key}' must be a list of other mod IDs")
    ov = m.get("overrides")
    if not isinstance(ov, list) or not ov or len(ov) > MAX_OVERRIDES:
        raise Refusal("BAD_MANIFEST", "'overrides' must be a non-empty list")
    for i, o in enumerate(ov):
        where = f"overrides[{i}]"
        if not isinstance(o, dict):
            raise Refusal("BAD_MANIFEST", f"{where} must be an object")
        if o.get("type") == "texture":
            if set(o) - TEXTURE_KEYS or not isinstance(o.get("entry"), str) or not isinstance(o.get("image"), str):
                raise Refusal("BAD_MANIFEST", f"{where}: a texture needs 'entry' and 'image' (and optional 'bundles')")
            if not re.match(r"^[A-Za-z0-9_ \\.-]{1,120}\.dds$", o["entry"]) or ".." in o["entry"]:
                raise Refusal("BAD_MANIFEST", f"{where}: 'entry' must be a bundle entry name such as menu\\\\mnu_fix.dds")
            if o["image"] not in files or not o["image"].lower().endswith(".png"):
                raise Refusal("BAD_MANIFEST", f"{where}: 'image' must name a .png file of the package")
            b = o.get("bundles", "all")
            if b != "all" and (not isinstance(b, list) or not b or len(b) > 256
                               or not all(isinstance(x, str) and re.match(r"^[A-Za-z0-9_/]{1,120}$", x) and ".." not in x
                                          for x in b)):
                raise Refusal("BAD_MANIFEST", f"{where}: 'bundles' must be \"all\" or a list such as GAMEDATAbin/fix")
        elif o.get("type") == "text":
            if set(o) - TEXT_KEYS or o.get("file") != "GAMEDATAbin/fix.lvl":
                raise Refusal("UNSUPPORTED", f"{where}: text overrides are supported in GAMEDATAbin/fix.lvl only")
            if not isinstance(o.get("offset"), int) or isinstance(o["offset"], bool) or o["offset"] < 4 or o["offset"] % 4:
                raise Refusal("BAD_MANIFEST", f"{where}: 'offset' must be the string's 4-aligned byte offset")
            if not isinstance(o.get("slot_sha256"), str) or not re.match(r"^[0-9a-f]{64}$", o["slot_sha256"]):
                raise Refusal("BAD_MANIFEST", f"{where}: 'slot_sha256' must be the 64-digit SHA-256 from text-find")
            if not isinstance(o.get("text"), str) or not o["text"] or len(o["text"]) > 1000:
                raise Refusal("BAD_MANIFEST", f"{where}: 'text' must be a non-empty text")
            # the shape only (glyph characters are checked against the glyphs at compile time; M34 review: Ý stays valid)
            encode_text("".join(c for c in o["text"] if c not in GLYPH_CODES) or " ")
        elif o.get("type") == "glyph":
            parse_glyph(o, files, where)
        elif o.get("type") == "subtitle":
            parse_subtitle(o, where)
        else:
            raise Refusal("UNSUPPORTED", f"{where}: type {o.get('type')!r} (supported: texture, text, glyph, subtitle)")
    chars = [o["char"] for o in ov if o["type"] == "glyph"]
    if len(chars) != len(set(chars)):
        raise Refusal("BAD_MANIFEST", "the same glyph twice")
    texts = [o["offset"] for o in ov if o["type"] == "text"]
    if len(texts) != len(set(texts)):
        raise Refusal("BAD_MANIFEST", "the same text offset twice")
    subs = [o["id"] for o in ov if o["type"] == "subtitle"]
    if len(subs) != len(set(subs)):
        raise Refusal("BAD_MANIFEST", "the same subtitle id twice")
    return m


def glyph_chars(m: dict) -> frozenset:
    return frozenset(o["char"] for o in m["overrides"] if o["type"] == "glyph")


def encode_text(text: str, glyphs=frozenset(), defined=None) -> bytes:
    """Text -> the game's 8-bit bytes. Extra letters/punctuation use their Windows-1252/1254 bytes, only when
    `glyphs` holds them (a glyph override of this mod or of a mod it requires). The Latin-1 letters whose bytes those
    glyphs take (Ð Ý Þ ð ý þ) are then refused. With `defined` (the codes FontRay defines, plus the glyphs) every byte
    must have a glyph."""
    missing = sorted({c for c in text if c in GLYPH_CODES and c not in glyphs})
    if missing:
        raise Refusal("TEXT_GLYPH_MISSING", f"{''.join(missing)}: the game's font has no glyph for these letters; a "
                      "glyph override must add them (in this mod or a mod it requires; RE_NOTES M34)")
    taken = {GLYPH_CODES[c] for c in glyphs}
    out = bytearray()
    for c in text:
        o = ord(c)
        if c in GLYPH_CODES:
            out.append(GLYPH_CODES[c])
        elif (0x20 <= o <= 0x7E or 0xA0 <= o <= 0xFF) and o not in taken:
            out.append(o)  # ASCII and Latin-1 = Windows-1252 in this range
        else:
            raise Refusal("TEXT_GLYPH_MISSING", f"character U+{o:04X} is outside the game's 8-bit text range"
                          + (" (its byte is a Turkish glyph here)" if o in taken else ""))
    if defined is not None:
        # The backslash starts the game's in-band codes (\l line break, \jc centre, \f1: font ...): never drawn.
        bad = sorted({chr(b) if b < 0x80 else bytes([b]).decode("cp1252", "replace") for b in out
                      if b not in defined and b not in taken and b != 0x5C})
        if bad:
            raise Refusal("TEXT_GLYPH_MISSING", f"{''.join(bad)}: the game's font has no glyph for these characters")
    return bytes(out)


def check_compat(m: dict, paths) -> None:
    rels = release_ids(paths)
    if not set(m["target"]["releases"]) & set(rels):
        raise Refusal("INCOMPATIBLE", f"made for {m['target']['releases']}, the game data is {rels}")
    pv = port_version(paths)
    if version_key(pv) < version_key(m["target"]["min_port_version"]):
        raise Refusal("INCOMPATIBLE", f"needs port version {m['target']['min_port_version']} or newer, this is {pv}")


# ---------------------------------------------------------------------------------------------------------------
# PNG (8-bit RGB / RGBA, not interlaced), decoded with the standard library.

def read_png(data: bytes):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise Refusal("BAD_IMAGE", "not a PNG")
    pos, ihdr, idat = 8, None, []
    while pos + 8 <= len(data):
        n, kind = struct.unpack_from(">I4s", data, pos)
        body = data[pos + 8:pos + 8 + n]
        if len(body) != n or pos + 12 + n > len(data):
            raise Refusal("BAD_IMAGE", "truncated PNG")
        if zlib.crc32(kind + body) & 0xFFFFFFFF != struct.unpack_from(">I", data, pos + 8 + n)[0]:
            raise Refusal("BAD_IMAGE", "PNG chunk checksum")
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + n
    if not ihdr:
        raise Refusal("BAD_IMAGE", "PNG without header")
    w, h, depth, ctype, comp, filt, interlace = ihdr
    if depth != 8 or ctype not in (2, 6) or comp or filt or interlace:
        raise Refusal("BAD_IMAGE", "only 8-bit RGB / RGBA PNGs without interlacing are supported")
    if not (1 <= w <= MAX_PNG_SIDE and 1 <= h <= MAX_PNG_SIDE):
        raise Refusal("BAD_IMAGE", f"PNG size {w}x{h}")
    bpp = 4 if ctype == 6 else 3
    stride = w * bpp
    expect = h * (stride + 1)
    d = zlib.decompressobj()
    raw = d.decompress(b"".join(idat), expect + 1)
    if len(raw) != expect or d.unconsumed_tail:
        raise Refusal("BAD_IMAGE", "PNG data size")
    out = bytearray(w * h * 4)
    prev = bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif f == 2:
            line = bytearray((a + b) & 0xFF for a, b in zip(line, prev))
        elif f == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        elif f != 0:
            raise Refusal("BAD_IMAGE", f"PNG filter {f}")
        if bpp == 4:
            out[y * w * 4:(y + 1) * w * 4] = line
        else:
            row = out[y * w * 4:(y + 1) * w * 4]
            row[0::4], row[1::4], row[2::4] = line[0::3], line[1::3], line[2::3]
            row[3::4] = b"\xff" * w
            out[y * w * 4:(y + 1) * w * 4] = row
        prev = line
    return w, h, bytes(out)


def write_png(w: int, h: int, rgba: bytes) -> bytes:
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


# ---------------------------------------------------------------------------------------------------------------
# DXT encode / decode and the console's linear mip layout (pinned SDK texture util, RE_NOTES "M26" / "M33").

def _565(r, g, b):
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def _rgb(c):
    r, g, b = c >> 11, (c >> 5) & 63, c & 31
    return (r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31


def encode_colour(px):
    """px: 16 (r, g, b) tuples -> 8-byte DXT1 colour block (4-colour mode), little-endian."""
    lo = [min(p[i] for p in px) for i in range(3)]
    hi = [max(p[i] for p in px) for i in range(3)]
    # The box's diagonal that follows the colours: a channel falling while the widest one rises swaps its ends.
    d = max(range(3), key=lambda i: hi[i] - lo[i])
    mean = [sum(p[i] for p in px) / 16 for i in range(3)]
    for i in range(3):
        if i != d and sum((p[d] - mean[d]) * (p[i] - mean[i]) for p in px) < 0:
            lo[i], hi[i] = hi[i], lo[i]
    c0, c1 = _565(*hi), _565(*lo)
    if c0 < c1:
        c0, c1 = c1, c0
    if c0 == c1:
        return struct.pack("<HHI", c0, c1, 0)
    e0, e1 = _rgb(c0), _rgb(c1)
    pal = [e0, e1, tuple((2 * a + b + 1) // 3 for a, b in zip(e0, e1)), tuple((a + 2 * b + 1) // 3 for a, b in zip(e0, e1))]
    idx = 0
    for i, p in enumerate(px):
        best = min(range(4), key=lambda k: (p[0] - pal[k][0]) ** 2 + (p[1] - pal[k][1]) ** 2 + (p[2] - pal[k][2]) ** 2)
        idx |= best << (2 * i)
    return struct.pack("<HHI", c0, c1, idx)


def encode_colour_punch(px, alphas):
    """DXT1 with 1-bit alpha (M33 review: cut-outs must stay cut out): a block with a texel below alpha 128 uses the
    three-colour mode (c0 <= c1), index 3 = transparent."""
    if all(a >= 128 for a in alphas):
        return encode_colour(px)
    solid = [p for p, a in zip(px, alphas) if a >= 128]
    if not solid:
        return struct.pack("<HHI", 0, 0, 0xFFFFFFFF)
    lo = [min(p[i] for p in solid) for i in range(3)]
    hi = [max(p[i] for p in solid) for i in range(3)]
    c0, c1 = sorted((_565(*lo), _565(*hi)))  # c0 <= c1 selects the three-colour mode
    e0, e1 = _rgb(c0), _rgb(c1)
    pal = [e0, e1, tuple((a + b) // 2 for a, b in zip(e0, e1))]
    idx = 0
    for i, (p, a) in enumerate(zip(px, alphas)):
        k = 3 if a < 128 else min(range(3), key=lambda k: sum((p[j] - pal[k][j]) ** 2 for j in range(3)))
        idx |= k << (2 * i)
    return struct.pack("<HHI", c0, c1, idx)


def encode_alpha(alphas):
    a0, a1 = max(alphas), min(alphas)
    if a0 == a1:
        return bytes([a0, a1, 0, 0, 0, 0, 0, 0])
    pal = [a0, a1] + [((7 - k) * a0 + k * a1 + 3) // 7 for k in range(1, 7)]
    bits = 0
    for i, a in enumerate(alphas):
        best = min(range(8), key=lambda k: abs(a - pal[k]))
        bits |= best << (3 * i)
    return bytes([a0, a1]) + bits.to_bytes(6, "little")


def encode_level(w, h, rgba, fmt):
    """Upright RGBA -> blocks in storage order (bottom block row first, the bundle convention), little-endian."""
    bw, bh = (w + 3) // 4, (h + 3) // 4
    rows = []
    for by in range(bh):
        out = bytearray()
        for bx in range(bw):
            px, al = [], []
            for ty in range(4):
                # storage is bottom row first: stored texel row ty of block row by is image row h-1-(4*by+ty)
                y = h - 1 - min(4 * by + ty, h - 1)
                for tx in range(4):
                    x = min(4 * bx + tx, w - 1)
                    o = (y * w + x) * 4
                    px.append((rgba[o], rgba[o + 1], rgba[o + 2]))
                    al.append(rgba[o + 3])
            if fmt == "DXT5":
                out += encode_alpha(al) + encode_colour(px)
            else:
                out += encode_colour_punch(px, al)
        rows.append(bytes(out))
    return rows


def decode_level(w, h, blocks_rows, fmt):
    """Inverse of encode_level (for export and the selftest): storage rows -> upright RGBA."""
    out = bytearray(w * h * 4)
    bpb = 16 if fmt == "DXT5" else 8
    for by, row in enumerate(blocks_rows):
        for bx in range(len(row) // bpb):
            blk = row[bx * bpb:(bx + 1) * bpb]
            if fmt == "DXT5":
                a0, a1 = blk[0], blk[1]
                apal = [a0, a1] + ([((7 - k) * a0 + k * a1 + 3) // 7 for k in range(1, 7)] if a0 > a1 else
                                   [((5 - k) * a0 + k * a1 + 2) // 5 for k in range(1, 5)] + [0, 255])
                abits = int.from_bytes(blk[2:8], "little")
                cblk = blk[8:]
            else:
                apal, abits, cblk = None, 0, blk
            c0, c1, idx = struct.unpack("<HHI", cblk)
            e0, e1 = _rgb(c0), _rgb(c1)
            if c0 > c1 or fmt == "DXT5":
                pal = [e0 + (255,), e1 + (255,), tuple((2 * a + b + 1) // 3 for a, b in zip(e0, e1)) + (255,),
                       tuple((a + 2 * b + 1) // 3 for a, b in zip(e0, e1)) + (255,)]
            else:
                pal = [e0 + (255,), e1 + (255,), tuple((a + b) // 2 for a, b in zip(e0, e1)) + (255,), (0, 0, 0, 0)]
            for t in range(16):
                ty, tx = divmod(t, 4)
                y, x = h - 1 - (4 * by + ty), 4 * bx + tx
                if y < 0 or x >= w:
                    continue
                c = pal[(idx >> (2 * t)) & 3]
                a = apal[(abits >> (3 * t)) & 7] if apal else c[3]
                o = (y * w + x) * 4
                out[o:o + 4] = bytes((c[0], c[1], c[2], a))
    return bytes(out)


def downsample(w, h, rgba):
    nw, nh = max(w // 2, 1), max(h // 2, 1)
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        for x in range(nw):
            for c in range(4):
                s = n = 0
                for dy in (0, 1):
                    for dx in (0, 1):
                        sx, sy = min(2 * x + dx, w - 1), min(2 * y + dy, h - 1)
                        s += rgba[(sy * w + sx) * 4 + c]
                        n += 1
                out[(y * nw + x) * 4 + c] = (s + n // 2) // n
    return nw, nh, bytes(out)


def _align(v, a):
    return (v + a - 1) // a * a


def _next_pow2(v):
    return 1 << (v - 1).bit_length() if v > 1 else 1


def _log2_ceil(v):
    return (v - 1).bit_length()


def packed_mip_offset(w, h, mip):
    """Pinned SDK GetPackedMipOffset for a 2D texture, in texels (x, y)."""
    lw, lh = _log2_ceil(w), _log2_ceil(h)
    ls = min(lw, lh)
    base = ls - 4 if ls > 4 else 0
    pm = mip - base
    if pm < 3:
        return (0, 16 >> pm) if lw > lh else (16 >> pm, 0)
    if lw > lh:
        return ((1 << (lw - base)) >> (pm - 2), 0)
    return (0, (1 << (lh - base)) >> (pm - 2))


def layout(w, h, fmt):
    """Byte layout of a linear 2D texture with a full mip chain in the bundle: base blob size and, for every level
    1..max, (blob, byte offset of its area, row pitch in bytes, x blocks, y blocks, width, height)."""
    bpb = 16 if fmt == "DXT5" else 8
    bw, bh = (w + 3) // 4, (h + 3) // 4
    base_pitch = _align(_align(bw, 32) * bpb, 256)
    base_size = base_pitch * _align(bh, 32)
    levels = [(0, 0, base_pitch, 0, 0, w, h)]
    ls = _log2_ceil(min(w, h))
    if ls <= 4:
        # the base level itself sits in a packed tail (a side of 16 texels or less): not supported here
        return None, None, levels
    packed = ls - 4
    max_level = max(w, h).bit_length() - 1
    offset = 0
    tail = None
    for lv in range(1, max_level + 1):
        lw, lh = max(w >> lv, 1), max(h >> lv, 1)
        if lv >= packed:
            if tail is None:
                tail = (offset, lv)
                pitch_t = max(_next_pow2(w) >> lv, 1)
                rows_t = max(_next_pow2(h) >> lv, 1)
                tp = _align(_align((pitch_t + 3) // 4, 32) * bpb, 256)
                tail_stride = _align(tp * _align((rows_t + 3) // 4, 32), 4096)
                tail_pitch = tp
                offset += tail_stride
            x, y = packed_mip_offset(w, h, lv)
            levels.append((1, tail[0], tail_pitch, x // 4, y // 4, lw, lh))
            continue
        pitch_t = max(_next_pow2(w) >> lv, 1)
        rows_t = max(_next_pow2(h) >> lv, 1)
        p = _align(_align((pitch_t + 3) // 4, 32) * bpb, 256)
        stride = _align(p * _align((rows_t + 3) // 4, 32), 4096)
        levels.append((1, offset, p, 0, 0, lw, lh))
        offset += stride
    return base_size, offset, levels


# ---------------------------------------------------------------------------------------------------------------
# Game data: bundles and texture records

def bhf_entries(path: Path):
    b = path.read_bytes()
    if len(b) < 4:
        return []
    n, = struct.unpack_from(">I", b, 0)
    if len(b) != 4 + n * 0x114:
        return []
    out = []
    for i in range(n):
        o = 4 + i * 0x114
        s1, o1, s2, o2 = struct.unpack_from(">4I", b, o)
        out.append((b[o + 16:o + 0x114].split(b"\0")[0].decode("latin1"), s1, o1, s2, o2))
    return out


def bundle_level_file(bhf: Path) -> Path:
    stem = bhf.stem
    m = re.match(r"^(.*)_\d+$", stem)
    return bhf.with_name((m.group(1) if m else stem) + ".lvl")


def texture_record(lvl: Path, entry: str):
    """(width, height, flags) of the texture record named like the entry (`.tga`), or None if absent / ambiguous."""
    name = entry[:-4].encode("latin1").lower() + b".tga"
    d = lvl.read_bytes()
    low = d.lower()
    found = set()
    start = 0
    while True:
        i = low.find(name, start)
        if i < 0:
            break
        start = i + 1
        if d[i - 1:i] not in (b"\0", b"\\") and i > 0:
            continue
        s = d.rfind(b"\0", 0, i) + 1
        if d[s:i + len(name)].lower() != name or d[i + len(name):i + len(name) + 1] != b"\0" or s < 0x4A:
            continue
        rec = s - 0x4A
        hh, ww = struct.unpack_from(">HH", d, rec + 0x1C)
        flags, = struct.unpack_from(">I", d, rec + 0x14)
        found.add((ww, hh, flags))
    return found.pop() if len(found) == 1 else None


def all_bundles(game: Path):
    return sorted(game.rglob("*.bhf"))


def resolve_texture(game: Path, o: dict):
    """Every (bhf path, entry tuple, w, h, fmt) the texture override addresses."""
    entry = o["entry"]
    if o.get("bundles", "all") == "all":
        bhfs = all_bundles(game)
    else:
        bhfs = []
        for b in o["bundles"]:
            p = game.joinpath(*b.split("/")).with_suffix(".bhf")
            if not p.is_file():
                raise Refusal("TARGET_MISSING", f"bundle {b} not found")
            bhfs.append(p)
    hits = []
    for bhf in bhfs:
        for e in bhf_entries(bhf):
            if e[0].lower() == entry.lower():
                lvl = bundle_level_file(bhf)
                rec = texture_record(lvl, e[0]) if lvl.is_file() else None
                if not rec:
                    raise Refusal("UNSUPPORTED", f"{entry} in {bhf.name}: no unique texture record in {lvl.name}")
                w, h, flags = rec
                fmt = "DXT5" if flags & 0x8 else "DXT1"
                base, mips, _ = layout(w, h, fmt)
                if (base, mips) != (e[1], e[3]):
                    raise Refusal("UNSUPPORTED", f"{entry} in {bhf.name}: {w}x{h} {fmt} does not match the stored "
                                  f"sizes {e[1]} / {e[3]} (layout {base} / {mips})")
                hits.append((bhf, e, w, h, fmt))
        if o.get("bundles", "all") != "all" and not any(h[0] == bhf for h in hits):
            raise Refusal("TARGET_MISSING", f"{entry} is not in {bhf.relative_to(game).as_posix()}")
    if not hits:
        raise Refusal("TARGET_MISSING", f"no bundle holds {entry}")
    return hits


def encoded_levels(cache: Path, png: bytes, w, h, fmt):
    """Encoded block rows of every level of an image, cached by content (encoding is slow in pure Python)."""
    key = sha256_bytes(png + f"|{w}x{h}|{fmt}|v2".encode())
    cdir = cache / "encoded"
    cf = cdir / f"{key}.json"
    if cf.is_file():
        try:
            return [[bytes.fromhex(r) for r in lv] for lv in json.loads(cf.read_text())]
        except (ValueError, OSError):
            pass
    if png[:8] == b"\x89PNG\r\n\x1a\n" and png[12:16] == b"IHDR" and struct.unpack_from(">II", png, 16) != (w, h):
        raise Refusal("BAD_IMAGE", f"the image is {'x'.join(map(str, struct.unpack_from('>II', png, 16)))}; "
                      f"the texture is {w}x{h}")  # before decoding (M33 review: decoding is slow in pure Python)
    pw, ph, rgba = read_png(png)
    if (pw, ph) != (w, h):
        raise Refusal("BAD_IMAGE", f"the image is {pw}x{ph}; the texture is {w}x{h}")
    out = []
    lw, lh, img = w, h, rgba
    _, _, lay = layout(w, h, fmt)
    for i in range(len(lay)):
        if i:
            lw, lh, img = downsample(lw, lh, img)
        out.append(encode_level(lw, lh, img, fmt))
    cdir.mkdir(parents=True, exist_ok=True)
    tmp = cf.with_suffix(".tmp")
    tmp.write_text(json.dumps([[r.hex() for r in lv] for lv in out]))
    os.replace(tmp, cf)
    return out


def swap16(b: bytes) -> bytes:
    a = bytearray(b)
    a[0::2], a[1::2] = b[1::2], b[0::2]
    return bytes(a)


def place_levels(orig: list, levels_rows, lay, fmt):
    """Writes encoded levels into copies of the original blobs (padding bytes stay the game's own)."""
    bpb = 16 if fmt == "DXT5" else 8
    blobs = [bytearray(orig[0]), bytearray(orig[1])]
    for (blob, off, pitch, x0, y0, lw, lh), rows in zip(lay, levels_rows):
        for j, row in enumerate(rows):
            at = off + (y0 + j) * pitch + x0 * bpb
            if at + len(row) > len(blobs[blob]):
                raise Refusal("UNSUPPORTED", "a mip level falls outside its blob")
            blobs[blob][at:at + len(row)] = swap16(row)
    return bytes(blobs[0]), bytes(blobs[1])


def text_slot(data: bytes, offset: int):
    if offset >= len(data) or data[offset - 1] != 0:
        raise Refusal("TARGET_CHANGED", f"offset {offset} is not the start of a string")
    end = data.find(b"\0", offset)
    if end <= offset or end - offset > 4096:
        raise Refusal("TARGET_CHANGED", f"no string at offset {offset}")
    # Only text is text: every byte of the original a printable 8-bit character (M33 review: a NUL-delimited run of
    # other data must not be a target). Strings with control bytes are not targets in format 1.
    if any(b < 0x20 or b == 0x7F for b in data[offset:end]):
        raise Refusal("UNSUPPORTED", f"the bytes at {offset} are not a plain text string")
    slot_end = _align(end + 1, 4)
    if any(data[end:slot_end]):
        raise Refusal("TARGET_CHANGED", f"the string at {offset} has no padding")
    return data[offset:slot_end]


# ---------------------------------------------------------------------------------------------------------------
# M34: the font (glyph records and atlas) and the language-table pointers

def font_records(fix: bytes, base: int) -> list:
    t = base + 50
    return [struct.unpack_from(">6H2B", fix, t + c * 14) for c in range(256)]


def read_font(fix: bytes):
    """{"ray": records of the first FontRay copy, "cells": every mapped atlas cell of the four definitions, "defined":
    codes both FontRay copies define}, or None when the definitions are not exactly the shipped ones."""
    for base, want in FONT["sha256"].items():
        if base + FONTDEF_BYTES > len(fix) or sha256_bytes(fix[base:base + FONTDEF_BYTES]) != want:
            return None
    copies = [font_records(fix, b) for b in FONT["fontray"]]
    cells = []
    for base in FONT["fontray"] + FONT["others"]:
        for x, y, h, w, _ps, _d, bm, df in font_records(fix, base):
            if df and bm == 0 and w and h:
                cells.append((x, y, x + w, y + h))
    defined = {c for c in range(256) if all(cp[c][7] for cp in copies)}
    return {"ray": copies[0], "cells": cells, "defined": defined}


def font_defined(paths):
    """FontRay's defined codes in the person's fix.lvl (None when it is not the shipped font)."""
    p = paths["game"] / "GAMEDATAbin" / "fix.lvl"
    f = read_font(p.read_bytes()) if p.is_file() else None
    return f["defined"] if f else None


def level_rows(blobs, lv, fmt):
    """Storage rows of one mip level (blob, offset, pitch, x blocks, y blocks, w, h) -> list of block rows."""
    blob, off, pitch, x0, y0, lw, lh = lv
    bpb = 16 if fmt == "DXT5" else 8
    n = (lw + 3) // 4 * bpb
    return [swap16(blobs[blob][off + (y0 + j) * pitch + x0 * bpb:off + (y0 + j) * pitch + x0 * bpb + n])
            for j in range((lh + 3) // 4)]


def encode_block(img, w, h, bx, br, fmt):
    """One block of an upright RGBA image, block column bx and upright block row br, in storage order (the block's
    bottom texel row first, as encode_level)."""
    px, al = [], []
    for ty in range(4):
        y = min(4 * br + 3 - ty, h - 1)
        for tx in range(4):
            o = (y * w + min(4 * bx + tx, w - 1)) * 4
            px.append((img[o], img[o + 1], img[o + 2]))
            al.append(img[o + 3])
    return encode_alpha(al) + encode_colour(px) if fmt == "DXT5" else encode_colour_punch(px, al)


def compose_glyph(o, font, atlas, files, aw):
    """The glyph override's picture (width x height, white with alpha) and, when it is one crop of one existing
    glyph at the origin, the atlas position it can reuse without new pixels."""
    w, h = o["width"], o["height"]
    canvas = bytearray(w * h * 4)
    for i in range(w * h):
        canvas[i * 4:i * 4 + 3] = b"\xff\xff\xff"
    alias = None
    for ly in o["layers"]:
        x0, y0 = ly["x"], ly["y"]
        if "glyph" in ly:
            code = ly["glyph"].encode("cp1252")[0]
            gx, gy, gh, gw, _ps, _d, _bm, df = font["ray"][code]
            if not df:
                raise Refusal("BAD_MANIFEST", f"glyph {o['char']}: the font has no {ly['glyph']!r}")
            c = ly.get("crop") or [0, 0, gw, gh]
            if c[2] > gw or c[3] > gh:
                raise Refusal("BAD_MANIFEST", f"glyph {o['char']}: crop {c} is outside {ly['glyph']!r} ({gw}x{gh})")
            src_w, src_h = c[2] - c[0], c[3] - c[1]
            alpha = [[atlas[((gy + c[1] + j) * aw + gx + c[0] + i) * 4 + 3] for i in range(src_w)] for j in range(src_h)]
            if len(o["layers"]) == 1 and (x0, y0, src_w, src_h) == (0, 0, w, h):
                alias = (gx + c[0], gy + c[1])
        elif "bitmap" in ly:
            alpha = [[BITMAP_LEVELS.index(ch) * 255 // (len(BITMAP_LEVELS) - 1) for ch in r] for r in ly["bitmap"]]
        else:
            iw, ih, rgba = read_png(files[ly["image"]])
            if iw > GLYPH_MAX_SIDE or ih > GLYPH_MAX_SIDE:
                raise Refusal("BAD_IMAGE", f"glyph {o['char']}: a layer image larger than {GLYPH_MAX_SIDE} px")
            alpha = [[rgba[(j * iw + i) * 4 + 3] for i in range(iw)] for j in range(ih)]
        for j, row in enumerate(alpha):
            for i, a in enumerate(row):
                if not a:
                    continue
                x, y = x0 + i, y0 + j
                if not (0 <= x < w and 0 <= y < h):
                    raise Refusal("BAD_MANIFEST", f"glyph {o['char']}: a layer reaches outside the {w}x{h} glyph")
                k = (y * w + x) * 4 + 3
                canvas[k] = canvas[k] + a * (255 - canvas[k]) // 255  # white over white: alpha "over"
    return bytes(canvas), alias


def place_glyphs(font, atlas, size, need):
    """Deterministic placement of glyph pictures in the atlas. A 4x4 block may take new pixels when no mapped cell of
    any font definition (grown by one texel) touches it and every inked texel in it belongs to no mapped glyph (an
    unmapped picture: no record of the four definitions points within two texels of it). Fully empty blocks are
    used first. Each picture keeps a one-texel empty margin. Returns {char: (x, y)} and the blocks to clear."""
    nb = size // 4
    cellmask = bytearray(size * size)   # 1 = inside a mapped cell grown by two texels
    blocked = bytearray(nb * nb)        # 1 = a mapped cell grown by one texel touches the block
    for x0, y0, x1, y1 in font["cells"]:
        for y in range(max(y0 - 2, 0), min(y1 + 2, size)):
            cellmask[y * size + max(x0 - 2, 0):y * size + min(x1 + 2, size)] = b"\x01" * (min(x1 + 2, size) - max(x0 - 2, 0))
        for by in range(max(y0 - 1, 0) // 4, (min(y1 + 1, size) - 1) // 4 + 1):
            for bx in range(max(x0 - 1, 0) // 4, (min(x1 + 1, size) - 1) // 4 + 1):
                blocked[by * nb + bx] = 1
    inked = bytearray(nb * nb)
    for y in range(size):
        for x in range(size):
            if atlas[(y * size + x) * 4 + 3]:
                b = (y // 4) * nb + x // 4
                inked[b] = 1
                if cellmask[y * size + x]:
                    blocked[b] = 1   # ink of a mapped glyph that reaches outside its cell
    placed, clear = {}, set()
    order =sorted(need, key=lambda n: (-n[2], -n[1], n[0]))
    for allow_ink in (False, True):
        for ch, w, h in order:
            if ch in placed:
                continue
            sat = [[0] * (nb + 1) for _ in range(nb + 1)]
            for by in range(nb):
                for bx in range(nb):
                    bad = blocked[by * nb + bx] or (inked[by * nb + bx] and not allow_ink)
                    sat[by + 1][bx + 1] = bad + sat[by][bx + 1] + sat[by + 1][bx] - sat[by][bx]
            spot = None
            for y in range(1, size - h):
                by0, by1 = (y - 1) // 4, (y + h) // 4 + 1
                if by1 > nb:
                    break
                for x in range(1, size - w):
                    bx0, bx1 = (x - 1) // 4, (x + w) // 4 + 1
                    if bx1 > nb:
                        break
                    if sat[by1][bx1] - sat[by0][bx1] - sat[by1][bx0] + sat[by0][bx0] == 0:
                        spot = (x, y)
                        break
                if spot:
                    break
            if spot is None:
                continue
            placed[ch] = spot
            x, y = spot
            for by in range((y - 1) // 4, (y + h) // 4 + 1):
                for bx in range((x - 1) // 4, (x + w) // 4 + 1):
                    blocked[by * nb + bx] = 1
                    clear.add((bx, by))
    missing = [n[0] for n in need if n[0] not in placed]
    if missing:
        raise Refusal("UNSUPPORTED", f"no room in the font atlas for {''.join(missing)}")
    return placed, clear


def compile_glyphs(m: dict, files: dict, paths) -> list:
    """Every range of a mod's glyph overrides: the font atlas (base level and mips, only the blocks of the new glyphs
    re-encoded) and the glyph records of both FontRay copies. Cached by the glyphs and the atlas bytes."""
    game = paths["game"]
    fixp = game / "GAMEDATAbin" / "fix.lvl"
    fix = fixp.read_bytes()
    font = read_font(fix)
    if font is None:
        raise Refusal("TARGET_CHANGED", "the game's font definitions are not the ones glyph overrides are made for")
    hits = resolve_texture(game, {"entry": FONT["atlas"], "bundles": [FONT["bundle"]]})
    bhf, e, w, h, fmt = hits[0]
    if (w, h, fmt) != FONT["atlas_size"]:
        raise Refusal("TARGET_CHANGED", f"the font atlas is {w}x{h} {fmt}")
    btf = bhf.with_suffix(".btf")
    with open(btf, "rb") as f:
        f.seek(e[2])
        b0 = f.read(e[1])
        f.seek(e[4])
        b1 = f.read(e[3])
    glyphs = [o for o in m["overrides"] if o["type"] == "glyph"]
    key = sha256_bytes(json.dumps(glyphs, sort_keys=True).encode() + b"".join(
        sha256_bytes(files[ly["image"]]).encode() for o in glyphs for ly in o["layers"] if "image" in ly)
        + sha256_bytes(b0 + b1).encode() + sha256_bytes(fix[:0x8000]).encode() + b"|glyphs-v1")
    cf = paths["cache"] / "glyphs" / f"{key}.json"
    blobs = recs = None
    if cf.is_file():
        try:
            c = json.loads(cf.read_text())
            assert isinstance(c, dict) and isinstance(c.get("records"), dict) and all(
                k in GLYPH_CODES and isinstance(v, str) and len(v) == 28 for k, v in c["records"].items())
            nb0, nb1 = (paths["cache"] / "glyphs" / f"{key}.0.bin").read_bytes(), (paths["cache"] / "glyphs" / f"{key}.1.bin").read_bytes()
            if sha256_bytes(nb0) == c["b0"] and sha256_bytes(nb1) == c["b1"]:
                blobs, recs = (nb0, nb1), {k: bytes.fromhex(v) for k, v in c["records"].items()}
        except (OSError, ValueError, KeyError, TypeError, AssertionError):  # a damaged cache is rebuilt
            blobs = None
    if blobs is None:
        _, _, lay = layout(w, h, fmt)
        atlas = decode_level(w, h, level_rows((b0, b1), lay[0], fmt), fmt)
        pics = {o["char"]: compose_glyph(o, font, atlas, files, w) for o in glyphs}
        need = [(ch, o["width"], o["height"]) for o in glyphs for ch in [o["char"]] if pics[ch][1] is None]
        placed, clear = place_glyphs(font, atlas, w, need) if need else ({}, set())
        img = bytearray(atlas)
        for bx, by in clear:
            for y in range(4 * by, 4 * by + 4):
                for x in range(4 * bx, 4 * bx + 4):
                    img[(y * w + x) * 4:(y * w + x) * 4 + 4] = b"\xff\xff\xff\x00"
        for ch, (x, y) in placed.items():
            o = next(g for g in glyphs if g["char"] == ch)
            pic = pics[ch][0]
            for j in range(o["height"]):
                img[((y + j) * w + x) * 4:((y + j) * w + x + o["width"]) * 4] = pic[j * o["width"] * 4:(j + 1) * o["width"] * 4]
        out = [bytearray(b0), bytearray(b1)]
        bpb = 16
        # base level: only the cleared blocks change
        changed = set(clear)
        lv = lay[0]
        nbr = (h + 3) // 4
        for bx, br in sorted(changed):
            at = lv[1] + (nbr - 1 - br) * lv[2] + bx * bpb
            out[0][at:at + bpb] = swap16(encode_block(img, w, h, bx, br, fmt))
        # mip levels: texels whose footprint holds a changed texel are recomputed from the level above (a 2x2 mean of
        # the changed picture, as the encoder's own mips), their blocks re-encoded; every other block keeps its bytes
        prev, pw, ph = img, w, h
        prev_changed = {(x, y) for bx, by in changed for y in range(4 * by, 4 * by + 4) for x in range(4 * bx, 4 * bx + 4)}
        for lv in lay[1:]:
            lw, lh = lv[5], lv[6]
            cur = bytearray(decode_level(lw, lh, level_rows((b0, b1), lv, fmt), fmt))
            ch_now = {(x >> 1, y >> 1) for x, y in prev_changed if (x >> 1) < lw and (y >> 1) < lh}
            for x, y in ch_now:
                for c in range(4):
                    s = n = 0
                    for dy in (0, 1):
                        for dx in (0, 1):
                            sx, sy = min(2 * x + dx, pw - 1), min(2 * y + dy, ph - 1)
                            s += prev[(sy * pw + sx) * 4 + c]
                            n += 1
                    cur[(y * lw + x) * 4 + c] = (s + n // 2) // n
            nbr_l = (lh + 3) // 4
            for bx, br in sorted({(x // 4, y // 4) for x, y in ch_now}):
                at = lv[1] + (lv[4] + nbr_l - 1 - br) * lv[2] + (lv[3] + bx) * bpb
                out[lv[0]][at:at + bpb] = swap16(encode_block(cur, lw, lh, bx, br, fmt))
            prev, pw, ph, prev_changed = cur, lw, lh, ch_now
        recs = {}
        for o in glyphs:
            ch = o["char"]
            x, y = pics[ch][1] or placed[ch]
            recs[ch] = struct.pack(">6H2B", x, y, o["height"], o["width"], 1, o["descent"] & 0xFFFF, 0, 1)
        blobs = (bytes(out[0]), bytes(out[1]))
        cf.parent.mkdir(parents=True, exist_ok=True)
        for i, b in enumerate(blobs):
            tmp = cf.with_name(f"{key}.{i}.tmp")
            tmp.write_bytes(b)
            os.replace(tmp, cf.with_name(f"{key}.{i}.bin"))
        cf.write_text(json.dumps({"b0": sha256_bytes(blobs[0]), "b1": sha256_bytes(blobs[1]),
                                  "records": {k: v.hex() for k, v in recs.items()}}))
    ranges = [(btf, e[2], blobs[0], f"{FONT['atlas']}#base"), (btf, e[4], blobs[1], f"{FONT['atlas']}#mips")]
    for ch in sorted(recs):
        for base in FONT["fontray"]:
            ranges.append((fixp, base + 50 + GLYPH_CODES[ch] * 14, recs[ch], f"glyph {ch}@{base:#x}"))
    return ranges


def text_refs(game: Path) -> dict:
    """{string offset: [pointer locations]} for every pointer fix.ptr lists in fix.lvl (value = offset - REF_BIAS)."""
    lvl, ptr = game / "GAMEDATAbin" / "fix.lvl", game / "GAMEDATAbin" / "fix.ptr"
    if not ptr.is_file():
        return {}
    d, p = lvl.read_bytes(), ptr.read_bytes()
    if len(p) < 4 or len(p) != 4 + 8 * struct.unpack_from(">I", p, 0)[0]:
        return {}
    refs = {}
    for i in range(struct.unpack_from(">I", p, 0)[0]):
        fid, loc = struct.unpack_from(">II", p, 4 + 8 * i)
        if fid == 0 and loc % 4 == 0 and loc + 4 <= len(d):
            refs.setdefault(struct.unpack_from(">I", d, loc)[0] + REF_BIAS, []).append(loc)
    return refs


# M38 (D-075): which text packer compile_texts uses. "auto" (default): the M34 packer, and the compacting one only
# when the M34 packer refuses (a mod that packs today gets the very same ranges); "m34": never compact; "compact":
# always compact (tests). The tool option --text-packer sets it for one command and the tools it starts.
TEXT_PACKER_ENV = "R3HD_TEXT_PACKER"
TEXT_PACKERS = ("auto", "m34", "compact")


def text_packer_mode() -> str:
    v = os.environ.get(TEXT_PACKER_ENV, "").strip().lower() or "auto"
    if v not in TEXT_PACKERS:
        raise Refusal("USAGE", f"{TEXT_PACKER_ENV}={v}: expected one of {', '.join(TEXT_PACKERS)}")
    return v


def compile_texts(texts: list, paths, glyphs, defined, packer=None) -> tuple:
    """Every range of a mod's text overrides, whether any text moved, and the packer that placed them ("fit" when every
    text fits its slot, "m34" or "compact"). M34 packer: texts that fit stay in their slot; longer ones go into the
    free space of this mod's own slots (each slot's tail after its new text, and the whole slot of a moved string),
    4-aligned, and every pointer to a moved string is redirected. A slot gives space only when no pointer points
    inside it. The compacting packer (M38) is used as text_packer_mode() says: see pack_compact."""
    mode = packer or text_packer_mode()
    p = paths["game"] / "GAMEDATAbin" / "fix.lvl"
    data = p.read_bytes()
    items = []
    for o in texts:
        slot = text_slot(data, o["offset"])
        if sha256_bytes(slot) != o["slot_sha256"]:
            raise Refusal("TARGET_CHANGED", f"the string at {o['offset']} is not the one the mod was made for")
        items.append((o["offset"], slot, encode_text(o["text"], glyphs, defined)))
    longer = [it for it in items if len(it[2]) + 1 > len(it[1])]
    if not longer and mode != "compact":
        return [(p, off, enc + b"\0" * (len(slot) - len(enc)), f"text@{off}") for off, slot, enc in items], False, "fit"
    refs = text_refs(paths["game"])
    if mode == "compact":
        return _no_overlap(pack_compact(p, items, refs)) + ("compact",)
    try:
        return _no_overlap(pack_m34(p, items, longer, refs)) + ("m34",)
    except Refusal:
        if mode == "m34":
            raise
    return _no_overlap(pack_compact(p, items, refs)) + ("compact",)


def _no_overlap(packed: tuple) -> tuple:
    """M38 review: a mod's own text ranges (slots and redirected pointers) must never overlap. The plan writer would
    keep the first and report the other as shadowed, so a linked mod would apply in part: refuse it whole instead.
    Valid slots cannot overlap (text_slot); this only guards against data or packer defects."""
    ranges = sorted((off, off + len(data), what) for _, off, data, what in packed[0])
    for (lo1, hi1, w1), (lo2, hi2, w2) in zip(ranges, ranges[1:]):
        if lo2 < hi1:
            raise Refusal("TEXT_OVERLAP", f"{w1} and {w2} would write the same bytes ({lo2}..{min(hi1, hi2)})")
    return packed


def _pointed_inside(refs: dict):
    inner = sorted(refs)

    def pointed_inside(lo, hi):
        import bisect
        i = bisect.bisect_right(inner, lo)
        return i < len(inner) and inner[i] < hi
    return pointed_inside


def _write_slots(content: dict, slots: list):
    def write(lo, data):
        for s_lo, s_hi in slots:
            a, b = max(lo, s_lo), min(lo + len(data), s_hi)
            if a < b:
                content[s_lo][a - s_lo:b - s_lo] = data[a - lo:b - lo]
    return write


def pack_m34(p: Path, items: list, longer: list, refs: dict) -> tuple:
    """The M34 packer (D-071, verified in game E-175): unchanged."""
    pointed_inside = _pointed_inside(refs)
    content = {off: bytearray(len(slot)) for off, slot, _ in items}
    free = []
    for off, slot, enc in items:
        if pointed_inside(off, off + len(slot)):
            if (off, slot, enc) in longer:
                raise Refusal("TEXT_TOO_LONG", f"the string at {off} is pointed into; it cannot move")
            content[off][:len(enc)] = enc
            continue
        if (off, slot, enc) in longer:
            if not refs.get(off):
                raise Refusal("TEXT_TOO_LONG", f"{len(enc)} bytes for a slot of {len(slot) - 1}, and no table pointer "
                              f"to the string at {off} to move it")
            free.append((off, off, off + len(slot)))
        else:
            content[off][:len(enc)] = enc
            start = _align(off + len(enc) + 1, 4)
            if start < off + len(slot):
                free.append((off, start, off + len(slot)))
    out_ptrs = []
    merged = []
    for owner, lo, hi in sorted(free, key=lambda f: f[1]):
        if merged and merged[-1][1] == lo:   # a free tail followed by a freed slot: one space
            merged[-1][1] = hi
        else:
            merged.append([lo, hi])
    free = merged
    slots = sorted((off, off + len(slot)) for off, slot, _ in items)
    write = _write_slots(content, slots)
    for off, slot, enc in sorted(longer, key=lambda it: (-len(it[2]), it[0])):
        need = len(enc) + 1
        k = next((i for i, f in enumerate(free) if f[1] - f[0] >= need), None)
        if k is None:
            room = max((f[1] - f[0] for f in free), default=0)
            raise Refusal("TEXT_TOO_LONG", f"{len(enc)} bytes for the string at {off} (slot {len(slot) - 1}); the "
                          f"largest free space among this mod's slots is {max(room - 1, 0)}")
        lo, hi = free[k]
        write(lo, enc + b"\0")
        free[k] = [_align(lo + need, 4), hi]
        for loc in refs[off]:
            out_ptrs.append((p, loc, struct.pack(">I", lo - REF_BIAS), f"pointer@{loc}->{lo}"))
    ranges = [(p, off, bytes(content[off]), f"text@{off}") for off, _, _ in items]
    return ranges + sorted(out_ptrs, key=lambda r: r[1]), True


def pack_compact(p: Path, items: list, refs: dict) -> tuple:
    """M38 (D-075): the compacting packer. The mod's slots form runs of adjacent slots. A slot that a pointer points
    into (or that holds a pointer location), or whose string no table pointer reaches, is pinned: its text stays at its
    offset and must fit (a pinned string without inner pointers gives its tail to the next run). Every other string of
    a run may move: the run is one free space. Three layouts are tried, the first that places everything wins:
      1. each run keeps its own strings in their order, each at its own offset unless an earlier one pushes it (the
         largest strings leave the run until the rest fit); the strings that left go, largest first, into the free
         gap (between kept strings or at a run's end) with the least room that holds them;
      2. while that fails, one run more packs its kept strings from its start (all its free space at its end): the
         run whose packing gives the largest free end first;
      3. every movable string, largest first, into the free run with the least room that holds it.
    Every pointer to a string that ends up elsewhere is redirected, in every language table (a shared string keeps
    one copy)."""
    import bisect
    pointed_inside = _pointed_inside(refs)
    locs = sorted(loc for v in refs.values() for loc in v)

    def holds_pointer(lo, hi):
        i = bisect.bisect_left(locs, lo - 3)
        return i < len(locs) and locs[i] < hi
    content = {off: bytearray(len(slot)) for off, slot, _ in items}
    runs, cur = [], None   # [lo, hi, [(offset, text)...]]
    for off, slot, enc in sorted(items, key=lambda it: it[0]):
        end, fits = off + len(slot), len(enc) + 1 <= len(slot)
        inside = pointed_inside(off, end) or holds_pointer(off, end)
        if inside or not refs.get(off):
            if not fits:
                raise Refusal("TEXT_TOO_LONG", f"the string at {off} is pointed into; it cannot move" if inside else
                              f"{len(enc)} bytes for a slot of {len(slot) - 1}, and no table pointer to the string at "
                              f"{off} to move it")
            content[off][:len(enc)] = enc
            tail = _align(off + len(enc) + 1, 4)
            cur = [tail, end, []] if not inside and tail < end else None
            if cur:
                runs.append(cur)
            continue
        if cur is not None and cur[1] == off:
            cur[1] = end
            cur[2].append((off, enc))
        else:
            cur = [off, end, [(off, enc)]]
            runs.append(cur)

    def layout(lo, hi, strs, in_place):
        need = [len(enc) + 1 for _, enc in strs]
        bound = [hi] * (len(strs) + 1)   # the latest 4-aligned start of each string that leaves room for the rest
        for i in reversed(range(len(strs))):
            b = bound[i + 1] - need[i]
            bound[i] = b - b % 4
        pos, at = lo, []
        for i, (off, _) in enumerate(strs):
            a = max(pos, min(off, bound[i])) if in_place else pos
            if a + need[i] > bound[i + 1]:
                return None, pos
            at.append(a)
            pos = _align(a + need[i], 4)
        return at, pos

    def keep(lo, hi, strs, in_place):
        """The run's own strings that stay in it (the largest leave until the rest fit), their places, the others."""
        own, out = list(strs), []
        while own:
            at, _ = layout(lo, hi, own, in_place)
            if at is not None:
                return own, at, out
            big = max(own, key=lambda s: (len(s[1]), s[0]))
            own.remove(big)
            out.append(big)
        return [], [], out

    def attempt(modes):   # per run: "in_place", "tight" or "spill" (every string of the run placed afresh)
        placed, room, spill = {}, [], []
        for (lo, hi, strs), how in zip(runs, modes):
            own, at, out = keep(lo, hi, strs, how == "in_place") if how != "spill" else ([], [], list(strs))
            placed.update({s[0]: a for s, a in zip(own, at)})
            spill += out
            pos = lo
            for (_, enc), a in zip(own, at):   # the free gaps between the kept strings and the run's free end
                if a > pos:
                    room.append([pos, a])
                pos = _align(a + len(enc) + 1, 4)
            if pos < hi:
                room.append([pos, hi])
        for off, enc in sorted(spill, key=lambda s: (-len(s[1]), s[0])):
            need = len(enc) + 1
            fit = [i for i, r in enumerate(room) if r[1] - r[0] >= need]
            if not fit:
                return None, (off, enc, max((r[1] - r[0] for r in room), default=0))
            k = min(fit, key=lambda i: (room[i][1] - room[i][0], room[i][0]))
            placed[off] = room[k][0]
            room[k][0] = _align(room[k][0] + need, 4)
        return placed, None

    def packed_end(i):   # the free end a run gets when its kept strings are packed from its start
        lo, hi, strs = runs[i]
        own, at, _ = keep(lo, hi, strs, False)
        return (hi - (_align(at[-1] + len(own[-1][1]) + 1, 4) if own else lo), -i)
    modes = ["in_place"] * len(runs)
    placed, fail = attempt(modes)
    while placed is None and "in_place" in modes:
        modes[max((i for i, m in enumerate(modes) if m == "in_place"), key=packed_end)] = "tight"
        placed, fail = attempt(modes)
    if placed is None:
        placed, fail = attempt(["spill"] * len(runs))
    if placed is None:
        off, enc, largest = fail
        cap = sum(hi - lo for lo, hi, _ in runs)
        need = sum(_align(len(e) + 1, 4) for _, _, strs in runs for _, e in strs)
        raise Refusal("TEXT_TOO_LONG", f"{len(enc)} bytes for the string at {off}; compacting this mod's movable slots "
                      f"({len(runs)} runs, {cap} bytes for {need} bytes of text) leaves the largest free space at "
                      f"{max(largest - 1, 0)}" + (f": shorten this mod's texts by at least {need - cap} bytes"
                                                  if need > cap else ""))
    write = _write_slots(content, sorted((off, off + len(slot)) for off, slot, _ in items))
    text = {off: enc for _, _, strs in runs for off, enc in strs}
    ptrs = []
    for off, at in sorted(placed.items()):
        write(at, text[off] + b"\0")
        if at != off:
            ptrs += [(p, loc, struct.pack(">I", at - REF_BIAS), f"pointer@{loc}->{at}") for loc in refs[off]]
    ranges = [(p, off, bytes(content[off]), f"text@{off}") for off, _, _ in items]
    return ranges + sorted(ptrs, key=lambda r: r[1]), bool(ptrs)


# ---------------------------------------------------------------------------------------------------------------
# M35: movie subtitles, GAMEDATAbin/VS.sub (RE_NOTES "M35"). Little-endian: u16 cue count; 20-byte cues (u8 language
# 1-5, 3 pad bytes, u32 movie, u32 start ms, u32 end ms, u32 string index); u16 string count; per string a u16 length
# and its bytes (no NUL). The title reads the file sequentially with stdio (loader 8222B5C8) and never past the last
# string, so a rebuilt string section is padded with zeros to the file's own size, and every cue (language, movie,
# timing, order, index) keeps its bytes. M36 (D-073): a longer rebuild grows the file for the guest instead (plan
# record `grow`, VS.sub only, runtime 0.36.0 and newer); the loader never asks the size and mallocs each string by its
# own length (RE_NOTES "M36"). A cue's id is vs.<language>.<movie>.<n>, n counting the cues of that language and movie
# in file order.

SUB_FILE = "GAMEDATAbin/VS.sub"
SUB_LANGS = {1: "en", 2: "fr", 3: "es", 4: "it", 5: "de"}   # by content (RE_NOTES M35)
SUB_ID_RE = re.compile(r"^vs\.(en|fr|es|it|de)\.(\d{1,4})\.(\d{1,3})$")
SUB_KEYS = {"type", "id", "source_sha256", "text"}
SUB_MAX_TEXT = 400        # bytes of one subtitle (the longest shipped one has 117)
SUB_MAX_MS = 3_600_000    # a cue ends within an hour
SUB_MAX_GROW = 1 << 20    # M36: bytes VS.sub may grow by (kMaxGrowBytes of tools/m33_mod_overlay.h)
SUB_GROW_PORT = "0.36.0"  # M36: the first runtime that serves a grown VS.sub


def parse_vs_sub(data: bytes) -> dict:
    """The cues and strings of a VS.sub; refuses anything but the shipped layout."""
    def bad(why):
        return Refusal("TARGET_CHANGED", f"VS.sub is not the supported subtitle table: {why}")
    if len(data) < 4:
        raise bad("too short")
    n = struct.unpack_from("<H", data, 0)[0]
    p = 2 + 20 * n
    if not 0 < n <= 4096 or p + 2 > len(data):
        raise bad(f"{n} cues")
    cues, ids, count = [], {}, {}
    for i in range(n):
        lang, = struct.unpack_from("<B", data, 2 + 20 * i)
        movie, start, end, index = struct.unpack_from("<4I", data, 2 + 20 * i + 4)
        if lang not in SUB_LANGS or not start < end <= SUB_MAX_MS or movie > 9999 or index != i:
            raise bad(f"cue {i}: language {lang}, {start}-{end} ms, index {index}")
        key = (SUB_LANGS[lang], movie)
        sid = f"vs.{key[0]}.{movie}.{count.get(key, 0)}"
        count[key] = count.get(key, 0) + 1
        ids[sid] = i
        cues.append((SUB_LANGS[lang], movie, start, end, index, data[2 + 20 * i:22 + 20 * i]))
    if struct.unpack_from("<H", data, p)[0] != n:
        raise bad("the string count differs from the cue count")
    p += 2
    strings, offsets = [], []
    for i in range(n):
        if p + 2 > len(data):
            raise bad(f"string {i} is outside the file")
        ln = struct.unpack_from("<H", data, p)[0]
        if p + 2 + ln > len(data) or b"\0" in data[p + 2:p + 2 + ln]:
            raise bad(f"string {i}")
        offsets.append(p)
        strings.append(data[p + 2:p + 2 + ln])
        p += 2 + ln
    if any(data[p:]):
        raise bad("data after the last string")
    return {"cues": cues, "strings": strings, "offsets": offsets, "end": p, "ids": ids}


def sub_hash(sub: dict, i: int) -> str:
    """A cue's identity: its 20 bytes and its string (so a timing or text change in the game data is noticed)."""
    return sha256_bytes(sub["cues"][i][5] + sub["strings"][i])


def parse_subtitle(o: dict, where: str):
    if set(o) - SUB_KEYS or not isinstance(o.get("id"), str) or not SUB_ID_RE.match(o["id"]):
        raise Refusal("BAD_MANIFEST", f"{where}: a subtitle needs 'id' (vs.<language>.<movie>.<cue>, e.g. vs.en.42.0), "
                      "'source_sha256' and 'text' (timing and order are the game's and cannot be changed)")
    if not isinstance(o.get("source_sha256"), str) or not re.match(r"^[0-9a-f]{64}$", o["source_sha256"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'source_sha256' must be the cue's 64-digit SHA-256 (r3hd_loc.py catalog)")
    if not isinstance(o.get("text"), str) or not o["text"] or len(o["text"]) > SUB_MAX_TEXT:
        raise Refusal("BAD_MANIFEST", f"{where}: 'text' must be a non-empty text of at most {SUB_MAX_TEXT} characters")
    encode_text("".join(c for c in o["text"] if c not in GLYPH_CODES) or " ")


def compile_subtitles(subs: list, paths, glyphs, defined) -> list:
    """One range: VS.sub from the first changed string to its end, the strings rebuilt and zero-padded."""
    p = paths["game"] / SUB_FILE
    if not p.is_file():
        raise Refusal("NO_GAME_DATA", f"{SUB_FILE} is missing")
    data = p.read_bytes()
    sub = parse_vs_sub(data)
    new = list(sub["strings"])
    changed = []
    for o in subs:
        i = sub["ids"].get(o["id"])
        if i is None:
            raise Refusal("TARGET_CHANGED", f"{o['id']}: no such cue in this game's VS.sub")
        if sub_hash(sub, i) != o["source_sha256"]:
            raise Refusal("TARGET_CHANGED", f"{o['id']}: the cue is not the one the mod was made for")
        enc = encode_text(o["text"], glyphs, defined)
        if len(enc) > SUB_MAX_TEXT:
            raise Refusal("TEXT_TOO_LONG", f"{o['id']}: {len(enc)} bytes (at most {SUB_MAX_TEXT})")
        new[i] = enc
        changed.append(i)
    first = min(changed)
    lo = sub["offsets"][first]
    body = b"".join(struct.pack("<H", len(s)) + s for s in new[first:])
    room = len(data) - lo
    if len(body) <= room:   # fits: zero-padded to the file's own size (M35; such a plan works on any port since 0.35)
        return [(p, lo, body + bytes(room - len(body)), f"subtitles@{lo}")]
    # M36 (D-073): longer than the file. The plan grows VS.sub for the guest (a `grow` record: the runtime of 0.36.0 and
    # newer serves the bytes past the file's end and reports the new size); the strings run to the new end, unpadded.
    grow = len(body) - room
    if grow > SUB_MAX_GROW:
        raise Refusal("TEXT_TOO_LONG", f"the subtitles need {grow} bytes more than VS.sub holds; it can grow by at "
                      f"most {SUB_MAX_GROW}: shorten some of this mod's subtitles by {grow - SUB_MAX_GROW} bytes")
    pv = port_version(paths)
    if version_key(pv) < version_key(SUB_GROW_PORT):
        raise Refusal("INCOMPATIBLE", f"the subtitles are {grow} bytes longer than VS.sub; a longer subtitle table "
                      f"needs port version {SUB_GROW_PORT} or newer, this is {pv} (or shorten them by {grow} bytes)")
    return [(p, lo, body, f"subtitles@{lo}+{grow}")]


# ---------------------------------------------------------------------------------------------------------------
# Installed mods and state

def load_state(paths) -> dict:
    p = paths["mods"] / "state.json"
    if not p.exists():
        return {"schema": STATE_SCHEMA, "mods": []}
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(s, dict) and s.get("schema") == STATE_SCHEMA and isinstance(s.get("mods"), list)
        ids = set()
        for e in s["mods"]:
            assert isinstance(e, dict) and isinstance(e.get("id"), str) and ID_RE.match(e["id"])
            assert isinstance(e.get("enabled"), bool) and e["id"] not in ids
            ids.add(e["id"])
        return s
    except (OSError, ValueError, AssertionError):
        raise Refusal("STATE_DAMAGED", str(p))


def save_state(paths, s: dict):
    paths["mods"].mkdir(parents=True, exist_ok=True)
    p = paths["mods"] / "state.json"
    tmp = p.with_name(f"state.json.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def installed_dir(paths, mod_id) -> Path:
    if not isinstance(mod_id, str) or not ID_RE.match(mod_id):  # M33 review: "." or a path is never an id
        raise Refusal("NOT_INSTALLED", repr(mod_id))
    return paths["mods"] / "installed" / mod_id


def recover(paths) -> list:
    """Finishes or undoes what an interrupted import / remove left (a killed process, a locked file): a replaced mod's
    previous folder comes back when the new one is missing; staging and half-removed folders are deleted. Only
    folders this tool names (.staging-*, .old-<id>-*, .removing-<id>-*) directly under the mods folder are touched."""
    done = []
    root, inst = paths["mods"], paths["mods"] / "installed"

    def plain_dir(p):
        st = os.lstat(p)
        return stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode) and not getattr(st, "st_file_attributes", 0) & 0x400
    for p in sorted(root.glob(".staging-*")) if root.is_dir() else []:
        pid = p.name[len(".staging-"):]
        if pid.isdigit() and int(pid) != os.getpid() and plain_dir(p):
            shutil.rmtree(p)
            done.append(f"removed {p.name}")
    for p in sorted(inst.glob(".old-*")) if inst.is_dir() else []:
        m = re.match(r"^\.old-(.+)-(\d+)$", p.name)
        if not m or not ID_RE.match(m.group(1)) or not plain_dir(p) or int(m.group(2)) == os.getpid():
            continue
        target = inst / m.group(1)
        if not target.exists():
            os.replace(p, target)
            done.append(f"restored {m.group(1)}")
        else:
            shutil.rmtree(p)
            done.append(f"removed {p.name}")
    for p in sorted(inst.glob(".removing-*")) if inst.is_dir() else []:
        if plain_dir(p):
            shutil.rmtree(p)
            done.append(f"removed {p.name}")
    return done


# The runtime refuses a plan beyond these (tools/m33_mod_overlay.h); the plan is refused here first, with a reason.
PLAN_MAX_FILES, PLAN_MAX_RANGES, PLAN_MAX_BYTES, PLAN_MAX_RANGE, PLAN_MAX_LINE = 4096, 65536, 512 << 20, 64 << 20, 4000


def load_installed(paths, mod_id) -> dict:
    """{relative path: bytes} of an installed mod after checking every file against installed.json."""
    d = installed_dir(paths, mod_id)
    st = os.lstat(d) if d.exists() else None
    if st is None or not stat.S_ISDIR(st.st_mode) or getattr(st, "st_file_attributes", 0) & 0x400:
        raise Refusal("NOT_INSTALLED", mod_id)
    try:
        rec = json.loads((d / "installed.json").read_text(encoding="utf-8"))
        listed = rec["files"]
    except (OSError, ValueError, KeyError):
        raise Refusal("DAMAGED", f"{mod_id}: installed.json")
    files = read_package(d)
    files.pop("installed.json", None)
    if set(files) != set(listed) or any(sha256_bytes(files[r]) != listed[r] for r in files):
        raise Refusal("DAMAGED", mod_id)
    return files


def required_glyphs(m: dict, paths, manifests=None) -> frozenset:
    """Glyphs the mods this one requires add (from their installed manifests)."""
    out = set()
    for rid in m.get("requires", []):
        rm = (manifests or {}).get(rid)
        if rm is None:
            try:
                rm = parse_manifest(load_installed(paths, rid))
            except Refusal:
                continue
        out |= glyph_chars(rm)
    return frozenset(out)


def compile_mod(m: dict, files: dict, paths, manifests=None) -> list:
    """Every range of one mod: (game file, offset, new bytes, description). Refusal if anything does not apply.
    m["_linked"] is set when the ranges belong together (glyphs, moved text): such a mod applies whole or not at all."""
    game = paths["game"]
    if not (game / "GAMEDATAbin").is_dir():
        raise Refusal("NO_GAME_DATA", str(game))
    check_compat(m, paths)
    out = []
    glyphs = glyph_chars(m) | required_glyphs(m, paths, manifests)
    texts = [o for o in m["overrides"] if o["type"] == "text"]
    subs = [o for o in m["overrides"] if o["type"] == "subtitle"]
    linked = False
    defined = None
    if texts or subs:
        defined = font_defined(paths)
        if defined is None and glyphs:
            raise Refusal("TARGET_CHANGED", "the game's font definitions are not the ones glyph overrides are made for")
    if texts:
        rs, moved, m["_text_packer"] = compile_texts(texts, paths, glyphs, defined)
        out += rs
        linked |= moved
    if subs:   # M35: the rebuilt string section belongs together (applied whole or not at all)
        out += compile_subtitles(subs, paths, glyphs, defined)
        linked = True
    if glyph_chars(m):
        out += compile_glyphs(m, files, paths)
        linked = True
    m["_linked"] = linked
    for o in m["overrides"]:
        if o["type"] != "texture":
            continue
        else:
            for bhf, e, w, h, fmt in resolve_texture(game, o):
                btf = bhf.with_suffix(".btf")
                name, s1, o1, s2, o2 = e
                with open(btf, "rb") as f:
                    f.seek(o1)
                    orig0 = f.read(s1)
                    f.seek(o2)
                    orig1 = f.read(s2)
                if len(orig0) != s1 or len(orig1) != s2:
                    raise Refusal("TARGET_CHANGED", f"{btf.name} is shorter than its header says")
                rows = encoded_levels(paths["cache"], files[o["image"]], w, h, fmt)
                b0, b1 = place_levels([orig0, orig1], rows, layout(w, h, fmt)[2], fmt)
                out.append((btf, o1, b0, f"{name}#base"))
                if s2:
                    out.append((btf, o2, b1, f"{name}#mips"))
    return out


def achievement_text(files: dict) -> tuple:
    """D-101: ([(id, field, source_sha256, text)], problem) of a mod's optional achievements/achievements.json.
    Any problem ignores the whole file (the game's text and the byte plan are not affected); empty texts are left
    out (English is shown)."""
    raw = files.get(ACH_FILE)
    if raw is None:
        return [], ""
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as e:
        return [], f"not JSON: {e}"
    if not isinstance(doc, dict) or set(doc) - {"format", "kind", "title_id", "language", "strings", "note"}:
        return [], "unknown keys"
    if doc.get("format") != 1 or doc.get("kind") != ACH_KIND or doc.get("title_id") != TITLE_ID:
        return [], f"format 1, kind {ACH_KIND} and title_id {TITLE_ID} are required"
    if not isinstance(doc.get("strings"), list) or len(doc["strings"]) > 512:
        return [], "strings must be a list (at most 512)"
    rows, seen = [], set()
    for n, e in enumerate(doc["strings"]):
        if not isinstance(e, dict) or set(e) - {"id", "field", "source_sha256", "text", "english"}:
            return [], f"strings[{n}]: unknown keys"
        i, f, h, t = e.get("id"), e.get("field"), e.get("source_sha256"), e.get("text", "")
        if not isinstance(i, int) or isinstance(i, bool) or not 1 <= i <= 0xFFFF or f not in ACH_FIELDS:
            return [], f"strings[{n}]: id 1..65535 and field {', '.join(ACH_FIELDS)} required"
        if not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h) or not isinstance(t, str):
            return [], f"strings[{n}]: source_sha256 (64 lower-case hex) and a text string required"
        if (i, f) in seen:
            return [], f"{i}.{f} listed twice"
        seen.add((i, f))
        if not t:
            continue
        if len(t) > ACH_MAX[f] or any(ord(c) < 0x20 or 0x7F <= ord(c) < 0xA0 for c in t):
            return [], f"{i}.{f}: longer than {ACH_MAX[f]} characters or a control character"
        rows.append((i, f, h, t))
    return rows, ""


def write_achievement_text(out: Path, rows) -> str:
    out.mkdir(parents=True, exist_ok=True)
    path = out / ACH_TEXT_NAME
    if not rows:
        path.unlink(missing_ok=True)
        return ""
    body = "".join(f"{i}\t{f}\t{h}\t{t}\n" for i, f, h, t in rows)
    tmp = path.with_name(f"{ACH_TEXT_NAME}.tmp-{os.getpid()}")
    tmp.write_bytes(body.encode("utf-8"))
    os.replace(tmp, path)
    return str(path)


def resolve_all(paths, write_plan=None) -> dict:
    """Validates every installed mod and, in priority order, decides what applies. With write_plan=DIR also writes
    the launch plan there. Returns the per-mod report."""
    recover(paths)
    state = load_state(paths)
    report, applied, claimed = [], {}, []  # claimed: (file, lo, hi, mod id)
    manifests, ach_rows = {}, {}
    for e in state["mods"]:
        r = {"id": e["id"], "enabled": e["enabled"], "state": "disabled", "detail": "", "name": e["id"], "version": "",
             "description": "", "overrides": 0, "ranges": 0, "shadowed": []}
        report.append(r)
        try:
            files = load_installed(paths, e["id"])
            m = parse_manifest(files)
            if m["id"] != e["id"]:
                raise Refusal("DAMAGED", f"{e['id']}: manifest id {m['id']}")
            manifests[e["id"]] = m
            r.update(name=m["name"], version=m["version"], description=m.get("description", ""),
                     overrides=len(m["overrides"]))
            if not e["enabled"]:
                check_compat(m, paths)
                continue
            for other in applied:
                if other in m.get("conflicts", []) or m["id"] in manifests[other].get("conflicts", []):
                    raise Refusal("CONFLICT", f"conflicts with {other}")
            ranges = compile_mod(m, files, paths, manifests)
            if m.get("_text_packer"):
                r["text_packer"] = m["_text_packer"]
            applied[e["id"]] = (m, ranges)
            ach_rows[e["id"]] = achievement_text(files)
            r["state"] = "pending"
        except Refusal as x:
            r["state"], r["code"], r["detail"] = ("invalid" if e["enabled"] else "disabled_invalid"), x.code, x.detail
    order = [e["id"] for e in state["mods"]]

    def drop_missing_dependencies():
        changed = True
        while changed:  # dependencies: a mod applies only if everything it requires applies
            changed = False
            for mid, (m, _) in list(applied.items()):
                missing = [q for q in m.get("requires", []) if q not in applied]
                if missing:
                    del applied[mid]
                    r = next(x for x in report if x["id"] == mid)
                    r.update(state="invalid", code="MISSING_DEPENDENCY", detail=f"requires {', '.join(missing)}")
                    changed = True
    drop_missing_dependencies()
    # M34: glyph records point into their mod's atlas and moved text into that mod's own slots, so such a mod applies
    # whole or not at all: a higher-priority mod over any of its bytes refuses it (and what requires it), then the
    # priority pass starts again without it.
    while True:
        seen, refused_one = [], False
        for mid in [i for i in order if i in applied]:
            m, ranges = applied[mid]
            over = next((c for path, off, data, what in ranges for c in seen
                         if c[0] == path and c[1] < off + len(data) and off < c[2]), None) if m.get("_linked") else None
            if over:
                del applied[mid]
                next(x for x in report if x["id"] == mid).update(
                    state="invalid", code="CONFLICT", detail=f"adds glyphs or moves text, and {over[3]} changes the same data")
                drop_missing_dependencies()
                refused_one = True
                break
            seen += [(path, off, off + len(data), mid) for path, off, data, what in ranges]
        if not refused_one:
            break
    ranges_out = []
    for mid in [i for i in order if i in applied]:
        m, ranges = applied[mid]
        r = next(x for x in report if x["id"] == mid)
        n = 0
        for path, off, data, what in ranges:
            hi = off + len(data)
            owner = next((c for c in claimed if c[0] == path and c[1] < hi and off < c[2]), None)
            if owner:
                r["shadowed"].append(f"{what} (by {owner[3]})")
                continue
            claimed.append((path, off, hi, mid))
            ranges_out.append((path, off, data, mid))
            n += 1
        r["state"], r["ranges"] = "active", n
    files_out = {Path(os.path.abspath(r[0])) for r in ranges_out}
    total = sum(len(r[2]) for r in ranges_out)
    longest = max((len(str(f)) for f in files_out), default=0) + len(str(paths["cache"])) + 200
    if len(files_out) > PLAN_MAX_FILES or len(ranges_out) > PLAN_MAX_RANGES or total > PLAN_MAX_BYTES \
            or any(len(r[2]) > PLAN_MAX_RANGE for r in ranges_out) or longest > PLAN_MAX_LINE:
        raise Refusal("TOO_LARGE", f"the enabled mods change {len(ranges_out)} ranges, {total} bytes in "
                      f"{len(files_out)} files: more than one launch can carry; disable some")
    result = {"mods": report, "active": [r["id"] for r in report if r["state"] == "active"], "ranges": len(ranges_out)}
    ach = {}
    for mid in result["active"]:   # priority order: the first mod that has an entry wins it
        rows, problem = ach_rows.get(mid, ([], ""))
        r = next(x for x in report if x["id"] == mid)
        if problem:
            r["achievement_text"] = f"ignored: {problem}"
        elif rows:
            r["achievement_text"] = len(rows)
        for row in rows:
            ach.setdefault((row[0], row[1]), row)
    result["achievement_text_entries"] = len(ach)
    if write_plan is not None:
        result["plan"] = write_plan_files(paths, Path(write_plan), ranges_out,
                                          [(i, manifests[i]["version"]) for i in result["active"]])
        result["achievement_text"] = write_achievement_text(Path(write_plan), sorted(ach.values()))
    return result


def fnv_cached(cache: dict, data: bytes) -> str:
    k = sha256_bytes(data)
    if k not in cache:
        cache[k] = f"{fnv1a64(data):016x}"
    return cache[k]


def write_plan_files(paths, out: Path, ranges, mods) -> str:
    out.mkdir(parents=True, exist_ok=True)
    plan = out / PLAN_NAME
    if not ranges:
        plan.unlink(missing_ok=True)
        for f in (out / "ranges").glob("*.bin") if (out / "ranges").is_dir() else []:
            f.unlink()
        return ""
    fc_path = out / "fnv_cache.json"
    try:
        fc = json.loads(fc_path.read_text())
        assert isinstance(fc, dict)
    except (OSError, ValueError, AssertionError):
        fc = {}
    rdir = out / "ranges"
    rdir.mkdir(exist_ok=True)
    files = []
    lines = ["R3HD_MOD_PLAN 1", f"# written by tools/r3hd_mods.py at {now()}"]
    lines += [f"mod {i} {v}" for i, v in mods]
    keep = set()
    body = []
    ends = {}
    for path, off, data, mid in ranges:
        path = Path(os.path.abspath(path))
        ends[path] = max(ends.get(path, 0), off + len(data))
    for path, off, data, mid in ranges:
        path = Path(os.path.abspath(path))
        if path not in files:
            files.append(path)
            size = path.stat().st_size
            lines.append(f"file {size} {path}")
            if ends[path] > size:   # M36 (D-073): only a grown VS.sub reaches past its file's end
                if path.name.lower() != "vs.sub":
                    raise Refusal("TOO_LARGE", f"{path.name}: a range past the end of the file")
                lines.append(f"grow {len(files) - 1} {ends[path]}")
        with open(path, "rb") as f:
            f.seek(off)
            own = f.read(len(data))
        name = sha256_bytes(data)[:32] + ".bin"
        keep.add(name)
        blob = rdir / name
        if not blob.is_file() or blob.read_bytes() != data:
            tmp = blob.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, blob)
        body.append(f"range {files.index(path)} {off} {len(data)} {fnv_cached(fc, own)} {fnv_cached(fc, data)} {mid} "
                    f"{blob.resolve()}")
    # file records first (the runtime reads them before any range refers to them)
    lines = [ln for ln in lines] + body + [f"end {len(files)} {len(ranges)}", ""]
    for f in rdir.glob("*.bin"):
        if f.name not in keep:
            f.unlink()
    tmp = plan.with_name(f"{PLAN_NAME}.tmp-{os.getpid()}")
    tmp.write_bytes("\n".join(lines).encode("utf-8"))
    os.replace(tmp, plan)
    fc_path.write_text(json.dumps(fc))
    return str(plan)


# ---------------------------------------------------------------------------------------------------------------
# Commands

def cmd_validate(paths, source: Path) -> dict:
    files = read_package(source)
    m = parse_manifest(files)
    out = {"id": m["id"], "name": m["name"], "version": m["version"], "overrides": len(m["overrides"]), "files": len(files)}
    if (paths["game"] / "GAMEDATAbin").is_dir():
        out["ranges"] = len(compile_mod(m, files, paths))
        if m.get("_text_packer"):
            out["text_packer"] = m["_text_packer"]
    return out


def cmd_import(paths, source: Path, replace=False, enable=False) -> dict:
    recover(paths)
    files = read_package(source)
    m = parse_manifest(files)
    ranges = compile_mod(m, files, paths)  # a mod that cannot apply to this game data is not installed
    state = load_state(paths)
    existing = next((e for e in state["mods"] if e["id"] == m["id"]), None)
    target = installed_dir(paths, m["id"])
    if (existing or target.exists()) and not replace:
        raise Refusal("EXISTS", m["id"])
    (paths["mods"] / "installed").mkdir(parents=True, exist_ok=True)
    stage = paths["mods"] / f".staging-{os.getpid()}"
    if stage.exists():
        shutil.rmtree(stage)
    try:
        for rel, data in files.items():
            p = stage.joinpath(*rel.split("/"))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        rec = {"schema": 1, "id": m["id"], "version": m["version"], "imported_at": now(),
               "source_name": source.name, "files": {r: sha256_bytes(b) for r, b in sorted(files.items())}}
        (stage / "installed.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
        old = None
        if target.exists():
            old = target.with_name(f".old-{m['id']}-{os.getpid()}")
            os.replace(target, old)
        os.replace(stage, target)
        if old:
            shutil.rmtree(old)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    if existing:
        existing["installed_at"] = now()
        if enable:
            existing["enabled"] = True
    else:
        state["mods"].append({"id": m["id"], "enabled": bool(enable), "installed_at": now()})
    save_state(paths, state)
    return {"id": m["id"], "version": m["version"], "replaced": bool(existing), "enabled": bool(enable or
            (existing and existing["enabled"])), "ranges": len(ranges)}


def cmd_set(paths, mod_id, enabled: bool) -> dict:
    installed_dir(paths, mod_id)  # the id's shape
    state = load_state(paths)
    e = next((x for x in state["mods"] if x["id"] == mod_id), None)
    if not e:
        raise Refusal("NOT_INSTALLED", mod_id)
    e["enabled"] = enabled
    save_state(paths, state)
    return {"id": mod_id, "enabled": enabled}


def cmd_move(paths, mod_id, where) -> dict:
    installed_dir(paths, mod_id)  # the id's shape
    state = load_state(paths)
    ids = [e["id"] for e in state["mods"]]
    if mod_id not in ids:
        raise Refusal("NOT_INSTALLED", mod_id)
    i = ids.index(mod_id)
    e = state["mods"].pop(i)
    j = {"up": max(i - 1, 0), "down": min(i + 1, len(ids) - 1), "top": 0, "bottom": len(ids) - 1}[where]
    state["mods"].insert(j, e)
    save_state(paths, state)
    return {"id": mod_id, "priority": j + 1, "order": [x["id"] for x in state["mods"]]}


def cmd_remove(paths, mod_id) -> dict:
    recover(paths)
    state = load_state(paths)
    e = next((x for x in state["mods"] if x["id"] == mod_id), None)
    d = installed_dir(paths, mod_id)
    if not e and not d.exists():
        raise Refusal("NOT_INSTALLED", mod_id)
    if d.exists():
        st = os.lstat(d)
        if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & 0x400 or not stat.S_ISDIR(st.st_mode):
            raise Refusal("UNSAFE_PACKAGE", f"{d} is not a plain folder; nothing was removed")
        trash = d.with_name(f".removing-{mod_id}-{os.getpid()}")
        os.replace(d, trash)
        shutil.rmtree(trash)
    if e:
        state["mods"].remove(e)
        save_state(paths, state)
    return {"id": mod_id, "removed": True}


def cmd_text_find(paths, text: str) -> dict:
    data = (paths["game"] / "GAMEDATAbin" / "fix.lvl").read_bytes()
    needle = text.encode("latin1") + b"\0"
    hits, i = [], data.find(needle)
    refs = text_refs(paths["game"])
    while i >= 0:
        if i % 4 == 0 and data[i - 1] == 0:
            slot = text_slot(data, i)
            # M34: the table pointers to the string (a text longer than its slot can move only when it has some)
            hits.append({"offset": i, "capacity": len(slot) - 1, "slot_sha256": sha256_bytes(slot),
                         "pointers": len(refs.get(i, []))})
        i = data.find(needle, i + 1)
    return {"file": "GAMEDATAbin/fix.lvl", "text": text, "matches": hits}


def cmd_texture_info(paths, entry: str) -> dict:
    hits = resolve_texture(paths["game"], {"entry": entry, "bundles": "all"})
    return {"entry": entry, "bundles": [{"bundle": h[0].relative_to(paths["game"]).with_suffix("").as_posix(),
                                         "width": h[2], "height": h[3], "format": h[4], "base": h[1][1],
                                         "mips": h[1][3]} for h in hits]}


def cmd_texture_export(paths, entry: str, out: Path) -> dict:
    bhf, e, w, h, fmt = resolve_texture(paths["game"], {"entry": entry, "bundles": "all"})[0]
    with open(bhf.with_suffix(".btf"), "rb") as f:
        f.seek(e[2])
        raw = swap16(f.read(e[1]))
    pitch = layout(w, h, fmt)[2][0][2]
    bpb = 16 if fmt == "DXT5" else 8
    rows = [raw[j * pitch:j * pitch + ((w + 3) // 4) * bpb] for j in range((h + 3) // 4)]
    out.write_bytes(write_png(w, h, decode_level(w, h, rows, fmt)))
    return {"entry": entry, "bundle": bhf.relative_to(paths["game"]).as_posix(), "width": w, "height": h,
            "format": fmt, "out": str(out), "note": "game-derived: keep it private"}


# ---------------------------------------------------------------------------------------------------------------
# Selftest (synthetic fixtures only: a fake game tree, fake bundles, fake mods)

def selftest() -> int:
    results = []
    sys.stdout.reconfigure(errors="backslashreplace")  # test names hold Turkish letters; consoles may not (cp1254 has no Ý)

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} {name}{'' if ok else ' :: ' + str(detail)}")

    def refused(fn, code):
        try:
            fn()
        except Refusal as x:
            return x.code == code or x.code
        return False

    # layout against the four sizes verified on the real data (M26 table and M33 bundle headers)
    l512 = layout(512, 512, "DXT5")
    check("layout: 512x512 DXT5 = the M26 table (sizes, area offsets, tail positions 16 at (4,0) ... 1 at (0,1))",
          l512[:2] == (262144, 131072)
          and [lv[1] for lv in l512[2][1:]] == [0, 0x10000, 0x14000, 0x18000] + [0x1C000] * 5
          and [lv[2] for lv in l512[2][1:5]] == [1024, 512, 512, 512]
          and [(lv[3], lv[4]) for lv in l512[2][5:]] == [(4, 0), (2, 0), (1, 0), (0, 2), (0, 1)], l512[2])
    check("layout: 1024x1024 DXT5 (menu frame) 1048576 / 393216", layout(1024, 1024, "DXT5")[:2] == (1048576, 393216))
    check("layout: 512x512 DXT1 (moon) 131072 / 65536", layout(512, 512, "DXT1")[:2] == (131072, 65536))
    check("layout: 128x128 DXT5 (menu icons) 16384 / 49152", layout(128, 128, "DXT5")[:2] == (16384, 49152))
    check("layout: 256x256 DXT5 65536 / 65536", layout(256, 256, "DXT5")[:2] == (65536, 65536))

    # PNG round trip and DXT encode / decode
    w, h = 16, 8
    img = b"".join(bytes(p) for p in [(x * 16 % 256, y * 32 % 256, (x + y) * 8 % 256, 255 if x < 8 else 0)
                                      for y in range(h) for x in range(w)])
    pw, ph, back = read_png(write_png(w, h, img))
    check("png: round trip", (pw, ph, back) == (w, h, img))
    flat = bytes([200, 40, 90, 255] * 64)
    rows = encode_level(8, 8, flat, "DXT5")
    dec = decode_level(8, 8, rows, "DXT5")
    check("dxt5: a flat colour decodes within 565 rounding",
          all(abs(dec[i] - flat[i]) <= 4 for i in range(len(flat))), dec[:8])
    grad = b"".join(bytes((x * 32, 255 - x * 32, 128, 255)) for y in range(8) for x in range(8))
    dec = decode_level(8, 8, encode_level(8, 8, grad, "DXT1"), "DXT1")
    check("dxt1: a gradient decodes within 24 per channel", max(abs(dec[i] - grad[i]) for i in range(len(grad))) <= 24)
    cut = b"".join(bytes((250, 10, 10, 255) if (x + y) % 2 else (0, 0, 0, 0)) for y in range(4) for x in range(4))
    dec = decode_level(4, 4, encode_level(4, 4, cut, "DXT1"), "DXT1")
    check("dxt1: cut-out texels stay transparent, the others opaque (1-bit alpha)",
          all((dec[i * 4 + 3] == 0) == (cut[i * 4 + 3] == 0) for i in range(16)) and dec[4] >= 240)
    vert = b"".join(bytes((0, 0, 0, 255) if y < 4 else (255, 255, 255, 255)) for y in range(8) for x in range(4))
    rows = encode_level(4, 8, vert, "DXT1")
    check("storage: bottom row first (the image's bottom half is block row 0)",
          decode_level(4, 4, [rows[0]], "DXT1")[0] == 255 and decode_level(4, 8, rows, "DXT1")[0] == 0)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        game = td / "game"
        (game / "GAMEDATAbin" / "lvl1").mkdir(parents=True)
        # a fake fix.lvl with strings, and a fake level with one texture record + bundle
        fix = bytearray(0x200)
        fix[0x40:0x40 + 15] = b"Help & Options\0"
        fix[0x50:0x54] = b"New\0"
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(bytes(fix))
        lvl = bytearray(0x200)
        rec = 0x40
        struct.pack_into(">I", lvl, rec + 0x14, 0x8008)
        struct.pack_into(">HH", lvl, rec + 0x1C, 32, 32)
        nm = b"menu\\fake.tga\0"
        lvl[rec + 0x4A:rec + 0x4A + len(nm)] = nm
        (game / "GAMEDATAbin" / "lvl1" / "lvl1.lvl").write_bytes(bytes(lvl))
        base, mips, _ = layout(32, 32, "DXT5")
        bhf = struct.pack(">I", 1) + struct.pack(">4I", base, 0, mips, base) + b"menu\\fake.dds".ljust(0x104, b"\0")
        (game / "GAMEDATAbin" / "lvl1" / "lvl1_2.bhf").write_bytes(bhf)
        btf = bytes((i * 7) & 0xFF for i in range(base + mips))
        (game / "GAMEDATAbin" / "lvl1" / "lvl1_2.btf").write_bytes(btf)
        before = {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}
        paths = {"home": None, "mods": td / "mods", "cache": td / "cache", "game": game}
        slot = text_slot(bytes(fix), 0x40)
        png32 = write_png(32, 32, bytes([10, 200, 30, 255] * 1024))

        def mk(name, manifest, extra=None, as_zip=False):
            d = td / "src" / name
            d.mkdir(parents=True)
            (d / "mod.json").write_text(json.dumps(manifest), encoding="utf-8")
            for rel, data in (extra or {}).items():
                (d / rel).parent.mkdir(parents=True, exist_ok=True)
                (d / rel).write_bytes(data)
            if as_zip:
                z = td / "src" / f"{name}.zip"
                with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                    for p in d.rglob("*"):
                        if p.is_file():
                            zf.write(p, f"{name}/{p.relative_to(d).as_posix()}")
                return z
            return d

        def manifest(mid, overrides, **kw):
            m = {"format": 1, "id": mid, "name": mid, "version": "1.0.0",
                 "target": {"title_id": TITLE_ID, "releases": release_ids(paths), "min_port_version": "0.0.1"},
                 "overrides": overrides}
            m.update(kw)
            return m

        text_ov = {"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": 0x40, "slot_sha256": sha256_bytes(slot),
                   "text": "Seçenekler"}
        tex_ov = {"type": "texture", "entry": "menu\\fake.dds", "image": "t/fake.png"}
        a = mk("a", manifest("test.a", [text_ov, tex_ov]), {"t/fake.png": png32}, as_zip=True)
        r = cmd_import(paths, a, enable=True)
        check("import: a zip with a top-level folder, text + texture, enabled", r["ranges"] == 3 and r["enabled"], r)
        res = resolve_all(paths, write_plan=paths["cache"])
        plan = Path(res["plan"]).read_text() if res.get("plan") else ""
        check("plan: one mod active, three ranges, header and end", res["active"] == ["test.a"] and res["ranges"] == 3
              and plan.startswith("R3HD_MOD_PLAN 1") and "\nend 2 3\n" in plan, res)
        rng = [ln.split() for ln in plan.splitlines() if ln.startswith("range ")]
        txt = next(x for x in rng if x[2] == str(0x40))
        blob = Path(" ".join(txt[7:])).read_bytes()
        check("plan: text range = cp1252 bytes + NUL padding, hashes of old / new bytes",
              blob == "Seçenekler".encode("cp1252") + b"\0" * 6 and txt[4] == f"{fnv1a64(slot):016x}"
              and txt[5] == f"{fnv1a64(blob):016x}", blob)
        tb = next(x for x in rng if x[2] == "0")
        tblob = Path(" ".join(tb[7:])).read_bytes()
        dec = decode_level(32, 32, [swap16(tblob[j * layout(32, 32, "DXT5")[2][0][2]:][:8 * 16]) for j in range(8)], "DXT5")
        check("plan: texture base level decodes to the mod's image", all(abs(dec[i] - [10, 200, 30, 255][i % 4]) <= 4
                                                                        for i in range(len(dec))))
        check("game data never written", before == {p: p.read_bytes() for p in game.rglob("*") if p.is_file()})
        cmd_set(paths, "test.a", False)
        res = resolve_all(paths, write_plan=paths["cache"])
        check("disable: no plan (the baseline)", res["active"] == [] and not (paths["cache"] / PLAN_NAME).exists())
        cmd_set(paths, "test.a", True)

        # D-101: optional achievement display text beside mod.json (never in the byte plan, never refuses a mod)
        h1, h2 = "1" * 64, "2" * 64
        ach_doc = {"format": 1, "kind": ACH_KIND, "title_id": TITLE_ID, "language": "tr", "strings": [
            {"id": 9, "field": "label", "source_sha256": h1, "text": "Başarı", "english": "x"},
            {"id": 9, "field": "description", "source_sha256": h2, "text": ""},
            {"id": 1, "field": "unachieved", "source_sha256": h2, "text": "Kilitli"}]}
        cmd_import(paths, mk("ach", manifest("test.ach", [tex_ov]), {"t/fake.png": png32,
                                                                     ACH_FILE: json.dumps(ach_doc).encode()}), enable=True)
        res = resolve_all(paths, write_plan=paths["cache"])
        tsv = Path(res.get("achievement_text") or paths["cache"] / "none").read_text(encoding="utf-8") \
            if res.get("achievement_text") else ""
        check("achievement text: written apart from the plan, empty texts left out, plan unchanged",
              "test.ach" in res["active"] and res["achievement_text_entries"] == 2 and res["ranges"] == 3
              and tsv == f"1\tunachieved\t{h2}\tKilitli\n9\tlabel\t{h1}\tBaşarı\n", (res, tsv))
        bad = dict(ach_doc, strings=[{"id": 9, "field": "gamerscore", "source_sha256": h1, "text": "100"}])
        cmd_import(paths, mk("ach2", manifest("test.ach", [tex_ov]), {"t/fake.png": png32,
                                                                      ACH_FILE: json.dumps(bad).encode()}), replace=True,
                   enable=True)
        res = resolve_all(paths, write_plan=paths["cache"])
        r_ach = next(x for x in res["mods"] if x["id"] == "test.ach")
        check("achievement text: a bad file is ignored, the mod still applies, no text file",
              r_ach["state"] == "active" and str(r_ach.get("achievement_text", "")).startswith("ignored")
              and not (paths["cache"] / ACH_TEXT_NAME).exists(), r_ach)
        check("achievement text: only text fields (no id / score / unlock edits)",
              achievement_text({ACH_FILE: json.dumps(dict(ach_doc, strings=[{"id": 9, "field": "label",
                                "source_sha256": h1, "text": "a\x01"}])).encode()})[1] != ""
              and achievement_text({})[0] == [] and achievement_text({ACH_FILE: b"{"})[1].startswith("not JSON"))
        cmd_remove(paths, "test.ach")

        # priority and declared conflicts / dependencies
        b = mk("b", manifest("test.b", [dict(text_ov, text="Ayarlar")]))
        cmd_import(paths, b, enable=True)
        res = resolve_all(paths)
        rb = next(x for x in res["mods"] if x["id"] == "test.b")
        check("priority: the first mod wins an overlap, the second is reported as shadowed",
              rb["state"] == "active" and rb["ranges"] == 0 and rb["shadowed"], rb)
        cmd_move(paths, "test.b", "top")
        res = resolve_all(paths)
        ra = next(x for x in res["mods"] if x["id"] == "test.a")
        check("priority: moving changes the winner", ra["ranges"] == 2 and len(ra["shadowed"]) == 1, ra)
        c = mk("c", manifest("test.c", [dict(text_ov, offset=0x50, slot_sha256=sha256_bytes(text_slot(bytes(fix), 0x50)),
                                             text="Yen")], conflicts=["test.b"]))
        cmd_import(paths, c, enable=True)
        rc = next(x for x in resolve_all(paths)["mods"] if x["id"] == "test.c")
        check("conflicts: a declared conflict with a higher-priority mod is refused", rc.get("code") == "CONFLICT", rc)
        cmd_remove(paths, "test.c")
        dmod = mk("d", manifest("test.d", [dict(text_ov, offset=0x50, slot_sha256=sha256_bytes(text_slot(bytes(fix), 0x50)),
                                                text="Yen")], requires=["test.missing"]))
        cmd_import(paths, dmod, enable=True)
        rd = next(x for x in resolve_all(paths)["mods"] if x["id"] == "test.d")
        check("requires: a missing dependency refuses the mod", rd.get("code") == "MISSING_DEPENDENCY", rd)
        check("import: the same id again is refused without replace", refused(lambda: cmd_import(paths, dmod), "EXISTS") is True)
        check("remove: folder and entry gone", cmd_remove(paths, "test.d")["removed"]
              and not installed_dir(paths, "test.d").exists()
              and "test.d" not in [e["id"] for e in load_state(paths)["mods"]])

        # tampering with an installed mod
        (installed_dir(paths, "test.b") / "mod.json").write_text(
            json.dumps(manifest("test.b", [dict(text_ov, text="X")])), encoding="utf-8")
        rb = next(x for x in resolve_all(paths)["mods"] if x["id"] == "test.b")
        check("installed files are verified (an edited mod.json is DAMAGED)", rb.get("code") == "DAMAGED", rb)

        # refusals: manifest and targets
        def imp(name, m, extra=None):
            return lambda: cmd_import(paths, mk(name, m, extra))
        check("refuse: unknown format", refused(imp("f1", dict(manifest("x.f1", [text_ov]), format=2)), "UNSUPPORTED") is True)
        check("refuse: other title", refused(imp("f2", dict(manifest("x.f2", [text_ov]), target={
            "title_id": "41560817", "releases": ["x"], "min_port_version": "0.1"})), "INCOMPATIBLE") is True)
        check("refuse: newer port version", refused(imp("f3", dict(manifest("x.f3", [text_ov]), target={
            "title_id": TITLE_ID, "releases": release_ids(paths), "min_port_version": "99.0"})), "INCOMPATIBLE") is True)
        check("refuse: other release", refused(imp("f4", dict(manifest("x.f4", [text_ov]), target={
            "title_id": TITLE_ID, "releases": ["ps3-hd"], "min_port_version": "0.1"})), "INCOMPATIBLE") is True)
        check("refuse: unknown key", refused(imp("f5", dict(manifest("x.f5", [text_ov]), script="x")), "BAD_MANIFEST") is True)
        check("refuse: text too long", refused(imp("f6", manifest("x.f6", [dict(text_ov, text="Yardım")])),
                                               "TEXT_GLYPH_MISSING") is True
              and refused(imp("f6b", manifest("x.f6b", [dict(text_ov, text="Seçenekler ve Yardım Menüsü")])),
                          "TEXT_GLYPH_MISSING") is True
              and refused(imp("f6c", manifest("x.f6c", [dict(text_ov, text="Secenekler ve Yardim")])), "TEXT_TOO_LONG") is True)
        check("refuse: changed target string", refused(imp("f7", manifest("x.f7", [dict(text_ov, slot_sha256="0" * 64)])),
                                                       "TARGET_CHANGED") is True)
        check("refuse: text outside fix.lvl", refused(imp("f8", manifest("x.f8", [dict(text_ov, file="Default.xex")])),
                                                      "UNSUPPORTED") is True)
        check("refuse: unknown override type (no code, no memory patch)",
              refused(imp("f9", manifest("x.f9", [{"type": "patch", "address": 1}])), "UNSUPPORTED") is True)
        check("refuse: wrong image size", refused(imp("f10", manifest("x.f10", [tex_ov]),
                                                      {"t/fake.png": write_png(16, 16, bytes(1024))}), "BAD_IMAGE") is True)
        check("refuse: missing texture entry", refused(imp("f11", manifest("x.f11", [dict(tex_ov, entry="menu\\none.dds")]),
                                                       {"t/fake.png": png32}), "TARGET_MISSING") is True)
        check("refuse: corrupt PNG", refused(imp("f12", manifest("x.f12", [tex_ov]), {"t/fake.png": png32[:-20] + b"x" * 20}),
                                             "BAD_IMAGE") is True)

        # refusals: package shape
        def zip_with(name, members, attrs=None):
            z = td / "src" / f"{name}.zip"
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                for n, data in members.items():
                    zi = zipfile.ZipInfo(n)
                    if attrs and n in attrs:
                        zi.external_attr = attrs[n]
                    zf.writestr(zi, data, compress_type=zipfile.ZIP_DEFLATED)
            return z
        good = json.dumps(manifest("z.ok", [text_ov])).encode()
        for label, members, attrs, code in (
                ("path traversal", {"mod.json": good, "../evil.txt": b"x"}, None, "UNSAFE_PACKAGE"),
                ("absolute path", {"mod.json": good, "/abs.txt": b"x"}, None, "UNSAFE_PACKAGE"),
                ("drive path", {"mod.json": good, "C:/x.txt": b"x"}, None, "UNSAFE_PACKAGE"),
                ("backslash", {"mod.json": good, "a\\..\\x.txt": b"x"}, None, "UNSAFE_PACKAGE"),
                ("executable", {"mod.json": good, "run.exe": b"MZ"}, None, "UNSAFE_PACKAGE"),
                ("DLL", {"mod.json": good, "x/hook.dll": b"MZ"}, None, "UNSAFE_PACKAGE"),
                ("script", {"mod.json": good, "setup.ps1": b"x"}, None, "UNSAFE_PACKAGE"),
                ("reserved name", {"mod.json": good, "nul.txt": b"x"}, None, "UNSAFE_PACKAGE"),
                ("symlink member", {"mod.json": good, "link.txt": b"/etc/passwd"}, {"link.txt": (0o120777 << 16)},
                 "UNSAFE_PACKAGE"),
                ("duplicate by case", {"mod.json": good, "A.txt": b"1", "a.txt": b"2"}, None, "UNSAFE_PACKAGE"),
                ("no manifest", {"readme.txt": b"x"}, None, "NOT_A_MOD"),
                ("zip bomb", {"mod.json": good, "big.txt": b"\0" * (8 << 20)}, None, "TOO_LARGE")):
            z = zip_with(label.replace(" ", "_"), members, attrs)
            check(f"refuse package: {label}", refused(lambda z=z: read_package(z), code) is True)
        # a folder with a link (when the system allows creating one)
        lnk = td / "src" / "linkdir"
        lnk.mkdir()
        (lnk / "mod.json").write_bytes(good)
        try:
            os.symlink(game / "GAMEDATAbin" / "fix.lvl", lnk / "fix.txt")
            check("refuse package: a folder holding a symbolic link", refused(lambda: read_package(lnk), "UNSAFE_PACKAGE") is True)
        except OSError:
            print("SKIP refuse package: a folder holding a symbolic link (no symlink privilege)")
        check("refused imports left nothing behind",
              sorted(p.name for p in (paths["mods"] / "installed").iterdir()) == ["test.a", "test.b"]
              and not list(paths["mods"].glob(".staging-*")))
        check("game data never written (end)", before == {p: p.read_bytes() for p in game.rglob("*") if p.is_file()})
        # M33 review fixes
        check("refuse: an id that is a path ('.', '..', 'a/b') never reaches the file system",
              all(refused(lambda i=i: cmd_remove(paths, i), "NOT_INSTALLED") is True for i in (".", "..", "a/b", "A"))
              and (paths["mods"] / "installed" / "test.a").is_dir())
        z = zip_with("nulspace", {"mod.json": good, "nul .txt": b"x"})
        check("refuse package: a device name with a space before its extension", refused(lambda: read_package(z),
                                                                                       "UNSAFE_PACKAGE") is True)
        bin_fix = bytearray(fix)
        bin_fix[0x80:0x84] = b"\x01\x02A\0"
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(bytes(bin_fix))
        check("refuse: a NUL-delimited run that is not plain text is not a text target",
              refused(lambda: text_slot(bytes(bin_fix), 0x80), "UNSUPPORTED") is True)
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(bytes(fix))
        inst = paths["mods"] / "installed"
        os.replace(inst / "test.b", inst / ".old-test.b-999999")   # a replace interrupted between its two renames
        (paths["mods"] / ".staging-999998").mkdir()
        (inst / ".removing-x-999997").mkdir()
        done = recover(paths)
        check("recover: an interrupted replace gets its folder back; staging and half-removed folders go",
              (inst / "test.b").is_dir() and not (paths["mods"] / ".staging-999998").exists()
              and not (inst / ".removing-x-999997").exists() and len(done) == 3, done)
        saved_limit = globals()["PLAN_MAX_RANGES"]
        globals()["PLAN_MAX_RANGES"] = 1
        try:
            check("plan: more than the runtime carries is refused before launch",
                  refused(lambda: resolve_all(paths, write_plan=paths["cache"]), "TOO_LARGE") is True)
        finally:
            globals()["PLAN_MAX_RANGES"] = saved_limit
        # state damage is refused, not rewritten
        (paths["mods"] / "state.json").write_text("{bad", encoding="utf-8")
        check("damaged state.json is refused and kept", refused(lambda: resolve_all(paths), "STATE_DAMAGED") is True
              and (paths["mods"] / "state.json").read_text() == "{bad")
    saved_font = dict(FONT)
    try:
        selftest_m34(check, refused, release_ids)
    finally:
        FONT.clear()
        FONT.update(saved_font)
    selftest_m35(check, refused)
    selftest_m38(check, refused)
    n_fail = results.count(False)
    print(f"R3HD_MODS_SELFTEST {'PASS' if not n_fail else 'FAIL'} {len(results) - n_fail}/{len(results)}")
    return 1 if n_fail else 0


def selftest_m34(check, refused, release_ids):
    """M34: glyph overrides, Turkish text and moved text on a synthetic fix.lvl (two FontRay copies, two other
    definitions, a 64x64 DXT5 atlas in the fix bundle, a three-string table that fix.ptr lists)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        game = td / "game"
        (game / "GAMEDATAbin").mkdir(parents=True)
        fix = bytearray(0x6000)
        for off, s in ((0x100, b"Alpha"), (0x108, b"Beta beta beta"), (0x118, b"Gamma"), (0x120, b"Delta")):
            fix[off:off + len(s)] = s
        refs = {0x200: 0x100, 0x204: 0x108, 0x208: 0x118, 0x20C: 0x108, 0x210: 0x120}   # Beta twice (shared)
        for loc, off in refs.items():
            struct.pack_into(">I", fix, loc, off - REF_BIAS)
        ptr = struct.pack(">I", len(refs)) + b"".join(struct.pack(">II", 0, loc) for loc in refs)
        (game / "GAMEDATAbin" / "fix.ptr").write_bytes(ptr)
        # fonts: every printable code but the Turkish ones on one 6x8 cell; i, g on their own cells
        defs = (0x1000, 0x2000, 0x3000, 0x4000)
        for k, base in enumerate(defs):
            fix[base:base + 7] = b"FontRay" if k < 2 else b"FontPAD"
            for c in list(range(0x20, 0x7F)) + list(range(0xC0, 0x100)):
                if c in (0xD0, 0xDE, 0xF0, 0xFD, 0xFE) or k >= 2 and c != 0x41:
                    continue
                x, y, h, w = {ord("i"): (8, 0, 10, 4), ord("g"): (16, 0, 12, 6)}.get(c, (0, 0, 8, 6))
                struct.pack_into(">6H2B", fix, base + 50 + c * 14, x, y, h, w, 1, 2 if c == ord("g") else 0, 0, 1)
        rec = 0x5000
        struct.pack_into(">I", fix, rec + 0x14, 0x8008)
        struct.pack_into(">HH", fix, rec + 0x1C, 64, 64)
        nm = b"texts\\typoray3.tga\0"
        fix[rec + 0x4A:rec + 0x4A + len(nm)] = nm
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(bytes(fix))
        FONT.update(fontray=defs[:2], others=defs[2:], atlas_size=(64, 64, "DXT5"),
                    sha256={b: sha256_bytes(bytes(fix[b:b + FONTDEF_BYTES])) for b in defs})
        img = bytearray(64 * 64 * 4)
        for y in range(64):
            for x in range(64):
                ink = (x < 6 and y < 8) or (8 <= x < 12 and (y < 2 or 4 <= y < 10)) or (16 <= x < 22 and 2 <= y < 12)
                img[(y * 64 + x) * 4:(y * 64 + x) * 4 + 4] = b"\xff\xff\xff" + (b"\xff" if ink else b"\0")
        base, mips, lay = layout(64, 64, "DXT5")
        blobs = [bytearray(base), bytearray(mips)]
        lw, lh, cur = 64, 64, bytes(img)
        for i, lv in enumerate(lay):
            if i:
                lw, lh, cur = downsample(lw, lh, cur)
            for j, row in enumerate(encode_level(lw, lh, cur, "DXT5")):
                at = lv[1] + (lv[4] + j) * lv[2] + lv[3] * 16
                blobs[lv[0]][at:at + len(row)] = swap16(row)
        bhf = struct.pack(">I", 1) + struct.pack(">4I", base, 0, mips, base) + b"texts\\typoray3.dds".ljust(0x104, b"\0")
        (game / "GAMEDATAbin" / "fix.bhf").write_bytes(bhf)
        (game / "GAMEDATAbin" / "fix.btf").write_bytes(bytes(blobs[0]) + bytes(blobs[1]))
        before = {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}
        paths = {"home": None, "mods": td / "mods", "cache": td / "cache", "game": game}
        rel = release_ids(paths)
        n = [0]

        def mod(mid, overrides, **kw):
            d = td / "src" / f"{mid}-{n[0]}"
            n[0] += 1
            d.mkdir(parents=True)
            m = {"format": 1, "id": mid, "name": mid, "version": "1.0.0",
                 "target": {"title_id": TITLE_ID, "releases": rel, "min_port_version": "0.0.1"}, "overrides": overrides}
            m.update(kw)
            (d / "mod.json").write_text(json.dumps(m), encoding="utf-8")
            return d
        dotless = {"type": "glyph", "char": "ı", "width": 4, "height": 6, "descent": 0,
                   "layers": [{"glyph": "i", "crop": [0, 4, 4, 10], "x": 0, "y": 0}]}
        gbreve = {"type": "glyph", "char": "ğ", "width": 6, "height": 15, "descent": 2,
                  "layers": [{"bitmap": ["@..@", ".@@."], "x": 1, "y": 0}, {"glyph": "g", "x": 0, "y": 3}]}

        def slot_hash(off):
            return sha256_bytes(text_slot(bytes(fix), off))

        def text(off, t):
            return {"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": off, "slot_sha256": slot_hash(off), "text": t}
        font_mod = mod("tr.font", [dotless, gbreve])
        cmd_import(paths, font_mod, enable=True)
        res = resolve_all(paths, write_plan=paths["cache"])
        plan = Path(res["plan"]).read_text()
        rng = [ln.split() for ln in plan.splitlines() if ln.startswith("range ")]
        recs = {int(r[2]): Path(" ".join(r[7:])).read_bytes() for r in rng if r[3] == "14"}
        check("glyph: a record per glyph in both FontRay copies, at the Windows-1254 codes",
              sorted(recs) == sorted(b + 50 + c * 14 for b in defs[:2] for c in (0xF0, 0xFD)), sorted(recs))
        r_i = struct.unpack(">6H2B", recs[defs[0] + 50 + 0xFD * 14])
        check("glyph: a single crop at the origin reuses the font's own pixels (dotless i = the stem of i)",
              r_i == (8, 4, 6, 4, 1, 0, 0, 1), r_i)
        r_g = struct.unpack(">6H2B", recs[defs[0] + 50 + 0xF0 * 14])
        check("glyph: a composed glyph gets a cell of its size and descent", r_g[2:8] == (15, 6, 1, 2, 0, 1), r_g)
        tb = [Path(" ".join(r[7:])).read_bytes() for r in rng if r[3] == str(base)][0]
        tm = [Path(" ".join(r[7:])).read_bytes() for r in rng if r[3] == str(mips)][0]
        old = decode_level(64, 64, level_rows((bytes(blobs[0]), bytes(blobs[1])), lay[0], "DXT5"), "DXT5")
        new = decode_level(64, 64, level_rows((tb, tm), lay[0], "DXT5"), "DXT5")
        cells = [(0, 0, 6, 8), (8, 0, 12, 10), (16, 0, 22, 12)]
        inside = [(x, y) for x0, y0, x1, y1 in cells for y in range(y0, y1) for x in range(x0, x1)]
        check("glyph: every texel of the mapped glyphs keeps its value", all(old[(y * 64 + x) * 4:(y * 64 + x) * 4 + 4]
                                                                            == new[(y * 64 + x) * 4:(y * 64 + x) * 4 + 4]
                                                                            for x, y in inside))
        gx, gy = r_g[0], r_g[1]
        check("glyph: the composed picture is in its cell (breve corners and the g's ink, transparent between)",
              new[((gy) * 64 + gx + 1) * 4 + 3] > 200 and new[((gy) * 64 + gx + 2) * 4 + 3] < 40
              and new[((gy + 3 + 5) * 64 + gx + 2) * 4 + 3] > 200, (gx, gy))
        check("glyph: game data never written", before == {p: p.read_bytes() for p in game.rglob("*") if p.is_file()})
        # Turkish text
        check("text: Turkish letters encode to their Windows-1254 bytes when glyphs exist",
              encode_text("ığ", frozenset("ığ")) == b"\xfd\xf0")
        check("text: without a glyph override a Turkish letter is refused",
              refused(lambda: cmd_import(paths, mod("x.t1", [text(0x100, "ığ")])), "TEXT_GLYPH_MISSING") is True)
        check("text: with a required font mod it is accepted",
              cmd_import(paths, mod("tr.text", [text(0x100, "ığ")], requires=["tr.font"]), enable=True)["ranges"] == 1)
        check("text: a letter whose byte a glyph takes (Ý for İ) is refused",
              refused(lambda: encode_text("Ý", frozenset("İ")), "TEXT_GLYPH_MISSING") is True)
        check("text: a byte without a glyph in the font is refused (Ð)",
              refused(lambda: encode_text("Ð", frozenset(), set(range(0x20, 0x7F))), "TEXT_GLYPH_MISSING") is True)
        check("text: a mod without glyphs may still use Ý (M33 behaviour; M34 review)",
              parse_manifest({"mod.json": json.dumps({"format": 1, "id": "x.y", "name": "y", "version": "1.0.0",
                                                      "target": {"title_id": TITLE_ID, "releases": rel,
                                                                 "min_port_version": "0.0.1"},
                                                      "overrides": [text(0x100, "Ýes")]}).encode()})["id"] == "x.y")
        check("text: in-band codes stay allowed", encode_text("\\jcA\\lB", frozenset(), set(range(0x41, 0x7F))) == b"\\jcA\\lB")
        # the ellipsis (U+2026 = 0x85, a glyph override like the Turkish letters)
        ell = {"type": "glyph", "char": "…", "width": 5, "height": 1, "descent": 0,
               "layers": [{"bitmap": ["@.@.@"], "x": 0, "y": 0}]}
        check("text: without its glyph override the ellipsis is refused",
              refused(lambda: cmd_import(paths, mod("x.e1", [text(0x100, "A…")])), "TEXT_GLYPH_MISSING") is True)
        check("text: with its glyph the ellipsis encodes to 0x85 and passes the font check",
              encode_text("A…", frozenset("…"), set(range(0x41, 0x7F))) == b"A\x85")
        er = compile_mod(parse_manifest({"mod.json": (mod("x.e2", [ell, text(0x100, "A…")]) / "mod.json").read_bytes()}),
                         {}, paths)
        e_recs = {r[1]: struct.unpack(">6H2B", r[2]) for r in er if r[3].startswith("glyph ")}
        e_txt = [r[2] for r in er if r[3].startswith("text")]
        check("glyph: the ellipsis gets a record at 0x85 in both FontRay copies, and the text its byte",
              sorted(e_recs) == sorted(b + 50 + 0x85 * 14 for b in defs[:2])
              and all(v[2:8] == (1, 5, 1, 0, 0, 1) for v in e_recs.values()) and e_txt and e_txt[0].startswith(b"A\x85\0"),
              (sorted(e_recs), e_txt))
        # Issue #2: CP1252 ligatures have artwork, but no shipped FontRay records.
        # They remain opt-in glyphs; plain text must never silently draw a blank.
        for ch, code in (("Œ", 0x8C), ("œ", 0x9C)):
            check(f"French: {ch} without a glyph is refused",
                  refused(lambda ch=ch: encode_text(ch), "TEXT_GLYPH_MISSING") is True)
            check(f"French: {ch} encodes only with its glyph",
                  encode_text(ch, frozenset(ch), set()) == bytes([code]))
            lig = dict(ell, char=ch)
            rs = compile_mod(parse_manifest({"mod.json": (mod(f"x.fr{code}", [lig, text(0x100, "A" + ch)]) /
                                                          "mod.json").read_bytes()}), {}, paths)
            recs = {r[1]: struct.unpack(">6H2B", r[2]) for r in rs if r[3].startswith("glyph ")}
            txt = [r[2] for r in rs if r[3].startswith("text")]
            check(f"French: {ch} gets both records and the correct text byte",
                  sorted(recs) == sorted(b + 50 + code * 14 for b in defs[:2])
                  and all(v[2:8] == (1, 5, 1, 0, 0, 1) for v in recs.values())
                  and txt and txt[0].startswith(bytes([65, code, 0])))
        check("French: one ligature never authorizes the other",
              refused(lambda: encode_text("œŒ", frozenset("œ")), "TEXT_GLYPH_MISSING") is True)
        # moved text
        mv = mod("x.move", [text(0x108, "B"), text(0x100, "Much longer")])
        ranges = compile_mod(parse_manifest({"mod.json": (mv / "mod.json").read_bytes()}), {}, paths)
        ptrs = {r[1]: struct.unpack(">I", r[2])[0] for r in ranges if r[3].startswith("pointer")}
        tgt = list(ptrs.values())[0] + REF_BIAS if ptrs else None
        content = {r[1]: r[2] for r in ranges if r[3].startswith("text")}
        check("move: a longer text goes into the mod's freed space and its pointer follows",
              list(ptrs) == [0x200] and tgt is not None and 0x108 < tgt < 0x118
              and content[0x108][tgt - 0x108:].startswith(b"Much longer\0") and content[0x108][:2] == b"B\0",
              (ptrs, content))
        mv2 = mod("x.move2", [text(0x100, "x"), text(0x108, "Beta is now much longer than before")])
        m2 = parse_manifest({"mod.json": (mv2 / "mod.json").read_bytes()})
        check("move: no room among the mod's own slots is refused with the size",
              refused(lambda: compile_mod(m2, {}, paths), "TEXT_TOO_LONG") is True)
        mv3 = mod("x.move3", [text(0x100, "a"), text(0x118, "g"), text(0x108, "Beta, shared, long")])
        r3 = compile_mod(parse_manifest({"mod.json": (mv3 / "mod.json").read_bytes()}), {}, paths)
        p3 = sorted(r[1] for r in r3 if r[3].startswith("pointer"))
        check("move: every pointer to a shared string is redirected; adjacent free space joins",
              p3 == [0x204, 0x20C], p3)
        fx = bytearray(fix)
        struct.pack_into(">I", fx, 0x210, 0x10A - REF_BIAS)   # a pointer into the middle of Beta's slot
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(bytes(fx))
        (game / "GAMEDATAbin" / "fix.ptr").write_bytes(ptr)
        check("move: a slot something points into never moves",
              refused(lambda: compile_mod(parse_manifest({"mod.json": (mv3 / "mod.json").read_bytes()}), {}, paths),
                      "TEXT_TOO_LONG") is True)
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(bytes(fix))
        # atomic mods: a higher-priority texture of the atlas refuses the font mod and what requires it
        png = write_png(64, 64, bytes(64 * 64 * 4))
        atl = mod("x.atlas", [{"type": "texture", "entry": "texts\\typoray3.dds", "image": "a.png"}])
        (atl / "a.png").write_bytes(png)
        cmd_import(paths, atl, enable=True)
        cmd_move(paths, "x.atlas", "top")
        res = resolve_all(paths)
        st = {x["id"]: (x["state"], x.get("code")) for x in res["mods"]}
        check("linked: a font mod under a mod that changes its atlas is refused whole, its dependants too",
              st["tr.font"] == ("invalid", "CONFLICT") and st["tr.text"] == ("invalid", "MISSING_DEPENDENCY")
              and st["x.atlas"][0] == "active", st)
        cmd_move(paths, "x.atlas", "bottom")
        res = resolve_all(paths)
        st = {x["id"]: (x["state"], x.get("code")) for x in res["mods"]}
        check("linked: above it, the font mod applies and the atlas mod is the shadowed one",
              st["tr.font"][0] == "active" and st["tr.text"][0] == "active"
              and next(x for x in res["mods"] if x["id"] == "x.atlas")["shadowed"], st)
        # damaged or foreign data
        bad = bytearray(fix)
        bad[defs[1] + 50 + 0x41 * 14] ^= 1
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(bytes(bad))
        check("glyph: a font that is not the shipped one is refused",
              refused(lambda: compile_glyphs(parse_manifest({"mod.json": (font_mod / "mod.json").read_bytes()}), {}, paths),
                      "TARGET_CHANGED") is True)
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(bytes(fix))
        big = dict(gbreve, char="Ğ", width=60, height=60, layers=[{"glyph": "g", "x": 0, "y": 0}])
        check("glyph: no room in the atlas is refused",
              refused(lambda: compile_glyphs(parse_manifest({"mod.json": mod("x.big", [big]).joinpath("mod.json").read_bytes()}),
                                             {}, paths), "UNSUPPORTED") is True)
        for label, g, code in (
                ("a letter that is not Turkish", dict(dotless, char="x"), "UNSUPPORTED"),
                ("a size over 64", dict(dotless, width=65), "BAD_MANIFEST"),
                ("a layer outside the glyph", dict(dotless, layers=[{"glyph": "i", "x": 3, "y": 0}]), "BAD_MANIFEST"),
                ("a crop outside the source glyph", dict(dotless, layers=[{"glyph": "i", "crop": [0, 0, 9, 9], "x": 0, "y": 0}]),
                 "BAD_MANIFEST"),
                ("a bitmap with other characters", dict(dotless, layers=[{"bitmap": ["ab"], "x": 0, "y": 0}]), "BAD_MANIFEST"),
                ("an unknown layer key", dict(dotless, layers=[{"glyph": "i", "x": 0, "y": 0, "code": 1}]), "BAD_MANIFEST"),
                ("a char that is not a text (M34 review)", dict(dotless, char=["x"]), "UNSUPPORTED"),
                ("an image that is not a name (M34 review)", dict(dotless, layers=[{"image": ["a"], "x": 0, "y": 0}]),
                 "BAD_MANIFEST"),
                ("the same glyph twice", None, "BAD_MANIFEST")):
            ov = [dotless, dotless] if g is None else [g]
            check(f"refuse glyph: {label}", refused(lambda ov=ov: compile_glyphs(
                parse_manifest({"mod.json": json.dumps({"format": 1, "id": "x.g", "name": "g", "version": "1.0.0",
                                                        "target": {"title_id": TITLE_ID, "releases": rel,
                                                                   "min_port_version": "0.0.1"},
                                                        "overrides": ov}).encode()}), {}, paths), code) is True)
        check("glyph: game data never written (end)", before == {p: p.read_bytes() for p in game.rglob("*") if p.is_file()})


def selftest_m35(check, refused):
    """M35: subtitle overrides on a synthetic VS.sub (original strings, two languages, two movies)."""
    def vs(cues, strings, tail=b""):
        b = struct.pack("<H", len(cues))
        for i, (lang, movie, start, end) in enumerate(cues):
            b += struct.pack("<B3x4I", lang, movie, start, end, i)
        b += struct.pack("<H", len(strings)) + b"".join(struct.pack("<H", len(x)) + x for x in strings)
        return b + tail
    cues = [(1, 3, 1000, 2000), (1, 3, 2500, 4000), (2, 3, 1000, 2000), (1, 9, 500, 900)]
    texts = [b"Hello there.", b"Mind the gap!", b"Bonjour.", b"Off we go."]
    data = vs(cues, texts)
    sub = parse_vs_sub(data)
    check("subtitle: ids per language and movie in file order",
          list(sub["ids"]) == ["vs.en.3.0", "vs.en.3.1", "vs.fr.3.0", "vs.en.9.0"], list(sub["ids"]))
    for label, bad in (("a language outside 1-5", vs([(6, 3, 1, 2)], [b"x"])),
                       ("an end before the start", vs([(1, 3, 5, 2)], [b"x"])),
                       ("a string index out of order", vs([(1, 3, 1, 2)], [b"x"])[:18] + struct.pack("<I", 7) + vs([(1, 3, 1, 2)], [b"x"])[22:]),
                       ("a string count unlike the cue count", vs([(1, 3, 1, 2)], [b"x", b"y"])),
                       ("a string past the end", vs([(1, 3, 1, 2)], [b"x"])[:-1]),
                       ("bytes after the last string", vs([(1, 3, 1, 2)], [b"x"], b"junk")),
                       ("a NUL inside a string", vs([(1, 3, 1, 2)], [b"a\0b"]))):
        check(f"subtitle: refused: {label}", refused(lambda bad=bad: parse_vs_sub(bad), "TARGET_CHANGED") is True)
    with tempfile.TemporaryDirectory() as td:
        game = Path(td)
        (game / "GAMEDATAbin").mkdir()
        (game / "GAMEDATAbin" / "VS.sub").write_bytes(data)
        paths = {"game": game}

        def ov(sid, text, h=None):
            return {"type": "subtitle", "id": sid, "source_sha256": h or sub_hash(sub, sub["ids"][sid]), "text": text}
        (p, off, new, what), = compile_subtitles([ov("vs.en.3.1", "Dikkat et!")], paths, frozenset(), None)
        got = data[:off] + new
        back = parse_vs_sub(got)
        check("subtitle: the file keeps its size; cues and other strings unchanged",
              len(got) == len(data) and data[:off] == got[:off] and [c[5] for c in back["cues"]] == [c[5] for c in sub["cues"]]
              and back["strings"][1] == b"Dikkat et!" and back["strings"][2:] == sub["strings"][2:]
              and set(got[back["end"]:]) <= {0}, (back["strings"], len(got), len(data)))
        same = compile_subtitles([ov("vs.en.3.0", "Hello there.")], paths, frozenset(), None)[0]
        check("subtitle: the same text rebuilds the original bytes", data[:same[1]] + same[2] == data)
        tr = compile_subtitles([ov("vs.en.9.0", "Şimdi!")], paths, frozenset("ğĞşŞıİ"), None)[0]
        check("subtitle: a Turkish letter with its glyph encodes to Windows-1254",
              parse_vs_sub(data[:tr[1]] + tr[2])["strings"][3] == b"\xdeimdi!")
        # M36: a longer total grows the file (the bytes past its end are the plan's), refused on an older port.
        (gp, goff, gnew, gwhat), = compile_subtitles([ov("vs.en.3.0", "Merhaba, nasılsın bakalım?")], paths,
                                                     frozenset("ğĞşŞıİ"), None)
        grown = data[:goff] + gnew
        gback = parse_vs_sub(grown)
        check("subtitle (M36): a longer total grows the file; cues, order and the other strings unchanged",
              len(grown) > len(data) and gback["end"] == len(grown) and gwhat.endswith(f"+{len(grown) - len(data)}")
              and [c[5] for c in gback["cues"]] == [c[5] for c in sub["cues"]]
              and gback["strings"][1:] == sub["strings"][1:], (len(grown), len(data), gwhat))
        with tempfile.TemporaryDirectory() as hd:
            (Path(hd) / "installer.json").write_text(json.dumps({"version": "0.35.0"}))
            check("subtitle (M36): growing on a port before 0.36.0 is refused, with the overage",
                  refused(lambda: compile_subtitles([ov("vs.en.9.0", "Off we go, off we go, off we go!")],
                                                    dict(paths, home=Path(hd)), frozenset(), None), "INCOMPATIBLE") is True)
            check("subtitle (M36): a total that still fits works on 0.35.0 (zero-padded, same size)",
                  len(data[:off] + compile_subtitles([ov("vs.en.3.1", "Dikkat et!")], dict(paths, home=Path(hd)),
                                                     frozenset(), None)[0][2]) == len(data))
        saved_grow = globals()["SUB_MAX_GROW"]
        globals()["SUB_MAX_GROW"] = 4
        try:
            check("subtitle (M36): growth beyond the limit is refused with the overage",
                  refused(lambda: compile_subtitles([ov("vs.en.9.0", "Off we go, off we go, off we go!")], paths,
                                                    frozenset(), None), "TEXT_TOO_LONG") is True)
        finally:
            globals()["SUB_MAX_GROW"] = saved_grow
        # The plan carries the grow record right after VS.sub's file record, and the range's game hash covers only
        # the part inside the file.
        cache = game / "cache"
        plan_text = Path(write_plan_files({"cache": cache}, cache, [(gp, goff, gnew, "m.sub")], [("m.sub", "1")])) \
            .read_text(encoding="utf-8").splitlines()
        fi = next(i for i, ln in enumerate(plan_text) if ln.startswith("file "))
        rg = next(ln for ln in plan_text if ln.startswith("range ")).split(" ")
        check("subtitle (M36): plan: `grow 0 <new size>` follows the file record; the game hash is of the bytes inside",
              plan_text[fi] == f"file {len(data)} {os.path.abspath(gp)}" and plan_text[fi + 1] == f"grow 0 {len(grown)}"
              and rg[4] == f"{fnv1a64(data[goff:]):016x}" and int(rg[3]) == len(gnew), plan_text)
        other = game / "GAMEDATAbin" / "x.lvl"
        other.write_bytes(b"abc")
        check("subtitle (M36): plan: no other file may reach past its end",
              refused(lambda: write_plan_files({"cache": cache}, cache, [(other, 1, b"xyz", "m.sub")], [("m.sub", "1")]),
                      "TOO_LARGE") is True)
        check("subtitle: a cue of another game version is refused",
              refused(lambda: compile_subtitles([ov("vs.en.3.0", "x", "0" * 64)], paths, frozenset(), None),
                      "TARGET_CHANGED") is True)
        check("subtitle: an id the file does not have is refused",
              refused(lambda: compile_subtitles([ov("vs.en.3.0", "x") | {"id": "vs.en.4.0"}], paths, frozenset(), None),
                      "TARGET_CHANGED") is True)
        check("subtitle: a Turkish letter without its glyph is refused",
              refused(lambda: compile_subtitles([ov("vs.en.3.0", "Şu")], paths, frozenset(), None),
                      "TEXT_GLYPH_MISSING") is True)
    base = {"format": 1, "id": "x.sub", "name": "x", "version": "1.0.0",
            "target": {"title_id": TITLE_ID, "releases": ["r"], "min_port_version": "0.35.0"}}
    good = {"type": "subtitle", "id": "vs.en.3.0", "source_sha256": "a" * 64, "text": "Merhaba."}
    for label, o in (("a timing field", dict(good, start_ms=5)), ("a malformed id", dict(good, id="vs.en.3")),
                     ("an empty text", dict(good, text="")), ("a short hash", dict(good, source_sha256="ab"))):
        check(f"subtitle manifest: refused: {label}", refused(
            lambda o=o: parse_manifest({"mod.json": json.dumps(dict(base, overrides=[o])).encode()}), "BAD_MANIFEST") is True)
    check("subtitle manifest: the same id twice is refused", refused(
        lambda: parse_manifest({"mod.json": json.dumps(dict(base, overrides=[good, good])).encode()}), "BAD_MANIFEST") is True)
    check("subtitle manifest: a valid override parses",
          parse_manifest({"mod.json": json.dumps(dict(base, overrides=[good])).encode()})["overrides"][0]["id"] == "vs.en.3.0")


def selftest_m38(check, refused):
    """M38: the compacting text packer on a synthetic table: six 7-letter strings in adjacent 8-byte slots at 0x100,
    one pointer each at 0x400 + 4i, and a second pointer to String4 (a shared string, as another language's table)."""
    saved = os.environ.pop(TEXT_PACKER_ENV, None)
    try:
        with tempfile.TemporaryDirectory() as td:
            game = Path(td) / "game"
            (game / "GAMEDATAbin").mkdir(parents=True)
            paths = {"game": game}
            offs = [0x100 + 8 * i for i in range(6)]
            base_refs = {0x400 + 4 * i: off for i, off in enumerate(offs)}
            base_refs[0x420] = offs[4]

            def table(refs):
                fix = bytearray(0x800)
                for i, off in enumerate(offs):
                    fix[off:off + 7] = f"String{i}".encode()
                for loc, off in refs.items():
                    struct.pack_into(">I", fix, loc, off - REF_BIAS)
                (game / "GAMEDATAbin" / "fix.lvl").write_bytes(bytes(fix))
                (game / "GAMEDATAbin" / "fix.ptr").write_bytes(
                    struct.pack(">I", len(refs)) + b"".join(struct.pack(">II", 0, loc) for loc in refs))
                return bytes(fix)

            def ovs(fix, texts):
                return [{"type": "text", "file": "GAMEDATAbin/fix.lvl", "offset": offs[i],
                         "slot_sha256": sha256_bytes(text_slot(fix, offs[i])), "text": t} for i, t in texts.items()]

            def compile_(fix, texts, packer=None):
                return compile_texts(ovs(fix, texts), paths, frozenset(), None, packer)

            def seen(fix, ranges, refs):
                """{pointer location: the string the game reads through it} with the ranges applied."""
                d = bytearray(fix)
                for _, off, data, _ in ranges:
                    d[off:off + len(data)] = data
                out = {}
                for loc in refs:
                    at = struct.unpack_from(">I", d, loc)[0] + REF_BIAS
                    out[loc] = bytes(d[at:d.index(b"\0", at)]).decode("latin-1")
                return out

            def expect(texts, refs):
                return {loc: texts.get(offs.index(off), f"String{offs.index(off)}") if off in offs else None
                        for loc, off in refs.items()}

            def inside(ranges, refs, lo, hi):
                return all(lo <= off and off + len(data) <= hi or (off in refs and len(data) == 4)
                           for _, off, data, _ in ranges)
            fix = table(base_refs)
            frag = {0: "x", 1: "Metin 1", 2: "y", 3: "Metin 3", 4: "Uzun metin"}
            check("compact: the fragmented case is refused by the M34 packer (free 16 bytes in chunks of 4, 4, 8; "
                  "11 needed)", refused(lambda: compile_(fix, frag, "m34"), "TEXT_TOO_LONG") is True)
            r, moved, packer = compile_(fix, frag)
            check("compact: auto falls back to the compacting packer, which packs it", packer == "compact" and moved,
                  packer)
            check("compact: every pointer reads its new text, the shared string through both pointers, the string "
                  "outside the mod unchanged", seen(fix, r, base_refs) == expect(frag, base_refs), seen(fix, r, base_refs))
            ptr_locs = sorted(off for _, off, data, what in r if what.startswith("pointer"))
            check("compact: strings keep their offsets unless pushed (String0-2 stay; 3 and 4 move, 4 by both pointers)",
                  ptr_locs == [0x40C, 0x410, 0x420], ptr_locs)
            check("compact: ranges stay inside the mod's slots or are listed pointer locations",
                  inside(r, base_refs, offs[0], offs[5]), [(x[1], len(x[2])) for x in r])
            check("compact: deterministic", compile_(fix, frag) == (r, moved, packer))
            os.environ[TEXT_PACKER_ENV] = "m34"
            check("gate: R3HD_TEXT_PACKER=m34 keeps the M34 refusal",
                  refused(lambda: compile_(fix, frag), "TEXT_TOO_LONG") is True)
            os.environ[TEXT_PACKER_ENV] = "bogus"
            check("gate: an unknown packer name is refused", refused(lambda: compile_(fix, frag), "USAGE") is True)
            os.environ.pop(TEXT_PACKER_ENV)
            easy = {0: "x", 1: "Uzun metin"}
            r34 = compile_(fix, easy, "m34")
            check("gate: a mod the M34 packer packs gets the very same ranges under auto",
                  compile_(fix, easy) == r34 and r34[2] == "m34" and compile_(fix, {0: "x"})[2] == "fit")
            rc = compile_(fix, easy, "compact")
            check("gate: forced compaction of that mod reads the same texts",
                  rc[2] == "compact" and seen(fix, rc[0], base_refs) == expect(easy, base_refs))
            # a pointer into String2 pins it: two runs; the run of String3 and String4 cannot keep both, the first
            # attempt (own strings first) fails and the second (all strings, largest first) packs
            pin_refs = {**base_refs, 0x430: offs[2] + 2}
            fix = table(pin_refs)
            r, moved, packer = compile_(fix, frag)
            got = seen(fix, r, pin_refs)
            check("pinned: a slot pointed into stays; the rest packs around it",
                  packer == "compact" and {k: v for k, v in got.items() if k != 0x430}
                  == {k: v for k, v in expect(frag, pin_refs).items() if k != 0x430}
                  and got[0x408] == "y" and struct.unpack_from(">I", fix, 0x408) == (offs[2] - REF_BIAS,)
                  and not any(off == 0x408 for _, off, _, _ in r), got)
            check("pinned: a longer text in a pinned slot is refused",
                  refused(lambda: compile_(fix, {**frag, 2: "longer text"}), "TEXT_TOO_LONG") is True)
            # String1 without a table pointer: it stays, its tail joins the next run
            un_refs = {k: v for k, v in base_refs.items() if v != offs[1]}
            fix = table(un_refs)
            unr = {0: "x", 1: "ab", 2: "y", 3: "Metin 3", 4: "Uzun metin uzun"}   # String4 needs String1's tail
            r, moved, packer = compile_(fix, unr)
            data = bytearray(fix)
            for _, off, b, _ in r:
                data[off:off + len(b)] = b
            check("unreferenced: the string stays at its offset and gives its tail",
                  packer == "compact" and data[offs[1]:offs[1] + 3] == b"ab\0"
                  and seen(fix, r, un_refs) == expect(unr, un_refs)
                  and struct.unpack_from(">I", data, 0x408)[0] + REF_BIAS == offs[1] + 4, seen(fix, r, un_refs))
            check("unreferenced: a longer text without a table pointer is refused",
                  refused(lambda: compile_(fix, {**unr, 1: "a longer one"}), "TEXT_TOO_LONG") is True)
            fix = table(base_refs)
            # M38 review: a packer result whose ranges overlap is refused whole (never applied in part)
            real = globals()["pack_compact"]
            try:
                globals()["pack_compact"] = lambda p, items, refs: (
                    [(p, offs[0], b"x" * 12, "text@a"), (p, offs[1], b"y" * 8, "text@b")], True)
                check("overlap: overlapping ranges from a packer are refused, not applied in part",
                      refused(lambda: compile_(fix, frag, "compact"), "TEXT_OVERLAP") is True)
            finally:
                globals()["pack_compact"] = real
            try:
                compile_(fix, {i: f"Daha uzun {i}" for i in range(5)})
                check("too long: refused with the overage", False)
            except Refusal as x:
                check("too long: refused, naming a string, the largest free space and the overage",
                      x.code == "TEXT_TOO_LONG" and "the string at" in x.detail and "largest free space" in x.detail
                      and "by at least" in x.detail, x.detail)
    finally:
        os.environ.pop(TEXT_PACKER_ENV, None)
        if saved is not None:
            os.environ[TEXT_PACKER_ENV] = saved


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["validate", "import", "list", "enable", "disable", "remove", "move", "plan",
                                    "text-find", "texture-info", "texture-export", "selftest"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--home")
    ap.add_argument("--mods-root")
    ap.add_argument("--cache")
    ap.add_argument("--game-dir")
    ap.add_argument("--out")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--enable", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--rows", action="store_true", help="tab-separated rows for the Settings launcher")
    ap.add_argument("--text-packer", choices=TEXT_PACKERS,
                    help="M38: auto (default; compacts only when the M34 packer refuses), m34 or compact")
    a = ap.parse_args()
    if a.text_packer:
        os.environ[TEXT_PACKER_ENV] = a.text_packer
    if a.cmd == "selftest":
        return selftest()
    paths = resolve_paths(a)
    need = {"validate": 1, "import": 1, "list": 0, "enable": 1, "disable": 1, "remove": 1, "move": 2, "plan": 0,
            "text-find": 1, "texture-info": 1, "texture-export": 2}[a.cmd]
    try:
        if len(a.args) != need:
            raise Refusal("USAGE", f"{a.cmd} takes {need} argument(s)")
        if a.cmd == "validate":
            r = cmd_validate(paths, Path(a.args[0]))
        elif a.cmd == "import":
            r = cmd_import(paths, Path(a.args[0]), a.replace, a.enable)
        elif a.cmd == "list":
            r = resolve_all(paths)
        elif a.cmd in ("enable", "disable"):
            r = cmd_set(paths, a.args[0], a.cmd == "enable")
        elif a.cmd == "remove":
            r = cmd_remove(paths, a.args[0])
        elif a.cmd == "move":
            if a.args[1] not in ("up", "down", "top", "bottom"):
                raise Refusal("USAGE", "move ID up|down|top|bottom")
            r = cmd_move(paths, a.args[0], a.args[1])
        elif a.cmd == "plan":
            r = resolve_all(paths, write_plan=a.out or paths["cache"])
        elif a.cmd == "text-find":
            r = cmd_text_find(paths, a.args[0])
        elif a.cmd == "texture-info":
            r = cmd_texture_info(paths, a.args[0])
        else:
            r = cmd_texture_export(paths, a.args[0], Path(a.args[1]))
        r = {"result": "ok", **r}
        code = 0
    except Refusal as x:
        r = {"result": "refused", "code": x.code, "detail": x.detail, "advice": ADVICE.get(x.code, "")}
        code = 2
    except (OSError, zipfile.BadZipFile, zlib.error, UnicodeError, ValueError, EOFError, struct.error) as x:
        # M33 review: a damaged archive, a locked or unreadable file is a refusal with a reason, never a traceback.
        r = {"result": "refused", "code": "UNREADABLE", "detail": f"{type(x).__name__}: {x}",
             "advice": ADVICE["UNREADABLE"]}
        code = 2
    if a.rows:
        # M33: tab-separated rows for the Settings launcher (tools/launcher/r3hd_launcher.cpp), UTF-8.
        def cell(v):
            return re.sub(r"[\t\r\n]+", " ", str(v if v is not None else "")).strip()
        lines = ["R3HD_MODS_ROWS\t1", "\t".join(["RESULT", r["result"], cell(r.get("code")),
                                                  cell(r.get("detail") if code else r.get("id", "")),
                                                  cell(r.get("advice"))])]
        for m in r.get("mods", []) if code == 0 else []:
            lines.append("\t".join(["MOD", cell(m["id"]), "1" if m["enabled"] else "0", cell(m["state"]), cell(m["name"]),
                                    cell(m["version"]), cell(m.get("code")), cell(m.get("detail")),
                                    cell(m.get("description")), str(m.get("ranges", 0)), str(len(m.get("shadowed", [])))]))
        lines.append("END")
        sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))
    elif a.json:
        print(json.dumps(r, indent=1, default=str))
    else:
        print(json.dumps(r, indent=1, default=str, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
