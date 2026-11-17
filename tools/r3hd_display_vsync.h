// D-220: host display V-Sync for the D3D12 presenter (Windows), a launch-time player preference.
// Installed as include/rex/r3hd_display_vsync.h by tools/r3hd_display_vsync_patch.py.
//
// R3HD_DISPLAY_VSYNC=on (play.ps1 -VSync on; Settings > Display > V-Sync) selects synchronized presentation:
//   * Present(1, 0): one vertical blank per present, no DXGI_PRESENT_ALLOW_TEARING, no DXGI_PRESENT_RESTART.
//   * The paint connection reports implicit V-Sync, so the SDK presenter paints on the UI thread only and
//     turns its DXGI WaitForVBlank UI tick off (presenter.cpp GetDesiredPaintModeFromUIThread /
//     AreUITicksNeededFromUIThread). The guest-output (command-processor) thread never calls a blocking Present.
//   * The swap chain is created with DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT and a maximum frame
//     latency of 1; the UI thread waits on that object (bounded) before it paints, so at most one finished frame
//     is queued ahead of the display.
// Anything else (unset, "off") keeps the pinned presentation exactly: Present(0, RESTART | ALLOW_TEARING when the
// swap chain allows tearing), no waitable object, no implicit V-Sync.
//
// This is not the SDK's `vsync` cvar, which schedules the guest's vblank interrupt (E-265) and is never exposed.
// Guest timing is owned by the M16 deadline vblank worker (D-046) and does not read anything here.
// The driver or compositor may still override the requested behaviour (forced V-Sync, G-Sync/FreeSync, DWM).
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>

namespace r3hdvsync {

// DXGI values, repeated here so this header and its host test need no DXGI headers. The patch site
// static_asserts them against the SDK's DXGI definitions.
constexpr uint32_t kPresentRestart = 0x00000004u;        // DXGI_PRESENT_RESTART
constexpr uint32_t kPresentAllowTearing = 0x00000200u;   // DXGI_PRESENT_ALLOW_TEARING
constexpr uint32_t kSwapChainAllowTearing = 2048u;       // DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING
constexpr uint32_t kSwapChainLatencyWaitable = 64u;      // DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT
constexpr uint32_t kMaxFrameLatency = 1;
// Upper bound of one wait on the frame-latency object. A present normally retires within one refresh
// (<= 50 ms even at 20 Hz); the bound only keeps the UI thread alive if the object is never signalled
// (for example while the window cannot be presented).
constexpr uint32_t kLatencyWaitTimeoutMs = 100;

inline bool Parse(const char* value) { return value && !std::strcmp(value, "on"); }
inline bool Enabled() {
  static const bool on = Parse(std::getenv("R3HD_DISPLAY_VSYNC"));
  return on;
}

struct PresentArgs {
  uint32_t sync_interval;
  uint32_t flags;
};
// The Present arguments. Off reproduces the pinned call exactly.
inline PresentArgs Choose(bool vsync, bool swap_chain_allows_tearing) {
  if (vsync) return {1u, 0u};
  return {0u, kPresentRestart | (swap_chain_allows_tearing ? kPresentAllowTearing : 0u)};
}
// Swap-chain creation / ResizeBuffers flags (ResizeBuffers must repeat the creation flags).
inline uint32_t SwapChainFlags(bool vsync, bool allow_tearing) {
  return (allow_tearing ? kSwapChainAllowTearing : 0u) | (vsync ? kSwapChainLatencyWaitable : 0u);
}

// Observation only: one summary line per kWindow presents, from the presenting thread. Present call time,
// frame-latency wait time and HRESULT classes. Never waits or changes what is presented.
constexpr size_t kWindow = 600;
struct Stats {
  size_t used = 0;
  uint64_t windows = 0;
  uint32_t timeouts = 0, occluded = 0, failed = 0;
  std::array<uint32_t, kWindow> call_us{};
  std::array<uint32_t, kWindow> wait_us{};
};
struct Summary {
  uint64_t window = 0;
  uint32_t call_p50 = 0, call_p95 = 0, call_max = 0;
  uint32_t wait_p50 = 0, wait_p95 = 0, wait_max = 0;
  uint32_t timeouts = 0, occluded = 0, failed = 0;
};
inline uint32_t Clamp32(int64_t us) { return us < 0 ? 0u : us > 0xFFFFFFFFll ? 0xFFFFFFFFu : uint32_t(us); }
inline uint32_t Percentile(std::array<uint32_t, kWindow> v, size_t permille) {
  std::sort(v.begin(), v.end());
  return v[std::min(kWindow - 1, kWindow * permille / 1000)];
}
// hresult_class: 0 success, 1 occluded (DXGI_STATUS_OCCLUDED), 2 failure.
// Returns true when a window completed and `out` holds its summary.
inline bool Add(Stats& s, int64_t call_us, int64_t wait_us, bool wait_timed_out, int hresult_class, Summary& out) {
  s.call_us[s.used] = Clamp32(call_us);
  s.wait_us[s.used] = Clamp32(wait_us);
  ++s.used;
  if (wait_timed_out) ++s.timeouts;
  if (hresult_class == 1) ++s.occluded;
  if (hresult_class == 2) ++s.failed;
  if (s.used < kWindow) return false;
  out.window = ++s.windows;
  out.call_p50 = Percentile(s.call_us, 500);
  out.call_p95 = Percentile(s.call_us, 950);
  out.call_max = *std::max_element(s.call_us.begin(), s.call_us.end());
  out.wait_p50 = Percentile(s.wait_us, 500);
  out.wait_p95 = Percentile(s.wait_us, 950);
  out.wait_max = *std::max_element(s.wait_us.begin(), s.wait_us.end());
  out.timeouts = s.timeouts;
  out.occluded = s.occluded;
  out.failed = s.failed;
  s.used = 0;
  s.timeouts = s.occluded = s.failed = 0;
  return true;
}

}  // namespace r3hdvsync
