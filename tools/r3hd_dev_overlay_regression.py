#!/usr/bin/env python3
"""D-114 / D-121: regression of developer-overlay isolation. Starts no game and shows nothing on the person's desktop.

  * play.ps1: F3 and F4 disabled on every launch unless -DevOverlay; binding overrides refused in -ExtraArgs;
    BIN\\r3hd.toml is set aside (moved unchanged to PLAYROOT\\dev_overlay_config\\) only in a real launch, after the
    agent guard, never in a dry run, and kept in place with -DevOverlay
  * the set-aside functions in a scratch folder: plan, unique target names, bytes preserved, a failed move stops the
    launch and leaves the file where it was
  * -DryRun in a synthetic installed home with a synthetic bin\\ (placeholder executable and DLLs, the real extracted
    game data): normal vs -DevOverlay arguments, the keyboard map (F1 of original_pc included) and the Settings
    preferences identical in both, no anisotropic / vsync / mouse argument (the SDK's 4x default, D-112, stays)
  * the installer engine: dev_overlay_config\\ is a user item; its selftest (the D-114 lifecycle cases among them)
usage: r3hd_dev_overlay_regression.py [--skip-engine-selftest]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
import r3hd_installer as engine  # noqa: E402

SDK = ROOT / "external" / "rexglue-sdk"
GAME = Path(os.environ.get("R3HD_GAME_DIR") or ROOT / "private" / "extracted" / "5841123F")
checks, skipped = [], []


def check(name, cond, detail=""):
    checks.append((name, bool(cond)))
    print(f"{'ok  ' if cond else 'FAIL'} {name}" + (f"  ({detail})" if detail and not cond else ""))


def skip(name, why):
    skipped.append(name)
    print(f"skip {name}  ({why})")


def powershell(script: str):
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, errors="replace", timeout=300)
    return r.returncode, r.stdout + r.stderr


def play_function(name: str) -> str:
    play = (TOOLS / "play.ps1").read_text(encoding="utf-8")
    m = re.search(r"^function " + name + r"\b.*?(?=^function |\Z)", play, re.M | re.S)
    return m.group(0)


def ps_quote(p) -> str:
    return "'" + str(p).replace("'", "''") + "'"


# --- play.ps1 source --------------------------------------------------------------------------------------------------

def static_checks():
    play = (TOOLS / "play.ps1").read_text(encoding="utf-8")
    check("play.ps1: debug overlay is developer-only",
          "if (-not $DevOverlay) { $arguments += '--bind_debug_overlay=None' }" in play)
    check("play.ps1: -DevOverlay is a switch", re.search(r"^\s*\[switch\]\$DevOverlay,", play, re.M))
    check("play.ps1: --bind_settings=None unless -DevOverlay",
          "if (-not $DevOverlay) { $arguments += '--bind_settings=None' }" in play)
    check("play.ps1: --bind_settings is refused in -ExtraArgs",
          re.search(r"if \(\$extra -match '\^--bind_settings='\) \{ throw ", play))
    move = play.index("\nMove-DevConfig $devConfig")
    check("play.ps1: the file is moved only in a real launch, after the dry-run exit and the agent guard",
          move > play.index("if ($DryRun) {") and move > play.index("if ($agent -and -not $AllowFromAgent)")
          and move < play.index("$process = Start-Process"))
    check("play.ps1: the choice is recorded in launch.json and session.json",
          "dev_overlay = $devText; sessions_removed" in play and "    dev_overlay = $devText\n" in play)
    check("play.ps1: the set-aside never deletes (no Remove-Item in its functions)",
          "Remove-Item" not in play_function("Get-DevConfigPlan") + play_function("Move-DevConfig"))
    aniso = (SDK / "src" / "graphics" / "pipeline" / "texture" / "cache.cpp").read_text(encoding="utf-8")
    check("SDK default anisotropic_override stays 3 (4x, D-112)",
          re.search(r"REXCVAR_DEFINE_INT32\(anisotropic_override, 3,", aniso))
    check("engine: dev_overlay_config is a user item (kept, allowed by a fresh install, removed only on confirmation)",
          "dev_overlay_config" in engine.USER_ITEMS and engine.DEV_CONFIG == "r3hd.toml")


# --- set-aside functions ----------------------------------------------------------------------------------------------

def function_checks():
    funcs = play_function("Get-DevConfigPlan") + play_function("Move-DevConfig")
    with tempfile.TemporaryDirectory(prefix="r3hd_d114_fn_") as tmp:
        t = Path(tmp)
        bin_dir, play = t / "bin", t / "home"
        bin_dir.mkdir()
        play.mkdir()

        def plan(keep):
            code, out = powershell(funcs + f"\n$p = Get-DevConfigPlan {ps_quote(bin_dir)} {ps_quote(play)} '20261026-120000' "
                                           f"${str(keep).lower()}\n$p | ConvertTo-Json -Compress")
            try:
                return json.loads(out.strip().splitlines()[-1])
            except (ValueError, IndexError):
                return {"error": out[-300:]}

        p = plan(False)
        check("plan: no BIN\\r3hd.toml -> nothing to do", p.get("state") == "none" and p.get("target") is None, p)
        toml = bin_dir / "r3hd.toml"
        toml.write_bytes(b"vsync = false\r\nmnk_mouse = true\n")
        check("plan: -DevOverlay keeps the file in place", plan(True).get("state") == "kept")
        p = plan(False)
        check("plan: a normal launch sets it aside under PLAYROOT\\dev_overlay_config",
              p.get("state") == "set_aside" and Path(p["target"]) == play / "dev_overlay_config" / "r3hd-20261026-120000.toml", p)
        (play / "dev_overlay_config").mkdir()
        (play / "dev_overlay_config" / "r3hd-20261026-120000.toml").write_bytes(b"older")
        p = plan(False)
        check("plan: an earlier set-aside file is never replaced (unique name)",
              Path(p.get("target", "")).name == "r3hd-20261026-120000-1.toml", p)
        code, out = powershell(funcs + f"\n$p = Get-DevConfigPlan {ps_quote(bin_dir)} {ps_quote(play)} '20261026-120000' $false"
                                       "\nMove-DevConfig $p\n'MOVED'")
        target = play / "dev_overlay_config" / "r3hd-20261026-120000-1.toml"
        check("move: the file leaves BIN\\ byte for byte; the earlier one is untouched",
              code == 0 and "MOVED" in out and not toml.exists() and target.read_bytes() == b"vsync = false\r\nmnk_mouse = true\n"
              and (play / "dev_overlay_config" / "r3hd-20261026-120000.toml").read_bytes() == b"older", out[-300:])
        code, out = powershell(funcs + f"\nMove-DevConfig (Get-DevConfigPlan {ps_quote(bin_dir)} {ps_quote(play)} 'x' $false)\n'NOOP'")
        check("move: nothing to move is a no-op", code == 0 and "NOOP" in out, out[-300:])
        # A failed move stops the launch and leaves the file where it was (dev_overlay_config blocked by a file).
        play2 = t / "home2"
        play2.mkdir()
        (play2 / "dev_overlay_config").write_bytes(b"not a folder")
        toml.write_bytes(b"vsync = false\n")
        code, out = powershell(funcs + f"\nMove-DevConfig (Get-DevConfigPlan {ps_quote(bin_dir)} {ps_quote(play2)} 's' $false)\n'MOVED'")
        check("move: a failure throws a PREFLIGHT message and leaves BIN\\r3hd.toml unchanged",
              code != 0 and "PREFLIGHT:" in out and "MOVED" not in out and toml.read_bytes() == b"vsync = false\n"
              and (play2 / "dev_overlay_config").read_bytes() == b"not a folder", out[-300:])


# --- dry runs ---------------------------------------------------------------------------------------------------------

def dry_run_checks():
    if not (GAME / "Default.xex").is_file():
        skip("play.ps1 -DryRun with a synthetic bin", "needs the extracted game data (Default.xex)")
        return
    with tempfile.TemporaryDirectory(prefix="r3hd_d114_play_") as tmp:
        t = Path(tmp)
        bin_dir, home = t / "bin", t / "home"
        bin_dir.mkdir()
        for name in ("r3hd.exe", "rexruntime.dll", "rexgpu-xenos.dll", "ffmpeg.dll", "mspack.dll"):
            (bin_dir / name).write_bytes(b"placeholder")  # the dry run only checks they exist
        (home / "sessions").mkdir(parents=True)
        (home / "installer.json").write_text("{}", encoding="utf-8")
        toml = bin_dir / "r3hd.toml"
        toml_bytes = b"vsync = false\nanisotropic_override = 0\nmnk_mouse = true\nbind_settings = \"F9\"\n"
        toml.write_bytes(toml_bytes)

        def dry(prefs, *extra):
            (home / "settings.json").write_text(json.dumps({"schema": 3, "preset": "vanilla", "preferences": prefs}),
                                                encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if not k.startswith("R3HD_")}
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TOOLS / "play.ps1"),
                                "-UserHome", str(home), "-BinDir", str(bin_dir), "-GameDir", str(GAME), "-DryRun", *extra],
                               capture_output=True, text=True, errors="replace", env=env, timeout=300)
            out = r.stdout + r.stderr
            return r.returncode, out, [l.split(": ", 1)[1] for l in out.splitlines() if l.startswith("argument   : ")]

        prefs = {"display": "fullscreen", "diagnostics": "detailed"}
        code, out, args = dry(prefs, "-KeyLayout", "original_pc")
        check("dry run (player): exit 0, --bind_settings=None passed", code == 0 and "--bind_settings=None" in args, out[-500:])
        check("dry run (player): F3 disabled exactly once", args.count("--bind_debug_overlay=None") == 1)
        check("dry run (player): reports the set-aside, moves nothing, creates nothing",
              "would be moved unchanged" in out and toml.read_bytes() == toml_bytes
              and not (home / "dev_overlay_config").exists(), out[-500:])
        code_d, out_d, args_d = dry(prefs, "-KeyLayout", "original_pc", "-DevOverlay")
        check("dry run (-DevOverlay): no --bind_settings, the file is loaded as is",
              code_d == 0 and not any(a.startswith("--bind_settings") for a in args_d)
              and "is loaded as is" in out_d and toml.read_bytes() == toml_bytes, out_d[-500:])
        check("dry run (-DevOverlay): F3 binding remains at SDK/config value",
              code_d == 0 and not any(a.startswith("--bind_debug_overlay=") for a in args_d))
        same = lambda xs: [a for a in xs if a not in ("--bind_settings=None", "--bind_debug_overlay=None") and not a.startswith("--log_file=")]  # noqa: E731
        check("dry run: every other argument is identical in both modes (Settings, keyboard map; the session's log "
              "path aside)", same(args) == same(args_d) and len(args_d) > 20, set(args) ^ set(args_d))
        check("dry run: the Settings preferences still apply (fullscreen, detailed diagnostics)",
              "--fullscreen=true" in args and not any(a.startswith("--log_max_files") for a in args))
        check("dry run: the keyboard map is passed, F1 of original_pc included",
              "--keybind_left_trigger=F1" in args and sum(a.startswith("--keybind_") for a in args) >= 26, args)
        check("dry run: no anisotropic, vsync, mouse or sensitivity argument (SDK defaults, D-112 4x)",
              not any(re.match(r"--(anisotropic_override|vsync|mnk_mouse|mnk_sensitivity)=", a) for a in args + args_d))
        code, out, _ = dry(prefs, "-Mouse")
        check("dry run: -Mouse still adds --mnk_mouse=true beside --bind_settings=None",
              code == 0 and "argument   : --mnk_mouse=true" in out and "argument   : --bind_settings=None" in out, out[-300:])
        code, out, _ = dry(prefs, "-ExtraArgs", "--bind_settings=F4")
        check("dry run: -ExtraArgs --bind_settings=F4 is refused (use -DevOverlay)",
              code != 0 and "enabled with -DevOverlay" in out, out[-300:])
        for binding in ("F3", "F9", "None"):
            code, out, _ = dry(prefs, "-ExtraArgs", "--bind_debug_overlay=" + binding)
            check("dry run: debug binding override refused: " + binding,
                  code != 0 and "enabled with -DevOverlay" in out, out[-300:])
        toml.unlink()
        code, out, args = dry({})
        check("dry run without BIN\\r3hd.toml: F4 off, nothing to set aside",
              code == 0 and "--bind_settings=None" in args and "dev overlay: off; no " in out, out[-300:])


def engine_checks():
    r = subprocess.run([sys.executable, str(TOOLS / "r3hd_installer.py"), "selftest"], capture_output=True, text=True,
                       timeout=1800)
    d114 = [l for l in r.stdout.splitlines() if "D-114" in l]
    check("engine selftest PASS, the 8 D-114 lifecycle cases among them",
          r.returncode == 0 and "R3HD_INSTALLER_SELFTEST PASS" in r.stdout and len(d114) == 8
          and all(l.startswith("ok") for l in d114), (r.stdout + r.stderr)[-500:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-engine-selftest", action="store_true")
    a = ap.parse_args()
    static_checks()
    function_checks()
    dry_run_checks()
    if a.skip_engine_selftest:
        skip("engine selftest", "--skip-engine-selftest")
    else:
        engine_checks()
    failed = sum(not ok for _, ok in checks)
    print(f"D114_DEV_OVERLAY_REGRESSION {'PASS' if not failed else 'FAIL'} checks={len(checks)} failures={failed} "
          f"skipped={len(skipped)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
