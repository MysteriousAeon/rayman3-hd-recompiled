// LM-A: identifies every Linux r3hd built from the production tree on the portable M4 backend. Compiled only by
// tools/linux/game/CMakeLists.txt for a tree marked LMA_PORTABLE_M4.txt; never by the Windows build. The string is an
// exported symbol too, so the ELF identifies itself without being run.
#include <cstdio>

extern "C" __attribute__((used, visibility("default"))) const char r3hd_lma_build[] =
    "R3HD LINUX PREVIEW (LM-A): portable M4 guest exceptions; hardware-fault conversion not implemented. "
    "Not a release.";

namespace {
struct LmaBanner {
  LmaBanner() {
    std::fprintf(stderr, "%s\n", r3hd_lma_build);
    std::fflush(stderr);
  }
} lma_banner;
}  // namespace
