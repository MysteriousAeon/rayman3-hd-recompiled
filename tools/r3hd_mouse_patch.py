"""Replay after r3hd_padmap_patch.py at the same pin (last in the chain): native mouse controls (D-138). Idempotent.

Installed header: r3hd_mouse.h (button state, camera mapping, guest context; SDK-free, tools/r3hd_mouse_test.cpp).
  * src/input/mnk/mnk_input_driver.cpp (reset to the pin by the M4 replay, so this runs on the M32 / M49 text):
    - `mnk_mouse_buttons` (default false): mouse buttons act in gameplay through their keybind_* tokens (LMB, RMB, MMB,
      MB4, MB5). Their state is the mouse's own (r3hd_mouse::Buttons), never the keyboard's key_down_ / pending bits:
      the poll shows them to its own bindings only, a short click is latched for one poll, a release is always taken,
      and focus loss, an overlay taking the mouse, leaving gameplay or the option off need a fresh press.
    - `mnk_mouse` (the mouse camera) now counts only relative motion of the locked pointer, maps it through
      r3hd_mouse::Camera (the title's dead zone and hold, RE_NOTES "Mouse camera"), and never warps the cursor: without
      a pointer lock it stays off for that focus. Capture is requested only while the guest is in gameplay.
    - one `R3HD mouse camera=.. buttons=.. sensitivity=..` line at Setup (configuration, never input); `R3HD mouse
      capture=on|off|unavailable` when the pointer lock changes; test hooks for the hidden-run source.
  * include/rex/input/mnk/mnk_input_driver.h: the mouse members and test hooks (outside the M4 / M32 inserts).
  * src/ui/keybinds.cpp: the names MB4 / MB5 (side buttons).
  * src/kernel/xboxkrnl/xboxkrnl_video.cpp: VdSwap publishes the gameplay fact of r3hd_ds_state.h (read-only) to
    r3hd_mouse::g_context; `R3HD mouse context gameplay=..` on a change while a mouse option is on.
  * D-145: VdSwap also publishes the title's Look Mode flag (bytes 82C07D5C = 1 and 82C5C770 = FF, D-143, read-only, in
    gameplay only) and the level's identity; while it is set the mouse camera drives the LEFT stick through
    r3hd_mouse::LookStick (the title looks with it there and ignores the right stick, E-327); `R3HD mouse look_mode=..`
    on a change while a mouse option is on. Outside Look Mode the D-138 camera is unchanged.
tools/m32_key_test.h carries the hidden-run vocabulary (codes 400 / 401 counts, 410..414 buttons). No generated code,
no guest memory write, no new device output, no global input.
"""
from m3_runtime_patch import SDK
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

DRIVER = 'src/input/mnk/mnk_input_driver.cpp'
HEADER = 'include/rex/input/mnk/mnk_input_driver.h'

CVAR = (
    '// D-138: mouse buttons through their keybind_* tokens, in gameplay only (tools/r3hd_mouse.h).\n'
    'REXCVAR_DEFINE_BOOL(mnk_mouse_buttons, false, "Input",\n'
    '                    "Mouse buttons act as their bound pad inputs in gameplay");\n')

BUTTON_INDEX = (
    '// D-138: the mouse button\'s index in r3hd_mouse::Buttons, -1 for none.\n'
    'int MouseButtonIndex(rex::ui::MouseEvent::Button button) {\n'
    '  switch (button) {\n'
    '    case rex::ui::MouseEvent::Button::kLeft: return r3hd_mouse::kLeft;\n'
    '    case rex::ui::MouseEvent::Button::kRight: return r3hd_mouse::kRight;\n'
    '    case rex::ui::MouseEvent::Button::kMiddle: return r3hd_mouse::kMiddle;\n'
    '    case rex::ui::MouseEvent::Button::kX1: return r3hd_mouse::kX1;\n'
    '    case rex::ui::MouseEvent::Button::kX2: return r3hd_mouse::kX2;\n'
    '    default: return -1;\n'
    '  }\n'
    '}\n\n')

