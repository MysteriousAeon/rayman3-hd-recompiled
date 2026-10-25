// Real MnK driver regression: default keyboard keys for menu confirm (pad A) and cancel (pad B).
// The title confirms with A and leaves a submenu with B (hidden run m10_cancel1); Escape must reach B.
#include <rex/input/mnk/mnk_input_driver.h>
#include <rex/ui/ui_event.h>
#include <rex/cvar.h>
#include <cstdio>
using namespace rex;
using namespace rex::input;
using rex::ui::VirtualKey;
int main() {
  int checks = 0, failures = 0;
  auto check = [&](bool ok, const char* what) {
    ++checks;
    if (!ok) { ++failures; std::printf("FAIL: %s\n", what); }
  };
  check(rex::cvar::SetFlagByName("mnk_mode", "true"), "mnk_mode");
  mnk::MnkInputDriver driver(nullptr, 0);
  check(driver.Setup() == X_STATUS_SUCCESS, "setup");
  rex::ui::UISetupEvent focus(nullptr, false); driver.OnGotFocus(focus);
  std::vector<DeviceInfo> devices; driver.EnumerateDevices(devices);
  if (devices.size() != 1) { std::puts("FAIL: device count"); return 2; }
  auto id = devices[0].id;
  auto buttons = [&] {
    X_INPUT_STATE state{};
    driver.GetDeviceState(id, &state);
    return uint16_t(state.gamepad.buttons);
  };
  struct Bind { VirtualKey key; uint16_t button; const char* name; };
  const Bind binds[] = {
      {VirtualKey::kSpace, X_INPUT_GAMEPAD_A, "Space -> A (confirm)"},
      {VirtualKey::kOem1, X_INPUT_GAMEPAD_A, "Semicolon -> A (confirm)"},
      {VirtualKey::kEscape, X_INPUT_GAMEPAD_B, "Escape -> B (cancel)"},
      {VirtualKey::kBack, X_INPUT_GAMEPAD_B, "Backspace -> B (cancel)"},
      {VirtualKey::kOem7, X_INPUT_GAMEPAD_B, "Quote -> B (cancel)"},
      // Neighbouring bindings must be exactly what they were.
      {VirtualKey::kReturn, X_INPUT_GAMEPAD_START, "Return -> Start"},
      {VirtualKey::kX, X_INPUT_GAMEPAD_START, "X -> Start"},
      {VirtualKey::kTab, X_INPUT_GAMEPAD_BACK, "Tab -> Back"},
      {VirtualKey::kZ, X_INPUT_GAMEPAD_BACK, "Z -> Back"},
      {VirtualKey::kL, X_INPUT_GAMEPAD_X, "L -> X"},
      {VirtualKey::kP, X_INPUT_GAMEPAD_Y, "P -> Y"},
  };
  for (const Bind& bind : binds) {
    rex::ui::KeyEvent key(nullptr, bind.key, 1, false, false, false, false, false);
    // Held: exactly that one button, on every poll.
    driver.OnKeyDown(key);
    check(buttons() == bind.button, bind.name);
    check(buttons() == bind.button, bind.name);
    driver.OnKeyUp(key);
    check(buttons() == 0, bind.name);
    // Tap shorter than a poll interval: seen once, then gone.
    driver.OnKeyDown(key); driver.OnKeyUp(key);
    check(buttons() == bind.button, bind.name);
    check(buttons() == 0, bind.name);
  }
  // Confirm then cancel, as in a menu: no residue of the first press in the second.
  rex::ui::KeyEvent confirm(nullptr, VirtualKey::kSpace, 1, false, false, false, false, false);
  rex::ui::KeyEvent cancel(nullptr, VirtualKey::kEscape, 1, false, false, false, false, false);
  driver.OnKeyDown(confirm); driver.OnKeyUp(confirm);
  check(buttons() == X_INPUT_GAMEPAD_A, "confirm tap");
  driver.OnKeyDown(cancel); driver.OnKeyUp(cancel);
  check(buttons() == X_INPUT_GAMEPAD_B, "cancel tap after confirm");
  check(buttons() == 0, "released after cancel");
  // Escape pressed while the window is not focused does nothing.
  driver.OnLostFocus(focus);
  driver.OnKeyDown(cancel); driver.OnKeyUp(cancel);
  driver.OnGotFocus(focus);
  check(buttons() == 0, "Escape without focus");
  std::printf("M10 menu keys: %d checks, %d failures: %s\n", checks, failures, failures ? "FAIL" : "PASS");
  std::fflush(stdout);
  return failures ? 1 : 0;
}
