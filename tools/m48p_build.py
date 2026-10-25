#!/usr/bin/env python3
"""M48-P (D-087): build the PRIVATE playtest setup from the frozen M46/M48 runtime, the M47 Turkish candidate and the
current installer sources, and write its manifest. Nothing is compiled except the Inno Setup script; nothing is uploaded.

    python tools/m48p_build.py OUT [--mod ZIP] [--test-variant NAME --dpi-proxy PT] [--fast]

OUT/stage/            r3hd_stage.py build (payload/ + the LGPL corresponding-source archive), audit PASS required
OUT/work/flags/       tools/m48p_flags.py output
OUT/dist/             Rayman3HDRecompiled-<version>-setup.exe, r3hd-lgpl-source-<version>.zip, MANIFEST.json,
                      SHA256SUMS.txt (the files a playtester would receive: the setup and its companion source archive)
--test-variant NAME   a test-only build (OUT/test/NAME/; e.g. a DPI proxy font) that is never a candidate.

Refuses (exit 2) when a runtime binary of the build tree or of the staged payload differs from the frozen M48 hashes,
when the Turkish package is not the M47 candidate, or when the payload audit fails.
"""
import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISCC = ROOT / "external" / "innosetup" / "ISCC.exe"
ISS = ROOT / "tools" / "installer" / "r3hd_setup.iss"
BUILD = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
MOD = ROOT / "private" / "tr" / "rayman3hd-turkish" / "build" / "preview" / "tr_full_dev-0_2_0.zip"
# The frozen M46 build of the M48 replay candidate (reports/milestone48/REPORT.md section 2).
FROZEN = {
    "r3hd.exe": "fc7c62694c4d684bfd4243af3e0c3b0d872a336eabce6aebcaf77c6596cb56df",
    "rexruntime.dll": "2e33264866bc6cddc9da63fa999f867c7f1049ea147030e1aa6dab4c414efe89",
    "rexgpu-xenos.dll": "67210f861524c2f75a5d23d1ddb76f61956051c859d982157d8f1df3d827a7d8",
    "ffmpeg.dll": "68dd542c69763e8ceebedcc8eeaf3173bc14221d6ab08010575841513ad55229",
    "mspack.dll": "fa48bfb0b688d2366cc4131b2cd98d3b1e1417a8c5d44448103bbbf61676bd97",
}
MOD_SHA256 = "39b220e75e7c38ea04500ec17acaee57511fbba49fe0ec9b3475f2a6b015ae2f"
MOD_ID, MOD_VERSION = "tr.full.dev", "0.2.0-dev"
VERSION = "0.36.0-private-playtest"
SETUP_NAME = f"Rayman3HDRecompiled-{VERSION}-setup.exe"


class Refused(Exception):
    pass


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def run(cmd, log: Path):
    r = subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(r.stdout + r.stderr, encoding="utf-8")
    if r.returncode != 0:
        raise Refused(f"{Path(str(cmd[1]) if len(cmd) > 1 else str(cmd[0])).name} failed ({r.returncode}); see {log}")
    return r.stdout


