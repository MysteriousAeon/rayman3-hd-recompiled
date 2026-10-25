// M21 (D-050): when the game window hides the mouse cursor. Host-only, no game material.
//
// The pinned SDK leaves the cursor visible over the game window unless mouse capture asks otherwise, so it
// stays on the picture during controller play. The rule here: hidden while the game window is open, focused
// and not minimized, shown again by mouse movement for the window's auto-hide delay, and always shown when
// the window loses focus, is minimized or closes. The window applies the result with SDL_HideCursor /
// SDL_ShowCursor, which select the cursor image used over the SDL window's own client area: nothing here
// moves, confines or captures the pointer, and no other application's cursor is affected.
//
// A hidden test window (R3HD_NONINTRUSIVE) gets Action::kNone in every state: it never touches cursor state.
// R3HD_CURSOR=visible (play.ps1 -Cursor visible) keeps the SDK's behaviour.
#pragma once

#include <cstring>

namespace m21cursor {

enum class Mode { kAuto, kPinned };
// Mirrors rex::ui::Window::CursorVisibility (what other host code asked for, e.g. mouse capture).
enum class Requested { kVisible, kHidden, kAutoHidden };
enum class Action { kNone, kShow, kHide };

struct State {
  bool nonintrusive = false;  // hidden test window
  bool open = false;          // the native window exists
  bool focused = false;       // it has the input focus
  bool minimized = false;
  bool mouse_recent = false;  // the mouse moved over it within the auto-hide delay
  Requested requested = Requested::kVisible;
};

constexpr Action Decide(const State& s) {
  if (s.nonintrusive) return Action::kNone;
  if (!s.open || !s.focused || s.minimized) return Action::kShow;
  if (s.requested == Requested::kHidden) return Action::kHide;
  return s.mouse_recent ? Action::kShow : Action::kHide;
}

// Unset, empty or "auto": the rule above. "visible": the SDK's behaviour. Anything else: the rule above.
inline Mode ModeFromEnv(const char* value) {
  return value && std::strcmp(value, "visible") == 0 ? Mode::kPinned : Mode::kAuto;
}

inline const char* Name(Action a) {
  return a == Action::kShow ? "show" : a == Action::kHide ? "hide" : "none";
}

// The window's bookkeeping, kept apart from SDL so that the event sequence can be tested without a window.
// Every event returns the action to apply now (kNone only for a hidden test window).
class Tracker {
 public:
  explicit Tracker(bool nonintrusive = false) { state_.nonintrusive = nonintrusive; }

  Action Opened(bool focused, bool minimized) {
    state_.open = true;
    state_.focused = focused;
    state_.minimized = minimized;
    state_.mouse_recent = false;
    return Apply();
  }
  Action Focus(bool focused) {
    state_.focused = focused;
    state_.mouse_recent = false;  // a click that brings the focus back is not mouse use
    return Apply();
  }
  Action Minimized() {
    state_.minimized = true;
    state_.mouse_recent = false;
    return Apply();
  }
  Action Restored() {
    state_.minimized = false;
    return Apply();
  }
  Action MouseMoved() {
    // Movement of a captured mouse steers the game; it is not use of the cursor.
    if (state_.requested != Requested::kHidden) state_.mouse_recent = true;
    return Apply();
  }
  Action MouseIdle() {
    state_.mouse_recent = false;
    return Apply();
  }
  Action Request(Requested requested) {
    state_.requested = requested;
    if (requested == Requested::kHidden) state_.mouse_recent = false;
    return Apply();
  }
  Action Closed() {
    state_.open = false;
    state_.focused = false;
    state_.mouse_recent = false;
    return Apply();
  }

  const State& state() const { return state_; }
  // True when the last event changed the applied action (the window logs only then).
  bool changed() const { return changed_; }
  // The mouse-idle timer is wanted only while movement is what keeps the cursor shown.
  bool wants_idle_timer() const {
    return !state_.nonintrusive && state_.open && state_.focused && !state_.minimized && state_.mouse_recent &&
           state_.requested != Requested::kHidden;
  }

 private:
  Action Apply() {
    Action a = Decide(state_);
    changed_ = a != last_;
    last_ = a;
    return a;
  }

  State state_;
  Action last_ = Action::kNone;
  bool changed_ = false;
};

}  // namespace m21cursor
