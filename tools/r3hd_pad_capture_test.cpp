// Settings input only. The runner extracts the production decoder into decoder.h.
// Fixtures follow SDL PS5SimpleStatePacket_t / PS5StatePacket_t at the SDK's SDL
// pin 8bf3b7215ad9fc3deb583c6a3a37c6c67f2e24e4 (not the Settings offset table).
#include <cstdint>
#include <cstdio>
#include <utility>
#include <vector>
using DWORD = unsigned long;
#include "decoder.h"

static int checks = 0, failures = 0;
static void check(bool ok, const char* name) {
  ++checks;
  if (!ok) { ++failures; std::printf("FAIL %s\n", name); }
}

// Transport envelopes plus independently specified sequential payload fields.
enum Format { Simple10, Simple78, Usb64, Enhanced78, DS4Usb64, DS4Bt78 };
static std::vector<uint8_t> report(Format f, uint8_t face = 8, uint8_t shoulders = 0,
                                   uint8_t lt = 0, uint8_t rt = 0) {
  std::vector<uint8_t> r;
  if (f == Enhanced78) r = {0x31, 0xA0};
  else if (f == DS4Bt78) r = {0x11, 0xC0, 0};
  else r = {0x01};
  r.insert(r.end(), {128, 128, 128, 128});
  if (f == Usb64 || f == Enhanced78) r.insert(r.end(), {lt, rt, 0xA5, face, shoulders, 0});
  else r.insert(r.end(), {face, shoulders, 0, lt, rt});
  r.resize(f == Simple10 ? 10 : f == Usb64 || f == DS4Usb64 ? 64 : 78, 0);
  return r;
}
static bool parse(Format f, const std::vector<uint8_t>& r, PadSample& s) {
  return ParseSony(f >= DS4Usb64 ? Sony::DualShock4 : Sony::DualSense, r.data(), r.size(), s);
}
int main() {
  PadSample s;
  // Decisive reproduction of the human symptoms: old n>=32 chooses full USB
  // for a padded simple BT report, reading trigger bytes as buttons and vice versa.
  auto r = report(Simple78, 8, 4, 0x10, 0);
  parse(Simple78, r, s);
  std::printf("padded BT L2: buttons=%04x lt=%u rt=%u\n", s.buttons, s.lt, s.rt);
  check(s.buttons == 0 && s.lt == 0x10 && s.rt == 0, "BT simple78 L2 is analog, not Square");
  r = report(Simple78, 8, 8, 0, 0x31);
  parse(Simple78, r, s);
  std::printf("padded BT R2: buttons=%04x lt=%u rt=%u\n", s.buttons, s.lt, s.rt);
  check(s.buttons == 0 && s.rt == 0x31, "BT simple78 R2 is analog, not L1");
  r = report(Simple78, 0x88);
  parse(Simple78, r, s);
  check(s.buttons == 0x8000 && s.lt == 0, "BT simple78 Triangle is a button, not a trigger");
  for (Format f : {Simple10, Simple78, Usb64, Enhanced78, DS4Usb64, DS4Bt78}) {
    check(parse(f, report(f), s) && s.buttons == 0 && s.lt == 0 && s.rt == 0 && s.lx == 0 && s.ry == 0,
          "neutral, including full-report nonzero sequence counter");
    for (auto b : {std::pair<uint8_t, uint16_t>{0x10, 0x4000}, {0x20, 0x1000}, {0x40, 0x2000}, {0x80, 0x8000}})
      check(parse(f, report(f, 8 | b.first), s) && s.buttons == b.second && s.lt == 0 && s.rt == 0,
            "face button classification");
    for (auto b : {std::pair<uint8_t, uint16_t>{1, 0x100}, {2, 0x200}, {0x10, 0x20}, {0x20, 0x10}, {0x40, 0x40}, {0x80, 0x80}})
      check(parse(f, report(f, 8, b.first), s) && s.buttons == b.second && s.lt == 0 && s.rt == 0,
            "shoulder, menu and stick-click classification");
    const uint16_t hats[] = {1, 9, 8, 10, 2, 6, 4, 5, 0};
    for (uint8_t h = 0; h < 9; ++h)
      check(parse(f, report(f, h), s) && s.buttons == hats[h], "D-pad including diagonals and neutral");
    check(parse(f, report(f, 8, 0x0C, 170, 210), s) && s.buttons == 0 && s.lt == 170 && s.rt == 210,
          "trigger digital bits never become buttons");
    r = report(f);
    size_t st = f == Enhanced78 ? 2 : f == DS4Bt78 ? 3 : 1;
    r[st] = 0; r[st + 1] = 255; r[st + 2] = 255; r[st + 3] = 0;
    check(parse(f, r, s) && s.lx == -32768 && s.ly == -32512 && s.rx == 32512 && s.ry == 32768,
          "all four axes and directions");
  }
  for (size_t n : {0u, 1u, 9u, 11u, 32u, 63u, 65u, 77u, 79u}) {
    r.assign(n, 0); if (n) r[0] = 1;
    check(!ParseSony(Sony::DualSense, r.data(), r.size(), s), "unknown/truncated DualSense ID01 length refused");
  }
  r.assign(12, 0); r[0] = 0x31;
  check(!ParseSony(Sony::DualSense, r.data(), r.size(), s), "truncated enhanced BT refused");
  r = report(Usb64);
  check(!ParseSony(Sony::None, r.data(), r.size(), s), "unknown device refused");
  r[0] = 0x02;
  check(!ParseSony(Sony::DualSense, r.data(), r.size(), s), "output/other report refused");
  std::printf("PAD_CAPTURE_DECODER %s checks=%d failures=%d\n", failures ? "FAIL" : "PASS", checks, failures);
  return failures ? 1 : 0;
}
