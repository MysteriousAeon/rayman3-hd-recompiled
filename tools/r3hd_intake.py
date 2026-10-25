#!/usr/bin/env python3
"""M27 (D-059): identify, validate and extract a person's own Rayman 3 HD (Xbox 360) data.

Read-only on the input. Standard library only; no key, no network, no download. A package is accepted only when
its header identity matches `config/intake/known_releases.json` (content ID recomputed from the header, title,
content type, media ID, version); an extracted tree only when every file matches the release's tracked manifest
(path, size, SHA-256) with nothing missing and nothing extra. Extraction happens only after the identity check,
into a new directory, and is judged against the same manifest before it is renamed into place.

usage:
  r3hd_intake.py identify INPUT [--json]          INPUT = package file, extracted tree, or a folder to search
  r3hd_intake.py verify TREE [--json]             TREE  = extracted content (Default.xex at its root)
  r3hd_intake.py extract PACKAGE OUT [--json]     OUT   = new directory: OUT/content + OUT/intake.json
  r3hd_intake.py selftest                          synthetic cases only (no game data needed)

Exit codes: 0 supported / done, 2 refused (reason printed), 1 usage or internal error.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASES = ROOT / "config" / "intake" / "known_releases.json"
TOOL_VERSION = 1
XCONTENT_MAGICS = (b"LIVE", b"PIRS", b"CON ")
HEADER_READ = 0x10000
SEARCH_DEPTH = 8


class Refused(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def load_releases(path: Path = RELEASES) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        raise Refused("RELEASE_TABLE_SCHEMA", f"{path} has schema {data.get('schema')!r}, this tool reads 1")
    return data["releases"]


# --- package header --------------------------------------------------------------------------------------------

def read_header(path: Path) -> dict:
    """Header fields of an XContent package; Refused if it is not one or is damaged."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            h = f.read(HEADER_READ)
    except OSError as e:
        raise Refused("UNREADABLE", str(e))
    if h[:4] not in XCONTENT_MAGICS:
        raise Refused("NOT_XCONTENT", "the file is not an Xbox 360 content package (no LIVE / PIRS / CON magic)")
    if len(h) < 0x971A:
        raise Refused("TRUNCATED", f"the header is incomplete ({len(h)} bytes)")
    be32 = lambda o: struct.unpack_from(">I", h, o)[0]
    header_size = be32(0x340)
    aligned = (header_size + 0xFFF) & ~0xFFF
    if not 0x971A <= header_size <= HEADER_READ or aligned > len(h):
        raise Refused("CORRUPT_HEADER", f"implausible header size {header_size:#x}")
    vd = h[0x379:0x379 + 0x24]
    fields = {
        "magic": h[:4].decode("ascii"),
        "content_type": f"{be32(0x344):08X}",
        "media_id": f"{be32(0x354):08X}",
        "version_raw": f"{be32(0x358):08X}",
        "base_version_raw": f"{be32(0x35C):08X}",
        "title_id": f"{be32(0x360):08X}",
        "volume_type": be32(0x3A9),
        "read_only": bool(vd[2] & 1),
        "top_hash_table_hash": vd[8:28].hex(),
        "total_allocated_blocks": struct.unpack(">I", vd[28:32])[0],
        "content_id": h[0x32C:0x340].hex().upper(),
        "header_hash_ok": hashlib.sha1(h[0x344:aligned]).digest() == h[0x32C:0x340],
        "size": size,
        "display_name": h[0x411:0x411 + 0x80].decode("utf-16-be", "replace").split("\0")[0],
    }
    return fields


