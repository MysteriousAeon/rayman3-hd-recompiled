#!/usr/bin/env python3
"""M44 tooling regression (no game run): the optional gameplay voice-subtitle switch (D-081, experimental), its patch
shape and settings, and the title facts it depends on, re-derived from the local target when it is present.

    python tools/m44_regression.py                 -> M44_REGRESSION PASS checks=N failures=0 skipped=K
    python tools/m44_regression.py --run RUN...    also judges hidden run directories (private/work/m6_runs/RUN):
                                                   a run named *_gamesubs must log mode all and one applied state;
                                                   any other run must log mode original and no M44 state line

Target facts (RE_NOTES "M44"; skipped, never passed, without `private/work/default_image.bin` or the game data): the
two guard instructions of 8212F150, the restriction word 82837348 = 1 in the image and read by that one instruction
only (no store, no address materialisation, no pointer to it), and the M44 case: `fix.lvl` offset 166588 is en.748
with the slot hash of the person's override record, named by intro_15's sound event Play_VD_IN15_Glob_05_04, which is
not on the title's always-show list. This script starts no executable.
"""
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
SDK = ROOT / "external" / "rexglue-sdk"
RUNS = ROOT / "private" / "work" / "m6_runs"
IMAGE = ROOT / "private" / "work" / "default_image.bin"
DATA = ROOT / "private" / "extracted" / "5841123F" / "GAMEDATAbin"
BASE = 0x82000000
TEXT = (0x820E0000, 0x820E0000 + 0x72C550)

checks = failures = skipped = 0


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL {label}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


header = read(TOOLS / "m44_gameplay_subtitles.h")
patch = read(TOOLS / "m44_runtime_patch.py")

# --- the header's rules (mirrored: the hidden runs test the compiled code) ----------------------------------------
consts = dict(re.findall(r"constexpr uint32_t (k\w+) = (0x[0-9A-F]+);", header))
check(consts.get("kRestriction") == "0x82837348" and consts.get("kGuardAddress") == "0x8212F1F4",
      "header: restriction word and guard address")
check("kGuard[2] = {0x3D608283u, 0x816B7348u}" in header, "header: guard = lis r11,-0x7d7d ; lwz r11,0x7348(r11)")
check('std::strcmp(value, "all") == 0' in header and 'std::getenv("R3HD_GAMEPLAY_SUBTITLES")' in header,
      "header: only R3HD_GAMEPLAY_SUBTITLES=all selects it")
check(header.count("write(") == 1 and "write(kRestriction, 0u);" in header and header.count("std::memcpy(guest_base") == 1,
      "header: one guest store, 0 into the restriction word")
check("if (value == 0) return Result::kKept;" in header and "if (value != 1) return Result::kRefusedValue;" in header,
      "header: stores only over the image's value 1; another value refuses")
check("if (!Enabled()) return;" in header and "if (s.done) return;" in header, "header: off = nothing; a refusal is final")
check("s.applied++ == 0 && log" in header, "header: one applied line per process, never per frame")


def step(image: dict, enabled: bool):
    """Python mirror of m44sub::Step on {address: value}."""
    if not enabled:
        return "off", image
    if image.get(0x8212F1F4) != 0x3D608283 or image.get(0x8212F1F8) != 0x816B7348:
        return "refused_guard", image
    v = image.get(0x82837348, 0)
    if v == 0:
        return "kept", image
    if v != 1:
        return "refused_value", image
    return "applied", {**image, 0x82837348: 0}


good = {0x8212F1F4: 0x3D608283, 0x8212F1F8: 0x816B7348, 0x82837348: 1}
check(step(good, False) == ("off", good), "mirror: off writes nothing")
check(step(good, True) == ("applied", {**good, 0x82837348: 0}), "mirror: applied stores 0")
check(step({**good, 0x82837348: 0}, True)[0] == "kept", "mirror: already 0 is kept")
check(step({**good, 0x82837348: 2}, True)[0] == "refused_value", "mirror: unexpected value refused")
check(step({**good, 0x8212F1F8: 0}, True)[0] == "refused_guard", "mirror: another image refused")

