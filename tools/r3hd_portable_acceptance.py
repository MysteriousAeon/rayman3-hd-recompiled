#!/usr/bin/env python3
"""Isolated actual-ZIP path/Settings/mod/ACL acceptance; never starts a game.

python tools/r3hd_portable_acceptance.py ZIP SOURCE OUT [--mod ZIP]
SOURCE is read only; OUT must not exist. All extracted data and retained evidence stay private.
Game verification is separately owned by the established M6 hidden runner.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import r3hd_installer as engine
import r3hd_portable_zip as pack
from m46_lgpl import pe_tables


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archive", type=Path)
    ap.add_argument("source", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--mod", type=Path)
    ap.add_argument("--startup-source", type=Path, help="Test a development startup script in the extracted copy only; reseal its manifest entry, never the input ZIP")
    a = ap.parse_args()
    out = a.out.resolve()
    if not out.is_relative_to(pack.ROOT / "private/work"):
        raise ValueError("Acceptance output must be a new directory under private/work")
    out.mkdir()
    results = []
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("R3HD_")}

    def check(name, ok):
        results.append({"name": name, "pass": bool(ok)})
        (out / "results.json").write_bytes(pack.encoded(results))
        print(("PASS " if ok else "FAIL ") + name, flush=True)
        if not ok:
            raise AssertionError(name)

    def run(tag, args, expected=0):
        r = subprocess.run([str(x) for x in args], cwd=out, env=env, capture_output=True, timeout=600)
        (out / (tag + ".stdout")).write_bytes(r.stdout)
        (out / (tag + ".stderr")).write_bytes(r.stderr)
        check(tag, r.returncode == expected)
        return r

    check("archive audit", pack.check(a.archive)["result"] == "PASS")
    with zipfile.ZipFile(a.archive) as z:
        z.extractall(out / "Extracted Türkçe 東京 folder")
    home = out / "Extracted Türkçe 東京 folder" / pack.TOP
    if a.startup_source:
        rel = "app/tools/r3hd_portable.py"
        (home / rel).write_bytes(a.startup_source.read_bytes().replace(b"\r\n", b"\n"))
        manifest = engine.read_json(home / "portable.json")
        manifest["files"][rel] = {"size": (home / rel).stat().st_size, "sha256": engine.sha256(home / rel)}
        engine.write_json(home / "portable.json", manifest)
        check("development startup overlay recorded", engine.sha256(home / rel) == manifest["files"][rel]["sha256"])
    py = home / "app/python/python.exe"
    tool = home / "app/tools/r3hd_portable.py"
    run("prepare", [py, "-B", tool, "prepare", "--no-input", "--source", a.source.resolve()])
    run("native_model", [home / "app/r3hd_launcher.exe", "--no-ui"])
    dry = run("native_play_dry", [home / "app/r3hd_launcher.exe", "--play", "--dry-run", "--no-ui"])
    check("dry-run only", b"PLAY ENDED" in dry.stdout and b"argument" in dry.stdout)
    script = out / "settings.txt"
    script.write_bytes(b"profile hdplus\nset display windowed\nclick save\ndump saved\nreload\ndump reloaded\n")
    ui = out / "settings_ui"
    ui.mkdir()
    run("private_settings", [home / "app/r3hd_launcher.exe", "--ui-test", script, "--out", ui])
    saved = engine.read_json(home / "settings.json")
    check("private Settings persists in portable home", saved["preset"] == "hdplus")
    if a.mod:
        run("translation_import", [py, "-B", home / "app/tools/r3hd_mods.py", "import", a.mod.resolve(), "--home", home])
    # Preserve representative profile/history files and any real imported mod, then move the entire home.
    for rel in ("profiles/default/user/ leading space", "save_history/test/user/save"):
        f = home / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"synthetic user-owned preservation sentinel")
    kept = {p.relative_to(home).as_posix(): engine.sha256(p) for name in (*engine.USER_ITEMS, "data")
            for p in ([home / name] if (home / name).is_file() else (home / name).rglob("*")) if p.is_file()}
    (out / "user_hashes_before_relocation.json").write_bytes(pack.encoded(kept))
    relocated = out / "Relocated İ 東京 game"
    home.rename(relocated)
    home = relocated
    py = home / "app/python/python.exe"
    tool = home / "app/tools/r3hd_portable.py"
    run("relocated_prepare", [py, "-B", tool, "prepare", "--no-input"])
    run("relocated_model", [home / "app/r3hd_launcher.exe", "--no-ui"])
    run("relocated_play_dry", [home / "app/r3hd_launcher.exe", "--play", "--dry-run", "--no-ui"])
    check("relocation preserves all user and game bytes", all(engine.sha256(home / n) == sha for n, sha in kept.items()))
    # Deny actual directory writes for this disposable home only. Restore the exact ACL in finally.
    # The denial omits WRITE_DAC so restoring the saved ACL does not require taking ownership.
    acl = out / "restricted.ps1"
    acl.write_bytes(b'''param([string]$Target)
$ErrorActionPreference='Stop'
$original=[System.IO.Directory]::GetAccessControl($Target)
$originalSddl=$original.GetSecurityDescriptorSddlForm([System.Security.AccessControl.AccessControlSections]::Access)
$changed=[System.IO.Directory]::GetAccessControl($Target)
$sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User
Write-Output ('ADMIN_TOKEN ' + ([System.Security.Principal.WindowsPrincipal][System.Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator))
$rule=New-Object System.Security.AccessControl.FileSystemAccessRule($sid,'Write,Delete','ContainerInherit,ObjectInherit','None','Deny')
try {
  $changed.AddAccessRule($rule)
  [System.IO.Directory]::SetAccessControl($Target,$changed)
  & "$Target/app/python/python.exe" -B "$Target/app/tools/r3hd_portable.py" prepare --no-input
  $result=$LASTEXITCODE
} finally {
  $restore=New-Object System.Security.AccessControl.DirectorySecurity
  $restore.SetSecurityDescriptorSddlForm($originalSddl,[System.Security.AccessControl.AccessControlSections]::Access)
  [System.IO.Directory]::SetAccessControl($Target,$restore)
}
if ([System.IO.Directory]::GetAccessControl($Target).GetSecurityDescriptorSddlForm([System.Security.AccessControl.AccessControlSections]::Access) -cne $originalSddl) { throw 'ACL restoration differs' }
if ($result -ne 2) { throw "Restricted directory unexpectedly returned $result" }
Write-Output 'RESTRICTED_DIRECTORY PASS'
''')
    run("restricted_acl", ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", acl, "-Target", home])
    run("acl_restored_prepare", [py, "-B", tool, "prepare", "--no-input"])
    check("restricted failure preserves user bytes", all(engine.sha256(home / n) == sha for n, sha in kept.items()))
    # Record imported dependency closure from actual PEs. Windows API/system DLLs remain OS prerequisites.
    imports = {p.relative_to(home).as_posix(): sorted(pe_tables(p)[0])
               for folder in ("bin", "app/python") for p in (home / folder).glob("*") if p.suffix.lower() in (".dll", ".exe")}
    (out / "imports.json").write_bytes(pack.encoded(imports))
    for binary, names in imports.items():
        for name in names:
            if name.lower().startswith(("msvcp", "vcruntime", "concrt")):
                check("local CRT " + binary + " -> " + name, (home / Path(binary).parent / name).is_file())
    (out / "home.txt").write_bytes(str(home).encode("utf-8"))
    print(f"PORTABLE_ACCEPTANCE PASS checks={len(results)} game_starts=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