def identify_package(path: Path, releases: list) -> dict:
    f = read_header(path)
    if not f["header_hash_ok"]:
        raise Refused("CORRUPT_HEADER", "the header's content ID does not match its contents (damaged or edited)")
    titles = {r["package"]["title_id"] for r in releases}
    if f["title_id"] not in titles:
        raise Refused("UNSUPPORTED_TITLE", f"title ID {f['title_id']} is not Rayman 3 HD ({', '.join(sorted(titles))})")
    for r in releases:
        p = r["package"]
        if f["content_id"] != p["content_id"]:
            continue
        for key in ("magic", "content_type", "title_id", "media_id", "version_raw", "base_version_raw",
                    "top_hash_table_hash", "total_allocated_blocks"):
            if f[key] != p[key]:
                raise Refused("CORRUPT_HEADER", f"content ID matches {r['id']} but {key} differs")
        if f["volume_type"] != 0 or not f["read_only"]:
            raise Refused("CORRUPT_HEADER", "content ID matches but the volume is not read-only STFS")
        need = p["total_allocated_blocks"] * 0x1000
        if f["size"] < need:
            raise Refused("TRUNCATED", f"the package is {f['size']} bytes, its volume needs more than {need}")
        return {"kind": "package", "release": r["id"], "fields": f}
    if f["content_type"] != "000D0000":
        raise Refused("UNSUPPORTED_CONTENT", f"content type {f['content_type']} is not the game package (000D0000); "
                      "title updates, saves and other downloads are not accepted")
    raise Refused("UNSUPPORTED_VERSION", f"Rayman 3 HD package with content ID {f['content_id']} (version "
                  f"{f['version_raw']}): not a release this build was translated from")


# --- extracted tree --------------------------------------------------------------------------------------------

def load_manifest(release: dict) -> dict:
    m = ROOT / release["content"]["manifest"]
    # M28: a fresh clone with Git's default core.autocrlf=true checks the manifest out with CRLF; the recorded hash
    # is of the LF form (found by the clean-workspace build, E-151), so line endings are normalised first.
    raw = m.read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(raw).hexdigest() != release["content"]["manifest_sha256"]:
        raise Refused("MANIFEST_CHANGED", f"{m} does not have the hash recorded for {release['id']}")
    rows = {}
    for line in raw.decode("utf-8").splitlines():
        path, size, sha = line.split("\t")
        rows[path] = (int(size), sha)
    return rows


