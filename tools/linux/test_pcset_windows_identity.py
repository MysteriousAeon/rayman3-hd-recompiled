#!/usr/bin/env python3
"""LX-4 (E-375): the shared host headers keep the Windows build exactly as it was.

r3hd_pc_settings.h and r3hd_app.h gained POSIX branches beside the Windows code. Evaluated for _WIN32, each file must
give the same tokens on the same line numbers (`#line` directives restore them; REXLOG embeds __LINE__) as the
reference commit, the last Windows-verified version. Run from the repository; needs git. A legitimate Windows change
moves REFERENCE to the commit that was verified with a Windows build.

  python tools/linux/test_pcset_windows_identity.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# G6-P59: moved from 9cf8967 (E-374) after the Windows changes of v1.2.0 (controller navigation, tooltips, prompts,
# DualSense Auto) and G6-P45 (HUD toggle); 68a28bd holds both files as they are and passed the full Windows
# build_milestone8.bat replay (E-530). Earlier references: 9cf8967 (E-373 / E-374).
REFERENCE = "68a28bd"
HOSTUPDATE_COMMIT = "662b505"  # LX-4 (E-375): the r3hd_pc_settings.h that r3hd_linux_build.py hostupdate installs
FILES = ("tools/m2_host/r3hd_pc_settings.h", "tools/m2_host/r3hd_app.h")
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\w+|\S')


def stream(text, win=True):
    """(token, line) pairs of the active branch, honoring `#if [!]defined(_WIN32)`, #else, #endif and `#line N`."""
    text = text.replace('\r\n', '\n')
    text = re.sub(r'/\*.*?\*/', lambda m: '\n' * m.group(0).count('\n'), text, flags=re.S)
    out, stack, line = [], [], 0
    for raw in text.split('\n'):
        line += 1
        s = raw.strip()
        if not s.startswith('"'):
            s = re.sub(r'\s*//.*$', '', s)
        m = re.match(r'#\s*if\s+(!?)defined\(_WIN32\)$', s) or re.match(r'#\s*if(n?)def\s+_WIN32$', s)  # G6-P59
        if m:
            stack.append(win != bool(m.group(1)))
            continue
        if s == '#else' and stack:
            stack[-1] = not stack[-1]
            continue
        if s == '#endif' and stack:
            stack.pop()
            continue
        if not all(stack):
            continue
        m = re.match(r'#\s*line\s+(\d+)$', s)
        if m:
            line = int(m.group(1)) - 1
            continue
        if s == '#pragma once' or s.startswith('#define R3HD_PCSET_POSIX_FONTS('):  # directives emit no token
            continue
        out += [(t, line) for t in TOKEN.findall(s)]
    return out


HOOK = "R3HD_PCSET_POSIX_FONTS(atlas, pcset_host_.font)"  # r3hd_app.h; empty on Windows (r3hd_pc_settings.h)
EMPTY_ON_WINDOWS = "#else\n#define R3HD_PCSET_POSIX_FONTS(atlas, font)\n#endif"


def main() -> int:
    fails = []
    panel = (ROOT / FILES[0]).read_text(encoding="utf-8").replace("\r\n", "\n")
    if EMPTY_ON_WINDOWS not in panel:
        fails.append("R3HD_PCSET_POSIX_FONTS is not defined empty for Windows")
    for rel in FILES:
        ref = subprocess.run(["git", "show", f"{REFERENCE}:{rel}"], cwd=ROOT, capture_output=True, check=True).stdout
        # The Windows preprocessor expands the hook to nothing; it shares a line with existing code, so lines hold.
        # Since LX-4 the reference carries the hook as well (G6-P59 moved REFERENCE past it), so it is removed on both.
        a = stream(ref.decode("utf-8").replace(" " + HOOK, ""))
        b = stream((ROOT / rel).read_text(encoding="utf-8").replace(" " + HOOK, ""))
        if [t for t, _ in a] != [t for t, _ in b]:
            fails.append(f"{rel}: Windows tokens differ from {REFERENCE}")
        elif a != b:
            first = next(x for x in zip(a, b) if x[0] != x[1])
            fails.append(f"{rel}: Windows line numbers differ from {REFERENCE} (first {first})")
        else:
            print(f"ok   {rel}: {len(a)} Windows tokens, tokens and lines identical to {REFERENCE}")
    # The native batch moves the LM-A tree to exactly this header (r3hd_linux_build.py hostupdate).
    sys.path.insert(0, str(ROOT / "tools" / "linux"))
    import hashlib
    import r3hd_linux_build as b
    # G6-P59 (D-310): hostupdate is the LX-4 transition of the RC1-era LM-A tree and stays pinned to the LX-4 header.
    # A later Linux build packages a fresh LM-A tree (r3hd_lma_tree.py) that already holds the current headers, so
    # hostupdate correctly refuses the current header (its "new content differs" check) instead of half-updating.
    lx4 = subprocess.run(["git", "show", f"{HOSTUPDATE_COMMIT}:{FILES[0]}"], cwd=ROOT, capture_output=True,
                         check=True).stdout
    lf = hashlib.sha256(lx4.replace(b"\r\n", b"\n")).hexdigest()
    if b.HOST_UPDATES["r3hd_pc_settings.h"]["new"] != lf:
        fails.append(f"r3hd_linux_build.py HOST_UPDATES r3hd_pc_settings.h new != {lf} ({HOSTUPDATE_COMMIT})")
    else:
        print(f"ok   hostupdate's new r3hd_pc_settings.h is the LX-4 header ({HOSTUPDATE_COMMIT})")
    for f in fails:
        print("FAIL", f)
    print(f"R3HD_PCSET_WINDOWS_IDENTITY {'PASS' if not fails else 'FAIL'} files={len(FILES)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
