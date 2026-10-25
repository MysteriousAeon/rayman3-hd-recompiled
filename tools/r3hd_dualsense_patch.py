"""Replay after the M50 patch at the same pin (last in the chain): DualSense light bar / R2 resistance (D-102) and
the optional achievement display text with the overlay's Turkish glyphs (D-101). Idempotent.

Installed headers: r3hd_dualsense.h (policy), r3hd_ds_state.h (guest facts, read-only), r3hd_ds_sdl.h (SDL glue),
r3hd_achtext.h (display text).
  * src/kernel/xboxkrnl/xboxkrnl_video.cpp: VdSwap publishes world / gameplay and, with the light bar on, the active
    power-up (D-104), only while a DualSense option is on; it logs one `R3HD dualsense light=.. trigger=.. policy=..`
    line, then one `R3HD dualsense state world=.. gameplay=.. power=.. code=.. step=..` line per change.
  * src/input/sdl/sdl_input_driver.*: per-pad policy; a step at every title poll of that pad; the idle colour of a
    renumbered pad; everything is released at focus loss (also the close path: the window sends focus loss before
    OnClosing, whose first listener hard-exits) and at OnClosing, by reports the device acts on (D-105: an LED write
    of SDL's player colour, a trigger clear) followed by one bounded wait. The window's own focus (OnGotFocus /
    OnLostFocus) gates output; is_active() only means "no overlay captures input". A title-initiated exit sends
    neither focus loss nor OnClosing: the release then runs at the drivers' detach (OnWindowAvailable(nullptr)).
    Hidden runs: M23 gate.
  * src/ui/overlay/achievements_overlay.cpp, achievement_toast.cpp: label / description / unachieved text through
    r3hd_achtext (English unless R3HD_ACH_TEXT names an entry made from this exact English).
  * src/ui/imgui_drawer.cpp: U+0100..U+017F merged from a Windows system font (ProggyTiny has U+0020..U+00FF only).
Nothing here changes guest memory, achievement ids, unlocks, the store or the title's enumerator.
"""
from m8_runtime_patch import SDK, patch_once
from m16_runtime_patch import install

VIDEO = 'src/kernel/xboxkrnl/xboxkrnl_video.cpp'
M44_LINE = '  // M44 (D-081): optional gameplay voice subtitles, off unless R3HD_GAMEPLAY_SUBTITLES=all.\n'
# The VdSwap block as the D-102 build installed it. The video file is not reset to the pin by the M2 replay, so a tree
# patched before D-104 still holds it: it is replaced by DS_BLOCK instead of getting a second block.
DS_BLOCK_D102 = (
    '  // D-102: DualSense guest facts (read-only), only while a DualSense option is on.\n'
    '  {\n'
    '    static const bool ds_on = [] {\n'
    '      const auto s = r3hd_ds::state::Configured();\n'
    '      REXLOG_INFO("R3HD dualsense light={} trigger={} policy={}", s.light ? "on" : "off",\n'
    '                  s.trigger ? "on" : "off", std::getenv("R3HD_NONINTRUSIVE") ? "suppressed" : "enabled");\n'
    '      return s.light || s.trigger;\n'
    '    }();\n'
    '    if (ds_on && r3hd_ds::state::Swap(REX_KERNEL_MEMORY()->virtual_membase())) {\n'
    '      const auto g = r3hd_ds::state::Read();\n'
    '      REXLOG_INFO("R3HD dualsense state world={} gameplay={}", g.world, g.gameplay ? 1 : 0);\n'
    '    }\n'
    '  }\n')
# D-104: with the light bar on, the active power-up as well (the global actor, read only through committed pages of
# the title's 64 KiB-page heap).
DS_BLOCK = (
    '  // D-102 / D-104: DualSense guest facts (read-only), only while a DualSense option is on.\n'
    '  {\n'
    '    static const bool ds_on = [] {\n'
    '      const auto s = r3hd_ds::state::Configured();\n'
    '      REXLOG_INFO("R3HD dualsense light={} trigger={} policy={}", s.light ? "on" : "off",\n'
    '                  s.trigger ? "on" : "off", std::getenv("R3HD_NONINTRUSIVE") ? "suppressed" : "enabled");\n'
    '      return s.light || s.trigger;\n'
    '    }();\n'
    '    if (ds_on) {\n'
    '      auto* memory = REX_KERNEL_MEMORY();\n'
    '      const auto readable = [memory](uint32_t address, uint32_t size) {\n'
    '        if (address < 0x40000000u || address > 0x7F000000u - size) return false;\n'
    '        auto* heap = memory->LookupHeap(address);\n'
    '        return heap && heap->QueryRangeAccess(address, address + size - 1) != rex::memory::PageAccess::kNoAccess;\n'
    '      };\n'
    '      if (r3hd_ds::state::Swap(memory->virtual_membase(), r3hd_ds::state::Configured().light, readable)) {\n'
    '        const auto g = r3hd_ds::state::Read();\n'
    '        REXLOG_INFO("R3HD dualsense state world={} gameplay={} power={} code={} step={}", g.world,\n'
    '                    g.gameplay ? 1 : 0, r3hd_ds::state::PowerName(g.power), g.power_code, g.power_step);\n'
    '      }\n'
    '    }\n'
    '  }\n')


