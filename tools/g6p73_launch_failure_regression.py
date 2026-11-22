#!/usr/bin/env python3
"""G6-P73: what play.ps1 leaves behind when a launch fails, on synthetic installed and portable homes only.

Four outcome classes (D-322):
  preflight      play.ps1 refuses before anything is created (arguments, settings, missing / damaged files):
                 exit 1, the reason on the console (the launcher's cache\\launcher_play.log); no session folder, no
                 save_history entry.
  start_failed   preflight passed but Windows did not create the game process: session.json is a launcher-only record
                 (`record: launcher_only`, `outcome: start_failed`, `game_started: false`, no PID, exit code, log or
                 crash fields), support_report.txt states it, the profile copy this attempt took is not kept, exit 1.
  game exit != 0 the game ran and ended abnormally: the existing session.json / report, exit 1.
  normal exit    the game ran and ended with 0: the existing session.json / report, exit 0.

This test never starts the game, the launcher or play.ps1's launch from an agent shell. Preflight cases run the real
play.ps1 -DryRun as the launcher does (-File HOME\\app\\tools\\play.ps1 -UserHome HOME) on synthetic files only. The
launch cases load every top-level function of play.ps1 with the PowerShell parser, set the variables the earlier part
of the script would set, and run play.ps1's own text from "# --- launch ---" to its final exit unchanged, as a script in
HOME\\app\\tools, hidden (CREATE_NO_WINDOW), PATH reduced to System32 so only the bundled Python is used. The started
program is a windowless stand-in: pythonw.exe of the staged, hash-pinned embedded Python (GUI subsystem: no window,
focus change or input) running a short script that may append to the synthetic profile at once and exits with a code.
Every case records exit code, console message, session files, support-report presence, save_history changes and
the profile / older-history hashes. The mutation `unescaped` restores the pre-G6-P72 start (a bracketed home then
fails to start), which must now leave the launcher-only record.

Usage: python tools/g6p73_launch_failure_regression.py [--python-dir DIR] [--play PLAY_PS1] [--json OUT] [--keep DIR]
Prints G6P73_LAUNCH_FAILURE PASS / FAIL; without a pinned embedded Python: G6P73_LAUNCH_FAILURE SKIP, exit 3.
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
SYS32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
PS = SYS32 / "WindowsPowerShell" / "v1.0" / "powershell.exe"
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FAKE_USER, FAKE_PC = "QaPerson", "QA-DESKTOP-73"
VERSION = "9.9.9-synthetic"
STUB_FILES = ("pythonw.exe", "python3.dll", "python311.dll", "python311.zip", "python311._pth")
STUB_SCRIPT = ("import os, sys\n"
               "a = dict(x.split('=', 1) for x in sys.argv[1:] if x.startswith('--') and '=' in x)\n"
               "if a.get('--write'):\n"
               "    with open(a['--write'], 'ab') as f:\n"
               "        f.write(b'-CHANGED-BY-STAND-IN')\n"
               "with open('stub_report.txt', 'w', encoding='utf-8') as f:\n"
               "    f.write(os.getcwd())\n"
               "sys.exit(int(a.get('--code', '0')))\n")
SAVE_REL = Path("5841123F") / "00000001" / "slot0" / "slot0"
SAVE_BYTES = b"SAVE-SECRET-BYTES-" + bytes(range(64))
OLD_STAMP = "20261101-000000"

# Everything play.ps1 computes before "# --- launch ---", for a vanilla launch of profile 'default'.
PREAMBLE = r'''
param([string]$Source, [string]$Play, [string]$Stamp, [string]$Exe, [string]$Script, [string]$Code, [string]$Write,
      [string]$Mutation)
$ErrorActionPreference = 'Stop'
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Source, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'play.ps1 has parse errors' }
$esc = '[Management.Automation.WildcardPattern]::Escape'
foreach ($f in @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false))) {
    $t = $f.Extent.Text
    if ($Mutation -eq 'unescaped' -and $f.Name -eq 'Start-R3hdGameProcess') {
        $t = $t.Replace("($esc(`$Exe))", '$Exe').Replace("($esc(`$Session))", '$Session')
    }
    . ([scriptblock]::Create($t))
}
$repo = Split-Path -Parent $PSScriptRoot
$homeRoot = $Play; $play = $Play; $legacyPlay = $false
$historyText = Join-Path $play 'save_history'
$sessions = Join-Path $play 'sessions'; $stamp = $Stamp; $session = Join-Path $sessions $stamp
$Profile = 'default'; $user = Join-Path $play "profiles/$Profile/user"; $cache = Join-Path $play 'cache'
$exe = $Exe; $arguments = @($Script, "--code=$Code", "--write=$Write")
$python = Join-Path $repo 'python\python.exe'
$prune = @(); $devConfig = [ordered]@{ state = 'none'; source = 'bin\r3hd.toml'; target = $null }
$devText = 'off; no bin\r3hd.toml'
$presetLabel = 'vanilla (launcher defaults)'; $presetWarnings = @(); $SettingsFile = ''
$License = 'full'; $licenseMask = 1; $licenseText = 'full version (synthetic)'
$Display = 'windowed'; $window = $null; $scale = 1; $RenderScale = 'auto'
$target = [ordered]@{ width = 1280; height = 720; source = 'default window' }; $renderText = '1280x720 (synthetic)'
$Pacing = 'precise'; $Revisit = 'fixed'; $Cursor = 'auto'; $SaveClock = 'local'; $GameLanguage = 'en'
$Diagnostics = 'standard'; $ButtonPrompts = 'xbox'; $DiscordPresence = 'off'; $VSync = 'on'
$keyText = 'synthetic'; $padText = 'synthetic'; $modsText = 'none installed'; $modsNotes = @(); $modsPlan = ''
$achText = ''; $structuralMarker = $null; $pcsetHome = ''; $pcsetText = 'F4; this session only'
$settingParams = [ordered]@{}
'''

# Remove-R3hdUnstartedSnapshot's guards, on a synthetic profile: only the one copy this launch made, of an unchanged
# profile, in a folder this launch created, may go. Prints one JSON line {case: [removed, folder_still_there]}.
GUARDS = r'''
param([string]$Source, [string]$Keeper, [string]$Base)
$ErrorActionPreference = 'Stop'
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Source, [ref]$tokens, [ref]$parseErrors)
$f = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Remove-R3hdUnstartedSnapshot' }, $false))
if ($f.Count -ne 1) { '{"defined": false}'; exit 0 }
. ([scriptblock]::Create($f[0].Extent.Text))
. $Keeper
$out = [ordered]@{ defined = $true }
foreach ($case in 'removable', 'existed_before', 'profile_changed', 'extra_item', 'two_copies', 'no_keeper') {
    $user = Join-Path $Base "$case\user"; $hist = Join-Path $Base "$case\save_history\20261120-110000"
    New-Item -ItemType Directory -Path $user -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $user 'slot.bin'), 'SAVE')
    $created = $true
    if ($case -eq 'existed_before') { New-Item -ItemType Directory -Path $hist -Force | Out-Null; $created = -not (Test-Path -LiteralPath $hist) }
    $k = New-SaveKeeper $user $hist
    [void](Update-SaveKeeper $k 'before the session' -Final)
    if ($case -eq 'profile_changed') { [IO.File]::AppendAllText((Join-Path $user 'slot.bin'), 'X'); (Get-Item -LiteralPath (Join-Path $user 'slot.bin')).LastWriteTimeUtc = [DateTime]::UtcNow.AddMinutes(1) }
    if ($case -eq 'extra_item') { [IO.File]::WriteAllText((Join-Path $hist 'note.txt'), 'other') }
    if ($case -eq 'two_copies') { [IO.File]::AppendAllText((Join-Path $user 'slot.bin'), 'Y'); (Get-Item -LiteralPath (Join-Path $user 'slot.bin')).LastWriteTimeUtc = [DateTime]::UtcNow.AddMinutes(2); [void](Update-SaveKeeper $k 'changed' -Final) }
    $arg = if ($case -eq 'no_keeper') { $null } else { $k }
    $removed = Remove-R3hdUnstartedSnapshot $arg $created
    $out[$case] = @([bool]$removed, (Test-Path -LiteralPath $hist), (Test-Path -LiteralPath (Join-Path $user 'slot.bin')))
}
$out | ConvertTo-Json -Compress
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
        if all((c / n).is_file() for n in STUB_FILES + ("python.exe",)) and sha256(c / "python311.zip") == want:
            return c
    return None


def tree(root: Path) -> dict:
    """Relative path -> SHA-256 (files) or '<dir>', for everything under root."""
    out = {}
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            out[p.relative_to(root).as_posix()] = "<dir>" if p.is_dir() else sha256(p)
    return out


def build_home(base: Path, name: str, kind: str, python_dir: Path, play: Path) -> Path:
    home = base / "Users" / FAKE_USER / "Games" / name
    for dest, src in PAYLOAD["app_files"].items():  # app\tools, app\config (the settings registry), notices
        t = home.joinpath(*dest.split("/"))
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / src, t)
    shutil.copyfile(play, home / "app" / "tools" / "play.ps1")
    shutil.copytree(python_dir, home / "app" / "python",
                    ignore=shutil.ignore_patterns("tcl", "*.pyd", "tcl86t.dll", "tk86t.dll"))
    state = {"schema": 1, "version": VERSION}
    if kind == "portable":
        state["distribution"] = "portable"
        (home / "portable.json").write_text(json.dumps({"schema": 1, "application_version": VERSION}), encoding="utf-8")
    (home / "installer.json").write_text(json.dumps(state), encoding="utf-8")
    save = home / "profiles" / "default" / "user" / SAVE_REL
    save.parent.mkdir(parents=True)
    save.write_bytes(SAVE_BYTES)
    old = home / "save_history" / OLD_STAMP / "000"
    (old / "user").mkdir(parents=True)
    (old / "user" / "old.bin").write_bytes(b"OLDER-HISTORY")
    (old / "snapshot.json").write_text('{"index": 0, "reason": "before the session"}', encoding="utf-8")
    stub = home / "bin" / "stub"
    stub.mkdir(parents=True)
    for n in STUB_FILES:
        shutil.copyfile(python_dir / n, stub / n)
    (stub / "stub_game.py").write_text(STUB_SCRIPT, encoding="utf-8")
    for d in ("sessions", "cache"):
        (home / d).mkdir()
    return home


def env_for(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in ("PATH", "PYTHONPATH", "PYTHONHOME") and not k.upper().startswith("R3HD_")}
    env.update(PATH=f"{SYS32};{SYS32 / 'WindowsPowerShell' / 'v1.0'}", USERNAME=FAKE_USER, COMPUTERNAME=FAKE_PC,
               USERPROFILE=str(home.parents[1]), LOCALAPPDATA=str(home.parents[1] / "AppData" / "Local"))
    return env


def snapshot_state(home: Path) -> dict:
    return {"profile": tree(home / "profiles"), "old_history": tree(home / "save_history" / OLD_STAMP),
            "history_sessions": sorted(p.name for p in (home / "save_history").iterdir()),
            "sessions": sorted(p.name for p in (home / "sessions").iterdir()) if (home / "sessions").is_dir() else None}


def observe(home: Path, stamp: str, r, before: dict) -> dict:
    after = snapshot_state(home)
    s = home / "sessions" / stamp
    info = None
    if (s / "session.json").is_file():
        info = json.loads((s / "session.json").read_text(encoding="utf-8-sig"))
    rep = s / "support_report.txt"
    hist = home / "save_history" / stamp
    return {"rc": r.returncode, "stdout": r.stdout[-1500:], "stderr": r.stderr[-1500:],
            "session_files": sorted(p.name for p in s.iterdir()) if s.is_dir() else None,
            "session": info, "report": rep.read_text(encoding="utf-8") if rep.is_file() else None,
            "history_entry": tree(hist) if hist.is_dir() else None,
            "new_history": [n for n in after["history_sessions"] if n not in before["history_sessions"]],
            "new_sessions": [n for n in (after["sessions"] or []) if n not in (before["sessions"] or [])],
            "profile_unchanged": after["profile"] == before["profile"],
            "old_history_unchanged": after["old_history"] == before["old_history"],
            "profile_after": after["profile"]}


def run_launch(play: Path, home: Path, stamp: str, code: int = 0, write: bool = False, exe: Path = None,
               mutation: str = "") -> dict:
    harness = home / "app" / "tools" / "_g6p73_launch.ps1"
    text = play.read_text(encoding="utf-8-sig")
    harness.write_text(PREAMBLE + text[text.index("# --- launch ---"):], encoding="utf-8-sig")
    before = snapshot_state(home)
    stub = home / "bin" / "stub"
    r = subprocess.run([str(PS), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness),
                        "-Source", str(play), "-Play", str(home), "-Stamp", stamp,
                        "-Exe", str(exe or stub / "pythonw.exe"), "-Script", str(stub / "stub_game.py"),
                        "-Code", str(code), "-Write", str(home / "profiles/default/user" / SAVE_REL) if write else "",
                        "-Mutation", mutation], cwd=home, env=env_for(home), capture_output=True, text=True,
                       encoding="oem", errors="replace", creationflags=NOWIN, timeout=300)
    harness.unlink()
    return observe(home, stamp, r, before)


def run_dry(home: Path, extra=()) -> dict:
    before = snapshot_state(home)
    full_before = tree(home)
    r = subprocess.run([str(PS), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(home / "app" / "tools" / "play.ps1"), "-UserHome", str(home), *extra, "-DryRun"],
                       cwd=home, env=env_for(home), capture_output=True, text=True, encoding="oem",
                       errors="replace", creationflags=NOWIN, timeout=300)
    out = observe(home, "none", r, before)
    out["created"] = sorted(k for k in tree(home) if k not in full_before and "__pycache__" not in k)
    return out


def last_session(home: Path):
    import r3hd_installer
    return r3hd_installer.last_session(home)


def private_text_absent(text: str, home: Path) -> bool:
    low = (text or "").lower()
    return all(x.lower() not in low for x in (FAKE_USER, FAKE_PC, str(home), "SAVE-SECRET", "--code=", "--write="))


def preflight_cases(base: Path, kind: str, python_dir: Path, play: Path, results: dict):
    def fresh(tag):
        home = build_home(base, f"Rayman pf {kind} {tag}", kind, python_dir, play)
        (home / "data" / "content").mkdir(parents=True)
        (home / "data" / "content" / "Default.xex").write_bytes(b"NOT-THE-GAME")  # wrong hash
        return home

    def bin_files(home):
        for n in ("r3hd.exe", "rexruntime.dll", "rexgpu-xenos.dll", "ffmpeg.dll", "mspack.dll") + (
                ("MSVCP140.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll") if kind == "portable" else ()):
            (home / "bin" / n).write_bytes(b"synthetic")

    cases = {}
    home = fresh("noexe")  # no bin\r3hd.exe at all
    cases["missing_exe"] = (home, run_dry(home))
    home = fresh("badxex")
    bin_files(home)
    cases["invalid_data"] = (home, run_dry(home))
    home = fresh("nodata")
    bin_files(home)
    (home / "data" / "content" / "Default.xex").unlink()
    cases["missing_data"] = (home, run_dry(home))
    home = fresh("settings")
    bin_files(home)
    (home / "settings.json").write_text("{ this is not json", encoding="utf-8")
    cases["malformed_settings"] = (home, run_dry(home))
    home = fresh("argument")
    cases["invalid_argument"] = (home, run_dry(home, ["-Profile", "bad name"]))
    expect = {"missing_exe": "PREFLIGHT: Executable missing", "invalid_data": "PREFLIGHT: Default.xex does not match",
              "missing_data": "PREFLIGHT: Extracted game content missing", "malformed_settings": "Settings refused",
              "invalid_argument": "Profile must be a simple name"}
    for name, (home, out) in cases.items():
        tag = f"{kind}/preflight/{name}"
        results[tag] = out
        check(f"{tag}: exit 1 with the reason ({expect[name]})",
              out["rc"] == 1 and expect[name] in out["stdout"] + out["stderr"], (out["stdout"] + out["stderr"])[-300:])
        check(f"{tag}: no session folder, no save_history entry, nothing new in the home",
              not out["new_sessions"] and not out["new_history"] and not out["created"], str(out["created"])[:300])
        check(f"{tag}: profile and older history unchanged", out["profile_unchanged"] and out["old_history_unchanged"])


def launch_cases(base: Path, kind: str, python_dir: Path, play: Path, results: dict):
    original = {"5841123F/00000001/slot0/slot0": hashlib.sha256(SAVE_BYTES).hexdigest()}

    def tag_of(name):
        return f"{kind}/launch/{name}"

    def genuine(name, out, code, home, stamp):
        tag = tag_of(name)
        results[tag] = out
        s = out["session"] or {}
        check(f"{tag}: exit {0 if code == 0 else 1}", out["rc"] == (0 if code == 0 else 1), out["stderr"][-300:])
        check(f"{tag}: the stand-in ran in the session folder",
              "stub_report.txt" in (out["session_files"] or []))
        check(f"{tag}: genuine session.json unchanged in form (exit code, clean_exit, log; no launcher-only keys)",
              s.get("exit_code") == code and s.get("clean_exit") == (code == 0) and "log" in s
              and not {"record", "outcome", "game_started", "start_error"} & set(s), json.dumps(s)[:300])
        check(f"{tag}: support report written", bool(out["report"]) and f"session: {stamp}" in out["report"]
              and private_text_absent(out["report"], home))
        check(f"{tag}: the copy taken before the start is kept in save_history\\{stamp}\\000",
              out["new_history"] == [stamp] and (out["history_entry"] or {}).get("000/user/" + SAVE_REL.as_posix())
              == original[SAVE_REL.as_posix()], json.dumps(out["history_entry"])[:300])
        check(f"{tag}: older history unchanged", out["old_history_unchanged"])
        last = last_session(home)
        check(f"{tag}: Settings LASTRUN {'ok' if code == 0 else 'failed'}", last[0] == stamp and last[2] == int(code != 0),
              str(last))

    def start_failed(name, out, home, stamp):
        tag = tag_of(name)
        results[tag] = out
        s = out["session"] or {}
        # The Windows message text follows the display language; the cmdlet name and error id do not.
        check(f"{tag}: exit 1 and Start-Process's own error on the console (what the launcher reads)",
              out["rc"] == 1 and "Start-Process :" in out["stderr"]
              and "Microsoft.PowerShell.Commands.StartProcessCommand" in out["stderr"], out["stderr"][-300:])
        check(f"{tag}: session.json is a launcher-only record",
              s.get("record") == "launcher_only" and s.get("outcome") == "start_failed" and s.get("game_started") is False
              and s.get("game_pid") is None and s.get("session") == stamp and bool(s.get("start_error")), json.dumps(s)[:300])
        check(f"{tag}: no game details fabricated (no exit code, duration, log, crash or clean-exit field)",
              not {"exit_code", "exit_hex", "clean_exit", "crash_report", "seconds", "log", "ended"} & set(s), str(sorted(s)))
        rep = out["report"] or ""
        check(f"{tag}: support report states the failed start and is redacted",
              "outcome: start_failed" in rep and "game_started: false" in rep and "start_error:" in rep
              and "exit:" not in rep and private_text_absent(rep, home), rep[:400])
        check(f"{tag}: the console names the session folder and the report",
              "Diagnostics:" in out["stdout"] and "support_report.txt" in out["stdout"], out["stdout"][-300:])
        check(f"{tag}: no save_history entry for an attempt whose game never ran",
              not out["new_history"], str(out["new_history"]))
        check(f"{tag}: profile and older history unchanged", out["profile_unchanged"] and out["old_history_unchanged"])
        last = last_session(home)
        check(f"{tag}: Settings LASTRUN names it as failed (start_failed)", last == (stamp, "start_failed", 1), str(last))

    home = build_home(base, f"Rayman 3 HD {kind}", kind, python_dir, play)
    genuine("normal_exit", run_launch(play, home, "20261120-100000", 0), 0, home, "20261120-100000")
    genuine("nonzero_exit", run_launch(play, home, "20261120-100001", 7), 7, home, "20261120-100001")
    out = run_launch(play, home, "20261120-100002", -1073741819)
    genuine("crash_code_exit", out, -1073741819, home, "20261120-100002")

    # A game that changes the profile at once: the copy taken before the start must hold the original bytes.
    stamp = "20261120-100003"
    out = run_launch(play, home, stamp, 0, write=True)
    results[tag_of("immediate_save_change")] = out
    ent = out["history_entry"] or {}
    rel = "user/" + SAVE_REL.as_posix()
    check(f"{tag_of('immediate_save_change')}: snapshot 000 holds the profile as it was before the start",
          ent.get("000/" + rel) == original[SAVE_REL.as_posix()], json.dumps(ent)[:300])
    changed = hashlib.sha256(SAVE_BYTES + b"-CHANGED-BY-STAND-IN").hexdigest()
    check(f"{tag_of('immediate_save_change')}: the changed save is kept after the session (001)",
          ent.get("001/" + rel) == changed, json.dumps(ent)[:300])
    (home / "profiles/default/user" / SAVE_REL).write_bytes(SAVE_BYTES)  # test-owned profile back to the original

    stamp = "20261120-100004"
    out = run_launch(play, home, stamp, 0, exe=home / "bin" / "r3hd.exe")  # removed after preflight
    start_failed("missing_exe_at_start", out, home, stamp)

    # Unusable session folder: a file where the sessions folder belongs; nothing can be recorded there.
    blocked = build_home(base, f"Rayman blocked {kind}", kind, python_dir, play)
    shutil.rmtree(blocked / "sessions")
    (blocked / "sessions").write_text("not a folder", encoding="utf-8")
    out = run_launch(play, blocked, "20261120-100005", 0)
    results[tag_of("unusable_session_folder")] = out
    check(f"{tag_of('unusable_session_folder')}: exit 1, nothing started or recorded, no save_history entry",
          out["rc"] == 1 and out["session_files"] is None and not out["new_history"] and out["profile_unchanged"]
          and out["old_history_unchanged"], out["stderr"][-300:])

    # Bracketed home: the G6-P72 escape lets it start; the pre-G6-P72 start must now leave the launcher-only record.
    br = build_home(base, f"Rayman 3 HD {kind} [PC]", kind, python_dir, play)
    genuine("bracket_home_normal_exit", run_launch(play, br, "20261120-100006", 0), 0, br, "20261120-100006")
    stamp = "20261120-100007"
    start_failed("bracket_home_unescaped_start", run_launch(play, br, stamp, 0, mutation="unescaped"), br, stamp)


def guard_cases(base: Path, play: Path, results: dict):
    harness = base / "_g6p73_guards.ps1"
    harness.write_text(GUARDS, encoding="utf-8-sig")
    r = subprocess.run([str(PS), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness),
                        "-Source", str(play), "-Keeper", str(TOOLS / "play_savekeeper.ps1"), "-Base", str(base / "guards")],
                       capture_output=True, text=True, encoding="oem", errors="replace", creationflags=NOWIN, timeout=120)
    harness.unlink()
    line = next((l for l in r.stdout.splitlines() if l.startswith("{")), None)
    out = json.loads(line) if line else {"defined": None, "stderr": r.stderr[-300:]}
    results["guards"] = out
    check("guards: play.ps1 defines Remove-R3hdUnstartedSnapshot", out.get("defined") is True, json.dumps(out)[:300])
    check("guards: the one copy of an unchanged profile in a folder this launch made is removed",
          out.get("removable") == [True, False, True], str(out.get("removable")))
    for case in ("existed_before", "profile_changed", "extra_item", "two_copies", "no_keeper"):
        check(f"guards: kept when {case.replace('_', ' ')}", (out.get(case) or [None])[0] is False
              and (case == "no_keeper" or out.get(case)[1] is True) and out.get(case)[2] is True, str(out.get(case)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--python-dir", help="a staged app\\python folder (default: search private/work/*/*/app/python)")
    ap.add_argument("--play", type=Path, default=TOOLS / "play.ps1", help="the play.ps1 under test")
    ap.add_argument("--json", type=Path, help="write every observation here (private evidence)")
    ap.add_argument("--keep", type=Path, help="keep the synthetic homes in this new folder")
    a = ap.parse_args()
    if os.name != "nt" or not PS.is_file():
        print("G6P73_LAUNCH_FAILURE SKIP: needs Windows PowerShell 5.1")
        return 3
    python_dir = find_python(a.python_dir)
    if not python_dir:
        print("G6P73_LAUNCH_FAILURE SKIP: no staged embedded Python matching config/release/payload.json")
        return 3
    play = a.play.resolve()
    results = {}
    with tempfile.TemporaryDirectory(prefix="g6p73_") as tmp:
        base = Path(a.keep).resolve() if a.keep else Path(tmp)
        base.mkdir(parents=True, exist_ok=not a.keep)
        guard_cases(base, play, results)
        for kind in ("installed", "portable"):
            preflight_cases(base, kind, python_dir, play, results)
            launch_cases(base, kind, python_dir, play, results)
    if a.json:
        a.json.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"G6P73_LAUNCH_FAILURE {'PASS' if not failures else 'FAIL'} checks={checks} failures={len(failures)} "
          f"game_starts=0")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
