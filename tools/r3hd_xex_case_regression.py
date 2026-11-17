#!/usr/bin/env python3
"""LX-6 (E-377) regression: the patched SDK carries the case-insensitive entrypoint check without changing Windows.

Run after the chain (tools/build_milestone8.bat) or on any patched SDK copy. Checks:
  * src/ui/rex_app.cpp has the hooked `if` line exactly once and the unhooked line no longer;
  * the hook shares the original line (same line count as the line it replaces), so no later line moves;
  * include/rex/rex_app.h ends with the helper block exactly as tools/r3hd_xex_case_patch.py writes it, and
    its Windows branch defines REX_XEX_CASE_FALLBACK empty (Windows tokens after preprocessing are unchanged);
  * the chain runs the patch last, after r3hd_vulkan_parity_patch.py.
Final line R3HD_XEX_CASE_REGRESSION PASS|FAIL.
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import r3hd_xex_case_patch as P  # noqa: E402
from m3_runtime_patch import SDK  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


cpp = (SDK / P.CPP).read_text().replace("\r\n", "\n")
hdr = (SDK / P.HDR).read_text().replace("\r\n", "\n")
check("rex_app.cpp: the hooked entrypoint check is present once", cpp.count(P.LINE_AFTER) == 1)
check("rex_app.cpp: the unhooked check is gone", P.LINE_BEFORE not in cpp)
check("the hook shares the original line", P.LINE_AFTER.count("\n") == P.LINE_BEFORE.count("\n") == 1)
check("rex_app.h ends with the helper block", hdr.endswith(P.HELPER))
check("Windows: the macro is empty", "#else\n#define REX_XEX_CASE_FALLBACK(path)\n#endif\n" in P.HELPER)
check("the helper is POSIX-only", P.HELPER.index("#if !defined(_WIN32)") < P.HELPER.index("XexExistsIgnoringCase"))
bat = (TOOLS / "build_milestone8.bat").read_text(encoding="utf-8")
check("the chain runs it after the Vulkan parity patch",
      0 < bat.index("python tools\\r3hd_vulkan_parity_patch.py") < bat.index("python tools\\r3hd_xex_case_patch.py"))
print(f"R3HD_XEX_CASE_REGRESSION {'PASS' if not fails else 'FAIL'}")
sys.exit(1 if fails else 0)
