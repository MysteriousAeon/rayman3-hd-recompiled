// Guest facts for the DualSense policy (D-102, D-104), read-only. Installed into the SDK as <rex/r3hd_ds_state.h> by
// tools/r3hd_dualsense_patch.py. The VdSwap export calls Swap() once per guest frame; the SDL input driver calls
// Read(). Nothing is written to the guest. Addresses (RE_NOTES "M18", "M12", "Active power-up"):
//   82836F60  current world 1..9, set by each level's global actor (script procedure 0x354)
//   82C06221  engine block +1: the current level name (menumap = front end, staff = credits, endgame = end hub)
//   82875F2C  1 while the pause menu is open: 0 -> 1 at Start, 1 -> 0 at Resume in both pauses of a hidden run
//             (tools/r3hd_state_probe.py, E-249); cleared by the title's leave-pause routine 821079F8 together
//             with its engine-clock restore (RE_NOTES "M24"), read by five routines.
//   40CA9A2C  Perso of the fix level's global actor (GlobalActorModel, the same address in all 61 scanned levels);
//             its designer variable 0 is the active power-up: written 0..4 by the five YAM_mPowerz Go / Cine
//             behaviours, 5 by its own expiry macro, the player's init / hit macros and a few level scripts (E-252).
//             Reached through Perso +0xC Brain, Brain +0 Mind, Mind +0 AI model / +0xC DsgMem (RE_NOTES "M5"); every
//             guest address is checked with the caller's page-access test before it is read.
// Settings: R3HD_DS_LIGHT / R3HD_DS_TRIGGER = on | off (default off; play.ps1 sets them from the Settings);
// R3HD_DS_TRIGGER_STRENGTH = 0..100 percent (D-108; default 30, anything else than a plain number in range = 30).
// All three are read once, at the first DualSense step of the process: a change applies at the next game start.
#pragma once

#include <atomic>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <cstring>

#if __has_include(<rex/r3hd_dualsense.h>)
#include <rex/r3hd_dualsense.h>
#else
#include "r3hd_dualsense.h"   // the standalone test
#endif

