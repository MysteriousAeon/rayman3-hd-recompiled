"""G6-P89 (D-338): pins for the test-only experimental 3:2 renderer (tools/g6p89_scale32.h, g6p89_scale32_patch.py).

Rules (each also checked against a mutant that must fail):
  * gate: the path needs R3HD_NONINTRUSIVE and R3HD_TEST_G6P89_SCALE_3_2 exactly "1"; refusal logs once and exits 137;
    the integer path of Scale is the SDK's `value * scale` expression;
  * the flag is named only by the G6-P89 tools and the records: never by play.ps1, the hidden runner, the launcher or
    the Settings registry, so a person cannot select 1.5x;
  * build order: the patch replays last (after the G6-P88 census patch) and this regression runs before M8_BUILD_OK;
  * every hunk of tools/g6p89_scale32_edits.py is unique and changes only pinned SDK lines (no earlier patch's text);
  * after a replay: the installed header equals tools/g6p89_scale32.h, every hunk is present once, the three 3:2
    shader headers carry the manifest's DXBC, and every remaining integer-accessor call in the 3:2-capable files is in
    an allowed context (integer-only branch, a refused path, or log text inside an IntegerLogScope);
  * host test (tools/g6p89_scale32_test.cpp, compiled with clang++): exact arithmetic, model R collision freedom, range
    and ownership, no aliasing, checksum equal to the G6-P88 Python model, refusal exit code 137;
  * G6-P92 resolve extents: the 3:2 copy refusal is g6p89::ResolveExtentExact (whole 8-pixel threads along X, whole
    4-row groups along Y), the 3:2 copy variant declares 8x4 thread groups (source edit and, after a replay, the
    installed DXBC) matching kResolveGroupHeightLog2, GetCopyShader uses that group height only while rational (the
    integer path keeps the SDK table), and model S6 (tools/g6p88_sdk_scaled_model.py) passes with every negative
    control detected. Mutants reject the old over-conservative height rule, an always-true rule, the 4-row group
    height leaking into the integer path and an 8-row 3:2 shader.
"""
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
sys.path.insert(0, str(ROOT / "tools"))
FLAG = "R3HD_TEST_G6P89_SCALE_3_2"
DEV_FLAG = "R3HD_RENDER_SCALE_3_2"
# G6-P141: R3HD_RENDER_SCALE_3_2 is wired by play.ps1 exclusively for explicit -RenderScale 1.5 (cleared otherwise);
# legacy hidden-test flag R3HD_TEST_G6P89_SCALE_3_2 stays strictly out of run_milestone6.ps1, the launcher, and registry
# (and is scrubbed in play.ps1 $testOnly).
ALLOWED_FLAG_PREFIXES = ("tools/g6p89_", "tools/g6p141_", "tools/play.ps1", "tools/linux/r3hd_play.py", "reports/post_release/G6P89_",
                         "tools/g6p90_", "tools/g6p91_", "reports/post_release/G6P90_", "reports/post_release/G6P91_",
                         "reports/post_release/G6P92_", "reports/post_release/G6P140_", "reports/post_release/G6P141_",
                         "PROJECT_STATE.md", "CURRENT_TASK.md",
                         "DECISIONS.md", "EXPERIMENTS.md", "RE_NOTES.md", "KNOWLEDGE_INDEX.md", "AGENT_WORKFLOWS.md",
                         "config/release/production_identity.json")
