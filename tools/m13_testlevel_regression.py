"""Deterministic checks that isolated level entry stays a hidden-test-only option (M13, D-040). Starts no game.

The title's developer option "-level:NAME" reaches the guest only through the runtime setting `cl`. Only the
hidden runner sets it, only from its -TestLevel parameter; the player launcher refuses it; the host never sets
it by itself; a run started that way is recorded as such.
Needs: a built executable and no running r3hd (launcher preflight).
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks = failures = 0


def powershell(script: str, *argv: str):
    done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / script), *argv],
                          cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=120)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL: {label}")


runner = (ROOT / "tools" / "run_milestone6.ps1").read_text(encoding="utf-8-sig")
play = (ROOT / "tools" / "play.ps1").read_text(encoding="utf-8-sig")
host = "".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted((ROOT / "tools" / "m2_host").glob("*"))
               if p.is_file())

check(re.search(r"\[string\]\$TestLevel = ''", runner) is not None, "runner: TestLevel is off by default")
check("$TestLevel -notmatch '^[A-Za-z0-9_]{1,24}$'" in runner, "runner: TestLevel is validated as a plain name")
check(runner.count("--cl=") == 1 and 'if ($TestLevel) { $arguments += "--cl=-level:$TestLevel" }' in runner,
      "runner: cl is passed only from TestLevel and only as -level:")
check(re.search(r"\$extra -match '\^--\([^']*\|cl\)='\) \{ throw", runner) is not None, "runner: cl refused in -ExtraArgs")
check("test_level = if ($TestLevel) { $TestLevel } else { $null }" in runner, "runner: run.json records the test level")
check("$env:R3HD_NONINTRUSIVE = '1'" in runner, "runner: hidden mode is unconditional")
check("$TestLevel" not in play and play.count("--cl=") == 1 and "if ($extra -match '^--cl=') { throw" in play,
      "launcher: no level option, cl refused")
check("-level:" not in host and '"cl"' not in host and "REXCVAR_SET(cl" not in host, "host: never sets the guest command line")
for script in sorted((ROOT / "tools").glob("*.py")):
    text = script.read_text(encoding="utf-8", errors="replace")
    if script.name not in ("m13_testlevel_regression.py",) and "--cl=" in text:
        check(False, f"{script.name} passes cl directly")
check(True, "no Python tool passes cl directly")

code, out = powershell("play.ps1", "-DryRun", "-ExtraArgs", "--cl=-level:wood_10")
check(code != 0 and "DRY RUN" not in out and "hidden test runs only" in out, "launcher refuses -ExtraArgs --cl=-level:...")
code, out = powershell("play.ps1", "-DryRun")
check(code == 0 and "DRY RUN" in out and "--cl" not in out, "default launch carries no guest command line")
runs = ROOT / "private" / "work" / "m6_runs"
for argv in (("-ExtraArgs", "--cl=-level:wood_10"), ("-TestLevel", "wood_10;x"), ("-TestLevel", "..\\x")):
    name = "m13_regression_refused"
    code, out = powershell("run_milestone6.ps1", "-Run", name, "-Seconds", "5", *argv)
    check(code != 0, f"hidden runner refuses {' '.join(argv)}")
    check(not (runs / name).exists(), f"no run directory after refused {' '.join(argv)}")

print(f"m13 test-level gate: {checks} checks, {failures} failures: {'FAIL' if failures else 'PASS'}")
sys.exit(1 if failures else 0)
