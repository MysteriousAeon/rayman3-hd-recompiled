// M22: silent audio instrumentation and the hidden-run mute. Installed as include/rex/m22_audio_probe.h by
// tools/m22_runtime_patch.py; used from the SDL audio driver and the XMA context only.
//
// 1. Hidden test runs (R3HD_NONINTRUSIVE) are inaudible: the SDL stream gain is 0, so nothing reaches the
//    speakers while every sample is still mixed, counted and (when asked) captured exactly as before.
//    R3HD_AUDIO_AUDIBLE=1 restores the audible hidden run. A visible session is never muted by this.
// 2. R3HD_M22_AUDIO=1 writes m22_audio.txt in the process working directory (a private run directory):
//    statistics only, no samples.
//      out T_US Q PEAK RMS ZEROS STEP CLIENT   one line per output callback frame (256 sample frames at 48 kHz)
//                                       of one render client (the title opens two: game and movie):
//                                       Q 1 = a mixed guest frame, 0 = nothing queued (driver wrote silence);
//                                       ZEROS = samples that are exactly 0; STEP = largest sample-to-sample
//                                       difference including the join with the previous frame
//      xma T_US CTX start               first decoded frame of a context after its reset
//      xma T_US CTX end FRAMES MS       a context reset after it decoded FRAMES frames over MS milliseconds
//      xma T_US CTX starve MS           an enabled context whose two input buffers were both consumed got
//                                       input again after MS milliseconds without a reset in between
//      xma T_US CTX error CODE          the decoder refused a frame
//    It never changes what is decoded, mixed or submitted.
#pragma once
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <mutex>

namespace m22audio {
inline bool HiddenMute() {
  static const bool mute = std::getenv("R3HD_NONINTRUSIVE") && !std::getenv("R3HD_AUDIO_AUDIBLE");
  return mute;
}

inline std::FILE* File() {
  static std::FILE* file = std::getenv("R3HD_M22_AUDIO") ? std::fopen("m22_audio.txt", "w") : nullptr;
  return file;
}
inline std::mutex& Lock() { static std::mutex m; return m; }
inline long long NowUs() {
  static const auto start = std::chrono::steady_clock::now();
  return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - start).count();
}

inline void Output(const void* client, const float* data, int count, int channels, bool queued) {
  std::FILE* file = File();
  if (!file) return;
  float peak = 0, step = 0;
  double energy = 0;
  int zeros = 0;
  std::lock_guard<std::mutex> guard(Lock());
  // The title opens two render clients (game, movie); each gets a tag and its own history.
  static const void* clients[4] = {};
  int tag = 0;
  while (tag < 3 && clients[tag] && clients[tag] != client) ++tag;
  clients[tag] = client;
  // Interleaved: compare a sample with the previous one of the same channel.
  static float last4[4][8] = {};
  float* last2 = last4[tag];
  channels = std::clamp(channels, 1, 8);
  for (int i = 0; i < count; ++i) {
    const float v = data[i];
    peak = std::max(peak, std::abs(v));
    energy += double(v) * v;
    zeros += v == 0;
    step = std::max(step, std::abs(v - last2[i % channels]));
    last2[i % channels] = v;
  }
  std::fprintf(file, "out %lld %d %.5f %.5f %d %.5f %d\n", NowUs(), queued ? 1 : 0, peak,
               count ? std::sqrt(energy / count) : 0.0, zeros, step, tag);
}

struct Context {
  bool started = false, starving = false;
  long long start_us = 0, starve_us = 0;
  unsigned frames = 0;
};
inline Context& Ctx(uint32_t id) { static Context c[512]; return c[id & 511]; }

inline void XmaFrame(uint32_t id) {
  std::FILE* file = File();
  if (!file) return;
  std::lock_guard<std::mutex> guard(Lock());
  Context& c = Ctx(id);
  ++c.frames;
  if (c.started) return;
  c.started = true; c.start_us = NowUs();
  std::fprintf(file, "xma %lld %u start\n", c.start_us, id);
}
inline void XmaReset(uint32_t id) {
  std::FILE* file = File();
  if (!file) return;
  std::lock_guard<std::mutex> guard(Lock());
  Context& c = Ctx(id);
  if (c.started) {
    const long long now = NowUs();
    std::fprintf(file, "xma %lld %u end %u %lld\n", now, id, c.frames, (now - c.start_us) / 1000);
  }
  c = Context();
}
// Called from Work() with the context's input state before decoding.
inline void XmaInput(uint32_t id, bool any_input_valid) {
  std::FILE* file = File();
  if (!file) return;
  std::lock_guard<std::mutex> guard(Lock());
  Context& c = Ctx(id);
  if (!c.started) return;
  if (!any_input_valid) {
    if (!c.starving) { c.starving = true; c.starve_us = NowUs(); }
    return;
  }
  if (c.starving) {
    c.starving = false;
    const long long now = NowUs();
    std::fprintf(file, "xma %lld %u starve %lld\n", now, id, (now - c.starve_us) / 1000);
  }
}
inline void XmaError(uint32_t id, int code) {
  std::FILE* file = File();
  if (!file) return;
  std::lock_guard<std::mutex> guard(Lock());
  std::fprintf(file, "xma %lld %u error %d\n", NowUs(), id, code);
}
}  // namespace m22audio
