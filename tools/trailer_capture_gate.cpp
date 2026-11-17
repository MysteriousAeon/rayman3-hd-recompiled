// Private trailer experiment. Only built by trailer_capture_prepare.py, never the normal build.
#ifndef R3HD_PRIVATE_CAPTURE
#error This source requires the dedicated private capture build
#endif
#include <rex/ppc/context.h>
#include <rex/system/kernel_state.h>
#include <rex/logging.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "trailer_capture_input.h"

// The marker is logged from a live hook so the linker must retain it in the PE.
static constexpr char kCaptureIdentity[] = "R3HD_PRIVATE_CAPTURE_BUILD_V1";

void TrailerCaptureGate(PPCRegister& r11) {
  static bool initialized = false, previous = false;
  static unsigned sequence = 0;
  static auto next = std::chrono::steady_clock::time_point{};
  const auto now = std::chrono::steady_clock::now();
  const auto* base = REX_KERNEL_MEMORY()->virtual_membase();
  auto word = [&](unsigned a) { unsigned v; std::memcpy(&v, base + a, 4); return _byteswap_ulong(v); };
  char level[16] = {};
  std::memcpy(level, base + 0x82C06221, 15);
  for (char& c : level) if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
  const bool ordinary = level[0] && std::strcmp(level, "menumap") &&
      std::strcmp(level, "endgame") && std::strcmp(level, "staff") &&
      word(0x82875F2C) == 0 && word(0x82876194) == 0;
  if (!initialized) {
    REXLOG_INFO("{} gate=821A0158 startup=visible shortcut=F5 control={}", kCaptureIdentity,
                std::getenv("R3HD_CAPTURE_CONTROL") ? "file" : "none");
    initialized = true;
  }
  trailer_capture::state.Context(ordinary, level);
  // Private ephemeral command channel: SEQUENCE hide|show. No input injection or guest-memory writes.
  if (now >= next) {
    next = now + std::chrono::milliseconds(50);
    if (const char* path = std::getenv("R3HD_CAPTURE_CONTROL")) {
      if (FILE* f = std::fopen(path, "r")) {
        unsigned n = 0; char command[8] = {};
        const bool valid = std::fscanf(f, "%u %7s", &n, command) == 2;
        std::fclose(f);
        if (valid && n > sequence && (!std::strcmp(command, "hide") || !std::strcmp(command, "show"))) {
          sequence = n;
          trailer_capture::state.Command(!std::strcmp(command, "hide"));
          REXLOG_INFO("TRAILER_GATE command={} hidden={} ordinary={}", sequence, trailer_capture::state.Hidden(), ordinary);
        }
      }
    }
  }
  const bool hidden = trailer_capture::state.Hidden();
  if (hidden != previous) {
    REXLOG_INFO("TRAILER_GATE hidden={} native={} level={}", hidden, r11.u32, level);
    previous = hidden;
  }
  // Only the register loaded for this comparison changes. The native flag and updates remain untouched.
  if (hidden) r11.u64 = 0;
}
