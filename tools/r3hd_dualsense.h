// DualSense light bar and R2 trigger policy (D-102). Pure decisions, no SDL call and no guest access: the SDK's SDL
// input driver steps it through <rex/r3hd_ds_sdl.h> (installed by tools/r3hd_dualsense_patch.py) with the guest facts
// of <rex/r3hd_ds_state.h>; tools/r3hd_dualsense_test.cpp drives it with a mock pad.
//
// Outputs are requests for the caller: set the light bar (SDL_SetGamepadLED), or write one right-trigger effect
// (SDL_SendGamepadEffect with ucEnableBits1 = 0x04 and the 11 bytes at rgucRightTriggerEffect; the layout and the two
// modes used here are those of SDL's own testcontroller.c at the pinned SDL 3.5.0: 0x05 = clear, 0x01 = constant
// resistance from a start position with a force).
// Giving the light bar back is an LED write too (D-105, E-255): a DualSense keeps the last colour a report commanded,
// it has no "previous colour" to return to and no report that reads one back, and at SDL 3.5.0 neither
// SDL_SetGamepadPlayerIndex with the pad's own index (a no-op: no report at all) nor anything else clears the
// driver's color_set flag. So the release colour is SDL's own player colour for the pad's index (IdleLight): the
// colour SDL itself sends when it takes the pad into enhanced mode, i.e. what the pad shows in this game with both
// options off. It is a documented fallback, not a restored "previous" colour.
// Light and trigger are independent: either may be off, unsupported or failed without touching the other.
// Trigger strength (D-108): the person's percentage scales only the force byte of the constant resistance
// (TriggerForce: 100 % = trigger_force, the D-105 value); the start position, R2's input and the gameplay are never
// scaled. 0 % means no resistance at all: the trigger is cleared like the option off.
#pragma once

#include <cstdint>

