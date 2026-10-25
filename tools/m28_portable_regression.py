#!/usr/bin/env python3
"""M28 regression (D-062, D-063): portable paths, per-user home and the user build mode, without starting the game.

Checks
  * tools/r3hd_paths.py selftest (precedence, home, install refusals)
  * play.ps1 -DryRun resolves the same game / bin / play / settings paths as r3hd_paths.py resolve for the legacy
    launch, an environment home, an option home, explicit overrides; a home's settings.json is applied only when
    no -Preset / -SettingsFile is named; a dry run creates nothing in the home
  * build_milestone8.bat: user mode wiring (R3HD_GAME_DIR, R3HD_JOBS, r3hd_build_step.py audit, the M28 selftests)
  * m2_prepare.py keeps the developer manifest text for the default game directory
  * run_milestone6.ps1 takes R3HD_GAME_DIR and keeps its repository default
The dry runs need the built executable and the extracted Default.xex (play.ps1's preflight); without them they
are counted as skipped, never as passed. The temporary home lives in the system temp directory and is removed.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import r3hd_paths  # noqa: E402

checks, skipped = [], []


def check(name, cond, detail=""):
    checks.append((name, bool(cond)))
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  ({detail})" if detail and not cond else ""))


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("R3HD_")}
    env.update(extra)
    return env


def dry_run(env, *args):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TOOLS / "play.ps1"),
                        "-DryRun", *args], capture_output=True, text=True, env=env, cwd=ROOT)
    out = {}
    for line in r.stdout.splitlines():
        if len(line) >= 12 and line[11] == ":":  # play.ps1 prints an 11-character label, then ": value"
            out.setdefault(line[:11].strip(), line[12:].strip())
    return r.returncode, out, r.stdout + r.stderr


def norm(p):
    return str(Path(p).resolve()).lower() if p else ""


r = subprocess.run([sys.executable, str(TOOLS / "r3hd_paths.py"), "selftest"], capture_output=True, text=True)
check("r3hd_paths selftest", r.returncode == 0 and "R3HD_PATHS_SELFTEST PASS" in r.stdout, r.stdout[-300:])

r = subprocess.run([sys.executable, str(TOOLS / "r3hd_release_audit.py"), "git"], capture_output=True, text=True, cwd=ROOT)
check("release audit of the tracked tree (G-PKG for the source-only release)", r.returncode == 0
      and "R3HD_RELEASE_AUDIT PASS" in r.stdout, (r.stdout + r.stderr)[-400:])

bat = (TOOLS / "build_milestone8.bat").read_text(encoding="utf-8")
for needle in ['if not defined R3HD_GAME_DIR set "R3HD_GAME_DIR=%CD%\\private\\extracted\\5841123F"',
               "python tools\\r3hd_build_step.py audit || exit /b 1", "-j %R3HD_J6%",
               "python tools\\r3hd_bootstrap.py selftest || exit /b 1", "python tools\\r3hd_build_step.py selftest || exit /b 1",
               "python tools\\r3hd_release_audit.py selftest || exit /b 1", "python tools\\m28_portable_regression.py || exit /b 1"]:
    check(f"build script has: {needle[:60]}", bat.count(needle) == 1)
check("build script: SDK and test builds use R3HD_J4", bat.count("-j %R3HD_J4%") == 2)
check("build script no longer calls the target audit directly", "tools\\m3_target_audit.py" not in bat)
m2 = (TOOLS / "m2_prepare.py").read_text(encoding="utf-8")
check("m2_prepare keeps the relative developer game path", "game_ref = '../../extracted/5841123F'" in m2
      and "R3HD_GAME_DIR" in m2)
m6 = (TOOLS / "run_milestone6.ps1").read_text(encoding="utf-8")
check("hidden runner: R3HD_GAME_DIR with repository default",
      "if ($env:R3HD_GAME_DIR) { $env:R3HD_GAME_DIR } else { Join-Path $repo 'private/extracted/5841123F' }" in m6)
play = (TOOLS / "play.ps1").read_text(encoding="utf-8")
check("play.ps1 no longer requires the unused TracyClient.dll", "'TracyClient.dll'" not in play)

legacy_bin, legacy_game = r3hd_paths.LEGACY["bin_dir"], r3hd_paths.LEGACY["game_dir"]
if "--skip-runtime-dry-run" in sys.argv[1:]:
    skipped.append("play.ps1 dry runs (explicit --skip-runtime-dry-run; game may be running)")
elif not ((legacy_bin / "r3hd.exe").is_file() and (legacy_game / "Default.xex").is_file()):
    skipped.append("play.ps1 dry runs (no build or no extracted data)")
else:
    with tempfile.TemporaryDirectory(prefix="r3hd_m28_") as t:
        t = Path(t)
        home = t / "Home"
        r3hd_paths.init_home(home, preset="hdplus", log=lambda *_: None)
        before = sorted(str(p.relative_to(home)) for p in home.rglob("*"))

        code, out, text = dry_run(clean_env())
        want = r3hd_paths.resolve(env={})
        check("legacy dry run: repository paths, no settings file", code == 0
              and norm(out.get("game data")) == norm(want["game_dir"]["path"])
              and norm(out.get("bin dir")) == norm(want["bin_dir"]["path"])
              and norm(out.get("play root")) == norm(want["play_root"]["path"])
              and out.get("settings") == "" and out.get("preset", "").startswith("vanilla (launcher defaults)"), text[-400:])

        env = clean_env(R3HD_HOME=str(home), R3HD_GAME_DIR=str(legacy_game), R3HD_BIN_DIR=str(legacy_bin))
        code, out, text = dry_run(env)
        want = r3hd_paths.resolve(env=env)
        check("env home: play root and settings from the home, data / bin from their variables", code == 0
              and norm(out.get("play root")) == norm(want["play_root"]["path"]) == norm(home)
              and norm(out.get("settings")) == norm(want["settings"]["path"]) == norm(home / "settings.json")
              and norm(out.get("game data")) == norm(legacy_game) and norm(out.get("bin dir")) == norm(legacy_bin), text[-400:])
        check("home settings.json applied (hdplus: layer coordinates separate)",
              out.get("layer coord") == "separate" and "hdplus" in out.get("preset", ""), text[-400:])
        check("profile under the home", norm(out.get("profile")) == norm(home / "profiles" / "default" / "user"))

        code, out, text = dry_run(clean_env(R3HD_GAME_DIR=str(legacy_game), R3HD_BIN_DIR=str(legacy_bin)),
                                  "-UserHome", str(home), "-Preset", "vanilla")
        check("named -Preset wins over the home's settings.json", code == 0 and out.get("settings") == ""
              and out.get("layer coord") == "original", text[-400:])

        other = t / "OtherPlay"
        code, out, text = dry_run(env, "-PlayRoot", str(other), "-GameDir", str(legacy_game), "-BinDir", str(legacy_bin))
        want = r3hd_paths.resolve({"play_root": str(other)}, env=env)
        check("explicit -PlayRoot beats the home", code == 0 and norm(out.get("play root")) == norm(want["play_root"]["path"])
              == norm(other), text[-400:])

        code, out, text = dry_run(clean_env(R3HD_HOME=str(home)))
        check("home without data or build: preflight names both missing", code != 0
              and "Executable missing" in text and "Extracted game content missing" in text, text[-400:])

        after = sorted(str(p.relative_to(home)) for p in home.rglob("*"))
        check("dry runs created nothing in the home", before == after and not other.exists())

failed = [n for n, ok in checks if not ok]
print(f"M28_PORTABLE_REGRESSION {'PASS' if not failed else 'FAIL'} checks={len(checks)} failures={len(failed)} "
      f"skipped={len(skipped)}" + (f" ({'; '.join(skipped)})" if skipped else ""))
sys.exit(0 if not failed else 1)