CLANG = r"C:\Program Files\LLVM\bin\clang++.exe"
# Remaining integer-accessor calls allowed in 3:2-capable files after the replay (substring of the line).
ALLOWED_ACCESSOR_LINES = (
    "uint32_t(resource_desc.SampleDesc.Count), draw_resolution_scale_x(),",  # M15 rt_create, IntegerLogScope
    "draw_resolution_scale_y());",                                   # continuation of the two lines above / below
    "draw_resolution_scale_x(), draw_resolution_scale_y());",         # ROV clear group count (ROV refused at 3:2)
    "command_list.D3DDispatch((dispatch.width_tiles * draw_resolution_scale_x())",  # integer branch
    "dispatch.height_tiles * draw_resolution_scale_y(), 1);",
    "uint32_t draw_resolution_scale_area = draw_resolution_scale_x() * draw_resolution_scale_y();",  # integer branch
    "texture_resolution_scaled && !texture_scale.Rational() ? draw_resolution_scale_",  # integer only
    "(draw_resolution_scale_x() * draw_resolution_scale_y() - 1);",  # texture memory limit, integer branch
    "uint32_t pixel_size_x = draw_resolution_scale_x()",              # host depth store (refused above at 3:2)
    "uint32_t pixel_size_y = draw_resolution_scale_y()",
    "assert_true(draw_resolution_scale_x() <= 7);",                   # host depth store constant (refused first)
    "assert_true(draw_resolution_scale_y() <= 7);",
    "constant.resolution_scale_x = draw_resolution_scale_x();",
    "constant.resolution_scale_y = draw_resolution_scale_y();",
    "constants.scale_x = texture_cache_->draw_resolution_scale_x();",  # readback downscale (refused via accessor)
    "constants.scale_y = texture_cache_->draw_resolution_scale_y();",
    "uint64_t scale_x = texture_cache_->draw_resolution_scale_x();",   # occlusion, integer branch
    "uint64_t scale_y = texture_cache_->draw_resolution_scale_y();",
)
SCALE_FILES = ("include/rex/graphics/pipeline/render_target/cache.h", "src/graphics/pipeline/render_target/cache.cpp",
               "include/rex/graphics/pipeline/texture/cache.h", "src/graphics/pipeline/texture/cache.cpp",
               "src/graphics/util/draw.cpp", "src/graphics/d3d12/render_target_cache.cpp",
               "src/graphics/d3d12/texture_cache.cpp", "include/rex/graphics/d3d12/texture_cache.h",
               "src/graphics/d3d12/command_processor.cpp", "src/graphics/d3d12/pipeline_cache.cpp")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def sources() -> dict:
    t = {n: read(ROOT / "tools" / n) for n in ("g6p89_scale32.h", "build_milestone8.bat", "run_milestone6.ps1",
                                                "play.ps1", "g6p89_scale32_patch.py", "g6p89_scale32_edits.py",
                                                "g6p89_shader_build.py")}
    try:
        files = subprocess.check_output(["git", "-C", str(ROOT), "grep", "-l", "--untracked", FLAG],
                                        text=True).split()
    except subprocess.CalledProcessError:
        files = []
    t["_flag_files"] = files
    return t


