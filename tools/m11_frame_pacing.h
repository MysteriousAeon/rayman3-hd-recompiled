// Milestone 11 observational frame-pacing statistics for pinned ReXGlue c94f5eb.
// Installed as include/rex/m11_frame_pacing.h by tools/m11_runtime_patch.py. Two call sites: the end of the
// backend's guest swap handling (command-processor thread) and the host swap-chain present (UI thread).
// It measures the interval between consecutive calls with the performance counter and logs one summary line
// per kWindow intervals. It never waits, never changes what is rendered or when, and allocates nothing.
#pragma once
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <rex/logging.h>

namespace m11pace {
constexpr size_t kWindow = 600;

struct Series {
  const char* name;
  std::chrono::steady_clock::time_point last{};
  bool started = false;
  size_t used = 0;
  uint64_t windows = 0;
  std::array<uint32_t, kWindow> us{};
};

// Each series is touched by one thread only (see the call sites).
inline void Tick(Series& s) {
  auto now = std::chrono::steady_clock::now();
  if (!s.started) {
    s.started = true;
    s.last = now;
    return;
  }
  uint64_t us = uint64_t(std::chrono::duration_cast<std::chrono::microseconds>(now - s.last).count());
  s.last = now;
  s.us[s.used++] = us > 0xFFFFFFFFull ? 0xFFFFFFFFu : uint32_t(us);
  if (s.used < kWindow) return;
  s.used = 0;
  std::array<uint32_t, kWindow> v = s.us;
  uint64_t sum = 0;
  unsigned over20 = 0, over33 = 0, over50 = 0, over100 = 0;
  for (uint32_t x : v) {
    sum += x;
    over20 += x > 20000;
    over33 += x > 33400;
    over50 += x > 50000;
    over100 += x > 100000;
  }
  // M16: spread and frame-to-frame pattern of the regular intervals (within a quarter of the window median, so
  // loads and stalls do not count): standard deviation, and lag-1 autocorrelation in thousandths. A value near
  // -500 means each frame's time has its own independent error around an exact schedule.
  std::array<uint32_t, kWindow> ordered = s.us;
  std::sort(v.begin(), v.end());
  const double median = double(v[kWindow / 2]);
  double core[kWindow];
  size_t core_n = 0;
  for (uint32_t x : ordered) {
    if (double(x) >= median * 0.75 && double(x) <= median * 1.25) core[core_n++] = double(x);
  }
  double core_mean = 0, core_var = 0, core_cov = 0;
  for (size_t i = 0; i < core_n; ++i) core_mean += core[i];
  core_mean = core_n ? core_mean / double(core_n) : 0;
  for (size_t i = 0; i < core_n; ++i) core_var += (core[i] - core_mean) * (core[i] - core_mean);
  for (size_t i = 0; i + 1 < core_n; ++i) core_cov += (core[i] - core_mean) * (core[i + 1] - core_mean);
  const double core_sd = core_n ? std::sqrt(core_var / double(core_n)) : 0;
  const int lag1_milli = (core_n > 2 && core_var > 0) ? int(1000.0 * core_cov / core_var) : 0;
  REXLOG_INFO("M11 pacing series={} window={} n={} mean_us={} min_us={} p50_us={} p95_us={} p99_us={} max_us={} "
              "over_20ms={} over_33ms={} over_50ms={} over_100ms={} core_n={} core_sd_us={} lag1_milli={}",
              s.name, ++s.windows, kWindow, sum / kWindow, v.front(), v[kWindow / 2], v[kWindow * 95 / 100],
              v[kWindow * 99 / 100], v.back(), over20, over33, over50, over100, core_n, uint32_t(core_sd),
              lag1_milli);
}

inline void GuestSwap() {
  static Series s{"guest_swap"};
  Tick(s);
}
inline void HostPresent() {
  static Series s{"host_present"};
  Tick(s);
}
}  // namespace m11pace
