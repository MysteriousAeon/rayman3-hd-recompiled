#!/usr/bin/env python3
"""M49 (D-088): build the private 0.49.0 candidate setup from the current build tree, the release copy of the Turkish
translation and the installer sources, and write its manifest. Nothing is compiled except the Inno Setup script;
nothing is uploaded. The M48 replay candidate and the M48-P setup are never touched (their folders are not written).

    python tools/m49_build.py OUT --expect-runtime HASHES.json [--test-variant NAME --dpi-proxy PT] [--fast]

OUT/stage/            r3hd_stage.py build (payload/ + the LGPL corresponding-source archive), audit PASS required
OUT/work/flags/       tools/m48p_flags.py output
OUT/dist/             Rayman3HDRecompiled-0.49.0-setup.exe, r3hd-lgpl-source-0.49.0.zip, MANIFEST.json, SHA256SUMS.txt
--expect-runtime      {"r3hd.exe": sha256, ...} of the integrated M49 build (written by `--record-runtime FILE`);
                      the build refuses when the build tree or the staged payload differs from it
--record-runtime F    write the build tree's runtime hashes to F and stop (after a full build that ended M8_BUILD_OK)

Refuses (exit 2) when the Turkish package is not the M49 release copy, when OUT/dist exists, or when the audit fails.
"""
import argparse
import datetime
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from m48p_build import BUILD, FROZEN, ISCC, ISS, ROOT, Refused, git, run, sha  # noqa: E402

MOD = ROOT / "private" / "m49" / "turkish" / "rayman3hd-turkish-1.0.0.zip"
MOD_SHA256 = "5f7c609295936dd5a14df789995d4e51d11cfc5c8f66952809fd8b1b8641aa68"
MOD_ID, MOD_VERSION = "tr.full.dev", "1.0.0"
MOD_SOURCE = "M47 / M48-P candidate 39b220e7..., overrides byte-identical (tools/m49_turkish_package.py)"
VERSION = "0.49.0"
SETUP_NAME = f"Rayman3HDRecompiled-{VERSION}-setup.exe"
RUNTIME = tuple(FROZEN)
TAG = "M49_BUILD"
CLASSIFICATION = ("PRIVATE CANDIDATE - not publishable while D-065 gates R-01 / R-02 are open; "
                  "see reports/milestone49/REPORT.md")
# Later milestones reuse this builder (tools/m50_build.py): each callable gets the staged payload folder, may raise
# Refused, and returns manifest entries.
EXTRA_CHECKS = []


