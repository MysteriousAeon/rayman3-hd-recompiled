#pragma once
// G6-P80 (test only, hidden runs): scripted answers for the title's message boxes.
//
// In a hidden run the port shows XamShowMessageBoxUI as an ImGui modal in the hidden window. Nobody can answer it, so
// the title's sign-in error box ("Sign In" / "Back", sub_820F47C8) stays open for the rest of the process. While it is
// open the title's sign-in handler (sub_820F4F28) returns before its sign-in request branch, so later START presses
// cannot reach XamShowSigninUI (E-566). A person would answer the box.
//
// With the user-scoped schedule (m6input::UserEventsEnabled(): R3HD_NONINTRUSIVE + R3HD_TEST_USER_EVENTS exactly "1")
// a message box with an overlapped is instead left pending, with XN_SYS_UI = true, until the schedule answers it with
// code 340+B: then the chosen button B is written and the overlapped completes through the SDK's own deferred path
// (100 ms, completion, 100 ms, XN_SYS_UI = false), exactly the timing of the SDK's headless default answer. No answer:
// the box stays open, as before. Without the flag nothing here runs. One box at a time; others use the old path.
#include <chrono>
#include <cstdint>
#include <mutex>

#include <rex/logging.h>
#include <rex/memory/utils.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xio.h>
#include <rex/system/xtypes.h>
#include <rex/thread.h>

namespace g6p80dlg {
using rex::X_RESULT;  // the X_ERROR_* macros name it unqualified

struct Box {
  bool open = false;
  uint32_t result = 0, overlapped = 0, buttons = 0;
};
inline std::mutex& Lock() { static std::mutex m; return m; }
inline Box& Current() { static Box b; return b; }

// Called by XamShowMessageBoxUI in the test mode. True when the box is now pending for a scripted answer.
inline bool Open(uint32_t result_ptr, uint32_t overlapped_ptr, uint32_t buttons, uint32_t active) {
  if (!result_ptr || !overlapped_ptr || buttons == 0 || buttons > 4) return false;
  {
    std::lock_guard<std::mutex> g(Lock());
    if (Current().open) return false;
    Current() = {true, result_ptr, overlapped_ptr, buttons};
  }
  auto* ks = REX_KERNEL_STATE();
  rex::system::XOverlappedSetResult(ks->memory()->TranslateVirtual(overlapped_ptr), X_ERROR_IO_PENDING);
  ks->BroadcastNotification(0x9, true);  // XN_SYS_UI = true, as the SDK's dialog paths do
  REXKRNL_INFO("G6P80 dialog open buttons={} active={}", buttons, active);
  return true;
}

// Called from the test-mode input poll for each scheduled answer (code 340+B).
inline void Answer(uint32_t button) {
  Box box;
  {
    std::lock_guard<std::mutex> g(Lock());
    box = Current();
    if (!box.open || button >= box.buttons) {
      REXKRNL_INFO("G6P80 dialog answer button={} dropped={}", button, box.open ? "out_of_range" : "no_box");
      return;
    }
    Current() = {};
  }
  REXKRNL_INFO("G6P80 dialog answer button={}", button);
  const uint32_t result_ptr = box.result;
  REX_KERNEL_STATE()->CompleteOverlappedDeferred(
      [result_ptr, button]() -> X_RESULT {
        rex::memory::store_and_swap<uint32_t>(REX_KERNEL_MEMORY()->TranslateVirtual(result_ptr), button);
        return X_ERROR_SUCCESS;
      },
      box.overlapped, nullptr,
      []() {
        rex::thread::Sleep(std::chrono::milliseconds(100));
        REX_KERNEL_STATE()->BroadcastNotification(0x9, false);  // XN_SYS_UI = false
      });
}

}  // namespace g6p80dlg
