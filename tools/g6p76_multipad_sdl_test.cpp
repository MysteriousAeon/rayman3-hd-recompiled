// G6-P76: two controllers on the pinned SDL (static library of the SDK build), as two SDL virtual gamepads that exist
// only inside this process (SDL_AttachVirtualJoystick): Windows and other programs never see them, and their "motors"
// are callbacks that record the last speeds. Every physical SDL joystick backend is switched off before SDL starts, and
// the test refuses (exit 2, nothing opened) if any non-virtual joystick is visible. No window, no game, no physical
// controller is opened, lit, renumbered or vibrated.
//
// What it covers: per-pad input isolation and removal events in SDL itself; vibration routing per pad through the
// production helper (tools/r3hd_pad_motors_sdl.h, the code the SDL driver runs at close); removal of one pad while both
// vibrate; the G6-P75 close with two pads; and which identity SDL gives two devices (instance id, GUID, name), the basis
// for not deduplicating devices. The SDL driver's SetDeviceVibration is reproduced as in G6-P75's test.
//
//   g6p76_multipad_sdl_test.exe            normal policy (a visible session)
//   g6p76_multipad_sdl_test.exe hidden     run with R3HD_NONINTRUSIVE set: M23 must stop every device call
// Ends with G6P76_MULTIPAD_SDL_TEST PASS n/n.
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

struct Motors {
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

bool Vibrate(r3hd_motors::Outputs& out, Pad& pad, Uint16 l, Uint16 r) {
  if (out.closed()) return true;
  const bool sent = SDL_RumbleGamepad(pad.sdl, l, r, 0xFFFF);
  r3hd_motors::Requested(pad.motors, l, r, sent);
  return sent;
}

void Pump(int ms) {
  const Uint64 end = SDL_GetTicks() + ms;
  while (SDL_GetTicks() < end) {
    SDL_UpdateGamepads();
    SDL_Delay(5);
  }
}

SDL_JoystickID Attach(Motors* m, const char* name, Uint16 vendor, Uint16 product) {
  SDL_VirtualJoystickDesc desc;
  SDL_INIT_INTERFACE(&desc);
  desc.type = SDL_JOYSTICK_TYPE_GAMEPAD;
  desc.naxes = SDL_GAMEPAD_AXIS_COUNT;
  desc.nbuttons = SDL_GAMEPAD_BUTTON_COUNT;
  desc.vendor_id = vendor;
  desc.product_id = product;
  desc.name = name;
  desc.userdata = m;
  desc.Rumble = Rumble;
  return SDL_AttachVirtualJoystick(&desc);
}

bool OnlyVirtual(int expected) {
  int count = 0;
  SDL_JoystickID* ids = SDL_GetJoysticks(&count);
  bool foreign = false;
  for (int i = 0; i < count; ++i) foreign |= !SDL_IsJoystickVirtual(ids[i]);
  SDL_free(ids);
  return count == expected && !foreign;
}

// Drains queued SDL events; counts REMOVED events for `which`.
int DrainRemoved(SDL_JoystickID which) {
  SDL_UpdateGamepads();
  SDL_PumpEvents();
  int removed = 0;
  SDL_Event e;
  while (SDL_PollEvent(&e))
    if (e.type == SDL_EVENT_GAMEPAD_REMOVED && e.gdevice.which == which) ++removed;
  return removed;
}

}  // namespace

