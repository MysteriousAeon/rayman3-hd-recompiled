#!/usr/bin/env python3
"""HD+ lighting L1 tooling regression (no game run): the red-correction bypass (`-RedCorrection bypass`,
`red_correction` in the registry; D-150) is the HD+ value and never Vanilla's (D-151), changes one constant of one
draw in the host's upload only, and its hidden split diagnostic restores every state it changes.

    python tools/hdl_regression.py              -> HDL_REGRESSION PASS checks=N failures=0
    python tools/hdl_regression.py --run RUN... also judge hidden run directories (private/work/m6_runs/RUN):
                                                a run named *_bypass must have bypassed the pass (when it drew it),
                                                a run named *split* must pass tools/hdl_redcorrection_ab.py,
                                                any other run must have left the pass as the title issues it
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
TOOLS = ROOT / "tools"
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
    mode = re.findall(r"HDL red_correction=(\w+)", log)
    passes = re.findall(r"HDL red_correction pass=(\w+)", log)
    check("refused" not in passes, f"{name}: the pass's constant layout was never refused")
    if "split" in name:
        check(mode == ["split"], f"{name}: split diagnostic selected (got {mode})")
        result = subprocess.run([sys.executable, str(TOOLS / "hdl_redcorrection_ab.py"), str(RUNS / name)],
                                capture_output=True, text=True)
        check(result.returncode == 0 and "HDL_SPLIT PASS" in result.stdout, f"{name}: same-frame A/B judged clean")
    elif name.endswith("_bypass"):
        check(mode == ["bypass"], f"{name}: bypass selected (got {mode})")
        check(set(passes) <= {"bypassed"}, f"{name}: every logged pass bypassed (got {passes})")
    else:
        check(mode == ["original"], f"{name}: the title's pass (got {mode})")
        check(set(passes) <= {"original"}, f"{name}: no pass bypassed (got {passes})")


if "--run" in sys.argv:
    for run_name in sys.argv[sys.argv.index("--run") + 1:]:
        judge_run(run_name)

header = read(TOOLS / "hdl_red_correction.h")
cp = read(SDK / "src/graphics/d3d12/command_processor.cpp")
bat = read(TOOLS / "build_milestone8.bat")
play = read(TOOLS / "play.ps1")

check(read(SDK / "include/rex/hdl_red_correction.h") == header, "hdl_red_correction.h: installed copy equals tools/")

# Off by default; exactly one value selects it; the diagnostic needs the hidden-run frame request.
check(header.count("std::getenv(") == 4,
      "header: R3HD_RED_CORRECTION, R3HD_RED_CORRECTION_AB, R3HD_FRAME_REQUEST, R3HD_NONINTRUSIVE only")
check('std::getenv("R3HD_RED_CORRECTION");' in header and '!std::strcmp(v, "bypass")' in header,
      "header: only 'bypass' selects the bypass")
check('!std::strcmp(v, "split") && request && *request && std::getenv("R3HD_NONINTRUSIVE")' in header,
      "header: split needs a hidden run (frame request and non-intrusive mode)")
check("inline bool Wanted() { return Selected() && !Split(); }" in header, "header: split draws the title's pass first")
check("0xDB19DF80422CD907ull" in header and "kBypassThreshold = 2.0f" in header,
      "header: the pass's hash and a threshold above any red share")
check("return float_count >= 1 && (bitmap[0] & 1) != 0;" in header, "header: c0 must be read (first packed constant)")

# The bypass: one gated block before the constant upload; one constant of one upload changes; never reused.
start = cp.index("  // HD+ lighting L1 (D-150): optional red-correction bypass")
select = cp[start:cp.index("  // Write the constant buffer data.\n", start)]
check(cp.count("  // HD+ lighting L1 (D-150): optional red-correction bypass") == 1, "command processor: one select block")
check("pixel_shader->ucode_data_hash() == hdlred::kPixelShaderHash" in select, "select: the pass's hash is required")
check("hdl_red_bypass = hdl_wanted && hdl_layout;" in select, "select: wanted and layout both required")
check(cp.count("std::memcpy(hdl_pixel_c0, &hdlred::kBypassThreshold, sizeof(float));") == 1
      and "    if (hdl_red_bypass) {\n      // The buffer starts with c0" in cp,
      "upload: only c0.x of the host copy is replaced, only for the bypassed draw")
check(cp.count("cbuffer_binding_float_pixel_.up_to_date = !hdl_red_bypass;") == 1,
      "upload: a bypassed upload is not reused by the next draw")
check(cp.count("hdl_red_bypass") == 5, "command processor: hdl_red_bypass used only by the select block and the upload")

# The split diagnostic: gated by Split(); a second draw; viewport, scissor and the constant binding restored.
start = cp.index("  // HD+ lighting L1 (D-150), hidden diagnostic only")
split = cp[start:cp.index("  // Draw.\n", start)]
check(cp.count("  // HD+ lighting L1 (D-150), hidden diagnostic only") == 1, "command processor: one split block")
check("const bool hdl_split = hdlred::Split() &&" in split, "split: gated by the hidden diagnostic")
check(cp.count("if (hdl_split && hdl_split_begin()) {") == 2 and cp.count("      hdl_split_end();\n") == 2,
      "split: each draw path issues the copy and restores state")
check("SetViewport(hdl_saved_viewport);" in split and "SetScissorRect(hdl_saved_scissor);" in split
      and "cbuffer_binding_float_pixel_.address);" in split, "split: viewport, scissor and pixel constants restored")
for block, label in ((select, "select"), (split, "split")):
    for word in ("WriteRegister", "regs.values[", "memory_->", "store_and_swap", "TranslatePhysical",
                 "texture_cache_->", "render_target_cache_->", "shared_memory_->"):
        check(word not in block, f"{label}: no '{word}' (no guest write, no other resource)")

# Build chain, launcher script, registry, resolver.
check("python tools\\m23_runtime_patch.py || exit /b 1\r\npython tools\\hdl_runtime_patch.py || exit /b 1" in bat
      or "python tools\\m23_runtime_patch.py || exit /b 1\npython tools\\hdl_runtime_patch.py || exit /b 1" in bat,
      "build: hdl_runtime_patch.py replays right after M23")
check("[ValidateSet('original', 'bypass')][string]$RedCorrection = 'original'," in play,
      "play.ps1: the parameter default is the vanilla column")
check("$env:R3HD_RED_CORRECTION = $RedCorrection" in play and "$env:R3HD_RED_CORRECTION = $savedRedCorrection" in play,
      "play.ps1: passed to the runtime and restored afterwards")
check("RedCorrection = 'red_correction'" in play, "play.ps1: resolved like every other preset setting")
reg = json.loads(read(ROOT / "config" / "settings" / "registry.json"))["settings"]["red_correction"]
# D-151: gate G-HDP-L1 passed (E-348); HD+ selects the bypass, Vanilla keeps the title's pass.
check(reg["vanilla"] == "original" and reg["hdplus"] == "bypass" and "hdplus_candidate" not in reg
      and "provisional" not in reg and str(reg.get("validation", "")).startswith("passed"),
      "registry: Vanilla original, HD+ bypass, validation passed (not a candidate, not provisional)")
check(reg["category"] == "hd_correction" and reg["values"] == ["original", "bypass"] and reg.get("ui", "shown") == "shown"
      and reg.get("group") == "corrections" and reg.get("scope", "preset") == "preset",
      "registry: a preset HD correction shown under Corrections (chosen per setting only in Custom)")
sys.path.insert(0, str(TOOLS))
import r3hd_settings as S
registry = S.load_registry()
resolve = S.resolve_presets
vanilla, hdplus = resolve(registry, "vanilla"), resolve(registry, "hdplus")
check(vanilla["values"]["red_correction"] == "original" and vanilla["sources"]["red_correction"] == "vanilla",
      "resolver: Vanilla keeps the title's pass")
check(hdplus["values"]["red_correction"] == "bypass" and hdplus["sources"]["red_correction"] == "hdplus"
      and not any("red_correction" in w for w in hdplus["warnings"]), "resolver: HD+ bypasses it, without a warning")
check(resolve(registry)["values"]["red_correction"] == "original", "resolver: no preset = Vanilla = original")
for base, want in (("vanilla", "original"), ("hdplus", "bypass")):
    old = {"schema": 3, "preset": "custom", "base": base, "overrides": {"layer_coords": "separate"}}
    check(resolve(registry, settings=old)["values"]["red_correction"] == want,
          f"resolver: a Custom file on {base} that never named it follows its base ({want})")
    for value in ("original", "bypass"):
        f = {"schema": 3, "preset": "custom", "base": base, "overrides": {"red_correction": value}}
        r = resolve(registry, settings=f)
        check(r["values"]["red_correction"] == value and r["preset"] == "custom" and r["sources"]["red_correction"] == "custom",
              f"resolver: a stored Custom choice {value} on {base} is kept")
for preset in ("vanilla", "hdplus"):
    check(resolve(registry, settings={"schema": 3, "preset": preset})["values"]["red_correction"] == reg[preset],
          f"resolver: a fixed {preset} settings file resolves {reg[preset]}")
# D-150 addendum settled by D-151: an explicit override on Vanilla is a labelled choice, never Vanilla's own value.
e = resolve(registry, "vanilla", explicit={"red_correction": "bypass"})
check(e["values"]["red_correction"] == "bypass" and e["label"] == "vanilla+explicit" and e["sources"]["red_correction"] == "explicit",
      "resolver: -RedCorrection bypass on Vanilla is labelled vanilla+explicit")
e = resolve(registry, "hdplus", explicit={"red_correction": "original"})
check(e["values"]["red_correction"] == "original" and e["label"] == "hdplus+explicit",
      "resolver: -RedCorrection original on HD+ restores the title's pass, labelled hdplus+explicit")
check(resolve(registry, "hdplus", explicit={"red_correction": "bypass"})["label"] == "hdplus",
      "resolver: an explicit bypass on HD+ equals the preset")
written = S.make_settings(registry, "custom", "hdplus", ["RedCorrection=original"])
check(written["overrides"] == {"red_correction": "original"}
      and resolve(registry, settings=written)["values"]["red_correction"] == "original",
      "write: Custom stores the choice under its launcher name too")

print(f"HDL_REGRESSION {'PASS' if failures == 0 else 'FAIL'} checks={checks} failures={failures}")
sys.exit(1 if failures else 0)
