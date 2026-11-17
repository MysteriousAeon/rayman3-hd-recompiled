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
  script-constant (D-223, development prototype) one int or real constant node of a behaviour script in a level file,
            identified by level, behaviour name, script and node index, the SHA-256 of the script's nodes and the
            declared kind; written in place (4 bytes), never a relocated or load-rewritten word
  macro-constant (D-226, development prototype) the same in one macro of a level's AI model, identified by the model's
            first normal behaviour name and the macro index; refused for fix.lvl, a macro filled at load, a macro
            whose two scripts differ, and a macro referenced from anything but its own model's scripts
  designer-default (D-227, development prototype) the initial value of one bool / byte / int / real designer variable
            of one actor instance of a level's AI model (model key, instance index in file order, variable number,
            the SHA-256 of the instance's initial buffer); written in place in the instance's initial and current
            buffers; refused for fix.lvl, other types, relocated words and buffers referenced from other data
  actor-position (D-228, development prototype) the initial translation (x, y, z) of one actor of a level's AI model
            (model key, actor index in file order, SHA-256 of its matrix); written in its matrix and the matrix's
            byte-swapped snapshot; rotation and scale unchanged; refused for fix.lvl, identity matrices and matrices
            without exactly one snapshot or referenced from other data
  waypoint-position (D-231, development prototype) x, y, z of one waypoint of a graph that one actor instance's
            designer variable owns (model key, instance, variable, node index, SHA-256 of the waypoint); radius and
            flags unchanged; refused for fix.lvl, shared graphs or waypoints and anything pointing into them
  insert-passive-lum (D-251, G6-P1, DEVELOPMENT ONLY: refused unless R3HD_DEV_STRUCTURAL_TX names the level) one
            additional instance of intro_10's verified red lum (instance 6 of NIN_m_Lums_Int10), placed within 1 unit
            of an approved position; exact .lvl / .ptr / transit.lvl SHA-256 required; compiled into one level
            transaction of version 2 (appended actor, personal type, SO and backup records, a rebuilt pointer table,
            transit's actor count) that only a development runtime accepts; one per mod, never with insert-graph-node
  insert-scripted-frog (D-254, G6-P2, DEVELOPMENT ONLY: refused unless R3HD_DEV_STRUCTURAL_TX names the level) one
            additional, independent instance of intro_10's verified looping sound generator (instance 2 of
            NIK_mGenSound, MAN_mGenSound_Frog) that runs the game's own script; placement "at_source" and period_ms
            500 or 2000 (its designer variable 5) only; exact .lvl / .ptr / transit.lvl SHA-256 required; one version-2
            level transaction (own Brain / Mind / Intelligence / designer buffers, personal type, SO / backup /
            always-active records, an extended sound-event resolve table, transit's actor count); one per mod, never
            with another structural operation
  insert-fairy-on-graph (D-256, G6-P3, DEVELOPMENT ONLY: refused unless R3HD_DEV_STRUCTURAL_TX names the level) one
            additional fairy light in intro_20 (a copy of instance 2 of NIN_m_FairyLight) whose designer variable 2
            references an EXISTING waypoint graph: follow_graph_of 0 or 1 = the graph that fairy instance follows
            (the reference keeps its target; the source's own graph is not copied); exact .lvl / .ptr / transit.lvl
            SHA-256 required; one version-2 level transaction; one per mod, never with another structural operation
  insert-gensound-manager (D-257, G6-P4, DEVELOPMENT ONLY: refused unless R3HD_DEV_STRUCTURAL_TX names the level) one
            additional intro_10 sound manager (a copy of MAN_mGenManager_Frog) whose designer variable 0 references an
            EXISTING NIK_mGenSound actor it moves onto its graph: moves_gensound_instance 0 (Forest ambience) or 1
            (SmallRiver); the copy shares the source's model and graph; exact .lvl / .ptr / transit.lvl SHA-256
            required; one version-2 level transaction; one per mod, never with another structural operation
  insert-toad-intro (D-261, G6-P8, DEVELOPMENT ONLY: refused unless R3HD_DEV_STRUCTURAL_TX names the level) one
            additional intro_10 NIN_m_ToadIntro (a copy of instance 1; instance 0's block holds the shared model),
            placement "at_source" and owner "dynamic_world" only (linked after the source); exact .lvl / .ptr /
            transit.lvl SHA-256 required; one version-2 level transaction; one per mod, never with another
            structural operation
  insert-toad-intro-pair (D-262, G6-P9, DEVELOPMENT-ONLY COMPOSITION PILOT: refused unless R3HD_DEV_STRUCTURAL_TX
            names the level) exactly two additional intro_10 NIN_m_ToadIntro (copies of instance 1, "count": 2,
            placement "at_source", owner "dynamic_world"), built by one coordinated construction into ONE version-2
            level transaction; one per mod, never with another structural operation (insert-toad-intro included)
  insert-lum-toad-pair (D-264, G6-P11, DEVELOPMENT-ONLY HETEROGENEOUS PILOT: refused unless R3HD_DEV_STRUCTURAL_TX
            names the level) exactly one additional intro_10 NIN_m_Lums_Int10 (instance 6, lum_placement
            "flight_path") and one NIN_m_ToadIntro (instance 1, toad_placement "at_source"), owner "dynamic_world",
            built by one coordinated construction into ONE version-2 level transaction; one per mod, never with
            another structural operation
  collision-vertex-offset (D-266, G6-P13, DEVELOPMENT ONLY: refused unless R3HD_DEV_STRUCTURAL_TX names the level)
            one named preset of one exact level file (intro_15: spawn-drop-1.50, control-far-drop-1.50 and, D-267,
            spawn-small-drop-0.30 inside every known bound, no octree / box words) lowers the
            three vertices of one static-collision triangle and rewrites the derived face / edge normals, edge
            scalars and octree bounds; no offsets or values come from the manifest; ordinary same-size ranges.
            D-269: spawn-small-drop-0.30-visual also moves the same surface's visual vertices; D-271:
            spawn-multi-surface-v1 lowers two fixed vertex groups (-0.30 / -0.15; 25 collision + 25 visual
            triangles), each moved collision vertex with exactly one visual twin
            D-275: intro_20 start-two-step-v1 (ground under Rayman's start: vertex 0 -0.30, 2 / 4 -0.15)
  insert-fairy-with-terrain (D-276, G6-P20, DEVELOPMENT-ONLY COMPOSITION PILOT: refused unless
            R3HD_DEV_STRUCTURAL_TX names the level) exactly the insert-fairy-on-graph keys plus "terrain_preset":
            "start-two-step-v1" (intro_20 only): the fairy and the terrain preset built from the same original files
            into ONE version-2 level transaction; one per mod, never with another structural operation or terrain edit
  terrain-patch (D-273, G6-P17, DEVELOPMENT ONLY: refused unless R3HD_DEV_STRUCTURAL_TX names the level)
            {"type": "terrain-patch", "patch": <terrain-patch-v1>}: named groups of an allow-listed region's
            vertices (intro_15 spawn-ground-v1) with fixed z displacements, compiled into the verified G6-P16 edit;
            one terrain edit per mod (never with collision-vertex-offset)
  level-patch (D-277, G6-P21, DEVELOPMENT ONLY: refused unless R3HD_DEV_STRUCTURAL_TX names the level)
            {"type": "level-patch", "patch": <level-patch-v1>}: intro_20 only, exactly one terrain component
            (preset start-two-step-v1, or D-278 an embedded terrain-patch-v1 of region start-floor-v1) + exactly one
            fairylight component (follow_graph_of 0 = graph A / 1 = graph B), compiled by
            insert-fairy-with-terrain into one version-2 transaction; the patch id must be the mod id
  insert-graph-node (D-243, G5-P1, DEVELOPMENT ONLY: refused unless R3HD_DEV_STRUCTURAL_TX names the level) one new
            node inserted after an allow-listed node of an allow-listed graph (intro_10's flight graph, after node 13),
            exact .lvl / .ptr SHA-256 required; compiled into one level transaction (`level-tx`, appended objects and
            a rebuilt pointer table) that only a development runtime accepts; one structural mod per level, never
            shadowed: an overlapping mod refuses the lower-priority side whole. G5-P5 (D-249): one mod may carry two
            on intro_10's flight graph (after nodes 13 and 22), compiled together into one transaction in original
            node order; any invalid one refuses the mod whole
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
  r3hd_mods.py script-info LEVEL [--behavior TEXT]      authoring (D-223): behaviours, script hashes, int / real constants
  r3hd_mods.py script-info LEVEL --model TEXT           authoring (D-226 - D-231): macros, instances, actors, waypoints
  r3hd_mods.py terrain-patch PATCH.json [--out DIR]    development (D-273): compile a terrain-patch-v1 file, list its
                                                        ranges; --out writes a private mod folder for import
  r3hd_mods.py level-patch PATCH.json [--out DIR]      development (D-277): compile a level-patch-v1 file (intro_20
                                                        terrain + FairyLight); --out writes a private mod folder;
                                                        --check (G6-P24) validates and previews only, writes nothing;
                                                        text report by default, the structured report with --json
                                                        (guide: docs/development/LEVEL_PATCH_AUTHORING.md)
  r3hd_mods.py selftest                                synthetic fixtures only
Common: --home H (else R3HD_HOME, else the repository layout), --mods-root DIR, --cache DIR, --game-dir DIR, --json,
--text-packer auto|m34|compact.
Exit 0 ok, 2 refused (reason code), 1 internal error. Standard library only (the installed Python has no extensions).
"""
import argparse
import datetime
import hashlib
import json
import math
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
        elif o.get("type") == "script-constant":
            parse_script_constant(o, where)
        elif o.get("type") == "macro-constant":
            parse_macro_constant(o, where)
        elif o.get("type") == "designer-default":
            parse_designer_default(o, where)
        elif o.get("type") == "actor-position":
            parse_actor_position(o, where)
        elif o.get("type") == "waypoint-position":
            parse_waypoint_position(o, where)
        elif o.get("type") == "insert-graph-node":   # G5-P1 (D-243): development-only, refused unless enabled
            parse_insert_graph_node(o, where)
        elif o.get("type") == "insert-passive-lum":   # G6-P1 (D-251): development-only, refused unless enabled
            parse_insert_passive_lum(o, where)
        elif o.get("type") == "insert-scripted-frog":   # G6-P2 (D-254): development-only, refused unless enabled
            parse_insert_scripted_frog(o, where)
        elif o.get("type") == "insert-fairy-with-terrain":   # G6-P20 (D-276): development-only composition pilot
            parse_insert_fairy_with_terrain(o, where)
        elif o.get("type") == "insert-fairy-on-graph":   # G6-P3 (D-256): development-only, refused unless enabled
            parse_insert_fairy_on_graph(o, where)
        elif o.get("type") == "insert-gensound-manager":   # G6-P4 (D-257): development-only, refused unless enabled
            parse_insert_gensound_manager(o, where)
        elif o.get("type") == "insert-toad-intro":   # G6-P8 (D-261): development-only, refused unless enabled
            parse_insert_toad_intro(o, where)
        elif o.get("type") == "insert-toad-intro-pair":   # G6-P9 (D-262): development-only pilot, refused unless enabled
            parse_insert_toad_intro_pair(o, where)
        elif o.get("type") == "insert-lum-toad-pair":   # G6-P11 (D-264): development-only pilot, refused unless enabled
            parse_insert_lum_toad_pair(o, where)
        elif o.get("type") == "collision-vertex-offset":   # G6-P13 (D-266): development-only, refused unless enabled
            parse_collision_vertex_offset(o, where)
        elif o.get("type") == "terrain-patch":   # G6-P17 (D-273): development-only, refused unless enabled
            parse_terrain_override(o, where)
        elif o.get("type") == "level-patch":   # G6-P21 (D-277): development-only declarative composition
            parse_level_patch_override(o, where)
        else:
            raise Refusal("UNSUPPORTED", f"{where}: type {o.get('type')!r} (supported: texture, text, glyph, subtitle, "
                                         "script-constant, macro-constant, designer-default, actor-position, "
                                         "waypoint-position)")
    chars = [o["char"] for o in ov if o["type"] == "glyph"]
    if len(chars) != len(set(chars)):
        raise Refusal("BAD_MANIFEST", "the same glyph twice")
    texts = [o["offset"] for o in ov if o["type"] == "text"]
    if len(texts) != len(set(texts)):
        raise Refusal("BAD_MANIFEST", "the same text offset twice")
    subs = [o["id"] for o in ov if o["type"] == "subtitle"]
    if len(subs) != len(set(subs)):
        raise Refusal("BAD_MANIFEST", "the same subtitle id twice")
    nodes = [(o["level"], o["behavior"], o["script"], o["node"]) for o in ov if o["type"] == "script-constant"]
    if len(nodes) != len(set(nodes)):
        raise Refusal("BAD_MANIFEST", "the same script node twice")
    mnodes = [(o["level"], o["model"], o["macro"], o["node"]) for o in ov if o["type"] == "macro-constant"]
    if len(mnodes) != len(set(mnodes)):
        raise Refusal("BAD_MANIFEST", "the same macro node twice")
    dvars = [(o["level"], o["model"], o["instance"], o["variable"]) for o in ov if o["type"] == "designer-default"]
    if len(dvars) != len(set(dvars)):
        raise Refusal("BAD_MANIFEST", "the same designer variable twice")
    wpts = [(o["level"], o["model"], o["instance"], o["variable"], o["node"]) for o in ov
            if o["type"] == "waypoint-position"]
    if len(wpts) != len(set(wpts)):
        raise Refusal("BAD_MANIFEST", "the same waypoint twice")
    if sum(1 for o in ov if o["type"] == "collision-vertex-offset") > 1:   # G6-P13: one preset per mod
        raise Refusal("BAD_MANIFEST", "at most one collision-vertex-offset per mod (one preset)")
    if sum(1 for o in ov if o["type"] in ("collision-vertex-offset", "terrain-patch")) > 1:   # G6-P17: no merging
        raise Refusal("BAD_MANIFEST", "at most one terrain edit (terrain-patch or collision-vertex-offset) per mod")
    actors = [(o["level"], o["model"], o["instance"]) for o in ov if o["type"] == "actor-position"]
    if len(actors) != len(set(actors)):
        raise Refusal("BAD_MANIFEST", "the same actor twice")
    igs = [o for o in ov if o["type"] == "insert-graph-node"]
    if len(igs) > 1:   # G5-P1: one structural operation per mod; G5-P5 (D-249): up to STRUCT_MAX_OPS on one graph
        key = lambda o: (o["level"], o["model"], o["instance"], o["variable"], o["lvl_sha256"], o["ptr_sha256"])  # noqa
        if len({key(o) for o in igs}) != 1:
            raise Refusal("BAD_MANIFEST", "the structural operations (insert-graph-node) of one mod must all change "
                                          "the same graph of the same level files")
        if len(igs) > STRUCT_MAX_OPS.get(igs[0]["level"], 1):
            raise Refusal("BAD_MANIFEST", f"at most {STRUCT_MAX_OPS.get(igs[0]['level'], 1)} structural operation(s) "
                                          f"(insert-graph-node) per mod for {igs[0]['level']}")
        if len({o["after_node"] for o in igs}) != len(igs):
            raise Refusal("BAD_MANIFEST", "the same insertion site (after_node) twice")
    lums = [o for o in ov if o["type"] == "insert-passive-lum"]
    if len(lums) > 1 or (lums and igs):   # G6-P1 (D-251): one structural transaction per mod, one new actor
        raise Refusal("BAD_MANIFEST", "a mod may carry one insert-passive-lum, and not together with insert-graph-node")
    frogs = [o for o in ov if o["type"] == "insert-scripted-frog"]
    if len(frogs) > 1 or (frogs and (igs or lums)):   # G6-P2 (D-254): one new scripted actor, no composition
        raise Refusal("BAD_MANIFEST", "a mod may carry one insert-scripted-frog, and no other structural operation")
    fairies = [o for o in ov if o["type"] == "insert-fairy-on-graph"]
    if len(fairies) > 1 or (fairies and (igs or lums or frogs)):   # G6-P3 (D-256): one new actor, no composition
        raise Refusal("BAD_MANIFEST", "a mod may carry one insert-fairy-on-graph, and no other structural operation")
    mgrs = [o for o in ov if o["type"] == "insert-gensound-manager"]
    if len(mgrs) > 1 or (mgrs and (igs or lums or frogs or fairies)):   # G6-P4 (D-257): one new actor, no composition
        raise Refusal("BAD_MANIFEST", "a mod may carry one insert-gensound-manager, and no other structural operation")
    toads = [o for o in ov if o["type"] == "insert-toad-intro"]
    if len(toads) > 1 or (toads and (igs or lums or frogs or fairies or mgrs)):   # G6-P8 (D-261): one new actor
        raise Refusal("BAD_MANIFEST", "a mod may carry one insert-toad-intro, and no other structural operation")
    pairs = [o for o in ov if o["type"] == "insert-toad-intro-pair"]
    if len(pairs) > 1 or (pairs and (igs or lums or frogs or fairies or mgrs or toads)):   # G6-P9 (D-262): one pair
        raise Refusal("BAD_MANIFEST", "a mod may carry one insert-toad-intro-pair, and no other structural operation")
    lts = [o for o in ov if o["type"] == "insert-lum-toad-pair"]
    if len(lts) > 1 or (lts and (igs or lums or frogs or fairies or mgrs or toads or pairs)):   # G6-P11 (D-264)
        raise Refusal("BAD_MANIFEST", "a mod may carry one insert-lum-toad-pair, and no other structural operation")
    terrain = [o for o in ov if o["type"] in ("terrain-patch", "collision-vertex-offset")]
    if terrain and (igs or lums or frogs or fairies or mgrs or toads or pairs or lts):   # G6-P18 (D-274): fail closed
        raise Refusal("BAD_MANIFEST", "a terrain edit (terrain-patch / collision-vertex-offset) and a structural "
                                      "operation cannot share a mod: no level supports both (G6-P18)")
    mixes = [o for o in ov if o["type"] in ("insert-fairy-with-terrain", "level-patch")]
    if mixes and (len(mixes) > 1 or terrain or igs or lums or frogs or fairies or mgrs or toads or pairs or lts):
        raise Refusal("BAD_MANIFEST", "a mod may carry one insert-fairy-with-terrain or level-patch, and no other "
                                      "structural operation or terrain edit (G6-P20 / G6-P21)")
    for o in mixes:   # G6-P21: the declared owner is the transaction's owner
        if o["type"] == "level-patch" and o["patch"]["id"] != m["id"]:
            raise Refusal("BAD_MANIFEST", f"level-patch: the patch's id {o['patch']['id']!r} is not the mod's id")
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
# Script constants (D-223, E-455; development prototype): typed same-size edits of integer and real constants in the
# behaviour scripts of a level file. File domain, big-endian (RE_NOTES "M5 completion" and "Script constants"):
#   <level>.ptr  u32 count, then {i32 target file, u32 slot}; the slot's offset in the .lvl is slot + 4, a pointer's
#                target is its value + 4 (file ids: 0 fix, 1 the level, 2 transit)
#   behaviour list {u32 -> entries, u32 count}; behaviour = 0x100-byte name, u32 -> script array, u32 schedule,
#                u8 script count (0x10C bytes); script array = u32 -> node array per script
#   node         u32 parameter, u16, u8 indent, u8 type; a script ends before the next node of indent 0
# Only types 0x0C (int32) and 0x0D (float32) are edited: their parameter is never a relocated word and reaches the
# running game unchanged (E-455). Every other type, and any word the .ptr lists, is refused; so is type 0x1F, which
# the loader rewrites. The guest still reads the person's own file through the ordinary plan range.

SCRIPT_CONST_KEYS = {"type", "level", "behavior", "script", "node", "script_sha256", "kind", "value"}
SCRIPT_KINDS = {"int": 0x0C, "real": 0x0D}
SCRIPT_LEVEL_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")
BEHAVIOR_SIZE = 0x10C
SCRIPT_MAX_NODES = 4000
FLOAT32_MAX = 3.4028234663852886e38


def parse_script_constant(o: dict, where: str):
    if set(o) - SCRIPT_CONST_KEYS or set(SCRIPT_CONST_KEYS) - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: a script-constant needs exactly {sorted(SCRIPT_CONST_KEYS)}")
    if not isinstance(o["level"], str) or not SCRIPT_LEVEL_RE.match(o["level"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'level' must be a level folder name such as intro_10, or fix")
    if not isinstance(o["behavior"], str) or not 3 <= len(o["behavior"]) < 0x100 \
            or not all(32 <= ord(c) < 127 for c in o["behavior"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'behavior' must be the behaviour's full name from script-info")
    for key in ("script", "node"):
        if not isinstance(o[key], int) or isinstance(o[key], bool) or not 0 <= o[key] < SCRIPT_MAX_NODES:
            raise Refusal("BAD_MANIFEST", f"{where}: '{key}' must be an index from script-info")
    if not isinstance(o["script_sha256"], str) or not re.match(r"^[0-9a-f]{64}$", o["script_sha256"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'script_sha256' must be the 64-digit SHA-256 from script-info")
    if o["kind"] not in SCRIPT_KINDS:
        raise Refusal("UNSUPPORTED", f"{where}: 'kind' must be int or real (other script nodes cannot be changed)")
    script_value_bytes(o, where)


MACRO_CONST_KEYS = {"type", "level", "model", "macro", "node", "script_sha256", "kind", "value"}


def parse_macro_constant(o: dict, where: str):
    """D-226: like a script-constant, with the model (its first normal behaviour's full name) and macro index."""
    if set(o) - MACRO_CONST_KEYS or MACRO_CONST_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: a macro-constant needs exactly {sorted(MACRO_CONST_KEYS)}")
    if o["level"] == "fix":
        raise Refusal("UNSUPPORTED", f"{where}: macros of fix.lvl cannot be changed (any level may call them)")
    parse_script_constant({**{k: v for k, v in o.items() if k not in ("model", "macro")}, "type": "script-constant",
                           "behavior": o["model"], "script": o["macro"]}, where)


def script_value_bytes(o: dict, where: str) -> bytes:
    v = o["value"]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise Refusal("BAD_MANIFEST", f"{where}: 'value' must be a number")
    if o["kind"] == "int":
        if not isinstance(v, int) or not -(1 << 31) <= v < (1 << 31):
            raise Refusal("BAD_MANIFEST", f"{where}: an int 'value' must be a whole number from -2147483648 to 2147483647")
        return struct.pack(">i", v)
    if not (abs(v) <= FLOAT32_MAX):   # also refuses NaN and infinities
        raise Refusal("BAD_MANIFEST", f"{where}: a real 'value' must be a finite 32-bit float")
    return struct.pack(">f", v)


def script_level_files(game: Path, level: str):
    g = game / "GAMEDATAbin"
    if level == "fix":
        return g / "fix.lvl", g / "fix.ptr", 0
    return g / level / f"{level}.lvl", g / level / f"{level}.ptr", 1


def read_script_index(game: Path, level: str) -> dict:
    """The behaviours of one level file: {"lvl", "data", "slots", "behaviours": {name: [(node array offset or None,
    [(parameter, indent, type)] or None) per script] or None when the name is not unique}}."""
    lvl_p, ptr_p, me = script_level_files(game, level)
    if not lvl_p.is_file() or not ptr_p.is_file():
        raise Refusal("TARGET_MISSING", f"level {level}: {lvl_p.name} / {ptr_p.name} not found")
    lvl, ptr = lvl_p.read_bytes(), ptr_p.read_bytes()
    n = struct.unpack_from(">I", ptr, 0)[0] if len(ptr) >= 4 else None
    if n is None or 4 + 8 * n > len(ptr):
        raise Refusal("TARGET_CHANGED", f"{ptr_p.name} is not a pointer table")
    slots = {}
    for i in range(n):
        f, loc = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        slots[loc + 4] = f

    def target(o):   # file offset an own-file pointer at o leads to, else None
        if slots.get(o) != me or o + 4 > len(lvl):
            return None
        t = struct.unpack_from(">I", lvl, o)[0] + 4
        return t if t < len(lvl) else None

    def name(r):
        if r + BEHAVIOR_SIZE > len(lvl):
            return None
        b = lvl[r:r + 0x100].split(b"\0", 1)[0]
        return b.decode("ascii") if len(b) >= 3 and b":" in b and all(32 <= c < 127 for c in b) else None

    def walk(na):   # [(parameter, indent, type)] up to the next indent 0, or None past the file / the limit
        if na is None:
            return None
        nodes = []
        for k in range(SCRIPT_MAX_NODES):
            o = na + 8 * k
            if o + 8 > len(lvl):
                return None
            p, _, ind, kind = struct.unpack_from(">IHBB", lvl, o)
            if ind == 0 and k:
                return nodes
            nodes.append((p, ind, kind))
        return None

    records, headers = {}, {}
    for so in sorted(slots):
        base = target(so)
        if base is None or so + 8 > len(lvl):
            continue
        count = struct.unpack_from(">I", lvl, so + 4)[0]
        if not 0 < count < 512:
            continue
        names = [name(base + i * BEHAVIOR_SIZE) for i in range(count)]
        if all(names):
            headers[so] = names
            for i, nm in enumerate(names):
                records.setdefault(nm, set()).add(base + i * BEHAVIOR_SIZE)
    behaviours = {}
    for nm, recs in records.items():
        if len(recs) != 1:
            behaviours[nm] = None
            continue
        r = next(iter(recs))
        count = lvl[r + 0x108]
        arr = target(r + 0x100) if count else None
        scripts = []
        for j in range(count if arr is not None else 0):
            na = target(arr + 4 * j)
            scripts.append((na, walk(na)))
        behaviours[nm] = scripts
    ix = {"lvl": lvl_p, "data": lvl, "slots": slots, "behaviours": behaviours,
          "headers": headers}   # G6-P7 (D-260): behaviour-list headers {header offset: names}, read-only consumers
    ix["models"], ix["macro_refs"] = read_models(lvl_p, lvl, slots, me, target, walk, headers, behaviours, level)
    ix["defaults"] = read_designer_defaults(lvl_p, lvl, slots, me, target, headers, level)
    ix["placements"] = read_placements(lvl_p, lvl, slots, me, target, headers, level)
    ix["graphs"] = read_graphs(lvl_p, lvl, slots, target, ix["defaults"], level)
    return ix


def model_records(lvl, slots, target, headers) -> dict:
    """{model key (first normal behaviour's full name): [AI model record offsets]}: a record whose +0 points to a
    behaviour list header and whose -4 does not (that would be the reflex list at +4)."""
    found = {}
    for m in sorted(slots):
        h = target(m)
        if h in headers and target(m - 4) not in headers and m + 0x10 <= len(lvl):
            found.setdefault(headers[h][0], []).append(m)
    return found


def read_models(lvl_p, lvl, slots, me, target, walk, headers, behaviours, level) -> tuple:
    """D-226: the AI models of a level file and their macros: {model key (first normal behaviour's name): [macro
    {"nodes_at", "nodes", "entry", "safe": "" or the reason it cannot be changed}] or None when the key is not
    unique}. An AI model is a record whose +0 points to a behaviour list (and whose -4 does not: that would be the
    reflex list at +4); +4 reflex list, +0xC macro list = {-> entries, count in the top byte}; a macro entry =
    {-> script, -> script}, script = {-> nodes} (RE_NOTES "M5 completion", "Script constants")."""
    found = model_records(lvl, slots, target, headers)
    owner = {}   # node offset -> model key: every node of the model's behaviour scripts and macros
    entries = {}   # macro entry offset -> (model key, index)
    list_heads = {}   # macro list header offset -> its first entry (the header's own pointer to it is allowed)
    models = {}
    for key, ms in found.items():
        if len(ms) != 1:
            models[key] = None
            continue
        m = ms[0]
        for lst in (target(m), target(m + 4)):
            for nm in headers.get(lst, ()):
                for na, nodes in behaviours.get(nm) or ():
                    for k in range(len(nodes or ())):
                        owner[na + 8 * k] = key
        macros = []
        ml = target(m + 0xC)
        ents = target(ml) if ml is not None and ml + 8 <= len(lvl) else None
        count = lvl[ml + 4] if ents is not None else 0
        if ents is not None:
            list_heads[ml] = ents
        for i in range(count):
            e = ents + 8 * i
            s0 = target(e) if e + 8 <= len(lvl) else None
            s1 = target(e + 4) if e + 8 <= len(lvl) else None
            na = target(s0) if s0 is not None else None
            nodes = walk(na)
            safe = ""
            if na is None or nodes is None:
                safe = "the macro has no script (a null macro)"
            elif s1 is None or target(s1) != na:
                safe = "the macro's two scripts are not the same node array"
            else:
                for k in range(len(nodes)):
                    owner[na + 8 * k] = key
            entries[e] = (key, i)
            macros.append({"entry": e, "nodes_at": na, "nodes": nodes, "safe": safe})
        models[key] = macros
    # every word that points at a macro entry must be its own list header or a 0x29 node of its own model
    refs = {"list_header": 0, "own_model": 0, "other_model": 0, "other_data": 0, "transit": 0}
    for so, f in slots.items():
        t = target(so)
        if t not in entries:
            continue
        key, i = entries[t]
        if list_heads.get(so) == t:
            refs["list_header"] += 1
            continue
        kind = lvl[so + 7] if so + 8 <= len(lvl) else None
        if kind == 0x29 and owner.get(so) == key:
            refs["own_model"] += 1
            continue
        refs["other_model" if kind == 0x29 and so in owner else "other_data"] += 1
        macro = models[key][i] if models.get(key) else None
        if macro is not None and not macro["safe"]:
            macro["safe"] = ("the macro is also called by another model" if kind == 0x29 and so in owner
                             else "the macro is referenced from data that is not one of its model's scripts")
    # a level's transit file may point into the level (file id 1): such a reference makes the macro unsafe too
    t_lvl, t_ptr = lvl_p.with_name("transit.lvl"), lvl_p.with_name("transit.ptr")
    if level != "fix" and t_lvl.is_file() and t_ptr.is_file():
        tl, tp = t_lvl.read_bytes(), t_ptr.read_bytes()
        n = struct.unpack_from(">I", tp, 0)[0] if len(tp) >= 4 else 0
        for i in range(min(n, (len(tp) - 4) // 8)):
            f, loc = struct.unpack_from(">iI", tp, 4 + 8 * i)
            if f == 1 and loc + 8 <= len(tl):
                t = struct.unpack_from(">I", tl, loc + 4)[0] + 4
                if t in entries and models.get(entries[t][0]):
                    refs["transit"] += 1
                    macro = models[entries[t][0]][entries[t][1]]
                    if not macro["safe"]:
                        macro["safe"] = "the macro is referenced from the level's transit file"
    return models, refs


# D-227: designer-variable initial values of the actor instances a level file holds. An AI model's +8 points to its
# DsgVar record {-> model default buffer, -> info array, buffer length, count in the top byte}; an info entry is 16
# bytes {buffer offset, type, 0, 4}. Each actor instance of the model has a DsgMem {-> the model's +8, -> initial
# buffer, -> current buffer} (RE_NOTES "Designer-variable defaults"); in the file both buffers hold the same bytes
# and differ from the model's defaults, so an edit writes the variable in both instance buffers. Types whose width
# is established from the target (E-460): 0 bool (1 byte), 2 byte (1 byte; values 0..127 since its signedness is
# not established), 5 int, 7 real. Every other type, a word the .ptr lists, and a buffer anything but its own
# DsgMem points at are refused.
DSG_KINDS = {0: ("bool", 1), 2: ("byte", 1), 5: ("int", 4), 7: ("real", 4)}
DSG_MAX_BUFFER = 1 << 16
DESIGNER_DEFAULT_KEYS = {"type", "level", "model", "instance", "variable", "initial_sha256", "kind", "value"}


def read_designer_defaults(lvl_p, lvl, slots, me, target, headers, level) -> dict:
    """{model key: None when the key is not unique, else {"vars": [(buffer offset, type)], "length", "instances":
    [{"dsgmem", "initial", "current", "safe": "" or the reason it cannot be changed}] in file order}}."""
    W = lambda o: struct.unpack_from(">I", lvl, o)[0]   # noqa: E731
    pointers_to = {}
    for so in slots:
        t = target(so)
        if t is not None:
            pointers_to.setdefault(t, []).append(so)
    out, buffers = {}, []
    for key, ms in model_records(lvl, slots, target, headers).items():
        if len(ms) != 1:
            out[key] = None
            continue
        m = ms[0]
        dv = target(m + 8)
        entry = {"vars": [], "length": 0, "instances": []}
        out[key] = entry
        if dv is None or dv + 0x10 > len(lvl):
            continue
        info, length, count = target(dv + 4), W(dv + 8), lvl[dv + 0xC]
        if not count or info is None or info + 16 * count > len(lvl) or not 0 < length < DSG_MAX_BUFFER:
            continue
        entry["length"] = length
        entry["vars"] = [(W(info + 16 * i), W(info + 16 * i + 4)) for i in range(count)]
        for so in sorted(pointers_to.get(m + 8, ())):
            if so + 0xC > len(lvl):
                continue
            ini, cur = target(so + 4), target(so + 8)
            inst = {"dsgmem": so, "initial": ini, "current": cur, "safe": ""}
            if ini is None or cur is None or max(ini, cur) + length > len(lvl):
                inst["safe"] = "the instance's initial or current buffer is not in this file"
            elif abs(ini - cur) < length:
                inst["safe"] = "the instance's initial and current buffers overlap"
            else:
                for b in (ini, cur):
                    inside = [p for t in range(b, b + length) for p in pointers_to.get(t, ())]
                    if inside != [so + (4 if b == ini else 8)]:
                        inst["safe"] = "the instance's buffer is referenced from data other than its own DsgMem"
                buffers += [(ini, ini + length, inst), (cur, cur + length, inst)]
            entry["instances"].append(inst)
    # buffers must not overlap each other (another instance's buffer)
    spans = sorted(buffers, key=lambda s: s[:2])
    reach, last = -1, None
    for b0, b1, inst in spans:
        if b0 < reach:
            for i in (inst, last):
                i["safe"] = i["safe"] or "the instance's buffer overlaps another buffer"
        if b1 > reach:
            reach, last = b1, inst
    # a level's transit file may point into the level (file id 1): a pointer into a buffer makes the instance unsafe
    t_lvl, t_ptr = lvl_p.with_name("transit.lvl"), lvl_p.with_name("transit.ptr")
    if level != "fix" and t_lvl.is_file() and t_ptr.is_file() and spans:
        tl, tp = t_lvl.read_bytes(), t_ptr.read_bytes()
        n = struct.unpack_from(">I", tp, 0)[0] if len(tp) >= 4 else 0
        for i in range(min(n, (len(tp) - 4) // 8)):
            f, loc = struct.unpack_from(">iI", tp, 4 + 8 * i)
            if f == 1 and loc + 8 <= len(tl):
                t = struct.unpack_from(">I", tl, loc + 4)[0] + 4
                for b0, b1, inst in spans:
                    if b0 <= t < b1 and not inst["safe"]:
                        inst["safe"] = "the instance's buffer is referenced from the level's transit file"
    return out


# D-228: initial placement of the actors a level file holds. An actor = SuperObject {+0 type 2, +4 -> Perso, +0x1C
# parent, +0x20 -> matrix}; Perso +4 -> StdGame (+0xC -> back to the SuperObject), +0xC -> Brain -> Mind -> AI model
# (whose key names the actor's model). Matrix (0x54 bytes) = type, 4 x 4 floats column by column from +4 (translation
# x, y, z at +0x34), 4 more floats. Every matrix has exactly one snapshot: a record {-> matrix, -> copy, 0x54, flags}
# whose copy holds the same 0x54 bytes with every 32-bit word byte-swapped (RE_NOTES "Actor placement"). An edit
# writes the translation in the matrix (big-endian) and in its snapshot copy (word-swapped), so both stay equal.
# Type 1 (identity, translation always 0) and matrices without exactly that snapshot are refused.
PLACEMENT_SIZE = 0x54
PLACEMENT_TYPES = {2, 3, 5, 6, 7}
PLACEMENT_KEYS = {"type", "level", "model", "instance", "matrix_sha256", "position"}


def read_placements(lvl_p, lvl, slots, me, target, headers, level) -> dict:
    """{model key: None when the key is not unique, else [{"so", "matrix", "snapshot", "safe": "" or why it cannot
    be changed}] in file order}."""
    W = lambda o: struct.unpack_from(">I", lvl, o)[0]   # noqa: E731
    keys = {}
    for key, ms in model_records(lvl, slots, target, headers).items():
        for m in ms:
            keys[m] = key if len(ms) == 1 else None
    pointers_to = {}
    for so in slots:
        t = target(so)
        if t is not None:
            pointers_to.setdefault(t, []).append(so)
    out, spans = {}, []
    for s in sorted(slots):
        x = s - 4   # a SuperObject's +4 is the Perso pointer
        if x < 0 or x + 0x24 > len(lvl) or W(x) != 2:
            continue
        p = target(s)
        std = target(p + 4) if p is not None and p + 0x10 <= len(lvl) else None
        if std is None or std + 0x10 > len(lvl) or target(std + 0xC) != x:
            continue
        chain = target(p + 0xC)
        for _ in range(2):   # Brain -> Mind -> AI model record
            chain = target(chain) if chain is not None else None
        model = chain
        if model is None or model not in keys:
            continue
        key = keys[model]
        if key is None:
            out[headers[target(model)][0]] = None
            continue
        if key in out and out[key] is None:
            continue
        inst = {"so": x, "matrix": target(x + 0x20), "snapshot": None, "safe": ""}
        out.setdefault(key, []).append(inst)
        m = inst["matrix"]
        if m is None or m + PLACEMENT_SIZE > len(lvl):
            inst["safe"] = "the actor's matrix is not in this file"
            continue
        if W(m) not in PLACEMENT_TYPES:
            inst["safe"] = f"the actor's matrix is type {W(m)} (only types 2, 3, 5, 6, 7 carry a translation)"
            continue
        refs = [r for r in pointers_to.get(m, ()) if r != x + 0x20]
        if len(refs) != 1 or refs[0] + 0xC > len(lvl) or W(refs[0] + 4 + 4) != PLACEMENT_SIZE \
                or target(refs[0] + 4) is None:
            inst["safe"] = "the actor's matrix has no single snapshot or is referenced from other data"
            continue
        c = target(refs[0] + 4)
        inst["snapshot"] = c
        swapped = b"".join(lvl[c + k:c + k + 4][::-1] for k in range(0, PLACEMENT_SIZE, 4))
        if c + PLACEMENT_SIZE > len(lvl) or swapped != lvl[m:m + PLACEMENT_SIZE]:
            inst["safe"] = "the actor's snapshot does not hold the same matrix"
            continue
        if pointers_to.get(c, []) != [refs[0] + 4] or any(
                pointers_to.get(t) for b in (m, c) for t in range(b + 1, b + PLACEMENT_SIZE)) or any(
                w in slots for b in (m, c) for w in range(b - 3, b + PLACEMENT_SIZE)):
            inst["safe"] = "the actor's matrix or snapshot is shared, relocated or referenced from other data"
            continue
        spans += [(m, inst), (c, inst)]
    spans.sort(key=lambda s: s[0])
    for (a, ia), (b, ib) in zip(spans, spans[1:]):
        if b < a + PLACEMENT_SIZE:
            for i in (ia, ib):
                i["safe"] = i["safe"] or "the actor's matrix overlaps another matrix or snapshot"
    t_lvl, t_ptr = lvl_p.with_name("transit.lvl"), lvl_p.with_name("transit.ptr")
    if level != "fix" and t_lvl.is_file() and t_ptr.is_file() and spans:
        tl, tp = t_lvl.read_bytes(), t_ptr.read_bytes()
        n = struct.unpack_from(">I", tp, 0)[0] if len(tp) >= 4 else 0
        for i in range(min(n, (len(tp) - 4) // 8)):
            f, loc = struct.unpack_from(">iI", tp, 4 + 8 * i)
            if f == 1 and loc + 8 <= len(tl):
                t = struct.unpack_from(">I", tl, loc + 4)[0] + 4
                for b, inst in spans:
                    if b <= t < b + PLACEMENT_SIZE and not inst["safe"]:
                        inst["safe"] = "the actor's matrix is referenced from the level's transit file"
    return out


# D-229 (E-462): procedures DB and 219 (node type 0x04) set an actor's position from script data; the intro_15
# bridge whose model calls them did not keep an edited starting position. A model whose own behaviours or macros call
# either is refused (3,448 of 5,362 movable actors).
POSITION_PROCEDURES = {0xDB, 0x219}
SETS_POSITION = ("the model's scripts set the actor's position themselves (procedures DB / 219), so a new starting "
                 "position is not kept (E-462)")


def model_sets_position(ix: dict, key: str) -> bool:
    prefix = "\\".join(key.split("\\")[:2]) + "\\"
    scripts = [nodes for name, ss in ix["behaviours"].items() if name.startswith(prefix) for _, nodes in ss or ()]
    scripts += [mac["nodes"] for mac in ix["models"].get(key) or ()]
    return any(k == 0x04 and p in POSITION_PROCEDURES for nodes in scripts for p, _, k in nodes or ())


def placement_rows(ix: dict, insts: list, key: str = None) -> list:
    rows = []
    sets = key is not None and model_sets_position(ix, key)
    for n, inst in enumerate(insts):
        if inst["safe"] or sets:
            rows.append({"instance": n, "cannot_change": inst["safe"] or SETS_POSITION})
            continue
        m = inst["matrix"]
        rows.append({"instance": n, "matrix_sha256": sha256_bytes(ix["data"][m:m + PLACEMENT_SIZE]),
                     "matrix_type": struct.unpack_from(">I", ix["data"], m)[0],
                     "position": list(struct.unpack_from(">3f", ix["data"], m + 0x34))})
    return rows


def parse_actor_position(o: dict, where: str):
    """D-228: the initial translation of one actor instance of a level's AI model (rotation and scale unchanged)."""
    if set(o) - PLACEMENT_KEYS or PLACEMENT_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: an actor-position needs exactly {sorted(PLACEMENT_KEYS)}")
    if not isinstance(o["level"], str) or not SCRIPT_LEVEL_RE.match(o["level"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'level' must be a level folder name such as intro_10")
    if o["level"] == "fix":
        raise Refusal("UNSUPPORTED", f"{where}: actors of fix.lvl cannot be moved")
    if not isinstance(o["model"], str) or not 3 <= len(o["model"]) < 0x100 \
            or not all(32 <= ord(c) < 127 for c in o["model"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'model' must be the model's full first-behaviour name")
    if not isinstance(o["instance"], int) or isinstance(o["instance"], bool) or not 0 <= o["instance"] < 4096:
        raise Refusal("BAD_MANIFEST", f"{where}: 'instance' must be an index from script-info --model")
    if not isinstance(o["matrix_sha256"], str) or not re.match(r"^[0-9a-f]{64}$", o["matrix_sha256"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'matrix_sha256' must be the 64-digit SHA-256 from script-info")
    placement_bytes(o, where)


def placement_bytes(o: dict, where: str) -> bytes:
    pos = o["position"]
    if not isinstance(pos, list) or len(pos) != 3:
        raise Refusal("BAD_MANIFEST", f"{where}: 'position' must be [x, y, z]")
    return b"".join(script_value_bytes({"kind": "real", "value": v}, where) for v in pos)


def compile_actor_positions(ovs: list, paths, cache=None) -> list:
    out, cache = [], {} if cache is None else cache
    for o in ovs:
        where = f"actor-position {o['level']} {o['model']!r} instance {o['instance']}"
        if o["level"] == "fix":
            raise Refusal("UNSUPPORTED", f"{where}: actors of fix.lvl cannot be moved")
        if o["level"] not in cache:
            cache[o["level"]] = read_script_index(paths["game"], o["level"])
        ix = cache[o["level"]]
        if o["model"] not in ix["placements"]:
            raise Refusal("TARGET_MISSING", f"{where}: no actor of an AI model with this first behaviour in this level")
        insts = ix["placements"][o["model"]]
        if insts is None:
            raise Refusal("TARGET_CHANGED", f"{where}: the model is not unique in this level")
        if o["instance"] >= len(insts):
            raise Refusal("TARGET_MISSING", f"{where}: the model has {len(insts)} actor(s) in this file")
        inst = insts[o["instance"]]
        if inst["safe"]:
            raise Refusal("UNSUPPORTED", f"{where}: {inst['safe']}")
        if model_sets_position(ix, o["model"]):
            raise Refusal("UNSUPPORTED", f"{where}: {SETS_POSITION}")
        m, c = inst["matrix"], inst["snapshot"]
        if sha256_bytes(ix["data"][m:m + PLACEMENT_SIZE]) != o["matrix_sha256"]:
            raise Refusal("TARGET_CHANGED", f"{where}: the actor's matrix is not the one this mod was made for")
        data = placement_bytes(o, where)
        swapped = b"".join(data[k:k + 4][::-1] for k in range(0, 12, 4))
        tag = f"{o['level']}:{o['model']}#{o['instance']}"
        out += [(ix["lvl"], m + 0x34, data, tag + " matrix"), (ix["lvl"], c + 0x34, swapped, tag + " snapshot")]
    return out


# D-231: waypoint positions of a level graph owned by one actor. A designer variable of type 20 (graph) of an actor
# instance points to a graph {+0 -> first node, +4 -> last node, +8 node count}; node (0x1C) {+0 next, +4 previous,
# +8 -> graph, +0xC -> waypoint, +0x18 -> arc list}; waypoint (0x14) {x, y, z, radius, flags}, big-endian floats
# (RE_NOTES "Waypoint graphs"). An edit writes x, y, z (12 bytes) of one waypoint; radius and flags stay. Refused:
# fix, a graph referenced by anything but its own nodes and its owner's two buffers (shared with other actors or
# data), a waypoint referenced by anything but its node, a relocated word or a pointer inside it, transit references.
GRAPH_TYPE = 20
WAYPOINT_SIZE = 0x14
WAYPOINT_KEYS = {"type", "level", "model", "instance", "variable", "node", "waypoint_sha256", "position"}


def read_graphs(lvl_p, lvl, slots, target, defaults, level) -> dict:
    """{(model key, instance, variable): {"graph", "nodes": [(node, waypoint)], "safe": "" or why the graph's
    waypoints cannot change, "wsafe": {node index: why that waypoint cannot change}}}."""
    W = lambda o: struct.unpack_from(">I", lvl, o)[0]   # noqa: E731
    pointers_to = {}
    for so in slots:
        t = target(so)
        if t is not None:
            pointers_to.setdefault(t, []).append(so)
    out = {}
    for key, e in defaults.items():
        for n, inst in enumerate((e or {}).get("instances", ())):
            if inst["initial"] is None or inst["current"] is None:
                continue
            for var, (off, t) in enumerate(e["vars"]):
                if t != GRAPH_TYPE or off + 4 > e["length"]:
                    continue
                g = target(inst["initial"] + off)
                if g is None:
                    continue
                entry = {"graph": g, "nodes": [], "safe": "", "wsafe": {}}
                out[(key, n, var)] = entry
                if target(inst["current"] + off) != g:
                    entry["safe"] = "the instance's initial and current buffers name different graphs"
                    continue
                count = W(g + 8) if g + 0xC <= len(lvl) else 0
                node, prev, seen = target(g), None, set()
                while node is not None and node not in seen and len(seen) < 4096 and node + 0x1C <= len(lvl):
                    seen.add(node)
                    if target(node + 8) != g or target(node + 4) != prev:
                        break
                    entry["nodes"].append((node, target(node + 0xC)))
                    prev, node = node, target(node)
                if not 0 < count == len(entry["nodes"]) or target(g + 4) != prev:
                    entry["safe"] = "the graph's node list is not the one this decoder understands"
                    continue
                allowed = {nd + 8 for nd, _ in entry["nodes"]} | {inst["initial"] + off, inst["current"] + off}
                if set(pointers_to.get(g, ())) != allowed or len(pointers_to.get(g, ())) != len(allowed):
                    entry["safe"] = "the graph is referenced by another actor or other data"
                    continue
                for i, (nd, w) in enumerate(entry["nodes"]):
                    why = ""
                    if w is None or w + WAYPOINT_SIZE > len(lvl):
                        why = "the node has no waypoint in this file"
                    elif pointers_to.get(w, []) != [nd + 0xC]:
                        why = "the waypoint is shared with another node or referenced from other data"
                    elif any(s in slots for s in range(w - 3, w + WAYPOINT_SIZE)) or any(
                            pointers_to.get(x) for x in range(w + 1, w + WAYPOINT_SIZE)):
                        why = "the waypoint holds or is pointed into by a relocated word"
                    if why:
                        entry["wsafe"][i] = why
    t_lvl, t_ptr = lvl_p.with_name("transit.lvl"), lvl_p.with_name("transit.ptr")
    if level != "fix" and t_lvl.is_file() and t_ptr.is_file() and out:
        tl, tp = t_lvl.read_bytes(), t_ptr.read_bytes()
        n = struct.unpack_from(">I", tp, 0)[0] if len(tp) >= 4 else 0
        inside = {}
        for entry in out.values():
            inside[entry["graph"]] = entry
            for nd, w in entry["nodes"]:
                for b, size in ((nd, 0x1C), (w, WAYPOINT_SIZE)):
                    if b is not None:
                        for x in range(b, b + size):
                            inside.setdefault(x, entry)
        for i in range(min(n, (len(tp) - 4) // 8)):
            f, loc = struct.unpack_from(">iI", tp, 4 + 8 * i)
            if f == 1 and loc + 8 <= len(tl):
                t = struct.unpack_from(">I", tl, loc + 4)[0] + 4
                if t in inside and not inside[t]["safe"]:
                    inside[t]["safe"] = "the graph is referenced from the level's transit file"
    return out


def waypoint_rows(ix: dict, key: str) -> list:
    rows = []
    for (k, n, var), entry in sorted(ix["graphs"].items()):
        if k != key:
            continue
        if entry["safe"]:
            rows.append({"instance": n, "variable": var, "cannot_change": entry["safe"]})
            continue
        nodes = []
        for i, (nd, w) in enumerate(entry["nodes"]):
            if i in entry["wsafe"]:
                nodes.append({"node": i, "cannot_change": entry["wsafe"][i]})
                continue
            d = ix["data"][w:w + WAYPOINT_SIZE]
            nodes.append({"node": i, "waypoint_sha256": sha256_bytes(d), "position": list(struct.unpack(">3f", d[:12])),
                          "radius": struct.unpack(">f", d[12:16])[0]})
        rows.append({"instance": n, "variable": var, "nodes": nodes})
    return rows


def parse_waypoint_position(o: dict, where: str):
    """D-231: x, y, z of one waypoint of a graph owned by one actor instance (radius and flags unchanged)."""
    if set(o) - WAYPOINT_KEYS or WAYPOINT_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: a waypoint-position needs exactly {sorted(WAYPOINT_KEYS)}")
    if not isinstance(o["level"], str) or not SCRIPT_LEVEL_RE.match(o["level"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'level' must be a level folder name such as intro_10")
    if o["level"] == "fix":
        raise Refusal("UNSUPPORTED", f"{where}: waypoints of fix.lvl cannot be moved")
    if not isinstance(o["model"], str) or not 3 <= len(o["model"]) < 0x100 \
            or not all(32 <= ord(c) < 127 for c in o["model"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'model' must be the model's full first-behaviour name")
    for k in ("instance", "variable", "node"):
        if not isinstance(o[k], int) or isinstance(o[k], bool) or not 0 <= o[k] < 4096:
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be an index from script-info --model")
    if not isinstance(o["waypoint_sha256"], str) or not re.match(r"^[0-9a-f]{64}$", o["waypoint_sha256"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'waypoint_sha256' must be the 64-digit SHA-256 from script-info")
    placement_bytes(o, where)


def compile_waypoint_positions(ovs: list, paths, cache=None) -> list:
    out, cache = [], {} if cache is None else cache
    for o in ovs:
        where = (f"waypoint-position {o['level']} {o['model']!r} instance {o['instance']} variable {o['variable']} "
                 f"node {o['node']}")
        if o["level"] == "fix":
            raise Refusal("UNSUPPORTED", f"{where}: waypoints of fix.lvl cannot be moved")
        if o["level"] not in cache:
            cache[o["level"]] = read_script_index(paths["game"], o["level"])
        ix = cache[o["level"]]
        if ix["defaults"].get(o["model"], 0) is None:
            raise Refusal("TARGET_CHANGED", f"{where}: the model is not unique in this level")
        entry = ix["graphs"].get((o["model"], o["instance"], o["variable"]))
        if entry is None:
            raise Refusal("TARGET_MISSING", f"{where}: no graph in this designer variable of this actor")
        if entry["safe"]:
            raise Refusal("UNSUPPORTED", f"{where}: {entry['safe']}")
        if o["node"] >= len(entry["nodes"]):
            raise Refusal("TARGET_MISSING", f"{where}: the graph has {len(entry['nodes'])} nodes")
        if o["node"] in entry["wsafe"]:
            raise Refusal("UNSUPPORTED", f"{where}: {entry['wsafe'][o['node']]}")
        w = entry["nodes"][o["node"]][1]
        if sha256_bytes(ix["data"][w:w + WAYPOINT_SIZE]) != o["waypoint_sha256"]:
            raise Refusal("TARGET_CHANGED", f"{where}: the waypoint is not the one this mod was made for")
        out.append((ix["lvl"], w, placement_bytes(o, where), f"{o['level']}:{o['model']}@{o['instance']}"
                                                             f".v{o['variable']}.n{o['node']}"))
    return out


# ---------------------------------------------------------------------------------------------------------------
# G6-P13 (D-266): the development-only, same-size operation `collision-vertex-offset`. One named preset lowers the
# three vertices of one static-collision triangle of one exact level file and rewrites, from the edited vertices,
# every value the file derives from them (RE_NOTES "Static collision is file-backed", E-499):
#   zdr mesh (file offset Z): +0 u16 vertices, +2 u16 elements, +8 -> vertices (x, y, z float32), +0xC -> element
#     types (1 = triangles only), +0x10 -> elements, +0x14 -> octree, +0x1C sphere radius, +0x20 sphere centre;
#   triangle element: +4 -> u16 index triples, +8 -> one face normal per triangle = normalize((b - a) x (c - a)),
#     +0xC u16 triangles, +0x14 -> u16 edge slot per corner (corner c = edge (v_c, v_c+1)), +0x18 -> edge normals =
#     normalize(sum of the face normals of the slot's triangles), +0x1C -> edge scalars (1.0 for a one-triangle
#     edge; for a shared edge either 1.0 or min over its triangles of dot(face normal, edge normal) -- |n1 + n2| / 2
#     for two -- by a rule not established between the two classes: the class is kept),
#     +0x20 u16 slots;
#   octree: header {-> root node, u16 triangles, ->, AABB}; node 0x20 {AABB min, max, +0x18 -> 8 children or 0,
#     +0x1C -> leaf list or 0}; leaf list = u16 little-endian count, then (u8 element, triangle as one byte, or two
#     bytes with 0x80 set) -- exactly the triangles whose geometry intersects the cell (393 / 393 leaves).
# Lists cannot change size, so a lowered triangle must stay inside cells that list it: the preset extends the min z
# of the bottom cells under the edit (and of their ancestors and the header) to OCTREE_FLOOR. Every model rule above
# is re-checked on the original data before anything is written; any mismatch refuses the whole mod.
# Off unless R3HD_DEV_STRUCTURAL_TX names the level (compile-time only: the plan holds ordinary `range` records).
COLLISION_KEYS = {"type", "level", "preset", "lvl_sha256"}
COLLISION_ALLOW = {"intro_15": {
    "lvl": (8474200, "474596d68f86de3eba7f3cb19d1595abdc62b37252e2d6d13c6c83483416f4e2"),
    "ptr": (335140, "aaafc65cdf088e2fdb42425288a6f038e7bf7d99023f2aca3b828b231aa43457"),
    "zdr": 0x5A77C, "vertices": 667, "elements": 7, "triangles": 1227, "octree_floor": -11.5,
    "presets": {
        # E-499: the triangle under Rayman's settled spawn point (element 3 triangle 33), lowered 1.50
        "spawn-drop-1.50": {"dz": -1.5, "vertices": {
            365: "c2bffc4b4255d832c11a7638", 392: "c2bb7a9c42648d94c10e11d4", 393: "c2c125c342659436c10fb3ac"}},
        # E-499 control: element 3 triangle 19, 30.4 units from the spawn point, the same edit and derived data
        "control-far-drop-1.50": {"dz": -1.5, "vertices": {
            355: "c2935f6c420f0266c109e974", 356: "c299e80a420c7e88c10e11cc", 380: "c2943af84200f3fcc10d22ec"}},
        # G6-P13b (E-500): the spawn triangle lowered 0.30, inside every known bound: no octree or box word changes;
        # refused if a moved vertex leaves the octree root, the IPO SuperObject's +0x38 box or its file copy
        "spawn-small-drop-0.30": {"dz": -0.3, "bounds": "keep", "vertices": {
            365: "c2bffc4b4255d832c11a7638", 392: "c2bb7a9c42648d94c10e11d4", 393: "c2c125c342659436c10fb3ac"}},
        # G6-P15 (E-502): the verified small drop plus the same surface's visual vertices (E-501: visual object
        # 0x15C74, element 14 triangle 32; visual 1134 / 1187 / 1188 <-> collision 365 / 392 / 393) and the 14 visual
        # face normals that use them; vertex normals unchanged (rule unknown)
        "spawn-small-drop-0.30-visual": {"dz": -0.3, "bounds": "keep", "vertices": {
            365: "c2bffc4b4255d832c11a7638", 392: "c2bb7a9c42648d94c10e11d4", 393: "c2c125c342659436c10fb3ac"},
            "visual": {"object": 0x15C74, "vertices_total": 3543, "elements": 15, "ring": 14, "match": 0.001, "map": {
                1134: ("c2bffc704255d84ec11a763c", 365), 1187: ("c2bb7ac042648db0c10e11d8", 392),
                1188: ("c2c125e842659452c10fb3b0", 393)}}},
        # G6-P16 (E-504 / D-271): a two-step shallow bowl around the spawn point -- the spawn triangle's vertices
        # lowered 0.30 and the four adjacent ground vertices 387 / 388 / 391 / 394 lowered 0.15 (two independently
        # displaced groups; 25 collision + 25 visual triangles), inside every known bound, no octree / box words;
        # each moved collision vertex has exactly one visual twin in object 0x15C74 (no crack); ground triangles stay
        # at normal z >= 0.9
        "spawn-multi-surface-v1": {"bounds": "keep", "ring": 25, "min_normal_z": 0.9, "groups": [
            {"dz": -0.3, "vertices": {365: "c2bffc4b4255d832c11a7638", 392: "c2bb7a9c42648d94c10e11d4",
                                      393: "c2c125c342659436c10fb3ac"}},
            {"dz": -0.15, "vertices": {387: "c2bb1225425114d3c11a7638", 388: "c2c34472424dc27cc11a7638",
                                       391: "c2b756be42603120c10c0464", 394: "c2c66b34425eb6c8c10c44c3"}}],
            "visual": {"object": 0x15C74, "vertices_total": 3543, "elements": 15, "ring": 25, "match": 0.001,
                       "complete": True, "map": {
                           1134: ("c2bffc704255d84ec11a763c", 365), 1187: ("c2bb7ac042648db0c10e11d8", 392),
                           1188: ("c2c125e842659452c10fb3b0", 393), 1181: ("c2bb1249425114eec11a763c", 387),
                           1182: ("c2c34496424dc298c11a763c", 388), 1186: ("c2b756e24260313cc10c0468", 391),
                           1189: ("c2c66b58425eb6e4c10c44c8", 394)}}}},
    "box_copies": (0x378180,)},   # E-499: a second copy of mesh 0x5A77C's AABB (owner not traced)
    # G6-P19 (E-508 / D-275): intro_20 ground under Rayman's start (read-only probe l1: standing at (-66.637,
    # -64.214, -25.078) from 3.5 s, spread 0). Mesh 0x4B3F0 (432 vertices, 6 triangle elements, 768 triangles) of IPO
    # SuperObject 0xB9BC (type 0x20) under a Sector; PhysicalObject 0xBA50 -> visual set 0xBA60 -> visual object 0xBA80
    # (3,650 vertices, 11 elements); identity transforms. Spawn triangle = element 1 triangle 11 (10 / 0 / 9); corner 10
    # has no visual twin within 0.001 (1368 is 0.0058 above it) and stays fixed.
    "intro_20": {
    "lvl": (6135684, "a21aa7691db4cedb3892e685e5395fd23b530b0bde4d64a09035dfb5f2d0b11f"),
    "ptr": (273540, "be90b58a3bfa78d19f3335489edcc79214442d52cbde04c6ad5a465f9fb17cb1"),
    "zdr": 0x4B3F0, "vertices": 432, "elements": 6, "triangles": 768, "octree_floor": -35.5,
    "presets": {
        # spawn corner 0 lowered 0.30 (Rayman stands in triangle 10 / 0 / 9) and the west floor 2 / 4 lowered 0.15; corner
        # 9 cannot move (triangle 1/189 is at normal z 0.908, the ground floor 0.9) and the rim vertices 1 / 5 / 8 / 36 /
        # 37 are wall bottoms (vertical element-0 faces): fixed. Each moved vertex has exactly one visual twin.
        "start-two-step-v1": {"bounds": "keep", "min_normal_z": 0.9, "groups": [
            {"dz": -0.3, "vertices": {0: "c289a937c2866d8ac1c98008"}},
            {"dz": -0.15, "vertices": {2: "c299aabac288c981c1c99b58", 4: "c28bf333c26ff395c1c9769e"}}],
            "visual": {"object": 0xBA80, "vertices_total": 3650, "elements": 11, "ring": "collision", "match": 0.001,
                       "complete": True, "pair": True, "map": {
                           131: ("c289a937c2866d8ac1c98008", 0), 141: ("c299aab9c288c981c1c99b5a", 2),
                           196: ("c28bf333c26ff395c1c9769e", 4)}}}},
    "box_copies": (0x215D6C,)}}   # E-508: an unowned copy of the IPO +0x38 box (as intro_15's 0x378180)
COLLISION_TOL = {"face": 2.5e-5, "edge": 2e-6, "scalar": 2e-6}

# ---------------------------------------------------------------------------------------------------------------
# G6-P17 (D-273): declarative terrain patches (`terrain-patch-v1`, DEVELOPMENT ONLY, same gate as above). A patch names
# an allow-listed region and 2-4 named groups of that region's vertices, each with one fixed z displacement; it is
# compiled into the collision_edit spec above (the verified G6-P16 mechanics: same validators, same derived data, same
# same-size ranges). The region's vertices, original bytes and visual twins come from the verified preset it is built
# on (never from the patch); a patch carries no offsets, addresses, coordinates or file paths. Every proposed
# deformation is checked whole: ground steepness, flips, degenerate triangles, every known bound (no octree / box
# words), octree leaf membership, one visual twin per moved vertex and no second coincident visual vertex, and (new)
# every edited visual triangle pairs with one edited collision triangle (same corners), with equal ring sizes.
TERRAIN_FORMAT = "terrain-patch-v1"
TERRAIN_KEYS = {"format", "level", "lvl_sha256", "region", "name", "groups"}
TERRAIN_OPTIONAL = {"description"}
TERRAIN_GROUP_KEYS = {"name", "vertices", "delta_z"}
TERRAIN_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
TERRAIN_MAX_BYTES = 1 << 16
TERRAIN_REGIONS = {"intro_15": {
    # E-504 / E-505: the seven ground vertices around the spawn point moved in spawn-multi-surface-v1 (runtime-loaded,
    # drawn, walked and framebuffer-attributed); each has one verified visual twin in object 0x15C74
    "spawn-ground-v1": {"preset": "spawn-multi-surface-v1", "delta_z": (-0.30, -0.05), "groups": (2, 4),
                        "min_normal_z": 0.9}},
    # G6-P22 (E-511 / D-278): the three intro_20 ground vertices moved in start-two-step-v1 (runtime-loaded and stood on in
    # G6-P19 / G6-P20; collision 0 / 2 / 4, each with one verified visual twin in object 0xBA80). Corner 9 and the rim
    # vertices 1 / 5 / 8 / 36 / 37 stay out (slope / wall bottoms, D-275). 2-3 groups, lowering only, every combination
    # still checked whole by collision_edit (E-511 sweep: every grid combination of the box passes).
    "intro_20": {
    "start-floor-v1": {"preset": "start-two-step-v1", "delta_z": (-0.30, -0.05), "groups": (2, 3),
                       "min_normal_z": 0.9},
    # G6-P25 (E-514 / D-281): start-floor-v1 + the west pit-floor corner, collision vertex 6 (pure floor: triangles 1/2
    # (6, 5, 7), 1/3, 1/4, no wall triangle; exact unique visual twin 204, next visual vertex 2.58 away). It makes
    # triangle 1/2 -- the ramp to the west rim, outside start-floor-v1 -- editable. Vertex 6 is capped at -0.20: below
    # about -0.24 element 1 edge slot 9 (originally non-coplanar, stored 1.0) becomes coplanar, the unresolved D-266
    # scalar class. A separate versioned region so start-floor-v1 declarations keep their exact meaning.
    "start-floor-v2": {"preset": "start-two-step-v1", "delta_z": (-0.30, -0.05), "groups": (2, 4),
                       "min_normal_z": 0.9, "vertex_delta_z": {6: (-0.20, -0.05)},
                       "note": "vertex 6 (triangles 1/2-1/4): runtime-witnessed on the original floor (G6-P26 run w2) and "
                               "with west-basin (G6-P27 run m1, triangle 1/4); other values are predicted, not measured",
                       "extra": {6: ("c299aad2c2749e29c1c9d4dc", 204, "c299aad2c2749e29c1c9d4dc")}}}}


def terrain_region(level: str, region: str) -> dict:
    """The allow-list of one region: {collision vertex: (original hex, visual vertex, visual original hex)} plus the
    visual object constants, read from the verified preset the region is built on (G6-P25: plus the region's verified
    `extra` vertices)."""
    r = TERRAIN_REGIONS[level][region]
    p = COLLISION_ALLOW[level]["presets"][r["preset"]]
    coll = {k: w for g in p["groups"] for k, w in g["vertices"].items()}
    twin = {c: (v, w) for v, (w, c) in p["visual"]["map"].items()}
    vis = {k: p["visual"][k] for k in ("object", "vertices_total", "elements", "match")}
    verts = {k: (coll[k], *twin[k]) for k in coll}
    verts.update(r.get("extra", {}))
    return {**r, "vertices": dict(sorted(verts.items())), "visual": vis}


def _terrain_json(raw: bytes, where: str):
    """A patch file: UTF-8 JSON object, no duplicate keys, no NaN / Infinity literals, at most 64 KiB."""
    if len(raw) > TERRAIN_MAX_BYTES:
        raise Refusal("BAD_MANIFEST", f"{where}: the patch file is larger than {TERRAIN_MAX_BYTES} bytes")

    def pairs(kv):
        keys = [k for k, _ in kv]
        if len(keys) != len(set(keys)):
            raise Refusal("BAD_MANIFEST", f"{where}: duplicate key in the patch")
        return dict(kv)

    def const(c):
        raise Refusal("BAD_MANIFEST", f"{where}: {c} is not a finite number")
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs, parse_constant=const)
    except (UnicodeDecodeError, ValueError) as e:
        raise Refusal("BAD_MANIFEST", f"{where}: the patch is not JSON: {e}")


def parse_terrain_patch(p, where: str) -> dict:
    """Validate one terrain-patch-v1 object without game data; returns its canonical form (groups ordered by their
    lowest vertex, vertices ascending, displacements as float). Refusal for anything malformed or unsupported."""
    if not isinstance(p, dict):
        raise Refusal("BAD_MANIFEST", f"{where}: a terrain patch must be an object")
    if p.get("format") != TERRAIN_FORMAT:
        raise Refusal("UNSUPPORTED", f"{where}: format {p.get('format')!r} (supported: {TERRAIN_FORMAT})")
    if set(p) - TERRAIN_KEYS - TERRAIN_OPTIONAL or TERRAIN_KEYS - set(p):
        raise Refusal("BAD_MANIFEST", f"{where}: a terrain patch needs exactly {sorted(TERRAIN_KEYS)} "
                                      f"(optional: {sorted(TERRAIN_OPTIONAL)}); unknown or missing: "
                                      f"{sorted((set(p) - TERRAIN_KEYS - TERRAIN_OPTIONAL) | (TERRAIN_KEYS - set(p)))}")
    if not isinstance(p["level"], str) or p["level"] not in TERRAIN_REGIONS:
        raise Refusal("UNSUPPORTED", f"{where}: level {p['level']!r} (supported: {', '.join(sorted(TERRAIN_REGIONS))})")
    lv = p["level"]
    if not isinstance(p["region"], str) or p["region"] not in TERRAIN_REGIONS[lv]:
        raise Refusal("UNSUPPORTED", f"{where}: region {p['region']!r} of {lv} (supported: "
                                     f"{', '.join(sorted(TERRAIN_REGIONS[lv]))})")
    if not isinstance(p["lvl_sha256"], str) or not re.match(r"^[0-9a-f]{64}$", p["lvl_sha256"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'lvl_sha256' must be the level file's 64-digit lower-case SHA-256")
    if p["lvl_sha256"] != COLLISION_ALLOW[lv]["lvl"][1]:
        raise Refusal("TARGET_CHANGED", f"{where}: 'lvl_sha256' is not the {lv}.lvl this region was verified on")
    if not isinstance(p["name"], str) or not TERRAIN_NAME_RE.match(p["name"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'name' must be 1-48 characters of a-z 0-9 - (lower case)")
    if "description" in p and (not isinstance(p["description"], str) or len(p["description"]) > 500):
        raise Refusal("BAD_MANIFEST", f"{where}: 'description' must be text of at most 500 characters")
    reg = terrain_region(lv, p["region"])
    lo, hi = reg["delta_z"]
    gs = p["groups"]
    if not isinstance(gs, list) or not reg["groups"][0] <= len(gs) <= reg["groups"][1]:
        raise Refusal("BAD_MANIFEST", f"{where}: 'groups' must be a list of {reg['groups'][0]}-{reg['groups'][1]} groups")
    seen, names, out = {}, set(), []
    for i, g in enumerate(gs):
        w = f"{where}: groups[{i}]"
        if not isinstance(g, dict) or set(g) != TERRAIN_GROUP_KEYS:
            raise Refusal("BAD_MANIFEST", f"{w} must be an object with exactly {sorted(TERRAIN_GROUP_KEYS)}")
        if not isinstance(g["name"], str) or not TERRAIN_NAME_RE.match(g["name"]) or g["name"] in names:
            raise Refusal("BAD_MANIFEST", f"{w}: 'name' must be a unique 1-48 character a-z 0-9 - name")
        names.add(g["name"])
        vs = g["vertices"]
        if not isinstance(vs, list) or not vs or not all(type(v) is int for v in vs):
            raise Refusal("BAD_MANIFEST", f"{w}: 'vertices' must be a non-empty list of vertex numbers")
        for v in vs:
            if v not in reg["vertices"]:
                raise Refusal("UNSUPPORTED", f"{w}: vertex {v} is not in region {p['region']} (allowed: "
                                             f"{', '.join(map(str, reg['vertices']))})")
            if v in seen:
                raise Refusal("BAD_MANIFEST", f"{w}: vertex {v} is assigned twice (already in group "
                                              f"{seen[v]!r}; each vertex belongs to one group)")
            seen[v] = g["name"]
        dz = g["delta_z"]
        if type(dz) not in (int, float) or not math.isfinite(dz):
            raise Refusal("BAD_MANIFEST", f"{w}: 'delta_z' must be a finite number")
        if not lo <= dz <= hi:
            raise Refusal("UNSUPPORTED", f"{w}: delta_z {dz} is outside {lo:.2f}..{hi:.2f}: this region only lowers "
                                         f"ground (negative values, {-hi:.2f} to {-lo:.2f} down)"
                                         + ("; raising is not supported" if dz > 0 else ""))
        for v in vs:   # G6-P25: a vertex with a tighter verified range (start-floor-v2 vertex 6)
            vlo, vhi = reg.get("vertex_delta_z", {}).get(v, (lo, hi))
            if not vlo <= dz <= vhi:
                raise Refusal("UNSUPPORTED", f"{w}: delta_z {dz} is outside vertex {v}'s verified range "
                                             f"{vlo:.2f}..{vhi:.2f} in region {p['region']}")
        out.append({"name": g["name"], "vertices": sorted(vs), "delta_z": float(dz)})
    canon = {"format": TERRAIN_FORMAT, "level": lv, "lvl_sha256": p["lvl_sha256"], "region": p["region"],
             "name": p["name"]}
    if "description" in p:
        canon["description"] = p["description"]
    canon["groups"] = sorted(out, key=lambda g: g["vertices"][0])
    return canon


def terrain_identity(canon: dict) -> str:
    return sha256_bytes(json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def terrain_spec(canon: dict) -> dict:
    """The collision_edit spec of a canonical patch (the G6-P16 group form, ring sizes derived, pairing checked)."""
    reg = terrain_region(canon["level"], canon["region"])
    moved = [v for g in canon["groups"] for v in g["vertices"]]
    return {"bounds": "keep", "min_normal_z": reg["min_normal_z"],
            "groups": [{"dz": g["delta_z"], "vertices": {v: reg["vertices"][v][0] for v in g["vertices"]}}
                       for g in canon["groups"]],
            "visual": {**reg["visual"], "ring": "collision", "complete": True, "pair": True,
                       "map": {reg["vertices"][v][1]: (reg["vertices"][v][2], v) for v in sorted(moved)}}}


def parse_terrain_override(o: dict, where: str):
    if not structural_enabled():
        raise Refusal("UNSUPPORTED", f"{where}: terrain-patch is a development-only operation (D-273) that this "
                                     "installation does not enable")
    if set(o) != {"type", "patch"}:
        raise Refusal("BAD_MANIFEST", f"{where}: a terrain-patch override needs exactly ['patch', 'type']")
    parse_terrain_patch(o["patch"], where)


def compile_terrain_patch(patch, paths, where="terrain-patch") -> tuple:
    """(canonical patch, [(level file, offset, new bytes, label)]) of one patch against the person's own files."""
    canon = parse_terrain_patch(patch, where)
    lv = canon["level"]
    where = f"{where} {lv} {canon['region']} {canon['name']}"
    if not structural_enabled(lv):
        raise Refusal("UNSUPPORTED", f"{where}: development-only (D-273), not enabled for this level (a private "
                                     f"development compile needs {STRUCT_ENV}={lv})")
    lvl_p, ptr_p, _ = script_level_files(paths["game"], lv)
    if not lvl_p.is_file() or not ptr_p.is_file():
        raise Refusal("TARGET_MISSING", f"{where}: {lvl_p.name} / {ptr_p.name} not found")
    lvl, ptr = lvl_p.read_bytes(), ptr_p.read_bytes()
    if sha256_bytes(lvl) != canon["lvl_sha256"]:
        raise Refusal("TARGET_CHANGED", f"{where}: the level file is not the one this patch was made for")
    edits = collision_edit(lvl, ptr, lv, terrain_spec(canon), where)
    return canon, [(lvl_p, off, data, f"{lv}:terrain.{canon['name']} {w}") for off, data, w in edits]


def parse_collision_vertex_offset(o: dict, where: str):
    if not structural_enabled():
        raise Refusal("UNSUPPORTED", f"{where}: collision-vertex-offset is a development-only operation (D-266) that "
                                     "this installation does not enable")
    if set(o) - COLLISION_KEYS or COLLISION_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: a collision-vertex-offset needs exactly {sorted(COLLISION_KEYS)}")
    if not isinstance(o["level"], str) or o["level"] not in COLLISION_ALLOW:
        raise Refusal("UNSUPPORTED", f"{where}: level {o['level']!r} (the development experiment supports "
                                     f"{', '.join(sorted(COLLISION_ALLOW))})")
    if not isinstance(o["preset"], str) or o["preset"] not in COLLISION_ALLOW[o["level"]]["presets"]:
        raise Refusal("UNSUPPORTED", f"{where}: preset {o['preset']!r} (supported: "
                                     f"{', '.join(sorted(COLLISION_ALLOW[o['level']]['presets']))})")
    if not isinstance(o["lvl_sha256"], str) or not re.match(r"^[0-9a-f]{64}$", o["lvl_sha256"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'lvl_sha256' must be the level file's 64-digit SHA-256")


def _f32(x: float) -> float:
    return struct.unpack(">f", struct.pack(">f", x))[0]


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n > 1e-12 else None


def _face(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    w = [c[i] - a[i] for i in range(3)]
    return _unit([u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]])


def _tri_box(t, lo, hi) -> bool:
    """Separating-axis test: does triangle t (3 points) intersect the closed box lo..hi (1e-4 tolerance)?"""
    c = [(lo[i] + hi[i]) / 2 for i in range(3)]
    h = [(hi[i] - lo[i]) / 2 for i in range(3)]
    v = [[p[i] - c[i] for i in range(3)] for p in t]
    e = [[v[(k + 1) % 3][i] - v[k][i] for i in range(3)] for k in range(3)]
    cr = lambda a, b: [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]  # noqa
    axes = [[1, 0, 0], [0, 1, 0], [0, 0, 1], cr(e[0], e[1])]
    axes += [cr(u, ek) for ek in e for u in ([1, 0, 0], [0, 1, 0], [0, 0, 1])]
    for a in axes:
        if sum(x * x for x in a) < 1e-12:
            continue
        p = [sum(x[i] * a[i] for i in range(3)) for x in v]
        r = sum(h[i] * abs(a[i]) for i in range(3))
        if min(p) > r + 1e-4 or max(p) < -r - 1e-4:
            return False
    return True


def collision_edit(lvl: bytes, ptr: bytes, level: str, spec: dict, where: str, check_files=True) -> list:
    """G6-P13: [(file offset, new bytes, label)] for one allow-listed preset, sorted, non-overlapping, same size.
    Everything is computed from the file and checked against the model in the header comment; Refusal otherwise.
    `check_files` False is only for the offline negative tests (mutated copies must reach the inner checks)."""
    allow = COLLISION_ALLOW[level]

    def fail(why):
        raise Refusal("TARGET_CHANGED", f"{where}: {why}")
    if check_files and ((len(lvl), sha256_bytes(lvl)) != allow["lvl"] or (len(ptr), sha256_bytes(ptr)) != allow["ptr"]):
        fail("the level files are not the exact ones this experiment was made for")
    n = struct.unpack_from(">I", ptr, 0)[0] if len(ptr) >= 4 else 0
    if 4 + 8 * n > len(ptr):
        fail("the pointer table is malformed")
    slots = {}
    for i in range(n):
        f, loc = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        slots[loc + 4] = f
    U32 = lambda o: struct.unpack_from(">I", lvl, o)[0]   # noqa: E731
    F = lambda o, k=1: struct.unpack_from(f">{k}f", lvl, o)   # noqa: E731

    def P(o):   # target of an own-file pointer field, else fail
        if slots.get(o) != 1 or o + 4 > len(lvl):
            fail(f"expected a relocated pointer at 0x{o:X}")
        t = U32(o) + 4
        if not 4 <= t < len(lvl):
            fail(f"pointer at 0x{o:X} leaves the file")
        return t

    def P0(o):
        return None if U32(o) == 0 and o not in slots else P(o)
    Z = allow["zdr"]
    refs = [s for s, f in slots.items() if f == 1 and U32(s) + 4 == Z]
    if len(refs) != 1:
        fail("the collision mesh is not referenced exactly once")
    nv, ne = struct.unpack_from(">HH", lvl, Z)
    if (nv, ne) != (allow["vertices"], allow["elements"]):
        fail("the collision mesh header differs")
    vo, to, eo, octo = P(Z + 8), P(Z + 0xC), P(Z + 0x10), P(Z + 0x14)
    if U32(Z + 0x18) or Z + 0x18 in slots:
        fail("the mesh has parallel boxes (not handled)")
    radius, centre = F(Z + 0x1C)[0], F(Z + 0x20, 3)
    verts = [list(F(vo + 12 * k, 3)) for k in range(nv)]
    if any(not math.isfinite(c) for v in verts for c in v):
        fail("non-finite vertex")
    if any(s in slots for s in range(vo, vo + 12 * nv, 4)):
        fail("a vertex word is relocated")
    if struct.unpack_from(f">{ne}H", lvl, to) != (1,) * ne:
        fail("an element is not a triangle list")
    els = []
    for i in range(ne):
        b = P(eo + 4 * i)
        nt = struct.unpack_from(">H", lvl, b + 0xC)[0]
        tri, nrm, mp, en, es = P(b + 4), P(b + 8), P(b + 0x14), P(b + 0x18), P(b + 0x1C)
        slots_n = struct.unpack_from(">H", lvl, b + 0x20)[0]
        idx = struct.unpack_from(f">{3 * nt}H", lvl, tri)
        if max(idx, default=0) >= nv:
            fail(f"element {i}: a vertex index is out of range")
        mapping = struct.unpack_from(f">{3 * nt}H", lvl, mp)
        if set(mapping) != set(range(slots_n)):
            fail(f"element {i}: the edge slots are not 0..{slots_n - 1}")
        els.append({"nt": nt, "idx": idx, "nrm": nrm, "map": mapping, "en": en, "es": es,
                    "fn": [list(F(nrm + 12 * j, 3)) for j in range(nt)]})
    if sum(e["nt"] for e in els) != allow["triangles"]:
        fail("the triangle count differs")
    # G6-P16 (D-271): a preset may hold several vertex groups, each with its own fixed displacement
    groups = spec.get("groups")
    if groups is None:
        groups = [{"dz": spec["dz"], "vertices": spec["vertices"]}]
        dz_range = (-2.0, -0.25)
    else:
        dz_range = (-0.30, -0.05)
        if not isinstance(groups, list) or not 2 <= len(groups) <= 4:
            fail("unsupported vertex groups")
    spec_v, dzk = {}, {}
    for g in groups:
        dz = g["dz"]
        if not (isinstance(dz, float) and math.isfinite(dz) and dz_range[0] <= dz <= dz_range[1]):
            fail("unsupported displacement")
        for k, want in g["vertices"].items():
            if k in spec_v:
                fail(f"vertex {k} is in two groups")
            spec_v[k], dzk[k] = want, dz
    for k, want in spec_v.items():
        if not 0 <= k < nv:
            fail(f"vertex {k} does not exist")
        if lvl[vo + 12 * k:vo + 12 * k + 12].hex() != want:
            fail(f"vertex {k} is not the original value")
    new = [v[:] for v in verts]
    for k in spec_v:
        new[k][2] = _f32(verts[k][2] + dzk[k])
    # ring: every triangle that uses a moved vertex
    ring = [(ei, j) for ei, e in enumerate(els) for j in range(e["nt"]) if set(spec_v) & set(e["idx"][3 * j:3 * j + 3])]
    if not ring:
        fail("no triangle uses the vertices")
    if "ring" in spec and len(ring) != spec["ring"]:
        fail(f"the collision ring has {len(ring)} triangles, not {spec['ring']}")
    out = []
    for k in sorted(spec_v):
        out.append((vo + 12 * k + 8, struct.pack(">f", new[k][2]), f"vertex {k} z"))
        if math.dist(new[k], centre) > radius:
            fail(f"vertex {k} would leave the mesh's bounding sphere")
    newfn = {}
    for ei, j in ring:
        e = els[ei]
        a, b, c = (e["idx"][3 * j + q] for q in range(3))
        old = _face(verts[a], verts[b], verts[c])
        if old is None or math.dist(old, e["fn"][j]) > COLLISION_TOL["face"]:
            fail(f"element {ei} triangle {j}: the stored normal does not follow the face-normal rule")
        nn = _face(new[a], new[b], new[c])
        if nn is None:
            fail(f"element {ei} triangle {j} would become degenerate")
        if "min_normal_z" in spec and (nn[2] * old[2] <= 0 or old[2] >= spec["min_normal_z"] > nn[2]):
            fail(f"element {ei} triangle {j} would become too steep or flip")
        newfn[(ei, j)] = [_f32(x) for x in nn]
        out.append((e["nrm"] + 12 * j, struct.pack(">3f", *newfn[(ei, j)]), f"element {ei} triangle {j} normal"))
    for ei in sorted({ei for ei, _ in ring}):
        e = els[ei]
        members, ends = {}, {}
        for j in range(e["nt"]):
            t = e["idx"][3 * j:3 * j + 3]
            for c in range(3):
                s = e["map"][3 * j + c]
                ed = frozenset((t[c], t[(c + 1) % 3]))
                if ends.setdefault(s, ed) != ed:
                    fail(f"element {ei}: edge slot {s} names two edges")
                members.setdefault(s, []).append(j)
        touched = sorted({e["map"][3 * j + c] for (x, j) in ring if x == ei for c in range(3)})
        for s in touched:
            js = members[s]
            old_n = _unit([sum(e["fn"][j][i] for j in js) for i in range(3)])
            got_n = F(e["en"] + 12 * s, 3)
            if old_n is None or math.dist(old_n, got_n) > COLLISION_TOL["edge"]:
                fail(f"element {ei}: edge slot {s} does not follow the edge-normal rule")
            fns = [newfn.get((ei, j), e["fn"][j]) for j in js]
            nn = _unit([sum(f[i] for f in fns) for i in range(3)])
            if nn is None:
                fail(f"element {ei}: edge slot {s} would have no normal")
            nn = [_f32(x) for x in nn]
            if struct.pack(">3f", *nn) != lvl[e["en"] + 12 * s:e["en"] + 12 * s + 12]:
                out.append((e["en"] + 12 * s, struct.pack(">3f", *nn), f"element {ei} edge {s} normal"))
            sc = F(e["es"] + 4 * s)[0]
            if len(js) == 1 or sc == 1.0:
                if abs(sc - 1.0) > COLLISION_TOL["scalar"]:
                    fail(f"element {ei}: one-triangle edge slot {s} is not 1.0")
                continue
            h_old = min(sum(e["fn"][j][i] * got_n[i] for i in range(3)) for j in js)
            if abs(sc - h_old) > COLLISION_TOL["scalar"]:
                fail(f"element {ei}: edge slot {s} scalar follows no known rule")
            h_new = _f32(min(sum(f[i] * nn[i] for i in range(3)) for f in fns))
            if struct.pack(">f", h_new) != lvl[e["es"] + 4 * s:e["es"] + 4 * s + 4]:
                out.append((e["es"] + 4 * s, struct.pack(">f", h_new), f"element {ei} edge {s} scalar"))
    # octree: decode, check the leaf lists, extend the bottom cells under the edit
    root = P(octo)
    if struct.unpack_from(">H", lvl, octo + 4)[0] != allow["triangles"] or F(octo + 0xC, 6) != F(root, 6):
        fail("the octree header differs")
    nodes, leaves, stack = [], {}, [root]
    while stack:
        nd = stack.pop()
        if len(nodes) > 4096:
            fail("the octree is larger than expected")
        nodes.append(nd)
        kids, lst = P0(nd + 0x18), P0(nd + 0x1C)
        if kids is not None:
            stack += [c for c in (P0(kids + 4 * q) for q in range(8)) if c is not None]
        else:
            items, p = set(), lst
            if lst is not None:
                cnt, p = struct.unpack_from("<H", lvl, lst)[0], lst + 2
                for _ in range(cnt):
                    el, x = lvl[p], lvl[p + 1]
                    tr, p = (((x & 0x7F) << 8) | lvl[p + 2], p + 3) if x & 0x80 else (x, p + 2)
                    if el >= ne or tr >= els[el]["nt"]:
                        fail("an octree leaf names a triangle that does not exist")
                    items.add((el, tr))
            leaves[nd] = items
    floor_z = allow["octree_floor"]
    root_min_z = F(root + 8)[0]
    if min(new[k][2] for k in spec_v) <= floor_z:
        fail("the displacement goes below the octree floor of this experiment")
    pts = [new[q] for ei, j in ring for q in els[ei]["idx"][3 * j:3 * j + 3]]
    fx = (min(p[0] for p in pts), max(p[0] for p in pts))
    fy = (min(p[1] for p in pts), max(p[1] for p in pts))
    keep = spec.get("bounds", "extend") == "keep"
    if keep:   # G6-P13b: every moved vertex inside the octree root, the IPO's +0x38 box and its copies; no bound edits
        cs_ = refs[0] - 0xC
        po_ = [s - 4 for s, f in slots.items() if f == 1 and U32(s) + 4 == cs_]
        data_ = [s for s, f in slots.items() if f == 1 and len(po_) == 1 and U32(s) + 4 == po_[0]]
        so_ = [s - 4 for s, f in slots.items() if f == 1 and len(data_) == 1 and U32(s) + 4 == data_[0]]
        if len(po_) != 1 or len(data_) != 1 or len(so_) != 1 or U32(so_[0]) not in (0x20, 0x40):
            fail("the mesh's IPO SuperObject is not unique")
        ipo_box, ipo_box2 = P(so_[0] + 0x38), P(so_[0] + 0x34)
        boxes = [("octree root", F(root, 3), F(root + 12, 3)), ("IPO +0x38 box", F(ipo_box, 3), F(ipo_box + 12, 3)),
                 ("IPO +0x34 box", F(ipo_box2, 3), F(ipo_box2 + 12, 3))]
        for c_ in allow.get("box_copies", ()):
            if lvl[c_:c_ + 24] != lvl[ipo_box:ipo_box + 24]:
                fail(f"the AABB copy at 0x{c_:X} differs from the IPO box")
            boxes.append((f"AABB copy 0x{c_:X}", F(c_, 3), F(c_ + 12, 3)))
        for name, lo, hi in boxes:
            for k in spec_v:
                if not all(lo[i] <= new[k][i] <= hi[i] for i in range(3)):
                    fail(f"vertex {k} would leave the {name}")
        box = {nd: (list(F(nd, 3)), list(F(nd + 12, 3))) for nd in nodes}
    else:
        box = {}
        for nd in nodes:
            lo, hi = list(F(nd, 3)), list(F(nd + 12, 3))
            if lo[2] == root_min_z and lo[0] <= fx[1] and hi[0] >= fx[0] and lo[1] <= fy[1] and hi[1] >= fy[0]:
                lo[2] = floor_z
                out.append((nd + 8, struct.pack(">f", floor_z), f"octree node 0x{nd:X} min z"))
            box[nd] = (lo, hi)
        if root not in {o_ - 8 for o_, _, _ in out}:
            fail("the edit is not under the octree root's bottom")
        out.append((octo + 0xC + 8, struct.pack(">f", floor_z), "octree header min z"))
    tri = lambda g, ei, j: [g[q] for q in els[ei]["idx"][3 * j:3 * j + 3]]   # noqa: E731
    ringset = set(ring)
    for nd, items in leaves.items():   # the model: a leaf lists exactly the triangles intersecting its cell
        involved = items & ringset or box[nd][0] != list(F(nd, 3))
        if not involved:
            continue
        lo0, hi0 = F(nd, 3), F(nd + 12, 3)
        exact = {(ei, j) for ei, e in enumerate(els) for j in range(e["nt"]) if _tri_box(tri(verts, ei, j), lo0, hi0)}
        if exact != items:
            fail(f"octree leaf 0x{nd:X} does not list exactly the triangles in its cell")
        after = {(ei, j) for ei, e in enumerate(els) for j in range(e["nt"])
                 if _tri_box(tri(new, ei, j), *box[nd])}
        if not after <= items:
            fail(f"octree leaf 0x{nd:X} would contain a triangle it does not list")
    for nd, items in leaves.items():   # a lowered triangle must not reach any other cell
        for ei, j in ring:
            if (ei, j) not in items and _tri_box(tri(new, ei, j), *box[nd]):
                fail(f"element {ei} triangle {j} would enter octree leaf 0x{nd:X}, which does not list it")
    vis = spec.get("visual")
    if vis:   # G6-P15 (D-269): the same surface's visual vertices and face normals (E-501 mapping)
        out += collision_visual_edit(lvl, slots, U32, F, P, vis, dzk, {k: new[k] for k in spec_v}, fail,
                                     ([els[ei]["idx"][3 * j:3 * j + 3] for ei, j in ring], verts))
    out = sorted(set(out))
    for (o1, d1, w1), (o2, _, w2) in zip(out, out[1:]):
        if o1 + len(d1) > o2:
            fail(f"{w1} and {w2} overlap")
    for o_, d, w in out:
        if any(s in slots for s in range(o_ - 3, o_ + len(d))):
            fail(f"{w} would overwrite a relocated word")
    return out


def collision_visual_edit(lvl, slots, U32, F, P, vis, dzk, coll_new, fail, coll_ring=None) -> list:
    """G6-P15: the visual geometric object of the edited surface (RE_NOTES "Visual geometry of a static surface"):
    {+0 -> vertices, +4 -> vertex normals, +0x10 -> element types, +0x14 -> elements, +0x24 / +0x26 counts,
    +0x2C sphere radius, +0x30 centre}; triangle element {+4 u16 triangles, +0xC -> index triples, +0x14 -> face
    normals, +0x2A u16 parallel box}. Moves the mapped vertices by the same dz, rewrites the face normals of every
    triangle that uses them (normalize((b - a) x (c - a)), checked on the originals first); vertex normals, colours,
    UVs and indices are left unchanged (their rule is not established: E-501)."""
    go = vis["object"]
    nv, ne = struct.unpack_from(">HH", lvl, go + 0x24)
    if (nv, ne) != (vis["vertices_total"], vis["elements"]):
        fail("the visual object header differs")
    vo, no_, to, eo = P(go), P(go + 4), P(go + 0x10), P(go + 0x14)
    refs = lambda t: [s for s, f in slots.items() if f == 1 and U32(s) + 4 == t]   # noqa: E731
    if len(refs(go)) != 1 or len(refs(vo)) != 1 or len(refs(no_)) != 1:
        fail("the visual object or its vertex / normal arrays are shared")
    if any(s in slots for s in range(vo, vo + 12 * nv, 4)):
        fail("a visual vertex word is relocated")
    if struct.unpack_from(f">{ne}H", lvl, to) != (1,) * ne:
        fail("a visual element is not a triangle list")
    radius, centre = F(go + 0x2C)[0], F(go + 0x30, 3)
    verts = [list(F(vo + 12 * k, 3)) for k in range(nv)]
    new = [v[:] for v in verts]
    out = []
    for k, (want, ck) in sorted(vis["map"].items()):
        if lvl[vo + 12 * k:vo + 12 * k + 12].hex() != want:
            fail(f"visual vertex {k} is not the original value")
        if ck not in coll_new:
            fail(f"visual vertex {k} maps to collision vertex {ck}, which the preset does not move")
        dz = dzk[ck]
        if max(abs(verts[k][i] - (coll_new[ck][i] - (dz if i == 2 else 0.0))) for i in range(3)) > vis["match"]:
            fail(f"visual vertex {k} does not coincide with collision vertex {ck}")
        new[k][2] = _f32(verts[k][2] + dz)
        if math.dist(new[k], centre) > radius:
            fail(f"visual vertex {k} would leave the visual bounding sphere")
        out.append((vo + 12 * k + 8, struct.pack(">f", new[k][2]), f"visual vertex {k} z"))
    moved = set(vis["map"])
    if vis.get("complete"):   # G6-P16: every moved collision vertex has exactly one visual twin and no other
        if sorted(ck for _, ck in vis["map"].values()) != sorted(coll_new):
            fail("the visual map does not cover every moved collision vertex exactly once")
        for ck, p in coll_new.items():
            p0 = [p[0], p[1], p[2] - dzk[ck]]
            near = [k for k in range(nv) if k not in moved and math.dist(verts[k], p0) < 0.01]
            if near:
                fail(f"visual vertex {near[0]} also coincides with collision vertex {ck} (would crack)")
    ring = 0
    pairs = None
    if vis.get("pair"):   # G6-P17 (D-273): each edited visual triangle must have one edited collision triangle twin
        ctris, cverts = coll_ring
        cset = {frozenset(t) for t in ctris}
        pairs = set()
    for i in range(ne):
        b = P(eo + 4 * i)
        nt = struct.unpack_from(">H", lvl, b + 4)[0]
        tri, fn = P(b + 0xC), P(b + 0x14)
        idx = struct.unpack_from(f">{3 * nt}H", lvl, tri)
        if max(idx, default=0) >= nv:
            fail(f"visual element {i}: a vertex index is out of range")
        for j in range(nt):
            t = idx[3 * j:3 * j + 3]
            if not moved & set(t):
                continue
            ring += 1
            if pairs is not None:   # a corner with no collision vertex at all is visual-only (E-506: 2766, 86)
                tw = []
                for q in t:
                    near = [c for c, p_ in enumerate(cverts) if math.dist(verts[q], p_) <= vis["match"]]
                    if len(near) > 1:
                        fail(f"visual element {i} triangle {j}: corner {q} coincides with several collision vertices")
                    tw.append(near[0] if near else None)
                if None not in tw:
                    if frozenset(tw) not in cset or frozenset(tw) in pairs:
                        fail(f"visual element {i} triangle {j} pairs with no (unpaired) edited collision triangle")
                    pairs.add(frozenset(tw))
            if struct.unpack_from(">H", lvl, b + 0x2A)[0] != 0xFFFF:
                fail(f"visual element {i} has a parallel box (not handled)")
            old = _face(*(verts[q] for q in t))
            if old is None or math.dist(old, F(fn + 12 * j, 3)) > COLLISION_TOL["face"] * 4:
                fail(f"visual element {i} triangle {j}: the stored normal does not follow the face-normal rule")
            nn = _face(*(new[q] for q in t))
            if nn is None:
                fail(f"visual element {i} triangle {j} would become degenerate")
            out.append((fn + 12 * j, struct.pack(">3f", *(_f32(x) for x in nn)), f"visual element {i} triangle {j} normal"))
    want = len(coll_ring[0]) if vis["ring"] == "collision" else vis["ring"]   # G6-P17: derived from the collision ring
    if ring != want:
        fail(f"the visual ring has {ring} triangles, not {want}")
    return out


def compile_collision_vertex_offset(o: dict, paths) -> list:
    where = f"collision-vertex-offset {o['level']} {o['preset']}"
    allow = COLLISION_ALLOW.get(o["level"])
    if allow is None or not structural_enabled(o["level"]):
        raise Refusal("UNSUPPORTED", f"{where}: development-only, not enabled for this level")
    lvl_p, ptr_p, _ = script_level_files(paths["game"], o["level"])
    if not lvl_p.is_file() or not ptr_p.is_file():
        raise Refusal("TARGET_MISSING", f"{where}: {lvl_p.name} / {ptr_p.name} not found")
    lvl, ptr = lvl_p.read_bytes(), ptr_p.read_bytes()
    if sha256_bytes(lvl) != o["lvl_sha256"]:
        raise Refusal("TARGET_CHANGED", f"{where}: the level file is not the one this mod was made for")
    edits = collision_edit(lvl, ptr, o["level"], allow["presets"][o["preset"]], where)
    return [(lvl_p, off, data, f"{o['level']}:collision.{o['preset']} {w}") for off, data, w in edits]


# ---------------------------------------------------------------------------------------------------------------
# G5-P1 (D-243): the development-only structural operation `insert-graph-node` (one new node, its waypoint, arc list
# and arc, appended to the level file; the level's pointer table rebuilt). Off unless R3HD_DEV_STRUCTURAL_TX names the
# level, and then only for the allow-listed files, graph and node; the plan carries it as one `level-tx` (all or
# nothing), which only a development runtime accepts (tools/m33_mod_overlay.h, R3HD_DEV_STRUCTURAL_TX).

STRUCT_ENV = "R3HD_DEV_STRUCTURAL_TX"
INSERT_NODE_KEYS = {"type", "level", "model", "instance", "variable", "after_node", "lvl_sha256", "ptr_sha256",
                    "position"}
FLY10 = "Gen_NIN\\NIN_m_GenFlyIntro_10\\NIN_m_GenFlyIntro_10.rul^CreateIntelligence^CreateComport:NIN_C_FlyInit"
# level -> exact original files (size, sha256) and the graphs (model key, instance, variable) -> nodes after which one
# node may be inserted. Node 13: G3b (E-469, D-236), G5-P1 (E-476). Node 22: G5-P2a (E-477, D-244; selected from the
# graph's topology, references and the generator's observed route). G5-P4a (E-480, D-247): intro_20's fairy light
# (NIN_m_FairyLight instance 2, designer variable 2), after node 3 -- the graph its owner flies around without input
# (0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 0, about 23 s a loop, within 0.3 units of every waypoint; read-only survey s1).
FAIRY20 = "Fairylum\\NIN_m_FairyLight\\NIN_m_FairyLight.rul^CreateIntelligence^CreateComport:NIN_C_InitLight"
STRUCT_ALLOW = {"intro_10": {
    "lvl": (7661836, "a37638bf1370357db21f33df5c4d37ae806b3c4b9f81b331503ba62d1b19e2ee"),
    "ptr": (209068, "6c9dd70c488a1cac95efc0a55a6086255dae2d851bacd93f5abefdcc8200e940"),
    "graphs": {(FLY10, 0, 0): (13, 22)}},
    "intro_20": {
    "lvl": (6135684, "a21aa7691db4cedb3892e685e5395fd23b530b0bde4d64a09035dfb5f2d0b11f"),
    "ptr": (273540, "be90b58a3bfa78d19f3335489edcc79214442d52cbde04c6ad5a465f9fb17cb1"),
    "graphs": {(FAIRY20, 2, 2): (3,)}}}
STRUCT_MAX_GROW = {"lvl": 4096, "ptr": 1024}   # bytes; = the development runtime's bounds
# G5-P5 (D-249): insert-graph-node operations one mod may carry for a level, all on the same graph, compiled into one
# transaction (canonical order: original node index). intro_10: nodes 13 and 22 together (E-482); others: one.
STRUCT_MAX_OPS = {"intro_10": 2}
# G5-P2a (D-244): engine memory block 8 (level areas; E-465a census, RE_NOTES "Level-file loading"). Measured per
# level in hidden runs with the level opened directly: the single free chunk after the level's area and cross-file
# save table (13,088,528 bytes for intro_10 in E-465a, E-469, E-476), and the largest level-file pre-read the CRT heap
# was seen to serve (intro_15, 8,474,200 bytes, E-465a G5). The budget below must hold with a fixed margin; it is a
# conservative static gate for the measured entry path, not a guarantee for every game state.
# G5-P4a (E-480): intro_20 opened directly, one free chunk of 14,630,936 bytes after its area (6,135,680 at
# 0x40F51494) and save table (survey s1; re-measured by the acceptance control A). Same CRT-heap pre-read evidence.
STRUCT_MEMORY = {"intro_10": {"free_after_load": 13088528, "preread_verified": 8474200},
                 "intro_20": {"free_after_load": 14630936, "preread_verified": 8474200}}
STRUCT_MEMORY_MARGIN = 1 << 20   # bytes of block 8 kept free beyond the loader's temporary need


def structural_budget(level: str, lvl_old: int, lvl_new: int, ptr_new: int, cross: int, where: str) -> dict:
    """G5-P2a (D-244): the block-8 / pre-read budget of one level transaction, or Refusal BUDGET. The level's area is
    the file minus its first word, allocated as ceil(L / 4) + 1 words (82235EB0); the loader's temporary `.ptr` buffers
    are bounded by 4 x (growth + .ptr length + 8 x cross-file entries) (E-465a G3 bound); both come out of the free
    chunk measured after a normal load of the original level."""
    mem = STRUCT_MEMORY.get(level)
    if mem is None:
        raise Refusal("BUDGET", f"{where}: no measured memory budget for level {level}")
    for v in (lvl_old, lvl_new, ptr_new, cross):
        if not isinstance(v, int) or v < 0 or v >= 1 << 31:
            raise Refusal("BUDGET", f"{where}: size out of range")
    if lvl_new < lvl_old or (lvl_new - lvl_old) % 4:
        raise Refusal("BUDGET", f"{where}: the level file's growth is not a whole number of words")
    words = lambda n: -(-(n - 4) // 4) + 1   # noqa: E731  (area = file length - 4)
    area_growth = (words(lvl_new) - words(lvl_old)) * 4
    temp = 4 * ((lvl_new - lvl_old) + ptr_new + 8 * cross)
    free_after = mem["free_after_load"] - area_growth
    out = {"area_growth": area_growth, "free_after_load": free_after, "temporary_bound": temp,
           "margin": STRUCT_MEMORY_MARGIN, "headroom": free_after - temp - STRUCT_MEMORY_MARGIN,
           "preread": lvl_new, "preread_verified": mem["preread_verified"]}
    if out["headroom"] < 0:
        raise Refusal("BUDGET", f"{where}: block-8 budget: {free_after} bytes free after load, {temp} needed for the "
                                f"loader's temporary buffers plus a {STRUCT_MEMORY_MARGIN}-byte margin")
    if lvl_new > mem["preread_verified"]:
        raise Refusal("BUDGET", f"{where}: the level file ({lvl_new} bytes) is larger than any pre-read verified")
    return out
STRUCT_MAX_DISTANCE = 16.0                      # units from the midpoint of the two neighbours' waypoints
TX_VERSION = 1
NODE_SIZE, ARC_LIST_SIZE, ARC_SIZE = 0x1C, 0xC, 0x20


def structural_enabled_env() -> bool:
    """The development gate itself (the environment), ignoring a production-policy scope."""
    return bool(os.environ.get(STRUCT_ENV, ""))


def structural_enabled(level=None) -> bool:
    v = os.environ.get(STRUCT_ENV, "")
    if v:
        return level is None or v == level
    # G6-P30 (D-286): inside a production-policy scope (level_patch_production), the compile of that one level
    return bool(_PROD_SCOPE) and (level is None or level == _PROD_SCOPE[-1])


# G6-P30 (D-286): the production policy for structural content. Exactly one composition compiles without the
# development gate: an intro_20 level patch of a start-floor terrain (region start-floor-v1 / -v2 patch, or the
# start-two-step-v1 preset) + the FairyLight on graph A, without a route. The production runtime (tools/
# m33_mod_overlay.h) enforces the content independently: the pinned ptr / transit results, the FairyLight-A base image
# of the .lvl with the 22 terrain windows reset, and a bound on every word inside those windows. Every other structural
# operation (graph B, routes, all intro_10 insertions, graph nodes, other terrain) stays development-only.
_PROD_SCOPE = []
PROD_TERRAIN_REGIONS = ("start-floor-v1", "start-floor-v2")
PROD_TERRAIN_PRESETS = ("start-two-step-v1",)


def level_patch_production(p) -> str:
    """'' when a raw level-patch object is inside the production policy (its full validation follows), else why not."""
    if not isinstance(p, dict) or p.get("format") != LEVEL_PATCH_FORMAT or p.get("level") != "intro_20":
        return "only intro_20 level-patch-v1 declarations have a production policy"
    comps = p.get("components")
    if not isinstance(comps, list) or not all(isinstance(c, dict) for c in comps):
        return "malformed components"
    types = sorted(str(c.get("type")) for c in comps)
    if "route" in types:
        return "a graph C route is offline-verified only (G6-P28); routes stay development-only"
    if types != ["fairylight", "terrain"]:
        return "the production policy covers exactly one terrain + one FairyLight component"
    f = next(c for c in comps if c.get("type") == "fairylight")
    if f.get("follow_graph_of") != 0 or isinstance(f.get("follow_graph_of"), bool):
        return "only the FairyLight on graph A is production-supported (graph B with terrain is offline-verified only)"
    t = next(c for c in comps if c.get("type") == "terrain")
    if "patch" in t:
        tp = t["patch"]
        if not isinstance(tp, dict) or tp.get("region") not in PROD_TERRAIN_REGIONS:
            return f"terrain region must be one of {', '.join(PROD_TERRAIN_REGIONS)}"
    elif t.get("preset") not in PROD_TERRAIN_PRESETS:
        return f"terrain preset must be one of {', '.join(PROD_TERRAIN_PRESETS)}"
    return ""


class production_scope:
    """Context: structural_enabled(level) is true for the policy's level while a production-eligible patch is parsed or
    compiled (never for anything else; never sets the environment)."""

    def __init__(self, level):
        self.level = level

    def __enter__(self):
        _PROD_SCOPE.append(self.level)

    def __exit__(self, *exc):
        _PROD_SCOPE.pop()


def parse_insert_graph_node(o: dict, where: str):
    if not structural_enabled():
        raise Refusal("UNSUPPORTED", f"{where}: insert-graph-node is a development-only structural operation (D-243) "
                                     "that this installation does not enable")
    if set(o) - INSERT_NODE_KEYS or INSERT_NODE_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: an insert-graph-node needs exactly {sorted(INSERT_NODE_KEYS)}")
    if not isinstance(o["level"], str) or not SCRIPT_LEVEL_RE.match(o["level"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'level' must be a level folder name such as intro_10")
    if o["level"] not in STRUCT_ALLOW:
        raise Refusal("UNSUPPORTED", f"{where}: level {o['level']} (the development pilot supports "
                                     f"{', '.join(sorted(STRUCT_ALLOW))})")
    if not isinstance(o["model"], str) or not 3 <= len(o["model"]) < 0x100 \
            or not all(32 <= ord(c) < 127 for c in o["model"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'model' must be the model's full first-behaviour name")
    for k in ("instance", "variable", "after_node"):
        if not isinstance(o[k], int) or isinstance(o[k], bool) or not 0 <= o[k] < 4096:
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be an index from script-info --model")
    for k in ("lvl_sha256", "ptr_sha256"):
        if not isinstance(o[k], str) or not re.match(r"^[0-9a-f]{64}$", o[k]):
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be the 64-digit SHA-256 of the level's original file")
    placement_bytes(o, where)


def _u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def build_insert_node(lvl: bytes, ptr: bytes, me: int, entry: dict, after: int, pos, where: str) -> tuple:
    """(new .lvl, new .ptr, [(edited offset, label)], info): one node inserted after node `after` of the graph
    `entry` (read_graphs); build_insert_nodes with one site (G5-P1 / G5-P2a / G5-P4a output, byte for byte)."""
    return build_insert_nodes(lvl, ptr, me, entry, [(after, pos)], where)


def _insert_site(lvl: bytes, slots: dict, me: int, g: int, nodes: list, after: int, where: str) -> dict:
    """The original objects of one insertion site (node `after` -> node `after` + 1), every precondition checked
    against the original files: one arc, no capabilities or weight, exclusive references."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: {why}")

    def target(o):
        if slots.get(o) != me or o + 4 > len(lvl):
            return None
        t = _u32(lvl, o) + 4
        return t if t < len(lvl) else None
    if not 0 <= after < len(nodes) - 1:
        raise Refusal("UNSUPPORTED", f"{where}: a node can only be inserted between a node and the one after it "
                                     f"(the graph has {len(nodes)} nodes)")
    A, B = nodes[after], nodes[after + 1]
    if target(A) != B or target(B + 4) != A:
        fail(f"nodes {after} and {after + 1} are not linked to each other")
    WA, LA = target(A + 0xC), target(A + 0x18)
    if WA is None or WA + 0x14 > len(lvl) or target(B + 0xC) is None:
        fail("the nodes have no waypoints in this file")
    if any(s in slots for s in range(WA + 0xC, WA + 0x14, 4)):
        fail("the waypoint's radius or flags hold a relocated word")
    if LA is None or LA + ARC_LIST_SIZE > len(lvl) or _u32(lvl, LA + 8) != 1 or LA + 8 in slots:
        fail("the node does not have exactly one arc (junctions are not supported)")
    ARC = target(LA)
    if ARC is None or target(LA + 4) != ARC or ARC + ARC_SIZE > len(lvl):
        fail("the node's arc list does not hold one arc")
    if _u32(lvl, ARC) or _u32(lvl, ARC + 4) or ARC in slots or ARC + 4 in slots:
        fail("the arc is linked to other arcs")
    if target(ARC + 8) != LA or target(ARC + 0xC) != B:
        fail("the node's arc does not lead to the next node")
    if any(s in slots for s in range(ARC + 0x10, ARC + ARC_SIZE, 4)):
        fail("the arc's attributes hold a relocated word")
    # G5-P2a (D-244): validated invariants for any allow-listed site: the arc carries no capabilities or weight (the
    # copy needs no meaning), and nothing else points at the successor, the arc or into the arc list (so redirecting
    # those references cannot leave a stale one)
    if lvl[ARC + 0x10:ARC + ARC_SIZE] != bytes(ARC_SIZE - 0x10):
        fail("the arc has capabilities or a weight (not supported)")
    nxt = target(B)
    allowed_b = {A, ARC + 0xC} | ({nxt + 4} if nxt is not None else {g + 4})
    into_b, into_arc, into_list = set(), set(), set()
    for so in slots:
        t = target(so)
        if t == B:
            into_b.add(so)
        elif t is not None and ARC <= t < ARC + ARC_SIZE:
            into_arc.add(so)
        elif t is not None and LA <= t < LA + ARC_LIST_SIZE:
            into_list.add(so)
    if into_b != allowed_b:
        fail("the next node is referenced from other data")
    if into_arc != {LA, LA + 4} or into_list != {A + 0x18, ARC + 8}:
        fail("the node's arc or arc list is referenced from other data")
    return {"after": after, "A": A, "B": B, "WA": WA, "LA": LA, "ARC": ARC}


def build_insert_nodes(lvl: bytes, ptr: bytes, me: int, entry: dict, ops: list, where: str) -> tuple:
    """G5-P5 (D-249): (new .lvl, new .ptr, [(edited offset, label)], info) of one or more nodes inserted into the same
    graph, ops = [(after, position)] in strictly increasing order of `after` (the caller's canonical order; original
    node indices, never indices of the modified graph). Every site is validated against the ORIGINAL files first; one
    allocator places all new objects past the file's end in their source objects' 16-byte phases (site by site, in
    graph order), the three link words of each site and the graph's count (once, + len(ops)) are edited with their old
    values asserted, the new pointer slots of all sites are appended in that order to the file's own list, the
    cross-file table moves once. verify_inserts then re-checks the result as the loader and the game would see it."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: {why}")
    if len(lvl) < 8 or len(lvl) % 4 or len(lvl) >= 1 << 31 or len(ptr) < 4:
        fail("the level files' sizes are not ones this operation understands")
    if not ops:
        fail("no insertion")
    afters = [a for a, _ in ops]
    if any(not isinstance(a, int) for a in afters) or any(b <= a for a, b in zip(afters, afters[1:])):
        fail("the insertion sites are not distinct and in graph order")
    if any(b - a < 2 for a, b in zip(afters, afters[1:])):
        raise Refusal("UNSUPPORTED", f"{where}: adjacent insertion sites (a node that is both a site's successor and "
                                     "the next site) are not supported")
    n, m = _u32(ptr, 0), _u32(lvl, 0)
    if 4 + 8 * n + 16 * m != len(ptr):
        fail("the pointer table's layout (count, own entries, cross-file table) is not the one this operation knows")
    slots = {}
    for i in range(n):
        f, loc = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        if loc + 4 in slots:
            fail("the original pointer table names one slot twice")
        slots[loc + 4] = f
    g = entry["graph"]
    nodes = [nd for nd, _ in entry["nodes"]]
    count = _u32(lvl, g + 8)
    if count != len(nodes) or g + 8 in slots:
        fail("the graph's node count does not match its node list")
    sites = [_insert_site(lvl, slots, me, g, nodes, a, where) for a in afters]
    owned = [{s["A"], s["B"], s["WA"], s["LA"], s["ARC"]} for s in sites]
    if sum(len(x) for x in owned) != len(set().union(*owned)):
        fail("two insertion sites share an original object")
    end = cur = len(lvl)
    places = []
    for s in sites:
        place = {}
        for name, size, src in (("node", NODE_SIZE, s["A"]), ("waypoint", 0x14, s["WA"]),
                                ("list", ARC_LIST_SIZE, s["LA"]), ("arc", ARC_SIZE, s["ARC"])):
            off = cur + (src - cur) % 16
            if off % 4 or off < cur or off + size > 1 << 31:
                fail("alignment")
            place[name] = off
            cur = off + size
        places.append(place)
    tail = -(-(cur - end) // 16) * 16
    if end + tail >= 1 << 31:
        fail("the level file would be too large")
    new = bytearray(lvl) + bytearray(tail)
    edits = []
    plan = []
    for s, place in zip(sites, places):
        A, B, ARC, after = s["A"], s["B"], s["ARC"], s["after"]
        FN = place["node"]
        plan += [(A, B - 4, FN - 4, f"node{after}.next"), (B + 4, A - 4, FN - 4, f"node{after + 1}.previous"),
                 (ARC + 0xC, B - 4, FN - 4, f"node{after}.arc.target")]
    plan.append((g + 8, count, count + len(sites), "graph.count"))
    if len({o for o, _, _, _ in plan}) != len(plan):
        fail("two edits of one word")
    for o, old, value, label in plan:
        if _u32(lvl, o) != old:
            fail(f"{label} is not the expected value")
        struct.pack_into(">I", new, o, value)
        edits.append((o, label))
    new_slots = []
    for s, place in zip(sites, places):
        A, B, WA, ARC = s["A"], s["B"], s["WA"], s["ARC"]
        FN, FW, FL, FA = place["node"], place["waypoint"], place["list"], place["arc"]
        pos = dict(ops)[s["after"]]
        struct.pack_into(">7I", new, FN, B - 4, A - 4, g - 4, FW - 4, 0, 0, FL - 4)
        new[FW:FW + 12] = struct.pack(">3f", *pos)
        new[FW + 12:FW + 0x14] = lvl[WA + 12:WA + 0x14]
        struct.pack_into(">3I", new, FL, FA - 4, FA - 4, 1)
        struct.pack_into(">4I", new, FA, 0, 0, FL - 4, B - 4)
        new[FA + 0x10:FA + ARC_SIZE] = lvl[ARC + 0x10:ARC + ARC_SIZE]
        new_slots += [FN, FN + 4, FN + 8, FN + 0xC, FN + 0x18, FL, FL + 4, FA + 8, FA + 0xC]
    nptr = (struct.pack(">I", n + len(new_slots)) + ptr[4:4 + 8 * n]
            + b"".join(struct.pack(">iI", me, s - 4) for s in new_slots) + ptr[4 + 8 * n:])
    new = bytes(new)
    verify_inserts(lvl, ptr, new, nptr, me, g, nodes, list(zip(afters, places)), new_slots, edits, where)
    if len(sites) == 1:
        info = {"after": afters[0], "nodes": len(nodes) + 1, "objects": dict(places[0]), "tail": tail,
                "slots": len(new_slots), "edits": [label for _, label in edits]}
    else:
        info = {"after": afters, "nodes": len(nodes) + len(sites),
                "sites": [{"after": a, "objects": dict(p)} for a, p in zip(afters, places)], "tail": tail,
                "slots": len(new_slots), "edits": [label for _, label in edits]}
    return new, nptr, edits, info


def verify_insert(old_lvl, old_ptr, lvl, ptr, me, g, old_nodes, after, place, new_slots, edits, where):
    """One site: verify_inserts (kept for the G5-P1 / G5-P4a tests)."""
    verify_inserts(old_lvl, old_ptr, lvl, ptr, me, g, old_nodes, [(after, place)], new_slots, edits, where)


def verify_inserts(old_lvl, old_ptr, lvl, ptr, me, g, old_nodes, sites, new_slots, edits, where):
    """The simulator: the new files as the loader (827CDA58: own-file slot += area base; no checks) and the game's
    graph walks (+0 until 0, back by +4) would use them; sites = [(after, place)]. Any difference from the planned
    structure refuses."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: simulated load: {why}")
    n0, m = _u32(old_ptr, 0), _u32(old_lvl, 0)
    n = _u32(ptr, 0)
    if _u32(lvl, 0) != m or 4 + 8 * n + 16 * m != len(ptr) or ptr[4 + 8 * n:] != old_ptr[4 + 8 * n0:]:
        fail("pointer table layout or cross-file table")
    if ptr[4:4 + 8 * n0] != old_ptr[4:4 + 8 * n0]:
        fail("original pointer entries changed")
    slots = {}
    for i in range(n):
        f, loc = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        if loc + 4 in slots:
            fail(f"duplicate relocation slot {loc + 4:#x}")
        slots[loc + 4] = f
    added = [loc + 4 for _, loc in (struct.unpack_from(">iI", ptr, 4 + 8 * i) for i in range(n0, n))]
    if added != new_slots or any(slots[s] != me for s in added):
        fail("new relocation entries")
    objects = sorted((p[k], z) for _, p in sites for k, z in (("node", NODE_SIZE), ("waypoint", 0x14),
                                                               ("list", ARC_LIST_SIZE), ("arc", ARC_SIZE)))
    if objects[0][0] < len(old_lvl) or objects[-1][0] + objects[-1][1] > len(lvl) \
            or any(a + z > b for (a, z), (b, _) in zip(objects, objects[1:])):
        fail("new objects overlap each other or the original file")
    known = {o for o, _ in objects} | {g} | set(old_nodes)
    for s in added:
        if not (len(old_lvl) <= s and s + 4 <= len(lvl) and any(o <= s < o + z for o, z in objects)):
            fail(f"new slot {s:#x} outside the new objects")
        if _u32(lvl, s) + 4 not in known:
            fail(f"new slot {s:#x} does not point at a known object")
    for o, _ in edits:
        if slots.get(o) == me and _u32(lvl, o) + 4 not in known:
            fail(f"edited word {o:#x} does not point at a known object")
    changed = [o for o in range(0, len(old_lvl), 4) if lvl[o:o + 4] != old_lvl[o:o + 4]]
    if changed != sorted(o for o, _ in edits):
        fail("words other than the planned edits changed")

    def target(o):
        return _u32(lvl, o) + 4 if slots.get(o) == me and o + 4 <= len(lvl) and _u32(lvl, o) + 4 < len(lvl) else None
    want = []
    new_at = {after: p["node"] for after, p in sites}
    for i, nd in enumerate(old_nodes):
        want.append(nd)
        if i in new_at:
            want.append(new_at[i])
    walk, prev, nd = [], None, target(g)
    while nd is not None and len(walk) <= len(want):
        if nd in walk or target(nd + 8) != g or target(nd + 4) != prev:
            fail(f"node {len(walk)} of the walk")
        walk.append(nd)
        prev, nd = nd, target(nd)
    if walk != want or _u32(lvl, g + 8) != len(walk) \
            or target(g + 4) != walk[-1] or lvl[walk[-1]:walk[-1] + 4] != old_lvl[walk[-1]:walk[-1] + 4]:
        fail("forward walk, count or last node")
    back, nd = [], target(g + 4)
    while nd is not None and len(back) <= len(walk):
        back.append(nd)
        nd = target(nd + 4)
    if back[::-1] != walk:
        fail("backward walk")
    for after, place in sites:
        A, B, FN, FW, FL, FA = (old_nodes[after], old_nodes[after + 1], place["node"], place["waypoint"],
                                place["list"], place["arc"])
        arc_a = target(target(A + 0x18))
        if arc_a is None or target(arc_a + 0xC) != FN or _u32(lvl, target(A + 0x18) + 8) != 1:
            fail(f"node {after}'s arc")
        if target(FN + 0xC) != FW or target(FN + 0x18) != FL or target(FL) != FA or target(FL + 4) != FA \
                or _u32(lvl, FL + 8) != 1 or target(FA + 8) != FL or target(FA + 0xC) != B \
                or _u32(lvl, FA) or _u32(lvl, FA + 4):
            fail(f"the new node after {after}: waypoint, arc list or arc")


def compile_insert_graph_node(o: dict, paths) -> tuple:
    """G5-P1 (D-243): (ranges, transaction) of one insert-graph-node (compile_insert_graph_nodes with one)."""
    return compile_insert_graph_nodes([o], paths)


def compile_insert_graph_nodes(ops: list, paths) -> tuple:
    """G5-P1 (D-243) / G5-P5 (D-249): (ranges, transaction) of a mod's insert-graph-node operations, all on one graph
    of one level (at most STRUCT_MAX_OPS for the level), as ONE level transaction. Canonical order: by original node
    index (manifest order does not matter); every operation is validated before anything is built, so one invalid
    operation refuses all of them. Ranges: the edited words (three per site, the count once), the appended tail of the
    level file, and the whole rebuilt pointer table (one range: its game-bytes hash covers the original)."""
    if not ops:
        raise Refusal("BAD_MANIFEST", "no structural operation")
    o = ops[0]
    level = o["level"]
    same = ("level", "model", "instance", "variable", "lvl_sha256", "ptr_sha256")
    if any(x[k] != o[k] for x in ops for k in same):
        raise Refusal("BAD_MANIFEST", "the structural operations of one mod must all change the same graph of the "
                                      "same level files")
    ops = sorted(ops, key=lambda x: x["after_node"])
    afters = [x["after_node"] for x in ops]
    where = (f"insert-graph-node {level} {o['model']!r} instance {o['instance']} variable {o['variable']} "
             f"after node{'s' if len(ops) > 1 else ''} {', '.join(str(a) for a in afters)}")
    if len(set(afters)) != len(afters):
        raise Refusal("BAD_MANIFEST", f"{where}: the same insertion site twice")
    allow = STRUCT_ALLOW.get(level)
    if allow is None or not structural_enabled(level):
        raise Refusal("UNSUPPORTED", f"{where}: development-only, not enabled for this level")
    if len(ops) > STRUCT_MAX_OPS.get(level, 1):
        raise Refusal("UNSUPPORTED", f"{where}: at most {STRUCT_MAX_OPS.get(level, 1)} structural operation(s) per "
                                     f"mod for {level}")
    lvl_p, ptr_p, me = script_level_files(paths["game"], level)
    if not lvl_p.is_file() or not ptr_p.is_file():
        raise Refusal("TARGET_MISSING", f"{where}: {lvl_p.name} / {ptr_p.name} not found")
    lvl, ptr = lvl_p.read_bytes(), ptr_p.read_bytes()
    orig = {}
    for role, data in (("lvl", lvl), ("ptr", ptr)):
        sha = sha256_bytes(data)
        if sha != o[f"{role}_sha256"]:
            raise Refusal("TARGET_CHANGED", f"{where}: {role} file is not the version this mod was made for")
        if (len(data), sha) != allow[role]:
            raise Refusal("UNSUPPORTED", f"{where}: {role} file is not an allow-listed version")
        orig[role] = (len(data), sha)
    ix = read_script_index(paths["game"], level)
    if ix["data"] != lvl:
        raise Refusal("TARGET_CHANGED", f"{where}: the level file changed while it was read")
    if ix["defaults"].get(o["model"], 0) is None:
        raise Refusal("TARGET_CHANGED", f"{where}: the model is not unique in this level")
    gkey = (o["model"], o["instance"], o["variable"])
    entry = ix["graphs"].get(gkey)
    if entry is None:
        raise Refusal("TARGET_MISSING", f"{where}: no graph in this designer variable of this actor")
    if entry["safe"]:
        raise Refusal("UNSUPPORTED", f"{where}: {entry['safe']}")
    nodes = entry["nodes"]
    built = []
    for x in ops:
        if x["after_node"] not in allow["graphs"].get(gkey, ()):
            raise Refusal("UNSUPPORTED", f"{where}: the development pilot supports only the allow-listed graph and "
                                         f"nodes (not after node {x['after_node']})")
        pos = struct.unpack(">3f", placement_bytes(x, where))
        a = x["after_node"]
        if a + 1 < len(nodes) and nodes[a][1] is not None and nodes[a + 1][1] is not None:
            wa = struct.unpack_from(">3f", lvl, nodes[a][1])
            wb = struct.unpack_from(">3f", lvl, nodes[a + 1][1])
            mid = [(p + q) / 2 for p, q in zip(wa, wb)]
            if sum((p - q) ** 2 for p, q in zip(pos, mid)) ** 0.5 > STRUCT_MAX_DISTANCE:
                raise Refusal("UNSUPPORTED", f"{where}: the position after node {a} is more than "
                                             f"{STRUCT_MAX_DISTANCE:g} units from the midpoint of the two "
                                             "neighbouring waypoints")
        built.append((a, pos))
    new_lvl, new_ptr, edits, info = build_insert_nodes(lvl, ptr, me, entry, built, where)
    for role, old, new in (("lvl", lvl, new_lvl), ("ptr", ptr, new_ptr)):
        if not 0 < len(new) - len(old) <= STRUCT_MAX_GROW[role]:
            raise Refusal("BUDGET", f"{where}: the {role} file would grow by {len(new) - len(old)} bytes")
    info["memory"] = structural_budget(level, len(lvl), len(new_lvl), len(new_ptr), _u32(lvl, 0), where)
    tag = f"{level}:insert-graph-node"
    ranges = [(lvl_p, off, new_lvl[off:off + 4], f"{tag}.{label}") for off, label in edits]
    ranges += [(lvl_p, len(lvl), new_lvl[len(lvl):], f"{tag}.appended"), (ptr_p, 0, new_ptr, f"{tag}.pointer_table")]
    tx = {"level": level, "files": {"lvl": (lvl_p, *orig["lvl"]), "ptr": (ptr_p, *orig["ptr"])},
          "images": {"lvl": new_lvl, "ptr": new_ptr}, "info": info}
    return ranges, tx


# ---------------------------------------------------------------------------------------------------------------
# G6-P1 (D-251): the development-only structural operation `insert-passive-lum`: one additional instance of
# intro_10's red lum (NIN_m_Lums_Int10), G4b's construction (E-471, D-238) owned by the compiler. Off unless
# R3HD_DEV_STRUCTURAL_TX names the level, and then only for the allow-listed source actor, files and positions. The
# plan carries it as one `level-tx` of version 2 whose members are the level file, its pointer table AND the level's
# transit.lvl (a same-size member: the dynamic world's actor count), all or nothing; only a development runtime
# accepts version 2 (g5p1_dev_gate.py, G6-P1 edits). Version 1 (insert-graph-node) is unchanged.
# G6-P5 (D-258): construction primitives shared by the four verified structural actor operations (insert-passive-lum,
# insert-scripted-frog, insert-fairy-on-graph, insert-gensound-manager). Each is deterministic and strictly checked;
# none infers ownership from address ranges: every caller classifies its pointers from its own verified census facts
# and passes the classification in. What stays per operation (and why) is in reports/post_release/
# STRUCTURAL_MODDING_G6P5_SHARED_ACTOR_CONSTRUCTION.md.
ACTOR_RECORD, ACTOR_BACKUP, ACTOR_BACKUP_DATA, ACTOR_PERSONAL, ACTOR_ALWAYS = 0x48, 0x18, 0x54, 0x14, 0x14


def actor_level_inputs(o: dict, paths, spec: dict, allow: dict, where: str) -> dict:
    """The level file, its pointer table and transit.lvl of one structural actor operation: each must exist, be the
    version the manifest names AND an allow-listed version; the script index is read from the same level file."""
    lvl_p, ptr_p, me = script_level_files(paths["game"], o["level"])
    tl_p = lvl_p.with_name("transit.lvl")
    for p in (lvl_p, ptr_p, tl_p):
        if not p.is_file():
            raise Refusal("TARGET_MISSING", f"{where}: {p.name} not found")
    data = {"lvl": lvl_p.read_bytes(), "ptr": ptr_p.read_bytes(), "transit": tl_p.read_bytes()}
    orig = {}
    for role in ("lvl", "ptr", "transit"):
        sha = sha256_bytes(data[role])
        if sha != o[f"{role}_sha256"]:
            raise Refusal("TARGET_CHANGED", f"{where}: {role} file is not the version this mod was made for")
        if (len(data[role]), sha) != (spec["transit"] if role == "transit" else allow[role]):
            raise Refusal("UNSUPPORTED", f"{where}: {role} file is not an allow-listed version")
        orig[role] = (len(data[role]), sha)
    ix = read_script_index(paths["game"], o["level"])
    if ix["data"] != data["lvl"]:
        raise Refusal("TARGET_CHANGED", f"{where}: the level file changed while it was read")
    return {"level": o["level"], "paths": {"lvl": lvl_p, "ptr": ptr_p, "transit": tl_p}, "me": me, "data": data,
            "orig": orig, "ix": ix}


def actor_transaction(op: str, inp: dict, new_lvl: bytes, new_ptr: bytes, new_tl: bytes, edits: list, info: dict,
                      where: str) -> tuple:
    """(ranges, transaction) of one built actor: both growth bounds and the block-8 budget checked; ranges = the
    edited original words (in the builder's edit order), the appended tail, the whole rebuilt pointer table and
    transit's count word; one version-2 level transaction over (lvl, ptr, same-size transit)."""
    level, P, orig = inp["level"], inp["paths"], inp["orig"]
    lvl, ptr = inp["data"]["lvl"], inp["data"]["ptr"]
    for role, old, new in (("lvl", lvl, new_lvl), ("ptr", ptr, new_ptr)):
        if not 0 < len(new) - len(old) <= STRUCT_MAX_GROW[role]:
            raise Refusal("BUDGET", f"{where}: the {role} file would grow by {len(new) - len(old)} bytes")
    info["memory"] = structural_budget(level, len(lvl), len(new_lvl), len(new_ptr), _u32(lvl, 0), where)
    tag = f"{level}:{op}"
    ranges = [(P["lvl"], off, new_lvl[off:off + 4], f"{tag}.{label}") for off, label in edits]
    ranges += [(P["lvl"], len(lvl), new_lvl[len(lvl):], f"{tag}.appended"),
               (P["ptr"], 0, new_ptr, f"{tag}.pointer_table"),
               (P["transit"], info["transit_word"], new_tl[info["transit_word"]:info["transit_word"] + 4],
                f"{tag}.transit.world_count")]
    tx = {"level": level, "version": TX_VERSION_ACTOR, "same_size": ("transit",),
          "files": {"lvl": (P["lvl"], *orig["lvl"]), "ptr": (P["ptr"], *orig["ptr"]),
                    "transit": (P["transit"], *orig["transit"])},
          "images": {"lvl": new_lvl, "ptr": new_ptr, "transit": new_tl}, "info": info}
    return ranges, tx


def apply_original_edits(lvl: bytes, new: bytearray, plan: list, fail) -> list:
    """Each planned edit (offset, expected original value, new value, label) of an ORIGINAL word, in offset order:
    one edit per word, every original value asserted before it is replaced. [(offset, label)]."""
    if len({o for o, _, _, _ in plan}) != len(plan):
        fail("two edits of one word")
    edits = []
    for o, old, value, label in sorted(plan):
        if _u32(lvl, o) != old:
            fail(f"{label} is not the expected value")
        struct.pack_into(">I", new, o, value)
        edits.append((o, label))
    return edits


def extend_pointer_table(ptr: bytes, new_slots: list) -> bytes:
    """The pointer table with the new own-file / other-file entries [(file, slot offset)] appended after the original
    entries, in the given order; the cross-file table unchanged."""
    n = _u32(ptr, 0)
    return (struct.pack(">I", n + len(new_slots)) + ptr[4:4 + 8 * n]
            + b"".join(struct.pack(">iI", f, o - 4) for f, o in new_slots) + ptr[4 + 8 * n:])


def bump_actor_count(tl: bytes, spec: dict, count: int, fail, added: int = 1) -> bytes:
    """transit.lvl with the dynamic world's actor count (asserted = `count`) + `added` (1; G6-P9's pair: 2); nothing
    else changes."""
    W = spec["world"]
    if _u32(tl, W + 0x10) != count:
        fail("the dynamic world's count")
    ntl = bytearray(tl)
    struct.pack_into(">I", ntl, W + 0x10, count + added)
    return bytes(ntl)


def actor_tables(lvl: bytes, ptr: bytes, tl: bytes, me: int, fail) -> tuple:
    """(slots {slot offset: file}, cross-file entries, target, tail) of the ORIGINAL level files: the sizes and the
    pointer table's layout (count, own entries, cross-file table) checked, no slot named twice. target(o) = the
    own-file word's target offset (None unless o is an own-file slot inside the level); tail(o) = o is an
    unrelocated zero word (a list's end)."""
    if len(lvl) < 8 or len(lvl) % 4 or len(lvl) >= 1 << 31 or len(ptr) < 4 or len(tl) < 0x10 or len(tl) % 4:
        fail("the level files' sizes are not ones this operation understands")
    n, m = _u32(ptr, 0), _u32(lvl, 0)
    if 4 + 8 * n + 16 * m != len(ptr):
        fail("the pointer table's layout (count, own entries, cross-file table) is not the one this operation knows")
    slots = {}
    for i in range(n):
        f, loc = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        if loc + 4 in slots:
            fail("the original pointer table names one slot twice")
        slots[loc + 4] = f
    cross = [struct.unpack_from(">IiIi", ptr, 4 + 8 * n + 16 * j) for j in range(m)]

    def target(o):
        if slots.get(o) != me or o + 4 > len(lvl):
            return None
        t = _u32(lvl, o) + 4
        return t if t < len(lvl) else None

    def tail(o):   # an unrelocated zero word: the end of a list
        return o is not None and o + 4 <= len(lvl) and o not in slots and _u32(lvl, o) == 0
    return slots, cross, target, tail


def actor_walk(start, step, limit: int = 65536) -> list:
    """A list walk: start, step(start), ... until None, a repeat or `limit` elements."""
    out, x = [], start
    while x is not None and x not in out and len(out) < limit:
        out.append(x)
        x = step(x)
    return out


def actor_census(lvl: bytes, slots: dict, me: int, so: int, blk: int) -> tuple:
    """The source block's relocated words by kind of target: (in-block, own-file external, other-file)."""
    inner, ext, other = [], [], []
    for o in range(so, so + blk, 4):
        if o in slots:
            if slots[o] != me:
                other.append(o)
            elif so <= _u32(lvl, o) + 4 < so + blk:
                inner.append(o)
            else:
                ext.append(o)
    return inner, ext, other


def actor_siblings(target, so: int, fail) -> tuple:
    """(next, previous) sibling of the source, each linking back to it."""
    nxt, prv = target(so + 0x14), target(so + 0x18)
    if nxt is None or prv is None or target(nxt + 0x18) != so or target(prv + 0x14) != so:
        fail("the source is not linked between two siblings")
    return nxt, prv


def actor_personal_types(lvl: bytes, slots: dict, target, tail, spec: dict, std: int, family: bool, fail) -> tuple:
    """The personal object-type list {first, last, count}; elements {next, previous, -> header, -> name, flags}:
    (elements, count, the source's index, its element, names). The new name must be unique and either share the
    source type's family prefix (family=True, G6-P1's lum rule) or extend the source type's own name (the others)."""
    PH = spec["personal"]
    pels = actor_walk(target(PH), target, 4096)
    pcount = _u32(lvl, PH + 8)
    if PH + 8 in slots or not pels or len(pels) != pcount or target(PH + 4) != pels[-1] or not tail(pels[-1]) \
            or any(target(b + 4) != a for a, b in zip(pels, pels[1:])):
        fail("the personal object-type list")
    k = _u32(lvl, std + 8)
    if k >= pcount:
        fail("the source's personal index")
    tmpl, names = pels[k], []
    for el in pels:
        nm = target(el + 0xC)
        if nm is None or target(el + 8) != target(tmpl + 8) or el + 0x10 in slots:
            fail("a personal object-type element")
        names.append(lvl[nm:nm + 0x40].split(b"\0")[0])
    new_name = spec["new_name"]
    if family:
        if new_name in names or not new_name.startswith(names[k].rsplit(b"_", 1)[0] + b"_"):
            fail("the new personal-type name is not unique or not of the source's family")
    elif new_name in names or not new_name.startswith(names[k] + b"_"):
        fail("the new personal-type name is not unique or not derived from the source's type")
    return pels, pcount, k, tmpl, names


def actor_records(lvl: bytes, slots: dict, target, tail, spec: dict, fail) -> list:
    """The SO-record list {+0 next, +4 -> SuperObject, state}; its header is reached from the level word
    `records_ref`: the records in list order."""
    RH = spec["records"]
    if target(spec["records_ref"]) != RH:
        fail("the SO-record list header")
    rl = actor_walk(target(RH), target)
    if RH + 8 in slots or not rl or len(rl) != _u32(lvl, RH + 8) or target(RH + 4) != rl[-1] or not tail(rl[-1]):
        fail("the SO-record list")
    return rl


def actor_backup_links(target, tail, spec: dict, fail) -> list:
    """The backup list: header {first link, last link}; a link is a record's +4 and points at the next record's +4."""
    BH = spec["backups"]
    links = actor_walk(target(BH), target)
    if not links or target(BH + 4) != links[-1] or not tail(links[-1]):
        fail("the backup list")
    return links


def actor_backup_records(lvl: bytes, slots: dict, target, links: list, spec: dict, rest: list, label: str, fail,
                         shared=None) -> tuple:
    """The source's backup records (those whose data word lies in its block), exactly at the verified block offsets,
    each referenced as expected; the matrix one (0x54 bytes, its own byte-swapped copy) and inline ones (the block
    word itself, never inside a `shared` region): ([(record, data address)], matrix copy)."""
    SO, BLK, MX = spec["so"], spec["block"], spec["matrix"]
    sbs = [(l_ - 4, target(l_ + 4)) for l_ in links if target(l_ + 4) is not None and SO <= target(l_ + 4) < SO + BLK]
    if [t - SO for _, t in sbs] != list(spec["backup_targets"]) or any(sb + 8 not in rest for sb, _ in sbs):
        fail(f"the source's backup records are not the verified {label}")
    scopy = None
    for sb, t in sbs:
        if any(sb + q in slots for q in (0, 0x10, 0x14)):
            fail("a backup record holds unexpected pointers")
        if t == SO + MX:
            scopy = target(sb + 0xC)
            if _u32(lvl, sb + 0x10) != ACTOR_BACKUP_DATA or scopy is None or scopy + ACTOR_BACKUP_DATA > len(lvl) \
                    or any(scopy + q in slots for q in range(0, ACTOR_BACKUP_DATA, 4)) \
                    or b"".join(lvl[scopy + q:scopy + q + 4][::-1] for q in range(0, 0x54, 4)) != lvl[SO + MX:SO + MX + 0x54]:
                fail("the source's matrix backup")
        elif sb + 0xC in slots or _u32(lvl, sb + 0x10) != 0 or _u32(lvl, sb + 0xC) != _u32(lvl, t) \
                or (shared is not None and shared(t)):
            fail("an inline backup record does not hold its block word")
    return sbs, scopy


def actor_always(lvl: bytes, slots: dict, target, tail, spec: dict, rest: list, same_flags: bool, fail) -> tuple:
    """The always-active list: header {first, last, count} and its in-data owner copy; elements {next, previous,
    -> owner, -> SuperObject, flags}: (elements, the source's element). same_flags: the source's element carries
    the last element's flags (G6-P2's check)."""
    SO, AH, AO = spec["so"], spec["always"], spec["always_owner"]
    al = actor_walk(target(AH), target, 4096)
    if not al or AH + 8 in slots or AO + 8 in slots or target(AH) != target(AO) or target(AH + 4) != target(AO + 4) \
            or target(AH + 4) != al[-1] or not tail(al[-1]) or len(al) != _u32(lvl, AH + 8) \
            or _u32(lvl, AO + 8) != len(al) or any(target(b + 4) != a for a, b in zip(al, al[1:])) \
            or any(target(e + 8) != AO or e + 0xC not in slots or e + 0x10 in slots for e in al):
        fail("the always-active list")
    sel = [e for e in al if target(e + 0xC) == SO]
    if len(sel) != 1 or sel[0] + 0xC not in rest \
            or (same_flags and lvl[sel[0] + 0x10:sel[0] + 0x14] != lvl[al[-1] + 0x10:al[-1] + 0x14]):
        fail("the source's always-active element")
    return al, sel[0]


def actor_world(tl: bytes, cross: list, target, spec: dict, me: int, fail) -> tuple:
    """The transit dynamic world {.., +8 first child, +0xC last child (cross-file entries), +0x10 count}: its
    children in sibling order (the source among them, not last) and the count."""
    SO, W = spec["so"], spec["world"]
    if W + 0x14 > len(tl):
        fail("transit.lvl is too short")
    ends = {}
    for oa, fa, ob, fb in cross:
        if fa != me and fb == me and oa + 4 in (W + 8, W + 0xC):
            ends.setdefault(oa + 4 - W, []).append(ob + 4)
    if sorted(ends) != [8, 0xC] or any(len(v) != 1 for v in ends.values()):
        fail("the dynamic world's first and last children")
    wl = actor_walk(ends[8][0], lambda x: target(x + 0x14), 4096)
    wcount = _u32(tl, W + 0x10)
    if len(wl) != wcount or wl[-1] != ends[0xC][0] or SO not in wl or SO == wl[-1] \
            or any(target(b + 0x18) != a for a, b in zip(wl, wl[1:])):
        fail("the dynamic world's children")
    return wl, wcount


def actor_name(spec: dict) -> bytes:
    """The new personal-type name, NUL-padded to a word (at least one NUL)."""
    return spec["new_name"] + bytes(4 - len(spec["new_name"]) % 4)


def actor_segments(block: int, regions, packed: bool) -> tuple:
    """The parts of the source block the copy carries: the block minus the given left-out regions (block offsets
    [start, end)). packed=False keeps every segment at its own offset (left-out regions stay as zero bytes in the
    copy); packed=True places each segment in its source 16-byte phase right after the previous one (G6-P4).
    ([(source start, source end, copy offset)], copy size, cmap(source block offset) -> copy offset; KeyError for an
    offset in a left-out region)."""
    segs, a = [], 0
    for x, y in sorted(regions):
        segs.append((a, x))
        a = y
    segs.append((a, block))
    out, pos = [], 0
    for a, b in segs:
        pos = pos + (a % 16 - pos % 16) % 16 if packed else a
        out.append((a, b, pos))
        pos += b - a

    def cmap(k):
        for a, b, d in out:
            if a <= k < b:
                return k - a + d
        raise KeyError(hex(k))
    return out, (pos if packed else block), cmap


def actor_layout(size: int, so: int, copy_size: int, name_len: int, n_backups: int, fail, always: bool = False,
                 table_words: int = 0) -> tuple:
    """Where the appended objects go, in this order: the copy (in the source's 16-byte phase), the personal element,
    its name, the SO record, the backup records, the matrix-backup copy, the always-active element (when the source
    has one), a table of `table_words` words (G6-P2's resolve table); the tail padded to 16 bytes. ({object: offset},
    end)."""
    fc = size + (so % 16 - size % 16) % 16
    L = {"copy": fc, "personal": fc + copy_size + (-copy_size) % 4}
    L["name"] = L["personal"] + ACTOR_PERSONAL
    L["record"] = L["name"] + name_len
    L["backup"] = L["record"] + ACTOR_RECORD
    L["backup_copy"] = L["backup"] + ACTOR_BACKUP * n_backups
    end = L["backup_copy"] + ACTOR_BACKUP_DATA
    if always:
        L["always"] = end
        end += ACTOR_ALWAYS
    if table_words:
        L["table"] = end
        end += 4 * table_words
    end += (-end) % 16
    if end >= 1 << 31 or any(v % 4 for v in L.values()):
        fail("alignment")
    return L, end


COPY_CLASSES = ("owned", "shared", "other", "link")


def actor_copy(new: bytearray, lvl: bytes, s: dict, so: int, fc: int, segs: list, cmap, kinds: dict, fail) -> list:
    """Copies the source block's segments to the copy at `fc` and plans the copy's relocations. Every relocated word
    of a copied segment carries an EXPLICIT class from the caller's verified census (never inferred from its value):
      owned       rebased onto the copy; its target must lie in a copied segment (an instance object it owns)
      shared      unchanged: model data or a shared region of the source (target identity kept)
      other       unchanged: an other-file pointer (same file, same target)
      link        a sibling link, rewritten here: next -> the source's next sibling, previous -> the source
      ("ref", T)  an explicit reference to an existing object at file offset T (an actor, a graph)
    A relocated word without a class refuses. The copy's personal index becomes the old type count. New slots, in
    block order: [(file, copy offset)]."""
    slots = s["slots"]
    new_slots = []
    for a, b, d in segs:
        new[fc + d:fc + d + b - a] = lvl[so + a:so + b]
    for a, b, d in segs:
        for o in range(so + a, so + b, 4):
            if o not in slots:
                continue
            kind, co = kinds.get(o), fc + o - so - a + d
            if kind == "owned":
                try:
                    ct = cmap(_u32(lvl, o) + 4 - so)
                except KeyError:
                    fail(f"the copy's owned pointer at +{o - so:#x} leads outside its copied segments")
                struct.pack_into(">I", new, co, fc + ct - 4)
            elif isinstance(kind, tuple) and len(kind) == 2 and kind[0] == "ref" and isinstance(kind[1], int):
                struct.pack_into(">I", new, co, kind[1] - 4)
            elif kind not in COPY_CLASSES:
                fail(f"the copy's relocated word at +{o - so:#x} has no ownership class")
            new_slots.append((slots[o], co))
    if kinds.get(so + 0x14) != "link" or kinds.get(so + 0x18) != "link":
        fail("the source's sibling links are not classified as links")
    struct.pack_into(">I", new, fc + cmap(0x14), s["next"] - 4)
    struct.pack_into(">I", new, fc + cmap(0x18), so - 4)
    struct.pack_into(">I", new, fc + cmap(s["std"] - so) + 8, s["pcount"])
    return new_slots


def actor_register(new: bytearray, lvl: bytes, me: int, spec: dict, s: dict, L: dict, name: bytes, cm) -> tuple:
    """Appends the copy's registration objects, each a copy of the source's own (its state / flags bytes kept): the
    personal-type element and its name, the SO record, the backup records in the source's order (data words mapped
    to the copy by cm(source address); the matrix one with its own copy of the matrix backup), and the always-active
    element when the source has one. (new slots in that order, the plan of original-word edits that link each
    object last into its list and the copy after the source in the sibling chain)."""
    put = lambda o, v: struct.pack_into(">I", new, o, v)   # noqa: E731
    SO, fc = spec["so"], L["copy"]
    new_slots = []
    pe, plast = L["personal"], s["personal"][-1]
    new[pe:pe + ACTOR_PERSONAL] = lvl[s["template"]:s["template"] + ACTOR_PERSONAL]
    put(pe, 0)
    put(pe + 4, plast - 4)
    put(pe + 0xC, L["name"] - 4)
    new[L["name"]:L["name"] + len(name)] = name
    new_slots += [(me, pe + 4), (me, pe + 8), (me, pe + 0xC), (me, plast)]
    rec, rlast = L["record"], s["records"][-1]
    new[rec:rec + ACTOR_RECORD] = lvl[s["srec"]:s["srec"] + ACTOR_RECORD]
    put(rec, 0)
    put(rec + 4, fc - 4)
    new_slots += [(me, rec + 4), (me, rlast)]
    # backup records, chained after the old last link in the source's order (the first one's predecessor is an
    # original word, edited by the plan)
    blink = prev = s["links"][-1]
    for i, (sb, t) in enumerate(s["backups"]):
        r = L["backup"] + ACTOR_BACKUP * i
        new[r:r + ACTOR_BACKUP] = lvl[sb:sb + ACTOR_BACKUP]
        put(r + 4, 0)
        if i:
            put(prev, r)
        put(r + 8, cm(t) - 4)
        new_slots.append((me, r + 8))
        if t == SO + spec["matrix"]:
            new[L["backup_copy"]:L["backup_copy"] + ACTOR_BACKUP_DATA] = lvl[s["scopy"]:s["scopy"] + ACTOR_BACKUP_DATA]
            put(r + 0xC, L["backup_copy"] - 4)
            new_slots.append((me, r + 0xC))
        new_slots.append((me, prev))
        prev = r + 4
    PH, RH, BH = spec["personal"], spec["records"], spec["backups"]
    plan = [(SO + 0x14, s["next"] - 4, fc - 4, "source.next"), (s["next"] + 0x18, SO - 4, fc - 4, "next.previous"),
            (PH + 4, plast - 4, pe - 4, "personal.last"), (PH + 8, s["pcount"], s["pcount"] + 1, "personal.count"),
            (plast, 0, pe - 4, "personal.old_last.next"), (RH + 4, rlast - 4, rec - 4, "records.last"),
            (RH + 8, len(s["records"]), len(s["records"]) + 1, "records.count"),
            (rlast, 0, rec - 4, "records.old_last.next"), (BH + 4, blink - 4, prev - 4, "backups.last"),
            (blink, 0, L["backup"], "backups.old_last.next")]
    if "always" in spec:   # the always-active element (owner and flags as the source's own element)
        AH, AO, ae, alast = spec["always"], spec["always_owner"], L["always"], s["always"][-1]
        put(ae, 0)
        put(ae + 4, alast - 4)
        put(ae + 8, AO - 4)
        put(ae + 0xC, fc - 4)
        new[ae + 0x10:ae + 0x14] = lvl[s["always_el"] + 0x10:s["always_el"] + 0x14]
        new_slots += [(me, ae + 4), (me, ae + 8), (me, ae + 0xC), (me, alast)]
        n = len(s["always"])
        plan += [(alast, 0, ae - 4, "always.old_last.next"), (AH + 4, alast - 4, ae - 4, "always.last"),
                 (AH + 8, n, n + 1, "always.count"), (AO + 4, alast - 4, ae - 4, "always_owner.last"),
                 (AO + 8, n, n + 1, "always_owner.count")]
    return new_slots, plan


def actor_verify_load(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, spec, s, objects, new_slots, edits, to_src,
                      fail, n_actors: int = 1) -> tuple:
    """The simulator's common part: the new files as the loader would use them (own-file slot += area base, no
    checks; the original entries and the cross-file table unchanged; the new entries exactly the planned ones), the
    appended objects disjoint and after the original file with zero padding, every new slot inside a new object or an
    old list end (other-file slots only where the source word has the same file, by to_src(copy word) -> source
    word), no original word changed but the planned edits, transit changed only in its actor count. (slots, target)."""
    n0, m = _u32(old_ptr, 0), _u32(old_lvl, 0)
    n = _u32(ptr, 0)
    if _u32(lvl, 0) != m or 4 + 8 * n + 16 * m != len(ptr) or ptr[4 + 8 * n:] != old_ptr[4 + 8 * n0:] \
            or ptr[4:4 + 8 * n0] != old_ptr[4:4 + 8 * n0]:
        fail("pointer table layout, original entries or cross-file table")
    slots = {}
    for i in range(n):
        f, loc = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        if loc + 4 in slots:
            fail(f"duplicate relocation slot {loc + 4:#x}")
        slots[loc + 4] = f
    added = [(f, loc + 4) for f, loc in (struct.unpack_from(">iI", ptr, 4 + 8 * i) for i in range(n0, n))]
    if added != new_slots:
        fail("new relocation entries")
    size = len(old_lvl)
    objects = sorted(objects)
    if objects[0][0] < size or objects[-1][0] + objects[-1][1] > len(lvl) \
            or any(a + z > b for (a, z), (b, _) in zip(objects, objects[1:])):
        fail("new objects overlap each other or the original file")
    endo = objects[-1][0] + objects[-1][1]
    if lvl[size:objects[0][0]] != bytes(objects[0][0] - size) or lvl[endo:] != bytes(len(lvl) - endo):
        fail("padding")
    tails = {s["personal"][-1], s["records"][-1], s["links"][-1]} | ({s["always"][-1]} if "always" in spec else set())
    if any(o in s["slots"] for o in tails) or not tails <= {o for o, _ in edits}:
        fail("old list ends")
    for f, o in added:
        if not (any(a <= o < a + z for a, z in objects) or (o in tails and f == me)) or o + 4 > len(lvl):
            fail(f"new slot {o:#x} outside the new objects")
        if f == me and not _u32(lvl, o) + 4 < len(lvl):
            fail(f"new slot {o:#x} points outside the level")
        if f != me and (to_src(o) is None or s["slots"].get(to_src(o)) != f):
            fail(f"new other-file slot {o:#x}")
    changed = [o for o in range(0, size, 4) if lvl[o:o + 4] != old_lvl[o:o + 4]]
    if changed != sorted(o for o, _ in edits):
        fail("words other than the planned edits changed")
    W = spec["world"]
    if len(tl) != len(old_tl) or [o for o in range(0, len(tl), 4) if tl[o:o + 4] != old_tl[o:o + 4]] != [W + 0x10] \
            or _u32(tl, W + 0x10) != _u32(old_tl, W + 0x10) + n_actors:
        fail("transit.lvl changes other than the dynamic world's count")

    def target(o):
        return _u32(lvl, o) + 4 if slots.get(o) == me and o + 4 <= len(lvl) and _u32(lvl, o) + 4 < len(lvl) else None
    return slots, target


def actor_verify_lists(old_lvl, lvl, tl, me, spec, s, L, slots, target, cm, std, fail):
    """The simulator's list walks: the dynamic world (the copy right after the source, count + 1, links consistent,
    first / last unchanged, its parent word the source's), the SO records (the new one last, naming the copy; the
    original owners unchanged; exactly one record each for the copy and the source), the backup records (the
    copy's last, in the source's order and kinds, data words on the copy by cm, its own matrix copy), the personal
    types (the new element last, unique name, the source type's flags, the copy's index its position) and, when the
    source has one, the always-active list (the copy's element last in both headers, owner as every element)."""
    SO, MX, W, C = spec["so"], spec["matrix"], spec["world"], L["copy"]
    first = next(ob + 4 for oa, fa, ob, fb in s["cross"] if fa != me and fb == me and oa + 4 == W + 8)
    last = next(ob + 4 for oa, fa, ob, fb in s["cross"] if fa != me and fb == me and oa + 4 == W + 0xC)
    w = actor_walk(first, lambda x: target(x + 0x14), 4096)
    want = list(s["walk"])
    want.insert(want.index(SO) + 1, C)
    if w != want or w[-1] != last or _u32(tl, W + 0x10) != len(w) \
            or any(target(b + 0x18) != a for a, b in zip(w, w[1:])) or target(C + 0x1C) is not None \
            or _u32(lvl, C + 0x1C) != _u32(old_lvl, SO + 0x1C):
        fail("the dynamic world")
    rl = actor_walk(target(spec["records"]), target)
    if rl != s["records"] + [L["record"]] or _u32(lvl, spec["records"] + 8) != len(rl) \
            or target(spec["records"] + 4) != rl[-1] or target(L["record"] + 4) != C:
        fail("the SO-record list")
    owners = [target(r + 4) for r in rl]
    old_owners = [_u32(old_lvl, r + 4) + 4 if s["slots"].get(r + 4) == me else None for r in s["records"]]
    if owners[:-1] != old_owners or owners.count(C) != 1 or owners.count(SO) != 1:
        fail("SO-record owners (the original ones unchanged, exactly one record each for the copy and the source)")
    bl = actor_walk(target(spec["backups"]), target)
    mine = [L["backup"] + ACTOR_BACKUP * i + 4 for i in range(len(s["backups"]))]
    if bl != s["links"] + mine or target(spec["backups"] + 4) != bl[-1]:
        fail("the backup list")
    for i, (sb, t) in enumerate(s["backups"]):
        r = L["backup"] + ACTOR_BACKUP * i
        if target(r + 8) != cm(t) or lvl[r + 0x10:r + 0x18] != old_lvl[sb + 0x10:sb + 0x18]:
            fail("a backup record of the copy")
        if t == SO + MX and (target(r + 0xC) != L["backup_copy"] or b"".join(
                lvl[L["backup_copy"] + q:L["backup_copy"] + q + 4][::-1] for q in range(0, 0x54, 4))
                != lvl[cm(t):cm(t) + 0x54]):
            fail("the copy's matrix backup")
        if t != SO + MX and (r + 0xC in slots or _u32(lvl, r + 0xC) != _u32(lvl, cm(t))):
            fail("an inline backup of the copy")
    pl = actor_walk(target(spec["personal"]), target)
    nm = target(L["personal"] + 0xC)
    if pl != s["personal"] + [L["personal"]] or _u32(lvl, spec["personal"] + 8) != len(pl) \
            or target(spec["personal"] + 4) != pl[-1] or target(L["personal"] + 4) != s["personal"][-1] \
            or nm != L["name"] or lvl[nm:nm + 0x40].split(b"\0")[0] != spec["new_name"] \
            or pl.index(L["personal"]) != _u32(lvl, std + 8) \
            or lvl[L["personal"] + 0x10:L["personal"] + 0x14] != old_lvl[s["template"] + 0x10:s["template"] + 0x14]:
        fail("the personal object-type list")
    if "always" in spec:
        AH, AO = spec["always"], spec["always_owner"]
        al = actor_walk(target(AH), target, 4096)
        if al != s["always"] + [L["always"]] or target(AH + 4) != al[-1] or target(AO + 4) != al[-1] \
                or _u32(lvl, AH + 8) != len(al) or _u32(lvl, AO + 8) != len(al) or target(L["always"] + 0xC) != C \
                or target(L["always"] + 8) != AO or target(L["always"] + 4) != s["always"][-1] \
                or [target(e + 0xC) for e in al].count(C) != 1 or [target(e + 0xC) for e in al].count(SO) != 1:
            fail("the always-active list")


INSERT_LUM_KEYS = {"type", "level", "model", "instance", "lvl_sha256", "ptr_sha256", "transit_sha256", "position"}
LUM10 = "lum\\NIN_m_Lums_Int10\\NIN_m_Lums_Int10.rul^CreateIntelligence^CreateComport:NIN_C_RedLums_Init"
TX_VERSION_ACTOR = 2
# level -> the verified G4b scenario (E-471, RE_NOTES "Level growth G4"): exact transit.lvl (the level and pointer
# table come from STRUCT_ALLOW), the one source actor (model key, actor index in file order, its SuperObject and its
# 1,208-byte block with 14 in-block, 16 own-file external and 1 transit pointers), the lists it must
# be registered in (personal object-type list header, SO-record list header and the level word that points at it,
# backup list header, the transit dynamic world), block offsets (the three translation copies, the matrix, the 3dData
# buffer word that must be 0 in the file), the new personal-type name (G4b's), and the approved positions: a new lum is
# placed within `radius` units of one anchor (G4b B: the source + 5 units in z; G4b C / E: on the flight path).
LUM_ALLOW = {"intro_10": {
    "transit": (41508, "d300ba3a4a3c03cec6a73eb9da8a8d820fcc3a669591e976b357e804315bf275"),
    "model": LUM10, "instance": 6, "so": 0x549A30, "block": 0x4B8, "census": (14, 16, 1),
    "personal": 0x1C74, "records_ref": 0x1CFC, "records": 0x5A7434, "backups": 0x1CEC, "world": 0x9B4,
    "matrix": 0xC4, "translations": (0xC4 + 0x34, 0x260 + 0x34, 0x498), "buffer": 0x14C,
    "new_name": b"NIN_m_Lums_Int10_G4B",
    "anchors": {"beside_source": ("source", (0.0, 0.0, 5.0)), "flight_path": ("absolute", (17.87, -101.22, -44.18))},
    "radius": 1.0}}
LUM_RECORD, LUM_BACKUP, LUM_BACKUP_DATA, LUM_PERSONAL = ACTOR_RECORD, ACTOR_BACKUP, ACTOR_BACKUP_DATA, ACTOR_PERSONAL


def parse_insert_passive_lum(o: dict, where: str):
    if not structural_enabled():
        raise Refusal("UNSUPPORTED", f"{where}: insert-passive-lum is a development-only structural operation (D-251) "
                                     "that this installation does not enable")
    if set(o) - INSERT_LUM_KEYS or INSERT_LUM_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: an insert-passive-lum needs exactly {sorted(INSERT_LUM_KEYS)}")
    if not isinstance(o["level"], str) or not SCRIPT_LEVEL_RE.match(o["level"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'level' must be a level folder name such as intro_10")
    if o["level"] not in LUM_ALLOW:
        raise Refusal("UNSUPPORTED", f"{where}: level {o['level']} (the development pilot supports "
                                     f"{', '.join(sorted(LUM_ALLOW))})")
    if not isinstance(o["model"], str) or not 3 <= len(o["model"]) < 0x100 \
            or not all(32 <= ord(c) < 127 for c in o["model"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'model' must be the model's full first-behaviour name")
    if not isinstance(o["instance"], int) or isinstance(o["instance"], bool) or not 0 <= o["instance"] < 4096:
        raise Refusal("BAD_MANIFEST", f"{where}: 'instance' must be an index from script-info --model")
    for k in ("lvl_sha256", "ptr_sha256", "transit_sha256"):
        if not isinstance(o[k], str) or not re.match(r"^[0-9a-f]{64}$", o[k]):
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be the 64-digit SHA-256 of the level's original file")
    placement_bytes(o, where)


def lum_anchors(lvl: bytes, spec: dict) -> dict:
    """{name: (x, y, z)} of the approved positions, as 32-bit floats (G4b's values)."""
    f32 = lambda v: struct.unpack(">f", struct.pack(">f", v))[0]   # noqa: E731
    src = struct.unpack_from(">3f", lvl, spec["so"] + spec["translations"][0])
    return {name: tuple(f32(s + d) for s, d in zip(src, v)) if kind == "source" else tuple(f32(x) for x in v)
            for name, (kind, v) in spec["anchors"].items()}


def _lum_source(lvl: bytes, ptr: bytes, tl: bytes, me: int, spec: dict, peers: list, where: str) -> dict:
    """Every original object the insertion touches, each precondition checked against the ORIGINAL files: the source
    block's pointer census and ownership (in-block pointers rebased; external pointers shared with another instance of
    the model, so model data, not an instance buffer), its incoming references (siblings, one SO record, one backup
    record; nothing in the cross-file table), and the four lists (personal types, SO records, backups, the transit
    dynamic world) with their tails and counts."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: {why}")
    slots, cross, target, tail = actor_tables(lvl, ptr, tl, me, fail)
    SO, BLK, MX = spec["so"], spec["block"], spec["matrix"]
    if SO % 4 or SO + BLK > len(lvl) or _u32(lvl, SO) != 2:
        fail("the source is not an actor SuperObject")
    inner, ext, other = actor_census(lvl, slots, me, SO, BLK)
    if (len(inner), len(ext), len(other)) != spec["census"]:
        fail(f"the source block's pointers are {len(inner)} / {len(ext)} / {len(other)}, not the verified "
             f"{spec['census']}")
    if other != [SO + 0x1C] or _u32(lvl, SO + 0x1C) + 4 != spec["world"]:
        fail("the source's only other-file pointer is not its parent, the transit dynamic world")
    nxt, prv = actor_siblings(target, SO, fail)
    for o in ext:
        if o in (SO + 0x14, SO + 0x18):
            continue
        t = _u32(lvl, o) + 4
        if not any(
                slots.get(p + o - SO) == me and _u32(lvl, p + o - SO) + 4 == t for p in peers):
            fail(f"the source block's pointer at +{o - SO:#x} is not model data shared with another instance")
    if target(SO + 0x20) != SO + MX:
        fail("the source's matrix is not in its block")
    std = target(target(SO + 4) + 4) if target(SO + 4) is not None else None
    if std is None or not SO <= std < SO + BLK - 12 or std + 8 in slots:
        fail("the source's standard-game record is not in its block")
    if _u32(lvl, SO + spec["buffer"]) or SO + spec["buffer"] in slots:
        fail("the source's 3dData buffer word is not 0 in the file (it must be allocated at initialization)")
    pos = [lvl[SO + t:SO + t + 12] for t in spec["translations"]]
    if len(set(pos)) != 1 or spec["translations"][0] != MX + 0x34:
        fail("the source's translation copies differ")
    # incoming references: the two siblings, one SO record (+4), one backup record (+8); nothing cross-file
    into = sorted(o for o in slots if slots[o] == me and not SO <= o < SO + BLK and SO <= _u32(lvl, o) + 4 < SO + BLK)
    recs = [o for o in into if _u32(lvl, o) + 4 == SO and o not in (nxt + 0x18, prv + 0x14)]
    baks = [o for o in into if _u32(lvl, o) + 4 == SO + MX]
    if len(recs) != 1 or len(baks) != 1 or sorted([nxt + 0x18, prv + 0x14] + recs + baks) != into:
        fail("the source is referenced from data other than its siblings, one SO record and one backup record")
    if any((fa == me and SO <= oa + 4 < SO + BLK) or (fb == me and SO <= ob + 4 < SO + BLK) for oa, fa, ob, fb in cross):
        fail("the source is referenced from the cross-file table")
    srec, sb = recs[0] - 4, baks[0] - 8
    if any(srec + k in slots for k in range(8, ACTOR_RECORD, 4)) or SO + BLK > srec >= SO:
        fail("the source's SO record holds other pointers")
    if any(sb + k in slots for k in (0, 0x10, 0x14)) or _u32(lvl, sb + 0x10) != ACTOR_BACKUP_DATA:
        fail("the source's backup record is not a 0x54-byte matrix backup")
    scopy = target(sb + 0xC)
    if scopy is None or scopy + ACTOR_BACKUP_DATA > len(lvl) or any(scopy + k in slots for k in range(0, 0x54, 4)) \
            or b"".join(lvl[scopy + k:scopy + k + 4][::-1] for k in range(0, 0x54, 4)) != lvl[SO + MX:SO + MX + 0x54]:
        fail("the source's backup copy does not hold its matrix")
    pels, pcount, k, tmpl, names = actor_personal_types(lvl, slots, target, tail, spec, std, True, fail)
    rl = actor_records(lvl, slots, target, tail, spec, fail)
    if srec not in rl:
        fail("the SO-record list")
    links = actor_backup_links(target, tail, spec, fail)
    if sb + 4 not in links:
        fail("the backup list")
    walk, wcount = actor_world(tl, cross, target, spec, me, fail)
    return {"slots": slots, "cross": cross, "next": nxt, "prev": prv, "std": std, "index": k, "pcount": pcount,
            "personal": pels, "template": tmpl, "names": names, "srec": srec, "records": rl, "sb": sb,
            "scopy": scopy, "links": links, "walk": walk, "world_count": wcount, "inner": inner, "ext": ext,
            "backups": [(sb, SO + MX)]}


def build_passive_lum(lvl: bytes, ptr: bytes, tl: bytes, me: int, spec: dict, peers: list, pos, where: str) -> tuple:
    """(new .lvl, new .ptr, new transit.lvl, [(edited .lvl offset, label)], info): G4b's one additional lum
    (E-471), every word it changes asserted first. Appended after the file's end: the copy (in the source's 16-byte
    phase, in-block pointers rebased, external pointers kept, its own translation and personal index), the personal
    element and its name, the SO record, the backup record and its byte-swapped matrix copy; linked after the source
    in the sibling chain and last in the three level lists; transit's dynamic-world count + 1. verify_passive_lum
    then re-checks the result as the loader and the game's list walks would see it."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: {why}")
    s = _lum_source(lvl, ptr, tl, me, spec, peers, where)
    SO, BLK = spec["so"], spec["block"]
    name = actor_name(spec)
    size = len(lvl)
    segs, CS, cmap = actor_segments(BLK, (), packed=False)
    L, end = actor_layout(size, SO, CS, len(name), len(s["backups"]), fail)
    fc = L["copy"]
    new = bytearray(lvl) + bytearray(end - size)
    # pointer ownership (G6-P1): in-block pointers owned; external ones model data shared with the other lums; the
    # transit parent an other-file pointer
    kinds = {o: "owned" for o in s["inner"]}
    kinds.update({o: "shared" for o in s["ext"]})
    kinds.update({SO + 0x14: "link", SO + 0x18: "link", SO + 0x1C: "other"})
    new_slots = actor_copy(new, lvl, s, SO, fc, segs, cmap, kinds, fail)
    for t in spec["translations"]:
        struct.pack_into(">3f", new, fc + t, *pos)
    reg, plan = actor_register(new, lvl, me, spec, s, L, name, lambda t: fc + cmap(t - SO))
    new_slots += reg
    for i, v in enumerate(pos):   # its own matrix-backup copy holds the new translation (words byte-swapped)
        new[L["backup_copy"] + 0x34 + 4 * i:L["backup_copy"] + 0x38 + 4 * i] = struct.pack(">f", v)[::-1]
    edits = apply_original_edits(lvl, new, plan, fail)
    nptr = extend_pointer_table(ptr, new_slots)
    W = spec["world"]
    ntl = bump_actor_count(tl, spec, s["world_count"], fail)
    new = bytes(new)
    verify_passive_lum(lvl, ptr, tl, new, nptr, ntl, me, spec, s, L, new_slots, edits, pos, where)
    info = {"objects": dict(L), "tail": end - size, "slots": len(new_slots), "edits": [label for _, label in edits],
            "personal_index": s["pcount"], "position": list(pos), "actors": s["world_count"] + 1,
            "records": len(s["records"]) + 1, "personal_types": s["pcount"] + 1, "transit_word": W + 0x10}
    return new, nptr, ntl, edits, info


def verify_passive_lum(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, spec, s, L, new_slots, edits, pos, where):
    """The simulator: the new files as the loader (own-file slot += area base, no checks; cross-file entries resolved
    by the transit file's first / last children) and the game's list walks would use them. Any difference from the
    planned structure refuses."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: simulated load: {why}")
    SO, BLK, MX = spec["so"], spec["block"], spec["matrix"]
    C = L["copy"]
    objects = [(C, BLK), (L["personal"], ACTOR_PERSONAL), (L["name"], L["record"] - L["name"]),
               (L["record"], ACTOR_RECORD), (L["backup"], ACTOR_BACKUP * len(s["backups"])),
               (L["backup_copy"], ACTOR_BACKUP_DATA)]
    slots, target = actor_verify_load(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, spec, s, objects, new_slots, edits,
                                      lambda o: o - C + SO if C <= o < C + BLK else None, fail)
    # the copy: rebased in-block pointers, the same external and other-file pointers as the source, own state
    for k in range(0, BLK, 4):
        so, co = SO + k, C + k
        if (so in s["slots"]) != (co in slots) or s["slots"].get(so) != slots.get(co):
            fail(f"the copy's pointer at +{k:#x}")
        if so in s["inner"] and (target(so) is None or target(co) != target(so) - SO + C):
            fail(f"the copy's in-block pointer at +{k:#x}")
        if so in s["ext"] and k not in (0x14, 0x18) and lvl[co:co + 4] != old_lvl[so:so + 4]:
            fail(f"the copy's shared pointer at +{k:#x}")
    if target(C + 0x18) != SO or any(target(o) is not None and SO <= target(o) < SO + BLK
                                     for o in range(C, C + BLK, 4) if o != C + 0x18):
        fail("the copy points into the source (other than its previous-sibling link)")
    std = s["std"] - SO + C
    if _u32(lvl, std + 8) != s["pcount"] or _u32(lvl, C + spec["buffer"]) != 0 \
            or any(lvl[C + t:C + t + 12] != struct.pack(">3f", *pos) for t in spec["translations"]):
        fail("the copy's personal index, 3dData buffer word or translation")
    actor_verify_lists(old_lvl, lvl, tl, me, spec, s, L, slots, target, lambda t: t - SO + C, std, fail)


def compile_insert_passive_lum(o: dict, paths) -> tuple:
    """G6-P1 (D-251): (ranges, transaction) of one insert-passive-lum: one level transaction of version 2 over the
    level file, its pointer table and transit.lvl. Ranges: the ten edited words, the appended tail, the whole rebuilt
    pointer table, transit's count word."""
    level = o["level"]
    where = f"insert-passive-lum {level} {o['model']!r} instance {o['instance']}"
    spec, allow = LUM_ALLOW.get(level), STRUCT_ALLOW.get(level)
    if spec is None or allow is None or not structural_enabled(level):
        raise Refusal("UNSUPPORTED", f"{where}: development-only, not enabled for this level")
    if o["model"] != spec["model"] or o["instance"] != spec["instance"]:
        raise Refusal("UNSUPPORTED", f"{where}: the development pilot supports only the verified source lum "
                                     f"(instance {spec['instance']} of {spec['model']!r})")
    inp = actor_level_inputs(o, paths, spec, allow, where)
    lvl, ptr, tl = inp["data"]["lvl"], inp["data"]["ptr"], inp["data"]["transit"]
    me, ix = inp["me"], inp["ix"]
    insts = ix["placements"].get(o["model"])
    if not insts or o["instance"] >= len(insts) or insts[o["instance"]]["so"] != spec["so"] \
            or insts[o["instance"]]["safe"]:
        raise Refusal("TARGET_CHANGED", f"{where}: the source actor is not the verified one")
    dsg = ix["defaults"].get(o["model"], {"vars": [], "instances": []})
    if dsg is None or dsg["vars"] or dsg["instances"] or model_sets_position(ix, o["model"]):
        raise Refusal("UNSUPPORTED", f"{where}: the model has designer variables or sets its own position (not a "
                                     "passive actor)")
    pos = struct.unpack(">3f", placement_bytes(o, where))
    anchors = lum_anchors(lvl, spec)
    near = [k for k, a in anchors.items() if math.dist(pos, a) <= spec["radius"]]
    if not near or not all(math.isfinite(v) for v in pos):
        raise Refusal("UNSUPPORTED", f"{where}: the position is not within {spec['radius']:g} unit(s) of an approved "
                                     f"position ({', '.join(sorted(anchors))})")
    peers = [i["so"] for n, i in enumerate(insts) if n != o["instance"]]
    new_lvl, new_ptr, new_tl, edits, info = build_passive_lum(lvl, ptr, tl, me, spec, peers, pos, where)
    info["anchor"] = near[0]
    return actor_transaction("insert-passive-lum", inp, new_lvl, new_ptr, new_tl, edits, info, where)


# G6-P2 (D-254): the development-only structural operation `insert-scripted-frog`: one additional, independent
# instance of intro_10's verified looping sound generator (instance 2 of NIK_mGenSound, `MAN_mGenSound_Frog`), G4c's
# construction (E-472 revision 1; functional closure E-474, D-241) owned by the compiler. It runs the game's own
# script (Init -> LoopOneShot); the only inputs are the verified source, its exact files, the placement preset
# (the source's own position, as verified) and the retrigger period (designer variable 5) from the two verified
# values. Off unless R3HD_DEV_STRUCTURAL_TX names the level; one version-2 level transaction (lvl, ptr, transit), the
# format G6-P1 introduced: every Frog change lies in those three files (the sound-event resolve table and the always
# list are in the level file), so no new transaction version is needed.
INSERT_FROG_KEYS = {"type", "level", "model", "instance", "lvl_sha256", "ptr_sha256", "transit_sha256", "placement",
                    "period_ms"}
FROG10 = "Gen_Sound\\NIK_mGenSound\\NIK_mGenSound.rul^CreateIntelligence^CreateComport:NIK_C_mGenSound_Init"
# level -> the verified G4c scenario (RE_NOTES "Level growth G4c" / "G4d-1", E-472 / E-474): the source block (0x520
# bytes, 19 in-block / 15 own-file external / 1 transit pointers), the blocks it owns (Brain, Mind, Intelligence,
# DsgMem and both designer buffers), its designer layout (sound-event words at 0 / 4 / 8 / 12, int variable 5 at 16,
# 30 bytes), the lists it is registered in (personal types, SO records, backups (four: three inline words and the
# matrix), the always-active list and its in-data owner header, the dynamic world), the level's sound-event resolve
# table (header pointer, the two group counts, 339 sorted file-domain words), the two known references from another
# actor's designer buffers (MAN_mGenManager_Frog's actor variable; it keeps naming the source), the new personal-type
# name (G4c's) and the verified periods (G4d-1: 500 and 2000 ms, each predicted and observed).
FROG_ALLOW = {"intro_10": {
    "transit": (41508, "d300ba3a4a3c03cec6a73eb9da8a8d820fcc3a669591e976b357e804315bf275"),
    "model": FROG10, "instance": 2, "so": 0x53BED0, "block": 0x520, "census": (19, 15, 1),
    "owned": (0x318, 0x324, 0x338, 0x490, 0x49C, 0x4BC), "dsgmem": 0x490, "buffers": (0x49C, 0x4BC),
    "dsg_length": 30, "events": (0, 4, 8, 12), "period_var": 16,
    "dsg_vars": ((0, 14), (4, 14), (8, 14), (12, 14), (29, 2), (16, 5), (28, 0), (20, 18), (24, 5)),
    "personal": 0x1C74, "records_ref": 0x1CFC, "records": 0x5A7434, "backups": 0x1CEC, "world": 0x9B4,
    "matrix": 0xC4, "backup_targets": (0x518, 0x514, 0x510, 0xC4),
    "always": 0x1CA8, "always_owner": 0x53A090,
    "resolve": {"ref": 0x1CE8, "groups": (0x1CE4, 0x1CE0), "count": 339},
    "foreign_refs": (0x53D2C0, 0x53D4CC),
    "new_name": b"MAN_mGenSound_Frog_G4C", "placements": ("at_source",), "periods": (500, 2000)}}
FROG_RECORD, FROG_BACKUP, FROG_BACKUP_DATA, FROG_PERSONAL, FROG_ALWAYS = (ACTOR_RECORD, ACTOR_BACKUP, ACTOR_BACKUP_DATA,
                                                                          ACTOR_PERSONAL, ACTOR_ALWAYS)


def parse_insert_scripted_frog(o: dict, where: str):
    if not structural_enabled():
        raise Refusal("UNSUPPORTED", f"{where}: insert-scripted-frog is a development-only structural operation "
                                     "(D-254) that this installation does not enable")
    if set(o) - INSERT_FROG_KEYS or INSERT_FROG_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: an insert-scripted-frog needs exactly {sorted(INSERT_FROG_KEYS)}")
    if not isinstance(o["level"], str) or not SCRIPT_LEVEL_RE.match(o["level"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'level' must be a level folder name such as intro_10")
    if o["level"] not in FROG_ALLOW:
        raise Refusal("UNSUPPORTED", f"{where}: level {o['level']} (the development pilot supports "
                                     f"{', '.join(sorted(FROG_ALLOW))})")
    if not isinstance(o["model"], str) or not 3 <= len(o["model"]) < 0x100 \
            or not all(32 <= ord(c) < 127 for c in o["model"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'model' must be the model's full first-behaviour name")
    if not isinstance(o["instance"], int) or isinstance(o["instance"], bool) or not 0 <= o["instance"] < 4096:
        raise Refusal("BAD_MANIFEST", f"{where}: 'instance' must be an index from script-info --model")
    for k in ("lvl_sha256", "ptr_sha256", "transit_sha256"):
        if not isinstance(o[k], str) or not re.match(r"^[0-9a-f]{64}$", o[k]):
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be the 64-digit SHA-256 of the level's original file")
    spec = FROG_ALLOW[o["level"]]
    if not isinstance(o["placement"], str) or o["placement"] not in spec["placements"]:
        raise Refusal("UNSUPPORTED", f"{where}: 'placement' must be one of {', '.join(spec['placements'])}")
    if not isinstance(o["period_ms"], int) or isinstance(o["period_ms"], bool) or o["period_ms"] not in spec["periods"]:
        raise Refusal("UNSUPPORTED", f"{where}: 'period_ms' must be one of the verified values "
                                     f"{', '.join(map(str, spec['periods']))}")


def _frog_source(lvl: bytes, ptr: bytes, tl: bytes, me: int, spec: dict, peers: list, foreign: list, where: str) -> dict:
    """Every original object the Frog insertion touches, each precondition checked against the ORIGINAL files (G4c's
    offline gate, owned here): the block's pointer census and owned sub-blocks, shared external pointers (model data
    of the other instances), the designer layout and buffers, the ten incoming references, the four lists plus the
    always-active list, and the sound-event resolve table."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: {why}")
    slots, cross, target, tail = actor_tables(lvl, ptr, tl, me, fail)
    SO, BLK, MX = spec["so"], spec["block"], spec["matrix"]
    if SO % 16 or SO + BLK > len(lvl) or _u32(lvl, SO) != 2:
        fail("the source is not an actor SuperObject")
    inner, ext, other = actor_census(lvl, slots, me, SO, BLK)
    if (len(inner), len(ext), len(other)) != spec["census"]:
        fail(f"the source block's pointers are {len(inner)} / {len(ext)} / {len(other)}, not the verified "
             f"{spec['census']}")
    if other != [SO + 0x1C] or _u32(lvl, SO + 0x1C) + 4 != spec["world"]:
        fail("the source's only other-file pointer is not its parent, the transit dynamic world")
    owned = {_u32(lvl, o) + 4 - SO for o in inner}
    if not set(spec["owned"]) <= owned:
        fail("the source does not own its Brain / Mind / Intelligence / DsgMem / designer buffers in its block")
    nxt, prv = actor_siblings(target, SO, fail)
    for o in ext:
        if o in (SO + 0x14, SO + 0x18):
            continue
        t = _u32(lvl, o) + 4
        if not any(slots.get(p + o - SO) == me and _u32(lvl, p + o - SO) + 4 == t for p in peers):
            fail(f"the source block's pointer at +{o - SO:#x} is not model data shared with another instance")
    if target(SO + 0x20) != SO + MX:
        fail("the source's matrix is not in its block")
    std = target(target(SO + 4) + 4) if target(SO + 4) is not None else None
    if std is None or not SO <= std < SO + BLK - 12 or std + 8 in slots:
        fail("the source's standard-game record is not in its block")
    # designer memory: DsgMem {-> model DsgVar (shared), -> initial, -> current}, both buffers referenced only there
    DM, (IB, CB), DL = SO + spec["dsgmem"], spec["buffers"], spec["dsg_length"]
    if target(DM + 4) != SO + IB or target(DM + 8) != SO + CB or DM in inner or DM not in ext:
        fail("the source's designer memory record")
    if any(SO + b + k in slots for b in (IB, CB) for k in range(0, DL + 2, 4)) or lvl[SO + IB:SO + IB + DL] != \
            lvl[SO + CB:SO + CB + DL]:
        fail("the source's designer buffers hold relocated words or differ in the file")
    # incoming references: two siblings, one SO record (+4), the always element (+0xC), the four backup records
    # (+8), and the known foreign designer references; nothing cross-file
    into = sorted(o for o in slots if slots[o] == me and not SO <= o < SO + BLK and SO <= _u32(lvl, o) + 4 < SO + BLK)
    if any((fa == me and SO <= oa + 4 < SO + BLK) or (fb == me and SO <= ob + 4 < SO + BLK) for oa, fa, ob, fb in cross):
        fail("the source is referenced from the cross-file table")
    if not set(spec["foreign_refs"]) <= set(into) or not all(any(a <= o < a + z for a, z in foreign)
                                                              for o in spec["foreign_refs"]):
        fail("the known references from another actor's designer buffers")
    rest = [o for o in into if o not in (nxt + 0x18, prv + 0x14) and o not in spec["foreign_refs"]]
    pels, pcount, k, tmpl, names = actor_personal_types(lvl, slots, target, tail, spec, std, False, fail)
    rl = actor_records(lvl, slots, target, tail, spec, fail)
    srecs = [r for r in rl if r + 4 in rest and target(r + 4) == SO]
    if len(srecs) != 1 or any(srecs[0] + q in slots for q in range(8, ACTOR_RECORD, 4)):
        fail("the source's SO record")
    links = actor_backup_links(target, tail, spec, fail)
    sbs, scopy = actor_backup_records(lvl, slots, target, links, spec, rest, "four", fail)
    al, sel_el = actor_always(lvl, slots, target, tail, spec, rest, True, fail)
    sel = [sel_el]
    if sorted(rest) != sorted([srecs[0] + 4, sel[0] + 0xC] + [sb + 8 for sb, _ in sbs]):
        fail("the source is referenced from data other than the verified ten references")
    # the sound-event resolve table: raw file-domain words (offset - 4), sorted, the source's type-14 words included
    R = spec["resolve"]
    ST = target(R["ref"])
    cnt = sum(_u32(lvl, g) for g in R["groups"])
    if ST is None or cnt != R["count"] or ST + 4 * cnt > len(lvl) or any(g in slots for g in R["groups"]) \
            or any(ST + 4 * i in slots for i in range(cnt)):
        fail("the sound-event resolve table")
    table = [_u32(lvl, ST + 4 * i) for i in range(cnt)]
    ev = [SO + b + e - 4 for b in (IB, CB) for e in spec["events"]]
    if table != sorted(table) or len(set(table)) != cnt or not set(ev) <= set(table) or max(table) + 4 >= len(lvl):
        fail("the sound-event resolve table's entries")
    wl, wcount = actor_world(tl, cross, target, spec, me, fail)
    return {"slots": slots, "cross": cross, "next": nxt, "prev": prv, "std": std, "pcount": pcount, "personal": pels,
            "template": tmpl, "srec": srecs[0], "records": rl, "links": links, "backups": sbs, "scopy": scopy,
            "always": al, "always_el": sel[0], "table": table, "table_at": ST, "events": ev, "walk": wl,
            "world_count": wcount, "inner": inner, "ext": ext}


def build_scripted_frog(lvl: bytes, ptr: bytes, tl: bytes, me: int, spec: dict, peers: list, foreign: list,
                        period: int, where: str) -> tuple:
    """(new .lvl, new .ptr, new transit.lvl, [(edited .lvl offset, label)], info): G4c's one additional Frog (E-472
    revision 1), every edited word asserted first. Appended: the copy (in the source's 16-byte phase; in-block
    pointers rebased so it owns its Brain / Mind / Intelligence / DsgMem / buffers; model pointers shared; its own
    personal index and designer variable 5 in both buffers), the personal element and name, the SO record, four
    backup records (source order) and the matrix copy, the always-active element, and a resolve table = the original
    entries + the copy's eight sound-event words (still sorted) that the level's table pointer moves to.
    verify_scripted_frog then re-checks the result as the loader and the game's list walks would see it."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: {why}")
    if period not in spec["periods"]:
        fail("the period is not a verified value")
    s = _frog_source(lvl, ptr, tl, me, spec, peers, foreign, where)
    SO, BLK = spec["so"], spec["block"]
    name = actor_name(spec)
    size = len(lvl)
    segs, CS, cmap = actor_segments(BLK, (), packed=False)
    L, end = actor_layout(size, SO, CS, len(name), len(s["backups"]), fail, always=True,
                          table_words=len(s["table"]) + len(s["events"]))
    fc = L["copy"]
    new = bytearray(lvl) + bytearray(end - size)
    put = lambda o, v: struct.pack_into(">I", new, o, v)   # noqa: E731
    # pointer ownership (G6-P2): in-block pointers owned (Brain / Mind / Intelligence / DsgMem / buffers); external
    # ones model data shared with the other GenSound actors; the transit parent an other-file pointer
    kinds = {o: "owned" for o in s["inner"]}
    kinds.update({o: "shared" for o in s["ext"]})
    kinds.update({SO + 0x14: "link", SO + 0x18: "link", SO + 0x1C: "other"})
    new_slots = actor_copy(new, lvl, s, SO, fc, segs, cmap, kinds, fail)
    for b in spec["buffers"]:
        struct.pack_into(">i", new, fc + b + spec["period_var"], period)
    reg, plan = actor_register(new, lvl, me, spec, s, L, name, lambda t: fc + cmap(t - SO))
    new_slots += reg
    # the resolve table (actor-specific: the Frog's sound-event fixups): original entries + the copy's sound-event
    # words (file domain), sorted order kept; the level's table pointer and group count move to it
    add = [e - SO + fc for e in s["events"]]
    table = s["table"] + add
    if table != sorted(table):
        fail("the extended resolve table would not stay sorted")
    for i, v in enumerate(table):
        put(L["table"] + 4 * i, v)
    R = spec["resolve"]
    plan += [(R["ref"], s["table_at"] - 4, L["table"] - 4, "resolve.table"),
             (R["groups"][1], _u32(lvl, R["groups"][1]), _u32(lvl, R["groups"][1]) + len(add), "resolve.count")]
    edits = apply_original_edits(lvl, new, plan, fail)
    nptr = extend_pointer_table(ptr, new_slots)
    W = spec["world"]
    ntl = bump_actor_count(tl, spec, s["world_count"], fail)
    new = bytes(new)
    verify_scripted_frog(lvl, ptr, tl, new, nptr, ntl, me, spec, s, L, new_slots, edits, period, where)
    info = {"objects": dict(L), "tail": end - size, "slots": len(new_slots), "edits": [label for _, label in edits],
            "personal_index": s["pcount"], "period_ms": period, "actors": s["world_count"] + 1,
            "records": len(s["records"]) + 1, "personal_types": s["pcount"] + 1, "always": len(s["always"]) + 1,
            "resolve_entries": len(table), "transit_word": W + 0x10}
    return new, nptr, ntl, edits, info


def verify_scripted_frog(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, spec, s, L, new_slots, edits, period, where):
    """The simulator: the new files as the loader (own-file slot += area base) and the game's list walks and the
    resolve-table parser (822A5918: each entry e -> the word at base + e) would use them. Any difference from the
    planned structure refuses."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: simulated load: {why}")
    SO, BLK, MX = spec["so"], spec["block"], spec["matrix"]
    C = L["copy"]
    tw = 4 * (len(s["table"]) + len(s["events"]))
    objects = [(C, BLK), (L["personal"], ACTOR_PERSONAL), (L["name"], L["record"] - L["name"]),
               (L["record"], ACTOR_RECORD), (L["backup"], ACTOR_BACKUP * len(s["backups"])),
               (L["backup_copy"], ACTOR_BACKUP_DATA), (L["always"], ACTOR_ALWAYS), (L["table"], tw)]
    slots, target = actor_verify_load(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, spec, s, objects, new_slots, edits,
                                      lambda o: o - C + SO if C <= o < C + BLK else None, fail)
    if any(L["table"] <= o < L["table"] + tw for _, o in new_slots):
        fail("a relocation slot inside the resolve table")
    # the copy: rebased in-block pointers (its own Brain / Mind / Intelligence / DsgMem / buffers), model pointers
    # shared, no pointer into the source except its previous-sibling link
    for k in range(0, BLK, 4):
        so, co = SO + k, C + k
        if (so in s["slots"]) != (co in slots) or s["slots"].get(so) != slots.get(co):
            fail(f"the copy's pointer at +{k:#x}")
        if so in s["inner"] and (target(so) is None or target(co) != target(so) - SO + C):
            fail(f"the copy's in-block pointer at +{k:#x}")
        if so in s["ext"] and k not in (0x14, 0x18) and lvl[co:co + 4] != old_lvl[so:so + 4]:
            fail(f"the copy's shared pointer at +{k:#x}")
    if target(C + 0x18) != SO or any(target(o) is not None and SO <= target(o) < SO + BLK
                                     for o in range(C, C + BLK, 4) if o != C + 0x18):
        fail("the copy points into the source (other than its previous-sibling link)")
    if not {target(o) - C for o in range(C, C + BLK, 4) if target(o) is not None and C <= target(o) < C + BLK} \
            >= set(spec["owned"]):
        fail("the copy does not own its Brain / Mind / Intelligence / DsgMem / buffers")
    DM, (IB, CB), DL = C + spec["dsgmem"], spec["buffers"], spec["dsg_length"]
    if target(DM) != target(SO + spec["dsgmem"]) or target(DM + 4) != C + IB or target(DM + 8) != C + CB:
        fail("the copy's designer memory record")
    pv = spec["period_var"]
    for b in (IB, CB):
        cb, sb = lvl[C + b:C + b + DL], old_lvl[SO + b:SO + b + DL]
        if struct.unpack_from(">i", cb, pv)[0] != period or cb[:pv] + cb[pv + 4:] != sb[:pv] + sb[pv + 4:] \
                or any(C + b + q in slots for q in range(0, DL + 2, 4)):
            fail("the copy's designer buffers")
    std = s["std"] - SO + C
    if _u32(lvl, std + 8) != s["pcount"] or lvl[C + MX:C + MX + 0x54] != old_lvl[SO + MX:SO + MX + 0x54]:
        fail("the copy's personal index or matrix")
    actor_verify_lists(old_lvl, lvl, tl, me, spec, s, L, slots, target, lambda t: t - SO + C, std, fail)
    # the resolve table as the parser walks it: every entry names a word in the level; the source's and the copy's
    # sound-event words each exactly once; nothing else of the copy
    R = spec["resolve"]
    ST, cnt = target(R["ref"]), sum(_u32(lvl, g) for g in R["groups"])
    tab = [_u32(lvl, ST + 4 * i) for i in range(cnt)] if ST is not None else []
    ce = [e - SO + C for e in s["events"]]
    if ST != L["table"] or cnt != len(s["table"]) + len(ce) or tab != s["table"] + ce \
            or any(not 0 <= e + 4 < len(lvl) for e in tab) or [e for e in tab if C <= e + 4 < C + BLK] != ce:
        fail("the sound-event resolve table")


def compile_insert_scripted_frog(o: dict, paths) -> tuple:
    """G6-P2 (D-254): (ranges, transaction) of one insert-scripted-frog: one level transaction of version 2 over the
    level file, its pointer table and transit.lvl. Ranges: the 17 edited words, the appended tail, the whole rebuilt
    pointer table, transit's count word."""
    level = o["level"]
    where = f"insert-scripted-frog {level} {o['model']!r} instance {o['instance']}"
    spec, allow = FROG_ALLOW.get(level), STRUCT_ALLOW.get(level)
    if spec is None or allow is None or not structural_enabled(level):
        raise Refusal("UNSUPPORTED", f"{where}: development-only, not enabled for this level")
    if o["model"] != spec["model"] or o["instance"] != spec["instance"]:
        raise Refusal("UNSUPPORTED", f"{where}: the development pilot supports only the verified source Frog "
                                     f"(instance {spec['instance']} of {spec['model']!r})")
    if o["placement"] not in spec["placements"] or o["period_ms"] not in spec["periods"]:
        raise Refusal("UNSUPPORTED", f"{where}: placement or period is not a verified preset")
    inp = actor_level_inputs(o, paths, spec, allow, where)
    lvl, ptr, tl = inp["data"]["lvl"], inp["data"]["ptr"], inp["data"]["transit"]
    me, ix = inp["me"], inp["ix"]
    insts = ix["placements"].get(o["model"])
    if not insts or o["instance"] >= len(insts) or insts[o["instance"]]["so"] != spec["so"] \
            or insts[o["instance"]]["safe"]:
        raise Refusal("TARGET_CHANGED", f"{where}: the source actor is not the verified one")
    dsg = ix["defaults"].get(o["model"])
    if not dsg or dsg["vars"] != list(spec["dsg_vars"]) or dsg["length"] != spec["dsg_length"] \
            or len(dsg["instances"]) != len(insts) or dsg["instances"][o["instance"]]["dsgmem"] != spec["so"] + spec["dsgmem"] \
            or [dsg["instances"][o["instance"]][k] for k in ("initial", "current")] != [spec["so"] + b for b in spec["buffers"]] \
            or dsg["instances"][o["instance"]]["safe"] or model_sets_position(ix, o["model"]):
        raise Refusal("UNSUPPORTED", f"{where}: the model's designer layout is not the verified one")
    peers = [i["so"] for n, i in enumerate(insts) if n != o["instance"]]
    foreign = [(inst[k], e["length"]) for key, e in ix["defaults"].items() if e and key != o["model"]
               for inst in e["instances"] for k in ("initial", "current") if isinstance(inst.get(k), int)]
    new_lvl, new_ptr, new_tl, edits, info = build_scripted_frog(lvl, ptr, tl, me, spec, peers, foreign, o["period_ms"],
                                                                where)
    return actor_transaction("insert-scripted-frog", inp, new_lvl, new_ptr, new_tl, edits, info, where)


# G6-P3 (D-256): the development-only structural operation `insert-fairy-on-graph`: one additional fairy light in
# intro_20 (a copy of instance 2 of NIN_m_FairyLight) whose designer variable 2 (type 20, a waypoint graph) REFERENCES
# an existing graph of the level, chosen symbolically as "the graph fairy instance N follows" (E-489: the fairy
# flies the graph its variable-2 word names; redirecting that word redirects the flight). The reference keeps its
# target's identity: the copy's two variable-2 words are own-file relocated words naming the existing graph (new
# `.ptr` slots, values = the graph's file offset - 4), never a copy of the graph. The source's own graph lies inside
# its block (+0x7B0..+0x9E4) and is NOT copied: those bytes stay zero in the copy and carry no relocation. Everything
# else follows G6-P1's lum recipe (siblings, personal type, SO record, matrix backup, transit's actor count) plus
# G6-P2's ownership checks (own Perso / 3dData / StdGame / Dynam / Brain / Mind / Intelligence / DsgMem / buffers).
# Off unless R3HD_DEV_STRUCTURAL_TX names the level; one version-2 level transaction (lvl, ptr, transit).
INSERT_FAIRY_KEYS = {"type", "level", "model", "instance", "lvl_sha256", "ptr_sha256", "transit_sha256",
                     "follow_graph_of"}
# level -> the verified G6-P3 scenario (E-489): the source (instance 2, SO, its 0xA4C-byte block to the next
# SuperObject with 78 in-block / 17 own-file external / 1 transit pointers), the objects it owns, its designer layout
# (variable 2 = the graph word at buffer offset 0; variable 0, a byte at 49), its own graph's region inside the block,
# the lists (as the lum), and the approved reference targets: follow_graph_of N -> the graph fairy instance N's
# variable 2 names, its file offset, node count and the instances that name it in the original file.
FAIRY_ALLOW = {"intro_20": {
    "transit": (26140, "51c0fbf1239acd6188316a6d64507761903d5a087df1ea717426d5cb810e6aa8"),
    "model": FAIRY20, "instance": 2, "so": 0x3358A0, "block": 0xA4C, "census": (78, 17, 1),
    "owned": (0x80, 0xAC, 0x2B4, 0x318, 0x5F8, 0x604, 0x618, 0x770, 0x77C, 0x9E4),
    "dsgmem": 0x770, "buffers": (0x77C, 0x9E4), "dsg_length": 50, "ref_word": 0, "start_byte": 49,
    "dsg_vars": ((49, 2), (48, 0), (0, 20), (4, 7), (8, 8), (20, 8), (32, 5), (36, 7), (40, 7), (44, 7)),
    "own_graph": 0x336050, "graph_region": (0x7B0, 0x9E4),
    "personal": 0x1C74, "records_ref": 0x1CFC, "records": 0x346960, "backups": 0x1CEC, "world": 0x9B4,
    "matrix": 0xC4, "buffer": 0x14C,
    "targets": {0: {"graph": 0x3226A8, "nodes": 5, "named_by": (0, 3)},
                1: {"graph": 0x335660, "nodes": 5, "named_by": (1, 7)}},
    "new_name": b"LLU_NIN_m_FairyLight_rose01_G6P3"}}
FAIRY_RECORD, FAIRY_BACKUP, FAIRY_BACKUP_DATA, FAIRY_PERSONAL = (ACTOR_RECORD, ACTOR_BACKUP, ACTOR_BACKUP_DATA,
                                                                  ACTOR_PERSONAL)
GRAPH_HEADER, GRAPH_NODE, GRAPH_WAYPOINT, GRAPH_ARCLIST, GRAPH_ARC = 0xC, 0x1C, 0x14, 0xC, 0x20


def parse_insert_fairy_on_graph(o: dict, where: str):
    if not structural_enabled():
        raise Refusal("UNSUPPORTED", f"{where}: insert-fairy-on-graph is a development-only structural operation "
                                     "(D-256) that this installation does not enable")
    if set(o) - INSERT_FAIRY_KEYS or INSERT_FAIRY_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: an insert-fairy-on-graph needs exactly {sorted(INSERT_FAIRY_KEYS)}")
    if not isinstance(o["level"], str) or not SCRIPT_LEVEL_RE.match(o["level"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'level' must be a level folder name such as intro_20")
    if o["level"] not in FAIRY_ALLOW:
        raise Refusal("UNSUPPORTED", f"{where}: level {o['level']} (the development pilot supports "
                                     f"{', '.join(sorted(FAIRY_ALLOW))})")
    if not isinstance(o["model"], str) or not 3 <= len(o["model"]) < 0x100 \
            or not all(32 <= ord(c) < 127 for c in o["model"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'model' must be the model's full first-behaviour name")
    if not isinstance(o["instance"], int) or isinstance(o["instance"], bool) or not 0 <= o["instance"] < 4096:
        raise Refusal("BAD_MANIFEST", f"{where}: 'instance' must be an index from script-info --model")
    for k in ("lvl_sha256", "ptr_sha256", "transit_sha256"):
        if not isinstance(o[k], str) or not re.match(r"^[0-9a-f]{64}$", o[k]):
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be the 64-digit SHA-256 of the level's original file")
    t = o["follow_graph_of"]
    if not isinstance(t, int) or isinstance(t, bool) or t not in FAIRY_ALLOW[o["level"]]["targets"]:
        raise Refusal("UNSUPPORTED", f"{where}: 'follow_graph_of' must name a fairy instance whose graph is a verified "
                                     f"reference target ({', '.join(map(str, FAIRY_ALLOW[o['level']]['targets']))})")


def _graph_objects(lvl: bytes, target, g: int, limit: int = 64):
    """{offset: (kind, size)} of one graph's objects (header, nodes, waypoints, arc lists, arcs) by the decoded
    layout (E-463 / E-464), or None when the node or arc chains do not decode."""
    objs = {g: ("graph", GRAPH_HEADER)}
    node, prev, n = target(g), None, 0
    while node is not None and n < limit:
        if node in objs or target(node + 8) != g or target(node + 4) != prev:
            return None
        objs[node] = ("node", GRAPH_NODE)
        w = target(node + 0xC)
        if w is None or w in objs:
            return None
        objs[w] = ("waypoint", GRAPH_WAYPOINT)
        al = target(node + 0x18)
        if al is not None:
            if al in objs:
                return None
            objs[al] = ("arclist", GRAPH_ARCLIST)
            a, k = target(al), 0
            while a is not None and k < 16:
                if a in objs:
                    return None
                objs[a] = ("arc", GRAPH_ARC)
                a, k = target(a), k + 1
        prev, node, n = node, target(node), n + 1
    if node is not None or n != _u32(lvl, g + 8) or target(g + 4) != prev:
        return None
    return objs


def _fairy_source(lvl: bytes, ptr: bytes, tl: bytes, me: int, spec: dict, peers: list, sel: int, named: dict,
                  where: str) -> dict:
    """Every original object the insertion touches, each precondition checked against the ORIGINAL files: the
    source block's pointer census, its owned objects, its own graph's region (exactly tiled by that graph's objects,
    referenced from outside the region only by the source's two variable-2 words), its designer buffers (the graph
    word the only relocated word, both buffers equal), its incoming references (siblings, one SO record, one backup),
    the lists, the transit dynamic world, and the selected reference target (the graph, its node count, exactly the
    references the allow-list names). `named` = {instance: (initial word offset, current word offset)} of every
    instance of the model."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: {why}")
    s = _lum_source(lvl, ptr, tl, me, dict(spec, translations=(spec["matrix"] + 0x34,)), peers, where)
    slots = s["slots"]

    def target(o):
        if slots.get(o) != me or o + 4 > len(lvl):
            return None
        t = _u32(lvl, o) + 4
        return t if t < len(lvl) else None
    SO, BLK = spec["so"], spec["block"]
    owned = {_u32(lvl, o) + 4 - SO for o in s["inner"]}
    if not set(spec["owned"]) <= owned:
        fail("the source does not own its Perso / 3dData / StdGame / Dynam / Brain / Mind / Intelligence / designer "
             "memory and buffers in its block")
    perso = target(SO + 4)
    brain = target(perso + 0xC) if perso is not None else None
    mind = target(brain) if brain is not None else None
    if perso != SO + 0x80 or mind is None or target(mind + 0xC) != SO + spec["dsgmem"] or target(perso) != SO + 0xAC \
            or target(perso + 8) != SO + 0x318 or brain != SO + 0x5F8 or target(mind + 4) != SO + 0x618:
        fail("the source's Perso / Brain / Mind / designer-memory chain is not the verified one")
    # designer memory and buffers: {-> model DsgVar (shared), -> initial, -> current}; the graph word is the only
    # relocated word of either buffer and names the source's own graph; both buffers equal in the file
    DM, (IB, CB), DL, RW = SO + spec["dsgmem"], spec["buffers"], spec["dsg_length"], spec["ref_word"]
    if target(DM + 4) != SO + IB or target(DM + 8) != SO + CB or DM in s["inner"] or DM not in s["ext"]:
        fail("the source's designer memory record")
    words = [SO + IB + RW, SO + CB + RW]
    for b in (IB, CB):
        if [o for o in range(SO + b, SO + b + DL) if o in slots] != [SO + b + RW] \
                or target(SO + b + RW) != spec["own_graph"]:
            fail("the source's designer buffers do not hold exactly one relocated word, its graph reference")
    if lvl[SO + IB:SO + IB + DL] != lvl[SO + CB:SO + CB + DL]:
        fail("the source's initial and current designer buffers differ in the file")
    # the source's own graph: inside its block, exactly the graph region, never pointed into from outside but by
    # the two variable-2 words; nothing in the region points outside it
    gl, gh = SO + spec["graph_region"][0], SO + spec["graph_region"][1]
    gobj = _graph_objects(lvl, target, spec["own_graph"])
    if gobj is None or min(gobj) != gl or max(o + z for o, (_, z) in gobj.items()) != gh \
            or sum(z for _, z in gobj.values()) != gh - gl:
        fail("the source's own graph does not exactly fill the region the copy leaves out")
    if any(gl <= o < gh and (target(o) is None or not gl <= target(o) < gh) for o in slots) \
            or any(gl <= o < gh and slots[o] != me for o in slots):
        fail("a word in the source's graph region points outside it")
    into_region = sorted(o for o in slots if not gl <= o < gh and target(o) is not None and gl <= target(o) < gh)
    if into_region != words:
        fail("the source's graph region is referenced by more than the source's two variable-2 words")
    # the selected reference target: the graph fairy instance `sel` follows; referenced from outside its own objects
    # by exactly the allow-listed instances' variable-2 words; a node count above the copy's variable 0 (a byte the
    # fairies' start values stay below; HYPOTHESIS: a start node index, E-489)
    tg = spec["targets"][sel]
    if sel not in named or [target(w) for w in named[sel]] != [tg["graph"]] * 2:
        fail(f"fairy instance {sel}'s variable 2 does not name the verified graph")
    tobj = _graph_objects(lvl, target, tg["graph"])
    if tobj is None or sum(1 for k, _ in tobj.values() if k == "node") != tg["nodes"]:
        fail("the target graph does not decode with the verified node count")
    inside = lambda o: any(a <= o < a + z for a, (_, z) in tobj.items())   # noqa: E731
    refs = sorted(o for o in slots if target(o) is not None and target(o) in tobj and not inside(o))
    if refs != sorted(w for n in tg["named_by"] for w in named[n]) \
            or any(target(o) != tg["graph"] for o in refs):
        fail("the target graph is referenced by more (or other) data than the verified fairies' variable 2")
    if any(target(o) is not None and not inside(target(o)) for o in slots if inside(o)):
        fail("the target graph points outside its own objects")
    if not lvl[SO + IB + spec["start_byte"]] < tg["nodes"]:
        fail("the target graph has fewer nodes than the copy's variable 0")
    s.update(perso=perso, mind=mind, words=words, region=(gl, gh), target_graph=tg["graph"],
             target_objects=sorted(tobj), target_refs=refs)
    return s


def build_fairy_on_graph(lvl: bytes, ptr: bytes, tl: bytes, me: int, spec: dict, peers: list, sel: int, named: dict,
                         where: str) -> tuple:
    """(new .lvl, new .ptr, new transit.lvl, [(edited .lvl offset, label)], info): one additional fairy light that
    follows an existing graph, every edited word asserted first. Appended after the file's end: the copy (in the
    source's 16-byte phase; in-block pointers rebased so it owns its Perso / 3dData / StdGame / Dynam / Brain / Mind /
    Intelligence / designer memory and buffers; model pointers shared; the graph region zero and unrelocated; both
    variable-2 words = the target graph, new own-file slots; its own personal index), the personal element and name,
    the SO record, the backup record and its matrix copy; linked after the source in the sibling chain and last in
    the three level lists; transit's dynamic-world count + 1. verify_fairy_on_graph re-checks the result."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: {why}")
    s = _fairy_source(lvl, ptr, tl, me, spec, peers, sel, named, where)
    SO, BLK = spec["so"], spec["block"]
    gl, gh = s["region"]
    name = actor_name(spec)
    size = len(lvl)
    segs, CS, cmap = actor_segments(BLK, [(gl - SO, gh - SO)], packed=False)   # the own graph left out (zero)
    L, end = actor_layout(size, SO, CS, len(name), len(s["backups"]), fail)
    fc = L["copy"]
    new = bytearray(lvl) + bytearray(end - size)
    # pointer ownership (G6-P3): in-block pointers owned; the two variable-2 words an explicit reference to the
    # target graph (kept identity, not rebased); external ones model data; the transit parent an other-file pointer
    kinds = {o: "owned" for o in s["inner"]}
    kinds.update({o: "shared" for o in s["ext"]})
    kinds.update({o: ("ref", s["target_graph"]) for o in s["words"]})
    kinds.update({SO + 0x14: "link", SO + 0x18: "link", SO + 0x1C: "other"})
    new_slots = actor_copy(new, lvl, s, SO, fc, segs, cmap, kinds, fail)
    reg, plan = actor_register(new, lvl, me, spec, s, L, name, lambda t: fc + cmap(t - SO))
    new_slots += reg
    edits = apply_original_edits(lvl, new, plan, fail)
    nptr = extend_pointer_table(ptr, new_slots)
    W = spec["world"]
    ntl = bump_actor_count(tl, spec, s["world_count"], fail)
    new = bytes(new)
    verify_fairy_on_graph(lvl, ptr, tl, new, nptr, ntl, me, spec, s, L, new_slots, edits, where)
    info = {"objects": dict(L), "tail": end - size, "slots": len(new_slots), "edits": [label for _, label in edits],
            "personal_index": s["pcount"], "actors": s["world_count"] + 1, "records": len(s["records"]) + 1,
            "personal_types": s["pcount"] + 1, "transit_word": W + 0x10, "follow_graph_of": sel,
            "target_graph": s["target_graph"], "reference_words": [w - SO + fc for w in s["words"]],
            "graph_region": [gl - SO + fc, gh - SO + fc]}
    return new, nptr, ntl, edits, info


def verify_fairy_on_graph(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, spec, s, L, new_slots, edits, where):
    """The simulator: the new files as the loader (own-file slot += area base; cross-file entries by the transit
    file's first / last children) and the game's list walks would use them, plus the reference: the copy's two
    variable-2 words name the target graph, which still decodes with its node count and is now named by its
    original fairies and the copy only. Any difference from the planned structure refuses."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: simulated load: {why}")
    SO, BLK, MX = spec["so"], spec["block"], spec["matrix"]
    C = L["copy"]
    objects = [(C, BLK), (L["personal"], ACTOR_PERSONAL), (L["name"], L["record"] - L["name"]),
               (L["record"], ACTOR_RECORD), (L["backup"], ACTOR_BACKUP * len(s["backups"])),
               (L["backup_copy"], ACTOR_BACKUP_DATA)]
    slots, target = actor_verify_load(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, spec, s, objects, new_slots, edits,
                                      lambda o: o - C + SO if C <= o < C + BLK else None, fail)
    gl, gh = s["region"]
    cl, chh = gl - SO + C, gh - SO + C
    words = [w - SO + C for w in s["words"]]
    TG = s["target_graph"]
    # the copy: graph region zero and unrelocated; reference words -> the target graph; other in-block pointers
    # rebased; external / other-file pointers as the source; nothing into the source but the previous-sibling link
    if lvl[cl:chh] != bytes(chh - cl) or any(cl <= o < chh for o in slots):
        fail("the copy's left-out graph region is not empty")
    for k in range(0, BLK, 4):
        so, co = SO + k, C + k
        if gl <= so < gh:
            continue
        if (so in s["slots"]) != (co in slots) or s["slots"].get(so) != slots.get(co):
            fail(f"the copy's pointer at +{k:#x}")
        if co in words:
            if target(co) != TG:
                fail(f"the copy's reference word at +{k:#x} does not name the target graph")
        elif so in s["inner"] and (target(so) is None or target(co) != target(so) - SO + C):
            fail(f"the copy's in-block pointer at +{k:#x}")
        elif so in s["ext"] and k not in (0x14, 0x18) and lvl[co:co + 4] != old_lvl[so:so + 4]:
            fail(f"the copy's shared pointer at +{k:#x}")
    if target(C + 0x18) != SO or any(target(o) is not None and SO <= target(o) < SO + BLK
                                     for o in range(C, C + BLK, 4) if o != C + 0x18):
        fail("the copy points into the source (other than its previous-sibling link)")
    if any(target(o) is not None and cl <= target(o) < chh for o in slots):
        fail("a pointer leads into the copy's left-out graph region")
    owned = {target(o) - C for o in range(C, C + BLK, 4) if target(o) is not None and C <= target(o) < C + BLK}
    if not owned >= set(spec["owned"]):
        fail("the copy does not own its Perso / Brain / Mind / Intelligence / designer memory and buffers")
    DM, (IB, CB), DL = C + spec["dsgmem"], spec["buffers"], spec["dsg_length"]
    if target(DM) != target(SO + spec["dsgmem"]) or target(DM + 4) != C + IB or target(DM + 8) != C + CB:
        fail("the copy's designer memory record")
    RW = spec["ref_word"]
    for b in (IB, CB):
        cb, sb = lvl[C + b:C + b + DL], old_lvl[SO + b:SO + b + DL]
        if cb[:RW] + cb[RW + 4:] != sb[:RW] + sb[RW + 4:] or [o for o in range(C + b, C + b + DL)
                                                             if o in slots] != [C + b + RW]:
            fail("the copy's designer buffers")
    std = s["std"] - SO + C
    if _u32(lvl, std + 8) != s["pcount"] or _u32(lvl, C + spec["buffer"]) != 0 \
            or lvl[C + MX:C + MX + 0x54] != old_lvl[SO + MX:SO + MX + 0x54]:
        fail("the copy's personal index, 3dData buffer word or matrix")
    # the reference target: unchanged objects, the same node walk, named by its original fairies and the copy only
    tobj = _graph_objects(lvl, target, TG)
    if tobj is None or sorted(tobj) != s["target_objects"] \
            or any(lvl[o:o + z] != old_lvl[o:o + z] for o, (_, z) in tobj.items()):
        fail("the target graph changed or no longer decodes")
    inside = lambda o: any(a <= o < a + z for a, (_, z) in tobj.items())   # noqa: E731
    refs = sorted(o for o in slots if target(o) is not None and target(o) in tobj and not inside(o))
    if refs != sorted(s["target_refs"] + words):
        fail("the target graph's references are not its original fairies' and the copy's")
    # the source keeps its own graph
    if [target(w) for w in s["words"]] != [spec["own_graph"]] * 2 or _graph_objects(lvl, target, spec["own_graph"]) \
            is None:
        fail("the source's own graph reference")
    actor_verify_lists(old_lvl, lvl, tl, me, spec, s, L, slots, target, lambda t: t - SO + C, std, fail)


def build_insert_fairy_on_graph(o: dict, paths) -> tuple:
    """G6-P3 (D-256) / G6-P20: the checked inputs and the built images of one insert-fairy-on-graph (shared by the
    standalone operation and the G6-P20 composition)."""
    level = o["level"]
    where = f"insert-fairy-on-graph {level} {o['model']!r} instance {o['instance']}"
    spec, allow = FAIRY_ALLOW.get(level), STRUCT_ALLOW.get(level)
    if spec is None or allow is None or not structural_enabled(level):
        raise Refusal("UNSUPPORTED", f"{where}: development-only, not enabled for this level")
    if o["model"] != spec["model"] or o["instance"] != spec["instance"]:
        raise Refusal("UNSUPPORTED", f"{where}: the development pilot supports only the verified source fairy "
                                     f"(instance {spec['instance']} of {spec['model']!r})")
    sel = o["follow_graph_of"]
    if sel not in spec["targets"]:
        raise Refusal("UNSUPPORTED", f"{where}: follow_graph_of {sel!r} is not a verified reference target")
    inp = actor_level_inputs(o, paths, spec, allow, where)
    lvl, ptr, tl = inp["data"]["lvl"], inp["data"]["ptr"], inp["data"]["transit"]
    me, ix = inp["me"], inp["ix"]
    insts = ix["placements"].get(o["model"])
    if not insts or o["instance"] >= len(insts) or insts[o["instance"]]["so"] != spec["so"] \
            or insts[o["instance"]]["safe"]:
        raise Refusal("TARGET_CHANGED", f"{where}: the source actor is not the verified one")
    dsg = ix["defaults"].get(o["model"])
    inst = dsg["instances"][o["instance"]] if dsg and o["instance"] < len(dsg["instances"]) else None
    if not dsg or [tuple(v) for v in dsg["vars"]] != list(spec["dsg_vars"]) or dsg["length"] != spec["dsg_length"] or len(dsg["instances"]) != len(insts) or inst is None \
            or inst["dsgmem"] != spec["so"] + spec["dsgmem"] \
            or [inst["initial"], inst["current"]] != [spec["so"] + b for b in spec["buffers"]] or inst["safe"]:
        raise Refusal("UNSUPPORTED", f"{where}: the model's designer layout is not the verified one")
    rv = dict(spec["dsg_vars"]).get(spec["ref_word"])
    if rv != GRAPH_TYPE:
        raise Refusal("UNSUPPORTED", f"{where}: the reference variable is not a graph variable")
    named = {n: (e["initial"] + spec["ref_word"], e["current"] + spec["ref_word"]) for n, e in enumerate(dsg["instances"])
             if isinstance(e.get("initial"), int) and isinstance(e.get("current"), int)}
    peers = [i["so"] for n, i in enumerate(insts) if n != o["instance"]]
    new_lvl, new_ptr, new_tl, edits, info = build_fairy_on_graph(lvl, ptr, tl, me, spec, peers, sel, named, where)
    return inp, new_lvl, new_ptr, new_tl, edits, info, where


def compile_insert_fairy_on_graph(o: dict, paths) -> tuple:
    """G6-P3 (D-256): (ranges, transaction) of one insert-fairy-on-graph: one level transaction of version 2 over
    the level file, its pointer table and transit.lvl. Ranges: the ten edited words, the appended tail, the whole
    rebuilt pointer table, transit's count word."""
    inp, new_lvl, new_ptr, new_tl, edits, info, where = build_insert_fairy_on_graph(o, paths)
    return actor_transaction("insert-fairy-on-graph", inp, new_lvl, new_ptr, new_tl, edits, info, where)


# ---------------------------------------------------------------------------------------------------------------
# G6-P20 (D-276): the development-only composition pilot `insert-fairy-with-terrain`: exactly the G6-P3 fairy insertion
# (intro_20, source instance 2, follow_graph_of 0 / 1) and exactly the G6-P19 terrain preset start-two-step-v1, in ONE
# version-2 level transaction. Both are built from the same original files, read and hash-checked once
# (actor_level_inputs); the terrain edit is computed from those original bytes by the unchanged collision_edit, must
# lie inside the original file, must not touch any word the fairy edits, any slot of the original or the rebuilt
# pointer table, and is laid over the fairy's image only where that image still holds the original bytes. The
# transaction's member images (and so its result hashes and identity) cover both. Anything else is refused whole.
INSERT_FAIRY_TERRAIN_KEYS = INSERT_FAIRY_KEYS | {"terrain_preset"}
FAIRY_TERRAIN_ALLOW = {"intro_20": ("start-two-step-v1",)}


def parse_insert_fairy_with_terrain(o: dict, where: str):
    if not structural_enabled():
        raise Refusal("UNSUPPORTED", f"{where}: insert-fairy-with-terrain is a development-only composition (D-276) "
                                     "that this installation does not enable")
    if set(o) - INSERT_FAIRY_TERRAIN_KEYS or INSERT_FAIRY_TERRAIN_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: an insert-fairy-with-terrain needs exactly "
                                      f"{sorted(INSERT_FAIRY_TERRAIN_KEYS)}")
    parse_insert_fairy_on_graph({k: v for k, v in o.items() if k != "terrain_preset"}, where)
    if o["level"] not in FAIRY_TERRAIN_ALLOW or o["terrain_preset"] not in FAIRY_TERRAIN_ALLOW[o["level"]]:
        raise Refusal("UNSUPPORTED", f"{where}: terrain_preset {o['terrain_preset']!r} (the composition pilot supports "
                                     f"{FAIRY_TERRAIN_ALLOW.get(o['level'], ())} on {o['level']})")


def compile_insert_fairy_with_terrain(o: dict, paths, terrain=None) -> tuple:
    """`terrain` (G6-P22, D-278): None = the fixed preset `terrain_preset` of `o`; else (collision_edit spec, name) of
    a validated terrain-patch-v1 (terrain_spec of its canonical form; `o` then carries no terrain_preset). Everything
    after the terrain spec is the same code for both."""
    level = o["level"]
    if terrain is None:
        if level not in FAIRY_TERRAIN_ALLOW or o["terrain_preset"] not in FAIRY_TERRAIN_ALLOW[level] \
                or not structural_enabled(level):
            raise Refusal("UNSUPPORTED", f"insert-fairy-with-terrain {level}: development-only, not enabled for this "
                                         "level")
        tspec, tname = COLLISION_ALLOW[level]["presets"][o["terrain_preset"]], o["terrain_preset"]
    else:
        if "terrain_preset" in o or level not in TERRAIN_REGIONS or level not in FAIRY_TERRAIN_ALLOW \
                or not structural_enabled(level):
            raise Refusal("UNSUPPORTED", f"insert-fairy-with-terrain {level}: development-only, not enabled for this "
                                         f"level (a private development compile needs {STRUCT_ENV}={level})")
        tspec, tname = terrain
    inp, new_lvl, new_ptr, new_tl, edits, info, where = build_insert_fairy_on_graph(
        {k: v for k, v in o.items() if k != "terrain_preset"}, paths)
    where = f"insert-fairy-with-terrain {level} {tname}"
    lvl, ptr = inp["data"]["lvl"], inp["data"]["ptr"]
    terr = collision_edit(lvl, ptr, level, tspec, where)
    fairy_words = {off for off, _ in edits}
    n = _u32(new_ptr, 0)
    new_slots = {struct.unpack_from(">iI", new_ptr, 4 + 8 * i)[1] + 4 for i in range(n)}
    final = bytearray(new_lvl)
    for off, data, w in terr:
        if off + len(data) > len(lvl):
            raise Refusal("STRUCTURE_CHECK", f"{where}: terrain {w} lies outside the original file")
        if any(f < off + len(data) and off < f + 4 for f in fairy_words):
            raise Refusal("STRUCTURE_CHECK", f"{where}: terrain {w} overlaps a word the fairy edits")
        if any(q in new_slots for q in range(off - 3, off + len(data))):
            raise Refusal("STRUCTURE_CHECK", f"{where}: terrain {w} touches a slot of the rebuilt pointer table")
        if new_lvl[off:off + len(data)] != lvl[off:off + len(data)]:
            raise Refusal("STRUCTURE_CHECK", f"{where}: terrain {w}: the fairy image does not hold the original bytes")
        final[off:off + len(data)] = data
    info["terrain"] = {"preset" if terrain is None else "patch": tname, "ranges": len(terr),
                       "bytes": sum(len(d) for _, d, _ in terr)}
    ranges, tx = actor_transaction("insert-fairy-with-terrain", inp, new_lvl, new_ptr, new_tl, edits, info, where)
    P = inp["paths"]
    ranges += [(P["lvl"], off, data, f"{level}:insert-fairy-with-terrain.terrain.{tname} {w}")
               for off, data, w in terr]
    tx["images"]["lvl"] = bytes(final)
    return ranges, tx


# G6-P21 (D-277): `level-patch-v1`, a strict declarative document for the one verified multi-component composition
# (intro_20: exactly one terrain component + exactly one FairyLight component, one owning mod, one version-2
# transaction). It is a thin typed adapter: the canonical document selects the inputs of the unchanged
# compile_insert_fairy_with_terrain (terrain preset; FairyLight follow_graph_of 0 = graph A 0x3226A8, 1 = graph B
# 0x335660, the two verified G6-P3 reference targets; source fairy fixed by FAIRY_ALLOW). No offsets, pointers, paths,
# actor types, counts or new graphs can be expressed. Components may appear in either order; the canonical form
# orders them terrain, fairylight. Development-only (R3HD_DEV_STRUCTURAL_TX), like the operation it selects.
LEVEL_PATCH_FORMAT = "level-patch-v1"
LEVEL_PATCH_KEYS = {"format", "level", "id", "lvl_sha256", "ptr_sha256", "transit_sha256", "components"}
LEVEL_PATCH_OPTIONAL = {"description"}
LEVEL_PATCH_COMPONENTS = {"terrain": {"type", "preset"}, "fairylight": {"type", "follow_graph_of"},
                          "route": {"type", "waypoints"}}
# G6-P22 (D-278): a terrain component is EITHER the fixed preset form above OR {"type": "terrain", "patch":
# <terrain-patch-v1>} -- an embedded declarative patch of one of the level's terrain regions (TERRAIN_REGIONS), same
# level and level file, no description of its own. Never both keys.
LEVEL_PATCH_TERRAIN_FORMS = ({"type", "preset"}, {"type", "patch"})
LEVEL_PATCH_ORDER = ("terrain", "fairylight", "route")
LEVEL_PATCH_REQUIRED = ("terrain", "fairylight")
LEVEL_PATCH_LEVELS = ("intro_20",)
# G6-P28 (D-284): an OPTIONAL third component {"type": "route", "waypoints": [{"node": N, "offset": [dx, dy, dz]},
# ...]} moves 1-6 waypoints of graph C, the loop FairyLight instance 2 flies on its own (0x336050, 6 nodes, owned by
# that instance alone: the D-231 waypoint-position rules accept every waypoint; read_graphs finds no other reference).
# Each offset is in level units from the ORIGINAL waypoint, Euclidean length above 0 and at most `max_move` (E-480:
# instance 2 passed within 0.20-0.27 of every original waypoint and within 0.22 of an inserted waypoint 6 units off
# its route). The new positions are compiled by the unchanged compile_waypoint_positions (identity = the verified
# original waypoint) and merged into the version-2 transaction under the terrain rule of G6-P20 (same size, original
# bytes in the FairyLight image, disjoint from every FairyLight / terrain range and from the rebuilt pointer table).
# The new FairyLight follows graph A or B and is not changed. A patch without a route compiles byte for byte as before.
LEVEL_PATCH_ROUTES = {"intro_20": {"model": FAIRY20, "instance": 2, "variable": 2, "graph": 0x336050, "nodes": 6,
                                   "max_move": 6.0, "name": "graph C",
                                   "flyer": "the loop of original FairyLight instance 2"}}


def parse_level_patch(p, where: str) -> dict:
    """Validate one level-patch-v1 object without game data; returns its canonical form. Refusal otherwise."""
    if not structural_enabled():
        why = level_patch_production(p)   # G6-P30 (D-286)
        if not why:
            with production_scope("intro_20"):
                return parse_level_patch(p, where)
        raise Refusal("UNSUPPORTED", f"{where}: development-only level patch: {why} (a private development compile "
                                     f"needs {STRUCT_ENV}=intro_20 in the environment)")
    if not structural_enabled():
        raise Refusal("UNSUPPORTED", f"{where}: level-patch is a development-only composition (D-277) that this "
                                     f"installation does not enable (a private development compile needs "
                                     f"{STRUCT_ENV}=intro_20 in the environment)")
    if not isinstance(p, dict):
        raise Refusal("BAD_MANIFEST", f"{where}: a level patch must be an object")
    if p.get("format") != LEVEL_PATCH_FORMAT:
        raise Refusal("UNSUPPORTED", f"{where}: format {p.get('format')!r} (supported: {LEVEL_PATCH_FORMAT})")
    if set(p) - LEVEL_PATCH_KEYS - LEVEL_PATCH_OPTIONAL or LEVEL_PATCH_KEYS - set(p):
        raise Refusal("BAD_MANIFEST", f"{where}: a level patch needs exactly {sorted(LEVEL_PATCH_KEYS)} (optional: "
                                      f"{sorted(LEVEL_PATCH_OPTIONAL)}); unknown: "
                                      f"{sorted(set(p) - LEVEL_PATCH_KEYS - LEVEL_PATCH_OPTIONAL)}, missing: "
                                      f"{sorted(LEVEL_PATCH_KEYS - set(p))}")
    level = p["level"]
    if level not in LEVEL_PATCH_LEVELS or level not in FAIRY_ALLOW or level not in FAIRY_TERRAIN_ALLOW:
        raise Refusal("UNSUPPORTED", f"{where}: level {level!r} (supported: {', '.join(LEVEL_PATCH_LEVELS)})")
    if not isinstance(p["id"], str) or not ID_RE.match(p["id"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'id' must be the owning mod's id (lowercase a-z 0-9 . _ -)")
    want = {"lvl_sha256": STRUCT_ALLOW[level]["lvl"][1], "ptr_sha256": STRUCT_ALLOW[level]["ptr"][1],
            "transit_sha256": FAIRY_ALLOW[level]["transit"][1]}
    for k, v in want.items():
        if not isinstance(p[k], str) or not re.match(r"^[0-9a-f]{64}$", p[k]):
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be the 64-digit lowercase SHA-256 of the original file")
        if p[k] != v:
            f_ = {"lvl_sha256": f"{level}.lvl", "ptr_sha256": f"{level}.ptr", "transit_sha256": "transit.lvl"}[k]
            raise Refusal("UNSUPPORTED", f"{where}: '{k}' is not the verified original {f_} of {level} (expected "
                                         f"{v[:8]}...; copy the source hashes from a supported example declaration)")
    if "description" in p and (not isinstance(p["description"], str) or len(p["description"]) > 200
                               or not all(32 <= ord(c) < 127 for c in p["description"])):
        raise Refusal("BAD_MANIFEST", f"{where}: 'description' must be at most 200 printable ASCII characters")
    comps = p["components"]
    if not isinstance(comps, list) or not comps:
        raise Refusal("BAD_MANIFEST", f"{where}: 'components' must be a non-empty list")
    seen = {}
    for i, c in enumerate(comps):
        w = f"{where}: components[{i}]"
        if not isinstance(c, dict) or "type" not in c:
            raise Refusal("BAD_MANIFEST", f"{w}: a component must be an object with a 'type'")
        t = c["type"]
        if t not in LEVEL_PATCH_COMPONENTS:
            raise Refusal("UNSUPPORTED", f"{w}: component type {t!r} (supported: {', '.join(LEVEL_PATCH_ORDER)})")
        if t == "terrain" and set(c) not in LEVEL_PATCH_TERRAIN_FORMS:
            raise Refusal("BAD_MANIFEST", f"{w}: a terrain component needs exactly ['preset', 'type'] or exactly "
                                          "['patch', 'type'] (never both)")
        if t != "terrain" and set(c) != LEVEL_PATCH_COMPONENTS[t]:
            raise Refusal("BAD_MANIFEST", f"{w}: a {t} component needs exactly {sorted(LEVEL_PATCH_COMPONENTS[t])}")
        if t in seen:
            raise Refusal("BAD_MANIFEST", f"{w}: a second {t} component (exactly one of each is allowed)")
        if t == "terrain" and "patch" in c:   # G6-P22 (D-278)
            tp = c["patch"]
            if not isinstance(tp, dict):
                raise Refusal("BAD_MANIFEST", f"{w}: 'patch' must be a terrain-patch-v1 object")
            if "description" in tp:
                raise Refusal("BAD_MANIFEST", f"{w}: an embedded terrain patch carries no description (the level "
                                              "patch has one)")
            if tp.get("level") != level:
                raise Refusal("UNSUPPORTED", f"{w}: the terrain patch's level {tp.get('level')!r} is not {level}")
            seen[t] = {"type": "terrain", "patch": parse_terrain_patch(tp, f"{w}.patch")}
            continue
        if t == "terrain" and c["preset"] not in FAIRY_TERRAIN_ALLOW[level]:
            raise Refusal("UNSUPPORTED", f"{w}: terrain preset {c['preset']!r} (supported on {level}: "
                                         f"{', '.join(FAIRY_TERRAIN_ALLOW[level])})")
        if t == "fairylight":
            g = c["follow_graph_of"]
            if not isinstance(g, int) or isinstance(g, bool) or g not in FAIRY_ALLOW[level]["targets"]:
                raise Refusal("UNSUPPORTED", f"{w}: follow_graph_of {g!r} (supported: " + ", ".join(
                    f"{k} = {LEVEL_PATCH_GRAPHS[level][k]}" for k in sorted(FAIRY_ALLOW[level]["targets"])) + ")")
        if t == "route":   # G6-P28 (D-284)
            seen[t] = parse_level_patch_route(c["waypoints"], level, w)
            continue
        seen[t] = dict(c)
    missing = [t for t in LEVEL_PATCH_REQUIRED if t not in seen]
    if missing:
        raise Refusal("BAD_MANIFEST", f"{where}: missing component(s) {missing}: the only supported composition is "
                                      "exactly one terrain + exactly one fairylight (+ at most one route)")
    canon = {k: p[k] for k in sorted(LEVEL_PATCH_KEYS | (LEVEL_PATCH_OPTIONAL & set(p))) if k != "components"}
    canon["components"] = [seen[t] for t in LEVEL_PATCH_ORDER if t in seen]
    return canon


def parse_level_patch_route(wps, level: str, where: str) -> dict:
    """G6-P28 (D-284): the canonical route component (waypoints sorted by node, offsets as floats) or a Refusal."""
    spec = LEVEL_PATCH_ROUTES.get(level)
    if spec is None:
        raise Refusal("UNSUPPORTED", f"{where}: no route is supported on {level}")
    if not isinstance(wps, list) or not 1 <= len(wps) <= spec["nodes"]:
        raise Refusal("BAD_MANIFEST", f"{where}: 'waypoints' must be a list of 1 to {spec['nodes']} moves")
    out = []
    for i, m_ in enumerate(wps):
        wi = f"{where}.waypoints[{i}]"
        if not isinstance(m_, dict) or set(m_) != {"node", "offset"}:
            raise Refusal("BAD_MANIFEST", f"{wi}: a move needs exactly ['node', 'offset']")
        n = m_["node"]
        if not isinstance(n, int) or isinstance(n, bool):
            raise Refusal("BAD_MANIFEST", f"{wi}: 'node' must be an integer")
        if not 0 <= n < spec["nodes"]:
            raise Refusal("UNSUPPORTED", f"{wi}: node {n} ({spec['name']} has nodes 0-{spec['nodes'] - 1})")
        d = m_["offset"]
        if not isinstance(d, list) or len(d) != 3 or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in d):
            raise Refusal("BAD_MANIFEST", f"{wi}: 'offset' must be [dx, dy, dz], three finite numbers")
        d = [float(v) for v in d]
        length = math.sqrt(sum(v * v for v in d))
        if length == 0.0:
            raise Refusal("BAD_MANIFEST", f"{wi}: the offset is zero (leave the waypoint out instead)")
        if length > spec["max_move"]:
            raise Refusal("UNSUPPORTED", f"{wi}: node {n} moves {length:.3f} units; {spec['name']} allows at most "
                                         f"{spec['max_move']:g} units from each original waypoint")
        out.append({"node": n, "offset": d})
    nodes = [m_["node"] for m_ in out]
    if len(set(nodes)) != len(nodes):
        raise Refusal("BAD_MANIFEST", f"{where}: node {next(n for n in nodes if nodes.count(n) > 1)} is moved twice")
    return {"type": "route", "waypoints": sorted(out, key=lambda m_: m_["node"])}


def level_patch_route_edits(canon: dict, paths, lvl: bytes) -> list:
    """G6-P28: [(offset, 12 bytes, label, (original xyz), (new xyz))] of a canonical patch's route ([] without one),
    built by the unchanged waypoint-position compiler on the verified original waypoints of `lvl`."""
    r = next((x for x in canon["components"] if x["type"] == "route"), None)
    if r is None:
        return []
    level = canon["level"]
    spec = LEVEL_PATCH_ROUTES[level]
    ix = read_script_index(paths["game"], level)
    if ix["data"] != lvl:
        raise Refusal("TARGET_CHANGED", f"level-patch {level}: the level file changed during the compile")
    entry = ix["graphs"].get((spec["model"], spec["instance"], spec["variable"]))
    if entry is None or entry["graph"] != spec["graph"] or len(entry["nodes"]) != spec["nodes"] or entry["safe"] \
            or entry["wsafe"]:
        raise Refusal("STRUCTURE_CHECK", f"level-patch {level}: {spec['name']} is not the verified graph")
    ovs, info = [], []
    for m_ in r["waypoints"]:
        w = entry["nodes"][m_["node"]][1]
        old = struct.unpack_from(">3f", lvl, w)
        new = struct.unpack(">3f", struct.pack(">3f", *(a + b for a, b in zip(old, m_["offset"]))))
        if not all(math.isfinite(v) for v in new):
            raise Refusal("UNSUPPORTED", f"level-patch {level}: node {m_['node']}: the moved waypoint is not finite")
        ovs.append({"type": "waypoint-position", "level": level, "model": spec["model"], "instance": spec["instance"],
                    "variable": spec["variable"], "node": m_["node"],
                    "waypoint_sha256": sha256_bytes(lvl[w:w + WAYPOINT_SIZE]), "position": list(new)})
        info.append((old, new))
    eds = compile_waypoint_positions(ovs, paths, {level: ix})
    return [(off, data, f"{spec['name']} node {m_['node']}", old, new)
            for (_, off, data, _), m_, (old, new) in zip(eds, r["waypoints"], info)]


def level_patch_identity(canon: dict) -> str:
    """SHA-256 of the canonical semantic content (the free-text description excluded)."""
    return sha256_bytes(json.dumps({k: v for k, v in canon.items() if k != "description"}, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8"))


def level_patch_operation(canon: dict) -> dict:
    """The insert-fairy-with-terrain operation a canonical level patch selects (validated by its own parser). With an
    embedded terrain patch (G6-P22) the operation carries no terrain_preset; its fairy part is validated alone."""
    c = {x["type"]: x for x in canon["components"]}
    spec = FAIRY_ALLOW[canon["level"]]
    o = {"type": "insert-fairy-with-terrain", "level": canon["level"], "model": spec["model"],
         "instance": spec["instance"], "lvl_sha256": canon["lvl_sha256"], "ptr_sha256": canon["ptr_sha256"],
         "transit_sha256": canon["transit_sha256"], "follow_graph_of": c["fairylight"]["follow_graph_of"]}
    if "patch" in c["terrain"]:
        if not structural_enabled():
            raise Refusal("UNSUPPORTED", "level-patch: development-only composition (D-278), not enabled")
        parse_insert_fairy_on_graph({**o, "type": "insert-fairy-on-graph"}, "level-patch")
        return o
    o["terrain_preset"] = c["terrain"]["preset"]
    parse_insert_fairy_with_terrain(o, "level-patch")
    return o


def level_patch_terrain(canon: dict):
    """None for the fixed preset form; else (collision_edit spec, name) of the embedded terrain patch (G6-P22)."""
    t = next(x for x in canon["components"] if x["type"] == "terrain")
    return (terrain_spec(t["patch"]), t["patch"]["name"]) if "patch" in t else None


def compile_level_patch(patch, paths, where="level-patch") -> tuple:
    """(canonical patch, ranges, transaction): the G6-P20 compiler on the selected operation (and, G6-P22, the
    embedded terrain patch's spec instead of the fixed preset). G6-P30 (D-286): without the development gate only a
    production-policy patch compiles (inside production_scope)."""
    if not structural_enabled():
        canon = parse_level_patch(patch, where)   # refuses anything outside the production policy
        with production_scope(canon["level"]):
            return compile_level_patch(canon, paths, where)
    canon = parse_level_patch(patch, where)
    ranges, tx = compile_insert_fairy_with_terrain(level_patch_operation(canon), paths, level_patch_terrain(canon))
    if any(x["type"] == "route" for x in canon["components"]):
        # G6-P28 (D-284): the G6-P20 terrain merge rule, applied to the route's waypoint words
        P = tx["files"]["lvl"][0]
        lvl = Path(P).read_bytes()
        if (len(lvl), sha256_bytes(lvl)) != tuple(tx["files"]["lvl"][1:]):
            raise Refusal("TARGET_CHANGED", f"{where}: the level file changed during the compile")
        route = level_patch_route_edits(canon, paths, lvl)
        w = f"{where}: route"
        taken = [(o, o + len(d)) for p, o, d, _ in ranges if Path(p) == Path(P)]
        new_ptr = tx["images"]["ptr"]
        n = _u32(new_ptr, 0)
        new_slots = {struct.unpack_from(">iI", new_ptr, 4 + 8 * i)[1] + 4 for i in range(n)}
        final = bytearray(tx["images"]["lvl"])
        for off, data, label, _, _ in route:
            if off + len(data) > len(lvl):
                raise Refusal("STRUCTURE_CHECK", f"{w}: {label} lies outside the original file")
            if any(a < off + len(data) and off < b for a, b in taken):
                raise Refusal("STRUCTURE_CHECK", f"{w}: {label} overlaps a FairyLight or terrain range")
            if any(q in new_slots for q in range(off - 3, off + len(data))):
                raise Refusal("STRUCTURE_CHECK", f"{w}: {label} touches a slot of the rebuilt pointer table")
            if final[off:off + len(data)] != lvl[off:off + len(data)]:
                raise Refusal("STRUCTURE_CHECK", f"{w}: {label}: the composed image does not hold the original bytes")
            final[off:off + len(data)] = data
            taken.append((off, off + len(data)))
        tx["images"]["lvl"] = bytes(final)
        tx["info"]["route"] = {"graph": LEVEL_PATCH_ROUTES[canon["level"]]["name"], "ranges": len(route)}
        ranges = ranges + [(P, off, data, f"{canon['level']}:level-patch.route.{label}")
                           for off, data, label, _, _ in route]
    return canon, ranges, tx


def parse_level_patch_override(o: dict, where: str):
    if set(o) != {"type", "patch"}:
        raise Refusal("BAD_MANIFEST", f"{where}: a level-patch override needs exactly ['patch', 'type']")
    parse_level_patch(o["patch"], where)


# G6-P24 (D-280): the level-patch preview report (`level-patch PATCH.json --check`). It adds no validation path of its
# own: a report exists only for a patch that compile_level_patch accepted (the parser, whole-deformation validators,
# conflict checks and transaction builder that --out uses), plus a standing-height prediction and the evidence status
# of the exact guest images. The prediction is the G6-P19 / G6-P22 method: the probe's measured height offset by the
# change of the collision plane under its (x, y); it is reported unavailable when that model does not apply.
LEVEL_PATCH_PROBE = {"intro_20": {
    # E-508 probe l1 (read-only, spread 0): Rayman's settled point on the unmodified level, on collision element 1
    # triangle 11, 0..0.02 above its plane
    "xyz": (-66.63662719726562, -64.2138671875, -25.077850341796875), "triangle": (1, 11), "gap": (0.0, 0.02),
    "source": "E-508 probe l1"}}
LEVEL_PATCH_GRAPHS = {"intro_20": {0: "graph A", 1: "graph B"}}
# G6-P26 (E-515 / D-282): further measured standing witnesses on the UNMODIFIED level (same model as the probe above);
# reported beside the spawn prediction, never replacing it. A modified height there is a prediction until measured.
LEVEL_PATCH_WITNESSES = {"intro_20": (
    {"name": "west floor", "xyz": (-75.43341064453125, -62.810546875, -25.212162017822266), "triangle": (1, 4),
     "gap": (0.0, 0.02), "source": "G6-P26 (E-515) run w2"},)}
LEVEL_PATCH_ADVICE = {   # author-facing advice of the level-patch command (codes unchanged)
    "BAD_MANIFEST": "The declaration does not follow level-patch-v1; start from a supported example "
                    "(docs/development/LEVEL_PATCH_AUTHORING.md).",
    "UNSUPPORTED": "The declaration asks for something the current authoring workflow does not support or enable; "
                   "the supported controls are listed in docs/development/LEVEL_PATCH_AUTHORING.md.",
    "TARGET_CHANGED": "Your game files or the declaration's source hashes are not the exact versions this workflow "
                      "supports, or the terrain failed a geometry check named above.",
    "TARGET_MISSING": "The intro_20 level files were not found under --game-dir (or the default game folder)."}
# guest images (lvl, ptr, transit result SHA-256) observed in the guest on a development build
LEVEL_PATCH_RUNTIME = (
    {"images": ("5cec9e4dbcd1d39377188898eab7970868ea0324aedb81ecd46885060576db48",
                "40934d08eeed74d87eb0dd385d82a7382cce6e2c53166083741be16d5ee8979c",
                "2be9a434eed49c9625efe0462a67510216813aff7edc3e75e4e083bff3a0a7e4"),
     "run": "G6-P23 (E-512) run m1", "settled_z": -25.1415,
     "observed": "63 / 63 ranges served, terrain and FairyLight words read back, FairyLight followed graph A"},
    {"images": ("4507437c0877ef21c933eec3aef72b64d558e9b5f26c2ef5dfbbcc0a0d267eda",
                "40934d08eeed74d87eb0dd385d82a7382cce6e2c53166083741be16d5ee8979c",
                "2be9a434eed49c9625efe0462a67510216813aff7edc3e75e4e083bff3a0a7e4"),
     "run": "G6-P20 (E-509) run m1", "settled_z": -25.2656,
     "observed": "63 / 63 ranges served, terrain words read back, FairyLight followed graph A"},
    {"images": ("086042dfecb2b2031d653170e8a85ab8d2266f8dbe151eee6f44cdd59bc842bd",
                "40934d08eeed74d87eb0dd385d82a7382cce6e2c53166083741be16d5ee8979c",
                "2be9a434eed49c9625efe0462a67510216813aff7edc3e75e4e083bff3a0a7e4"),
     "run": "G6-P27 (E-516) run m1", "settled_z": -25.3972,
     "observed": "55 / 55 ranges served, terrain and FairyLight words read back, Rayman walked to the west floor and "
                 "stood on the modified plane (residual 0.0001), FairyLight followed graph A"})


def collision_triangles(lvl: bytes, ptr: bytes, level: str) -> tuple:
    """(vertices, {(element, triangle): vertex indices}) of a level's allow-listed static collision mesh (the header
    fields collision_edit reads). Only used on files the compiler already accepted."""
    slots = {}
    for i in range(struct.unpack_from(">I", ptr, 0)[0]):
        f, loc = struct.unpack_from(">iI", ptr, 4 + 8 * i)
        slots[loc + 4] = f

    def P(o):
        if slots.get(o) != 1:
            raise Refusal("STRUCTURE_CHECK", f"{level}: expected a relocated pointer at 0x{o:X}")
        return struct.unpack_from(">I", lvl, o)[0] + 4
    Z = COLLISION_ALLOW[level]["zdr"]
    nv, ne = struct.unpack_from(">HH", lvl, Z)
    vo, eo = P(Z + 8), P(Z + 0x10)
    verts = [struct.unpack_from(">3f", lvl, vo + 12 * k) for k in range(nv)]
    tris = {}
    for i in range(ne):
        b = P(eo + 4 * i)
        nt = struct.unpack_from(">H", lvl, b + 0xC)[0]
        idx = struct.unpack_from(f">{3 * nt}H", lvl, P(b + 4))
        tris.update({(i, j): idx[3 * j:3 * j + 3] for j in range(nt)})
    return verts, tris


def collision_surface(verts, tris, x: float, y: float) -> list:
    """[(triangle, z of its plane at (x, y), normal z)] of the upward (normal z > 0.5) triangles over (x, y)."""
    out = []
    for t, (ia, ib, ic) in sorted(tris.items()):
        a, b, c = verts[ia], verts[ib], verts[ic]
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-9:
            continue
        l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / den
        l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / den
        l3 = 1 - l1 - l2
        n = _face(a, b, c)
        if min(l1, l2, l3) >= -1e-6 and n and n[2] > 0.5:
            out.append((t, l1 * a[2] + l2 * b[2] + l3 * c[2], n[2]))
    return out


def standing_prediction(level: str, lvl: bytes, ptr: bytes, edits, pr=None) -> dict:
    """Predicted settled z of the recorded standing probe (or witness `pr`, G6-P26) after same-size terrain `edits`
    [(offset, bytes)] of the original level file; {"available": False, "reason": ...} when the model does not apply."""
    pr = pr or LEVEL_PATCH_PROBE.get(level)
    if pr is None:
        return {"available": False, "reason": f"no verified standing probe is recorded for {level}"}
    x, y, z = pr["xyz"]
    probe = {"x": round(x, 4), "y": round(y, 4), "z": round(z, 4), "source": pr["source"],
             "triangle": list(pr["triangle"])}
    new = bytearray(lvl)
    for off, data in edits:
        new[off:off + len(data)] = data
    v0, tris = collision_triangles(lvl, ptr, level)
    v1, _ = collision_triangles(bytes(new), ptr, level)
    h0, h1 = collision_surface(v0, tris, x, y), collision_surface(v1, tris, x, y)
    want = "element {} triangle {}".format(*pr["triangle"])
    if [t for t, _, _ in h0] != [pr["triangle"]] or not pr["gap"][0] <= z - h0[0][1] < pr["gap"][1]:
        return {"available": False, "probe": probe, "reason": f"the unmodified level does not hold the recorded "
                f"standing surface ({want}, 0..{pr['gap'][1]} below the probe) under the probe"}
    if [t for t, _, _ in h1] != [pr["triangle"]]:
        return {"available": False, "probe": probe, "reason": f"after this edit the probe is over {len(h1)} upward "
                f"collision triangle(s), not only {want}: no single standing surface to predict from"}
    return {"available": True, "probe": probe, "probe_triangle_vertices": sorted(tris[pr["triangle"]]),
            "surface_z_original": round(h0[0][1], 4),
            "surface_z_patched": round(h1[0][1], 4), "surface_change": round(h1[0][1] - h0[0][1], 4),
            "normal_z_patched": round(h1[0][2], 4), "predicted_settled_z": round(h1[0][1] + (z - h0[0][1]), 4)}


def level_patch_preview(canon: dict, ranges: list, tx: dict, paths) -> dict:
    """The structured report of one accepted level patch (see the G6-P24 comment above)."""
    level = canon["level"]
    t = next(x for x in canon["components"] if x["type"] == "terrain")
    g = next(x for x in canon["components"] if x["type"] == "fairylight")["follow_graph_of"]
    lvl, ptr = (Path(tx["files"][k][0]).read_bytes() for k in ("lvl", "ptr"))
    if [(len(b), sha256_bytes(b)) for b in (lvl, ptr)] != [tx["files"][k][1:] for k in ("lvl", "ptr")]:
        raise Refusal("TARGET_CHANGED", f"level-patch {level}: the level files changed during the check")
    terr = [(o, d, w.split(" ", 1)[1]) for p, o, d, w in ranges
            if ".terrain." in w and Path(p) == Path(tx["files"]["lvl"][0])]
    tz = {"form": "patch" if "patch" in t else "preset"}
    if "patch" in t:
        tp, reg = t["patch"], TERRAIN_REGIONS[level][t["patch"]["region"]]
        tz.update({"name": tp["name"], "region": tp["region"],
                   "moved": {str(v): gr["delta_z"] for gr in tp["groups"] for v in gr["vertices"]},
                   "groups": tp["groups"],
                   "allowed": {"vertices": sorted(terrain_region(level, tp["region"])["vertices"]),
                               "delta_z": list(reg["delta_z"]), "groups": list(reg["groups"]),
                               "lowering_only": True, "min_ground_normal_z": reg["min_normal_z"],
                               "vertex_delta_z": {str(v): list(r_) for v, r_ in reg.get("vertex_delta_z", {}).items()}}})
    else:
        spec = COLLISION_ALLOW[level]["presets"][t["preset"]]
        tz.update({"name": t["preset"], "moved": {str(v): gr["dz"] for gr in spec["groups"] for v in gr["vertices"]},
                   "allowed": "a fixed verified preset (no parameters)"})
    nz = [struct.unpack(">3f", d)[2] for _, d, w in terr if re.match(r"^element \d+ triangle \d+ normal$", w)]
    tz.update({"collision_triangles": len(nz), "visual_vertices": sum(1 for *_, w in terr if w.startswith("visual vertex")),
               "collision_triangle_ids": [f"{a}/{b}" for a, b in sorted(
                   tuple(map(int, re.findall(r"\d+", w))) for *_, w in terr
                   if re.match(r"^element \d+ triangle \d+ normal$", w))],
               "visual_triangles": sum(1 for *_, w in terr if re.match(r"^visual element \d+ triangle \d+ normal$", w)),
               "lowest_ground_normal_z": round(min(nz), 4) if nz else None, "ranges": len(terr),
               "bytes": sum(len(d) for _, d, _ in terr),
               "checks": "passed: face / edge normal and edge scalar rules, no flip / degenerate / too-steep ground, "
                         "every known bound (octree root, IPO boxes, AABB copy), octree leaf membership, one visual "
                         "twin per moved vertex, visual / collision triangle pairing, no relocated word"})
    st = standing_prediction(level, lvl, ptr, [(o, d) for o, d, _ in terr])
    if st["available"]:
        z0 = st["probe"]["z"]
        st["moved_vertices_on_probe_triangle"] = sorted(int(v) for v in tz["moved"]
                                                        if int(v) in st["probe_triangle_vertices"])
        ref = FAIRY_TERRAIN_ALLOW[level][0]
        rr = standing_prediction(level, lvl, ptr, [(o, d) for o, d, _ in
                                                   collision_edit(lvl, ptr, level, COLLISION_ALLOW[level]["presets"][ref],
                                                                  f"reference {ref}")])
        st["compared"] = {"unmodified": {"z": z0, "difference": round(st["predicted_settled_z"] - z0, 4)}}
        if rr["available"]:
            st["compared"][ref] = {"z": rr["predicted_settled_z"],
                                   "difference": round(st["predicted_settled_z"] - rr["predicted_settled_z"], 4)}
    wits = []
    for w_ in LEVEL_PATCH_WITNESSES.get(level, ()):   # G6-P26: measured original, predicted modified
        p_ = standing_prediction(level, lvl, ptr, [(o, d) for o, d, _ in terr], w_)
        p_["name"] = w_["name"]
        if p_["available"]:
            p_["moved_vertices_on_witness_triangle"] = sorted(int(v) for v in tz["moved"]
                                                              if int(v) in p_["probe_triangle_vertices"])
        wits.append(p_)
    images = tuple(sha256_bytes(tx["images"][k]) for k in ("lvl", "ptr", "transit"))
    seen = next((r for r in LEVEL_PATCH_RUNTIME if r["images"] == images), None)
    ev = {"target_resources": "VERIFIED: the level files are the exact original versions this composition supports",
          "offline": "VERIFIED by the compiler: schema, whole-deformation validators, FairyLight composition and "
                     "conflict checks, one atomic version-2 transaction",
          "standing_height": ("PREDICTED from the collision plane under the probe (not measured)" if st["available"]
                              else "UNAVAILABLE: " + st["reason"]),
          "runtime": (f"OBSERVED for these exact guest images: {seen['run']} ({seen['observed']}; settled z "
                      f"{seen['settled_z']})" if seen else
                      "UNTESTED: these exact guest images have not run in the guest")}
    prod_why = level_patch_production(canon)   # G6-P30 (D-286)
    rc = next((x for x in canon["components"] if x["type"] == "route"), None)
    route = None
    if rc is not None:   # G6-P28 (D-284)
        rs, img = LEVEL_PATCH_ROUTES[level], tx["images"]["lvl"]
        rr_ = [r_ for r_ in ranges if ".route." in r_[3] and Path(r_[0]) == Path(tx["files"]["lvl"][0])]
        moves = []
        for (_, o, d, _), m_ in zip(rr_, rc["waypoints"]):
            old, new = struct.unpack_from(">3f", lvl, o), struct.unpack_from(">3f", img, o)
            moves.append({"node": m_["node"], "offset": m_["offset"], "distance": round(math.dist(old, new), 4),
                          "original": [round(v, 4) for v in old], "new": [round(v, 4) for v in new]})
        route = {"graph": rs["name"], "graph_offset": f"0x{rs['graph']:X}", "flyer": rs["flyer"],
                 "nodes": rs["nodes"], "max_move": rs["max_move"], "moves": moves, "ranges": len(rr_),
                 "prediction": "the fairy flies its loop 0 -> 1 -> ... -> 5 -> 0 through the moved waypoints "
                               "(PREDICTED; E-480: within 0.20-0.27 of every original waypoint, 0.22 of a waypoint "
                               "inserted 6 units off the route)"}
        ev["route"] = ("SUPPORTED, not run: the waypoint words are the verified D-231 waypoint-position edit; the loop "
                       "and its owner were measured in E-480; flight through moved waypoints is predicted")
    lim = ["intro_20 only: one terrain component + one FairyLight; no other actors, levels or graphs" if rc is None
           else "intro_20 only: one terrain component + one FairyLight + graph C's waypoints; no other actors, levels "
                "or graphs, no new nodes",
           "the intro_20 terrain is not framebuffer-attributed (drawn change unverified)"]
    if rc is not None:
        lim.append("route: graph C is flown by an original fairy (instance 2), not by the added FairyLight; moved "
                   "waypoints are not checked against level geometry, visibility or the camera")
    if "patch" in t and set(TERRAIN_REGIONS[level][t["patch"]["region"]].get("extra", {})) & set(map(int, tz["moved"])):
        lim.append(TERRAIN_REGIONS[level][t["patch"]["region"]]["note"])
    if g != 0:
        lim.append("graph B combined with terrain is offline-verified only (graph B alone ran in G6-P3 run C)")
    if wits:
        ev["witness_heights"] = ("original surface MEASURED at " + ", ".join(f"{x['name']} ({x['probe']['source']})"
                                 for x in wits if x["available"]) + "; modified heights PREDICTED")
    out = {"verdict": "valid", "terrain": tz, "standing": st, "witnesses": wits,
           "fairylight": {"follow_graph_of": g, "graph": LEVEL_PATCH_GRAPHS[level][g],
                          "graph_offset": f"0x{FAIRY_ALLOW[level]['targets'][g]['graph']:X}",
                          "source_instance": FAIRY_ALLOW[level]["instance"]},
           "sources": {k: {"file": Path(tx["files"][k][0]).name, "size": tx["files"][k][1],
                           "sha256": tx["files"][k][2]} for k in ("lvl", "ptr", "transit")},
           "authorization": ({"development_only": True, "compile_gate": f"{STRUCT_ENV}={level}",
                              "runtime": "needs a development runtime build; the production runtime refuses level "
                                         "transactions"} if prod_why or structural_enabled_env() else
                             {"development_only": False, "production_policy": "D-286",
                              "runtime": "accepted by a production runtime build only if its images meet the "
                                         "production content policy (pinned results, FairyLight-A base, terrain "
                                         "windows)"}),
           "production": {"eligible": not prod_why, "reason": prod_why or "start-floor terrain + FairyLight graph A"},
           "evidence": ev, "runtime_observed": seen is not None, "limitations": lim}
    if route is not None:
        out["route"] = route
    return out


def level_patch_text(r: dict, source: str) -> str:
    """Concise human-readable form of a level-patch result or refusal."""
    if r["result"] != "ok":
        return (f"level-patch {source}: REFUSED ({r['code']})\n  {r['detail']}\n"
                + (f"  {r['advice']}\n" if r.get("advice") else "") + "  Nothing was written.\n")
    p, pv, tx = r["patch"], r["preview"], r["transaction"]
    tz, st, fl = pv["terrain"], pv["standing"], pv["fairylight"]
    wrote = (f"wrote mod folder {r['mod']['folder']} (mod id {r['mod']['id']})" if "mod" in r else
             "nothing written" + ("" if r.get("check") else "; add --out DIR to write a mod folder"))
    moved = ", ".join(f"vertex {v} {dz:+.2f}" for v, dz in sorted(tz["moved"].items(), key=lambda x: int(x[0])))
    if tz["form"] == "patch":
        a = tz["allowed"]
        terr = (f"{tz['name']} (region {tz['region']}): {moved}\n"
                f"               allowed: vertices {' '.join(map(str, a['vertices']))}, lowering "
                f"{-a['delta_z'][1]:.2f}..{-a['delta_z'][0]:.2f}"
                + "".join(f" (vertex {v}: {-r_[1]:.2f}..{-r_[0]:.2f})" for v, r_ in a.get("vertex_delta_z", {}).items())
                + f", {a['groups'][0]}-{a['groups'][1]} groups")
    else:
        terr = f"preset {tz['name']}: {moved}"
    if st["available"]:
        cmp_ = "; ".join(f"{k} {v['z']:.4f}: {v['difference']:+.4f}" for k, v in st.get("compared", {}).items())
        on = st["moved_vertices_on_probe_triangle"]
        stand = (f"Rayman settles at z {st['predicted_settled_z']:.4f} (predicted; {cmp_})\n"
                 f"               he stands on collision triangle {'/'.join(map(str, st['probe']['triangle']))} "
                 f"(vertices {' '.join(map(str, st['probe_triangle_vertices']))}): "
                 + (f"moved vertex {' '.join(map(str, on))} sets his height" if on else
                    "none of the moved vertices changes his height"))
    else:
        stand = f"prediction unavailable: {st['reason']}"
    g = r["growth"]
    m = tx["members"]
    lines = [f"level-patch {source}: VALID ({wrote})",
             f"  declaration  {p['id']}  identity {p['identity_sha256'][:16]}",
             f"  target       {p['level']}: " + ", ".join(f"{s['file']} {s['sha256'][:8]}" for s in pv["sources"].values())
             + " (exact originals)",
             f"  terrain      {terr}",
             f"               geometry checks passed: {tz['collision_triangles']} collision triangles, "
             f"{tz['visual_vertices']} visual vertices / {tz['visual_triangles']} visual triangles, lowest ground "
             f"normal z {tz['lowest_ground_normal_z']}",
             f"               edited collision triangles: {' '.join(tz['collision_triangle_ids'])}",
             f"  standing     {stand}",
             *[(f"  {w_['name']:<12} z {w_['predicted_settled_z']:.4f} (predicted; measured original {w_['probe']['z']:.4f}, "
                f"{w_['probe']['source']}, triangle {'/'.join(map(str, w_['probe']['triangle']))}): "
                + (f"moved vertex {' '.join(map(str, w_['moved_vertices_on_witness_triangle']))} changes it"
                   if w_['moved_vertices_on_witness_triangle'] else "no moved vertex changes it"))
               if w_["available"] else f"  {w_['name']:<12} prediction unavailable: {w_['reason']}"
               for w_ in pv.get("witnesses", [])],
             f"  fairylight   follows {fl['graph']} (follow_graph_of {fl['follow_graph_of']})",
             *([f"  route        {pv['route']['graph']} ({pv['route']['flyer']}): "
                + "; ".join(f"node {m_['node']} moved {m_['distance']:.3f} to ({', '.join(f'{v:.3f}' for v in m_['new'])})"
                            for m_ in pv["route"]["moves"]),
                f"               allowed: nodes 0-{pv['route']['nodes'] - 1}, at most {pv['route']['max_move']:g} units "
                f"each; {pv['route']['prediction']}"] if "route" in pv else []),
             f"  transaction  level-tx v{tx['version']} {tx['id']}: {r['range_count']} ranges "
             f"({r['terrain_ranges']} terrain + {r['fairylight_ranges']} FairyLight"
             + (f" + {r['route_ranges']} route)" if "route_ranges" in r else ")"),
             "               " + ", ".join(f"{k} {m[k]['size']:,} -> {m[k]['guest_size']:,} ({g[k]:+,})"
                                           for k in ("lvl", "ptr", "transit")),
             (f"  gate         development only ({pv['authorization']['compile_gate']}); "
              f"{pv['authorization']['runtime']}" if pv["authorization"]["development_only"] else
              f"  gate         production policy D-286: {pv['authorization']['runtime']}"),
             "  gameplay     yes: changes the level's ground and adds an actor"
             + ("; moves an original fairy's route" if "route" in pv else ""),
             f"  runtime      {pv['evidence']['runtime']}"]
    lines += [f"  limit        {x}" for x in pv["limitations"]]
    return "\n".join(lines) + "\n"


def transaction_summary(mod_id: str, tx: dict) -> dict:
    """The plan writer's member results and identifier of one built transaction (same formula as write_plan_files)."""
    members = []
    for role, (p, size, orig) in sorted(tx["files"].items()):
        img = tx["images"][role]
        members.append((role, Path(p).name, size, orig, len(img), sha256_bytes(img)))
    v = tx.get("version", TX_VERSION)
    return {"version": v, "id": tx_id(tx["level"], mod_id, members, v),
            "members": {r: {"size": s, "guest_size": g, "result_sha256": h} for r, _, s, _, g, h in members}}


# G6-P4 (D-257): the development-only structural operation `insert-gensound-manager`: one additional sound manager
# in intro_10 (a copy of `MAN_mGenManager_Frog`, the only NIK_mGenManager instance) whose designer variable 0 (type
# 18, an actor) REFERENCES an existing NIK_mGenSound actor chosen symbolically (`moves_gensound_instance` 0 = the
# Forest ambience 0x53A09C, 1 = SmallRiver 0x53B9B0). E-490: the manager's behaviour GestionType_0 moves the actor its
# v0 names onto the waypoint of its graph that value call 0xAD picks (procedure 219); redirecting v0 redirects the
# move. The source's block also stores its MODEL (AI model, DsgVar, behaviours and scripts, +0x338..+0xD6C) and its
# GRAPH (+0xEF0..+0x10DC): the copy shares both (every pointer into them keeps its original target) and leaves both
# regions out (zero, unrelocated). v0 names the chosen actor (two new own-file slots naming an EXISTING actor).
# Lists as G6-P2's Frog (siblings, personal type, SO record, three backups (two inline, the matrix), the always-active
# list) and transit's actor count; no sound-event words. Off unless R3HD_DEV_STRUCTURAL_TX names the level.
INSERT_GMGR_KEYS = {"type", "level", "model", "instance", "lvl_sha256", "ptr_sha256", "transit_sha256",
                    "moves_gensound_instance"}
GM10 = "Gen_Sound\\NIK_mGenManager\\NIK_mGenManager.rul^CreateIntelligence^CreateComport:NIK_C_mGenManager_Init"
GMGR_ALLOW = {"intro_10": {
    "transit": (41508, "d300ba3a4a3c03cec6a73eb9da8a8d820fcc3a669591e976b357e804315bf275"),
    "model": GM10, "instance": 0, "so": 0x53C3F0, "block": 0x11E4, "census": (96, 11, 2),
    "other": ((0x1C, 2), (0xB6C, 0)),
    "regions": {"model": (0x338, 0xD6C), "graph": (0xEF0, 0x10DC)},
    "kept": (0x324, 0xD6C, 0xD74, 0xD78, 0xD80, 0xEC4, 0xED4, 0x10E0),
    "owned": (0x80, 0xAC, 0x2B4, 0x318, 0x324, 0xD6C, 0xEC4, 0xED0, 0x10DC, 0x10FC, 0x11B0, 0x11BC),
    "dsgmem": 0xEC4, "buffers": (0xED0, 0x10DC), "dsg_length": 30, "ref_word": 0, "graph_word": 4,
    "dsg_vars": ((0, 18), (29, 2), (4, 20), (28, 2), (8, 19), (12, 18), (16, 8)),
    "own_target": 0x53BED0, "graph": 0x53D2E0, "graph_nodes": 8, "target_model": FROG10,
    "targets": {0: 0x53A09C, 1: 0x53B9B0},
    "personal": 0x1C74, "records_ref": 0x1CFC, "records": 0x5A7434, "backups": 0x1CEC, "world": 0x9B4,
    "matrix": 0xC4, "buffer": 0x14C, "backup_targets": (0x113C, 0x113E, 0xC4),
    "always": 0x1CA8, "always_owner": 0x53A090, "new_name": b"MAN_mGenManager_Frog_G6P4"}}


def parse_insert_gensound_manager(o: dict, where: str):
    if not structural_enabled():
        raise Refusal("UNSUPPORTED", f"{where}: insert-gensound-manager is a development-only structural operation "
                                     "(D-257) that this installation does not enable")
    if set(o) - INSERT_GMGR_KEYS or INSERT_GMGR_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: an insert-gensound-manager needs exactly {sorted(INSERT_GMGR_KEYS)}")
    if not isinstance(o["level"], str) or not SCRIPT_LEVEL_RE.match(o["level"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'level' must be a level folder name such as intro_10")
    if o["level"] not in GMGR_ALLOW:
        raise Refusal("UNSUPPORTED", f"{where}: level {o['level']} (the development pilot supports "
                                     f"{', '.join(sorted(GMGR_ALLOW))})")
    if not isinstance(o["model"], str) or not 3 <= len(o["model"]) < 0x100 \
            or not all(32 <= ord(c) < 127 for c in o["model"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'model' must be the model's full first-behaviour name")
    if not isinstance(o["instance"], int) or isinstance(o["instance"], bool) or not 0 <= o["instance"] < 4096:
        raise Refusal("BAD_MANIFEST", f"{where}: 'instance' must be an index from script-info --model")
    for k in ("lvl_sha256", "ptr_sha256", "transit_sha256"):
        if not isinstance(o[k], str) or not re.match(r"^[0-9a-f]{64}$", o[k]):
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be the 64-digit SHA-256 of the level's original file")
    t = o["moves_gensound_instance"]
    if not isinstance(t, int) or isinstance(t, bool) or t not in GMGR_ALLOW[o["level"]]["targets"]:
        raise Refusal("UNSUPPORTED", f"{where}: 'moves_gensound_instance' must name a verified target actor "
                                     f"({', '.join(map(str, GMGR_ALLOW[o['level']]['targets']))})")


def _gmgr_source(lvl: bytes, ptr: bytes, tl: bytes, me: int, spec: dict, peers: list, sel: int, foreign: list,
                 where: str) -> dict:
    """Every original object the insertion touches, each precondition checked against the ORIGINAL files: the block's
    pointer census, its owned objects, its shared regions (model and graph: closed, referenced from outside only by
    the verified kept words), its designer buffers (v0 -> the Frog, v2 -> the graph, nothing else relocated), its
    incoming references (siblings, one SO record, three backups, one always-active element), the four lists, the
    transit dynamic world, and the selected target (an actor no designer buffer names)."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: {why}")
    slots, cross, target, tail = actor_tables(lvl, ptr, tl, me, fail)
    SO, BLK, MX = spec["so"], spec["block"], spec["matrix"]
    if SO % 16 or SO + BLK > len(lvl) or _u32(lvl, SO) != 2:
        fail("the source is not an actor SuperObject")
    regions = [(SO + a, SO + b) for a, b in spec["regions"].values()]
    inreg = lambda o: any(a <= o < b for a, b in regions)   # noqa: E731
    inner, ext, other = actor_census(lvl, slots, me, SO, BLK)
    if (len(inner), len(ext), len(other)) != spec["census"]:
        fail(f"the source block's pointers are {len(inner)} / {len(ext)} / {len(other)}, not the verified "
             f"{spec['census']}")
    if sorted((o - SO, slots[o]) for o in other) != sorted(spec["other"]) or _u32(lvl, SO + 0x1C) + 4 != spec["world"] \
            or any(o != SO + 0x1C and not inreg(o) for o in other):
        fail("the source's other-file pointers are not its transit parent and the verified fix word of its model")
    nxt, prv = actor_siblings(target, SO, fail)
    IB, CB = spec["buffers"]
    v0 = [SO + IB + spec["ref_word"], SO + CB + spec["ref_word"]]
    v2 = [SO + IB + spec["graph_word"], SO + CB + spec["graph_word"]]
    for o in ext:
        if o in (SO + 0x14, SO + 0x18):
            continue
        t = _u32(lvl, o) + 4
        if o in v0:
            if t != spec["own_target"]:
                fail("the source's actor reference does not name the verified actor")
            continue
        if not any(slots.get(p + o - SO) == me and _u32(lvl, p + o - SO) + 4 == t for p in peers):
            fail(f"the source block's pointer at +{o - SO:#x} is not family data shared with the GenSound actors")
    # shared regions: closed (every own-file pointer inside stays inside its region), referenced from outside them
    # only by the verified kept words of the block
    for a, b in regions:
        if any(a <= o < b and slots[o] == me and (target(o) is None or not a <= target(o) < b) for o in slots):
            fail("a shared region of the source points outside itself")
    kept = sorted(o for o in slots if not inreg(o) and target(o) is not None and inreg(target(o)))
    if kept != sorted(SO + k for k in spec["kept"]):
        fail("the source's shared regions are referenced by other words than the verified ones")
    owned = {_u32(lvl, o) + 4 - SO for o in inner if o not in kept and not inreg(o)}
    if not set(spec["owned"]) <= owned:
        fail("the source does not own its Perso / Brain / Mind / Intelligence / designer memory and buffers")
    perso = target(SO + 4)
    brain = target(perso + 0xC) if perso is not None else None
    mind = target(brain) if brain is not None else None
    if perso != SO + 0x80 or target(perso) != SO + 0xAC or target(perso + 4) != SO + 0x2B4 or perso + 8 in slots \
            or brain != SO + 0x318 or mind != SO + 0x324 or target(mind + 4) != SO + 0xD6C \
            or target(mind + 0xC) != SO + spec["dsgmem"] or not inreg(target(mind)):
        fail("the source's Perso / Brain / Mind / designer-memory chain is not the verified one")
    std = target(perso + 4)
    if std + 8 in slots or _u32(lvl, SO + spec["buffer"]) or SO + spec["buffer"] in slots:
        fail("the source's standard-game record or 3dData buffer word")
    DM, DL = SO + spec["dsgmem"], spec["dsg_length"]
    if target(DM + 4) != SO + IB or target(DM + 8) != SO + CB or not inreg(target(DM)):
        fail("the source's designer memory record")
    for b in (IB, CB):
        if [o for o in range(SO + b, SO + b + DL) if o in slots] != sorted([SO + b + spec["ref_word"],
                                                                             SO + b + spec["graph_word"]]):
            fail("the source's designer buffers do not hold exactly its actor and graph references")
    if lvl[SO + IB:SO + IB + DL] != lvl[SO + CB:SO + CB + DL] or [target(w) for w in v2] != [spec["graph"]] * 2:
        fail("the source's designer buffers differ or do not name its graph")
    ga, gb = SO + spec["regions"]["graph"][0], SO + spec["regions"]["graph"][1]
    gobj = _graph_objects(lvl, target, spec["graph"])
    if gobj is None or min(gobj) != ga or max(o + z for o, (_, z) in gobj.items()) != gb \
            or sum(z for _, z in gobj.values()) != gb - ga \
            or sum(1 for k, _ in gobj.values() if k == "node") != spec["graph_nodes"]:
        fail("the source's graph does not exactly fill its graph region")
    # incoming references: siblings, one SO record (+4), three backups (+8), one always element (+0xC)
    into = sorted(o for o in slots if slots[o] == me and not SO <= o < SO + BLK and SO <= _u32(lvl, o) + 4 < SO + BLK)
    if any((fa == me and SO <= oa + 4 < SO + BLK) or (fb == me and SO <= ob + 4 < SO + BLK) for oa, fa, ob, fb in cross):
        fail("the source is referenced from the cross-file table")
    rest = [o for o in into if o not in (nxt + 0x18, prv + 0x14)]
    pels, pcount, k, tmpl, names = actor_personal_types(lvl, slots, target, tail, spec, std, False, fail)
    rl = actor_records(lvl, slots, target, tail, spec, fail)
    srecs = [r for r in rl if r + 4 in rest and target(r + 4) == SO]
    if len(srecs) != 1 or any(srecs[0] + q in slots for q in range(8, ACTOR_RECORD, 4)):
        fail("the source's SO record")
    links = actor_backup_links(target, tail, spec, fail)
    sbs, scopy = actor_backup_records(lvl, slots, target, links, spec, rest, "three", fail, shared=inreg)
    al, sel_el = actor_always(lvl, slots, target, tail, spec, rest, False, fail)
    sel_el = [sel_el]
    if sorted(rest) != sorted([srecs[0] + 4, sel_el[0] + 0xC] + [sb + 8 for sb, _ in sbs]):
        fail("the source is referenced from data other than its siblings, SO record, backups and always element")
    wl, wcount = actor_world(tl, cross, target, spec, me, fail)
    # the selected target: an actor SuperObject of the world, not the source's own target, named by no designer
    # buffer of the level (no other manager moves it)
    TS = spec["targets"].get(sel)
    if TS is None or TS == spec["own_target"] or TS not in wl or _u32(lvl, TS) != 2:
        fail("the selected target is not a verified actor of the dynamic world")
    if any(target(o) == TS for a, z in foreign for o in range(a, a + z, 4) if o in slots):
        fail("the selected target is already named by an actor's designer variable")
    return {"slots": slots, "cross": cross, "next": nxt, "prev": prv, "std": std, "pcount": pcount, "personal": pels,
            "template": tmpl, "srec": srecs[0], "records": rl, "links": links, "backups": sbs, "scopy": scopy,
            "always": al, "always_el": sel_el[0], "walk": wl, "world_count": wcount, "inner": inner, "ext": ext,
            "other": other, "regions": regions, "kept": kept, "v0": v0, "v2": v2, "target": TS}


def gmgr_layout(spec: dict):
    """The copy packs only the source block's instance segments (the block minus its shared regions), each placed in
    its source 16-byte phase: ([(source start, source end, copy offset)], copy size, map(source block offset))."""
    return actor_segments(spec["block"], spec["regions"].values(), packed=True)


def build_gensound_manager(lvl: bytes, ptr: bytes, tl: bytes, me: int, spec: dict, peers: list, sel: int,
                           foreign: list, where: str) -> tuple:
    """(new .lvl, new .ptr, new transit.lvl, [(edited .lvl offset, label)], info): one additional sound manager whose
    v0 names an existing GenSound actor, every edited word asserted first. Appended: the copy (in the source's 16-byte
    phase; its instance objects rebased; its model and graph regions left out, every pointer into them kept on the
    source's; v0 = the target, new own-file slots), the personal element and name, the SO record, three backup records
    (source order; the matrix one with its own copy), the always-active element; transit's count + 1.
    verify_gensound_manager re-checks the result as the loader and the game's list walks would see it."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: {why}")
    s = _gmgr_source(lvl, ptr, tl, me, spec, peers, sel, foreign, where)
    SO = spec["so"]
    segs, CS, cmap = gmgr_layout(spec)
    name = actor_name(spec)
    size = len(lvl)
    L, end = actor_layout(size, SO, CS, len(name), len(s["backups"]), fail, always=True)
    fc = L["copy"]
    new = bytearray(lvl) + bytearray(end - size)
    # pointer ownership (G6-P4): instance pointers owned (rebased into the packed segments); pointers into the
    # source's model and graph regions shared (kept on the source's); v0 an explicit reference to the target actor;
    # external ones family data shared with the GenSound actors; the transit parent an other-file pointer (the
    # model region's fix word is not copied)
    kinds = {o: "owned" for o in s["inner"]}
    kinds.update({o: "shared" for o in s["ext"]})
    kinds.update({o: "shared" for o in s["kept"]})
    kinds.update({o: ("ref", s["target"]) for o in s["v0"]})
    kinds.update({SO + 0x14: "link", SO + 0x18: "link"})
    kinds.update({o: "other" for o in s["other"] if not any(a <= o < b for a, b in s["regions"])})
    new_slots = actor_copy(new, lvl, s, SO, fc, segs, cmap, kinds, fail)
    reg, plan = actor_register(new, lvl, me, spec, s, L, name, lambda t: fc + cmap(t - SO))
    new_slots += reg
    edits = apply_original_edits(lvl, new, plan, fail)
    nptr = extend_pointer_table(ptr, new_slots)
    W = spec["world"]
    ntl = bump_actor_count(tl, spec, s["world_count"], fail)
    new = bytes(new)
    verify_gensound_manager(lvl, ptr, tl, new, nptr, ntl, me, spec, s, L, new_slots, edits, where)
    info = {"objects": dict(L), "tail": end - size, "slots": len(new_slots), "edits": [label for _, label in edits],
            "personal_index": s["pcount"], "actors": s["world_count"] + 1, "records": len(s["records"]) + 1,
            "personal_types": s["pcount"] + 1, "always": len(s["always"]) + 1, "transit_word": W + 0x10,
            "moves_gensound_instance": sel, "target": s["target"],
            "reference_words": [fc + cmap(w - SO) for w in s["v0"]], "copy_size": CS,
            "segments": [[a, b, d] for a, b, d in segs]}
    return new, nptr, ntl, edits, info


def verify_gensound_manager(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, spec, s, L, new_slots, edits, where):
    """The simulator: the new files as the loader and the game's list walks would use them, plus the references: the
    copy (its packed instance segments) mirrors the source's instance data, its v0 words name the target actor, its
    kept words the source's model and graph, nothing points into the source's shared regions from the copy except
    those kept words. Any difference from the planned structure refuses."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: simulated load: {why}")
    SO, BLK, MX = spec["so"], spec["block"], spec["matrix"]
    segs, CS, cmap = gmgr_layout(spec)
    C = L["copy"]
    objects = [(C, CS), (L["personal"], ACTOR_PERSONAL), (L["name"], L["record"] - L["name"]),
               (L["record"], ACTOR_RECORD), (L["backup"], ACTOR_BACKUP * len(s["backups"])),
               (L["backup_copy"], ACTOR_BACKUP_DATA), (L["always"], ACTOR_ALWAYS)]
    to_src = {C + d + k: SO + a + k for a, b, d in segs for k in range(0, b - a, 4)}   # copy word -> source word
    slots, target = actor_verify_load(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, spec, s, objects, new_slots, edits,
                                      to_src.get, fail)
    sreg = s["regions"]
    insreg = lambda o: any(a <= o < b for a, b in sreg)   # noqa: E731
    cm = lambda o: C + cmap(o - SO)   # noqa: E731  (a source instance address -> the copy's)
    kept_c = {cm(o) for o in s["kept"]}
    v0c = [cm(w) for w in s["v0"]]
    std = cm(s["std"])
    for (a1, b1, d1), (a2, b2, d2) in zip(segs, segs[1:]):
        if lvl[C + d1 + b1 - a1:C + d2] != bytes(d2 - d1 - (b1 - a1)):
            fail("padding between the copy's segments")
    # every copy word mirrors its source word: data equal (but the personal index and the sibling links), pointers
    # rebased / kept / retargeted / shared by kind
    for co, so in to_src.items():
        k = so - SO
        if (so in s["slots"]) != (co in slots) or s["slots"].get(so) != slots.get(co):
            fail(f"the copy's pointer at +{k:#x}")
        if co not in slots:
            if lvl[co:co + 4] != old_lvl[so:so + 4] and co != std + 8:
                fail(f"the copy's data word at +{k:#x} differs from the source's")
            continue
        if co in v0c:
            if target(co) != s["target"]:
                fail(f"the copy's actor reference at +{k:#x} does not name the target")
        elif co in kept_c:
            if target(co) != target(so) or not insreg(target(co)):
                fail(f"the copy's shared-region pointer at +{k:#x} does not keep the source's target")
        elif so in s["inner"]:
            if target(so) is None or insreg(target(so)) or target(co) != cm(target(so)):
                fail(f"the copy's in-block pointer at +{k:#x}")
        elif so in s["ext"] and k not in (0x14, 0x18) and lvl[co:co + 4] != old_lvl[so:so + 4]:
            fail(f"the copy's shared pointer at +{k:#x}")
        elif so in s["other"] and lvl[co:co + 4] != old_lvl[so:so + 4]:
            fail(f"the copy's other-file pointer at +{k:#x}")
    if target(C + 0x14) != s["next"] or target(C + 0x18) != SO:
        fail("the copy's sibling links")
    into_src = [o for o in range(C, C + CS, 4) if target(o) is not None and SO <= target(o) < SO + BLK]
    if sorted(into_src) != sorted([C + 0x18] + list(kept_c)):
        fail("the copy points into the source other than its previous-sibling link and the shared regions")
    owned = {target(o) for o in range(C, C + CS, 4) if target(o) is not None and C <= target(o) < C + CS}
    if not owned >= {cm(SO + k) for k in spec["owned"]}:
        fail("the copy does not own its Perso / Brain / Mind / Intelligence / designer memory and buffers")
    DM, (IB, CB), DL = cm(SO + spec["dsgmem"]), spec["buffers"], spec["dsg_length"]
    if target(DM) != target(SO + spec["dsgmem"]) or target(DM + 4) != cm(SO + IB) or target(DM + 8) != cm(SO + CB):
        fail("the copy's designer memory record")
    RW = spec["ref_word"]
    for b in (IB, CB):
        cb, sb = lvl[cm(SO + b):cm(SO + b) + DL], old_lvl[SO + b:SO + b + DL]
        if cb[:RW] + cb[RW + 4:] != sb[:RW] + sb[RW + 4:] or target(cm(SO + b) + spec["graph_word"]) != spec["graph"]:
            fail("the copy's designer buffers")
    mind = target(target(target(C + 4) + 0xC))
    if mind != cm(SO + 0x324) or target(mind) != target(SO + 0x324) or target(mind + 4) != cm(SO + 0xD6C):
        fail("the copy's Mind (own) does not use the source's AI model")
    if _u32(lvl, std + 8) != s["pcount"] or _u32(lvl, cm(SO + spec["buffer"])) != 0 \
            or lvl[cm(SO + MX):cm(SO + MX) + 0x54] != old_lvl[SO + MX:SO + MX + 0x54]:
        fail("the copy's personal index, 3dData buffer word or matrix")
    if [target(w) for w in s["v0"]] != [spec["own_target"]] * 2:
        fail("the source's actor reference")
    if sorted(o for o in range(C, C + CS, 4) if target(o) == s["target"]) != sorted(v0c):
        fail("the copy names its target other than through v0")
    actor_verify_lists(old_lvl, lvl, tl, me, spec, s, L, slots, target, cm, std, fail)


def compile_insert_gensound_manager(o: dict, paths) -> tuple:
    """G6-P4 (D-257): (ranges, transaction) of one insert-gensound-manager: one level transaction of version 2 over
    the level file, its pointer table and transit.lvl."""
    level = o["level"]
    where = f"insert-gensound-manager {level} {o['model']!r} instance {o['instance']}"
    spec, allow = GMGR_ALLOW.get(level), STRUCT_ALLOW.get(level)
    if spec is None or allow is None or not structural_enabled(level):
        raise Refusal("UNSUPPORTED", f"{where}: development-only, not enabled for this level")
    if o["model"] != spec["model"] or o["instance"] != spec["instance"]:
        raise Refusal("UNSUPPORTED", f"{where}: the development pilot supports only the verified source manager "
                                     f"(instance {spec['instance']} of {spec['model']!r})")
    sel = o["moves_gensound_instance"]
    if sel not in spec["targets"]:
        raise Refusal("UNSUPPORTED", f"{where}: moves_gensound_instance {sel!r} is not a verified target")
    inp = actor_level_inputs(o, paths, spec, allow, where)
    lvl, ptr, tl = inp["data"]["lvl"], inp["data"]["ptr"], inp["data"]["transit"]
    me, ix = inp["me"], inp["ix"]
    insts = ix["placements"].get(o["model"])
    if not insts or len(insts) != 1 or insts[0]["so"] != spec["so"] or insts[0]["safe"]:
        raise Refusal("TARGET_CHANGED", f"{where}: the source actor is not the verified one")
    dsg = ix["defaults"].get(o["model"])
    inst = dsg["instances"][0] if dsg and dsg.get("instances") else None
    if not dsg or [tuple(v) for v in dsg["vars"]] != list(spec["dsg_vars"]) or dsg["length"] != spec["dsg_length"] \
            or inst is None or inst["dsgmem"] != spec["so"] + spec["dsgmem"] \
            or [inst["initial"], inst["current"]] != [spec["so"] + b for b in spec["buffers"]] or inst["safe"]:
        raise Refusal("UNSUPPORTED", f"{where}: the model's designer layout is not the verified one")
    vt = dict(spec["dsg_vars"])
    if vt.get(spec["ref_word"]) != 18 or vt.get(spec["graph_word"]) != GRAPH_TYPE:
        raise Refusal("UNSUPPORTED", f"{where}: the reference variables are not an actor and a graph variable")
    targets = ix["placements"].get(spec["target_model"]) or []
    if sel >= len(targets) or targets[sel]["so"] != spec["targets"][sel] or model_sets_position(ix, spec["target_model"]):
        raise Refusal("UNSUPPORTED", f"{where}: the target is not the verified GenSound actor, or that model positions "
                                     "itself")
    peers = [i["so"] for i in targets]
    foreign = [(e2[k], d["length"]) for key, d in ix["defaults"].items() if d
               for e2 in d["instances"] for k in ("initial", "current") if isinstance(e2.get(k), int)]
    new_lvl, new_ptr, new_tl, edits, info = build_gensound_manager(lvl, ptr, tl, me, spec, peers, sel, foreign, where)
    return actor_transaction("insert-gensound-manager", inp, new_lvl, new_ptr, new_tl, edits, info, where)


# G6-P8 (D-261): the development-only structural operation `insert-toad-intro`: one additional intro_10
# NIN_m_ToadIntro, a copy of instance 1 (SuperObject 0x581268, a 0x4B8 block of the red lum's layout: census 14 / 16 /
# 1). The model (AI model 0x580C78, its behaviours and scripts) lives in instance 0's block and is shared, never
# copied. Construction = G6-P1's verified recipe through the G6-P5 primitives (build_passive_lum: in-block pointers
# owned, external ones shared, +0x14 / +0x18 sibling links, +0x1C the transit parent), the Toad's own facts only,
# exactly G6-P7's private prototype that E-494 run g3 verified at run time (A-PASS: registration, own state, its own
# Init run under the scheduler, the guest's list element at +0x4A8 linked after the source, release on Exit Game).
# Symbolic inputs only: placement "at_source" (the source's translation) and owner "dynamic_world" (linked after
# the source; personal type, SO record and matrix backup appended; transit's actor count + 1).
INSERT_TOAD_KEYS = {"type", "level", "model", "instance", "lvl_sha256", "ptr_sha256", "transit_sha256", "placement",
                    "owner"}
TOAD10 = "Toad\\NIN_m_ToadIntro\\NIN_m_ToadIntro.rul^CreateIntelligence^CreateComport:NIN_C_ToadInit"
TOAD_ALLOW = {"intro_10": {
    "transit": (41508, "d300ba3a4a3c03cec6a73eb9da8a8d820fcc3a669591e976b357e804315bf275"),
    "model": TOAD10, "instance": 1, "so": 0x581268, "block": 0x4B8, "census": (14, 16, 1),
    "personal": 0x1C74, "records_ref": 0x1CFC, "records": 0x5A7434, "backups": 0x1CEC, "world": 0x9B4,
    "matrix": 0xC4, "translations": (0xC4 + 0x34, 0x260 + 0x34, 0x498), "buffer": 0x14C,
    "new_name": b"XAP_ToadIntro_G6P7", "anchors": {"at_source": ("source", (0.0, 0.0, 0.0))}, "radius": 0.0,
    "placements": ("at_source",), "owners": ("dynamic_world",)}}


def parse_insert_toad_intro(o: dict, where: str):
    if not structural_enabled():
        raise Refusal("UNSUPPORTED", f"{where}: insert-toad-intro is a development-only structural operation (D-261) "
                                     "that this installation does not enable")
    if set(o) - INSERT_TOAD_KEYS or INSERT_TOAD_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: an insert-toad-intro needs exactly {sorted(INSERT_TOAD_KEYS)}")
    if not isinstance(o["level"], str) or not SCRIPT_LEVEL_RE.match(o["level"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'level' must be a level folder name such as intro_10")
    if o["level"] not in TOAD_ALLOW:
        raise Refusal("UNSUPPORTED", f"{where}: level {o['level']} (the development pilot supports "
                                     f"{', '.join(sorted(TOAD_ALLOW))})")
    if not isinstance(o["model"], str) or not 3 <= len(o["model"]) < 0x100 \
            or not all(32 <= ord(c) < 127 for c in o["model"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'model' must be the model's full first-behaviour name")
    if not isinstance(o["instance"], int) or isinstance(o["instance"], bool) or not 0 <= o["instance"] < 4096:
        raise Refusal("BAD_MANIFEST", f"{where}: 'instance' must be an index from script-info --model")
    for k in ("lvl_sha256", "ptr_sha256", "transit_sha256"):
        if not isinstance(o[k], str) or not re.match(r"^[0-9a-f]{64}$", o[k]):
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be the 64-digit SHA-256 of the level's original file")
    spec = TOAD_ALLOW[o["level"]]
    if not isinstance(o["placement"], str) or o["placement"] not in spec["placements"]:
        raise Refusal("UNSUPPORTED", f"{where}: 'placement' must be one of {', '.join(spec['placements'])}")
    if not isinstance(o["owner"], str) or o["owner"] not in spec["owners"]:
        raise Refusal("UNSUPPORTED", f"{where}: 'owner' must be one of {', '.join(spec['owners'])}")


def compile_insert_toad_intro(o: dict, paths) -> tuple:
    """G6-P8 (D-261): (ranges, transaction) of one insert-toad-intro: one level transaction of version 2 over the
    level file, its pointer table and transit.lvl. Ranges: the ten edited words, the appended tail, the whole rebuilt
    pointer table, transit's count word."""
    level = o["level"]
    where = f"insert-toad-intro {level} {o['model']!r} instance {o['instance']}"
    spec, allow = TOAD_ALLOW.get(level), STRUCT_ALLOW.get(level)
    if spec is None or allow is None or not structural_enabled(level):
        raise Refusal("UNSUPPORTED", f"{where}: development-only, not enabled for this level")
    if o["model"] != spec["model"] or o["instance"] != spec["instance"]:
        raise Refusal("UNSUPPORTED", f"{where}: the development pilot supports only the verified source Toad "
                                     f"(instance {spec['instance']} of {spec['model']!r})")
    if o["placement"] not in spec["placements"] or o["owner"] not in spec["owners"]:
        raise Refusal("UNSUPPORTED", f"{where}: only the verified placement and owner")
    inp = actor_level_inputs(o, paths, spec, allow, where)
    lvl, ptr, tl = inp["data"]["lvl"], inp["data"]["ptr"], inp["data"]["transit"]
    me, ix = inp["me"], inp["ix"]
    insts = ix["placements"].get(o["model"])
    if not insts or o["instance"] >= len(insts) or insts[o["instance"]]["so"] != spec["so"] \
            or insts[o["instance"]]["safe"]:
        raise Refusal("TARGET_CHANGED", f"{where}: the source actor is not the verified one")
    dsg = ix["defaults"].get(o["model"], {"vars": [], "instances": []})
    if dsg is None or dsg["vars"] or dsg["instances"] or model_sets_position(ix, o["model"]):
        raise Refusal("UNSUPPORTED", f"{where}: the model has designer variables or sets its own position")
    pos = struct.unpack_from(">3f", lvl, spec["so"] + spec["translations"][0])   # "at_source"
    peers = [i["so"] for n, i in enumerate(insts) if n != o["instance"]]
    new_lvl, new_ptr, new_tl, edits, info = build_passive_lum(lvl, ptr, tl, me, spec, peers, pos, where)
    info["placement"], info["owner"] = o["placement"], o["owner"]
    return actor_transaction("insert-toad-intro", inp, new_lvl, new_ptr, new_tl, edits, info, where)


# G6-P9 (D-262): the development-only composition pilot `insert-toad-intro-pair`: TWO additional intro_10
# NIN_m_ToadIntro, both copies of instance 1, built by ONE coordinated construction into ONE version-2 transaction
# (never two single-Toad images merged). The source and the four lists are parsed and checked once; both copies get
# their own block (each in the source's 16-byte phase), personal type, name, SO record, backup record and matrix copy;
# the sibling chain becomes source -> A -> B -> next; each list gains A then B; each of the ten original words
# insert-toad-intro edits is edited exactly once (counts + 2, transit's actor count + 2); one pointer table (A's block
# words, B's block words, then A's and B's registration words). Copy A carries the single operation's name, copy B
# its own. Exactly two; the single operation is unchanged and still one per mod.
INSERT_TOAD_PAIR_KEYS = INSERT_TOAD_KEYS | {"count"}
TOAD_PAIR_ALLOW = {"intro_10": dict(TOAD_ALLOW["intro_10"], new_names=(b"XAP_ToadIntro_G6P7", b"XAP_ToadIntro_G6P9"),
                                    counts=(2,))}


def parse_insert_toad_intro_pair(o: dict, where: str):
    if not structural_enabled():
        raise Refusal("UNSUPPORTED", f"{where}: insert-toad-intro-pair is a development-only structural pilot (D-262) "
                                     "that this installation does not enable")
    if set(o) - INSERT_TOAD_PAIR_KEYS or INSERT_TOAD_PAIR_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: an insert-toad-intro-pair needs exactly "
                                      f"{sorted(INSERT_TOAD_PAIR_KEYS)}")
    if not isinstance(o["level"], str) or not SCRIPT_LEVEL_RE.match(o["level"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'level' must be a level folder name such as intro_10")
    if o["level"] not in TOAD_PAIR_ALLOW:
        raise Refusal("UNSUPPORTED", f"{where}: level {o['level']} (the development pilot supports "
                                     f"{', '.join(sorted(TOAD_PAIR_ALLOW))})")
    if not isinstance(o["model"], str) or not 3 <= len(o["model"]) < 0x100 \
            or not all(32 <= ord(c) < 127 for c in o["model"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'model' must be the model's full first-behaviour name")
    if not isinstance(o["instance"], int) or isinstance(o["instance"], bool) or not 0 <= o["instance"] < 4096:
        raise Refusal("BAD_MANIFEST", f"{where}: 'instance' must be an index from script-info --model")
    for k in ("lvl_sha256", "ptr_sha256", "transit_sha256"):
        if not isinstance(o[k], str) or not re.match(r"^[0-9a-f]{64}$", o[k]):
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be the 64-digit SHA-256 of the level's original file")
    spec = TOAD_PAIR_ALLOW[o["level"]]
    if not isinstance(o["count"], int) or isinstance(o["count"], bool) or o["count"] not in spec["counts"]:
        raise Refusal("UNSUPPORTED", f"{where}: 'count' must be {' or '.join(map(str, spec['counts']))} (one Toad is "
                                     "insert-toad-intro; more is not supported)")
    if not isinstance(o["placement"], str) or o["placement"] not in spec["placements"]:
        raise Refusal("UNSUPPORTED", f"{where}: 'placement' must be one of {', '.join(spec['placements'])}")
    if not isinstance(o["owner"], str) or o["owner"] not in spec["owners"]:
        raise Refusal("UNSUPPORTED", f"{where}: 'owner' must be one of {', '.join(spec['owners'])}")


def toad_pair_layout(size: int, so: int, blk: int, name_lens: list, n_backups: int, fail) -> tuple:
    """Where the pair's appended objects go: copy A then copy B (each in the source's 16-byte phase), then for A and
    then for B: personal element, name, SO record, backup records, matrix-backup copy; the tail padded to 16 bytes.
    ({object: [A offset, B offset]}, end)."""
    fa = size + (so % 16 - size % 16) % 16
    fb = fa + blk + (so % 16 - (fa + blk) % 16) % 16
    L = {"copy": [fa, fb], "personal": [], "name": [], "record": [], "backup": [], "backup_copy": []}
    pos = fb + blk + (-(fb + blk)) % 4
    for n in name_lens:
        L["personal"].append(pos)
        L["name"].append(pos + ACTOR_PERSONAL)
        L["record"].append(pos + ACTOR_PERSONAL + n)
        L["backup"].append(L["record"][-1] + ACTOR_RECORD)
        L["backup_copy"].append(L["backup"][-1] + ACTOR_BACKUP * n_backups)
        pos = L["backup_copy"][-1] + ACTOR_BACKUP_DATA
    end = pos + (-pos) % 16
    if end >= 1 << 31 or any(v % 4 for vs in L.values() for v in vs) or fa % 16 != fb % 16:
        fail("alignment")
    return L, end


def build_toad_pair(lvl: bytes, ptr: bytes, tl: bytes, me: int, spec: dict, peers: list, pos, where: str) -> tuple:
    """(new .lvl, new .ptr, new transit.lvl, [(edited .lvl offset, label)], info): G6-P9's two additional Toads by one
    coordinated construction on the G6-P5 primitives. Every original word is asserted before its one edit;
    verify_toad_pair then re-checks the combined result as the loader and the game's list walks would see it."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: {why}")
    s = _lum_source(lvl, ptr, tl, me, spec, peers, where)   # the source and the four lists, checked once
    SO, BLK, MX = spec["so"], spec["block"], spec["matrix"]
    nn = spec["new_names"]
    fam = s["names"][s["index"]].rsplit(b"_", 1)[0] + b"_"
    if len(nn) != 2 or nn[0] != spec["new_name"] or nn[0] == nn[1] \
            or any(n in s["names"] or not n.startswith(fam) for n in nn):
        fail("the two new personal-type names are not unique or not of the source's family")
    names = [actor_name(dict(spec, new_name=n)) for n in nn]
    size = len(lvl)
    segs, CS, cmap = actor_segments(BLK, (), packed=False)
    L, end = toad_pair_layout(size, SO, CS, [len(n) for n in names], len(s["backups"]), fail)
    fa, fb = L["copy"]
    new = bytearray(lvl) + bytearray(end - size)
    put = lambda o, v: struct.pack_into(">I", new, o, v)   # noqa: E731
    kinds = {o: "owned" for o in s["inner"]}
    kinds.update({o: "shared" for o in s["ext"]})
    kinds.update({SO + 0x14: "link", SO + 0x18: "link", SO + 0x1C: "other"})
    new_slots = []
    for fc in (fa, fb):   # each copy owns its instance objects (rebased into ITS block), shares the model
        new_slots += actor_copy(new, lvl, s, SO, fc, segs, cmap, kinds, fail)
        for t in spec["translations"]:
            struct.pack_into(">3f", new, fc + t, *pos)
    # the chain inside the pair (both words are relocated slots already planned by actor_copy): A's next is B, B's
    # previous is A; B's personal index is the old type count + 1 (A's = the old count)
    put(fa + cmap(0x14), fb - 4)
    put(fb + cmap(0x18), fa - 4)
    put(fb + cmap(s["std"] - SO) + 8, s["pcount"] + 1)
    # registration, A then B; each object is linked after the list's CURRENT last (an original word only for A)
    PH, RH, BH = spec["personal"], spec["records"], spec["backups"]
    plast, rlast, blink = s["personal"][-1], s["records"][-1], s["links"][-1]
    pp, rp, bp = plast, rlast, blink
    for i, fc in enumerate((fa, fb)):
        pe, nm = L["personal"][i], L["name"][i]
        new[pe:pe + ACTOR_PERSONAL] = lvl[s["template"]:s["template"] + ACTOR_PERSONAL]
        put(pe, 0)
        put(pe + 4, pp - 4)
        put(pe + 0xC, nm - 4)
        new[nm:nm + len(names[i])] = names[i]
        if i:
            put(pp, pe - 4)
        new_slots += [(me, pe + 4), (me, pe + 8), (me, pe + 0xC), (me, pp)]
        pp = pe
        rec = L["record"][i]
        new[rec:rec + ACTOR_RECORD] = lvl[s["srec"]:s["srec"] + ACTOR_RECORD]
        put(rec, 0)
        put(rec + 4, fc - 4)
        if i:
            put(rp, rec - 4)
        new_slots += [(me, rec + 4), (me, rp)]
        rp = rec
        for j, (sb, t) in enumerate(s["backups"]):
            r = L["backup"][i] + ACTOR_BACKUP * j
            new[r:r + ACTOR_BACKUP] = lvl[sb:sb + ACTOR_BACKUP]
            put(r + 4, 0)
            if bp != blink:
                put(bp, r)
            put(r + 8, fc + cmap(t - SO) - 4)
            new_slots.append((me, r + 8))
            if t == SO + MX:
                bc = L["backup_copy"][i]
                new[bc:bc + ACTOR_BACKUP_DATA] = lvl[s["scopy"]:s["scopy"] + ACTOR_BACKUP_DATA]
                for q, v in enumerate(pos):   # the matrix copy holds the copy's translation (words byte-swapped)
                    new[bc + 0x34 + 4 * q:bc + 0x38 + 4 * q] = struct.pack(">f", v)[::-1]
                put(r + 0xC, bc - 4)
                new_slots.append((me, r + 0xC))
            new_slots.append((me, bp))
            bp = r + 4
    nrec = len(s["records"])
    plan = [(SO + 0x14, s["next"] - 4, fa - 4, "source.next"), (s["next"] + 0x18, SO - 4, fb - 4, "next.previous"),
            (PH + 4, plast - 4, L["personal"][1] - 4, "personal.last"),
            (PH + 8, s["pcount"], s["pcount"] + 2, "personal.count"),
            (plast, 0, L["personal"][0] - 4, "personal.old_last.next"),
            (RH + 4, rlast - 4, L["record"][1] - 4, "records.last"), (RH + 8, nrec, nrec + 2, "records.count"),
            (rlast, 0, L["record"][0] - 4, "records.old_last.next"), (BH + 4, blink - 4, bp - 4, "backups.last"),
            (blink, 0, L["backup"][0], "backups.old_last.next")]
    edits = apply_original_edits(lvl, new, plan, fail)
    nptr = extend_pointer_table(ptr, new_slots)
    W = spec["world"]
    ntl = bump_actor_count(tl, spec, s["world_count"], fail, added=2)
    new = bytes(new)
    verify_toad_pair(lvl, ptr, tl, new, nptr, ntl, me, spec, s, L, new_slots, edits, pos, where)
    info = {"objects": {k: list(v) for k, v in L.items()}, "tail": end - size, "slots": len(new_slots),
            "edits": [label for _, label in edits], "personal_index": [s["pcount"], s["pcount"] + 1],
            "position": list(pos), "actors": s["world_count"] + 2, "records": nrec + 2,
            "personal_types": s["pcount"] + 2, "transit_word": W + 0x10, "count": 2,
            "names": [n.decode("ascii") for n in nn]}
    return new, nptr, ntl, edits, info


def verify_toad_pair(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, spec, s, L, new_slots, edits, pos, where):
    """The pair's simulator: the new files as the loader and the game's list walks would use them. Each copy carries
    the source's relocation pattern, owns its instance objects in ITS block, shares the model, points into neither the
    source nor the other copy except through the chain links; the world chain source -> A -> B -> next; each list
    (SO records, backups, personal types) gains exactly A then B; counts + 2. Any difference refuses."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: simulated load: {why}")
    SO, BLK, MX, W = spec["so"], spec["block"], spec["matrix"], spec["world"]
    cps = L["copy"]
    objects = [(c, BLK) for c in cps]
    for i in range(2):
        objects += [(L["personal"][i], ACTOR_PERSONAL), (L["name"][i], L["record"][i] - L["name"][i]),
                    (L["record"][i], ACTOR_RECORD), (L["backup"][i], ACTOR_BACKUP * len(s["backups"])),
                    (L["backup_copy"][i], ACTOR_BACKUP_DATA)]
    slots, target = actor_verify_load(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, spec, s, objects, new_slots, edits,
                                      lambda o: next((o - c + SO for c in cps if c <= o < c + BLK), None), fail,
                                      n_actors=2)
    links = {cps[0] + 0x18: SO, cps[0] + 0x14: cps[1], cps[1] + 0x18: cps[0], cps[1] + 0x14: s["next"]}
    for i, C in enumerate(cps):
        for k in range(0, BLK, 4):
            so, co = SO + k, C + k
            if (so in s["slots"]) != (co in slots) or s["slots"].get(so) != slots.get(co):
                fail(f"copy {'AB'[i]}'s pointer at +{k:#x}")
            if so in s["inner"] and (target(so) is None or target(co) != target(so) - SO + C):
                fail(f"copy {'AB'[i]}'s in-block pointer at +{k:#x}")
            if so in s["ext"] and k not in (0x14, 0x18) and lvl[co:co + 4] != old_lvl[so:so + 4]:
                fail(f"copy {'AB'[i]}'s shared pointer at +{k:#x}")
            t = target(co)
            if co in links:
                if t != links[co]:
                    fail(f"copy {'AB'[i]}'s chain link at +{k:#x}")
            elif t is not None and any(b != C and b <= t < b + BLK for b in [SO] + cps):
                fail(f"copy {'AB'[i]} points into the source or the other copy at +{k:#x}")
        std = s["std"] - SO + C
        if _u32(lvl, std + 8) != s["pcount"] + i or _u32(lvl, C + spec["buffer"]) != 0 \
                or any(lvl[C + t:C + t + 12] != struct.pack(">3f", *pos) for t in spec["translations"]):
            fail(f"copy {'AB'[i]}'s personal index, 3dData buffer word or translation")
    first = next(ob + 4 for oa, fa, ob, fb in s["cross"] if fa != me and fb == me and oa + 4 == W + 8)
    last = next(ob + 4 for oa, fa, ob, fb in s["cross"] if fa != me and fb == me and oa + 4 == W + 0xC)
    w = actor_walk(first, lambda x: target(x + 0x14), 4096)
    want = list(s["walk"])
    want[want.index(SO) + 1:want.index(SO) + 1] = cps
    if w != want or w[-1] != last or _u32(tl, W + 0x10) != len(w) \
            or any(target(b + 0x18) != a for a, b in zip(w, w[1:])) \
            or any(target(C + 0x1C) is not None or _u32(lvl, C + 0x1C) != _u32(old_lvl, SO + 0x1C) for C in cps):
        fail("the dynamic world")
    rl = actor_walk(target(spec["records"]), target)
    owners = [target(r + 4) for r in rl]
    old_owners = [_u32(old_lvl, r + 4) + 4 if s["slots"].get(r + 4) == me else None for r in s["records"]]
    if rl != s["records"] + L["record"] or _u32(lvl, spec["records"] + 8) != len(rl) \
            or target(spec["records"] + 4) != rl[-1] or owners[-2:] != cps or owners[:-2] != old_owners \
            or any(owners.count(x) != 1 for x in [SO] + cps):
        fail("the SO-record list")
    bl = actor_walk(target(spec["backups"]), target)
    mine = [L["backup"][i] + ACTOR_BACKUP * j + 4 for i in range(2) for j in range(len(s["backups"]))]
    if bl != s["links"] + mine or target(spec["backups"] + 4) != bl[-1]:
        fail("the backup list")
    for i, C in enumerate(cps):
        for j, (sb, t) in enumerate(s["backups"]):
            r, bc, ct = L["backup"][i] + ACTOR_BACKUP * j, L["backup_copy"][i], t - SO + C
            if target(r + 8) != ct or lvl[r + 0x10:r + 0x18] != old_lvl[sb + 0x10:sb + 0x18]:
                fail(f"a backup record of copy {'AB'[i]}")
            if t == SO + MX and (target(r + 0xC) != bc or b"".join(
                    lvl[bc + q:bc + q + 4][::-1] for q in range(0, 0x54, 4)) != lvl[ct:ct + 0x54]):
                fail(f"copy {'AB'[i]}'s matrix backup")
            if t != SO + MX and (r + 0xC in slots or _u32(lvl, r + 0xC) != _u32(lvl, ct)):
                fail(f"an inline backup of copy {'AB'[i]}")
    pl = actor_walk(target(spec["personal"]), target)
    nms = [lvl[target(e + 0xC):target(e + 0xC) + 0x40].split(b"\0")[0] for e in pl]
    if pl != s["personal"] + L["personal"] or _u32(lvl, spec["personal"] + 8) != len(pl) \
            or target(spec["personal"] + 4) != pl[-1] or any(target(b + 4) != a for a, b in zip(pl, pl[1:])) \
            or [target(e + 0xC) for e in L["personal"]] != L["name"] or nms[-2:] != list(spec["new_names"]) \
            or len(set(nms)) != len(nms) \
            or any(pl.index(L["personal"][i]) != _u32(lvl, s["std"] - SO + C + 8) for i, C in enumerate(cps)) \
            or any(lvl[e + 0x10:e + 0x14] != old_lvl[s["template"] + 0x10:s["template"] + 0x14] for e in L["personal"]):
        fail("the personal object-type list")


def compile_insert_toad_intro_pair(o: dict, paths) -> tuple:
    """G6-P9 (D-262): (ranges, transaction) of one insert-toad-intro-pair: one version-2 level transaction over the
    level file, its pointer table and transit.lvl. Ranges: the ten edited words, the appended tail, the whole rebuilt
    pointer table, transit's count word."""
    level = o["level"]
    where = f"insert-toad-intro-pair {level} {o['model']!r} instance {o['instance']}"
    spec, allow = TOAD_PAIR_ALLOW.get(level), STRUCT_ALLOW.get(level)
    if spec is None or allow is None or not structural_enabled(level):
        raise Refusal("UNSUPPORTED", f"{where}: development-only, not enabled for this level")
    if o["model"] != spec["model"] or o["instance"] != spec["instance"]:
        raise Refusal("UNSUPPORTED", f"{where}: the development pilot supports only the verified source Toad "
                                     f"(instance {spec['instance']} of {spec['model']!r})")
    if o["count"] not in spec["counts"] or o["placement"] not in spec["placements"] or o["owner"] not in spec["owners"]:
        raise Refusal("UNSUPPORTED", f"{where}: only two Toads, the verified placement and owner")
    inp = actor_level_inputs(o, paths, spec, allow, where)
    lvl, ptr, tl = inp["data"]["lvl"], inp["data"]["ptr"], inp["data"]["transit"]
    me, ix = inp["me"], inp["ix"]
    insts = ix["placements"].get(o["model"])
    if not insts or o["instance"] >= len(insts) or insts[o["instance"]]["so"] != spec["so"] \
            or insts[o["instance"]]["safe"]:
        raise Refusal("TARGET_CHANGED", f"{where}: the source actor is not the verified one")
    dsg = ix["defaults"].get(o["model"], {"vars": [], "instances": []})
    if dsg is None or dsg["vars"] or dsg["instances"] or model_sets_position(ix, o["model"]):
        raise Refusal("UNSUPPORTED", f"{where}: the model has designer variables or sets its own position")
    pos = struct.unpack_from(">3f", lvl, spec["so"] + spec["translations"][0])   # "at_source"
    peers = [i["so"] for n, i in enumerate(insts) if n != o["instance"]]
    new_lvl, new_ptr, new_tl, edits, info = build_toad_pair(lvl, ptr, tl, me, spec, peers, pos, where)
    info["placement"], info["owner"] = o["placement"], o["owner"]
    return actor_transaction("insert-toad-intro-pair", inp, new_lvl, new_ptr, new_tl, edits, info, where)


# G6-P11 (D-264): the development-only heterogeneous composition pilot `insert-lum-toad-pair`: ONE additional
# intro_10 NIN_m_Lums_Int10 (G6-P1's source, instance 6, at the runtime-verified `flight_path` preset) and ONE
# additional NIN_m_ToadIntro (G6-P8's source, instance 1, `at_source`), built by ONE coordinated construction into ONE
# version-2 transaction (never two single images merged). Both sources and the four lists are parsed and checked once
# each (the two parses must agree on every list); each copy keeps its own recipe (G6-P1's / G6-P8's class map: in-block
# owned, external shared with its own model's instances, +0x1C the transit parent) and its own source's 16-byte phase;
# each is linked after ITS source in the world chain (the two sites must not be adjacent); the three level lists gain
# the Lum then the Toad. Original words: each source's next and its next's previous (four), plus the eight list words,
# each edited once (counts + 2); transit's actor count + 2. Exactly one Lum and one Toad; nothing else.
INSERT_LUM_TOAD_KEYS = {"type", "level", "lvl_sha256", "ptr_sha256", "transit_sha256", "lum_model", "lum_instance",
                        "lum_placement", "toad_model", "toad_instance", "toad_placement", "owner"}
LUM_TOAD_ALLOW = {"intro_10": {"lum": LUM_ALLOW["intro_10"], "toad": TOAD_ALLOW["intro_10"],
                               "lum_placements": ("flight_path",), "toad_placements": ("at_source",),
                               "owners": ("dynamic_world",)}}


def parse_insert_lum_toad_pair(o: dict, where: str):
    if not structural_enabled():
        raise Refusal("UNSUPPORTED", f"{where}: insert-lum-toad-pair is a development-only structural pilot (D-264) "
                                     "that this installation does not enable")
    if set(o) - INSERT_LUM_TOAD_KEYS or INSERT_LUM_TOAD_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: an insert-lum-toad-pair needs exactly {sorted(INSERT_LUM_TOAD_KEYS)}")
    if not isinstance(o["level"], str) or not SCRIPT_LEVEL_RE.match(o["level"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'level' must be a level folder name such as intro_10")
    if o["level"] not in LUM_TOAD_ALLOW:
        raise Refusal("UNSUPPORTED", f"{where}: level {o['level']} (the development pilot supports "
                                     f"{', '.join(sorted(LUM_TOAD_ALLOW))})")
    for k in ("lum_model", "toad_model"):
        if not isinstance(o[k], str) or not 3 <= len(o[k]) < 0x100 or not all(32 <= ord(c) < 127 for c in o[k]):
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be the model's full first-behaviour name")
    for k in ("lum_instance", "toad_instance"):
        if not isinstance(o[k], int) or isinstance(o[k], bool) or not 0 <= o[k] < 4096:
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be an index from script-info --model")
    for k in ("lvl_sha256", "ptr_sha256", "transit_sha256"):
        if not isinstance(o[k], str) or not re.match(r"^[0-9a-f]{64}$", o[k]):
            raise Refusal("BAD_MANIFEST", f"{where}: '{k}' must be the 64-digit SHA-256 of the level's original file")
    spec = LUM_TOAD_ALLOW[o["level"]]
    for k, allowed in (("lum_placement", spec["lum_placements"]), ("toad_placement", spec["toad_placements"]),
                       ("owner", spec["owners"])):
        if not isinstance(o[k], str) or o[k] not in allowed:
            raise Refusal("UNSUPPORTED", f"{where}: '{k}' must be one of {', '.join(allowed)}")


def lum_toad_layout(size: int, lso: int, tso: int, blk: int, name_lens: list, n_backups: list, fail) -> tuple:
    """Where the pair's appended objects go: the Lum copy (in the Lum source's 16-byte phase), the Toad copy (in the
    Toad source's phase), then for the Lum and then for the Toad: personal element, name, SO record, backup records,
    matrix-backup copy; the tail padded to 16 bytes. ({object: [Lum offset, Toad offset]}, end)."""
    fl = size + (lso % 16 - size % 16) % 16
    ft = fl + blk + (tso % 16 - (fl + blk) % 16) % 16
    L = {"copy": [fl, ft], "personal": [], "name": [], "record": [], "backup": [], "backup_copy": []}
    pos = ft + blk + (-(ft + blk)) % 4
    for n, nb in zip(name_lens, n_backups):
        L["personal"].append(pos)
        L["name"].append(pos + ACTOR_PERSONAL)
        L["record"].append(pos + ACTOR_PERSONAL + n)
        L["backup"].append(L["record"][-1] + ACTOR_RECORD)
        L["backup_copy"].append(L["backup"][-1] + ACTOR_BACKUP * nb)
        pos = L["backup_copy"][-1] + ACTOR_BACKUP_DATA
    end = pos + (-pos) % 16
    if end >= 1 << 31 or any(v % 4 for vs in L.values() for v in vs) or fl % 16 != lso % 16 or ft % 16 != tso % 16:
        fail("alignment")
    return L, end


def build_lum_toad_pair(lvl: bytes, ptr: bytes, tl: bytes, me: int, specs: list, peers: list, poss: list,
                        where: str) -> tuple:
    """(new .lvl, new .ptr, new transit.lvl, [(edited .lvl offset, label)], info): G6-P11's one Lum and one Toad by one
    coordinated construction on the G6-P5 primitives; specs / peers / poss = [Lum's, Toad's]. Every original word is
    asserted before its one edit; verify_lum_toad_pair then re-checks the combined result as the loader and the game's
    list walks would see it."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: {why}")
    ss = [_lum_source(lvl, ptr, tl, me, sp, pr, where) for sp, pr in zip(specs, peers)]   # each source checked once
    if any(ss[0][k] != ss[1][k] for k in ("slots", "cross", "personal", "pcount", "records", "links", "walk",
                                           "world_count")):
        fail("the two sources' parses of the shared lists disagree")
    s0 = ss[0]
    SOs = [sp["so"] for sp in specs]
    BLK = specs[0]["block"]
    if specs[1]["block"] != BLK or SOs[0] == SOs[1] or not SOs[0] <= SOs[1] - BLK and not SOs[1] <= SOs[0] - BLK:
        fail("the two sources are not two distinct actors of the verified block size")
    if ss[0]["next"] == SOs[1] or ss[1]["next"] == SOs[0]:
        fail("the two insertion sites are adjacent in the world chain")
    nn = [sp["new_name"] for sp in specs]
    if nn[0] == nn[1]:
        fail("the two new personal-type names are the same")
    names = [actor_name(sp) for sp in specs]
    size = len(lvl)
    segs, CS, cmap = actor_segments(BLK, (), packed=False)
    L, end = lum_toad_layout(size, SOs[0], SOs[1], CS, [len(n) for n in names], [len(s["backups"]) for s in ss],
                             fail)
    new = bytearray(lvl) + bytearray(end - size)
    put = lambda o, v: struct.pack_into(">I", new, o, v)   # noqa: E731
    new_slots = []
    for i, (s, sp, fc, pos) in enumerate(zip(ss, specs, L["copy"], poss)):
        SO = sp["so"]   # each copy: its own source's verified class map (G6-P1 / G6-P8), linked after its source
        kinds = {o: "owned" for o in s["inner"]}
        kinds.update({o: "shared" for o in s["ext"]})
        kinds.update({SO + 0x14: "link", SO + 0x18: "link", SO + 0x1C: "other"})
        new_slots += actor_copy(new, lvl, s, SO, fc, segs, cmap, kinds, fail)
        for t in sp["translations"]:
            struct.pack_into(">3f", new, fc + t, *pos)
        put(fc + cmap(s["std"] - SO) + 8, s0["pcount"] + i)   # personal index: the Lum the old count, the Toad + 1
    # registration, Lum then Toad; each object a copy of ITS source's own and linked after the list's CURRENT last
    PH, RH, BH = specs[0]["personal"], specs[0]["records"], specs[0]["backups"]
    if (specs[1]["personal"], specs[1]["records"], specs[1]["backups"], specs[1]["world"]) != (PH, RH, BH,
                                                                                               specs[0]["world"]):
        fail("the two specs name different lists")
    plast, rlast, blink = s0["personal"][-1], s0["records"][-1], s0["links"][-1]
    pp, rp, bp = plast, rlast, blink
    for i, (s, sp, fc, pos) in enumerate(zip(ss, specs, L["copy"], poss)):
        SO = sp["so"]
        pe, nm = L["personal"][i], L["name"][i]
        new[pe:pe + ACTOR_PERSONAL] = lvl[s["template"]:s["template"] + ACTOR_PERSONAL]
        put(pe, 0)
        put(pe + 4, pp - 4)
        put(pe + 0xC, nm - 4)
        new[nm:nm + len(names[i])] = names[i]
        if i:
            put(pp, pe - 4)
        new_slots += [(me, pe + 4), (me, pe + 8), (me, pe + 0xC), (me, pp)]
        pp = pe
        rec = L["record"][i]
        new[rec:rec + ACTOR_RECORD] = lvl[s["srec"]:s["srec"] + ACTOR_RECORD]
        put(rec, 0)
        put(rec + 4, fc - 4)
        if i:
            put(rp, rec - 4)
        new_slots += [(me, rec + 4), (me, rp)]
        rp = rec
        for j, (sb, t) in enumerate(s["backups"]):
            r = L["backup"][i] + ACTOR_BACKUP * j
            new[r:r + ACTOR_BACKUP] = lvl[sb:sb + ACTOR_BACKUP]
            put(r + 4, 0)
            if bp != blink:
                put(bp, r)
            put(r + 8, fc + cmap(t - SO) - 4)
            new_slots.append((me, r + 8))
            if t == SO + sp["matrix"]:
                bc = L["backup_copy"][i]
                new[bc:bc + ACTOR_BACKUP_DATA] = lvl[s["scopy"]:s["scopy"] + ACTOR_BACKUP_DATA]
                for q, v in enumerate(pos):   # the matrix copy holds the copy's translation (words byte-swapped)
                    new[bc + 0x34 + 4 * q:bc + 0x38 + 4 * q] = struct.pack(">f", v)[::-1]
                put(r + 0xC, bc - 4)
                new_slots.append((me, r + 0xC))
            new_slots.append((me, bp))
            bp = r + 4
    nrec = len(s0["records"])
    plan = []
    for s, SO, fc, tag in zip(ss, SOs, L["copy"], ("lum", "toad")):
        plan += [(SO + 0x14, s["next"] - 4, fc - 4, f"{tag}.source.next"),
                 (s["next"] + 0x18, SO - 4, fc - 4, f"{tag}.next.previous")]
    plan += [(PH + 4, plast - 4, L["personal"][1] - 4, "personal.last"),
             (PH + 8, s0["pcount"], s0["pcount"] + 2, "personal.count"),
             (plast, 0, L["personal"][0] - 4, "personal.old_last.next"),
             (RH + 4, rlast - 4, L["record"][1] - 4, "records.last"), (RH + 8, nrec, nrec + 2, "records.count"),
             (rlast, 0, L["record"][0] - 4, "records.old_last.next"), (BH + 4, blink - 4, bp - 4, "backups.last"),
             (blink, 0, L["backup"][0], "backups.old_last.next")]
    edits = apply_original_edits(lvl, new, plan, fail)
    nptr = extend_pointer_table(ptr, new_slots)
    W = specs[0]["world"]
    ntl = bump_actor_count(tl, specs[0], s0["world_count"], fail, added=2)
    new = bytes(new)
    verify_lum_toad_pair(lvl, ptr, tl, new, nptr, ntl, me, specs, ss, L, new_slots, edits, poss, where)
    info = {"objects": {k: list(v) for k, v in L.items()}, "tail": end - size, "slots": len(new_slots),
            "edits": [label for _, label in edits], "personal_index": [s0["pcount"], s0["pcount"] + 1],
            "positions": [list(p) for p in poss], "actors": s0["world_count"] + 2, "records": nrec + 2,
            "personal_types": s0["pcount"] + 2, "transit_word": W + 0x10,
            "names": [n.decode("ascii") for n in nn], "sources": SOs}
    return new, nptr, ntl, edits, info


def verify_lum_toad_pair(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, specs, ss, L, new_slots, edits, poss, where):
    """The heterogeneous pair's simulator: the new files as the loader and the game's list walks would use them. Each
    copy carries ITS source's relocation pattern, owns its instance objects in its own block, shares its own model,
    points into no source and not into the other copy except its previous-sibling link to its own source; the world
    chain has the Lum copy right after the Lum source and the Toad copy right after the Toad source; each list (SO
    records, backups, personal types) gains exactly the Lum then the Toad; counts + 2. Any difference refuses."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", f"{where}: simulated load: {why}")
    s0, W, BLK = ss[0], specs[0]["world"], specs[0]["block"]
    SOs, cps = [sp["so"] for sp in specs], L["copy"]
    tails = dict(s0)   # the old list ends the common simulator checks (the same for both parses)
    objects = [(c, BLK) for c in cps]
    for i in range(2):
        objects += [(L["personal"][i], ACTOR_PERSONAL), (L["name"][i], L["record"][i] - L["name"][i]),
                    (L["record"][i], ACTOR_RECORD), (L["backup"][i], ACTOR_BACKUP * len(ss[i]["backups"])),
                    (L["backup_copy"][i], ACTOR_BACKUP_DATA)]
    slots, target = actor_verify_load(old_lvl, old_ptr, old_tl, lvl, ptr, tl, me, specs[0], tails, objects, new_slots,
                                      edits, lambda o: next((o - c + so for c, so in zip(cps, SOs) if c <= o < c + BLK),
                                                            None), fail, n_actors=2)
    tag = ("Lum", "Toad")
    for i, (s, sp, C, SO, pos) in enumerate(zip(ss, specs, cps, SOs, poss)):
        links = {C + 0x18: SO, C + 0x14: s["next"]}
        for k in range(0, BLK, 4):
            so, co = SO + k, C + k
            if (so in s["slots"]) != (co in slots) or s["slots"].get(so) != slots.get(co):
                fail(f"the {tag[i]} copy's pointer at +{k:#x}")
            if so in s["inner"] and (target(so) is None or target(co) != target(so) - SO + C):
                fail(f"the {tag[i]} copy's in-block pointer at +{k:#x}")
            if so in s["ext"] and k not in (0x14, 0x18) and lvl[co:co + 4] != old_lvl[so:so + 4]:
                fail(f"the {tag[i]} copy's shared pointer at +{k:#x}")
            t = target(co)
            if co in links:
                if t != links[co]:
                    fail(f"the {tag[i]} copy's sibling link at +{k:#x}")
            elif t is not None and any(b != C and b <= t < b + BLK for b in SOs + cps):
                fail(f"the {tag[i]} copy points into a source or the other copy at +{k:#x}")
        std = s["std"] - SO + C
        if _u32(lvl, std + 8) != s0["pcount"] + i or _u32(lvl, C + sp["buffer"]) != 0 \
                or any(lvl[C + t:C + t + 12] != struct.pack(">3f", *pos) for t in sp["translations"]):
            fail(f"the {tag[i]} copy's personal index, 3dData buffer word or translation")
    first = next(ob + 4 for oa, fa, ob, fb in s0["cross"] if fa != me and fb == me and oa + 4 == W + 8)
    last = next(ob + 4 for oa, fa, ob, fb in s0["cross"] if fa != me and fb == me and oa + 4 == W + 0xC)
    w = actor_walk(first, lambda x: target(x + 0x14), 4096)
    want = []
    for x in s0["walk"]:
        want.append(x)
        if x in SOs:
            want.append(cps[SOs.index(x)])
    if w != want or w[-1] != last or _u32(tl, W + 0x10) != len(w) \
            or any(target(b + 0x18) != a for a, b in zip(w, w[1:])) \
            or any(target(C + 0x1C) is not None or _u32(lvl, C + 0x1C) != _u32(old_lvl, SO + 0x1C)
                   for C, SO in zip(cps, SOs)):
        fail("the dynamic world")
    RH, BH, PH = specs[0]["records"], specs[0]["backups"], specs[0]["personal"]
    rl = actor_walk(target(RH), target)
    owners = [target(r + 4) for r in rl]
    old_owners = [_u32(old_lvl, r + 4) + 4 if s0["slots"].get(r + 4) == me else None for r in s0["records"]]
    if rl != s0["records"] + L["record"] or _u32(lvl, RH + 8) != len(rl) or target(RH + 4) != rl[-1] \
            or owners[-2:] != cps or owners[:-2] != old_owners or any(owners.count(x) != 1 for x in SOs + cps) \
            or any(lvl[r + 8:r + ACTOR_RECORD] != old_lvl[s["srec"] + 8:s["srec"] + ACTOR_RECORD]
                   for r, s in zip(L["record"], ss)):
        fail("the SO-record list")
    bl = actor_walk(target(BH), target)
    mine = [L["backup"][i] + ACTOR_BACKUP * j + 4 for i in range(2) for j in range(len(ss[i]["backups"]))]
    if bl != s0["links"] + mine or target(BH + 4) != bl[-1]:
        fail("the backup list")
    for i, (s, sp, C, SO) in enumerate(zip(ss, specs, cps, SOs)):
        for j, (sb, t) in enumerate(s["backups"]):
            r, bc, ct = L["backup"][i] + ACTOR_BACKUP * j, L["backup_copy"][i], t - SO + C
            if target(r + 8) != ct or lvl[r + 0x10:r + 0x18] != old_lvl[sb + 0x10:sb + 0x18]:
                fail(f"a backup record of the {tag[i]} copy")
            if t == SO + sp["matrix"] and (target(r + 0xC) != bc or b"".join(
                    lvl[bc + q:bc + q + 4][::-1] for q in range(0, 0x54, 4)) != lvl[ct:ct + 0x54]):
                fail(f"the {tag[i]} copy's matrix backup")
            if t != SO + sp["matrix"] and (r + 0xC in slots or _u32(lvl, r + 0xC) != _u32(lvl, ct)):
                fail(f"an inline backup of the {tag[i]} copy")
    pl = actor_walk(target(PH), target)
    nms = [lvl[target(e + 0xC):target(e + 0xC) + 0x40].split(b"\0")[0] for e in pl]
    if pl != s0["personal"] + L["personal"] or _u32(lvl, PH + 8) != len(pl) or target(PH + 4) != pl[-1] \
            or any(target(b + 4) != a for a, b in zip(pl, pl[1:])) \
            or [target(e + 0xC) for e in L["personal"]] != L["name"] \
            or nms[-2:] != [sp["new_name"] for sp in specs] or len(set(nms)) != len(nms) \
            or any(pl.index(L["personal"][i]) != _u32(lvl, s["std"] - SO + C + 8)
                   for i, (s, SO, C) in enumerate(zip(ss, SOs, cps))) \
            or any(lvl[e + 8:e + 0xC] != old_lvl[s["template"] + 8:s["template"] + 0xC]
                   or lvl[e + 0x10:e + 0x14] != old_lvl[s["template"] + 0x10:s["template"] + 0x14]
                   for e, s in zip(L["personal"], ss)):
        fail("the personal object-type list")


def compile_insert_lum_toad_pair(o: dict, paths) -> tuple:
    """G6-P11 (D-264): (ranges, transaction) of one insert-lum-toad-pair: one version-2 level transaction over the
    level file, its pointer table and transit.lvl. Ranges: the twelve edited words, the appended tail, the whole
    rebuilt pointer table, transit's count word."""
    level = o["level"]
    where = f"insert-lum-toad-pair {level}"
    al, allow = LUM_TOAD_ALLOW.get(level), STRUCT_ALLOW.get(level)
    if al is None or allow is None or not structural_enabled(level):
        raise Refusal("UNSUPPORTED", f"{where}: development-only, not enabled for this level")
    lspec, tspec = al["lum"], al["toad"]
    if (o["lum_model"], o["lum_instance"]) != (lspec["model"], lspec["instance"]) \
            or (o["toad_model"], o["toad_instance"]) != (tspec["model"], tspec["instance"]):
        raise Refusal("UNSUPPORTED", f"{where}: the development pilot supports only the verified source Lum "
                                     f"(instance {lspec['instance']}) and source Toad (instance {tspec['instance']})")
    if o["lum_placement"] not in al["lum_placements"] or o["toad_placement"] not in al["toad_placements"] \
            or o["owner"] not in al["owners"]:
        raise Refusal("UNSUPPORTED", f"{where}: only the verified placements and owner")
    if lspec["transit"] != tspec["transit"]:
        raise Refusal("UNSUPPORTED", f"{where}: the two recipes name different transit.lvl versions")
    inp = actor_level_inputs(o, paths, lspec, allow, where)
    lvl, ptr, tl = inp["data"]["lvl"], inp["data"]["ptr"], inp["data"]["transit"]
    me, ix = inp["me"], inp["ix"]
    peers = []
    for sp in (lspec, tspec):
        insts = ix["placements"].get(sp["model"])
        if not insts or sp["instance"] >= len(insts) or insts[sp["instance"]]["so"] != sp["so"] \
                or insts[sp["instance"]]["safe"]:
            raise Refusal("TARGET_CHANGED", f"{where}: a source actor is not the verified one")
        dsg = ix["defaults"].get(sp["model"], {"vars": [], "instances": []})
        if dsg is None or dsg["vars"] or dsg["instances"] or model_sets_position(ix, sp["model"]):
            raise Refusal("UNSUPPORTED", f"{where}: a model has designer variables or sets its own position")
        peers.append([i["so"] for n, i in enumerate(insts) if n != sp["instance"]])
    lpos = lum_anchors(lvl, lspec)[o["lum_placement"]]
    tpos = struct.unpack_from(">3f", lvl, tspec["so"] + tspec["translations"][0])   # "at_source"
    new_lvl, new_ptr, new_tl, edits, info = build_lum_toad_pair(lvl, ptr, tl, me, [lspec, tspec], peers,
                                                                [lpos, tpos], where)
    info["placements"], info["owner"] = [o["lum_placement"], o["toad_placement"]], o["owner"]
    return actor_transaction("insert-lum-toad-pair", inp, new_lvl, new_ptr, new_tl, edits, info, where)


def tx_id(level: str, mod_id: str, members: list, version: int = TX_VERSION) -> str:
    """G5-P1: the transaction's identifier: the first 16 hex digits of the SHA-256 of its canonical text (the runtime
    recomputes it; members = [(role, file name, size, original sha256, guest size, result sha256)] in role order).
    G6-P1 (D-251): version 2 (lvl, ptr, transit) names its version in the text; version 1's text is unchanged."""
    text = f"level-tx {version} {level} {mod_id}\n" + "".join(
        f"tx-file {role} {name.lower()} {size} {orig} {guest} {result}\n" for role, name, size, orig, guest, result in
        sorted(members))
    return sha256_bytes(text.encode("ascii"))[:16]


def designer_hash(ix: dict, inst: dict, length: int) -> str:
    return sha256_bytes(ix["data"][inst["initial"]:inst["initial"] + length])


def designer_field(ix: dict, entry: dict, inst: dict, var: int):
    """(kind, size, buffer offset) of an editable variable of one instance, else raises the reason as a string."""
    if inst["safe"]:
        raise ValueError(inst["safe"])
    off, t = entry["vars"][var]
    if t not in DSG_KINDS:
        raise ValueError(f"variable {var} is type {t}; only bool, byte, int and real variables can be changed")
    kind, size = DSG_KINDS[t]
    ends = sorted({o for o, _ in entry["vars"] if o > off} | {entry["length"]})
    if off % size or off + size > ends[0]:
        raise ValueError(f"variable {var} does not fit its place in the buffer")
    for b in (inst["initial"], inst["current"]):
        if any(w in ix["slots"] for w in range(b + off - 3, b + off + size)):   # a word at w covers w..w+3
            raise ValueError(f"variable {var} holds a relocated word")
    d = ix["data"]
    if d[inst["initial"] + off:inst["initial"] + off + size] != d[inst["current"] + off:inst["current"] + off + size]:
        raise ValueError(f"variable {var}: the file's initial and current values differ")
    return kind, size, off


def designer_value(kind: str, raw: bytes):
    if kind == "real":
        return struct.unpack(">f", raw)[0]
    return int.from_bytes(raw, "big", signed=(kind == "int"))


def designer_value_bytes(o: dict, where: str) -> bytes:
    v, kind = o["value"], o["kind"]
    if kind == "real":
        return script_value_bytes({"kind": "real", "value": v}, where)
    if isinstance(v, bool) or not isinstance(v, int):
        raise Refusal("BAD_MANIFEST", f"{where}: 'value' of a {kind} must be a whole number")
    if kind == "int":
        return script_value_bytes({"kind": "int", "value": v}, where)
    lo, hi = {"bool": (0, 1), "byte": (0, 127)}[kind]
    if not lo <= v <= hi:
        raise Refusal("BAD_MANIFEST", f"{where}: a {kind} 'value' must be from {lo} to {hi}")
    return bytes([v])


def parse_designer_default(o: dict, where: str):
    """D-227: the initial value of one designer variable of one actor instance of a level's AI model."""
    if set(o) - DESIGNER_DEFAULT_KEYS or DESIGNER_DEFAULT_KEYS - set(o):
        raise Refusal("BAD_MANIFEST", f"{where}: a designer-default needs exactly {sorted(DESIGNER_DEFAULT_KEYS)}")
    if not isinstance(o["level"], str) or not SCRIPT_LEVEL_RE.match(o["level"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'level' must be a level folder name such as intro_10")
    if o["level"] == "fix":
        raise Refusal("UNSUPPORTED", f"{where}: designer variables of fix.lvl cannot be changed (they persist "
                                     "across levels)")
    if not isinstance(o["model"], str) or not 3 <= len(o["model"]) < 0x100 \
            or not all(32 <= ord(c) < 127 for c in o["model"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'model' must be the model's full first-behaviour name")
    for key in ("instance", "variable"):
        if not isinstance(o[key], int) or isinstance(o[key], bool) or not 0 <= o[key] < 4096:
            raise Refusal("BAD_MANIFEST", f"{where}: '{key}' must be an index from script-info --model")
    if not isinstance(o["initial_sha256"], str) or not re.match(r"^[0-9a-f]{64}$", o["initial_sha256"]):
        raise Refusal("BAD_MANIFEST", f"{where}: 'initial_sha256' must be the 64-digit SHA-256 from script-info")
    if o["kind"] not in {k for k, _ in DSG_KINDS.values()}:
        raise Refusal("UNSUPPORTED", f"{where}: 'kind' must be bool, byte, int or real (other designer variables "
                                     "cannot be changed)")
    designer_value_bytes(o, where)


def compile_designer_defaults(ovs: list, paths, cache=None) -> list:
    out, cache = [], {} if cache is None else cache
    for o in ovs:
        where = f"designer-default {o['level']} {o['model']!r} instance {o['instance']} variable {o['variable']}"
        if o["level"] == "fix":
            raise Refusal("UNSUPPORTED", f"{where}: designer variables of fix.lvl cannot be changed")
        if o["level"] not in cache:
            cache[o["level"]] = read_script_index(paths["game"], o["level"])
        ix = cache[o["level"]]
        if o["model"] not in ix["defaults"]:
            raise Refusal("TARGET_MISSING", f"{where}: no AI model with this first behaviour in this level")
        entry = ix["defaults"][o["model"]]
        if entry is None:
            raise Refusal("TARGET_CHANGED", f"{where}: the model is not unique in this level")
        if o["instance"] >= len(entry["instances"]):
            raise Refusal("TARGET_MISSING", f"{where}: the model has {len(entry['instances'])} instance(s) in this file")
        inst = entry["instances"][o["instance"]]
        if inst["safe"]:
            raise Refusal("UNSUPPORTED", f"{where}: {inst['safe']}")
        if designer_hash(ix, inst, entry["length"]) != o["initial_sha256"]:
            raise Refusal("TARGET_CHANGED", f"{where}: the instance's initial values are not the ones this mod was "
                                            "made for")
        if o["variable"] >= len(entry["vars"]):
            raise Refusal("TARGET_MISSING", f"{where}: the model has {len(entry['vars'])} designer variables")
        try:
            kind, size, off = designer_field(ix, entry, inst, o["variable"])
        except ValueError as x:
            raise Refusal("UNSUPPORTED", f"{where}: {x}")
        if kind != o["kind"]:
            raise Refusal("TARGET_CHANGED", f"{where}: the variable is a {kind}, not a {o['kind']}")
        data = designer_value_bytes(o, where)
        tag = f"{o['level']}:{o['model']}@{o['instance']}.v{o['variable']}"
        out += [(ix["lvl"], inst["initial"] + off, data, tag + " initial"),
                (ix["lvl"], inst["current"] + off, data, tag + " current")]
    return out


def designer_rows(ix: dict, entry: dict) -> list:
    rows = []
    for n, inst in enumerate(entry["instances"]):
        if inst["safe"]:
            rows.append({"instance": n, "cannot_change": inst["safe"]})
            continue
        vs = []
        for var in range(len(entry["vars"])):
            try:
                kind, size, off = designer_field(ix, entry, inst, var)
            except ValueError:
                continue
            raw = ix["data"][inst["initial"] + off:inst["initial"] + off + size]
            vs.append({"variable": var, "kind": kind, "value": designer_value(kind, raw)})
        rows.append({"instance": n, "initial_sha256": designer_hash(ix, inst, entry["length"]), "variables": vs})
    return rows


def script_hash(ix: dict, na: int, nodes: list) -> str:
    return sha256_bytes(ix["data"][na:na + 8 * len(nodes)])


def compile_script_constants(ovs: list, paths, cache=None) -> list:
    out, cache = [], {} if cache is None else cache
    for o in ovs:
        where = f"script-constant {o['level']} {o['behavior']!r} script {o['script']} node {o['node']}"
        if o["level"] not in cache:
            cache[o["level"]] = read_script_index(paths["game"], o["level"])
        ix = cache[o["level"]]
        if o["behavior"] not in ix["behaviours"]:
            raise Refusal("TARGET_MISSING", f"{where}: no such behaviour in this level")
        scripts = ix["behaviours"][o["behavior"]]
        if scripts is None:
            raise Refusal("TARGET_CHANGED", f"{where}: the behaviour name is not unique in this level")
        if o["script"] >= len(scripts):
            raise Refusal("TARGET_MISSING", f"{where}: the behaviour has {len(scripts)} script(s)")
        na, nodes = scripts[o["script"]]
        if na is None or nodes is None or script_hash(ix, na, nodes) != o["script_sha256"]:
            raise Refusal("TARGET_CHANGED", f"{where}: the script is not the one this mod was made for")
        if o["node"] >= len(nodes):
            raise Refusal("TARGET_MISSING", f"{where}: the script has {len(nodes)} nodes")
        kind = nodes[o["node"]][2]
        off = na + 8 * o["node"]
        if kind != SCRIPT_KINDS[o["kind"]] or off in ix["slots"]:
            raise Refusal("TARGET_CHANGED", f"{where}: the node is type {kind:02X}, not a {o['kind']} constant")
        out.append((ix["lvl"], off, script_value_bytes(o, where), f"{o['level']}:{o['behavior']}#{o['script']}.{o['node']}"))
    return out


def compile_macro_constants(ovs: list, paths, cache=None) -> list:
    out, cache = [], {} if cache is None else cache
    for o in ovs:
        where = f"macro-constant {o['level']} {o['model']!r} macro {o['macro']} node {o['node']}"
        if o["level"] == "fix":
            raise Refusal("UNSUPPORTED", f"{where}: macros of fix.lvl cannot be changed (any level may call them)")
        if o["level"] not in cache:
            cache[o["level"]] = read_script_index(paths["game"], o["level"])
        ix = cache[o["level"]]
        if o["model"] not in ix["models"]:
            raise Refusal("TARGET_MISSING", f"{where}: no AI model with this first behaviour in this level")
        macros = ix["models"][o["model"]]
        if macros is None:
            raise Refusal("TARGET_CHANGED", f"{where}: the model is not unique in this level")
        if o["macro"] >= len(macros):
            raise Refusal("TARGET_MISSING", f"{where}: the model has {len(macros)} macro(s)")
        mac = macros[o["macro"]]
        if mac["safe"]:
            raise Refusal("UNSUPPORTED", f"{where}: {mac['safe']}")
        na, nodes = mac["nodes_at"], mac["nodes"]
        if script_hash(ix, na, nodes) != o["script_sha256"]:
            raise Refusal("TARGET_CHANGED", f"{where}: the macro is not the one this mod was made for")
        if o["node"] >= len(nodes):
            raise Refusal("TARGET_MISSING", f"{where}: the macro has {len(nodes)} nodes")
        kind = nodes[o["node"]][2]
        off = na + 8 * o["node"]
        if kind != SCRIPT_KINDS[o["kind"]] or off in ix["slots"]:
            raise Refusal("TARGET_CHANGED", f"{where}: the node is type {kind:02X}, not a {o['kind']} constant")
        out.append((ix["lvl"], off, script_value_bytes(o, where), f"{o['level']}:{o['model']}!{o['macro']}.{o['node']}"))
    return out


def script_constant_rows(ix: dict, nodes: list) -> list:
    rows = []
    for k, (p, ind, kind) in enumerate(nodes):
        if kind == SCRIPT_KINDS["int"]:
            rows.append({"node": k, "kind": "int", "value": struct.unpack(">i", struct.pack(">I", p))[0]})
        elif kind == SCRIPT_KINDS["real"]:
            rows.append({"node": k, "kind": "real", "value": float(f"{struct.unpack('>f', struct.pack('>I', p))[0]:.9g}")})
    return rows


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
    consts = [o for o in m["overrides"] if o["type"] == "script-constant"]
    mconsts = [o for o in m["overrides"] if o["type"] == "macro-constant"]
    dflts = [o for o in m["overrides"] if o["type"] == "designer-default"]
    places = [o for o in m["overrides"] if o["type"] == "actor-position"]
    places_w = [o for o in m["overrides"] if o["type"] == "waypoint-position"]
    if consts or mconsts or dflts or places or places_w:   # D-223 / D-226 / D-227 / D-228: logic edits apply whole or not at all
        cache = {}
        out += (compile_script_constants(consts, paths, cache) + compile_macro_constants(mconsts, paths, cache)
                + compile_designer_defaults(dflts, paths, cache) + compile_actor_positions(places, paths, cache)
                + compile_waypoint_positions(places_w, paths, cache))
        linked = True
    colls = [o for o in m["overrides"] if o["type"] == "collision-vertex-offset"]
    if colls:   # G6-P13 (D-266): the preset's ranges apply whole or not at all
        out += compile_collision_vertex_offset(colls[0], paths)
        linked = True
    terr = [o for o in m["overrides"] if o["type"] == "terrain-patch"]
    if terr:   # G6-P17 (D-273): the patch's ranges apply whole or not at all
        out += compile_terrain_patch(terr[0]["patch"], paths)[1]
        linked = True
    structs = [o for o in m["overrides"] if o["type"] == "insert-graph-node"]
    if structs:   # G5-P1 (D-243): one level transaction; applies whole or not at all, never shadowed
        rs, m["_tx"] = compile_insert_graph_nodes(structs, paths)   # G5-P5 (D-249): all of them, one transaction
        out += rs
        linked = True
    lums = [o for o in m["overrides"] if o["type"] == "insert-passive-lum"]
    if lums:   # G6-P1 (D-251): one version-2 level transaction (lvl, ptr, transit); whole or nothing, never shadowed
        rs, m["_tx"] = compile_insert_passive_lum(lums[0], paths)
        out += rs
        linked = True
    frogs = [o for o in m["overrides"] if o["type"] == "insert-scripted-frog"]
    if frogs:   # G6-P2 (D-254): one version-2 level transaction (lvl, ptr, transit); whole or nothing
        rs, m["_tx"] = compile_insert_scripted_frog(frogs[0], paths)
        out += rs
        linked = True
    mixes = [o for o in m["overrides"] if o["type"] in ("insert-fairy-with-terrain", "level-patch")]
    if mixes:   # G6-P20 (D-276): one version-2 level transaction (lvl, ptr, transit) carrying fairy and terrain;
        # G6-P21 (D-277): a level-patch selects the same compiler's inputs
        if mixes[0]["type"] == "level-patch":
            _, rs, m["_tx"] = compile_level_patch(mixes[0]["patch"], paths)
        else:
            rs, m["_tx"] = compile_insert_fairy_with_terrain(mixes[0], paths)
        out += rs
        linked = True
    fairies = [o for o in m["overrides"] if o["type"] == "insert-fairy-on-graph"]
    if fairies:   # G6-P3 (D-256): one version-2 level transaction (lvl, ptr, transit); whole or nothing
        rs, m["_tx"] = compile_insert_fairy_on_graph(fairies[0], paths)
        out += rs
        linked = True
    mgrs = [o for o in m["overrides"] if o["type"] == "insert-gensound-manager"]
    if mgrs:   # G6-P4 (D-257): one version-2 level transaction (lvl, ptr, transit); whole or nothing
        rs, m["_tx"] = compile_insert_gensound_manager(mgrs[0], paths)
        out += rs
        linked = True
    toads = [o for o in m["overrides"] if o["type"] == "insert-toad-intro"]
    if toads:   # G6-P8 (D-261): one version-2 level transaction (lvl, ptr, transit); whole or nothing
        rs, m["_tx"] = compile_insert_toad_intro(toads[0], paths)
        out += rs
        linked = True
    pairs = [o for o in m["overrides"] if o["type"] == "insert-toad-intro-pair"]
    if pairs:   # G6-P9 (D-262): one version-2 level transaction (lvl, ptr, transit) for both Toads; whole or nothing
        rs, m["_tx"] = compile_insert_toad_intro_pair(pairs[0], paths)
        out += rs
        linked = True
    lts = [o for o in m["overrides"] if o["type"] == "insert-lum-toad-pair"]
    if lts:   # G6-P11 (D-264): one version-2 level transaction (lvl, ptr, transit) for the Lum and the Toad
        rs, m["_tx"] = compile_insert_lum_toad_pair(lts[0], paths)
        out += rs
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


# ---------------------------------------------------------------------------------------------------------------
# G5-P2b (D-245): development-only structural-session recovery marker. MODS\structural_session.json exists while a
# launch with an active structural transaction (G5-P1) may be running: written durably (temporary file, flush, fsync,
# atomic replace, read back) by `plan` right after the plan that activates it and before the launcher starts the game;
# cleared only by `structural-end` for the same session and plan after a controlled exit. While any marker exists (also
# an unreadable or malformed one), structural mods are refused (STRUCTURAL_RECOVERY) and every other mod applies as
# before; `structural-recovery clear` is the explicit re-authorization. The marker belongs to this mods folder (one
# home / private profile); it holds no game data and never touches saves. It names no cause of a crash.

STRUCT_MARKER = "structural_session.json"
MARKER_SCHEMA = 1
SESSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def structural_marker_path(paths) -> Path:
    return Path(paths["mods"]) / STRUCT_MARKER


def read_structural_marker(paths) -> tuple:
    """("none" | "armed" | "malformed", data or None). A marker that cannot be read counts as present."""
    p = structural_marker_path(paths)
    try:
        if not p.exists() and not p.is_symlink():
            return "none", None
        st = os.lstat(p)
        if not stat.S_ISREG(st.st_mode) or st.st_size > 65536:
            return "malformed", None
        d = json.loads(p.read_bytes().decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return "malformed", None
    ok = (isinstance(d, dict) and d.get("schema") == MARKER_SCHEMA and isinstance(d.get("session"), str)
          and SESSION_RE.match(d["session"]) and isinstance(d.get("plan_sha256"), str)
          and re.fullmatch(r"[0-9a-f]{64}", d["plan_sha256"]) and isinstance(d.get("mods"), list)
          and all(isinstance(x, str) and ID_RE.match(x) for x in d["mods"]) and isinstance(d.get("levels"), list))
    return ("armed", d) if ok else ("malformed", None)


def write_structural_marker(paths, session: str, plan: Path, structural: dict) -> dict:
    """Durably records an active structural session; returns the marker, or raises OSError (then nothing is armed)."""
    p = structural_marker_path(paths)
    d = {"schema": MARKER_SCHEMA, "session": session, "plan_sha256": sha256_bytes(Path(plan).read_bytes()),
         "mods": sorted(structural), "levels": sorted(set(structural.values())), "written_at": now()}
    body = json.dumps(d, indent=1).encode("utf-8")
    tmp = p.with_name(f"{STRUCT_MARKER}.tmp-{os.getpid()}")
    try:
        with open(tmp, "wb") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
        if p.read_bytes() != body:
            raise OSError("the marker did not read back as written")
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return d


def end_structural_session(paths, session: str, plan_sha: str, controlled: bool) -> dict:
    """Clears the marker only for the same session and plan after a controlled exit; otherwise keeps it."""
    state, d = read_structural_marker(paths)
    if state != "armed":
        return {"cleared": False, "marker": state}
    if d["session"] != session or d["plan_sha256"] != plan_sha:
        return {"cleared": False, "marker": "armed", "reason": "another session's marker"}
    if not controlled:
        return {"cleared": False, "marker": "armed", "reason": "the session did not end normally"}
    structural_marker_path(paths).unlink()
    return {"cleared": True, "marker": "none"}


def resolve_all(paths, write_plan=None, session=None, _structural_block=None) -> dict:
    """Validates every installed mod and, in priority order, decides what applies. With write_plan=DIR also writes
    the launch plan there (G5-P2b: and arms the structural-session marker when the plan activates a structural mod).
    Returns the per-mod report."""
    recover(paths)
    state = load_state(paths)
    marker_state, marker = read_structural_marker(paths) if paths.get("mods") else ("none", None)
    if _structural_block is None and marker_state != "none":
        _structural_block = ("STRUCTURAL_RECOVERY",
                             f"a structural session ({marker['session'] if marker else 'unreadable marker'}) did not "
                             "end normally; structural mods are off for this launch (`structural-recovery clear` "
                             "re-enables them)")
    report, applied, claimed = [], {}, []  # claimed: (file, lo, hi, mod id)
    manifests, ach_rows = {}, {}
    for e in state["mods"]:
        r = {"id": e["id"], "enabled": e["enabled"], "state": "disabled", "detail": "", "name": e["id"], "version": "",
             "description": "", "overrides": 0, "ranges": 0, "shadowed": [], "gameplay": False}
        report.append(r)
        try:
            files = load_installed(paths, e["id"])
            m = parse_manifest(files)
            if m["id"] != e["id"]:
                raise Refusal("DAMAGED", f"{e['id']}: manifest id {m['id']}")
            manifests[e["id"]] = m
            r.update(name=m["name"], version=m["version"], description=m.get("description", ""),
                     overrides=len(m["overrides"]), gameplay=changes_game_logic(m))
            if not e["enabled"]:
                check_compat(m, paths)
                continue
            for other in applied:
                if other in m.get("conflicts", []) or m["id"] in manifests[other].get("conflicts", []):
                    raise Refusal("CONFLICT", f"conflicts with {other}")
            ranges = compile_mod(m, files, paths, manifests)
            if m.get("_tx") and _structural_block:   # G5-P2b: recovery marker or marker write failure
                raise Refusal(*_structural_block)
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
    # G5-P1 (D-243): one structural mod per level; two or more refuse all of them (no priority among structures)
    by_level = {}
    for mid in [i for i in order if i in applied and applied[i][0].get("_tx")]:
        by_level.setdefault(applied[mid][0]["_tx"]["level"], []).append(mid)
    for level, mids in by_level.items():
        if len(mids) > 1:
            for mid in mids:
                del applied[mid]
                next(x for x in report if x["id"] == mid).update(
                    state="invalid", code="STRUCTURAL_CONFLICT",
                    detail=f"one structural mod per level: {', '.join(q for q in mids if q != mid)} also changes the "
                           f"structure of {level}")
    drop_missing_dependencies()
    # M34: glyph records point into their mod's atlas and moved text into that mod's own slots, so such a mod applies
    # whole or not at all: a higher-priority mod over any of its bytes refuses it (and what requires it), then the
    # priority pass starts again without it.
    while True:
        seen, refused_one = [], False
        for mid in [i for i in order if i in applied]:
            m, ranges = applied[mid]
            structural = bool(m.get("_tx"))
            # G5-P1: a fixed-size mod is not shadowed by a higher structural one either: it is refused whole
            over = next((c for path, off, data, what in ranges for c in seen
                         if c[0] == path and c[1] < off + len(data) and off < c[2]
                         and (m.get("_linked") or c[4])), None)
            if over:
                del applied[mid]
                if structural:
                    code, detail = "STRUCTURAL_CONFLICT", f"changes the level structure, and {over[3]} changes the same data"
                elif over[4]:
                    code, detail = "STRUCTURAL_CONFLICT", f"changes data that {over[3]}'s level structure change owns"
                else:
                    code, detail = "CONFLICT", f"adds glyphs or moves text, and {over[3]} changes the same data"
                next(x for x in report if x["id"] == mid).update(state="invalid", code=code, detail=detail)
                drop_missing_dependencies()
                refused_one = True
                break
            seen += [(path, off, off + len(data), mid, structural) for path, off, data, what in ranges]
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
            if owner and (m.get("_tx") or applied[owner[3]][0].get("_tx")):   # G5-P1: settled above
                raise RuntimeError(f"structural range {what} of {mid} would be shadowed")
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
    result["structural_active"] = {i: applied[i][0]["_tx"]["level"] for i in result["active"]
                                   if applied[i][0].get("_tx")}   # G5-P1 (D-243)
    # D-224: applied mods whose validated overrides change game logic; the plan names them (`gameplay` records).
    result["gameplay_active"] = [i for i in result["active"] if changes_game_logic(manifests[i])]
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
                                          [(i, manifests[i]["version"]) for i in result["active"]],
                                          result["gameplay_active"],
                                          [(i, applied[i][0]["_tx"]) for i in result["active"]
                                           if applied[i][0].get("_tx")])
        result["achievement_text"] = write_achievement_text(Path(write_plan), sorted(ach.values()))
        if result["structural_active"] and result["plan"]:   # G5-P2b: arm before the launcher can start the game
            sid = session or f"plan-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
            try:
                if not SESSION_RE.match(sid):
                    raise OSError("invalid session id")
                result["structural_marker"] = write_structural_marker(paths, sid, Path(result["plan"]),
                                                                      result["structural_active"])
            except OSError as x:   # never launch a structural transaction without its marker
                return resolve_all(paths, write_plan, session, ("STRUCTURAL_MARKER",
                                   f"the structural-session marker could not be written ({x}); structural mods are "
                                   "off for this launch"))
    result["structural_recovery"] = marker_state
    return result


def fnv_cached(cache: dict, data: bytes) -> str:
    k = sha256_bytes(data)
    if k not in cache:
        cache[k] = f"{fnv1a64(data):016x}"
    return cache[k]


def changes_game_logic(m: dict) -> bool:
    """D-224: a validated manifest that changes game logic (script constants, D-223). Decided from the override
    types parse_manifest accepted, never from the mod's own description."""
    return any(o["type"] in ("script-constant", "macro-constant", "designer-default", "actor-position",
                             "waypoint-position", "insert-graph-node", "insert-passive-lum",
                             "insert-scripted-frog", "insert-fairy-on-graph", "insert-fairy-with-terrain",
                             "insert-gensound-manager", "insert-toad-intro", "insert-toad-intro-pair",
                             "insert-lum-toad-pair", "collision-vertex-offset", "terrain-patch", "level-patch")
               for o in m["overrides"])


def write_plan_files(paths, out: Path, ranges, mods, gameplay=(), txs=()) -> str:
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
    lines += [f"gameplay {i}" for i in gameplay]   # D-224: a runtime before D-224 refuses such a plan
    keep = set()
    body = []
    ends = {}
    for path, off, data, mid in ranges:
        path = Path(os.path.abspath(path))
        ends[path] = max(ends.get(path, 0), off + len(data))
    # G5-P1 (D-243): one `level-tx` per structural mod, then per member file (right after its `file` record) one
    # `tx-file`: role, original sha256, guest size and the sha256 of what the guest reads (the original with the
    # transaction mod's ranges). Only a development runtime accepts them; any other refuses the plan as a whole.
    tx_member = {}
    for mid, tx in txs:
        members = []
        same_size = tx.get("same_size", ())   # G6-P1 (D-251): transit.lvl is edited in place, never grown
        for role, (p, size, orig) in sorted(tx["files"].items()):
            p = Path(os.path.abspath(p))
            data = p.read_bytes()
            if len(data) != size or sha256_bytes(data) != orig:
                raise Refusal("TARGET_CHANGED", f"{p.name} changed while the plan was written")
            image = bytearray(data) + bytes(max(0, ends.get(p, 0) - len(data)))
            for path, off, blob, owner in ranges:
                if owner == mid and Path(os.path.abspath(path)) == p:
                    image[off:off + len(blob)] = blob
            if role in same_size:
                if len(image) != size or bytes(image) == data:
                    raise Refusal("STRUCTURE_CHECK", f"{p.name}: a same-size member that grows or does not change")
            elif len(image) <= size:
                raise Refusal("STRUCTURE_CHECK", f"{p.name}: a structural transaction that does not grow the file")
            tx_member[p] = (role, orig, len(image), sha256_bytes(bytes(image)))
            members.append((role, p.name, size, orig, len(image), tx_member[p][3]))
        version = tx.get("version", TX_VERSION)
        lines.append(f"level-tx {version} {tx['level']} {mid} {tx_id(tx['level'], mid, members, version)}")
    for path, off, data, mid in ranges:
        path = Path(os.path.abspath(path))
        if path not in files:
            files.append(path)
            size = path.stat().st_size
            lines.append(f"file {size} {path}")
            if path in tx_member:
                role, orig, guest, result = tx_member[path]
                lines.append(f"tx-file {len(files) - 1} {role} {orig} {guest} {result}")
            if ends[path] > size and path in tx_member:   # G5-P1 (D-243): a development level transaction's member
                lines.append(f"grow {len(files) - 1} {ends[path]}")
            elif ends[path] > size:   # M36 (D-073): only a grown VS.sub reaches past its file's end
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

def cmd_terrain_patch(paths, source: Path, out_dir=None) -> dict:
    """G6-P17 (D-273): validate and compile one terrain-patch-v1 file against the person's own level files; report its
    identity and every changed range; with --out, also write a private mod folder (mod.json only) for `import`."""
    if not source.is_file():
        raise Refusal("USAGE", f"terrain-patch PATCH.json: {source} is not a file")
    canon, eds = compile_terrain_patch(_terrain_json(source.read_bytes(), source.name), paths, source.name)
    r = {"patch": {"format": canon["format"], "level": canon["level"], "region": canon["region"],
                   "name": canon["name"], "identity_sha256": terrain_identity(canon),
                   "groups": [{"name": g["name"], "vertices": g["vertices"], "delta_z": g["delta_z"]}
                              for g in canon["groups"]]},
         "file": eds[0][0].name if eds else None, "range_count": len(eds), "bytes": sum(len(d) for _, _, d, _ in eds),
         "gameplay": True, "development_only": True,
         "ranges": [{"offset": o, "length": len(d), "what": w.split(" ", 1)[1]} for _, o, d, w in eds]}
    if out_dir is not None:
        if out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
            raise Refusal("USAGE", f"--out {out_dir}: must be a new or empty folder")
        m = {"format": FORMAT, "id": f"terrain.{canon['name']}", "name": f"Terrain patch {canon['name']}",
             "version": "1.0.0", "description": canon.get("description", "") or f"{TERRAIN_FORMAT} {canon['name']}",
             "target": {"title_id": TITLE_ID, "releases": release_ids(paths), "min_port_version": "0.0.1"},
             "overrides": [{"type": "terrain-patch", "patch": canon}]}
        parse_manifest({"mod.json": json.dumps(m).encode("utf-8")})
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "mod.json").write_text(json.dumps(m, indent=1) + "\n", encoding="utf-8")
        r["mod"] = {"id": m["id"], "folder": str(out_dir)}
    return r


def cmd_level_patch(paths, source: Path, out_dir=None, check=False) -> dict:
    """G6-P21 (D-277): validate and compile one level-patch-v1 file against the person's own level files; report its
    components, transaction identity, ranges and growth; with --out, also write a private mod folder (mod.json only)
    for `import`. Nothing is written unless the whole patch compiles. G6-P24 (D-280): every accepted patch also gets
    the preview report (level_patch_preview); --check is the explicit non-writing form (never with --out)."""
    if check and out_dir is not None:
        raise Refusal("USAGE", "level-patch --check writes nothing; leave out --out (or drop --check to write a mod)")
    if not source.is_file():
        raise Refusal("USAGE", f"level-patch PATCH.json: {source} is not a file")
    if out_dir is not None and out_dir.exists() and (not out_dir.is_dir() or any(out_dir.iterdir())):
        raise Refusal("USAGE", f"--out {out_dir}: must be a new or empty folder")
    canon, ranges, tx = compile_level_patch(_terrain_json(source.read_bytes(), source.name), paths, source.name)
    ts = transaction_summary(canon["id"], tx)
    terr = [r for r in ranges if ".terrain." in r[3]]
    rte = [r for r in ranges if ".route." in r[3]]   # G6-P28 (D-284)
    r = {"patch": {"format": canon["format"], "level": canon["level"], "id": canon["id"],
                   "identity_sha256": level_patch_identity(canon), "components": canon["components"]},
         "transaction": {"level": tx["level"], **ts},
         "growth": {k: len(tx["images"][k]) - tx["files"][k][1] for k in ("lvl", "ptr", "transit")},
         "range_count": len(ranges), "terrain_ranges": len(terr),
         "fairylight_ranges": len(ranges) - len(terr) - len(rte),
         "gameplay": True, "development_only": True, "check": bool(check),
         "preview": level_patch_preview(canon, ranges, tx, paths)}
    r["development_only"] = r["preview"]["authorization"]["development_only"]   # G6-P30 (D-286)
    if rte:
        r["route_ranges"] = len(rte)
    if out_dir is not None:
        m = {"format": FORMAT, "id": canon["id"], "name": f"Level patch {canon['id']}", "version": "1.0.0",
             "description": canon.get("description", "") or f"{LEVEL_PATCH_FORMAT} {canon['id']}",
             "target": {"title_id": TITLE_ID, "releases": release_ids(paths), "min_port_version": "0.0.1"},
             "overrides": [{"type": "level-patch", "patch": canon}]}
        parse_manifest({"mod.json": json.dumps(m).encode("utf-8")})
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "mod.json").write_text(json.dumps(m, indent=1) + "\n", encoding="utf-8")
        r["mod"] = {"id": m["id"], "folder": str(out_dir)}
    return r


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


def cmd_macro_info(paths, level: str, model: str) -> dict:
    """D-226: the macros of the AI models whose key (first normal behaviour's full name) contains `model`: per macro
    its node count, script_sha256, int / real constants, or why it cannot be changed. D-227: per actor instance of
    the model in this file, its initial_sha256 and the bool / byte / int / real designer variables that can change.
    D-228: per actor of the model in this file, its matrix_sha256, matrix type and initial position."""
    ix = read_script_index(paths["game"], level)
    rows = []
    for key in sorted(ix["models"]):
        if model.lower() not in key.lower():
            continue
        macros = ix["models"][key]
        if macros is None:
            rows.append({"model": key, "note": "model not unique in this level: cannot be changed"})
            continue
        out = []
        for i, mac in enumerate(macros):
            cannot = mac["safe"] or ("macros of fix.lvl: any level may call them" if level == "fix" else "")
            out.append({"macro": i, "nodes": len(mac["nodes"]) if mac["nodes"] else None,
                        "script_sha256": None if cannot else script_hash(ix, mac["nodes_at"], mac["nodes"]),
                        "cannot_change": cannot or None,
                        "constants": [] if cannot else script_constant_rows(ix, mac["nodes"])})
        entry = ix["defaults"].get(key)
        inst = (([] if not entry else designer_rows(ix, entry)) if level != "fix"
                else [{"note": "designer variables of fix.lvl cannot be changed"}])
        places = ix["placements"].get(key)
        place = (([] if not places else placement_rows(ix, places, key)) if level != "fix"
                 else [{"note": "actors of fix.lvl cannot be moved"}])
        graphs = waypoint_rows(ix, key) if level != "fix" else [{"note": "waypoints of fix.lvl cannot be moved"}]
        rows.append({"model": key, "macros": out, "instances": inst, "placements": place, "graphs": graphs})
    return {"level": level, "models": rows, "note": "game-derived: keep it private"}


def cmd_script_info(paths, level: str, behavior=None) -> dict:
    """D-223: the behaviours of a level (fix for fix.lvl). With --behavior TEXT (part of a name, any case): each
    script's node count, script_sha256 and its int / real constants, the values a script-constant override names."""
    if not SCRIPT_LEVEL_RE.match(level):
        raise Refusal("USAGE", "script-info LEVEL: a level folder name such as intro_10, or fix")
    ix = read_script_index(paths["game"], level)
    rows = []
    for nm in sorted(ix["behaviours"]):
        scripts = ix["behaviours"][nm]
        if behavior is not None and behavior.lower() not in nm.lower():
            continue
        if scripts is None:
            rows.append({"behavior": nm, "note": "name not unique in this level: cannot be changed"})
            continue
        if behavior is None:
            rows.append({"behavior": nm, "scripts": len(scripts),
                         "constants": sum(len(script_constant_rows(ix, s[1])) for s in scripts if s[1] is not None)})
            continue
        rows.append({"behavior": nm, "scripts": [
            {"script": j, "nodes": None if nodes is None else len(nodes),
             "script_sha256": None if nodes is None else script_hash(ix, na, nodes),
             "constants": [] if nodes is None else script_constant_rows(ix, nodes)}
            for j, (na, nodes) in enumerate(scripts)]})
    return {"level": level, "behaviors": rows, "note": "game-derived: keep it private"}


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
        check("D-224: a texture + text mod is not gameplay-affecting (no flag, no plan record)",
              res["gameplay_active"] == [] and res["mods"][0]["gameplay"] is False and "\ngameplay " not in plan, res)
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
    selftest_actor_primitives(check, refused)
    selftest_script(check, refused)
    selftest_macro(check, refused)
    selftest_designer(check, refused)
    selftest_placement(check, refused)
    selftest_waypoint(check, refused)
    selftest_collision(check, refused)
    selftest_terrain(check, refused)
    # G5-P1 (D-243): the development-only structural operation is refused unless explicitly enabled
    saved = os.environ.pop(STRUCT_ENV, None)
    try:
        o = {"type": "insert-graph-node", "level": "intro_10", "model": FLY10, "instance": 0, "variable": 0,
             "after_node": 13, "lvl_sha256": "0" * 64, "ptr_sha256": "0" * 64, "position": [0.0, 0.0, 0.0]}
        check("structural (D-243): insert-graph-node is refused without the development opt-in",
              refused(lambda: parse_insert_graph_node(o, "o"), "UNSUPPORTED") is True
              and refused(lambda: compile_insert_graph_node(o, {"game": Path(".")}), "UNSUPPORTED") is True)
        os.environ[STRUCT_ENV] = "intro_10"
        check("structural (D-243): enabled, only allow-listed levels and exact keys are accepted",
              refused(lambda: parse_insert_graph_node(dict(o, level="intro_15"), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_graph_node(dict(o, offset=4), "o"), "BAD_MANIFEST") is True)
        # G5-P4a (D-247): the second level is allow-listed with its own files, graph, node and measured memory only
        os.environ[STRUCT_ENV] = "intro_20"
        o20 = dict(o, level="intro_20", model=FAIRY20, instance=2, variable=2, after_node=3)
        check("structural (D-247): intro_20 is allow-listed with exactly one graph and node and a measured budget",
              parse_insert_graph_node(o20, "o") is None and set(STRUCT_ALLOW) == set(STRUCT_MEMORY)
              == {"intro_10", "intro_20"} and STRUCT_ALLOW["intro_20"]["graphs"] == {(FAIRY20, 2, 2): (3,)}
              and refused(lambda: parse_insert_graph_node(dict(o20, level="intro_17"), "o"), "UNSUPPORTED") is True
              and refused(lambda: structural_budget("intro_17", 8, 8, 4, 0, "o"), "BUDGET") is True)
        # G5-P5 (D-249): two operations only on one graph of intro_10, distinct sites, refused before any file is read
        g = {"game": Path(".")}
        one20 = refused(lambda: compile_insert_graph_nodes([o20, dict(o20, after_node=1)], g), "UNSUPPORTED")
        os.environ[STRUCT_ENV] = "intro_10"
        check("structural (D-249): two operations need one graph and distinct sites; intro_20 takes one",
              STRUCT_MAX_OPS == {"intro_10": 2}
              and refused(lambda: compile_insert_graph_nodes([o, dict(o, after_node=22, variable=1)], g),
                          "BAD_MANIFEST") is True
              and refused(lambda: compile_insert_graph_nodes([o, dict(o)], g), "BAD_MANIFEST") is True
              and refused(lambda: compile_insert_graph_nodes([o, dict(o, after_node=22), dict(o, after_node=5)], g),
                          "UNSUPPORTED") is True
              and one20 is True)
        lo = {"type": "insert-passive-lum", "level": "intro_10", "model": LUM10, "instance": 6,
              "lvl_sha256": "0" * 64, "ptr_sha256": "0" * 64, "transit_sha256": "0" * 64,
              "position": [17.87, -101.22, -44.18]}
        lum_ok = parse_insert_passive_lum(lo, "o") is None
        os.environ.pop(STRUCT_ENV, None)
        check("structural (D-251): insert-passive-lum is development-only, exact keys, allow-listed level, version 2",
              lum_ok and refused(lambda: parse_insert_passive_lum(lo, "o"), "UNSUPPORTED") is True
              and refused(lambda: compile_insert_passive_lum(lo, g), "UNSUPPORTED") is True
              and set(LUM_ALLOW) == {"intro_10"} and TX_VERSION_ACTOR == 2 and TX_VERSION == 1
              and changes_game_logic({"overrides": [lo]})
              and tx_id("intro_10", "m", []) != tx_id("intro_10", "m", [], TX_VERSION_ACTOR))
        os.environ[STRUCT_ENV] = "intro_10"
        check("structural (D-251): insert-passive-lum refuses other levels, extra keys and a second structural op",
              refused(lambda: parse_insert_passive_lum(dict(lo, level="intro_20"), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_passive_lum(dict(lo, offset=4), "o"), "BAD_MANIFEST") is True
              and refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.lum", "name": "x", "version": "1.0.0", "overrides": [lo, dict(lo)],
                   "target": {"title_id": TITLE_ID, "releases": ["x"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True)
        fo = {"type": "insert-scripted-frog", "level": "intro_10", "model": FROG10, "instance": 2,
              "lvl_sha256": "0" * 64, "ptr_sha256": "0" * 64, "transit_sha256": "0" * 64, "placement": "at_source",
              "period_ms": 500}
        frog_ok = parse_insert_scripted_frog(fo, "o") is None and parse_insert_scripted_frog(
            dict(fo, period_ms=2000), "o") is None
        os.environ.pop(STRUCT_ENV, None)
        check("structural (D-254): insert-scripted-frog is development-only, exact keys, allow-listed level, presets",
              frog_ok and refused(lambda: parse_insert_scripted_frog(fo, "o"), "UNSUPPORTED") is True
              and refused(lambda: compile_insert_scripted_frog(fo, g), "UNSUPPORTED") is True
              and set(FROG_ALLOW) == {"intro_10"} and changes_game_logic({"overrides": [fo]}))
        os.environ[STRUCT_ENV] = "intro_10"
        check("structural (D-254): insert-scripted-frog refuses other presets, levels, extra keys and composition",
              refused(lambda: parse_insert_scripted_frog(dict(fo, period_ms=1000), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_scripted_frog(dict(fo, placement="flight_path"), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_scripted_frog(dict(fo, level="intro_20"), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_scripted_frog(dict(fo, offset=4), "o"), "BAD_MANIFEST") is True
              and refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.frog", "name": "x", "version": "1.0.0", "overrides": [fo, lo],
                   "target": {"title_id": TITLE_ID, "releases": ["x"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True)
        fg = {"type": "insert-fairy-on-graph", "level": "intro_20", "model": FAIRY20, "instance": 2,
              "lvl_sha256": "0" * 64, "ptr_sha256": "0" * 64, "transit_sha256": "0" * 64, "follow_graph_of": 0}
        fairy_ok = parse_insert_fairy_on_graph(fg, "o") is None and parse_insert_fairy_on_graph(
            dict(fg, follow_graph_of=1), "o") is None
        os.environ.pop(STRUCT_ENV, None)
        check("structural (D-256): insert-fairy-on-graph is development-only, exact keys, allow-listed level, targets",
              fairy_ok and refused(lambda: parse_insert_fairy_on_graph(fg, "o"), "UNSUPPORTED") is True
              and refused(lambda: compile_insert_fairy_on_graph(fg, g), "UNSUPPORTED") is True
              and set(FAIRY_ALLOW) == {"intro_20"} and set(FAIRY_ALLOW["intro_20"]["targets"]) == {0, 1}
              and changes_game_logic({"overrides": [fg]}))
        os.environ[STRUCT_ENV] = "intro_20"
        check("structural (D-256): insert-fairy-on-graph refuses other targets, levels, raw references and composition",
              refused(lambda: parse_insert_fairy_on_graph(dict(fg, follow_graph_of=4), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_fairy_on_graph(dict(fg, follow_graph_of=True), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_fairy_on_graph(dict(fg, follow_graph_of="0x3226a8"), "o"),
                          "UNSUPPORTED") is True
              and refused(lambda: parse_insert_fairy_on_graph(dict(fg, level="intro_10"), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_fairy_on_graph(dict(fg, graph=0x3226A8), "o"), "BAD_MANIFEST") is True
              and refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.fairy", "name": "x", "version": "1.0.0", "overrides": [fg, dict(fg)],
                   "target": {"title_id": TITLE_ID, "releases": ["x"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True
              and refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.fairy", "name": "x", "version": "1.0.0", "overrides": [fg, o20],
                   "target": {"title_id": TITLE_ID, "releases": ["x"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True)
        gq = {"type": "insert-gensound-manager", "level": "intro_10", "model": GM10, "instance": 0,
              "lvl_sha256": "0" * 64, "ptr_sha256": "0" * 64, "transit_sha256": "0" * 64, "moves_gensound_instance": 0}
        gm_ok = parse_insert_gensound_manager(gq, "o") is None and parse_insert_gensound_manager(
            dict(gq, moves_gensound_instance=1), "o") is None
        os.environ.pop(STRUCT_ENV, None)
        check("structural (D-257): insert-gensound-manager is development-only, exact keys, allow-listed level, targets",
              gm_ok and refused(lambda: parse_insert_gensound_manager(gq, "o"), "UNSUPPORTED") is True
              and refused(lambda: compile_insert_gensound_manager(gq, g), "UNSUPPORTED") is True
              and set(GMGR_ALLOW) == {"intro_10"} and set(GMGR_ALLOW["intro_10"]["targets"]) == {0, 1}
              and changes_game_logic({"overrides": [gq]}))
        os.environ[STRUCT_ENV] = "intro_10"
        check("structural (D-257): insert-gensound-manager refuses other targets, levels, raw references, composition",
              refused(lambda: parse_insert_gensound_manager(dict(gq, moves_gensound_instance=2), "o"),
                      "UNSUPPORTED") is True
              and refused(lambda: parse_insert_gensound_manager(dict(gq, moves_gensound_instance=False), "o"),
                          "UNSUPPORTED") is True
              and refused(lambda: parse_insert_gensound_manager(dict(gq, moves_gensound_instance="0x53a09c"), "o"),
                          "UNSUPPORTED") is True
              and refused(lambda: parse_insert_gensound_manager(dict(gq, level="intro_20"), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_gensound_manager(dict(gq, actor=0x53A09C), "o"), "BAD_MANIFEST") is True
              and refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.gm", "name": "x", "version": "1.0.0", "overrides": [gq, dict(gq)],
                   "target": {"title_id": TITLE_ID, "releases": ["x"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True
              and refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.gm", "name": "x", "version": "1.0.0", "overrides": [gq, fo],
                   "target": {"title_id": TITLE_ID, "releases": ["x"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True)
        tq = {"type": "insert-toad-intro", "level": "intro_10", "model": TOAD10, "instance": 1,
              "lvl_sha256": "0" * 64, "ptr_sha256": "0" * 64, "transit_sha256": "0" * 64, "placement": "at_source",
              "owner": "dynamic_world"}
        toad_ok = parse_insert_toad_intro(tq, "o") is None
        os.environ.pop(STRUCT_ENV, None)
        check("structural (D-261): insert-toad-intro is development-only, exact keys, allow-listed level, version 2",
              toad_ok and refused(lambda: parse_insert_toad_intro(tq, "o"), "UNSUPPORTED") is True
              and refused(lambda: compile_insert_toad_intro(tq, g), "UNSUPPORTED") is True
              and set(TOAD_ALLOW) == {"intro_10"} and changes_game_logic({"overrides": [tq]}))
        os.environ[STRUCT_ENV] = "intro_10"
        check("structural (D-261): insert-toad-intro refuses other placements, owners, levels, raw inputs, composition",
              refused(lambda: parse_insert_toad_intro(dict(tq, placement=[59.75, -256.08, -56.09]), "o"),
                      "UNSUPPORTED") is True
              and refused(lambda: parse_insert_toad_intro(dict(tq, placement="beside_source"), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_toad_intro(dict(tq, owner="0x581268"), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_toad_intro(dict(tq, level="intro_20"), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_toad_intro(dict(tq, offset=0x74E918), "o"), "BAD_MANIFEST") is True
              and refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.toad", "name": "x", "version": "1.0.0", "overrides": [tq, dict(tq)],
                   "target": {"title_id": TITLE_ID, "releases": ["x"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True
              and refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.toad", "name": "x", "version": "1.0.0", "overrides": [tq, gq],
                   "target": {"title_id": TITLE_ID, "releases": ["x"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True)
        pq = dict(tq, type="insert-toad-intro-pair", count=2)
        pair_ok = parse_insert_toad_intro_pair(pq, "o") is None

        def pman(ovs):
            return lambda: parse_manifest({"mod.json": json.dumps(
                {"format": 1, "id": "x.pair", "name": "x", "version": "1.0.0", "overrides": ovs,
                 "target": {"title_id": TITLE_ID, "releases": ["x"], "min_port_version": "0.0.1"}}).encode()})
        os.environ.pop(STRUCT_ENV, None)
        check("structural (D-262): insert-toad-intro-pair is development-only, exact keys, count 2, version 2",
              pair_ok and refused(lambda: parse_insert_toad_intro_pair(pq, "o"), "UNSUPPORTED") is True
              and refused(lambda: compile_insert_toad_intro_pair(pq, g), "UNSUPPORTED") is True
              and set(TOAD_PAIR_ALLOW) == {"intro_10"} and changes_game_logic({"overrides": [pq]}))
        os.environ[STRUCT_ENV] = "intro_10"
        check("structural (D-262): insert-toad-intro-pair refuses other counts, placements, levels, raw inputs, "
              "composition",
              all(refused(lambda c=c: parse_insert_toad_intro_pair(dict(pq, count=c), "o"), "UNSUPPORTED") is True
                  for c in (1, 3, True, "2"))
              and refused(lambda: parse_insert_toad_intro_pair({k: v for k, v in pq.items() if k != "count"}, "o"),
                          "BAD_MANIFEST") is True
              and refused(lambda: parse_insert_toad_intro_pair(dict(pq, placement="beside_source"), "o"),
                          "UNSUPPORTED") is True
              and refused(lambda: parse_insert_toad_intro_pair(dict(pq, level="intro_20"), "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_insert_toad_intro_pair(dict(pq, offset=0x74EDD8), "o"), "BAD_MANIFEST") is True
              and all(refused(pman(ovs), "BAD_MANIFEST") is True for ovs in ([pq, dict(pq)], [pq, tq], [tq, pq],
                                                                             [pq, gq])))
        hq = {"type": "insert-lum-toad-pair", "level": "intro_10", "lvl_sha256": "0" * 64, "ptr_sha256": "0" * 64,
              "transit_sha256": "0" * 64, "lum_model": LUM10, "lum_instance": 6, "lum_placement": "flight_path",
              "toad_model": TOAD10, "toad_instance": 1, "toad_placement": "at_source", "owner": "dynamic_world"}
        het_ok = parse_insert_lum_toad_pair(hq, "o") is None
        os.environ.pop(STRUCT_ENV, None)
        check("structural (D-264): insert-lum-toad-pair is development-only, exact keys, allow-listed level, version 2",
              het_ok and refused(lambda: parse_insert_lum_toad_pair(hq, "o"), "UNSUPPORTED") is True
              and refused(lambda: compile_insert_lum_toad_pair(hq, g), "UNSUPPORTED") is True
              and set(LUM_TOAD_ALLOW) == {"intro_10"} and changes_game_logic({"overrides": [hq]}))
        os.environ[STRUCT_ENV] = "intro_10"
        check("structural (D-264): insert-lum-toad-pair refuses other placements, owners, levels, raw inputs, "
              "composition",
              all(refused(lambda k=k, v=v: parse_insert_lum_toad_pair(dict(hq, **{k: v}), "o"), "UNSUPPORTED") is True
                  for k, v in (("lum_placement", "beside_source"), ("lum_placement", [17.87, -101.22, -44.18]),
                               ("toad_placement", "flight_path"), ("owner", "0x581268"), ("level", "intro_20")))
              and refused(lambda: parse_insert_lum_toad_pair(dict(hq, offset=0x74E910), "o"), "BAD_MANIFEST") is True
              and refused(lambda: parse_insert_lum_toad_pair({k: v for k, v in hq.items() if k != "owner"}, "o"),
                          "BAD_MANIFEST") is True
              and all(refused(pman(ovs), "BAD_MANIFEST") is True for ovs in ([hq, dict(hq)], [hq, tq], [pq, hq],
                                                                             [hq, gq])))
    finally:
        os.environ.pop(STRUCT_ENV, None)
        if saved is not None:
            os.environ[STRUCT_ENV] = saved
    n_fail = results.count(False)
    print(f"R3HD_MODS_SELFTEST {'PASS' if not n_fail else 'FAIL'} {len(results) - n_fail}/{len(results)}")
    return 1 if n_fail else 0


def selftest_macro(check, refused):
    """D-226: macro-constant overrides on synthetic levels: one AI model with three macros (editable; null; two
    different scripts), a self-call and a behaviour call; variants with a call from another model, a stray reference
    and a reference from the transit file."""
    bA = "Gen\\M_A\\M_A.rul^CreateIntelligence^CreateComport:A_Init"
    bA2 = "Gen\\M_A\\M_A.rul^CreateIntelligence^CreateComport:A_Idle"
    bB = "Gen\\M_B\\M_B.rul^CreateIntelligence^CreateComport:B_Init"

    def level(variant=""):
        lvl, slots = bytearray(0x1000), []

        def ptr(at, to):
            struct.pack_into(">I", lvl, at, to - 4)
            slots.append((1, at - 4))

        def nodes(at, rows):
            for k, (p, ind, kind) in enumerate(rows + [(0, 0, 0)]):
                struct.pack_into(">IHBB", lvl, at + 8 * k, p & 0xFFFFFFFF, 0, ind, kind)
        ptr(0x100, 0x200)
        struct.pack_into(">I", lvl, 0x104, 2)
        for i, (nm, count) in enumerate(((bA, 1), (bA2, 0))):
            r = 0x200 + i * BEHAVIOR_SIZE
            lvl[r:r + len(nm)] = nm.encode()
            lvl[r + 0x108] = count
        ptr(0x200 + 0x100, 0x500)
        ptr(0x500, 0x600)
        nodes(0x600, [(1, 1, 0x02), (0, 2, 0x29)])
        ptr(0x608, 0xC30)                       # A_Init calls macro 0
        ptr(0xC00, 0x100)                       # model A: normal list
        ptr(0xC0C, 0xC20)                       # model A: macro list
        ptr(0xC20, 0xC30)
        struct.pack_into(">I", lvl, 0xC24, 3 << 24)
        ptr(0xC30, 0xC60)
        ptr(0xC34, 0xC64)                       # macro 0: both scripts lead to 0xD00
        ptr(0xC60, 0xD00)
        ptr(0xC64, 0xD00)
        ptr(0xC40, 0xC68)                       # macro 1 (0xC38) stays null; macro 2: two different node arrays
        ptr(0xC44, 0xC6C)
        ptr(0xC68, 0xD80)
        ptr(0xC6C, 0xDC0)
        nodes(0xD00, [(1, 1, 0x02), (45, 2, 0x0C), (struct.unpack(">I", struct.pack(">f", 2.5))[0], 2, 0x0D),
                      (0, 2, 0x29), (0x00010002, 2, 0x1F)])
        ptr(0xD18, 0xC30)                       # macro 0 calls itself (own model)
        nodes(0xD80, [(7, 1, 0x0C)])
        nodes(0xDC0, [(7, 1, 0x0C)])
        if variant == "other":                  # model B's behaviour calls model A's macro 0
            ptr(0x108, 0x900)
            struct.pack_into(">I", lvl, 0x10C, 1)
            lvl[0x900:0x900 + len(bB)] = bB.encode()
            lvl[0x900 + 0x108] = 1
            ptr(0x900 + 0x100, 0xB00)
            ptr(0xB00, 0xB10)
            nodes(0xB10, [(0, 1, 0x29)])
            ptr(0xB10, 0xC30)
            ptr(0xC10, 0x108)                   # model B: normal list
        if variant == "data":
            ptr(0xE00, 0xC30)                   # a word that is no script node points at macro 0
        return bytes(lvl), struct.pack(">I", len(slots)) + b"".join(struct.pack(">iI", f, loc) for f, loc in slots)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        game = td / "game"
        for name, variant in (("lv", ""), ("lother", "other"), ("ldata", "data"), ("ltr", "")):
            (game / "GAMEDATAbin" / name).mkdir(parents=True)
            lvl, ptr = level(variant)
            (game / "GAMEDATAbin" / name / f"{name}.lvl").write_bytes(lvl)
            (game / "GAMEDATAbin" / name / f"{name}.ptr").write_bytes(ptr)
        tl = bytearray(16)
        struct.pack_into(">I", tl, 8, 0xC30 - 4)
        (game / "GAMEDATAbin" / "ltr" / "transit.lvl").write_bytes(bytes(tl))
        (game / "GAMEDATAbin" / "ltr" / "transit.ptr").write_bytes(struct.pack(">IiI", 1, 1, 4))
        lvl, _ = level()
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(lvl)
        (game / "GAMEDATAbin" / "fix.ptr").write_bytes(struct.pack(">I", 0))
        before = {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}
        paths = {"home": None, "mods": td / "mods", "cache": td / "cache", "game": game}
        ix = read_script_index(game, "lv")
        macs = ix["models"].get(bA)
        check("macro: the model is keyed by its first behaviour; macro 0 editable (5 nodes), 1 null, 2 two scripts",
              set(ix["models"]) == {bA} and len(macs) == 3 and not macs[0]["safe"] and len(macs[0]["nodes"]) == 5
              and "null" in macs[1]["safe"] and "not the same node array" in macs[2]["safe"]
              and ix["macro_refs"] == {"list_header": 1, "own_model": 2, "other_model": 0, "other_data": 0,
                                       "transit": 0}, (ix["models"], ix["macro_refs"]))
        h = script_hash(ix, macs[0]["nodes_at"], macs[0]["nodes"])

        def ov(**kw):
            o = {"type": "macro-constant", "level": "lv", "model": bA, "macro": 0, "node": 1, "script_sha256": h,
                 "kind": "int", "value": 60}
            o.update(kw)
            return o
        (p, off, data, _), = compile_macro_constants([ov()], paths)
        check("macro: an int constant is 4 bytes in place at its node", p.name == "lv.lvl" and off == 0xD08
              and data == struct.pack(">i", 60), (p, off, data))
        (_, off, data, _), = compile_macro_constants([ov(node=2, kind="real", value=0.5)], paths)
        check("macro: a real constant is a big-endian float32", off == 0xD10 and data == struct.pack(">f", 0.5))
        info = cmd_macro_info(paths, "lv", "a_init")["models"][0]["macros"]
        check("macro-info: hash and constants of macro 0; the reasons for 1 and 2",
              info[0]["script_sha256"] == h and info[0]["constants"] == [{"node": 1, "kind": "int", "value": 45},
                                                                          {"node": 2, "kind": "real", "value": 2.5}]
              and info[1]["cannot_change"] and info[2]["cannot_change"] and not info[0]["cannot_change"], info)
        for label, o, code in (("a relocated macro call (0x29)", ov(node=3), "TARGET_CHANGED"),
                               ("a load-rewritten node (0x1F)", ov(node=4), "TARGET_CHANGED"),
                               ("a real declared on an int node", ov(kind="real", value=1.0), "TARGET_CHANGED"),
                               ("a node index past the macro's", ov(node=5), "TARGET_MISSING"),
                               ("a null macro", ov(macro=1), "UNSUPPORTED"),
                               ("a macro whose two scripts differ", ov(macro=2), "UNSUPPORTED"),
                               ("a macro index past the model's", ov(macro=3), "TARGET_MISSING"),
                               ("a changed macro (other hash)", ov(script_sha256="0" * 64), "TARGET_CHANGED"),
                               ("an unknown model", ov(model=bA2), "TARGET_MISSING"),
                               ("a macro another model calls", ov(level="lother"), "UNSUPPORTED"),
                               ("a macro a non-script word points at", ov(level="ldata"), "UNSUPPORTED"),
                               ("a macro the transit file points at", ov(level="ltr"), "UNSUPPORTED"),
                               ("a macro of fix.lvl", ov(level="fix"), "UNSUPPORTED")):
            got = refused(lambda o=o: compile_macro_constants([o], paths), code)
            check(f"macro compile: refused: {label}", got is True, got)
        for label, o, code in (("an unknown key", ov(extra=1), "BAD_MANIFEST"),
                               ("a missing key", {k: v for k, v in ov().items() if k != "macro"}, "BAD_MANIFEST"),
                               ("fix.lvl", ov(level="fix"), "UNSUPPORTED"),
                               ("a kind other than int / real", ov(kind="actor"), "UNSUPPORTED"),
                               ("an int beyond int32", ov(value=1 << 31), "BAD_MANIFEST"),
                               ("a NaN real", ov(kind="real", value=float("nan")), "BAD_MANIFEST")):
            got = refused(lambda o=o: parse_macro_constant(o, "o"), code)
            check(f"macro manifest: refused: {label}", got is True, got)

        def mod(mid, overrides):
            d = td / "src" / mid
            d.mkdir(parents=True)
            (d / "mod.json").write_text(json.dumps(
                {"format": 1, "id": mid, "name": mid, "version": "1.0.0", "overrides": overrides,
                 "target": {"title_id": TITLE_ID, "releases": release_ids(paths), "min_port_version": "0.0.1"}}),
                encoding="utf-8")
            return d
        check("macro manifest: the same macro node twice is refused",
              refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.twice", "name": "x", "version": "1.0.0", "overrides": [ov(), ov(value=4)],
                   "target": {"title_id": TITLE_ID, "releases": ["r"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True)
        cmd_import(paths, mod("m.ok", [ov(), ov(node=2, kind="real", value=0.5)]), enable=True)
        check("macro import: a mod with one valid and one unsafe macro edit is refused whole; nothing is installed",
              refused(lambda: cmd_import(paths, mod("m.half", [ov(macro=0, node=2, kind="real", value=0.5),
                                                                ov(level="lother")]), enable=True),
                      "UNSUPPORTED") is True and not installed_dir(paths, "m.half").exists())
        res = resolve_all(paths, write_plan=paths["cache"])
        plan = Path(res["plan"]).read_text(encoding="utf-8")
        check("macro plan: the valid mod applies (2 ranges) and is named as changing game logic",
              res["active"] == ["m.ok"] and res["ranges"] == 2 and res["gameplay_active"] == ["m.ok"]
              and "\ngameplay m.ok\n" in plan and res["mods"][0]["gameplay"] is True, res)
        cmd_import(paths, mod("m.top", [ov(value=99)]), enable=True)
        cmd_move(paths, "m.top", "top")
        res = resolve_all(paths)
        low = next(x for x in res["mods"] if x["id"] == "m.ok")
        check("macro priority: a higher mod over one node refuses the whole lower macro mod",
              res["active"] == ["m.top"] and low["code"] == "CONFLICT", res["mods"])
        for mid in ("m.ok", "m.top"):
            cmd_set(paths, mid, False)
        res = resolve_all(paths, write_plan=paths["cache"])
        check("macro disabled: no plan, nothing gameplay-active, the mods stay marked",
              res["ranges"] == 0 and res["gameplay_active"] == [] and all(x["gameplay"] for x in res["mods"])
              and not (paths["cache"] / PLAN_NAME).exists(), res)
        check("macro: game files are never written", before == {p: p.read_bytes() for p in game.rglob("*") if p.is_file()})


def selftest_terrain(check, refused):
    """G6-P17 (D-273): terrain-patch-v1 schema, canonical form and policy without game data (the compiled geometry is
    checked against the person's exact file by tools/experiments/modding_feasibility/g6p17_terrain.py check)."""
    good = {"format": TERRAIN_FORMAT, "level": "intro_15", "lvl_sha256": COLLISION_ALLOW["intro_15"]["lvl"][1],
            "region": "spawn-ground-v1", "name": "t",
            "groups": [{"name": "a", "vertices": [393, 365, 392], "delta_z": -0.3},
                       {"name": "b", "vertices": [387, 388, 391, 394], "delta_z": -0.15}]}
    reg = terrain_region("intro_15", "spawn-ground-v1")
    check("G6-P17: region spawn-ground-v1 = the seven G6-P16 vertices, each with its verified visual twin",
          sorted(reg["vertices"]) == [365, 387, 388, 391, 392, 393, 394]
          and all(len(w) == 24 and len(vw) == 24 for w, _, vw in reg["vertices"].values()))
    c = parse_terrain_patch(good, "p")
    check("G6-P17: canonical form (groups by lowest vertex, vertices ascending, float displacement)",
          [g["vertices"] for g in c["groups"]] == [[365, 392, 393], [387, 388, 391, 394]]
          and all(type(g["delta_z"]) is float for g in c["groups"]))
    swapped = {**good, "groups": list(reversed(good["groups"]))}
    check("G6-P17: group order does not change the canonical patch or its identity",
          parse_terrain_patch(swapped, "p") == c and terrain_identity(parse_terrain_patch(swapped, "p")) == terrain_identity(c))
    ms = COLLISION_ALLOW["intro_15"]["presets"]["spawn-multi-surface-v1"]
    sp = terrain_spec(c)
    check("G6-P17: the G6-P16 patch maps onto the preset's groups, originals and visual twins",
          [g["vertices"] for g in sp["groups"]] == [g["vertices"] for g in ms["groups"]]
          and [g["dz"] for g in sp["groups"]] == [g["dz"] for g in ms["groups"]] and sp["visual"]["map"] == ms["visual"]["map"]
          and sp["bounds"] == "keep" and sp["min_normal_z"] == ms["min_normal_z"])

    def g(i, **kw):
        return {**good, "groups": [dict(x, **kw) if k == i else x for k, x in enumerate(good["groups"])]}
    for name, p, code in (("format", {**good, "format": "terrain-patch-v2"}, "UNSUPPORTED"),
                          ("level", {**good, "level": "intro_10"}, "UNSUPPORTED"),
                          ("region", {**good, "region": "x"}, "UNSUPPORTED"),
                          ("hash", {**good, "lvl_sha256": "0" * 64}, "TARGET_CHANGED"),
                          ("vertex outside the region", g(0, vertices=[365, 1]), "UNSUPPORTED"),
                          ("duplicate vertex", g(1, vertices=[387, 365]), "BAD_MANIFEST"),
                          ("NaN", g(0, delta_z=float("nan")), "BAD_MANIFEST"),
                          ("infinity", g(0, delta_z=float("inf")), "BAD_MANIFEST"),
                          ("boolean displacement", g(0, delta_z=True), "BAD_MANIFEST"),
                          ("too deep", g(0, delta_z=-0.31), "UNSUPPORTED"),
                          ("raising", g(0, delta_z=0.05), "UNSUPPORTED"),
                          ("unknown key", {**good, "offset": 1}, "BAD_MANIFEST"),
                          ("unknown group key", g(0, dz=-0.3), "BAD_MANIFEST"),
                          ("one group", {**good, "groups": good["groups"][:1]}, "BAD_MANIFEST"),
                          ("malformed group", {**good, "groups": [1, 2]}, "BAD_MANIFEST"),
                          ("not an object", [good], "BAD_MANIFEST")):
        check(f"G6-P17: refused: {name}", refused(lambda p=p: parse_terrain_patch(p, "p"), code) is True)
    check("G6-P17: NaN literal / duplicate key in a patch file refused",
          refused(lambda: _terrain_json(b'{"a": NaN}', "f"), "BAD_MANIFEST") is True
          and refused(lambda: _terrain_json(b'{"a": 1, "a": 2}', "f"), "BAD_MANIFEST") is True)
    old = os.environ.pop(STRUCT_ENV, None)
    try:
        ov = {"type": "terrain-patch", "patch": good}
        check("G6-P17: terrain-patch override refused while the development gate is off",
              refused(lambda: parse_terrain_override(dict(ov), "o"), "UNSUPPORTED") is True)
        check("G6-P17: compile refused while the gate is off",
              refused(lambda: compile_terrain_patch(good, {"game": Path(".")}), "UNSUPPORTED") is True)
        os.environ[STRUCT_ENV] = "intro_10"
        check("G6-P17: a gate naming another level does not enable the compile",
              refused(lambda: compile_terrain_patch(good, {"game": Path(".")}), "UNSUPPORTED") is True)
        os.environ[STRUCT_ENV] = "intro_15"
        check("G6-P17: override with an extra key refused",
              refused(lambda: parse_terrain_override({**ov, "preset": "x"}, "o"), "BAD_MANIFEST") is True)
        check("G6-P17: gameplay-affecting", changes_game_logic({"overrides": [ov]}) is True)
        os.environ[STRUCT_ENV] = "intro_10"   # G6-P18 (D-274): any one gate value enables parsing of both kinds
        lt = {"type": "insert-lum-toad-pair", "level": "intro_10", "lvl_sha256": "0" * 64, "ptr_sha256": "0" * 64,
              "transit_sha256": "0" * 64, "lum_model": LUM10, "lum_instance": 6, "lum_placement": "flight_path",
              "toad_model": TOAD10, "toad_instance": 1, "toad_placement": "at_source", "owner": "dynamic_world"}
        cv = {"type": "collision-vertex-offset", "level": "intro_15", "preset": "spawn-multi-surface-v1",
              "lvl_sha256": "0" * 64}

        def man(*ovs):
            return {"mod.json": json.dumps({"format": FORMAT, "id": "t.mix", "name": "t", "version": "1.0.0",
                                            "target": {"title_id": TITLE_ID, "releases": ["x"],
                                                       "min_port_version": "0.0.1"},
                                            "overrides": list(ovs)}).encode()}
        check("G6-P18: a terrain edit and a structural actor transaction in one mod are refused (either order, "
              "terrain-patch or preset); each alone parses",
              all(refused(lambda o_=o_: parse_manifest(man(*o_)), "BAD_MANIFEST") is True
                  for o_ in ([ov, lt], [lt, ov], [cv, lt]))
              and parse_manifest(man(ov))["id"] == "t.mix" and parse_manifest(man(lt))["id"] == "t.mix")
        os.environ[STRUCT_ENV] = "intro_20"   # G6-P20 (D-276): the composition pilot's manifest rules
        fx = {"type": "insert-fairy-with-terrain", "level": "intro_20", "model": FAIRY20, "instance": 2,
              "lvl_sha256": "0" * 64, "ptr_sha256": "0" * 64, "transit_sha256": "0" * 64, "follow_graph_of": 0,
              "terrain_preset": "start-two-step-v1"}
        fg = {k: v for k, v in fx.items() if k != "terrain_preset"} | {"type": "insert-fairy-on-graph"}
        check("G6-P20: insert-fairy-with-terrain parses alone; refuses other presets, extra / missing keys, any other "
              "structural operation or terrain edit in the same mod; gameplay-affecting",
              parse_insert_fairy_with_terrain(dict(fx), "o") is None
              and parse_manifest(man(fx))["id"] == "t.mix"
              and refused(lambda: parse_insert_fairy_with_terrain(dict(fx, terrain_preset="spawn-multi-surface-v1"), "o"),
                          "UNSUPPORTED") is True
              and refused(lambda: parse_insert_fairy_with_terrain(dict(fx, offset=4), "o"), "BAD_MANIFEST") is True
              and refused(lambda: parse_insert_fairy_with_terrain(fg | {"type": fx["type"]}, "o"), "BAD_MANIFEST") is True
              and all(refused(lambda o_=o_: parse_manifest(man(*o_)), "BAD_MANIFEST") is True
                      for o_ in ([fx, fx], [fx, fg], [fg, fx], [fx, cv], [fx, ov], [fg, cv]))
              and changes_game_logic({"overrides": [fx]}))
        # G6-P21 (D-277): level-patch-v1 schema refusals (synthetic; the compile is checked by g6p21_level_patch.py)
        lp = {"format": LEVEL_PATCH_FORMAT, "level": "intro_20", "id": "t.mix",
              "lvl_sha256": STRUCT_ALLOW["intro_20"]["lvl"][1], "ptr_sha256": STRUCT_ALLOW["intro_20"]["ptr"][1],
              "transit_sha256": FAIRY_ALLOW["intro_20"]["transit"][1],
              "components": [{"type": "terrain", "preset": "start-two-step-v1"},
                             {"type": "fairylight", "follow_graph_of": 0}]}
        T, F = lp["components"]
        lpo = {"type": "level-patch", "patch": lp}
        cl = parse_level_patch(lp, "o")
        bad = {"BAD_MANIFEST": [dict(lp, extra=1), {k: v for k, v in lp.items() if k != "id"}, dict(lp, id="Bad"),
                                dict(lp, components=[T]), dict(lp, components=[F]), dict(lp, components=[T, T, F]),
                                dict(lp, components=[T, F, F]), dict(lp, components=[]),
                                dict(lp, components=[T, dict(F, offset=4)]), dict(lp, lvl_sha256="0" * 63)],
               "UNSUPPORTED": [dict(lp, format="level-patch-v2"), dict(lp, level="intro_15"),
                               dict(lp, lvl_sha256="0" * 64), dict(lp, transit_sha256="0" * 64),
                               dict(lp, components=[dict(T, preset="spawn-multi-surface-v1"), F]),
                               dict(lp, components=[T, dict(F, follow_graph_of=2)]),
                               dict(lp, components=[T, dict(F, follow_graph_of=True)]),
                               dict(lp, components=[T, F, {"type": "toad"}])]}
        check("G6-P21: level-patch-v1 parses; canonical order terrain, fairylight; either input order -> the same "
              "canonical form and identity; graph B a distinct identity; the operation selected = G6-P20's",
              cl["components"] == [T, F] and parse_level_patch(dict(lp, components=[F, T]), "o") == cl
              and level_patch_identity(cl) == level_patch_identity(dict(cl, description="x"))
              and level_patch_identity(parse_level_patch(dict(lp, components=[T, dict(F, follow_graph_of=1)]), "o"))
              != level_patch_identity(cl)
              and level_patch_operation(cl) == dict(fx, lvl_sha256=lp["lvl_sha256"], ptr_sha256=lp["ptr_sha256"],
                                                    transit_sha256=lp["transit_sha256"]))
        check("G6-P21: level-patch-v1 refuses unknown / missing keys, bad id, duplicate / missing / extra / unknown "
              "components, unknown component keys, other version / level / source hash / preset / graph",
              all(refused(lambda p_=p_: parse_level_patch(p_, "o"), code) is True for code, ps in bad.items()
                  for p_ in ps)
              and refused(lambda: _terrain_json(b'{"format": 1, "format": 2}', "o"), "BAD_MANIFEST") is True)
        check("G6-P21: a level-patch mod parses; refused when its id differs from the mod id, with a second "
              "level-patch, with insert-fairy-with-terrain, a fairy, a terrain edit or an actor transaction; "
              "gameplay-affecting",
              parse_manifest(man(lpo))["id"] == "t.mix"
              and refused(lambda: parse_manifest(man({"type": "level-patch", "patch": dict(lp, id="t.other")})),
                          "BAD_MANIFEST") is True
              and refused(lambda: parse_manifest(man(dict(lpo, extra=1))), "BAD_MANIFEST") is True
              and all(refused(lambda o_=o_: parse_manifest(man(*o_)), "BAD_MANIFEST") is True
                      for o_ in ([lpo, lpo], [lpo, fx], [fx, lpo], [lpo, fg], [lpo, cv], [lpo, ov], [lpo, lt]))
              and changes_game_logic({"overrides": [lpo]}))
        # G6-P22 (D-278): intro_20 region start-floor-v1 and the embedded terrain-patch form of a terrain component
        tp20 = {"format": TERRAIN_FORMAT, "level": "intro_20", "lvl_sha256": COLLISION_ALLOW["intro_20"]["lvl"][1],
                "region": "start-floor-v1", "name": "start-two-step-v1",
                "groups": [{"name": "spawn-corner", "vertices": [0], "delta_z": -0.3},
                           {"name": "west-floor", "vertices": [4, 2], "delta_z": -0.15}]}
        g0, g1 = tp20["groups"]
        c20 = parse_terrain_patch(tp20, "o")
        TP = {"type": "terrain", "patch": tp20}
        lpp = dict(lp, components=[F, TP])
        clp = parse_level_patch(lpp, "o")
        check("G6-P22: intro_20 start-floor-v1 patch parses (vertices 0 / 2 / 4); start-two-step-v1 as data -> the "
              "preset's exact collision_edit spec; an embedded terrain patch parses in either order, canonical "
              "{type, patch: canonical patch}, its own identity, the fairy part of the operation unchanged",
              terrain_spec(c20) == COLLISION_ALLOW["intro_20"]["presets"]["start-two-step-v1"]
              and clp["components"] == [{"type": "terrain", "patch": c20}, F]
              and parse_level_patch(dict(lp, components=[TP, F]), "o") == clp
              and level_patch_identity(clp) != level_patch_identity(cl)
              and level_patch_terrain(clp) == (terrain_spec(c20), "start-two-step-v1") and level_patch_terrain(cl) is None
              and level_patch_operation(clp) == {k: v for k, v in level_patch_operation(cl).items()
                                                 if k != "terrain_preset"})
        bad22 = {"UNSUPPORTED": [dict(tp20, groups=[g0, dict(g1, vertices=[9])]),
                                 dict(tp20, groups=[g0, dict(g1, vertices=[1])]),
                                 dict(tp20, groups=[dict(g0, delta_z=-0.31), g1]),
                                 dict(tp20, groups=[dict(g0, delta_z=0.1), g1]), dict(tp20, region="spawn-ground-v1")],
                 "BAD_MANIFEST": [dict(tp20, groups=[dict(g0, vertices=[0, 2, 4])]),
                                  dict(tp20, groups=[g0, dict(g1, vertices=[0, 2])]),
                                  dict(tp20, groups=[g0, dict(g1, delta_z="x")]), dict(tp20, offset=4)],
                 "TARGET_CHANGED": [dict(tp20, lvl_sha256="0" * 64)]}
        bad22l = {"BAD_MANIFEST": [dict(lp, components=[dict(TP, preset="start-two-step-v1"), F]),
                                   dict(lp, components=[dict(TP, patch=[1]), F]),
                                   dict(lp, components=[dict(TP, patch=dict(tp20, description="d")), F]),
                                   dict(lp, components=[TP, T, F])],
                  "UNSUPPORTED": [dict(lp, components=[dict(TP, patch=dict(tp20, level="intro_15")), F]),
                                  dict(lp, components=[dict(TP, patch=dict(tp20, groups=[g0, dict(g1, vertices=[9])])),
                                                       F])]}
        check("G6-P22: start-floor-v1 refuses vertices outside 0 / 2 / 4, raising or > 0.30 lowering, one group, "
              "duplicate vertices, non-numbers, unknown keys, another region / hash; a terrain component with both "
              "preset and patch, a non-object / described / other-level / invalid embedded patch, two terrains",
              all(refused(lambda p_=p_: parse_terrain_patch(p_, "o"), code) is True for code, ps in bad22.items()
                  for p_ in ps)
              and all(refused(lambda p_=p_: parse_level_patch(p_, "o"), code) is True for code, ps in bad22l.items()
                      for p_ in ps))
        check("G6-P22: a level-patch mod with an embedded terrain patch parses; refused with a terrain-patch "
              "override in the same mod",
              parse_manifest(man({"type": "level-patch", "patch": lpp}))["id"] == "t.mix"
              and refused(lambda: parse_manifest(man({"type": "level-patch", "patch": lpp},
                                                     {"type": "terrain-patch", "patch": tp20})), "BAD_MANIFEST") is True)

        # G6-P24 (D-280): author-facing diagnostics name the cause and the supported choices
        def detail(fn):
            try:
                fn()
            except Refusal as x:
                return x.detail
            return ""
        d_dup = detail(lambda: parse_terrain_patch(dict(tp20, groups=[g0, dict(g1, vertices=[0])]), "o"))
        d_up = detail(lambda: parse_terrain_patch(dict(tp20, groups=[dict(g0, delta_z=0.1), g1]), "o"))
        d_v = detail(lambda: parse_terrain_patch(dict(tp20, groups=[g0, dict(g1, vertices=[9])]), "o"))
        d_g = detail(lambda: parse_level_patch(dict(lp, components=[T, dict(F, follow_graph_of=2)]), "o"))
        d_h = detail(lambda: parse_level_patch(dict(lp, ptr_sha256="0" * 64), "o"))
        d_k = detail(lambda: parse_level_patch(dict(lp, description="d", colour=1), "o"))
        check("G6-P24: diagnostics name the duplicate vertex's first group, raising, the allowed vertices, graphs "
              "A / B, the affected source file (ASCII) and unknown vs missing keys",
              "already in group 'spawn-corner'" in d_dup and "raising is not supported" in d_up
              and "allowed: 0, 2, 4" in d_v and "0 = graph A, 1 = graph B" in d_g
              and "intro_20.ptr" in d_h and d_h.isascii() and "unknown: ['colour'], missing: []" in d_k, d_k)
        vs = [(0.0, 0.0, 1.0), (2.0, 0.0, 1.0), (0.0, 2.0, 2.0), (0.0, 0.0, 5.0), (0.0, 2.0, 5.0)]
        su = collision_surface(vs, {(0, 0): (0, 1, 2), (0, 1): (0, 3, 4)}, 0.5, 0.5)
        check("G6-P24: collision_surface returns the plane height of the upward triangle under (x, y) only",
              len(su) == 1 and su[0][0] == (0, 0) and abs(su[0][1] - 1.25) < 1e-9
              and collision_surface(vs, {(0, 0): (0, 1, 2)}, 5.0, 5.0) == [])
        # G6-P25 (D-281): region start-floor-v2 = start-floor-v1 + vertex 6 (twin 204, capped at -0.20)
        v2 = dict(tp20, region="start-floor-v2", groups=[{"name": "c", "vertices": [6], "delta_z": -0.2},
                                                         {"name": "f", "vertices": [2, 4], "delta_z": -0.15}])
        c2 = parse_terrain_patch(v2, "o")
        d6 = detail(lambda: parse_terrain_patch(dict(v2, groups=[dict(v2["groups"][0], delta_z=-0.25),
                                                                 v2["groups"][1]]), "o"))
        check("G6-P25: start-floor-v2 parses vertex 6 (visual twin 204 in its spec, 2-4 groups); vertex 6 below -0.20 "
              "refused naming its range; start-floor-v1 still refuses vertex 6 and keeps exactly 0 / 2 / 4",
              terrain_spec(c2)["visual"]["map"][204] == ("c299aad2c2749e29c1c9d4dc", 6)
              and "vertex 6's verified range -0.20..-0.05" in d6
              and refused(lambda: parse_terrain_patch(dict(v2, region="start-floor-v1"), "o"), "UNSUPPORTED") is True
              and list(terrain_region("intro_20", "start-floor-v1")["vertices"]) == [0, 2, 4]
              and terrain_spec(c20) == COLLISION_ALLOW["intro_20"]["presets"]["start-two-step-v1"]
              and parse_level_patch(dict(lp, components=[{"type": "terrain", "patch": v2}, F]), "o")["components"][0]
              == {"type": "terrain", "patch": c2})
        # G6-P28 (D-284): optional route component (graph C waypoint offsets); synthetic parse checks only
        R = {"type": "route", "waypoints": [{"node": 3, "offset": [0, -5, 3]}, {"node": 0, "offset": [-4.0, -3, -2]}]}
        lpr = dict(lp, components=[R, F, T])
        cr = parse_level_patch(lpr, "o")
        mv = lambda *ms: dict(R, waypoints=[{"node": n_, "offset": o_} for n_, o_ in ms])   # noqa: E731
        bad28 = {"BAD_MANIFEST": [dict(lp, components=[T, F, {"type": "route"}]),
                                  dict(lp, components=[T, F, dict(R, extra=1)]),
                                  dict(lp, components=[T, F, R, R]), dict(lp, components=[F, R]),
                                  dict(lp, components=[T, R]), dict(lp, components=[T, F, mv()]),
                                  dict(lp, components=[T, F, dict(R, waypoints={"node": 0})]),
                                  dict(lp, components=[T, F, mv(*[(i % 6, [1, 0, 0]) for i in range(7)])]),
                                  dict(lp, components=[T, F, mv((1, [1, 0, 0]), (1, [0, 1, 0]))]),
                                  dict(lp, components=[T, F, mv((1, [0, 0, 0]))]),
                                  dict(lp, components=[T, F, mv((1, [1, 0]))]),
                                  dict(lp, components=[T, F, mv((1, [True, 0, 0]))]),
                                  dict(lp, components=[T, F, mv((1, ["1", 0, 0]))]),
                                  dict(lp, components=[T, F, mv((1, [float("nan"), 0, 0]))]),
                                  dict(lp, components=[T, F, mv((1, [float("inf"), 0, 0]))]),
                                  dict(lp, components=[T, F, mv((True, [1, 0, 0]))]),
                                  dict(lp, components=[T, F, dict(R, waypoints=[{"node": 1, "offset": [1, 0, 0],
                                                                                 "position": [0, 0, 0]}])])],
                 "UNSUPPORTED": [dict(lp, components=[T, F, mv((6, [1, 0, 0]))]),
                                 dict(lp, components=[T, F, mv((-1, [1, 0, 0]))]),
                                 dict(lp, components=[T, F, mv((1, [6.0, 0.001, 0]))]),
                                 dict(lp, components=[T, F, mv((1, [5, 5, 0]))])]}
        check("G6-P28: level-patch-v1 accepts an optional route (canonical order terrain, fairylight, route; moves "
              "sorted by node, offsets as floats; a distinct identity; exactly 6.0 units allowed); a patch without "
              "one keeps its canonical form",
              cr["components"] == [T, F, {"type": "route", "waypoints": [{"node": 0, "offset": [-4.0, -3.0, -2.0]},
                                                                         {"node": 3, "offset": [0.0, -5.0, 3.0]}]}]
              and level_patch_identity(cr) != level_patch_identity(cl) and cl["components"] == [T, F]
              and parse_level_patch(dict(lp, components=[T, F, mv((5, [0, 6, 0]))]), "o")["components"][2]
              == {"type": "route", "waypoints": [{"node": 5, "offset": [0.0, 6.0, 0.0]}]}
              and level_patch_operation(cr) == level_patch_operation(cl))
        check("G6-P28: route refusals (missing / extra / duplicate component or keys, no / too many / repeated moves, "
              "zero, short, non-numeric or non-finite offsets, node outside 0-5, a move above 6 units)",
              all(refused(lambda p_=p_: parse_level_patch(p_, "o"), code) is True for code, ps in bad28.items()
                  for p_ in ps)
              and "at most 6 units" in detail(lambda: parse_level_patch(dict(lp, components=[T, F, mv((1, [5, 5, 0]))]),
                                                                       "o")))
        rt = level_patch_text({"result": "refused", "code": "UNSUPPORTED", "detail": "d", "advice": "a"}, "p.json")
        check("G6-P24: a refused level patch's text report says that nothing was written",
              rt.startswith("level-patch p.json: REFUSED (UNSUPPORTED)") and "Nothing was written." in rt)
        os.environ.pop(STRUCT_ENV, None)
        check("G6-P28: a level patch with a route is refused while the development gate is off (parse, manifest, "
              "compile)",
              refused(lambda: parse_level_patch(lpr, "o"), "UNSUPPORTED") is True
              and refused(lambda: parse_manifest(man({"type": "level-patch", "patch": lpr})), "UNSUPPORTED") is True
              and refused(lambda: compile_level_patch(lpr, {"game": Path(".")}), "UNSUPPORTED") is True)
        # G6-P30 (D-286): with the gate off only the production policy (start-floor terrain + graph A, no route)
        # parses / compiles; replaces the G6-P21 / G6-P22 "always refused" checks
        gb = dict(lp, components=[T, dict(F, follow_graph_of=1)])
        check("G6-P30: gate off: production-policy patches parse (preset and embedded start-floor terrain, graph A) "
              "with the same canonical form, scope closed afterwards; a mod carrying one parses; the compile reaches the "
              "game files (TARGET_MISSING), not the gate",
              parse_level_patch(lp, "o") == cl and parse_level_patch(lpp, "o") == clp and not _PROD_SCOPE
              and parse_manifest(man(lpo))["id"] == "t.mix" and not structural_enabled("intro_20")
              and refused(lambda: compile_level_patch(lp, {"game": Path(".")}), "TARGET_MISSING") is True
              and not _PROD_SCOPE)
        check("G6-P30: gate off: graph B, a route, a non-start-floor component set and other levels stay refused "
              "(UNSUPPORTED, development-only) in parse, manifest and compile",
              all(refused(lambda q=q: parse_level_patch(q, "o"), "UNSUPPORTED") is True
                  and refused(lambda q=q: parse_manifest(man({"type": "level-patch", "patch": q})), "UNSUPPORTED")
                  is True and refused(lambda q=q: compile_level_patch(q, {"game": Path(".")}), "UNSUPPORTED") is True
                  for q in (gb, lpr, dict(lp, components=[T]), dict(lp, level="intro_10")))
              and "development-only" in detail(lambda: parse_level_patch(gb, "o")) and not _PROD_SCOPE)
        check("G6-P20: insert-fairy-with-terrain refused while the development gate is off (parse and compile)",
              refused(lambda: parse_insert_fairy_with_terrain(dict(fx), "o"), "UNSUPPORTED") is True
              and refused(lambda: compile_insert_fairy_with_terrain(dict(fx), {"game": Path(".")}), "UNSUPPORTED") is True)
        os.environ[STRUCT_ENV] = "intro_15"
        with tempfile.TemporaryDirectory() as td:
            check("G6-P17: missing level files refused",
                  refused(lambda: compile_terrain_patch(good, {"game": Path(td)}), "TARGET_MISSING") is True)
    finally:
        os.environ.pop(STRUCT_ENV, None)
        if old is not None:
            os.environ[STRUCT_ENV] = old


def selftest_collision(check, refused):
    """G6-P13 (D-266): collision-vertex-offset refusals that need no game data (the geometry itself is checked against
    the person's exact file by tools/experiments/modding_feasibility/g6p13_collision.py check)."""
    old = os.environ.pop(STRUCT_ENV, None)
    try:
        good = {"type": "collision-vertex-offset", "level": "intro_15", "preset": "spawn-drop-1.50",
                "lvl_sha256": "0" * 64}
        check("G6-P13: collision-vertex-offset is refused while the development gate is off",
              refused(lambda: parse_collision_vertex_offset(dict(good), "o"), "UNSUPPORTED") is True)
        check("G6-P13: compile refused while the gate is off",
              refused(lambda: compile_collision_vertex_offset(dict(good), {"game": Path(".")}), "UNSUPPORTED") is True)
        os.environ[STRUCT_ENV] = "intro_10"
        check("G6-P13: a gate naming another level does not enable the intro_15 compile",
              refused(lambda: compile_collision_vertex_offset(dict(good), {"game": Path(".")}), "UNSUPPORTED") is True)
        os.environ[STRUCT_ENV] = "intro_15"
        for name, o, code in (("unknown preset", {**good, "preset": "spawn-drop-3.00"}, "UNSUPPORTED"),
                              ("other level", {**good, "level": "intro_10"}, "UNSUPPORTED"),
                              ("an offset key", {**good, "offset": 4}, "BAD_MANIFEST"),
                              ("a displacement key", {**good, "dz": -1.5}, "BAD_MANIFEST"),
                              ("a vertex key", {**good, "vertices": [1]}, "BAD_MANIFEST"),
                              ("missing hash", {k: v for k, v in good.items() if k != "lvl_sha256"}, "BAD_MANIFEST"),
                              ("bad hash", {**good, "lvl_sha256": "AB"}, "BAD_MANIFEST")):
            check(f"G6-P13: refused: {name}", refused(lambda o=o: parse_collision_vertex_offset(o, "o"), code) is True)
        check("G6-P13: gameplay-affecting", changes_game_logic({"overrides": [good]}) is True)
        ms = COLLISION_ALLOW["intro_15"]["presets"]["spawn-multi-surface-v1"]
        vk = [k for g_ in ms["groups"] for k in g_["vertices"]]
        check("G6-P16: spawn-multi-surface-v1 is fixed: two disjoint groups inside the group guard, one visual twin each",
              len(ms["groups"]) == 2 and len(vk) == len(set(vk)) == 7
              and all(-0.30 <= g_["dz"] <= -0.05 for g_ in ms["groups"]) and ms["bounds"] == "keep"
              and sorted(c for _, c in ms["visual"]["map"].values()) == sorted(vk) and ms["visual"]["complete"])
        check("G6-P16: refused: a groups key in the manifest",
              refused(lambda: parse_collision_vertex_offset({**good, "preset": "spawn-multi-surface-v1", "groups": []},
                                                            "o"), "BAD_MANIFEST") is True)
        with tempfile.TemporaryDirectory() as td:
            g = Path(td) / "GAMEDATAbin" / "intro_15"
            check("G6-P13: missing level files refused",
                  refused(lambda: compile_collision_vertex_offset(dict(good), {"game": Path(td)}), "TARGET_MISSING")
                  is True)
            g.mkdir(parents=True)
            (g / "intro_15.lvl").write_bytes(b"\0" * 64)
            (g / "intro_15.ptr").write_bytes(b"\0" * 4)
            check("G6-P13: a manifest hash that differs from the level file is refused",
                  refused(lambda: compile_collision_vertex_offset(dict(good), {"game": Path(td)}), "TARGET_CHANGED")
                  is True)
            check("G6-P13: a level file that is not the allow-listed one is refused before any edit",
                  refused(lambda: compile_collision_vertex_offset({**good, "lvl_sha256": sha256_bytes(b"\0" * 64)},
                                                                  {"game": Path(td)}), "TARGET_CHANGED") is True)
        box = ([0.0, 0.0, 0.0], [1.0, 1.0, 1.0])
        check("G6-P13: triangle/box test (inside, crossing, outside, beside a corner)",
              _tri_box([[0.2, 0.2, 0.5], [0.8, 0.2, 0.5], [0.2, 0.8, 0.5]], *box)
              and _tri_box([[-5, -5, 0.5], [5, -5, 0.5], [0, 5, 0.5]], *box)
              and not _tri_box([[0, 0, 2], [1, 0, 2], [0, 1, 2]], *box)
              and not _tri_box([[1.5, 0.6, 0.5], [0.6, 1.5, 0.5], [1.5, 1.5, 0.5]], *box))
    finally:
        os.environ.pop(STRUCT_ENV, None)
        if old is not None:
            os.environ[STRUCT_ENV] = old


def selftest_waypoint(check, refused):
    """D-231: waypoint-position overrides on synthetic levels: one AI model whose instance owns a 3-node graph in
    designer variable 0 (variable 1 is an int); variants: the graph also named by another word, two nodes sharing a
    waypoint, a pointer into a waypoint, a transit-file reference."""
    bA = "Gen\\W_A\\W_A.rul^CreateIntelligence^CreateComport:W_Init"

    def level(variant=""):
        lvl, slots = bytearray(0x2000), []

        def ptr(at, to):
            struct.pack_into(">I", lvl, at, to - 4)
            slots.append((1, at - 4))
        ptr(0x100, 0x200)
        struct.pack_into(">I", lvl, 0x104, 1)
        lvl[0x200:0x200 + len(bA)] = bA.encode()
        ptr(0x1A00, 0x100)                        # AI model; +8 -> DsgVar {buffer, info, length 8, 2 variables}
        ptr(0x1A08, 0x1C00)
        ptr(0x1C00, 0x1C40)
        ptr(0x1C04, 0x1C80)
        struct.pack_into(">II", lvl, 0x1C08, 8, 2 << 24)
        struct.pack_into(">IIII", lvl, 0x1C80, 0, GRAPH_TYPE, 0, 4)
        struct.pack_into(">IIII", lvl, 0x1C90, 4, 5, 0, 4)
        ptr(0x300, 0x1A08)                        # DsgMem: initial 0x30C, current 0x400; both name the graph
        ptr(0x304, 0x30C)
        ptr(0x308, 0x400)
        ptr(0x30C, 0x800)
        ptr(0x400, 0x800)
        ptr(0x800, 0x900)                         # graph: first, last, 3 nodes
        ptr(0x804, 0x940)
        struct.pack_into(">I", lvl, 0x808, 3)
        for i in range(3):
            nd, w = 0x900 + 0x20 * i, 0xA00 + 0x20 * i
            if i < 2:
                ptr(nd, nd + 0x20)
            if i:
                ptr(nd + 4, nd - 0x20)
            ptr(nd + 8, 0x800)
            ptr(nd + 0xC, 0xA20 if variant == "sharedwp" and i == 2 else w)
            struct.pack_into(">5f", lvl, w, float(i), 2.0 * i, 3.0 * i, 1.0, 0.0)
        if variant == "sharedgraph":
            ptr(0xE00, 0x800)
        if variant == "into":
            ptr(0xE00, 0xA24)
        return bytes(lvl), struct.pack(">I", len(slots)) + b"".join(struct.pack(">iI", f, loc) for f, loc in slots)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        game = td / "game"
        for name, variant in (("wv", ""), ("wsg", "sharedgraph"), ("wsw", "sharedwp"), ("win", "into"),
                              ("wtr", "")):
            (game / "GAMEDATAbin" / name).mkdir(parents=True)
            lvl, ptr = level(variant)
            (game / "GAMEDATAbin" / name / f"{name}.lvl").write_bytes(lvl)
            (game / "GAMEDATAbin" / name / f"{name}.ptr").write_bytes(ptr)
        tl = bytearray(16)
        struct.pack_into(">I", tl, 8, 0xA20 - 4)
        (game / "GAMEDATAbin" / "wtr" / "transit.lvl").write_bytes(bytes(tl))
        (game / "GAMEDATAbin" / "wtr" / "transit.ptr").write_bytes(struct.pack(">IiI", 1, 1, 4))
        lvl, _ = level()
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(lvl)
        (game / "GAMEDATAbin" / "fix.ptr").write_bytes(struct.pack(">I", 0))
        before = {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}
        paths = {"home": None, "mods": td / "mods", "cache": td / "cache", "game": game}
        ix = read_script_index(game, "wv")
        e = ix["graphs"].get((bA, 0, 0))
        check("waypoint: the instance's graph variable leads to 3 nodes and their waypoints; the int variable is no graph",
              e is not None and not e["safe"] and not e["wsafe"] and [w for _, w in e["nodes"]] == [0xA00, 0xA20, 0xA40]
              and (bA, 0, 1) not in ix["graphs"], e)
        rows = waypoint_rows(ix, bA)
        check("waypoint info: per node its hash, position and radius",
              [(n["position"], n["radius"]) for n in rows[0]["nodes"]] ==
              [([0.0, 0.0, 0.0], 1.0), ([1.0, 2.0, 3.0], 1.0), ([2.0, 4.0, 6.0], 1.0)], rows)
        hs = [n["waypoint_sha256"] for n in rows[0]["nodes"]]

        def ov(**kw):
            o = {"type": "waypoint-position", "level": "wv", "model": bA, "instance": 0, "variable": 0, "node": 1,
                 "waypoint_sha256": hs[1], "position": [7.5, -2.25, 3.0]}
            o.update(kw)
            return o
        rs = compile_waypoint_positions([ov()], paths)
        check("waypoint: x, y, z only (12 bytes at the waypoint; radius and flags not written)",
              [(p.name, off, data) for p, off, data, _ in rs] == [("wv.lvl", 0xA20, struct.pack(">3f", 7.5, -2.25, 3.0))],
              rs)
        same = []
        for i in range(3):
            same += compile_waypoint_positions([ov(node=i, waypoint_sha256=hs[i],
                                                   position=[float(i), 2.0 * i, 3.0 * i])], paths)
        check("waypoint: every waypoint compiled with its own position equals the file's bytes",
              len(same) == 3 and all(ix["data"][off:off + len(d)] == d for _, off, d, _ in same))
        for label, o, code in (("a graph another word also names", ov(level="wsg"), "UNSUPPORTED"),
                               ("a waypoint two nodes share", ov(level="wsw"), "UNSUPPORTED"),
                               ("a waypoint another word points into", ov(level="win"), "UNSUPPORTED"),
                               ("a waypoint the transit file points at", ov(level="wtr"), "UNSUPPORTED"),
                               ("a changed waypoint (other hash)", ov(waypoint_sha256="0" * 64), "TARGET_CHANGED"),
                               ("another node's hash", ov(waypoint_sha256=hs[2]), "TARGET_CHANGED"),
                               ("a node index past the graph's", ov(node=3), "TARGET_MISSING"),
                               ("a variable that is not a graph", ov(variable=1), "TARGET_MISSING"),
                               ("an instance the model does not have", ov(instance=1), "TARGET_MISSING"),
                               ("an unknown model", ov(model=bA.replace("W_Init", "W_Idle")), "TARGET_MISSING"),
                               ("fix.lvl", ov(level="fix"), "UNSUPPORTED")):
            got = refused(lambda o=o: compile_waypoint_positions([o], paths), code)
            check(f"waypoint compile: refused: {label}", got is True, got)
        for label, o, code in (("an unknown key", ov(extra=1), "BAD_MANIFEST"),
                               ("a missing key", {k: v for k, v in ov().items() if k != "node"}, "BAD_MANIFEST"),
                               ("fix.lvl", ov(level="fix"), "UNSUPPORTED"),
                               ("a NaN coordinate", ov(position=[float("nan"), 0.0, 0.0]), "BAD_MANIFEST"),
                               ("an infinite coordinate", ov(position=[0.0, float("-inf"), 0.0]), "BAD_MANIFEST"),
                               ("two coordinates", ov(position=[0.0, 0.0]), "BAD_MANIFEST"),
                               ("a boolean node index", ov(node=True), "BAD_MANIFEST")):
            got = refused(lambda o=o: parse_waypoint_position(o, "o"), code)
            check(f"waypoint manifest: refused: {label}", got is True, got)

        def mod(mid, overrides):
            d = td / "src" / mid
            d.mkdir(parents=True)
            (d / "mod.json").write_text(json.dumps(
                {"format": 1, "id": mid, "name": mid, "version": "1.0.0", "overrides": overrides,
                 "target": {"title_id": TITLE_ID, "releases": release_ids(paths), "min_port_version": "0.0.1"}}),
                encoding="utf-8")
            return d
        check("waypoint manifest: the same waypoint twice is refused",
              refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.twice", "name": "x", "version": "1.0.0",
                   "overrides": [ov(), ov(position=[0.0, 0.0, 0.0])],
                   "target": {"title_id": TITLE_ID, "releases": ["r"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True)
        cmd_import(paths, mod("w.ok", [ov(), ov(node=2, waypoint_sha256=hs[2], position=[9.0, 9.0, 9.0])]),
                   enable=True)
        check("waypoint import: a mod with one valid and one unsafe move is refused whole; nothing is installed",
              refused(lambda: cmd_import(paths, mod("w.half", [ov(), ov(level="wsg")]), enable=True),
                      "UNSUPPORTED") is True and not installed_dir(paths, "w.half").exists())
        res = resolve_all(paths, write_plan=paths["cache"])
        plan = Path(res["plan"]).read_text(encoding="utf-8")
        check("waypoint plan: the valid mod applies (2 ranges) and is named as changing game logic",
              res["active"] == ["w.ok"] and res["ranges"] == 2 and res["gameplay_active"] == ["w.ok"]
              and "\ngameplay w.ok\n" in plan and res["mods"][0]["gameplay"] is True, res)
        cmd_import(paths, mod("w.top", [ov(position=[0.0, 1.0, 0.0])]), enable=True)
        cmd_move(paths, "w.top", "top")
        res = resolve_all(paths)
        low = next(x for x in res["mods"] if x["id"] == "w.ok")
        check("waypoint priority: a higher mod moving the same waypoint refuses the whole lower mod",
              res["active"] == ["w.top"] and low["code"] == "CONFLICT", res["mods"])
        for mid in ("w.ok", "w.top"):
            cmd_set(paths, mid, False)
        res = resolve_all(paths, write_plan=paths["cache"])
        check("waypoint disabled: no plan, nothing gameplay-active, the mods stay marked",
              res["ranges"] == 0 and res["gameplay_active"] == [] and all(x["gameplay"] for x in res["mods"])
              and not (paths["cache"] / PLAN_NAME).exists(), res)
        check("waypoint: game files are never written",
              before == {p: p.read_bytes() for p in game.rglob("*") if p.is_file()})


def selftest_placement(check, refused):
    """D-228: actor-position overrides on synthetic levels: one AI model with two actors (type-2 matrix with its
    word-swapped snapshot; type-5 matrix) and variants: an identity matrix, no snapshot, a snapshot that differs, a
    stray pointer into a matrix, two actors sharing one matrix and a transit-file reference."""
    bA = "Gen\\P_A\\P_A.rul^CreateIntelligence^CreateComport:P_Init"

    def level(variant=""):
        lvl, slots = bytearray(0x2000), []

        def ptr(at, to):
            struct.pack_into(">I", lvl, at, to - 4)
            slots.append((1, at - 4))
        ptr(0x100, 0x200)
        struct.pack_into(">I", lvl, 0x104, 1)
        lvl[0x200:0x200 + len(bA)] = bA.encode()
        ptr(0x1A00, 0x100)                        # AI model record (its normal list)
        ptr(0x1A40, 0x1A50)                       # Brain -> Mind; Mind -> model
        ptr(0x1A50, 0x1A00)

        def actor(so, mat, snap, typ, xyz):
            struct.pack_into(">I", lvl, so, 2)
            ptr(so + 4, so + 0x100)               # Perso
            ptr(so + 0x100 + 4, so + 0x140)       # Perso +4 StdGame; StdGame +0xC -> SuperObject
            ptr(so + 0x140 + 0xC, so)
            ptr(so + 0x100 + 0xC, 0x1A40)         # Perso +0xC Brain
            ptr(so + 0x20, mat)
            if variant == "shared" and so != 0x400:
                return
            words = [typ, *(struct.unpack(">I", struct.pack(">f", v))[0] for v in
                            (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, *xyz, 1, 1, 1, 1, 1))]
            for k, w in enumerate(words):
                struct.pack_into(">I", lvl, mat + 4 * k, w)
                if snap is not None:
                    struct.pack_into("<I", lvl, snap + 4 * k, w ^ (1 if variant == "differ" and k == 14 else 0))
            if snap is not None:
                rec = mat + 0x100
                ptr(rec, mat)
                ptr(rec + 4, snap)
                struct.pack_into(">II", lvl, rec + 8, PLACEMENT_SIZE, 0x50320200)
        actor(0x400, 0x900, 0x1400, 1 if variant == "identity" else 2, (22.5, -12.0, -34.25))
        actor(0x600, 0x400 + 0x500 if variant == "shared" else 0xB00, None if variant == "nosnap" else 0x1600, 5,
              (1.0, 2.0, 3.0))
        if variant == "data":
            ptr(0x1800, 0x910)                    # a word that is no matrix reference points into actor 0's matrix
        if variant == "setter":                   # D-229: P_Init's script calls procedure DB (sets the position)
            lvl[0x200 + 0x108] = 1
            ptr(0x200 + 0x100, 0x1B00)
            ptr(0x1B00, 0x1B40)
            for k, (p_, ind, kind) in enumerate([(0xDB, 1, 0x04), (0x13, 2, 0x00), (0, 0, 0)]):
                struct.pack_into(">IHBB", lvl, 0x1B40 + 8 * k, p_, 0, ind, kind)
        return bytes(lvl), struct.pack(">I", len(slots)) + b"".join(struct.pack(">iI", f, loc) for f, loc in slots)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        game = td / "game"
        for name, variant in (("pv", ""), ("pid", "identity"), ("pns", "nosnap"), ("pdf", "differ"),
                              ("pdt", "data"), ("psh", "shared"), ("ptr", ""),
                              ("pset", "setter")):
            (game / "GAMEDATAbin" / name).mkdir(parents=True)
            lvl, ptr = level(variant)
            (game / "GAMEDATAbin" / name / f"{name}.lvl").write_bytes(lvl)
            (game / "GAMEDATAbin" / name / f"{name}.ptr").write_bytes(ptr)
        tl = bytearray(16)
        struct.pack_into(">I", tl, 8, 0x934 - 4)
        (game / "GAMEDATAbin" / "ptr" / "transit.lvl").write_bytes(bytes(tl))
        (game / "GAMEDATAbin" / "ptr" / "transit.ptr").write_bytes(struct.pack(">IiI", 1, 1, 4))
        lvl, _ = level()
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(lvl)
        (game / "GAMEDATAbin" / "fix.ptr").write_bytes(struct.pack(">I", 0))
        before = {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}
        paths = {"home": None, "mods": td / "mods", "cache": td / "cache", "game": game}
        ix = read_script_index(game, "pv")
        insts = ix["placements"].get(bA)
        check("placement: two actors of the model in file order, both movable, each with its snapshot",
              insts is not None and [i["so"] for i in insts] == [0x400, 0x600] and not any(i["safe"] for i in insts)
              and [i["snapshot"] for i in insts] == [0x1400, 0x1600], insts)
        rows = placement_rows(ix, insts, bA)
        set_rows = placement_rows(read_script_index(game, "pset"), read_script_index(game, "pset")["placements"][bA],
                                  bA)
        check("placement info (D-229): a model whose script sets the position lists every actor as not movable",
              all("procedures DB / 219" in r.get("cannot_change", "") for r in set_rows) and len(set_rows) == 2,
              set_rows)
        check("placement info: matrix hash, type and position per actor",
              [(r["matrix_type"], r["position"]) for r in rows] == [(2, [22.5, -12.0, -34.25]), (5, [1.0, 2.0, 3.0])],
              rows)
        h0, h1 = rows[0]["matrix_sha256"], rows[1]["matrix_sha256"]

        def ov(**kw):
            o = {"type": "actor-position", "level": "pv", "model": bA, "instance": 0, "matrix_sha256": h0,
                 "position": [19.1, -13.5, -34.5]}
            o.update(kw)
            return o
        rs = compile_actor_positions([ov()], paths)
        be = struct.pack(">3f", 19.1, -13.5, -34.5)
        check("placement: the translation in the matrix (big-endian) and its snapshot (word-swapped), 12 bytes each",
              [(p.name, off, data) for p, off, data, _ in rs] ==
              [("pv.lvl", 0x934, be), ("pv.lvl", 0x1434, b"".join(be[k:k + 4][::-1] for k in (0, 4, 8)))], rs)
        same = compile_actor_positions([ov(position=[22.5, -12.0, -34.25]),
                                        ov(instance=1, matrix_sha256=h1, position=[1.0, 2.0, 3.0])], paths)
        check("placement: every actor compiled with its own position equals the file's bytes (matrix and snapshot)",
              len(same) == 4 and all(ix["data"][off:off + len(d)] == d for _, off, d, _ in same))
        check("placement: rotation, scale and the other matrix words are not written",
              all(len(d) == 12 and (off - 0x34) in (0x900, 0x1400, 0xB00, 0x1600) for _, off, d, _ in rs + same))
        for label, o, code in (("an identity matrix (type 1)", ov(level="pid"), "UNSUPPORTED"),
                               ("a matrix without a snapshot", ov(level="pns", instance=1, matrix_sha256=h1),
                                "UNSUPPORTED"),
                               ("a snapshot that holds another matrix", ov(level="pdf"), "UNSUPPORTED"),
                               ("a matrix another word points into", ov(level="pdt"), "UNSUPPORTED"),
                               ("two actors sharing one matrix", ov(level="psh"), "UNSUPPORTED"),
                               ("a matrix the transit file points into", ov(level="ptr"), "UNSUPPORTED"),
                               ("a model whose script sets the position (procedure DB)", ov(level="pset"),
                                "UNSUPPORTED"),
                               ("a changed matrix (other hash)", ov(matrix_sha256="0" * 64), "TARGET_CHANGED"),
                               ("the other actor's hash", ov(matrix_sha256=h1), "TARGET_CHANGED"),
                               ("an actor index past the model's", ov(instance=2), "TARGET_MISSING"),
                               ("an unknown model", ov(model=bA.replace("P_Init", "P_Idle")), "TARGET_MISSING"),
                               ("fix.lvl", ov(level="fix"), "UNSUPPORTED")):
            got = refused(lambda o=o: compile_actor_positions([o], paths), code)
            check(f"placement compile: refused: {label}", got is True, got)
        for label, o, code in (("an unknown key", ov(extra=1), "BAD_MANIFEST"),
                               ("a missing key", {k: v for k, v in ov().items() if k != "instance"}, "BAD_MANIFEST"),
                               ("fix.lvl", ov(level="fix"), "UNSUPPORTED"),
                               ("two coordinates", ov(position=[1.0, 2.0]), "BAD_MANIFEST"),
                               ("a NaN coordinate", ov(position=[1.0, float("nan"), 2.0]), "BAD_MANIFEST"),
                               ("an infinite coordinate", ov(position=[float("inf"), 0.0, 0.0]), "BAD_MANIFEST"),
                               ("a coordinate beyond float32", ov(position=[1e39, 0.0, 0.0]), "BAD_MANIFEST"),
                               ("a text coordinate", ov(position=["1", 0.0, 0.0]), "BAD_MANIFEST")):
            got = refused(lambda o=o: parse_actor_position(o, "o"), code)
            check(f"placement manifest: refused: {label}", got is True, got)

        def mod(mid, overrides):
            d = td / "src" / mid
            d.mkdir(parents=True)
            (d / "mod.json").write_text(json.dumps(
                {"format": 1, "id": mid, "name": mid, "version": "1.0.0", "overrides": overrides,
                 "target": {"title_id": TITLE_ID, "releases": release_ids(paths), "min_port_version": "0.0.1"}}),
                encoding="utf-8")
            return d
        check("placement manifest: the same actor twice is refused",
              refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.twice", "name": "x", "version": "1.0.0",
                   "overrides": [ov(), ov(position=[0.0, 0.0, 0.0])],
                   "target": {"title_id": TITLE_ID, "releases": ["r"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True)
        cmd_import(paths, mod("p.ok", [ov(), ov(instance=1, matrix_sha256=h1, position=[4.0, 5.0, 6.0])]),
                   enable=True)
        check("placement import: a mod with one valid and one unsafe move is refused whole; nothing is installed",
              refused(lambda: cmd_import(paths, mod("p.half", [ov(), ov(level="pid")]), enable=True),
                      "UNSUPPORTED") is True and not installed_dir(paths, "p.half").exists())
        res = resolve_all(paths, write_plan=paths["cache"])
        plan = Path(res["plan"]).read_text(encoding="utf-8")
        check("placement plan: the valid mod applies (4 ranges) and is named as changing game logic",
              res["active"] == ["p.ok"] and res["ranges"] == 4 and res["gameplay_active"] == ["p.ok"]
              and "\ngameplay p.ok\n" in plan and res["mods"][0]["gameplay"] is True, res)
        cmd_import(paths, mod("p.top", [ov(position=[0.0, 0.0, 0.0])]), enable=True)
        cmd_move(paths, "p.top", "top")
        res = resolve_all(paths)
        low = next(x for x in res["mods"] if x["id"] == "p.ok")
        check("placement priority: a higher mod moving the same actor refuses the whole lower mod",
              res["active"] == ["p.top"] and low["code"] == "CONFLICT", res["mods"])
        for mid in ("p.ok", "p.top"):
            cmd_set(paths, mid, False)
        res = resolve_all(paths, write_plan=paths["cache"])
        check("placement disabled: no plan, nothing gameplay-active, the mods stay marked",
              res["ranges"] == 0 and res["gameplay_active"] == [] and all(x["gameplay"] for x in res["mods"])
              and not (paths["cache"] / PLAN_NAME).exists(), res)
        check("placement: game files are never written",
              before == {p: p.read_bytes() for p in game.rglob("*") if p.is_file()})


def selftest_designer(check, refused):
    """D-227: designer-default overrides on synthetic levels: one AI model (DsgVar of 6 variables: int, real, a
    pointer, byte, bool, a byte whose initial and current values differ) with two instances; variants with a stray
    pointer into a buffer, a buffer outside the file, overlapping buffers and a transit-file reference."""
    bA = "Gen\\D_A\\D_A.rul^CreateIntelligence^CreateComport:D_Init"
    bB = "Gen\\D_A\\D_A.rul^CreateIntelligence^CreateComport:D_Idle"
    real = struct.unpack(">I", struct.pack(">f", 2.5))[0]

    def level(variant=""):
        lvl, slots = bytearray(0x1000), []

        def ptr(at, to):
            struct.pack_into(">I", lvl, at, to - 4)
            slots.append((1, at - 4))
        ptr(0x100, 0x200)
        struct.pack_into(">I", lvl, 0x104, 1)
        lvl[0x200:0x200 + len(bA)] = bA.encode()
        ptr(0xC00, 0x100)                         # model: normal list; +8 -> DsgVar
        ptr(0xC08, 0xE00)
        ptr(0xE00, 0xE40)                         # DsgVar: default buffer, info, length 16, 6 variables
        ptr(0xE04, 0xE80)
        struct.pack_into(">II", lvl, 0xE08, 16, 6 << 24)
        for i, (off, t) in enumerate(((0, 5), (4, 7), (8, 18), (12, 2), (13, 0), (14, 2))):
            struct.pack_into(">IIII", lvl, 0xE80 + 16 * i, off, t, 0, 4)

        def instance(mem, ini, cur, fill=True):
            ptr(mem, 0xC08)
            ptr(mem + 4, ini)
            if cur is not None:
                ptr(mem + 8, cur)
            for b in (ini, cur) if fill else ():
                if b is None:
                    continue
                struct.pack_into(">iI", lvl, b, 7 if mem == 0x300 else 8, real)
                ptr(b + 8, 0x200)                   # variable 2: a pointer (relocated)
                lvl[b + 12:b + 15] = bytes([3, 1, 9 if b == ini else 10])
        instance(0x300, 0x30C, None if variant == "missing" else 0x400)
        instance(0x500, 0x50C, 0x404 if variant == "overlap" else 0x600, fill=variant != "overlap")
        if variant == "data":
            ptr(0x700, 0x310)                       # a word that is no DsgMem points into instance 0's buffer
        return bytes(lvl), struct.pack(">I", len(slots)) + b"".join(struct.pack(">iI", f, loc) for f, loc in slots)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        game = td / "game"
        for name, variant in (("dv", ""), ("ddata", "data"), ("dmiss", "missing"), ("dover", "overlap"),
                              ("dtr", "")):
            (game / "GAMEDATAbin" / name).mkdir(parents=True)
            lvl, ptr = level(variant)
            (game / "GAMEDATAbin" / name / f"{name}.lvl").write_bytes(lvl)
            (game / "GAMEDATAbin" / name / f"{name}.ptr").write_bytes(ptr)
        tl = bytearray(16)
        struct.pack_into(">I", tl, 8, 0x310 - 4)
        (game / "GAMEDATAbin" / "dtr" / "transit.lvl").write_bytes(bytes(tl))
        (game / "GAMEDATAbin" / "dtr" / "transit.ptr").write_bytes(struct.pack(">IiI", 1, 1, 4))
        lvl, _ = level()
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(lvl)
        (game / "GAMEDATAbin" / "fix.ptr").write_bytes(struct.pack(">I", 0))
        before = {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}
        paths = {"home": None, "mods": td / "mods", "cache": td / "cache", "game": game}
        ix = read_script_index(game, "dv")
        e = ix["defaults"].get(bA)
        check("designer: the model is keyed by its first behaviour; 6 variables, 2 editable instances in file order",
              e is not None and len(e["vars"]) == 6 and e["length"] == 16 and len(e["instances"]) == 2
              and [i["initial"] for i in e["instances"]] == [0x30C, 0x50C]
              and not any(i["safe"] for i in e["instances"]), e)
        h0 = designer_hash(ix, e["instances"][0], 16)
        h1 = designer_hash(ix, e["instances"][1], 16)

        def ov(**kw):
            o = {"type": "designer-default", "level": "dv", "model": bA, "instance": 0, "variable": 0,
                 "initial_sha256": h0, "kind": "int", "value": 60}
            o.update(kw)
            return o
        rs = compile_designer_defaults([ov()], paths)
        check("designer: an int is written in place in the initial and the current buffer",
              [(p.name, off, data) for p, off, data, _ in rs] == [("dv.lvl", 0x30C, struct.pack(">i", 60)),
                                                                  ("dv.lvl", 0x400, struct.pack(">i", 60))], rs)
        rs = compile_designer_defaults([ov(instance=1, initial_sha256=h1, variable=1, kind="real", value=0.5)], paths)
        check("designer: a real of instance 1 is a big-endian float32 in its own buffers",
              [(off, data) for _, off, data, _ in rs] == [(0x510, struct.pack(">f", 0.5)),
                                                         (0x604, struct.pack(">f", 0.5))], rs)
        rs = compile_designer_defaults([ov(variable=3, kind="byte", value=100), ov(variable=4, kind="bool", value=0)],
                                       paths)
        check("designer: a byte and a bool are one byte each", [(off, data) for _, off, data, _ in rs] ==
              [(0x318, b"\x64"), (0x40C, b"\x64"), (0x319, b"\x00"), (0x40D, b"\x00")], rs)
        same = []
        for var, kind, value in ((0, "int", 7), (1, "real", 2.5), (3, "byte", 3), (4, "bool", 1)):
            same += compile_designer_defaults([ov(variable=var, kind=kind, value=value)], paths)
        check("designer: every editable variable compiled with its own value equals the file's bytes",
              len(same) == 8 and all(ix["data"][off:off + len(d)] == d for _, off, d, _ in same))
        info = cmd_macro_info(paths, "dv", "d_init")["models"][0]["instances"]
        check("designer info: per instance its hash and the editable variables (no pointer, no differing value)",
              info[0]["initial_sha256"] == h0 and info[1]["initial_sha256"] == h1 and info[0]["variables"] == [
                  {"variable": 0, "kind": "int", "value": 7}, {"variable": 1, "kind": "real", "value": 2.5},
                  {"variable": 3, "kind": "byte", "value": 3}, {"variable": 4, "kind": "bool", "value": 1}], info)
        for label, o, code in (("a pointer variable", ov(variable=2), "UNSUPPORTED"),
                               ("a variable whose initial and current values differ", ov(variable=5, kind="byte",
                                                                                         value=1), "UNSUPPORTED"),
                               ("a kind other than the variable's", ov(kind="real", value=1.0), "TARGET_CHANGED"),
                               ("a changed instance (other hash)", ov(initial_sha256="0" * 64), "TARGET_CHANGED"),
                               ("the other instance's hash", ov(initial_sha256=h1), "TARGET_CHANGED"),
                               ("an instance index past the model's", ov(instance=2), "TARGET_MISSING"),
                               ("a variable index past the model's", ov(variable=6), "TARGET_MISSING"),
                               ("an unknown model", ov(model=bB), "TARGET_MISSING"),
                               ("a buffer another word points into", ov(level="ddata"), "UNSUPPORTED"),
                               ("a buffer outside the file", ov(level="dmiss"), "UNSUPPORTED"),
                               ("overlapping buffers", ov(level="dover", instance=1, initial_sha256=h1),
                                "UNSUPPORTED"),
                               ("a buffer the transit file points into", ov(level="dtr"), "UNSUPPORTED"),
                               ("fix.lvl", ov(level="fix"), "UNSUPPORTED")):
            got = refused(lambda o=o: compile_designer_defaults([o], paths), code)
            check(f"designer compile: refused: {label}", got is True, got)
        for label, o, code in (("an unknown key", ov(extra=1), "BAD_MANIFEST"),
                               ("a missing key", {k: v for k, v in ov().items() if k != "instance"}, "BAD_MANIFEST"),
                               ("fix.lvl", ov(level="fix"), "UNSUPPORTED"),
                               ("a kind other than bool / byte / int / real", ov(kind="vector"), "UNSUPPORTED"),
                               ("a byte above 127", ov(kind="byte", value=128), "BAD_MANIFEST"),
                               ("a bool other than 0 / 1", ov(kind="bool", value=2), "BAD_MANIFEST"),
                               ("a fractional byte", ov(kind="byte", value=1.5), "BAD_MANIFEST"),
                               ("an int beyond int32", ov(value=1 << 31), "BAD_MANIFEST"),
                               ("a NaN real", ov(kind="real", value=float("nan")), "BAD_MANIFEST")):
            got = refused(lambda o=o: parse_designer_default(o, "o"), code)
            check(f"designer manifest: refused: {label}", got is True, got)

        def mod(mid, overrides):
            d = td / "src" / mid
            d.mkdir(parents=True)
            (d / "mod.json").write_text(json.dumps(
                {"format": 1, "id": mid, "name": mid, "version": "1.0.0", "overrides": overrides,
                 "target": {"title_id": TITLE_ID, "releases": release_ids(paths), "min_port_version": "0.0.1"}}),
                encoding="utf-8")
            return d
        check("designer manifest: the same variable twice is refused",
              refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.twice", "name": "x", "version": "1.0.0", "overrides": [ov(), ov(value=4)],
                   "target": {"title_id": TITLE_ID, "releases": ["r"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True)
        cmd_import(paths, mod("d.ok", [ov(), ov(variable=3, kind="byte", value=6)]), enable=True)
        check("designer import: a mod with one valid and one unsafe edit is refused whole; nothing is installed",
              refused(lambda: cmd_import(paths, mod("d.half", [ov(variable=1, kind="real", value=1.0),
                                                                ov(variable=2)]), enable=True),
                      "UNSUPPORTED") is True and not installed_dir(paths, "d.half").exists())
        res = resolve_all(paths, write_plan=paths["cache"])
        plan = Path(res["plan"]).read_text(encoding="utf-8")
        check("designer plan: the valid mod applies (4 ranges) and is named as changing game logic",
              res["active"] == ["d.ok"] and res["ranges"] == 4 and res["gameplay_active"] == ["d.ok"]
              and "\ngameplay d.ok\n" in plan and res["mods"][0]["gameplay"] is True, res)
        cmd_import(paths, mod("d.top", [ov(value=99)]), enable=True)
        cmd_move(paths, "d.top", "top")
        res = resolve_all(paths)
        low = next(x for x in res["mods"] if x["id"] == "d.ok")
        check("designer priority: a higher mod over one variable refuses the whole lower mod",
              res["active"] == ["d.top"] and low["code"] == "CONFLICT", res["mods"])
        for mid in ("d.ok", "d.top"):
            cmd_set(paths, mid, False)
        res = resolve_all(paths, write_plan=paths["cache"])
        check("designer disabled: no plan, nothing gameplay-active, the mods stay marked",
              res["ranges"] == 0 and res["gameplay_active"] == [] and all(x["gameplay"] for x in res["mods"])
              and not (paths["cache"] / PLAN_NAME).exists(), res)
        check("designer: game files are never written",
              before == {p: p.read_bytes() for p in game.rglob("*") if p.is_file()})


def selftest_script(check, refused):
    """D-223: script-constant overrides on a synthetic level (two behaviours, three scripts, pointer and rewritten
    nodes) and on a synthetic fix.lvl; manifest validation, refusals, priority and the written plan; D-224 marking."""
    import subprocess
    def level(names, fix_id=1, dup=False):
        lvl, slots = bytearray(0x1000), []

        def ptr(at, to, fid=fix_id):   # a pointer slot at file offset `at` to file offset `to`
            struct.pack_into(">I", lvl, at, to - 4)
            slots.append((fid, at - 4))

        def nodes(at, rows):
            for k, (p, ind, kind) in enumerate(rows + [(0, 0, 0)]):
                struct.pack_into(">IHBB", lvl, at + 8 * k, p & 0xFFFFFFFF, 0, ind, kind)
        ptr(0x100, 0x200)
        struct.pack_into(">I", lvl, 0x104, 2)
        if dup:   # a second list naming the first behaviour again, at another record
            ptr(0x108, 0x900)
            struct.pack_into(">I", lvl, 0x10C, 1)
            lvl[0x900:0x900 + len(names[0])] = names[0].encode()
        for i, (nm, arr, count) in enumerate(((names[0], 0x500, 2), (names[1], 0x520, 1))):
            r = 0x200 + i * BEHAVIOR_SIZE
            lvl[r:r + len(nm)] = nm.encode()
            ptr(r + 0x100, arr)
            lvl[r + 0x108] = count
        ptr(0x500, 0x600)
        ptr(0x504, 0x700)
        ptr(0x520, 0x800)
        nodes(0x600, [(5, 1, 0x02), (7, 2, 0x0C), (struct.unpack(">I", struct.pack(">f", 1.5))[0], 2, 0x0D),
                      (0, 2, 0x17), (0x00010002, 2, 0x1F), (9, 2, 0x0C)])
        ptr(0x600 + 8 * 3, 0x200)   # node 3 (type 17) is a relocated pointer
        nodes(0x700, [(100, 1, 0x0C)])
        nodes(0x800, [(-3, 1, 0x0C)])
        ptr(0x600 + 8 * 5, 0x200)   # node 5 claims to be an int, but the table lists its word: never edited
        return bytes(lvl), struct.pack(">I", len(slots)) + b"".join(struct.pack(">iI", f, loc) for f, loc in slots)

    b0 = "Gen\\M_Test\\M_Test.rul^CreateIntelligence^CreateComport:T_Init"
    b1 = "Gen\\M_Test\\M_Test.rul^CreateIntelligence^CreateComport:T_Move"
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        game = td / "game"
        (game / "GAMEDATAbin" / "lvl1").mkdir(parents=True)
        (game / "GAMEDATAbin" / "dup1").mkdir(parents=True)
        lvl, ptr = level([b0, b1])
        (game / "GAMEDATAbin" / "lvl1" / "lvl1.lvl").write_bytes(lvl)
        (game / "GAMEDATAbin" / "lvl1" / "lvl1.ptr").write_bytes(ptr)
        fix, fptr = level([b0, b1], fix_id=0)
        (game / "GAMEDATAbin" / "fix.lvl").write_bytes(fix)
        (game / "GAMEDATAbin" / "fix.ptr").write_bytes(fptr)
        d, dptr = level([b0, b1], dup=True)
        (game / "GAMEDATAbin" / "dup1" / "dup1.lvl").write_bytes(d)
        (game / "GAMEDATAbin" / "dup1" / "dup1.ptr").write_bytes(dptr)
        before = {p: p.read_bytes() for p in game.rglob("*") if p.is_file()}
        paths = {"home": None, "mods": td / "mods", "cache": td / "cache", "game": game}
        ix = read_script_index(game, "lvl1")
        s0 = ix["behaviours"][b0]
        check("script: index finds both behaviours, their scripts and nodes (up to the next indent 0)",
              set(ix["behaviours"]) == {b0, b1} and [len(s[1]) for s in s0] == [6, 1]
              and len(ix["behaviours"][b1][0][1]) == 1, {k: v and [len(s[1] or ()) for s in v] for k, v in ix["behaviours"].items()})
        h0, h1 = script_hash(ix, *s0[0]), script_hash(ix, *s0[1])
        info = cmd_script_info(paths, "lvl1", "t_init")
        consts = info["behaviors"][0]["scripts"][0]["constants"]
        check("script-info: constants of script 0 are the int and real nodes with their values",
              consts == [{"node": 1, "kind": "int", "value": 7}, {"node": 2, "kind": "real", "value": 1.5},
                         {"node": 5, "kind": "int", "value": 0x200 - 4}]
              and info["behaviors"][0]["scripts"][0]["script_sha256"] == h0, info)

        def ov(**kw):
            o = {"type": "script-constant", "level": "lvl1", "behavior": b0, "script": 0, "node": 1,
                 "script_sha256": h0, "kind": "int", "value": 3}
            o.update(kw)
            return o
        (p, off, data, what), = compile_script_constants([ov()], paths)
        check("compile: an int constant is 4 bytes in place at its node, big-endian",
              p.name == "lvl1.lvl" and off == 0x608 and data == struct.pack(">i", 3), (p, off, data))
        (_, off, data, _), = compile_script_constants([ov(node=2, kind="real", value=-0.25)], paths)
        check("compile: a real constant is a big-endian float32", off == 0x610 and data == struct.pack(">f", -0.25))
        (_, off, data, _), = compile_script_constants([ov(script=1, node=0, script_sha256=h1, value=-(1 << 31))], paths)
        check("compile: script 1 of the behaviour, the smallest int32", off == 0x700 and data == b"\x80\0\0\0")
        (p, off, _, _), = compile_script_constants([ov(level="fix")], paths)
        check("compile: fix.lvl (own file id 0)", p.name == "fix.lvl" and off == 0x608)
        for label, o, code in (("an int declared on a real node", ov(node=2), "TARGET_CHANGED"),
                               ("a real declared on an int node", ov(kind="real", value=1.0), "TARGET_CHANGED"),
                               ("a relocated pointer node", ov(node=3), "TARGET_CHANGED"),
                               ("a load-rewritten node (type 1F)", ov(node=4), "TARGET_CHANGED"),
                               ("an int node whose word is in the pointer table", ov(node=5), "TARGET_CHANGED"),
                               ("a changed script (other hash)", ov(script_sha256="0" * 64), "TARGET_CHANGED"),
                               ("an unknown behaviour", ov(behavior=b0 + "x"), "TARGET_MISSING"),
                               ("a script index past the behaviour's", ov(script=2), "TARGET_MISSING"),
                               ("a node index past the script's", ov(node=6), "TARGET_MISSING"),
                               ("an unknown level", ov(level="nolevel"), "TARGET_MISSING"),
                               ("a behaviour named twice in its level", ov(level="dup1"), "TARGET_CHANGED")):
            check(f"compile: refused: {label}", refused(lambda o=o: compile_script_constants([o], paths), code) is True,
                  refused(lambda o=o: compile_script_constants([o], paths), code))
        for label, o, code in (("an unknown key", ov(extra=1), "BAD_MANIFEST"),
                               ("a missing key", {k: v for k, v in ov().items() if k != "script_sha256"}, "BAD_MANIFEST"),
                               ("a level path", ov(level="../lvl1"), "BAD_MANIFEST"),
                               ("a kind other than int / real", ov(kind="actor"), "UNSUPPORTED"),
                               ("a boolean value", ov(value=True), "BAD_MANIFEST"),
                               ("a fractional int", ov(value=2.5), "BAD_MANIFEST"),
                               ("an int beyond int32", ov(value=1 << 31), "BAD_MANIFEST"),
                               ("an infinite real", ov(kind="real", value=float("inf")), "BAD_MANIFEST"),
                               ("a NaN real", ov(kind="real", value=float("nan")), "BAD_MANIFEST"),
                               ("a real beyond float32", ov(kind="real", value=1e39), "BAD_MANIFEST"),
                               ("a negative node index", ov(node=-1), "BAD_MANIFEST"),
                               ("a short hash", ov(script_sha256="ab"), "BAD_MANIFEST")):
            check(f"manifest: refused: {label}", refused(lambda o=o: parse_script_constant(o, "o"), code) is True,
                  refused(lambda o=o: parse_script_constant(o, "o"), code))

        def mod(mid, overrides, **kw):
            d = td / "src" / mid
            d.mkdir(parents=True)
            m = {"format": 1, "id": mid, "name": mid, "version": "1.0.0", "overrides": overrides,
                 "target": {"title_id": TITLE_ID, "releases": release_ids(paths), "min_port_version": "0.0.1"}}
            m.update(kw)
            (d / "mod.json").write_text(json.dumps(m), encoding="utf-8")
            return d
        check("manifest: the same node twice in one mod is refused",
              refused(lambda: parse_manifest({"mod.json": json.dumps(
                  {"format": 1, "id": "x.twice", "name": "x", "version": "1.0.0", "overrides": [ov(), ov(value=4)],
                   "target": {"title_id": TITLE_ID, "releases": ["r"], "min_port_version": "0.0.1"}}).encode()}),
                  "BAD_MANIFEST") is True)
        cmd_import(paths, mod("t.low", [ov(value=11), ov(node=2, kind="real", value=2.0)]), enable=True)
        res = resolve_all(paths, write_plan=paths["cache"])
        plan = Path(res["plan"]).read_text(encoding="utf-8")
        rng = [ln.split() for ln in plan.splitlines() if ln.startswith("range ")]
        blobs = {int(x[2]): Path(" ".join(x[7:])).read_bytes() for x in rng}
        check("plan: two 4-byte ranges in the level file, hashes of the old and new bytes",
              res["active"] == ["t.low"] and blobs == {0x608: struct.pack(">i", 11), 0x610: struct.pack(">f", 2.0)}
              and all(x[3] == "4" and x[4] == f"{fnv1a64(lvl[int(x[2]):int(x[2]) + 4]):016x}" for x in rng)
              and f"lvl1{os.sep}lvl1.lvl" in plan, plan)
        lines = plan.splitlines()
        check("D-224: the applied script mod is gameplay-affecting: report, result and one plan record after the mods",
              res["gameplay_active"] == ["t.low"] and res["mods"][0]["gameplay"] is True
              and [ln for ln in lines if ln.startswith("gameplay ")] == ["gameplay t.low"]
              and lines.index("gameplay t.low") == lines.index("mod t.low 1.0.0") + 1, (res, lines[:6]))
        cmd_import(paths, mod("t.high", [ov(value=12)]), enable=True)
        cmd_move(paths, "t.high", "top")
        res = resolve_all(paths, write_plan=paths["cache"])
        low = next(x for x in res["mods"] if x["id"] == "t.low")
        check("priority: a higher mod changing one of its nodes refuses the whole lower script mod (no half edit)",
              res["active"] == ["t.high"] and low["state"] == "invalid" and low["code"] == "CONFLICT", res["mods"])
        check("D-224: conflict: only the applied mod is named in the plan; the refused one stays marked in the list",
              res["gameplay_active"] == ["t.high"] and low["gameplay"] is True
              and [ln for ln in Path(res["plan"]).read_text(encoding="utf-8").splitlines()
                   if ln.startswith("gameplay ")] == ["gameplay t.high"], res)
        rows = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve()), "list", "--rows", "--mods-root",
                               str(paths["mods"]), "--cache", str(paths["cache"]), "--game-dir", str(game)],
                              capture_output=True, text=True, encoding="utf-8")
        mod_rows = {r.split("\t")[1]: r.split("\t") for r in rows.stdout.splitlines() if r.startswith("MOD\t")}
        check("D-224: --rows gives the launcher a 12th column: 1 for both script mods (applied or not)",
              rows.returncode == 0 and len(mod_rows) == 2 and all(len(r) == 12 and r[11] == "1" for r in mod_rows.values()),
              rows.stdout[-400:] + rows.stderr[-400:])
        cmd_move(paths, "t.high", "bottom")
        res = resolve_all(paths)
        high = next(x for x in res["mods"] if x["id"] == "t.high")
        check("priority: below the other, it is refused in turn; the upper mod applies whole",
              res["active"] == ["t.low"] and high["code"] == "CONFLICT", res["mods"])
        cmd_set(paths, "t.high", False)
        cmd_set(paths, "t.low", False)
        res = resolve_all(paths, write_plan=paths["cache"])
        check("disabled: no plan is written", res["ranges"] == 0 and not (paths["cache"] / PLAN_NAME).exists(), res)
        check("D-224: disabled script mods stay marked in the list but nothing is gameplay-active",
              res["gameplay_active"] == [] and all(x["gameplay"] for x in res["mods"]), res)
        check("game files are never written", before == {p: p.read_bytes() for p in game.rglob("*") if p.is_file()})


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


def selftest_actor_primitives(check, refused):
    """G6-P5 (D-258): the shared structural actor primitives on synthetic data (no game files)."""
    def fail(why):
        raise Refusal("STRUCTURE_CHECK", why)
    segs, size, cmap = actor_segments(0x40, [(0x10, 0x20)], packed=True)
    useg, usize, ucmap = actor_segments(0x40, [(0x10, 0x20)], packed=False)
    check("actor_segments: packed keeps each segment in its 16-byte phase; unpacked keeps offsets",
          segs == [(0, 0x10, 0), (0x20, 0x40, 0x10)] and size == 0x30 and cmap(0x24) == 0x14
          and useg == [(0, 0x10, 0), (0x20, 0x40, 0x20)] and usize == 0x40 and ucmap(0x24) == 0x24)
    try:
        cmap(0x18)
        unmapped = False
    except KeyError:
        unmapped = True
    check("actor_segments: an offset inside a left-out region raises", unmapped)
    L, end = actor_layout(0x1004, 0x48, 0x40, 8, 2, fail, always=True, table_words=3)
    check("actor_layout: the copy in the source's 16-byte phase, then personal, name, record, backups, matrix copy, "
          "always element, table; tail padded to 16",
          L == {"copy": 0x1008, "personal": 0x1048, "name": 0x105C, "record": 0x1064, "backup": 0x10AC,
                "backup_copy": 0x10DC, "always": 0x1130, "table": 0x1144} and end == 0x1150, (L, hex(end)))
    check("actor_layout: a name that breaks word alignment refuses",
          refused(lambda: actor_layout(0x1000, 0x10, 0x40, 3, 1, fail), "STRUCTURE_CHECK") is True)
    base = bytearray(0x100)
    struct.pack_into(">I", base, 0x10, 5)
    check("apply_original_edits: two edits of one word refuse; a wrong original value refuses",
          refused(lambda: apply_original_edits(bytes(base), bytearray(base), [(0x10, 5, 6, "a"), (0x10, 5, 7, "b")],
                                               fail), "STRUCTURE_CHECK") is True
          and refused(lambda: apply_original_edits(bytes(base), bytearray(base), [(0x10, 4, 6, "a")], fail),
                      "STRUCTURE_CHECK") is True)
    nb = bytearray(base)
    ed = apply_original_edits(bytes(base), nb, [(0x14, 0, 9, "y"), (0x10, 5, 6, "x")], fail)
    check("apply_original_edits: edits applied in offset order", ed == [(0x10, "x"), (0x14, "y")]
          and _u32(nb, 0x10) == 6 and _u32(nb, 0x14) == 9)
    ptr = struct.pack(">IiI", 1, 1, 0x20) + b"CROSSCROSSCROSS!"
    check("extend_pointer_table: new entries after the original ones, in order, the cross-file table kept",
          extend_pointer_table(ptr, [(1, 0x30), (2, 0x40)]) == struct.pack(">IiIiIiI", 3, 1, 0x20, 1, 0x2C, 2, 0x3C)
          + b"CROSSCROSSCROSS!")
    tl = bytearray(0x40)
    struct.pack_into(">I", tl, 0x20, 4)
    ntl = bump_actor_count(bytes(tl), {"world": 0x10}, 4, fail)
    check("bump_actor_count: only the count word + 1; a wrong count refuses",
          _u32(ntl, 0x20) == 5 and ntl[:0x20] == tl[:0x20] and ntl[0x24:] == tl[0x24:]
          and refused(lambda: bump_actor_count(bytes(tl), {"world": 0x10}, 3, fail), "STRUCTURE_CHECK") is True)
    # a synthetic 0x40-byte source block at 0x40: links at +0x14 / +0x18, an owned pointer at +0x20 (-> +0x30), a
    # shared one at +0x24 (-> 0x10), a reference at +0x28 (-> 0x80 after the copy is retargeted), an other-file
    # pointer at +0x1C; its standard-game record at +0x30 (personal index at +0x38)
    lvl = bytearray(0x100)
    for k, v in ((0x14, 0x8C), (0x18, 0x0C), (0x1C, 0x9B0), (0x20, 0x6C), (0x24, 0x0C), (0x28, 0x3C)):
        struct.pack_into(">I", lvl, 0x40 + k, v)
    slots = {0x54: 1, 0x58: 1, 0x5C: 2, 0x60: 1, 0x64: 1, 0x68: 1}
    src = {"slots": slots, "next": 0x90, "std": 0x70, "pcount": 7}
    kinds = {0x54: "link", 0x58: "link", 0x5C: "other", 0x60: "owned", 0x64: "shared", 0x68: ("ref", 0xA0)}
    sg, sz, cm = actor_segments(0x40, (), packed=False)
    new = bytearray(lvl) + bytearray(0x40)
    ns = actor_copy(new, bytes(lvl), src, 0x40, 0x100, sg, cm, kinds, fail)
    check("actor_copy: owned rebased, shared / other kept, reference retargeted, links and personal index written, "
          "slots in block order",
          ns == [(1, 0x114), (1, 0x118), (2, 0x11C), (1, 0x120), (1, 0x124), (1, 0x128)]
          and [_u32(new, 0x100 + k) for k in (0x14, 0x18, 0x1C, 0x20, 0x24, 0x28, 0x38)]
          == [0x8C, 0x3C, 0x9B0, 0x12C, 0x0C, 0x9C, 7], [hex(_u32(new, 0x100 + k)) for k in range(0, 0x40, 4)])
    for name, kd, sgs in (("an unclassified relocated word", {k: v for k, v in kinds.items() if k != 0x64}, None),
                          ("an unknown class", kinds | {0x64: "rebase"}, None),
                          ("a malformed reference", kinds | {0x68: ("ref", "x")}, None),
                          ("a sibling link not classified as a link", kinds | {0x54: "shared"}, None),
                          ("an owned pointer into a left-out region", kinds,
                           actor_segments(0x40, [(0x30, 0x40)], packed=False))):
        sgx, _, cmx = sgs if sgs else (sg, sz, cm)
        check(f"actor_copy: {name} refuses",
              refused(lambda: actor_copy(bytearray(lvl) + bytearray(0x40), bytes(lvl), src, 0x40, 0x100, sgx, cmx,
                                         kd, fail), "STRUCTURE_CHECK") is True)


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
                                    "text-find", "texture-info", "texture-export", "script-info", "selftest",
                                    "structural-end", "structural-recovery", "terrain-patch", "level-patch"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--home")
    ap.add_argument("--mods-root")
    ap.add_argument("--cache")
    ap.add_argument("--game-dir")
    ap.add_argument("--out")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--enable", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="level-patch (G6-P24): validate and preview only; writes nothing (never with --out)")
    ap.add_argument("--behavior", help="script-info: only behaviours whose name contains this text, in detail")
    ap.add_argument("--model", help="script-info (D-226): the macros of AI models whose first behaviour contains this")
    ap.add_argument("--rows", action="store_true", help="tab-separated rows for the Settings launcher")
    ap.add_argument("--session", help="G5-P2b: the launch session id (plan, structural-end)")
    ap.add_argument("--plan-sha", help="G5-P2b: structural-end: the plan's SHA-256 from the marker")
    ap.add_argument("--controlled", choices=("yes", "no"), help="G5-P2b: structural-end: the session ended normally")
    ap.add_argument("--text-packer", choices=TEXT_PACKERS,
                    help="M38: auto (default; compacts only when the M34 packer refuses), m34 or compact")
    a = ap.parse_args()
    if a.text_packer:
        os.environ[TEXT_PACKER_ENV] = a.text_packer
    if a.cmd == "selftest":
        return selftest()
    paths = resolve_paths(a)
    need = {"validate": 1, "import": 1, "list": 0, "enable": 1, "disable": 1, "remove": 1, "move": 2, "plan": 0,
            "text-find": 1, "texture-info": 1, "texture-export": 2, "script-info": 1, "structural-end": 0,
            "structural-recovery": None, "terrain-patch": 1, "level-patch": 1}[a.cmd]
    try:
        if need is None:   # structural-recovery [clear]
            if a.args not in ([], ["clear"]):
                raise Refusal("USAGE", "structural-recovery [clear]")
        elif len(a.args) != need:
            raise Refusal("USAGE", f"{a.cmd} takes {need} argument(s)")
        if a.check and a.cmd != "level-patch":
            raise Refusal("USAGE", "--check is a level-patch option")
        if a.session is not None and not SESSION_RE.match(a.session):
            raise Refusal("USAGE", "--session: 1-64 characters of A-Z a-z 0-9 . _ -")
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
            r = resolve_all(paths, write_plan=a.out or paths["cache"], session=a.session)
        elif a.cmd == "structural-end":   # G5-P2b
            if not a.session or not a.plan_sha or not a.controlled:
                raise Refusal("USAGE", "structural-end --session S --plan-sha H --controlled yes|no")
            r = end_structural_session(paths, a.session, a.plan_sha, a.controlled == "yes")
        elif a.cmd == "structural-recovery":   # G5-P2b: status, or the explicit re-authorization
            st, d = read_structural_marker(paths)
            r = {"marker": st, "session": (d or {}).get("session")}
            if a.args == ["clear"] and st != "none":
                structural_marker_path(paths).unlink()
                r["cleared"] = True
        elif a.cmd == "terrain-patch":   # G6-P17 (D-273)
            r = cmd_terrain_patch(paths, Path(a.args[0]), Path(a.out) if a.out else None)
        elif a.cmd == "level-patch":   # G6-P21 (D-277)
            r = cmd_level_patch(paths, Path(a.args[0]), Path(a.out) if a.out else None, a.check)
        elif a.cmd == "text-find":
            r = cmd_text_find(paths, a.args[0])
        elif a.cmd == "texture-info":
            r = cmd_texture_info(paths, a.args[0])
        elif a.cmd == "script-info" and a.model is not None:
            if not SCRIPT_LEVEL_RE.match(a.args[0]):
                raise Refusal("USAGE", "script-info LEVEL: a level folder name such as intro_10, or fix")
            r = cmd_macro_info(paths, a.args[0], a.model)
        elif a.cmd == "script-info":
            r = cmd_script_info(paths, a.args[0], a.behavior)
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
    if code and a.cmd == "level-patch":   # G6-P24: a refused level patch writes no mod folder (checked by g6p24)
        r["advice"] = LEVEL_PATCH_ADVICE.get(r["code"], r["advice"])
        r["written"] = False
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
                                    cell(m.get("description")), str(m.get("ranges", 0)), str(len(m.get("shadowed", []))),
                                    "1" if m.get("gameplay") else "0"]))   # D-224: changes game logic
        lines.append("END")
        sys.stdout.buffer.write(("\n".join(lines) + "\n").encode("utf-8"))
    elif a.json:
        print(json.dumps(r, indent=1, default=str))
    elif a.cmd == "level-patch":   # G6-P24 (D-280): concise text; the structured report is --json
        sys.stdout.write(level_patch_text(r, Path(a.args[0]).name if a.args else "?"))
    else:
        print(json.dumps(r, indent=1, default=str, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