# --- patch shape ------------------------------------------------------------------------------------------------
video = read(SDK / "src/kernel/xboxkrnl/xboxkrnl_video.cpp")
cp = read(SDK / "src/graphics/d3d12/command_processor.cpp")
installed = SDK / "include/rex/m44_gameplay_subtitles.h"
check(installed.is_file() and installed.read_bytes() == (TOOLS / "m44_gameplay_subtitles.h").read_bytes(),
      "SDK: installed header equals tools/m44_gameplay_subtitles.h (replay the patch chain)")
check(video.count("m44sub::Swap(") == 1 and video.count("#include <rex/m44_gameplay_subtitles.h>") == 1,
      "SDK: one call site in VdSwap, one include")
i44, i24, i17 = video.find("m44sub::Swap("), video.find("m24ev::Event(m24ev::kVdSwap"), video.find("m17trace::Swap(")
check(0 <= i44 < i24 < i17, "SDK: the call precedes the M24 / M17 lines (the trace sees the applied word)")
check(video.count("#include <rex/m24_event_trace.h>\n#include <mutex>\n") == 1
      and video.count("#include <rex/m44_gameplay_subtitles.h>\n#include <rex/hook.h>\n") == 1,
      "SDK: the M24 / M31 include pair stays together (their replays find it); the M44 include sits before hook.h")
check(video.count('REXLOG_INFO("M44 gameplay_subtitles mode={} state={} frames={}"') == 1, "SDK: state line")
check(cp.count('REXGPU_INFO("M44 gameplay_subtitles={}", m44sub::ModeName());\n'
               '  REXGPU_INFO("M33 mods={}"') == 1, "SDK: mode logged at start-up, in front of the M33 line")
check("REXGPU_INFO(\"M26 texture_orient={}\", m26tex::Enabled() ? \"corrected\" : \"original\");\n"
      "  REXGPU_INFO(\"M23 layer_coords={}\"" in cp, "SDK: the M26 / M23 lines still together")
bat = read(TOOLS / "build_milestone8.bat")
check(bat.index("m36_runtime_patch.py") < bat.index("m44_runtime_patch.py") < bat.index("cmake -S external/rexglue-sdk"),
      "build: the patch replays after M36, before the SDK build")
check("tools\\m44_regression.py" in bat, "build: this regression runs")
check("midasm_hook" not in patch and "toml" not in patch, "patch: host code only, no generated-code hook")

# --- settings: D-090 made it a preference shown in Settings > Corrections (was experimental and hidden, D-081) ---------
reg = json.loads(read(ROOT / "config/settings/registry.json"))
s = reg["settings"].get("gameplay_subtitles", {})
check(s.get("category") == "enhancement" and s.get("scope") == "preference" and s.get("values") == ["original", "all"],
      "registry (D-090): a preference, original | all")
check(s.get("vanilla") == "original" and s.get("hdplus") == "original", "registry: off by default in Vanilla and HD+")
check("ui" not in s and s.get("group") == "corrections" and s.get("launcher") == "GameplaySubtitles"
      and s.get("decision") == "D-081, D-090", "registry: shown under Corrections; -GameplaySubtitles; D-081, D-090")
play = read(TOOLS / "play.ps1")
check("[ValidateSet('original', 'all')][string]$GameplaySubtitles = 'original'," in play, "play.ps1: parameter, default original")
check(play.count("$env:R3HD_GAMEPLAY_SUBTITLES = $GameplaySubtitles") == 1
      and play.count("$env:R3HD_GAMEPLAY_SUBTITLES = $savedGameplaySubs") == 1,
      "play.ps1: sets the variable for the game and restores the caller's afterwards")
sys.path.insert(0, str(TOOLS))
import r3hd_settings as rs  # noqa: E402

r = rs.load_registry()
check(rs.resolve(r, preset="vanilla")["values"]["gameplay_subtitles"] == "original", "resolve: vanilla original")
check(rs.resolve(r, preset="hdplus")["values"]["gameplay_subtitles"] == "original", "resolve: hdplus original")
check(rs.resolve(r, settings={"schema": 3, "preset": "hdplus", "preferences": {"gameplay_subtitles": "all"}})
      ["values"]["gameplay_subtitles"] == "all", "resolve (D-090): HD+ with the preference on")
