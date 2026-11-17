#!/usr/bin/env python3
"""Regression for the Linux package (B4, E-375) on synthetic binaries (POSIX with a C compiler; no game data).

Builds stand-in ELF binaries, packages them with tools/linux/r3hd_linux_package.py (the R-01 key audit is replaced by
the established boundary, since stand-ins carry no key), checks the archive, refuses tampering, extracts it and runs
the real portable preparation (app/tools/r3hd_portable.py prepare --no-input) up to its request for the person's game
data: the program files, the LGPL shared-library check and the platform check must pass first.

  python3 tools/linux/test_r3hd_linux_package.py [--cc gcc]
"""
import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import r3hd_linux_package as P  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cc", default="cc")
    a = ap.parse_args()
    fails, oks = [], []

    def check(name, ok, detail=""):
        (oks if ok else fails).append(name + ("" if ok else f" ({detail})"))
        print(("ok   " if ok else "FAIL ") + name + ("" if ok else f" ({detail})"))

    # E-376: dependency classification (any platform). The four desktop-session client libraries LX2 found are
    # admitted for librexruntime.so only, by exact SONAME; nothing else is.
    desktop = ["libX11.so.6", "libX11-xcb.so.1", "libxcb.so.1", "libwayland-client.so.0"]
    shipped = [r.split("/", 1)[1] for r in P.BINARIES]
    native = ["libffmpeg.so", "libmspack.so", "libc.so.6", "libm.so.6", "libstdc++.so.6", "libgcc_s.so.1"]
    check("runtime: the four desktop-session libraries are host libraries",
          P.unexpected_needed("bin/librexruntime.so", desktop + native, shipped) == [])
    check("the desktop-session libraries are not admitted for other binaries",
          P.unexpected_needed("bin/r3hd", desktop, shipped) == sorted(desktop)
          and P.unexpected_needed("bin/librexgpu-xenos.so", ["libxcb.so.1"], shipped) == ["libxcb.so.1"])
    for odd in ("libSDL3.so.0", "libz.so.1", "libX11.so.5", "libxcb-xkb.so.1", "libwayland-cursor.so.0",
                "libvulkan.so.1", "libavcodec.so.61"):
        check(f"runtime: unexpected {odd} is refused", P.unexpected_needed("bin/librexruntime.so", [odd], shipped) == [odd])
    # B7 (E-378): the floor comes from the exact symbol needs; the baselines name what blocks each system; the
    # portable preparation refuses an older system early with both versions.
    reqs = {"bin/r3hd": {"GLIBC_2.2.5": ["memcpy"], "GLIBC_2.44": ["new_fn"], "GLIBCXX_3.4.36": ["_ZNew"]},
            "bin/librexruntime.so": {"GLIBC_2.38": ["__isoc23_strtol"], "GLIBCXX_3.4.30": ["_ZOld"]}}
    check("floor from symbol needs", P.floor_from(reqs) == {"glibc": "2.44", "glibcxx": "3.4.36"}, P.floor_from(reqs))
    rep = P.baseline_report(reqs)
    check("baselines list the blocking symbols", "bin/r3hd: new_fn@GLIBC_2.44" in rep["ubuntu-26.04"]
          and "bin/r3hd: _ZNew@GLIBCXX_3.4.36" in rep["ubuntu-26.04"]
          and "bin/librexruntime.so: __isoc23_strtol@GLIBC_2.38" in rep["debian-12"]
          and not any("memcpy" in x for v in rep.values() for x in v), rep)
    sys.path.insert(0, str(HERE.parent))
    import r3hd_portable as portable
    floor = {"glibc": "2.44", "glibcxx": "3.4.36"}

    def refusal(versions, requires=floor):
        try:
            portable.check_linux_baseline(requires, lambda: versions)
        except portable.engine.Refusal as e:
            return str(e)
        return None
    old = refusal({"glibc": "2.43", "glibcxx": "3.4.35"})
    check("an older system is refused early with both versions",
          old is not None and "UNSUPPORTED_OS" in old and "glibc 2.44 or newer (this system: 2.43)" in old
          and "3.4.36 or newer (this system: 3.4.35)" in old, old)
    check("a newer system passes (2.44 vs 2.100 compares numerically)",
          refusal({"glibc": "2.100", "glibcxx": "3.4.36"}) is None)
    check("libstdc++ not found is refused", "not found" in (refusal({"glibc": "2.44", "glibcxx": None}) or ""))
    check("a package without a recorded floor is not checked", refusal({"glibc": None}, {}) is None)
    if os.name == "nt":
        print(f"R3HD_LINUX_PACKAGE_TEST {'PASS' if not fails else 'FAIL'} checks={len(oks) + len(fails)} "
              "(classification only; the package build is POSIX only)")
        return 0 if not fails else 1
    P.key_hits = lambda binaries: dict(P.KEY_BOUNDARY)  # stand-ins carry no key; the real audit runs natively
    import r3hd_linux_build as LB  # E-378: stand-in builds have no CMake tree; test_r3hd_host_inputs.py covers it
    LB.host_input_problems = lambda build, log: ["host inputs changed since r3hd was built: ['sdk:share/rexglue/rex_app.cpp']"]
    with tempfile.TemporaryDirectory() as tmp:
        try:
            P.build(Path(tmp), Path(tmp), Path(tmp) / "stale.tar.gz", "lx-test")
            check("a stale game build is refused before packaging", False, "built")
        except ValueError as e:
            check("a stale game build is refused before packaging",
                  "not current with its host inputs" in str(e) and not (Path(tmp) / "stale.tar.gz").exists(), e)
    LB.host_input_problems = lambda build, log: []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "bin").mkdir()
        (t / "lib").mkdir()
        (t / "stubs").mkdir()
        (t / "s.c").write_text("int r3hd_stand_in(void) { return 0; }\n")
        (t / "m.c").write_text("int main(void) { return 0; }\n")
        for soname in desktop + ["libSDL3.so.0"]:  # stand-ins with the real SONAMEs, so DT_NEEDED is exact
            subprocess.check_call([a.cc, "-shared", "-fPIC", f"-Wl,-soname,{soname}", str(t / "s.c"),
                                   "-o", str(t / "stubs" / soname)])

        def compile_set(bin_dir, lib_dir, runtime_needs, exe_needs=()):
            for rel, where in P.BINARIES.items():
                name = rel.split("/", 1)[1]
                src, flags = ("m.c", []) if name == "r3hd" else ("s.c", ["-shared", "-fPIC"])
                deps = runtime_needs if name == "librexruntime.so" else exe_needs if name == "r3hd" else ()
                d = bin_dir if where == "bin" else lib_dir
                subprocess.check_call([a.cc, *flags, str(t / src), "-o", str(d / name), "-Wl,--no-as-needed",
                                       *[str(t / "stubs" / s) for s in deps]])

        compile_set(t / "bin", t / "lib", desktop)
        out = t / "pkg.tar.gz"
        r = P.build(t / "bin", t / "lib", out, "lx-test")
        check("build + check PASS with the runtime needing the four desktop-session libraries",
              r["result"] == "PASS" and not r["publishable"] and r["host_desktop_libraries"] == sorted(desktop), r)
        check("the desktop-session libraries are not packaged", not any(
            n.endswith(tuple(desktop)) for n in tarfile.open(out).getnames()))
        for label, runtime, exe in (("runtime needs libSDL3.so.0", desktop + ["libSDL3.so.0"], ()),
                                    ("r3hd needs libX11.so.6", desktop, ["libX11.so.6"])):
            (t / label.replace(" ", "_")).mkdir()
            b, l = t / label.replace(" ", "_") / "bin", t / label.replace(" ", "_") / "lib"
            b.mkdir(), l.mkdir()
            compile_set(b, l, runtime, exe)
            try:
                P.build(b, l, t / (label.replace(" ", "_") + ".tar.gz"), "lx-test")
                check(f"refused: {label}", False, "built")
            except ValueError as e:
                check(f"refused: {label}", "neither packaged nor system" in str(e), e)
        check("never overwrites", _refuses(lambda: P.build(t / "bin", t / "lib", out, "lx-test")))
        # B3b (E-378): the Linux corresponding-source archive is verified and recorded in portable.json.
        import hashlib
        import json
        import zipfile
        version = json.loads((P.ROOT / "config/release/payload.json").read_bytes())["version"]

        def source_zip(name, platform="linux-x86_64", tamper=False):
            files = {"README.txt": b"r", "FFmpeg/COPYING.LGPLv2.1": b"l"}
            man = {"platform": platform, "program_version": version,
                   "components": {"ffmpeg": {"commit": "0604b464"}, "libmspack": {"commit": "30590772"}},
                   "files": {n: hashlib.sha256(d).hexdigest() for n, d in files.items()}}
            path = t / name
            path.parent.mkdir(exist_ok=True)
            with zipfile.ZipFile(path, "w") as z:
                for n, d in files.items():
                    z.writestr("r3hd-lgpl-source/" + n, d + (b"x" if tamper else b""))
                z.writestr("r3hd-lgpl-source/MANIFEST.json", json.dumps(man))
            return path

        good_src = source_zip(f"r3hd-lgpl-source-{version}-linux-x86_64.zip")
        r = P.build(t / "bin", t / "lib", t / "with-source.tar.gz", "lx-test", good_src)
        with tarfile.open(t / "with-source.tar.gz") as z:
            pj = json.loads(z.extractfile(P.TOP + "/portable.json").read())
            notice = z.extractfile(P.TOP + "/app/licenses/LGPL-SOURCE.txt").read()
        check("--lgpl-source: the archive's name and hash are recorded",
              pj["lgpl"]["corresponding_source"]["sha256"] == hashlib.sha256(good_src.read_bytes()).hexdigest()
              and r["lgpl_corresponding_source"]["archive"] == good_src.name, pj["lgpl"])
        check("the package's LGPL notice is the Linux one", b"libffmpeg.so" in notice and b"ffmpeg.dll" not in notice)
        for label, bad_src in (("wrong platform", source_zip(f"plat/r3hd-lgpl-source-{version}-linux-x86_64.zip", "windows")),
                               ("tampered file", source_zip(f"tam/r3hd-lgpl-source-{version}-linux-x86_64.zip", tamper=True)),
                               ("other version", source_zip("r3hd-lgpl-source-0.0.1-linux-x86_64.zip"))):
            dest = t / (label.replace(" ", "_") + ".tar.gz")
            check(f"--lgpl-source refused: {label}", _refuses(lambda: P.build(t / "bin", t / "lib", dest, "lx-test", bad_src))
                  and not dest.exists())
        with tarfile.open(out) as z:
            names = {m.name.split("/", 1)[1]: m for m in z.getmembers()}
        check("Windows-only entry points absent", not (set(names) & P.WINDOWS_ONLY), set(names) & P.WINDOWS_ONLY)
        check("launcher and portable preparer present",
              {"app/tools/linux/r3hd_play.py", "app/tools/r3hd_portable.py", "app/tools/r3hd_installer.py",
               "app/config/settings/registry.json", "Play.sh", "Settings.sh"} <= set(names))
        check("executable modes", names["bin/r3hd"].mode == 0o755 and names["Play.sh"].mode == 0o755
              and names["app/tools/r3hd_installer.py"].mode == 0o644)
        bad = t / "bad.tar.gz"
        with tarfile.open(out) as src, tarfile.open(bad, "w:gz") as dst:
            for m in src.getmembers():
                data = src.extractfile(m).read()
                if m.name.endswith("/settings.json.example") or m.name.endswith("app/README-LINUX.txt"):
                    data += b"x"
                    m.size = len(data)
                import io
                dst.addfile(m, io.BytesIO(data))
        check("tampered member refused", _refuses(lambda: P.check(bad)))
        home = t / "x"
        home.mkdir()
        with tarfile.open(out) as z:
            z.extractall(home, filter="data") if sys.version_info >= (3, 12) else z.extractall(home)
        root = home / P.TOP
        env = {k: v for k, v in os.environ.items() if not k.startswith("R3HD_")}
        p = subprocess.run(["sh", str(root / "Play.sh"), "--no-input"], capture_output=True, text=True, env=env,
                           timeout=300)
        text = p.stdout + p.stderr
        check("portable preparation reaches the game-data request (files, LGPL .so, platform pass)",
              p.returncode == 2 and "PACKAGE_REQUIRED" in text, text[-500:])
        check("no bytecode written into app/", not list((root / "app").rglob("__pycache__")))
        lib = root / "bin/libffmpeg.so"
        lib.write_bytes(b"not an ELF")
        p = subprocess.run(["sh", str(root / "Play.sh"), "--no-input"], capture_output=True, text=True, env=env)
        check("a replaced LGPL library that is not an ELF is refused clearly", "PORTABLE_LGPL_FORMAT" in p.stdout + p.stderr,
              (p.stdout + p.stderr)[-300:])
    print(f"R3HD_LINUX_PACKAGE_TEST {'PASS' if not fails else 'FAIL'} checks={len(oks) + len(fails)}")
    return 0 if not fails else 1


def _refuses(fn):
    try:
        fn()
    except (ValueError, OSError):
        return True
    return False


if __name__ == "__main__":
    sys.exit(main())
