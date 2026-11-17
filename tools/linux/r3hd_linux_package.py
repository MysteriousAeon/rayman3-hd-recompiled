#!/usr/bin/env python3
"""Linux portable packaging: historical private builds and reviewed public promotion.

  python3 tools/linux/r3hd_linux_package.py build --bin GAMEBUILD --lib SDKLIB --out OUT.tar.gz --development-id ID
  python3 tools/linux/r3hd_linux_package.py check OUT.tar.gz

One product: the package is the portable home of the Windows ZIP (tools/r3hd_portable_zip.py) with Linux binaries.
  bin/        r3hd, librexruntime.so, librexgpu-xenos.so, libffmpeg.so, libmspack.so (LGPL, replaceable: D-084/B3)
  app/        config/release/payload.json's app files and licences, minus the Windows-only entry points, plus
              app/tools/r3hd_portable.py and app/tools/linux/r3hd_play.py (the play.ps1 counterpart)
  Play.sh / Settings.sh   -> python3 app/tools/r3hd_portable.py play|settings (prepare: the person's own game data,
              intake, settings.json with the installation defaults, installer.json; then the launcher / configure)
  payload.json, portable.json   the engine's payload and the portable manifest, exactly as on Windows
No game data, no generated sources, no user files. Checks: exact member set, sizes and hashes, no game-data hash,
no developer path in a binary, ELF x86-64 for every binary, the R-01 key boundary unchanged (only the runtime
library carries the established retail-key hit). A development package is never publishable. The separate
promote --public-release command accepts only the authenticated Noble tar and matching Linux LGPL source,
changes reviewed notices/metadata only, and audits a fresh release directory. It never compiles or publishes.
Never overwrites an output; never publishes. Technical checks only: NOT a legal clearance.
"""
import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import r3hd_installer as engine  # noqa: E402
import r3hd_release_audit as audit  # noqa: E402

TOP = "Rayman3HDRecompiled-Linux"
MTIME = 315532800  # 1980-01-01, as the Windows ZIP's fixed date
BINARIES = {"bin/r3hd": "bin", "bin/librexgpu-xenos.so": "bin", "bin/librexruntime.so": "lib",
            "bin/libffmpeg.so": "lib", "bin/libmspack.so": "lib"}
EXECUTABLE = {"bin/r3hd", "Play.sh", "Settings.sh"}
WINDOWS_ONLY = {"app/tools/play.ps1", "app/tools/play_savekeeper.ps1", "app/play.cmd", "app/settings.cmd"}
LINUX_APP = {"app/tools/r3hd_portable.py": "tools/r3hd_portable.py",
             "app/tools/linux/r3hd_play.py": "tools/linux/r3hd_play.py",
             "app/tools/linux/r3hd_settings_gui.py": "tools/linux/r3hd_settings_gui.py"}
KEY_BOUNDARY = {"bin/librexruntime.so": {"xe_xex2_retail_key": 1}}  # the same material as bin/rexruntime.dll (R-01)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=1, sort_keys=True) + "\n").encode()


def entry_script(action):
    return ("#!/bin/sh\n# Rayman 3 HD Recompiled (Linux Experimental): " + action + ". Needs python3 (3.10+).\n"
            "HERE=$(CDPATH= cd -- \"$(dirname -- \"$0\")\" && pwd)\nexport PYTHONDONTWRITEBYTECODE=1\n"
            "exec python3 -B \"$HERE/app/tools/r3hd_portable.py\" " + action + " \"$@\"\n").encode()


# Libraries every supported Linux desktop provides; anything else a packaged binary needs must be in bin/.
SYSTEM_LIBS = {"libc.so.6", "libm.so.6", "libstdc++.so.6", "libgcc_s.so.1", "libdl.so.2", "libpthread.so.0",
               "librt.so.1", "ld-linux-x86-64.so.2"}
# E-376: the display-server client libraries of the desktop session. The SDK's rexui (inside librexruntime.so) links
# them: src/ui/CMakeLists.txt pkg_check_modules(x11-xcb) and (wayland-client) for the Vulkan surfaces. They must come from the host, never
# from the package: they speak the host's X11 / Wayland protocol and are shared with the host's Vulkan driver WSI
# (AppImage's excludelist and the Steam Linux Runtime treat them as host libraries for the same reason). Admitted
# only for the binary that holds the windowing code, by exact SONAME; anything else still refuses the package.
DESKTOP_SESSION_LIBS = {"bin/librexruntime.so": {"libX11.so.6", "libX11-xcb.so.1", "libxcb.so.1",
                                                 "libwayland-client.so.0"}}


