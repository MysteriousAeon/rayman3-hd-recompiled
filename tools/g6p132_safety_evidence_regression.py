#!/usr/bin/env python3
"""G6-P132 adversarial offline regression: hidden test safety gate, runtime_config metadata,
evidence-driven M22/M23 judges, and hardened E06D7363 origin classification.

Zero r3hd.exe game launches. Uses synthetic fixtures, C# preflight state machine matrix,
synthetic non-game stand-in executables, and retained G6-P128 / G6-P131 records.
"""
from __future__ import annotations

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
TOOLS = ROOT / "tools"
RUNNER = TOOLS / "run_milestone6.ps1"
PLAY = TOOLS / "play.ps1"
M6_RUNS = ROOT / "private" / "work" / "m6_runs"

sys.path.insert(0, str(TOOLS))
import m12_fault_classifier as fault_clf  # noqa: E402
import m12_save_entry as m12  # noqa: E402
from r3hd_run_metadata import load_run_metadata, validate_runtime_config  # noqa: E402

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


def build_sentinel_standin(out_exe: Path, sentinel_file: Path) -> bool:
    """Compile a minimal non-game stand-in exe with M23 marker that writes a sentinel file if launched."""
    out_exe.parent.mkdir(parents=True, exist_ok=True)
    src = out_exe.with_suffix(".cpp")
    escaped = str(sentinel_file).replace("\\", "\\\\")
    src.write_text(f'''
#include <cstdio>
#include <windows.h>
static volatile const char* kMarker = "M23 haptics policy={{}} physical_pad_drivers={{}}";
int main() {{
    if (!kMarker[0]) return 2;
    FILE* f = std::fopen("{escaped}", "w");
    if (f) {{ std::fputs("LAUNCHED\\n", f); std::fclose(f); }}
    Sleep(150);
    return 0;
}}
''', encoding="utf-8")
    p = subprocess.run(
        ["cmd", "/c", "tools\\devenv.bat", "clang++", "-std=c++17", "-O1", str(src), "-o", str(out_exe)],
        capture_output=True, text=True, cwd=str(ROOT), timeout=60,
    )
    return p.returncode == 0 and out_exe.is_file()


def make_valid_runtime_config(
    *,
    draw_trace: bool = False,
    audio_probe: bool = False,
    layer_coords: str = "original",
    layer_source: str = "default",
    iso_verified: bool = True,
    iso_source: str = "inherited",
) -> dict:
    return {
        "execution_mode": "unattended_hidden",
        "nonintrusive": True,
        "hidden_window": True,
        "audio_hidden_mute": True,
        "m22_draw_trace": {
            "enabled": draw_trace,
            "source": "R3HD_M22_DRAW_TRACE" if draw_trace else "unset",
        },
        "m22_audio_probe": {
            "enabled": audio_probe,
            "source": "R3HD_M22_AUDIO" if audio_probe else "unset",
        },
        "layer_coords": {
            "effective": layer_coords,
            "source": layer_source,
        },
        "desktop_isolation": {
            "requested": "isolated_non_input_desktop",
            "verified": iso_verified,
            "source": iso_source,
        },
        "bounded_capture": {
            "frame_request_enabled": True,
            "m5_capture_enabled": False,
            "max_readbacks": 8,
        },
    }


def test_safety_preflight_matrix() -> None:
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
$activeDefault = Make-Ctx $true $true 'Default' $true $true 'Default'
$validIsolated = Make-Ctx $true $false 'r3hd_m6_abc123' $true $true 'Default'
$unverifiableNoInput = Make-Ctx $true $false 'r3hd_m6_abc123' $false $false $null
$unverifiableIoTrue = Make-Ctx $true $true 'r3hd_m6_abc123' $true $true 'Default'
$unverifiableSameName = Make-Ctx $true $false 'Default' $true $true 'default'

