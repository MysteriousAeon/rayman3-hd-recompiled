#!/usr/bin/env python3
"""HD+ lighting L1 (D-150, gate G-HDP-L1): an isolated human acceptance folder for the red-correction bypass.

    python tools/hdl_l1_home.py make DIR      DIR under private/work, new or empty; needs a clean tracked tree
    python tools/hdl_l1_home.py check DIR     home, launchers, pristine saves and their sources unchanged
    python tools/hdl_l1_home.py reset DIR hq|tower   (run by the launchers before every launch)

DIR gets the layout of the B13 home (E-339), with its missing-manifest lesson applied from the start:
  * home\\   tools/r3hd_test_home.py make (bin = the current build, data\\content a junction to the extracted data,
            installer record, preset HD+): launcher-model INSTALL / FILES / DATA ok, so Settings opens ready to play;
  * src\\    the FULL git archive of HEAD (Settings resolves reports/milestone1/data/content_manifest.tsv from it;
            B13's first tools-and-config archive made Settings refuse with FileNotFoundError);
  * saves\\  read-only copies from two snapshots of the maintainer's own campaign (play.ps1 save history,
            session 20261013-202020): 017 resumes in fact_22 (Hoodlum Headquarters), 018 in tower_10 (Tower of the
            Leptys). Only slot RAY1 (save, header) and the achievements file are copied, as in an M12 entry (one
            slot per profile; the snapshots' other slot RAY is an early intro_15 save). Sources are only read;
  * four launchers (HQ / Tower x original / bypass) that differ only in -Profile and -RedCorrection; each first
    resets its profile in home\\profiles from saves\\ (so every launch starts from the same save), then runs this
    folder's play.ps1 with -UserHome home -Fullscreen. Extra arguments pass through (`-DryRun`);
  * L1_Settings.cmd (the Settings window of this home) and L1_ACCEPTANCE.md (the checklist, from src).
Nothing outside DIR is written. reset only replaces DIR\\home\\profiles\\l1_*\\user.
"""
import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "private" / "play" / "save_history" / "20261013-202020"
CASES = {
    "hq": {"profile": "l1_hq", "snapshot": "017", "level": "fact_22", "place": "Hoodlum Headquarters"},
    "tower": {"profile": "l1_tower", "snapshot": "018", "level": "tower_10", "place": "Tower of the Leptys"},
}
LAUNCHERS = {"L1_HQ_Original.cmd": ("hq", "original"), "L1_HQ_Bypass.cmd": ("hq", "bypass"),
             "L1_Tower_Original.cmd": ("tower", "original"), "L1_Tower_Bypass.cmd": ("tower", "bypass")}
RECORD = "l1_home.json"


def tree_hashes(top: Path) -> dict:
    out = {}
    for p in sorted(top.rglob("*")):
        if p.is_file():
            out[p.relative_to(top).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def kept(rel: str) -> bool:
    return rel.startswith("achievements/") or rel.endswith("/RAY1/RAY1") or rel.endswith("/RAY1.header")


def source_hashes(source: Path) -> dict:
    return {k: v for k, v in tree_hashes(source).items() if kept(k)}


def has_reparse(top: Path) -> bool:
    for dirpath, dirnames, filenames in os.walk(top):
        for n in dirnames + filenames:
            if os.lstat(os.path.join(dirpath, n)).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                return True
    return False


def launcher_text(name: str, case: str, mode: str, python: str) -> str:
    c = CASES[case]
    lines = [
        "@echo off",
        f"rem HD+ lighting L1 acceptance (D-150, gate G-HDP-L1). Development build only. {c['place']} ({c['level']}),",
        f"rem red correction {mode}. The other three launchers differ only in -Profile / -RedCorrection.",
        "rem Resets this folder's test profile from saves\\ (copies of the maintainer's campaign snapshots), then starts",
        "rem this folder's play.ps1 on this folder's home. Touches no other profile, save or installation.",
        "rem Extra arguments pass through to play.ps1 (for example -DryRun).",
        "setlocal",
        'set "T=%~dp0"',
        'set "T=%T:~0,-1%"',
        'set "R3HD_HOME="',
        'set "R3HD_GAME_DIR="',
        'set "R3HD_BIN_DIR="',
        'set "R3HD_PLAY_ROOT="',
        f'"{python}" "%T%\\src\\tools\\hdl_l1_home.py" reset "%T%" {case}',
        'if errorlevel 1 goto failed',
        f'powershell -NoProfile -ExecutionPolicy Bypass -File "%T%\\src\\tools\\play.ps1" -UserHome "%T%\\home" '
        f'-Profile {c["profile"]} -Fullscreen -RedCorrection {mode} %*',
        'if errorlevel 1 goto failed',
        'if "%~1"=="" pause',
        'exit /b 0',
        ':failed',
        f'echo {name} failed; nothing outside this folder was changed.',
        'if "%~1"=="" pause',
        'exit /b 1',
    ]
    return "\r\n".join(lines) + "\r\n"


def settings_text(python: str) -> str:
    lines = [
        "@echo off",
        "rem HD+ lighting L1 acceptance: the Settings window of this folder's home (to confirm the installation and the",
        "rem HD+ profile). The red-correction switch is hidden there; use the four L1_*.cmd launchers to play.",
        'set "T=%~dp0"',
        'set "T=%T:~0,-1%"',
        'set "R3HD_PLAY_ROOT=%T%\\home"',
        f'start "" "%T%\\r3hd_launcher.exe" --home "%T%\\home" --python "{python}" --tools "%T%\\src\\tools"',
    ]
    return "\r\n".join(lines) + "\r\n"


def load_record(top: Path) -> dict:
    return json.loads((top / RECORD).read_text(encoding="utf-8"))


def reset(top: Path, case: str) -> int:
    top = top.resolve()
    record, c = load_record(top), CASES[case]
    pristine = top / "saves" / case / "user"
    if tree_hashes(pristine) != record["saves"][case]["files"]:
        print(f"refused: {pristine} differs from {RECORD}; rebuild the folder with hdl_l1_home.py make")
        return 1
    profiles = top / "home" / "profiles"
    target = profiles / c["profile"] / "user"
    if has_reparse(profiles):
        print(f"refused: {profiles} contains a junction or link")
        return 1
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(pristine, target, copy_function=shutil.copyfile)
    print(f"L1 save reset: profile {c['profile']} resumes in {c['level']} ({c['place']}), "
          f"save {record['saves'][case]['slot_sha256'][:12]}")
    return 0


def check(top: Path) -> int:
    top = top.resolve()
    record, problems = load_record(top), []
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "r3hd_test_home.py"), "check", str(top / "home")],
                       capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode:
        problems.append("test home")
    for name, h in record["bin"].items():
        if hashlib.sha256((top / "home" / "bin" / name).read_bytes()).hexdigest() != h:
            problems.append(f"bin {name}")
    for case, s in record["saves"].items():
        if tree_hashes(top / "saves" / case / "user") != s["files"]:
            problems.append(f"pristine {case}")
        source = Path(s["source"])
        if source_hashes(source) != s["files"]:
            problems.append(f"source {case} ({source})")
    for name in list(LAUNCHERS) + ["L1_Settings.cmd", "L1_ACCEPTANCE.md", "r3hd_launcher.exe"]:
        if not (top / name).is_file():
            problems.append(f"missing {name}")
    if not (top / "src" / "reports" / "milestone1" / "data" / "content_manifest.tsv").is_file():
        problems.append("src has no content manifest")
    print(f"HDL_L1_HOME {'OK' if not problems else 'NOT_OK ' + ', '.join(problems)} commit={record['commit'][:7]}")
    return 0 if not problems else 1