SETUP_LOG = (
    '  // D-138: the mouse configuration of this launch (never input).\n'
    '  r3hd_mouse::g_log.store(REXCVAR_GET(mnk_mouse) || REXCVAR_GET(mnk_mouse_buttons), std::memory_order_relaxed);\n'
    '  REXLOG_INFO("R3HD mouse camera={} buttons={} sensitivity={} test_instance={}", REXCVAR_GET(mnk_mouse),\n'
    '              REXCVAR_GET(mnk_mouse_buttons), REXCVAR_GET(mnk_sensitivity), test_enabled_);\n')

POLL_HEAD_OLD = (
    '  QueueMouseCaptureUpdate(IsEnabled() && REXCVAR_GET(mnk_mouse) && IsMouseLookActive() &&\n'
    '                          has_focus_ && is_active());\n'
    '\n'
    '  if (!is_active() || !has_focus_) {\n'
    '    if (out_state) {\n')
POLL_HEAD_NEW = (
    '  // D-138: and only while the guest is in gameplay; the front end, pause and other menus release the pointer.\n'
    '  const uint32_t mouse_context = r3hd_mouse::Context();\n'
    '  const bool mouse_gameplay = r3hd_mouse::Gameplay(mouse_context);\n'
    '  const bool live = has_focus_ && is_active();\n'
    '  QueueMouseCaptureUpdate(IsEnabled() && REXCVAR_GET(mnk_mouse) && IsMouseLookActive() && live &&\n'
    '                          mouse_gameplay);\n'
    '\n'
    '  if (!live) {\n'
    '    {\n'
    '      std::lock_guard lock(state_mutex_);  // D-138: a held mouse button needs a fresh press after this\n'
    '      mouse_look_.Drop();  // D-145\n'
    '      mouse_buttons_.Disarm();\n'
    '      mouse_camera_.Drop();\n'
    '      mouse_dx_ = mouse_dy_ = 0.0f;\n'
    '    }\n'
    '    if (out_state) {\n')

POLL_LOCK_OLD = '  std::lock_guard lock(state_mutex_);\n\n  uint16_t buttons = 0;\n'
POLL_LOCK_NEW = (
    '  std::lock_guard lock(state_mutex_);\n'
    '\n'
    '  // D-138: this poll\'s mouse buttons as their virtual keys, seen by this poll\'s bindings only (cleared below).\n'
    '  uint8_t mouse_pressed = 0;\n'
    '  if (out_state) {\n'
    '    if (mouse_context != mouse_context_) {  // gameplay began or ended since the last poll\n'
    '      mouse_context_ = mouse_context;\n'
    '      mouse_buttons_.DisarmOlder(mouse_context);\n'
    '      mouse_camera_.Drop();\n'
    '    }\n'
    '    mouse_pressed = mouse_buttons_.Poll(REXCVAR_GET(mnk_mouse_buttons) && mouse_gameplay);\n'
    '  }\n'
    '  for (int i = 0; i < r3hd_mouse::kButtonCount; ++i) {\n'
    '    key_down_[r3hd_mouse::kVk[i]] = ((mouse_pressed >> i) & 1) != 0;\n'
    '  }\n'
    '\n'
    '  uint16_t buttons = 0;\n')

CAMERA_OLD = (
    '  if (REXCVAR_GET(mnk_mouse) && IsMouseLookActive()) {\n'
    '    double sensitivity = REXCVAR_GET(mnk_sensitivity);\n'
    '    constexpr double kBaseScale = 200.0;\n'
    '    rx += static_cast<int32_t>(double(mouse_dx_) * sensitivity * kBaseScale);\n'
    '    ry += static_cast<int32_t>(double(-mouse_dy_) * sensitivity * kBaseScale);\n'
    '  }\n'
    '  // Drained unconditionally: deltas keep accumulating in OnMouseMove while the\n'
    '  // mouse is off, and toggling it on would otherwise dump the whole backlog\n'
    '  // into one frame as a camera snap.\n'
    '  mouse_dx_ = 0.0f;\n'
    '  mouse_dy_ = 0.0f;\n')
