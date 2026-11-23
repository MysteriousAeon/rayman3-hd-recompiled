#!/usr/bin/env python3
"""G6-P99 offline regression: kernel-verified isolated non-input desktop focus baseline in run_milestone6.ps1.

Tests (no r3hd.exe game process launched):
  1. Source-level safety invariants in tools/run_milestone6.ps1 and tools/play.ps1.
  2. Direct execution of the exact M6Focus C# class from tools/run_milestone6.ps1 across positive and negative controls.
  3. Live Win32 desktop-context, IsThreadDesktopInputActive, and SetWinEventHook Start/Stop verification.
  4. Synthetic stand-in executable end-to-end tests of tools/run_milestone6.ps1:
     - Partial-initialization cleanup (missing M23 haptics marker fails closed, writes run.json, restores env).
     - Silent stand-in process exits 0 with hook/poll verified and zero game foreground events/samples.
     - On a verified isolated non-input desktop ONLY (UOI_IO=False), an activating stand-in process triggers
       NONINTRUSIVE FAILURE (game_foreground) and fails closed.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_milestone6.ps1"
LAUNCHER = ROOT / "tools" / "play.ps1"
M6_RUNS = ROOT / "private" / "work" / "m6_runs"
checks = failures = 0


def check(cond: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not cond:
        failures += 1
        print(f"FAIL {label}")


def run_ps(script: str, env: dict | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, env=env, timeout=timeout, cwd=str(ROOT),
    )


def extract_m6focus_csharp(text: str) -> str:
    m = re.search(r"Add-Type @'\r?\n(.*?)\r?\n'@", text, re.S)
    assert m, "Could not locate Add-Type C# block in tools/run_milestone6.ps1"
    return m.group(1)


def test_source_invariants() -> None:
    ps = RUNNER.read_text(encoding="utf-8-sig")
    play = LAUNCHER.read_text(encoding="utf-8-sig")

    check("exebox" not in ps.lower(), "runner never matches or trusts exebox desktop names")
    check("OpenInputDesktop(0, false, DESKTOP_READOBJECTS)" in ps, "runner opens input desktop read-only")
    check("CloseDesktop(inputDesk)" in ps and "finally" in ps, "runner closes input desktop handle in finally")
    check("UOI_IO = 6" in ps and "UOI_NAME = 2" in ps, "runner queries UOI_IO and UOI_NAME")
    check("!ctx.ThreadDesktopIo" in ps and "ctx.InputDesktopIo" in ps, "runner requires thread non-input and input active")
    check("OrdinalIgnoreCase" in ps and "!string.Equals(ctx.ThreadDesktopName, ctx.InputDesktopName" in ps,
          "runner requires distinct thread and input desktop names")
    check("IsThreadDesktopInputActive()" in ps and "desktop_became_active" in ps,
          "runner re-checks UOI_IO in 100 ms poll loop and fails closed if desktop becomes active")
    check("if (!TryGetDesktopInfo(threadDesk, out ioActive, out name)) return true;" in ps,
          "IsThreadDesktopInputActive fails closed on query error")
    check("SetWinEventHook(3, 3," in ps and "$gameFocusEvents -gt 0" in ps and "$gameFocusSamples -gt 0" in ps,
          "WinEvent hook and 100 ms game-foreground checks remain unconditionally active")
    check("$env:R3HD_NONINTRUSIVE = '1'" in ps and "ProcessWindowStyle]::Hidden" in ps,
          "non-intrusive hidden window mode unchanged (no visible fallback)")
    check("M23 haptics policy={} physical_pad_drivers={}" in ps, "M23 haptics preflight unchanged")
    check("isolated_non_input_desktop" not in play and "M6Focus" not in play,
          "normal human launcher play.ps1 untouched")


def test_csharp_matrix_and_live_win32() -> dict:
    cs = extract_m6focus_csharp(RUNNER.read_text(encoding="utf-8-sig"))
    ps_code = f"""
