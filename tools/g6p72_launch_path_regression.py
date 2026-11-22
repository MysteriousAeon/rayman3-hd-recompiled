#!/usr/bin/env python3
"""G6-P72: play.ps1 starts the game process from a home whose path holds [ ] (and other wildcard characters).

Windows PowerShell 5.1 resolves `Start-Process -FilePath` and `-WorkingDirectory` as wildcard paths. Before G6-P72 a
home such as `D:\\Games\\Rayman 3 HD [PC]` passed every preflight and the dry run, but the launch itself failed with
"file not found"; when the pattern also matched another existing folder (`Rayman [12]` beside `Rayman 1`) the process
started there instead. play.ps1 now starts the game only through `Start-R3hdGameProcess`, which escapes both paths.

This test never starts the game, the launcher or play.ps1's launch. It loads the real `Start-R3hdGameProcess` from
play.ps1 with the PowerShell parser (as r3hd_portable_preflight_regression.py does), checks that it is play.ps1's only
process start and its call is the real one, and runs it in Windows PowerShell (hidden, CREATE_NO_WINDOW) on synthetic
homes. The started program is a windowless stand-in: pythonw.exe of the staged, hash-pinned embedded Python
(GUI subsystem, no window, no focus change, no input) running a five-line script that records its working directory,
executable and arguments and exits with a chosen code. Checked: plain, [PC], Unicode + brackets, backtick + brackets
and a decoy folder the unescaped pattern would match; the working directory, executable, quoted arguments and exit
codes 0, 7 and 0xC0000005 are exact; the decoy is untouched. Two mutations restore the pre-G6-P72 forms (no escape;
the executable escaped but not the folder) and must be rejected by the bracket checks.

Optional (`--dry-run`, needs the private build and extracted game data): play.ps1 -DryRun exactly as the launcher
runs it (-File HOME\\app\\tools\\play.ps1 -UserHome HOME) on a bracketed synthetic installed home creates nothing.

Usage: python tools/g6p72_launch_path_regression.py [--python-dir DIR] [--play PLAY_PS1] [--dry-run] [--keep DIR]
Prints G6P72_LAUNCH_PATH PASS / FAIL; without a pinned embedded Python it prints G6P72_LAUNCH_PATH SKIP and exits 3.
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
PAYLOAD = json.loads((ROOT / "config/release/payload.json").read_text(encoding="utf-8"))
SYS32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
PS = SYS32 / "WindowsPowerShell" / "v1.0" / "powershell.exe"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
STUB_FILES = ("pythonw.exe", "python3.dll", "python311.dll", "python311.zip", "python311._pth")
STUB_SCRIPT = ("import json, os, sys\n"
               "with open('stub_report.json', 'w', encoding='utf-8') as f:\n"
               "    json.dump({'cwd': os.getcwd(), 'exe': sys.executable, 'argv': sys.argv[1:]}, f)\n"
               "sys.exit(int(sys.argv[-1]))\n")
HOMES = (("plain", "Rayman 3 HD"), ("brackets", "Rayman 3 HD [PC]"),
         ("unicode", "Rayman 3 HD Türkçe 東京 [Taşınabilir]"), ("backtick", "Rayman 3 HD `tick [x]"),
         ("decoy", "Rayman [12]"))
DECOY = "Rayman 1"  # what the unescaped pattern 'Rayman [12]' matches
CODES = (0, 7, -1073741819)  # normal, an error, 0xC0000005

# Loads exactly one Start-R3hdGameProcess from play.ps1 (optionally mutated), checks it is the only process start and
# that play.ps1 calls it once as the launch, runs it, and prints one JSON line. Writes nothing itself.
HARNESS = r'''
param([string]$Source, [string]$Mutation, [string]$Exe, [string]$Session, [string]$Script, [string]$Code)
$ErrorActionPreference = 'Stop'
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Source, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'play.ps1 has parse errors' }
$func = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Start-R3hdGameProcess' }, $true))
$calls = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Start-R3hdGameProcess' }, $true))
$starts = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.CommandAst] -and $n.GetCommandName() -eq 'Start-Process' }, $true))
$shape = [ordered]@{
    functions = $func.Count
    call = $(if ($calls.Count -eq 1) { $calls[0].Parent.Parent.Extent.Text } else { "$($calls.Count) calls" })
    starts_outside = @($starts | Where-Object { $func.Count -ne 1 -or -not ($_.Extent.StartOffset -ge $func[0].Extent.StartOffset -and $_.Extent.EndOffset -le $func[0].Extent.EndOffset) }).Count
}
$text = $func[0].Extent.Text
$esc = '[Management.Automation.WildcardPattern]::Escape'
if ($Mutation -eq 'unescaped') { $text = $text.Replace("($esc(`$Exe))", '$Exe').Replace("($esc(`$Session))", '$Session') }
if ($Mutation -eq 'exe_only') { $text = $text.Replace("($esc(`$Session))", '$Session') }
$shape.mutated = ($text -ne $func[0].Extent.Text)
. ([scriptblock]::Create($text))
$arguments = '"' + $Script + '" "--user_data_root=' + (Join-Path (Split-Path -Parent (Split-Path -Parent $Session)) 'profiles\default\user') + '" "' + $Code + '"'
try {
    $process = Start-R3hdGameProcess $Exe $arguments $Session
    $process.WaitForExit()
    $shape.result = 'exited'; $shape.exit_code = $process.ExitCode
} catch { $shape.result = 'thrown'; $shape.error = $_.Exception.GetType().FullName }
$shape | ConvertTo-Json -Compress
'''

failures = []
checks = 0


def check(name, cond, detail=""):
    global checks
    checks += 1
    print(("PASS " if cond else "FAIL ") + name + ("" if cond or not detail else f"  ({detail})"))
    if not cond:
        failures.append(name)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def find_python(explicit):
    want = PAYLOAD["python"].get("stdlib_zip_sha256")
    cands = [Path(explicit)] if explicit else sorted((ROOT / "private" / "work").glob("*/*/app/python"))
    for c in cands:
        if all((c / n).is_file() for n in STUB_FILES) and sha256(c / "python311.zip") == want:
            return c
    return None


def build_home(base: Path, name: str, python_dir: Path) -> Path:
    home = base / "Users" / "QaPerson" / "Games" / name
    stub = home / "bin" / "stub"
    stub.mkdir(parents=True)
    for n in STUB_FILES:
        shutil.copyfile(python_dir / n, stub / n)
    (stub / "stub_game.py").write_text(STUB_SCRIPT, encoding="utf-8")
    (home / "sessions" / "20261120-120000").mkdir(parents=True)
    (home / "profiles" / "default" / "user").mkdir(parents=True)
    return home


def run(play: Path, harness: Path, home: Path, code: int, mutation: str = ""):
    session = home / "sessions" / "20261120-120000"
    r = subprocess.run([str(PS), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness),
                        "-Source", str(play), "-Mutation", mutation, "-Exe", str(home / "bin" / "stub" / "pythonw.exe"),
                        "-Session", str(session), "-Script", str(home / "bin" / "stub" / "stub_game.py"),
                        "-Code", str(code)], capture_output=True, text=True, encoding="oem", errors="replace",
                       creationflags=NOWIN, timeout=120)
    line = next((l for l in r.stdout.splitlines() if l.startswith("{")), None)
    out = json.loads(line) if line else {"result": "harness_failed", "stderr": r.stderr.strip()[-300:]}
    report = session / "stub_report.json"
    out["report"] = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else None
    if report.is_file():
        report.unlink()
    return out


def exact(out, home: Path, code: int) -> bool:
    rep = out.get("report") or {}
    session = home / "sessions" / "20261120-120000"
    return (out.get("result") == "exited" and out.get("exit_code") == code and bool(rep)
            and os.path.normcase(rep["cwd"]) == os.path.normcase(str(session))
            and os.path.normcase(rep["exe"]) == os.path.normcase(str(home / "bin" / "stub" / "pythonw.exe"))
            and rep["argv"] == [f"--user_data_root={home / 'profiles' / 'default' / 'user'}", str(code)])


def dry_run(play: Path, base: Path, python_dir: Path):
    """play.ps1 -DryRun as the launcher runs it, on a bracketed synthetic installed home (private inputs read only)."""
    game, bin_dir = ROOT / "private/extracted/5841123F", ROOT / "private/work/rex/out/build/win-amd64-release"
    if not (game / "Default.xex").is_file() or not (bin_dir / "r3hd.exe").is_file():
        print("SKIP dry run: private build or extracted game data not present")
        return
    home = base / "Users" / "QaPerson" / "Games" / "Rayman 3 HD [PC] dry"
    for dest, src in PAYLOAD["app_files"].items():
        t = home.joinpath(*dest.split("/"))
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / src, t)
    shutil.copyfile(play, home / "app" / "tools" / "play.ps1")
    shutil.copytree(python_dir, home / "app" / "python", ignore=shutil.ignore_patterns("tcl", "tcl86t.dll", "tk86t.dll"))
    (home / "installer.json").write_text(json.dumps({"schema": 1, "version": "9.9.9-synthetic"}), encoding="utf-8")
    for d in ("profiles", "sessions", "cache"):
        (home / d).mkdir()
    before = sorted(p for p in home.rglob("*"))
    env = {k: v for k, v in os.environ.items() if k.upper() not in ("PYTHONPATH", "PYTHONHOME") and not k.startswith("R3HD_")}
    r = subprocess.run([str(PS), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(home / "app" / "tools" / "play.ps1"), "-UserHome", str(home), "-GameDir", str(game),
                        "-BinDir", str(bin_dir), "-DryRun"], cwd=home, env=env, capture_output=True, text=True,
                       encoding="oem", errors="replace", creationflags=NOWIN, timeout=300)
    check("dry run on a bracketed installed home: exit 0, DRY RUN line",
          r.returncode == 0 and "DRY RUN - nothing was started." in r.stdout, r.stderr.strip()[-300:])
    check("dry run on a bracketed installed home: nothing created", sorted(p for p in home.rglob("*")) == before)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--python-dir", help="a staged app\\python folder (default: search private/work/*/*/app/python)")
    ap.add_argument("--play", type=Path, default=TOOLS / "play.ps1", help="the play.ps1 under test")
    ap.add_argument("--dry-run", action="store_true", help="also dry-run play.ps1 on a bracketed home (private inputs)")
    ap.add_argument("--keep", type=Path, help="keep the synthetic homes in this new folder")
    a = ap.parse_args()
    if os.name != "nt" or not PS.is_file():
        print("G6P72_LAUNCH_PATH SKIP: needs Windows PowerShell 5.1")
        return 3
    python_dir = find_python(a.python_dir)
    if not python_dir:
        print("G6P72_LAUNCH_PATH SKIP: no staged embedded Python matching config/release/payload.json")
        return 3
    play = a.play.resolve()
    with tempfile.TemporaryDirectory(prefix="g6p72_") as tmp:
        base = Path(a.keep).resolve() if a.keep else Path(tmp)
        base.mkdir(parents=True, exist_ok=bool(not a.keep))
        harness = base / "_g6p72_start.ps1"
        harness.write_text(HARNESS, encoding="utf-8-sig")
        homes = {key: build_home(base, name, python_dir) for key, name in HOMES}
        decoy = build_home(base, DECOY, python_dir)
        decoy_before = sorted(str(p.relative_to(decoy)) for p in decoy.rglob("*"))

        first = run(play, harness, homes["plain"], 0)
        check("play.ps1 defines Start-R3hdGameProcess once", first.get("functions") == 1)
        check("play.ps1 launches the game with it, once",
              first.get("call") == "$process = Start-R3hdGameProcess $exe $quoted $session", first.get("call"))
        check("play.ps1 has no other Start-Process", first.get("starts_outside") == 0)
        for key, _ in HOMES:
            for code in CODES:
                out = first if (key, code) == ("plain", 0) else run(play, harness, homes[key], code)
                check(f"{key}: exact folder, executable, arguments and exit code {code}", exact(out, homes[key], code),
                      json.dumps({k: out.get(k) for k in ("result", "error", "exit_code", "report")}, ensure_ascii=True)[:300])
        check("decoy: the folder the unescaped pattern matches is untouched",
              sorted(str(p.relative_to(decoy)) for p in decoy.rglob("*")) == decoy_before)

        # Mutations: the pre-G6-P72 statement (nothing escaped) and an executable-only escape must be caught.
        for mutation in ("unescaped", "exe_only"):
            caught = []
            for key in ("brackets", "unicode", "backtick", "decoy"):
                out = run(play, harness, homes[key], 7, mutation)
                caught.append(out.get("mutated") is True and not exact(out, homes[key], 7))
            check(f"mutation {mutation}: rejected for every bracketed home", all(caught), str(caught))
            out = run(play, harness, homes["plain"], 7, mutation)
            check(f"mutation {mutation}: a plain home still passes (the check is specific)",
                  out.get("mutated") is True and exact(out, homes["plain"], 7))
        check("decoy: untouched after the mutations ran in it",
              [n for n in sorted(str(p.relative_to(decoy)) for p in decoy.rglob("*")) if n not in decoy_before] in
              ([], [str(Path("sessions/20261120-120000/stub_report.json"))]))
        stray = decoy / "sessions" / "20261120-120000" / "stub_report.json"
        if stray.is_file():
            stray.unlink()  # written by an unescaped mutation into the decoy, as the defect did

        if a.dry_run:
            dry_run(play, base, python_dir)
        harness.unlink()
    print(f"G6P72_LAUNCH_PATH {'PASS' if not failures else 'FAIL'} checks={checks} failures={len(failures)} game_starts=0")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
