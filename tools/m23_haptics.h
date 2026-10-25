// M23 (D-053): a hidden / unattended test run never drives a physical controller actuator.
// Installed as include/rex/m23_haptics.h by tools/m23_haptics_patch.py.
//
// Before this, a hidden run (R3HD_NONINTRUSIVE) took its pad state from the scheduled test source at the XAM
// boundary but still opened every connected controller through SDL and forwarded the title's XamInputSetState
// to it: the title's vibration reached the pad in a person's hands while they were doing something else.
//
// Policy, three independent layers, all keyed on the same variable that makes a run hidden (there is no switch
// that turns it off for a hidden run):
//   1. XamInputSetState answers a hidden run itself, like the other XAM input calls do: no driver is called.
//   2. A hidden run creates no physical pad driver (SDL, XInput): no controller is opened, so nothing can be
//      sent to one (vibration, trigger effects, LED, player index, mode changes) and no physical button can
//      reach a test.
//   3. The two places that write to an actuator (SDL_RumbleGamepad, XInputSetState) return before the call.
// A visible session (tools/play.ps1 never sets R3HD_NONINTRUSIVE) is untouched: vibration works as before.
// The hidden runner refuses to start an executable whose runtime library does not carry kMarker.
#pragma once
#include <atomic>
#include <cstdlib>

namespace m23haptics {
// Present in the runtime library's log format string; tools/run_milestone6.ps1 looks for it before a launch.
inline constexpr char kMarker[] = "M23 haptics policy={} physical_pad_drivers={}";

inline bool HiddenRun(const char* nonintrusive) { return nonintrusive != nullptr; }
inline bool Suppressed() {
  static const bool on = HiddenRun(std::getenv("R3HD_NONINTRUSIVE"));
  return on;
}
// What CreateDefaultInputSystem may add.
inline bool PhysicalPadDriversAllowed(bool suppressed) { return !suppressed; }
// Requests answered without reaching a device (layer 1) and calls stopped at a sink (layer 3; expected 0).
inline std::atomic<unsigned>& Answered() { static std::atomic<unsigned> n{0}; return n; }
inline std::atomic<unsigned>& StoppedAtSink() { static std::atomic<unsigned> n{0}; return n; }
// X_ERROR_SUCCESS (0) for the test source's one pad, X_ERROR_DEVICE_NOT_CONNECTED (0x48F) otherwise: the same
// users the hidden XamInputGetState answers for.
inline unsigned HiddenSetStateResult(unsigned user_index) {
  return (user_index == 0 || (user_index & 0xFF) == 0xFF) ? 0u : 0x48Fu;
}
}  // namespace m23haptics
