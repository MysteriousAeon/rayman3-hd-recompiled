// Exercise the actual launch snapshot with fake identity queries only: no SDL
// initialization, physical device opening, input sampling or output is possible.
#include <SDL3/SDL.h>
static int queries = 0, padCount = 1;
static SDL_GamepadType padTypes[2] = {SDL_GAMEPAD_TYPE_PS5, SDL_GAMEPAD_TYPE_XBOXONE};
static int players[2] = {0, 1};
static SDL_JoystickID ids[2] = {1, 2};
static SDL_InitFlags TestWasInit(SDL_InitFlags) { ++queries; return SDL_INIT_GAMEPAD; }
static SDL_JoystickID* TestGamepads(int* n) { ++queries; *n = padCount; return ids; }
static SDL_GamepadType TestType(SDL_JoystickID id) { ++queries; return padTypes[id - 1]; }
static int TestPlayer(SDL_JoystickID id) { ++queries; return players[id - 1]; }
static void TestFree(void*) {}
#define SDL_WasInit TestWasInit
#define SDL_GetGamepads TestGamepads
#define SDL_GetGamepadTypeForID TestType
#define SDL_GetGamepadPlayerIndexForID TestPlayer
#define SDL_free TestFree
#include "r3hd_button_prompts_sdl.h"
#undef SDL_WasInit
#undef SDL_GetGamepads
#undef SDL_GetGamepadTypeForID
#undef SDL_GetGamepadPlayerIndexForID
#undef SDL_free
#include "m33_mod_overlay.h"
#include <cstdio>
using namespace r3hd_prompts;
int main(int argc, char** argv) {
  int count = 0, failed = 0;
  auto check = [&](bool ok) { ++count; if (!ok) ++failed; };
  const Controller xbox{Family::Xbox, 0}, ps{Family::PlayStation, 0}, unknown{Family::Unknown, 0};
  check(SdlFamily(SDL_GAMEPAD_TYPE_PS3) == Family::PlayStation);
  check(SdlFamily(SDL_GAMEPAD_TYPE_PS4) == Family::PlayStation);
  check(SdlFamily(SDL_GAMEPAD_TYPE_PS5) == Family::PlayStation);
  check(SdlFamily(SDL_GAMEPAD_TYPE_XBOX360) == Family::Xbox);
  check(SdlFamily(SDL_GAMEPAD_TYPE_XBOXONE) == Family::Xbox);
  check(SdlFamily(SDL_GAMEPAD_TYPE_UNKNOWN) == Family::Unknown);
  check(SdlFamily(SDL_GAMEPAD_TYPE_STANDARD) == Family::Unknown);
  check(Select("auto", &xbox, 1) == Style::Xbox);
  check(Select("auto", &ps, 1) == Style::PlayStation);
  check(Select("auto", &unknown, 1) == Style::Xbox);
  check(Select("auto", nullptr, 0) == Style::Xbox);
  check(Select("xbox", &ps, 1) == Style::Xbox);
  check(Select("playstation", &xbox, 1) == Style::PlayStation);
  check(Select("playstation", nullptr, 0) == Style::PlayStation);
  check(Select("invalid", &ps, 1) == Style::Xbox);
  Controller pads[] = {{Family::Xbox, 1}, {Family::PlayStation, 0}};
  check(Select("auto", pads, 2) == Style::PlayStation);
  std::swap(pads[0], pads[1]);
  check(Select("auto", pads, 2) == Style::PlayStation);
  pads[1].player = 0;
  check(Select("auto", pads, 2) == Style::Xbox);  // ambiguous primary
  pads[0].player = pads[1].player = -1;
  check(Select("auto", pads, 2) == Style::Xbox);
  // New launches resolve disconnect/reconnect and changed identity, without stale state.
  check(Select("auto", &ps, 1) == Style::PlayStation);
  check(Select("auto", nullptr, 0) == Style::Xbox);
  check(Select("auto", &xbox, 1) == Style::Xbox);
  check(Select("auto", &ps, 1) == Style::PlayStation);
  auto env = [](const char* key, const char* value) {
#ifdef _WIN32
    _putenv_s(key, value ? value : "");
#else
    if (value) setenv(key, value, 1); else unsetenv(key);
#endif
  };
  env("R3HD_NONINTRUSIVE", nullptr);
  env("R3HD_BUTTON_PROMPTS", "auto");
  for (auto type : {SDL_GAMEPAD_TYPE_PS3, SDL_GAMEPAD_TYPE_PS4, SDL_GAMEPAD_TYPE_PS5}) {
    padTypes[0] = type; check(LaunchStyle() == Style::PlayStation);
  }
  padTypes[0] = SDL_GAMEPAD_TYPE_XBOXONE; check(LaunchStyle() == Style::Xbox);
  padTypes[0] = SDL_GAMEPAD_TYPE_UNKNOWN; check(LaunchStyle() == Style::Xbox);
  padCount = 0; check(LaunchStyle() == Style::Xbox);
  padCount = 2; padTypes[0] = SDL_GAMEPAD_TYPE_PS5;
  check(LaunchStyle() == Style::PlayStation);  // unique primary, despite another connected pad
  players[0] = 1; players[1] = 0;
  check(LaunchStyle() == Style::Xbox);  // Xbox primary wins even with a connected PS pad
  players[0] = 0; check(LaunchStyle() == Style::Xbox);  // ambiguity
  {  // G6-P43: the snapshot reports what the queried SDL instance enumerated
    Snapshot seen;
    check(LaunchStyle(&seen) == Style::Xbox && seen.queried && seen.initialized);
    check(seen.pads == 2 && seen.playstation == 1 && seen.xbox == 1);
  }
  players[1] = 1; padCount = 1;
  env("R3HD_BUTTON_PROMPTS", "xbox"); queries = 0;
  check(LaunchStyle() == Style::Xbox && queries == 0);
  env("R3HD_BUTTON_PROMPTS", "playstation"); queries = 0;
  check(LaunchStyle() == Style::PlayStation && queries == 0);
  env("R3HD_BUTTON_PROMPTS", "auto"); env("R3HD_NONINTRUSIVE", "1");
  env("R3HD_BUTTON_PROMPTS_TEST", "playstation"); queries = 0;
  check(LaunchStyle() == Style::PlayStation && queries == 0);
  env("R3HD_BUTTON_PROMPTS_TEST", "unknown");
  check(LaunchStyle() == Style::Xbox && queries == 0);
  env("R3HD_NONINTRUSIVE", nullptr); env("R3HD_BUTTON_PROMPTS_TEST", nullptr);
  env("R3HD_BUTTON_PROMPTS", nullptr);
  if (argc == 2) {
    m33mods::Plan plan;
    check(m33mods::Load(std::filesystem::path(argv[1]), plan).empty());
    check(plan.files.size() == 1 && plan.range_count > 0);
    for (const auto& file : plan.files) {
      check(file.path.filename() == "fix.btf" && file.guest_size == file.size);
      uint64_t end = 0;
      for (const auto& r : file.ranges) {
        check(r.offset >= end && r.offset + r.length <= file.size);
        end = r.offset + r.length;
        std::vector<uint8_t> whole(r.length + 20, 0xAA), split = whole;
        m33mods::Overlay(whole.data(), r.offset - 10, whole.size(), r.data.data(), r.offset, r.length);
        for (size_t i = 0; i < split.size(); i += 7)
          m33mods::Overlay(split.data() + i, r.offset - 10 + i, std::min(size_t(7), split.size() - i),
                           r.data.data(), r.offset, r.length);
        check(whole == split && whole.front() == 0xAA && whole.back() == 0xAA);
      }
    }
  }
  std::printf("BUTTON_PROMPT_TEST checks=%d failures=%d\n", count, failed);
  return failed ? 1 : 0;
}
