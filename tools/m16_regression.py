"""Deterministic M16 checks (D-043 vblank delivery, D-044 achievements entry, D-045 save keeper). Starts no game.

Part of the build. It verifies that the SDK tree carries the M16 patch in the shape the decisions describe, that
the launcher keeps profile snapshots through the tested helper, and that the two log / capture analysers give the
expected verdicts on synthetic input. The behaviour itself is measured by hidden runs:
  python tools/m12_save_entry.py smoke NAME RUN --idle 60 ; python tools/m16_pacing_check.py private/work/m6_runs/RUN
  python tools/m9_license_run.py RUN config/m16/achievements_ui.txt --license-mask 1 --seconds 120 --user-root RUN --play
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
checks = failures = 0


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL: {label}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# --- D-043: vblank delivery -------------------------------------------------------------------------------------
gs = read(SDK / "src/graphics/graphics_system.cpp")
cp = read(SDK / "src/graphics/command_processor.cpp")
header = read(SDK / "include/rex/m16_vblank.h")
check(read(ROOT / "tools/m16_vblank.h") == header, "installed m16_vblank.h equals tools/m16_vblank.h")
check(gs.count("m16vb::WaitForDeadline(") == 1, "vblank worker waits for the deadline")
check(gs.count("m16vb::Late(") == 1, "vblank lateness is recorded")
check(gs.count("m16vb::SignalVblank();") == 1, "vblank is signalled once")
check(gs.index("MarkVblank();\n            m16vb::SignalVblank();") > 0 if "MarkVblank();\n            m16vb::SignalVblank();" in gs
      else False, "the signal follows the interrupt delivery")
check("if (m16vb::Precise() && REXCVAR_GET(vsync))" in gs, "deadline wait only with guest vsync and when selected")
check(gs.count("rex::thread::Sleep(std::chrono::milliseconds(1));") >= 1, "the pinned 1 ms polling sleep is kept as the fallback")
check("last_frame_time += interval_ticks;" in gs and "uint64_t(double(guest_tick_frequency) / refresh_rate_hz)" in gs,
      "the vblank schedule is the pinned one")
check(cp.count("m16vb::RegisterWait(wait, is_memory, poll_reg_addr)") == 1, "register wait ends on a vblank")
check("if (!m16vb::RegisterWait(wait, is_memory, poll_reg_addr)) {\n            rex::thread::Sleep(std::chrono::milliseconds(wait / 0x100));"
      in cp, "the pinned register-wait sleep is kept as the fallback")
check("WaitForSingleObject(VblankEvent(), wait / 0x100)" in header, "the register wait keeps the packet's own time limit")
check('std::getenv("R3HD_VBLANK")' in header and 'return !(e && !std::strcmp(e, "poll"));' in header,
      "the deadline wait is the default since M17 (D-046); R3HD_VBLANK=poll selects the pinned sleeps")
check("TranslateVirtual" not in header and "memory" not in header.replace("is_memory", "").replace("memory={}", "").replace("memory word", ""),
      "the vblank header touches no guest memory")
pacing = read(SDK / "include/rex/m11_frame_pacing.h")
check(read(ROOT / "tools/m11_frame_pacing.h") == pacing, "installed m11_frame_pacing.h equals tools/m11_frame_pacing.h")
check("core_sd_us={} lag1_milli={}" in pacing, "pacing lines carry the jitter fields")

# --- D-044: achievements entry ---------------------------------------------------------------------------------
ui = read(SDK / "src/kernel/xam/xam_ui.cpp")
xi = read(SDK / "src/kernel/xam/xam_input.cpp")
gate = read(SDK / "include/rex/m16_sysui.h")
check(read(ROOT / "tools/m16_sysui.h") == gate, "installed m16_sysui.h equals tools/m16_sysui.h")
check("REX_EXPORT_STUB(__imp__XamShowAchievementsUI);" not in ui, "XamShowAchievementsUI is no longer a stub")
check(ui.count("REX_EXPORT(__imp__XamShowAchievementsUI, rex::kernel::xam::XamShowAchievementsUI_entry)") == 1,
      "XamShowAchievementsUI is exported once")
for other in ("XamShowAchievementDetailsUI", "XamShowAchievementsUIEx", "XamShowNuiAchievementsUI"):
    check(f"REX_EXPORT_STUB(__imp__{other});" in ui, f"{other} stays a stub (not imported behaviour, not invented)")
body = ui[ui.index("class M16AchievementsDialog"):ui.index("u32 XamShowPartyUI_entry")]
check("rex::ui::AchievementsOverlayDialog" in body, "the dialog is the runtime's existing achievements overlay")
check("UnlockAchievement" not in body and "SaveUnlockState" not in body and "RegisterAchievement" not in body,
      "the entry never unlocks, registers or writes an achievement")
check(body.count("BroadcastNotification(0x9, true)") == 1 and body.count("BroadcastNotification(0x9, false)") == 2,
      "XN_SYS_UI brackets the dialog")
check("REXCVAR_GET(headless)" in body, "headless runs show nothing")
check("return X_ERROR_SUCCESS;" in body and "X_ERROR_IO_PENDING" not in body, "the call returns at once")
check(xi.count("m16sysui::Filter(") == 2, "both pad sources pass the gate")
check(xi.count("m16sysui::IsOpen()") == 2, "both keystroke calls respect the gate")
check("input_state->gamepad = {};" in xi, "a hidden pad is neutral, the packet number is kept")
runner = read(ROOT / "tools/m16_runtime_patch.py")
check("Xbox Live" in runner and "license" not in runner.lower().replace("no xbox live, no entitlement", ""),
      "patch script states its limits and touches no licence setting")
steps = read(ROOT / "config/m16/achievements_ui.txt")
check(steps.rstrip().endswith("exit 30") and steps.count("press 42") == 2, "achievements scenario: two closes and a menu exit")

# --- D-045: save keeper ------------------------------------------------------------------------------------------
play = (ROOT / "tools/play.ps1").read_text(encoding="utf-8-sig")
keeper = (ROOT / "tools/play_savekeeper.ps1").read_text(encoding="utf-8-sig")
check(". (Join-Path $PSScriptRoot 'play_savekeeper.ps1')" in play, "launcher loads the save keeper")
check("[ValidateSet('pinned', 'precise')][string]$Pacing = 'precise'" in play, "launcher: pacing is precise unless -Pacing pinned (D-046)")
check("$env:R3HD_VBLANK = $(if ($Pacing -eq 'precise') { 'deadline' } else { 'poll' })" in play and "$env:R3HD_VBLANK = $savedVblank" in play,
      "launcher sets and restores the pacing switch")
check('save_history/$stamp' in play, "snapshots go to private/play/save_history/<session>")
check(play.count("Update-SaveKeeper $keeper") == 3, "snapshot before, during and after the session")
check("$process.WaitForExit(2000)" in play and "$process.WaitForExit()\n" in play.replace("\r\n", "\n"),
      "the launcher still waits for the game to end")
for verb in ("Remove-Item", "Move-Item", "Rename-Item", "Set-Content -LiteralPath $Keeper.UserRoot", "Clear-Content"):
    check(verb not in keeper, f"save keeper never uses {verb.split()[0]} on the profile")
check(keeper.count("Copy-Item") == 1 and "-Destination (Join-Path $dest 'user')" in keeper, "save keeper only copies out of the profile")
done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                       str(ROOT / "tools/m16_savekeeper_test.ps1")], cwd=ROOT, capture_output=True, text=True,
                      errors="replace", timeout=180)
check(done.returncode == 0 and "M16_SAVEKEEPER_TEST PASS" in done.stdout, "save keeper behaviour test")
ignore = read(ROOT / ".gitignore")
check(any(line.strip().rstrip("/") in ("private", "/private") for line in ignore.splitlines()), "private/ is ignored")

# --- analysers on synthetic input --------------------------------------------------------------------------------
def pacing_line(series, window, p50, p95, core_n, sd, lag):
    return (f"[t] M11 pacing series={series} window={window} n=600 mean_us={p50} min_us=14000 p50_us={p50} p95_us={p95} "
            f"p99_us={p95 + 300} max_us={p95 + 900} over_20ms=0 over_33ms=0 over_50ms=0 over_100ms=0 core_n={core_n} "
            f"core_sd_us={sd} lag1_milli={lag}\n")


def vblank_line(mode, window, p95):
    return (f"[t] M16 vblank mode={mode} window={window} n=600 late_mean_us={p95 // 2} late_p50_us={p95 // 2} "
            f"late_p95_us={p95} late_p99_us={p95 + 50} late_max_us={p95 + 400} spin_us={600 if mode == 'deadline' else 0}\n")


good = "".join(vblank_line("deadline", w, 5) + pacing_line("guest_swap", w, 16666, 16750, 600, 70, -490)
               + pacing_line("host_present", w, 16668, 16820, 600, 125, -500) for w in range(1, 6))
movie = "".join(pacing_line("guest_swap", w, 33333, 35000, 600, 700, -400) + pacing_line("host_present", w, 33333, 35000, 600, 700, -400)
                for w in range(6, 9))
pinned = "".join(vblank_line("poll", w, 1010) + pacing_line("guest_swap", w, 16660, 17850, 598, 690, -470)
                 + pacing_line("host_present", w, 16665, 17900, 598, 700, -460) for w in range(1, 6))
regressed = good.replace("core_sd_us=70 ", "core_sd_us=640 ")
late = good.replace("late_p95_us=5 ", "late_p95_us=900 ")
cases = (
    ("deadline run with regular frames", good, [], 0),
    ("movie windows are left out", good + movie, [], 0),
    ("pinned polling measured as such", pinned, ["--expect", "poll"], 0),
    ("pinned polling fails the default limits", pinned, [], 1),
    ("deadline mode with jittered swaps fails", regressed, [], 1),
    ("late vblanks fail", late, [], 1),
    ("a log without pacing data is not a pass", "nothing\n", [], 2),
    ("one steady window is not enough", vblank_line("deadline", 1, 5) + pacing_line("guest_swap", 1, 16666, 16750, 600, 70, -490)
     + pacing_line("host_present", 1, 16668, 16820, 600, 125, -500), [], 2),
)
with tempfile.TemporaryDirectory() as temp:
    for index, (label, text, argv, want) in enumerate(cases):
        run = Path(temp) / f"case{index}"
        run.mkdir()
        (run / "runtime.log").write_text(text)
        done = subprocess.run([sys.executable, str(ROOT / "tools/m16_pacing_check.py"), str(run), *argv],
                              capture_output=True, text=True)
        check(done.returncode == want, f"pacing checker: {label} -> exit {want} (got {done.returncode})")

    # CapFrameX analyser: an exact 60 Hz schedule with an alternating +-0.6 ms error per interval
    n = 1200
    between = [16.6667 + (0.6 if i % 2 else -0.6) for i in range(n)]
    times = [sum(between[:i]) / 1000 for i in range(n)]
    capture = {"Info": {"CreationDate": "2026-01-01T00:00:20.0000000Z", "PresentationMode": "synthetic"},
               "Runs": [{"CaptureData": {"TimeInSeconds": times, "MsBetweenPresents": between,
                                         "MsBetweenDisplayChange": [16.6667] * n, "PresentMode": [8] * n,
                                         "SyncInterval": [0] * n, "AllowsTearing": [1] * n, "Dropped": [False] * n,
                                         "FrameType": ["Application"] * n}}]}
    source = Path(temp) / "capture.json"
    source.write_text(json.dumps(capture))
    out = Path(temp) / "stats.json"
    done = subprocess.run([sys.executable, str(ROOT / "tools/m16_capframex.py"), str(source), "--json", str(out)],
                          capture_output=True, text=True)
    check(done.returncode == 0 and out.is_file(), "capture analyser runs")
    stats = json.loads(out.read_text())[0] if out.is_file() else {}
    bp = stats.get("between_presents", {})
    bd = stats.get("between_display_change", {})
    check(stats.get("frames") == n and abs(stats.get("nominal_ms", 0) - 16.667) < 0.01, "capture analyser: frame count and 60 Hz nominal")
    check(abs(bp.get("core_sd", 0) - 0.6) < 0.01, "capture analyser: interval spread")
    check(bp.get("core_lag1_autocorr", 0) < -0.99 and bp.get("core_alternation_share", 0) > 0.99, "capture analyser: alternation pattern")
    check(bd.get("core_sd", 1) < 0.001 and bd.get("within_0.5ms") == 1.0, "capture analyser: regular displayed cadence")
    check(stats.get("present_mode") == {"Hardware Composed: Independent Flip": n}, "capture analyser: present mode names")
    check(stats.get("stall_clusters_over_25ms") == [], "capture analyser: no stall in a regular capture")
    check("16.6667" not in done.stdout.replace('"nominal_ms": 16.667', ""), "capture analyser prints statistics, not samples")

print(f"M16_REGRESSION {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures}")
sys.exit(1 if failures else 0)
