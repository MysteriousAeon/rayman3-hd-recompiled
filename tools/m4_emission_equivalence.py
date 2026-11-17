#!/usr/bin/env python3
"""LM-A A2 (D1): Windows equivalence of the macro emission, by preprocessed tokens.

Compares two generated trees file by file (r3hd_*.h / r3hd_*.cpp; CRLF -> LF):
  * byte-identical files need nothing more;
  * every differing file is preprocessed for Windows with the production compile definitions and include order
    (clang++ -E -P; the tree's own r3hd_pch.h force-included, as the build's cmake_pch.hxx does) in both trees, and
    the two token streams must be identical.
The new M4 headers (tools/m4_seh.h, m4_seh_portable.h) are staged ahead of the installed SDK headers for both trees:
their Windows branch is unchanged apart from the added macros, which only the new tree uses.

    cmd /c tools\\devenv.bat python tools/m4_emission_equivalence.py --old OLD/generated/default --new NEW/generated/default
Prints M4_EMISSION_EQUIVALENCE PASS|FAIL; writes private/work/m4_emission/equivalence.json. Hashes and counts only.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "private/work/m4_emission"
NAME = re.compile(r"r3hd_[A-Za-z0-9_.]+\.(h|cpp)$")
DEFINES = ["-DNOMINMAX", "-DREX_HAS_D3D12=1", "-DSPDLOG_COMPILED_LIB", "-DSPDLOG_FMT_EXTERNAL",
           "-DWIN32_LEAN_AND_MEAN", "-D_DLL", "-D_MT", "-DNDEBUG"]
FLAGS = ["-std=gnu++23", "-msse4.1", "-fasync-exceptions", "-E", "-P"]
# C++ preprocessing tokens: raw strings first (they may contain quotes and newlines), prefixed string and character
# literals (never across a newline), identifiers, numbers with digit separators, punctuators.
TOKEN = re.compile(r'(?:u8|u|U|L)?R"(?P<d>[^()\\\s]{0,16})\((?:.|\n)*?\)(?P=d)"'
                   r'|(?:u8|u|U|L)?"(?:\\.|[^"\\\n])*"|(?:u8|u|U|L)?\'(?:\\.|[^\'\\\n])+\''
                   r"|[A-Za-z_]\w*|\.?\d(?:[eEpP][+-]|[\w.]|'(?=\w))*"
                   r'|::|->\*?|\+\+|--|<<=|>>=|<=>|<=|>=|==|!=|&&|\|\||<<|>>|##|\.\.\.|[-+*/%&|^]=|\S')


def tokenize(text):
    return [m.group(0) for m in TOKEN.finditer(text)]


def files(tree):
    return {p.name: p for p in tree.iterdir() if NAME.match(p.name)}


def norm(p):
    return p.read_bytes().replace(b"\r\n", b"\n")


def staged_headers():
    inc = OUT / "inc" / "rex"
    inc.mkdir(parents=True, exist_ok=True)
    for name in ("m4_seh.h", "m4_seh_portable.h"):
        shutil.copyfile(ROOT / "tools" / name, inc / name)
    return OUT / "inc"


def preprocess(tree, name, staged):
    sdk = ROOT / "external/rexglue-sdk/out/install/win-amd64/include"
    cmd = ["clang++", *DEFINES, "-I", str(staged), "-I", str(ROOT / "private/work/rex"),
           "-I", str(ROOT / "private/work/rex/src"), "-I", str(tree), "-isystem", str(sdk),
           "-isystem", str(sdk / "dxc"), *FLAGS]
    if name != "r3hd_pch.h":
        cmd += ["-include", str(tree / "r3hd_pch.h")]
    cmd += ["-x", "c++", str(tree / name)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError(f"preprocess failed {tree / name}: {p.stderr[-2000:]}")
    # The two trees live in different directories; __FILE__-style expansions name them. Normalize every spelling
    # of the tree's own path (both separators, escaped or not) so only real token differences remain.
    text = p.stdout
    resolved = tree.resolve()
    for spelling in sorted({str(resolved), str(resolved).replace("\\", "\\\\"), resolved.as_posix(),
                            str(tree), str(tree).replace("\\", "\\\\"), tree.as_posix()}, key=len, reverse=True):
        text = text.replace(spelling, "<TREE>")
    return tokenize(text)


def compare(old, new, name, staged):
    a, b = preprocess(old, name, staged), preprocess(new, name, staged)
    row = {"tokens": len(a), "identical": a == b,
           "sha256_tokens": hashlib.sha256("\x00".join(a).encode()).hexdigest()}
    if a != b:
        i = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        row["first_difference"] = {"index": i, "old": " ".join(a[max(0, i - 8):i + 8]),
                                   "new": " ".join(b[max(0, i - 8):i + 8]), "old_len": len(a), "new_len": len(b)}
    return name, row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old", type=Path, required=True)
    ap.add_argument("--new", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=max(2, (os.cpu_count() or 4) // 2))
    args = ap.parse_args()
    old, new = files(args.old), files(args.new)
    result = {"old_files": len(old), "new_files": len(new), "same_names": sorted(old) == sorted(new)}
    same, differ = [], []
    for name in sorted(set(old) & set(new)):
        (same if norm(old[name]) == norm(new[name]) else differ).append(name)
    result.update(byte_identical=len(same), differing=len(differ))
    staged = staged_headers()
    with ThreadPoolExecutor(args.jobs) as pool:
        rows = dict(pool.map(lambda n: compare(args.old, args.new, n, staged), differ))
    result["files"] = rows
    result["token_identical"] = sum(1 for r in rows.values() if r["identical"])
    result["pass"] = result["same_names"] and result["token_identical"] == len(differ)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "equivalence.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for name, r in rows.items():
        if not r["identical"]:
            print("DIFF", name, json.dumps(r["first_difference"])[:600])
    print(f"M4_EMISSION_EQUIVALENCE {'PASS' if result['pass'] else 'FAIL'} files={len(new)} "
          f"byte_identical={len(same)} differing={len(differ)} token_identical={result['token_identical']} "
          f"results={OUT / 'equivalence.json'}")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
