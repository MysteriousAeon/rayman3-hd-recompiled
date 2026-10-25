#!/usr/bin/env python3
"""M22 tooling regression (no game run): the fidelity instrumentation is off by default and read-only, and a
hidden test run cannot be heard (D-051).

    python tools/m22_regression.py                -> M22_REGRESSION PASS checks=N failures=0
    python tools/m22_regression.py --run RUN...   also judge hidden run directories (private/work/m6_runs/RUN):
                                                  the run was muted; no trace or probe file unless the run
                                                  is named m22_*, *_trace or *_probe
"""
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
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def judge_run(name: str) -> None:
    run = RUNS / name
    log = "\n".join(read(p) for p in sorted(run.glob("runtime*.log")))
    check("M22 audio hidden_mute=1" in log or "audio endpoint" not in log, f"{name}: hidden run muted")
    check("M22 audio hidden_mute=0" not in log, f"{name}: no audible render client")
    # A run that was asked for instrumentation says so in its name (m22_*, m23_*, *_trace, *_probe): the hidden
    # runner does not record the environment.
    if not (name.startswith(("m22_", "m23_")) or name.endswith(("_trace", "_probe"))):
        check(not list(run.glob("m22_draws_*.bin")), f"{name}: no draw trace without a request")
        check(not (run / "m22_audio.txt").exists(), f"{name}: no audio probe file without a request")
    check(len(list(run.glob("m22_draws_*.bin"))) <= len(list(run.glob("m3_frame_*.bmp"))),
          f"{name}: at most one trace per explicit frame")


if "--run" in sys.argv:
    for run_name in sys.argv[sys.argv.index("--run") + 1:]:
        judge_run(run_name)

trace = code_only(read(TOOLS / "m22_draw_trace.h"))
probe = code_only(read(TOOLS / "m22_audio_probe.h"))
patch = read(TOOLS / "m22_runtime_patch.py")
driver = read(SDK / "src/audio/sdl/sdl_audio_driver.cpp")
xma = read(SDK / "src/audio/xma_context.cpp")
cp = read(SDK / "src/graphics/d3d12/command_processor.cpp")
m3 = read(SDK / "include/rex/m3_gpu_trace.h")
bat = read(TOOLS / "build_milestone8.bat")
play = read(TOOLS / "play.ps1")
hidden = read(TOOLS / "run_milestone6.ps1")

# Installed copies are the tracked sources.
for header in ("m22_draw_trace.h", "m22_audio_probe.h"):
    check(read(SDK / "include/rex" / header) == read(TOOLS / header), f"{header}: installed copy equals tools/")

# Draw trace: opt-in, tied to explicit frame captures, no guest write, no render change.
check('std::getenv("R3HD_M22_DRAW_TRACE") != nullptr' in trace, "trace: enabled only by its variable")
check("if (!s.enabled) return;" in trace and "if (!captured) return;" in trace, "trace: armed only by an explicit capture")
check("kFileCap" in trace and "s.written < kFileCap" in trace, "trace: bounded file size")
check("m22draw::OnSwap(n, presenter && CaptureAt(n));" in m3, "trace: armed from the capture decision")
check(cp.count("m22draw::Tracing(m3gpu::counters().swaps.load())") == 2, "trace: one draw site, one copy site")
block = cp[cp.index("// M22: one-frame draw-state trace"):cp.index("// M5: active shader binding")]
check("TranslatePhysical" in block and "std::memcpy(row.head" in block, "trace: reads guest memory")
for word in ("store_and_swap", "regs.values[0x2000] =", "WriteRegister", "return false", "return true", "SetScissor",
             "pipeline_cache_->", "texture_cache_->"):
    check(word not in block, f"trace block: no '{word}' (read-only, no effect on the draw)")
check(block.count("TranslatePhysical") == 3 and block.count("m22draw::Bounded(") == 2,
      "trace block: three guest reads (texture head inside its page, index and vertex bytes bounded)")
check("0x20000000u - (address & 0x1FFFFFFFu)" in trace, "trace: reads never pass the end of the physical view")

# Audio: hidden mute by stream gain only; the probe writes statistics, never samples, never changes the data.
check('std::getenv("R3HD_NONINTRUSIVE") && !std::getenv("R3HD_AUDIO_AUDIBLE")' in probe, "mute: hidden runs only, with a switch back")
check("if (m22audio::HiddenMute()) SDL_SetAudioStreamGain(sdl_stream_, 0.0f);" in driver, "mute: SDL stream gain")
check(driver.count("SDL_SetAudioStreamGain") == 1, "mute: one site")
check(driver.index("SDL_SetAudioStreamGain") < driver.index("if (!SDL_ResumeAudioDevice(sdl_device))"), "mute: before the device resumes")
check('REXAPU_INFO("M22 audio hidden_mute={}"' in driver, "mute: logged")
check('std::getenv("R3HD_M22_AUDIO") ? std::fopen("m22_audio.txt", "w") : nullptr' in probe, "probe: opt-in file")
check("fwrite" not in probe, "probe: no sample data written")
check("const float* data" in probe and "float* data" not in probe.replace("const float* data", ""), "probe: output samples are const")
check(driver.count("m22audio::Output(driver, data, sample_count, driver->sdl_device_channels_,") == 2, "probe: both output paths")
for call in ("m22audio::XmaInput(id(), data.IsAnyInputBufferValid());", "m22audio::XmaReset(id());",
             "m22audio::XmaFrame(id());", "m22audio::XmaError(id(), 1);"):
    check(xma.count(call) == 1, f"probe: {call.split('(')[0]} once")
for name in ("XmaInput", "XmaReset", "XmaFrame", "XmaError", "Output"):
    body = probe[probe.index(f"inline void {name}("):]
    body = body[:body.index("\n}\n")]
    check("if (!file) return;" in body, f"probe: {name} does nothing without the file")

# Launcher and hidden runner.
check("'R3HD_M22_DRAW_TRACE', 'R3HD_M22_AUDIO', 'R3HD_AUDIO_AUDIBLE'" in play.split("$saved = @{}")[0], "play.ps1: clears the M22 variables")
check("SDL_SetAudioStreamGain" not in play, "play.ps1: no gain")
check("$env:R3HD_NONINTRUSIVE = '1'" in hidden, "hidden runner sets R3HD_NONINTRUSIVE (the mute gate)")
check("'R3HD_NONINTRUSIVE'" in play.split("$saved = @{}")[0] and "R3HD_NONINTRUSIVE" not in play.split("$saved = @{}")[1],
      "play.ps1 clears R3HD_NONINTRUSIVE and never sets it: a visible session is never muted")

# Build chain.
check("python tools\\m22_runtime_patch.py" in bat, "build replays the M22 patch")
check(bat.index("m21_runtime_patch.py") < bat.index("m22_runtime_patch.py") < bat.index("cmake --build external"), "patch order")
check("python tools\\m22_regression.py" in bat, "build runs this regression")
check("patch_once" in patch and "from_head" not in patch, "patch is additive (patch_once)")

print(f"M22_REGRESSION {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures}")
sys.exit(1 if failures else 0)
