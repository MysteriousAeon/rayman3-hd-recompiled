// Regression for tools/r3hd_padmap.h (D-115). No SDK, no device, no game: the map is driven with button states and
// keystroke virtual keys as the SDK's InputSystem hands them over, and a model of InputSystem::GetState (physical pads
// mapped, synthetic devices not, then the OR merge of state_merge.cpp). Ends with R3HD_PADMAP_TEST PASS n/n.
#include <algorithm>
#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>

#include "r3hd_padmap.h"

using namespace r3hd_padmap;

namespace {

int g_pass = 0, g_fail = 0;

void check(const char* what, bool ok) {
  if (ok) {
    ++g_pass;
  } else {
    ++g_fail;
    std::printf("FAIL %s\n", what);
  }
}

uint16_t Bit(const char* name) { return kTable[IndexOf(name, std::strlen(name))].bit; }
uint16_t Vk(const char* name) { return kTable[IndexOf(name, std::strlen(name))].vk; }

// InputSystem::GetState for one guest user: every device's state, physical ones through the map, merged by OR.
struct Device {
  bool synthetic;
  uint16_t buttons;
};
uint16_t Merged(const Map& m, const std::vector<Device>& devices) {
  uint16_t out = 0;
  for (const auto& d : devices) out |= d.synthetic ? d.buttons : m.Apply(d.buttons);
  return out;
}

// The SDL driver's keystroke algorithm reduced to what the map sees: the virtual key of every button that changed
// between two physical states (down or up). Mapped one for one, it must name exactly the guest buttons that changed.
std::vector<uint16_t> Changed(uint16_t before, uint16_t after) {
  std::vector<uint16_t> vks;
  for (const auto& b : kTable)
    if ((before ^ after) & b.bit) vks.push_back(b.vk);
  return vks;
}

}  // namespace

