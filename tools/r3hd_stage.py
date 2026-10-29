#!/usr/bin/env python3
"""M29 (D-066): stage the PRIVATE installer payload deterministically from the current verified build.

The payload (config/release/payload.json defines it) is what the installer carries: bin\\ = the three runtime
binaries of the build, app\\ = installer engine, launcher, the configs they read, notices and licence texts, and a
private Python runtime (pinned CPython 3.11.4 files + a deterministic standard-library zip without extension
modules). Never game data, saves, captures, debug symbols, maps or test executables.

Checks before anything is written: every input exists and is exactly the pinned file where a pin exists; the
generated code of the build equals the codegen digest of config/build/toolchain.json; the binaries carry no
absolute user-profile path. After writing: payload.json lists every file (size, SHA-256, role) and a payload ID
over that list; tools/r3hd_release_audit.py payload must PASS. Output goes to OUT.partial and is renamed to OUT
only when everything passed. The same inputs give the same payload.json byte for byte (no time stamps, no
absolute paths). Nothing is uploaded; the payload is private and NOT publishable.

usage:
  r3hd_stage.py build OUT [--build-dir D] [--python-dir D] [--skip-codegen-check]
  r3hd_stage.py portable STAGE --portable-out ZIP --development-id ID --crt-dir CRT
  r3hd_stage.py stdlib-digest [--python-dir D]       print the stdlib zip digest (to pin a new Python)
  r3hd_stage.py selftest
Exit 0 ok, 2 refused, 1 failure.
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "config" / "release" / "payload.json"
SDK = ROOT / "external" / "rexglue-sdk"
TEXT_SUFFIXES = {".py", ".ps1", ".json", ".tsv", ".txt", ".md", ".cmd", "._pth"}
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
sys.path.insert(0, str(ROOT / "tools"))
import r3hd_release_audit as audit  # noqa: E402


class Refusal(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def default_python_dir() -> Path:
    return Path(sys.base_prefix)


def text_bytes(rel: str, data: bytes) -> bytes:
    """LF for every text file, CRLF for batch files: independent of the checkout's core.autocrlf."""
    lf = data.replace(b"\r\n", b"\n")
    return lf.replace(b"\n", b"\r\n") if rel.endswith(".cmd") else lf


