#!/usr/bin/env python3
"""M17 tooling regression (no game run): frame-trace patch shape, pacing default, timing checker on synthetic traces.

    python tools/m17_regression.py        -> M17_REGRESSION PASS checks=N failures=0

The hidden checks that need the game are in reports/milestone17/REPORT.md:
    python tools/m17_frame_trace.py prepare T ; R3HD_FRAME_TRACE=T <hidden tool> ; python tools/m17_frame_trace.py check T
"""
import random
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
WORK = ROOT / "private" / "work" / "m17" / "regression"
sys.path.insert(0, str(ROOT / "tools"))
import m17_frame_trace as ft  # noqa: E402

checks = failures = 0


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL {label}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# --- patch shape ---------------------------------------------------------------------------------------------------
header = read(ROOT / "tools/m17_frame_trace.h")
check(read(SDK / "include/rex/m17_frame_trace.h") == header, "installed m17_frame_trace.h equals tools/m17_frame_trace.h")
video = read(SDK / "src/kernel/xboxkrnl/xboxkrnl_video.cpp")
check(video.count("m17trace::Swap(") == 1, "one trace call, in the VdSwap export")
check(video.index("m17trace::Swap(") > video.index("void VdSwap_entry("), "the trace call is inside VdSwap")
check('std::getenv("R3HD_FRAME_TRACE")' in header and "if (!path || !*path) return nullptr;" in header,
      "the trace is off unless R3HD_FRAME_TRACE names a file")
check("ReadProcessMemory(self, guest_base + address" in header, "guest memory is read through ReadProcessMemory")
check(all(word not in header for word in ("WriteProcessMemory", "store_and_swap", "memcpy(guest", "Sleep(", "SetEvent")),
      "the trace writes no guest memory and does no waiting")
check("'R3HD_FRAME_TRACE', 'R3HD_VBLANK_SPIN_US'" in (ROOT / "tools/play.ps1").read_text(encoding="utf-8-sig"),
      "the launcher clears the trace variable for a person's session")

# --- pacing default (D-046) ----------------------------------------------------------------------------------------
vblank = read(ROOT / "tools/m16_vblank.h")
check('return !(e && !std::strcmp(e, "poll"));' in vblank, "deadline vblank delivery is the default; R3HD_VBLANK=poll is the pinned timing")
check(read(SDK / "include/rex/m16_vblank.h") == vblank, "installed m16_vblank.h equals tools/m16_vblank.h")
play = (ROOT / "tools/play.ps1").read_text(encoding="utf-8-sig")
check("[string]$Pacing = 'precise'" in play and "{ 'deadline' } else { 'poll' }" in play, "launcher default is precise, pinned is explicit")
scenarios = read(ROOT / "tools/m14_regression.py")
check('"death_reload": ("menu_10", "idle290.txt", 300' in scenarios, "death_reload waits long enough for a constant-step run")
check((ROOT / "config/m14/idle290.txt").is_file(), "config/m14/idle290.txt exists")
build = read(ROOT / "tools/build_milestone8.bat")
check(build.index("m16_runtime_patch.py") < build.index("m17_runtime_patch.py"), "the M17 patch replays after M16")
check("python tools\\m17_regression.py" in build, "the build runs this regression")


