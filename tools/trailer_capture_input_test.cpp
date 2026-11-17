// No window, game, controller, OS event or global input. Real keyboard driver behind the capture listener.
#include "trailer_capture_input.h"
#include <rex/cvar.h>
#include <rex/input/mnk/mnk_input_driver.h>
#include <rex/ui/keybinds.h>
#include <cstdio>
#include <vector>

int main() {
  using namespace rex;
  unsigned checks = 0, failures = 0;
  auto check = [&](const char* name, bool ok) { ++checks; if (!ok) { ++failures; std::printf("FAIL %s\n", name); } };
  auto flag = [&](const char* key, const char* value) { check(key, cvar::SetFlagByName(key, value)); };
  flag("mnk_mode", "true"); flag("mnk_mouse", "false"); flag("mnk_mouse_buttons", "true");
  flag("keybind_x", "F5,LMB"); flag("keybind_a", "Space"); flag("keybind_lstick_right", "Right");
  input::mnk::MnkInputDriver driver(nullptr, 0);
  driver.SetTestEnabled(true); driver.Setup(); driver.TestSetGameplay(true);
  driver.set_is_active_callback([] { return true; });
  ui::UISetupEvent focus(nullptr, false);
  driver.OnGotFocus(focus);
  std::vector<input::DeviceInfo> devices; driver.EnumerateDevices(devices);
  if (devices.size() != 1) return 2;
  auto poll = [&] { input::X_INPUT_STATE s{}; driver.GetDeviceState(devices[0].id, &s); return s; };
  bool blocked = false;
  trailer_capture::Input listener([&] { return blocked; });
  auto key = [&](const char* name, bool down, bool repeat = false) {
    ui::KeyEvent e(nullptr, ui::ParseVirtualKey(name), 1, repeat, false, false, false, false);
    if (down) listener.OnKeyDown(e); else listener.OnKeyUp(e);
    if (!e.is_handled()) { if (down) driver.OnKeyDown(e); else driver.OnKeyUp(e); }
    return e.is_handled();
  };
  auto& s = trailer_capture::state;
  s.Context(true, "wood_11"); listener.OnGotFocus(focus);
  check("visible by default", !s.Hidden());
  check("F5 down consumed", key("F5", true)); check("first press hides", s.Hidden());
  for (int i=0; i<100; ++i) check("held repeat consumed", key("F5", true, true));
  check("repeat never toggles", s.Hidden());
  check("custom F5 attack binding never reaches game", uint16_t(poll().gamepad.buttons)==0);
  check("F5 up consumed", key("F5", false)); key("F5", true);
  check("second press restores", !s.Hidden()); key("F5", false);
  key("F5", true); listener.OnLostFocus(focus); driver.OnLostFocus(focus);
  check("focus loss restores", !s.Hidden());
  key("F5", true); check("unfocused down ignored", !s.Hidden());
  listener.OnGotFocus(focus); driver.OnGotFocus(focus); key("F5", true, true);
  check("stale held key after focus gain ignored", !s.Hidden());
  key("F5", false); key("F5", true); check("fresh key after focus gain works", s.Hidden()); key("F5", false);
  blocked = true; key("F5", true); check("keyboard ownership clears override", !s.Hidden());
  blocked = false; key("F5", true, true); check("ownership return needs fresh edge", !s.Hidden());
  key("F5", false); key("F5", true); check("fresh edge after ownership works", s.Hidden()); key("F5", false);
  check("F4 passes through", !key("F4", true)); check("F4 restores HUD", !s.Hidden()); key("F4", false);
  for (const char* name : {"F3","F7","Backtick"}) {
    check("reserved name is valid", ui::ParseVirtualKey(name) != ui::VirtualKey::kNone);
    check("reserved key passes", !key(name, true));
  }
  key("F5", true); key("F5", false); s.Context(false,"wood_11"); check("pause restores", !s.Hidden());
  s.Context(true,"wood_11"); check("resume stays visible", !s.Hidden());
  key("F5", true); key("F5", false); s.Context(true,"moor_00"); check("level change restores", !s.Hidden());
  key("F5", true); key("F5", false); s.Context(false,"moor_00"); s.Context(true,"moor_00");
  check("same-level reload through invalid context restores", !s.Hidden());
  key("F5", true); key("F5", false); key("Space",true); key("Space",false);
  check("normal A tap remains forwarded", uint16_t(poll().gamepad.buttons)==0x1000);
  key("Right",true); check("stick remains forwarded", poll().gamepad.thumb_lx > 0); key("Right",false);
  ui::MouseEvent mouse(nullptr,ui::MouseEvent::Button::kLeft,0,0);
  listener.OnMouseDown(mouse); check("mouse event unconsumed", !mouse.is_handled());
  driver.OnMouseDown(mouse); driver.OnMouseUp(mouse);
  check("mouse attack still works with HUD hidden", uint16_t(poll().gamepad.buttons)==0x4000);
  s.Command(false); check("fallback show", !s.Hidden()); s.Command(true); check("fallback hide", s.Hidden());
  listener.OnLostFocus(focus); check("focus loss clears fallback too", !s.Hidden());
  listener.OnGotFocus(focus); check("focus gain alone never restores stale request", !s.Hidden());
  listener.OnLostFocus(focus); s.Command(true); check("background explicit command cannot draw yet", !s.Hidden());
  listener.OnGotFocus(focus); check("explicit fallback request works on return", s.Hidden());
  s.Available(false); s.Command(true); s.Available(true); check("fallback cannot bypass keyboard owner", !s.Hidden());
  std::printf("CAPTURE_INPUT %s checks=%u failures=%u\n", failures ? "FAIL" : "PASS", checks, failures);
  return failures ? 1 : 0;
}