def stdlib_zip(python_dir: Path, exclude) -> bytes:
    lib = python_dir / "Lib"
    if not lib.is_dir():
        raise Refusal("PYTHON_MISSING", f"{lib} not found")
    ex = set(exclude)
    names = []
    for p in sorted(lib.rglob("*.py")):
        rel = p.relative_to(lib)
        if any(part in ex or part == "__pycache__" or part in ("test", "tests", "idle_test") for part in rel.parts):
            continue
        names.append((rel.as_posix(), p))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, p in names:
            info = zipfile.ZipInfo(name, ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0o644 << 16
            zf.writestr(info, p.read_bytes(), compresslevel=9)
    return buf.getvalue()


def collect(defn: dict, build_dir: Path, python_dir: Path, sdk: Path, root: Path) -> dict:
    """{payload path: (bytes, role)} from the definition, refusing on any missing or unpinned input."""
    out = {}
    for name in defn["binaries"]["files"]:
        p = build_dir / name
        if not p.is_file():
            raise Refusal("BUILD_MISSING", f"{p} not found (build first)")
        data = p.read_bytes()
        n = audit.binary_dev_paths(data)
        if n:
            raise Refusal("BINARY_DEVELOPER_PATH", f"{name} carries {n} absolute user-profile path(s); rebuild with "
                                                   "tools\\build_milestone8.bat (path map, D-066)")
        out["bin/" + name] = (data, "native")
    la = defn.get("launcher")
    if la:
        # M30 (D-067): the Settings launcher, built from tools/launcher alone.
        p = Path(os.path.abspath(la["build_dir"])) if Path(la["build_dir"]).is_absolute() else root / la["build_dir"]
        p = p / la["file"]
        if not p.is_file():
            raise Refusal("BUILD_MISSING", f"{p} not found (build with tools\\launcher\\build_launcher.bat)")
        data = p.read_bytes()
        if audit.binary_dev_paths(data):
            raise Refusal("BINARY_DEVELOPER_PATH", f"{la['file']} carries an absolute user-profile path")
        out[la["dest"]] = (data, "launcher_native")
    for dst, src in defn["app_files"].items():
        p = root / src
        if not p.is_file():
            raise Refusal("INPUT_MISSING", f"{src} not found")
        role = "notice" if dst.endswith(".txt") else ("launcher" if dst.endswith((".ps1", ".cmd")) else "installer")
        out[dst] = (text_bytes(dst, p.read_bytes()), role)
    for dst, src in defn.get("licenses", {}).get("files", {}).items():
        p = sdk / src
        if not p.is_file():
            raise Refusal("INPUT_MISSING", f"licence text {src} not found in the SDK checkout")
        out[dst] = (text_bytes(dst, p.read_bytes()), "notice")
    py = defn["python"]
    for name, pin in py["files"].items():
        p = python_dir / name
        if not p.is_file():
            raise Refusal("PYTHON_MISSING", f"{p} not found")
        data = p.read_bytes()
        if sha256_bytes(data) != pin:
            raise Refusal("PYTHON_PIN", f"{name} is not the pinned CPython {py['version']} file")
        out["app/python/" + name] = (text_bytes(name, data) if name.endswith(".txt") else data,
                                     "notice" if name.endswith(".txt") else "python_runtime")
    if sha256_bytes(out["app/python/LICENSE.txt"][0]) != py["files"]["LICENSE.txt"]:
        out["app/python/LICENSE.txt"] = ((python_dir / "LICENSE.txt").read_bytes(), "notice")
    z = stdlib_zip(python_dir, py["stdlib_exclude"])
    if sha256_bytes(z) != py["stdlib_zip_sha256"]:
        raise Refusal("PYTHON_PIN", f"standard-library zip {sha256_bytes(z)[:16]}... differs from the pin "
                                    f"{py['stdlib_zip_sha256'][:16]}... (another Python or another exclude list)")
    out["app/python/python311.zip"] = (z, "python_stdlib")
    out["app/python/python311._pth"] = (b"python311.zip\n.\n", "python_runtime_config")
    return out


def codegen_check(skip: bool) -> dict:
    pin = json.loads((ROOT / "config" / "build" / "toolchain.json").read_text(encoding="utf-8"))["codegen"]["digest"]
    if skip:
        return {"pinned": pin, "checked": False}
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "r3hd_build_step.py"), "digest", "--json"],
                       capture_output=True, text=True)
    try:
        got = json.loads(r.stdout)["digest"]
    except (ValueError, KeyError):
        raise Refusal("CODEGEN_UNKNOWN", f"r3hd_build_step.py digest failed: {(r.stdout + r.stderr).strip()[-200:]}")
    if got != pin:
        raise Refusal("CODEGEN_DIFFERENT", f"generated code {got[:16]}... is not the pinned {pin[:16]}...")
    return {"pinned": pin, "checked": True}


def manifest(defn: dict, files: dict, codegen: dict, releases: dict) -> dict:
    entries = {rel: {"size": len(data), "sha256": sha256_bytes(data), "role": role}
               for rel, (data, role) in sorted(files.items())}
    pid = sha256_bytes("".join(f"{r}\t{e['size']}\t{e['sha256']}\n" for r, e in entries.items()).encode())
    rel = releases["releases"][0]
    return {"schema": 1, "product": defn["product"], "version": defn["version"], "publishable": False,
            "payload_id": pid,
            "requires": {"release": rel["id"], "executable_sha256": rel["executable"]["sha256"],
                         "manifest_sha256": rel["content"]["manifest_sha256"], "codegen_digest": codegen["pinned"],
                         "codegen_checked": codegen["checked"], "windows": "10 or 11, x64",
                         "vc_runtime": "Microsoft Visual C++ Redistributable 2015-2022 x64 (not included)"},
            "python": defn["python"]["version"],
            "files": entries,
            "note": "PRIVATE installer payload of a prototype: translated game code and a key-bearing runtime; NOT "
                    "publishable (D-065, D-066). No game data: the installer extracts it from the owner's package."}


