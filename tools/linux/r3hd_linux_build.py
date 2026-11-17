"""LM-1 Linux build bring-up driver (native Linux x86-64 only; never used by the Windows build).

Replays the production SDK patch chain exactly as tools/build_milestone8.bat does (the order and the SDK target
list are read from that file, which stays the single source of truth). Then:
  * SDK: configured with the SDK's own `linux-amd64` preset (Clang, Ninja Multi-Config), built and installed as
    Release. Clang only: the SDK's CMake refuses every other compiler, and that requirement is not bypassed.
  * Per host compiler (Clang, and GCC where supported): the game host sources and the audited generated-code
    sample are compiled against that SDK install, and the POSIX host tests (m16, m20) are built and run.
It stops at compile readiness: no codegen, no game data, no game launch.

Subcommands:
  doctor    toolchain, workspace and SDK identity checks (read-only)
  run       doctor + patch chain + per-compiler SDK build/install + host compile + generated sample + host tests
  game      LM-2: link the real r3hd (Clang) from the DIAGNOSTIC, SEH-disabled tree against the SDK install of
            `run`; records ELF identity, dependencies and symbols; never runs it
  vbfix     D-020 on Vulkan (E-369): apply only the Vulkan IssueDraw edit of tools/m5_runtime_patch.py to the
            LM-1 SDK copy, rebuild/reinstall only rexgpu-xenos and stage it beside the unchanged LM-2 r3hd
  menu-run  one maintainer-watched, bounded run to the main menu in one D-020 mode (fixed | pinned); records the
            conditions, exit, logs and the mode the plugin logged
  evidence  zip the run's logs and results (PRIVATE: compiler output can name game symbols)
  hostupdate  LX-4 (E-375): bring the LM-A tree's prepared host sources to this source package (verified old -> new
            hashes; the manifest records the update), so `game` relinks r3hd with the portable PC Settings panel
  gamesync  E-378: incremental r3hd build in an existing game build, forced by the content of its host inputs (SDK
            install prefix, tree src/); writes the host-input stamp the package tool requires (sdkupdate runs it)

Workspace: a repository-shaped directory (the LM-1 source package) whose external/rexglue-sdk is a copy of an
existing SDK checkout at the pinned commit (the patch scripts address <repo>/external/rexglue-sdk). Nothing is
fetched, installed or system-configured.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SDK = ROOT / "external/rexglue-sdk"
SDK_PIN = "c94f5ebdcb3c9d1a460ca48e04f9758448f8d518"
SIMDE_PIN = "71fd833d9666141edcd1d3c109a80e228303d8d7"
COMPILERS = {"clang": ("clang", "clang++"), "gcc": ("gcc", "g++")}
HOST_SOURCES = ["tools/m2_host/main.cpp", "tools/m2_host/m2_trace.cpp"]
TOOLS = ["cmake", "ninja", "python3", "git", "pkg-config"]


class Fail(Exception):
    pass


def need(cond, what):
    if not cond:
        raise Fail(what)


def sh(argv, log, cwd=ROOT, check=True, env=None):
    """Run a command, append its full output to `log`, return (returncode, output)."""
    p = subprocess.run([str(a) for a in argv], cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout.decode(errors="replace")
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"$ {' '.join(map(str, argv))}\n{out}\n[exit {p.returncode}]\n")
    if check and p.returncode:
        raise Fail(f"command failed ({p.returncode}): {' '.join(map(str, argv))} (see {log.name})")
    return p.returncode, out


def git(*args, cwd=SDK):
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()


def patch_chain():
    """The python patch steps of tools/build_milestone8.bat, in order, up to the SDK configure."""
    steps = []
    for line in (ROOT / "tools/build_milestone8.bat").read_text(encoding="utf-8").splitlines():
        if line.startswith("cmake -S external/rexglue-sdk"):
            break
        m = re.fullmatch(r"python tools\\(\w+\.py) \|\| exit /b 1", line.strip())
        if m:
            steps.append(m.group(1))
    need(steps and steps[0] == "m2_runtime_patch.py" and len(steps) >= 30, f"patch chain parse ({len(steps)} steps)")
    return steps


def sdk_targets():
    """The SDK build targets of tools/build_milestone8.bat. SDL3_test is among them on purpose: the pinned SDK
    leaves SDL's SDL_TEST_LIBRARY at its default ON, so `cmake --install` installs libSDL3_test.a, which no other
    target depends on (LM-1 native attempt 1 failed at install without it)."""
    for line in (ROOT / "tools/build_milestone8.bat").read_text(encoding="utf-8").splitlines():
        m = re.match(r"cmake --build external/rexglue-sdk/out/build/win-amd64 --config Release --target (.+?) -j ", line)
        if m:
            targets = m.group(1).split()
            need("rexglue" in targets and "SDL3_test" in targets, f"SDK target list {targets}")
            return targets
    raise Fail("SDK build line not found in tools/build_milestone8.bat")


def doctor(compilers):
    facts = {"platform": platform.platform(), "machine": platform.machine(), "python": sys.version.split()[0]}
    need(platform.system() == "Linux" and platform.machine() == "x86_64", "native Linux x86-64 required")
    # The patch chain rewrites <ROOT>/external/rexglue-sdk: only ever in a source-package workspace (no .git),
    # never in a development checkout whose SDK another build uses.
    need(not (ROOT / ".git").exists(), "run only in an extracted source-package workspace, not a Git checkout")
    for t in TOOLS + list(COMPILERS["clang"]) + [c for k in compilers for c in COMPILERS[k]]:
        need(shutil.which(t), f"missing tool: {t}")
        facts[t] = subprocess.run([t, "--version"], capture_output=True, text=True).stdout.splitlines()[:1]
    need(git("rev-parse", "HEAD") == SDK_PIN, "workspace SDK is not at the pinned commit")
    simde = git("rev-parse", "HEAD", cwd=SDK / "thirdparty/simde")
    need(simde == SIMDE_PIN, f"SIMDe is not at its pin ({simde})")
    facts.update(sdk=SDK_PIN, simde=simde, steps=len(patch_chain()))
    for name in ("SOURCE_MANIFEST.json", "IMPLEMENTATION_ID.json"):
        if (ROOT / name).exists():
            facts[name] = json.loads((ROOT / name).read_text())
    return facts


def apply_patches(out):
    log = out / "patch.log"
    # Some patch steps skip an already-patched file (m46): the chain must start from the pristine pinned tree.
    modified = git("status", "--porcelain", "--untracked-files=no")
    need(not modified, "the workspace SDK copy has modified tracked files; use a fresh copy of the pinned checkout")
    steps = patch_chain()
    for step in steps:
        sh([sys.executable, f"tools/{step}"], log)
    return {"steps": steps, "sdk_status_lines": len(git("status", "--short").splitlines())}


SDK_PRESET = "linux-amd64"  # The SDK's own Linux preset: Clang, Ninja Multi-Config, Debug;Release;RelWithDebInfo.
SDK_CLANG_REQUIREMENT = "ReXGlue requires the Clang compiler"


def build_sdk(out, jobs):
    """Configure, build and install the patched SDK exactly as its supported preset does (Clang only).

    The preset matters for the install set: rexruntime links TracyClient only outside Release, through a generator
    expression. Under Ninja Multi-Config with all three configurations (the preset, and the Windows build) CMake
    keeps TracyClient as a target-level dependency, so a Release build produces it; a single-config Release build
    does not, while the install rules (REXGLUE_ENABLE_TRACY ON) still require libTracyClient.so (LM-1 retry 1).
    """
    log = out / "sdk-clang.log"
    build, prefix = SDK / f"out/build/{SDK_PRESET}", SDK / f"out/install/{SDK_PRESET}"
    flags = f"-march=x86-64-v2 -ffile-prefix-map={ROOT}=."
    result = {"preset": SDK_PRESET, "compiler": "clang", "config": "Release"}
    rc, text = sh(["cmake", "--preset", SDK_PRESET, f"-DCMAKE_C_FLAGS={flags}", f"-DCMAKE_CXX_FLAGS={flags}"], log,
                  cwd=SDK, check=False)
    result["configure_exit"] = rc
    if rc:
        result["configure_errors"] = install_errors(text)
        return result
    targets = sdk_targets()
    # Keep going so one run classifies every remaining Linux compile failure.
    rc, text = sh(["cmake", "--build", build, "--config", "Release", "--target", *targets, "-j", str(jobs), "--",
                   "-k", "0"], log, check=False)
    errors = sorted({m.group(0) for m in re.finditer(r"^[^\s:]+:\d+:\d+: (?:fatal )?error: .*$", text, re.M)})
    result.update(targets=targets, build_exit=rc, error_count=len(errors), errors=errors[:200],
                  warning_count=len(re.findall(r": warning: ", text)))
    if rc == 0:
        # Recorded, not raised: the CMake error is kept verbatim.
        irc, itext = sh(["cmake", "--install", build, "--config", "Release"], log, check=False)
        result["install_exit"] = irc
        result["install_errors"] = install_errors(itext)
        if irc == 0:
            result["installed"] = str(prefix.relative_to(ROOT))
    return result


def install_errors(text):
    """`CMake Error` blocks of a log (the error line plus its indented continuation lines)."""
    out, lines = [], text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("CMake Error"):
            block = [line] + [l for l in lines[i + 1:i + 6] if l.startswith("  ") and l.strip()]
            out.append(" ".join(x.strip() for x in block))
    return out[:20]


def summarize(result):
    """The SDK row plus one row per host compiler; never raises on a partial result."""
    sdk = result.get("sdk") or {}
    rows = {"sdk": {k: sdk.get(k) for k in ("configure_exit", "build_exit", "error_count", "install_exit")}}
    for key, row in (result.get("configurations") or {}).items():
        rows[key] = {"host": (row.get("host") or {}).get("status"),
                     "sample": (row.get("generated_sample") or {}).get("exit"), "tests": row.get("host_tests")}
    return rows


def sdk_passed(sdk):
    return bool(sdk) and sdk.get("configure_exit") == 0 and sdk.get("build_exit") == 0 and sdk.get("install_exit") == 0


def passed(row):
    """A compiler row passes when every check it can run passes. A GCC host compile that the SDK's own exported
    configuration refuses (Clang requirement) is recorded as sdk-unsupported and is not a failure."""
    host = (row.get("host") or {}).get("status")
    return (host in ("pass", "sdk-unsupported") and (row.get("generated_sample") or {"exit": 0}).get("exit") == 0
            and bool(row.get("host_tests")) and not any(row["host_tests"].values()))


def compile_host(out, key, private):
    """Object-compile the game host sources against the installed patched SDK (CMake, as the game target does)."""
    cc, cxx = COMPILERS[key]
    proj = out / f"host-{key}"
    shutil.rmtree(proj, ignore_errors=True)
    proj.mkdir(parents=True)
    sources = [s for s in HOST_SOURCES if s.endswith("m2_trace.cpp") or private]
    (proj / "CMakeLists.txt").write_text(f"""cmake_minimum_required(VERSION 3.24)
