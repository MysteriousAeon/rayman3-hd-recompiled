#pragma once
// UI-thread launch snapshot only; identity queries never open or sample a device.
// G6-P43 (D-299): SDL is linked statically into rexruntime and, through its link
// interface, again into the host executable. Only the rexruntime copy is initialized
// (by the SDL input driver). The host must call RuntimeLaunchStyle, which is defined
// in rexruntime; LaunchStyle inlined into another module queries an uninitialized
// SDL, sees no gamepads and falls back to Xbox.
#include <SDL3/SDL.h>
#include <cstdlib>
#include <vector>
#include <rex/r3hd_button_prompt_policy.h>
namespace r3hd_prompts {
struct Snapshot { bool queried = false, initialized = false; size_t pads = 0, playstation = 0, xbox = 0; };
inline Family SdlFamily(SDL_GamepadType type) {
  if (type == SDL_GAMEPAD_TYPE_PS3 || type == SDL_GAMEPAD_TYPE_PS4 || type == SDL_GAMEPAD_TYPE_PS5)
    return Family::PlayStation;
  if (type == SDL_GAMEPAD_TYPE_XBOX360 || type == SDL_GAMEPAD_TYPE_XBOXONE) return Family::Xbox;
  return Family::Unknown;
}
inline Style LaunchStyle(Snapshot* seen = nullptr) {
  const char* p = std::getenv("R3HD_BUTTON_PROMPTS");
  const std::string_view preference = p ? p : "auto";
  if (preference != "auto") return Select(preference, nullptr, 0);
  // The hidden runner has no physical input drivers. Never query physical devices
  // there; the explicit synthetic identity is restricted to that test policy.
  if (std::getenv("R3HD_NONINTRUSIVE")) {
    const char* t = std::getenv("R3HD_BUTTON_PROMPTS_TEST");
    const Controller synthetic{t && std::string_view(t) == "playstation" ? Family::PlayStation :
                               t && std::string_view(t) == "xbox" ? Family::Xbox : Family::Unknown, 0};
    return Select(preference, &synthetic, t ? 1 : 0);
  }
  std::vector<Controller> pads;
  const bool initialized = SDL_WasInit(SDL_INIT_GAMEPAD) != 0;
  if (initialized) {
    int count = 0;
    SDL_JoystickID* ids = SDL_GetGamepads(&count);
    for (int i = 0; i < count; ++i)
      pads.push_back({SdlFamily(SDL_GetGamepadTypeForID(ids[i])), SDL_GetGamepadPlayerIndexForID(ids[i])});
    SDL_free(ids);
  }
  if (seen) {
    *seen = {true, initialized, pads.size(), 0, 0};
    for (const auto& pad : pads) {
      seen->playstation += pad.family == Family::PlayStation;
      seen->xbox += pad.family == Family::Xbox;
    }
  }
  return Select(preference, pads.data(), pads.size());
}
// Defined in rexruntime next to the SDL input driver (r3hd_button_prompts_patch.py).
Style RuntimeLaunchStyle();
}
