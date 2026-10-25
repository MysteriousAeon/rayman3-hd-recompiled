// Milestone 24: observational host event trace for pinned ReXGlue c94f5eb. Installed as
// include/rex/m24_event_trace.h by tools/m24_runtime_patch.py.
//
// OFF unless R3HD_M24_EVENTS names an output file. When on, each call site appends one fixed record: kind,
// thread id, the host performance counter and two words. It never waits on anything but its own short lock,
// reads no guest memory and changes nothing the guest or the renderer can observe. Reader:
// tools/m24_pause_resume.py. The file holds times, counts and pad button bits only, yet it describes a run of
// the game: tools keep it under private/.
//
// One thing is always on, in every run and session: the log line `M24 gpu_bound` (FenceWaited / FenceFrame
// below). It says that the command processor had to wait 4 ms or more, one or several times in a row, for the
// host GPU to finish a frame it was given three frames earlier, i.e. that the host GPU could not keep up.
// It is written one second after the last such wait and costs two counter reads around a wait that only
// happens when the GPU is behind.
//
// Kinds (a, b):
//   1 kVdSwap       guest thread, VdSwap export          (thread cycles / 1024 since its last VdSwap, 0)
//   2 kCpSwap       command processor, end of a swap     (draws since the last swap, copies << 16 | clears)
//   3 kPresent      UI thread, swap-chain Present        (microseconds spent inside Present, HRESULT)
//   4 kButtons      XamInputGetState, on change only     (button bits, left trigger << 8 | right trigger)
//   5 kVibration    XamInputSetState, on change only     (left motor, right motor)
//   6 kPipeline     host pipeline state object created   (microseconds spent creating it, 0)
//   7 kTextureLoad  host texture loaded from guest memory (0, 0)
//   8 kCpWait       command processor, a WAIT_REG_MEM on memory, at its start
//                                                         (microseconds waited, reference << 16 | first value & 0xFFFF)
//   9 kImportWait   any thread, a kernel import that took 300 us or more, at its start
//                                                         (microseconds inside the import, guest caller address)
//  10 kGpuWait      guest thread, one finished wait at the title's GPU-progress spin step that slept (D-037), at
//                   its start                             (microseconds, sleeps << 16 | longest sleep in microseconds)
//  11 kFenceWait    command processor, a wait for the host GPU to finish an earlier submission, at its start
//                                                         (microseconds, submissions the GPU was behind)
#pragma once
#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <mutex>
#include <rex/logging.h>
#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace m24ev {
enum Kind : uint32_t { kVdSwap = 1, kCpSwap = 2, kPresent = 3, kButtons = 4, kVibration = 5, kPipeline = 6, kTextureLoad = 7, kCpWait = 8, kImportWait = 9, kGpuWait = 10, kFenceWait = 11 };

struct Record {
  uint32_t kind;
  uint32_t thread;
  int64_t counter;
  uint32_t a;
  uint32_t b;
};
static_assert(sizeof(Record) == 24, "record layout is read by tools/m24_pause_resume.py");

// The SDK is several modules (runtime library, GPU library) and each has its own copy of this state, so the
// file is opened for shared appending and every write is one whole number of records: no header, no stream
// position. Each module's first record is kind 0 with the performance-counter frequency in (a, b).
struct State {
#if defined(_WIN32)
  HANDLE file = INVALID_HANDLE_VALUE;
#endif
  std::mutex lock;
  Record buffer[64];
  uint32_t used = 0;
};

inline int64_t Now() {
#if defined(_WIN32)
  LARGE_INTEGER now;
  QueryPerformanceCounter(&now);
  return now.QuadPart;
#else
  return 0;
#endif
}

inline int64_t Frequency() {
#if defined(_WIN32)
  static const int64_t frequency = [] {
    LARGE_INTEGER q;
    QueryPerformanceFrequency(&q);
    return int64_t(q.QuadPart);
  }();
  return frequency;
#else
  return 1;
#endif
}

inline State* Open() {
#if defined(_WIN32)
  const char* path = std::getenv("R3HD_M24_EVENTS");
  if (!path || !*path) return nullptr;
  const HANDLE file = CreateFileA(path, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS,
                                  FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file == INVALID_HANDLE_VALUE) return nullptr;
  static State s;
  s.file = file;
  const int64_t frequency = Frequency();
  s.buffer[s.used++] = Record{0, uint32_t(GetCurrentProcessId()), Now(), uint32_t(frequency), uint32_t(frequency >> 32)};
  return &s;
#else
  return nullptr;
#endif
}

inline State* Get() {
  static State* const s = Open();
  return s;
}

inline bool Enabled() { return Get() != nullptr; }

// Caller holds the lock.
inline void Flush(State& s) {
#if defined(_WIN32)
  if (!s.used) return;
  DWORD written = 0;
  WriteFile(s.file, s.buffer, DWORD(s.used * sizeof(Record)), &written, nullptr);
  s.used = 0;
#endif
}

