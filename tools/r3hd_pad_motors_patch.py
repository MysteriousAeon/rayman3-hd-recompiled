"""Replay after r3hd_lockon_runtime_patch.py at the same pin (last in the chain): controller motors are stopped when the
game closes (G6-P75, D-324). Idempotent.

Installed headers: r3hd_pad_motors.h (SDL-free policy), r3hd_pad_motors_sdl.h (its one SDL call, behind M23).
  * include/rex/input/input_driver.h, input_system.h, src/input/input_system.cpp: InputSystem::OnHostClosing() tells
    every driver that the game is closing (default: nothing).
  * src/ui/rex_app.cpp: ReXApp::OnClosing calls it before TerminateTitle and the hard exit. A window close reaches
    OnClosing whether or not the window had the focus; the SDL driver's own OnClosing never runs (the app is the
    window's first listener and exits), so SDL_CloseGamepad, the only place SDL cancels a rumble, was never reached.
  * src/input/sdl/sdl_input_driver.*: each pad remembers whether its last vibration request may have left a motor
    running; at OnHostClosing and at the title-exit detach (OnWindowAvailable(nullptr), D-034 / D-105) every such pad
    gets one zero request and later requests of the title are answered without a device call.
Nothing here changes vibration during play, focus or pause handling, mappings, prompts or any guest state.
"""
import sys

from m8_runtime_patch import SDK, patch_once
from m16_runtime_patch import install

TAG = 'G6-P75 (D-324)'

ON_HOST_CLOSING_DECL = (
    '  virtual void OnWindowAvailable(rex::ui::Window* /*window*/) {}\n'
    '\n'
    f'  // {TAG}: the game is closing (window close or title exit); a driver stops what it drives. Default: nothing.\n'
    '  virtual void OnHostClosing() {}\n')

SYSTEM_DECL = (
    '  void SetActiveCallback(std::function<bool()> callback);\n'
    f'  /// {TAG}: the game is closing; every driver stops its outputs.\n'
    '  void OnHostClosing();\n')

SYSTEM_IMPL = (
    f'// {TAG}: called by ReXApp::OnClosing before the hard exit (no driver teardown follows it).\n'
    'void InputSystem::OnHostClosing() {\n'
    '  for (auto& driver : drivers_) {\n'
    '    driver->OnHostClosing();\n'
    '  }\n'
    '}\n'
    '\n'
    'void InputSystem::SetDeviceAssignment(')

APP_CLOSING = (
    '  shutting_down_.store(true, std::memory_order_release);\n'
    f'  // {TAG}: stop the controllers\' motors first; nothing after this point closes the pads.\n'
    '  if (runtime_ && runtime_->input_system()) {\n'
    '    static_cast<rex::input::InputSystem*>(runtime_->input_system())->OnHostClosing();\n'
    '  }\n'
    '  if (runtime_ && runtime_->kernel_state()) {\n'
    '    runtime_->kernel_state()->TerminateTitle();\n')

SDL_INCLUDE = '#include <rex/m23_haptics.h>\n' f'#include <rex/r3hd_pad_motors_sdl.h>  // {TAG}\n'

# At the end of OnWindowAvailable: the D-102 title-exit block at its start is that patch's own idempotence text
# (the driver file is not reset by the replay), so nothing is inserted inside it.
SDL_WINDOW_END = (
    '      REXLOG_INFO("SDL input driver initialized successfully");\n'
    '    });\n'
    '  }\n'
    '}\n')
SDL_TITLE_EXIT = (
    SDL_WINDOW_END[:-2] +
    f'  if (!window && SDL_Gamepad_initialized_) {{  // {TAG}: title exit (after the D-105 release above)\n'
    '    auto guard = DrainAndLock();\n'
    '    CloseMotorsLocked("title_exit");\n'
    '  }\n'
    '}\n')

SDL_CLOSE_IMPL = (
    f'// {TAG}: the game is closing. Under the controllers lock: one zero request to every pad that may be vibrating,\n'
    '// then no request of the title reaches a device again.\n'
    'void SDLInputDriver::CloseMotorsLocked(const char* reason) {\n'
    '  const bool first = !motor_outputs_.closed();\n'
    '  const int stopped = r3hd_motors::CloseSdl(motor_outputs_, controllers_);\n'
    '  if (first) REXLOG_INFO("R3HD pad motors closed reason={} stopped={}", reason, stopped);\n'
    '}\n'
    '\n'
    'void SDLInputDriver::OnHostClosing() {\n'
    '  if (!SDL_Gamepad_initialized_) return;\n'
    '  auto guard = DrainAndLock();\n'
    '  CloseMotorsLocked("close");\n'
    '}\n'
    '\n'
    'void SDLInputDriver::OnLostFocus(rex::ui::UISetupEvent&) {\n')

