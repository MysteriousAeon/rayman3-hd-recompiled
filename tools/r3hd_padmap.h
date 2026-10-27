// Controller map (D-115, D-116). Pure decisions, no SDK call: tools/r3hd_padmap_patch.py installs this header and
// calls it from the SDK's InputSystem, which applies it to the state and keystrokes of physical pads only (never to
// the synthetic keyboard / NOP devices) before every device of a guest user is merged. tools/r3hd_padmap_test.cpp
// drives it without the SDK.
//
// Buttons: a bijection of the 14 digital buttons of the Xbox 360 pad: for every guest button (what the title reads)
// the physical button that produces it. A bijection keeps every guest button reachable, makes a press of one physical
// button one press of one guest button (so keystroke events translate one for one, repeats included) and needs no
// state of its own: a pad that is unplugged and plugged in again is mapped exactly as before. The Guide bit (0x0400)
// and the unused bit 0x0800 pass unchanged. SDL names a DualSense's buttons by position (Cross = south = A, Circle = B,
// Square = X, Triangle = Y, L1 / R1, Create = Back, Options = Start, L3 / R3), so one map serves both families.
// Analog (D-116): the two triggers may be exchanged with each other, and the two sticks with each other. An analog
// input only ever moves whole to the other input of its kind (every value, full range, no threshold); it is never
// given to a button nor a button to it, so the title keeps its own analog semantics (the lock-on threshold, the
// camera's easing). tools/r3hd_ds_sdl.h puts the DualSense resistance on the trigger that gives the guest its right
// trigger (lock-on).
//
// Configuration: R3HD_PAD_MAP = comma-separated guest=physical pairs naming only the inputs that differ from the
// default (tools/r3hd_settings.py resolve_controller writes it; tools/play.ps1 passes it); an exchange is named both
// ways (left_trigger=right_trigger,right_trigger=left_trigger). Empty or absent = the original controls. A value that
// is not a bijection within each kind (unknown name, an input named twice, a physical input used twice, a button
// paired with an analog input or a trigger with a stick) is not used at all: the original controls apply and the
// start-up line says state=invalid. Names and order are config/controls/padmap.json's (tools/r3hd_padmap_regression.py
// ties the two).
#pragma once

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>

namespace r3hd_padmap {

inline constexpr int kButtons = 14;
inline constexpr int kInputs = 18;  // the buttons, then the triggers (14, 15) and the sticks (16, 17)

struct Button {
  const char* name;
  uint16_t bit;  // X_INPUT_GAMEPAD_*
  uint16_t vk;   // rex::ui::VirtualKey::kXInputPad*
};

inline constexpr Button kTable[kButtons] = {
    {"a", 0x1000, 0x5800},           {"b", 0x2000, 0x5801},
    {"x", 0x4000, 0x5802},           {"y", 0x8000, 0x5803},
    {"left_shoulder", 0x0100, 0x5805}, {"right_shoulder", 0x0200, 0x5804},
    {"back", 0x0020, 0x5815},        {"start", 0x0010, 0x5814},
    {"lstick_press", 0x0040, 0x5816}, {"rstick_press", 0x0080, 0x5817},
    {"dpad_up", 0x0001, 0x5810},     {"dpad_down", 0x0002, 0x5811},
    {"dpad_left", 0x0004, 0x5812},   {"dpad_right", 0x0008, 0x5813},
};
inline constexpr const char* kAnalog[4] = {"left_trigger", "right_trigger", "left_stick", "right_stick"};

inline constexpr uint16_t kMapped = 0xF3FF;  // the 14 bits above; Guide 0x0400 and 0x0800 pass unchanged

inline const char* NameOf(int i) { return i < kButtons ? kTable[i].name : kAnalog[i - kButtons]; }

inline int IndexOf(const char* name, size_t len) {
  for (int i = 0; i < kInputs; ++i)
    if (std::strlen(NameOf(i)) == len && std::strncmp(NameOf(i), name, len) == 0) return i;
  return -1;
}

// 0 a button, 1 a trigger, 2 a stick: a guest input takes a physical input of its own kind only.
inline int KindOf(int i) { return i < kButtons ? 0 : 1 + (i - kButtons) / 2; }

enum class State { kDefault, kCustom, kInvalid };

inline const char* StateName(State s) {
  return s == State::kCustom ? "custom" : s == State::kInvalid ? "invalid" : "default";
}

class Map {
 public:
  Map() {
    for (int i = 0; i < kInputs; ++i) source_[i] = i;
  }

