// Issue #6 / D-301: host-only checks of the F5 score / Combo toggle rules (tools/m2_host/r3hd_hud_state.h).
// No SDK, window, guest memory or input device: build with any C++20 compiler, e.g.
//   clang++ -std=c++20 -I tools/m2_host tools/hud_toggle_state_test.cpp -o hud_toggle_state_test.exe
#include <cstdio>
#include "r3hd_hud_state.h"

static int checks = 0, failures = 0;
static void Check(bool ok, const char* what) {
  ++checks;
  if (!ok) { ++failures; std::printf("FAIL %s\n", what); }
}

int main() {
  using r3hd_hud::State;
  // Setting values: only "f5" enables; absent / off / anything else stays off.
  Check(r3hd_hud::EnabledValue("f5"), "f5 enables");
  Check(!r3hd_hud::EnabledValue(nullptr) && !r3hd_hud::EnabledValue("off") && !r3hd_hud::EnabledValue("F5") &&
            !r3hd_hud::EnabledValue("on") && !r3hd_hud::EnabledValue(""), "absent, off and other values stay off");
  // Context: ordinary gameplay only.
  Check(r3hd_hud::OrdinaryContext("moor_00", 0, 0), "a gameplay level is ordinary");
  for (const char* level : {"", "menumap", "endgame", "staff"})
    Check(!r3hd_hud::OrdinaryContext(level, 0, 0), "menu / end / credits / unnamed are not ordinary");
  Check(!r3hd_hud::OrdinaryContext("moor_00", 1, 0), "paused is not ordinary");
  Check(!r3hd_hud::OrdinaryContext("moor_00", 0, 0x10000), "cinematic word is not ordinary");

  State s;
  Check(!s.Hidden(), "startup visible");
  s.Context(true, "moor_00");
  Check(!s.Down(false) && !s.Hidden(), "no toggle before focus");
  s.Up();
  s.Focus(true);
  Check(s.Down(false) && s.Hidden(), "first press hides");
  for (int i = 0; i < 100; ++i) Check(!s.Down(true) && s.Hidden(), "held repeats do not toggle");
  Check(!s.Down(false) && s.Hidden(), "a duplicate down without release does not toggle");
  s.Up();
  Check(s.Down(false) && !s.Hidden(), "second press shows");
  s.Up();
  Check(!s.Down(true) && !s.Hidden(), "modified / repeat press ignored");
  s.Up();
  // Every reset shows the HUD again and needs a fresh press afterwards.
  auto hide = [&] { s.Down(false); s.Up(); return s.Hidden(); };
  Check(hide(), "hide again");
  s.Context(false, "moor_00");
  Check(!s.Hidden(), "pause / cinematic shows");
  s.Context(true, "moor_00");
  Check(!s.Hidden(), "resume stays visible");
  Check(hide(), "hide after resume");
  s.Context(true, "moor_10");
  Check(!s.Hidden(), "level change shows");
  Check(hide(), "hide in new level");
  s.Focus(false);
  Check(!s.Hidden(), "focus loss shows");
  Check(!s.Down(false), "unfocused press ignored");
  s.Up();
  s.Focus(true);
  Check(!s.Hidden() && hide(), "focus back: visible until pressed");
  s.Available(false);
  Check(!s.Hidden(), "overlay owning input shows");
  Check(!s.Down(false), "press while overlay owns input ignored");
  s.Up();
  s.Available(true);
  Check(!s.Hidden() && hide(), "overlay closed: visible until pressed");
  s.Reset();
  Check(!s.Hidden(), "reserved overlay shortcut shows");
  // Not ordinary: presses never hide.
  s.Context(false, "menumap");
  Check(!s.Down(false) && !s.Hidden(), "menu press ignored");
  s.Up();
  std::printf("HUD_TOGGLE_STATE %s %d/%d\n", failures ? "FAIL" : "PASS", checks - failures, checks);
  return failures ? 1 : 0;
}
