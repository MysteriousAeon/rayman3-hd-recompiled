"""Replay after r3hd_dualsense_patch.py at the same pin (last in the chain): the controller map (D-115; D-116 adds the
trigger and stick exchanges, ApplyAnalog, beside the buttons). Idempotent; a tree patched by D-115 is migrated.

Installed header: r3hd_padmap.h (the map, SDK-free; tools/r3hd_padmap_test.cpp tests it).
  * src/input/input_system.cpp: GetState maps the buttons of every non-synthetic device (a physical pad, SDL or XInput)
    before the devices of a guest user are merged, so the keyboard's state (its own keybind_* map) and the NOP device
    never pass through it; GetKeystroke maps a physical pad's button virtual key the same way. The factory logs one
    `R3HD padmap state=default|custom|invalid map=.. error=..` line at the end of the
    factory, in every run (configuration, never a press).
  * src/kernel/xam/xam_input.cpp (reset to the pin by the M2 replay): with R3HD_NONINTRUSIVE and R3HD_PADMAP_TEST a
    hidden run's scheduled pad state is mapped as a physical pad's would be (test only; tools/r3hd_padmap_game.py).
The SDL driver (its pad state, the DualSense light bar / R2 policy of D-102 / D-105, rumble), sticks, triggers and the
guest are not touched. No generated code, no guest memory write, no new device output.
"""
from m3_runtime_patch import SDK
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

SYSTEM = 'src/input/input_system.cpp'

STATE_MAP_D115 = (
    '    // D-115: the controller button map, physical pads only (the keyboard keeps its own keybind_* map).\n'
    '    if (const DeviceInfo* info = DeviceInfoFor(id); info && !info->synthetic) {\n'
    '      state.gamepad.buttons = r3hd_padmap::Get().Apply(static_cast<uint16_t>(state.gamepad.buttons));\n'
    '    }\n')
STATE_MAP = (
    '    // D-115 / D-116: the controller map, physical pads only (the keyboard keeps its own keybind_* map).\n'
    '    if (const DeviceInfo* info = DeviceInfoFor(id); info && !info->synthetic) {\n'
    '      const auto& pad_map = r3hd_padmap::Get();\n'
    '      state.gamepad.buttons = pad_map.Apply(static_cast<uint16_t>(state.gamepad.buttons));\n'
    '      uint8_t lt = state.gamepad.left_trigger, rt = state.gamepad.right_trigger;\n'
    '      int16_t lx = state.gamepad.thumb_lx, ly = state.gamepad.thumb_ly;\n'
    '      int16_t rx = state.gamepad.thumb_rx, ry = state.gamepad.thumb_ry;\n'
    '      pad_map.ApplyAnalog(lt, rt, lx, ly, rx, ry);\n'
    '      state.gamepad.left_trigger = lt, state.gamepad.right_trigger = rt;\n'
    '      state.gamepad.thumb_lx = lx, state.gamepad.thumb_ly = ly;\n'
    '      state.gamepad.thumb_rx = rx, state.gamepad.thumb_ry = ry;\n'
    '    }\n')
KEY_MAP = (
    '      if (const DeviceInfo* info = DeviceInfoFor(id); info && !info->synthetic) {  // D-115: as GetState\n'
    '        out_keystroke->virtual_key = r3hd_padmap::Get().MapKey(static_cast<uint16_t>(out_keystroke->virtual_key));\n'
    '      }\n')
FACTORY_LOG = (
    '  {  // D-115: the controller button map of this launch (configuration, never a press)\n'
    '    const auto& pad_map = r3hd_padmap::Get();\n'
    '    REXLOG_INFO("R3HD padmap state={} map={} error={}", r3hd_padmap::StateName(pad_map.state()),\n'
    '                pad_map.text().empty() ? std::string("-") : pad_map.text(),\n'
    '                pad_map.error().empty() ? std::string("-") : pad_map.error());\n'
    '  }\n')
# At the end of the factory: the M23 patch searches the text around its own log line (AGENTS: never insert there).
FACTORY_END = '  input->SetDeviceAssignment(std::make_unique<SlotAssignment>());\n  return input;\n}\n'
M23_LOG = (
    '  REXLOG_INFO(m23haptics::kMarker, m23haptics::Suppressed() ? "suppressed" : "normal",\n'
    '              (m23_pads && !tool_mode) ? "allowed" : "none");\n')
M32_LINE = '    if (m32keys::Enabled()) s = m32keys::Sample(bool(input_state));  // M32 (D-069): through the real driver\n'
TEST_MAP = (
    '    if (r3hd_padmap::ScheduleTest()) {  // D-115 (test only): the scheduled state as a physical pad\'s\n'
    '      static uint16_t padmap_last = 0;\n'
    '      const uint16_t mapped = r3hd_padmap::Get().Apply(s.buttons);\n'
    '      if (mapped != padmap_last) {\n'
    '        padmap_last = mapped;\n'
    '        REXLOG_INFO("R3HD padmap_test buttons={:04X} mapped={:04X}", s.buttons, mapped);\n'
    '      }\n'
    '      s.buttons = mapped;\n'
    '      uint8_t lt = s.lt, rt = s.rt;  // D-116: the analog exchanges, as GetState\n'
    '      int16_t lx = s.lx, ly = s.ly, rx = s.rx, ry = s.ry;\n'
    '      r3hd_padmap::Get().ApplyAnalog(lt, rt, lx, ly, rx, ry);\n'
    '      s.lt = lt, s.rt = rt, s.lx = lx, s.ly = ly, s.rx = rx, s.ry = ry;\n'
    '    }\n')

if __name__ == '__main__':
    install('r3hd_padmap.h')
    system = SDK / SYSTEM
    if STATE_MAP_D115 in system.read_text():  # D-116: a tree patched by D-115 gets the analog lines too
        system.write_text(system.read_text().replace(STATE_MAP_D115, STATE_MAP))
        print('migrated the D-115 lines in', SYSTEM)

    patch_once(SYSTEM, [
        ('#include <rex/m23_haptics.h>\n', '#include <rex/m23_haptics.h>\n#include <rex/r3hd_padmap.h>\n'),
        ('    if (driver->GetDeviceState(id, &state) != X_ERROR_SUCCESS) {\n      continue;\n    }\n',
         '    if (driver->GetDeviceState(id, &state) != X_ERROR_SUCCESS) {\n      continue;\n    }\n' + STATE_MAP),
        ('    if (result == X_ERROR_SUCCESS) {\n      out_keystroke->user_index = static_cast<uint8_t>(user_index);\n',
         '    if (result == X_ERROR_SUCCESS) {\n' + KEY_MAP +
         '      out_keystroke->user_index = static_cast<uint8_t>(user_index);\n'),
        (FACTORY_END, FACTORY_LOG + FACTORY_END),
    ])

    patch_once('src/kernel/xam/xam_input.cpp', [
        ('#include <rex/m32_key_test.h>\n', '#include <rex/m32_key_test.h>\n#include <rex/r3hd_padmap.h>\n'),
        (M32_LINE, M32_LINE + TEST_MAP),
    ])
