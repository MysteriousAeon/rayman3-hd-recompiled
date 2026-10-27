#!/usr/bin/env python3
"""M29 (D-066): regression of the private installer prototype (run by tools/build_milestone8.bat).

Starts no game and no installer: it runs the engine and staging selftests (synthetic fixtures), and checks the wiring
that must not drift: the payload definition and allowlist, the Inno Setup script's privilege / ownership rules, the
launchers, the bundled-Python branch of play.ps1, the registry labels the Custom page shows, and the build's path map.
With --payload DIR it also audits a staged payload (tools/r3hd_stage.py build OUT -> OUT/payload).
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
checks = []


def check(name, ok):
    checks.append((name, bool(ok)))


def run(*args):
    r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=ROOT)
    if r.returncode:
        # Keep the nested failure's evidence in the build log; a bare failed aggregate cannot be diagnosed.
        print(f"Nested {Path(args[0]).name} exited {r.returncode}:", flush=True)
        print(r.stdout + r.stderr, flush=True)
    return r.returncode, r.stdout + r.stderr


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--payload")
    a = ap.parse_args()

    rc, out = run(TOOLS / "issue3_installer_regression.py")
    check("Issue #3 process-query safety", rc == 0)
    rc, out = run(TOOLS / "r3hd_installer.py", "selftest")
    check("engine selftest", rc == 0 and "R3HD_INSTALLER_SELFTEST PASS" in out)
    rc, out = run(TOOLS / "r3hd_stage.py", "selftest")
    check("staging selftest", rc == 0 and "R3HD_STAGE_SELFTEST PASS" in out)

    defn = json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))
    pallow = json.loads((ROOT / "config" / "release" / "payload_allowlist.json").read_text(encoding="utf-8"))
    check("payload is marked not publishable", defn["publishable"] is False and "NOT publishable" in defn["note"])
    check("payload binaries are the runtime files and the M46 LGPL DLLs", defn["binaries"]["files"]
          == ["r3hd.exe", "rexruntime.dll", "rexgpu-xenos.dll", "ffmpeg.dll", "mspack.dll"])
    check("every app file exists in the repository", all((ROOT / s).is_file() for s in defn["app_files"].values()))
    check("payload carries no game file, save or capture path", not any(
        re.search(r"private/|\.(xex|bhf|btf|bik|lvl|ptr|bmp|png|wav)$|(^|/)(saves?|profiles|save_history|captures?)/", x, re.I)
        for pair in defn["app_files"].items() for x in pair))
    check("every staged path has an allowlist entry or binary role",
          all(any(re.fullmatch(g["glob"].replace(".", r"\.").replace("**/", "(.*/)?").replace("*", "[^/]*"), d)
                  for g in pallow["allow"]) for d in list(defn["app_files"]) + list(defn["licenses"]["files"]))
          and set(pallow["binaries"]) == {"bin/" + n for n in defn["binaries"]["files"]}
          | {"app/python/" + n for n in defn["python"]["files"] if n.endswith((".exe", ".dll"))} | {"app/python/python311.zip"}
          | {defn["launcher"]["dest"]})  # M30: the Settings launcher
    check("bundled Python pinned (four files and the stdlib zip)", len(defn["python"]["files"]) == 4
          and re.fullmatch(r"[0-9a-f]{64}", defn["python"]["stdlib_zip_sha256"] or ""))
    check("licence texts for the LGPL components are staged", {"app/licenses/FFmpeg-COPYING.LGPLv2.1.txt",
                                                               "app/licenses/libmspack-COPYING.LIB.txt"} <= set(defn["licenses"]["files"]))
    notices = (ROOT / "tools" / "installer" / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    check("notices name the open licence gap", "disruptorplus" in notices)
    # M46 (D-084): FFmpeg and libmspack are their own DLLs; the source / replacement notice is staged.
    check("notices: LGPL code only in ffmpeg.dll / mspack.dll, source notice staged",
          "bin\\ffmpeg.dll" in notices and "bin\\mspack.dll" in notices and "licenses\\LGPL-SOURCE.txt" in notices
          and defn["app_files"].get("app/licenses/LGPL-SOURCE.txt") == "tools/installer/LGPL-SOURCE.txt")
    # M45 (D-083): the DXBC hash is DXC-derived (NCSA) and its licence text is staged; AMD's source is not built in.
    check("notices: DXBC hash under the DXC licence, licence text staged",
          "licenses\DirectXShaderCompiler-LICENSE.txt" in notices and "no longer built in" in notices
          and defn["app_files"].get("app/licenses/DirectXShaderCompiler-LICENSE.txt")
          == "tools/installer/DirectXShaderCompiler-LICENSE.txt")

    iss = (ROOT / "tools" / "installer" / "r3hd_setup.iss").read_text(encoding="utf-8")
    check("setup: per-user, no administrator", "PrivilegesRequired=lowest" in iss and "PrivilegesRequiredOverridesAllowed" not in iss)
    check("setup: x64, Windows 10 or later", "ArchitecturesAllowed=x64compatible" in iss and "MinVersion=10.0" in iss)
    # M48-P: the playtest build (#ifdef Playtest) also carries the bundled mod and the flag bitmaps, never copied
    plain = re.sub(r"(?ms)^#ifdef Playtest\n(.*?)^#endif\n", "", iss.split("[Files]", 1)[1].split("\n[", 1)[0])
    playtest = re.findall(r"(?ms)^#ifdef Playtest\n(.*?)^#endif\n", iss.split("[Files]", 1)[1].split("\n[", 1)[0])
    files = re.findall(r"^Source: .*$", plain, re.M)
    extra = [ln for blk in playtest for ln in re.findall(r"^Source: .*$", blk, re.M)]
    # M49 (D-088): the bilingual build also copies the bundled mod's .zip to {app}\extras (Settings > Mods later)
    copied = [ln for ln in extra if "dontcopy" not in ln]
    check("setup: the payload is the only [Files] entry and goes to {tmp} (the engine owns the installation); the "
          "bilingual build's extra entries are never copied, except the bundled mod's .zip into {app}\\extras",
          len(files) == 1 and 'DestDir: "{tmp}\\payload"' in files[0] and "dontcopy" in files[0]
          and len(copied) == 1 and copied[0].startswith('Source: "{#BundledMod}"') and 'DestDir: "{app}\\extras"' in copied[0])
    section = iss.split("[UninstallDelete]", 1)[1].split("\n[", 1)[0]  # M31: [InstallDelete] has its own entry
    udel = re.findall(r"^Type: (\w+); Name: \"([^\"]+)\"", section, re.M)
    check("setup: the uninstaller deletes only app\\ and an empty folder", udel == [("filesandordirs", "{app}\\app"),
                                                                                   ("dirifempty", "{app}")])
    check("setup: user data removal only on an explicit choice, default keep",
          "MB_DEFBUTTON2" in iss and "REMOVEUSERDATA|0" in iss and "--confirm" in iss)
    # M31: a test run writes shortcuts only into the folders its /STARTMENUDIR and /DESKTOPDIR name (none without them)
    check("setup: test mode writes no registry entry or launch, and shortcuts only into named test folders",
          "CreateUninstallRegKey=not IsTestMode" in iss and iss.count("Check: not IsTestMode") == 2
          and "if IsTestMode then Result := ExpandConstant('{param:STARTMENUDIR|}')" in iss
          and "if IsTestMode then Result := ExpandConstant('{param:DESKTOPDIR|}')" in iss
          and len(re.findall(r"^Name: \"\{code:(MenuDir|DesktopDir)\}", iss, re.M)) == 7  # M32: + Settings on the desktop; Play twice (with or without the local icon)
          and "{userprograms}" not in iss.split("[Code]")[0] and "{userdesktop}" not in iss.split("[Code]")[0])
    # M31: the install run is ExecAndLogOutput (a console program is always hidden there) for its progress lines
    # M48-P: every bundled-Python run writes no bytecode; only the install run (output captured: hidden) is not SW_HIDE
    check("setup: engine runs hidden with bytecode writing off", iss.count("python.exe") == iss.count("'-B \"'")
          and iss.count("SW_SHOWNORMAL") == 1 and "ExecAndLogOutput(PayloadPath('app\\python\\python.exe')," in iss
          and iss.count("SW_HIDE") >= 3)
    check("setup: the uninstaller asks the engine (--check) before deleting anything",
          "function InitializeUninstall: Boolean;" in iss and "uninstall --check" in iss and "Result := Code = 0;" in iss)
    check("setup: no network or download", not re.search(r"idp|DownloadTemporaryFile|CreateDownloadPage|http", iss, re.I))

    play = (TOOLS / "play.ps1").read_text(encoding="utf-8")
    check("play.ps1: bundled Python in an installed copy, PATH Python in a repository",
          "Join-Path $repo 'python\\python.exe'" in play and "& $python @resolverArgs" in play)
    for name in ("play.cmd", "settings.cmd"):
        txt = (ROOT / "tools" / "installer" / name).read_text(encoding="utf-8")
        check(f"{name}: runs from the installation it sits in", "%~dp0" in txt and "-UserHome" in txt if name == "play.cmd"
              else "%~dp0" in txt and "configure --home" in txt and " -B " in txt)

    reg = json.loads((ROOT / "config" / "settings" / "registry.json").read_text(encoding="utf-8"))
    check("registry: every setting has a UI label", all(s.get("label") for s in reg["settings"].values()))
    check("registry: HD+ = layer_coords separate, texture_orient corrected provisionally (M43)",
          reg["settings"]["layer_coords"]["hdplus"] == "separate" and reg["settings"]["texture_orient"]["hdplus"] == "corrected"
          and reg["settings"]["texture_orient"].get("provisional") is True)

    bat = (TOOLS / "build_milestone8.bat").read_text(encoding="utf-8")
    check("build: path map and PDB name for the SDK and the game", bat.count("%R3HD_PATHMAP%") >= 3
          and bat.count("/pdbaltpath:%%_PDB%%") == 3)

    if a.payload:
        rc, out = run(TOOLS / "r3hd_release_audit.py", "payload", a.payload)
        check("staged payload audit", rc == 0 and "R3HD_RELEASE_AUDIT PASS" in out)

    for n, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {n}")
    failed = sum(not ok for _, ok in checks)
    print(f"M29_INSTALLER_REGRESSION {'PASS' if not failed else 'FAIL'} checks={len(checks)} failures={failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
