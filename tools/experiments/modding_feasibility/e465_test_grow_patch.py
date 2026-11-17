#!/usr/bin/env python3
"""E-465b (D-233) test-only growth gate for intro_10.lvl. NOT part of any build chain or release.

The production overlay (tools/m33_mod_overlay.h) is never edited. This script edits only the SDK's installed copy
(external/rexglue-sdk/include/rex/m33_mod_overlay.h, outside Git) for a private incremental build, and `revert`
copies the production header back byte for byte (then rebuild with tools\\build_incremental.bat).

With the patch, a `grow` record may name a file only if ALL hold, otherwise the plan is refused as before
(`grow_not_allowed`):
  - the environment variable R3HD_E465_TEST_GROW is exactly "intro_10.lvl" (unset by default);
  - the file name is intro_10.lvl (ASCII, any case) and its host size is exactly 7,661,836 bytes;
  - the growth is at most 65,536 bytes;
  - the file's first range starts at offset 0 and covers the whole original file, so the plan's game-bytes hash
    (FNV-1a 64) checks every original byte before anything is served (`e465_identity` otherwise).
Everything else (sizes, hashes, coverage of the tail, atomic refusal) is the production validation unchanged.

usage: e465_test_grow_patch.py apply | revert | status
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROD = ROOT / "tools" / "m33_mod_overlay.h"
SDK = ROOT / "external" / "rexglue-sdk" / "include" / "rex" / "m33_mod_overlay.h"
MARK = "E465_TEST_GROW"

EDITS = [
    ("  uint64_t guest_size = 0;    // M36: = size unless a `grow` record set it\n",
     "  uint64_t guest_size = 0;    // M36: = size unless a `grow` record set it\n"
     "  bool e465_test = false;     // E465_TEST_GROW (test-only build): grown by the E-465b gate\n"),
    ("// M36: whether the file name (ASCII, without case) is one that a `grow` record may name.\n",
     "// E465_TEST_GROW (test-only build, tools/experiments/modding_feasibility/e465_test_grow_patch.py): intro_10.lvl of\n"
     "// exactly 7,661,836 bytes, only while R3HD_E465_TEST_GROW is \"intro_10.lvl\".\n"
     "constexpr uint64_t kE465Size = 7661836, kE465MaxGrow = 65536;\n"
     "inline bool E465TestGrow(const std::filesystem::path& p, uint64_t size) {\n"
     "  const char* v = std::getenv(\"R3HD_E465_TEST_GROW\");\n"
     "  if (!v || std::strcmp(v, \"intro_10.lvl\") != 0 || size != kE465Size) return false;\n"
     "  const auto name = p.filename().native();\n"
     "  const char* want = \"intro_10.lvl\";\n"
     "  if (name.size() != std::strlen(want)) return false;\n"
     "  for (size_t i = 0; i < name.size(); ++i) {\n"
     "    auto c = name[i];\n"
     "    if (c >= 'A' && c <= 'Z') c = c + 32;\n"
     "    if (c != decltype(c)(want[i])) return false;\n"
     "  }\n"
     "  return true;\n"
     "}\n\n"
     "// M36: whether the file name (ASCII, without case) is one that a `grow` record may name.\n"),
    ("      if (!GrowAllowed(t.path)) return fail(\"grow_not_allowed\");\n"
     "      if (t.guest_size != t.size || !t.ranges.empty()) return fail(\"grow_order\");\n"
     "      if (guest <= t.size || guest - t.size > kMaxGrowBytes) return fail(\"grow_bounds\");\n",
     "      t.e465_test = !GrowAllowed(t.path) && E465TestGrow(t.path, t.size);  // E465_TEST_GROW\n"
     "      if (!GrowAllowed(t.path) && !t.e465_test) return fail(\"grow_not_allowed\");\n"
     "      if (t.guest_size != t.size || !t.ranges.empty()) return fail(\"grow_order\");\n"
     "      if (guest <= t.size || guest - t.size > (t.e465_test ? kE465MaxGrow : kMaxGrowBytes)) return fail(\"grow_bounds\");\n"),
    ("    if (t.guest_size > t.size) {  // M36: every byte past the file's end belongs to a range\n",
     "    if (t.e465_test && (t.ranges.empty() || t.ranges[0].offset != 0 || t.ranges[0].length < t.size))\n"
     "      return \"e465_identity\";  // E465_TEST_GROW: the whole original file is hash-checked\n"
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