// A frame's records reach the file with its last one (the swap on the command processor, the present on the
// UI thread), so at most a frame is lost when the process ends.
inline void EventAt(uint32_t kind, int64_t counter, uint32_t a, uint32_t b) {
  State* s = Get();
  if (!s) return;
#if defined(_WIN32)
  const Record r{kind, uint32_t(GetCurrentThreadId()), counter, a, b};
  std::lock_guard<std::mutex> guard(s->lock);
  s->buffer[s->used++] = r;
  if (s->used == 64 || kind == kCpSwap || kind == kPresent) Flush(*s);
#endif
}

inline void Event(uint32_t kind, uint32_t a = 0, uint32_t b = 0) {
  if (Enabled()) EventAt(kind, Now(), a, b);
}

// Processor cycles the calling thread has used since its previous call, in units of 1024 cycles (0 on the first
// call): tells a frame the thread spent computing from one it spent waiting.
inline uint32_t ThreadKiloCyclesSinceLast() {
#if defined(_WIN32)
  thread_local ULONG64 last = 0;
  ULONG64 now = 0;
  if (!QueryThreadCycleTime(GetCurrentThread(), &now)) return 0;
  const ULONG64 delta = last ? (now - last) >> 10 : 0;
  last = now;
  return delta > 0xFFFFFFFFull ? 0xFFFFFFFFu : uint32_t(delta);
#else
  return 0;
#endif
}

// Microseconds since `start` (a value of Now()), saturated.
inline uint32_t MicrosSince(int64_t start) {
  const int64_t us = (Now() - start) * 1000000 / Frequency();
  return us < 0 ? 0u : us > 0xFFFFFFFFll ? 0xFFFFFFFFu : uint32_t(us);
}

// A kernel import that took at least kSlowImportUs: where a guest thread waited. The import's name is recorded
// as a 24-bit FNV-1a hash in the upper bits of the kind (the reader hashes the import list).
constexpr uint32_t kSlowImportUs = 300;
inline uint32_t NameHash(const char* s) {
  uint32_t h = 2166136261u;
  while (*s) h = (h ^ uint8_t(*s++)) * 16777619u;
  return h & 0xFFFFFFu;
}
struct ImportTimer {
  int64_t start;
  const char* name;
  uint32_t caller;
  ImportTimer(const char* name_, uint32_t caller_) : start(Enabled() ? Now() : 0), name(name_), caller(caller_) {}
  ~ImportTimer() {
    if (!start) return;
    const uint32_t us = MicrosSince(start);
    if (us >= kSlowImportUs) EventAt(uint32_t(kImportWait) | (NameHash(name) << 8), start, us, caller);
  }
};

// Host GPU behind (always on, command-processor thread only). A wait of kFenceSlowUs or more for the Direct3D
// submission fence opens or extends a burst; FenceFrame, called once per guest frame, logs the burst one second
// after its last wait: how many frames waited, for how long in all, the longest wait, and the burst's span.
constexpr uint32_t kFenceSlowUs = 4000;
struct FenceBurst {
  int64_t first = 0, last = 0;
  uint32_t waits = 0, longest_us = 0;
  uint64_t total_us = 0;
};
inline FenceBurst& Burst() {
  static FenceBurst b;
  return b;
}
inline void FenceWaited(int64_t start, uint32_t behind) {
  const uint32_t us = MicrosSince(start);
  if (Enabled()) EventAt(kFenceWait, start, us, behind);
  if (us < kFenceSlowUs) return;
  FenceBurst& b = Burst();
  if (!b.waits) b.first = start;
  b.last = Now();
  ++b.waits;
  b.total_us += us;
  if (us > b.longest_us) b.longest_us = us;
}
inline void FenceFrame() {
  FenceBurst& b = Burst();
  if (!b.waits) return;
  if (Now() - b.last < Frequency()) return;
  REXLOG_INFO("M24 gpu_bound waits={} total_ms={} longest_ms={} span_ms={}", b.waits, b.total_us / 1000,
              b.longest_us / 1000, (b.last - b.first) * 1000 / Frequency());
  b = FenceBurst{};
}

// Pad state and vibration are polled every frame: only a change is an event.
inline void Buttons(uint32_t buttons, uint32_t triggers) {
  if (!Enabled()) return;
  static std::atomic<uint64_t> last{~0ull};
  const uint64_t value = (uint64_t(buttons) << 32) | triggers;
  if (last.exchange(value) != value) EventAt(kButtons, Now(), buttons, triggers);
}

inline void Vibration(uint32_t left, uint32_t right) {
  if (!Enabled()) return;
  static std::atomic<uint64_t> last{~0ull};
  const uint64_t value = (uint64_t(left) << 32) | right;
  if (last.exchange(value) != value) EventAt(kVibration, Now(), left, right);
}
}  // namespace m24ev