def runtime_hashes(where: Path) -> dict:
    return {n: {"bytes": (where / n).stat().st_size, "sha256": sha(where / n)} for n in RUNTIME}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--expect-runtime", type=Path)
    ap.add_argument("--record-runtime", type=Path)
    ap.add_argument("--test-variant")
    ap.add_argument("--dpi-proxy", type=int)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--reuse-stage", action="store_true", help="test variants: use OUT/stage as it is")
    a = ap.parse_args()
    out = a.out.resolve()
    logs = out / "logs"
    try:
        if a.record_runtime:
            a.record_runtime.parent.mkdir(parents=True, exist_ok=True)
            a.record_runtime.write_text(json.dumps({n: v["sha256"] for n, v in runtime_hashes(BUILD).items()}, indent=1)
                                        + "\n", encoding="utf-8")
            print(f"{TAG} RECORDED {a.record_runtime}")
            return 0
        if not a.expect_runtime:
            raise Refused("--expect-runtime is required (the hashes of the integrated M49 build)")
        want = json.loads(a.expect_runtime.read_text(encoding="utf-8"))
        tree = runtime_hashes(BUILD)
        if {n: v["sha256"] for n, v in tree.items()} != want:
            raise Refused(f"build tree runtime differs from {a.expect_runtime}")
        if want == {n: FROZEN[n] for n in RUNTIME}:
            raise Refused("the build tree is still the frozen M48 runtime; build M49 first")
        mod_sha = sha(MOD)
        with zipfile.ZipFile(MOD) as z:
            m = json.loads(z.read("mod.json").decode("utf-8"))
        if mod_sha != MOD_SHA256 or m.get("id") != MOD_ID or m.get("version") != MOD_VERSION:
            raise Refused(f"{MOD}: {m.get('id')} {m.get('version')} {mod_sha} is not the M49 release copy {MOD_SHA256}")
        stage = out / "stage"
        if not (a.reuse_stage and (stage / "payload" / "payload.json").is_file()):
            if stage.exists():
                shutil.rmtree(stage)
            out.mkdir(parents=True, exist_ok=True)
            run([sys.executable, "tools/r3hd_stage.py", "build", stage], logs / "stage.log")
        payload = stage / "payload"
        staged = runtime_hashes(payload / "bin")
        if staged != tree:
            raise Refused("staged payload runtime differs from the build tree")
        audit = run([sys.executable, "tools/r3hd_release_audit.py", "payload", payload], logs / "audit.log")
        pj = json.loads((payload / "payload.json").read_text(encoding="utf-8"))
        if pj.get("version") != VERSION:
            raise Refused(f"payload version {pj.get('version')} is not {VERSION}")
        extra = {}
        for fn in EXTRA_CHECKS:
            extra.update(fn(payload))
        lgpl = sorted(stage.glob("r3hd-lgpl-source-*.zip"))
        if len(lgpl) != 1:
            raise Refused(f"expected one LGPL source archive in {stage}, found {len(lgpl)}")
        flags = out / "work" / "flags"
        run([sys.executable, "tools/m48p_flags.py", flags], logs / "flags.log")
        dest = out / "test" / a.test_variant if a.test_variant else out / "dist"
        if dest.exists():
            if not a.test_variant:
                raise Refused(f"{dest} exists: a candidate is never replaced; give a new OUT")
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        defines = [f"/DPayloadDir={payload}", f"/DOutputDir={dest}", f"/DBundledMod={MOD}", f"/DFlagDir={flags}"]
        if a.dpi_proxy:
            defines.append(f"/DDpiProxyFont={a.dpi_proxy}")
        if a.fast:
            defines.append("/DFastCompression")
        run([ISCC, "/Q", *defines, ISS], logs / f"iscc_{a.test_variant or 'dist'}.log")
        setup = dest / SETUP_NAME
        if not setup.is_file():
            raise Refused(f"ISCC wrote no {setup}")
        if a.test_variant:
            print(f"{TAG} TEST {a.test_variant} {setup} {sha(setup)}")
            return 0
        shutil.copy2(lgpl[0], dest / lgpl[0].name)
        head = git("rev-parse", "HEAD")
        dirty = bool(git("status", "--porcelain"))
        manifest = {
            "schema": 1,
            "product": "Rayman 3 HD Recompiled",
            "version": VERSION,
            "classification": CLASSIFICATION,
            "built_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_head": head, "git_worktree_dirty": dirty,
            "setup": {"file": setup.name, "bytes": setup.stat().st_size, "sha256": sha(setup)},
            "lgpl_source": {"file": lgpl[0].name, "bytes": lgpl[0].stat().st_size, "sha256": sha(lgpl[0])},
            "payload": {"id": pj.get("payload_id"), "version": pj.get("version"), "files": len(pj.get("files", []))},
            "runtime_binaries": staged,
            "launcher": {"sha256": sha(payload / "app" / "r3hd_launcher.exe")},
            "turkish_mod": {"file": MOD.name, "id": MOD_ID, "version": MOD_VERSION, "bytes": MOD.stat().st_size,
                            "sha256": mod_sha, "source": MOD_SOURCE,
                            "policy": "fresh Turkish setup: installed and on; fresh English: not installed, the .zip in "
                                      "extras\\; existing installation: only an installed older copy is updated"},
            "inno_setup": {"iscc_sha256": sha(ISCC), "languages": ["en (Default.isl)", "tr (Languages\\Turkish.isl)"]},
            "dependencies": ["Windows 10/11 x64", "Microsoft Visual C++ Redistributable 2015-2022 (x64)",
                             "a Direct3D 12 GPU", "the player's own Rayman 3 HD Xbox 360 XBLA package (5841123F, no TU)"],
            "notices": sorted(str(p.relative_to(payload)).replace("\\", "/") for p in (payload / "app").rglob("*")
                              if p.is_file() and (p.parent.name == "licenses" or p.name == "THIRD_PARTY_NOTICES.txt")),
            "audit": audit.strip().splitlines()[-1] if audit.strip() else "",
            **extra,
        }
        (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
        sums = "".join(f"{sha(p)} *{p.name}\n" for p in sorted(dest.iterdir()) if p.name != "SHA256SUMS.txt")
        (dest / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
        print(f"{TAG} OK {setup} {manifest['setup']['sha256']} payload={manifest['payload']['id'][:16]} "
              f"head={head[:7]}{' dirty' if dirty else ''}")
        return 0
    except Refused as e:
        print(f"{TAG} REFUSED {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