def write_tree(out: Path, files: dict, mf: dict):
    for rel, (data, _role) in files.items():
        p = out.joinpath(*rel.split("/"))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    (out / "payload.json").write_bytes((json.dumps(mf, indent=1) + "\n").encode())


def build(out: Path, build_dir: Path, python_dir: Path, skip_codegen=False, defn=None, sdk=SDK, root=ROOT,
          run_audit=True, log=print) -> dict:
    defn = defn or json.loads(DEFINITION.read_text(encoding="utf-8"))
    out = Path(os.path.abspath(out))
    if out.exists():
        raise Refusal("OUTPUT_EXISTS", f"{out} exists; staging never overwrites")
    if not out.parent.is_dir():
        raise Refusal("OUTPUT_PARENT_MISSING", str(out.parent))
    partial = out.with_name(out.name + ".partial")
    if partial.exists():
        raise Refusal("OUTPUT_EXISTS", f"{partial} is left from an earlier attempt; remove it first")
    files = collect(defn, build_dir, python_dir, sdk, root)
    codegen = codegen_check(skip_codegen)
    releases = json.loads((root / "config" / "intake" / "known_releases.json").read_text(encoding="utf-8"))
    mf = manifest(defn, files, codegen, releases)
    try:
        write_tree(partial / "payload", files, mf)
        if run_audit:
            allow, binaries, pins = audit.load_payload_rules(audit.DEFAULT_PAYLOAD_ALLOWLIST, str(DEFINITION))
            hashes = audit.GameHashes([audit.DEFAULT_MANIFEST], audit.DEFAULT_RELEASES)
            res = audit.audit_payload(str(partial / "payload"), allow, binaries, pins, hashes)
            with open(partial / "audit.json", "w", encoding="utf-8", newline="\n") as f:
                json.dump(res, f, indent=1)
            if res["verdict"] != "PASS":
                bad = [f"{r['path']}: {', '.join(x['code'] for x in r['reasons'])}" for r in res["results"] if r["verdict"] == "FAIL"]
                raise Refusal("AUDIT_FAILED", "; ".join(bad[:5]))
        lgpl = None
        if defn.get("lgpl_source"):
            # M46 (D-084): the corresponding source of bin/ffmpeg.dll and bin/mspack.dll, written beside the payload
            # so that it is distributed from the same place as the program (tools/m46_lgpl.py).
            import m46_lgpl
            lfiles, lversion = m46_lgpl.package_files()
            if lversion != defn["version"]:
                raise Refusal("LGPL_SOURCE", f"source archive version {lversion} is not the payload's {defn['version']}")
            lgpl = f"{m46_lgpl.record()['package']['name']}-{lversion}.zip"
            digest = m46_lgpl.write_zip(lfiles, partial / lgpl)
            log(f"LGPL corresponding source {lgpl} sha256 {digest[:16]}... -> {out / lgpl}")
        os.replace(partial, out)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    size = sum(e["size"] for e in mf["files"].values())
    log(f"staged {len(mf['files'])} files, {size / 1e6:.1f} MB, payload {mf['payload_id'][:16]}... -> {out / 'payload'}")
    return {"out": str(out), "payload_id": mf["payload_id"], "files": len(mf["files"]), "bytes": size,
            "version": mf["version"], "lgpl_source": lgpl}


