"""Replay after r3hd_mouse_patch.py at the same pin (last in the chain): the in-game PC Settings panel's input gate,
pointer and input-ownership hook (D-139). Idempotent.

Installed header: r3hd_hostui_gate.h (KeyGate / PadGate; SDK-free, tools/r3hd_hostui_gate_test.cpp).
  * include/rex/rex_app.h, src/ui/rex_app.cpp: SetHostUiInputBlocked(bool) for an app's own panel. While it is set the
    SDK's existing is_active() callback answers false, so every driver gives the guest a neutral, connected source
    (the path the SDK's own overlays used). Nothing sets it unless the app opens a panel.
  * src/input/mnk/mnk_input_driver.cpp (reset to the pin by the M4 replay; runs on the M32 / M49 / D-138 text): taps
    latched while the input is held are dropped, keys held when it comes back are withheld until their key-up
    (KeyGate). Mouse buttons and the pointer lock keep D-138's own rule (no press arms while is_active() is false).
  * src/input/sdl/sdl_input_driver.cpp + header, src/input/xinput/xinput_input_driver.cpp + header: PadGate on every
    state sample and on the keystroke path (no DOWN for input held through the panel; no repeat of a withheld button).
  * include/rex/ui/window.h, window_sdl.h / .cpp: Window::SetHostUiCursor(bool) shows the pointer while the panel is
    open through the M21 rule (tools/m21_cursor.h HostUi; SDL_ShowCursor / SDL_HideCursor only, never a warp, grab or
    capture; a hidden test window never touches cursor state).
No generated code, no guest memory write, no new device output, no global input.
"""
from m3_runtime_patch import SDK
from m8_runtime_patch import patch_once
from m16_runtime_patch import install


def replace_in_function(rel, start, end, before, after):
    """Replace every `before` inside one function body (idempotent: done once `after` is in the body)."""
    path = SDK / rel
    text = path.read_text()
    a = text.index(start)
    b = text.index(end, a)
    body = text[a:b]
    if after in body:
        return
    assert before in body, (rel, start, before)
    path.write_text(text[:a] + body.replace(before, after) + text[b:])
    print('patched', rel, start.split('(')[0])


def unpatch(rel, old, new):
    """Migration of a superseded D-139 insert in a file the replay does not reset (idempotent)."""
    path = SDK / rel
    text = path.read_text()
    if old in text:
        path.write_text(text.replace(old, new))
        print('migrated', rel)


