#!/usr/bin/env python3
"""G6-P53: the G6-P46 support report through the installed and portable play path, on synthetic homes only.

Both editions start the game the same way: the native launcher (Settings > Play, `r3hd_launcher.exe --play`, and the
portable Play.cmd -> r3hd_portable.py play -> r3hd_launcher.exe --play) runs HOME\\app\\tools\\play.ps1 -UserHome HOME
hidden. This test does not start a game, a launcher or play.ps1 itself. It copies the payload's app\\tools files
(config/release/payload.json app_files) and an already staged, hash-pinned embedded Python (app\\python with
python311._pth) into a synthetic installed home and a synthetic portable home, extracts play.ps1's end-of-session
block (from the G6-P46 support-report hook to the final exit) unchanged, and runs it in Windows PowerShell as a script
in HOME\\app\\tools, hidden (CREATE_NO_WINDOW, as the launcher does), with PATH reduced to System32 so only the
bundled Python can be used. Checked per edition: normal exit, unexpected exit with crash record and minidump,
incomplete diagnostics, missing session.json, a broken engine; report placement, version, redaction of synthetic
private paths / user / computer names, no saves, game content, launch arguments or minidump bytes; the exit code is
unchanged in every case. Payload membership of play.ps1 and the engine is checked for both packages.

Usage: python tools/g6p53_support_report_integration.py [--python-dir DIR]
Without a pinned embedded Python (DIR\\python311.zip matching config/release/payload.json) it prints
G6P53_SUPPORT_INTEGRATION_SKIP and exits 3; it never passes without one. Prints G6P53_SUPPORT_INTEGRATION_OK on success.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
PAYLOAD = json.loads((ROOT / "config/release/payload.json").read_text(encoding="utf-8"))
FAKE_USER, FAKE_PC = "QaPerson", "QA-DESKTOP-77"
OTHER_USER = "OtherPerson"  # synthetic; templated so the fixture stays a placeholder for the release audit
VERSION = "9.9.9-synthetic"
failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def find_python(explicit):
    want = PAYLOAD["python"].get("stdlib_zip_sha256")
    cands = [Path(explicit)] if explicit else sorted((ROOT / "private" / "work").glob("*/*/app/python"))
    for c in cands:
        if (c / "python.exe").is_file() and (c / "python311._pth").is_file() and (c / "python311.zip").is_file() \
                and sha256(c / "python311.zip") == want:
            return c
    return None


def hook_block() -> str:
    text = (TOOLS / "play.ps1").read_text(encoding="utf-8")
    start = text.index("# G6-P46 (D-302)")
    end = text.rindex("exit $(if ($exitCode -eq 0) { 0 } else { 1 })")
    return text[start:end] + "exit $(if ($exitCode -eq 0) { 0 } else { 1 })\r\n"


def build_home(base: Path, kind: str, python_dir: Path) -> Path:
    home = base / "Users" / FAKE_USER / "Games" / f"Rayman {kind} {FAKE_USER}"
    for dest, src in PAYLOAD["app_files"].items():
        if dest.startswith("app/tools/"):
            target = home.joinpath(*dest.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / src, target)
    shutil.copytree(python_dir, home / "app" / "python",
                    ignore=shutil.ignore_patterns("tcl", "*.pyd", "tcl86t.dll", "tk86t.dll", "pythonw.exe"))
    state = {"schema": 1, "version": VERSION}
    if kind == "portable":
        state["distribution"] = "portable"
        (home / "portable.json").write_text(json.dumps({"schema": 1, "application_version": VERSION}), encoding="utf-8")
    (home / "installer.json").write_text(json.dumps(state), encoding="utf-8")
    (home / "profiles").mkdir()
    (home / "profiles" / "slot0.sav").write_bytes(b"SAVE-SECRET-BYTES")
    (home / "data" / "content").mkdir(parents=True)
    (home / "data" / "content" / "level.ipk").write_bytes(b"GAME-CONTENT-BYTES")
    return home


def write_session(home: Path, stamp: str, case: str) -> int:
    s = home / "sessions" / stamp
    s.mkdir(parents=True)
    exe = home / "bin" / "r3hd.exe"
    if case == "missing":  # play.ps1 stopped before session.json; the hook still runs for the folder
        return 1
    crash = case == "crash"
    exit_code = -1073741819 if crash else (0 if case == "normal" else 1)
    info = {"session": stamp, "preset": "HD+", "display": "fullscreen", "mods": f"remix ({home}\\mods\\x)",
            "settings_file": str(home / "settings.json"), "save_history": str(home / "save_history"),
            "arguments": [f"--user_data_root={home}", "--SECRET-ARG"], "seconds": 3.5, "exit_code": exit_code,
            "exit_hex": f"{exit_code & 0xFFFFFFFF:08X}", "clean_exit": case == "normal", "crash_report": crash,
            "executable_sha256": "cd" * 32}
    if case != "incomplete":
        info["log"] = {"lines": 9, "warning": 1, "error": int(crash), "critical": 0, "stub_imports": 0,
                       "host_fault_codes": ["C0000005 x1"] if crash else [],
                       "last_lines": [f"[info] content {home}\\data\\content",
                                      rf"[error] C:\Users\{FAKE_USER}\AppData\Local\Temp\x on {FAKE_PC}",
                                      rf"[info] D:\Users\{OTHER_USER}\r3hd ok"]}
    (s / "session.json").write_text(json.dumps(info), encoding="utf-8-sig")
    (s / "runtime.log").write_text("RAW-LOG-NOT-COPIED", encoding="utf-8")
    if crash:
        (s / "r3hd_crash.txt").write_text(
            "r3hd crash report\ncode=C0000005 flags=00000000 thread=7\n"
            f"address=00007FF600001000 module={exe} offset=1000\nminidump=r3hd_crash.dmp written=1\n", encoding="utf-8")
        (s / "r3hd_crash.dmp").write_bytes(b"MDMP-MEMORY-SECRET")
    if case == "incomplete":  # a crash record cut off mid-write, no log summary
        (s / "r3hd_crash.txt").write_bytes(b"r3hd crash report\ncode=C00000")
    return 0 if exit_code == 0 else 1


def run_hook(home: Path, stamp: str, exit_code: int):
    harness = home / "app" / "tools" / "_g6p53_hook.ps1"
    harness.write_text("param([string]$Play, [string]$Stamp, [int]$ExitCode)\r\n$ErrorActionPreference = 'Stop'\r\n"
                       "$repo = Split-Path -Parent $PSScriptRoot\r\n$play = $Play\r\n$stamp = $Stamp\r\n"
                       "$exitCode = $ExitCode\r\n$session = Join-Path (Join-Path $play 'sessions') $stamp\r\n"
                       "$result = @{ seconds = 1; exit_hex = '0' }\r\n$census = @{ host_fault_codes = @() }\r\n"
                       + hook_block(), encoding="utf-8-sig")
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PATH", "PYTHONPATH", "PYTHONHOME")}
    env.update(PATH=f"{system32};{system32 / 'WindowsPowerShell' / 'v1.0'}", USERNAME=FAKE_USER, COMPUTERNAME=FAKE_PC,
               USERPROFILE=str(home.parents[1]), LOCALAPPDATA=str(home.parents[1] / "AppData" / "Local"))
    ps = system32 / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    r = subprocess.run([str(ps), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness),
                        "-Play", str(home), "-Stamp", stamp, "-ExitCode", str(exit_code)], cwd=home, env=env,
                       capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    harness.unlink()
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python-dir", help="a staged app\\python folder (default: search private/work/*/*/app/python)")
    py = find_python(ap.parse_args().python_dir)
    if py is None:
        print("G6P53_SUPPORT_INTEGRATION_SKIP no pinned embedded Python found (never a pass)")
        return 3
    print(f"embedded Python: {py.relative_to(ROOT) if py.is_relative_to(ROOT) else py}")

    import r3hd_portable_zip
    members = r3hd_portable_zip.defined_members()
    for rel in ("app/tools/play.ps1", "app/tools/r3hd_installer.py", "app/python/python.exe"):
        check(f"installer payload and portable ZIP both carry {rel}",
              rel in members and rel in set(PAYLOAD["app_files"]) | {"app/python/python.exe"})
    check("portable Play.cmd goes through r3hd_portable.py play -> launcher --play",
          b"r3hd_portable.py\" play" in r3hd_portable_zip.command("play")
          and 'args.append("--play")' in (TOOLS / "r3hd_portable.py").read_text(encoding="utf-8"))
    launcher = (TOOLS / "launcher" / "r3hd_launcher.cpp").read_text(encoding="utf-8")
    check("launcher Play runs app\\tools\\play.ps1 -UserHome HOME hidden",
          'p.tools + L"\\\\play.ps1", L"-UserHome", p.home' in launcher and "CREATE_NO_WINDOW" in launcher)

    with tempfile.TemporaryDirectory(prefix="g6p53_") as tmp:
        for kind in ("installed", "portable"):
            home = build_home(Path(tmp), kind, py)
            for n, case in enumerate(("normal", "crash", "incomplete", "missing")):
                stamp = f"20261118-12000{n}"
                want_exit = write_session(home, stamp, case)
                r = run_hook(home, stamp, {"normal": 0, "crash": -1073741819}.get(case, 1))
                out = home / "sessions" / stamp / "support_report.txt"
                tag = f"{kind}/{case}"
                check(f"{tag}: exit code preserved ({want_exit})", r.returncode == want_exit)
                check(f"{tag}: report written in sessions\\{stamp}", out.is_file())
                check(f"{tag}: play.ps1 prints the report path", f"Support report (redacted; review before sharing): {out}"
                      in r.stdout)
                if not out.is_file():
                    print(r.stdout, r.stderr)
                    continue
                text = out.read_text(encoding="utf-8")
                low = text.lower()
                check(f"{tag}: version and session identified", f"version: {VERSION}" in text and f"session: {stamp}" in text)
                check(f"{tag}: no user / computer name / other profile", all(x.lower() not in low for x in
                      (FAKE_USER, FAKE_PC, OTHER_USER)))
                check(f"{tag}: install path replaced", str(home).lower() not in low)
                check(f"{tag}: no saves, game content, arguments, raw log or dump",
                      all(x not in text for x in ("SAVE-SECRET", "GAME-CONTENT", "SECRET-ARG", "user_data_root",
                                                  "settings_file", "save_history", "RAW-LOG", "MDMP")))
                if case == "crash":
                    check(f"{tag}: exit named, module basename, dump excluded", "access violation" in text and
                          "module=r3hd.exe offset=1000" in text and "minidump: not included" in text)
                if case == "missing":
                    check(f"{tag}: missing session.json stated", "session.json: missing" in text)
                if case == "incomplete":
                    check(f"{tag}: truncated crash record kept, no log section", "[crash record]" in text
                          and "[last log lines]" not in text)
            # A broken engine never changes the result: the report is skipped, the exit code stays.
            (home / "app" / "tools" / "r3hd_installer.py").write_text("raise SystemExit(7)\n", encoding="utf-8")
            stamp = "20261118-130000"
            write_session(home, stamp, "crash")
            r = run_hook(home, stamp, -1073741819)
            check(f"{kind}/broken engine: exit code preserved, no report, no report line",
                  r.returncode == 1 and not (home / "sessions" / stamp / "support_report.txt").exists()
                  and "Support report" not in r.stdout)
            stamp = "20261118-130001"
            write_session(home, stamp, "normal")
            shutil.rmtree(home / "app" / "python")
            r = run_hook(home, stamp, 0)
            check(f"{kind}/no bundled Python and none on PATH: exit 0 preserved", r.returncode == 0
                  and "Support report" not in r.stdout)
    if failures:
        print(f"G6P53_SUPPORT_INTEGRATION_FAIL {len(failures)}")
        return 1
    print("G6P53_SUPPORT_INTEGRATION_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
