#!/usr/bin/env python3
"""M28 (D-062): provision the pinned ReXGlue SDK checkout that the build expects, from public sources only.

Steps (each idempotent; nothing is ever reset, deleted or overwritten outside the listed files):
  fetch      clone https://github.com/rexglue/rexglue-sdk into external/rexglue-sdk at the commit pinned in
             config/build/toolchain.json and check out every submodule at its recorded commit. An existing
             directory is accepted only if it is a git checkout at the pin (refused otherwise, never reset).
  symlinks   E-06: on Windows the libmspack submodule's git symlinks check out as small text files holding
             the link target; each is replaced by a copy of its target. Only index entries of mode 120000
             under thirdparty/libmspack are touched, and only while they still hold the link text.
  configure  `cmake --preset win-amd64` under the MSVC environment (R3HD_VCVARS / R3HD_LLVM_BIN as in the
             build), skipped when out/build/win-amd64/CMakeCache.txt exists (--reconfigure to force).
  all        fetch, symlinks, configure, then tools/r3hd_build_doctor.py.
  plan       print what each step would do and change nothing (default).
  selftest   offline checks on synthetic git repositories in a temporary directory.

No game data, key, firmware or console SDK is fetched; the SDK is BSD-3-Clause public source (licences:
reports/milestone27/REPORT.md section 5). Network access is needed for fetch only.

usage: r3hd_bootstrap.py [plan|fetch|symlinks|configure|all|selftest] [--reconfigure]
Exit 0 on success, 2 on a refusal (reason code printed), 1 on an unexpected failure.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "build" / "toolchain.json"
MSPACK = "thirdparty/libmspack"


class Refusal(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def git(*args, cwd=None, check=True, capture=True):
    cmd = ["git", "-c", "core.symlinks=false", "-c", "core.autocrlf=false", *args]
    r = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True)
    if check and r.returncode != 0:
        raise Refusal("GIT_FAILED", f"{' '.join(args[:3])}: {(r.stderr or '').strip()[-400:]}")
    return (r.stdout or "").strip()


def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def head_of(path: Path) -> str:
    if not (path / ".git").exists():
        return ""
    r = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def submodule_pins(sdk: Path) -> dict:
    out = git("-C", str(sdk), "submodule", "status", check=False)
    pins = {}
    for line in out.splitlines():
        parts = line.strip().lstrip("-+U").split()
        if len(parts) >= 2:
            pins[parts[1]] = parts[0]
    return pins


def fetch(sdk: Path, m: dict, log=print):
    want = m["rexglue_sdk"]["commit"]
    if sdk.exists():
        head = head_of(sdk)
        if not head:
            raise Refusal("SDK_DIR_NOT_CHECKOUT", f"{sdk} exists but is not a git checkout; move it away yourself")
        if head != want:
            raise Refusal("SDK_PIN_MISMATCH", f"{sdk} is at {head}, the build is pinned to {want}; not reset")
        log(f"fetch: {sdk} already at the pin")
    else:
        if sdk.parent == ROOT / "external":
            sdk.parent.mkdir(exist_ok=True)  # this repository's own ignored tool directory (absent in a fresh clone)
        if not sdk.parent.is_dir():
            raise Refusal("PARENT_MISSING", f"{sdk.parent} does not exist")
        log(f"fetch: clone {m['rexglue_sdk']['repository']} -> {sdk}")
        git("clone", "--no-checkout", m["rexglue_sdk"]["repository"], str(sdk), capture=False)
        git("-C", str(sdk), "checkout", "--detach", want, capture=False)
        if head_of(sdk) != want:
            raise Refusal("SDK_PIN_MISMATCH", "checkout did not reach the pin")
    pins = submodule_pins(sdk)
    expected = m["rexglue_sdk"]["submodules"]
    missing = [k for k, v in expected.items() if pins.get(k) != v or not head_of(sdk / k)]
    if missing:
        log(f"fetch: {len(missing)} submodule(s) to check out")
        git("-C", str(sdk), "submodule", "update", "--init", "--recursive", "--depth", "1", capture=False)
    pins = submodule_pins(sdk)
    bad = [k for k, v in expected.items() if pins.get(k) != v or head_of(sdk / k) != v]
    extra = sorted(set(pins) - set(expected))
    if bad:
        raise Refusal("SUBMODULE_PIN_MISMATCH", f"not at the manifest pin: {', '.join(bad)}")
    log(f"fetch: SDK {want[:12]} and {len(expected)} submodules at their pins"
        + (f"; unlisted submodules: {extra}" if extra else ""))


def link_entries(repo: Path, prefix: str = ""):
    out = git("-C", str(repo), "ls-files", "-s", *( [prefix] if prefix else [] ))
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        mode, blob, _ = meta.split()
        if mode == "120000":
            yield path, blob


def fix_symlinks(repo: Path, log=print) -> dict:
    """Replace git-symlink text stubs by copies of their targets (E-06). Returns counts."""
    counts = {"replaced": 0, "already": 0}
    for path, blob in list(link_entries(repo)):
        link = repo / path
        target_text = git("-C", str(repo), "cat-file", "-p", blob)
        target = (link.parent / target_text).resolve()
        if not target.is_relative_to(repo.resolve()) or not target.is_file():
            raise Refusal("SYMLINK_TARGET", f"{path} -> {target_text} is not a file inside the checkout")
        data = target.read_bytes()
        if not link.exists():
            raise Refusal("SYMLINK_MISSING", f"{path} is not checked out")
        current = link.read_bytes()
        if current == data:
            counts["already"] += 1
            continue
        if current.strip() != target_text.encode():
            raise Refusal("SYMLINK_UNEXPECTED", f"{path} holds neither the link text nor its target; left alone")
        tmp = link.with_name(link.name + ".r3hd-tmp")
        tmp.write_bytes(data)
        os.replace(tmp, link)
        counts["replaced"] += 1
    log(f"symlinks: {counts['replaced']} replaced, {counts['already']} already copies")
    return counts


def toolchain_env(m: dict) -> tuple:
    vcvars = Path(os.environ.get(m["msvc"]["env_override"], m["msvc"]["default_vcvars"]))
    llvm = Path(os.environ.get(m["llvm"]["env_override"], m["llvm"]["default_path"]))
    if not vcvars.is_file():
        raise Refusal("VCVARS_MISSING", f"{vcvars}; install Visual Studio Build Tools or set R3HD_VCVARS")
    if not (llvm / "clang++.exe").is_file():
        raise Refusal("LLVM_MISSING", f"{llvm}\\clang++.exe; install LLVM {m['llvm']['version']} or set R3HD_LLVM_BIN")
    return vcvars, llvm


def configure(sdk: Path, m: dict, reconfigure=False, log=print):
    cache = sdk / "out/build/win-amd64/CMakeCache.txt"
    if cache.is_file() and not reconfigure:
        log("configure: already configured (out/build/win-amd64)")
        return
    if not head_of(sdk):
        raise Refusal("SDK_MISSING", "run fetch first")
    vcvars, llvm = toolchain_env(m)
    if shutil.which("cmake") is None:
        raise Refusal("CMAKE_MISSING", "install CMake and put it on PATH")
    script = Path(tempfile.mkdtemp(prefix="r3hd_cfg_")) / "configure.cmd"
    script.write_text(f'@echo off\r\ncall "{vcvars}" >nul 2>&1 || exit /b 1\r\n'
                      f'set "PATH={llvm};%PATH%"\r\ncmake --preset {m["rexglue_sdk"]["preset"]}\r\n', encoding="ascii")
    try:
        r = subprocess.run(["cmd", "/d", "/c", str(script)], cwd=sdk)
    finally:
        shutil.rmtree(script.parent, ignore_errors=True)
    if r.returncode != 0 or not cache.is_file():
        raise Refusal("CONFIGURE_FAILED", f"cmake --preset exited {r.returncode}")
    log("configure: done")


def plan(sdk: Path, m: dict):
    head = head_of(sdk)
    print(f"sdk dir    : {sdk}")
    print(f"pin        : {m['rexglue_sdk']['commit']} ({'present' if head == m['rexglue_sdk']['commit'] else 'checkout at ' + head if head else 'absent'})")
    if head:
        pins = submodule_pins(sdk)
        ok = sum(pins.get(k) == v for k, v in m["rexglue_sdk"]["submodules"].items())
        print(f"submodules : {ok} of {len(m['rexglue_sdk']['submodules'])} at their pins")
        sub = sdk / MSPACK
        if head_of(sub):
            stubs = sum(1 for p, _ in link_entries(sub) if (sub / p).is_file() and (sub / p).stat().st_size < 128)
            print(f"symlinks   : {stubs} libmspack link stub(s) to replace")
        print(f"configured : {(sdk / 'out/build/win-amd64/CMakeCache.txt').is_file()}")
    print("plan only: nothing changed")


def selftest() -> int:
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    with tempfile.TemporaryDirectory(prefix="r3hd_boot_") as t:
        t = Path(t)
        src = t / "src"
        (src / "real").mkdir(parents=True)
        (src / "real" / "a.h").write_bytes(b"int a;\n")
        git("init", "-q", str(src))
        git("-C", str(src), "config", "user.email", "t@example.invalid")
        git("-C", str(src), "config", "user.name", "t")
        blob = subprocess.run(["git", "-C", str(src), "hash-object", "-w", "--stdin"], input="../real/a.h",
                              capture_output=True, text=True, check=True).stdout.strip()
        git("-C", str(src), "add", "real/a.h")
        git("-C", str(src), "update-index", "--add", "--cacheinfo", f"120000,{blob},links/a.h")
        git("-C", str(src), "commit", "-q", "-m", "fixture")
        pin = git("-C", str(src), "rev-parse", "HEAD")
        clone = t / "clone"
        git("clone", "-q", str(src), str(clone))
        link = clone / "links" / "a.h"
        check("stub checked out as text", link.read_bytes().strip() == b"../real/a.h")
        c1 = fix_symlinks(clone, log=lambda *_: None)
        check("stub replaced by target", link.read_bytes() == b"int a;\n" and c1["replaced"] == 1)
        c2 = fix_symlinks(clone, log=lambda *_: None)
        check("second run idempotent", c2 == {"replaced": 0, "already": 1})
        link.write_bytes(b"edited by someone\n")
        try:
            fix_symlinks(clone, log=lambda *_: None)
            check("unexpected content refused", False)
        except Refusal as e:
            check("unexpected content refused", e.code == "SYMLINK_UNEXPECTED" and link.read_bytes() == b"edited by someone\n")
        fake = {"rexglue_sdk": {"commit": "0" * 40, "repository": str(src), "submodules": {}}}
        try:
            fetch(clone, fake, log=lambda *_: None)
            check("existing checkout at another commit refused", False)
        except Refusal as e:
            check("existing checkout at another commit refused", e.code == "SDK_PIN_MISMATCH")
        plain = t / "plain"
        plain.mkdir()
        (plain / "keep.txt").write_bytes(b"x")
        try:
            fetch(plain, fake, log=lambda *_: None)
            check("non-checkout directory refused", False)
        except Refusal as e:
            check("non-checkout directory refused", e.code == "SDK_DIR_NOT_CHECKOUT" and (plain / "keep.txt").is_file())
        good = {"rexglue_sdk": {"commit": pin, "repository": str(src), "submodules": {}}}
        fresh = t / "fresh"
        fetch(fresh, good, log=lambda *_: None)
        check("fresh clone at pin", head_of(fresh) == pin)
        fetch(fresh, good, log=lambda *_: None)
        check("fetch idempotent", head_of(fresh) == pin)
        try:
            fetch(t / "nope" / "sdk", good, log=lambda *_: None)
            check("missing parent refused", False)
        except Refusal as e:
            check("missing parent refused", e.code == "PARENT_MISSING" and not (t / "nope").exists())
        saved = {k: os.environ.get(k) for k in ("R3HD_VCVARS", "R3HD_LLVM_BIN")}
        os.environ["R3HD_VCVARS"] = str(t / "none.bat")
        try:
            toolchain_env(manifest())
            check("missing vcvars reported", False)
        except Refusal as e:
            check("missing vcvars reported", e.code == "VCVARS_MISSING")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    m = manifest()
    check("manifest pins 22 submodules", len(m["rexglue_sdk"]["submodules"]) == 22)
    check("manifest repository is the public https URL", m["rexglue_sdk"]["repository"].startswith("https://github.com/"))
    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {n}")
    print(f"R3HD_BOOTSTRAP_SELFTEST {'PASS' if not failed else 'FAIL'} checks={len(checks)}")
    return 0 if not failed else 1


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    step = args[0] if args else "plan"
    reconfigure = "--reconfigure" in sys.argv
    if step == "selftest":
        return selftest()
    m = manifest()
    sdk = ROOT / m["rexglue_sdk"]["path"]
    try:
        if step == "plan":
            plan(sdk, m)
        elif step == "fetch":
            fetch(sdk, m)
        elif step == "symlinks":
            fix_symlinks(sdk / MSPACK)
        elif step == "configure":
            configure(sdk, m, reconfigure)
        elif step == "all":
            fetch(sdk, m)
            fix_symlinks(sdk / MSPACK)
            configure(sdk, m, reconfigure)
            return subprocess.run([sys.executable, str(ROOT / "tools" / "r3hd_build_doctor.py")]).returncode
        else:
            print(__doc__)
            return 1
    except Refusal as e:
        print(f"R3HD_BOOTSTRAP REFUSED {e.code}: {e.detail}", file=sys.stderr)
        return 2
    print(f"R3HD_BOOTSTRAP OK step={step}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
