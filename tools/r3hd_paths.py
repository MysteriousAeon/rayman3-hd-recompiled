#!/usr/bin/env python3
"""M28 (D-063): where the game data, the executable and the per-user files live; a per-user home; install.

Paths and their precedence (highest first; each path is resolved on its own):
  1. an explicit option (--game-dir / --bin-dir / --play-root; play.ps1 -GameDir / -BinDir / -PlayRoot)
  2. its environment variable (R3HD_GAME_DIR / R3HD_BIN_DIR / R3HD_PLAY_ROOT)
  3. a per-user home (--home / play.ps1 -UserHome, else R3HD_HOME):
       game_dir  = HOME\\data\\content   (tools/r3hd_intake.py extract PACKAGE HOME\\data writes it)
       bin_dir   = HOME\\bin             (r3hd_paths.py install --home HOME copies the build there)
       play_root = HOME                  (profiles\\<name>\\user, cache, sessions, save_history)
       settings  = HOME\\settings.json   (used by play.ps1 when it exists and no -Preset / -SettingsFile is given)
  4. the developer layout of this repository (unchanged since M8):
       private\\extracted\\5841123F, private\\work\\rex\\out\\build\\win-amd64-release, private\\play, no settings file
The suggested home on Windows is %LOCALAPPDATA%\\Rayman3HDRecomp (`default-home`); nothing is created there unless
asked. Existing profiles are never moved: a home starts with no profile; copying one is a person's choice.

usage:
  r3hd_paths.py resolve [--home H] [--game-dir D] [--bin-dir D] [--play-root D] [--json]
  r3hd_paths.py default-home
  r3hd_paths.py init-home HOME [--preset vanilla|hdplus]
  r3hd_paths.py install --home HOME [--from BUILD_DIR]
  r3hd_paths.py selftest
Exit 0 ok, 2 refusal (reason code), 1 failure.
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

ROOT = Path(__file__).resolve().parents[1]
LEGACY = {
    "game_dir": ROOT / "private" / "extracted" / "5841123F",
    "bin_dir": ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release",
    "play_root": ROOT / "private" / "play",
    "settings": None,
}
ENV = {"game_dir": "R3HD_GAME_DIR", "bin_dir": "R3HD_BIN_DIR", "play_root": "R3HD_PLAY_ROOT"}
HOME_REL = {"game_dir": Path("data") / "content", "bin_dir": Path("bin"), "play_root": Path("."),
            "settings": Path("settings.json")}
HOME_MARK = "r3hd_home.json"
# What play.ps1 needs next to the executable; TracyClient.dll is imported by none of them (M27).
RUNTIME_FILES = ("r3hd.exe", "rexruntime.dll", "rexgpu-xenos.dll", "ffmpeg.dll", "mspack.dll")  # M46: the LGPL DLLs (D-084)


class Refusal(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def default_home(env=None) -> Path:
    env = os.environ if env is None else env
    base = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Rayman3HDRecomp"


def resolve(explicit=None, home=None, env=None) -> dict:
    """Return {name: {"path": str|None, "source": ...}} by the precedence in the module text."""
    explicit = explicit or {}
    env = os.environ if env is None else env
    home_src = "option" if home else ("env R3HD_HOME" if env.get("R3HD_HOME") else None)
    # Relative values are taken from the current directory (play.ps1 does the same); the repository default is not.
    home = Path(os.path.abspath(home or env.get("R3HD_HOME"))) if home_src else None
    out = {}
    for name in ("game_dir", "bin_dir", "play_root", "settings"):
        if explicit.get(name):
            out[name] = {"path": os.path.abspath(explicit[name]), "source": "option"}
        elif name in ENV and env.get(ENV[name]):
            out[name] = {"path": os.path.abspath(env[ENV[name]]), "source": f"env {ENV[name]}"}
        elif home is not None:
            p = home / HOME_REL[name]
            if name == "settings" and not p.is_file():
                out[name] = {"path": None, "source": f"home ({home_src}): no settings.json"}
            else:
                out[name] = {"path": os.path.normpath(str(p)), "source": f"home ({home_src})"}
        else:
            p = LEGACY[name]
            out[name] = {"path": str(p) if p else None, "source": "repository default"}
    out["home"] = {"path": str(home) if home is not None else None, "source": home_src or "none"}
    return out


def init_home(home: Path, preset=None, log=print):
    if not home.parent.is_dir():
        raise Refusal("PARENT_MISSING", f"{home.parent} does not exist")
    mark = home / HOME_MARK
    if home.exists() and not mark.is_file() and any(home.iterdir()):
        raise Refusal("HOME_NOT_EMPTY", f"{home} exists, is not empty and is not a Rayman 3 HD home; choose another")
    for sub in ("bin", "profiles", "cache", "sessions"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    if not mark.is_file():
        mark.write_text(json.dumps({"schema": 1, "layout": {k: str(v) for k, v in HOME_REL.items()},
                                    "note": "per-user files of Rayman 3 HD Recompiled; game data and saves here are "
                                            "private: never share or upload them"}, indent=1) + "\n", encoding="utf-8")
    settings = home / "settings.json"
    if preset and not settings.exists():
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "r3hd_settings.py"), "write", str(settings),
                            "--preset", preset], capture_output=True, text=True)
        if r.returncode != 0:
            raise Refusal("SETTINGS_REFUSED", (r.stdout + r.stderr).strip()[-300:])
    log(f"home ready: {home} (game data goes to {home / HOME_REL['game_dir']} via tools/r3hd_intake.py extract "
        f"PACKAGE {home / 'data'})")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def install(home: Path, src: Path, log=print):
    if not (home / HOME_MARK).is_file():
        raise Refusal("NOT_A_HOME", f"{home} has no {HOME_MARK}; run init-home first")
    missing = [n for n in RUNTIME_FILES if not (src / n).is_file()]
    if missing:
        raise Refusal("BUILD_MISSING", f"{src} lacks {', '.join(missing)} (build first)")
    bin_dir = home / "bin"
    bin_dir.mkdir(exist_ok=True)
    record = bin_dir / "install.json"
    known = set(json.loads(record.read_text(encoding="utf-8"))["files"]) if record.is_file() else set()
    unrelated = sorted(p.name for p in bin_dir.iterdir() if p.name not in known | {"install.json"})
    if unrelated:
        raise Refusal("BIN_NOT_EMPTY", f"{bin_dir} holds files this tool did not install: {unrelated[:5]}")
    files = {}
    for n in RUNTIME_FILES:
        tmp = bin_dir / (n + ".partial")
        shutil.copyfile(src / n, tmp)
        os.replace(tmp, bin_dir / n)
        files[n] = sha256(bin_dir / n)
    for stale in sorted(known - set(files)):
        (bin_dir / stale).unlink(missing_ok=True)
    record.write_text(json.dumps({"schema": 1, "from": str(src), "files": files,
                                  "note": "built locally from the user's own game data; contains translated game code: "
                                          "never redistribute"}, indent=1) + "\n", encoding="utf-8")
    log(f"installed {len(files)} files into {bin_dir}")


def selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    r = resolve(env={})
    check("legacy defaults without home or env", all(r[k]["source"] == "repository default" for k in ("game_dir", "bin_dir", "play_root"))
          and r["game_dir"]["path"] == str(LEGACY["game_dir"]) and r["settings"]["path"] is None)
    with tempfile.TemporaryDirectory(prefix="r3hd_paths_") as t:
        t = Path(t)
        home = t / "Home"
        r = resolve(env={"R3HD_HOME": str(home)})
        check("env home derives all paths", r["game_dir"]["path"] == str(home / "data" / "content")
              and r["bin_dir"]["path"] == str(home / "bin") and r["home"]["source"] == "env R3HD_HOME")
        check("no settings.json -> no settings file", r["settings"]["path"] is None)
        r = resolve(home=str(t / "Other"), env={"R3HD_HOME": str(home)})
        check("option home beats env home", r["bin_dir"]["path"] == str(t / "Other" / "bin"))
        r = resolve(env={"R3HD_HOME": str(home), "R3HD_GAME_DIR": str(t / "g")})
        check("specific env beats home", r["game_dir"]["path"] == str(t / "g") and r["bin_dir"]["source"].startswith("home"))
        r = resolve(explicit={"game_dir": str(t / "x")}, env={"R3HD_GAME_DIR": str(t / "g")})
        check("option beats specific env", r["game_dir"]["path"] == str(t / "x"))
        r = resolve(explicit={"bin_dir": "relbin"}, env={"R3HD_HOME": "relhome"})
        check("relative values become absolute from the current directory",
              r["bin_dir"]["path"] == os.path.abspath("relbin") and r["game_dir"]["path"] == os.path.abspath("relhome/data/content"))
        check("default home under LOCALAPPDATA", default_home({"LOCALAPPDATA": str(t)}) == t / "Rayman3HDRecomp")
        busy = t / "busy"
        busy.mkdir()
        (busy / "mine.txt").write_bytes(b"keep")
        try:
            init_home(busy, log=lambda *_: None)
            check("non-empty foreign directory refused", False)
        except Refusal as e:
            check("non-empty foreign directory refused", e.code == "HOME_NOT_EMPTY" and (busy / "mine.txt").read_bytes() == b"keep")
        try:
            init_home(t / "a" / "b", log=lambda *_: None)
            check("missing parent refused", False)
        except Refusal as e:
            check("missing parent refused", e.code == "PARENT_MISSING" and not (t / "a").exists())
        init_home(home, preset="hdplus", log=lambda *_: None)
        init_home(home, preset="vanilla", log=lambda *_: None)
        s = json.loads((home / "settings.json").read_text(encoding="utf-8"))
        check("home created with settings; second init keeps the first choice", (home / HOME_MARK).is_file()
              and s.get("preset") == "hdplus" and not (home / "data").exists())
        r = resolve(env={"R3HD_HOME": str(home)})
        check("settings.json picked up in home", r["settings"]["path"] == str(home / "settings.json"))
        build = t / "build"
        build.mkdir()
        for n in RUNTIME_FILES:
            (build / n).write_bytes(n.encode())
        (build / "r3hd.pdb").write_bytes(b"debug")
        install(home, build, log=lambda *_: None)
        rec = json.loads((home / "bin" / "install.json").read_text(encoding="utf-8"))
        check("install copies runtime files only", sorted(p.name for p in (home / "bin").iterdir())
              == sorted(list(RUNTIME_FILES) + ["install.json"]) and rec["files"]["r3hd.exe"] == hashlib.sha256(b"r3hd.exe").hexdigest())
        (build / "r3hd.exe").write_bytes(b"new")
        install(home, build, log=lambda *_: None)
        check("reinstall replaces its own files", (home / "bin" / "r3hd.exe").read_bytes() == b"new")
        (home / "bin" / "someone_else.dll").write_bytes(b"x")
        try:
            install(home, build, log=lambda *_: None)
            check("unrelated file in bin refused", False)
        except Refusal as e:
            check("unrelated file in bin refused", e.code == "BIN_NOT_EMPTY" and (home / "bin" / "someone_else.dll").is_file())
        try:
            install(t / "nothome", build, log=lambda *_: None)
            check("install needs a home", False)
        except Refusal as e:
            check("install needs a home", e.code == "NOT_A_HOME")
    for n, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {n}")
    failed = sum(not ok for _, ok in checks)
    print(f"R3HD_PATHS_SELFTEST {'PASS' if not failed else 'FAIL'} checks={len(checks)}")
    return 0 if not failed else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["resolve", "default-home", "init-home", "install", "selftest"])
    ap.add_argument("target", nargs="?")
    ap.add_argument("--home")
    ap.add_argument("--game-dir")
    ap.add_argument("--bin-dir")
    ap.add_argument("--play-root")
    ap.add_argument("--from", dest="src")
    ap.add_argument("--preset", choices=["vanilla", "hdplus"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    try:
        if a.cmd == "selftest":
            return selftest()
        if a.cmd == "default-home":
            print(default_home())
        elif a.cmd == "resolve":
            r = resolve({"game_dir": a.game_dir, "bin_dir": a.bin_dir, "play_root": a.play_root}, a.home)
            if a.json:
                print(json.dumps(r, indent=1))
            else:
                for k, v in r.items():
                    print(f"{k:10} {v['path']}  [{v['source']}]")
        elif a.cmd == "init-home":
            if not a.target:
                raise Refusal("USAGE", "init-home HOME")
            init_home(Path(a.target), a.preset)
        elif a.cmd == "install":
            if not a.home:
                raise Refusal("USAGE", "install --home HOME [--from BUILD_DIR]")
            install(Path(a.home), Path(a.src) if a.src else LEGACY["bin_dir"])
    except Refusal as e:
        print(f"R3HD_PATHS REFUSED {e.code}: {e.detail}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