def check_frozen(where: Path, label: str) -> dict:
    out = {}
    for name, want in FROZEN.items():
        got = sha(where / name)
        if got != want:
            raise Refused(f"{label} {name}: {got} is not the frozen M48 binary {want}")
        out[name] = {"bytes": (where / name).stat().st_size, "sha256": got}
    return out


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--mod", type=Path, default=MOD)
    ap.add_argument("--test-variant")
    ap.add_argument("--dpi-proxy", type=int)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--reuse-stage", action="store_true", help="test variants: use OUT/stage as it is")
    a = ap.parse_args()
    out = a.out.resolve()
    logs = out / "logs"
    try:
        binaries = check_frozen(BUILD, "build tree")
        mod_sha = sha(a.mod)
        with zipfile.ZipFile(a.mod) as z:
            m = json.loads(z.read("mod.json").decode("utf-8"))
        if mod_sha != MOD_SHA256 or m.get("id") != MOD_ID or m.get("version") != MOD_VERSION:
            raise Refused(f"{a.mod}: {m.get('id')} {m.get('version')} {mod_sha} is not the M47 candidate {MOD_SHA256}")
        stage = out / "stage"
        if not (a.reuse_stage and (stage / "payload" / "payload.json").is_file()):
            if stage.exists():
                shutil.rmtree(stage)
            out.mkdir(parents=True, exist_ok=True)
            run([sys.executable, "tools/r3hd_stage.py", "build", stage], logs / "stage.log")
        payload = stage / "payload"
        staged = check_frozen(payload / "bin", "staged payload")
        audit = run([sys.executable, "tools/r3hd_release_audit.py", "payload", payload], logs / "audit.log")
        pj = json.loads((payload / "payload.json").read_text(encoding="utf-8"))
        lgpl = sorted(stage.glob("r3hd-lgpl-source-*.zip"))
        if len(lgpl) != 1:
            raise Refused(f"expected one LGPL source archive in {stage}, found {len(lgpl)}")
        flags = out / "work" / "flags"
        run([sys.executable, "tools/m48p_flags.py", flags], logs / "flags.log")
        dest = out / "test" / a.test_variant if a.test_variant else out / "dist"
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        defines = [f"/DPayloadDir={payload}", f"/DOutputDir={dest}", f"/DBundledMod={a.mod.resolve()}", f"/DFlagDir={flags}"]
        if a.dpi_proxy:
            defines.append(f"/DDpiProxyFont={a.dpi_proxy}")
        if a.fast:
            defines.append("/DFastCompression")
        run([ISCC, "/Q", *defines, ISS], logs / f"iscc_{a.test_variant or 'dist'}.log")
        setup = dest / SETUP_NAME
        if not setup.is_file():
            raise Refused(f"ISCC wrote no {setup}")
        if a.test_variant:
            print(f"M48P_BUILD TEST {a.test_variant} {setup} {sha(setup)}")
            return 0
        shutil.copy2(lgpl[0], dest / lgpl[0].name)
        head = git("rev-parse", "HEAD")
        dirty = bool(git("status", "--porcelain"))
        manifest = {
            "schema": 1,
            "product": "Rayman 3 HD Recompiled - unofficial private playtest (not affiliated with or endorsed by Ubisoft)",
            "version": VERSION,
            "classification": "PRIVATE PLAYTEST - not publishable (D-065 gates R-01 / R-02 open); see reports/milestone48p",
            "built_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_head": head, "git_worktree_dirty": dirty,
            "setup": {"file": setup.name, "bytes": setup.stat().st_size, "sha256": sha(setup)},
            "lgpl_source": {"file": lgpl[0].name, "bytes": lgpl[0].stat().st_size, "sha256": sha(lgpl[0])},
            "payload": {"id": pj.get("payload_id"), "version": pj.get("version"), "files": len(pj.get("files", []))},
            "runtime_binaries": staged,
            "runtime_equals_frozen_m48": staged == binaries,
            "launcher": {"sha256": sha(payload / "app" / "r3hd_launcher.exe")},
            "turkish_mod": {"file": a.mod.name, "id": MOD_ID, "version": MOD_VERSION, "bytes": a.mod.stat().st_size,
                            "sha256": mod_sha, "status": "1,120 reviewed drafts, 0 human-approved: NOT FINAL",
                            "default": "installed and enabled on a fresh installation (r3hd_bundled_mods.py policy)"},
            "gameplay_subtitles": "experimental D-081 option: on by default for a fresh installation (engine set-option)",
            "inno_setup": {"iscc_sha256": sha(ISCC), "languages": ["en (Default.isl)", "tr (Languages\\Turkish.isl)"]},
            "dependencies": ["Windows 10/11 x64", "Microsoft Visual C++ Redistributable 2015-2022 (x64)",
                             "a Direct3D 12 GPU", "the tester's own Rayman 3 HD Xbox 360 XBLA package (5841123F, no TU)"],
            "notices": sorted(str(p.relative_to(payload)).replace("\\", "/") for p in (payload / "app").rglob("*")
                              if p.is_file() and (p.parent.name == "licenses" or p.name == "THIRD_PARTY_NOTICES.txt")),
            "audit": audit.strip().splitlines()[-1] if audit.strip() else "",
            "known_limitations": "reports/milestone48p/REPORT.md section 11",
        }
        (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
        sums = "".join(f"{sha(p)} *{p.name}\n" for p in sorted(dest.iterdir()) if p.name != "SHA256SUMS.txt")
        (dest / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
        print(f"M48P_BUILD OK {setup} {manifest['setup']['sha256']} payload={manifest['payload']['id'][:16]} "
              f"runtime_frozen={manifest['runtime_equals_frozen_m48']} head={head[:7]}{' dirty' if dirty else ''}")
        return 0
    except Refused as e:
        print(f"M48P_BUILD REFUSED {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