def unexpected_needed(rel, libs, shipped):
    """The DT_NEEDED entries of one packaged binary that are neither packaged, system nor (for that binary) a
    desktop-session library."""
    return sorted(set(libs or ()) - set(shipped) - SYSTEM_LIBS - DESKTOP_SESSION_LIBS.get(rel, set()))


def needed(path):
    """DT_NEEDED of an ELF through readelf (binutils); None when readelf is absent."""
    try:
        out = subprocess.run(["readelf", "-d", str(path)], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", out)


def symbol_versions(data):
    """The newest GLIBC_ / GLIBCXX_ version names a binary references (the distribution baseline it needs)."""
    def newest(prefix):
        found = {tuple(int(x) for x in m.split(b".")) for m in re.findall(prefix + rb"((?:\d+\.)+\d+)", data)}
        return ".".join(map(str, max(found))) if found else None
    return {"glibc": newest(rb"GLIBC_"), "glibcxx": newest(rb"GLIBCXX_")}


# B7 (E-378): reference baselines (glibc, newest GLIBCXX_ of the distribution's default libstdc++), to show which
# systems a package can start on and which symbols prevent it. Information for the release decision, not a gate.
BASELINES = {"debian-12": ("2.36", "3.4.30"), "ubuntu-22.04": ("2.35", "3.4.30"), "ubuntu-24.04": ("2.39", "3.4.33"),
             "debian-13": ("2.41", "3.4.33"), "fedora-42": ("2.41", "3.4.34"), "ubuntu-26.04": ("2.43", "3.4.35")}


def vtuple(v):
    return tuple(int(x) for x in v.split("."))


def symbol_requirements(path):
    """{"GLIBC_x.y": [symbols], "GLIBCXX_x.y.z": [...]} of the versioned undefined symbols (binutils objdump -T);
    None when objdump is absent."""
    try:
        out = subprocess.run(["objdump", "-T", str(path)], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    req = {}
    for ver, name in re.findall(r"\*UND\*\s+\S+\s+(?:\S+\s+)?\(?(GLIBC(?:XX)?_[\d.]+)\)?\s+(\S+)$", out, re.M):
        req.setdefault(ver, set()).add(name)
    return {k: sorted(v) for k, v in sorted(req.items())}


def floor_from(reqs):
    """The newest GLIBC_ / GLIBCXX_ version any packaged binary's dynamic symbols need."""
    out = {"glibc": None, "glibcxx": None}
    for req in reqs.values():
        for ver in req or {}:
            kind, num = ver.split("_", 1)
            key = "glibc" if kind == "GLIBC" else "glibcxx"
            if out[key] is None or vtuple(num) > vtuple(out[key]):
                out[key] = num
    return out


def baseline_report(reqs):
    """Per reference baseline: the symbols (binary: name@version) newer than it; [] = it can start there."""
    report = {}
    for base, (glibc, glibcxx) in BASELINES.items():
        blocked = []
        for rel, req in reqs.items():
            for ver, names in (req or {}).items():
                kind, num = ver.split("_", 1)
                if vtuple(num) > vtuple(glibc if kind == "GLIBC" else glibcxx):
                    blocked += [f"{rel}: {n}@{ver}" for n in names]
        report[base] = sorted(blocked)
    return report


def elf_ok(data):
    return len(data) > 20 and data[:4] == b"\x7fELF" and data[4] == 2 and data[5] == 1 and \
        int.from_bytes(data[18:20], "little") == 62


def definition_files():
    d = json.loads((ROOT / "config/release/payload.json").read_bytes())
    sdk = ROOT / "external/rexglue-sdk"  # the pinned checkout the licences come from (payload.json "licenses")
    files = {}
    for dest, src in d["app_files"].items():
        if dest not in WINDOWS_ONLY:
            files[dest] = (ROOT / src).read_bytes().replace(b"\r\n", b"\n")
    if d.get("controller_prompts"):
        import r3hd_prompt_bundle
        resources = r3hd_prompt_bundle.collect(ROOT, d["controller_prompts"])
        if set(resources) & set(files):
            raise ValueError("controller prompt destination collision")
        files.update(resources)
    for dest, src in d["licenses"]["files"].items():
        files[dest] = (sdk / src).read_bytes()
    for dest, src in LINUX_APP.items():
        files[dest] = (ROOT / src).read_bytes().replace(b"\r\n", b"\n")
    files["app/README-LINUX.txt"] = (ROOT / "tools/linux/README-LINUX.txt").read_bytes().replace(b"\r\n", b"\n")
    # E-379: the application's neutral icons (r3hd.exe / Settings shortcut artwork, MIT Fluent, drawn by
    # make_r3hd_icon.py) for the desktop entries when no game-derived icon exists. No game artwork is shipped.
    import make_r3hd_icon as icons
    files["app/icons/rayman3hd-recompiled.png"] = icons.png(256, icons.render(256, "game"))
    files["app/icons/rayman3hd-recompiled-settings.png"] = icons.png(256, icons.render(256, "settings"))
    # B3b (E-378): the LGPL notice names the Linux libraries and the Linux corresponding-source archive.
    files["app/licenses/LGPL-SOURCE.txt"] = (ROOT / "tools/linux/LGPL-SOURCE-LINUX.txt").read_bytes() \
        .replace(b"\r\n", b"\n")
    return d, files


LGPL_SOURCE_NAME = re.compile(r"r3hd-lgpl-source-(.+)-linux-x86_64\.zip")


def lgpl_source(path, version):
    """B3b: the Linux corresponding-source archive distributed beside the package (m46_lgpl.py package --platform
    linux, made from the pinned git objects): name, platform, program version and every file hash."""
    import zipfile
    m = LGPL_SOURCE_NAME.fullmatch(path.name)
    if not m or m.group(1) != version:
        raise ValueError(f"{path.name}: expected r3hd-lgpl-source-{version}-linux-x86_64.zip")
    with zipfile.ZipFile(path) as z:
        man = json.loads(z.read("r3hd-lgpl-source/MANIFEST.json"))
        names = {n[len("r3hd-lgpl-source/"):] for n in z.namelist()}
        if man.get("platform") != "linux-x86_64" or man.get("program_version") != version:
            raise ValueError(f"{path.name}: not the Linux archive of version {version}")
        if names != set(man["files"]) | {"MANIFEST.json"}:
            raise ValueError(f"{path.name}: entries differ from its manifest")
        bad = [n for n, h in man["files"].items() if digest(z.read("r3hd-lgpl-source/" + n)) != h]
        if bad:
            raise ValueError(f"{path.name}: hash mismatch {bad[:3]}")
        commits = {k: c["commit"] for k, c in man["components"].items()}
    return {"archive": path.name, "sha256": digest(path.read_bytes()), "files": len(man["files"]), "commits": commits}


def build(bin_dir, lib_dir, out, development_id, lgpl_source_zip=None):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", development_id):
        raise ValueError("Use a short development identifier, not a release version")
    if out.exists() or Path(str(out) + ".partial").exists():
        raise ValueError("Output exists; never overwrite a package")
    # E-378: never package an r3hd older than its host inputs (LX2C: a stale ELF without the LX-6 rex_app.cpp).
    import tempfile
    sys.path.insert(0, str(TOOLS / "linux"))
    import r3hd_linux_build as lb
    with tempfile.TemporaryDirectory() as tmp:
        try:
            stale = lb.host_input_problems(bin_dir.resolve(), Path(tmp) / "stale.log")
        except lb.Fail as e:
            stale = [str(e)]
    if stale:
        raise ValueError("game build is not current with its host inputs: " + "; ".join(stale))
    d, files = definition_files()
    shipped = {r.split("/", 1)[1] for r in BINARIES}
    deps, baseline, reqs = {}, {"glibc": [], "glibcxx": []}, {}
    for rel, where in BINARIES.items():
        source = (bin_dir if where == "bin" else lib_dir) / rel.split("/", 1)[1]
        data = source.read_bytes()
        if not elf_ok(data):
            raise ValueError(f"{rel}: not a Linux x86-64 ELF")
        files[rel] = data
        deps[rel] = needed(source)
        reqs[rel] = symbol_requirements(source)
        missing = unexpected_needed(rel, deps[rel], shipped)
        if missing:
            raise ValueError(f"{rel} needs libraries that are neither packaged nor system libraries: {missing}")
        for k, v in symbol_versions(data).items():
            if v:
                baseline[k].append(v)
    lgpl = lgpl_source(lgpl_source_zip, d["version"]) if lgpl_source_zip else None
    floor = {k: max(v, key=vtuple) if v else None for k, v in baseline.items()}
    if all(r is not None for r in reqs.values()):  # exact: the versions the dynamic symbols need (objdump)
        floor = floor_from(reqs)
    releases = json.loads((ROOT / "config/intake/known_releases.json").read_bytes())
    rel0 = releases["releases"][0]
    entries = {r: {"size": len(b), "sha256": digest(b), "role": "native" if r in BINARIES else "app"}
               for r, b in sorted(files.items())}
    pid = digest("".join(f"{r}\t{e['size']}\t{e['sha256']}\n" for r, e in entries.items()).encode())
    payload = {"schema": engine.SCHEMA, "product": engine.PRODUCT, "version": d["version"] + "-linux-experimental",
               "publishable": False, "payload_id": pid, "platform": "linux-x86_64",
               "requires": {"release": rel0["id"], "executable_sha256": rel0["executable"]["sha256"],
                            "manifest_sha256": rel0["content"]["manifest_sha256"], "linux": "x86-64, glibc, Vulkan",
                            "glibc": floor["glibc"], "glibcxx": floor["glibcxx"],
                            "python": "python3 3.10+ (system)"},
               "files": entries,
               "note": "PRIVATE Linux Experimental payload of a prototype (translated game code, key-bearing runtime). "
                       "No game data: preparation reads it from the owner's package."}
    files["payload.json"] = encoded(payload)
    files["Play.sh"] = entry_script("play")
    files["Settings.sh"] = entry_script("settings")
    files["portable.json"] = encoded({
        "schema": 1, "data_model": "beside-application", "publishable": False, "development_id": development_id,
        "application_version": payload["version"], "payload_id": pid, "platform": "linux-x86_64",
        "prerequisites": {"linux": "x86-64 with Vulkan 1.2+ drivers", "python": "python3 3.10+"},
        "lgpl": {"replaceable": sorted(r for r in BINARIES if "ffmpeg" in r or "mspack" in r),
                 "corresponding_source": lgpl or "pending (B3b): required before any public release"},
        "files": {r: {"size": len(b), "sha256": digest(b)} for r, b in sorted(files.items())}})
    partial = Path(str(out) + ".partial")
    with tarfile.open(partial, "w:gz", format=tarfile.PAX_FORMAT) as t:
        for rel, data in sorted(files.items()):
            info = tarfile.TarInfo(TOP + "/" + rel)
            info.size, info.mtime, info.uid, info.gid, info.uname, info.gname = len(data), MTIME, 0, 0, "", ""
            info.mode = 0o755 if rel in EXECUTABLE else 0o644
            t.addfile(info, io.BytesIO(data))
    report = check(partial)
    partial.rename(out)
    report["archive"] = out.name
    report["needed"] = deps
    report["host_desktop_libraries"] = sorted({lib for rel, libs in deps.items() for lib in (libs or ())
                                               if lib in DESKTOP_SESSION_LIBS.get(rel, set())})
    report["requires"] = floor
    report["symbol_requirements"] = {rel: {v: n for v, n in (r or {}).items()
                                           if vtuple(v.split("_", 1)[1]) > vtuple("2.35" if v.startswith("GLIBC_") else "3.4.30")}
                                     for rel, r in reqs.items()}
    report["baselines"] = baseline_report(reqs)
    Path(str(out) + ".sha256").write_text(f"{report['sha256']}  {out.name}\n", encoding="utf-8")
    Path(str(out) + ".manifest.json").write_bytes(encoded(report))
    return report


def check(path):
    files = {}
    with tarfile.open(path, "r:gz") as t:
        for m in t.getmembers():
            name = m.name
            if not m.isfile() or not name.startswith(TOP + "/") or ".." in name.split("/") or "\\" in name:
                raise ValueError(f"Unsafe or unexpected archive entry: {name}")
            rel = name[len(TOP) + 1:]
            if rel in files:
                raise ValueError(f"Duplicate entry: {rel}")
            if (m.mode & 0o111 != 0) != (rel in EXECUTABLE):
                raise ValueError(f"Unexpected file mode: {rel}")
            files[rel] = t.extractfile(m).read()
    manifest = json.loads(files["portable.json"])
    if set(files) != set(manifest["files"]) | {"portable.json"}:
        raise ValueError("Archive members differ from portable.json")
    for rel, row in manifest["files"].items():
        if len(files[rel]) != row["size"] or digest(files[rel]) != row["sha256"]:
            raise ValueError(f"Archive checksum mismatch: {rel}")
    payload = json.loads(files["payload.json"])
    _, expected = definition_files()
    if set(payload["files"]) != set(expected) | set(BINARIES):
        raise ValueError("Payload differs from the release definition (Linux)")
    if set(manifest["files"]) != set(payload["files"]) | {"payload.json", "Play.sh", "Settings.sh"}:
        raise ValueError("Unexpected package contents (including possible user data)")
    if manifest.get("publishable") or payload.get("publishable"):
        raise ValueError("A Linux package is not publishable before B3b and a separate release decision")
    game = audit.GameHashes([audit.DEFAULT_MANIFEST], audit.DEFAULT_RELEASES)
    for rel in payload["files"]:
        data = files[rel]
        if digest(data) in game.hashes:
            raise ValueError(f"Game data in archive: {rel}")
        if rel in BINARIES:
            if not elf_ok(data):
                raise ValueError(f"{rel}: not a Linux x86-64 ELF")
            if audit.binary_dev_paths(data):
                raise ValueError(f"Developer path in archived binary: {rel}")
    keys = key_hits({rel: files[rel] for rel in BINARIES})
    if keys != KEY_BOUNDARY:
        raise ValueError(f"R-01 key boundary differs from the established one: {keys}")
    return {"result": "PASS", "files": len(files), "sha256": engine.sha256(Path(path)),
            "bytes": Path(path).stat().st_size, "development_id": manifest["development_id"],
            "application_version": manifest["application_version"], "payload_id": payload["payload_id"],
            "publishable": False, "lgpl_corresponding_source": manifest["lgpl"]["corresponding_source"]}


def key_hits(binaries):
    """tools/m50_r01_audit.py keys over the binaries (never prints key material); {file: hits} of the non-empty."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        for rel, data in binaries.items():
            p = Path(tmp) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        r = subprocess.run([sys.executable, str(TOOLS / "m50_r01_audit.py"), "keys", tmp, "--base", tmp],
                           capture_output=True, check=True)
    k = json.loads(r.stdout)
    if k["unresolved"]:
        raise ValueError("R-01 key audit unresolved")
    return {row["file"].replace("\\", "/"): row["hits"] for row in k["files"] if row["hits"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--bin", type=Path, required=True, help="the game build directory (r3hd, librexgpu-xenos.so)")
    b.add_argument("--lib", type=Path, required=True, help="the SDK install lib directory (librexruntime.so, ...)")
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--development-id", required=True)
    b.add_argument("--lgpl-source", type=Path,
                   help="B3b: r3hd-lgpl-source-<version>-linux-x86_64.zip, distributed beside the package (recorded)")
    c = sub.add_parser("check")
    c.add_argument("archive", type=Path)
    c.add_argument("--public-release", action="store_true", help="Audit the reviewed public Linux distribution")
    c.add_argument("--lgpl-source", type=Path, help="Required matching source archive in public mode")
    r = sub.add_parser("promote", help="Packaging only: promote the exact Noble archive, never rebuild binaries")
    r.add_argument("archive", type=Path)
    r.add_argument("--lgpl-source", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True, help="Fresh release directory; never overwritten")
    r.add_argument("--public-release", action="store_true", required=True)
    v = sub.add_parser("audit-release", help="Verify all five final release assets offline")
    v.add_argument("directory", type=Path)
    a = ap.parse_args()
    try:
        if a.cmd == 'build':
            report = build(a.bin, a.lib, a.out, a.development_id, a.lgpl_source)
        elif a.cmd == 'check' and not a.public_release:
            if a.lgpl_source:
                raise ValueError('--lgpl-source for check requires --public-release')
            report = check(a.archive)
        else:
            import r3hd_linux_release as release
            if a.cmd == 'check':
                if not a.lgpl_source:
                    raise ValueError('Public audit requires --lgpl-source')
                report = release.check_public(a.archive, a.lgpl_source)
            elif a.cmd == 'promote':
                report = release.promote(a.archive, a.lgpl_source, a.out)
            else:
                report = release.audit_directory(a.directory)
        # stdout is a JSON document: build/static acceptance redirects it to *.json.
        # Keep the human marker on stderr so it cannot corrupt that contract.
        print(json.dumps(report, sort_keys=True))
        print("R3HD_LINUX_PACKAGE " + report["result"], file=sys.stderr)
        return 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, tarfile.TarError,
            subprocess.CalledProcessError, engine.Refusal) as e:
        print(f"R3HD_LINUX_PACKAGE REFUSED {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
