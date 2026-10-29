"""Optional research probe in the host wrapper, never in generated game code.

Apply only after a standard build, then incremental build. Standard build restores
the original wrapper. No function/config address mappings or guest state change.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def apply(destination):
    source = destination / "m2_trace.cpp"
    text = source.read_bytes().decode("utf-8").replace("\r\n", "\n")
    before = '  m2_current_context = &ctx;\n'
    after = before + '  r3hd_mouse_dispatch::Enter(name, ctx);\n'
    include = '#include "r3hd_mouse_dispatch_trace.h"\n'
    if after not in text:
        if text.count(before) != 1:
            raise ValueError("expected one existing host entry probe")
        text = text.replace(before, after)
    if include not in text:
        text = text.replace('#include "m2_trace.h"\n', '#include "m2_trace.h"\n' + include)
    if text.count(include) != 1 or text.count('r3hd_mouse_dispatch::Enter(name, ctx);') != 1:
        raise ValueError("ambiguous probe installation")
    source.write_bytes(text.encode("utf-8"))
    (destination / "r3hd_mouse_dispatch_trace.h").write_bytes(
        (ROOT / "tools/r3hd_mouse_dispatch_trace.h").read_bytes())


if __name__ == "__main__":
    apply(ROOT / "private/work/rex/src")
    print("MOUSE_DISPATCH_PATCH installed optional host-entry observation")
