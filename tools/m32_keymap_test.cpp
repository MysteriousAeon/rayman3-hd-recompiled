// M32 (D-069): the real keyboard driver with the keymap's arguments. tools/m32_regression.py writes the case file from
// config/controls/keymap.json through tools/r3hd_settings.py (the arguments a launch passes) and runs this program:
//   set NAME VALUE            a runtime setting (keybind_*, mnk_modifier_keys), as the command line would set it
//   down KEY | up KEY         a key event by its runtime name (rex::ui::ParseVirtualKey)
//   tap KEY                   down and up before the next poll (a press shorter than a frame)
//   expect BUTTONS LT RT LX LY RX RY [LABEL]   the next poll's pad state (BUTTONS in hex)
//   release                   every key up, then one poll
// Exit 0 only when every expectation holds.
#include <rex/cvar.h>
#include <rex/input/mnk/mnk_input_driver.h>
#include <rex/ui/keybinds.h>
#include <rex/ui/ui_event.h>
#include <cstdio>
#include <fstream>
#include <set>
#include <sstream>
#include <string>
using namespace rex;
using namespace rex::input;

int main(int argc, char** argv) {
  if (argc < 2) { std::puts("usage: m32_keymap_test CASES"); return 2; }
  std::ifstream in(argv[1]);
  if (!in) { std::puts("FAIL: cannot read the case file"); return 2; }
  if (!rex::cvar::SetFlagByName("mnk_mode", "true")) { std::puts("FAIL: mnk_mode"); return 2; }
  mnk::MnkInputDriver driver(nullptr, 0);
  driver.Setup();
  rex::ui::UISetupEvent focus(nullptr, false);
  driver.OnGotFocus(focus);
  std::vector<DeviceInfo> devices;
  driver.EnumerateDevices(devices);
  if (devices.size() != 1) { std::puts("FAIL: device count"); return 2; }
  const auto id = devices[0].id;
  std::set<rex::ui::VirtualKey> held;
  int checks = 0, failures = 0, line_no = 0;
  std::string line;
  auto key = [&](const std::string& name, bool down) {
    auto vk = rex::ui::ParseVirtualKey(name);
    if (vk == rex::ui::VirtualKey::kNone) { std::printf("FAIL line %d: unknown key %s\n", line_no, name.c_str()); ++failures; return; }
    rex::ui::KeyEvent e(nullptr, vk, 1, !down, false, false, false, false);
    if (down) { driver.OnKeyDown(e); held.insert(vk); } else { driver.OnKeyUp(e); held.erase(vk); }
  };
  while (std::getline(in, line)) {
    ++line_no;
    std::istringstream f(line);
    std::string cmd;
    if (!(f >> cmd) || cmd[0] == '#') continue;
    if (cmd == "set") {
      std::string name, value;
      f >> name;
      std::getline(f, value);
      if (!value.empty() && value[0] == ' ') value.erase(0, 1);
      if (!rex::cvar::SetFlagByName(name, value)) { std::printf("FAIL line %d: set %s\n", line_no, name.c_str()); ++failures; }
    } else if (cmd == "down" || cmd == "up") {
      std::string name;
      f >> name;
      key(name, cmd == "down");
    } else if (cmd == "tap") {
      std::string name;
      f >> name;
      key(name, true);
      key(name, false);
    } else if (cmd == "release") {
      for (auto vk : std::set<rex::ui::VirtualKey>(held)) {
        rex::ui::KeyEvent e(nullptr, vk, 1, true, false, false, false, false);
        driver.OnKeyUp(e);
      }
      held.clear();
      X_INPUT_STATE drain{};
      driver.GetDeviceState(id, &drain);
    } else if (cmd == "expect") {
      unsigned buttons = 0;
      int lt = 0, rt = 0, lx = 0, ly = 0, rx = 0, ry = 0;
      std::string hex, label;
      f >> hex >> lt >> rt >> lx >> ly >> rx >> ry;
      std::getline(f, label);
      buttons = unsigned(std::stoul(hex, nullptr, 16));
      X_INPUT_STATE s{};
      driver.GetDeviceState(id, &s);
      ++checks;
      const auto& g = s.gamepad;
      if (unsigned(uint16_t(g.buttons)) != buttons || g.left_trigger != lt || g.right_trigger != rt ||
          g.thumb_lx != lx || g.thumb_ly != ly || g.thumb_rx != rx || g.thumb_ry != ry) {
        ++failures;
        std::printf("FAIL line %d%s: got %04X %d %d %d %d %d %d, want %04X %d %d %d %d %d %d\n", line_no, label.c_str(),
                    unsigned(uint16_t(g.buttons)), int(g.left_trigger), int(g.right_trigger), int(g.thumb_lx),
                    int(g.thumb_ly), int(g.thumb_rx), int(g.thumb_ry), buttons, lt, rt, lx, ly, rx, ry);
      }
    } else {
      std::printf("FAIL line %d: unknown command %s\n", line_no, cmd.c_str());
      ++failures;
    }
  }
  std::printf("M32 keymap driver: %d checks, %d failures: %s\n", checks, failures, failures || !checks ? "FAIL" : "PASS");
  std::fflush(stdout);
  return failures || !checks ? 1 : 0;
}
