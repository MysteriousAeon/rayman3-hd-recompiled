// Milestone 17: read-only per-frame guest trace for pinned ReXGlue c94f5eb. Installed as
// include/rex/m17_frame_trace.h by tools/m17_runtime_patch.py; one call site, the VdSwap export (guest thread
// that presents, once per guest frame).
//
// OFF unless R3HD_FRAME_TRACE names an output file. When on, every guest swap appends one record: the swap
// index, the host performance counter, the guest tick count, and the bytes of the guest memory ranges listed in
// "<output>.watch" (text, one "ADDRESS LENGTH" pair in hex per line; re-read when the file changes, so a
// test tool can add actor addresses after it has discovered them). Guest memory is only read, through
// ReadProcessMemory on the own process so an unmapped range yields a zero-length entry instead of a fault.
// Nothing the guest can observe is changed and nothing is written when the variable is absent.
// The output is game-derived: tools keep it under private/.
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace m17trace {
constexpr uint32_t kMaxRanges = 256;
constexpr uint32_t kMaxRangeBytes = 0x1000;

struct State {
  FILE* out = nullptr;
  std::string watch_path;
  std::vector<std::pair<uint32_t, uint32_t>> ranges;
  uint64_t watch_stamp = 0;
  uint32_t swap = 0;
  std::vector<uint8_t> scratch;
};

inline State* Open() {
  const char* path = std::getenv("R3HD_FRAME_TRACE");
  if (!path || !*path) return nullptr;
  FILE* f = std::fopen(path, "wb");
  if (!f) return nullptr;
  static State s;
  s.out = f;
  s.watch_path = std::string(path) + ".watch";
  s.scratch.resize(kMaxRangeBytes);
  std::setvbuf(f, nullptr, _IOFBF, 1 << 20);
  uint64_t frequency = 0;
#if defined(_WIN32)
  LARGE_INTEGER q;
  QueryPerformanceFrequency(&q);
  frequency = uint64_t(q.QuadPart);
#endif
  const uint32_t header[2] = {0x54463352u /* "R3FT" */, 1};
  std::fwrite(header, 4, 2, f);
  std::fwrite(&frequency, 8, 1, f);
  return &s;
}

#if defined(_WIN32)
inline void ReloadWatch(State& s) {
  WIN32_FILE_ATTRIBUTE_DATA info;
  if (!GetFileAttributesExA(s.watch_path.c_str(), GetFileExInfoStandard, &info)) return;
  const uint64_t stamp = (uint64_t(info.ftLastWriteTime.dwHighDateTime) << 32) ^ info.ftLastWriteTime.dwLowDateTime ^
                         (uint64_t(info.nFileSizeLow) << 40);
  if (stamp == s.watch_stamp) return;
  FILE* f = std::fopen(s.watch_path.c_str(), "r");
  if (!f) return;
  s.watch_stamp = stamp;
  s.ranges.clear();
  unsigned address = 0, length = 0;
  while (s.ranges.size() < kMaxRanges && std::fscanf(f, "%x %x", &address, &length) == 2) {
    if (length && length <= kMaxRangeBytes) s.ranges.emplace_back(address, length);
  }
  std::fclose(f);
}
#endif

// guest_base: host address of guest address 0. guest_ticks: the guest clock at the call.
inline void Swap(const uint8_t* guest_base, uint64_t guest_ticks) {
#if defined(_WIN32)
  static State* const s = Open();
  if (!s) return;
  if ((s->swap & 7) == 0) ReloadWatch(*s);
  LARGE_INTEGER now;
  QueryPerformanceCounter(&now);
  const uint32_t head[3] = {0x4D415246u /* "FRAM" */, s->swap, uint32_t(s->ranges.size())};
  std::fwrite(head, 4, 3, s->out);
  std::fwrite(&now.QuadPart, 8, 1, s->out);
  std::fwrite(&guest_ticks, 8, 1, s->out);
  const HANDLE self = GetCurrentProcess();
  for (const auto& [address, length] : s->ranges) {
    SIZE_T got = 0;
    if (!ReadProcessMemory(self, guest_base + address, s->scratch.data(), length, &got) || got != length) got = 0;
    const uint32_t entry[2] = {address, uint32_t(got)};
    std::fwrite(entry, 4, 2, s->out);
    if (got) std::fwrite(s->scratch.data(), 1, got, s->out);
  }
  if ((++s->swap & 63) == 0) std::fflush(s->out);
#else
  (void)guest_base;
  (void)guest_ticks;
#endif
}
}  // namespace m17trace
