#!/usr/bin/env python3
"""E-468 (D-235) G3a test-only growth gate for intro_10.lvl AND intro_10.ptr. NOT part of any build chain or release.

Successor of e465_test_grow_patch.py (unchanged, still usable for E-465b / E-467). The production overlay
(tools/m33_mod_overlay.h) is never edited. This script edits only the SDK's installed copy
(external/rexglue-sdk/include/rex/m33_mod_overlay.h, outside Git) for a private incremental build, and `revert`
copies the production header back byte for byte (then rebuild with tools\\build_incremental.bat).

With the patch, a `grow` record may name a file only if ALL hold, otherwise the plan is refused as before
(`grow_not_allowed`):
  - the environment variable R3HD_G3A_TEST_GROW is exactly "intro_10" (unset by default);
  - the file name (ASCII, any case) and host size are exactly intro_10.lvl / 7,661,836 bytes (growth <= 65,536) or
    intro_10.ptr / 209,068 bytes (growth <= 4,096);
  - the file's first range starts at offset 0 and covers the whole original file, so the plan's game-bytes hash
    (FNV-1a 64) checks every original byte before anything is served (`g3a_identity` otherwise).
Everything else (sizes, hashes, coverage of the tail, atomic refusal of the whole plan) is the production
validation unchanged.

usage: g3a_test_grow_patch.py apply | revert | status
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROD = ROOT / "tools" / "m33_mod_overlay.h"
SDK = ROOT / "external" / "rexglue-sdk" / "include" / "rex" / "m33_mod_overlay.h"
MARK = "G3A_TEST_GROW"

EDITS = [
    ("  uint64_t guest_size = 0;    // M36: = size unless a `grow` record set it\n",
     "  uint64_t guest_size = 0;    // M36: = size unless a `grow` record set it\n"
     "  uint64_t g3a_max = 0;       // G3A_TEST_GROW (test-only build): growth bound when the G3a gate admits it\n"),
    ("// M36: whether the file name (ASCII, without case) is one that a `grow` record may name.\n",
     "// G3A_TEST_GROW (test-only build, tools/experiments/modding_feasibility/g3a_test_grow_patch.py): intro_10.lvl of\n"
     "// exactly 7,661,836 bytes (+64 KiB) or intro_10.ptr of exactly 209,068 bytes (+4 KiB), only while\n"
     "// R3HD_G3A_TEST_GROW is \"intro_10\". Returns the growth bound, 0 = not admitted.\n"
     "inline uint64_t G3aTestGrow(const std::filesystem::path& p, uint64_t size) {\n"
     "  const char* v = std::getenv(\"R3HD_G3A_TEST_GROW\");\n"
     "  if (!v || std::strcmp(v, \"intro_10\") != 0) return 0;\n"
     "  struct Allowed { const char* name; uint64_t size, max; };\n"
     "  static const Allowed kAllowed[] = {{\"intro_10.lvl\", 7661836, 65536}, {\"intro_10.ptr\", 209068, 4096}};\n"
     "  const auto name = p.filename().native();\n"
     "  for (const auto& a : kAllowed) {\n"
     "    if (size != a.size || name.size() != std::strlen(a.name)) continue;\n"
     "    bool same = true;\n"
     "    for (size_t i = 0; i < name.size() && same; ++i) {\n"
     "      auto c = name[i];\n"
     "      if (c >= 'A' && c <= 'Z') c = c + 32;\n"
     "      same = c == decltype(c)(a.name[i]);\n"
     "    }\n"
     "    if (same) return a.max;\n"
     "  }\n"
     "  return 0;\n"
     "}\n\n"
     "// M36: whether the file name (ASCII, without case) is one that a `grow` record may name.\n"),
    ("      if (!GrowAllowed(t.path)) return fail(\"grow_not_allowed\");\n"
     "      if (t.guest_size != t.size || !t.ranges.empty()) return fail(\"grow_order\");\n"
     "      if (guest <= t.size || guest - t.size > kMaxGrowBytes) return fail(\"grow_bounds\");\n",
     "      t.g3a_max = GrowAllowed(t.path) ? 0 : G3aTestGrow(t.path, t.size);  // G3A_TEST_GROW\n"
     "      if (!GrowAllowed(t.path) && !t.g3a_max) return fail(\"grow_not_allowed\");\n"
     "      if (t.guest_size != t.size || !t.ranges.empty()) return fail(\"grow_order\");\n"
     "      if (guest <= t.size || guest - t.size > (t.g3a_max ? t.g3a_max : kMaxGrowBytes)) return fail(\"grow_bounds\");\n"),
    ("    if (t.guest_size > t.size) {  // M36: every byte past the file's end belongs to a range\n",
     "    if (t.g3a_max && (t.ranges.empty() || t.ranges[0].offset != 0 || t.ranges[0].length < t.size))\n"
     "      return \"g3a_identity\";  // G3A_TEST_GROW: the whole original file is hash-checked\n"
     "    if (t.guest_size > t.size) {  // M36: every byte past the file's end belongs to a range\n"),
]


def main(cmd):
    text = SDK.read_bytes().decode("utf-8")
    if cmd == "status":
        print("patched" if MARK in text else ("production" if SDK.read_bytes() == PROD.read_bytes() else "other"))
        return 0
    if cmd == "revert":
        SDK.write_bytes(PROD.read_bytes())
        print("reverted: SDK copy == tools/m33_mod_overlay.h")
        return 0
    if cmd != "apply":
        raise SystemExit(__doc__)
    if SDK.read_bytes() != PROD.read_bytes():
        raise SystemExit("SDK copy differs from the production header; revert first")
    if "#include <cstdlib>" not in text:
        text = text.replace("#include <cstdint>\n", "#include <cstdint>\n#include <cstdlib>\n", 1)
    for old, new in EDITS:
        if text.count(old) != 1:
            raise SystemExit(f"anchor not unique: {old[:60]!r}")
        text = text.replace(old, new)
    SDK.write_bytes(text.encode("utf-8"))
    print("applied (test-only): SDK copy patched")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
