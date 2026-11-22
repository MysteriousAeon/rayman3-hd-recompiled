"""Replay after r3hd_pad_motors_patch.py at the same pin (last in the chain): G6-P79 / G6-P80 profile handoff prototype.

TEST ONLY (D-328). Every effect is behind g6p79::Enabled() = R3HD_NONINTRUSIVE + R3HD_TEST_PROFILE_HANDOFF exactly
"1" (tools/g6p79_profile_handoff.h). Otherwise g6p79::Owner() is 0, the XAM user APIs answer exactly as before
(user 0 only), XamShowSigninUI broadcasts the same notifications with the same data, and nothing is recorded.
The one non-test behaviour in this file is G6-P83's (D-332) default: XamShowSigninUI sends XN_SYS_SIGNINCHANGED only
when the owner changed during the call (g6p82_signin_notify.h; R3HD_SIGNIN_NOTIFY=legacy switches back).

  * src/kernel/xam/xam_user.cpp (no earlier step patches it; rebuilt from the pin on every replay): each user-0
    special case asks g6p79::IsOwner(user). XamShowSigninUI, the title's sign-in request, is the only point where
    the owner may move. The owner's profile-settings read (after the size query) is a commit witness that locks it.
  * src/kernel/xam/xam_input.cpp: inside the M6 hidden-schedule path only, START presses are noted per user.
  * src/kernel/xam/xam_ui.cpp: the owner's device selection is also a commit witness.
Content stays keyed by the profile XUID, no guest memory is written and generated code is unchanged.

G6-P80 (D-329), still test only:
  * the candidate at XamShowSigninUI is the title's own selected user: its save-gate word 828750A0, read once,
    read-only (the patch's only guest memory access), cross-checked against a recent START edge and the connection;
  * a pending (not locked) owner whose controller is unplugged is rolled back to user 0, followed by
    XN_SYS_SIGNINCHANGED (g6p79::OnDisconnect);
  * with R3HD_TEST_USER_EVENTS exactly "1" (and the hidden gate) the schedule is pumped from every guest user's poll,
    events are user-scoped and their delivery is logged (m6_test_input.h), and the title's message box waits for a
    scripted answer (g6p80_test_dialog.h). Without that flag the input path and XamShowMessageBoxUI are unchanged.
"""
from m3_runtime_patch import patch
from m8_runtime_patch import patch_once
from m16_runtime_patch import install

TAG = 'G6-P79'

XAM_INPUT = [
    ('#include <rex/m6_test_input.h>',
     '#include <rex/m6_test_input.h>\n#include <rex/g6p79_profile_handoff.h>\n#include <rex/g6p80_test_dialog.h>'),
    # G6-P80 (test only): user-scoped events. The hook logs each note and rolls a pending handoff back when its user
    # is unplugged; then every due line is applied (from any user's poll) and scripted dialog answers are served.
    ('    const auto m6_route = m6input::RouteFor(actual_user_index);\n',
     '    static const bool g6p80_hooked = [] {  // G6-P80 (test only)\n'
     '      if (!m6input::UserEventsEnabled()) return false;\n'
     '      REXKRNL_INFO("G6P80 user_events enabled=1 target={}", m6input::TestUser());\n'
     '      m6input::SetUeHook(+[](const m6input::UeNote& n) {\n'
     '        static std::atomic<unsigned> lines{0};\n'
     '        if (n.kind == m6input::UeNote::kConnect && n.value == 0 && g6p79::OnDisconnect(n.user)) {\n'
     '          REXKRNL_INFO("G6P80 handoff rollback user={} owner={}", n.user, g6p79::Owner());\n'
     '          REX_KERNEL_STATE()->BroadcastNotification(0x0000000A, 1u << g6p79::Owner());  // XN_SYS_SIGNINCHANGED\n'
     '        }\n'
     '        if (lines.fetch_add(1) >= 512) return;\n'
     '        static const char* const kinds[] = {"target", "connect", "queued", "delivered", "dropped", "answer",\n'
     '                                            "answer_dropped", "limit"};\n'
     '        REXKRNL_INFO("G6P80 event {} seq={} user={} value={:X}", kinds[n.kind], n.seq, n.user, n.value);\n'
     '      });\n'
     '      return true;\n'
     '    }();\n'
     '    (void)g6p80_hooked;\n'
     '    m6input::Pump();  // G6-P80: no-op unless R3HD_TEST_USER_EVENTS\n'
     '    for (int b; (b = m6input::TakeDialogAnswer()) >= 0;) g6p80dlg::Answer(uint32_t(b));\n'
     '    const auto m6_route = m6input::RouteFor(actual_user_index);\n'),
    ('    auto s = m6input::Sample(bool(input_state));\n',
     '    auto s = m6input::SampleFor(actual_user_index, bool(input_state));  // G6-P80: user-scoped when enabled\n'),
    ('    (void)g6p77_logged;\n',
     '    (void)g6p77_logged;\n'
     '    static const bool g6p79_logged = [] {  // G6-P79 (test only)\n'
     '      if (g6p79::Enabled()) REXKRNL_INFO("G6P79 profile_handoff enabled=1 owner={}", g6p79::Owner());\n'
     '      return true;\n'
     '    }();\n'
     '    (void)g6p79_logged;\n'),
    ('    m24ev::Buttons(s.buttons, (uint32_t(s.lt) << 8) | uint32_t(s.rt));  // M24: on change, when tracing',
     '    if (g6p79::Enabled() && input_state && actual_user_index < g6p79::kUsers) {  // G6-P79: START candidates\n'
     '      static bool g6p79_held[g6p79::kUsers] = {};\n'
     '      static unsigned g6p79_lines = 0;\n'
     '      const bool start = (s.buttons & 0x0010) != 0;\n'
     '      if (start && !g6p79_held[actual_user_index]) g6p79::NoteStart(actual_user_index, g6p79::NowMs());  // press edge\n'
     '      if (start != g6p79_held[actual_user_index] && g6p79_lines < 64) {\n'
     '        ++g6p79_lines;\n'
     '        REXKRNL_INFO("G6P79 start user={} down={} owner={}", actual_user_index, int(start), g6p79::Owner());\n'
     '      }\n'
     '      g6p79_held[actual_user_index] = start;\n'
     '    }\n'
     '    m24ev::Buttons(s.buttons, (uint32_t(s.lt) << 8) | uint32_t(s.rt));  // M24: on change, when tracing'),
]

