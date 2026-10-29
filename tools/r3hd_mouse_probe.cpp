// Research probe of the CURRENT driver, not acceptance of a mouse feature.
// No app, window, SDL initialization, device opening or OS input injection.
// Baseline expectations deliberately reproduce dropped clicks and overlay leakage.
#include <rex/cvar.h>
#include <rex/input/mnk/mnk_input_driver.h>
#include <rex/input/state_merge.h>
#include <rex/ui/keybinds.h>
#include <rex/ui/ui_event.h>
#include <cstdio>
#include <cstdlib>

using namespace rex;
using namespace rex::input;

int main() {
  int checks = 0, failures = 0;
  auto check = [&](const char* label, bool ok) {
    ++checks;
    failures += !ok;
    std::printf("%s %s\n", ok ? "PASS" : "FAIL", label);
  };
  auto flag = [&](const char* name, const char* value) {
    if (!cvar::SetFlagByName(name, value)) {
      std::printf("FAIL unknown setting %s\n", name);
      std::exit(2);
    }
  };
  flag("mnk_mode", "true");
  flag("mnk_mouse", "false");  // Buttons must not require capture or mouse look.
  flag("mnk_modifier_keys", "true");
  flag("keybind_a", "None");
  flag("keybind_b", "None");
  flag("keybind_x", "E");
  flag("keybind_right_trigger", "None");
  mnk::MnkInputDriver driver(nullptr, 0);
  driver.Setup();
  bool active = true;
  driver.set_is_active_callback([&] { return active; });
  ui::UISetupEvent focus(nullptr, false);
  driver.OnGotFocus(focus);
  std::vector<DeviceInfo> devices;
  driver.EnumerateDevices(devices);
  if (devices.size() != 1) return 2;
  const auto id = devices[0].id;
  check("keyboard/mouse is synthetic (physical-pad remapping excluded)", devices[0].synthetic);
  auto poll = [&] {
    X_INPUT_STATE s{};
    check("GetDeviceState succeeds", driver.GetDeviceState(id, &s) == X_ERROR_SUCCESS);
    return unsigned(uint16_t(s.gamepad.buttons));
  };
  auto key = [&](bool down) {
    ui::KeyEvent e(nullptr, ui::ParseVirtualKey("E"), 1, !down, false, false, false, false);
    if (down) driver.OnKeyDown(e); else driver.OnKeyUp(e);
  };
  auto button = [&](ui::MouseEvent::Button b, bool down) {
    ui::MouseEvent e(nullptr, b, 0, 0);
    if (down) driver.OnMouseDown(e); else driver.OnMouseUp(e);
  };
  constexpr unsigned attack = X_INPUT_GAMEPAD_X;
  for (bool right : {false, true}) {
    const auto b = right ? ui::MouseEvent::Button::kRight : ui::MouseEvent::Button::kLeft;
    flag("keybind_x", right ? "E,RMB" : "E,LMB");
    std::printf("CASE %s -> guest X (0x4000)\n", right ? "RMB" : "LMB");
    button(b, true);
    check("held mouse produces only attack without mouse look", poll() == attack);
    check("held attack persists on next poll (charge)", poll() == attack);
    button(b, true);
    check("duplicate down still produces one attack bit", poll() == attack);
    key(true);
    check("keyboard plus mouse merge to one attack bit", poll() == attack);
    key(false);
    check("keyboard release does not release held mouse", poll() == attack);
    button(b, false);
    check("mouse release clears attack", poll() == 0);
    button(b, true); button(b, false);
    check("BASELINE DEFECT: sub-poll mouse click is lost", poll() == 0);
    button(b, true); button(b, false); button(b, true); button(b, false);
    check("BASELINE DEFECT: consecutive sub-poll clicks are both lost", poll() == 0);
    key(true); key(false);
    check("keyboard sub-poll tap is latched", poll() == attack);
    check("keyboard tap drains exactly once", poll() == 0);
    button(b, true); (void)poll();
    driver.OnLostFocus(focus);
    check("focus loss clears held attack", poll() == 0);
    button(b, true);
    driver.OnGotFocus(focus);
    check("unfocused click ignored; refocus does not resurrect", poll() == 0);
    button(b, false);
    active = false;
    button(b, true);
    check("inactive overlay poll returns zero", poll() == 0);
    active = true;
    check("BASELINE RISK: overlay down survives reactivation without release", poll() == attack);
    button(b, false);
    check("eventual release clears overlay-held attack", poll() == 0);
    active = false;
    button(b, true); button(b, false);
    active = true;
    check("complete overlay click leaves no held attack", poll() == 0);
    button(b, true);
    flag("mnk_mode", "false");
    button(b, false);  // Current driver ignores release while disabled.
    flag("mnk_mode", "true");
    check("BASELINE RISK: release while disabled leaves held attack", poll() == attack);
    driver.OnLostFocus(focus); driver.OnGotFocus(focus);
    check("focus reset recovers disabled-release state", poll() == 0);
    button(b, true);  // Model the focus-acquisition click arriving after focus gain.
    check("BASELINE RISK: first down immediately after focus gain attacks", poll() == attack);
    button(b, false);
    check("focus-acquisition click release clears attack", poll() == 0);
    // Exercise the runtime's actual merge, not a second hand-written OR model.
    X_INPUT_STATE mouse{}, pad{};
    check("released synthetic state succeeds before pad merge",
          driver.GetDeviceState(id, &mouse) == X_ERROR_SUCCESS && unsigned(uint16_t(mouse.gamepad.buttons)) == 0);
    pad.gamepad.buttons = attack;
    MergeInto(mouse, pad);
    check("physical-pad X survives a neutral/released mouse state", unsigned(uint16_t(mouse.gamepad.buttons)) == attack);
    button(b, true); key(true);
    check("held synthetic X succeeds before pad merge",
          driver.GetDeviceState(id, &mouse) == X_ERROR_SUCCESS && unsigned(uint16_t(mouse.gamepad.buttons)) == attack);
    MergeInto(mouse, pad);
    check("pad/keyboard/mouse X merge into one bit", unsigned(uint16_t(mouse.gamepad.buttons)) == attack);
    button(b, false); key(false);
    check("mouse/keyboard release clears synthetic source", poll() == 0);
  }
  flag("keybind_x", "E");
  button(ui::MouseEvent::Button::kLeft, true);
  button(ui::MouseEvent::Button::kRight, true);
  check("shipped keyboard-only binding ignores both mouse buttons", poll() == 0);
  button(ui::MouseEvent::Button::kLeft, false);
  button(ui::MouseEvent::Button::kRight, false);
  std::printf("R3HD_MOUSE_BASELINE %s checks=%d failures=%d\n", failures ? "FAIL" : "PASS", checks, failures);
  std::fflush(stdout);  // Runtime DLL teardown does not flush the probe's CRT stream.
  return failures ? 1 : 0;
}