CAMERA_NEW = (
    '  for (int i = 0; i < r3hd_mouse::kButtonCount; ++i) {\n'
    '    key_down_[r3hd_mouse::kVk[i]] = false;  // D-138: the keyboard\'s own key state never holds a mouse button\n'
    '  }\n'
    '  // D-138: the mouse camera (tools/r3hd_mouse.h), only with the pointer locked, in gameplay. One gameplay poll is\n'
    '  // one guest frame of the title\'s fixed step, so stick time is counted in frames. A query without a state (null\n'
    '  // out_state) spends nothing.\n'
    '  if (out_state) {\n'
    '    const bool mouse_live = REXCVAR_GET(mnk_mouse) && IsMouseLookActive() && mouse_gameplay &&\n'
    '                            (relative_mouse_mode_ || test_enabled_);\n'
    '    // D-145: in the title\'s Look Mode the mouse drives the left stick (the title ignores the right one there);\n'
    '    // a key held on an axis wins. Either way the other mapping holds nothing, so no motion crosses the boundary.\n'
    '    mouse_look_.SetLevel(r3hd_mouse::Level());\n'
    '    const bool look_mode = r3hd_mouse::LookMode() && mouse_gameplay;\n'
    '    if (look_mode != mouse_look_mode_) {  // Look Mode began or ended: motion pending at the change is dropped\n'
    '      mouse_look_mode_ = look_mode;\n'
    '      mouse_dx_ = mouse_dy_ = 0.0f;\n'
    '      mouse_camera_.Drop();\n'
    '      mouse_look_.Drop();\n'
    '    }\n'
    '    if (look_mode) {\n'
    '      mouse_camera_.Drop();\n'
    '      mouse_look_.Add(mouse_dx_, mouse_dy_);\n'
    '      mouse_look_.Poll(mouse_live, REXCVAR_GET(mnk_sensitivity), r3hd_mouse::LookTuning{}, lx, ly);\n'
    '    } else {\n'
    '      mouse_look_.Drop();\n'
    '      mouse_camera_.Add(mouse_dx_, mouse_dy_);\n'
    '      mouse_camera_.Poll(mouse_live, r3hd_mouse::kPollMs, REXCVAR_GET(mnk_sensitivity), r3hd_mouse::CameraTuning{},\n'
    '                         rx, ry);\n'
    '    }\n'
    '    // Drained unconditionally: deltas keep accumulating in OnMouseMove while the\n'
    '    // mouse is off, and toggling it on would otherwise dump the whole backlog\n'
    '    // into one frame as a camera snap.\n'
    '    mouse_dx_ = 0.0f;\n'
    '    mouse_dy_ = 0.0f;\n'
    '  }\n')

QUEUE_OLD = 'void MnkInputDriver::QueueMouseCaptureUpdate(bool should_capture) {\n'
QUEUE_NEW = ('void MnkInputDriver::QueueMouseCaptureUpdate(bool should_capture) {\n'
             '  if (std::getenv("R3HD_NONINTRUSIVE")) should_capture = false;  // D-138: a hidden run never captures\n')

CAPTURE_OLD = (
    '  mouse_captured_ = true;\n'
    '  precapture_cursor_visibility_ = window->GetCursorVisibility();\n'
    '  window->SetCursorVisibility(rex::ui::Window::CursorVisibility::kHidden);\n'
    '  window->CaptureMouse();\n'
    '  relative_mouse_mode_ = window->SetRelativeMouseMode(true);\n'
    '  if (!relative_mouse_mode_) {\n'
    '    REXLOG_WARN("Pointer lock unavailable, mouse look falls back to recentering the cursor");\n'
    '  }\n'
    '  // Reset deltas to avoid a spike on capture start\n'
    '  std::lock_guard lock(state_mutex_);\n'
    '  mouse_dx_ = 0.0f;\n'
    '  mouse_dy_ = 0.0f;\n'
    '}\n')
