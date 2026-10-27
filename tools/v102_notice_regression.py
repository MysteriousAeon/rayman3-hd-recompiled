#!/usr/bin/env python3
"""Focused RC4 packaging checks; no installer or game launch."""
import tempfile
from pathlib import Path

import m50_build as build


def main():
    with tempfile.TemporaryDirectory() as td:
        payload = Path(td)
        files = {
            "app/licenses/TinySHA1-LICENSE.txt": "tools/installer/TinySHA1-LICENSE.txt",
            "app/THIRD_PARTY_NOTICES.txt": "tools/installer/THIRD_PARTY_NOTICES.txt",
            "app/PROVENANCE.md": "docs/PROVENANCE.md",
        }
        for dst, src in files.items():
            p = payload / dst
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes((build.ROOT / src).read_bytes().replace(b"\r\n", b"\n"))
        assert build.tinysha_notice(payload)["tinysha_notice"]["matches_source_header"]
        count = 1
        for rel, replacement in (
            ("app/licenses/TinySHA1-LICENSE.txt", None),
            ("app/licenses/TinySHA1-LICENSE.txt", b"TinySHA1: thanks to its author\n"),
            ("app/THIRD_PARTY_NOTICES.txt", b"TinySHA1: terms in source headers\n"),
            ("app/PROVENANCE.md", b"outdated provenance\n"),
        ):
            p = payload / rel
            original = p.read_bytes()
            if replacement is None:
                p.unlink()
            else:
                p.write_bytes(replacement)
            try:
                build.tinysha_notice(payload)
            except build.Refused:
                count += 1
            else:
                raise AssertionError(f"packaging accepted damaged material: {rel}")
            finally:
                p.write_bytes(original)
        print(f"V102_NOTICE_REGRESSION PASS {count}/{count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