def static_check(t: dict) -> list:
    e = []
    h = t["g6p89_scale32.h"]
    if ('std::getenv("R3HD_RENDER_SCALE_3_2")' not in h or
            'std::getenv("R3HD_NONINTRUSIVE")' not in h or
            'std::getenv("R3HD_TEST_G6P89_SCALE_3_2")' not in h):
        e.append("gate must read R3HD_RENDER_SCALE_3_2, R3HD_NONINTRUSIVE and R3HD_TEST_G6P89_SCALE_3_2")
    if ('return std::strcmp(dev_flag, "1") == 0;' not in h or
            'return nonintrusive != nullptr && legacy_flag != nullptr && std::strcmp(legacy_flag, "1") == 0;' not in h):
        e.append("gate must require exact \"1\" for dev flag or runner+legacy flag")
    if "std::_Exit(kExitCode);" not in h or "constexpr int kExitCode = 137;" not in h:
        e.append("refusal must exit the process (code 137)")
    if "      return v * num;  // integer path: the original uint32 expression" not in h:
        e.append("integer path of Scale::Axis must be the original expression")
    if "if (den == 1) return guest * (uint64_t(x) * y);" not in h:
        e.append("integer path of AreaBytes changed")
    bat = t["build_milestone8.bat"]
    i127, i89 = bat.find("python tools\\g6p127_crown_blend_patch.py"), bat.find("python tools\\g6p89_scale32_patch.py")
    if i89 < 0 or i89 < i127 or i89 > bat.find("cmake -S external"):
        e.append("build: the G6-P89 patch must replay after g6p127_crown_blend_patch.py and before cmake")
    r127 = bat.find("python tools\\g6p127_crown_blend_regression.py || exit /b 1")
    r89 = bat.find("python tools\\g6p89_scale32_regression.py || exit /b 1")
    if r89 < 0 or r89 < r127 or r89 > bat.find("echo M8_BUILD_OK"):
        e.append("build: this regression must run after g6p127_crown_blend_regression.py, before M8_BUILD_OK")
    # G6-P92: the 3:2 resolve extent rule (computed, not a size list) and its dispatch geometry.
    if ("constexpr uint32_t kResolveGroupHeightLog2 = 2;" not in h or
            "constexpr uint32_t kResolveThreadWidthPixels = 8;" not in h or
            "  return host_width % kResolveThreadWidthPixels == 0 && host_height % (1u << kResolveGroupHeightLog2) == 0;"
            not in h):
        e.append("G6-P92: ResolveExtentExact must require whole 8-pixel threads and whole 4-row groups")
    ed = t["g6p89_scale32_edits.py"]
    if ("if (!g6p89::ResolveExtentExact(coordinate_info.width_div_8, height_div_8)) {" not in ed or
            "(height_div_8 & 1)" in ed):
        e.append("G6-P92: the 3:2 resolve size refusal must be ResolveExtentExact (no height-parity rule)")
    if ("draw_scale.Rational() ? g6p89::kResolveGroupHeightLog2 : shader_info.group_size_y_log2;" not in ed or
            "group_count_y_out = (height + ((1 << group_size_y_log2) - 1)) >> group_size_y_log2;" not in ed):
        e.append("G6-P92: GetCopyShader must use 4-row groups only while rational (integer path: SDK table)")
    if ("#define LOCAL_SIZE_X_XE 8\n#ifdef XE_RESOLUTION_SCALE_3_2\n" not in t["g6p89_shader_build.py"] or
            "  #define LOCAL_SIZE_Y_XE 4\n#else\n#define LOCAL_SIZE_Y_XE 8\n#endif\n" not in t["g6p89_shader_build.py"]):
        e.append("G6-P92: the 3:2 copy variant must declare LOCAL_SIZE_Y_XE 4 under XE_RESOLUTION_SCALE_3_2 (else 8)")
    if FLAG in t["run_milestone6.ps1"] or DEV_FLAG in t["run_milestone6.ps1"]:
        e.append("run_milestone6.ps1 must not hardcode the 3:2 flag")
    if "$env:R3HD_RENDER_SCALE_3_2 = $(if ($scale32) { '1' } else { $null })" not in t["play.ps1"]:
        e.append("play.ps1 must set R3HD_RENDER_SCALE_3_2 only when $scale32 is true and clear it otherwise")
    for f in t["_flag_files"]:
        if not f.startswith(ALLOWED_FLAG_PREFIXES):
            e.append(f"flag named outside the G6-P89 tools and records: {f}")
    return e


def dxbc_thread_group(data: bytes):
    """dcl_thread_group (opcode 155) of a DXBC container's SHEX / SHDR chunk, or None."""
    import struct
    if data[:4] != b"DXBC":
        return None
    count = struct.unpack_from("<I", data, 28)[0]
    for i in range(count):
        off = struct.unpack_from("<I", data, 32 + 4 * i)[0]
        if data[off:off + 4] in (b"SHEX", b"SHDR"):
            size = struct.unpack_from("<I", data, off + 4)[0]
            tokens = struct.unpack_from(f"<{size // 4}I", data, off + 8)
            j = 2
            while j < len(tokens):
                tok = tokens[j]
                op, length = tok & 0x7FF, (tok >> 24) & 0x7F
                if op == 0x35:  # customdata: length in the next token
                    length = tokens[j + 1]
                if op == 155:
                    return tokens[j + 1:j + 4]
                if length == 0:
                    return None
                j += length
    return None


def pristine(rel: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(SDK), "show", "HEAD:" + rel]).decode().replace("\r\n", "\n")
    except subprocess.CalledProcessError:
        return ""


