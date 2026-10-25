"""Replay after M8 at the same pin: Escape is a third default key for the pad's B button.

First human playtest: a submenu could not be left with the keyboard. The title's cancel action is pad B
(legend "B Back"; hidden run m10_cancel1). B was already bound to Quote and Backspace; Escape, the key a
keyboard player tries first, was bound to nothing. Only the default of `keybind_b` changes: no other binding,
no controller path and no guest behaviour is touched, and an explicit `--keybind_b=` still wins.
"""
from m8_runtime_patch import patch_once

if __name__ == '__main__':
    patch_once('src/input/mnk/mnk_input_driver.cpp', [
        ('REXCVAR_DEFINE_STRING(keybind_b, "Quote,Backspace", "Input/Keybinds/Controller", "B button");',
         'REXCVAR_DEFINE_STRING(keybind_b, "Quote,Backspace,Escape", "Input/Keybinds/Controller", "B button");'),
    ])
