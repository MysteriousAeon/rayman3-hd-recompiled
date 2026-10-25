#!/usr/bin/env python3
"""M23 tooling regression (no game run): the two-layer correction (`-LayerCoords separate`, first name
`-WaterLayers`; D-054) is off by default, touches one shader pair only and writes nothing to the guest (D-052).

    python tools/m23_regression.py                 -> M23_REGRESSION PASS checks=N failures=0
    python tools/m23_regression.py --run RUN...    also judge hidden run directories (private/work/m6_runs/RUN):
                                                   a run named *_separate must have drawn the corrected pair,
                                                   any other run must have left the pair as issued
    python tools/m23_regression.py --pair ORIGINAL SEPARATE
                                                   before / after on two traced runs of the same scene (needs
                                                   m23_trace_entry.py --shaders): the water draw carries the
                                                   title's shaders in ORIGINAL and the corrected ones in SEPARATE,
                                                   and the SDK's own disassembly of the corrected ones shows the
                                                   second layer on its own coordinates

The microcode edit itself is tested by m23_water_test.exe (in the build).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
TOOLS = ROOT / "tools"
RUNS = ROOT / "private" / "work" / "m6_runs"
VS, PS = 0x08E9BEDB27BDDEEE, 0x27336DBAE47E8650
VS_LINE, PS_LINE = "add o3.xy__, r3.xyyy, c11.xyyy", "tfetch2D r6, r3.xy, tf1"
checks = failures = 0


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL {label}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def run_log(name: str) -> str:
    return "\n".join(read(p) for p in sorted((RUNS / name).glob("runtime*.log")))


def judge_run(name: str) -> None:
    log = run_log(name)
    # `water_layers` is the label of builds before D-054; run directories of both kinds are judged.
    mode = re.findall(r"M23 (?:layer_coords|water_layers)=(\w+)", log)
    pair = re.findall(r"M23 (?:layer_coords|water_layers) pair=(\w+)", log)
    if name.endswith("_separate"):
        check(mode and set(mode) == {"separate"}, f"{name}: correction selected")
        check(pair == ["corrected"], f"{name}: the pair was found once and corrected (got {pair})")
    else:
        check(mode and set(mode) == {"original"}, f"{name}: the title's behaviour (got {sorted(set(mode))})")
        check(not pair, f"{name}: no pair line without the switch")


def water_draws(name: str):
    sys.path.insert(0, str(TOOLS))
    from m22_draw_report import parse
    found = []
    for trace in sorted((RUNS / name).glob("m22_draws_*.bin")):
        draws, _, _ = parse(trace)
        for d in draws:
            if len(d["textures"]) == 2 and d["regs"][0x201] == 0x06070607 and len(d["bindings"]) == 1 \
                    and d["bindings"][0]["stride"] == 36:
                found.append((trace.name, d["draw"], d["vs"], d["ps"]))
    return found


def disassembly(name: str, shader_hash: int, kind: str) -> str:
    path = RUNS / name / "shaders" / f"shader_{shader_hash:016X}.ucode.{kind}"
    return read(path) if path.is_file() else ""


def judge_pair(original: str, separate: str) -> None:
    judge_run(original)
    judge_run(separate)
    before, after = water_draws(original), water_draws(separate)
    check(bool(before) and all(vs == VS and ps == PS for _, _, vs, ps in before),
          f"{original}: two-layer draws carry the title's pair ({len(before)} draws)")
    check(bool(after) and all(vs != VS and ps != PS for _, _, vs, ps in after),
          f"{separate}: two-layer draws carry other shaders ({len(after)} draws)")
    check(len({(vs, ps) for _, _, vs, ps in after}) == 1, f"{separate}: one corrected pair")
    # The title's shaders, as the pinned SDK disassembles them: the vertex shader's instruction 15 writes
    # nothing, the pixel shader fetches both layers from r0.
    vs_before, ps_before = disassembly(original, VS, "vert"), disassembly(original, PS, "frag")
    check("max r0._, c0, c0" in vs_before and VS_LINE not in vs_before, f"{original}: vertex shader exports no second set")
    check("tfetch2D r6, r0.xy, tf1" in ps_before and PS_LINE not in ps_before, f"{original}: both layers fetched from r0")
    if after:
        vs_after = disassembly(separate, after[0][2], "vert")
        ps_after = disassembly(separate, after[0][3], "frag")
        check(VS_LINE in vs_after and "max r0._, c0, c0" not in vs_after, f"{separate}: vertex shader exports uv2 + c11")
        check(PS_LINE in ps_after and "tfetch2D r4, r0.xy, tf0" in ps_after, f"{separate}: second layer fetched from r3")
        strip = lambda text, line: [x for x in text.splitlines() if line not in x and "max r0._, c0, c0" not in x
                                    and "tfetch2D r6, r0.xy, tf1" not in x]
        check(strip(vs_after, VS_LINE) == strip(vs_before, VS_LINE), f"{separate}: no other vertex shader line differs")
        check(strip(ps_after, PS_LINE) == strip(ps_before, PS_LINE), f"{separate}: no other pixel shader line differs")


if "--run" in sys.argv:
    for run_name in sys.argv[sys.argv.index("--run") + 1:]:
        judge_run(run_name)
if "--pair" in sys.argv:
    at = sys.argv.index("--pair")
    judge_pair(sys.argv[at + 1], sys.argv[at + 2])

header = read(TOOLS / "m23_water_layers.h")
patch = read(TOOLS / "m23_runtime_patch.py")
cp = read(SDK / "src/graphics/d3d12/command_processor.cpp")
bat = read(TOOLS / "build_milestone8.bat")
play = read(TOOLS / "play.ps1")
hidden = read(TOOLS / "run_milestone6.ps1")

check(read(SDK / "include/rex/m23_water_layers.h") == header, "m23_water_layers.h: installed copy equals tools/")

# Off by default; one option under its current and its first name (D-054); one value.
check('Selected(Value(std::getenv("R3HD_LAYER_COORDS"), std::getenv("R3HD_WATER_LAYERS")))' in header
      and header.count("getenv") == 2, "header: the option's variable and its first name, nothing else")
check("inline const char* Value(const char* current, const char* legacy) { return current ? current : legacy; }" in header,
      "header: the first name counts only when the current variable is absent")
check('std::strcmp(value, "separate") == 0' in header, "header: only 'separate' selects the correction")
check(f"0x{VS:016X}ull" in header and f"0x{PS:016X}ull" in header, "header: the pair's hashes")
check("if (ucode.size() != plan.dword_count) return {};" in header and "!= plan.edits[i].expect) return {};" in header,
      "header: unexpected microcode is refused")

# One site in the command processor, gated, no guest write, no other state.
check(cp.count("m23water::Enabled()") == 2, "command processor: one draw site and one log line")
block = cp[cp.index("// M23 (D-052): optional two-layer surface correction"):cp.index("// M22: one-frame draw-state trace")]
check(block.lstrip().startswith("// M23") and "if (m23water::Enabled() && pixel_shader &&" in block, "site: flag tested first")
check("vertex_shader->ucode_data_hash() == m23water::kVertexShaderHash" in block
      and "pixel_shader->ucode_data_hash() == m23water::kPixelShaderHash" in block, "site: both hashes must match")
check("if (!m23_vs.empty() && !m23_ps.empty()) {" in block, "site: both edits must apply or neither shader is replaced")
for word in ("TranslatePhysical", "regs.values[", "WriteRegister", "store_and_swap", "memory_->", "return false",
             "return true", "texture_cache_->", "render_target_cache_->"):
    check(word not in block, f"site: no '{word}' (no guest access, no effect on any other draw)")
check(block.count("pipeline_cache_->LoadShader(") == 2 and block.count("AnalyzeShaderUcode") == 2,
      "site: the two edited shaders are loaded and analysed like any guest shader")
check('REXGPU_INFO("M23 layer_coords={}", m23water::Enabled() ? "separate" : "original");' in cp, "mode logged at start-up")
check("M23 water_layers" not in cp, "command processor: no log line under the first name")
check(cp.index("// M23 (D-052): optional two-layer") < cp.index("// M22: one-frame draw-state trace"),
      "site: before the M22 trace, so a trace records what was drawn")

# Launcher: a person's switch, default original, restored afterwards; hidden runner never sets it.
check("[Alias('WaterLayers')][ValidateSet('original', 'separate')][string]$LayerCoords = 'original'," in play,
      "play.ps1: -LayerCoords (first name -WaterLayers still accepted), default original")
check("$savedLayers = $env:R3HD_LAYER_COORDS" in play and "$env:R3HD_LAYER_COORDS = $LayerCoords" in play
      and "$env:R3HD_LAYER_COORDS = $savedLayers" in play, "play.ps1: sets the variable from the option and restores it")
check("$savedWater = $env:R3HD_WATER_LAYERS" in play and "$env:R3HD_WATER_LAYERS = $null" in play
      and "$env:R3HD_WATER_LAYERS = $savedWater" in play, "play.ps1: the first name's variable is cleared for the session and restored")
check(play.count("layer_coords = $LayerCoords") == 2 and "$WaterLayers" not in play, "play.ps1: the mode is recorded with the session")
check("R3HD_WATER_LAYERS" not in hidden and "R3HD_LAYER_COORDS" not in hidden, "hidden runner: never selects the correction by itself")

# Build chain.
check("python tools\\m23_runtime_patch.py" in bat and "python tools\\m23_prepare.py" in bat, "build replays the M23 patch")
check(bat.index("m22_runtime_patch.py") < bat.index("m23_runtime_patch.py") < bat.index("cmake --build external"), "patch order")
check(bat.index("m21_prepare.py") < bat.index("m23_prepare.py") < bat.index("rexglue.exe"), "prepare order")
check("m23_water_test.exe || exit /b 1" in bat and "m23_water_test " in bat, "build runs the microcode edit test")
check("python tools\\m23_regression.py" in bat, "build runs this regression")
check("patch_once" in patch and "from_head" not in patch, "patch is additive (patch_once)")

print(f"M23_REGRESSION {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures}")
sys.exit(1 if failures else 0)
