"""Deterministic checks of the rendering-resolution configuration (M15, D-042). Starts no game.

The host renderer draws the title's 1280x720 image N times larger along each axis when --resolution_scale=N is
set. The player launcher chooses N (-RenderScale auto|1|2|3); the executable and every hidden test default to 1,
so the retained regressions keep measuring the original-resolution path unless a run asks otherwise.
Needs: a built executable and no running r3hd (launcher preflight).
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
checks = failures = 0


def powershell(script: str, *argv: str):
    done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / script), *argv],
                          cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=120)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL: {label}")


def scale_of(out: str):
    found = re.findall(r"argument   : --resolution_scale=(\d+)", out)
    return int(found[0]) if len(found) == 1 else None


runner = (ROOT / "tools" / "run_milestone6.ps1").read_text(encoding="utf-8-sig")
play = (ROOT / "tools" / "play.ps1").read_text(encoding="utf-8-sig")
host = "".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted((ROOT / "tools" / "m2_host").glob("*"))
               if p.is_file())

# The scale is a renderer setting of the SDK at its default; nothing in the host or the hidden runner sets it.
cache = (SDK / "src/graphics/pipeline/texture/cache.cpp").read_text(errors="replace")
check(re.search(r'REXCVAR_DEFINE_INT32\(resolution_scale, 1, "GPU"', cache) is not None, "SDK: resolution_scale defaults to 1")
check("resolution_scale" not in host, "host: never sets the scale")
check("--resolution_scale" not in runner, "hidden runner: no scale unless a run passes one")
check("$env:R3HD_HIDDEN_EXTRA" in runner and "extra_arguments = $ExtraArgs" in runner,
      "hidden runner: inherited extra arguments are validated and recorded")
check("--fullscreen=false" in runner and re.search(r"\$extra -match '\^--\([^']*fullscreen[^']*\)='\) \{ throw", runner) is not None,
      "hidden runner: never fullscreen")

# Instrumentation lines of tools/m15_runtime_patch.py are in the sources the build compiles.
for rel, needle in (("src/ui/window_sdl.cpp", '"M15 window '), ("src/graphics/d3d12/command_processor.cpp", '"M15 draw_scale '),
                    ("src/graphics/d3d12/command_processor.cpp", '"M15 viewport '),
                    ("src/graphics/d3d12/render_target_cache.cpp", '"M15 rt_create '), ("src/ui/presenter.cpp", '"M15 present ')):
    check(needle in (SDK / rel).read_text(errors="replace"), f"SDK: {needle.strip()} line present in {rel}")

# Launcher.
check("[ValidateSet('auto', '1', '2', '3')][string]$RenderScale = 'auto'" in play, "launcher: -RenderScale auto|1|2|3, default auto")
check(play.count('"--resolution_scale=$scale"') == 1, "launcher: the scale is passed in exactly one place")
code, out = powershell("play.ps1", "-DryRun")
check(code == 0 and scale_of(out) == 1 and "--fullscreen=false" in out, "windowed default: 1280x720 window, scale 1")
code, out = powershell("play.ps1", "-DryRun", "-Fullscreen")
mode = re.search(r"shown in (\d+)x(\d+) \(primary display mode\)", out)
check(code == 0 and mode is not None and "--fullscreen=true" in out, "fullscreen: the display mode is read")
if mode:
    width, height = int(mode.group(1)), int(mode.group(2))
    want = min(3, max(1, -(-width // 1280), -(-height // 720)))
    check(scale_of(out) == want, f"fullscreen auto: {width}x{height} -> scale {want}")
    check(f"{1280 * want}x{720 * want} internal image" in out, "fullscreen auto: the internal image size is printed")
for value in ("1", "2", "3"):
    code, out = powershell("play.ps1", "-DryRun", "-Fullscreen", "-RenderScale", value)
    check(code == 0 and scale_of(out) == int(value), f"-RenderScale {value} is passed unchanged")
code, out = powershell("play.ps1", "-DryRun", "-Width", "2560", "-Height", "1440")
check(code == 0 and scale_of(out) == 2, "windowed 2560x1440: scale 2")
code, out = powershell("play.ps1", "-DryRun", "-Width", "1920", "-Height", "1080")
check(code == 0 and scale_of(out) == 2, "windowed 1920x1080: scale 2 (rendered above the window size, never below)")
for bad in ("4", "0", "native"):
    code, out = powershell("play.ps1", "-DryRun", "-RenderScale", bad)
    check(code != 0 and "DRY RUN" not in out, f"-RenderScale {bad} refused")
for extra in ("--resolution_scale=2", "--draw_resolution_scale_x=2", "--draw_resolution_scale_y=3"):
    code, out = powershell("play.ps1", "-DryRun", "-ExtraArgs", extra)
    check(code != 0 and "DRY RUN" not in out and "-RenderScale" in out, f"launcher refuses -ExtraArgs {extra}")

# The run checker: synthetic logs, one consistent and three broken chains.
import tempfile

good = """M15 window fullscreen_requested=true sdl_fullscreen=true exclusive_mode=false size=2560x1440 pixels=2560x1440 desktop_mode=2560x1440@60.00 pixel_density=1.00 display_scale=1.00
M3 host_swapchain_create size=2560x1440 format=B8G8R8A8_UNORM(87) buffers=3
M15 draw_scale x=2 y=2 as_requested=true
M15 rt_create kind=color guest_format=0 dxgi_format=28 msaa=0 guest=1280x2048 host=2560x4096 samples=1 scale=2x2
M15 rt_create kind=depth guest_format=0 dxgi_format=44 msaa=0 guest=1280x2048 host=2560x4096 samples=1 scale=2x2
M15 viewport draw=402 surface_info=14000500 guest_pitch=1280 msaa=0 host_viewport=0,0 2560x1440 host_scissor=0,0 2560x1440 scale=2x2
M3 swap count=1 frontbuffer=1F6F8000 packet=1280x720 source=2560x1440 dxgi_format=27 guest_format=6 output=2560x1440 display=1280x720
M15 present guest_output=2560x1440 aspect=2560:1440 swap_chain=2560x1440 surface=2560x1440 output_rect=0,0 2560x1440 ratio_x=1.000 ratio_y=1.000
"""
cases = (
    ("consistent 2x chain", good, ["--scale", "2"], 0),
    ("scale other than the one required", good, ["--scale", "1"], 1),
    ("depth target left at guest size", good.replace("kind=depth guest_format=0 dxgi_format=44 msaa=0 guest=1280x2048 host=2560x4096",
                                                    "kind=depth guest_format=0 dxgi_format=44 msaa=0 guest=1280x2048 host=1280x2048"), [], 1),
    ("upscaled 720p image in a 1440p swap chain", good.replace("source=2560x1440", "source=1280x720").replace("output=2560x1440", "output=1280x720"), [], 1),
    ("stretched presentation", good.replace("output_rect=0,0 2560x1440", "output_rect=0,0 2560x1200"), [], 1),
    ("main viewport not scaled", good.replace("host_viewport=0,0 2560x1440", "host_viewport=0,0 1280x720"), [], 1),
)
with tempfile.TemporaryDirectory() as temp:
    for index, (label, text, argv, want) in enumerate(cases):
        run = Path(temp) / f"case{index}"
        run.mkdir()
        (run / "runtime.log").write_text(text)
        done = subprocess.run([sys.executable, str(ROOT / "tools" / "m15_resolution_check.py"), str(run), *argv],
                              capture_output=True, text=True)
        check(done.returncode == want, f"run checker: {label} -> exit {want} (got {done.returncode})")

print(f"M15_RESOLUTION_REGRESSION {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures}")
sys.exit(1 if failures else 0)
