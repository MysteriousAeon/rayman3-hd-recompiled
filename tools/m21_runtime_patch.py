"""Replay after M20 at the same pin: game-window cursor rule and the console time-zone bias (M21, D-050).

Cursor (`tools/m21_cursor.h`, `src/ui/window_sdl.cpp`): the SDK leaves the mouse cursor visible over the game
window. Now it is hidden while the window is open, focused and not minimized, shown by mouse movement for the
window's auto-hide delay, and shown on focus loss, minimize and close. Only SDL_HideCursor / SDL_ShowCursor are
used (the cursor image over the SDL window's own client area): no warp, no confinement, no capture, no global
cursor state. A hidden test window (R3HD_NONINTRUSIVE) never reaches any of this code. `R3HD_CURSOR=visible`
keeps the SDK's behaviour.

Time zone (`tools/m21_timezone.h`, `src/kernel/xboxkrnl/xboxkrnl_xconfig.cpp`): the title converts UTC to local
time itself with the console's zone, read through ExGetXConfigSetting; the SDK answers 0, so every local time
in the title is UTC. Setting 1 (bias) now carries the host's current effective bias; settings 2..7 stay 0, so
the title applies no daylight rule of its own on top. `R3HD_TIMEZONE=utc` restores the SDK's answer.

Host-only: no generated code, no guest patch, no guest memory write.
"""
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