OWNER = 'g6p79::IsOwner(user_index)'

XAM_USER = [
    ('#include <rex/system/xtypes.h>\n',
     '#include <rex/system/xtypes.h>\n#include <rex/m6_test_input.h>\n#include <rex/g6p79_profile_handoff.h>\n'
     '#include <rex/g6p82_signin_notify.h>\n'),
    # XamUserGetXUID
    ('    if (user_index == 0) {\n'
     '      const auto& user_profile = REX_KERNEL_STATE()->user_profile();\n'
     '      auto type = user_profile->type() & type_mask;',
     f'    if ({OWNER}) {{  // {TAG}: the profile\'s user (0 unless the test handoff moved it)\n'
     '      const auto& user_profile = REX_KERNEL_STATE()->user_profile();\n'
     '      auto type = user_profile->type() & type_mask;'),
    # XamUserGetSigninState
    ('    if (user_index == 0) {\n'
     '      const auto& user_profile = REX_KERNEL_STATE()->user_profile();\n'
     '      signin_state = user_profile->signin_state();',
     f'    if ({OWNER}) {{  // {TAG}\n'
     '      const auto& user_profile = REX_KERNEL_STATE()->user_profile();\n'
     '      signin_state = user_profile->signin_state();'),
    # XamUserGetSigninInfo
    ('  std::memset(info, 0, sizeof(X_USER_SIGNIN_INFO));\n'
     '  if (user_index) {',
     '  std::memset(info, 0, sizeof(X_USER_SIGNIN_INFO));\n'
     f'  if (!{OWNER}) {{  // {TAG}'),
    # XamUserGetName
    ('  if (user_index) {\n'
     '    return X_E_NO_SUCH_USER;\n'
     '  }\n'
     '\n'
     '  const auto& user_profile = REX_KERNEL_STATE()->user_profile();\n'
     '  const auto& user_name = user_profile->name();',
     f'  if (!{OWNER}) {{  // {TAG}\n'
     '    return X_E_NO_SUCH_USER;\n'
     '  }\n'
     '\n'
     '  const auto& user_profile = REX_KERNEL_STATE()->user_profile();\n'
     '  const auto& user_name = user_profile->name();'),
    # XamUserGetGamerTag
    ('  if (user_index) {\n'
     '    return X_E_NO_SUCH_USER;\n'
     '  }\n'
     '\n'
     '  if (!buffer || buffer_len < 16) {',
     f'  if (!{OWNER}) {{  // {TAG}\n'
     '    return X_E_NO_SUCH_USER;\n'
     '  }\n'
     '\n'
     '  if (!buffer || buffer_len < 16) {'),
    # XamUserReadProfileSettingsEx: owner check and commit witness
    ('  if (!xuids && user_index) {\n'
     '    // Only support user 0.',
     f'  if (!xuids && !{OWNER}) {{  // {TAG}\n'
     '    // Only support user 0.'),
    ('  auto out_header = reinterpret_cast<X_USER_READ_PROFILE_SETTINGS*>(buffer);\n',
     f'  // {TAG}: a successful settings read by the owner (past the size query and the setting validation) is a\n'
     '  // commit witness: the title reads them only after its START commit found the user signed in. From then on\n'
     '  // the profile cannot move.\n'
     '  if (!xuids && g6p79::NoteCommitWitness(user_index))\n'
     '    REXKRNL_INFO("G6P79 handoff locked owner={} witness=profile_settings", uint32_t(user_index));\n'
     '  auto out_header = reinterpret_cast<X_USER_READ_PROFILE_SETTINGS*>(buffer);\n'),
    # XamUserWriteProfileSettings
    ('  if (user_index) {\n'
     '    // Only support user 0.\n'
     '    if (overlapped) {\n'
     '      REX_KERNEL_STATE()->CompleteOverlappedImmediate(overlapped.guest_address(),',
     f'  if (!{OWNER}) {{  // {TAG}\n'
     '    // Only support user 0.\n'
     '    if (overlapped) {\n'
     '      REX_KERNEL_STATE()->CompleteOverlappedImmediate(overlapped.guest_address(),'),
    # XamUserCheckPrivilege
    ('    if (user_index) {\n'
     '      return X_ERROR_NO_SUCH_USER;\n'
     '    }\n'
     '  }\n'
     '\n'
     '  // If we deny everything',
     f'    if (!{OWNER}) {{  // {TAG}\n'
     '      return X_ERROR_NO_SUCH_USER;\n'
     '    }\n'
     '  }\n'
     '\n'
     '  // If we deny everything'),
    # XamUserContentRestrictionGetFlags
    ('  if (user_index) {\n'
     '    return X_ERROR_NO_SUCH_USER;\n'
     '  }\n'
     '\n'
     '  // No restrictions?',
     f'  if (!{OWNER}) {{  // {TAG}\n'
     '    return X_ERROR_NO_SUCH_USER;\n'
     '  }\n'
     '\n'
     '  // No restrictions?'),
    # XamUserContentRestrictionGetRating
    ('  if (user_index) {\n'
     '    return X_ERROR_NO_SUCH_USER;\n'
     '  }\n'
     '\n'
     '  // Some games have special',
     f'  if (!{OWNER}) {{  // {TAG}\n'
     '    return X_ERROR_NO_SUCH_USER;\n'
     '  }\n'
     '\n'
     '  // Some games have special'),
    # XamUserGetMembershipTier
    ('  if (user_index) {\n'
     '    return X_ERROR_NO_SUCH_USER;\n'
     '  }\n'
     '  return 6 /* 6 appears to be Gold */;',
     f'  if (!{OWNER}) {{  // {TAG}\n'
     '    return X_ERROR_NO_SUCH_USER;\n'
     '  }\n'
     '  return 6 /* 6 appears to be Gold */;'),
    # XamUserAreUsersFriends
    ('    if (user_index == 0) {\n'
     '      const auto& user_profile = REX_KERNEL_STATE()->user_profile();\n'
     '      if (user_profile->signin_state() == 0) {',
     f'    if ({OWNER}) {{  // {TAG}\n'
     '      const auto& user_profile = REX_KERNEL_STATE()->user_profile();\n'
     '      if (user_profile->signin_state() == 0) {'),
    # XamShowSigninUI: the only handoff point
    ('  // To fix game modes that display a 4 profile signin UI (even if playing\n'
     '  // alone):\n'
     '  // XN_SYS_SIGNINCHANGED\n'
     '  REX_KERNEL_STATE()->BroadcastNotification(0x0000000A, 1);',
     '  const unsigned g6p82_owner_before = g6p79::Owner();  // G6-P82: the signed-in owner before this request\n'
     f'  // {TAG} (test only): the title\'s sign-in request is the only point where the one local profile may move,\n'
     '  // to the user the title itself selected (G6-P80), unless a commit witness has locked the owner.\n'
     '  if (g6p79::Enabled()) {\n'
     '    bool connected[g6p79::kUsers];\n'
     '    for (unsigned u = 0; u < g6p79::kUsers; ++u) connected[u] = m6input::RouteFor(u) != m6input::kNotConnected;\n'
     '    // G6-P80: the title\'s own selection, its save-gate word (read once, read-only; never written).\n'
     '    const uint32_t title_user = rex::memory::load_and_swap<uint32_t>(\n'
     '        REX_KERNEL_MEMORY()->TranslateVirtual(g6p79::kTitleSaveGateUser));\n'
     '    const auto d = g6p79::OnSigninRequest(connected, g6p79::NowMs(), title_user);\n'
     '    REXKRNL_INFO("G6P79 handoff signin_request panes={} flags={:X} outcome={} from={} to={} candidate={} "\n'
     '                 "connected={}{}{}{} title_user={:X} start_candidate={}",\n'
     '                 uint32_t(unk), uint32_t(unk_mask), g6p79::OutcomeName(d.outcome), d.from, d.to, d.candidate,\n'
     '                 int(connected[0]), int(connected[1]), int(connected[2]), int(connected[3]), title_user,\n'
     '                 d.start_candidate);\n'
     '  }\n'
     '\n'
     '  // To fix game modes that display a 4 profile signin UI (even if playing\n'
     '  // alone):\n'
     '  // XN_SYS_SIGNINCHANGED (data: signed-in user mask; 1 = user 0 as before, unless the test handoff moved it)\n'
     '  // G6-P82 / G6-P83 (D-332, g6p82_signin_notify.h): sent only when the owner changed during this call;\n'
     '  // R3HD_SIGNIN_NOTIFY exactly "legacy" sends it always, as inherited. XN_SYS_UI below is unchanged.\n'
     '  const bool g6p82_notify = g6p82::ShouldNotify(g6p82_owner_before, g6p79::Owner());\n'
     '  if (g6p82::Trace())\n'
     '    REXKRNL_INFO("G6P82 signin_ui owner_before={} owner_after={} signinchanged={} ui_off=1 notify_on_change={}",\n'
     '                 g6p82_owner_before, g6p79::Owner(), int(g6p82_notify), int(g6p82::Enabled()));\n'
     '  else if (g6p82::NoteLegacyOnce())\n'
     '    REXKRNL_INFO("XamShowSigninUI: legacy sign-in notification selected (R3HD_SIGNIN_NOTIFY=legacy)");\n'
     '  if (g6p82_notify)\n'
     '    REX_KERNEL_STATE()->BroadcastNotification(0x0000000A, 1u << g6p79::Owner());'),
]

