#!/usr/bin/env python3
"""G6-P75 (D-324): controller motors are stopped when the game closes. Source and wiring regression (no game run).

    python tools/g6p75_pad_motors_regression.py            -> G6P75_PAD_MOTORS_REGRESSION PASS checks=N
    python tools/g6p75_pad_motors_regression.py --binaries also: the built runtime library carries the close log line
    python tools/g6p75_pad_motors_regression.py --sdk DIR  read a copy of the SDK tree instead (dry runs)

Reads the replayed SDK tree (external/rexglue-sdk, written by tools/r3hd_pad_motors_patch.py), the installed headers
and the build script. Every rule is also run against mutated copies of those texts, and each mutation must be
rejected (negative controls: a rule that cannot fail proves nothing). The policy itself is tested by
r3hd_pad_motors_test.exe (mock pad) and r3hd_pad_motors_sdl_test.exe (pinned SDL, in-process virtual pad).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
if "--sdk" in sys.argv:
    SDK = Path(sys.argv[sys.argv.index("--sdk") + 1])
TOOLS = ROOT / "tools"
BUILD = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
LOG_LINE = "R3HD pad motors closed reason={} stopped={}"

FILES = {
    "app": SDK / "src/ui/rex_app.cpp",
    "driver_h": SDK / "include/rex/input/input_driver.h",
    "system_h": SDK / "include/rex/input/input_system.h",
    "system": SDK / "src/input/input_system.cpp",
    "sdl_h": SDK / "include/rex/input/sdl/sdl_input_driver.h",
    "sdl": SDK / "src/input/sdl/sdl_input_driver.cpp",
    "motors": TOOLS / "r3hd_pad_motors.h",
    "motors_sdl": TOOLS / "r3hd_pad_motors_sdl.h",
    "motors_inst": SDK / "include/rex/r3hd_pad_motors.h",
    "motors_sdl_inst": SDK / "include/rex/r3hd_pad_motors_sdl.h",
    "bat": TOOLS / "build_milestone8.bat",
    "test_bat": TOOLS / "build_pad_motors_test.bat",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")


def code_only(text: str) -> str:
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def body(text: str, head: str) -> str:
    if head not in text:
        return ""
    rest = text[text.index(head):]
    end = rest.find("\n}\n")
    return rest[: end if end >= 0 else len(rest)]


def before(text: str, a: str, b: str) -> bool:
    return a in text and b in text and text.index(a) < text.index(b)


def rules(t: dict) -> list:
    out = []

    def rule(name, ok):
        out.append((name, bool(ok)))

    app = body(t["app"], "void ReXApp::OnClosing(ui::UIEvent& e) {")
    rule("app: OnClosing tells the input system before TerminateTitle and the hard exit",
         before(code_only(app), "->OnHostClosing();", "TerminateTitle();") and
         before(code_only(app), "->OnHostClosing();", "std::_Exit(0);"))
    rule("driver interface: OnHostClosing is virtual with an empty default",
         "virtual void OnHostClosing() {}" in code_only(t["driver_h"]))
    rule("input system: OnHostClosing declared and forwarded to every driver",
         "void OnHostClosing();" in t["system_h"] and
         "driver->OnHostClosing();" in body(t["system"], "void InputSystem::OnHostClosing() {"))

    sdl, sdl_code = t["sdl"], code_only(t["sdl"])
    host = code_only(body(sdl, "void SDLInputDriver::OnHostClosing() {"))
    rule("SDL: window close stops the motors under the controllers lock",
         before(host, "DrainAndLock()", 'CloseMotorsLocked("close");'))
    avail = code_only(body(sdl, "void SDLInputDriver::OnWindowAvailable(rex::ui::Window* window) {"))
    tail = avail[avail.rfind("if (!window && SDL_Gamepad_initialized_) {"):] if 'CloseMotorsLocked("title_exit");' in avail else ""
    rule("SDL: title exit stops the motors under the controllers lock, after the D-105 release",
         before(tail, "DrainAndLock()", 'CloseMotorsLocked("title_exit");') and
         before(avail, 'r3hd_ds::ReleaseAll(controllers_, "title_exit");', 'CloseMotorsLocked("title_exit");') and
         before(avail, 'REXLOG_INFO("SDL input driver initialized successfully");', 'CloseMotorsLocked("title_exit");'))
    rule("SDL: the D-102 title-exit block is left as that patch wrote it (its idempotence text)",
         'r3hd_ds::ReleaseAll(controllers_, "title_exit");\n'
         '    r3hd_ds_speaker::Post(r3hd_ds_speaker::Request::kShutdown);  // D-141\n  }\n' in sdl)
    close = code_only(body(sdl, "void SDLInputDriver::CloseMotorsLocked(const char* reason) {"))
    rule("SDL: CloseMotorsLocked goes through the gated helper and logs once",
         "r3hd_motors::CloseSdl(motor_outputs_, controllers_)" in close and "if (first) REXLOG_INFO(" in close and
         f'"{LOG_LINE}"' in close)
    vib = code_only(body(sdl, "X_RESULT SDLInputDriver::SetDeviceVibration(DeviceId id, X_INPUT_VIBRATION* vibration) {"))
    rule("SDL: vibration keeps the M23 return first", before(vib, "m23haptics::Suppressed()", "SDL_RumbleGamepad("))
    rule("SDL: after the close a request reaches no device",
         before(vib, "if (motor_outputs_.closed()) {", "SDL_RumbleGamepad(") and
         before(vib, "auto guard = DrainAndLock();", "if (motor_outputs_.closed()) {"))
    rule("SDL: every request is recorded with its result",
         before(vib, "SDL_RumbleGamepad(", "r3hd_motors::Requested(controller->motors,") and
         "const bool sent = SDL_RumbleGamepad(controller->sdl, vibration->left_motor_speed," in vib)
    rule("SDL: the request itself is unchanged (speeds, SDL's maximum duration)",
         "vibration->right_motor_speed, kRumbleDurationMs);" in vib and
         "constexpr uint32_t kRumbleDurationMs = 0xFFFF;" in sdl_code)
    for fn in ("void SDLInputDriver::OnLostFocus(", "void SDLInputDriver::OnGotFocus(",
               "X_RESULT SDLInputDriver::GetDeviceState(", "X_RESULT SDLInputDriver::GetDeviceKeystroke(",
               "void SDLInputDriver::OnControllerDeviceRemovedLocked("):
        rule(f"SDL: {fn.split('::')[1].split('(')[0]} unchanged by D-324",
             fn in sdl and "motor" not in code_only(body(sdl, fn)).lower())
    rule("SDL header: per-pad state, outputs and the two entry points",
         all(s in t["sdl_h"] for s in ("r3hd_motors::Motors motors;", "r3hd_motors::Outputs motor_outputs_;",
                                       "void OnHostClosing() override;", "void CloseMotorsLocked(const char* reason);",
                                       "#include <rex/r3hd_pad_motors.h>")))

    m, ms = code_only(t["motors"]), code_only(t["motors_sdl"])
    rule("headers: installed copies equal tools/",
         t["motors_inst"] == t["motors"] and t["motors_sdl_inst"] == t["motors_sdl"])
    rule("helper: one device call, a zero rumble request",
         len(re.findall(r"SDL_\w+\(", ms.replace("SDL_Delay(50)", ""))) == 1 and
         ms.count("SDL_RumbleGamepad(pad.sdl, 0, 0, 0)") == 1)
    rule("helper: hidden runs (M23) return before the device call",
         before(ms, "if (m23haptics::Suppressed()) {", "SDL_RumbleGamepad("))
    rule("policy: only pads that may be running are stopped, once",
         "if (!pad.motors.running) continue;" in m and "if (!closed_) {" in m and "closed_ = true;" in m)
    rule("policy: a refused request keeps the pad in the set to stop",
         "m.running = sent ? nonzero : (m.running || nonzero);" in m)

    bat = t["bat"]
    main_line = "python tools\\r3hd_pad_motors_patch.py || exit /b 1"
    rule("build: the patch is replayed last, before the SDK build",
         bat.count(main_line) == 1 and before(bat, "python tools\\r3hd_lockon_runtime_patch.py", main_line) and
         before(bat, main_line, "cmake --build external"))
    rule("build: the superseded-insert migration runs just before the D-102 patch",
         "python tools\\r3hd_pad_motors_patch.py migrate || exit /b 1\npython tools\\r3hd_dualsense_patch.py" in bat)
    rule("build: the tests and this regression run before M8_BUILD_OK",
         before(bat, "call tools\\build_pad_motors_test.bat || exit /b 1", "echo M8_BUILD_OK") and
         "python tools\\g6p75_pad_motors_regression.py" in t["test_bat"] and
         "r3hd_pad_motors_sdl_test.exe hidden || exit /b 1" in t["test_bat"])
    return out


MUTATIONS = [
    ("app: OnClosing without the call", "app", "->OnHostClosing();", "->OnHostClosingX();"),
    ("app: the call block removed", "app",
     "  if (runtime_ && runtime_->input_system()) {\n"
     "    static_cast<rex::input::InputSystem*>(runtime_->input_system())->OnHostClosing();\n  }\n", ""),
    ("system: not forwarded", "system", "driver->OnHostClosing();", "(void)driver;"),
    ("SDL: close not stopped", "sdl", 'CloseMotorsLocked("close");', ""),
    ("SDL: title exit not stopped", "sdl", '    CloseMotorsLocked("title_exit");', ""),
    ("SDL: inserted inside the D-102 block", "sdl", '    r3hd_ds::ReleaseAll(controllers_, "title_exit");\n',
     '    r3hd_ds::ReleaseAll(controllers_, "title_exit");\n    CloseMotorsLocked("title_exit");\n'),
    ("SDL: no closed check", "sdl", "if (motor_outputs_.closed()) {", "if (false) {"),
    ("SDL: request not recorded", "sdl", "r3hd_motors::Requested(controller->motors,", "(void)(controller->motors,"),
    ("SDL: duration changed", "sdl", "vibration->right_motor_speed, kRumbleDurationMs);",
     "vibration->right_motor_speed, 0);"),
    ("SDL: focus loss stops motors", "sdl", "  r3hd_ds::ReleaseAll(controllers_, \"focus\");",
     "  CloseMotorsLocked(\"focus\");\n  r3hd_ds::ReleaseAll(controllers_, \"focus\");"),
    ("helper: nonzero stop", "motors_sdl", "SDL_RumbleGamepad(pad.sdl, 0, 0, 0)", "SDL_RumbleGamepad(pad.sdl, 1, 0, 0)"),
    ("helper: no M23 gate", "motors_sdl", "if (m23haptics::Suppressed()) {", "if (false) {"),
    ("helper: installed copy stale", "motors_sdl_inst", "SDL_Delay(50)", "SDL_Delay(5)"),
    ("policy: stops every pad", "motors", "if (!pad.motors.running) continue;", ""),
    ("policy: forgets a refused stop", "motors", "m.running = sent ? nonzero : (m.running || nonzero);",
     "m.running = nonzero;"),
    ("build: patch not replayed", "bat", "python tools\\r3hd_pad_motors_patch.py || exit /b 1", "rem pad motors"),
    ("build: migration after the D-102 patch", "bat", "python tools\\r3hd_pad_motors_patch.py migrate || exit /b 1\n",
     ""),
    ("build: tests not run", "bat", "call tools\\build_pad_motors_test.bat || exit /b 1", "rem tests"),
]


def main() -> int:
    texts = {k: read(p) if p.exists() else "" for k, p in FILES.items()}
    failures, n = 0, 0
    for name, ok in rules(texts):
        n += 1
        if not ok:
            failures += 1
            print(f"FAIL {name}")
    rejected = 0
    for label, key, old, new in MUTATIONS:
        n += 1
        mutated = dict(texts)
        if old not in mutated[key]:
            failures += 1
            print(f"FAIL mutation anchor missing: {label}")
            continue
        mutated[key] = mutated[key].replace(old, new, 1)
        if all(ok for _, ok in rules(mutated)):
            failures += 1
            print(f"FAIL mutation accepted: {label}")
        else:
            rejected += 1
    if "--binaries" in sys.argv:
        n += 1
        dll = BUILD / "rexruntime.dll"
        if not (dll.exists() and LOG_LINE.encode() in dll.read_bytes()):
            failures += 1
            print("FAIL binaries: rexruntime.dll carries the close log line")
    print(f"mutations rejected {rejected}/{len(MUTATIONS)}")
    print(f"G6P75_PAD_MOTORS_REGRESSION {'PASS' if not failures else 'FAIL'} checks={n} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
