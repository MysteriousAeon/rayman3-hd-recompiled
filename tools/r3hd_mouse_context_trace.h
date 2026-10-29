// Read-only XAM poll context research. No mouse feature or guest writes.
// Enabled only for hidden runs; output must be a private local path.
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <windows.h>

namespace r3hd_mouse_trace {
inline void Poll(const uint8_t* base, uint32_t user, bool has_state) {
  static const char* path = std::getenv("R3HD_MOUSE_CONTEXT_TRACE");
  if (!path || !*path || !std::getenv("R3HD_NONINTRUSIVE") || user || !has_state) return;
  static FILE* out = std::fopen(path, "wb");
  if (!out) return;
  static bool header = false;
  if (!header) {
    std::fputs("qpc,frame,engine,menu_mode,menu_state,page,loaded,pause_word,cinematic,pad_selector,freeze,current,next\n", out);
    header = true;
  }
  auto word = [&](uint32_t address) -> uint32_t {
    uint8_t data[4]{};
    SIZE_T got = 0;
    if (!ReadProcessMemory(GetCurrentProcess(), base + address, data, 4, &got) || got != 4) return UINT32_MAX;
    return (uint32_t(data[0]) << 24) | (uint32_t(data[1]) << 16) | (uint32_t(data[2]) << 8) | data[3];
  };
  auto text = [&](uint32_t address, char (&value)[31]) {
    SIZE_T got = 0;
    if (!ReadProcessMemory(GetCurrentProcess(), base + address, value, 30, &got) || got != 30) value[0] = 0;
    value[30] = 0;
    for (unsigned i = 0; i < 30 && value[i]; ++i)
      if (value[i] < 32 || value[i] > 126 || value[i] == ',') value[i] = '?';
  };
  char current[31]{}, next[31]{};
  text(0x82C06221, current); text(0x82C0623F, next);
  LARGE_INTEGER now{};
  QueryPerformanceCounter(&now);
  const auto engine_word = word(0x82C06220);
  std::fprintf(out, "%lld,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%s,%s\n", now.QuadPart,
               word(0x82C06284), engine_word == UINT32_MAX ? UINT32_MAX : engine_word >> 24,
               word(0x82875F48), word(0x828760FC), word(0x828760EC), word(0x82875F34),
               word(0x82875F2C), word(0x82876194), word(0x828761BC),
               word(0x82C07D58) == UINT32_MAX ? UINT32_MAX : ((word(0x82C07D58) >> 8) & 255), current, next);
  std::fflush(out);
}
}  // namespace r3hd_mouse_trace
