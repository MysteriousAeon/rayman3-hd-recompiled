#!/usr/bin/env python3
"""LM-A: package the PRODUCTION generated tree (macro emission, M2/M5 instrumented, as the Windows build uses it) for
the Linux r3hd built on the portable M4 backend (PRIVATE: game-derived code; maintainer transfer only).

    python tools/linux/r3hd_lma_tree.py package --zip private/work/linux_build/lma-private-tree.zip

Contents, under rex_lma/: generated/default (r3hd_*.h, r3hd_*.cpp, sources.cmake), the prepared host sources src/,
m4_generated_test.cpp (the five functions tools/m4_validate_emission.py extracts for tools/m4_real_owner_test.py),
the Windows reference results of the two backend differentials (windows_reference/),
the marker LMA_PORTABLE_M4.txt, lma_manifest.json (format, codegen digest, per-file SHA-256) and PRIVATE_MANIFEST.json.
The tree must equal the pinned codegen digest (config/build/toolchain.json); nothing is regenerated here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "private/work/rex"
GEN = WORK / "generated/default"
NAME = re.compile(r"r3hd_[A-Za-z0-9_.]+\.(h|cpp)$")
MARKER = ("LM-A PRODUCTION TREE for the Linux r3hd on the portable M4 backend (tools/m4_seh_portable.h).\n"
          "Hardware-fault conversion is not implemented (D2); full M4 equivalence is not claimed. Not a release.\n")
sha = lambda b: hashlib.sha256(b).hexdigest()


def package(zip_path):
    sys.path.insert(0, str(ROOT / "tools"))
    import r3hd_build_step
    files, digest = r3hd_build_step.digest(GEN)
    pinned = json.loads((ROOT / "config/build/toolchain.json").read_text(encoding="utf-8"))["codegen"]
    if (files, digest) != (pinned["files"], pinned["digest"]):
        raise SystemExit(f"generated tree {digest} ({files}) is not the pinned codegen {pinned['digest']}")
    entries = {}
    for p in sorted(GEN.iterdir()):
        if NAME.match(p.name) or p.name == "sources.cmake":
            entries[f"generated/default/{p.name}"] = p.read_bytes()
    for p in sorted((WORK / "src").iterdir()):
        if p.is_file():
            entries[f"src/{p.name}"] = p.read_bytes()
    entries["m4_generated_test.cpp"] = (WORK / "m4_generated_test.cpp").read_bytes()
    # Windows reference results of the backend differentials, for --compare on the native host (traces only).
    for name, path in (("m4_portable-results-windows.json", "private/work/m4_portable/results-windows.json"),
                       ("m4_real-results-windows.json", "private/work/m4_real/results-windows.json")):
        entries[f"windows_reference/{name}"] = (ROOT / path).read_bytes()
    entries["LMA_PORTABLE_M4.txt"] = MARKER.encode()
    manifest = {"format": "R3HD_LMA_TREE_V1", "codegen": {"files": files, "digest": digest},
                "generated_sha256": {n.split("/", 2)[2]: sha(b) for n, b in entries.items()
                                     if n.startswith("generated/")},
                "src_sha256": {n[4:]: sha(b) for n, b in entries.items() if n.startswith("src/")},
                "m4_generated_test_sha256": sha(entries["m4_generated_test.cpp"])}
    entries["lma_manifest.json"] = (json.dumps(manifest, indent=1) + "\n").encode()
    entries["PRIVATE_MANIFEST.json"] = (json.dumps({n: sha(b) for n, b in sorted(entries.items())}, indent=1)
                                        + "\n").encode()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in sorted(entries):
            info = zipfile.ZipInfo(f"rex_lma/{n}", date_time=(2026, 11, 7, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, entries[n])
    data = Path(zip_path).read_bytes()
    print(f"R3HD_LMA_TREE package entries={len(entries)} codegen={digest} size={len(data)} sha256={sha(data)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("package")
    p.add_argument("--zip", type=Path, required=True)
    args = ap.parse_args()
    package(args.zip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