int main(int argc, char** argv) {
  const bool hidden = argc > 1 && !std::strcmp(argv[1], "hidden");
  if (hidden != (std::getenv("R3HD_NONINTRUSIVE") != nullptr)) {
    std::printf("G6P76_MULTIPAD_SDL_TEST REFUSED: mode %s needs R3HD_NONINTRUSIVE %s\n", hidden ? "hidden" : "normal",
                hidden ? "set" : "unset");
    return 2;
  }
  for (const char* hint : {SDL_HINT_JOYSTICK_HIDAPI, SDL_HINT_JOYSTICK_RAWINPUT, SDL_HINT_JOYSTICK_GAMEINPUT,
                           SDL_HINT_JOYSTICK_DIRECTINPUT, SDL_HINT_XINPUT_ENABLED, SDL_HINT_JOYSTICK_WGI}) {
    SDL_SetHint(hint, "0");
  }
  if (!SDL_Init(SDL_INIT_GAMEPAD)) {
    std::printf("G6P76_MULTIPAD_SDL_TEST FAIL SDL_Init: %s\n", SDL_GetError());
    return 1;
  }
  if (!OnlyVirtual(0)) {
    std::printf("G6P76_MULTIPAD_SDL_TEST REFUSED: a joystick is visible before the virtual pads\n");
    SDL_Quit();
    return 2;
  }
  Motors m1, m2, m3;
  // Two distinguishable pads (an Xbox 360-type and a DualSense-type identity), then a third with pad 1's exact identity.
  const SDL_JoystickID id1 = Attach(&m1, "R3HD G6-P76 virtual pad 1", 0x045E, 0x028E);
  const SDL_JoystickID id2 = Attach(&m2, "R3HD G6-P76 virtual pad 2", 0x054C, 0x0CE6);
  if (!id1 || !id2 || !OnlyVirtual(2) || !SDL_IsGamepad(id1) || !SDL_IsGamepad(id2)) {
    std::printf("G6P76_MULTIPAD_SDL_TEST REFUSED: the two virtual pads are not the only devices\n");
    SDL_Quit();
    return 2;
  }
  check("fixture: only the two in-process virtual pads exist", true);
  SDL_Gamepad* g1 = SDL_OpenGamepad(id1);
  SDL_Gamepad* g2 = SDL_OpenGamepad(id2);
  check("fixture: both open, distinct instance ids", g1 && g2 && id1 != id2);
  SDL_Joystick* j1 = SDL_GetGamepadJoystick(g1);
  SDL_Joystick* j2 = SDL_GetGamepadJoystick(g2);

  // Input isolation in SDL: a press on pad 2 is reported for pad 2 only.
  SDL_SetJoystickVirtualButton(j2, SDL_GAMEPAD_BUTTON_START, true);
  SDL_SetJoystickVirtualAxis(j1, SDL_GAMEPAD_AXIS_LEFTX, 30000);
  SDL_SetJoystickVirtualAxis(j2, SDL_GAMEPAD_AXIS_LEFTX, -30000);
  SDL_UpdateGamepads();
  check("input: START on pad 2 only", SDL_GetGamepadButton(g2, SDL_GAMEPAD_BUTTON_START) &&
                                          !SDL_GetGamepadButton(g1, SDL_GAMEPAD_BUTTON_START));
  check("input: opposing sticks stay per pad", SDL_GetGamepadAxis(g1, SDL_GAMEPAD_AXIS_LEFTX) == 30000 &&
                                                   SDL_GetGamepadAxis(g2, SDL_GAMEPAD_AXIS_LEFTX) == -30000);

  // Identity: what a deduplication could key on.
  char guid1[33] = {}, guid2[33] = {}, guid3[33] = {};
  SDL_GUIDToString(SDL_GetJoystickGUIDForID(id1), guid1, sizeof(guid1));
  SDL_GUIDToString(SDL_GetJoystickGUIDForID(id2), guid2, sizeof(guid2));
  check("identity: different VID/PID give different GUIDs", std::strcmp(guid1, guid2) != 0);
  const SDL_JoystickID id3 = Attach(&m3, "R3HD G6-P76 virtual pad 1", 0x045E, 0x028E);  // pad 1's identity again
  SDL_GUIDToString(SDL_GetJoystickGUIDForID(id3), guid3, sizeof(guid3));
  const char* n1 = SDL_GetJoystickNameForID(id1);
  const char* n3 = SDL_GetJoystickNameForID(id3);
  check("identity: a second device with pad 1's VID/PID/name has the same GUID and name, another instance id",
        id3 && id3 != id1 && !std::strcmp(guid1, guid3) && n1 && n3 && !std::strcmp(n1, n3));
  std::printf("INFO guid1=%s guid2=%s guid3=%s serial1=%s path1=%s\n", guid1, guid2, guid3,
              SDL_GetJoystickSerial(j1) ? SDL_GetJoystickSerial(j1) : "-",
              SDL_GetJoystickPathForID(id1) ? SDL_GetJoystickPathForID(id1) : "-");
  SDL_DetachVirtualJoystick(id3);
  DrainRemoved(id3);
  check("identity: back to two devices", OnlyVirtual(2));

  if (!hidden) {
    // Routing: a request for pad 1 reaches pad 1 only.
    std::vector<Pad> pads{{g1}, {g2}};
    r3hd_motors::Outputs out;
    Vibrate(out, pads[0], 0xC000, 0x4000);
    check("routing: pad 1's request reaches pad 1 only", m1.calls == 1 && m1.low == 0xC000 && m2.calls == 0);
    Vibrate(out, pads[1], 0x1000, 0x2000);
    check("routing: pad 2's request reaches pad 2 only", m2.calls == 1 && m2.high == 0x2000 && m1.calls == 1);
    Vibrate(out, pads[1], 0, 0);
    check("routing: pad 2 stopped by the title; pad 1 still running", m2.low == 0 && m1.low == 0xC000 &&
                                                                       !pads[1].motors.running && pads[0].motors.running);
    Vibrate(out, pads[1], 0x3000, 0x3000);

    // Removal of pad 1 while both vibrate: the driver closes and erases it on SDL_EVENT_GAMEPAD_REMOVED.
    const int c2 = m2.calls;
    SDL_DetachVirtualJoystick(id1);
    const int removed = DrainRemoved(id1);
    SDL_CloseGamepad(pads[0].sdl);  // OnControllerDeviceRemovedLocked
    pads.erase(pads.begin());
    check("removal: SDL reports REMOVED for pad 1", removed == 1);
    check("removal: pad 2 keeps vibrating, untouched", m2.calls == c2 && m2.low == 0x3000);
    Pump(100);
    check("removal: pad 2 still reads input after pad 1 is gone",
          SDL_GetGamepadButton(pads[0].sdl, SDL_GAMEPAD_BUTTON_START));

    // Reconnection: a new instance id; vibration of the old handle cannot reach it.
    Motors m4;
    const SDL_JoystickID id4 = Attach(&m4, "R3HD G6-P76 virtual pad 1", 0x045E, 0x028E);
    check("reconnect: a new instance id", id4 && id4 != id1);
    pads.emplace_back(SDL_OpenGamepad(id4));
    check("reconnect: the new pad starts silent", m4.calls == 0 && !pads[1].motors.running);

    // G6-P75 close with two pads: only the running pad gets the zero request.
    const int sent = r3hd_motors::CloseSdl(out, pads);
    check("close: one stop, to pad 2 (running); the reconnected pad gets nothing",
          sent == 1 && m2.low == 0 && m2.high == 0 && m2.calls == c2 + 1 && m4.calls == 0);
    check("close: a later request reaches no pad", Vibrate(out, pads[0], 0xFFFF, 0xFFFF) &&
                                                      Vibrate(out, pads[1], 0xFFFF, 0xFFFF) && m2.calls == c2 + 1 &&
                                                      m4.calls == 0);
    // Both running at close.
    std::vector<Pad> both{{pads[0].sdl}, {pads[1].sdl}};
    r3hd_motors::Outputs out2;
    Vibrate(out2, both[0], 0x8000, 0);
    Vibrate(out2, both[1], 0, 0x8000);
    const int m2c = m2.calls, m4c = m4.calls;
    check("close: both pads running get one stop each",
          r3hd_motors::CloseSdl(out2, both) == 2 && m2.calls == m2c + 1 && m4.calls == m4c + 1 && m2.low == 0 &&
              m4.high == 0);
    SDL_CloseGamepad(pads[0].sdl);
    SDL_CloseGamepad(pads[1].sdl);
    SDL_DetachVirtualJoystick(id4);
  } else {
    std::vector<Pad> pads{{g1}, {g2}};
    r3hd_motors::Requested(pads[0].motors, 0xC000, 0, true);
    r3hd_motors::Requested(pads[1].motors, 0, 0xC000, true);
    r3hd_motors::Outputs out;
    r3hd_motors::CloseSdl(out, pads);
    check("hidden: no device call to either pad from the close", m1.calls == 0 && m2.calls == 0);
    check("hidden: the policy read the variable and the outputs are closed", m23haptics::Suppressed() && out.closed());
    SDL_CloseGamepad(g1);
    SDL_CloseGamepad(g2);
    SDL_DetachVirtualJoystick(id1);
  }
  SDL_DetachVirtualJoystick(id2);
  SDL_Quit();
  std::printf("G6P76_MULTIPAD_SDL_TEST %s %d/%d mode=%s\n", g_fail ? "FAIL" : "PASS", g_pass, g_pass + g_fail,
              hidden ? "hidden" : "normal");
  return g_fail ? 1 : 0;
}
