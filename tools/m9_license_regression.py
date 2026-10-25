"""Deterministic checks of the licence-mode switches (M9, D-032). Starts no game process.

The host sets licence bit 0 by default (full version) and leaves mask 0 when R3HD_TRIAL is set. The launch
scripts never pass a licence mask: they select full (default) or trial, and refuse any mask argument.
Needs: a built executable and no running r3hd (launcher preflight).
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checks = failures = 0


def check(condition: bool, label: str) -> None:
    global checks, failures
    checks += 1
    if not condition:
        failures += 1
        print(f"FAIL: {label}")


def powershell(script: str, *argv: str):
    done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / script), *argv],
                          cwd=ROOT, capture_output=True, text=True, errors="replace", timeout=120)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def mask_arguments(output: str):
    return re.findall(r"^argument\s+: (--license_mask\S*)\s*$", output, re.M)


code, out = powershell("play.ps1", "-DryRun")
check(code == 0 and "DRY RUN" in out, "default dry run succeeds")
check(re.search(r"^licence\s+: full version \(build default: license_mask=1;", out, re.M) is not None, "default is the full version")
check(mask_arguments(out) == [], "default passes no mask argument")

code, out = powershell("play.ps1", "-DryRun", "-License", "full")
check(code == 0 and re.search(r"^licence\s+: full version ", out, re.M) is not None and mask_arguments(out) == [], "explicit full")

code, out = powershell("play.ps1", "-DryRun", "-License", "trial")
check(code == 0 and re.search(r"^licence\s+: trial \(R3HD_TRIAL: license_mask=0;", out, re.M) is not None, "trial is selectable")
check(mask_arguments(out) == [], "trial passes no mask argument")

for value in ("all", "2", "0xFFFFFFFF", ""):
    code, out = powershell("play.ps1", "-DryRun", "-License", value)
    check(code != 0 and "DRY RUN" not in out, f"launcher refuses -License '{value}'")
for extra in ("--license_mask=1", "--license_mask=4294967295", "--license_mask=0"):
    for mode in ((), ("-License", "trial")):
        code, out = powershell("play.ps1", "-DryRun", *mode, "-ExtraArgs", extra)
        check(code != 0 and "DRY RUN" not in out, f"launcher refuses {' '.join(mode)} -ExtraArgs {extra}")

runs = ROOT / "private" / "work" / "m6_runs"
name = "m9_regression_refused"
for argv in (("-LicenseMask", "2"), ("-LicenseMask", "-1"), ("-LicenseMask", "4294967295"),
             ("-ExtraArgs", "--license_mask=1"), ("-LicenseMask", "0", "-ExtraArgs", "--license_mask=3")):
    code, out = powershell("run_milestone6.ps1", "-Run", name, "-Seconds", "1", *argv)
    check(code != 0, f"hidden runner refuses {' '.join(argv)}")
    check(not (runs / name).exists(), f"no run directory after refused {' '.join(argv)}")

# The host is the only place that sets the mask, and it sets the single observed bit.
host = (ROOT / "tools" / "m2_host" / "r3hd_app.h").read_text(encoding="utf-8")
check(re.findall(r'SetFlagByName\("license_mask",\s*"([^"]*)"\)', host) == ["1"], "host sets license_mask to 1 only")
check('getenv("R3HD_TRIAL")' in host and 'ResetToDefault("license_mask")' in host, "host keeps trial mode through R3HD_TRIAL")
for path in sorted((ROOT / "tools").glob("*.ps1")) + sorted((ROOT / "tools").glob("m[0-9]*.py")) + sorted((ROOT / "tools").glob("*.sh")):
    if path.name == Path(__file__).name:
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    check(re.search(r"--license_mask=[0-9A-Za-z]", text) is None, f"{path.name} passes no licence mask")

print(f"m9 licence switches: {checks} checks, {failures} failures: {'PASS' if not failures else 'FAIL'}")
sys.exit(1 if failures else 0)
