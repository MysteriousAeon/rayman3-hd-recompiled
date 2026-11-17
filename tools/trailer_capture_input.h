// Capture EXE only. Uses the game's Window listeners; no OS input or device APIs.
#pragma once
#ifndef R3HD_PRIVATE_CAPTURE
#error Private capture definition required
#endif
#include <rex/ui/window_listener.h>
#include <functional>
#include <mutex>
#include <string>

namespace trailer_capture {
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
  bool Down(bool repeat) {
    std::lock_guard lock(mutex_);
    const bool edge = !held_ && !repeat;
    held_ = true;
    if (edge && focused_ && available_ && ordinary_) { hidden_ = !hidden_; return true; }
    return false;
  }
  void Up() { std::lock_guard lock(mutex_); held_ = false; }
  void Command(bool hide) { std::lock_guard lock(mutex_); hidden_ = ordinary_ && available_ && hide; }
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

class Input final : public rex::ui::WindowListener, public rex::ui::WindowInputListener {
 public:
  explicit Input(std::function<bool()> blocked) : blocked_(std::move(blocked)) {}
  void OnGotFocus(rex::ui::UISetupEvent&) override { state.Focus(true); }
  void OnLostFocus(rex::ui::UISetupEvent&) override { state.Focus(false); }
  void OnKeyDown(rex::ui::KeyEvent& e) override {
    Sync();
    using K = rex::ui::VirtualKey;
    if (e.virtual_key() != K::kF5) {
      // Withdraw suppression before any reserved overlay takes keyboard ownership; never consume its shortcut.
      if (e.virtual_key() == K::kF3 || e.virtual_key() == K::kF4 || e.virtual_key() == K::kF7 ||
          e.virtual_key() == K::kOem3) state.Reset();
      return;
    }
    e.set_handled(true);  // Including repeats, unfocused events and custom F5 gameplay bindings.
    state.Down(e.prev_state() || e.repeat_count() > 1 || e.is_alt_pressed() || e.is_ctrl_pressed() ||
               e.is_shift_pressed() || e.is_super_pressed());
  }
  void OnKeyUp(rex::ui::KeyEvent& e) override {
    Sync();
    if (e.virtual_key() == rex::ui::VirtualKey::kF5) { e.set_handled(true); state.Up(); }
  }
 private:
  void Sync() { state.Available(!blocked_()); }
  std::function<bool()> blocked_;
};
}  // namespace trailer_capture
