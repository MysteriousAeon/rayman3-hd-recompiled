// DualSense output glue for the SDK's SDL input driver (D-102). Installed into the SDK as <rex/r3hd_ds_sdl.h> by
// tools/r3hd_dualsense_patch.py and included by src/input/sdl/sdl_input_driver.cpp only. The decisions are the
// tested policy of <rex/r3hd_dualsense.h>; the guest facts come from <rex/r3hd_ds_state.h> (VdSwap). Output reaches
// a pad only when it is a DualSense (SDL type PS5, Sony 054C, product 0CE6 / 0DF2), the session is not a hidden run
// (M23 gate: a hidden run opens no physical pad at all) and the person turned the option on.
#pragma once

#include <SDL3/SDL.h>

#include <atomic>
#include <cstdint>
#include <cstring>
#include <vector>

#include <rex/logging.h>
#include <rex/m23_haptics.h>
#include <rex/r3hd_ds_state.h>
#include <rex/r3hd_dualsense.h>

namespace r3hd_ds {

inline bool IsDualSense(SDL_Gamepad* pad) {
  const uint16_t product = SDL_GetGamepadProduct(pad);
  return SDL_GetGamepadType(pad) == SDL_GAMEPAD_TYPE_PS5 && SDL_GetGamepadVendor(pad) == 0x054C &&
         (product == 0x0CE6 || product == 0x0DF2);
}

inline bool IsXInputStyle(SDL_Gamepad* pad) {
  const SDL_GamepadType t = SDL_GetGamepadType(pad);
  return t == SDL_GAMEPAD_TYPE_XBOX360 || t == SDL_GAMEPAD_TYPE_XBOXONE;
}

inline bool IsBluetooth(SDL_Gamepad* pad) {
  return SDL_GetGamepadConnectionState(pad) == SDL_JOYSTICK_CONNECTION_WIRELESS;
}

// Window focus as the window reports it (OnGotFocus / OnLostFocus, D-105). The driver's is_active() only says that
// no host overlay captures input: it stays true behind another window after Alt+Tab.
inline std::atomic<bool>& WindowFocus() {
  static std::atomic<bool> focus{false};
  return focus;
}

// Per pad: what the policy holds plus a few counters for the summary line at close.
struct PadOutput {
  Policy policy;
  bool dualsense = false;
  bool bluetooth = false;
  uint32_t light_writes = 0, light_restores = 0, trigger_writes = 0;
  bool light_failed_logged = false, trigger_failed_logged = false;
};

// The 47-byte DualSense effects block as SDL's HIDAPI PS5 driver takes it through SDL_SendGamepadEffect: only the
// right-trigger enable bit (byte 0, 0x04) and the 11 right-trigger bytes (offset 10) are set; nothing else changes.
inline bool SendTrigger(SDL_Gamepad* pad, const Trigger& t) {
  uint8_t block[47] = {};
  block[0] = 0x04;
  std::memcpy(block + 10, t.bytes, sizeof(t.bytes));
  return SDL_SendGamepadEffect(pad, block, sizeof(block));
}

// Every request is one SDL call that queues one output report (D-105): the light bar is given back by writing the
// idle colour the policy chose, never by SDL_SetGamepadPlayerIndex (at SDL 3.5.0 a no-op for the pad's own index).
inline void Apply(SDL_Gamepad* pad, PadOutput& o, const Output& out) {
  if (out.set_light) {
    if (SDL_SetGamepadLED(pad, out.light.r, out.light.g, out.light.b)) {
      if (out.restore_light) {
        ++o.light_restores;
      } else if (o.light_writes++ == 0) {
        REXLOG_INFO("R3HD dualsense light=set first=1");
      }
    } else {
      o.policy.FailedLight();
      if (!o.light_failed_logged) REXLOG_WARN("R3HD dualsense light=unsupported error={}", SDL_GetError());
      o.light_failed_logged = true;
    }
  }
  if (out.send_trigger) {
    if (SendTrigger(pad, out.trigger)) {
      if (o.trigger_writes++ == 0) REXLOG_INFO("R3HD dualsense trigger=written first=1");
    } else {
      o.policy.FailedTrigger();
      if (!o.trigger_failed_logged) REXLOG_WARN("R3HD dualsense trigger=unsupported error={}", SDL_GetError());
      o.trigger_failed_logged = true;
    }
  }
}

// One step for the pad the title just polled. `all` = every open pad (an XInput-style pad beside a DualSense
// means DS4Windows / DSX / Steam Input or a second controller: no output).
// R2 itself is not an input of the policy (D-105): the resistance is armed before R2 moves.
template <typename Pad>
void Step(Pad& pad, const std::vector<Pad>& all, int player_index, bool input_active) {
  if (m23haptics::Suppressed()) return;
  PadOutput& o = pad.ds;
  if (!o.dualsense) return;
  const Settings s = state::Configured();
  static std::atomic<bool> logged{false};
  if (s.trigger && !logged.exchange(true)) {
    REXLOG_INFO("R3HD dualsense trigger_strength={} force={}", s.trigger_strength, TriggerForce(s));
  }
  Device d;
  d.attached = true;
  d.dualsense = true;
  d.bluetooth = o.bluetooth;
  for (const auto& other : all) d.remapper_suspected |= IsXInputStyle(other.sdl);
  const state::Guest g = state::Read();
  State st;
  st.focused = input_active && WindowFocus().load();
  st.gameplay = g.gameplay;
  st.world = g.world;
  st.power = g.power;
  st.player_index = player_index;
  st.now_ms = static_cast<uint32_t>(SDL_GetTicks());
  Apply(pad.sdl, o, o.policy.Step(d, s, st));
}

// Gives every pad back (focus loss, which the close path also sends before its hard exit, and OnClosing). SDL hands
// HID output to its rumble thread; when something was queued, wait a bounded moment so it is written before a
// closing process ends (two reports at most per pad; the thread writes them within a few milliseconds).
template <typename Pad>
void ReleaseAll(std::vector<Pad>& pads, const char* reason) {
  if (m23haptics::Suppressed()) return;
  bool queued = false;
  for (size_t i = 0; i < pads.size(); ++i) {
    PadOutput& o = pads[i].ds;
    if (!o.dualsense) continue;
    const Output out = o.policy.Release(static_cast<int>(i));
    queued |= out.set_light || out.send_trigger;
    Apply(pads[i].sdl, o, out);
    REXLOG_INFO("R3HD dualsense release reason={} light_writes={} light_restores={} trigger_writes={}", reason,
                o.light_writes, o.light_restores, o.trigger_writes);
  }
  if (queued) SDL_Delay(50);
}

// After SDL_SetGamepadPlayerIndex renumbered the pads.
template <typename Pad>
void Renumbered(Pad& pad, int player_index) {
  if (m23haptics::Suppressed() || !pad.ds.dualsense) return;
  Apply(pad.sdl, pad.ds, pad.ds.policy.Renumbered(player_index));
}

}  // namespace r3hd_ds
