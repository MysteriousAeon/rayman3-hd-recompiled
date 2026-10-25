// Milestone 16 (D-044): input gate for a host dialog that stands in for a console system UI the title asked
// for (XamShowAchievementsUI). Installed as include/rex/m16_sysui.h by tools/m16_runtime_patch.py.
//
// On the console the system UI owns the controller while it is shown: the title sees no buttons, and the
// player leaves it with B. The gate reproduces that at the XAM input boundary, for physical input and for the
// scripted test source alike:
//   - while the dialog is open the title is given a neutral pad;
//   - a close button (B, A, Start, Back) pressed after all buttons have been released once asks the dialog to
//     close (the A press that chose the menu entry is still down when the dialog opens and must not close it);
//   - after the dialog has closed the title keeps getting a neutral pad until the buttons are released, so the
//     closing press is not also a menu action.
// It holds no guest state and writes nothing to guest memory beyond the state structure the call fills anyway.
#pragma once
#include <cstdint>
#include <functional>
#include <mutex>

namespace m16sysui {
constexpr uint16_t kCloseButtons = 0x1000 /* A */ | 0x2000 /* B */ | 0x0010 /* Start */ | 0x0020 /* Back */;

enum class Action { kPass, kHide, kHideAndClose };

struct State {
  bool open = false;
  bool armed = false;
  bool closing = false;
  bool drain = false;
};

// Pure transition for one sampled pad state (regression: tools/m16_sysui_test.cpp).
inline Action Step(State& s, uint16_t buttons) {
  if (s.open) {
    if (s.closing) return Action::kHide;
    if (!s.armed) {
      if (buttons == 0) s.armed = true;
      return Action::kHide;
    }
    if (buttons & kCloseButtons) {
      s.closing = true;
      return Action::kHideAndClose;
    }
    return Action::kHide;
  }
  if (s.drain) {
    if (buttons == 0) {
      s.drain = false;
      return Action::kPass;
    }
    return Action::kHide;
  }
  return Action::kPass;
}

inline void Open(State& s) {
  s.open = true;
  s.armed = false;
  s.closing = false;
  s.drain = false;
}

inline void Closed(State& s) {
  s.open = false;
  s.armed = false;
  s.closing = false;
  s.drain = true;
}

struct Gate {
  std::mutex mutex;
  State state;
  std::function<void()> request_close;  // asks the UI thread to close the dialog; may be empty
};

inline Gate& gate() {
  static Gate g;
  return g;
}

inline bool IsOpen() {
  Gate& g = gate();
  std::lock_guard<std::mutex> lock(g.mutex);
  return g.state.open;
}

// Returns true when the title must be given a neutral pad instead of `buttons`.
inline bool Filter(uint16_t buttons) {
  Gate& g = gate();
  std::function<void()> close;
  Action action;
  {
    std::lock_guard<std::mutex> lock(g.mutex);
    action = Step(g.state, buttons);
    if (action == Action::kHideAndClose) close = g.request_close;
  }
  if (close) close();
  return action != Action::kPass;
}
}  // namespace m16sysui
