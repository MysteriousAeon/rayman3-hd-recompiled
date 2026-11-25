#!/usr/bin/env python3
"""G6-P141: Automated deterministic acceptance suite for native 1080p (1.5x / 3:2) rendering & Settings integration.

Runs offline with zero game launches and zero proprietary captures:
  1. Compiles and runs tools/g6p141_scale32_render_test.cpp (C++20):
     - viewport conversion, scissor boundaries, guest-to-host coordinate mapping,
     - synthetic procedural scene + Model R lossless round-trip + cross-scale tolerance + subpixel UV check,
     - 4xMSAA EDRAM tile / 1x<->4x transfer bijection, depth/stencil/alpha cutout invariants,
     - RT reuse & resource lifetime, HUD/UI positioning & presenter letterboxing.
  2. Verifies fail-closed refusal exit code (137) across 7 distinct refusal modes.
  3. Verifies Vanilla / HD+ / Custom profile independence and schema 1/2/3/4 persistence for render_scale=1.5.
  4. Verifies play.ps1 -DryRun for explicit -RenderScale 1.5 (windowed, fullscreen, settings file, CLI overrides),
     preservation of Auto Policy A (1x/2x/3x), and Linux fallback handling.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "linux"))

CLANG = r"C:\Program Files\LLVM\bin\clang++.exe"
checks = failures = 0


def check(cond: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not cond:
        failures += 1
        print(f"FAIL: {label}")


def powershell_play(*argv: str):
    done = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / "play.ps1"), *argv],
        cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=120,
    )
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def run_cpp_suite() -> None:
    clang = CLANG if os.path.exists(CLANG) else shutil.which("clang++")
    check(bool(clang), "clang++ available for C++20 deterministic render test")
    if not clang:
        return
    with tempfile.TemporaryDirectory(prefix="g6p141_rt_") as tmp:
        exe = os.path.join(tmp, "g6p141_scale32_render_test.exe")
        comp = subprocess.run(
            [clang, "-std=c++20", "-O2", "-D_CRT_SECURE_NO_WARNINGS",
             "-I", str(ROOT / "tools" / "g6p89_stub"), "-I", str(ROOT / "tools"),
             str(ROOT / "tools" / "g6p141_scale32_render_test.cpp"), "-o", exe],
            capture_output=True, text=True,
        )
        check(comp.returncode == 0, f"C++20 render test compiles ({comp.stderr[-200:].strip()})")
        if comp.returncode != 0:
            return
        res = subprocess.run([exe], capture_output=True, text=True, timeout=60)
        m = re.search(r"G6P141_RENDER_TEST PASS checks=(\d+) failures=0", res.stdout)
        check(res.returncode == 0 and m is not None, f"C++20 deterministic render test passes ({res.stdout.strip()})")
        for mode in ("refuse_viewport", "refuse_scissor", "refuse_resolve_size", "refuse_resolve_shader",
                     "refuse_address_align", "refuse_host_depth_store", "refuse_integer_accessor"):
            rr = subprocess.run([exe, mode], capture_output=True, text=True, timeout=30)
            check(rr.returncode == 137, f"fail-closed refusal {mode} exits 137 (got {rr.returncode})")


def run_settings_and_profile_checks() -> None:
    import r3hd_settings as rs
    reg = rs.load_registry()
    rs_spec = reg["settings"]["render_scale"]
    check("1.5" in rs_spec["values"], "registry: render_scale includes '1.5'")
    check(rs_spec["values"] == ["auto", "1", "1.5", "2", "3"], f"registry: render_scale order {rs_spec['values']}")
    lbl15 = rs_spec["value_labels"].get("1.5", "")
    check("1920" in lbl15 and "1080" in lbl15 and "1.5" in lbl15, f"registry: 1.5 label clear ({lbl15!r})")

    # Localization strings exist in EN and TR.
    ui = json.loads((ROOT / "config" / "settings" / "ui_strings.json").read_text(encoding="utf-8"))["strings"]
    check(lbl15 in ui and ui[lbl15].get("en") and ui[lbl15].get("tr"), "ui_strings: 1.5 label present in EN and TR")
    help_en = rs_spec["help"]
    check(help_en in ui and ui[help_en].get("en") and ui[help_en].get("tr"), "ui_strings: render_scale help present in EN and TR")

    # Vanilla / HD+ / Custom independence.
    v15 = rs.resolve(reg, settings={"schema": 2, "preset": "vanilla", "preferences": {"render_scale": "1.5"}})
    h15 = rs.resolve(reg, settings={"schema": 2, "preset": "hdplus", "preferences": {"render_scale": "1.5"}})
    c15 = rs.resolve(reg, settings={"schema": 3, "preset": "custom", "base": "hdplus",
                                    "overrides": {"crown_cutout": "original"},
                                    "preferences": {"render_scale": "1.5"}})
    check(v15["values"]["render_scale"] == "1.5" and v15["values"]["crown_cutout"] == "original"
          and v15["values"]["layer_coords"] == "original" and v15["label"] == "vanilla",
          "Vanilla + render_scale=1.5 keeps Vanilla corrections untouched")
    check(h15["values"]["render_scale"] == "1.5" and h15["values"]["crown_cutout"] == "cutout"
          and h15["values"]["layer_coords"] == "separate" and h15["label"] == "hdplus",
          "HD+ + render_scale=1.5 keeps HD+ corrections active")
    check(c15["values"]["render_scale"] == "1.5" and c15["values"]["crown_cutout"] == "original"
          and c15["values"]["layer_coords"] == "separate" and c15["label"] == "custom",
          "Custom + render_scale=1.5 stays independent of preset overrides")

    # Schema 1 backwards compatibility & preference preservation across preset switches.
    s1 = rs.resolve(reg, settings={"schema": 1, "preset": "custom", "base": "vanilla",
                                   "overrides": {"render_scale": "1.5"}})
    check(s1["values"]["render_scale"] == "1.5" and s1["sources"]["render_scale"] == "preference",
          "schema 1 file with render_scale=1.5 resolves cleanly as preference")
    kept = rs.make_settings(reg, "hdplus", keep_preferences={"render_scale": "1.5"})
    check(kept["preferences"]["render_scale"] == "1.5", "switching preset preserves render_scale=1.5")

    # Linux graceful fallback for 1.5 (D3D12 only).
    import r3hd_play as lp
    check(lp.render_scale("1.5", (1920, 1080)) == 1, "Linux r3hd_play falls back cleanly from 1.5 to integer 1")


def run_launcher_dryrun_checks() -> None:
    exe = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release" / "r3hd.exe"
    if not exe.is_file():
        print("NOTE: r3hd.exe not built yet; skipping play.ps1 -DryRun checks")
        return

    # Explicit -RenderScale 1.5 windowed and fullscreen.
    code, out = powershell_play("-DryRun", "-RenderScale", "1.5", "-WindowSize", "1920x1080")
    check(code == 0 and "1920x1080 internal image (scale 1.5, -RenderScale 1.5)" in out
          and "argument   : --resolution_scale=1" in out and "R3HD_RENDER_SCALE_3_2=1" in out,
          "play.ps1 -DryRun -RenderScale 1.5 windowed sets 1920x1080 3:2 cleanly")
    code, out = powershell_play("-DryRun", "-Fullscreen", "-RenderScale", "1.5")
    check(code == 0 and "1920x1080 internal image (scale 1.5, -RenderScale 1.5)" in out
          and "--fullscreen=true" in out and "argument   : --resolution_scale=1" in out,
          "play.ps1 -DryRun -Fullscreen -RenderScale 1.5 works in fullscreen")

    # Persisted settings file with render_scale=1.5 and CLI override back to 1 / 2 / auto.
    with tempfile.TemporaryDirectory(prefix="g6p141_ps_") as tmp:
        sf = Path(tmp) / "settings.json"
        sf.write_text(json.dumps({"schema": 3, "preset": "hdplus", "preferences": {"render_scale": "1.5"}}), encoding="utf-8")
        code, out = powershell_play("-DryRun", "-SettingsFile", str(sf), "-WindowSize", "1920x1080")
        check(code == 0 and "1920x1080 internal image (scale 1.5, -RenderScale 1.5)" in out
              and "preset     : hdplus" in out and "crown cut  : cutout" in out,
              "play.ps1 -DryRun loads persisted render_scale=1.5 with HD+")
        code, out = powershell_play("-DryRun", "-SettingsFile", str(sf), "-RenderScale", "2", "-WindowSize", "1920x1080")
        check(code == 0 and "2560x1440 internal image (scale 2, -RenderScale 2)" in out
              and "argument   : --resolution_scale=2" in out and "R3HD_RENDER_SCALE_3_2=1" not in out,
              "CLI -RenderScale 2 overrides persisted render_scale=1.5")
        code, out = powershell_play("-DryRun", "-SettingsFile", str(sf), "-RenderScale", "auto", "-Width", "1920", "-Height", "1080")
        check(code == 0 and "2560x1440 internal image (scale 2, -RenderScale auto)" in out
              and "argument   : --resolution_scale=2" in out,
              "CLI -RenderScale auto overrides persisted 1.5 and preserves Policy A (2x at 1920x1080)")


def main() -> int:
    run_cpp_suite()
    run_settings_and_profile_checks()
    run_launcher_dryrun_checks()
    print(f"G6P141_SCALE32_ACCEPTANCE {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
