// Milestone 44 (D-081): optional gameplay voice subtitles for pinned ReXGlue c94f5eb. Installed as
// include/rex/m44_gameplay_subtitles.h by tools/m44_runtime_patch.py; one call site, the VdSwap export (once per
// guest frame), in front of the M17 frame trace.
//
// The title shows a voiced line's subtitle (the sound bank's `subtitle` handle, drawn on the banner text object)
// during ordinary gameplay only for the lines of its own list (8212E260): its per-frame update 8212F150 sets the
// banner's visible word 828865D0 to 1 while the line plays only when the word 82837348 is 0, the cinematic state
// 82876194 is not 0, or the line is on that list. 82837348 is 1 in the image's data and the title never writes it
// (RE_NOTES "M44"). The restriction is the title's design, so Vanilla and HD+ keep it.
//
// R3HD_GAMEPLAY_SUBTITLES=all (experimental, Custom only) stores 0 in 82837348 so that the title's own update shows
// every voiced subtitle it has started, with its own text, start (voice start) and end (2 s after the voice
// ends), the Subtitles option still deciding whether the banner is drawn. Nothing else is written. The store is
// made only while the guest image still holds the two instructions of 8212F150 that read the word and the word
// holds 0 or 1; otherwise nothing is written and one `state=refused_*` line says why.
// Without the variable (or with "original") this costs one flag test per frame and writes nothing.
#pragma once
#include <cstdint>
#include <cstdlib>
#include <cstring>

namespace m44sub {
constexpr uint32_t kRestriction = 0x82837348;  // read once per frame by 8212F150 (lwz r11, 0x7348(r11))
constexpr uint32_t kGuardAddress = 0x8212F1F4;  // lis r11, -0x7d7d ; lwz r11, 0x7348(r11)
constexpr uint32_t kGuard[2] = {0x3D608283u, 0x816B7348u};

// "all" selects the enhancement; anything else, or no variable, is the title's own behaviour.
inline bool Selected(const char* value) { return value && std::strcmp(value, "all") == 0; }
inline bool Enabled() {
  static const bool on = Selected(std::getenv("R3HD_GAMEPLAY_SUBTITLES"));
  return on;
}
inline const char* ModeName() { return Enabled() ? "all" : "original"; }

inline uint32_t LoadBE(const uint8_t* base, uint32_t address) {
  uint32_t v;
  std::memcpy(&v, base + address, 4);
  return (v >> 24) | ((v >> 8) & 0xFF00u) | ((v << 8) & 0xFF0000u) | (v << 24);
}

enum class Result { kOff, kKept, kApplied, kRefusedGuard, kRefusedValue };
inline const char* Name(Result r) {
  switch (r) {
    case Result::kOff: return "off";
    case Result::kKept: return "kept";
    case Result::kApplied: return "applied";
    case Result::kRefusedGuard: return "refused_guard";
    case Result::kRefusedValue: return "refused_value";
  }
  return "?";
}

// One frame's decision for the word at kRestriction; `write` is called with the value to store.
// Pure apart from `write`; tools/m44_regression.py mirrors these rules.
template <typename Write>
inline Result Step(const uint8_t* base, bool enabled, Write&& write) {
  if (!enabled) return Result::kOff;
  if (LoadBE(base, kGuardAddress) != kGuard[0] || LoadBE(base, kGuardAddress + 4) != kGuard[1])
    return Result::kRefusedGuard;
  const uint32_t value = LoadBE(base, kRestriction);
  if (value == 0) return Result::kKept;
  if (value != 1) return Result::kRefusedValue;
  write(kRestriction, 0u);
  return Result::kApplied;
}

struct State {
  bool done = false;   // a refusal stops every later attempt
  uint32_t applied = 0;
};
inline State& state() {
  static State s;
  return s;
}

// guest_base: host address of guest address 0. log: one line per state change (never per frame).
inline void Swap(uint8_t* guest_base, void (*log)(const char* mode, const char* state, uint32_t count)) {
  if (!Enabled()) return;
  State& s = state();
  if (s.done) return;
  const Result r = Step(guest_base, true, [guest_base](uint32_t address, uint32_t value) {
    const uint32_t be = (value >> 24) | ((value >> 8) & 0xFF00u) | ((value << 8) & 0xFF0000u) | (value << 24);
    std::memcpy(guest_base + address, &be, 4);
  });
  if (r == Result::kApplied) {
    if (s.applied++ == 0 && log) log(ModeName(), Name(r), s.applied);
  } else if (r == Result::kRefusedGuard || r == Result::kRefusedValue) {
    s.done = true;
    if (log) log(ModeName(), Name(r), s.applied);
  }
}
}  // namespace m44sub
