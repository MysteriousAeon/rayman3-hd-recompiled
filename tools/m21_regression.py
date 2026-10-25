#!/usr/bin/env python3
"""M21 tooling regression (no game run): shape and isolation of the cursor rule and the time-zone bias (D-050).

    python tools/m21_regression.py                -> M21_REGRESSION PASS checks=N failures=0
    python tools/m21_regression.py --run RUN...   also judge hidden run directories (private/work/m6_runs/RUN):
                                                  the cursor was never touched, the zone line is present

The rule and the conversion themselves are tested by m21_host_test.exe (in the build). What needs a person: the
cursor over a visible, focused window (reports/milestone21/REPORT.md).
"""
import re
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


def code_only(text: str) -> str:
    """Source without // comments (the headers describe in words what the code must not do)."""
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def judge_run(name: str) -> None:
    """A hidden run: no cursor action at all, policy line says untouched, no unrecognised zone value."""
    parts = sorted((RUNS / name).glob("runtime*.log"))  # the log rotates: runtime.1.log holds the start
    if not parts:
        check(False, f"{name}: runtime log not found")
        return
    text = "".join(read(part) for part in parts)
    check("M6 window hidden=true show=false" in text, f"{name}: is a hidden run")
    check(text.count("M21 cursor policy=untouched") == 1, f"{name}: cursor policy untouched")
    check("M21 cursor action=" not in text, f"{name}: no cursor action in a hidden run")
    zone = re.findall(r"M21 timezone policy=(\w+) bias_min=(-?\d+) host_ok=(\w+) host_id=(\d+) recognised=(\w+)", text)
    check(all(z[4] == "true" for z in zone), f"{name}: zone setting recognised")
    check(all(-900 <= int(z[1]) <= 900 for z in zone), f"{name}: bias in range")


if "--run" in sys.argv:
    for run in sys.argv[sys.argv.index("--run") + 1:]:
        judge_run(run)

# --- the headers are installed and host-only ------------------------------------------------------------------------
for name in ("m21_cursor.h", "m21_timezone.h"):
    installed = SDK / "include/rex" / name
    check(installed.is_file() and installed.read_bytes() == (TOOLS / name).read_bytes(), f"installed header is tools/{name}")
    code = code_only(read(TOOLS / name))
    for needle in ("virtual_membase", "PPCContext", "TranslateVirtual", "REX_KERNEL_MEMORY", "ctx."):
        check(needle not in code, f"{name} does not touch guest state ({needle})")
cursor_code = code_only(read(TOOLS / "m21_cursor.h"))
check("SDL" not in cursor_code and "windows.h" not in cursor_code, "the cursor rule has no platform call of its own")

# --- cursor: the window applies the rule with the two SDL calls and nothing else -------------------------------------
window = read(SDK / "src/ui/window_sdl.cpp")
m21_lines = [line for line in window.splitlines() if "M21" in line and not line.lstrip().startswith("//")]
check(len(m21_lines) >= 14, "window patch present")
helper = window.split("void M21ApplyCursor(")[1].split("\n}\n")[0]
check(set(re.findall(r"\b(SDL_\w+|ShowCursor|SetCursor\w*|ClipCursor|SetCapture)\b", helper)) == {"SDL_HideCursor", "SDL_ShowCursor"},
      "the cursor action is SDL_HideCursor / SDL_ShowCursor only")
auto = window.split("bool M21CursorAuto()")[1].split("\n}\n")[0]
check('!std::getenv("R3HD_NONINTRUSIVE")' in auto and 'std::getenv("R3HD_CURSOR")' in auto, "hidden windows and R3HD_CURSOR are excluded once, at the gate")
calls = re.findall(r"^(.*)M21ApplyCursor\(M21Tracker\(\)\.(\w+)\(", window, re.M)
check(len(calls) == 10, "ten event sites")
check(all("if (M21CursorAuto())" in before or event in ("MouseIdle", "Request", "MouseMoved") for before, event in calls),
      "every one-line event site is behind the gate")
for event in ("MouseIdle", "Request", "MouseMoved"):
    block = window.split(f"M21ApplyCursor(M21Tracker().{event}(")[0].rsplit("if (M21CursorAuto()) {", 1)
    check(len(block) == 2 and block[1].count("}") == 0, f"{event} site is inside a gated block")
check({event for _, event in calls} == {"MouseIdle", "Opened", "Focus", "Closed", "Request", "Minimized", "Restored", "MouseMoved"},
      "open, focus, minimize, restore, mouse, request and close are all covered")
check(window.count('M21Tracker().Focus(false), "focus_lost"') == 1 and window.count('M21Tracker().Minimized(), "minimized"') == 1
      and window.count('M21Tracker().Closed(), "close"') == 1, "restoration on focus loss, minimize and close")
close = window.split("void WindowSDL::DestroySDLWindow()")[1].split("\n}\n")[0]
check(close.index("M21Tracker().Closed()") < close.index("SDL_DestroyWindow("), "the cursor is restored before the window is destroyed")
apply_now = window.split("void WindowSDL::ApplyCursorVisibilityNow() {")[1].split("\n}\n")[0]
check(apply_now.index('if (std::getenv("R3HD_NONINTRUSIVE")) return;') < apply_now.index("M21CursorAuto()"), "hidden windows return before any cursor code")
check("case CursorVisibility::kAutoHidden:" in apply_now, "the SDK's own behaviour is kept for R3HD_CURSOR=visible")
# Pointer position, confinement and capture: exactly the SDK's own sites, each already refused for hidden windows.
check(window.count("SDL_WarpMouseInWindow(") == 1 and window.count("SDL_SetWindowRelativeMouseMode(sdl_window_") == 1
      and window.count("SDL_CaptureMouse(") == 2, "no new warp, relative-mode or capture site")
