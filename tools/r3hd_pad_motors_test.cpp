// G6-P75 (D-324): mock-pad regression for tools/r3hd_pad_motors.h. No SDL, no device, no game. A mock device holds the
// last motor speeds it was given, as a controller does. Ends with R3HD_PAD_MOTORS_TEST PASS n/n.
#include <cstdint>
#include <cstdio>
#include <vector>

#include "r3hd_pad_motors.h"

namespace {

int g_pass = 0, g_fail = 0;
void check(const char* name, bool ok) {
  std::printf("%s %s\n", ok ? "PASS" : "FAIL", name);
  (ok ? g_pass : g_fail)++;
}

struct Device {  // what the controller holds
  uint16_t left = 0, right = 0;
  int writes = 0;
  bool fail = false;  // the next writes are refused (a pad removed at that moment, a driver error)
  bool Write(uint16_t l, uint16_t r) {
    ++writes;
    if (fail) return false;
    left = l, right = r;
    return true;
  }
  bool Running() const { return left || right; }
};

struct Pad {
  Pad(Device* d) : device(d) {}
  Device* device;
  r3hd_motors::Motors motors;
};

// SetDeviceVibration as the patched SDL driver does it.
bool Vibrate(r3hd_motors::Outputs& out, Pad& pad, uint16_t l, uint16_t r) {
  if (out.closed()) return true;  // answered without a device call
  const bool sent = pad.device->Write(l, r);
  r3hd_motors::Requested(pad.motors, l, r, sent);
  return sent;
}

int Close(r3hd_motors::Outputs& out, std::vector<Pad>& pads) {
  return out.Close(pads, [](Pad& p) { return p.device->Write(0, 0); });
}

}  // namespace

int main() {
  // Baseline (the behaviour before D-324): the game ends while the title has a pad vibrating and nothing reaches it.
  {
    Device d;
    Pad p{&d};
    r3hd_motors::Outputs out;
    Vibrate(out, p, 0xC000, 0x4000);
    check("baseline: without a close the controller keeps the title's last request", d.Running() && d.writes == 1);
  }
  // The close stops a vibrating pad once, and only that pad.
  {
    Device a, b, c;
    std::vector<Pad> pads{{&a}, {&b}, {&c}};
    r3hd_motors::Outputs out;
    Vibrate(out, pads[0], 0xC000, 0);
    Vibrate(out, pads[1], 0, 0);  // b was told zero: nothing runs
    const int sent = Close(out, pads);
    check("close: the vibrating pad is stopped", !a.Running() && a.writes == 2);
    check("close: a pad already at zero gets no output", b.writes == 1);
    check("close: a pad never vibrated gets no output", c.writes == 0);
    check("close: returns the number of pads given a stop", sent == 1);
    check("close: outputs closed", out.closed());
    check("close: a second close sends nothing", Close(out, pads) == 0 && a.writes == 2);
    check("after close: the title's request reaches no device", Vibrate(out, pads[0], 0xFFFF, 0xFFFF) &&
                                                                    a.writes == 2 && !a.Running());
  }
  // Request bookkeeping.
  {
    Device d;
    Pad p{&d};
    r3hd_motors::Outputs out;
    check("fresh pad: not running", !p.motors.running);
    Vibrate(out, p, 0, 1);
    check("right motor alone: running", p.motors.running);
    Vibrate(out, p, 0, 0);
    check("zero request taken: not running", !p.motors.running);
    d.fail = true;
    Vibrate(out, p, 0x8000, 0);
    check("refused start: counted as possibly running", p.motors.running);
    d.fail = false;
    Vibrate(out, p, 0x8000, 0);
    d.fail = true;
    Vibrate(out, p, 0, 0);
    check("refused stop: still counted as running", p.motors.running && d.Running());
    d.fail = false;
    std::vector<Pad> pads{p};
    Close(out, pads);
    check("close after a refused stop: the pad is stopped", !d.Running() && !pads[0].motors.running);
  }
  // A stop the device refuses: one attempt, the outputs still close.
  {
    Device d;
    std::vector<Pad> pads{{&d}};
    r3hd_motors::Outputs out;
    Vibrate(out, pads[0], 0x1000, 0x1000);
    d.fail = true;
    const int sent = Close(out, pads);
    check("refused close: one attempt, outputs closed", sent == 1 && out.closed() && d.writes == 2);
    check("refused close: no retry afterwards", Close(out, pads) == 0 && d.writes == 2);
  }
  // No pads at all (keyboard only): closing is harmless.
  {
    std::vector<Pad> none;
    r3hd_motors::Outputs out;
    check("no pads: nothing sent, outputs closed", Close(out, none) == 0 && out.closed());
  }
  std::printf("R3HD_PAD_MOTORS_TEST %s %d/%d\n", g_fail ? "FAIL" : "PASS", g_pass, g_pass + g_fail);
  return g_fail ? 1 : 0;
}
