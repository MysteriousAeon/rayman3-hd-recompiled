// Mocked-output regression for tools/r3hd_dualsense.h (D-102). No SDL, no device, no game: a mock pad applies the
// policy's requests and the checks look at what a real DualSense would hold. Ends with R3HD_DUALSENSE_TEST PASS n/n.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

#include "r3hd_dualsense.h"
#include "r3hd_ds_state.h"

using namespace r3hd_ds;

namespace {

// A fake guest address space for r3hd_ds_state.h (D-104): 4 GiB reserved, only the pages a test commits are
// readable, as in the runtime where readable() asks the guest heap for committed pages.
struct Guest4G {
  uint8_t* base = nullptr;
  std::vector<uint32_t> pages;   // committed 64 KiB pages (guest address >> 16)
  Guest4G() { base = static_cast<uint8_t*>(VirtualAlloc(nullptr, 0x100000000ull, MEM_RESERVE, PAGE_NOACCESS)); }
  ~Guest4G() { if (base) VirtualFree(base, 0, MEM_RELEASE); }
  void Commit(uint32_t address) {
    const uint32_t page = address >> 16;
    for (uint32_t p : pages) if (p == page) return;
    VirtualAlloc(base + (static_cast<uint64_t>(page) << 16), 0x10000, MEM_COMMIT, PAGE_READWRITE);
    pages.push_back(page);
  }
  void Put(uint32_t address, uint32_t v) {
    Commit(address);
    const uint8_t be[4] = {uint8_t(v >> 24), uint8_t(v >> 16), uint8_t(v >> 8), uint8_t(v)};
    std::memcpy(base + address, be, 4);
  }
  void PutText(uint32_t address, const char* s) {
    Commit(address);
    std::memset(base + address, 0, 16);
    std::memcpy(base + address, s, std::strlen(s));
  }
  bool Readable(uint32_t address, uint32_t size) const {
    for (uint32_t a = address >> 16; a <= (address + size - 1) >> 16; ++a) {
      bool found = false;
      for (uint32_t p : pages) found |= p == a;
      if (!found) return false;
    }
    return true;
  }
};

// The global actor's chain as the live reads show it (E-252); addresses after the Perso are made up.
constexpr uint32_t kBrain = 0x40CB0000, kMind = 0x40CB0100, kModel = 0x40CB0200, kDsgMem = 0x40CB0300,
                   kVars = 0x40CB0400, kInfo = 0x40CB0500, kBuffer = 0x40CB0600;
void GlobalActor(Guest4G& g, uint32_t code) {
  using r3hd_ds::state::kGlobalPerso;
  g.Put(kGlobalPerso + 0xC, kBrain);
  g.Put(kBrain, kMind);
  g.Put(kMind, kModel);
  g.Put(kMind + 0xC, kDsgMem);
  g.Put(kModel + 8, kVars);
  g.Put(kDsgMem, kModel + 8);
  g.Put(kDsgMem + 8, kBuffer);
  g.Put(kVars + 4, kInfo);
  g.Put(kVars + 8, 0x200);
  g.Put(kVars + 0xC, 114u << 24);
  g.Put(kInfo, 0);
  g.Put(kInfo + 4, r3hd_ds::state::kDsgVarInt);
  g.Put(kBuffer, code);
}
void Level(Guest4G& g, uint32_t world, const char* level, uint32_t pause) {
  g.Put(r3hd_ds::state::kWorld, world);
  g.PutText(r3hd_ds::state::kLevelName, level);
  g.Put(r3hd_ds::state::kPause, pause);
}

int g_pass = 0, g_fail = 0;
void Check(const char* name, bool ok) {
  std::printf("%s %s\n", ok ? "ok  " : "FAIL", name);
  (ok ? g_pass : g_fail)++;
}

struct MockPad {
  bool light_custom = false;
  Rgb light;
  Trigger trigger = ClearTrigger();
  int light_writes = 0, trigger_writes = 0, restores = 0;
  bool fail_light = false, fail_trigger = false;
  void Apply(const Output& o, Policy& p) {
    if (o.set_light) {
      if (fail_light) {
        p.FailedLight();
      } else {
        light = o.light, light_custom = !o.restore_light;
        ++(o.restore_light ? restores : light_writes);
      }
    }
    if (o.send_trigger) {
      if (fail_trigger) { p.FailedTrigger(); } else { trigger = o.trigger, ++trigger_writes; }
    }
  }
  bool Resisting() const { return trigger.bytes[0] == 0x01; }
  int Writes() const { return light_writes + trigger_writes + restores; }
};

// Protocol-level model of the pinned SDL 3.5.0 output path for a DualSense (SDL_joystick.c SDL_SetJoystickLED /
// SDL_SetJoystickIDForPlayerIndex, SDL_hidapi_ps5.c SetJoystickLED / SetDevicePlayerIndex / UpdateEffects /
// InternalSendJoystickEffect) and of the device itself, which keeps whatever the last output report commanded.
// MockPad above trusts the policy's intent; this one only believes reports that reach the device (E-255).
uint32_t Crc32(uint32_t crc, const uint8_t* p, size_t n) {
  crc = ~crc;
  while (n--) {
    crc ^= *p++;
    for (int k = 0; k < 8; ++k) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
  }
  return ~crc;
}

struct Ps5Model {
  bool bluetooth = false;
  // SDL_Joystick (SDL_joystick.c): the LED cache that stops SDL_SetJoystickLED from repeating a value for 5 s
  Rgb cache;
  uint32_t led_expiration = 0;
  bool cache_valid = false;
  int sdl_player_index = 0;
  // SDL_DriverPS5_Context
  bool color_set = false;
  Rgb led;
  // the device: what the last reports commanded
  Rgb device_light = {0, 0, 0x40};   // SDL's player 1 colour, sent when SDL entered enhanced mode
  Trigger device_trigger = ClearTrigger();
  std::vector<std::vector<uint8_t>> reports;
  bool malformed = false;

