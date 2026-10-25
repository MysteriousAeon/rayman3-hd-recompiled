#!/usr/bin/env python3
"""M50 R-01 audit: which shipped binaries carry key constants or fragments of the decrypted title image.

  m50_r01_audit.py keys  FILE_OR_DIR...   count every 16-byte key constant of the SDK in each file
  m50_r01_audit.py image IMAGE FILE...    count 32-byte high-entropy chunks of IMAGE found in each file

No key or image byte is printed or written: the key constants are read at run time from the local SDK checkout
(D-003), and results are names, files, counts and offsets only. Exit code 0 always; the caller judges.
"""
import argparse, json, math, os, re, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDK = os.path.join(REPO, "external", "rexglue-sdk", "src")
# (source file, array name, what it is) -- the 16-byte key constants the SDK can compile in.
KEY_SOURCES = [
    ("system/xex_module.cpp", "xe_xex2_retail_key", "XEX2 retail key (platform-wide; decrypts the player's Default.xex)"),
    ("system/xex_module.cpp", "xe_xex2_devkit_key", "XEX2 devkit key (platform-wide; development-console XEX only)"),
    ("kernel/xboxkrnl/xboxkrnl_crypt.cpp", "key19", "kernel XeKeysHmacSha key 0x19 (platform-wide)"),
    ("kernel/xboxkrnl/xboxkrnl_crypt.cpp", "xe_key_obfuscation_key", "kernel XeKeysAesCbcUsingKey obfuscation key"),
]


def _array(text, name):
    m = re.search(r"\b" + re.escape(name) + r"\s*\[[^\]]*\]\s*=\s*\{([^}]*)\}", text)
    if not m:
        return None
    vals = [int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]{1,2})", m.group(1))]
    return bytes(vals) if len(vals) == 16 else None


def load_keys(sdk=SDK):
    """A key that a patch removed (tools/m50_runtime_patch.py) is read from the pinned commit's copy instead."""
    keys = []
    for rel, name, what in KEY_SOURCES:
        value = _array(open(os.path.join(sdk, rel), encoding="utf-8", errors="replace").read(), name)
        removed = value is None
        if removed:
            git = subprocess.run(["git", "-C", os.path.dirname(sdk), "show", "HEAD:src/" + rel],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
            value = _array(git.stdout, name) if git.returncode == 0 else None
        keys.append({"name": name, "what": what, "source": rel, "value": value, "removed_from_source": removed})
    return keys


def iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in sorted(files):
                    yield os.path.join(root, f)
        else:
            yield p


def cmd_keys(args):
    keys = load_keys(args.sdk)
    rows = []
    for f in iter_files(args.paths):
        data = open(f, "rb").read()
        hits = {}
        for k in keys:
            if k["value"] is None or len(set(k["value"])) == 1:
                continue
            n, pos = 0, data.find(k["value"])
            while pos >= 0:
                n += 1
                pos = data.find(k["value"], pos + 1)
            if n:
                hits[k["name"]] = n
        rows.append({"file": os.path.relpath(f, args.base) if args.base else f, "hits": hits})
    unresolved = [k["name"] for k in keys if k["value"] is None]
    # A constant of one repeated byte (the SDK's all-zero placeholders) is no key and matches everywhere.
    out = {"keys": [{"name": k["name"], "what": k["what"], "source": k["source"],
                     "removed_from_source": k["removed_from_source"],
                     "placeholder": k["value"] is not None and len(set(k["value"])) == 1} for k in keys],
           "unresolved": unresolved, "files": rows,
           "carriers": sorted({r["file"] for r in rows if r["hits"]})}
    print(json.dumps(out, indent=1))


def entropy(b):
    c = {}
    for x in b:
        c[x] = c.get(x, 0) + 1
    return -sum(v / len(b) * math.log2(v / len(b)) for v in c.values())


def cmd_image(args):
    img = open(args.image, "rb").read()
    W, STEP = 32, 64
    index = {}
    for off in range(0, len(img) - W, STEP):
        chunk = img[off:off + W]
        if entropy(chunk) >= 4.0:          # skip padding, zero runs, repeated tables
            index.setdefault(chunk, off)
    rows = []
    for f in iter_files(args.paths):
        data = open(f, "rb").read()
        found = []
        # Every W-byte window of the file is looked up; chunks are anchored at image offsets that are multiples
        # of STEP, so any copied run of STEP + W bytes or more is found.
        get = index.get
        for pos in range(0, len(data) - W + 1):
            o = get(data[pos:pos + W])
            if o is not None:
                found.append((pos, o))
        rows.append({"file": f if not args.base else os.path.relpath(f, args.base), "bytes": len(data),
                     "matches": len(found), "first": [{"file_off": a, "image_off": b} for a, b in found[:5]]})
    print(json.dumps({"image_bytes": len(img), "indexed_chunks": len(index), "window": W, "step": STEP,
                      "files": rows}, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keys")
    k.add_argument("paths", nargs="+")
    k.add_argument("--sdk", default=SDK)
    k.add_argument("--base")
    i = sub.add_parser("image")
    i.add_argument("image")
    i.add_argument("paths", nargs="+")
    i.add_argument("--base")
    args = ap.parse_args()
    {"keys": cmd_keys, "image": cmd_image}[args.cmd](args)


if __name__ == "__main__":
    main()