  // R3HD_PAD_MAP's value (nullptr = absent). Never fails: anything that is not a bijection gives the default map.
  static Map Parse(const char* text) {
    if (!text || !*text) return Map();
    Map custom;
    bool named[kInputs] = {};
    const char* p = text;
    for (;;) {
      const char* end = std::strchr(p, ',');
      size_t len = end ? size_t(end - p) : std::strlen(p);
      const char* eq = static_cast<const char*>(std::memchr(p, '=', len));
      if (!eq) return Invalid("a pair without '='");
      int guest = IndexOf(p, size_t(eq - p));
      int physical = IndexOf(eq + 1, len - size_t(eq + 1 - p));
      if (guest < 0 || physical < 0) return Invalid("an unknown button");
      if (KindOf(guest) != KindOf(physical)) return Invalid("inputs of different kinds");
      if (named[guest]) return Invalid("a button named twice");
      named[guest] = true;
      custom.source_[guest] = physical;
      if (!end) break;
      p = end + 1;
    }
    bool used[kInputs] = {};
    for (int i = 0; i < kInputs; ++i) {
      if (used[custom.source_[i]]) return Invalid("a physical button used twice");
      used[custom.source_[i]] = true;
    }
    custom.state_ = custom.Identity() ? State::kDefault : State::kCustom;
    custom.text_ = custom.Describe();
    return custom;
  }

  // Physical buttons -> the guest buttons they produce.
  uint16_t Apply(uint16_t physical) const {
    if (state_ != State::kCustom) return physical;
    uint16_t out = physical & uint16_t(~kMapped);
    for (int g = 0; g < kButtons; ++g)
      if (physical & kTable[source_[g]].bit) out |= kTable[g].bit;
    return out;
  }

  // D-116: a physical pad's analog values -> the guest's (each moved whole; nothing is scaled or thresholded).
  void ApplyAnalog(uint8_t& lt, uint8_t& rt, int16_t& lx, int16_t& ly, int16_t& rx, int16_t& ry) const {
    if (TriggersSwapped()) std::swap(lt, rt);
    if (SticksSwapped()) {
      std::swap(lx, rx);
      std::swap(ly, ry);
    }
  }

  // A physical input's keystroke virtual key -> the guest input's; every other key unchanged. D-116: the trigger keys
  // (5806 / 5807) and the eight direction keys of each stick (5820..5827 / 5830..5837) follow the exchanges.
  uint16_t MapKey(uint16_t vk) const {
    if (state_ != State::kCustom) return vk;
    for (int g = 0; g < kButtons; ++g)
      if (kTable[source_[g]].vk == vk) return kTable[g].vk;
    if (TriggersSwapped() && (vk == 0x5806 || vk == 0x5807)) return uint16_t(vk ^ 0x0001);
    if (SticksSwapped() && ((vk >= 0x5820 && vk <= 0x5827) || (vk >= 0x5830 && vk <= 0x5837)))
      return uint16_t(vk ^ 0x0010);
    return vk;
  }

  bool TriggersSwapped() const { return state_ == State::kCustom && source_[kButtons] != kButtons; }
  bool SticksSwapped() const { return state_ == State::kCustom && source_[kButtons + 2] != kButtons + 2; }

  State state() const { return state_; }
  int source(int guest) const { return source_[guest]; }
  const std::string& text() const { return text_; }    // the pairs in effect ("" = default)
  const std::string& error() const { return error_; }  // why a value was not used

 private:
  static Map Invalid(const char* why) {
    Map m;
    m.state_ = State::kInvalid;
    m.error_ = why;
    return m;
  }

  bool Identity() const {
    for (int i = 0; i < kInputs; ++i)
      if (source_[i] != i) return false;
    return true;
  }

  std::string Describe() const {
    std::string s;
    for (int g = 0; g < kInputs; ++g) {
      if (source_[g] == g) continue;
      if (!s.empty()) s += ',';
      s += std::string(NameOf(g)) + "=" + NameOf(source_[g]);
    }
    return s;
  }

  int source_[kInputs];
  State state_ = State::kDefault;
  std::string text_, error_;
};

// The map of this process: R3HD_PAD_MAP read once.
inline const Map& Get() {
  static const Map map = Map::Parse(std::getenv("R3HD_PAD_MAP"));
  return map;
}

// Test only (tools/r3hd_padmap_game.py): a hidden run's scheduled pad state is mapped as if it came from a physical
// pad, so the map can be proven in the game without opening a controller (D-053). Off unless both variables are set;
// tools/play.ps1 clears R3HD_PADMAP_TEST.
inline bool ScheduleTest() {
  static const bool on = std::getenv("R3HD_NONINTRUSIVE") && std::getenv("R3HD_PADMAP_TEST");
  return on;
}

}  // namespace r3hd_padmap
