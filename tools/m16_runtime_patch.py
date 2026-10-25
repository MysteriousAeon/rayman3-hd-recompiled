"""Replay after M15 at the same pin: vblank delivery (M16, D-043) and the achievements entry (M16, D-044).

1. Vblank delivery. The pinned worker raises the guest vblank interrupt from a loop around a 1 ms sleep, so each
   interrupt is up to one host sleep quantum late, independently per frame; the title paces its frames on that
   interrupt. `tools/m16_vblank.h` replaces the sleep by a wait for the next deadline (high-resolution timer,
   then a short processor yield) and logs the lateness of every 600 vblanks (`M16 vblank`). The schedule, the
   interrupt and all guest-visible state are unchanged. Default since M17 (D-046); `R3HD_VBLANK=poll` selects the
   pinned sleeps.
   The command processor's WAIT_REG_MEM poll (one wait per frame, polled around 1 ms sleeps) waits the same
   time at most but returns when a vblank has been delivered (`M16 cp_wait`).

2. Achievements entry. `XamShowAchievementsUI` was an export stub, so the title's Achievements menu entry did
   nothing. It now shows the runtime's existing local achievements overlay (the F7 one: titles and descriptions
   from the title's own XDBF, unlock state from the profile's achievements file) as a stand-in for the console's
   system UI: XN_SYS_UI is broadcast around it and the title is given a neutral pad while it is open
   (`tools/m16_sysui.h`). No Xbox Live, no entitlement, no record is created or signed; an achievement is
   unlocked only by the title's own XGIUserWriteAchievements call, exactly as before.

Host-only: no guest memory writes beyond the pad state the input call fills anyway, no generated code change.
"""
import shutil

from m3_runtime_patch import ROOT, SDK
from m8_runtime_patch import patch_once


def install(name):
    source = ROOT / 'tools' / name
    target = SDK / 'include/rex' / name
    if not target.exists() or target.read_bytes() != source.read_bytes():
        shutil.copyfile(source, target)
        print('installed', target.name)


