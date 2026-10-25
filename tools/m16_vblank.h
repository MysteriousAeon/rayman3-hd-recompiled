// Milestone 16 (D-043): deadline wait for the guest vblank worker of pinned ReXGlue c94f5eb, with lateness
// statistics. Installed as include/rex/m16_vblank.h by tools/m16_runtime_patch.py.
//
// The pinned worker polls the guest clock in a loop around a 1 ms sleep and raises the guest vblank interrupt
// when a 1/60 s interval has passed. The schedule itself is exact (the reference time advances by whole
// intervals), but each interrupt is delivered up to one host sleep quantum late, independently per frame. The
// title paces its frames on that interrupt, so every frame start, guest swap and host present carried that
// error (human session 20261009-204726: present interval sd 0.68 ms, lag-1 autocorrelation -0.5).
//
// WaitForDeadline sleeps on a high-resolution waitable timer until shortly before the next deadline and then
// yields the processor until the deadline. It changes when the host thread wakes, nothing else: the interval,
// the interrupt, the counter and everything the guest can observe are the pinned code's.
//
// It is ON by default since M17 (D-046); R3HD_VBLANK=poll selects the pinned 1 ms polling sleeps for comparison.
// Reason (E-93 .. E-95): the title derives its simulation step from the measured frame time (clamped below at
// 16 ms, averaged over five frames, truncated). An exact 60 Hz vblank gives a constant 16 ms step; the polling
// lateness spread the measured times over 14..19 ms and made the step 17 ms on about one frame in eight, which
// changed scripted timing chains from the first seconds of a level (the M16 `menu_10` difference).
// R3HD_VBLANK_SPIN_US sets the final yield span (default 600).
#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <rex/logging.h>
#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace m16vb {
constexpr size_t kWindow = 600;

inline bool Precise() {
  static const bool v = [] {
    const char* e = std::getenv("R3HD_VBLANK");
    return !(e && !std::strcmp(e, "poll"));
  }();
  return v;
}

inline uint64_t SpinUs() {
  static const uint64_t v = [] {
    const char* e = std::getenv("R3HD_VBLANK_SPIN_US");
    long n = e ? std::atol(e) : 600;
    return uint64_t(std::clamp<long>(n, 0, 2000));
  }();
  return v;
}

// Lateness of one vblank against its scheduled time. Called by the worker thread only.
inline void Late(uint64_t late_ticks, uint64_t tick_frequency) {
  static std::array<uint32_t, kWindow> us{};
  static size_t used = 0;
  static uint64_t windows = 0;
  uint64_t v = tick_frequency ? late_ticks * 1000000ull / tick_frequency : 0;
  us[used++] = v > 0xFFFFFFFFull ? 0xFFFFFFFFu : uint32_t(v);
  if (used < kWindow) return;
  used = 0;
  std::array<uint32_t, kWindow> s = us;
  std::sort(s.begin(), s.end());
  uint64_t sum = 0;
  for (uint32_t x : s) sum += x;
  REXLOG_INFO("M16 vblank mode={} window={} n={} late_mean_us={} late_p50_us={} late_p95_us={} late_p99_us={} "
              "late_max_us={} spin_us={}",
              Precise() ? "deadline" : "poll", ++windows, kWindow, sum / kWindow, s[kWindow / 2],
              s[kWindow * 95 / 100], s[kWindow * 99 / 100], s.back(), Precise() ? SpinUs() : 0);
}

// One call per iteration of the worker loop, in place of its 1 ms sleep. Returns at the deadline, or earlier
// after at most about 4 ms so the caller's exit flag and interval setting stay live.
template <typename QueryTicks>
inline void WaitForDeadline(uint64_t deadline_ticks, uint64_t tick_frequency, QueryTicks&& query) {
#if defined(_WIN32)
  static thread_local HANDLE timer =
      CreateWaitableTimerExW(nullptr, nullptr, 0x00000002 /* high resolution */, TIMER_ALL_ACCESS);
  uint64_t now = query();
  if (now >= deadline_ticks || !tick_frequency) return;
  uint64_t remaining_us = (deadline_ticks - now) * 1000000ull / tick_frequency;
  const uint64_t spin_us = SpinUs();
  if (remaining_us > spin_us) {
    uint64_t sleep_us = std::min<uint64_t>(remaining_us - spin_us, 4000);
    if (timer) {
      LARGE_INTEGER due;
      due.QuadPart = -int64_t(sleep_us) * 10;
      SetWaitableTimer(timer, &due, 0, nullptr, nullptr, FALSE);
      WaitForSingleObject(timer, 10);
    } else {
      ::Sleep(1);
    }
    if (remaining_us - spin_us > 4000) return;  // not the last leg before the deadline
    now = query();
  }
  // Bounded by host time as well, in case the guest clock is scaled or stopped.
  LARGE_INTEGER f, t0, t;
  QueryPerformanceFrequency(&f);
  QueryPerformanceCounter(&t0);
  const long long limit = f.QuadPart * 3 / 1000;
  while (now < deadline_ticks) {
    YieldProcessor();
    QueryPerformanceCounter(&t);
    if (t.QuadPart - t0.QuadPart > limit) break;
    now = query();
  }
#else
  (void)deadline_ticks;
  (void)tick_frequency;
  (void)query;
#endif
}

#if defined(_WIN32)
// Signalled after every guest vblank (counter incremented, interrupt callback run).
inline HANDLE VblankEvent() {
  static const HANDLE event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
  return event;
}
#endif

inline void SignalVblank() {
#if defined(_WIN32)
  if (Precise()) SetEvent(VblankEvent());
#endif
}

// The command processor's WAIT_REG_MEM packet polls a register or a memory word and sleeps `wait / 0x100`
// milliseconds between polls. The title issues one such wait per frame (released by the vblank), so the poll
// period was a second independent per-frame delay. This waits the same time at most, but returns as soon as a
// vblank has been delivered; the caller's poll loop and its exit condition are unchanged. Returns false when
// the pinned sleep must be used.
inline bool RegisterWait(uint32_t wait, bool is_memory, uint32_t poll_address) {
  static uint64_t count = 0;  // command-processor thread only
  uint64_t n = ++count;
  if ((n & (n - 1)) == 0) {
    REXLOG_INFO("M16 cp_wait mode={} sleeps={} wait_ms={} memory={} address={:08X}",
                Precise() ? "vblank_event" : "sleep", n, wait / 0x100, is_memory, poll_address);
  }
#if defined(_WIN32)
  if (Precise()) {
    WaitForSingleObject(VblankEvent(), wait / 0x100);
    return true;
  }
#endif
  return false;
}
}  // namespace m16vb
