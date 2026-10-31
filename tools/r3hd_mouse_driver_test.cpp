// D-138 acceptance test of the REAL keyboard / mouse driver (rexruntime.dll) with mouse controls. Window-less: no app,
// window, SDL initialisation, device, cursor, focus change or OS input; events go straight to the driver's handlers.
// Built and run by tools/build_mouse_driver_test.bat (tools/r3hd_mouse_feature_regression.py);
// prints R3HD_MOUSE_DRIVER PASS n/n.
#include <rex/cvar.h>
#include <rex/input/mnk/mnk_input_driver.h>
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
    if (!ok) std::printf("FAIL %s\n", label);
  };
  auto flag = [&](const char* name, const char* value) {
    if (!cvar::SetFlagByName(name, value)) {
      std::printf("FAIL unknown setting %s\n", name);
      std::exit(2);
    }
  };
  flag("mnk_mode", "true");
  flag("mnk_mouse", "false");
  flag("mnk_mouse_buttons", "true");
  flag("mnk_modifier_keys", "true");
  flag("mnk_sensitivity", "1");
  flag("keybind_a", "Space");
  flag("keybind_b", "None");
  flag("keybind_x", "E,LMB");
  flag("keybind_right_trigger", "Shift,RMB");
  flag("keybind_y", "MB4");
  flag("keybind_back", "MB5");
  flag("keybind_rstick_left", "Left");
  flag("keybind_rstick_right", "Right");
  mnk::MnkInputDriver driver(nullptr, 0);
  driver.SetTestEnabled(true);  // window-less: the camera counts test motion as captured
  driver.Setup();
  bool active = true;
  driver.set_is_active_callback([&] { return active; });
  ui::UISetupEvent focus(nullptr, false);
  driver.OnGotFocus(focus);
  std::vector<DeviceInfo> devices;
  driver.EnumerateDevices(devices);
  if (devices.size() != 1) return 2;
  const auto id = devices[0].id;
  X_INPUT_STATE s{};
  auto poll = [&] {
    s = {};
    driver.GetDeviceState(id, &s);
    return unsigned(uint16_t(s.gamepad.buttons));
  };
  auto key = [&](const char* name, bool down) {
    ui::KeyEvent e(nullptr, ui::ParseVirtualKey(name), 1, !down, false, false, false, false);
    if (down) driver.OnKeyDown(e); else driver.OnKeyUp(e);
  };
  auto button = [&](ui::MouseEvent::Button b, bool down) {
    ui::MouseEvent e(nullptr, b, 0, 0);
    if (down) driver.OnMouseDown(e); else driver.OnMouseUp(e);
  };
  using B = ui::MouseEvent::Button;
  constexpr unsigned X = X_INPUT_GAMEPAD_X, A = X_INPUT_GAMEPAD_A;

  // --- outside gameplay (no swap yet, a menu, pause): the mouse does nothing ---
  driver.TestSetGameplay(false);
  button(B::kLeft, true);
  check("menu: left click gives no attack", poll() == 0);
  driver.TestSetGameplay(true);
  check("gameplay begins with the button still held from the menu: no carried attack", poll() == 0);
  button(B::kLeft, false);
  check("its release: nothing", poll() == 0);

  // --- held attack / charge, held lock-on ---
  button(B::kLeft, true);
  check("left held: X", poll() == X);
  check("left held: X on every poll (charge)", poll() == X && poll() == X);
  button(B::kLeft, false);
  check("left released: nothing", poll() == 0);
  button(B::kRight, true);
  poll();
  check("right held: right trigger full (lock-on)", s.gamepad.right_trigger == 0xFF && s.gamepad.buttons == 0);
  poll();
  check("right held: still locked on", s.gamepad.right_trigger == 0xFF);
  button(B::kRight, false);
  poll();
  check("right released: trigger released", s.gamepad.right_trigger == 0);

  // --- short clicks are latched for one poll; never repeated ---
  button(B::kLeft, true);
  button(B::kLeft, false);
  check("click shorter than a poll: one poll of X", poll() == X);
  check("... not repeated", poll() == 0);

  // --- the keyboard and the mouse stay independent ---
  key("E", true);
  button(B::kLeft, true);
  check("E and left: one X", poll() == X);
  key("E", false);
  check("E released, left still held: X", poll() == X);
  key("E", true);
  button(B::kLeft, false);
  check("left released, E still held: X", poll() == X);
  key("E", false);
  poll();
  button(B::kLeft, true);
  driver.TestSetGameplay(false);
  check("pause while left is held: nothing in the menu", poll() == 0);
  key("Space", true);
  key("Space", false);
  check("a key tap in the menu is still the keyboard's (A), the held mouse adds nothing", poll() == A);
  driver.TestSetGameplay(true);
  check("resume with left still held: no attack until a fresh press", poll() == 0);
  key("E", true);
  key("E", false);
  check("keyboard attack works meanwhile", poll() == X);
  button(B::kLeft, false);
  button(B::kLeft, true);
  check("fresh press after resume: X", poll() == X);
  button(B::kLeft, false);
  poll();

  // --- focus, overlays, the option ---
  button(B::kLeft, true);
  check("before focus loss: X", poll() == X);
  driver.OnLostFocus(focus);
  check("focus lost: nothing", poll() == 0);
  driver.OnGotFocus(focus);
  check("focus back, button still physically held: no stuck attack", poll() == 0);
  button(B::kLeft, false);
  check("release after focus return: nothing", poll() == 0);
  active = false;  // a host overlay holds the mouse
  button(B::kLeft, true);
  check("overlay in front: click gives nothing", poll() == 0);
  active = true;
  check("overlay closed, still held: nothing", poll() == 0);
  button(B::kLeft, false);
  poll();
  button(B::kLeft, true);
  check("then a fresh press acts", poll() == X);
  active = false;
  poll();
  active = true;
  check("overlay opened and closed while held: needs a fresh press", poll() == 0);
  button(B::kLeft, false);
  flag("mnk_mouse_buttons", "false");
  button(B::kLeft, true);
  check("Mouse Buttons off: left does nothing", poll() == 0);
  flag("mnk_mouse_buttons", "true");
  check("turned on while held: needs a fresh press", poll() == 0);
  flag("mnk_mode", "false");
  button(B::kLeft, false);  // a release is taken even with the driver off
  flag("mnk_mode", "true");
  button(B::kLeft, true);
  check("release taken while the driver was off; the next press acts", poll() == X);
  button(B::kLeft, false);
  poll();

  // --- side buttons and the middle button follow their bindings ---
  button(B::kX1, true);
  check("side button 1 bound to Y: Y", poll() == X_INPUT_GAMEPAD_Y);
  button(B::kX1, false);
  button(B::kX2, true);
  check("side button 2 bound to Back: Back", poll() == X_INPUT_GAMEPAD_BACK);
  button(B::kX2, false);
  button(B::kMiddle, true);
  check("middle button unbound: nothing", poll() == 0);
  button(B::kMiddle, false);
  poll();
  key("Shift", true);
  poll();
  check("keyboard lock-on (Shift) unchanged", s.gamepad.right_trigger == 0xFF);
  key("Shift", false);
  poll();

  // --- the camera: stick time from relative counts, only with Mouse Camera on, in gameplay ---
  driver.TestMouseMotion(100.0f, 0.0f);
  poll();
  check("Mouse Camera off: motion moves nothing", s.gamepad.thumb_rx == 0 && s.gamepad.thumb_ry == 0);
  poll();
  flag("mnk_mouse", "true");
  check("turning it on does not replay motion made while it was off", (poll(), s.gamepad.thumb_rx == 0));
  driver.TestMouseMotion(50.0f, 0.0f);
  int on = 0;
  for (int i = 0; i < 12; ++i) on += (poll(), s.gamepad.thumb_rx == 32767);
  check("50 counts: about 50 ms of full right stick", on >= 2 && on <= 4);
  driver.TestMouseMotion(-50.0f, 0.0f);
  on = 0;
  for (int i = 0; i < 12; ++i) on += (poll(), s.gamepad.thumb_rx == -32767);
  check("the other way: left", on >= 2 && on <= 4);
  driver.TestMouseMotion(0.0f, 300.0f);
  on = 0;
  for (int i = 0; i < 20; ++i) on += (poll(), s.gamepad.thumb_ry < 0);
  check("mouse down: stick down", on >= 6);
  driver.TestMouseMotion(5000.0f, 0.0f);
  driver.TestSetGameplay(false);
  poll();
  check("leaving gameplay: no camera motion", s.gamepad.thumb_rx == 0);
  driver.TestSetGameplay(true);
  on = 0;
  for (int i = 0; i < 20; ++i) on += (poll(), s.gamepad.thumb_rx != 0);
  check("back in gameplay: no backlog from before", on == 0);
  driver.TestMouseMotion(5000.0f, 0.0f);
  driver.OnLostFocus(focus);
  driver.OnGotFocus(focus);
  on = 0;
  for (int i = 0; i < 20; ++i) on += (poll(), s.gamepad.thumb_rx != 0);
  check("focus lost and back: no camera jump", on == 0);
  driver.TestMouseMotion(100000.0f, 0.0f);
  on = 0;
  for (int i = 0; i < 40; ++i) on += (poll(), s.gamepad.thumb_rx != 0);
  check("a huge flick is bounded (at most ~150 ms of stick)", on >= 1 && on <= 10);
  key("Left", true);
  driver.TestMouseMotion(20.0f, 0.0f);
  poll();
  check("arrow key and mouse add before the clamp (stays in range)", s.gamepad.thumb_rx == 0);
  key("Left", false);
  for (int i = 0; i < 10; ++i) poll();
  driver.TestMouseMotion(30.0f, 0.0f);
  driver.GetDeviceState(id, nullptr);
  on = 0;
  for (int i = 0; i < 10; ++i) on += (poll(), s.gamepad.thumb_rx != 0);
  check("a state query without a buffer spends no motion", on >= 1);
  for (int i = 0; i < 20; ++i) poll();

  // --- D-145: in the title's Look Mode the mouse drives the left stick ---
  flag("keybind_lstick_left", "A");
  flag("keybind_lstick_right", "D");
  flag("keybind_lstick_up", "W");
  flag("keybind_lstick_down", "S");
  int16_t max_lx = 0, max_rx = 0, min_partial = 32767, partial_before_full = 0;
  auto look_frames = [&](int n, bool* full_seen = nullptr) {
    for (int i = 0; i < n; ++i) {
      poll();
      const int16_t v = s.gamepad.thumb_lx;
      if (v > max_lx) max_lx = v;
      if (s.gamepad.thumb_rx > max_rx) max_rx = s.gamepad.thumb_rx;
      if (v > 0 && v < 32767) {
        if (v < min_partial) min_partial = v;
        if (full_seen && !*full_seen) ++partial_before_full;
      }
      if (full_seen && v == 32767) *full_seen = true;
    }
  };
  driver.TestSetLook(true, "menu_20");
  poll();  // the poll that sees Look Mode begin drops motion pending at the change
  bool full_seen = false;
  driver.TestMouseMotion(400.0f, 0.0f);
  max_lx = max_rx = 0;
  look_frames(30, &full_seen);
  check("Look Mode: mouse right drives the left stick right, never the right stick", max_lx > 0 && max_rx == 0);
  check("Look Mode: a direction starts with full deflection only (the title's calibration)",
        full_seen && partial_before_full == 0);
  min_partial = 32767;
  for (int k = 0; k < 20; ++k) {
    driver.TestMouseMotion(30.0f, 0.0f);
    look_frames(1);
  }
  look_frames(30);
  check("Look Mode: after it, smooth motion uses partial deflections, never below 0.45",
        min_partial < 32767 && min_partial >= int16_t(0.45 * 32767));
  driver.TestMouseMotion(0.0f, -300.0f);
  int up = 0;
  for (int i = 0; i < 20; ++i) up += (poll(), s.gamepad.thumb_ly > 0);
  check("Look Mode: mouse up drives the stick up (the title's Look Mode tilts the view up with it, E-331)", up >= 1);
  look_frames(30);
  key("D", true);
  driver.TestMouseMotion(-400.0f, 0.0f);
  poll();
  check("Look Mode: a held movement key wins on its axis", s.gamepad.thumb_lx == 32767);
  key("D", false);
  int left = 0;
  for (int i = 0; i < 20; ++i) left += (poll(), s.gamepad.thumb_lx < 0);
  check("Look Mode: the mouse motion made under the key does not come back after it", left == 0);
  driver.TestMouseMotion(5000.0f, 0.0f);
  driver.TestSetLook(false, "menu_20");
  int lx_after = 0, rx_after = 0;
  for (int i = 0; i < 20; ++i) {
    poll();
    lx_after += s.gamepad.thumb_lx != 0;
    rx_after += s.gamepad.thumb_rx != 0;
  }
  check("Look Mode ends: no left stick and no right-stick backlog from the motion pending at the change",
        lx_after == 0 && rx_after == 0);
  driver.TestMouseMotion(50.0f, 0.0f);
  on = 0;
  for (int i = 0; i < 12; ++i) on += (poll(), s.gamepad.thumb_rx == 32767);
  check("outside Look Mode: the D-138 camera again (right stick)", on >= 2 && on <= 4 && s.gamepad.thumb_lx == 0);
  flag("mnk_mouse", "false");
  driver.TestSetLook(true, "menu_20");
  driver.TestMouseMotion(400.0f, 0.0f);
  int any = 0;
  for (int i = 0; i < 20; ++i) any += (poll(), s.gamepad.thumb_lx != 0 || s.gamepad.thumb_rx != 0);
  check("Look Mode with Mouse Camera off: nothing", any == 0);
  flag("mnk_mouse", "true");
  driver.TestSetLook(true, "wood_10");  // a new level: the calibration guard is re-armed
  poll();
  full_seen = false;
  partial_before_full = 0;
  driver.TestMouseMotion(400.0f, 0.0f);
  look_frames(30, &full_seen);
  check("Look Mode in a new level: full deflection first again", full_seen && partial_before_full == 0);
  driver.TestSetLook(false, "wood_10");

  std::printf("R3HD_MOUSE_DRIVER %s %d/%d\n", failures ? "FAIL" : "PASS", checks - failures, checks);
  std::fflush(stdout);
  return failures ? 1 : 0;
}
