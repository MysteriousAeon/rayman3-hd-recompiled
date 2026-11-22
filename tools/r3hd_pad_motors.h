// G6-P75 (D-324): controller motors are stopped when the game closes. SDL-free policy, host only, no game material.
// Installed as include/rex/r3hd_pad_motors.h by tools/r3hd_pad_motors_patch.py; the SDL calls are in
// r3hd_pad_motors_sdl.h. Tested with a mock pad by tools/r3hd_pad_motors_test.cpp.
//
// XInput vibration holds until the title changes it; the SDL driver arms each request for SDL's maximum duration and
// SDL only cancels it in SDL_CloseGamepad or by its own timer. A window close hard-exits the process (ReXApp::OnClosing,
// std::_Exit) and a title exit destroys the runtime without closing the pads, so neither reaches SDL_CloseGamepad and
// a pad the title had vibrating at that moment was never told to stop.
//
// The rule: the driver remembers, per pad, whether its last vibration request may have left a motor running. When the
// game closes (window close or title exit) every such pad gets exactly one zero request, and from then on no request
// of the title reaches a device. A pad whose motors were never started gets no output at all. Nothing else changes:
// vibration during play, its strength and timing, focus loss and pause behave as before.
#pragma once
#include <cstdint>
#include <vector>

namespace r3hd_motors {

struct Motors {
  bool running = false;  // the last request asked for a nonzero speed, or a stop may not have reached the device
};

// After the driver's device call for one SetDeviceVibration request; `sent` is that call's result.
inline void Requested(Motors& m, uint16_t left, uint16_t right, bool sent) {
  const bool nonzero = (left | right) != 0;
  m.running = sent ? nonzero : (m.running || nonzero);  // a failed stop keeps the pad in the set to stop
}

// Once the game closes, the title's requests are answered without a device call.
class Outputs {
 public:
  bool closed() const { return closed_; }
  // Stops every pad that may be running (`stop(pad)` returns whether the device took the zero request) and closes
  // the outputs. Returns the number of pads given a stop request. A second call sends nothing.
  template <class Pad, class Stop>
  int Close(std::vector<Pad>& pads, Stop stop) {
    int sent = 0;
    if (!closed_) {
      for (auto& pad : pads) {
        if (!pad.motors.running) continue;
        ++sent;
        if (stop(pad)) pad.motors.running = false;
      }
    }
    closed_ = true;
    return sent;
  }

 private:
  bool closed_ = false;
};

}  // namespace r3hd_motors
