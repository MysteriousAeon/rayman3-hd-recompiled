#!/usr/bin/env python3
"""M23 haptics regression (no game run): a hidden test run cannot drive a controller actuator, a visible
session keeps vibration, and the hidden runner refuses a build without the safeguard (D-053).

    python tools/m23_haptics_regression.py                -> M23_HAPTICS_REGRESSION PASS checks=N failures=0
    python tools/m23_haptics_regression.py --run RUN...   also judge hidden run directories
                                                          (private/work/m6_runs/RUN): policy suppressed, no pad
                                                          driver created, no controller opened
    python tools/m23_haptics_regression.py --binaries     the built binaries carry the marker the runner needs

The policy functions are tested by m23_haptics_test.exe (in the build). What no test here can do is feel a
motor: the guarantee is structural (no device is opened, no call reaches a sink).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
TOOLS = ROOT / "tools"
RUNS = ROOT / "private" / "work" / "m6_runs"
BUILD = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
MARKER = "M23 haptics policy={} physical_pad_drivers={}"
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
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def judge_run(name: str) -> None:
    log = "\n".join(read(p) for p in sorted((RUNS / name).glob("runtime*.log")))
    policy = re.findall(r"M23 haptics policy=(\w+) physical_pad_drivers=(\w+)", log)
    check(bool(policy) and set(policy) == {("suppressed", "none")}, f"{name}: policy suppressed, no pad driver (got {sorted(set(policy))})")
    for needle in ("SDL input driver initialized", "SDL OnControllerDeviceAdded", "XInput driver"):
        check(needle not in log, f"{name}: '{needle}' absent (no controller opened)")


if "--run" in sys.argv:
    for run_name in sys.argv[sys.argv.index("--run") + 1:]:
        if not run_name.startswith("--"):
            judge_run(run_name)
if "--binaries" in sys.argv:
    found = [p.name for p in sorted(BUILD.glob("*")) if p.suffix in (".exe", ".dll") and p.name.startswith(("r3hd", "rex"))
             and MARKER.encode() in p.read_bytes()]
    check(bool(found), f"a built binary carries the marker (found in {found})")

header = read(TOOLS / "m23_haptics.h")
patch = read(TOOLS / "m23_haptics_patch.py")
xam = read(SDK / "src/kernel/xam/xam_input.cpp")
system = read(SDK / "src/input/input_system.cpp")
sdl = read(SDK / "src/input/sdl/sdl_input_driver.cpp")
xinput = read(SDK / "src/input/xinput/xinput_input_driver.cpp")
hidden = read(TOOLS / "run_milestone6.ps1")
play = read(TOOLS / "play.ps1")
bat = read(TOOLS / "build_milestone8.bat")

check(read(SDK / "include/rex/m23_haptics.h") == header, "m23_haptics.h: installed copy equals tools/")

# One variable decides, and it is the one that makes a run hidden; no opt-out exists.
code = code_only(header)
check(code.count("getenv") == 1 and 'std::getenv("R3HD_NONINTRUSIVE")' in code, "policy: keyed on R3HD_NONINTRUSIVE only")
check("return nonintrusive != nullptr;" in code, "policy: any value of the variable suppresses")
check(f'kMarker[] = "{MARKER}"' in header, "marker text")

# Layer 1: XAM answers a hidden run before any driver.
entry = xam[xam.index("u32 XamInputSetState_entry("):]
entry = entry[:entry.index("\n}\n")]
check("if (m23haptics::Suppressed()) {" in entry and "return m23haptics::HiddenSetStateResult(uint32_t(user_index));" in entry,
      "XAM: hidden run answered at the boundary")
check(entry.index("m23haptics::Suppressed()") < entry.index("is->SetState("), "XAM: before the input system call")
check(entry.count("is->SetState(") == 1, "XAM: one path to the drivers")

# Layer 2: no physical pad driver in a hidden run.
factory = system[system.index("CreateDefaultInputSystem(bool tool_mode) {"):]
check("const bool m23_pads = m23haptics::PhysicalPadDriversAllowed(m23haptics::Suppressed());" in factory, "factory: policy read once")
check('if (m23_pads && REXCVAR_GET(input_backend) == "xinput") {' in factory
      and 'if (m23_pads && REXCVAR_GET(input_backend) == "sdl") {' in factory, "factory: both pad drivers gated")
check(factory.count("XinputInputDriver>(") == 1 and factory.count("SDLInputDriver>(") == 1, "factory: no other pad driver creation")
check(system.count("std::make_unique<sdl::SDLInputDriver>") == 1 and system.count("std::make_unique<xinput::XinputInputDriver>") == 1,
      "input system: pad drivers are created in the factory only")
check("REXLOG_INFO(m23haptics::kMarker," in factory, "factory: policy logged with the marker format")

# Layer 3: every actuator call in the SDK sits behind the policy.
sinks = []
for path in sorted((SDK / "src").rglob("*.cpp")) + sorted((ROOT / "tools" / "m2_host").rglob("*.cpp")):
    if "thirdparty" in path.parts:
        continue
    text = code_only(read(path))
    for match in re.finditer(r"SDL_RumbleGamepad\w*\(|SDL_RumbleJoystick\w*\(|SDL_SendGamepadEffect\(|SDL_SendJoystickEffect\(|"
                             r"SDL_PlayHapticRumble\(|SDL_RunHapticEffect\(|SDL_OpenHaptic\w*\(|\bxiss\(", text):
        sinks.append((path.name, match.group(0)))
check(sorted(sinks) == [("sdl_input_driver.cpp", "SDL_RumbleGamepad("), ("xinput_input_driver.cpp", "xiss(")],
      f"exactly two actuator call sites exist (found {sorted(sinks)})")
for name, text, call in (("SDL", sdl, "SDL_RumbleGamepad("), ("XInput", xinput, "xiss(user_index, &native_vibration)")):
    body = text[text.index("::SetDeviceVibration(DeviceId id, X_INPUT_VIBRATION* vibration) {"):]
    body = body[:body.index("\n}\n")]
    check("if (m23haptics::Suppressed()) {" in body and body.index("m23haptics::Suppressed()") < body.index(call),
          f"{name} sink: policy tested before the device call")
    check(body.index("return X_ERROR_SUCCESS;") < body.index(call), f"{name} sink: returns before the device call")

# Fail closed: the hidden runner checks the build before it starts anything; a visible session is never hidden.
check(f"$text.Contains('{MARKER}')" in hidden, "runner: looks for the marker in the build's binaries")
check("if (-not $hapticsGuard) { throw 'Hidden run refused" in hidden, "runner: refuses without it")
check(hidden.index("if (-not $hapticsGuard)") < hidden.index("New-Object System.Diagnostics.ProcessStartInfo"),
      "runner: the refusal comes before the process is created")
check("$env:R3HD_NONINTRUSIVE = '1'" in hidden and hidden.index("if (-not $hapticsGuard)") < hidden.index("$env:R3HD_NONINTRUSIVE = '1'"),
      "runner: sets the variable the policy reads")
check("'R3HD_NONINTRUSIVE'" in play.split("$saved = @{}")[0] and "R3HD_NONINTRUSIVE" not in play.split("$saved = @{}")[1],
      "play.ps1 clears R3HD_NONINTRUSIVE and never sets it: a visible session keeps vibration")
for legacy in ("run_milestone2.ps1", "run_milestone3.ps1", "run_milestone4.ps1", "run_milestone5.ps1"):
    text = read(TOOLS / legacy)
    check("if (-not $env:R3HD_LEGACY_VISIBLE_RUN) { throw 'Superseded runner (D-053)" in text
          and text.index("R3HD_LEGACY_VISIBLE_RUN") < text.index("$ErrorActionPreference"), f"{legacy}: refuses unattended use")
check('if [ -z "$R3HD_LEGACY_VISIBLE_RUN" ]; then' in read(TOOLS / "m5_pilot_run.sh"), "m5_pilot_run.sh: refuses unattended use")
# Known runners plus the explicitly user-invoked E-304 visible observer.
# (m8_crash_regression.py starts m8_crash_test.exe, a host test without input code; this file names the patterns.)
starters = sorted(p.name for p in list(TOOLS.glob("*.py")) + list(TOOLS.glob("*.ps1")) + list(TOOLS.glob("*.sh"))
                  if p.name not in ("m23_haptics_regression.py", "m8_crash_regression.py")
                  and (p.name in ("combo_close_visual.py", "combo_close_playtest.py") or re.search(r"ProcessStartInfo|Start-Process[^\n]*\$exe|\"\$EXE\"|subprocess\.\w+\(\[str\(EXE\)", read(p))))
check(set(starters) <= {"play.ps1", "run_milestone2.ps1", "run_milestone3.ps1", "run_milestone4.ps1", "run_milestone5.ps1",
                        "run_milestone6.ps1", "m5_pilot_run.sh", "combo_close_visual.py", "combo_close_playtest.py"}, f"game starters are the known runners only (found {starters})")
playable = read(TOOLS / 'combo_close_playtest.py')
check("mode.add_argument('--manual'" in playable and "input('Press Enter" in playable
      and "R3HD_TEST_COMBO_PLAYTEST='1'" in playable and "'--mnk_mode=true'" in playable
      and "if not k.upper().startswith('R3HD_')" in playable,
      'private playable Combo: explicit manual launch, real input, inherited experiments removed')
diagnostic = read(TOOLS / 'combo_hud_diagnostic.py')
check("R3HD_TEST_COMBO_CAPTURE='1'" in diagnostic and "'R3HD_TEST_COMBO_CAPTURE'" in play
      and 'return m6frame::CaptureAt(swap)' in read(TOOLS / 'm8_runtime_patch.py')
      and '!std::strcmp(combo_capture, "1")' in read(TOOLS / 'm8_runtime_patch.py'),
      'private Combo captures: explicit diagnostic flag, bounded request policy, cleared by ordinary Play')
check("env.pop('R3HD_TEST_COMBO_CLOSE', None)" in diagnostic
      and "env.pop('R3HD_TEST_COMBO_PLAYTEST', None)" in diagnostic
      and "session / \"user\"" in diagnostic and "session / \"cache\"" in diagnostic,
      'private HUD control removes both prototype flags and redirects disposable writes')
check('Process(process_id,' in diagnostic and 'len(captures) < 8' in diagnostic
      and 'score_events < 4' in diagnostic and 'WriteProcessMemory' not in diagnostic,
      'private HUD diagnostics: owned child, read-only event sampling, at most eight captures')
visual = read(TOOLS / "combo_close_visual.py")
check("R3HD_NONINTRUSIVE='1'" in visual and "R3HD_TEST_COMBO_CLOSE=combo_mode" in visual
      and "if combo_mode not in ('timed', 'countdown', 'delayed-countdown'):" in visual
      and "if not k.upper().startswith('R3HD_')" in visual,
      "manual Combo observer: child-only device suppression, inherited experiments removed")
check("mode.add_argument('--manual'" in visual and "input('Press Enter" in visual
      and "owner.value == pid" in visual and "ui.ShowWindow(hwnd, 4)" in visual,
      "manual Combo observer: explicit invocation/readiness, reveal only owned window without activation")

# Build chain.
discord = read(TOOLS / "m2_host" / "r3hd_discord.h")
check('!std::getenv("R3HD_NONINTRUSIVE")' in discord and
      'if (Enabled()) StartWorker();' in discord,
      "Discord presence: hidden runs cannot reach the external client")
# D-102: the DualSense light bar / R2 output lives in an installed header (not in the .cpp scan above).
ds = read(TOOLS / "r3hd_ds_sdl.h")
check(read(SDK / "include/rex/r3hd_ds_sdl.h") == ds, "r3hd_ds_sdl.h: installed copy equals tools/")
for fn in ("void Step(", "void ReleaseAll(", "void Renumbered("):   # D-105 entry points
    body = ds[ds.index(fn):]
    body = body[:body.index("\n}\n")]
    check("if (m23haptics::Suppressed()" in body and body.index("m23haptics::Suppressed()") < body.index("Apply("),
          f"DualSense {fn.split()[1]} hidden runs return before any output")
ds_code = code_only(ds)
check(ds_code.count("SDL_SetGamepadLED(") == 1 and ds_code.count("SDL_SendGamepadEffect(") == 1
      and ds_code.count("Apply(") == 4, "DualSense: one light call, one effect call, reached only through Step / "
      "ReleaseAll / Renumbered")
check("SDL_SetGamepadPlayerIndex(" not in ds_code, "DualSense: the light is given back by an LED write (D-105)")
check("DualSense" not in sdl or "r3hd_ds::Step(" in sdl, "DualSense: the driver steps through the gated helper")
check("r3hd_ds::" not in sdl or all(f'r3hd_ds::ReleaseAll(controllers_, "{r}")' in sdl
                                    for r in ("focus", "close", "title_exit")),
      "DualSense: released at focus loss, window close and title exit (D-105)")
check("python tools\\r3hd_dualsense_patch.py" in bat and bat.index("m50_runtime_patch.py") < bat.index("r3hd_dualsense_patch.py")
      < bat.index("cmake --build external"), "build replays the DualSense patch last, before the SDK build")
check("python tools\\m23_haptics_patch.py" in bat, "build replays the haptics patch")
check(bat.index("m23_runtime_patch.py") < bat.index("m23_haptics_patch.py") < bat.index("cmake --build external"), "patch order")
check("m23_haptics_test.exe || exit /b 1" in bat and "m23_haptics_test " in bat, "build runs the policy test")
check("python tools\\m23_haptics_regression.py --binaries" in bat, "build runs this regression against the built binaries")
check("patch_once" in patch and "from_head" not in patch, "patch is additive (patch_once)")

print(f"M23_HAPTICS_REGRESSION {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures}")
sys.exit(1 if failures else 0)