project(r3hd_host_check LANGUAGES C CXX)
find_package(rexglue CONFIG REQUIRED)
add_library(r3hd_host OBJECT {' '.join(f'"{ROOT / s}"' for s in sources)})
target_compile_features(r3hd_host PRIVATE cxx_std_23)
# Game-tree layout: src/ holds the m2_host sources and the m8/m18/trailer headers next to them.
target_include_directories(r3hd_host PRIVATE "{ROOT / 'tools/m2_host'}" "{ROOT / 'tools'}" "{ROOT / 'tools/linux/compat'}" {f'"{private}"' if private else ''})
target_link_libraries(r3hd_host PRIVATE rex::runtime)
""")
    log = out / f"host-{key}.log"
    result = {"sources": sources, "skipped": [] if private else
              ["tools/m2_host/main.cpp (needs the private generated headers: --private-headers)"]}
    rc, text = sh(["cmake", "-S", proj, "-B", proj / "build", "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                   f"-DCMAKE_C_COMPILER={cc}", f"-DCMAKE_CXX_COMPILER={cxx}",
                   f"-DCMAKE_PREFIX_PATH={SDK / f'out/install/{SDK_PRESET}'}"], log, check=False)
    result["configure_exit"] = rc
    if rc:
        refused = SDK_CLANG_REQUIREMENT in text and key != "clang"
        result.update(status="sdk-unsupported" if refused else "fail", errors=install_errors(text))
        return result
    rc, text = sh(["cmake", "--build", proj / "build", "--", "-k", "0"], log, check=False)
    result.update(exit=rc, status="pass" if rc == 0 else "fail",
                  errors=re.findall(r"^\S+:\d+:\d+: error: .*$", text, re.M)[:50])
    return result


def compile_generated_sample(out, key, lge_private):
    """Object-compile the audited LGE generated sample (private, non-SEH bodies) against the patched SDK headers."""
    cc, cxx = COMPILERS[key]
    obj = out / f"generated-{key}.o"
    inc = SDK / f"out/install/{SDK_PRESET}/include"
    argv = [cxx, "-std=c++23", "-O2", "-msse4.1", "-fno-fast-math", "-frounding-math", "-c",
            "-DSPDLOG_COMPILED_LIB", "-DSPDLOG_FMT_EXTERNAL", "-I", ROOT / "tools/m2_host", "-I",
            ROOT / "tools/linux/compat", "-I", lge_private, "-isystem", inc, lge_private / "lge_generated.cpp",
            "-o", obj]
    if key == "gcc":
        # GCC only, both audited LGE workarounds: the DEFINE_REX_FUNC attribute placement (see its README) and the
        # prelude's __builtin_assume, which GCC lacks (LM-1 retry 2), in the pinned template's own GCC form.
        argv[1:1] = ["-include", ROOT / "tools/linux/compat_gcc/rex_gcc_builtin_assume.h",
                     "-include", ROOT / "tools/experiments/linux_guest_entry/lge_define_rex_func.h"]
    rc, text = sh(argv, out / f"generated-{key}.log", check=False)
    if obj.exists():
        obj.unlink()  # Compiled game code never leaves the workspace.
    return {"exit": rc, "errors": re.findall(r"^\S+:\d+:\d+: error: .*$", text, re.M)[:50]}


def host_tests(out, key):
    cc, cxx = COMPILERS[key]
    results = {}
    tests = {"m16_vblank_posix": ["tools/linux/m16_vblank_posix_test.cpp", "-I", "tools/linux/test_stub", "-I", "tools"],
             "m20_save_commit": ["tools/m20_save_commit_test.cpp", "-I", "tools"]}
    for name, args in tests.items():
        for opt in ("-O0", "-O2"):
            exe = out / f"{name}-{key}{opt}"
            log = out / f"test-{name}-{key}{opt}.log"
            rc, _ = sh([cxx, "-std=c++20", opt, "-Wall", "-Wextra", "-Werror", *args, "-o", exe], log, check=False)
            if rc == 0:
                work = out / f"{name}-{key}{opt}.work"
                shutil.rmtree(work, ignore_errors=True)
                work.mkdir()
                rc, _ = sh([exe], log, cwd=work, check=False)
                shutil.rmtree(work, ignore_errors=True)
            results[f"{name}{opt}"] = rc
    return results


def run(args):
    """SDK (Clang, preset) once; then per host compiler: host sources, generated sample, POSIX host tests.

    Acceptance: the SDK configure, build and install pass with Clang (the SDK refuses other compilers), and every
    per-compiler check passes. GCC is used only for components that do not build the SDK."""
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = {"status": "INCOMPLETE", "compilers": args.compilers}
    try:
        result["doctor"] = doctor(args.compilers)
        result["patch"] = apply_patches(out)
        result["sdk"] = build_sdk(out, args.jobs)
        for key in args.compilers:
            row = result.setdefault("configurations", {}).setdefault(key, {})
            if result["sdk"].get("installed"):
                row["host"] = compile_host(out, key, args.private_headers)
                if args.lge_private:
                    row["generated_sample"] = compile_generated_sample(out, key, args.lge_private.resolve())
            row["host_tests"] = host_tests(out, key)
        rows = list(result["configurations"].values())
        ok = sdk_passed(result["sdk"]) and rows and all(passed(r) for r in rows)
        result["status"] = "PASS" if ok else "FAIL"
    except Fail as error:
        result["status"], result["error"] = "FAIL", str(error)
    except Exception as error:  # Never let a driver bug hide the build's own result.
        result["status"], result["error"] = "FAIL", f"driver error {type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()[-4000:]
    finally:
        (out / "results.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(f"R3HD_LINUX_BUILD {result['status']} {json.dumps(summarize(result), sort_keys=True)} "
          f"{result.get('error', '')} results={out / 'results.json'}")
    return 0 if result["status"] == "PASS" else 1


GAME_REQUIRED_SYMBOLS = ("main", "r3hd_diagnostic_build", "_Z7M2EnterPKcR10PPCContext", "PPCImageConfig",
                         "PPCFuncMappings")
GAME_FORBIDDEN_SYMBOL_PARTS = ("M4Init", "M4SehFilter", "M4SehUnwind")  # No M4 SEH emission in the diagnostic tree.
# LM-A: the production tree on the portable backend. M4 owners are present (M4Init may be inlined, so it is not
# required); the Windows-only filter must not be. The portable backend's fail-fast record must be in the binary.
LMA_REQUIRED_SYMBOLS = ("main", "r3hd_lma_build", "_Z7M2EnterPKcR10PPCContext", "PPCImageConfig", "PPCFuncMappings")
LMA_FORBIDDEN_SYMBOL_PARTS = ("M4SehFilter",)
TREE_KINDS = {  # marker -> kind, manifest, build directory, banner bytes
    "DIAGNOSTIC_SEH_DISABLED.txt": ("diag", "diag_manifest.json", "build/game",
                                    b"R3HD DIAGNOSTIC BUILD: guest SEH disabled"),
    "LMA_PORTABLE_M4.txt": ("lma", "lma_manifest.json", "build/game-lma",
                            b"R3HD LINUX PREVIEW (LM-A): portable M4 guest exceptions"),
}


def tree_kind(tree):
    kinds = [v for marker, v in TREE_KINDS.items() if (tree / marker).is_file()]
    need(len(kinds) == 1, f"{tree} is not a marked tree ({', '.join(TREE_KINDS)})")
    return kinds[0]


def verify_tree(tree):
    """The tree is marked and every generated/host file matches its recorded SHA-256."""
    kind, manifest_name, _, _ = tree_kind(tree)
    m = json.loads((tree / manifest_name).read_text())
    if kind == "diag":
        need(m.get("format") == "R3HD_DIAG_TREE_V1"
             and m["manifest_change"][1] == "generate_exception_handlers = false", "diagnostic tree manifest")
    else:
        need(m.get("format") == "R3HD_LMA_TREE_V1", "LM-A tree manifest")
        need(hashlib.sha256((tree / "m4_generated_test.cpp").read_bytes()).hexdigest()
             == m["m4_generated_test_sha256"], "tree m4_generated_test.cpp")
    for name, digest in m["generated_sha256"].items():
        need(hashlib.sha256((tree / "generated/default" / name).read_bytes()).hexdigest() == digest, f"tree file {name}")
    for name, digest in m["src_sha256"].items():
        need(hashlib.sha256((tree / "src" / name).read_bytes()).hexdigest() == digest, f"tree src {name}")
    if kind == "diag":
        return {"kind": kind, "codegen_files": m["codegen_files"], "codegen_digest": m["codegen_digest"],
                "audit": m["audit"], "seh_emission": m["seh_emission"]}
    return {"kind": kind, "codegen_files": m["codegen"]["files"], "codegen_digest": m["codegen"]["digest"],
            "generated_files": len(m["generated_sha256"])}


def symbol_checks(nm_text, kind="diag"):
    names = {l.split()[-1] for l in nm_text.splitlines() if l.strip()}
    required = GAME_REQUIRED_SYMBOLS if kind == "diag" else LMA_REQUIRED_SYMBOLS
    forbidden = GAME_FORBIDDEN_SYMBOL_PARTS if kind == "diag" else LMA_FORBIDDEN_SYMBOL_PARTS
    return {"missing": [s for s in required if s not in names],
            "forbidden": sorted(n for n in names if any(p in n for p in forbidden)),
            "imp_functions": sum(1 for n in names if n.startswith("__imp__"))}


def build_game(out, tree, jobs):
    """Configure and build the Linux r3hd (Clang) from a marked tree against the LM-1 SDK install. No run."""
    prefix = SDK / f"out/install/{SDK_PRESET}"
    need((prefix / "lib/cmake/rexglue").is_dir(), f"no SDK install at {prefix} (run `run` first, LM-1)")
    kind, _, build_dir, banner = tree_kind(tree)
    result = {"tree": verify_tree(tree), "sdk_prefix": str(prefix.relative_to(ROOT))}
    build = out / build_dir
    shutil.rmtree(build, ignore_errors=True)
    log = out / "game.log"
    flags = f"-march=x86-64-v2 -ffile-prefix-map={ROOT}=."
    rc, text = sh(["cmake", "-S", ROOT / "tools/linux/game", "-B", build, "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
                   "-DCMAKE_C_COMPILER=clang", "-DCMAKE_CXX_COMPILER=clang++", f"-DCMAKE_C_FLAGS={flags}",
                   f"-DCMAKE_CXX_FLAGS={flags}", f"-DCMAKE_PREFIX_PATH={prefix}", f"-DR3HD_TREE={tree}"], log,
                  check=False)
    result["configure_exit"] = rc
    if rc:
        result["configure_errors"] = install_errors(text)
        return result
    rc, text = sh(["cmake", "--build", build, "--target", "r3hd", "-j", str(jobs), "--", "-k", "0"], log, check=False)
    errors = sorted({m.group(0) for m in re.finditer(r"^[^\s:]+:\d+:\d+: (?:fatal )?error: .*$", text, re.M)})
    link = sorted({l.strip() for l in text.splitlines() if "undefined reference" in l or "ld.lld: error" in l
                   or "ld: error" in l})
    result.update(build_exit=rc, error_count=len(errors), errors=errors[:200], link_errors=link[:100],
                  warning_count=len(re.findall(r": warning: ", text)))
    elf = build / "r3hd"
    if rc == 0 and elf.is_file():
        data = elf.read_bytes()
        _, header = sh(["readelf", "-h", "-W", elf], log, check=False)
        _, dynamic = sh(["readelf", "-d", "-W", elf], log, check=False)
        _, nm = sh(["nm", "--defined-only", elf], log, check=False)
        result["elf"] = {"path": str(elf.relative_to(ROOT)), "size": len(data),
                         "sha256": hashlib.sha256(data).hexdigest(),
                         "type": next((l.split(":", 1)[1].strip() for l in header.splitlines() if "Type:" in l), None),
                         "machine": next((l.split(":", 1)[1].strip() for l in header.splitlines() if "Machine:" in l), None),
                         "needed": re.findall(r"\(NEEDED\).*\[(.+?)\]", dynamic),
                         "runpath": re.findall(r"\((?:RUNPATH|RPATH)\).*\[(.+?)\]", dynamic),
                         "diagnostic_banner": banner in data,
                         "symbols": symbol_checks(nm, kind)}
        if kind == "lma":  # the portable backend is linked in (its fail-fast record), not the stand-in
            result["elf"]["portable_m4"] = b"M4 portable: FAIL-FAST" in data
    return result


def game_passed(result):
    elf = result.get("elf") or {}
    sym = elf.get("symbols") or {}
    lma = (result.get("tree") or {}).get("kind") == "lma"
    return (result.get("configure_exit") == 0 and result.get("build_exit") == 0 and bool(elf)
            and elf.get("diagnostic_banner") and not sym.get("missing") and not sym.get("forbidden")
            and (not lma or elf.get("portable_m4")))


def game(args):
    """LM-2: link the real r3hd from the diagnostic tree. Never runs it (LM-C needs separate authorization)."""
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = {"status": "INCOMPLETE", "diagnostic": "guest SEH disabled; never compatibility evidence"}
    try:
        need(platform.system() == "Linux" and platform.machine() == "x86_64", "native Linux x86-64 required")
        need(shutil.which("clang++") and shutil.which("readelf") and shutil.which("nm"), "clang++/readelf/nm required")
        result["game"] = build_game(out, args.tree.resolve(), args.jobs)
        if result["game"].get("tree", {}).get("kind") == "lma":  # E-374: the LM-A tree is not the diagnostic one
            result["diagnostic"] = ("LM-A production tree, portable M4; hardware-fault conversion not implemented; "
                                    "not a compatibility claim")
        result["status"] = "PASS" if game_passed(result["game"]) else "FAIL"
    except Fail as error:
        result["status"], result["error"] = "FAIL", str(error)
    except Exception as error:  # Never let a driver bug hide the build's own result.
        result["status"], result["error"] = "FAIL", f"driver error {type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()[-4000:]
    finally:
        kind = ((result.get("game") or {}).get("tree") or {}).get("kind", "diag")
        results_name = "results-game.json" if kind == "diag" else f"results-game-{kind}.json"
        (out / results_name).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    g = result.get("game") or {}
    elf = g.get("elf") or {}
    print(f"R3HD_LINUX_GAME {result['status']} kind={kind} configure={g.get('configure_exit')} "
          f"build={g.get('build_exit')} errors={g.get('error_count')} link_errors={len(g.get('link_errors') or [])} "
          f"size={elf.get('size')} sha256={elf.get('sha256')} portable_m4={elf.get('portable_m4')} "
          f"{result.get('error', '')} results={out / results_name}")
    return 0 if result["status"] == "PASS" else 1


# ---- D-020 on Vulkan (E-369): patch one SDK file, rebuild only the GPU plugin, then a bounded menu A/B. ----
VULKAN_CP = "src/graphics/vulkan/command_processor.cpp"
# LF SHA-256 of that file at the pin, and after tools/m5_runtime_patch.py (from a full Windows replay of the chain).
VULKAN_CP_PINNED = "4335110822d13947338efd7e773bd99266633d7083dfae9c9680034c0799dc77"
VULKAN_CP_FIXED = "135d277ea265a3e5e366a2be92a9bdd01c90efaa4c3fdeb738d6852772dfa05c"
# tools/r3hd_build_doctor.py sdk_digest of the whole patched tree after the chain without / with the Vulkan edit.
CHAIN_DIGEST_BEFORE = (99, "dc84f10269d32da0470c78d4b6039326c53221159b0350177a6dbe0c50edb70d")
CHAIN_DIGEST_AFTER = (100, "32362c3eb39d6eae4a6d3c429f9039a6e83d047ef78a831cabfa1cfdcc4bbda0")
LM2_ELF_SHA256 = "9191dee00913bde1d47ae2c9603a88738a9f41ccbb76ec862bbe2ab537c448a2"
PLUGIN = "librexgpu-xenos.so"
VB_MODE_MARKER = b"M5 vb_residency backend=vulkan mode="
DEFAULT_GAME_BUILD = ROOT / "private/work/linux_build/native_lm2/build/game"


def lf_sha256(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def chain_digest():
    sys.path.insert(0, str(ROOT / "tools"))
    import r3hd_build_doctor
    return r3hd_build_doctor.sdk_digest(SDK)


def installed_plugin():
    found = sorted((SDK / f"out/install/{SDK_PRESET}").rglob(PLUGIN))
    need(len(found) == 1, f"expected one installed {PLUGIN}, found {[str(p) for p in found]}")
    return found[0]


def apply_vulkan_vb_fix():
    """Apply only the Vulkan D-020 edit, with the chain's own patch() and edit list.

    Replaying tools/m5_runtime_patch.py alone on an already-patched tree would insert its other edits a second time;
    no other chain step touches this file (proven by the full replay), so this one edit reaches exactly the state of
    a fresh chain replay. The file must be pinned (or already fixed: idempotent); anything else stops."""
    path = SDK / VULKAN_CP
    before = lf_sha256(path)
    need(before in (VULKAN_CP_PINNED, VULKAN_CP_FIXED), f"{VULKAN_CP} is neither pinned nor D-020-fixed ({before})")
    if before == VULKAN_CP_PINNED:
        sys.path.insert(0, str(ROOT / "tools"))
        from m3_runtime_patch import patch
        from m5_runtime_patch import VULKAN_VB_EDITS
        patch(VULKAN_CP, VULKAN_VB_EDITS, from_head=False)
    after = lf_sha256(path)
    need(after == VULKAN_CP_FIXED, f"{VULKAN_CP} after the edit differs from the replayed chain ({after})")
    return {"before": before, "after": after, "applied": before == VULKAN_CP_PINNED}


def vbfix_passed(result):
    plugin = result.get("plugin") or {}
    return (result.get("source", {}).get("after") == VULKAN_CP_FIXED and result.get("build_exit") == 0
            and result.get("install_exit") == 0 and plugin.get("marker") and result.get("elf_unchanged"))


def vbfix(args):
    """Patch the Vulkan IssueDraw (D-020), rebuild and reinstall only rexgpu-xenos, stage it beside the LM-2 r3hd.

    The LM-2 ELF is reused unchanged: the edit lives in the GPU plugin, which r3hd loads from its own folder."""
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    log = out / "vbfix.log"
    game_build = args.game_build.resolve()
    result = {"status": "INCOMPLETE", "diagnostic": "guest SEH disabled; never compatibility evidence"}
    try:
        need(platform.system() == "Linux" and platform.machine() == "x86_64", "native Linux x86-64 required")
        need(not (ROOT / ".git").exists(), "run only in an extracted source-package workspace, not a Git checkout")
        need(git("rev-parse", "HEAD") == SDK_PIN, "workspace SDK is not at the pinned commit")
        need((SDK / f"out/build/{SDK_PRESET}/CMakeCache.txt").is_file(), "no LM-1 SDK build tree (run `run` first)")
        elf = game_build / "r3hd"
        need(elf.is_file() and hashlib.sha256(elf.read_bytes()).hexdigest() == LM2_ELF_SHA256,
             f"{elf} is not the LM-2 ELF")
        pre = chain_digest()
        result["chain_before"] = {"files": pre[0], "digest": pre[1], "matches_replay": tuple(pre) == CHAIN_DIGEST_BEFORE}
        result["source"] = apply_vulkan_vb_fix()
        post = chain_digest()
        result["chain_after"] = {"files": post[0], "digest": post[1], "matches_replay": tuple(post) == CHAIN_DIGEST_AFTER}
        build = SDK / f"out/build/{SDK_PRESET}"
        rc, text = sh(["cmake", "--build", build, "--config", "Release", "--target", "rexgpu-xenos", "-j",
                       str(args.jobs)], log, check=False)
        result["build_exit"] = rc
        result["compiled"] = sorted(set(re.findall(r"Building CXX object (\S+)", text)))
        result["errors"] = sorted({m.group(0) for m in re.finditer(r"^[^\s:]+:\d+:\d+: (?:fatal )?error: .*$", text,
                                                                   re.M)})[:50]
        if rc == 0:
            result["install_exit"], _ = sh(["cmake", "--install", build, "--config", "Release"], log, check=False)
        if result.get("install_exit") == 0:
            staged = game_build / PLUGIN
            backup = out / "plugin_before" / PLUGIN
            if staged.is_file() and not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staged, backup)  # the LM-C plugin, kept for a revert
            source = installed_plugin()
            shutil.copy2(source, staged)
            data = staged.read_bytes()
            result["plugin"] = {"installed": str(source.relative_to(ROOT)), "staged": str(staged.relative_to(ROOT)),
                                "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
                                "marker": VB_MODE_MARKER in data,
                                "before_sha256": hashlib.sha256(backup.read_bytes()).hexdigest()
                                if backup.is_file() else None}
        result["elf_unchanged"] = hashlib.sha256(elf.read_bytes()).hexdigest() == LM2_ELF_SHA256
        result["status"] = "PASS" if vbfix_passed(result) else "FAIL"
    except Fail as error:
        result["status"], result["error"] = "FAIL", str(error)
    except Exception as error:  # Never let a driver bug hide the build's own result.
        result["status"], result["error"] = "FAIL", f"driver error {type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()[-4000:]
    finally:
        (out / "results-vbfix.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    plugin = result.get("plugin") or {}
    print(f"R3HD_LINUX_VBFIX {result['status']} build={result.get('build_exit')} install={result.get('install_exit')} "
          f"compiled={len(result.get('compiled') or [])} marker={plugin.get('marker')} "
          f"elf_unchanged={result.get('elf_unchanged')} chain_before={result.get('chain_before', {}).get('matches_replay')} "
          f"chain_after={result.get('chain_after', {}).get('matches_replay')} {result.get('error', '')}")
    return 0 if result["status"] == "PASS" else 1


# LX-4 (E-375): host sources of the LM-A tree that this source package changes. "old" is the tree as packaged
# (lma_manifest.json), "new" what this package gives: r3hd_pc_settings.h is copied as is (m2_prepare copies it
# unchanged); r3hd_app.h is m2_prepare's own variant, so only the one-line hook is applied to it (its line ending kept).
HOST_UPDATES = {
    "r3hd_pc_settings.h": {"old": "66127c3c5023b3efdebcf17d837a1fa079ced2c8421adf0b60afa8f7b0caf0b9",
                           "new": "59968c316af7eece777c6015d142b56425492cc1d32455c453bee72620419e60",
                           "source": "tools/m2_host/r3hd_pc_settings.h"},
    "r3hd_app.h": {"old": "bff53d1655e65a773ec688295045b9b061337f936a76d6067335875dac3ad661",
                   "new": "f7b010c0e591f3c8a67a43877a52cfccc4b01aadb73e6b61b8b7cc8b07dfa5a7",
                   "edit": ("  void OnConfigureFonts(ImFontAtlas* atlas) override {",
                            "  void OnConfigureFonts(ImFontAtlas* atlas) override { R3HD_PCSET_POSIX_FONTS(atlas, pcset_host_.font)")},
}


def hostupdate(args):
    tree = args.tree.resolve()
    result = {"status": "INCOMPLETE", "files": {}}
    try:
        kind, manifest_name, _, _ = tree_kind(tree)
        need(kind == "lma", f"{tree} is not the LM-A tree")
        verify_tree(tree)  # the tree as it is now (old, or already updated) matches its manifest
        m = json.loads((tree / manifest_name).read_text())
        for name, h in HOST_UPDATES.items():
            path = tree / "src" / name
            cur = hashlib.sha256(path.read_bytes()).hexdigest()
            need(cur in (h["old"], h["new"]), f"src/{name}: unexpected content {cur}")
            if cur == h["old"]:
                if "source" in h:
                    data = (ROOT / h["source"]).read_bytes().replace(b"\r\n", b"\n")
                else:
                    old = path.read_bytes()
                    eol = b"\r\n" if b"\r\n" in old else b"\n"
                    anchor, repl = (x.encode() + eol for x in h["edit"])
                    need(old.count(anchor) == 1, f"src/{name}: edit anchor")
                    data = old.replace(anchor, repl)
                need(hashlib.sha256(data).hexdigest() == h["new"], f"src/{name}: new content differs from the package")
                path.write_bytes(data)
            m["src_sha256"][name] = h["new"]
            result["files"][name] = {"before": cur, "after": h["new"], "written": cur != h["new"]}
        if any(f["written"] for f in result["files"].values()):
            m.setdefault("host_updates", []).append({"by": "r3hd_linux_build.py hostupdate (LX-4, E-375)",
                                                     "files": {n: f["after"] for n, f in result["files"].items()}})
            (tree / manifest_name).write_text(json.dumps(m, indent=1) + "\n")
        verify_tree(tree)
        result["status"] = "PASS"
    except Fail as error:
        result["status"], result["error"] = "FAIL", str(error)
    print(f"R3HD_LINUX_HOSTUPDATE {result['status']} "
          f"written={sum(f['written'] for f in result['files'].values())} {result.get('error', '')}")
    return 0 if result["status"] == "PASS" else 1


def sdkupdate_passed(result):
    return (result.get("chain_after", {}).get("matches_new") and result.get("build_exit") == 0
            and result.get("install_exit") == 0)


def sdkupdate(args):
    """LM-A: bring the SDK copy from one patch-chain state to the next without a pristine replay.

    delta.json (made on Windows from two isolated full replays) lists every SDK file that differs between the chain
    the workspace was built with and the current one, with LF SHA-256 before and after, and both whole-tree digests.
    Each file must be in its expected old (or already new) state; it is replaced from the delta and checked; the whole
    tree must then equal the replayed new chain. Then an incremental SDK build and install (only what changed)."""
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    log = out / "sdkupdate.log"
    delta = args.delta.resolve()
    result = {"status": "INCOMPLETE"}
    try:
        need(platform.system() == "Linux" and platform.machine() == "x86_64", "native Linux x86-64 required")
        need(not (ROOT / ".git").exists(), "run only in an extracted source-package workspace, not a Git checkout")
        need(git("rev-parse", "HEAD") == SDK_PIN, "workspace SDK is not at the pinned commit")
        build = SDK / f"out/build/{SDK_PRESET}"
        need((build / "CMakeCache.txt").is_file(), "no LM-1 SDK build tree (run `run` first)")
        m = json.loads((delta / "delta.json").read_text())
        pre = chain_digest()
        result["chain_before"] = {"files": pre[0], "digest": pre[1], "matches_old": list(pre) == m["chain_old"],
                                  "matches_new": list(pre) == m["chain_new"]}
        need(result["chain_before"]["matches_old"] or result["chain_before"]["matches_new"],
             f"SDK chain state {pre} is neither the expected old {m['chain_old']} nor the new {m['chain_new']}")
        files = {}
        for rel, h in m["files"].items():
            path = SDK / rel
            cur = lf_sha256(path) if path.exists() else None
            need(cur in (h["old"], h["new"]), f"{rel}: unexpected content {cur}")
            if cur != h["new"]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((delta / "files" / rel).read_bytes())
            after = lf_sha256(path)
            need(after == h["new"], f"{rel}: content after the update differs ({after})")
            files[rel] = {"before": cur, "after": after, "written": cur != h["new"]}
        result["files"] = files
        post = chain_digest()
        result["chain_after"] = {"files": post[0], "digest": post[1], "matches_new": list(post) == m["chain_new"]}
        need(result["chain_after"]["matches_new"], f"SDK chain state after the update {post} != {m['chain_new']}")
        rc, text = sh(["cmake", "--build", build, "--config", "Release", "--target", *sdk_targets(), "-j",
                       str(args.jobs), "--", "-k", "0"], log, check=False)
        result["build_exit"] = rc
        result["compiled"] = len(set(re.findall(r"Building CXX object (\S+)", text)))
        result["errors"] = sorted({x.group(0) for x in re.finditer(r"^[^\s:]+:\d+:\d+: (?:fatal )?error: .*$", text,
                                                                   re.M)})[:50]
        if rc == 0:
            result["install_exit"], _ = sh(["cmake", "--install", build, "--config", "Release"], log, check=False)
        if result.get("install_exit") == 0 and getattr(args, "game_build", None):
            # E-374: the run directory holds its own copy of the GPU plugin (librexruntime comes from the SDK
            # install through LD_LIBRARY_PATH); refresh it so a run uses what the delta rebuilt.
            staged = args.game_build.resolve() / PLUGIN
            need(staged.is_file(), f"no staged {PLUGIN} in {args.game_build}")
            shutil.copy2(installed_plugin(), staged)
            result["staged_plugin_sha256"] = hashlib.sha256(staged.read_bytes()).hexdigest()
            # E-378: the game target compiles installed SDK sources itself (share/rexglue/rex_app.cpp) and includes
            # installed headers; relinking librexruntime.so never recompiles them. Rebuild the game target too.
            result["game"] = game_rebuild(args.game_build.resolve(), args.jobs, log)
        result["status"] = "PASS" if sdkupdate_passed(result) and \
            (not getattr(args, "game_build", None) or gamesync_passed(result.get("game") or {})) else "FAIL"
    except Fail as error:
        result["status"], result["error"] = "FAIL", str(error)
    except Exception as error:  # Never let a driver bug hide the build's own result.
        result["status"], result["error"] = "FAIL", f"driver error {type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()[-4000:]
    finally:
        (out / "results-sdkupdate.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(f"R3HD_LINUX_SDKUPDATE {result['status']} written={sum(f['written'] for f in (result.get('files') or {}).values())} "
          f"chain_after={result.get('chain_after', {}).get('matches_new')} build={result.get('build_exit')} "
          f"compiled={result.get('compiled')} install={result.get('install_exit')} "
          f"game_compiled={len((result.get('game') or {}).get('compiled') or [])} "
          f"elf={(result.get('game') or {}).get('elf_sha256')} {result.get('error', '')}")
    return 0 if result["status"] == "PASS" else 1


# ---- E-378: the game build's host inputs. LX2C showed a stale r3hd: sdkupdate relinked librexruntime.so, but the
# game target compiles the installed share/rexglue/rex_app.cpp itself, so its LX-6 change never reached the ELF.
# The game build directory therefore carries a content stamp of every host input outside the generated code: all
# files of the SDK install prefix (sources, headers, CMake package, libraries) and the tree's prepared src/. It is
# written only after a successful incremental build that leaves Ninja nothing to do; a package is refused unless
# the stamp names the ELF being packaged and still equals the inputs. Content, not timestamps: a changed input is
# touched before the build, so Ninja recompiles its dependants even if a copy kept an older modification time.
HOST_STAMP = "r3hd-host-inputs.json"


def game_cache(build):
    """(tree, prefix) of a configured game build, from its CMakeCache.txt."""
    cache = build / "CMakeCache.txt"
    need(cache.is_file(), f"{build} is not a configured game build (no CMakeCache.txt)")
    values = dict(re.findall(r"^([A-Za-z0-9_]+):[A-Z]+=(.*)$", cache.read_text(errors="replace"), re.M))
    need(values.get("R3HD_TREE") and values.get("CMAKE_PREFIX_PATH"), f"{cache}: no R3HD_TREE / CMAKE_PREFIX_PATH")
    return Path(values["R3HD_TREE"]), Path(values["CMAKE_PREFIX_PATH"].split(";")[0])


def host_inputs(build):
    """{key: (path, sha256)} for every host input of the game build (see HOST_STAMP)."""
    tree, prefix = game_cache(build)
    need(prefix.is_dir() and (tree / "src").is_dir(), f"game build inputs missing: {prefix}, {tree / 'src'}")
    found = {}
    for label, base in (("sdk", prefix), ("tree", tree / "src")):
        for p in sorted(base.rglob("*")):
            if p.is_file() and not p.is_symlink():
                found[f"{label}:{p.relative_to(base).as_posix()}"] = (p, hashlib.sha256(p.read_bytes()).hexdigest())
    return found


def ninja_pending(build, log):
    """The edges Ninja would still run for r3hd (a dry run); [] when the ELF is up to date."""
    rc, text = sh(["cmake", "--build", build, "--target", "r3hd", "--", "-n"], log, check=False)
    need(rc == 0, f"Ninja dry run failed in {build} (exit {rc})")
    return re.findall(r"^\[\d+/\d+\] (.*)$", text, re.M)


def sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def game_rebuild(build, jobs, log):
    """Incremental build of r3hd in an existing game build, forced by content; then the stamp."""
    result = {"build": str(build)}
    inputs = host_inputs(build)
    stamp_path = build / HOST_STAMP
    stamp = json.loads(stamp_path.read_text()) if stamp_path.is_file() else None
    result["baseline"] = stamp is None  # no earlier stamp: only Ninja's timestamps decide this first build
    changed = sorted(k for k, (_, h) in inputs.items() if stamp and stamp["inputs"].get(k) != h)
    elf = build / "r3hd"
    # Newer than every output built from the old content, even an ELF stamped in the future (clock skew); Ninja then
    # rebuilds exactly the dependants of each changed input.
    when = max(time.time_ns(), (elf.stat().st_mtime_ns if elf.is_file() else 0) + 10**9)
    for k in changed:
        os.utime(inputs[k][0], ns=(when, when))
    result["changed_inputs"] = changed
    result["elf_before"] = sha_file(elf) if elf.is_file() else None
    rc, text = sh(["cmake", "--build", build, "--target", "r3hd", "-j", str(jobs)], log, check=False)
    result["build_exit"] = rc
    result["compiled"] = sorted(set(re.findall(r"Building CXX object (\S+)", text)))
    result["linked"] = bool(re.search(r"Linking CXX executable \S*r3hd\b", text))
    result["errors"] = sorted({x.group(0) for x in re.finditer(r"^[^\s:]+:\d+:\d+: (?:fatal )?error: .*$", text,
                                                               re.M)})[:50]
    if rc == 0 and elf.is_file():
        result["pending_after"] = ninja_pending(build, log)
        result["elf_sha256"] = sha_file(elf)
        if not result["pending_after"]:
            stamp_path.write_text(json.dumps({"by": "r3hd_linux_build.py game_rebuild (E-378)",
                                              "elf_sha256": result["elf_sha256"],
                                              "inputs": {k: h for k, (_, h) in inputs.items()}}, indent=1) + "\n")
            result["stamp"] = str(stamp_path)
    return result


def gamesync_passed(g):
    return g.get("build_exit") == 0 and g.get("pending_after") == [] and bool(g.get("stamp"))


def host_input_problems(build, log):
    """Why the r3hd (and staged GPU plugin) of a game build may not match its host inputs ([] = current). Used by
    the package tool."""
    problems = []
    stamp_path = build / HOST_STAMP
    if not stamp_path.is_file():
        return [f"no {HOST_STAMP} in {build}: run `r3hd_linux_build.py gamesync --game-build {build}`"]
    stamp = json.loads(stamp_path.read_text())
    elf = build / "r3hd"
    if not elf.is_file() or sha_file(elf) != stamp.get("elf_sha256"):
        problems.append("bin/r3hd is not the ELF the host-input stamp was written for")
    current = {k: h for k, (_, h) in host_inputs(build).items()}
    diff = sorted(k for k in set(current) | set(stamp.get("inputs", {})) if current.get(k) != stamp["inputs"].get(k))
    if diff:
        problems.append(f"host inputs changed since r3hd was built: {diff[:8]}{' ...' if len(diff) > 8 else ''}")
    pending = ninja_pending(build, log)
    if pending:
        problems.append(f"Ninja would still rebuild r3hd: {pending[:4]}")
    plugins = sorted(game_cache(build)[1].rglob(PLUGIN))
    staged = build / PLUGIN
    if len(plugins) != 1 or not staged.is_file() or sha_file(staged) != sha_file(plugins[0]):
        problems.append(f"staged {PLUGIN} differs from the SDK install's ({len(plugins)} installed)")
    return problems


def gamesync(args):
    """E-378: bring an existing game build's r3hd up to date with its host inputs and write the stamp."""
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = {"status": "INCOMPLETE"}
    try:
        need(platform.system() == "Linux" and platform.machine() == "x86_64", "native Linux x86-64 required")
        result["game"] = game_rebuild(args.game_build.resolve(), args.jobs, out / "gamesync.log")
        result["status"] = "PASS" if gamesync_passed(result["game"]) else "FAIL"
    except Fail as error:
        result["status"], result["error"] = "FAIL", str(error)
    finally:
        (out / "results-gamesync.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    g = result.get("game") or {}
    print(f"R3HD_LINUX_GAMESYNC {result['status']} baseline={g.get('baseline')} changed={len(g.get('changed_inputs') or [])} "
          f"compiled={len(g.get('compiled') or [])} linked={g.get('linked')} pending={len(g.get('pending_after') or [])} "
          f"elf={g.get('elf_sha256')} {result.get('error', '')}")
    return 0 if result["status"] == "PASS" else 1


MODES ={"fixed": None, "pinned": "1"}  # value of R3HD_M5_VB_RESIDENCY_CACHE (None: unset)
# E-374: feature status lines the runtime and host log once (launcher-driven features; one entry per pattern).
FEATURE_LINES = {
    "dualsense": r"R3HD dualsense light=\w+ trigger=\w+[^\n]*",
    "uvs": r"UVS lit_uv_scroll shader=\w+[^\n]*",
    "m23": r"M23 layer_coords pair=\w+[^\n]*",
    "vblank": r"M16 vblank mode=\w+",
    "mods": r"M33 mods=\w+[^\n]*",
    "subtitles": r"M44 [^\n]*",
    "combo": r"ComboClose profile_mode=\w+",
    "sky": r"SkyClearTest mode=\w+",
    "texture_orient": r"M26 texture_orient[^\n]*",
}


def launcher_env(args, game_build, game, run_dir):
    """E-374: the R3HD_* feature variables tools/linux/r3hd_play.py would set for --preset / --set (no launch)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import r3hd_play
    ns = argparse.Namespace(bin=str(game_build), game=str(game), home=str(run_dir / "launcher_home"),
                            profile="default", preset=args.preset, settings=None, set=args.set, key_layout=None,
                            mods="off", license="full", no_keyboard=False, dev_overlay=False, log_level="debug",
                            extra=[], dry_run=True, check=False)
    return {k: v for k, v in r3hd_play.build_plan(ns)["env"].items() if v}

EXPECTED_MODE_LOG = {"fixed": "always_request", "pinned": "pinned_cache"}


def menu_env(mode, base, lib_dir):
    """Equivalent conditions for both modes: no R3HD_/REX_ overrides, no Lossless Scaling layer; only the switch
    differs."""
    env = {k: v for k, v in base.items() if not k.startswith(("R3HD_", "REX_"))}
    env["DISABLE_LSFG"] = "1"
    env["LD_LIBRARY_PATH"] = str(lib_dir)
    if MODES[mode] is not None:
        env["R3HD_M5_VB_RESIDENCY_CACHE"] = MODES[mode]
    return env


def menu_argv(elf, game, run_dir):
    return [str(elf), f"--game_data_root={game}", f"--user_data_root={run_dir / 'user'}",
            f"--cache_root={run_dir / 'cache'}", "--gpu_plugin=xenos", "--fullscreen=false", "--mnk_mode=true",
            "--log_level=debug", f"--log_file={run_dir / 'runtime.log'}", "--log_flush_interval=1"]


def judge_menu_run(mode, run_dir):
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(run_dir.glob("runtime*.log")))
    stderr = (run_dir / "stderr.log").read_text(encoding="utf-8", errors="replace") \
        if (run_dir / "stderr.log").is_file() else ""
    modes = re.findall(r"M5 vb_residency backend=vulkan mode=(\w+)", text)
    buttons = sorted(set(re.findall(r"M5 consumed function=\w+ samples=\d+ controller=\w+ buttons=([0-9A-F]{4})", text)))
    sticks = len(re.findall(r"M5 consumed .* ly=(?!0 )-?\d+", text))
    filters = {}
    for code, disposition in re.findall(r"M4 seh_filter pc=\w+ code=(\w+) filter=\w+ disposition=(-?\d+)", text):
        filters[f"{code}:{disposition}"] = filters.get(f"{code}:{disposition}", 0) + 1
    return {"mode_log": modes, "mode_ok": modes == [EXPECTED_MODE_LOG[mode]],
            "m4_aborts": len(re.findall(r"M4 portable: (?:unsupported|FAIL-FAST)", stderr + text)),
            "banner": "R3HD DIAGNOSTIC BUILD" in stderr or "R3HD LINUX PREVIEW (LM-A)" in stderr,
            "keyboard_mnk": "mnk_mode=true" in text,
            "guest_buttons": buttons, "guest_stick_samples": sticks,
            "presents": text.count("XELOG_GPU PRESENT"),
            # LM-A: real guest exception owners at work (the M4 log records of either backend)
            "m4_filters": filters, "m4_finally": len(re.findall(r"M4 seh_finally ", text)),
            "m4_fail_fast": re.findall(r"M4 portable: FAIL-FAST[^\n]*", stderr)[:5],
            "features": {k: sorted(set(m.strip()[:160] for m in re.findall(v, text)))[:4]
                         for k, v in FEATURE_LINES.items()}}


GUEST_EXIT_LINE = "Execution complete"  # rex_app.cpp: the guest main thread returned (e.g. the menu's Exit Game)


def supervise(p, seconds, exit_watch, log_path, clock=None, sleep=None, capture=None, core_fallback=True):
    """Wait for the run to end; never leave it running.

    Two ways a run is ended for it: the time limit (SIGTERM first: SDL turns it into a window close while its event
    loop runs), or a shutdown hang: the guest thread has exited (`Execution complete`) but the process is still alive
    `exit_watch` seconds later (E-371). On a shutdown hang, or a SIGTERM not honoured within 10 s, the stacks are
    taken while the process is still alive: `capture(pid)` first (a /proc thread snapshot and a GDB backtrace, no core
    file); only if that fails, and `core_fallback` is set, SIGQUIT asks the kernel for a core dump. The process is
    killed only after that."""
    import signal
    import time
    clock, sleep = clock or time.monotonic, sleep or time.sleep
    start, guest_exit_at, rec = clock(), None, {"timed_out": False, "exit_hang": False, "signals": []}

    def wait(limit):
        end = clock() + limit
        while clock() < end:
            if p.poll() is not None:
                return True
            sleep(0.25)
        return p.poll() is not None

    while p.poll() is None:
        now = clock()
        if guest_exit_at is None and log_path.is_file():
            with open(log_path, "rb") as f:
                f.seek(max(0, log_path.stat().st_size - 65536))
                if GUEST_EXIT_LINE.encode() in f.read():
                    guest_exit_at = now
                    rec["guest_exit_after_s"] = round(now - start, 1)
        if guest_exit_at is not None and now - guest_exit_at >= exit_watch:
            rec["exit_hang"] = True
            break
        if now - start >= seconds:
            rec["timed_out"] = True
            p.send_signal(signal.SIGTERM)
            rec["signals"].append("SIGTERM")
            wait(10)
            break
        sleep(0.25)
    if p.poll() is None:
        rec["capture"] = capture(p.pid) if capture else {"ok": False, "reason": "no live capture"}
        if p.poll() is None and not rec["capture"].get("ok") and core_fallback:
            p.send_signal(getattr(signal, "SIGQUIT", 3))  # 3 on Linux; the name is absent on Windows (tests)
            rec["signals"].append("SIGQUIT")
            rec["stack_signal"] = "SIGQUIT"
            wait(90)  # a core dump of a large address space takes time
        if p.poll() is None:
            p.kill()
            rec["signals"].append("SIGKILL")
    rec["exit"] = p.wait()
    rec["elapsed_s"] = round(clock() - start, 1)
    return rec


PR_SET_PTRACER, PR_SET_PTRACER_ANY = 0x59616D61, 0xFFFFFFFFFFFFFFFF


def allow_ptrace():
    """preexec_fn: let a non-ancestor debugger attach to this game process under Yama ptrace_scope 1 (the CachyOS
    default), so a hang can be read live. It changes no game behaviour; with scope 2/3 the attach still fails and the
    capture records it."""
    import ctypes
    try:
        ctypes.CDLL(None, use_errno=True).prctl(PR_SET_PTRACER, ctypes.c_ulong(PR_SET_PTRACER_ANY), 0, 0, 0)
    except Exception:
        pass


def gdb_thread_count(text):
    return len(re.findall(r"^Thread \d+ \(", text, re.M)) if "#0 " in text else 0


def live_capture(pid, run_dir, timeout=180):
    """Stacks of a hung process without a core file: every thread's /proc state and wait channel, then a GDB batch
    backtrace of all threads (attach, print, detach). Network symbol lookups (debuginfod) are off."""
    rec = {"ok": False}
    try:
        rec["ptrace_scope"] = Path("/proc/sys/kernel/yama/ptrace_scope").read_text().strip()
    except OSError:
        rec["ptrace_scope"] = None
    rows = []
    for task in sorted(Path(f"/proc/{pid}/task").glob("*"), key=lambda p: int(p.name)):
        def read(name):
            try:
                return (task / name).read_text(errors="replace").strip()
            except OSError:
                return "?"
        stat = read("stat")
        state = stat.rsplit(")", 1)[-1].split()[0] if ")" in stat else "?"
        rows.append("\t".join((task.name, read("comm"), state, read("wchan"))))
    header = "\t".join(("tid", "comm", "state", "wchan"))
    (run_dir / "proc_threads.txt").write_text("\n".join([header] + rows) + "\n", encoding="utf-8")
    rec["proc_threads"] = len(rows)
    if not shutil.which("gdb"):
        rec["gdb"] = "not installed"
        return rec
    env = dict(os.environ, DEBUGINFOD_URLS="")
    argv = ["gdb", "-nx", "-batch", "-p", str(pid), "-ex", "set pagination off", "-ex", "set debuginfod enabled off",
            "-ex", "info threads", "-ex", "thread apply all bt", "-ex", "detach"]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
        text = p.stdout + "\n--- stderr ---\n" + p.stderr
        rec["gdb_exit"] = p.returncode
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        text = f"gdb timed out after {timeout} s\n{out}"
        rec["gdb_exit"] = "timeout"
    (run_dir / "stacks.log").write_text(text, encoding="utf-8")
    rec["gdb_threads"] = gdb_thread_count(text)
    rec["ok"] = rec["gdb_threads"] > 0
    if not rec["ok"]:
        rec["gdb"] = next((l for l in text.splitlines() if "ptrace" in l.lower() or "not permitted" in l.lower()),
                          "no backtrace in the output")[:300]
    return rec


def capture_stacks(pid, path, attempts=24):
    """All-thread stacks of the core dump (systemd-coredump); text only. The core itself stays in the system store."""
    import time
    if not shutil.which("coredumpctl"):
        path.write_text("coredumpctl not available\n", encoding="utf-8")
        return {"available": False}
    text = ""
    for _ in range(attempts):  # systemd-coredump processes the dump asynchronously
        p = subprocess.run(["coredumpctl", "info", "--no-pager", str(pid)], capture_output=True, text=True)
        text = p.stdout + p.stderr
        if "Stack trace of thread" in text:
            break
        time.sleep(5)
    path.write_text(text, encoding="utf-8")
    return {"available": True, "threads": text.count("Stack trace of thread")}


def menu_run(args):
    """One maintainer-watched, bounded run to the main menu in one D-020 mode. The person drives the game and records
    what they see; this records the conditions, the exit, the logs and the mode the plugin actually used."""
    out = args.out.resolve()
    run_dir = out / (args.name or f"menu_{args.mode}")
    game_build = args.game_build.resolve()
    elf = game_build / "r3hd"
    need(platform.system() == "Linux", "native Linux required")
    need(elf.is_file(), f"no ELF at {elf}")
    elf_bytes = elf.read_bytes()
    elf_sha = hashlib.sha256(elf_bytes).hexdigest()
    if TREE_KINDS["LMA_PORTABLE_M4.txt"][3] in elf_bytes:
        elf_kind = "lma"  # LM-A production tree on the portable backend (built by `game` from an LMA tree)
        need(b"M4 portable: FAIL-FAST" in elf_bytes, f"{elf} lacks the portable M4 backend")
    else:
        elf_kind = "diag"
        need(elf_sha == LM2_ELF_SHA256, f"{elf} is neither the LM-2 ELF nor an LM-A build")
    need(VB_MODE_MARKER in (game_build / PLUGIN).read_bytes(), "the staged GPU plugin lacks the D-020 Vulkan edit (run vbfix)")
    game = args.game.resolve()
    need((game / "default.xex").is_file() or (game / "Default.xex").is_file(), f"no default.xex in {game}")
    need(not (game_build / "r3hd.toml").exists(), "an r3hd.toml beside the ELF would change the conditions")
    shutil.rmtree(run_dir, ignore_errors=True)  # fresh user/cache roots: both modes start from the same state
    (run_dir / "user").mkdir(parents=True)
    (run_dir / "cache").mkdir()
    libs = sorted((SDK / f"out/install/{SDK_PRESET}").rglob("librexruntime.so*"))
    need(libs, "no librexruntime.so in the SDK install")
    lib_dir = libs[0].parent
    env, argv = menu_env(args.mode, os.environ, lib_dir), menu_argv(elf, game, run_dir)
    feature_env = launcher_env(args, game_build, game, run_dir) if (args.preset or args.set) else {}
    env.update(feature_env)
    record = {"mode": args.mode, "argv": argv, "switch": env.get("R3HD_M5_VB_RESIDENCY_CACHE"),
              "env_set": {k: env[k] for k in ("DISABLE_LSFG", "LD_LIBRARY_PATH")},
              "plugin_sha256": hashlib.sha256((game_build / PLUGIN).read_bytes()).hexdigest(),
              "elf_sha256": elf_sha, "elf_kind": elf_kind, "seconds": args.seconds, "launcher_env": feature_env}
    print(f"R3HD_LINUX_MENU_RUN start mode={args.mode} seconds={args.seconds} (close the window when done)", flush=True)
    with open(run_dir / "stdout.log", "wb") as so, open(run_dir / "stderr.log", "wb") as se:
        p = subprocess.Popen(argv, env=env, stdout=so, stderr=se, preexec_fn=allow_ptrace)
        record.update(supervise(p, args.seconds, args.exit_watch, run_dir / "runtime.log",
                                capture=lambda pid: live_capture(pid, run_dir), core_fallback=args.core_fallback))
    if record.get("stack_signal"):  # live capture failed: stacks from the core (the core itself stays in the system)
        core = capture_stacks(p.pid, run_dir / "stacks-core.log")
        record["capture"]["core"] = core
        record["capture"]["ok"] = core.get("threads", 0) > 0
    record["stacks_captured"] = bool((record.get("capture") or {}).get("ok"))
    record.update(judge_menu_run(args.mode, run_dir))
    (run_dir / "run.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(f"R3HD_LINUX_MENU_RUN done mode={args.mode} exit={record['exit']} timed_out={record['timed_out']} "
          f"exit_hang={record['exit_hang']} signals={record['signals']} stacks_captured={record['stacks_captured']} "
          f"mode_log={record['mode_log']} mode_ok={record['mode_ok']} m4_aborts={record['m4_aborts']} "
          f"mnk={record['keyboard_mnk']} buttons={record['guest_buttons']} stick_samples={record['guest_stick_samples']} "
          f"elf_kind={record['elf_kind']} m4_filters={record['m4_filters']} m4_finally={record['m4_finally']}")
    return 0 if record["mode_ok"] and record["m4_aborts"] == 0 else 1


def evidence(args):
    out = args.out.resolve()
    names = sorted(p for p in out.rglob("*") if p.is_file() and p.suffix in (".json", ".log", ".txt") and
                   not any(part in ("build", "user", "cache", "plugin_before") for part in p.relative_to(out).parts))
    need(names, "nothing to package")
    with zipfile.ZipFile(args.zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in names:
            z.write(p, p.relative_to(out).as_posix())
        z.writestr("PRIVATE.txt", "PRIVATE: build logs may name game symbols. Keep under private/work/linux_build/.\n")
    print(f"R3HD_LINUX_EVIDENCE entries={len(names) + 1} path={args.zip}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("doctor")
    d.add_argument("--compilers", nargs="+", default=["clang", "gcc"], choices=sorted(COMPILERS))
    r = sub.add_parser("run")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--compilers", nargs="+", default=["clang", "gcc"], choices=sorted(COMPILERS))
    r.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    r.add_argument("--private-headers", type=Path, help="directory holding generated/default/r3hd_init.h etc.")
    r.add_argument("--lge-private", type=Path, help="the unchanged LGE private_generated directory")
    g = sub.add_parser("game", help="LM-2: link r3hd from the diagnostic tree (no run)")
    g.add_argument("--out", type=Path, required=True)
    g.add_argument("--tree", type=Path, required=True, help="the extracted rex_linux_diag directory")
    g.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    v = sub.add_parser("vbfix", help="D-020 on Vulkan: patch one SDK file, rebuild/stage only the GPU plugin")
    v.add_argument("--out", type=Path, required=True)
    v.add_argument("--game-build", type=Path, default=DEFAULT_GAME_BUILD, help="the LM-2 build/game directory")
    v.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    u = sub.add_parser("sdkupdate", help="LM-A: move the SDK copy to the current patch chain from a verified delta")
    u.add_argument("--out", type=Path, required=True)
    u.add_argument("--delta", type=Path, required=True, help="the extracted lma_sdk_delta directory")
    u.add_argument("--game-build", type=Path,
                   help="also refresh the GPU plugin staged in this r3hd build dir and rebuild r3hd (gamesync)")
    u.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    s = sub.add_parser("gamesync", help="E-378: incremental r3hd build forced by host-input content; writes the stamp")
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--game-build", type=Path, required=True, help="the configured game build (e.g. build/game-lma)")
    s.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    m = sub.add_parser("menu-run", help="one bounded, watched run to the main menu in one D-020 mode")
    m.add_argument("--out", type=Path, required=True)
    m.add_argument("--mode", choices=sorted(MODES), required=True)
    m.add_argument("--game", type=Path, required=True, help="the person's own title directory (default.xex)")
    m.add_argument("--game-build", type=Path, default=DEFAULT_GAME_BUILD,
                   help="directory holding r3hd and the GPU plugin (LM-2 default; an LM-A build/game-lma)")
    m.add_argument("--name", help="run directory name under --out (default menu_<mode>)")
    m.add_argument("--seconds", type=int, default=120)
    m.add_argument("--preset", choices=("vanilla", "hdplus", "custom"),
                   help="E-374: add the feature variables tools/linux/r3hd_play.py sets for this preset")
    m.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                   help="E-374: an explicit launcher setting (with or without --preset)")
    m.add_argument("--exit-watch", type=int, default=15,
                   help="seconds the process may outlive the guest's own exit before stacks are captured (E-371)")
    m.add_argument("--no-core-fallback", dest="core_fallback", action="store_false",
                   help="if the live GDB capture fails, kill without asking for a core dump")
    h = sub.add_parser("hostupdate", help="LX-4: update the LM-A tree's prepared host sources (verified)")
    h.add_argument("--tree", type=Path, required=True, help="the extracted rex_lma directory")
    e = sub.add_parser("evidence")
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--zip", type=Path, required=True)
    args = ap.parse_args()
    try:
        if args.cmd == "doctor":
            print(json.dumps(doctor(args.compilers), indent=1))
            return 0
        return {"run": run, "game": game, "vbfix": vbfix, "sdkupdate": sdkupdate, "menu-run": menu_run,
                "evidence": evidence, "hostupdate": hostupdate, "gamesync": gamesync}[args.cmd](args)
    except Fail as error:
        print(f"R3HD_LINUX_BUILD FAIL {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