namespace r3hd_ds {

struct Rgb {
  uint8_t r = 0, g = 0, b = 0;
  bool operator==(const Rgb& o) const { return r == o.r && g == o.g && b == o.b; }
};

// Power numbering = the power-up can behaviours of YAM_mPowerz (RE_NOTES "M14": 1 Grappin, 2 Rouade, 3 PoingGeant,
// 4 Snipe, 5 Helico). Names: Grappin = LockJaw (raybody_grappin), Rouade = Vortex (raybody_tornado), PoingGeant =
// Heavy Metal Fist, Snipe = Shock Rocket (their costumes, E-144), Helico = Throttle Copter. The running game's power
// is the global actor's code, mapped by r3hd_ds_state.h's PowerFromCode (E-252).
enum Power : int { kNone = 0, kLockJaw = 1, kVortex = 2, kHeavyMetalFist = 3, kShockRocket = 4, kThrottleCopter = 5 };

inline constexpr Rgb kPowerColour[6] = {
    {0, 0, 0},       // none
    {20, 80, 255},   // LockJaw: blue
    {30, 230, 60},   // Vortex: green
    {255, 25, 15},   // Heavy Metal Fist: red
    {255, 110, 0},   // Shock Rocket: orange
    {255, 215, 0},   // Throttle Copter: yellow
};

// SDL 3.5.0's player colours (SDL_hidapi_ps5.c SetLedsForPlayerIndex, the Linux hid-sony list), index % 7.
inline Rgb IdleLight(int player_index) {
  static constexpr Rgb kPlayer[7] = {{0x00, 0x00, 0x40}, {0x40, 0x00, 0x00}, {0x00, 0x40, 0x00}, {0x20, 0x00, 0x20},
                                     {0x20, 0x10, 0x00}, {0x00, 0x10, 0x10}, {0x10, 0x10, 0x10}};
  return kPlayer[(player_index < 0 ? 0 : player_index) % 7];
}

// World colour: index = the title's current world `82836F60` (1..9, RE_NOTES "M18"). Chosen from the existing
// private frames of each world (dominant hue of the scene, statistics only, E-244), saturated for an LED:
inline constexpr Rgb kWorldColour[10] = {
    {0, 0, 0},
    {70, 40, 255},    // 1 The Fairy Council: night blue / indigo (intro_10)
    {70, 170, 20},    // 2 Clearleaf Forest: forest green (wood_10)
    {170, 110, 10},   // 3 The Bog of Murk: murky amber (swamp_60)
    {110, 160, 255},  // 4 The Land of the Livid Dead: pale sky blue (moor_00)
    {255, 60, 10},    // 5 The Desert of the Knaaren: lava red-orange (knaar_10)
    {255, 160, 20},   // 6 The Longest Shortcut: gold (flash_10)
    {40, 220, 255},   // 7 The Summit Beyond the Clouds: ice cyan (sea_10, mount_50)
    {255, 30, 110},   // 8 Hoodlum Headquarters: magenta (fact_22)
    {170, 40, 255},   // 9 The Tower of the Leptys: violet (tower_10 / lept_15)
};

struct Device {
  bool attached = false;
  bool dualsense = false;          // SDL type PS5 through the HIDAPI driver, vendor 054C, product 0CE6 / 0DF2
  bool bluetooth = false;          // informational: SDL builds the USB / Bluetooth report itself
  bool remapper_suspected = false; // an XInput pad present beside it (DS4Windows / DSX / Steam virtual pad)
};

struct Settings {
  bool light = false;              // light bar by world / power
  bool trigger = false;            // R2 resistance, armed for the whole of focused gameplay (R2 = lock-on)
  uint8_t brightness = 100;        // percent, 0..100
  uint8_t trigger_force = 60;      // 0..255: the force at 100 % strength (D-105; SDL's test uses 110)
  uint8_t trigger_strength = 30;   // percent of trigger_force, 0..100 (D-108; 0 = no resistance)
  uint8_t trigger_start = 20;      // 0..255 trigger position where the resistance begins: early in the travel, before
                                   // the lock-on threshold (right_trigger 30), so it is felt while R2 goes down
};

struct State {
  bool hidden_run = false;         // R3HD_NONINTRUSIVE: never any output (D-053)
  bool focused = false;
  bool gameplay = false;           // a level of a world is running, no front end / pause / photo mode / movie
  int world = 0;                   // 82836F60, 1..9; anything else = no world colour
  int power = kNone;
  int player_index = 0;            // the pad's SDL player index: its idle light (IdleLight)
  uint32_t now_ms = 0;
};

struct Trigger {
  uint8_t bytes[11] = {};
  bool operator==(const Trigger& o) const {
    for (int i = 0; i < 11; ++i) if (bytes[i] != o.bytes[i]) return false;
    return true;
  }
};

inline Trigger ClearTrigger() { Trigger t; t.bytes[0] = 0x05; return t; }
inline Trigger Resistance(uint8_t start, uint8_t force) {
  Trigger t;
  t.bytes[0] = 0x01;
  t.bytes[1] = start;
  t.bytes[2] = force;
  return t;
}

struct Output {
  bool set_light = false;
  Rgb light;
  bool restore_light = false;      // set_light carries the idle colour: the game's override is given back
  bool send_trigger = false;
  Trigger trigger;
};

// The force byte actually sent: trigger_force scaled by the strength, rounded, never above trigger_force; 0 only at 0 %.
inline uint8_t TriggerForce(const Settings& s) {
  const unsigned pct = s.trigger_strength > 100 ? 100u : s.trigger_strength;
  if (pct == 0) return 0;
  const unsigned f = (s.trigger_force * pct + 50) / 100;
  return static_cast<uint8_t>(f == 0 ? 1 : f);
}

inline Rgb Scale(Rgb c, uint8_t pct) {
  if (pct > 100) pct = 100;
  return {static_cast<uint8_t>(c.r * pct / 100), static_cast<uint8_t>(c.g * pct / 100),
          static_cast<uint8_t>(c.b * pct / 100)};
}

// Edge-triggered: a request is made only when the wanted state differs from what this policy last requested.
// The caller reports a failed request through Failed*(), which disables that output for the rest of the attachment.
class Policy {
 public:
  Output Step(const Device& d, const Settings& s, const State& st) {
    Output out;
    if (!d.attached) {           // disconnect: the pad is gone, nothing can be sent; forget what it held
      Reset();
      return out;
    }
    const bool eligible = d.dualsense && !d.remapper_suspected && !st.hidden_run;
    if (!eligible) {             // never touch a pad we do not own (and never in a hidden run); undo our own once
      return st.hidden_run ? out : Release(st.player_index);
    }
    // light bar: power > world > default
    if (light_ok_) {
      Rgb want{};
      bool custom = false;
      if (s.light && st.focused && st.gameplay) {
        if (st.power >= kLockJaw && st.power <= kThrottleCopter) {
          want = Scale(kPowerColour[st.power], s.brightness), custom = true;
        } else if (st.world >= 1 && st.world <= 9) {
          want = Scale(kWorldColour[st.world], s.brightness), custom = true;
        }
      }
      if (custom && (!light_custom_ || !(want == light_))) {
        out.set_light = true, out.light = want, light_ = want, light_custom_ = light_written_ = true;
      } else if (!custom && light_custom_) {
        GiveBackLight(out, st.player_index);
      }
    }
    // trigger: armed for the whole of focused gameplay, before R2 moves (D-105): resistance that waited for the
    // lock-on came when R2 was already down. It never depends on R2 itself, so pressing R2 sends nothing.
    // D-108: at 0 % strength nothing is armed; a strength change while armed sends the new force once.
    if (trigger_ok_) {
      const uint8_t force = TriggerForce(s);
      const bool want_on = s.trigger && force > 0 && st.focused && st.gameplay;
      if (!trigger_known_ && s.trigger) {        // first contact with the option on: a defined state either way
        out.send_trigger = true, out.trigger = want_on ? Resistance(s.trigger_start, force) : ClearTrigger();
        trigger_on_ = want_on, trigger_known_ = true, force_ = force;
      } else if (want_on && (!trigger_on_ || force != force_)) {
        out.send_trigger = true, out.trigger = Resistance(s.trigger_start, force), trigger_on_ = true, force_ = force;
      } else if (!want_on && trigger_on_) {
        out.send_trigger = true, out.trigger = ClearTrigger(), trigger_on_ = false;
      }
    }
    return out;
  }

