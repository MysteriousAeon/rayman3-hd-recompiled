"""Create and reopen a source-only, hash-verified local CachyOS transfer ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NEW_FILES = ("transport.h", "transport.c", "access.S", "lifecycle.c", "run_lifecycle.py",
             "LIFECYCLE.md", "sdk_composition.cpp", "CMakeLists.txt", "run.py",
             "package.py", "README.md")
REPORTS = ("PORTABLE_GUEST_EXCEPTIONS_2026-11.md", "PORTABLE_GUEST_EMITTER_2026-11.md",
           "LINUX_GUEST_FAULT_2026-11.md", "LINUX_GUEST_INTEGRATION_2026-11.md",
           "LINUX_SDK_COMPOSITION_2026-11.md")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "private/work/linux_sdk_composition/cachyos-source.zip")
    args = ap.parse_args()
    entries = {}
    prior = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "--",
        "tools/experiments/portable_guest_eh", "tools/experiments/linux_guest_fault",
        "tools/experiments/linux_guest_integration"], text=True).splitlines()
    paths = [ROOT / name for name in prior] + [HERE / name for name in NEW_FILES]
    paths += [ROOT / "reports" / name for name in REPORTS]
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"missing or linked source: {path}")
        if path.suffix not in (".cpp", ".h", ".c", ".S", ".py", ".md") and path.name != "CMakeLists.txt":
            raise RuntimeError(f"non-source path: {path}")
        name = path.relative_to(ROOT).as_posix()
        entries[name] = path.read_bytes().replace(b"\r\n", b"\n")
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(entries.items())}
    entries["SOURCE_MANIFEST.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(entries.items()):
            z.writestr(name, data)
    with zipfile.ZipFile(args.out) as z:
        if z.testzip() or len(z.namelist()) != len(entries) or set(z.namelist()) != set(entries):
            raise RuntimeError("ZIP inventory/integrity mismatch")
        for name, data in entries.items():
            if z.read(name) != data:
                raise RuntimeError(f"ZIP content mismatch: {name}")
    result = {"status": "PASS", "source_files": len(manifest), "zip": str(args.out.resolve()),
              "sha256": hashlib.sha256(args.out.read_bytes()).hexdigest(),
              "scope": "experiment source and reports only; no SDK/data/binaries"}
    args.out.with_suffix(".verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