check(rs.resolve(r, settings={"schema": 1, "preset": "custom", "allow_experimental": True,
                              "overrides": {"gameplay_subtitles": "all"}})["values"]["gameplay_subtitles"] == "all",
      "resolve: custom all with allow_experimental")

# --- target facts ---------------------------------------------------------------------------------------------------
if IMAGE.is_file():
    img = IMAGE.read_bytes()
    word = lambda a: struct.unpack_from(">I", img, a - BASE)[0]
    check((word(0x8212F1F4), word(0x8212F1F8)) == (0x3D608283, 0x816B7348), "image: guard instructions of 8212F150")
    check(word(0x82837348) == 1, "image: restriction word 82837348 = 1")
    check(struct.pack(">I", 0x82837348) not in img, "image: no pointer to the restriction word")
    sites, lis = [], {}
    for a in range(TEXT[0], TEXT[1], 4):
        w = word(a)
        op, rd, ra, d = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
        if op == 15 and ra == 0:
            lis[rd] = (a, d)
            continue
        if d == 0x7348 and ra in lis and lis[ra][1] == 0x8283 and a - lis[ra][0] <= 64 and op in (14, *range(32, 56)):
            sites.append((a, op))
    check(sites == [(0x8212F1F8, 32)], f"image: the word's only use is the lwz at 8212F1F8 (found {[(hex(a), o) for a, o in sites]})")
    names = [m.decode() for m in re.findall(rb"Play_VD_[A-Za-z0-9_]+", img[0x82009400 - BASE:0x82009800 - BASE])]
    check("Play_VD_IN15_Glob_05_04" not in names and "Play_VD_IN10_Murf_01_01" in names,
          "image: the flower line is not on the always-show list; Murfy's intro_10 line is")
else:
    skipped += 7
lvl, bnh = DATA / "fix.lvl", DATA / "WORLD" / "SOUND" / "intro_15.bnh"
if lvl.is_file() and bnh.is_file():
    d = lvl.read_bytes()
    table = struct.unpack_from(">I", d, 0x7D34 + 8)[0] + 4  # second entry: en
    check(struct.unpack_from(">I", d, table + 4 * 748)[0] + 4 == 166588, "data: en.748 points at fix.lvl offset 166588")
    end = d.index(b"\0", 166588)
    check(hashlib.sha256(d[166588:(end + 4) & ~3]).hexdigest()
          == "f6fafde03c81cc2ea8ecad121c14b3d0a3bc314d854baadabe8be6f82a7a653d", "data: the slot hash of the override record")
    check(re.search(rb"file Play_VD_IN15_Glob_05_04 \* subtitle 0x000002ec", bnh.read_bytes()) is not None,
          "data: intro_15 sound event Play_VD_IN15_Glob_05_04 names handle 0x2EC = 748")
else:
    skipped += 3


# --- hidden runs ----------------------------------------------------------------------------------------------------
def judge_run(name: str) -> None:
    logs = "".join(read(p) for p in sorted((RUNS / name).glob("runtime*.log")))
    modes = re.findall(r"M44 gameplay_subtitles=(\w+)", logs)
    states = re.findall(r"M44 gameplay_subtitles mode=(\w+) state=(\w+)", logs)
    if name.endswith("_gamesubs"):
        check(modes == ["all"], f"{name}: mode all logged once ({modes})")
        check(states == [("all", "applied")], f"{name}: one applied state, no refusal ({states})")
    else:
        check(modes == ["original"], f"{name}: mode original logged once ({modes})")
        check(states == [], f"{name}: no M44 state line ({states})")


args = sys.argv[1:]
if args[:1] == ["--run"]:
    for n in args[1:]:
        judge_run(n)

print(f"M44_REGRESSION {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures} skipped={skipped}")
sys.exit(1 if failures else 0)
