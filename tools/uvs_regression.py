#!/usr/bin/env python3
"""Lit UV scroll regression (no game run; E-353, D-158, D-159): the `1t_d_lighting` edit adds c10 to the exported
coordinates and nothing else, is off unless R3HD_LIT_UV_SCROLL=applied, and is a preset correction: Vanilla original
(the title's shader as issued), HD+ applied, Custom either (D-156 conventions for stored choices and upgrades).

    python tools/uvs_regression.py              -> UVS_REGRESSION PASS checks=N failures=0
    python tools/uvs_regression.py --run RUN... also judge hidden run directories (private/work/m6_runs/RUN): a run
                                                named *_uvs must have drawn the edited shader, any other run must
                                                have left it as the title issues it
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
RUNS = ROOT / "private" / "work" / "m6_runs"
checks = failures = 0


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL {label}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def judge_run(name: str) -> None:
    log = "\n".join(read(p) for p in sorted((RUNS / name).glob("runtime*.log")))
    mode = re.findall(r"UVS lit_uv_scroll=(\w+)", log)
    shader = re.findall(r"UVS lit_uv_scroll shader=(\w+) vs=([0-9A-F]{16}) edited=([0-9A-F]{16})", log)
    check(bool(log), f"{name}: run log present")
    if name.endswith("_uvs"):
        check(mode == ["applied"], f"{name}: the run selected the lit UV scroll")
        check(len(shader) == 1 and shader[0][0] == "applied" and shader[0][1] == "D64D176416571592"
              and shader[0][2] != shader[0][1], f"{name}: the title's shader was replaced by the edited copy")
    else:
        check(mode == ["original"], f"{name}: the run kept the title's shader")
        check(not shader, f"{name}: no shader was edited")


header = read(ROOT / "tools/uvs_lit_scroll.h")
check("constexpr uint64_t kVertexShaderHash = 0xD64D176416571592ull;" in header, "edit keyed to the bound 1t_d_lighting")
edits = [tuple(int(x, 0) for x in m) for m in
         re.findall(r"\{(\d+), (0x[0-9A-F]+)u, (0x[0-9A-F]+)u\}", header.split("kVertexEdits[] = {", 1)[1].split("};", 1)[0])]
check([e[0] for e in edits] == [75, 76, 77], "the plan covers instruction 25 (dwords 75 .. 77) only")
check("constexpr Plan kVertexPlan = {120, kVertexEdits" in header, "the plan accepts only 120-dword microcode")
check([e for e in edits if e[1] != e[2]] == [(77, 0xE2030300, 0xA0030A00)], "only dword 77 changes")
if len(edits) == 3:
    d0, d1 = edits[0][2], edits[1][2]
    old, new = edits[2][1], edits[2][2]
    # Field layout of the pinned SDK's ucode.h ALU instruction (as checked for the M23 edit in m23_water_test).
    check((d0 & 0x3F) == 0 and (d0 >> 15) & 1 == 1, "vector destination is export 0 (coordinates and fog factor)")
    check((d0 >> 16) & 0xF == 0x7 and (d0 >> 20) & 0xF == 0, "write mask xyz, no scalar write")
    check((d1 >> 16) & 0xFF == 0xC0 and (d1 >> 8) & 0xFF == 0xC0 and d1 >> 24 == 0,
          "both operands swizzled xyzz, nothing negated")
    check((old >> 24) & 0x1F == 2 and (new >> 24) & 0x1F == 0, "operation max becomes add")
    check((old >> 16) & 0xFF == 3 and (old >> 31) & 1 and (new >> 16) & 0xFF == 3 and (new >> 31) & 1,
          "first operand stays temporary register r3")
    check((old >> 8) & 0xFF == 3 and (old >> 30) & 1 == 1, "title's second operand is register r3")
    check((new >> 8) & 0xFF == 10 and (new >> 30) & 1 == 0, "corrected second operand is constant c10")
    check(new & 0xFF == old & 0xFF, "remaining operand fields unchanged")
    m23 = read(ROOT / "tools/m23_water_layers.h")
    check("0xA0030B00u" in m23 and (new ^ 0xA0030B00) == 0x00000100,
          "same encoding as the M23 `add ..., c11` apart from the constant index")
check('std::strcmp(value, "applied") == 0' in header and 'std::getenv("R3HD_LIT_UV_SCROLL")' in header,
      "selected only by R3HD_LIT_UV_SCROLL=applied")
check("Corrected(" in header and "return {};" in header, "unexpected microcode is drawn as issued")

patch = read(ROOT / "tools/uvs_runtime_patch.py")
check("uvslit::Enabled() && vertex_shader->ucode_data_hash() == uvslit::kVertexShaderHash" in patch,
      "the substitution runs only when selected and only for that shader")
check("pipeline_cache_->AnalyzeShaderUcode(*vertex_shader);" in patch, "the edited copy is analysed (constant usage)")
check("pixel_shader =" not in patch and "regs[" not in patch and "memory" not in patch.split("SUBSTITUTE", 1)[1],
      "no pixel shader, register or memory change")
bat = read(ROOT / "tools/build_milestone8.bat")
order = [bat.find(f"python tools\\{n}") for n in ("m23_runtime_patch.py", "hdl_runtime_patch.py", "uvs_runtime_patch.py")]
check(-1 not in order and order == sorted(order), "build chain: uvs patch replays after M23 and hdl")
check("python tools\\uvs_regression.py" in bat, "build chain runs this regression")

cp = SDK / "src/graphics/d3d12/command_processor.cpp"
# The SDK checks need the replayed chain (build_milestone8.bat runs this after the patch steps); before a replay
# they are reported as skipped, never counted as passed.
if not (cp.exists() and "uvslit" in read(cp)):
    print("note: SDK not patched with uvs_runtime_patch.py; SDK checks skipped")
else:
    text = read(cp)
    check(text.count("uvslit::Enabled() && vertex_shader") == 1, "SDK: one substitution site")
    a, b, c = (text.find("uvslit::Enabled() && vertex_shader"), text.find("m23water::Enabled() && pixel_shader"),
               text.find("// M22: one-frame draw-state trace"))
    check(-1 < a < b < c, "SDK: substitution before the M23 block and before the M22 trace")
    check(text.count('REXGPU_INFO("UVS lit_uv_scroll={}"') == 1, "SDK: every log states the mode once")

play = read(ROOT / "tools/play.ps1")
check("[ValidateSet('original', 'applied')][string]$LitUvScroll = 'original'," in play
      and "$env:R3HD_LIT_UV_SCROLL = $LitUvScroll" in play and "$env:R3HD_LIT_UV_SCROLL = $savedLitUvScroll" in play,
      "launcher: -LitUvScroll original is the default, applied is explicit, the variable is restored")
setting_map = play[play.find("$settingParams = [ordered]@{"):play.find("$resolverArgs = @(")]
check(len(setting_map) > 100 and "LitUvScroll = 'lit_uv_scroll'" in setting_map,
      "launcher: resolved like every other preset setting (D-159)")
sys.path.insert(0, str(ROOT / "tools"))
import r3hd_settings as S  # noqa: E402
registry = S.load_registry()
reg = registry["settings"].get("lit_uv_scroll", {})
check(reg.get("vanilla") == "original" and reg.get("hdplus") == "applied" and reg.get("category") == "hd_correction"
      and reg.get("values") == ["original", "applied"] and reg.get("group") == "corrections"
      and reg.get("ui", "shown") == "shown" and reg.get("scope", "preset") == "preset" and reg.get("launcher") == "LitUvScroll"
      and "provisional" not in reg and str(reg.get("validation", "")).startswith("passed"),
      "registry lit_uv_scroll: Vanilla original, HD+ applied, a preset HD correction shown under Corrections, passed")
resolve = S.resolve_presets
check(resolve(registry)["values"]["lit_uv_scroll"] == "original"
      and resolve(registry, "vanilla")["values"]["lit_uv_scroll"] == "original"
      and resolve(registry, settings={"schema": 3, "preset": "vanilla"})["values"]["lit_uv_scroll"] == "original",
      "resolver: no preset, Vanilla and a fixed Vanilla file keep the title's shader")
h = resolve(registry, "hdplus")
check(h["values"]["lit_uv_scroll"] == "applied" and h["sources"]["lit_uv_scroll"] == "hdplus"
      and not any("lit_uv_scroll" in w for w in h["warnings"]), "resolver: HD+ selects applied, without a warning")
for base, want in (("vanilla", "original"), ("hdplus", "applied")):
    old = {"schema": 3, "preset": "custom", "base": base, "overrides": {"sky_clear": "original"}}
    check(resolve(registry, settings=old)["values"]["lit_uv_scroll"] == want,
          f"resolver: a Custom file on {base} that never named lit_uv_scroll follows its base ({want})")
    for value in ("original", "applied"):
        r = resolve(registry, settings={"schema": 3, "preset": "custom", "base": base, "overrides": {"lit_uv_scroll": value}})
        check(r["values"]["lit_uv_scroll"] == value and r["sources"]["lit_uv_scroll"] == "custom",
              f"resolver: a stored Custom lit_uv_scroll {value} on {base} is kept")
e = resolve(registry, "vanilla", explicit={"lit_uv_scroll": "applied"})
check(e["values"]["lit_uv_scroll"] == "applied" and e["label"] == "vanilla+explicit",
      "resolver: -LitUvScroll applied on Vanilla is labelled vanilla+explicit")
written = S.make_settings(registry, "custom", "hdplus", ["LitUvScroll=original"])
check(written["overrides"] == {"lit_uv_scroll": "original"}
      and resolve(registry, settings=written)["values"]["lit_uv_scroll"] == "original",
      "write: Custom stores the choice under its launcher name too")

args = sys.argv[1:]
if args[:1] == ["--run"]:
    for run in args[1:]:
        judge_run(run)
print(f"UVS_REGRESSION {'PASS' if failures == 0 else 'FAIL'} checks={checks} failures={failures}")
sys.exit(1 if failures else 0)
