#!/usr/bin/env python3
"""M29 (D-066): the installer engine of the private prototype: install, verify, repair, update, preset, uninstall.

One installation directory ("home", D-063 layout) holds everything; the engine owns some of it and never touches
the rest:
  installer-owned   app\\ (launcher, tools, configs, private Python runtime), bin\\ (r3hd.exe + runtime DLLs),
                    data\\ (game data extracted locally from the person's own package), cache\\ (shader cache),
                    installer.json, bin\\install.json, r3hd_home.json, the Inno Setup uninstaller files
  the person's      settings.json (the preset; replaced only on an explicit choice), profiles\\ (saves),
                    save_history\\, sessions\\ (diagnostics), mods\\ (M33: imported data mods, managed by
                    r3hd_mods.py; their launch plan lives in cache\\mods), dev_overlay_config\\ (D-114) and any
                    file the engine did not write
D-114: bin\\r3hd.toml is the one file of the person's that can appear in bin\\ (the SDK's developer overlay, F4, saves
it; no payload carries one). Setup re-runs, updates and uninstalls move it, unchanged, to dev_overlay_config\\ instead
of discarding it with bin\\ or leaving bin\\ behind; repair leaves it in place. Any other unknown file stays untouched.
The payload (tools/r3hd_stage.py) is a directory with payload.json (every file, size, SHA-256, role) and the files
under app\\ and bin\\. Game data enters only through tools/r3hd_intake.py: a package by header identity then
extraction judged against the 915-file manifest, or an already extracted tree verified against the same manifest.
Every change is staged in HOME\\.staging-<pid>, checked, then committed by renames under a journal
(HOME\\.r3hd_txn.json); an interrupted commit is rolled back (or finished, once complete) by the next run.

usage:
  r3hd_installer.py check-source SOURCE                       identify a package / extracted tree / folder
  r3hd_installer.py preflight --home H --payload P [--source S]
  r3hd_installer.py install --home H --payload P [--source S] [--preset vanilla|hdplus|custom [--base B]
                    [--set KEY=VALUE ...] [--allow-experimental]] [--reset-settings] [--allow-downgrade]
                    [--verify-data] [--progress] [--cancel-file F] [--desktop-shortcut 0|1]
  r3hd_installer.py verify --home H [--data]                  read-only; exit 3 when something is damaged
  r3hd_installer.py repair --home H --payload P [--source S]
  r3hd_installer.py set-preset --home H --preset P [--base B] [--set KEY=VALUE ...] [--allow-experimental]
  r3hd_installer.py set-option --home H --set KEY=VALUE      one hidden Custom setting, keeping the rest (M48-P)
  r3hd_installer.py status --home H
  r3hd_installer.py uninstall --home H [--remove-user-data --confirm HOME] [--from-uninstaller] [--check]
  r3hd_installer.py configure --home H                        interactive preset change (app\settings.cmd)
  r3hd_installer.py describe-options                          the Custom options, from the preset registry
  r3hd_installer.py launcher-model --home H                   what the Settings launcher shows (M30; tab-separated)
  r3hd_installer.py selftest                                  synthetic fixtures only
Common: --json (full result on stdout), --result-file F (KEY=VALUE lines for the Inno Setup front end),
--releases FILE (test fixture release table; printed in the result). Exit 0 ok, 2 refused, 3 damaged (verify),
1 internal error.
Test hooks (selftest / m29_installer_regression.py only, reported in every result when set):
R3HD_INSTALL_FAULT=<point> or kill:<point>, R3HD_INSTALL_FREE_BYTES=N, R3HD_INSTALL_SYSTEM32=DIR,
R3HD_INSTALL_FAKE_RUNNING=0|1, R3HD_INSTALL_FAKE_LAUNCHER=0|1.
M30 (D-067): the Settings launcher (app\\r3hd_launcher.exe) is an installer-owned payload file like any other. It
holds no setting of its own: it shows launcher-model and saves through set-preset. install / repair / uninstall
refuse while it is open (LAUNCHER_RUNNING), because they replace or remove the folder it runs from.
"""
import argparse
import csv
import datetime
import hashlib
import io
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# No __pycache__ beside the engine: it runs from the installer's payload, whose file list is verified exactly, and
# from HOMEpp, which the uninstaller removes file by file.
sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import r3hd_intake as intake  # noqa: E402  (the one game-data intake, M27)
import r3hd_settings as presets  # noqa: E402  (the one preset resolver, M27)

SCHEMA = 1
PRODUCT = "Rayman 3 HD Recompiled"
STATE = "installer.json"
HOME_MARK = "r3hd_home.json"
LOCK = ".r3hd_install.lock"
TXN = ".r3hd_txn.json"
COMPONENTS = ("app", "bin")
# M33: mods\ = imported data mods; D-114: dev_overlay_config\ = SDK overlay files moved out of bin\ (set_aside_dev_config)
USER_ITEMS = ("settings.json", "profiles", "save_history", "sessions", "mods", "dev_overlay_config")
DEV_CONFIG = "r3hd.toml"
UNINSTALLER = ("unins000.exe", "unins000.dat", "unins000.msg")
RUNTIME_FILES = ("r3hd.exe", "rexruntime.dll", "rexgpu-xenos.dll", "ffmpeg.dll", "mspack.dll")  # M46: the LGPL DLLs (D-084)
VC_RUNTIME = ("MSVCP140.dll", "MSVCP140_ATOMIC_WAIT.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll")
MARGIN = 256 << 20
HOOKS = ("R3HD_INSTALL_FAULT", "R3HD_INSTALL_FREE_BYTES", "R3HD_INSTALL_SYSTEM32", "R3HD_INSTALL_FAKE_RUNNING",
         "R3HD_INSTALL_FAKE_LAUNCHER")
LAUNCHER = "app/r3hd_launcher.exe"
MODEL_SCHEMA = 5  # M31: REQUIRES rows; M32: the keyboard rows (KEY*) replace the read-only CONTROL rows; D-115: PAD*; D-116: PADBUTTON kind, PADGROUP, PADACTION group name

ADVICE = {
    "NOT_XCONTENT": "The selected file is not an Xbox 360 content package. Select the Rayman 3 HD package file "
                    "copied from your console's storage (a file without extension under Content\\...\\5841123F\\000D0000).",
    "UNSUPPORTED_TITLE": "The selected package is not Rayman 3 HD.",
    "UNSUPPORTED_VERSION": "This Rayman 3 HD package is a version this build was not made for. Only the Xbox Live "
                           "Arcade release 0.0.0.1 without title update is supported.",
    "UNSUPPORTED_CONTENT": "This is a Rayman 3 HD download other than the game itself (a title update, save or add-on). "
                           "Select the game package (content type 000D0000).",
    "CORRUPT_HEADER": "The package header is damaged or was edited. Copy the package from your console again.",
    "TRUNCATED": "The package is incomplete. Copy it from your console again and check that the copy finished.",
    "CORRUPT_PACKAGE": "The package's data failed its integrity check. Copy it from your console again.",
    "TREE_MISMATCH": "The game files do not match the supported release exactly (files missing, extra or changed).",
    "NOTHING_FOUND": "No Rayman 3 HD package was found in that folder. Select the package file itself.",
    "AMBIGUOUS": "More than one supported package was found in that folder. Select the package file itself.",
    "UNREADABLE": "The file or folder cannot be read. Check the path and your permissions.",
    "SOURCE_CHANGED": "The package changed while it was being read. Make sure nothing else is writing to it and retry.",
    "OUTPUT_IN_SOURCE": "Choose an installation folder outside the folder that holds your game package.",
    "INSIDE_SOURCE": "Choose an installation folder outside the folder that holds your game package.",
    "HOME_NOT_EMPTY": "The installation folder already contains files that do not belong to Rayman 3 HD "
                      "Recompiled. Choose an empty or new folder.",
    "PARENT_MISSING": "The folder that should contain the installation folder does not exist.",
    "NO_SPACE": "There is not enough free space on the destination drive.",
    "WRITE_FAILED": "Writing to the installation folder failed (permissions, a file in use, or a full drive). "
                    "Nothing was changed.",
    "GAME_RUNNING": "Rayman 3 HD is running. Close the game and try again.",
    "LAUNCHER_RUNNING": "Rayman 3 HD Settings is open. Close it and try again.",
    "PROCESS_QUERY_FAILED": "Windows could not check running applications. No installation action was allowed. "
                            "Try again after closing the game and Settings.",
    "SETTINGS_REFUSED": "These settings cannot be saved.",
    "VC_RUNTIME_MISSING": "The Microsoft Visual C++ Redistributable 2015-2022 (x64) is missing. Install it from "
                          "Microsoft (aka.ms/vs/17/release/vc_redist.x64.exe) and run the installer again.",
    "UNSUPPORTED_OS": "Windows 10 or 11, 64-bit (x64), is required.",
    "PAYLOAD_DAMAGED": "The installer's own files are damaged. Download the installer again.",
    "PAYLOAD_MISSING": "The installer's own files were not found.",
    "PACKAGE_REQUIRED": "Select your Rayman 3 HD package: the game data must be extracted from it.",
    "RELEASE_MISMATCH": "The selected game data is a different release than this build needs.",
    "PRESET_REQUIRED": "Choose Vanilla, HD+ or Custom.",
    "SETTINGS_INCOMPATIBLE": "Your saved settings are not valid for this version. They were left unchanged; "
                             "choose a preset again (or install with --reset-settings).",
    "DOWNGRADE": "A newer version is installed. Uninstall it first, or use --allow-downgrade.",
    "INSTALL_NEWER": "This installation was made by a newer installer. Use that installer or a newer one.",
    "NOT_INSTALLED": "Rayman 3 HD Recompiled is not installed in this folder.",
    "PAYLOAD_MISMATCH": "This installer is a different version than the installed one. Repair with the installer of "
                        "the installed version, or install this version as an update.",
    "DATA_SOURCE_REQUIRED": "The installed game data is damaged. Select your Rayman 3 HD package to restore it.",
    "BUSY": "Another installer operation is running in this folder (or one stopped without cleaning up its lock).",
    "CONFIRMATION_REQUIRED": "Removing saves and settings needs an explicit confirmation naming the folder.",
    "CANCELLED": "The installation was cancelled. Nothing was changed in the installation folder.",
}


class Refusal(Exception):
    def __init__(self, code, detail, **extra):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.extra = code, detail, extra


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(p: Path, data):
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def is_within(child: Path, parent: Path) -> bool:
    try:
        Path(os.path.abspath(child)).relative_to(os.path.abspath(parent))
        return True
    except ValueError:
        return False


def rmtree(p: Path):
    if p.is_dir():
        shutil.rmtree(p)
    elif p.exists():
        p.unlink()


def fault(point: str):
    """Test-only failure injection (R3HD_INSTALL_FAULT=point | kill:point)."""
    want = os.environ.get("R3HD_INSTALL_FAULT", "")
    if want == point:
        raise OSError(f"injected fault at {point}")
    if want == "kill:" + point:
        sys.stdout.flush()
        os._exit(70)


def test_hooks():
    return {k: os.environ[k] for k in HOOKS if os.environ.get(k)}


# --- progress (M31) -----------------------------------------------------------------------------------------------

# Relative cost of one byte in each phase, so that the bar moves evenly in time. Calibrated on a real install of the
# supported package (reports/milestone31/REPORT.md section 9); a wrong weight makes the time estimate less exact,
# never the bar untrue: every unit is a byte actually written or checked.
# Measured (M31, E-164): 2.1 GB extracted in 10.9 s and hashed in 13.0 s; the 70 MB application copied and hashed in
# 0.7 s. Hashing a byte costs about 1.2 times extracting it.
WEIGHTS = {"payload": 1.0, "extract": 1.0, "check": 1.2, "copy": 1.0, "verify": 1.2, "commit": 1.0}
LABELS = {"payload": "Copying the application", "extract": "Extracting the game files from your package",
          "check": "Checking your game files", "copy": "Copying your game files",
          "verify": "Checking every extracted game file", "commit": "Finishing the installation"}


class Cancelled(Refusal):
    """The person cancelled (the front end's cancel file). Raised before the commit only; every handler that cleans up
    after a refusal (staging, a partial extraction, a new empty home) cleans up after it."""

    def __init__(self, detail):
        super().__init__("CANCELLED", detail)


class Progress:
    """M31 (D-068): the real progress of an install, as lines on stdout for the Inno Setup front end:
         R3HD_STEP <phase> <label>
         R3HD_PROGRESS <permille> <eta seconds, -1 = not yet known> <phase> <files done>/<files> <bytes done>/<bytes>
    plan() names the phases and their bytes before any work; begin() / add() are called by the work itself (payload
    copy, game-data extraction, validation, commit). The permille is the weighted share of bytes done; the estimate is
    the elapsed time scaled by the share left, given once 3 % and 3 seconds are done. While a cancel file exists, the
    next add() raises Cancelled, until commit() makes the change irreversible."""

    def __init__(self, emit=None, cancel_file=None, clock=None):
        self.emit, self.cancel_file = emit, Path(cancel_file) if cancel_file else None
        self.clock = clock or time.monotonic
        self.phases, self.total, self.base, self.phase = {}, 1.0, 0.0, None
        self.done = self.files = 0
        self.started = self.clock()
        self.last = -1.0
        self.calls = 0
        self.cancellable = True
        self.seconds = {}
        self._phase_start = self.started

    def plan(self, phases):
        """phases: [(name, bytes, files)], in order."""
        self.phases = {n: (b, f, i) for i, (n, b, f) in enumerate(phases)}
        self.order = [n for n, _, _ in phases]
        self.total = max(1.0, sum(b * WEIGHTS[n] for n, b, _ in phases))

    def begin(self, name):
        if name not in self.phases:
            return
        now = self.clock()
        if self.phase is not None:
            self.seconds[self.phase] = round(now - self._phase_start, 2)
        self._phase_start = now
        self.base = sum(self.phases[n][0] * WEIGHTS[n] for n in self.order[:self.order.index(name)])
        self.phase, self.done, self.files = name, 0, 0
        if self.emit:
            self.emit(f"R3HD_STEP {name} {LABELS.get(name, name)}")
        self.report(force=True)

    def add(self, nbytes, files=0):
        self.done += nbytes
        self.files += files
        self.calls += 1
        if self.calls % 64 == 0 or files:
            self.report()

    def check_cancel(self):
        if self.cancellable and self.cancel_file is not None and self.cancel_file.exists():
            raise Cancelled(str(self.cancel_file))

    def fraction(self):
        if self.phase is None:
            return 0.0
        b = self.phases[self.phase][0]
        return min(1.0, (self.base + min(self.done, b) * WEIGHTS[self.phase]) / self.total)

    def report(self, force=False):
        self.check_cancel()
        now = self.clock()
        if not force and now - self.last < 0.25:
            return
        self.last = now
        if not self.emit or self.phase is None:
            return
        f = self.fraction()
        elapsed = now - self.started
        eta = round(elapsed * (1 - f) / f) if f >= 0.03 and elapsed >= 3 else -1
        b, n, _ = self.phases[self.phase]
        self.emit(f"R3HD_PROGRESS {int(f * 1000)} {eta} {self.phase} {min(self.files, n)}/{n} {min(self.done, b)}/{b}")

    def commit(self):
        """From here the change is made: cancellation is no longer offered."""
        self.check_cancel()
        self.cancellable = False
        self.begin("commit")

    def finish(self):
        if self.phase is not None:
            self.seconds[self.phase] = round(self.clock() - self._phase_start, 2)
        if self.emit:
            self.emit(f"R3HD_PROGRESS 1000 0 done 0/0 0/0")


class _NoProgress:
    def begin(self, name): pass
    def add(self, nbytes, files=0): pass
    def commit(self): pass
    def finish(self): pass


# --- environment checks -------------------------------------------------------------------------------------------

