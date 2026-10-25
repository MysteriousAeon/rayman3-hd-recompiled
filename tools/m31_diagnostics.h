// M31 (D-068): bounded diagnostics of a playtest session (tools/m31_runtime_patch.py).
//
// A human session (R3HD_PLAY, set by tools/play.ps1) with standard diagnostics logs the first kFirst occurrences of
// a repetitive, known-benign runtime line and then every kEvery-th one, with the running count, instead of every
// one. Measured on the M30 sessions: the invalid texture-fetch pair was 63 % of all lines (about 460 bytes per
// second of play together with the periodic lines). R3HD_DIAGNOSTICS=detailed (play.ps1 -Diagnostics detailed)
// keeps every line, and a hidden test run (no R3HD_PLAY) is never affected: its counters read the full census.
// Logging only: nothing the title sees, no scheduling, no generated code.
#pragma once

#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <cstring>

namespace m31diag {

constexpr uint64_t kFirst = 8;
constexpr uint64_t kEvery = 1000;

inline bool Quiet() {
  static const bool quiet = [] {
    const char* play = std::getenv("R3HD_PLAY");
    const char* level = std::getenv("R3HD_DIAGNOSTICS");
    return play && *play && !(level && std::strcmp(level, "detailed") == 0);
  }();
  return quiet;
}

// Counts one occurrence; true when it is to be logged. *count receives the running count.
inline bool Sample(std::atomic<uint64_t>& counter, uint64_t* count = nullptr) {
  uint64_t n = counter.fetch_add(1, std::memory_order_relaxed) + 1;
  if (count) *count = n;
  return !Quiet() || n <= kFirst || n % kEvery == 0;
}

// True for a logged occurrence that stands for others (the line then names the count).
inline bool Sampled(uint64_t n) { return Quiet() && n > kFirst; }

}  // namespace m31diag