  void Report(const uint8_t* effects47) {
    std::vector<uint8_t> data(bluetooth ? 78 : 48, 0);
    const int offset = bluetooth ? 3 : 1;
    data[0] = bluetooth ? 0x31 : 0x02;
    if (bluetooth) data[1] = 0x00, data[2] = 0x10;
    std::memcpy(&data[offset], effects47, 47);
    if (bluetooth) {
      const uint8_t hdr = 0xA2;
      uint32_t crc = Crc32(0, &hdr, 1);
      crc = Crc32(crc, data.data(), data.size() - 4);
      std::memcpy(&data[data.size() - 4], &crc, 4);
    }
    reports.push_back(data);
    Deliver(data);
  }
  void Deliver(const std::vector<uint8_t>& data) {   // what the DualSense does with one output report
    const bool bt = data[0] == 0x31;
    if ((bt && data.size() != 78) || (!bt && (data[0] != 0x02 || data.size() != 48))) { malformed = true; return; }
    if (bt) {
      const uint8_t hdr = 0xA2;
      uint32_t crc = Crc32(Crc32(0, &hdr, 1), data.data(), data.size() - 4), got;
      std::memcpy(&got, &data[data.size() - 4], 4);
      if (crc != got) { malformed = true; return; }
    }
    const uint8_t* e = &data[bt ? 3 : 1];
    if (e[1] & 0x04) device_light = {e[44], e[45], e[46]};
    if (e[0] & 0x04) std::memcpy(device_trigger.bytes, e + 10, 11);
  }
  void UpdateEffectsLED() {   // UpdateEffects(k_EDS5EffectLED [| k_EDS5EffectPadLights])
    static const Rgb player[7] = {{0, 0, 0x40}, {0x40, 0, 0}, {0, 0x40, 0}, {0x20, 0, 0x20},
                                  {0x20, 0x10, 0}, {0, 0x10, 0x10}, {0x10, 0x10, 0x10}};
    uint8_t e[47] = {};
    e[1] = 0x04;
    const Rgb c = color_set ? led : player[(sdl_player_index < 0 ? 0 : sdl_player_index) % 7];
    e[44] = c.r, e[45] = c.g, e[46] = c.b;
    Report(e);
  }
  bool SetLED(Rgb c, uint32_t now) {   // SDL_SetGamepadLED
    const bool fresh = !cache_valid || !(c == cache);
    if (fresh || now >= led_expiration) {
      color_set = true, led = c;
      UpdateEffectsLED();
      led_expiration = now + 5000;
    }
    cache = c, cache_valid = true;
    return true;
  }
  void SetPlayerIndex(int index) {   // SDL_SetGamepadPlayerIndex
    if (index == sdl_player_index) return;   // "Joystick is already assigned the requested player index"
    sdl_player_index = index;
    UpdateEffectsLED();                      // color_set is NOT cleared: the last SDL_SetGamepadLED colour again
  }
  bool SendEffect(const uint8_t* block, int size) {   // SDL_SendGamepadEffect
    uint8_t e[47] = {};
    std::memcpy(e, block, size < 47 ? size : 47);
    Report(e);
    return true;
  }
};

// What r3hd_ds_sdl.h Apply does with one policy output, against the SDL model (kept in step with that file).
// Before D-105 a restore was SDL_SetGamepadPlayerIndex(pad, own index): in this model (as in SDL) no report at all.
void ApplySdl(Ps5Model& sdl, const Output& o, uint32_t now) {
  if (o.set_light) sdl.SetLED(o.light, now);
  if (o.send_trigger) {
    uint8_t block[47];
    EffectBlock(o.trigger, false, block);  // r3hd_ds_sdl.h: the left side only with the triggers exchanged (D-116)
    sdl.SendEffect(block, sizeof(block));
  }
}

Device Ds() { Device d; d.attached = true, d.dualsense = true; return d; }
// The D-105 checks below run at 100 % strength, which keeps the D-105 force 60 (D-108).
Settings On() { Settings s; s.light = true, s.trigger = true, s.trigger_strength = 100; return s; }
State Play(int world, uint32_t t) { State st; st.focused = true, st.gameplay = true, st.world = world, st.now_ms = t; return st; }

void Run(Policy& p, MockPad& m, const Device& d, const Settings& s, State st, uint32_t from, uint32_t to, uint32_t dt = 16) {
  for (uint32_t t = from; t < to; t += dt) {
    st.now_ms = t;
    m.Apply(p.Step(d, s, st), p);
  }
}

}  // namespace

