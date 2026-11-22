// G6-P75 (D-324): tools/r3hd_pad_motors_sdl.h against the pinned SDL (static library of the SDK build), with one SDL
// virtual gamepad that exists only inside this process (SDL_AttachVirtualJoystick): Windows and other programs never see
// it, and its "motors" are a callback that records the last speeds. Every physical SDL joystick backend is switched off
// before SDL starts, and the test refuses (exit 2, nothing opened) if any non-virtual joystick is visible, so no
// controller of the person is ever opened, lit, renumbered or vibrated. No window, no game.
//
//   r3hd_pad_motors_sdl_test.exe            normal policy (a visible session)
//   r3hd_pad_motors_sdl_test.exe hidden     run with R3HD_NONINTRUSIVE set: M23 must stop the device call
// Ends with R3HD_PAD_MOTORS_SDL_TEST PASS n/n.
#include <SDL3/SDL.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include <rex/r3hd_pad_motors_sdl.h>

namespace {

int g_pass = 0, g_fail = 0;
void check(const char* name, bool ok) {
  std::printf("%s %s\n", ok ? "PASS" : "FAIL", name);
  (ok ? g_pass : g_fail)++;
}

struct Motors {  // the virtual device's motors
  Uint16 low = 0, high = 0;
  int calls = 0;
};

bool SDLCALL Rumble(void* userdata, Uint16 low, Uint16 high) {
  auto* m = static_cast<Motors*>(userdata);
  m->low = low, m->high = high;
  ++m->calls;
  return true;
}

struct Pad {  // the fields of the SDL driver's ControllerState that r3hd_pad_motors_sdl.h uses
  Pad(SDL_Gamepad* g) : sdl(g) {}
  SDL_Gamepad* sdl;
  r3hd_motors::Motors motors;
};

// SetDeviceVibration as the patched SDL driver does it (65,535 ms: the driver's kRumbleDurationMs).
bool Vibrate(r3hd_motors::Outputs& out, Pad& pad, Uint16 l, Uint16 r) {
  if (out.closed()) return true;
  const bool sent = SDL_RumbleGamepad(pad.sdl, l, r, 0xFFFF);
  r3hd_motors::Requested(pad.motors, l, r, sent);
  return sent;
}

// Lets SDL run its joystick update for `ms` (its own rumble timer lives there).
void Pump(int ms) {
  const Uint64 end = SDL_GetTicks() + ms;
  while (SDL_GetTicks() < end) {
    SDL_UpdateGamepads();
    SDL_Delay(5);
  }
}

}  // namespace

