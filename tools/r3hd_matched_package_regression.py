#!/usr/bin/env python3
"""Synthetic-only checks for the matched installer/portable package guard.

No release payload, runtime binary, game data, or protected archive is copied.
The archive-audit entry point is stubbed with a synthetic PASS so these checks
exercise pair correspondence independently; this does not replace real archive
or acceptance validation.
"""
import contextlib
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import m50_build
import r3hd_portable_zip as pack


def encoded(data):
    return (json.dumps(data, sort_keys=True) + "\n").encode()


def fixture(root):
    stage = root / "stage"
    payload = stage / "payload"
    payload.mkdir(parents=True)
    version = "test-private"
    shared = {
        "app/r3hd_launcher.exe": b"synthetic launcher marker",
        "app/THIRD_PARTY_NOTICES.txt": b"synthetic notices marker",
    }
    omitted = {"app/play.cmd": b"installer Play", "app/settings.cmd": b"installer Settings"}
    base_files = {name: {"size": len(data), "sha256": pack.digest(data)}
                  for name, data in {**shared, **omitted}.items()}
    for name, data in {**shared, **omitted}.items():
        path = payload / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    source_name = f"r3hd-lgpl-source-{version}.zip"
    source_bytes = b"synthetic corresponding source marker"
    (stage / source_name).write_bytes(source_bytes)
    base = {"version": version, "payload_id": "synthetic-base-id", "files": base_files}
    (payload / "payload.json").write_bytes(encoded(base))
    archive = root / "portable.zip"
    inner_files = {name: value for name, value in base_files.items() if name not in omitted}
    portable = {"base_payload_id": base["payload_id"], "application_version": version}
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(pack.TOP + "/portable.json", encoded(portable))
        zf.writestr(pack.TOP + "/payload.json", encoded({"version": version, "files": inner_files}))
        for name, data in shared.items():
            zf.writestr(pack.TOP + "/" + name, data)
        zf.writestr(pack.TOP + "/" + source_name, source_bytes)
    return stage, archive, base, shared, source_name


def replace_member(archive, member, transform):
    temp = archive.with_name(archive.stem + "-changed.zip")
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(temp, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == pack.TOP + "/" + member:
                data = transform(data)
            dst.writestr(item, data)
    return temp


def expect_refusal(fn, contains):
    try:
        fn()
    except ValueError as exc:
        return contains in str(exc)
    return False


def main():
    checks = []

    def check(name, ok):
        checks.append(bool(ok))
        print(("PASS " if ok else "FAIL ") + name, flush=True)
        if not ok:
            raise AssertionError(name)

    with tempfile.TemporaryDirectory(prefix="r3hd_matched_pair_") as tmp:
        root = Path(tmp)
        def compare(current_stage, current_archive, base_record):
            with patch.object(pack, "check", return_value={"sha256": "synthetic", "bytes": 1}), \
                    patch.object(pack.engine, "load_payload", return_value=base_record):
                return pack.compare_stage(current_stage, current_archive)

        stage, archive, base, shared, source_name = fixture(root / "matching")
        result = compare(stage, archive, base)
        check("matching stage and ZIP report shared hashes and expected omissions",
              result["result"] == "PASS" and len(result["shared_files"]) == len(shared) and
              result["installer_only_payload"] == ["app/play.cmd", "app/settings.cmd"] and
              result["lgpl_source_sha256"] == pack.digest((stage / source_name).read_bytes()))

        archive = replace_member(archive, "app/THIRD_PARTY_NOTICES.txt", lambda _: b"changed notices")
        check("shared notice byte change is rejected",
              expect_refusal(lambda: compare(stage, archive, base), "shared bytes differ: app/THIRD_PARTY_NOTICES.txt"))
        stage, archive, base, _, _ = fixture(root / "version")
        archive = replace_member(archive, "payload.json", lambda raw: encoded({**json.loads(raw), "version": "other"}))
        check("portable payload version mismatch is rejected",
              expect_refusal(lambda: compare(stage, archive, base), "version or base payload identity differs"))
        stage, archive, base, _, _ = fixture(root / "members")
        archive = replace_member(archive, "payload.json", lambda raw: encoded({
            **json.loads(raw), "files": {**json.loads(raw)["files"], "unexpected/file": {"size": 0, "sha256": ""}}}))
        check("unexpected portable payload omission/addition is rejected",
              expect_refusal(lambda: compare(stage, archive, base), "Unexpected installer/ZIP payload difference"))
        stage, archive, base, _, _ = fixture(root / "missing")
        replace = lambda raw: encoded({**json.loads(raw), "files": {
            key: value for key, value in json.loads(raw)["files"].items() if key != "app/r3hd_launcher.exe"}})
        archive = replace_member(archive, "payload.json", replace)
        check("missing shared launcher is rejected as an unexpected omission",
              expect_refusal(lambda: compare(stage, archive, base), "Unexpected installer/ZIP payload difference"))
        stage, archive, base, _, source_name = fixture(root / "source")
        (stage / source_name).write_bytes(b"different source")
        check("corresponding source mismatch is rejected",
              expect_refusal(lambda: compare(stage, archive, base), "corresponding source differs"))
        stage, archive, base, _, _ = fixture(root / "identity")
        wrong_base = {**base, "payload_id": "different-base-id"}
        check("installer base payload identity mismatch is rejected",
              expect_refusal(lambda: compare(stage, archive, wrong_base), "base payload identity differs"))
        wrong_version = {**base, "version": "other"}
        check("installer base version mismatch is rejected",
              expect_refusal(lambda: compare(stage, archive, wrong_version), "version or base payload identity differs"))

    old_argv = sys.argv
    try:
        sys.argv = ["m50_build.py", "unused", "--expect-runtime", "unused.json", "--portable-id", "pair"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = m50_build.b.main()
        check("matched flags require an explicit pinned CRT source", status == 2 and "must be paired" in output.getvalue())

        sys.argv = ["m50_build.py", "unused", "--expect-runtime", "unused.json", "--portable-id", "pair",
                    "--crt-dir", "unused", "--test-variant", "test"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = m50_build.b.main()
        check("matched build refuses test variants before any build work", status == 2 and "no test-variant" in output.getvalue())
    finally:
        sys.argv = old_argv

    print(f"R3HD_MATCHED_PACKAGE_REGRESSION PASS checks={len(checks)} protected_files=0 builds=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