int main() {
  {  // defaults: both options off -> the pad is never written
    Policy p; MockPad m; Settings s;
    State st = Play(3, 0);
    Run(p, m, Ds(), s, st, 0, 5000);
    Check("defaults off: no output at all", m.Writes() == 0);
  }
  {  // hidden run: never any output, whatever the settings
    Policy p; MockPad m;
    State st = Play(2, 0); st.hidden_run = true; st.power = kVortex;
    Run(p, m, Ds(), On(), st, 0, 5000);
    Check("hidden run: no output", m.Writes() == 0);
  }
  {  // not a DualSense (virtual Xbox pad, Steam Input) -> nothing
    Policy p; MockPad m; Device d = Ds(); d.dualsense = false;
    State st = Play(2, 0);
    Run(p, m, d, On(), st, 0, 2000);
    Check("other pad types: no output", m.Writes() == 0);
  }
  {  // world colour, power priority, brightness, pause and focus restore
    Policy p; MockPad m; Settings s = On(); s.trigger = false;
    Run(p, m, Ds(), s, Play(2, 0), 0, 500);
    Check("world 2: forest green once", m.light_custom && m.light == kWorldColour[2] && m.light_writes == 1);
    State st = Play(2, 0); st.power = kHeavyMetalFist;
    Run(p, m, Ds(), s, st, 500, 1000);
    Check("power beats world: red", m.light == kPowerColour[kHeavyMetalFist] && m.light_writes == 2);
    st.power = kNone;
    Run(p, m, Ds(), s, st, 1000, 1500);
    Check("power ends: back to the world colour", m.light == kWorldColour[2] && m.light_writes == 3);
    State paused = Play(2, 0); paused.gameplay = false;
    Run(p, m, Ds(), s, paused, 1500, 2000);
    Check("pause: idle light written once", !m.light_custom && m.restores == 1 && m.light == IdleLight(0));
    Run(p, m, Ds(), s, Play(7, 0), 2000, 2500);
    State unfocused = Play(7, 0); unfocused.focused = false;
    Run(p, m, Ds(), s, unfocused, 2500, 3000);
    Check("focus loss: idle light", !m.light_custom && m.restores == 2 && m.light == IdleLight(0));
    s.brightness = 50;
    Run(p, m, Ds(), s, Play(5, 0), 3000, 3500);
    Check("brightness 50 %", m.light == Scale(kWorldColour[5], 50) && m.light.r == 127);
    State menu = Play(0, 0);
    Run(p, m, Ds(), s, menu, 3500, 4000);
    Check("no world number (front end): default", !m.light_custom);
  }
  {  // trigger (D-105): armed for the whole of focused gameplay, before R2 moves; no write per R2 press
    Policy p; MockPad m; Settings s = On(); s.light = false;
    State menu = Play(4, 0); menu.gameplay = false;
    Run(p, m, Ds(), s, menu, 0, 100);
    Check("option on in the front end: one clean-start clear", m.trigger_writes == 1 && !m.Resisting());
    State st = Play(4, 0);
    Run(p, m, Ds(), s, st, 100, 10100);
    Check("gameplay: resistance armed at once, written once in 10 s", m.Resisting() && m.trigger_writes == 2);
    Check("gentle default force, start before the lock-on threshold (30)",
          m.trigger.bytes[1] == 20 && m.trigger.bytes[2] == 60 && m.trigger.bytes[1] < 30);
    Check("constant resistance only (mode 0x01, no vibrating mode, other bytes 0)", [&] {
      bool zero = true;
      for (int i = 3; i < 11; ++i) zero &= m.trigger.bytes[i] == 0;
      return m.trigger.bytes[0] == 0x01 && zero;
    }());
    Policy q; MockPad n;
    Run(q, n, Ds(), s, st, 0, 50);
    Check("option on straight into gameplay: resistance is the first write", n.Resisting() && n.trigger_writes == 1);
    State paused = st; paused.gameplay = false;
    Run(p, m, Ds(), s, paused, 11000, 11200);
    Check("pause: cleared", !m.Resisting() && m.trigger_writes == 3);
    Run(p, m, Ds(), s, st, 11200, 11600);
    Check("resume: armed again", m.Resisting() && m.trigger_writes == 4);
    State unfocused = st; unfocused.focused = false;
    Run(p, m, Ds(), s, unfocused, 11600, 11800);
    Check("focus loss: cleared", !m.Resisting());
    Run(p, m, Ds(), s, st, 11800, 12200);
    Settings off = s; off.trigger = false;
    Run(p, m, Ds(), off, st, 12200, 12400);
    Check("option switched off in gameplay: cleared", !m.Resisting());
  }
  {  // trigger strength (D-108): only the force byte scales; 0 % arms nothing and clears what is there
    Settings s = On(); s.light = false;
    Check("default strength is 30 %", Settings{}.trigger_strength == 30);
    auto at = [&](int pct) { Settings x = s; x.trigger_strength = static_cast<uint8_t>(pct); return TriggerForce(x); };
    Check("force: 100 % = 60 (D-105 maximum kept), 30 % = 18, 50 % = 30, 1 % = 1, 0 % = 0",
          at(100) == 60 && at(30) == 18 && at(50) == 30 && at(1) == 1 && at(0) == 0);
    bool monotonic = true, bounded = true;
    for (int pct = 1; pct <= 100; ++pct) monotonic &= at(pct) >= at(pct - 1), bounded &= at(pct) >= 1 && at(pct) <= 60;
    Check("force grows with the strength and stays within 1..60 for 1..100 %", monotonic && bounded);
    Check("a strength above 100 is read as 100", at(200) == 60);
    for (int pct : {30, 100}) {
      Policy p; MockPad m; Settings x = s; x.trigger_strength = static_cast<uint8_t>(pct);
      Run(p, m, Ds(), x, Play(4, 0), 0, 2000);
      Check(pct == 30 ? "30 %: resistance armed once, start 20 unchanged, force 18"
                      : "100 %: resistance armed once, start 20 unchanged, force 60",
            m.Resisting() && m.trigger_writes == 1 && m.trigger.bytes[1] == 20 &&
            m.trigger.bytes[2] == (pct == 30 ? 18 : 60));
    }
    {
      Policy p; MockPad m; Settings zero = s; zero.trigger_strength = 0;
      m.trigger = Resistance(20, 60);   // an effect left on the pad (another program, an earlier crash)
      Run(p, m, Ds(), zero, Play(4, 0), 0, 5000);
      Check("0 %: the option on still writes one clear, the pad holds no resistance", !m.Resisting() &&
            m.trigger_writes == 1 && m.trigger == ClearTrigger());
      State paused = Play(4, 0); paused.gameplay = false;
      Run(p, m, Ds(), zero, paused, 5000, 5200);
      Run(p, m, Ds(), zero, Play(4, 0), 5200, 5400);
      const Output r = p.Release(0);
      Check("0 %: pause, resume and release send nothing more", m.trigger_writes == 1 && !r.send_trigger);
    }
    {
      Policy p; MockPad m; Settings x = s;
      Run(p, m, Ds(), x, Play(4, 0), 0, 500);
      x.trigger_strength = 75;
      Run(p, m, Ds(), x, Play(4, 0), 500, 1000);
      Check("a changed strength while armed: the new force once (45)", m.trigger_writes == 2 && m.trigger.bytes[2] == 45);
      x.trigger_strength = 0;
      Run(p, m, Ds(), x, Play(4, 0), 1000, 1500);
      Check("changed to 0 % while armed: cleared once", m.trigger_writes == 3 && !m.Resisting());
    }
    for (bool bt : {false, true}) {
      for (int pct : {0, 30, 100}) {
        Policy p; Ps5Model sdl; sdl.bluetooth = bt;
        sdl.device_trigger = Resistance(20, 60);
        Settings x = s; x.trigger_strength = static_cast<uint8_t>(pct);
        uint32_t t = 0;
        for (; t < 1000; t += 16) ApplySdl(sdl, p.Step(Ds(), x, Play(2, t)), t);
        const bool armed = sdl.device_trigger.bytes[0] == 0x01;
        const bool ok = pct == 0 ? sdl.device_trigger == ClearTrigger()
                                 : armed && sdl.device_trigger.bytes[1] == 20 &&
                                       sdl.device_trigger.bytes[2] == (pct == 30 ? 18 : 60);
        ApplySdl(sdl, p.Release(0), t);
        char name[96];
        std::snprintf(name, sizeof name, "SDL model %s %d %%: device force as wanted, cleared at release, one report",
                      bt ? "Bluetooth" : "USB", pct);
        Check(name, ok && !sdl.malformed && sdl.device_trigger == ClearTrigger() && sdl.reports.size() == (pct ? 2u : 1u));
      }
    }
    Check("strength setting parse: plain 0..100 kept, anything else falls back", [] {
      const char* name = "R3HD_DS_TRIGGER_STRENGTH_TEST";
      auto with = [&](const char* v) { _putenv_s(name, v); return r3hd_ds::state::Percent(name, 30); };
      const bool ok = with("0") == 0 && with("30") == 30 && with("100") == 100 && with("7") == 7 && with("101") == 30 &&
                      with("-5") == 30 && with("50%") == 30 && with("abc") == 30 && with("0100") == 30 && with("") == 30;
      _putenv_s(name, "");
      return ok && r3hd_ds::state::Percent("R3HD_DS_TRIGGER_STRENGTH_UNSET", 30) == 30;
    }());
  }
  {  // disconnect and reattach, shutdown
    Policy p; MockPad m; Settings s = On();
    State st = Play(8, 0);
    Run(p, m, Ds(), s, st, 0, 1000);
    const int before = m.Writes();
    Device gone; gone.attached = false;
    Run(p, m, gone, s, st, 1000, 1500);
    Check("disconnect: nothing sent", m.Writes() == before);
    MockPad fresh;   // a reattached pad starts from its own power-on state
    Run(p, fresh, Ds(), s, st, 1500, 1520);
    Check("reattach: state forgotten, a defined first trigger write", fresh.trigger_writes == 1 &&
                                                                        fresh.light_writes == 1);
    Run(p, fresh, Ds(), s, st, 1520, 2500);
    Check("reattach: light and resistance again", fresh.Resisting() && fresh.light == kWorldColour[8]);
    fresh.Apply(p.Release(0), p);
    Check("shutdown: idle light written and trigger cleared", !fresh.Resisting() && !fresh.light_custom &&
                                                                  fresh.light == IdleLight(0));
    const int after = fresh.Writes();
    fresh.Apply(p.Release(0), p);
    Check("second release sends nothing", fresh.Writes() == after);
  }
  {  // a remapper appears: undo our own effects once, then stay away
    Policy p; MockPad m; Settings s = On();
    State st = Play(6, 0);
    Run(p, m, Ds(), s, st, 0, 1000);
    Device d = Ds(); d.remapper_suspected = true;
    Run(p, m, d, s, st, 1000, 3000);
    Check("remapper: own effects undone", !m.Resisting() && !m.light_custom);
    const int w = m.Writes();
    Run(p, m, d, s, st, 3000, 6000);
    Check("remapper: then no further output", m.Writes() == w);
  }
  {  // independence: a failed light does not stop the trigger, and the reverse
    Policy p; MockPad m; m.fail_light = true;
    State st = Play(1, 0);
    Run(p, m, Ds(), On(), st, 0, 1000);
    Check("light unsupported: trigger still works", m.Resisting() && !m.light_custom);
    Policy q; MockPad n; n.fail_trigger = true;
    Run(q, n, Ds(), On(), st, 0, 1000);
    Check("trigger unsupported: light still works", n.light_custom && !n.Resisting() && !q.TriggerOn());
    const int w = n.trigger_writes;
    Run(q, n, Ds(), On(), st, 1000, 3000);
    Check("trigger unsupported: no retries", n.trigger_writes == w);
  }
  {  // stress: rapid pause / resume and world changes: one write per edge, never per frame
    Policy p; MockPad m; Settings s = On();
    State st = Play(1, 0);
    uint32_t t = 0;
    int edges = 0;
    bool was = true;
    srand(7);
    for (int i = 0; i < 2000; ++i, t += 16) {
      st.gameplay = (rand() % 10) < 6;
      if (i % 300 == 0) st.world = 1 + (i / 300) % 9, ++edges;
      edges += st.gameplay != was, was = st.gameplay;
      st.now_ms = t;
      m.Apply(p.Step(Ds(), s, st), p);
    }
    Check("stress: at most one light and one trigger write per edge", m.Writes() <= 2 * edges + 2);
    m.Apply(p.Release(0), p);
    Check("stress: release leaves a clean pad", !m.Resisting() && !m.light_custom);
  }
  {  // guest facts -> gameplay / world (r3hd_ds_state.h)
    using r3hd_ds::state::Decide;
    Check("level of a world, not paused: gameplay",
          Decide(3, "swamp_60", 0).gameplay && Decide(3, "swamp_60", 0).world == 3);
    Check("pause word set: not gameplay, world kept",
          !Decide(3, "swamp_60", 1).gameplay && Decide(3, "swamp_60", 1).world == 3);
    Check("front end, credits, end hub: not gameplay",
          !Decide(1, "menumap", 0).gameplay && !Decide(1, "MenuMap", 0).gameplay && !Decide(9, "staff", 0).gameplay &&
              !Decide(9, "endgame", 0).gameplay);
    Check("world 0 or out of range: no world", !Decide(0, "wood_11", 0).gameplay && Decide(12, "wood_11", 0).world == 0);
    Check("empty level name: not gameplay", !Decide(2, "", 0).gameplay);
    uint8_t mem[0x10] = {0x00, 0x00, 0x00, 0x07};
    Check("guest words are big-endian", r3hd_ds::state::LoadBE(mem, 0) == 7);
  }
  {  // D-104: the title's power code -> power -> light bar colour
    using r3hd_ds::state::PowerFromCode;
    Check("codes 0..4 = Vortex, Throttle Copter, LockJaw, Shock Rocket, Heavy Metal Fist; 5 = none",
          PowerFromCode(0) == kVortex && PowerFromCode(1) == kThrottleCopter && PowerFromCode(2) == kLockJaw &&
              PowerFromCode(3) == kShockRocket && PowerFromCode(4) == kHeavyMetalFist && PowerFromCode(5) == kNone);
    Check("codes the title never writes: none", PowerFromCode(-1) == kNone && PowerFromCode(6) == kNone &&
                                                    PowerFromCode(15) == kNone);
    const Rgb want[5] = {{30, 230, 60}, {255, 215, 0}, {20, 80, 255}, {255, 110, 0}, {255, 25, 15}};
    bool all = true;
    for (int code = 0; code < 5; ++code) {
      Policy p; MockPad m; Settings s = On(); s.trigger = false;
      State st = Play(3, 0); st.power = PowerFromCode(code);
      Run(p, m, Ds(), s, st, 0, 200);
      all &= m.light_custom && m.light == want[code] && m.light_writes == 1;
    }
    Check("each power: green / yellow / blue / orange / red, once", all);
    using r3hd_ds::state::Decide;
    Check("power counts in gameplay", Decide(4, "menu_20", 0, 3).power == kShockRocket);
    Check("paused: no power", Decide(4, "menu_20", 1, 3).power == kNone && Decide(4, "menu_20", 1, 3).world == 4);
    Check("front end / credits: no power", Decide(1, "menumap", 0, 4).power == kNone &&
                                               Decide(9, "staff", 0, 2).power == kNone);
    Check("code 5 or unread: no power", Decide(5, "knaar_60", 0, 5).power == kNone &&
                                            Decide(5, "knaar_60", 0).power == kNone &&
                                            Decide(5, "knaar_60", 0, 9).power == kNone);
  }
  {  // D-104: the read itself, through a fake guest address space
    Guest4G g;
    Check("guest test space reserved", g.base != nullptr);
    if (g.base) {
      int calls = 0;
      auto readable = [&](uint32_t a, uint32_t n) { ++calls; return g.Readable(a, n); };
      int step = -1;
      Check("nothing committed: unread at step 1",
            r3hd_ds::state::ReadPowerCode(g.base, readable, &step) == r3hd_ds::state::kPowerCodeUnread && step == 1);
      GlobalActor(g, 5);
      Check("global actor, no power: 5", r3hd_ds::state::ReadPowerCode(g.base, readable, &step) == 5 && step == 0);
      g.Put(kBuffer, 4);
      Check("Heavy Metal Fist: 4", r3hd_ds::state::ReadPowerCode(g.base, readable) == 4);
      g.Put(kDsgMem, kModel + 12);
      Check("DsgMem not naming the model's variables: step 2",
            r3hd_ds::state::ReadPowerCode(g.base, readable, &step) == r3hd_ds::state::kPowerCodeUnread && step == 2);
      g.Put(kDsgMem, kModel + 8);
      g.Put(kInfo + 4, 7);
      Check("first variable not an Int: step 4",
            r3hd_ds::state::ReadPowerCode(g.base, readable, &step) == r3hd_ds::state::kPowerCodeUnread && step == 4);
      g.Put(kInfo + 4, r3hd_ds::state::kDsgVarInt);
      g.Put(kBuffer, 9);
      Check("value outside 0..5: step 6",
            r3hd_ds::state::ReadPowerCode(g.base, readable, &step) == r3hd_ds::state::kPowerCodeUnread && step == 6);
      g.Put(kMind + 0xC, 0x41000000);   // a DsgMem on a page nobody committed
      Check("pointer into an uncommitted page: refused before reading (step 2, its first use)",
            r3hd_ds::state::ReadPowerCode(g.base, readable, &step) == r3hd_ds::state::kPowerCodeUnread && step == 2);
      g.Put(kMind + 0xC, kDsgMem);

      // VdSwap sequence -> what the SDL side reads -> the light bar: pickup, expiry, pause, death reload, level change
      Policy p; MockPad m; Settings s = On(); s.trigger = false;
      auto frame = [&](uint32_t t) {
        r3hd_ds::state::Swap(g.base, true, readable);
        const auto gs = r3hd_ds::state::Read();
        State st = Play(gs.world, t); st.gameplay = gs.gameplay; st.power = gs.power;
        m.Apply(p.Step(Ds(), s, st), p);
      };
      Level(g, 4, "menu_20", 0);
      GlobalActor(g, 5);
      frame(0);
      Check("swap: world colour without a power", m.light == kWorldColour[4] && m.light_writes == 1);
      g.Put(kBuffer, 3);
      frame(16);
      Check("swap: Shock Rocket pickup -> orange", m.light == kPowerColour[kShockRocket] && m.light_writes == 2);
      g.Put(kBuffer, 5);
      frame(32);
      Check("swap: expiry (code 5) -> world colour again", m.light == kWorldColour[4] && m.light_writes == 3);
      g.Put(kBuffer, 4);
      frame(48);
      Level(g, 4, "menu_20", 1);
      const int before = calls;
      frame(64);
      Check("swap: pause -> default light, power not even read", !m.light_custom && calls == before &&
                                                                     r3hd_ds::state::Read().power == kNone);
      Level(g, 4, "menu_20", 0);
      frame(80);
      Check("swap: resume with the power still held -> red", m.light == kPowerColour[kHeavyMetalFist]);
      g.Put(kBuffer, 5);   // the player's init macro at the death reload writes 5
      frame(96);
      Check("swap: death reload -> world colour", m.light == kWorldColour[4]);
      g.Put(kBuffer, 2);
      frame(112);
      Level(g, 1, "menumap", 0);   // back to the front end with a LockJaw code left in memory
      frame(128);
      Check("swap: front end with a stale code -> default light", !m.light_custom &&
                                                                      r3hd_ds::state::Read().power == kNone);
      Level(g, 5, "knaar_10", 0);
      g.Put(kBuffer, 5);
      frame(144);
      Check("swap: next level -> its world colour", m.light == kWorldColour[5]);
      g.Put(kBuffer, 1);
      g.Put(kVars + 0xC, 0);   // the structure stops checking out (a level being replaced): no colour from it
      frame(160);
      Check("swap: structure fails -> world colour, step logged", m.light == kWorldColour[5] &&
                                                                      r3hd_ds::state::Read().power_step == 3);
      g.Put(kVars + 0xC, 114u << 24);
      const int quiet = calls;
      r3hd_ds::state::Swap(g.base, false, readable);
      Check("light bar off: the power is never read", calls == quiet && r3hd_ds::state::Read().power == kNone);
    }
  }
  // E-255: the real-hardware report (USB and Bluetooth alike) through the SDL 3.5.0 model; only device state counts.
  for (const bool bt : {false, true}) {
    const char* tag = bt ? "bluetooth" : "usb";
    char name[200];
    auto check = [&](const char* what, bool ok) { std::snprintf(name, sizeof(name), "%s: %s", tag, what); Check(name, ok); };
    auto light_only = [](const std::vector<uint8_t>& r) { const uint8_t* e = &r[r[0] == 0x31 ? 3 : 1]; return e[0] == 0 && e[1] == 0x04; };
    auto trigger_only = [](const std::vector<uint8_t>& r) { const uint8_t* e = &r[r[0] == 0x31 ? 3 : 1]; return e[0] == 0x04 && e[1] == 0; };
    {
      Policy p; Ps5Model sdl; sdl.bluetooth = bt;
      const Rgb idle = sdl.device_light;   // the colour the pad shows in this game with both options off
      Settings s = On();
      uint32_t t = 0;
      auto run = [&](State st, uint32_t ms) {
        for (uint32_t end = t + ms; t < end; t += 16) { st.now_ms = t; ApplySdl(sdl, p.Step(Ds(), s, st), t); }
      };
      State play = Play(3, 0);
      run(play, 300);
      check("gameplay: world colour on the device", sdl.device_light == kWorldColour[3]);
      check("gameplay: R2 resistance armed before R2 is pressed (right trigger 0)",
            sdl.device_trigger.bytes[0] == 0x01);
      State power = play; power.power = kShockRocket;
      run(power, 300);
      check("power-up: its colour on the device", sdl.device_light == kPowerColour[kShockRocket]);
      run(play, 300);
      check("power-up ends: world colour again", sdl.device_light == kWorldColour[3]);
      State paused = play; paused.gameplay = false;
      size_t before = sdl.reports.size();
      run(paused, 300);
      check("pause: an LED report reaches the device", sdl.reports.size() > before);
      check("pause: the device no longer shows the game colour", !(sdl.device_light == kWorldColour[3]));
      check("pause: the device shows the idle colour", sdl.device_light == idle);
      check("pause: no resistance", sdl.device_trigger.bytes[0] == 0x05);
      check("pause: two reports, then quiet", sdl.reports.size() == before + 2);
      run(play, 300);
      check("resume: world colour and resistance again", sdl.device_light == kWorldColour[3] &&
                                                           sdl.device_trigger.bytes[0] == 0x01);
      ApplySdl(sdl, p.Release(0), t);   // OnLostFocus (Alt+Tab): WindowFocus false, then ReleaseAll
      State away = play; away.focused = false;
      before = sdl.reports.size();
      run(away, 2000);
      check("focus loss: the device shows the idle colour", sdl.device_light == idle);
      check("focus loss: no resistance", sdl.device_trigger.bytes[0] == 0x05);
      check("focus loss: no report while away (no polling traffic)", sdl.reports.size() == before);
      run(play, 300);
      check("refocus: world colour and resistance again", sdl.device_light == kWorldColour[3] &&
                                                            sdl.device_trigger.bytes[0] == 0x01);
      State front = Play(1, 0); front.gameplay = false;   // main menu
      run(front, 300);
      check("main menu: idle colour, no resistance", sdl.device_light == idle && sdl.device_trigger.bytes[0] == 0x05);
      run(play, 300);
      before = sdl.reports.size();
      ApplySdl(sdl, p.Release(0), t);   // window close: focus loss, then the hard exit
      check("exit: reports issued before the process ends", sdl.reports.size() == before + 2);
      check("exit: the device shows the idle colour", sdl.device_light == idle);
      check("exit: no resistance", sdl.device_trigger.bytes[0] == 0x05);
      ApplySdl(sdl, p.Release(0), t);   // OnClosing after the focus loss: nothing left to send
      check("exit: second release sends nothing", sdl.reports.size() == before + 2);
      bool shapes = true;
      for (const auto& r : sdl.reports) shapes &= light_only(r) || trigger_only(r);
      check("light reports touch only the LED, trigger reports only R2 (rumble / audio bits never set)", shapes);
      check("every report well-formed (id, size, CRC on Bluetooth)", !sdl.malformed);
    }
    {  // each option off on its own
      Policy p; Ps5Model sdl; sdl.bluetooth = bt;
      const Rgb idle = sdl.device_light;
      Settings s = On();
      uint32_t t = 0;
      auto run = [&](const Settings& v, State st, uint32_t ms) {
        for (uint32_t end = t + ms; t < end; t += 16) { st.now_ms = t; ApplySdl(sdl, p.Step(Ds(), v, st), t); }
      };
      run(s, Play(5, 0), 300);
      Settings no_light = s; no_light.light = false;
      run(no_light, Play(5, 0), 300);
      check("light switched off: idle colour, resistance kept", sdl.device_light == idle &&
                                                                  sdl.device_trigger.bytes[0] == 0x01);
      run(s, Play(5, 0), 300);
      Settings no_trigger = s; no_trigger.trigger = false;
      run(no_trigger, Play(5, 0), 300);
      check("trigger switched off: cleared, light kept", sdl.device_trigger.bytes[0] == 0x05 &&
                                                           sdl.device_light == kWorldColour[5]);
      Settings none;
      size_t before = sdl.reports.size();
      run(none, Play(5, 0), 300);
      check("both off: one LED write gives the light back", sdl.device_light == idle &&
                                                              sdl.reports.size() == before + 1);
    }
    {  // disconnect / reconnect: the driver makes a new PadOutput, SDL a new context; nothing stale is inherited
      Policy p; Ps5Model sdl; sdl.bluetooth = bt;
      uint32_t t = 0;
      for (; t < 300; t += 16) ApplySdl(sdl, p.Step(Ds(), On(), Play(8, t)), t);
      Device gone; gone.attached = false;
      const size_t before = sdl.reports.size();
      for (; t < 600; t += 16) ApplySdl(sdl, p.Step(gone, On(), Play(8, t)), t);
      check("disconnect: nothing sent", sdl.reports.size() == before);
      Ps5Model again; again.bluetooth = bt;   // the pad lost its effects with its power / link
      State paused = Play(8, 0); paused.gameplay = false;
      for (; t < 900; t += 16) { paused.now_ms = t; ApplySdl(again, p.Step(Ds(), On(), paused), t); }
      check("reconnect in the pause: a defined clear, no stale light or resistance",
            again.device_trigger.bytes[0] == 0x05 && again.device_light == IdleLight(0) && again.reports.size() == 1);
      for (; t < 1200; t += 16) ApplySdl(again, p.Step(Ds(), On(), Play(8, t)), t);
      check("reconnect, back in play: world colour and resistance", again.device_light == kWorldColour[8] &&
                                                                       again.device_trigger.bytes[0] == 0x01);
    }
    {  // ownership: a remapper or virtual pad beside it, a pad that is not a DualSense
      Policy p; Ps5Model sdl; sdl.bluetooth = bt;
      uint32_t t = 0;
      for (; t < 300; t += 16) ApplySdl(sdl, p.Step(Ds(), On(), Play(6, t)), t);
      Device d = Ds(); d.remapper_suspected = true;
      for (; t < 600; t += 16) ApplySdl(sdl, p.Step(d, On(), Play(6, t)), t);
      check("remapper appears: own light and resistance undone on the device",
            sdl.device_light == IdleLight(0) && sdl.device_trigger.bytes[0] == 0x05);
      const size_t w = sdl.reports.size();
      for (; t < 3000; t += 16) ApplySdl(sdl, p.Step(d, On(), Play(6, t)), t);
      check("remapper: then no report at all", sdl.reports.size() == w);
      Policy q; Ps5Model other; other.bluetooth = bt;
      Device xbox = Ds(); xbox.dualsense = false;
      for (t = 0; t < 2000; t += 16) ApplySdl(other, q.Step(xbox, On(), Play(6, t)), t);
      ApplySdl(other, q.Release(0), t);
      check("not a DualSense: no report, not even at release", other.reports.empty());
    }
    {  // SDL renumbers the pads after another one left
      Policy p; Ps5Model sdl; sdl.bluetooth = bt; sdl.sdl_player_index = 1;
      uint32_t t = 0;
      for (; t < 300; t += 16) ApplySdl(sdl, p.Step(Ds(), On(), [&] { State st = Play(4, t); st.player_index = 1; return st; }()), t);
      sdl.SetPlayerIndex(0);
      ApplySdl(sdl, p.Renumbered(0), t);
      check("renumbered in play: SDL repeats the world colour, nothing else sent", sdl.device_light == kWorldColour[4]);
      State paused = Play(4, t); paused.gameplay = false;
      for (; t < 600; t += 16) { paused.now_ms = t; ApplySdl(sdl, p.Step(Ds(), On(), paused), t); }
      check("then paused: player 1 idle colour", sdl.device_light == IdleLight(0));
      Policy q; Ps5Model two; two.bluetooth = bt; two.sdl_player_index = 1;
      State st = Play(4, 0); st.player_index = 1;
      for (t = 0; t < 300; t += 16) { st.now_ms = t; ApplySdl(two, q.Step(Ds(), On(), st), t); }   // world colour
      st.gameplay = false;
      for (; t < 600; t += 16) { st.now_ms = t; ApplySdl(two, q.Step(Ds(), On(), st), t); }
      check("pad 1 paused: its own idle colour (red)", two.device_light == IdleLight(1));
      two.SetPlayerIndex(0);
      check("renumbered while idle: SDL repeats the stale colour", two.device_light == IdleLight(1));
      ApplySdl(two, q.Renumbered(0), t);
      check("renumbered while idle: the new index's idle colour is written", two.device_light == IdleLight(0));
      const size_t n = two.reports.size();
      ApplySdl(two, q.Renumbered(0), t);
      check("renumbered twice: nothing more", two.reports.size() == n);
    }
  }
  {  // D-116: the effect block of either trigger (SDL 3.5.0 DS5EffectsState: R2 bytes at 10, L2 bytes at 21)
    const Trigger t = Resistance(20, 18);
    uint8_t r[47], l[47];
    EffectBlock(t, false, r);
    EffectBlock(t, true, l);
    bool rOnly = r[0] == 0x04 && std::memcmp(r + 10, t.bytes, 11) == 0, lOnly = l[0] == 0x08 && std::memcmp(l + 21, t.bytes, 11) == 0;
    for (int i = 1; i < 47; ++i) {
      if ((i < 10 || i >= 21) && r[i]) rOnly = false;
      if ((i < 21 || i >= 32) && l[i]) lOnly = false;
    }
    Check("trigger block: R2 only (enable 0x04, bytes 10..20), nothing else", rOnly);
    Check("trigger block, triggers exchanged: L2 only (enable 0x08, bytes 21..31), nothing else", lOnly);
    uint8_t c[47];
    EffectBlock(ClearTrigger(), true, c);
    Check("trigger block: a clear goes to the same side", c[0] == 0x08 && c[21] == 0x05 && c[10] == 0);
  }
  std::printf("R3HD_DUALSENSE_TEST %s %d/%d\n", g_fail ? "FAIL" : "PASS", g_pass, g_pass + g_fail);
  return g_fail ? 1 : 0;
}