def check_platform():
    machine = (os.environ.get("PROCESSOR_ARCHITEW6432") or platform.machine() or "").upper()
    # platform.machine() comes from the environment; without it the 64-bit Python runtime itself says x64.
    if os.name != "nt" or (machine and machine not in ("AMD64", "X86_64")) or sys.maxsize <= 2 ** 32:
        raise Refusal("UNSUPPORTED_OS", f"{platform.system()} {machine or 'unknown machine'}")
    if sys.getwindowsversion().major < 10:
        raise Refusal("UNSUPPORTED_OS", f"Windows {platform.version()}")
    sys32 = Path(os.environ.get("R3HD_INSTALL_SYSTEM32") or Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")
    missing = [n for n in VC_RUNTIME if not (sys32 / n).is_file()]
    if missing:
        raise Refusal("VC_RUNTIME_MISSING", f"missing in {sys32}: {', '.join(missing)}")


def _parse_process_snapshot(stdout: bytes, encoding="oem") -> list[tuple[str, int]]:
    """Full tasklist CSV only: absence is proven by valid rows, never a localized message."""
    if not isinstance(stdout, bytes) or not stdout:
        raise ValueError("missing process-query output")
    rows = list(csv.reader(io.StringIO(stdout.decode(encoding)), strict=True))
    result = []
    for row in rows:
        if not row:
            continue
        if (len(row) != 5 or not row[0] or any(c in row[0] for c in '\x00\r\n')
                or not row[1].isascii() or not row[1].isdecimal()):
            raise ValueError("malformed process-query row")
        result.append((row[0].lower(), int(row[1])))
    if not result:
        raise ValueError("empty process snapshot")
    return result


def _process_snapshot() -> list[tuple[str, int]]:
    # tasklist writes OEM, not ANSI. Decode on this thread so failures are observable.
    # A full list avoids translated /FI no-match messages, whose meaning is not machine-readable.
    exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tasklist.exe"
    try:
        r = subprocess.run([str(exe), "/FO", "CSV", "/NH"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30)
        if r.returncode != 0:
            raise ValueError(f"tasklist exit {r.returncode}")
        return _parse_process_snapshot(r.stdout)
    except (OSError, subprocess.SubprocessError, ValueError, LookupError, csv.Error) as e:
        raise Refusal("PROCESS_QUERY_FAILED", f"{type(e).__name__}: {e}") from e


def image_running(image: str, hook: str) -> bool:
    fake = os.environ.get(hook)
    if fake in ("0", "1"):
        return fake == "1"
    return any(name == image.lower() for name, _ in _process_snapshot())


def game_running() -> bool:
    return image_running("r3hd.exe", "R3HD_INSTALL_FAKE_RUNNING")


def check_not_running():
    """install / repair / uninstall: neither the game nor the Settings launcher may run from this folder (M30)."""
    if game_running():
        raise Refusal("GAME_RUNNING", "r3hd.exe is running")
    if image_running("r3hd_launcher.exe", "R3HD_INSTALL_FAKE_LAUNCHER"):
        raise Refusal("LAUNCHER_RUNNING", "r3hd_launcher.exe is running")


def process_alive(pid: int) -> bool:
    try:
        return any(found == pid for _, found in _process_snapshot())
    except Refusal:
        return True  # cannot tell: keep the lock


def recover_if_needed(home: Path, log) -> str:
    """Run the journal recovery before any precondition that the interrupted state would fail (M29 review)."""
    if home.is_dir() and ((home / TXN).is_file() or any(home.glob(".staging-*"))):
        with Lock(home):
            return recover(home, log)
    return "clean"


def free_bytes(p: Path) -> int:
    fake = os.environ.get("R3HD_INSTALL_FREE_BYTES")
    if fake:
        return int(fake)
    while not p.exists() and p.parent != p:
        p = p.parent
    return shutil.disk_usage(p).free


# --- payload ------------------------------------------------------------------------------------------------------

def safe_rel(rel: str) -> bool:
    parts = rel.split("/")
    return (parts[0] in COMPONENTS and len(parts) > 1 and all(p and p not in (".", "..") and ":" not in p and "\\" not in p
                                                             for p in parts))


def load_payload(p: Path, verify=True) -> dict:
    mf = p / "payload.json"
    if not mf.is_file():
        raise Refusal("PAYLOAD_MISSING", f"{mf} not found")
    try:
        data = read_json(mf)
    except ValueError as e:
        raise Refusal("PAYLOAD_DAMAGED", f"payload.json: {e}")
    if data.get("schema") != SCHEMA or not isinstance(data.get("files"), dict):
        raise Refusal("PAYLOAD_DAMAGED", f"payload.json schema {data.get('schema')!r}")
    bad = [r for r in data["files"] if not safe_rel(r)]
    if bad:
        raise Refusal("PAYLOAD_DAMAGED", f"unsafe payload paths: {bad[:3]}")
    if verify:
        present = {q.relative_to(p).as_posix() for q in p.rglob("*") if q.is_file()} - {"payload.json"}
        extra = sorted(present - set(data["files"]))
        missing = sorted(set(data["files"]) - present)
        damaged = [r for r, i in sorted(data["files"].items()) if r in present
                   and ((p / r).stat().st_size != i["size"] or sha256(p / r) != i["sha256"])]
        if extra or missing or damaged:
            raise Refusal("PAYLOAD_DAMAGED", f"extra {extra[:3]}, missing {missing[:3]}, damaged {damaged[:3]}")
    return data


DUALSENSE_SINCE = "1.0.1"
NEW_IN_DUALSENSE = ("dualsense_light", "dualsense_trigger")


def upgrade_defaults(data):
    """D-108: the DualSense light bar and R2 resistance are on in a new installation (install_default). A home updated
    from a version that had no such options (before 1.0.1) holds no choice about them, so it gets the same values. A
    1.0.1 home that does not name one keeps Off: before preserve_default an explicit Off was not stored. Returns the
    settings with the added preferences, or None when nothing is added (a named value is never changed)."""
    if not data or not isinstance(data.get("schema"), int) or data["schema"] < 2:
        return None
    reg = presets.load_registry()
    named = presets.preferences_of(reg, data)
    add = {k: reg["settings"][k]["install_default"] for k in NEW_IN_DUALSENSE if k not in named}
    if not add:
        return None
    out = json.loads(json.dumps(data))
    out["preferences"] = dict(sorted({**(out.get("preferences") or {}), **add}.items()))
    presets.resolve(reg, settings=out)  # never persist a file that would not resolve
    return out


def version_key(v: str):
    core = v.split("-")[0]
    return tuple(int(x) for x in core.split("."))


# --- releases and game data ---------------------------------------------------------------------------------------

def load_releases(path=None) -> list:
    return intake.load_releases(Path(path)) if path else intake.load_releases()


def required_release(payload: dict, releases: list) -> dict:
    rid = payload["requires"]["release"]
    for r in releases:
        if r["id"] == rid:
            if r["executable"]["sha256"] != payload["requires"]["executable_sha256"]:
                raise Refusal("RELEASE_MISMATCH", f"{rid}: the release table and the payload disagree on Default.xex")
            return r
    raise Refusal("RELEASE_MISMATCH", f"the payload needs {rid}, which the release table does not list")


def check_source(source: Path, releases: list) -> dict:
    """Identify a package / extracted tree / folder with the intake (header check only for a package)."""
    try:
        r = intake.identify(source, releases)
    except intake.Refused as e:
        raise Refusal(e.code, e.detail)
    out = {"kind": r["kind"], "release": r["release"], "path": str(Path(r.get("path", source)).resolve())}
    if r["kind"] == "package":
        out["content_id"] = r["fields"]["content_id"]
        out["display_name"] = r["fields"]["display_name"]
        out["size"] = r["fields"]["size"]
    else:
        out["files"] = r["files"]
    return out


def stage_data(src: dict, dst: Path, release: dict, releases: list, log, progress=None) -> dict:
    """Write dst/content + dst/intake.json from a checked source; the source is only read. progress (M31): phases
    extract + verify (a package) or check + copy + verify (an extracted tree)."""
    progress = progress or _NoProgress()
    if src["kind"] == "package":
        log("extracting and validating the game data (915 files, about 2 GB)")
        try:
            return intake.extract(Path(src["path"]), dst, releases, progress)
        except intake.Refused as e:
            raise Refusal(e.code, e.detail)
    log("copying and validating the extracted game data (915 files, about 2 GB)")
    tree = Path(src["path"])
    manifest = intake.load_manifest(release)
    try:
        intake.verify_tree(tree, release, manifest, progress, "check")
    except intake.Refused as e:
        raise Refusal(e.code, e.detail)
    content = dst / "content"
    progress.begin("copy")
    for rel in sorted(manifest):
        target = content.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tree.joinpath(*rel.split("/")), target)
        progress.add(manifest[rel][0], files=1)
    try:
        verified = intake.verify_tree(content, release, manifest, progress)
    except intake.Refused as e:
        raise Refusal(e.code, f"the copy does not verify: {e.detail}")
    record = {"tool": "r3hd_installer.py", "tool_version": SCHEMA, "release": release["id"],
              "source": {"kind": "tree", "path": str(tree)},
              "content": {"directory": "content", "files": verified["files"],
                          "manifest_sha256": release["content"]["manifest_sha256"],
                          "executable_sha256": release["executable"]["sha256"]},
              "note": "Copied locally from the person's own extracted data. Game data: never redistribute this directory."}
    write_json(dst / "intake.json", record)
    return record


PLAY_ICON = "play_icon.ico"  # in data\: game-derived, made locally, never redistributed (like data\content)


def play_icon_bytes(package: Path, content_id: str = None):
    """The package's own 64x64 title thumbnail (a PNG in the XContent header at 0x171A, its size at 0x1712) as a
    one-image ICO (Windows reads PNG entries), or None. Read only from the person's package; never shipped."""
    try:
        fields = intake.read_header(package)
        if content_id and fields.get("content_id") != content_id:
            return None
        with open(package, "rb") as f:
            h = f.read(0x171A + 0x4000)
    except (intake.Refused, OSError):
        return None
    n = struct.unpack_from(">I", h, 0x1712)[0] if len(h) >= 0x171A else 0
    png = h[0x171A:0x171A + n]
    if not 0 < n <= 0x4000 or len(png) != n or png[:8] != b"\x89PNG\r\n\x1a\n" or png[12:16] != b"IHDR":
        return None
    w, ht = struct.unpack_from(">II", png, 16)
    if not (0 < w <= 256 and 0 < ht <= 256):
        return None
    return struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", w % 256, ht % 256, 0, 0, 1, 32, n, 22) + png


def write_play_icon(home: Path) -> bool:
    """Post-1.0.0 UX: data/play_icon.ico for the Play shortcuts, from the package the data came from (recorded in
    data/intake.json) while it is still there; an existing icon is kept. False: none (the launcher's own icon)."""
    dst = home / "data" / PLAY_ICON
    try:
        src = read_json(home / "data" / "intake.json").get("source", {})
        # Package extraction records predate source.kind; their verified content_id identifies the package.
        package_source = src.get("kind") == "package" or (src.get("kind") is None and bool(src.get("content_id")))
        ico = play_icon_bytes(Path(src["path"]), src.get("content_id")) if package_source else None
    except (OSError, ValueError, KeyError, TypeError):
        ico = None
    if ico is None:
        return dst.is_file()
    if not dst.is_file() or dst.read_bytes() != ico:
        dst.write_bytes(ico)
    return True


def data_state(home: Path, release: dict, full=False) -> dict:
    data = home / "data"
    rec = data / "intake.json"
    if not rec.is_file() or not (data / "content").is_dir():
        return {"state": "missing"}
    try:
        r = read_json(rec)
    except ValueError:
        return {"state": "damaged", "detail": "intake.json unreadable"}
    if r.get("release") != release["id"] or r.get("content", {}).get("manifest_sha256") != release["content"]["manifest_sha256"]:
        return {"state": "other_release", "detail": r.get("release")}
    manifest = intake.load_manifest(release)
    if full:
        try:
            intake.verify_tree(data / "content", release, manifest)
        except intake.Refused as e:
            return {"state": "damaged", "detail": e.detail}
        return {"state": "ok", "checked": "sha256"}
    content = data / "content"
    missing, wrong = [], []
    for rel, (size, _sha) in manifest.items():
        f = content.joinpath(*rel.split("/"))
        if not f.is_file():
            missing.append(rel)
        elif f.stat().st_size != size:
            wrong.append(rel)
    if missing or wrong:
        return {"state": "damaged", "detail": f"{len(missing)} missing, {len(wrong)} wrong size", "missing": missing[:5],
                "wrong_size": wrong[:5]}
    return {"state": "ok", "checked": "sizes"}


# --- settings -----------------------------------------------------------------------------------------------------

def settings_from_args(preset, base, pairs, allow_exp, home: Path = None, fresh=False, keyboard=None,
                       ui_language=None, controller=None) -> dict:
    """A settings file for an explicit choice. With home, the preferences of its readable settings.json (display
    mode, rendering resolution, ...) are carried over: they do not belong to a preset (M30, D-067). fresh = the first
    settings file of a brand-new installation: the registry's install defaults apply unless a pair names them (M31,
    D-068: a new installation starts in fullscreen; an existing one keeps its choice). M32 (D-069): the keyboard map
    is carried over the same way unless keyboard (layout, {input: keys}) replaces it; a stored map that does not
    validate is not carried (set_preset keeps a copy of that file first). D-115: the controller button map likewise,
    unless controller ({input: button}) replaces it."""
    reg = presets.load_registry()
    keep = presets.install_defaults(reg) if fresh else None
    if fresh and ui_language is not None:
        if ui_language not in reg["settings"]["ui_language"]["values"]:
            raise Refusal("USAGE", "ui-language takes en or tr")
        keep["ui_language"] = ui_language
    if fresh and (base if preset == "custom" else preset) == "hdplus":
        keep["gameplay_subtitles"] = "all"  # D-090: a fresh HD+ (or Custom on HD+) starts with them; Vanilla does not
    keep_keys = keep_pad = None
    carry = {}
    if not fresh and home is not None and (home / "settings.json").is_file():
        try:
            old = presets.load_settings_file(home / "settings.json")
            keep = presets.preferences_of(reg, old)
            keep_keys = presets.keyboard_of(presets.load_keymap(), old)
            keep_pad = presets.controller_of(presets.load_padmap(), old)
            carry = hidden_overrides(reg, old)
        except presets.Refused:
            keep = None
    if preset == "custom" and carry:
        # M48-P: a Custom choice that does not name a hidden override (the Settings launcher never shows one, e.g. the
        # experimental gameplay subtitles) keeps it, with the experimental permission it needs; a fixed preset drops it.
        named = {str(p).split("=", 1)[0] for p in pairs}
        extra = [f"{k}={v}" for k, v in carry.items() if k not in named]
        pairs = list(pairs) + extra
        allow_exp = allow_exp or any(reg["settings"][p.split("=", 1)[0]]["category"] == "experimental" for p in extra)
    try:
        if keyboard is not None:
            keep_keys = presets.keyboard_section(presets.load_keymap(), keyboard[0], keyboard[1])
        if controller is not None:
            keep_pad = presets.controller_section(presets.load_padmap(), controller)
        return presets.make_settings(reg, preset, base, pairs, allow_exp, keep, keep_keys, keep_pad)
    except presets.Refused as e:
        raise Refusal("SETTINGS_REFUSED", f"{e.code}: {e.detail}")


def hidden_overrides(reg: dict, settings: dict) -> dict:
    """M48-P: the Custom overrides of ui "hidden" settings that are not preferences (gameplay_subtitles)."""
    if not settings or settings.get("preset") != "custom":
        return {}
    out = {}
    for key, value in (settings.get("overrides") or {}).items():
        s = reg["settings"].get(key)
        if s is not None and s.get("ui") == "hidden" and presets.scope(s) != "preference" and value in s["values"]:
            out[key] = value
    return out


def set_ui_language(home: Path, value: str) -> dict:
    """Change only the UI preference. In particular, do not normalize or replace saved keyboard data."""
    recover_if_needed(home, lambda *_: None)
    with Lock(home):
        st = read_state(home)
        if st is None:
            raise Refusal("NOT_INSTALLED", str(home))
        try:
            data = presets.load_settings_file(home / "settings.json")
            preferences = data.get("preferences", {})
            if not isinstance(preferences, dict):
                raise Refusal("SETTINGS_REFUSED", "preferences must be an object")
            if preferences.get("ui_language") == value:
                return {"action": "set-option", "changed": False, "home": str(home), "preset": settings_state(home)}
            # Schema 1 predates preferences. Its existing fields retain their exact values.
            data["schema"] = max(2, data["schema"])
            data["preferences"] = {**preferences, "ui_language": value}
            presets.resolve_presets(presets.load_registry(), settings=data)
        except presets.Refused as e:
            raise Refusal("SETTINGS_REFUSED", f"{e.code}: {e.detail}")
        write_json(home / "settings.json", data)
        st["settings"] = data
        st["history"] = (st.get("history", []) + [{"action": "set-ui-language", "at": now()}])[-50:]
        write_json(home / STATE, st)
    return {"action": "set-option", "changed": True, "home": str(home), "preset": settings_state(home)}


def set_option(home: Path, key: str, value: str) -> dict:
    """M48-P: one adjustable non-preference setting (the playtest setup's gameplay subtitles) without choosing a preset:
    a fixed preset becomes Custom on that preset, Custom keeps its base and overrides; the value is stored explicitly,
    also when it equals the base (an explicit Off is a choice). An equal value of a fixed preset changes nothing."""
    home = Path(os.path.abspath(home))
    reg = presets.load_registry()
    s = reg["settings"].get(key)
    if s is None or s["category"] == "mandatory":
        raise Refusal("USAGE", f"set-option takes an adjustable setting, not {key!r}")
    if value not in s["values"]:
        raise Refusal("USAGE", f"{key} takes one of {', '.join(s['values'])}")
    if key == "ui_language":
        return set_ui_language(home, value)
    data = {"preset": "vanilla"}
    if (home / "settings.json").is_file():
        try:
            data = presets.load_settings_file(home / "settings.json")
        except presets.Refused as e:
            raise Refusal("SETTINGS_REFUSED", f"{e.code}: {e.detail}")
    if presets.scope(s) == "preference":
        # D-090: a preference (gameplay subtitles) never changes the preset; the resolved preset is kept
        cur = presets.resolve(reg, settings=data) if data.get("schema") else {"preset": "vanilla", "base": "vanilla",
                                                                               "values": {key: s["vanilla"]}}
        if cur["values"].get(key) == value and (not s.get("preserve_default") or
                                               presets.preferences_of(reg, data).get(key) == value):
            return {"action": "set-option", "home": str(home), "changed": False, "preset": settings_state(home)}
        pairs = [f"{k}={v}" for k, v in (data.get("overrides") or {}).items() if k != key] + [f"{key}={value}"]
        allow = data.get("allow_experimental") is True and cur["preset"] == "custom"
        r = set_preset(home, cur["preset"], cur["base"] if cur["preset"] == "custom" else None,
                       pairs if cur["preset"] == "custom" else [f"{key}={value}"], allow)
        return {**r, "action": "set-option", "changed": True}
    if data.get("preset") in ("vanilla", "hdplus"):
        base, overrides = data["preset"], {}
        if value == s[base]:
            return {"action": "set-option", "home": str(home), "changed": False, "preset": settings_state(home)}
    else:
        base, overrides = data.get("base") or "vanilla", dict(data.get("overrides") or {})
        if overrides.get(key) == value:
            return {"action": "set-option", "home": str(home), "changed": False, "preset": settings_state(home)}
    overrides[key] = value
    allow = data.get("allow_experimental") is True or any(
        reg["settings"][k]["category"] == "experimental" and v != reg["settings"][k]["values"][0]
        for k, v in overrides.items() if k in reg["settings"])
    r = set_preset(home, "custom", base, [f"{k}={v}" for k, v in overrides.items()], allow)
    return {**r, "action": "set-option", "changed": True}


def keyboard_state(home: Path) -> dict:
    """M32 (D-069): the keyboard map a launch from this home uses (the resolver's view of settings.json)."""
    km = presets.load_keymap()
    section = None
    f = home / "settings.json"
    if f.is_file():
        try:
            section = presets.load_settings_file(f).get("keyboard")
        except presets.Refused:
            section = None
    return presets.resolve_keyboard(km, section)


def controller_state(home: Path) -> dict:
    """D-115: the controller button map a launch from this home uses (the resolver's view of settings.json)."""
    section = None
    f = home / "settings.json"
    if f.is_file():
        try:
            section = presets.load_settings_file(f).get("controller")
        except presets.Refused:
            section = None
    return presets.resolve_controller(presets.load_padmap(), section)


def settings_state(home: Path) -> dict:
    f = home / "settings.json"
    if not f.is_file():
        return {"state": "missing"}
    try:
        data = presets.load_settings_file(f)
        out = presets.resolve(presets.load_registry(), settings=data)
    except presets.Refused as e:
        return {"state": "invalid", "detail": f"{e.code}: {e.detail}"}
    return {"state": "ok", "preset": out["preset"], "label": out["label"], "values": out["values"],
            "warnings": out["warnings"]}


def invalid_copy_path(home: Path) -> Path:
    """Where an unreadable settings.json is kept before it is replaced; never an existing file (M30)."""
    stem = f"settings.json.invalid-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    p, n = home / stem, 1
    while p.exists():
        n += 1
        p = home / f"{stem}-{n}"
    return p


# --- home, lock, journal ------------------------------------------------------------------------------------------

def read_state(home: Path):
    p = home / STATE
    if not p.is_file():
        return None
    try:
        s = read_json(p)
    except ValueError:
        raise Refusal("STATE_DAMAGED", f"{p} is unreadable; reinstall into a new folder or remove it by hand")
    if not isinstance(s.get("schema"), int) or s["schema"] > SCHEMA:
        raise Refusal("INSTALL_NEWER", f"{p} has schema {s.get('schema')!r}, this engine reads {SCHEMA}")
    return s


def check_home_for_fresh(home: Path):
    if home.exists() and not home.is_dir():
        raise Refusal("HOME_NOT_EMPTY", f"{home} is a file")
    if not home.exists():
        if not home.parent.is_dir():
            raise Refusal("PARENT_MISSING", f"{home.parent} does not exist")
        return
    allowed = set(USER_ITEMS) | set(UNINSTALLER) | {HOME_MARK, LOCK, "cache"}
    foreign = sorted(p.name for p in home.iterdir() if p.name not in allowed and not p.name.startswith(".staging-")
                     and not p.name.startswith("settings.json.invalid-"))
    if foreign:
        raise Refusal("HOME_NOT_EMPTY", f"{home} holds {foreign[:5]}")


class Lock:
    def __init__(self, home: Path):
        self.path = home / LOCK

    def __enter__(self):
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # M29 review: a lock left by a killed engine is taken over when its process no longer exists.
            if not self.stale():
                raise Refusal("BUSY", f"{self.path} is held by a running installer operation")
            self.path.unlink()
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, json.dumps({"pid": os.getpid(), "at": now()}).encode())
        os.close(fd)
        return self

    def stale(self) -> bool:
        try:
            pid = int(json.loads(self.path.read_text(encoding="utf-8"))["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            return True  # unreadable or half-written: no live owner can be named
        if pid == os.getpid():
            return False
        return not process_alive(pid)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except OSError:
            pass


def recover(home: Path, log) -> str:
    """Finish or roll back an interrupted commit; remove staging left by an interrupted preparation."""
    t = home / TXN
    if not t.is_file():
        for s in home.glob(".staging-*"):
            log(f"removing an interrupted preparation: {s.name}")
            rmtree(s)
        return "clean"
    j = read_json(t)
    if j.get("state") == "committed":
        log("finishing an interrupted installation (all files were already in place)")
        finish(home, j)
        return "finished"
    log("rolling back an interrupted installation (the previous files are restored)")
    rollback(home, j)
    return "rolled_back"


def rollback(home: Path, j: dict):
    staging, old = home / j["staging"], home / j["old"]
    for it in reversed(j["items"]):
        # Derived from the file system, not from the journal alone: a kill can land between a rename and its record.
        if (home / it).exists() and staging.is_dir() and not (staging / it).exists():
            os.replace(home / it, staging / it)
        if (old / it).exists() and not (home / it).exists():
            os.replace(old / it, home / it)
    rmtree(staging)
    rmtree(old)
    (home / TXN).unlink()


def finish(home: Path, j: dict):
    rmtree(home / j["old"])
    rmtree(home / j["staging"])
    (home / TXN).unlink()


def commit(home: Path, staging: Path, items: list, log) -> bool:
    """Rename the staged items into place; True when the previous files were also cleaned up."""
    old = home / f".old-{os.getpid()}"
    j = {"schema": SCHEMA, "staging": staging.name, "old": old.name, "items": items, "state": "committing"}
    write_json(home / TXN, j)
    old.mkdir(exist_ok=True)
    try:
        for it in items:
            if (home / it).exists():
                os.replace(home / it, old / it)
            fault(f"commit:{it}")
            os.replace(staging / it, home / it)
        j["state"] = "committed"
        write_json(home / TXN, j)
    except BaseException:
        rollback(home, j)
        raise
    # From here the new files are in place: a cleanup problem is finished by the next run, never reported as failure.
    try:
        fault("before_cleanup")
        finish(home, j)
        return True
    except OSError as e:
        log(f"the new files are in place; removing the previous ones is left to the next run ({e})")
        return False


# --- operations ---------------------------------------------------------------------------------------------------

def copy_payload(payload_dir: Path, payload: dict, staging: Path, only=None, progress=None):
    progress = progress or _NoProgress()
    progress.begin("payload")
    for rel, info in sorted(payload["files"].items()):
        if only is not None and rel not in only:
            continue
        dst = staging.joinpath(*rel.split("/"))
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(payload_dir.joinpath(*rel.split("/")), dst)
        progress.add(info["size"])
        if sha256(dst) != info["sha256"]:
            raise Refusal("WRITE_FAILED", f"{rel} differs after copying")
        progress.add(info["size"], files=1)


def bin_record(payload: dict) -> dict:
    files = {r.split("/", 1)[1]: i["sha256"] for r, i in payload["files"].items() if r.startswith("bin/")}
    return {"schema": 1, "from": f"installer payload {payload['payload_id'][:16]} ({payload['version']})", "files": files,
            "note": "installed by tools/r3hd_installer.py; contains translated game code: never redistribute"}


def home_mark() -> dict:
    return {"schema": 1, "layout": {"game_dir": "data\\content", "bin_dir": "bin", "play_root": ".", "settings": "settings.json"},
            "note": "per-user files of Rayman 3 HD Recompiled; game data and saves here are private: never share or upload them"}


def new_state(payload: dict, data_rec: dict, settings: dict, prev, desktop_shortcut=None, settings_shortcut=None) -> dict:
    hist = list(prev.get("history", [])) if prev else []
    # M31 (D-068): the desktop shortcut choice the front end made (created by Inno Setup, never by the engine). Kept
    # from the previous record unless a new choice is given; the front end never recreates a declined one.
    shortcuts = dict(prev.get("shortcuts", {})) if prev else {}
    if desktop_shortcut is not None:
        shortcuts["desktop"] = bool(desktop_shortcut)
    if settings_shortcut is not None:  # M32 (D-069): the optional desktop shortcut of the Settings window
        shortcuts["desktop_settings"] = bool(settings_shortcut)
    action = "install" if not prev else ("update" if prev.get("version") != payload["version"] or
                                          prev.get("payload_id") != payload["payload_id"] else "reinstall")
    hist.append({"action": action, "version": payload["version"], "payload_id": payload["payload_id"], "at": now()})
    return {"schema": SCHEMA, "product": PRODUCT, "version": payload["version"], "payload_id": payload["payload_id"],
            "files": {r: i["sha256"] for r, i in sorted(payload["files"].items())},
            "data": data_rec, "settings": settings, "owned": ["app", "bin", "data", "cache", STATE, HOME_MARK],
            "shortcuts": shortcuts, "history": hist[-50:],
            "note": "installer state of a private prototype; translated game code and locally extracted game data: "
                    "never redistribute this folder"}


def preflight(home: Path, payload_dir: Path, source=None, releases=None, need_data=True) -> dict:
    check_platform()
    payload = load_payload(payload_dir)
    releases = releases if releases is not None else load_releases()
    release = required_release(payload, releases)
    check_not_running()
    src = None
    if source is not None:
        src = check_source(Path(source), releases)
        if src["release"] != release["id"]:
            raise Refusal("RELEASE_MISMATCH", f"{src['release']} given, {release['id']} needed")
        holder = Path(src["path"]).parent if src["kind"] == "package" else Path(src["path"])
        if is_within(home, holder):
            raise Refusal("INSIDE_SOURCE", f"{home} is inside {holder}")
    need = sum(i["size"] for i in payload["files"].values()) + (release["content"]["bytes"] if need_data else 0) + MARGIN
    free = free_bytes(home)
    if free < need:
        raise Refusal("NO_SPACE", f"{free >> 20} MiB free, {need >> 20} MiB needed", needed=need, free=free)
    return {"payload": payload, "release": release, "source": src, "needed_bytes": need, "free_bytes": free}


def install(home: Path, payload_dir: Path, source=None, preset=None, base=None, pairs=(), allow_exp=False,
            reset_settings=False, allow_downgrade=False, verify_data=False, releases=None, log=print, progress=None,
            desktop_shortcut=None, settings_shortcut=None, ui_language=None) -> dict:
    home = Path(os.path.abspath(home))
    releases = releases if releases is not None else load_releases()
    if source is not None:
        # Before anything is created: never write into the folder that holds the person's package or tree.
        s = Path(os.path.abspath(source))
        holder = s.parent if s.is_file() else s
        if is_within(home, holder):
            raise Refusal("INSIDE_SOURCE", f"{home} is inside {holder}")
    recover_if_needed(home, log)
    if not (home / STATE).is_file():
        check_home_for_fresh(home)
    created = not home.exists()
    home.mkdir(exist_ok=True)
    try:
        return _install(home, payload_dir, source, preset, base, pairs, allow_exp, reset_settings, allow_downgrade,
                        verify_data, releases, log, progress or _NoProgress(), desktop_shortcut,
                        settings_shortcut, ui_language)
    except BaseException:
        if created and home.is_dir() and not any(home.iterdir()):
            home.rmdir()  # a refused first install leaves no empty folder behind
        raise


def _install(home, payload_dir, source, preset, base, pairs, allow_exp, reset_settings, allow_downgrade, verify_data,
             releases, log, progress, desktop_shortcut=None, settings_shortcut=None, ui_language=None) -> dict:
    with Lock(home):
        recovered = recover(home, log)
        prev = read_state(home)
        if prev is None:
            check_home_for_fresh(home)
        payload = load_payload(payload_dir)
        release = required_release(payload, releases)
        if prev:
            if prev["version"] != payload["version"] and version_key(payload["version"]) < version_key(prev["version"]) \
                    and not allow_downgrade:
                raise Refusal("DOWNGRADE", f"installed {prev['version']}, this installer {payload['version']}")
        dstate = data_state(home, release, full=verify_data) if prev else {"state": "missing"}
        need_data = dstate["state"] != "ok"
        if need_data and source is None:
            raise Refusal("PACKAGE_REQUIRED", f"game data {dstate['state']}: a package or extracted tree is needed")
        pf = preflight(home, payload_dir, source if need_data else None, releases, need_data)
        # Settings: an explicit choice is written; otherwise the person's file is kept as it is, never reverted.
        sstate = settings_state(home)
        write_settings = None
        if preset:
            # M31 (D-068): only a home with no installation record and no settings file is new.
            write_settings = settings_from_args(preset, base, pairs, allow_exp, home,
                                                fresh=prev is None and sstate["state"] == "missing",
                                                ui_language=ui_language)
        elif sstate["state"] == "ok":
            pass
        elif sstate["state"] == "invalid" and not reset_settings:
            raise Refusal("SETTINGS_INCOMPATIBLE", sstate["detail"])
        elif prev and prev.get("settings"):
            write_settings = prev["settings"]
        elif sstate["state"] == "invalid":
            write_settings = settings_from_args("vanilla", None, (), False)
        else:
            raise Refusal("PRESET_REQUIRED", "no settings.json and no preset given")
        if prev and version_key(prev["version"]) < version_key(DUALSENSE_SINCE) <= version_key(payload["version"]):
            current = write_settings if write_settings is not None else                 presets.load_settings_file(home / "settings.json") if sstate["state"] == "ok" else None
            write_settings = upgrade_defaults(current) or write_settings
        # M31 (D-068): every phase and its bytes are known before any work; the front end shows their real progress.
        if isinstance(progress, Progress):
            cbytes, cfiles = release["content"]["bytes"], release["content"]["files"]
            pbytes = sum(i["size"] for i in payload["files"].values())
            phases = [("payload", 2 * pbytes, len(payload["files"]))]
            if need_data:
                phases += ([("extract", cbytes, cfiles)] if pf["source"]["kind"] == "package"
                           else [("check", cbytes, cfiles), ("copy", cbytes, cfiles)]) + [("verify", cbytes, cfiles)]
            phases.append(("commit", max(1, sum(b for _, b, _ in phases) // 200), 0))
            progress.plan(phases)
        staging = home / f".staging-{os.getpid()}"
        staging.mkdir()
        try:
            log(f"copying the application ({len(payload['files'])} files)")
            copy_payload(payload_dir, payload, staging, progress=progress)
            write_json(staging / "bin" / "install.json", bin_record(payload))
            fault("after_payload")
            if need_data:
                data_rec = stage_data(pf["source"], staging / "data", release, releases, log, progress)
            else:
                data_rec = prev["data"]
            fault("after_data")
            progress.commit()  # M31: the last moment a cancellation is honoured; nothing in HOME was touched yet
            items = ["app", "bin"] + (["data"] if need_data else [])
            if write_settings is not None:
                if sstate["state"] == "invalid":
                    backup = invalid_copy_path(home)
                    shutil.copyfile(home / "settings.json", backup)
                    log(f"previous settings kept as {backup.name}")
                write_json(staging / "settings.json", write_settings)
                items.append("settings.json")
            kept_settings = write_settings if write_settings is not None else presets.load_settings_file(home / "settings.json")
            write_json(staging / STATE, new_state(payload, data_rec, kept_settings, prev, desktop_shortcut,
                                                    settings_shortcut))
            items.append(STATE)
            if not (home / HOME_MARK).is_file():
                write_json(staging / HOME_MARK, home_mark())
                items.append(HOME_MARK)
            dev_config = set_aside_dev_config(home)  # D-114: the old bin\ is discarded by the commit
            if dev_config:
                log(f"developer overlay settings kept as {dev_config}")
            log("committing")
            cleaned = commit(home, staging, items, log)
        except Refusal:
            rmtree(staging)
            raise
        except OSError as e:
            rmtree(staging)
            raise Refusal("WRITE_FAILED", str(e))
        for d in ("profiles", "cache", "sessions"):
            (home / d).mkdir(exist_ok=True)
        play_icon = write_play_icon(home)
        progress.finish()
        st = read_state(home)
        return {"action": st["history"][-1]["action"], "home": str(home), "version": payload["version"],
                "phase_seconds": getattr(progress, "seconds", {}),
                "payload_id": payload["payload_id"], "data": "extracted" if need_data else "kept",
                "settings": "written" if write_settings is not None else "kept", "recovered": recovered,
                "cleanup_pending": not cleaned, "preset": settings_state(home), "play_icon": int(play_icon),
                "dev_config_set_aside": dev_config}


def verify(home: Path, full_data=False, releases=None) -> dict:
    home = Path(os.path.abspath(home))
    st = read_state(home)
    if st is None:
        raise Refusal("NOT_INSTALLED", str(home))
    missing, damaged = [], []
    for rel, sha in sorted(st["files"].items()):
        f = home.joinpath(*rel.split("/"))
        if not f.is_file():
            missing.append(rel)
        elif sha256(f) != sha:
            damaged.append(rel)
    known = {r.split("/", 1)[1] for r in st["files"] if r.startswith("bin/")} | {"install.json"}
    extra = sorted(p.name for p in (home / "bin").iterdir() if p.name not in known) if (home / "bin").is_dir() else []
    releases = releases if releases is not None else load_releases()
    release = next((r for r in releases if r["id"] == st["data"]["release"]), None)
    d = data_state(home, release, full_data) if release else {"state": "other_release"}
    s = settings_state(home)
    healthy = not missing and not damaged and d["state"] == "ok" and s["state"] == "ok" and not (home / TXN).exists()
    return {"result": "healthy" if healthy else "damaged", "version": st["version"], "files": len(st["files"]),
            "missing": missing, "damaged": damaged, "unexpected_in_bin": extra, "data": d,
            "settings": {k: v for k, v in s.items() if k != "values"}, "interrupted": (home / TXN).exists()}


def repair(home: Path, payload_dir: Path, source=None, releases=None, log=print) -> dict:
    home = Path(os.path.abspath(home))
    recover_if_needed(home, log)
    if not (home / STATE).is_file():
        raise Refusal("NOT_INSTALLED", str(home))
    releases = releases if releases is not None else load_releases()
    with Lock(home):
        recovered = recover(home, log)
        st = read_state(home)
        payload = load_payload(payload_dir)
        if payload["payload_id"] != st["payload_id"]:
            raise Refusal("PAYLOAD_MISMATCH", f"installed {st['version']} ({st['payload_id'][:12]}), "
                                              f"installer {payload['version']} ({payload['payload_id'][:12]})")
        check_platform()
        check_not_running()
        rep = verify(home, full_data=True, releases=releases)
        release = required_release(payload, releases)
        restored = []
        try:
            for rel in rep["missing"] + rep["damaged"]:
                dst = home.joinpath(*rel.split("/"))
                dst.parent.mkdir(parents=True, exist_ok=True)
                tmp = dst.with_name(dst.name + ".repair")
                shutil.copyfile(payload_dir.joinpath(*rel.split("/")), tmp)
                if sha256(tmp) != payload["files"][rel]["sha256"]:
                    raise Refusal("WRITE_FAILED", f"{rel} differs after copying")
                os.replace(tmp, dst)
                restored.append(rel)
            if not (home / "bin" / "install.json").is_file():
                write_json(home / "bin" / "install.json", bin_record(payload))
            if not (home / HOME_MARK).is_file():
                write_json(home / HOME_MARK, home_mark())
        except OSError as e:
            raise Refusal("WRITE_FAILED", str(e))
        data_action = "ok"
        if rep["data"]["state"] != "ok":
            src_path = source or (st["data"].get("source", {}).get("path"))
            if not src_path or not Path(src_path).exists():
                raise Refusal("DATA_SOURCE_REQUIRED", f"game data {rep['data']['state']}: {rep['data'].get('detail', '')}",
                              restored=restored)
            pf = preflight(home, payload_dir, src_path, releases, need_data=True)
            staging = home / f".staging-{os.getpid()}"
            staging.mkdir()
            try:
                rec = stage_data(pf["source"], staging / "data", release, releases, log)
                st["data"] = rec
                commit(home, staging, ["data"], log)
            except Refusal:
                rmtree(staging)
                raise
            except OSError as e:
                rmtree(staging)
                raise Refusal("WRITE_FAILED", str(e))
            data_action = "restored"
        settings_action = "ok"
        s = settings_state(home)
        if s["state"] != "ok":
            if s["state"] == "invalid":
                backup = invalid_copy_path(home)
                os.replace(home / "settings.json", backup)
                log(f"unreadable settings kept as {backup.name}")
            write_json(home / "settings.json", st.get("settings") or settings_from_args("vanilla", None, (), False))
            settings_action = "restored from the installation record"
        for d in ("profiles", "cache", "sessions"):
            (home / d).mkdir(exist_ok=True)
        st["history"] = (st.get("history", []) + [{"action": "repair", "version": st["version"], "at": now(),
                                                    "restored": len(restored), "data": data_action}])[-50:]
        write_json(home / STATE, st)
        return {"action": "repair", "home": str(home), "recovered": recovered, "restored_files": restored,
                "data": data_action, "settings": settings_action, "unexpected_in_bin": rep["unexpected_in_bin"]}


def set_preset(home: Path, preset, base=None, pairs=(), allow_exp=False, keyboard=None, controller=None) -> dict:
    """keyboard (M32): (layout, {input: keys}) replaces the keyboard map; None keeps the saved one. controller
    (D-115): {input: button} replaces the controller button map ({} = the original controls); None keeps it."""
    home = Path(os.path.abspath(home))
    recover_if_needed(home, lambda *_: None)
    if not (home / STATE).is_file():
        raise Refusal("NOT_INSTALLED", str(home))
    data = settings_from_args(preset, base, pairs, allow_exp, home, keyboard=keyboard, controller=controller)
    with Lock(home):
        st = read_state(home)
        if (settings_state(home)["state"] == "invalid" or keyboard_state(home)["state"] == "invalid"
                or controller_state(home)["state"] == "invalid"):
            # M30: an unreadable file is replaced by an explicit choice, never deleted: a copy is kept beside it.
            backup = invalid_copy_path(home)
            shutil.copyfile(home / "settings.json", backup)
        write_json(home / "settings.json", data)
        st["settings"] = data
        st["history"] = (st.get("history", []) + [{"action": "set-preset", "preset": preset, "at": now()}])[-50:]
        write_json(home / STATE, st)
    kb = keyboard_state(home)
    pad = controller_state(home)
    return {"action": "set-preset", "home": str(home), "preset": settings_state(home),
            "keyboard": {"state": kb["state"], "layout": kb["layout"], "keys": kb["keys"]},
            "controller": {"state": pad["state"], "changed": pad["changed"]}}


def configure(home: Path, ask=input, say=print) -> dict:
    """Interactive preset change for a person (app\\settings.cmd); everything goes through set_preset."""
    home = Path(os.path.abspath(home))
    cur = settings_state(home)
    say(f"Rayman 3 HD Recompiled settings ({home})")
    say(f"Current preset: {cur.get('label', cur['state'])}")
    for k, v in sorted(cur.get("values", {}).items()):
        say(f"  {k:15} {v}")
    say("")
    say("  1  Vanilla   Xbox 360 HD presentation with the essential PC compatibility fixes")
    say("  2  HD+       Fixes visual issues inherited from the Xbox 360 HD release")
    say("  3  Custom    choose each adjustable option")
    say("  Enter        keep the current settings")
    choice = ask("Choice: ").strip()
    if not choice:
        say("Nothing changed.")
        return {"action": "configure", "changed": False}
    if choice in ("1", "2"):
        r = set_preset(home, "vanilla" if choice == "1" else "hdplus")
    elif choice == "3":
        pairs = []
        for o in describe_options():
            note = f" [{o['note']}]" if o["note"] else ""
            default = cur.get("values", {}).get(o["key"], o["vanilla"])
            say(f"{o['label']}{note}")
            shown = f"{o['values'][0]} ... {o['values'][-1]}" if o["range"] else " / ".join(o["values"])
            ans = ask(f"  {shown} (Enter = {default}): ").strip() or default
            while ans not in o["values"]:
                ans = ask(f"  one of {shown}: ").strip() or default
            # M30: a preference is always named (set_preset keeps unnamed ones); a correction only when it differs
            if o["scope"] == "preference" or ans != o["vanilla"]:
                pairs.append(f"{o['key']}={ans}")
        r = set_preset(home, "custom", "vanilla", pairs)
    else:
        say("Unknown choice; nothing changed.")
        return {"action": "configure", "changed": False}
    say(f"Saved: {r['preset'].get('label')}. It applies the next time the game starts.")
    return {"action": "configure", "changed": True, "preset": r["preset"]}


def set_aside_dev_config(home: Path):
    """D-114: move bin\\r3hd.toml (the SDK overlay's saved settings) unchanged to dev_overlay_config\\; the target
    name never replaces an earlier file. Returns the new path relative to HOME, or None when there is no such file."""
    src = home / "bin" / DEV_CONFIG
    if not src.is_file() or src.is_symlink():
        return None
    d = home / USER_ITEMS[-1]
    d.mkdir(exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target, n = d / f"r3hd-{stamp}.toml", 1
    while target.exists():
        target, n = d / f"r3hd-{stamp}-{n}.toml", n + 1
    os.replace(src, target)
    return f"{d.name}/{target.name}"


def remove_empty_dirs(root: Path):
    if not root.is_dir():
        return
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass
    try:
        root.rmdir()
    except OSError:
        pass


def uninstall(home: Path, remove_user_data=False, confirm=None, from_uninstaller=False, releases=None, log=print,
              check_only=False) -> dict:
    home = Path(os.path.abspath(home))
    recover_if_needed(home, log)
    if not (home / STATE).is_file():
        raise Refusal("NOT_INSTALLED", str(home))
    if remove_user_data and (not confirm or os.path.normcase(os.path.abspath(confirm)) != os.path.normcase(str(home))):
        raise Refusal("CONFIRMATION_REQUIRED", f"--remove-user-data needs --confirm {home}")
    check_not_running()
    releases = releases if releases is not None else load_releases()
    with Lock(home):
        recover(home, log)
        st = read_state(home)
        if check_only:
            # The uninstaller asks before it deletes anything of its own (M29 review): a refusal here leaves all.
            return {"action": "uninstall-check", "home": str(home), "version": st["version"]}
        self_inside = is_within(Path(sys.executable), home / "app") or is_within(Path(__file__), home / "app")
        defer_app = from_uninstaller or self_inside
        removed = 0
        for rel in sorted(st["files"]):
            if not safe_rel(rel):
                continue  # a damaged or edited record never steers a deletion outside app/ and bin/
            if defer_app and rel.startswith("app/"):
                continue
            f = home.joinpath(*rel.split("/"))
            if f.is_file():
                f.unlink()
                removed += 1
        (home / "bin" / "install.json").unlink(missing_ok=True)
        dev_config = set_aside_dev_config(home)
        remove_empty_dirs(home / "bin")
        if not defer_app:
            remove_empty_dirs(home / "app")
        release = next((r for r in releases if r["id"] == st["data"].get("release")), None)
        data_removed = 0
        if release:
            for rel in intake.load_manifest(release):
                f = home / "data" / "content" / Path(*rel.split("/"))
                if f.is_file():
                    f.unlink()
                    data_removed += 1
        (home / "data" / "intake.json").unlink(missing_ok=True)
        (home / "data" / PLAY_ICON).unlink(missing_ok=True)
        remove_empty_dirs(home / "data")
        rmtree(home / "cache")
        user_removed = []
        if remove_user_data:
            for name in USER_ITEMS:
                if (home / name).exists():
                    rmtree(home / name)
                    user_removed.append(name)
            for f in home.glob("settings.json.invalid-*"):
                f.unlink()
        (home / STATE).unlink()
        kept = [n for n in USER_ITEMS if (home / n).exists()]
        if not kept:
            (home / HOME_MARK).unlink(missing_ok=True)
    left = sorted(p.name for p in home.iterdir()) if home.is_dir() else []
    if not left:
        home.rmdir()
    return {"action": "uninstall", "home": str(home), "removed_app_files": removed, "removed_data_files": data_removed,
            "app_deferred_to_uninstaller": defer_app, "user_data_removed": user_removed, "user_data_kept": kept,
            "dev_config_set_aside": dev_config, "left_in_home": left}


def status(home: Path) -> dict:
    home = Path(os.path.abspath(home))
    st = read_state(home)
    if st is None:
        raise Refusal("NOT_INSTALLED", str(home))
    desktop = st.get("shortcuts", {}).get("desktop")
    desktop_settings = st.get("shortcuts", {}).get("desktop_settings")
    return {"home": str(home), "version": st["version"], "payload_id": st["payload_id"], "release": st["data"]["release"],
            "preset": settings_state(home), "history": st.get("history", [])[-5:], "interrupted": (home / TXN).exists(),
            "desktop_shortcut": "" if desktop is None else str(int(desktop)),
            "settings_shortcut": "" if desktop_settings is None else str(int(desktop_settings)),
            "gameplay_subtitles": settings_state(home).get("values", {}).get("gameplay_subtitles", "")}


def describe_options() -> list:
    """The adjustable settings a person is shown. M31 (D-068): ui "hidden" ones (cursor, save clock) are left out;
    they keep resolving and an existing choice is kept, because set-preset carries unnamed preferences over."""
    reg = presets.load_registry()
    out = []
    for key, s in reg["settings"].items():
        if s["category"] == "mandatory" or s.get("ui") == "hidden":
            continue
        note = ""
        if s["category"] == "experimental":
            note = "experimental"
        elif str(s.get("validation", "")).startswith("pending"):
            note = "not yet visually validated"
        out.append({"key": key, "label": s.get("label", key), "category": s["category"], "values": s["values"],
                    "vanilla": s["vanilla"], "hdplus": s["hdplus"], "note": note, "decision": s["decision"],
                    "scope": presets.scope(s), "group": s.get("group", ""), "help": s.get("help", ""),
                    "value_labels": s.get("value_labels") or {v: v for v in s["values"]},
                    "requires": dict(s.get("requires") or {}), "range": s.get("range")})
    return out


def last_session(home: Path) -> tuple:
    """The newest finished play session (play.ps1 writes session.json at its end): name, exit code, failed."""
    sessions = home / "sessions"
    names = sorted((d.name for d in sessions.iterdir() if (d / "session.json").is_file()), reverse=True) \
        if sessions.is_dir() else []
    for name in names[:1]:
        try:
            s = json.loads((sessions / name / "session.json").read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return name, "unreadable", 0
        failed = not s.get("clean_exit", False) or bool(s.get("crash_report"))
        return name, f"0x{s.get('exit_hex', '')}" if s.get("exit_hex") else str(s.get("exit_code")), int(failed)
    return "", "", 0


def _field(v) -> str:
    return " ".join(str(v).replace("\t", " ").split())


def launcher_model(home: Path, releases=None) -> str:
    """M30 (D-067): everything the Settings launcher shows, as tab-separated lines (no JSON parser in the launcher).
    Read-only and quick (file presence and sizes, no hashing). Row kinds, in this order:
      R3HD_LAUNCHER_MODEL schema | HOME path | PRODUCT name | VERSION v | INSTALL state | FILES state n first |
      DATA state detail | RUNNING 0/1 | LASTRUN session exit failed(0/1) | SETTINGS state preset base label detail |
      PRESET key name text |
      GROUP key name | SETTING key group scope category label help note vanilla hdplus current (11 fields) |
      VALUE key value label | REQUIRES key other value (M31) | SLIDER key min max unit (D-108) |
      KEYBOARD state layout warnings | KEYLAYOUT key name text | KEYGROUP key name |
      KEYINPUT id group hidden(0/1) required(0/1) pad action | KEYDEFAULT layout id key... |
      KEYBIND id key... | KEYNAME name label scans reserved_reason | KEYFALLBACK key input | KEYNOTE text |
      KEYSHARE key input input (D-120, optional collision exception; no settings schema change) |
      PADSTATE state warnings | PADBUTTON id label kind | PADGROUP key name | PADACTION input group name |
      PADBIND input button | END
    The settings rows are the registry's adjustable, shown settings in its order; mandatory behaviour is never
    listed. REQUIRES and SLIDER follow their setting's VALUE rows. M32 (D-069): the keyboard rows are config/controls/keymap.json
    and the resolver's view of the saved map (KEYBIND: the keys a launch uses, one field per slot, '' = empty);
    KEYDEFAULT gives every layout's keys so the window can show a layout or restore one without a rule of its own.
    D-115: the controller rows are config/controls/padmap.json and the resolver's view of the saved map: PADBUTTON in
    the padmap's order, PADACTION the inputs the window lists, PADBIND every input's button (all 14, so a swap with an
    input that is not listed is still shown correctly); the original controls are each input on its own button.
    D-116: PADBUTTON also lists the four analog inputs with their kind (button | trigger | stick) and PADBIND all 18;
    PADGROUP / PADACTION are padmap.json's groups and actions (the input, its group, the action's name)."""
    home = Path(os.path.abspath(home))
    reg = presets.load_registry()
    rows = [("R3HD_LAUNCHER_MODEL", MODEL_SCHEMA), ("HOME", home), ("PRODUCT", PRODUCT)]
    st, install = None, "ok"
    try:
        st = read_state(home)
        if st is None:
            install = "not_installed"
    except Refusal as e:
        install = e.code.lower()
    if st is not None and (home / TXN).exists():
        install = "interrupted"
    rows.append(("VERSION", st["version"] if st else ""))
    rows.append(("INSTALL", install))
    if st:
        missing = [r for r in sorted(st["files"]) if not home.joinpath(*r.split("/")).is_file()]
        rows.append(("FILES", "missing" if missing else "ok", len(missing), missing[0] if missing else ""))
        releases = releases if releases is not None else load_releases()
        release = next((r for r in releases if r["id"] == st["data"].get("release")), None)
        d = data_state(home, release) if release else {"state": "other_release", "detail": st["data"].get("release")}
        rows.append(("DATA", d["state"], d.get("detail", "")))
    else:
        rows.append(("FILES", "unknown", 0, ""))
        rows.append(("DATA", "unknown", ""))
    rows.append(("RUNNING", int(game_running())))
    rows.append(("LASTRUN", *last_session(home)))
    values = {k: s["vanilla"] for k, s in reg["settings"].items()}
    f = home / "settings.json"
    if not f.is_file():
        rows.append(("SETTINGS", "missing", "vanilla", "vanilla", "vanilla", ""))
    else:
        try:
            out = presets.resolve(reg, settings=presets.load_settings_file(f))
            values = out["values"]
            rows.append(("SETTINGS", "ok", out["preset"], out["base"], out["label"], ""))
        except presets.Refused as e:
            rows.append(("SETTINGS", "invalid", "vanilla", "vanilla", "vanilla", f"{e.code}: {e.detail}"))
    for key in ("vanilla", "hdplus", "custom"):
        ui = reg.get("preset_ui", {}).get(key, {})
        rows.append(("PRESET", key, ui.get("name", key), ui.get("text", reg["presets"][key])))
    for key, name in reg.get("groups", {}).items():
        rows.append(("GROUP", key, name))
    for o in describe_options():
        rows.append(("SETTING", o["key"], o["group"] or "advanced", o["scope"], o["category"], o["label"], o["help"],
                     o["note"], o["vanilla"], o["hdplus"], values[o["key"]]))
        for v in o["values"]:
            rows.append(("VALUE", o["key"], v, o["value_labels"].get(v, v)))
        for other, v in o["requires"].items():
            rows.append(("REQUIRES", o["key"], other, v))
        if o["range"]:  # D-108: shown as a slider over its VALUE rows (min ... max)
            rows.append(("SLIDER", o["key"], o["range"]["min"], o["range"]["max"], o["range"].get("unit", "")))
    km = presets.load_keymap()
    kb = keyboard_state(home)
    rows.append(("KEYBOARD", kb["state"], kb["layout"], " ".join(kb["warnings"])))
    for key, layout in km["layouts"].items():
        rows.append(("KEYLAYOUT", key, layout["name"], layout["text"]))
    for g in km["groups"]:
        rows.append(("KEYGROUP", g["key"], g["name"]))
    for share in km.get("shared_keys", []):
        rows.append(("KEYSHARE", share["key"], *share["inputs"]))
    for i in km["inputs"]:
        rows.append(("KEYINPUT", i["id"], i["group"], int(bool(i.get("hidden"))), int(i["id"] in km["required"]),
                     i["pad"], i["action"]))
    for key in km["layouts"]:
        for input_id, keys in presets.layout_keys(km, key).items():
            rows.append(("KEYDEFAULT", key, input_id, *keys))
    for input_id, keys in kb["keys"].items():
        rows.append(("KEYBIND", input_id, *keys))
    for k in km["keys"]:
        rows.append(("KEYNAME", k["name"], k.get("label", k["name"]), ",".join(k["scan"]), km["reserved"].get(k["name"], "")))
    for key, target in km["fallbacks"].items():
        rows.append(("KEYFALLBACK", key, target))
    rows.append(("KEYNOTE", "Escape and Enter also work as Back and Start when no other control uses them."))
    pm = presets.load_padmap(km)
    pad = controller_state(home)
    rows.append(("PADSTATE", pad["state"], " ".join(pad["warnings"])))
    for b in pm["_ids"]:
        rows.append(("PADBUTTON", b, pm["_labels"][b], pm["_kind"][b]))
    for g in pm["groups"]:
        rows.append(("PADGROUP", g["key"], g["name"]))
    for a in pm["actions"]:
        rows.append(("PADACTION", a["input"], a["group"], a["name"]))
    for input_id, b in pad["buttons"].items():
        rows.append(("PADBIND", input_id, b))
    import r3hd_ui_locale as ui_locale
    language = values.get("ui_language", "en")
    rows.append(("LANG", "ui_language", language))
    rows.extend(("UISTRING", key, label) for key, label in ui_locale.rows(language))
    rows.append(("END",))
    def cell(row, value):
        # Source keys may include intentional spaces. Preserve them in catalog rows.
        if row[0] == "UISTRING":
            return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ")
        return _field(value)
    return "".join("\t".join(cell(row, x) for x in row) + "\n" for row in rows)


# --- selftest -----------------------------------------------------------------------------------------------------

def make_fixture(t: Path, version="0.29.0", tag=b"v1"):
    """A synthetic release (manifest + tree) and payload; nothing from the game."""
    tree = t / "src_tree"
    if not tree.exists():
        files = {"Default.xex": b"synthetic xex", "GAMEDATAbin/a.bhf": b"aaa", "GAMEDATAbin/sub/b.btf": b"bbbb"}
        rows = []
        for rel, data in files.items():
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_bytes(data)
            rows.append(f"{rel}\t{len(data)}\t{hashlib.sha256(data).hexdigest()}")
        man = t / "manifest.tsv"
        man.write_bytes(("\n".join(sorted(rows)) + "\n").encode())
        rel_table = {"schema": 1, "releases": [{
            "id": "synthetic-release", "package": {"title_id": "5841123F", "content_id": "00" * 20},
            "content": {"manifest": str(man), "manifest_sha256": hashlib.sha256(man.read_bytes()).hexdigest(),
                        "files": 3, "bytes": sum(len(d) for d in files.values())},
            "executable": {"path": "Default.xex", "sha256": hashlib.sha256(files["Default.xex"]).hexdigest()}}]}
        (t / "releases.json").write_text(json.dumps(rel_table), encoding="utf-8")
    rel_table = json.loads((t / "releases.json").read_text(encoding="utf-8"))
    pl = t / f"payload_{version}_{tag.decode()}"
    files = {"bin/r3hd.exe": b"MZ exe " + tag, "bin/rexruntime.dll": b"MZ rt " + tag, "bin/rexgpu-xenos.dll": b"MZ gpu",
             "app/tools/play.ps1": b"# launcher " + tag, "app/config/settings/registry.json": b"{}",
             "app/r3hd_launcher.exe": b"MZ settings launcher " + tag}
    entries = {}
    for rel, data in files.items():
        (pl / rel).parent.mkdir(parents=True, exist_ok=True)
        (pl / rel).write_bytes(data)
        entries[rel] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "role": "test"}
    pid = hashlib.sha256("".join(f"{r}\t{e['size']}\t{e['sha256']}\n" for r, e in sorted(entries.items())).encode()).hexdigest()
    r0 = rel_table["releases"][0]
    write_json(pl / "payload.json", {"schema": 1, "version": version, "payload_id": pid, "files": entries,
                                     "requires": {"release": r0["id"], "executable_sha256": r0["executable"]["sha256"]}})
    return pl, tree, load_releases(t / "releases.json")


def selftest() -> int:
    checks = []
    DS = {"dualsense_light": "on", "dualsense_trigger": "on"}  # D-108: what a new installation stores

    def check(name, cond):
        checks.append((name, bool(cond)))

    def refused(fn, code):
        try:
            fn()
        except Refusal as e:
            return e.code == code
        return False

    quiet = lambda *_: None  # noqa: E731
    saved = {k: os.environ.get(k) for k in HOOKS}
    os.environ["R3HD_INSTALL_FAKE_RUNNING"] = "0"
    os.environ["R3HD_INSTALL_FAKE_LAUNCHER"] = "0"
    try:
        with tempfile.TemporaryDirectory(prefix="r3hd_inst_") as tmp:
            t = Path(tmp)
            pl, tree, rels = make_fixture(t)
            sys32 = t / "sys32"
            sys32.mkdir()
            for n in VC_RUNTIME:
                (sys32 / n).write_bytes(b"x")
            os.environ["R3HD_INSTALL_SYSTEM32"] = str(sys32)
            tree_before = {p: p.read_bytes() for p in tree.rglob("*") if p.is_file()}
            home = t / "Home"
            r = install(home, pl, tree, "hdplus", releases=rels, log=quiet)
            check("fresh install from an extracted tree", r["action"] == "install" and r["data"] == "extracted"
                  and (home / "bin" / "r3hd.exe").read_bytes() == b"MZ exe v1" and (home / "data" / "content" / "Default.xex").is_file())
            check("source tree untouched", tree_before == {p: p.read_bytes() for p in tree.rglob("*") if p.is_file()})
            check("preset persisted", read_json(home / "settings.json")["preset"] == "hdplus")
            check("no Play icon from an extracted tree (no package header); the launcher's icon is used",
                  r["play_icon"] == 0 and not write_play_icon(home) and not (home / "data" / PLAY_ICON).exists())
            from unittest.mock import patch
            record_path = home / "data" / "intake.json"
            original_record = record_path.read_bytes()
            write_json(record_path, {"source": {"path": "synthetic-package", "content_id": "synthetic-id"}})
            with patch.object(sys.modules[__name__], "play_icon_bytes", return_value=b"synthetic icon") as thumbnail:
                check("package extraction record without kind creates Play icon using verified content id",
                      write_play_icon(home) and (home / "data" / PLAY_ICON).read_bytes() == b"synthetic icon"
                      and thumbnail.call_args.args == (Path("synthetic-package"), "synthetic-id"))
            (home / "data" / PLAY_ICON).unlink()
            record_path.write_bytes(original_record)
            check("verify healthy", verify(home, True, rels)["result"] == "healthy")
            check("no staging, journal or lock left", not list(home.glob(".staging-*")) and not list(home.glob(".old-*"))
                  and not (home / TXN).exists() and not (home / LOCK).exists())
            (home / "profiles" / "default" / "user").mkdir(parents=True)
            (home / "profiles" / "default" / "user" / "save.dat").write_bytes(b"SAVE")
            # repair
            (home / "bin" / "rexruntime.dll").write_bytes(b"corrupt")
            (home / "app" / "tools" / "play.ps1").unlink()
            (home / "data" / "content" / "GAMEDATAbin" / "a.bhf").write_bytes(b"aaX")
            rep = verify(home, True, rels)
            check("verify finds damage", rep["result"] == "damaged" and rep["damaged"] == ["bin/rexruntime.dll"]
                  and rep["missing"] == ["app/tools/play.ps1"] and rep["data"]["state"] == "damaged")
            r = repair(home, pl, releases=rels, log=quiet)
            check("repair restores files and data, keeps saves", r["data"] == "restored" and len(r["restored_files"]) == 2
                  and verify(home, True, rels)["result"] == "healthy"
                  and (home / "profiles" / "default" / "user" / "save.dat").read_bytes() == b"SAVE")
            (home / "settings.json").write_text("{broken", encoding="utf-8")
            r = repair(home, pl, releases=rels, log=quiet)
            check("repair restores unreadable settings from the record and keeps the broken copy",
                  read_json(home / "settings.json")["preset"] == "hdplus" and list(home.glob("settings.json.invalid-*")))
            check("repair with another payload refused", refused(lambda: repair(home, make_fixture(t, "0.30.0", b"v2")[0],
                                                                                releases=rels, log=quiet), "PAYLOAD_MISMATCH"))
            check("a new installation starts in fullscreen, a new HD+ one with gameplay subtitles (D-090); repair "
                  "restores that from the record (M31)",
                  read_json(home / "settings.json")["preferences"] == {"display": "fullscreen", "gameplay_subtitles": "all", **DS})
            set_preset(home, "hdplus", pairs=["display=windowed"])
            check("choosing the window stores the default (nothing) and resolves windowed (M31)",
                  read_json(home / "settings.json")["preferences"] == {"gameplay_subtitles": "all", **DS}
                  and settings_state(home)["values"]["display"] == "windowed")
            # preset change without reinstall
            r = set_preset(home, "custom", "hdplus", ["cursor=visible"])
            s = read_json(home / "settings.json")
            check("set-preset custom; a preference goes to preferences (M30)", s["preset"] == "custom"
                  and s["overrides"] == {} and s["preferences"] == {"cursor": "visible", "gameplay_subtitles": "all", **DS} and s["schema"] == 3
                  and (home / "bin" / "r3hd.exe").read_bytes() == b"MZ exe v1")
            # M30 (D-067): preferences survive a preset change; custom overrides do not
            set_preset(home, "custom", "vanilla", ["texture_orient=corrected", "render_scale=2"])
            set_preset(home, "hdplus")
            s = read_json(home / "settings.json")
            check("switching to a fixed preset keeps preferences and drops custom overrides", s["preset"] == "hdplus"
                  and "overrides" not in s and s["preferences"] == {"cursor": "visible", "gameplay_subtitles": "all", "render_scale": "2", **DS})
            set_preset(home, "vanilla", pairs=["render_scale=auto", "display=fullscreen"])
            s = read_json(home / "settings.json")
            check("a preference set back to its default is not stored; a fixed preset takes preferences",
                  s["preset"] == "vanilla" and s["preferences"] == {"cursor": "visible", "display": "fullscreen",
                                                                    "gameplay_subtitles": "all", **DS})
            set_option(home, "gameplay_subtitles", "original")
            check("gameplay subtitles turned off on vanilla: the default, not stored (D-090)",
                  read_json(home / "settings.json")["preferences"] == {"cursor": "visible", "display": "fullscreen", **DS})
            check("a correction on a fixed preset is refused", refused(lambda: set_preset(home, "hdplus", None,
                                                                                          ["texture_orient=corrected"]), "SETTINGS_REFUSED"))
            # D-090: gameplay subtitles are a preference; set-option never changes the preset (the 1.0.0 report:
            # an HD+ installation shown as Custom because the installer stored them as a Custom override on HD+)
            r = set_option(home, "gameplay_subtitles", "all")
            s = read_json(home / "settings.json")
            check("set-option (D-090): gameplay subtitles on vanilla stay vanilla, as a preference",
                  r["changed"] and s["preset"] == "vanilla" and "overrides" not in s and "allow_experimental" not in s
                  and s["preferences"] == {"cursor": "visible", "display": "fullscreen", "gameplay_subtitles": "all", **DS}
                  and status(home)["gameplay_subtitles"] == "all")
            set_preset(home, "hdplus")
            check("a preset change keeps the gameplay subtitle preference (D-090)",
                  read_json(home / "settings.json")["preset"] == "hdplus"
                  and settings_state(home)["values"]["gameplay_subtitles"] == "all"
                  and not set_option(home, "gameplay_subtitles", "all")["changed"])
            set_preset(home, "custom", "vanilla", ["texture_orient=corrected"])
            set_option(home, "gameplay_subtitles", "original")
            s = read_json(home / "settings.json")
            check("set-option Off on Custom keeps Custom and its overrides (D-090)",
                  s["preset"] == "custom" and s["overrides"] == {"texture_orient": "corrected"}
                  and settings_state(home)["values"]["gameplay_subtitles"] == "original"
                  and refused(lambda: set_option(home, "revisit", "original"), "USAGE"))
            # the reported file: a 1.0.0 HD+ installation with gameplay subtitles on
            (home / "settings.json").write_text('{"schema": 3, "preset": "custom", "base": "hdplus", "overrides": '
                                                '{"gameplay_subtitles": "all"}, "allow_experimental": true, '
                                                '"preferences": {"display": "fullscreen"}}', encoding="utf-8")
            rows = launcher_model(home, rels).splitlines()
            check("a 1.0.0 HD+ file (Custom holding only gameplay subtitles) reads as HD+ with subtitles on (D-090)",
                  any(x.startswith("SETTINGS	ok	hdplus	hdplus	hdplus") for x in rows)
                  and settings_state(home)["values"]["gameplay_subtitles"] == "all")
            set_option(home, "gameplay_subtitles", "original")
            set_option(home, "gameplay_subtitles", "all")
            check("its first save migrates it to HD+ with the preference, keeping the others (D-090)",
                  read_json(home / "settings.json") == {"schema": 3, "preset": "hdplus", "preferences":
                                                        {"display": "fullscreen", "gameplay_subtitles": "all"}})
            set_option(home, "gameplay_subtitles", "original")
            set_preset(home, "vanilla", pairs=["render_scale=auto", "display=fullscreen"])
            (home / "settings.json").write_text('{"schema": 1, "preset": "custom", "base": "hdplus", "overrides": '
                                                '{"cursor": "visible", "render_scale": "3", "texture_orient": "corrected"}}',
                                                encoding="utf-8")
            m = dict((row.split("\t")[1], row.split("\t")) for row in launcher_model(home, rels).splitlines()
                     if row.startswith("SETTING\t"))
            check("an M29 (schema 1) custom file stays valid; its preferences are read as preferences",
                  settings_state(home)["state"] == "ok" and m["render_scale"][-1] == "3" and m["texture_orient"][-1] == "corrected"
                  and m["layer_coords"][-1] == "separate")
            set_preset(home, "hdplus")
            s = read_json(home / "settings.json")
            check("an M29 file's preferences survive the next preset change", s["preferences"] == {"cursor": "visible",
                                                                                                    "render_scale": "3"})
            before = (home / "settings.json").read_bytes()
            (home / "settings.json").write_text("{broken", encoding="utf-8")
            n_invalid = len(list(home.glob("settings.json.invalid-*")))
            model = launcher_model(home, rels)
            check("launcher-model reports an unreadable file and shows vanilla values",
                  "\nSETTINGS\tinvalid\tvanilla\t" in model and model.endswith("END\n"))
            set_preset(home, "hdplus")
            check("set-preset over an unreadable file keeps a copy of it",
                  len(list(home.glob("settings.json.invalid-*"))) == n_invalid + 1 and read_json(home / "settings.json")["preset"] == "hdplus")
            (home / "settings.json").write_bytes(before)
            rows = launcher_model(home, rels).splitlines()
            kinds = [r.split("\t")[0] for r in rows]
            check("launcher-model: header, state rows, presets, settings with every value, end",
                  kinds[:10] == ["R3HD_LAUNCHER_MODEL", "HOME", "PRODUCT", "VERSION", "INSTALL", "FILES", "DATA", "RUNNING",
                                 "LASTRUN", "SETTINGS"]
                  and kinds.count("PRESET") == 3 and kinds[-1] == "END" and "\t".join(rows[4].split("\t")[1:]) == "ok"
                  and rows[5] == "FILES\tok\t0\t" and rows[6].startswith("DATA\tok") and rows[8] == "LASTRUN\t\t\t0"
                  and rows[9].startswith("SETTINGS\tok\thdplus\thdplus\thdplus"))
            (home / "sessions" / "20261014-120000").mkdir(parents=True)
            (home / "sessions" / "20261014-120000" / "session.json").write_text(
                '{"exit_code": -1073741819, "exit_hex": "C0000005", "clean_exit": false, "crash_report": true}',
                encoding="utf-8-sig")
            check("launcher-model reports a failed last session", "\nLASTRUN\t20261014-120000\t0xC0000005\t1\n"
                  in launcher_model(home, rels))
            shutil.rmtree(home / "sessions" / "20261014-120000")
            check("launcher-model never lists mandatory behaviour", not any(r.startswith(("SETTING\trevisit", "SETTING\tpacing"))
                                                                            for r in rows))
            check("launcher-model rows have a fixed width", all(len(r.split("\t")) == {"SETTING": 11, "VALUE": 4, "PRESET": 4,
                                                                                    "REQUIRES": 4, "KEYINPUT": 7,
                                                                                    "KEYBIND": 4, "KEYDEFAULT": 5, "KEYSHARE": 4,
                                                                                    "KEYNAME": 5, "KEYBOARD": 4}
                                                                .get(r.split("\t")[0], len(r.split("\t"))) for r in rows))
            km = presets.load_keymap()
            check("launcher-model (M31/M32): window size requires the window mode; keyboard listed; hidden settings absent",
                  "REQUIRES\twindow_size\tdisplay\twindowed" in rows and kinds.count("KEYINPUT") == len(km["inputs"])
                  and kinds.count("KEYBIND") == len(km["inputs"]) and "KEYBIND\ta\tSpace\t" in rows
                  and "KEYBOARD\tdefault\tmodern\t" in rows
                  and kinds.count("KEYDEFAULT") == len(km["inputs"]) * len(km["layouts"])
                  and "KEYINPUT\ta\tactions\t0\t1\tA\tJump; again in the air to glide. Confirm in menus" in rows
                  and not any(r.startswith(("SETTING\tcursor", "SETTING\tsave_clock", "CONTROL")) for r in rows))
            (home / "app" / "r3hd_launcher.exe").unlink()
            check("launcher-model reports a missing installed file",
                  "FILES\tmissing\t1\tapp/r3hd_launcher.exe" in launcher_model(home, rels))
            prefs_before = (home / "settings.json").read_bytes()
            r = repair(home, pl, releases=rels, log=quiet)
            check("repair restores a missing launcher without touching the settings", r["restored_files"] == [LAUNCHER]
                  and (home / "app" / "r3hd_launcher.exe").read_bytes() == b"MZ settings launcher v1"
                  and (home / "settings.json").read_bytes() == prefs_before)
            os.environ["R3HD_INSTALL_FAKE_LAUNCHER"] = "1"
            check("repair / uninstall refused while the Settings launcher runs; nothing removed",
                  refused(lambda: repair(home, pl, releases=rels, log=quiet), "LAUNCHER_RUNNING")
                  and refused(lambda: uninstall(home, check_only=True, releases=rels, log=quiet), "LAUNCHER_RUNNING")
                  and (home / STATE).is_file() and (home / LAUNCHER).is_file())
            set_preset(home, "hdplus")
            check("the launcher itself may still save settings while it runs", read_json(home / "settings.json")["preset"] == "hdplus")
            os.environ["R3HD_INSTALL_FAKE_LAUNCHER"] = "0"
            set_preset(home, "custom", "hdplus", ["cursor=visible"])
            answers = iter(["3", "", "", "2", "bogus", "separate", "", "", "", "", "", "", ""])  # + default Discord / DualSense
            configure(home, ask=lambda _: next(answers), say=quiet)
            s = read_json(home / "settings.json")
            check("configure (Custom) writes the chosen options through the resolver", s["preset"] == "custom"
                  and s["overrides"] == {"layer_coords": "separate", "texture_orient": "corrected"}  # M43: Enter keeps HD+'s value
                  and s["preferences"] == {"cursor": "visible", "render_scale": "2", "dualsense_light": "off",
                                           "dualsense_trigger": "off"})  # D-108: a named DualSense option is kept
            configure(home, ask=lambda _: "", say=quiet)
            check("configure with Enter changes nothing", read_json(home / "settings.json") == s)
            set_preset(home, "custom", "hdplus", ["cursor=visible"])
            check("set-preset refuses a mandatory override", refused(lambda: set_preset(home, "custom", None, ["revisit=original"]),
                                                                    "SETTINGS_REFUSED"))
            # update keeps data, saves and the custom preset
            pl2 = make_fixture(t, "0.30.0", b"v2")[0]
            data_mtime = (home / "data" / "content" / "Default.xex").stat().st_mtime_ns
            r = install(home, pl2, releases=rels, log=quiet)
            check("update without source keeps data and settings", r["action"] == "update" and r["data"] == "kept"
                  and r["settings"] == "kept" and read_json(home / "settings.json")["preferences"]["cursor"] == "visible"
                  and (home / "data" / "content" / "Default.xex").stat().st_mtime_ns == data_mtime
                  and (home / "bin" / "r3hd.exe").read_bytes() == b"MZ exe v2")
            check("downgrade refused", refused(lambda: install(home, pl, releases=rels, log=quiet), "DOWNGRADE"))
            # interrupted commit: rolled back at once, and after a kill by the next run
            os.environ["R3HD_INSTALL_FAULT"] = "commit:bin"
            pl3 = make_fixture(t, "0.31.0", b"v3")[0]
            check("fault in commit -> WRITE_FAILED", refused(lambda: install(home, pl3, releases=rels, log=quiet), "WRITE_FAILED"))
            os.environ.pop("R3HD_INSTALL_FAULT")
            check("rollback restores the previous version", (home / "bin" / "r3hd.exe").read_bytes() == b"MZ exe v2"
                  and read_json(home / STATE)["version"] == "0.30.0" and verify(home, True, rels)["result"] == "healthy"
                  and not list(home.glob(".staging-*")) and not list(home.glob(".old-*")))
            os.environ["R3HD_INSTALL_FAULT"] = "before_cleanup"
            r = install(home, pl3, releases=rels, log=quiet)
            os.environ.pop("R3HD_INSTALL_FAULT")
            check("a cleanup failure after the commit is not a failed install", r["action"] == "update"
                  and r["cleanup_pending"] and (home / TXN).is_file() and read_json(home / STATE)["version"] == "0.31.0")
            check("the committed journal is finished by the next run", recover(home, quiet) == "finished"
                  and not list(home.glob(".old-*")) and not (home / TXN).exists() and verify(home, True, rels)["result"] == "healthy")
            # space and foreign directories
            os.environ["R3HD_INSTALL_FREE_BYTES"] = "1000"
            check("insufficient space refused, nothing left", refused(lambda: install(t / "H2", pl, tree, "vanilla", releases=rels,
                                                                                      log=quiet), "NO_SPACE") and not (t / "H2").exists())
            os.environ.pop("R3HD_INSTALL_FREE_BYTES")
            foreign = t / "Foreign"
            foreign.mkdir()
            (foreign / "mine.txt").write_bytes(b"keep")
            check("foreign non-empty folder refused", refused(lambda: install(foreign, pl, tree, "vanilla", releases=rels, log=quiet),
                                                            "HOME_NOT_EMPTY") and (foreign / "mine.txt").read_bytes() == b"keep")
            check("install inside the source folder refused before writing anything",
                  refused(lambda: install(tree / "inst", pl, tree, "vanilla", releases=rels, log=quiet), "INSIDE_SOURCE")
                  and not (tree / "inst").exists())
            check("first install needs a source", refused(lambda: install(t / "H3", pl, None, "vanilla", releases=rels, log=quiet),
                                                         "PACKAGE_REQUIRED"))
            check("first install needs a preset", refused(lambda: install(t / "H4", pl, tree, None, releases=rels, log=quiet),
                                                         "PRESET_REQUIRED"))
            os.environ["R3HD_INSTALL_SYSTEM32"] = str(t / "empty_sys32")
            check("missing VC++ runtime refused", refused(lambda: install(t / "H5", pl, tree, "vanilla", releases=rels, log=quiet),
                                                         "VC_RUNTIME_MISSING"))
            os.environ["R3HD_INSTALL_SYSTEM32"] = str(sys32)
            os.environ["R3HD_INSTALL_FAKE_RUNNING"] = "1"
            check("running game refused", refused(lambda: uninstall(home, releases=rels, log=quiet), "GAME_RUNNING"))
            os.environ["R3HD_INSTALL_FAKE_RUNNING"] = "0"
            bad = make_fixture(t, "0.29.0", b"bad")[0]
            (bad / "bin" / "r3hd.exe").write_bytes(b"tampered")
            check("damaged payload refused", refused(lambda: install(t / "H6", bad, tree, "vanilla", releases=rels, log=quiet),
                                                    "PAYLOAD_DAMAGED"))
            (bad / "bin" / "extra.dll").write_bytes(b"x")
            check("unexpected payload file refused", refused(lambda: load_payload(bad), "PAYLOAD_DAMAGED"))
            wrong = t / "wrong_tree"
            shutil.copytree(tree, wrong)
            (wrong / "GAMEDATAbin" / "a.bhf").write_bytes(b"zzz")
            check("tree with changed content refused", refused(lambda: install(t / "H7", pl, wrong, "vanilla", releases=rels,
                                                                               log=quiet), "TREE_MISMATCH") and not (t / "H7" / STATE).exists())
            # a kill in the middle of a commit, recovered by uninstall's own recovery
            os.environ["R3HD_INSTALL_FAULT"] = "kill:commit:data"
            r = subprocess.run([sys.executable, __file__, "install", "--home", str(t / "H8"), "--payload", str(pl),
                                "--source", str(tree), "--preset", "vanilla", "--releases", str(t / "releases.json")],
                               capture_output=True, text=True)
            os.environ.pop("R3HD_INSTALL_FAULT")
            check("killed install leaves a journal", r.returncode == 70 and (t / "H8" / TXN).is_file())
            check("the killed engine's lock is left behind", (t / "H8" / LOCK).is_file())
            r = install(t / "H8", pl, tree, "vanilla", releases=rels, log=quiet)
            check("retrying install takes over the stale lock, rolls back and installs", r["action"] == "install"
                  and verify(t / "H8", True, rels)["result"] == "healthy" and not (t / "H8" / LOCK).exists()
                  and not list((t / "H8").glob(".old-*")))
            (t / "H8" / LOCK).write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
            check("a lock held by a live process is respected", refused(lambda: set_preset(t / "H8", "hdplus"), "BUSY"))
            (t / "H8" / LOCK).unlink()
            os.environ["R3HD_INSTALL_FAULT"] = "kill:commit:installer.json"
            r = subprocess.run([sys.executable, __file__, "install", "--home", str(t / "H8"), "--payload", str(pl3),
                                "--releases", str(t / "releases.json")], capture_output=True, text=True)
            os.environ.pop("R3HD_INSTALL_FAULT")
            check("an update killed while installer.json is out of place", r.returncode == 70
                  and not (t / "H8" / STATE).exists())
            r = uninstall(t / "H8", check_only=True, releases=rels, log=quiet)
            check("uninstall recovers it first, and --check removes nothing", r["action"] == "uninstall-check"
                  and r["version"] == "0.29.0" and (t / "H8" / "bin" / "r3hd.exe").read_bytes() == b"MZ exe v1")
            # uninstall
            (home / "notes.txt").write_bytes(b"mine")
            r = uninstall(home, releases=rels, log=quiet)
            check("uninstall removes owned files only, keeps saves and settings", not (home / "bin").exists()
                  and not (home / "app").exists() and not (home / "data").exists() and not (home / STATE).exists()
                  and (home / "profiles" / "default" / "user" / "save.dat").read_bytes() == b"SAVE"
                  and (home / "settings.json").is_file() and (home / "notes.txt").read_bytes() == b"mine")
            check("reinstall refused while a foreign file is in the folder",
                  refused(lambda: install(home, pl3, tree, None, releases=rels, log=quiet), "HOME_NOT_EMPTY"))
            (home / "notes.txt").unlink()
            r = install(home, pl3, tree, None, releases=rels, log=quiet)
            (home / "notes.txt").write_bytes(b"mine")
            check("reinstall over kept user data keeps the person's preset", r["settings"] == "kept"
                  and read_json(home / "settings.json")["preset"] == "custom")
            check("user-data removal needs confirmation", refused(lambda: uninstall(home, True, None, releases=rels, log=quiet),
                                                                 "CONFIRMATION_REQUIRED") and (home / STATE).is_file())
            (home / "data" / PLAY_ICON).write_bytes(b"ico")
            check("an existing Play icon is kept when its package is gone", write_play_icon(home))
            r = uninstall(home, True, str(home), releases=rels, log=quiet)
            check("removal also deletes the locally made Play icon", not (home / "data" / PLAY_ICON).exists())
            check("confirmed removal deletes saves but never unknown files", not (home / "profiles").exists()
                  and not (home / "settings.json").exists() and (home / "notes.txt").is_file() and r["left_in_home"] == ["notes.txt"])
            h9 = t / "H9"
            install(h9, pl, tree, "vanilla", releases=rels, log=quiet)
            (h9 / "unins000.exe").write_bytes(b"inno")
            (h9 / "bin" / DEV_CONFIG).write_bytes(b"vsync = false\n")
            r = uninstall(h9, from_uninstaller=True, releases=rels, log=quiet)
            check("uninstaller mode leaves app\\ to the uninstaller", (h9 / "app").is_dir() and not (h9 / "bin").exists()
                  and r["app_deferred_to_uninstaller"])
            check("D-114: uninstaller mode also moves bin\\r3hd.toml out of bin\\",
                  [p.read_bytes() for p in (h9 / "dev_overlay_config").glob("r3hd-*.toml")] == [b"vsync = false\n"]
                  and "dev_overlay_config" in r["user_data_kept"])
            # D-114: bin\r3hd.toml (the SDK overlay's saved settings) is moved, never deleted or left to block a reinstall.
            h11 = t / "H11"
            install(h11, pl, tree, "vanilla", releases=rels, log=quiet)
            dev_dir = h11 / "dev_overlay_config"
            (h11 / "bin" / DEV_CONFIG).write_bytes(b"vsync = false\n")
            r = repair(h11, pl, releases=rels, log=quiet)
            check("D-114: repair leaves bin\\r3hd.toml in place", (h11 / "bin" / DEV_CONFIG).read_bytes()
                  == b"vsync = false\n" and not dev_dir.exists() and DEV_CONFIG in r["unexpected_in_bin"])
            r = install(h11, pl, None, None, releases=rels, log=quiet)
            moved = sorted(dev_dir.glob("r3hd-*.toml"))
            check("D-114: a setup re-run moves bin\\r3hd.toml unchanged to dev_overlay_config\\",
                  not (h11 / "bin" / DEV_CONFIG).exists() and len(moved) == 1 and moved[0].read_bytes() == b"vsync = false\n"
                  and r["dev_config_set_aside"] == f"dev_overlay_config/{moved[0].name}" and verify(h11, releases=rels)["result"] == "healthy")
            (h11 / "bin" / DEV_CONFIG).write_bytes(b"mnk_mouse = true\n")
            r = install(h11, pl3, None, None, releases=rels, log=quiet)
            moved = sorted(dev_dir.glob("r3hd-*.toml"))
            check("D-114: an update moves it too and never replaces an earlier one", len(moved) == 2
                  and sorted(p.read_bytes() for p in moved) == [b"mnk_mouse = true\n", b"vsync = false\n"])
            (h11 / "bin" / DEV_CONFIG).write_bytes(b"anisotropic_override = 0\n")
            r = uninstall(h11, releases=rels, log=quiet)
            check("D-114: uninstall moves it out of bin\\, removes bin\\ and keeps it with the user data",
                  not (h11 / "bin").exists() and len(list(dev_dir.glob("r3hd-*.toml"))) == 3
                  and r["dev_config_set_aside"] and "dev_overlay_config" in r["user_data_kept"])
            r = install(h11, pl3, tree, None, releases=rels, log=quiet)
            check("D-114: a fresh install into the same folder works and keeps the set-aside files",
                  r["action"] == "install" and len(list(dev_dir.glob("r3hd-*.toml"))) == 3
                  and not (h11 / "bin" / DEV_CONFIG).exists())
            (h11 / "bin" / "notes.txt").write_bytes(b"mine")
            uninstall(h11, releases=rels, log=quiet)
            check("D-114: any other unknown file in bin\\ is still kept, and still blocks a fresh install",
                  (h11 / "bin" / "notes.txt").read_bytes() == b"mine"
                  and refused(lambda: install(h11, pl3, tree, None, releases=rels, log=quiet), "HOME_NOT_EMPTY"))
            (h11 / "bin" / "notes.txt").unlink()
            (h11 / "bin").rmdir()
            install(h11, pl3, tree, None, releases=rels, log=quiet)
            r = uninstall(h11, True, str(h11), releases=rels, log=quiet)
            check("D-114: a confirmed removal of the user data removes dev_overlay_config\\ with it",
                  not dev_dir.exists() and "dev_overlay_config" in r["user_data_removed"] and not h11.exists())
            check("describe-options lists the shown adjustable settings only (M31: cursor and save clock hidden)",
                  [o["key"] for o in describe_options()] == ["display", "window_size", "render_scale", "layer_coords",
                                                             "texture_orient", "gameplay_subtitles", "discord_presence",
                                                             "dualsense_light", "dualsense_trigger",
                                                             "dualsense_trigger_strength", "diagnostics"])
            r = install(t / "H10", pl, tree, "vanilla", pairs=["render_scale=2"], releases=rels, log=quiet)
            r = install(t / "H10", pl3, None, "hdplus", releases=rels, log=quiet)
            check("an update with an explicit preset keeps the preferences (M30), the install default included (M31)",
                  r["settings"] == "written" and read_json(t / "H10" / "settings.json")
                  == {"schema": 3, "preset": "hdplus", "preferences": {"display": "fullscreen", "render_scale": "2", **DS}})
            # M32 (D-069): the keyboard map is a preference of its own: kept by preset changes, updates and repairs.
            h10 = t / "H10"
            refused_conflict = refused(lambda: set_preset(h10, "hdplus", keyboard=("modern", {"x": "Space"})),
                                       "SETTINGS_REFUSED")
            refused_required = refused(lambda: set_preset(h10, "hdplus", keyboard=("modern", {"a": ""})),
                                       "SETTINGS_REFUSED")
            refused_reserved = refused(lambda: set_preset(h10, "hdplus", keyboard=("modern", {"a": "F4"})),
                                       "SETTINGS_REFUSED")
            check("keyboard (M32): a conflict, a required input without a key and a reserved key are refused; the file "
                  "is unchanged", refused_conflict and refused_required and refused_reserved
                  and "keyboard" not in read_json(h10 / "settings.json"))
            set_preset(h10, "hdplus", keyboard=("original_pc", {"x": "V,B", "y": ""}))
            kb1 = read_json(h10 / "settings.json").get("keyboard")
            set_preset(h10, "custom", "vanilla", ["texture_orient=corrected"])
            set_preset(h10, "vanilla")
            kb2 = read_json(h10 / "settings.json").get("keyboard")
            r = install(h10, pl3, None, "hdplus", releases=rels, log=quiet)
            kb3 = read_json(h10 / "settings.json").get("keyboard")
            (h10 / "settings.json").unlink()
            repair(h10, pl3, releases=rels, log=quiet)
            kb4 = read_json(h10 / "settings.json").get("keyboard")
            model = launcher_model(h10, rels)
            check("keyboard (M32): saved as the changed inputs only; kept by preset changes, an update and a repair",
                  kb1 == {"layout": "original_pc", "keys": {"x": ["V", "B"], "y": []}} and kb1 == kb2 == kb3 == kb4
                  and "KEYBIND\tx\tV\tB\n" in model and "KEYBIND\ty\t\t\n" in model
                  and "KEYBOARD\tsaved\toriginal_pc\t\n" in model)
            set_preset(h10, "vanilla", keyboard=("modern", {}))
            check("keyboard (M32): restoring the default layout stores nothing", "keyboard" not in
                  read_json(h10 / "settings.json") and "KEYBOARD\tdefault\tmodern\t\n" in launcher_model(h10, rels))
            bad = read_json(h10 / "settings.json")
            bad["keyboard"] = {"layout": "modern", "keys": {"a": ["Nope"]}}
            bad["preferences"] = {"render_scale": "3"}
            write_json(h10 / "settings.json", bad)
            model = launcher_model(h10, rels)
            set_preset(h10, "hdplus")
            check("keyboard (M32): a damaged map is reported, the other settings still apply, and saving replaces it "
                  "after keeping a copy", "KEYBOARD\tinvalid\tmodern\t" in model and "SETTINGS\tok\t" in model
                  and settings_state(h10)["values"]["render_scale"] == "3"
                  and "keyboard" not in read_json(h10 / "settings.json") and list(h10.glob("settings.json.invalid-*")))
            # D-115: the controller button map is a preference of its own like the keyboard map.
            refused_pad = refused(lambda: set_preset(h10, "hdplus", controller={"a": "b"}), "SETTINGS_REFUSED")
            refused_unknown = refused(lambda: set_preset(h10, "hdplus", controller={"a": "left_trigger"}),
                                      "SETTINGS_REFUSED")
            refused_kind = refused(lambda: set_preset(h10, "hdplus", controller={"left_trigger": "left_stick",
                                                                                 "left_stick": "left_trigger"}),
                                   "SETTINGS_REFUSED")
            check("controller (D-115, D-116): a button on two inputs, a trigger for a button and a stick for a trigger "
                  "are refused; the file is unchanged", refused_pad and refused_unknown and refused_kind
                  and "controller" not in read_json(h10 / "settings.json"))
            set_preset(h10, "hdplus", keyboard=("original_pc", {"x": "H"}),
                       controller={"a": "b", "b": "a", "left_trigger": "right_trigger", "right_trigger": "left_trigger"})
            pad1 = read_json(h10 / "settings.json")
            set_preset(h10, "custom", "vanilla", ["texture_orient=corrected"])
            set_preset(h10, "vanilla", keyboard=("modern", {}))
            pad2 = read_json(h10 / "settings.json")
            install(h10, pl3, None, "hdplus", releases=rels, log=quiet)
            pad3 = read_json(h10 / "settings.json")
            (h10 / "settings.json").unlink()
            repair(h10, pl3, releases=rels, log=quiet)
            pad4 = read_json(h10 / "settings.json")
            model = launcher_model(h10, rels)
            check("controller (D-115): saved as the changed inputs only (schema 4), kept by preset changes, a keyboard "
                  "change, an update and a repair",
                  pad1["schema"] == 4 and pad1["controller"] == {"buttons": {"a": "b", "b": "a"},
                                                                 "analog": {"left_trigger": "right_trigger",
                                                                            "right_trigger": "left_trigger"}}
                  and pad1["keyboard"] == {"layout": "original_pc", "keys": {"x": ["H"]}}
                  and pad1["controller"] == pad2["controller"] == pad3["controller"] == pad4["controller"]
                  and "keyboard" not in pad2 and "PADSTATE\tsaved\t\n" in model and "PADBIND\ta\tb\n" in model
                  and "PADBIND\tb\ta\n" in model and "PADBIND\tx\tx\n" in model
                  and "PADBIND\tright_trigger\tleft_trigger\n" in model and "PADBIND\tleft_stick\tleft_stick\n" in model
                  and "PADBUTTON\ta\tA / Cross\tbutton\n" in model and "PADBUTTON\tright_trigger\tRT / R2\ttrigger\n" in model
                  and "PADGROUP\tactions\tActions\n" in model and "PADACTION\tstart\tmenus\tPause\n" in model
                  and "PADACTION\tright_trigger\tactions\tLock on\n" in model
                  and "PADACTION\ty\tactions\tLook Mode (hold)\n" in model and model.startswith("R3HD_LAUNCHER_MODEL\t5\n"))
            set_option(h10, "ui_language", "tr")
            set_option(h10, "render_scale", "2")
            check("controller (D-115): the interface language and a single option keep the map",
                  read_json(h10 / "settings.json").get("controller") == pad1["controller"])
            set_option(h10, "ui_language", "en")
            set_preset(h10, "vanilla", controller={})
            check("controller (D-115): restoring the original controls stores nothing (schema 3 again)",
                  "controller" not in read_json(h10 / "settings.json") and read_json(h10 / "settings.json")["schema"] == 3
                  and "PADSTATE\tdefault\t\n" in launcher_model(h10, rels))
            bad = read_json(h10 / "settings.json")
            bad.update(schema=4, controller={"buttons": {"a": "b"}}, keyboard={"layout": "original_pc", "keys": {}})
            write_json(h10 / "settings.json", bad)
            model = launcher_model(h10, rels)
            set_preset(h10, "hdplus")
            check("controller (D-115): a damaged map is reported, the keyboard map and settings still apply, and saving "
                  "replaces it after keeping a copy", "PADSTATE\tinvalid\tsaved controller buttons not used" in model
                  and "KEYBOARD\tsaved\toriginal_pc\t\n" in model and "SETTINGS\tok\t" in model
                  and "controller" not in read_json(h10 / "settings.json")
                  and read_json(h10 / "settings.json").get("keyboard") == {"layout": "original_pc", "keys": {}}
                  and len(list(h10.glob("settings.json.invalid-*"))) >= 2)
            # M31 (D-068): an M30 installation in a window (the default then: nothing stored) stays in a window.
            h11 = t / "H11"
            install(h11, pl, tree, "vanilla", releases=rels, log=quiet)
            write_json(h11 / "settings.json", {"schema": 2, "preset": "hdplus", "preferences": {"render_scale": "3"}})
            r1 = install(h11, pl3, None, None, releases=rels, log=quiet)
            r2 = install(h11, pl3, None, "vanilla", releases=rels, log=quiet)
            check("an upgrade or a new profile keeps an existing window choice; no install default (M31)",
                  r1["settings"] == "kept" and r2["settings"] == "written"
                  and read_json(h11 / "settings.json")["preferences"] == {"render_scale": "3"}
                  and settings_state(h11)["values"]["display"] == "windowed")
            (h11 / "settings.json").unlink()
            repair(h11, pl3, releases=rels, log=quiet)
            check("repair of a missing settings file restores the recorded choice, not the install default (M31)",
                  read_json(h11 / "settings.json")["preferences"] == {"render_scale": "3"})
            h12 = t / "H12"
            install(h12, pl, tree, "custom", "hdplus", ["display=windowed", "window_size=1920x1080"], releases=rels, log=quiet)
            check("an explicit window choice at the first install wins over the install default (M31)",
                  read_json(h12 / "settings.json")["preferences"] == {"window_size": "1920x1080", "gameplay_subtitles": "all", **DS})
            check("a fresh Vanilla installation starts without gameplay subtitles (D-090); Custom follows its base",
                  "gameplay_subtitles" not in read_json(t / "H10" / "settings.json")["preferences"])
            # M31 (D-068): progress and cancellation.
            ticks = iter(range(10 ** 6))
            lines = []
            p = Progress(emit=lines.append, clock=lambda: float(next(ticks)))
            install(t / "H13", pl, tree, "vanilla", releases=rels, log=quiet, progress=p)
            steps = [ln.split()[1] for ln in lines if ln.startswith("R3HD_STEP ")]
            permille = [int(ln.split()[1]) for ln in lines if ln.startswith("R3HD_PROGRESS ")]
            pbytes = sum(i["size"] for i in read_json(pl / "payload.json")["files"].values())
            check("progress: every phase in order, from an extracted tree (M31)",
                  steps == ["payload", "check", "copy", "verify", "commit"])
            check("progress: the share only grows and ends at 1000", permille == sorted(permille) and permille[-1] == 1000
                  and permille[0] == 0)
            check("progress: the payload phase counts each byte copied and checked",
                  any(ln.startswith("R3HD_PROGRESS ") and ln.split()[3] == "payload"
                      and ln.split()[5] == f"{2 * pbytes}/{2 * pbytes}" for ln in lines))
            check("progress: a time estimate only after 3 % and 3 seconds", all(
                int(ln.split()[2]) == -1 for ln in lines if ln.startswith("R3HD_PROGRESS ") and int(ln.split()[1]) < 30))
            cancel = t / "cancel.flag"
            cancel.write_text("x", encoding="utf-8")
            check("cancel before anything: refused CANCELLED, no folder left, the source untouched",
                  refused(lambda: install(t / "H14", pl, tree, "vanilla", releases=rels, log=quiet,
                                          progress=Progress(cancel_file=cancel)), "CANCELLED")
                  and not (t / "H14").exists()
                  and tree_before == {q: q.read_bytes() for q in tree.rglob("*") if q.is_file()})
            cancel.unlink()

            def cancel_at(phase):
                def emit(line):
                    if line.startswith("R3HD_STEP ") and line.split()[1] == phase:
                        cancel.write_text("x", encoding="utf-8")
                return emit
            h15 = t / "H15"
            install(h15, pl, tree, "hdplus", releases=rels, log=quiet)
            (h15 / "profiles" / "default").mkdir(parents=True)
            (h15 / "profiles" / "default" / "save.dat").write_bytes(b"SAVE15")
            before15 = (h15 / "settings.json").read_bytes()
            check("cancel during a first install's game-data copy: nothing is left, not even the folder",
                  refused(lambda: install(t / "H16", pl, tree, "vanilla", releases=rels, log=quiet,
                                          progress=Progress(emit=cancel_at("copy"), cancel_file=cancel)), "CANCELLED")
                  and not (t / "H16").exists())
            cancel.unlink()
            check("cancel during an update's application copy: the installed version is unchanged and healthy",
                  refused(lambda: install(h15, pl3, None, None, releases=rels, log=quiet,
                                          progress=Progress(emit=cancel_at("payload"), cancel_file=cancel)), "CANCELLED")
                  and read_json(h15 / STATE)["version"] == "0.29.0" and verify(h15, True, rels)["result"] == "healthy"
                  and not list(h15.glob(".staging-*")) and not (h15 / LOCK).exists() and not (h15 / TXN).exists()
                  and (h15 / "settings.json").read_bytes() == before15
                  and (h15 / "profiles" / "default" / "save.dat").read_bytes() == b"SAVE15")
            cancel.unlink()
            r = install(h15, pl3, None, None, releases=rels, log=quiet,
                        progress=Progress(emit=cancel_at("commit"), cancel_file=cancel))
            h17 = t / "H17"
            install(h17, pl, tree, "vanilla", releases=rels, log=quiet, desktop_shortcut=False)
            s1 = status(h17)["desktop_shortcut"]
            install(h17, pl3, None, None, releases=rels, log=quiet)
            s2 = status(h17)["desktop_shortcut"]
            check("the desktop shortcut choice is recorded and kept by an update that names none (M31)",
                  s1 == "0" and s2 == "0" and status(h15)["desktop_shortcut"] == "")
            check("a cancel request after the commit started is not honoured: the update completes",
                  r["action"] == "update" and read_json(h15 / STATE)["version"] == "0.31.0"
                  and verify(h15, True, rels)["result"] == "healthy")
            cancel.unlink()
            uninstall(t / "H10", releases=rels, log=quiet)
            check("uninstall removes the launcher with the other owned files", not (t / "H10" / "app").exists()
                  and (t / "H10" / "settings.json").is_file())
            check("texture_orient keeps internal evidence without a development qualifier in Settings",
                  next(o for o in describe_options() if o["key"] == "texture_orient")["note"] == ""
                  and presets.load_registry()["settings"]["texture_orient"]["provisional"] is True)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    for n, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {n}")
    failed = sum(not ok for _, ok in checks)
    print(f"R3HD_INSTALLER_SELFTEST {'PASS' if not failed else 'FAIL'} checks={len(checks)}")
    return 0 if not failed else 1


# --- command line -------------------------------------------------------------------------------------------------

def emit(result: dict, args, code: int):
    hooks = test_hooks()
    if hooks:
        result["test_hooks"] = hooks
    if getattr(args, "releases", None):
        result["release_table"] = args.releases
    if args.json:
        print(json.dumps(result, indent=1, default=str))
    if args.result_file:
        lines = [f"RESULT={result.get('result', 'ok')}", f"CODE={result.get('code', '')}",
                 f"MESSAGE={' '.join(str(result.get('message', '')).split())}"]
        for k in ("release", "kind", "display_name", "version", "preset_label", "detail", "desktop_shortcut",
              "settings_shortcut", "gameplay_subtitles", "changed"):
            if result.get(k) is not None:
                lines.append(f"{k.upper()}={' '.join(str(result[k]).split())}")
        Path(args.result_file).write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["check-source", "preflight", "install", "verify", "repair", "set-preset", "set-option",
                                    "status", "uninstall", "describe-options", "configure", "launcher-model", "selftest"])
    ap.add_argument("source_arg", nargs="?")
    ap.add_argument("--home")
    ap.add_argument("--payload")
    ap.add_argument("--source")
    ap.add_argument("--preset", choices=["vanilla", "hdplus", "custom"])
    ap.add_argument("--base", choices=["vanilla", "hdplus"])
    ap.add_argument("--ui-language", choices=["en", "tr"], help="install: initial Settings language for a fresh home only")
    ap.add_argument("--set", nargs="*", default=[], dest="pairs")
    ap.add_argument("--allow-experimental", action="store_true")
    ap.add_argument("--reset-settings", action="store_true")
    ap.add_argument("--allow-downgrade", action="store_true")
    ap.add_argument("--verify-data", action="store_true")
    ap.add_argument("--data", action="store_true")
    ap.add_argument("--remove-user-data", action="store_true")
    ap.add_argument("--confirm")
    ap.add_argument("--from-uninstaller", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--releases")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--result-file")
    ap.add_argument("--progress", action="store_true", help="install: R3HD_STEP / R3HD_PROGRESS lines on stdout (M31)")
    ap.add_argument("--cancel-file", help="install: stop and discard the staged work when this file appears (M31)")
    ap.add_argument("--desktop-shortcut", choices=["0", "1"], help="install: record the front end's desktop shortcut choice (M31)")
    ap.add_argument("--settings-shortcut", choices=["0", "1"],
                    help="install: record the front end's Settings desktop shortcut choice (M32)")
    ap.add_argument("--keyboard", help="set-preset: keyboard layout (M32); with --key the inputs changed from it")
    ap.add_argument("--key", nargs="*", default=[], help="set-preset: INPUT=KEY[,KEY] (M32); an empty value unbinds")
    ap.add_argument("--pad", nargs="*", help="set-preset: INPUT=BUTTON pairs that replace the controller button map "
                                             "(D-115; --pad alone = the original controls); without it the map is kept")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    log = (lambda m: print(f"r3hd_installer: {m}", file=sys.stderr))

    def need(*names):
        for n in names:
            if not getattr(a, n):
                raise Refusal("USAGE", f"{a.cmd} needs --{n.replace('_', '-')}")

    try:
        rels = load_releases(a.releases) if a.releases else None
        if a.cmd == "check-source":
            src = a.source_arg or a.source
            if not src:
                raise Refusal("USAGE", "check-source SOURCE")
            r = check_source(Path(src), rels if rels is not None else load_releases())
            r["message"] = f"Supported: {r['release']} ({r['kind']})"
        elif a.cmd == "preflight":
            need("home", "payload")
            pf = preflight(Path(os.path.abspath(a.home)), Path(a.payload), a.source, rels)
            if not (Path(a.home) / STATE).is_file():
                check_home_for_fresh(Path(os.path.abspath(a.home)))
            r = {"version": pf["payload"]["version"], "needed_bytes": pf["needed_bytes"], "free_bytes": pf["free_bytes"],
                 "source": pf["source"], "message": "ready"}
        elif a.cmd == "install":
            need("home", "payload")
            progress = None
            if a.progress or a.cancel_file:
                progress = Progress(emit=(lambda line: print(line, flush=True)) if a.progress else None,
                                    cancel_file=a.cancel_file)
            r = install(Path(a.home), Path(a.payload), a.source, a.preset, a.base, a.pairs, a.allow_experimental,
                        a.reset_settings, a.allow_downgrade, a.verify_data, rels, log, progress,
                        None if a.desktop_shortcut is None else a.desktop_shortcut == "1",
                        None if a.settings_shortcut is None else a.settings_shortcut == "1", a.ui_language)
            r["message"] = f"{r['action']} complete"
            r["preset_label"] = r["preset"].get("label")
        elif a.cmd == "verify":
            need("home")
            r = verify(Path(a.home), a.data, rels)
            r["message"] = r["result"]
            return emit(r, a, 0 if r["result"] == "healthy" else 3)
        elif a.cmd == "repair":
            need("home", "payload")
            r = repair(Path(a.home), Path(a.payload), a.source, rels, log)
            r["message"] = "repair complete"
        elif a.cmd == "set-preset":
            need("home", "preset")
            if a.key and not a.keyboard:
                raise Refusal("USAGE", "--key needs --keyboard LAYOUT")
            keyboard = None
            if a.keyboard:
                try:
                    keyboard = (a.keyboard, presets.parse_key_pairs(a.key))
                except presets.Refused as e:
                    raise Refusal("SETTINGS_REFUSED", f"{e.code}: {e.detail}")
            controller = None
            if a.pad is not None:
                try:
                    controller = presets.parse_pad_pairs(a.pad)
                except presets.Refused as e:
                    raise Refusal("SETTINGS_REFUSED", f"{e.code}: {e.detail}")
            r = set_preset(Path(a.home), a.preset, a.base, a.pairs, a.allow_experimental, keyboard, controller)
            r["message"] = f"preset {r['preset'].get('label')}"
            r["preset_label"] = r["preset"].get("label")
        elif a.cmd == "set-option":
            need("home")
            if len(a.pairs) != 1 or "=" not in a.pairs[0]:
                raise Refusal("USAGE", "set-option --home H --set KEY=VALUE")
            r = set_option(Path(a.home), *a.pairs[0].split("=", 1))
            r["message"] = ("changed: " if r["changed"] else "unchanged: ") + str(r["preset"].get("label"))
            r["preset_label"] = r["preset"].get("label")
            r["changed"] = int(r["changed"])
        elif a.cmd == "configure":
            need("home")
            r = configure(Path(a.home))
            r["message"] = "configured" if r["changed"] else "unchanged"
        elif a.cmd == "launcher-model":
            need("home")
            sys.stdout.buffer.write(launcher_model(Path(a.home), rels).encode("utf-8"))
            sys.stdout.flush()
            return 0
        elif a.cmd == "status":
            need("home")
            r = status(Path(a.home))
            r["message"] = f"installed {r['version']}"
        elif a.cmd == "uninstall":
            need("home")
            r = uninstall(Path(a.home), a.remove_user_data, a.confirm, a.from_uninstaller, rels, log, a.check)
            if a.check:
                r["message"] = "ready to uninstall"
            else:
                r["message"] = "uninstalled" + (f"; kept: {', '.join(r['user_data_kept'])}" if r["user_data_kept"] else "")
        else:
            opts = describe_options()
            if a.result_file:
                lines = [f"{o['key']}|{o['label']}|{','.join(o['values'])}|{o['vanilla']}|{o['hdplus']}|{o['note']}" for o in opts]
                Path(a.result_file).write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
            if a.json or not a.result_file:
                print(json.dumps(opts, indent=1))
            return 0
    except Refusal as e:
        advice = ADVICE.get(e.code, "")
        r = {"result": "refused", "code": e.code, "detail": e.detail, "message": f"{advice} ({e.code}: {e.detail})".strip(),
             **e.extra}
        print(f"R3HD_INSTALLER REFUSED {e.code}: {e.detail}", file=sys.stderr)
        return emit(r, a, 2)
    except Exception as e:  # noqa: BLE001  (reported to the front end, never swallowed)
        r = {"result": "error", "code": "INTERNAL", "message": f"{type(e).__name__}: {e}"}
        print(f"R3HD_INSTALLER ERROR {type(e).__name__}: {e}", file=sys.stderr)
        emit(r, a, 1)
        raise
    r.setdefault("result", "ok")
    print(f"R3HD_INSTALLER OK {a.cmd}: {r.get('message', '')}", file=sys.stderr)
    return emit(r, a, 0)


if __name__ == "__main__":
    sys.exit(main())
