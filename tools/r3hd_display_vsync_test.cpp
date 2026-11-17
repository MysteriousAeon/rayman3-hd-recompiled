// D-220 host test of tools/r3hd_display_vsync.h: request parsing, Present arguments, swap-chain flags and the
// observation statistics. No DXGI, window, device or game. Prints R3HD_DISPLAY_VSYNC_TEST PASS n.
#include <cstdio>

#include "r3hd_display_vsync.h"

static int g_checks = 0, g_fails = 0;
static void Check(bool ok, const char* what) {
  ++g_checks;
  if (!ok) {
    ++g_fails;
    std::printf("FAIL %s\n", what);
  }
}

int main() {
  using namespace r3hdvsync;
  // Only the exact launcher value turns it on.
  Check(Parse("on"), "on");
  Check(!Parse(nullptr) && !Parse("") && !Parse("off") && !Parse("On") && !Parse("1") && !Parse("true") &&
            !Parse("on "),
        "everything else is off");

  // Off is the pinned call: Present(0, RESTART | ALLOW_TEARING when the swap chain allows it).
  PresentArgs a = Choose(false, true);
  Check(a.sync_interval == 0 && a.flags == (0x4u | 0x200u), "off with tearing = pinned");
  a = Choose(false, false);
  Check(a.sync_interval == 0 && a.flags == 0x4u, "off without tearing = pinned");
  // On: one vertical blank, never ALLOW_TEARING (invalid with a nonzero interval) or RESTART.
  for (bool tearing : {false, true}) {
    a = Choose(true, tearing);
    Check(a.sync_interval == 1 && a.flags == 0, "on = Present(1, 0)");
    Check((a.flags & kPresentAllowTearing) == 0, "on never allows tearing");
  }

  // Swap-chain flags: off reproduces the pinned creation / ResizeBuffers flags.
  Check(SwapChainFlags(false, true) == 2048u && SwapChainFlags(false, false) == 0u, "off flags pinned");
  Check(SwapChainFlags(true, true) == (2048u | 64u) && SwapChainFlags(true, false) == 64u, "on adds waitable");
  Check(kMaxFrameLatency == 1 && kLatencyWaitTimeoutMs >= 50 && kLatencyWaitTimeoutMs <= 250, "bounds");

  // Statistics: one summary per window, counters reset, percentiles of the window.
  Stats s;
  Summary out;
  int summaries = 0;
  for (size_t i = 0; i < kWindow; ++i) {
    bool done = Add(s, int64_t(i), int64_t(kWindow - 1 - i), i < 3, i % 100 == 0 ? 1 : (i == 7 ? 2 : 0), out);
    summaries += done;
    Check(done == (i == kWindow - 1), "summary only at the window end");
  }
  Check(summaries == 1 && out.window == 1, "first window");
  Check(out.call_p50 == kWindow / 2 && out.call_p95 == kWindow * 95 / 100 && out.call_max == kWindow - 1,
        "call percentiles");
  Check(out.wait_p50 == kWindow / 2 && out.wait_max == kWindow - 1, "wait percentiles");
  Check(out.timeouts == 3 && out.occluded == kWindow / 100 && out.failed == 1, "counters");
  for (size_t i = 0; i < kWindow; ++i) summaries += Add(s, -5, 0x7FFFFFFFFFFFll, false, 0, out);
  Check(summaries == 2 && out.window == 2, "second window");
  Check(out.timeouts == 0 && out.occluded == 0 && out.failed == 0, "counters reset");
  Check(out.call_max == 0 && out.wait_max == 0xFFFFFFFFu, "clamped to 32 bits");

  std::printf("R3HD_DISPLAY_VSYNC_TEST %s %d checks\n", g_fails ? "FAIL" : "PASS", g_checks);
  return g_fails ? 1 : 0;
}
