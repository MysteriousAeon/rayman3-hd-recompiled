"""LGPL components of the Windows runtime: checks, corresponding-source archive and replacement test (M46, D-084).

FFmpeg (libavutil + libavcodec) and libmspack's lzxd.c are built as their own DLLs, ffmpeg.dll and mspack.dll, which
rexruntime.dll imports by name (tools/m46_runtime_patch.py). The record of what is used is
config/release/lgpl_components.json; the human-readable notice is tools/installer/LGPL-SOURCE.txt.

  check [--build-tree]   pins, configuration, licence headers of the compiled FFmpeg sources, notices and payload
                         definition; with --build-tree also the built binaries: imports and exports, no LGPL code in
                         any other shipped binary, the static archives absent from rexruntime's link, staged copies
                         equal. Read-only. Final line M46_CHECK PASS|FAIL.
  package [--out DIR]    write the corresponding-source archive r3hd-lgpl-source-<version>.zip (deterministic: same
                         pins, same bytes) from the pinned git objects and the patched SDK build sections, then
                         check it. Final line M46_PACKAGE OK <path> <sha256>.
  rebuild ZIP DIR [--modify]
                         unpack the archive into DIR (must not exist) and build ffmpeg.dll and mspack.dll with the
                         archive's own CMake file, as README.txt tells a recipient to. --modify first changes the
                         sources: FFmpeg logs one warning from the XMA decoder's init, lzxd_init appends a line to
                         the file named by M46_MSPACK_MARKER. Final line M46_REBUILD OK DIR.
  replace-test [--entry NAME]
                         package, rebuild unmodified and modified, put each pair of DLLs into its own copy of the
                         build (private/work/m46/replace), and run the hidden M12 smoke on each copy through
                         R3HD_EXE: both must pass; only the modified FFmpeg may log its marker. The title's XEX
                         is not LZX-compressed, so mspack.dll is exercised by m46_lzx_probe.exe (the runtime's own
                         lzx_decompress) on a makecab LZX cabinet, against the shipped, plain and modified DLLs:
                         exact output each time, the lzxd_init marker only from the modified one. Final line
                         M46_REPLACE PASS|FAIL.

The archive and the test copies stay under private/work/m46 (never committed). Game runs are hidden, muted and use
the test input source (tools/run_milestone6.ps1). Technical checks only: NOT a legal clearance.
"""
import argparse
import fnmatch
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "external" / "rexglue-sdk"
RECORD = ROOT / "config" / "release" / "lgpl_components.json"
SDK_OUT = SDK / "out" / "win-amd64" / "Release"
SDK_BIN = SDK / "out" / "install" / "win-amd64" / "bin"
APP_BUILD = ROOT / "private" / "work" / "rex" / "out" / "build" / "win-amd64-release"
WORK = ROOT / "private" / "work" / "m46"
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
PREFIX = "r3hd-lgpl-source/"
VCVARS = os.environ.get("R3HD_VCVARS", r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat")
LLVM_BIN = os.environ.get("R3HD_LLVM_BIN", r"C:\Program Files\LLVM\bin")
FFMPEG_MARK = "M46 replacement FFmpeg build in use"

failures = []


def check(label, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + label + (f" ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(label)
    return ok


def record():
    return json.loads(RECORD.read_text(encoding="utf-8"))


def git(repo, *args, data=None):
    return subprocess.run(["git", "-C", str(repo), *args], input=data, capture_output=True, check=True).stdout


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- PE import / export tables (no external tool)

def pe_tables(path):
    d = Path(path).read_bytes()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    if d[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"{path}: not a PE file")
    nsec, = struct.unpack_from("<H", d, pe + 6)
    optsz, = struct.unpack_from("<H", d, pe + 20)
    opt = pe + 24
    if struct.unpack_from("<H", d, opt)[0] != 0x20B:
        raise ValueError(f"{path}: not PE32+")
    exp_rva, _ = struct.unpack_from("<II", d, opt + 112)
    imp_rva, _ = struct.unpack_from("<II", d, opt + 120)
    secs = [struct.unpack_from("<IIII", d, opt + optsz + i * 40 + 8) for i in range(nsec)]

    def off(rva):
        for vsize, va, rsize, raw in secs:
            if va <= rva < va + max(vsize, rsize):
                return raw + rva - va
        raise ValueError(f"{path}: RVA {rva:#x} outside the sections")

    def cstr(rva):
        o = off(rva)
        return d[o:d.index(b"\0", o)].decode("ascii")

    imports = {}
    o = off(imp_rva) if imp_rva else None
    while o is not None:
        oft, _, _, name, ft = struct.unpack_from("<IIIII", d, o)
        if not (oft or name):
            break
        names, t = [], off(oft or ft)
        while True:
            e, = struct.unpack_from("<Q", d, t)
            if not e:
                break
            names.append(f"#{e & 0xFFFF}" if e >> 63 else cstr((e & 0x7FFFFFFF) + 2))
            t += 8
        imports[cstr(name)] = names
        o += 20
    exports = []
    if exp_rva:
        o = off(exp_rva)
        n, = struct.unpack_from("<I", d, o + 24)
        names_rva, = struct.unpack_from("<I", d, o + 32)
        no = off(names_rva)
        exports = [cstr(struct.unpack_from("<I", d, no + 4 * i)[0]) for i in range(n)]
    return imports, exports


def system_import(name, allowed):
    return any(fnmatch.fnmatch(name.lower(), a.lower()) for a in allowed)


# ---------------------------------------------------------------- check

def ffmpeg_sources():
    """The FFmpeg files the SDK compiles (its own lists in thirdparty/CMakeLists.txt, x86-64 parts)."""
    text = (SDK / "thirdparty" / "CMakeLists.txt").read_text(encoding="utf-8")
    body = text[text.index("# FFmpeg - Audio/video codec library"):]
    body = re.sub(r"if\(IS_ARM64\).*?endif\(\)", "", body, flags=re.S)
    return sorted(set(re.findall(r"\$\{FFMPEG_DIR\}/(\S+\.c)\b", body)))


def check_sources(rec):
    ff, ms = rec["components"]["ffmpeg"], rec["components"]["libmspack"]
    fdir, mdir = SDK / ff["sdk_path"], SDK / ms["sdk_path"]
    check("FFmpeg submodule at the pinned commit", git(fdir, "rev-parse", "HEAD").decode().strip() == ff["commit"])
    check("FFmpeg submodule has no local change", git(fdir, "status", "--porcelain").strip() == b"")
    check("libmspack submodule at the pinned commit", git(mdir, "rev-parse", "HEAD").decode().strip() == ms["commit"])
    changed = [l[3:] for l in git(mdir, "status", "--porcelain").decode().splitlines()]
    check("libmspack: only the E-06 symlink copies differ from git",
          all(c.startswith("cabextract/mspack/") for c in changed), str(changed[:3]))
    for rel in ms["files"]:
        blob = git(mdir, "show", f"HEAD:{rel}")
        built = (mdir / "cabextract/mspack" / Path(rel).name).read_bytes().replace(b"\r\n", b"\n")
        check(f"libmspack {Path(rel).name} built by the SDK equals {rel} at the pin", built == blob)
    hdr = git(fdir, "show", f"HEAD:{ff['config_header']}").decode()  # the pin itself is checked above
    defs = dict(re.findall(r"^#define (\w+) (.+?)\s*$", hdr, re.M))
    for k, v in ff["config_required"].items():
        check(f"FFmpeg {ff['config_header']}: {k} {v}", defs.get(k) == v, defs.get(k))
    enabled = sorted(k for k, v in defs.items() if v == "1" and re.fullmatch(
        r"CONFIG_\w+_(DECODER|ENCODER|PARSER|BSF|DEMUXER|MUXER|PROTOCOL|HWACCEL|FILTER|INDEV|OUTDEV)", k))
    check("FFmpeg enabled components are exactly the recorded ones", enabled == sorted(ff["config_enabled"]), str(enabled))
    check("FFmpeg configure line has no --enable-gpl / nonfree / version3",
          not re.search(r"--enable-(gpl|nonfree|version3)", defs.get("FFMPEG_CONFIGURATION", "")))
    srcs = ffmpeg_sources()
    gpl, plain = [], []
    for s in srcs:
        head = (fdir / s).read_text(encoding="utf-8", errors="replace")[:4000]
        if "Lesser General Public" in head or "LGPL" in head:
            continue
        (gpl if "General Public License" in head else plain).append(s)
    check(f"compiled FFmpeg sources ({len(srcs)}): none under a GPL notice", not gpl and len(srcs) > 150, str(gpl))
    check("compiled FFmpeg sources without an LGPL notice are the recorded permissive ones",
          sorted(plain) == sorted(ff["compiled_sources_without_lgpl_header"]), str(plain))
    cm = (SDK / "thirdparty" / "CMakeLists.txt").read_text(encoding="utf-8")
    check("SDK patched: mspack and ffmpeg are SHARED (M46)",
          "add_library(mspack SHARED" in cm and 'add_library(ffmpeg SHARED' in cm)
    check("rexaudio links ffmpeg, not the static archives",
          "PRIVATE ffmpeg" in (SDK / "src/audio/CMakeLists.txt").read_text(encoding="utf-8"))


def check_notices(rec):
    ff, ms = rec["components"]["ffmpeg"], rec["components"]["libmspack"]
    notice = (ROOT / "tools/installer/LGPL-SOURCE.txt").read_text(encoding="utf-8")
    third = (ROOT / "tools/installer/THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    check("LGPL-SOURCE.txt names both pinned commits and repositories",
          all(x in notice for x in (ff["commit"], ms["commit"], ff["repository"], ms["repository"])))
    check("LGPL-SOURCE.txt lists every function rexruntime imports",
          all(n in notice for n in ff["imported_by_rexruntime"] + ms["imported_by_rexruntime"]))
    check("THIRD_PARTY_NOTICES: FFmpeg / libmspack under their own DLLs",
          "bin\\ffmpeg.dll" in third and "bin\\mspack.dll" in third and ff["commit"][:7] in third and ms["commit"][:7] in third)
    defn = json.loads((ROOT / "config/release/payload.json").read_text(encoding="utf-8"))
    lic = defn["licenses"]["files"]
    check("payload ships both DLLs", {ff["dll"], ms["dll"]} <= set(defn["binaries"]["files"]))
    check("payload stages the LGPL texts and the source notice",
          lic.get("app/licenses/FFmpeg-COPYING.LGPLv2.1.txt") == "thirdparty/FFmpeg/COPYING.LGPLv2.1"
          and lic.get("app/licenses/libmspack-COPYING.LIB.txt") == "thirdparty/libmspack/libmspack/COPYING.LIB"
          and defn["app_files"].get("app/licenses/LGPL-SOURCE.txt") == "tools/installer/LGPL-SOURCE.txt")
    check("staging writes the source archive beside the payload (payload.json lgpl_source)", bool(defn.get("lgpl_source")))
    allow = json.loads((ROOT / "config/release/payload_allowlist.json").read_text(encoding="utf-8"))["binaries"]
    check("payload allowlist has both DLLs as native", allow.get("bin/ffmpeg.dll") == allow.get("bin/mspack.dll") == "native")
    sys.path.insert(0, str(ROOT / "tools"))
    import r3hd_installer, r3hd_paths  # noqa: E402
    check("installer and developer install copy both DLLs",
          {"ffmpeg.dll", "mspack.dll"} <= set(r3hd_installer.RUNTIME_FILES) & set(r3hd_paths.RUNTIME_FILES))
    check("play.ps1 preflight requires both DLLs",
          "'ffmpeg.dll', 'mspack.dll'" in (ROOT / "tools/play.ps1").read_text(encoding="utf-8"))


def check_build(rec):
    ff, ms = rec["components"]["ffmpeg"], rec["components"]["libmspack"]
    allowed = rec["system_imports_allowed"]
    markers = [m.encode() for c in (ff, ms) for m in c["markers"]]
    imp, _ = pe_tables(SDK_OUT / "rexruntime.dll")
    check("rexruntime.dll imports exactly the recorded FFmpeg functions from ffmpeg.dll",
          sorted(imp.get("ffmpeg.dll", [])) == sorted(ff["imported_by_rexruntime"]), str(imp.get("ffmpeg.dll")))
    check("rexruntime.dll imports exactly lzxd_init / decompress / free from mspack.dll",
          sorted(imp.get("mspack.dll", [])) == sorted(ms["imported_by_rexruntime"]), str(imp.get("mspack.dll")))
    fimp, fexp = pe_tables(SDK_OUT / "ffmpeg.dll")
    check("ffmpeg.dll exports only av* names and every name rexruntime imports",
          all(e.startswith("av") for e in fexp) and set(ff["imported_by_rexruntime"]) <= set(fexp), f"{len(fexp)} exports")
    check("ffmpeg.dll imports only Windows / C runtime DLLs",
          all(system_import(n, allowed) for n in fimp), str(sorted(fimp)))
    mimp, mexp = pe_tables(SDK_OUT / "mspack.dll")
    check("mspack.dll exports exactly lzxd_*", sorted(mexp) == sorted(ms["exports"]), str(mexp))
    check("mspack.dll imports only Windows / C runtime DLLs", all(system_import(n, allowed) for n in mimp), str(sorted(mimp)))
    for name, comp in (("ffmpeg.dll", ff), ("mspack.dll", ms)):
        data = (SDK_OUT / name).read_bytes()
        check(f"{name} carries its library's markers", all(m.encode() in data for m in comp["markers"]))
    for name in rec["shipped_without_lgpl_code"]:
        for where in (SDK_OUT, APP_BUILD):
            p = where / name
            if p.is_file():
                data = p.read_bytes()
                hit = [m.decode() for m in markers if m in data]
                check(f"no FFmpeg / libmspack code marker in {where.name}/{name}", not hit, str(hit))
    for name in ("ffmpeg.dll", "mspack.dll"):
        ref = sha256((SDK_OUT / name).read_bytes())
        for where in (SDK_BIN, APP_BUILD):
            p = where / name
            check(f"{name} staged in {where.relative_to(ROOT)} equals the SDK build",
                  p.is_file() and sha256(p.read_bytes()) == ref)
    ninja = (SDK / "out/build/win-amd64/CMakeFiles/impl-Release.ninja").read_text(encoding="utf-8")
    i = ninja.index("Release/rexruntime.lib:")
    blk = ninja[ninja.rfind("\nbuild ", 0, i):ninja.find("\n\n", i)]
    libs = {Path(x).name for x in re.findall(r"\S+\.lib", blk)}
    check("rexruntime link line has no static FFmpeg archive", not {"libavcodec.lib", "libavutil.lib"} & libs, str(libs))
    check("rexruntime links ffmpeg.lib and mspack.lib, both import libraries",
          {"ffmpeg.lib", "mspack.lib"} <= libs and b"__imp_avcodec_open2" in (SDK_OUT / "ffmpeg.lib").read_bytes()
          and b"__imp_lzxd_init" in (SDK_OUT / "mspack.lib").read_bytes())


def cmd_check(a):
    rec = record()
    check_sources(rec)
    check_notices(rec)
    if a.build_tree:
        check_build(rec)
    print(f"M46_CHECK {'PASS' if not failures else 'FAIL'} ({len(failures)} failure(s))")
    return 0 if not failures else 1


# ---------------------------------------------------------------- package

def git_tree(repo, commit, sub=None):
    """{path: bytes} of every blob of COMMIT (under SUB), straight from the git objects (no export-ignore, no
    line-ending conversion)."""
    args = ["ls-tree", "-r", "-z", "--full-tree", commit] + ([sub] if sub else [])
    entries = [e for e in git(repo, *args).split(b"\0") if e]
    out, shas = {}, []
    for e in entries:
        meta, path = e.split(b"\t", 1)
        mode, kind, sha = meta.split()
        if kind != b"blob":
            raise RuntimeError(f"{repo}: {kind.decode()} entry {path.decode()} (submodule?) not supported")
        if mode == b"120000":
            raise RuntimeError(f"{repo}: symlink {path.decode()} in the packaged tree")
        shas.append((path.decode(), sha.decode()))
    p = subprocess.Popen(["git", "-C", str(repo), "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for path, sha in shas:
        p.stdin.write(sha.encode() + b"\n")
        p.stdin.flush()
        header = p.stdout.readline().split()
        size = int(header[2])
        out[path] = p.stdout.read(size)
        p.stdout.read(1)
    p.stdin.close()
    p.wait()
    return out


def standalone_cmake():
    text = (SDK / "thirdparty" / "CMakeLists.txt").read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    ms = text.index("# libmspack - LZX decompression")
    me = text.index("# o1heap", ms)
    mspack = text[ms:me].rstrip() + "\n"
    old_dir = '"${CMAKE_CURRENT_SOURCE_DIR}/libmspack/cabextract/mspack"'
    assert mspack.count(old_dir) == 1
    mspack = mspack.replace(old_dir, '"${CMAKE_CURRENT_SOURCE_DIR}/libmspack/libmspack/mspack"')
    fs = text.rfind("#=====", 0, text.index("# FFmpeg - Audio/video codec library"))
    end = 'set_target_properties(ffmpeg ffmpeg_def PROPERTIES FOLDER "FFmpeg")\n'
    fe = text.index(end) + len(end)
    ffmpeg = text[fs:fe]
    head = (
        "# Rebuilds bin\\ffmpeg.dll and bin\\mspack.dll of Rayman 3 HD Recompiled from this archive (README.txt).\n"
        "# The two sections below are copied from the ReXGlue SDK's thirdparty/CMakeLists.txt as the program builds\n"
        "# them (BSD-3-Clause, ReXGlue-SDK-LICENSE.txt); only the libmspack directory is changed, to the library's own.\n"
        "cmake_minimum_required(VERSION 3.20)\n"
        "project(r3hd_lgpl_components C)\n"
        "include(GNUInstallDirs)\n"
        "if(NOT WIN32 OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)\n"
        "    message(FATAL_ERROR \"This archive builds the Windows x64 DLLs only\")\n"
        "endif()\n"
        "set(IS_X86_64 TRUE)\n"
        "set(IS_ARM64 FALSE)\n"
        "set(CMAKE_RUNTIME_OUTPUT_DIRECTORY \"${CMAKE_BINARY_DIR}\")\n"
        "set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY \"${CMAKE_BINARY_DIR}\")\n"
        "# The SDK's own options for all of its C code.\n"
        "add_compile_options(-fno-strict-aliasing -ffp-model=strict)\n\n"
    )
    return head + "#" + "=" * 77 + "\n" + mspack + "\n" + ffmpeg


def package_files():
    rec = record()
    ff, ms = rec["components"]["ffmpeg"], rec["components"]["libmspack"]
    files = {}
    for path, data in git_tree(SDK / ff["sdk_path"], ff["commit"]).items():
        files["FFmpeg/" + path] = data
    for path, data in git_tree(SDK / ms["sdk_path"], ms["commit"], "libmspack").items():
        files["libmspack/" + path] = data
    overlay = SDK / "thirdparty" / "ffmpeg-overlay"
    for name in ("codec_list.c", "parser_list.c", "bsf_list.c", "m46_ffmpeg_def.cmake", "m46_ffmpeg_dll.c"):
        files["ffmpeg-overlay/" + name] = (overlay / name).read_bytes().replace(b"\r\n", b"\n")
    files["CMakeLists.txt"] = standalone_cmake().encode("utf-8")
    files["ReXGlue-SDK-LICENSE.txt"] = (SDK / "LICENSE").read_bytes().replace(b"\r\n", b"\n")
    files["README.txt"] = (ROOT / "tools/installer/LGPL-SOURCE.txt").read_bytes().replace(b"\r\n", b"\n")
    # M50 (D-089): the project's own build files carry an explicit licence (LGPL-2.1-or-later).
    files["LGPL-BUILD-FILES-LICENSE.txt"] = (ROOT / "tools/installer/LGPL-BUILD-FILES-LICENSE.txt").read_bytes() \
        .replace(b"\r\n", b"\n")
    version = json.loads((ROOT / "config/release/payload.json").read_text(encoding="utf-8"))["version"]
    manifest = {
        "schema": 1, "name": rec["package"]["name"], "program_version": version,
        "components": {k: {x: c[x] for x in ("dll", "repository", "commit", "spdx")} for k, c in rec["components"].items()},
        "sdk": {"repository": "rexglue/rexglue-sdk", "commit": git(SDK, "rev-parse", "HEAD").decode().strip(),
                "build_sections": "thirdparty/CMakeLists.txt after tools/m46_runtime_patch.py"},
        "files": {p: sha256(d) for p, d in sorted(files.items())},
    }
    files["MANIFEST.json"] = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode()
    return files, version


def write_zip(files, path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(PREFIX + name, ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0o644 << 16
            zf.writestr(info, files[name], compresslevel=9)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())
    return sha256(buf.getvalue())


def check_package(path):
    rec = record()
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        check("archive: every entry under r3hd-lgpl-source/", all(n.startswith(PREFIX) for n in names))
        man = json.loads(zf.read(PREFIX + "MANIFEST.json"))
        listed = set(man["files"]) | {"MANIFEST.json"}
        check("archive: entries equal the manifest", {n[len(PREFIX):] for n in names} == listed)
        bad = [p for p, h in man["files"].items() if sha256(zf.read(PREFIX + p)) != h]
        check("archive: every file matches its manifest hash", not bad, str(bad[:3]))
        for k, c in rec["components"].items():
            check(f"archive: {k} pinned to the recorded commit", man["components"][k]["commit"] == c["commit"])
        ff, ms = rec["components"]["ffmpeg"], rec["components"]["libmspack"]
        n_ff = len([e for e in git(SDK / ff["sdk_path"], "ls-tree", "-r", "-z", ff["commit"]).split(b"\0") if e])
        n_ms = len([e for e in git(SDK / ms["sdk_path"], "ls-tree", "-r", "-z", ms["commit"], "libmspack").split(b"\0") if e])
        check(f"archive: complete FFmpeg tree ({n_ff} files)", sum(p.startswith("FFmpeg/") for p in man["files"]) == n_ff)
        check(f"archive: complete libmspack library directory ({n_ms} files)",
              sum(p.startswith("libmspack/") for p in man["files"]) == n_ms)
        need = ["FFmpeg/COPYING.LGPLv2.1", "FFmpeg/LICENSE.md", "libmspack/libmspack/COPYING.LIB",
                "libmspack/libmspack/mspack/lzxd.c", "ffmpeg-overlay/m46_ffmpeg_def.cmake", "CMakeLists.txt",
                "README.txt", "ReXGlue-SDK-LICENSE.txt", "LGPL-BUILD-FILES-LICENSE.txt"]
        check("archive: licence texts, build files and README present", all(p in man["files"] for p in need))
        game = [p for p in man["files"] if re.search(r"\.(xex|bhf|btf|bik|lvl|ptr|sav)$|(^|/)(private|saves?|generated)/", p, re.I)]
        check("archive: no game data, save or private path", not game, str(game[:3]))


def cmd_package(a):
    files, version = package_files()
    out = Path(a.out) if a.out else ROOT / record()["package"]["dir"]
    path = out / f"{record()['package']['name']}-{version}.zip"
    digest = write_zip(files, path)
    (path.with_suffix(".zip.sha256")).write_text(f"{digest}  {path.name}\n", encoding="ascii")
    check_package(path)
    print(f"files {len(files)}, bytes {path.stat().st_size}")
    if failures:
        print("M46_PACKAGE FAIL")
        return 1
    print(f"M46_PACKAGE OK {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path} {digest}")
    return 0


# ---------------------------------------------------------------- rebuild

def edit(path, old, new):
    data = path.read_bytes()
    nl = b"\r\n" if b"\r\n" in data else b"\n"
    text = data.replace(b"\r\n", b"\n")
    assert text.count(old.encode()) == 1, (path, old)
    path.write_bytes(text.replace(old.encode(), new.encode()).replace(b"\n", nl))


def rebuild(zip_path, work, modify=False, log=None):
    work = Path(work)
    if work.exists():
        raise SystemExit(f"{work} exists; give a new directory")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(work)
    src = work / PREFIX.rstrip("/")
    if modify:
        edit(src / "FFmpeg/libavcodec/wmaprodec.c",
             "static av_cold int xmaframes_decode_init(AVCodecContext* avctx)\n{\n",
             "static av_cold int xmaframes_decode_init(AVCodecContext* avctx)\n{\n"
             "    { static int m46_once; if (!m46_once) { m46_once = 1;\n"
             f"      av_log(avctx, AV_LOG_WARNING, \"{FFMPEG_MARK}\\n\"); }} }}\n")
        lz = src / "libmspack/libmspack/mspack/lzxd.c"
        edit(lz, "#include <system.h>\n", "#include <stdio.h>\n#include <stdlib.h>\n#include <system.h>\n")
        edit(lz, "  if (!system) return NULL;\n",
             "  if (!system) return NULL;\n"
             "  { const char *m46 = getenv(\"M46_MSPACK_MARKER\");\n"
             "    if (m46) { FILE *f = fopen(m46, \"ab\"); if (f) { fputs(\"lzxd_init\\n\", f); fclose(f); } } }\n")
    bat = work / "rebuild.bat"
    bat.write_text("\r\n".join([
        "@echo off",
        f'call "{VCVARS}" >nul 2>&1',
        f'set "PATH={LLVM_BIN};%PATH%"',
        f'cd /d "{src}"',
        'cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang "-DCMAKE_C_FLAGS=-march=x86-64-v2" || exit /b 1',
        "cmake --build build --target ffmpeg mspack || exit /b 1",
        ""]), encoding="ascii")
    with open(log or work / "rebuild.log", "w", encoding="utf-8") as out:
        rc = subprocess.run(["cmd", "/c", str(bat)], stdout=out, stderr=subprocess.STDOUT).returncode
    dlls = {n: src / "build" / n for n in ("ffmpeg.dll", "mspack.dll")}
    if rc or not all(p.is_file() for p in dlls.values()):
        raise SystemExit(f"rebuild failed (exit {rc}); see {log or work / 'rebuild.log'}")
    return dlls


def cmd_rebuild(a):
    dlls = rebuild(a.zip, a.dir, a.modify)
    for n, p in dlls.items():
        print(n, p.stat().st_size, sha256(p.read_bytes())[:16])
    print(f"M46_REBUILD OK {a.dir}")
    return 0


# ---------------------------------------------------------------- replacement test

def smoke(entry, run, exe_dir, marker_file):
    env = dict(os.environ, R3HD_EXE=str(exe_dir / "r3hd.exe"), M46_MSPACK_MARKER=str(marker_file))
    log = WORK / "replace" / f"{run}.smoke.log"
    with open(log, "w", encoding="utf-8") as out:
        rc = subprocess.run([sys.executable, str(ROOT / "tools/m12_save_entry.py"), "smoke", entry, run],
                            cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT).returncode
    text = log.read_text(encoding="utf-8", errors="replace")
    last = [l for l in text.splitlines() if l.startswith("M12_SMOKE")]
    run_dir = ROOT / "private/work/m6_runs" / run
    seen = any(FFMPEG_MARK.encode() in p.read_bytes() for p in run_dir.rglob("*.log")) if run_dir.is_dir() else False
    lz = marker_file.read_text(encoding="ascii").count("lzxd_init") if marker_file.is_file() else 0
    return rc, (last[-1] if last else "no M12_SMOKE line"), seen, lz


def lzx_case(work):
    """An LZX stream with a known answer: Windows makecab (LZX, 2 MiB window) compresses a deterministic file; the
    probe gets the folder's concatenated CFDATA payload (CAB LZX = one stream), the original file is the oracle."""
    import random
    work.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(46)
    text = (ROOT / "tools/installer/LGPL-SOURCE.txt").read_bytes()
    parts = []
    while sum(map(len, parts)) < 1_200_000:
        parts.append(text[rnd.randrange(len(text) // 2):][:rnd.randrange(64, 4096)])
        parts.append(bytes(rnd.randrange(256) for _ in range(rnd.randrange(16, 512))))
    data = b"".join(parts)[:1_200_000]
    (work / "orig.bin").write_bytes(data)
    subprocess.run(["makecab", "/D", "CompressionType=LZX", "/D", "CompressionMemory=21", "orig.bin", "orig.cab"],
                   cwd=work, capture_output=True, check=True)
    cab = (work / "orig.cab").read_bytes()
    assert cab[:4] == b"MSCF" and struct.unpack_from("<H", cab, 34)[0] & 4 == 0
    assert struct.unpack_from("<H", cab, 26)[0] == 1, "one folder expected"
    start, blocks, ctype = struct.unpack_from("<IHH", cab, 36)
    assert ctype & 0xF == 3, f"not LZX: {ctype:#x}"
    window = 1 << ((ctype >> 8) & 0x1F)
    o, payload, total = start, [], 0
    for _ in range(blocks):
        _, cb, unc = struct.unpack_from("<IHH", cab, o)
        payload.append(cab[o + 8:o + 8 + cb])
        total += unc
        o += 8 + cb
    assert total == len(data)
    (work / "stream.lzx").write_bytes(b"".join(payload))
    return work / "stream.lzx", data, window


def build_probe(work):
    exe = work / "m46_lzx_probe.exe"
    bat = work / "probe.bat"
    bat.write_text("\r\n".join([
        "@echo off", f'call "{VCVARS}" >nul 2>&1', f'set "PATH={LLVM_BIN};%PATH%"',
        f'clang++ -std=c++20 -O2 "{ROOT / "tools/m46_lzx_probe.cpp"}" "{SDK_OUT / "rexruntime.lib"}" -o "{exe}" || exit /b 1',
        ""]), encoding="ascii")
    r = subprocess.run(["cmd", "/c", str(bat)], capture_output=True, text=True)
    if r.returncode or not exe.is_file():
        raise SystemExit(f"probe build failed: {r.stdout[-800:]} {r.stderr[-800:]}")
    return exe


def lzx_probe(probe, exe_dir, case, marker):
    stream, data, window = case
    stream, exe_dir, marker = Path(os.path.abspath(stream)), Path(os.path.abspath(exe_dir)), Path(os.path.abspath(marker))
    exe = exe_dir / probe.name
    shutil.copyfile(probe, exe)
    out = exe_dir / "lzx_out.bin"
    env = dict(os.environ, M46_MSPACK_MARKER=str(marker))
    r = subprocess.run([str(exe), str(stream), str(out), str(len(data)), str(window)], cwd=exe_dir, env=env,
                       capture_output=True, text=True, timeout=120)
    same = out.is_file() and out.read_bytes() == data
    lz = marker.read_text(encoding="ascii").count("lzxd_init") if marker.is_file() else 0
    exe.unlink()
    out.unlink(missing_ok=True)
    return r.returncode, same, lz, r.stdout.strip()


def cmd_replace_test(a):
    rec = record()
    base = WORK / "replace"
    if base.exists():
        raise SystemExit(f"{base} exists from an earlier test; move it away first")
    base.mkdir(parents=True)
    files, version = package_files()
    zpath = ROOT / rec["package"]["dir"] / f"{rec['package']['name']}-{version}.zip"
    digest = write_zip(files, zpath)
    check_package(zpath)
    print(f"archive {zpath.relative_to(ROOT)} sha256 {digest}")
    shipped = {n: pe_tables(SDK_OUT / n) for n in ("ffmpeg.dll", "mspack.dll")}
    variants = {}
    for kind, modify in (("plain", False), ("modified", True)):
        dlls = rebuild(zpath, base / f"src-{kind}", modify, log=base / f"rebuild-{kind}.log")
        print(f"rebuilt {kind}: " + ", ".join(f"{n} {sha256(p.read_bytes())[:16]}" for n, p in dlls.items()))
        for n, p in dlls.items():
            imp, exp = pe_tables(p)
            check(f"{kind} {n}: same export names as the shipped DLL", sorted(exp) == sorted(shipped[n][1]),
                  f"{len(exp)} vs {len(shipped[n][1])}")
            check(f"{kind} {n}: imports only Windows / C runtime DLLs",
                  all(system_import(d, rec["system_imports_allowed"]) for d in imp))
            same = sha256(p.read_bytes()) == sha256((SDK_OUT / n).read_bytes())
            print(f"note: {kind} {n} {'is' if same else 'is not'} byte-identical to the shipped DLL")
        has_mark = FFMPEG_MARK.encode() in dlls["ffmpeg.dll"].read_bytes() and b"M46_MSPACK_MARKER" in dlls["mspack.dll"].read_bytes()
        check(f"{kind}: marker code {'present' if modify else 'absent'}", has_mark == modify)
        exe_dir = base / f"bin-{kind}"
        exe_dir.mkdir()
        for n in ("r3hd.exe", "rexruntime.dll", "rexgpu-xenos.dll"):
            shutil.copyfile(APP_BUILD / n, exe_dir / n)
        for n, p in dlls.items():
            shutil.copyfile(p, exe_dir / n)
        variants[kind] = exe_dir
    case = lzx_case(base / "lzx")
    probe = build_probe(base)
    print(f"LZX case: {len(case[1])} bytes, window {case[2]}, stream {case[0].stat().st_size} bytes (makecab)")
    for kind, exe_dir in [("shipped", APP_BUILD)] + list(variants.items()):
        marker = base / f"lzx-{kind}.txt"
        rc, same, lz, line = lzx_probe(probe, exe_dir, case, marker) if kind != "shipped" else (None, None, None, None)
        if kind == "shipped":
            tmp = base / "bin-shipped"
            tmp.mkdir()
            for n in ("rexruntime.dll", "ffmpeg.dll", "mspack.dll"):
                shutil.copyfile(APP_BUILD / n, tmp / n)
            rc, same, lz, line = lzx_probe(probe, tmp, case, marker)
        print(f"{kind}: LZX probe exit {rc}, output equal {same}, lzxd_init marker lines {lz}; {line}")
        check(f"{kind}: runtime LZX path through mspack.dll decodes the cabinet stream exactly", rc == 0 and same)
        check(f"{kind}: lzxd_init marker {'written' if kind == 'modified' else 'absent'}", (lz > 0) == (kind == "modified"))
    for kind, exe_dir in variants.items():
        run = f"m46_replace_{kind}_{a.tag}"
        marker = base / f"mspack-{kind}.txt"
        rc, line, seen, lz = smoke(a.entry, run, exe_dir, marker)
        print(f"{kind}: exit {rc}; {line}; FFmpeg marker in log: {seen}; lzxd_init marker lines: {lz}")
        check(f"{kind}: hidden smoke passes with the rebuilt DLLs", rc == 0 and line.startswith("M12_SMOKE PASS"), line)
        if kind == "modified":
            check("modified ffmpeg.dll ran inside the game (its warning reached the runtime log)", seen)
        else:
            check("plain rebuild: no FFmpeg marker (control)", not seen)
        # Default.xex of this title uses basic compression: the game loads mspack.dll but never calls lzxd (lz == 0).
        print(f"note: {kind}: lzxd_init lines during the game run: {lz} (the title's XEX is not LZX-compressed)")
    print(f"M46_REPLACE {'PASS' if not failures else 'FAIL'} ({len(failures)} failure(s))")
    return 0 if not failures else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--build-tree", action="store_true")
    p = sub.add_parser("package")
    p.add_argument("--out")
    r = sub.add_parser("rebuild")
    r.add_argument("zip")
    r.add_argument("dir")
    r.add_argument("--modify", action="store_true")
    t = sub.add_parser("replace-test")
    t.add_argument("--entry", default="swamp_60_human")
    t.add_argument("--tag", default="1", help="suffix of the hidden run names (m46_replace_<kind>_<tag>)")
    a = ap.parse_args()
    return {"check": cmd_check, "package": cmd_package, "rebuild": cmd_rebuild, "replace-test": cmd_replace_test}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