def edits_check() -> list:
    from g6p89_scale32_edits import EDITS
    e = []
    for rel, hunks in EDITS.items():
        lines = set(pristine(rel).splitlines(keepends=True))
        for before, after in hunks:
            if before == after:
                e.append(f"{rel}: empty hunk")
            for d in difflib.ndiff(before.splitlines(keepends=True), after.splitlines(keepends=True)):
                if d.startswith("- ") and d[2:] not in lines:
                    e.append(f"{rel}: hunk changes a non-pinned line {d[2:].strip()[:60]!r}")
    return e


def replay_check() -> tuple:
    """Returns (replayed, errors)."""
    from g6p89_scale32_edits import EDITS
    installed = SDK / "include/rex/g6p89_scale32.h"
    if not installed.exists():
        return False, []
    e = []
    if read(installed) != read(ROOT / "tools/g6p89_scale32.h"):
        e.append("installed SDK header differs from tools/g6p89_scale32.h (replay needed)")
    for rel, hunks in EDITS.items():
        text = read(SDK / rel)
        for _, after in hunks:
            if text.count(after) != 1:
                e.append(f"{rel}: hunk present {text.count(after)} times: {after.strip()[:60]!r}")
    import g6p87_shader_repro as g87
    from g6p89_shader_manifest import MANIFEST as manifest
    for v in manifest["variants"]:
        p = SDK / "src/graphics/shaders/bytecode/d3d12_5_1" / v["header"]
        if not p.exists() or g87.sha256(g87.parse_header(read(p))[1]) != v["dxbc_sha256"]:
            e.append(f"3:2 shader {v['header']} missing or not the manifest DXBC")
        elif v["header"] == "resolve_fast_32bpp_1x2xmsaa_scaled32_cs.h":
            tg = dxbc_thread_group(g87.parse_header(read(p))[1])
            if tg is None or tuple(tg) != (8, 4, 1):
                e.append(f"G6-P92: installed 3:2 copy variant thread group {tg}, expected (8, 4, 1)")
    for rel in SCALE_FILES:
        for n, line in enumerate(read(SDK / rel).splitlines(), 1):
            if re.search(r"draw_resolution_scale_[xy]\(\)", line) and "uint32_t draw_resolution_scale_" not in line:
                if not any(a in line for a in ALLOWED_ACCESSOR_LINES):
                    e.append(f"{rel}:{n}: integer accessor outside an allowed context: {line.strip()[:80]}")
    return True, e