$ErrorActionPreference = 'Stop'
Add-Type @'
{cs}
'@
function Make-Ctx([bool]$tOk, [bool]$tIo, [string]$tName, [bool]$iOk, [bool]$iIo, [string]$iName) {{
    $c = New-Object M6DesktopContext
    $c.ThreadDesktopOk = $tOk
    $c.ThreadDesktopIo = $tIo
    $c.ThreadDesktopName = $tName
    $c.InputDesktopOk = $iOk
    $c.InputDesktopIo = $iIo
    $c.InputDesktopName = $iName
    return $c
}}
$zero = [IntPtr]::Zero
$hwnd = [IntPtr]0x12345
$cases = [ordered]@{{
    non_null_default = [M6Focus]::EvaluateBaseline($hwnd, (Make-Ctx $true $true 'Default' $true $true 'Default'))
    non_null_isolated = [M6Focus]::EvaluateBaseline($hwnd, (Make-Ctx $true $false 'priv_desk' $true $true 'Default'))
    null_active_default = [M6Focus]::EvaluateBaseline($zero, (Make-Ctx $true $true 'Default' $true $true 'Default'))
    null_exebox_name_but_io_true = [M6Focus]::EvaluateBaseline($zero, (Make-Ctx $true $true 'exebox-FAKE1234' $true $true 'Default'))
    null_input_desk_denied = [M6Focus]::EvaluateBaseline($zero, (Make-Ctx $true $false 'priv_desk' $false $false $null))
    null_input_desk_io_false = [M6Focus]::EvaluateBaseline($zero, (Make-Ctx $true $false 'priv_desk' $true $false 'Default'))
    null_same_desk_case_insensitive = [M6Focus]::EvaluateBaseline($zero, (Make-Ctx $true $false 'Default' $true $true 'default'))
    null_thread_desk_failed = [M6Focus]::EvaluateBaseline($zero, (Make-Ctx $false $false $null $true $true 'Default'))
    null_ctx_null = [M6Focus]::EvaluateBaseline($zero, $null)
    null_empty_name = [M6Focus]::EvaluateBaseline($zero, (Make-Ctx $true $false '' $true $true 'Default'))
    null_valid_isolated = [M6Focus]::EvaluateBaseline($zero, (Make-Ctx $true $false 'priv_desk' $true $true 'Default'))
}}
$liveCtx = [M6Focus]::QueryDesktopContext()
$liveFg = [M6Focus]::GetForegroundWindow()
$liveNullEval = [M6Focus]::EvaluateBaseline($zero, $liveCtx)
$liveRealEval = [M6Focus]::EvaluateBaseline($liveFg, $liveCtx)
$liveActive = [M6Focus]::IsThreadDesktopInputActive()
[M6Focus]::Start()
$hookReady = [M6Focus]::HookEverReady
$hookStop = [M6Focus]::Stop()
[ordered]@{{
    cases = $cases
    live = [ordered]@{{
        fg_is_zero = ($liveFg -eq $zero)
        thread_ok = $liveCtx.ThreadDesktopOk
        thread_io = $liveCtx.ThreadDesktopIo
        input_ok = $liveCtx.InputDesktopOk
        input_io = $liveCtx.InputDesktopIo
        names_differ = ($liveCtx.ThreadDesktopOk -and $liveCtx.InputDesktopOk -and -not [string]::Equals($liveCtx.ThreadDesktopName, $liveCtx.InputDesktopName, [System.StringComparison]::OrdinalIgnoreCase))
        is_active = $liveActive
        null_eval = $liveNullEval
        real_eval = $liveRealEval
        hook_ready = $hookReady
        hook_stop = $hookStop
    }}
}} | ConvertTo-Json -Depth 6
"""
    p = run_ps(ps_code)
    check(p.returncode == 0, f"M6Focus C# matrix executes cleanly (rc={p.returncode}, err={p.stderr.strip()[:200]})")
    if p.returncode != 0:
        return {}
    data = json.loads(p.stdout)
    c = data["cases"]

    check(c["non_null_default"]["Allowed"] is True and c["non_null_default"]["Mode"] == "foreground_window"
          and c["non_null_default"]["DesktopIsolationVerified"] is False,
          "non-NULL foreground on active Default -> foreground_window")
    check(c["non_null_isolated"]["Allowed"] is True and c["non_null_isolated"]["Mode"] == "foreground_window"
          and c["non_null_isolated"]["DesktopIsolationVerified"] is True,
          "non-NULL foreground on isolated desktop -> foreground_window + isolation verified")
    for neg in ("null_active_default", "null_exebox_name_but_io_true", "null_input_desk_denied",
                "null_input_desk_io_false", "null_same_desk_case_insensitive", "null_thread_desk_failed",
                "null_ctx_null", "null_empty_name"):
        check(c[neg]["Allowed"] is False and c[neg]["Mode"] == "rejected"
              and c[neg]["DesktopIsolationVerified"] is False
              and c[neg]["RejectReason"] == "No active application available for focus verification",
              f"negative control fails closed: {neg}")
    check(c["null_valid_isolated"]["Allowed"] is True
          and c["null_valid_isolated"]["Mode"] == "isolated_non_input_desktop"
          and c["null_valid_isolated"]["DesktopIsolationVerified"] is True
          and c["null_valid_isolated"]["RejectReason"] is None,
          "valid kernel-verified isolated non-input desktop -> isolated_non_input_desktop")

    live = data["live"]
    check(live["thread_ok"] is True, "live QueryDesktopContext reads thread desktop")
    check(live["hook_ready"] is True and live["hook_stop"] is True, "live SetWinEventHook starts and stops cleanly")
    if live["thread_io"]:
        check(live["is_active"] is True, "live active input desktop: IsThreadDesktopInputActive is True")
        check(live["null_eval"]["Allowed"] is False, "live active input desktop: NULL foreground fails closed")
        if not live["fg_is_zero"]:
            check(live["real_eval"]["Allowed"] is True and live["real_eval"]["Mode"] == "foreground_window",
                  "live active input desktop: real foreground window allowed")
    else:
        check(live["is_active"] is False, "live non-input desktop: IsThreadDesktopInputActive is False")
        if live["input_ok"] and live["input_io"] and live["names_differ"]:
            check(live["null_eval"]["Allowed"] is True
                  and live["null_eval"]["Mode"] == "isolated_non_input_desktop",
                  "live isolated non-input desktop: NULL foreground verified and allowed")
        else:
            check(live["null_eval"]["Allowed"] is False,
                  "live non-input desktop without verified distinct input desktop: fails closed")
    return live


def build_standin_exe(out_exe: Path, include_m23: bool, activate_window: bool) -> bool:
    out_exe.parent.mkdir(parents=True, exist_ok=True)
    marker = "M23 haptics policy={} physical_pad_drivers={}" if include_m23 else "NO_HAPTICS_MARKER"
    src = out_exe.with_suffix(".cpp")
    if activate_window:
        body = f'''
#include <windows.h>
static volatile const char* kMarker = "{marker}";
static LRESULT CALLBACK WndProc(HWND h, UINT m, WPARAM w, LPARAM l) {{
    if (m == WM_DESTROY) {{ PostQuitMessage(0); return 0; }}
    return DefWindowProcW(h, m, w, l);
}}
int main() {{
    if (!kMarker[0]) return 2;
    WNDCLASSW wc = {{}};
    wc.lpfnWndProc = WndProc;
    wc.hInstance = GetModuleHandleW(nullptr);
    wc.lpszClassName = L"G6P99SynthActivate";
    RegisterClassW(&wc);
    HWND h = CreateWindowExW(0, wc.lpszClassName, L"G6P99", WS_OVERLAPPEDWINDOW, 0, 0, 120, 80, nullptr, nullptr, wc.hInstance, nullptr);
    ShowWindow(h, SW_SHOWNORMAL);
    SetForegroundWindow(h);
    DWORD end = GetTickCount() + 600;
    MSG msg;
    while (GetTickCount() < end) {{
        while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {{ TranslateMessage(&msg); DispatchMessageW(&msg); }}
        Sleep(20);
    }}
    DestroyWindow(h);
    return 0;
}}
'''
    else:
        body = f'''
#include <windows.h>
static volatile const char* kMarker = "{marker}";
int main() {{
    if (!kMarker[0]) return 2;
    Sleep(350);
    return 0;
}}
'''
    src.write_text(body, encoding="utf-8")
    p = subprocess.run(
        ["cmd", "/c", "tools\\devenv.bat", "clang++", "-std=c++17", "-O1", str(src), "-o", str(out_exe), "-luser32"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=60,
    )
    if p.returncode != 0:
        print(f"build_standin_exe stderr: {p.stderr.strip()[-300:]}")
    return p.returncode == 0 and out_exe.is_file()


def test_runner_synthetic_e2e(live: dict) -> None:
    tag = uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory(dir=ROOT / "private" / "work") as tmp:
        tdir = Path(tmp)
        run_names = []
        try:
            # 1. Partial-initialization cleanup: binary missing M23 marker fails closed.
            no_m23 = tdir / "nom23" / "r3hd_synth_nom23.exe"
            ok = build_standin_exe(no_m23, include_m23=False, activate_window=False)
            check(ok, "compile synthetic stand-in without M23 marker")
            if ok:
                rn = f"g6p99_nom23_{tag}"
                run_names.append(rn)
                env = os.environ.copy()
                env["R3HD_EXE"] = str(no_m23)
                p = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER),
                     "-Run", rn, "-Seconds", "5", "-Schedule", "config/m5/idle.txt"],
                    capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=30,
                )
                rj = json.loads((M6_RUNS / rn / "run.json").read_text(encoding="utf-8-sig"))
                check(p.returncode != 0 and rj["exit_code"] is None and rj["error"] is not None
                      and "controller-vibration safeguard" in rj["error"]["message"],
                      "missing M23 marker fails closed before launch with run.json recorded")

            # 2. Clean silent stand-in exe with M23 marker passes cleanly.
            silent = tdir / "silent" / "r3hd_synth_silent.exe"
            ok = build_standin_exe(silent, include_m23=True, activate_window=False)
            check(ok, "compile synthetic silent stand-in with M23 marker")
            if ok:
                rn = f"g6p99_silent_{tag}"
                run_names.append(rn)
                env = os.environ.copy()
                env["R3HD_EXE"] = str(silent)
                p = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER),
                     "-Run", rn, "-Seconds", "5", "-Schedule", "config/m5/idle.txt"],
                    capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=30,
                )
                rj = json.loads((M6_RUNS / rn / "run.json").read_text(encoding="utf-8-sig"))
                expected_mode = "foreground_window" if not live.get("fg_is_zero") else "isolated_non_input_desktop"
                check(p.returncode == 0 and rj["exit_code"] == 0 and rj["error"] is None,
                      f"silent stand-in passes end-to-end (rc={p.returncode}, err={rj.get('error')})")
                check(rj["focus_baseline_mode"] == expected_mode,
                      f"focus_baseline_mode matches context ({rj.get('focus_baseline_mode')} == {expected_mode})")
                check(rj["game_foreground_events"] == 0 and rj["game_foreground_samples"] == 0
                      and rj["desktop_became_active"] is False and rj["monitor_hook_ready"] is True
                      and rj["monitor_stop_clean"] is True,
                      "silent stand-in records zero focus theft, clean hook stop, desktop inactive")

            # 3. Unexpected foreground activation negative control (ONLY on verified isolated non-input desktop).
            if live and not live.get("thread_io") and live.get("input_ok") and live.get("input_io") and live.get("names_differ"):
                act = tdir / "activate" / "r3hd_synth_activate.exe"
                ok = build_standin_exe(act, include_m23=True, activate_window=True)
                check(ok, "compile synthetic activating stand-in (isolated desktop only)")
                if ok:
                    rn = f"g6p99_activate_{tag}"
                    run_names.append(rn)
                    env = os.environ.copy()
                    env["R3HD_EXE"] = str(act)
                    p = subprocess.run(
                        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER),
                         "-Run", rn, "-Seconds", "5", "-Schedule", "config/m5/idle.txt"],
                        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=30,
                    )
                    rj = json.loads((M6_RUNS / rn / "run.json").read_text(encoding="utf-8-sig"))
                    check(p.returncode != 0 and rj["error"] is not None
                          and rj["error"]["kind"] == "game_foreground"
                          and (rj["game_foreground_events"] > 0 or rj["game_foreground_samples"] > 0),
                          f"isolated desktop catches unexpected foreground activation (events={rj.get('game_foreground_events')}, samples={rj.get('game_foreground_samples')})")
        finally:
            for rn in run_names:
                d = M6_RUNS / rn
                if d.exists():
                    shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    test_source_invariants()
    live = test_csharp_matrix_and_live_win32()
    test_runner_synthetic_e2e(live)
    status = "PASS" if failures == 0 else "FAIL"
    print(f"G6P99_FOCUS_BASELINE_REGRESSION {status} checks={checks} failures={failures}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