if __name__ == '__main__':
    install('m21_cursor.h')
    install('m21_timezone.h')

    patch_once('src/ui/window_sdl.cpp', [
        ('#include <rex/ui/window_sdl.h>\n#include <cstdlib>\n',
         '#include <rex/ui/window_sdl.h>\n#include <cstdlib>\n#include <rex/m21_cursor.h>\n'),
        ("// SDL timer callback (runs on SDL's timer thread): defer the actual hide to\n",
         '// M21 (D-050): cursor rule of the game window, see rex/m21_cursor.h. One game window per process; UI\n'
         '// thread only. False for a hidden test window, which therefore never touches cursor state.\n'
         'bool M21CursorAuto() {\n'
         '  static const bool value =\n'
         '      !std::getenv("R3HD_NONINTRUSIVE") &&\n'
         '      m21cursor::ModeFromEnv(std::getenv("R3HD_CURSOR")) == m21cursor::Mode::kAuto;\n'
         '  return value;\n'
         '}\n'
         '\n'
         'm21cursor::Tracker& M21Tracker() {\n'
         '  static m21cursor::Tracker tracker;\n'
         '  return tracker;\n'
         '}\n'
         '\n'
         'void M21ApplyCursor(m21cursor::Action action, const char* reason) {\n'
         '  if (action == m21cursor::Action::kHide) {\n'
         '    SDL_HideCursor();\n'
         '  } else if (action == m21cursor::Action::kShow) {\n'
         '    SDL_ShowCursor();\n'
         '  }\n'
         '  const m21cursor::Tracker& tracker = M21Tracker();\n'
         '  if (tracker.changed()) {\n'
         '    REXLOG_INFO("M21 cursor action={} reason={} focus={} minimized={}", m21cursor::Name(action), reason,\n'
         '                tracker.state().focused, tracker.state().minimized);\n'
         '  }\n'
         '}\n'
         '\n'
         'm21cursor::Requested M21Requested(Window::CursorVisibility visibility) {\n'
         '  switch (visibility) {\n'
         '    case Window::CursorVisibility::kHidden:\n'
         '      return m21cursor::Requested::kHidden;\n'
         '    case Window::CursorVisibility::kAutoHidden:\n'
         '      return m21cursor::Requested::kAutoHidden;\n'
         '    default:\n'
         '      return m21cursor::Requested::kVisible;\n'
         '  }\n'
         '}\n'
         '\n'
         "// SDL timer callback (runs on SDL's timer thread): defer the actual hide to\n"),
        ('  window->app_context().CallInUIThreadDeferred([window] {\n'
         '    if (window->GetCursorVisibility() == Window::CursorVisibility::kAutoHidden) {\n',
         '  window->app_context().CallInUIThreadDeferred([window] {\n'
         '    if (M21CursorAuto()) {\n'
         '      // Globals only: the window may be gone by now.\n'
         '      M21ApplyCursor(M21Tracker().MouseIdle(), "mouse_idle");\n'
         '      return;\n'
         '    }\n'
         '    if (window->GetCursorVisibility() == Window::CursorVisibility::kAutoHidden) {\n'),
        ('  ApplyCursorVisibilityNow();\n'
         '  if (!std::getenv("R3HD_NONINTRUSIVE")) SDL_ShowWindow(sdl_window_);\n',
         '  ApplyCursorVisibilityNow();\n'
         '  if (M21CursorAuto()) M21ApplyCursor(M21Tracker().Opened(false, false), "open");\n'
         '  REXLOG_INFO("M21 cursor policy={}", std::getenv("R3HD_NONINTRUSIVE") ? "untouched"\n'
         '                                      : M21CursorAuto()              ? "auto"\n'
         '                                                                     : "pinned");\n'
         '  if (!std::getenv("R3HD_NONINTRUSIVE")) SDL_ShowWindow(sdl_window_);\n'),
        ('  if (SDL_GetWindowFlags(sdl_window_) & SDL_WINDOW_INPUT_FOCUS) {\n'
         '    OnFocusUpdate(true, destruction_receiver);\n',
         '  if (SDL_GetWindowFlags(sdl_window_) & SDL_WINDOW_INPUT_FOCUS) {\n'
         '    if (M21CursorAuto()) M21ApplyCursor(M21Tracker().Focus(true), "open_focused");\n'
         '    OnFocusUpdate(true, destruction_receiver);\n'),
        ('  if (sdl_window_) {\n'
         '    sdl_app_context().UnregisterWindow(sdl_window_id_);\n',
         '  if (sdl_window_) {\n'
         '    if (M21CursorAuto()) M21ApplyCursor(M21Tracker().Closed(), "close");\n'
         '    sdl_app_context().UnregisterWindow(sdl_window_id_);\n'),
        ('void WindowSDL::ApplyCursorVisibilityNow() {\n'
         '  if (std::getenv("R3HD_NONINTRUSIVE")) return;\n',
         'void WindowSDL::ApplyCursorVisibilityNow() {\n'
         '  if (std::getenv("R3HD_NONINTRUSIVE")) return;\n'
         '  if (M21CursorAuto()) {\n'
         '    // What other host code asks for (mouse capture: kHidden) is one input of the rule.\n'
         '    M21ApplyCursor(M21Tracker().Request(M21Requested(GetCursorVisibility())), "request");\n'
         '    if (M21Tracker().wants_idle_timer() && sdl_window_) RearmCursorAutoHideTimer();\n'
         '    return;\n'
         '  }\n'),
        ('    case SDL_EVENT_WINDOW_FOCUS_GAINED:\n'
         '      OnFocusUpdate(true, destruction_receiver);\n',
         '    case SDL_EVENT_WINDOW_FOCUS_GAINED:\n'
         '      if (M21CursorAuto()) M21ApplyCursor(M21Tracker().Focus(true), "focus_gained");\n'
         '      OnFocusUpdate(true, destruction_receiver);\n'),
        ('    case SDL_EVENT_WINDOW_FOCUS_LOST:\n'
         '      OnFocusUpdate(false, destruction_receiver);\n',
         '    case SDL_EVENT_WINDOW_FOCUS_LOST:\n'
         '      if (M21CursorAuto()) M21ApplyCursor(M21Tracker().Focus(false), "focus_lost");\n'
         '      OnFocusUpdate(false, destruction_receiver);\n'),
        ('    case SDL_EVENT_WINDOW_MINIMIZED:\n'
         '      OnMinimized(destruction_receiver);\n',
         '    case SDL_EVENT_WINDOW_MINIMIZED:\n'
         '      if (M21CursorAuto()) M21ApplyCursor(M21Tracker().Minimized(), "minimized");\n'
         '      OnMinimized(destruction_receiver);\n'),
        ('    case SDL_EVENT_WINDOW_RESTORED:\n'
         '      OnRestored(destruction_receiver);\n',
         '    case SDL_EVENT_WINDOW_RESTORED:\n'
         '      if (M21CursorAuto()) M21ApplyCursor(M21Tracker().Restored(), "restored");\n'
         '      OnRestored(destruction_receiver);\n'),
        ('      if (GetCursorVisibility() == CursorVisibility::kAutoHidden) {\n'
         '        SDL_ShowCursor();\n'
         '        RearmCursorAutoHideTimer();\n'
         '      }\n',
         '      if (M21CursorAuto()) {\n'
         '        // Mouse use shows the cursor again; the idle timer hides it after the auto-hide delay.\n'
         '        M21ApplyCursor(M21Tracker().MouseMoved(), "mouse_moved");\n'
         '        if (M21Tracker().wants_idle_timer()) RearmCursorAutoHideTimer();\n'
         # The SDK's own branch is unreachable for a hidden test window today; guarded all the same.
         '      } else if (!std::getenv("R3HD_NONINTRUSIVE") &&\n'
         '                 GetCursorVisibility() == CursorVisibility::kAutoHidden) {\n'
         '        SDL_ShowCursor();\n'
         '        RearmCursorAutoHideTimer();\n'
         '      }\n'),
    ])

    patch_once('src/kernel/xboxkrnl/xboxkrnl_xconfig.cpp', [
        ('#include <rex/cvar.h>\n',
         '#include <atomic>\n#include <climits>\n#include <cstdlib>\n\n'
         '#include <rex/cvar.h>\n#include <rex/m21_timezone.h>\n'),
        ('        case 0x0001:  // XCONFIG_USER_TIME_ZONE_BIAS\n'
         '        case 0x0002:  // XCONFIG_USER_TIME_ZONE_STD_NAME\n',
         '        case 0x0001: {  // XCONFIG_USER_TIME_ZONE_BIAS\n'
         "          // M21 (D-050): the host's current effective bias in minutes, see rex/m21_timezone.h. The\n"
         '          // settings below stay 0, so the title applies no daylight rule of its own on top.\n'
         '          static const m21tz::Policy m21_policy = m21tz::ParsePolicy(std::getenv("R3HD_TIMEZONE"));\n'
         '          static std::atomic<int32_t> m21_logged{INT32_MIN};\n'
         '          const m21tz::HostZone m21_zone =\n'
         '              m21_policy.kind == m21tz::Kind::kHost ? m21tz::QueryHostZone() : m21tz::HostZone{};\n'
         '          const int32_t m21_bias = m21tz::GuestBias(m21_policy, m21_zone);\n'
         '          if (m21_logged.exchange(m21_bias) != m21_bias) {\n'
         '            REXKRNL_INFO("M21 timezone policy={} bias_min={} host_ok={} host_id={} recognised={}",\n'
         '                         m21_policy.kind == m21tz::Kind::kUtc     ? "utc"\n'
         '                         : m21_policy.kind == m21tz::Kind::kFixed ? "fixed"\n'
         '                                                                  : "host",\n'
         '                         m21_bias, m21_zone.ok, m21_zone.id, m21_policy.recognised);\n'
         '          }\n'
         '          setting_size = 4;\n'
         '          memory::store_and_swap<uint32_t>(value, uint32_t(m21_bias));\n'
         '          break;\n'
         '        }\n'
         '        case 0x0002:  // XCONFIG_USER_TIME_ZONE_STD_NAME\n'),
    ])
