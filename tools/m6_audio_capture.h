// Bounded private float32 PCM capture at the existing SDL submission boundary.
#pragma once
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
namespace m6audio {
inline void Capture(const float* data, unsigned count, unsigned channels) {
  static auto start=std::chrono::steady_clock::now();
  const char* path=std::getenv("R3HD_AUDIO_CAPTURE");
  if (!path) return;
  const char* after=std::getenv("R3HD_AUDIO_AFTER");
  double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
  if (seconds < (after ? std::atof(after) : 0)) return;
  static FILE* file=std::fopen(path,"wb");
  static unsigned written=0;
  if (!file) return;
  unsigned n=std::min(count,48000*channels*10-written);
  if (n) { std::fwrite(data,sizeof(float),n,file); written+=n; }
  if (written >= 48000*channels*10) { std::fclose(file); file=nullptr; }
}
}
