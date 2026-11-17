#include "bridge.h"
#include <exception>

namespace {
thread_local unsigned unwind_count = 0;
struct LibraryLifetime {
  ~LibraryLifetime() { if (std::uncaught_exceptions() != 0) ++unwind_count; }
};
}

// Deliberately lets the caller's typed exception unwind through this DSO.
extern "C" PGEH_BRIDGE_API void pgeh_bridge(void (*callback)(void*), void* context) {
  LibraryLifetime lifetime; // Prevent a tail call from erasing the DSO unwind frame.
  callback(context);
}
extern "C" PGEH_BRIDGE_API unsigned pgeh_bridge_unwind_count() noexcept { return unwind_count; }