int main() {
  // Table: 14 distinct buttons, bits and virtual keys; the mask is their union.
  {
    uint16_t bits = 0;
    bool distinct = true;
    for (int i = 0; i < kButtons; ++i) {
      if (bits & kTable[i].bit) distinct = false;
      bits |= kTable[i].bit;
      for (int j = i + 1; j < kButtons; ++j) distinct &= kTable[i].vk != kTable[j].vk;
    }
    check("table: 14 distinct bits and virtual keys", distinct && bits == kMapped);
    check("table: Guide and 0x0800 are not mapped", (kMapped & 0x0400) == 0 && (kMapped & 0x0800) == 0);
  }

  // Default: absent, empty and an explicit identity are the original controls, unchanged bit for bit.
  for (const char* text : {static_cast<const char*>(nullptr), "", "a=a", "a=a,b=b,start=start"}) {
    Map m = Map::Parse(text);
    bool same = m.state() == State::kDefault && m.text().empty();
    for (uint32_t s = 0; s <= 0xFFFF; s += 7) same &= m.Apply(uint16_t(s)) == uint16_t(s);
    for (const auto& b : kTable) same &= m.MapKey(b.vk) == b.vk;
    check(text ? (std::string("default: '") + text + "'").c_str() : "default: absent", same);
  }

  // A swap of A and B (a DualSense's Cross and Circle are the same SDL buttons).
  {
    Map m = Map::Parse("a=b,b=a");
    check("swap: custom", m.state() == State::kCustom && m.text() == "a=b,b=a");
    check("swap: physical B gives guest A", m.Apply(Bit("b")) == Bit("a"));
    check("swap: physical A gives guest B", m.Apply(Bit("a")) == Bit("b"));
    check("swap: both held give both", m.Apply(Bit("a") | Bit("b")) == (Bit("a") | Bit("b")));
    check("swap: other buttons unchanged", m.Apply(Bit("x") | Bit("start")) == (Bit("x") | Bit("start")));
    check("swap: Guide passes", m.Apply(0x0400 | Bit("a")) == (0x0400 | Bit("b")));
    check("swap: nothing held is nothing", m.Apply(0) == 0);
    check("swap: keystroke B -> A, A -> B", m.MapKey(Vk("b")) == Vk("a") && m.MapKey(Vk("a")) == Vk("b"));
    check("swap: trigger and stick keys unchanged",
          m.MapKey(0x5806) == 0x5806 && m.MapKey(0x5807) == 0x5807 && m.MapKey(0x5820) == 0x5820);
  }

  // A three-way rotation, written in any order: the effect is the bijection, its text is canonical.
  {
    Map m = Map::Parse("x=y,a=x,y=a");
    check("rotation: custom, canonical text", m.state() == State::kCustom && m.text() == "a=x,x=y,y=a");
    check("rotation: X -> A, Y -> X, A -> Y",
          m.Apply(Bit("x")) == Bit("a") && m.Apply(Bit("y")) == Bit("x") && m.Apply(Bit("a")) == Bit("y"));
  }

  // Every single-button state of every transposition: one physical press is one guest press.
  {
    bool ok = true;
    for (int i = 0; i < kButtons; ++i)
      for (int j = 0; j < kButtons; ++j) {
        if (i == j) continue;
        std::string text = std::string(kTable[i].name) + "=" + kTable[j].name + "," + kTable[j].name + "=" + kTable[i].name;
        Map m = Map::Parse(text.c_str());
        ok &= m.state() == State::kCustom;
        for (int k = 0; k < kButtons; ++k) {
          int guest = k == j ? i : k == i ? j : k;
          ok &= m.Apply(kTable[k].bit) == kTable[guest].bit;
          ok &= m.MapKey(kTable[k].vk) == kTable[guest].vk;
        }
      }
    check("all 182 transpositions: one press -> one press, state and keystroke agree", ok);
  }

  // Keystrokes and state agree for any change: the mapped virtual keys of what changed physically are exactly the
  // virtual keys of what changed for the guest.
  {
    Map m = Map::Parse("a=b,b=a,x=dpad_up,dpad_up=x,start=back,back=start");
    bool ok = true;
    uint16_t prev = 0;
    uint32_t seed = 12345;
    for (int n = 0; n < 5000; ++n) {
      seed = seed * 1103515245u + 12345u;
      uint16_t next = uint16_t(seed >> 8) & kMapped;
      std::vector<uint16_t> physical = Changed(prev, next), guest = Changed(m.Apply(prev), m.Apply(next));
      std::vector<uint16_t> mapped;
      for (uint16_t vk : physical) mapped.push_back(m.MapKey(vk));
      std::sort(mapped.begin(), mapped.end());
      std::sort(guest.begin(), guest.end());
      ok &= mapped == guest;
      prev = next;
    }
    check("keystrokes match state changes (5000 random states)", ok);
  }

  // Invalid values: not used at all (the original controls), with a reason.
  for (const char* text : {"a=b", "a=b,b=a,a=x", "a=q,q=a", "jump=b", "a", "a=b,,b=a", "a=b,b=a,", "=a", "A=B,B=A",
                           "a=b ,b=a", "left_trigger=a,a=left_trigger"}) {
    Map m = Map::Parse(text);
    bool same = m.state() == State::kInvalid && m.text().empty() && !m.error().empty();
    for (uint32_t s = 0; s <= 0xFFFF; s += 13) same &= m.Apply(uint16_t(s)) == uint16_t(s);
    check((std::string("invalid -> original controls: '") + text + "'").c_str(), same);
  }

  // Keyboard and pad together (InputSystem::GetState): the keyboard device is synthetic and keeps its own map.
  {
    Map m = Map::Parse("a=b,b=a");
    check("coexist: keyboard Jump (A) stays A while the pad is mapped",
          Merged(m, {{true, Bit("a")}, {false, 0}}) == Bit("a"));
    check("coexist: pad Circle (B) is guest A", Merged(m, {{true, 0}, {false, Bit("b")}}) == Bit("a"));
    check("coexist: keyboard B + pad B = guest B and A",
          Merged(m, {{true, Bit("b")}, {false, Bit("b")}}) == (Bit("a") | Bit("b")));
    check("coexist: two pads, both mapped", Merged(m, {{false, Bit("a")}, {false, Bit("b")}}) == (Bit("a") | Bit("b")));
    check("coexist: NOP device (synthetic, idle) adds nothing", Merged(m, {{true, 0}, {false, Bit("x")}}) == Bit("x"));
  }

  // Disconnect / reconnect: the map holds no state. A pad unplugged while a button is held reports nothing held (the
  // driver forgets it); the same pad plugged in again (a new device for the SDK) maps exactly as before.
  {
    Map m = Map::Parse("a=y,y=a");
    uint16_t before = m.Apply(Bit("y"));
    uint16_t gone = Merged(m, {{true, 0}});  // only the keyboard is left
    uint16_t back = Merged(m, {{true, 0}, {false, Bit("y")}});
    check("reconnect: held button releases, the new device maps the same", before == Bit("a") && gone == 0 && back == before);
    check("reconnect: the process map is read once", &Get() == &Get());
  }

  // D-116: the analog exchanges. Values move whole (full range, no threshold); a button never takes an analog input.
  {
    auto analog = [](const Map& m, uint8_t lt, uint8_t rt, int16_t lx, int16_t ly, int16_t rx, int16_t ry) {
      m.ApplyAnalog(lt, rt, lx, ly, rx, ry);
      return std::vector<int>{lt, rt, lx, ly, rx, ry};
    };
    Map none = Map::Parse(nullptr), buttonsOnly = Map::Parse("a=b,b=a");
    check("analog: the original controls change no value",
          analog(none, 7, 200, -32768, 32767, 5, -6) == std::vector<int>{7, 200, -32768, 32767, 5, -6});
    check("analog: a button map changes no value",
          analog(buttonsOnly, 7, 200, -32768, 32767, 5, -6) == std::vector<int>{7, 200, -32768, 32767, 5, -6});
    Map t = Map::Parse("left_trigger=right_trigger,right_trigger=left_trigger");
    check("triggers: custom, described both ways", t.state() == State::kCustom &&
          t.text() == "left_trigger=right_trigger,right_trigger=left_trigger" && t.TriggersSwapped() && !t.SticksSwapped());
    bool whole = true;
    for (int v = 0; v < 256; ++v) whole &= analog(t, uint8_t(v), uint8_t(255 - v), 1, 2, 3, 4) == std::vector<int>{255 - v, v, 1, 2, 3, 4};
    check("triggers: every value 0..255 moves whole to the other trigger, sticks untouched", whole);
    check("triggers: physical L2 at 29 stays 29 (no threshold of ours; the title's lock-on is its own)",
          analog(t, 29, 0, 0, 0, 0, 0)[1] == 29);
    check("triggers: trigger keys exchanged", t.MapKey(0x5806) == 0x5807 && t.MapKey(0x5807) == 0x5806);
    check("triggers: buttons and stick keys unchanged", t.Apply(0xF3FF) == 0xF3FF && t.MapKey(0x5820) == 0x5820);
    Map s = Map::Parse("left_stick=right_stick,right_stick=left_stick");
    check("sticks: both axes of each stick exchanged, full range",
          analog(s, 1, 2, -32768, 32767, 100, -100) == std::vector<int>{1, 2, 100, -100, -32768, 32767});
    bool keys = true;
    for (uint16_t k = 0; k < 8; ++k) keys &= s.MapKey(0x5820 + k) == 0x5830 + k && s.MapKey(0x5830 + k) == 0x5820 + k;
    check("sticks: the eight direction keys of each stick exchanged", keys);
    check("sticks: stick presses (L3 / R3) are buttons and stay", s.Apply(Bit("lstick_press")) == Bit("lstick_press"));
    Map all = Map::Parse("a=y,y=a,left_trigger=right_trigger,right_trigger=left_trigger,left_stick=right_stick,right_stick=left_stick");
    check("combined: buttons, triggers and sticks together", all.state() == State::kCustom && all.Apply(Bit("y")) == Bit("a") &&
          analog(all, 9, 0, 1, 0, 0, 0) == std::vector<int>{0, 9, 0, 0, 1, 0});
    const char* bad[] = {"a=left_trigger", "left_trigger=a", "left_trigger=left_stick", "left_trigger=right_trigger",
                         "left_stick=right_stick", "left_trigger=right_trigger,right_trigger=right_trigger",
                         "right_stick=left_stick,right_stick=right_stick", "lt=rt,rt=lt"};
    bool refused = true;
    for (const char* b : bad) {
      Map m = Map::Parse(b);
      refused &= m.state() == State::kInvalid && !m.TriggersSwapped() && !m.SticksSwapped() &&
                 analog(m, 1, 2, 3, 4, 5, 6) == std::vector<int>{1, 2, 3, 4, 5, 6};
    }
    check("analog: a button paired with an analog input, two kinds, a one-way or doubled pair are not used", refused);
    check("analog: identity named explicitly is the default",
          Map::Parse("left_trigger=left_trigger,right_trigger=right_trigger").state() == State::kDefault);
  }

  std::printf("R3HD_PADMAP_TEST %s %d/%d\n", g_fail ? "FAIL" : "PASS", g_pass, g_pass + g_fail);
  return g_fail ? 1 : 0;
}
