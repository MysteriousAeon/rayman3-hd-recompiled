#!/usr/bin/env python3
"""M27 (D-061): read-only check of a machine against config/build/toolchain.json before a local build.

Reports, per prerequisite, OK / MISSING / DIFFERENT and what to do; changes nothing (git status / rev-parse,
file reads, version queries only). With --data the extracted game tree is verified file by file
(tools/r3hd_intake.py verify). With --sdk-digest it prints the patched-SDK digest of this checkout.

usage: r3hd_build_doctor.py [--data] [--json] [--sdk-digest]
M28: honours R3HD_GAME_DIR and R3HD_BUILD_MODE (user: the developer audit inputs are optional);
provision a missing SDK with tools/r3hd_bootstrap.py.
Exit code 0 when every required item is OK, 2 otherwise.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "build" / "toolchain.json"


def run(*cmd, cwd=None) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def sdk_patched_files(sdk: Path) -> list:
    out = run("git", "-C", str(sdk), "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=all")
    paths = []
    for line in out.splitlines():
        path = line[3:].strip().strip('"')
        if path.startswith("out/"):
            continue
        paths.append(path)
    return sorted(paths)


def sdk_digest(sdk: Path) -> tuple:
    h = hashlib.sha256()
    files = sdk_patched_files(sdk)
    for rel in files:
        p = sdk / rel
        data = p.read_bytes().replace(b"\r\n", b"\n") if p.is_file() else b"<deleted>"
        h.update(rel.encode() + b"\0" + hashlib.sha256(data).digest())
    return len(files), h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", action="store_true", help="verify the extracted game tree (about 2 GB read)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sdk-digest", action="store_true")
    a = ap.parse_args()
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sdk = ROOT / m["rexglue_sdk"]["path"]
    if a.sdk_digest:
        n, d = sdk_digest(sdk)
        print(f"files={n} digest={d}")
        return 0
    rows = []

    def item(name, state, detail, required=True):
        rows.append({"item": name, "state": state, "detail": detail, "required": required})

    item("python", "OK" if sys.version_info[:2] >= tuple(m["python"]["min"]) else "DIFFERENT",
         f"{sys.version.split()[0]} (needs {'.'.join(map(str, m['python']['min']))}+ for tomllib)")
    git = run("git", "--version").strip()
    item("git", "OK" if git else "MISSING", git or "install Git for Windows")
    cmake = run("cmake", "--version").splitlines()
    item("cmake", "OK" if cmake else "MISSING", cmake[0] if cmake else "install CMake")
    llvm = Path(os.environ.get(m["llvm"]["env_override"], m["llvm"]["default_path"]))
    clang = run(str(llvm / "clang++.exe"), "--version")
    ver = re.search(r"clang version (\S+)", clang)
    item("llvm", "OK" if ver and ver.group(1) == m["llvm"]["version"] else ("DIFFERENT" if ver else "MISSING"),
         f"{ver.group(1) if ver else 'no clang++'} at {llvm} (pinned {m['llvm']['version']}; override with R3HD_LLVM_BIN)")
    vcvars = Path(os.environ.get(m["msvc"]["env_override"], m["msvc"]["default_vcvars"]))
    item("msvc vcvars64", "OK" if vcvars.is_file() else "MISSING", str(vcvars))
    tools = vcvars.parents[2] / "Tools" / "MSVC" / m["msvc"]["toolset"] if vcvars.is_file() else None
    item("msvc toolset", "OK" if tools and tools.is_dir() else "MISSING", f"{m['msvc']['toolset']}")
    wsdk = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10" / "Include" / m["msvc"]["windows_sdk"]
    item("windows sdk", "OK" if wsdk.is_dir() else "MISSING", m["msvc"]["windows_sdk"])

    head = run("git", "-C", str(sdk), "rev-parse", "HEAD").strip()
    item("rexglue sdk pin", "OK" if head == m["rexglue_sdk"]["commit"] else ("DIFFERENT" if head else "MISSING"),
         f"{head or 'no checkout'} at {sdk}")
    if head:
        subs = dict(reversed(l.lstrip("-+ U").split()[:2]) for l in run("git", "-C", str(sdk), "submodule", "status").splitlines() if l.strip())
        bad = [k for k, v in m["rexglue_sdk"]["submodules"].items() if subs.get(k) != v]
        item("sdk submodules", "OK" if not bad else "DIFFERENT", f"{len(m['rexglue_sdk']['submodules']) - len(bad)} of "
             f"{len(m['rexglue_sdk']['submodules'])} at their pins" + (f"; differ: {', '.join(bad[:4])}" if bad else ""))
        mspack = sdk / "thirdparty/libmspack/cabextract/mspack"
        stubs = [p.name for p in mspack.glob("*") if p.is_file() and p.stat().st_size < 64 and b"/" in p.read_bytes()[:64]] if mspack.is_dir() else ["(missing)"]
        item("libmspack symlink fix (E-06)", "OK" if not stubs else "MISSING", "regular files" if not stubs else f"stubs: {stubs[:3]}")
        item("sdk configured", "OK" if (sdk / "out/build/win-amd64/CMakeCache.txt").is_file() else "MISSING",
             "out/build/win-amd64 (cmake --preset win-amd64)")
        n, d = sdk_digest(sdk)
        want = m["rexglue_sdk"]["patched_state"]
        state = "OK" if (n, d) == (want["files"], want["digest"]) else ("CLEAN" if n == 0 else "DIFFERENT")
        item("sdk patch chain", state, f"{n} files, digest {d[:16]}... (expected {want['files']} files, "
             f"{want['digest'][:16]}...; CLEAN = not yet patched, the build applies the chain)", required=False)

    game_dir = Path(os.environ.get("R3HD_GAME_DIR") or ROOT / "private/extracted/5841123F")
    xex = game_dir / "Default.xex"
    rel = json.loads((ROOT / m["game_data"]["release_table"]).read_text(encoding="utf-8"))["releases"][0]
    if xex.is_file():
        ok = hashlib.sha256(xex.read_bytes()).hexdigest() == rel["executable"]["sha256"]
        item("game executable", "OK" if ok else "DIFFERENT", f"{xex} (tools/r3hd_intake.py extract)")
    else:
        item("game executable", "MISSING", f"{xex}: run tools/r3hd_intake.py extract PACKAGE OUT and set R3HD_GAME_DIR=OUT\content "
             "(or place content as private/extracted/5841123F)")
    if a.data:
        r = subprocess.run([sys.executable, str(ROOT / "tools/r3hd_intake.py"), "verify", str(game_dir)],
                           capture_output=True, text=True)
        item("game data tree", "OK" if r.returncode == 0 else "DIFFERENT", (r.stderr.strip().splitlines() or ["?"])[-1])
    for path, expect in m["developer_inputs"].items():
        p = ROOT / path
        if re.fullmatch(r"[0-9a-f]{64}", expect):
            state = "OK" if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == expect else ("DIFFERENT" if p.is_file() else "MISSING")
        else:
            state = "OK" if p.is_file() else "MISSING"
        item(path, state, "developer target audit only (tools/m3_target_audit.py, M1 developer steps); a user build "
             "(R3HD_BUILD_MODE=user) does not need it", required=os.environ.get("R3HD_BUILD_MODE", "developer").lower() != "user")
    item("build mode", "OK", f"{os.environ.get('R3HD_BUILD_MODE', 'developer')} (R3HD_BUILD_MODE); user builds must reproduce "
         f"codegen digest {m['codegen']['digest'][:16]}... ({m['codegen']['files']} files)", required=False)
    ready = all(r["state"] == "OK" for r in rows if r["required"])
    if a.json:
        print(json.dumps({"ready": ready, "items": rows}, indent=2))
    else:
        for r in rows:
            print(f"{r['state']:9} {r['item']:30} {r['detail']}")
    print(f"R3HD_BUILD_DOCTOR ready={'yes' if ready else 'no'} items={len(rows)} "
          f"not_ok={sum(r['state'] != 'OK' for r in rows if r['required'])}", file=sys.stderr)
    return 0 if ready else 2


if __name__ == "__main__":
    sys.exit(main())
