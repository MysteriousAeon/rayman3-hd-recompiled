#!/usr/bin/env python3
"""G6-P74 (D-323): launcher recovery polish on synthetic installed and portable homes only.

Three parts:
  banner      tools/r3hd_installer.py last_session (the launcher's LASTRUN row) names a launcher-only failed start
              `start_failed` only when session.json has record=launcher_only, outcome=start_failed and
              game_started=false (JSON false), and `start_failed_no_report` when its support_report.txt is missing;
              genuine crashes / abnormal / normal exits keep their values; partial records are `incomplete` (the general
              banner), non-object or broken JSON `unreadable` (no banner). Static: the launcher selects the approved
              wording only for those two values and keeps D-306's text otherwise; the catalog holds the approved
              English and Turkish text. (The compiled launcher's banner is checked by m30_launcher_regression.py.)
  collect     play.ps1 -Collect (run exactly as a person would: -File HOME\\app\\tools\\play.ps1 -UserHome HOME -Collect)
              in homes with spaces, [PC], Unicode and [P-C]{x}; a neighbour folder that the wildcard [PC] matches
              holds a sentinel diagnostics.zip. The archive must be in the selected home's newest session, hold that
              session's files, and nothing else anywhere may change.
  structural  the launch block of play.ps1 (loaded as tools/g6p73_launch_failure_regression.py does: functions by the
              parser, the text from "# --- launch ---" unchanged, hidden, a windowless stand-in) with a development
              structural marker in HOME\\mods: a start Windows refuses ends only the marker this attempt armed;
              pre-existing, concurrently replaced, other-plan, malformed and undeletable (read-only) markers are kept
              byte-identical with an actionable console line; genuine exits keep G5-P4b's behaviour.
Mutations (the fixes removed from a copy of play.ps1) must fail the collect and structural parts.

Nothing starts the game, the launcher or setup. Usage:
  python tools/g6p74_launcher_recovery_regression.py [--python-dir DIR] [--play PLAY_PS1] [--json OUT] [--keep DIR]
Prints G6P74_LAUNCHER_RECOVERY PASS / FAIL; without a pinned embedded Python: SKIP, exit 3.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import g6p73_launch_failure_regression as g73  # noqa: E402
import r3hd_installer  # noqa: E402

APPROVED_EN = "The game couldn't be started. Check the latest support report for details."
APPROVED_TR = "Oyun başlatılamadı. Ayrıntılar için son destek raporunu kontrol edin."
FALLBACK_EN, FALLBACK_TR = "The game couldn't be started.", "Oyun başlatılamadı."
GENERIC_EN = "The last session ended unexpectedly. Logs and support_report.txt: sessions\\{session}"
COLLECT_FIX = "-DestinationPath ([Management.Automation.WildcardPattern]::Escape($zip))"
STRUCT_FIX = "Clear-R3hdUnstartedStructuralSession $python $PSScriptRoot $modsRoot $stamp $structuralMarker }"
STAMP = "20261120-100000"

# Added after g73.PREAMBLE: the mods root play.ps1 computes, and the marker `plan` returned for this attempt.
STRUCT_PREAMBLE = r'''
$modsRoot = Join-Path $play 'mods'
if ($env:G6P74_MARKER) { $structuralMarker = Get-Content -LiteralPath $env:G6P74_MARKER -Raw | ConvertFrom-Json }
'''

failures, checks = [], 0


def check(name, cond, detail=""):
    global checks
    checks += 1
    print(("PASS " if cond else "FAIL ") + name + ("" if cond or not detail else f"  ({detail})"))
    if not cond:
        failures.append(name)
    return bool(cond)


def tree(root: Path) -> dict:
    return g73.tree(root)


# ------------------------------------------------------------------------------------------------- banner --
def banner_cases(base: Path, results: dict):
    def session(home, name, body, report=False):
        s = home / "sessions" / name
        s.mkdir(parents=True)
        (s / "session.json").write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8-sig")
        if report:
            (s / "support_report.txt").write_text("synthetic report\n", encoding="utf-8")

    lo = {"session": STAMP, "record": "launcher_only", "outcome": "start_failed", "game_started": False,
          "game_pid": None, "start_error": "System.IO.FileNotFoundException: synthetic"}
    cases = {
        # name: (session.json body, support report present, expected (exit field, failed))
        "start_failed_with_report": (lo, True, ("start_failed", 1)),
        "start_failed_without_report": (lo, False, ("start_failed_no_report", 1)),
        "genuine_crash": ({"exit_code": -1073741819, "exit_hex": "C0000005", "clean_exit": False,
                           "crash_report": True}, True, ("0xC0000005", 1)),
        "genuine_nonzero_exit": ({"exit_code": 7, "exit_hex": "00000007", "clean_exit": False, "crash_report": False},
                                 True, ("0x00000007", 1)),
        "normal_exit": ({"exit_code": 0, "exit_hex": "00000000", "clean_exit": True, "crash_report": False}, True,
                        ("0x00000000", 0)),
        "partial_outcome_only": ({"session": STAMP, "outcome": "start_failed"}, True, ("incomplete", 1)),
        "partial_no_game_started": ({**{k: v for k, v in lo.items() if k != "game_started"}}, True, ("incomplete", 1)),
        "game_started_true": ({**lo, "game_started": True}, True, ("incomplete", 1)),
        "game_started_zero": ({**lo, "game_started": 0}, True, ("incomplete", 1)),
        "game_started_string": ({**lo, "game_started": "false"}, True, ("incomplete", 1)),
        "record_only": ({"session": STAMP, "record": "launcher_only"}, True, ("incomplete", 1)),
        "broken_json": ('{"record": "launcher_only", "outcome": "start_', True, ("unreadable", 0)),
        "json_list": ('["launcher_only", "start_failed", false]', True, ("unreadable", 0)),
        "json_string": ('"start_failed"', True, ("unreadable", 0)),
    }
    for name, (body, report, want) in cases.items():
        home = base / "banner" / name
        session(home, STAMP, body, report)
        try:
            got = r3hd_installer.last_session(home)
        except Exception as x:  # the pre-G6-P74 engine raised AttributeError on a non-object record
            got = ("raised", type(x).__name__, -1)
        results[f"banner_{name}"] = list(got)
        check(f"banner: {name} -> LASTRUN {want[0]} failed={want[1]}", got == (STAMP, *want), str(got))

    # The newest session decides; an older launcher-only failure does not colour a later normal exit.
    home = base / "banner" / "older_failure_newer_normal"
    session(home, "20261120-090000", lo, True)
    session(home, STAMP, cases["normal_exit"][0], True)
    got = r3hd_installer.last_session(home)
    check("banner: a later normal exit is not shown as a failed start", got == (STAMP, "0x00000000", 0), str(got))
    home = base / "banner" / "no_sessions"
    home.mkdir(parents=True)
    check("banner: no sessions folder -> no LASTRUN failure", r3hd_installer.last_session(home) == ("", "", 0))

    # The launcher's own model row (what the native window parses).
    home = base / "banner" / "start_failed_with_report"
    rows = [l.split("\t") for l in r3hd_installer.launcher_model(home).splitlines()]
    lastrun = next((r for r in rows if r[0] == "LASTRUN"), None)
    check("banner: launcher model row LASTRUN carries start_failed", lastrun == ["LASTRUN", STAMP, "start_failed", "1"],
          str(lastrun))

    # Static: the launcher's selection and the catalog.
    cpp = (TOOLS / "launcher" / "r3hd_launcher.cpp").read_text(encoding="utf-8")
    sel = re.search(r"void UpdateBanner\(\) \{(.*?)\n\}", cpp, re.S).group(1)
    check("banner: launcher shows the approved text only for LASTRUN start_failed",
          f'm.lastFailed && m.lastExit == L"start_failed")\n    banner += L"\\n" + T(L"{APPROVED_EN}")' in sel, sel[:200])
    check("banner: launcher shows the report-free fallback only for start_failed_no_report",
          f'm.lastFailed && m.lastExit == L"start_failed_no_report")\n    banner += L"\\n" + T(L"{FALLBACK_EN}")' in sel)
    generic = GENERIC_EN.replace("\\", "\\\\")
    check("banner: every other failure keeps D-306's text with the session folder",
          f'else if (m.lastFailed)\n    banner += L"\\n" + F(L"{generic}", {{{{L"session", m.lastStamp}}}});' in sel)
    cat = json.loads((ROOT / "config/settings/ui_strings.json").read_text(encoding="utf-8"))["strings"]
    check("banner: catalog holds the approved English and Turkish text",
          cat.get(APPROVED_EN) == {"en": APPROVED_EN, "tr": APPROVED_TR}, str(cat.get(APPROVED_EN)))
    check("banner: catalog holds the fallback (the approved first sentence) in both languages",
          cat.get(FALLBACK_EN) == {"en": FALLBACK_EN, "tr": FALLBACK_TR}, str(cat.get(FALLBACK_EN)))
    check("banner: the fallback makes no support-report claim in either language",
          "report" not in FALLBACK_EN.lower() and "rapor" not in FALLBACK_TR.lower())


# ------------------------------------------------------------------------------------------------ collect --
def run_collect(home: Path):
    return subprocess.run([str(g73.PS), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                           str(home / "app" / "tools" / "play.ps1"), "-UserHome", str(home), "-Collect"],
                          cwd=home, env=g73.env_for(home), capture_output=True, text=True, encoding="oem",
                          errors="replace", creationflags=g73.NOWIN, timeout=300)


def collect_cases(base: Path, kind: str, python_dir: Path, play: Path, results: dict, report=True) -> dict:
    """Returns {check name: passed}. With report=False (a mutation) nothing is counted."""
    out = {}

    def ok(name, cond, detail=""):
        out[name] = bool(cond)
        if report:
            check(name, cond, detail)

    def session_files(home, stamp, marker):
        s = home / "sessions" / stamp
        s.mkdir(parents=True, exist_ok=True)
        (s / "runtime.log").write_text(f"runtime log of {marker}\n", encoding="utf-8")
        (s / "session.json").write_text(json.dumps({"session": stamp, "home": marker}), encoding="utf-8")
        (s / "support_report.txt").write_text(f"report of {marker}\n", encoding="utf-8")
        (s / "launch.json").write_text("{}", encoding="utf-8")
        (s / "notes.bin").write_bytes(b"not collected")
        return s

    # An invalid range such as [P-C] cannot be used at all: powershell.exe -File refuses the script path before
    # play.ps1 runs (a Windows PowerShell 5.1 host limitation that also stops Play; recorded in the G6-P74 report).
    names = {"space": f"Rayman 3 HD {kind}", "bracket": f"Rayman 3 HD {kind} [PC]",
             "unicode": f"Rayman ÜğİşÇ Ω {kind}", "range_brace": f"Rayman 3 HD {kind} [C-P]{{x}}"}
    # The wildcards match "... P" and "... P{x}": a person's other folders that must not be touched.
    games = base / "Users" / g73.FAKE_USER / "Games"
    neighbours = {}
    for tag, n in (("bracket", f"Rayman 3 HD {kind} P"), ("range_brace", f"Rayman 3 HD {kind} P{{x}}")):
        ns = session_files(games / n, "20261120-100009", "NEIGHBOUR")
        (ns / "diagnostics.zip").write_bytes(b"NEIGHBOUR-SENTINEL")
        neighbours[tag] = ns
    homes = {}
    for tag, name in names.items():
        home = g73.build_home(base, name, kind, python_dir, play)
        session_files(home, "20261120-090000", f"{tag}-older")
        homes[tag] = (home, session_files(home, "20261120-100009", tag))
    for tag, (home, sess) in homes.items():
        label = f"collect {kind} {tag}"
        before = {k: v for k, v in tree(games).items() if "__pycache__" not in k}
        r = run_collect(home)
        z = sess / "diagnostics.zip"
        after = {k: v for k, v in tree(games).items() if "__pycache__" not in k}
        rel = (z.relative_to(games)).as_posix()
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        entries = sorted(zipfile.ZipFile(z).namelist()) if z.is_file() else None
        results[label] = {"rc": r.returncode, "stderr": r.stderr[-600:], "entries": entries, "changed": changed}
        ok(f"{label}: exit 0 and the console names this home's archive",
           r.returncode == 0 and f"{sess.name}\\diagnostics.zip" in r.stdout, (r.stdout + r.stderr)[-400:])
        ok(f"{label}: the archive holds exactly the newest session's text files",
           entries == ["launch.json", "runtime.log", "session.json", "support_report.txt"], str(entries))
        same = entries is not None and all(zipfile.ZipFile(z).read(n) == (sess / n).read_bytes() for n in entries)
        ok(f"{label}: archived bytes are this home's own (the report unchanged, so its redaction too)", same)
        ok(f"{label}: nothing else changed (no neighbour or other home touched)", changed == [rel], str(changed))
        if tag in neighbours:
            ok(f"{label}: the wildcard-matching neighbour keeps its sentinel and files",
               (neighbours[tag] / "diagnostics.zip").read_bytes() == b"NEIGHBOUR-SENTINEL")
        if not report:
            continue
        r2 = run_collect(home)   # a second collect replaces the archive (idempotent)
        ok(f"{label}: a second collect succeeds and leaves one archive with the same entries",
           r2.returncode == 0 and z.is_file() and sorted(zipfile.ZipFile(z).namelist()) == entries
           and len(list(sess.glob("diagnostics*"))) == 1, r2.stderr[-300:])
    if report:
        empty = g73.build_home(base, f"Rayman 3 HD {kind} [PC] empty", kind, python_dir, play)
        r = run_collect(empty)
        ok(f"collect {kind}: a home without sessions still refuses with the existing message and exit 1",
           r.returncode == 1 and "No playtest session" in r.stderr and not list(empty.rglob("diagnostics.zip")),
           r.stderr[-300:])
    return out


# --------------------------------------------------------------------------------------------- structural --
def write_marker(path: Path, session: str, plan_sha: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps({"schema": 1, "session": session, "plan_sha256": plan_sha,
                                 "mods": ["g5p1.neutral"], "levels": ["intro_10"],
                                 "written_at": "2026-11-20T10:00:00"}, indent=1).encode("utf-8"))


def run_struct(play: Path, home: Path, stamp: str, armed: Path = None, code: int = 0, exe: Path = None) -> dict:
    harness = home / "app" / "tools" / "_g6p74_launch.ps1"
    text = play.read_text(encoding="utf-8-sig")
    harness.write_text(g73.PREAMBLE + STRUCT_PREAMBLE + text[text.index("# --- launch ---"):], encoding="utf-8-sig")
    before = g73.snapshot_state(home)
    stub = home / "bin" / "stub"
    env = g73.env_for(home)
    env.pop("G6P74_MARKER", None)
    if armed:
        env["G6P74_MARKER"] = str(armed)
    r = subprocess.run([str(g73.PS), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(harness), "-Source", str(play), "-Play", str(home), "-Stamp", stamp,
                        "-Exe", str(exe or stub / "pythonw.exe"), "-Script", str(stub / "stub_game.py"),
                        "-Code", str(code), "-Write", "", "-Mutation", ""], cwd=home, env=env, capture_output=True,
                       text=True, encoding="oem", errors="replace", creationflags=g73.NOWIN, timeout=300)
    harness.unlink()
    return g73.observe(home, stamp, r, before)


def recovery_state(home: Path) -> dict:
    py = home / "app" / "python" / "python.exe"
    r = subprocess.run([str(py), "-B", str(home / "app" / "tools" / "r3hd_mods.py"), "structural-recovery", "--json",
                        "--mods-root", str(home / "mods")], capture_output=True, text=True, creationflags=g73.NOWIN,
                       env=g73.env_for(home), timeout=120)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"raw": r.stdout[-300:] + r.stderr[-300:]}


def structural_cases(base: Path, kind: str, python_dir: Path, play: Path, results: dict, report=True,
                     only=None) -> dict:
    out = {}

    def ok(name, cond, detail=""):
        out[name] = bool(cond)
        if report:
            check(name, cond, detail)

    plan_sha, other_sha = "a" * 64, "b" * 64
    cases = only or ("armed_start_failed", "pre_existing", "concurrent_other_session", "concurrent_other_plan",
                     "malformed", "undeletable", "genuine_abnormal_exit", "genuine_exit0_no_orderly_line")
    for i, case in enumerate(cases):
        label = f"structural {kind} {case}"
        home = g73.build_home(base, f"Rayman struct {kind} {case} [PC]", kind, python_dir, play)
        stamp = f"20261120-1100{i:02d}"
        marker = home / "mods" / "structural_session.json"
        armed = home / "cache" / "armed_marker.json"   # what `plan` returned to this attempt
        write_marker(armed, stamp, plan_sha)
        missing = home / "bin" / "r3hd.exe"
        arg = armed
        exe, code = missing, 0
        if case == "armed_start_failed":
            write_marker(marker, stamp, plan_sha)
        elif case == "pre_existing":      # an earlier session's marker: plan armed nothing for this attempt
            write_marker(marker, "20261119-090000", other_sha)
            arg = None
        elif case == "concurrent_other_session":
            write_marker(marker, "20261120-115959", plan_sha)
        elif case == "concurrent_other_plan":
            write_marker(marker, stamp, other_sha)
        elif case == "malformed":
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_bytes(b"{not json")
        elif case == "undeletable":
            write_marker(marker, stamp, plan_sha)
            os.chmod(marker, stat.S_IREAD)
        elif case == "genuine_abnormal_exit":
            write_marker(marker, stamp, plan_sha)
            exe, code = None, 7
        elif case == "genuine_exit0_no_orderly_line":
            write_marker(marker, stamp, plan_sha)
            exe, code = None, 0
        before = marker.read_bytes()
        o = run_struct(play, home, stamp, arg, code, exe)
        if case == "undeletable":
            os.chmod(marker, stat.S_IREAD | stat.S_IWRITE)
        s = o["session"] or {}
        rec = recovery_state(home)
        results[label] = {"rc": o["rc"], "session": s, "stdout": o["stdout"][-800:], "recovery": rec,
                          "marker_present": marker.exists()}
        kept = marker.exists() and marker.read_bytes() == before
        if case == "armed_start_failed":
            ok(f"{label}: exit 1, launcher-only record, Start-Process's own error",
               o["rc"] == 1 and s.get("record") == "launcher_only" and "Start-Process :" in o["stderr"], o["stderr"][-300:])
            ok(f"{label}: the marker this attempt armed is cleared", not marker.exists())
            ok(f"{label}: the record and console say so",
               s.get("structural_session") == "cleared (no game ran)"
               and "its marker was cleared; no game ran with it" in o["stdout"], o["stdout"][-400:])
            ok(f"{label}: the next launch starts unblocked (structural-recovery: none)", rec.get("marker") == "none", str(rec))
            ok(f"{label}: no save_history entry; profile and older history unchanged",
               not o["new_history"] and o["profile_unchanged"] and o["old_history_unchanged"])
        elif case in ("genuine_abnormal_exit", "genuine_exit0_no_orderly_line"):
            ok(f"{label}: the game ran (exit {code}); G5-P4b keeps the marker without an orderly line", kept
               and o["rc"] == (1 if code else 0), str(o["rc"]))
            ok(f"{label}: genuine session.json has no launcher-only or structural_session field",
               not {"record", "outcome", "game_started", "structural_session"} & set(s), str(sorted(s)))
            ok(f"{label}: the next launch still refuses structural mods (armed)", rec.get("marker") == "armed", str(rec))
        else:
            ok(f"{label}: exit 1 with the launcher-only record", o["rc"] == 1 and s.get("record") == "launcher_only")
            ok(f"{label}: the marker is kept byte-identical", kept)
            if case == "pre_existing":
                ok(f"{label}: nothing attempted (no structural_session field, no console line)",
                   "structural_session" not in s and "Development structural session" not in o["stdout"], str(sorted(s)))
            else:
                ok(f"{label}: the record names it kept and the console gives the recovery command",
                   str(s.get("structural_session", "")).startswith("kept: ")
                   and "structural-recovery clear" in o["stdout"], f"{s.get('structural_session')} | {o['stdout'][-300:]}")
            ok(f"{label}: the next launch still refuses structural mods",
               rec.get("marker") == ("malformed" if case == "malformed" else "armed"), str(rec))
    return out


# ----------------------------------------------------------------------------------------------- mutations --
def mutation_cases(base: Path, python_dir: Path, play: Path, results: dict):
    text = play.read_bytes().decode("utf-8-sig")
    for name, find, repl in (("collect_unescaped", COLLECT_FIX, "-DestinationPath $zip"),
                             ("structural_not_cleared", STRUCT_FIX, "$null }")):
        check(f"mutation {name}: the fix is present in play.ps1 (once)", text.count(find) == 1)
        mut = base / f"mut_{name}" / "play.ps1"
        mut.parent.mkdir(parents=True)
        mut.write_bytes(text.replace(find, repl).encode("utf-8"))
        b = base / f"mut_{name}"
        if name == "collect_unescaped":
            res = collect_cases(b, "installed", python_dir, mut, {}, report=False)
        else:
            res = structural_cases(b, "installed", python_dir, mut, {}, report=False, only=("armed_start_failed",))
        failed = sorted(k for k, v in res.items() if not v)
        results[f"mutation_{name}"] = failed
        check(f"mutation {name}: rejected ({len(failed)} checks fail)", bool(failed), "the mutation passed")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--python-dir", help="a staged app\\python folder (default: search private/work/*/*/app/python)")
    ap.add_argument("--play", type=Path, default=TOOLS / "play.ps1", help="the play.ps1 under test")
    ap.add_argument("--json", type=Path, help="write every observation here (private evidence)")
    ap.add_argument("--keep", type=Path, help="keep the synthetic homes in this new folder")
    ap.add_argument("--no-mutations", action="store_true", help="skip the mutation controls (baseline runs)")
    a = ap.parse_args()
    if os.name != "nt" or not g73.PS.is_file():
        print("G6P74_LAUNCHER_RECOVERY SKIP: needs Windows PowerShell 5.1")
        return 3
    python_dir = g73.find_python(a.python_dir)
    if not python_dir:
        print("G6P74_LAUNCHER_RECOVERY SKIP: no staged embedded Python matching config/release/payload.json")
        return 3
    play = a.play.resolve()
    results = {}
    with tempfile.TemporaryDirectory(prefix="g6p74_") as tmp:
        base = Path(a.keep).resolve() if a.keep else Path(tmp)
        base.mkdir(parents=True, exist_ok=not a.keep)
        banner_cases(base, results)
        for kind in ("installed", "portable"):
            collect_cases(base / f"c_{kind}", kind, python_dir, play, results)
            structural_cases(base / f"s_{kind}", kind, python_dir, play, results)
        if not a.no_mutations:
            mutation_cases(base, python_dir, play, results)
        for p in base.rglob("*"):   # a failed run may leave the read-only control behind
            if p.is_file() and not os.access(p, os.W_OK):
                os.chmod(p, stat.S_IREAD | stat.S_IWRITE)
    if a.json:
        a.json.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"G6P74_LAUNCHER_RECOVERY {'PASS' if not failures else 'FAIL'} checks={checks} failures={len(failures)} "
          f"game_starts=0")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
