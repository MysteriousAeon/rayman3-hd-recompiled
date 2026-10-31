// D-139: the input gate of a host panel (in-game PC Settings). Host-only, no game material, SDK-free.
//
// While a host panel holds the input (the SDK's is_active() callback is false), every input driver gives the guest
// a connected, neutral source. When the panel closes, whatever is still held from before or during it stays withheld
// until it is released (a button or key let go, a trigger or stick back inside its release zone); only fresh input
// reaches the guest. This is the release-before-rearm rule of D-128, applied per source in each driver:
//   * KeyGate (keyboard and mouse driver): keys held at the reactivation are withheld until their key-up; pending
//     taps latched while the panel was open are dropped by the driver at that point.
//   * PadGate (SDL and XInput pads): buttons held at the reactivation are withheld until released, triggers until
//     they fall to kTriggerRelease, each stick until both axes are inside its release zone. The zones are XInput's
//     documented dead zones; they only decide when a held control counts as released and never change the values
//     the guest sees afterwards (no new gameplay dead zone).
// The gate never grants input, never writes guest memory and does nothing while no panel was opened: Apply / Sync
// with active == true on every sample leaves every value unchanged.
#pragma once
#include <cstdint>
#include <cstdlib>

namespace r3hd_hostui {

// D-142 (test only): the app's SetHostUiInputBlocked state, mirrored for the hidden-run key source
// (tools/m32_key_test.h), whose private driver instance is not one of the InputSystem's drivers and so never sees the
// SDK's is_active() callback. The app (r3hd.exe) and the key source (rexruntime.dll) are different modules, each with
// its own copy of an inline variable, so the mirror is this process environment variable (rex::platform::env, Win32),
// set only in hidden runs while a panel is open. No product path reads it.
inline constexpr const char* kTestSourceBlocked = "R3HD_HOSTUI_TEST_BLOCKED";

constexpr int kLeftStickRelease = 7849;   // XINPUT_GAMEPAD_LEFT_THUMB_DEADZONE
constexpr int kRightStickRelease = 8689;  // XINPUT_GAMEPAD_RIGHT_THUMB_DEADZONE
constexpr int kTriggerRelease = 30;       // XINPUT_GAMEPAD_TRIGGER_THRESHOLD

// G is any struct with the X_INPUT_GAMEPAD field names (buttons, left_trigger, right_trigger, thumb_lx ... thumb_ry).
class PadGate {
 public:
  // One raw sample of this pad; returns the state the guest may see in `pad`. `active` is the driver's is_active().
  template <class G>
  void Apply(bool active, G& pad) {
    if (!active) {
      was_active_ = false;
      pad = G{};
      return;
    }
    if (!was_active_) {  // the panel closed: everything held now is withheld until released
      was_active_ = true;
      buttons_ = static_cast<uint16_t>(pad.buttons);
      lt_ = pad.left_trigger > kTriggerRelease;
      rt_ = pad.right_trigger > kTriggerRelease;
      ls_ = Outside(pad.thumb_lx, pad.thumb_ly, kLeftStickRelease);
      rs_ = Outside(pad.thumb_rx, pad.thumb_ry, kRightStickRelease);
    }
    buttons_ &= static_cast<uint16_t>(pad.buttons);  // a released button leaves the withheld set for good
    pad.buttons = static_cast<decltype(pad.buttons)>(pad.buttons & ~buttons_);
    if (lt_) {
      lt_ = pad.left_trigger > kTriggerRelease;
      if (lt_) pad.left_trigger = 0;
    }
    if (rt_) {
      rt_ = pad.right_trigger > kTriggerRelease;
      if (rt_) pad.right_trigger = 0;
    }
    if (ls_) {
      ls_ = Outside(pad.thumb_lx, pad.thumb_ly, kLeftStickRelease);
      if (ls_) pad.thumb_lx = pad.thumb_ly = 0;
    }
    if (rs_) {
      rs_ = Outside(pad.thumb_rx, pad.thumb_ry, kRightStickRelease);
      if (rs_) pad.thumb_rx = pad.thumb_ry = 0;
    }
  }
  // True while something held through a panel is still withheld (or a panel holds the input).
  bool Holding() const { return !was_active_ || buttons_ || lt_ || rt_ || ls_ || rs_; }
  // Something held through a panel is still withheld (false while the panel is open and before the first sample).
  bool Withholding() const { return was_active_ && (buttons_ || lt_ || rt_ || ls_ || rs_); }

 private:
  static bool Outside(int x, int y, int zone) { return std::abs(x) > zone || std::abs(y) > zone; }
  bool was_active_ = true;
  uint16_t buttons_ = 0;
  bool lt_ = false, rt_ = false, ls_ = false, rs_ = false;
};

// Keyboard state by virtual key (the MnK driver's key_down_ array, 256 entries). Under the driver's own mutex.
class KeyGate {
 public:
  static constexpr int kKeys = 256;
  // Call before acting on input. Returns true exactly when the input comes back (the driver then drops pending taps).
  bool Sync(bool active, const bool* key_down) {
    if (!active) {
      was_active_ = false;
      return false;
    }
    if (was_active_) return false;
    was_active_ = true;
    for (int i = 0; i < kKeys; ++i) held_[i] = key_down[i];
    return true;
  }
  void Released(unsigned vk) {
    if (vk < unsigned(kKeys)) held_[vk] = false;
  }
  void ClearHeld() {
    for (bool& h : held_) h = false;
  }
  // The keys the guest may see: down and not withheld.
  void Mask(const bool* key_down, bool* out) const {
    for (int i = 0; i < kKeys; ++i) out[i] = key_down[i] && !held_[i];
  }
  bool active() const { return was_active_; }

 private:
  bool was_active_ = true;
  bool held_[kKeys] = {};
};

}  // namespace r3hd_hostui