def migrate_video_block():
    path = SDK / VIDEO
    text = path.read_text()
    if DS_BLOCK_D102 in text:
        assert text.count(DS_BLOCK_D102) == 1 and DS_BLOCK not in text, VIDEO
        path.write_text(text.replace(DS_BLOCK_D102, DS_BLOCK))
        print('migrated the D-102 block in', VIDEO)


DRIVER = 'src/input/sdl/sdl_input_driver.cpp'
# D-105 driver lines: real window focus, the light bar given back by an LED write of the idle colour, one bounded wait
# before a closing exit, the idle colour of a renumbered pad, and R2 no longer an input of the policy.
FOCUS_INIT = '    r3hd_ds::WindowFocus().store(window->HasFocus());  // D-105\n'
LOST_FOCUS = (
    'void SDLInputDriver::OnLostFocus(rex::ui::UISetupEvent&) {\n'
    '  // D-102 / D-105: give the pad back (light bar, R2) when the window loses focus; the close path sends this too.\n'
    '  r3hd_ds::WindowFocus().store(false);  // before the lock, so no later step lights the pad again\n'
    '  if (!SDL_Gamepad_initialized_) return;\n'
    '  auto guard = DrainAndLock();\n'
    '  r3hd_ds::ReleaseAll(controllers_, "focus");  // LED write of the idle colour, trigger clear, bounded wait\n'
    '}\n')
GOT_FOCUS = (
    'void SDLInputDriver::OnGotFocus(rex::ui::UISetupEvent&) {\n'
    '  r3hd_ds::WindowFocus().store(true);  // D-105: the next title poll lights the pad again\n'
    '}\n')
CLOSE_RELEASE = '    r3hd_ds::ReleaseAll(controllers_, "close");  // D-102 / D-105\n'
# A title-initiated exit (the title's own quit) destroys the window without OnBeforeClose: no focus loss, no OnClosing.
# ReXApp::OnDestroy detaches the input drivers first (M11, D-034); that is the last call this driver gets.
TITLE_EXIT = (
    '  if (!window && SDL_Gamepad_initialized_) {  // D-105: title exit, no focus loss or OnClosing follows\n'
    '    auto guard = DrainAndLock();\n'
    '    r3hd_ds::ReleaseAll(controllers_, "title_exit");\n'
    '  }\n')
STEP = (
    '  // D-102: DualSense light bar / R2 resistance for the pad the title just read (nothing for other pads).\n'
    '  r3hd_ds::Step(*controller, controllers_, static_cast<int>(controller - controllers_.data()), is_active);\n')
RENUMBERED = '    r3hd_ds::Renumbered(controllers_[i], static_cast<int>(i));  // D-105: SDL repeated its last LED colour\n'
# The same places as the D-102 build left them (the driver is not reset to the pin by the M2 replay either).
DRIVER_D102 = [
    ('void SDLInputDriver::OnLostFocus(rex::ui::UISetupEvent&) {\n'
     '  // D-102: give the pad back (light bar, R2) when the window loses focus; the close path sends this too.\n'
     '  if (!SDL_Gamepad_initialized_) return;\n'
     '  auto guard = DrainAndLock();\n'
     '  bool sent = false;\n'
     '  for (size_t i = 0; i < controllers_.size(); ++i) {\n'
     '    sent |= controllers_[i].ds.policy.LightCustom() || controllers_[i].ds.policy.TriggerOn();\n'
     '    r3hd_ds::Release(controllers_[i], static_cast<int>(i));\n'
     '  }\n'
     '  if (sent) SDL_Delay(30);  // SDL writes HID output on its own thread; let it go out before a closing exit\n'
     '}\n', LOST_FOCUS),
    ('    for (size_t i = 0; i < controllers_.size(); ++i) {\n'
     '      r3hd_ds::Release(controllers_[i], static_cast<int>(i));  // D-102\n'
     '    }\n', CLOSE_RELEASE),
    ('  // D-102: DualSense light bar / R2 resistance for the pad the title just read (nothing for other pads).\n'
     '  r3hd_ds::Step(*controller, controllers_, static_cast<int>(controller - controllers_.data()), is_active,\n'
     '                controller->state.gamepad.right_trigger);\n', STEP),
    ('    controllers_[i].ds.policy.LightReset();  // D-102: SDL put the player colour back\n', RENUMBERED),
]


