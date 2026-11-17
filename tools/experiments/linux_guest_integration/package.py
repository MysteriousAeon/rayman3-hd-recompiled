"""Create and re-open an allowlisted, source-only local CachyOS transfer ZIP."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIRECTORIES = ("portable_guest_eh", "linux_guest_fault", "linux_guest_integration")
SUFFIXES = {".cpp", ".h", ".c", ".S", ".py", ".md", ".cmake"}
REPORTS = ("PORTABLE_GUEST_EXCEPTIONS_2026-11.md", "PORTABLE_GUEST_EMITTER_2026-11.md",
           "LINUX_GUEST_FAULT_2026-11.md", "LINUX_GUEST_INTEGRATION_2026-11.md")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "private/work/linux_guest_integration/cachyos-source.zip")
    args = parser.parse_args()
    entries = {}
    for directory in DIRECTORIES:
        for path in sorted((HERE.parent / directory).iterdir()):
            if path.is_file() and (path.suffix in SUFFIXES or path.name == "CMakeLists.txt"):
                entries[path.relative_to(ROOT).as_posix()] = path.read_bytes().replace(b"\r\n", b"\n")
    for report in REPORTS:
        path = ROOT / "reports" / report
        entries[path.relative_to(ROOT).as_posix()] = path.read_bytes().replace(b"\r\n", b"\n")
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(entries.items())}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            archive.writestr(name, data)
        archive.writestr("SOURCE_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    with zipfile.ZipFile(args.out) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(entries) + 1:
            raise RuntimeError("ZIP integrity or inventory mismatch")
        if set(archive.namelist()) != set(entries) | {"SOURCE_MANIFEST.json"}:
            raise RuntimeError("unexpected ZIP path")
        for name, expected in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise RuntimeError(f"hash mismatch: {name}")
    summary = {"status": "PASS", "files": len(entries), "zip": str(args.out.resolve()),
               "sha256": hashlib.sha256(args.out.read_bytes()).hexdigest(),
               "content": "allowlisted experiment source and reports; no SDK/data/binaries"}
    args.out.with_suffix(".verification.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
