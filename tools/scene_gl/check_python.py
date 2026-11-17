#!/usr/bin/env python3
"""G6-P39 (D-295): refuse to build the OpenGL bridge against any Python other than the payload's pinned CPython.

    check_python.py PYTHON_DIR     exit 0 when PYTHON_DIR/python311.dll equals config/release/payload.json's pin and
                                   PYTHON_DIR has include/Python.h and libs/python311.lib
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    d = Path(argv[0])
    pin = json.loads((ROOT / "config" / "release" / "payload.json").read_text(encoding="utf-8"))["python"]["files"]
    dll = d / "python311.dll"
    ok = dll.is_file() and hashlib.sha256(dll.read_bytes()).hexdigest() == pin["python311.dll"] \
        and (d / "include" / "Python.h").is_file() and (d / "libs" / "python311.lib").is_file()
    print(f"SCENE_GL_PYTHON {'OK' if ok else 'REFUSED'} {d}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
