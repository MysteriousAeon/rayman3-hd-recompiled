#!/usr/bin/env python3
"""G6-P58: the G6-P46 support report through the Linux launcher (tools/linux/r3hd_play.py), synthetic only.

No game, no build, no graphical session: the launcher's end-of-session path (finish -> finalize_session ->
support-report CLI) runs on plans built in dry-run mode for synthetic homes, with a fake executable file. Checks:
normal exit, signal and non-zero exits, missing diagnostics, an unfinished (plan-only) session.json, report-generator
failure isolation, Linux home / user / host redaction, exit-status preservation, and that a Windows session's report
is byte-identical to the one HEAD's engine writes. Static and synthetic evidence only; runs on Windows or Linux.
Prints G6P58_LINUX_SUPPORT_REPORT_OK on success.
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "linux"))
import r3hd_installer as eng  # noqa: E402
import r3hd_play as P  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


USER, HOST = "qaperson", "qa-laptop-77"
LINUX_HOME = f"/home/{USER}"


def make_plan(home):
    ns = dict(bin=None, game=None, home=str(home), profile="default", preset="hdplus", settings=None, set=[],
              key_layout=None, mods="on", license="full", no_keyboard=False, dev_overlay=False, log_level="info",
              extra=[], dry_run=True, check=False)
    plan = P.build_plan(P.argparse.Namespace(**ns), now=P.datetime.datetime(2026, 11, 18, 12, 0, 0))
    exe = Path(home) / "bin" / "r3hd"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"\x7fELF synthetic")
    plan["executable"] = str(exe)
    session = Path(plan["session"])
    session.mkdir(parents=True, exist_ok=True)
    plan["platform"] = "linux"  # as launch() records it
    (session / "session.json").write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")  # as launch() does
    plan["started"] = "2026-11-18T12:00:00"
    return plan, session


def run_finish(plan, code, run=subprocess.run):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        rc = P.finish(plan, code, run)
    return rc, buf.getvalue()


saved_env = dict(os.environ)
os.environ.update(USER=USER, LOGNAME=USER, HOSTNAME=HOST, HOME=LINUX_HOME)
try:
    with tempfile.TemporaryDirectory(prefix="g6p58_") as tmp:
        # 1. Normal completion, with runtime logs that name Linux paths, the user and the host.
        home = Path(tmp) / f"r3hd {USER}"
        home.mkdir()
        (home / "installer.json").write_text(json.dumps({"schema": 1, "version": "1.1.0-rc1"}), encoding="utf-8")
        plan, s = make_plan(home)
        (s / "runtime.1.log").write_text("[i] [warning] old part\n", encoding="utf-8")
        (s / "runtime.log").write_text(
            f"[i] [info] game data {LINUX_HOME}/.local/share/r3hd/data/content\n"
            f"[i] [error] cannot open /var/home/{USER}/x on {HOST}\n"
            f"[i] [info] user {USER} at {home}/profiles\n"
            "[i] [info] XamFoo stub=true count=1 first\n", encoding="utf-8")
        rc, out = run_finish(plan, 0)
        rec = json.loads((s / "session.json").read_text(encoding="utf-8"))
        rep = s / eng.SUPPORT_REPORT
        text = rep.read_text(encoding="utf-8") if rep.is_file() else ""
        low = text.lower()
        check("normal exit preserved", rc == 0)
        check("session.json finished for Linux", rec.get("platform") == "linux" and rec.get("exit_code") == 0
              and rec.get("clean_exit") is True and rec.get("seconds", -1) >= 0 and "exit_signal" not in rec)
        check("log census mirrors play.ps1", rec["log"]["lines"] == 5 and rec["log"]["warning"] == 1
              and rec["log"]["error"] == 1 and rec["log"]["stub_imports"] == 1
              and rec["log"]["last_lines"][0].endswith("old part"))
        check("executable hash recorded", len(rec.get("executable_sha256", "")) == 64)
        check("report written beside the logs", rep.is_file())
        check("launcher prints the report path", f"Support report (redacted; review before sharing): {rep}" in out
              and f"Diagnostics: {s}" in out)
        check("Linux os line, no Windows claims", "\nos: " in text.replace("\r", "") and "windows:" not in low
              and "0x" not in text and "user / host name" in text)
        check("normal exit named", "exit: 0 normal exit" in text and "clean_exit: True" in text)
        check("settings whitelist from the Linux plan", "preset: hdplus" in text and "display: " in text
              and "render_scale: " in text)
        check("user name never appears", USER not in low)
        check("host name never appears", HOST not in low)
        check("install path replaced", str(home).lower() not in low and "<install>" in low)
        check("Linux home paths replaced", "<HOME>/.local/share" in text and "/var/home/<USER>/x" in text)
        check("arguments and env not listed", "user_data_root" not in text and "R3HD_" not in text
              and "LD_LIBRARY_PATH" not in text)

        # 2. Unexpected exits: a signal (subprocess returns -N) and a non-zero status; codes are returned unchanged.
        plan, s = make_plan(home)
        rc, out = run_finish(plan, -11)
        text = (s / eng.SUPPORT_REPORT).read_text(encoding="utf-8")
        check("signal exit preserved", rc == -11)
        check("signal named, not an NTSTATUS", "exit: -11 (signal SIGSEGV)" in text and "clean_exit: False" in text
              and "0x" not in text and "(SIGSEGV)" in out)
        plan, s = make_plan(home)
        rc, _ = run_finish(plan, 3)
        text = (s / eng.SUPPORT_REPORT).read_text(encoding="utf-8")
        check("non-zero exit preserved and reported plainly", rc == 3 and "exit: 3\n" in text)

        # 3. Missing diagnostics: no logs, no executable, no installer.json.
        bare = Path(tmp) / "bare"
        bare.mkdir()
        plan, s = make_plan(bare)
        Path(plan["executable"]).unlink()
        rc, _ = run_finish(plan, 1)
        rec = json.loads((s / "session.json").read_text(encoding="utf-8"))
        text = (s / eng.SUPPORT_REPORT).read_text(encoding="utf-8")
        check("missing logs and executable tolerated", rc == 1 and rec["log"]["lines"] == 0
              and "executable_sha256: unknown" in text and "[last log lines]" not in text)
        # A session whose launcher died before finishing: session.json is still only the plan.
        plan, s = make_plan(bare)
        out_unfinished = eng.support_report(bare, s.name, env=dict(os.environ))
        check("unfinished Linux session reported as unknown",
              "exit: unknown" in out_unfinished.read_text(encoding="utf-8"))
        (s / "session.json").unlink()
        check("missing session.json still yields a report", "session.json: missing" in
              eng.support_report(bare, s.name).read_text(encoding="utf-8"))

        # 4. Report-generator failure isolation: exit codes unchanged, no report line, no exception.
        def raises(*a, **k):
            raise OSError("no python")

        def fails(*a, **k):
            return subprocess.CompletedProcess(a, 2, stdout='{"result":"refused"}', stderr="")

        def garbage(*a, **k):
            return subprocess.CompletedProcess(a, 0, stdout="not json", stderr="")

        for name, run, code in (("raising", raises, 0), ("refusing", fails, -11), ("garbage", garbage, 5)):
            plan, s = make_plan(home)
            rc, out = run_finish(plan, code, run)
            check(f"generator {name}: exit {code} preserved, no report line", rc == code and "Support report" not in out)
        plan, s = make_plan(home)
        plan["session"] = str(Path(tmp) / "gone" / "20261118-120000")  # session.json cannot be written
        rc, out = run_finish(plan, 7)
        check("unwritable session record: exit preserved", rc == 7)
finally:
    os.environ.clear()
    os.environ.update(saved_env)

# 5. Windows: a Windows session's report is byte-identical to HEAD's engine (when the repository has HEAD).
head = subprocess.run(["git", "-C", str(REPO), "show", "HEAD:tools/r3hd_installer.py"], capture_output=True)
if head.returncode == 0 and os.name == "nt":
    with tempfile.TemporaryDirectory(prefix="g6p58w_") as tmp:
        old_path = Path(tmp) / "r3hd_installer_head.py"
        old_path.write_bytes(head.stdout)
        spec = importlib.util.spec_from_file_location("r3hd_installer_head", old_path)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        # Synthetic accounts, templated so the fixture stays a placeholder for the release audit.
        qa_user, qa_pc, other_linux_user = "QaPerson", "QA-DESKTOP-77", "someone"
        os.environ.update(USERNAME=qa_user, COMPUTERNAME=qa_pc, USERPROFILE=rf"C:\Users\{qa_user}")
        try:
            home = Path(tmp) / f"Rayman {qa_user}"
            s = home / "sessions" / "20261118-101500"
            s.mkdir(parents=True)
            (home / "installer.json").write_text(json.dumps({"schema": 1, "version": "1.2.0"}), encoding="utf-8")
            (s / "session.json").write_text(json.dumps({
                "preset": "HD+", "display": "fullscreen", "seconds": 3.0, "exit_code": -1073741819,
                "exit_hex": "C0000005", "clean_exit": False, "crash_report": False, "executable_sha256": "ab" * 32,
                "log": {"lines": 2, "error": 1, "last_lines": [rf"[e] C:\Users\{qa_user}\x on {qa_pc}",
                                                               f"[i] /home/{other_linux_user}/y"]}}), encoding="utf-8-sig")
            a = old.support_report(home).read_bytes()
            b = eng.support_report(home).read_bytes()
            (s / "session.json").unlink()
            c, d = old.support_report(home, s.name).read_bytes(), eng.support_report(home, s.name).read_bytes()
            check("Windows report byte-identical to HEAD (finished and missing session.json)", a == b and c == d)
        finally:
            os.environ.clear()
            os.environ.update(saved_env)
else:
    print("SKIP Windows byte comparison (needs a Windows host and git HEAD)")

play = (TOOLS / "linux" / "r3hd_play.py").read_text(encoding="utf-8")
check("main finishes the session after launch", "return finish(plan, launch(plan, " in play)

if failures:
    print(f"G6P58_LINUX_SUPPORT_REPORT_FAIL {len(failures)}")
    sys.exit(1)
print("G6P58_LINUX_SUPPORT_REPORT_OK")
