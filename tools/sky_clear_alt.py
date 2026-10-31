"""Clearleaf sky (E-350, D-153): label the frames of a hidden R3HD_TEST_SKY_CLEAR=alternate run. Standard library only.

usage: sky_clear_alt.py RUN

The runtime log records each switch of the scene clear ("SkyClearTest alternate background=0|1") and each saved
frame ("M3 frame_capture swap=N file=..."), with times. A frame is labelled with the half it was captured in;
one captured less than 0.15 s after a switch is labelled "edge" (the clear of the frame shown may still be the
previous half's). Prints one line per frame: file, label, seconds since the last switch.
"""
import re
import sys
from datetime import datetime
from pathlib import Path

STAMP = r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3})\]"


def main() -> int:
    run = Path(sys.argv[1])
    switches, frames = [], []
    for line in (run / "runtime.log").read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(STAMP, line)
        if not m:
            continue
        t = datetime.strptime(m[1], "%Y-%m-%d %H:%M:%S.%f")
        s = re.search(r"SkyClearTest alternate background=(\w+)", line)
        if s:
            switches.append((t, s[1] in ("true", "1")))
        f = re.search(r"M3 frame_capture swap=\d+ file=(\S+)", line)
        if f:
            frames.append((t, f[1]))
    if not switches:
        print("SKY_ALT FAIL no switch logged (run made without R3HD_TEST_SKY_CLEAR=alternate?)")
        return 1
    for t, name in frames:
        before = [s for s in switches if s[0] <= t]
        if not before:
            print(f"{name} original-start")
            continue
        at, on = before[-1]
        gap = (t - at).total_seconds()
        print(f"{name} {'edge' if gap < 0.15 else 'background' if on else 'original'} {gap:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