$res = [ordered]@{{
    inherited_ok = [M6Focus]::EvaluateDesktopPreflight($validIsolated, $false, $false, 0, $null, $true, $true, $null)
    inherited_monitor_fail = [M6Focus]::EvaluateDesktopPreflight($validIsolated, $false, $false, 0, $null, $true, $false, 'hook failed')
    private_succeeds = [M6Focus]::EvaluateDesktopPreflight($activeDefault, $true, $true, 0, $validIsolated, $true, $true, $null)
    create_denied = [M6Focus]::EvaluateDesktopPreflight($activeDefault, $true, $false, 5, $null, $true, $false, $null)
    isolation_unverifiable_no_input = [M6Focus]::EvaluateDesktopPreflight($activeDefault, $true, $true, 0, $unverifiableNoInput, $true, $true, $null)
    isolation_unverifiable_io_true = [M6Focus]::EvaluateDesktopPreflight($activeDefault, $true, $true, 0, $unverifiableIoTrue, $true, $true, $null)
    isolation_unverifiable_same_name = [M6Focus]::EvaluateDesktopPreflight($activeDefault, $true, $true, 0, $unverifiableSameName, $true, $true, $null)
    isolation_unverifiable_no_winsta = [M6Focus]::EvaluateDesktopPreflight($activeDefault, $true, $true, 0, $validIsolated, $false, $true, $null)
    create_ok_attach_fails = [M6Focus]::EvaluateDesktopPreflight($activeDefault, $true, $true, 0, $validIsolated, $true, $false, 'SetThreadDesktop failed (Win32 error 5)')
    no_fg_fallback_nonnull = [M6Focus]::EvaluateBaseline([IntPtr]0x12345, $activeDefault)
    safe_close_zero = [M6Focus]::SafeCloseDesktop([IntPtr]::Zero)
    force_priv = [M6Focus]::PrepareIsolatedDesktop($validIsolated, $true)
}}
if ($res.force_priv.CreatedDesktopHandle -ne [IntPtr]::Zero) {{
    [void][M6Focus]::SafeCloseDesktop($res.force_priv.CreatedDesktopHandle)
}}
$child = [System.Diagnostics.Process]::Start('cmd.exe', '/c exit 42')
[void]$child.WaitForExit(5000)
[int]$nativeCode = -1
$gotExit = [M6Focus]::TryGetProcessExitCode($child.Handle, [ref]$nativeCode)
$child.Dispose()
$res.native_exit_ok = $gotExit
$res.native_exit_code = $nativeCode
$res.safe_close_handle_zero = [M6Focus]::SafeCloseHandle([IntPtr]::Zero)
$res | ConvertTo-Json -Depth 6
"""
    p = run_ps(ps_code)
    check(p.returncode == 0, f"safety: C# EvaluateDesktopPreflight matrix executes (rc={p.returncode})")
    if p.returncode != 0:
        print(p.stderr[:400])
        return
    r = json.loads(p.stdout)

    check(r["inherited_ok"]["Allowed"] is True and r["inherited_ok"]["Source"] == "inherited"
          and r["inherited_ok"]["SafetyStatus"] == "verified_isolated"
          and r["inherited_ok"]["DesktopIsolationVerified"] is True,
          "safety: inherited verified isolated desktop allowed")
    check(r["inherited_monitor_fail"]["Allowed"] is False
          and r["inherited_monitor_fail"]["SafetyStatus"] == "fail_closed_monitor_start_failed",
          "safety: inherited desktop fails closed if monitor start fails")
    check(r["private_succeeds"]["Allowed"] is True and r["private_succeeds"]["Source"] == "created_private"
          and r["private_succeeds"]["SafetyStatus"] == "verified_isolated"
          and r["private_succeeds"]["DesktopIsolationVerified"] is True,
          "safety: private desktop succeeds before launch")
    check(r["create_denied"]["Allowed"] is False
          and r["create_denied"]["SafetyStatus"] == "fail_closed_desktop_create_denied"
          and r["create_denied"]["LastWin32Error"] == 5
          and r["create_denied"]["DesktopIsolationVerified"] is False,
          "safety: desktop creation denied fails closed with Win32 error")
    for k in ("isolation_unverifiable_no_input", "isolation_unverifiable_io_true",
              "isolation_unverifiable_same_name", "isolation_unverifiable_no_winsta"):
        check(r[k]["Allowed"] is False
              and r[k]["SafetyStatus"] == "fail_closed_isolation_unverifiable"
              and r[k]["DesktopIsolationVerified"] is False,
              f"safety: isolation unverifiable fails closed ({k})")
    check(r["create_ok_attach_fails"]["Allowed"] is False
          and r["create_ok_attach_fails"]["SafetyStatus"] == "fail_closed_desktop_attach_failed"
          and r["create_ok_attach_fails"]["DesktopIsolationVerified"] is False
          and "SetThreadDesktop" in (r["create_ok_attach_fails"]["RejectReason"] or ""),
          "safety: desktop creation succeeds but attachment fails -> fail closed")
    check(r["no_fg_fallback_nonnull"]["Allowed"] is False
          and r["no_fg_fallback_nonnull"]["Mode"] == "rejected"
          and r["no_fg_fallback_nonnull"]["DesktopIsolationVerified"] is False,
          "safety: no fallback to foreground desktop even when HWND != 0")
    check(r["safe_close_zero"] is True, "safety: SafeCloseDesktop(IntPtr.Zero) is a clean no-op")
    fp = r["force_priv"]
    check(fp["Source"] != "inherited",
          f"safety: ForcePrivateDesktop never falls back to inherited (got {fp['Source']!r})")
    if fp["Allowed"]:
        check(fp["Source"] == "created_private" and fp["SafetyStatus"] == "verified_isolated"
              and fp["DesktopIsolationVerified"] is True,
              "safety: ForcePrivateDesktop succeeds only as verified created_private")
    else:
        check(fp["SafetyStatus"] == "fail_closed_desktop_create_denied"
              and fp["DesktopIsolationVerified"] is False and fp["Source"] == "none",
              f"safety: ForcePrivateDesktop fails closed when CreateDesktopW denied (got {fp['SafetyStatus']!r})")
    check(r["native_exit_ok"] is True and r["native_exit_code"] == 42,
          f"safety: TryGetProcessExitCode recovers exact non-zero exit code (ok={r['native_exit_ok']}, code={r['native_exit_code']})")
    check(r["safe_close_handle_zero"] is True, "safety: SafeCloseHandle(IntPtr.Zero) is a clean no-op")


def test_safety_preflight_blocks_launch_and_env_sanitization() -> None:
    tag = uuid.uuid4().hex[:8]
    with tempfile.TemporaryDirectory(dir=ROOT / "private" / "work") as tmp:
        tdir = Path(tmp)
        standin = tdir / "r3hd_sentinel.exe"
        sentinel = tdir / "was_launched.txt"
        ok = build_sentinel_standin(standin, sentinel)
        check(ok, "safety-e2e: compile sentinel non-game stand-in")
        if not ok:
            return
        rn = f"g6p132_preflight_{tag}"
        run_dir = M6_RUNS / rn
        try:
            env = os.environ.copy()
            env["R3HD_EXE"] = str(standin)
            env["R3HD_M22_DRAW_TRACE"] = "1"
            env["R3HD_LAYER_COORDS"] = "original"
            env["R3HD_WATER_LAYERS"] = "separate"  # R3HD_LAYER_COORDS must take precedence!
            env["R3HD_SECRET_CANARY_TOKEN"] = "TOP_SECRET_CANARY_98765"
            env["API_KEY"] = "SHOULD_NEVER_LEAK_XYZ"
            p = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER),
                 "-Run", rn, "-Seconds", "5", "-Schedule", "config/m5/idle.txt"],
                capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=30,
            )
            rj_text = (run_dir / "run.json").read_text(encoding="utf-8-sig")
            rj = json.loads(rj_text)

            # Verify no sensitive env leakage regardless of whether sandbox denied desktop or isolated desktop succeeded.
            check("TOP_SECRET_CANARY_98765" not in rj_text and "R3HD_SECRET_CANARY_TOKEN" not in rj_text
                  and "SHOULD_NEVER_LEAK_XYZ" not in rj_text and "API_KEY" not in rj_text,
                  "metadata: zero sensitive environment leakage in run.json")

            # Verify runtime_config schema & effective env precedence.
            state, _, rc, err = load_run_metadata(run_dir)
            check(state == "valid" and rc is not None, f"metadata: runner emits valid runtime_config ({err})")
            if rc is not None:
                check(rc["m22_draw_trace"]["enabled"] is True and rc["m22_draw_trace"]["source"] == "R3HD_M22_DRAW_TRACE",
                      "metadata: captures R3HD_M22_DRAW_TRACE=1")
                check(rc["m22_audio_probe"]["enabled"] is False and rc["m22_audio_probe"]["source"] == "unset",
                      "metadata: captures unset R3HD_M22_AUDIO")
                check(rc["layer_coords"]["effective"] == "original" and rc["layer_coords"]["source"] == "R3HD_LAYER_COORDS",
                      "metadata: R3HD_LAYER_COORDS takes precedence over legacy R3HD_WATER_LAYERS")
                check(rc["bounded_capture"]["max_readbacks"] == 8
                      and rc["bounded_capture"]["m5_capture_enabled"] is False,
                      "metadata: bounded_capture normalized without private paths")

            if rj.get("safety_status") == "fail_closed_desktop_create_denied":
                check(p.returncode != 0, "safety-e2e: failed preflight exits non-zero")
                check(not sentinel.exists(), "safety-e2e: game/stand-in process creation NOT called after failed preflight")
                check(not (run_dir / "process.json").exists(), "safety-e2e: process.json absent after failed preflight")
                check(rj["exit_code"] is None and rj["desktop_isolation_verified"] is False
                      and rj["focus_baseline_mode"] == "rejected",
                      "safety-e2e: run.json records rejected preflight state")
            else:
                check(p.returncode == 0 and sentinel.exists()
                      and rj["safety_status"] == "verified_isolated"
                      and rj["desktop_isolation_verified"] is True,
                      "safety-e2e: verified isolated desktop launches stand-in cleanly")
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    # Verify explicit interactive workflow (tools/play.ps1 -DryRun) remains supported and untouched.
    p_play = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PLAY), "-DryRun"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=30,
    )
    check(p_play.returncode == 0, f"safety: explicit interactive play.ps1 -DryRun remains supported (rc={p_play.returncode})")


def test_runtime_config_helper_matrix() -> None:
    """Test Get-SanitizedRuntimeConfig directly across env combinations + schema validation edge cases."""
    ps_src = RUNNER.read_text(encoding="utf-8-sig")
    m = re.search(r"(function Get-SanitizedRuntimeConfig\(.*?\r?\n\})", ps_src, re.S)
    check(m is not None, "metadata: located Get-SanitizedRuntimeConfig in run_milestone6.ps1")
    if not m:
        return
    fn_code = m.group(1)
    ps_test = f"""
