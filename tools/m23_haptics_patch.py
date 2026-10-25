"""Replay after the M23 water patch at the same pin: hidden test runs never drive a controller actuator (D-053).

`tools/m23_haptics.h`. Three layers, all keyed on R3HD_NONINTRUSIVE (the variable that makes a run hidden):
1. XamInputSetState is answered at the XAM boundary (success for the test source's pad), no driver call.
2. CreateDefaultInputSystem adds no SDL / XInput pad driver: no controller is opened.
3. SDLInputDriver::SetDeviceVibration and XinputInputDriver::SetDeviceVibration return before the device call.
A visible session is unchanged. Every log carries `M23 haptics policy=`; tools/run_milestone6.ps1 refuses to
launch when the runtime library lacks that string (a build without the safeguard).

Host-only: no generated code, no guest patch, no guest memory write.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

if __name__ == '__main__':
    install('m23_haptics.h')

    patch_once('src/kernel/xam/xam_input.cpp', [
        ('#include <rex/m6_test_input.h>\n', '#include <rex/m6_test_input.h>\n#include <rex/m23_haptics.h>\n'),
        ('  if (!vibration) {\n    return X_ERROR_BAD_ARGUMENTS;\n  }\n\n  uint32_t actual_user_index = user_index;\n'
         '  if ((user_index & 0xFF) == 0xFF) {\n    // Always pin user to 0.\n    actual_user_index = 0;\n  }\n\n'
         '  (void)unk;  // Unused in this implementation\n',
         '  if (!vibration) {\n    return X_ERROR_BAD_ARGUMENTS;\n  }\n'
         '  // M23 (D-053): a hidden run answers vibration itself; no input driver is called.\n'
         '  if (m23haptics::Suppressed()) {\n'
         '    if (++m23haptics::Answered() == 1) REXKRNL_INFO("M23 haptics first vibration request answered without a device");\n'
         '    return m23haptics::HiddenSetStateResult(uint32_t(user_index));\n'
         '  }\n\n  uint32_t actual_user_index = user_index;\n'
         '  if ((user_index & 0xFF) == 0xFF) {\n    // Always pin user to 0.\n    actual_user_index = 0;\n  }\n\n'
         '  (void)unk;  // Unused in this implementation\n'),
    ])
    patch_once('src/input/input_system.cpp', [
        ('#include <rex/logging.h>\n', '#include <rex/logging.h>\n#include <rex/m23_haptics.h>\n'),
        ('  auto input = std::make_unique<InputSystem>(nullptr);\n\n  if (!tool_mode) {\n',
         '  auto input = std::make_unique<InputSystem>(nullptr);\n'
         '  // M23 (D-053): a hidden run opens no physical controller.\n'
         '  const bool m23_pads = m23haptics::PhysicalPadDriversAllowed(m23haptics::Suppressed());\n'
         '  REXLOG_INFO(m23haptics::kMarker, m23haptics::Suppressed() ? "suppressed" : "normal",\n'
         '              (m23_pads && !tool_mode) ? "allowed" : "none");\n\n  if (!tool_mode) {\n'),
        ('    if (REXCVAR_GET(input_backend) == "xinput") {', '    if (m23_pads && REXCVAR_GET(input_backend) == "xinput") {'),
        ('    if (REXCVAR_GET(input_backend) == "sdl") {', '    if (m23_pads && REXCVAR_GET(input_backend) == "sdl") {'),
    ])
    patch_once('src/input/sdl/sdl_input_driver.cpp', [
        ('#include <rex/logging.h>\n', '#include <rex/logging.h>\n#include <rex/m23_haptics.h>\n'),
        ('X_RESULT SDLInputDriver::SetDeviceVibration(DeviceId id, X_INPUT_VIBRATION* vibration) {\n',
         'X_RESULT SDLInputDriver::SetDeviceVibration(DeviceId id, X_INPUT_VIBRATION* vibration) {\n'
         '  // M23 (D-053): last line of defence; a hidden run has no SDL pad driver in the first place.\n'
         '  if (m23haptics::Suppressed()) {\n    ++m23haptics::StoppedAtSink();\n    return X_ERROR_SUCCESS;\n  }\n'),
    ])
    patch_once('src/input/xinput/xinput_input_driver.cpp', [
        ('#include <rex/logging.h>\n', '#include <rex/logging.h>\n#include <rex/m23_haptics.h>\n'),
        ('X_RESULT XinputInputDriver::SetDeviceVibration(DeviceId id, X_INPUT_VIBRATION* vibration) {\n',
         'X_RESULT XinputInputDriver::SetDeviceVibration(DeviceId id, X_INPUT_VIBRATION* vibration) {\n'
         '  // M23 (D-053): last line of defence; a hidden run has no XInput pad driver in the first place.\n'
         '  if (m23haptics::Suppressed()) {\n    ++m23haptics::StoppedAtSink();\n    return X_ERROR_SUCCESS;\n  }\n'),
    ])
