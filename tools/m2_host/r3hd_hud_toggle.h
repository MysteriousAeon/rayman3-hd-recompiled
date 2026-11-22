// Issue #6 (D-301): the F5 listener for the opt-in score / Combo Meter toggle (r3hd_hud_state.h). Registered only
// when hud_toggle is on, at maximum input priority on the game window: F5 down / up are consumed (including repeats
// and a player's own F5 binding) and never reach a gameplay driver. Every other key, the mouse and controllers pass
// through unchanged. Uses the game's Window listeners only; no OS input or device APIs. Ported from the private
// trailer listener (tools/trailer_capture_input.h, E-360) without its command-file channel.
#pragma once
#include <rex/ui/window_listener.h>
#include <functional>
#include "r3hd_hud_state.h"

namespace r3hd_hud {
class Input final : public rex::ui::WindowListener, public rex::ui::WindowInputListener {
 public:
  explicit Input(std::function<bool()> blocked) : blocked_(std::move(blocked)) {}
  void OnGotFocus(rex::ui::UISetupEvent&) override { state.Focus(true); }
  void OnLostFocus(rex::ui::UISetupEvent&) override { state.Focus(false); }
  void OnKeyDown(rex::ui::KeyEvent& e) override {
    Sync();
    using K = rex::ui::VirtualKey;
    if (e.virtual_key() != K::kF5) {
      // Show the HUD again before a reserved overlay takes the keyboard; never consume its shortcut.
      if (e.virtual_key() == K::kF3 || e.virtual_key() == K::kF4 || e.virtual_key() == K::kF7 ||
          e.virtual_key() == K::kOem3) state.Reset();
      return;
    }
    e.set_handled(true);
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
}  // namespace r3hd_hud
