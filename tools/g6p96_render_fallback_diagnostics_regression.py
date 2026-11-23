#!/usr/bin/env python3
"""G6-P96: offline regression for rendering-resolution fallback diagnostics.

Covers (without launching the game or any visible window):
- play.ps1 -Summarize (Get-LogCensus) parsing of M15 draw_scale across rotated logs,
  accepted scales, reduced/asymmetric scales, missing events, and malformed events;
- r3hd_installer.py support_report() formatting for accepted, refused/reduced, auto,
  manual, asymmetric, missing, and malformed draw_scale events;
- support-report redaction, raw-log non-copying, and compact size;
- unchanged normal launch / exit behavior and Settings last_session (LASTRUN) status.

Prints G6P96_RENDER_FALLBACK_DIAGNOSTICS_OK on success.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import r3hd_installer as eng  # noqa: E402

PS = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
PLAY_PS1 = TOOLS / "play.ps1"
failures = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f" [{detail}]" if detail and not cond else ""))
    if not cond:
        failures.append(name)


def run_summarize(session_dir: Path) -> dict:
    r = subprocess.run(
        [str(PS), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(PLAY_PS1), "-Summarize", str(session_dir)],
        capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if r.returncode != 0:
        raise RuntimeError(f"play.ps1 -Summarize failed ({r.returncode}): {r.stderr.strip()}")
    return json.loads(r.stdout)


def run_end_hook(home: Path, stamp: str, scale: int, opt: str, draw_scale_ps: str) -> subprocess.CompletedProcess:
    text = PLAY_PS1.read_text(encoding="utf-8")
    start = text.index("# G6-P46 (D-302)")
    end = text.rindex("exit $(if ($exitCode -eq 0) { 0 } else { 1 })")
    block = text[start:end] + "exit $(if ($exitCode -eq 0) { 0 } else { 1 })\r\n"
    harness = home / "_g6p96_hook.ps1"
    harness.write_text(
        "$ErrorActionPreference = 'Stop'\r\n"
        f"$repo = '{home}'\r\n"
        f"$play = '{home}'\r\n"
        f"$stamp = '{stamp}'\r\n"
        f"$scale = {scale}\r\n"
        f"$RenderScale = '{opt}'\r\n"
        "$License = 'full'\r\n$licenseMask = 1\r\n$exitCode = 0\r\n"
        f"$session = '{home / 'sessions' / stamp}'\r\n"
        "$result = @{ seconds = 5.0; exit_hex = '00000000'; crash_report = $false; save_snapshots = 0 }\r\n"
        f"$census = @{{ lines = 40; warning = 1; error = 0; critical = 0; stub_imports = 0; guest_license_masks = @('00000001'); host_fault_codes = @(); draw_scale = {draw_scale_ps} }}\r\n"
        + block,
        encoding="utf-8-sig",
    )
    r = subprocess.run(
        [str(PS), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    harness.unlink()
    return r


with tempfile.TemporaryDirectory(prefix="g6p96_") as tmp:
    root = Path(tmp)

    # 1. play.ps1 -Summarize (Get-LogCensus) tests
    s_ok = root / "sum_ok"
    s_ok.mkdir()
    tail_noise = "\n".join(f"[12:00:0{i % 10}] [info] frame {i}" for i in range(25))
    (s_ok / "runtime.log").write_text(
        "[12:00:00] [info] M15 draw_scale x=2 y=2 as_requested=true\n" + tail_noise + "\n",
        encoding="utf-8",
    )
    c_ok = run_summarize(s_ok)
    check("census: accepted draw_scale captured past last_lines window",
          c_ok.get("draw_scale") == {"x": 2, "y": 2, "as_requested": True}, str(c_ok.get("draw_scale")))

    s_rot = root / "sum_rotated_fallback"
    s_rot.mkdir()
    (s_rot / "runtime.1.log").write_text(
        "[12:00:00] [warning] The requested draw resolution scale is not supported by the device or the emulator, reducing to 1x1\n"
        "[12:00:00] [info] M15 draw_scale x=1 y=1 as_requested=false\n",
        encoding="utf-8",
    )
    (s_rot / "runtime.log").write_text(tail_noise + "\n", encoding="utf-8")
    c_rot = run_summarize(s_rot)
    check("census: fallback draw_scale captured from rotated runtime.1.log",
          c_rot.get("draw_scale") == {"x": 1, "y": 1, "as_requested": False}, str(c_rot.get("draw_scale")))

    s_asym = root / "sum_asym"
    s_asym.mkdir()
    (s_asym / "runtime.log").write_text(
        "[12:00:00] [info] M15 draw_scale x=2 y=3 as_requested=false\n",
        encoding="utf-8",
    )
    c_asym = run_summarize(s_asym)
    check("census: asymmetric draw_scale captured",
          c_asym.get("draw_scale") == {"x": 2, "y": 3, "as_requested": False}, str(c_asym.get("draw_scale")))

    s_miss = root / "sum_missing"
    s_miss.mkdir()
    (s_miss / "runtime.log").write_text(tail_noise + "\n", encoding="utf-8")
    c_miss = run_summarize(s_miss)
    check("census: missing M15 draw_scale omits draw_scale", "draw_scale" not in c_miss, str(c_miss.get("draw_scale")))

    s_bad = root / "sum_malformed"
    s_bad.mkdir()
    (s_bad / "runtime.log").write_text(
        "[12:00:00] [info] M15 draw_scale x=0 y=1 as_requested=false\n"
        "[12:00:00] [info] M15 draw_scale x=abc y=2 as_requested=false\n"
        "[12:00:00] [info] M15 draw_scale x=999999999999 y=1 as_requested=false\n"
        "[12:00:00] [info] M15 draw_scale x=1 y=1 as_requested=maybe\n"
        "[12:00:00] [info] M15 draw_scale x=1 y=1 as_requested=truefoo\n"
        "[12:00:00] [info] M15 draw_scale x=99 y=1 as_requested=false\n",
        encoding="utf-8",
    )
    c_bad = run_summarize(s_bad)
    check("census: malformed M15 draw_scale lines ignored without error",
          "draw_scale" not in c_bad, str(c_bad.get("draw_scale")))

    s_mixed = root / "sum_mixed"
    s_mixed.mkdir()
    (s_mixed / "runtime.log").write_text(
        "[12:00:00] [info] M15 draw_scale x=1 y=1 as_requested=false\n"
        "[12:00:01] [info] M15 draw_scale x=0 y=0 as_requested=maybe\n",
        encoding="utf-8",
    )
    c_mixed = run_summarize(s_mixed)
    check("census: valid M15 draw_scale survives later malformed line",
          c_mixed.get("draw_scale") == {"x": 1, "y": 1, "as_requested": False}, str(c_mixed.get("draw_scale")))

    # 2. support_report() tests
    fake_user, fake_pc = "QaFallbackUser", "QA-GPU-HOST-99"
    env = {"USERNAME": fake_user, "COMPUTERNAME": fake_pc, "USERPROFILE": rf"C:\Users\{fake_user}"}
    home = root / f"Rayman {fake_user}"
    home.mkdir()
    (home / "installer.json").write_text(json.dumps({"schema": 1, "version": "1.3.0"}), encoding="utf-8")

    def make_report(stamp: str, extra_info: dict, log_dict: dict) -> str:
        sdir = home / "sessions" / stamp
        sdir.mkdir(parents=True)
        info = {
            "session": stamp, "preset": "HD+", "display": "fullscreen",
            "seconds": 30.0, "exit_code": 0, "exit_hex": "00000000",
            "clean_exit": True, "crash_report": False, "executable_sha256": "ab" * 32,
            "log": log_dict,
        }
        info.update(extra_info)
        (sdir / "session.json").write_text(json.dumps(info), encoding="utf-8-sig")
        (sdir / "runtime.log").write_text("RAW-LOG-SENTINEL-NEVER-COPY\n", encoding="utf-8")
        return eng.support_report(home, stamp, env=env).read_text(encoding="utf-8")

    base_log = {
        "lines": 120, "warning": 1, "error": 0, "critical": 0, "stub_imports": 0,
        "last_lines": [rf"[info] C:\Users\{fake_user}\AppData\Local\Temp\x on {fake_pc}"],
    }

    # 2a. Auto-selected scale accepted
    t = make_report("20261123-010001",
                    {"render_scale": 2, "render_scale_option": "auto"},
                    {**base_log, "draw_scale": {"x": 2, "y": 2, "as_requested": True}})
    check("report auto accepted: settings include scale and option",
          "render_scale: 2" in t and "render_scale_option: auto" in t)
    check("report auto accepted: actual draw_scale reported, no fallback line",
          "draw_scale: 2x2 (2560x1440; requested 2x2 via auto, as_requested=true)" in t
          and "draw_scale_fallback:" not in t, t)

    # 2b. Manual scale accepted
    t = make_report("20261123-010002",
                    {"render_scale": 3, "render_scale_option": "3"},
                    {**base_log, "draw_scale": {"x": 3, "y": 3, "as_requested": True}})
    check("report manual accepted: actual draw_scale reported, no fallback line",
          "render_scale_option: 3" in t
          and "draw_scale: 3x3 (3840x2160; requested 3x3 via manual, as_requested=true)" in t
          and "draw_scale_fallback:" not in t, t)

    # 2c. Auto-selected scale refused/reduced to 1x1
    t = make_report("20261123-010003",
                    {"render_scale": 2, "render_scale_option": "auto"},
                    {**base_log, "draw_scale": {"x": 1, "y": 1, "as_requested": False}})
    check("report auto fallback: draw_scale and clear fallback explanation present",
          "draw_scale: 1x1 (1280x720; requested 2x2 via auto, as_requested=false)" in t
          and "draw_scale_fallback: automatic reduction -- graphics device did not support requested scale 2x2 (2560x1440, auto); renderer used 1x1 (1280x720)" in t,
          t)
    check("report auto fallback: redaction, no raw log, compact size",
          fake_user.lower() not in t.lower() and fake_pc.lower() not in t.lower()
          and str(home).lower() not in t.lower() and "RAW-LOG-SENTINEL" not in t
          and len(t.encode("utf-8")) < 4096)

    # 2d. Manual scale refused/reduced to 1x1
    t = make_report("20261123-010004",
                    {"render_scale": 3, "render_scale_option": "3"},
                    {**base_log, "draw_scale": {"x": 1, "y": 1, "as_requested": False}})
    check("report manual fallback: draw_scale and manual mode stated",
          "draw_scale: 1x1 (1280x720; requested 3x3 via manual, as_requested=false)" in t
          and "draw_scale_fallback: automatic reduction -- graphics device did not support requested scale 3x3 (3840x2160, manual); renderer used 1x1 (1280x720)" in t,
          t)

    # 2e. Asymmetric virtual-address-space clamp
    t = make_report("20261123-010005",
                    {"render_scale": 3, "render_scale_option": "3"},
                    {**base_log, "draw_scale": {"x": 2, "y": 3, "as_requested": False}})
    check("report asymmetric fallback: 2x3 (2560x2160) reported accurately",
          "draw_scale: 2x3 (2560x2160; requested 3x3 via manual, as_requested=false)" in t
          and "renderer used 2x3 (2560x2160)" in t, t)

    # 2f. Fallback event without render_scale in session.json
    t = make_report("20261123-010006",
                    {},
                    {**base_log, "draw_scale": {"x": 1, "y": 1, "as_requested": False}})
    check("report fallback without requested scale: still flags reduction cleanly",
          "draw_scale: 1x1 (1280x720; as_requested=false)" in t
          and "draw_scale_fallback: automatic reduction -- graphics device did not support the requested rendering scale; renderer used 1x1 (1280x720)" in t,
          t)

    # 2g. Missing draw_scale event
    t = make_report("20261123-010007",
                    {"render_scale": 2, "render_scale_option": "auto"},
                    dict(base_log))
    check("report missing draw_scale: states not recorded without claiming fallback",
          "draw_scale: not recorded" in t and "draw_scale_fallback:" not in t, t)

    # 2h. Malformed draw_scale values in session.json
    malformed_cases = [
        ("str", "corrupt"),
        ("list", [1, 1]),
        ("zero", {"x": 0, "y": 1, "as_requested": False}),
        ("bool_x", {"x": True, "y": 1, "as_requested": False}),
        ("str_bool", {"x": 1, "y": 1, "as_requested": "false"}),
        ("huge", {"x": 99, "y": 1, "as_requested": False}),
    ]
    for idx, (label, bad_val) in enumerate(malformed_cases):
        t = make_report(f"20261123-01010{idx}",
                        {"render_scale": 2, "render_scale_option": "auto"},
                        {**base_log, "draw_scale": bad_val})
        check(f"report malformed draw_scale ({label}): handled safely",
              "draw_scale: unavailable (malformed diagnostic event)" in t and "draw_scale_fallback:" not in t, t)

    # 3. Unchanged normal launch / Settings LASTRUN behavior on fallback session
    # Make fallback session the newest one and confirm last_session reports clean (failed=0).
    make_report("20261123-020000",
                {"render_scale": 2, "render_scale_option": "auto"},
                {**base_log, "draw_scale": {"x": 1, "y": 1, "as_requested": False}})
    check("last_session: fallback session with exit 0 is not marked failed",
          eng.last_session(home) == ("20261123-020000", "0x00000000", 0), str(eng.last_session(home)))

    # 4. play.ps1 end-of-session console message (only on fallback; exit code preserved)
    r_fb = run_end_hook(home, "20261123-020000", 2, "auto", "@{ x = 1; y = 1; as_requested = $false }")
    check("play.ps1 console: prints fallback note when as_requested=false, exit 0",
          r_fb.returncode == 0
          and "Rendering resolution: graphics device did not support requested scale 2x2 (2560x1440, -RenderScale auto); renderer used 1x1 (1280x720)." in r_fb.stdout,
          r_fb.stdout)
    r_ok = run_end_hook(home, "20261123-010001", 2, "auto", "@{ x = 2; y = 2; as_requested = $true }")
    check("play.ps1 console: prints no fallback note when as_requested=true, exit 0",
          r_ok.returncode == 0 and "Rendering resolution:" not in r_ok.stdout, r_ok.stdout)

if failures:
    print(f"G6P96_RENDER_FALLBACK_DIAGNOSTICS_FAIL {len(failures)}")
    sys.exit(1)
print("G6P96_RENDER_FALLBACK_DIAGNOSTICS_OK")
