// Real MnK driver regression: a discrete tap between state polls is sampled once.
#include <rex/input/mnk/mnk_input_driver.h>
#include <rex/ui/ui_event.h>
#include <rex/cvar.h>
#include <cstdio>
using namespace rex;
using namespace rex::input;
int main() {
  int checks = 0, failures = 0;
  auto check = [&](bool ok) { ++checks; if (!ok) ++failures; };
  check(rex::cvar::SetFlagByName("mnk_mode", "true"));
  mnk::MnkInputDriver driver(nullptr, 0);
  check(driver.Setup() == X_STATUS_SUCCESS);
  rex::ui::UISetupEvent focus(nullptr, false); driver.OnGotFocus(focus);
  std::vector<DeviceInfo> devices; driver.EnumerateDevices(devices); check(devices.size() == 1);
  if (devices.empty()) return 2;
  auto id = devices[0].id;
  rex::ui::KeyEvent start(nullptr, rex::ui::VirtualKey::kReturn, 1, false, false, false, false, false);
  X_INPUT_STATE state{};
  driver.OnKeyDown(start); driver.OnKeyUp(start);
  check(driver.GetDeviceState(id, &state) == X_ERROR_SUCCESS);
  check(uint16_t(state.gamepad.buttons) == X_INPUT_GAMEPAD_START);
  driver.GetDeviceState(id, &state); check(uint16_t(state.gamepad.buttons) == 0);
  driver.OnKeyDown(start);
  driver.GetDeviceState(id, &state); check(uint16_t(state.gamepad.buttons) == X_INPUT_GAMEPAD_START);
  driver.GetDeviceState(id, &state); check(uint16_t(state.gamepad.buttons) == X_INPUT_GAMEPAD_START);
  driver.OnKeyUp(start); driver.GetDeviceState(id, &state); check(uint16_t(state.gamepad.buttons) == 0);
  driver.OnKeyDown(start); driver.OnKeyUp(start); driver.OnLostFocus(focus); driver.OnGotFocus(focus);
  driver.GetDeviceState(id, &state); check(uint16_t(state.gamepad.buttons) == 0);
  driver.OnKeyDown(start); driver.OnKeyUp(start);
  driver.GetDeviceState(id, nullptr); driver.GetDeviceState(id, &state);
  check(uint16_t(state.gamepad.buttons) == X_INPUT_GAMEPAD_START);
  driver.GetDeviceState(id, &state); check(uint16_t(state.gamepad.buttons) == 0);
  std::printf("MnK sampling: %d checks, %d failures: %s\n", checks, failures, failures ? "FAIL" : "PASS");
  return failures ? 1 : 0;
}
