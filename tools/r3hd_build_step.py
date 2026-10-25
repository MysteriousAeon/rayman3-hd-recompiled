#!/usr/bin/env python3
"""M28 (D-062): the build's post-codegen check, in developer or user mode.

  audit             called by build_milestone8.bat after `rexglue codegen`.
                    Developer mode (default): runs the M3 target audit (tools/m3_target_audit.py), which reads the
                    decrypted image and PE analysis written by the M1 developer steps (private/work/default_image.bin,
                    private/work/pe_analysis.json), then reports whether the generated code equals the pinned
                    digest (report only: a config change legitimately changes it).
                    User mode (R3HD_BUILD_MODE=user): the developer inputs are not needed and not read. The
                    configuration is the pinned one, so the audit's result is already the tracked
                    reports/milestone4/target_audit.json; instead the generated code must equal the digest pinned
                    in config/build/toolchain.json ("codegen"), i.e. the code the developer audit and every
                    regression ran on. A difference stops the build (CODEGEN_DIFFERENT).
  digest [--json]   print the digest of the generated tree.
  selftest          synthetic checks of the digest rules.

Digest: SHA-256 over the sorted r3hd_*.h / r3hd_*.cpp files of generated/default (name, SHA-256 of the content
with CRLF -> LF), with the M2 instrumentation block that the build appends to r3hd_pch.h removed. codegen.d
(absolute paths) and stamps are excluded. Only hashes are recorded; generated code is never tracked.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "build" / "toolchain.json"
GENERATED = ROOT / "private/work/rex/generated/default"
MARKER = b"// M2 observational instrumentation"
NAME = re.compile(r"r3hd_[A-Za-z0-9_.]+\.(h|cpp)")
AUDIT_ARGS = ["private/work/rex/generated/default", "private/work/default_image.bin", "private/work/pe_analysis.json",
              "reports/milestone3/data/eh_map.json", "reports/milestone4/target_audit.json"]


sys.path.insert(0, str(ROOT / "tools"))
from m5_prepare import M5_BLOCK  # noqa: E402  (its build actions run only under __main__)

PARTITIONED = re.compile(r"r3hd_(recomp|funcs)\.\d+\.(cpp|h)")


def digest(gen: Path) -> tuple:
    """Partition-independent digest of the generated code (E-151).

    Codegen spreads the functions over numbered partitions, and the assignment is persisted in
    codegen.partition.json: a work tree that grew over many configurations keeps its old assignment, a fresh one
    computes another (45,197 of 45,858 functions placed differently, same code). So the numbered files are not
    hashed as files: every DEFINE_REX_FUNC block (through its closing brace at column 0) is hashed under its name
    (without the M5 input-trace block the build inserts after codegen, like the M2 block of r3hd_pch.h),
    the remaining file-scope lines (helper declarations that codegen repeats in each partition that needs them)
    and the partition headers' declaration lines count as sets, and preprocessor lines are left out. The
    unpartitioned files (r3hd_init.*, r3hd_funcs.h, r3hd_pch.h without the M2 block) are hashed whole.
    """
    files, functions, scope, decls = 0, {}, set(), set()
    whole = hashlib.sha256()
    for p in sorted(gen.iterdir(), key=lambda p: p.name):
        if not p.is_file() or not NAME.fullmatch(p.name):
            continue
        files += 1
        data = p.read_bytes().replace(b"\r\n", b"\n")
        if p.name == "r3hd_pch.h":
            data = data.split(MARKER)[0]
        if not PARTITIONED.fullmatch(p.name):
            whole.update(p.name.encode() + b"\0" + hashlib.sha256(data).digest())
            continue
        text = data.decode("utf-8", "replace")
        if p.name.startswith("r3hd_recomp."):
            text = text.replace(M5_BLOCK, "")  # inserted by the build's m5_instrument step after codegen
        lines = text.split("\n")
        if p.name.startswith("r3hd_funcs."):
            decls.update(l.strip() for l in lines if l.strip() and not l.startswith("#"))
            continue
        block = None
        for line in lines:
            if block is None:
                m = re.match(r"DEFINE_REX_FUNC\((\w+)\)", line)
                if m:
                    name, block = m.group(1), [line]
                elif line.strip() and not line.startswith("#"):
                    scope.add(line.rstrip())
            else:
                block.append(line)
                if line == "}":
                    if name in functions:
                        raise ValueError(f"function {name} defined twice")
                    functions[name] = hashlib.sha256("\n".join(block).encode()).hexdigest()
                    block = None
        if block is not None:
            raise ValueError(f"unterminated function {name} in {p.name}")
    h = hashlib.sha256(whole.digest())
    for name in sorted(functions):
        h.update(name.encode() + b"\0" + bytes.fromhex(functions[name]))
    for group in (scope, decls):
        h.update(b"\1" + hashlib.sha256("\n".join(sorted(group)).encode()).digest())
    return files, h.hexdigest()


def audit() -> int:
    mode = os.environ.get("R3HD_BUILD_MODE", "developer").lower()
    if mode not in ("developer", "user"):
        print(f"R3HD_BUILD_STEP FAIL unknown R3HD_BUILD_MODE={mode} (developer or user)")
        return 1
    want = json.loads(MANIFEST.read_text(encoding="utf-8"))["codegen"]
    if not GENERATED.is_dir():
        print(f"R3HD_BUILD_STEP FAIL no generated code at {GENERATED.relative_to(ROOT)}")
        return 1
    n, d = digest(GENERATED)
    same = (n, d) == (want["files"], want["digest"])
    if mode == "developer":
        missing = [a for a in AUDIT_ARGS[1:3] if not (ROOT / a).is_file()]
        if missing:
            print(f"R3HD_BUILD_STEP FAIL developer audit inputs missing: {', '.join(missing)} "
                  "(written by the M1 developer steps); a build from the pinned configuration sets R3HD_BUILD_MODE=user")
            return 1
        r = subprocess.run([sys.executable, str(ROOT / "tools/m3_target_audit.py"), *AUDIT_ARGS], cwd=ROOT)
        if r.returncode != 0:
            return r.returncode
        print(f"R3HD_BUILD_STEP audit=developer codegen={'pinned' if same else 'CHANGED'} files={n} digest={d}")
        if not same:
            print("  (developer mode reports only; after a deliberate config change record the new digest in "
                  "config/build/toolchain.json \"codegen\" so user builds accept it)")
        return 0
    if not same:
        print(f"R3HD_BUILD_STEP FAIL CODEGEN_DIFFERENT files={n} digest={d} expected files={want['files']} "
              f"digest={want['digest']}")
        return 1
    print(f"R3HD_BUILD_STEP audit=user (developer target audit not run; its inputs are not needed) codegen=pinned "
          f"files={n} digest={d}")
    return 0


def selftest() -> int:
    checks = []
    with tempfile.TemporaryDirectory(prefix="r3hd_step_") as t:
        g = Path(t)
        fa = "DEFINE_REX_FUNC(sub_1) {\n\tx = 1;\n\t__restgprlr_22(ctx, base);\n}\n"
        fb = "DEFINE_REX_FUNC(sub_2) {\n\ty = 2;\n}\n"
        helper = "extern void Helper(int);\n"

        def tree(parts, pch=b"p\n"):
            for old in g.glob("r3hd_*"):
                old.unlink()
            for i, text in enumerate(parts):
                (g / f"r3hd_recomp.{i}.cpp").write_bytes(text.encode())
                (g / f"r3hd_funcs.{i}.h").write_bytes(b"#pragma once\nDECLARE_REX_FUNC(sub_1);\n")
            (g / "r3hd_pch.h").write_bytes(pch)
            return digest(g)

        base = tree(['#include "r3hd_funcs.0.h"\n' + helper + fa + fb])
        checks.append(("files counted", base[0] == 3))
        (g / "codegen.d").write_bytes(b"C:/somewhere\n")
        checks.append(("dependency file ignored", digest(g) == base))
        checks.append(("pch instrumentation block ignored", tree(['#include "r3hd_funcs.0.h"\n' + helper + fa + fb],
                       b"p\n" + MARKER + b"\n#include x\n")[1] == base[1]))
        checks.append(("line endings ignored", tree([('#include "r3hd_funcs.0.h"\n' + helper + fa + fb).replace("\n", "\r\n")])[1] == base[1]))
        checks.append(("functions moved between partitions, helper repeated: same digest",
                       tree(['#include "r3hd_funcs.0.h"\n' + fb, '#include "r3hd_funcs.1.h"\n' + helper + fa + helper])[1] == base[1]))
        m5 = fa.replace("\t__restgprlr_22", M5_BLOCK + "\t__restgprlr_22")
        checks.append(("M5 input-trace block ignored", tree([helper + m5 + fb])[1] == base[1]))
        checks.append(("function body change detected", tree([helper + fa.replace("x = 1", "x = 3") + fb])[1] != base[1]))
        checks.append(("added function detected", tree([helper + fa + fb + "DEFINE_REX_FUNC(sub_3) {\n}\n"])[1] != base[1]))
        checks.append(("file-scope change detected", tree([helper.replace("int", "long") + fa + fb])[1] != base[1]))
        try:
            tree([fa + fa])
            checks.append(("duplicate function refused", False))
        except ValueError:
            checks.append(("duplicate function refused", True))
    want = json.loads(MANIFEST.read_text(encoding="utf-8")).get("codegen", {})
    checks.append(("manifest pins a codegen digest", re.fullmatch(r"[0-9a-f]{64}", want.get("digest", "")) is not None))
    for name, ok in checks:
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
    failed = sum(not ok for _, ok in checks)
    print(f"R3HD_BUILD_STEP_SELFTEST {'PASS' if not failed else 'FAIL'} checks={len(checks)}")
    return 0 if not failed else 1


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "audit":
        return audit()
    if cmd == "digest":
        n, d = digest(Path(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else GENERATED)
        print(json.dumps({"files": n, "digest": d}) if "--json" in sys.argv else f"files={n} digest={d}")
        return 0
    if cmd == "selftest":
        return selftest()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
