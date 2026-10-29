// Feasibility evidence only: exercise the real keyboard driver without a window,
// SDL initialization, physical devices, guest code or global input injection.
// A passing baseline reproduces blockers; it does NOT accept a PC Settings UI.
#include <rex/cvar.h>
#include <rex/input/mnk/mnk_input_driver.h>
#include <rex/ui/keybinds.h>
#include <rex/ui/ui_event.h>
#include <cstdio>
#include <cstdlib>

int main() {
  std::puts("PC_SETTINGS_INPUT_BASELINE begin (windowless)");
  std::fflush(stdout);
  using namespace rex;
  using namespace rex::input;
  int checks = 0, failures = 0;
  auto check = [&](const char* label, bool ok) {
    ++checks;
    failures += !ok;
    std::printf("%s %s\n", ok ? "PASS" : "FAIL", label);
    std::fflush(stdout);
  };
  auto flag = [&](const char* name, const char* value) {
    if (!cvar::SetFlagByName(name, value)) {
      std::fprintf(stderr, "FAIL unknown setting %s\n", name);
      std::exit(2);
    }
  };
  flag("mnk_mode", "true");
  flag("mnk_mouse", "false");
  flag("mnk_modifier_keys", "true");
  flag("keybind_x", "E");
  flag("keybind_a", "Space");
  flag("keybind_lstick_up", "W");
  flag("keybind_rstick_right", "Right");
  mnk::MnkInputDriver driver(nullptr, 0);
  check("driver setup", driver.Setup() == X_STATUS_SUCCESS);
  bool active = true;
  driver.set_is_active_callback([&] { return active; });
  ui::UISetupEvent focus(nullptr, false);
  driver.OnGotFocus(focus);
  std::vector<DeviceInfo> devices;
  driver.EnumerateDevices(devices);
  check("one synthetic device", devices.size() == 1 && devices[0].synthetic);
  if (devices.size() != 1) return 2;
  auto key = [&](const char* name, bool down) {
    ui::KeyEvent e(nullptr, ui::ParseVirtualKey(name), 1, false, false, false, false, false);
    if (down) driver.OnKeyDown(e); else driver.OnKeyUp(e);
  };
  auto poll = [&] {
    X_INPUT_STATE state{};
    check("state poll succeeds", driver.GetDeviceState(devices[0].id, &state) == X_ERROR_SUCCESS);
    return state;
  };
  auto neutral = [](const X_INPUT_STATE& s) {
    return !s.gamepad.buttons && !s.gamepad.left_trigger && !s.gamepad.right_trigger &&
           !s.gamepad.thumb_lx && !s.gamepad.thumb_ly && !s.gamepad.thumb_rx && !s.gamepad.thumb_ry;
  };
  auto reset = [&] {
    driver.OnLostFocus(focus);
    driver.OnGotFocus(focus);
    active = true;
    check("focus reset is neutral", neutral(poll()));
  };
  check("initial state neutral", neutral(poll()));
  key("E", true); key("E", false);
  check("ordinary attack tap retained for one poll", poll().gamepad.buttons == X_INPUT_GAMEPAD_X);
  check("ordinary attack tap drains", neutral(poll()));

  // Model the existing SetActiveCallback boundary, not a newly implemented UI.
  active = false;
  key("E", true); key("E", false);
  check("inactive poll suppresses attack", neutral(poll()));
  active = true;
  check("BLOCKER: completed inactive tap leaks after close", poll().gamepad.buttons == X_INPUT_GAMEPAD_X);
  check("leaked tap drains", neutral(poll()));
  reset();
  for (const char* name : {"E", "W", "Right"}) {
    key(name, true);
    check("held gameplay input exists before opening", !neutral(poll()));
    active = false;
    check("inactive hold is neutral", neutral(poll()));
    active = true;
    check("BLOCKER: hold resumes without release/rearm", !neutral(poll()));
    key(name, false);
    check("release clears held input", neutral(poll()));
    reset();
  }
  key("W", true); key("Right", true); key("E", true);
  driver.OnLostFocus(focus);
  check("real focus loss clears movement camera and attack", neutral(poll()));
  key("Space", true); key("Space", false);
  driver.OnGotFocus(focus);
  check("unfocused events ignored", neutral(poll()));
  key("Space", true); key("Space", false);
  check("BLOCKER: confirm tap immediately after refocus reaches guest", poll().gamepad.buttons == X_INPUT_GAMEPAD_A);
  check("refocus tap drains", neutral(poll()));
  std::printf("PC_SETTINGS_INPUT_BASELINE %s checks=%d failures=%d; UI acceptance DEFERRED\n",
              failures ? "FAIL" : "PASS", checks, failures);
  std::fflush(stdout);  // Preserve evidence when output is a pipe rather than a console.
  return failures ? 1 : 0;
}
