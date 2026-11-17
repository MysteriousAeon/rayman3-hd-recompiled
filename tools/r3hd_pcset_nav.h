#pragma once
// Settings-only navigation. Raw physical positions deliberately bypass gameplay remapping.
// No SDL initialisation, opening, output, or desktop input. Called on the drawer's UI thread.
#include <algorithm>
#include <map>
#include <cstdlib>
#include <SDL3/SDL.h>
#include <imgui.h>
#include <rex/r3hd_hostui_gate.h>

namespace r3hd_pcset {
struct NavPad {
  uint16_t buttons = 0;
  uint8_t left_trigger = 0, right_trigger = 0;
  int16_t thumb_lx = 0, thumb_ly = 0, thumb_rx = 0, thumb_ry = 0;
};
class GamepadNavigation {
 public:
  // Also used by windowless regressions: each connection must release held inputs first.
  NavPad Filter(uint32_t id, NavPad pad) {
    auto [it, fresh] = gates_.try_emplace(id);
    if (fresh) { NavPad seed = pad; it->second.Apply(false, seed); }
    it->second.Apply(true, pad);
    return pad;
  }
  void Reset() { gates_.clear(); }

  static void Feed(ImGuiIO& io, const NavPad& p) {
    const struct { ImGuiKey key; uint16_t mask; } buttons[] = {
        {ImGuiKey_GamepadFaceDown, 0x1000}, {ImGuiKey_GamepadFaceRight, 0x2000}};
    for (const auto& b : buttons) io.AddKeyEvent(b.key, (p.buttons & b.mask) != 0);
    // A deliberate navigation dead zone; gameplay values are never changed.
    // ImGui's LStick keys scroll, whereas Dpad keys move focus and edit sliders.
    // Route either navigation control to the latter, avoiding simultaneous scrolling.
    const auto axis = [&](ImGuiKey key, int value, uint16_t mask) {
      const float v = (p.buttons & mask) ? 1.0f : std::clamp((value - 16000.0f) / 16767.0f, 0.0f, 1.0f);
      io.AddKeyAnalogEvent(key, v > 0.0f, v);
    };
    axis(ImGuiKey_GamepadDpadLeft, -int(p.thumb_lx), 4);
    axis(ImGuiKey_GamepadDpadRight, p.thumb_lx, 8);
    axis(ImGuiKey_GamepadDpadUp, p.thumb_ly, 1);
    axis(ImGuiKey_GamepadDpadDown, -int(p.thumb_ly), 2);
  }
  void Update(ImGuiIO& io, bool enabled, bool focused) {
    if (enabled && !enabled_) {
      old_gamepad_ = (io.ConfigFlags & ImGuiConfigFlags_NavEnableGamepad) != 0;
      old_backend_ = (io.BackendFlags & ImGuiBackendFlags_HasGamepad) != 0;
      io.ConfigFlags |= ImGuiConfigFlags_NavEnableGamepad;
    }
    if (!enabled && enabled_) {
      Feed(io, {});
      if (!old_gamepad_) io.ConfigFlags &= ~ImGuiConfigFlags_NavEnableGamepad;
      if (!old_backend_) io.BackendFlags &= ~ImGuiBackendFlags_HasGamepad;
      Reset();
    }
    enabled_ = enabled;
    if (!enabled) return;  // no controller polling while closed
    NavPad merged;
    std::map<uint32_t, bool> seen;
    if (focused && !std::getenv("R3HD_NONINTRUSIVE") && SDL_WasInit(SDL_INIT_GAMEPAD)) {
      int count = 0;
      SDL_JoystickID* ids = SDL_GetGamepads(&count);
      for (int i = 0; i < count; ++i) {
        SDL_Gamepad* pad = SDL_GetGamepadFromID(ids[i]);  // borrowed, already opened by runtime
        if (!pad) continue;
        seen[ids[i]] = true;
        NavPad raw;
        const SDL_GamepadButton buttons[] = {SDL_GAMEPAD_BUTTON_DPAD_UP, SDL_GAMEPAD_BUTTON_DPAD_DOWN,
            SDL_GAMEPAD_BUTTON_DPAD_LEFT, SDL_GAMEPAD_BUTTON_DPAD_RIGHT,
            SDL_GAMEPAD_BUTTON_SOUTH, SDL_GAMEPAD_BUTTON_EAST};
        const uint16_t masks[] = {1, 2, 4, 8, 0x1000, 0x2000};
        for (int j = 0; j < 6; ++j) if (SDL_GetGamepadButton(pad, buttons[j])) raw.buttons |= masks[j];
        raw.thumb_lx = SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_LEFTX);
        raw.thumb_ly = int16_t(std::clamp(-int(SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_LEFTY)), -32768, 32767));
        raw = Filter(ids[i], raw);
        merged.buttons |= raw.buttons;
        if (std::abs(int(raw.thumb_lx)) > std::abs(int(merged.thumb_lx))) merged.thumb_lx = raw.thumb_lx;
        if (std::abs(int(raw.thumb_ly)) > std::abs(int(merged.thumb_ly))) merged.thumb_ly = raw.thumb_ly;
      }
      SDL_free(ids);
    }
    for (auto it = gates_.begin(); it != gates_.end();) {
      if (!seen.count(it->first)) it = gates_.erase(it); else ++it;
    }
    io.BackendFlags |= ImGuiBackendFlags_HasGamepad;
    Feed(io, merged);  // releases on focus loss / disconnect; re-arms after neutral
  }
 private:
  std::map<uint32_t, r3hd_hostui::PadGate> gates_;
  bool enabled_ = false, old_gamepad_ = false, old_backend_ = false;
};
}  // namespace r3hd_pcset
