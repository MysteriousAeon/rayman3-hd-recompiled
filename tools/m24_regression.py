#!/usr/bin/env python3
"""M24 tooling regression (no game run): event-trace patch shape, launcher gate, analyzer self-test.

    python tools/m24_regression.py                  -> M24_REGRESSION PASS checks=N failures=0
    python tools/m24_regression.py --run RUN...     also judges hidden run directories (private/work/m6_runs/RUN
                                                    or a path): the trace left the run's safeguards alone

The hidden checks that need the game are in reports/milestone24/REPORT.md:
    python tools/m24_pause_resume.py run TAG --gpu ; python tools/m24_pause_resume.py analyze TAG --expect gpu_bound
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"

checks = failures = 0


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL {label}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# --- the header ------------------------------------------------------------------------------------------------
header = read(ROOT / "tools/m24_event_trace.h")
check(read(SDK / "include/rex/m24_event_trace.h") == header, "installed m24_event_trace.h equals tools/m24_event_trace.h")
check('std::getenv("R3HD_M24_EVENTS")' in header and "if (!path || !*path) return nullptr;" in header,
      "the trace is off unless R3HD_M24_EVENTS names a file")
check("FILE_APPEND_DATA" in header and "FILE_SHARE_READ | FILE_SHARE_WRITE" in header and "OPEN_ALWAYS" in header,
      "the file is opened for shared appending (several modules write to it)")
check("fopen" not in header and "fwrite" not in header, "no buffered stream with a private file position")
check(all(word not in header for word in ("WriteProcessMemory", "ReadProcessMemory", "virtual_membase", "store_and_swap",
                                           "Sleep(", "SetEvent", "WaitForSingleObject", "SuspendThread")),
      "the header reads no guest memory, writes none and waits on nothing")
check("static_assert(sizeof(Record) == 24" in header, "record layout asserted")
check(header.count("REXLOG_INFO(") == 1 and 'REXLOG_INFO("M24 gpu_bound waits={} total_ms={} longest_ms={} span_ms={}"' in header,
      "the one always-on output is the M24 gpu_bound log line")
body = header[header.index("inline void FenceWaited"):header.index("// Pad state and vibration")]
check("if (us < kFenceSlowUs) return;" in body and "if (Now() - b.last < Frequency()) return;" in body,
      "gpu_bound: only waits of kFenceSlowUs or more count, logged one second after the last")

# --- the call sites --------------------------------------------------------------------------------------------
SITES = {
    "src/kernel/xboxkrnl/xboxkrnl_video.cpp": {"m24ev::Event(m24ev::kVdSwap, m24ev::ThreadKiloCyclesSinceLast())": 1},
    "include/rex/m3_gpu_trace.h": {"m24ev::Event(m24ev::kCpSwap,": 1, "m24ev::FenceFrame();": 1},
    "src/ui/d3d12/d3d12_presenter.cpp": {"m24ev::EventAt(m24ev::kPresent,": 1, "m24_present_start": 3},
    "src/kernel/xam/xam_input.cpp": {"m24ev::Buttons(": 2, "m24ev::Vibration(": 1},
    "src/graphics/d3d12/pipeline_cache.cpp": {"m24ev::kPipeline": 1},
    "src/graphics/d3d12/texture_cache.cpp": {"m24ev::Event(m24ev::kTextureLoad)": 1},
    "src/graphics/command_processor.cpp": {"m24ev::kCpWait": 1},
    "src/graphics/d3d12/command_processor.cpp": {"m24ev::FenceWaited(m24_fence_start, uint32_t(m24_fence_behind));": 1},
    "include/rex/m2_import_trace.h": {"m24ev::ImportTimer m24_import_timer(name, unsigned(ctx.lr) - 4)": 1},
}
sources = {}
for rel, needles in SITES.items():
    sources[rel] = text = read(SDK / rel)
    check(text.count("#include <rex/m24_event_trace.h>") == 1 or rel == "src/graphics/d3d12/command_processor.cpp",
          f"{rel}: the header is included once")
    for needle, count in needles.items():
        check(text.count(needle) == count, f"{rel}: {needle!r} x{count} (found {text.count(needle)})")

# every use outside the header is a recording call or a timestamp, never a decision
ALLOWED = re.compile(r"m24ev::(Event|EventAt|Enabled|Now|MicrosSince|Buttons|Vibration|ThreadKiloCyclesSinceLast|"
                     r"FenceWaited|FenceFrame|ImportTimer|k[A-Z][A-Za-z]+)\b")
for rel, text in sources.items():
    used = set(re.findall(r"m24ev::\w+", text))
    check(all(ALLOWED.fullmatch(name) for name in used), f"{rel}: only recording calls ({sorted(used)})")

# an M24 line never sits inside the text an earlier patch script looks for on a replay (the M17 one did, once:
# the frame trace was then called twice per frame)
video = sources["src/kernel/xboxkrnl/xboxkrnl_video.cpp"]
check(video.count("m17trace::Swap(") == 1, "the M17 frame trace is still called once")
check(video.index("m24ev::Event(m24ev::kVdSwap") < video.index("// M17: read-only frame trace")
      and "QueryGuestTickCount());\n  // All of these parameters are REQUIRED." in video,
      "the M24 VdSwap record stands in front of the M17 lines, which stay contiguous")
check(sources["include/rex/m3_gpu_trace.h"].count("m11pace::GuestSwap();") == 1
      and sources["src/ui/d3d12/d3d12_presenter.cpp"].count("m11pace::HostPresent();") == 1, "the M11 pacing calls are still single")

fence = sources["src/graphics/d3d12/command_processor.cpp"]
at = fence.index("m24ev::FenceWaited(")
check("WaitForSingleObject(fence_completion_event_, INFINITE);" in fence[at - 120:at], "the fence wait itself is the pinned call")
check(fence.count("WaitForSingleObject(fence_completion_event_, INFINITE);") == 2, "no fence wait added or removed")
wait = sources["src/graphics/command_processor.cpp"]
check(wait.count("m16vb::RegisterWait(wait, is_memory, poll_reg_addr)") == 1, "the M16 vblank wait is unchanged")
present = sources["src/ui/d3d12/d3d12_presenter.cpp"]
check("DXGI_PRESENT_RESTART" in present and present.count("swap_chain->Present(") == 1, "one Present call, flags unchanged")
pad = sources["src/kernel/xam/xam_input.cpp"]
check(pad.index("m24ev::Vibration(") < pad.index("if (m23haptics::Suppressed())"), "vibration is recorded before the D-053 gate, never after it")
check("m23haptics::HiddenSetStateResult" in pad, "the D-053 answer for hidden runs is still there")

host = read(ROOT / "tools/m2_host/m2_trace.cpp")
check("#include <rex/m24_event_trace.h>" in host and host.count("m24ev::EventAt(m24ev::kGpuWait") == 1, "the D-037 wait hook records a finished wait")
step = host[host.index("void M11GpuWaitStep"):host.index("// M18 (D-047)")]
check("due.QuadPart = -1000;" in step and "WaitForSingleObject(timer, 2);" in step and "if (++streak <= 256) return;" in step,
      "the D-037 wait itself (256 free steps, 100 us timer, 2 ms bound) is unchanged")
built = ROOT / "private/work/rex/src/m2_trace.cpp"
check(not built.exists() or read(built) == host, "the build tree's m2_trace.cpp equals tools/m2_host/m2_trace.cpp")

# --- launcher and tools ----------------------------------------------------------------------------------------
play = read(ROOT / "tools/play.ps1")
gate = play[play.index("$testOnly ="):play.index("$saved = @{}")]
check("'R3HD_M24_EVENTS'" in gate, "play.ps1 clears R3HD_M24_EVENTS (the trace is for hidden tools)")
check(not re.search(r"nvidia|NvAPI|powercfg|PowerManagement|PREFERRED_PSTATE", play, re.I),
      "play.ps1 does not touch driver or system power settings")
build = read(ROOT / "tools/build_milestone8.bat")
check(build.index("m23_haptics_patch.py") < build.index("m24_runtime_patch.py") < build.index("cmake --build external"),
      "the M24 patch replays after M23 and before the SDK build")
check("python tools\\m24_regression.py" in build, "this regression is in the build")
tool = read(ROOT / "tools/m24_pause_resume.py")
check('"--play", "--user-root", run]' in tool and "m9_license_run.py" in tool, "the reproduction goes through the hidden runner")
check("shutil.copytree(m12.SAVES / a.entry / \"profile\", profile)" in tool, "it runs on a working copy of a save entry")
check(not re.search(r"SendInput|keybd_event|mouse_event|SetForegroundWindow|SetCursorPos", tool), "no global input, no window activation")
for name in ("pause_resume_swamp60.txt", "pause_lengths_swamp60.txt", "pause_variants_swamp60.txt", "pause_lengths_knaar10.txt",
             "resume_state_swamp60.txt", "resume_hold_variants_swamp60.txt"):
    steps = [line.split("#", 1)[0].split() for line in read(ROOT / "config/m24" / name).splitlines()]
    kinds = {step[0] for step in steps if step}
    check(kinds <= {"log", "wait", "press", "axis"}, f"config/m24/{name}: log / wait / press / axis only ({sorted(kinds)})")

selftest = subprocess.run([sys.executable, str(ROOT / "tools/m24_pause_resume.py"), "selftest"], capture_output=True, text=True)
check(selftest.returncode == 0 and "M24_PAUSE_SELFTEST PASS" in selftest.stdout, "m24_pause_resume.py selftest")

# --- follow-up: game state across a pause (tools/m24_resume_state.py; D-056) ----------------------------------------
state = read(ROOT / "tools/m24_resume_state.py")
check("beside(run_dir, trace, game, log)" in tool, "the pause runner offers its read-only hook beside the run")
check("m24.cmd_run(a)" in state and "m9_license_run" not in state, "the state run is the pause runner's hidden run")
check(not re.search(r"WriteProcessMemory|SendInput|keybd_event|mouse_event|SetForegroundWindow|SetCursorPos", state),
      "the state tool writes no guest memory, no global input, no window activation")
check("m17.write_watch(trace, ranges)" in state and "MATRIX_BYTES, TRANSLATION = 0x40, 0x34" in state,
      "it records actor matrices through the M17 frame trace's watch list")
check(not re.search(r"m24_resume_state|resume_state", read(ROOT / "tools/play.ps1")), "play.ps1 does not know the state tool")
selftest = subprocess.run([sys.executable, str(ROOT / "tools/m24_resume_state.py"), "selftest"], capture_output=True, text=True)
check(selftest.returncode == 0 and "M24_RESUME_SELFTEST PASS" in selftest.stdout, "m24_resume_state.py selftest")

# --- optional: hidden run directories --------------------------------------------------------------------------
if "--run" in sys.argv:
    for name in sys.argv[sys.argv.index("--run") + 1:]:
        run = Path(name) if Path(name).is_dir() else ROOT / "private/work/m6_runs" / name
        log = read(run / "runtime.log") if (run / "runtime.log").is_file() else ""
        check(bool(log), f"{name}: runtime.log")
        check("M23 haptics policy=suppressed physical_pad_drivers=none" in log, f"{name}: hidden run opened no physical controller")
        check("M22 audio hidden_mute=1" in log, f"{name}: hidden run was muted")
        check("M21 cursor policy=untouched" in log and "M21 cursor action=" not in log, f"{name}: cursor untouched")
        check(not re.search(r"M2 import=\S+ stub=true", log), f"{name}: no stubbed import reached")

print(f"M24_REGRESSION {'FAIL' if failures else 'PASS'} checks={checks} failures={failures}")
sys.exit(1 if failures else 0)