# --- timing checker on synthetic traces ----------------------------------------------------------------------------
def synthetic(path: Path, frames: int, jitter_ms: float, seed: int = 1) -> None:
    """A 60 Hz trace whose engine timer follows the title's filter (clamp below at 16 ms, mean of five, truncate)."""
    rng = random.Random(seed)
    frequency, ticks_per_ms = 10_000_000, 50_000
    out = [struct.pack("<IIQ", 0x54463352, 1, frequency)]
    remainder = total = previous_count = 0
    window = []
    for i in range(frames):
        t_ms = i * (1000.0 / 60.0) + rng.uniform(0.0, jitter_ms)
        count = int(t_ms * ticks_per_ms)
        elapsed = count - previous_count + remainder if i else 0
        delta, remainder = (elapsed // ticks_per_ms, elapsed % ticks_per_ms) if i else (0, 0)
        previous_count = count
        total += delta
        window = (window + [max(delta, 16)])[-5:]
        useful = sum(window) // len(window)
        block = bytearray(0x70)
        struct.pack_into(">IIII", block, 0, i + 1, 1, total, delta)
        struct.pack_into(">I", block, 0x50, useful)
        struct.pack_into(">f", block, 0x58, 1.0 / 60.0)
        struct.pack_into(">II", block, 0x5C, count & 0xFFFFFFFF, count >> 32)
        struct.pack_into(">I", block, 0x6C, ticks_per_ms)
        ranges = [(ft.ENGINE + 0x64, bytes(block)), (0x82BCE058, struct.pack(">I", i))]
        out.append(struct.pack("<IIIqQ", 0x4D415246, i, len(ranges), int(t_ms * frequency / 1000.0), count))
        for address, data in ranges:
            out.append(struct.pack("<II", address, len(data)) + data)
    path.write_bytes(b"".join(out))


WORK.mkdir(parents=True, exist_ok=True)
exact, jittered, short = WORK / "exact.trace", WORK / "jittered.trace", WORK / "short.trace"
synthetic(exact, 3000, 0.05)
synthetic(jittered, 3000, 2.0)
synthetic(short, 300, 0.05)
summary = ft.timer_summary(exact)
check(set(summary["delta_ms"]) <= {16, 17} and summary["useful_ms"] == {16: summary["regular_steps"]},
      "exact 60 Hz: measured 16 / 17 ms, step 16 ms on every frame")
check(abs(summary["simulated_per_wall"] - 0.96) < 0.001, "exact 60 Hz: simulated time is 0.960 of wall time")
noisy = ft.timer_summary(jittered)
check(noisy["useful_ms"].get(17, 0) > 0.05 * noisy["regular_steps"] and noisy["simulated_per_wall"] > 0.9625,
      "per-frame lateness of 0..2 ms: 17 ms steps appear and simulated time runs faster")
cases = [("exact trace passes", exact, [], 0), ("jittered trace fails", jittered, [], 1),
         ("jittered trace is recorded with --expect poll", jittered, ["--expect", "poll"], 0),
         ("a short trace is not a pass", short, [], 1)]
for label, trace, argv, want in cases:
    done = subprocess.run([sys.executable, str(ROOT / "tools/m17_frame_trace.py"), "check", str(trace), *argv],
                          capture_output=True, text=True)
    check(done.returncode == want, f"timing checker: {label} -> exit {want} (got {done.returncode})")
stalled = WORK / "stalled.trace"
synthetic(stalled, 40, 0.05)
stalled.write_bytes(stalled.read_bytes())
ft_rows = ft.timer_summary(stalled, first_frame=38)
check(ft_rows.get("frames", 0) < 3 or ft_rows.get("regular_steps") == 0, "too few frames give a summary, not an exception")
done = subprocess.run([sys.executable, str(ROOT / "tools/m17_frame_trace.py"), "check", str(stalled), "--from-frame", "38"],
                      capture_output=True, text=True)
check(done.returncode == 1 and "Traceback" not in done.stderr, "timing checker: a trace without regular steps fails cleanly")
stalled.unlink()
truncated = WORK / "truncated.trace"
truncated.write_bytes(exact.read_bytes()[:-37])
check(len(list(ft.frames(truncated))) == 2999, "a trace cut inside its last record still reads the complete records")
ft.write_watch(WORK / "w.trace", ft.TIMER_WATCH)
check((WORK / "w.trace.watch").read_text().splitlines()[0] == "82C06284 70", "watch list format: hex address and length")
for tool in ("m17_frame_trace.py", "m17_combat_trace.py"):
    check(subprocess.run([sys.executable, "-m", "py_compile", str(ROOT / "tools" / tool)]).returncode == 0, f"{tool} compiles")
for path in (exact, jittered, short, truncated):
    path.unlink()

print(f"M17_REGRESSION {'PASS' if failures == 0 else 'FAIL'} checks={checks} failures={failures}")
sys.exit(0 if failures == 0 else 1)
