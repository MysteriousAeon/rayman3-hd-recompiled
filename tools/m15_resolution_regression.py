"""Deterministic checks of the rendering-resolution configuration (M15, D-042). Starts no game.

The host renderer draws the title's 1280x720 image N times larger along each axis when --resolution_scale=N is
set. The player launcher chooses N (-RenderScale auto|1|2|3); the executable and every hidden test default to 1,
so the retained regressions keep measuring the original-resolution path unless a run asks otherwise.
Auto (D-333 Policy A, D-334): the smallest N covering the 16:9 picture the presenter shows inside the target
(Get-AutoRenderScale), checked against an exact fitted-rectangle model and a port of the presenter's integer
output rectangle; 16:9 targets keep the earlier whole-target result.
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
check("[ValidateSet('auto', '1', '1.5', '2', '3')][string]$RenderScale = 'auto'" in play, "launcher: -RenderScale auto|1|1.5|2|3, default auto")
check(play.count('"--resolution_scale=$scale"') == 1, "launcher: the scale is passed in exactly one place")


# D-333 Policy A (G6-P85): Auto covers the 16:9 picture the presenter shows (the largest 16:9 rectangle inside the
# target), not the whole target. Reference model in exact integers, independent of play.ps1's formulation.
def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def policy_a(width: int, height: int) -> int:
    if width <= 0 or height <= 0:
        return 1
    # Fitted 16:9 picture as an exact fraction: pw = min(W, 16H/9), ph = min(H, 9W/16). 1280N x 720N covers it when
    # 1280N >= pw and 720N >= ph; with denominators cleared: 9*1280N >= min(9W, 16H) and 16*720N >= min(16H, 9W).
    pw9, ph16 = min(9 * width, 16 * height), min(16 * height, 9 * width)
    n = 1
    while not (9 * 1280 * n >= pw9 and 16 * 720 * n >= ph16):
        n += 1
    return min(3, n)


def legacy_auto(width: int, height: int) -> int:
    """The G6-P84 rule (whole target), kept to prove the regression distinguishes the two."""
    return min(3, max(1, ceil_div(width, 1280), ceil_div(height, 720)))


def play_function(name: str) -> str:
    m = re.search(r"^function " + name + r"\b.*?(?=^function |\Z)", play, re.M | re.S)
    return m.group(0) if m else ""


helper = play_function("Get-AutoRenderScale")
check(bool(helper), "launcher: Get-AutoRenderScale helper exists")
check(play.count("Get-AutoRenderScale $target.width $target.height") == 1
      and "if ($RenderScale -eq 'auto') { $scale = Get-AutoRenderScale $target.width $target.height } elseif ($RenderScale -eq '1.5') { $scale = 1; $scale32 = $true } else { $scale = [int]$RenderScale }" in play,
      "launcher: Auto is computed once, by the helper, on the one target (fullscreen display mode or window); explicit 1|1.5|2|3 pass through")
check("[Math]::Ceiling($target.width / 1280.0)" not in play, "launcher: the whole-target Auto formula is gone")
check(re.search(r"(?i)nvidia|amd|intel|adapter|vendor|gpu", helper.split("{", 1)[1]) is None,
      "launcher: Auto depends on the target size only (no GPU / adapter input)")

# (target, expected Auto scale). The 16:9 rows are the earlier contract (D-146) and must not move.
AUTO_TABLE = [
    ((1280, 720), 1), ((1920, 1080), 2), ((2560, 1440), 2), ((3840, 2160), 3), ((1366, 768), 2),
    ((2560, 1600), 2), ((2256, 1504), 2), ((3440, 1440), 2), ((5120, 1440), 2), ((1920, 1200), 2), ((1280, 800), 1),
    ((1280, 1024), 1), ((2560, 1080), 2), ((2880, 1800), 3), ((3840, 1600), 3), ((3840, 2400), 3),
    # Boundaries: exactly a scale's image, one pixel more on one axis (stays: the picture still fits that image),
    # one pixel more on both axes (next scale), and the same on narrow (tall) and wide shapes.
    ((2560, 1441), 2), ((2561, 1440), 2), ((2561, 1441), 3), ((1281, 721), 2), ((1281, 720), 1), ((1280, 721), 1),
    ((2560, 9999), 2), ((2561, 9999), 3), ((9999, 1440), 2), ((9999, 1441), 3), ((1281, 4000), 2),
    # Extreme but valid shapes, and sizes beyond 3840x2160 (the scale-3 cap).
    ((1, 10000), 1), ((10000, 1), 1), ((640, 360), 1), ((7680, 4320), 3), ((100000, 100000), 3), ((3841, 2161), 3),
]
INVALID = [("0", "720", 1), ("1280", "0", 1), ("0", "0", 1), ("-1920", "1080", 1), ("$null", "$null", 1),
           ("$null", "1080", 1), ("'abc'", "720", 1)]
lines = [f"Get-AutoRenderScale {w} {h}" for (w, h), _ in AUTO_TABLE] + [f"Get-AutoRenderScale {w} {h}" for w, h, _ in INVALID]
done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", helper + "\n" + "\n".join(lines)],
                      cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=120)
got = (done.stdout or "").split()
check(done.returncode == 0 and len(got) == len(lines), f"Auto helper ran on {len(lines)} targets")
for i, ((w, h), want) in enumerate(AUTO_TABLE):
    check(policy_a(w, h) == want, f"reference model: {w}x{h} -> {want}")
    check(i < len(got) and got[i] == str(want), f"Auto {w}x{h} -> scale {want} (got {got[i] if i < len(got) else None})")
    if w * 9 == h * 16:
        check(legacy_auto(w, h) == want, f"16:9 {w}x{h}: unchanged from the earlier rule")
for j, (w, h, want) in enumerate(INVALID, len(AUTO_TABLE)):
    check(j < len(got) and got[j] == str(want), f"Auto with an unusable size {w} x {h} -> scale {want}")
changed = [(w, h) for (w, h), want in AUTO_TABLE if legacy_auto(w, h) != want]
check({(2560, 1600), (2256, 1504), (3440, 1440), (5120, 1440), (1280, 800)} <= set(changed),
      f"the earlier whole-target rule fails this table on the non-16:9 rows (differs on {changed})")
for w in range(1, 4000, 7):
    for h in (360, 719, 720, 721, 1080, 1439, 1440, 1441, 2159, 2160, 2161, 3000):
        if policy_a(w, h) != min(3, max(1, min(ceil_div(w, 1280), ceil_div(h, 720)))):
            check(False, f"min(ceil) closed form disagrees with the fitted-rectangle model at {w}x{h}")


def presenter_rect(sw: int, sh: int, ax: int = 16, ay: int = 9) -> tuple:
    """src/ui/presenter.cpp output rectangle with present_letterbox on and no overscan cutoff (safe area 100):
    rescale_unsigned rounds half up."""
    def rescale(v, new, old):
        return (v * new + (old >> 1)) // old
    if sw * ay > sh * ax:
        oh = rescale(sw, ay, ax)
        if oh * 100 > sh * 100:
            return rescale(sh * 100, ax, ay * 100), sh
        return sw, oh
    ow = rescale(sh, ax, ay)
    if ow * 100 > sw * 100:
        return sw, rescale(sw * 100, ay, ax * 100)
    return ow, sh


check(presenter_rect(2560, 1600) == (2560, 1440) and presenter_rect(2256, 1504) == (2256, 1269)
      and presenter_rect(5120, 1440) == (2560, 1440) and presenter_rect(1280, 800) == (1280, 720), "presenter model: G6-P84 rectangles")
bad = []
for w in range(320, 6200, 13):
    for h in range(180, 3600, 11):
        n = policy_a(w, h)
        ow, oh = presenter_rect(w, h)
        covers = 1280 * n >= ow and 720 * n >= oh
        smaller_covers = n > 1 and 1280 * (n - 1) >= ow and 720 * (n - 1) >= oh
        if (n < 3 and not covers) or smaller_covers or n > legacy_auto(w, h):
            bad.append((w, h, n, ow, oh))
check(not bad, f"Auto is the smallest scale covering the presenter's integer output rectangle, never above the earlier rule "
               f"(below the scale-3 cap; first failures {bad[:3]})")
code, out = powershell("play.ps1", "-DryRun")
check(code == 0 and scale_of(out) == 1 and "--fullscreen=false" in out, "windowed default: 1280x720 window, scale 1")
code, out = powershell("play.ps1", "-DryRun", "-Fullscreen")
mode = re.search(r"shown in (\d+)x(\d+) \(primary display mode\)", out)
check(code == 0 and mode is not None and "--fullscreen=true" in out, "fullscreen: the display mode is read")
if mode:
    width, height = int(mode.group(1)), int(mode.group(2))
    want = policy_a(width, height)
    check(scale_of(out) == want, f"fullscreen auto: {width}x{height} -> scale {want}")
    check(f"{1280 * want}x{720 * want} internal image" in out, "fullscreen auto: the internal image size is printed")
for value in ("1", "2", "3"):
    code, out = powershell("play.ps1", "-DryRun", "-Fullscreen", "-RenderScale", value)
    check(code == 0 and scale_of(out) == int(value), f"-RenderScale {value} is passed unchanged")
code, out = powershell("play.ps1", "-DryRun", "-Width", "2560", "-Height", "1440")
check(code == 0 and scale_of(out) == 2, "windowed 2560x1440: scale 2")
code, out = powershell("play.ps1", "-DryRun", "-Width", "1920", "-Height", "1080")
check(code == 0 and scale_of(out) == 2, "windowed 1920x1080: scale 2 (rendered above the window size, never below)")
# D-333 Policy A through the real launcher (-DryRun, windowed with an explicit size): non-16:9 windows.
for (w, h), want in (((2560, 1600), 2), ((1280, 800), 1), ((3440, 1440), 2), ((2561, 1441), 3)):
    code, out = powershell("play.ps1", "-DryRun", "-Width", str(w), "-Height", str(h))
    check(code == 0 and scale_of(out) == want and f"{1280 * want}x{720 * want} internal image" in out
          and f"shown in {w}x{h} (window" in out, f"dry run windowed {w}x{h}: Auto -> scale {want}")
for value in ("1", "2", "3"):
    code, out = powershell("play.ps1", "-DryRun", "-Width", "2560", "-Height", "1600", "-RenderScale", value)
    check(code == 0 and scale_of(out) == int(value), f"windowed 2560x1600 -RenderScale {value}: passed unchanged")
if mode:
    # Fullscreen and Window mode use the same rule on the same pixel rectangle.
    code, out = powershell("play.ps1", "-DryRun", "-Width", str(width), "-Height", str(height))
    check(code == 0 and scale_of(out) == policy_a(width, height), f"windowed {width}x{height} = fullscreen on that display")
# A stored preference: auto follows Policy A, an explicit stored scale is kept, a named parameter wins over both.
import json
import tempfile as _tf
with _tf.TemporaryDirectory(prefix="r3hd_m15_") as tmp:
    for stored, extra, want in (("auto", [], 2), ("3", [], 3), ("1", [], 1), ("3", ["-RenderScale", "1"], 1),
                                ("1", ["-RenderScale", "auto"], 2)):
        sf = Path(tmp) / f"settings_{stored}.json"
        sf.write_text(json.dumps({"schema": 2, "preset": "vanilla", "preferences": {"render_scale": stored}}), encoding="utf-8")
        code, out = powershell("play.ps1", "-DryRun", "-SettingsFile", str(sf), "-Width", "2560", "-Height", "1600", *extra)
        check(code == 0 and scale_of(out) == want, f"settings render_scale={stored} {' '.join(extra)} at 2560x1600 -> scale {want}")
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
