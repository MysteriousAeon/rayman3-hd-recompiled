// LM-2: identifies every Linux r3hd built from the diagnostic tree. Compiled only by tools/linux/game/CMakeLists.txt,
// never by the Windows or a production build. The string is also an exported symbol, so the ELF identifies itself
// without being run (`nm -D r3hd | grep r3hd_diagnostic_build`, `strings r3hd`).
#include <cstdio>

extern "C" __attribute__((used, visibility("default"))) const char r3hd_diagnostic_build[] =
    "R3HD DIAGNOSTIC BUILD: guest SEH disabled (generate_exception_handlers = false). "
    "Not compatibility evidence. Not for release.";

namespace {
struct DiagnosticBanner {
  DiagnosticBanner() {
    std::fprintf(stderr, "%s\n", r3hd_diagnostic_build);
    std::fflush(stderr);
  }
} diagnostic_banner;
}  // namespace
