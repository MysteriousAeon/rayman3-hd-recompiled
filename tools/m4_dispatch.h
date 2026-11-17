// LM-A (D4): the call from FunctionDispatcher::Execute into guest code (installed into the SDK by
// tools/m4_runtime_patch.py). On Windows it is the call itself, so the SDK file's preprocessed tokens are unchanged
// (the include replaces a blank line and the macro the call line: no line moves either). With the portable backend
// the call runs inside an M4HostBoundary: a guest exception transfer may not cross it and fails fast, naming it.
#pragma once
#if defined(_WIN32) && !defined(R3HD_M4_PORTABLE)
#define M4_DISPATCH(fn, ctx, base, address) fn(ctx, base)
#else
#include <rex/m4_seh.h>
#define M4_DISPATCH(fn, ctx, base, address) \
  do { M4HostBoundary m4_boundary("FunctionDispatcher::Execute", (address)); fn(ctx, base); } while (0)
#endif