def selftest() -> int:
    checks = []

    def check(name, ok):
        checks.append((name, bool(ok)))

    def refused(fn, code):
        try:
            fn()
        except Refusal as e:
            return e.code == code
        return False

    quiet = lambda *_: None  # noqa: E731
    with tempfile.TemporaryDirectory(prefix="r3hd_stage_") as tmp:
        t = Path(tmp)
        bd, py, sdk, root = t / "build", t / "py", t / "sdk", t / "root"
        bd.mkdir()
        for n in ("r3hd.exe", "rexruntime.dll", "rexgpu-xenos.dll", "r3hd.pdb", "m4_input_test.exe"):
            (bd / n).write_bytes(b"MZ" + bytes(62) + n.encode())
        (py / "Lib" / "json").mkdir(parents=True)
        (py / "Lib" / "os.py").write_bytes(b"import sys\r\n")
        (py / "Lib" / "json" / "__init__.py").write_bytes(b"x = 1\n")
        (py / "Lib" / "test").mkdir()
        (py / "Lib" / "test" / "t.py").write_bytes(b"skip\n")
        (py / "Lib" / "__pycache__").mkdir()
        (py / "Lib" / "__pycache__" / "os.cpython-311.pyc").write_bytes(b"\0")
        (py / "python.exe").write_bytes(b"MZ" + bytes(62) + b"py")
        (py / "LICENSE.txt").write_bytes(b"PSF\r\n")
        (sdk / "thirdparty" / "x").mkdir(parents=True)
        (sdk / "thirdparty" / "x" / "LICENSE").write_bytes(b"MIT\n")
        (root / "tools").mkdir(parents=True)
        (root / "tools" / "a.py").write_bytes(b"print(1)\r\n")
        (root / "tools" / "go.cmd").write_bytes(b"@echo off\necho hi\n")
        (root / "config" / "intake").mkdir(parents=True)
        (root / "config" / "intake" / "known_releases.json").write_bytes(
            json.dumps({"schema": 1, "releases": [{"id": "r", "executable": {"sha256": "e"},
                                                   "content": {"manifest_sha256": "m"}}]}).encode())
        (root / "lb").mkdir()
        (root / "lb" / "r3hd_launcher.exe").write_bytes(b"MZ" + bytes(62) + b"settings")
        defn = {"product": "p", "version": "0.0.1", "binaries": {"files": ["r3hd.exe", "rexruntime.dll", "rexgpu-xenos.dll"]},
                "launcher": {"build_dir": "lb", "file": "r3hd_launcher.exe", "dest": "app/r3hd_launcher.exe"},
                "app_files": {"app/tools/a.py": "tools/a.py", "app/go.cmd": "tools/go.cmd"},
                "licenses": {"files": {"app/licenses/x-LICENSE.txt": "thirdparty/x/LICENSE"}},
                "python": {"version": "t", "files": {"python.exe": sha256_bytes((py / "python.exe").read_bytes()),
                                                     "LICENSE.txt": sha256_bytes(b"PSF\r\n")},
                           "stdlib_exclude": ["test"], "stdlib_zip_sha256": ""}}
        defn["python"]["stdlib_zip_sha256"] = sha256_bytes(stdlib_zip(py, ["test"]))
        kw = dict(skip_codegen=True, defn=defn, sdk=sdk, root=root, run_audit=False, log=quiet)
        r1 = build(t / "o1", bd, py, **kw)
        r2 = build(t / "o2", bd, py, **kw)
        check("same inputs give the same payload.json", (t / "o1" / "payload" / "payload.json").read_bytes()
              == (t / "o2" / "payload" / "payload.json").read_bytes() and r1["payload_id"] == r2["payload_id"])
        names = sorted(p.relative_to(t / "o1" / "payload").as_posix() for p in (t / "o1" / "payload").rglob("*") if p.is_file())
        check("only defined files are staged (no pdb, no test exe)", "bin/r3hd.pdb" not in names
              and "bin/m4_input_test.exe" not in names and "bin/r3hd.exe" in names and "app/licenses/x-LICENSE.txt" in names)
        check("the Settings launcher is staged with its role (M30)", "app/r3hd_launcher.exe" in names and json.loads(
            (t / "o1" / "payload" / "payload.json").read_bytes())["files"]["app/r3hd_launcher.exe"]["role"] == "launcher_native")
        check("text LF, batch CRLF", (t / "o1" / "payload" / "app" / "tools" / "a.py").read_bytes() == b"print(1)\n"
              and (t / "o1" / "payload" / "app" / "go.cmd").read_bytes() == b"@echo off\r\necho hi\r\n")
        with zipfile.ZipFile(t / "o1" / "payload" / "app" / "python" / "python311.zip") as zf:
            zn = zf.namelist()
        check("stdlib zip: .py only, excluded packages and caches left out", sorted(zn) == ["json/__init__.py", "os.py"])
        check("existing output refused", refused(lambda: build(t / "o1", bd, py, **kw), "OUTPUT_EXISTS"))
        (bd / "rexruntime.dll").write_bytes(b"MZ" + bytes(62) + ("C:\\Us" + "ers\\dev\\x.cpp").encode())
        check("binary with a developer path refused", refused(lambda: build(t / "o3", bd, py, **kw), "BINARY_DEVELOPER_PATH")
              and not (t / "o3").exists() and not (t / "o3.partial").exists())
        (bd / "rexruntime.dll").write_bytes(b"MZ" + bytes(62) + b"rexruntime.dll")
        (py / "python.exe").write_bytes(b"MZ other")
        check("unpinned Python refused", refused(lambda: build(t / "o4", bd, py, **kw), "PYTHON_PIN"))
        (py / "python.exe").write_bytes(b"MZ" + bytes(62) + b"py")
        (root / "lb" / "r3hd_launcher.exe").unlink()
        check("missing Settings launcher refused", refused(lambda: build(t / "o6", bd, py, **kw), "BUILD_MISSING"))
        (bd / "rexgpu-xenos.dll").unlink()
        check("missing binary refused", refused(lambda: build(t / "o5", bd, py, **kw), "BUILD_MISSING"))
    for n, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {n}")
    failed = sum(not ok for _, ok in checks)
    print(f"R3HD_STAGE_SELFTEST {'PASS' if not failed else 'FAIL'} checks={len(checks)}")
    return 0 if not failed else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=["build", "portable", "stdlib-digest", "selftest"])
    ap.add_argument("out", nargs="?")
    ap.add_argument("--build-dir", default=None)
    ap.add_argument("--python-dir", default=None)
    ap.add_argument("--skip-codegen-check", action="store_true")
    ap.add_argument("--portable-out", type=Path)
    ap.add_argument("--development-id")
    ap.add_argument("--crt-dir", type=Path)
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    defn = json.loads(DEFINITION.read_text(encoding="utf-8"))
    py = Path(a.python_dir) if a.python_dir else default_python_dir()
    try:
        if a.cmd == "portable":
            if not all((a.out, a.portable_out, a.development_id, a.crt_dir)):
                raise Refusal("USAGE", "portable STAGE --portable-out ZIP --development-id ID --crt-dir CRT")
            import r3hd_portable_zip
            try:
                r = r3hd_portable_zip.build(Path(a.out), a.portable_out, a.development_id, a.crt_dir)
            except (OSError, ValueError, KeyError) as e:
                raise Refusal("PORTABLE_REFUSED", str(e))
            print("R3HD_PORTABLE_ZIP " + json.dumps(r, sort_keys=True))
            return 0
        if a.cmd == "stdlib-digest":
            print(sha256_bytes(stdlib_zip(py, defn["python"]["stdlib_exclude"])))
            return 0
        if not a.out:
            raise Refusal("USAGE", "build OUT")
        bd = Path(a.build_dir) if a.build_dir else ROOT / defn["binaries"]["build_dir"]
        r = build(Path(a.out), bd, py, a.skip_codegen_check, defn)
        print(json.dumps(r, indent=1))
    except Refusal as e:
        print(f"R3HD_STAGE REFUSED {e.code}: {e.detail}", file=sys.stderr)
        return 2
    print("R3HD_STAGE OK (private payload; NOT publishable; not a legal clearance)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
