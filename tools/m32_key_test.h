// M32 (D-069): test-only keyboard source for hidden runs. Same schedule file and vocabulary as m6_test_input.h
// (R3HD_INPUT_SCHEDULE: "ms scancode down", SDL scancodes), but with R3HD_KEYMAP_TEST=1 the keys do not go through
// m6's fixed scancode table: each one is translated as the window would translate it (TranslateSDLScancode) and
// handed to a private instance of the real keyboard driver, whose state is then read with the live keybind_*
// settings. So the keys a launch passes reach the title exactly as a person's would, minus the window itself.
// No window, no SDL event, no desktop input: the instance has no window and the hidden run's own driver is untouched.
#pragma once
#include <rex/input/mnk/mnk_input_driver.h>
#include <rex/m6_test_input.h>
#include <rex/logging.h>
#include <rex/ui/sdl_virtual_key.h>
#include <rex/ui/ui_event.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
namespace m32keys {
using rex::X_RESULT;  // X_ERROR_SUCCESS expands to an unqualified X_RESULT
inline bool Enabled() {
  static const bool on = std::getenv("R3HD_NONINTRUSIVE") && std::getenv("R3HD_KEYMAP_TEST");
  return on;
}
class Source {
  std::ifstream file_;
  std::chrono::steady_clock::time_point start_ = std::chrono::steady_clock::now();
  std::unique_ptr<rex::input::mnk::MnkInputDriver> driver_;
  rex::input::DeviceId id_{};
  unsigned ms_ = 0, scan_ = 0;
  int down_ = 0;
  bool waiting_ = false, ok_ = false;
  m6input::State previous_{};

 public:
  explicit Source(const char* path) : file_(path ? path : "") {
    driver_ = std::make_unique<rex::input::mnk::MnkInputDriver>(nullptr, 0);
    driver_->SetTestEnabled(true);
    driver_->Setup();
    rex::ui::UISetupEvent focus(nullptr, false);
    driver_->OnGotFocus(focus);
    std::vector<rex::input::DeviceInfo> devices;
    driver_->EnumerateDevices(devices);
    ok_ = devices.size() == 1;
    if (ok_) id_ = devices[0].id;
    REXLOG_INFO("M32 keymap_test source=mnk_driver device={}", ok_ ? "ok" : "missing");
  }
  m6input::State Sample(unsigned elapsed, bool consume) {
    for (;;) {
      if (!waiting_) {
        auto pos = file_.tellg();
        std::string line;
        if (!std::getline(file_, line) || file_.eof()) {
          file_.clear();
          file_.seekg(pos);
          break;  // retry an incomplete appended line
        }
        if (std::sscanf(line.c_str(), "%u %u %d", &ms_, &scan_, &down_) != 3) continue;
        waiting_ = true;
      }
      if (ms_ > elapsed) break;
      waiting_ = false;
      if (scan_ >= 300 || down_ < 0 || down_ > 1) {
        REXLOG_INFO("M32 keymap_test ignored scancode={} value={} (analog axes are not keys)", scan_, down_);
        continue;
      }
      auto vk = rex::ui::TranslateSDLScancode(SDL_Scancode(scan_));
      rex::ui::KeyEvent e(nullptr, vk, 1, !down_, false, false, false, false);
      if (down_) driver_->OnKeyDown(e); else driver_->OnKeyUp(e);
      REXLOG_INFO("M32 keymap_test key scancode={} vk={} down={}", scan_, unsigned(vk), down_);
    }
    m6input::State s;
    rex::input::X_INPUT_STATE state{};
    if (ok_ && driver_->GetDeviceState(id_, consume ? &state : nullptr) == X_ERROR_SUCCESS && consume) {
      s.buttons = uint16_t(state.gamepad.buttons);
      s.lx = state.gamepad.thumb_lx; s.ly = state.gamepad.thumb_ly;
      s.rx = state.gamepad.thumb_rx; s.ry = state.gamepad.thumb_ry;
      s.lt = state.gamepad.left_trigger; s.rt = state.gamepad.right_trigger;
    } else if (!consume) {
      s = previous_;  // a null query must not drain a latched press
    }
    s.packet = previous_.packet + (s.buttons != previous_.buttons || s.lx != previous_.lx || s.ly != previous_.ly ||
                                   s.rx != previous_.rx || s.ry != previous_.ry || s.lt != previous_.lt ||
                                   s.rt != previous_.rt);
    if (consume && (s.buttons != previous_.buttons || s.lt != previous_.lt || s.rt != previous_.rt ||
                    s.lx != previous_.lx || s.ly != previous_.ly || s.rx != previous_.rx || s.ry != previous_.ry))
      REXLOG_INFO("M32 keymap_test pad buttons={:04X} lt={} rt={} lx={} ly={} rx={} ry={}", s.buttons, s.lt, s.rt,
                  s.lx, s.ly, s.rx, s.ry);
    if (consume) previous_ = s;
    return s;
  }
  m6input::State SampleNow(bool consume) {
    return Sample(unsigned(std::chrono::duration_cast<std::chrono::milliseconds>(
                               std::chrono::steady_clock::now() - start_).count()), consume);
  }
};
inline m6input::State Sample(bool consume) {
  static std::mutex lock;
  std::lock_guard guard(lock);
  static Source source(std::getenv("R3HD_INPUT_SCHEDULE"));
  return source.SampleNow(consume);
}
}  // namespace m32keys