SDL_VIBRATION_BEFORE = (
    '  // XInput vibration holds until the guest changes it, but SDL rumble expires,\n'
    '  // and a zero duration expires on the next SDL_UpdateJoysticks. Arm it for\n'
    '  // SDL\'s maximum instead; each call cancels the previous effect anyway.\n'
    '  return SDL_RumbleGamepad(controller->sdl, vibration->left_motor_speed,\n'
    '                           vibration->right_motor_speed, kRumbleDurationMs)\n'
    '             ? X_ERROR_SUCCESS\n'
    '             : X_ERROR_FUNCTION_FAILED;\n')
SDL_VIBRATION_AFTER = (
    f'  if (motor_outputs_.closed()) {{  // {TAG}: the game is closing; the pads were stopped\n'
    '    return X_ERROR_SUCCESS;\n'
    '  }\n'
    '\n'
    '  // XInput vibration holds until the guest changes it, but SDL rumble expires,\n'
    '  // and a zero duration expires on the next SDL_UpdateJoysticks. Arm it for\n'
    '  // SDL\'s maximum instead; each call cancels the previous effect anyway.\n'
    '  const bool sent = SDL_RumbleGamepad(controller->sdl, vibration->left_motor_speed,\n'
    '                                     vibration->right_motor_speed, kRumbleDurationMs);\n'
    '  r3hd_motors::Requested(controller->motors, vibration->left_motor_speed, vibration->right_motor_speed,\n'
    f'                         sent);  // {TAG}\n'
    '  return sent ? X_ERROR_SUCCESS : X_ERROR_FUNCTION_FAILED;\n')

SDL_HEADER = [
    ('#include <rex/r3hd_hostui_gate.h>\n',
     '#include <rex/r3hd_hostui_gate.h>\n' f'#include <rex/r3hd_pad_motors.h>  // {TAG}\n'),
    ('  void OnWindowAvailable(rex::ui::Window* window) override;\n',
     '  void OnWindowAvailable(rex::ui::Window* window) override;\n'
     f'  void OnHostClosing() override;  // {TAG}\n'),
    ('    r3hd_hostui::PadGate host_gate;  // D-139\n',
     '    r3hd_hostui::PadGate host_gate;  // D-139\n'
     f'    r3hd_motors::Motors motors;  // {TAG}\n'),
    ('  void QueueControllerUpdate();\n',
     '  void QueueControllerUpdate();\n'
     f'  void CloseMotorsLocked(const char* reason);  // {TAG}\n'),
    ('  uint64_t next_device_id_ = 1;\n',
     '  uint64_t next_device_id_ = 1;\n'
     f'  r3hd_motors::Outputs motor_outputs_;  // {TAG}; under controllers_mutex_\n'),
]

EDITS = {
    'include/rex/input/input_driver.h': [
        ('  virtual void OnWindowAvailable(rex::ui::Window* /*window*/) {}\n', ON_HOST_CLOSING_DECL)],
    'include/rex/input/input_system.h': [
        ('  void SetActiveCallback(std::function<bool()> callback);\n', SYSTEM_DECL)],
    'src/input/input_system.cpp': [('void InputSystem::SetDeviceAssignment(', SYSTEM_IMPL)],
    'src/ui/rex_app.cpp': [
        ('  shutting_down_.store(true, std::memory_order_release);\n'
         '  if (runtime_ && runtime_->kernel_state()) {\n'
         '    runtime_->kernel_state()->TerminateTitle();\n', APP_CLOSING)],
    'include/rex/input/sdl/sdl_input_driver.h': SDL_HEADER,
    'src/input/sdl/sdl_input_driver.cpp': [
        ('#include <rex/m23_haptics.h>\n', SDL_INCLUDE),
        (SDL_WINDOW_END, SDL_TITLE_EXIT),
        ('void SDLInputDriver::OnLostFocus(rex::ui::UISetupEvent&) {\n', SDL_CLOSE_IMPL),
        (SDL_VIBRATION_BEFORE, SDL_VIBRATION_AFTER),
    ],
}

# The first G6-P75 build placed this line inside the D-102 title-exit block, which is r3hd_dualsense_patch.py's own
# idempotence text; the driver file is not reset by the replay. `migrate` (run in the chain just before that patch)
# takes it back. Idempotent: on any other tree it changes nothing.
SUPERSEDED_TITLE_EXIT = '    r3hd_ds::ReleaseAll(controllers_, "title_exit");\n' f'    CloseMotorsLocked("title_exit");  // {TAG}\n'


def migrate():
    path = SDK / 'src/input/sdl/sdl_input_driver.cpp'
    text = path.read_text()
    if SUPERSEDED_TITLE_EXIT in text:
        assert text.count(SUPERSEDED_TITLE_EXIT) == 1
        path.write_text(text.replace(SUPERSEDED_TITLE_EXIT, '    r3hd_ds::ReleaseAll(controllers_, "title_exit");\n'))
        print('migrated src/input/sdl/sdl_input_driver.cpp')


if __name__ == '__main__':
    if sys.argv[1:] == ['migrate']:
        migrate()
        sys.exit(0)
    install('r3hd_pad_motors.h')
    install('r3hd_pad_motors_sdl.h')
    for rel, edits in EDITS.items():
        patch_once(rel, edits)
