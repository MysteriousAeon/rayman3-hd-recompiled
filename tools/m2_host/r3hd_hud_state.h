// Issue #6 (D-301): the opt-in score / Combo Meter visibility toggle. Host-only state, no SDK dependency, so
// tools/hud_toggle_state_test.cpp compiles it on its own. The rules are those verified for the private trailer
// build (E-359 / E-360, tools/trailer_capture_input.h): a fresh F5 key-down toggles; repeats, modified presses,
// focus loss, a host overlay that owns input (PC Settings, the SDK's F3/F4/F7/Backtick overlays), pause, cinematic
// state, a menu / end-game / credits level and any level change show the HUD again. Startup is always visible.
#pragma once
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>

namespace r3hd_hud {
// Registry hud_toggle (play.ps1 -HudToggle -> R3HD_HUD_TOGGLE). Only "f5" enables it; anything else is off.
inline bool EnabledValue(const char* v) { return v && !std::strcmp(v, "f5"); }
inline bool Enabled() {
  static const bool on = EnabledValue(std::getenv("R3HD_HUD_TOGGLE"));
  return on;
}

// The title's own state, read at the gate (821A0158): ordinary gameplay only. Level name lower-cased.
inline bool OrdinaryContext(const char* level, uint32_t pause_word, uint32_t cinematic_word) {
  return level[0] && std::strcmp(level, "menumap") && std::strcmp(level, "endgame") && std::strcmp(level, "staff") &&
         pause_word == 0 && cinematic_word == 0;
}

class State {
 public:
  void Context(bool ordinary, const char* level) {
    std::lock_guard lock(mutex_);
    if (!ordinary || level_ != level) { hidden_ = false; held_ = false; }
    ordinary_ = ordinary;
    level_ = level;
  }
  void Focus(bool focused) {
    std::lock_guard lock(mutex_);
    focused_ = focused;
    held_ = false;
    if (!focused) hidden_ = false;
  }
  void Available(bool available) {
    std::lock_guard lock(mutex_);
    if (available != available_) { hidden_ = false; held_ = false; }
    available_ = available;
  }
  void Reset() { std::lock_guard lock(mutex_); hidden_ = false; held_ = false; }
  // Returns true when this press toggled.
  bool Down(bool repeat) {
    std::lock_guard lock(mutex_);
    const bool edge = !held_ && !repeat;
    held_ = true;
    if (edge && focused_ && available_ && ordinary_) { hidden_ = !hidden_; return true; }
    return false;
  }
  void Up() { std::lock_guard lock(mutex_); held_ = false; }
  bool Hidden() {
    std::lock_guard lock(mutex_);
    return hidden_ && focused_ && available_ && ordinary_;
  }

 private:
  std::mutex mutex_;
  std::string level_;
  bool ordinary_ = false, focused_ = false, available_ = true, held_ = false, hidden_ = false;
};
inline State state;
}  // namespace r3hd_hud
