// G6-P75 (D-324): the SDL side of r3hd_pad_motors.h. Installed as include/rex/r3hd_pad_motors_sdl.h by
// tools/r3hd_pad_motors_patch.py and included by src/input/sdl/sdl_input_driver.cpp only. Its one device call is a
// zero rumble request, behind the M23 policy like every actuator call (tools/m23_haptics_regression.py audits it).
#pragma once
#include <SDL3/SDL.h>

#include <vector>

#include <rex/m23_haptics.h>
#include <rex/r3hd_pad_motors.h>

namespace r3hd_motors {

// Under the driver's controllers lock. Returns the number of pads given a stop request.
template <class Pad>
int CloseSdl(Outputs& outputs, std::vector<Pad>& pads) {
  if (m23haptics::Suppressed()) {  // M23 (D-053): a hidden run has no pad driver; never a device call here either
    return outputs.Close(pads, [](Pad&) { return true; });
  }
  const int sent = outputs.Close(pads, [](Pad& pad) { return SDL_RumbleGamepad(pad.sdl, 0, 0, 0); });
  // SDL hands HID output to its rumble thread; let it write the stop before a closing process ends (as r3hd_ds).
  if (sent) SDL_Delay(50);
  return sent;
}

}  // namespace r3hd_motors