CAPTURE_NEW = (
    '  if (mouse_lock_failed_) {\n'
    '    return;  // D-138: tried once in this focus; there is no cursor-warping fallback\n'
    '  }\n'
    '  mouse_captured_ = true;\n'
    '  precapture_cursor_visibility_ = window->GetCursorVisibility();\n'
    '  window->SetCursorVisibility(rex::ui::Window::CursorVisibility::kHidden);\n'
    '  window->CaptureMouse();\n'
    '  relative_mouse_mode_ = window->SetRelativeMouseMode(true);\n'
    '  if (!relative_mouse_mode_) {\n'
    '    REXLOG_WARN("R3HD mouse capture=unavailable (no pointer lock): the mouse camera is off until the next focus");\n'
    '    mouse_lock_failed_ = true;\n'
    '    ReleaseMouseCaptureFromUIThread(window);\n'
    '    return;\n'
    '  }\n'
    '  REXLOG_INFO("R3HD mouse capture=on");\n'
    '  // Reset deltas to avoid a spike on capture start\n'
    '  std::lock_guard lock(state_mutex_);\n'
    '  mouse_dx_ = 0.0f;\n'
    '  mouse_dy_ = 0.0f;\n'
    '  mouse_camera_.Drop();\n'
    '  mouse_look_.Drop();  // D-145\n'
    '}\n')

RELEASE_OLD = (
    '  window->SetRelativeMouseMode(false);\n'
    '  relative_mouse_mode_ = false;\n'
    '  window->ReleaseMouse();\n'
    '}\n')
RELEASE_NEW = (
    '  window->SetRelativeMouseMode(false);\n'
    '  relative_mouse_mode_ = false;\n'
    '  window->ReleaseMouse();\n'
    '  REXLOG_INFO("R3HD mouse capture=off");  // D-138: motion of the released pointer never reaches the camera\n'
    '  std::lock_guard lock(state_mutex_);\n'
    '  mouse_dx_ = 0.0f;\n'
    '  mouse_dy_ = 0.0f;\n'
    '  mouse_camera_.Drop();\n'
    '  mouse_look_.Drop();  // D-145\n'
    '}\n')

BUTTONS_OLD = (
    'void MnkInputDriver::OnMouseDown(rex::ui::MouseEvent& e) {\n'
    '  if (!IsEnabled() || !has_focus_)\n'
    '    return;\n'
    '  std::lock_guard lock(state_mutex_);\n'
    '  switch (e.button()) {\n'
    '    case rex::ui::MouseEvent::Button::kLeft:\n'
    '      SetKeyState(static_cast<uint16_t>(VirtualKey::kLButton), true);\n'
    '      break;\n'
    '    case rex::ui::MouseEvent::Button::kRight:\n'
    '      SetKeyState(static_cast<uint16_t>(VirtualKey::kRButton), true);\n'
    '      break;\n'
    '    case rex::ui::MouseEvent::Button::kMiddle:\n'
    '      SetKeyState(static_cast<uint16_t>(VirtualKey::kMButton), true);\n'
    '      break;\n'
    '    default:\n'
    '      break;\n'
    '  }\n'
    '}\n'
    '\n'
    'void MnkInputDriver::OnMouseUp(rex::ui::MouseEvent& e) {\n'
    '  if (!IsEnabled())\n'
    '    return;\n'
    '  std::lock_guard lock(state_mutex_);\n'
    '  switch (e.button()) {\n'
    '    case rex::ui::MouseEvent::Button::kLeft:\n'
    '      SetKeyState(static_cast<uint16_t>(VirtualKey::kLButton), false);\n'
    '      break;\n'
    '    case rex::ui::MouseEvent::Button::kRight:\n'
    '      SetKeyState(static_cast<uint16_t>(VirtualKey::kRButton), false);\n'
    '      break;\n'
    '    case rex::ui::MouseEvent::Button::kMiddle:\n'
    '      SetKeyState(static_cast<uint16_t>(VirtualKey::kMButton), false);\n'
    '      break;\n'
    '    default:\n'
    '      break;\n'
    '  }\n'
    '}\n')