def main():
    install('r3hd_hostui_gate.h')
    install('m21_cursor.h')  # D-139 adds HostUi to the M21 rule

    # --- the app's ownership hook -------------------------------------------------------------------------------
    patch_once('include/rex/rex_app.h', [
        ('  ui::ImGuiDrawer* imgui_drawer() const { return imgui_drawer_.get(); }\n',
         '  ui::ImGuiDrawer* imgui_drawer() const { return imgui_drawer_.get(); }\n'
         '  // D-139: an app\'s own panel holds the input while this is set: the guest sees neutral, connected sources.\n'
         '  void SetHostUiInputBlocked(bool blocked) { host_ui_input_blocked_.store(blocked, std::memory_order_release); }\n'
         '  bool HostUiInputBlocked() const { return host_ui_input_blocked_.load(std::memory_order_acquire); }\n'),
        (' private:\n  std::function<void(PathConfig)> MakeResumeCallback();\n',
         ' private:\n  std::atomic<bool> host_ui_input_blocked_{false};  // D-139\n'
         '  std::function<void(PathConfig)> MakeResumeCallback();\n'),
    ])
    patch_once('src/ui/rex_app.cpp', [
        ('      input_sys->SetActiveCallback([this]() {\n',
         '      input_sys->SetActiveCallback([this]() {\n'
         '        if (host_ui_input_blocked_.load(std::memory_order_acquire)) return false;  // D-139\n'),
    ])

    # --- keyboard / mouse driver ------------------------------------------------------------------------------
    mnk = 'src/input/mnk/mnk_input_driver.cpp'
    patch_once('include/rex/input/mnk/mnk_input_driver.h', [
        ('#include <rex/r3hd_mouse.h>\n', '#include <rex/r3hd_mouse.h>\n#include <rex/r3hd_hostui_gate.h>\n'),
        ('  uint16_t pending_buttons_ = 0;\n',
         '  uint16_t pending_buttons_ = 0;\n  r3hd_hostui::KeyGate host_gate_;  // D-139\n'),
    ])
    patch_once(mnk, [
        ('  const bool live = has_focus_ && is_active();\n  QueueMouseCaptureUpdate(',
         '  const bool host_active = is_active();  // D-139: false while a host panel holds the input\n'
         '  const bool live = has_focus_ && host_active;\n  QueueMouseCaptureUpdate('),
        ('      mouse_buttons_.Disarm();\n      mouse_camera_.Drop();\n      mouse_dx_ = mouse_dy_ = 0.0f;\n    }\n',
         '      mouse_buttons_.Disarm();\n      mouse_camera_.Drop();\n      mouse_dx_ = mouse_dy_ = 0.0f;\n'
         '      host_gate_.Sync(host_active, key_down_);  // D-139\n'
         '      if (!host_active) pending_buttons_ = 0;  // a tap made while a panel holds the input never acts\n'
         '    }\n'),
        ('  std::lock_guard lock(state_mutex_);\n\n  // D-138: this poll\'s mouse buttons',
         '  std::lock_guard lock(state_mutex_);\n\n'
         '  // D-139: a key held through a host panel stays withheld until its key-up; taps latched before are dropped.\n'
         '  if (host_gate_.Sync(host_active, key_down_)) pending_buttons_ = 0;\n\n'
         '  // D-138: this poll\'s mouse buttons'),
        ('    key_down_[r3hd_mouse::kVk[i]] = ((mouse_pressed >> i) & 1) != 0;\n  }\n',
         '    key_down_[r3hd_mouse::kVk[i]] = ((mouse_pressed >> i) & 1) != 0;\n  }\n'
         '  bool gate_keys[r3hd_hostui::KeyGate::kKeys];  // D-139: what the bindings below may see\n'
         '  host_gate_.Mask(key_down_, gate_keys);\n'),
        ('  SetKeyState(vk, true);\n',
         '  // D-139: keys held through a host panel are withheld until released; nothing latches while one is open.\n'
         '  const bool host_active = is_active();\n'
         '  if (host_gate_.Sync(host_active, key_down_)) pending_buttons_ = 0;\n'
         '  SetKeyState(vk, true);\n'
         '  if (!host_active) return;\n'
         '  bool gate_keys[r3hd_hostui::KeyGate::kKeys];\n'
         '  host_gate_.Mask(key_down_, gate_keys);\n'),
        ('  SetKeyState(vk, false);\n}\n',
         '  SetKeyState(vk, false);\n  host_gate_.Released(vk);  // D-139\n}\n'),
        ('    mouse_buttons_.Clear();  // D-138\n',
         '    mouse_buttons_.Clear();  // D-138\n    host_gate_.ClearHeld();  // D-139: focus loss released every key\n'),
    ])
    replace_in_function(mnk, 'X_RESULT MnkInputDriver::GetDeviceState(', 'X_RESULT MnkInputDriver::SetDeviceVibration(',
                        'IsBindPressed(key_down_, ', 'IsBindPressed(gate_keys, ')
    replace_in_function(mnk, 'void MnkInputDriver::OnKeyDown(', 'void MnkInputDriver::OnKeyUp(',
                        'IsBindPressed(key_down_, ', 'IsBindPressed(gate_keys, ')

    # --- SDL pads -----------------------------------------------------------------------------------------------
    patch_once('include/rex/input/sdl/sdl_input_driver.h', [
        ('#include <rex/r3hd_ds_sdl.h>\n', '#include <rex/r3hd_ds_sdl.h>\n#include <rex/r3hd_hostui_gate.h>\n'),
        ('    r3hd_ds::PadOutput ds;  // D-102\n',
         '    r3hd_ds::PadOutput ds;  // D-102\n    r3hd_hostui::PadGate host_gate;  // D-139\n'),
    ])
    patch_once('src/input/sdl/sdl_input_driver.cpp', [
        # After the inactive block: the D-102 patch searches the text between the memcpy and that block.
        ('    std::memset(&out_state->gamepad, 0, sizeof(out_state->gamepad));\n  }\n  return X_ERROR_SUCCESS;\n',
         '    std::memset(&out_state->gamepad, 0, sizeof(out_state->gamepad));\n  }\n'
         '  controller->host_gate.Apply(is_active, out_state->gamepad);  // D-139: held input waits for its release\n'
         '  return X_ERROR_SUCCESS;\n'),
        ('  const uint64_t curr_butts =\n'
         '      is_active ? (static_cast<uint64_t>(static_cast<uint16_t>(controller->state.gamepad.buttons)) |\n'
         '                   AnalogToKeyfield(controller->state.gamepad))\n'
         '                : uint64_t(0);\n'
         '  KeystrokeState& last = controller->keystroke;\n',
         '  // D-139: the gate of GetDeviceState: no DOWN for input held through a host panel.\n'
         '  X_INPUT_GAMEPAD gated = controller->state.gamepad;\n'
         '  controller->host_gate.Apply(is_active, gated);\n'
         '  const uint64_t curr_butts =\n'
         '      is_active ? (static_cast<uint64_t>(static_cast<uint16_t>(gated.buttons)) | AnalogToKeyfield(gated))\n'
         '                : uint64_t(0);\n'
         '  KeystrokeState& last = controller->keystroke;\n'
         '  if (controller->host_gate.Holding() && last.repeat_state != RepeatState::Idle &&\n'
         '      !(curr_butts & (uint64_t(1) << last.repeat_butt_idx)))\n'
         '    last.repeat_state = RepeatState::Idle;  // D-139: a withheld button never repeats\n'),
    ])

    # --- XInput pads (input_backend=xinput only) ----------------------------------------------------------------
    # These two files are not reset by the replay: the first D-139 lines (no lock) are taken back first.
    unpatch('include/rex/input/xinput/xinput_input_driver.h',
            '  r3hd_hostui::PadGate host_gates_[4];  // D-139, by XInput slot\n  void* module_;\n', '  void* module_;\n')
    unpatch('src/input/xinput/xinput_input_driver.cpp',
            '  if (user_index < 4) host_gates_[user_index].Apply(is_active(), out_state->gamepad);  // D-139\n', '')
    unpatch('src/input/xinput/xinput_input_driver.cpp',
            '  // D-139: no key-down while a host panel holds the input or input held through it waits for release.\n'
            '  if ((!is_active() || (user_index < 4 && host_gates_[user_index].Holding())) &&\n'
            '      !(native_keystroke.Flags & XINPUT_KEYSTROKE_KEYUP))\n'
            '    return X_ERROR_EMPTY;\n', '')
    patch_once('include/rex/input/xinput/xinput_input_driver.h', [
        ('#include <rex/input/input_driver.h>\n',
         '#include <rex/input/input_driver.h>\n#include <rex/r3hd_hostui_gate.h>\n'),
        (' private:\n', ' private:\n  r3hd_hostui::PadGate host_gates_[4];  // D-139, by XInput slot\n'
                        '  std::mutex host_gates_mutex_;  // state and keystroke calls may come from different threads\n'),
    ])
    patch_once('src/input/xinput/xinput_input_driver.cpp', [
        ('  out_state->gamepad.thumb_ry = native_state.state.Gamepad.sThumbRY;\n',
         '  out_state->gamepad.thumb_ry = native_state.state.Gamepad.sThumbRY;\n'
         '  if (user_index < 4) {  // D-139\n'
         '    std::lock_guard lock(host_gates_mutex_);\n'
         '    host_gates_[user_index].Apply(is_active(), out_state->gamepad);\n'
         '  }\n'),
        ('  out_keystroke->virtual_key = native_keystroke.VirtualKey;\n',
         '  // D-139: no key-down while a host panel holds the input or input held through it waits for release\n'
         '  // (a title that never polls the state is not withheld after the panel closes).\n'
         '  bool withheld = !is_active();\n'
         '  if (user_index < 4 && !withheld) {\n'
         '    std::lock_guard lock(host_gates_mutex_);\n'
         '    withheld = host_gates_[user_index].Withholding();\n'
         '  }\n'
         '  if (withheld && !(native_keystroke.Flags & XINPUT_KEYSTROKE_KEYUP))\n'
         '    return X_ERROR_EMPTY;\n'
         '  out_keystroke->virtual_key = native_keystroke.VirtualKey;\n'),
    ])

    # --- pointer while the panel is open ------------------------------------------------------------------------
    patch_once('include/rex/ui/window.h', [
        ('  void SetCursorVisibility(CursorVisibility new_cursor_visibility);\n',
         '  void SetCursorVisibility(CursorVisibility new_cursor_visibility);\n'
         '  // D-139: a host panel takes the mouse; the pointer shows while it is open (UI thread only).\n'
         '  void SetHostUiCursor(bool open) { ApplyHostUiCursor(open); }\n'),
        ('  virtual void ApplyNewCursorVisibility(CursorVisibility old_cursor_visibility) {\n',
         '  virtual void ApplyHostUiCursor(bool open) { (void)open; }\n'
         '  virtual void ApplyNewCursorVisibility(CursorVisibility old_cursor_visibility) {\n'),
    ])
    patch_once('include/rex/ui/window_sdl.h', [
        ('  void ApplyNewCursorVisibility(CursorVisibility old_cursor_visibility) override;\n',
         '  void ApplyNewCursorVisibility(CursorVisibility old_cursor_visibility) override;\n'
         '  void ApplyHostUiCursor(bool open) override;  // D-139\n'),
    ])
    patch_once('src/ui/window_sdl.cpp', [
        ('void WindowSDL::ApplyNewCursorVisibility(CursorVisibility old_cursor_visibility) {\n',
         'void WindowSDL::ApplyHostUiCursor(bool open) {\n'
         '  if (std::getenv("R3HD_NONINTRUSIVE")) return;\n'
         '  if (M21CursorAuto()) M21ApplyCursor(M21Tracker().HostUi(open), "host_ui");\n'
         '}\n\n'
         'void WindowSDL::ApplyNewCursorVisibility(CursorVisibility old_cursor_visibility) {\n'),
    ])


if __name__ == '__main__':
    main()
