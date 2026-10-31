#!/usr/bin/env python3
"""Clearleaf sky (E-351, D-155): an isolated human acceptance folder for the background-colour scene clear.

    python tools/sky_ab_home.py make DIR      DIR under private/work, new or empty; needs a clean tracked tree
    python tools/sky_ab_home.py check DIR     home, launchers, pristine saves and their sources unchanged
    python tools/sky_ab_home.py reset DIR clearleaf|bog   (run by the launchers before every launch)

The layout is that of the L1 folder (tools/hdl_l1_home.py, E-347):
  * home\\   tools/r3hd_test_home.py make (bin = the current build, data\\content a junction to the extracted data,
            installer record, preset HD+), so Settings opens ready to play;
  * src\\    the full git archive of HEAD (Settings and play.ps1 of the build's commit);
  * saves\\  read-only copies of two private M12 save entries (private/saves/NAME/profile): wood_11_human resumes in
            wood_11 (Clearleaf Forest, the opening cinematic), swamp_60_human in swamp_60 (Bog of Murk, at the hut).
            Only slot RAY1 (save, header) and the achievements file are copied. Sources are only read;
  * four launchers (Clearleaf / Bog x original / background) that differ only in -Profile and -SkyClear; each first
    resets its profile in home\\profiles from saves\\ (so every launch starts from the same save), then runs this
    folder's play.ps1 with -UserHome home -Fullscreen. Extra arguments pass through (`-DryRun`);
  * Sky_Settings.cmd (the Settings window of this home) and SKY_ACCEPTANCE.md (the checklist, from src).
Nothing outside DIR is written. reset only replaces DIR\\home\\profiles\\sky_*\\user.
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
ENTRIES = ROOT / "private" / "saves"
CASES = {
    "clearleaf": {"profile": "sky_clearleaf", "entry": "wood_11_human", "level": "wood_11", "place": "Clearleaf Forest"},
    "bog": {"profile": "sky_bog", "entry": "swamp_60_human", "level": "swamp_60", "place": "Bog of Murk"},
}
LAUNCHERS = {"Sky_Clearleaf_Original.cmd": ("clearleaf", "original"),
             "Sky_Clearleaf_Background.cmd": ("clearleaf", "background"),
             "Sky_Bog_Original.cmd": ("bog", "original"), "Sky_Bog_Background.cmd": ("bog", "background")}
RECORD = "sky_home.json"


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
        f"rem Clearleaf sky acceptance (D-155). Development build only. {c['place']} ({c['level']}),",
        f"rem sky clear {mode}. The other three launchers differ only in -Profile / -SkyClear.",
        "rem Resets this folder's test profile from saves\\ (copies of a private save entry), then starts",
        "rem this folder's play.ps1 on this folder's home. Touches no other profile, save or installation.",
        "rem Extra arguments pass through to play.ps1 (for example -DryRun).",
        "setlocal",
        'set "T=%~dp0"',
        'set "T=%T:~0,-1%"',
        'set "R3HD_HOME="',
        'set "R3HD_GAME_DIR="',
        'set "R3HD_BIN_DIR="',
        'set "R3HD_PLAY_ROOT="',
        f'"{python}" "%T%\\src\\tools\\sky_ab_home.py" reset "%T%" {case}',
        'if errorlevel 1 goto failed',
        f'powershell -NoProfile -ExecutionPolicy Bypass -File "%T%\\src\\tools\\play.ps1" -UserHome "%T%\\home" '
        f'-Profile {c["profile"]} -Fullscreen -SkyClear {mode} %*',
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
        "rem Clearleaf sky acceptance: the Settings window of this folder's home (to confirm the installation and the",
        "rem HD+ profile). The sky clear switch is not in Settings; use the four Sky_*.cmd launchers to play.",
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
        print(f"refused: {pristine} differs from {RECORD}; rebuild the folder with sky_ab_home.py make")
        return 1
    profiles = top / "home" / "profiles"
    target = profiles / c["profile"] / "user"
    if has_reparse(profiles):
        print(f"refused: {profiles} contains a junction or link")
        return 1
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(pristine, target, copy_function=shutil.copyfile)
    print(f"Sky save reset: profile {c['profile']} resumes in {c['level']} ({c['place']}), "
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
    for name in list(LAUNCHERS) + ["Sky_Settings.cmd", "SKY_ACCEPTANCE.md", "r3hd_launcher.exe"]:
        if not (top / name).is_file():
            problems.append(f"missing {name}")
    if not (top / "src" / "reports" / "milestone1" / "data" / "content_manifest.tsv").is_file():
        problems.append("src has no content manifest")
    print(f"SKY_HOME {'OK' if not problems else 'NOT_OK ' + ', '.join(problems)} commit={record['commit'][:7]}")
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
    sources = {case: ENTRIES / c["entry"] / "profile" for case, c in CASES.items()}
    before = {case: source_hashes(p) for case, p in sources.items()}
    for case, c in CASES.items():
        entry = json.loads((ENTRIES / c["entry"] / "entry.json").read_text(encoding="utf-8"))
        if entry.get("level_key") != c["level"] or entry.get("slot") != "RAY1":
            raise SystemExit(f"refused: entry {c['entry']} does not resume in {c['level']} from slot RAY1")
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
    (top / "Sky_Settings.cmd").write_bytes(settings_text(python).encode("ascii"))
    shutil.copyfile(top / "src" / "reports" / "clearleaf_sky" / "SKY_ACCEPTANCE.md", top / "SKY_ACCEPTANCE.md")
    record = {"tool": "sky_ab_home.py", "commit": commit, "bin": bins, "saves": saves,
              "launchers": {n: {"case": c, "sky_clear": m} for n, (c, m) in LAUNCHERS.items()},
              "note": "Private human-test folder (D-155). home\\data\\content is a junction to the extracted data: "
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