int main(int argc, char** argv) {
  const bool hidden = argc > 1 && !std::strcmp(argv[1], "hidden");
  if (hidden != (std::getenv("R3HD_NONINTRUSIVE") != nullptr)) {
    std::printf("R3HD_PAD_MOTORS_SDL_TEST REFUSED: mode %s needs R3HD_NONINTRUSIVE %s\n", hidden ? "hidden" : "normal",
                hidden ? "set" : "unset");
    return 2;
  }
  for (const char* hint : {SDL_HINT_JOYSTICK_HIDAPI, SDL_HINT_JOYSTICK_RAWINPUT, SDL_HINT_JOYSTICK_GAMEINPUT,
                           SDL_HINT_JOYSTICK_DIRECTINPUT, SDL_HINT_XINPUT_ENABLED, SDL_HINT_JOYSTICK_WGI}) {
    SDL_SetHint(hint, "0");
  }
  if (!SDL_Init(SDL_INIT_GAMEPAD)) {
    std::printf("R3HD_PAD_MOTORS_SDL_TEST FAIL SDL_Init: %s\n", SDL_GetError());
    return 1;
  }
  int count = 0;
  SDL_JoystickID* ids = SDL_GetJoysticks(&count);
  bool foreign = false;
  for (int i = 0; i < count; ++i) foreign |= !SDL_IsJoystickVirtual(ids[i]);
  SDL_free(ids);
  if (count != 0 || foreign) {
    std::printf("R3HD_PAD_MOTORS_SDL_TEST REFUSED: %d joystick(s) visible before the virtual pad (non-virtual: %s)\n",
                count, foreign ? "yes" : "no");
    SDL_Quit();
    return 2;
  }

  Motors motors;
  SDL_VirtualJoystickDesc desc;
  SDL_INIT_INTERFACE(&desc);
  desc.type = SDL_JOYSTICK_TYPE_GAMEPAD;
  desc.naxes = SDL_GAMEPAD_AXIS_COUNT;
  desc.nbuttons = SDL_GAMEPAD_BUTTON_COUNT;
  desc.name = "R3HD G6-P75 in-process virtual pad";
  desc.userdata = &motors;
  desc.Rumble = Rumble;
  const SDL_JoystickID id = SDL_AttachVirtualJoystick(&desc);
  ids = SDL_GetJoysticks(&count);
  foreign = false;
  for (int i = 0; i < count; ++i) foreign |= !SDL_IsJoystickVirtual(ids[i]);
  SDL_free(ids);
  if (!id || count != 1 || foreign || !SDL_IsGamepad(id)) {
    std::printf("R3HD_PAD_MOTORS_SDL_TEST REFUSED: the virtual pad is not the only device (id %u, %d device(s))\n",
                unsigned(id), count);
    SDL_Quit();
    return 2;
  }
  check("fixture: only the in-process virtual pad exists", true);

  if (!hidden) {
    // Baseline: what the driver did before D-324. The title's request is armed for 65.5 s; the close path then ran
    // no device call before the hard exit.
    {
      Pad pad{SDL_OpenGamepad(id)};
      r3hd_motors::Outputs unused;
      Vibrate(unused, pad, 0xC000, 0x4000);
      const int calls = motors.calls;
      Pump(300);  // the moments a close takes: SDL's own timer does not stop it
      check("baseline: the request reached the pad", calls == 1 && motors.low == 0xC000 && motors.high == 0x4000);
      check("baseline: without SDL_CloseGamepad the pad is left vibrating", motors.calls == calls && motors.low == 0xC000);
      SDL_CloseGamepad(pad.sdl);
      check("control: SDL cancels it only in SDL_CloseGamepad, which a hard exit never reaches",
            motors.low == 0 && motors.high == 0 && motors.calls == calls + 1);
    }
    // The fix.
    {
      motors = {};
      std::vector<Pad> pads{{SDL_OpenGamepad(id)}};
      r3hd_motors::Outputs out;
      Vibrate(out, pads[0], 0xC000, 0x4000);
      const int sent = r3hd_motors::CloseSdl(out, pads);
      check("close: one zero request reaches the vibrating pad",
            sent == 1 && motors.low == 0 && motors.high == 0 && motors.calls == 2 && !pads[0].motors.running);
      check("close: a second close sends nothing", r3hd_motors::CloseSdl(out, pads) == 0 && motors.calls == 2);
      check("close: a later request of the title reaches no device",
            Vibrate(out, pads[0], 0xFFFF, 0xFFFF) && motors.calls == 2 && motors.low == 0);
      SDL_CloseGamepad(pads[0].sdl);
    }
    {
      motors = {};
      std::vector<Pad> pads{{SDL_OpenGamepad(id)}};
      r3hd_motors::Outputs out;
      Vibrate(out, pads[0], 0x2000, 0);
      Vibrate(out, pads[0], 0, 0);  // the title stopped it itself
      const int before = motors.calls;
      check("close: a pad the title already stopped gets no output",
            r3hd_motors::CloseSdl(out, pads) == 0 && motors.calls == before && out.closed());
      SDL_CloseGamepad(pads[0].sdl);
    }
    {
      motors = {};
      std::vector<Pad> pads{{SDL_OpenGamepad(id)}};
      r3hd_motors::Outputs out;
      check("close: a pad never vibrated gets no output", r3hd_motors::CloseSdl(out, pads) == 0 && motors.calls == 0);
      SDL_CloseGamepad(pads[0].sdl);
    }
    {
      // Removed during vibration: the pad left the driver's list, nothing is sent to a handle that is gone.
      motors = {};
      std::vector<Pad> pads{{SDL_OpenGamepad(id)}};
      r3hd_motors::Outputs out;
      Vibrate(out, pads[0], 0x8000, 0x8000);
      SDL_CloseGamepad(pads[0].sdl);  // the driver closes and erases a removed pad (OnControllerDeviceRemovedLocked)
      pads.clear();
      const int calls = motors.calls;
      check("removed while vibrating: SDL's close stopped it and the close sends nothing more",
            r3hd_motors::CloseSdl(out, pads) == 0 && motors.calls == calls && motors.low == 0);
    }
  } else {
    // M23 (D-053): a hidden run never reaches a device from this helper.
    motors = {};
    std::vector<Pad> pads{{SDL_OpenGamepad(id)}};
    r3hd_motors::Requested(pads[0].motors, 0xC000, 0, true);  // as if a request had been taken
    r3hd_motors::Outputs out;
    r3hd_motors::CloseSdl(out, pads);
    check("hidden: no device call from the close", motors.calls == 0);
    check("hidden: the policy read the variable and the outputs are closed", m23haptics::Suppressed() && out.closed());
    SDL_CloseGamepad(pads[0].sdl);
  }

  SDL_DetachVirtualJoystick(id);
  SDL_Quit();
  std::printf("R3HD_PAD_MOTORS_SDL_TEST %s %d/%d mode=%s\n", g_fail ? "FAIL" : "PASS", g_pass, g_pass + g_fail,
              hidden ? "hidden" : "normal");
  return g_fail ? 1 : 0;
}
