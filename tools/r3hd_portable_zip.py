#!/usr/bin/env python3
"""Build/check a portable ZIP from an audited release stage (private by default).

python tools/r3hd_portable_zip.py build STAGE OUT.zip --development-id NAME --crt-dir CRT
python tools/r3hd_portable_zip.py check OUT.zip
Never rewrites a stage, version, existing archive or installed home. No publication.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

import r3hd_installer as engine
import r3hd_release_audit as audit
from r3hd_portable import safe_path

ROOT = Path(__file__).resolve().parents[1]
TOP = "Rayman3HDRecompiled-Portable"
DATE = (1980, 1, 1, 0, 0, 0)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=1, sort_keys=True) + "\n").encode()


def command(action):
    return ("@echo off\r\nsetlocal\r\n"
            '"%~dp0app\\python\\python.exe" -B "%~dp0app\\tools\\r3hd_portable.py" ' + action + '\r\n'
            "if errorlevel 1 (pause & exit /b 2)\r\n").encode()


def defined_members():
    d = json.loads((ROOT / "config/release/payload.json").read_bytes())
    return (set(d["app_files"]) | set(d["licenses"]["files"]) |
            {"bin/" + n for n in d["binaries"]["files"]} | {d["launcher"]["dest"]} |
            {"app/python/" + n for n in d["python"]["files"]} |
            {"app/python/python311.zip", "app/python/python311._pth"})


def build(stage, out, development_id, crt_dir, public_release=False):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", development_id):
        raise ValueError("Use a short development identifier, not a release version")
    if any(p.exists() for p in (out, out.with_suffix(out.suffix + ".partial"),
                               out.with_suffix(out.suffix + ".sha256"), out.with_suffix(out.suffix + ".manifest.json"))):
        raise ValueError("Output exists; never overwrite a package")
    payload = stage / "payload"
    mf = engine.load_payload(payload)
    if public_release and (not mf.get("publishable") or out.name != f"Rayman3HDRecompiled-{mf['version']}-portable.zip"):
        raise ValueError("Public packaging requires an approved public payload and exact release filename")
    if set(mf["files"]) != defined_members():
        raise ValueError("Stage differs from the exact release definition")
    allow, binaries, pins = audit.load_payload_rules(audit.DEFAULT_PAYLOAD_ALLOWLIST, audit.DEFAULT_PAYLOAD_DEF)
    result = audit.audit_payload(str(payload), allow, binaries, pins,
                                 audit.GameHashes([audit.DEFAULT_MANIFEST], audit.DEFAULT_RELEASES), public_release)
    if result["verdict"] != "PASS":
        raise ValueError("Payload audit refused: " + str(result["reason_counts"]))
    if b"def check_platform(vc_dir=None):" not in (payload / "app/tools/r3hd_installer.py").read_bytes():
        raise ValueError("Stage uses an older engine without application-local CRT validation; restage current source")
    if b"activeCodePage" not in (payload / "bin/r3hd.exe").read_bytes():
        raise ValueError("Runtime has no UTF-8 path manifest; rebuild before packaging")
    # Retain the existing private R-01 boundary. Never print key material.
    r = subprocess.run([sys.executable, str(ROOT / "tools/m50_r01_audit.py"), "keys", str(payload),
                        "--base", str(payload)], capture_output=True, check=True)
    keys = json.loads(r.stdout)
    hits = {row["file"].replace("\\", "/"): row["hits"] for row in keys["files"] if row["hits"]}
    if keys["unresolved"] or hits != {"bin/rexruntime.dll": {"xe_xex2_retail_key": 1}}:
        raise ValueError("Private runtime R-01 boundary differs; release review required")
    # Corresponding source travels inside the ZIP, not as an easily separated optional download.
    lgpl = stage / f"r3hd-lgpl-source-{mf['version']}.zip"
    with zipfile.ZipFile(lgpl) as z:
        source = json.loads(z.read("r3hd-lgpl-source/MANIFEST.json"))
        if source["program_version"] != mf["version"]:
            raise ValueError("LGPL source version differs from payload")
    # The installer console entry points bypass preparation; expose only the portable entry points.
    base_payload_id = mf["payload_id"]
    for obsolete in ("app/play.cmd", "app/settings.cmd"):
        mf["files"].pop(obsolete, None)
    mf["payload_id"] = digest("".join(f"{r}\t{i['size']}\t{i['sha256']}\n"
        for r, i in sorted(mf["files"].items())).encode())
    files = {rel: (payload / rel).read_bytes() for rel in mf["files"]}
    files["payload.json"] = encoded(mf)
    files["app/tools/r3hd_portable.py"] = (ROOT / "tools/r3hd_portable.py").read_bytes().replace(b"\r\n", b"\n")
    # Only unmodified pinned retail x64 redist files, never debug or system-directory copies.
    crt = json.loads((ROOT / "config/release/portable_crt.json").read_bytes())
    for name, sha in crt["files"].items():
        data = (crt_dir / name).read_bytes()
        if digest(data) != sha:
            raise ValueError("CRT pin mismatch: " + name)
        files["bin/" + name] = data
    files["app/python/vcruntime140.dll"] = files["bin/vcruntime140.dll"]
    files["app/licenses/PORTABLE-CRT.txt"] = (ROOT / "tools/installer/PORTABLE-CRT.txt").read_bytes().replace(b"\r\n", b"\n")
    files["app/licenses/portable_crt.json"] = encoded(crt)
    files.update({"Play.cmd": command("play"), "Settings.cmd": command("settings"),
                  "PORTABLE.txt": (ROOT / "tools/installer/PORTABLE.txt").read_bytes().replace(b"\r\n", b"\n"),
                  lgpl.name: lgpl.read_bytes()})
    files["portable.json"] = encoded({"schema": 1, "data_model": "beside-application", "publishable": public_release,
        **({"release_version": mf["version"]} if public_release else {"development_id": development_id}),
        "application_version": mf["version"], "payload_id": mf["payload_id"],
        "base_payload_id": base_payload_id,
        "prerequisites": {"windows": "10 1903+ or 11, x64", "vc_runtime": "application-local " + crt["version"]},
        "files": {r: {"size": len(b), "sha256": digest(b)} for r, b in sorted(files.items())}})
    partial = out.with_suffix(out.suffix + ".partial")
    with zipfile.ZipFile(partial, "w") as z:
        for rel, data in sorted(files.items()):
            info = zipfile.ZipInfo(TOP + "/" + rel, DATE)
            info.create_system = 0
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data, compresslevel=9)
    report = check(partial)
    partial.rename(out)
    out.with_suffix(out.suffix + ".sha256").write_bytes((report["sha256"] + "  " + out.name + "\n").encode())
    out.with_suffix(out.suffix + ".manifest.json").write_bytes(encoded(report))
    return report


def check(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or any(not n.startswith(TOP + "/") or
                not safe_path(n) or n.endswith("/") for n in names):
            raise ValueError("Unsafe/duplicate archive entries")
        manifest = json.loads(z.read(TOP + "/portable.json"))
        expected = {TOP + "/" + r for r in manifest["files"]} | {TOP + "/portable.json"}
        if set(names) != expected:
            raise ValueError("Archive members differ from manifest")
        for rel, row in manifest["files"].items():
            data = z.read(TOP + "/" + rel)
            if len(data) != row["size"] or digest(data) != row["sha256"]:
                raise ValueError("Archive checksum mismatch: " + rel)
        payload = json.loads(z.read(TOP + "/payload.json"))
        if manifest.get("publishable"):
            if (manifest.get("release_version") != payload["version"] or
                    manifest["application_version"] != payload["version"] or
                    payload.get("publishable") is not True or "development_id" in manifest):
                raise ValueError("Public portable metadata differs from the approved payload")
        if set(payload["files"]) != defined_members() - {"app/play.cmd", "app/settings.cmd"}:
            raise ValueError("Archive payload differs from the exact release definition")
        additions = {"Play.cmd", "Settings.cmd", "PORTABLE.txt", "payload.json", "app/tools/r3hd_portable.py",
                     "app/python/vcruntime140.dll", "app/licenses/PORTABLE-CRT.txt", "app/licenses/portable_crt.json",
                     f"r3hd-lgpl-source-{payload['version']}.zip"}
        crt = json.loads((ROOT / "config/release/portable_crt.json").read_bytes())
        additions |= {"bin/" + name for name in crt["files"]}
        if set(manifest["files"]) != set(payload["files"]) | additions:
            raise ValueError("Unexpected portable contents (including possible user data)")
        for rel, row in payload["files"].items():
            if manifest["files"][rel] != {"size": row["size"], "sha256": row["sha256"]}:
                raise ValueError("Portable manifest differs from payload: " + rel)
        for name, sha in crt["files"].items():
            if manifest["files"]["bin/" + name]["sha256"] != sha:
                raise ValueError("Archive CRT pin mismatch: " + name)
        if manifest["files"]["app/python/vcruntime140.dll"]["sha256"] != crt["files"]["vcruntime140.dll"]:
            raise ValueError("Python CRT pin mismatch")
        required = {"app/PROVENANCE.md", "app/THIRD_PARTY_NOTICES.txt", "app/licenses/TinySHA1-LICENSE.txt",
                    "app/licenses/LGPL-SOURCE.txt", "app/python/LICENSE.txt", "app/r3hd_launcher.exe"}
        if not required <= set(manifest["files"]):
            raise ValueError("Required notices/launcher absent")
        # Judge actual archive bytes independently of both editable package manifests.
        _, binaries, pins = audit.load_payload_rules(audit.DEFAULT_PAYLOAD_ALLOWLIST, audit.DEFAULT_PAYLOAD_DEF)
        game_hashes = audit.GameHashes([audit.DEFAULT_MANIFEST], audit.DEFAULT_RELEASES)
        for rel in payload["files"]:
            data = z.read(TOP + "/" + rel)
            if digest(data) in game_hashes.hashes:
                raise ValueError("Game data in archive: " + rel)
            if rel in pins and digest(data) != pins[rel]:
                raise ValueError("Archive Python pin mismatch: " + rel)
            if rel in binaries and audit.binary_dev_paths(data):
                raise ValueError("Developer path in archived binary: " + rel)
    return {"result": "PASS", "files": len(names), "sha256": engine.sha256(path),
            "bytes": path.stat().st_size,
            **({"release_version": manifest["release_version"]} if manifest.get("publishable")
               else {"development_id": manifest["development_id"]}),
            "application_version": manifest["application_version"], "publishable": manifest.get("publishable", False)}


def compare_stage(stage, archive):
    """Verify actual ZIP bytes against the exact audited installer input, including source/notices.

    This compares pristine distributions; recipient LGPL replacements remain a startup policy.
    """
    report = check(archive)
    payload = stage / "payload"
    base = engine.load_payload(payload)
    with zipfile.ZipFile(archive) as z:
        portable = json.loads(z.read(TOP + "/portable.json"))
        inner = json.loads(z.read(TOP + "/payload.json"))
        if (portable["base_payload_id"] != base["payload_id"] or
                portable["application_version"] != base["version"] or inner["version"] != base["version"]):
            raise ValueError("Installer/ZIP version or base payload identity differs")
        omitted = {"app/play.cmd", "app/settings.cmd"}
        if set(base["files"]) - set(inner["files"]) != omitted or set(inner["files"]) - set(base["files"]):
            raise ValueError("Unexpected installer/ZIP payload difference")
        shared = {}
        for rel in sorted(inner["files"]):
            data = z.read(TOP + "/" + rel)
            if data != (payload / rel).read_bytes():
                raise ValueError("Installer/ZIP shared bytes differ: " + rel)
            shared[rel] = {"size": len(data), "sha256": digest(data)}
        source = f"r3hd-lgpl-source-{base['version']}.zip"
        if z.read(TOP + "/" + source) != (stage / source).read_bytes():
            raise ValueError("Installer/ZIP corresponding source differs")
    return {"result": "PASS", "archive": archive.name, "sha256": report["sha256"],
            "bytes": report["bytes"], "version": base["version"], "base_payload_id": base["payload_id"],
            "shared_files": shared, "installer_only_payload": sorted(omitted),
            "lgpl_source_sha256": engine.sha256(stage / source), "publishable": report["publishable"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("stage", type=Path)
    b.add_argument("out", type=Path)
    b.add_argument("--development-id", required=True)
    b.add_argument("--public-release", action="store_true", help="Package a separately approved public payload")
    b.add_argument("--crt-dir", type=Path, required=True, help="Pinned retail x64 Microsoft.VC145.CRT folder")
    c = sub.add_parser("check")
    c.add_argument("archive", type=Path)
    pair = sub.add_parser("compare-stage", help="verify the actual ZIP against its installer input stage")
    pair.add_argument("stage", type=Path)
    pair.add_argument("archive", type=Path)
    a = ap.parse_args()
    try:
        if a.cmd == "build":
            report = build(a.stage, a.out, a.development_id, a.crt_dir, a.public_release)
        elif a.cmd == "compare-stage":
            report = compare_stage(a.stage, a.archive)
        else:
            report = check(a.archive)
        print("R3HD_PORTABLE_ZIP " + json.dumps(report, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, engine.Refusal) as e:
        print("R3HD_PORTABLE_ZIP REFUSED " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