def sha256_file(path: Path, progress=None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            if progress is not None:
                progress.add(len(chunk))
    return h.hexdigest()


def verify_tree(tree: Path, release: dict, manifest: dict = None, progress=None, phase="verify") -> dict:
    """progress (M31, optional): an object with begin(phase) and add(bytes, files=0) -- the installer engine's
    progress report; it may raise to stop (the installer's cancellation), which leaves nothing behind here."""
    manifest = manifest if manifest is not None else load_manifest(release)
    if not tree.is_dir():
        raise Refused("NOT_A_DIRECTORY", str(tree))
    if progress is not None:
        progress.begin(phase)
    present = {p.relative_to(tree).as_posix(): p for p in tree.rglob("*") if p.is_file()}
    missing = sorted(set(manifest) - set(present))
    extra = sorted(set(present) - set(manifest))
    wrong_size, wrong_hash = [], []
    for rel in sorted(set(manifest) & set(present)):
        size, sha = manifest[rel]
        if present[rel].stat().st_size != size:
            wrong_size.append(rel)
        elif sha256_file(present[rel], progress) != sha:
            wrong_hash.append(rel)
        if progress is not None:
            progress.add(0, files=1)
    result = {"kind": "tree", "release": release["id"], "files": len(present), "missing": missing, "extra": extra,
              "wrong_size": wrong_size, "wrong_hash": wrong_hash}
    if missing or extra or wrong_size or wrong_hash:
        def few(xs):
            return ", ".join(xs[:5]) + (f" (+{len(xs) - 5})" if len(xs) > 5 else "")
        parts = [f"{n} {name}: {few(xs)}" for name, xs, n in
                 (("missing", missing, len(missing)), ("extra", extra, len(extra)),
                  ("size differs", wrong_size, len(wrong_size)), ("content differs", wrong_hash, len(wrong_hash))) if xs]
        e = Refused("TREE_MISMATCH", "; ".join(parts))
        e.result = result
        raise e
    return result


# --- input discovery -------------------------------------------------------------------------------------------

def candidates(folder: Path) -> list:
    """Files under `folder` (bounded depth) that start with an XContent magic and name title 5841123F."""
    found = []
    base = len(folder.parts)
    for dirpath, dirnames, filenames in os.walk(folder):
        if len(Path(dirpath).parts) - base >= SEARCH_DEPTH:
            dirnames[:] = []
        for name in filenames:
            p = Path(dirpath) / name
            try:
                with open(p, "rb") as f:
                    h = f.read(0x364)
            except OSError:
                continue
            if len(h) == 0x364 and h[:4] in XCONTENT_MAGICS and h[0x360:0x364] == bytes.fromhex("5841123F"):
                found.append(p)
    return sorted(found)


def identify(path: Path, releases: list) -> dict:
    if path.is_file():
        return identify_package(path, releases)
    if (path / "Default.xex").is_file():
        last = None
        for r in releases:
            try:
                return verify_tree(path, r)
            except Refused as e:
                last = e
        raise last
    if path.is_dir():
        found = candidates(path)
        if not found:
            raise Refused("NOTHING_FOUND", f"no Rayman 3 HD package (title 5841123F) and no extracted tree under {path}")
        results, refusals = [], []
        for p in found:
            try:
                results.append(dict(identify_package(p, releases), path=str(p)))
            except Refused as e:
                refusals.append({"path": str(p), "code": e.code, "detail": e.detail})
        if len(results) != 1:
            detail = (f"{len(results)} supported packages found; give the file itself" if results
                      else "; ".join(f"{r['path']}: {r['code']}" for r in refusals))
            e = Refused("AMBIGUOUS" if results else refusals[0]["code"], detail)
            e.result = {"supported": results, "refused": refusals}
            raise e
        return dict(results[0], refused_others=refusals)
    raise Refused("UNREADABLE", f"{path} does not exist")


# --- extraction ------------------------------------------------------------------------------------------------

def safe_parts(path: str) -> list:
    parts = path.split("/")
    for p in parts:
        if (not p or p in (".", "..") or any(c in p for c in '\\:*?"<>|') or any(ord(c) < 32 for c in p)
                or p.rstrip(" .") != p):
            raise Refused("UNSAFE_PATH", f"package entry {path!r} is not a plain relative path")
    return parts


def is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def extract(package: Path, out: Path, releases: list, progress=None) -> dict:
    ident = identify_package(package, releases)
    release = next(r for r in releases if r["id"] == ident["release"])
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise Refused("OUTPUT_EXISTS", f"{out} exists and is not an empty directory; nothing is overwritten")
    if is_within(out, package.parent):
        # Never write beside or inside the person's source folder (a console dump tree or a USB drive).
        raise Refused("OUTPUT_IN_SOURCE", f"{out} is inside the folder that holds the package")
    if not out.parent.is_dir():
        raise Refused("OUTPUT_PARENT_MISSING", f"{out.parent} does not exist; nothing is created above the output")
    stale = sorted(out.parent.glob(f"{out.name}.partial-*"))
    if stale:
        raise Refused("OUTPUT_EXISTS", f"{stale[0]} is left from an earlier extraction; remove it first")
    manifest = load_manifest(release)
    before = package.stat()
    staging = out.parent / f"{out.name}.partial-{os.getpid()}"
    content = staging / "content"
    content.mkdir(parents=True)
    sys.path.insert(0, str(ROOT / "tools"))
    from stfs_extract import Stfs  # the project's reviewed reader (per-block SHA-1 checks)
    started = time.time()
    try:
        try:
            s = Stfs(str(package))
            entries = s.entries()
        except SystemExit as e:
            raise Refused("CORRUPT_PACKAGE", str(e))
        files = 0
        if progress is not None:
            progress.begin("extract")
        for e in entries:
            parts = safe_parts(e["path"])
            dst = content.joinpath(*parts)
            if e["dir"]:
                dst.mkdir(parents=True, exist_ok=True)
                continue
            if e["path"] not in manifest:
                raise Refused("TREE_MISMATCH", f"the package holds {e['path']!r}, which the release does not")
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                with open(dst, "wb") as o:
                    for chunk in s.file_blocks(e):
                        o.write(chunk)
                        if progress is not None:
                            progress.add(len(chunk))
            except SystemExit as x:
                raise Refused("CORRUPT_PACKAGE", f"{e['path']}: {x}")
            files += 1
            if progress is not None:
                progress.add(0, files=1)
        s.f.close()
        verified = verify_tree(content, release, manifest, progress)
        after = package.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise Refused("SOURCE_CHANGED", "the package changed while it was read")
        record = {
            "tool": "r3hd_intake.py", "tool_version": TOOL_VERSION, "release": release["id"],
            "source": {"path": str(package.resolve()), "size": before.st_size, "content_id": ident["fields"]["content_id"],
                       "header_hash_ok": True, "modified_ns": before.st_mtime_ns},
            "content": {"directory": "content", "files": verified["files"], "manifest_sha256": release["content"]["manifest_sha256"],
                        "executable_sha256": release["executable"]["sha256"]},
            "seconds": round(time.time() - started, 1),
            "note": "Generated locally from the person's own package. Game data: never redistribute this directory.",
        }
        (staging / "intake.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        if out.exists():
            out.rmdir()
        staging.rename(out)
        return record
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


# --- selftest (synthetic, no game data) ------------------------------------------------------------------------

def _fake_header(title="5841123F", ctype=0x000D0000, version=1, magic=b"LIVE", damage=False) -> bytearray:
    h = bytearray(0xB000)
    h[:4] = magic
    struct.pack_into(">I", h, 0x340, 0xAD0E)
    struct.pack_into(">II", h, 0x344, ctype, 2)
    struct.pack_into(">III", h, 0x354, 0x12345678, version, version)
    h[0x360:0x364] = bytes.fromhex(title)
    h[0x379 + 2] = 1
    h[0x32C:0x340] = hashlib.sha1(h[0x344:0xB000]).digest()
    if damage:
        h[0x400] ^= 1
    return h


def selftest() -> int:
    checks = failures = 0

    def check(cond, label):
        nonlocal checks, failures
        checks += 1
        if not cond:
            failures += 1
            print("FAIL", label)

    def refused(fn, code):
        try:
            fn()
        except Refused as e:
            return e.code == code
        return False

    releases = load_releases()
    check(len(releases) == 1 and releases[0]["package"]["title_id"] == "5841123F", "release table: one release")
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        cases = {
            "not_xcontent.bin": (b"MZ" + bytes(0xB000), "NOT_XCONTENT"),
            "truncated.bin": (bytes(_fake_header())[:0x900], "TRUNCATED"),
            "other_title.bin": (bytes(_fake_header(title="4D5307E6")), "UNSUPPORTED_TITLE"),
            "other_version.bin": (bytes(_fake_header(version=2)), "UNSUPPORTED_VERSION"),
            "title_update.bin": (bytes(_fake_header(ctype=0x000B0000)), "UNSUPPORTED_CONTENT"),
            "damaged.bin": (bytes(_fake_header(damage=True)), "CORRUPT_HEADER"),
        }
        for name, (data, code) in cases.items():
            (t / name).write_bytes(data)
            check(refused(lambda: identify(t / name, releases), code), f"package {name} -> {code}")
        # A header that claims the known content ID but whose own hash disagrees is damaged, never accepted.
        forged = _fake_header()
        forged[0x32C:0x340] = bytes.fromhex(releases[0]["package"]["content_id"])
        (t / "forged.bin").write_bytes(bytes(forged))
        check(refused(lambda: identify(t / "forged.bin", releases), "CORRUPT_HEADER"), "forged content ID -> CORRUPT_HEADER")
        # Folder search: finds packages by header, refuses when none is supported, reports nothing found.
        dump = t / "dump" / "Content" / "0000000000000000" / "5841123F" / "000D0000"
        dump.mkdir(parents=True)
        (dump / "AAAA").write_bytes(bytes(_fake_header(version=2)))
        check(refused(lambda: identify(t / "dump", releases), "UNSUPPORTED_VERSION"), "folder with an unsupported package")
        (t / "empty").mkdir()
        check(refused(lambda: identify(t / "empty", releases), "NOTHING_FOUND"), "empty folder -> NOTHING_FOUND")
        check(refused(lambda: identify(t / "missing", releases), "UNREADABLE"), "missing path -> UNREADABLE")
        # Tree verification against a synthetic manifest.
        tree = t / "tree"
        (tree / "GAMEDATAbin").mkdir(parents=True)
        (tree / "Default.xex").write_bytes(b"xex")
        (tree / "GAMEDATAbin" / "a.bhf").write_bytes(b"abc")
        man = {"Default.xex": (3, hashlib.sha256(b"xex").hexdigest()),
               "GAMEDATAbin/a.bhf": (3, hashlib.sha256(b"abc").hexdigest())}
        fake = dict(releases[0], id="synthetic")
        check(verify_tree(tree, fake, man)["files"] == 2, "tree: exact match accepted")
        (tree / "extra.txt").write_bytes(b"x")
        check(refused(lambda: verify_tree(tree, fake, man), "TREE_MISMATCH"), "tree: extra file refused")
        (tree / "extra.txt").unlink()
        (tree / "GAMEDATAbin" / "a.bhf").write_bytes(b"abd")
        check(refused(lambda: verify_tree(tree, fake, man), "TREE_MISMATCH"), "tree: changed content refused")
        (tree / "GAMEDATAbin" / "a.bhf").write_bytes(b"abcd")
        check(refused(lambda: verify_tree(tree, fake, man), "TREE_MISMATCH"), "tree: changed size refused")
        (tree / "GAMEDATAbin" / "a.bhf").unlink()
        check(refused(lambda: verify_tree(tree, fake, man), "TREE_MISMATCH"), "tree: missing file refused")
        check(refused(lambda: identify(tree, releases), "TREE_MISMATCH"), "tree: identify refuses a wrong tree")
        # Entry names from a package are plain relative paths only.
        for bad in ("../x", "a/../../x", "C:/x", "a\\b", "", "a//b", "con.", "a/ b ", "x\x01"):
            check(refused(lambda: safe_parts(bad), "UNSAFE_PATH"), f"unsafe entry {bad!r}")
        check(safe_parts("GAMEDATAbin/fact_55/fact_55_2.btf") == ["GAMEDATAbin", "fact_55", "fact_55_2.btf"], "plain entry")
        # Extraction refuses before reading anything when the identity or the output is wrong.
        out = t / "out_nonempty"
        out.mkdir()
        (out / "keep").write_bytes(b"k")
        check(refused(lambda: extract(t / "other_version.bin", t / "out_new", releases), "UNSUPPORTED_VERSION"),
              "extract: unsupported package refused")
        check(not (t / "out_new").exists() and not list(t.glob("out_new.partial-*")), "extract: nothing written after a refusal")
        check((out / "keep").read_bytes() == b"k", "extract: an existing directory is never touched")
        check(refused(lambda: extract(t / "other_version.bin", t / "no" / "such" / "out", releases), "UNSUPPORTED_VERSION")
              and not (t / "no").exists(), "extract: no parent directory is created on a refusal")
        check(refused(lambda: extract(t / "other_version.bin", t / "inside", releases), "UNSUPPORTED_VERSION"),
              "extract: identity is checked first")
        check(load_manifest(releases[0]).get("Default.xex", (0, ""))[1] == releases[0]["executable"]["sha256"],
              "tracked manifest: hash recorded and Default.xex entry agrees with the release table")
    print(f"R3HD_INTAKE_SELFTEST {'PASS' if not failures else 'FAIL'} checks={checks} failures={failures}")
    return 0 if not failures else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("identify", "verify"):
        p = sub.add_parser(name)
        p.add_argument("path", type=Path)
        p.add_argument("--json", action="store_true")
    p = sub.add_parser("extract")
    p.add_argument("package", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--json", action="store_true")
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest()
    releases = load_releases()
    try:
        if a.cmd == "identify":
            r = identify(a.path, releases)
        elif a.cmd == "verify":
            r = verify_tree(a.path, releases[0])
        else:
            r = extract(a.package, a.out, releases)
    except Refused as e:
        if a.json:
            print(json.dumps({"result": "refused", "code": e.code, "detail": e.detail, **getattr(e, "result", {})}, indent=2))
        print(f"R3HD_INTAKE REFUSED {e.code}: {e.detail}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"result": "supported", **r}, indent=2, default=str))
    print(f"R3HD_INTAKE OK {a.cmd} release={r['release']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
