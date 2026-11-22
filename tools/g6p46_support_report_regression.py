#!/usr/bin/env python3
"""G6-P46 (D-302): the redacted support report (r3hd_installer.py support-report) on synthetic homes only.

No game, no build, no process other than one CLI call of the engine. Checks: paths, user and computer names are
replaced; the crash record keeps only the module's file name and never includes the minidump; exit codes are named;
missing or hostile session names are refused; a session without session.json still yields a report; play.ps1 calls
the command best-effort after session.json. Prints G6P46_SUPPORT_REPORT_OK on success.
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

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


with tempfile.TemporaryDirectory(prefix="g6p46_") as tmp:
    fake_user, fake_pc = "QaPerson", "QA-DESKTOP-77"
    other_linux_user = "someone"  # synthetic; templated so the fixture stays a placeholder for the release audit
    os.environ.update(USERNAME=fake_user, COMPUTERNAME=fake_pc, USERPROFILE=rf"C:\Users\{fake_user}")
    home = Path(tmp) / f"Rayman {fake_user}"
    stamp = "20261118-101500"
    s = home / "sessions" / stamp
    s.mkdir(parents=True)
    (home / "installer.json").write_text(json.dumps({"schema": 1, "version": "1.2.0"}), encoding="utf-8")
    exe = home / "app" / "bin" / "r3hd.exe"
    session = {"session": stamp, "preset": "HD+", "display": "fullscreen", "mods": f"remix ({home}\\mods\\x)",
               "settings_file": str(home / "settings.json"), "arguments": [f"--user_data_root={home}"],
               "seconds": 12.5, "exit_code": -1073741819, "exit_hex": "C0000005", "clean_exit": False,
               "crash_report": True, "executable_sha256": "ab" * 32,
               "log": {"lines": 40, "warning": 2, "error": 1, "critical": 0, "stub_imports": 3,
                       "host_fault_codes": ["C0000005 x1"],
                       "last_lines": [f"[info] opened {home}\\data\\content\\x.ipk",
                                      rf"[error] C:\Users\{fake_user}\AppData\Local\Temp\a failed on {fake_pc}",
                                      f"[info] /home/{other_linux_user}/.local/share/r3hd ok"]}}
    (s / "session.json").write_text(json.dumps(session), encoding="utf-8-sig")
    (s / "r3hd_crash.txt").write_text(
        "r3hd crash report\ncode=C0000005 flags=00000000 thread=12\n"
        f"address=00007FF6000012AB module={exe} offset=12AB\naccess=read target=0000000000000010\n"
        "minidump=r3hd_crash.dmp written=1\n", encoding="utf-8")
    (s / "r3hd_crash.dmp").write_bytes(b"MDMP-SECRET-BYTES")
    (s / "runtime.log").write_text("SHOULD-NOT-BE-READ-DIRECTLY", encoding="utf-8")

    out = eng.support_report(home)  # newest session
    text = out.read_text(encoding="utf-8")
    low = text.lower()
    check("report written beside the logs", out == s / eng.SUPPORT_REPORT)
    check("version and session recorded", "version: 1.2.0" in text and f"session: {stamp}" in text)
    check("exit code named", "0xC0000005" in text and "access violation" in text)
    check("user name never appears", fake_user.lower() not in low)
    check("computer name never appears", fake_pc.lower() not in low)
    check("install path replaced", str(home).lower() not in low and "<install>" in low)
    check("other Linux home replaced", f"/home/{other_linux_user}" not in text and "/home/<USER>" in text)
    check("crash module reduced to file name", "module=r3hd.exe offset=12AB" in text)
    check("minidump not included", "MDMP" not in text and "minidump: not included" in text)
    check("raw runtime.log not copied", "SHOULD-NOT-BE-READ" not in text)
    check("settings file and arguments not listed", "settings_file" not in text and "user_data_root" not in text)
    check("log summary and host faults", "error: 1" in text and "host_fault_codes: C0000005 x1" in text)

    # A session that ended without session.json (play.ps1 stopped) still yields a report when named.
    s2 = home / "sessions" / "20261118-110000"
    s2.mkdir()
    out2 = eng.support_report(home, s2.name)
    check("missing session.json is reported, not a crash", "session.json: missing" in out2.read_text(encoding="utf-8"))

    # G6-P73 (D-322): a start Windows refused leaves a launcher-only record; the report states it, invents no exit and
    # redacts the error text like any other field.
    s3 = home / "sessions" / "20261118-120000"
    s3.mkdir()
    (s3 / "session.json").write_text(json.dumps({
        "session": s3.name, "record": "launcher_only", "outcome": "start_failed", "game_started": False,
        "game_pid": None, "preset": "HD+", "executable_sha256": None, "arguments": [f"--user_data_root={home}"],
        "start_error": (rf"System.InvalidOperationException: cannot run {home}\bin\r3hd.exe for "
                        rf"C:\Users\{fake_user}\x on {fake_pc} (InvalidOperationException,StartProcessCommand)")}),
        encoding="utf-8-sig")
    text3 = eng.support_report(home, s3.name).read_text(encoding="utf-8")
    check("start_failed: outcome and the redacted error stated",
          "outcome: start_failed" in text3 and "game_started: false" in text3
          and r"start_error: System.InvalidOperationException: cannot run <INSTALL>\bin\r3hd.exe" in text3)
    check("start_failed: no exit, duration or crash line invented",
          all(x not in text3 for x in ("exit:", "duration_s:", "clean_exit:", "crash_record:")))
    check("start_failed: user / computer name and arguments absent", fake_user.lower() not in text3.lower()
          and fake_pc.lower() not in text3.lower() and "user_data_root" not in text3)
    check("start_failed: Settings LASTRUN names it as failed", eng.last_session(home) == (s3.name, "start_failed", 1))

    def refused(fn, code):
        try:
            fn()
        except eng.Refusal as e:
            return e.code == code
        return False

    check("unknown session refused", refused(lambda: eng.support_report(home, "nope"), "NO_SESSION"))
    check("path in session name refused", refused(lambda: eng.support_report(home, "..\\..\\x"), "NO_SESSION"))
    empty = Path(tmp) / "empty"
    empty.mkdir()
    check("home without sessions refused", refused(lambda: eng.support_report(empty), "NO_SESSION"))

    # The CLI as play.ps1 calls it.
    (s / eng.SUPPORT_REPORT).unlink()
    r = subprocess.run([sys.executable, "-B", str(TOOLS / "r3hd_installer.py"), "support-report", "--home", str(home),
                        "--session", stamp, "--json"], capture_output=True, text=True)
    ok = r.returncode == 0
    try:
        ok = ok and Path(json.loads(r.stdout)["report"]) == s / eng.SUPPORT_REPORT and (s / eng.SUPPORT_REPORT).is_file()
    except (ValueError, KeyError):
        ok = False
    check("CLI writes the report and returns its path", ok)

play = (TOOLS / "play.ps1").read_text(encoding="utf-8")
i_json, i_rep = play.find("'session.json') -Encoding UTF8"), play.find("support-report --home $play --session $stamp")
check("play.ps1 runs the report after session.json, best effort", 0 < i_json < i_rep and
      "} catch { $supportReport = $null }" in play and play.rstrip().endswith("exit $(if ($exitCode -eq 0) { 0 } else { 1 })"))

if failures:
    print(f"G6P46_SUPPORT_REPORT_FAIL {len(failures)}")
    sys.exit(1)
print("G6P46_SUPPORT_REPORT_OK")