XAM_UI = [
    ('#include <rex/m16_sysui.h>', '#include <rex/m16_sysui.h>\n#include <rex/g6p79_profile_handoff.h>'),
    # G6-P80: anchored on a line the earlier steps never duplicate (this file is not reset between replays).
    ('#include <rex/ui/imgui_drawer.h>\n',
     '#include <rex/ui/imgui_drawer.h>\n#include <rex/m6_test_input.h>\n#include <rex/g6p80_test_dialog.h>\n'),
    # G6-P80 (test only): with the user-scoped schedule a message box waits for a scripted answer (code 340+B).
    ('  X_RESULT result;\n  if (REXCVAR_GET(headless)) {\n    // Auto-pick the focused button.\n',
     '  if (m6input::UserEventsEnabled() &&  // G6-P80 (test only): answered by the schedule, see g6p80_test_dialog.h\n'
     '      g6p80dlg::Open(result_ptr.guest_address(), overlapped.guest_address(), uint32_t(button_count),\n'
     '                     uint32_t(active_button)))\n'
     '    return X_ERROR_IO_PENDING;\n'
     '  X_RESULT result;\n  if (REXCVAR_GET(headless)) {\n    // Auto-pick the focused button.\n'),
    ('                uint64_t(total_requested), device_id_ptr.guest_address(),\n'
     '                overlapped.guest_address());\n'
     '  return xeXamDispatchHeadless(',
     '                uint64_t(total_requested), device_id_ptr.guest_address(),\n'
     '                overlapped.guest_address());\n'
     f'  // {TAG}: device selection for the owner is a commit witness (see XamUserReadProfileSettingsEx).\n'
     '  if (g6p79::NoteCommitWitness(user_index))\n'
     '    REXKRNL_INFO("G6P79 handoff locked owner={} witness=device_selector", uint32_t(user_index));\n'
     '  return xeXamDispatchHeadless('),
]


if __name__ == '__main__':
    install('g6p79_profile_handoff.h')
    install('g6p80_test_dialog.h')
    install('g6p82_signin_notify.h')  # G6-P82 / G6-P83 (D-332): state-change-aware SIGNINCHANGED by default
    patch('src/kernel/xam/xam_user.cpp', XAM_USER)  # from the pin: idempotent, never stale
    patch_once('src/kernel/xam/xam_input.cpp', XAM_INPUT)
    patch_once('src/kernel/xam/xam_ui.cpp', XAM_UI)
