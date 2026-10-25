#!/usr/bin/env python3
"""Scan the decrypted image for middleware/feature signature strings.
Prints counts and a few short matching strings (<=100 chars each) per keyword. Evidence of presence, not of runtime use."""
import re, sys, collections
img = open(sys.argv[1], "rb").read()
strs = [m.group().decode("latin-1") for m in re.finditer(rb"[\x20-\x7e]{5,}", img)]
wide = [m.group().decode("utf-16-be") for m in re.finditer(rb"(?:\x00[\x20-\x7e]){5,}", img)]
print(f"ascii strings: {len(strs)}  utf16be strings: {len(wide)}")
keys = sys.argv[2:] or ["bink", "RAD Game", "xma", "fmod", "wwise", "audiokinetic", "havok", "scaleform", "gfx",
        "openspace", "ubi", "dare", "hybrid", "\.xex", "\.dll", "\.exe", "xaudio", "d3dx", "hlsl", "zlib",
        "inflate", "lzo", "vorbis", "ogg", "mp3", "adpcm", "lua", "python", "copyright", "version", "game:\\\\",
        "d:\\\\", "\.pdb", "shadercache", "\.psh", "\.vsh", "savegame", "\.sav", "leaderboard", "achievement",
        "x:\\\\", "e:\\\\", "c:\\\\", "\.cpp", "\.lvl", "\.btf", "\.hxx", "\.bik", "speex", "theora", "curl", "ssl", "http"]
for k in keys:
    rx = re.compile(k, re.I)
    hits = [s for s in strs + wide if rx.search(s)]
    uniq = list(collections.OrderedDict.fromkeys(hits))
    print(f"\n## /{k}/ : {len(hits)} hits, {len(uniq)} unique")
    for s in uniq[:8]:
        print("   ", s[:100])