namespace r3hd_ds::state {

inline constexpr uint32_t kWorld = 0x82836F60;
inline constexpr uint32_t kLevelName = 0x82C06221;
inline constexpr uint32_t kPause = 0x82875F2C;
inline constexpr uint32_t kGlobalPerso = 0x40CA9A2C;
inline constexpr uint32_t kDsgVarInt = 5;          // designer-variable type word of an Int (live reads, E-252)
inline constexpr int kPowerCodeNone = 5;           // the global actor's value without a power
inline constexpr int kPowerCodeUnread = 15;        // not in gameplay, or the structure did not check out

struct Guest {
  int world = 0;
  bool gameplay = false;
  int power = kNone;
  int power_code = kPowerCodeUnread;
  int power_step = 0;   // 0 = read, else the first step of ReadPowerCode that did not check out (log only)
};

inline std::atomic<uint32_t> g_packed{0};   // bits 0..7 world, bit 8 gameplay, 12..15 power code, 16..19 step

inline uint32_t LoadBE(const uint8_t* membase, uint32_t address) {
  uint32_t v;
  std::memcpy(&v, membase + address, 4);
  return (v >> 24) | ((v >> 8) & 0xFF00) | ((v << 8) & 0xFF0000) | (v << 24);
}

// The title's power code -> the policy's power. Codes are the constants the can behaviours write (YAM_mPowerz:
// 2GoRouade 0, 5GoHelico 1, 1GoGrappin 2, 4GoSnipe 3, 3GoPoingGeant 4); the player's costume macro then picks the
// body texture raybody_tornado (0), keeps rayman with object table 37 (1), raybody_grappin (2), ray_snipingfist (3),
// raybody_forcefist (4) (E-252).
inline int PowerFromCode(int code) {
  switch (code) {
    case 0: return kVortex;
    case 1: return kThrottleCopter;
    case 2: return kLockJaw;
    case 3: return kShockRocket;
    case 4: return kHeavyMetalFist;
    default: return kNone;   // 5 = no power; anything else is not a power the title writes
  }
}

inline const char* PowerName(int power) {
  static const char* const names[] = {"none", "lockjaw", "vortex", "heavy_metal_fist", "shock_rocket",
                                      "throttle_copter"};
  return power >= kNone && power <= kThrottleCopter ? names[power] : "none";
}

// The global actor's designer variable 0, or kPowerCodeUnread when any step fails: an address that is not readable
// guest memory, an AI model whose designer variables are not the ones the DsgMem names, a first variable that is
// not an Int, a value outside 0..5. readable(address, size) is the caller's page-access test; *step names the
// first check that failed (1 .. 6), 0 after a read.
template <typename Readable>
int ReadPowerCode(const uint8_t* membase, Readable&& readable, int* step = nullptr) {
  auto word = [&](uint32_t address, uint32_t& out) {
    if (!readable(address, 4u)) return false;
    out = LoadBE(membase, address);
    return true;
  };
  auto fail = [&](int n) {
    if (step) *step = n;
    return kPowerCodeUnread;
  };
  uint32_t brain, mind, model, dsgmem, model_vars, dsgmem_vars, info, length, count, offset, type, buffer, code;
  if (!word(kGlobalPerso + 0xC, brain) || !word(brain, mind) || !word(mind, model) || !word(mind + 0xC, dsgmem))
    return fail(1);
  if (!word(model + 8, model_vars) || !word(dsgmem, dsgmem_vars) || dsgmem_vars != model + 8) return fail(2);
  if (!word(model_vars + 4, info) || !word(model_vars + 8, length) || !word(model_vars + 0xC, count) ||
      (count >> 24) < 3)
    return fail(3);
  if (!word(info, offset) || !word(info + 4, type) || type != kDsgVarInt || offset + 4 > length) return fail(4);
  if (!word(dsgmem + 8, buffer)) return fail(5);
  if (!word(buffer + offset, code) || code > static_cast<uint32_t>(kPowerCodeNone)) return fail(6);
  if (step) *step = 0;
  return static_cast<int>(code);
}

// Pure decision from the raw guest values (tested in r3hd_dualsense_test.cpp). The power counts only in gameplay:
// out of it (front end, pause, a level being replaced) it is not read, so nothing stale can outlive a level.
inline Guest Decide(uint32_t world, const char* level, uint32_t pause_word, int power_code = kPowerCodeUnread) {
  Guest g;
  char low[16] = {};
  for (int i = 0; i < 15 && level[i]; ++i) low[i] = static_cast<char>(std::tolower(static_cast<unsigned char>(level[i])));
  const bool front = !low[0] || !std::strcmp(low, "menumap") || !std::strcmp(low, "staff") ||
                     !std::strcmp(low, "endgame");
  g.world = (world >= 1 && world <= 9) ? static_cast<int>(world) : 0;
  g.gameplay = !front && g.world != 0 && pause_word == 0;
  g.power_code = g.gameplay && power_code >= 0 && power_code <= kPowerCodeNone ? power_code : kPowerCodeUnread;
  g.power = g.gameplay ? PowerFromCode(g.power_code) : kNone;
  return g;
}

inline uint32_t Pack(const Guest& g) {
  return (g.gameplay ? 0x100u : 0u) | static_cast<uint32_t>(g.world) | (static_cast<uint32_t>(g.power_code) << 12) |
         (static_cast<uint32_t>(g.power_step & 0xF) << 16);
}

inline Guest Unpack(uint32_t v) {
  Guest g;
  g.world = static_cast<int>(v & 0xFF);
  g.gameplay = (v & 0x100) != 0;
  g.power_code = static_cast<int>((v >> 12) & 0xF);
  g.power_step = static_cast<int>((v >> 16) & 0xF);
  g.power = g.gameplay ? PowerFromCode(g.power_code) : kNone;
  return g;
}

// Returns true when the published state changed (the caller logs it: rare, level changes, pauses, power changes).
// with_power = false (light bar off) leaves the power unread.
template <typename Readable>
bool Swap(const uint8_t* membase, bool with_power, Readable&& readable) {
  if (!membase) return false;
  char level[16];
  std::memcpy(level, membase + kLevelName, 15);
  level[15] = 0;
  Guest g = Decide(LoadBE(membase, kWorld), level, LoadBE(membase, kPause));
  if (g.gameplay && with_power) {
    int step = 0;
    g = Decide(LoadBE(membase, kWorld), level, 0, ReadPowerCode(membase, readable, &step));
    g.power_step = step;
  }
  const uint32_t packed = Pack(g);
  return g_packed.exchange(packed, std::memory_order_relaxed) != packed;
}

inline Guest Read() { return Unpack(g_packed.load(std::memory_order_relaxed)); }

inline bool On(const char* name) {
  const char* v = std::getenv(name);
  return v && !std::strcmp(v, "on");
}

inline uint8_t Percent(const char* name, uint8_t fallback) {
  const char* v = std::getenv(name);
  if (!v || !*v || std::strlen(v) > 3) return fallback;
  unsigned n = 0;
  for (const char* c = v; *c; ++c) {
    if (!std::isdigit(static_cast<unsigned char>(*c))) return fallback;
    n = n * 10 + static_cast<unsigned>(*c - '0');
  }
  return n > 100 ? fallback : static_cast<uint8_t>(n);
}

inline Settings Configured() {
  static const Settings s = [] {
    Settings x;
    x.light = On("R3HD_DS_LIGHT");
    x.trigger = On("R3HD_DS_TRIGGER");
    x.trigger_strength = Percent("R3HD_DS_TRIGGER_STRENGTH", x.trigger_strength);
    return x;
  }();
  return s;
}

}  // namespace r3hd_ds::state