BUTTONS_NEW = (
    'void MnkInputDriver::OnMouseDown(rex::ui::MouseEvent& e) {\n'
    '  // D-138: the mouse\'s own state (tools/r3hd_mouse.h), never the keyboard\'s. A press arms only while it may\n'
    '  // act: driver and option on, focused, no overlay holding the mouse, guest in gameplay.\n'
    '  const int b = MouseButtonIndex(e.button());\n'
    '  if (b < 0)\n'
    '    return;\n'
    '  const uint32_t context = r3hd_mouse::Context();\n'
    '  const bool live = IsEnabled() && has_focus_ && is_active() && REXCVAR_GET(mnk_mouse_buttons) &&\n'
    '                    r3hd_mouse::Gameplay(context);\n'
    '  std::lock_guard lock(state_mutex_);\n'
    '  mouse_buttons_.Down(r3hd_mouse::Button(b), live, context);\n'
    '}\n'
    '\n'
    'void MnkInputDriver::OnMouseUp(rex::ui::MouseEvent& e) {\n'
    '  // D-138: a release is always taken, also with the driver off or an overlay in front.\n'
    '  const int b = MouseButtonIndex(e.button());\n'
    '  if (b < 0)\n'
    '    return;\n'
    '  std::lock_guard lock(state_mutex_);\n'
    '  mouse_buttons_.Up(r3hd_mouse::Button(b));\n'
    '}\n'
    '\n'
    'void MnkInputDriver::TestMouseMotion(float dx, float dy) {\n'
    '  std::lock_guard lock(state_mutex_);\n'
    '  mouse_dx_ += dx;\n'
    '  mouse_dy_ += dy;\n'
    '}\n'
    '\n'
    'void MnkInputDriver::TestMouseButton(int button, bool down) {\n'
    '  static constexpr rex::ui::MouseEvent::Button kButtons[] = {\n'
    '      rex::ui::MouseEvent::Button::kLeft, rex::ui::MouseEvent::Button::kRight,\n'
    '      rex::ui::MouseEvent::Button::kMiddle, rex::ui::MouseEvent::Button::kX1, rex::ui::MouseEvent::Button::kX2};\n'
    '  if (button < 0 || button >= r3hd_mouse::kButtonCount)\n'
    '    return;\n'
    '  rex::ui::MouseEvent e(nullptr, kButtons[button], 0, 0);\n'
    '  if (down)\n'
    '    OnMouseDown(e);\n'
    '  else\n'
    '    OnMouseUp(e);\n'
    '}\n'
    '\n'
    'void MnkInputDriver::TestSetGameplay(bool gameplay) {\n'
    '  r3hd_mouse::PublishGameplay(gameplay);\n'
    '}\n'
    '\n'
    'void MnkInputDriver::TestSetLook(bool look, const char* level) {\n'
    '  r3hd_mouse::PublishLook(look);\n'
    '  r3hd_mouse::PublishLevel(level);\n'
    '}\n')

MOVE_OLD = (
    '    if (relative_mouse_mode_) {\n'
    '      // The pointer is locked, so the absolute position no longer moves.\n'
    '      mouse_dx_ += e.dx();\n'
    '      mouse_dy_ += e.dy();\n'
    '    } else {\n'
    '      mouse_dx_ += float(x - prev_mouse_x_);\n'
    '      mouse_dy_ += float(y - prev_mouse_y_);\n'
    '    }\n')
MOVE_NEW = (
    '    // D-138: only relative motion of the locked pointer counts; the position of a free pointer never does.\n'
    '    if (relative_mouse_mode_) {\n'
    '      mouse_dx_ += e.dx();\n'
    '      mouse_dy_ += e.dy();\n'
    '    }\n')
RECENTER_OLD = (
    '  // Without a pointer lock the cursor still has to be kept off the edges.\n'
    '  if (mouse_captured_ && !relative_mouse_mode_) {\n'
    '    RecenterCursorFromUIThread(x, y);\n'
    '  }\n')
RECENTER_NEW = '  // D-138: never a cursor warp; without a pointer lock the mouse camera is off (ApplyMouseCaptureFromUIThread).\n'

