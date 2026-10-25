"""Replay after the M31 patch at the same pin: keyboard remapping at the runtime's own key -> pad boundary (M32, D-069).

1. `src/input/mnk/mnk_input_driver.cpp` (not reset by the M2 replay; every edit here is idempotent):
   - `mnk_modifier_keys` (default false = the SDK's exact matching): when true, Shift / Control are keys like any
     other (a bare "Shift" binding fires while Shift is held) and holding them no longer silences the other bare
     bindings; a binding with a prefix ("Shift+Up") then needs at least those modifiers. tools/play.ps1 passes it
     with the keymap's arguments (the layouts bind Shift / Control alone and never use a prefix).
   - one `M32 keyboard` line at start-up with every binding in effect (the keys a launch passed, not keystrokes).
   - a test-only switch on an instance (`SetTestEnabled`) so the hidden-run key source below can use the real
     driver while the run's own window driver stays disabled (`--mnk_mode=false`).
2. `include/rex/input/mnk/mnk_input_driver.h`: that switch.
3. `src/kernel/xam/xam_input.cpp` (reset to the pin by the M2 replay): with R3HD_NONINTRUSIVE and R3HD_KEYMAP_TEST
   the hidden run's pad state comes from `tools/m32_key_test.h` (scheduled keys -> SDL scancode translation -> the
   real driver with the live keybind_* settings) instead of m6's fixed scancode table.

Host-only: no generated code, no guest memory write, no scheduling change, no new device output.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

DRIVER = 'src/input/mnk/mnk_input_driver.cpp'

if __name__ == '__main__':
    install('m32_key_test.h')

    patch_once('include/rex/input/mnk/mnk_input_driver.h', [
        ('  void OnGotFocus(rex::ui::UISetupEvent& e) override;\n\n private:\n',
         '  void OnGotFocus(rex::ui::UISetupEvent& e) override;\n\n'
         '  // M32 (D-069): a window-less instance used by the hidden-run key source (tools/m32_key_test.h) only.\n'
         '  void SetTestEnabled(bool on) { test_enabled_ = on; }\n\n private:\n'),
        ('  uint32_t packet_number_ = 0;\n};\n',
         '  uint32_t packet_number_ = 0;\n\n  bool test_enabled_ = false;  // M32\n};\n'),
    ])

    patch_once(DRIVER, [
        ('REXCVAR_DEFINE_DOUBLE(mnk_sensitivity, 1.0, "Input", "Mouse sensitivity for right stick")\n'
         '    .range(0.01, 10.0);\n',
         'REXCVAR_DEFINE_DOUBLE(mnk_sensitivity, 1.0, "Input", "Mouse sensitivity for right stick")\n'
         '    .range(0.01, 10.0);\n'
         '// M32 (D-069): Shift / Control as keys of their own (see TokenPressed).\n'
         'REXCVAR_DEFINE_BOOL(mnk_modifier_keys, false, "Input",\n'
         '                    "Shift and Control are bindable keys; holding them does not silence other bindings");\n'),
        ('bool TokenPressed(const bool (&key_down)[256], std::string_view token, uint8_t live_mods) {\n'
         '  uint8_t want = TakeModifiers(token);\n'
         '  if (want != live_mods) {\n'
         '    return false;\n'
         '  }\n',
         'bool TokenPressed(const bool (&key_down)[256], std::string_view token, uint8_t live_mods) {\n'
         '  uint8_t want = TakeModifiers(token);\n'
         '  // M32 (D-069): with mnk_modifier_keys a prefix asks for at least those modifiers and a bare key ignores\n'
         '  // them, so a bare "Shift" or "Control" binding can fire and holding it keeps the other keys working.\n'
         '  if (REXCVAR_GET(mnk_modifier_keys) ? (want & live_mods) != want : want != live_mods) {\n'
         '    return false;\n'
         '  }\n'),
        ('X_STATUS MnkInputDriver::Setup() {\n  return X_STATUS_SUCCESS;\n}\n',
         'X_STATUS MnkInputDriver::Setup() {\n'
         '  // M32 (D-069): the bindings this launch passed (configuration, never keystrokes).\n'
         '  REXLOG_INFO("M32 keyboard test_instance={} mnk_mode={} modifier_keys={} a={} b={} x={} y={} start={} back={} "\n'
         '              "lt={} rt={} lb={} rb={} ls={} rs={} lup={} ldown={} lleft={} lright={} rup={} rdown={} "\n'
         '              "rleft={} rright={} dup={} ddown={} dleft={} dright={} guide={}",\n'
         '              test_enabled_, REXCVAR_GET(mnk_mode), REXCVAR_GET(mnk_modifier_keys), REXCVAR_GET(keybind_a),\n'
         '              REXCVAR_GET(keybind_b), REXCVAR_GET(keybind_x), REXCVAR_GET(keybind_y), REXCVAR_GET(keybind_start),\n'
         '              REXCVAR_GET(keybind_back), REXCVAR_GET(keybind_left_trigger), REXCVAR_GET(keybind_right_trigger),\n'
         '              REXCVAR_GET(keybind_left_shoulder), REXCVAR_GET(keybind_right_shoulder),\n'
         '              REXCVAR_GET(keybind_lstick_press), REXCVAR_GET(keybind_rstick_press), REXCVAR_GET(keybind_lstick_up),\n'
         '              REXCVAR_GET(keybind_lstick_down), REXCVAR_GET(keybind_lstick_left), REXCVAR_GET(keybind_lstick_right),\n'
         '              REXCVAR_GET(keybind_rstick_up), REXCVAR_GET(keybind_rstick_down), REXCVAR_GET(keybind_rstick_left),\n'
         '              REXCVAR_GET(keybind_rstick_right), REXCVAR_GET(keybind_dpad_up), REXCVAR_GET(keybind_dpad_down),\n'
         '              REXCVAR_GET(keybind_dpad_left), REXCVAR_GET(keybind_dpad_right), REXCVAR_GET(keybind_guide));\n'
         '  return X_STATUS_SUCCESS;\n}\n'),
        ('bool MnkInputDriver::IsEnabled() const {\n  return REXCVAR_GET(mnk_mode);\n}\n',
         'bool MnkInputDriver::IsEnabled() const {\n  return REXCVAR_GET(mnk_mode) || test_enabled_;  // M32: test instance\n}\n'),
    ])

    patch_once('src/kernel/xam/xam_input.cpp', [
        ('#include <rex/m16_sysui.h>\n', '#include <rex/m16_sysui.h>\n#include <rex/m32_key_test.h>\n'),
        ('    auto s = m6input::Sample(bool(input_state));\n',
         '    auto s = m6input::Sample(bool(input_state));\n'
         '    if (m32keys::Enabled()) s = m32keys::Sample(bool(input_state));  // M32 (D-069): through the real driver\n'),
    ])