  // Process end, focus loss, option change to off, or device handed back: undo whatever this policy set, with
  // reports the device acts on (an LED write of the idle colour, a trigger clear).
  Output Release(int player_index) {
    Output out;
    if (light_custom_) GiveBackLight(out, player_index);
    if (trigger_on_) out.send_trigger = true, out.trigger = ClearTrigger(), trigger_on_ = false;
    return out;
  }

  // SDL renumbered the pads (another one left). A changed index makes SDL repeat its color_set colour, the last one
  // written: a game colour stays right, but an idle colour is the old index's, so the new index's is written.
  Output Renumbered(int player_index) {
    Output out;
    if (light_written_ && !light_custom_ && light_ok_ && !(light_ == IdleLight(player_index))) {
      GiveBackLight(out, player_index);
    }
    return out;
  }
  void FailedLight() { light_ok_ = false, light_custom_ = false; }
  void FailedTrigger() { trigger_ok_ = false, trigger_on_ = false; }
  bool TriggerOn() const { return trigger_on_; }
  bool LightCustom() const { return light_custom_; }
  // Wrote the light bar during this attachment: SDL's color_set then stays on the last colour written, and SDL
  // repeats that colour itself when it renumbers the pads.
  bool LightWritten() const { return light_written_; }

 private:
  void GiveBackLight(Output& out, int player_index) {
    out.set_light = true, out.restore_light = true, out.light = IdleLight(player_index);
    light_ = out.light, light_custom_ = false;
  }
  void Reset() {
    light_custom_ = light_written_ = trigger_on_ = trigger_known_ = false;
    light_ok_ = trigger_ok_ = true;
  }
  Rgb light_{};
  bool light_custom_ = false, light_ok_ = true, light_written_ = false;
  bool trigger_on_ = false, trigger_known_ = false, trigger_ok_ = true;
  uint8_t force_ = 0;              // the force of the resistance last sent
};

}  // namespace r3hd_ds