FOCUS_LOST_OLD = (
    '    pending_buttons_ = 0;\n'
    '    mouse_dx_ = 0.0f;\n'
    '    mouse_dy_ = 0.0f;\n'
    '  }\n'
    '  if (attached_window_) {\n')
FOCUS_LOST_NEW = (
    '    pending_buttons_ = 0;\n'
    '    mouse_dx_ = 0.0f;\n'
    '    mouse_dy_ = 0.0f;\n'
    '    mouse_buttons_.Clear();  // D-138\n'
    '    mouse_camera_.Drop();\n'
    '    mouse_look_.Drop();  // D-145\n'
    '  }\n'
    '  if (attached_window_) {\n')
FOCUS_GOT_OLD = 'void MnkInputDriver::OnGotFocus(rex::ui::UISetupEvent&) {\n  has_focus_ = true;\n}\n'
FOCUS_GOT_NEW = ('void MnkInputDriver::OnGotFocus(rex::ui::UISetupEvent&) {\n  has_focus_ = true;\n'
                 '  mouse_lock_failed_ = false;  // D-138: the pointer lock may be tried again\n}\n')

HEADER_MEMBERS = (
    '  // D-138: the mouse\'s own button state and camera (tools/r3hd_mouse.h), under state_mutex_.\n'
    '  r3hd_mouse::Buttons mouse_buttons_;\n'
    '  r3hd_mouse::Camera mouse_camera_;\n'
    '  r3hd_mouse::LookStick mouse_look_;  // D-145: the left stick in the title\'s Look Mode\n'
    '  bool mouse_look_mode_ = false;      // D-145: Look Mode at the last poll\n'
    '  uint32_t mouse_context_ = 0;\n'
    '  bool mouse_lock_failed_ = false;  // UI thread only\n'
    '\n')

VIDEO_BLOCK = (
    '  // D-138: the mouse\'s guest context (the read-only facts of r3hd_ds_state.h): no mouse input outside gameplay.\n'
    '  {\n'
    '    const uint8_t* membase = REX_KERNEL_MEMORY()->virtual_membase();\n'
    '    char level[16];\n'
    '    std::memcpy(level, membase + r3hd_ds::state::kLevelName, 15);\n'
    '    level[15] = 0;\n'
    '    const bool gameplay =\n'
    '        r3hd_ds::state::Decide(r3hd_ds::state::LoadBE(membase, r3hd_ds::state::kWorld), level,\n'
    '                               r3hd_ds::state::LoadBE(membase, r3hd_ds::state::kPause)).gameplay;\n'
    '    if (r3hd_mouse::PublishGameplay(gameplay) && r3hd_mouse::g_log.load(std::memory_order_relaxed)) {\n'
    '      REXLOG_INFO("R3HD mouse context gameplay={} level={}", gameplay ? 1 : 0, level);\n'
    '    }\n'
    '    // D-145: the title\'s Look Mode flag (D-143: 82C07D5C = 1, cross-check 82C5C770 = FF), in gameplay only.\n'
    '    const bool look = gameplay && membase[0x82C07D5Cu] == 1 && membase[0x82C5C770u] == 0xFF;\n'
    '    r3hd_mouse::PublishLevel(level);\n'
    '    if (r3hd_mouse::PublishLook(look) && r3hd_mouse::g_log.load(std::memory_order_relaxed)) {\n'
    '      REXLOG_INFO("R3HD mouse look_mode={} level={}", look ? 1 : 0, level);\n'
    '    }\n'
    '  }\n')

# D-145: xboxkrnl_video.cpp is not reset by the replay; a tree patched before D-145 carries the D-138 block without
# the Look Mode lines, which is migrated in place (the block below is that one minus the D-145 lines).
_LOOK_AT = VIDEO_BLOCK.index("    // D-145: the title's Look Mode flag")
VIDEO_BLOCK_D138 = VIDEO_BLOCK[:_LOOK_AT] + VIDEO_BLOCK[VIDEO_BLOCK.index("\n  }\n", _LOOK_AT) + 1:]


