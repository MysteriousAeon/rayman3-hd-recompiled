"""Replay after the M46 patch at the same pin: hold-to-walk for the keyboard (M49, D-088).

`src/input/mnk/mnk_input_driver.cpp` (not reset by the M2 replay; every edit is idempotent):
  * `keybind_walk` (default empty: no key) and `mnk_walk_magnitude` (0.1 .. 1.0, default 0.5): while a Walk key is
    held, the keyboard's left stick keeps its direction and gets that length (tools/m49_walk.h), the same for straight
    and diagonal directions. Released, the stick is exactly what the keys gave before. The right stick, triggers,
    buttons and the mouse are not touched; a physical controller never passes through this driver.
  * one `M49 keyboard walk=... magnitude=...` line at the first poll (the launch's configuration, never keystrokes).

tools/play.ps1 passes both through the keymap's arguments (tools/r3hd_settings.py). Host-only: no generated code, no
guest memory write, no scheduling change, no new device output.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

DRIVER = 'src/input/mnk/mnk_input_driver.cpp'

if __name__ == '__main__':
    install('m49_walk.h')

    patch_once(DRIVER, [
        ('REXCVAR_DEFINE_STRING(keybind_guide, "", "Input/Keybinds/Controller", "Guide button");\n',
         'REXCVAR_DEFINE_STRING(keybind_guide, "", "Input/Keybinds/Controller", "Guide button");\n'
         '// M49 (D-088): hold-to-walk (tools/m49_walk.h).\n'
         'REXCVAR_DEFINE_STRING(keybind_walk, "", "Input/Keybinds/Controller", "Walk (hold): shorter left stick");\n'
         'REXCVAR_DEFINE_DOUBLE(mnk_walk_magnitude, 0.5, "Input", "Left stick length while Walk is held")\n'
         '    .range(0.1, 1.0);\n'),
        ('#include <rex/input/mnk/mnk_input_driver.h>\n',
         '#include <rex/input/mnk/mnk_input_driver.h>\n#include <rex/m49_walk.h>\n'),
        # The configuration line is written at the first poll: Setup's text is the M32 patch's search text.
        ('  if (IsBindPressed(key_down_, REXCVAR_GET(keybind_lstick_down)))\n    ly -= INT16_MAX;\n\n',
         '  if (IsBindPressed(key_down_, REXCVAR_GET(keybind_lstick_down)))\n    ly -= INT16_MAX;\n'
         '  // M49 (D-088): hold-to-walk.\n'
         '  static bool m49_logged = false;\n'
         '  if (!m49_logged) {\n'
         '    m49_logged = true;\n'
         '    REXLOG_INFO("M49 keyboard walk={} magnitude={}", REXCVAR_GET(keybind_walk), REXCVAR_GET(mnk_walk_magnitude));\n'
         '  }\n'
         '  m49walk::Apply(lx, ly, IsBindPressed(key_down_, REXCVAR_GET(keybind_walk)), REXCVAR_GET(mnk_walk_magnitude));\n\n'),
    ])