def make(top: Path) -> int:
    top = top.resolve()
    if not str(top).lower().startswith(str((ROOT / "private" / "work").resolve()).lower() + os.sep):
        raise SystemExit(f"refused: {top} is not under private/work")
    if top.exists() and any(top.iterdir()):
        raise SystemExit(f"refused: {top} exists and is not empty (this tool never overwrites)")
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        raise SystemExit("refused: tracked files differ from HEAD; commit first so src equals the build's commit")
    commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=True).stdout.strip()
    sources = {case: HISTORY / c["snapshot"] / "user" for case, c in CASES.items()}
    before = {case: source_hashes(p) for case, p in sources.items()}
    top.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "r3hd_test_home.py"), "make", str(top / "home"),
                        "--preset", "hdplus"], capture_output=True, text=True)
    (top / "make_home.log").write_text(r.stdout + r.stderr, encoding="utf-8")
    if r.returncode:
        raise SystemExit(f"r3hd_test_home make failed:\n{r.stdout}{r.stderr}")
    tar = top / "src.tar"
    subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", "-o", str(tar), commit], check=True)
    with tarfile.open(tar) as t:
        t.extractall(top / "src")
    tar.unlink()
    shutil.copyfile(ROOT / "private" / "work" / "launcher" / "r3hd_launcher.exe", top / "r3hd_launcher.exe")
    saves = {}
    for case, source in sources.items():
        dest = top / "saves" / case / "user"
        for rel in before[case]:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / rel, dest / rel)
        files = tree_hashes(dest)
        if len(files) != 3 or files != before[case] or source_hashes(source) != files:
            raise SystemExit(f"copy of {source} does not match its source")
        for p in dest.rglob("*"):
            if p.is_file():
                p.chmod(stat.S_IREAD)
        slot = next(k for k in files if k.endswith("/RAY1/RAY1"))
        saves[case] = {**CASES[case], "source": str(source), "files": files, "slot_sha256": files[slot]}
    bins = json.loads((top / "home" / "bin" / "install.json").read_text(encoding="utf-8"))["files"]
    python = sys.executable
    for name, (case, mode) in LAUNCHERS.items():
        (top / name).write_bytes(launcher_text(name, case, mode, python).encode("ascii"))
    (top / "L1_Settings.cmd").write_bytes(settings_text(python).encode("ascii"))
    shutil.copyfile(top / "src" / "reports" / "hdplus_lighting" / "L1_ACCEPTANCE.md", top / "L1_ACCEPTANCE.md")
    record = {"tool": "hdl_l1_home.py", "commit": commit, "bin": bins, "saves": saves,
              "launchers": {n: {"case": c, "red_correction": m} for n, (c, m) in LAUNCHERS.items()},
              "note": "Private human-test folder (G-HDP-L1). home\\data\\content is a junction to the extracted data: "
                      "never delete through it. Saves are private: never share them."}
    (top / RECORD).write_text(json.dumps(record, indent=1), encoding="utf-8")
    for case in CASES:
        if reset(top, case):
            return 1
    return check(top)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("make", "check"):
        sub.add_parser(name).add_argument("dir", type=Path)
    r = sub.add_parser("reset")
    r.add_argument("dir", type=Path)
    r.add_argument("case", choices=sorted(CASES))
    a = ap.parse_args()
    if a.cmd == "make":
        return make(a.dir)
    if a.cmd == "check":
        return check(a.dir)
    return reset(a.dir, a.case)


if __name__ == "__main__":
    raise SystemExit(main())