def migrate_video_block():
    path = SDK / 'src/kernel/xboxkrnl/xboxkrnl_video.cpp'
    text = path.read_text()
    if VIDEO_BLOCK not in text and VIDEO_BLOCK_D138 in text:
        assert text.count(VIDEO_BLOCK_D138) == 1
        path.write_text(text.replace(VIDEO_BLOCK_D138, VIDEO_BLOCK))
        print('migrated the D-138 VdSwap block in src/kernel/xboxkrnl/xboxkrnl_video.cpp (D-145)')


if __name__ == '__main__':
    install('r3hd_mouse.h')
    migrate_video_block()

    patch_once(HEADER, [
        ('#include <rex/ui/window_listener.h>\n', '#include <rex/ui/window_listener.h>\n#include <rex/r3hd_mouse.h>\n'),
        ('  void OnMouseMove(rex::ui::MouseEvent& e) override;\n',
         '  void OnMouseMove(rex::ui::MouseEvent& e) override;\n'
         '  // D-138 (test only): motion and buttons of the hidden-run source (tools/m32_key_test.h).\n'
         '  void TestMouseMotion(float dx, float dy);\n'
         '  void TestMouseButton(int button, bool down);\n'
         '  void TestSetGameplay(bool gameplay);  // a native test without a guest; never in a game run\n'
         '  void TestSetLook(bool look, const char* level);  // D-145: the same, for Look Mode and the level\n'),
        ('  bool relative_mouse_mode_ = false;\n',
         '  std::atomic<bool> relative_mouse_mode_{false};  // D-138: the guest poll reads it too\n'),
        ('  std::atomic<bool> has_focus_{true};\n', HEADER_MEMBERS + '  std::atomic<bool> has_focus_{true};\n'),
    ])

    patch_once(DRIVER, [
        ('\nnamespace rex::input::mnk {\n\nnamespace {\n', '\n' + CVAR + '\nnamespace rex::input::mnk {\n\nnamespace {\n'),
        ('#include <rex/m49_walk.h>\n', '#include <rex/m49_walk.h>\n#include <rex/r3hd_mouse.h>\n'),
        ('std::atomic<bool> mouse_look_active{true};\n', BUTTON_INDEX + 'std::atomic<bool> mouse_look_active{true};\n'),
        ('  return X_STATUS_SUCCESS;\n}\n\nvoid MnkInputDriver::OnWindowAvailable(',
         SETUP_LOG + '  return X_STATUS_SUCCESS;\n}\n\nvoid MnkInputDriver::OnWindowAvailable('),
        (POLL_HEAD_OLD, POLL_HEAD_NEW),
        (POLL_LOCK_OLD, POLL_LOCK_NEW),
        (CAMERA_OLD, CAMERA_NEW),
        (QUEUE_OLD, QUEUE_NEW),
        (CAPTURE_OLD, CAPTURE_NEW),
        (RELEASE_OLD, RELEASE_NEW),
        (BUTTONS_OLD, BUTTONS_NEW),
        (MOVE_OLD, MOVE_NEW),
        (RECENTER_OLD, RECENTER_NEW),
        (FOCUS_LOST_OLD, FOCUS_LOST_NEW),
        (FOCUS_GOT_OLD, FOCUS_GOT_NEW),
    ])

    patch_once('src/ui/keybinds.cpp', [
        ('    {"MMB", VirtualKey::kMButton},\n',
         '    {"MMB", VirtualKey::kMButton},\n'
         '    {"MB4", VirtualKey::kXButton1},  // D-138: side buttons\n'
         '    {"MB5", VirtualKey::kXButton2},\n'),
    ])

    patch_once('src/kernel/xboxkrnl/xboxkrnl_video.cpp', [
        ('#include <rex/graphics/register_file.h>\n',
         '#include <rex/r3hd_mouse.h>\n#include <rex/graphics/register_file.h>\n'),
        ('  assert(width);\n  assert(height);\n\n  namespace xenos = rex::graphics::xenos;\n',
         '  assert(width);\n  assert(height);\n\n' + VIDEO_BLOCK + '\n  namespace xenos = rex::graphics::xenos;\n'),
    ])