for forbidden in ("SDL_WarpMouseGlobal", "SDL_SetWindowMouseGrab", "SDL_SetWindowMouseRect", "ClipCursor", "SetCursorPos",
                  "SetCapture(", "SDL_SetWindowKeyboardGrab"):
    check(forbidden not in window, f"window code does not use {forbidden.strip()}")
check(window.count("SDL_RaiseWindow(") == 1, "no new focus request")
for path in sorted((SDK / "src").rglob("*.cpp")):
    if path.name == "window_sdl.cpp" or "thirdparty" in path.parts:
        continue
    text = read(path)
    if "SDL_" in text or "m21" in text:
        check("SDL_HideCursor" not in text and "SDL_ShowCursor" not in text and "m21cursor" not in text,
              f"{path.name}: no cursor call outside the window")

# --- time zone: one setting, host bias, everything else as pinned ----------------------------------------------------
xconfig = read(SDK / "src/kernel/xboxkrnl/xboxkrnl_xconfig.cpp")
case = xconfig.split("case 0x0001: {  // XCONFIG_USER_TIME_ZONE_BIAS")[1].split("case 0x0002:")[0]
check("m21tz::GuestBias(m21_policy, m21_zone)" in case and "store_and_swap<uint32_t>(value, uint32_t(m21_bias))" in case and "setting_size = 4;" in case,
      "setting 1 carries the bias as a 4-byte value")
rest = xconfig.split("case 0x0002:  // XCONFIG_USER_TIME_ZONE_STD_NAME")[1].split("break;")[0]
check(all(f"case 0x000{n}:" in rest for n in range(3, 8)) and "store_and_swap<uint32_t>(value, 0);" in rest, "settings 2..7 still answer 0")
check(xconfig.count("m21tz::") >= 6 and xconfig.count("QueryHostZone()") == 1, "one host query site")
for other in ("xboxkrnl_rtl.cpp", "xboxkrnl_threading.cpp", "xboxkrnl_io_info.cpp"):
    check("m21" not in read(SDK / "src/kernel/xboxkrnl" / other), f"{other}: guest clock, time fields and file times are not converted")
zone = read(TOOLS / "m21_timezone.h")
zone_code = code_only(zone)
check(zone_code.count("GetTimeZoneInformation(") == 1 and "SetTimeZoneInformation" not in zone_code and "SetSystemTime" not in zone_code
      and "SetLocalTime" not in zone_code and "SetDynamicTimeZoneInformation" not in zone_code,
      "the host zone is read, never set")
for needle in ("SetFileTime", "utime", "last_write_time", "fopen", "CreateFile"):
    check(needle not in zone_code, f"no file or timestamp is rewritten ({needle})")

# --- switches --------------------------------------------------------------------------------------------------------
play = read(TOOLS / "play.ps1")
test_only = play.split("$testOnly =")[1].split("$saved = @{}")[0]
check("'R3HD_CURSOR'" in test_only and "'R3HD_TIMEZONE'" in test_only, "play.ps1 clears inherited R3HD_CURSOR and R3HD_TIMEZONE")
check("[ValidateSet('auto', 'visible')][string]$Cursor = 'auto'" in play and "[ValidateSet('local', 'utc')][string]$SaveClock = 'local'" in play,
      "launcher defaults: cursor auto, save clock local")
check("$env:R3HD_TIMEZONE = 'utc'" in play and "bias:" not in play, "the launcher offers host or utc, never a fixed bias")
check("R3HD_NONINTRUSIVE" not in play.split("$saved = @{}")[1], "the launcher never starts a hidden window")
allowed = {"m21_regression.py", "m21_runtime_patch.py", "m21_timezone.h", "m21_cursor.h", "m21_host_test.cpp", "m21_campaign_check.py", "play.ps1"}
for path in sorted(TOOLS.glob("*")):
    if path.is_file() and path.suffix in (".py", ".ps1", ".bat", ".sh", ".h", ".cpp") and path.name not in allowed:
        text = read(path)
        check("R3HD_CURSOR" not in text and "R3HD_TIMEZONE" not in text, f"{path.name} does not use the M21 switches")
hidden = read(TOOLS / "run_milestone6.ps1")
check("R3HD_NONINTRUSIVE" in hidden, "the hidden runner sets R3HD_NONINTRUSIVE (the cursor gate)")

# --- build order -----------------------------------------------------------------------------------------------------
build = read(TOOLS / "build_milestone8.bat")
check(build.index("m20_runtime_patch.py") < build.index("m21_runtime_patch.py") < build.index("cmake --build external/rexglue-sdk"),
      "the M21 patch replays after M20, before the SDK build")
check(build.index("m20_prepare.py") < build.index("m21_prepare.py") < build.index("rexglue.exe"), "m21_prepare.py runs after m20_prepare.py")
check("m21_host_test.exe || exit /b 1" in build and "m21_regression.py || exit /b 1" in build, "the M21 test and this regression are in the build")

print(f"M21_REGRESSION {'PASS' if failures == 0 else 'FAIL'} checks={checks} failures={failures}")
sys.exit(1 if failures else 0)