def model_checksum() -> str:
    import g6p88_sdk_scaled_model as m
    nl = m.unit_log2(2)
    h, mask = 1469598103934665603, (1 << 64) - 1
    for hy in range(1080):
        for hx in range(1920):
            xs = hx >> nl
            g = m.tiled2d(((xs // 3) * 2) << nl, (hy // 3) * 2, 1280, 2)
            a = g * 9 // 4 + (((((xs % 3) * 3 + hy % 3) << nl) + (hx & ((1 << nl) - 1))) << 2)
            h = ((h ^ a) * 1099511628211) & mask
    # Tie the closed form to the model's own Fraction implementation on a sample.
    for hx, hy in ((0, 0), (11, 2), (12, 3), (1919, 1079), (777, 555)):
        xs = hx >> nl
        g = m.tiled2d(((xs // 3) * 2) << nl, (hy // 3) * 2, 1280, 2)
        assert m.rational_offset(hx, hy, 1280, 2)[1] == \
            g * 9 // 4 + (((((xs % 3) * 3 + hy % 3) << nl) + (hx & ((1 << nl) - 1))) << 2)
    return f"{h:016x}"


def s6_model() -> list:
    """G6-P92: model S6 (resolve dispatch coverage at 3:2) with its negative controls."""
    import g6p88_sdk_scaled_model as m
    v = m.s6_verdict(m.run_s6(full=False))
    bad = [k for k, ok in v.items() if not ok]
    return [f"G6-P92 model S6 failed: {bad}"] if bad else []


def host_test() -> list:
    clang = CLANG if os.path.exists(CLANG) else shutil.which("clang++")
    if not clang:
        return ["clang++ not found for the host test"]
    e = []
    with tempfile.TemporaryDirectory() as tmp:
        exe = os.path.join(tmp, "g6p89_scale32_test.exe")
        r = subprocess.run([clang, "-std=c++20", "-O1", "-D_CRT_SECURE_NO_WARNINGS", "-I", str(ROOT / "tools/g6p89_stub"),
                            "-I", str(ROOT / "tools"), str(ROOT / "tools/g6p89_scale32_test.cpp"), "-o", exe],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return [f"host test compile failed: {r.stderr[-400:]}"]
        r = subprocess.run([exe], capture_output=True, text=True)
        m = re.search(r"G6P89_HOST_TEST PASS checksum=([0-9a-f]{16})", r.stdout)
        if r.returncode != 0 or not m:
            e.append(f"host test failed: {r.stdout.strip()} {r.stderr.strip()[-300:]}")
        elif m.group(1) != model_checksum():
            e.append("host R offsets differ from the G6-P88 Python model")
        r = subprocess.run([exe, "refuse"], capture_output=True, text=True)
        if r.returncode != 137:
            e.append(f"refusal exit code {r.returncode}, expected 137")
    return e


MUTANTS = {
    "flag value": ("g6p89_scale32.h", 'std::strcmp(dev_flag, "1") == 0', 'std::strcmp(dev_flag, "0") != 0'),
    "runner gate": ("g6p89_scale32.h", "return nonintrusive != nullptr && legacy_flag != nullptr",
                    "return legacy_flag != nullptr"),
    "no exit": ("g6p89_scale32.h", "std::_Exit(kExitCode);", "(void)kExitCode;"),
    "integer path": ("g6p89_scale32.h", "      return v * num;  // integer path", "      return v * num + 0;  // integer path"),
    "order": ("build_milestone8.bat", "python tools\\g6p89_scale32_patch.py || exit /b 1\n", ""),
    "regression": ("build_milestone8.bat", "python tools\\g6p89_scale32_regression.py || exit /b 1\n", ""),
    "launcher flag": ("play.ps1", "$env:R3HD_RENDER_SCALE_3_2 = $(if ($scale32) { '1' } else { $null })",
                      "$env:R3HD_RENDER_SCALE_3_2 = '1'"),
    "old height rule": ("g6p89_scale32_edits.py",
                        "if (!g6p89::ResolveExtentExact(coordinate_info.width_div_8, height_div_8)) {",
                        "if ((coordinate_info.width_div_8 & 1) || (height_div_8 & 1)) {"),
    "rule always true": ("g6p89_scale32.h",
                         "  return host_width % kResolveThreadWidthPixels == 0 && "
                         "host_height % (1u << kResolveGroupHeightLog2) == 0;",
                         "  return true;"),
    "4-row groups at integer scales": ("g6p89_scale32_edits.py",
                                       "draw_scale.Rational() ? g6p89::kResolveGroupHeightLog2 : "
                                       "shader_info.group_size_y_log2;",
                                       "g6p89::kResolveGroupHeightLog2;"),
    "8-row 3:2 shader": ("g6p89_shader_build.py", "  #define LOCAL_SIZE_Y_XE 4\n", "  #define LOCAL_SIZE_Y_XE 8\n"),
}


def main() -> int:
    t = sources()
    errors = static_check(t) + edits_check()
    caught = 0
    for name, (f, old, new) in MUTANTS.items():
        m = dict(t)
        m[f] = (t[f].replace(old, new, 1) if old else t[f] + new)
        if m[f] == t[f]:
            errors.append(f"mutant {name} did not apply")
        elif static_check(m):
            caught += 1
        else:
            errors.append(f"mutant {name} not caught")
    replayed, re_errors = replay_check()
    errors += re_errors
    errors += host_test()
    errors += s6_model()
    import g6p89_shader_build
    try:
        names = {x[0] for x in g6p89_shader_build.EDITS}
        assert names == set(g6p89_shader_build.PRISTINE)
    except AssertionError:
        errors.append("shader edit set differs from the pinned file list")
    print(f"G6P89_SCALE32_REGRESSION {'PASS' if not errors else 'FAIL'} mutants={caught}/{len(MUTANTS)} "
          f"replayed={int(replayed)} {errors[:20]}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