if __name__ == '__main__':
    # tools/m11_frame_pacing.h gained core_sd_us / lag1_milli in M16; m11_runtime_patch.py installs it.
    install('m16_vblank.h')
    install('m16_sysui.h')

    patch_once('src/graphics/graphics_system.cpp', [
        ('          while (current_time - last_frame_time >= interval_ticks) {\n'
         '            MarkVblank();\n'
         '            last_frame_time += interval_ticks;\n'
         '          }\n'
         '          rex::thread::Sleep(std::chrono::milliseconds(1));\n',
         '          while (current_time - last_frame_time >= interval_ticks) {\n'
         '            // M16 (D-043): lateness of this vblank against its schedule.\n'
         '            m16vb::Late(current_time - last_frame_time - interval_ticks, guest_tick_frequency);\n'
         '            MarkVblank();\n'
         '            m16vb::SignalVblank();  // M16 (D-043): release a command-processor register wait\n'
         '            last_frame_time += interval_ticks;\n'
         '          }\n'
         '          if (m16vb::Precise() && REXCVAR_GET(vsync)) {\n'
         '            // M16 (D-043): wake at the next deadline instead of polling every millisecond.\n'
         '            m16vb::WaitForDeadline(last_frame_time + interval_ticks, guest_tick_frequency,\n'
         '                                   [] { return chrono::Clock::QueryGuestTickCount(); });\n'
         '          } else {\n'
         '            rex::thread::Sleep(std::chrono::milliseconds(1));\n'
         '          }\n'),
    ])
    path = SDK / 'src/graphics/graphics_system.cpp'
    text = path.read_text()
    if '#include <rex/m16_vblank.h>' not in text:
        anchor = '#include <rex/graphics/graphics_system.h>\n'
        assert text.count(anchor) == 1, 'graphics_system.cpp include anchor'
        path.write_text(text.replace(anchor, anchor + '#include <rex/m16_vblank.h>\n'))
        print('patched include src/graphics/graphics_system.cpp')

    patch_once('src/graphics/command_processor.cpp', [
        ('          rex::thread::Sleep(std::chrono::milliseconds(wait / 0x100));\n',
         '          // M16 (D-043): same wait, ended early by a delivered vblank.\n'
         '          if (!m16vb::RegisterWait(wait, is_memory, poll_reg_addr)) {\n'
         '            rex::thread::Sleep(std::chrono::milliseconds(wait / 0x100));\n'
         '          }\n'),
    ])
    path = SDK / 'src/graphics/command_processor.cpp'
    text = path.read_text()
    if '#include <rex/m16_vblank.h>' not in text:
        anchor = '#include <rex/graphics/command_processor.h>\n'
        assert text.count(anchor) == 1, 'command_processor.cpp include anchor'
        path.write_text(text.replace(anchor, anchor + '#include <rex/m16_vblank.h>\n'))
        print('patched include src/graphics/command_processor.cpp')

    patch_once('src/kernel/xam/xam_input.cpp', [
        ('#include <rex/m6_test_input.h>\n',
         '#include <rex/m6_test_input.h>\n#include <rex/m16_sysui.h>\n'),
        ('    auto s = m6input::Sample(bool(input_state));\n'
         '    if (input_state) {\n',
         '    auto s = m6input::Sample(bool(input_state));\n'
         '    if (m16sysui::Filter(s.buttons)) {\n'
         '      // M16 (D-044): a host dialog standing in for a system UI owns the pad.\n'
         '      s.buttons = 0;\n'
         '      s.lx = s.ly = s.rx = s.ry = 0;\n'
         '      s.lt = s.rt = 0;\n'
         '    }\n'
         '    if (input_state) {\n'),
        ('  return is->GetState(actual_user_index, input_state);\n'
         '}\n',
         '  auto m16_result = is->GetState(actual_user_index, input_state);\n'
         '  if (m16_result == X_ERROR_SUCCESS && input_state &&\n'
         '      m16sysui::Filter(uint16_t(input_state->gamepad.buttons))) {\n'
         '    // M16 (D-044): a host dialog standing in for a system UI owns the pad.\n'
         '    input_state->gamepad = {};\n'
         '  }\n'
         '  return m16_result;\n'
         '}\n'),
        ('  if (m6input::Enabled()) return actual_user_index == 0 ? X_ERROR_EMPTY : X_ERROR_DEVICE_NOT_CONNECTED;\n'
         '  return is->GetKeystroke(actual_user_index, flags, keystroke);\n',
         '  if (m6input::Enabled()) return actual_user_index == 0 ? X_ERROR_EMPTY : X_ERROR_DEVICE_NOT_CONNECTED;\n'
         '  if (m16sysui::IsOpen()) return X_ERROR_EMPTY;  // M16 (D-044)\n'
         '  return is->GetKeystroke(actual_user_index, flags, keystroke);\n'),
        ('  if (m6input::Enabled()) return user_index == 0 ? X_ERROR_EMPTY : X_ERROR_DEVICE_NOT_CONNECTED;\n'
         '  auto result = is->GetKeystroke(user_index, flags, keystroke);\n',
         '  if (m6input::Enabled()) return user_index == 0 ? X_ERROR_EMPTY : X_ERROR_DEVICE_NOT_CONNECTED;\n'
         '  if (m16sysui::IsOpen()) return X_ERROR_EMPTY;  // M16 (D-044)\n'
         '  auto result = is->GetKeystroke(user_index, flags, keystroke);\n'),
    ])

    patch_once('src/kernel/xam/xam_ui.cpp', [
        ('#include <rex/ui/imgui_dialog.h>\n',
         '#include <rex/ui/imgui_dialog.h>\n'
         '#include <rex/m16_sysui.h>\n'
         '#include <rex/system/achievement_manager.h>\n'
         '#include <rex/ui/overlay/achievements_overlay.h>\n'),
        ('u32 XamShowPartyUI_entry(u32 r3, u32 r4) {\n',
         '// M16 (D-044): the title\'s Achievements menu entry. The console shows its system achievements list; here\n'
         '// the runtime\'s local achievements overlay is shown in its place. The call returns at once, as on the\n'
         '// console; XN_SYS_UI brackets the dialog and the input gate keeps the pad away from the title meanwhile.\n'
         'class M16AchievementsDialog : public rex::ui::AchievementsOverlayDialog {\n'
         ' public:\n'
         '  M16AchievementsDialog(rex::ui::ImGuiDrawer* imgui_drawer, rex::Runtime* runtime,\n'
         '                        rex::system::KernelState* kernel_state)\n'
         '      : rex::ui::AchievementsOverlayDialog(imgui_drawer, nullptr, runtime,\n'
         '                                           &kernel_state->achievements()),\n'
         '        kernel_state_(kernel_state) {}\n'
         '  void RequestClose() { Close(); }\n'
         '  static M16AchievementsDialog* current;  // UI thread only\n'
         '\n'
         ' protected:\n'
         '  void OnDraw(ImGuiIO& io) override {\n'
         '    rex::ui::AchievementsOverlayDialog::OnDraw(io);\n'
         '    ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y - 24.0f),\n'
         '                            ImGuiCond_Always, ImVec2(0.5f, 1.0f));\n'
         '    ImGui::SetNextWindowBgAlpha(0.92f);\n'
         '    if (ImGui::Begin("##m16_achievements_hint", nullptr,\n'
         '                     ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize |\n'
         '                         ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoSavedSettings |\n'
         '                         ImGuiWindowFlags_NoFocusOnAppearing)) {\n'
         '      ImGui::TextUnformatted("B / Esc: return to the game");\n'
         '      ImGui::SameLine();\n'
         '      if (ImGui::SmallButton("Close")) {\n'
         '        Close();\n'
         '      }\n'
         '    }\n'
         '    ImGui::End();\n'
         '  }\n'
         '  void OnClose() override {\n'
         '    {\n'
         '      auto& gate = m16sysui::gate();\n'
         '      std::lock_guard<std::mutex> lock(gate.mutex);\n'
         '      m16sysui::Closed(gate.state);\n'
         '    }\n'
         '    current = nullptr;\n'
         '    REXKRNL_INFO("M16 achievements_ui close");\n'
         '    // Broadcast XN_SYS_UI = false\n'
         '    kernel_state_->BroadcastNotification(0x9, false);\n'
         '  }\n'
         '\n'
         ' private:\n'
         '  rex::system::KernelState* kernel_state_;\n'
         '};\n'
         'M16AchievementsDialog* M16AchievementsDialog::current = nullptr;\n'
         '\n'
         'u32 XamShowAchievementsUI_entry(u32 user_index, u32 unk) {\n'
         '  auto* kernel_state = REX_KERNEL_STATE();\n'
         '  auto* emulator = kernel_state->emulator();\n'
         '  rex::ui::WindowedAppContext* app_context = emulator->app_context();\n'
         '  ui::ImGuiDrawer* imgui_drawer = emulator->imgui_drawer();\n'
         '  size_t total = 0, unlocked = 0;\n'
         '  for (const auto& a : kernel_state->achievements().ListAchievements()) {\n'
         '    ++total;\n'
         '    unlocked += kernel_state->achievements().IsUnlocked(a.id) ? 1 : 0;\n'
         '  }\n'
         '  const bool can_show = !REXCVAR_GET(headless) && imgui_drawer && app_context;\n'
         '  REXKRNL_INFO("M16 achievements_ui request user={} arg={:08X} achievements={} unlocked={} dialog={}",\n'
         '               uint32_t(user_index), uint32_t(unk), total, unlocked, can_show);\n'
         '  if (!can_show) {\n'
         '    return X_ERROR_SUCCESS;\n'
         '  }\n'
         '  {\n'
         '    auto& gate = m16sysui::gate();\n'
         '    std::lock_guard<std::mutex> lock(gate.mutex);\n'
         '    if (gate.state.open) {\n'
         '      return X_ERROR_SUCCESS;\n'
         '    }\n'
         '    m16sysui::Open(gate.state);\n'
         '    gate.request_close = [app_context]() {\n'
         '      app_context->CallInUIThreadDeferred([]() {\n'
         '        if (M16AchievementsDialog::current) {\n'
         '          M16AchievementsDialog::current->RequestClose();\n'
         '        }\n'
         '      });\n'
         '    };\n'
         '  }\n'
         '  // Broadcast XN_SYS_UI = true\n'
         '  kernel_state->BroadcastNotification(0x9, true);\n'
         '  if (!app_context->CallInUIThreadDeferred([imgui_drawer, emulator, kernel_state]() {\n'
         '        M16AchievementsDialog::current =\n'
         '            new M16AchievementsDialog(imgui_drawer, emulator, kernel_state);\n'
         '        REXKRNL_INFO("M16 achievements_ui open");\n'
         '      })) {\n'
         '    auto& gate = m16sysui::gate();\n'
         '    {\n'
         '      std::lock_guard<std::mutex> lock(gate.mutex);\n'
         '      gate.state = m16sysui::State{};\n'
         '    }\n'
         '    kernel_state->BroadcastNotification(0x9, false);\n'
         '  }\n'
         '  return X_ERROR_SUCCESS;\n'
         '}\n'
         '\n'
         'u32 XamShowPartyUI_entry(u32 r3, u32 r4) {\n'),
        ('REX_EXPORT(__imp__XamShowPartyUI, rex::kernel::xam::XamShowPartyUI_entry)\n',
         'REX_EXPORT(__imp__XamShowPartyUI, rex::kernel::xam::XamShowPartyUI_entry)\n'
         'REX_EXPORT(__imp__XamShowAchievementsUI, rex::kernel::xam::XamShowAchievementsUI_entry)\n'),
    ])
    # patch_once cannot express a removal (an empty replacement is always "already present").
    path = SDK / 'src/kernel/xam/xam_ui.cpp'
    text = path.read_text()
    stub = 'REX_EXPORT_STUB(__imp__XamShowAchievementsUI);\n'
    if stub in text:
        assert text.count(stub) == 1, 'XamShowAchievementsUI stub'
        path.write_text(text.replace(stub, ''))
        print('removed stub XamShowAchievementsUI')