def migrate_driver():
    path = SDK / DRIVER
    text = path.read_text()
    changed = False
    for old, new in DRIVER_D102:
        if old in text:
            assert text.count(old) == 1 and new not in text, (DRIVER, old[:60])
            text = text.replace(old, new)
            changed = True
    if changed:
        path.write_text(text)
        print('migrated the D-102 lines in', DRIVER)


if __name__ == '__main__':
    for name in ('r3hd_dualsense.h', 'r3hd_ds_state.h', 'r3hd_ds_sdl.h', 'r3hd_achtext.h'):
        install(name)

    migrate_video_block()
    patch_once(VIDEO, [
        ('#include <rex/cvar.h>\n', '#include <rex/r3hd_ds_state.h>\n#include <rex/cvar.h>\n'),
        (M44_LINE, DS_BLOCK + M44_LINE),
    ])

    patch_once('include/rex/input/sdl/sdl_input_driver.h', [
        ('#include <rex/input/input_driver.h>\n', '#include <rex/input/input_driver.h>\n#include <rex/r3hd_ds_sdl.h>\n'),
        ('    // Per pad rather than per guest user, so it survives reassignment.\n    KeystrokeState keystroke;\n',
         '    // Per pad rather than per guest user, so it survives reassignment.\n    KeystrokeState keystroke;\n'
         '    r3hd_ds::PadOutput ds;  // D-102\n'),
    ])

    migrate_driver()
    patch_once(DRIVER, [
        ('void SDLInputDriver::OnWindowAvailable(rex::ui::Window* window) {\n  if (window && !attached_window_) {\n',
         'void SDLInputDriver::OnWindowAvailable(rex::ui::Window* window) {\n' + TITLE_EXIT +
         '  if (window && !attached_window_) {\n'),
        ('    attached_window_ = window;\n    window->AddListener(this);\n',
         '    attached_window_ = window;\n    window->AddListener(this);\n' + FOCUS_INIT),
        ('void SDLInputDriver::OnLostFocus(rex::ui::UISetupEvent&) {}\n', LOST_FOCUS),
        ('void SDLInputDriver::OnGotFocus(rex::ui::UISetupEvent&) {}\n', GOT_FOCUS),
        ('    for (auto& controller : controllers_) {\n      SDL_CloseGamepad(controller.sdl);\n    }\n    controllers_.clear();\n',
         CLOSE_RELEASE +
         '    for (auto& controller : controllers_) {\n      SDL_CloseGamepad(controller.sdl);\n    }\n    controllers_.clear();\n'),
        ('  std::memcpy(out_state, &controller->state, sizeof(*out_state));\n  if (!is_active) {\n',
         '  std::memcpy(out_state, &controller->state, sizeof(*out_state));\n' + STEP + '  if (!is_active) {\n'),
        ('  const int ordinal = static_cast<int>(controllers_.size()) - 1;\n  SDL_SetGamepadPlayerIndex(controller, ordinal);\n',
         '  const int ordinal = static_cast<int>(controllers_.size()) - 1;\n  SDL_SetGamepadPlayerIndex(controller, ordinal);\n'
         '  // D-102: only a DualSense can get light bar / trigger output.\n'
         '  controllers_.back().ds.dualsense = r3hd_ds::IsDualSense(controller);\n'
         '  controllers_.back().ds.bluetooth = r3hd_ds::IsBluetooth(controller);\n'
         '  if (controllers_.back().ds.dualsense) {\n'
         '    REXLOG_INFO("R3HD dualsense pad=dualsense transport={}",\n'
         '                controllers_.back().ds.bluetooth ? "bluetooth" : "usb");\n'
         '  }\n'),
        ('    SDL_SetGamepadPlayerIndex(controllers_[i].sdl, static_cast<int>(i));\n  }\n',
         '    SDL_SetGamepadPlayerIndex(controllers_[i].sdl, static_cast<int>(i));\n' + RENUMBERED + '  }\n'),
    ])

    patch_once('src/ui/overlay/achievements_overlay.cpp', [
        ('#include <rex/runtime.h>\n', '#include <rex/r3hd_achtext.h>\n#include <rex/runtime.h>\n'),
        ('      const std::string& desc = is_unlocked ? a.description : a.unachieved_description;\n',
         '      // D-101: optional display text (English unless a mod entry was made from this exact English).\n'
         '      const auto& ach_text = r3hd_achtext::Get([](const char* s) { REXLOG_INFO("{}", s); });\n'
         '      const std::string& desc =\n'
         '          is_unlocked ? ach_text.Display(a.id, r3hd_achtext::kDescription, a.description, a.description)\n'
         '                      : ach_text.Display(a.id, r3hd_achtext::kUnachieved, a.unachieved_description,\n'
         '                                         a.description);\n'
         '      const std::string& label = ach_text.Display(a.id, r3hd_achtext::kLabel, a.label, a.description);\n'),
        ('      ImGui::TextColored(title_color, "%s", a.label.c_str());\n',
         '      ImGui::TextColored(title_color, "%s", label.c_str());\n'),
        ('    ImGui::BeginChild("##achlist", ImVec2(0.0f, 0.0f), false);\n',
         '    ImGui::BeginChild("##achlist", ImVec2(0.0f, 0.0f), false);\n'
         '    {  // D-101: one line per change of what the list shows (hidden checks cannot capture host overlays)\n'
         '      static int logged = -1;\n'
         '      const auto& t = r3hd_achtext::Get([](const char* s) { REXLOG_INFO("{}", s); });\n'
         '      const int glyph = ImGui::GetFont()->IsGlyphInFont(0x011F);\n'
         '      const int key = (static_cast<int>(t.size()) * 1000 + static_cast<int>(t.stale())) * 2 + glyph;\n'
         '      if (key != logged) {\n'
         '        logged = key;\n'
         '        REXLOG_INFO("R3HD achievement_text overlay entries={} stale={} glyph_011F={}", t.size(), t.stale(), glyph);\n'
         '      }\n'
         '    }\n'),
    ])

    patch_once('src/ui/overlay/achievement_toast.cpp', [
        ('#include <rex/ui/immediate_drawer.h>\n',
         '#include <rex/logging.h>\n#include <rex/r3hd_achtext.h>\n#include <rex/ui/immediate_drawer.h>\n'),
        ('    ImGui::TextUnformatted(toast.event.achievement.label.c_str());\n',
         '    // D-101: optional display text; the unlock itself is unchanged.\n'
         '    ImGui::TextUnformatted(r3hd_achtext::Get([](const char* s) { REXLOG_INFO("{}", s); })\n'
         '                               .Display(toast.event.achievement.id, r3hd_achtext::kLabel,\n'
         '                                        toast.event.achievement.label, toast.event.achievement.description)\n'
         '                               .c_str());\n'),
    ])

    patch_once('src/ui/imgui_drawer.cpp', [
        ('#include <cstring>\n', '#include <cstdlib>\n#include <cstring>\n'),
        ('  if (font_setup_) {\n    font_setup_(io.Fonts);\n  }\n',
         '#if REX_PLATFORM_WIN32\n'
         '  // D-101: Latin Extended-A (Turkish g-breve, dotless i, dotted I, s-cedilla ...) for host overlay text, merged\n'
         '  // from a Windows system font; ProggyTiny covers U+0020..U+00FF only.\n'
         '  {\n'
         '    static const ImWchar latin_ext_a[] = {0x0100, 0x017F, 0};\n'
         '    const char* windir = std::getenv("WINDIR");\n'
         '    const char* chosen = nullptr;\n'
         '    std::string path;\n'
         '    for (const char* name : {"tahoma.ttf", "segoeui.ttf", "arial.ttf"}) {\n'
         '      path = std::string(windir ? windir : "C:\\\\Windows") + "\\\\Fonts\\\\" + name;\n'
         '      if (std::filesystem::exists(path)) {\n'
         '        chosen = name;\n'
         '        break;\n'
         '      }\n'
         '    }\n'
         '    if (chosen) {\n'
         '      ImFontConfig ext_config;\n'
         '      ext_config.MergeMode = true;\n'
         '      ext_config.OversampleH = ext_config.OversampleV = 1;\n'
         '      ext_config.PixelSnapH = true;\n'
         '      io.Fonts->AddFontFromFileTTF(path.c_str(), 11.0f, &ext_config, latin_ext_a);\n'
         '    }\n'
         '    REXLOG_INFO("R3HD overlay_font latin_ext_a={}", chosen ? chosen : "none");\n'
         '  }\n'
         '#endif\n'
         '\n'
         '  if (font_setup_) {\n    font_setup_(io.Fonts);\n  }\n'),
    ])