$ErrorActionPreference = 'Stop'
{fn_code}
$keys = @('R3HD_M22_DRAW_TRACE','R3HD_M22_AUDIO','R3HD_LAYER_COORDS','R3HD_WATER_LAYERS','R3HD_NONINTRUSIVE','R3HD_AUDIO_AUDIBLE','R3HD_M5_CAPTURE','R3HD_FRAME_REQUEST','SECRET_TOKEN')
$orig = @{{}}
foreach ($k in $keys) {{ $orig[$k] = [Environment]::GetEnvironmentVariable($k) }}
try {{
    foreach ($k in $keys) {{ [Environment]::SetEnvironmentVariable($k, $null) }}
    [Environment]::SetEnvironmentVariable('R3HD_NONINTRUSIVE', '1')
    [Environment]::SetEnvironmentVariable('R3HD_FRAME_REQUEST', 'C:\\private\\secret\\frame.request')
    [Environment]::SetEnvironmentVariable('SECRET_TOKEN', 'LEAK_CHECK_999')
    $c_default = Get-SanitizedRuntimeConfig $true 'inherited'

    [Environment]::SetEnvironmentVariable('R3HD_M22_DRAW_TRACE', '1')
    [Environment]::SetEnvironmentVariable('R3HD_M22_AUDIO', '1')
    [Environment]::SetEnvironmentVariable('R3HD_LAYER_COORDS', 'separate')
    $c_traced_sep = Get-SanitizedRuntimeConfig $true 'created_private'

    [Environment]::SetEnvironmentVariable('R3HD_LAYER_COORDS', $null)
    [Environment]::SetEnvironmentVariable('R3HD_WATER_LAYERS', 'separate')
    $c_legacy_wl = Get-SanitizedRuntimeConfig $true 'inherited'

    [Environment]::SetEnvironmentVariable('R3HD_LAYER_COORDS', 'untrusted_token_xyz')
    $c_precedence = Get-SanitizedRuntimeConfig $false 'none'

    [ordered]@{{
        c_default = $c_default
        c_traced_sep = $c_traced_sep
        c_legacy_wl = $c_legacy_wl
        c_precedence = $c_precedence
    }} | ConvertTo-Json -Depth 6
}} finally {{
    foreach ($k in $keys) {{ [Environment]::SetEnvironmentVariable($k, $orig[$k]) }}
}}
"""
    p = run_ps(ps_test)
    check(p.returncode == 0, f"metadata: Get-SanitizedRuntimeConfig matrix executes (rc={p.returncode})")
    if p.returncode != 0:
        print(p.stderr[:300])
        return
    check("LEAK_CHECK_999" not in p.stdout and "untrusted_token_xyz" not in p.stdout and "C:\\private\\secret" not in p.stdout,
          "metadata: no raw env strings, secrets, or private paths leaked")
    data = json.loads(p.stdout)
    check(data["c_default"]["m22_draw_trace"]["enabled"] is False
          and data["c_default"]["layer_coords"] == {"effective": "original", "source": "default"}
          and data["c_default"]["audio_hidden_mute"] is True,
          "metadata: default env snapshot accurate")
    check(data["c_traced_sep"]["m22_draw_trace"]["enabled"] is True
          and data["c_traced_sep"]["m22_audio_probe"]["enabled"] is True
          and data["c_traced_sep"]["layer_coords"] == {"effective": "separate", "source": "R3HD_LAYER_COORDS"}
          and data["c_traced_sep"]["desktop_isolation"]["source"] == "created_private",
          "metadata: traced + separate + created_private snapshot accurate")
    check(data["c_legacy_wl"]["layer_coords"] == {"effective": "separate", "source": "R3HD_WATER_LAYERS"},
          "metadata: legacy R3HD_WATER_LAYERS=separate recognized when R3HD_LAYER_COORDS unset")
    check(data["c_precedence"]["layer_coords"] == {"effective": "original", "source": "R3HD_LAYER_COORDS"}
          and data["c_precedence"]["desktop_isolation"]["verified"] is False,
          "metadata: R3HD_LAYER_COORDS overrides R3HD_WATER_LAYERS and normalizes unknown value to original")

    # Schema validator edge cases
    check(validate_runtime_config({"mode": "hidden-XAM"})[0] == "legacy", "metadata: legacy run.json without runtime_config")
    check(validate_runtime_config({"runtime_config_schema_version": 99, "runtime_config": {}})[0] == "malformed",
          "metadata: unsupported schema version fails closed as malformed")
    check(validate_runtime_config({"runtime_config_schema_version": 1})[0] == "malformed",
          "metadata: missing runtime_config payload fails closed as malformed")
    bad_rc = make_valid_runtime_config()
    bad_rc["layer_coords"]["effective"] = "bogus"
    check(validate_runtime_config({"runtime_config_schema_version": 1, "runtime_config": bad_rc})[0] == "malformed",
          "metadata: invalid layer_coords enum fails closed as malformed")


def _run_judge(script_name: str, run_name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / script_name), "--run", run_name],
        capture_output=True, text=True, cwd=str(ROOT), timeout=30,
    )


def test_m22_m23_classification() -> None:
    tag = uuid.uuid4().hex[:8]
    created: list[Path] = []

    def make_run(suffix: str, *, log: str, meta: dict | str | None, files: list[str] = ()) -> str:
        rn = f"g6p132_{tag}_{suffix}"
        d = M6_RUNS / rn
        d.mkdir(parents=True, exist_ok=True)
        created.append(d)
        (d / "runtime.log").write_text(log, encoding="utf-8")
        if isinstance(meta, dict):
            (d / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        elif isinstance(meta, str):
            (d / "run.json").write_text(meta, encoding="utf-8")
        for fn in files:
            (d / fn).write_bytes(b"synthetic")
        return rn

    try:
        base_log = "M22 audio hidden_mute=1\nM23 layer_coords=original\n"
        sep_log = "M22 audio hidden_mute=1\nM23 layer_coords=separate\n"
        sep_pair_log = "M22 audio hidden_mute=1\nM23 layer_coords=separate\nM23 layer_coords pair=corrected\n"
        audible_log = "M22 audio hidden_mute=0\nM23 layer_coords=original\n"

        # 1. Valid traced diagnostic run with arbitrary directory name -> M22 PASS
        rn = make_run("arbitrary_diag", log=base_log,
                      meta={"safety_status": "verified_isolated", "runtime_config_schema_version": 1,
                            "runtime_config": make_valid_runtime_config(draw_trace=True)},
                      files=["m3_frame_00001.bmp", "m22_draws_00001.bin"])
        check(_run_judge("m22_regression.py", rn).returncode == 0,
              "m22: valid traced diagnostic run with arbitrary directory name PASS")

        # 2. Trace absent when explicitly required -> M22 FAIL
        rn = make_run("missing_trace", log=base_log,
                      meta={"safety_status": "verified_isolated", "runtime_config_schema_version": 1,
                            "runtime_config": make_valid_runtime_config(draw_trace=True)},
                      files=["m3_frame_00001.bmp"])
        check(_run_judge("m22_regression.py", rn).returncode != 0,
              "m22: trace absent when explicitly required FAIL")

        # 3. Trace unexpectedly present when explicitly disabled (even with *_trace suffix!) -> M22 FAIL
        rn = make_run("disabled_but_named_trace", log=base_log,
                      meta={"safety_status": "verified_isolated", "runtime_config_schema_version": 1,
                            "runtime_config": make_valid_runtime_config(draw_trace=False)},
                      files=["m3_frame_00001.bmp", "m22_draws_00001.bin"])
        check(_run_judge("m22_regression.py", rn).returncode != 0,
              "m22: trace unexpectedly present when explicitly disabled FAIL (overrides *_trace suffix)")

        # 4. Genuine audio failure remains a failure -> M22 FAIL
        rn = make_run("audible_fail", log=audible_log,
                      meta={"safety_status": "verified_isolated", "runtime_config_schema_version": 1,
                            "runtime_config": make_valid_runtime_config(draw_trace=False)})
        check(_run_judge("m22_regression.py", rn).returncode != 0,
              "m22: genuine hidden_mute=0 audio failure remains FAIL")

        # 5. Safety failure in run.json remains a failure -> M22 FAIL & M23 FAIL
        rn = make_run("safety_fail", log=base_log,
                      meta={"safety_status": "fail_closed_game_foreground", "runtime_config_schema_version": 1,
                            "runtime_config": make_valid_runtime_config(iso_verified=False)})
        check(_run_judge("m22_regression.py", rn).returncode != 0, "m22: safety failure remains FAIL")
        check(_run_judge("m23_regression.py", rn).returncode != 0, "m23: safety failure remains FAIL")

        # 6. Malformed run.json metadata -> M22 FAIL & M23 FAIL
        rn = make_run("malformed_json", log=base_log, meta="{not valid json")
        check(_run_judge("m22_regression.py", rn).returncode != 0, "m22: malformed run.json fails closed")
        check(_run_judge("m23_regression.py", rn).returncode != 0, "m23: malformed run.json fails closed")

        # 7. Legitimate HD+ layer_coords=separate with arbitrary directory name (non-water level, pair=[]) -> M23 PASS
        rn = make_run("hdplus_menu00", log=sep_log,
                      meta={"safety_status": "verified_isolated", "runtime_config_schema_version": 1,
                            "runtime_config": make_valid_runtime_config(layer_coords="separate", layer_source="R3HD_LAYER_COORDS")})
        check(_run_judge("m23_regression.py", rn).returncode == 0,
              "m23: legitimate HD+ layer_coords=separate with arbitrary name PASS")

        # 8. Wrong layer-coordinate result -> M23 FAIL (both directions)
        rn = make_run("wrong_lc_orig", log=base_log,
                      meta={"safety_status": "verified_isolated", "runtime_config_schema_version": 1,
                            "runtime_config": make_valid_runtime_config(layer_coords="separate", layer_source="R3HD_LAYER_COORDS")})
        check(_run_judge("m23_regression.py", rn).returncode != 0,
              "m23: expected separate but logged original FAIL")

        rn = make_run("wrong_lc_sep", log=sep_log,
                      meta={"safety_status": "verified_isolated", "runtime_config_schema_version": 1,
                            "runtime_config": make_valid_runtime_config(layer_coords="original", layer_source="default")})
        check(_run_judge("m23_regression.py", rn).returncode != 0,
              "m23: expected original but logged separate FAIL")

        # 9. Legacy naming compatibility (run.json without runtime_config)
        rn_leg_trace = make_run("legacy_trace", log=base_log, meta={"mode": "hidden-XAM"},
                                files=["m3_frame_00001.bmp", "m22_draws_00001.bin"])
        rn_leg_plain = make_run("legacy_plain", log=base_log, meta={"mode": "hidden-XAM"},
                                files=["m3_frame_00001.bmp", "m22_draws_00001.bin"])
        rn_leg_sep = make_run("legacy_separate", log=sep_pair_log, meta={"mode": "hidden-XAM"})
        check(_run_judge("m22_regression.py", rn_leg_trace).returncode == 0, "m22: legacy *_trace naming preserved")
        check(_run_judge("m22_regression.py", rn_leg_plain).returncode != 0, "m22: legacy non-trace with trace still FAIL")
        check(_run_judge("m23_regression.py", rn_leg_sep).returncode == 0, "m23: legacy *_separate naming preserved")
    finally:
        for d in created:
            shutil.rmtree(d, ignore_errors=True)


HOST_TEXTINPUT_RECORD = """\
M2 exception code=E06D7363 host_pc=00007FFDC712569A last_entered_function=host lr=00000000 indirect=00000000 sp=00000000 fault_address=00000068FE7FDB58
M2 exception_location module=C:\\WINDOWS\\System32\\KERNELBASE.dll offset=C569A
M2 stack 0 module=C:\\Test\\r3hd.exe offset=2928898
M2 stack 1 module=C:\\WINDOWS\\SYSTEM32\\ntdll.dll offset=C6DF6
M2 stack 2 module=C:\\WINDOWS\\SYSTEM32\\ntdll.dll offset=C6595
M2 stack 3 module=C:\\WINDOWS\\SYSTEM32\\ntdll.dll offset=19F3D
M2 stack 4 module=C:\\WINDOWS\\System32\\KERNELBASE.dll offset=C569A
M2 stack 5 module=C:\\WINDOWS\\System32\\ucrtbase.dll offset=AE836
M2 stack 6 module=C:\\Windows\\System32\\CoreMessaging.dll offset=6DB28
M2 stack 7 module=C:\\WINDOWS\\SYSTEM32\\CoreUIComponents.dll offset=18563
M2 stack 8 module=C:\\WINDOWS\\System32\\Windows.UI.Core.TextInput.dll offset=112FC
M2 stack 9 module=C:\\WINDOWS\\System32\\InputSwitch.dll offset=361D
"""


def test_exception_classification() -> None:
    # 1. Positively identified handled host TextInput exception
    r = fault_clf.classify_fault_log_text(HOST_TEXTINPUT_RECORD, run_clean_handled=True)
    check(r["host_handled_textinput_count"] == 1 and r["guest_or_unknown_count"] == 0
          and r["actionable"] is False and r["raw_codes"] == {"E06D7363": 1},
          "exc: positively identified handled host TextInput E06D7363 -> HOST_HANDLED_TEXTINPUT")

    # 2. Same record when run did NOT exit cleanly (missing handling proof) -> GUEST_OR_UNKNOWN
    r = fault_clf.classify_fault_log_text(HOST_TEXTINPUT_RECORD, run_clean_handled=False)
    check(r["guest_or_unknown_count"] == 1 and r["host_handled_textinput_count"] == 0 and r["actionable"] is True,
          "exc: E06D7363 without clean run handling context -> GUEST_OR_UNKNOWN (actionable)")

    # 3. Guest-origin E06D7363 (guest function + non-zero lr/sp + r3hd.exe in frame 6)
    guest_rec = HOST_TEXTINPUT_RECORD.replace("last_entered_function=host", "last_entered_function=sub_820F4F28")
    r = fault_clf.classify_fault_log_text(guest_rec, run_clean_handled=True)
    check(r["guest_or_unknown_count"] == 1 and r["actionable"] is True and r["raw_codes"] == {"E06D7363": 1},
          "exc: guest-origin E06D7363 (last_entered_function!=host) -> GUEST_OR_UNKNOWN")

    guest_reg = HOST_TEXTINPUT_RECORD.replace("lr=00000000", "lr=820F4F28")
    r = fault_clf.classify_fault_log_text(guest_reg, run_clean_handled=True)
    check(r["guest_or_unknown_count"] == 1 and r["actionable"] is True,
          "exc: guest-origin E06D7363 (non-zero lr) -> GUEST_OR_UNKNOWN")

    r3hd_deep = HOST_TEXTINPUT_RECORD.replace("C:\\WINDOWS\\System32\\InputSwitch.dll", "C:\\Test\\r3hd.exe")
    r = fault_clf.classify_fault_log_text(r3hd_deep, run_clean_handled=True)
    check(r["guest_or_unknown_count"] == 1 and r["actionable"] is True,
          "exc: r3hd.exe in stack frame >= 1 -> GUEST_OR_UNKNOWN")

    # 4. Unknown-module E06D7363 & non-System32 spoofed DLL
    unk_mod = HOST_TEXTINPUT_RECORD.replace("InputSwitch.dll", "unknown_hook.dll")
    r = fault_clf.classify_fault_log_text(unk_mod, run_clean_handled=True)
    check(r["guest_or_unknown_count"] == 1 and r["actionable"] is True,
          "exc: unknown-module E06D7363 -> GUEST_OR_UNKNOWN")

    spoof_path = HOST_TEXTINPUT_RECORD.replace("C:\\WINDOWS\\System32\\Windows.UI.Core.TextInput.dll",
                                               "C:\\Temp\\Windows.UI.Core.TextInput.dll")
    r = fault_clf.classify_fault_log_text(spoof_path, run_clean_handled=True)
    check(r["guest_or_unknown_count"] == 1 and r["actionable"] is True,
          "exc: non-System32 TextInput path -> GUEST_OR_UNKNOWN")

    # 5. Missing stack / missing exception_location evidence
    no_stack = "\n".join(HOST_TEXTINPUT_RECORD.splitlines()[:2]) + "\n"
    r = fault_clf.classify_fault_log_text(no_stack, run_clean_handled=True)
    check(r["guest_or_unknown_count"] == 1 and r["actionable"] is True,
          "exc: missing stack evidence -> GUEST_OR_UNKNOWN")

    no_loc = "\n".join([HOST_TEXTINPUT_RECORD.splitlines()[0]] + HOST_TEXTINPUT_RECORD.splitlines()[2:]) + "\n"
    r = fault_clf.classify_fault_log_text(no_loc, run_clean_handled=True)
    check(r["guest_or_unknown_count"] == 1 and r["actionable"] is True,
          "exc: missing exception_location -> GUEST_OR_UNKNOWN")

    # 6. Malformed record
    malformed_log = "M2 exception code=E06D7363 TRUNCATED_GARBAGE\n"
    r = fault_clf.classify_fault_log_text(malformed_log, run_clean_handled=True)
    check(r["guest_or_unknown_count"] == 1 and r["actionable"] is True and bool(r["malformed_lines"]),
          "exc: malformed record fails closed as GUEST_OR_UNKNOWN")

    # 7. Other fatal exceptions (C0000005, DEADC0DE) + routine exceptions (406D1388)
    fatal_log = (
        "M2 exception code=C0000005 host_pc=00007FF600001234 last_entered_function=sub_82001000 "
        "lr=82001004 indirect=00000000 sp=70001000 fault_address=0000000000000000\n"
        "M2 exception code=406D1388 host_pc=00007FFDC712569A last_entered_function=host "
        "lr=00000000 indirect=00000000 sp=00000000 fault_address=0000000000000000\n"
    )
    r = fault_clf.classify_fault_log_text(fatal_log, run_clean_handled=True)
    check(r["categories"]["OTHER_EXCEPTION"] == 2
          and r["actionable_other_codes"] == {"C0000005": 1}
          and r["routine_other_codes"] == {"406D1388": 1}
          and r["actionable"] is True,
          "exc: C0000005 actionable OTHER_EXCEPTION, 406D1388 routine")

    # 8. Mixed host and guest E06D7363 records -> raw count preserved AND actionable FAIL!
    mixed = HOST_TEXTINPUT_RECORD + HOST_TEXTINPUT_RECORD + guest_rec
    r = fault_clf.classify_fault_log_text(mixed, run_clean_handled=True)
    check(r["raw_codes"] == {"E06D7363": 3}
          and r["host_handled_textinput_count"] == 2
          and r["guest_or_unknown_count"] == 1
          and r["actionable"] is True,
          "exc: mixed host + guest records preserve raw count (3) and remain actionable FAIL")

    # 9. Safety failure survives exit_code=0 in m12.evaluate_run
    tag = uuid.uuid4().hex[:8]
    rn = f"g6p132_m12_safety_{tag}"
    d = M6_RUNS / rn
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / "run.json").write_text(json.dumps({
            "exit_code": 0, "forced_termination": False, "error": None,
            "game_foreground_events": 0, "game_foreground_samples": 0,
            "desktop_became_active": False, "safety_status": "fail_closed_desktop_became_active",
        }), encoding="utf-8")
        (d / "runtime.log").write_text("vfs_open path=C:\\x\\knaar_30\\knaar_30.lvl result=00000000\n", encoding="utf-8")
        facts = m12.evaluate_run(rn, "knaar_30", None)
        check(any("safety_status=fail_closed_desktop_became_active" in x for x in facts["reasons"]),
              "safety: m12.evaluate_run fails on non-verified safety_status even when exit_code == 0")
    finally:
        shutil.rmtree(d, ignore_errors=True)

    # 10. Retained G6-P131 & G6-P128 m2_faults.log real-world verification
    retained_isolated = [
        "g6p62_g6p131a_load_knaar_30",
        "g6p62_g6p131b_load_knaar_60",
        "g6p62_g6p131b_load_fact_40",
        "g6p62_g6p131b_load_tower_10",
        "g6p62_g6p131b_load_lept_15",
        "g6p62_g6p131b_finished_tower_revisit",
        "g6p128_menu00_vanilla",
    ]
    for name in retained_isolated:
        rdir = M6_RUNS / name
        if (rdir / "m2_faults.log").is_file():
            res = fault_clf.classify_fault_log(rdir, run_clean_handled=True)
            check(res["host_handled_textinput_count"] > 0
                  and res["host_handled_textinput_count"] == res["raw_codes"].get("E06D7363", 0)
                  and res["guest_or_unknown_count"] == 0
                  and res["actionable"] is False,
                  f"exc-retained: {name} all E06D7363 ({res['raw_codes'].get('E06D7363', 0)}) -> HOST_HANDLED_TEXTINPUT")

    # Retained sandbox unsafe attempt (has 40010006, 0 E06D7363) must remain actionable OTHER_EXCEPTION!
    sdir = M6_RUNS / "g6p62_g6p131s_load_knaar_30"
    if (sdir / "m2_faults.log").is_file():
        res = fault_clf.classify_fault_log(sdir, run_clean_handled=True)
        check(res["actionable"] is True and res["actionable_other_codes"] == {"40010006": 2}
              and res["host_handled_textinput_count"] == 0,
              "exc-retained: g6p62_g6p131s_load_knaar_30 40010006x2 remains actionable OTHER_EXCEPTION")


def main() -> int:
    test_safety_preflight_matrix()
    test_safety_preflight_blocks_launch_and_env_sanitization()
    test_runtime_config_helper_matrix()
    test_m22_m23_classification()
    test_exception_classification()
    print(f"G6P132_SAFETY_EVIDENCE_REGRESSION {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
